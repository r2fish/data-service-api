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
     pair instead; `MitateDB-api`/`MitateDB-api-http` do not enforce
     `operation_depth` at all, so `delete()` is safe (and used) there --
     `drop_entity` is `SurfaceAbsent` specifically on `MitateDB-api`
     in-process, which would need its own extra absence-handling for no
     benefit, since `delete()` already works cleanly on both MitateDB
     plugs.

     **Branch condition, WP-5 rework (review finding 3)**: this choice is
     driven by the SAME declared, observable property the paragraph above
     already reasons from -- `limit_enforcement.operation_depth ==
     "enforced"` in the plug's own `capability_document()` -- never by the
     plug's own name. `r2db-api`/`r2db-api-http` are the only two
     currently-registered plugs that declare `operation_depth` enforced,
     which is exactly why they are the ones that need the flat
     `drop_entity()` probe instead of the deeper `delete()` one; this is
     the same correspondence `test_c05_limit_declaration_agreement.py::
     _drive_operation_depth` already asserts, read here rather than
     re-derived. A future plug is routed correctly by what it declares,
     not by whether its name happens to start with `"r2db-api"`.

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


def _operation_depth_enforced(iso: ConformanceAdapter) -> bool:
    """WP-5 rework (review finding 3): the declared, observable property
    this file's own destructive-probe branch is keyed on, replacing the
    earlier `adapter.name.startswith("r2db-api")` check. Mirrors
    `test_c05_limit_declaration_agreement.py::_drive_operation_depth`'s
    own read of the identical field."""
    return iso.capability_document().get("limit_enforcement", {}).get("operation_depth") == "enforced"


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

    if _operation_depth_enforced(iso):
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

    # `MitateDB-api`/`MitateDB-api-http`: `delete()` (no operation_depth
    # enforcement on either plug, so no depth pitfall here).
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
