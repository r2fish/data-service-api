# MitateDB-api

Google Cloud implementation of the common `data-service-api` contract.

Target runtime:

- API runtime: Google Cloud Run (two services -- data plane and control
  plane -- built from one image, `docker/Dockerfile`)
- Database: Cloud SQL for PostgreSQL 16

MitateDB-api is not a Mitate-specific API variant. It is the Google Cloud
implementation of the same public Data Service API used by r2db-api.

Public API semantics and security guarantees are defined by `../spec/`;
implementation-independent acceptance is defined by `../conformance-tests/`.

Google Cloud deployment, Cloud SQL connectivity, secrets, provisioning,
scaling, and operations belong here and must not leak into the common
public contract.

## Status

Phase 3 (`docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md`) is complete:
the common contract's application-plane HTTP surface (`/v1/*`) and the
control plane (`/control/v1`, 11 endpoints + the out-of-band bootstrap/
reset ceremony) both run over real PostgreSQL persistence, and this peer
registers as **two** conformance adapters. `security/CONTROL_MAPPING.md`
is the authoritative row-by-row account of what is local/test evidence
versus what remains unevidenced (Cloud SQL/Cloud Run production platform
evidence is `absent` until an operator runs `docs/cloud-run-cloud-sql.md`
once).

Run the local test suite with:

```sh
cd MitateDB-api && ../.venv/bin/python -m pytest tests/ -q
```

(a real local PostgreSQL 16 server is required -- `host=/tmp port=5432` by
default, `MITATEDB_TEST_ADMIN_DSN` to override; these tests do not skip
when PostgreSQL is unreachable, they fail loudly).

### What exists

- **A backend seam** (`src/mitatedb_api/backend.py`, `cell.py`): request
  validation, capability declaration, error classification, and
  declare-and-echo confirmation-phrase construction live in one
  backend-independent layer; only execution differs per backend --
  `backend_sqlite.py` (a local, deterministic test double, never a
  deployment target) and `backend_postgres.py` (real PostgreSQL via
  psycopg 3, values always server-side bind parameters, identifiers
  composed only via `psycopg.sql.Identifier` after a two-stage check
  against a syntax allowlist and the target database's own live
  `information_schema` catalog, one execution choke point typed to reject
  any `str` statement).
- **`migrations/`** (`0001_bootstrap_platform.sql` through
  `0004_deprovision_application.sql`): a platform registry database
  (`applications`/`credentials`/`control_credentials`/`control_audit`) plus
  database-per-application provisioning -- one dedicated PostgreSQL
  database per application, two dedicated login roles (`runtime`: DML
  only; `developer`: DDL within its own database's `public` schema only),
  `REVOKE CONNECT ... FROM PUBLIC` so crossing to another application's
  database is not a SQL operation that exists at all, not merely a grant
  an implementation defect could omit. Every management statement drawn
  from a fixed, Cloud-SQL-compatible allowlist (no superuser-only feature
  anywhere) -- see `docs/cloud-run-cloud-sql.md` for the runbook and the
  real-instance verification procedure.
- **Application-plane HTTP** (`src/mitatedb_api/http.py`, Starlette): the
  contract's 7 endpoints. The request-byte bound (SI-08) is enforced in
  the ASGI `receive` loop, measured from actual bytes received, sized from
  the SAME `FoundationConfig.max_request_bytes` the capability document
  declares. `POST /v1/schema/operations` supports `create_entity`/
  `add_field`; every other schema operation and every endpoint behind an
  `unavailable` capability (`audit_query`, `application_catalog`) refuses
  uniformly with `CAPABILITY_UNSUPPORTED`, matching its own declaration
  exactly -- `MitateDB-api/tests/test_http.py::test_declared_unavailable_
  endpoints_deny_uniformly_after_auth` parametrizes `POST /v1/audit/query`
  among them and pins both the post-authentication `CAPABILITY_UNSUPPORTED`
  and the unauthenticated `AUTH_*`-first ordering. (`audit_query` is
  `unavailable` **on this host**: since phase 4 WP-3(b) it is `enabled` on
  the control service, which is a different deployment unit making a
  different, equally true statement about itself -- see the audit note under
  "What remains reference-only or unimplemented".) **`cross_entity_mutation`, closed phase 3.5 WP-2/WP-3**
  (`docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md`): no longer
  `unavailable` -- `POST /v1/data/mutations` executes a real two-pass
  (validate-all-then-execute) atomic unit across `insert`/`update`/`delete`
  spanning multiple entities in one request, declared `partial`
  (`unsupported: ["upsert"]`, matching this peer's own single-entity
  `atomic_mutation` declaration exactly), bound by a new `batch_entities`
  resource class (default 10, distinct-entity counting) alongside the
  existing `batch_items`. See `security/CONTROL_MAPPING.md`'s SI-08/SI-11
  rows for the full enforcement/atomicity evidence.
- **Control plane, `/control/v1`** (`src/mitatedb_api/control_plane.py`,
  `control_http.py`, `control_main.py`): the contract's 11 endpoints
  (capabilities, application register/list/enable/disable, credential
  issue/list/rotate/revoke/disable/enable), a fixed evaluation order
  (rate-limit -> authenticate -> must_rotate gate -> capability check ->
  shape -> target resolution -> bounds -> destructive-confirmation ->
  execute+audit), three enforced resource classes
  (`applications`/`credentials_per_application`/
  `control_requests_per_minute`) plus its own `request_bytes` bound, and a
  durable, same-transaction, 13-field audit trail
  (`mitatedb_registry.control_audit`, INSERT-only from the control-plane
  process' own role -- it cannot read its own writes back). A
  `role=control` credential can only ever be minted by the out-of-band
  operator ceremony, `python -m mitatedb_api.ops bootstrap`/`reset`
  (declare-and-echo gated) -- no in-band path exists anywhere. Whether the
  application-plane process declares `control_plane: enabled` is a
  deployer decision (`MITATEDB_CONTROL_PLANE_STATUS`), not a detected
  fact -- see `docs/cloud-run-cloud-sql.md` §8 invariant 3. **Control
  bundle, closed phase 3.5 WP-1/WP-5** (design §1/§4): `must_rotate`
  exposure on `list_credentials`; a second, narrower `role="audit"`
  control-credential class (read-only on the 3 read endpoints, ceremony-
  issued only, fail-closed with durable audit on the other 8); per-
  application issuance freeze (`freeze-issuance`/`unfreeze-issuance` CLI,
  `FORBIDDEN` while frozen). See `security/CONTROL_MAPPING.md`'s SI-02/
  SI-06/SI-07 rows for the full evidence.
- **Break-glass CLI** (`python -m mitatedb_api.ops`, `src/mitatedb_api/
  ops.py`): beyond `bootstrap`/`reset`, an operator with a live control
  credential and direct Cloud SQL access (no `/control/v1` network path
  required) can `list-applications`/`list-credentials`/`enable-
  application`/`disable-application`/`enable-credential`/`disable-
  credential`/`rotate-credential`/`revoke-credential`/`audit-report` --
  every state-changing one of these calls the SAME `ControlPlaneService`
  methods `/control/v1` itself uses, never a second, reimplemented
  control-plane logic path. `deprovision <application_id>` is this CLI's
  own second genuinely destructive subcommand (declare-and-echo gated,
  fingerprinted on the application's own `registered_at`) -- it permanently
  removes an application's entire database, both its login roles, and its
  registry rows. See `docs/CONTROL_PLANE_COMPROMISE_PLAYBOOK.md` for the
  control-credential lockout/compromise recovery procedure this CLI
  supports.
- **Two conformance adapters**: `MitateDB-api` (in-process, `conformance/
  conformance_adapter_mitatedb.py`) and `MitateDB-api-http`
  (`conformance/conformance_adapter_mitatedb_http.py`, real HTTP + real
  PostgreSQL, throwaway-prefixed databases/roles per run, the bootstrap/
  reset ceremony run as a real `python -m mitatedb_api.ops` subprocess).
  Both are `required: true` in `../conformance-tests/registry.json`.
  Executable conditions this peer now participates in for real: C-01,
  C-03, C-06, C-08, C-11 (partial, see `conformance-tests/CONDITIONS.md`),
  C-12, C-13, C-14, C-15, C-16 (PROVIDED branch, phase 3.5 WP-3 --
  `cross_entity_mutation` is `partial` on both adapters), C-17
  (structural-evidence branch, since `row_addressability` stays
  `unavailable`), C-18.
- **Deployment assets** (`docker/Dockerfile`, `docs/cloud-run-cloud-sql.md`,
  `docs/CONTROL_PLANE_COMPROMISE_PLAYBOOK.md`): one non-root, multi-stage
  image serving either ASGI app (`SERVICE=data`/`SERVICE=control`), a
  Cloud SQL/Cloud Run runbook with four runbook-level invariants
  (control service `max-instances=1`; application roles never created via
  the Cloud SQL Users API/Console; the two services' declared/actual
  control-plane state kept in lockstep; provisioning sessions run with
  statement logging disabled), and the control-credential lockout/
  compromise recovery playbook.

All of the above has been exercised against a real local PostgreSQL 16
cluster (`tests/test_postgres.py`, `test_control_plane_postgres.py`, and
both conformance adapters) -- not a mocked database. That is local/
test-cluster evidence, not production evidence: no step in
`docs/cloud-run-cloud-sql.md` has yet been run against a real Cloud SQL
instance or a real Cloud Run deployment (`security/CONTROL_MAPPING.md`
records this per invariant, and `docs/cloud-run-cloud-sql.md` §9 is the
real-instance verification procedure for when that changes).

### What remains reference-only or unimplemented

- **Capability envelope frozen this phase** (design v1.2 §0): `upsert`,
  `contains`/`matches`/`is_null`, `row_addressability`,
  `revision_preconditions`, `idempotency`, `application_catalog`,
  and `best_effort_transactions` stay at their current
  declaration (`unavailable`/`unsupported`). **`cross_entity_mutation` no
  longer belongs on this list**: the requester approved phase 3.5
  (2026-08-31) and it shipped as `partial` in WP-2/WP-3 -- see the "What
  now exists" section above and
  `docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md`. **Neither does
  `audit_query`**: phase 4 WP-3(b) shipped it as `enabled` on the CONTROL
  service (the data service still declares it `unavailable`, truthfully --
  that host does not serve it), see the audit note at the end of this
  section and `docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md`.
- **Application-plane resource bounds beyond `request_bytes`**: request
  rate, concurrency, and execution-time limits are not implemented at the
  application-code layer on this peer (Cloud Run's own concurrency/
  timeout settings are a deployment-layer control, not yet declared as
  such -- `limit_enforcement: deployment_required` -- anywhere in this
  codebase).
- **RLS defence-in-depth**, **IAM DB authentication/Cloud SQL Connector**,
  and a **shared/cross-instance control-plane rate window** (needed only
  if the control service ever runs with more than one instance) are all
  deferred future strengthening, not implemented.
- ~~**Application-plane durable audit sink** and `audit_query` itself are
  phase 4 scope -- the control plane's own audit trail (above) is durable
  and real; the application plane's is not yet.~~ **Closed, phase 4
  WP-3(a)/WP-3(b)** (`docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md`): the
  application plane now writes to `mitatedb_registry.application_audit`
  (migration `0005`, `mitatedbsvc_api` INSERT-only, a separate SELECT-only
  `mitatedbsvc_auditreader` as the only network reader). Fail-closed-class
  events are committed **before** the data transaction commits -- a sink
  failure rolls the operation back with `SERVICE_UNAVAILABLE` -- and the
  backends' `commit()` moved inside the classified `try` so a commit failure
  produces a durable `error` row for the same `request_id` instead of
  escaping unclassified. Ordinary query/insert/update successes are recorded
  too (they previously were not recorded anywhere) via a bounded buffer whose
  overflow is never silent. The pre-existing 6-field in-memory sink, whose
  allowlist silently rounds unknown values, is deliberately kept OFF the
  durable path. `audit_query` is served on the control service at
  `/control/v1/audit/query` and the `/v1/audit/query` alias, for control and
  audit credentials only, with `contract_version` now `1.4.0`. Operational
  procedure is `docs/cloud-run-cloud-sql.md` §3.2b-§3.2f; the evidence table
  is `security/CONTROL_MAPPING.md`'s SI-14 row.
- The SQLite backend (`backend_sqlite.py`) remains a local, deterministic
  test double and is never a deployment target (unchanged from the
  original foundation).

Application-facing code intentionally has no SQL/native-command execution
surface and no access to Control or Provisioning authorities.
