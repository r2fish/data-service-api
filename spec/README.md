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

`CONTRACT_HISTORY.md` is the provenance companion for `data-service-api.v1.json`: every contract value carrying a provenance marker (a "Since 1.x.y", "subordinate ruling N", or similar phrase) gets a `## <json_path>` anchor there, naming that value's full text copied verbatim, the `CCR_DISPOSITION.md` subordinate ruling it refers to, and the contract version that introduced it. Anchors are JSON paths (e.g. `## versioning.version_binding`), not condition or ruling IDs, because that is the only identifier the contract JSON itself offers for a value. The contract JSON carries no reference key pointing at this companion — reaching it is one hop from this `spec/` directory, not one hop from inside the JSON itself, so an agent working from the contract alone should also check what else lives in `spec/`.

Contract 1.7.0 (subordinate ruling 12) moved the provenance-marker text itself out of 26 of those anchored values (`R-10 (B)`), leaving only the numbered decision they refer to inside the contract body; `CONTRACT_HISTORY_MANIFEST.json` records, per `json_path`, exactly what was removed (`stripped_prefix` / `stripped_insert`, plus a single word-level `rewrite`) so that applying it in reverse to the live contract value reconstructs `CONTRACT_HISTORY.md`'s own quote for that path byte-for-byte. Three values could not be mechanically separated this way (`unstripped: true` in the manifest, with a `reason`) and still carry the marker inline in the contract body.

Contract 1.8.0 (subordinate ruling 13) adds no new `## <json_path>` anchor: its 4 marker-free contract values carry no provenance marker of their own (deliberately, continuing R-10 (B)'s direction of keeping the contract body free of provenance text). Their provenance, and 1.8.0's own monitor-finalized anchor sentence, are instead recorded in the existing `## versioning.version_binding` section's "Revision note" -- the same anchor that already covers subordinate ruling 13's own 4th 1.8.0 piece of prose in that section's quote -- so the `## <json_path>` scanner/heading agreement the paragraph above describes is unaffected: 1.8.0 adds no heading and no exception to it. Those 4 are `capability_status.rules`' new array element, the sentence appended to `limits.profile`, `versioning.obligations`' 1.8.0 entry, and — added by 1.8.0's own pre-publication addendum (supervisor ruling U-9, 2026-09-08; "Revision note 2" in the same section) — the sentence pair appended to `structured_operations.idempotency.record`, which likewise gains no anchor of its own.

Contract 1.9.0 (subordinate ruling 14) likewise adds no new `## <json_path>` anchor: its 6 marker-free contract values carry no provenance marker of their own. Their provenance is instead recorded in the existing `## versioning.version_binding` section's "Revision note 3" -- the same anchor that already covers subordinate ruling 14's own 1.9.0 piece of prose in that section's quote -- so the `## <json_path>` scanner/heading agreement the paragraph above describes is unaffected: 1.9.0 adds no heading and no exception to it. Those 6 are the new top-level `common_baseline` section, `capability_status.rules`' new array element, `versioning.obligations`' 1.9.0 entry, `endpoints.operation_catalog`, `schemas.OperationCatalogDocument` and `definitions.OperationCatalogEntry`.

`OPERATION_CATALOG.json` is a derived, machine-generated artifact: `tools/contract_catalog.py` projects `data-service-api.v1.json`'s `endpoints`/`control_endpoints` entries into one `{name, method, path, roles, requires_capability, atomicity, destructive, request_schema, response_schema}` record apiece, reading structure only (never interpreting prose). It is non-authoritative — the contract JSON remains the source of truth — and is regenerated deterministically; `conformance-tests/test_operation_catalog_register.py` asserts the checked-in file still matches a fresh run of the generator.

Do not treat deployment-specific paths, proxies, database connection mechanics,
or cloud-provider products as part of the common API contract.

The JSON artifact is a contract document rather than a JSON Schema for one
request body: endpoint payload schemas are named under `schemas`, and each
implementation must expose equivalent semantics through its adapter.
