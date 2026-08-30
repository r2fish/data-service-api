-- MitateDB-api PostgreSQL provisioning -- 0003: provision one application
-- (database-per-application, R-1)
--
-- WHO RUNS THIS: the operator/deploy tooling, connected to the
-- `mitatedb_platform` database as `mitatedbsvc_provision`, once per
-- application being onboarded (run 0001 and 0002 first, exactly once
-- each):
--
--   psql "$MITATEDBSVC_PROVISION_DSN" -v app_id='acme' \
--     -v runtime_password="$(openssl rand -base64 32)" \
--     -v developer_password="$(openssl rand -base64 32)" \
--     -f 0003_provision_application.sql
--
-- Record the two generated passwords in your secret manager immediately --
-- nothing in this flow returns or stores them in recoverable form.
--
-- WHAT "PROVISIONING ONE APPLICATION" MEANS (R-1):
--   1. namespace  -- one PostgreSQL *database*, `mitatedb_app_<app_id>`,
--                    whose `public` schema is owned by that application's
--                    own developer role. This is the primary containment
--                    wall: with no schema-per-application FDW/dblink path
--                    between databases, cross-application access is not a
--                    permission this file might forget to revoke
--                    somewhere -- it does not exist as a SQL operation at
--                    all once `CONNECT` on the wrong database is refused
--                    (`tests/test_postgres.py::
--                    test_cross_database_connect_is_refused_at_the_
--                    database_level` verifies this directly, with a raw
--                    `psycopg.connect`, not through this foundation's own
--                    `PostgresBackend`).
--   2. privilege  -- two login roles: `..._rt` (DML only, no CREATE on
--                    `public`) and `..._dv` (owns `public`, so it can DDL
--                    there; still NOSUPERUSER/NOCREATEDB/NOCREATEROLE).
--                    Neither role is ever granted `CONNECT` on any
--                    database but its own application's.
--
-- R-1's design explicitly does NOT layer Row Level Security underneath
-- database-per-application for this WP (design v1.1 §7 future-work
-- register: "RLS defence-in-depth の併用...database-per-applicationが主
-- 境界として実測確立した後の追加層として") -- the primary wall above is
-- this WP's own real, tested containment boundary.
--
-- WHY THIS IS A SCRIPT, NOT A SINGLE FUNCTION CALL: `CREATE DATABASE`
-- cannot run inside a transaction block (which every plpgsql function
-- body implicitly is), and setting up the new database's `public` schema
-- requires actually being connected to it (`\c` below opens a new
-- physical connection -- one PostgreSQL connection cannot switch which
-- database it is connected to mid-session). 0002's `begin_provision_
-- application`/`finish_provision_application` bracket this script: the
-- former validates and creates the two login roles (transactional, safe
-- as a function); the latter records the finished application in the
-- registry only once every step below has succeeded.

\set ON_ERROR_STOP on

SELECT * FROM mitatedb_registry.begin_provision_application(:'app_id', :'runtime_password', :'developer_password') \gset

-- `CREATE DATABASE` -- a plain top-level statement (see this file's
-- header). No `OWNER` clause: it defaults to the executing role
-- (`mitatedbsvc_provision`), matching how `0001` creates
-- `mitatedb_platform` the same way. `TEMPLATE template0` avoids inheriting
-- any accumulated customisation of `template1` on this cluster.
CREATE DATABASE :"database_name" TEMPLATE template0 ENCODING 'UTF8';

-- Primary wall: a newly created PostgreSQL database grants `CONNECT` to
-- `PUBLIC` by default. Close that immediately, then grant `CONNECT` only
-- to this application's own two roles. From this point on, no role
-- outside this pair -- including every *other* application's own
-- runtime/developer roles -- can even open a connection to this
-- database.
REVOKE CONNECT ON DATABASE :"database_name" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"database_name" TO :"runtime_role";
GRANT CONNECT ON DATABASE :"database_name" TO :"developer_role";

-- Reconnect to the new database itself. `mitatedbsvc_provision` can do
-- this even though `PUBLIC`'s default `CONNECT` was just revoked above,
-- because it owns this database (object owners implicitly hold every
-- privilege on their own object, bypassing ACL checks).
\c :database_name

-- Close `public`'s default privileges, same as `0001` does for the
-- platform database. `mitatedbsvc_provision` still implicitly owns
-- `public` too at this instant (PostgreSQL 15+: a freshly created
-- database's `public` schema is owned by the pseudo-role
-- `pg_database_owner`, which resolves to whoever owns the *current*
-- database -- `mitatedbsvc_provision`, until the `ALTER SCHEMA ... OWNER
-- TO` below hands it to the developer role). Order matters: the `GRANT
-- USAGE` below must run *before* ownership moves to the developer role,
-- or `mitatedbsvc_provision` would no longer have authority to grant
-- anything on this schema at all.
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO :"runtime_role";

-- `mitatedbsvc_provision` needs the `SET` option on the developer role
-- *before* it can either (a) transfer `public`'s ownership to it, below,
-- or (b) assume it via `SET LOCAL ROLE` further down: PostgreSQL 16
-- hardened ownership transfer so that changing an object's owner TO a
-- role now requires the grantor to already be able to `SET ROLE` to that
-- role, not merely to hold `ADMIN OPTION` on it (which is all `CREATE
-- ROLE` grants its creator automatically). This membership is granted
-- immediately before it is needed and revoked immediately after (`REVOKE
-- ... FROM CURRENT_USER` below), so `mitatedbsvc_provision` never holds
-- standing membership in any application's developer role between
-- provisioning runs.
GRANT :"developer_role" TO CURRENT_USER WITH SET TRUE;

-- `public` schema ownership -- and therefore all future DDL authority in
-- it -- moves to the developer role now. Scoped to exactly this one
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

-- Schema-revision bookkeeping table (P3 WP-1 round 2 instruction #5;
-- `backend_postgres.PostgresBackend.schema_revision`/`_bump_schema_
-- revision`): created directly here, not left to application code, so
-- every provisioned application starts at revision 0. Deliberately
-- created BEFORE the `ALTER DEFAULT PRIVILEGES` statement below, so that
-- statement's own future-tables grant does NOT retroactively apply to it
-- -- the runtime role gets NO privilege on this table at all (R-1: this
-- bookkeeping is read/written exclusively over the developer connection
-- by `PostgresBackend`, regardless of which application-level role
-- (runtime or developer) triggered the call that needed it -- a
-- deliberately narrower grant than r2db-api's own analogous
-- `_r2db_schema_revision` table, which DOES grant its own runtime role
-- SELECT/UPDATE; independently decided here rather than mirrored, since
-- nothing in this foundation's own design requires the runtime role to
-- read it directly).
CREATE TABLE public._mdb_schema_revision (
    id boolean PRIMARY KEY DEFAULT TRUE,
    revision bigint NOT NULL DEFAULT 0,
    CONSTRAINT _mdb_schema_revision_singleton CHECK (id)
);
INSERT INTO public._mdb_schema_revision (id, revision) VALUES (TRUE, 0);

-- From here on, any table the developer role creates in `public` (i.e.
-- every entity table `PostgresBackend.create_collection`/`add_field`
-- creates at request time) automatically grants the runtime role DML --
-- and only DML, never DDL -- the moment it exists, with no per-table
-- grant statement required from the application process.
ALTER DEFAULT PRIVILEGES FOR ROLE :"developer_role" IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :"runtime_role";

COMMIT;
-- `SET LOCAL ROLE` above reverted automatically at `COMMIT`; the temporary
-- membership itself is revoked explicitly below rather than left to
-- accrue.
REVOKE :"developer_role" FROM CURRENT_USER;

-- Reconnect to the platform database to record the now-complete
-- application in the registry. `psql`'s `\c` has no "go back" form, so
-- the platform database name is named again explicitly here -- literally,
-- matching how `0001`/`0002` name it, so the test harness's own textual
-- `mitatedb` -> throwaway-prefix substitution (`tests/test_postgres.py`)
-- rewrites this occurrence identically to every other one in this
-- migration set.
\c mitatedb_platform
SELECT mitatedb_registry.finish_provision_application(:'app_id', :'database_name', :'runtime_role', :'developer_role');
