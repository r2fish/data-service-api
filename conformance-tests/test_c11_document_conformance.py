"""C-11 -- discovery/catalog document conformance (SI-08, SI-15).

design: docs/design/CONFORMANCE_CONDITIONS_V1_1.md section 3 (C-11). Every
test here carries @pytest.mark.condition("C-11") via the module-level
`pytestmark`, except the registry-wide vacuity guard at the bottom, which
is not adapter-parametrized (it iterates every registered adapter itself)
but still asserts the same condition.
"""
from __future__ import annotations

import pytest

from conftest import registered_adapters
from adapter import (
    CATALOG_SURFACE_ABSENT,
    UNCLASSIFIED,
    ConformanceDenial,
    Fixture,
    load_contract,
    load_contract_error_codes,
)
from schema_check import assert_valid

pytestmark = pytest.mark.condition("C-11")


def _unclassified_hint(code: str) -> str:
    if code != UNCLASSIFIED:
        return ""
    return (
        " -- code is adapter.UNCLASSIFIED: the peer raised a native "
        "exception the adapter could not map to a contract code. This is a "
        "finding under SI-05/SI-10, not a denial."
    )


def _assert_is_contract_code(code: str) -> None:
    contract_codes = load_contract_error_codes()
    assert code in contract_codes, f"denial code {code!r} is not a contract error code{_unclassified_hint(code)}"


# --- 1. capability document shape + vocabulary -------------------------


def test_capability_document_conforms_to_schema_and_vocabulary(adapter, fx: Fixture):
    contract = load_contract()
    schema = contract["schemas"]["CapabilityDocument"]
    document = adapter.capability_document()
    assert_valid(document, schema, contract, label=f"{adapter.name} capability_document()")

    defined = set(contract["capability_status"]["defined"])
    status_enum = set(contract["capability_status"]["status_enum"])
    enforcement_enum = set(contract["capability_status"]["enforcement_enum"])

    capabilities = document.get("capabilities", {})
    unknown = set(capabilities) - defined
    assert not unknown, f"{adapter.name}: declares capability name(s) not in capability_status.defined: {unknown}"

    for name, entry in capabilities.items():
        status = entry.get("status")
        assert status in status_enum, f"{adapter.name}: capability {name!r} has status {status!r} not in status_enum"

    for resource, level in document.get("limit_enforcement", {}).items():
        assert level in enforcement_enum, (
            f"{adapter.name}: limit_enforcement[{resource!r}] = {level!r} is not in enforcement_enum"
        )


# --- 2. catalog document: real shape, or an honest structural absence ----


def test_catalog_document_conforms_to_schema_or_is_honestly_absent(adapter, fx: Fixture):
    contract = load_contract()
    schema = contract["schemas"]["CatalogDocument"]
    capability_document = adapter.capability_document()
    catalog_status = capability_document.get("capabilities", {}).get("application_catalog", {}).get("status")

    try:
        document = adapter.catalog_document(fx.runtime_a)
    except ConformanceDenial as denial:
        _assert_is_contract_code(denial.code)
        assert denial.code == "CAPABILITY_UNSUPPORTED", (
            f"{adapter.name}: catalog_document() denial code {denial.code!r} is not "
            f"CAPABILITY_UNSUPPORTED{_unclassified_hint(denial.code)}"
        )
        # Only "unavailable" is consistent with a denial/absence: "partial"
        # declares *some* real, working catalog behavior, so a peer that
        # declares partial but has nothing to show here is self-
        # contradictory, not merely "not fully enabled" (review finding 6).
        assert catalog_status == "unavailable", (
            f"{adapter.name}: application_catalog is declared {catalog_status!r}, but catalog_document() "
            "was denied -- only status 'unavailable' is consistent with no catalog document at all"
        )
        return

    if document == CATALOG_SURFACE_ABSENT:
        assert catalog_status == "unavailable", (
            f"{adapter.name}: application_catalog is declared {catalog_status!r}, but catalog_document() "
            "reports CATALOG_SURFACE_ABSENT -- only status 'unavailable' is consistent with a structurally "
            "absent catalog surface"
        )
        return

    assert_valid(document, schema, contract, label=f"{adapter.name} catalog_document()")


# --- 3. registry-wide vacuity guard (not per-adapter-parametrized) --------


def test_at_least_one_adapter_returns_a_real_catalog_document():
    # design section 3: "positive control: 少なくとも1 adapter は文書を返す
    # -- registry 全体での vacuity 防止は suite 側で assert する". If every
    # registered adapter were allowed to claim CATALOG_SURFACE_ABSENT or a
    # denial, the schema check in test 2 above would be exercised on zero
    # real documents across the whole suite -- vacuously "passing" without
    # ever having validated a real CatalogDocument shape. This iterates the
    # live registry directly (not the parametrized `adapter` fixture) so it
    # runs exactly once regardless of how many adapters are registered.
    contract = load_contract()
    schema = contract["schemas"]["CatalogDocument"]
    saw_real_document = False
    for name, adapter_obj in registered_adapters().items():
        fx = adapter_obj.build_fixture()
        try:
            document = adapter_obj.catalog_document(fx.runtime_a)
        except ConformanceDenial:
            continue
        if document == CATALOG_SURFACE_ABSENT:
            continue
        assert_valid(document, schema, contract, label=f"{name} catalog_document()")
        saw_real_document = True
    assert saw_real_document, (
        "no registered adapter returned a real CatalogDocument; the schema check in "
        "test_catalog_document_conforms_to_schema_or_is_honestly_absent is vacuous across the whole registry"
    )
