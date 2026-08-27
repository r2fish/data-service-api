# Common Data Service API Specification

This directory is the authoritative, platform-independent contract shared by `r2db-api` and `MitateDB-api`.

The target is that an AI agent can use either implementation from:

1. this API specification,
2. a base URL, and
3. an authorized API key.

`data-service-api.v1.json` is the initial machine-readable contract. It covers endpoint semantics, request/response shapes, authentication roles, error codes, structured query/schema operations, finite resource limits, lifecycle, audit semantics, and versioning/compatibility rules. `CCR_DISPOSITION.md` records the formal disposition of CCR-01 through CCR-12.

Do not treat deployment-specific paths, proxies, database connection mechanics,
or cloud-provider products as part of the common API contract.

The JSON artifact is a contract document rather than a JSON Schema for one
request body: endpoint payload schemas are named under `schemas`, and each
implementation must expose equivalent semantics through its adapter.
