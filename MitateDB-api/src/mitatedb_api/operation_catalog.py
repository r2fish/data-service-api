"""Design docs/design/PHASE11_MIN_COMMON_PROFILE_V1.md D-5: loads this
package's own byte-identical packaged copy of the derived operation
catalog (`mitatedb_api/contract/OPERATION_CATALOG.json`, wired in as
package data in `pyproject.toml`, mirroring `http.py`'s identical
loading discipline for `contract/data-service-api.v1.json`) -- the SAME
source `http.py::get_operation_catalog` serves at `GET /v1/operation-
catalog` and the in-process conformance adapter's port v1.17
`operation_catalog_document()` returns, so C-29's own byte-identity check
never has a re-encoding step of this peer's own to drift from `tools/
contract_catalog.py`'s generated file.

Read once, as raw BYTES -- never re-serialized through `json.dumps` --
so a whitespace/key-order difference introduced by a re-encode can never
silently pass the byte-for-byte comparison this condition performs.
"""
from __future__ import annotations

import json
from importlib import resources

_PACKAGED_OPERATION_CATALOG_PATH = "OPERATION_CATALOG.json"
_PACKAGED_CONTRACT_PATH = "data-service-api.v1.json"


def load_operation_catalog_bytes() -> bytes:
    return resources.files("mitatedb_api.contract").joinpath(_PACKAGED_OPERATION_CATALOG_PATH).read_bytes()


def operation_catalog_endpoint_path() -> str:
    """The contract's own `endpoints.operation_catalog.path` -- read from
    the packaged contract JSON, never a literal, so a deployment-side
    default URL derives the SAME path this repository's contract
    actually declares."""
    text = resources.files("mitatedb_api.contract").joinpath(_PACKAGED_CONTRACT_PATH).read_text()
    contract = json.loads(text)
    return contract["endpoints"]["operation_catalog"]["path"]


def derive_operation_catalog_url(data_base_url: str) -> str:
    """The ONE derivation both the data-plane and control-plane
    composition roots call for their own `operation_catalog_url` default
    (env var unset). A plain `data_base_url + operation_catalog_
    endpoint_path()` concatenation doubles the contract's own
    `versioning.base_path` (`/v1`), since `data_base_url` already ends
    with it and `endpoints.operation_catalog.path` already starts with
    it, producing `.../v1/v1/operation-catalog` -- a 404 -- so this
    function strips that shared prefix before joining the two instead.

    Reads `versioning.base_path` and `endpoints.operation_catalog.path`
    from the SAME packaged contract JSON `operation_catalog_endpoint_
    path()` reads, asserts `path` starts with `base_path` and `data_
    base_url` ends with `base_path`, then returns `data_base_url + path[
    len(base_path):]` -- `data_base_url` with its trailing `base_path`
    replaced by the full `path`, i.e. BASE-RELATIVE to `data_base_url`
    itself (never merely `data_base_url`'s origin plus `path`: a `data_
    base_url` carrying a reverse-proxy prefix ahead of `base_path`, e.g.
    `https://host.example.invalid/api/v1`, keeps that prefix in the
    result -- reachable behind the SAME prefix a client already reaches
    `data_base_url` through)."""
    text = resources.files("mitatedb_api.contract").joinpath(_PACKAGED_CONTRACT_PATH).read_text()
    contract = json.loads(text)
    base_path = contract["versioning"]["base_path"]
    path = contract["endpoints"]["operation_catalog"]["path"]
    assert path.startswith(base_path), (
        f"contract endpoints.operation_catalog.path {path!r} does not start with versioning.base_path {base_path!r}"
    )
    assert data_base_url.endswith(base_path), (
        f"surfaces.data.base_url {data_base_url!r} does not end with versioning.base_path {base_path!r}"
    )
    return data_base_url + path[len(base_path):]
