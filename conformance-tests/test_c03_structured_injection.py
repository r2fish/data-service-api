"""C-03 -- structured injection (SI-04, SI-05).

design: docs/design/CONFORMANCE_ADAPTER_V1.md section 5.2. Every test here
carries @pytest.mark.condition("C-03") via the module-level `pytestmark`.
"""
from __future__ import annotations

from typing import Any

import pytest

from adapter import (
    UNCLASSIFIED,
    VALID_CONFIRMATION,
    ConformanceDenial,
    Fixture,
    MUST_COVER_IDENTIFIER_POSITIONS,
    MUST_COVER_VALUE_POSITIONS,
    NATIVE_SURFACE_FORBIDDEN_NAME_FRAGMENTS,
    PayloadNotExpressible,
    assert_no_payload_echo,
    fresh_identifier,
    load_contract_error_codes,
    native_cause_of,
    signature_forbids_parameters,
)
from payloads import IDENTIFIER_PAYLOADS, NON_STRING_IDENTIFIERS, VALUE_PAYLOADS

pytestmark = pytest.mark.condition("C-03")

# design section 5.2 item 3
IDENTIFIER_DENIAL_CODES = {"IDENTIFIER_INVALID", "VALIDATION_FAILED", "NOT_FOUND"}

ALL_IDENTIFIER_PAYLOADS: list[Any] = [*IDENTIFIER_PAYLOADS, *NON_STRING_IDENTIFIERS]


def _unclassified_hint(code: str) -> str:
    """Extra message text pointing out an UNCLASSIFIED denial code (design
    section 10.2), so a code-membership failure caused by an unmapped
    native exception does not read like a generic code mismatch."""
    if code != UNCLASSIFIED:
        return ""
    return (
        " -- code is adapter.UNCLASSIFIED: the peer raised a native "
        "exception the adapter could not map to a contract code. This is a "
        "finding under SI-05/SI-10, not a denial."
    )


def _assert_is_contract_code(code: str) -> None:
    contract_codes = load_contract_error_codes()
    assert code in contract_codes, (
        f"denial code {code!r} is not a contract error code{_unclassified_hint(code)}"
    )


# --- 1. positive control ----------------------------------------------------


def test_positive_control_full_crud_cycle_succeeds(adapter, fx: Fixture):
    entity = fresh_identifier("c03_positive")
    field_name = "label"
    adapter.create_entity(fx.developer_a, entity, {field_name: "text"})
    adapter.insert(fx.runtime_a, entity, {field_name: "hello"})
    rows = adapter.select_eq(fx.runtime_a, entity, [field_name], field_name, "hello")
    assert any(r.get(field_name) == "hello" for r in rows)
    # Peers legitimately differ on whether a plain filtered delete needs
    # destructive/confirmation at all (the contract's Mutation.destructive /
    # .confirmation apply to any mutation, and SI-09 leaves "appropriate
    # authority/semantics" to the implementation). destructive=True with an
    # explicit confirmation is the superset request every conformant peer
    # must accept for an otherwise-legitimate single-row delete, so the
    # positive control uses that rather than assuming one peer's more
    # permissive convention. This is a legitimate destructive delete, so it
    # uses the VALID_CONFIRMATION sentinel (design section 10.1) rather than
    # a made-up token: the adapter substitutes whatever confirmation spelling
    # that peer actually requires.
    affected = adapter.delete(
        fx.runtime_a, entity, field_name, "hello", destructive=True, confirmation=VALID_CONFIRMATION
    )
    assert affected >= 1


# --- 2. no native command surface -------------------------------------------


def test_no_native_command_surface_is_exposed(adapter, fx: Fixture):
    assert adapter.native_command_surface() is None

    callables = adapter.public_operation_callables()
    assert callables, "public_operation_callables() returned nothing to inspect"
    violations = signature_forbids_parameters(callables, NATIVE_SURFACE_FORBIDDEN_NAME_FRAGMENTS)
    assert not violations, f"native-command-suggestive parameter(s) found on public surface: {violations}"


# --- 3. identifier positions reject every payload (+ item 6 non-echo) ------


def test_identifier_positions_reject_every_payload(adapter, fx: Fixture):
    positions = adapter.identifier_positions(fx)
    covered = set(positions)
    missing = MUST_COVER_IDENTIFIER_POSITIONS - covered
    assert not missing, f"identifier_positions() is missing required position(s): {missing}"

    failures: list[str] = []
    skipped: list[str] = []
    # design section 10.3: some (position, payload) pairs cannot even be
    # constructed at the harness level (e.g. an unhashable payload placed
    # in a mapping-key position). Those raise PayloadNotExpressible, which
    # this test treats as "not observed here" -- neither a pass nor a
    # failure for that pair. But per design principle 4 (an exemption must
    # not become silent permission), every payload in the corpus must still
    # be shown to have been actually denied in at least one position;
    # tracked here by corpus index rather than by payload value, since some
    # payloads (e.g. [], {}) are themselves unhashable.
    denied_anywhere = [False] * len(ALL_IDENTIFIER_PAYLOADS)

    for position_name, probe in positions.items():
        for index, payload in enumerate(ALL_IDENTIFIER_PAYLOADS):
            try:
                probe(payload)
            except PayloadNotExpressible as exc:
                skipped.append(
                    f"{position_name}: payload {payload!r} skipped -- not expressible at this "
                    f"position ({exc.reason})"
                )
                continue
            except ConformanceDenial as denial:
                _assert_is_contract_code(denial.code)
                denied_anywhere[index] = True
                if denial.code not in IDENTIFIER_DENIAL_CODES:
                    failures.append(
                        f"{position_name}: payload {payload!r} denied with unexpected code "
                        f"{denial.code!r}{_unclassified_hint(denial.code)}"
                    )
                # design section 5.2 item 6: native message must not echo the payload
                assert_no_payload_echo(
                    native_cause_of(denial), payload, context=f"{position_name}:{payload!r}"
                )
            else:
                failures.append(f"{position_name}: payload {payload!r} was NOT denied")

    never_tested = [
        repr(ALL_IDENTIFIER_PAYLOADS[i]) for i, denied in enumerate(denied_anywhere) if not denied
    ]
    if never_tested:
        failures.append(
            "the following payload(s) were PayloadNotExpressible in every covered position, so "
            "the corpus never actually observed a denial for them (design section 10.3, principle "
            "4 -- a per-position exemption must not become a whole-corpus blind spot): "
            + ", ".join(never_tested)
        )

    # PayloadNotExpressible pairs are, by themselves, neither a pass nor a
    # failure (design section 10.3) -- so `skipped` alone must never cause
    # this assertion to fail. It is surfaced only as context alongside a
    # real failure, to aid diagnosis of *why* a position/payload pair is
    # absent from the evidence above.
    if failures and skipped:
        failures.append("skipped (position, payload) pairs, for context:\n  " + "\n  ".join(skipped))

    assert not failures, "\n".join(failures)


# --- 4. value positions prove the binding boundary --------------------------


def test_value_positions_round_trip_or_deny(adapter, fx: Fixture):
    positions = adapter.value_positions(fx)
    covered = set(positions)
    missing = MUST_COVER_VALUE_POSITIONS - covered
    assert not missing, f"value_positions() is missing required position(s): {missing}"

    failures: list[str] = []
    for position_name, probe in positions.items():
        for payload in VALUE_PAYLOADS:
            try:
                result = probe(payload)
            except ConformanceDenial as denial:
                _assert_is_contract_code(denial.code)
                # design section 5.2 item 6: native message must not echo the payload
                assert_no_payload_echo(
                    native_cause_of(denial), payload, context=f"{position_name}:{payload!r}"
                )
                continue

            if position_name == "insert_value":
                if result != payload:
                    failures.append(
                        f"insert_value: payload {payload!r} did not round-trip byte-equal, got {result!r}"
                    )
            elif position_name == "filter_value":
                if not result:
                    failures.append(
                        f"filter_value: payload {payload!r} matched no rows (binding did not "
                        "reproduce the written value)"
                    )
            else:
                # any additional, adapter-declared value position beyond the
                # required set: apply the same round-trip-or-empty-is-suspect
                # heuristic conservatively by requiring a non-falsy result.
                if not result and result != 0:
                    failures.append(f"{position_name}: payload {payload!r} produced an empty/falsy result")
    assert not failures, "\n".join(failures)


# --- 5. structural integrity across the whole corpus ------------------------


def test_structural_integrity_across_corpus(adapter, fx: Fixture):
    # The identifier corpus (design section 6.2 IDENTIFIER_PAYLOADS /
    # NON_STRING_IDENTIFIERS) is, by construction, made entirely of payloads
    # that MUST be denied (test above). If even one reaches execution, it
    # would mutate structure it should never have touched, so entity set AND
    # shared_entity's row count must be byte-identical before/after running
    # it -- this is what design section 5.2 item 5 means by "if a single
    # injection payload reaches execution, this invariant breaks."
    #
    # The value corpus (VALUE_PAYLOADS) is different in kind: design section
    # 5.2 item 4 requires insert_value/filter_value to prove a *successful*,
    # safely-bound round trip wherever the payload isn't denied outright.
    # That means value-position probes are expected to legitimately write
    # rows into shared_entity as part of proving the binding boundary --
    # growing its row count is the correct, intended outcome, not a
    # structural-integrity violation. Applying the row-count invariance to
    # the value corpus as well would contradict item 4's own requirement, so
    # it is scoped to the identifier corpus only. The entity SET is still
    # checked across the full run: neither corpus is ever expected to create
    # or drop an entity.
    ents_before = adapter.entities(fx.runtime_a)
    count_before = adapter.count(fx.runtime_a, fx.shared_entity)

    identifier_positions = adapter.identifier_positions(fx)
    for probe in identifier_positions.values():
        for payload in ALL_IDENTIFIER_PAYLOADS:
            try:
                probe(payload)
            except ConformanceDenial:
                pass
            except PayloadNotExpressible:
                # design section 10.3: the request could not even be
                # constructed at this position, so nothing executed and
                # there is nothing for the structural-integrity check below
                # to observe from this (position, payload) pair.
                pass

    ents_after_identifiers = adapter.entities(fx.runtime_a)
    count_after_identifiers = adapter.count(fx.runtime_a, fx.shared_entity)
    assert ents_after_identifiers == ents_before, "entity set changed after running the identifier corpus"
    assert count_after_identifiers == count_before, (
        "shared_entity row count changed after running the identifier corpus: "
        "an injection payload reached execution"
    )

    value_positions = adapter.value_positions(fx)
    for probe in value_positions.values():
        for payload in VALUE_PAYLOADS:
            try:
                probe(payload)
            except ConformanceDenial:
                pass

    ents_after = adapter.entities(fx.runtime_a)
    assert ents_after == ents_before, "entity set changed after running the value corpus"
