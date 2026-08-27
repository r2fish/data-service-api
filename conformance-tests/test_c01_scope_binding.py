"""C-01 -- scope tampering (SI-01, SI-06).

design: docs/design/CONFORMANCE_ADAPTER_V1.md section 5.1. Every test here
carries @pytest.mark.condition("C-01") via the module-level `pytestmark`.
"""
from __future__ import annotations

import pytest

from adapter import (
    UNCLASSIFIED,
    ConformanceDenial,
    Fixture,
    MUST_COVER_TAMPER_KINDS,
    ScopeView,
    TAMPER_DISPOSITIONS,
    TAMPER_KINDS,
    fresh_identifier,
    load_contract_error_codes,
    signature_forbids_parameters,
)

pytestmark = pytest.mark.condition("C-01")

# design section 5.1 item 3
MUST_DENY_CODES = {
    "SCOPE_MISMATCH",
    "AUTH_INVALID",
    "FORBIDDEN",
    "AUTH_REQUIRED",
    "NOT_FOUND",
    "VALIDATION_FAILED",
}

# A placeholder select/filter field used only in probes that are expected to
# be denied purely on entity/application-scope grounds (design 5.1 items
# 7/8). Its value never needs to be a real field of the target entity: the
# assertion under test is that the operation is denied before field-level
# schema is ever consulted for out-of-scope data, and (item 8) that the
# denial is identical whether the entity exists in another application or
# does not exist at all.
_PLACEHOLDER_FIELD = "id"


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


def _snapshot(adapter, session) -> tuple[frozenset[str], dict[str, int]]:
    ents = frozenset(adapter.entities(session))
    counts = {e: adapter.count(session, e) for e in ents}
    return ents, counts


# --- 1. positive control -------------------------------------------------


def test_positive_control_scope_is_bound_and_legitimate_access_succeeds(adapter, fx: Fixture):
    assert adapter.scope_of(fx.runtime_a) == ScopeView(application_id=fx.app_a, role="runtime")

    # A legitimate read/write cycle must succeed for runtime_a. `Fixture`
    # does not specify the field schema of `shared_entity`, so this uses a
    # dedicated entity created fresh (via developer_a's schema authority)
    # specifically for this assertion, then written/read by runtime_a --
    # this proves runtime_a's scope-bound data access works without
    # depending on undocumented shared_entity field names.
    entity = fresh_identifier("c01_positive")
    field_name = "label"
    adapter.create_entity(fx.developer_a, entity, {field_name: "text"})
    adapter.insert(fx.runtime_a, entity, {field_name: "seed"})
    rows = adapter.select_eq(fx.runtime_a, entity, [field_name], field_name, "seed")
    assert any(r.get(field_name) == "seed" for r in rows)


# --- 2. tamper vector coverage -------------------------------------------


def test_tamper_vector_kind_coverage(adapter, fx: Fixture):
    vectors = adapter.tamper_vectors(fx)
    assert vectors, "tamper_vectors() returned no vectors"
    kinds = {v.kind for v in vectors}
    assert kinds <= set(TAMPER_KINDS), f"unknown tamper kind(s): {kinds - set(TAMPER_KINDS)}"
    missing = MUST_COVER_TAMPER_KINDS - kinds
    assert not missing, f"tamper_vectors() is missing required kind(s): {missing}"
    for v in vectors:
        assert v.disposition in TAMPER_DISPOSITIONS, f"{v.name}: unknown disposition {v.disposition!r}"


# --- 3. must_deny vectors -------------------------------------------------


def test_must_deny_vectors_are_denied_with_contract_codes(adapter, fx: Fixture):
    vectors = [v for v in adapter.tamper_vectors(fx) if v.disposition == "must_deny"]
    assert vectors, "no must_deny tamper vectors declared"
    for v in vectors:
        assert v.attempt is not None, f"{v.name}: must_deny vector has no attempt()"
        with pytest.raises(ConformanceDenial) as ei:
            v.attempt()
        denial = ei.value
        _assert_is_contract_code(denial.code)
        assert denial.code in MUST_DENY_CODES, (
            f"{v.name}: denial code {denial.code!r} not in the accepted set "
            f"{MUST_DENY_CODES}{_unclassified_hint(denial.code)}"
        )


# --- 4. must_ignore vectors ------------------------------------------------


def test_must_ignore_vectors_leave_scope_and_other_app_unchanged(adapter, fx: Fixture):
    vectors = [v for v in adapter.tamper_vectors(fx) if v.disposition == "must_ignore"]
    for v in vectors:
        assert v.attempt is not None, f"{v.name}: must_ignore vector has no attempt()"
        scope_before = adapter.scope_of(fx.runtime_a)
        ents_before, counts_before = _snapshot(adapter, fx.runtime_b)

        try:
            v.attempt()
        except ConformanceDenial:
            pass  # denial is also an acceptable outcome; only state matters

        scope_after = adapter.scope_of(fx.runtime_a)
        ents_after, counts_after = _snapshot(adapter, fx.runtime_b)

        assert scope_after == scope_before, f"{v.name}: server-bound scope changed"
        assert ents_after == ents_before, f"{v.name}: application B's entity set changed"
        assert counts_after == counts_before, f"{v.name}: application B's row counts changed"


# --- 5. structurally_absent vectors ----------------------------------------


def test_structurally_absent_vectors_have_no_forbidden_parameters(adapter, fx: Fixture):
    vectors = [v for v in adapter.tamper_vectors(fx) if v.disposition == "structurally_absent"]
    for v in vectors:
        assert v.surface, f"{v.name}: structurally_absent vector declares no surface to inspect"
        assert v.forbidden_parameters, f"{v.name}: structurally_absent vector declares no forbidden_parameters"
        violations = signature_forbids_parameters(v.surface, v.forbidden_parameters)
        assert not violations, f"{v.name}: forbidden parameter(s) present on public surface: {violations}"


# --- 6. role non-elevation --------------------------------------------------


def test_runtime_credential_cannot_self_elevate_to_schema_authority(adapter, fx: Fixture):
    entities_before = set(adapter.entities(fx.developer_a))
    entity = fresh_identifier("c01_role_probe")
    with pytest.raises(ConformanceDenial) as ei:
        adapter.create_entity(fx.runtime_a, entity, {"label": "text"})
    _assert_is_contract_code(ei.value.code)
    entities_after = set(adapter.entities(fx.developer_a))
    assert entities_after == entities_before, "schema state changed despite denial of runtime schema attempt"


# --- 7. cross-application unreachability ------------------------------------


def test_cross_application_entity_is_unreachable(adapter, fx: Fixture):
    count_before = adapter.count(fx.runtime_b, fx.b_only_entity)

    with pytest.raises(ConformanceDenial):
        adapter.select_eq(fx.runtime_a, fx.b_only_entity, [_PLACEHOLDER_FIELD], _PLACEHOLDER_FIELD, "x")
    with pytest.raises(ConformanceDenial):
        adapter.insert(fx.runtime_a, fx.b_only_entity, {_PLACEHOLDER_FIELD: "x"})
    # This is a negative test: it must be denied on scope grounds alone, so
    # it deliberately does NOT request a real destructive delete. Passing
    # VALID_CONFIRMATION here would ask the adapter to supply a genuine
    # destructive-confirmation token; if a scope check ever regressed, that
    # would let this "denial" probe actually delete application B's data
    # instead of proving it can't be reached (design section 10.1).
    with pytest.raises(ConformanceDenial):
        adapter.delete(
            fx.runtime_a,
            fx.b_only_entity,
            _PLACEHOLDER_FIELD,
            "x",
            destructive=False,
            confirmation=None,
        )

    count_after = adapter.count(fx.runtime_b, fx.b_only_entity)
    assert count_after == count_before, "application B's row count changed after A's failed cross-app attempts"


# --- 8. non-disclosure of existence differences ------------------------------


def test_cross_application_denial_does_not_disclose_existence(adapter, fx: Fixture):
    with pytest.raises(ConformanceDenial) as ei_other_app:
        adapter.select_eq(fx.runtime_a, fx.b_only_entity, [_PLACEHOLDER_FIELD], _PLACEHOLDER_FIELD, "x")
    with pytest.raises(ConformanceDenial) as ei_nonexistent:
        adapter.select_eq(
            fx.runtime_a, "nonexistent_entity_xyz", [_PLACEHOLDER_FIELD], _PLACEHOLDER_FIELD, "x"
        )

    code_other_app = ei_other_app.value.code
    code_nonexistent = ei_nonexistent.value.code
    _assert_is_contract_code(code_other_app)
    _assert_is_contract_code(code_nonexistent)
    assert code_other_app == code_nonexistent, (
        "denial code differs between touching another application's entity "
        f"({code_other_app!r}) and touching a name that does not exist anywhere "
        f"({code_nonexistent!r}); this discloses the other application's entity "
        "existence, contrary to SI-01"
    )
