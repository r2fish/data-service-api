"""C-19 -- client self-sufficiency (D-1/D-2/D-3, contract 1.6.0).

design: docs/design/PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md section 6.2
("新 vector (4 plug 全数、非空 precondition 付き)") / section 6.3 (the
recommended C-19 condition and its disclosed limits, supervisor-ruled into
`conformance-tests/CONDITIONS.md`'s C-19 row). work order:
docs/work-orders/WORK_ORDER_PHASE6_CONTRACT_160_V1.md WP-1 item 4 (the
three vectors) and item 8 (the two `xfail(strict=True)` registrations in
this file). Every real (non-guard, non-static) test here carries
`@pytest.mark.condition("C-19")` via the module-level `pytestmark`.

C-19's own proposition (CONDITIONS.md's C-19 row; the 2026-09-05 narrowing
is recorded in CONDITIONS_HISTORY.md#c-19): a
client holding only the common contract, one base URL, and one
credential -- with no peer-specific knowledge -- can authenticate with
that credential, verbatim, on the surface its authority class admits
(application credential -> data surface; control credential -> control
surface; never the other -- SI-02, verified by C-13/C-14, which is why
the two verbatim vectors below use one credential of each class), can
discover where the OTHER surface is reached, and can discover entity
types. Three decisions from contract 1.6.0 (subordinate ruling 11) make
this true: D-1 (a credential's `secret` is a complete, verbatim bearer
token -- nothing to compose or split), D-2 (`CapabilityDocument.surfaces`
names where the OTHER surface is), D-3 (`EntityDescriptor.field_types`
names every field's real type).

**Declare-first, and silently vacuous as of THIS work package**: every
real vector below branches on the adapter's own declared `contract_version`
(`>= 1.6.0`, `adapter.parse_semver`/semver-tuple comparison, never a
string comparison) and returns early otherwise. As of WP-1, no
registered adapter declares 1.6.0 -- the contract 1.6.0 vocabulary this
file reads (`spec/data-service-api.v1.json`'s `field_type` enum's seventh
member `json`, `CapabilityDocument.surfaces`, `EntityDescriptor.
field_types`) is published by WP-1's own contract commit, but no PEER
implements or declares it until WP-2 (r2db-api) / WP-3 (MitateDB-api).
This file's own real vectors are therefore silently vacuous on every
currently-registered adapter, by design (common-suite discipline:
"green because the branch was never entered" is never reported as
"green because verified" -- work order WP-1 "非 vacuity 要件"). The fact
of that vacuity is what `test_c19_every_control_surface_adapter_declares_
1_6_0` below stands in for, in the SAME shape phase 5's identically-
purposed 1.5.0 guard used (`test_c09_every_control_surface_adapter_
declares_1_5_0`, `test_c09_audit_evidence.py`): registered `xfail(strict=
True)` here, to be un-xfailed in the SAME commit as the LAST 1.6.0 flip
(WP-3).

**Scope decisions made in this WP, flagged for supervisor review (design
had left them open)**:

- The D-3 catalog round-trip vector needs the common suite to know, on
  its OWN side, which contract-vocabulary type it declared for each
  field it creates, so it can compare that declaration against what
  `catalog_document()` reports back (design section 6.1 item 3 left this
  "existing `Fixture` vs. new method(s)" choice to this WP). This file
  chooses NEW METHODS: `ConformanceAdapter.create_entity_with_declared_
  types`/`.add_field_with_declared_type` (port v1.10, `adapter.py`), not
  a `Fixture` change -- the round-trip vector calls these two methods
  itself with types it already knows, so `Fixture` (built once per test,
  before any of THIS vector's own entities exist) never needed to carry
  declared-type state at all.
- The D-2 declare-and-echo vector (design section 6.2 item 2(iii)) is
  realized here as a SECOND real call to `capability_document()`/
  `control_capabilities()` (self-consistency across two real, independent
  calls to the peer's own real entry point), not a literal HTTP GET
  dialed against the declared `surfaces.<x>.base_url` STRING -- building
  that would need a new port primitive beyond the three port v1.10
  changes work order WP-1 item 5(a)/(b)/(c) enumerates, which this WP did
  not add without a ruling (common-suite discipline: undesigned
  machinery is reported, not silently invented). This is disclosed as a
  limit on `CONDITIONS.md`'s C-19 row and restated in the WP-1 completion
  report for two-sided review. It is, in any case, unreachable by any
  currently-registered adapter as of this WP.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Any, Mapping

import pytest

from adapter import (
    REPO_ROOT,
    ConformanceDenial,
    ControlCredentialHandle,
    Fixture,
    fresh_identifier,
    load_contract,
    parse_semver,
)
from conftest import registered_adapters

pytestmark = pytest.mark.condition("C-19")


# --- shared helpers (each test module owns its own copy -- existing
# convention, see e.g. test_c09_audit_evidence.py's/test_c14_authority_
# boundary.py's own identically-named helpers) --------------------------


def _semver_tuple(version: str) -> tuple[int, int, int]:
    try:
        return parse_semver(version)
    except ValueError:
        # An unparseable declared version has not affirmatively
        # demonstrated it meets a >= 1.6.0 floor -- fail-closed to "below
        # every real version", the same direction test_c09_audit_
        # evidence.py's own `_semver_tuple` takes for the identical case.
        return (0, 0, 0)


def _capability_document(adapter) -> Mapping[str, Any]:
    document = adapter.capability_document()
    assert isinstance(document, Mapping) and "contract_version" in document, (
        f"{adapter.name}: capability_document() carries no 'contract_version' -- {document!r}"
    )
    return document


def _capability_status(document: Mapping[str, Any], name: str) -> str:
    capabilities = document.get("capabilities", {})
    entry = capabilities.get(name, {})
    return entry.get("status", "unavailable") if isinstance(entry, Mapping) else "unavailable"


def _control_plane_status(adapter) -> str:
    return _capability_status(_capability_document(adapter), "control_plane")


def _is_http_plug(adapter) -> bool:
    """`True` for the two HTTP+ASGI-transport plugs (`adapter.name`
    carries "(http+postgres)"), `False` for the two in-process plugs --
    the same "http" substring test this repository's own registry
    `name`/adapter `.name` values already make unambiguous (`r2db-api` /
    `MitateDB-api` vs. `r2db-api (http+postgres)` / `MitateDB-api
    (http+postgres)`). Used only by the D-2 declare-and-echo vector
    (design section 6.2 item 2(iii)), which design scopes to the two
    plugs that route a real request through a real ASGI handler."""
    return "http" in adapter.name.lower()


def _contract_field_type_vocabulary() -> tuple[str, ...]:
    """The contract's own `field_type` enum, read fresh from `spec/
    data-service-api.v1.json` on every call (adapter.py's own "never
    hardcode a copy" rule, module docstring) -- never a literal copy of
    the 7 words maintained in this file."""
    contract = load_contract()
    return tuple(contract["schemas"]["SchemaOperationRequest"]["properties"]["field_type"]["enum"])


# --- vector 1 (D-1): credential verbatim --------------------------------


def test_c19_application_credential_verbatim_authenticates_on_data_surface(adapter, fx: Fixture):
    """Design section 6.2 item 1: an application credential's `secret`,
    used verbatim (no adapter-side transformation), authenticates on the
    DATA surface. `issue_credential_inband` already returns a
    `CredentialHandle` built from the peer's own real response with no
    port-level composition (port v1.10's own verbatim regulation,
    `adapter.py`'s `CredentialHandle`/`issue_credential_inband`
    docstrings) -- this vector's own job is only to confirm the resulting
    handle authenticates for real, not to re-derive or re-compose
    anything of its own.

    precondition (design section 6.2 item 1): `control_plane` other than
    `unavailable` (an in-band issuance path must exist at all).
    """
    document = _capability_document(adapter)
    if _semver_tuple(str(document.get("contract_version", "0.0.0"))) < (1, 6, 0):
        return
    if _control_plane_status(adapter) == "unavailable":
        return

    control_actor = adapter.control_credential()
    handle = adapter.issue_credential_inband(control_actor, fx.app_a, "runtime")
    session = adapter.authenticate(handle)
    scope = adapter.scope_of(session)
    assert scope.application_id == fx.app_a and scope.role == "runtime", (
        f"{adapter.name}: authenticate()'d session's own scope {scope!r} does not match the issued "
        f"credential (application_id={fx.app_a!r}, role='runtime')"
    )


def test_c19_control_credential_verbatim_authenticates_on_control_surface(adapter, fx: Fixture):
    """Design section 6.2 item 1's control-surface half: a ROTATED control
    credential's fresh `secret`, used verbatim to build a new handle
    (`credential_ref` unchanged, `secret` read directly off the rotate
    response and placed unmodified -- the exact idiom `test_c15_
    bootstrap_reset_lifecycle.py`'s own rotate-handling already uses),
    authenticates on the CONTROL surface (`GET /control/v1/capabilities`).

    precondition: `control_plane` other than `unavailable`.
    """
    document = _capability_document(adapter)
    if _semver_tuple(str(document.get("contract_version", "0.0.0"))) < (1, 6, 0):
        return
    if _control_plane_status(adapter) == "unavailable":
        return

    control_actor = adapter.control_credential()
    rotated = adapter.rotate_credential(control_actor, control_actor.credential_ref)
    new_secret = rotated["secret"] if isinstance(rotated, Mapping) else getattr(rotated, "secret")
    fresh_handle = ControlCredentialHandle(credential_ref=control_actor.credential_ref, secret=new_secret)
    result = adapter.control_capabilities(fresh_handle)
    assert isinstance(result, Mapping) and "contract_version" in result, (
        f"{adapter.name}: control_capabilities() with the rotated credential's own verbatim secret did not "
        f"return a real capability document -- {result!r}"
    )


# --- vector 2 (D-2): surfaces --------------------------------------------


def test_c19_surfaces_present_and_consistent_across_both_documents(adapter, fx: Fixture):
    """Design section 6.2 item 2(i)/(ii), 4 plugs all (no precondition
    beyond the version gate -- both document reads are cheap and require
    no real HTTP dial, design section 6.2 item 2's own "4 plug 全数" note
    for (i)/(ii)).

    (i) `surfaces.data` is present and identical in the data-plane and
        control-plane capability documents.
    (ii) `surfaces.control` is present iff `control_plane` is other than
         `unavailable` (contract's own conditional-omission rule, D-2).
    """
    data_document = _capability_document(adapter)
    contract_version = str(data_document.get("contract_version", "0.0.0"))
    if _semver_tuple(contract_version) < (1, 6, 0):
        return

    surfaces = data_document.get("surfaces")
    assert isinstance(surfaces, Mapping), (
        f"{adapter.name}: declares contract_version {contract_version!r} (>= 1.6.0) but capability_document() "
        f"carries no 'surfaces' object at all -- {data_document!r}"
    )
    data_surface = surfaces.get("data")
    assert isinstance(data_surface, Mapping) and data_surface.get("base_url"), (
        f"{adapter.name}: surfaces.data.base_url is missing or empty -- {surfaces!r}"
    )

    control_status = _control_plane_status(adapter)
    if control_status == "unavailable":
        assert "control" not in surfaces, (
            f"{adapter.name}: control_plane is 'unavailable' but surfaces.control is present -- {surfaces!r} "
            "(D-2: a deployment declaring control_plane unavailable omits surfaces.control)"
        )
        return

    control_surface = surfaces.get("control")
    assert isinstance(control_surface, Mapping) and control_surface.get("base_url"), (
        f"{adapter.name}: control_plane is {control_status!r} (not unavailable) but surfaces.control is "
        f"missing or empty -- {surfaces!r}"
    )

    control_actor = adapter.control_credential()
    control_document = adapter.control_capabilities(control_actor)
    assert control_document.get("contract_version") == contract_version, (
        f"{adapter.name}: data-plane declares contract_version {contract_version!r} but the control-plane "
        f"document declares {control_document.get('contract_version')!r}"
    )
    assert control_document.get("surfaces") == surfaces, (
        f"{adapter.name}: data-plane and control-plane capability documents disagree on 'surfaces' -- "
        f"{surfaces!r} vs {control_document.get('surfaces')!r} (D-2: both documents return the same object)"
    )


_HTTP_ADAPTER_NAMES: tuple[str, ...] = tuple(
    name for name, obj in registered_adapters().items() if _is_http_plug(obj)
)
assert _HTTP_ADAPTER_NAMES, (
    "no registered adapter is an HTTP plug -- test_c19_surfaces_declare_and_echo_on_http_plugs would "
    "collect zero items, which is silent vacuity by construction (common-suite discipline 1), never an "
    "empty-but-acceptable parametrize"
)


@pytest.mark.parametrize("adapter_name", _HTTP_ADAPTER_NAMES)
def test_c19_surfaces_declare_and_echo_on_http_plugs(adapter_name: str) -> None:
    """Design section 6.2 item 2(iii). Review finding F(i) / audit finding
    (i) (2026-09-04, supervisor-ruled): parametrized DIRECTLY over the
    HTTP-only adapter names (`_HTTP_ADAPTER_NAMES`, never the shared,
    all-4-plug `adapter` fixture, and never an in-body `if not _is_http_
    plug(adapter): return`) -- the two in-process plugs never contribute
    a permanently-vacuous collected item at all, rather than one that
    silently returns on every run forever (common-suite discipline 1's
    own "空振り禁止" read literally at the COLLECTION level, not only at
    the assertion level -- the prior in-body early-return form collected
    4 items but only ever asserted on 2). `surfaces.*.base_url` is
    necessarily a synthetic, non-dialable value on BOTH in-process plugs
    (design section 6.2 item 2(iii)/section 6.4, this file's own module
    docstring) -- exercising this vector against them would be a
    structural non-observation, not a real pass.
    """
    adapter = registered_adapters()[adapter_name]
    data_document_1 = _capability_document(adapter)
    contract_version = str(data_document_1.get("contract_version", "0.0.0"))
    if _semver_tuple(contract_version) < (1, 6, 0):
        return

    data_document_2 = _capability_document(adapter)
    assert data_document_2.get("contract_version") == contract_version, (
        f"{adapter.name}: a second, independent capability_document() call returned a different "
        f"contract_version ({data_document_2.get('contract_version')!r} vs {contract_version!r})"
    )
    assert data_document_2.get("surfaces") == data_document_1.get("surfaces"), (
        f"{adapter.name}: a second, independent capability_document() call returned different surfaces -- "
        f"{data_document_1.get('surfaces')!r} vs {data_document_2.get('surfaces')!r}"
    )

    if _control_plane_status(adapter) == "unavailable":
        return
    control_actor = adapter.control_credential()
    control_document_1 = adapter.control_capabilities(control_actor)
    control_document_2 = adapter.control_capabilities(control_actor)
    assert control_document_2.get("contract_version") == contract_version, (
        f"{adapter.name}: a second, independent control_capabilities() call returned a different "
        f"contract_version ({control_document_2.get('contract_version')!r} vs {contract_version!r})"
    )
    assert control_document_2.get("surfaces") == control_document_1.get("surfaces"), (
        f"{adapter.name}: a second, independent control_capabilities() call returned different surfaces -- "
        f"{control_document_1.get('surfaces')!r} vs {control_document_2.get('surfaces')!r}"
    )


# --- vector 3 (D-3): typed catalog + round-trip --------------------------


def _json_equal(observed: Any, written: Any) -> bool:
    """Type-aware JSON-value equality (review F6, 2026-09-04): plain `==`
    conflates types Python treats as numerically equal but the CONTRACT's
    own 7-word vocabulary treats as distinct (`1 == True`, `0 == False`,
    `3 == 3.0`) -- design docs/design/PHASE6_CONTRACT_160_CLIENT_
    DISCOVERY_V1.md's own §1.3 handoff records BOTH MitateDB backends
    currently storing a declared `boolean` field as an INTEGER, exactly
    the defect WP-3 (γ) is scoped to correct (0/1 -> JSON boolean wire
    representation). A bare `==` round-trip check cannot see that
    defect AT ALL (it silently accepts `1` back for a written `True`);
    this is the SAME strictness the `boolean`-declared-field round-trip
    below already uses (`is value`), generalized so the `json`-typed
    field's own round-trip (which must accept ALL five JSON shapes, not
    only booleans) gets it too. Recurses into `dict`/`list`; scalars
    compare by EXACT type first, then value -- `bool` is checked before
    `int`/`float` because `isinstance(True, int)` is `True` in Python.
    """
    if isinstance(observed, bool) or isinstance(written, bool):
        return type(observed) is type(written) and observed == written
    if isinstance(observed, dict) and isinstance(written, dict):
        return observed.keys() == written.keys() and all(
            _json_equal(observed[k], written[k]) for k in observed
        )
    if isinstance(observed, list) and isinstance(written, list):
        return len(observed) == len(written) and all(
            _json_equal(o, w) for o, w in zip(observed, written)
        )
    return type(observed) is type(written) and observed == written


def _typed_catalog_precondition(adapter) -> tuple[bool, Mapping[str, Any]]:
    document = _capability_document(adapter)
    contract_version = str(document.get("contract_version", "0.0.0"))
    if _semver_tuple(contract_version) < (1, 6, 0):
        return False, document
    if _capability_status(document, "application_catalog") == "unavailable":
        return False, document
    return True, document


def test_c19_field_types_declaration_round_trip_and_default_and_value_round_trip(adapter, fx: Fixture):
    """Design section 6.2 item 3(i)/(ii)/(iii). precondition:
    `application_catalog` other than `unavailable`.

    (i) every entity's `fields` is a subset of its `field_types` keys,
        and every value is one of the contract's 7 field_type words.
    (ii) a type DECLARED via `create_entity_with_declared_types`/`add_
         field_with_declared_type` (contract vocabulary, verbatim) is
         reported back unchanged by `catalog_document()` (declaration
         round-trip).
    (iii) a field named in `fields` but NOT named in the request's own
          `field_types` reports `json` (D-3(ii)'s default), and a `json`-
          typed field's value round-trips for every JSON shape (object,
          array, string, number, boolean) -- "書けること" alone is not
          enough (design section 6.2 item 3(iii)): the value read back
          must be the SAME JSON value, not merely accepted. A `boolean`-
          declared field gets the identical round-trip check.
          `field_types` omitted entirely on `create_entity` is also
          confirmed accepted here (the request's own optionality, D-3's
          own "never required" rule).
    """
    ok, document = _typed_catalog_precondition(adapter)
    if not ok:
        return

    entity = fresh_identifier("c19_typed")
    declared = {"marker": "string", "typed_bool": "boolean"}
    fields = ["marker", "typed_bool", "untyped_field"]
    adapter.create_entity_with_declared_types(fx.developer_a, entity, fields, declared)
    adapter.add_field_with_declared_type(fx.developer_a, entity, "typed_number", "number")

    # `field_types` omitted entirely -- a second entity, confirming the
    # request-level key stays fully optional (D-3's own "never required").
    untyped_entity = fresh_identifier("c19_untyped")
    adapter.create_entity_with_declared_types(fx.developer_a, untyped_entity, ["marker"], None)

    vocabulary = _contract_field_type_vocabulary()
    catalog = adapter.catalog_document(fx.runtime_a)
    entities = {row["entity"]: row for row in catalog["entities"]}
    assert entity in entities, f"{adapter.name}: catalog_document() does not list the just-created entity {entity!r}"
    row = entities[entity]

    # (i)
    field_types = row.get("field_types")
    assert isinstance(field_types, Mapping) and field_types, (
        f"{adapter.name}: catalog entity {entity!r} carries no non-empty 'field_types' -- {row!r}"
    )
    assert set(row["fields"]) <= set(field_types.keys()), (
        f"{adapter.name}: catalog entity {entity!r}'s 'fields' {row['fields']!r} is not a subset of its "
        f"'field_types' keys {sorted(field_types.keys())!r}"
    )
    assert all(v in vocabulary for v in field_types.values()), (
        f"{adapter.name}: catalog entity {entity!r}'s field_types {field_types!r} carries a value outside "
        f"the contract's own 7-word vocabulary {vocabulary!r}"
    )

    # (ii) declaration round-trip.
    assert field_types.get("typed_bool") == "boolean", (
        f"{adapter.name}: field declared 'boolean' via create_entity_with_declared_types reports "
        f"{field_types.get('typed_bool')!r} in the catalog"
    )
    assert field_types.get("typed_number") == "number", (
        f"{adapter.name}: field declared 'number' via add_field_with_declared_type reports "
        f"{field_types.get('typed_number')!r} in the catalog"
    )

    # (iii) undeclared default.
    assert field_types.get("untyped_field") == "json", (
        f"{adapter.name}: a field named in 'fields' but not in the request's own 'field_types' reports "
        f"{field_types.get('untyped_field')!r}, expected the D-3(ii) default 'json'"
    )

    # (iii) value round-trip on the json-typed field.
    json_values = ({"a": 1, "b": [2, 3]}, [1, "two", 3.0], "plain-string", 3.5, True, False)
    for value in json_values:
        marker = fresh_identifier("c19v")
        adapter.insert(fx.runtime_a, entity, {"marker": marker, "untyped_field": value})
        rows = adapter.select_eq(fx.runtime_a, entity, ["untyped_field"], "marker", marker)
        assert len(rows) == 1, f"{adapter.name}: expected exactly one row for marker {marker!r}, got {rows!r}"
        assert _json_equal(rows[0]["untyped_field"], value), (
            f"{adapter.name}: json-typed field round-trip failed -- wrote {value!r}, read back "
            f"{rows[0]['untyped_field']!r}"
        )

    # boolean round-trip (the same "true stays true" check, on the
    # explicitly-'boolean'-declared field rather than the default-json one).
    for value in (True, False):
        marker = fresh_identifier("c19v")
        adapter.insert(fx.runtime_a, entity, {"marker": marker, "typed_bool": value})
        rows = adapter.select_eq(fx.runtime_a, entity, ["typed_bool"], "marker", marker)
        assert len(rows) == 1
        assert rows[0]["typed_bool"] is value, (
            f"{adapter.name}: boolean-typed field round-trip failed -- wrote {value!r}, read back "
            f"{rows[0]['typed_bool']!r}"
        )


# design section 6.2 item 3(iv), v1.4 correction (work order WP-1 item 4,
# monitor ruling 2026-09-04): the negative side is exercised for the SIX
# words other than `json` -- `json` means any JSON value, so no violating
# value exists for it, and asserting one would be an empty-precondition
# vacuous vector (common-suite discipline 1). Exact values per the work
# order's own enumeration.
_NEGATIVE_VECTOR_CASES: tuple[tuple[str, Any], ...] = (
    ("boolean", 7),
    ("integer", "abc"),
    ("number", "abc"),
    ("string", 123),
    ("object", [1, 2, 3]),
    ("array", {"x": 1}),
)

# Review F8 (2026-09-04): a hand-maintained word list can silently drift
# from the contract's own `field_type` enum (measured, review mutation
# beta: dropping the `("object", [1, 2, 3])` row shrank collection from
# 44 to 40 items with NOTHING going red) -- this pins the word SET
# (never the per-word bad-value choices, which have no contract-derived
# source of truth) against `_contract_field_type_vocabulary()` minus
# `"json"` (D-3(iv)'s own "no violating value exists for json" rule),
# load-bearing from WP-1 itself (a spec-file edit, not a peer flip,
# already turns this red -- it does not wait on declare-first).
assert {case[0] for case in _NEGATIVE_VECTOR_CASES} == set(_contract_field_type_vocabulary()) - {"json"}, (
    "the negative vector's own word set has drifted from the contract's field_type enum minus 'json' -- "
    f"cases={sorted(c[0] for c in _NEGATIVE_VECTOR_CASES)!r}, "
    f"expected={sorted(set(_contract_field_type_vocabulary()) - {'json'})!r}"
)


@pytest.mark.parametrize(
    "field_type,bad_value", _NEGATIVE_VECTOR_CASES, ids=[case[0] for case in _NEGATIVE_VECTOR_CASES]
)
def test_c19_field_types_negative_rejects_value_outside_declared_type(
    adapter, fx: Fixture, field_type: str, bad_value: Any
) -> None:
    """Design section 6.2 item 3(iv): a value outside a field's declared
    type is refused with `VALIDATION_FAILED`. Collected as 6 (words) x 4
    (adapters) = 24 items -- never a 7th `json` row (there is no
    violating value for `json`, see the constant's own comment above)."""
    ok, document = _typed_catalog_precondition(adapter)
    if not ok:
        return

    entity = fresh_identifier(f"c19_neg_{field_type}")
    adapter.create_entity_with_declared_types(fx.developer_a, entity, ["typed_field"], {"typed_field": field_type})
    with pytest.raises(ConformanceDenial) as exc_info:
        adapter.insert(fx.runtime_a, entity, {"typed_field": bad_value})
    assert exc_info.value.code == "VALIDATION_FAILED", (
        f"{adapter.name}: writing {bad_value!r} into a field declared {field_type!r} got "
        f"{exc_info.value.code!r}, expected VALIDATION_FAILED"
    )


# --- whole-registry vacuity guard (work order WP-1 item 8) ---------------


def test_c19_every_control_surface_adapter_declares_1_6_0():
    """Whole-registry guard, same non-parametrized/`registered_adapters()`
    -walking shape as `test_c09_every_control_surface_adapter_declares_
    1_5_0` (phase 5 WP-1's identically-purposed guard for the PRIOR
    contract bump) -- requires every control-surface-bearing registered
    adapter to declare `contract_version >= 1.6.0`. Registered `xfail(
    strict=True)` in WP-1 (false until every peer flips); the `xfail` is
    removed here, in the SAME commit as the LAST 1.6.0 flip (WP-3 追補,
    supervisor ruling 2026-09-04 -- both peers now declare 1.6.0), the
    guard's own body unchanged -- so that flip commit itself demonstrates
    the guard turning green unaided, exactly as the 1.4.0/1.5.0 guards did
    at their own last flips.

    This guard is what stands in, for THIS work package, for the fact
    that `test_c19_application_credential_verbatim_...`/`test_c19_
    surfaces_...`/`test_c19_field_types_...` above are all silently
    vacuous on every currently-registered adapter (module docstring) --
    it is never reported here as "green because verified" (common-suite
    discipline 3).
    """
    control_surface_adapters: list[str] = []
    not_1_6_0: list[str] = []
    for name, adapter_obj in registered_adapters().items():
        if _control_plane_status(adapter_obj) not in ("enabled", "partial"):
            continue
        control_surface_adapters.append(name)
        document = _capability_document(adapter_obj)
        if _semver_tuple(str(document.get("contract_version", "0.0.0"))) < (1, 6, 0):
            not_1_6_0.append(f"{name}: declares {document.get('contract_version')!r}")

    assert control_surface_adapters, (
        "no registered adapter has a control surface at all -- this guard is vacuous by construction"
    )
    assert not not_1_6_0, (
        f"not every control-surface-bearing registered adapter declares contract_version >= 1.6.0: "
        f"{not_1_6_0!r} (control-surface adapters checked: {control_surface_adapters!r})"
    )


# --- static fixed test: no adapter composes or decomposes the bearer -----
# (design section 6.2's own "adapter が bearer を組み立ても分解もしないこと
# の静的固定", D-1(e); work order WP-1 item 8's second xfail(strict=True))


# Prototyped and calibrated in scratchpad/wp1y/static_proto.py against all
# four real adapter files before being placed here (common-suite
# discipline 5: undesigned machinery is prototyped and measured before it
# is placed in the suite). One false positive was found and fixed during
# calibration -- see `_composition_findings`'s own comment below; the
# fixed form has zero false positives/negatives against the four real
# files as of this WP (WP-1 completion report has the run transcript).
# No exclusion list was needed.

_ID_MARKERS = ("credential_id", "credential_ref")
_SECRET_MARKERS = ("secret",)
_DECOMPOSITION_METHODS = ("split", "rsplit", "partition", "rpartition")

# Review F7 / audit finding (vi) (2026-09-04): a genuine, reviewed
# non-secret use of one of `_DECOMPOSITION_METHODS` with a literal "."
# argument (or the hand-rolled find/index-based slice equivalent) that
# the broadened scanner below would otherwise flag. Each entry is
# (relative-path-string, lineno) -> a stated reason. Calibrated against
# every currently-registered adapter's own module file (WP-1 completion
# report has the run transcript) -- empty means none were found; a
# future finding is added here ONE LINE AT A TIME, with a reason, never
# by narrowing the scanner's own rule back toward name-dependence.
_DECOMPOSITION_ALLOWLIST: dict[tuple[str, int], str] = {}

# Phase 6 WP-3 差し戻し 最終ラウンド (supervisor ruling 2026-09-04, 裁定 2,
# review F2/F3, audit finding C): the MIRROR of `_DECOMPOSITION_ALLOWLIST`
# above, for composition -- port v1.10's new `tampered_bearer(handle) ->
# str` abstract method is EXPLICITLY the one place every plug is permitted
# (indeed required) to compose a bearer string (`handle.credential_ref` +
# "." + a fresh, never-issued identifier), so the common suite can
# construct a KNOWN-BAD credential without a peer-specific store dial-in
# (`tampered_bearer`'s own port docstring).
#
# Keyed by (relative-path-string, ENCLOSING FUNCTION NAME) -- never a bare
# line number (F2's own empirical finding: a line-keyed entry goes stale
# silently the moment the function it names gains/loses a line above it,
# and this round's own two stale entries, discovered by direct re-
# execution against the allowlist-ignored scanner, are exactly that
# failure). `test_c19_composition_allowlist_has_no_dead_entries` below
# asserts every entry here corresponds to an ACTUAL finding when the
# allowlist is ignored -- an entry that suppresses nothing is a bug in
# this table, caught structurally, not merely by prose review.
_COMPOSITION_ALLOWLIST: dict[tuple[str, str], str] = {
    ("MitateDB-api/conformance/conformance_adapter_mitatedb.py", "tampered_bearer"):
        "tampered_bearer: the port's own designated bearer-tampering primitive (brief item C)",
    ("MitateDB-api/conformance/conformance_adapter_mitatedb_http.py", "tampered_bearer"):
        "tampered_bearer: the port's own designated bearer-tampering primitive (brief item C)",
    ("r2db-api/conformance/conformance_adapter_r2db.py", "tampered_bearer"):
        "tampered_bearer: the port's own designated bearer-tampering primitive (brief item C)",
    ("r2db-api/conformance/conformance_adapter_r2db_http.py", "tampered_bearer"):
        "tampered_bearer: the port's own designated bearer-tampering primitive (brief item C)",
}


def _scanned_adapter_files() -> tuple[Path, ...]:
    """Derived from the LIVE registry (`registered_adapters()`), never a
    hardcoded tuple (review F7 / audit finding (vi)) -- a hardcoded list
    of 4 files silently drops a 5th registered adapter's own module from
    this scan, the same gap the whole-registry vacuity guard above
    already avoids by walking `registered_adapters()` itself instead of
    a name list. One file per DISTINCT module (`r2db-api`/`r2db-api-http`
    are two different modules, both scanned; a future adapter sharing a
    module with an already-registered one is scanned once, correctly,
    not twice)."""
    paths: set[Path] = set()
    for name, adapter_obj in registered_adapters().items():
        module = sys.modules[type(adapter_obj).__module__]
        module_file = getattr(module, "__file__", None)
        assert module_file, f"{name}: module {module.__name__!r} carries no __file__ to scan"
        paths.add(Path(module_file).resolve())
    return tuple(sorted(paths))


def _text(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def _is_id_shaped(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _ID_MARKERS)


def _is_secret_shaped(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _SECRET_MARKERS)


def _is_dot_literal(node) -> bool:
    return isinstance(node, ast.Constant) and node.value == "."


def _joinedstr_expr_and_literal_parts(node: ast.JoinedStr) -> tuple[list[str], list[str]]:
    """Splits an f-string's own values into (interpolated-expression
    texts, literal-text runs). Kept separate deliberately (calibration
    finding): checking id-/secret-SHAPE against literal PROSE produced a
    false positive on `f'could not parse credential_id/secret from ...
    {stdout!r}'` (an error MESSAGE that happens to mention both words) --
    composition is about what is INTERPOLATED, never about what an
    adjacent literal string happens to say."""
    expr_parts: list[str] = []
    literal_parts: list[str] = []
    for value in node.values:
        if isinstance(value, ast.FormattedValue):
            expr_parts.append(_text(value.value))
        elif isinstance(value, ast.Constant) and isinstance(value.value, str):
            literal_parts.append(value.value)
    return expr_parts, literal_parts


def _build_parent_map(tree: ast.AST) -> dict[int, ast.AST]:
    """Maps `id(node) -> parent node` for every node in `tree` -- `ast`
    itself carries no parent pointers, so a caller that needs to walk
    UP from a matched node (here: to find its innermost enclosing
    function) must build this once per tree."""
    parents: dict[int, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[id(child)] = parent
    return parents


def _enclosing_function_name(node: ast.AST, parents: dict[int, ast.AST]) -> str | None:
    """Walks UP `parents` from `node` to the nearest `FunctionDef`/
    `AsyncFunctionDef` ancestor's own name -- `None` for a match at
    module level (no enclosing function at all)."""
    current = parents.get(id(node))
    while current is not None:
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return current.name
        current = parents.get(id(current))
    return None


def _secret_bound_names(tree: ast.AST) -> dict[int, set[str]]:
    """Phase 6 WP-3 差し戻し 最終ラウンド (supervisor ruling 2026-09-04,
    裁定 2 (b), review F3): a SIMPLE, single-function-scoped dataflow
    pass -- for every `FunctionDef`/`AsyncFunctionDef` node, collects the
    plain local names directly assigned from a `.secret` attribute
    access (`token = handle.secret`, `x.y = z.secret` excluded --
    only a bare `Name` target) anywhere in that function's own body
    (nested function bodies included, a conservative over-approximation:
    a name that would actually be scoped to a DEEPER nested closure is
    still treated as secret-shaped in the outer function's own set,
    which only makes this MORE cautious, never less). Returns `{id(func_
    node): {names...}}` -- deliberately keyed by the function node's own
    identity, not its name (two functions can share a name across
    different classes/nesting levels in the same file).

    This closes the specific gap review finding R1 measured: a receiver-
    name-independent decomposition scan already existed (`_decomposition_
    findings` below), but composition detection still required the
    INTERPOLATED text itself to literally contain the substring "secret"
    -- `token = handle.secret; f"{handle.credential_ref}.{token}"` evades
    that substring check even though `token` genuinely IS the secret,
    one assignment removed. This function makes that one-hop indirection
    visible to `_is_secret_shaped_at`."""
    result: dict[int, set[str]] = {}
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        names: set[str] = set()
        for node in ast.walk(func):
            if not isinstance(node, ast.Assign):
                continue
            if not (isinstance(node.value, ast.Attribute) and node.value.attr == "secret"):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        result[id(func)] = names
    return result


def _is_secret_shaped_at(expr_node: ast.AST, text: str, *, bound_names: set[str]) -> bool:
    """`_is_secret_shaped` (substring on the expression's own unparsed
    text) OR (the expression is a bare local name this function's own
    `_secret_bound_names` dataflow pass traced back to a `.secret`
    attribute access) -- the two independent ways an interpolated part
    can genuinely BE the secret without spelling out "secret" itself."""
    if _is_secret_shaped(text):
        return True
    return isinstance(expr_node, ast.Name) and expr_node.id in bound_names


def _composition_findings(tree: ast.AST, relative_path: str) -> list[str]:
    """(a)合成不在, BROADENED (supervisor ruling 2026-09-04, 裁定 2 (a),
    review F2/F3, audit finding C): the prior form required the SECOND
    (non-id) interpolated part to itself be secret-SHAPED (contain the
    substring "secret") -- measured, direct re-execution with the
    allowlist ignored, to find ZERO findings against any of the four
    real `tampered_bearer` bodies (`f"{handle.credential_ref}.{fresh_
    identifier('tampered')}"`): `fresh_identifier('tampered')` names no
    secret at all, by design (a deliberately KNOWN-BAD, never-issued
    probe value) -- so the substring check never fired, and the four
    `_COMPOSITION_ALLOWLIST` entries suppressed nothing (dead lines).

    This peer's own bearer shape (`credential_wire.py`'s own docstring)
    IS `<credential_id>.<secret>` -- joining an id-shaped expression with
    ANY other expression via a literal "." is ALREADY the composition
    act on this port, regardless of what the second part happens to be
    named or shaped like; requiring it to ALSO look like "secret" was
    over-narrow from the start. Dropped here for all three forms
    (f-string/`+`/`".".join`) -- an id-shaped part plus a literal "."
    plus ANY second part is now sufficient. `_is_secret_shaped_at`
    (裁定 2 (b), dataflow-aware) still runs and is recorded in the
    finding message for audit traceability (which part genuinely reads
    as secret-shaped, directly or one assignment removed), but is no
    longer a GATING condition -- see the module-level rationale above.

    Findings are keyed by (relative_path, ENCLOSING FUNCTION NAME) for
    `_COMPOSITION_ALLOWLIST` lookups (F2: line-number keys go stale
    silently; a function-name key survives an unrelated line shifting
    inside the same function) -- port v1.10's own `tampered_bearer` is
    the ONE designated exception to the "no composition" rule."""
    findings: list[str] = []
    parents = _build_parent_map(tree)
    secret_names_by_func = _secret_bound_names(tree)

    def _bound_names_for(node: ast.AST) -> set[str]:
        current = parents.get(id(node))
        while current is not None:
            if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return secret_names_by_func.get(id(current), set())
            current = parents.get(id(current))
        return set()

    def _allowlisted(node: ast.AST) -> bool:
        func_name = _enclosing_function_name(node, parents)
        return func_name is not None and (relative_path, func_name) in _COMPOSITION_ALLOWLIST

    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            expr_nodes = [v.value for v in node.values if isinstance(v, ast.FormattedValue)]
            expr_parts = [_text(e) for e in expr_nodes]
            _, literal_parts = _joinedstr_expr_and_literal_parts(node)
            has_id = any(_is_id_shaped(p) for p in expr_parts)
            has_dot_literal = any("." in p for p in literal_parts)
            if has_id and has_dot_literal and len(expr_nodes) >= 2:
                if _allowlisted(node):
                    continue
                bound = _bound_names_for(node)
                secret_note = any(_is_secret_shaped_at(e, t, bound_names=bound) for e, t in zip(expr_nodes, expr_parts))
                findings.append(
                    f"line {node.lineno}: composition(f-string, secret-shaped-part={secret_note}): {_text(node)}"
                )
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            text = _text(node)
            if _is_id_shaped(text) and "." in text:
                if _allowlisted(node):
                    continue
                bound = _bound_names_for(node)
                secret_note = _is_secret_shaped_at(node, text, bound_names=bound)
                findings.append(f"line {node.lineno}: composition(+, secret-shaped-part={secret_note}): {text}")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "join":
            sep_text = _text(node.func.value)
            is_dot_sep = "." in sep_text or (isinstance(node.func.value, ast.Constant) and node.func.value.value == ".")
            if is_dot_sep:
                args_text = " ".join(_text(a) for a in node.args)
                if _is_id_shaped(args_text):
                    if _allowlisted(node):
                        continue
                    bound = _bound_names_for(node)
                    secret_note = _is_secret_shaped_at(node, args_text, bound_names=bound)
                    findings.append(
                        f"line {node.lineno}: composition(join, secret-shaped-part={secret_note}): {_text(node)}"
                    )
    return findings


def _decomposition_findings(tree: ast.AST, relative_path: str) -> list[str]:
    """(b)分解不在, BROADENED (review F7 / audit finding (vi), 2026-09-04):
    the prior form only flagged a `.split()`/`.partition()`/`.rsplit()`
    call whose own RECEIVER text mentioned "secret"/"bearer"
    (name-dependent) -- measured, review mutation, to miss `token =
    handle.secret; token.split(".")` entirely (an intermediate variable
    evades name-based detection, even though the SAME line is exactly
    the prohibited decomposition). This form drops the receiver-name
    dependency: it flags ANY `.split(".")`/`.rsplit(".")`/
    `.partition(".")`/`.rpartition(".")` call -- regardless of receiver
    -- whose own FIRST argument is the literal delimiter `"."` (this
    port's own credential locator separator), plus the hand-rolled
    equivalent (a slice subscript whose bound is a `.find(".")`/
    `.index(".")` call on that same delimiter). A finding at
    `(relative_path, lineno)` already recorded in `_DECOMPOSITION_
    ALLOWLIST` (a genuine, reviewed non-secret use, with a stated reason)
    is excluded -- never a blanket allowance, one named line at a time.

    Still a SYNTACTIC scan, not a semantic one (CONDITIONS.md's C-19 row
    limit (e)): it cannot see decomposition performed by a function this
    file merely CALLS (e.g. handing the bearer to an external helper
    that itself splits it) -- only expressions written directly in the
    scanned file's own AST. Deliberately separate from (a) composition
    detection (design section 6.2's own warning): dropping the
    composition alone but deriving `credential_id` by SPLITTING the
    bearer would pass (a) while still being exactly the prohibited
    behavior port v1.10's verbatim regulation forbids.
    """
    findings: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _DECOMPOSITION_METHODS
            and node.args
            and _is_dot_literal(node.args[0])
        ):
            if (relative_path, node.lineno) in _DECOMPOSITION_ALLOWLIST:
                continue
            findings.append(f'line {node.lineno}: decomposition(.{node.func.attr}(".")): {_text(node)}')
        elif isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Slice):
            bounds = (node.slice.lower, node.slice.upper)
            hit = any(
                isinstance(bound, ast.Call)
                and isinstance(bound.func, ast.Attribute)
                and bound.func.attr in ("find", "index")
                and bound.args
                and _is_dot_literal(bound.args[0])
                for bound in bounds
            )
            if hit:
                if (relative_path, node.lineno) in _DECOMPOSITION_ALLOWLIST:
                    continue
                findings.append(f"line {node.lineno}: decomposition(slice via find/index('.')): {_text(node)}")
    return findings


def test_c19_adapters_never_compose_or_decompose_the_bearer_secret() -> None:
    """Static, source-level fixed test (design section 6.2's own D-1(e),
    work order WP-1 item 8's second `xfail(strict=True)`): scans every
    REGISTERED adapter's own module file's AST (`_scanned_adapter_files()`
    below, never the port, never a peer's product `src/`) for (a)
    composition and (b) decomposition (see each helper's own docstring
    above).

    Phase 6 WP-3 (design docs/design/PHASE6_CONTRACT_160_CLIENT_
    DISCOVERY_V1.md section 3 D-1(d)): `xfail(strict=True)` removed in
    this same commit as MitateDB-api's own last 1.6.0 flip --
    `conformance_adapter_mitatedb_http.py`'s own 5 composition sites
    (`issue_credential`/`issue_credential_inband`/`_control_send`/
    `audit_query_on_data_plane_host`/`isolated_control_surface`) are
    removed alongside it: every real issuance point on that peer now
    returns an already-composed, ready-to-present bearer (`credential_
    store_postgres.PostgresCredentialStore.issue`, `control_http.py`'s
    own issue/rotate JSON responses, `ops.py`'s own CLI stdout), so the
    adapter has nothing left to compose. This flip is a real, load-
    bearing removal, not a weakening of the check itself -- the scan
    logic below is unchanged from WP-1's own registration.
    """
    all_findings: dict[str, list[str]] = {}
    for path in _scanned_adapter_files():
        relative_path = str(path.relative_to(REPO_ROOT))
        tree = ast.parse(path.read_text(), filename=str(path))
        findings = _composition_findings(tree, relative_path) + _decomposition_findings(tree, relative_path)
        if findings:
            all_findings[relative_path] = findings

    assert not all_findings, (
        "one or more conformance adapters compose or decompose a credential's bearer secret "
        f"(port v1.10 verbatim regulation, D-1(e)): {all_findings!r}"
    )


def test_c19_composition_allowlist_has_no_dead_entries() -> None:
    """裁定 2 (F2/F3, audit finding C): every `_COMPOSITION_ALLOWLIST`
    entry must suppress a REAL finding -- an entry that matches nothing
    (the pre-fix state: all 4 entries were dead, `fresh_identifier(
    'tampered')` never satisfied the old substring-based `has_secret`
    gate at all) is a bug in this table, not a harmless no-op. Measured
    directly: run the scanner with the allowlist ignored, then assert
    every `_COMPOSITION_ALLOWLIST` key names a (relative_path, function)
    pair that the ignored-allowlist run actually flagged at least once."""
    findings_by_key: dict[tuple[str, str], int] = {}
    for path in _scanned_adapter_files():
        relative_path = str(path.relative_to(REPO_ROOT))
        tree = ast.parse(path.read_text(), filename=str(path))
        parents = _build_parent_map(tree)
        secret_names_by_func = _secret_bound_names(tree)

        def _bound_names_for(node: ast.AST, _parents=parents, _by_func=secret_names_by_func) -> set[str]:
            current = _parents.get(id(node))
            while current is not None:
                if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    return _by_func.get(id(current), set())
                current = _parents.get(id(current))
            return set()

        for node in ast.walk(tree):
            matched = False
            if isinstance(node, ast.JoinedStr):
                expr_nodes = [v.value for v in node.values if isinstance(v, ast.FormattedValue)]
                expr_parts = [_text(e) for e in expr_nodes]
                _, literal_parts = _joinedstr_expr_and_literal_parts(node)
                if any(_is_id_shaped(p) for p in expr_parts) and any("." in p for p in literal_parts) and len(expr_nodes) >= 2:
                    matched = True
            elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
                text = _text(node)
                if _is_id_shaped(text) and "." in text:
                    matched = True
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "join":
                sep_text = _text(node.func.value)
                is_dot_sep = "." in sep_text or (isinstance(node.func.value, ast.Constant) and node.func.value.value == ".")
                if is_dot_sep:
                    args_text = " ".join(_text(a) for a in node.args)
                    if _is_id_shaped(args_text):
                        matched = True
            if matched:
                func_name = _enclosing_function_name(node, parents)
                if func_name is not None:
                    findings_by_key[(relative_path, func_name)] = findings_by_key.get((relative_path, func_name), 0) + 1

    dead_entries = [key for key in _COMPOSITION_ALLOWLIST if findings_by_key.get(key, 0) == 0]
    assert not dead_entries, (
        f"_COMPOSITION_ALLOWLIST entries that suppress no actual finding (dead lines): {dead_entries!r}"
    )
    # And the converse direction (常設規律1's own "非空振り" spirit,
    # applied to this table too): every registered plug's own
    # `tampered_bearer` genuinely IS flagged when the allowlist is
    # ignored -- exactly one composition site per plug.
    for relative_path, function_name in _COMPOSITION_ALLOWLIST:
        assert findings_by_key.get((relative_path, function_name), 0) >= 1, (
            f"{relative_path}::{function_name}: allowlisted but the allowlist-ignored scan found nothing there"
        )
