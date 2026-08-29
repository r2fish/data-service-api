"""C-15 -- bootstrap/reset lifecycle (SI-13, SI-14).

design: docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md section 4 "C-15
(bootstrap/reset lifecycle) の検証ベクタ", registered in
`conformance-tests/CONDITIONS.md`. Every test here carries
`@pytest.mark.condition("C-15")` via the module-level `pytestmark`.

Design section 4 states five vectors for this condition:

1. Bootstrap is refused (`CONFLICT`) while any control credential row
   exists -- including one that has since been revoked (design section 8
   M-6: the contract's own text is "while a control credential exists",
   not "while an *unrevoked* one exists"; reading it the narrower way
   would open a second credential-minting path once every credential is
   revoked, alongside reset).
2. Reset revokes every existing control credential atomically and mints
   exactly one new one; Application data, application credentials, and
   the audit trail are all untouched (the audit trail specifically: the
   pre-reset event sequence survives as a prefix, and exactly one
   non-revoked control credential remains afterward).
3. The credential a ritual (bootstrap/reset) issues is not permanent: it
   is authorized for nothing but `control_capabilities`/self-rotate until
   a real rotation completes, after which it holds full authority.
4. Lifecycle-changing operations emit canonical audit events, and denied
   control-plane requests are durably recorded too, not only successful
   state changes.
5. No default/fixed/empty/guessable secret is ever accepted, and two
   independent ritual runs never mint the same secret.

This file shares its absence-branch machinery (`_control_plane_status`,
`_assert_control_operation_absent_or_uniformly_refused`,
`_assert_uniform_absence_form`) with
`conformance-tests/test_c14_authority_boundary.py` in *shape only* -- each
file defines its own copy rather than importing from the other or from a
new shared module. This is a deliberate choice, not an oversight: the
normative port (`adapter.py`) is deliberately condition-driven and minimal
(design principle 2), so it is not the right home for a helper that exists
only to serve two specific condition test files' own dispatch logic;
creating a third module (e.g. `_c1415_common.py`) purely to deduplicate
~40 lines between two files would add a permanent cross-file coupling
(a change to one condition's helper silently changing the other's
behavior) in exchange for avoiding a small, easily-audited duplication.
Each file staying self-contained and independently readable -- the same
property every other condition file in this suite already has -- was
judged the better trade.

As of this port revision (WP-5 of the CCR-14 design, the declaration
flip), `r2db-api` (in-process) and `r2db-api-http` both declare
`control_plane: enabled` and take the PROVIDED branch for real -- each
runs the real bootstrap/reset ritual (`r2db_api.control_plane.
bootstrap_control_credential`/`reset_control_credentials`, the ceremony
core extracted out of `ops.py` this WP; the in-process adapter calls it
directly, the HTTP adapter runs it via the real `python -m r2db_api.ops`
CLI subprocess). `MitateDB-api` remains surface-absent for every test
below. Per this repository's "skip is fail" rule and design principle 4,
no branch here is ever skipped, for any adapter.

Form (b) (declared-unavailable)'s known, measured acceptance-boundary
limitation (mutation M5/M9: a fabricated `ConformanceDenial(CAPABILITY_
UNSUPPORTED)` is structurally indistinguishable from a genuine one at this
port level) is documented in full in `test_c14_authority_boundary.py`'s
module docstring and `CONDITIONS.md`'s C-14 status text; it applies
identically here and is not re-derived in this file.
"""
from __future__ import annotations

from typing import Any, Callable, Mapping

import pytest

from adapter import (
    ConformanceDenial,
    ControlCredentialHandle,
    Fixture,
    SurfaceAbsent,
    UNCLASSIFIED,
    fresh_identifier,
    load_contract_error_codes,
    signature_forbids_parameters,
)

pytestmark = pytest.mark.condition("C-15")

# WP-5 (design §13.3): widened to include `AUTH_REQUIRED` -- see
# `test_c14_authority_boundary.py`'s identical set/comment for the full
# rationale (an empty-secret probe measured, on both provided-branch r2db-api
# adapters, to answer `AUTH_REQUIRED` rather than `AUTH_INVALID`; both are
# genuine 401-series fail-closed outcomes, §8 m-7).
_FAIL_CLOSED_CODES = frozenset({"AUTH_INVALID", "AUTH_REVOKED", "AUTH_REQUIRED", "FORBIDDEN"})


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
    """Identical in behavior to `test_c14_authority_boundary.py`'s helper
    of the same name (explicit `AssertionError` naming the missing key,
    rather than a bare `KeyError`) -- duplicated here per this file's own
    module docstring.
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


def _synthetic_control_actor() -> ControlCredentialHandle:
    """A placeholder `ControlCredentialHandle` for an absence-branch thunk
    that needs *some* actor value to construct a well-formed call, but
    whose real peer target (`_control_surface_absent`, every registered
    adapter) raises unconditionally before ever inspecting it -- never
    obtained via a real ritual call, since the ritual itself is one of the
    operations under test here and calling it to build this value would
    be circular.
    """
    return ControlCredentialHandle(credential_ref=fresh_identifier("c15_syn_ctl"), secret=fresh_identifier("c15_syn_secret"))


def _assert_control_operation_absent_or_uniformly_refused(adapter, thunk: Callable[[], Any]) -> str:
    """Identical in behavior to `test_c14_authority_boundary.py`'s helper
    of the same name (including the M-7 exact-equality/surface-coverage
    strengthening) -- see that module's docstring for the full rationale
    of each branch. Duplicated here per this file's own module docstring
    (deliberate, not an oversight).
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
            "defect"
        )


def _assert_uniform_absence_form(adapter, thunks: Mapping[str, Callable[[], Any]]) -> None:
    forms = {name: _assert_control_operation_absent_or_uniformly_refused(adapter, thunk) for name, thunk in thunks.items()}
    unique_forms = set(forms.values())
    assert len(unique_forms) == 1, (
        f"{adapter.name}: control-plane absence form is not uniform across operations: {forms!r}. A "
        "control_plane declaration must mean one consistent thing, not a mix depending on which operation "
        "is asked."
    )


# --- 1. bootstrap refused while any control credential row exists ---------


def test_c15_bootstrap_refused_while_any_control_credential_exists(adapter, fx: Fixture):
    if _control_plane_status(adapter) != "enabled":
        _assert_uniform_absence_form(adapter, {"bootstrap": lambda: adapter.bootstrap()})
        return

    # Establish control-credential existence OURSELVES (design independent
    # review, major M-1): an earlier revision of this test relied on some
    # *other* test in this module having already called `control_
    # credential()` first against the same session-scoped adapter -- a
    # cross-test-ordering assumption pytest does not guarantee (test order
    # within a module is stable by default, but nothing here should
    # depend on that). `control_credential()` itself completes the ritual
    # if it has not already run, so this line alone is sufficient.
    control_actor = adapter.control_credential()

    with pytest.raises(ConformanceDenial) as ei:
        adapter.bootstrap()
    _assert_is_contract_code(ei.value.code)
    assert ei.value.code == "CONFLICT", (
        f"{adapter.name}: bootstrap while a control credential already exists got {ei.value.code!r}, "
        "expected CONFLICT"
    )

    # Revoke every existing control credential in-band -- the current
    # actor's OWN credential LAST (design independent review, minor: were
    # it revoked mid-loop, the actor could no longer be trusted to
    # authorize the remaining revokes on some peer's real implementation).
    # No `destructive`/`confirmation` fields are passed: the contract's
    # own Q-1 adjudication (design section 0.5) leaves `revoke_credential_
    # inband`'s confirmation *check* suspended, so this call site
    # correctly supplies neither field today -- once Q-1 is adjudicated,
    # this call will need the canonical confirmation phrase added.
    # Design section 8 M-6: "while a control credential exists" means "a
    # row exists", not "an unrevoked row exists" -- the only legitimate
    # second-mint path after every credential is revoked is reset, never
    # a second bootstrap.
    rows = list(adapter.list_credentials(control_actor))
    control_rows = [row for row in rows if row.get("role") == "control"]
    own_ref = control_actor.credential_ref
    ordered_rows = sorted(control_rows, key=lambda row: row["credential_id"] == own_ref)
    for row in ordered_rows:
        adapter.revoke_credential_inband(control_actor, row["credential_id"])
    with pytest.raises(ConformanceDenial) as ei2:
        adapter.bootstrap()
    _assert_is_contract_code(ei2.value.code)
    assert ei2.value.code == "CONFLICT", (
        f"{adapter.name}: bootstrap after every control credential was revoked (but not deleted) got "
        f"{ei2.value.code!r}, expected CONFLICT -- revoked rows still count as 'exists' (design section 8 M-6)"
    )

    # Clean up: reset re-establishes a usable control credential for any
    # test that runs after this one against the same long-lived adapter.
    adapter.reset()


# --- 2. reset revokes every control credential, spares the application plane


def test_c15_reset_revokes_every_control_credential_and_spares_application_plane(adapter, fx: Fixture):
    if _control_plane_status(adapter) != "enabled":
        _assert_uniform_absence_form(adapter, {"reset": lambda: adapter.reset()})
        return

    # Application-plane state that must survive reset completely untouched.
    before_rows = adapter.select_eq(fx.runtime_a, fx.shared_entity, ["item_key"], None, None)
    app_handle = adapter.issue_credential(fx.app_a, "runtime")
    app_session_before = adapter.authenticate(app_handle)
    scope_before = adapter.scope_of(app_session_before)

    old_control = adapter.control_credential()
    # M-6: snapshot the audit trail before reset, so the prefix-preservation
    # property below has something real to compare against.
    before_audit = list(adapter.control_audit_events())
    new_control = adapter.reset()

    assert new_control.secret != old_control.secret, (
        f"{adapter.name}: reset must mint a genuinely new control-credential secret, not reuse the old one"
    )

    # M-6 (design independent review, implements what CONDITIONS.md already
    # claims): the pre-reset audit event sequence survives as a PREFIX of
    # the post-reset trail -- reset may append new events (the revoke(s)
    # and the new mint), but must never rewrite or remove existing ones.
    after_audit = list(adapter.control_audit_events())
    assert after_audit[: len(before_audit)] == before_audit, (
        f"{adapter.name}: reset did not preserve the pre-reset audit event sequence as a prefix of the "
        "post-reset trail -- events were rewritten or removed instead of only appended to"
    )

    # The old secret is immediately, synchronously unusable -- propagation
    # 0ms, design section R-8: every control-plane authentication is a
    # fresh request-time store lookup with no cache to lag behind.
    with pytest.raises(ConformanceDenial) as ei:
        adapter.control_capabilities(old_control)
    _assert_is_contract_code(ei.value.code)
    assert ei.value.code in _FAIL_CLOSED_CODES, (
        f"{adapter.name}: the pre-reset control secret authenticated after reset -- got {ei.value.code!r} "
        f"instead of one of {sorted(_FAIL_CLOSED_CODES)!r}"
    )

    # Application data, application credentials, and their scope are all
    # unaffected by a control-plane reset.
    after_rows = adapter.select_eq(fx.runtime_a, fx.shared_entity, ["item_key"], None, None)
    assert before_rows == after_rows, f"{adapter.name}: application data changed across a control-plane reset"
    app_session_after = adapter.authenticate(app_handle)
    scope_after = adapter.scope_of(app_session_after)
    assert scope_before == scope_after, (
        f"{adapter.name}: an application credential's scope changed across a control-plane reset "
        f"({scope_before!r} -> {scope_after!r})"
    )

    # New control credential genuinely works.
    adapter.control_capabilities(new_control)

    # WP-5 provided-branch fix (test-code bug, first execution -- WP-1's own
    # §10.4 handoff predicted this class of defect): `reset()`'s own minted
    # credential is must_rotate (design R-5) -- authorized for nothing but
    # `control_capabilities`/self-rotate until a real rotation completes
    # (test_c15_first_issued_credential_is_not_permanent, vector 3, is what
    # actually verifies that gate). `list_credentials` is not on that
    # allow-list, so this vector's own probe below must complete a real
    # self-rotate first, exactly as an operator finishing the ritual would
    # -- this does not change vector 2's own claim under test (exactly one
    # non-revoked control credential remains after reset), only how this
    # test authenticates to observe it.
    rotated = adapter.rotate_credential(new_control, new_control.credential_ref)
    new_secret = rotated["secret"] if isinstance(rotated, Mapping) else getattr(rotated, "secret")
    full_new_control = ControlCredentialHandle(credential_ref=new_control.credential_ref, secret=new_secret)

    # M-6: exactly one non-revoked control credential remains after reset
    # -- the fresh one reset just minted.
    control_rows_after = [row for row in adapter.list_credentials(full_new_control) if row.get("role") == "control"]
    non_revoked_after = [row for row in control_rows_after if not row.get("revoked")]
    assert len(non_revoked_after) == 1 and non_revoked_after[0]["credential_id"] == new_control.credential_ref, (
        f"{adapter.name}: after reset, list_credentials() does not show exactly one non-revoked control "
        f"credential matching the freshly reset credential ({new_control.credential_ref!r}) -- got "
        f"{non_revoked_after!r}"
    )


# --- 3. the first-issued credential is not permanent -----------------------


def test_c15_first_issued_credential_is_not_permanent(adapter, fx: Fixture):
    """The must-rotate gate (design section R-5) is one implementation of
    the contract's "expires or requires rotation" bootstrap[5] clause.
    This test verifies that specific realization; a future peer choosing
    a time-based expiry instead would need a time-injection extension to
    this port (this port has no clock-control primitive), which is out of
    this test's scope to anticipate.
    """
    if _control_plane_status(adapter) != "enabled":
        _assert_uniform_absence_form(adapter, {
            "reset": lambda: adapter.reset(),
            "rotate_credential": lambda: adapter.rotate_credential(_synthetic_control_actor(), fresh_identifier("c15_cred")),
        })
        return

    fresh = adapter.reset()  # a freshly-minted, must_rotate control credential.

    # Every operation but capabilities/self-rotate is refused.
    with pytest.raises(ConformanceDenial) as ei:
        adapter.list_applications(fresh)
    _assert_is_contract_code(ei.value.code)
    assert ei.value.code == "FORBIDDEN", (
        f"{adapter.name}: a must_rotate control credential attempting list_applications got {ei.value.code!r}, "
        "expected FORBIDDEN"
    )

    # capabilities remains callable even before rotation.
    adapter.control_capabilities(fresh)

    # Self-rotate clears the must-rotate gate. `rotate_credential`'s own
    # port docstring (M-2): the peer's real rotate response is not
    # unified into a port-level type, so this inspects it directly for a
    # `secret`-shaped field.
    rotated = adapter.rotate_credential(fresh, fresh.credential_ref)
    new_secret = rotated["secret"] if isinstance(rotated, Mapping) else getattr(rotated, "secret")
    full_actor = ControlCredentialHandle(credential_ref=fresh.credential_ref, secret=new_secret)
    adapter.list_applications(full_actor)  # now succeeds -- full authority restored.


# --- 4. canonical audit + durable denial recording --------------------------


def test_c15_lifecycle_changes_emit_canonical_audit_and_denials_are_recorded(adapter, fx: Fixture):
    """Sink-failure-injection fail-closed verification (design section R-6)
    is implementation-side test scope (work packages WP-2/WP-3), not this
    common-suite condition's: this port has no fault-injection primitive,
    and adding one purely to observe an internal failure mode would make
    the port less peer-agnostic, not more. This test verifies only what
    is genuinely observable through the port as it stands: canonical
    event emission for state changes, and durable recording of denials.
    """
    if _control_plane_status(adapter) != "enabled":
        _assert_uniform_absence_form(adapter, {"control_audit_events": lambda: adapter.control_audit_events()})
        return

    control_actor = adapter.control_credential()
    before_count = len(adapter.control_audit_events())

    new_app = fresh_identifier("c15_audit_app")
    adapter.register_application_inband(control_actor, new_app)
    issued = adapter.issue_credential_inband(control_actor, new_app, "runtime")
    adapter.set_application_enabled_inband(control_actor, new_app, False)

    after_state_change = adapter.control_audit_events()
    assert len(after_state_change) >= before_count + 3, (
        f"{adapter.name}: 3 lifecycle state changes (register/issue/disable) added fewer than 3 audit events "
        f"({len(after_state_change) - before_count})"
    )

    forbidden_field_fragments = ("secret", "verifier", "password", "token")
    for event in after_state_change:
        for key, value in event.items():
            key_l = key.lower()
            for forbidden in forbidden_field_fragments:
                assert forbidden not in key_l, (
                    f"{adapter.name}: control_audit_events() event field {key!r} looks secret-shaped "
                    f"(contains {forbidden!r})"
                )
            if isinstance(value, str):
                assert value != issued.secret, (
                    f"{adapter.name}: control_audit_events() event field {key!r} carries a real credential "
                    "secret verbatim"
                )
                # Minor (design independent review): also check the
                # CONTROL actor's own secret, not only the application
                # credential's -- state changes here were all performed
                # by `control_actor`, so its secret is exactly as much at
                # risk of verbatim leakage as the application credential's.
                assert value != control_actor.secret, (
                    f"{adapter.name}: control_audit_events() event field {key!r} carries the control actor's "
                    "own credential secret verbatim"
                )

    # A denial event: an authentication failure against the control plane
    # (a bogus secret on a real credential_ref) must be durably recorded
    # too (design section 8 B-3 -- sink_failure_policy names denials
    # first, not only state changes).
    bogus_actor = ControlCredentialHandle(credential_ref=control_actor.credential_ref, secret=fresh_identifier("c15_bogus"))
    with pytest.raises(ConformanceDenial):
        adapter.control_capabilities(bogus_actor)
    after_denial = adapter.control_audit_events()
    assert len(after_denial) >= len(after_state_change) + 1, (
        f"{adapter.name}: an authentication denial against the control plane did not add a durable audit event"
    )


# --- 5. no default credential -----------------------------------------------


def test_c15_no_default_credential(adapter, fx: Fixture):
    """Full verification of "two independently-bootstrapped *environments*'
    initial secrets never coincide" needs two separate deployments, a
    concept this port has no primitive for. The port-expressible
    approximation here is two independent ritual runs against the *same*
    adapter's own control-credential store, which must still mint
    different secrets from each other; the stronger, genuinely
    cross-environment claim is implementation/review evidence, not
    something one adapter's own state can fully stand in for.
    """
    if _control_plane_status(adapter) != "enabled":
        _assert_uniform_absence_form(adapter, {"bootstrap": lambda: adapter.bootstrap()})
        return

    guessable_secrets = ("", "admin", "changeme")
    application_secret = adapter.issue_credential(fx.app_a, "runtime").secret
    existing_ref = adapter.control_credential().credential_ref
    for secret in (*guessable_secrets, application_secret):
        bogus_actor = ControlCredentialHandle(credential_ref=existing_ref, secret=secret)
        with pytest.raises(ConformanceDenial) as ei:
            adapter.control_capabilities(bogus_actor)
        _assert_is_contract_code(ei.value.code)
        assert ei.value.code in _FAIL_CLOSED_CODES, (
            f"{adapter.name}: guessable/foreign secret {secret!r} authenticated against the control plane -- "
            f"got {ei.value.code!r} instead of one of {sorted(_FAIL_CLOSED_CODES)!r}"
        )

    first = adapter.reset()
    second = adapter.reset()
    assert first.secret != second.secret, (
        f"{adapter.name}: two independent reset rituals against the same control-credential store minted "
        "the same secret"
    )
