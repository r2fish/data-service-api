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
skeleton: production evidence for identity, network and database grants
remains required. (The append-only audit sink itself is no longer pending --
both planes now have one, backed by PostgreSQL grants rather than by code
discipline; see the audit note further down and
`security/CONTROL_MAPPING.md`'s SI-14 row.)

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
  `0011_idempotency_records_upgrade.sql`, 11 files): `0001` control-plane
  bootstrap; `0002` provisioning-function helpers; `0003`/`0004`
  provision/deprovision one application -- schema-per-application
  (database-per-application, see the provisioning runbook §0), two
  dedicated PostgreSQL roles per application (`runtime`: DML only;
  `developer`: DDL within its own schema only), and row-level security as a
  defence-in-depth layer under both; `0005` credential store + read-only
  API role; `0006` control-plane HTTP surface storage --
  `control_credentials`/`control_audit` and the least-privilege
  `r2dbsvc_controlplane` role (see the control-plane bullet below); `0007`
  application-plane durable audit sink (phase 4, `application_audit`);
  `0008` platform-declarations table + audit-writer-role timeouts (Q4
  phase); `0009` retrofits the per-application platform-upgrade ledger onto
  an application provisioned before Q4 WP-3; `0010` adds the
  per-application field-constraints declaration registry (contract 1.7.0
  R-2); `0011` adds the per-application idempotency-record side table
  (contract 1.7.0 R-5). A separately-bootstrapped control role
  (`NOSUPERUSER`/`NOCREATEDB`) performs provisioning; the API process never
  holds that credential. `docs/POSTGRES_PROVISIONING_RUNBOOK.md` is the
  operator runbook. Provisioning is always run by an operator against a
  real PostgreSQL server -- **never by the API process** -- and always
  targets a footprint namespaced separately from the existing VPS
  deployment.
- **A control-plane HTTP surface, `/control/v1`** (CCR-14,
  `docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md`): 12 distinct control
  endpoints (`capabilities`, application register/list/enable/disable,
  credential issue/list/rotate/revoke/disable/enable, `audit_query`) --
  C-14's fail-closed authority boundary (`conformance-tests/CONDITIONS.md`)
  covers 11 of these, every one except `audit_query` --
  `src/r2db_api/control_http.py`'s route table has 13 `Route(...)` entries
  because `audit_query` is registered twice, at its canonical
  `/control/v1/audit/query` path and, for one further minor version, also
  at the `/v1/audit/query` alias (contract `endpoints.audit_query.
  deprecation_note`; same handler) -- served by a distinct ASGI app
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
  fact -- see `r2db-api/deploy/DEPLOYMENT_RUNBOOK.md` §7. `GET /v1/
  operation-catalog`'s declared URL (`R2DB_OPERATION_CATALOG_URL`,
  optional) is unset by default and derives from `surfaces.data.base_url`
  (base-relative, not merely its origin -- reachable behind the same
  reverse-proxy prefix `surfaces.data.base_url` itself carries) -- see
  that same runbook section for when to override it.
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
  mounted present-denial stub), never the PROVIDED branch MitateDB takes
  (MitateDB declares `cross_entity_mutation: partial` on both its
  adapters). C-14 (control-plane authority boundary) and C-15
  (bootstrap/reset lifecycle) run against a real `/control/v1` for this
  adapter and against a real, in-process `ControlPlaneService` for the
  plain `r2db-api` adapter. `MitateDB-api` implements its own `/control/v1`
  control-plane HTTP surface too (`MitateDB-api/src/mitatedb_api/control_http.py`)
  -- all four registered adapters (`r2db-api`, `r2db-api-http`,
  `MitateDB-api`, `MitateDB-api-http`) currently declare `control_plane:
  enabled` and take C-14's and C-15's PROVIDED branch for real, end-to-end;
  no peer is on the surface-absent branch for either condition. See
  `docs/design/CONFORMANCE_ADAPTER_V1.md`,
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
  precondition semantics) are executable across all four conformance
  adapters (`conformance-tests/CONDITIONS.md`).

All of the above has been exercised against a real local PostgreSQL 16
server (`r2db-api/tests/test_postgres.py`, `test_http.py`, and the
`r2db-api-http` conformance adapter) -- not against a mocked or simulated
database. That is local/test-cluster evidence, not production evidence.
**r2db Stage 1, contract 1.6.0, was installed on the VPS on 2026-09-05**:
migrations 0001, 0002, 0005, 0006, 0007 and 0003 were applied in that order (0004 is the deprovision script and is never applied at install), `pg_hba`/`pg_ident` posture B was
configured, and external reachability on port 8443 was verified
(`docs/work-orders/DEPLOY_PHASE6_20260904.md` §8, items 9-12). The
records do not show any later contract version having been deployed to
that VPS since -- `docs/work-orders/DEPLOY_Q4_20260905.md` is an
unexecuted procedure/template for a later application, not a completion
record (`security/CONTROL_MAPPING.md` records the acceptance-boundary
detail per invariant).

### What remains reference-only or unimplemented

- The in-memory `ApplicationCell`/`InMemoryCell` path remains a
  `StorageBackend` implementation, kept and tested as a test double rather
  than removed.
- The connection pool (`postgres.py`'s `_RolePool`) is hand-rolled, not
  `psycopg_pool`.
- ~~The audit sink failure policy ... is stated by the contract but not yet
  enforced against a real external sink.~~ **Closed, phase 4 WP-2(a)/WP-2(b)**
  (`docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md`): the application plane now
  has a durable sink, `r2dbsvc_registry.application_audit` (migration
  `0007`), and the policy is enforced against it. Fail-closed-class events
  (destructive operations through the confirmation choke, every schema
  operation, lifecycle events, security-control failures, and the six
  authentication/authorization denial codes) are written and committed on a
  separate platform connection **before** the data transaction commits, so a
  sink failure rolls the operation back and answers `SERVICE_UNAVAILABLE`;
  ordinary data-operation successes ride a bounded buffer (default 1000) that
  never discards silently -- an overflow emits a fixed-text `logging.error`
  and a durable `security_control_failure` row carrying the dropped count.
  `r2dbsvc_api` holds `INSERT` only on that table; a separate SELECT-only
  `r2dbsvc_auditreader` role is the only network reader. The in-process
  `AuditSink` (`src/r2db_api/audit.py`) still exists, but only as the record
  of denials the design deliberately keeps non-durable, not as the plane's
  only audit trail. Operational procedure (capacity thresholds, alerting,
  retention, reading evidence during an outage) is
  `docs/POSTGRES_PROVISIONING_RUNBOOK.md` §15; the evidence table is
  `security/CONTROL_MAPPING.md`'s SI-14 row.
- Long-running schema evolution jobs are not implemented by this
  synchronous foundation. A future job capability must define finite
  execution/queue bounds, observable state transitions, cancellation,
  expiry, and rollback semantics before it is advertised.
- `/v1/audit/query` **on the data-plane host** still authenticates the caller
  and then answers `CAPABILITY_UNSUPPORTED`, and the data plane still
  declares `audit_query: unavailable` -- deliberately, because that host does
  not provide the audit surface and says so truthfully. `DataService`'s
  public facade exposes no audit accessor for any *application* credential to
  reach, and never will.
  **Update, phase 4 WP-2(b): `audit_query` itself is implemented, on the
  control host.** `POST /control/v1/audit/query` (canonical, contract 1.4.0
  classifies it under `control_endpoints`) and `POST /v1/audit/query` (the
  same handler, kept as an alias for one further minor version) read the
  UNION of
  `control_audit` and `application_audit` as the SELECT-only
  `r2dbsvc_auditreader` role, in a total order of
  `(recorded_at, plane, event_id)`, paged with an opaque per-event cursor,
  withholding rows newer than a declared visibility lag that is DERIVED from
  the two audit-writer timeouts rather than asserted. `plane` is derived from
  the source table, not a column any writer can set. Authority is control or
  audit credentials only -- an application credential is `FORBIDDEN` -- and
  the `role="audit"` credential (phase 3.5) is now allowed `audit_query` in
  addition to its three read endpoints, so a distributable, read-only
  credential can read the audit trail itself, which was not previously
  reachable by any in-band path. Both paths are registered whether or not
  `R2DB_AUDIT_DSN` is configured; unset means an authenticated caller gets
  `CAPABILITY_UNSUPPORTED`, never a bare 404, and the capability stays
  declared `unavailable`. `audit_query` consumes its own
  `audit_requests_per_minute` window and never the control-plane one, so
  polling for evidence cannot lock out a break-glass `revoke_credential`. See
  `security/CONTROL_MAPPING.md`'s SI-02/SI-06/SI-08/SI-14 rows and
  `docs/POSTGRES_PROVISIONING_RUNBOOK.md` §15.

Application-facing code intentionally has no SQL/native-command execution
surface and no access to Control or Provisioning authorities.
