"""`control_plane.ControlPlaneService` direct tests (WP-4, design v1.2 R-6).

All exercised against `InMemoryControlBackend` -- fast, no PostgreSQL
dependency (the Postgres backend gets its own, smaller test module,
`test_control_plane_postgres.py`, since `ControlPlaneService` itself is
backend-agnostic and every rule tested here is a SERVICE-layer rule, never a
backend-specific one). WP-4's own scope: this module is never mounted
behind an HTTP app in this WP -- see `test_control_http_unmounted.py`.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from mitatedb_api.control_plane import (ControlPlaneLimits, ControlPlaneService,
                                        InMemoryControlBackend, bootstrap_control_credential)
from mitatedb_api.errors import (AuthenticationError, AuthenticationRequiredError,
                                 AuthorizationError, CapabilityError, ConflictError,
                                 DestructiveConfirmationRequired, NotFoundError,
                                 ResourceLimitError, ValidationError)

_APP_PEPPER = "control-plane-service-app-pepper-x"
_CONTROL_PEPPER = "control-plane-service-ctl-pepper-x"

_SPEC_PATH = Path(__file__).resolve().parents[2] / "spec" / "data-service-api.v1.json"
_SPEC = json.loads(_SPEC_PATH.read_text())
_SCHEMAS = _SPEC["schemas"]


def _assert_schema_exact(schema_name: str, value: dict) -> None:
    """Minimal closed-shape checker (no `jsonschema` dependency in this
    package): every key in `value` must be a declared property, and every
    required property must be present -- the same `additionalProperties:
    false` + `required` discipline `http.py::_check_object_shape` already
    applies to incoming requests, applied here to OUTGOING control-plane
    results (R-6: "制御面応答は契約 schema の完全一致")."""
    schema = _SCHEMAS[schema_name]
    allowed = set(schema.get("properties", {}))
    extra = set(value) - allowed
    assert not extra, f"{schema_name} result has undeclared keys: {sorted(extra)}"
    missing = set(schema.get("required", [])) - set(value)
    assert not missing, f"{schema_name} result is missing required keys: {sorted(missing)}"


def _assert_schema_exact_item(schema_name: str, value: dict) -> None:
    """Same as `_assert_schema_exact`, but for one ITEM of an array-typed
    top-level schema's own `items` sub-schema (`ApplicationsResult.
    applications[*]` / `CredentialsResult.credentials[*]`)."""
    item_schema = _SCHEMAS[schema_name]["properties"][_ITEM_KEY[schema_name]]["items"]
    allowed = set(item_schema.get("properties", {}))
    extra = set(value) - allowed
    assert not extra, f"{schema_name} item has undeclared keys: {sorted(extra)}"
    missing = set(item_schema.get("required", [])) - set(value)
    assert not missing, f"{schema_name} item is missing required keys: {sorted(missing)}"


_ITEM_KEY = {"ApplicationsResult": "applications", "CredentialsResult": "credentials"}


def _limits(**overrides) -> ControlPlaneLimits:
    base = dict(applications=5, credentials_per_application=2, control_requests_per_minute=90)
    base.update(overrides)
    return ControlPlaneLimits(**base)


def _bootstrapped(limits=None):
    backend = InMemoryControlBackend(app_pepper=_APP_PEPPER, control_pepper=_CONTROL_PEPPER)
    with backend.unit_of_work() as work:
        credential_id, secret = bootstrap_control_credential(backend.control_credential_store, backend.append_audit, work=work)
    service = ControlPlaneService(backend, limits=limits or _limits())
    # Clear must_rotate via self-rotate so ordinary tests do not have to
    # thread the must_rotate allow-list through every call site.
    rotated = service.rotate_credential(credential_id, secret, credential_id)
    return service, backend, credential_id, rotated["secret"]


# --------------------------------------------------------------------------
# Bounds numeric constraints (R-6 / WP-0 M-5).
# --------------------------------------------------------------------------


@pytest.mark.parametrize("field,value", [
    ("applications", 0), ("applications", 201),
    ("credentials_per_application", 0), ("credentials_per_application", 201),
    ("control_requests_per_minute", 0), ("control_requests_per_minute", 201),
])
def test_limits_reject_out_of_range_values(field, value) -> None:
    kwargs = dict(applications=5, credentials_per_application=2, control_requests_per_minute=90)
    kwargs[field] = value
    with pytest.raises(ValueError):
        ControlPlaneLimits(**kwargs)


def test_limits_reject_control_requests_per_minute_too_close_to_the_margin() -> None:
    # applications=5, credentials_per_application=2 -> the floor is 5+4+67=76;
    # 76 itself (not exceeding it) must be rejected.
    with pytest.raises(ValueError):
        ControlPlaneLimits(applications=5, credentials_per_application=2, control_requests_per_minute=76)
    ControlPlaneLimits(applications=5, credentials_per_application=2, control_requests_per_minute=77)


# --------------------------------------------------------------------------
# Authentication: AUTH_REQUIRED vs AUTH_INVALID, AUTH_STATE_UNAVAILABLE
# exemption from durable audit.
# --------------------------------------------------------------------------


def test_missing_credential_raises_auth_required_and_is_durably_recorded() -> None:
    service, backend, _cid, _secret = _bootstrapped()
    before = len(backend.audit_sink.snapshot())
    with pytest.raises(AuthenticationRequiredError):
        service.control_capabilities(None, None)
    after = backend.audit_sink.snapshot()
    assert len(after) == before + 1
    assert after[-1].reason_code == "AUTH_REQUIRED"
    assert after[-1].outcome == "deny"


def test_wrong_secret_raises_auth_invalid_and_is_durably_recorded() -> None:
    service, backend, cid, _secret = _bootstrapped()
    before = len(backend.audit_sink.snapshot())
    with pytest.raises(AuthenticationError):
        service.control_capabilities(cid, "not-the-real-secret")
    after = backend.audit_sink.snapshot()
    assert len(after) == before + 1
    assert after[-1].reason_code == "AUTH_INVALID"


def test_auth_state_unavailable_is_never_durably_audited() -> None:
    """Design R-6's second audit exemption: when the credential STORE
    itself is unreachable, a durable write is also presumed impossible and
    is never attempted (unlike AUTH_REQUIRED/AUTH_INVALID above, both of
    which ARE durably recorded)."""
    from mitatedb_api.errors import AuthorizationStateUnavailable

    service, backend, cid, secret = _bootstrapped()

    class _DeadBackend:
        def __getattr__(self, name):
            return getattr(backend, name)

        def authenticate_control(self, credential_id, secret):
            raise AuthorizationStateUnavailable("simulated store outage")

    service._backend = _DeadBackend()
    before = len(backend.audit_sink.snapshot())
    with pytest.raises(AuthorizationStateUnavailable):
        service.control_capabilities(cid, secret)
    assert len(backend.audit_sink.snapshot()) == before


def test_rate_limit_denial_is_never_durably_audited() -> None:
    backend = InMemoryControlBackend(app_pepper=_APP_PEPPER, control_pepper=_CONTROL_PEPPER)
    service = ControlPlaneService(backend, limits=_limits(control_requests_per_minute=77))
    # No credential exists at all yet; every call fails at rate-limit or at
    # authentication -- exhaust the (tiny) rate window with authentication
    # failures against a nonexistent credential first, then observe that
    # the request which actually trips LIMIT_EXCEEDED adds no audit row.
    for _ in range(77):
        with pytest.raises(AuthenticationRequiredError):
            service.control_capabilities(None, None)
    before = len(backend.audit_sink.snapshot())
    with pytest.raises(ResourceLimitError) as excinfo:
        service.control_capabilities(None, None)
    assert excinfo.value.details["limit_class"] == "control_requests_per_minute"
    assert len(backend.audit_sink.snapshot()) == before  # unchanged: no new audit row


def test_rate_window_recovers_a_token_after_60_seconds_of_injected_clock_time() -> None:
    """Reviewer m-1: the rate limiter is a genuinely SLIDING 60-second
    window, not merely a bound that is never exceeded -- a stale entry
    must actually fall out of the window once 60 seconds of (injected)
    clock time have passed, freeing a slot for a new request. Without this
    test, widening the window's own comparison (`now - stamp < 60` ->
    `< 6000`) still passes every other control-plane test (they only ever
    exercise "reach the limit", never "wait, then reach it again")."""
    fake_now = [1_000.0]

    def _clock() -> float:
        return fake_now[0]

    backend = InMemoryControlBackend(app_pepper=_APP_PEPPER, control_pepper=_CONTROL_PEPPER)
    service = ControlPlaneService(backend, limits=_limits(control_requests_per_minute=77), clock=_clock)

    for _ in range(77):
        with pytest.raises(AuthenticationRequiredError):
            service.control_capabilities(None, None)
    with pytest.raises(ResourceLimitError):
        service.control_capabilities(None, None)

    # Advance the injected clock by 61 seconds -- every one of the 77
    # earlier timestamps must now have aged out of the window.
    fake_now[0] += 61.0
    with pytest.raises(AuthenticationRequiredError):
        # Not a ResourceLimitError: the window recovered, so this request
        # is charged successfully and fails only on the (still-missing)
        # credential, exactly as the very first call of this test did.
        service.control_capabilities(None, None)


# --------------------------------------------------------------------------
# must_rotate gate (FORBIDDEN, allow-list, self-rotate exception).
# --------------------------------------------------------------------------


def test_must_rotate_forbids_every_operation_except_capabilities_and_self_rotate() -> None:
    backend = InMemoryControlBackend(app_pepper=_APP_PEPPER, control_pepper=_CONTROL_PEPPER)
    with backend.unit_of_work() as work:
        cid, secret = bootstrap_control_credential(backend.control_credential_store, backend.append_audit, work=work)
    service = ControlPlaneService(backend, limits=_limits())

    # Allowed while must_rotate:
    service.control_capabilities(cid, secret)

    # Forbidden while must_rotate:
    with pytest.raises(AuthorizationError):
        service.register_application(cid, secret, "someapp")
    with pytest.raises(AuthorizationError):
        service.list_applications(cid, secret)

    # Self-rotate is allowed and clears must_rotate.
    rotated = service.rotate_credential(cid, secret, cid)
    new_secret = rotated["secret"]
    service.register_application(cid, new_secret, "someapp")  # no longer forbidden


def test_must_rotate_forbidden_is_durably_audited_with_reason_forbidden() -> None:
    backend = InMemoryControlBackend(app_pepper=_APP_PEPPER, control_pepper=_CONTROL_PEPPER)
    with backend.unit_of_work() as work:
        cid, secret = bootstrap_control_credential(backend.control_credential_store, backend.append_audit, work=work)
    service = ControlPlaneService(backend, limits=_limits())
    with pytest.raises(AuthorizationError):
        service.list_applications(cid, secret)
    last = backend.audit_sink.snapshot()[-1]
    assert last.reason_code == "FORBIDDEN"
    assert last.outcome == "deny"


# --------------------------------------------------------------------------
# register_application / list_applications / enable / disable.
# --------------------------------------------------------------------------


def test_register_application_result_matches_schema_exactly() -> None:
    service, _backend, cid, secret = _bootstrapped()
    result = service.register_application(cid, secret, "shopapp")
    _assert_schema_exact("ApplicationStateResult", result)
    assert result == {"application_id": "shopapp", "enabled": True}


def test_register_application_rejects_bad_identifier_shape() -> None:
    service, _backend, cid, secret = _bootstrapped()
    with pytest.raises(ValidationError):
        service.register_application(cid, secret, "NotLowercase")
    with pytest.raises(ValidationError):
        service.register_application(cid, secret, "")


def test_register_application_duplicate_is_conflict() -> None:
    service, _backend, cid, secret = _bootstrapped()
    service.register_application(cid, secret, "dupapp")
    with pytest.raises(ConflictError):
        service.register_application(cid, secret, "dupapp")


def test_register_application_enforces_the_applications_bound() -> None:
    service, _backend, cid, secret = _bootstrapped(limits=_limits(applications=2))
    service.register_application(cid, secret, "app1")
    service.register_application(cid, secret, "app2")
    with pytest.raises(ResourceLimitError) as excinfo:
        service.register_application(cid, secret, "app3")
    assert excinfo.value.details["limit_class"] == "applications"


def test_list_applications_and_enable_disable_round_trip() -> None:
    service, _backend, cid, secret = _bootstrapped()
    service.register_application(cid, secret, "toggled")
    listing = service.list_applications(cid, secret)
    _assert_schema_exact("ApplicationsResult", listing)
    for item in listing["applications"]:
        _assert_schema_exact_item("ApplicationsResult", item)
    disabled = service.set_application_enabled(cid, secret, "toggled", False)
    assert disabled == {"application_id": "toggled", "enabled": False}
    enabled = service.set_application_enabled(cid, secret, "toggled", True)
    assert enabled == {"application_id": "toggled", "enabled": True}


def test_set_application_enabled_unknown_application_is_not_found() -> None:
    service, _backend, cid, secret = _bootstrapped()
    with pytest.raises(NotFoundError):
        service.set_application_enabled(cid, secret, "nope", False)


# --------------------------------------------------------------------------
# issue_credential: role=control refusal precedes target resolution
# (C-14 vector-3 style), shape-before-capability, bounds.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("application_id", ["ghostapp99", "disabledapp", "fullapp"])
def test_role_control_is_refused_uniformly_regardless_of_target_state(application_id) -> None:
    service, _backend, cid, secret = _bootstrapped(limits=_limits(credentials_per_application=1))
    if application_id == "disabledapp":
        service.register_application(cid, secret, application_id)
        service.set_application_enabled(cid, secret, application_id, False)
    elif application_id == "fullapp":
        service.register_application(cid, secret, application_id)
        service.issue_credential(cid, secret, application_id, "runtime")  # saturates the bound (limit=1)
    # "does-not-exist" is registered nowhere at all.
    with pytest.raises(CapabilityError):
        service.issue_credential(cid, secret, application_id, "control")


def test_issue_credential_role_shape_is_validated_before_capability_check() -> None:
    service, _backend, cid, secret = _bootstrapped()
    with pytest.raises(ValidationError):
        service.issue_credential(cid, secret, "someapp", "not-a-real-role")


def test_issue_credential_result_matches_schema_exactly() -> None:
    service, _backend, cid, secret = _bootstrapped()
    service.register_application(cid, secret, "issuertest")
    result = service.issue_credential(cid, secret, "issuertest", "runtime")
    _assert_schema_exact("CredentialIssued", result)
    assert result["role"] == "runtime"


def test_issue_credential_enforces_credentials_per_application_bound_excluding_revoked() -> None:
    service, _backend, cid, secret = _bootstrapped(limits=_limits(credentials_per_application=1))
    service.register_application(cid, secret, "boundedapp")
    first = service.issue_credential(cid, secret, "boundedapp", "runtime")
    with pytest.raises(ResourceLimitError) as excinfo:
        service.issue_credential(cid, secret, "boundedapp", "runtime")
    assert excinfo.value.details["limit_class"] == "credentials_per_application"
    # R-6: revoked rows are NOT counted -- revoking the one existing
    # credential must free up headroom for a new one.
    service.revoke_credential(cid, secret, first["credential_id"])
    second = service.issue_credential(cid, secret, "boundedapp", "runtime")
    assert second["credential_id"] != first["credential_id"]


def test_issue_credential_unknown_application_is_not_found() -> None:
    service, _backend, cid, secret = _bootstrapped()
    with pytest.raises(NotFoundError):
        service.issue_credential(cid, secret, "ghostapp", "runtime")


# --------------------------------------------------------------------------
# list_credentials: merged listing, control rows have no application_id and
# no must_rotate key, schema-exact.
# --------------------------------------------------------------------------


def test_list_credentials_merges_application_and_control_rows() -> None:
    service, backend, cid, secret = _bootstrapped()
    service.register_application(cid, secret, "listedapp")
    issued = service.issue_credential(cid, secret, "listedapp", "runtime")

    listing = service.list_credentials(cid, secret)
    _assert_schema_exact("CredentialsResult", listing)
    by_id = {row["credential_id"]: row for row in listing["credentials"]}
    for row in listing["credentials"]:
        _assert_schema_exact_item("CredentialsResult", row)

    app_row = by_id[issued["credential_id"]]
    assert app_row["role"] == "runtime"
    assert app_row["application_id"] == "listedapp"

    control_row = by_id[cid]
    assert control_row["role"] == "control"
    assert "application_id" not in control_row
    assert "must_rotate" not in control_row


# --------------------------------------------------------------------------
# rotate_credential: self-rotate while must_rotate, revoked cannot rotate.
# --------------------------------------------------------------------------


def test_rotate_credential_refuses_a_revoked_credential() -> None:
    service, _backend, cid, secret = _bootstrapped()
    service.register_application(cid, secret, "rotapp")
    issued = service.issue_credential(cid, secret, "rotapp", "runtime")
    service.revoke_credential(cid, secret, issued["credential_id"])
    with pytest.raises(ValidationError):
        service.rotate_credential(cid, secret, issued["credential_id"])


def test_rotate_credential_result_matches_schema_exactly() -> None:
    service, _backend, cid, secret = _bootstrapped()
    service.register_application(cid, secret, "rotapp2")
    issued = service.issue_credential(cid, secret, "rotapp2", "runtime")
    result = service.rotate_credential(cid, secret, issued["credential_id"])
    _assert_schema_exact("CredentialRotated", result)


# --------------------------------------------------------------------------
# revoke_credential: declare-and-echo for the last active control
# credential ONLY; ordinary revokes are never gated; un-revoke absence.
# --------------------------------------------------------------------------


def test_revoke_application_credential_is_never_gated() -> None:
    service, _backend, cid, secret = _bootstrapped()
    service.register_application(cid, secret, "ungated")
    issued = service.issue_credential(cid, secret, "ungated", "runtime")
    result = service.revoke_credential(cid, secret, issued["credential_id"])
    _assert_schema_exact("CredentialStateResult", result)
    assert result["revoked"] is True


def test_revoke_last_active_control_credential_requires_exact_confirmation() -> None:
    service, backend, cid, secret = _bootstrapped()
    with pytest.raises(DestructiveConfirmationRequired) as excinfo:
        service.revoke_credential(cid, secret, cid)
    details = excinfo.value.details
    for key in ("required_confirmation", "consequence", "reversible_alternative", "recovery"):
        assert key in details

    # A well-shaped but non-matching confirmation must NOT satisfy the gate
    # (no prefix/substring acceptance).
    with pytest.raises(DestructiveConfirmationRequired):
        service.revoke_credential(cid, secret, cid, destructive=True, confirmation="yes")
    with pytest.raises(DestructiveConfirmationRequired):
        service.revoke_credential(cid, secret, cid, destructive=True,
                                  confirmation=details["required_confirmation"][:-1])
    # A non-bool `destructive` (even a truthy-looking string) is a SHAPE
    # defect, not a confirmation mismatch -- rejected before the
    # confirmation comparison is even reached (no truthy coercion anywhere
    # in this gate).
    with pytest.raises(ValidationError):
        service.revoke_credential(cid, secret, cid, destructive="true", confirmation=details["required_confirmation"])

    result = service.revoke_credential(cid, secret, cid, destructive=True, confirmation=details["required_confirmation"])
    assert result["revoked"] is True

    # Authentication now fails -- no un-revoke path exists anywhere.
    with pytest.raises(AuthenticationError):
        service.control_capabilities(cid, secret)


def test_revoke_credential_confirmation_denial_is_durably_audited() -> None:
    service, backend, cid, secret = _bootstrapped()
    before = len(backend.audit_sink.snapshot())
    with pytest.raises(DestructiveConfirmationRequired):
        service.revoke_credential(cid, secret, cid)
    after = backend.audit_sink.snapshot()
    assert len(after) == before + 1
    assert after[-1].reason_code == "DESTRUCTIVE_CONFIRMATION_REQUIRED"


def test_enable_credential_never_resurrects_a_revoked_credential() -> None:
    service, _backend, cid, secret = _bootstrapped()
    service.register_application(cid, secret, "unrevokeable")
    issued = service.issue_credential(cid, secret, "unrevokeable", "runtime")
    service.revoke_credential(cid, secret, issued["credential_id"])
    state = service.set_credential_enabled(cid, secret, issued["credential_id"], True)
    assert state["revoked"] is True
    # Still cannot rotate (store-level gate proves it is actually dead).
    with pytest.raises(ValidationError):
        service.rotate_credential(cid, secret, issued["credential_id"])


def test_set_credential_enabled_result_matches_schema_exactly() -> None:
    service, _backend, cid, secret = _bootstrapped()
    service.register_application(cid, secret, "toggleapp")
    issued = service.issue_credential(cid, secret, "toggleapp", "runtime")
    disabled = service.set_credential_enabled(cid, secret, issued["credential_id"], False)
    _assert_schema_exact("CredentialStateResult", disabled)
    assert disabled == {"credential_id": issued["credential_id"], "enabled": False, "revoked": False}


# --------------------------------------------------------------------------
# control_capabilities: schema-exact, request_bytes declared unavailable at
# the service layer (R-7 -- the HTTP layer, WP-5, flips it to enforced).
# --------------------------------------------------------------------------


def test_control_capabilities_result_matches_schema_exactly_and_declares_request_bytes() -> None:
    service, _backend, cid, secret = _bootstrapped()
    result = service.control_capabilities(cid, secret)
    _assert_schema_exact("CapabilityDocument", result)
    assert "request_bytes" in result["limits"]
    assert result["limit_enforcement"]["request_bytes"] == "unavailable"
    assert result["limit_enforcement"]["applications"] == "enforced"


# --------------------------------------------------------------------------
# R-6 same-transaction guarantee: a fault in the durable audit write rolls
# the accompanying state change back too (mutation-injection completion
# condition #1 -- "同一tx監査を分離する" would otherwise pass unnoticed).
# --------------------------------------------------------------------------


def test_audit_write_fault_rolls_back_an_accompanying_application_registration() -> None:
    service, backend, cid, secret = _bootstrapped()
    backend.audit_sink.inject_fault(RuntimeError("simulated durable-audit outage"))
    try:
        with pytest.raises(Exception):
            service.register_application(cid, secret, "shouldnotexist")
    finally:
        backend.audit_sink.inject_fault(None)
    # The application row must NOT exist -- if it did, the audit write and
    # the state change would have detached from each other.
    assert backend.application_exists("shouldnotexist") is False
    # A retry (audit healthy again) succeeds normally.
    result = service.register_application(cid, secret, "shouldnotexist")
    assert result["enabled"] is True


def test_audit_write_fault_rolls_back_an_accompanying_credential_revoke() -> None:
    service, backend, cid, secret = _bootstrapped()
    service.register_application(cid, secret, "faultapp")
    issued = service.issue_credential(cid, secret, "faultapp", "runtime")

    backend.audit_sink.inject_fault(RuntimeError("simulated durable-audit outage"))
    try:
        with pytest.raises(Exception):
            service.revoke_credential(cid, secret, issued["credential_id"])
    finally:
        backend.audit_sink.inject_fault(None)
    # The credential must still be usable (revoke never durably happened) --
    # observed through the store's own state, not through re-authenticating
    # (this is an application credential, not exercised by control auth).
    enabled, revoked = backend.credential_state(issued["credential_id"])
    assert revoked is False, "a fault-injected audit write must roll the state change back, not detach from it"


def test_audit_write_fault_rolls_back_the_reset_ceremony_atomically() -> None:
    from mitatedb_api.control_plane import reset_control_credentials

    backend = InMemoryControlBackend(app_pepper=_APP_PEPPER, control_pepper=_CONTROL_PEPPER)
    with backend.unit_of_work() as work:
        cid, secret = bootstrap_control_credential(backend.control_credential_store, backend.append_audit, work=work)

    rows = backend.control_credential_store.list_all()
    phrase_active = [row[0] for row in rows if row[1] and not row[2]]
    from mitatedb_api.control_plane import _reset_confirmation_phrase
    phrase = _reset_confirmation_phrase(phrase_active)

    backend.audit_sink.inject_fault(RuntimeError("simulated durable-audit outage"))
    try:
        with pytest.raises(Exception):
            with backend.unit_of_work() as work:
                reset_control_credentials(backend.control_credential_store, backend.append_audit, work=work,
                                          destructive=True, confirmation=phrase)
    finally:
        backend.audit_sink.inject_fault(None)

    # The original credential must still authenticate -- the revoke_all +
    # issue pair rolled back together with the failed audit write, not
    # partially applied.
    service = ControlPlaneService(backend)
    result = service.control_capabilities(cid, secret)
    assert result["role"] == "control"


# --------------------------------------------------------------------------
# Reviewer m-2: `control_audit.CONTROL_AUDIT_FIELDS` must be exactly the
# contract's own `audit.fields` -- 12 columns, no more, no fewer. Existing
# tests only ever read the in-memory `ControlAuditEvent` dataclass directly
# (which has its own, independent 12 fields spelled out in its own
# definition) or construct rows by keyword, so a field silently dropped
# from this tuple was previously invisible: it is used ONLY as the SELECT
# projection list in `control_audit.read_control_audit_events` -- the R-8
# reader WP-5's own C-15 will depend on to observe audit evidence at all.
#
# B-1 measure (Phase 3.5 WP-1, design docs/design/
# PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md §1-G "B-1 措置", P35-D14;
# CCR_DISPOSITION.md subordinate ruling 8): contract 1.3.0 adds `target_id`
# to `audit.fields` (13 fields), while `CONTROL_AUDIT_FIELDS` itself is
# unchanged in this WP (exposing it is WP-5's own §4 "target_id" work item,
# a peer src/ change this WP is not permitted to make). The exact-set-
# equality form below would therefore go red for a reason that has nothing
# to do with a real regression in this file's own subject matter. Loosened
# to inclusion -- the original 12-field literal (frozen here, independent of
# `CONTROL_AUDIT_FIELDS` itself, so this guard cannot be satisfied by
# shrinking that tuple) must be a subset of `CONTROL_AUDIT_FIELDS`, which in
# turn must be a subset of the contract's current `audit.fields` -- as an
# explicit, single-peer, test-only exception to the usual single-commit
# discipline (behavior unchanged). WP-5 restores 13-field exact equality
# once `target_id` is actually populated and exposed by this peer.
# --------------------------------------------------------------------------

_ORIGINAL_TWELVE_CONTROL_AUDIT_FIELDS = frozenset({
    "event_id", "event_class", "occurred_at", "request_id", "application_id",
    "actor_type", "actor_id", "role", "operation", "target_kind", "outcome",
    "reason_code",
})


# n-2: this test's NAME is deliberately retained as-is (still says "_exactly")
# even though the body below is the loosened inclusion form -- WP-5 restores
# real set-equality in this same function, so keeping the name stable across
# both WPs keeps `git log`/`grep` on this identifier meaningful throughout.
def test_control_audit_fields_matches_the_contract_audit_fields_exactly() -> None:
    from mitatedb_api.control_audit import CONTROL_AUDIT_FIELDS

    contract_fields = tuple(_SPEC["audit"]["fields"])
    # Reviewer m-2: `len(...) >= 12` is already implied by the frozenset
    # subset check below (12 known-distinct literals <= CONTROL_AUDIT_FIELDS
    # forces at least 12 members); a bare `>= 12` count therefore added no
    # coverage the subset check didn't already have. A uniqueness check does
    # add coverage the old `len(...) == 12` used to provide incidentally (a
    # duplicated field name would satisfy both the subset check and a bare
    # length check while still being a real defect in this tuple).
    assert len(set(CONTROL_AUDIT_FIELDS)) == len(CONTROL_AUDIT_FIELDS), (
        f"control_audit.CONTROL_AUDIT_FIELDS {CONTROL_AUDIT_FIELDS} contains a duplicate field name"
    )
    assert _ORIGINAL_TWELVE_CONTROL_AUDIT_FIELDS <= set(CONTROL_AUDIT_FIELDS) <= set(contract_fields), (
        f"control_audit.CONTROL_AUDIT_FIELDS {sorted(CONTROL_AUDIT_FIELDS)} must retain the original 12 "
        f"core fields {sorted(_ORIGINAL_TWELVE_CONTROL_AUDIT_FIELDS)} and remain a subset of contract "
        f"audit.fields {sorted(contract_fields)} -- a dropped/renamed core field, or a field this peer "
        f"emits that the contract does not declare, silently corrupts every row "
        f"`read_control_audit_events` (R-8's own reader) ever returns"
    )
