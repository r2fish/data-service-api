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

from typing import Any, Callable, Mapping

import pytest

from absence import (
    assert_control_operation_absent_or_uniformly_refused as _shared_assert_control_operation_absent_or_uniformly_refused,
)
from absence import assert_is_contract_code as _assert_is_contract_code
from absence import assert_uniform_absence_form as _shared_assert_uniform_absence_form
from adapter import (
    ConformanceDenial,
    Fixture,
    fresh_identifier,
)

# port v1.6 (design docs/design/DESTRUCTIVE_CONFIRMATION_V1.md R-6 item 4 /
# WP-0 m-4): this vocabulary and the absence-form mechanism itself now live
# in the shared `absence` module (C-06's `drop_entity` absent branch reuses
# the identical mechanism). `{"credential", "control"}` is this file's own
# C-14-specific vocabulary requirement, preserved unchanged from before the
# extraction.
_CONTROL_PLANE_FORBIDDEN_VOCABULARY = ("credential", "control")


def _assert_control_operation_absent_or_uniformly_refused(adapter, thunk: Callable[[], Any]) -> str:
    return _shared_assert_control_operation_absent_or_uniformly_refused(
        adapter, thunk, required_forbidden_vocabulary=_CONTROL_PLANE_FORBIDDEN_VOCABULARY
    )


def _assert_uniform_absence_form(adapter, thunks: Mapping[str, Callable[[], Any]]) -> None:
    _shared_assert_uniform_absence_form(
        adapter, thunks, required_forbidden_vocabulary=_CONTROL_PLANE_FORBIDDEN_VOCABULARY
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

# Supervisor ruling 2026-09-06 item 1 (design docs/design/
# CONFORMANCE_ADAPTER_V1.md §21.4): the `applications` vector below drives
# a small, overridden bound on an `isolated_control_surface()` instead
# of the real, shared-surface `limits["applications"]` value -- driving a
# three-digit real bound to its exact position (as this vector did before
# this ruling) costs 100+ control-plane calls, which starves the SHARED
# `control_requests_per_minute` window every other test/vector on this
# session-scoped adapter depends on (the diagnosed cause of 24 unrelated
# failures, WP-5 rework round 2). Same precedent `isolated_application_
# surface()`'s own small conformance profile already established for the
# application plane (C-05 V2): the ENFORCEMENT MECHANISM is what this
# vector proves, not the literal production-configured value, which the
# "classes" loop below already separately confirms is a positive,
# discoverable, `enforced`-labeled, `_MAX_EXERCISABLE_LIMIT`-bounded int.
#
# WP-5 rework (review finding 2): the override itself is no longer a
# fixed guess -- it used to be a hardcoded `8`, and this suite's own
# permanent, module-cached residue (measured, mutation M4:
# `test_c06_destructive_confirmation.py`'s own `_SHARED_FIXTURE_CACHE`
# plus MitateDB's own capability-probe application) already sits at
# exactly 5 pre-existing applications by the time this vector runs on
# EVERY one of the 4 currently-registered plugs, leaving the old fixed
# override only 3 applications of real headroom. A future module adding
# a few more of that same permanent-residue shape would silently exhaust
# that fixed headroom and fail this vector with a message that reads as
# "a prior test's own cleanup failed" even though nothing actually
# failed. Fixed by deriving the override from an OBSERVED count instead:
# `n_existing_shared + _APPLICATIONS_OVERRIDE_MARGIN`, read fresh, below,
# every time this vector runs. The isolated surface's own rate window is
# always empty (never the shared one), so this margin costs nothing to
# widen -- there is no reason for it to ever be tight again.
_APPLICATIONS_OVERRIDE_MARGIN = 3


def _control_plane_status(adapter) -> str:
    """The peer's own declared `control_plane` capability status, read from
    its real, application-plane `capability_document()` -- never a value
    this suite infers or caches. `service.py`'s `DataService.capabilities()`
    (`r2db-api`, both adapters -- constructor-injected via `control_plane_
    status`, WP-5 R-9) and `cell.py` (`MitateDB-api`, likewise
    composition-root-injected) are where each peer publishes this. The
    r2db-api pair has declared `"enabled"` since CCR-14 WP-5; the
    MitateDB-api pair has since that peer's own design-v1.2 WP-5, so all
    four registered adapters declare `"enabled"` today.

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
    class"). The `applications` drive (supervisor ruling 2026-09-06 item 1)
    runs on an `isolated_control_surface(limits_override=...)` -- its own
    small, overridden bound, its own empty rate window -- rather than
    driving the real, large declared bound on the shared surface; whatever
    Applications it registers are cleaned up by that primitive's own
    `with`-block exit, not by this test, so this test does not permanently
    saturate the session-scoped adapter's registry for whatever runs after
    it, and does not spend the SHARED `control_requests_per_minute`
    window's own budget doing so.
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

    # Positional-arithmetic headroom precondition (B-1/B-2), NARROWED by
    # supervisor ruling 2026-09-06 item 1: the `applications` drive no
    # longer runs on the SHARED surface at all (it now runs on an
    # `isolated_control_surface()`, below, with its own empty rate window)
    # -- only `credentials_per_application` still spends the shared
    # window's own budget. `applications_headroom_drive` below is
    # therefore retained purely as EXTRA margin (a real conformance build
    # that also satisfies the pre-ruling inequality has strictly more
    # headroom than this narrowed vector actually needs), never a
    # requirement this vector's own drive still creates.
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

    # -- applications: driven on an ISOLATED control surface (supervisor
    # ruling 2026-09-06 items 1/2, design docs/design/
    # CONFORMANCE_ADAPTER_V1.md §21.4) -- registering up to the REAL,
    # large `apps_limit` on the SHARED surface (as this vector did before
    # this ruling) costs 100+ control-plane calls inside the SAME shared
    # `control_requests_per_minute` window every other test/vector in this
    # file (and every other file -- this adapter is session-scoped)
    # depends on, starving them (measured: 24 unrelated test failures,
    # WP-5 rework round 2 diagnosis). `isolated_control_surface(limits_
    # override=...)`'s own empty rate window and small, overridden
    # `applications` bound mean driving to the EXACT declared position now
    # costs a handful of calls, never touching the shared window at all.
    #
    # The isolated surface shares the SAME underlying application registry
    # as the shared surface (`isolated_control_surface()`'s own docstring:
    # "sharing this adapter's own real registered application/credential
    # state"), so `n_existing` (read via the isolated surface's own
    # `list_applications`) still reflects real, pre-existing registrations
    # -- the SAME headroom arithmetic this vector always used, just
    # against the isolated surface's own (small, overridden) declared
    # bound rather than the real, large one (item 2's own "既存の登録数
    # k を読んでから期待成功数 = limit − k とする headroom 算術").
    # `deprovision_application` cleanup for whatever this drive registers
    # is `isolated_control_surface()`'s OWN responsibility, on its own
    # `with`-block exit (its docstring's own "residue list") -- this
    # vector must NOT also deprovision them itself, or it would attempt a
    # double deprovision against an application the primitive already
    # removed.
    # WP-5 rework (review finding 2): the override is derived from an
    # OBSERVED pre-existing count, read via the SHARED surface's own
    # `list_applications`, rather than a fixed guess -- one cheap read,
    # well inside the `margin`-request allowance already asserted above
    # (this vector's own isolated-surface work below spends none of the
    # shared rate window at all, so this single extra shared-surface call
    # is the only cost). The isolated surface shares the SAME underlying
    # registry (`isolated_control_surface()`'s own docstring), so this
    # count is the same one the isolated surface's own re-read, just
    # below, is expected to reproduce.
    n_existing_shared = len(adapter.list_applications(control_actor))
    isolated_applications_override = n_existing_shared + _APPLICATIONS_OVERRIDE_MARGIN

    with adapter.isolated_control_surface(limits_override={"applications": isolated_applications_override}) as isolated:
        isolated_document = isolated.capabilities(control_actor)
        isolated_apps_limit = isolated_document.get("limits", {}).get("applications")
        assert isolated_apps_limit == isolated_applications_override, (
            f"{adapter.name}: isolated_control_surface(limits_override={{'applications': "
            f"{isolated_applications_override!r}}}) did not take effect -- the isolated surface's own "
            f"control_capabilities() declared applications={isolated_apps_limit!r}, expected the override "
            f"{isolated_applications_override!r} (the declaration and the surface under test must be the "
            "SAME instance's)"
        )

        existing_applications = isolated.list_applications(control_actor)
        n_existing = len(existing_applications)
        assert n_existing < isolated_applications_override, (
            f"{adapter.name}: the registry held {n_existing_shared!r} applications when read via the shared "
            f"surface immediately before this override was computed ({isolated_applications_override!r} = "
            f"{n_existing_shared!r} + {_APPLICATIONS_OVERRIDE_MARGIN!r} margin), but re-reading via the "
            f"isolated surface's own list_applications() now shows {n_existing!r} -- either the registry grew "
            "between the two reads (unexpected within one, single-threaded test), or the margin itself has "
            "been reduced to 0"
        )
        required_successes = isolated_applications_override - n_existing
        successes = 0
        limit_hit = False
        for _ in range(required_successes + 1):
            app_id = fresh_identifier("c14_bound_app")
            try:
                isolated.register_application(control_actor, app_id)
                successes += 1
            except ConformanceDenial as exc:
                _assert_is_contract_code(exc.code)
                assert exc.code == "LIMIT_EXCEEDED", (
                    f"{adapter.name}: registering application #{successes + 1} of this drive got {exc.code!r}, "
                    "expected LIMIT_EXCEEDED"
                )
                assert successes == required_successes, (
                    f"{adapter.name}: applications drive was refused with LIMIT_EXCEEDED after only "
                    f"{successes!r} success(es), but the isolated surface's own overridden bound "
                    f"{isolated_applications_override!r} (with {n_existing!r} pre-existing) predicts exactly "
                    f"{required_successes!r} -- refused before the declared bound: cannot attribute the "
                    "refusal to the applications class (it may be a different class's bound firing early)"
                )
                limit_hit = True
                break
        assert limit_hit, (
            f"{adapter.name}: registering {required_successes + 1!r} new applications on the isolated "
            f"surface never triggered LIMIT_EXCEEDED for its own overridden applications bound "
            f"{isolated_applications_override!r} (with {n_existing!r} pre-existing) -- the declared limit is "
            "not actually enforced"
        )

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

    # -- control_requests_per_minute: run LAST, burst against an ISOLATED
    # surface (port v1.10 addendum A, supervisor ruling 2026-09-04,
    # `adapter.isolated_control_surface()`) -- never the shared, session-
    # scoped adapter's own control surface every other vector/test on
    # this file (and every other file) depends on. `control_capabilities`
    # is an operation no PERMANENT bound applies to (design section R-5:
    # it remains callable even by a must_rotate credential) -- that
    # operation choice IS the class attribution (supervisor ruling): a
    # burst of `control_capabilities`-equivalent calls cannot be confused
    # with the applications/credentials_per_application drives above,
    # both already fully cleaned up by this point. The isolated surface's
    # own rate window starts genuinely EMPTY (it shares application/
    # credential state with the shared surface, but its OWN, freshly
    # constructed `_rate_window`) -- unlike the `applications` class
    # above, this drive needs no `n_existing`-style headroom arithmetic:
    # the declared bound predicts EXACTLY `rate_limit` successes before
    # the first refusal, and this vector now asserts that exact position
    # (design's own "位置算術" requirement, not observed by this class
    # before this addendum).
    with adapter.isolated_control_surface() as isolated_call:
        successes = 0
        limit_hit = False
        for _ in range(rate_limit + margin):
            try:
                isolated_call(control_actor)
                successes += 1
            except ConformanceDenial as exc:
                _assert_is_contract_code(exc.code)
                assert exc.code == "LIMIT_EXCEEDED", (
                    f"{adapter.name}: exceeding the declared control_requests_per_minute limit (isolated "
                    f"surface) got {exc.code!r}, expected LIMIT_EXCEEDED"
                )
                assert successes == rate_limit, (
                    f"{adapter.name}: the isolated control surface's own control_requests_per_minute drive "
                    f"was refused with LIMIT_EXCEEDED after only {successes!r} success(es), but the declared "
                    f"bound {rate_limit!r} predicts exactly that many on a genuinely empty, isolated window -- "
                    "refused before the declared bound: cannot attribute the refusal to the "
                    "control_requests_per_minute class (it may be a different class's bound, or a wrongly-"
                    "configured isolated surface, firing early)"
                )
                # Review F4 (2026-09-04), CORRECTED phase 7 WP-4 (design
                # docs/design/PHASE7_EVIDENCE_REPRODUCIBILITY_AND_
                # PUBLICATION_V1.md D-6.4, closing PHASE6_CONTRACT_160_
                # CLIENT_DISCOVERY_V1.md §11 L6-19): this comment
                # previously read "`limit_class` carries no contract
                # guarantee (`errors.shape`'s `details` is a free-form
                # object)" -- that premise was stale/incorrect. The
                # contract's `errors.details_vocabulary.LIMIT_EXCEEDED.
                # limit_class` is "string, required", and `versioning.
                # version_binding` lists it as an unconditional 1.2.0
                # obligation ("errors.details_vocabulary's LIMIT_EXCEEDED.
                # limit_class requirement") -- both currently-registered
                # peers declare `contract_version` 1.6.0, so they claim
                # conformance to it. The check below therefore stays a
                # SOFT check (`if limit_class is not None`) not because
                # the contract permits omission, but because widening it
                # to a hard, unconditional assertion is left to C-14's own
                # scope (this correction is C-05's own D-6.4 cross-
                # reference; it does not itself escalate this assert --
                # phase 7 WP-4 explicitly does not decide that). Same
                # soft-check shape C-16's own `batch_entities` LIMIT_
                # EXCEEDED assertion uses (`test_c16_cross_entity_
                # atomicity.py`'s `limit_class` check, same correction
                # applies there). Both currently-registered peers do emit
                # it (`r2db-api/src/r2db_api/control_plane.py::ControlPlaneService._check_rate`,
                # `MitateDB-api/src/mitatedb_api/control_plane.py::ControlPlaneService._check_rate`),
                # so this is a real, reachable-once-provided-branch check,
                # not a dead assertion. `conformance-tests/test_c05_limit_
                # declaration_agreement.py`'s own V2 vector is the common
                # suite's first HARD `limit_class` check (application
                # plane), grounded in this same contract obligation.
                limit_class = exc.details.get("limit_class")
                if limit_class is not None:
                    assert limit_class == "control_requests_per_minute", (
                        f"{adapter.name}: LIMIT_EXCEEDED for the isolated control surface's own "
                        f"control_requests_per_minute drive carried limit_class={limit_class!r}, expected "
                        "'control_requests_per_minute'"
                    )
                limit_hit = True
                break
        assert limit_hit, (
            f"{adapter.name}: issuing up to {rate_limit + margin!r} control_capabilities()-equivalent calls "
            f"against the isolated surface never triggered LIMIT_EXCEEDED for the declared "
            f"control_requests_per_minute bound {rate_limit!r}"
        )
    # No recovery-wait: the isolated surface is discarded on `with` exit
    # (`adapter.isolated_control_surface()`'s own docstring -- an HTTP
    # plug releases the fresh connection pools it opened; an in-process
    # plug releases nothing, by construction). It shares no RATE-WINDOW
    # state with the adapter's own SHARED control surface, so there is
    # nothing on the shared surface to "recover" and no 60-second wait to
    # pay, and every later test/vector against this same session-scoped
    # adapter observes the shared surface's own rate window exactly as it
    # was before this drive ran (design docs/design/
    # PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md addendum A, work order
    # WP-1 completion condition A-1).
