# r2db-api PostgreSQL provisioning runbook

Status: operator runbook for `r2db-api/migrations/`. Companion to
`docs/design/R2DB_SERVICE_LAYER_ARCHITECTURE.md` §5.3 (deployment target:
the existing VPS) and §8 ("D-3 改訂" -- database-per-application, the
topology this runbook now describes) and
`security/SECURITY_INVARIANTS_V1.md` (SI-00, SI-01, SI-02, SI-03).

This document names environment-variable *names* and uses synthetic
examples (`example.invalid`) only. It never contains a real host,
credential, or DSN. Per CLAUDE.md's Public Repository Security Gate, treat
every file in this repository as public from creation time.

## 0. Topology: database-per-application

Each application gets its own PostgreSQL **database** (not merely its own
schema inside one shared database, as an earlier revision of this runbook
described). That application's entities live in that database's `public`
schema. The two per-application roles (`runtime`, `developer`) are
unchanged in spirit: `runtime` gets DML only, `developer` owns `public` and
can DDL there. See §8 of the architecture document for the full rationale
-- in short: a database boundary in PostgreSQL admits no cross-database
query path at all without FDW/dblink (never granted here), whereas a
schema boundary can be crossed by a single missed `REVOKE`/RLS policy. The
database boundary is now the primary wall; RLS remains a secondary,
verified one (§3 below).

## 1. What this provisions, and what it deliberately does not

`r2db-api/migrations/` provisions a **new, separately-namespaced**
PostgreSQL footprint for the service-layer implementation described in
`R2DB_SERVICE_LAYER_ARCHITECTURE.md`. It does **not** touch, migrate, or
depend on the currently-running old `r2db-api` deployment
(`project/r2-vps/apps/r2db-api`), and it never has that deployment's
credentials in the first place -- that absence of connection information
*is* the isolation evidence design §5.3 C-1 asks for, not merely a
convention this runbook asks you to follow separately.

**Namespace collision, re-examined for database-per-application.** The
existing VPS deployment is *also* database-per-application (its own
`app_<slug>_<hex>` naming convention). Before this revision, this
implementation's own per-application objects were schemas living inside
one shared `r2dbsvc_platform` database -- invisible to `pg_database`
entirely, so a name collision against the existing deployment's databases
was structurally impossible regardless of naming. That is no longer true:
this implementation's per-application objects are now themselves real
entries in the same cluster's `pg_database` catalog the existing
deployment's databases live in, so the collision surface is real and must
be checked deliberately, not assumed away by the old argument. It remains
impossible here specifically because the two prefixes differ at the very
first character -- `r2dbsvc_app_<slug>` vs. `app_<slug>_<hex>` -- for
every possible `<slug>`/`<hex>`, not because of the different topology.
Every object this migration set creates carries the `r2dbsvc_` prefix:

| Object | Name |
|---|---|
| bootstrap/control-plane login role | `r2dbsvc_control` |
| control-plane database (bookkeeping only, no application data) | `r2dbsvc_platform` |
| control-plane bookkeeping schema | `r2dbsvc_registry` (inside `r2dbsvc_platform`) |
| per-application database | `r2dbsvc_app_<slug>` |
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
   Has `CREATEROLE` (to create per-application roles) **and now
   `CREATEDB`** (to create each application's own database -- see §8.5
   condition 1 of the architecture decision; database-per-application
   means provisioning an application means creating a database, not just a
   schema), but explicitly `NOSUPERUSER`. Used to run
   `0002_provisioning_functions.sql` once, and thereafter to run
   `0003_provision_application.sql` / `0004_deprovision_application.sql`
   whenever an application is onboarded or removed. **This credential
   lives only with whoever operates the platform** (a deploy script, a
   human operator's own session) -- it is never given to the `r2db-api`
   HTTP process, and it is not one of the environment variables the
   application reads (see §4). This is the literal realization of §5.3
   C-2: "the API process's role does not have
   `CREATEDB`/`CREATEROLE`/superuser," because the API process never even
   receives this credential to begin with.

   `r2dbsvc_control`'s `CREATEDB` privilege is still far short of
   superuser: it can create databases (and, per §8.5's own investigation,
   still cannot create event triggers, which PostgreSQL reserves for true
   superuser with no delegation path -- see §3 below for why that matters
   and what this implementation does instead).
3. **Per-application `runtime`/`developer` roles** -- created by
   `0003_provision_application.sql`, one pair per application. These *are*
   what the `r2db-api` process uses at request time, via
   `r2db_api.postgres.PostgresCell`. Each is a plain login role with
   `CONNECT` on exactly one application's database (and nothing else in
   the cluster), with no `CREATEROLE`, `CREATEDB`, or superuser of its own.

## 3. RLS automation: why not a template-database event trigger, and what runs instead

Architecture §8.5 condition 3 asks for RLS to survive without depending on
runtime code remembering to enable it, and names a preferred approach:
(a) a `CREATE EVENT TRIGGER` in a template database, so `CREATE DATABASE
... TEMPLATE` propagates automatic RLS enablement to every future table in
every application database, with no application code involved at all.

**This runbook does not implement (a).** `CREATE EVENT TRIGGER` is
unconditionally superuser-only in PostgreSQL -- there is no ownership or
`GRANT`-based delegation path for it, unlike every other privilege this
migration set manages. §2 above documents the bootstrap/cluster
administrator who runs `0001` as either "an existing superuser, **or** a
role with `CREATEROLE` and `CREATEDB`" -- deliberately not requiring true
superuser. Depending on event-trigger automation would silently require
the *stronger* of those two options every time, on a target (the existing
VPS, §5.3) where that is not confirmed to hold, and RLS automation would
then only be as trustworthy as "did whoever ran 0001 happen to have
superuser that day." That is exactly the kind of unverified assumption
CLAUDE.md's Security Invariants section asks not to be papered over.

**What runs instead is (b):** `PostgresCell._create_entity`
(`r2db-api/src/r2db_api/postgres.py`) still enables and forces RLS on
every table it creates, exactly as before this revision -- and
additionally, in the same transaction, calls
`PostgresCell.verify_row_level_security()`, which re-derives from live
`pg_class`/`pg_namespace` catalog state whether *every* table in the
application's database has RLS enabled and forced, and refuses to let the
transaction commit if not. This is checked, not assumed: a bug in the
RLS-enabling code, or a table created by some future code path that
forgets to call it, is caught before commit, not discovered later.

`0003_provision_application.sql` additionally installs a SQL-level
equivalent of the same query, `public._r2db_missing_rls`, directly inside
every application's own database -- so an operator (or a monitoring
script) can run `SELECT * FROM _r2db_missing_rls;` against any application
database at any time, independent of the application process, and expect
an empty result. `r2db-api/tests/test_postgres.py::
test_verify_row_level_security_detects_missing_rls` exercises both forms,
including deliberately disabling RLS on a table outside `PostgresCell` to
confirm the check actually detects drift rather than only ever agreeing
with what `PostgresCell` itself already believes.

## 4. Connection ceiling

Historical note: before this section's current revision, every
`PostgresCell` created its own two `_RolePool`s (`runtime`/`developer`) and
held them forever once opened, lazily up to `pool_size` connections each.
Effective cluster-wide consumption was `applications × 2 roles ×
pool_size`, growing without bound as applications were onboarded -- at
`pool_size = 4`, 11 applications already reached 88 connections and 13
reached 104, against this cluster's default `max_connections = 100`. That
unbounded growth is what `r2db_api.postgres.SharedPoolManager` fixes.

`PostgresCell`'s `runtime`/`developer` pools are no longer private to that
cell. They are handles (`_PoolHandle`) onto pools owned by one shared,
process-wide `SharedPoolManager` (`default_pool_manager`, or an injected
one), keyed by `(application_id, role)`, with:

- **idle eviction** -- a pool unused for `R2DB_POOL_IDLE_SECONDS` (default
  `300`) is closed and dropped from the cache the next time the manager is
  consulted for any key;
- **an LRU cap on live pools**, `R2DB_POOL_CACHE_MAX` (default `32`) -- the
  property that actually decouples the ceiling from application count:
  however many applications are onboarded, at most `cache_max` pools are
  ever open in this manager at once, the least-recently-used one evicted
  to make room for a new one beyond that;
- **a fixed per-pool connection cap**, `R2DB_POOL_SIZE` (default `2`) +
  `R2DB_POOL_MAX_OVERFLOW` (default `2`) = `4` connections per pool --
  matching the currently deployed reference implementation's effective
  per-application capacity (`r2-vps/apps/r2db-api/src/r2db_api/pools.py`'s
  SQLAlchemy `pool_size=2, max_overflow=2`), though this module's pools do
  not distinguish a "core" size from "overflow" the way SQLAlchemy's do --
  both knobs simply sum into one `maxconn` (`SharedPoolManager`'s
  `_default_maxconn`).

Eviction never closes a connection some caller currently has checked out
(`_RolePool.retire()`): a pool being evicted closes only the connections
idle in its own queue immediately; any connection still in flight is
closed when its caller returns it, not before.

The cluster-wide ceiling is now:

`cache_max` bounds the number of live *pools*, and the manager keys a pool
by `(application_id, role)` -- so the role factor is already inside
`cache_max` and must not be multiplied in again:

```
live_pools        = min(applications × 2 roles, cache_max)
total_connections = live_pools × (pool_size + pool_max_overflow)
```

which, past `applications × 2 = cache_max`, stops growing with application
count at all:

```
ceiling_connections = cache_max × (pool_size + pool_max_overflow)
```

**Worked example**, at every knob's default (`cache_max = 32`, `pool_size +
pool_max_overflow = 4`):

```
32 pool-cache slots × 4 = 128 connections    (worst case, cache fully saturated)
```

This is exactly the ceiling the currently deployed implementation already
lives with (`pool_cache_max = 32`, `pool_size = 2` + `max_overflow = 2`),
so an operator sizing this deployment can reuse the existing deployment's
experience rather than starting from scratch.

That is still an operator-facing figure to size against `max_connections`
(PostgreSQL's own default is 100) -- 128 exceeds a default-configured
cluster on its own, before counting the control-plane role, any
interactive `psql` session, or `superuser_reserved_connections` (default
3). The difference from before is that this figure is now a *knob*, not a
function of how many applications happen to be onboarded: fifteen
applications and one hundred applications produce the identical worst-case
ceiling once `applications ≥ cache_max`, where previously each additional
application raised it by `2 × pool_size` with no limit at all.

Concretely, before onboarding a new application:

1. Query the cluster's configured ceiling: `SHOW max_connections;`.
2. Compute `min(already-provisioned applications + 1, R2DB_POOL_CACHE_MAX)
   × 2 × (R2DB_POOL_SIZE + R2DB_POOL_MAX_OVERFLOW)` and confirm it leaves
   headroom below that ceiling for the control role, interactive/admin
   sessions, and `superuser_reserved_connections`.
3. If the ceiling is close, either raise `max_connections` (a PostgreSQL
   restart is required) or lower `R2DB_POOL_CACHE_MAX` and/or
   `R2DB_POOL_SIZE`/`R2DB_POOL_MAX_OVERFLOW` -- all four are plain
   environment-variable settings consulted when `SharedPoolManager`'s
   default instance is constructed, not fixed by this migration set. A
   single cell can still request its own per-pool cap by passing
   `PostgresCell(..., pool_size=...)` explicitly, same as before.
4. If neither is acceptable, treat this as the "re-evaluate topology"
   signal architecture §8.3 already anticipates (connection pooling
   middleware such as pgbouncer, or revisiting the topology decision) --
   this runbook does not implement that; it only gives the operator the
   figure to decide with.

## 5. Order of operations

```
1. (cluster admin)   psql "$R2DBSVC_BOOTSTRAP_ADMIN_DSN" \
                       -v control_password="$R2DBSVC_CONTROL_PASSWORD" \
                       -f r2db-api/migrations/0001_bootstrap_control_plane.sql

2. (r2dbsvc_control) psql "$R2DBSVC_CONTROL_DSN" \
                       -f r2db-api/migrations/0002_provisioning_functions.sql

3. (r2dbsvc_control) -- once per application being onboarded:
                     psql "$R2DBSVC_CONTROL_DSN" \
                       -v app_slug='myapp' \
                       -v runtime_password="$(openssl rand -base64 32)" \
                       -v developer_password="$(openssl rand -base64 32)" \
                       -f r2db-api/migrations/0003_provision_application.sql

                     Record the two generated passwords in your secret
                     manager immediately -- nothing in this flow returns or
                     stores them in recoverable form.
```

Step 1 and step 2 are each safe to re-run: `0001` checks
`pg_roles`/`pg_database` before creating anything, and `0002` uses `CREATE
SCHEMA IF NOT EXISTS` / `CREATE OR REPLACE FUNCTION`. Step 3 is **not**
idempotent by design -- it raises if the slug is already provisioned, so a
re-run is a deliberate signal, not silently absorbed.

**Why step 3 is a multi-statement script, not a single function call (a
change from the previous, schema-per-application revision of this
runbook):** `CREATE DATABASE` cannot run inside a transaction block, which
every statement inside a PL/pgSQL function body implicitly is. Database-
per-application therefore cannot be provisioned by one opaque function
call the way schema-per-application could; `0003_provision_application.sql`
is a real, readable psql script for exactly this reason -- see its header
comment for the full mechanics (it creates the database, closes `PUBLIC`'s
default `CONNECT`, reconnects into the new database via `\c`, and sets up
`public`'s ownership/RLS-verification view there).

To remove an application (e.g. tearing down a test/staging application):

```
psql "$R2DBSVC_CONTROL_DSN" -v app_slug='myapp' \
  -f r2db-api/migrations/0004_deprovision_application.sql
```

This drops that application's entire database (every table in it, along
with the `public` schema and every grant inside it) and both its roles. It
does not touch any other application's database, role, or data -- verified
for exactly this property by `r2db-api/tests/test_postgres.py::
test_cross_database_connect_is_refused_at_the_database_level` and
`::test_cross_application_isolation_at_the_application_level`.

Deprovisioning a slug that was never provisioned now raises loudly
(a deliberate behavioural change from the previous single-function
`deprovision_application`, which silently no-op'd in that case -- see
`0002_provisioning_functions.sql`'s header for why).

If `0004` reports `database "..." is being accessed by other users`, this
is very likely a still-running autovacuum worker that visited the
database's system catalogs after `0003`'s own `CREATE ROLE`/`CREATE
DATABASE` -- `0004` deliberately does not attempt to terminate background
workers (doing so requires true superuser, which `r2dbsvc_control` is
not); simply re-run `0004` a few seconds later, once autovacuum has
finished on its own.

### A note on `psql`'s password variables

Steps that pass a password use `psql`'s own `-v name=value` /
`:'name'`-in-SQL substitution, not a `DO $$ ... $$` block -- `psql`
deliberately does not expand `:'var'` inside a dollar-quoted body, so a
password can only reach a plain, non-dollar-quoted statement this way (see
the comment at the top of `0001_bootstrap_control_plane.sql` for why that
matters). Whatever secret-manager tooling replaces `$(openssl rand ...)` in
your actual deploy script should preserve that same shape: the password
value flows through `-v`, never concatenated into SQL text your own script
builds. `0003`'s identifier substitutions (database/role names computed by
`0002`'s functions) use psql's matching `:"name"`-in-SQL identifier form,
for the same reason.

Passwords set via `CREATE ROLE ... PASSWORD ...` / `ALTER ROLE ...
PASSWORD ...` appear in plaintext in that statement's SQL text. If cluster
statement logging (`log_statement`) is enabled at `all` or `mod`, either
run steps 1 and 3 with logging temporarily reduced for that session, or
treat the log destination itself as credential-bearing and handle it under
the same access controls as a secret store. This is a general PostgreSQL
operational property of `CREATE ROLE ... PASSWORD`, not specific to this
migration set.

## 6. Environment variables the `r2db-api` process itself reads

None of the variables in §5 above (`R2DBSVC_BOOTSTRAP_ADMIN_DSN`,
`R2DBSVC_CONTROL_DSN`) are read by the `r2db-api` application process --
those are operator-only, per §2. The application process, once
`r2db_api.postgres.PostgresCell` is wired into `DataService` (a deliberately
separate follow-up step -- see `R2DB_SERVICE_LAYER_ARCHITECTURE.md` §3 step
2 and this work order's own scope note), needs exactly two DSNs *per
application it serves*: the `runtime` and `developer` connection strings
`PostgresCell.__init__`'s `runtime_dsn`/`developer_dsn` parameters expect,
each one naming that application's own database directly (not a shared
platform database with a schema qualifier, as an earlier revision of this
runbook described).

Suggested environment-variable naming for that follow-up wiring step (not
yet implemented by this change set -- `PostgresCell` currently takes these
as constructor arguments, supplied by whatever wires it into `DataService`):

```
R2DB_PG_RUNTIME_DSN_<APPLICATION_SLUG>=postgresql://r2dbsvc_app_<slug>_runtime:REPLACE_ME@example.invalid:5432/r2dbsvc_app_<slug>
R2DB_PG_DEVELOPER_DSN_<APPLICATION_SLUG>=postgresql://r2dbsvc_app_<slug>_developer:REPLACE_ME@example.invalid:5432/r2dbsvc_app_<slug>
```

Add the corresponding synthetic entries to `.env.example` (repository root)
when that wiring step lands, following the existing `DATABASE_URL` example
there -- name only, never a real value.

## 7. Network isolation (§5.3 C-3) -- verify, do not assume

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

## 8. Local development / test posture

`r2db-api/tests/test_postgres.py` runs steps 1-4 above end-to-end against a
local PostgreSQL server, entirely under a random-per-run throwaway prefix
(`r2dbtest<8 hex chars>_...`, never `r2dbsvc_`), and drops everything it
created -- including its own throwaway control-plane bootstrap and every
per-application database it provisioned -- in a fixture teardown that runs
even on failure. It takes its admin/bootstrap DSN from
`R2DB_TEST_ADMIN_DSN` (default: `host=/tmp port=5432 dbname=postgres`,
matching a typical local Homebrew/Postgres.app socket setup), so the same
test file can run against a differently-configured server (including,
eventually, the VPS's own PostgreSQL instance, once §5.3's connection
constraints allow reaching it for a controlled test run) by overriding that
one variable -- never by editing the test file.

If PostgreSQL is not reachable, these tests fail with a message naming the
DSN that failed; they do not skip (§5.3 C-5).
