# r2db-api PostgreSQL provisioning runbook

Status: operator runbook for `r2db-api/migrations/`. Companion to
`docs/design/R2DB_SERVICE_LAYER_ARCHITECTURE.md` §5.3 (deployment target:
the existing VPS) and `security/SECURITY_INVARIANTS_V1.md` (SI-00, SI-01,
SI-02, SI-03).

This document names environment-variable *names* and uses synthetic
examples (`example.invalid`) only. It never contains a real host,
credential, or DSN. Per CLAUDE.md's Public Repository Security Gate, treat
every file in this repository as public from creation time.

## 1. What this provisions, and what it deliberately does not

`r2db-api/migrations/` provisions a **new, separately-namespaced**
PostgreSQL footprint for the service-layer implementation described in
`R2DB_SERVICE_LAYER_ARCHITECTURE.md`. It does **not** touch, migrate, or
depend on the currently-running old `r2db-api` deployment
(`project/r2-vps/apps/r2db-api`), and it never has that deployment's
credentials in the first place -- that absence of connection information
*is* the isolation evidence design §5.3 C-1 asks for, not merely a
convention this runbook asks you to follow separately.

Every object this migration set creates carries the `r2dbsvc_` prefix:

| Object | Name |
|---|---|
| bootstrap/control-plane login role | `r2dbsvc_control` |
| platform database | `r2dbsvc_platform` |
| control-plane bookkeeping schema | `r2dbsvc_registry` (inside `r2dbsvc_platform`) |
| per-application schema | `r2dbsvc_app_<slug>` |
| per-application runtime role | `r2dbsvc_app_<slug>_runtime` |
| per-application developer role | `r2dbsvc_app_<slug>_developer` |

None of these names, ports, or database identifiers are shared with, or
derived from, whatever the existing deployment uses. If the existing
deployment happens to already use a name with the `r2dbsvc_` prefix
(unexpected, but verify before running 0001), stop and pick a different
prefix throughout `migrations/` and this runbook before proceeding, rather
than assume.

## 2. Roles and who runs what (design D-3, §5.3 C-2)

There are three distinct credential tiers in this flow, and **the
application process never holds the first two**:

1. **Bootstrap/cluster administrator** -- an existing superuser, or a role
   with `CREATEROLE` and `CREATEDB`, on the target PostgreSQL cluster. Used
   exactly once, to run `0001_bootstrap_control_plane.sql`. Not stored
   anywhere the application reads.
2. **`r2dbsvc_control`** -- the provisioning/operator role `0001` creates.
   Has `CREATEROLE` (to create per-application roles) but explicitly
   `NOSUPERUSER` and `NOCREATEDB`. Used to run `0002_provisioning_functions.sql`
   once, and thereafter to call `provision_application(...)` /
   `deprovision_application(...)` whenever an application is onboarded or
   removed. **This credential lives only with whoever operates the
   platform** (a deploy script, a human operator's own session) -- it is
   never given to the `r2db-api` HTTP process, and it is not one of the
   environment variables the application reads (see §4). This is the literal
   realization of §5.3 C-2: "the API process's role does not have
   `CREATEDB`/`CREATEROLE`/superuser," because the API process never even
   receives this credential to begin with.
3. **Per-application `runtime`/`developer` roles** -- created by
   `provision_application`, one pair per application. These *are* what the
   `r2db-api` process uses at request time, via `r2db_api.postgres.PostgresCell`.
   Each is a plain login role scoped to exactly one application's schema
   (see `R2DB_SERVICE_LAYER_ARCHITECTURE.md` D-3), with no `CREATEROLE`,
   `CREATEDB`, or superuser of its own.

## 3. Order of operations

```
1. (cluster admin)  psql "$R2DBSVC_BOOTSTRAP_ADMIN_DSN" \
                       -v control_password="$R2DBSVC_CONTROL_PASSWORD" \
                       -f r2db-api/migrations/0001_bootstrap_control_plane.sql

2. (r2dbsvc_control) psql "$R2DBSVC_CONTROL_DSN" \
                       -f r2db-api/migrations/0002_provisioning_functions.sql

3. (r2dbsvc_control) -- once per application being onboarded:
                     psql "$R2DBSVC_CONTROL_DSN" -c \
                       "SELECT r2dbsvc_registry.provision_application(
                          'myapp',
                          :'runtime_password',
                          :'developer_password'
                        );" \
                       -v runtime_password="$(openssl rand -base64 32)" \
                       -v developer_password="$(openssl rand -base64 32)"

                     Record the two generated passwords in your secret
                     manager immediately -- `provision_application` does not
                     return them, and there is no way to recover a
                     PostgreSQL role's password after the fact (only reset
                     it, via `ALTER ROLE ... PASSWORD ...` run again by
                     `r2dbsvc_control`).
```

Step 1 and step 2 are each safe to re-run: `0001` checks
`pg_roles`/`pg_database` before creating anything, and `0002` uses `CREATE
SCHEMA IF NOT EXISTS` / `CREATE OR REPLACE FUNCTION`. Step 3 is **not**
idempotent by design -- `provision_application` raises if the slug is
already provisioned, so a re-run is a deliberate signal, not silently
absorbed.

To remove an application (e.g. tearing down a test/staging application):

```
psql "$R2DBSVC_CONTROL_DSN" -c \
  "SELECT r2dbsvc_registry.deprovision_application('myapp');"
```

This drops that application's schema (`CASCADE`, i.e. every table in it)
and both its roles. It does not touch any other application's schema, role,
or data -- verified for exactly this property by
`r2db-api/tests/test_postgres.py::test_cross_application_isolation_at_database_level`.

### A note on `psql`'s password variables

Steps that pass a password use `psql`'s own `-v name=value` /
`:'name'`-in-SQL substitution, not a `DO $$ ... $$` block -- `psql`
deliberately does not expand `:'var'` inside a dollar-quoted body, so a
password can only reach a plain, non-dollar-quoted statement this way (see
the comment at the top of `0001_bootstrap_control_plane.sql` for why that
matters). Whatever secret-manager tooling replaces `$(openssl rand ...)` in
your actual deploy script should preserve that same shape: the password
value flows through `-v`, never concatenated into SQL text your own script
builds.

Passwords set via `CREATE ROLE ... PASSWORD ...` / `ALTER ROLE ...
PASSWORD ...` appear in plaintext in that statement's SQL text. If cluster
statement logging (`log_statement`) is enabled at `all` or `mod`, either
run steps 1 and 3 with logging temporarily reduced for that session, or
treat the log destination itself as credential-bearing and handle it under
the same access controls as a secret store. This is a general PostgreSQL
operational property of `CREATE ROLE ... PASSWORD`, not specific to this
migration set.

## 4. Environment variables the `r2db-api` process itself reads

None of the variables in §3 above (`R2DBSVC_BOOTSTRAP_ADMIN_DSN`,
`R2DBSVC_CONTROL_DSN`) are read by the `r2db-api` application process --
those are operator-only, per §2. The application process, once
`r2db_api.postgres.PostgresCell` is wired into `DataService` (a deliberately
separate follow-up step -- see `R2DB_SERVICE_LAYER_ARCHITECTURE.md` §3 step
2 and this work order's own scope note), needs exactly two DSNs *per
application it serves*: the `runtime` and `developer` connection strings
`PostgresCell.__init__`'s `runtime_dsn`/`developer_dsn` parameters expect.

Suggested environment-variable naming for that follow-up wiring step (not
yet implemented by this change set -- `PostgresCell` currently takes these
as constructor arguments, supplied by whatever wires it into `DataService`):

```
R2DB_PG_RUNTIME_DSN_<APPLICATION_SLUG>=postgresql://r2dbsvc_app_<slug>_runtime:REPLACE_ME@example.invalid:5432/r2dbsvc_platform
R2DB_PG_DEVELOPER_DSN_<APPLICATION_SLUG>=postgresql://r2dbsvc_app_<slug>_developer:REPLACE_ME@example.invalid:5432/r2dbsvc_platform
```

Add the corresponding synthetic entries to `.env.example` (repository root)
when that wiring step lands, following the existing `DATABASE_URL` example
there -- name only, never a real value.

## 5. Network isolation (§5.3 C-3) -- verify, do not assume

This runbook and the migration SQL cannot prove PostgreSQL is unreachable
from outside the VPS; that is deployment configuration, not application
code, per §5.3 C-3. Before/alongside running `0001`, confirm on the target
host:

- `postgresql.conf`'s `listen_addresses` does not bind a public interface
  (loopback / Unix socket only, matching how this runbook's own local
  development and test setup connects via `host=/tmp` / `localhost`).
- `pg_hba.conf` restricts each `r2dbsvc_*` role to the expected local
  socket/loopback method, and does not grant it (or `PUBLIC`) a broader
  `host` line reachable from outside.

Record the actual verified configuration in
`security/CONTROL_MAPPING.md` as deployment-control evidence once this is
run against the real VPS -- that document, not this runbook, is where
platform-control evidence for the common Security Invariants is expected to
live per CLAUDE.md's development order.

## 6. Local development / test posture

`r2db-api/tests/test_postgres.py` runs steps 1-3 above end-to-end against a
local PostgreSQL server, entirely under a random-per-run throwaway prefix
(`r2dbtest<8 hex chars>_...`, never `r2dbsvc_`), and drops everything it
created -- including its own throwaway control-plane bootstrap -- in a
fixture teardown that runs even on failure. It takes its admin/bootstrap DSN
from `R2DB_TEST_ADMIN_DSN` (default: `host=/tmp port=5432 dbname=postgres`,
matching a typical local Homebrew/Postgres.app socket setup), so the same
test file can run against a differently-configured server (including,
eventually, the VPS's own PostgreSQL instance, once §5.3's connection
constraints allow reaching it for a controlled test run) by overriding that
one variable -- never by editing the test file.

If PostgreSQL is not reachable, these tests fail with a message naming the
DSN that failed; they do not skip (§5.3 C-5).
