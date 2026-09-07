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

-- CCR-13 (docs/design/R2DB_CCR13_STORAGE_V1.md R-7 addendum, WP-3 review
-- "object/array の DOMAIN 型統一"): the two DOMAINs `PostgresCell._add_field`
-- declares a column as when the client's `field_type` is `"object"`/
-- `"array"`. Both are `jsonb` underneath -- PostgreSQL has no separate
-- "object" or "array" storage type -- but a bare `jsonb` column's own
-- catalog entry cannot report which of the two a client originally
-- declared (`information_schema.columns.data_type` is `jsonb` either way).
-- A DOMAIN's own name *is* reported (`information_schema.columns.
-- domain_name`), which is what lets `PostgresCell._load_catalog` recover
-- the declared type at all -- the entire reason these exist, not merely
-- the `jsonb_typeof` CHECK. NULL is allowed for either domain (NOT NULL is
-- out of this contract version's scope, R-7).
--
-- The CHECK is defence-in-depth underneath `r2db_api.structured._check_
-- type`'s own Python-side dict/list validation (which is what answers a
-- bad write with `VALIDATION_FAILED` naming only the field, before this
-- CHECK is ever reached) -- a real server-side invariant that should never
-- fire if `_check_type` is doing its job, so `PostgresCell` lets a CHECK
-- violation here fall through to its ordinary `SERVICE_UNAVAILABLE`
-- mapping rather than trying to decode and re-surface it. A named
-- constraint (`CONSTRAINT ... CHECK`, composed as `{entity}__{field}` the
-- way `create_index` names its own objects) was considered and rejected:
-- the composed name can exceed PostgreSQL's 63-byte identifier limit
-- (silently truncated, breaking the reverse lookup a disclosure-safe error
-- mapping would need), and a `CheckViolation`'s own DETAIL text includes
-- the entire failing row -- exactly what `errors.disclosure` forbids
-- surfacing. Leaving the constraint unnamed (PostgreSQL synthesizes one
-- privately) sidesteps both traps, since nothing in `PostgresCell` ever
-- needs to parse a synthesized name back into a client-facing identifier.
CREATE DOMAIN public._r2db_json_object AS jsonb
    CHECK (VALUE IS NULL OR jsonb_typeof(VALUE) = 'object');
CREATE DOMAIN public._r2db_json_array AS jsonb
    CHECK (VALUE IS NULL OR jsonb_typeof(VALUE) = 'array');

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

-- Q4 WP-3 (design docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md D-3(a)/(b)(i),
-- work order docs/work-orders/WORK_ORDER_Q4_DB_SIDE_SINGLE_TRUTH_V1.md
-- WP-3 change table A): the per-application platform-upgrade ledger --
-- "how far has THIS application's own database been upgraded", recorded
-- inside that same database (D-3's own "実体と同じデータベースの中に記録
-- する"), never in a control-plane-side table that could drift from a
-- restored/cloned copy of this one. A brand-new application, provisioned
-- by this very script, starts out already at the LATEST per-application
-- upgrade number this shipped package knows about -- seeded below as the
-- literal, de-zero-padded integer(s) `r2db_api.platform_upgrades.
-- PLATFORM_UPGRADE_NUMBERS` names (currently `{9}`; kept in three-way sync
-- with that package constant and every real `NNNN_..._upgrade.sql` file
-- under `migrations/` by `tests/test_platform_upgrade_ledger_scan.py`'s
-- own three-way-match assertion, design D-3(d) regulation (d)) -- so a
-- freshly provisioned application never needs `0009` (or any later
-- per-application upgrade script) run against it at all; those exist
-- solely to bring an application provisioned BEFORE that number shipped
-- up to date (D-3(b)(ii)).
--
-- No RLS on this table (monitor ruling 2026-09-05, design D-3(a)'s own
-- note): unlike `_r2db_schema_revision` above, `FORCE ROW LEVEL SECURITY`
-- would apply even to this table's OWNER (the developer role), which is
-- exactly the role every per-application upgrade script (and this
-- template) writes through via `SET LOCAL ROLE` -- forcing RLS here would
-- require a policy admitting that write with no isolation benefit this
-- table's own access pattern (provision-DSN-only writes, U-2) needs.
--
-- `REVOKE ALL ... FROM :"runtime_role"` undoes the `ALTER DEFAULT
-- PRIVILEGES` rule just above (which would otherwise auto-grant the
-- runtime role full DML on this brand-new table the instant it is
-- created) before granting back exactly `SELECT` (requester ruling
-- 2026-09-05, U-2: "台帳表に対するruntime roleの権限はSELECTのみ付与") --
-- read-only, for this same process' own cell open time check
-- (`r2db_api.postgres.PostgresCell.verify_platform_upgrades_applied`,
-- design D-3(f)). `GRANT SELECT ... TO SESSION_USER` (the provision role
-- running this very script, NOT `CURRENT_USER` -- see this block's own
-- position inside `SET LOCAL ROLE :"developer_role"`) is what lets `ops
-- upgrade-applications`/`ops upgrade-status` (D-4/D-5), which authenticate
-- as the provision role against each application's own database in turn,
-- read this table AFTER this script's own closing `REVOKE :"developer_
-- role" FROM CURRENT_USER` below has ended the provision role's one-shot
-- membership in the developer role (design D-3(a)'s own "付与が無いと
-- --dry-runすら動かない" note). `GRANT USAGE ON SCHEMA public TO
-- SESSION_USER` is likewise required for that same reason (implementer
-- finding, real-PG confirmed): the `REVOKE ALL ON SCHEMA public FROM
-- PUBLIC` above already stripped the provision role's OWN standing
-- access to this schema (its earlier access, before `ALTER SCHEMA public
-- OWNER TO :"developer_role"`, was as the schema's IMPLICIT owner via
-- `pg_database_owner`, which the ownership transfer itself ends) --
-- `GRANT SELECT` on a table alone does not let a role even NAME an object
-- inside a schema it has no `USAGE` on ("permission denied for schema
-- public").
CREATE TABLE IF NOT EXISTS public._r2db_platform_upgrades (
    upgrade_number integer     PRIMARY KEY,
    script_name    text        NOT NULL,
    applied_at     timestamptz NOT NULL DEFAULT now()
);
REVOKE ALL    ON public._r2db_platform_upgrades FROM :"runtime_role";
GRANT  SELECT ON public._r2db_platform_upgrades TO :"runtime_role";
GRANT  SELECT ON public._r2db_platform_upgrades TO SESSION_USER;
GRANT  USAGE  ON SCHEMA public TO SESSION_USER;
INSERT INTO public._r2db_platform_upgrades (upgrade_number, script_name)
    VALUES (9, '0009_platform_upgrades_ledger_upgrade.sql')
    ON CONFLICT (upgrade_number) DO NOTHING;

-- Phase 9 WP-2a (contract 1.7.0 R-2, design docs/design/PHASE9_
-- CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md §3 D-2, work order
-- docs/work-orders/WORK_ORDER_PHASE9_CONTRACT_170_V1.md §2 WP-2a): the
-- per-application field-constraints declaration registry, paired with
-- `migrations/0010_field_constraints_upgrade.sql` the same way this
-- block above is paired with `0009` -- a brand-new application, provi-
-- sioned by THIS script, gets the table and the ledger row directly; an
-- application provisioned before this WP shipped reaches both through
-- `0010` (via `ops upgrade-applications`). See `0010`'s own header for
-- the table's full shape/access-pattern rationale (identical here).
CREATE TABLE IF NOT EXISTS public._r2db_field_constraints (
    entity_name text    NOT NULL,
    field_name  text    NOT NULL,
    nullable    boolean NOT NULL DEFAULT true,
    enum_values jsonb,
    PRIMARY KEY (entity_name, field_name)
);
REVOKE ALL    ON public._r2db_field_constraints FROM :"runtime_role";
GRANT  SELECT ON public._r2db_field_constraints TO :"runtime_role";
GRANT  SELECT ON public._r2db_field_constraints TO SESSION_USER;
INSERT INTO public._r2db_platform_upgrades (upgrade_number, script_name)
    VALUES (10, '0010_field_constraints_upgrade.sql')
    ON CONFLICT (upgrade_number) DO NOTHING;

-- §8.5 condition 3(b) -- see this file's header. A live view, not a
-- point-in-time claim: querying it always reflects the database's current
-- catalog state, so it catches RLS having been disabled or never enabled
-- on any table by any means, not just ones `PostgresCell` created.
-- `_r2db_schema_revision` (created above, already RLS-protected) and --
-- Q4 WP-3, design D-3(e)(ii) -- the per-application platform-upgrade
-- ledger just created above (which deliberately carries no RLS at all,
-- see that block's own comment) are both excluded the same way
-- `PostgresCell._load_catalog`/`_rls_offenders` exclude them from the
-- application-visible catalog/RLS-coverage check (`r2db_api.postgres.
-- _BOOKKEEPING_TABLES`). `CREATE OR REPLACE VIEW` (monitor ruling
-- 2026-09-05; a plain `CREATE VIEW` before this WP) -- `0009_..._upgrade.
-- sql` re-runs this identical `CREATE OR REPLACE VIEW` statement against
-- every application provisioned BEFORE this WP shipped, whose own copy of
-- this view was frozen at ITS `0003` run's definition (design D-3(e)(ii):
-- "既存applicationのビューは0003適用時点の定義で固まっている") -- the
-- template and the per-application upgrade script must therefore always
-- carry the exact same view body.
CREATE OR REPLACE VIEW public._r2db_missing_rls AS
    SELECT c.relname AS table_name
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relkind = 'r'
      AND c.relname NOT IN ('_r2db_schema_revision', '_r2db_platform_upgrades', '_r2db_field_constraints')
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
