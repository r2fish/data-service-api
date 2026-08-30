"""C-17 -- declaration/addressability/uniqueness agreement (SI-05, SI-15).

design: docs/design/R2DB_CCR13_STORAGE_V1.md section 4 "C-17 宣言と実挙動の
一致", registered in `conformance-tests/CONDITIONS.md`. Every test here
carries @pytest.mark.condition("C-17") via the module-level `pytestmark`.

Structure: every test function branches once, at its top, on whether this
adapter's peer declares `row_addressability: enabled`. The `enabled` branch
performs the real behavioral assertion the test's name describes, against a
fresh entity this test creates. The *not*-enabled branch (currently only
`MitateDB-api`, per its own honest `unavailable` declaration) does not skip
-- design principle 4 ("uncertainty must not silently become permission")
and this repository's own "skip is fail" rule both forbid that -- it instead
runs `_assert_declaration_dependent_surface_is_absent_or_denied`, which
accepts either of two honest evidence forms for this side (design
docs/design/R2DB_CCR13_STORAGE_V1.md section 4: "宣言に依存する操作の不在は
structural evidence", widened by docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md
R-8/WP-2.5, B-2/D-H):

  (a) **structurally absent** -- `create_unique_index` raises `SurfaceAbsent`
      because no real entry point on the peer's public surface could even
      receive an index-creation request at all. That claim is independently
      verified via `signature_forbids_parameters` rather than accepted on
      the adapter's word. This is the only form any currently-registered
      adapter takes (`MitateDB-api`'s in-process `ApplicationDeveloper` has
      no schema-mutation call with an index/uniqueness parameter).
  (b) **real, present denial** -- `create_unique_index` raises a real
      `ConformanceDenial(CAPABILITY_UNSUPPORTED)` because a real entry point
      DOES exist (e.g. a mounted `/v1/schema/operations` dispatcher) but the
      peer refuses this specific operation the way its own
      `row_addressability: unavailable` declaration requires -- the same
      "受理する but denies, before execution" shape `test_c18_revision_
      precondition_semantics.py`'s unavailable side already establishes as
      a legitimate alternative to (a), and `SurfaceAbsent`'s own docstring
      itself forbids raising `SurfaceAbsent` to excuse a peer that actually
      received and mishandled a request. Only `CAPABILITY_UNSUPPORTED` is
      accepted here -- any other denial code is a genuine finding, not a
      second honest form of absence. No currently-registered adapter takes
      this form; it exists so a future adapter with a real, mounted schema
      surface (a mount whose declared capability nonetheless stays
      `unavailable`) is not forced to lie via `SurfaceAbsent` about an entry
      point that demonstrably exists.

Every test function in this module therefore makes a genuine assertion
against every registered adapter, never a bare pass-through.
"""
from __future__ import annotations

import pytest

from absence import assert_control_operation_absent_or_uniformly_refused
from adapter import (
    CATALOG_SURFACE_ABSENT,
    UNCLASSIFIED,
    BatchOperation,
    ConformanceDenial,
    Fixture,
    VALID_CONFIRMATION,
    fresh_identifier,
    load_contract,
    load_contract_error_codes,
)
from schema_check import assert_valid

pytestmark = pytest.mark.condition("C-17")


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


def _row_addressability_enabled(adapter) -> bool:
    document = adapter.capability_document()
    return document.get("capabilities", {}).get("row_addressability", {}).get("status") == "enabled"


def _assert_declaration_dependent_surface_is_absent_or_denied(adapter, fx: Fixture) -> None:
    """The falsifiable fact design section 4 prescribes for a
    `row_addressability: unavailable` peer: every operation whose meaning
    depends on a catalog uniqueness/address declaration -- `create_unique_
    index` chief among them, since `upsert`'s own key-selection vocabulary
    (`unique_key`) is meaningless without one -- must be either structurally
    absent or, if a real entry point exists, refused before execution.

    Two honest evidence forms are accepted (module docstring above; design
    docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md R-8/WP-2.5, B-2/D-H):

    (a) `SurfaceAbsent` -- no real entry point exists at all.
    (b) `ConformanceDenial(CAPABILITY_UNSUPPORTED)` -- a real entry point
        DOES exist and refuses this specific request, matching the peer's
        own `row_addressability: unavailable` declaration.

    Both forms' own verification is delegated to `absence.py`'s shared
    `assert_control_operation_absent_or_uniformly_refused` -- the same
    mechanism `test_c14_authority_boundary.py`'s control-plane absence
    checks and C-06's `drop_entity` absent branch already use (WP-2.5
    review m-1: this function used to reimplement form (a)'s re-
    verification inline, `assert not signature_forbids_parameters(...)`,
    without the shared helper's additional `declared_surface >=
    public_operation_callables()` check -- migrating onto the shared
    helper closes that gap for free, rather than hand-maintaining a second,
    weaker copy of the same hardening). Only `CAPABILITY_UNSUPPORTED` is
    accepted for form (b); any other denial code is a genuine finding (a
    real entry point misclassifying the refusal), never a second form of
    absence -- the shared helper enforces this identically to what this
    function's own inline check used to.

    Requirement (d) of WP-2.5, C-17-specific and therefore NOT part of the
    shared helper (which has no notion of a capability-specific follow-up
    state check): once the shared helper reports `"declared_unavailable"`
    (form (b)), this additionally confirms no unique index was actually
    created, by probing with two colliding inserts and requiring BOTH to
    succeed -- a real unique index would have refused the second with
    `CONFLICT`.
    """
    entity = fresh_identifier("c17_absent")
    adapter.create_entity(fx.developer_a, entity, {"label": "text"})
    index_name = fresh_identifier("idx")

    def _attempt_create_unique_index() -> None:
        adapter.create_unique_index(fx.developer_a, entity, index_name, ["label"])

    form = assert_control_operation_absent_or_uniformly_refused(adapter, _attempt_create_unique_index)
    if form != "declared_unavailable":
        return  # form (a), surface_absent -- nothing further to check here

    # (d): a real entry point that genuinely refused the index request
    # (form (b)) must not have created it anyway. Probed by attempting two
    # inserts that would collide under the requested (label) unique index
    # -- both must succeed, since no index was ever actually created.
    adapter.attempt_mutation(
        fx.runtime_a, entity, "insert", values={"label": "c17-dup-probe"}, where_field=None, where_value=None,
    )
    adapter.attempt_mutation(
        fx.runtime_a, entity, "insert", values={"label": "c17-dup-probe"}, where_field=None, where_value=None,
    )
    rows = adapter.select_eq(fx.runtime_a, entity, ["label"], "label", "c17-dup-probe")
    assert len(rows) == 2, (
        f"{adapter.name}: create_unique_index was refused with CAPABILITY_UNSUPPORTED (a present-denial "
        f"claim of no effect), but a duplicate-value probe found {len(rows)} row(s) instead of 2 -- an "
        "index enforcing uniqueness on 'label' appears to have been created despite the refusal"
    )


# --- 1. declaration_required: every declared entity's descriptor is complete ---


def test_declared_entities_satisfy_declaration_required_completeness(adapter, fx: Fixture):
    entity = fresh_identifier("c17_declare")
    adapter.create_entity(fx.developer_a, entity, {"label": "text"})
    adapter.insert(fx.runtime_a, entity, {"label": "seed"})

    if not _row_addressability_enabled(adapter):
        _assert_declaration_dependent_surface_is_absent_or_denied(adapter, fx)
        return

    contract = load_contract()
    entity_descriptor_schema = contract["definitions"]["EntityDescriptor"]
    document = adapter.catalog_document(fx.developer_a)
    assert document != CATALOG_SURFACE_ABSENT, (
        f"{adapter.name}: declares row_addressability enabled but catalog_document() reports "
        "CATALOG_SURFACE_ABSENT"
    )
    entities_by_name = {item["entity"]: item for item in document["entities"]}
    assert entity in entities_by_name, f"{adapter.name}: freshly created entity is not in its own catalog document"

    # declaration_required's full-count sweep: every entity this document
    # names -- not only the one this test just created -- must carry a
    # complete, schema-valid declaration if it claims `mutation_class`
    # `mutable` at all (`EntityDescriptor`'s own conditional `required`).
    # The positive control is non-vacuous: `entity` above is guaranteed to
    # be in this set and guaranteed `mutable` (R-1: r2db-api's entities are
    # unconditionally mutable), so this loop always covers at least one
    # real, mutable entity when row_addressability is enabled.
    saw_mutable = False
    for name, descriptor in entities_by_name.items():
        assert_valid(descriptor, entity_descriptor_schema, contract, label=f"EntityDescriptor[{name!r}]")
        # WP-5 final review (blocker): `EntityDescriptor`'s own schema only
        # requires address_fields/address_reuse/mutation_class together
        # when `mutation_class` is ALREADY present and equal to `"mutable"`
        # (its `if/then` is keyed on that). An entity missing
        # `mutation_class` entirely satisfies that schema trivially and was
        # previously waved through here too (`.get(...) == "mutable"` is
        # `False` for a missing key, same as for a genuinely non-mutable
        # one) -- so a peer that silently dropped the declaration for one
        # entity while `row_addressability` stayed `enabled` was
        # undetectable by this suite. `declaration_required` ("must not be
        # advertised as enabled unless every entity carries a declaration")
        # requires every entity to declare a `mutation_class` once the
        # capability itself is enabled -- checked here explicitly, since
        # C-11's own schema check does not (`EntityDescriptor.required` is
        # only `entity`/`fields`) and this is the only condition that does.
        assert "mutation_class" in descriptor, (
            f"{adapter.name}: entity {name!r} has no mutation_class declaration at all, but "
            "row_addressability is declared enabled -- declaration_required requires every entity to "
            "carry one"
        )
        if descriptor["mutation_class"] == "mutable":
            saw_mutable = True
            for address_field in descriptor["address_fields"]:
                assert address_field in descriptor["fields"], (
                    f"{adapter.name}: entity {name!r} declares address_fields {descriptor['address_fields']!r} "
                    f"not a subset of its own fields {descriptor['fields']!r}"
                )
    assert saw_mutable, (
        f"{adapter.name}: declares row_addressability enabled, but no entity in its own catalog document "
        "declares mutation_class 'mutable' -- this test's sweep would be vacuous"
    )


# --- 2. address is visible (selectable) and targetable (>=1 eq match) -----


def test_address_field_is_visible_and_targets_at_most_one_row(adapter, fx: Fixture):
    if not _row_addressability_enabled(adapter):
        _assert_declaration_dependent_surface_is_absent_or_denied(adapter, fx)
        return

    entity = fresh_identifier("c17_address")
    adapter.create_entity(fx.developer_a, entity, {"label": "text"})
    document = adapter.catalog_document(fx.developer_a)
    descriptor = next(item for item in document["entities"] if item["entity"] == entity)
    address_fields = descriptor["address_fields"]

    affected1, addresses1 = adapter.attempt_mutation_with_addresses(
        fx.runtime_a, entity, "insert", values={"label": "row-one"}, where_field=None, where_value=None,
    )
    assert affected1 == 1 and addresses1, f"{adapter.name}: insert did not report an assigned address"
    address1 = addresses1[0]["address"]
    affected2, addresses2 = adapter.attempt_mutation_with_addresses(
        fx.runtime_a, entity, "insert", values={"label": "row-two"}, where_field=None, where_value=None,
    )
    address2 = addresses2[0]["address"]
    assert address1 != address2, f"{adapter.name}: two distinct inserts were assigned the same address"

    # property 2: visible -- every address field is an ordinary selectable
    # field that appears in a query's own result.
    select_fields = list(address_fields) + ["label"]
    rows = adapter.select_eq(fx.runtime_a, entity, select_fields, address_fields[0], address1[address_fields[0]])
    assert rows and all(field in rows[0] for field in address_fields), (
        f"{adapter.name}: address field(s) {address_fields!r} did not appear in the query result"
    )
    for field in address_fields:
        assert rows[0][field] == address1[field], (
            f"{adapter.name}: selected address field {field!r} disagrees with the assigned address"
        )

    # property 3: targetable -- a full-address eq match returns exactly the
    # one row that address belongs to, never the other one.
    matched_labels = {row["label"] for row in adapter.select_eq(fx.runtime_a, entity, ["label"], address_fields[0], address1[address_fields[0]])}
    assert matched_labels == {"row-one"}, (
        f"{adapter.name}: full-address eq match on {address_fields[0]!r} returned {matched_labels!r}, expected only 'row-one'"
    )


# --- 3. address is immutable ------------------------------------------------


def test_update_that_would_change_an_address_field_is_rejected(adapter, fx: Fixture):
    if not _row_addressability_enabled(adapter):
        _assert_declaration_dependent_surface_is_absent_or_denied(adapter, fx)
        return

    entity = fresh_identifier("c17_immutable")
    adapter.create_entity(fx.developer_a, entity, {"label": "text"})
    document = adapter.catalog_document(fx.developer_a)
    descriptor = next(item for item in document["entities"] if item["entity"] == entity)
    address_field = descriptor["address_fields"][0]

    adapter.attempt_mutation(fx.runtime_a, entity, "insert", values={"label": "seed"}, where_field=None, where_value=None)
    with pytest.raises(ConformanceDenial) as ei:
        adapter.attempt_mutation(
            fx.runtime_a, entity, "update",
            values={address_field: 999999}, where_field="label", where_value="seed",
        )
    _assert_is_contract_code(ei.value.code)
    assert ei.value.code == "VALIDATION_FAILED", (
        f"{adapter.name}: update carrying an address-field value was refused with {ei.value.code!r}, "
        "expected VALIDATION_FAILED (property 4, addressability.properties 'Immutable')"
    )
    # No partial/silent effect: the row's own (real) address is unchanged.
    rows = adapter.select_eq(fx.runtime_a, entity, ["label"], "label", "seed")
    assert rows, f"{adapter.name}: row disappeared after a rejected address-changing update"


# --- 4. a write that would duplicate a declared unique key is CONFLICT -----


def test_unique_key_duplicate_write_is_refused_with_conflict(adapter, fx: Fixture):
    if not _row_addressability_enabled(adapter):
        _assert_declaration_dependent_surface_is_absent_or_denied(adapter, fx)
        return

    entity = fresh_identifier("c17_uniqconflict")
    adapter.create_entity(fx.developer_a, entity, {"tag": "text"})
    adapter.create_unique_index(fx.developer_a, entity, fresh_identifier("uniq"), ["tag"])
    adapter.attempt_mutation(fx.runtime_a, entity, "insert", values={"tag": "dup"}, where_field=None, where_value=None)
    with pytest.raises(ConformanceDenial) as ei:
        adapter.attempt_mutation(fx.runtime_a, entity, "insert", values={"tag": "dup"}, where_field=None, where_value=None)
    _assert_is_contract_code(ei.value.code)
    assert ei.value.code == "CONFLICT", (
        f"{adapter.name}: inserting a duplicate declared-unique key value was refused with {ei.value.code!r}, "
        "expected CONFLICT"
    )
    rows = adapter.select_eq(fx.runtime_a, entity, ["tag"], "tag", "dup")
    assert len(rows) == 1, f"{adapter.name}: {len(rows)} rows carry the supposedly-unique tag 'dup' after a rejected duplicate write"


# --- 5. upsert: zero declared unique keys -----------------------------------


def test_upsert_on_entity_with_no_declared_unique_key_is_capability_unsupported(adapter, fx: Fixture):
    if not _row_addressability_enabled(adapter):
        _assert_declaration_dependent_surface_is_absent_or_denied(adapter, fx)
        return

    entity = fresh_identifier("c17_nokey")
    adapter.create_entity(fx.developer_a, entity, {"label": "text"})
    count_before = adapter.count(fx.runtime_a, entity)
    with pytest.raises(ConformanceDenial) as ei:
        adapter.attempt_mutation(fx.runtime_a, entity, "upsert", values={"label": "x"}, where_field=None, where_value=None)
    _assert_is_contract_code(ei.value.code)
    assert ei.value.code == "CAPABILITY_UNSUPPORTED", (
        f"{adapter.name}: upsert on an entity with no declared uniqueness key: {ei.value.code!r}, expected CAPABILITY_UNSUPPORTED"
    )
    assert adapter.count(fx.runtime_a, entity) == count_before, f"{adapter.name}: state changed despite a refused upsert"

    # WP-5 final review (recommendation): precedence probe. The contract's
    # own upsert text is explicit that "on an entity with no declared
    # uniqueness key, upsert fails with CAPABILITY_UNSUPPORTED regardless of
    # any unique_key field (the capability check precedes key-name
    # resolution)". A `unique_key` naming an undeclared key on an entity
    # that HAS keys is `NOT_FOUND` (covered by the multi-key test below);
    # this probe is the other half -- attaching a `unique_key` here must
    # not change the answer to `NOT_FOUND` just because a key-name lookup
    # was attempted before the capability gate.
    with pytest.raises(ConformanceDenial) as ei_named:
        adapter.attempt_mutation(
            fx.runtime_a, entity, "upsert", values={"label": "x"}, where_field=None, where_value=None,
            unique_key="bogus",
        )
    _assert_is_contract_code(ei_named.value.code)
    assert ei_named.value.code == "CAPABILITY_UNSUPPORTED", (
        f"{adapter.name}: upsert with unique_key='bogus' on an entity with no declared uniqueness key: "
        f"{ei_named.value.code!r}, expected CAPABILITY_UNSUPPORTED (the capability check must precede "
        "key-name resolution, not resolve to NOT_FOUND)"
    )
    assert adapter.count(fx.runtime_a, entity) == count_before, (
        f"{adapter.name}: state changed despite a refused upsert with a bogus unique_key"
    )


# --- 6. upsert: exactly one declared unique key -----------------------------


def test_upsert_on_entity_with_one_declared_unique_key_resolves_insert_then_update(adapter, fx: Fixture):
    if not _row_addressability_enabled(adapter):
        _assert_declaration_dependent_surface_is_absent_or_denied(adapter, fx)
        return

    entity = fresh_identifier("c17_onekey")
    adapter.create_entity(fx.developer_a, entity, {"tag": "text", "note": "text"})
    adapter.create_unique_index(fx.developer_a, entity, fresh_identifier("uniq"), ["tag"])

    affected1, addresses1 = adapter.attempt_mutation_with_addresses(
        fx.runtime_a, entity, "upsert", values={"tag": "k1", "note": "first"}, where_field=None, where_value=None,
    )
    assert affected1 == 1, f"{adapter.name}: first upsert (no existing key match) did not report affected 1"
    assert addresses1 and len(addresses1) == 1, (
        f"{adapter.name}: first upsert (no existing key match) must resolve to insert and appear in "
        f"assigned_addresses -- got {addresses1!r}"
    )

    affected2, addresses2 = adapter.attempt_mutation_with_addresses(
        fx.runtime_a, entity, "upsert", values={"tag": "k1", "note": "second"}, where_field=None, where_value=None,
    )
    assert affected2 == 1, f"{adapter.name}: second upsert (existing key match) did not report affected 1"
    assert not addresses2, (
        f"{adapter.name}: second upsert (existing key match) resolved to update but still appeared in "
        f"assigned_addresses -- got {addresses2!r}"
    )
    rows = adapter.select_eq(fx.runtime_a, entity, ["tag", "note"], "tag", "k1")
    assert len(rows) == 1 and rows[0]["note"] == "second", (
        f"{adapter.name}: upsert on an existing key must update the one existing row, got {rows!r}"
    )


# --- 7. upsert on an entity with more than one declared unique key --------


def test_upsert_on_entity_with_multiple_unique_keys_requires_named_unique_key(adapter, fx: Fixture):
    if not _row_addressability_enabled(adapter):
        _assert_declaration_dependent_surface_is_absent_or_denied(adapter, fx)
        return

    entity = fresh_identifier("c17_multikey")
    adapter.create_entity(fx.developer_a, entity, {"a": "text", "b": "text"})
    key_a = fresh_identifier("keya")
    key_b = fresh_identifier("keyb")
    adapter.create_unique_index(fx.developer_a, entity, key_a, ["a"])
    adapter.create_unique_index(fx.developer_a, entity, key_b, ["b"])

    # (h) omitting unique_key on a multi-key entity: VALIDATION_FAILED, and
    # the capability check (§ R-5) precedes key-name resolution -- the
    # entity clearly does declare uniqueness keys, so this must not be
    # confused with the zero-key CAPABILITY_UNSUPPORTED case above.
    count_before = adapter.count(fx.runtime_a, entity)
    with pytest.raises(ConformanceDenial) as ei_omit:
        adapter.attempt_mutation(fx.runtime_a, entity, "upsert", values={"a": "1", "b": "2"}, where_field=None, where_value=None)
    _assert_is_contract_code(ei_omit.value.code)
    assert ei_omit.value.code == "VALIDATION_FAILED", (
        f"{adapter.name}: upsert omitting unique_key on a multi-key entity: {ei_omit.value.code!r}, expected VALIDATION_FAILED"
    )
    assert adapter.count(fx.runtime_a, entity) == count_before, f"{adapter.name}: state changed despite a refused ambiguous upsert"

    # (i) naming a real declared key executes for real.
    affected = adapter.attempt_mutation(
        fx.runtime_a, entity, "upsert", values={"a": "1", "b": "2"}, where_field=None, where_value=None, unique_key=key_a,
    )
    assert affected == 1, f"{adapter.name}: upsert naming a real declared unique_key did not execute"

    # (j) a unique_key naming no declared key at all: NOT_FOUND.
    with pytest.raises(ConformanceDenial) as ei_unknown:
        adapter.attempt_mutation(
            fx.runtime_a, entity, "upsert", values={"a": "9", "b": "9"}, where_field=None, where_value=None,
            unique_key=fresh_identifier("nosuchkey"),
        )
    _assert_is_contract_code(ei_unknown.value.code)
    assert ei_unknown.value.code == "NOT_FOUND", (
        f"{adapter.name}: upsert naming an undeclared unique_key: {ei_unknown.value.code!r}, expected NOT_FOUND"
    )

    # (k) unique_key on any operation other than upsert: VALIDATION_FAILED.
    with pytest.raises(ConformanceDenial) as ei_wrong_op:
        adapter.attempt_mutation(
            fx.runtime_a, entity, "insert", values={"a": "5", "b": "6"}, where_field=None, where_value=None,
            unique_key=key_a,
        )
    _assert_is_contract_code(ei_wrong_op.value.code)
    assert ei_wrong_op.value.code == "VALIDATION_FAILED", (
        f"{adapter.name}: unique_key attached to insert: {ei_wrong_op.value.code!r}, expected VALIDATION_FAILED"
    )


# --- 8. address_reuse: never -------------------------------------------------


def test_deleted_address_is_never_reused_by_a_later_insert(adapter, fx: Fixture):
    if not _row_addressability_enabled(adapter):
        _assert_declaration_dependent_surface_is_absent_or_denied(adapter, fx)
        return

    entity = fresh_identifier("c17_reuse")
    adapter.create_entity(fx.developer_a, entity, {"tag": "text"})
    document = adapter.catalog_document(fx.developer_a)
    descriptor = next(item for item in document["entities"] if item["entity"] == entity)
    assert descriptor["address_reuse"] == "never", (
        f"{adapter.name}: entity declares address_reuse {descriptor['address_reuse']!r}, "
        "this test only exercises the 'never' declaration"
    )
    address_field = descriptor["address_fields"][0]

    affected, addresses = adapter.attempt_mutation_with_addresses(
        fx.runtime_a, entity, "insert", values={"tag": "first"}, where_field=None, where_value=None,
    )
    retired_address = addresses[0]["address"]
    deleted = adapter.delete(fx.runtime_a, entity, "tag", "first", destructive=True, confirmation=VALID_CONFIRMATION)
    assert deleted == 1, f"{adapter.name}: expected the seeded row to be deleted"

    affected2, addresses2 = adapter.attempt_mutation_with_addresses(
        fx.runtime_a, entity, "insert", values={"tag": "second"}, where_field=None, where_value=None,
    )
    new_address = addresses2[0]["address"]
    assert new_address[address_field] != retired_address[address_field], (
        f"{adapter.name}: a retired address ({retired_address!r}) was reused by a later insert ({new_address!r}), "
        "despite address_reuse: never"
    )


# --- 9. assigned_addresses' insert-only membership holds within one batch --


def test_assigned_addresses_membership_holds_when_mixed_in_one_batch(adapter, fx: Fixture):
    # WP-5 final review (recommendation): every other assigned_addresses
    # check in this file calls `attempt_mutation_with_addresses` once per
    # operation, so a defect that only shows up when different operation
    # kinds share one real atomic batch (e.g. an accumulation bug that
    # attaches an address entry to a non-insert operation only because a
    # real insert elsewhere in the same batch precedes it) would not be
    # caught anywhere in this file. This test presents one real batch
    # mixing insert, update, upsert-resolving-to-update, and a properly
    # confirmed delete together, and requires exactly one assigned_addresses
    # element -- the insert's -- no matter what else shares the batch.
    if not _row_addressability_enabled(adapter):
        _assert_declaration_dependent_surface_is_absent_or_denied(adapter, fx)
        return

    entity = fresh_identifier("c17_batchmix")
    adapter.create_entity(fx.developer_a, entity, {"marker": "text", "tag": "text"})
    adapter.create_unique_index(fx.developer_a, entity, fresh_identifier("uniq"), ["tag"])
    # Three distinct pre-existing rows, one per non-insert operation below,
    # so each operation's own effect can be verified independently
    # afterward without one operation's write overwriting another's.
    adapter.attempt_mutation(
        fx.runtime_a, entity, "insert", values={"marker": "to-update", "tag": "tag-for-update"},
        where_field=None, where_value=None,
    )
    adapter.attempt_mutation(
        fx.runtime_a, entity, "insert", values={"marker": "seed-for-upsert", "tag": "upsert-target-tag"},
        where_field=None, where_value=None,
    )
    adapter.attempt_mutation(
        fx.runtime_a, entity, "insert", values={"marker": "to-delete", "tag": "tag-for-delete"},
        where_field=None, where_value=None,
    )

    operations = [
        BatchOperation(operation="insert", values={"marker": "brand-new", "tag": "insert-tag"}),
        BatchOperation(operation="update", values={"marker": "updated-in-place"}, where_field="marker", where_value="to-update"),
        # Matches the second seeded row's own unique key ("upsert-target-
        # tag" is not touched by the update above, which only targets the
        # first row), so this resolves to an update, not an insert.
        BatchOperation(operation="upsert", values={"tag": "upsert-target-tag", "marker": "resolved-as-update"}),
        BatchOperation(
            operation="delete", where_field="marker", where_value="to-delete",
            destructive=True, confirmation=VALID_CONFIRMATION,
        ),
    ]
    affected, addresses = adapter.attempt_batch_with_addresses(fx.runtime_a, entity, operations)
    assert affected == 4, (
        f"{adapter.name}: batch of insert+update+upsert(update-resolving)+delete reported affected "
        f"{affected!r}, expected 4"
    )
    assert addresses is not None and len(addresses) == 1, (
        f"{adapter.name}: assigned_addresses for a batch containing exactly one insert -- alongside an "
        "update, an update-resolving upsert, and a delete -- must contain exactly one element, got "
        f"{addresses!r}"
    )
    assert addresses[0]["address"] not in (
        None,
    ), f"{adapter.name}: the one assigned_addresses element must carry a real address, got {addresses[0]!r}"

    rows = adapter.select_eq(fx.runtime_a, entity, ["marker"], "marker", "updated-in-place")
    assert rows, f"{adapter.name}: the batch's update did not take effect"
    rows_resolved = adapter.select_eq(fx.runtime_a, entity, ["marker"], "tag", "upsert-target-tag")
    assert rows_resolved and rows_resolved[0]["marker"] == "resolved-as-update", (
        f"{adapter.name}: the batch's upsert did not resolve to an update of the existing row"
    )
    rows_deleted = adapter.select_eq(fx.runtime_a, entity, ["marker"], "marker", "to-delete")
    assert not rows_deleted, f"{adapter.name}: the batch's delete did not take effect"
