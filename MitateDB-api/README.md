# MitateDB-api

Google Cloud implementation of the common `data-service-api` contract.

Target runtime:

- API runtime: Google Cloud Run
- Database: Cloud SQL for PostgreSQL

MitateDB-api is not a Mitate-specific API variant. It is the Google Cloud implementation of the same public Data Service API used by r2db-api.

Public API semantics and security guarantees are defined by `../spec/`; implementation-independent acceptance is defined by `../conformance-tests/`.

Google Cloud deployment, Cloud SQL connectivity, secrets, provisioning, scaling, and operations belong here and must not leak into the common public contract.
