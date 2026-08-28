"""C-13 -- credential revocation terminality (SI-13).

design: docs/design/CONFORMANCE_CONDITIONS_V1_1.md section 3 (C-13). Every
test here carries @pytest.mark.condition("C-13") via the module-level
`pytestmark`.
"""
from __future__ import annotations

import pytest

from adapter import (
    UNCLASSIFIED,
    ConformanceDenial,
    Fixture,
    TAMPER_DISPOSITIONS,
    load_contract_error_codes,
    signature_forbids_parameters,
)

pytestmark = pytest.mark.condition("C-13")

# The same acceptance set C-08 uses for "the credential is refused".
REVOKED_CODES = {"AUTH_REVOKED", "AUTH_INVALID"}

# design section 2: a must_deny reactivation-vector denial may legitimately
# come from several different control-plane failure modes depending on the
# peer and the specific vector (a terminal-revoke rejection, an
# authorization failure, a not-found on a defensive re-provision probe, a
# conflict on a re-issue-same-id probe, or an authentication failure when
# the vector's own attempt() chains a post-condition authenticate call).
REACTIVATION_MUST_DENY_CODES = {
    "VALIDATION_FAILED",
    "AUTH_INVALID",
    "AUTH_REVOKED",
    "FORBIDDEN",
    "NOT_FOUND",
    "CONFLICT",
    "CAPABILITY_UNSUPPORTED",
}


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


def test_revoked_credential_stays_revoked_across_every_reactivation_vector(adapter, fx: Fixture):
    handle = adapter.issue_credential(fx.app_a, "runtime")

    # positive control
    adapter.authenticate(handle)

    adapter.revoke_credential(handle)
    with pytest.raises(ConformanceDenial) as ei_revoked:
        adapter.authenticate(handle)
    _assert_is_contract_code(ei_revoked.value.code)
    assert ei_revoked.value.code in REVOKED_CODES, (
        f"{adapter.name}: authenticate after revoke: {ei_revoked.value.code!r} not in {REVOKED_CODES}"
    )

    vectors = adapter.credential_reactivation_vectors(handle)
    assert vectors, f"{adapter.name}: credential_reactivation_vectors() returned no vectors"

    for v in vectors:
        assert v.disposition in TAMPER_DISPOSITIONS, f"{v.name}: unknown disposition {v.disposition!r}"

        if v.disposition == "must_deny":
            assert v.attempt is not None, f"{v.name}: must_deny vector has no attempt()"
            with pytest.raises(ConformanceDenial) as ei_vector:
                v.attempt()
            _assert_is_contract_code(ei_vector.value.code)
            assert ei_vector.value.code in REACTIVATION_MUST_DENY_CODES, (
                f"{v.name}: denial code {ei_vector.value.code!r} not in "
                f"{REACTIVATION_MUST_DENY_CODES}{_unclassified_hint(ei_vector.value.code)}"
            )

        elif v.disposition == "must_ignore":
            assert v.attempt is not None, f"{v.name}: must_ignore vector has no attempt()"
            try:
                v.attempt()
            except ConformanceDenial:
                pass  # a denial is also acceptable; only the post-condition below is required
            with pytest.raises(ConformanceDenial) as ei_after:
                adapter.authenticate(handle)
            _assert_is_contract_code(ei_after.value.code)
            assert ei_after.value.code in REVOKED_CODES, (
                f"{v.name}: credential authenticated again after a must_ignore reactivation vector "
                f"(code {ei_after.value.code!r})"
            )

        else:  # structurally_absent
            assert v.surface, f"{v.name}: structurally_absent vector declares no surface to inspect"
            assert v.forbidden_parameters, f"{v.name}: structurally_absent vector declares no forbidden_parameters"
            violations = signature_forbids_parameters(v.surface, v.forbidden_parameters)
            assert not violations, f"{v.name}: forbidden parameter(s) present on public surface: {violations}"

    # Final check, after every declared vector has been attempted: the
    # credential is still, unconditionally, denied.
    with pytest.raises(ConformanceDenial) as ei_final:
        adapter.authenticate(handle)
    _assert_is_contract_code(ei_final.value.code)
    assert ei_final.value.code in REVOKED_CODES, (
        f"{adapter.name}: final authenticate: {ei_final.value.code!r} not in {REVOKED_CODES}"
    )
