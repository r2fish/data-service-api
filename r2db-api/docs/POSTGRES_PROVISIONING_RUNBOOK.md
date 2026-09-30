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

**Prerequisite: PostgreSQL 13 or later.** CCR-13
(`docs/design/R2DB_CCR13_STORAGE_V1.md` R-1/R-4/§6 申し送り 4) provisions
every entity table with a server-assigned `id bigint GENERATED ALWAYS AS
IDENTITY` address column and an invisible `_r2db_revision uuid NOT NULL
DEFAULT gen_random_uuid()` column; `gen_random_uuid()` is a PostgreSQL
built-in only from version 13 onward (earlier versions need the `pgcrypto`
extension's `gen_random_uuid()` instead, which this migration set does not
provision or depend on). Confirm the target cluster's version (`SELECT
version();`) before running `0001` on it.

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

**Current pool sizing and the per-worker connection budget are in §20.**
Every role pool and the platform pool of one data-plane worker are sized
from that worker's own thread limit (`R2DB_THREAD_LIMIT` + 2), and the
F-16/F-18 floors multiply by the declared `process_ceilings`; the figures
below that size a pool from the declared `concurrency` describe the
single-process sizing that §20 replaces.

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

**+ platform pool (additive, two pools, one role).** `0005_credential_
store.sql` (§9) adds two more consumers of connections that the
arithmetic above does not yet account for, both against the SAME
`r2dbsvc_api` role/DSN: `r2db_api.credential_store.PostgresCredential
Store`, which the running API process uses to read credential/application
state from `r2dbsvc_registry` on every request (design docs/design/
R2DB_CREDENTIAL_PERSISTENCE_AND_COMPOSITION_ROOT_V1.md, P2-D4), and
`r2db_api.credential_store.PostgresApplicationAuditSink` (Q4 phase D-1(b)),
the durable `application_audit` writer. Each is a single, separate pool --
neither is registered with `SharedPoolManager`, keyed by `(application_id,
role)`, or subject to the idle-eviction/LRU-cap sweep described above --
so neither multiplies with application count the way the per-application
ceiling does; they multiply by exactly 2 (one pool each) instead.

**Fact (Phase 10 WP-4e, supervisor ruling 2026-09-09):** `R2DB_PLATFORM_
POOL_SIZE`'s own default is no longer a fixed `4` -- `r2db_api.main.
build_app` now sizes BOTH platform-plane pools from the declared
`ResourceLimits.concurrency` ceiling (default `32`, `role_pool_size`, the
SAME function/value the per-application role pools below already use)
unless the env var is set explicitly, for the same reason as the WP-8a
fact below: once concurrent requests' authentication reads can genuinely
reach this pool at once (`run_in_threadpool` delegation), a pool sized
below the declared bound times out and fails closed with `AUTH_STATE_
UNAVAILABLE` (503) well under that bound. The full cluster-wide ceiling,
accounting for both platform-plane pools alongside the per-application
one, is therefore:

```
ceiling_connections = (cache_max × (pool_size + pool_max_overflow)) + (2 × platform_pool_size)
                     = (32 × 4) + (2 × 32)                           (worked example, pre-WP-8a per-application pool model)
                     = 192
```

(The pre-WP-4e worked example -- `(32 × 4) + 4 = 132`, one pool only,
fixed at `4` -- is superseded; kept out of this section so it is not
mistaken for the current default.) **This 192 figure is itself superseded
by the WP-8a fact immediately below** -- the per-application `cache_max ×
(pool_size + pool_max_overflow)` term it is built on is no longer how a
served application's own role pool is sized. It is kept here only as a
snapshot of the pre-WP-8a model, the same treatment the 132 figure above
already gets -- do not use it to size a real deployment; see "One
formula, not three" below for the figure to actually use.

**Fact (Phase 10 WP-8a review F-1, supervisor ruling 2026-09-08):** since
this fix, `r2db_api.main`'s composition root no longer sizes a served
application's role pool from `R2DB_POOL_SIZE + R2DB_POOL_MAX_OVERFLOW`
(the `pool_size = 4` the superseded worked example above uses) -- it sizes
it from the declared `ResourceLimits.concurrency` ceiling instead (default
`32`, `r2db_api.main._role_pool_size`), so that `DataService._slot`'s own
429 LIMIT_EXCEEDED, not a pool-exhaustion 503, is what a client actually
hits at the declared bound. The real per-application connection demand is
therefore declared `concurrency` × role count (runtime + developer) ×
applications served by this process, plus `2 × platform_pool_size` (WP-4e
above) for the two platform-plane pools -- see "One formula, not three"
below for how this combines with `superuser_reserved_connections` into
the actual `max_connections` requirement (deployment-wide sizing across
both role AND platform pools, including any bound on applications served
per process, is R-31's own, broader, Phase 11 concern; this note records
the real per-role/per-pool figures only).

**Fact (Phase 10 WP-4f, supervisor ruling 2026-09-09):** the arithmetic
above assumed every role's own `CONNECTION LIMIT` (as shipped by
`0002`/`0005`/`0006`) was already high enough to admit the real pool it
backs -- WP-4e's own conformance investigation found this false for
`r2dbsvc_controlplane` (4 platform-plane stores x a fixed `pool_size` 4 =
16, against a shipped `CONNECTION LIMIT` of only 10 -- already exceeded by
a SINGLE control-plane process, no test harness involved), and the
identical shape recurs for `r2dbsvc_api` (2 stores x declared `concurrency`
= 64, against 10) and every served application's own runtime/developer
roles (1 store x declared `concurrency` = 32, against 20/10). Migration
`0013_role_connection_limits.sql` raises exactly these four role classes
to (real pool composition) + 4 (a fixed operator-headroom margin):

| Role | Pool composition | Old `CONNECTION LIMIT` | New `CONNECTION LIMIT` |
| --- | --- | --- | --- |
| `r2dbsvc_api` | `credentials` + `durable_audit`, each pool-sized to declared `concurrency` (default 32) = 2 x 32 = 64 | 10 | 68 |
| `r2dbsvc_controlplane` | 4 platform-plane stores x fixed `pool_size` 4 (WP-4e's own investigated-and-reverted default, `control_main.build_control_app`) = 16 | 10 | 20 |
| `<slug>_runtime` | 1 store, `PostgresCell`'s own pool sized to declared `concurrency` (default 32) | 20 | 36 |
| `<slug>_developer` | 1 store, same sizing as `<slug>_runtime` | 10 | 36 |
| `r2dbsvc_control` | short-lived, one-shot CLI/provisioning connections only -- no persistent pool | 5 | unchanged (already >= its own real pool composition) |
| `r2dbsvc_auditreader` | 1 store, fixed `pool_size` 4 (`PostgresAuditQueryStore`'s own default) | 5 | unchanged (already >= its own real pool composition) |

**One formula, not three (L-2, WP-4 integration review 2026-09-10):** the
CONNECTION LIMIT table above records each role's own real pool-composition
floor plus headroom -- a PER-ROLE ceiling PostgreSQL enforces
independently, capping how many connections THAT role may hold open at
once. It is not an additional term to sum into `max_connections`, and
PostgreSQL itself never requires `max_connections` to accommodate every
role at its own `CONNECTION LIMIT` simultaneously -- roles may be
deliberately over-subscribed relative to `max_connections` when an
operator knows they never all peak together. The one PostgreSQL fact that
actually governs `max_connections` is:

```
max_connections >= real simultaneous connections this deployment can produce at once
                    + superuser_reserved_connections (default 3)
```

"real simultaneous connections this deployment can produce at once" is
the WP-8a figure above -- declared `concurrency` × role count (runtime +
developer) × applications served by this process, plus `2 ×
platform_pool_size` for the two platform-plane pools -- plus however many
interactive/diagnostic `psql` sessions an operator expects to hold open
at once. Summing the CONNECTION LIMIT table instead is a conservative,
easy-to-compute stand-in for that real figure (never smaller than it, by
construction of the table's own +4 headroom margin) for an operator who
has not derived it -- not a PostgreSQL requirement in its own right.
Re-check the real figure against `SHOW max_connections;` before applying
`0013` to a cluster already close to its own configured ceiling. Applying
it by hand (an already-running cluster this script has not touched, or a
retrofit after the fact), via `ops apply-platform-migration` (R-90 WP-1,
`--lock-timeout` required):

```
python -m r2db_api.ops apply-platform-migration 0013_role_connection_limits.sql --lock-timeout <value>
```

`python -m r2db_api.ops verify-declarations` now also checks the
CONNECTION LIMIT table above, independently of `max_connections` (new
check `F-16`): each role's own `pg_roles.rolconnlimit` is `-1` or at least
its own real pool-composition floor -- the bare pool-composition figure
in the table's own "Pool composition" column, WITHOUT the `+4` headroom
margin `0013` bakes in (e.g. 64 for `r2dbsvc_api`, not 68) -- a strictly
WEAKER, never stronger, bound than what this migration ships (L-1: the
two are not the identical formula, though `0013`'s own +4 margin always
clears F-16's floor with room to spare). Run unconditionally alongside
every other check that command already runs, so a FUTURE deployment that
raises `ResourceLimits.concurrency` without a follow-up migration like
`0013` is caught at verify time instead of silently reopening this exact
failure mode.

`python -m r2db_api.ops verify-declarations` also checks a cluster-wide necessary condition (new check `F-18`): the connection count the declared `process_ceilings` guarantees this deployment opens -- one platform pool per data process, one runtime/developer pair per data process once at least one application is registered, one control-plane pool per control process -- plus `superuser_reserved_connections` plus `reserved_connections`, must stay at or under `max_connections`; both `r2db_api.main.build_app` and `r2db_api.control_main.build_control_app` fail the same unscoped check at their own startup, `verify-declarations` itself exiting 17. `part1a_check_max_connections.sh` below runs BEFORE deployment (right after `0002`, before any application is provisioned or `process_ceilings` is declared); F-18 runs AFTER deployment, against the `process_ceilings` a deployment has actually declared -- the two checks are not redundant, and "One formula, not three" above (the CONNECTION LIMIT sum is a conservative stand-in, never itself the requirement) still holds unchanged. F-18 is a necessary condition only, never counting an interactive/diagnostic `psql` session nor its own connection, and it reports the upper bound (every REGISTERED application x every data process) for information only, never as the judged quantity. A rollout that runs two revisions of a plane side by side is covered only if `process_ceilings` declares that overlap's own process count -- that declared count is exactly what F-18's lower bound multiplies. Evidence: `r2db-api/tests/test_ops_verify_declarations.py::test_verify_declarations_f18_fails_when_the_declared_lower_bound_exceeds_max_connections`, `::test_verify_declarations_f18_passes_when_the_declared_lower_bound_fits`, `r2db-api/tests/test_credential_persistence.py::test_build_app_fails_fast_when_the_declared_process_ceilings_lower_bound_exceeds_max_connections`, `r2db-api/tests/test_surfaces_env.py::test_build_control_app_fails_fast_when_the_declared_process_ceilings_lower_bound_exceeds_max_connections`.

`verify-declarations` also checks the collation every registered, provisioned application's own database was provisioned with (new check `F-19`, `verify-declarations` itself exiting 18): `pg_database.datcollate` must be `'C'` (codepoint-order string comparison, matching this peer's in-memory backend -- neither a column-level `COLLATE` clause nor an index-level one can reach the strings inside a jsonb value), `datcollate` alone is not enough -- `datctype` must stay this cluster's own UTF-8 locale (never `'C'`), and, on a server that can report it (`pg_database.datlocprovider`, PostgreSQL 15 and later), the locale provider must be libc, never ICU (an ICU database's own `LC_COLLATE` string does not govern its ordering, so datcollate `'C'` there would be a false green). A cluster that was itself `initdb`'d with a `C`/`POSIX` cluster-wide locale fails F-19 too, and correctly so: this cluster's own `template0` would then hand every new application database `datctype = 'C'`, breaking non-ASCII case folding and pattern matching -- initialize the cluster (`initdb`, out of `verify-declarations`'s own scope) with a real UTF-8 locale, the same one `tools/testpg/dsa_testpg.py` uses for every throwaway test cluster. The only remedy for an application database that fails F-19 for the `collate`/`ctype`/`missing` reasons is re-provisioning it (`0003_provision_application.sql`); an existing database's own collation cannot be changed in place. A database that fails F-19 for the `provider` reason (ICU) cannot be fixed by re-running the current `0003` against a cluster whose own `template0` was itself `initdb`'d with an ICU provider -- `CREATE DATABASE` inherits the template's provider -- re-provision it against a cluster `initdb`'d with the libc locale provider instead. A database missing from `pg_database` (the `missing` reason) may also be one `0004_deprovision_application.sql` left mid-way (dropped, but its own `applications` row not yet cleared) -- completing that deprovision, rather than re-provisioning, is the correct remedy there. Evidence: `r2db-api/tests/test_ops_verify_declarations.py::test_verify_declarations_f19_fails_when_an_application_database_collation_is_not_c`, `::test_verify_declarations_f19_passes_after_provisioning_with_0003`, `r2db-api/tests/test_postgres.py::test_application_database_collation_is_c`, `::test_application_database_collation_keeps_the_cluster_ctype` (these 2 provisioning pins, together with 4 more `test_postgres.py` string-collation parity tests -- `test_parity_string_collation_order_by_string_column`, `::test_parity_string_collation_order_by_untyped_column`, `::test_parity_string_collation_keyset_cursor_walk`, `::test_parity_string_collation_where_gt_lt` -- and the 5 pre-existing `test_postgres.py` parity tests (the 4 `test_parity_order_by_jsonb_*` tests and `test_parity_order_by_null_placement_and_cross_type`), 11 passed under `-k "collation or parity_order"`).

**`part1a_check_max_connections.sh` (R-66 WP-1, design D-2):**
`part1_provision_host_and_db.sh` now runs this check itself, right after
`0002` and before `0005` -- it connects over `R2DBSVC_CONTROL_DSN`, reads
`SHOW max_connections;` and `SHOW superuser_reserved_connections;`, and
refuses (before `0005` or any later migration runs) unless `max_
connections` minus `superuser_reserved_connections` is at least
`98 + 72 × (N + 1)`, N being the number of already-provisioned
applications in `r2dbsvc_registry.applications` (0 if that table does not
exist yet). `98`/`72` are this section's own CONNECTION LIMIT table
literals (98 = 68 + 20 + 5 + 5, the platform-plane roles; 72 = 36 + 36,
one application's own runtime + developer roles) -- the SAME
"conservative, easy-to-compute stand-in" the "One formula, not three"
paragraph above describes, never the real PostgreSQL requirement itself.
An operator who has derived the real figure from that paragraph's own
formula sets `R2DBSVC_EXPECTED_PEAK_CONNECTIONS` (a positive integer) to
use it instead of this script's own conservative default; any other
value (unset is not "any other value" -- it is the documented default)
is refused with the same message shape.

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

**The platform migrations that come after `0002`** are each described in
their own section, and are applied in the order `part1_provision_host_
and_db.sh` actually runs them, not ascending file-number order (`0013`,
`0014`, `0015` and `0016` all run before `0008`/`0012` despite their own HIGHER file
numbers -- design D-1, R-66 WP-1): `0005` (§9, credential store), `0006`
(§11, control-plane storage), `0007` (§15, audit sink), **`0013` (§4, role `CONNECTION
LIMIT`s, Phase 10 WP-4f -- additive only, safe to apply by hand at any
point after `0002`/`0005`/`0006`/`0007` exist on an already-running
cluster; run by this script since R-66 WP-1 -- at the
default thread limit (F-16 floors, §20), both processes now REFUSE TO START
until it is applied, F-16 `check_role_connection_limits`;
`part1a_check_max_connections.sh`, run right after `0002`, verifies this
migration's own precondition -- `max_connections` re-checked against this
section's own worked example -- before this script ever applies it)**,
`0014` (§19, auditreader `statement_timeout`, R-56 -- additive only, no
process REFUSES TO START without it; `ops verify-declarations` reports
`FAIL F-17` until it is applied and the control process restarted),
`0015` (§20, the credential-keyed `requests_per_minute` row every
data-plane worker shares -- on a platform database without its rate
function, the application-plane process and its preflight refuse to
start, naming the migration),
`0016` (§21, the refusal-window counter every data-plane worker adds to --
on a platform database without its function, or with one not in the state
the file leaves it in, the application-plane process and its preflight
refuse to start, naming the migration),
**`0008` (§16, platform declarations + writer-role timeouts, Q4 phase --
both processes now REFUSE TO START until it is applied)**, and `0012`
(process ceilings, Phase 10 WP-6a -- also required before either process
starts, F-15). **§17 covers the
third class of migration** -- per-application upgrade scripts, of which
`0009` is this peer's first: those are applied per application database, by
`python -m r2db_api.ops upgrade-applications --lock-timeout <value>`, never by hand in this order.
An application provisioned by the current `0003` (step 3 above) already
carries the ledger `0009` retrofits, so §17 is a catch-up step for databases
provisioned before that revision, exactly like the CCR-13 DOMAIN note below.

**CCR-13 note (procedural only -- no application database has actually been
provisioned against this cluster yet, so this has not been exercised):**
`0003_provision_application.sql` now also creates two DOMAINs,
`public._r2db_json_object`/`public._r2db_json_array`
(`docs/design/R2DB_CCR13_STORAGE_V1.md` R-7 addendum, "object/array の
DOMAIN 型統一"), inside the application database it provisions. Because
step 3 is not re-runnable against an already-provisioned slug, an
application database provisioned with a pre-CCR-13 `0003` before this
DOMAIN addition landed will be missing both -- `field_type: "object"`/
`"array"` on that application will fail until an operator applies just the
two `CREATE DOMAIN` statements (see `0003`'s own body for the exact SQL) by
hand against that one application's database, as the `developer` role, the
same way `0003` itself does it. This is a one-time, per-already-provisioned-
application catch-up step, not a routine part of onboarding a new
application (which always gets both from a single, current `0003` run).

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

To remove an application (e.g. tearing down a test/staging application), use
`ops deprovision` (R-90 WP-2) rather than `psql -f` directly -- it enforces
`--lock-timeout` the same way `ops apply-platform-migration` (§16/§18/§19)
does, and it is gated by a `--confirm <phrase>` declare-and-echo step (this
runbook's own destructive-confirmation convention, §12/§13): invoke it once
without `--confirm` and it prints the required phrase as JSON on stderr and
exits 2, touching nothing; invoke it again with that exact phrase to
actually run `0004_deprovision_application.sql`. The phrase's own
`@registered=` digest is this application's own
`r2dbsvc_registry.applications.provisioned_at` -- deprovisioning this slug
and then re-provisioning it changes `provisioned_at`, which changes the
required phrase too, so a stale echoed phrase from an earlier provisioning
is refused:

```
python -m r2db_api.ops deprovision myapp --confirm <phrase> --lock-timeout <value>
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
`0002_provisioning_functions.sql`'s header for why); `ops deprovision`
itself also refuses an unregistered or never-provisioned slug before
computing a confirmation phrase at all (no `provisioned_at` to fingerprint
against).

**If `0005_credential_store.sql` has been applied on this platform database,
clear this application's credentials first.** `0004` refuses to proceed
(before touching anything -- no live-connection pre-check, no temporary
self-grant, no `ALLOW_CONNECTIONS` change, no `pg_terminate_backend`, no
`DROP DATABASE`, no `DROP ROLE` -- design `docs/design/
DEPROVISION_FORCED_DROP_V0_1.md` v1.0 D-2R adds the first three stages,
all of which still run strictly after this guard, never before it) while
any `credentials` row still references this slug
(`application_slug` is `ON DELETE RESTRICT`, by design -- §9). `ops
deprovision` relays the script's own failure text (with any connection
value redacted) and exits non-zero; the error names the count and the
remedy:

```
python -m r2db_api.ops deprovision myapp --confirm <phrase> --lock-timeout <value>
error: deprovision script failed:

ERROR:  application myapp still has 2 credential row(s) referencing it -- revoke it first
(python -m r2db_api.ops revoke-credential <credential_id>), then delete the row
(python -m r2db_api.ops delete-credential <credential_id> --confirm ...; run it
once without --confirm first to see the exact value to pass) before deprovisioning
```

For every credential row still referencing the slug: `python -m r2db_api.ops
revoke-credential <credential_id>` (stop it from authenticating), then
`python -m r2db_api.ops delete-credential <credential_id>` (actually clear
the row -- unlike revoke, this is permanent and is the only thing that
satisfies `0005_credential_store.sql`'s own `credentials.application_slug`
foreign key, `ON DELETE RESTRICT` -- the constraint `0004`'s deprovisioning
script detects and refuses against, via `0005`'s own `assert_no_credentials_
for_deprovision` guard function, shown above). **Q-1 WP-4: `delete-
credential` is genuinely destructive and is now gated (design
docs/design/DESTRUCTIVE_CONFIRMATION_V1.md R-4) the same way `reset` is
(§12 above)** -- an invocation with no `--confirm`, or the wrong one, is
refused: **exit code 2 *and* the declaration printed as one line of JSON on
stderr** (exit code 2 alone is not this refusal's signature -- `argparse`'s
own usage errors and this CLI's other `_die`-based failures also exit 2;
only the JSON-on-stderr shape identifies an R-4 confirmation refusal
specifically), and nothing is deleted:

```
python -m r2db_api.ops delete-credential <credential_id>
# refused: exit 2 + the declaration as JSON on stderr; the row above is untouched
python -m r2db_api.ops delete-credential <credential_id> \
  --confirm "DELETE_CREDENTIAL <credential_id>"
# succeeds -- the row is now gone
```

`python -m r2db_api.ops list-credentials` finds
every row for a given application. Once none remain, re-run `0004`. A
platform database that has never had `0005` applied at all skips this check
entirely (`0004` detects the guard function's absence and behaves exactly
as it did before `0005` existed) -- see `0004_deprovision_application.sql`'s
own header for the `to_regprocedure`-gated mechanics.

If `0004` reports `database "..." is being accessed by other users`, this
is very likely a still-running autovacuum worker that visited the
database's system catalogs after `0003`'s own `CREATE ROLE`/`CREATE
DATABASE` -- `0004` deliberately does not attempt to terminate background
workers (doing so requires true superuser, which `r2dbsvc_control` is
not); simply re-run `0004` a few seconds later, once autovacuum has
finished on its own.

**Correction note (2026-09-19, design `docs/design/
DEPROVISION_FORCED_DROP_V0_1.md` v1.0; the paragraph above is not
rewritten, only annotated)**: this error can have two different causes
here. (i) the autovacuum worker did not finish within PostgreSQL's own
grace period -- M-12 is a single measurement of a plain `DROP DATABASE`
succeeding with one worker present, not evidence this never happens under
load. (ii) a connection under a role other than this application's own,
that raced in after the pre-check passed and before `DROP DATABASE` ran.
Either way the database is left with `ALLOW_CONNECTIONS false` -- the
application stays down -- so "wait a few seconds and retry" is not free.
For (ii), read `pg_stat_activity` by `usename` as an admin to find the
connection's owner, have them close it, then re-run `0004`.

At this point the database itself is left with
`ALLOW_CONNECTIONS false` and the temporary self-grant of this
application's roles still standing (design `docs/design/
DEPROVISION_FORCED_DROP_V0_1.md` v1.0 §4.1); re-running `0004` clears both
and completes the deprovision. To abandon instead of retrying, see the
equivalent state in §14's branch (B) recovery below for the two commands
that undo it.

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
those are operator-only, per §2.

**See §10 for the actual, implemented contract.** This section previously
described the application process's own environment variables as
"suggested naming, not yet implemented" -- that follow-up wiring step
(`r2db_api.main`, the composition root uvicorn/systemd starts as
`r2db_api.main:app`) now exists; §10 is the current, accurate reference
for it, not this section.

`R2DB_MIGRATIONS_DIR` is likewise listed in §10's table below (supervisor
ruling 2026-09-06 M-2(a)) even though, like `R2DBSVC_BOOTSTRAP_ADMIN_DSN`/
`R2DBSVC_CONTROL_DSN` above, it is not read by `r2db_api.main` itself --
it is read only by `python -m r2db_api.ops` (the CLI), detailed in §17.

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

## 9. Credential store and the `r2dbsvc_api` role (`0005_credential_store.sql`)

Companion to design docs/design/
R2DB_CREDENTIAL_PERSISTENCE_AND_COMPOSITION_ROOT_V1.md (decisions
P2-D1/P2-D2/P2-D3/P2-D4). Before this migration, the only place a
credential's verifier or an application's enabled/disabled state existed
was `r2db_api.auth.CredentialStore`'s in-memory Python dict -- gone on
every process restart, and never shared between processes. This is the
migration that fixes that.

**Run once, after 0002** (order relative to 0003/0004 does not matter --
this is control-plane bootstrap, independent of any one application),
connected as `r2dbsvc_control`:

```
psql "$R2DBSVC_CONTROL_DSN" -v api_password="$R2DBSVC_API_PASSWORD" \
  -f r2db-api/migrations/0005_credential_store.sql
```

`R2DBSVC_API_PASSWORD` is a new environment-variable *name*, generated the
same way `R2DBSVC_CONTROL_PASSWORD` is (§5's note on `psql`'s password
variables applies identically here). Like `0001`/`0002`, this file is safe
to re-run: `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` / `CREATE TABLE IF
NOT EXISTS` are natively idempotent, the role-creation statement uses the
same conditional-`\gexec` idiom `0001` already established, and `GRANT` is
naturally idempotent.

**What it adds:**

| Object | Purpose |
|---|---|
| `r2dbsvc_registry.applications.enabled` (new column, default `true`) | Persists what was previously only `DataService`'s in-memory `_disabled_apps` set -- without this, a CLI-disabled application silently re-enables itself on the next process restart (fail-open). Not a new lifecycle state; same meaning as the in-memory set it replaces. |
| `r2dbsvc_registry.credentials` (new table) | Mirrors `r2db_api.auth.CredentialRecord`'s shape (credential_id / application / role / verifier / enabled / revoked) field-for-field, plus `created_at`/`updated_at`. Only the verifier (`HMAC-SHA256(pepper, secret)`) is ever stored -- the secret itself is shown once, at issue/rotate time, by `python -m r2db_api.ops`, and is never written anywhere. `role` stays restricted to `runtime`/`developer`; a control-credential role is intentionally not a value this column accepts yet (added, additively, only once CCR-14 is resolved -- see the design doc's §0). `application_slug` is `ON DELETE RESTRICT`, not `CASCADE`, per the CCR-14 lessons-learned record: a previous implementation's `CASCADE` silently severed the audit trail's link from a credential back to its application. |
| `r2dbsvc_api` (new login role) | `LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT CONNECTION LIMIT 10`. Granted `CONNECT` on `r2dbsvc_platform`, `USAGE` on `r2dbsvc_registry`, and `SELECT` (only) on `applications`/`credentials`. This is the role the *running API process* authenticates as (`R2DB_PLATFORM_DSN`, §6/§10) -- strictly read-only, and a completely different role from `r2dbsvc_control`, which keeps every write privilege and remains operator/CLI-only (§2, §5.3 C-2). A compromise of the running API process cannot alter a credential's `enabled`/`revoked` state or an application's `enabled` flag through this role's grants -- it can only read the state `python -m r2db_api.ops` (connected as `r2dbsvc_control`) already wrote. |
| `r2dbsvc_registry.assert_no_credentials_for_deprovision` (new function) | Called by `0004_deprovision_application.sql`, immediately after `begin_deprovision_application` and before anything destructive runs: refuses to deprovision an application while any credential row still references it (see §5's deprovisioning note). Not called at all -- gracefully -- on a platform database that has never had `0005` applied. |

**CCR-14 is resolved** (`spec/CCR_DISPOSITION.md`); the canonical, normal-
operation, in-band way to issue/rotate/revoke/disable/enable an application
credential, or disable/enable an application, is now the control-plane HTTP
surface, `/control/v1` (`docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md`, §11
below) -- deployed as its own process, `r2db_api.control_main:app` (see
`r2db-api/deploy/DEPLOYMENT_RUNBOOK.md` §7). `python -m r2db_api.ops`
remains available for the same operations as an operator **break-glass**
path (R-10) -- always usable even when `/control/v1` itself is unreachable,
and the *only* path for the operations `/control/v1` deliberately does not
expose at all: the bootstrap/reset control-credential ritual (§12 below;
there is no HTTP endpoint anywhere that can create a `role=control`
credential -- "案B") and `delete-credential` (permanent row removal, kept
CLI-only by design). Run `python -m r2db_api.ops --help` for the full
subcommand list; application-credential subcommands require
`R2DB_CONTROL_DSN` (the `r2dbsvc_control` DSN, never the read-only
`r2dbsvc_api` one) and `R2DB_CREDENTIAL_PEPPER` (the same pepper value the
running API process is configured with -- a credential issued with the
wrong pepper never authenticates); control-credential subcommands
(`bootstrap`/`reset`/`enable-control-credential`/`rotate-control-credential`)
require `R2DB_CONTROL_CREDENTIAL_PEPPER` instead (§11/§12 below).
`delete-credential` is the one genuinely destructive, irreversible
subcommand here (every other one is a soft state change on a row that
stays on record) -- it exists specifically to satisfy the deprovisioning
guard above, which a revoke/disable alone cannot: the guard is a real
foreign key, and only removing the row clears it. It is itself guarded: it
refuses a credential that is not already revoked, so the lifecycle is
always revoke first, then delete -- a live credential can never vanish
without a revocation having been recorded.

**Every *state-changing* subcommand of this CLI now writes a canonical,
durable event to `r2dbsvc_registry.control_audit` in the same transaction
as the state change itself** (CCR-14 R-6, §11 below) -- the durable-audit
gap this section used to note here is closed; a `control_audit` write
failure aborts the state change too (fail-closed by construction).
Read-only subcommands (`list-credentials`, `list-apps`, `audit-report`, §12
below) write nothing to `control_audit` -- a read has nothing to audit, the
same rule the state-changing subcommands' own audit obligation does not
apply to. `/control/v1`'s own denials (authentication failure, authorization
refusal, capability rejection) are durably recorded the same way,
independent of this CLI.

## 10. Environment variables the `r2db-api` process itself reads (as of `r2db_api.main`)

§6 above described this as a "suggested naming, not yet implemented"
follow-up step; it is now implemented (`r2db_api/main.py`, design P2-D5).
`r2db_api.main:app` is the module-level ASGI application uvicorn/systemd
start (`ExecStart=... uvicorn r2db_api.main:app ...`, see `deploy/systemd/
r2dbsvc-api.service` and `deploy/env/api.env.example`, P3-D8). It reads, at
import time -- a missing/invalid value below is an import-time failure,
not a partial startup:

| Variable | Required | Meaning |
|---|---|---|
| `R2DB_CREDENTIAL_PEPPER` | yes | Verifier HMAC pepper -- same value `python -m r2db_api.ops` must be run with. |
| `R2DB_PLATFORM_DSN` | yes | The `r2dbsvc_api` role's DSN against `r2dbsvc_platform` (§9's read-only role). |
| `R2DB_SERVE_APPS` | yes | Comma-separated application slugs this process serves. Each one is checked against `r2dbsvc_registry.applications` at startup: unregistered or `enabled = false` both fail startup loudly. |
| `R2DB_APP_<SLUG_UPPER>_RUNTIME_DSN` | yes, per served slug | That application's `runtime` role DSN (`PostgresCell`'s `runtime_dsn`). |
| `R2DB_APP_<SLUG_UPPER>_DEVELOPER_DSN` | yes, per served slug | That application's `developer` role DSN (`PostgresCell`'s `developer_dsn`). |
| `R2DB_POOL_*` | no | Existing per-application pool tuning -- see `SharedPoolManager` and §4. |
| `R2DB_PLATFORM_POOL_SIZE` | no, default derived from `ResourceLimits.concurrency` (32, WP-4e -- no longer a fixed `4`) | Caps BOTH platform-plane pools (credential store + durable audit sink) -- see §4's "+ platform pool" note. |
| `R2DB_PLATFORM_SCHEMA` | no, default `r2dbsvc_registry` | **TEST-ONLY -- never set this in a real deployment.** Overrides the registry schema name `PostgresCredentialStore`/`r2db_api.main` look `applications`/`credentials` up under. Its only reason to exist is so this repository's own test suite and the conformance adapter -- which run the real migration files with `r2dbsvc` textually rewritten to a random throwaway prefix, to avoid colliding with anything else in a shared local cluster -- can point a built app at their own rewritten schema. A real deployment always uses the literal schema `0005_credential_store.sql` creates and must leave this unset. |
| `R2DB_CONTROL_PLANE_STATUS` | no, default `unavailable` | CCR-14 (R-9, `docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md`). Allowed values are exactly `enabled`/`unavailable`; anything else is a startup failure, never a silent fallback. This is a **deployer declaration**, not a detected fact -- this process cannot verify on its own whether a `/control/v1` control-plane process (`r2db_api.control_main`) is actually reachable. Set it to `enabled` only once that process is genuinely deployed and reachable (`r2db-api/deploy/DEPLOYMENT_RUNBOOK.md` §7); the authoritative check for "is a control plane actually reachable" in a separated deployment is always the control plane's own `GET /control/v1/capabilities`, never this declaration. |
| ~~`R2DB_DATA_BASE_URL`~~ | **REMOVED (Q4 phase WP-1, design `docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md` D-2)** | **No longer read. This process now REFUSES TO START whenever this variable is defined at all, whatever its value (an empty string included)** -- fail-fast F-2, which names the `ops` command below. `surfaces.data.base_url` (contract 1.6.0, unconditional obligation) is now the `surfaces` row of `r2dbsvc_registry.platform_declarations` (migration `0008`), a SINGLE row **both** this process and `r2db_api.control_main` read at startup. Declare it with `python -m r2db_api.ops declare-surfaces --data-base-url <URL> [--control-base-url <URL>]` and restart both processes -- §16 below. The same shape rules still apply, now checked on the declared value (absolute URL, ends `/v1`, no trailing slash) and on the write path as well as the read path. **Still a deployer-stated fact, never derived from a request's Host header.** |
| ~~`R2DB_CONTROL_BASE_URL`~~ | **REMOVED (Q4 phase WP-1, design D-2)** | **No longer read; defining it at all fails startup (F-2), exactly as above.** `surfaces.control.base_url` is the `control` half of that same single declared row, shared with `r2db_api.control_main` -- which is why re-declaring without `--control-base-url` (or with the explicit `--no-control`) also removes the control declaration for the control-plane process, whose own startup then fails with F-3c. The suffix requirement is unchanged (`/control/v1`, no trailing slash). **The one thing this phase did NOT close (design §3.11 point 7, ledger LQ4-16): that both processes read the SAME platform database is not verified by either of them** -- a control process pointed at a stale platform DSN reproduces the old L6-5a drift. Diffing `surfaces` between `.../v1/capabilities` and `.../control/v1/capabilities` after any change therefore REMAINS a required post-deploy check (`docs/work-orders/DEPLOY_Q4_20260905.md` §4-1). |
| `R2DB_MIGRATIONS_DIR` | no, default resolves this package's own packaged `migrations/` directory (Phase 7 WP-3, ledger LQ4-24; supervisor ruling 2026-09-06 M-2(a)) | **Not read by `r2db_api.main` -- read only by `python -m r2db_api.ops` (the CLI)**, listed here for the same reason `R2DB_PLATFORM_SCHEMA` above is: an operational escape hatch worth documenting alongside the rest of this contract even though it is scoped to one consumer. Overrides the directory `ops upgrade-applications`/`upgrade-status --script` resolve per-application upgrade scripts under. Required whenever `r2db-api` is installed non-editable into a venv (`pip install -c constraints.txt <install root>`, `constraints.txt` at the repository root of that checkout/`git archive` extraction -- R-19; `ops`'s own default resolution assumes a source-checkout layout and does not find the migrations directory once this package is `pip install`ed) -- `deploy/scripts/part1_provision_host_and_db.sh` sets it explicitly around its own `ops upgrade-applications` call for exactly this reason. See §17 for the full command shapes. |

The corresponding synthetic entries already exist in `deploy/env/api.env.example`
(P3-D8), following the existing repository-root `.env.example` pattern --
name only, never a real value.

**The control-plane HTTP process (`r2db_api.control_main:app`) is a
separate process with its own, separate environment-variable contract** --
`R2DB_CONTROLPLANE_DSN`, `R2DB_CONTROL_CREDENTIAL_PEPPER`,
`R2DB_CREDENTIAL_PEPPER`, the optional `R2DB_CONTROL_LIMIT_*` resource-bound
overrides, and the same `R2DB_PLATFORM_SCHEMA`/`R2DB_PLATFORM_POOL_SIZE`
knobs as above. It is never read by `r2db_api.main` (the table above) and
this process never reads `R2DB_PLATFORM_DSN`/`R2DB_SERVE_APPS` in turn --
the two processes' environments do not overlap in meaning even where a
variable name looks similar. See `r2db-api/deploy/DEPLOYMENT_RUNBOOK.md` §7
for the authoritative table and deployment steps, and `control_main.py`'s
own module docstring for the exact contract this reference is kept in sync
with.

## 11. Control-plane HTTP surface storage (`0006_control_plane_http.sql`)

Companion to `docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md` (R-2/R-3/R-4/R-6).
**Run once, after `0002` and `0005`** (`0006` revises two of `0002`'s own
functions, and does not depend on `0005` beyond running after it by
convention), connected as `r2dbsvc_control`:

```
psql "$R2DBSVC_CONTROL_DSN" -v controlplane_password="$R2DBSVC_CONTROLPLANE_PASSWORD" \
  -f r2db-api/migrations/0006_control_plane_http.sql
```

`R2DBSVC_CONTROLPLANE_PASSWORD` is a new environment-variable *name*,
generated the same way `R2DBSVC_CONTROL_PASSWORD`/`R2DBSVC_API_PASSWORD` are
(§5's note on `psql`'s password variables applies identically here). Like
`0001`/`0002`/`0005`, this file is safe to re-run: every `ALTER TABLE ...
DROP NOT NULL`/`DROP DEFAULT`, `CREATE TABLE IF NOT EXISTS`, and `CREATE OR
REPLACE FUNCTION` in it is natively idempotent, and its one `ADD CONSTRAINT`
is guarded by a `pg_constraint` catalog check (see the migration's own
header for the full idempotency argument, including why `CREATE OR REPLACE
FUNCTION` does not reset a function's existing ACL).

**Not yet exercised against the real VPS (procedural note only, matching
§5's CCR-13 note's own caveat)**: no application has actually been
provisioned against that cluster yet, so the two-state registry change
below has not been exercised there either -- this section describes what
`0006` does and why, verified against a local PostgreSQL 16 cluster
(`r2db-api/tests/test_control_plane_store.py`), not production evidence.

**What it adds:**

| Object | Purpose |
|---|---|
| `applications` two-state registry (no new column) | `database_name`/`runtime_role`/`developer_role`/`provisioned_at` all become nullable, guarded by a new CHECK: either all four are NULL ("registered, not yet provisioned") or all four are NOT NULL ("provisioned") -- a half-filled row can never exist. "Provisioned" is still judged solely by `database_name IS NOT NULL`. |
| `begin_provision_application` (revised) | Writes **nothing** to `applications` any more (round-2 review ruling; see the migration's own header for the crash-safety argument) -- it only enforces the already-provisioned guard and runs the two `CREATE ROLE` statements. `finish_provision_application` is now the only place `applications` is ever written during provisioning. |
| `finish_provision_application` (revised) | An explicit two-branch `UPDATE ... WHERE database_name IS NULL` then, if no row matched, `INSERT` -- handles both the operator-first flow (no pre-existing row) and the registered-row flow (a row already exists from `POST /control/v1/applications`) without an `ON CONFLICT` that could silently mask a real race (see the migration's own header, case (iii)). |
| `begin_deprovision_application` (revised) | Adds `AND database_name IS NOT NULL` to its own lookup -- a registered-only row is never mistaken for a deprovisioning target. |
| `r2dbsvc_registry.control_credentials` (new table) | `credential_id` (`ctl_` + 16 hex) / `verifier` (UNIQUE) / `enabled` / `revoked` / `must_rotate` (default `true`) / `created_at` / `updated_at`. No `application_slug` column at all -- structurally incapable of holding, or being confused with, an application credential (`credentials.role`'s own `CHECK (role IN ('runtime','developer'))` is untouched). **Dated addendum (2026-08-31, phase 3.5 WP-4, house style -- original text above kept for record, "and no `role` column at all" is no longer accurate**: an in-place `ALTER TABLE` added `role text NOT NULL DEFAULT 'control' CHECK (role IN ('control', 'audit'))` (`docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md` §1-D/§4) -- a *second*, narrower control-credential authority class (`audit`, read-only on 3 endpoints, ceremony-issued only), still structurally distinct from an application credential's own `role` vocabulary (`'runtime'`/`'developer'`) and its own separate table; see `security/CONTROL_MAPPING.md`'s SI-02/SI-06 rows). |
| `r2dbsvc_registry.control_audit` (new table) | Contract `audit.fields`' **13** named columns (phase 3.5 WP-1/WP-4 added `target_id`, a nullable, optional field naming the single target credential/application a lifecycle event acted on -- `docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md` §1-C/§4) plus `recorded_at` (this table's own `DEFAULT now()` DB-side insertion timestamp, distinct from the application-supplied `occurred_at`). `event_id` is the primary key, generated application-side (never a server default), so a retried INSERT after a failed one can never split one intended event into two ids. |
| `applications.issuance_frozen` (dated addendum, 2026-08-31, phase 3.5 WP-4) | An in-place `ALTER TABLE r2dbsvc_registry.applications ADD COLUMN issuance_frozen boolean NOT NULL DEFAULT false` -- a per-application, CLI-only (`freeze-issuance`/`unfreeze-issuance`, non-destructive, no declare-and-echo) issuance lever: `issue_credential` against a frozen application is refused `FORBIDDEN` (`docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md` §1-E/§4). |
| `r2dbsvc_controlplane` (new login role) | `LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT CONNECTION LIMIT 10`. This is the role the control-plane HTTP process (`r2db_api.control_main`) authenticates as (`R2DB_CONTROLPLANE_DSN`) -- **never** `r2dbsvc_control`. Grants: `applications` SELECT/INSERT/UPDATE (no DELETE -- application deletion stays out of scope); `credentials` SELECT/INSERT/UPDATE (no DELETE -- `delete-credential` stays CLI-only); `control_credentials` SELECT/UPDATE **only, deliberately no INSERT** (the database-privilege half of "control-credential issuance is out-of-band only" -- "案B" -- independent of and in addition to the application-level enforcement); `control_audit` INSERT **only, no SELECT/UPDATE/DELETE** (append-only from this role -- R-3/R-6; this role can append an audit event but can never read one back, verified by `r2db-api/tests/test_control_plane_store.py::test_controlplane_role_grants_match_the_design`). No `GRANT EXECUTE` on any provisioning function, and no `GRANT` on any `SEQUENCE`/`FUNCTION` object at all, appears anywhere in this migration for this role -- both confirmed as review items, not merely asserted (see the migration's own §1.4 comments, each tied to the specific design requirement it satisfies). |
| `r2dbsvc_control` gains an explicit `GRANT INSERT ON control_audit` too | Not merely relying on this role's pre-existing schema-owner privilege (`0002`'s `CREATE SCHEMA ... AUTHORIZATION r2dbsvc_control`) -- stated explicitly so a future change to schema ownership cannot silently revoke the CLI's own ability to write audit rows as a side effect nobody noticed. This is the one grant this role gains from `0006`; it already has full DML on every other table in this schema by ownership. |

**Append-only, precisely scoped**: `control_audit`'s append-only guarantee
holds *from the `r2dbsvc_controlplane` role* -- the schema owner
(`r2dbsvc_control`, the operator/CLI role) retains ordinary PostgreSQL
owner privilege over this table (can `SELECT`/`UPDATE`/`DELETE` it, same as
every other table in this schema it owns). This is the same "externally
governed where required" shape the common contract's own `audit.immutability`
already anticipates (`security/CONTROL_MAPPING.md`'s SI-14 row states this
precisely) -- append-only is a real, DB-enforced property against the
control-plane HTTP process specifically, not a claim that no PostgreSQL
role anywhere could ever alter this table.

## 12. Bootstrap/reset ritual (`python -m r2db_api.ops bootstrap`/`reset`)

The **only** way a `role=control` credential is ever created (design "案B" --
no HTTP endpoint anywhere can do this). Both connect with `R2DB_CONTROL_DSN`
(`r2dbsvc_control`) and `R2DB_CONTROL_CREDENTIAL_PEPPER` (a value that must
differ from `R2DB_CREDENTIAL_PEPPER` -- both subcommands refuse to run at
all if the two are equal, checked before touching the database).

**`bootstrap`** -- run exactly once per platform database, ever:

```
R2DB_CONTROL_DSN=... R2DB_CONTROL_CREDENTIAL_PEPPER=... python -m r2db_api.ops bootstrap
```

Refuses (`CONFLICT`, exit code 1) if **any** `control_credentials` row
already exists -- including one that has since been revoked (the contract's
own text is "while a control credential exists", read as row-existence, not
"while an unrevoked one exists"; reading it the other way would open a
second issuance path once every row happened to be revoked). **Recovery
from that state is always `reset`, never a second `bootstrap`.** On success,
prints `credential_id`/`secret` once (never stored anywhere by this process
beyond the verifier) and writes one canonical `control_credential_lifecycle`
audit event in the same transaction as the issuance.

**`reset`** -- the general-purpose recovery, at any time. **Q-1 WP-4 (design
docs/design/DESTRUCTIVE_CONFIRMATION_V1.md R-4): `reset` is genuinely
destructive (it revokes every existing control credential) and is now gated
by the same declare-and-echo confirmation protocol the rest of this
contract's destructive operations use -- `reset` is now a two-step
invocation, not one:**

```
# Step 1: declaration (no --confirm, or a wrong one) -- refused: exit code 2
# *and* the confirmation phrase to echo (plus consequence/reversible_
# alternative/recovery) printed as one line of JSON on stderr. Nothing is
# touched at all. (Exit code 2 alone is not this refusal's signature --
# `argparse`'s own usage errors and this CLI's `_die`-based failures
# [missing env var, etc.] also exit 2; only the JSON-on-stderr shape
# identifies an R-4 confirmation refusal specifically.)
R2DB_CONTROL_DSN=... R2DB_CONTROL_CREDENTIAL_PEPPER=... python -m r2db_api.ops reset

# Step 2: echo the declared phrase back verbatim -- this is the invocation
# that actually runs the ritual.
R2DB_CONTROL_DSN=... R2DB_CONTROL_CREDENTIAL_PEPPER=... \
  python -m r2db_api.ops reset --confirm RESET_CONTROL_CREDENTIALS
```

**The first, unconfirmed invocation above is the declaration step, not an
attempt at the ritual itself -- `reset` has not run at all when it exits 2
with the JSON declaration on stderr.** Nothing in `control_credentials`/
`applications`/`credentials`/`control_audit`
is read or written by that first invocation (the confirmation phrase,
`RESET_CONTROL_CREDENTIALS`, is a fixed constant needing no database state
to compute -- see `structured.RESET_CONTROL_CREDENTIALS`'s own docstring for
why `reset`'s phrase carries no state fingerprint, unlike a re-creatable
named target). An operator who already knows the phrase (as documented
here) may skip straight to step 2; an operator who does not (or who wants to
confirm this documentation is still accurate) gets it fresh from step 1's
own stderr declaration every time -- guessing or hardcoding a phrase from
memory alone is never the supported path (contract
`destructive_confirmation.client_obligation`), even though this operation's
own phrase happens to be a fixed string in this implementation.

Once actually confirmed (step 2), `reset` revokes **every** existing control
credential and issues exactly one new one, atomically (both in the same
transaction -- there is never a moment where the old credentials are
revoked but no new one exists yet, or vice versa). Touches nothing in
`applications`/`credentials`/`control_audit` beyond the one canonical event
this itself writes.

**Both rituals serialize against each other** via a fixed-key
`pg_advisory_xact_lock` (`ops.py`'s own `_RITUAL_ADVISORY_LOCK_KEY`),
acquired before the existence check runs, on the same connection/transaction
the rest of the ritual uses -- closing the race where two concurrent
`bootstrap` invocations (or a `bootstrap` and a `reset`) could otherwise
both observe "no live row" before either commits.

**Non-permanence (must-rotate)**: the credential either ritual issues has
`must_rotate = true` -- authorized for nothing but `GET
/control/v1/capabilities` and rotating itself (in-band, or the CLI
break-glass `rotate-control-credential` below) until a real rotation
completes. This is what satisfies the contract's "expires or requires
rotation" for the first-issued credential without depending on wall-clock
time.

**Break-glass, control-credential-specific (R-10, always available even
with `/control/v1` fully down):**

```
python -m r2db_api.ops enable-control-credential <credential_id>   # re-enable a disabled (not revoked) one
python -m r2db_api.ops rotate-control-credential <credential_id>   # replace its secret in place, same credential_id
```

Neither offers an *un-revoke* -- revocation stays terminal by design (SI-13:
un-revoking would make a durably-recorded revocation event false); the only
recovery from a revoked control credential is `reset`.

## 12a. Phase 6 WP-2: existing-credential re-issuance for the locator wire form (D-1)

Contract 1.6.0 (subordinate ruling 11, item 1) requires that a credential's
`secret` be presented **verbatim, whole**, as `Authorization: Bearer
<secret>`. This peer's common realization (design docs/design/
PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md D-1(c)) is a locator token,
`<credential_id>.<secret>`, joined by a single `.` -- authentication now
resolves the row by `credential_id` (a `credential_id`-keyed lookup,
`credential_store.py`'s `_SELECT_BY_ID`) and THEN checks the secret's digest,
rather than the pre-1.6.0 digest-keyed lookup alone.

**No migration and no re-hash is required at the database level** -- the
stored `verifier` column is unchanged in shape and content (still `HMAC-
SHA256(pepper, secret)` of the same *secret* value each credential was
issued with); only the WIRE form the client presents has changed, from the
bare secret to the composed locator. **This means every credential issued
before this peer's own 1.6.0 flip -- both application credentials
(`r2dbsvc_registry.credentials`) and control credentials (`control_
credentials`) -- can no longer authenticate as-is**: a client presenting
only the old bare secret (no `credential_id.` prefix) now fails closed with
`AUTH_INVALID` (SI-15's own fail-closed-on-malformed-locator rule), the
identical response an unknown credential produces (SI-10: the response
never distinguishes the two).

**There is no compatibility shim and none is planned** (design's own
"互換シムを置かない" ruling) -- there is no dual-form transitional period.
**Operator action required, once, at or before this peer's 1.6.0 rollout**:
every application and control credential that must keep working needs a
fresh secret, via the ordinary rotation path, not a new provisioning step
(the row/`credential_id`/scope are unchanged -- only the secret half):

```
# Application credentials (repeat per credential_id that must keep working):
R2DB_CONTROL_DSN=... R2DB_CREDENTIAL_PEPPER=... \
  python -m r2db_api.ops rotate-credential <credential_id>

# Control credentials (break-glass, works even with /control/v1 down):
R2DB_CONTROL_DSN=... R2DB_CONTROL_CREDENTIAL_PEPPER=... \
  python -m r2db_api.ops rotate-control-credential <credential_id>
```

Each command prints the SAME two lines as issuance (`credential_id:` /
`secret:`) -- the printed `secret:` is now the complete, composed bearer
token; copy it whole (never split it, never re-derive a locator from a
`credential_id` you already know and an old bare secret you happen to
still have -- both are contract violations a conformant client must not
make, and this peer's own store no longer has a row keyed on the old bare
secret's digest to match against regardless). This is a Stage 1 concern
only in the sense that Stage 1 (`DEPLOYMENT_RUNBOOK.md` §0) carries no
production traffic yet -- there is no live client to coordinate a rotation
window with. A deployment that has already taken production traffic before
adopting 1.6.0 must treat this rotation as a **breaking, coordinated
credential-rollover event**, not a background operation: every holder of an
affected credential needs the new composed secret before (or immediately
after) the flip, or their next request fails closed.

## 13. Control-plane lockout paths and recovery

Three ways an operator can end up unable to use `/control/v1` at all, and
the current, lightest recovery for each (design R-5 §7/§8 m-2 originally
recorded all three as "recover via `reset` only" -- written before R-10, in
the same design revision, added the two lighter break-glass subcommands
below specifically to avoid needing `reset`'s heavier blast radius,
revoke-everything-and-remint-one, for the two cases that do not actually
involve a revoked credential; this section documents the current, more
specific guidance those additions make possible, not a contradiction of R-5):

1. **A rotation succeeded, but the new secret was never captured** (network
   blip, terminal scrollback lost, etc.) -- the credential itself is fine
   and not disabled/revoked, only its current secret is unknown. Recovery:
   `rotate-control-credential <credential_id>` (same `credential_id`, a
   fresh secret, printed once) -- lighter than `reset`, and preserves audit
   continuity (every prior `control_audit` row naming this `credential_id`
   still refers to the same, still-live credential).
2. **The one live control credential was disabled** (not revoked) --
   in-band or by mistake. Recovery: `enable-control-credential
   <credential_id>` -- re-enables it in place; no new secret is issued or
   needed.
3. **`control_requests_per_minute` (R-7) is exhausted** -- the credential
   itself is unaffected; the control-plane HTTP process is refusing *all*
   `/control/v1` requests (429) until its single, global rate window
   clears. `python -m r2db_api.ops` never goes through this window at all
   (`ControlPlaneService`'s rate check is HTTP-request-path-specific; the
   CLI talks to PostgreSQL directly) -- any CLI subcommand, not only
   `reset`, is unaffected and usable immediately. Simply waiting also
   resolves this with no CLI use at all: the window is a sliding 60-second
   window (`ControlPlaneService._check_rate`, round-2 review MI-7 --
   stricter than a fixed/bucketed window, deliberately), so it always
   clears within 60 seconds of the last request that filled it, regardless
   of `R2DB_CONTROL_LIMIT_CONTROL_REQUESTS_PER_MINUTE`'s own configured
   count.

`reset` remains the universal fallback for all three (and the *only*
recovery once a control credential has actually been revoked, or when the
`credential_id` itself is not known/trusted) -- it is simply heavier than
necessary for cases 1 and 2 above, now that lighter, targeted recovery
exists for them. Since Q-1 WP-4, `reset` is the two-step, gated invocation
§12 above documents (a first, unconfirmed call declares the phrase and
touches nothing; echoing it back on a second call runs the ritual) -- that
first, declaring call is always safe to run in every one of the three
lockout scenarios above, including case 3 (the rate window has no bearing
on this CLI at all, per that bullet's own note), so an operator unsure which
case applies can always start with an unconfirmed `reset` to get the exact
phrase to echo, with nothing at risk from that first call alone.

## 14. Manual recovery from a crash between `begin_provision_application` and `finish_provision_application`

A known, pre-existing operational wart (unchanged by `0006` -- see that
migration's own header comment on `begin_provision_application`, "KNOWN,
UNCHANGED, PRE-EXISTING WART"): `begin_provision_application` (§2/§5 above)
runs its two `CREATE ROLE` statements *before* `0003`'s `CREATE DATABASE`
step, and (since `0006`) writes nothing to `applications` at all --
`finish_provision_application`, at the very end of `0003`, is the only
place a provisioning claim is ever recorded. A process crash, connection
loss, or operator interrupt **anywhere between `begin`'s `CREATE ROLE`
statements and `finish` running** -- which spans the whole of `0003`'s own
body: `CREATE DATABASE`, the `CONNECT`/`USAGE` grants, `\c` into the new
database, `ALTER SCHEMA public OWNER TO` the developer role, and the
domain/table/RLS/view setup inside it -- therefore leaves:

- the two per-application login roles (`r2dbsvc_app_<slug>_runtime`,
  `r2dbsvc_app_<slug>_developer`) **created and present in `pg_roles`**, but
- **no completed provisioning claim** in `r2dbsvc_registry.applications` --
  either no row at all (operator-first flow), or a registered-only row
  (`database_name IS NULL`, from a prior `POST /control/v1/applications`)
  left exactly as it was.

This is safe from a serving standpoint (`r2db_api.main`'s own startup
check, §10 above, refuses to serve a registered-but-not-provisioned slug),
but a *retry* of provisioning for the same slug now fails loudly until the
residue is cleared by hand -- **exactly how depends on where inside `0003`
the crash landed**, which is why detection below has three queries, not
two: a crash before `CREATE DATABASE` leaves only role residue (`CREATE
ROLE ... already exists` on retry), but a crash at or after `CREATE
DATABASE` also leaves the database itself behind, and once `ALTER SCHEMA
public OWNER TO` has run, that database's `public` schema (and everything
`0003` created inside it before the crash) is *owned* by the residual
developer role -- `DROP ROLE` refuses to drop a role that still owns
objects, so the two-query, roles-only recovery this section originally
described does not work past that point (confirmed by re-running this
recovery against a deliberately crashed `0003` at several injection
points).

**Detection:**

```sql
-- 1. Do the per-application roles already exist?
SELECT rolname FROM pg_roles
  WHERE rolname IN ('r2dbsvc_app_<slug>_runtime', 'r2dbsvc_app_<slug>_developer');

-- 2. Is there a completed provisioning claim for this slug?
SELECT database_name FROM r2dbsvc_registry.applications
  WHERE application_slug = '<slug>';

-- 3. Did CREATE DATABASE itself already run?
SELECT 1 FROM pg_database WHERE datname = 'r2dbsvc_app_<slug>';
```

If query 1 returns either role **and** query 2 returns no row, or a row
with `database_name IS NULL`, provisioning never completed for this slug
even though `begin`'s roles were created -- this is exactly the residue
this section recovers from. Query 3 decides *which* of the two recovery
branches below applies -- do not skip it and assume branch (A); guessing
wrong surfaces as `DROP ROLE` failing with a "some objects depend on it"
error partway through branch (A), not as a silent no-op.

**Recovery -- branch (A): query 3 returned no row (`CREATE DATABASE` never ran)**

1. Confirm nothing is actually connected as either residual role:
   ```sql
   SELECT pid, usename FROM pg_stat_activity
     WHERE usename IN ('r2dbsvc_app_<slug>_runtime', 'r2dbsvc_app_<slug>_developer');
   ```
   This should return no rows -- these roles' passwords were freshly
   generated for the interrupted run (per `0003`'s own header, by the
   operator, via `openssl rand`, with an instruction to record them in a
   secret manager immediately; whether that recording actually happened is
   a matter of operator practice this recovery cannot verify) and, since
   provisioning never completed, nothing in this flow has had reason to
   authenticate as either role yet. If this query does return a row,
   investigate before proceeding -- dropping a role with an active session
   requires terminating that session first, and an active session here
   would itself be unexpected and worth understanding.
2. Drop the residual roles:
   ```sql
   DROP ROLE IF EXISTS r2dbsvc_app_<slug>_runtime;
   DROP ROLE IF EXISTS r2dbsvc_app_<slug>_developer;
   ```
   Safe: no database was ever created for this slug (query 3 confirmed it),
   so neither role owns anything anywhere in the cluster to worry about
   orphaning -- at this point in `0003` they hold only `CONNECT`/membership
   grants, never ownership, and a role that merely holds granted privileges
   (as opposed to owning objects) drops cleanly.
3. Re-run `0003_provision_application.sql` for the slug (§5 above) as
   normal, with freshly generated passwords -- `begin_provision_application`
   now finds no pre-existing roles and no completed provisioning claim, so
   it proceeds exactly as a first attempt would.

**Recovery -- branch (B): query 3 returned a row (`CREATE DATABASE` already ran)**

The database must be removed *before* the roles -- in this branch, `public`
(and whatever `0003` managed to create inside it before the crash: the two
CCR-13 domains, `_r2db_schema_revision`, the `_r2db_missing_rls` view) may
already be owned by the residual developer role (`ALTER SCHEMA public
OWNER TO`, `0003`'s own line -- see this section's intro), which blocks a
plain `DROP ROLE` outright. Dropping the database first removes every
object inside it, ownership included, so neither role owns anything left
anywhere in the cluster once it is gone:

1. Clear any sessions against the residual database, in the same order
   `0004`'s own live-connection handling now uses (design
   `docs/design/DEPROVISION_FORCED_DROP_V0_1.md` v1.0, D-2R) -- a crash
   mid-`0003` is not expected to leave live sessions, but confirm rather
   than assume:
   ```sql
   -- pre-check: read who (if anyone) is connected before changing anything.
   -- `backend_type` reads NULL here for a backend whose role you do not
   -- hold privileges of (design M-5/H-2); judge by `usename`/`usesysid`
   -- instead -- `usesysid IS NULL` is a background worker (autovacuum),
   -- which the pre-check deliberately does not count (design D-2R
   -- stage (2), M-12).
   SELECT usename, usesysid IS NOT NULL AS is_a_login_role FROM pg_stat_activity
     WHERE datname = 'r2dbsvc_app_<slug>' AND pid <> pg_backend_pid();

   -- temporary self-grant (branch (B) was entered because CREATE DATABASE
   -- had already run, and both roles are created before it -- see this
   -- section's intro; if either GRANT still reports role "..." does not
   -- exist, skip that one, exactly as 0004's own EXISTS guard does):
   -- needed only if a connection under one of them is present
   -- (`pg_terminate_backend` requires privileges of the role being
   -- terminated); a no-op otherwise.
   GRANT r2dbsvc_app_<slug>_runtime TO CURRENT_USER WITH INHERIT TRUE, SET FALSE;
   GRANT r2dbsvc_app_<slug>_developer TO CURRENT_USER WITH INHERIT TRUE, SET FALSE;

   -- close the reconnect window before terminating
   ALTER DATABASE r2dbsvc_app_<slug> WITH ALLOW_CONNECTIONS false;

   -- narrowed terminate, the same filter `0004` itself uses
   SELECT pg_terminate_backend(pid) FROM pg_stat_activity
     WHERE datname = 'r2dbsvc_app_<slug>' AND pid <> pg_backend_pid()
       AND backend_type = 'client backend';
   ```
   If this stops partway through, the state left behind and what to do
   next mirrors `0004`'s own (design §4.1):

   | Stopped at | State left behind | Next step |
   |---|---|---|
   | the pre-check read (nothing changed yet) | database, `ALLOW_CONNECTIONS`, role membership and the registry row all unchanged | investigate the connection the read reported, then continue |
   | `ALLOW_CONNECTIONS false` through the terminate | database left unreachable (`ALLOW_CONNECTIONS false`); the temporary self-grant left standing | continue to step 2 below, or abandon with `ALTER DATABASE r2dbsvc_app_<slug> WITH ALLOW_CONNECTIONS true` and `REVOKE r2dbsvc_app_<slug>_runtime FROM CURRENT_USER` (likewise `_developer`), run by `r2dbsvc_control` itself |
2. Drop the database, then the two roles:
   ```sql
   DROP DATABASE IF EXISTS r2dbsvc_app_<slug>;
   DROP ROLE IF EXISTS r2dbsvc_app_<slug>_runtime;
   DROP ROLE IF EXISTS r2dbsvc_app_<slug>_developer;
   ```
   The `DROP DATABASE` above must succeed before the `DROP ROLE` statements
   are attempted -- if it fails (e.g. `database "..." is being accessed by
   other users`, most likely a just-terminated backend not yet fully gone
   from `pg_stat_activity` -- the residual-visibility gap `0004`'s own
   comment above its terminate step documents; the autovacuum-worker
   condition this note previously named is not the usual cause here --
   the narrowed terminate above never touches a worker, and a plain
   `DROP DATABASE` cleared one in the design's own measurement (M-12, a
   single measurement -- see §5's correction note for the two causes and
   why waiting is not free)), resolve that first (a short wait is usually
   enough); do not attempt to drop the roles while the database that owns
   objects through them still exists.
3. Re-run `0003_provision_application.sql` for the slug (§5 above) as
   normal, with freshly generated passwords -- identical to branch (A)'s
   own step 3, now that both the roles and the database are gone.

## 15. Application-plane durable audit sink (`0007_application_audit.sql`) and `audit_query`

Companion to `docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md` (D-1/D-5/D-6).
Applying `0007`, configuring the reader DSN, the relationship between the two
audit-writer timeouts and the `audit_query` visibility lag, and then, in
§15.1-§15.5, the operational parts: platform-DB capacity thresholds,
logs-based alerting, manual retention/pruning, reading evidence during
a platform-DB outage, and the paths the control host's edge policy must
cover.

**Apply `0007`, once, after `0006`** (order matters only in that `0007`
assumes `r2dbsvc_registry.control_audit` already exists), connected as
`r2dbsvc_control`:

```
psql "$R2DBSVC_CONTROL_DSN" -v auditreader_password="$R2DBSVC_AUDITREADER_PASSWORD" \
  -f r2db-api/migrations/0007_application_audit.sql
```

`R2DBSVC_AUDITREADER_PASSWORD` is a new environment-variable *name*,
generated the same way every other `psql -v ..._password` variable in this
runbook is (§5's note on `psql`'s password variables). Like every other
migration in this directory, `0007` is safe to re-run (`CREATE TABLE IF NOT
EXISTS`, the conditional `CREATE ROLE ... \gexec` idiom, naturally
idempotent `GRANT`s).

**What it adds** (full rationale: the migration file's own header, and
design D-1/D-5/§6.1): the `application_audit` table (`r2dbsvc_api`
INSERT-only), and the new `r2dbsvc_auditreader` role -- SELECT-only on
*both* `control_audit` and `application_audit`, held by nothing else in
this cluster.

**Reader DSN (`R2DB_AUDIT_DSN`)**: the control-plane HTTP process
(`r2db_api.control_main`) reads this env var, OPTIONALLY. Set it to a DSN
authenticating as `r2dbsvc_auditreader` against `r2dbsvc_platform`, and
`audit_query` (`POST /control/v1/audit/query`, aliased at `POST /v1/audit/
query` on the same control host) becomes `enabled` -- both paths answer
real requests, control/audit credential only. **Leave it unset** and
`audit_query` stays declared `unavailable`: the two routes are still
registered (never a bare 404) and still authenticate the caller, but answer
`CAPABILITY_UNSUPPORTED` for anyone who successfully authenticates. This is
a real, honest capability toggle, not a "coming soon" placeholder -- a
deployment can run indefinitely with `application_audit`/`control_audit`
durably filling and `R2DB_AUDIT_DSN` unset; evidence keeps accumulating,
only the in-band read surface is off.

**The two writer timeouts and `visibility_lag_ms` -- SUPERSEDED by the Q4
phase (2026-09-05, design `docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md`
D-1/D-2, migration `0008`). Read §16 below; the paragraphs this replaces
described the env-var mechanism that no longer exists.** In summary of what
changed: `R2DB_AUDIT_STATEMENT_TIMEOUT_MS` / `R2DB_AUDIT_IDLE_TIMEOUT_MS`
are **removed** env vars -- either one defined at all, whatever its value,
now fails startup (F-1) -- and both writer roles carry `statement_timeout` /
`idle_in_transaction_session_timeout` as PostgreSQL **role settings**
(`ALTER ROLE ... SET`, `0008`), which is the single source both the declared
`audit_query.visibility_lag_ms` and the writer connections' own effective
values come from. The derivation itself is unchanged --
`max(statement_timeout_ms + idle_in_transaction_session_timeout_ms) over the
declared writer roles + 1000` (1s clock-skew margin), `11000` at the shipped
`5000`/`5000` defaults -- but it is no longer a claim two processes have to
be configured into agreeing about: each writer process verifies, at startup,
that its OWN effective value equals the catalog value it derived from, and
refuses to start otherwise (F-7/F-9/F-10/F-11/F-13, §16). The former
"structural assumption" recorded here and in `security/CONTROL_MAPPING.md`'s
SI-14 point 12 is closed, with the two limits §16 states.

The denial-coalescing window moved the same way: `control_capabilities.
audit_query.coalescing_window_ms` is now the `audit_coalescing_window_ms`
row of `r2dbsvc_registry.platform_declarations`, read by BOTH processes at
startup, so the data-plane's actual `DataService(denial_coalesce_window_s=
...)` and the published declaration come from one row rather than from a
constant on one side and a constructor argument on the other. Change it with
`python -m r2db_api.ops declare-coalescing-window --ms <N>` and restart both
processes -- never by editing a constant in either process' source. The
window's counts are not held in any process: every data-plane worker adds
to the same counter row in the platform database (`0016`, §21). The window
length is part of that row's key, so workers restarted one by one across a
length change never add to each other's rows.

**Anything that changes either timeout still changes a published
declaration** -- that has not changed, only the place you change it (`ops`,
not env) and the fact that a mismatch now stops a process instead of
publishing a false declaration.

**Declared audit vocabularies (contract 1.5.0, subordinate ruling 10 item 1).**
The `audit_query` capability entry also publishes THREE vocabularies:
`event_classes`, and -- new in contract 1.5.0 -- `operations` and
`target_kinds`. Each is the set of values the corresponding audit-row column
can take, and every event `audit_query` returns carries values drawn from
them. The contract requires only that superset relation and enumerates no
enum: each implementation declares its OWN vocabulary, so the two peers'
spellings legitimately differ (this peer folds every data mutation into one
`mutate`/`entity` pair; the sibling peer names each operation individually and
calls the target a `collection`). This process publishes them `sorted()` from
`r2db-api/src/r2db_api/audit_query.py`'s `DECLARED_AUDIT_OPERATIONS` /
`DECLARED_AUDIT_TARGET_KINDS` -- currently **27 `operations` and 5
`target_kinds`**. `audit_query.operations` is the audit row's `operation`
vocabulary, unrelated to the `operations` array of a mutation request body.

Three things to know operationally. **(1) There is no env-var knob and nothing
to size** -- unlike the two timeouts above, these are fixed by the code you
deployed; the only way they change is a new build. **(2) Only the CONTROL
process declares them.** The data-plane host declares `audit_query` as
`unavailable` and carries neither key, deliberately: it never serves
`audit_query`, so declaring a vocabulary it can never surface would be an
untrue declaration. `unavailable` there is correct, not a deployment fault.
**(3) They are version-bound.** A build predating contract 1.5.0 declares
`contract_version: "1.4.0"` and carries neither key -- fully conformant for
that version; a build declaring `1.5.0` must carry both. A deployment whose
declared version and declared keys disagree is a version-binding defect. If an
`audit_query` result ever shows an `operation` or `target_kind` absent from
the declaration, treat it as a defect and report it: the declaration is
checked against this package's own source on every test run, so a divergence
in a live deployment means the deployed artifact is not the tested one.

**`audit_requests_per_minute`**: a separate, dedicated env var,
`R2DB_CONTROL_LIMIT_AUDIT_REQUESTS_PER_MINUTE` (default `60`, same
convention as `R2DB_CONTROL_LIMIT_CONTROL_REQUESTS_PER_MINUTE`) -- this
window governs `audit_query` alone (both its canonical and alias paths) and
is never shared with `control_requests_per_minute`. This separation is what
lets a break-glass `revoke_credential` succeed even while an audit tool is
polling `audit_query` at its own, independent rate. Recommended polling
interval for an audit consumer: no faster than the declared
`visibility_lag_ms` (polling faster than the lag a deployment has actually
configured cannot surface events any sooner, it only spends more of this
window).

**Sizing the `audit_requests_per_minute` window.** One `audit_query` call
is one page, so a consumer's steady-state cost is
`60000 / <declared visibility_lag_ms>` requests per minute -- about **5.5
req/min per consumer** at the default 11000 ms lag. The default of `60`
therefore supports roughly **ten** concurrently polling audit consumers
with headroom. Size it as:

```
audit_requests_per_minute  >=  ceil(<concurrent audit consumers>
                                    * 60000 / <visibility_lag_ms>)
                               + headroom for catch-up
```

One thing makes the naive product too small in practice: **catch-up is
paging, not polling**. A consumer resuming after an outage walks the cursor
one page per request until a page comes back empty, so draining a backlog
of N events at `limit` per page costs `N/limit` requests as fast as the
consumer can issue them -- far above the steady-state rate. Size for the
catch-up case, or accept refusals during catch-up.

**Raising the window on this peer is a configuration change, with no upper
bound.** `ControlPlaneLimits.__post_init__` (`src/r2db_api/limits.py`)
validates only that each limit is a positive integer -- there is no ceiling
on `audit_requests_per_minute` here, and the peer's own test suite really
does construct and publish `audit_requests_per_minute=100_000`. So a
deployment that outgrows the default sets
`R2DB_CONTROL_LIMIT_AUDIT_REQUESTS_PER_MINUTE` to whatever its audit-agent
population needs and nothing else has to change. Widening this window does
not weaken the property the window exists for: it is checked **before**
authentication and before any durable write, so no window size lets an
unauthenticated flood generate audit rows. **The accepted value has always
been an operator responsibility on this peer, published as-declared** in
`control_capabilities` -- there is no code-side guardrail against declaring
an implausibly large value, and there never has been. **This peer and
`MitateDB-api` are now symmetric** (Phase 5 D-3, Q3 案A, WP-4): MitateDB's
own `ControlPlaneLimits.__post_init__` used to bound the same four
request-count classes to `[1, 200]`, so raising this window there used to
be a code change rather than a configuration change; that ceiling has been
removed, and MitateDB now carries the identical "positive integer, no
upper bound, operator's responsibility" rule (`MitateDB-api/docs/cloud-run-
cloud-sql.md` §3.2c). The contract declares no range for this class, so
both peers have always conformed regardless; the (now former) asymmetry is
recorded in `security/CONTROL_MAPPING.md`'s SI-08 row.

Hitting the window is a plain `LIMIT_EXCEEDED`
refusal and costs nothing but time: the consumer's cursor is still valid, so
it resumes exactly where it stopped. In every case a break-glass
`revoke_credential` is unaffected, because `audit_query` never touches
`control_requests_per_minute` (`r2db-api/tests/test_audit_query.py::test_
audit_query_does_not_consume_the_control_requests_per_minute_window`).

### 15.1 Platform-DB capacity thresholds (row size x row count)

The design bounds audit growth in three layers (D-1's own capacity
argument): bounded row SIZE, bounded row COUNT per operation, and this
runbook's monitoring. The third layer is only meaningful with the first two
quantified, so:

**Row size.** `0007`'s per-column `length` CHECKs cap the eleven bounded text
columns at `64 + 256 + 256 + 64 + 256 + 64 + 64 + 64 + 32 + 128 + 256 =
1504` characters in total. Adding `event_id` (a uuid string), the two
timestamps, `count`, `audit_seq` and PostgreSQL's own per-tuple overhead,
**budget 2 KiB as a hard per-row upper bound**. No application input can
exceed it -- the CHECK rejects the INSERT, which is itself verified
(`test_application_audit.py::test_api_role_cannot_insert_a_value_longer_
than_the_length_check`).

**Counter row size (`0016`, §21).** The ten bounded text columns of
`denial_window_counter` cap at `64 + 256 + 256 + 64 + 256 + 64 + 64 + 64 +
128 + 256 = 1472` characters. `denial_key` has no CHECK of its own: it is
the JSON text of the window length and four of those columns, measured at
4252 bytes with each of the four at its limit and made of characters JSON
escapes as `\u00XX`. **Budget 6 KiB per counter row**, counting each
character as one byte, as the 2 KiB `application_audit` budget above does.
Multi-byte characters raise it: with every column filled with 4-byte UTF-8
characters the text columns measured 8732 bytes, about 8.9 KB per row
before compression with the fixed columns and tuple header.

**Row count, whole deployment.** Nothing is counted per process: every
event is written before its response, and every data-plane worker adds to
the same counter row (§21). Per interval the deployment adds at most:

| source | bound (all processes together) |
|---|---|
| operations | 1 `application_audit` row per user operation (+1 `error` row if the data commit fails) |
| coalesced denials | per key and window: 1 `application_audit` row (the first refusal) + 1 `denial_window_counter` row (each later refusal adds 1 to it). The window length is part of the key. With `audit_coalescing_window_ms` 0, every refusal is its own `application_audit` row and no counter row is written |

Counter rows are audit evidence. `r2dbsvc_api` holds no privilege on the
table (it reaches it only through the function), so no process can lower or
delete a count. Retention is §15.3's procedure with `window_end` in place of
`recorded_at`; vacuum is left to autovacuum, as for `application_audit`.
Unlike that INSERT-only table, each later refusal UPDATEs its counter row
and leaves one dead tuple until autovacuum reclaims it.

A serviceable rate model for alerting, with `W = 3600000 /
audit_coalescing_window_ms` windows per hour (60 at the shipped 60000):

```
bytes/hour  ~=  2 KiB * ( <ops/hour> + <distinct denial keys> * W )
              + 6 KiB * <distinct denial keys> * W
```

Alert on the **growth rate** of the tables, not an absolute size (an absolute
size is a retention decision, §15.3):

```sql
-- as r2dbsvc_control (schema owner); sample periodically and alert on delta
SELECT pg_total_relation_size('r2dbsvc_registry.application_audit')     AS application_audit_bytes,
       pg_total_relation_size('r2dbsvc_registry.control_audit')         AS control_audit_bytes,
       pg_total_relation_size('r2dbsvc_registry.denial_window_counter') AS denial_window_counter_bytes;
```

Why this matters beyond housekeeping: the platform database also holds the
credential store for **every** application, so filling its disk stops
authentication platform-wide. That is the availability side of SI-00, and it
is the reason the row-size and row-count bounds above exist at all.

### 15.2 Logs-based alerting

A revision that counts refusals in the platform database (`0016`, §21;
contract 1.13.0) emits no log message of its own from the audit pipeline:
every event and every refusal count is written before its response, and a
write that fails answers the request `SERVICE_UNAVAILABLE` (503) instead of
waiting in memory (contract `audit.process_loss_policy`). **A revision older
than that -- the rollback target, and the old revision while a rollout
overlaps -- still keeps a bounded buffer and an in-process refusal window,
and the five fixed messages below are its only signal of evidence loss.
Keep a logs-based alert on each of the five for as long as such a revision
can serve.** They are fixed `logging.error` strings with no interpolation,
defined in that revision's `src/r2db_api/service.py`, in two independent
channels (buffer/overflow and coalescing), so alert on all five:

| message (exact) | meaning |
|---|---|
| `application_audit buffer overflow: events were dropped` | evidence loss has ALREADY happened: the bounded buffer evicted its oldest events |
| `application_audit overflow-alert row could not be written; retrying with backoff` | the in-band alert row itself cannot be written -- both the durable channel and the in-band alert are failing at once; retry is sticky with exponential backoff to a 60s ceiling |
| `application_audit overflow-alert row recorded; pending overflow cleared` | recovery of the pair above: the alert row landed and the accumulated drop count was reported in its `count` |
| `application_audit coalesced-denial summary row could not be written; retrying` | the window-end aggregate row of a coalesced denial is not landing. The first, synchronous row of that window IS durable, but the **repeat count is stranded in memory** -- and because the writer holds INSERT only, that first row's `count` can never be amended later (§15.1, design P4-D6). This is the only carrier of "how many times", so a stuck aggregate row is evidence loss even though nothing is refused |
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
ceiling up to one row per flush interval (this peer's default: 2s) -- this is
an accepted tradeoff, not a defect: the declared bound of at most one alert
row per flush interval still holds regardless (the `alert_min_interval_s`
floor rate-limits every attempt independently of this flag), evidence reaches
the durable table sooner from a partially-working sink, and no evidence is
ever lost either way -- the drop counter keeps accumulating and is reported
in the eventual alert row's `count`. As before, **do not read a gap between
messages as recovery**; read the recovery message of the pair concerned (the
third message for the buffer/overflow channel, the fifth for the coalescing
one).

### 15.3 Retention and pruning (manual, external, deliberately unautomated)

Nothing in `r2db_api` ever deletes an audit row, and no process role can:
`r2dbsvc_api` has INSERT only, `r2dbsvc_controlplane` has INSERT on
`control_audit` only, and `r2dbsvc_auditreader` has SELECT only. Pruning is a
**schema-owner (`r2dbsvc_control`) operation performed by an operator**,
which is precisely the contract's `audit.immutability` "externally governed
where required by the deployment" shape (design D-11/§10 -- automatic pruning
is explicitly out of scope, not merely unimplemented).

Procedure, in order:

Step 1 -- **EXPORT the window first; step 3 is irreversible.** There is no
CLI reader for `application_audit` (§15.4: `python -m r2db_api.ops
audit-report` reads `control_audit` ONLY), so export this table directly, as
`r2dbsvc_auditreader` (`R2DB_AUDIT_DSN`) or as the schema owner:

```
psql "$R2DB_AUDIT_DSN" -c "\copy (SELECT * FROM r2dbsvc_registry.application_audit \
  WHERE recorded_at < now() - interval '365 days' ORDER BY recorded_at, event_id) \
  TO '<export path>' WITH (FORMAT csv, HEADER)"
```

Store the export wherever the retention policy says evidence lives, and
verify it is readable before continuing. When the table being pruned is
`control_audit` instead, `python -m r2db_api.ops audit-report --since ...
--until ...` (over `R2DB_CONTROL_DSN`) is the supported export for that one.

```sql
-- 2. As r2dbsvc_control: confirm the blast radius before deleting.
SELECT count(*), min(recorded_at), max(recorded_at)
  FROM r2dbsvc_registry.application_audit
 WHERE recorded_at < now() - interval '365 days';

-- 3. As r2dbsvc_control: delete that same window.
DELETE FROM r2dbsvc_registry.application_audit
 WHERE recorded_at < now() - interval '365 days';
```

The identical three steps apply to `r2dbsvc_registry.control_audit` with its
own retention period. Record what was pruned, when, and by whom: after the
DELETE the table itself no longer evidences it.

### 15.4 Reading evidence while the platform database is unavailable

`audit_query`, the credential store, and both audit tables share ONE
database. If it is unreachable, the data plane already fails at
authentication (this was true before phase 4 -- the durable sink adds no new
single point of failure), and `audit_query` cannot answer either. **Evidence
is unreadable at exactly the moment it is most wanted.**

The one read path that does not depend on the control HTTP app, the reader
role, or `audit_query` is the out-of-band CLI, `python -m r2db_api.ops
audit-report`, which SELECTs directly over `R2DB_CONTROL_DSN`. Keep it and
its credentials available to operators: it is not made redundant by
`audit_query` and must not be retired in its favour. **Be precise about its
scope, though: `audit-report` reads `control_audit` only.** There is no CLI
reader for `application_audit`; the equivalent out-of-band access is a direct
`psql` session as `r2dbsvc_auditreader` (or as the schema owner
`r2dbsvc_control`) against `r2dbsvc_platform`:

```sql
SELECT recorded_at, event_class, request_id, application_id, actor_id,
       operation, target_kind, outcome, reason_code, count
  FROM r2dbsvc_registry.application_audit
 WHERE recorded_at >= now() - interval '1 hour'
 ORDER BY recorded_at, event_id;
```

Repeated refusals are counted in `denial_window_counter` (§21), not in
`application_audit`: each row is one key's window, `occurrences` counts
every refusal of it including the first (whose own row is in
`application_audit`), and a window is closed once `window_end` has passed:

```sql
SELECT window_start, window_end, occurrences, event_class, application_id,
       actor_id, operation, reason_code
  FROM r2dbsvc_registry.denial_window_counter
 WHERE window_end >= now() - interval '1 hour'
 ORDER BY window_end, denial_key;
```

All of these -- the CLI included -- still need the platform database itself
to be reachable. What they remove is the dependency on the control HTTP
process and on `audit_query` being declared `enabled`, not the dependency on
the database. There is deliberately no second copy of the evidence anywhere
(external SIEM forwarding is out of scope for this phase, design §10); if a
deployment needs evidence to survive the database being down, that is an
export/retention decision it must make for itself under §15.3.

### 15.5 The control host now serves a path outside the `/control/v1/*` prefix

Before phase 4, the control HTTP app (`r2db_api.control_main`) served
`/control/v1/*` and nothing else, so an edge policy expressed as a path
prefix -- "`/control/v1/*` is reachable only from the management network",
an LB path matcher, an ingress rule, an nginx `location` block -- covered the
whole control surface by construction. **That is no longer true.** The
control app now serves BOTH:

| path on the control host | note |
|---|---|
| `POST /control/v1/audit/query` | the canonical path; contract 1.4.0 classifies `audit_query` under `control_endpoints` |
| `POST /v1/audit/query` | the SAME handler, kept as an alias for one minor because the contract's previous classification put `audit_query` on the application surface |

Both are registered whether or not `R2DB_AUDIT_DSN` is set (unset means an
authenticated caller gets `CAPABILITY_UNSUPPORTED`, never a bare 404).

The alias exists so that a deployment routing by path prefix
(`/v1/*` to the data plane, `/control/v1/*` to the control plane) still has
`/control/v1/audit/query` as a correct route. But it means the reverse
mistake is now possible: **an edge policy that restricts only
`/control/v1/*` leaves the control host's `/v1/audit/query` outside that
restriction**, and that path reads `control_audit` as well as
`application_audit` -- SI-02 data reachable through a route the existing
operational boundary does not describe. When reviewing the deployment:

1. The control host's own network/IAM restriction must be expressed over the
   HOST (or over both prefixes), not over `/control/v1/*` alone.
2. `/v1/audit/query` on the **data** host is a different endpoint entirely and
   is unchanged: it authenticates an application credential and answers
   `CAPABILITY_UNSUPPORTED`. Two hosts answering the same path differently is
   deliberate -- each is making a true statement about itself -- and is
   pinned by `r2db-api/tests/test_audit_query.py::test_data_plane_host_audit_
   query_still_refuses_with_capability_unsupported`.
3. Do not "fix" the asymmetry by routing the data host's `/v1/audit/query` to
   the control app. That would put a control/audit credential's traffic on the
   application-facing host, which is the separation the SI-00/SI-02 rows of
   `security/CONTROL_MAPPING.md` exist to keep.

## 16. Platform declarations and writer-role timeouts (`0008_platform_declarations_and_writer_timeouts.sql`, Q4 phase WP-1)

Design `docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md` D-1/D-2 (work order
`docs/work-orders/WORK_ORDER_Q4_DB_SIDE_SINGLE_TRUTH_V1.md` WP-1). This
migration moves four things that used to be per-process environment
variables into the platform database itself, as the single state **both**
`r2db_api.main` and `r2db_api.control_main` read at startup.

**Run once, after `0007`, as `r2dbsvc_control` against `r2dbsvc_platform`,
via `ops apply-platform-migration` (R-90 WP-1)** -- required (`--lock-timeout`
is a mandatory argument, never a default) so a re-apply against a running
cluster always bounds how long it may wait behind another session's lock;
idempotent -- safe to re-run, and a re-run resets a hand-changed timeout
back to the shipped default (an assignment, never an increment -- see the
migration's own header), so use `ops set-platform-timeouts` for a real,
lasting change instead. **`0008` is always given together with its own
required successor, `0012` (§18), in the SAME call** -- `0012` widens the
`platform_declarations_key_check` constraint `0008` itself defines, so the
subcommand's own closure check refuses a solo `0008`; giving both here is
always safe, since `0012` is idempotent and does not touch anything `0008`
manages:

```
python -m r2db_api.ops apply-platform-migration \
  0008_platform_declarations_and_writer_timeouts.sql 0012_process_ceilings.sql \
  --lock-timeout <value> --api-role r2dbsvc_api --controlplane-role r2dbsvc_controlplane
```

The two `-v` variables name the service writer roles this file both issues
`ALTER ROLE ... SET` for **and** seeds into the `audit_writer_roles`
declaration row -- from the same variables, in the same transaction, so the
`ALTER ROLE` targets and the declared row can never drift apart. Production
values are the two above; this repository's own tests pass throwaway-prefixed
names through the same variables, which is exactly why the role names are
not hard-coded anywhere in the product code (design D-2(h)).

What it creates:

- `statement_timeout` / `idle_in_transaction_session_timeout` as PostgreSQL
  **role settings** on both writer roles, at the shipped defaults
  `5000ms`/`5000ms` -- **identical to the SESSION-level defaults this phase
  replaces, so applying this migration changes no observable behavior.**
  **Scope note (design §3.11 point 1, ledger LQ4-4), an operator
  responsibility:** `ALTER ROLE ... SET` bounds **every** connection those
  roles make, not only audit writes -- `r2dbsvc_api` is also the credential
  store's read role (`0005`) and `r2dbsvc_controlplane` is also the
  control-plane registry's role (`0006`). 5000ms is generous for the short,
  indexed statements either role issues elsewhere, but if you ever shorten
  these substantially, you are shortening those paths too.
- `r2dbsvc_registry.platform_declarations`, a three-key table
  (`surfaces`, `audit_coalescing_window_ms`, `audit_writer_roles`) with a
  NAMED `CHECK` on `key` and `SELECT` for the two platform roles (writes go
  through the provision DSN only). `audit_coalescing_window_ms` is seeded
  with the shipped default `60000` and `audit_writer_roles` with the two
  role names above; **`surfaces` is deployment-specific and is deliberately
  NOT seeded** -- declare it before first start:

```
python -m r2db_api.ops declare-surfaces \
  --data-base-url https://data.example.invalid/v1 \
  --control-base-url https://control.example.invalid/control/v1
```

Omitting `--control-base-url` entirely -- or passing `--no-control`, the
explicit spelling of that same omission -- declares no control surface;
passing both at once is a usage error (exit 2). Because this is ONE row
shared by both processes, re-declaring without a control surface also
removes it for the control-plane process, which then refuses to start
(F-3c). The other three subcommands, all on `R2DB_CONTROL_DSN`:

```
python -m r2db_api.ops set-platform-timeouts --statement-ms 5000 --idle-ms 5000
python -m r2db_api.ops declare-coalescing-window --ms 60000
python -m r2db_api.ops show-declarations
```

`set-platform-timeouts` places the SAME two values on **every role listed in
`audit_writer_roles`** -- it takes no role-name argument and has no per-role
flag, because the published `visibility_lag_ms` is the max across those
roles anyway. It rejects `0` and negatives (`0` means "no limit" in
PostgreSQL, and an audit writer must never run unbounded).
`show-declarations` prints both the table's rows and each declared role's
own `pg_db_role_setting` entry, which is the one command to run when
something looks inconsistent.

**Every declaration is a startup-time snapshot** (requester ruling U-3):
apply the change, then **restart both processes**. Nothing re-reads the
table per request.

**Restart order matters whenever a timeout VALUE changes** (design §9.2):

- **Shortening either timeout: restart the DATA-plane process first, the
  control process second.**
- **Lengthening either timeout: restart the CONTROL process first, the
  data-plane second.**

The reason is one-directional harm, not symmetry: the reverse order leaves a
window in which the published `visibility_lag_ms` is SHORTER than the bound
the still-old writer connections actually honor, and a consumer that follows
C-09 (wait the declared lag, then poll) silently misses rows it never sees
again. The transient disagreement itself cannot be removed (design §3.11
point 10, ledger LQ4-17) -- only its direction can.

**The four removed environment variables.** `R2DB_AUDIT_STATEMENT_TIMEOUT_MS`,
`R2DB_AUDIT_IDLE_TIMEOUT_MS`, `R2DB_DATA_BASE_URL`, `R2DB_CONTROL_BASE_URL`
are no longer read by either process, and **any one of them still defined --
whatever its value, an empty string included -- makes that process refuse to
start** (F-1 for the two timeouts, F-2 for the two URLs). This is deliberate:
a deployment that copies an old `api.env`/`control.env` forward stops at the
next restart with a message naming the `ops` command to run, rather than
running on with a stale, unread configuration. Remove those lines from
`/etc/r2dbsvc/api.env` and `/etc/r2dbsvc/control.env`
(`deploy/env/{api,control}.env.example` already carry the removal notices).

**Startup fail-fast, in the order the checks run** (design §3.7/§3.8 hold the
verbatim message text; every message names the next command to run):

| # | Condition |
|---|---|
| F-1 / F-2 | a removed env var is defined (timeouts / base URLs) |
| F-8 | `r2dbsvc_registry.platform_declarations` does not exist -- `0008` was never applied to this platform database |
| F-3 / F-3c | no `surfaces` row / a `surfaces` row with no `control` half, in the control-plane process |
| F-4 / F-4b | the window or `audit_writer_roles` row is missing / its value is malformed (validated on every read, because the table can be hand-edited) |
| F-5 | a declared `base_url` fails the shape check (absolute, `/v1` or `/control/v1`, no trailing slash) |
| F-6 | `surfaces.control` and this process' `R2DB_CONTROL_PLANE_STATUS` disagree (data-plane only; the default remedy is to fix the status variable, since re-declaring would break the control process) |
| F-13 | this connection's `current_user` is not one of the declared `audit_writer_roles` |
| F-7 / F-10 / F-11 / F-9 | the role setting is absent / is `0` or negative / is overridden by an `ALTER ROLE ... IN DATABASE ...` row carrying either timeout key / disagrees with this connection's actual effective value |

**What this does NOT verify -- two limits, both real:**

1. **That both processes read the same platform database is not checked by
   either of them** (design §3.11 point 7, ledger LQ4-16). Neither knows the
   other's DSN. Hand the control process a stale `R2DB_CONTROLPLANE_DSN`
   pointing at an old platform database and the pre-Q4 `surfaces` /
   `visibility_lag_ms` drift returns in exactly its old shape. **Diffing the
   two capability documents' `surfaces` after any change remains a required
   post-deploy check** (`docs/work-orders/DEPLOY_Q4_20260905.md` §4-1).
2. **A process effective-checks only its own role, and only at startup**
   (design §3.11 point 9, ledger LQ4-15). The control process reads
   `r2dbsvc_api`'s catalog entry -- that is where half the declared lag comes
   from -- but cannot observe that role's effective value; only the
   data-plane process can, on its own next start. And connections a pool
   opens after startup are not re-checked, which matters under a connection
   pooler; whether this deployment has one in front of PostgreSQL is not
   recorded here.

Reading both roles' declared settings by hand is still useful at deploy time,
and is the one place both are visible together:

```
psql "$R2DBSVC_CONTROL_DSN" -c "SELECT r.rolname, s.setconfig FROM pg_db_role_setting s JOIN pg_roles r ON r.oid = s.setrole WHERE s.setdatabase = 0"
```

## 17. Per-application platform-upgrade ledger and bulk apply (revised `0003` + `0009_platform_upgrades_ledger_upgrade.sql`, Q4 phase WP-3)

Design `docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md` D-3/D-4/D-5 (work order
WP-3). Every application database now carries its own ledger table,
`public._r2db_platform_upgrades`, recording which of this package's
per-application upgrade scripts have been applied to it. This peer currently
ships exactly one such script, `0009`, so the complete set is `{9}`.

- **A freshly provisioned application already has it**: `0003` (§5 step 3)
  creates the ledger and seeds every number this package ships. Nothing extra
  to do when onboarding.
- **An application provisioned before this WP shipped needs the retrofit**,
  which is what `0009` is for -- and the way to run it is `ops`, not a
  hand-run script per database:

```
# Preview: applies nothing, reports applied/pending per application.
R2DB_MIGRATIONS_DIR=<MIGRATIONS_DIR> python -m r2db_api.ops upgrade-applications --lock-timeout <value> --dry-run

# Apply. Visits every registered application; one failure does not stop the
# rest -- failed applications are listed at the end with a cleanup line.
R2DB_MIGRATIONS_DIR=<MIGRATIONS_DIR> python -m r2db_api.ops upgrade-applications --lock-timeout <value>
```

`--lock-timeout <value>` is required (design D-7; no default) -- a positive
integer optionally followed by `ms`/`s`/`min`, applied as the psql session's
own `lock_timeout` for each per-application upgrade script it runs.

`R2DB_MIGRATIONS_DIR=<MIGRATIONS_DIR>` (pointing at this package's `migrations/`
directory) is required whenever `r2db-api` was installed non-editable into a
venv (`pip install -c constraints.txt <install root>`, `constraints.txt` at
the repository root of the same checkout/`git archive` extraction -- R-19;
`part1_provision_host_and_db.sh`'s own Step 2 install command does this
itself, failing fast if `constraints.txt` is not found there first) --
`ops`'s own default migrations-directory resolution assumes a
source checkout layout and does not find the migrations directory in that
case (`r2db_api.ops._migrations_dir`'s own comment). Omit it only when
running against an editable/source checkout, where the default resolution
already finds it.

`--application <slug>` limits either form to one application. `enabled` does
**not** affect which applications are targeted -- a disabled application's
database is brought current too, so re-enabling it later never surfaces a
stale ledger. Both commands run on `R2DB_CONTROL_DSN` (the provision role);
no API process holds that DSN (`security/CONTROL_MAPPING.md` SI-02 row).

Exit codes: `0` nothing pending, `1` enumeration failed (registry/provision
DSN unreachable), `2` usage error (unknown `--application`, a `--script`
file that does not exist, a script number this package does not ship), `3`
at least one application failed to apply, `4` (`--dry-run` only) at least one
application still has a pending upgrade.

**If an application fails to apply**: the upgrade script's own ritual grants
`r2dbsvc_control` a *temporary* membership in that application's developer
role and revokes it at the end of a successful run; a failed run never
reaches that closing `REVOKE`, so the output for a failed application
includes the exact statement to issue by hand on the provision DSN, of the
form:

```sql
REVOKE "<that application's developer role>" FROM "r2dbsvc_control";
```

Issue it after diagnosing and fixing the failure, then re-run
`upgrade-applications` for that application. Leaving it unrevoked crosses no
boundary SI-02/SI-12 draws (the provision role can already reach every
application database), but it does defeat the existing ritual's intent that
the membership is temporary, and repeated failures accumulate (design §3.11
point 8, ledger LQ4-14).

**Read-only status** (provision DSN only, writes nothing):

```
python -m r2db_api.ops upgrade-status
python -m r2db_api.ops upgrade-status --application myapp
```

It reports `applied` / `pending` / `database_name` per application (an
application with no ledger table at all reports `applied: []`; one whose
provisioning never finished reports a NULL `database_name` and every number
pending). Exit codes `0`/`4` mirror `--dry-run`. **This is the ONLY
visualization of per-application upgrade state** (requester ruling U-1,
design §5): deliberately not exposed on any HTTP surface, and `list-apps` is
unchanged. Run it as part of every deploy's pre-flight, the same way
`show-declarations` is.

**Data-plane enforcement, disclosed for context (no operator action).** From
this WP on, the data-plane process reads the ledger when it opens an
application's storage boundary and compares it against the set this package
ships. If a number is missing -- including the case where the ledger table
does not exist at all -- **that application's cell refuses every request with
`SERVICE_UNAVAILABLE`, and the response names the missing upgrade number(s)
and `ops upgrade-applications`** (F-12; the runtime role holds `SELECT` on
the ledger for exactly this check, requester ruling U-2). **The process still
starts, every other served application still serves normally, and
`/v1/capabilities` is unaffected** (supervisor ruling 2026-09-05, review
H-1): only the lagging application's own cell refuses, until the upgrade is
applied **and the process is restarted** (the check is a cell-open snapshot,
like every other declaration in this phase). The startup log carries the same
F-12 line, so a missed upgrade is visible without waiting for a client to
report it.

**Recovery from an F-12 refusal**, start to finish:

1. `python -m r2db_api.ops upgrade-status --application <slug>` -- confirm
   which numbers are pending (exit 4 means at least one is).
2. `R2DB_MIGRATIONS_DIR=<MIGRATIONS_DIR> python -m r2db_api.ops upgrade-applications
   --application <slug> --lock-timeout <value> --dry-run`, then the same
   command without `--dry-run` (see the `R2DB_MIGRATIONS_DIR` note above --
   required for a non-editable install).
3. If it exits 3, read the failure block: fix the cause, issue the printed
   `REVOKE`, re-run step 2.
4. `sudo systemctl restart r2dbsvc-api.service` -- the check is a cell-open
   snapshot, so the refusing cell keeps refusing until the process restarts.
5. Re-check with any ordinary request against that application, and with
   `ops upgrade-status` (expect exit 0).

**When you ship the next per-application upgrade script** (design §9.4): name
it `NNNN_<name>_upgrade.sql`, wrap its body after `\c` in one transaction,
make it idempotent, give it no `\q` skip path, record its own number in the
ledger with `INSERT ... ON CONFLICT DO NOTHING` as the last statement, and
add that number to BOTH the `0003` template's seed list and the package
constant, in the same commit. A static test holds those three sets equal, so
forgetting one of them fails CI instead of shipping a deployment whose
cell-open check silently does not require the new number.

## 18. `process_ceilings` (`0012_process_ceilings.sql`, Phase 10 WP-6a)

Design `docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md` D-5(ii)/(iii) (work
order `docs/work-orders/WORK_ORDER_PHASE10_DEPLOYMENT_EVIDENCE_V1.md`
WP-6a). Contract 1.8.0 defines `limit_enforcement`'s scope as **the
deployment reachable at a plane's declared `surfaces` base URL**, never one
process alone -- `process_ceilings` is the deployer's own declaration of how
many processes may serve that base URL at the same time, and is what
`limit_enforcement` is computed from at every startup.

**Mechanism -- same as `surfaces`/§16 above:** a single-source declaration
table (`r2dbsvc_registry.platform_declarations`), written only through `ops`
against the provision DSN, read at startup by both processes, and validated
by the identical Python function on both the write path and every read
path. `0012` is a SEPARATE platform single-shot migration from `0008` (§16)
-- it only widens `platform_declarations_key_check` (a closed, named
`CHECK`) to admit the new key; it does not touch role settings, timeouts, or
the `surfaces`/`audit_coalescing_window_ms`/`audit_writer_roles` rows `0008`
already manages.

**Normally applied together with `0008` in the SAME §16 run** (`0008`'s own
required successor). The solo invocation below, as `r2dbsvc_control`
against `r2dbsvc_platform` via `ops apply-platform-migration` (R-90 WP-1),
is for drift recovery (re-converging a hand-dropped
`platform_declarations_key_check`) and the existing-host rollout procedure
below ONLY -- both run against a platform where `0008` is already applied,
so the closure check (which only fires when `0008` itself is part of the
SAME call) never rejects a solo `0012` (idempotent -- safe to re-run, takes
no `-v` variables):

```
python -m r2db_api.ops apply-platform-migration 0012_process_ceilings.sql --lock-timeout <value>
```

Like `surfaces`, `0012` deliberately seeds NO `process_ceilings` row
(deployment-specific) -- declare it before either process's next start:

```
python -m r2db_api.ops declare-process-ceilings --data 1 --control 1
```

`--data`/`--control` are each the maximum number of processes that may serve
that plane's `surfaces` base URL at the same time, and must each be a
positive integer. **`--data` is `api.env`'s `R2DB_WORKERS`** -- the number
of uvicorn workers `r2dbsvc-api.service` starts (`--workers
${R2DB_WORKERS}`) -- **and `--control` is 1** (`R2DB_CONTROL_WORKERS=1`,
`DEPLOYMENT_RUNBOOK.md` §8). `part1_provision_host_and_db.sh` declares
`1`/`1`, matching `R2DB_WORKERS=1`; re-declare `--data` whenever
`R2DB_WORKERS` changes. Every process that serves a base URL runs on one
host (`DEPLOYMENT_RUNBOOK.md` §8) -- see "What changes when you raise a
ceiling above 1" below.

**Required upgrade order for an EXISTING host** (ledger LQ4-24: the same gap
`0008`+`ops declare-surfaces` closed for `surfaces` in §16 re-opens for
`process_ceilings` -- a script-provisioned host upgraded to a `r2db_api`
release that requires `process_ceilings` (this one) must run these three
steps, in this exact order, before restarting either process, or both will
refuse to start (F-15) with no `process_ceilings` row to read yet):

1. `python -m r2db_api.ops apply-platform-migration 0012_process_ceilings.sql --lock-timeout <value>`
2. `python -m r2db_api.ops declare-process-ceilings --data <R2DB_WORKERS> --control 1`
3. Restart both `r2dbsvc-api.service` and `r2dbsvc-control.service` --
   **every declaration in this phase is a startup-time snapshot** (requester
   ruling U-3, unchanged from §16): nothing re-reads the table per request.

**Startup fail-fast**: F-15 -- the `process_ceilings` row is missing, or its
value is not a JSON object with exactly the two positive-integer keys
`data`/`control`. The message names the `ops declare-process-ceilings`
command to run. `ops verify-declarations` reports this as `F-15`, exit code
`14`.

**What `process_ceilings` actually changes.** `GET /v1/capabilities` and
`GET /control/v1/capabilities` both report `limit_enforcement` per class,
computed from the DECLARED ceiling, not from any live process count this
deployment cannot observe from inside a single process:

- `requests_per_minute` (data-plane) -- counted in the platform-database
  row every data-plane worker shares (`0015`, §20): `enforced` at any
  declared ceiling.
- `concurrency` (data-plane) -- held by the host-shared slot directory
  (`R2DB_SLOT_DIR`, `DEPLOYMENT_RUNBOOK.md` §8): `enforced` only while
  `process_ceilings.data` EQUALS `R2DB_WORKERS`; a larger ceiling is read
  as processes on another host, whose slots are not shared, and answers
  `deployment_required`. A ceiling below `R2DB_WORKERS` stops startup.
- `control_requests_per_minute`/`audit_requests_per_minute`
  (control-plane) -- in-memory, per-process windows: `enforced` while
  `process_ceilings.control` is `1`, `deployment_required` once it is `2`
  or more (contract 1.8.0's own enforcement-scope definition: a
  per-process bound is `enforced` for the WHOLE deployment only while
  exactly one process may serve that plane's base URL).
- `applications`/`credentials_per_application` (control-plane) -- bound in
  PostgreSQL under a same-transaction table lock: `enforced` regardless of
  the declared ceiling. `idempotency_entries` (data-plane) is also bound
  in PostgreSQL and also `enforced` regardless of the declared ceiling,
  but its own count lock is out of this WP's scope (WP-6d-i, both peers,
  supervisory ruling 2026-09-08) -- not yet added as of this document.
- Every other class (`request_bytes`, `batch_items`, `result_items`,
  `query_complexity`, `execution_ms`, `schema_objects`, `operation_depth`,
  `enum_members`, `idempotency_retention_ms`) is request-scoped and
  unaffected by `process_ceilings` either way.

**What this does NOT verify (same limit as §16's own two, extended here):**
neither process can observe how many instances of itself, or of the sibling
plane, are actually running behind the declared base URL -- the declared
ceiling and the real process topology are an operator responsibility, kept
in agreement by deployment discipline (runbook + a post-deploy check), not
by anything either process can check from inside itself.

**What changes when you raise a ceiling above 1.** Declaring `--data` equal
to a larger `R2DB_WORKERS` keeps both data-plane classes `enforced` and
raises the F-16/F-18 floors with it (§20). Declaring `--data` ABOVE
`R2DB_WORKERS` is honest, not silently unsafe:
`limit_enforcement.concurrency` reports `deployment_required` instead of
`enforced`, telling a client that the host-shared slots may not cover every
process behind the base URL; `requests_per_minute` stays `enforced`.
Declaring `--control 2` or higher makes the two control-plane windows
report `deployment_required` and raises the control roles' F-16 floors
(§20). The honest declaration is the entire point.

## 19. `r2dbsvc_auditreader`'s own `statement_timeout` (`0014_auditreader_statement_timeout.sql`, R-56)

Design `docs/design/R2DB_AUDIT_READER_STATEMENT_TIMEOUT_V0_1.md` D-1/D-4
(work order `docs/work-orders/WORK_ORDER_R56_R2DB_AUDIT_READER_TIMEOUT_V1.md`).
Bounds the reader role's own statements (an operator's interactive `psql`
session included, not only `r2db_api.control_main`'s own pooled
connections) to `5000ms` -- the same number the two writer roles already
carry (§16).

**Run once, after `0007`, as the role that created `r2dbsvc_auditreader`**
(normally `r2dbsvc_control`), via `ops apply-platform-migration` (R-90 WP-1,
`--lock-timeout` required); idempotent -- safe to re-run, takes no `-v`
variables:

```
python -m r2db_api.ops apply-platform-migration 0014_auditreader_statement_timeout.sql --lock-timeout <value>
```

**Role settings take effect at login, not on an already-open connection.**
`r2db_api.control_main`'s own reader pool holds connections open for the
life of the process and never re-reads role settings on one already open.
**Order of operations, in this exact sequence:**

1. Apply `0014` (above).
2. Restart the control process (`r2dbsvc-control.service`) -- the only
   process that opens connections with this role's DSN
   (`R2DB_AUDIT_DSN`) -- so every open reader connection is replaced by
   one that actually carries the new value.
3. Run `python -m r2db_api.ops verify-declarations` with `R2DB_CONTROL_DSN` set
   to `r2dbsvc_api`'s DSN (a declared writer role; as `r2dbsvc_control` the run stops at `FAIL F-13` first, §21) and read the `F-17` line.

**On an existing deployment, `ops verify-declarations` reports `FAIL F-17`
(exit code 16) until `0014` has been applied.** This is the intended
signal, not a regression: the check makes machine-readable a gap that
already existed (an audit reader with no statement-level bound) rather
than one this migration introduces. Applying `0014` and restarting the
control process (steps 1-2 above) clears it.

**What `F-17` checks and does not check.** `ops verify-declarations`
identifies the auditreader role by its actual grants (`SELECT` on both
`application_audit` and `control_audit`, same as §4's connection-limit
check) and reads its role-level `pg_db_role_setting` entry over the
CONTROL DSN -- it never opens a connection with the reader's own DSN, so
it confirms the **declaration** is a positive value with no per-database
override, not that a currently-running process' own connections have
actually picked it up (that is what step 2's restart is for). A platform
with no auditreader role at all (`0007` not yet applied) is not flagged.

**ADMIN OPTION precondition.** Like every other `ALTER ROLE ... SET`
migration in this set, `0014` succeeds only when run as the role that
created `r2dbsvc_auditreader` (CREATEROLE's own implicit ADMIN OPTION on
a role it created) -- normally `r2dbsvc_control`, since `0007` is what
creates that role. If a different role created it on this cluster, grant
ADMIN OPTION explicitly first (`GRANT r2dbsvc_auditreader TO
r2dbsvc_control WITH ADMIN OPTION`, run as a role that already holds it),
or `0014` fails and rolls back entirely (its own `BEGIN`/`COMMIT`).

## 20. Multi-process data plane: the shared rate row (`0015_credential_request_rate.sql`) and the connection budget

Design `docs/design/MULTI_PROCESS_WORKER_V0_1.md` D-3 (1) and (5). The
data plane runs `R2DB_WORKERS` uvicorn workers on one host
(`r2db-api/deploy/DEPLOYMENT_RUNBOOK.md` §8); this section covers what that
means for the platform database.

**`0015` -- the credential-keyed `requests_per_minute` row.** Creates
`r2dbsvc_registry.credential_request_rate` (one row per credential) and the
function `r2dbsvc_registry.credential_request_rate_admit`, and grants
`r2dbsvc_api` `SELECT`/`INSERT`/`UPDATE` on the table and `EXECUTE` on the
function -- nothing to any other role. Every data-plane worker counts an
authenticated request with one autocommit statement on its own platform
pool (the `r2dbsvc_api` role), after authentication, so every worker
shares one count per credential; unauthenticated requests never reach the
table. A database failure on that statement refuses the request, the same
way as any other platform-database failure -- it never lets the request
through uncounted. Rows go away with their credential (`ON DELETE
CASCADE`). Run it as `r2dbsvc_control` against `r2dbsvc_platform`, after
`0005` (it references `credentials`); idempotent, no `-v` variables:

```
python -m r2db_api.ops apply-platform-migration 0015_credential_request_rate.sql --lock-timeout <value>
```

`part1_provision_host_and_db.sh` applies it on a host it provisions. On a
platform database without its rate function, the application-plane
process and its preflight refuse to start, naming the migration -- apply
it before starting a release that counts in it.

**Window shape (disclosure).** The row keeps one count per integer second
for the current second and the 60 before it (`int[61]`, a ring indexed by
the second modulo 61), anchored to the database clock (`clock_timestamp()`),
so the workers' own clocks never enter the window, and its base second only
moves forward. At a window edge it may count up to one second more than
60 s: it may refuse a request slightly early, and it never admits more than
the declared `requests_per_minute`.

**Connection budget -- counted from the thread limit.** One worker never
has more requests using the database at once than its thread limit
(`R2DB_THREAD_LIMIT`, default 4), so every pool of one worker is sized
`p = R2DB_THREAD_LIMIT + 2` (`role_pool_size`; `p = 6` by default): the
credential store and the durable audit sink (both `r2dbsvc_api`), and each
served application's runtime and developer pool. The declared
`concurrency` is not part of the budget -- a slot holds a file lock, not a
connection. The control process computes the same data-plane terms for its
own startup F-16/F-18 checks from `R2DB_THREAD_LIMIT` in `control.env`, so
keep that value equal to `api.env`'s (both unset, the default 4, is equal).
With `W = process_ceilings.data` (equal to `R2DB_WORKERS`) and
`C = process_ceilings.control` (1):

| Role | F-16 floor (startup and `verify-declarations`) | At `p = 6` | Limit this set ships (`0013`; auditreader `0007`) | Largest count that fits |
| --- | --- | --- | --- | --- |
| `r2dbsvc_api` | `2 × p × W` | `12 × W` | 68 | `W` ≤ 5 |
| each `<slug>_runtime` / `<slug>_developer` | `p × W` | `6 × W` | 36 | `W` ≤ 6 |
| `r2dbsvc_controlplane` | `16 × C` | `16 × C` | 20 | `C` = 1 |
| `r2dbsvc_auditreader` | `4 × C` | `4 × C` | 5 | `C` = 1 |

F-18 (startup and `verify-declarations`, cluster-wide) judges the lower
bound `W × (2p + 2p) + C × 16` once at least one application is registered
(`W × 2p + C × 16` with none) plus `superuser_reserved_connections` plus
`reserved_connections` against `max_connections`. At `p = 6`: `24 × W + 16`
(`12 × W + 16` with no application registered) -- 40 at `W = 1`, 112 at
`W = 4` (64 with no application registered).

So at the default thread limit, `R2DB_WORKERS` up to 5 fits the role limits
`0013` sets. A larger count, or a raised `R2DB_THREAD_LIMIT`, needs a
higher `CONNECTION LIMIT` than `0013` sets on the roles the table names --
for a deployed platform, a new platform migration; F-16 stops startup
naming the role, its current limit and the exact floor it needs. `0013` sets fixed values (`ALTER ROLE ... CONNECTION LIMIT`), so
applying it again returns a raised limit to them. Every figure here
assumes the unit is restarted with stop and start, never SIGHUP
(`DEPLOYMENT_RUNBOOK.md` §8): SIGHUP runs `R2DB_WORKERS + 1` workers for a
while, outside these floors.

**`process_ceilings.control` of 2 or more** needs a `CONNECTION LIMIT` of at
least `16 × process_ceilings.control` on `r2dbsvc_controlplane` and at
least `4 × process_ceilings.control` on `r2dbsvc_auditreader`; F-16 reports
the exact floor it needs, naming the role. `0013`'s 20 and `0007`'s 5 cover
one control process only.

## 21. Refusal-window counter (`0016_denial_window_counter.sql`)

Design `docs/design/AUDIT_PROCESS_LOSS_V0_1.md` §5. Creates
`r2dbsvc_registry.denial_window_counter` (one row per refusal key and
window) and the function `r2dbsvc_registry.denial_window_record`, which runs
as its owner (`SECURITY DEFINER`, `search_path` pinned). `r2dbsvc_api` gets
`EXECUTE` on the function and nothing on the table, `r2dbsvc_auditreader`
gets `SELECT` on the table, and `PUBLIC` gets neither. Both objects are owned
by the schema's owner role (`r2dbsvc_control`) whichever role runs the file.
Every data-plane worker counts a refusal with one autocommit call on its own
platform pool before the refusal's response is returned; if that call
fails, the refusal is answered `SERVICE_UNAVAILABLE` instead. `audit_query`
reads the counter rows of closed windows as summary events. Capacity:
§15.1.

Run it as `r2dbsvc_control` against `r2dbsvc_platform`, after `0007` (it
references `application_audit` and `r2dbsvc_auditreader`); idempotent, no
`-v` variables:

```
python -m r2db_api.ops apply-platform-migration 0016_denial_window_counter.sql --lock-timeout <value>
```

`part1_provision_host_and_db.sh` applies it on a host it provisions, right
after `0015`. On a platform database without the function, or with one not
in the state the file leaves it in, the application-plane process and its
preflight refuse to start, naming the migration (F-21) -- apply it before
starting a release that counts in it. The file adds new objects only and
changes no existing one, so a release that predates it keeps running on the
migrated database.

**Locks.** The first application locks only the objects it creates; a
re-application takes ACCESS EXCLUSIVE on `denial_window_counter` until its
`COMMIT` (fact: a read of the applying session's own `pg_locks` just before
`COMMIT`, on a PostgreSQL 16 throwaway cluster; the statement that takes it
is, by inference, the `ALTER TABLE ... OWNER TO`). While it waits and holds,
every refusal a release that counts in the table records, and every
`audit_query` read of the table, waits up to `--lock-timeout` plus that hold
-- and, while every thread of a worker waits on such a refusal, every other
request of that worker. `--lock-timeout` is required with no default, as
for `0015` (§20) and every other `apply-platform-migration` run (§16): it
bounds how long the run waits behind another session's lock, and so how
long requests queued behind that wait are held; choose it the same way as
for `0015`.

**Check it with `ops verify-declarations` and read the `F-21` line.** The
command reaches F-21 only over the DSN of a declared audit writer role; run
as `r2dbsvc_control` it stops earlier, at `FAIL F-13` (exit 11). Pass
`r2dbsvc_api`'s DSN for this one invocation:

```
R2DB_CONTROL_DSN=<DSN of r2dbsvc_api> python -m r2db_api.ops verify-declarations
```

Before the migration the run ends `FAIL F-21` (exit 20), naming the
migration; after it, `OK F-21` and exit 0. F-21 checks the state the file
leaves: the function is `SECURITY DEFINER` with `search_path` pinned and not
executable by `PUBLIC`, it and the table are owned by the schema's owner,
every role that writes `application_audit` may `EXECUTE` it, no runtime role
holds a direct privilege on the table, and every role that reads both audit
tables may `SELECT` it.
