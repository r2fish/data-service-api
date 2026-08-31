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
- **`migrations/`** (`0001_bootstrap_control_plane.sql` through
  `0006_control_plane_http.sql`): schema-per-application (database-per-
  application, see the provisioning runbook §0), two dedicated PostgreSQL
  roles per application (`runtime`: DML only; `developer`: DDL within its
  own schema only), and row-level security as a defence-in-depth layer
  under both. A separately-bootstrapped control role
  (`NOSUPERUSER`/`NOCREATEDB`) performs provisioning; the API process never
  holds that credential. `0006` additionally lays down the control-plane
  HTTP surface's own storage -- `control_credentials`/`control_audit` and
  the least-privilege `r2dbsvc_controlplane` role (see the control-plane
  bullet below). `docs/POSTGRES_PROVISIONING_RUNBOOK.md` is the operator
  runbook. Provisioning is always run by an operator against a real
  PostgreSQL server -- **never by the API process** -- and always targets a
  footprint namespaced separately from the existing VPS deployment.
- **A control-plane HTTP surface, `/control/v1`** (CCR-14,
  `docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md`): 11 endpoints
  (`capabilities`, application register/list/enable/disable, credential
  issue/list/rotate/revoke/disable/enable) served by a distinct ASGI app
  (`src/r2db_api/control_http.py`, assembled by `src/r2db_api/control_main.py`)
  with its own credential type (`role=control`, a dedicated verifier table
  and HMAC pepper -- structurally unable to coexist with an application
  credential in either direction), its own least-privilege DB role
  (`r2dbsvc_controlplane`), and its own durable audit sink
  (`control_audit`, contract `audit.fields`' full 13 columns as of contract
  1.3.0 (phase 3.5 WP-1 added `target_id`; populated at every emission site
  since WP-4), state changes and denials alike written in the same
  transaction as the change they describe). A `role=control` credential can only ever be created by an
  out-of-band operator ritual (`python -m r2db_api.ops bootstrap`/`reset`)
  -- there is no in-band issuance path anywhere, by design ("案B",
  `spec/CCR_DISPOSITION.md`); the ritual's first-issued credential is
  `must_rotate=true` until one real rotation completes. `python -m
  r2db_api.ops` itself is no longer a stand-in control surface -- it is now
  the bootstrap/reset ritual plus operator break-glass recovery for when
  `/control/v1` is unreachable (see `r2db-api/docs/
  CONTROL_PLANE_COMPROMISE_PLAYBOOK.md` for the compromise/misuse recovery
  procedure this CLI's `audit-report` subcommand supports). Whether a given
  deployment's application-plane process declares `control_plane: enabled`
  is a deployer decision (`R2DB_CONTROL_PLANE_STATUS`), not a detected
  fact -- see `r2db-api/deploy/DEPLOYMENT_RUNBOOK.md` §7.
- **`DataService.catalog()`** and an optional per-operation `request_id`
  threaded through service calls, so a single request's audit events
  correlate.
- **A third conformance adapter, `r2db-api-http`**
  (`conformance/conformance_adapter_r2db_http.py`), running
  C-01/C-03/C-06/C-08/C-11/C-12/C-14/C-15/C-16/C-17/C-18 over this real
  HTTP+PostgreSQL stack rather than in-process. **C-16 (phase 3.5 WP-3)**:
  this peer's own `cross_entity_mutation` stays `unavailable` (P35-D1, no
  real client demand on this peer) -- both r2db adapters take C-16's
  documented ABSENT branch (in-process = surface-absent, http = a real,
  mounted present-denial stub), never the PROVIDED branch MitateDB takes. C-14 (control-plane
  authority boundary) and C-15 (bootstrap/reset lifecycle) run against a
  real `/control/v1` for this adapter and against a real, in-process
  `ControlPlaneService` for the plain `r2db-api` adapter -- both currently
  take the PROVIDED branch (`control_plane: enabled`, exercised for real);
  `MitateDB-api` still takes the surface-absent branch (no equivalent
  surface exists yet -- next phase). See `docs/design/CONFORMANCE_ADAPTER_V1.md`,
  `docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md`, and
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
- `/v1/audit/query` (the data-plane, application-facing endpoint) still
  authenticates the caller but always fails with `CAPABILITY_UNSUPPORTED`:
  `audit_query` itself remains unimplemented (out of CCR-14's own scope --
  its endpoint/read-access shape is a separate, not-yet-designed decision),
  and `DataService`'s public facade deliberately exposes no audit accessor
  for any *application* credential to reach regardless. This is no longer
  because no control/audit credential type exists at all -- CCR-14 added a
  `role=control` credential type (above) -- but that type authenticates
  only against `/control/v1`, a different plane entirely; it is fail-closed
  against every `/v1` data/schema endpoint, `/v1/audit/query` included
  (condition C-14), and `/control/v1` itself has no audit-QUERY endpoint of
  its own either. **Update, phase 3.5 WP-1/WP-4**: a distributable, weaker
  `role="audit"` control credential now exists and can read `list_credentials`/
  `list_applications`/`control_capabilities` -- a read-only view of
  control-plane STATE (never a query over `control_audit` itself, which
  remains unread by any in-band path) -- see `security/CONTROL_MAPPING.md`'s
  SI-02/SI-06 rows.

Application-facing code intentionally has no SQL/native-command execution
surface and no access to Control or Provisioning authorities.
