-- MitateDB-api PostgreSQL upgrade -- 0008: retrofit the per-application
-- platform-upgrade ledger onto an application provisioned BEFORE Q4 phase
-- WP-4 (design docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md D-3, §1.5
-- finding 7a/7b/8).
--
-- WHO RUNS THIS: the operator/deploy tooling (or `python -m mitatedb_api.
-- ops upgrade-applications`, design D-4), connected to `mitatedb_
-- platform` as `mitatedbsvc_provision`, once per EXISTING application
-- whose own ledger does not yet carry this script's own number (a
-- database provisioned by the UPDATED `0003_provision_application.sql`
-- already carries this table AND this number seeded -- running this
-- script against one is then a harmless no-op, see IDEMPOTENT below):
--
--   psql "$MITATEDB_PROVISION_DSN" -v app_id='acme' \
--     -f 0008_platform_upgrades_upgrade.sql
--
-- CLASSIFICATION (work order docs/work-orders/
-- WORK_ORDER_Q4_DB_SIDE_SINGLE_TRUTH_V1.md §4 WP-4 変更対象 B, design
-- §8.1): a per-application UPGRADE script -- `0003`'s own revision (this
-- SAME WP) reaches a NEWLY provisioned application via (b)(i), this
-- script reaches an EXISTING one via (b)(ii); both reach the SAME end
-- state (design D-3(b)). Named `NNNN_<name>_upgrade.sql` (design §8.1
-- item 1) so the static ledger-discipline scanner (`tests/
-- test_platform_upgrade_ledger_scan.py`) picks it up. Unlike `0006`
-- (grandfathered, design §8.1/§10 allow-list `{6}`), this script carries
-- no backslash-q skip path (design D-3(c) item 3: psql returns exit 0 on
-- that meta-command, indistinguishable from success -- the operator/`ops
-- upgrade-applications` (design D-4(b)) is the one that filters
-- `database_name IS NOT NULL` applications BEFORE ever invoking this
-- script, so this script itself never needs a defensive "unprovisioned,
-- skip" branch).
--
-- WHAT THIS DOES: creates `public._mdb_platform_upgrades` (idempotent) in
-- the named application's own database if missing, records THIS script's
-- own number (8) unconditionally, and additionally backfills upgrade
-- number 6 (`0006_declared_field_types_upgrade.sql`) as already-applied
-- IF AND ONLY IF `public._mdb_field_types` already exists in this
-- database -- the same detection design D-3(b)(ii) specifies
-- (`to_regclass('public._mdb_field_types') IS NOT NULL`). If that table
-- does NOT exist, 6 is deliberately left OUT of the ledger (never
-- inserted, never assumed) -- this application's own ledger then reads
-- `{8}`, and `ops upgrade-status`/`upgrade-applications` (design D-4(b)'s
-- own SET-DIFFERENCE definition of "pending", never a "highest applied
-- number" comparison) correctly reports 6 as still pending, so a later
-- `ops upgrade-applications` run applies `0006_declared_field_types_
-- upgrade.sql` for real instead of silently skipping it forever.
--
-- IDEMPOTENT: `CREATE TABLE IF NOT EXISTS` + `ON CONFLICT (upgrade_
-- number) DO NOTHING` on every ledger INSERT below -- safe to re-run
-- against the same application any number of times.
--
-- WHY A SCRIPT, NOT A FUNCTION: reaching the target application's own
-- database requires actually being connected to it (`\c` below), the
-- same reason `0003_provision_application.sql`'s own header gives.

\set ON_ERROR_STOP on

SELECT database_name, runtime_role, developer_role FROM mitatedb_registry.applications
    WHERE application_id = :'app_id' \gset

\c :database_name

-- Same temporary-membership ritual as `0003_provision_application.sql`'s
-- own header comment explains (PostgreSQL 16's own ownership-transfer
-- hardening) -- needed here too, since the table below must be owned by
-- the developer role (matching `_mdb_schema_revision`'s own ownership),
-- not by `mitatedbsvc_provision`.
GRANT :"developer_role" TO CURRENT_USER WITH SET TRUE;

BEGIN;
SET LOCAL ROLE :"developer_role";

-- Same shape `0003_provision_application.sql`'s own revision creates for
-- a brand-new application (design D-3(a)) -- created here for an
-- EXISTING one that predates that revision. `IF NOT EXISTS` makes this a
-- harmless no-op against a database this WP's own updated `0003` already
-- provisioned.
CREATE TABLE IF NOT EXISTS public._mdb_platform_upgrades (
    upgrade_number integer     PRIMARY KEY,
    script_name    text        NOT NULL,
    applied_at     timestamptz NOT NULL DEFAULT now()
);

-- Match the updated `0003`'s own grant shape exactly (design D-3(a),
-- requester ruling 2026-09-05 U-2: runtime role gets SELECT only, never
-- DML) -- both provisioning paths reach the identical end state. Harmless
-- (and idempotent) to run again if already granted.
REVOKE ALL    ON public._mdb_platform_upgrades FROM :"runtime_role";
GRANT  SELECT ON public._mdb_platform_upgrades TO :"runtime_role";
-- `SET LOCAL ROLE :"developer_role"` is in effect, so CURRENT_USER is the
-- developer role (this table's own owner, as it just created it) and
-- SESSION_USER is `mitatedbsvc_provision`, the role actually running this
-- script -- granted `SELECT` here, as the owner, so `ops upgrade-status`/
-- `upgrade-applications` (provision DSN only) can read this table back
-- after this ritual's own closing `REVOKE :"developer_role" FROM
-- CURRENT_USER` (below) drops the provision role's temporary developer
-- membership. `USAGE` on the SCHEMA itself, same reasoning as the
-- revised `0003`'s own identical pair of grants -- schema-level `USAGE`
-- is checked before any table-level grant, and database ownership does
-- not itself confer it.
GRANT  USAGE  ON SCHEMA public TO SESSION_USER;
GRANT  SELECT ON public._mdb_platform_upgrades TO SESSION_USER;

-- This script's own number, unconditionally (design §8.1: static scanner
-- requires ONE statement targeting this table to contain BOTH `ON
-- CONFLICT` and the bare integer literal `8`, de-zero-padded).
INSERT INTO public._mdb_platform_upgrades (upgrade_number, script_name)
VALUES (8, '0008_platform_upgrades_upgrade.sql')
ON CONFLICT (upgrade_number) DO NOTHING;

-- Backfill 6 ONLY if `0006_declared_field_types_upgrade.sql` has already
-- run against this database (design D-3(b)(ii)) -- never created here (a
-- SEPARATE, already-shipped script owns creating `_mdb_field_types`; this
-- statement only detects whether that already happened).
INSERT INTO public._mdb_platform_upgrades (upgrade_number, script_name)
SELECT 6, '0006_declared_field_types_upgrade.sql'
WHERE to_regclass('public._mdb_field_types') IS NOT NULL
ON CONFLICT (upgrade_number) DO NOTHING;

COMMIT;
-- `SET LOCAL ROLE` above reverted automatically at `COMMIT`; the temporary
-- membership itself is revoked explicitly below rather than left to
-- accrue.
REVOKE :"developer_role" FROM CURRENT_USER;

\c mitatedb_platform
