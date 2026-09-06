# Common Data Service API Specification

This directory is the authoritative, platform-independent contract shared by `r2db-api` and `MitateDB-api`.

The target is that an AI agent can use either implementation from:

1. this API specification,
2. a base URL, and
3. an authorized API key.

`data-service-api.v1.json` is intentionally **not** an OpenAPI document. It is a
platform-independent semantic contract — the source of truth for both
implementations. An OpenAPI description of the HTTP surface may be derived from
it for tooling purposes, but any derived artifact is non-authoritative, and the
absence of OpenAPI structure here is a design decision, not a defect.

`data-service-api.v1.json` is the initial machine-readable contract. It covers endpoint semantics, request/response shapes, authentication roles, error codes, structured query/schema operations, finite resource limits, lifecycle, audit semantics, and versioning/compatibility rules. `CCR_DISPOSITION.md` records the formal disposition of CCR-01 through CCR-12.

`CONTRACT_HISTORY.md` is the provenance companion for `data-service-api.v1.json`: every contract value carrying a provenance marker (a "Since 1.x.y", "subordinate ruling N", or similar phrase) gets a `## <json_path>` anchor there, naming that value's full text copied verbatim (the provenance marker is embedded within it, not extracted from it), the `CCR_DISPOSITION.md` subordinate ruling it refers to, and the contract version that introduced it. Anchors are JSON paths (e.g. `## versioning.version_binding`), not condition or ruling IDs, because that is the only identifier the contract JSON itself offers for a value. The contract JSON carries no reference key pointing at this companion — reaching it is one hop from this `spec/` directory, not one hop from inside the JSON itself, so an agent working from the contract alone should also check what else lives in `spec/`.

Do not treat deployment-specific paths, proxies, database connection mechanics,
or cloud-provider products as part of the common API contract.

The JSON artifact is a contract document rather than a JSON Schema for one
request body: endpoint payload schemas are named under `schemas`, and each
implementation must expose equivalent semantics through its adapter.
