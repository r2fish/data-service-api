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
                         ┌─────────────────────────┐
  mitate-application ──▶ │ Cloud Run: mitatedb-data │──▶ Cloud SQL
  (its own service       │ mitatedb_api.main:app    │    (mitatedb_platform +
   account only)         │ /v1/*                    │     one DB per app)
                         └─────────────────────────┘
                         ┌─────────────────────────┐
  operator (IAM-gated,   │ Cloud Run: mitatedb-ctrl │──▶ Cloud SQL
  --no-allow-unauth.) ──▶│ mitatedb_api.control_    │    (mitatedb_platform
                         │ main:app  /control/v1/*  │     registry only)
                         └─────────────────────────┘
```

Two separate Cloud Run services from the SAME container image (`docker/
Dockerfile`, `SERVICE=data` / `SERVICE=control`) -- design R-6/R-9's own
"独立 ASGI app...既定は分離" default. Both connect to the SAME Cloud SQL
instance's `mitatedb_platform` database, as two DIFFERENT PostgreSQL roles
with disjoint grants (`mitatedbsvc_api` read-only on `applications`/
`credentials`, nothing on `control_credentials`/`control_audit`;
`mitatedbsvc_controlplane` read/write on `applications`/`credentials`/
`control_credentials`, INSERT-only on `control_audit` -- migration `0002`,
design R-4's own process-role separation).

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
  --set-secrets=MITATEDB_CREDENTIAL_PEPPER=mitatedb-credential-pepper:latest,MITATEDB_CONTROL_CREDENTIAL_PEPPER=mitatedb-control-credential-pepper:latest,MITATEDB_CONTROLPLANE_DSN=mitatedb-controlplane-dsn:latest
```

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
python -m mitatedb_api.ops revoke-credential crd_0123456789abcdef
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
