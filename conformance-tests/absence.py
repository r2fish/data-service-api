"""Shared "structurally absent OR uniformly refused" assertion mechanism.

Extracted (port v1.6, design docs/design/DESTRUCTIVE_CONFIRMATION_V1.md R-6
item 4 / WP-0 m-4) out of `test_c14_authority_boundary.py`, where this
mechanism originated as private, module-local helpers
(`_assert_control_operation_absent_or_uniformly_refused`/
`_assert_uniform_absence_form`/`_unclassified_hint`/`_assert_is_contract_
code`). This is a pure move, not a revision: pass/fail behavior for C-14 is
equivalent to the pre-extraction private functions (C-14's own suite stays
green against this module) -- NOT byte-for-byte identical, since the move
itself generalized two things the pre-extraction functions hardcoded to
C-14's own control-plane vocabulary (review correction m-7, so this
docstring does not overstate the extraction's own scope): assertion
messages that said "control-plane" now say the capability-neutral phrasing
above, and the `{"credential", "control"}` forbidden-vocabulary check
became the optional `required_forbidden_vocabulary` parameter (empty by
default; `test_c14_authority_boundary.py` supplies its own vocabulary at
its call sites to preserve that check unchanged for its own callers). It
now lives here so C-06's
`drop_entity` absent branch (a peer with no schema-drop entry point at all,
e.g. `MitateDB-api`) can reuse the identical mechanism C-14 already
established for its own control-plane absence claims, rather than
duplicating or drifting from it.

See `test_c14_authority_boundary.py`'s module docstring for the two forms
this mechanism distinguishes (design docs/design/
R2DB_CCR14_CONTROL_PLANE_V1.md section 4):

- (a) **surface-absent**: no real call on the peer's public surface could
  even receive the request. The port operation raises `SurfaceAbsent`,
  independently re-verified via `signature_forbids_parameters` rather than
  trusted on its word.
- (b) **declared-unavailable**: a real entry point exists, but the peer's
  own capability document declares the relevant capability `unavailable`
  (or, for a condition without its own capability-status entry, refuses
  every real entry point uniformly with `CAPABILITY_UNSUPPORTED` for some
  other structural reason), so every real entry point refuses uniformly
  with `CAPABILITY_UNSUPPORTED`.

Both forms are genuinely verified here, never accepted on an adapter's bare
word (design principle 4: uncertainty must not silently become permission).

**`audit_query`'s declare-first form is NOT the two-form model above (port
v1.8, phase 4 WP-1, design docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md
§8.4, work order supplementary ruling 1)**: `ConformanceAdapter.
audit_query`/`audit_visibility_lag_ms` collapse form
(b) into form (a) for this one capability specifically -- an `audit_query`
declared anything other than `enabled`/`partial` (most commonly
`unavailable`) raises `SurfaceAbsent`, WITHOUT presenting any request to
the peer, even when a real, routed HTTP entry point exists that would
itself answer `CAPABILITY_UNSUPPORTED` if reached directly (design D-5/
M-4's dual posture: AUDIT DSN unset still registers the route). This is a
genuine, deliberate extension of what `SurfaceAbsent` means for this one
port method group -- see `SurfaceAbsent`'s own class docstring in
`adapter.py` for the full rationale -- not a bug in this module's general
mechanism. `assert_control_operation_absent_or_uniformly_refused` (below)
still applies unmodified to every OTHER control-plane capability, which
keep the ordinary two-form split; a caller checking `audit_query`'s own
absence must not run it through this shared helper expecting form (b) to
be a legitimate alternative outcome there -- only `SurfaceAbsent` is
ever correct for an undeclared/unavailable `audit_query`
(`test_c09_audit_evidence.py` implements this narrower, `audit_query`-
specific check directly, rather than reusing this module's two-form
assertion for it).
"""
from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

from adapter import (
    UNCLASSIFIED,
    ConformanceDenial,
    SurfaceAbsent,
    load_contract_error_codes,
    signature_forbids_parameters,
)


def unclassified_hint(code: str) -> str:
    if code != UNCLASSIFIED:
        return ""
    return (
        " -- code is adapter.UNCLASSIFIED: the peer raised a native exception the adapter could not map "
        "to a contract code. This is a finding under SI-05/SI-10, not a denial."
    )


def assert_is_contract_code(code: str) -> None:
    contract_codes = load_contract_error_codes()
    assert code in contract_codes, f"denial code {code!r} is not a contract error code{unclassified_hint(code)}"


def assert_control_operation_absent_or_uniformly_refused(
    adapter, thunk: Callable[[], Any], *, required_forbidden_vocabulary: Sequence[str] = ()
) -> str:
    """Runs `thunk`. Exactly one of two shapes is acceptable whenever the
    capability under test is not declared available (design section 4's two
    absence forms):

    - (a) surface-absent: `thunk` raises `SurfaceAbsent`. Its claim is
      independently re-verified (design docs/design/
      R2DB_CCR14_CONTROL_PLANE_V1.md WP-1 independent review, major M-7):

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
    - (b) declared-unavailable: `thunk` raises `ConformanceDenial` with
      `code == "CAPABILITY_UNSUPPORTED"` -- any other code is a finding:
      an unavailable declaration must refuse uniformly, not with an
      unrelated error (a `NOT_FOUND`, for instance, would mean the peer
      resolved the target before ever checking capability availability).

    `thunk` succeeding without raising is always a failure regardless of
    form: an "unavailable"/absent declaration under which the operation
    actually executes is exactly the reverse-direction defect design
    section 4 vector 4 (declared status disagreeing with real behavior)
    describes.

    Returns `"surface_absent"` or `"declared_unavailable"` so the caller
    can additionally assert every operation it exercises takes the *same*
    form (`assert_uniform_absence_form`, below).

    `required_forbidden_vocabulary` (port v1.6, design docs/design/
    DESTRUCTIVE_CONFIRMATION_V1.md R-6 item 4 extraction): an optional set
    of name fragments (case-insensitive) that must be a subset of the
    `SurfaceAbsent`'s declared `forbidden_parameters` -- guards against a
    declared `forbidden_parameters` set that is narrow enough to make the
    signature check above pass vacuously (C-14's own precedent:
    `{"credential", "control"}` for its control-plane vocabulary). Empty by
    default: this vocabulary is specific to whichever capability a caller
    is checking (C-14's is credential/control-shaped; a caller checking a
    different absent capability, e.g. C-06's `drop_entity`, supplies its
    own fragments or none at all) and does not generalize to every use of
    this shared helper.
    """
    try:
        thunk()
    except SurfaceAbsent as exc:
        violations = set(signature_forbids_parameters(exc.surface, exc.forbidden_parameters))
        exempt = set(exc.exempt_parameters)
        assert violations == exempt, (
            f"{adapter.name}: SurfaceAbsent's signature_forbids_parameters violations "
            f"{sorted(violations)!r} do not exactly equal its declared exempt_parameters "
            f"{sorted(exempt)!r} -- an unexempted violation means a real parameter could carry the absent "
            "capability (claim false); a stale or padded exemption naming a parameter that is not actually "
            "a violation is itself suspect (design docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md WP-1 "
            "independent review major M-7)"
        )
        if required_forbidden_vocabulary:
            declared = {f.lower() for f in exc.forbidden_parameters}
            required = {f.lower() for f in required_forbidden_vocabulary}
            assert required <= declared, (
                f"{adapter.name}: SurfaceAbsent's forbidden_parameters {exc.forbidden_parameters!r} does not "
                f"include all of {sorted(required)!r} -- a narrower fragment set could pass "
                "signature_forbids_parameters vacuously without actually covering the vocabulary this claim "
                "is supposed to rule out"
            )
        public_surface = set(adapter.public_operation_callables())
        declared_surface = set(exc.surface)
        assert declared_surface >= public_surface, (
            f"{adapter.name}: SurfaceAbsent's declared surface omits "
            f"{[c for c in public_surface if c not in declared_surface]!r} of the peer's own real "
            "public_operation_callables() -- shrinking the evidence surface below the peer's real public "
            "surface would let a genuine matching parameter elsewhere on the peer go unchecked "
            "(independent review major M-7)"
        )
        return "surface_absent"
    except ConformanceDenial as exc:
        assert_is_contract_code(exc.code)
        assert exc.code == "CAPABILITY_UNSUPPORTED", (
            f"{adapter.name}: this capability is declared unavailable, but this operation was refused with "
            f"{exc.code!r} instead of CAPABILITY_UNSUPPORTED -- an unavailable declaration must refuse "
            "every real entry point uniformly (design section 4 form (b))"
        )
        return "declared_unavailable"
    else:
        raise AssertionError(
            f"{adapter.name}: this capability is not declared available, but the operation succeeded -- an "
            "unavailable/absent declaration under which the operation actually executes is a genuine defect "
            "(design section 4 vector 4's reverse direction)"
        )


def assert_uniform_absence_form(
    adapter, thunks: Mapping[str, Callable[[], Any]], *, required_forbidden_vocabulary: Sequence[str] = ()
) -> None:
    """Runs every thunk in `thunks` through
    `assert_control_operation_absent_or_uniformly_refused` and requires
    every one to report the *same* form. A capability-unavailable
    declaration means one consistent thing -- surface-absent XOR
    declared-unavailable -- not a per-operation coin flip; a peer that
    answers some operations with `SurfaceAbsent` and others with a real
    `CAPABILITY_UNSUPPORTED` denial is declaring something internally
    inconsistent about its own topology, which this suite treats as a
    finding rather than silently accepting whichever form each individual
    operation happened to take.

    `required_forbidden_vocabulary` is passed through unchanged to every
    call.
    """
    forms = {
        name: assert_control_operation_absent_or_uniformly_refused(
            adapter, thunk, required_forbidden_vocabulary=required_forbidden_vocabulary
        )
        for name, thunk in thunks.items()
    }
    unique_forms = set(forms.values())
    assert len(unique_forms) == 1, (
        f"{adapter.name}: absence form is not uniform across operations: {forms!r}. An unavailable/absent "
        "declaration must mean one consistent thing, not a mix depending on which operation is asked."
    )
