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

The proxy also has a unix-socket mode (`cloud-sql-proxy --unix-socket
<socket-dir> <instance-connection-name>`). **§10's Gate-0 read requires
that mode**, because its item (1) confirms which Cloud SQL instance is
being read by matching the instance connection name against the socket
path inside the DSN -- a TCP DSN carries nothing that identifies the
instance, so item (1) stays `unknown`. The bootstrap steps in §3 do not
depend on item (1) and work over either mode.

## 3. Platform bootstrap (run once)

**Connection settings for every `psql` invocation below go into libpq
environment variables, never into a conninfo string on argv.** A conninfo
string (and above all a `password=` inside one) passed as an argument is
readable by every other user on the host through `ps`/`/proc`, while these
environment variables are visible only to the process, its children, and
root -- the same reason `ops.py` builds its own psql subprocess
environment from the DSN instead of putting the DSN on argv. Export the
host and port once for this section, and put the database, role, and
password on each invocation:

```sh
export PGHOST=127.0.0.1 PGPORT=5432   # §2's proxy in --port mode
```

(A `~/.pgpass` entry or `PGPASSFILE` is better still than `PGPASSWORD`;
either is strictly better than a `password=` on argv. §10 uses the
proxy's unix-socket mode and a different `PGHOST` value.)

**One exception remains, and it is not closed**: the one-time bootstrap
steps below still pass a password literal on argv -- in a psql variable
(`-v ..._password="$..."`) and inside a `-c "ALTER ROLE ... PASSWORD
'...'"` body. A psql variable and a `-c` body have no environment-variable
form, so those literals are still readable through `ps`/`/proc` for as
long as the command runs. Invariant 4 below keeps them out of Cloud SQL's
query log; it does nothing about the host's own process table. Run the
bootstrap on a host no other user has a session on.

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
PGDATABASE=postgres PGUSER=postgres psql \
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
PGDATABASE=postgres PGUSER=postgres psql \
  -v provision_password="$MITATEDBSVC_PROVISION_PASSWORD" \
  -f MitateDB-api/migrations/0001_bootstrap_platform.sql
# 2. Grant the missing SET option by hand -- the role now exists, so this
#    resolves.
PGDATABASE=postgres PGUSER=postgres psql \
  -c "GRANT mitatedbsvc_provision TO postgres WITH SET TRUE"
# 3. Re-run 0001 -- CREATE ROLE is a no-op (role already exists), CREATE
#    DATABASE now succeeds.
PGDATABASE=postgres PGUSER=postgres psql \
  -v provision_password="$MITATEDBSVC_PROVISION_PASSWORD" \
  -f MitateDB-api/migrations/0001_bootstrap_platform.sql
# 4. Revoke the temporary membership.
PGDATABASE=postgres PGUSER=postgres psql \
  -c "REVOKE mitatedbsvc_provision FROM postgres"
```
Keep this only as a fallback for a checkout that predates the in-file fix,
not as the normal procedure -- a checkout with the fix needs only the
single `psql -f 0001_...` command above.

### 3.2 Registry schema + process roles (migration `0002`)

```sh
PGDATABASE=mitatedb_platform PGUSER=mitatedbsvc_provision PGPASSWORD="$MITATEDBSVC_PROVISION_PASSWORD" \
  psql \
  -f MitateDB-api/migrations/0002_registry_and_functions.sql
```

This creates `mitatedbsvc_api`/`mitatedbsvc_controlplane` (both `LOGIN`,
both `NOSUPERUSER NOCREATEDB NOCREATEROLE`) with no password yet -- set one
for each and record both in Secret Manager:

```sh
PGDATABASE=postgres PGUSER=postgres psql -c \
  "ALTER ROLE mitatedbsvc_api PASSWORD '$(openssl rand -base64 32)'"
PGDATABASE=postgres PGUSER=postgres psql -c \
  "ALTER ROLE mitatedbsvc_controlplane PASSWORD '$(openssl rand -base64 32)'"
```

### 3.2b Application-plane durable audit sink + `audit_query` reader (migration `0005`, Phase 4 WP-3(a)/WP-3(b))

Migration and wiring below; the operational parts -- capacity thresholds,
the five fixed alert messages, `audit_requests_per_minute` sizing, manual
retention, and reading evidence during a Cloud SQL outage -- are §3.2c-§3.2f
immediately after it.

Run once, after `0002`, as the SAME `mitatedbsvc_provision` role/connection:

```sh
PGDATABASE=mitatedb_platform PGUSER=mitatedbsvc_provision PGPASSWORD="$MITATEDBSVC_PROVISION_PASSWORD" \
  psql \
  -f MitateDB-api/migrations/0005_application_audit.sql
```

This creates `mitatedb_registry.application_audit` (`mitatedbsvc_api`
gains INSERT-only on it -- no new privilege on any other object) and the
new `mitatedbsvc_auditreader` role (`LOGIN`, `SELECT`-only on BOTH
`control_audit` and `application_audit`, no password yet):

```sh
PGDATABASE=postgres PGUSER=postgres psql -c \
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
PGDATABASE=mitatedb_platform PGUSER=mitatedbsvc_provision PGPASSWORD="$MITATEDBSVC_PROVISION_PASSWORD" \
  psql \
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

**Phase 10 WP-6b (design D-5 (ii)) adds a second required-before-first-
startup declaration, `process_ceilings`.** Apply its own platform
single-shot migration (also idempotent) and declare the row -- **required
alongside `surfaces` before either service will start (F-15)**:

```sh
PGDATABASE=mitatedb_platform PGUSER=mitatedbsvc_provision PGPASSWORD="$MITATEDBSVC_PROVISION_PASSWORD" \
  psql \
  -f MitateDB-api/migrations/0011_process_ceilings.sql
python -m mitatedb_api.ops declare-process-ceilings --data 1 --control 1
```

`--data` must equal `mitatedb-data`'s own `MITATEDB_WORKERS` (its
`--max-instances` stays 1) and `--control` must be 1 (Invariant 1, §6.2;
§6.5) -- see those sections for the full correctness argument and §6.1 for
the upgrade order on an EXISTING deployment (migration → declare →
restart, never the reverse; LQ4-24).

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

**Phase 10 WP-4f (supervisor ruling 2026-09-09) adds a role `CONNECTION
LIMIT` migration, peer-symmetric with r2db-api's own `0013_role_
connection_limits.sql`.** A PostgreSQL role's `CONNECTION LIMIT` must be
at least the real worst-case number of simultaneous connections the
process(es) using that role can open at once ("pool 合計") -- otherwise a
burst of real concurrent requests hits PostgreSQL's own hard `FATAL: too
many connections for role` refusal instead of the declared 429/503 the
contract promises. Apply this platform single-shot migration (idempotent
-- safe to re-run) BEFORE (or after -- order relative to `0007`/`0011` is
irrelevant) the `platform_declarations` migration above:

```sh
PGDATABASE=mitatedb_platform PGUSER=mitatedbsvc_provision PGPASSWORD="$MITATEDBSVC_PROVISION_PASSWORD" \
  psql \
  -f MitateDB-api/migrations/0012_role_connection_limits.sql

PGDATABASE=mitatedb_platform PGUSER=mitatedbsvc_provision PGPASSWORD="$MITATEDBSVC_PROVISION_PASSWORD" \
  psql \
  -f MitateDB-api/migrations/0013_role_statement_timeouts.sql

PGDATABASE=mitatedb_platform PGUSER=mitatedbsvc_provision PGPASSWORD="$MITATEDBSVC_PROVISION_PASSWORD" \
  psql \
  -f MitateDB-api/migrations/0014_role_connection_limits_rollout.sql
```

(2026-09-18: the block above used to stop at `0012`. Two files after it
touch the same subject, so all three run here, and always in the order
`0012` -> `0013` -> `0014`: each of the two earlier files replaces
`begin_provision_application` with its OWN `CONNECTION LIMIT` literals,
so running one of them alone after `0014` lowers a limit again.
`0013` and `0014` both alter `mitatedbsvc_auditreader`, which `0005`
(§3.2b) creates, so both fail with an undefined-role error on a database
where `0005` has not run -- unlike `0012`, whose own order relative to
`0007`/`0011` stays irrelevant. §10.10's numbered-set note and §10.10.1
step 7 carry the same order for an existing deployment.)

The data service also needs the credential-keyed `requests_per_minute`
row every data-plane worker shares (`0016`, §6.5), applied the same way,
after `0002` (order relative to `0005`/`0007`/`0011`-`0014` does not
matter). On a platform database without its rate function, the data
service and its preflight refuse to start, naming the migration:

```sh
PGDATABASE=mitatedb_platform PGUSER=mitatedbsvc_provision PGPASSWORD="$MITATEDBSVC_PROVISION_PASSWORD" \
  psql \
  -f MitateDB-api/migrations/0016_credential_request_rate.sql
```

**Current pool sizing and the per-worker connection budget are in §6.5.**
Every pool of one data-plane worker is sized from that worker's own thread
limit (`MITATEDB_THREAD_LIMIT` + 2), and the F-16/F-18 floors multiply by
the declared `process_ceilings`; the table below, which sizes a pool from
the declared `concurrency`, describes the single-process sizing that §6.5
replaces.

Role floor arithmetic (formula: worst-case pool composition + 4 fixed
operator-headroom connections):

| Role | Pool composition | Old `CONNECTION LIMIT` | New `CONNECTION LIMIT` (as `0012` sets it -- the values a deployment carries today are in the note below this table) |
| --- | --- | --- | --- |
| `mitatedbsvc_api` | platform pool (`role_pool_size`, declared `max_concurrency`, default 32) + durable audit sink's own per-write transient connections (also bounded by `max_concurrency`) = 2 x 32 = 64 | 20 | 68 |
| `mitatedbsvc_controlplane` | 4 platform-plane stores, peer-symmetric worst case with r2db-api's own measured 16 | 10 | 20 |
| `<app>_rt` (runtime) | 1 store, bounded by `max_concurrency` = 32 | 20 | 36 |
| `<app>_dv` (developer) | 1 store, bounded by `max_concurrency` = 32 | 10 | 36 |
| `mitatedbsvc_provision` | short-lived, one-shot CLI/provisioning connections only -- no persistent pool | 5 | unchanged (already >= its own real pool composition) |
| `mitatedbsvc_auditreader` | 1 store, fixed floor 4 | 5 | unchanged (already >= its own real pool composition) |

(2026-09-18: the "New `CONNECTION LIMIT`" column above is `0012`'s own
value and is no longer the value a deployment carries once the block
above has been run to its end. `0014` raises the same composition to the
demand of TWO revisions of the same process serving at once, which is
what a rollout puts side by side: `mitatedbsvc_api` 132, `mitatedbsvc_
controlplane` 36, each `<app>_rt` / `<app>_dv` 68, and
`mitatedbsvc_auditreader` 12 -- the auditreader's "unchanged" row holds
for ONE process only, and 5 no longer covers 2 x 4. `mitatedbsvc_
provision` stays unchanged. The formula is the same one this table uses,
with "pool 合計" read over the processes serving at once: §10.10's own
precondition arithmetic works the same numbers.)

The CONNECTION LIMIT figures the table above sets are PER-ROLE ceilings PostgreSQL enforces independently -- summing them is not itself the PostgreSQL requirement `max_connections` has to satisfy. The one fact that actually governs `max_connections` is:

```
max_connections >= real simultaneous connections this deployment can produce at once
                    + superuser_reserved_connections (default 3)
```

"real simultaneous connections this deployment can produce at once" is declared `concurrency` x role count (runtime + developer) x applications served by this process, plus `2 x platform_pool_size` for the two platform-plane pools, plus however many interactive/diagnostic `psql` sessions an operator expects to hold open at once. Summing the CONNECTION LIMIT table instead is a conservative, easy-to-compute stand-in for that real figure for an operator who has not derived it -- not a PostgreSQL requirement in its own right. Re-check the real figure against `SHOW max_connections;` before applying a migration to an instance already close to its own configured ceiling.

`python -m mitatedb_api.ops verify-declarations` now also checks this
(new check `F-16`): each role's own `pg_roles.rolconnlimit` is `-1` or at
least its own real pool-composition floor above, run unconditionally
alongside every other check that command already runs.

`python -m mitatedb_api.ops verify-declarations` also checks a cluster-wide necessary condition (new check `F-18`): the connection count the declared `process_ceilings` guarantees this deployment opens -- one platform pool per data process, one runtime/developer pair per data process once at least one application is registered, one control-plane pool per control process -- plus `superuser_reserved_connections` plus `reserved_connections`, must stay at or under `max_connections`; both `mitatedb-app` and `mitatedb-ctrl` fail the same unscoped check at their own startup, `verify-declarations` itself exiting 17. Unlike Gate-0 item (8) (§10.10), F-18 never takes an operator-supplied process count or reserved-connection value -- it reads `process_ceilings` directly -- and it counts only ONE registered application's own runtime/developer pair toward the judged lower bound, never the full registered-application count (that full count feeds only a reported, unjudged upper bound). It is a necessary condition only, never counting an interactive/diagnostic `psql` session nor its own connection; the `mitatedb-ctrl` startup judgment sizes the data-plane pools from its own environment's thread limit (`MITATEDB_THREAD_LIMIT`, exactly as its F-16 call does, §6.5), so keep that value equal to the data service's; if the open rollout-overlap question (R-52) is resolved by declaring the overlap's own process count in `process_ceilings`, that declared count is exactly what F-18's lower bound already counts. Evidence: `MitateDB-api/tests/test_ops_verify_declarations.py::test_verify_declarations_f18_fails_when_the_declared_lower_bound_exceeds_max_connections`, `::test_verify_declarations_f18_passes_when_the_declared_lower_bound_fits`, `MitateDB-api/tests/test_application_audit.py::test_build_app_fails_fast_when_the_declared_process_ceilings_lower_bound_exceeds_max_connections`, `MitateDB-api/tests/test_control_main.py::test_build_control_app_fails_fast_when_the_declared_process_ceilings_lower_bound_exceeds_max_connections`.

`verify-declarations` also checks the collation every registered, provisioned application's own database was provisioned with (new check `F-19`, `verify-declarations` itself exiting 18): `pg_database.datcollate` must be `'C'` (codepoint-order string comparison, matching this peer's SQLite backend), `datctype` must stay this cluster's own UTF-8 locale (never `'C'`), and, on a server that can report it (`pg_database.datlocprovider`, PostgreSQL 15 and later), the locale provider must be libc, never ICU (an ICU database's own `LC_COLLATE` string does not govern its ordering, so datcollate `'C'` there would be a false green). A Cloud SQL instance itself provisioned with a `C`/`POSIX` locale fails F-19 too, and correctly so: this cluster's own `template0` would then hand every new application database `datctype = 'C'`, breaking non-ASCII case folding and pattern matching -- provision the instance with a real UTF-8 locale, the same one `tools/testpg/dsa_testpg.py` uses for every throwaway test cluster. The only remedy for an application database that fails F-19 for the `collate`/`ctype`/`missing` reasons is re-provisioning it (`0003_provision_application.sql`); an existing database's own collation cannot be changed in place. A database that fails F-19 for the `provider` reason (ICU) cannot be fixed by re-running the current `0003` against an instance whose own `template0` was itself provisioned with an ICU provider -- `CREATE DATABASE` inherits the template's provider -- re-provision it against an instance using the libc locale provider instead. A database missing from `pg_database` (the `missing` reason) may also be one `0004_deprovision_application.sql` left mid-way (dropped, but its own `applications` row not yet cleared) -- completing that deprovision, rather than re-provisioning, is the correct remedy there. Evidence: `MitateDB-api/tests/test_ops_verify_declarations.py::test_verify_declarations_f19_fails_when_an_application_database_collation_is_not_c`, `::test_verify_declarations_f19_passes_after_provisioning_with_0003`, `MitateDB-api/tests/test_postgres.py::test_application_database_collation_is_c`, `::test_application_database_collation_keeps_the_cluster_ctype` (5 passed under `-k "collation or parity_order"`).

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
PGDATABASE=mitatedb_platform PGUSER=mitatedbsvc_api PGPASSWORD="$MITATEDBSVC_API_PASSWORD" \
  psql -c \
  "SHOW statement_timeout; SHOW idle_in_transaction_session_timeout;"
PGDATABASE=mitatedb_platform PGUSER=mitatedbsvc_controlplane PGPASSWORD="$MITATEDBSVC_CONTROLPLANE_PASSWORD" \
  psql -c \
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
`<buffer capacity> x M`, where **M is the number of `mitatedb-data`
processes: its `MITATEDB_WORKERS` on its one instance** (`--max-instances=1`,
Invariant 1, §6.2). Invariant 1 also pins the declared `process_ceilings.
data` (`ops declare-process-ceilings`'s own `--data` value) to that same
number, so **M is this deployment's own declared `process_ceilings.data`**
-- never a scaler maximum picked independently of that declaration. With
`MITATEDB_WORKERS=1` and `process_ceilings: {1, 1}` (§6.1), M is 1; a
deployment that raises `MITATEDB_WORKERS` re-declares
`process_ceilings.data` to match (§6.5), and this arithmetic uses that
number.

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
# Set PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD from the mitatedb-audit-dsn
# secret's own fields rather than expanding the whole DSN onto argv, where
# `ps` makes it readable to every other user on the host (§3's convention).
psql -c "\copy (SELECT * FROM mitatedb_registry.application_audit \
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
PGDATABASE=mitatedb_platform PGUSER=mitatedbsvc_provision PGPASSWORD="$MITATEDBSVC_PROVISION_PASSWORD" \
  psql \
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
PGDATABASE=mitatedb_platform PGUSER=mitatedbsvc_provision PGPASSWORD="$MITATEDBSVC_PROVISION_PASSWORD" \
  psql \
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
python -m mitatedb_api.ops upgrade-applications --dry-run --lock-timeout <value>

# Apply. Visits every application; a failure on one does not stop the rest
# -- failed applications are listed at the end, each with a REVOKE cleanup
# line (see below).
python -m mitatedb_api.ops upgrade-applications --lock-timeout <value>
```

**`--lock-timeout` is required on both forms and has no default** (a
positive integer, optionally suffixed `ms`/`s`/`min`; `0` is refused
because PostgreSQL reads it as "no timeout"). It is set on the psql
session before each per-application upgrade script runs, so a script
waiting on a lock fails and rolls back instead of queueing behind it
indefinitely. §10.7's per-application-upgrade row is where the value comes
from.

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
   --dry-run --lock-timeout <value>` (§10.7's per-application-upgrade row),
   then the same command without `--dry-run`.
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
| `mitatedb-provision-dsn` | `MITATEDB_PROVISION_DSN` (`mitatedbsvc_provision`; unix-socket form, §5, for §10's Gate-0 read -- item (1) stays `unknown` over a TCP DSN; this secret keeps the `password=` form below, and the only thing that turns it into a `passfile=` form is §10.1's own converter, whose passfile is local and temporary) | **operator/break-glass CLI only -- never a Cloud Run service** (§7) |
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
  --max-instances=1 \
  --cpu=1 \
  --set-secrets=MITATEDB_CREDENTIAL_PEPPER=mitatedb-credential-pepper:latest,MITATEDB_PLATFORM_DSN=mitatedb-platform-dsn:latest \
  --set-env-vars=MITATEDB_SERVE_APPS=acme,MITATEDB_CONTROL_PLANE_STATUS=enabled,MITATEDB_WORKERS=1
# ... plus one --set-secrets pair per onboarded application's own
# MITATEDB_APP_<ID_UPPER>_{RUNTIME,DEVELOPER}_DSN.
```

**`--max-instances=1` with `MITATEDB_WORKERS=1` here matches the
`process_ceilings.data = 1` this deployment declares below -- see
Invariant 1 in §6.2: one instance, `process_ceilings.data` equal to
`MITATEDB_WORKERS`, and `--cpu` at least `MITATEDB_WORKERS`.** To serve
with more worker processes, raise `MITATEDB_WORKERS` and `--cpu` together
and keep `--max-instances=1` (§6.5). The image sets `MITATEDB_SLOT_DIR`
itself (§6.5); never override it here.

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

`MITATEDB_OPERATION_CATALOG_URL` (optional, both services): unset,
`GET /v1/operation-catalog`'s declared URL derives from `surfaces.data.
base_url` with its trailing contract `versioning.base_path` replaced by
the contract's own `endpoints.operation_catalog.path` -- reachable
behind the same reverse-proxy prefix, if any, `surfaces.data.base_url`
itself already carries. Set it (the SAME value on both `gcloud run
deploy` commands) only for a CDN-fronted copy of the operation catalog.
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

`MITATEDB_THREAD_LIMIT` (optional): on the data service, `run_in_
threadpool`'s own worker-thread limiter for each worker process' event
loop (`http.py`'s `create_app(..., thread_limit=)`), and the basis every
pool of that worker is sized from (§6.5); the control service reads it
only for its own startup connection checks (F-16/F-18), so set the SAME
value on both services. Unset or empty defaults to
`DEFAULT_THREAD_LIMIT` (4). A positive integer raises or lowers it; zero,
negative, or non-numeric is a startup failure naming this variable.

**Phase 10 WP-6b (design D-5 (ii)): `process_ceilings` is declared the
same way, and is REQUIRED (F-15) alongside `surfaces` before either
service will start**:

```sh
python -m mitatedb_api.ops declare-process-ceilings --data 1 --control 1
```

`--data`/`--control` are how many processes may serve each plane's own
base URL at the same time -- **`--data` must equal `mitatedb-data`'s own
`MITATEDB_WORKERS` on its one instance, and `--control` must be 1
(`MITATEDB_CONTROL_WORKERS=1` on one `mitatedb-ctrl` instance)**
(Invariant 1, §6.2 below; §6.5); the app itself checks that
`MITATEDB_WORKERS` does not exceed `--data` at startup, but it cannot
verify the Cloud Run side (`--max-instances`) of that match (the same limitation as the `MITATEDB_PLATFORM_DSN`/`MITATEDB_
CONTROLPLANE_DSN` pairing two paragraphs above, and the same limitation
LQ4-15 already names for a different pair of values) -- keeping the two
in agreement is a runbook/deployer discipline, checked post-deploy the
same way §6.3 already cross-checks `surfaces`, never enforced by either
process at startup.

**Upgrade order on an EXISTING deployment (this migration/declaration
did not exist before Phase 10): apply migration `0011_process_
ceilings.sql` to the platform database, THEN run `declare-process-
ceilings` above, THEN restart both services** -- never the reverse
(startup is a snapshot read, design U-3; declaring before the migration
is applied fails with an undefined-CHECK-vocabulary error, and restarting
before declaring re-fails startup with F-15). **`part1_provision_host_
and_db.sh` does not yet run migration `0008`/`declare-surfaces` either
(LQ4-24) -- a script-provisioned host has the identical gap for THIS
migration/declaration pair, and needs the same manual catch-up this
paragraph describes until LQ4-24 is closed.**

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
  --set-secrets=MITATEDB_CREDENTIAL_PEPPER=mitatedb-credential-pepper:latest,MITATEDB_CONTROL_CREDENTIAL_PEPPER=mitatedb-control-credential-pepper:latest,MITATEDB_CONTROLPLANE_DSN=mitatedb-controlplane-dsn:latest,MITATEDB_AUDIT_DSN=mitatedb-audit-dsn:latest \
  --set-env-vars=MITATEDB_CONTROL_WORKERS=1
```

`MITATEDB_CONTROL_WORKERS` is required and always 1 (§6.5).

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

**Invariant 1 -- one host per plane: `--max-instances=1` on EITHER Cloud
Run service, and each plane's declared `process_ceilings` equal to the
worker processes on that one instance** (`process_ceilings.data` =
`MITATEDB_WORKERS` for `mitatedb-data`, `process_ceilings.control` = 1 =
`MITATEDB_CONTROL_WORKERS` for `mitatedb-ctrl`, §6.1 above). **It is not a
scaling convenience, it is a correctness requirement.** The data service
scales by running more uvicorn worker processes on its one instance --
raise `MITATEDB_WORKERS` and `--cpu` together, `--cpu` at least
`MITATEDB_WORKERS` -- never by raising `--max-instances` (§6.5). The
reason: the data service's `concurrency` bound is held by file locks in
the instance's own slot directory, which every worker on that instance
shares and no other instance sees, and the control service's
`control_requests_per_minute`/`audit_requests_per_minute` windows are
in-process counters. Contract 1.8.0 makes this precise: an `enforced`
declaration for one of these classes describes the WHOLE deployment
reachable at the declared surfaces base URL, never one process or one
instance. `concurrency` is declared `enforced` only while
`process_ceilings.data` equals `MITATEDB_WORKERS` (a larger declaration is
read as processes on another instance and answers `deployment_required`);
`requests_per_minute` is counted in one platform-database row per
credential (`0016`, §6.5) and stays `enforced` at any declared ceiling;
the control windows are `enforced` only while `process_ceilings.control`
is 1. So raising `--max-instances` on either service is a silent
regression to a false `enforced` claim for the host-held classes, not
merely a capacity change. **The app cannot verify the Cloud Run side of
this match** (`--max-instances` and `--cpu` are outside either composition
root's own reach; the app itself checks only that the worker count does not
exceed the declared ceiling) -- topology and declaration agreement is a
runbook discipline, verified post-deploy (§6.3, §6.5), the same limitation
LQ4-15 already names for surfaces/DSN pairing.

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

### 6.5 Worker processes on one instance

Companion to `docs/design/MULTI_PROCESS_WORKER_V0_1.md` (D-1, D-3) and
Invariant 1 (§6.2). The data service serves with several uvicorn worker
processes on its ONE instance; this section is what that asks of a
deployment.

**One host.** Each base URL is served by one Cloud Run instance
(`--max-instances=1` on both services). The data service's worker
processes on that instance share one slot directory, which no other
instance sees, and `process_ceilings` counts processes, not instances.
Scale the data service by worker processes, never by instances.

**Workers and the declaration.**

- `MITATEDB_WORKERS` (`mitatedb-data`) is required: a positive integer, no
  default, set with `--set-env-vars` (§6.1). The image's `CMD` passes it as
  `--workers "${MITATEDB_WORKERS}"`, so uvicorn never falls back to
  `WEB_CONCURRENCY`.
- `--cpu` is at least `MITATEDB_WORKERS`: every worker is a separate Python
  process, and fewer vCPUs than workers leaves workers waiting for CPU.
  Every worker holds its own copy of the application, so size `--memory`
  for `MITATEDB_WORKERS` copies too.
- Declare `process_ceilings.data` equal to `MITATEDB_WORKERS`:
  `python -m mitatedb_api.ops declare-process-ceilings --data <MITATEDB_WORKERS> --control 1`,
  then deploy both services again (both read the declaration once, at
  startup). A revision's process ceiling is its `--max-instances` (1) times
  its `MITATEDB_WORKERS`; that product is what `process_ceilings.data` and
  every other process count in this runbook mean. `ops inventory` counts a
  NEW-basis revision's connection demand from `role_pool_size(--thread-
  limit)`, the SAME per-process floor F-16 uses (the table below) -- an
  OLD-basis revision (one still running a `--concurrency`-sized pool
  instead) is counted separately, from its own declared `concurrency`
  (§10.4.3).
- The preflight and every worker refuse to start when `MITATEDB_WORKERS`
  exceeds `process_ceilings.data`. `limit_enforcement.concurrency` is
  `enforced` only while the two are EQUAL; a larger declaration is read as
  processes on another instance and answers `deployment_required`.
  `requests_per_minute` is counted in one platform-database row per
  credential (`0016`, below) and stays `enforced` at any declared ceiling.
- `MITATEDB_CONTROL_WORKERS` (`mitatedb-ctrl`) is required and always `1`,
  with `process_ceilings.control = 1`: the control service's
  `control_requests_per_minute`/`audit_requests_per_minute` windows are
  per process. Its preflight refuses a value above
  `process_ceilings.control`.

**Slot directory.** The image creates `/var/lib/mitatedb/slots`, owned by
the image's `USER` (`mitatedb`), mode `0700`, and sets `MITATEDB_SLOT_DIR`
to it (`docker/Dockerfile`). The data service only checks the directory --
existence, owner = its own effective uid, mode `0700`, and a `flock`
self-check that a second lock on one file is refused -- and never creates
it. Every in-flight request holds one of `concurrency` slot files under an
exclusive `flock`, so the declared `concurrency` bounds every worker on the
instance together. The directory holds three kinds of file: `slot-<i>`
(one per slot), `selfcheck` (the startup `flock` self-check) and `scan`
(held briefly while a worker looks for a free slot). Never override
`MITATEDB_SLOT_DIR` and never run the container as another user; either
stops startup. The control service uses no slot directory.

**Preflight in `CMD`.** Each branch of the image's `CMD` runs the service's
own preflight -- `python -m mitatedb_api.main --preflight` for `data`,
`python -m mitatedb_api.control_main --preflight` for `control` -- joined
to `exec uvicorn` with `&&`. The preflight builds the application once
with the container's own environment -- every startup check: F-13, F-15,
F-16, F-18, the served-application registry, the pepper separation, the
worker count against `process_ceilings`, and on `data` the slot-directory
checks -- and exits non-zero on the first failure; the container then ends
with that status and the revision never becomes ready. uvicorn's own
worker supervisor cannot do this: it replaces a worker that failed at
startup and itself keeps running. The preflight closes its own
connections before uvicorn starts.

**Signals: never SIGTTIN, never SIGHUP.** Never send either to the uvicorn
supervisor (from a debugging shell, for example). SIGTTIN starts one more
worker while it runs -- beyond `MITATEDB_WORKERS`, the declared
`process_ceilings.data`, and the connection budget below. SIGHUP replaces
the workers one at a time, so `MITATEDB_WORKERS + 1` processes run for a
while, again beyond that budget. To pick up a change, deploy a new
revision: its instance stops the old process group and starts a new one.

**Never stop a single worker.** Do not stop one worker with SIGSTOP or by
attaching a debugger to it. A worker stopped in the middle of admitting a request holds up admission
on the whole host: while it is stopped, every request can wait up to 1 s
and then be answered `503`. To restart, stop the whole process group
and start it again: deploy a new revision (above).

**Cloud Run and `--max-instances`.** Inference (推測; not verified against
Cloud Run itself): Cloud Run may run more instances than `--max-instances`
for a short time; while it does, two instances' workers do not share slots,
so in-flight requests may reach up to twice the declared `concurrency`.

**Connection budget -- counted from the thread limit.** One worker never
has more requests using the database at once than its thread limit
(`MITATEDB_THREAD_LIMIT`, default 4), so every pool of one worker is sized
`p = MITATEDB_THREAD_LIMIT + 2` (`role_pool_size`; `p = 6` by default).
Each worker also holds one persistent connection per served application
for each of its runtime and developer roles, so `W` workers hold `W` such
connections per role. The declared `concurrency` is not part of the
budget -- a slot holds a file lock, not a connection. With
`W = process_ceilings.data` (equal to `MITATEDB_WORKERS`) and
`C = process_ceilings.control` (1):

| Role | F-16 floor (startup and `verify-declarations`) | At `p = 6` | Limit `0014` sets | Largest count that fits |
| --- | --- | --- | --- | --- |
| `mitatedbsvc_api` | `2 × p × W` | `12 × W` | 132 | `W` ≤ 11 |
| each `<app>_rt` / `<app>_dv` | `p × W` (the persistent connections are `W`; the floor keeps the pool formula) | `6 × W` | 68 | `W` ≤ 11 |
| `mitatedbsvc_controlplane` | `16 × C` | `16 × C` | 36 | `C` ≤ 2 |
| `mitatedbsvc_auditreader` | `4 × C` | `4 × C` | 12 | `C` ≤ 3 |

F-18 (startup and `verify-declarations`, cluster-wide) judges the lower
bound `W × (2p + 2p) + C × 16` once at least one application is registered
(`W × 2p + C × 16` with none) plus `superuser_reserved_connections` plus
`reserved_connections` against `max_connections`. At `p = 6`: `24 × W + 16`
(`12 × W + 16` with no application registered) -- 40 at `W = 1`, 112 at
`W = 4` (64 with no application registered).

`0014` sizes its limits for two revisions serving side by side (the
rollout overlap below): two revisions of `W` workers each need `2 × 12 × W`
on `mitatedbsvc_api` and `2 × 6 × W` on each application role, so
`MITATEDB_WORKERS` up to 5 keeps that margin at the default thread limit.
A larger count, or a raised `MITATEDB_THREAD_LIMIT`, needs a higher
`CONNECTION LIMIT` than `0014` sets -- a new platform migration; F-16 stops
startup naming the role, its current limit and the exact floor it needs.
Every figure here assumes SIGHUP is never sent (above).

**`process_ceilings.control` of 2 or more** needs a `CONNECTION LIMIT` of at
least `16 × process_ceilings.control` on `mitatedbsvc_controlplane` and at
least `4 × process_ceilings.control` on `mitatedbsvc_auditreader`; F-16
reports the exact floor it needs, naming the role.

**`0016` -- the credential-keyed `requests_per_minute` row.** Creates
`mitatedb_registry.credential_request_rate` (one row per credential) and
the function `mitatedb_registry.credential_request_rate_admit`, and grants
`mitatedbsvc_api` access to them -- nothing to any other role. Every
data-plane worker counts an authenticated request with one autocommit
statement on its own platform pool (the `mitatedbsvc_api` role), after
authentication, so every worker shares one count per credential;
unauthenticated requests never reach the table. A database failure on that
statement refuses the request, the same way as any other platform-database
failure -- it never lets the request through uncounted. Rows go away with
their credential (`ON DELETE CASCADE`). A new platform applies it in §3
with the other platform migrations. On an existing deployment it is
applied by §10.10.1 step 7a, before the candidate that counts in it is
deployed; against production, run it only through that gated procedure
(section 10). On a platform database without its rate function, the data
service and its preflight refuse to start, naming the migration.

**Window shape (disclosure).** The row keeps one count per integer second
for the current second and the 60 before it (`int[61]`, a ring indexed by
the second modulo 61), anchored to the database clock (`clock_timestamp()`),
so the workers' own clocks never enter the window, and its base second only
moves forward. At a window edge it may count up to one second more than
60 s: it may refuse a request slightly early, and it never admits more than
the declared `requests_per_minute`.

**Rollout overlap: what holds and what does not.** While a new revision
takes over, old and new revisions may serve at the same time on two
instances:

- `requests_per_minute` holds -- one shared row per credential.
- `concurrency` does not: the two instances' slot directories are not
  shared, so in-flight requests may reach up to twice the declared bound.
- The control service's two windows are per process, so overlapping control
  revisions allow up to twice each declared bound.
- Both revisions' connections count at once: `0014`'s limits are sized
  for that (above), while F-16/F-18 count only the declared
  `process_ceilings` unless it declares the overlap's own process count.

**Confirming on the deployed revision.** This repository's development
machine has no container runtime, so the image's behavior is confirmed on
Cloud Run after deployment: the revision becomes ready (a failing preflight
ends the container with a non-zero status, the revision never becomes
ready, and its log carries the preflight's traceback naming the failing
check), and with `process_ceilings.data` equal to `MITATEDB_WORKERS`,
`GET /v1/capabilities` reports `limit_enforcement.concurrency` and
`limit_enforcement.requests_per_minute` as `enforced`.

## 7. Break-glass CLI (`python -m mitatedb_api.ops`, WP-6)

Run from a checked-out source tree with `PYTHONPATH=MitateDB-api/src`
(never from inside a running container image -- `docker/Dockerfile`'s own
footer note; `migrations/` and the CLI's default `0004` script path are
both source-tree-relative). All bootstrap/reset/break-glass subcommands
connect directly to Cloud SQL through the Cloud SQL Auth Proxy (proxy
running in the background) -- **never** through either Cloud Run service;
this is exactly the "the network path to `/control/v1` is unavailable but
the database is reachable" scenario the CLI exists for (`ops.py`'s own
module docstring).

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
- `deprovision <application_id> --lock-timeout <value> [--confirm PHRASE]`
  -- requires `MITATEDB_PROVISION_DSN` (it runs
  `0004_deprovision_application.sql` directly, the same provisioning-level
  operation §3.4 documents) and, since it is genuinely irreversible, a
  declare-and-echo confirmation: run once without `--confirm` to get the
  phrase (printed as JSON to stderr, exit 2, nothing touched), then again
  with `--confirm '<the printed phrase>'`. **`--lock-timeout` is required
  and has no default** (same value shape as `upgrade-applications`;
  §10.7's deprovision row is where the value comes from).
- `apply-platform-migration <FILENAME> [<FILENAME> ...] --lock-timeout
  <value> [--api-role ROLE --controlplane-role ROLE]` -- requires
  `MITATEDB_PROVISION_DSN`; re-applies one or more of the accepted
  platform migrations, in migration order, as one run (§10.10).
  **`--lock-timeout` is required and has no default** (§10.7 is where
  the value comes from; the tool does not check that a run's files
  share one §10.7 value, so composing a run only from files whose
  §10.7 value agrees is the operator's own responsibility).
- `inventory` -- requires `MITATEDB_PROVISION_DSN`; the read-only Gate-0
  DB-layer read (§10.5). It opens its own read-only connections and
  changes nothing.

**Which proxy mode**: over `--port` (TCP) the DSNs below have the
`host=127.0.0.1 port=5432 ...` shape §2 shows. **`inventory` and the
platform-upgrade procedure in §10 require the proxy's unix-socket mode
instead** (§10.1), because item (1) can only be confirmed from a DSN whose
host path carries the instance connection name. Follow §3's convention for
every `psql` invocation: libpq environment variables, never a conninfo
string on argv.

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
3. **Live-connection deprovision** (design `docs/design/
   DEPROVISION_FORCED_DROP_V0_1.md` v1.0, D-2R -- supersedes the
   `pg_signal_backend` grant this item previously called for; see the
   correction note on the 2026-09-01 record below, §9.1): `0004` no
   longer needs cluster-wide `pg_signal_backend` membership at all. It
   instead runs a pre-check, a temporary self-grant of this application's
   own roles, and `ALLOW_CONNECTIONS false`, ahead of the narrowed
   `pg_terminate_backend`/`DROP DATABASE`/`DROP ROLE` steps that were
   already here. Verify it end to end:
   ```sh
   # libpq environment variables from the admin DSN's own fields, never
   # the DSN on argv (§3's convention). Read-only, before running anything
   # below. `backend_type` reads NULL here for a backend whose role you do
   # not hold privileges of (design M-5/H-2), so judge by `usename`/
   # `usesysid` instead -- a row with `usesysid IS NULL` is a background
   # worker (autovacuum), which the pre-check deliberately does not count
   # (design D-2R stage (2), M-12).
   psql -c "SELECT usename, usesysid IS NOT NULL AS is_a_login_role
             FROM pg_stat_activity
             WHERE datname = '<application database>' AND pid <> pg_backend_pid()"
   ```
   Record whether that database has a connection open under a role other
   than this application's own runtime/developer role or the executing
   role -- `0004`'s own pre-check (D-2R stage (2)) refuses outright, before
   changing anything, if it does. **Provision a throwaway application for
   this check only (§3.4).** Then open one connection under *its* runtime
   role deliberately (to exercise the live-connection path this design
   memo exists for -- with the runtime credentials recorded at
   provisioning time, or simply by letting the Data service serve one
   request against it) and deprovision *that* application (§3.4's own
   reverse, `0004_deprovision_application.sql`, or the break-glass
   `deprovision` subcommand, §7). Confirm the script completes in a single
   pass, with no retry. **Never run this item against an application in
   service** -- deprovision is irreversible (§10.6).

   If it stops instead, what is left behind and what to do next follows
   design §4.1:

   | Stopped at | State left behind | Next step |
   |---|---|---|
   | the pre-check (stage (2)) | nothing changed -- `ALLOW_CONNECTIONS` stays true, no membership, database and registry row both intact | close the connection identified by the read above, then re-run `0004` (the exception itself is a fixed message and names no role, by design) |
   | `--lock-timeout` cancels stage (3) or stage (4) itself | the temporary self-grant of whichever role was already granted (possibly neither, if the cancel hit the first `GRANT` -- then nothing changed, same as the row above) left standing, but `ALLOW_CONNECTIONS` is still **true** (unlike the row below, where it already reads `false`) -- `--lock-timeout` applies to the whole psql session, so it can cancel these auto-committing statements individually (design §10.7's deprovision row) | same as below: re-run `0004` to complete it, or abandon with the same two `REVOKE`s (a no-op for a role that was never granted) (no `ALTER DATABASE` to revert, since it never ran) |
   | stage (4) onward, up to and including `DROP DATABASE` | database left unreachable (`ALLOW_CONNECTIONS false`); the temporary self-grant membership left standing; registry row intact | re-run `0004` to complete it, or to abandon: `ALTER DATABASE <database> WITH ALLOW_CONNECTIONS true` and `REVOKE <runtime role> FROM CURRENT_USER` and `REVOKE <developer role> FROM CURRENT_USER` (both, if both grants ran), run by `mitatedbsvc_provision` itself |
   | after `DROP DATABASE`, before `DROP ROLE`/`finish_deprovision_application` | database gone; the two roles, their temporary self-grant membership, and the registry row left behind | re-run `0004` -- it completes |

   **Whether Cloud SQL's own management connections (e.g. a
   `cloudsqladmin`-owned session) count toward the pre-check's "connection
   under a role other than runtime/developer/executing" test is unexercised
   against a real instance (`absent`)** -- no runbook step, migration,
   configuration, or code in this repository depends on `cloudsqladmin`;
   every occurrence of the name is prose recording this same gap.
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
  - **Correction note (2026-09-19, design `docs/design/
    DEPROVISION_FORCED_DROP_V0_1.md` v1.0 M-3; this record is not
    rewritten, only annotated -- `docs/work-orders/OPERATING_CONDITIONS.md`
    §1.8 item 56/57)**: this `GRANT` had no effect on its own --
    `mitatedbsvc_provision` is `NOINHERIT` (`migrations/
    0001_bootstrap_platform.sql`), so holding `pg_signal_backend`
    membership without `WITH INHERIT TRUE` (never granted here) does
    nothing for it. The membership may be `REVOKE`d; the role able to do
    so is bootstrap `postgres`, the role that ran the `GRANT` above --
    `mitatedbsvc_provision` itself never held admin option on
    `pg_signal_backend` and cannot revoke its own membership in it (unlike
    `0004`'s own temporary self-grant, which the executing role can
    self-revoke because it holds admin option on the role it grants,
    M-13). D-2R (adopted above, item 3) does not use `pg_signal_backend`
    at all.
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

## 10. Gate-0 read and platform upgrade procedure

This is the operator procedure for the Gate-0 read (10 items) that runs
BEFORE any platform upgrade of the Data/Control services, and for the
upgrade itself (platform migrations
`0005`/`0007`/`0011`/`0012`/`0013`/`0014`/`0016`, per-application
upgrades,
declarations, removal of the legacy base-URL env
vars, restart, health, traffic, rollback). The judgment vocabulary
(confirmed / blocked / unknown, plus the `remediation-required` note) and
the 10 items themselves are defined in `docs/design/MITATEDB_PLATFORM_
READONLY_INVENTORY_V0_1.md` sections 1.1/1.2 -- this section does not
restate them.

The section runs in four stages, in this order:

| Stage | What happens | Where |
|---|---|---|
| 1. First read | the platform-layer read and `ops inventory`, then the overall judgment and the report. An item that is not confirmed makes Gate-0 not ready, and the report to the requesting side is `blocked—platform remediation required` with the breakdown | §10.1-§10.5, §10.9 |
| 2. Platform remediation | the numbered set of platform migrations, the per-application upgrades, the declarations, the env-only change (including the move of traffic onto that revision on a service whose traffic is pinned, and the removal of a tag that keeps a Data revision out of §10.4.3's agreement -- no percentage moves, but it is the same traffic projection), and the reserved-connection count. **This stage is gated by the isolated proof, the independent audit and the requester's approval -- never by Gate-0 ready** | §10.10.1 |
| 3. Second read | the whole first read again, on every one of the 10 items. **Gate-0 is ready only when all 10 come back confirmed**; an `unknown` that survives this read stops the procedure and is never carried forward as a warning | §10.10.2 |
| 4. Candidate | deploy the candidate, restart, health, traffic, rollback. **Gate-0 ready gates exactly this stage** | §10.10.3 |

- **The read (§10.1-§10.5) never changes production state**: no DDL, no
  DML, no declaration replacement, no restart, no traffic change, no API
  enablement. Stages 2 and 4 do change state, and only they.
- **Against production, nothing in stage 2 or stage 4 runs until three
  things are true: the same procedure has been proved against the isolated
  pair, that evidence has passed an independent audit, and the requester
  has approved.** All three, not the acceptance record in §10.8 alone.
- **Nothing in this section has been run against production yet.** The
  tables in §10.6/§10.7 and the procedure in §10.10 are drafts until
  §10.8's acceptance record is filled in.
- Every value below is written as a shape (`<project>`, `<region>`,
  `<service>`, `<revision>`, `<instance-connection-name>`, ...). An
  operator supplies the real value at run time only -- never into this
  repository and never into a report (`docs/security/public-repository-
  policy.md`).
- **`unknown` never proceeds (fail-closed)** -- it is never downgraded to
  a warning and carried forward. What it forbids proceeding to is stage 4:
  an `unknown` in the first read is what stage 2 exists to clear, and it
  has to be gone in stage 3 before any candidate is deployed or any
  traffic is moved.

### 10.1 Preconditions and working environment

- **Where to run**: the root of a checkout of the candidate HEAD, with
  `PYTHONPATH=MitateDB-api/src` (the same shape §7 documents).
- **psql**: a PostgreSQL 16-or-newer client. Every `ops` subcommand that
  starts psql reads `psql --version` first and stops with a fixed message
  if the binary is missing, unreadable, or older than 16.
- **Do not export libpq connection variables.** On the path that starts
  psql, `ops` builds the subprocess environment from the DSN itself and
  refuses to run when the parent shell still carries a connection-setting
  variable the DSN does not override (`PGHOST`, `PGPORT`, `PGDATABASE`,
  `PGUSER`, `PGPASSWORD`, `PGPASSFILE`, `PGSSLMODE`, `PGSSLROOTCERT`,
  `PGOPTIONS`, `PGSERVICE`, `PGSERVICEFILE`, `PGSYSCONFDIR` and the rest
  of the same table). The refusal names the variable, never its value. Put
  what you need into the DSN (`passfile=`, `sslrootcert=`, ...) or unset it
  first.
- **That refusal covers only the psql invocations, not the psycopg
  connections.** It is built where a psql subprocess environment is built,
  so it guards exactly the three subcommands that start psql
  (`apply-platform-migration`, and the per-application scripts that
  `upgrade-applications` and `deprovision` run), and the `psql --version`
  check sits on the same path. **Every other subcommand connects with
  psycopg directly and neither check applies**: `inventory`,
  `show-declarations`, `declare-surfaces`, `declare-process-ceilings`,
  `declare-coalescing-window`, `set-platform-timeouts`,
  `verify-declarations` and `upgrade-status` -- and so do the registry
  connections `upgrade-applications` and `deprovision` themselves open
  before any script runs. On an unguarded connection libpq quietly fills
  any connection setting the DSN omits from the parent shell's own `PG*`
  variables -- a different database, read and reported as if it were the
  intended one, with nothing in the output to show it. **So the rule above
  is the operator's own to keep for every subcommand in this section, not
  something the tool enforces for most of them.** If this shell ran §3
  (which exports `PGHOST` and `PGPORT`), `unset PGHOST PGPORT` before
  entering this section, or use a fresh shell:

  ```sh
  unset PGHOST PGPORT PGDATABASE PGUSER PGPASSWORD PGOPTIONS PGSERVICE
  ```
- **Run the Cloud SQL Auth Proxy in unix-socket mode for this section**:

  ```sh
  cloud-sql-proxy --unix-socket <socket-dir> <instance-connection-name> &
  ```

  The socket lands at `<socket-dir>/<instance-connection-name>/`, so the
  provision DSN has the form `host=<socket-dir>/<instance-connection-name>
  port=5432 dbname=mitatedb_platform user=mitatedbsvc_provision
  passfile=<passfile path>` -- the same unix-socket shape §5
  describes for the in-container path. `ops inventory` compares the
  instance connection name it is given against the socket path inside the
  DSN and reports `match`/`mismatch`/`unknown` only, never the path
  itself. **Over a TCP DSN (`host=127.0.0.1 ...`, the shape §2/§3/§7 use
  for bootstrap and break-glass work) there is nothing in the connection
  string that identifies which Cloud SQL instance is on the other end, so
  item (1) stays `unknown` and Gate-0 cannot reach ready.** If the
  `mitatedb-provision-dsn` secret (§4) holds a TCP DSN, re-record it in
  unix-socket form before running this section. Do not print the DSN to
  check its shape -- `inventory`'s own `connection.comparison` value is
  the check.
- **Where that passfile comes from.** The secret itself keeps §5's
  password-bearing form; the `passfile=` form above is derived from it
  once, at the start of this section, and lives only as long as this
  section does. Create the private directory and the converter first,
  under a `umask` that leaves nothing group- or world-readable, outside
  every git work tree:

  ```sh
  umask 077
  MITATEDB_PROVISION_PASSFILE="$(mktemp -d)/provision.passfile"
  export MITATEDB_PROVISION_PASSFILE
  ```

  Then save this file as
  `<the directory that path names>/dsn-to-passfile.py` (an editor, or a
  `cat >` heredoc typed at the left margin -- it carries no secret of its
  own, only the conversion):

  ```python
  import os
  import sys
  from psycopg.conninfo import conninfo_to_dict, make_conninfo

  params = conninfo_to_dict(os.environ["MITATEDB_PROVISION_DSN"])
  password = params.pop("password", None)
  if password is None:
      print(make_conninfo(**params))
      sys.exit(0)

  def field(value):
      return str(value).replace("\\", "\\\\").replace(":", "\\:")

  path = os.environ["MITATEDB_PROVISION_PASSFILE"]
  line = "*:*:" + ":".join(field(params.get(key, "*")) for key in ("dbname", "user"))
  fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
  with os.fdopen(fd, "w") as handle:
      handle.write(line + ":" + field(password) + "\n")
  params["passfile"] = path
  print(make_conninfo(**params))
  ```

  The converter writes libpq's own single line
  (`*:*:<dbname>:<user>:<password>` -- host and port are wildcards, so the
  line matches however libpq names a unix-socket host when it looks the
  password up; `:` and `\` inside a field are escaped the way libpq
  requires) at file mode `0600`, and
  prints the SAME DSN with `password=` replaced by `passfile=` -- so the
  password reaches one file and nothing else: not the screen, not argv
  (the value stays in the environment variable both this script and §10.3
  already use), not the shell history (the Shell rule below), and not
  `set -x` output (`set +x` inside the subshell). Nothing here prints the
  password-bearing DSN, and the printed passfile form is captured by a
  command substitution rather than shown -- §10.3's own subshell is where
  it runs, one line after the fetch. A DSN that already names a
  `passfile=` passes through with the same parameters, so running it
  twice is safe.
  **Both `ops` connection paths accept the result**: psycopg reads
  `passfile=` itself, and the psql path turns each DSN parameter into its
  own libpq variable, `passfile` into `PGPASSFILE` (which is why the
  refusal above does not fire on the five variables step 2 and step 11
  export). Confirm the passfile form authenticates on the isolated pair
  before using it against production, and use this passfile only with
  the DSN it was derived from, against the pair this run is reading. **When this section ends, whether it completed or stopped,
  remove that file and its directory** (`rm -f
  "$MITATEDB_PROVISION_PASSFILE"` and then the directory `mktemp -d`
  created, converter included) and leave no copy anywhere else: it is the
  only place outside Secret Manager that carries the provision password.
- **gcloud**: run as the operator's existing principal, with prompts
  disabled, and never enable an API:

  ```sh
  export CLOUDSDK_CORE_DISABLE_PROMPTS=1
  export CLOUDSDK_CORE_LOG_HTTP=false
  ```

  Pass `--quiet` on every gcloud invocation and never pass `--log-http`.
  **A disabled API, insufficient permission, or a state that needs an
  interactive answer makes the affected item `unknown`** -- never enable
  the API and read again. A non-zero gcloud exit status makes every item
  that depends on that read `unknown`.
- **Shell**: do not use `set -x`. Leave no history (`set +o history` under
  bash, or a fresh shell started with an empty `HISTFILE`).
- **Where the evidence goes**: a private directory on the operator's own
  machine, outside every git work tree. Confirm that when you create it:

  ```sh
  mkdir -m 700 <evidence-dir>
  git -C <evidence-dir> rev-parse --is-inside-work-tree 2>/dev/null && echo "STOP: inside a git work tree"
  ```

  If `STOP` prints, pick another location. Evidence files are made by
  redirecting stdout; `inventory` never writes a file of its own. The
  format is JSON (a gcloud `--format=json(...)`/`value(...)` projection,
  or `inventory`'s own single JSON line).

### 10.2 Isolated check of `--quiet`'s own default answer (gate before production)

Before §10.4 is run against production even once, confirm and record the
following in an isolated project. **With no record, or with a record
showing that an API was enabled, the production read does not start.**

1. In the isolated project pick one API that is currently disabled
   (`<disabled-api>`; if one of the Cloud Run Admin / Artifact Registry /
   Secret Manager APIs §10.4 uses is disabled there, use that one).

   ```sh
   gcloud services list --enabled --project=<isolated-project> --quiet \
     --filter='config.name=<disabled-api>' --format='value(config.name)'   # must be empty
   ```

2. In a shell carrying §10.1's two environment variables, run a read
   command that needs that API, with `--quiet`, and record its exit
   status.
3. Run step 1's command again and confirm the output is still empty (the
   API was not enabled).
4. Run §10.4's projection expressions (the `--format`/`--flatten`/
   `--filter` shapes in the table below) against an isolated revision and
   confirm every field comes back non-empty. If one is empty, fix the
   expression and re-version this section before going to production.

Record (filled in by the operator; no real values):

| Date | gcloud version | API class used | Exit status of step 2 | Still not enabled (step 3) | Every projection non-empty (step 4) | Recorded by |
|---|---|---|---|---|---|---|
| (empty) | | | | | | |

### 10.3 Passing the DSN

- The DSN travels in the environment variable `MITATEDB_PROVISION_DSN`
  only. `inventory`, `apply-platform-migration`, `upgrade-applications`
  and `deprovision` all take it from there and none of them accepts a DSN
  argument.
- Forbidden: `set -x`, gcloud HTTP logging, letting the DSN reach shell
  history, expanding the DSN onto argv (including `psql
  "$MITATEDB_PROVISION_DSN"`), and `echo`/`printf`/writing the DSN to a
  file. (§10.1's converter writes the password alone to its passfile,
  never the DSN.)
- Fetch it from Secret Manager by command substitution straight into the
  variable, and **keep the variable inside the subshell that runs the
  subcommand**, so it is not still in the parent shell while §10.4's
  gcloud reads run:

  ```sh
  (
    set +x
    MITATEDB_PROVISION_DSN="$(gcloud secrets versions access latest \
      --secret=<provision-dsn-secret> --project=<project> --quiet 2>/dev/null)" || exit 1
    export MITATEDB_PROVISION_DSN
    MITATEDB_PROVISION_DSN="$(PYTHONPATH=MitateDB-api/src python3 \
      "$(dirname "$MITATEDB_PROVISION_PASSFILE")/dsn-to-passfile.py")" || exit 1
    PYTHONPATH=MitateDB-api/src python3 -m mitatedb_api.ops <subcommand> ...
  )
  ```

  `2>/dev/null` keeps a failed fetch from printing gcloud's own error text
  to the screen. A failed fetch ends the subshell with status 1, and every
  item that depended on it is `unknown`. The second assignment is §10.1's
  own converter: what the subcommand then gets is the passfile form, and
  the password-bearing form never leaves this subshell.

### 10.4 Platform-layer read

**Write only the projected fields into the evidence.** Never write a whole
revision spec (`describe`'s default output, a bare `--format=json`, or
`--format=yaml`). Project env NAMES only; read an env VALUE only for the
env names in the allow-table below. For secrets, keep the env name and the
version state only -- never the secret's name or value.

The services are Data (`mitatedb-data`, §6.1) and Control
(`mitatedb-ctrl`, §6.2). On a deployment that runs Control, do each read
below for both.

**Projection table** (use the expressions §10.2 step 4 confirmed against
an isolated revision):

| What is read | Command shape | Projection |
|---|---|---|
| Traffic allocation | `gcloud run services describe <service> --project=<project> --region=<region> --quiet` | `--format='json(status.traffic[].revisionName,status.traffic[].percent,status.traffic[].tag,status.latestReadyRevisionName)'` |
| Revision basics | `gcloud run revisions describe <revision> --project=<project> --region=<region> --quiet` | the three annotation keys are projected BY NAME (never the whole `metadata.annotations` map), see the command below |
| Ready condition | `gcloud run revisions list --service=<service> --project=<project> --region=<region> --quiet --flatten='status.conditions[]' --filter='metadata.name=<revision> AND status.conditions.type=Ready'` | `--format='value(status.conditions.status)'` |
| Env names in every container | `gcloud run revisions list --service=<service> ... --quiet --flatten='spec.containers[].env[]' --filter='metadata.name=<revision>'` | `--format='value(spec.containers.env.name)'` |
| Value of an allow-table env | the same, with `--filter='metadata.name=<revision> AND spec.containers.env.name=<allowed-env>'` | `--format='value(spec.containers.env.value)'` |
| Secret state per env name | the "secret state" shape below | env name and state only |
| Build provenance | `gcloud artifacts docker images describe '<image>@<digest>' --project=<project> --quiet --show-provenance` | `--format='json(provenance_summary)'` |
| Local outcome | each command's own exit status | one line appended to `<evidence-dir>/exit-status.txt` |

Name the three annotation keys in the projection itself. **Do not project
`metadata.annotations` as a whole and narrow it afterwards**: the whole map
also carries `serving.knative.dev/creator` and `serving.knative.dev/
lastModifier`, which are operator email addresses (personal data), and a
projection that reads them at all can leak them into a shell buffer or a
partially written file:

```sh
gcloud run revisions describe <revision> --project=<project> --region=<region> --quiet \
  --format='json(metadata.name,metadata.creationTimestamp,metadata.annotations."autoscaling.knative.dev/maxScale",metadata.annotations."autoscaling.knative.dev/minScale",metadata.annotations."run.googleapis.com/cloudsql-instances",spec.serviceAccountName,spec.containers[].image,status.imageDigest)' \
  > <evidence-dir>/<service-label>-<revision-label>.json
```

**Secret state** (the secret's name stays in a shell variable; the
evidence keeps the env name and the state only):

```sh
gcloud run revisions list --service=<service> --project=<project> --region=<region> --quiet \
  --flatten='spec.containers[].env[]' \
  --filter='metadata.name=<revision> AND spec.containers.env.valueFrom.secretKeyRef.name:*' \
  --format='value(spec.containers.env.name,spec.containers.env.valueFrom.secretKeyRef.name,spec.containers.env.valueFrom.secretKeyRef.key)' \
| while IFS="$(printf '\t')" read -r env_name secret_name secret_version; do
    state="$(gcloud secrets versions describe "${secret_version:-latest}" --secret="$secret_name" \
      --project=<project> --quiet --format='value(state)' 2>/dev/null)" || state=unreadable
    printf '%s\t%s\n' "$env_name" "${state:-unreadable}"
  done > <evidence-dir>/<service-label>-<revision-label>-secret-states.tsv
```

**Env-value allow-table** (non-secret numeric settings that are inputs to
a judgment -- the value of an env name NOT in this table is never read).
The NEW/OLD basis distinction the first two rows below read applies to
Data only; Control carries no basis of its own (§10.4.3, D-5: its
per-process demand is a fixed floor on either basis):

| Env name | Item it feeds | When unset |
|---|---|---|
| `MITATEDB_WORKERS` | a revision's own worker count and NEW/OLD-basis status for item (8) (§10.4.3) | that revision's own worker count is `WEB_CONCURRENCY`'s own value (the next row), or 1 when it carries neither; its basis is OLD-basis unless its image digest is a NEW-basis digest (in which case the digest and the `MITATEDB_WORKERS` presence disagree, and §10.4.3's own basis rule applies) |
| `WEB_CONCURRENCY` | an OLD-basis revision's own worker count for item (8), when it carries no `MITATEDB_WORKERS` (§10.4.3) | that revision's own worker count is 1 |
| `MITATEDB_THREAD_LIMIT` | `inventory --thread-limit` for item (8)'s NEW-basis processes (§6.5) | item (8) is `unknown` for the parts that depend on it -- the code default is never substituted |
| `MITATEDB_CONTROL_WORKERS` | Control's own process ceiling/total for item (8) (§10.4.3; always 1 on a NEW-basis Control revision, which requires this name) | on a NEW-basis Control revision, that revision's own Control process count cannot be established (the name is required to start); on an OLD-basis Control revision, that revision's own worker count is `WEB_CONCURRENCY`'s own value, or 1 when it carries neither |
| `MITATEDB_MAX_CONCURRENCY` | `inventory --concurrency` for item (8)'s OLD-basis processes only (§10.4.3) | item (8) is `unknown` for the parts that depend on it, unless §10.4.3's own declared-default exception applies (an OLD-basis revision counted toward item (8), including one that takes no traffic but has `minScale` 1 or more) -- the code default is never substituted for `--thread-limit` |
| `MITATEDB_PLATFORM_POOL_SIZE` | whether a revision counted toward item (8) forces `--thread-limit`/`--data-process-count-old-basis` both omitted for the whole read (§10.4.3) | no effect by itself -- only WHETHER the name is present is read, never its value (F-16 itself never reads it either, an existing gap this runbook does not close) |

Note that §6.1's own deploy command does not set
`MITATEDB_MAX_CONCURRENCY`, since it deploys the current, NEW-basis code;
`MITATEDB_MAX_CONCURRENCY` is only ever read from an OLD-basis revision
still running the pre-existing, `--concurrency`-sized pool.

**Env names that must be present** (if the env-name list for a revision
does not contain these, the projection is not being read and every item
depending on that revision is `unknown`):

| Service | Env names |
|---|---|
| Data | `MITATEDB_PLATFORM_DSN`, `MITATEDB_CREDENTIAL_PEPPER`, `MITATEDB_SERVE_APPS` |
| Control | `MITATEDB_CONTROLPLANE_DSN`, `MITATEDB_CREDENTIAL_PEPPER`, `MITATEDB_CONTROL_CREDENTIAL_PEPPER` |

**What makes an item `unknown` (all items)**: a non-zero gcloud exit
status; a projected field that comes back empty (an empty projection is
never read as "absent"); an empty env-name list; a missing must-be-present
env name; an unset allow-table env whose own "When unset" cell says the
item is `unknown`.

#### 10.4.1 Item (1) isolated/production pair

1. For every Data/Control revision that carries traffic (percent greater
   than 0, or a tag), read `run.googleapis.com/cloudsql-instances`.
2. Only when every one of those revisions carries the SAME value AND that
   value names exactly one connection name, pass it to §10.5's
   `inventory` as `--cloud-sql-connection-name <instance-connection-
   name>`. If the value is unreadable, differs between revisions, or names
   more than one connection, omit the argument and item (1) is `unknown`.
3. Item (1) is confirmed only when `inventory`'s `connection.comparison`
   is `match` (`connection.judgment` confirmed). **`mismatch` (the
   database being read is not the one the revisions use) and `unknown`
   both stop here** -- do not go on to §10.6 and later.
4. Record in the evidence whether this read was against the isolated or
   the production pair.

#### 10.4.2 Item (7) legacy base-URL env vars

Env names in question: `MITATEDB_DATA_BASE_URL`,
`MITATEDB_CONTROL_BASE_URL`.

1. **Current revision / template**: if either name appears in the env
   names (across every container) of a traffic-carrying revision or of the
   service's current template, item (7) is confirmed +
   `remediation-required`. If neither appears, it is confirmed.
2. **New candidate / next template**: if the candidate is not deployed at
   the time of the read, read the deploy command §10.10 step 13 will run
   (the candidate HEAD's own §6.1/§6.2 shape, plus the env it passes) as
   the next template.
   - If the deploy replaces env wholesale (both `--set-env-vars` and
     `--set-secrets`, or `--clear-env-vars` with `--clear-secrets`), judge
     on the env names that command passes.
   - **If the deploy carries existing env forward** (`--update-env-vars`,
     `--update-secrets`, or a deploy with no env flag at all), apply that
     command's additions and removals to the env names read in step 1 and
     judge on the result. **Without an explicit removal of the legacy
     names, item (7) is blocked** -- the removal is the flag

     ```text
     --remove-env-vars=MITATEDB_DATA_BASE_URL,MITATEDB_CONTROL_BASE_URL
     ```

     (one argument, no line break: a break turns `BASE_URL` into a
     positional argument and gcloud reads it as the service name) or an
     equivalent.
   - If either name survives in the result, item (7) is blocked.
3. After the candidate is deployed (§10.10 step 13), read the candidate
   revision's env names again; if either name is still there, item (7) is
   blocked.
4. The presence of either name on the previous-Ready rollback revision is
   recorded in the evidence only -- it does not block, and that revision's
   env is not rewritten.

#### 10.4.3 Item (8) platform-layer inputs

Read item (8)'s arguments as follows and pass them to §10.5. If any one of
them is not established, omit that argument -- the part of item (8) that
depends on it is then `unknown`. Note that `inventory` rejects seven
inconsistent input shapes with exit status 1, before opening a database
connection, rather than judging them: `--control-not-deployed` given
together with `--control-process-ceiling`; `--control-not-deployed` given
together with `--control-process-count-total`; `--data-process-count-
total` smaller than `--data-process-ceiling`; `--control-process-count-
total` smaller than `--control-process-ceiling`; `--data-process-count-
old-basis` greater than `--data-process-count-total`; `--data-process-
count-total` minus `--data-process-count-old-basis` less than
`--data-process-ceiling` (the new-basis remainder must itself be at least
the ceiling); and `--concurrency` given while `--data-process-count-
old-basis` is `0`.

**A revision's basis** (NEW or OLD, design
docs/design/MITATEDB_INVENTORY_DEMAND_BASIS_V0_1.md D-4) is decided from
TWO facts together: its image digest (§10.4.4's
own digest read; a NEW-basis digest is one built from the code that
declares `--thread-limit`/`--data-process-count-old-basis` below) and
whether its env carries `MITATEDB_WORKERS` at all. A revision is NEW-basis
only when both agree (a NEW-basis digest that carries `MITATEDB_WORKERS`);
it is OLD-basis only when both agree the other way (a pre-existing digest
with no `MITATEDB_WORKERS`). **When a revision's digest and its
`MITATEDB_WORKERS` presence disagree, omit `--data-process-count-old-
basis` (and, with it, `--concurrency`) for the whole read** -- this
runbook cannot tell that revision's own basis from the evidence it reads,
and guessing risks undercounting a real OLD-basis process's demand.

| Argument | How it is read |
|---|---|
| `--thread-limit` | the `MITATEDB_THREAD_LIMIT` value carried by every NEW-basis revision counted below, INCLUDING one that cannot take traffic (that revision's own real demand does not depend on whether it currently serves), plus the candidate (whose value is the one step 13's own deploy command carries, §10.10.3). If they differ, use the largest. **Omit the argument when even one of those revisions has the name unset** -- an unset NEW-basis revision runs on the code's own default (`DEFAULT_THREAD_LIMIT`), which is not read from the platform |
| `--data-process-count-old-basis` | the WORST-CASE OLD-basis Data process count (the total computed below) -- `0` when no OLD-basis revision is counted |
| `--concurrency` | the `MITATEDB_MAX_CONCURRENCY` value carried by every OLD-basis revision counted in `--data-process-count-old-basis`, INCLUDING one that cannot take traffic (an OLD-basis process's own real demand does not depend on whether it currently serves). If they differ, use the largest. **Pass this only when `--data-process-count-old-basis` is 1 or more; omit it when that count is `0`, and also omit it (leaving that part of item (8) `unknown`) when it is 1 or more and even one of those revisions has the name unset.** **Exception**: when an OLD-basis revision counted toward item (8) (including one that takes no traffic but has `minScale` 1 or more) carries no `MITATEDB_MAX_CONCURRENCY` at all, its value may instead be declared from the code default in effect at the commit its own image digest was built from -- record that commit and the file/line the default came from in the evidence table's addend row for this value. **The exception applies only when BOTH of the following are confirmed at that commit, and does not apply (the argument is omitted, `unknown`) when either one cannot be confirmed**: (i) that commit's own build input Dockerfile does not set `MITATEDB_MAX_CONCURRENCY`, `WEB_CONCURRENCY`, `MITATEDB_PLATFORM_POOL_SIZE` or `MITATEDB_THREAD_LIMIT` with an `ENV` instruction; (ii) that commit's own `config.py` carries a default value for `max_concurrency`. Disclosure: a declared default that is wrong undercounts demand, and nothing this runbook runs checks a declared default against anything actually deployed. This exception does not apply to `--thread-limit`: an unset `MITATEDB_THREAD_LIMIT` on a NEW-basis revision is never filled in, by declared default or otherwise |
| `--data-process-ceiling` | the NEW candidate Data revision's own process ceiling: its `--max-instances` (i.e. `autoscaling.knative.dev/maxScale` once deployed) times its `MITATEDB_WORKERS` (§6.5) -- this is the value compared against the `process_ceilings` declaration |
| `--data-process-count-total` | the WORST-CASE Data process count across BOTH bases: the sum, over every revision (OLD-basis and NEW-basis alike) that can serve at the same time, of that revision's `autoscaling.knative.dev/maxScale` times its worker count, plus the candidate's own ceiling (the total computed below). **Never the number of instances or processes running at the moment of the read** -- that number is a snapshot, and passing it makes the demand arithmetic too small, so item (8) can come back confirmed on a database that PostgreSQL's own `CONNECTION LIMIT` refusal would hit under load |
| `--control-process-ceiling` | the same as `--data-process-ceiling`, for Control, with `MITATEDB_CONTROL_WORKERS` (always 1) in place of `MITATEDB_WORKERS` |
| `--control-process-count-total` | the same as `--data-process-count-total`, for Control |
| `--control-not-deployed` | pass this INSTEAD of both Control arguments, and only when no Control process is deployed at all. It is the only way to omit them; it excludes Control's own roles from item (8)'s `CONNECTION LIMIT = -1` check, from the demand arithmetic, and from the declaration comparison, and puts `control_deployed: false` in the output |
| `--reserved-connections` | `superuser_reserved_connections` plus `reserved_connections` plus whatever Cloud SQL itself reserves. Omit until the source (value and document) for the Cloud SQL reserve is established |

**A NEW-basis revision's worker count** is the `MITATEDB_WORKERS` value it
carries (`MITATEDB_CONTROL_WORKERS` on Control), read from the revision's
env the same way as `MITATEDB_MAX_CONCURRENCY`. **An OLD-basis revision's
worker count** is its `WEB_CONCURRENCY` value (uvicorn's `--workers` falls
back to it on an image whose `CMD` does not pass `--workers`), or `1` when
it carries neither. If the value read is not a positive integer, omit the
total.

**Cases that leave `--data-process-count-old-basis`/`--concurrency`/
`--thread-limit` omitted** (item (8) then `unknown` for the parts that
depend on them):

- a `MITATEDB_PLATFORM_POOL_SIZE`-carrying revision is among those
  counted (that env overrides the pool size F-16 itself never reads
  either -- an existing gap this runbook does not close),
- an OLD-basis revision carries `MITATEDB_THREAD_LIMIT`, or its own
  `concurrency` is below 6 (its real api-role demand can then exceed the
  `2 × concurrency` floor `ops inventory` assumes for an OLD-basis
  process),
- a revision's digest and its `MITATEDB_WORKERS` presence disagree (the
  basis check above),
- a NEW-basis revision does not carry `MITATEDB_THREAD_LIMIT`,
- an OLD-basis revision counted toward item (8) has an attested source ref
  that does not carry the pool-sizing shape the `2 x concurrency` floor
  above assumes. Confirm all three of the following at that ref, or omit
  `--data-process-count-old-basis` (and, with it, `--concurrency`) for the
  whole read: `http.py`'s `create_app` defaults `thread_limit` to
  `DEFAULT_THREAD_LIMIT` (4) (`git show <source-ref>:MitateDB-api/src/
  mitatedb_api/http.py | grep DEFAULT_THREAD_LIMIT`); `main.py` builds the
  platform pool's own default size by calling `config.role_pool_size`
  (`git show <source-ref>:MitateDB-api/src/mitatedb_api/main.py | grep
  role_pool_size`); and that `role_pool_size` returns the declared
  `max_concurrency` (`git show <source-ref>:MitateDB-api/src/mitatedb_api/
  config.py | grep -A3 'def role_pool_size'`).

**Disclosure.** `ops inventory` cannot check that a declared OLD-basis
process count is itself correct: a wrong, too-small declaration
undercounts demand.

**Demand is counted per basis.** `ops inventory` counts a NEW-basis
process's connection demand from `role_pool_size(--thread-limit)` -- the
SAME per-process floor F-16 uses (§6.5) -- and an OLD-basis process's
demand from its own declared `--concurrency`, adding the two together
(design docs/design/MITATEDB_INVENTORY_DEMAND_BASIS_V0_1.md D-2). At the
default thread limit (4) and the default OLD-basis `concurrency` (32), a
rollout of one OLD-basis process plus `W` NEW-basis processes has an api
demand of `64 + 12W`: confirmed against `0014`'s 132 through `W = 5`,
blocked at `W = 6` (design docs/design/MITATEDB_INVENTORY_DEMAND_BASIS_V0_1.md
§5.1).

**How the worst-case total is computed** (per service):

1. From §10.4's traffic projection, list the revisions with percent
   greater than 0, plus the revisions with percent 0 that carry a tag (a
   tag URL can start an instance too). A revision that appears on several
   rows is counted once.
2. From the service's revision list, add the revisions not in step 1 whose
   `autoscaling.knative.dev/minScale` is 1 or more.

   ```sh
   gcloud run revisions list --service=<service> --project=<project> --region=<region> --quiet \
     --format='value(metadata.name,metadata.annotations."autoscaling.knative.dev/minScale")'
   ```

3. Decide each revision's own basis (above) for every revision from steps
   1-2, and for the candidate. **If any one revision's digest and
   `MITATEDB_WORKERS` presence disagree, omit `--data-process-count-old-
   basis` (and, with it, `--concurrency`) for the whole read** (the
   argument table above) -- Data is the only service that argument is
   ever read for.
4. Add the candidate, on the NEW basis: the `--max-instances` value of the
   deploy command §10.10 step 13 will run, times the `MITATEDB_WORKERS`
   value that command sets. Once the candidate is deployed, read its
   `autoscaling.knative.dev/maxScale` and its `MITATEDB_WORKERS` back; if
   either differs from the command's value, redo the Gate-0 read.
5. Read `autoscaling.knative.dev/maxScale` and the worker count (above)
   for each revision from steps 1-2. **If even one `maxScale` is empty or
   not a positive integer, omit the total** -- the Cloud Run default is
   never substituted.
6. `--data-process-count-old-basis` is the sum, over the OLD-basis
   revisions from steps 1-2 only, of `maxScale` times worker count (`0`
   when none). `--data-process-count-total` is that same sum PLUS the sum,
   over the NEW-basis revisions from steps 1-2 and the candidate, of the
   same product.

**How the total is checked**:

- The traffic percentages sum to 100 (if not, the projection is not being
  read, so omit the total).
- Keep the addend table in the evidence (the revision's evidence label,
  which step counted it, its own **basis** column from step 3, its
  `maxScale`, its worker count and their product) and confirm its row
  count equals (number of step-1 revisions) + (number of step-2
  revisions) + 1 for the candidate. **A row whose basis column is left
  empty (the digest/`MITATEDB_WORKERS` mismatch above) means the whole
  total is omitted, not merely that row.** Sum the OLD-basis rows' own
  product TWICE -- once summing the addend table's own basis column by
  hand, once against the `--data-process-count-old-basis` value itself --
  and confirm the two agree, the same way the grand total is checked
  below.
- Compute the total twice and get the same answer (shell arithmetic, and
  either a hand re-read of the addend table or a second operator).
- If the two disagree, or the addend table and the traffic projection
  disagree about revision names, omit the total.

#### 10.4.4 Item (9) build provenance, rollback revision, traffic, secrets

1. **Digest reference**: every traffic-carrying revision and the candidate
   reference `spec.containers[].image` in `@sha256:` digest form. If even
   one container is referenced by tag, item (9) is `unknown`.
2. **Provenance**: for each digest, read §10.4's build-provenance
   projection and keep the source ref and the build input in the
   evidence. If provenance is unreadable (empty, or no attestation), item
   (9) is `unknown`. If two revisions on the same digest carry different
   provenance, item (9) is `unknown`.
3. **Rollback revision**: the traffic-carrying revisions (and their
   allocation) at the time of the Gate-0 read are the rollback target.
   Every one of them must exist with Ready condition `True`. If one is
   absent or not Ready, item (9) is blocked.
4. **Traffic allocation**: keep §10.4's traffic projection in the
   evidence.
5. **Secrets**: in each revision's secret-state file, every env name's
   state is `ENABLED`. An `unreadable` entry makes item (9) `unknown`; a
   `DISABLED`/`DESTROYED` entry makes it blocked.
6. The service account (`spec.serviceAccountName`) goes into the evidence
   only.
7. **Basis of the digest**: for each distinct digest among the revisions
   counted toward item (8) (§10.4.3) that has not already been confirmed
   this way, read `MitateDB-api/src/mitatedb_api/main.py` at the source
   ref item (9)'s own provenance step attested for that digest:

   ```sh
   git show <source-ref>:MitateDB-api/src/mitatedb_api/main.py \
     | grep -n '_workers_from_env(env, "MITATEDB_WORKERS")'
   ```

   That digest is a NEW-basis digest when the ref's own `main.py` calls
   `_workers_from_env` for `MITATEDB_WORKERS` (the function that raises
   when the name is unset, empty or not a positive integer) -- an OLD-basis
   ref carries no such call at all. Record the result (digest, source ref,
   NEW-basis or OLD-basis) in §10.4.3's own addend table, in its **basis**
   column, for every revision on that digest.

#### 10.4.5 Item (10) starting prefix N

Item (10) reads no production state; it is judged on the candidate HEAD's
own repository-side evidence.

1. If there is a record of `MitateDB-api/tests/test_platform_migration_
   reapply.py` passing at the candidate HEAD's SHA (the CI `conformance`
   job's result, or a completion-gate tally line), item (10) is confirmed.
   With no such record it is `unknown`.
2. In the production Gate-0 read, **the only thing done for item (10) is
   to record the starting prefix N that corresponds to the source ref item
   (9) attested for the running revision**:

   ```sh
   git fetch origin <source-ref>
   git ls-tree --name-only FETCH_HEAD MitateDB-api/migrations/ \
     | grep '\.sql$' | grep -v '/0004_deprovision_application\.sql$' | sort
   ```

   N is the number of output lines. Confirm that the output equals the
   first N lines of the candidate HEAD's own list (the same
   `MitateDB-api/migrations/*.sql` sequence in numeric order, minus
   `0004`) and record N in the evidence. If it does not match (a gap, or a
   different name), item (10) is `unknown`.
3. If N is one of the starting points that test excludes
   (`_REAPPLY_EXCLUDED_STARTING_POINTS`, currently `{3, 4, 5, 6}`), there
   is no re-application evidence from that starting point: item (10) is
   blocked, and the upgrade in §10.10 does not start.
4. If item (9) is `unknown` so that no source ref is established, N cannot
   be recorded and item (10) is `unknown`.

### 10.5 DB-layer read (`ops inventory`)

Run it in §10.3's subshell, with §10.4's values as arguments (a shape that
works under bash 3.2 too). **Set the ten variables below in the parent
shell first, from §10.4's own reads** (`CONNECTION_NAME` from §10.4.1, the
nine others from §10.4.3); leave a variable unset for every argument
§10.4 told you to omit, and set `CONTROL_NOT_DEPLOYED` to any non-empty
value only in the case §10.4.3's table describes. **Leave `CONCURRENCY`
unset when `DATA_PROCESS_COUNT_OLD_BASIS` is `0`** (§10.4.3: `inventory`
rejects the pair otherwise) -- set `DATA_PROCESS_COUNT_OLD_BASIS` itself
to `0` explicitly (never leave it unset) to declare that no Data process
is on the old basis:

```sh
(
  set +x
  MITATEDB_PROVISION_DSN="$(gcloud secrets versions access latest \
    --secret=<provision-dsn-secret> --project=<project> --quiet 2>/dev/null)" || exit 1
  export MITATEDB_PROVISION_DSN
  set --
  [ -n "$CONNECTION_NAME" ]             && set -- "$@" --cloud-sql-connection-name "$CONNECTION_NAME"
  [ -n "$THREAD_LIMIT" ]                && set -- "$@" --thread-limit "$THREAD_LIMIT"
  [ -n "$DATA_PROCESS_COUNT_OLD_BASIS" ] && set -- "$@" --data-process-count-old-basis "$DATA_PROCESS_COUNT_OLD_BASIS"
  [ "$DATA_PROCESS_COUNT_OLD_BASIS" != "0" ] && [ -n "$CONCURRENCY" ] && set -- "$@" --concurrency "$CONCURRENCY"
  [ -n "$DATA_PROCESS_CEILING" ]        && set -- "$@" --data-process-ceiling "$DATA_PROCESS_CEILING"
  [ -n "$DATA_PROCESS_COUNT_TOTAL" ]    && set -- "$@" --data-process-count-total "$DATA_PROCESS_COUNT_TOTAL"
  [ -n "$CONTROL_PROCESS_CEILING" ]     && set -- "$@" --control-process-ceiling "$CONTROL_PROCESS_CEILING"
  [ -n "$CONTROL_PROCESS_COUNT_TOTAL" ] && set -- "$@" --control-process-count-total "$CONTROL_PROCESS_COUNT_TOTAL"
  [ -n "$CONTROL_NOT_DEPLOYED" ]        && set -- "$@" --control-not-deployed
  [ -n "$RESERVED_CONNECTIONS" ]        && set -- "$@" --reserved-connections "$RESERVED_CONNECTIONS"
  PYTHONPATH=MitateDB-api/src python3 -m mitatedb_api.ops inventory "$@" \
    > <evidence-dir>/inventory.json 2> <evidence-dir>/inventory.stderr
  echo "inventory $?" >> <evidence-dir>/exit-status.txt
)
```

- An omitted argument leaves the part that depends on it `unknown`. The
  numeric arguments accept positive integers only
  (`--reserved-connections` and `--data-process-count-old-basis` accept 0
  as well). `--data-process-count-old-basis` must not exceed
  `--data-process-count-total`, and `--data-process-count-total` minus
  `--data-process-count-old-basis` must not be less than
  `--data-process-ceiling` -- both refused with exit status 1, before any
  database connection. `--control-not-deployed` is mutually exclusive with
  both Control arguments, and `--concurrency` is mutually exclusive with
  `--data-process-count-old-basis 0` (leave `CONCURRENCY` unset in that
  case, above).
- The output is one JSON line on stdout. Keys against Gate-0 items:
  `connection` -> item (1)'s DB side, `declarations` -> (2), `migrations`
  -> (3), `credentials` -> (4), `ddl_lock` -> (6)'s runtime-settings half,
  `connection_headroom` -> (8). Each of those carries `judgment`
  (confirmed / blocked / unknown) and `remediation_required`;
  `unjudged_items` lists item (5) in full and item (6)'s
  `lock-and-downtime` half with the reason `runbook-acceptance` -- those
  two are judged by §10.8's acceptance record. There is no `ready` key:
  the overall judgment is §10.9's, never this subcommand's.
- Three items carry counts as well, and those counts are what §10.9's
  report quotes: `credentials` carries `total_count`, `enabled_count`,
  `revoked_count` and `must_rotate_count`; `migrations` carries
  `registered_only_count` (applications registered but never
  provisioned); `connection_headroom` carries `control_deployed`.
  `declarations`, `migrations` and `ddl_lock` also carry a `reason` key
  (`null` unless that item is blocked).
- Every connection `inventory` opens carries its own fixed, short
  `lock_timeout` and `statement_timeout`. A read that overruns one of them
  leaves that item `unknown` -- which is what happens when the read races
  a migration or an upgrade, so do not run `inventory` while stage 2 is
  applying anything.
- Exit status: `0` = every item this subcommand judges is confirmed, `2` =
  at least one is blocked/unknown, `1` = the tool itself failed (stderr
  carries a fixed message only) or an input shape was rejected.
  **Exit status `0` is not Gate-0 ready**: the DB layer does not judge
  item (5), item (6)'s lock/downtime half, (7), (9), (10), or item (1)'s
  platform side.
- Item (6)'s runtime-settings half is confirmed only when every target
  role (`mitatedbsvc_api`, `mitatedbsvc_controlplane`,
  `mitatedbsvc_auditreader`, and each application's own runtime/developer
  role) carries a POSITIVE role-level `statement_timeout`. A value of 0, a
  negative value, or a value that cannot be parsed is blocked with the
  fixed reason `statement-timeout-unbounded`; no declaration at all is
  `unknown`. A target role whose `CONNECTION LIMIT` is `-1` (unlimited) or
  which `pg_roles` does not carry leaves the item `unknown` before any
  timeout value is read at all. Migration `0013` is what puts the
  `statement_timeout` on the auditreader and on the application roles, and
  `0012` is what replaces a `-1` `CONNECTION LIMIT` with a finite one
  (§10.10 step 7), so on a deployment where they have not run yet, expect
  item (6) `unknown` in the first read and resolve it in stage 2.
  (2026-09-18: step 7 now ends with `0014`, which sets a finite
  `CONNECTION LIMIT` on the same roles AND on `mitatedbsvc_auditreader`,
  which `0012` never alters -- so a `-1` on the auditreader is resolved
  there too.)
- **An application provisioned by a `0003_provision_application.sql` old
  enough to predate the per-application upgrade ledger, with `0008` not
  yet applied, makes `migrations` blocked with the reason
  `ledger-unreadable`.** `upgrade-status` and `upgrade-applications` fail
  on the same application, so stage 2 cannot resolve it. **Do not start
  §10.10 at all while any application is in that state**; the design
  register in
  `docs/design/MITATEDB_PLATFORM_READONLY_INVENTORY_V0_1.md` section 12.4
  records how that case is handled.

### 10.6 Per-migration compatibility table (item (5))

**This table is a draft. The compatibility judgments are not settled until
the independent review in §10.8 accepts them.** Table version: **6**
(2026-09-29: the `0016` row also states the referential-integrity trigger
its foreign key adds on `credentials` and the cascade an application's own
deprovision carries to `credential_request_rate`. Version 5, 2026-09-29:
adds the `0016` row. Version 4, 2026-09-20, R-57 WP-3:
follows `apply-platform-migration` accepting a run of FILENAMEs and
refusing a solo `0012`/`0013` application that has a later file
redefining its own targets).
Change the table and the version goes up by one and §10.8's acceptance
record goes back to "not accepted".

- Every migration is forward-only; there is no down file. "Rollback" here
  means "move traffic back to the previous Ready revision and keep the
  schema as the migration left it".
- "The rollback target does not contain this migration" means the file is
  absent from `MitateDB-api/migrations/` at that revision's own source ref
  (decided with `git ls-tree`). If the target does contain it, that
  revision was built against the post-migration schema and the row's
  judgment is not needed.
- A source of "fact" is the file's own text or a read of the source at
  that ref. "Inference" is a judgment with its reasoning stated, and it is
  what the review examines.
- **A row that reasons about "that revision's own `config.py`" and the
  like holds only for the refs where that reading is true, so every such
  row states the condition its own judgment depends on in the last
  column.** The rollback target is one specific revision with one attested
  source ref (item (9)), so the check is concrete: read the named file at
  that ref and confirm the condition (§10.10 step 1). **If the condition
  cannot be confirmed at that ref -- including a ref too old to have the
  file at all -- the row is not "compatible" for this run, and item (5) is
  `unknown`.** A rollback target older than the whole range is therefore
  never judged compatible by default.

| Migration | How this procedure treats it | Down / way back | Does a rollback target that lacks it still run on the post-migration schema? | Source | Condition this judgment depends on -- confirm it at the rollback target's own attested source ref |
|---|---|---|---|---|---|
| `0001`, `0002`, `0003` | not applied here (bootstrap / provisioning, §3.1-§3.4) | -- | not applicable | -- | -- |
| `0004_deprovision_application.sql` | never run by an upgrade (only `deprovision` runs it) | **irreversible** (drops the application's database and both of its roles) | not applicable. Running it makes that application unrecoverable; it is not run inside a Gate-0 read or an upgrade | fact (the file's own `DROP DATABASE`/`DROP ROLE`) | -- |
| `0005_application_audit.sql` | applied (platform) | none; not reverted | **compatible**. Adds `mitatedb_registry.application_audit` and the `mitatedbsvc_auditreader` role, grants `mitatedbsvc_api` INSERT on the new table plus USAGE on its sequence, and adds a new SELECT grant for `mitatedbsvc_auditreader` on the EXISTING `mitatedb_registry.control_audit` without narrowing the grant already there (`0002` grants the control plane INSERT on that table) -- it names no existing table in any `ALTER`/`DROP` (fact: the file's own statements and header). A revision that lacks it reads and writes none of the new objects | fact | none: the judgment rests on `0005`'s own statements, so it holds at every ref |
| `0007_platform_declarations.sql` | applied (platform), inside the numbered set. **Re-applying it is idempotent but NOT value-neutral**: it re-sets both roles' `statement_timeout` and `idle_in_transaction_session_timeout` to `5000ms` unconditionally, and it replaces the `audit_writer_roles` declaration row with the pair passed in `--api-role`/`--controlplane-role` (`ON CONFLICT ... DO UPDATE`). Record both before applying and restore them straight afterwards (§10.10 steps 2 and 4) | none; not reverted | **compatible (inference), with one part left unverified**. A pre-`0007` revision does not read `platform_declarations` and reads surfaces from env instead (fact: that revision's own `config.py`). The effect it does feel is the role-level `statement_timeout`/`idle_in_transaction_session_timeout` (5000ms) on `mitatedbsvc_api`/`mitatedbsvc_controlplane`; a role setting applies at login, so sessions that revision opens after the migration carry it while sessions already open keep their own. That revision applied the same two values itself with `SET SESSION`, but only on the audit write connection (fact: that revision's own `application_audit.py`). **Unverified: whether that revision's other queries (registry reads and the like) all finish inside 5 seconds.** Accepting this table at its current version accepts that residual risk -- such a query is cancelled with `canceling statement due to statement timeout` instead of running unbounded | fact + inference, one part unverified | a ref whose `config.py` reads the surfaces from env and performs no `platform_declarations` read, and whose `application_audit.py` applies both timeouts with `SET SESSION` on the audit write connection |
| `0011_process_ceilings.sql` | applied (platform) | none; not reverted | **compatible**. It only widens the `key` CHECK vocabulary. A pre-`0011` revision's declaration read picks known keys by name and ignores a row with an unknown key (`process_ceilings`) (fact: that revision's own `platform_declarations.read_platform_declarations`); a pre-`0007` revision does not read the table at all | fact | a ref whose declaration read selects known keys by name and ignores an unknown key, or a ref that does not read the table at all |
| `0012_role_connection_limits.sql` | applied (platform). **A role whose current `CONNECTION LIMIT` is ABOVE the value this file sets is lowered to it.** No `ops` subcommand prints those current values -- item (8)'s output carries judgment keys only, and `verify-declarations`'s F-16 names a value only inside its own failure message, for the first role that fails -- so read them with a catalog read over the provision DSN and record them before applying (§10.10 step 2). (2026-09-18: `0014_role_connection_limits_rollout.sql` now raises the same roles above these values, so re-applying `0012` ALONE after `0014` lowers `mitatedbsvc_api`, `mitatedbsvc_controlplane` and every EXISTING application's runtime and developer role back to 68 / 20 / 36, and drops `0013`'s `statement_timeout` line from every FUTURE application's roles; `mitatedbsvc_auditreader` is unaffected, because `0012` never alters it. Re-applying `0014` compensates. The set's own order is `0012` -> `0013` -> `0014` -- §10.10's numbered-set note and §10.10.1 step 7) `apply-platform-migration` refuses a lone `0012`; that call must also carry `0013` and `0014` in the same run, and a solo `0012` application is possible only outside the tool, applied directly with `psql`. | none; not reverted | **compatible**. Sets each role's `CONNECTION LIMIT` to a fixed value (68 / 20 / 36) and replaces `begin_provision_application` with the same signature and result columns (fact: `0002`'s and `0012`'s own definitions). An older revision's pool ceiling is at or below the new value (inference) | fact + inference | a ref whose own per-role pool composition, at the concurrency that ref is deployed with, stays within 68 / 20 / 36 -- compute it from that ref's own `config.py` |
| `0013_role_statement_timeouts.sql` | applied (platform). `apply-platform-migration` refuses a lone `0013`; that call must also carry `0014` in the same run, and a solo `0013` application is possible only outside the tool, applied directly with `psql`. | none; not reverted | **compatible (inference)**. Adds a role-level `statement_timeout` (`5000ms`) to `mitatedbsvc_auditreader` and to every application's runtime/developer role, and replaces `begin_provision_application` so future roles get the same setting -- additive; it drops and revokes nothing (fact: the file's own header and statements). (2026-09-18: that still describes `0013` against `0012`, but it no longer holds for a re-application after `0014_role_connection_limits_rollout.sql`: `0013` alone afterwards lowers every FUTURE application's runtime and developer role to `CONNECTION LIMIT` 36 -- the value `0013` inherited from `0012` -- while every EXISTING role keeps its `0014` value and every future role still carries the `statement_timeout`. Re-applying `0014` compensates) A revision that lacks it passes its own per-request deadline with `SET LOCAL`, which overrides the role setting. R-87 (2026-09-23): the 8 developer-connection catalog reads (`schema_count`/`field_domains`/`field_types`/`all_field_types`/`field_constraints`/`field_types_and_constraints`/`all_field_constraints`/`schema_revision`) carry no per-request deadline, but each now issues its own per-transaction `SET LOCAL statement_timeout`/`lock_timeout` at the constructed `max_execution_ms` (the declared `execution_ms`) -- the role setting bites only on developer-connection statements that carry neither a deadline nor their own `SET LOCAL` (inference). Note: an audit query slower than the new bound is cancelled rather than running unbounded | fact + inference | a ref whose request paths set their own per-request deadline with `SET LOCAL statement_timeout`, or (R-87) whose own developer-connection catalog reads issue their own per-transaction `SET LOCAL` regardless of deadline. The note holds at every other ref: a path that carries neither a deadline nor a `SET LOCAL` of its own is bounded by the role setting |
| `0014_role_connection_limits_rollout.sql` | applied (platform), last in the numbered set. It raises `mitatedbsvc_api` to `CONNECTION LIMIT` 132, `mitatedbsvc_controlplane` to 36, `mitatedbsvc_auditreader` to 12 and every application's runtime and developer role to 68 -- the demand of TWO revisions of the same process serving at once, which is what a rollout puts side by side (§10.10's precondition arithmetic). **A role whose current `CONNECTION LIMIT` is ABOVE the value this file sets is lowered to it**, exactly as `0012`'s own row warns: this file SETs its four values rather than raising toward them. On a deployment carrying `0012`'s and `0013`'s own values it lowers nothing, but a limit raised by hand above 132 / 36 / 12 / 68 comes back down to it -- so read the current values with the catalog read and record them before applying, the same way `0012`'s row says to (§10.10 step 2). **Re-applying `0014` itself is idempotent, but the two files before it are not value-neutral after it**: `0012` alone afterwards lowers the api, controlplane and existing application roles back to 68 / 20 / 36 and drops `0013`'s `statement_timeout` from future application roles, and `0013` alone afterwards lowers future application roles to 36 while leaving every existing role as `0014` set it. Re-applying `0014` compensates for either. **The second case is caught by nothing this procedure runs until an application is provisioned after it** -- item (8) compares the roles that exist, and until the next provisioning call no role carries the lowered value (§10.10.1 step 7). `apply-platform-migration` enforces the order: it refuses `0012` or `0013` given without every one of its own later files in the same run, so a run that includes `0012` is always `0012` `0013` `0014`, a run that includes `0013` always carries `0014`, and `0014` can still be applied on its own | none; not reverted | **compatible**. Sets four `CONNECTION LIMIT`s to fixed values above `0012`'s and `0005`'s own (132 / 36 / 12 / 68), raising each of those and lowering only a limit already above its own new value, and drops and revokes nothing, and replaces `begin_provision_application` with the same signature and result columns, keeping `0013`'s `statement_timeout` lines (fact: the file's own header and statements). An older revision's pool ceiling is at or below the new value (inference) | fact + inference | a ref whose own per-role pool composition, at the concurrency that ref is deployed with, stays within 132 / 36 / 12 / 68 -- compute it from that ref's own `config.py`, the same way `0012`'s row does |
| `0016_credential_request_rate.sql` | applied (platform), by §10.10.1 step 7a, after the numbered set's `0014` and before the candidate is deployed. **A candidate that counts in it cannot start without it**: on a platform database without its rate function, the data service and its preflight refuse to start, naming the migration. No later accepted file redefines its targets, so `apply-platform-migration` accepts it alone | none; not reverted | **compatible**. Creates a new table `mitatedb_registry.credential_request_rate` (with a foreign key to the EXISTING `mitatedb_registry.credentials`, `ON DELETE CASCADE`) and a new function `mitatedb_registry.credential_request_rate_admit`, revokes both from `PUBLIC` and grants them to `mitatedbsvc_api` only -- it names no existing object in any `ALTER`/`DROP` and narrows no existing grant (fact: the file's own statements). A revision that lacks it reads and writes none of the new objects. That foreign key adds a referential-integrity trigger on the EXISTING `credentials` table, and an application's own deprovision (`0004`, `finish_deprovision_application`'s own `DELETE` from `credentials`) cascades to that application's own rows in `credential_request_rate` | fact | a ref whose `MitateDB-api/src/` does not name `credential_request_rate` (confirm with `git grep` at that ref) |
| `0006_declared_field_types_upgrade.sql` (per-application) | applied by `upgrade-applications` to applications that have not recorded it | none | **compatible (inference)**. Adds a table and fills type rows from the existing columns. A pre-`0006` revision does not read that table | inference | a ref that does not read the declared-field-types table |
| `0008_platform_upgrades_upgrade.sql` (per-application) | as above | none | **compatible**. Adds the ledger table. "Not yet applied" is decided by (numbers this revision ships) minus (numbers recorded), so extra recorded numbers are ignored (fact: `platform_upgrades.pending_upgrade_numbers`). A pre-`0008` revision does not read the ledger | fact | a ref whose own `pending_upgrade_numbers` computes (numbers it ships) minus (numbers recorded), and which does not read the ledger |
| `0009_field_constraints_upgrade.sql` (per-application) | as above | none | **compatible (with a note)**. Adds columns that have defaults. A pre-`0009` revision's INSERT into `_mdb_field_types` names its columns explicitly (fact: that revision's own `backend_postgres.py`). Note: constraints the new revision declared (`enum_json`/`nullable`) are not enforced by the old revision (inference) | fact + inference | a ref whose `backend_postgres.py` names the columns explicitly in its INSERT into `_mdb_field_types` |
| `0010_idempotency_records_upgrade.sql` (per-application) | as above | none | **compatible (with a note)**. Adds a table. Note: a pre-`0010` revision does not carry `_mdb_idempotency` among the names it excludes in `schema_count`, so it counts that application's tables one too high (fact: that revision's own `backend_postgres.py` `NOT IN` list of three names). Idempotency records written by the new revision are not used by the old one (inference) | fact + inference | a ref whose `schema_count` excludes exactly the three names its own `backend_postgres.py` `NOT IN` list carries |
| `0015_row_order_column_upgrade.sql` (per-application) | applied by `upgrade-applications` to applications that have not recorded it | none; no down script is provided -- reverting, if ever needed, is a manual `ALTER TABLE ... DROP COLUMN _mdb_row` on every collection table of the affected application | **not compatible**. A pre-`0015` revision's own `cell.py::ApplicationCell._select_fields` (select-all) and `add_field`'s own field-count check both call `self._backend.field_domains(collection)` directly, with no exclusion of `_mdb_row` (fact, static read: `cell.py`:3109-3110/1583 at `HEAD~3`, unchanged by the two revisions between it and this one). Once the column physically exists on a collection table, that revision's own select-all response includes `_mdb_row` as if it were a declared field, and its own `add_field` field-count check (`current = ...field_domains(...); len(current) >= max_fields`) counts it too, refusing `add_field` on that collection one field earlier than the deployed `max_fields` actually allows | fact (static read; not executed against a real pre-`0015` revision) | a ref whose `cell.py` calls `self._backend.field_domains` with no `_mdb_row` exclusion (every ref before this revision) |

**If any migration turns out to be irreversible or to require downtime**,
ask the requester for a separate decision covering backup/restore and the
scope of the outage, and do not go to production without that decision and
its review.

### 10.7 Lock type, stop-time limit, and applied `lock_timeout` table (item (6))

**This table is a draft. The stop-time limits and the `lock_timeout`
values are not settled until the independent review in §10.8 accepts
them.** Table version: **6** (2026-09-29: the `0016` row's own "what waits
on the locked object" column also names deprovision. Version 5,
2026-09-29: adds the `0016` row). Change
the table and the version goes up by one and §10.8's acceptance record
goes back to "not accepted".

- Lock types follow the PostgreSQL 16 documentation (the Explicit Locking
  table and each command's own Notes). For commands the documentation does
  not describe a lock for (`ALTER ROLE`, `ALTER DATABASE`, `GRANT`/
  `REVOKE`, `CREATE OR REPLACE FUNCTION`, `DROP DATABASE`, `DROP ROLE`)
  the row says "inference".
- Requests that conflict with a statement already waiting for a lock queue
  behind it (including an ACCESS SHARE request arriving while an ACCESS
  EXCLUSIVE request waits). The bound on "how long a following request can
  wait" is therefore `lock_timeout` PLUS how long that lock is held (to
  the end of the transaction).
- `statement_timeout`: the provision role has no role-level value, and
  neither `ops` nor anything in this section passes one (fact: `0007` sets
  it for `mitatedbsvc_api`/`mitatedbsvc_controlplane` only, and `0013` for
  the auditreader and the application roles -- never for
  `mitatedbsvc_provision`). A per-application `SET LOCAL ROLE` does not
  pick up a role's settings (PostgreSQL documentation: role settings apply
  at login).
- A running Data/Control process reads `platform_declarations` only at
  startup (fact: `main.build_app` and
  `control_composition.build_control_service` are the only callers of
  `read_platform_declarations`).

| Target | Transaction | Statements and lock types | What waits on the locked object | Applied `lock_timeout` (draft) | Bound on how long a following request waits (draft) | Maintenance window |
|---|---|---|---|---|---|---|
| `0005` | **no `BEGIN`/`COMMIT` -- each statement auto-commits**, so a failure part-way leaves the earlier statements applied and the file is re-run to finish | `CREATE TABLE IF NOT EXISTS`: no-op if present (inference: no heavy lock on an existing table). `REVOKE`/`GRANT ... ON` the new table and `GRANT USAGE ON SEQUENCE`: inference (ACL update). `DO` block with `CREATE ROLE` when absent: inference (role catalog). `GRANT CONNECT ON DATABASE`, `GRANT USAGE ON SCHEMA`: inference. `GRANT SELECT ON mitatedb_registry.control_audit`: an EXISTING table's ACL -- inference. `SELECT mitatedb_registry.assert_role_has_no_memberships(...)`: catalog read, ACCESS SHARE (fact: documentation) | `control_audit` writes from the control-plane process while its ACL is updated | `3s` | 3 seconds + hold time (ACL/catalog only). Running processes are unaffected | not needed (draft) |
| `0007` | the whole file is one `BEGIN`/`COMMIT` | `ALTER ROLE ... SET` x4: role catalog row update (inference: no user-table lock). `CREATE TABLE IF NOT EXISTS`: no-op if present (inference). `REVOKE`/`GRANT ... ON` the table: inference (ACL update, no heavy lock on the table). `INSERT ... ON CONFLICT` x2: ROW EXCLUSIVE and row locks (fact: documentation). **Neither of those two writes is value-neutral on a re-application**: the four `ALTER ROLE`s set `5000ms` unconditionally, and the `audit_writer_roles` INSERT is `DO UPDATE`, so it replaces that row with the pair passed on the command line (the `audit_coalescing_window_ms` INSERT is `DO NOTHING` and does not) -- §10.10 steps 2 and 4 record the current values first and restore them straight after the apply, before any restart | a startup declaration read (ACCESS SHARE, which does not conflict with ROW EXCLUSIVE), and a `declare-*` write to the same row | `3s` | 3 seconds + hold time (a few rows in a small table). Running processes are unaffected | not needed (draft) |
| `0011` | one `BEGIN`/`COMMIT` | `ALTER TABLE ... DROP CONSTRAINT`: ACCESS EXCLUSIVE (fact: the documented default). `ALTER TABLE ... ADD CONSTRAINT ... CHECK`: ACCESS EXCLUSIVE plus a scan validating existing rows (fact: documentation) | any process starting up and reading `platform_declarations`, and `show-declarations` / `verify-declarations` / `inventory` / `declare-*` | `2s` | 2 seconds + hold time (a scan of a few rows). A process starting during that window waits on its declaration read. Running processes are unaffected | not needed (draft); do not run it at the same time as a restart |
| `0012` sections 1-2 | one `BEGIN`/`COMMIT` | `ALTER ROLE ... CONNECTION LIMIT` x2, plus x2 per application inside the `DO` block: role catalog row updates (inference). The `DO` block's `SELECT ... FROM mitatedb_registry.applications`: ACCESS SHARE (fact: documentation) | only an operation taking ACCESS EXCLUSIVE on `applications`, which no procedure here does | `3s` | 3 seconds + hold time. Existing connections are not dropped; the new limit applies to new connections | not needed (draft) |
| `0012` section 3 | **outside the transaction** (two statements, each auto-committing) | `CREATE OR REPLACE FUNCTION mitatedb_registry.begin_provision_application` and `REVOKE ... ON FUNCTION`: inference (function catalog row update; a call already running finishes on the pre-replacement definition) | provisioning running at the same time | the same (`3s`) | the same | not needed (draft); do not run it at the same time as provisioning |
| `0013` | **the whole file is one `BEGIN`/`COMMIT`** -- a permission failure anywhere rolls the whole run back and leaves nothing changed | `ALTER ROLE mitatedbsvc_auditreader SET statement_timeout`: role catalog row update (inference). `DO` block: `SELECT runtime_role, developer_role FROM mitatedb_registry.applications` (ACCESS SHARE, fact: documentation) plus `EXISTS (SELECT 1 FROM pg_roles ...)` and `ALTER ROLE ... SET` per role (inference). `CREATE OR REPLACE FUNCTION mitatedb_registry.begin_provision_application` and `REVOKE ... ON FUNCTION`: inference | only an operation taking ACCESS EXCLUSIVE on `applications`; provisioning running at the same time (the function is replaced inside this transaction) | `3s` | 3 seconds + hold time (role catalog plus one function). Existing sessions keep their own settings; the new bound applies at the next login | not needed (draft); do not run it at the same time as provisioning |
| `0014` | **the whole file is one `BEGIN`/`COMMIT`** -- a permission failure anywhere rolls the whole run back and leaves nothing changed | `ALTER ROLE ... CONNECTION LIMIT` x3 on the platform-plane roles (`mitatedbsvc_api`, `mitatedbsvc_controlplane`, `mitatedbsvc_auditreader`): role catalog row updates (inference). `DO` block: `SELECT runtime_role, developer_role FROM mitatedb_registry.applications` (ACCESS SHARE, fact: documentation) plus `EXISTS (SELECT 1 FROM pg_roles ...)` and `ALTER ROLE ... CONNECTION LIMIT` per role (inference). `CREATE OR REPLACE FUNCTION mitatedb_registry.begin_provision_application` and `REVOKE ... ON FUNCTION`: inference | only an operation taking ACCESS EXCLUSIVE on `applications`; provisioning running at the same time (the function is replaced inside this transaction) | `3s` | 3 seconds + hold time (role catalog plus one function). Existing connections are not dropped; the new limit applies to new connections | not needed (draft); do not run it at the same time as provisioning |
| `0016` | **the whole file is one `BEGIN`/`COMMIT`** -- a failure anywhere rolls the whole run back and leaves nothing changed | `CREATE TABLE IF NOT EXISTS mitatedb_registry.credential_request_rate` with `REFERENCES mitatedb_registry.credentials`: on the first application, SHARE ROW EXCLUSIVE on `credentials` (inference: the documentation states that lock for adding a foreign key with `ALTER TABLE`, and a `REFERENCES` clause in `CREATE TABLE` creates the same constraint), held to the end of the transaction; a no-op if the table is present (inference). `REVOKE`/`GRANT ... ON` the new table: inference (ACL update). `CREATE OR REPLACE FUNCTION mitatedb_registry.credential_request_rate_admit` and `REVOKE`/`GRANT ... ON FUNCTION`: inference (function catalog) | on the first application, credential issue, revoke, enable and disable, and deprovision (`0004`'s own `finish_deprovision_application` `DELETE` from `credentials`) -- their `INSERT`/`UPDATE`/`DELETE` on `credentials` all take ROW EXCLUSIVE, which conflicts with SHARE ROW EXCLUSIVE (fact: documentation); authentication reads of `credentials` (ACCESS SHARE) do not conflict | `3s` | 3 seconds + hold time (one new empty table, one function). Running processes' reads are unaffected | not needed (draft) |
| per-application upgrade (`0006`, `0008`, `0009`, `0010`, via `upgrade-applications`) | per application: `GRANT <developer_role> TO CURRENT_USER` (auto-commit) -> one `BEGIN`/`COMMIT` -> `REVOKE` (auto-commit). A failure leaves the temporary membership behind (§3.4b's cleanup) | `CREATE TABLE IF NOT EXISTS` (`0006`, `0008`, `0010`): inference (no heavy lock on an existing table). `INSERT`: ROW EXCLUSIVE (fact: documentation). `0006`'s read of `information_schema.columns`: ACCESS SHARE (fact: documentation). **`0009`'s `ALTER TABLE public._mdb_field_types ADD COLUMN IF NOT EXISTS` x2: ACCESS EXCLUSIVE** (fact: the documented default); the defaults are constants so no table rewrite happens (fact: documentation); the lock is still taken when the column already exists (inference). `GRANT`/`REVOKE` on roles, tables and the schema: inference | that application's own requests that read `_mdb_field_types` (during `0009`), and schema operations on that application | `2s` (`--lock-timeout 2s`) | 2 seconds + hold time per application (catalog-only changes). Other applications are unaffected | not needed (draft) |
| deprovision (`0004`, via `deprovision`) | outside a transaction (`DROP DATABASE` cannot run inside one -- fact: documentation). **A failure after stage (3) (and after either `GRANT` that already succeeded -- a cancel on the first `GRANT` itself leaves nothing changed) leaves the temporary self-grant membership behind** (design §5.1 (i)), the same property the per-application upgrade row above records for its own temporary grant | `begin_deprovision_application` / `finish_deprovision_application`: registry row updates (inference: ROW EXCLUSIVE and row locks). `GRANT <role> TO CURRENT_USER WITH INHERIT TRUE, SET FALSE` (stage (3), when either role still exists): inference (`pg_auth_members` row). `ALTER DATABASE ... WITH ALLOW_CONNECTIONS false` (stage (4)): inference (`pg_database` row update). `pg_terminate_backend`: no lock. `DROP DATABASE`: fails while another connection exists (fact: documentation), lock type inference. `DROP ROLE`: inference | operations updating the same application's registry rows, plus, after stage (4), every new connection attempt to that application's database (refused, not queued); existing sessions are ended by stage (5)'s terminate, not by the `ALTER` | `5s` (`--lock-timeout 5s`) -- applied to the whole psql session, so it also bounds stage (3)'s `GRANT` and stage (4)'s `ALTER DATABASE`; a timeout at either leaves only the temporary self-grant standing while `ALLOW_CONNECTIONS` is still true (see §9 item 3's failure-state table for that state) | that application stops permanently (irreversible, §10.6). An operation touching the SAME application's registry rows waits at most 5 seconds + hold time; other applications are not affected. If the run stops at stage (4) or later, that application's database is left refusing new connections (`datallowconn=false`) until an operator re-runs `0004` or reverts it -- an unbounded stop, not a lock wait, plus fleet-command degradation (design §4.1 / F-3) | never run by an upgrade |

**How the table's values are passed**:

- Platform migrations (`0005`, `0007`, `0011`, `0012`, `0013`, `0014`,
  `0016`):
  `apply-platform-migration <filename> [<filename> ...] --lock-timeout
  <the table's value>`. The argument is required and has no default, and
  the tool does not carry its own copy of this table (design D-4, R-5) --
  a run composes files that share the same §10.7 value, and mixing files
  whose §10.7 values differ is the operator's own responsibility, not
  something the tool checks. Do not assemble `PGOPTIONS` by hand -- the
  subcommand builds the psql environment from the DSN and adds the lock
  timeout to `PGOPTIONS` itself.
- Per-application upgrade: `upgrade-applications --lock-timeout <the
  table's value>`, required and with no default (`--dry-run` needs it
  too).
- Deprovision: `deprovision --lock-timeout <the table's value>`,
  required and with no default.
- The accepted value shape is a positive integer with an optional `ms` /
  `s` / `min` suffix. `0` is refused, because PostgreSQL reads 0 as "no
  timeout".
- On overrun psql fails with `canceling statement due to lock timeout`
  and that transaction is rolled back. Follow §10.10's stop conditions.

### 10.8 Acceptance record for the tables and the procedure

Item (5), and item (6)'s lock/downtime half, are judged by the
independent review (in design-review mode) of §10.6/§10.7 recorded here.
**A record whose "version reviewed" does not equal the table's current
version counts as no record at all.**

| Subject | Current version | Conclusion | Version reviewed | Where the review is recorded | Date accepted | Recorded by |
|---|---|---|---|---|---|---|
| §10.6 compatibility | 6 | not accepted | 4 | `docs/work-orders/WORK_ORDER_R57_PLATFORM_MIGRATION_RUN_V1.md` §5 | -- | -- |
| §10.7 lock / stop time / `lock_timeout` | 6 | not accepted | 4 | `docs/work-orders/WORK_ORDER_R54_DEPROVISION_LIVE_CONNECTIONS_V1.md` §5 | -- | -- |
| §10.10 upgrade procedure (stages 2-4) | 9 | not accepted | 7 | `docs/work-orders/WORK_ORDER_R57_PLATFORM_MIGRATION_RUN_V1.md` §5 | -- | -- |

### 10.9 Gate-0 overall judgment and report

This judgment is made the same way in both reads: the first read (stage 1)
and the second read (stage 3, §10.10.2) use exactly this section.

**Overall judgment** (the DB layer and the platform layer are read in the
same run and reported together):

| Item | Confirmed when |
|---|---|
| (1) | §10.4.1 read exactly one connection name AND `inventory`'s `connection.judgment` is confirmed |
| (2) | `inventory`'s `declarations.judgment` |
| (3) | `inventory`'s `migrations.judgment` (`ledger-unreadable` is blocked, §10.5) |
| (4) | `inventory`'s `credentials.judgment` |
| (5) | §10.8 records §10.6 accepted at its current version, §10.4.4's rollback target is attested, and every §10.6 row the rollback target does not contain is "compatible" (a note is allowed) AND has its last-column condition confirmed at that target's own attested source ref. A row whose condition cannot be confirmed there leaves (5) `unknown` |
| (6) | `inventory`'s `ddl_lock.judgment` is confirmed, §10.8 records §10.7 accepted at its current version, and no row being applied needs a maintenance window (or, if one does, a separate decision covers it) |
| (7) | §10.4.2 |
| (8) | `inventory`'s `connection_headroom.judgment` (arguments from §10.4.3) |
| (9) | §10.4.4 |
| (10) | §10.4.5 |

- **Gate-0 is ready only when all 10 items are confirmed AND §10.8's
  acceptance records name the tables' current versions.** `inventory`'s
  exit status `0` on its own never makes Gate-0 ready.
- A `remediation-required` note is a work item that lets the procedure
  proceed; it is not a blocker (stage 2 clears it).
- **With even one blocked or unknown item, Gate-0 is not ready.** What
  "not ready" forbids is stage 4: no candidate is deployed and no traffic
  is moved (§10.10.3).
- **In the FIRST read, "not ready" is the normal starting state of a
  deployment that has not had the platform remediation yet** -- a
  deployment where `0013` has not run reports item (6) `unknown`, one
  where `--thread-limit`/`--data-process-count-old-basis` cannot yet be
  established (§10.4.3) reports item (8) `unknown`, and so on. Report it
  (below), then look the finding up in
  §10.10.1's table of findings that stage 2 resolves. **A finding that is
  not in that table is not resolved by stage 2: stop there.**
- **In the SECOND read (stage 3), any item that is still not confirmed
  stops the procedure.** An `unknown` is never downgraded to a warning and
  carried into stage 4, and stage 2 is not repeated in the hope of a
  different answer without a new decision (§10.10.2 names the one
  exception: a finding whose row in §10.10.1's table names a step).

**Report** (what goes into the repository and into the report to the
requesting side):

- Each item's judgment. **`unknown` and `blocked` both map to
  `blocked—platform remediation required`, with the breakdown (how many
  unknown, how many blocked) stated alongside.** Only `confirmed` is a
  pass. **Write that phrase exactly as printed here, with an em dash
  (U+2014) and no spaces around it**: the receiving side matches the
  string literally, so an ASCII `--` in its place is a different report.
- The `remediation-required` notes.
- Counts that carry no identifier (for example: how many applications are
  registered only; how many credentials are in each state).
- What never goes in: DSNs, credentials, tokens, HTTP bodies, real data,
  and the service account, Cloud SQL connection name, real digest,
  revision name, database name and secret name (those stay in §10.1's
  evidence).

Shape:

```text
Gate-0 (<isolated|production>) (<first read|second read>) <date>
(1) confirmed
(2) confirmed [remediation-required]
(3) blocked—platform remediation required (breakdown: blocked)
(4) confirmed (credentials <n>; by state <enabled n / revoked n / must_rotate n>)
(5) blocked—platform remediation required (breakdown: unknown)
...
(10) confirmed (starting prefix N = <n>)
overall: <ready | blocked—platform remediation required (unknown <n>, blocked <n>)>
acceptance records: §10.6 version <n> <accepted|not accepted>, §10.7 version <n> <accepted|not accepted>, §10.10 version <n> <accepted|not accepted>
```

### 10.10 Platform upgrade procedure (stages 2-4)

Procedure version: **9** (2026-09-29: step 6 also checks, on paper and
against the `process_ceilings` values it is about to declare, an
OLD-basis revision's own older startup check for `max_connections`
headroom, states that check's own lower bound, and gives a two-stage path
for a value that check does not clear -- raise the worker count first
without raising the ceiling, raise the ceiling only once every counted
revision is on the NEW basis -- with the same check added to the
preconditions' own paper arithmetic and to Rollback; §10.4.3's own
declared-default exception for `--concurrency` now applies only when that
commit's own Dockerfile build input sets none of the four pool-sizing env
names and that commit's own `config.py` carries a `max_concurrency`
default, and carries a disclosure sentence; §10.4.3's own `unknown` cases
for `--data-process-count-old-basis` gain the case where an OLD-basis
revision's own attested source ref does not carry the pool-sizing shape
the `2 x concurrency` floor assumes, with a step to confirm it at that
ref and a matching row in §10.10.1's own findings table; the env-value
allow-table's `MITATEDB_WORKERS`/`MITATEDB_CONTROL_WORKERS` rows state the
`WEB_CONCURRENCY` fallback an OLD-basis revision's own worker count reads,
and the basis distinction is stated to apply to Data only; step 13 and its
own read-back also carry Control's own `MITATEDB_CONTROL_WORKERS`/
`MITATEDB_THREAD_LIMIT`; item (9) gains a step that reads each counted
digest's own attested source ref to record its basis in §10.4.3's own
addend table; the two omission phrases in §10.4.3 read "for the whole
read" throughout; a few figures in the worked example and in §10.10.1's
own findings table are corrected against `ops.py`'s own arithmetic; and
step 10's own combined env change is one `--update-env-vars=` flag).
Version 8, 2026-09-29: adds step 7a for `0016`; counts a
revision's processes as `maxScale` times its worker count in step 6 and
step 13; splits item (8)'s demand arithmetic by revision basis -- an
OLD-basis process's own demand from its declared `concurrency`, a
NEW-basis process's from `role_pool_size(--thread-limit)`, the same floor
the startup connection-limit check uses -- with the worked example to
match; §10.4.3's own argument table gains `--thread-limit` and
`--data-process-count-old-basis`, the two rejections `inventory` raises
for the latter, and the rule that `--concurrency` and `--thread-limit`
each take the largest value over every revision counted toward item (8),
including one that cannot take traffic; an OLD-basis revision counted
toward item (8) may declare its `concurrency` from the commit-and-file-line
default that built its image, an exception that does not extend to
`--thread-limit`; the env-value allow-table gains the worker, thread-limit
and presence-only `MITATEDB_PLATFORM_POOL_SIZE` rows, and an item is
`unknown` for an unset name only where that row's own "When unset" cell
says so; §10.10.1's item (8) findings name `minScale` as the way out for a
counted revision that takes no traffic; and step 10's env-only change
declares `MITATEDB_THREAD_LIMIT` only on a NEW-basis template, step 13
always). Version 7, 2026-09-20, R-57 WP-3: follows
`apply-platform-migration` accepting a run and refusing a solo file with
a later file that redefines its own targets). Change the procedure and
the version goes up by one and §10.8's acceptance record goes back to
"not accepted".

**Preconditions**:

- All three rows of §10.8 are accepted, each at the version its subject
  now carries.
- **Item (8)'s demand arithmetic has been checked on paper, before a
  single piece of state is changed.** Item (8) is the one item whose answer
  depends on inputs that stage 2 and stage 4 themselves decide (the
  concurrency this deployment declares, and the process counts a cutover
  puts side by side), so it is computed here rather than discovered in the
  second read, with production already changed. Take the inputs the second
  read will pass (§10.4.3: the concurrency value, the thread-limit value,
  the worst-case OLD-basis and NEW-basis Data process counts and Data's own
  candidate ceiling, Control's own worst-case process count total and
  candidate ceiling, the reserved-connection count) and the limit each role
  will carry AT THE SECOND READ: for a role `0012` names, that file's own value (it sets the
  limits it names to its own value, raising one below it and lowering one
  above it -- §10.6's `0012` row), and for every other role (the
  auditreader's own limit from `0005`, and any other role `0012` does not
  name) the value the step-2 catalog read returns (2026-09-18: step 7 now
  ends with `0014_role_connection_limits_rollout.sql`, so the value to
  substitute for the four role classes IT names is `0014`'s own -- 132 for
  the api role, 36 for the controlplane role, 12 for the auditreader and
  68 for each application's runtime and developer role. The auditreader is
  no longer a role only the catalog read answers for; a role none of the
  files names still is). Item (8) never compares the provision role at
  all: it excludes the owner of both audit tables.
  `max_connections` comes from that same read. Both are the read-only
  shapes step 2 and step 11 use, which change nothing. Then compute
  exactly what the tool computes:

  ```text
  api role demand                    = O x 2 x concurrency
                                       + N x 2 x role_pool_size(thread_limit)
  controlplane role demand           = control total x 16
  auditreader role demand            = control total x 4
  each application's runtime role
  and developer role demand          = O x concurrency + N x role_pool_size(thread_limit)
  application demand (condition 2)   = 0 when no application is registered,
                                        else the LARGER of that per-role
                                        demand and 2 x K x (O + N)
                                        (K = the number of registered
                                        applications with a role)
  total demand                       = api + controlplane + auditreader
                                       + the application demand (condition 2)
                                       + 2
  ```

  (`O` = the worst-case OLD-basis Data process count, `N` = the worst-case
  NEW-basis Data process count, `role_pool_size(thread_limit) = thread_limit
  + 2` -- design docs/design/MITATEDB_INVENTORY_DEMAND_BASIS_V0_1.md D-2.)
  The factor `2` in the api demand is the number of
  connection stores that role carries per process, on either basis; the
  `16` and the `4` are fixed floors that do not depend on either basis
  (§6.5); and the trailing `+ 2` is the read's own connections. The
  auditreader demand is `0` unless a role actually carries `0005`'s own
  auditreader grant shape. With `--control-not-deployed` the controlplane
  and auditreader demands are `0` and those roles are left out of both
  conditions below. The two conditions item (8) then applies are:

  1. every one of those roles' own `CONNECTION LIMIT` is greater than or
     equal to its own demand above (and none of them is `-1`, which is
     `unknown` before any demand is compared -- a `-1` on a role `0012`
     names is the `unknown` row §10.10.1 resolves with step 7, so
     substitute `0012`'s own value here; a `-1` on any other role stops
     the procedure -- 2026-09-18: step 7 also applies `0014`, whose own
     value is the one to substitute for the four role classes it names,
     `mitatedbsvc_auditreader` among them);
  2. total demand plus the reserved-connection count is less than or equal
     to `max_connections`.

  **Worked example** -- the limits step 7 leaves once `0014` has been
  applied, a declared OLD-basis `concurrency` of 32, a `thread_limit` of 4
  (`role_pool_size` 6), at least one application registered, one OLD-basis
  process (`O = 1`) and `W` NEW-basis processes (`N = W`) -- the shape a
  rollout produces once the revision now serving and the candidate stand
  side by side, with both worst-case control totals equal to 1 (design
  docs/design/MITATEDB_INVENTORY_DEMAND_BASIS_V0_1.md §5):

  ```text
  role                    limit   demand at W = 5              condition 1
  api                       132   2x32 + 2x6x5 = 124           124 <= 132 ok
  controlplane               36   16                            16 <=  36 ok
  auditreader                12    4                             4 <=  12 ok
  each application's
  runtime / developer        68   32 + 6x5 = 62                 62 <=  68 ok

  total demand   = 98 + 18x5 + 20 = 208   (98 + 18W + 20C is the general
                                            form at C = 1 control process;
                                            condition 2 compares 208 + the
                                            reserve against max_connections)
  ```

  **This `208` holds while the number of registered applications with a
  role (K) is 1 through 5.** The application term inside it is the LARGER
  of the per-role floor (`62` at `W = 5`) and `2 x K x (O + N)` (`12K` at
  `O + N = 6`); `12K` stays at or below `62` only through `K = 5`
  (`12 x 6 = 72` exceeds it), so at `K = 6` or more the application term is
  `12K` instead of `62` and the total is correspondingly larger.

  **At `W = 6` the api role's own condition 1 fails**: the api demand is
  `2x32 + 2x6x6 = 136`, above 132, so the answer is
  `blocked—platform remediation required`. `W <= 5` is therefore the
  largest NEW-basis worker count this one-OLD-basis-process rollout
  supports without a further platform migration; once every counted
  revision is on the NEW basis (`O = 0`), the same limits instead support
  `V + W <= 11` total NEW-basis processes across the two revisions (§6.5's
  own table), since the OLD-basis term drops out entirely. The way back
  from a `W` that fails is the total's own inputs (§10.4.3): the tag on a
  revision that is kept only for reachability, and a `minScale` of 1 or
  more on a revision that is not serving. Taking a tag off is the way out
  §10.10.1's own item (8) `unknown` row already names, and it "is itself
  a traffic-projection change and therefore carries the same three
  conditions as step 10's own move (the isolated proof, the independent
  audit and the requester's approval) -- otherwise it is a separate
  decision". Changing a `minScale` is a deployment change of the same
  kind (§10.10.1's own item (8) `unknown` rows name it too), so it is
  decided the same way.

  **`0014` does not move condition 2.** It raises the per-role limits
  condition 1 compares, while condition 2 compares a sum built out of the
  demands, the reserve and `max_connections` -- none of which a
  `CONNECTION LIMIT` change touches -- so that sum is the same before and
  after step 7. **The application term in that sum is the LARGER of the
  per-role demand above and `2 x K x (O + N)`** (K = the number of
  registered applications with a role): each of the
  K applications holds a persistent connection on each of its own two
  roles per Data process at once, so a once-per-process count alone would
  undercount once `K` reaches 4 at the default thread limit. Read the sum
  for what it is: the number this procedure compares, never smaller than
  the real worst-case persistent-connection count. When it is condition 2
  that fails, the lever is the Cloud SQL instance's own `max_connections`
  flag (§3.2b names it) rather than any migration -- what value it should
  carry is not settled here.

  **If even one of them does not hold, stage 2 does not start**: report
  `blocked—platform remediation required` with which role or which sum
  fails, and stop. **This section has no fix for it** -- raising a role's
  own `CONNECTION LIMIT` value takes a new platform migration (§10.10.1's
  table of findings), and counting the totals differently is a separate
  decision (2026-09-18: the numbered set now ends with `0014`, so what
  this means today is a FURTHER platform migration above `0014`'s own
  values). Record the arithmetic and its inputs in the evidence (§10.1)
  and compute it twice, the way §10.4.3 requires of the totals themselves.
- **The declared `process_ceilings.data`/`.control` step 6 is about to
  write is also checked on paper against every OLD-basis revision counted
  toward item (8), and against the rollback target, before step 6 runs**:
  each such revision's own attested source ref carries a startup check of
  its own, older than and separate from the worker-count check step 6
  describes below, whose lower bound is `process_ceilings.data x (2 x
  concurrency, or 4 x concurrency when the platform has at least one
  registered application) + process_ceilings.control x 16`, compared
  against `max_connections` minus `superuser_reserved_connections` minus
  `reserved_connections`. Step 6 states this check and the way through a
  value that fails it in full.
- **Against production, three things are true before anything in §10.10.1
  or §10.10.3 runs: this whole procedure has been run against the isolated
  pair end to end, that evidence has passed an independent audit, and the
  requester has approved.** Gate-0 ready is not one of the three, and
  §10.8's acceptance record is not a substitute for any of them
  (`security/CONTROL_MAPPING.md` records the same limit on
  `apply-platform-migration` itself).
- Stage 1 has been read and reported against the pair this run will
  change, and every finding it produced is one §10.10.1's table covers.
- No application is in the `ledger-unreadable` state (§10.5).
- Production gets the SAME digest the isolated run used, and the
  production read shows no difference from the isolated read.

**Stop conditions** (at every step): a non-zero exit status; a
`lock_timeout` overrun; a bad Ready condition or health check; a
`verify-declarations` failure; a finding the table in §10.10.1 does not
cover; an item the second read leaves not confirmed; a discovery that a
migration is irreversible, unrecoverable, or needs downtime.
**If you stop before traffic has moved, leave the candidate at 0%.**
Remove the cause and restart from the step that stopped (each migration,
declaration and per-application upgrade is re-appliable on item (10)'s
evidence).

**Applying a platform migration**: use `apply-platform-migration`, which
takes the DSN from the environment only, accepts one or more FILENAMEs as
a single run, passes `ON_ERROR_STOP=1`, puts the required `--lock-timeout`
value into the psql environment itself, and redacts connection values out
of psql's output before any failure text is printed. Each FILENAME
argument is a bare file name: a path separator is refused, the name must
be one of the accepted platform migrations, and the resolved path must
stay inside the migrations directory. A run's FILENAMEs must be given in
migration order with no repeat, and a file with a later file that
redefines one of its own targets is refused unless every one of those
later files is given too, in the same run -- both checks run, and refuse
with a fixed message, before any psql subprocess starts.

```sh
(
  set +x
  MITATEDB_PROVISION_DSN="$(gcloud secrets versions access latest \
    --secret=<provision-dsn-secret> --project=<project> --quiet 2>/dev/null)" || exit 1
  export MITATEDB_PROVISION_DSN
  PYTHONPATH=MitateDB-api/src python3 -m mitatedb_api.ops apply-platform-migration \
    <filename> [<filename> ...] --lock-timeout <the §10.7 value, the same for every file in the run> [--api-role ... --controlplane-role ...]
)
```

**Apply the platform migrations as one numbered set, never one file out of
order.** The set is `0005_application_audit.sql`,
`0007_platform_declarations.sql`, `0011_process_ceilings.sql`,
`0012_role_connection_limits.sql`, `0013_role_statement_timeouts.sql`,
`0014_role_connection_limits_rollout.sql`, in
that order, every time, followed by `0016_credential_request_rate.sql`
(step 7a). `apply-platform-migration` enforces the order and
the `0012`/`0013`/`0014` closure within one run; it does not force
`0005`, `0007` and `0011` into that same run, so this operator rule still
covers the rest of the set. Two reasons for the rule:

- `0012` and `0013` both `CREATE OR REPLACE` the same
  `begin_provision_application` function. Applying `0012` alone after
  `0013` drops `0013`'s `statement_timeout` lines from the function, so
  every FUTURE application's roles are provisioned without the bound
  (roles that already exist keep the setting). The only compensation for
  such an out-of-order application is the next `inventory` run reporting
  the new application's item (6) as `unknown` again, until `0013` is
  applied once more. (2026-09-18: `0014` replaces that same function
  again, so all three files do. Applying `0012` or `0013` alone after
  `0014` also lowers a `CONNECTION LIMIT`; §10.6's `0014` row and
  §10.10.1 step 7 carry what each case lowers, what catches it and what
  does not.)
- `0013` names the `mitatedbsvc_auditreader` role that `0005` creates.
  Applying `0013` on a database where `0005` has not run fails with an
  undefined-role error. `0014` alters that role too, so the same failure
  applies to it.

**Prerequisite for the `ALTER ROLE` statements in `0007`, `0012`, `0013`
and `0014`, and what to do when it is not met.** Four files in the set
issue `ALTER ROLE`, and the prerequisite is the same rule for all of them:
PostgreSQL 16 lets a role run `ALTER ROLE` against another role only if it
holds CREATEROLE together with ADMIN OPTION on that target role, and
CREATEROLE carries that option automatically only for a role it created
itself. **So the role that applies the set must hold ADMIN OPTION on every
role the set alters:**

| Statements | Roles altered | Which step creates those roles |
|---|---|---|
| `0007`'s four `ALTER ROLE ... SET`, and `0012`'s and `0014`'s two `ALTER ROLE ... CONNECTION LIMIT` each | the api role and the controlplane role (`mitatedbsvc_api`, `mitatedbsvc_controlplane`) | `0002` (§3.2) |
| `0013`'s `ALTER ROLE ... SET statement_timeout` and `0014`'s own `ALTER ROLE ... CONNECTION LIMIT` | `mitatedbsvc_auditreader` | `0005` (§3.2b) |
| `0012`'s, `0013`'s and `0014`'s own `DO` blocks | every application's runtime and developer role | `begin_provision_application` (§3.4) |

**The prerequisite holds when `0002`, `0005` and provisioning were all run
as the role that now applies the set** (normally `mitatedbsvc_provision`,
per §3.1/§3.2/§3.2b/§3.4). It does not hold on a cluster where one of them
was run as the Cloud SQL instance's own administrative role instead.

When it does not hold, the file neither works around it nor skips the
role: the statement fails with `permission denied to alter role`, naming
the role in its DETAIL line, and `apply-platform-migration` exits non-zero
with the psql output redacted. `0007`, `0013` and `0014` are each a single
transaction, so nothing at all changes; in `0012` a failure in sections
1-2 rolls those sections back and section 3 never runs.

To fix it, grant the missing option explicitly for **each role the failure
named** -- run this as a role that already holds ADMIN OPTION on that
role, or as the cluster's administrative role, and then run the same call
again, in full, from its first file (every file in a run is idempotent,
and the same §10.7 `--lock-timeout` value applies to the whole call):

```sql
GRANT <the role> TO <provision role> WITH ADMIN TRUE, INHERIT FALSE, SET FALSE;
```

`INHERIT FALSE` and `SET FALSE` keep the grant to the ADMIN option alone:
the applying role gains neither the target role's privileges by
inheritance nor the ability to `SET ROLE` to it. This leaves the same
state a role gets automatically when it created the target role itself.

Measured on a throwaway PostgreSQL 16 cluster whose auditreader was created
by the administrative role rather than the applying role. **The
measurement is about `mitatedbsvc_auditreader` and `0013`**; for the api,
controlplane and application roles the same behaviour is inferred from the
same PostgreSQL 16 rule and has not been measured:

- before the grant, `apply-platform-migration 0013_role_statement_timeouts.sql`
  exits 2 on `permission denied to alter role`, and neither an application
  role's setting nor the `begin_provision_application` body changes;
- after the grant, the same command exits 0 and the auditreader and the
  application roles carry the setting;
- the grant trips no existing check: `assert_role_has_no_memberships`
  (called by `0005` and by `begin_provision_application`) tests whether the
  role it is given is itself a member of another role, not whether another
  role is a member of it, so re-applying `0005`/`0012`/`0013` and
  provisioning a new application all succeed; `ops inventory` discovers its
  target roles from table grants and never reads role membership, so the
  grant alone changes no item's judgment (item (6) turns `confirmed` only
  once `0013` has actually applied);
- the applying role's `SET ROLE mitatedbsvc_auditreader` is refused;
- the resulting `pg_auth_members` row (admin option set, inherit and set
  options unset) is identical to the one a cluster has when the applying
  role created the auditreader itself;
- `REVOKE mitatedbsvc_auditreader FROM <provision role>` removes the row
  again, after which `0013` fails as before.

(2026-09-18: `0014` was measured the same way and on the same kind of
throwaway PostgreSQL 16 cluster, with a registry row naming an
application role the applying role holds no ADMIN OPTION on -- one
created by the cluster's administrative role rather than by
`begin_provision_application`, so CREATEROLE's own implicit option never
attached. **That measurement is about an application role and `0014`**;
the api, controlplane and auditreader cases of the same file are
inferred from the same PostgreSQL 16 rule and have not been measured,
and neither has any of it been measured against production:

- `apply-platform-migration 0014_role_connection_limits_rollout.sql`
  exits non-zero, PostgreSQL raising `InsufficientPrivilege`
  (SQLSTATE `42501`) on the `ALTER ROLE` inside the per-application
  loop;
- the whole run rolls back with it: the platform-plane `ALTER ROLE`s in
  the file's own section 1, which run BEFORE that loop, are undone as
  well, so the api role still carries the limit it had before the run
  (68 on a cluster where only `0012` had run) and nothing is left
  half-applied;
- the way out is the same `GRANT ... WITH ADMIN TRUE, INHERIT FALSE,
  SET FALSE` above, for each role the failure names, and then running
  the same call again, in full, from its first file (every file in a
  run is idempotent).

`MitateDB-api/tests/test_ops_apply_platform_migration.py::test_apply_
platform_migration_0014_is_transactional_and_rolls_back_on_permission_
failure` holds the rollback -- a non-zero exit and the api role's limit
unchanged at 68. The SQLSTATE above is from the same measurement, not
from anything that test asserts.)

**Correction note (2026-09-20, design `docs/design/
MITATEDB_PLATFORM_MIGRATION_RUN_V0_1.md` G-1; this record is not
rewritten, only annotated -- `docs/work-orders/OPERATING_CONDITIONS.md`
§1.8 item 57)**: since R-57, `apply-platform-migration` refuses a lone
`0012` or a lone `0013`, because the later file(s) that redefine their
targets (`_PLATFORM_MIGRATION_SUPERSEDED_BY`) are not given in the same
call; a lone `0014` is still accepted. The single-file `0013` invocation
measured above is a record of the tool's pre-R-57 shape, when it
accepted only one FILENAME per call.

#### 10.10.1 Stage 2 -- platform remediation

**What gates this stage is not Gate-0.** The first read of a deployment
that has not been remediated yet reports items as `unknown`, and that is
the state this stage exists to clear. What gates it is the three things
§10.10's preconditions name: the isolated proof, the independent audit and
the requester's approval. **This stage changes production state** (DDL,
declarations, role settings, per-application upgrades, one env-only
revision, on a service whose traffic is pinned the traffic move onto that
revision in step 10, and, where a tag-only revision keeps a Data revision
out of §10.4.3's agreement, the removal of that tag), so nothing here runs
against production until all three hold.

Run the steps in order and stop at the first stop condition. **No
candidate is deployed anywhere in this stage** -- that is stage 4. The only
traffic PERCENTAGES this stage moves are step 10's own move onto the
env-only revision, which runs the same digest the revision it replaces
runs. Taking a tag off a revision (§10.10.1's table, item (8)) moves no
percentage, but it is the same traffic projection and carries the same
three conditions.

**Findings from the first read that this stage resolves.** Look each
finding up here before starting:

| Item | How the first read reports it | The step that resolves it |
|---|---|---|
| (2) `declarations` | confirmed + `remediation-required`: the `platform_declarations` table itself is absent, so no declaration can be read at all (the state of a deployment where `0007` has never run) | step 4 (`0007` creates the table), then step 5, step 6 and step 9 for the rows themselves |
| (2) `declarations` | confirmed + `remediation-required`: a required declaration row is absent | step 5 (`0011` widens the `key` CHECK so the `process_ceilings` row may exist), step 6 (`declare-process-ceilings`), step 9 (`declare-surfaces`) |
| (2) `declarations` | blocked, reason `declaration-invalid`: a row exists but its value fails validation | re-declare that row: step 6 for `process_ceilings`, step 9 for `surfaces`, `declare-coalescing-window` for `audit_coalescing_window_ms` (each replaces the whole row) |
| (3) `migrations` | confirmed + `remediation-required`: an application has per-application upgrades pending | step 8 (`upgrade-applications`) |
| (6) `ddl_lock` | `unknown`: a target role carries no role-level `statement_timeout` | step 4 (`0007`, for the api and controlplane roles) and step 7 (`0013`, for the auditreader and the application roles) |
| (6) `ddl_lock` | `unknown`: a target role's `CONNECTION LIMIT` is `-1`, so no timeout value is read at all | step 7 (`0012` sets a finite limit), for a role `0012` itself names -- item (6) reads every target role it finds by grant, so a `-1` on `mitatedbsvc_auditreader` is not resolved by this table (2026-09-18: step 7 now ends with `0014`, which sets `mitatedbsvc_auditreader`'s own `CONNECTION LIMIT` as well, so a `-1` there IS resolved by this table; a `-1` on a role none of the files names still is not) |
| (6) `ddl_lock` | blocked, reason `statement-timeout-unbounded`: a declared value is 0, negative, or unparseable | step 4 and step 7 -- both files set `5000ms` unconditionally. If the unbounded value was one this deployment had chosen on purpose (step 2's record), choose a POSITIVE replacement and pass it to `set-platform-timeouts` in step 4 instead |
| (7) legacy base-URL env | confirmed + `remediation-required`: a legacy name is on the current revision or the current template | step 10 (the env-only change removes both names from the template) |
| (7) legacy base-URL env | blocked: the deploy that will create the candidate carries the legacy names forward without removing them | step 10, plus step 13's own deploy, which must carry the removal flag §10.4.2 step 2 names |
| (8) `connection_headroom` | `unknown`: `--concurrency` was omitted because `MITATEDB_MAX_CONCURRENCY` is not carried by every OLD-basis Data revision counted toward item (8) (§10.4.3), and §10.4.3's own declared-default exception does not apply | step 10 in full -- the env-only change declares the value, and on a service whose traffic is pinned to a revision it also moves the traffic onto the revision that carries it; step 13's own deploy carries the same value to the candidate. **A revision reachable only by a tag keeps its own env**, which a template change does not reach, so if one of those is missing the value this row does not resolve the finding: report and stop. The way out is to take the tag off that revision (`gcloud run services update-traffic <service> --remove-tags=<tag> --project=<project> --region=<region> --quiet`), which is itself a traffic-projection change and therefore carries the same three conditions as step 10's own move (the isolated proof, the independent audit and the requester's approval) -- otherwise it is a separate decision. **A counted revision that takes no traffic but has `minScale` 1 or more keeps its own env too**, the same way a tag-reachable revision does: the way out is its own `minScale` (§10.10's own worked example above, "the way back from a `W` that fails"), decided the same way as the tag removal above -- a template change does not reach it either |
| (8) `connection_headroom` | `unknown`: `--thread-limit` was omitted because a NEW-basis Data revision counted toward item (8) does not carry `MITATEDB_THREAD_LIMIT` | step 10 in full, the same way as the `--concurrency` row above -- declare `MITATEDB_THREAD_LIMIT` on the env-only revision and on the candidate's own step 13 deploy. The same tag-reachable-revision and `minScale`-revision exceptions apply: report and stop if one is missing |
| (8) `connection_headroom` | `unknown`: `--data-process-count-old-basis` (and, with it, `--concurrency`; and `--thread-limit` too for a `MITATEDB_PLATFORM_POOL_SIZE`-carrying revision) was omitted for one of §10.4.3's own reasons -- a `MITATEDB_PLATFORM_POOL_SIZE`-carrying revision among those counted, an OLD-basis revision carrying `MITATEDB_THREAD_LIMIT` or whose own `concurrency` is below 6, an OLD-basis revision whose own attested source ref does not carry the pool-sizing shape the `2 x concurrency` floor assumes, or a revision whose image digest and `MITATEDB_WORKERS` presence disagree | **not a finding this stage resolves.** None of these is a platform-state defect step 4-11 changes; each is a property of which revisions are currently deployed, what they carry and what their own source ref's code does, which only a further deployment decision (redeploying or retiring the revision in question) changes -- report `blocked—platform remediation required` and stop |
| (8) `connection_headroom` | `unknown`: `--reserved-connections` was omitted because the reserve was not established | step 11 |
| (8) `connection_headroom` | `unknown`: a role's `CONNECTION LIMIT` is `-1` | step 7 (`0012`), for a role `0012` itself names -- a `-1` on any other role is not resolved here (2026-09-18: step 7 now ends with `0014`, which names `mitatedbsvc_auditreader` too, so a `-1` on it is resolved here as well; a `-1` on a role none of the files names still is not) |
| (8) `connection_headroom` | `unknown` + `remediation-required`: the `process_ceilings` declaration is absent | step 5 and step 6 |
| (8) `connection_headroom` | blocked: the `process_ceilings` row exists but its value is malformed (a shape or value the declaration read rejects, rather than an absent row) | step 6 (`declare-process-ceilings` replaces the whole row with a valid pair) |
| (8) `connection_headroom` | blocked: the declared `process_ceilings` value does not equal the candidate's own ceiling | step 6 (re-declare the ceilings the candidate will be deployed with) |
| (8) `connection_headroom` | blocked: a role's `CONNECTION LIMIT` is below its own computed demand | **not a finding this stage resolves.** `0012` sets the limits of the roles it names to its own fixed value (68 for the api role, 20 for the controlplane role, 36 for each application's runtime and developer role), raising one below that value and lowering one above it, and it changes no other role's limit: `mitatedbsvc_auditreader`'s own limit stays as `0005` created it, and the provision role's is untouched as well. So a limit below its own demand is a platform-remediation item of its own: report `blocked—platform remediation required` and stop, because changing a `CONNECTION LIMIT` value takes a new platform migration. This is the condition §10.10's preconditions check on paper before anything is changed; step 7 raises the limits `0012` names, so what stops here is a limit still below its own demand once `0012`'s own value is substituted -- the auditreader's, or one `0012` lowers (this row itself names no step to re-run). (2026-09-18: step 7 now ends with `0014_role_connection_limits_rollout.sql`, which raises the api role to 132, the controlplane role to 36, `mitatedbsvc_auditreader` to 12 and each application's runtime and developer role to 68. Substitute THOSE values here: the auditreader is no longer outside the limits step 7 raises, and what stops here is a limit still below its own demand once `0014`'s own values are substituted. **So this row's "not a finding this stage resolves" is now the narrower one**: a first read of a deployment that has not had step 7 yet reports item (8) blocked on limits `0014` itself raises -- the api role's own 68 against a demand of 128 at a worst-case total of 2 OLD-basis processes (O = 2, N = 0: `2 x 2 x 32`) is the ordinary case -- and step 7 resolves exactly those. What this row still does not resolve, and what still stops the procedure, is a limit that is below its own demand once `0014`'s own values have been substituted; raising one above them takes a further platform migration, and for that case this row names no step to re-run) |

**A finding is resolved by this stage only when its row names a step.**
The row for a role's `CONNECTION LIMIT` below its own demand names none,
and neither does anything absent from the table. In particular this stage
does not resolve: item (1) `mismatch` or `unknown`; item (3) blocked with
`ledger-unreadable`, or `unknown` from a per-application read that failed;
item (4) `unknown`; item (5) not confirmed (that is §10.8's acceptance and
§10.6's own source-ref condition, not a state change); item (8) blocked
because a role's `CONNECTION LIMIT` is below its own demand, or because
total demand plus the reserve exceeds `max_connections`; item (9) not
confirmed; item (10) `unknown` or blocked. Report and stop. (2026-09-18:
the item (8) entry in that list is now the conditional one its own row
above carries -- a limit below its own demand **once step 7's own values
are substituted**. A limit that is below its demand only because step 7
has not run yet is resolved by step 7, and is the ordinary first-read
state of a deployment that has not been remediated. The first sentence
above is unchanged for every other entry: a finding whose row names no
step is not resolved here.)

**Steps** (run the whole sequence against the isolated pair first, then
against production):

1. **Fix the rollback target**: immediately before touching anything, read
   §10.4's traffic projection and §10.4.4 again and fix the rollback
   revisions (and their allocation) and their digests in the evidence. If
   they differ from the first read, redo the read. Then, for each §10.6
   row the rollback target does not contain, read the file named in that
   row's last column at the target's own attested source ref and confirm
   the condition stated there. **If any condition cannot be confirmed at
   that ref, item (5) is `unknown` and this stage does not start.**
2. **Record what the numbered set will overwrite.** Re-applying the set is
   idempotent but not value-neutral (§10.6/§10.7's `0007` and `0012`
   rows), so the current values are recorded first:

   ```sh
   ( ...§10.3's subshell... PYTHONPATH=MitateDB-api/src python3 -m mitatedb_api.ops show-declarations ) \
     > <evidence-dir>/declarations-before.json
   ```

   `show-declarations` prints every `platform_declarations` row (key,
   value, `updated_at`) and, for each role named in the
   `audit_writer_roles` row, that role's own `pg_db_role_setting` entries
   -- which is where a value `set-platform-timeouts` wrote shows up. From
   that output record:

   - the `audit_writer_roles` value: the two role names, in order. Step 4
     passes exactly these two, so `0007`'s `DO UPDATE` rewrites the row
     with what is already in it;
   - both writer roles' current `statement_timeout` and
     `idle_in_transaction_session_timeout`. If either differs from
     `5000ms`, step 4 restores it.

   `CONNECTION LIMIT` is not in that output, and no other `ops`
   subcommand prints it either (§10.6's `0012` row), so read it from the
   catalog. **No part of this reads the password out of the DSN.** The
   provision DSN names a `passfile=` (§10.1's own converter puts it there,
   and §3's own note prefers a passfile to a password in the environment),
   so the only secret-bearing variable exported here is `PGPASSFILE`.
   **That passfile is mode `0600`**: libpq silently ignores a more
   permissive one, and psql then tries to connect with no password at all
   (in a shell with a terminal it stops at a prompt instead). The DSN
   itself never enters this subshell and therefore cannot be printed out
   of it. If no passfile exists yet, run §10.1's converter -- printing the
   DSN to lift the password out of it is not an option (§10.1, §10.3):

   ```sh
   (
     set +x
     export PGPASSFILE=<the passfile the provision DSN names>
     export PGHOST=<socket-dir>/<instance-connection-name> PGPORT=5432
     export PGDATABASE=mitatedb_platform PGUSER=mitatedbsvc_provision
     psql -At -c "SELECT rolname, rolconnlimit FROM pg_roles \
       WHERE rolname IN ('<api role>', '<controlplane role>', '<auditreader role>') \
          OR rolname IN (SELECT runtime_role FROM mitatedb_registry.applications WHERE runtime_role IS NOT NULL) \
          OR rolname IN (SELECT developer_role FROM mitatedb_registry.applications WHERE developer_role IS NOT NULL) \
       ORDER BY rolname"
   ) > <evidence-dir>/role-connection-limits-before.txt
   ```

   Keep this subshell separate from every subshell that runs an `ops`
   subcommand: the variables exported here are exactly what an `ops`
   psycopg connection would silently pick up for a parameter its own DSN
   omits (§10.1). The psql-starting subcommands rebuild their own
   environment from the DSN and refuse to start only for a
   connection-setting variable the DSN does NOT override -- the five
   exported here are all named by the provision DSN, so no refusal fires;
   the reason to keep this subshell apart is the psycopg path (§10.1). This
   is a read-only catalog query, and it is the same read
   §10.10's own `CONNECTION LIMIT` precondition uses.

   None of these recorded values is a secret, but they go where every
   other piece of evidence goes (§10.1): a directory outside every git
   work tree, never into this repository and never into a report.
3. **`0005`**: `apply-platform-migration 0005_application_audit.sql
   --lock-timeout <the §10.7 value for 0005>`. It takes no psql variables.
   It is already applied on a deployment that followed §3.2b; re-applying
   it is a no-op, and it is in the set so the numbered order is kept.
4. **`0007`, then restore what it overwrote**:
   `apply-platform-migration 0007_platform_declarations.sql
   --lock-timeout <the §10.7 value for 0007> --api-role <api role>
   --controlplane-role <controlplane role>`, passing exactly the two role
   names step 2 recorded. **Both role arguments are required for this
   file** (§3.2b) -- the subcommand refuses the run, before starting psql,
   if one is missing, and refuses an argument the file does not reference.
   Straight after the apply, and before any restart:

   - re-run `show-declarations` and compare it with step 2's record;
   - if the two writer roles' timeouts are now `5000ms` where step 2
     recorded something else, restore them:

     ```sh
     ( ...§10.3's subshell... PYTHONPATH=MitateDB-api/src python3 -m mitatedb_api.ops \
         set-platform-timeouts --statement-ms <recorded milliseconds> --idle-ms <recorded milliseconds> )
     ```

     **Both arguments take a bare integer number of milliseconds.** The
     recorded value carries a unit (a role setting reads back as `5000ms`),
     so pass the number without it -- a value with the unit still attached
     is rejected as a usage error and nothing is written. That subcommand
     writes one pair of values for both writer roles together, takes its
     target roles from the `audit_writer_roles` row itself, and refuses 0
     or a negative value;
   - if the `audit_writer_roles` row itself now names a different pair
     than step 2 recorded, the wrong names were passed: apply `0007` again
     with the recorded pair (every apply replaces that row).

   A role setting takes effect at each new login, so the restored values
   reach the running processes at the restart in step 14.
5. **`0011`**: `apply-platform-migration 0011_process_ceilings.sql
   --lock-timeout <the §10.7 value for 0011>`, after `0007` (`0011` widens
   the CHECK constraint `0007` created). **Do not run it at the same time
   as a restart** (§10.7's `0011` row: it takes ACCESS EXCLUSIVE on
   `platform_declarations`, and a process starting inside that window
   waits on its own declaration read).
6. **`declare-process-ceilings`**: `--data`/`--control` take the process
   ceilings of the candidate deployed in step 13: its `--max-instances`
   times its `MITATEDB_WORKERS` for `--data`, and its `--max-instances`
   times its `MITATEDB_CONTROL_WORKERS` (1) for `--control` (§6.2's
   Invariant 1, §6.5). Run it after `0011`.

   ```sh
   ( ...§10.3's subshell... PYTHONPATH=MitateDB-api/src python3 -m mitatedb_api.ops declare-process-ceilings --data <n> --control <n> )
   ```

   Both arguments are required positive integers. On a deployment that
   runs no Control process, `--control` still takes a positive integer:
   declare the ceiling Control would be deployed with, since a declaration
   is a permitted maximum rather than a statement about what is deployed
   today, and item (8) does not compare Control's declared ceiling at all
   when `--control-not-deployed` is passed.

   **This step opens a window, stated here and accepted rather than
   reordered**: a Data/Control process reads `process_ceilings` at startup
   and uses the declared value as its own process ceiling (fact:
   `main.build_app` and `control_composition.build_control_service` are
   the only callers of `read_platform_declarations`), so between this step
   and the moment traffic is on the candidate (step 16), a previous
   revision that cold-starts reads the value declared for the candidate.
   The order is forced from both sides: `0011` must widen the CHECK before
   this row can exist at all, and the candidate cannot start before the
   row exists (a missing `process_ceilings` row fails startup closed).

   **That window is accepted only when the value declared here is at or
   above the ceiling the revisions now serving were deployed with** (each
   one's `maxScale` times its worker count, §10.4.3). A process reads the
   declared Data ceiling at startup, and what it publishes depends on its
   own image:

   - a revision whose image runs one process (its `CMD` passes no
     `--workers`) publishes `concurrency` and `requests_per_minute` as
     `enforced` while that ceiling is 1, and as `deployment_required`
     above it (fact: that image's own `capabilities_document.build_
     capabilities_document`);
   - a revision whose image passes `--workers "${MITATEDB_WORKERS}"`
     refuses to start when its `MITATEDB_WORKERS` exceeds that ceiling,
     publishes `concurrency` as `enforced` while its `MITATEDB_WORKERS`
     equals it and as `deployment_required` while it is lower, and
     publishes `requests_per_minute` as `enforced` at any ceiling, counted
     in `0016`'s shared row (fact: `capabilities_document.resolve_limit_
     enforcement` and `main.build_app`).

   Declaring a LOWER ceiling therefore lets a previous one-process
   revision that cold-starts inside the window publish `enforced` while
   more than one process may serve -- a declaration the deployment does
   not keep, which is exactly what a client is entitled to rely on -- and
   stops a previous multi-process revision from starting at all. **This
   step does not cover the downward direction**: it needs a separate
   decision about the order or the value, so stop and ask for one.

   **An OLD-basis revision's own startup check reads the SAME
   `process_ceilings` row, through an older check that computes a
   different bound.** Every OLD-basis revision counted toward item (8),
   and the rollback target (§10.10.1 step 1), carries its own startup
   check for `max_connections` headroom at its own attested source ref;
   that check is separate from, and older than, the worker-count check
   above, and it never raises `deployment_required` -- it refuses to
   start. Its lower bound is `process_ceilings.data x (2 x concurrency, or
   4 x concurrency when the platform has at least one registered
   application) + process_ceilings.control x 16`, using THAT revision's
   own declared `MITATEDB_MAX_CONCURRENCY` (not necessarily the largest
   value §10.4.3's own `--concurrency` argument carries), and the check
   refuses to start when that bound plus `superuser_reserved_connections`
   plus `reserved_connections` exceeds `max_connections`. **Compute this
   bound twice, with that revision's own concurrency and the
   `--data`/`--control` values this step is about to declare, for every
   OLD-basis revision counted toward item (8) and for the rollback
   target.** If it does not hold for one of them, declaring
   the raised ceiling here would let that revision refuse to start on a
   cold start (a scale-out, a restart, or a rollback) before traffic ever
   reaches the candidate -- **this step has no fix for that**: raising a
   role's own `CONNECTION LIMIT` takes a new platform migration
   (§10.10.1's own table), and the ceiling this step is about to declare
   is exactly what widens the gap, not what closes it.

   **When it does not hold, decouple the worker-count raise from the
   ceiling raise instead of forcing them through together.** First, run
   this whole stage with the ceiling left at its CURRENT value (not
   raised) and the candidate's own `MITATEDB_WORKERS` set to `1`: with one
   OLD-basis process (its own declared `concurrency`, default 32) and one
   NEW-basis process (`MITATEDB_WORKERS` 1, default `MITATEDB_THREAD_LIMIT`
   4) side by side, the api role's own demand is `2 x 32 + 2 x 6 = 76` and
   each application's own is `32 + 6 = 38`, both within `0014`'s own 132
   and 68 -- so this first pass needs no ceiling raise at all. Move traffic
   onto that candidate through the rest of this stage as usual. Only once
   every revision counted toward item (8), and the rollback target, is on
   the NEW basis (so the OLD-basis startup check above no longer applies
   to any of them) does the ceiling get raised: run this whole stage again
   from step 1, this time raising `process_ceilings.data` and
   `MITATEDB_WORKERS` together to the intended worker count. **The second
   pass's own rollback target is then the first pass's candidate
   (`MITATEDB_WORKERS` 1, NEW basis)**: the worker-count check above
   refuses a start only when `MITATEDB_WORKERS` exceeds the declared
   ceiling, never when the ceiling is above it, so that target cold-starts
   under the raised ceiling and simply publishes `concurrency` as
   `deployment_required` rather than `enforced` while it does.
7. **`0012`, `0013`, `0014`, as one run**: `apply-platform-migration
   0012_role_connection_limits.sql 0013_role_statement_timeouts.sql
   0014_role_connection_limits_rollout.sql --lock-timeout <the §10.7
   value, the same for `0012`, `0013` and `0014`>`. `0012` must come
   after `0005`; see the numbered-set note and the ADMIN OPTION
   prerequisite above. **Do not run this at the same time as
   provisioning** (§10.7's `0012` section 3, `0013` and `0014` rows: all
   three replace `begin_provision_application`). Then re-run §10.5's
   `inventory` and check `ddl_lock` (item (6)) and `connection_headroom`
   (item (8), headroom against `SHOW max_connections`); the full read is
   step 12.

   **The failure window this run can stop in** (design
   `MITATEDB_PLATFORM_MIGRATION_RUN_V0_1.md` D-4): a failure partway
   through does not undo the files that already applied. If the run
   fails at `0013`, `0012` has already applied, including its section 3
   (`CREATE OR REPLACE FUNCTION begin_provision_application` and the
   following `REVOKE`) -- two statements outside the transaction, each
   auto-committing (§10.7's `0012` section 3 row) -- so
   `begin_provision_application` is left carrying `0012`'s own values
   (`CONNECTION LIMIT` 36, no `statement_timeout`) even though the run
   as a whole did not succeed, a state nothing in this procedure catches
   on its own. `apply-platform-migration` prints which files applied and
   which did not run, and says to re-run the whole run from its first
   file because every file in it is idempotent; do exactly that.

   **`apply-platform-migration` refuses `0012` or `0013` given without
   every one of its own later files in the same call, so a run that
   includes `0012` is always `0012` `0013` `0014`, a run that includes
   `0013` always carries `0014`, and `0014` can still be applied on its
   own.** The path below stays open outside the
   tool (a file applied directly with `psql`). Each of those two
   replaces `begin_provision_application` with its own `CONNECTION
   LIMIT` literals, so after `0014` has been applied:

   - `0012` alone lowers `mitatedbsvc_api` to 68,
     `mitatedbsvc_controlplane` to 20 and every EXISTING application's
     runtime and developer role to 36, and drops `0013`'s
     `statement_timeout` from every FUTURE application's roles
     (`mitatedbsvc_auditreader` is untouched -- `0012` never alters it);
   - `0013` alone leaves every EXISTING role as `0014` set it and lowers
     only every FUTURE application's runtime and developer role, to 36.

   **The first case the next `inventory` reports as item (8) blocked at a
   worst-case total of 2 OLD-basis processes** (the same `O = 2, N = 0`
   case §10.10.1's own item (8) table above works out: `2 x 2 x 32 = 128`
   against the api role's own lowered 68). **The second one nothing
   reports at all until an
   application is provisioned after it**: item (8) compares the roles
   that exist, and until the next `begin_provision_application` call no
   role carries the lowered value, so no item of the read and no other
   check in this procedure turns. That is a limit of what can be
   observed, not a reason to accept the state. **The compensation for
   either case is to apply `0014` once more, and `0014` on its own is
   the one safe single application here**: it sets only its own values,
   and its own `begin_provision_application` carries `0013`'s
   `statement_timeout = 5000ms` for both the runtime and the developer
   role, in the `CREATE ROLE` branch and in the `duplicate_object`
   fallback alike, so re-applying it drops nothing `0013` put in place.

   **On a cluster where a `deprovision` was interrupted, `0012` fails
   and the set does not complete.** An interrupted `deprovision` can
   leave a registry row whose `runtime_role`/`developer_role` name roles
   the catalog no longer carries; `0013` and `0014` skip such a name
   (each tests `pg_roles` before its own `ALTER ROLE`), but `0012`'s own
   per-application loop alters every name the row carries with no such
   test, so it fails with `undefined_object` and its sections 1-2 roll
   back -- the numbered set cannot be completed while the row is in that
   state, and `0014` is never reached. The way out is to finish the
   interrupted deprovision first, with §7's own `deprovision
   <application_id> --lock-timeout <the §10.7 deprovision value>
   --confirm <the printed phrase>` for that application: every drop step
   in the file it runs is `IF EXISTS`, and the registry row is removed
   unconditionally at the end, so running it again on a half-finished
   deprovision completes it rather than failing on what is already gone
   (fact: `0004_deprovision_application.sql`'s own statements). It is
   irreversible for that application (§10.6's `0004` row), so it is a
   step to take deliberately; if the application is not one to
   deprovision, stop and report instead of re-running the set.

   **7a. `0016`**: `apply-platform-migration
   0016_credential_request_rate.sql --lock-timeout <the §10.7 value for
   0016>`. It takes no psql variables, needs `0002` (it references
   `mitatedb_registry.credentials` and grants to `mitatedbsvc_api`), and
   no later file redefines its targets, so it runs alone, after step 7.
   **Skipping it stops the candidate**: on a platform database without its
   rate function, the candidate's data service and its preflight refuse
   to start, naming the migration, and the candidate never becomes ready
   in step 13. It is idempotent. Credential issue and revoke wait
   on it the first time it runs (§10.7's `0016` row).
8. **Per-application upgrade** (`--lock-timeout` is §10.7's
   per-application-upgrade value):

   ```sh
   ( ...§10.3's subshell... PYTHONPATH=MitateDB-api/src python3 -m mitatedb_api.ops upgrade-status )
   ( ...§10.3's subshell... PYTHONPATH=MitateDB-api/src python3 -m mitatedb_api.ops upgrade-applications --dry-run --lock-timeout <value> )
   ( ...§10.3's subshell... PYTHONPATH=MitateDB-api/src python3 -m mitatedb_api.ops upgrade-applications --lock-timeout <value> )
   ```

   Establish which applications are targeted, what is pending, and which
   are registered-only with `upgrade-status` and `--dry-run` before
   applying. On exit status `3`, finish §3.4b's failure procedure (run the
   printed `REVOKE`) and re-run. `upgrade-status` must finish `0` at the
   end. An application in the `ledger-unreadable` state (§10.5) has
   already stopped the procedure before this step.
9. **Declarations**: `declare-surfaces` REPLACES the shared row, so settle
   the values (the Data/Control base URLs; either `--control-base-url` or
   `--no-control`) before running it (§6.1; agreement with each service's
   own `MITATEDB_CONTROL_PLANE_STATUS` is checked at startup). Run it
   before step 10, so the surfaces are declared before the legacy env
   names go away.
10. **The env-only change**: declare `MITATEDB_MAX_CONCURRENCY` and remove
    the legacy base-URL env names from the service's template, with no new
    image:

    ```sh
    gcloud run services update <service> --project=<project> --region=<region> --quiet \
      --update-env-vars=MITATEDB_MAX_CONCURRENCY=<n> \
      --remove-env-vars=MITATEDB_DATA_BASE_URL,MITATEDB_CONTROL_BASE_URL
    ```

    This creates a new revision on the SAME image digest -- it is not the
    candidate, which carries a new digest and is deployed in step 13.
    **What the new revision has to end up with is the digest the
    traffic-carrying revision runs and that revision's own env, plus
    `MITATEDB_MAX_CONCURRENCY` and minus the two legacy names -- nothing
    else added and nothing else dropped.** The two flags above edit the
    template in place, which is exactly that. A deploy form instead of
    `services update` does not: `--set-env-vars` (the flag §6.1/§6.2's own
    deploy commands use) replaces the env wholesale, so anything the
    current revision carries and that command does not list is gone from
    the new revision. If a deploy form is used here, list the complete set.

    **Run this once per service that carries either legacy name** -- item
    (7)'s own targets are the Data and the Control service -- but declare
    `MITATEDB_MAX_CONCURRENCY` on Data, whose revisions are the ones
    §10.4.3 reads that value from. If Control's traffic is pinned to a
    revision as well, the traffic move below is made on that service too.

    **`MITATEDB_THREAD_LIMIT` is declared this same way, but only when the
    env-only revision's own template is a NEW-basis image digest** -- for
    that template, pass both names on the SAME `--update-env-vars=` flag
    (`gcloud` reads one comma-separated list, not one flag per name):

    ```sh
    gcloud run services update <service> --project=<project> --region=<region> --quiet \
      --update-env-vars=MITATEDB_MAX_CONCURRENCY=<n>,MITATEDB_THREAD_LIMIT=<n> \
      --remove-env-vars=MITATEDB_DATA_BASE_URL,MITATEDB_CONTROL_BASE_URL
    ```

    and carry the same value in step 13's own deploy.
    **Never add `MITATEDB_THREAD_LIMIT` to an OLD-basis template**:
    §10.4.3's own list of cases that leave `--data-process-count-old-basis`
    omitted counts an OLD-basis revision carrying `MITATEDB_THREAD_LIMIT` as
    itself a reason for `unknown`, so adding it there trades one `unknown`
    for another.

    Then handle four consequences:

    - `<n>` is the value item (8)'s `--concurrency` is read from in step 12,
      so use one value across every Data revision §10.4.3's own
      `--concurrency` rule reads, and the same value in step 13's own
      deploy;
    - the legacy names must not come back in step 13's own deploy
      (§10.4.2 step 2 names the flag that keeps them out);
    - the new revision becomes the service's current revision. If the
      service's traffic is set to latest it also takes the traffic the
      previous revision had; if traffic is pinned to a revision, it takes
      none until traffic is moved. §10.4's traffic projection is what says
      which of the two this service is. Either way, re-fix step 1's
      rollback record only after the traffic move below, and keep the
      record as it stood before this step as this step's own back-out
      target -- the digest is unchanged, so item (9)'s attestation still
      covers it;
    - **on a service whose traffic is pinned to a revision, move the
      traffic to this new revision here.** Until that happens the revision
      carrying the traffic is still one without `MITATEDB_MAX_CONCURRENCY`,
      so §10.4.3's rule leaves `--concurrency` omitted and item (8)
      `unknown` through the second read, and this step has resolved
      nothing. **This is a production traffic change, so it is covered by
      the same three conditions §10.10's preconditions place on this whole
      stage** (the isolated proof, the independent audit and the
      requester's approval) -- it is not a step to take on Gate-0 ready.
      Move it, then check health, and go back if health does not hold:

      ```sh
      gcloud run services update-traffic <service> --to-revisions=<env-only-revision>=100 \
        --project=<project> --region=<region> --quiet
      ```

      Health: the service's traffic projection shows that revision at
      100%; its Ready condition is `True`; its env no longer carries
      either legacy name; and an authenticated capabilities read against
      the stable service URL succeeds (§6.3's shape, no business
      reads/writes and no operation-depth probe). Back out by moving the
      traffic to the revision (and the allocation) step 1 recorded, with
      the same command shape -- the digest is unchanged and no schema or
      declaration is involved, so that is the whole way back for this step.
11. **Establish the reserved-connection count.** Item (8) stays `unknown`
    until `--reserved-connections` is passed, and the argument accepts `0`
    -- so a deployment that establishes "nothing further is reserved"
    passes `0` rather than omitting the argument. Read the server settings,
    and record the number and its source (for the part the server does not
    report, the Cloud SQL documentation page and the figure it states) in
    the evidence:

    ```sh
    (
      set +x
      export PGPASSFILE=<the passfile the provision DSN names>
      export PGHOST=<socket-dir>/<instance-connection-name> PGPORT=5432
      export PGDATABASE=mitatedb_platform PGUSER=mitatedbsvc_provision
      psql -At -c "SELECT name, setting FROM pg_settings WHERE name IN ('superuser_reserved_connections', 'reserved_connections', 'max_connections') ORDER BY name"
    ) > <evidence-dir>/reserved-connections.txt
    ```

    The same read-only shape as step 2, with the same rules: `PGPASSFILE`
    rather than the password field, and a subshell of its own, apart from
    every subshell that runs an `ops` subcommand (§10.1).
    `max_connections` comes back in the same read because §10.10's
    `CONNECTION LIMIT` precondition needs it.

#### 10.10.2 Stage 3 -- the second read

12. **Read everything again.** Re-run §10.4 and §10.5 in full and judge
    all 10 items by §10.9 again -- not only the items stage 2 touched. Use
    the same evidence directory with fresh file names (`...-after`), and
    report the result with `(second read)` in the header line.

    - **Gate-0 is ready only when all 10 items come back confirmed AND
      §10.8's acceptance records name the current versions.** Then, and
      only then, stage 4 starts.
    - **An item that is still not confirmed stops the procedure here.** It
      is reported as `blocked—platform remediation required` with the
      breakdown, exactly as in the first read. An `unknown` is never
      downgraded to a warning and never carried into stage 4.
    - **One exception, and only this one: a finding that appears here and
      whose row in §10.10.1's table names a step may be cleared by running
      that step again and reading again.** Item (8) reports one cause at a
      time -- the first one in its own order of evaluation -- so a
      deployment with two causes in that table needs more than one read,
      and the second cause is expected to show up only once the first is
      gone. That is not "repeating stage 2 in the hope of a different
      answer": the step that runs again is the one the table names for the
      finding in hand, and the read that follows judges all 10 items
      again. A finding whose row names no step, or one the table does not
      carry at all, stops the procedure here as above.
    - `remediation-required` notes that stage 2 was supposed to clear
      should be gone; one that is still there means the step that was
      meant to clear it did not, so treat it as a finding, not as a note.

#### 10.10.3 Stage 4 -- candidate, health, traffic

Gate-0 ready (step 12) gates exactly this stage.

13. **Deploy the candidate**: use §6.1/§6.2's deploy with `--no-traffic`
    to create the candidate. It carries the digest the second read
    attested, and it must not reintroduce the legacy env names
    (`MITATEDB_DATA_BASE_URL`, `MITATEDB_CONTROL_BASE_URL`): if the deploy
    carries env forward, pass the removal flag §10.4.2 step 2 names.
    **The deploy's own env must include
    `MITATEDB_MAX_CONCURRENCY=<the value step 10 declared>`**,
    `MITATEDB_THREAD_LIMIT=<the value used for item (8)'s own
    --thread-limit, §10.4.3>`, and `MITATEDB_WORKERS=<the worker count
    step 6's --data was computed from>` (§6.5: `MITATEDB_WORKERS` is
    required and has no default; `MITATEDB_THREAD_LIMIT` falls back to 4
    when unset, which is why it is set here explicitly, matching the
    value item (8) was judged on). `MITATEDB_MAX_CONCURRENCY` is required
    here for its own admission-slot bound (§6.5's `concurrency` slot
    directory), on the candidate exactly as on every other revision --
    item (8) reads it as a judging value only from an OLD-basis revision
    (§10.4.3); the candidate itself, being NEW-basis, is judged from
    `MITATEDB_THREAD_LIMIT` instead. §6.1/§6.2's deploy sets the env with
    `--set-env-vars`, which replaces it wholesale, so step 10's
    declaration is not inherited by a revision this command creates:
    leave a name out and the candidate runs on the code's own default for
    it instead of the declared value, which for `MITATEDB_THREAD_LIMIT`
    is the role `CONNECTION LIMIT` demand `0014` exists to bound.
    **On a deployment that runs Control, Control's own candidate deploy
    carries `MITATEDB_CONTROL_WORKERS=1`** (§6.2: required, always 1) **and
    the SAME `MITATEDB_THREAD_LIMIT` value as Data's own candidate**
    (`control_composition.build_control_service` reads it from its own
    process env the same way `main.build_app` does). Do not
    modify the rollback target revisions. After deploying, do §10.4.2
    step 3 and §10.4.3 step 3, and read the candidate's own
    `MITATEDB_MAX_CONCURRENCY`, `MITATEDB_THREAD_LIMIT` and
    `MITATEDB_WORKERS` back as well: if any of the three differs from the
    value the second read used, item (8) was judged on a value this
    deployment does not run, so redo the read -- the same rule §10.4.3
    step 3 applies to a ceiling that reads back differently. On a
    deployment that runs Control, read Control's own candidate
    `MITATEDB_CONTROL_WORKERS` and `MITATEDB_THREAD_LIMIT` back the same
    way; redo the read on the same disagreement.
14. **Restart Data/Control**: declarations are read at startup, so the
    candidate's own start IS the restart, and it is where step 4's
    restored role settings reach the processes. When the change shortens a
    writer timeout, bring Data up first; when it lengthens one, bring
    Control up first (§3.2b).
15. **Health (before moving traffic)**: the candidate's Ready condition is
    `True`; the candidate's digest equals the digest attested in the
    second read; the candidate's env names no longer carry the legacy
    names. Over the provision DSN run `show-declarations`,
    `verify-declarations` (with `--control` too on a deployment that runs
    Control) and `upgrade-status`, and all must succeed. Some
    `verify-declarations` checks judge from the operator's own shell
    environment and local code, so use them for this post-check only,
    never as grounds for a Gate-0 confirmed. Call the candidate's own tag
    URL only when the deploy that created it assigned a tag (§6.1/§6.2's
    own deploy commands assign none, and a `--no-traffic` revision without
    a tag has no URL of its own to call) and the requesting side's own
    design says its preconditions are met.
16. **Traffic**: `gcloud run services update-traffic <service>
    --to-revisions=<candidate-revision>=100 --project=<project>
    --region=<region> --quiet`.
17. **Health (after moving traffic)**: the service's traffic projection
    shows the candidate at 100%; the Ready condition holds; an
    authenticated read of capabilities against the stable service URL
    succeeds (§6.3's shape). Do not mix in business reads/writes,
    fixtures, or an operation-depth probe.

**Rollback**:

- Move traffic back to the target fixed in step 1: `gcloud run services
  update-traffic <service> --to-revisions=<rollback-revision>=100
  --project=<project> --region=<region> --quiet` (if the allocation was
  split, restore the allocation that was fixed).
- Schema and declarations are NOT reverted (§10.6's compatibility rows are
  what make that safe).
- **The `process_ceilings` declaration stays at step 6's own value; it is
  never moved back by this rollback.** The rollback target cold-starts
  under that same declared ceiling, so it cold-starts only when step 6's
  own OLD-basis startup-check arithmetic (above) held for it before step 6
  ran -- a rollback target for which that arithmetic did not hold cannot be
  brought back this way at all, and that is checked before step 6 runs,
  not discovered here.
- **One part of that safety is unverified, and this is where it is felt.**
  §10.6's `0007` row is compatible by inference with one part left open:
  whether a pre-`0007` rollback target's other queries (registry reads and
  the like) all finish inside the 5-second role-level `statement_timeout`
  that migration sets on `mitatedbsvc_api`/`mitatedbsvc_controlplane` has
  not been verified. A role setting applies at login, so a target that
  cold-starts after the migration opens its sessions under that bound, and
  a query above it is cancelled with `canceling statement due to statement
  timeout`. Accepting §10.6 at its current version accepts that residual
  risk; when the rollback target is a pre-`0007` revision, this is the
  route the risk lands on, and there is no second way back (the schema and
  the declarations stay as the stage left them).
- **After traffic has moved, a failure means checking the requesting
  side's own design first**: whether the requesting application must be
  returned to its own previous Ready revision before this Data Service is
  moved back.
- These are never part of an automatic rollback: deleting a secret
  version, revoking a credential, deleting a Cloud SQL resource, or
  rewriting the env of a rollback target revision.

**Closing this section** (after a completed run, and equally after one
that stopped at any step): remove the passfile §10.1 derived and the
directory holding it and the converter, and unset
`MITATEDB_PROVISION_PASSFILE`. Nothing else outside Secret Manager carries
the provision password, so this is what puts it back to one place. The
evidence directory stays where §10.1 put it.
