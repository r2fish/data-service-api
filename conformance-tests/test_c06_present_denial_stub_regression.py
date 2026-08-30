"""Regression guard for C-06 V3/V6's `drop_entity` present-denial form
(WP-2.5c, docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md R-8).

No currently-registered adapter takes the new `"declared_unavailable"`
(present-denial) form of `_drop_entity_form_and_probe`: both r2db-api
adapters take `"present"` (a real, functioning `drop_entity`), and
`MitateDB-api` takes `"surface_absent"` (no drop/destroy parameter exists
anywhere on its public surface). Exercising the new form at all therefore
requires a small, in-memory-only stub -- never registered in
`registry.json`, never presented to the shared `adapter`/`fx` fixtures --
mirroring `test_c17_present_denial_stub_regression.py`'s own precedent for
the identical situation C-17's own present-denial widening was in.
"""
from __future__ import annotations

import itertools
from typing import Any, Mapping

import pytest

from adapter import ConformanceDenial, Fixture, SurfaceAbsent
from test_c06_destructive_confirmation import (
    _assert_drop_entity_absence_agrees_with_declaration,
    _assert_drop_entity_present_denial_had_no_effect,
    _drop_entity_form_and_probe,
)
from test_c06_destructive_confirmation import (
    test_c06_v6_drop_entity_fingerprint_invalidation as _real_v6_test,
)

pytestmark = pytest.mark.condition("C-06")

# `test_c06_destructive_confirmation.py`'s own `_capability_document()`
# caches by `adapter.name` in a module-level dict for the whole test
# session -- every `_StubAdapter` instance therefore needs a name unique to
# ITSELF, not merely to this class, or a later test's stub would silently
# read an earlier test's stub's cached document instead of its own
# (measured directly: without this counter, `test_present_denial_form_
# rejects_a_declaration_that_omits_drop_entity` below spuriously passed
# through by inheriting an earlier test's cached, drop_entity-unsupported
# document).
_STUB_NAME_COUNTER = itertools.count()


class _StubAdapter:
    """Minimal, test-only stand-in for a hypothetical peer whose schema
    surface is real (unlike `MitateDB-api`'s) but whose `drop_entity`
    operation is refused -- the present-denial form of C-06's V3/V6
    absence side. Implements only what `_drop_entity_form_and_probe`,
    `absence.py`'s shared helper, and `_assert_drop_entity_absence_agrees_
    with_declaration` actually call.

    `deny_code`: the code `drop_entity` refuses with -- the scenario under
    test.
    `actually_drops`: when `True`, the entity is removed from `entities()`
    despite the refusal -- simulating a peer that claims (via `deny_code`)
    it never dropped the entity, while actually doing so anyway. An honest
    present-denial peer never sets this.
    `declare_unsupported`: whether the stub's own capability document
    declares `drop_entity` as unsupported (the honest case) or omits it
    entirely (the declaration-inconsistent case M-6 guards against).
    """

    def __init__(self, *, deny_code: str, actually_drops: bool = False, declare_unsupported: bool = True) -> None:
        self.name = f"StubAdapter-c06-present-denial-{next(_STUB_NAME_COUNTER)}"
        self._deny_code = deny_code
        self._actually_drops = actually_drops
        self._declare_unsupported = declare_unsupported
        self._entities: set[str] = set()

    def create_entity(self, session, entity: str, fields: Mapping[str, str]) -> None:
        self._entities.add(entity)

    def drop_entity(self, session, entity: str, *, destructive: bool, confirmation: str | None) -> None:
        if self._actually_drops:
            self._entities.discard(entity)
        raise ConformanceDenial(self._deny_code, self.name, "StubAdapter")

    def entities(self, session) -> set[str]:
        return set(self._entities)

    def capability_document(self) -> Mapping[str, Any]:
        schema_ops: dict[str, Any] = {"status": "partial", "operations": ["create_entity"]}
        if self._declare_unsupported:
            schema_ops["unsupported"] = ["drop_entity"]
        else:
            schema_ops["unsupported"] = []
        return {
            "contract_version": "1.2.0",
            "capabilities": {"schema_operations": schema_ops},
        }

    def public_operation_callables(self):
        return [self.create_entity]


def _seed(deny_code: str, *, actually_drops: bool = False, declare_unsupported: bool = True) -> tuple[_StubAdapter, str]:
    stub = _StubAdapter(deny_code=deny_code, actually_drops=actually_drops, declare_unsupported=declare_unsupported)
    entity = "stub_entity"
    stub.create_entity(None, entity, {"item_key": "integer"})
    return stub, entity


def test_present_denial_form_accepts_an_honest_capability_unsupported_stub() -> None:
    """Sanity/positive control: a genuinely honest present-denial stub
    (refuses with the one accepted code, never actually drops the entity,
    declares drop_entity unsupported) must classify as
    "declared_unavailable" and pass its declaration-consistency check."""
    stub, entity = _seed("CAPABILITY_UNSUPPORTED")
    form, denial = _drop_entity_form_and_probe(stub, None, entity)
    assert form == "declared_unavailable" and denial is None
    _assert_drop_entity_absence_agrees_with_declaration(stub)
    assert entity in stub.entities(None), "the honest stub's own entity vanished unexpectedly"


def test_present_denial_form_rejects_a_declaration_inconsistent_denial_code() -> None:
    """Kills the "誤コード受理" mutant (WP-2.5c completion condition (ii)):
    if the `denial.code == "CAPABILITY_UNSUPPORTED"` check inside
    `absence.py`'s shared `assert_control_operation_absent_or_uniformly_
    refused` is ever weakened or removed, this stub -- refusing with an
    unrelated code -- would be silently accepted as a second honest form
    of absence instead of failing loudly."""
    stub, entity = _seed("VALIDATION_FAILED")
    with pytest.raises(AssertionError, match="instead of CAPABILITY_UNSUPPORTED"):
        _drop_entity_form_and_probe(stub, None, entity)


def test_present_denial_form_still_probes_for_a_secretly_dropped_entity() -> None:
    """Kills the "(d) プローブ除去" mutant: if the post-denial no-effect
    probe (`_assert_drop_entity_present_denial_had_no_effect`, requirement
    (d)) is ever deleted from the V3/V6 call sites, this stub -- which
    refuses `drop_entity` with the honest code but secretly drops the
    entity anyway -- would go completely unnoticed by the classification
    step alone. The classification itself (`_drop_entity_form_and_probe`)
    still succeeds (form is correctly "declared_unavailable"); it is the
    CALLER's own follow-up probe that must catch the inconsistency, so this
    test drives both steps together, exactly as V3/V6 do."""
    stub, entity = _seed("CAPABILITY_UNSUPPORTED", actually_drops=True)
    form, denial = _drop_entity_form_and_probe(stub, None, entity)
    assert form == "declared_unavailable" and denial is None
    assert entity not in stub.entities(None), "test setup problem: stub did not actually simulate a drop"
    with pytest.raises(AssertionError, match="appears to have been dropped despite the refusal"):
        _assert_drop_entity_present_denial_had_no_effect(stub, None, entity)


def test_present_denial_form_rejects_a_declaration_that_omits_drop_entity() -> None:
    """The M-6-style declaration-consistency check (`_assert_drop_entity_
    absence_agrees_with_declaration`) must reject a present-denial peer
    whose OWN capability document neither declares `schema_operations`
    `unavailable` nor lists `drop_entity` under `unsupported` -- an
    internally inconsistent declaration (refuses in practice, but claims
    support on paper)."""
    stub, entity = _seed("CAPABILITY_UNSUPPORTED", declare_unsupported=False)
    form, denial = _drop_entity_form_and_probe(stub, None, entity)
    assert form == "declared_unavailable" and denial is None
    with pytest.raises(AssertionError, match="disagrees with this peer's own declared capability document"):
        _assert_drop_entity_absence_agrees_with_declaration(stub)


# --- requirement (iii): the pre-existing SurfaceAbsent (form (a)) side is --
# unchanged plumbing (the same `absence.py` shared helper C-14/C-15/C-17
# already exercise), but is re-verified here directly against `drop_entity`
# too, so this file's own regression net covers all three forms
# `_drop_entity_form_and_probe` now distinguishes, not just the two new to
# WP-2.5c.


def _fake_surface_with_drop_param(drop=None):
    """A real callable whose signature genuinely contains a parameter name
    matching a forbidden-vocabulary fragment (`"drop"`) -- used below to
    construct a SurfaceAbsent claim that IS false."""


class _SurfaceAbsentStubAdapter:
    def __init__(self, *, lying: bool) -> None:
        self.name = f"StubAdapter-c06-surface-absent-{next(_STUB_NAME_COUNTER)}"
        self._lying = lying
        self._entities: set[str] = set()

    def create_entity(self, session, entity: str, fields: Mapping[str, str]) -> None:
        self._entities.add(entity)

    def drop_entity(self, session, entity: str, *, destructive: bool, confirmation: str | None) -> None:
        if self._lying:
            raise SurfaceAbsent(
                self.name, "drop_entity",
                "synthetic lying claim: declares absence but the evidence surface below genuinely "
                "carries a parameter matching 'drop'",
                surface=[_fake_surface_with_drop_param], forbidden_parameters=["drop"],
            )
        raise SurfaceAbsent(
            self.name, "drop_entity", "genuinely no drop/destroy entry point on this stub's surface",
            surface=self.public_operation_callables(), forbidden_parameters=["drop", "destroy"],
        )

    def entities(self, session) -> set[str]:
        return set(self._entities)

    def capability_document(self) -> Mapping[str, Any]:
        return {
            "contract_version": "1.2.0",
            "capabilities": {"schema_operations": {"status": "unavailable"}},
        }

    def public_operation_callables(self):
        return [self.create_entity]


def test_present_denial_widening_still_accepts_a_genuine_surface_absent_stub() -> None:
    """Requirement (iii): the pre-existing SurfaceAbsent form must still
    classify correctly after WP-2.5c's widening -- unchanged from before,
    since `_drop_entity_form_and_probe` delegates this form entirely to
    `absence.py`'s shared, untouched SurfaceAbsent branch."""
    stub = _SurfaceAbsentStubAdapter(lying=False)
    entity = "stub_entity"
    stub.create_entity(None, entity, {"item_key": "integer"})
    form, denial = _drop_entity_form_and_probe(stub, None, entity)
    assert form == "surface_absent" and denial is None
    _assert_drop_entity_absence_agrees_with_declaration(stub)


def test_present_denial_widening_still_rejects_a_lying_surface_absent_claim() -> None:
    """Requirement (iii): the SurfaceAbsent side's own independent
    re-verification (`signature_forbids_parameters` against the claimed
    surface) must still catch a false claim after WP-2.5c's widening --
    unchanged, since it lives entirely inside `absence.py`'s shared helper,
    untouched by this WP."""
    stub = _SurfaceAbsentStubAdapter(lying=True)
    entity = "stub_entity"
    stub.create_entity(None, entity, {"item_key": "integer"})
    with pytest.raises(AssertionError, match="signature_forbids_parameters"):
        _drop_entity_form_and_probe(stub, None, entity)


# --- final review m-C1: pin V6's OWN wiring to the (d) probe, not just the --
# helper it happens to call. Every test above exercises `_drop_entity_form_
# and_probe`/`_assert_drop_entity_present_denial_had_no_effect` directly --
# none of them proves `test_c06_v6_drop_entity_fingerprint_invalidation`
# ITSELF actually wires the (d) probe into its own body. Measured directly:
# deleting that call site from V6 left every stub test above green (they
# never call V6 at all) AND all 4 real registered adapters' own V6 run
# green too (no registered present-denial peer -- `MitateDB-api-http` --
# has any real drop code path to secretly execute, so V6's own real-adapter
# coverage never exercises what the deleted call site would have caught).
# This closes that gap by calling V6 ITSELF -- not a helper it happens to
# use -- with a stub that secretly drops its entity despite an honest
# `CAPABILITY_UNSUPPORTED` refusal.


def _stub_fixture(adapter: _StubAdapter) -> Fixture:
    # V6 only ever reads `fx.developer_a` before returning early for a
    # non-"present" form (`fx.shared_entity` is read only in the "present"
    # continuation, never reached here) -- placeholder strings for every
    # other field are enough to satisfy `Fixture`'s own required fields.
    return Fixture(
        adapter=adapter,
        app_a="stub_app_a", app_b="stub_app_b",
        runtime_a="stub-runtime-session", developer_a="stub-developer-session",
        runtime_b="stub-runtime-b-session",
        shared_entity="stub_shared_entity", a_only_entity="stub_a_only_entity", b_only_entity="stub_b_only_entity",
    )


def test_v6_itself_wires_the_d_probe_and_catches_a_secretly_dropping_present_denial_stub() -> None:
    """m-C1 (final review): calls `test_c06_v6_drop_entity_fingerprint_
    invalidation` DIRECTLY (it is an ordinary function -- nothing prevents
    invoking it outside pytest's own fixture machinery, the same technique
    `test_c17_present_denial_stub_regression.py` already uses for its own
    helper function) against a present-denial stub that secretly drops its
    entity. If V6's own body still calls `_assert_drop_entity_present_
    denial_had_no_effect` after classifying the "declared_unavailable"
    form, this raises; if that call site is ever deleted from V6 (the exact
    mutation this test exists to catch), V6 returns silently instead and
    this test fails with "DID NOT RAISE"."""
    stub = _StubAdapter(deny_code="CAPABILITY_UNSUPPORTED", actually_drops=True)
    fx = _stub_fixture(stub)
    with pytest.raises(AssertionError, match="appears to have been dropped despite the refusal"):
        _real_v6_test(stub, fx)
