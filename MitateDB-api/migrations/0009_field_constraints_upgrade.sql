-- MitateDB-api PostgreSQL upgrade -- 0009: retrofit the `enum_json`/
-- `nullable` columns (contract 1.7.0 `field_constraints`, design docs/
-- design/PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md D-2 (1)/
-- (4)) onto `public._mdb_field_types` for an application provisioned
-- BEFORE Phase 9 WP-3a.
--
-- WHO RUNS THIS: the operator/deploy tooling (or `python -m mitatedb_api.
-- ops upgrade-applications`, design D-4), connected to `mitatedb_
-- platform` as `mitatedbsvc_provision`, once per EXISTING application
-- whose own ledger does not yet carry this script's own number (a
-- database provisioned by the UPDATED `0003_provision_application.sql`
-- already carries both columns AND this number seeded -- running this
-- script against one is then a harmless no-op, see IDEMPOTENT below):
--
--   psql "$MITATEDB_PROVISION_DSN" -v app_id='acme' \
--     -f 0009_field_constraints_upgrade.sql
--
-- CLASSIFICATION (work order docs/work-orders/
-- WORK_ORDER_PHASE9_CONTRACT_170_V1.md §2 WP-3a, design §8.1): a
-- per-application UPGRADE script -- `0003`'s own revision (this SAME WP)
-- reaches a NEWLY provisioned application via its own `CREATE TABLE`,
-- this script reaches an EXISTING one via `ALTER TABLE ... ADD COLUMN IF
-- NOT EXISTS`; both reach the SAME end state. Named `NNNN_<name>_
-- upgrade.sql` (design §8.1 item 1) so the static ledger-discipline
-- scanner (`tests/test_platform_upgrade_ledger_scan.py`) picks it up.
--
-- WHAT THIS DOES: adds `enum_json text NULL` and `nullable boolean NOT
-- NULL DEFAULT TRUE` to `public._mdb_field_types` (idempotent -- `ADD
-- COLUMN IF NOT EXISTS`) in the named application's own database, and
-- records THIS script's own number (9) in the per-application ledger
-- unconditionally. Every EXISTING row of `_mdb_field_types` (one per
-- field this application already declared, via `0003`'s original
-- `CREATE TABLE` or `0006`'s own backfill) picks up `enum_json = NULL`,
-- `nullable = TRUE` from the column defaults -- exactly the contract's
-- own default declaration for a field that predates this constraint
-- concept entirely (D-2 (2): "nullable の既定は true...これは既存挙動を
-- 宣言化するものである").
--
-- IDEMPOTENT: `ADD COLUMN IF NOT EXISTS` + `ON CONFLICT (upgrade_number)
-- DO NOTHING` on the ledger INSERT -- safe to re-run against the same
-- application any number of times.
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
-- hardening) -- needed here too, since `_mdb_field_types` is owned by
-- the developer role.
GRANT :"developer_role" TO CURRENT_USER WITH SET TRUE;

BEGIN;
SET LOCAL ROLE :"developer_role";

-- Same shape `0003_provision_application.sql`'s own revision creates for
-- a brand-new application (design D-2 (1)/(4)) -- added here for an
-- EXISTING one that predates that revision. `IF NOT EXISTS` makes this a
-- harmless no-op against a database this WP's own updated `0003` already
-- provisioned.
ALTER TABLE public._mdb_field_types ADD COLUMN IF NOT EXISTS enum_json text NULL;
ALTER TABLE public._mdb_field_types ADD COLUMN IF NOT EXISTS nullable boolean NOT NULL DEFAULT TRUE;

-- This script's own number, unconditionally (design §8.1: static scanner
-- requires ONE statement targeting this table to contain BOTH `ON
-- CONFLICT` and the bare integer literal `9`, de-zero-padded).
INSERT INTO public._mdb_platform_upgrades (upgrade_number, script_name)
VALUES (9, '0009_field_constraints_upgrade.sql')
ON CONFLICT (upgrade_number) DO NOTHING;

COMMIT;
-- `SET LOCAL ROLE` above reverted automatically at `COMMIT`; the temporary
-- membership itself is revoked explicitly below rather than left to
-- accrue.
REVOKE :"developer_role" FROM CURRENT_USER;

\c mitatedb_platform
