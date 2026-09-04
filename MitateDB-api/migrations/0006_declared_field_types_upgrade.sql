-- MitateDB-api PostgreSQL upgrade -- 0006: retrofit the declared-type
-- registry onto an application provisioned BEFORE Phase 6 WP-3 (design
-- docs/design/PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md D-3, §1.5
-- finding 2a).
--
-- WHO RUNS THIS: the operator/deploy tooling, connected to
-- `mitatedb_platform` as `mitatedbsvc_provision`, once per EXISTING
-- application that was provisioned before this WP shipped (a database
-- provisioned by the UPDATED `0003_provision_application.sql` already
-- carries this table -- running this script against one is then a
-- harmless no-op, see IDEMPOTENT below):
--
--   psql "$MITATEDBSVC_PROVISION_DSN" -v app_id='acme' \
--     -f 0006_declared_field_types_upgrade.sql
--
-- CLASSIFICATION (work order docs/work-orders/WORK_ORDER_PHASE6_
-- CONTRACT_160_V1.md §7 item 5(c)): a per-application UPGRADE script,
-- the third of the three migration classes that work order fixes --
-- distinct from (a) the one-time platform/per-application migrations
-- already applied (`0001`/`0002`/`0005`, and each application's own
-- ALREADY-RUN `0003`/`0004`, none of which this file edits in place) and
-- (b) `0003_provision_application.sql` itself, a template revised by
-- this same WP so a NEWLY provisioned application gets this table
-- directly. `0003`'s revision and this script are issued as a PAIR
-- (work order's own requirement): a new application reaches the table
-- via (b), an existing one via (c) -- both must reach the SAME end
-- state, which this script's own grant handling (below) exists to
-- guarantee.
--
-- WHAT THIS DOES: creates `public._mdb_field_types` (idempotent) in the
-- named application's own database if missing, and backfills one row
-- per EXISTING column of every EXISTING entity table, from that
-- column's own PHYSICAL type -- the SAME backfill rule
-- `field_types.FOUNDATION_TYPE_TO_CONTRACT_TYPE` applies in Python:
--
--   bigint            -> integer
--   double precision  -> number
--   integer           -> boolean
--   text              -> string   (see the KNOWN LIMITATION note below)
--
-- KNOWN LIMITATION (disclosed, not resolved by this script -- WP-3's own
-- "実測事項" (i)): a physical `text` column is ambiguous on this
-- backend -- it could have been declared `string` (the common case: a
-- name-only `create_entity` field, or an explicit `string`-typed `add_
-- field`), OR `object`/`array` (an `add_field` call naming one of those
-- two contract words was already valid before contract 1.6.0 --
-- `http.py`'s own pre-WP-3 `_CONTRACT_FIELD_TYPE_TO_MITATEDB` mapping
-- already accepted them, mapping both to physical `json`/TEXT).
-- PostgreSQL's own catalog cannot recover which of the two a column was
-- originally declared as (this is exactly the fact `backend_postgres.
-- py`'s own pre-WP-3 comment on `_DOMAIN_BY_DATA_TYPE` used to assert
-- did not matter -- L6-1 (v), corrected by this same WP). This script
-- therefore backfills EVERY physical `text` column as `string`,
-- unconditionally -- the same default `create_entity`'s own pre-1.6.0
-- name-only path always used. If a real deployment's own application
-- database has an `add_field`-created `object`/`array` column, this
-- script reports it as `string` instead; an operator with out-of-band
-- knowledge of such a column should correct that one row by hand after
-- running this script:
--
--   UPDATE public._mdb_field_types SET declared_type = 'object'
--     WHERE entity = '<entity>' AND field = '<field>';
--
-- IDEMPOTENT: `CREATE TABLE IF NOT EXISTS` + `ON CONFLICT (entity,
-- field) DO NOTHING` -- safe to re-run against the same application (a
-- column added between two runs picks up its own row on the second run;
-- an already-backfilled column, including one an operator hand-corrected
-- per the note above, is never touched again).
--
-- WHY A SCRIPT, NOT A FUNCTION: reaching the target application's own
-- database requires actually being connected to it (`\c` below), the
-- same reason `0003_provision_application.sql`'s own header gives.

\set ON_ERROR_STOP on

SELECT database_name, runtime_role, developer_role FROM mitatedb_registry.applications
    WHERE application_id = :'app_id' \gset

\if :{?database_name}
\else
    \warn 'application ' :app_id ' has no database_name on record (never fully provisioned) -- nothing to upgrade'
    \q
\endif

\c :database_name

-- Same temporary-membership ritual as `0003_provision_application.sql`'s
-- own header comment explains (PostgreSQL 16's own ownership-transfer
-- hardening) -- needed here too, since the table below must be owned by
-- the developer role (matching `_mdb_schema_revision`'s own ownership),
-- not by `mitatedbsvc_provision`.
GRANT :"developer_role" TO CURRENT_USER WITH SET TRUE;

BEGIN;
SET LOCAL ROLE :"developer_role";

CREATE TABLE IF NOT EXISTS public._mdb_field_types (
    entity text NOT NULL,
    field text NOT NULL,
    declared_type text NOT NULL CHECK (declared_type IN ('string', 'integer', 'number', 'boolean', 'object', 'array', 'json')),
    PRIMARY KEY (entity, field)
);

-- Match the updated `0003`'s own grant shape exactly: the runtime role
-- gets NO privilege on this bookkeeping table. A freshly-provisioned
-- application's own copy is created BEFORE `ALTER DEFAULT PRIVILEGES`
-- ever runs, so it is naturally exempt; THIS application's own `ALTER
-- DEFAULT PRIVILEGES FOR ROLE developer_role` rule is already standing
-- (set by its own, already-applied `0003` run) and would otherwise grant
-- the runtime role SELECT/INSERT/UPDATE/DELETE on this table
-- automatically the instant it is created above -- explicitly revoked
-- here so both provisioning paths reach the identical end state (work
-- order §7 item 5(c)'s own requirement). Harmless (and idempotent) to
-- run again if this table already existed and was already revoked.
REVOKE ALL ON public._mdb_field_types FROM :"runtime_role";

INSERT INTO public._mdb_field_types (entity, field, declared_type)
SELECT c.table_name, c.column_name,
    CASE c.data_type
        WHEN 'bigint' THEN 'integer'
        WHEN 'double precision' THEN 'number'
        WHEN 'integer' THEN 'boolean'
        ELSE 'string'
    END
FROM information_schema.columns c
WHERE c.table_schema = 'public'
  AND c.table_name NOT IN ('_mdb_schema_revision', '_mdb_field_types')
ON CONFLICT (entity, field) DO NOTHING;

COMMIT;
REVOKE :"developer_role" FROM CURRENT_USER;

\c mitatedb_platform
