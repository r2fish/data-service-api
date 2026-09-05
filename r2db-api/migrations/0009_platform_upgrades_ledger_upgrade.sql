-- r2db-api PostgreSQL upgrade -- 0009: retrofit the per-application
-- platform-upgrade ledger onto an application provisioned BEFORE Q4 WP-3
-- (design docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md D-3(b)(ii), work order
-- docs/work-orders/WORK_ORDER_Q4_DB_SIDE_SINGLE_TRUTH_V1.md WP-3).
--
-- WHO RUNS THIS: the operator/deploy tooling (or `python -m r2db_api.ops
-- upgrade-applications`, D-4, which runs this exact script once per
-- application whose own ledger does not yet record upgrade `9`), connected
-- to `r2dbsvc_platform` as `r2dbsvc_control`, once per EXISTING application
-- that was provisioned before this WP shipped (a database provisioned by
-- the UPDATED `0003_provision_application.sql` already carries this ledger,
-- pre-seeded with `9` -- running this script against one is then a
-- harmless no-op, see IDEMPOTENT below):
--
--   psql "$R2DBSVC_CONTROL_DSN" -v app_slug='myapp' \
--     -f 0009_platform_upgrades_ledger_upgrade.sql
--
-- CLASSIFICATION (design §8.1's own naming regime, work order §4 WP-0
-- change table B): a per-application UPGRADE script, the same class
-- `MitateDB-api/migrations/0006_declared_field_types_upgrade.sql` (Phase 6
-- WP-3) established -- distinct from (a) the one-time platform/
-- per-application migrations already applied (`0001`/`0002`/`0005`-`0008`,
-- and each application's own already-run `0003`/`0004`, none of which this
-- file edits in place) and (b) `0003_provision_application.sql` itself, a
-- TEMPLATE this same WP revises so a NEWLY provisioned application gets
-- this ledger directly, pre-seeded. `0003`'s revision and this script are
-- issued as a PAIR (design D-3(b), work order constraint 3's own "テンプレ
-- ート改訂とper-app upgrade scriptは対で出す"): a new application reaches
-- the ledger via (b), an existing one via this script -- both must reach
-- the SAME end state, which this script's own grant handling (below)
-- mirrors `0003`'s literally, and which `r2db-api/tests/test_postgres.py`
-- verifies directly against both provisioning paths.
--
-- WHAT THIS DOES: creates `public._r2db_platform_upgrades` (idempotent) in
-- the named application's own database if missing, records upgrade `9` in
-- it (`ON CONFLICT (upgrade_number) DO NOTHING` -- also idempotent), and
-- re-installs `public._r2db_missing_rls` with `CREATE OR REPLACE VIEW` so
-- this application's own copy (frozen at whatever `0003` looked like when
-- IT was provisioned, design D-3(e)(ii)) also excludes this newly created
-- ledger table from its own RLS-coverage check (the ledger deliberately
-- carries no RLS at all, see the table-creation comment below).
--
-- NO EARLY-QUIT SKIP PATH (design D-3(c) point 3, §1.5 finding 7a, work
-- order §4 WP-3 change table B: this script carries none of psql's own
-- backslash-q meta-command literally, anywhere, by design -- it is the
-- one grep-observable property the D-3(d) static regime and this WP's
-- own completion condition audit both hold this script to): that
-- meta-command returns exit code 0, indistinguishable from a script that
-- genuinely ran to completion -- a bulk-apply tool (`ops upgrade-
-- applications`, D-4) that treated a silent no-op the same as a real
-- success could never tell "this application's ledger is now correct"
-- apart from "this script quietly skipped it". Unlike `MitateDB-api/
-- migrations/0006_...upgrade.sql` (which DOES carry that meta-command,
-- for the case where `application_slug` has no `database_name` on
-- record), this script assumes it is called ONLY against an application
-- that already has one -- the ops-side caller (`ops upgrade-
-- applications`) is what filters registry rows by `database_name IS NOT
-- NULL` before ever invoking this script (design D-3(c) point 3's own
-- "対象外のapplicationはops側が
-- registryのdatabase_nameで絞る"), so this script itself never needs a
-- conditional skip branch at all.
--
-- IDEMPOTENT: `CREATE TABLE IF NOT EXISTS` + `ON CONFLICT (upgrade_number)
-- DO NOTHING` + `CREATE OR REPLACE VIEW` -- safe to re-run against the same
-- application any number of times (`r2db-api/tests/test_postgres.py`
-- applies this script twice and asserts the ledger's own end state is
-- identical both times).
--
-- ATOMIC (design D-3(c) point 1): the ledger table's creation/grants, the
-- ledger INSERT recording upgrade `9`, and the `_r2db_missing_rls`
-- redefinition all run inside the SAME `BEGIN ... COMMIT` block below --
-- if anything in this script's own body fails before `COMMIT`, PostgreSQL
-- rolls back every DDL/DML statement in it (transactional DDL), so a
-- failed run never leaves a partially-created ledger table, or a ledger
-- table that exists but was never actually recorded as applied.
--
-- WHY A SCRIPT, NOT A FUNCTION: reaching the target application's own
-- database requires actually being connected to it (`\c` below), the same
-- reason `0003_provision_application.sql`'s own header gives.

\set ON_ERROR_STOP on

SELECT database_name, runtime_role, developer_role FROM r2dbsvc_registry.applications
    WHERE application_slug = :'app_slug' \gset

\c :database_name

-- Same temporary-membership ritual `0003_provision_application.sql`'s own
-- header comment explains (PostgreSQL 16's own ownership-transfer
-- hardening) -- needed here too, since the table below must be owned by
-- the developer role (matching `_r2db_schema_revision`'s own ownership),
-- not by `r2dbsvc_control`.
GRANT :"developer_role" TO CURRENT_USER WITH SET TRUE;

BEGIN;
SET LOCAL ROLE :"developer_role";

-- Design D-3(a)/(e); mirrors `0003_provision_application.sql`'s own ledger
-- block verbatim (see that file's own comment for the full rationale of
-- each grant/revoke below -- repeated only where this script's own
-- retrofit context differs).
--
-- No RLS on this table (design D-3(a)'s own note, `FORCE ROW LEVEL
-- SECURITY` would apply even to this table's OWNER, the developer role
-- this whole block runs as).
CREATE TABLE IF NOT EXISTS public._r2db_platform_upgrades (
    upgrade_number integer     PRIMARY KEY,
    script_name    text        NOT NULL,
    applied_at     timestamptz NOT NULL DEFAULT now()
);
-- Unlike `0003` (where this table is created BEFORE `ALTER DEFAULT
-- PRIVILEGES` ever runs, so it is naturally exempt from that rule's
-- auto-grant), THIS application's own `ALTER DEFAULT PRIVILEGES FOR ROLE
-- developer_role` rule is already standing (set by its own, already-
-- applied `0003` run) and would otherwise grant the runtime role
-- SELECT/INSERT/UPDATE/DELETE on this table automatically the instant it
-- is created above -- explicitly revoked here so both provisioning paths
-- reach the identical end state (requester ruling 2026-09-05, U-2:
-- "runtime roleの権限はSELECTのみ付与"). Harmless (and idempotent) to run
-- again if this table already existed and was already revoked.
REVOKE ALL    ON public._r2db_platform_upgrades FROM :"runtime_role";
GRANT  SELECT ON public._r2db_platform_upgrades TO :"runtime_role";
GRANT  SELECT ON public._r2db_platform_upgrades TO SESSION_USER;
-- Implementer finding (real-PG confirmed, same reasoning as `0003`'s own
-- identical grant): this application's `public` schema has carried no
-- standing `USAGE` grant for the provision role since ITS OWN original
-- `0003` run (which already revoked `PUBLIC`'s default access and
-- transferred ownership to the developer role) -- without this, `ops
-- upgrade-applications`/`ops upgrade-status` cannot even NAME this table
-- ("permission denied for schema public"), regardless of the `GRANT
-- SELECT` above.
GRANT  USAGE  ON SCHEMA public TO SESSION_USER;
INSERT INTO public._r2db_platform_upgrades (upgrade_number, script_name)
    VALUES (9, '0009_platform_upgrades_ledger_upgrade.sql')
    ON CONFLICT (upgrade_number) DO NOTHING;

-- Design D-3(e)(ii): this application's own `_r2db_missing_rls` copy was
-- frozen at whatever `0003` looked like when THIS application was
-- provisioned (before this WP), so it does not yet exclude the ledger
-- table just created above. `CREATE OR REPLACE VIEW` re-installs the
-- IDENTICAL definition the (also revised, this same WP) template now
-- installs for a brand-new application -- both must always match.
CREATE OR REPLACE VIEW public._r2db_missing_rls AS
    SELECT c.relname AS table_name
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relkind = 'r'
      AND c.relname NOT IN ('_r2db_schema_revision', '_r2db_platform_upgrades')
      AND (c.relrowsecurity = false OR c.relforcerowsecurity = false);
GRANT SELECT ON public._r2db_missing_rls TO :"runtime_role";

COMMIT;
-- `SET LOCAL ROLE` above reverted automatically at `COMMIT`; the temporary
-- membership itself is revoked explicitly below rather than left to accrue
-- (mirrors `0003_provision_application.sql`'s own closing comment).
REVOKE :"developer_role" FROM CURRENT_USER;

\c r2dbsvc_platform
