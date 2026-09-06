"""C-02 -- runtime cannot execute schema/development or control operations
(SI-02, SI-03).

design: docs/design/PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md
D-6.7, registered in `conformance-tests/CONDITIONS.md`. Every test here
carries `@pytest.mark.condition("C-02")` via the module-level `pytestmark`.

This condition's own proposition ("Runtime cannot execute schema/
development or control operations") already touches ground two OTHER
conditions independently cover in part: `test_c01_scope_binding.py::
test_runtime_credential_cannot_self_elevate_to_schema_authority` (a single
`create_entity` probe) and `test_c14_authority_boundary.py::test_c14_
application_credentials_fail_closed_on_every_control_operation` (an
exhaustive 11-endpoint sweep, both roles). Per this WP's own禁止事項 7
("C-01/C-14/C-16 の既存 vector と同じ assert を二重に書かない"), this file
does not clone either of those -- it gives C-02 its OWN condition-tagged
evidence with genuinely different shape:

  1. **schema-operation denial WITH a same-request positive control**: the
     runtime credential is denied `create_entity`, and the identical
     request then succeeds for real under the developer credential in the
     SAME test -- a materially different assertion shape from C-01's own
     (which never runs a positive control in the same test), proving this
     is a real privilege boundary rather than a broken/absent capability.
  2. **one representative control-plane read, runtime-only**: `control_
     capabilities()` under a runtime credential. Deliberately a single
     endpoint, not a re-run of C-14's own 11-endpoint/2-role sweep -- this
     gives C-02 its own minimal, genuinely-executed evidence for the
     "control operations" half of its proposition without duplicating
     C-14's enumeration.

Uses `conftest.isolated`/`provision_pair` (port v1.11's own `isolated_
application_surface()`, C-05's primitive) rather than the ordinary `fx`
fixture: this condition needs one ordinary, working application, and `fx`
used per test with no teardown permanently grows the session-scoped
adapter's own `applications` registry (measured, WP-5) -- see `conftest.
isolated`'s own docstring for the full, four-round measurement history.
"""
from __future__ import annotations

import pytest

from absence import assert_control_operation_absent_or_uniformly_refused
from adapter import ConformanceAdapter, ConformanceDenial, fresh_identifier, load_contract_error_codes
from conftest import assert_runtime_credential_denied_schema_authority, provision_pair

pytestmark = pytest.mark.condition("C-02")

_CONTROL_PLANE_FORBIDDEN_VOCABULARY = ("credential", "control")


def _control_plane_status(adapter: ConformanceAdapter) -> str:
    return adapter.capability_document().get("capabilities", {}).get("control_plane", {}).get("status", "unavailable")


def _assert_is_contract_code(code: str) -> None:
    assert code in load_contract_error_codes(), f"denial code {code!r} is not a contract error code"


def test_c02_runtime_denied_create_entity_but_developer_succeeds_on_the_same_request(
    adapter: ConformanceAdapter, isolated
) -> None:
    iso = isolated
    developer, runtime, _app_id = provision_pair(iso, app_prefix="c02create")
    entity = fresh_identifier("c02schema")

    # WP-5 rework (review finding 10): the denial half is IDENTICAL to
    # `test_c01_scope_binding.py::test_runtime_credential_cannot_self_
    # elevate_to_schema_authority`'s own probe -- shared via `conftest.
    # assert_runtime_credential_denied_schema_authority` rather than kept
    # as two near-copies. This test's own, non-duplicated contribution is
    # the positive control immediately below, which C-01's own test never
    # runs.
    assert_runtime_credential_denied_schema_authority(
        iso, developer, runtime, entity, adapter_name=adapter.name,
    )

    # Positive control -- the SAME request, same entity name, succeeds for
    # real under the developer credential: this is a genuine privilege
    # boundary, not a broken/absent capability the runtime probe alone
    # could not distinguish.
    iso.create_entity(developer, entity, {"label": "text"})
    entities_after_developer = set(iso.entities(developer))
    assert entity in entities_after_developer, (
        f"{adapter.name}: developer's create_entity for {entity!r} did not take effect -- this test's own "
        "positive control would be vacuous"
    )


def test_c02_runtime_denied_on_control_capabilities_read(adapter: ConformanceAdapter, isolated) -> None:
    iso = isolated
    _developer, _runtime, app_id = provision_pair(iso, app_prefix="c02control")
    runtime_actor = iso.issue_credential(app_id, "runtime")

    if _control_plane_status(adapter) != "enabled":
        assert_control_operation_absent_or_uniformly_refused(
            iso,
            lambda: iso.control_capabilities(runtime_actor),
            required_forbidden_vocabulary=_CONTROL_PLANE_FORBIDDEN_VOCABULARY,
        )
        return

    with pytest.raises(ConformanceDenial) as ei:
        iso.control_capabilities(runtime_actor)
    _assert_is_contract_code(ei.value.code)
    assert ei.value.code != "CAPABILITY_UNSUPPORTED", (
        f"{adapter.name}: control_plane is declared 'enabled' but the runtime credential's control_"
        f"capabilities() read was refused with CAPABILITY_UNSUPPORTED rather than an authority-refusal code "
        f"-- this reads as the capability itself being absent, not the runtime credential being denied"
    )
