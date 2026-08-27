# MitateDB-api

Google Cloud implementation of the common `data-service-api` contract.

Target runtime:

- API runtime: Google Cloud Run
- Database: Cloud SQL for PostgreSQL

MitateDB-api is not a Mitate-specific API variant. It is the Google Cloud implementation of the same public Data Service API used by r2db-api.

Public API semantics and security guarantees are defined by `../spec/`; implementation-independent acceptance is defined by `../conformance-tests/`.

Google Cloud deployment, Cloud SQL connectivity, secrets, provisioning, scaling, and operations belong here and must not leak into the common public contract.

## Foundation status

The repository now contains an executable, contract-independent foundation in
`src/mitatedb_api/` with local tests in `tests/test_foundation.py`. Run it with:

```text
python3 -m unittest discover -s MitateDB-api/tests -v
```

This foundation demonstrates application-bound cells, server-bound
credentials, Runtime/Developer separation, structured parameter-bound data
operations, finite resource limits, explicit destructive semantics, atomic
rollback, local-path revocation fail-closed behavior, and secret-free local
audit evidence on the local API path. Production authority isolation,
Runtime/Developer database identity split, propagation bounds and an
externally governed append-only audit sink remain deployment work.
It does not define or replace the common HTTP API; that remains a follow-up
against `../spec/` led by the r2db-api workstream.
