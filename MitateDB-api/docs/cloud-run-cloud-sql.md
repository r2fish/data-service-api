# MitateDB-api Cloud Run / Cloud SQL deployment runbook

Status: operator/deploy-tooling runbook, implementation-local to
`MitateDB-api` (this document names `MitateDB-api`-specific roles, schema
names, migration files, and CLI commands; r2db-api's own equivalent
deployment material -- VPS/systemd/nginx, `r2db-api/deploy/
DEPLOYMENT_RUNBOOK.md` and `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md`
-- was read only as a reference for the *shape* of the problems a
deployment runbook has to solve, never copied: r2db-api targets a
long-lived VPS PostgreSQL cluster, this peer targets Cloud Run/Cloud SQL,
design v1.2 R-9). Companion documents: `docs/design/
MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md` (R-1/R-6/R-9 -- the design
decisions this runbook executes), `security/CONTROL_MAPPING.md` (evidence
status), and `CONTROL_PLANE_COMPROMISE_PLAYBOOK.md` (this same directory --
what to do once a control credential is lost, leaked, or misused; this
runbook's own §8 only points there, it does not repeat that material).

**Evidence honesty (R-1, WP-6)**: everything this repository's own test
suite exercises (`tests/test_postgres.py`, the `MitateDB-api-http`
conformance adapter) runs against a local PostgreSQL 16 cluster (Homebrew,
`host=/tmp port=5432`) -- **no step in this runbook has yet been executed
against a real Cloud SQL instance or a real Cloud Run deployment**. This
document is deploy-time procedure, not deploy-time evidence; `security/
CONTROL_MAPPING.md`'s own MitateDB column records `production_platform_
evidence: absent` until an operator has actually run it once and recorded
the outcome (§9 below).

Scope: everything below is operator/deploy-tooling work. Nothing in
`MitateDB-api`'s own application code drives GCP APIs, creates GCP
resources, or reads a GCP-specific credential type -- the code only ever
sees a PostgreSQL DSN and two pepper strings, supplied as plain environment
variables (design R-9: "コードは Cloud を知らない"). Every identifier below
(`example-project`, `example.internal`, etc.) is a synthetic placeholder --
substitute your own project/organization values; this document must never
be edited to contain a real project id, service account email, or secret
value (`docs/security/public-repository-policy.md`).

## 0. Topology this runbook builds

```
                        ┌──────────────────────────┐
  mitate-application ──▶│ Cloud Run: mitatedb-data │──▶ Cloud SQL
  (its own service      │ mitatedb_api.main:app    │    as mitatedbsvc_api:
   account only)        │ /v1/*                    │    - one DB per app
                        │  incl. /v1/audit/query   │    - registry SELECT
                        │  -> CAPABILITY_UNSUPP.   │    - application_audit
                        └──────────────────────────┘      INSERT-only
                        ┌──────────────────────────┐
  operator (IAM-gated,  │ Cloud Run: mitatedb-ctrl │──▶ Cloud SQL
  --no-allow-unauth.) ─▶│ mitatedb_api.control_    │    as mitatedbsvc_
                        │ main:app                 │    controlplane:
                        │ /control/v1/*            │    - registry r/w
                        │  + /control/v1/audit/    │    - control_audit
                        │      query               │      INSERT-only
                        │  + /v1/audit/query       │
                        │      (alias, SAME        │──▶ Cloud SQL
                        │       handler)           │    as mitatedbsvc_
                        └──────────────────────────┘    auditreader
                                                        (MITATEDB_AUDIT_DSN,
                                                         optional):
                                                        - SELECT-only on
                                                          control_audit +
                                                          application_audit
```

Two separate Cloud Run services from the SAME container image (`docker/
Dockerfile`, `SERVICE=data` / `SERVICE=control`) -- design R-6/R-9's own
"独立 ASGI app...既定は分離" default. Both connect to the SAME Cloud SQL
instance's `mitatedb_platform` database, as DIFFERENT PostgreSQL roles
with disjoint grants (`mitatedbsvc_api` read-only on `applications`/
`credentials`, nothing on `control_credentials`/`control_audit`, and since
migration `0005` INSERT-only on `application_audit`;
`mitatedbsvc_controlplane` read/write on `applications`/`credentials`/
`control_credentials`, INSERT-only on `control_audit`, nothing at all on
`application_audit` -- migrations `0002`/`0005`, design R-4's own
process-role separation). The control service additionally holds a THIRD,
optional connection as `mitatedbsvc_auditreader` (SELECT-only on both audit
tables, `MITATEDB_AUDIT_DSN`, §3.2b) -- that is the only role in this
topology that can read an audit table back over the network, and neither
process role can.

**The control service now serves a path outside the `/control/v1/*`
prefix.** `POST /v1/audit/query` on `mitatedb-ctrl` is an ALIAS of
`POST /control/v1/audit/query` -- the same handler, kept for one minor
because contract 1.4.0 moved `audit_query`'s canonical classification to
`control_endpoints` (item 7). It is registered whether or not
`MITATEDB_AUDIT_DSN` is set. Consequence for deployment policy: **an edge
rule, LB path matcher, or ingress restriction expressed over
`/control/v1/*` alone no longer covers the whole control surface** -- it
leaves `/v1/audit/query` on the control host outside the boundary, and that
path reads `control_audit`. Express the restriction over the SERVICE (which
`--no-allow-unauthenticated` plus the operator-only invoker binding of §6.2
already does here) or over both prefixes. The identically-spelled path on
`mitatedb-data` is a DIFFERENT endpoint and is unchanged: it authenticates
an application credential and answers `CAPABILITY_UNSUPPORTED`, a true
statement about a host that does not provide the audit surface -- pinned by
`MitateDB-api/tests/test_http.py::test_declared_unavailable_endpoints_deny_
uniformly_after_auth`, which parametrizes over `POST /v1/audit/query` among
the data service's other declared-unavailable endpoints and fixes both the
post-authentication `CAPABILITY_UNSUPPORTED` and the unauthenticated
`AUTH_*`-first ordering. Do not
"unify" them by routing the data service's `/v1/audit/query` to the control
service -- that would put control/audit credential traffic onto the
application-facing service, which is exactly the separation this topology
exists to keep.

### 0.1 Operational deviation record -- current deployment (2026-09-01)

This is a legitimate configuration this architecture permits, not a
violation of it -- the control plane is optional per contract/design
(`FoundationConfig.control_plane_status` defaults to `"unavailable"`,
`config.py`: "an operator who does not explicitly opt in...sees no behavior
change at all"), and this runbook's §2 instance sizing/networking values are
this document's own defaults, not hard requirements. The first real
deployment (2026-09-01) intentionally runs a configuration narrower than
the full two-service topology above, recorded here honestly rather than
left as an undocumented drift from this runbook's own diagram:

- **No standing control Cloud Run service (`mitatedb-ctrl`) deployed.**
  Application onboarding (§3.4, `0003`/`0004`) is performed via the
  break-glass CLI (§7) run locally through the Cloud SQL Auth Proxy
  ceremony (§2's own `cloud-sql-proxy` step), not over `/control/v1` HTTP.
  The data service's own `MITATEDB_CONTROL_PLANE_STATUS` is set to
  `unavailable` (not `enabled`, unlike §6.1's own example
  `--set-env-vars`) -- matching **invariant 3** (§8 above) even though no
  control service was ever stood up to begin with, not only when one is
  torn down: the data service's own capability declaration must never claim
  a control plane that is not actually reachable.
- **`db-f1-micro` tier**, narrower than §2's own `db-custom-2-7680`
  example -- a capacity choice for this deployment's current scale, not a
  security property; revisit sizing independently of everything else in
  this record.
- **Public IP, empty authorized networks, connector-only access** --
  narrower than §2's own `--no-assign-ip` default. The instance has a
  public IP assigned, but its authorized-networks list is empty (no CIDR
  admitted), so the only reachable path is still Cloud Run's own Cloud SQL
  connector (§6's own `--add-cloudsql-instances`, now also gated by
  `roles/cloudsql.client` above) and the operator's own Cloud SQL Auth
  Proxy (§2) -- not a bare TCP path open to the internet. VPC peering
  (`--no-assign-ip`, §2's own documented default) is tracked as future work
  for this deployment, not yet applied.

None of the three deviations above changes any Security Invariant control
mapping (`security/CONTROL_MAPPING.md`) -- they are deployment-scale and
network-topology choices the architecture already treats as configurable,
recorded here so a later operator does not mistake this deployment's
current shape for this runbook's own required defaults.

## 1. Prerequisites

- A GCP project with the Cloud SQL Admin API and Cloud Run API enabled.
- `gcloud` and `psql` (PostgreSQL 16 client) available to whoever runs this
  runbook -- an operator workstation or a CI/CD job with the same tools.
- This repository checked out (`MitateDB-api/migrations/*.sql`,
  `MitateDB-api/src/mitatedb_api/ops.py` -- both are run from the checkout,
  never from inside a running container; see `docker/Dockerfile`'s own
  footer note on why `migrations/` is deliberately not baked into the
  image).
- A Secret Manager instance in the same project (§4).

## 2. Cloud SQL instance

```sh
gcloud sql instances create mitatedb-platform \
  --project=example-project \
  --database-version=POSTGRES_16 \
  --tier=db-custom-2-7680 \
  --region=us-central1 \
  --no-assign-ip \
  --network=projects/example-project/global/networks/default \
  --require-ssl
```

**PostgreSQL 16, fixed (design R-1)**: migration `0001`'s own `GRANT <role>
TO CURRENT_USER WITH SET TRUE` statement is a PostgreSQL 16+ construct --
this is the version-pin's own concrete reason, not an arbitrary choice.
`--no-assign-ip` + a private-network connection (Cloud Run's own [Cloud SQL
connector](https://cloud.google.com/sql/docs/postgres/connect-run) or a
VPC connector) keeps the instance off the public internet entirely; this
runbook does not use a public IP anywhere below.

Connect to it for the bootstrap steps below via the Cloud SQL Auth Proxy
(or `gcloud sql connect`, which wraps the same thing) rather than a bare
TCP DSN:

```sh
cloud-sql-proxy --port 5432 example-project:us-central1:mitatedb-platform &
```

## 3. Platform bootstrap (run once)

**Invariant 4 (WP-1 review M-7, this runbook's own instance): disable
statement logging for this session before running any provisioning SQL.**
Every provisioning statement below binds a freshly generated password as a
plpgsql `%L` literal (`CREATE ROLE ... PASSWORD %L`) -- if `log_statement`
is `all`/`mod`/`ddl` for the connecting role or the whole instance, that
literal is written to Cloud SQL's own query log in plaintext. Set this
BEFORE step 3.1:

```sh
gcloud sql instances patch mitatedb-platform --database-flags=log_statement=none
```

(Restore whatever flag value your organization's baseline requires once
every provisioning step below has completed -- this is a provisioning-
session-scoped precaution, not a permanent instance setting this runbook
prescribes.)

### 3.1 `mitatedbsvc_provision` + `mitatedb_platform` (migration `0001`)

Connect as the Cloud SQL instance's own bootstrap superuser-equivalent
(the `postgres` user Cloud SQL creates by default, which IS a
`cloudsqlsuperuser` member -- the one and only place in this whole runbook
that role is used, and only to run `CREATE ROLE`/`CREATE DATABASE` for the
provisioning role itself):

```sh
export MITATEDBSVC_PROVISION_PASSWORD="$(openssl rand -base64 32)"
psql "host=127.0.0.1 port=5432 dbname=postgres user=postgres" \
  -v provision_password="$MITATEDBSVC_PROVISION_PASSWORD" \
  -f MitateDB-api/migrations/0001_bootstrap_platform.sql
```

Record `MITATEDBSVC_PROVISION_PASSWORD` in Secret Manager immediately (§4)
-- nothing in this flow re-displays it.

**SET-ROLE behavior on real Cloud SQL (2026-09-01 fix)**: `0001` now
brackets its own `CREATE DATABASE mitatedb_platform OWNER mitatedbsvc_
provision` with `GRANT mitatedbsvc_provision TO CURRENT_USER WITH SET
TRUE` / `REVOKE ... FROM CURRENT_USER` (self-contained, no separate
operator step needed). This exists because PostgreSQL 16 requires the
executing role to already be able to `SET ROLE` to a role before naming it
in an `OWNER`/`OWNER TO` clause, and Cloud SQL's own bootstrap `postgres`
role -- a `cloudsqlsuperuser` member, not a genuine PostgreSQL superuser --
does NOT get the `SET` option for free on a role it just created via
`CREATE ROLE` (only `ADMIN OPTION`), unlike a true superuser. Without the
bracket, this step fails with `must be able to SET ROLE
"mitatedbsvc_provision"`.

**Fallback for an older checkout** (a `MitateDB-api/migrations/0001_
bootstrap_platform.sql` from before this fix, lacking the bracket above):
the `GRANT` cannot be run BEFORE `0001` on a fresh instance -- it names a
role (`mitatedbsvc_provision`) that does not exist yet until `0001`'s own
`CREATE ROLE` step creates it. The real, executable recovery sequence
instead runs `0001` first (its `CREATE ROLE` step succeeds; `CREATE
DATABASE` then fails under `ON_ERROR_STOP`, since the pre-fix file has no
bracket), grants the missing `SET` option by hand, then **re-runs** `0001`
-- which is safe because every step in it is already idempotent (`CREATE
ROLE` is a no-op the second time; `CREATE DATABASE` now succeeds):
```sh
# 1. Run 0001 as above -- CREATE ROLE succeeds, CREATE DATABASE fails
#    under ON_ERROR_STOP ("must be able to SET ROLE ...").
psql "host=127.0.0.1 port=5432 dbname=postgres user=postgres" \
  -v provision_password="$MITATEDBSVC_PROVISION_PASSWORD" \
  -f MitateDB-api/migrations/0001_bootstrap_platform.sql
# 2. Grant the missing SET option by hand -- the role now exists, so this
#    resolves.
psql "host=127.0.0.1 port=5432 dbname=postgres user=postgres" \
  -c "GRANT mitatedbsvc_provision TO postgres WITH SET TRUE"
# 3. Re-run 0001 -- CREATE ROLE is a no-op (role already exists), CREATE
#    DATABASE now succeeds.
psql "host=127.0.0.1 port=5432 dbname=postgres user=postgres" \
  -v provision_password="$MITATEDBSVC_PROVISION_PASSWORD" \
  -f MitateDB-api/migrations/0001_bootstrap_platform.sql
# 4. Revoke the temporary membership.
psql "host=127.0.0.1 port=5432 dbname=postgres user=postgres" \
  -c "REVOKE mitatedbsvc_provision FROM postgres"
```
Keep this only as a fallback for a checkout that predates the in-file fix,
not as the normal procedure -- a checkout with the fix needs only the
single `psql -f 0001_...` command above.

### 3.2 Registry schema + process roles (migration `0002`)

```sh
psql "host=127.0.0.1 port=5432 dbname=mitatedb_platform user=mitatedbsvc_provision password=$MITATEDBSVC_PROVISION_PASSWORD" \
  -f MitateDB-api/migrations/0002_registry_and_functions.sql
```

This creates `mitatedbsvc_api`/`mitatedbsvc_controlplane` (both `LOGIN`,
both `NOSUPERUSER NOCREATEDB NOCREATEROLE`) with no password yet -- set one
for each and record both in Secret Manager:

```sh
psql "host=127.0.0.1 port=5432 dbname=postgres user=postgres" -c \
  "ALTER ROLE mitatedbsvc_api PASSWORD '$(openssl rand -base64 32)'"
psql "host=127.0.0.1 port=5432 dbname=postgres user=postgres" -c \
  "ALTER ROLE mitatedbsvc_controlplane PASSWORD '$(openssl rand -base64 32)'"
```

### 3.2b Application-plane durable audit sink + `audit_query` reader (migration `0005`, Phase 4 WP-3(a)/WP-3(b))

Migration and wiring below; the operational parts -- capacity thresholds,
the five fixed alert messages, `audit_requests_per_minute` sizing, manual
retention, and reading evidence during a Cloud SQL outage -- are §3.2c-§3.2f
immediately after it.

Run once, after `0002`, as the SAME `mitatedbsvc_provision` role/connection:

```sh
psql "host=127.0.0.1 port=5432 dbname=mitatedb_platform user=mitatedbsvc_provision password=$MITATEDBSVC_PROVISION_PASSWORD" \
  -f MitateDB-api/migrations/0005_application_audit.sql
```

This creates `mitatedb_registry.application_audit` (`mitatedbsvc_api`
gains INSERT-only on it -- no new privilege on any other object) and the
new `mitatedbsvc_auditreader` role (`LOGIN`, `SELECT`-only on BOTH
`control_audit` and `application_audit`, no password yet):

```sh
psql "host=127.0.0.1 port=5432 dbname=postgres user=postgres" -c \
  "ALTER ROLE mitatedbsvc_auditreader PASSWORD '$(openssl rand -base64 32)'"
```

Record the reader's DSN in Secret Manager under `mitatedb-audit-dsn` (same
convention as `mitatedb-controlplane-dsn`), and configure it on the
CONTROL service (`mitatedb-ctrl`, §6.2) via the `MITATEDB_AUDIT_DSN`
environment variable -- **optional**: unset, `audit_query` stays declared
`unavailable` (the two HTTP routes `/control/v1/audit/query` and `/v1/
audit/query` still exist and still authenticate, answering `CAPABILITY_
UNSUPPORTED` rather than a bare 404).

**Q4 phase (design docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md D-1/D-2)
supersedes the two paragraphs this replaces**: `MITATEDB_AUDIT_STATEMENT_
TIMEOUT_MS`/`MITATEDB_AUDIT_IDLE_TIMEOUT_MS` and `MITATEDB_DATA_BASE_URL`/
`MITATEDB_CONTROL_BASE_URL` are **removed** env vars -- defined at all
(even as an empty string) makes both services refuse to start (F-1/F-2).
The two writer timeouts and `surfaces` now live in the platform database
itself, as the single source both processes read at startup, closing the
former "nothing enforces it"/"must be updated to match by hand" gap this
section used to document.

Apply the platform single-shot migration (idempotent -- safe to re-run):

```sh
psql "host=127.0.0.1 port=5432 dbname=mitatedb_platform user=mitatedbsvc_provision password=$MITATEDBSVC_PROVISION_PASSWORD" \
  -v api_role='mitatedbsvc_api' -v controlplane_role='mitatedbsvc_controlplane' \
  -f MitateDB-api/migrations/0007_platform_declarations.sql
```

**Both `-v` variables are required** (correction 2026-09-05, Q4 phase WP-5 --
this command previously omitted them, and `psql` stops on the first
unset-variable reference): they name the two service writer roles this file
both issues `ALTER ROLE ... SET` for **and** seeds into the
`audit_writer_roles` declaration row, from the same variables inside the
same transaction, so the roles that carry the timeouts and the roles the
control service derives the lag over can never drift apart (design D-2(h)).
The two values above are this deployment's production role names; the
repository's own tests pass throwaway-prefixed names through the very same
variables, which is why no role name is hard-coded in the product code.

This sets `statement_timeout`/`idle_in_transaction_session_timeout` as
PostgreSQL role settings on BOTH `mitatedbsvc_api` and
`mitatedbsvc_controlplane` (shipped default `5000ms`/`5000ms`, matching
the pre-Q4 default -- no behavior change at deploy time) and creates
`mitatedb_registry.platform_declarations`, seeding
`audit_coalescing_window_ms` with the shipped default (`60000`).
`surfaces` is deployment-specific and is **not** seeded -- declare it once
both Cloud Run URLs are known:

```sh
python -m mitatedb_api.ops declare-surfaces \
  --data-base-url https://mitatedb-data.example.invalid/v1 \
  --control-base-url https://mitatedb-ctrl.example.invalid/control/v1
```

(omit `--control-base-url <URL>` entirely -- or pass `--no-control`, an
explicit, equivalent form of that same omission -- for a deployment with
no control surface; neither is required, but passing both is a usage
error, since this command replaces the entire row.)

Change either writer timeout with `set-platform-timeouts` (always both
roles together -- there is no per-role flag) or the coalescing window with
`declare-coalescing-window`, and inspect the current state (both the
declarations table and each role's own `pg_db_role_setting` row) with
`show-declarations`:

```sh
python -m mitatedb_api.ops set-platform-timeouts --statement-ms 5000 --idle-ms 5000
python -m mitatedb_api.ops declare-coalescing-window --ms 60000
python -m mitatedb_api.ops show-declarations
```

All four subcommands connect with `MITATEDB_PROVISION_DSN` (the same
`mitatedbsvc_provision` credential the migrations above already use).
**Every one of these changes is a startup-time snapshot** (design U-3):
apply the change, then restart BOTH `mitatedb-app`/`mitatedb-ctrl` for it
to take effect. Ordering matters when the change narrows a bound:
restart the DATA service first when **shortening** either timeout
(otherwise the control service could briefly declare a `visibility_lag_ms`
shorter than what the still-old data service's pooled connections
actually honor), and restart the CONTROL service first when
**lengthening** it (§9.2 of the design).

**Verify the two timeouts are genuinely applied** -- from a session
authenticated as the writer role each service actually connects as
(`mitatedbsvc_api` for the data service's own `application_audit` writer,
`mitatedbsvc_controlplane` for the control service's own `control_audit`
writer), confirm both effective values match the declaration:

```sh
psql "host=127.0.0.1 port=5432 dbname=mitatedb_platform user=mitatedbsvc_api password=$MITATEDBSVC_API_PASSWORD" -c \
  "SHOW statement_timeout; SHOW idle_in_transaction_session_timeout;"
psql "host=127.0.0.1 port=5432 dbname=mitatedb_platform user=mitatedbsvc_controlplane password=$MITATEDBSVC_CONTROLPLANE_PASSWORD" -c \
  "SHOW statement_timeout; SHOW idle_in_transaction_session_timeout;"
```

Both must report the SAME two values -- but this is now also
**self-verifying**: each process checks its OWN writer connection's
effective value against `pg_db_role_setting` at every startup (design
D-1(b)) and refuses to start on a mismatch (an `options=-c ...` override,
`PGOPTIONS`, or a stray `ALTER ROLE ... IN DATABASE ...` row all count),
so a silent drift between "declared" and "effective" can no longer reach
production undetected the way it could before Q4 -- **for that process'
own role.** This limitation is real, not editorial caution (design §3.11
point 9): role settings apply only at login time, so the control service
can read (but never effective-check) `mitatedbsvc_api`'s catalog
declaration, and vice versa -- verifying `mitatedbsvc_api`'s own effective
value is the data service's own job, done on its own next startup, not
something the control service's startup check can substitute for. The two
manual `psql`/`SHOW` commands above remain the way to confirm BOTH roles
together, in one place, at deploy time.

The `audit_requests_per_minute` window is a SEPARATE pre-auth counter from
`control_requests_per_minute` (`MITATEDB_CONTROL_AUDIT_REQUESTS_PER_
MINUTE_LIMIT`, default 60) -- never shared, so a high-frequency audit
poller cannot exhaust the window a break-glass `revoke_credential` depends
on. Like `control_requests_per_minute` (Invariant 1, §6.2), this window is
an in-process counter too, so it inherits the SAME `--max-instances=1`
requirement on `mitatedb-ctrl`.

`coalescing_window_ms` (the declared denial-coalescing window, part of the
`audit_query` capability entry) now comes from the SAME `platform_
declarations` row both services read at startup (`audit_coalescing_
window_ms`, above) -- both processes describe the SAME window by
construction, closing the former "control cannot read the data-plane
process' own live `AuditRouter`, so the two can drift" gap this section
used to document. Change it with `ops declare-coalescing-window` (above),
never by hand-editing a constant in either service's own source.

**Declared audit vocabularies (contract 1.5.0, subordinate ruling 10 item 1).**
The same `audit_query` capability entry also publishes THREE vocabularies:
`event_classes`, and -- new in contract 1.5.0 -- `operations` and
`target_kinds`. They are the sets of values the corresponding columns of an
audit row can take, and every event `audit_query` returns carries values drawn
from them (the contract requires the superset relation, never a particular
member: each implementation declares its own vocabulary, and the contract
enumerates no enum). On this service they are published `sorted()` as the
**union of two modules** -- the control half in `src/mitatedb_api/audit_
query.py` and the application half in `src/mitatedb_api/application_audit.py`
-- currently **29 `operations` and 5 `target_kinds`**. Note that
`audit_query.operations` is the audit row's `operation` vocabulary and has
nothing to do with the `operations` array of a mutation request body.

Two operational consequences. **(1) There is no env-var knob for these**, and
there is nothing to size: unlike the timeouts above, they are fixed by the
code you deployed, so the only way they change is a new image. **(2) They are
version-bound.** An image built before contract 1.5.0 declares
`contract_version: "1.4.0"` and carries neither key, which is fully conformant
for that version; an image that declares `1.5.0` must carry both. A deployment
where the declared version and the declared keys disagree is a version-binding
defect, not a configuration choice. If you ever see an `operation` or
`target_kind` value in an `audit_query` result that is absent from the
declaration, treat it as a defect and report it -- the declaration is checked
against this service's own source on every test run, so a divergence in a real
deployment means the deployed artifact is not the tested one.

### 3.2c Sizing the `audit_requests_per_minute` window

One `audit_query` call returns one page, so a consumer's steady-state cost
is `60000 / <declared visibility_lag_ms>` requests per minute -- about
**5.5 req/min per consumer** at the default 11000 ms lag, since polling
faster than the lag cannot surface anything sooner. The default of `60`
therefore supports roughly **ten** concurrently polling audit consumers.

```
audit_requests_per_minute  >=  ceil(<concurrent audit consumers>
                                    * 60000 / <visibility_lag_ms>)
                               + headroom for catch-up
```

One correction to that naive product. **Catch-up is paging, not
polling**: a consumer resuming after an outage walks the cursor one page per
request until a page comes back empty, so draining N backlogged events at
`limit` per page costs `N/limit` requests issued as fast as it can -- far
above steady state. Size for the catch-up case, or accept refusals during
catch-up.

**Raising this window is a configuration change, with no upper bound**
(Phase 5 D-3, Q3 案A, WP-4). `ControlPlaneLimits.__post_init__` validates
only that each of the four request-count classes is a positive integer --
there is no ceiling here, and the peer's own test suite really does
construct and publish `control_requests_per_minute=100_000`-scale values
(`MitateDB-api/tests/test_control_plane_service.py::
test_limits_accept_generous_values_beyond_the_former_ceiling`). A
deployment that outgrows the default sets
`MITATEDB_CONTROL_AUDIT_REQUESTS_PER_MINUTE_LIMIT` to whatever its
audit-agent population needs and nothing else has to change -- **matching
`r2db-api`'s own `ControlPlaneLimits.__post_init__`**, which has validated
only "positive integer" with no ceiling from the start (`r2db-api/docs/
POSTGRES_PROVISIONING_RUNBOOK.md` §15). The accepted value is now an
**operator responsibility, published as-declared** in
`control_capabilities` -- this peer used to fold the new class into a
shared `[1, 200]` range with the other three classes, which incidentally
acted as a guardrail against a wildly oversized configuration; removing
that ceiling removes the guardrail too (there is nothing in the product
that stops an operator from declaring, say,
`audit_requests_per_minute=5_000_000`). That is a deliberate trade (the
requester's design principle 3, "don't dodge behind a constraint"), not an
oversight -- it is recorded here and in `security/CONTROL_MAPPING.md`'s
SI-08 row. Widening this window does not weaken the property the window
exists for: it is checked **before** authentication and before any
durable write, so no window size lets an unauthenticated flood generate
audit rows. Exceeding the window is a plain `LIMIT_EXCEEDED` refusal that
costs only time -- the consumer's cursor stays valid and it resumes
exactly where it stopped. In every case a break-glass `revoke_credential`
is unaffected: `audit_query` never touches `control_requests_per_minute`
(`MitateDB-api/tests/test_audit_query.py::
test_audit_query_wire_calls_never_consume_the_control_requests_per_minute_
window`).

**Invariant 1 applies here too**: this window, like
`control_requests_per_minute`, is an in-process counter, so
`--max-instances=1` on `mitatedb-ctrl` (§6.2) is what keeps its declared
`enforced` status true.

### 3.2d Cloud SQL capacity thresholds (row size x row count x M)

**Row size.** `0005`'s per-column `length` CHECKs cap the eleven bounded text
columns at `64 + 256 + 256 + 64 + 256 + 64 + 64 + 64 + 32 + 128 + 256 =
1504` characters in total; adding `event_id`, the two timestamps, `count`,
`audit_seq` and per-tuple overhead, **budget 2 KiB as a hard per-row upper
bound**. No application input can exceed it -- the CHECK rejects the INSERT
(`MitateDB-api/tests/test_application_audit.py::test_api_role_cannot_insert_
a_value_longer_than_the_length_check`).

**Row count per instance.**

| source | bound per instance |
|---|---|
| fail-closed operations | 1 row per user operation (+1 `error` row if the data commit fails) |
| coalesced denials | **2** rows per coalescing key per 60s window -- first synchronous row + window-end aggregate row; never 1 |
| buffered ordinary successes | at most `MITATEDB_AUDIT_BUFFER_CAPACITY` (default 1000) in flight |
| buffer-overflow alerts | at most 1 row per flush interval (`MITATEDB_AUDIT_FLUSH_INTERVAL_S`) |

**Multiply by M.** Coalescing counters and the buffer are **process-local**,
so deployment-wide the ceilings are `2 x <keys> x <windows> x M` and
`<buffer capacity> x M`, where **M is `mitatedb-data`'s own
`--max-instances`**. Note the asymmetry with the control service: `mitatedb-
ctrl` is pinned to `--max-instances=1` by Invariant 1, but `mitatedb-data`
is not, so **M here is the data service's scaler maximum**, and that number,
not the per-process default, belongs in the arithmetic.

```
bytes/hour  ~=  2 KiB * M * ( <ops/hour>
                            + 2 * <distinct denial keys> * 60
                            + 3600 / <flush interval seconds> )
```

Alert on **growth rate**, not absolute size (absolute size is a retention
decision, §3.2e):

```sql
-- as mitatedbsvc_provision (schema owner); sample periodically, alert on delta
SELECT pg_total_relation_size('mitatedb_registry.application_audit') AS application_audit_bytes,
       pg_total_relation_size('mitatedb_registry.control_audit')     AS control_audit_bytes;
```

This matters beyond housekeeping: `mitatedb_platform` also holds the
credential store for **every** application, so filling the instance's disk
stops authentication platform-wide -- the availability side of SI-00, and the
reason the row-size and row-count bounds exist at all. On Cloud SQL, pair the
query above with the instance's own storage-utilization metric and keep
automatic storage increase enabled.

**The five fixed alert messages.** The audit pipeline emits exactly five
`logging.error` messages, all fixed strings with **no interpolation** (no
client-supplied value can reach Cloud Logging through them). They are
defined in one place, `src/mitatedb_api/audit_dispatch.py` (the three
buffer/alert messages at L82-84, the two coalescing messages at L85-86,
emitted from `_note_aggregate_write_result`, L438). Build a logs-based
metric/alert on exact-string match for **each of the five** -- they are two
independent evidence-loss channels, and alerting on only the first three
leaves the coalescing channel silent:

| message (exact) | meaning |
|---|---|
| `application_audit buffer overflow: events were dropped` | evidence loss has ALREADY happened: the bounded buffer evicted its oldest events |
| `application_audit overflow-alert row could not be written; retrying with backoff` | the in-band alert row itself cannot be written -- both channels failing at once; retry is sticky with exponential backoff to a 60s ceiling |
| `application_audit overflow-alert row recorded; pending overflow cleared` | recovery of the pair above: the alert row landed and the accumulated drop count is in its `count` |
| `application_audit coalesced-denial summary row could not be written; retrying` | the window-end aggregate row of a coalesced denial is not landing. The first, synchronous row of that window IS durable, but the **repeat count is stranded in memory** -- and because the writer holds INSERT only, that first row's `count` can never be amended later (§3.2d, design P4-D6). That row is the only carrier of "how many times", so a stuck aggregate row is evidence loss even though nothing is refused |
| `application_audit coalesced-denial summary row recorded; retry cleared` | recovery of the pair above: the aggregate row landed and the stranded repeat count is now in its `count` |

Both retrying/recovered pairs fire only on a failing<->healthy **state
transition** (never once per attempt), the same logging-DoS discipline the
overflow alert uses.

**Known sharpness, both peers (P4-D15, WP-B2, 2026-09-03)**: the flush
"failing" flag clears on ANY successful flush, regardless of how much the
buffer still holds -- it is not gated on the buffer fully draining, as an
earlier revision had it. Completion-order semantics govern concurrent
flushes (periodic, threshold, and explicit can all race on the same buffer):
whichever attempt COMPLETES LAST decides the flag's value, so a still-failing
concurrent flush that completes after a successful one sets the flag back to
failing. If the sink is FLAPPING (success and failure completing
alternately), the alert re-fire interval can rise from the 60s backoff
ceiling up to one row per flush interval -- this is an accepted tradeoff, not
a defect: the declared bound of at most one alert row per flush interval
still holds regardless (the `alert_min_interval_s` floor rate-limits every
attempt independently of this flag), evidence reaches the durable table
sooner from a partially-working sink, and no evidence is ever lost either way
(the drop counter keeps accumulating and is reported in the eventual alert
row's `count`). As before, **do not read a gap between messages as
recovery** -- read the recovery message of the pair concerned (the third
message for the buffer/overflow channel, the fifth for the coalescing one).

### 3.2e Retention and pruning (manual, external, deliberately unautomated)

Nothing in `mitatedb_api` ever deletes an audit row, and no process role can:
`mitatedbsvc_api` has INSERT only, `mitatedbsvc_controlplane` has INSERT on
`control_audit` only, `mitatedbsvc_auditreader` has SELECT only. Pruning is a
**schema-owner (`mitatedbsvc_provision`) operation performed by an
operator** -- the contract's `audit.immutability` "externally governed where
required by the deployment" shape (design D-11/§10: automatic pruning is
explicitly out of scope, not merely unimplemented).

Step 1 -- **EXPORT the window first; step 3 is irreversible.** There is no
CLI reader for `application_audit` (§3.2f: `python -m mitatedb_api.ops
audit-report` reads `control_audit` ONLY, and needs `MITATEDB_PROVISION_DSN`
-- the schema owner, not `mitatedbsvc_auditreader` and not the control-plane
role, which is INSERT-only on that table). Export this table directly, as
`mitatedbsvc_auditreader` (`MITATEDB_AUDIT_DSN`) or as the schema owner:

```
psql "$MITATEDB_AUDIT_DSN" -c "\copy (SELECT * FROM mitatedb_registry.application_audit \
  WHERE recorded_at < now() - interval '365 days' ORDER BY recorded_at, event_id) \
  TO '<export path>' WITH (FORMAT csv, HEADER)"
```

Store the export wherever the retention policy says evidence lives, and
verify it is readable before continuing. When the table being pruned is
`control_audit` instead, `python -m mitatedb_api.ops audit-report --since ...
--until ...` (over `MITATEDB_PROVISION_DSN`) is the supported export for that
one.

```sql
-- 2. As mitatedbsvc_provision: confirm the blast radius.
SELECT count(*), min(recorded_at), max(recorded_at)
  FROM mitatedb_registry.application_audit
 WHERE recorded_at < now() - interval '365 days';

-- 3. As mitatedbsvc_provision: delete that same window.
DELETE FROM mitatedb_registry.application_audit
 WHERE recorded_at < now() - interval '365 days';
```

The identical three steps apply to `mitatedb_registry.control_audit` with its
own period. Record what was pruned, when, and by whom -- after the DELETE the
table no longer evidences it.

### 3.2f Reading evidence while Cloud SQL is unavailable

`audit_query`, the credential store, and both audit tables live in ONE
database. If `mitatedb_platform` is unreachable, `mitatedb-data` already
fails at authentication (true before phase 4 -- the durable sink adds no new
single point of failure) and `audit_query` cannot answer either: **evidence
is unreadable at exactly the moment it is most wanted.**

The one read path that does not depend on the control HTTP app, the reader
role, or `audit_query` is the out-of-band CLI, `python -m mitatedb_api.ops
audit-report` (§7), which SELECTs directly over **`MITATEDB_PROVISION_DSN`**
(the schema owner -- `mitatedbsvc_controlplane` is INSERT-only on that table
and cannot read it back, and `mitatedbsvc_auditreader` is not what this
command uses). Keep it and its credentials available to operators; it is not
made redundant by `audit_query`. **Be precise about its scope: `audit-report`
reads `control_audit` only.** There
is no CLI reader for `application_audit`; the equivalent out-of-band access
is a direct `psql` session as `mitatedbsvc_auditreader` (or as the schema
owner `mitatedbsvc_provision`):

```sql
SELECT recorded_at, event_class, request_id, application_id, actor_id,
       operation, target_kind, outcome, reason_code, count
  FROM mitatedb_registry.application_audit
 WHERE recorded_at >= now() - interval '1 hour'
 ORDER BY recorded_at, event_id;
```

All of these -- the CLI included -- still require the Cloud SQL instance
itself to be reachable. What they remove is the dependency on `mitatedb-ctrl`
being up and on `audit_query` being declared `enabled`, not the dependency on
the database. There is deliberately no second copy of the evidence anywhere
(external SIEM forwarding is out of scope for this phase, design §10); if a
deployment needs evidence to survive the database being down, that is an
export decision it must make for itself under §3.2e.

### 3.3 Invariant 2 -- application roles are NEVER created via the Users API/Console

**Invariant 2 (design R-1 second-round M-8): every application role
(`mitatedbsvc_api`, `mitatedbsvc_controlplane`, and every per-application
runtime/developer role migration `0003` creates) MUST be created only by
running the migration SQL above/below as `mitatedbsvc_provision` -- never
via `gcloud sql users create`, never via the Cloud SQL Console's "Users"
tab.** Cloud SQL's own Users API/Console path makes every role it creates
a member of `cloudsqlsuperuser`, which can `CONNECT` to *any* database on
the instance regardless of `REVOKE CONNECT ... FROM PUBLIC` (migration
`0002`'s own containment wall) -- defeating the database-per-application
boundary R-1 is built on. Migration `0002`'s own `assert_role_has_no_
memberships` function (called by `begin_provision_application`,
`0002_registry_and_functions.sql` lines ~443-450) is the fail-closed
backstop that catches this if it ever happens by mistake: it aborts
provisioning if the role it just created (or a pre-existing role reused
under the same name) has ANY `pg_auth_members` row or any of
`rolsuper`/`rolcreatedb`/`rolcreaterole`/`rolinherit` set. Verifying this
backstop against your own Cloud SQL instance is part of §9 below.

### 3.4 Application provisioning (migrations `0003`/`0004`, per application)

Run once per application being onboarded, after that application has
already been `register_application`-ed in-band (`/control/v1`) or via the
break-glass CLI's own reach (registration alone leaves `database_name`
NULL -- the two-state registry, design R-4):

```sh
psql "host=127.0.0.1 port=5432 dbname=mitatedb_platform user=mitatedbsvc_provision password=$MITATEDBSVC_PROVISION_PASSWORD" \
  -v app_id='acme' \
  -v runtime_password="$(openssl rand -base64 32)" \
  -v developer_password="$(openssl rand -base64 32)" \
  -f MitateDB-api/migrations/0003_provision_application.sql
```

Record both generated passwords in Secret Manager as
`MITATEDB_APP_ACME_RUNTIME_DSN`/`MITATEDB_APP_ACME_DEVELOPER_DSN`-shaped
secrets (§4) -- this script never re-displays them, and nothing else in
this system can recover them (they are stored only as password hashes
inside PostgreSQL's own role catalog, which nothing in this codebase ever
reads back).

`0004_deprovision_application.sql` reverses this (drops the database and
both roles) -- run directly via `psql` the same way, or via the
break-glass CLI's own `deprovision` subcommand (§7).

### 3.4a Declared-type registry upgrade for existing applications (migration `0006`, Phase 6 WP-3)

Contract 1.6.0 (design `docs/design/PHASE6_CONTRACT_160_CLIENT_DISCOVERY_
V1.md` D-3) requires every field this peer serves to carry a real,
declared type (`GET /v1/catalog`, `application_catalog: enabled`). A
freshly `0003`-provisioned application already carries the registry table
this needs (`public._mdb_field_types`) -- this step is for **applications
provisioned before this WP shipped**.

Run once per EXISTING application, connected as `mitatedbsvc_provision`:

```sh
psql "host=127.0.0.1 port=5432 dbname=mitatedb_platform user=mitatedbsvc_provision password=$MITATEDBSVC_PROVISION_PASSWORD" \
  -v app_id='acme' \
  -f MitateDB-api/migrations/0006_declared_field_types_upgrade.sql
```

This creates `public._mdb_field_types` in that application's own database
(idempotent -- a no-op if the table already exists) and backfills one row
per existing column from its own PHYSICAL type:

| Physical type (this application's own table) | Backfilled contract type |
|---|---|
| `bigint` | `integer` |
| `double precision` | `number` |
| `integer` | `boolean` |
| `text` | `string` |

**Known limitation, disclosed (not resolved) by this script**: a physical
`text` column is ambiguous on this backend -- it may have been declared
`string` (the common case), or `object`/`array` (an `add_field` call
naming either word was already valid before contract 1.6.0). PostgreSQL's
own catalog cannot recover which of the two a column was originally
declared as, so this script backfills every physical `text` column as
`string`. If this application has an `add_field`-created `object`/`array`
column, correct that one row by hand after running this script:

```sql
UPDATE public._mdb_field_types SET declared_type = 'object'
  WHERE entity = '<entity>' AND field = '<field>';
```

Re-running the migration script is always safe (it never overwrites an
existing row, hand-corrected or not).

**Run this before flipping that application's own data service image to a
contract-1.6.0 build** -- `GET /v1/catalog`/every structured write goes
through the same registry the moment the new image starts, and an entity
this script has not yet reached simply has no rows there until it is run
(a schema operation issued through the new image writes its own registry
row automatically; only PRE-EXISTING columns need this backfill).

### 3.4b Per-application platform-upgrade ledger and bulk apply (migration `0008`, Q4 phase WP-4)

Design `docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md` D-3/D-4/D-5 (work order
`docs/work-orders/WORK_ORDER_Q4_DB_SIDE_SINGLE_TRUTH_V1.md` §4 WP-4):
every application database now carries its own ledger table
(`public._mdb_platform_upgrades`) recording which of this package's
per-application upgrade scripts (`0006_declared_field_types_upgrade.sql`,
`0008_platform_upgrades_upgrade.sql`, and any later one this package
ships) it has already had applied. A freshly `0003`-provisioned
application already carries this table, seeded with every number this
package currently ships (`{6, 8}`) -- this step is for **applications
provisioned before this WP shipped**, exactly like §3.4a above.

**Data-plane enforcement (no operator action, disclosed for context)**:
starting with this WP, a served application whose own ledger is missing
one or more of these numbers (including an application whose ledger table
does not exist at all) refuses every request with `SERVICE_UNAVAILABLE`
the moment the data-plane process opens that application's own storage
boundary -- the response names the missing upgrade number(s) and the
`ops upgrade-applications` command below. **This does not stop the
data-plane process from starting, and it does not affect any OTHER served
application** (supervisor ruling 2026-09-05, review H-1): the process
starts normally, every other served application's own cell serves exactly
as before, and only the affected application's own cell refuses -- every
request against it -- until `ops upgrade-applications` is run and the
process is restarted. Do not wait for a client report of this to notice a
missed upgrade; use `ops upgrade-status` (below) as part of every
deploy's own pre-flight, the same way `ops show-declarations` already is
(§3.2b).

**Bulk-apply every pending upgrade across every provisioned application**
(provision DSN only -- never a control credential, SI-02):

```sh
# Preview first -- applies nothing, reports applied/pending per application.
python -m mitatedb_api.ops upgrade-applications --dry-run

# Apply. Visits every application; a failure on one does not stop the rest
# -- failed applications are listed at the end, each with a REVOKE cleanup
# line (see below).
python -m mitatedb_api.ops upgrade-applications
```

`--application <id>` limits either form to one application.
`enabled` does **not** affect which applications are targeted -- a
disabled application's own database is still brought current, so
re-enabling it later never surfaces a stale ledger.

Exit codes: `0` nothing pending, `1` enumeration failed (registry/provision
DSN unreachable), `2` usage error, `3` at least one application failed to
apply (see cleanup below), `4` (`--dry-run` only) at least one application
still has a pending upgrade.

**If an application fails to apply**: the per-application upgrade script's
own ritual grants `mitatedbsvc_provision` a *temporary* membership in that
application's own developer role, revoked explicitly at the end of a
successful run -- a failed run never reaches that closing `REVOKE`, so the
output for a failed application includes the exact statement to run by
hand to close it out:

```sql
REVOKE "<app>_dv" FROM "mitatedbsvc_provision";
```

Run this (issued on the provision DSN) after diagnosing and fixing
whatever caused the failure, then re-run `ops upgrade-applications` for
that application.

**Read-only status** (provision DSN only, no application is ever
modified):

```sh
python -m mitatedb_api.ops upgrade-status
python -m mitatedb_api.ops upgrade-status --application acme
```

Reports `applied`/`pending`/`database_name` per application (an
application with no ledger table at all reports `applied: []`). Exit
codes `0`/`4` mirror `upgrade-applications --dry-run`; this command never
writes anything, so `1`/`2` are its only other possible outcomes. This is
the **sole** peer-local visualization of per-application upgrade state
(design `docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md` §5 U-1, requester
ruling 2026-09-05) -- it is never exposed on any HTTP surface, and
`list-applications` (§7) is unchanged (still the contract-shaped
`ApplicationsResult`, no upgrade-state column added).

**Recovery from an F-12 refusal**, start to finish (the r2db peer's own
`POSTGRES_PROVISIONING_RUNBOOK.md` §17 states the same five steps):

1. `python -m mitatedb_api.ops upgrade-status --application <id>` -- confirm
   which numbers are pending (exit `4` means at least one is).
2. `python -m mitatedb_api.ops upgrade-applications --application <id>
   --dry-run`, then the same command without `--dry-run`.
3. If it exits `3`, read that application's failure block: fix the cause,
   issue the printed `REVOKE`, re-run step 2.
4. **Redeploy or restart the data service** (`gcloud run services update
   mitatedb-data ...`, or any new revision) -- the ledger check is a
   cell-open snapshot, so the refusing cell keeps refusing until the process
   opens that application's storage boundary again.
5. Re-check with an ordinary request against that application, and with
   `ops upgrade-status` (expect exit `0`).

**`--script <NNNN>` danger, disclosed** (design D-4(f)): this flag applies
one specific script only to databases that have not yet recorded it --
never to one that already has (`recorded, skipped`, still counted a
success). This is the **only** thing standing between `--script 6` and
data corruption: `0006`'s own backfill scans every column not named
`_mdb_schema_revision`/`_mdb_field_types` and inserts a declared-type row
per column found -- run a second time against a database that already
carries `public._mdb_platform_upgrades`, it would misinterpret that
table's own three columns as application data and corrupt `_mdb_field_
types` with three bogus rows. `0006` is already shipped and cannot be
revised in place; never invoke it by any means other than `ops
upgrade-applications` (with or without `--script 6`) once this WP has
shipped.

## 4. Secret Manager

Six secret families, none of which is ever committed to this repository or
baked into the container image:

| Secret Manager name (example) | Contents | Consumed by |
|---|---|---|
| `mitatedb-credential-pepper` | `MITATEDB_CREDENTIAL_PEPPER` value | data service, control service (pepper-separation check only), `ops.py` |
| `mitatedb-control-credential-pepper` | `MITATEDB_CONTROL_CREDENTIAL_PEPPER` value | control service, `ops.py` |
| `mitatedb-platform-dsn` | `MITATEDB_PLATFORM_DSN` (`mitatedbsvc_api`, unix-socket form, §5) | data service |
| `mitatedb-controlplane-dsn` | `MITATEDB_CONTROLPLANE_DSN` (`mitatedbsvc_controlplane`, unix-socket form) | control service, `ops.py` |
| `mitatedb-provision-dsn` | `MITATEDB_PROVISION_DSN` (`mitatedbsvc_provision`) | **operator/break-glass CLI only -- never a Cloud Run service** (§7) |
| `mitatedb-app-<id>-{runtime,developer}-dsn` | per-application DSNs, one pair per onboarded application | data service (`MITATEDB_APP_<ID_UPPER>_{RUNTIME,DEVELOPER}_DSN`) |

**The two peppers must be genuinely different values** -- both composition
roots (`mitatedb_api.main.build_app`, `mitatedb_api.control_composition.
build_control_service`) call `assert_pepper_separation` at startup and
refuse to start if they are equal (R-2's pepper-separation rule; catches an
operator who copy-pasted the same Secret Manager value into both secret
names).

```sh
printf '%s' "$(openssl rand -base64 48)" | gcloud secrets create mitatedb-credential-pepper --data-file=-
printf '%s' "$(openssl rand -base64 48)" | gcloud secrets create mitatedb-control-credential-pepper --data-file=-
```

Grant each Cloud Run service's own runtime service account `roles/
secretmanager.secretAccessor` on exactly the secrets that service needs --
the data service must never be able to read `mitatedb-controlplane-dsn` or
`mitatedb-provision-dsn`, and the control service must never be able to
read `mitatedb-provision-dsn` (R-4's process-role separation, restated at
the IAM layer: least privilege applies to who can even READ the DSN, not
only to what the DSN's own PostgreSQL role can do once connected).

## 5. Cloud SQL connection (unix socket DSN)

Cloud Run's built-in Cloud SQL connection mounts a unix socket at
`/cloudsql/<INSTANCE_CONNECTION_NAME>` -- no Cloud SQL Auth Proxy sidecar
needed inside the container itself (the platform provides the equivalent
tunnel). A DSN of this form is what every `MITATEDB_*_DSN` secret above
should contain:

```
host=/cloudsql/example-project:us-central1:mitatedb-platform port=5432 dbname=mitatedb_platform user=mitatedbsvc_api password=<from Secret Manager> sslmode=disable
```

(`sslmode=disable` is correct and safe specifically for the unix-socket
path -- the socket never leaves the Cloud Run sandbox's own loopback
namespace; a TCP DSN to a public IP would need `sslmode=verify-full`
instead, which this runbook's `--no-assign-ip` instance does not need at
all.) `psycopg.connect(dsn)` (every composition root in this codebase)
accepts this form unmodified -- no code change, no Cloud SQL Connector
library dependency (design R-9: "IAM DB 認証・Cloud SQL Connector の採否は
現行: 標準 DSN + Secret Manager 参照" -- the future-work register, §7 of
the design doc, tracks IAM DB auth as a later strengthening, not this
WP's scope).

## 6. Two Cloud Run services

**Build the image from the repository root, naming the Dockerfile
explicitly** (not from inside `MitateDB-api/` the way a package-local
Dockerfile normally would be): `docker/Dockerfile`'s builder stage `COPY`s
`MitateDB-api/pyproject.toml` and `MitateDB-api/src` using paths relative
to the REPOSITORY ROOT, so the build context must be the repository root
regardless. The common contract itself no longer needs any special
handling at image-build time (Phase 6 WP-0): `mitatedb_api.http` (and
`control_http.py`, which imports from it) load it via `importlib.
resources` from a packaged copy shipped inside the wheel this builder
stage's own `pip install .` already produces
(`mitatedb_api/contract/data-service-api.v1.json`, wired in as package
data, `pyproject.toml`'s own `[tool.setuptools.package-data]`) -- no
runtime-stage `COPY spec/...` and no filesystem-layout arithmetic (see
that Dockerfile's own CONTRACT PACKAGING note):

```sh
docker build -f MitateDB-api/docker/Dockerfile \
  --build-arg SERVICE=data \
  -t us-central1-docker.pkg.dev/example-project/mitatedb/mitatedb-api:SERVICE_data \
  .
docker push us-central1-docker.pkg.dev/example-project/mitatedb/mitatedb-api:SERVICE_data
```

Repeat with `--build-arg SERVICE=control` and a `SERVICE_control` tag for
the control service's own image (§6.2). Both `gcloud run deploy` commands
below then reference the tag already pushed here via `--image=`.

**Grant each runtime service account `roles/cloudsql.client` before
deploying** (2026-09-01, operator-measured first-deployment finding):
`--add-cloudsql-instances` wires up Cloud Run's built-in Cloud SQL
connector, but the connector itself calls the Cloud SQL Admin API
(`cloudsql.instances.get`) as the service account named by
`--service-account` to resolve the instance's connection metadata --
without `roles/cloudsql.client` on that service account, the connector
fails closed with a `403` on `cloudsql.instances.get` before the container
ever gets a chance to open a DSN connection at all (a distinct failure from
any PostgreSQL-level auth/grant problem, and one that surfaces as a
container startup/connector error, not an application error). Grant it to
BOTH runtime service accounts (data and control) before running either
`gcloud run deploy` below:

```sh
gcloud projects add-iam-policy-binding example-project \
  --member=serviceAccount:mitatedb-data-runtime@example-project.iam.gserviceaccount.com \
  --role=roles/cloudsql.client
gcloud projects add-iam-policy-binding example-project \
  --member=serviceAccount:mitatedb-ctrl-runtime@example-project.iam.gserviceaccount.com \
  --role=roles/cloudsql.client
```

### 6.1 Data service (`mitatedb-data`)

```sh
gcloud run deploy mitatedb-data \
  --project=example-project --region=us-central1 \
  --image=us-central1-docker.pkg.dev/example-project/mitatedb/mitatedb-api:SERVICE_data \
  --add-cloudsql-instances=example-project:us-central1:mitatedb-platform \
  --service-account=mitatedb-data-runtime@example-project.iam.gserviceaccount.com \
  --no-allow-unauthenticated \
  --set-secrets=MITATEDB_CREDENTIAL_PEPPER=mitatedb-credential-pepper:latest,MITATEDB_PLATFORM_DSN=mitatedb-platform-dsn:latest \
  --set-env-vars=MITATEDB_SERVE_APPS=acme,MITATEDB_CONTROL_PLANE_STATUS=enabled
# ... plus one --set-secrets pair per onboarded application's own
# MITATEDB_APP_<ID_UPPER>_{RUNTIME,DEVELOPER}_DSN.
```

**Q4 phase (design D-2) supersedes `MITATEDB_DATA_BASE_URL`/
`MITATEDB_CONTROL_BASE_URL` as env vars** -- they are now **removed**
(defined at all, even empty, fails startup loudly, F-2). `surfaces` is
declared ONCE, in the platform database, and read by BOTH Cloud Run
services at startup (§3.2b above already covers applying migration
`0007_platform_declarations.sql` and running `ops declare-surfaces`) --
never set as a per-service env var on either `gcloud run deploy` command.
Declare it (or re-declare it, once this deployment's real Cloud Run URLs
are known) with:

```sh
python -m mitatedb_api.ops declare-surfaces \
  --data-base-url https://mitatedb-data.example.invalid/v1 \
  --control-base-url https://mitatedb-ctrl.example.invalid/control/v1
```

`--data-base-url` must end at `/v1` (no trailing slash); `--control-base-
url` must end at `/control/v1` (no trailing slash) -- both checked on
write AND on every read (form only, never reachability; design D-2(d)).
Both services reading the SAME row is now **structural, once they are
both actually pointed at the same platform database** -- not a deployer
discipline to remember for the row's OWN content any more (design's own
former "nothing in either process can detect a mismatched pair by
itself" gap this replaces) -- `surfaces.control`'s presence in that row
is additionally cross-checked against each process' own `MITATEDB_
CONTROL_PLANE_STATUS` at startup (F-6): the data service refuses to
start if the row declares `control` while this service itself declares
`unavailable`, or vice versa. **This does not close the OUTER gap**
(design §3.11 point 7): neither process knows the other's own `MITATEDB_
PLATFORM_DSN`/`MITATEDB_CONTROLPLANE_DSN`, so if the two Cloud Run
services are ever given DSNs pointing at two DIFFERENT platform
databases (a stale secret-manager value on one side, say), each reads
its OWN row consistently but the two rows can still disagree -- this
remains a deployer responsibility, verified only by the post-deploy
`/capabilities` cross-check both surfaces already receive (§6.3 below),
never by either process itself. Replace the two example `https://...
example.invalid` values above with this deployment's own real Cloud Run
service URLs (`gcloud run services describe ... --format='value
(status.url)'`) before going live, then restart BOTH services (design
U-3: startup snapshot).

Invoker binding: **only `mitate-application`'s own service account**, never
`allUsers` and never a broad project role:

```sh
gcloud run services add-iam-policy-binding mitatedb-data \
  --project=example-project --region=us-central1 \
  --member=serviceAccount:mitate-application@example-project.iam.gserviceaccount.com \
  --role=roles/run.invoker
```

### 6.2 Control service (`mitatedb-ctrl`)

```sh
gcloud run deploy mitatedb-ctrl \
  --project=example-project --region=us-central1 \
  --image=us-central1-docker.pkg.dev/example-project/mitatedb/mitatedb-api:SERVICE_control \
  --add-cloudsql-instances=example-project:us-central1:mitatedb-platform \
  --service-account=mitatedb-ctrl-runtime@example-project.iam.gserviceaccount.com \
  --no-allow-unauthenticated \
  --max-instances=1 \
  --set-secrets=MITATEDB_CREDENTIAL_PEPPER=mitatedb-credential-pepper:latest,MITATEDB_CONTROL_CREDENTIAL_PEPPER=mitatedb-control-credential-pepper:latest,MITATEDB_CONTROLPLANE_DSN=mitatedb-controlplane-dsn:latest,MITATEDB_AUDIT_DSN=mitatedb-audit-dsn:latest
```

No `surfaces`-related env var on this command either (Q4 phase, design
D-2) -- `control_composition.build_control_service` reads the SAME
`platform_declarations` row §6.1 above declares (`control_composition.
build_control_service` fails closed at startup if that row is absent, or
if it has no `control` entry -- this composition root always requires a
control surface unconditionally, unlike the data service's own
status-conditional check, F-3c). There is nothing to keep "the SAME
value as §6.1" by deployer discipline any more, **as long as
`MITATEDB_CONTROLPLANE_DSN` on this service and `MITATEDB_PLATFORM_DSN`
on §6.1's service name the same platform database** -- neither process
verifies that of the other (design §3.11 point 7; the same limitation
§6.1 above states, restated here because this command is the other half
of the pair it applies to).

`MITATEDB_AUDIT_DSN` (Phase 4 WP-3(b), §3.2b above) is optional -- omit the
`--set-secrets` entry entirely to leave `audit_query` declared
`unavailable` on this deployment.

**Invariant 1 (design R-6 second-round M-7, D-K): `--max-instances=1` is
not a scaling convenience, it is a correctness requirement.**
`ControlPlaneService`'s own `control_requests_per_minute` rate limiter is
an in-process window (`control_plane.py`'s own `_rate_window` list) -- with
more than one instance, each instance would enforce the bound
independently, so the control-discovery response's own `limit_enforcement:
{control_requests_per_minute: "enforced"}` claim (contract `capability_
status.rules`) would become false under real concurrent scale-out. A
shared window (Redis, Cloud SQL-backed, or `deployment_required`
re-declaration) is future-work (§7 of the design doc, D-K) -- until that
lands, `max-instances=1` is the only way this declaration stays true, and
removing this flag without also doing that future work is a silent
regression to a false claim, not merely a capacity change.

Invoker binding: operators only (a Google group, never `allUsers`, never
the broad application service account):

```sh
gcloud run services add-iam-policy-binding mitatedb-ctrl \
  --project=example-project --region=us-central1 \
  --member=group:mitatedb-operators@example.internal \
  --role=roles/run.invoker
```

### 6.3 Calling the control service over HTTP: Cloud Run IAM vs. the control credential

`mitatedb-ctrl` is deployed `--no-allow-unauthenticated` (§6.2): Cloud Run's
own front end requires a caller-supplied Google ID token before the request
ever reaches this container, checked against the `roles/run.invoker`
binding (§6.2's own operator-group binding). Separately, every
`/control/v1/*` handler (and its `/v1/audit/query` alias, §0) requires a
control credential, carried the same way an application credential is on
the data service: `Authorization: Bearer <credential_id>.<secret>`
(`control_http.py`'s own `_bearer_pair`, which reuses `_extract_bearer`
from `http.py` unchanged). Both checks want the SAME header. Neither §6.2
above nor `docs/work-orders/DEPLOY_PHASE4_20260903.md` previously said how
an operator reconciles that collision; this section does.

**Two paths, chosen by who the caller is -- not interchangeable defaults.**

- **Interactive operator (a human, a user account) -- default:
  `gcloud run services proxy`.** `gcloud run services proxy mitatedb-ctrl
  --project=example-project --region=us-central1 --port=8443` starts a
  local proxy that authenticates to Cloud Run using the operator's own
  `gcloud` user-account credentials and handles the IAM layer itself; the
  operator's own request to the local proxy needs only the application's
  own `Authorization: Bearer <credential_id>.<secret>` header --
  `curl -sk -H "Authorization: Bearer <control credential id>.<control credential secret>" http://127.0.0.1:8443/control/v1/capabilities`
  is enough. No ID token to mint by hand, nothing extra to construct. Use
  this for a person at a terminal.

- **Service account (automation: CI/CD, a scheduled audit-polling agent)
  -- `X-Serverless-Authorization`.** Cloud Run also accepts the caller's
  Google ID token in an `X-Serverless-Authorization: Bearer <ID token>`
  header; when present, Cloud Run's own front end authenticates the
  request against that header and passes the token through to the
  container with its signature removed (Cloud Run's own documented
  behavior: "This removes the signature before passing the token to the
  user container" -- it does not strip the header outright). This is
  Cloud Run's own accommodation for an application that already uses
  `Authorization` for its own purposes, and it is the path for a caller
  that cannot run a local proxy: put the control credential in
  `Authorization` and the ID token in `X-Serverless-Authorization`.

  ```sh
  curl -sk \
    -H "Authorization: Bearer <control credential id>.<control credential secret>" \
    -H "X-Serverless-Authorization: Bearer $(gcloud auth print-identity-token --audiences=<mitatedb-ctrl Cloud Run URL>)" \
    <mitatedb-ctrl Cloud Run URL>/control/v1/capabilities
  ```

  **Unverified on real infrastructure -- check before relying on this in
  automation.** There are reports that `gcloud auth print-identity-token
  --audiences=<url>` is refused for a user-account principal and only
  succeeds for a service account; this runbook has not exercised that call
  against a real `mitatedb-ctrl` deployment either way, so both
  possibilities are recorded here rather than asserted. If it is refused
  for your caller, mint the ID token another way appropriate to that
  principal type, or fall back to the `gcloud run services proxy` path
  above (which needs no `--audiences` at all and is the recommended
  default for exactly this reason).

(No secret value belongs in this document -- `<control credential id>`,
`<control credential secret>`, and `<mitatedb-ctrl Cloud Run URL>` are
placeholders, filled in only at the caller's own terminal or automation
config, never here. The caller -- human or service account -- must be a
principal named in the `roles/run.invoker` binding of §6.2.)

**The application never treats the IAM layer as a credential.**
`control_http.py`'s own `_bearer_pair` (`control_http.py:148-157`) calls
`_extract_bearer`, defined once in `http.py:344-351` and reused unchanged
by both services; it reads `request.headers.get("authorization")` only --
no code in this repository reads `X-Serverless-Authorization` at all, so it
makes no difference to the application that Cloud Run forwards a
signature-stripped copy of the ID token in that header on the
`X-Serverless-Authorization` path above -- nothing here looks at it either
way. The IAM check (Cloud Run's front end, against the `roles/run.invoker`
binding) and the control-credential check (`ControlPlaneService.
authenticate`, inside the container) are therefore two independent layers,
verified by two different parties over two different headers -- the
credential the container asserts against is never the same secret Cloud Run
used to admit the connection.

**Verification calls used after deployment**
(`docs/work-orders/DEPLOY_PHASE4_20260903.md` §4 -- endpoint and expected
shape only, no real values; shown on the `X-Serverless-Authorization` path,
substitute the `gcloud run services proxy` path above if calling
interactively):

```sh
# capabilities declaration (§4-1/§4-2). Phase 6 WP-3 (design D-1(d)):
# <control credential secret> is the EXACT value `ops.py`'s own `secret:`
# line printed -- present it verbatim as the bearer; never split it apart
# or reassemble it from a separately-remembered credential id.
curl -sk \
  -H "Authorization: Bearer <control credential secret>" \
  -H "X-Serverless-Authorization: Bearer $(gcloud auth print-identity-token --audiences=<mitatedb-ctrl Cloud Run URL>)" \
  <mitatedb-ctrl Cloud Run URL>/control/v1/capabilities
# expect 200; capabilities.audit_query.status == "enabled" if MITATEDB_AUDIT_DSN is
# wired (else "unavailable", not a failure -- §4-6); capabilities.contract_version == "1.6.0"
# (Phase 6 WP-3) and, when audit_query is "enabled", three non-empty declared
# vocabularies under capabilities.audit_query: event_classes, operations (29 words
# on this peer) and target_kinds (5). capabilities.surfaces.data/.control must both
# be present (§6.4/§0.1 invariant, contract 1.6.0 D-2) and must match the SAME
# object the data service's own capabilities response returns. An image built
# before contract 1.6.0 correctly declares an earlier version and carries neither
# new key -- that is conformant for THAT version, not a failure; what must never
# disagree is the image's version and its declaration (§3.2b).

# audit_query, cursor-paginated (§4-5)
curl -sk -X POST \
  -H "Authorization: Bearer <control credential id>.<control credential secret>" \
  -H "X-Serverless-Authorization: Bearer $(gcloud auth print-identity-token --audiences=<mitatedb-ctrl Cloud Run URL>)" \
  -H 'Content-Type: application/json' -d '{"limit": 5}' \
  <mitatedb-ctrl Cloud Run URL>/control/v1/audit/query
# expect 200; events[].cursor present; resume with {"after": "<last cursor>", "limit": 5}
# until an empty page comes back (len(events) < limit does not by itself mean "done")

# DSN unset -> CAPABILITY_UNSUPPORTED on BOTH the canonical path and the alias
# (DEPLOY_PHASE4 §4-6 requires checking both; a legacy edge rule scoped to
# only one prefix would leave the other one unchecked, §0's own warning)
curl -sk -X POST \
  -H "Authorization: Bearer <control credential id>.<control credential secret>" \
  -H "X-Serverless-Authorization: Bearer $(gcloud auth print-identity-token --audiences=<mitatedb-ctrl Cloud Run URL>)" \
  -H 'Content-Type: application/json' -d '{"limit": 5}' \
  <mitatedb-ctrl Cloud Run URL>/control/v1/audit/query
# expect HTTP 400 (not 404, not 200); error.code == "CAPABILITY_UNSUPPORTED"
# (control_http.py:71 -- CAPABILITY_UNSUPPORTED maps to 400; the route is
# registered and authenticates/authorizes before this check ever runs)

curl -sk -X POST \
  -H "Authorization: Bearer <control credential id>.<control credential secret>" \
  -H "X-Serverless-Authorization: Bearer $(gcloud auth print-identity-token --audiences=<mitatedb-ctrl Cloud Run URL>)" \
  -H 'Content-Type: application/json' -d '{"limit": 5}' \
  <mitatedb-ctrl Cloud Run URL>/v1/audit/query
# expect the SAME on the alias: HTTP 400, error.code == "CAPABILITY_UNSUPPORTED"
```

**Ordering note (§0.1 invariant 3).** Only flip the data service's
`MITATEDB_CONTROL_PLANE_STATUS` to `enabled` (§3(c) step 6 of the deploy
work order) *after* `mitatedb-ctrl`'s capabilities have actually been
fetched successfully through one of the two paths above -- that response is
the confirmation that the control service is reachable at all. Flipping the
env var first asserts a control plane the operator has not yet observed to
be up, which is exactly the false declaration invariant 3 exists to
prevent.

### 6.4 Phase 6 WP-3 cutover: 3 observable behavior changes (contract 1.6.0)

Flipping a deployment's `contract_version` declaration to `1.6.0` (§0.1
invariant 3's own ordering discipline applies here too: flip the
declaration only once the underlying behavior is already live, same
commit) brings 3 real, observable behavior changes alongside the
additive contract itself (design `PHASE6_CONTRACT_160_CLIENT_DISCOVERY_
V1.md` §8 item 4, `spec/CCR_DISPOSITION.md` subordinate ruling 11's own
additive-性 argument for why none of the three is a contract break):

- **(α) undeclared field default, `text` -> `json`**: a `create_entity`
  field named without an explicit `field_types` entry used to be created
  as this peer's own `text` type (plain strings only); it is now created
  `json` (any JSON value). This WIDENS what such a field accepts -- an
  existing write that used to succeed still succeeds. Existing entities
  created before this cutover are unaffected (their columns already
  exist; this only changes what a NEW, undeclared field defaults to).
- **(β) `json`/`object`/`array`-declared read shape**: reading a field
  declared `json`, `object`, or `array` now returns the actual JSON value
  (an object, array, string, number, boolean, or `null`) instead of a
  JSON-text STRING a caller previously had to `json.loads()` a second
  time. A client that keeps calling `json.loads()` on such a field's own
  response value after this cutover gets a `TypeError` (the value is no
  longer a string) -- update any such client before (or in the same
  release as) flipping this deployment's image.
- **(γ) `boolean`-declared wire representation**: a field declared
  `boolean` now round-trips as a real JSON boolean (`true`/`false`) on
  both read AND write -- writing an integer (`0`, `1`, or any other int)
  to such a field is now `VALIDATION_FAILED`, where it previously
  succeeded (silently storing `0`/`1`). A client that writes `0`/`1` to a
  declared-boolean field must switch to `false`/`true` before (or in the
  same release as) flipping this deployment's image.

None of the three requires re-issuing any existing credential (unlike Q1's
own credential-format change, which is entirely internal to this peer's
issuance responses -- the RECEIVING side, `http.py::_split_bearer`/
`control_http.py::_bearer_pair`, is unchanged by this WP, so an already-
issued credential keeps authenticating exactly as before).

## 7. Break-glass CLI (`python -m mitatedb_api.ops`, WP-6)

Run from a checked-out source tree with `PYTHONPATH=MitateDB-api/src`
(never from inside a running container image -- `docker/Dockerfile`'s own
footer note; `migrations/` and the CLI's default `0004` script path are
both source-tree-relative). All bootstrap/reset/break-glass subcommands
connect directly to Cloud SQL through the Cloud SQL Auth Proxy the same way
§3 does (`host=127.0.0.1 port=5432 ...` in each DSN below, proxy running in
the background) -- **never** through either Cloud Run service; this is
exactly the "the network path to `/control/v1` is unavailable but the
database is reachable" scenario the CLI exists for (`ops.py`'s own module
docstring).

- `bootstrap` / `reset` -- unchanged from WP-5, `MITATEDB_CONTROLPLANE_DSN`
  + `MITATEDB_CONTROL_CREDENTIAL_PEPPER` (+ `MITATEDB_CREDENTIAL_PEPPER`
  for the separation check). See `CONTROL_PLANE_COMPROMISE_PLAYBOOK.md` for
  when to run `reset`.
- `list-applications` / `list-credentials` / `enable-application` /
  `disable-application` / `enable-credential` / `disable-credential` /
  `rotate-credential` / `revoke-credential` -- additionally require
  `MITATEDB_CONTROL_CREDENTIAL_ID`/`MITATEDB_CONTROL_CREDENTIAL_SECRET`
  (the operator's own live, already-rotated control credential -- these
  commands authenticate through the exact same `ControlPlaneService`
  `/control/v1` itself uses, so a `must_rotate` credential can do nothing
  here beyond self-`rotate-credential`, same as over HTTP).
- `audit-report` -- requires `MITATEDB_PROVISION_DSN` instead (read-only;
  `mitatedbsvc_controlplane` is INSERT-only on `control_audit` and cannot
  read it back -- `mitatedbsvc_provision`, the schema owner, can).
- `deprovision <application_id> [--confirm PHRASE]` -- requires
  `MITATEDB_PROVISION_DSN` (it runs `0004_deprovision_application.sql`
  directly, the same provisioning-level operation §3.4 documents) and,
  since it is genuinely irreversible, a declare-and-echo confirmation:
  run once without `--confirm` to get the phrase (printed as JSON to
  stderr, exit 2, nothing touched), then again with `--confirm
  '<the printed phrase>'`.

Example (revoking a leaked application credential with the CLI, no HTTP
access needed):

```sh
export MITATEDB_CONTROLPLANE_DSN="host=127.0.0.1 port=5432 dbname=mitatedb_platform user=mitatedbsvc_controlplane password=..."
export MITATEDB_CREDENTIAL_PEPPER="..." MITATEDB_CONTROL_CREDENTIAL_PEPPER="..."
export MITATEDB_CONTROL_CREDENTIAL_ID="ctl_..." MITATEDB_CONTROL_CREDENTIAL_SECRET="..."
python -m mitatedb_api.ops revoke-credential crd_0123456789abcdef  # synthetic
```

## 8. If a control credential is lost, leaked, or misused

Do not improvise here -- follow `CONTROL_PLANE_COMPROMISE_PLAYBOOK.md`
(this same directory) end to end. Two summary facts that motivate
**invariant 3** below (the playbook itself explains why in full):

- Stopping/undeploying the control Cloud Run service is a legitimate first
  response to a suspected compromise (it removes the network path to
  `/control/v1` immediately), but the break-glass CLI (§7) still reaches
  the same control credentials directly through Cloud SQL -- stopping the
  service alone does not revoke anything.
- The canonical recovery for a lost/leaked/lockout control credential is
  `python -m mitatedb_api.ops reset` (declare-and-echo gated), never a
  second `bootstrap`.

**Invariant 3 (design R-9 second-round m-13): if the control service is
stopped, undeployed, or scaled to zero for any reason, the data service's
own `MITATEDB_CONTROL_PLANE_STATUS` environment variable must be flipped
to `unavailable` in the SAME change.** With the two services split apart
(§0's own topology), the data service's `control_plane` capability
declaration (`GET /v1/capabilities`) is populated from `MITATEDB_CONTROL_
PLANE_STATUS` (`config.FoundationConfig.control_plane_status`,
`__post_init__`'s own `{"enabled", "unavailable"}` vocabulary check) --
an *operator assertion*, not something the data service can verify by
reaching the control service itself (R-4's own process-role separation
means the data service holds no credential that could even attempt such a
check). Leaving `MITATEDB_CONTROL_PLANE_STATUS=enabled` set on the data
service while the control service is actually down makes that capability
declaration false -- exactly the "宣言と実挙動の一致" property this whole
design track (R-7) is built to preserve. Re-deploy the data service with
`--update-env-vars=MITATEDB_CONTROL_PLANE_STATUS=unavailable` in the same
maintenance window that stops the control service, and flip it back only
once the control service is confirmed serving again.

## 9. Cloud SQL real-instance R-1 vocabulary verification

Before declaring this runbook "done" for a given Cloud SQL instance, run
each step below once and record the outcome in `security/CONTROL_
MAPPING.md`'s own MitateDB `production_platform_evidence` note (currently
`absent`). This is the "実機で語彙が拒否された場合は設計改版" check the
design's own §4 risk register calls for -- every command listed here is
drawn verbatim from `migrations/0001_bootstrap_platform.sql`'s own R-1
allowlist comment, so a failure here is a real Cloud SQL incompatibility
to escalate, not a runbook typo to silently work around.

1. **Role/database DDL** (§3.1-3.2 above already exercise this): `CREATE
   ROLE ... LOGIN PASSWORD ... NOSUPERUSER NOCREATEDB NOCREATEROLE
   NOINHERIT CONNECTION LIMIT ...`, `CREATE DATABASE`, `GRANT`/`REVOKE`,
   `REVOKE ALL ON SCHEMA public FROM PUBLIC`, `ALTER SCHEMA public OWNER
   TO ...` -- if any of §3 fails, this instance does not accept the R-1
   vocabulary and the design needs revisiting before proceeding further.
2. **`GRANT <role> TO CURRENT_USER WITH SET TRUE` (PostgreSQL 16+, the
   version-pin's own reason)**: exercised inside `begin_provision_
   application` (migration `0002`, called by §3.4) -- confirm §3.4
   completes without a syntax error specifically on this construct (a
   pre-16 Cloud SQL instance would reject it at parse time, distinct from
   a privilege error).
3. **`pg_terminate_backend` / `pg_signal_backend` membership**: Cloud SQL
   requires the executing role to be a `pg_signal_backend` member for
   `pg_terminate_backend` to succeed (superuser is not available at all).
   Grant it once, then verify:
   ```sh
   psql "$MITATEDBSVC_PROVISION_DSN" -c "GRANT pg_signal_backend TO mitatedbsvc_provision"
   ```
   then run a deprovision (§3.4's own reverse, `0004_deprovision_
   application.sql`, or the break-glass `deprovision` subcommand, §7)
   against an application with an open connection and confirm the
   `pg_terminate_backend` step inside that script succeeds rather than
   raising `permission denied to terminate process`.
4. **`assert_role_has_no_memberships`/cloudsqlsuperuser fail-closed check**
   (§3.3's own invariant 2): deliberately create a throwaway role via
   `gcloud sql users create` (NOT the migration SQL), then attempt to
   `ALTER ROLE <that role> RENAME TO <a runtime-role-shaped name>` and
   re-run `begin_provision_application` against it -- confirm the
   function's own `RAISE EXCEPTION` fires (a `pg_auth_members` row for
   `cloudsqlsuperuser` is exactly what a Users-API-created role carries).
   Clean up the throwaway role afterward; this step exists to prove the
   backstop works, not to leave the misconfigured role in place.
5. **Provisioning-session `log_statement` suppression** (§3's own
   invariant 4): confirm `SHOW log_statement` reads `none` (or your
   organization's equivalent no-literal-logging setting) for the
   connection profile §3 actually used, before generating and binding any
   password literal.

Record the date, Cloud SQL version string (`SELECT version()`), and a
pass/fail per numbered item above in `security/CONTROL_MAPPING.md` once
this section has actually been run -- until then, every claim in this
runbook remains procedure, not evidence.

### 9.1 First-execution record (2026-09-01, operator-reported)

This runbook was executed against a real Cloud SQL instance for the first
time on 2026-09-01. Outcome per item above, as reported by the operator and
verified by the supervisor (surfaced, in turn, the three defects this
document/`docker/Dockerfile`/`migrations/0001_bootstrap_platform.sql`
record fixes for, dated the same day) -- recorded honestly, including what
is still unexercised:

- **Cloud SQL version**: PostgreSQL 16.14.
- **Item 1 (role/database DDL)**: PASS -- ceremony-assisted (the
  pre-fix manual `GRANT ... WITH SET TRUE` / `REVOKE` ceremony around
  `0001`, §3.1's own fallback note above; the in-file self-contained fix
  postdates this run).
- **Item 2 (`GRANT <role> TO CURRENT_USER WITH SET TRUE`, exercised inside
  `0003_provision_application.sql:105`, before `ALTER SCHEMA public OWNER
  TO`)**: PASS -- `0003_provision_application.sql` completed with no syntax
  error on this construct.
- **Item 3 (`pg_terminate_backend`/`pg_signal_backend`)**: the `GRANT
  pg_signal_backend TO mitatedbsvc_provision` catalog grant was applied;
  deprovision (the step that actually exercises `pg_terminate_backend`) has
  **not yet been exercised** against this instance -- open.
- **Item 4 (`assert_role_has_no_memberships`/cloudsqlsuperuser fail-closed
  probe)**: **not yet exercised** against this instance -- open.
- **Item 5 (`log_statement` suppression)**: PASS -- `SHOW log_statement`
  confirmed `none` for the §3 connection profile before any password
  literal was bound.

Mirrored in `security/CONTROL_MAPPING.md`'s own SI-00/SI-01 rows (MitateDB
column) as a dated operator-reported note, without removing the honest
remaining gaps those rows already record (deprovision/item 4 unexercised,
`platform_evidence_required_before_production` items beyond the above still
absent).
