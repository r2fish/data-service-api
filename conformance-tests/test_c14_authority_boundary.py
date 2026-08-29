"""C-14 -- control-plane authority boundary (SI-00, SI-02, SI-03, SI-08).

design: docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md section 4 "C-14
(authority boundary) の検証ベクタ", registered in
`conformance-tests/CONDITIONS.md`. Every test here carries
`@pytest.mark.condition("C-14")` via the module-level `pytestmark`.

Design section 4 states five vectors for this condition:

1. An application credential (runtime and developer both) is fail-closed
   against every one of the 11 contract control endpoints (folded onto 9
   port v1.5 methods here -- `set_application_enabled_inband`/`set_
   credential_enabled_inband` each carry an `enabled` boolean instead of
   being split into two methods).
2. A control credential is refused on every data/schema (application-plane)
   endpoint.
3. An in-band `role="control"` credential-issuance request is refused with
   `CAPABILITY_UNSUPPORTED`, regardless of whether the target application
   exists, is disabled, or is already at its `credentials_per_application`
   limit (design section 8 M-1's fixed evaluation order: the capability
   refusal precedes every other check).
4. The peer's declared `control_plane` status agrees with its real
   behavior, in both directions: `enabled` must mean in-band operations
   really work (this file's own "provided" branches), and anything other
   than `enabled` must mean no control operation actually executes (the
   absence helper's own "success is a failure" branch, below).
5. The three SI-08 resource-boundary classes (`applications`,
   `credentials_per_application`, `control_requests_per_minute`) are
   published in `control_capabilities()`'s `limits`/`limit_enforcement`
   as `enforced`, and each is genuinely driveable past in a real test run.

Design section 4 also defines two shapes a peer without a real, `enabled`
in-band surface may honestly take -- neither is a skip, and both are
genuinely verified here, never accepted on an adapter's bare word:

- (a) **surface-absent**: no real call on the peer's public surface could
  even receive the request. The port operation raises `SurfaceAbsent`
  (C-17 precedent), independently re-verified via
  `signature_forbids_parameters`.
- (b) **declared-unavailable**: a real entry point exists, but the peer's
  own `control_plane` capability is declared `unavailable`, so every real
  entry point refuses uniformly with `CAPABILITY_UNSUPPORTED`. **Known
  acceptance boundary (measured, WP-1 fix-round mutation M5/M9):** this
  form's authenticity -- that the `CAPABILITY_UNSUPPORTED` denial genuinely
  came from a real peer call, not a fabricated `ConformanceDenial` an
  adapter raises without presenting the request anywhere -- cannot be
  structurally proven at this port level the way form (a)'s claim can
  (`ConformanceDenial` deliberately carries no provenance evidence
  analogous to `SurfaceAbsent`'s `surface`/`forbidden_parameters`, design
  section 4.1). Form (b)'s authenticity is therefore adapter-honesty plus
  review evidence, not something this suite can independently verify --
  recorded here and in `CONDITIONS.md`'s C-14 status text. A positive-
  existence check (a hypothetical `control_inband_surface()` port op
  requiring the entry point to demonstrably exist before a denial from it
  counts) is deliberately DEFERRED rather than spec'd speculatively: no
  currently-registered peer takes form (b) at all, and designing that
  check without a real form-(b) peer to validate it against risks solving
  the wrong problem.

As of this port revision (WP-5 of the CCR-14 design, the declaration
flip), `r2db-api` (in-process) and `r2db-api-http` both declare
`control_plane: enabled` and take the PROVIDED branch for real -- see
each adapter's own `control_capabilities`/`register_application_inband`/
etc. implementations (`conformance_adapter_r2db.py`/
`conformance_adapter_r2db_http.py`) for how each presents requests to its
real `/control/v1`-equivalent surface. `MitateDB-api` remains
surface-absent, form (a), for every test below -- see that adapter's own
`_control_surface_absent` for its evidence. Per this repository's "skip is
fail" rule and design principle 4, no branch here is ever skipped, for
any adapter.

`deprovision_application` (port v1.5 fix-round addition, the 14th
abstract method, design independent-review supervisor ruling on blockers
B-1/B-2) is this file's own test-harness cleanup primitive: vector 5's
`applications` resource-bound drive registers real Applications to
saturate the declared bound, and must undo that afterward rather than
permanently poisoning the session-scoped adapter's registry for every
later test that shares it.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Mapping

import pytest

from adapter import (
    ConformanceDenial,
    Fixture,
    SurfaceAbsent,
    UNCLASSIFIED,
    fresh_identifier,
    load_contract_error_codes,
    signature_forbids_parameters,
)

pytestmark = pytest.mark.condition("C-14")

# design section 8 m-7: no single contract code is fixed for a fail-closed
# authority refusal (an implementation may reasonably answer AUTH_INVALID,
# AUTH_REVOKED, or FORBIDDEN for different reasons); the common suite
# requires membership in this set rather than one exact code, so
# implementation differences that all satisfy "fail-closed" are not
# penalized. NOT_FOUND and CAPABILITY_UNSUPPORTED are never acceptable
# here -- see `_inband_endpoint_thunks`'s own docstring for why.
#
# WP-5 (design §13.3, measured against the real provided-branch peers):
# `AUTH_REQUIRED` (no secret presented at all -- the empty-secret probe) is
# ALSO a genuine fail-closed outcome on both r2db-api adapters, distinct
# from `AUTH_INVALID` (a *wrong* secret) only in which store-level check
# fired first. §8 m-7's own "401 系 fail-closed, code非固定" reasoning
# already covers this: the common suite was under-broadened here, not the
# implementations under-conforming -- widened to match, same principle.
_FAIL_CLOSED_CODES = frozenset({"AUTH_INVALID", "AUTH_REVOKED", "AUTH_REQUIRED", "FORBIDDEN"})

# design docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md section 4's own
# conformance-buildability requirement (also stated on `adapter.py`'s new
# port v1.5 abstract-method group): a conformance build's SI-08 resource
# bounds must be small enough to actually drive over in one test run.
_MAX_EXERCISABLE_LIMIT = 200


def _unclassified_hint(code: str) -> str:
    if code != UNCLASSIFIED:
        return ""
    return (
        " -- code is adapter.UNCLASSIFIED: the peer raised a native exception the adapter could not map "
        "to a contract code. This is a finding under SI-05/SI-10, not a denial."
    )


def _assert_is_contract_code(code: str) -> None:
    contract_codes = load_contract_error_codes()
    assert code in contract_codes, f"denial code {code!r} is not a contract error code{_unclassified_hint(code)}"


def _control_plane_status(adapter) -> str:
    """The peer's own declared `control_plane` capability status, read from
    its real, application-plane `capability_document()` -- never a value
    this suite infers or caches. `service.py`'s `DataService.capabilities()`
    (`r2db-api`, both adapters -- constructor-injected via `control_plane_
    status`, WP-5 R-9) and `cell.py:468` (`MitateDB-api`) are where each
    peer publishes this; as of WP-5 the two r2db-api adapters declare
    `"enabled"` and `MitateDB-api` still declares `"unavailable"`.

    Raises an explicit, actionable `AssertionError` naming whichever key is
    missing rather than letting a bare `KeyError` propagate (design
    independent review, minor): a peer whose capability document omits
    `capabilities`/`control_plane`/`status` entirely is a real finding
    (the contract requires this shape) and should read as one, not as an
    opaque `KeyError` traceback that looks like a harness bug.
    """
    document = adapter.capability_document()
    capabilities = document.get("capabilities")
    assert isinstance(capabilities, dict), (
        f"{adapter.name}: capability_document() has no 'capabilities' mapping -- {document!r}"
    )
    control_plane = capabilities.get("control_plane")
    assert isinstance(control_plane, dict) and "status" in control_plane, (
        f"{adapter.name}: capability_document()['capabilities'] has no 'control_plane' entry carrying a "
        f"'status' key -- got {control_plane!r}. A peer missing this key is a finding under the contract's "
        "capability_status vocabulary, not silently treated as unavailable."
    )
    return control_plane["status"]


def _application_actor(adapter, fx: Fixture):
    """A real application `CredentialHandle` (not a post-`authenticate()`
    session object -- port v1.5's in-band `actor` parameter takes a
    handle directly, exactly like `authenticate()`'s own parameter),
    minted fresh via the pre-existing out-of-band `issue_credential`
    setup primitive. Used as `actor` for every C-14 absence-branch thunk:
    the surface-absence claim must hold even when a genuine application
    credential is the one presenting the request, not merely for a bare
    `None` -- proving the entry point is missing for a *real* credential
    holder is the actual content of vector 1's absence side.
    """
    return adapter.issue_credential(fx.app_a, "runtime")


def _assert_control_operation_absent_or_uniformly_refused(adapter, thunk: Callable[[], Any]) -> str:
    """Runs `thunk`. Exactly one of two shapes is acceptable whenever
    `control_plane` is declared anything other than `"enabled"` (design
    section 4's two absence forms):

    - (a) surface-absent: `thunk` raises `SurfaceAbsent`. Its claim is
      independently re-verified, more strongly than the original C-17
      precedent (design docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md WP-1
      independent review, major M-7):

      - `signature_forbids_parameters(exc.surface, exc.forbidden_
        parameters)`'s violations must EXACTLY equal `exc.exempt_
        parameters` -- not merely a subset. An unexempted violation means
        a real parameter could carry the absent capability (the claim is
        false, C-14 mutation M1 exercises this). A violation set that is a
        *proper subset* of the declared exemptions is just as suspect: a
        stale or padded exemption naming a parameter that is not actually
        a violation either no longer applies, or was never a real
        exemption to begin with (C-14 mutation M7 exercises this).
      - the declared `surface` must cover at least the peer's own real
        `public_operation_callables()` (`set(exc.surface) >=
        set(adapter.public_operation_callables())`) -- an adapter cannot
        narrow its evidence surface below the peer's actual public surface
        just to dodge a violation elsewhere on it (C-14 mutation M8
        exercises this).
      - the *declared* `forbidden_parameters` set is not a weakened,
        narrow list chosen merely to make the signature check pass
        vacuously (C-14 mutation M4): `{"credential", "control"}` must be
        a subset of the declared set.
    - (b) declared-unavailable: `thunk` raises `ConformanceDenial` with
      `code == "CAPABILITY_UNSUPPORTED"` -- any other code is a finding:
      an unavailable declaration must refuse uniformly, not with an
      unrelated error (a `NOT_FOUND`, for instance, would mean the peer
      resolved the target before ever checking capability availability).
      See this module's own docstring for this form's known,
      measured acceptance-boundary limitation (mutation M5/M9).

    `thunk` succeeding without raising is always a failure regardless of
    form: an "unavailable"/absent declaration under which a control
    operation actually executes is the reverse half of design section 4
    vector 4 (declared status disagreeing with real behavior) -- the same
    property `test_c14_declared_status_agrees_with_actual_surface`'s
    module-level name calls out explicitly, enforced here for every
    thunk this helper is ever given, not only that one test's own thunks.

    Returns `"surface_absent"` or `"declared_unavailable"` so the caller
    can additionally assert every operation it exercises takes the *same*
    form (`_assert_uniform_absence_form`, below) -- a peer answering some
    operations one way and others the other way is an internally
    inconsistent declaration in its own right, not two independently
    acceptable outcomes.
    """
    try:
        thunk()
    except SurfaceAbsent as exc:
        violations = set(signature_forbids_parameters(exc.surface, exc.forbidden_parameters))
        exempt = set(exc.exempt_parameters)
        assert violations == exempt, (
            f"{adapter.name}: control-plane SurfaceAbsent's signature_forbids_parameters violations "
            f"{sorted(violations)!r} do not exactly equal its declared exempt_parameters "
            f"{sorted(exempt)!r} -- an unexempted violation means a real parameter could carry the absent "
            "capability (claim false); a stale or padded exemption naming a parameter that is not actually "
            "a violation is itself suspect (design section 4, independent review major M-7)"
        )
        declared = {f.lower() for f in exc.forbidden_parameters}
        assert {"credential", "control"} <= declared, (
            f"{adapter.name}: control-plane SurfaceAbsent's forbidden_parameters {exc.forbidden_parameters!r} "
            "does not include both 'credential' and 'control' -- a narrower fragment set could pass "
            "signature_forbids_parameters vacuously without actually covering the control-plane vocabulary "
            "this claim is supposed to rule out (C-14 mutation M4 hardens exactly this)"
        )
        public_surface = set(adapter.public_operation_callables())
        declared_surface = set(exc.surface)
        assert declared_surface >= public_surface, (
            f"{adapter.name}: control-plane SurfaceAbsent's declared surface omits "
            f"{[c for c in public_surface if c not in declared_surface]!r} of the peer's own real "
            "public_operation_callables() -- shrinking the evidence surface below the peer's real public "
            "surface would let a genuine control-plane-shaped parameter elsewhere on the peer go unchecked "
            "(independent review major M-7, C-14 mutation M8)"
        )
        return "surface_absent"
    except ConformanceDenial as exc:
        _assert_is_contract_code(exc.code)
        assert exc.code == "CAPABILITY_UNSUPPORTED", (
            f"{adapter.name}: control_plane is declared unavailable, but this operation was refused with "
            f"{exc.code!r} instead of CAPABILITY_UNSUPPORTED -- an unavailable declaration must refuse "
            "every real entry point uniformly (design section 4 form (b))"
        )
        return "declared_unavailable"
    else:
        raise AssertionError(
            f"{adapter.name}: control_plane is not declared 'enabled', but this operation succeeded -- an "
            "unavailable/absent declaration under which a control operation actually executes is a genuine "
            "defect (design section 4 vector 4's reverse direction)"
        )


def _assert_uniform_absence_form(adapter, thunks: Mapping[str, Callable[[], Any]]) -> None:
    """Runs every thunk in `thunks` through
    `_assert_control_operation_absent_or_uniformly_refused` and requires
    every one to report the *same* form. A `control_plane` declaration
    means one consistent thing -- surface-absent XOR declared-unavailable
    -- not a per-operation coin flip; a peer that answers some control
    operations with `SurfaceAbsent` and others with a real
    `CAPABILITY_UNSUPPORTED` denial is declaring something internally
    inconsistent about its own topology, which this suite treats as a
    finding rather than silently accepting whichever form each individual
    operation happened to take.
    """
    forms = {name: _assert_control_operation_absent_or_uniformly_refused(adapter, thunk) for name, thunk in thunks.items()}
    unique_forms = set(forms.values())
    assert len(unique_forms) == 1, (
        f"{adapter.name}: control-plane absence form is not uniform across operations: {forms!r}. A "
        "control_plane declaration must mean one consistent thing, not a mix depending on which operation "
        "is asked."
    )


def _inband_endpoint_thunks(adapter, actor) -> dict[str, Callable[[], Any]]:
    """The 11 contract control endpoints, folded onto 9 port v1.5 methods
    (design section 4's own "11 endpoints -> 9 ops" mapping;
    `set_application_enabled_inband`/`set_credential_enabled_inband` each
    contribute two calls here, one per boolean).

    `application_id`/`credential_ref` targets are deliberately fresh,
    never-provisioned identifiers -- never a real Application or
    credential this test set up. Design section 8 M-1's fixed evaluation
    order (a capability/authority refusal must precede target resolution)
    means a genuinely fail-closed peer refuses every one of these with an
    authority code even though the named target does not exist:
    `NOT_FOUND` would be evidence the peer got as far as resolving the
    target before ever checking who `actor` is, which is exactly the
    ordering defect vector 1 exists to catch (see `_FAIL_CLOSED_CODES`'s
    own docstring comment above).
    """
    application_id = fresh_identifier("c14_tgt_app")
    credential_ref = fresh_identifier("c14_tgt_cred")
    return {
        "control_capabilities": lambda: adapter.control_capabilities(actor),
        "register_application_inband": lambda: adapter.register_application_inband(actor, fresh_identifier("c14_reg")),
        "list_applications": lambda: adapter.list_applications(actor),
        "set_application_enabled_inband(enable)": lambda: adapter.set_application_enabled_inband(actor, application_id, True),
        "set_application_enabled_inband(disable)": lambda: adapter.set_application_enabled_inband(actor, application_id, False),
        "issue_credential_inband": lambda: adapter.issue_credential_inband(actor, application_id, "runtime"),
        "list_credentials": lambda: adapter.list_credentials(actor),
        "rotate_credential": lambda: adapter.rotate_credential(actor, credential_ref),
        "revoke_credential_inband": lambda: adapter.revoke_credential_inband(actor, credential_ref),
        "set_credential_enabled_inband(enable)": lambda: adapter.set_credential_enabled_inband(actor, credential_ref, True),
        "set_credential_enabled_inband(disable)": lambda: adapter.set_credential_enabled_inband(actor, credential_ref, False),
    }


def _all_control_op_thunks(adapter, actor) -> dict[str, Callable[[], Any]]:
    """`_inband_endpoint_thunks`'s 11, plus the two out-of-band ritual
    hooks (`bootstrap`/`reset`), the two privileged setup/observation
    operations (`control_credential`/`control_audit_events`), and the
    fix-round addition `deprovision_application` -- every one of port
    v1.5's 14 abstract methods, 16 calls total. `bootstrap`/`reset`/
    `control_credential`/`deprovision_application` ignore `actor` entirely
    (design section 1.2: these have no in-band caller by contract; they
    are privileged/out-of-band operations), but are included here because
    the absence claim ("no control-plane surface exists on this peer at
    all") must cover them too, not only the 11 in-band endpoints.
    """
    thunks = dict(_inband_endpoint_thunks(adapter, actor))
    thunks.update({
        "bootstrap": lambda: adapter.bootstrap(),
        "reset": lambda: adapter.reset(),
        "control_credential": lambda: adapter.control_credential(),
        "control_audit_events": lambda: adapter.control_audit_events(),
        "deprovision_application": lambda: adapter.deprovision_application(fresh_identifier("c14_tgt_deprov")),
    })
    return thunks


# --- 1. application credentials fail closed on every control endpoint -----


def test_c14_application_credentials_fail_closed_on_every_control_operation(adapter, fx: Fixture):
    if _control_plane_status(adapter) != "enabled":
        _assert_uniform_absence_form(adapter, _all_control_op_thunks(adapter, _application_actor(adapter, fx)))
        return

    for role in ("runtime", "developer"):
        actor = adapter.issue_credential(fx.app_a, role)
        for label, thunk in _inband_endpoint_thunks(adapter, actor).items():
            with pytest.raises(ConformanceDenial) as ei:
                thunk()
            _assert_is_contract_code(ei.value.code)
            # This first assertion is logically implied by the membership
            # check below it (`_FAIL_CLOSED_CODES` is disjoint from
            # {NOT_FOUND, CAPABILITY_UNSUPPORTED} by construction) -- kept
            # separately anyway because it gives a specific, actionable
            # diagnosis (an evaluation-order defect) rather than the
            # generic "wrong code" message the membership check alone
            # would produce.
            assert ei.value.code not in {"NOT_FOUND", "CAPABILITY_UNSUPPORTED"}, (
                f"{adapter.name}: {role} application credential against {label} got {ei.value.code!r}, which "
                "is evidence the peer resolved the target/capability before ever checking who the caller is "
                "-- not fail-closed (design section 8 M-1's evaluation-order requirement)"
            )
            assert ei.value.code in _FAIL_CLOSED_CODES, (
                f"{adapter.name}: {role} application credential against {label} got {ei.value.code!r}, "
                f"expected one of {sorted(_FAIL_CLOSED_CODES)!r} (design section 8 m-7: no single code is "
                "fixed, but the answer must be an authority-refusal code)"
            )


# --- 2. a control credential is refused on the application/data plane -----


def test_c14_control_credential_rejected_on_data_plane(adapter, fx: Fixture):
    """Provided branch keeps an authenticate()-only contraction, documented
    here rather than widened speculatively (design independent review,
    major M-5): on both currently-registered peers, `authenticate()` is
    the single gate every data/schema endpoint sits behind (design section
    R-8's own architecture -- every application-plane operation
    re-authenticates the bearer secret fresh on every call, no session
    cache, no alternate entry that skips this check). Rejecting a control
    credential at that one gate therefore covers the design's full
    data/schema endpoint enumeration (query/mutations/catalog/
    schema_operations) for both peers today. A future peer where some
    data-plane endpoint is reachable without a prior `authenticate()` step
    would need this vector widened to probe that endpoint directly --
    supervisor ruling, overridable.
    """
    if _control_plane_status(adapter) != "enabled":
        _assert_uniform_absence_form(adapter, {"control_credential": lambda: adapter.control_credential()})
        return

    control_actor = adapter.control_credential()
    with pytest.raises(ConformanceDenial) as ei:
        adapter.authenticate(control_actor)
    _assert_is_contract_code(ei.value.code)
    assert ei.value.code in _FAIL_CLOSED_CODES, (
        f"{adapter.name}: a control credential presented to the application-plane authenticate() got "
        f"{ei.value.code!r}, expected one of {sorted(_FAIL_CLOSED_CODES)!r} (401-series fail-closed, design "
        "section R-8)"
    )


# --- 3. in-band role=control issuance: CAPABILITY_UNSUPPORTED, fixed order


def test_c14_role_control_issuance_refused_with_capability_unsupported(adapter, fx: Fixture):
    if _control_plane_status(adapter) != "enabled":
        _assert_uniform_absence_form(adapter, {
            "issue_credential_inband(role=control)": lambda: adapter.issue_credential_inband(
                _application_actor(adapter, fx), fx.app_a, "control"
            ),
        })
        return

    control_actor = adapter.control_credential()

    def _expect_capability_unsupported(application_id: str, label: str) -> None:
        with pytest.raises(ConformanceDenial) as ei:
            adapter.issue_credential_inband(control_actor, application_id, "control")
        _assert_is_contract_code(ei.value.code)
        assert ei.value.code == "CAPABILITY_UNSUPPORTED", (
            f"{adapter.name}: role=control issuance ({label}) got {ei.value.code!r}, expected "
            "CAPABILITY_UNSUPPORTED regardless of the target application's own state (design section 8 M-1's "
            "fixed evaluation order: the capability refusal precedes application-existence/state/limit "
            "resolution)"
        )

    # (i) a real, existing, enabled application.
    _expect_capability_unsupported(fx.app_a, "existing application")

    # (ii) an application that does not exist at all.
    _expect_capability_unsupported(fresh_identifier("c14_missing"), "nonexistent application")

    # (iii) a real application that is disabled.
    disabled_app = fresh_identifier("c14_disabled")
    adapter.provision_application(disabled_app)
    adapter.disable_application(disabled_app)
    _expect_capability_unsupported(disabled_app, "disabled application")

    # (iv) a real application already at its credentials_per_application
    # limit -- saturated via IN-BAND issuance (the control actor), not the
    # out-of-band `issue_credential` setup primitive (design independent
    # review, minor): this vector is specifically about the in-band
    # surface's own evaluation order, so the precondition state it drives
    # against should itself be reached the same way a real client would.
    # Cleanup revokes every credential this saturation issued.
    limits = adapter.control_capabilities(control_actor).get("limits", {})
    limit = limits.get("credentials_per_application")
    assert isinstance(limit, int) and limit > 0, (
        f"{adapter.name}: control_capabilities()['limits']['credentials_per_application'] is not a positive "
        f"int ({limit!r}) -- required to drive this vector's limit-saturation case"
    )
    saturated_app = fresh_identifier("c14_saturated")
    adapter.provision_application(saturated_app)
    issued_for_saturation = []
    try:
        for _ in range(limit):
            issued_for_saturation.append(adapter.issue_credential_inband(control_actor, saturated_app, "runtime"))
        _expect_capability_unsupported(saturated_app, "application at its credentials_per_application limit")
    finally:
        for handle in issued_for_saturation:
            adapter.revoke_credential_inband(control_actor, handle.credential_ref)


# --- 4. declared status agrees with real behavior, both directions --------


def test_c14_declared_status_agrees_with_actual_surface(adapter, fx: Fixture):
    """Forward direction (this test's provided branch): `control_plane:
    enabled` must mean a real in-band register->list roundtrip works, and
    a real in-band credential issuance against the freshly registered
    application actually returns a usable (non-empty) secret. Reverse
    direction (the absence branch below, and in fact every other test in
    this file via `_assert_control_operation_absent_or_uniformly_refused`'s
    own "success is a failure" clause): anything other than `enabled` must
    mean these same operations do not actually execute. Both directions of
    design section 4 vector 4 are therefore exercised by this file as a
    whole, not only by this one test function.

    This provided branch deliberately does NOT authenticate the issued
    credential and check its data-plane scope (design independent review,
    major M-3, supervisor ruling, overridable): registration effectiveness
    under design R-4 is a CONTROL-PLANE-level property -- the Application
    is registered ("registered, not yet provisioned") and can have
    credentials issued against it. Data-plane reachability is a
    deployment property (the server's own static serving set, R-4), not
    what this vector tests: an in-band-registered Application is
    legitimately "registered but unprovisioned" until an operator
    separately provisions it, and its data-plane `authenticate()` fails
    closed in that state by design, not by defect (R-4: "登録済みだが未
    provisioning の Application への credential 発行は許す" -- issuance
    succeeds; data-plane reach is a separate concern the contract does not
    tie to registration). Asserting a successful authenticate()/scope_of()
    roundtrip here would fail a conformant peer that correctly implements
    this two-state registry.
    """
    if _control_plane_status(adapter) != "enabled":
        actor = _application_actor(adapter, fx)
        _assert_uniform_absence_form(adapter, {
            "register_application_inband": lambda: adapter.register_application_inband(actor, fresh_identifier("c14_reg")),
            "list_applications": lambda: adapter.list_applications(actor),
        })
        return

    control_actor = adapter.control_credential()
    new_app = fresh_identifier("c14_declared")
    adapter.register_application_inband(control_actor, new_app)
    listed = adapter.list_applications(control_actor)
    application_ids = {row["application_id"] for row in listed}
    assert new_app in application_ids, (
        f"{adapter.name}: control_plane declared enabled, but a freshly in-band-registered application "
        f"{new_app!r} does not appear in list_applications()'s own real response -- the declaration and the "
        "real surface disagree"
    )

    issued = adapter.issue_credential_inband(control_actor, new_app, "runtime")
    assert issued.secret, (
        f"{adapter.name}: control_plane declared enabled, but an in-band credential issuance against the "
        f"freshly registered application {new_app!r} returned no usable secret -- got {issued!r}"
    )


# --- 5. resource bounds are published and enforced (SI-08) ----------------


def test_c14_resource_bounds_published_and_enforced(adapter, fx: Fixture):
    """SI-08 resource-class discrimination is established POSITIONALLY, not
    via a contract-defined "resource" label (design independent review,
    blockers B-1/B-2, supervisor ruling): the contract's `LIMIT_EXCEEDED`
    denial carries no class-discriminating field in its problem+json shape
    (`spec/data-service-api.v1.json` `errors.shape`: `details` is a
    free-form object with no canonical "resource" key at all) -- this
    suite does not invent contract vocabulary the contract itself does not
    define to work around that. Each class below is driven ALONE, one at a
    time, and the refusal is required to land at the EXACT position the
    declared bound predicts; any earlier refusal cannot be attributed to
    the class under test (design's own words: "refused before the
    declared bound -- cannot attribute the refusal to the applications
    class"). The `applications` drive registers real Applications and
    cleans them up via `deprovision_application` in a `finally`, so this
    test does not permanently saturate the session-scoped adapter's
    registry for whatever runs after it.
    """
    if _control_plane_status(adapter) != "enabled":
        _assert_uniform_absence_form(adapter, {
            "control_capabilities": lambda: adapter.control_capabilities(_application_actor(adapter, fx)),
            "deprovision_application": lambda: adapter.deprovision_application(fresh_identifier("c14_tgt_deprov")),
        })
        return

    control_actor = adapter.control_credential()
    document = adapter.control_capabilities(control_actor)
    limits = document.get("limits", {})
    enforcement = document.get("limit_enforcement", {})
    classes = ("applications", "credentials_per_application", "control_requests_per_minute")
    for cls in classes:
        assert cls in limits, f"{adapter.name}: control_capabilities()['limits'] is missing resource class {cls!r}"
        assert enforcement.get(cls) == "enforced", (
            f"{adapter.name}: control_capabilities()['limit_enforcement'][{cls!r}] is {enforcement.get(cls)!r}, "
            "expected 'enforced' (SI-08)"
        )
        value = limits[cls]
        assert isinstance(value, int) and value > 0, (
            f"{adapter.name}: control_capabilities()['limits'][{cls!r}] is not a positive int: {value!r}"
        )
        assert value <= _MAX_EXERCISABLE_LIMIT, (
            f"{adapter.name}: control_capabilities()['limits'][{cls!r}] is {value!r}, exceeding "
            f"{_MAX_EXERCISABLE_LIMIT} -- a conformance build MUST configure its SI-08 resource bounds small "
            "enough to actually drive over in a test run (design docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md "
            "section 4's own conformance-buildability requirement, restated on adapter.py's port v1.5 "
            "abstract-method group); a bound that is only theoretically finite cannot be exercised by this "
            "vector"
        )

    apps_limit = limits["applications"]
    cred_limit = limits["credentials_per_application"]
    rate_limit = limits["control_requests_per_minute"]

    # Positional-arithmetic headroom precondition (B-1/B-2): the
    # applications and credentials_per_application drives below must not
    # themselves get rate-limited before reaching their own declared
    # bound, or their own LIMIT_EXCEEDED could not be attributed to their
    # own class either. Worst-case request counts: `applications`
    # (1 list_applications + up to apps_limit+1 register attempts);
    # `credentials_per_application` (up to cred_limit+1 issue attempts +
    # cred_limit in-band revoke-cleanup calls). `deprovision_application`
    # cleanup is the peer's operator-privileged, out-of-band path (like
    # `provision_application`), not a rate-limited `/control/v1` call, so
    # it is excluded from this arithmetic.
    applications_headroom_drive = apps_limit + 2
    credentials_drive = 2 * cred_limit + 1
    margin = 64
    assert rate_limit > applications_headroom_drive + credentials_drive + margin, (
        f"{adapter.name}: declared control_requests_per_minute ({rate_limit!r}) does not leave enough "
        f"headroom over the applications drive's worst case ({applications_headroom_drive!r} requests) plus "
        f"the credentials_per_application drive's worst case ({credentials_drive!r} requests) plus a "
        f"{margin!r}-request margin -- a conformance build must configure control_requests_per_minute > "
        f"{applications_headroom_drive + credentials_drive + margin!r} so a permanent-bound drive's "
        "LIMIT_EXCEEDED can never be confused with an early rate-limit refusal (design independent review, "
        "blockers B-1/B-2)"
    )

    # -- applications: read current count, drive to the exact bound, clean up. --
    existing_applications = adapter.list_applications(control_actor)
    n_existing = len(existing_applications)
    assert n_existing < apps_limit, (
        f"{adapter.name}: the registry already holds {n_existing!r} applications, at or past the declared "
        f"applications bound {apps_limit!r}, before this test even started driving it -- the suite has "
        "already saturated the registry (a prior test's own cleanup failed, or the conformance build's "
        "bound is too small for the suite's own fixture/application churn)"
    )
    required_successes = apps_limit - n_existing
    registered_apps: list[str] = []
    try:
        successes = 0
        limit_hit = False
        for _ in range(required_successes + 1):
            app_id = fresh_identifier("c14_bound_app")
            try:
                adapter.register_application_inband(control_actor, app_id)
                registered_apps.append(app_id)
                successes += 1
            except ConformanceDenial as exc:
                _assert_is_contract_code(exc.code)
                assert exc.code == "LIMIT_EXCEEDED", (
                    f"{adapter.name}: registering application #{successes + 1} of this drive got {exc.code!r}, "
                    "expected LIMIT_EXCEEDED"
                )
                assert successes == required_successes, (
                    f"{adapter.name}: applications drive was refused with LIMIT_EXCEEDED after only "
                    f"{successes!r} success(es), but the declared bound {apps_limit!r} (with {n_existing!r} "
                    f"pre-existing) predicts exactly {required_successes!r} -- refused before the declared "
                    "bound: cannot attribute the refusal to the applications class (it may be a different "
                    "class's bound, e.g. the rate limiter, firing early)"
                )
                limit_hit = True
                break
        assert limit_hit, (
            f"{adapter.name}: registering {required_successes + 1!r} new applications never triggered "
            f"LIMIT_EXCEEDED for the declared applications bound {apps_limit!r} (with {n_existing!r} "
            "pre-existing) -- the declared limit is not actually enforced"
        )
    finally:
        for app_id in registered_apps:
            adapter.deprovision_application(app_id)

    # -- credentials_per_application: fresh application, drive to the exact bound, clean up. --
    cred_app = fresh_identifier("c14_bound_cred_app")
    adapter.provision_application(cred_app)
    try:
        issued_handles: list = []
        try:
            successes = 0
            limit_hit = False
            for _ in range(cred_limit + 1):
                try:
                    handle = adapter.issue_credential_inband(control_actor, cred_app, "runtime")
                    issued_handles.append(handle)
                    successes += 1
                except ConformanceDenial as exc:
                    _assert_is_contract_code(exc.code)
                    assert exc.code == "LIMIT_EXCEEDED", (
                        f"{adapter.name}: issuing credential #{successes + 1} to a fresh application got "
                        f"{exc.code!r}, expected LIMIT_EXCEEDED"
                    )
                    assert successes == cred_limit, (
                        f"{adapter.name}: credentials_per_application drive was refused with LIMIT_EXCEEDED "
                        f"after only {successes!r} success(es), but the declared bound {cred_limit!r} "
                        "predicts exactly that many -- refused before the declared bound: cannot attribute "
                        "the refusal to the credentials_per_application class"
                    )
                    limit_hit = True
                    break
            assert limit_hit, (
                f"{adapter.name}: issuing {cred_limit + 1!r} credentials to one application never triggered "
                f"LIMIT_EXCEEDED for the declared credentials_per_application bound {cred_limit!r}"
            )
        finally:
            # revoked credentials do not count toward the bound (design
            # R-7), so revoking every credential this drive issued
            # restores the application's headroom for later tests.
            for handle in issued_handles:
                adapter.revoke_credential_inband(control_actor, handle.credential_ref)
    finally:
        adapter.deprovision_application(cred_app)

    # -- control_requests_per_minute: run LAST, burst, then confirm recovery. --
    # `control_capabilities` is an operation no PERMANENT bound applies to
    # (design section R-5: it remains callable even by a must_rotate
    # credential) -- that operation choice IS the class attribution
    # (supervisor ruling): a burst of `control_capabilities` calls cannot
    # be confused with the applications/credentials_per_application
    # drives above, both already fully cleaned up by this point.
    successes = 0
    limit_hit = False
    for _ in range(rate_limit + margin):
        try:
            adapter.control_capabilities(control_actor)
            successes += 1
        except ConformanceDenial as exc:
            _assert_is_contract_code(exc.code)
            assert exc.code == "LIMIT_EXCEEDED", (
                f"{adapter.name}: exceeding the declared control_requests_per_minute limit got {exc.code!r}, "
                "expected LIMIT_EXCEEDED"
            )
            limit_hit = True
            break
    assert limit_hit, (
        f"{adapter.name}: issuing up to {rate_limit + margin!r} control_capabilities() calls never "
        f"triggered LIMIT_EXCEEDED for the declared control_requests_per_minute bound {rate_limit!r}"
    )

    # Recovery: wait for the next minute-window rollover -- bounded, <=61s
    # -- and confirm one more call succeeds. This is provided-branch-only
    # code (never executed under WP-1; the real time cost is documented
    # here rather than hidden) and proves the refusal above was transient
    # (the rate class, not a permanent bound), while also un-poisoning the
    # rate window for whatever runs after this test against the same
    # session-scoped adapter.
    time.sleep(61)
    adapter.control_capabilities(control_actor)
