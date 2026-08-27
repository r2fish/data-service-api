-- r2db-api PostgreSQL provisioning -- 0003: provision one application
-- (database-per-application, architecture §8 "D-3 改訂")
--
-- WHO RUNS THIS: the operator/deploy tooling, connected to the
-- `r2dbsvc_platform` database as `r2dbsvc_control`, once per application
-- being onboarded (run 0001 and 0002 first, exactly once each):
--
--   psql "$R2DBSVC_CONTROL_DSN" -v app_slug='myapp' \
--     -v runtime_password="$(openssl rand -base64 32)" \
--     -v developer_password="$(openssl rand -base64 32)" \
--     -f 0003_provision_application.sql
--
-- Record the two generated passwords in your secret manager immediately --
-- nothing in this flow returns or stores them in recoverable form.
--
-- WHAT "PROVISIONING ONE APPLICATION" MEANS NOW (design D-3's three layers,
-- restated for database-per-application):
--   1. namespace   -- one PostgreSQL *database*, `r2dbsvc_app_<slug>`, whose
--                     `public` schema is owned by that application's own
--                     developer role. This is the primary wall (§8.5
--                     condition 1): with no schema-per-application FDW/
--                     dblink path between databases, cross-application
--                     access is not a permission this file might forget to
--                     revoke somewhere -- it does not exist as a SQL
--                     operation at all once `CONNECT` on the wrong database
--                     is refused.
--   2. privilege    -- two login roles: `..._runtime` (DML only, no CREATE
--                     on `public`) and `..._developer` (owns `public`, so
--                     it can DDL there; still NOSUPERUSER / NOCREATEDB /
--                     NOCREATEROLE). Neither role is ever granted `CONNECT`
--                     on any database but its own two-role application's
--                     (§8.5 condition 1).
--   3. RLS          -- kept as the secondary wall (§8.5 condition 3),
--                     applied by `PostgresCell._create_entity` (application
--                     code) to every table it creates at request time, the
--                     same as before this revision. See this file's next
--                     comment block for why the event-trigger alternative
--                     (§8.5 condition 3(a)) is not used, and what this file
--                     installs instead ((b): the `_r2db_missing_rls`
--                     verification view).
--
-- WHY THIS IS A SCRIPT, NOT A SINGLE FUNCTION CALL: see
-- `0002_provisioning_functions.sql`'s header. `CREATE DATABASE` cannot run
-- inside a transaction block (which every plpgsql function body implicitly
-- is), and setting up the new database's `public` schema requires actually
-- being connected to it (`\c` below opens a new physical connection -- one
-- session cannot switch databases mid-connection). 0002's
-- `begin_provision_application`/`finish_provision_application` bracket this
-- script: the former validates and creates the two login roles
-- (transactional, safe as a function); the latter records the finished
-- application in the registry only once every step below has succeeded, so
-- a crash partway through never leaves the registry believing an
-- incompletely-provisioned application is ready.
--
-- RLS AUTOMATION (§8.5 condition 3): OPTION (A) WAS INVESTIGATED AND
-- REJECTED. Option (a) -- a `CREATE EVENT TRIGGER` in a template database,
-- so `CREATE DATABASE ... TEMPLATE` propagates it to every application
-- database, applying RLS automatically to every future `CREATE TABLE` with
-- no runtime code involved -- was evaluated against this file's own stated
-- constraint (`migrations/0001_*` is "run by a cluster administrator", not
-- necessarily by a literal PostgreSQL superuser: 0001's own header
-- documents the administrator as "an existing superuser, OR a role with
-- CREATEROLE and CREATEDB"). `CREATE EVENT TRIGGER` has no
-- ownership/grant-based delegation path in PostgreSQL at all -- unlike
-- table/schema/function privileges, it is unconditionally superuser-only,
-- with no `GRANT`, no role membership, and no way to make a CREATEDB+
-- CREATEROLE-but-not-superuser administrator sufficient. Since 0001
-- explicitly allows onboarding this whole footprint without ever obtaining
-- true superuser, requiring one specifically for event-trigger creation
-- would introduce a strictly stronger operational precondition than
-- anything else in this migration set needs, on a target (the existing VPS,
-- §5.3) where that precondition is not confirmed to hold. Depending on it
-- would also make RLS automation itself only as trustworthy as "did whoever
-- ran 0001 happen to have superuser that day" -- exactly the kind of
-- silent, unverified assumption CLAUDE.md's Security Invariants section
-- asks this project not to paper over.
--
-- OPTION (B) IS WHAT THIS FILE INSTALLS INSTEAD: `PostgresCell._create_entity`
-- keeps enabling+forcing RLS at table-creation time (unchanged), but this
-- script additionally creates a verification view,
-- `public._r2db_missing_rls`, inside every application's own database --
-- so "is RLS actually enabled+forced on every table in this database right
-- now" is answered by a real query against live catalog state, not by
-- trusting that every code path which ever creates a table remembered to
-- ask for it. `r2db_api.postgres.PostgresCell.verify_row_level_security()`
-- runs the equivalent check from the application side (and `_create_entity`
-- calls it, in the same transaction, after every table it creates -- so a
-- future bug in the RLS-enabling code itself is caught before the
-- transaction can commit, not discovered later by an operator). Both are
-- exercised by `r2db-api/tests/test_postgres.py`.

\set ON_ERROR_STOP on

SELECT * FROM r2dbsvc_registry.begin_provision_application(:'app_slug', :'runtime_password', :'developer_password') \gset

-- `CREATE DATABASE` -- a plain top-level statement (see this file's header:
-- no function, no transaction block). No `OWNER` clause: it defaults to the
-- executing role (`r2dbsvc_control`), matching how `0001` creates
-- `r2dbsvc_platform` the same way. `TEMPLATE template0` avoids inheriting
-- any accumulated customisation of `template1` on this cluster, the same
-- reasoning `0001` already applied to the platform database.
CREATE DATABASE :"database_name" TEMPLATE template0 ENCODING 'UTF8';

-- §8.5 condition 1, the primary wall: a newly created PostgreSQL database
-- grants `CONNECT` to `PUBLIC` by default. Close that immediately, then
-- grant `CONNECT` only to this application's own two roles. From this
-- point on, no role outside this pair -- including every *other*
-- application's runtime/developer roles -- can even open a connection to
-- this database; `r2db-api/tests/test_postgres.py::
-- test_cross_database_connect_is_refused_at_the_database_level` verifies
-- this directly, with a raw `psycopg.connect`, not through `PostgresCell`.
REVOKE CONNECT ON DATABASE :"database_name" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"database_name" TO :"runtime_role";
GRANT CONNECT ON DATABASE :"database_name" TO :"developer_role";

-- Reconnect to the new database itself. `r2dbsvc_control` can do this even
-- though `PUBLIC`'s default `CONNECT` was just revoked above, because it
-- owns this database (object owners implicitly hold every privilege on
-- their own object, bypassing ACL checks -- the same reason it does not
-- need an explicit `CONNECT` grant on `r2dbsvc_platform` either).
\c :database_name

-- §8.5 condition 2: close `public`'s default privileges, same as `0001`
-- does for the platform database. At this instant `r2dbsvc_control` still
-- implicitly owns `public` too (PostgreSQL 15+: a freshly created
-- database's `public` schema is owned by the pseudo-role
-- `pg_database_owner`, which resolves to whoever owns the *current*
-- database -- `r2dbsvc_control`, until the `ALTER SCHEMA ... OWNER TO`
-- below hands it to the developer role). Order matters here: the `GRANT
-- USAGE` below must run *before* ownership moves to the developer role, or
-- `r2dbsvc_control` would no longer have authority to grant anything on
-- this schema at all.
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO :"runtime_role";

-- `r2dbsvc_control` needs the `SET` option on the developer role *before*
-- it can either (a) transfer `public`'s ownership to it, below, or (b)
-- assume it via `SET LOCAL ROLE` further down: PostgreSQL 16 hardened
-- ownership transfer specifically so that changing an object's owner TO a
-- role now requires the grantor to already be able to `SET ROLE` to that
-- role, not merely to hold `ADMIN OPTION` on it (which is all `CREATE
-- ROLE` grants its creator automatically -- confirmed empirically while
-- writing this file: attempting the `ALTER SCHEMA ... OWNER TO` below
-- before this grant fails with `must be able to SET ROLE "..."`). This
-- membership is granted immediately before it is needed and revoked
-- immediately after (`REVOKE ... FROM CURRENT_USER` below), so
-- `r2dbsvc_control` never holds standing membership in any application's
-- developer role between provisioning runs.
GRANT :"developer_role" TO CURRENT_USER WITH SET TRUE;

-- `public` schema ownership -- and therefore all future DDL authority in
-- it -- moves to the developer role now. This *is* the developer role's
-- schema-changing authority (SI-03), scoped to exactly this one
-- application's database and reaching no other application's database at
-- all (there is no cross-database ownership/grant relationship in
-- PostgreSQL to misconfigure).
ALTER SCHEMA public OWNER TO :"developer_role";

-- Everything from here through `REVOKE ... FROM CURRENT_USER` below
-- creates objects *inside* `public`, which now requires owner-level
-- privilege -- so it runs as the developer role itself (`SET LOCAL ROLE`,
-- scoped to this one transaction, using the `SET` option just granted
-- above).

BEGIN;
SET LOCAL ROLE :"developer_role";

-- Schema-revision bookkeeping table, created directly here (not left to
-- application code) so every provisioned application starts at revision 0
-- with its RLS policy already in place, matching the pattern
-- `PostgresCell._create_entity` uses for entity tables it creates later.
CREATE TABLE public._r2db_schema_revision (
    id boolean PRIMARY KEY DEFAULT TRUE,
    revision bigint NOT NULL DEFAULT 0,
    CONSTRAINT _r2db_schema_revision_singleton CHECK (id)
);
INSERT INTO public._r2db_schema_revision (id, revision) VALUES (TRUE, 0);
ALTER TABLE public._r2db_schema_revision ENABLE ROW LEVEL SECURITY;
ALTER TABLE public._r2db_schema_revision FORCE ROW LEVEL SECURITY;
CREATE POLICY schema_revision_application_isolation ON public._r2db_schema_revision
    USING (current_user IN (:'runtime_role', :'developer_role'))
    WITH CHECK (current_user IN (:'runtime_role', :'developer_role'));
GRANT SELECT, UPDATE ON public._r2db_schema_revision TO :"runtime_role";

-- From here on, any table the developer role creates in `public` (i.e.
-- every entity table `PostgresCell.apply_schema`'s `create_entity` path
-- creates at request time) automatically grants the runtime role DML --
-- and only DML, never DDL -- the moment it exists, with no per-table grant
-- statement required from the application process.
ALTER DEFAULT PRIVILEGES FOR ROLE :"developer_role" IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :"runtime_role";

-- §8.5 condition 3(b) -- see this file's header. A live view, not a
-- point-in-time claim: querying it always reflects the database's current
-- catalog state, so it catches RLS having been disabled or never enabled
-- on any table by any means, not just ones `PostgresCell` created.
-- `_r2db_schema_revision` (created above, already RLS-protected) is
-- excluded the same way `PostgresCell._load_catalog` excludes it from the
-- application-visible catalog.
CREATE VIEW public._r2db_missing_rls AS
    SELECT c.relname AS table_name
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relkind = 'r'
      AND c.relname <> '_r2db_schema_revision'
      AND (c.relrowsecurity = false OR c.relforcerowsecurity = false);
GRANT SELECT ON public._r2db_missing_rls TO :"runtime_role";

COMMIT;
-- `SET LOCAL ROLE` above reverted automatically at `COMMIT`; the temporary
-- membership itself is revoked explicitly below rather than left to accrue.
REVOKE :"developer_role" FROM CURRENT_USER;

-- Reconnect to the platform database to record the now-complete
-- application in the registry. `psql`'s `\c` has no "go back" form (it
-- only remembers the *current* connection's parameters, and the first
-- `\c` above already overwrote those), so the platform database name is
-- named again explicitly here -- literally, matching how `0001`/`0002`
-- name it, so the test harness's textual `r2dbsvc` -> throwaway-prefix
-- substitution (see `r2db-api/tests/test_postgres.py`) rewrites this
-- occurrence identically to every other one in this migration set.
\c r2dbsvc_platform
SELECT r2dbsvc_registry.finish_provision_application(:'app_slug', :'database_name', :'runtime_role', :'developer_role');
