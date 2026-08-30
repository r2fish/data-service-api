"""Regression guard for C-17's present-denial branch, form (b) (WP-2.5
review M-2, docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md R-8).

No currently-registered adapter takes form (b) of `test_c17_declaration_
agreement.py`'s `_assert_declaration_dependent_surface_is_absent_or_denied`
(`MitateDB-api`, the only peer declaring `row_addressability: unavailable`,
takes form (a), `SurfaceAbsent`, since its in-process schema surface
genuinely has no index/uniqueness parameter at all). That branch was
therefore verified only by a one-off, throwaway mutation-injection harness
at the time WP-2.5 introduced it -- not by anything that runs on every
suite invocation and would actually catch a regression. Independent review
confirmed this the hard way: re-injecting the two mutations below survived
against the full registry (no registered adapter exercises form (b) at
all, so nothing failed).

This file closes that gap with a small, adapter-agnostic, in-memory-only
stub (`_StubAdapter`, below) that exercises form (b) directly against the
real, unmutated `_assert_declaration_dependent_surface_is_absent_or_denied`
-- never registered in `registry.json`, never presented to the shared
`adapter`/`fx` fixtures, so this file changes nothing about which adapters
the rest of the suite runs against (design principle: this suite widens
verification, it does not fabricate coverage of a peer that does not exist
-- `_StubAdapter` stands in for a hypothetical FUTURE peer taking form (b),
the same role a synthetic stub plays in `test_c06_destructive_confirmation.
py`'s own vacuity-guard precedent).
"""
from __future__ import annotations

from typing import Any, Mapping

import pytest

from adapter import ConformanceDenial, Fixture
from test_c17_declaration_agreement import _assert_declaration_dependent_surface_is_absent_or_denied

pytestmark = pytest.mark.condition("C-17")


class _StubAdapter:
    """Minimal, test-only stand-in for a hypothetical peer whose schema
    surface is real (unlike `MitateDB-api`'s) but whose `row_addressability`
    capability stays `unavailable` -- form (b) of C-17's unavailable side.
    Implements only what `_assert_declaration_dependent_surface_is_absent_
    or_denied` and `absence.py`'s shared helper actually call: `name`,
    `create_entity`, `create_unique_index`, `public_operation_callables`,
    and (for the (d) follow-up probe) `attempt_mutation`/`select_eq`. Never
    registered in `registry.json`; exists only inside this test module.

    `deny_code`: the code `create_unique_index` refuses with -- the
    scenario under test.
    `index_enforced`: when `True`, a SECOND insert of a value already
    present is refused with `CONFLICT` -- simulating a peer that claims
    (via `deny_code`) it never created the requested index, while actually
    still enforcing uniqueness on that field. An honest form-(b) peer never
    sets this.
    """

    name = "StubAdapter-c17-present-denial"

    def __init__(self, *, deny_code: str, index_enforced: bool) -> None:
        self._deny_code = deny_code
        self._index_enforced = index_enforced
        self._entities: dict[str, list[dict]] = {}

    def create_entity(self, session, entity: str, fields: Mapping[str, str]) -> None:
        self._entities[entity] = []

    def create_unique_index(self, session, entity: str, index: str, fields) -> None:
        raise ConformanceDenial(self._deny_code, self.name, "StubAdapter")

    def public_operation_callables(self):
        # A real surface is irrelevant to form (b) -- `create_unique_index`
        # never raises `SurfaceAbsent` on this stub, so this is never
        # consulted by `absence.py`'s shared helper for this stub. Kept
        # non-empty (`SurfaceAbsent`-style callers elsewhere would need a
        # real surface) purely so nothing downstream chokes on emptiness.
        return [self.create_entity]

    def attempt_mutation(
        self, session, entity: str, operation: str, *,
        values=None, where_field=None, where_value=None, expected_revision=None, unique_key=None,
    ) -> int:
        assert operation == "insert", f"stub only implements insert, got {operation!r}"
        rows = self._entities.setdefault(entity, [])
        if self._index_enforced and any(r.get("label") == values.get("label") for r in rows):
            raise ConformanceDenial("CONFLICT", self.name, "StubAdapter")
        rows.append(dict(values))
        return 1

    def select_eq(self, session, entity: str, select, field: str, value: Any) -> list[dict]:
        rows = self._entities.get(entity, [])
        return [{k: r[k] for k in select if k in r} for r in rows if r.get(field) == value]


def _stub_fixture(adapter: _StubAdapter) -> Fixture:
    # Only `developer_a`/`runtime_a` are read by the function under test;
    # the rest are present only because `Fixture` is a frozen dataclass
    # requiring every field.
    return Fixture(
        adapter=adapter,
        app_a="stub_app_a", app_b="stub_app_b",
        runtime_a="stub-runtime-session", developer_a="stub-developer-session",
        runtime_b="stub-runtime-b-session",
        shared_entity="stub_shared_entity", a_only_entity="stub_a_only_entity", b_only_entity="stub_b_only_entity",
    )


def test_present_denial_branch_accepts_an_honest_capability_unsupported_stub() -> None:
    """Sanity/positive control: a genuinely honest form-(b) stub (refuses
    with the one accepted code, never actually enforces the index) must
    pass without raising anything."""
    stub = _StubAdapter(deny_code="CAPABILITY_UNSUPPORTED", index_enforced=False)
    _assert_declaration_dependent_surface_is_absent_or_denied(stub, _stub_fixture(stub))


def test_present_denial_branch_rejects_a_declaration_inconsistent_denial_code() -> None:
    """Kills the "誤コード受理" mutant (WP-2.5 review M-2): if the
    `denial.code == "CAPABILITY_UNSUPPORTED"` check inside
    `assert_control_operation_absent_or_uniformly_refused` (or a future
    reimplementation that bypasses it) is ever weakened or removed, this
    stub -- refusing with an unrelated code -- would be silently accepted
    as a second honest form of absence, and this test goes from FAILED
    (correct today) to passing (a mutant surviving)."""
    stub = _StubAdapter(deny_code="VALIDATION_FAILED", index_enforced=False)
    with pytest.raises(AssertionError, match="instead of CAPABILITY_UNSUPPORTED"):
        _assert_declaration_dependent_surface_is_absent_or_denied(stub, _stub_fixture(stub))


def test_present_denial_branch_still_probes_for_a_secretly_enforced_index() -> None:
    """Kills the "(d) プローブ除去" mutant (WP-2.5 review M-2): if the
    post-denial duplicate-insert probe (design requirement (d) -- both
    inserts must succeed, since no index was ever actually created) is
    ever deleted from `_assert_declaration_dependent_surface_is_absent_or_
    denied`, this stub -- which refuses `create_unique_index` with the
    honest code but secretly still enforces uniqueness on 'label' -- would
    go completely unnoticed: the function would return normally right
    after the code check, with `attempt_mutation` never even being called.
    That flip (an exception here -> nothing raised at all) is exactly what
    this test is written to catch: `pytest.raises` demands SOME exception,
    so a probe-less mutant fails this test with "DID NOT RAISE" instead of
    silently passing."""
    stub = _StubAdapter(deny_code="CAPABILITY_UNSUPPORTED", index_enforced=True)
    with pytest.raises(ConformanceDenial) as excinfo:
        _assert_declaration_dependent_surface_is_absent_or_denied(stub, _stub_fixture(stub))
    assert excinfo.value.code == "CONFLICT", (
        f"expected the (d) probe's second colliding insert to surface the stub's own simulated enforcement "
        f"as CONFLICT, got {excinfo.value.code!r}"
    )
