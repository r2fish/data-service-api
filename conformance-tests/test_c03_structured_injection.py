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
    assert_no_payload_echo_in_details,
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
                # port v1.6 review M-3: same second channel as the
                # value-position check below.
                assert_no_payload_echo_in_details(denial.details, payload, context=f"{position_name}:{payload!r}")
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
                # port v1.6 review M-3: `details` is a second, independent
                # channel a denial can reflect a payload through (design
                # docs/design/DESTRUCTIVE_CONFIRMATION_V1.md R-6 item 2 /
                # C-06 vector V8's own check) -- checked alongside the
                # native-message check above, not instead of it.
                assert_no_payload_echo_in_details(denial.details, payload, context=f"{position_name}:{payload!r}")
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


# --- 6. contains/matches value corpus (Q-2 literal/wildcard semantics) ------
#
# design docs/design/R2DB_CCR13_STORAGE_V1.md §0.5 Q-2 adjudication
# (contract 1.1.0 `structured_operations.query_operators`): `contains` is
# literal substring containment -- no character of its value is ever
# interpreted as a wildcard/pattern token -- while `matches` is a real
# wildcard grammar (`%`/`_` as meta-characters, `\` as an escape). Neither
# `test_value_positions_round_trip_or_deny` above nor
# `test_c12_capability_agreement.py`'s reverse condition exercise this: both
# only ever use `eq`. These probes place values containing the wildcard
# meta-characters themselves at the `contains`/`matches` *value* position
# specifically, so a peer that silently gave `contains` wildcard semantics
# (a live regression risk this same design's own §0.5 Q-2 exists to
# foreclose) would be caught by a pattern falsely matching a row it should
# not.

CONTAINS_MATCHES_VALUE_PAYLOADS: list[str] = ["50%off", "a_b_c", "back\\slash", "%_\\mixed"]


def _declared_query_operators_c03(capability_document: dict) -> set[str]:
    entry = capability_document.get("capabilities", {}).get("structured_query", {})
    if entry.get("status") in ("enabled", "partial"):
        return set(entry.get("operators", []))
    return set()


def test_contains_value_position_is_literal_never_wildcard_interpreted(adapter, fx: Fixture):
    declared = _declared_query_operators_c03(adapter.capability_document())
    entity = fresh_identifier("c03_containslit")
    field_name = "label"
    adapter.create_entity(fx.developer_a, entity, {field_name: "text"})

    if "contains" not in declared:
        # Undeclared vocabulary member: C-12's reverse condition already
        # covers the capability-agreement half of this; here it is enough
        # to confirm the same real query entry point still denies it
        # honestly rather than silently executing wildcard-interpreted.
        with pytest.raises(ConformanceDenial) as ei:
            adapter.attempt_filter(fx.runtime_a, entity, [field_name], field_name, "contains", "50%off")
        _assert_is_contract_code(ei.value.code)
        assert ei.value.code == "CAPABILITY_UNSUPPORTED", (
            f"{adapter.name}: contains is undeclared; attempt_filter() must deny with "
            f"CAPABILITY_UNSUPPORTED, got {ei.value.code!r}{_unclassified_hint(ei.value.code)}"
        )
        return

    for payload in CONTAINS_MATCHES_VALUE_PAYLOADS:
        adapter.insert(fx.runtime_a, entity, {field_name: payload})
        # positive: the payload, used verbatim as its own contains pattern,
        # matches the row it came from -- a plain substring search always
        # matches itself, wildcard-interpreted or not, so this alone does
        # not yet distinguish the two; the negative check right below does.
        rows = adapter.attempt_filter(fx.runtime_a, entity, [field_name], field_name, "contains", payload)
        assert any(r.get(field_name) == payload for r in rows), (
            f"{adapter.name}: contains({payload!r}) did not match the row holding that exact value"
        )

    # negative: a `%`-containing pattern must not ALSO match a row that
    # merely fits the wildcard-interpreted shape (`50%off` interpreted as
    # SQL LIKE would match `50XXXoff`, `50off`, etc.) -- if it did, this
    # peer would be giving `contains` the exact wildcard semantics Q-2
    # explicitly forecloses.
    adapter.insert(fx.runtime_a, entity, {field_name: "50XXXoff"})
    adapter.insert(fx.runtime_a, entity, {field_name: "50off"})
    rows = adapter.attempt_filter(fx.runtime_a, entity, [field_name], field_name, "contains", "50%off")
    matched_values = {r.get(field_name) for r in rows}
    assert matched_values == {"50%off"}, (
        f"{adapter.name}: contains('50%off') matched {matched_values!r} -- expected only the row containing "
        "the literal substring '50%off', not rows a wildcard-interpreted % would additionally match"
    )


def test_matches_value_position_applies_real_wildcard_grammar_and_rejects_bad_patterns(adapter, fx: Fixture):
    declared = _declared_query_operators_c03(adapter.capability_document())
    entity = fresh_identifier("c03_matcheswild")
    field_name = "label"
    adapter.create_entity(fx.developer_a, entity, {field_name: "text"})

    if "matches" not in declared:
        with pytest.raises(ConformanceDenial) as ei:
            adapter.attempt_filter(fx.runtime_a, entity, [field_name], field_name, "matches", "50\\%off%")
        _assert_is_contract_code(ei.value.code)
        assert ei.value.code == "CAPABILITY_UNSUPPORTED", (
            f"{adapter.name}: matches is undeclared; attempt_filter() must deny with "
            f"CAPABILITY_UNSUPPORTED, got {ei.value.code!r}{_unclassified_hint(ei.value.code)}"
        )
        return

    adapter.insert(fx.runtime_a, entity, {field_name: "50%off everything"})
    adapter.insert(fx.runtime_a, entity, {field_name: "hello"})
    # `%` as a real wildcard (any sequence, including empty) and `\%` as an
    # escaped literal percent, in the same pattern.
    rows = adapter.attempt_filter(fx.runtime_a, entity, [field_name], field_name, "matches", "50\\%off%")
    matched_values = {r.get(field_name) for r in rows}
    assert matched_values == {"50%off everything"}, (
        f"{adapter.name}: matches('50\\\\%off%') matched {matched_values!r}, expected only '50%off everything'"
    )
    # `_` as a real wildcard (exactly one character).
    rows_underscore = adapter.attempt_filter(fx.runtime_a, entity, [field_name], field_name, "matches", "hel_o")
    assert {r.get(field_name) for r in rows_underscore} == {"hello"}, (
        f"{adapter.name}: matches('hel_o') did not match 'hello' via the `_` wildcard"
    )
    # A pattern ending in an unescaped backslash has no next character to
    # escape and is malformed grammar (contract `query_operators.matches`),
    # refused deterministically rather than depending on stored data.
    count_before = adapter.count(fx.runtime_a, entity)
    with pytest.raises(ConformanceDenial) as ei:
        adapter.attempt_filter(fx.runtime_a, entity, [field_name], field_name, "matches", "trailing\\")
    _assert_is_contract_code(ei.value.code)
    assert ei.value.code == "VALIDATION_FAILED", (
        f"{adapter.name}: matches pattern with a trailing unescaped backslash: {ei.value.code!r}, "
        "expected VALIDATION_FAILED"
    )
    assert adapter.count(fx.runtime_a, entity) == count_before, (
        f"{adapter.name}: state changed despite a rejected malformed matches pattern"
    )
