# Common Data Service API Specification

This directory is the authoritative, platform-independent contract shared by `r2db-api` and `MitateDB-api`.

The target is that an AI agent can use either implementation from:

1. this API specification,
2. a base URL, and
3. an authorized API key.

The common contract will be extracted from the validated r2db-api behavior before MitateDB-api implementation expands it. It should cover at least endpoint semantics, request/response shapes, authentication roles, error codes, filtering/query semantics, structured schema operations, security invariants, and versioning/compatibility rules.

Do not treat current implementation details such as VPS paths, nginx, localhost PostgreSQL, Cloud Run, or Cloud SQL connection mechanics as part of the common API contract.

An authoritative machine-readable OpenAPI artifact should live here once extracted and validated; do not hand-invent a schema that is not supported by implementation/tests.
