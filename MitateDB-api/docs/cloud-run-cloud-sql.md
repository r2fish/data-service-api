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

The declared `visibility_lag_ms` is derived from `MITATEDB_AUDIT_
STATEMENT_TIMEOUT_MS` + `MITATEDB_AUDIT_IDLE_TIMEOUT_MS` (both default
`5000`, read by BOTH the data service and the control service -- they
must agree) plus a fixed 1000ms clock-skew margin (11000ms at defaults).

**Verify the two timeouts are genuinely applied** (WP-3(b) review finding
H) -- from a session authenticated as the writer role each service
actually connects as (`mitatedbsvc_api` for the data service's own
`application_audit` writer, `mitatedbsvc_controlplane` for the control
service's own `control_audit` writer), confirm both SESSION-level values
match the configured/default env vars:

```sh
psql "host=127.0.0.1 port=5432 dbname=mitatedb_platform user=mitatedbsvc_api password=$MITATEDBSVC_API_PASSWORD" -c \
  "SHOW statement_timeout; SHOW idle_in_transaction_session_timeout;"
psql "host=127.0.0.1 port=5432 dbname=mitatedb_platform user=mitatedbsvc_controlplane password=$MITATEDBSVC_CONTROLPLANE_PASSWORD" -c \
  "SHOW statement_timeout; SHOW idle_in_transaction_session_timeout;"
```

Both must report the SAME two values (the default `5s`/`5s`, or whatever
`MITATEDB_AUDIT_STATEMENT_TIMEOUT_MS`/`MITATEDB_AUDIT_IDLE_TIMEOUT_MS` are
set to on both Cloud Run services) -- a mismatch between the two
processes silently invalidates the derived `visibility_lag_ms` this
section declares (the declaration is computed once, by the control
service alone, from ITS OWN env; nothing enforces the data service
agreeing with it).
The `audit_requests_per_minute` window is a SEPARATE pre-auth counter from
`control_requests_per_minute` (`MITATEDB_CONTROL_AUDIT_REQUESTS_PER_
MINUTE_LIMIT`, default 60) -- never shared, so a high-frequency audit
poller cannot exhaust the window a break-glass `revoke_credential` depends
on. Like `control_requests_per_minute` (Invariant 1, §6.2), this window is
an in-process counter too, so it inherits the SAME `--max-instances=1`
requirement on `mitatedb-ctrl`.

`coalescing_window_ms` (the declared denial-coalescing window, part of the
`audit_query` capability entry) is derived from the SAME single source
constant the data-plane's own `AuditRouter` falls back to
(`application_audit.DEFAULT_DENIAL_COALESCE_WINDOW_S`, 60s) -- the control
service (a separate process) cannot read the data-plane process' own live
`AuditRouter` instance. If a future deployment ever constructs `AuditRouter
(denial_coalesce_window_s=...)` with a non-default value on the data-plane
side, this declaration must be updated to match by hand (there is no
env-var knob for it today) -- exactly the same "both processes must agree"
caveat this section's own `visibility_lag_ms` note above already carries.
State the rule for both values as one rule: **if you change the value, you
have changed the declaration, and the declaration must be changed with it.**

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

Two corrections to that naive product. (i) **Catch-up is paging, not
polling**: a consumer resuming after an outage walks the cursor one page per
request until a page comes back empty, so draining N backlogged events at
`limit` per page costs `N/limit` requests issued as fast as it can -- far
above steady state. (ii) **The accepted range is `[1, 200]`**
(`ControlPlaneLimits.__post_init__`, shared with the other request-count
classes), so past roughly 36 steady-state consumers, or on any catch-up
burst wanting more than 200 requests in a minute, the **range ceiling binds
before the default does**. That ceiling follows from folding the new class
into the existing range instead of inventing a second mechanism; raising it
is a design change, not a configuration change. **That ceiling is specific
to this peer** -- `r2db-api`'s own `ControlPlaneLimits.__post_init__`
validates only "positive integer" and has no upper bound, so the equivalent
change there is a single env var. The contract declares no range for this
class, so both peers conform; the asymmetry is recorded in
`security/CONTROL_MAPPING.md`'s SI-08 row. Exceeding the window is a
plain `LIMIT_EXCEEDED` refusal that costs only time -- the consumer's cursor
stays valid and it resumes exactly where it stopped. In every case a
break-glass `revoke_credential` is unaffected: `audit_query` never touches
`control_requests_per_minute` (`MitateDB-api/tests/test_audit_query.py::
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

**Known sharpness, both peers**: the flush "failing" flag clears only when
the buffer fully drains, so under continuous load it can stay set after the
sink has actually recovered, holding the alert re-fire interval at the 60s
backoff ceiling. No evidence is lost (the drop counter keeps accumulating and
is reported in the eventual alert row's `count`), but **do not read a gap
between messages as recovery** -- read the recovery message of the pair
concerned (the third message for the buffer/overflow channel, the fifth for
the coalescing one).

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

**Build the image first, from the repository root** (2026-09-01 fix, first
deployment finding): `docker/Dockerfile`'s runtime stage now packages a copy
of the common contract (`spec/data-service-api.v1.json`) into the image at
the exact filesystem path `mitatedb_api.http`'s own `_CONTRACT_PATH`
resolves to inside a `pip install .` venv layout
(`/opt/venv/lib/spec/data-service-api.v1.json` -- see that Dockerfile's own
comment for the `.parents[3]` arithmetic). `spec/` lives one level above
`MitateDB-api/`, at the common repository root, so this image must be built
with the REPOSITORY ROOT as build context, naming the Dockerfile
explicitly, not from inside `MitateDB-api/` the way a package-local
Dockerfile normally would be:

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
# capabilities declaration (§4-1/§4-2)
curl -sk \
  -H "Authorization: Bearer <control credential id>.<control credential secret>" \
  -H "X-Serverless-Authorization: Bearer $(gcloud auth print-identity-token --audiences=<mitatedb-ctrl Cloud Run URL>)" \
  <mitatedb-ctrl Cloud Run URL>/control/v1/capabilities
# expect 200; capabilities.audit_query.status == "enabled" if MITATEDB_AUDIT_DSN is
# wired (else "unavailable", not a failure -- §4-6); capabilities.contract_version == "1.4.0"

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
