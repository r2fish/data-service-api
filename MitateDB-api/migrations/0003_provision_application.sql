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

-- Phase 6 WP-3 (design docs/design/PHASE6_CONTRACT_160_CLIENT_DISCOVERY_
-- V1.md D-3, §1.5 finding 2a): the declared-type registry -- the SOLE
-- source of truth for every entity field's own contract-vocabulary type
-- (`backend_postgres.PostgresBackend.field_types`/`field_domains`,
-- `http.py::get_catalog`). Physical column type alone cannot answer this
-- (`object`/`array`/`json` are all physically TEXT, and a declared
-- `boolean` is physically INTEGER -- indistinguishable from `integer`'s
-- own INTEGER-range values without this table). Created here, same
-- bookkeeping-table treatment as `_mdb_schema_revision` immediately
-- above -- BEFORE the `ALTER DEFAULT PRIVILEGES` statement below, so the
-- runtime role gets NO privilege on it either (read/written exclusively
-- over the developer connection, same reasoning as that table's own
-- comment: nothing in this foundation's design requires the runtime role
-- to read it directly). `(entity, field)` is the natural primary key --
-- at most one declared type per field, ever (`add_field` cannot replace
-- an existing field's type; this peer has no `alter_field`, design §1.5
-- finding 1c). `declared_type` is constrained to the SAME 7-word contract
-- vocabulary `field_types.CONTRACT_TYPES` enumerates in Python -- a
-- second, independent enforcement point (defence in depth, R-2's own
-- precedent), not the only one.
-- Phase 9 WP-3a (design docs/design/
-- PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md D-2 (1)/(4)):
-- `enum_json`/`nullable` carry this field's own contract 1.7.0
-- `field_constraints` declaration, alongside `declared_type` in the SAME
-- row -- never a second table (`(entity, field)` is already the natural
-- key for "one declaration row per field", D-2 (1)/(4)'s own "宣言の正本
-- は peer ごと・backend ごとに置く" choice for this backend). `enum_json`
-- is a JSON-array TEXT column (`NULL` when this field declares no
-- `enum`), the same "store structured text, decode in Python" pattern
-- entity-table `object`/`array`/`json` columns already use elsewhere in
-- this foundation -- not a native `jsonb` column, so this bookkeeping
-- table's own shape stays consistent with every other TEXT-column choice
-- already on it (`declared_type`). `nullable` defaults `TRUE` -- the
-- contract's own default (D-2 (2): "nullable の既定は true"), so a row
-- inserted by `0006`'s own pre-Phase-9 backfill logic (which this
-- migration's constraint below cannot retroactively rewrite, but a NEW
-- application provisioned by this template starts with) is never
-- ambiguous.
CREATE TABLE public._mdb_field_types (
    entity text NOT NULL,
    field text NOT NULL,
    declared_type text NOT NULL CHECK (declared_type IN ('string', 'integer', 'number', 'boolean', 'object', 'array', 'json')),
    enum_json text NULL,
    nullable boolean NOT NULL DEFAULT TRUE,
    PRIMARY KEY (entity, field)
);

-- Q4-WP4-LEDGER-BEGIN (test harnesses may strip this marked block,
-- inclusive of both marker lines, to reconstruct a synthetic
-- "pre-Q4-WP4" provisioning template for an EXISTING-application
-- backfill test -- `tests/test_platform_upgrades.py`'s own `_legacy_
-- 0003_text` helper does exactly this; never edit this marker pair
-- without updating that helper too).
-- Q4 phase (design docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md D-3(a)/(b)(i),
-- work order docs/work-orders/WORK_ORDER_Q4_DB_SIDE_SINGLE_TRUTH_V1.md §4
-- WP-4 変更対象 A): the per-application platform-upgrade ledger --
-- records which of this package's own per-application upgrade scripts
-- (`0006_declared_field_types_upgrade.sql`, `0008_platform_upgrades_
-- upgrade.sql`, and any later one this package ships) have already been
-- applied to THIS application's own database. Same bookkeeping-table
-- treatment as `_mdb_schema_revision`/`_mdb_field_types` immediately
-- above -- created BEFORE `ALTER DEFAULT PRIVILEGES` so the runtime role
-- gets no privilege from that statement, and explicitly `REVOKE`d/
-- `GRANT`ed below instead (design D-3(a): the runtime role needs `SELECT`
-- on this ONE table, unlike the other two, so it can read its own
-- application's ledger at cell-open time -- requester ruling 2026-09-05
-- U-2: "台帳表に対する runtime role の権限は SELECT のみを付与する").
-- Deliberately NOT wrapped in Row Level Security (design D-3(a), monitor
-- ruling 2026-09-05): `_mdb_schema_revision`/`_mdb_field_types` already
-- have none either on this peer (unlike r2db-api's own `_r2db_schema_
-- revision`), so this table follows the SAME peer-local precedent, not a
-- new one.
CREATE TABLE public._mdb_platform_upgrades (
    upgrade_number integer     PRIMARY KEY,
    script_name    text        NOT NULL,
    applied_at     timestamptz NOT NULL DEFAULT now()
);

-- The runtime role gets NO privilege from `ALTER DEFAULT PRIVILEGES`
-- below (this table is created before that statement runs, same as
-- `_mdb_schema_revision`/`_mdb_field_types`) -- these two statements
-- REVOKE any privilege a re-run of this template might otherwise leave
-- standing, then GRANT exactly `SELECT` (U-2), matching the terminal
-- state `0008_platform_upgrades_upgrade.sql`'s own identical REVOKE/GRANT
-- pair brings an EXISTING application to (design D-3(b): both
-- provisioning paths reach the identical end state).
REVOKE ALL    ON public._mdb_platform_upgrades FROM :"runtime_role";
GRANT  SELECT ON public._mdb_platform_upgrades TO :"runtime_role";
-- `SET LOCAL ROLE :"developer_role"` is in effect (see above), so
-- CURRENT_USER is the developer role (this table's own owner) and
-- SESSION_USER is `mitatedbsvc_provision`, the role actually running this
-- script -- granted `SELECT` here, as the owner, so `ops upgrade-status`/
-- `upgrade-applications` (provision DSN only, design D-4) can read this
-- table back after the ritual's own closing `REVOKE :"developer_role"
-- FROM CURRENT_USER` (below) drops the provision role's temporary
-- developer membership (design D-3(a)'s own "付与が無いと --dry-run すら
-- 動かない" note). `USAGE` on the SCHEMA itself is also required --
-- PostgreSQL checks schema-level `USAGE` before ever consulting a
-- table-level grant (design §3.9's own DDL is a skeleton; `public` is
-- owned by the developer role, and database ownership -- which
-- `mitatedbsvc_provision` does hold, `CREATE DATABASE`'s own default
-- `OWNER` above -- does NOT itself confer schema-level access to objects
-- inside that database, so without this line `ops upgrade-status`/
-- `upgrade-applications` would fail with "permission denied for schema
-- public" despite the table-level `GRANT SELECT` immediately above).
GRANT  USAGE  ON SCHEMA public TO SESSION_USER;
GRANT  SELECT ON public._mdb_platform_upgrades TO SESSION_USER;

-- A NEWLY provisioned application starts out already carrying every
-- per-application upgrade number this package's own migrations set
-- currently ships (design D-3(b)(i)) -- `{6, 8}`, kept in three-way sync
-- with `platform_upgrades.PLATFORM_UPGRADE_NUMBERS` and the real
-- `migrations/*_upgrade.sql` file-number set by the static scanner
-- (`tests/test_platform_upgrade_ledger_scan.py::
-- test_real_migrations_three_way_match`, design §10). Integer-literal
-- tuples only (design §8.1: a function call, dollar-quote, or nested
-- parenthesis here would slip past that scanner's own `VALUES (...)`
-- extraction and fail closed as a three-way mismatch instead).
INSERT INTO public._mdb_platform_upgrades (upgrade_number, script_name) VALUES
    (6, '0006_declared_field_types_upgrade.sql'),
    (8, '0008_platform_upgrades_upgrade.sql'),
    (9, '0009_field_constraints_upgrade.sql'),
    (10, '0010_idempotency_records_upgrade.sql')
ON CONFLICT (upgrade_number) DO NOTHING;
-- Q4-WP4-LEDGER-END

-- Phase 9 WP-3c (design docs/design/
-- PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md D-5, 追補 2
-- S-a/S-b/S-f; 監督裁定集約 rulings-r5-r6.md I-1): the idempotency-record
-- side table -- one row per `idempotency_key` this Application has
-- committed a request under, still within its own `idempotency_
-- retention_ms` window. Created here (a NEW application) and by
-- `migrations/0010_idempotency_records_upgrade.sql` (an EXISTING one) --
-- both reach the identical end state (design §8.1's own two-provisioning-
-- path convention, matching `_mdb_platform_upgrades`/`_mdb_field_types`
-- before it). UNLIKE `_mdb_schema_revision`/`_mdb_field_types` (developer-
-- connection only) and LIKE `_mdb_platform_upgrades`, the runtime role
-- needs a real, explicit grant here -- but FULL DML (`SELECT`/`INSERT`/
-- `UPDATE`/`DELETE`), not the ledger's own read-only `SELECT`:
-- `ApplicationCell.transact`'s own idempotency lookup/reap/write all run
-- over the RUNTIME connection, the same one its own data DML already
-- runs on (I-1's own "record は data tx と同一 tx で書く", applied to the
-- mutate path). A schema-op idempotency write (`create_entity`/
-- `add_field`/`alter_field`) instead runs over the DEVELOPER connection,
-- alongside that op's own DDL -- the developer role already owns this
-- table (it created it), so no separate grant is needed for that path.
CREATE TABLE public._mdb_idempotency (
    key            text        PRIMARY KEY,
    digest         text        NOT NULL,
    response_json  text        NOT NULL,
    created_at_ms  bigint      NOT NULL
);
GRANT SELECT, INSERT, UPDATE, DELETE ON public._mdb_idempotency TO :"runtime_role";

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
