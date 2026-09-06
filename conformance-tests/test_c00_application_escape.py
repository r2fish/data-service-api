"""C-00 -- a credential for Application A has no path to B or control/
provisioning authority (SI-00, SI-02, SI-07).

design: docs/design/PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md
D-6.7, registered in `conformance-tests/CONDITIONS.md`. Every test here
carries `@pytest.mark.condition("C-00")` via the module-level `pytestmark`.

C-00's own proposition ("no path to B or control/provisioning authority")
is, in substantial part, ALREADY fixed by two other conditions' own
executable vectors -- per this WP's own instruction ("C-01/C-14 が既に
固定している部分は参照し、欠けている vector だけ足す") and禁止事項 7
("同じ assert を二重に書かない"), this file does not clone either:

  - `test_c01_scope_binding.py::test_cross_application_entity_is_
    unreachable` already fixes the data-plane half for the ordinary
    `select_eq`/`insert`/`delete` entry points (application A's runtime
    credential cannot reach application B's entity through them), plus
    `::test_cross_application_denial_does_not_disclose_existence`
    (non-disclosure).
  - `test_c14_authority_boundary.py::test_c14_application_credentials_
    fail_closed_on_every_control_operation` already fixes the
    control/provisioning-authority half exhaustively (both roles, all 11
    in-band control endpoints).

This file adds exactly the two vectors those do NOT cover:

  1. **the batch entry point** (`attempt_batch_with_addresses`) -- a
     STRUCTURALLY DIFFERENT dispatch path from the single-operation
     `select_eq`/`insert`/`delete` C-01 already exercises. Application A's
     runtime credential, targeting application B's own entity through a
     batch request, must be denied identically -- application B's row
     count must not change.
  2. **catalog disclosure** -- `catalog_document()` (not exercised by C-01
     at all) must not list application B's entity name in application A's
     own catalog view. Neither honest "nothing to disclose" shape (a
     `CATALOG_SURFACE_ABSENT` structural absence, or a real, present
     entry point that denies every request uniformly) is treated as a
     vacuous pass without its own assertion: a real denial's code is
     still checked against the contract's own code vocabulary, AND
     (WP-5 rework, review finding 5) the peer's own declaration is
     cross-checked for honesty in either such branch -- see this test
     function's own docstring for the measured, currently-0-of-4-plugs
     reach of both branches.

Uses `conftest.isolated`/`provision_pair` (port v1.11's own `isolated_
application_surface()`, C-05's primitive) rather than the ordinary `fx`
fixture: both applications this file needs are provisioned/deprovisioned
entirely within one isolated instance per test, so this file's own
contribution never permanently grows the session-scoped adapter's
`applications` registry -- see `conftest.isolated`'s own docstring for the
full, four-round measurement history behind this choice. Neither test in
this file uses a `where` filter, so neither trips the isolated profile's
own small `operation_depth` bound (see `conftest.provision_pair`'s own
docstring for the pitfall this avoids).
"""
from __future__ import annotations

import pytest

from adapter import (
    CATALOG_SURFACE_ABSENT,
    BatchOperation,
    ConformanceAdapter,
    ConformanceDenial,
    fresh_identifier,
    load_contract_error_codes,
)
from conftest import provision_pair

pytestmark = pytest.mark.condition("C-00")

# design docs/design/CONFORMANCE_ADAPTER_V1.md section 12 / `Fixture`'s own
# docstring: the common suite's convention for a placeholder field name safe
# against any peer's own reserved names (mirrors `test_c01_scope_binding.
# py`'s identical `_PLACEHOLDER_FIELD`).
_PLACEHOLDER_FIELD = "item_key"


def _assert_is_contract_code(code: str) -> None:
    assert code in load_contract_error_codes(), f"denial code {code!r} is not a contract error code"


def _application_catalog_status(iso: ConformanceAdapter) -> str:
    return iso.capability_document().get("capabilities", {}).get("application_catalog", {}).get("status", "unavailable")


def test_c00_batch_entry_point_does_not_reach_another_application(
    adapter: ConformanceAdapter, isolated
) -> None:
    iso = isolated
    _dev_a, runtime_a, _app_a = provision_pair(iso, app_prefix="c00batcha")
    developer_b, runtime_b, _app_b = provision_pair(iso, app_prefix="c00batchb")
    entity_b = fresh_identifier("c00batch_b_entity")
    iso.create_entity(developer_b, entity_b, {_PLACEHOLDER_FIELD: "text"})

    count_before = iso.count(runtime_b, entity_b)
    with pytest.raises(ConformanceDenial) as ei:
        iso.attempt_batch_with_addresses(runtime_a, entity_b, [
            BatchOperation(operation="insert", values={_PLACEHOLDER_FIELD: "x"}),
        ])
    _assert_is_contract_code(ei.value.code)

    count_after = iso.count(runtime_b, entity_b)
    assert count_after == count_before, (
        f"{adapter.name}: application B's row count changed ({count_before} -> {count_after}) after "
        "application A's runtime credential presented a batch targeting B's own entity"
    )


def test_c00_catalog_document_does_not_disclose_another_applications_entities(
    adapter: ConformanceAdapter, isolated
) -> None:
    iso = isolated
    developer_a, _runtime_a, _app_a = provision_pair(iso, app_prefix="c00cata")
    developer_b, _runtime_b, _app_b = provision_pair(iso, app_prefix="c00catb")
    entity_a = fresh_identifier("c00cat_a_entity")
    entity_b = fresh_identifier("c00cat_b_entity")
    iso.create_entity(developer_a, entity_a, {"label": "text"})
    iso.create_entity(developer_b, entity_b, {"label": "text"})

    # WP-5 rework (review finding 5): re-measured directly (a prior
    # comment here, since corrected, wrongly assumed `MitateDB-api-http`
    # still declared `application_catalog: unavailable` and took the
    # `except ConformanceDenial` branch below -- stale as of the phase 6
    # WP-3 flip). As of THIS measurement, all 4 currently-registered
    # plugs (`r2db-api`, `r2db-api-http`, `MitateDB-api`,
    # `MitateDB-api-http`) declare `application_catalog: enabled` and
    # return a real document here -- the disclosure sweep below (the
    # entity_names/`entity_b` checks) runs, and provides genuine
    # evidence, on all 4 of them. BOTH early-return branches immediately
    # below (`except ConformanceDenial` and `CATALOG_SURFACE_ABSENT`) are
    # therefore currently unreached by any of the 4 registered plugs --
    # disclosed in `CONDITIONS.md`'s own C-00 row rather than left silent
    # -- kept only for a future peer that genuinely takes one of those two
    # honest "nothing to disclose" shapes. Each still carries its own
    # declaration-honesty assert (the peer's own `application_catalog`
    # status must not say 'enabled' while a real call denies/omits the
    # surface) so a future peer that DOES reach one of them is still
    # genuinely checked, not waved through on a bare early return.
    try:
        document = iso.catalog_document(developer_a)
    except ConformanceDenial as denial:
        # A peer whose catalog surface exists but refuses every request
        # uniformly discloses nothing at all by construction -- still a
        # genuine assertion (the code itself is contract-valid), not a
        # bare pass. Currently unreached (see this test's own docstring
        # above), kept for a future peer that takes this shape.
        _assert_is_contract_code(denial.code)
        # Declaration honesty (review finding 5): a denial branch with
        # zero evidence toward C-00's own disclosure proposition is only
        # acceptable when the peer's OWN declaration says there is
        # nothing to disclose from in the first place -- a peer that
        # denies catalog_document() while still claiming
        # `application_catalog: enabled` would be lying about the surface
        # this vector needs to exercise.
        assert _application_catalog_status(iso) != "enabled", (
            f"{adapter.name}: catalog_document() was denied ({denial.code!r}) but this peer declares "
            "application_catalog 'enabled' -- an enabled catalog surface must not uniformly deny every "
            "request (declaration honesty)"
        )
        return

    if document == CATALOG_SURFACE_ABSENT:
        # No catalog entry point exists on this peer's public surface at
        # all -- nothing to disclose from, honestly, structurally absent.
        # Same declaration-honesty check as the denial branch above.
        assert _application_catalog_status(iso) != "enabled", (
            f"{adapter.name}: catalog_document() reported CATALOG_SURFACE_ABSENT but this peer declares "
            "application_catalog 'enabled'"
        )
        return

    entity_names = {item["entity"] for item in document.get("entities", [])}
    assert entity_names, (
        f"{adapter.name}: catalog_document() for application A's own developer reported no entities at "
        "all -- this test's own non-vacuity requirement (application A's own fixture entities must appear)"
    )
    assert entity_b not in entity_names, (
        f"{adapter.name}: catalog_document() for application A's own developer disclosed application B's "
        f"entity {entity_b!r}"
    )
