"""C-10 -- application clients cannot obtain DB credentials, private
management authority, or bypass-enabling configuration (SI-12).

design: docs/design/PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md
D-6.7, registered in `conformance-tests/CONDITIONS.md`. Every test here
carries `@pytest.mark.condition("C-10")` via the module-level `pytestmark`.

**Scope, stated plainly (design D-6.7 / L7-7)**: this condition is
exercised at the **adapter boundary**, never "the wire" -- two of the four
currently-registered adapters (`r2db-api`, `MitateDB-api`) are in-process
and have no wire to inspect at all, so a wire-level check could never be
applied uniformly. "Adapter boundary" means: every value a real port
operation call actually returns to its caller (or, on a denial, the
`ConformanceDenial`'s own `code`/`details`) is JSON-serialized and scanned
for credential-bearing/DSN-shaped/bypass-configuration-shaped substrings
by `conftest.ScanningAdapterProxy` (the shared "generic proxy" fixture
mechanism this WP places in `conftest.py`, per design's own instruction --
`conformance-tests/adapter.py` itself gains no new port method for C-10.
WP-5 rework, review finding 7: this file previously claimed the port's
own line count was unchanged, which is false in this same working tree --
`adapter.py` does carry a real diff, but it is entirely the unrelated
§21.4 `limits_override`/`IsolatedControlHandle` addendum this WP's
supervisor ruling separately authorized for C-14's own vector, not
anything C-10 added). The scope is exactly "what THIS
worker's own calls observed" -- under `-n 5 --dist loadgroup`, each plug is
its own xdist group/worker, so there is no session-wide aggregation across
plugs, and none is claimed here. PG-role-level evidence that the platform
database itself never hands out a superuser/bypass role to an application
credential is `security/CONTROL_MAPPING.md`'s own peer-local SI-12 row,
referenced, never duplicated here (this suite has no way to inspect GRANTs
from outside a real connection at all).

Both currently-registered PAIRS take the SAME shape here: `r2db-api`/
`r2db-api-http` and `MitateDB-api`/`MitateDB-api-http` are driven through
an identical sequence of ordinary port operations plus one deliberately
erroneous one, all via the scanning proxy -- the proxy raises immediately
(as an `AssertionError`, distinct from a`pytest.raises(ConformanceDenial)`
failure) the moment any call it wraps returns or denies with unsafe
content, so a passing run for a given plug is that plug's own genuine
non-vacuous negative evidence (`scanned_calls` is asserted `>= 1` per plug,
this file's own per-plug non-vacuity requirement, design principle 4 /
this repository's "空振り禁止" discipline).

Uses `conftest.isolated`/`provision_pair` (port v1.11's own `isolated_
application_surface()`, C-05's primitive) rather than the ordinary `fx`
fixture: this condition needs one ordinary, working application, and `fx`
used per test with no teardown permanently grows the session-scoped
adapter's own `applications` registry (measured, WP-5) -- see `conftest.
isolated`'s own docstring for the full, four-round measurement history.
No call in this file uses a `where` filter, so none trips the isolated
profile's own small `operation_depth` bound (see `conftest.provision_
pair`'s own docstring for the pitfall this avoids). The scanning proxy
wraps the ISOLATED instance directly, so every provisioning/teardown call
this test makes is scanned too, not only the "ordinary traffic" calls.
"""
from __future__ import annotations

import pytest

from adapter import BatchOperation, ConformanceAdapter, ConformanceDenial, fresh_identifier
from conftest import ScanningAdapterProxy, provision_pair

pytestmark = pytest.mark.condition("C-10")


def _control_plane_status(adapter: ConformanceAdapter) -> str:
    return adapter.capability_document().get("capabilities", {}).get("control_plane", {}).get("status", "unavailable")


def test_c10_no_bypass_material_appears_in_observed_responses(adapter: ConformanceAdapter, isolated) -> None:
    iso = isolated
    scanning = ScanningAdapterProxy(iso)
    developer, runtime, _app_id = provision_pair(scanning, app_prefix="c10")
    entity = fresh_identifier("c10")

    # Ordinary application-plane traffic, real success responses.
    scanning.capability_document()
    scanning.create_entity(developer, entity, {"label": "text"})
    scanning.insert(runtime, entity, {"label": "seed"})
    scanning.select_eq(runtime, entity, ["label"], "label", "seed")
    scanning.attempt_mutation(
        runtime, entity, "insert", values={"label": "second"}, where_field=None, where_value=None,
    )
    scanning.attempt_batch_with_addresses(
        runtime, entity, [BatchOperation(operation="insert", values={"label": "third"})],
    )
    scanning.catalog_document(developer)
    scanning.count(runtime, entity)
    scanning.entities(developer)

    # A real denial too -- code/details are scanned on the ConformanceDenial
    # branch, not only on a success return value.
    with pytest.raises(ConformanceDenial):
        scanning.attempt_mutation(
            runtime, entity, fresh_identifier("c10_bogus_operation"),
            values=None, where_field=None, where_value=None,
        )

    # Control-plane traffic: the PROVIDED branch for the 4 currently-
    # registered adapters (all declare `control_plane: enabled`), the
    # honest absence branch kept for a future peer that does not (design
    # principle 4 -- never skipped).
    if _control_plane_status(adapter) == "enabled":
        control_actor = scanning.control_credential()
        scanning.control_capabilities(control_actor)
        scanning.list_applications(control_actor)
        scanning.list_credentials(control_actor)
    else:
        with pytest.raises(ConformanceDenial):
            scanning.control_capabilities(iso.issue_credential(fresh_identifier("c10absent"), "runtime"))

    assert scanning.scanned_calls >= 8, (
        f"{adapter.name}: expected the scanning proxy to have observed several real calls, got "
        f"{scanning.scanned_calls} -- this test's own per-plug non-vacuity requirement"
    )
