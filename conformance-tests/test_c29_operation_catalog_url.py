"""C-29 -- the derived operation catalog a peer names in
`operation_catalog_url` is the contract's own: the document served at that
URL is byte-identical to the derived operation catalog this repository's
spec generates, whose own `contract_version` equals the version the same
capability document declares, so a client that read the URL and a client
that read the specification hold the same index (SI-10).

design: docs/design/PHASE11_MIN_COMMON_PROFILE_V1.md D-5, §6.4 (C-29 行の
最終形), §6.6 (`schemas.OperationCatalogDocument`/`definitions.
OperationCatalogEntry`), §7.1 item 2 (port v1.17), §8.2 (SI 列), §11
(honest scope). Work order: docs/work-orders/
WORK_ORDER_PHASE11_MIN_COMMON_PROFILE_V1.md WP-3. Every test here carries
`@pytest.mark.condition("C-29")` via the module-level `pytestmark`.

**Two stages** (design §6.4/§7.1 item 2):

  (i)  On all SIX plugs, the body the peer itself returns for its own
       `operation_catalog` operation (port v1.17 `operation_catalog_
       document()`) is compared byte-for-byte against the packaged
       derived catalog for the declared contract version, and the parsed
       body is validated against `schemas.OperationCatalogDocument` with
       `conformance-tests/schema_check.py`.
  (ii) On plugs whose `transport_kind` is `socket`, the declared
       `operation_catalog_url` is dialled for real (a brand new httpx
       client, never the adapter's own internal one -- mirrors C-19's own
       `test_c19_surfaces_are_really_dialable_on_socket_plugs`) and
       yields the same body.

**Honest limits** (design §6.4/§11): on the four in-process plugs the
declared `operation_catalog_url` is a synthetic, non-dialled placeholder;
the URL is NOT required to sit under `surfaces.data.base_url` (D-5); and
this file's own byte comparison, not C-11's response-schema reverse-
validation, is what holds the served document to the contract (C-11's own
hand-written schema enumeration does not include `OperationCatalogDocument`
-- design §6.6/§11).
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from adapter import ConformanceAdapter, fresh_identifier, load_contract
from conftest import registered_adapters
from schema_check import assert_valid

pytestmark = pytest.mark.condition("C-29")

ROOT = Path(__file__).parents[1]
# Phase 11 WP-3 (design D-5): the packaged, byte-identical copy -- same
# artifact `test_operation_catalog_register.py::
# test_operation_catalog_packaged_copies_are_byte_identical` pins the two
# peer copies against. Read once, as raw bytes (never re-serialized), so
# this test's own comparison has no re-encoding step of its own to drift
# from either side.
_PACKAGED_CATALOG_BYTES = (ROOT / "spec" / "OPERATION_CATALOG.json").read_bytes()

_SOCKET_ADAPTER_NAMES: tuple[str, ...] = tuple(
    name for name, obj in registered_adapters().items() if getattr(obj, "transport_kind", None) == "socket"
)
# non-vacuity guard (work order completion condition 3: "(ii) の socket 段
# が 1 plug 以上で実走する"): a pure read of the already-built registry, no
# real surface started to evaluate this -- mirrors test_c19_client_self_
# sufficiency.py's own identically-shaped guard immediately after its own
# `_SOCKET_ADAPTER_NAMES`.
assert _SOCKET_ADAPTER_NAMES, (
    "no registered adapter declares transport_kind == 'socket' -- registry.json must register at "
    "least one socket-transport plug for C-29's own stage (ii) to be non-vacuous"
)


def _probe_session(adapter: ConformanceAdapter):
    """A fresh, disposable runtime session -- solely to authenticate the
    `operation_catalog_document()`/real-dial calls below, never itself
    part of what this condition observes (mirrors C-19's own probe-
    application pattern)."""
    probe_app = fresh_identifier("c29probe")
    adapter.provision_application(probe_app)
    handle = adapter.issue_credential(probe_app, "runtime")
    return adapter.authenticate(handle)


def test_c29_served_body_matches_the_packaged_catalog(adapter: ConformanceAdapter) -> None:
    """Stage (i): all six plugs."""
    session = _probe_session(adapter)
    served_bytes = adapter.operation_catalog_document(session)
    assert served_bytes == _PACKAGED_CATALOG_BYTES, (
        f"{adapter.name}: operation_catalog_document() is not byte-identical to the packaged "
        f"spec/OPERATION_CATALOG.json ({len(served_bytes)} bytes served, "
        f"{len(_PACKAGED_CATALOG_BYTES)} bytes expected)"
    )

    parsed = json.loads(served_bytes)
    contract = load_contract()
    assert_valid(
        parsed, contract["schemas"]["OperationCatalogDocument"], contract,
        label=f"{adapter.name} operation_catalog_document()",
    )


def test_c29_declared_version_matches_the_served_catalog(adapter: ConformanceAdapter) -> None:
    """Design C-29 row's own second half: "whose own `contract_version`
    equals the version the same capability document declares." Checked
    against the SAME probe session's capability document, not a fresh
    one, so a peer that flipped mid-test cannot silently pass either
    check individually."""
    capdoc = adapter.capability_document()
    session = _probe_session(adapter)
    served_bytes = adapter.operation_catalog_document(session)
    served = json.loads(served_bytes)
    assert served["contract_version"] == capdoc.get("contract_version"), (
        f"{adapter.name}: operation_catalog_document()'s own contract_version "
        f"{served['contract_version']!r} does not match capability_document()'s "
        f"{capdoc.get('contract_version')!r}"
    )


def test_c29_data_and_control_planes_declare_the_same_url(adapter: ConformanceAdapter) -> None:
    """Work order WP-3 タスク 2 (design §7.1 訂正註「control plane の宣言
    版」item (5)): the control surface's own `CapabilityDocument` carries
    the SAME `operation_catalog_url` value the data surface's own document
    carries -- one deployer-set value, echoed on both planes (`surfaces`
    already does this for co-hosting; this is the SAME discipline applied
    to a value that names a data-surface operation).

    Every registered adapter declares a control surface (C-19 requires
    all six plugs to answer on the control plane too), so this never
    skips -- a peer that cannot produce a control credential here is a
    real failure, not a vacuous branch."""
    data_url = adapter.capability_document().get("operation_catalog_url")
    assert data_url, f"{adapter.name}: capability_document() carries no operation_catalog_url"
    control_handle = adapter.control_credential()
    control_doc = adapter.control_capabilities(control_handle)
    control_url = control_doc.get("operation_catalog_url")
    assert control_url == data_url, (
        f"{adapter.name}: control_capabilities() operation_catalog_url {control_url!r} "
        f"does not match capability_document() operation_catalog_url {data_url!r}"
    )


@pytest.mark.parametrize("adapter_name", _SOCKET_ADAPTER_NAMES)
def test_c29_operation_catalog_url_is_really_dialable_on_socket_plugs(adapter_name: str) -> None:
    """Stage (ii): a real dial against the declared `operation_catalog_url`
    (a brand new httpx client, never the adapter's own internal
    transport) yields the same body `operation_catalog_document()`
    already returned in-process -- mirrors `test_c19_client_self_
    sufficiency.py::test_c19_surfaces_are_really_dialable_on_socket_plugs`.

    The judgement is `adapter.transport_kind == "socket"`
    (`_SOCKET_ADAPTER_NAMES`, computed from the live registry), never a
    name suffix or URL shape guess (`OPERATING_CONDITIONS.md` section 1.7
    item 52)."""
    adapter = registered_adapters()[adapter_name]
    capdoc = adapter.capability_document()
    declared_url = capdoc.get("operation_catalog_url")
    assert declared_url, f"{adapter.name}: capability_document() carries no operation_catalog_url"

    session = _probe_session(adapter)
    in_process_bytes = adapter.operation_catalog_document(session)

    probe_app = fresh_identifier("c29dial")
    adapter.provision_application(probe_app)
    handle = adapter.issue_credential(probe_app, "runtime")
    with httpx.Client(timeout=10.0) as client:
        response = client.get(declared_url, headers={"authorization": f"Bearer {handle.secret}"})
    assert response.status_code == 200, (
        f"{adapter.name}: real dial against declared operation_catalog_url {declared_url!r} "
        f"returned status {response.status_code} (body: {response.text!r})"
    )
    assert response.content == in_process_bytes, (
        f"{adapter.name}: real dial against {declared_url!r} returned a body that does not match "
        "the in-process operation_catalog_document() result"
    )
    assert response.content == _PACKAGED_CATALOG_BYTES, (
        f"{adapter.name}: real dial against {declared_url!r} does not match the packaged "
        "spec/OPERATION_CATALOG.json"
    )
