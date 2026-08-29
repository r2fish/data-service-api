"""C-08 -- revocation boundary (SI-13, SI-15).

design: docs/design/CONFORMANCE_ADAPTER_V1.md section 5.3. Every test here
carries @pytest.mark.condition("C-08") via the module-level `pytestmark`.

Design section 5.3 item 8 calls for checking that a capability document
publishes `propagation_bound_ms()`'s value. The `ConformanceAdapter` ABC
(design section 4.4) now exposes `capability_document()`, so this file
checks the full item 8: `propagation_bound_ms()` is finite/non-negative,
the peer's own capability document publishes
`authorization_propagation_bound_ms` as a non-negative integer, and the two
values agree. SI-13's requirement is that the bound be *published*, not
merely known internally to the peer.
"""
from __future__ import annotations

import contextlib

import pytest

from adapter import UNCLASSIFIED, ConformanceDenial, Fixture, load_contract_error_codes

pytestmark = pytest.mark.condition("C-08")

# design section 5.3 items 2/3
REVOKED_CODES = {"AUTH_REVOKED", "AUTH_INVALID"}
# design section 5.3 item 4
DISABLED_CODES = {"APPLICATION_DISABLED", "AUTH_INVALID"}
# design section 5.3 item 7
UNAVAILABLE_CODES = {"AUTH_STATE_UNAVAILABLE", "SERVICE_UNAVAILABLE"}


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


def _assert_code_in(code: str, allowed: set[str], *, label: str) -> None:
    assert code in allowed, (
        f"{label}: denial code {code!r} not in the accepted set {allowed}{_unclassified_hint(code)}"
    )


# --- 1. positive control ----------------------------------------------------


def test_positive_control_runtime_operations_succeed(adapter, fx: Fixture):
    assert adapter.scope_of(fx.runtime_a).application_id == fx.app_a
    # must not raise
    adapter.entities(fx.runtime_a)


# --- 2 & 3. existing session stops; re-authentication is refused -----------


def test_revoked_credential_stops_existing_session_and_reauth(adapter, fx: Fixture):
    handle = adapter.issue_credential(fx.app_a, "runtime")
    session = adapter.authenticate(handle)
    # sanity: works before revoke
    adapter.entities(session)

    adapter.revoke_credential(handle)

    # item 2: the already-authenticated session must stop working, not just
    # future authenticate() calls.
    with pytest.raises(ConformanceDenial) as ei_session:
        adapter.entities(session)
    _assert_is_contract_code(ei_session.value.code)
    _assert_code_in(ei_session.value.code, REVOKED_CODES, label="revoked-session operation")

    # item 3: re-authenticating with the revoked secret must also fail.
    with pytest.raises(ConformanceDenial) as ei_auth:
        adapter.authenticate(handle)
    _assert_is_contract_code(ei_auth.value.code)
    _assert_code_in(ei_auth.value.code, REVOKED_CODES, label="re-authenticate with revoked secret")


# --- 4, 5 & 6. disable propagates; containment; selective re-enable --------


def test_disable_propagates_contains_and_enable_is_selective(adapter, fx: Fixture):
    # A second, never-revoked credential/session for app_a.
    normal_handle = adapter.issue_credential(fx.app_a, "runtime")
    normal_session = adapter.authenticate(normal_handle)
    adapter.entities(normal_session)  # sanity: works before disable

    # A credential we will revoke, to prove revocation survives disable/enable.
    revoked_handle = adapter.issue_credential(fx.app_a, "runtime")
    adapter.authenticate(revoked_handle)
    adapter.revoke_credential(revoked_handle)

    adapter.disable_application(fx.app_a)
    try:
        # item 4: disable propagates to a *different*, non-revoked
        # credential's session.
        with pytest.raises(ConformanceDenial) as ei_disabled:
            adapter.entities(normal_session)
        _assert_is_contract_code(ei_disabled.value.code)
        _assert_code_in(ei_disabled.value.code, DISABLED_CODES, label="disabled-application operation")

        # item 5: containment -- application B is unaffected.
        adapter.entities(fx.runtime_b)  # must not raise
    finally:
        adapter.enable_application(fx.app_a)

    # item 6: the normal credential recovers after enable ...
    normal_session_2 = adapter.authenticate(normal_handle)
    adapter.entities(normal_session_2)  # must not raise

    # ... but the revoked credential does not come back just because the
    # application was re-enabled.
    with pytest.raises(ConformanceDenial) as ei_still_revoked:
        adapter.authenticate(revoked_handle)
    _assert_is_contract_code(ei_still_revoked.value.code)
    _assert_code_in(ei_still_revoked.value.code, REVOKED_CODES, label="revoked credential after re-enable")


# --- 7. authorization-state-unavailable fails closed, then recovers -------


def test_authorization_state_unavailable_fails_closed_then_recovers(adapter, fx: Fixture):
    fresh_handle = adapter.issue_credential(fx.app_a, "runtime")

    adapter.set_authorization_state_available(False)
    try:
        with pytest.raises(ConformanceDenial) as ei_new_auth:
            adapter.authenticate(fresh_handle)
        _assert_is_contract_code(ei_new_auth.value.code)
        _assert_code_in(ei_new_auth.value.code, UNAVAILABLE_CODES, label="new authenticate while unavailable")

        with pytest.raises(ConformanceDenial) as ei_existing:
            adapter.entities(fx.runtime_a)
        _assert_is_contract_code(ei_existing.value.code)
        _assert_code_in(ei_existing.value.code, UNAVAILABLE_CODES, label="existing session while unavailable")
    finally:
        adapter.set_authorization_state_available(True)

    # recovery: normal operation resumes
    adapter.entities(fx.runtime_a)  # must not raise
    session = adapter.authenticate(fresh_handle)
    adapter.entities(session)  # must not raise


# --- 8. propagation bound is a finite, non-negative value ------------------


def test_propagation_bound_is_finite_and_non_negative(adapter, fx: Fixture):
    bound = adapter.propagation_bound_ms()
    assert isinstance(bound, int) and not isinstance(bound, bool)
    assert bound >= 0

    # design section 5.3 item 8: the bound must be *published*, not merely
    # known internally. A missing/empty document is a real SI-13 gap, not
    # an escape hatch (design principle 4).
    document = adapter.capability_document()
    assert document, "capability_document() must not be None or empty"
    assert "authorization_propagation_bound_ms" in document, (
        "capability document does not publish authorization_propagation_bound_ms"
    )
    published_bound = document["authorization_propagation_bound_ms"]
    assert isinstance(published_bound, int) and not isinstance(published_bound, bool)
    assert published_bound >= 0
    assert published_bound == bound, (
        f"published authorization_propagation_bound_ms ({published_bound}) disagrees "
        f"with propagation_bound_ms() ({bound})"
    )


# --- 9. idempotency: repeating a denial-establishing call does not loosen --


def test_double_revoke_and_double_disable_do_not_loosen_denial(adapter, fx: Fixture):
    handle = adapter.issue_credential(fx.app_a, "runtime")
    session = adapter.authenticate(handle)
    adapter.revoke_credential(handle)
    with contextlib.suppress(Exception):
        adapter.revoke_credential(handle)  # second revoke: outcome unspecified, must not un-revoke
    with pytest.raises(ConformanceDenial):
        adapter.entities(session)

    adapter.disable_application(fx.app_a)
    try:
        with contextlib.suppress(Exception):
            adapter.disable_application(fx.app_a)  # second disable: outcome unspecified
        other_handle = adapter.issue_credential(fx.app_a, "runtime")
        with pytest.raises(ConformanceDenial):
            adapter.authenticate(other_handle)
    finally:
        adapter.enable_application(fx.app_a)
