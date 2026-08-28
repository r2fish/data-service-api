# r2db-api

VPS / PostgreSQL implementation of the common `data-service-api` contract.

## Current source

The previously deployed implementation is retained separately as the
旧r2db-api実装 and is not modified by this repository work.

Migration of the previous implementation is intentionally not implicit;
production cutover remains an explicit development task.

## Contract rule

Public behavior should conform to `../spec/` and `../conformance-tests/`. VPS-specific nginx, systemd, filesystem paths, local PostgreSQL provisioning, and operational details remain implementation-local.

## Foundation

`src/r2db_api` models server-bound credentials, application-scoped
structured operations, finite limits, canonical audit events, and the
authority topology. `config/authority-topology.yaml` is a deployment
skeleton: production evidence for identity, network, database grants, and
an external append-only audit sink remains required.

This is still not a production deployment. What has changed since the
initial in-memory foundation is described below; `security/CONTROL_MAPPING.md`
is the authoritative row-by-row account of what is local/test evidence
versus what remains unevidenced.

### What now exists

- **`StorageBackend` protocol** (`src/r2db_api/backend.py`) names the exact
  call surface `DataService` uses per application (`query`, `transact`,
  `apply_schema`, `catalog`). `structured.py` is the shared
  validation/planning layer both backends cross -- identifier syntax, the
  operator allowlist, mutation shape, and destructive-confirmation logic
  live there once, not duplicated per backend.
- **`PostgresCell`** (`src/r2db_api/postgres.py`), a `StorageBackend` over
  PostgreSQL via psycopg 3. Values are always server-side bind parameters;
  identifiers are composed only via `psycopg.sql.Identifier`, after both the
  shared syntax allowlist and a second check against the schema's live
  `information_schema` catalog; `_run` is the single execution choke point
  and is typed to reject anything but a composed `psycopg.sql` object, so no
  method anywhere in the file can execute a raw string. One HTTP request
  maps to one real PostgreSQL transaction (design D-5).
- **An ASGI HTTP layer** (`src/r2db_api/http.py`, Starlette) implementing the
  contract's endpoints (`/v1/capabilities`, `/v1/data/{entity}/query`,
  `/v1/data/{entity}/mutations`, `/v1/catalog`, `/v1/schema/operations`,
  `/v1/audit/query`). The request-byte bound (SI-08) is enforced in the ASGI
  `receive` loop, measured from actual bytes received, before Starlette's
  body parser or routing ever runs. `spec/data-service-api.v1.json` is
  loaded at import time as the single source of request shapes; a
  byte-identical packaged copy ships with the distribution so a checkout
  without the sibling `spec/` tree still imports.
- **`migrations/`** (`0001_bootstrap_control_plane.sql`,
  `0002_provisioning_functions.sql`): schema-per-application, two dedicated
  PostgreSQL roles per application (`runtime`: DML only; `developer`: DDL
  within its own schema only), and row-level security as a defence-in-depth
  layer under both. A separately-bootstrapped control role
  (`NOSUPERUSER`/`NOCREATEDB`) performs provisioning; the API process never
  holds that credential. `docs/POSTGRES_PROVISIONING_RUNBOOK.md` is the
  operator runbook. Provisioning is always run by an operator against a
  real PostgreSQL server -- **never by the API process** -- and always
  targets a footprint namespaced separately from the existing VPS
  deployment.
- **`DataService.catalog()`** and an optional per-operation `request_id`
  threaded through service calls, so a single request's audit events
  correlate.
- **A third conformance adapter, `r2db-api-http`**
  (`conformance/conformance_adapter_r2db_http.py`), running
  C-01/C-03/C-08/C-11/C-12/C-17/C-18 over this real HTTP+PostgreSQL stack
  rather than in-process. See `docs/design/CONFORMANCE_ADAPTER_V1.md` and
  `conformance-tests/CONDITIONS.md`.
- **CCR-13 storage layer** (`docs/design/R2DB_CCR13_STORAGE_V1.md`): typed
  columns (`add_field`'s `field_type`, native `bigint`/`double precision`/
  `boolean`/`text` columns plus DOMAIN-typed `object`/`array`), server-
  assigned row addresses (`id`) with a never-reused-within-lifetime
  guarantee, declared domain uniqueness (`create_index`/`drop_index`),
  `upsert` resolving against a declared unique key, per-row optimistic-
  concurrency `expected_revision` preconditions, `order_by`, and cursor
  pagination -- all implemented on both `ApplicationCell` and
  `PostgresCell` and declared through `capabilities()`
  (`structured_query`/`atomic_mutation`/`schema_operations`/
  `row_addressability`/`revision_preconditions` all `enabled` or
  `partial` as appropriate, no longer `unavailable`). Conditions C-17
  (declaration/addressability/uniqueness agreement) and C-18 (revision-
  precondition semantics) are executable across all three conformance
  adapters.

All of the above has been exercised against a real local PostgreSQL 16
server (`r2db-api/tests/test_postgres.py`, `test_http.py`, and the
`r2db-api-http` conformance adapter) -- not against a mocked or simulated
database. That is local/test-cluster evidence, not production evidence.
**PostgreSQL provisioning has not been performed on the VPS**; the
migrations exist in this repository but have not been run there, and no
production identity/network/database-grant evidence exists yet
(`security/CONTROL_MAPPING.md` records this per invariant).

### What remains reference-only or unimplemented

- The in-memory `ApplicationCell`/`InMemoryCell` path remains a
  `StorageBackend` implementation, kept and tested as a test double rather
  than removed.
- The connection pool (`postgres.py`'s `_RolePool`) is hand-rolled, not
  `psycopg_pool`.
- The audit sink failure policy (`spec/data-service-api.v1.json`
  `audit.sink_failure_policy`: durable, fail-closed recording for
  authentication/authorization denials, credential/Application lifecycle
  changes, destructive/privilege-sensitive operations, and security-control
  failures; bounded-buffer-plus-alert for ordinary data-operation events) is
  stated by the contract but not yet enforced against a real external sink.
  `AuditSink` (`src/r2db_api/audit.py`) is still a single in-process,
  append-only list with no durability boundary to fail against -- there is
  no bounded buffer, no alerting path, and no fail-closed enforcement tied
  to sink failure. A production deployment must add both the external sink
  and the policy's enforcement.
- Long-running schema evolution jobs are not implemented by this
  synchronous foundation. A future job capability must define finite
  execution/queue bounds, observable state transitions, cancellation,
  expiry, and rollback semantics before it is advertised.
- `/v1/audit/query` authenticates the caller but always fails with
  `CAPABILITY_UNSUPPORTED`: this foundation has no separately-authenticated
  control/audit credential type, and `DataService`'s public facade
  deliberately exposes no audit accessor for any application credential to
  reach.

Application-facing code intentionally has no SQL/native-command execution
surface and no access to Control or Provisioning authorities.
