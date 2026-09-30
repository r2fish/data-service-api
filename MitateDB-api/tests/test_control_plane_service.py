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

from mitatedb_api.control_plane import (_AUDIT_ROLE_ALLOWED_OPERATIONS, ControlPlaneLimits,
                                        ControlPlaneService, InMemoryControlBackend,
                                        bootstrap_control_credential,
                                        issue_audit_credential_ceremony)
from mitatedb_api.credential_wire import split_bearer_locator
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
        credential_id, bearer = bootstrap_control_credential(backend.control_credential_store, backend.append_audit, work=work)
    # Phase 6 WP-3 追補, round 2 (supervisor ruling 2026-09-04, corrected
    # after empirical finding): `control_auth.ControlCredentialStore.
    # authenticate` takes the RAW secret only now (it can also be reached
    # via a real HTTP boundary that always pre-splits, `tests/test_
    # control_http_unmounted.py`'s own topology) -- this file's own
    # helper is a direct in-process `ControlPlaneService` caller, so it
    # splits the COMPOSED bearer ONCE here, the same discipline every
    # other real receiving boundary on this peer now follows.
    secret = bearer
    service = ControlPlaneService(backend, limits=limits or _limits())
    # Clear must_rotate via self-rotate so ordinary tests do not have to
    # thread the must_rotate allow-list through every call site.
    rotated = service.rotate_credential(secret, credential_id)
    rotated_secret = rotated["secret"]
    return service, backend, credential_id, rotated_secret


# --------------------------------------------------------------------------
# Bounds numeric constraints (R-6 / WP-0 M-5).
# --------------------------------------------------------------------------


# Phase 5 D-3 (Q3 案A, WP-4): the former [1, 200] ceiling on all four
# request-count classes is removed -- `ControlPlaneLimits.__post_init__`
# now checks only "positive integer" (symmetric with r2db-api's own
# `ControlPlaneLimits`, r2db-api/src/r2db_api/limits.py:140-143). The
# `201`-valued cases this parametrize used to carry are gone: `201` is now
# an ordinary accepted value, not a rejection case. The lower-bound (`0`)
# cases are kept and widened to all FOUR classes (the pre-Phase-5 list only
# covered 3 -- `audit_requests_per_minute`'s own lower bound had never been
# exercised here). `match=` pins the exact post-removal error text so a
# reintroduction of the old "[1, 200]" wording (which would now describe a
# nonexistent ceiling) is caught here, not just by a passing/failing count.
@pytest.mark.parametrize("field,value", [
    ("applications", 0),
    ("credentials_per_application", 0),
    ("control_requests_per_minute", 0),
    ("audit_requests_per_minute", 0),
])
def test_limits_reject_out_of_range_values(field, value) -> None:
    kwargs = dict(applications=5, credentials_per_application=2, control_requests_per_minute=90,
                   audit_requests_per_minute=60)
    kwargs[field] = value
    with pytest.raises(ValueError, match="must be a positive integer"):
        ControlPlaneLimits(**kwargs)


def test_limits_reject_control_requests_per_minute_too_close_to_the_margin() -> None:
    # applications=5, credentials_per_application=2 -> the floor is 5+4+67=76;
    # 76 itself (not exceeding it) must be rejected. Unaffected by the
    # ceiling removal above -- this relational check is independent of it.
    with pytest.raises(ValueError):
        ControlPlaneLimits(applications=5, credentials_per_application=2, control_requests_per_minute=76)
    ControlPlaneLimits(applications=5, credentials_per_application=2, control_requests_per_minute=77)


def test_limits_accept_generous_values_beyond_the_former_ceiling() -> None:
    # Same shape as r2db-api's own `_GENEROUS_LIMITS`
    # (r2db-api/tests/test_control_http.py:57: applications=1_000,
    # credentials_per_application=1_000, control_requests_per_minute=
    # 100_000; r2db-api/tests/test_audit_query.py's own module-level
    # `_GENEROUS_LIMITS` additionally sets audit_requests_per_minute=
    # 100_000, the 4th class, to the same scale) -- scaled well past the
    # removed 200 ceiling on ALL FOUR request-count classes, and satisfying
    # the still-enforced margin inequality (control_requests_per_minute >
    # applications + 2*credentials_per_application + 67).
    # `audit_requests_per_minute` is independent of that inequality (it is
    # never a term in it), so it is included here explicitly rather than
    # relying on the 3-field version above to stand in for the 4th class.
    # Construction succeeding is the positive half of this WP's proof;
    # `test_limits_reject_out_of_range_values` above only proves the LOWER
    # bound survives, not that the ceiling is actually gone -- that
    # requires an accepted value the old [1, 200] range would have
    # rejected, for EVERY class the old range covered.
    limits = ControlPlaneLimits(
        applications=1_000,
        credentials_per_application=1_000,
        control_requests_per_minute=100_000,
        audit_requests_per_minute=100_000,
    )
    assert limits.applications == 1_000
    assert limits.credentials_per_application == 1_000
    assert limits.control_requests_per_minute == 100_000
    assert limits.audit_requests_per_minute == 100_000
    # The accepted value is declared as-is, not silently clamped --
    # `as_dict()` is the same structure `control_capabilities()` publishes.
    declared = limits.as_dict()
    assert declared["applications"] == 1_000
    assert declared["credentials_per_application"] == 1_000
    assert declared["control_requests_per_minute"] == 100_000
    assert declared["audit_requests_per_minute"] == 100_000


# --------------------------------------------------------------------------
# Authentication: AUTH_REQUIRED vs AUTH_INVALID, AUTH_STATE_UNAVAILABLE
# exemption from durable audit.
# --------------------------------------------------------------------------


def test_missing_credential_raises_auth_required_and_is_durably_recorded() -> None:
    service, backend, _cid, _secret = _bootstrapped()
    before = len(backend.audit_sink.snapshot())
    with pytest.raises(AuthenticationRequiredError):
        service.control_capabilities(None)
    after = backend.audit_sink.snapshot()
    assert len(after) == before + 1
    assert after[-1].reason_code == "AUTH_REQUIRED"
    assert after[-1].outcome == "deny"


def test_wrong_secret_raises_auth_invalid_and_is_durably_recorded() -> None:
    service, backend, cid, _secret = _bootstrapped()
    before = len(backend.audit_sink.snapshot())
    with pytest.raises(AuthenticationError):
        service.control_capabilities("not-the-real-secret")
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

        def authenticate_control(self, secret):
            raise AuthorizationStateUnavailable("simulated store outage")

    service._backend = _DeadBackend()
    before = len(backend.audit_sink.snapshot())
    with pytest.raises(AuthorizationStateUnavailable):
        service.control_capabilities(secret)
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
            service.control_capabilities(None)
    before = len(backend.audit_sink.snapshot())
    with pytest.raises(ResourceLimitError) as excinfo:
        service.control_capabilities(None)
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
            service.control_capabilities(None)
    with pytest.raises(ResourceLimitError):
        service.control_capabilities(None)

    # Advance the injected clock by 61 seconds -- every one of the 77
    # earlier timestamps must now have aged out of the window.
    fake_now[0] += 61.0
    with pytest.raises(AuthenticationRequiredError):
        # Not a ResourceLimitError: the window recovered, so this request
        # is charged successfully and fails only on the (still-missing)
        # credential, exactly as the very first call of this test did.
        service.control_capabilities(None)


# --------------------------------------------------------------------------
# must_rotate gate (FORBIDDEN, allow-list, self-rotate exception).
# --------------------------------------------------------------------------


def test_must_rotate_forbids_every_operation_except_capabilities_and_self_rotate() -> None:
    backend = InMemoryControlBackend(app_pepper=_APP_PEPPER, control_pepper=_CONTROL_PEPPER)
    with backend.unit_of_work() as work:
        cid, bearer = bootstrap_control_credential(backend.control_credential_store, backend.append_audit, work=work)
    secret = bearer
    service = ControlPlaneService(backend, limits=_limits())

    # Allowed while must_rotate:
    service.control_capabilities(secret)

    # Forbidden while must_rotate:
    with pytest.raises(AuthorizationError):
        service.register_application(secret, "someapp")
    with pytest.raises(AuthorizationError):
        service.list_applications(secret)

    # Self-rotate is allowed and clears must_rotate.
    rotated = service.rotate_credential(secret, cid)
    new_secret = rotated["secret"]
    service.register_application(new_secret, "someapp")  # no longer forbidden


def test_must_rotate_forbidden_is_durably_audited_with_reason_forbidden() -> None:
    backend = InMemoryControlBackend(app_pepper=_APP_PEPPER, control_pepper=_CONTROL_PEPPER)
    with backend.unit_of_work() as work:
        cid, bearer = bootstrap_control_credential(backend.control_credential_store, backend.append_audit, work=work)
    secret = bearer
    service = ControlPlaneService(backend, limits=_limits())
    with pytest.raises(AuthorizationError):
        service.list_applications(secret)
    last = backend.audit_sink.snapshot()[-1]
    assert last.reason_code == "FORBIDDEN"
    assert last.outcome == "deny"


# --------------------------------------------------------------------------
# register_application / list_applications / enable / disable.
# --------------------------------------------------------------------------


def test_register_application_result_matches_schema_exactly() -> None:
    service, _backend, cid, secret = _bootstrapped()
    result = service.register_application(secret, "shopapp")
    _assert_schema_exact("ApplicationStateResult", result)
    assert result == {"application_id": "shopapp", "enabled": True}


def test_register_application_rejects_bad_identifier_shape() -> None:
    service, _backend, cid, secret = _bootstrapped()
    with pytest.raises(ValidationError):
        service.register_application(secret, "NotLowercase")
    with pytest.raises(ValidationError):
        service.register_application(secret, "")


def test_register_application_duplicate_is_conflict() -> None:
    service, _backend, cid, secret = _bootstrapped()
    service.register_application(secret, "dupapp")
    with pytest.raises(ConflictError):
        service.register_application(secret, "dupapp")


def test_register_application_enforces_the_applications_bound() -> None:
    service, _backend, cid, secret = _bootstrapped(limits=_limits(applications=2))
    service.register_application(secret, "app1")
    service.register_application(secret, "app2")
    with pytest.raises(ResourceLimitError) as excinfo:
        service.register_application(secret, "app3")
    assert excinfo.value.details["limit_class"] == "applications"


def test_list_applications_and_enable_disable_round_trip() -> None:
    service, _backend, cid, secret = _bootstrapped()
    service.register_application(secret, "toggled")
    listing = service.list_applications(secret)
    _assert_schema_exact("ApplicationsResult", listing)
    for item in listing["applications"]:
        _assert_schema_exact_item("ApplicationsResult", item)
    disabled = service.set_application_enabled(secret, "toggled", False)
    assert disabled == {"application_id": "toggled", "enabled": False}
    enabled = service.set_application_enabled(secret, "toggled", True)
    assert enabled == {"application_id": "toggled", "enabled": True}


def test_set_application_enabled_unknown_application_is_not_found() -> None:
    service, _backend, cid, secret = _bootstrapped()
    with pytest.raises(NotFoundError):
        service.set_application_enabled(secret, "nope", False)


# --------------------------------------------------------------------------
# issue_credential: role=control refusal precedes target resolution
# (C-14 vector-3 style), shape-before-capability, bounds.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("application_id", ["ghostapp99", "disabledapp", "fullapp"])
def test_role_control_is_refused_uniformly_regardless_of_target_state(application_id) -> None:
    service, _backend, cid, secret = _bootstrapped(limits=_limits(credentials_per_application=1))
    if application_id == "disabledapp":
        service.register_application(secret, application_id)
        service.set_application_enabled(secret, application_id, False)
    elif application_id == "fullapp":
        service.register_application(secret, application_id)
        service.issue_credential(secret, application_id, "runtime")  # saturates the bound (limit=1)
    # "does-not-exist" is registered nowhere at all.
    with pytest.raises(CapabilityError):
        service.issue_credential(secret, application_id, "control")


def test_issue_credential_role_shape_is_validated_before_capability_check() -> None:
    service, _backend, cid, secret = _bootstrapped()
    with pytest.raises(ValidationError):
        service.issue_credential(secret, "someapp", "not-a-real-role")


def test_issue_credential_result_matches_schema_exactly() -> None:
    service, _backend, cid, secret = _bootstrapped()
    service.register_application(secret, "issuertest")
    result = service.issue_credential(secret, "issuertest", "runtime")
    _assert_schema_exact("CredentialIssued", result)
    assert result["role"] == "runtime"


def test_issue_credential_enforces_credentials_per_application_bound_excluding_revoked() -> None:
    service, _backend, cid, secret = _bootstrapped(limits=_limits(credentials_per_application=1))
    service.register_application(secret, "boundedapp")
    first = service.issue_credential(secret, "boundedapp", "runtime")
    with pytest.raises(ResourceLimitError) as excinfo:
        service.issue_credential(secret, "boundedapp", "runtime")
    assert excinfo.value.details["limit_class"] == "credentials_per_application"
    # R-6: revoked rows are NOT counted -- revoking the one existing
    # credential must free up headroom for a new one.
    service.revoke_credential(secret, first["credential_id"])
    second = service.issue_credential(secret, "boundedapp", "runtime")
    assert second["credential_id"] != first["credential_id"]


def test_issue_credential_unknown_application_is_not_found() -> None:
    service, _backend, cid, secret = _bootstrapped()
    with pytest.raises(NotFoundError):
        service.issue_credential(secret, "ghostapp", "runtime")


# --------------------------------------------------------------------------
# list_credentials: merged listing, control rows have no application_id and
# no must_rotate key, schema-exact.
# --------------------------------------------------------------------------


def test_list_credentials_merges_application_and_control_rows() -> None:
    service, backend, cid, secret = _bootstrapped()
    service.register_application(secret, "listedapp")
    issued = service.issue_credential(secret, "listedapp", "runtime")

    listing = service.list_credentials(secret)
    _assert_schema_exact("CredentialsResult", listing)
    by_id = {row["credential_id"]: row for row in listing["credentials"]}
    for row in listing["credentials"]:
        _assert_schema_exact_item("CredentialsResult", row)

    app_row = by_id[issued["credential_id"]]
    assert app_row["role"] == "runtime"
    assert app_row["application_id"] == "listedapp"
    # Phase 3.5 WP-5 (§1-B/§4, P35-D7): application-credential rows never
    # carry `must_rotate` at all -- the concept does not exist for them.
    assert "must_rotate" not in app_row

    # Phase 3.5 WP-5 (§1-B/§4, P35-D7 reversal of the original §8 m-9): a
    # control-table row's `must_rotate` IS now exposed, with its real value
    # -- this credential was just bootstrapped and self-rotated by
    # `_bootstrapped()` (see that helper), so `must_rotate` is `False` here.
    control_row = by_id[cid]
    assert control_row["role"] == "control"
    assert "application_id" not in control_row
    assert control_row["must_rotate"] is False


# --------------------------------------------------------------------------
# rotate_credential: self-rotate while must_rotate, revoked cannot rotate.
# --------------------------------------------------------------------------


def test_rotate_credential_refuses_a_revoked_credential() -> None:
    # O-8 (版フリップ監査, ruling `{scratchpad}/rulings-r3-r7-flip.md`
    # 追補4): a state conflict (target contradicts the requested
    # operation), not a ValidationError shoehorned into the 11-word
    # vocabulary -- matches r2db-api's own same-site fix (CONFLICT).
    service, _backend, cid, secret = _bootstrapped()
    service.register_application(secret, "rotapp")
    issued = service.issue_credential(secret, "rotapp", "runtime")
    service.revoke_credential(secret, issued["credential_id"])
    with pytest.raises(ConflictError):
        service.rotate_credential(secret, issued["credential_id"])


def test_rotate_credential_result_matches_schema_exactly() -> None:
    service, _backend, cid, secret = _bootstrapped()
    service.register_application(secret, "rotapp2")
    issued = service.issue_credential(secret, "rotapp2", "runtime")
    result = service.rotate_credential(secret, issued["credential_id"])
    _assert_schema_exact("CredentialRotated", result)


# --------------------------------------------------------------------------
# revoke_credential: declare-and-echo for the last active control
# credential ONLY; ordinary revokes are never gated; un-revoke absence.
# --------------------------------------------------------------------------


def test_revoke_application_credential_is_never_gated() -> None:
    service, _backend, cid, secret = _bootstrapped()
    service.register_application(secret, "ungated")
    issued = service.issue_credential(secret, "ungated", "runtime")
    result = service.revoke_credential(secret, issued["credential_id"])
    _assert_schema_exact("CredentialStateResult", result)
    assert result["revoked"] is True


def test_revoke_last_active_control_credential_requires_exact_confirmation() -> None:
    service, backend, cid, secret = _bootstrapped()
    with pytest.raises(DestructiveConfirmationRequired) as excinfo:
        service.revoke_credential(secret, cid)
    details = excinfo.value.details
    for key in ("required_confirmation", "consequence", "reversible_alternative", "recovery"):
        assert key in details

    # A well-shaped but non-matching confirmation must NOT satisfy the gate
    # (no prefix/substring acceptance).
    with pytest.raises(DestructiveConfirmationRequired):
        service.revoke_credential(secret, cid, destructive=True, confirmation="yes")
    with pytest.raises(DestructiveConfirmationRequired):
        service.revoke_credential(secret, cid, destructive=True,
                                  confirmation=details["required_confirmation"][:-1])
    # A non-bool `destructive` (even a truthy-looking string) is a SHAPE
    # defect, not a confirmation mismatch -- rejected before the
    # confirmation comparison is even reached (no truthy coercion anywhere
    # in this gate).
    with pytest.raises(ValidationError):
        service.revoke_credential(secret, cid, destructive="true", confirmation=details["required_confirmation"])

    result = service.revoke_credential(secret, cid, destructive=True, confirmation=details["required_confirmation"])
    assert result["revoked"] is True

    # Authentication now fails -- no un-revoke path exists anywhere.
    with pytest.raises(AuthenticationError):
        service.control_capabilities(secret)


def test_revoke_credential_confirmation_denial_is_durably_audited() -> None:
    service, backend, cid, secret = _bootstrapped()
    before = len(backend.audit_sink.snapshot())
    with pytest.raises(DestructiveConfirmationRequired):
        service.revoke_credential(secret, cid)
    after = backend.audit_sink.snapshot()
    assert len(after) == before + 1
    assert after[-1].reason_code == "DESTRUCTIVE_CONFIRMATION_REQUIRED"


def test_enable_credential_never_resurrects_a_revoked_credential() -> None:
    service, _backend, cid, secret = _bootstrapped()
    service.register_application(secret, "unrevokeable")
    issued = service.issue_credential(secret, "unrevokeable", "runtime")
    service.revoke_credential(secret, issued["credential_id"])
    state = service.set_credential_enabled(secret, issued["credential_id"], True)
    assert state["revoked"] is True
    # Still cannot rotate (store-level gate proves it is actually dead).
    # O-8: CONFLICT, not ValidationError (see test_rotate_credential_
    # refuses_a_revoked_credential above).
    with pytest.raises(ConflictError):
        service.rotate_credential(secret, issued["credential_id"])


def test_set_credential_enabled_result_matches_schema_exactly() -> None:
    service, _backend, cid, secret = _bootstrapped()
    service.register_application(secret, "toggleapp")
    issued = service.issue_credential(secret, "toggleapp", "runtime")
    disabled = service.set_credential_enabled(secret, issued["credential_id"], False)
    _assert_schema_exact("CredentialStateResult", disabled)
    assert disabled == {"credential_id": issued["credential_id"], "enabled": False, "revoked": False}


# --------------------------------------------------------------------------
# control_capabilities: schema-exact, request_bytes declared unavailable at
# the service layer (R-7 -- the HTTP layer, WP-5, flips it to enforced).
# --------------------------------------------------------------------------


def test_control_capabilities_result_matches_schema_exactly_and_declares_request_bytes() -> None:
    service, _backend, cid, secret = _bootstrapped()
    result = service.control_capabilities(secret)
    _assert_schema_exact("CapabilityDocument", result)
    assert "request_bytes" in result["limits"]
    assert result["limit_enforcement"]["request_bytes"] == "unavailable"
    assert result["limit_enforcement"]["applications"] == "enforced"
    # Phase 4 WP-3(b): this WP ships the 1.4.0 obligations for this peer's
    # control plane, so the flip lands in this same commit as the audit_
    # query bundle it accompanies. Phase 5 WP-3: re-flipped to 1.5.0 in the
    # same commit as the `operations`/`target_kinds` declaration keys.
    # Phase 10 WP-6b/pair-closing: re-flipped again to 1.8.0 in the same
    # commit as this host's own `process_ceilings` mapping (design D-5
    # (v)).
    assert result["contract_version"] == "1.13.0"
    assert result["role"] == "control"


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
            service.register_application(secret, "shouldnotexist")
    finally:
        backend.audit_sink.inject_fault(None)
    # The application row must NOT exist -- if it did, the audit write and
    # the state change would have detached from each other.
    assert backend.application_exists("shouldnotexist") is False
    # A retry (audit healthy again) succeeds normally.
    result = service.register_application(secret, "shouldnotexist")
    assert result["enabled"] is True


def test_audit_write_fault_rolls_back_an_accompanying_credential_revoke() -> None:
    service, backend, cid, secret = _bootstrapped()
    service.register_application(secret, "faultapp")
    issued = service.issue_credential(secret, "faultapp", "runtime")

    backend.audit_sink.inject_fault(RuntimeError("simulated durable-audit outage"))
    try:
        with pytest.raises(Exception):
            service.revoke_credential(secret, issued["credential_id"])
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
        cid, bearer = bootstrap_control_credential(backend.control_credential_store, backend.append_audit, work=work)
    secret = bearer
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
    result = service.control_capabilities(secret)
    assert result["role"] == "control"


# --------------------------------------------------------------------------
# Reviewer m-2: `control_audit.CONTROL_AUDIT_FIELDS` must be exactly the
# contract's own `audit.fields` -- 13 columns (as of contract 1.3.0's
# `target_id` addition), no more, no fewer. Existing tests only ever read
# the in-memory `ControlAuditEvent` dataclass directly (which has its own,
# independent 13 fields spelled out in its own definition) or construct
# rows by keyword, so a field silently dropped from this tuple was
# previously invisible: it is used ONLY as the SELECT projection list in
# `control_audit.read_control_audit_events` -- the R-8 reader C-15 depends
# on to observe audit evidence at all.
#
# B-1 measure (Phase 3.5 WP-1, design docs/design/
# PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md §1-G "B-1 措置", P35-D14;
# CCR_DISPOSITION.md subordinate ruling 8): WP-1 loosened this test from
# exact set equality to inclusion, because contract 1.3.0's `target_id`
# addition would otherwise go red here for a reason unrelated to this
# file's own subject matter (exposing `target_id` was WP-5's own §4 work
# item, a peer src/ change WP-1 was not permitted to make). Phase 3.5 WP-5
# (this WP) restores exact set equality now that `target_id` is actually
# populated and exposed by `CONTROL_AUDIT_FIELDS` -- this closes the loop
# P35-D14 opened.
# --------------------------------------------------------------------------

_CONTRACT_AUDIT_FIELDS_AT_1_3_0 = frozenset({
    "event_id", "event_class", "occurred_at", "request_id", "application_id",
    "actor_type", "actor_id", "role", "operation", "target_kind", "outcome",
    "reason_code", "target_id",
})


def test_control_audit_fields_matches_the_contract_audit_fields_exactly() -> None:
    from mitatedb_api.control_audit import CONTROL_AUDIT_FIELDS

    contract_fields = tuple(_SPEC["audit"]["fields"])
    # A uniqueness check adds coverage a bare `len(...) == 13` would not (a
    # duplicated field name could otherwise satisfy a length check while
    # still being a real defect in this tuple).
    assert len(set(CONTROL_AUDIT_FIELDS)) == len(CONTROL_AUDIT_FIELDS), (
        f"control_audit.CONTROL_AUDIT_FIELDS {CONTROL_AUDIT_FIELDS} contains a duplicate field name"
    )
    assert set(CONTROL_AUDIT_FIELDS) == set(contract_fields) == _CONTRACT_AUDIT_FIELDS_AT_1_3_0, (
        f"control_audit.CONTROL_AUDIT_FIELDS {sorted(CONTROL_AUDIT_FIELDS)} must be exactly contract "
        f"audit.fields {sorted(contract_fields)} -- a dropped/renamed/added field on either side silently "
        f"corrupts every row `read_control_audit_events` (R-8's own reader) ever returns"
    )


# ===========================================================================
# Phase 3.5 WP-5 control-plane bundle (design docs/design/
# PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md §4) -- target_id on lifecycle
# events (§1-C), audit-role authorization (§1-D), per-application issuance
# freeze (§1-E), the audit-credential ceremony, and the revoke-gate role
# filter. must_rotate exposure (§1-B) is covered above (Section 6's
# `test_list_credentials_merges_application_and_control_rows`).
# ===========================================================================


def _seed_audit_credential(backend, *, must_rotate: bool = False):
    """Issues a `role="audit"` control-table credential directly against
    this backend's own store -- the same shape `issue_audit_credential_
    ceremony` uses internally, without going through the CLI. Returns
    `(credential_id, secret)` -- the RAW secret (Phase 6 WP-3 追補, round
    2: `.issue()` returns a COMPOSED bearer; this helper's own callers
    pass the result straight into direct `ControlPlaneService` calls)."""
    store = backend.control_credential_store
    with backend.unit_of_work() as work:
        credential_id, bearer = store.issue(must_rotate=must_rotate, role="audit", work=work)
    secret = bearer
    return credential_id, secret


def test_target_id_populated_for_application_and_credential_lifecycle_events() -> None:
    """design §1-C/§4: `target_id` on the durable audit row -- the single
    target credential_id/application_id a lifecycle event acted on --
    populated for register/enable/disable-application and
    issue/rotate/revoke/enable/disable-credential."""
    service, backend, cid, secret = _bootstrapped()
    app_id = "tidapp"

    service.register_application(secret, app_id)
    assert backend.audit_sink.snapshot()[-1].target_id == app_id

    service.set_application_enabled(secret, app_id, False)
    assert backend.audit_sink.snapshot()[-1].target_id == app_id
    service.set_application_enabled(secret, app_id, True)
    assert backend.audit_sink.snapshot()[-1].target_id == app_id

    issued = service.issue_credential(secret, app_id, "runtime")
    app_cred_id = issued["credential_id"]
    assert backend.audit_sink.snapshot()[-1].target_id == app_cred_id

    service.rotate_credential(secret, app_cred_id)
    assert backend.audit_sink.snapshot()[-1].target_id == app_cred_id

    service.set_credential_enabled(secret, app_cred_id, False)
    assert backend.audit_sink.snapshot()[-1].target_id == app_cred_id

    service.revoke_credential(secret, app_cred_id)
    assert backend.audit_sink.snapshot()[-1].target_id == app_cred_id


def test_target_id_populated_for_control_credential_lifecycle_events() -> None:
    service, backend, cid, secret = _bootstrapped()
    other_id, other_secret = _seed_audit_credential(backend, must_rotate=False)

    service.rotate_credential(secret, other_id)
    assert backend.audit_sink.snapshot()[-1].target_id == other_id

    service.set_credential_enabled(secret, other_id, False)
    assert backend.audit_sink.snapshot()[-1].target_id == other_id

    service.revoke_credential(secret, other_id)
    assert backend.audit_sink.snapshot()[-1].target_id == other_id


def test_target_id_populated_on_bootstrap_and_reset() -> None:
    from mitatedb_api.control_plane import reset_control_credentials, _reset_confirmation_phrase

    backend = InMemoryControlBackend(app_pepper=_APP_PEPPER, control_pepper=_CONTROL_PEPPER)
    with backend.unit_of_work() as work:
        credential_id, _secret = bootstrap_control_credential(
            backend.control_credential_store, backend.append_audit, work=work)
    assert backend.audit_sink.snapshot()[-1].target_id == credential_id

    phrase = _reset_confirmation_phrase([credential_id])
    with backend.unit_of_work() as work:
        new_id, _new_secret = reset_control_credentials(
            backend.control_credential_store, backend.append_audit, work=work,
            destructive=True, confirmation=phrase)
    assert backend.audit_sink.snapshot()[-1].target_id == new_id


# --------------------------------------------------------------------------
# audit-role authorization (§1-D): accepted on exactly the 3 read-only
# endpoints, FORBIDDEN + durably audited on every other one.
# --------------------------------------------------------------------------


def test_audit_role_accepted_on_exactly_the_three_read_endpoints() -> None:
    service, backend, _cid, _secret = _bootstrapped()
    audit_id, audit_secret = _seed_audit_credential(backend, must_rotate=False)

    caps = service.control_capabilities(audit_secret)
    assert caps["role"] == "audit"

    apps = service.list_applications(audit_secret)
    assert isinstance(apps["applications"], list)

    creds = service.list_credentials(audit_secret)
    assert any(row["credential_id"] == audit_id and row["role"] == "audit" for row in creds["credentials"])


def test_audit_role_forbidden_fail_closed_on_every_other_control_endpoint() -> None:
    """design §1-D/§4 (contract `control_plane.authority`): every non-read
    control endpoint must refuse an `audit`-role principal with
    `AuthorizationError` (`FORBIDDEN`), durably audited -- exercised here
    against all 8 non-read operations at the service layer.

    This loop's own `attempts` dict is a hand-maintained enumeration, NOT
    structurally complete on its own -- the actual structural-completeness
    guarantee (a future operation fails the test until explicitly
    classified, never silently skipped) lives in `test_control_http_
    unmounted.py`'s own matrix test, which derives its enumeration from
    `control_http._ROUTES` (the real wire route table) and asserts set-
    equality against it. This test remains useful alongside that one for
    exercising the SERVICE layer directly, independent of any HTTP binding.
    """
    service, backend, owner_id, owner_secret = _bootstrapped()
    audit_id, audit_secret = _seed_audit_credential(backend, must_rotate=False)

    app_id = "auditwriteapp"
    service.register_application(owner_secret, app_id)
    issued = service.issue_credential(owner_secret, app_id, "runtime")
    cred_id = issued["credential_id"]

    attempts = {
        "register_application": lambda: service.register_application(audit_secret, "auditwriteapp2"),
        "disable_application": lambda: service.set_application_enabled(audit_secret, app_id, False),
        "enable_application": lambda: service.set_application_enabled(audit_secret, app_id, True),
        "issue_credential": lambda: service.issue_credential(audit_secret, app_id, "runtime"),
        "rotate_credential (other)": lambda: service.rotate_credential(audit_secret, cred_id),
        "rotate_credential (self)": lambda: service.rotate_credential(audit_secret, audit_id),
        "revoke_credential": lambda: service.revoke_credential(audit_secret, cred_id),
        "disable_credential": lambda: service.set_credential_enabled(audit_secret, cred_id, False),
        "enable_credential": lambda: service.set_credential_enabled(audit_secret, cred_id, True),
    }
    for label, attempt in attempts.items():
        before = len(backend.audit_sink.snapshot())
        with pytest.raises(AuthorizationError):
            attempt()
        after = backend.audit_sink.snapshot()
        assert len(after) == before + 1, f"{label} denial did not add exactly one durable audit row"
        assert after[-1].reason_code == "FORBIDDEN", f"{label} did not refuse with FORBIDDEN"
        assert after[-1].outcome == "deny"
        assert after[-1].role == "audit"

    # The audit credential itself was never touched by any refused attempt
    # above -- still enabled, not revoked (confirmed by a 4th read).
    still_alive = service.control_capabilities(audit_secret)
    assert still_alive["role"] == "audit"


def test_audit_role_must_rotate_gate_allows_only_capabilities() -> None:
    """design §4 M-1: unlike `role="control"`, self-rotate is NOT in the
    `must_rotate` allow-list for `role="audit"` -- the out-of-band ceremony
    is what clears `must_rotate` before a secret is ever distributed, so no
    in-band audit principal is ever actually stuck here in practice, but the
    gate itself must still refuse self-rotate AND the other two read-only
    endpoints for one that IS (somehow) still rotate-pending."""
    service, backend, _cid, _secret = _bootstrapped()
    audit_id, audit_secret = _seed_audit_credential(backend, must_rotate=True)

    caps = service.control_capabilities(audit_secret)
    assert caps["role"] == "audit"

    with pytest.raises(AuthorizationError):
        service.rotate_credential(audit_secret, audit_id)
    with pytest.raises(AuthorizationError):
        service.list_applications(audit_secret)
    with pytest.raises(AuthorizationError):
        service.list_credentials(audit_secret)


# --------------------------------------------------------------------------
# out-of-band audit-credential issuance ceremony.
# --------------------------------------------------------------------------


def test_issue_audit_credential_ceremony_distributes_a_must_rotate_false_audit_credential() -> None:
    """`issue_audit_credential_ceremony` -- issues AND rotates in one
    transaction before returning a secret, so the returned secret's
    `must_rotate` is already `False` (design §4 M-1: no in-band self-rotate
    path exists for an audit principal, so the ceremony itself must
    complete the rotate half)."""
    backend = InMemoryControlBackend(app_pepper=_APP_PEPPER, control_pepper=_CONTROL_PEPPER)
    with backend.unit_of_work() as work:
        credential_id, bearer = issue_audit_credential_ceremony(
            backend.control_credential_store, backend.append_audit, work=work)
    secret = bearer
    principal = backend.control_credential_store.authenticate(secret)
    assert principal.credential_id == credential_id
    assert principal.must_rotate is False
    assert principal.role == "audit"

    events = backend.audit_sink.snapshot()
    assert len(events) == 1
    assert events[0].operation == "issue_audit_credential"
    assert events[0].outcome == "allow"
    assert events[0].target_id == credential_id


# --------------------------------------------------------------------------
# per-application issuance freeze (§1-E): forbids new issuance only,
# precedence, and isolation from already-issued credentials.
# --------------------------------------------------------------------------


def test_issuance_freeze_forbids_then_unfreeze_allows_again() -> None:
    service, backend, cid, secret = _bootstrapped()
    app_id = "fzapp"
    service.register_application(secret, app_id)

    with backend.unit_of_work() as work:
        backend.set_application_issuance_frozen(app_id, True, work=work)
    before = len(backend.audit_sink.snapshot())
    with pytest.raises(AuthorizationError):
        service.issue_credential(secret, app_id, "runtime")
    after = backend.audit_sink.snapshot()
    assert len(after) == before + 1
    assert after[-1].reason_code == "FORBIDDEN"

    with backend.unit_of_work() as work:
        backend.set_application_issuance_frozen(app_id, False, work=work)
    issued = service.issue_credential(secret, app_id, "runtime")
    assert issued["application_id"] == app_id


def test_issuance_freeze_precedence_role_control_refused_before_freeze_check() -> None:
    """design §1-E/M-8, C-14 vector 3 discipline: the `role="control"`
    `CAPABILITY_UNSUPPORTED` capability refusal is evaluated BEFORE
    application-existence/state/limit resolution -- including the freeze
    check. A frozen application must still yield `CapabilityError`
    (`CAPABILITY_UNSUPPORTED`), never `AuthorizationError` (`FORBIDDEN`),
    for a `role="control"` issuance request."""
    service, backend, cid, secret = _bootstrapped()
    app_id = "fzprecapp"
    service.register_application(secret, app_id)
    with backend.unit_of_work() as work:
        backend.set_application_issuance_frozen(app_id, True, work=work)

    with pytest.raises(CapabilityError):
        service.issue_credential(secret, app_id, "control")


def test_issuance_freeze_does_not_affect_already_issued_credentials() -> None:
    """Freezing an application only refuses NEW issuance -- an
    already-live credential for that application keeps authenticating
    exactly as before (freeze has no concept of "revoke existing
    credentials")."""
    service, backend, cid, secret = _bootstrapped()
    app_id = "fzliveapp"
    service.register_application(secret, app_id)
    issued = service.issue_credential(secret, app_id, "runtime")
    app_cred_id = issued["credential_id"]

    with backend.unit_of_work() as work:
        backend.set_application_issuance_frozen(app_id, True, work=work)

    state = backend.credential_state(app_cred_id)
    assert state is not None and state[0] is True and state[1] is False  # enabled, not revoked

    with pytest.raises(AuthorizationError):
        service.issue_credential(secret, app_id, "runtime")

    # Still live after the freeze-time NEW-issuance refusal above.
    state_again = backend.credential_state(app_cred_id)
    assert state_again is not None and state_again[0] is True and state_again[1] is False


def test_in_memory_issuance_freeze_rolls_back_with_its_own_unit_of_work() -> None:
    """WP-4 r2db lesson (n-2), applied proactively: `InMemoryApplication
    Registry.set_issuance_frozen` participates in the SAME shared undo-log
    `work` token every other write in this module already does (`work.
    on_rollback(...)`) -- so a fault raised elsewhere in the same `unit_of_
    work()` body rolls the freeze flag back too, structurally, with no
    separate snapshot list that could forget this one piece of state."""
    service, backend, cid, secret = _bootstrapped()
    app_id = "fzrollbackapp"
    service.register_application(secret, app_id)
    assert backend._applications.issuance_frozen(app_id) is False  # noqa: SLF001

    class _InjectedFault(Exception):
        pass

    with pytest.raises(_InjectedFault):
        with backend.unit_of_work() as work:
            backend.set_application_issuance_frozen(app_id, True, work=work)
            # The freeze write above is visible mid-transaction...
            assert backend._applications.issuance_frozen(app_id) is True  # noqa: SLF001
            raise _InjectedFault("simulated failure later in the same transaction")

    # ...but rolled back once the surrounding unit of work fails.
    assert backend._applications.issuance_frozen(app_id) is False  # noqa: SLF001


# --------------------------------------------------------------------------
# revoke-gate role filter (WP-4 r2db lesson, applied proactively): the
# "last active control credential" count must exclude role="audit" rows.
# --------------------------------------------------------------------------


def test_revoke_gate_active_audit_credential_does_not_mask_last_active_control_credential() -> None:
    """The last-active-control-credential revoke gate's own "active" count
    filters to `role == "control"` rows -- this WP's own addition,
    preventing a regression this WP's own `role` column would otherwise
    introduce (an audit row masking the sole management credential from
    the "last active control credential" gate). Seeds exactly one active
    control credential AND one active audit credential, then asserts
    revoking the control credential still requires confirmation."""
    service, backend, cid, secret = _bootstrapped()
    audit_id, audit_secret = _seed_audit_credential(backend, must_rotate=False)

    with pytest.raises(DestructiveConfirmationRequired):
        service.revoke_credential(secret, cid)

    # Still live -- the unconfirmed probe never executed.
    caps = service.control_capabilities(secret)
    assert caps["role"] == "control"
    still_alive = service.control_capabilities(audit_secret)
    assert still_alive["role"] == "audit"


def test_revoke_gate_revoking_the_audit_credential_itself_is_never_gated() -> None:
    """Revoking the ACTIVE audit credential itself (with the sole active
    control credential also present and untouched) succeeds unconfirmed --
    an audit credential is excluded from the gate's own "active" count
    entirely (it can never be the credential `active_ids[0] ==
    target_credential_id` matches), so this is an ordinary, non-
    destructive-confirmation-gated revoke, exactly like an application
    credential's."""
    service, backend, cid, secret = _bootstrapped()
    audit_id, audit_secret = _seed_audit_credential(backend, must_rotate=False)

    result = service.revoke_credential(secret, audit_id)
    assert result == {"credential_id": audit_id, "enabled": True, "revoked": True}

    with pytest.raises(AuthenticationError):
        service.control_capabilities(audit_secret)

    # The control credential (the actual gate target) was untouched by
    # revoking the audit credential.
    caps = service.control_capabilities(secret)
    assert caps["role"] == "control"
