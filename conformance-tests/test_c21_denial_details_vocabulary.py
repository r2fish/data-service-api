"""C-21 -- denials this contract requires structured diagnostics for carry
them (SI-05, SI-10).

design: docs/design/PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md
D-3, §6.2 "C-21 検証エラー語彙", registered in `conformance-tests/
CONDITIONS.md`. Every test here carries `@pytest.mark.condition("C-21")`
via the module-level `pytestmark`.

Unconditional 1.7.0 obligation (D-1(2)): this row does not branch on any
capability -- it branches on the plug's own declared `contract_version`
(never a string compare, `adapter.parse_semver`, C-19's own `_semver_
tuple` precedent):

  - `contract_version < (1, 7, 0)`: `xfail(strict=True)`, attached at
    runtime (`request.node.add_marker`, work order §0.4 item 4 -- the
    version gate is read at execution time, never a file edit) --
    **the test body below still runs for real**, exactly as C-07 (ii)'s
    declare-first branch does: this is what makes the marker a real
    verification rather than a blanket skip. If a peer wired R-3's
    structured-details vocabulary in BEFORE flipping its declared version,
    the assertions below would genuinely pass and `strict=True` turns that
    XPASS into a hard failure (D-1(7): "宣言が挙動より先に出ることを機構
    が禁じる"). `observed_branch = "pre_1_7_0"`.
  - `>= (1, 7, 0)`: the 3 codes this vocabulary binds --
    `VALIDATION_FAILED`, `IDENTIFIER_INVALID`, `CAPABILITY_UNSUPPORTED` --
    are each probed; for every one this plug actually answers with, the
    required keys/vocabulary/path-format/value-domain rules are asserted,
    and the SI-10 scan (`conftest.assert_details_vocabulary_values_safe`,
    restricted to the 4 vocabulary keys) is run over its `details`.
    `observed_branch = "vocabulary_enforced"`.

Per-plug non-vacuity (declaration-based, §6.2 supervisor ruling S-c):
`observed_branch` is cross-checked against the branch the plug's own
declared `contract_version` implies; additionally, in the `>= 1.7.0`
branch, at least one of the 3 codes must have actually been observed.
**MitateDB never emits `IDENTIFIER_INVALID` at all** (D-3(6), disclosed) --
its own non-vacuity is carried by `VALIDATION_FAILED`/`CAPABILITY_
UNSUPPORTED` alone.
"""
from __future__ import annotations

import re
from typing import Any, Mapping

import pytest

from adapter import ConformanceAdapter, ConformanceDenial, fresh_identifier, parse_semver
from conftest import assert_details_vocabulary_values_safe, provision_pair

pytestmark = pytest.mark.condition("C-21")

_VIOLATED_DECLARATION_VOCABULARY = frozenset({
    "request_schema", "identifier_syntax", "field_type", "enum", "nullable",
    "capability", "budget", "unsupported_field", "plan", "idempotency_key",
})

# design D-3 実装の指示 / conftest._DETAILS_VOCABULARY_KEYS: the 4 keys
# `errors.details_vocabulary` requires. WP-1b rework (review point G):
# used below to explicitly OBSERVE, in the pre-1.7.0 branch, that this
# plug's own CURRENT denial does not already carry all 4 -- replacing the
# structurally-dead `assert observed_codes` (review point G: lines 119/161
# add unconditionally, so it could never be empty) with a real,
# declaration-derived `observed_branch` cross-check (C-07 (ii)'s own
# `_expected_branch_for_status` form, supervisor ruling 2026-09-07).
_DETAILS_VOCABULARY_KEYS = ("field", "declared_type", "observed_type", "violated_declaration")


def _expected_branch_for_pre_1_7_0(pre_1_7_0: bool) -> str:
    return "pre_1_7_0" if pre_1_7_0 else "vocabulary_enforced"


def _assert_validation_failed_shape(details: Mapping[str, Any], *, adapter_name: str) -> None:
    violated = details.get("violated_declaration")
    assert violated in _VIOLATED_DECLARATION_VOCABULARY, (
        f"{adapter_name}: VALIDATION_FAILED details.violated_declaration {violated!r} is outside the "
        f"closed vocabulary {sorted(_VIOLATED_DECLARATION_VOCABULARY)!r} -- {details!r}"
    )
    if violated in ("field_type", "nullable"):
        assert details.get("declared_type") is not None and details.get("observed_type") is not None, (
            f"{adapter_name}: violated_declaration={violated!r} requires BOTH declared_type and "
            f"observed_type -- {details!r}"
        )
    elif violated == "enum":
        assert details.get("declared_type") is not None, (
            f"{adapter_name}: violated_declaration='enum' requires declared_type -- {details!r}"
        )
        assert "observed_type" not in details, (
            f"{adapter_name}: violated_declaration='enum' must NOT carry observed_type (it is not what "
            f"was violated; carrying it invites misreading as a type mismatch) -- {details!r}"
        )
    elif violated == "request_schema":
        assert details.get("field") is not None, (
            f"{adapter_name}: violated_declaration='request_schema' requires 'field' -- {details!r}"
        )
    field = details.get("field")
    if field is not None:
        assert isinstance(field, str) and not field.startswith("/"), (
            f"{adapter_name}: details.field {field!r} must be a '/'-separated request-body path with no "
            f"leading separator"
        )


# 監督裁定 N-4 (`{scratchpad}/rulings-r2-closure.md`): `details.field` is a
# request-internal path -- no leading "/" -- and, where the denial is
# attributable to one of the two shapes the ruling names, that path also
# matches the shape: a VALUE violation (a value written by, or filtered
# through, one mutation operation) reads `operations/<i>/values/<field>`;
# a schema-request DECLARATION violation (the `field_constraints`/`enum`/
# `nullable` declaration itself is invalid, `violated_declaration:
# constraint_declaration`, or a `field_constraints` sent without `fields`,
# `violated_declaration: request_schema`) reads `field_constraints/...`,
# or is one of the bare words `enum`/`nullable`/`field_constraints`/
# `operation`. `kind=None` asserts only the generic no-leading-"/" form
# (used for denials the ruling does not name a specific shape for, e.g.
# `IDENTIFIER_INVALID`).
_VALUE_FIELD_RE = re.compile(r"^operations/\d+/values/")
_SCHEMA_DECLARATION_FIELD_BARE_WORDS = frozenset({"enum", "nullable", "field_constraints", "operation"})


def _assert_details_field_path_shape(field: Any, *, kind: "str | None", adapter_name: str) -> None:
    if field is None:
        return
    assert isinstance(field, str) and not field.startswith("/"), (
        f"{adapter_name}: details.field {field!r} must be a request-internal path with no leading '/' "
        "(裁定 N-4)"
    )
    if kind == "value":
        assert _VALUE_FIELD_RE.match(field), (
            f"{adapter_name}: a value-violation details.field {field!r} must have the form "
            "'operations/<i>/values/<field>' (裁定 N-4)"
        )
    elif kind == "schema_declaration":
        assert field.startswith("field_constraints/") or field in _SCHEMA_DECLARATION_FIELD_BARE_WORDS, (
            f"{adapter_name}: a schema-request declaration-violation details.field {field!r} must be "
            "'field_constraints/...' or one of 'enum'/'nullable'/'field_constraints'/'operation' (裁定 N-4)"
        )


def test_c21_denial_details_vocabulary(adapter: ConformanceAdapter, isolated, request: pytest.FixtureRequest) -> None:
    iso = isolated
    contract_version = adapter.capability_document()["contract_version"]
    pre_1_7_0 = parse_semver(contract_version) < (1, 7, 0)
    if pre_1_7_0:
        request.node.add_marker(pytest.mark.xfail(
            reason=(
                f"{adapter.name} declares contract_version {contract_version!r} (< 1.7.0) -- the R-3 "
                "structured-details vocabulary is an unconditional 1.7.0 obligation (design D-1(2)/D-3); "
                "this branch is expected to fail (not merely skip) until this peer's own version-flip "
                "commit lands, per D-1(7)."
            ),
            strict=True,
        ))

    developer, runtime, _app_id = provision_pair(iso, app_prefix="c21")
    entity = fresh_identifier("c21")
    iso.create_entity(developer, entity, {"label": "text", "count": "integer"})

    if pre_1_7_0:
        # Work order §6 訂正註 7 (supervisor ruling, post-WP-1-audit,
        # 2026-09-07): a non-asserting RECORD only, not part of the
        # xfail(strict=True) node's pass/fail body. The audit's mutation
        # E3/E2 (peer's in-process adapter forced to carry request_id /
        # the full 4-key details even while still declaring < 1.7.0) found
        # that an `assert` here gives the xfail-marked node an
        # always-available way to fail for a reason OTHER than the real
        # R-3 vocabulary check below -- masking a genuinely early
        # implementation instead of exposing it as a strict XPASS. The
        # real, unconditional detection is the vocabulary body's own
        # assertions further down (`_assert_validation_failed_shape` etc.),
        # which only pass for real once R-3 is wired in.
        with pytest.raises(ConformanceDenial) as ei_pre:
            iso.attempt_mutation(
                runtime, entity, "insert", values={"count": "also-not-an-integer"}, where_field=None, where_value=None,
            )
        pre_details = ei_pre.value.details or {}
        _already_full_vocabulary = all(k in pre_details for k in _DETAILS_VOCABULARY_KEYS)  # recorded, never asserted

    observed_codes: set[str] = set()

    # VALIDATION_FAILED -- field_type violation (both declared_type and
    # observed_type required).
    with pytest.raises(ConformanceDenial) as ei_type:
        iso.attempt_mutation(
            runtime, entity, "insert", values={"count": "not-an-integer"}, where_field=None, where_value=None,
        )
    assert ei_type.value.code == "VALIDATION_FAILED", f"{adapter.name}: {ei_type.value.code!r}"
    _assert_validation_failed_shape(ei_type.value.details, adapter_name=adapter.name)
    assert ei_type.value.details.get("violated_declaration") == "field_type", ei_type.value.details
    assert_details_vocabulary_values_safe(ei_type.value.details, adapter_name=adapter.name)
    observed_codes.add("VALIDATION_FAILED")

    # VALIDATION_FAILED -- request_schema violation (unknown field name).
    # Contract 1.11.0 (subordinate ruling 16) unifies every registered
    # plug on VALIDATION_FAILED for this exact probe (C-07's own module
    # docstring records the pre-1.11.0 cross-peer difference this closed:
    # NOT_FOUND on both r2db plugs, VALIDATION_FAILED on both MitateDB
    # plugs); the `if` below is kept rather than tightened to an
    # unconditional assert, since C-31 -- not C-21 -- is this suite's own
    # dedicated pin for the code this position now answers with.
    bad_field = fresh_identifier("c21_nosuch")
    with pytest.raises(ConformanceDenial) as ei_schema:
        iso.attempt_mutation(runtime, entity, "insert", values={bad_field: "x"}, where_field=None, where_value=None)
    if ei_schema.value.code == "VALIDATION_FAILED":
        _assert_validation_failed_shape(ei_schema.value.details, adapter_name=adapter.name)
        assert ei_schema.value.details.get("violated_declaration") == "request_schema", ei_schema.value.details
        assert_details_vocabulary_values_safe(ei_schema.value.details, adapter_name=adapter.name)
        observed_codes.add("VALIDATION_FAILED")

    # IDENTIFIER_INVALID -- malformed entity identifier. Disclosed
    # non-uniformity (D-3(6)): MitateDB never emits this code at all; where
    # a peer answers something else here, only the code observed above/
    # below counts toward non-vacuity.
    try:
        iso.create_entity(developer, "not a valid identifier!", {"label": "text"})
    except ConformanceDenial as identifier_denial:
        if identifier_denial.code == "IDENTIFIER_INVALID":
            assert identifier_denial.details.get("violated_declaration") == "identifier_syntax", (
                identifier_denial.details
            )
            assert identifier_denial.details.get("field") is not None, identifier_denial.details
            assert_details_vocabulary_values_safe(identifier_denial.details, adapter_name=adapter.name)
            observed_codes.add("IDENTIFIER_INVALID")
    else:
        pytest.fail(f"{adapter.name}: create_entity accepted a malformed identifier 'not a valid identifier!'")

    # CAPABILITY_UNSUPPORTED -- declaration-based probe, 2nd rework
    # (supervisor ruling, 2026-09-08, superseding the S-c `budget=
    # {"batch_items": 10}` probe this replaces): main `f30fb85` flips BOTH
    # peers' `request_budget` to `enabled` (WP-2cd / WP-3cd), so the S-c
    # probe now also `DID NOT RAISE` -- the identical failure mode that
    # made S-c itself replace the `dry_run=True` probe before it. Rather
    # than chase a third request-level capability that might flip
    # `enabled` under it too, this probe uses the SAME "operation name
    # not declared for this request" shape `test_c12_capability_
    # agreement.py`/`test_c04_unsupported_and_safe_errors.py` already use
    # elsewhere in this suite, in the one form that is universal across
    # every currently-registered plug regardless of that plug's own
    # whole-capability `atomic_mutation` declaration: `upsert` presented
    # against `entity`, which (unlike the C-12 positive-control entity)
    # declares no uniqueness key at all. `test_c17_declaration_agreement.
    # py::test_upsert_on_entity_with_no_declared_unique_key_is_capability_
    # unsupported` already establishes this is refused CAPABILITY_
    # UNSUPPORTED unconditionally, on every peer, independent of whether
    # that peer's own capability document declares `upsert` supported at
    # the whole-capability level (r2db-api does; MitateDB-api does not) --
    # the entity-level uniqueness *declaration* upsert actually needs is
    # what is missing here, so this is a genuine "declared-in-the-contract-
    # vocabulary, undeclared-for-this-request" capability gap, presented to
    # each peer's real dispatcher, never fabricated by the adapter (design
    # principle 4).
    #
    # Measured `details` at the two real call sites (phase9-r2db WP-2e /
    # phase9-mitatedb worktrees, read-only): r2db-api's `structured.py::
    # _apply_upsert` (`fail("CAPABILITY_UNSUPPORTED", "Upsert requires a
    # declared domain uniqueness key.", details=violation("capability",
    # field="operation"))`) carries the full 2-key shape, `field` the bare
    # word `"operation"`. MitateDB-api's `cell.py::_plan_operation`
    # (`raise CapabilityError(f"transact does not support operation type
    # {op_type!r}")`) carries NO `details` at all yet -- `CapabilityError`
    # is a pre-existing call site `errors.ValidationError`'s own WP-3a
    # docstring already discloses as out of THIS work package's scope (the
    # D-3 vocabulary rollout onto every pre-existing choke point is WP-3e's
    # own, separate task). Because the two peers' `field` values differ
    # (one bare word, one absent), only the closed vocabulary/generic
    # request-internal-path shape is asserted below, not a literal value;
    # `field`'s presence itself is not required while this gap stands (the
    # `_assert_details_field_path_shape`/`.get` calls below already
    # tolerate `None`).
    count_before = iso.count(runtime, entity)
    with pytest.raises(ConformanceDenial) as ei_cap:
        iso.attempt_mutation(
            runtime, entity, "upsert", values={"label": "x"}, where_field=None, where_value=None,
        )
    assert ei_cap.value.code == "CAPABILITY_UNSUPPORTED", f"{adapter.name}: {ei_cap.value.code!r}"
    assert ei_cap.value.details.get("violated_declaration") == "capability", ei_cap.value.details
    _assert_details_field_path_shape(ei_cap.value.details.get("field"), kind=None, adapter_name=adapter.name)
    assert_details_vocabulary_values_safe(ei_cap.value.details, adapter_name=adapter.name)
    observed_codes.add("CAPABILITY_UNSUPPORTED")
    # No side effect: a refused upsert must not have inserted/updated
    # anything (SI-09), same discipline C-17's own no-declared-key upsert
    # negative control already asserts.
    count_after = iso.count(runtime, entity)
    assert count_after == count_before, (
        f"{adapter.name}: row count changed ({count_before} -> {count_after}) despite the "
        "no-declared-unique-key upsert being refused CAPABILITY_UNSUPPORTED"
    )

    # WP-1b rework (review point G, supervisor ruling 2026-09-07 item 6):
    # the OLD `assert observed_codes` here was structurally dead --
    # CAPABILITY_UNSUPPORTED is added unconditionally just above, so the
    # set could never be empty. Replaced with `observed_codes` itself
    # (at least one of the 3 codes was actually observed, not merely
    # presumed).
    assert observed_codes, f"{adapter.name}: no required-vocabulary code was observed at all (non-vacuity)"

    # 監督裁定 N-4 (`{scratchpad}/rulings-r2-closure.md`): (a) details.field's
    # own path FORM is asserted on the value-violation probe already run
    # above (`ei_type`, a field_type violation on an insert operation's
    # own values); (b) two field_constraints-related denials -- a
    # declaration that is itself invalid (`enum` on an untyped/`json`
    # field, `violated_declaration: constraint_declaration`) and a
    # `field_constraints` sent without `fields` (`violated_declaration:
    # request_schema`) -- are added to the probe set, using port v1.13's
    # `schema_operation_with_result` (the `alter_field` primitive's own
    # entry point, and the only port method that can carry
    # `field_constraints` through to `create_entity` without going
    # through the two pre-existing, pre-v1.13 convenience methods).
    # Deliberately placed AFTER every pre-existing probe/assert in this
    # body (not interleaved) so the `< 1.7.0` branch's own failure --
    # which already happens on ONE of the pre-existing vocabulary asserts
    # above, for every peer currently registered -- fires first; a peer
    # not yet declaring 1.7.0 is not expected to reach this leg at all.
    #
    # Both new probes are declare-first the same way the pre-existing
    # unknown-field probe above is (`ei_schema`): where this deployment's
    # own `constraint_declarations` capability is `unavailable`, a
    # request carrying `field_constraints` is refused CAPABILITY_
    # UNSUPPORTED before the declaration itself is ever examined (C-20's
    # own `unavailable` branch) -- that is a DIFFERENT denial than the
    # one this leg is probing for, and is accepted here without asserting
    # the schema-declaration field-shape (which only applies once the
    # declaration is actually examined).
    _assert_details_field_path_shape(ei_type.value.details.get("field"), kind="value", adapter_name=adapter.name)

    json_field = fresh_identifier("c21declfld")
    bad_entity = fresh_identifier("c21decl")
    with pytest.raises(ConformanceDenial) as ei_decl:
        iso.schema_operation_with_result(
            developer, bad_entity, "create_entity",
            fields=[json_field], field_constraints={json_field: {"enum": ["a", "b"]}},
        )
    if ei_decl.value.code == "CAPABILITY_UNSUPPORTED":
        assert ei_decl.value.details.get("violated_declaration") == "capability", ei_decl.value.details
    else:
        assert ei_decl.value.code == "VALIDATION_FAILED", (
            f"{adapter.name}: an enum declared on a json (type-undeclared) field in create_entity -> "
            f"{ei_decl.value.code!r}, expected VALIDATION_FAILED or CAPABILITY_UNSUPPORTED"
        )
        assert ei_decl.value.details.get("violated_declaration") == "constraint_declaration", (
            ei_decl.value.details
        )
        _assert_details_field_path_shape(
            ei_decl.value.details.get("field"), kind="schema_declaration", adapter_name=adapter.name,
        )
        assert_details_vocabulary_values_safe(ei_decl.value.details, adapter_name=adapter.name)

    nofields_entity = fresh_identifier("c21declnf")
    with pytest.raises(ConformanceDenial) as ei_fc_nofields:
        iso.schema_operation_with_result(
            developer, nofields_entity, "create_entity", field_constraints={"label": {"enum": ["a", "b"]}},
        )
    if ei_fc_nofields.value.code == "CAPABILITY_UNSUPPORTED":
        assert ei_fc_nofields.value.details.get("violated_declaration") == "capability", (
            ei_fc_nofields.value.details
        )
    else:
        assert ei_fc_nofields.value.code == "VALIDATION_FAILED", (
            f"{adapter.name}: field_constraints sent without fields -> {ei_fc_nofields.value.code!r}, "
            "expected VALIDATION_FAILED or CAPABILITY_UNSUPPORTED"
        )
        assert ei_fc_nofields.value.details.get("violated_declaration") == "request_schema", (
            ei_fc_nofields.value.details
        )
        _assert_details_field_path_shape(
            ei_fc_nofields.value.details.get("field"), kind="schema_declaration", adapter_name=adapter.name,
        )
        assert_details_vocabulary_values_safe(ei_fc_nofields.value.details, adapter_name=adapter.name)

    # Work order §6 訂正註 7 (supervisor ruling, post-WP-1-audit,
    # 2026-09-07): the declaration-derived `observed_branch` cross-check
    # is done ONLY in the `>= 1.7.0` branch. The audit's mutation E3/E2
    # showed that when this cross-check was unconditional, `expected_
    # branch` is always "pre_1_7_0" while `observed_branch` was always
    # hardcoded to "vocabulary_enforced" in the `< 1.7.0` branch -- the
    # two can never agree, so this assert ALWAYS raised in that branch
    # regardless of what the vocabulary body above actually observed,
    # making a genuine strict XPASS structurally impossible (D-1(7)'s
    # own detection never fired). In the `< 1.7.0` branch the vocabulary
    # body's own unconditional assertions above are the entire detection
    # mechanism: they only pass for real once R-3 is wired in, and
    # strict=True turns that genuine pass into the intended hard failure.
    if not pre_1_7_0:
        observed_branch = "vocabulary_enforced"
        expected_branch = _expected_branch_for_pre_1_7_0(pre_1_7_0)
        assert observed_branch == expected_branch, (
            f"{adapter.name}: contract_version {contract_version!r} implies branch {expected_branch!r}, but the "
            f"full R-3 vocabulary body completed without any refusal -- observed {observed_branch!r} (an early "
            "implementation ahead of this peer's own version-flip commit, D-1(7))"
        )
