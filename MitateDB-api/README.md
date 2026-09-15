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
control plane (`/control/v1`, 12 distinct endpoints + the out-of-band
bootstrap/reset ceremony) both run over real PostgreSQL persistence, and
this peer registers as **two** conformance adapters. `security/CONTROL_MAPPING.md`
is the authoritative row-by-row account of what is local/test evidence
versus what remains unevidenced. Cloud SQL/Cloud Run production platform
evidence is partial, not absent: `docs/cloud-run-cloud-sql.md` §9.1 records
the runbook's first real execution against a live Cloud SQL 16.14 instance
(2026-09-01, operator-reported, supervisor-verified) -- role/database DDL,
the `GRANT ... WITH SET TRUE` construct, and `log_statement` suppression
PASS, while deprovision and the cloudsqlsuperuser fail-closed probe remain
unexercised against that instance.

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
  `add_field`/`alter_field` (developer credentials only; `create_index`/
  `drop_index`/`drop_entity`/`jobs` stay `unsupported`); every other schema
  operation and the one endpoint behind an `unavailable` capability
  (`audit_query`) refuses uniformly with `CAPABILITY_UNSUPPORTED`, matching
  its own declaration exactly -- `MitateDB-api/tests/test_http.py::test_
  declared_unavailable_endpoints_deny_uniformly_after_auth` parametrizes
  `POST /v1/audit/query` (its only case) and pins both the
  post-authentication `CAPABILITY_UNSUPPORTED` and the unauthenticated
  `AUTH_*`-first ordering. The other three `unavailable` capabilities have
  no endpoint of their own to deny uniformly and are refused in their own,
  different forms: `best_effort_transactions` is a present denial of the
  *request-parameter value* `transaction: "best_effort"` on
  `POST /v1/data/{entity}/mutations` (`http.py:1004-1010`); the
  cross-entity `POST /v1/data/mutations` batch has no `transaction` field
  to refuse at all (`http.py:1137`). `revision_preconditions` is a present
  denial of the `expected_revision` parameter `transact()` accepts on
  either mutation entry point (`conformance-tests/CONDITIONS.md:47`, C-18).
  `row_addressability` has no call surface at all on the in-process
  adapter -- `SurfaceAbsent` (`conformance-tests/CONDITIONS.md:46`, C-17
  form (a)). (`audit_query` is
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
  `control_http.py`, `control_main.py`): 12 distinct control endpoints
  (capabilities, application register/list/enable/disable, credential
  issue/list/rotate/revoke/disable/enable, `audit_query`) -- C-14's
  fail-closed authority boundary (`conformance-tests/CONDITIONS.md`)
  covers 11 of these, every one except `audit_query` --
  `control_http.py`'s route table has 13 `Route(...)` entries because
  `audit_query` is registered twice, at its canonical
  `/control/v1/audit/query` path and, for one further minor version, also
  at the `/v1/audit/query` alias (contract `endpoints.audit_query.
  deprecation_note`; same handler) -- a fixed evaluation order
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
  Both are `required: true` in `../conformance-tests/registry.json`
  (all 4 registered adapters -- `r2db-api`, `r2db-api-http`, `MitateDB-api`,
  `MitateDB-api-http` -- are `required: true`).
  Executable conditions this peer now participates in for real: **all 26
  registered conditions, C-00 through C-25** (`conformance-tests/CONDITIONS.md`),
  each executable on all four registered adapters. Notable branches for this
  peer: C-11 partial (see `conformance-tests/CONDITIONS.md`); C-14/C-15
  PROVIDED (`control_plane: enabled`, exercised for real end-to-end); C-16
  PROVIDED (phase 3.5 WP-3 -- `cross_entity_mutation` is `partial` on both
  adapters); C-17 structural-evidence branch (`row_addressability` stays
  `unavailable`).
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
test-cluster evidence, not full production evidence: `docs/cloud-run-cloud-sql.md`
§9.1 records the runbook's first real execution, against a live Cloud SQL
16.14 instance (2026-09-01, operator-reported, supervisor-verified) --
role/database DDL, the `GRANT ... WITH SET TRUE` construct, and
`log_statement` suppression PASS, while deprovision (`pg_terminate_backend`)
and the `assert_role_has_no_memberships`/cloudsqlsuperuser fail-closed probe
remain unexercised against that instance (`security/CONTROL_MAPPING.md`
records this per invariant; `docs/cloud-run-cloud-sql.md` §9 is the ongoing
real-instance verification procedure).

### What remains reference-only or unimplemented

- **Remaining declaration gaps** (`cell.py`'s `__build_capabilities_document`
  (body now in `capabilities_document.py`), as of this WP): `upsert` (`unsupported` within `atomic_mutation`/
  `cross_entity_mutation`), `contains`/`matches`/`is_null` (`unsupported`
  within `structured_query`), `create_index`/`drop_index`/`drop_entity`/
  `jobs` (`unsupported` within `schema_operations`), `row_addressability`,
  `revision_preconditions`, and `best_effort_transactions` stay
  `unavailable`/`unsupported`. **`idempotency` (Phase 9 WP-3c, `cell.py:3887`)
  and `application_catalog` (Phase 6 WP-3, `cell.py:3860`) no longer belong
  on this list**: both are `enabled`. **`cross_entity_mutation` no
  longer belongs on this list**: the requester approved phase 3.5
  (2026-08-31) and it shipped as `partial` in WP-2/WP-3 -- see the "What
  now exists" section above and
  `docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md`. **Neither does
  `audit_query`**: phase 4 WP-3(b) shipped it as `enabled` on the CONTROL
  service (the data service still declares it `unavailable`, truthfully --
  that host does not serve it), see the audit note at the end of this
  section and `docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md`.
- **Application-plane resource bounds** (Phase 8 WP-1a, rework 1,
  2026-09-06): `requests_per_minute` and `concurrency` are `enforced` --
  `_LimitStateHolder.acquire_rate`/`.concurrency_slot` (`cell.py:744`,
  `:775-782`, `:785-794`), declared in `limit_enforcement`
  (`cell.py:4051`, `:4055`); `execution_ms` is declared
  `reference_wall_clock`, not `enforced` (`cell.py:4044`) -- a wall-clock
  deadline (`time.monotonic() + max_execution_ms`) handed to the backend,
  `backend_postgres.py` converts it into a real `SET LOCAL
  statement_timeout`/`lock_timeout` (`backend_postgres.py:1658-1661`),
  matching r2db-api's own identical declaration. Cloud Run's own
  concurrency/timeout settings remain a separate, undeclared
  deployment-layer control on top of the above -- the contract's
  `limit_enforcement` enum has a `deployment_required` member for exactly
  this kind of control (`contract/data-service-api.v1.json:198,1201`), but
  it appears nowhere in either peer's own declaration code.
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
