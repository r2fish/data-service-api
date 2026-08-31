"""C-16 -- cross-entity atomicity (SI-08, SI-11).

design: docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md section 3
("WP-3"), registered in `conformance-tests/CONDITIONS.md`. Every test here
carries @pytest.mark.condition("C-16") via the module-level `pytestmark`.

Structure mirrors `test_c17_declaration_agreement.py`'s own house style:
every vector test branches once, at its top, on whether this adapter's peer
declares `cross_entity_mutation` `enabled`/`partial` (`_cross_entity_
available`). The available branch performs the real behavioral assertion
the vector describes, against `fx.shared_entity`/`fx.a_only_entity` -- two
real, distinct entities that already coexist under Application A
(`fx.developer_a`/`fx.runtime_a`), exactly what a cross-entity batch needs,
with no additional fixture provisioning required. The *not*-available
branch does not skip (design principle 4 / this repository's "skip is
fail" rule) -- it runs `_assert_cross_entity_absent_or_denied`, which
accepts either of the two honest evidence forms `absence.py`'s shared
`assert_control_operation_absent_or_uniformly_refused` already establishes
for every other capability-absence claim on this port (surface-absent for
an in-process peer with no cross-entity entry point at all; a real,
present `CAPABILITY_UNSUPPORTED` denial for a peer whose wire dispatcher
genuinely receives the request but refuses it uniformly).

With the four currently-registered adapters: both `MitateDB-api` adapters
declare `cross_entity_mutation: partial` (phase 3.5 WP-2 flip) and take the
available branch for real; `r2db-api` (in-process) and `r2db-api-http`
both stay `unavailable` (P35-D1 -- no real client demand on this peer) and
take the absence branch -- in two DIFFERENT honest forms, pinned explicitly
by V5 below (`r2db-api` = surface-absent, `r2db-api-http` =
present-denial), the same two-form split C-14/C-15/C-17/C-06's own
`drop_entity` row already establish elsewhere on this port.
"""
from __future__ import annotations

import warnings

import pytest

from absence import assert_control_operation_absent_or_uniformly_refused
from conftest import registered_adapters
from adapter import (
    UNCLASSIFIED,
    VALID_CONFIRMATION,
    ConformanceDenial,
    Fixture,
    ScopedBatchOperation,
    fresh_identifier,
    load_contract,
    load_contract_error_codes,
)

pytestmark = pytest.mark.condition("C-16")


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


def _cross_entity_status(adapter) -> str:
    return adapter.capability_document().get("capabilities", {}).get("cross_entity_mutation", {}).get(
        "status", "unavailable"
    )


def _cross_entity_available(adapter) -> bool:
    return _cross_entity_status(adapter) in ("enabled", "partial")


def _assert_cross_entity_absent_or_denied(adapter, fx: Fixture) -> str:
    """The falsifiable fact for a peer that does not declare
    `cross_entity_mutation` `enabled`/`partial`: `attempt_cross_entity_
    batch` must be either structurally absent or, if a real entry point
    exists, refused before execution -- never fabricated by this test,
    delegated entirely to `absence.py`'s shared, independently-verifying
    mechanism (the same one C-14/C-17/C-06's own absence branches use)."""
    entity = fresh_identifier("c16_absent")
    adapter.create_entity(fx.developer_a, entity, {"label": "text"})

    def _attempt() -> None:
        adapter.attempt_cross_entity_batch(
            fx.runtime_a, [ScopedBatchOperation(operation="insert", entity=entity, values={"label": "x"})],
        )

    # m-4 (phase 3.5 WP-3 review): pin the required_forbidden_vocabulary
    # (C-14 precedent, absence.py) so a SurfaceAbsent claim's own declared
    # forbidden_parameters is actually verified to cover the cross-entity
    # vocabulary this claim is about, not merely a non-empty violation set
    # of unspecified content.
    return assert_control_operation_absent_or_uniformly_refused(
        adapter, _attempt, required_forbidden_vocabulary=("entities",),
    )


# ---------------------------------------------------------------------------
# V1: positive -- 2 entities, insert into each, single unit -> both commit
# ---------------------------------------------------------------------------


def test_c16_v1_two_entity_insert_commits_as_one_unit(adapter, fx: Fixture):
    if not _cross_entity_available(adapter):
        _assert_cross_entity_absent_or_denied(adapter, fx)
        return

    entity_a, entity_b = fx.shared_entity, fx.a_only_entity
    marker_a = fresh_identifier("c16v1a")
    marker_b = fresh_identifier("c16v1b")

    affected = adapter.attempt_cross_entity_batch(fx.runtime_a, [
        ScopedBatchOperation(operation="insert", entity=entity_a, values={"label": marker_a}),
        ScopedBatchOperation(operation="insert", entity=entity_b, values={"label": marker_b}),
    ])
    assert affected == 2, (
        f"{adapter.name}: a single cross-entity unit inserting into 2 entities reported affected {affected!r}, "
        "expected 2"
    )
    assert adapter.select_eq(fx.runtime_a, entity_a, ["label"], "label", marker_a), (
        f"{adapter.name}: cross-entity insert into {entity_a!r} did not commit"
    )
    assert adapter.select_eq(fx.runtime_a, entity_b, ["label"], "label", marker_b), (
        f"{adapter.name}: cross-entity insert into {entity_b!r} did not commit"
    )


# ---------------------------------------------------------------------------
# V2: atomicity -- valid op on entity A + invalid op on entity B -> denial,
# BOTH entities unchanged
# ---------------------------------------------------------------------------


def test_c16_v2_invalid_operation_on_one_entity_voids_the_whole_unit(adapter, fx: Fixture):
    if not _cross_entity_available(adapter):
        _assert_cross_entity_absent_or_denied(adapter, fx)
        return

    entity_a, entity_b = fx.shared_entity, fx.a_only_entity
    marker_a = fresh_identifier("c16v2a")
    count_a_before = adapter.count(fx.runtime_a, entity_a)
    count_b_before = adapter.count(fx.runtime_a, entity_b)

    with pytest.raises(ConformanceDenial) as ei:
        adapter.attempt_cross_entity_batch(fx.runtime_a, [
            ScopedBatchOperation(operation="insert", entity=entity_a, values={"label": marker_a}),
            # An unknown field name on entity_b: a genuine shape/validation
            # defect, refused before any execution -- never a capability
            # gap (this is not about an unsupported operation member).
            ScopedBatchOperation(
                operation="insert", entity=entity_b,
                values={fresh_identifier("c16v2_nosuchfield"): "x"},
            ),
        ])
    _assert_is_contract_code(ei.value.code)
    assert ei.value.code == "VALIDATION_FAILED", (
        f"{adapter.name}: a cross-entity unit with a valid op on one entity and an unknown-field op on "
        f"another was refused with {ei.value.code!r}, expected VALIDATION_FAILED"
        f"{_unclassified_hint(ei.value.code)}"
    )
    assert adapter.count(fx.runtime_a, entity_a) == count_a_before, (
        f"{adapter.name}: {entity_a!r} row count changed despite the whole cross-entity unit being denied"
    )
    assert adapter.count(fx.runtime_a, entity_b) == count_b_before, (
        f"{adapter.name}: {entity_b!r} row count changed despite the whole cross-entity unit being denied"
    )


# ---------------------------------------------------------------------------
# V3: batch_entities -- finite discoverable bound (unconditional), and the
# L+1 distinct-entity boundary vector (conditional on constructibility,
# design m-3 -- no hardcoded numeric literal, read from the declaration)
# ---------------------------------------------------------------------------


def _contract_scoped_mutation_operations_ceiling() -> int:
    """The contract's own hard ceiling on operations[] length for one
    cross-entity request (m-3, phase 3.5 WP-3 review): read live from
    `spec/data-service-api.v1.json` `schemas.ScopedMutationRequest.
    properties.operations.maxItems`, never hardcoded here -- `adapter.py`'s
    own module docstring forbids maintaining a hardcoded copy of
    contract-derived data."""
    contract = load_contract()
    return contract["schemas"]["ScopedMutationRequest"]["properties"]["operations"]["maxItems"]


def _v3_constructibility(adapter) -> tuple[bool, int, str]:
    """Returns `(constructible, declared_batch_entities, reason)`.
    `constructible` mirrors design m-3's own guard: an `L+1` distinct-entity
    vector can only be constructed within the contract's own
    `ScopedMutationRequest.operations` ceiling (`maxItems`, read live --
    see `_contract_scoped_mutation_operations_ceiling` above) and,
    defensively, within this suite's own declared `batch_items` bound too
    -- whichever is smaller. `reason` is always a non-empty, human-readable
    explanation when `constructible` is `False`, never discarded by this
    function's own callers (m-2, phase 3.5 WP-3 review)."""
    document = adapter.capability_document()
    limits = document.get("limits", {})
    declared_batch_entities = limits.get("batch_entities")
    if not isinstance(declared_batch_entities, int) or declared_batch_entities <= 0:
        return False, declared_batch_entities, f"batch_entities is not a positive int (got {declared_batch_entities!r})"
    declared_batch_items = limits.get("batch_items")
    ceiling = _contract_scoped_mutation_operations_ceiling()
    if isinstance(declared_batch_items, int) and declared_batch_items > 0:
        ceiling = min(ceiling, declared_batch_items)
    if declared_batch_entities >= ceiling:
        return (
            False, declared_batch_entities,
            f"declared batch_entities ({declared_batch_entities!r}) is not < "
            f"min(ScopedMutationRequest.operations.maxItems, batch_items) ({ceiling!r})",
        )
    return True, declared_batch_entities, ""


def test_c16_v3_batch_entities_bound_is_discoverable_and_enforced(adapter, fx: Fixture):
    if not _cross_entity_available(adapter):
        _assert_cross_entity_absent_or_denied(adapter, fx)
        return

    # Unconditional half: batch_entities is finite, discoverable, positive,
    # and declared enforced -- checked for every available adapter,
    # regardless of whether the boundary vector below is constructible.
    document = adapter.capability_document()
    limits = document.get("limits", {})
    enforcement = document.get("limit_enforcement", {})
    assert "batch_entities" in limits, f"{adapter.name}: capability_document()['limits'] is missing batch_entities"
    declared_batch_entities = limits["batch_entities"]
    assert isinstance(declared_batch_entities, int) and declared_batch_entities > 0, (
        f"{adapter.name}: limits.batch_entities is not a positive int: {declared_batch_entities!r}"
    )
    assert enforcement.get("batch_entities") == "enforced", (
        f"{adapter.name}: limit_enforcement.batch_entities is {enforcement.get('batch_entities')!r}, "
        "expected 'enforced' (SI-08)"
    )

    # Conditional half (design m-3): only constructed when the declared
    # bound leaves room for an L+1-entity vector within the contract's own
    # ScopedMutationRequest.operations ceiling / batch_items.
    constructible, declared, reason = _v3_constructibility(adapter)
    if not constructible:
        # Not a skip: a real, disclosed, computed fact about this adapter's
        # own declaration, not hidden uncertainty (m-2, phase 3.5 WP-3
        # review: `reason` is surfaced, not silently discarded -- a
        # UserWarning here so it is visible in this adapter's own test run
        # even though the assertion-message channel below is unreachable
        # on a passing/skipped-body test). Registry-wide vacuity is
        # guarded separately below
        # (test_at_least_one_available_adapter_can_construct_the_v3_boundary_vector),
        # which also carries this same reason into ITS OWN failure message.
        warnings.warn(
            f"{adapter.name}: V3's L+1-entity boundary vector is not constructible for this adapter: {reason}",
            stacklevel=1,
        )
        return

    # Acceptance half (M-4, phase 3.5 WP-3 review): submitting EXACTLY the
    # declared bound's own distinct-entity count must NOT be refused
    # specifically for batch_entities -- the same "refused before the
    # declared bound cannot be attributed to this class" discipline
    # `test_c14_authority_boundary.py`'s own vector 5 already establishes
    # for its own resource classes. These entities are fresh and
    # nonexistent, so some OTHER real denial (e.g. NOT_FOUND, once pass 1
    # reaches per-entity validation) is expected and accepted here --
    # only a LIMIT_EXCEEDED genuinely attributed to batch_entities at this
    # exact count would mean the bound is enforced one entity too early.
    at_bound_entities = [fresh_identifier(f"c16v3at_{i}") for i in range(declared)]
    at_bound_operations = [
        ScopedBatchOperation(operation="insert", entity=entity, values={"label": "x"})
        for entity in at_bound_entities
    ]
    try:
        adapter.attempt_cross_entity_batch(fx.runtime_a, at_bound_operations)
    except ConformanceDenial as exc:
        _assert_is_contract_code(exc.code)
        assert not (exc.code == "LIMIT_EXCEEDED" and exc.details.get("limit_class") == "batch_entities"), (
            f"{adapter.name}: a cross-entity unit naming exactly the declared batch_entities bound "
            f"({declared!r}) distinct entities was refused with LIMIT_EXCEEDED/batch_entities -- the bound "
            "is enforced one entity earlier than declared (refused before the declared bound: cannot "
            "attribute this refusal to batch_entities actually sitting at declared+1)"
        )

    entities = [fresh_identifier(f"c16v3_{i}") for i in range(declared + 1)]
    operations = [
        ScopedBatchOperation(operation="insert", entity=entity, values={"label": "x"})
        for entity in entities
    ]
    with pytest.raises(ConformanceDenial) as ei:
        adapter.attempt_cross_entity_batch(fx.runtime_a, operations)
    _assert_is_contract_code(ei.value.code)
    assert ei.value.code == "LIMIT_EXCEEDED", (
        f"{adapter.name}: a cross-entity unit naming {declared + 1!r} distinct entities (declared bound "
        f"{declared!r}) was refused with {ei.value.code!r}, expected LIMIT_EXCEEDED"
        f"{_unclassified_hint(ei.value.code)}"
    )
    limit_class = ei.value.details.get("limit_class")
    if limit_class is not None:
        assert limit_class == "batch_entities", (
            f"{adapter.name}: LIMIT_EXCEEDED for an over-bound distinct-entity count carried "
            f"limit_class={limit_class!r}, expected 'batch_entities'"
        )


def test_at_least_one_available_adapter_can_construct_the_v3_boundary_vector():
    # Vacuity guard (mirrors test_c12_capability_agreement.py's own
    # registry-wide guards): if every registered adapter that declares
    # cross_entity_mutation available also declared a batch_entities bound
    # at or past the contract's ScopedMutationRequest.operations ceiling
    # (or batch_items), V3's own L+1-entity vector would never actually
    # run its LIMIT_EXCEEDED branch anywhere in the registry.
    saw_constructible = False
    # m-2 (phase 3.5 WP-3 review): every available-but-not-constructible
    # adapter's own computed reason is carried here, not discarded --
    # surfaced in this guard's own failure message below if it ever fires,
    # so a future non-constructible adapter's own diagnosis is immediately
    # visible rather than requiring a second, separate investigation.
    unconstructible_reasons: list[str] = []
    for name, adapter_obj in registered_adapters().items():
        if not _cross_entity_available(adapter_obj):
            continue
        constructible, declared, reason = _v3_constructibility(adapter_obj)
        if constructible:
            saw_constructible = True
            break
        unconstructible_reasons.append(f"{name} (declared batch_entities={declared!r}): {reason}")
    assert saw_constructible, (
        "no registered adapter declaring cross_entity_mutation available has a constructible "
        "batch_entities boundary vector; V3's L+1-entity vector is vacuous across the whole registry. "
        f"Per-adapter reasons: {unconstructible_reasons!r}"
    )


# ---------------------------------------------------------------------------
# V4: destructive delete inside the unit -- declare-and-echo, and a
# wrong-entity phrase refused with nothing executed
# ---------------------------------------------------------------------------


def test_c16_v4_destructive_delete_inside_the_unit(adapter, fx: Fixture):
    if not _cross_entity_available(adapter):
        _assert_cross_entity_absent_or_denied(adapter, fx)
        return

    entity_a, entity_b = fx.shared_entity, fx.a_only_entity
    insert_marker = fresh_identifier("c16v4")
    # `fx.a_only_entity` already carries a seeded row (build_fixture's own
    # "a-only" seed, label field), used here as the delete target so this
    # vector needs no extra provisioning beyond the standard fixture.
    delete_label = "a-only"

    def _unit(delete_entity: str, confirmation) -> list[ScopedBatchOperation]:
        return [
            ScopedBatchOperation(operation="insert", entity=entity_a, values={"label": insert_marker}),
            ScopedBatchOperation(
                operation="delete", entity=delete_entity, where_field="label", where_value=delete_label,
                destructive=True, confirmation=confirmation,
            ),
        ]

    def _assert_untouched() -> None:
        assert not adapter.select_eq(fx.runtime_a, entity_a, ["label"], "label", insert_marker), (
            f"{adapter.name}: {entity_a!r}'s insert leg executed despite the unit's own delete leg being denied"
        )
        assert adapter.select_eq(fx.runtime_a, entity_b, ["label"], "label", delete_label), (
            f"{adapter.name}: {entity_b!r}'s seeded row disappeared despite the unit's own delete leg being denied"
        )

    # probe: unconfirmed delete on entity_b, inside a real cross-entity unit
    # alongside a non-destructive insert on entity_a -- must deny, neither
    # leg executes.
    with pytest.raises(ConformanceDenial) as ei_probe:
        adapter.attempt_cross_entity_batch(fx.runtime_a, _unit(entity_b, None))
    _assert_is_contract_code(ei_probe.value.code)
    assert ei_probe.value.code == "DESTRUCTIVE_CONFIRMATION_REQUIRED", (
        f"{adapter.name}: an unconfirmed destructive delete inside a cross-entity unit was refused with "
        f"{ei_probe.value.code!r}, expected DESTRUCTIVE_CONFIRMATION_REQUIRED"
    )
    phrase_b = ei_probe.value.details.get("required_confirmation")
    assert isinstance(phrase_b, str) and phrase_b, (
        f"{adapter.name}: DESTRUCTIVE_CONFIRMATION_REQUIRED denial carried no non-empty required_confirmation"
    )
    _assert_untouched()

    # a DIFFERENT entity's own correct delete phrase, presented for
    # entity_b's delete: phrase_construction's own scope-included rule
    # (the target entity is part of the derivation) requires this to be a
    # DIFFERENT phrase and to still be refused. M-2 (phase 3.5 WP-3
    # review): probes entity_a with the EXACT SAME predicate
    # (where_field="label", where_value=delete_label) phrase_b's own probe
    # used for entity_b -- the entity is therefore the ONLY input that
    # varies between the two probes, so `phrase_a != phrase_b` genuinely
    # isolates entity participation in the derivation (a prior revision
    # varied both the entity AND the where_value together, "seed-a" vs.
    # delete_label, which could not distinguish "the entity is part of the
    # derivation" from "the selection is").
    with pytest.raises(ConformanceDenial) as ei_a_probe:
        adapter.attempt_cross_entity_batch(fx.runtime_a, [
            ScopedBatchOperation(
                operation="delete", entity=entity_a, where_field="label", where_value=delete_label,
                destructive=True, confirmation=None,
            ),
        ])
    phrase_a = ei_a_probe.value.details.get("required_confirmation")
    assert isinstance(phrase_a, str) and phrase_a, (
        f"{adapter.name}: probing entity_a's own delete carried no non-empty required_confirmation"
    )
    assert phrase_a != phrase_b, (
        f"{adapter.name}: entity_a's and entity_b's delete phrases collided ({phrase_a!r}) despite an "
        "IDENTICAL where-predicate on both probes -- phrase_construction's own scope-included rule requires "
        "the target entity itself to be part of the derivation"
    )

    with pytest.raises(ConformanceDenial) as ei_wrong:
        adapter.attempt_cross_entity_batch(fx.runtime_a, _unit(entity_b, phrase_a))
    assert ei_wrong.value.code == "DESTRUCTIVE_CONFIRMATION_REQUIRED", (
        f"{adapter.name}: entity_a's own correct phrase, presented for entity_b's delete inside the same "
        f"cross-entity unit, was refused with {ei_wrong.value.code!r}, expected "
        "DESTRUCTIVE_CONFIRMATION_REQUIRED"
    )
    _assert_untouched()

    # echo: the real, currently-valid phrase for entity_b's own delete
    # executes -- both legs of the unit commit together.
    affected = adapter.attempt_cross_entity_batch(fx.runtime_a, _unit(entity_b, VALID_CONFIRMATION))
    assert affected == 2, (
        f"{adapter.name}: echoing entity_b's own correct phrase inside the cross-entity unit reported "
        f"affected {affected!r}, expected 2 (one insert, one delete)"
    )
    assert adapter.select_eq(fx.runtime_a, entity_a, ["label"], "label", insert_marker), (
        f"{adapter.name}: {entity_a!r}'s insert leg did not commit alongside the confirmed delete"
    )
    assert not adapter.select_eq(fx.runtime_a, entity_b, ["label"], "label", delete_label), (
        f"{adapter.name}: {entity_b!r}'s confirmed delete leg did not commit"
    )


# ---------------------------------------------------------------------------
# V5: unavailable peers -- evidence-form pinning (design section 3, M-5)
# ---------------------------------------------------------------------------

# With the four currently-registered adapters (design v1.2 section 3's own
# closing sentence): r2db-api (in-process) has no cross-entity entry point
# on DataService at all (surface-absent); r2db-api-http's real
# `POST /v1/data/mutations` mount authenticates then refuses uniformly with
# CAPABILITY_UNSUPPORTED (present-denial). Both MitateDB-api adapters are
# available as of phase 3.5 WP-2 and are exercised by V1-V4 instead, not
# here.
_EXPECTED_ABSENCE_FORM: dict[str, str] = {
    "r2db-api": "surface_absent",
    "r2db-api-http": "declared_unavailable",
}


def test_c16_v5_unavailable_peers_take_their_declared_evidence_form():
    saw_unavailable = False
    for name, adapter_obj in registered_adapters().items():
        if _cross_entity_available(adapter_obj):
            continue
        saw_unavailable = True
        fx = adapter_obj.build_fixture()
        form = _assert_cross_entity_absent_or_denied(adapter_obj, fx)
        expected = _EXPECTED_ABSENCE_FORM.get(name)
        assert expected is not None, (
            f"{name}: cross_entity_mutation is unavailable on this newly-registered adapter, but no expected "
            "evidence form is pinned in _EXPECTED_ABSENCE_FORM -- add one (design section 3's own two-form "
            "split) rather than leaving this vector's own regression-pin coverage silently incomplete"
        )
        assert form == expected, (
            f"{name}: expected the {expected!r} absence-evidence form for an unavailable "
            f"cross_entity_mutation declaration, got {form!r}"
        )
    assert saw_unavailable, (
        "no registered adapter currently declares cross_entity_mutation unavailable; "
        "test_c16_v5_unavailable_peers_take_their_declared_evidence_form is vacuous across the whole registry"
    )
