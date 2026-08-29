"""C-06 -- destructive confirmation (SI-09).

design: docs/design/DESTRUCTIVE_CONFIRMATION_V1.md R-6, subordinate ruling
6 (contract `destructive_confirmation` section, contract 1.2.0). Every test
here carries `@pytest.mark.condition("C-06")` via the module-level
`pytestmark`.

## Branch dispatch (design R-6, mirrors C-14's `_control_plane_status`
dispatch pattern)

Every test below branches on the peer's own declared `capability_
document()["contract_version"]`, compared as a semver TUPLE
(`adapter.contract_version_at_least`) -- never as a string (design's own
named trap: a naive string compare ranks "1.10.0" below "1.2.0"):

- **strict branch (contract_version >= 1.2.0)**: the full declare-and-echo
  semantics this file's vectors V1-V8 verify (`phrase_construction`,
  `valid_confirmation`, the four-key `denial.details_keys` vocabulary, the
  last-control-credential revoke gate).
- **baseline branch (< 1.2.0)**: the pre-1.2.0 semantics this port has
  always required of `VALID_CONFIRMATION`-based coverage -- an unconfirmed
  destructive delete is never executed (whatever code the peer answers
  with) and a request carrying `VALID_CONFIRMATION` succeeds. This is
  exactly the "existing coverage stays green" floor `test_c01_scope_
  binding.py`/`test_c03_structured_injection.py`/`test_c17_declaration_
  agreement.py`/`test_c18_revision_precondition_semantics.py` already
  exercise indirectly through `delete(..., confirmation=VALID_
  CONFIRMATION)`; this module names it explicitly as C-06's own floor.

**As of this work package (WP-2), every registered adapter (`r2db-api`,
`r2db-api-http`, `MitateDB-api`) declares `contract_version: 1.1.0`** (the
r2db/MitateDB flip to 1.2.0 is WP-3/WP-5's own single-commit work, per
design's per-peer flip rule). Every test below therefore takes the baseline
branch for real, for every currently-registered adapter -- the strict-branch
code paths are written to this design's exact spec and exercised only by
`test_contract_version_at_least_*`/`test_resolve_valid_confirmation_*`'s
own direct unit tests of the *pure* dispatch/derivation functions
(`adapter.parse_semver`/`contract_version_at_least`/`resolve_valid_
confirmation`) at the bottom of this file -- proving the vector bodies'
own skeletons import and branch correctly, not that a real >= 1.2.0 peer
satisfies them end-to-end. **First real execution of the strict branch
against a genuine 1.2.0 peer is explicitly WP-3's own completion condition
(r2db-api) and WP-5's (MitateDB-api)**, not this WP's -- see this file's
own `CONDITIONS.md` C-06 row for the same disclosure.

## Vectors (design R-6, strict branch)

- V1: unconfirmed destructive delete -> `DESTRUCTIVE_CONFIRMATION_REQUIRED`,
  all four `details` keys present, string keys non-empty, row count
  unchanged.
- V2/V2b: `destructive: false` (this port's `delete()` always passes
  `destructive` explicitly -- see that test's own docstring for why V2b's
  literal "field omitted on the wire" is not independently expressible
  through this port and collapses onto the same assertion as V2) with an
  otherwise-correct phrase -> still denied.
- V3: full-match adversarial checks -- phrase+suffix, a proper prefix of
  the real phrase (this mechanically covers the old fixed-token "DELETE"
  residual-acceptance defect once a real peer's phrase embeds that
  literal, without this suite hardcoding that literal itself), a
  case-changed phrase, another entity's correct phrase, another
  operation's correct phrase (`drop_entity`'s phrase presented to
  `delete`), and the correct phrase for a *different* selection/where on
  the same entity -- every one denied, state unchanged.
- V4: phrase determinism -- two probes of the identical request yield the
  identical phrase; a second, independent credential for the same
  Application, of a DIFFERENT role (`developer`, not another `runtime`;
  review n-2), probing the identical request also yields the identical
  phrase (phrase_construction depends only on operation/target/consequence,
  never on requester identity or role).
- V5: probe -> echo the declared phrase verbatim -> the operation executes
  (this vector genuinely mutates the shared Fixture's seeded row for real).
- V6: state-fingerprint invalidation for `drop_entity`, against a
  throwaway entity created fresh inside this test (review m-5 -- not
  `fx.a_only_entity`, removing an implicit ordering dependency on V3's own
  use of that entity) -- probe, re-probe the SAME request and require the
  identical phrase (establishing determinism BEFORE testing invalidation,
  review M-1), an unrelated schema change to the SAME entity, re-probe
  (old phrase now denied), the freshly re-probed phrase succeeds.
  Surface-absent peers (no schema-drop entry point) take the shared
  absence mechanism (`absence.assert_control_operation_absent_or_
  uniformly_refused`, the same mechanism `test_c14_authority_boundary.py`
  uses for the control-plane surface, given its own `("drop", "destroy")`
  forbidden-vocabulary guard, review M-5) instead of this vector's real
  assertions, and additionally requires the absence claim to agree with
  this peer's own declared `capabilities.schema_operations` (review M-6).
  Also applies a V3-equivalent adversarial subset to `drop_entity` itself.
- V7: the in-band last-control-credential revoke gate -- control-plane-
  provided peers only; a surface-absent peer takes the same shared absence
  mechanism (its own `("credential", "control")` vocabulary guard) against
  `revoke_credential_inband`. Checks only the contract's own four-key
  requirement, deliberately NOT `audited: true` -- an r2db-specific,
  contract-optional declaration this vector must not promote into a
  common-suite requirement (supervisor ruling, review M-7; see that
  test's own docstring).
- V8: payload-echo -- an adversarial value probed through a real
  destructive request must not appear verbatim, at any nesting depth, in
  any `details` value (`adapter.assert_no_payload_echo_in_details`, made
  recursive by review M-4).

A registry-wide vacuity guard (review blocker B-1,
`test_c06_branch_dispatch_vacuity_guard`) independently re-verifies every
registered adapter's strict/baseline classification and asserts the
resulting adapter-name sets explicitly, so this dispatch cannot silently
drift from what the suite actually exercises.

Design principle 4 (skip is fail) applies here exactly as everywhere else
in this repository: no branch below is ever a `pytest.skip`. The
baseline/strict dispatch above is a real, asserted branch with its own
real assertions on both sides, never a silent no-op.
"""
from __future__ import annotations

from typing import Any, Mapping

import pytest

from absence import assert_control_operation_absent_or_uniformly_refused
from adapter import (
    ConformanceDenial,
    Fixture,
    SurfaceAbsent,
    VALID_CONFIRMATION,
    assert_no_payload_echo_in_details,
    contract_version_at_least,
    fresh_identifier,
    parse_semver,
    resolve_valid_confirmation,
)
from conftest import registered_adapters

pytestmark = pytest.mark.condition("C-06")

_REQUIRED_DETAIL_KEYS = ("required_confirmation", "consequence", "reversible_alternative", "recovery")

# ---------------------------------------------------------------------------
# Module-local `fx` override (one half of a two-part fix for a real,
# measured regression -- see the OTHER half at `_contract_version` below,
# and docs/design/CONFORMANCE_ADAPTER_V1.md section 16.5's full incident
# record): this suite never reads `Fixture`'s B-side fields (`app_b`/
# `runtime_b`/`b_only_entity`) -- every vector below operates within a
# single Application. conftest.py's own `fx` fixture is function-scoped by
# design (so C-01-style cross-test isolation tests never share state),
# which would otherwise cost this file 8 vector tests x a full
# two-Application `build_fixture()` each = 16 out-of-band `provision_
# application` calls per r2db adapter to the SAME shared, session-scoped
# registry `test_c15_bootstrap_reset_lifecycle.py`'s own audit test reads
# from at session end -- measured (full-suite runs, stashed-tree control)
# to push that registry's real out-of-band `applications` count past the
# `applications` SI-08 bound (100) there, a real regression this WP found
# and fixed before landing, not a pre-existing gap and not something raising
# the limit or touching C-15 should paper over. This override -- a fixture
# of the SAME name defined in this test module, which pytest resolves in
# preference to conftest.py's for tests in this module -- builds ONE real
# `Fixture` per adapter (via the unmodified, real `adapter.build_fixture()`;
# nothing about the fixture itself is faked or shrunk) and memoizes it for
# this whole module's run. Precisely which check may share the cached
# Fixture's data safely differs by branch, corrected here per review m-5
# (an earlier revision of this comment overclaimed this uniformly):
# `_assert_baseline_delete_invariant` -- the ONLY code path that actually
# runs against any currently-registered adapter (every one still declares
# `contract_version: 1.1.0`) -- operates on a freshly `insert()`-ed,
# uniquely-marked row of its own rather than the shared fixture's single
# seeded row, specifically so its own repeated invocations (once per
# vector test, 8 times, against the SAME cached Fixture) never step on
# each other. The STRICT branch's own vectors (dead code today, exercised
# only once each per adapter across this module's whole run when they do
# run) are not bound by that same constraint and mutate the shared
# Fixture's real state directly where the vector itself calls for it: V5
# deletes the seeded row for real (a genuine, one-time echo-then-execute);
# V6 no longer touches the shared fixture's own entities at all (review
# m-5 also moved V6's drop target to a throwaway entity of its own,
# created fresh inside that test, removing an implicit ordering dependency
# on V3's own use of `fx.a_only_entity`); V7 mutates control-plane
# credential state, entirely independent of this Fixture.
# ---------------------------------------------------------------------------

_SHARED_FIXTURE_CACHE: dict[str, Fixture] = {}


@pytest.fixture()
def fx(adapter) -> Fixture:
    cached = _SHARED_FIXTURE_CACHE.get(adapter.name)
    if cached is not None:
        return cached
    fixture = adapter.build_fixture()
    _SHARED_FIXTURE_CACHE[adapter.name] = fixture
    return fixture


# ---------------------------------------------------------------------------
# Branch dispatch
# ---------------------------------------------------------------------------


_CAPABILITY_DOCUMENT_CACHE: dict[str, Mapping[str, Any]] = {}


def _capability_document(adapter) -> Mapping[str, Any]:
    """The peer's own real `capability_document()`, memoized per adapter
    for this module's whole run (review correction m-1: merges what were,
    in an earlier revision of this file, two independent uncached-per-call
    sources -- `_contract_version` and `_control_plane_status` each called
    `capability_document()` on their own).

    Every registered adapter's `capability_document()` provisions a FRESH,
    disposable probe Application on every single call (it is scoped to an
    authenticated session and has no anonymous path -- see each plug's own
    `capability_document()` docstring). `_contract_version`, below, is
    called from the top of every one of C-06's 8 vector tests via
    `_branch_for`; `_control_plane_status` and `_schema_operations_
    capability` are each called from more than one vector too -- leaving
    any of them uncached would provision one throwaway Application PER
    CALL, measured (together with the `fx` override above) to be the
    direct cause of a real regression this WP found and fixed before
    landing (`test_c15_bootstrap_reset_lifecycle.py`'s own audit test
    hitting the shared `applications` SI-08 bound). Fetching the WHOLE
    document once and deriving every one of this file's own capability
    reads from that single cached copy keeps this file's total added
    footprint at exactly 3 Applications per r2db adapter for its entire
    run (1 capability probe + `fx`'s own 2) -- unlike `test_c14_authority_
    boundary.py`'s own `_control_plane_status` (a single call per test,
    re-fetched every time, left alone as out of this WP's scope: that
    file's own vector count/footprint was not part of the regression this
    WP measured and fixed).
    """
    cached = _CAPABILITY_DOCUMENT_CACHE.get(adapter.name)
    if cached is not None:
        return cached
    document = adapter.capability_document()
    _CAPABILITY_DOCUMENT_CACHE[adapter.name] = document
    return document


def _contract_version(adapter) -> str:
    """The peer's own declared `contract_version`, derived from the
    single cached `_capability_document(adapter)`."""
    document = _capability_document(adapter)
    version = document.get("contract_version")
    assert isinstance(version, str) and version, (
        f"{adapter.name}: capability_document() has no non-empty string 'contract_version' -- {document!r}"
    )
    return version


def _branch_for(adapter) -> str:
    """Returns `"strict"` or `"baseline"` -- the C-06 analogue of C-14's
    own `_assert_control_operation_absent_or_uniformly_refused` return
    value, recorded here so every vector test below dispatches on, and
    reports, the SAME resolved branch rather than each re-deriving it
    independently."""
    return "strict" if contract_version_at_least(_contract_version(adapter), "1.2.0") else "baseline"


def _control_plane_status(adapter) -> str:
    """This file's own copy of `test_c14_authority_boundary.py`'s
    identically-named helper (design section 15.6's own "no shared
    _c1415_common.py" precedent -- this repository deliberately does not
    generalize condition-specific plumbing beyond what a design revision
    explicitly authorizes; only the absence mechanism itself was so
    authorized for this WP, design R-6 item 4), adapted here to read from
    the single cached `_capability_document(adapter)` (m-1) rather than
    calling `capability_document()` again on every invocation the way
    C-14's own copy still does."""
    document = _capability_document(adapter)
    capabilities = document.get("capabilities")
    assert isinstance(capabilities, dict), (
        f"{adapter.name}: capability_document() has no 'capabilities' mapping -- {document!r}"
    )
    control_plane = capabilities.get("control_plane")
    assert isinstance(control_plane, dict) and "status" in control_plane, (
        f"{adapter.name}: capability_document()['capabilities'] has no 'control_plane' entry carrying a "
        f"'status' key -- got {control_plane!r}"
    )
    return control_plane["status"]


def _schema_operations_capability(adapter) -> Mapping[str, Any]:
    """The peer's own declared `capabilities.schema_operations` entry
    (review correction M-6), derived from the same single cached
    `_capability_document(adapter)`. Used by V6's absent branch to check
    the `SurfaceAbsent` claim for `drop_entity` agrees with what this peer
    itself declares -- an internal-consistency check in the same spirit as
    C-14 vector 4 (declared status agrees with actual surface), applied
    here to the schema-operations capability instead of control_plane.
    """
    document = _capability_document(adapter)
    capabilities = document.get("capabilities")
    assert isinstance(capabilities, dict), (
        f"{adapter.name}: capability_document() has no 'capabilities' mapping -- {document!r}"
    )
    schema_ops = capabilities.get("schema_operations")
    assert isinstance(schema_ops, dict), (
        f"{adapter.name}: capability_document()['capabilities'] has no 'schema_operations' entry -- "
        f"got {schema_ops!r}"
    )
    return schema_ops


# ---------------------------------------------------------------------------
# Shared probe/assertion helpers
# ---------------------------------------------------------------------------


def _assert_four_declarations(details: Mapping[str, Any], *, context: str = "") -> None:
    """design R-1-2 `details_rules`: all four keys present on every
    denial; `required_confirmation`/`consequence` are non-empty strings;
    `reversible_alternative`/`recovery` are each a non-empty string or
    `None` (never an empty string, never omitted)."""
    suffix = f" ({context})" if context else ""
    for key in _REQUIRED_DETAIL_KEYS:
        assert key in details, f"denial details missing required key {key!r}{suffix}: {details!r}"
    for key in ("required_confirmation", "consequence"):
        value = details[key]
        assert isinstance(value, str) and value, f"details[{key!r}] must be a non-empty string{suffix}: {value!r}"
    for key in ("reversible_alternative", "recovery"):
        value = details[key]
        assert value is None or (isinstance(value, str) and value), (
            f"details[{key!r}] must be a non-empty string or null{suffix}: {value!r}"
        )


def _assert_probe_denial_code(adapter, denial: ConformanceDenial, *, operation: str) -> None:
    """Review correction M-2: fail loudly, with the same wording
    `resolve_valid_confirmation` itself uses for the identical check, the
    moment a probe denies with anything other than `DESTRUCTIVE_
    CONFIRMATION_REQUIRED` -- rather than letting every call site read
    `denial.details["required_confirmation"]` next and crash with an
    undiagnostic `KeyError` for what is actually a wrong-code finding.
    """
    assert denial.code == "DESTRUCTIVE_CONFIRMATION_REQUIRED", (
        f"{adapter.name}: probe (destructive=True, no confirmation) for {operation} expected "
        f"DESTRUCTIVE_CONFIRMATION_REQUIRED, got {denial.code!r}"
    )


def _probe_delete(adapter, session, entity: str, field: str, value: Any) -> ConformanceDenial:
    """Presents the destructive `delete` with NO confirmation, exactly as
    `resolve_valid_confirmation`'s own probe contract requires, and returns
    the resulting denial. A probe succeeding outright is always a suite
    failure regardless of caller -- SI-09 must never let an unconfirmed
    destructive operation through -- so this deliberately does not catch
    a non-raise; `pytest.raises` does that for every call site instead.
    """
    with pytest.raises(ConformanceDenial) as excinfo:
        adapter.delete(session, entity, field, value, destructive=True, confirmation=None)
    denial = excinfo.value
    _assert_probe_denial_code(adapter, denial, operation="delete")
    return denial


def _probe_drop_entity(adapter, session, entity: str) -> ConformanceDenial:
    with pytest.raises(ConformanceDenial) as excinfo:
        adapter.drop_entity(session, entity, destructive=True, confirmation=None)
    denial = excinfo.value
    _assert_probe_denial_code(adapter, denial, operation="drop_entity")
    return denial


def _assert_delete_denied(
    adapter, session, entity: str, field: str, value: Any, *, destructive: bool, confirmation: Any
) -> ConformanceDenial:
    """A single delete attempt that MUST be denied, whatever confirmation
    is supplied. Used by V2/V2b/V3 for every "still not a valid
    confirmation" variant."""
    with pytest.raises(ConformanceDenial) as excinfo:
        adapter.delete(session, entity, field, value, destructive=destructive, confirmation=confirmation)
    return excinfo.value


def _assert_baseline_delete_invariant(adapter, fx: Fixture) -> None:
    """The baseline-branch floor design R-6 defines for every vector on a
    peer declaring `contract_version < 1.2.0`: an unconfirmed destructive
    delete is never executed (whatever code the peer answers -- baseline
    semantics predate the four-key details vocabulary entirely, so this
    does not inspect `details` at all), and `VALID_CONFIRMATION` succeeds.

    Operates on a freshly `insert()`-ed row of its own, uniquely marked via
    `probe_key` -- never the shared fixture's single seeded row -- so this
    is safe to call repeatedly against the SAME cached `Fixture` (this
    module's own `fx` override, above, memoizes one `Fixture` per adapter
    across all 8 vector tests rather than building a fresh one per test).
    """
    session = fx.runtime_a
    entity = fx.shared_entity
    marker = fresh_identifier("c06_baseline_row")
    adapter.insert(session, entity, {"item_key": 2, "label": "c06-baseline", "probe_key": marker, "probe_value": marker})
    before = adapter.count(session, entity)

    with pytest.raises(ConformanceDenial):
        adapter.delete(session, entity, "probe_key", marker, destructive=True, confirmation=None)
    assert adapter.count(session, entity) == before, (
        f"{adapter.name}: an unconfirmed destructive delete changed row count under baseline "
        "(<1.2.0) semantics -- SI-09 violation regardless of contract_version"
    )

    affected = adapter.delete(session, entity, "probe_key", marker, destructive=True, confirmation=VALID_CONFIRMATION)
    assert affected == 1, f"{adapter.name}: VALID_CONFIRMATION delete did not affect exactly this test's own marked row"
    assert adapter.count(session, entity) == before - 1


# ---------------------------------------------------------------------------
# V1: unconfirmed destructive delete
# ---------------------------------------------------------------------------


def test_c06_v1_unconfirmed_destructive_delete_denied(adapter, fx: Fixture):
    if _branch_for(adapter) != "strict":
        _assert_baseline_delete_invariant(adapter, fx)
        return

    session = fx.runtime_a
    entity = fx.shared_entity
    before = adapter.count(session, entity)
    denial = _probe_delete(adapter, session, entity, "item_key", 1)
    assert denial.code == "DESTRUCTIVE_CONFIRMATION_REQUIRED", (
        f"{adapter.name}: unconfirmed destructive delete denial code was {denial.code!r}, expected "
        "DESTRUCTIVE_CONFIRMATION_REQUIRED under strict (>= 1.2.0) semantics"
    )
    _assert_four_declarations(denial.details, context="V1 unconfirmed delete")
    assert adapter.count(session, entity) == before, (
        f"{adapter.name}: an unconfirmed destructive delete changed row count (SI-09 violation)"
    )


# ---------------------------------------------------------------------------
# V2 / V2b: destructive=false with an otherwise-correct phrase
# ---------------------------------------------------------------------------


def test_c06_v2_destructive_false_with_correct_phrase_denied(adapter, fx: Fixture):
    """design R-6 V2/V2b combined: `destructive: false` (or, per the
    contract's own `valid_confirmation` rule, an OMITTED `destructive`
    field -- "a missing destructive field is equivalent to false") with an
    otherwise-correct `confirmation` phrase must still be denied.

    Port-level scope note (design docs/design/DESTRUCTIVE_CONFIRMATION_V1.md
    R-1-3's own "フィールド欠落は false と同値" rule, corrected per review
    nit): this port's `ConformanceAdapter.delete()` signature requires
    `destructive: bool` as an explicit Python keyword argument on every
    call -- but what each adapter does with it on the wire is NOT uniform
    across all three registered peers (an earlier revision of this
    docstring overstated this as "every registered adapter's delete()...
    never omits the field", which is simply wrong for `MitateDB-api`: that
    peer's real `session.delete()` has no `destructive` wire parameter
    AT ALL -- deletion there is unconditionally destructive, gated by
    `confirm` alone, so there is no separate field for its adapter to
    either send or omit). What IS true for every peer is narrower: this
    port's OWN `delete()` method always receives an explicit Python
    `bool`, so a caller here cannot construct a request that omits the
    argument entirely -- genuine wire-level field OMISSION (V2b's own
    literal reading, meaningful only for a peer whose wire shape has a
    real `destructive` key to omit, i.e. `r2db-api`) is therefore not
    independently expressible at this port level without a second,
    lower-level entry point this design did not authorize adding here --
    V2 and V2b collapse onto the identical port-level assertion below.
    Verifying that `r2db-api`'s own wire parser treats an *omitted*
    `destructive` key identically to an explicit `false` is real, real
    coverage, but it is peer-local test scope, not something this common
    port can observe today: WP-3's own handoff (per this review) is to add
    it there, by separating confirmation-setting from the `destructive`
    check inside `_build_mutation_item` (both r2db plugs currently only
    ever set `confirmation` INSIDE the `if destructive:` branch, so a
    request with `destructive` omitted/false but `confirmation` present
    cannot be constructed through this adapter today either -- that
    coupling has to be undone first, on the r2db plugs specifically, before
    a real wire-omission vector can be added anywhere).
    """
    if _branch_for(adapter) != "strict":
        _assert_baseline_delete_invariant(adapter, fx)
        return

    session = fx.runtime_a
    entity = fx.shared_entity
    before = adapter.count(session, entity)
    phrase_denial = _probe_delete(adapter, session, entity, "item_key", 1)
    phrase = phrase_denial.details["required_confirmation"]

    denial = _assert_delete_denied(adapter, session, entity, "item_key", 1, destructive=False, confirmation=phrase)
    assert denial.code == "DESTRUCTIVE_CONFIRMATION_REQUIRED"
    assert adapter.count(session, entity) == before


# ---------------------------------------------------------------------------
# V3: full-match adversarial checks
# ---------------------------------------------------------------------------


def _v3_tamper_variants(phrase: str) -> dict[str, str]:
    """Derives every V3 tamper variant FROM the real phrase obtained via
    probe -- never a hardcoded literal (design R-6 V3: "正句の前方部分
    (実句から導出、ハードコードしない)"). A case-changed variant is only
    included when `swapcase()` actually differs from `phrase` (a
    phrase with no cased characters -- unlikely, but not impossible for a
    pure-digest spelling -- would otherwise silently test the same string
    twice)."""
    variants = {
        "suffix": phrase + "x",
        "proper_prefix": phrase[:-1] if len(phrase) > 1 else "",
    }
    swapped = phrase.swapcase()
    if swapped != phrase:
        variants["case_changed"] = swapped
    return variants


def test_c06_v3_confirmation_exact_match_required(adapter, fx: Fixture):
    if _branch_for(adapter) != "strict":
        _assert_baseline_delete_invariant(adapter, fx)
        return

    session = fx.runtime_a
    entity = fx.shared_entity
    other_entity = fx.a_only_entity
    before = adapter.count(session, entity)

    real_denial = _probe_delete(adapter, session, entity, "item_key", 1)
    phrase = real_denial.details["required_confirmation"]

    for name, variant in _v3_tamper_variants(phrase).items():
        denial = _assert_delete_denied(
            adapter, session, entity, "item_key", 1, destructive=True, confirmation=variant
        )
        assert denial.code == "DESTRUCTIVE_CONFIRMATION_REQUIRED", f"V3 variant {name!r} was not denied correctly"

    # another entity's correct phrase presented to THIS entity's delete.
    other_denial = _probe_delete(adapter, session, other_entity, "item_key", 1)
    other_phrase = other_denial.details["required_confirmation"]
    assert other_phrase != phrase, (
        "fixture/peer defect: two different entities' delete phrases collided -- phrase_construction's own "
        "scope-included rule requires the target to be part of the derivation"
    )
    _assert_delete_denied(adapter, session, entity, "item_key", 1, destructive=True, confirmation=other_phrase)

    # another OPERATION's correct phrase (drop_entity) presented to delete.
    try:
        drop_denial = _probe_drop_entity(adapter, fx.developer_a, other_entity)
    except SurfaceAbsent:
        pass  # this peer has no drop_entity surface at all -- nothing to cross-present here (V6 covers this).
    else:
        drop_phrase = drop_denial.details["required_confirmation"]
        _assert_delete_denied(adapter, session, entity, "item_key", 1, destructive=True, confirmation=drop_phrase)

    # the correct phrase for a DIFFERENT selection/where on the same entity.
    different_where_denial = _probe_delete(adapter, session, entity, "item_key", 999999)
    different_where_phrase = different_where_denial.details["required_confirmation"]
    assert different_where_phrase != phrase, (
        "fixture/peer defect: two different where-predicates on the same entity/operation collided onto the "
        "same phrase -- phrase_construction's own scope-included rule (M-3/Q1-D9) requires the operation's own "
        "selection to be part of the derivation"
    )
    _assert_delete_denied(
        adapter, session, entity, "item_key", 1, destructive=True, confirmation=different_where_phrase
    )

    assert adapter.count(session, entity) == before, "V3: no tamper variant may ever change state"


# ---------------------------------------------------------------------------
# V4: phrase determinism, requester-independence
# ---------------------------------------------------------------------------


def test_c06_v4_phrase_is_deterministic_and_requester_independent(adapter, fx: Fixture):
    if _branch_for(adapter) != "strict":
        _assert_baseline_delete_invariant(adapter, fx)
        return

    session = fx.runtime_a
    entity = fx.shared_entity

    first = _probe_delete(adapter, session, entity, "item_key", 1).details["required_confirmation"]
    second = _probe_delete(adapter, session, entity, "item_key", 1).details["required_confirmation"]
    assert first == second, (
        f"{adapter.name}: two probes of the identical request produced different phrases ({first!r} != "
        f"{second!r}) -- phrase_construction requires this server-side computation to be stateless/deterministic"
    )

    # design R-6 V4's own text: a second credential for the same
    # Application, of a DIFFERENT role (`developer`, not another
    # `runtime`) -- checking role-independence, not merely
    # credential-independence (review correction n-2).
    other_handle = adapter.issue_credential(fx.app_a, "developer")
    other_session = adapter.authenticate(other_handle)
    third = _probe_delete(adapter, other_session, entity, "item_key", 1).details["required_confirmation"]
    assert third == first, (
        f"{adapter.name}: a second, independent developer credential for the SAME application probing the "
        f"IDENTICAL request got a different phrase ({third!r} != {first!r}) -- phrase_construction depends "
        "only on operation/target/consequence, never on requester identity or role"
    )


# ---------------------------------------------------------------------------
# V5: probe -> echo -> execute
# ---------------------------------------------------------------------------


def test_c06_v5_echo_executes(adapter, fx: Fixture):
    if _branch_for(adapter) != "strict":
        _assert_baseline_delete_invariant(adapter, fx)
        return

    session = fx.runtime_a
    entity = fx.shared_entity
    before = adapter.count(session, entity)

    denial = _probe_delete(adapter, session, entity, "item_key", 1)
    phrase = denial.details["required_confirmation"]

    affected = adapter.delete(session, entity, "item_key", 1, destructive=True, confirmation=phrase)
    assert affected >= 1, f"{adapter.name}: echoing the server's own declared phrase verbatim did not execute"
    assert adapter.count(session, entity) == before - affected


# ---------------------------------------------------------------------------
# V6: drop_entity state-fingerprint invalidation
# ---------------------------------------------------------------------------


_V6_ABSENCE_VOCABULARY = ("drop", "destroy")


def test_c06_v6_drop_entity_fingerprint_invalidation(adapter, fx: Fixture):
    if _branch_for(adapter) != "strict":
        _assert_baseline_delete_invariant(adapter, fx)
        return

    developer = fx.developer_a
    # review correction m-5: a throwaway entity of this test's own,
    # created fresh here -- not `fx.a_only_entity` (the earlier revision's
    # choice), which V3 also probes/references. Sharing a target between
    # the two tests made V6's own drop-at-the-end implicitly depend on
    # running after V3 (or before it, for V3's own later probes) within
    # the same cached `Fixture` -- an ordering dependency neither test
    # should have to reason about. Real out-of-band Application
    # provisioning is NOT this test's own footprint concern here (the
    # applications-count budget this WP already found and fixed is about
    # `provision_application`, not entity/schema-level creation within an
    # already-provisioned Application).
    entity = fresh_identifier("c06_v6_entity")
    adapter.create_entity(developer, entity, {"item_key": "integer"})

    try:
        first_denial = _probe_drop_entity(adapter, developer, entity)
    except SurfaceAbsent:
        # This peer has no schema-drop entry point at all (e.g.
        # MitateDB-api) -- the shared C-14-originated absence mechanism
        # (design R-6 item 4) verifies the claim independently rather than
        # accepting it on the adapter's word. `("drop", "destroy")` is this
        # vector's own forbidden-vocabulary guard (review correction M-5) --
        # distinct from C-14's own `("credential", "control")`, since this
        # absence claim is about schema/drop capability, not control-plane
        # authority.
        assert_control_operation_absent_or_uniformly_refused(
            adapter, lambda: adapter.drop_entity(developer, entity, destructive=True, confirmation=None),
            required_forbidden_vocabulary=_V6_ABSENCE_VOCABULARY,
        )
        # Review correction M-6: the absence claim must agree with this
        # peer's OWN declared `capabilities.schema_operations` -- a peer
        # claiming `SurfaceAbsent` for `drop_entity` while its own
        # capability document is silent about it (or, worse, declares it
        # supported) is an internally inconsistent declaration, the same
        # "declared status agrees with actual surface" property C-14
        # already checks for its own capability. Satisfied either by
        # `status == "unavailable"` (the whole schema-operations surface
        # is off) or by `"drop_entity"` appearing in `unsupported` (a
        # `partial` surface that names this operation specifically --
        # `MitateDB-api`'s own real declaration, measured: `status:
        # "partial"`, `unsupported` includes `"drop_entity"`).
        schema_ops = _schema_operations_capability(adapter)
        unsupported = schema_ops.get("unsupported", [])
        assert schema_ops.get("status") == "unavailable" or "drop_entity" in unsupported, (
            f"{adapter.name}: drop_entity is SurfaceAbsent, but capabilities.schema_operations declares "
            f"status={schema_ops.get('status')!r} and unsupported={unsupported!r} -- neither says "
            "'unavailable' nor lists drop_entity as unsupported, so the absence claim disagrees with this "
            "peer's own declared capability document"
        )
        return

    first_phrase = first_denial.details["required_confirmation"]
    _assert_four_declarations(first_denial.details, context="V6 drop_entity first probe")

    # V3-equivalent adversarial subset against drop_entity itself.
    for name, variant in _v3_tamper_variants(first_phrase).items():
        with pytest.raises(ConformanceDenial) as excinfo:
            adapter.drop_entity(developer, entity, destructive=True, confirmation=variant)
        assert excinfo.value.code == "DESTRUCTIVE_CONFIRMATION_REQUIRED", f"V6 drop_entity variant {name!r}"

    other_entity_denial = _probe_drop_entity(adapter, developer, fx.shared_entity)
    other_entity_phrase = other_entity_denial.details["required_confirmation"]
    assert other_entity_phrase != first_phrase
    with pytest.raises(ConformanceDenial) as excinfo:
        adapter.drop_entity(developer, entity, destructive=True, confirmation=other_entity_phrase)
    assert excinfo.value.code == "DESTRUCTIVE_CONFIRMATION_REQUIRED"

    # Review correction M-1: establish this exact target's own phrase
    # DETERMINISM (re-probe, expect the identical phrase) before the
    # schema change that is about to invalidate it -- otherwise a change
    # in the re-probed phrase after the schema change could, in
    # principle, be explained by the phrase simply not being stable at
    # all (a V4-class defect) rather than by the state fingerprint
    # genuinely changing, and this vector would not be able to tell the
    # two apart.
    redundant_denial = _probe_drop_entity(adapter, developer, entity)
    assert redundant_denial.details["required_confirmation"] == first_phrase, (
        f"{adapter.name}: drop_entity's phrase for the IDENTICAL request changed between two probes taken "
        "before any schema change -- establish determinism (V4) before testing invalidation"
    )

    # An unrelated schema change to the SAME entity (`create_unique_index`,
    # not `add_field` -- this port has no standalone `add_field` operation;
    # `create_unique_index` bumps the same monotonic state fingerprint
    # design R-2 item 1 requires of "every schema operation", so it serves
    # this vector's own "any other schema change" requirement equally well
    # without a second, unauthorized port addition).
    adapter.create_unique_index(developer, entity, fresh_identifier("c06_v6_idx"), ["item_key"])

    with pytest.raises(ConformanceDenial) as excinfo:
        adapter.drop_entity(developer, entity, destructive=True, confirmation=first_phrase)
    assert excinfo.value.code == "DESTRUCTIVE_CONFIRMATION_REQUIRED", (
        f"{adapter.name}: the pre-schema-change drop_entity phrase was still accepted after an unrelated "
        "schema change to the same entity -- the state fingerprint did not invalidate it"
    )

    second_denial = _probe_drop_entity(adapter, developer, entity)
    second_phrase = second_denial.details["required_confirmation"]
    assert second_phrase != first_phrase, (
        f"{adapter.name}: drop_entity's re-probed phrase after a schema change is identical to the pre-change "
        "phrase -- the state fingerprint did not change"
    )
    adapter.drop_entity(developer, entity, destructive=True, confirmation=second_phrase)
    assert entity not in adapter.entities(developer), f"{adapter.name}: drop_entity with the fresh phrase did not execute"


# ---------------------------------------------------------------------------
# V7: last-control-credential revoke gate
# ---------------------------------------------------------------------------


_V7_ABSENCE_VOCABULARY = ("credential", "control")


def test_c06_v7_control_credential_gate(adapter, fx: Fixture):
    """design R-6 V7. **Scope note (supervisor ruling, review correction
    M-7):** `audited: true` is NOT asserted here, even though `service.py`/
    `control_plane.py`'s own `_deny` path is documented (design R-3) to
    include it on this exact denial. The contract's own `errors.
    details_vocabulary` declares `audited` an OPTIONAL, code-agnostic key
    (`docs/design/DESTRUCTIVE_CONFIRMATION_V1.md` subordinate ruling 7(B)),
    never a requirement of `DESTRUCTIVE_CONFIRMATION_REQUIRED` itself
    (contrast `required_confirmation`/`consequence`/`reversible_
    alternative`/`recovery`, which the contract's own `destructive_
    confirmation.denial.details_keys` DOES require) -- asserting it here
    would promote r2db's own implementation choice into a common-suite
    requirement every future control-plane-provided peer would have to
    match, which is exactly what this port's `capability_document()`/
    peer-agnostic design principle 2 forbids. `audited: true` on this
    denial is real, valuable, r2db-specific evidence; WP-3 adds it as an
    r2db-local test (`r2db-api/tests/test_control_plane_service.py`-
    equivalent), not here. C-06 checks only what the contract itself
    requires: the four keys present and non-empty/null-or-non-empty.
    """
    if _branch_for(adapter) != "strict":
        _assert_baseline_delete_invariant(adapter, fx)
        return

    if _control_plane_status(adapter) != "enabled":
        actor = adapter.issue_credential(fx.app_a, "runtime")
        assert_control_operation_absent_or_uniformly_refused(
            adapter,
            lambda: adapter.revoke_credential_inband(
                actor, fresh_identifier("c06_v7_tgt_cred"), destructive=True, confirmation=None
            ),
            required_forbidden_vocabulary=_V7_ABSENCE_VOCABULARY,
        )
        return

    control_actor = adapter.control_credential()
    rows = adapter.list_credentials(control_actor)
    active_control_rows = [
        row for row in rows
        if row.get("role") == "control" and row.get("enabled") and not row.get("revoked")
    ]
    assert len(active_control_rows) == 1, (
        f"{adapter.name}: V7 precondition is exactly one active control credential; found "
        f"{len(active_control_rows)} -- {active_control_rows!r}. This adapter's own control_credential() "
        "maintenance is expected to keep this invariant across the whole session (see that method's own "
        "docstring); a violation here means some other test left a second live control credential behind."
    )
    assert active_control_rows[0]["credential_id"] == control_actor.credential_ref

    with pytest.raises(ConformanceDenial) as excinfo:
        adapter.revoke_credential_inband(
            control_actor, control_actor.credential_ref, destructive=True, confirmation=None
        )
    denial = excinfo.value
    assert denial.code == "DESTRUCTIVE_CONFIRMATION_REQUIRED"
    _assert_four_declarations(denial.details, context="V7 unconfirmed revoke of the last control credential")
    # `audited` is deliberately NOT asserted here -- see this test's own
    # docstring (supervisor ruling, review correction M-7).

    phrase = denial.details["required_confirmation"]
    adapter.revoke_credential_inband(control_actor, control_actor.credential_ref, destructive=True, confirmation=phrase)

    # Recovery: this adapter's own privileged `control_credential()`
    # maintenance re-validates its tracked handle against the real store on
    # every call and transparently repairs via a real reset ceremony when
    # it finds the tracked credential dead (see that method's own
    # docstring) -- exactly the "adapter特権経路で復旧" design R-6 V7
    # requires, never a second, ad-hoc recovery mechanism this test invents.
    restored = adapter.control_credential()
    assert restored.credential_ref != control_actor.credential_ref, (
        f"{adapter.name}: control_credential() returned the just-revoked credential instead of repairing via "
        "a real reset"
    )


# ---------------------------------------------------------------------------
# V8: payload-echo probe
# ---------------------------------------------------------------------------


def test_c06_v8_no_payload_echo_in_declarations(adapter, fx: Fixture):
    if _branch_for(adapter) != "strict":
        _assert_baseline_delete_invariant(adapter, fx)
        return

    session = fx.runtime_a
    entity = fx.shared_entity
    adversarial_value = "c06_v8_" + "<script>alert('DROP TABLE users; --')</script>_ünïcödé"

    denial = _probe_delete(adapter, session, entity, "probe_value", adversarial_value)
    assert_no_payload_echo_in_details(denial.details, adversarial_value, context="V8 adversarial where-value probe")


# ---------------------------------------------------------------------------
# Branch-dispatch vacuity guard (review blocker B-1) -- registry-wide, not
# parametrized via the `adapter`/`fx` fixtures, mirroring `test_c11_
# document_conformance.py`/`test_c12_capability_agreement.py`'s own
# registry-wide vacuity guards (`registered_adapters()`, iterated directly,
# runs exactly once regardless of how many adapters are registered).
# ---------------------------------------------------------------------------

# Expected as of THIS work package (port v1.6): every registered adapter
# still declares `contract_version: 1.1.0` (§ this file's own module
# docstring) -- so strict is the EMPTY set and baseline is all three. This
# is deliberately a literal, hardcoded expectation, not derived from
# anything computed below: WP-3 flips both r2db plugs to 1.2.0 in one
# commit, and WP-5 flips MitateDB-api -- each flip MUST update these two
# sets in the same commit as the flip, or this test goes red (a peer that
# is expected to have moved to the strict branch but is still being
# classified baseline, or vice versa, is exactly the silent-drift design
# principle 4 forbids). The registry keys used here are `registered_
# adapters()`'s own dict keys (`registry.json`'s `name` field), matching
# `test_c11`/`test_c12`'s own convention -- NOT each adapter object's own
# `.name` property (`"r2db-api (http+postgres)"` for the HTTP plug, used
# elsewhere in this file for diagnostic messages only).
_EXPECTED_STRICT_ADAPTER_NAMES: frozenset[str] = frozenset()
_EXPECTED_BASELINE_ADAPTER_NAMES: frozenset[str] = frozenset({"r2db-api", "r2db-api-http", "MitateDB-api"})


def test_c06_branch_dispatch_vacuity_guard():
    """(a) For every registered adapter, `_branch_for`'s resolution must
    agree with an INDEPENDENT re-derivation: a fresh `capability_
    document()` call (never this file's own `_capability_document` cache,
    which must not be able to hide a caching bug by cross-checking
    against itself) fed through `contract_version_at_least` directly. (b)
    The resulting strict/baseline adapter-NAME sets must equal the
    explicit, hardcoded expectation above -- so a peer silently taking the
    wrong branch (this WP's own `_branch_for`/`_contract_version` computing
    something other than what a real, independent read of the peer's own
    declaration says) is caught here, and so is the reverse: a peer that
    SHOULD have flipped (WP-3/WP-5's own completion condition) but did not
    get this test's own expectation updated in the same commit.
    """
    actual_strict: set[str] = set()
    actual_baseline: set[str] = set()
    for name, adapter_obj in registered_adapters().items():
        document = adapter_obj.capability_document()
        version = document.get("contract_version")
        assert isinstance(version, str) and version, (
            f"{name}: capability_document() has no non-empty string 'contract_version' -- {document!r}"
        )
        independently_strict = contract_version_at_least(version, "1.2.0")
        resolved = _branch_for(adapter_obj)
        assert (resolved == "strict") == independently_strict, (
            f"{name}: _branch_for resolved {resolved!r}, but an independent semver check of "
            f"contract_version={version!r} (freshly re-read, not this file's own cache) says "
            f"strict={independently_strict!r} -- these must agree"
        )
        (actual_strict if resolved == "strict" else actual_baseline).add(name)

    assert actual_strict == _EXPECTED_STRICT_ADAPTER_NAMES, (
        f"strict-branch adapter set drifted from the expected {_EXPECTED_STRICT_ADAPTER_NAMES!r}: got "
        f"{actual_strict!r} -- if a peer's own flip WP (WP-3/WP-5) just landed, update "
        "_EXPECTED_STRICT_ADAPTER_NAMES/_EXPECTED_BASELINE_ADAPTER_NAMES in the SAME commit as the flip"
    )
    assert actual_baseline == _EXPECTED_BASELINE_ADAPTER_NAMES, (
        f"baseline-branch adapter set drifted from the expected {_EXPECTED_BASELINE_ADAPTER_NAMES!r}: got "
        f"{actual_baseline!r}"
    )


# ---------------------------------------------------------------------------
# Pure-function unit tests (design instructions item C-4): the strict
# branch is never exercised against a real peer in this WP (every
# registered adapter still declares 1.1.0) -- these tests instead verify,
# directly and without any adapter, that the dispatch/derivation
# primitives the vectors above depend on are themselves correct and that
# the vector bodies above import/collect without error (module-level
# collection already proves that much; these add real behavioral coverage
# of the pure functions).
# ---------------------------------------------------------------------------


def test_parse_semver_parses_three_part_versions():
    assert parse_semver("1.2.0") == (1, 2, 0)
    assert parse_semver("1.10.0") == (1, 10, 0)
    assert parse_semver("0.0.1") == (0, 0, 1)


def test_parse_semver_rejects_malformed_versions():
    with pytest.raises(ValueError):
        parse_semver("1.2")
    with pytest.raises(ValueError):
        parse_semver("1.2.3.4")
    with pytest.raises(ValueError):
        parse_semver("not-a-version")


def test_parse_semver_rejects_boundary_cases_review_m4():
    # pre-release/build-metadata suffixes: this repository's own
    # `contract_version` vocabulary never carries one, so silently
    # accepting the numeric prefix and discarding the rest would hide a
    # real declaration defect (review correction m-4).
    with pytest.raises(ValueError):
        parse_semver("1.2.0-rc1")
    with pytest.raises(ValueError):
        parse_semver("1.2.0+build5")
    # incidental surrounding whitespace must not be silently stripped.
    with pytest.raises(ValueError):
        parse_semver(" 1.2.0")
    with pytest.raises(ValueError):
        parse_semver("1.2.0 ")
    # leading zeros are not a valid component spelling.
    with pytest.raises(ValueError):
        parse_semver("1.02.0")


def test_parse_semver_error_message_names_the_unsupported_format():
    # review correction m-4: a raw `int()` failure used to raise a bare,
    # undiagnostic ValueError -- this asserts the new message is
    # actionable rather than merely present.
    with pytest.raises(ValueError, match="unsupported version format"):
        parse_semver("1.2.0-rc1")


def test_contract_version_at_least_uses_semver_tuple_comparison_not_string_comparison():
    # design's own named trap: "1.10.0" < "1.2.0" as STRINGS, but
    # 1.10.0 >= 1.2.0 as versions.
    assert contract_version_at_least("1.10.0", "1.2.0") is True
    assert "1.10.0" < "1.2.0"  # sanity: the string trap really exists
    assert contract_version_at_least("1.2.0", "1.2.0") is True
    assert contract_version_at_least("1.1.0", "1.2.0") is False
    assert contract_version_at_least("2.0.0", "1.2.0") is True


def test_resolve_valid_confirmation_returns_legacy_token_below_1_2_0():
    probe_calls = []

    def probe():
        probe_calls.append(1)
        raise AssertionError("probe must not be called below contract_version 1.2.0")

    result = resolve_valid_confirmation(contract_version="1.1.0", legacy_token="DELETE", probe=probe)
    assert result == "DELETE"
    assert probe_calls == []


def test_resolve_valid_confirmation_echoes_the_probed_phrase_at_or_above_1_2_0():
    def probe():
        raise ConformanceDenial(
            code="DESTRUCTIVE_CONFIRMATION_REQUIRED", adapter="fake",
            details={
                "required_confirmation": "DELETE fake_entity @where=abc123",
                "consequence": "rows are permanently destroyed",
                "reversible_alternative": None,
                "recovery": None,
            },
        )

    result = resolve_valid_confirmation(contract_version="1.2.0", legacy_token="DELETE", probe=probe)
    assert result == "DELETE fake_entity @where=abc123"


def test_resolve_valid_confirmation_rejects_a_probe_that_succeeds():
    def probe():
        return None  # the destructive operation executed without confirmation

    with pytest.raises(AssertionError):
        resolve_valid_confirmation(contract_version="1.2.0", legacy_token="DELETE", probe=probe)


def test_resolve_valid_confirmation_rejects_a_probe_missing_the_phrase():
    def probe():
        raise ConformanceDenial(
            code="DESTRUCTIVE_CONFIRMATION_REQUIRED", adapter="fake",
            details={"consequence": "x", "reversible_alternative": None, "recovery": None},
        )

    with pytest.raises(AssertionError):
        resolve_valid_confirmation(contract_version="1.2.0", legacy_token="DELETE", probe=probe)


def test_resolve_valid_confirmation_rejects_a_probe_denied_with_the_wrong_code():
    def probe():
        raise ConformanceDenial(code="VALIDATION_FAILED", adapter="fake")

    with pytest.raises(AssertionError):
        resolve_valid_confirmation(contract_version="1.2.0", legacy_token="DELETE", probe=probe)


def test_assert_no_payload_echo_in_details_catches_a_verbatim_leak():
    with pytest.raises(AssertionError):
        assert_no_payload_echo_in_details(
            {"required_confirmation": "DELETE evil_payload_marker @where=abc"}, "evil_payload_marker"
        )


def test_assert_no_payload_echo_in_details_passes_when_clean():
    assert_no_payload_echo_in_details(
        {"required_confirmation": "DELETE some_entity @where=abc", "consequence": "x"}, "evil_payload_marker"
    )


def test_v3_tamper_variants_derives_from_the_real_phrase_not_a_hardcoded_literal():
    variants = _v3_tamper_variants("DELETE fake_entity @where=abc123")
    assert variants["suffix"] == "DELETE fake_entity @where=abc123x"
    assert variants["proper_prefix"] == "DELETE fake_entity @where=abc12"
    assert all(v != "DELETE fake_entity @where=abc123" for v in variants.values())
