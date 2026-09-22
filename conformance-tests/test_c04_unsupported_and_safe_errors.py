"""C-04 -- unsupported operations fail before execution; public error bodies
are safe, structured diagnostics (SI-05, SI-10, SI-15).

design: docs/design/PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md
D-6.7, registered in `conformance-tests/CONDITIONS.md`. Every test here
carries `@pytest.mark.condition("C-04")` via the module-level `pytestmark`.

Two, independent propositions, each with its own test function:

  1. **execution order**: an operation name outside the mutation vocabulary
     (`insert`/`update`/`upsert`/`delete`) is refused *before* execution --
     state (row count) unchanged. This is a fresh vector, not a re-run of
     C-17's own `upsert`-with-no-declared-key case (that one is about a
     DIFFERENT precondition -- an entity's own uniqueness declaration --
     and stays C-17's; this one is about the OPERATION NAME ITSELF being
     outside the contract's own closed vocabulary, independent of any
     entity's schema). **Measured code difference across plugs (not a
     defect this test papers over, disclosed here)**: three of the four
     currently-registered plugs (`r2db-api`, `r2db-api-http`,
     `MitateDB-api`) reach a business-logic vocabulary check and refuse
     with `CAPABILITY_UNSUPPORTED`; `MitateDB-api-http`'s own wire-level
     JSON-shape check enumerates the `operation` field itself and refuses
     the same, genuinely out-of-vocabulary value with `VALIDATION_FAILED`
     -- BEFORE the business-logic layer is ever reached, i.e. still a
     pre-execution, shape-level rejection of the same underlying fact.
     Both codes are accepted here for that reason; `NOT_FOUND`/`CONFLICT`
     (evidence the peer resolved something or executed a comparison before
     ever checking the operation name) are not.
  2. **safe error content**: a real `ConformanceDenial`'s own `details`
     mapping -- the one, deliberately structured surface a public client
     ever sees for a denial (design section 4.1 excludes the native
     exception's message text from this port entirely) -- carries no
     stack-trace, SQL-fragment, or DSN-shaped substring. Exercised against
     the richest `details` mapping this port currently has any real
     traffic for: an unconfirmed destructive request's `DESTRUCTIVE_
     CONFIRMATION_REQUIRED` denial (`required_confirmation`/`consequence`/
     `reversible_alternative`/`recovery`, all real, peer-computed strings
     on every one of the four currently-registered adapters, which all
     declare `contract_version >= 1.2.0` -- design D-6.7's "誤入力" here is
     a destructively-shaped request presented with no confirmation at all,
     a genuine client mistake, not a synthetic probe this suite
     fabricates). The negative-content scanner itself (`conftest.assert_
     no_unsafe_diagnostic_content`) is shared with C-10's own generic-proxy
     check -- this file uses it directly, against one specific denial's
     `details`, rather than through C-10's own all-calls proxy.

     **Per-peer probe choice (measured, WP-5, `conftest.provision_pair`'s
     own docstring)**: `delete()`'s own request shape carries its filter
     as a `where` LIST-of-dict, one nesting level deeper than a flat
     insert -- this trips `isolated_application_surface()`'s own small
     `operation_depth=4` bound on both `r2db-api` plugs (which enforce
     that class), producing `LIMIT_EXCEEDED` instead of the denial this
     test is checking for. `drop_entity()`'s own request shape is a flat,
     single-level dict on every peer, so it is used for the `r2db-api`
     pair instead; `MitateDB-api`/`MitateDB-api-http` route to `delete()`
     because `drop_entity` is declared structurally unsupported on both
     (`_peer_declares_drop_entity_supported`'s own docstring). **Measured,
     Phase 8 WP-1a follow-on (this ruling's own re-run) -- disclosed here,
     not fixed here (out of this ruling's file scope)**: `delete()` is
     genuinely safe on `MitateDB-api` in-process (its own `request` dict
     nests to depth 3: `{collection,filters,...} -> filters[] -> Filter`,
     comfortably under the bound=4), but its `MitateDB-api-http` HTTP-wire
     counterpart is NOT -- the JSON body `{"operations": [{"operation":
     "delete", "where": [{"field", "operator", "value"}], ...}]}` nests to
     depth 5 (`operations[] -> op -> where[] -> filter-dict`), one level
     past the bound, and `operation_depth` is `enforced` on this transport
     (`cell.py` comment above `"operation_depth": "enforced"`) -- this is
     the SAME structural fact the `r2db-api` paragraph above already
     names, now also reachable on `MitateDB-api-http` specifically. This
     surfaces only now: the pre-ruling `_operation_depth_enforced` proxy
     misrouted this plug into `drop_entity()` (`SurfaceAbsent`) instead,
     which masked it behind a different failure. `test_c04_error_details_
     carry_no_unsafe_diagnostic_content[MitateDB-api-http]` stays red
     after this ruling's fix for this reason; resolving it needs either a
     different wire shape or a different isolated `operation_depth` bound
     for this transport -- both out of `_peer_declares_drop_entity_
     supported`'s own file-scoped mandate, so left for a follow-on
     decision rather than patched here.

     **Branch condition, supervisor ruling 2026-09-06 (Phase 8 WP-1a
     follow-on; supersedes the WP-5 rework 2's `limit_enforcement.
     operation_depth` proxy)**: `operation_depth` enforcement stopped
     correlating with `drop_entity` support the moment WP-1a's own rework
     made `MitateDB-api` also enforce `operation_depth` -- that proxy then
     misrouted both MitateDB plugs into the `drop_entity()` probe below,
     where `drop_entity` is `SurfaceAbsent`. The branch is now keyed on
     the ACTUALLY DECLARED capability instead: `_peer_declares_drop_
     entity_supported` below reads whether `drop_entity` is a schema
     operation the plug's own capability document reports it executes,
     never the plug's own name and never a proxy signal. `r2db-api`/
     `r2db-api-http` declare it supported, `MitateDB-api`/`MitateDB-api-
     http` declare it structurally unsupported -- see that helper's own
     docstring for the exact key and the contract/source line references
     backing each side.

Uses `conftest.isolated`/`provision_pair` (port v1.11's own `isolated_
application_surface()`, C-05's primitive) rather than the ordinary `fx`
fixture: this condition needs one ordinary, working application, and `fx`
used per test with no teardown permanently grows the session-scoped
adapter's own `applications` registry (measured, WP-5) -- see `conftest.
isolated`'s own docstring for the full, four-round measurement history.
"""
from __future__ import annotations

import pytest

from adapter import ConformanceAdapter, ConformanceDenial, fresh_identifier, load_contract_error_codes
from conftest import assert_no_unsafe_diagnostic_content, provision_pair

pytestmark = pytest.mark.condition("C-04")

# Both codes are pre-execution, shape/capability-level refusals of the same
# underlying fact (an operation name outside the contract's closed
# vocabulary) -- see this module's own docstring for the measured,
# per-plug difference in which one a given plug's own dispatch layer
# reaches first.
_ACCEPTED_UNSUPPORTED_OPERATION_CODES = frozenset({"CAPABILITY_UNSUPPORTED", "VALIDATION_FAILED"})


def _peer_declares_drop_entity_supported(iso: ConformanceAdapter) -> bool:
    """Supervisor ruling 2026-09-06 (Phase 8 WP-1a follow-on): replaces
    `_operation_depth_enforced` (removed here), the WP-5 rework 2 proxy
    that keyed this file's own destructive-probe branch on `limit_
    enforcement.operation_depth == "enforced"` as a stand-in for "is this
    the `r2db-api` pair, the one that supports `drop_entity`". That proxy
    broke the moment it stopped being a proxy for anything: Phase 8 WP-1a
    made `MitateDB-api`/`MitateDB-api-http` also declare `operation_depth`
    `enforced`, so both took the `drop_entity()` branch below too, where
    `drop_entity` is `SurfaceAbsent` on `MitateDB-api` in-process (2 of
    this file's tests went red on a full `conformance-tests` run --
    `test_c04_error_details_carry_no_unsafe_diagnostic_content
    [MitateDB-api]`/`[MitateDB-api-http]`).

    This reads the ACTUALLY DECLARED capability instead: whether
    `drop_entity` -- one of the six schema operations `SchemaOperation
    Request.operation` names (`spec/data-service-api.v1.json:1042`) -- is
    an operation this peer really executes, per its own capability
    document's `capabilities.schema_operations` entry (a peer-published
    key inside `CapabilityDocument.capabilities`'s deliberately open
    shape, `spec/data-service-api.v1.json:218`'s own note on `operations`
    applies identically to its sibling `unsupported`).

    That entry publishes the vocabulary two ways, and only one is usable
    through `capability_document()`: `operations` (the executable subset)
    is gated on the CALLING session's own role -- `r2db_api/capabilities_document.py:
    31`'s `schema_ops = [...] if role == "developer" else []`,
    `mitatedb_api/capabilities_document.py:99`'s identical `is_developer` gate -- and
    every one of the four adapters' own `capability_document()` always
    probes with a `"runtime"`-role credential (measured by reading each:
    `conformance_adapter_r2db.py:590`, `conformance_adapter_r2db_http.py:
    2024`, `conformance_adapter_mitatedb.py:753`, `conformance_adapter_
    mitatedb_http.py` around its own `_capability_probe_session` cache),
    so `operations` reads back empty through this call on every plug and
    cannot distinguish anything. `unsupported` is NOT role-gated on
    either peer (same two source lines): it is a fixed list published
    regardless of who is asking, so it is the one reliable read available
    here. r2db-api's own `unsupported` (`r2db_api/capabilities_document.py:62`) is
    `["jobs"]` -- `drop_entity` absent, i.e. declared supported;
    MitateDB-api's own (`mitatedb_api/capabilities_document.py:99`) is `["create_
    index", "drop_index", "drop_entity", "jobs"]` -- `drop_entity`
    present, i.e. declared genuinely unsupported, matching the structural
    `SurfaceAbsent` fact this module's own header docstring already
    measured.

    Mirrors `test_c05_limit_declaration_agreement.py::_v3_cases`'s own
    per-plug (not cross-plug) non-vacuity discipline -- the `assert`
    below only proves THIS plug's own read is real (a present, non-`None`
    `unsupported` list), never that both branches are exercised across
    the whole file: that cross-plug fact does not survive `-n 5 --dist
    loadgroup` (each plug is its own `xdist_group`/worker, `conftest.py::
    pytest_collection_modifyitems`), so it is confirmed by running this
    module and reading which adapter took which branch, not by an
    in-process aggregate."""
    schema_operations = iso.capability_document().get("capabilities", {}).get("schema_operations", {})
    unsupported = schema_operations.get("unsupported")
    assert unsupported is not None, (
        f"{iso.name}: capability_document()['capabilities']['schema_operations'] carries no 'unsupported' "
        "key to read -- this branch condition needs a real, peer-published vocabulary, not a silent default"
    )
    return "drop_entity" not in unsupported


def test_c04_operation_outside_the_mutation_vocabulary_is_refused_before_execution(
    adapter: ConformanceAdapter, isolated
) -> None:
    iso = isolated
    developer, runtime, _app_id = provision_pair(iso, app_prefix="c04unsup")
    entity = fresh_identifier("c04unsup")
    iso.create_entity(developer, entity, {"label": "text"})
    count_before = iso.count(runtime, entity)

    bogus_operation = fresh_identifier("c04_not_a_real_operation")
    with pytest.raises(ConformanceDenial) as ei:
        iso.attempt_mutation(
            runtime, entity, bogus_operation,
            values={"label": "x"}, where_field=None, where_value=None,
        )
    assert ei.value.code in load_contract_error_codes(), f"denial code {ei.value.code!r} is not a contract error code"
    assert ei.value.code in _ACCEPTED_UNSUPPORTED_OPERATION_CODES, (
        f"{adapter.name}: an operation name ({bogus_operation!r}) outside the mutation vocabulary was "
        f"refused with {ei.value.code!r}, expected one of {sorted(_ACCEPTED_UNSUPPORTED_OPERATION_CODES)!r}"
    )
    count_after = iso.count(runtime, entity)
    assert count_after == count_before, (
        f"{adapter.name}: row count changed ({count_before} -> {count_after}) despite an unsupported "
        "operation being refused -- the peer executed (at least partially) before refusing it"
    )
    # The denial itself must also be scanned (mutation 2's own target can
    # land on either probe in this file; a second, differently-shaped
    # probe here means the scan is exercised twice, not vacuously once).
    assert_no_unsafe_diagnostic_content(
        ei.value.code, adapter_name=adapter.name, context="unsupported-operation denial.code",
    )
    assert_no_unsafe_diagnostic_content(
        ei.value.details, adapter_name=adapter.name, context="unsupported-operation denial.details",
    )


def test_c04_error_details_carry_no_unsafe_diagnostic_content(adapter: ConformanceAdapter, isolated) -> None:
    iso = isolated
    developer, runtime, _app_id = provision_pair(iso, app_prefix="c04safe")
    entity = fresh_identifier("c04safe")
    iso.create_entity(developer, entity, {"label": "text"})

    if _peer_declares_drop_entity_supported(iso):
        # `drop_entity` -- flat, single-level request dict, safe under the
        # isolated profile's small operation_depth bound on this peer (see
        # this module's own docstring / conftest.provision_pair's).
        with pytest.raises(ConformanceDenial) as ei:
            iso.drop_entity(developer, entity, destructive=True, confirmation=None)
        assert ei.value.code == "DESTRUCTIVE_CONFIRMATION_REQUIRED", (
            f"{adapter.name}: expected DESTRUCTIVE_CONFIRMATION_REQUIRED from an unconfirmed destructive "
            f"drop_entity, got {ei.value.code!r}"
        )
        details = ei.value.details
        assert details, (
            f"{adapter.name}: expected a non-empty details mapping on a DESTRUCTIVE_CONFIRMATION_REQUIRED "
            "denial (this test's own non-vacuity requirement)"
        )
        assert_no_unsafe_diagnostic_content(
            details, adapter_name=adapter.name, context="DESTRUCTIVE_CONFIRMATION_REQUIRED denial.details",
        )
        # The entity is untouched -- a rejected destructive request must
        # not execute (SI-09).
        assert entity in set(iso.entities(developer)), (
            f"{adapter.name}: {entity!r} disappeared despite the destructive drop_entity being refused"
        )
        return

    # `MitateDB-api`/`MitateDB-api-http`: `drop_entity` is declared
    # unsupported (structurally `SurfaceAbsent` in-process), so `delete()`
    # is the probe -- its request shape stays within the isolated
    # profile's `operation_depth` bound on this peer regardless of that
    # peer's own `operation_depth` enforcement status (see this module's
    # own header docstring / `_peer_declares_drop_entity_supported`'s).
    iso.attempt_mutation(
        runtime, entity, "insert", values={"label": "seed"}, where_field=None, where_value=None,
    )
    with pytest.raises(ConformanceDenial) as ei:
        iso.delete(runtime, entity, "label", "seed", destructive=True, confirmation=None)
    assert ei.value.code == "DESTRUCTIVE_CONFIRMATION_REQUIRED", (
        f"{adapter.name}: expected DESTRUCTIVE_CONFIRMATION_REQUIRED from an unconfirmed destructive "
        f"delete, got {ei.value.code!r}"
    )
    details = ei.value.details
    assert details, (
        f"{adapter.name}: expected a non-empty details mapping on a DESTRUCTIVE_CONFIRMATION_REQUIRED "
        "denial (this test's own non-vacuity requirement)"
    )
    assert_no_unsafe_diagnostic_content(
        details, adapter_name=adapter.name, context="DESTRUCTIVE_CONFIRMATION_REQUIRED denial.details",
    )
    rows = iso.select_eq(runtime, entity, ["label"], "label", "seed")
    assert rows, f"{adapter.name}: seeded row disappeared despite the destructive delete being refused"
