-- MitateDB-api PostgreSQL upgrade -- 0010: create `public._mdb_idempotency`
-- (contract 1.7.0 `structured_operations.idempotency`, design docs/design/
-- PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md D-5, 追補 2
-- S-a/S-b/S-f; 監督裁定集約 rulings-r5-r6.md I-1) onto an application
-- provisioned BEFORE Phase 9 WP-3c.
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
--     -f 0010_idempotency_records_upgrade.sql
--
-- CLASSIFICATION (work order docs/work-orders/
-- WORK_ORDER_PHASE9_CONTRACT_170_V1.md §2 WP-3c, design §8.1): a
-- per-application UPGRADE script -- `0003`'s own revision (this SAME WP)
-- reaches a NEWLY provisioned application via its own `CREATE TABLE`,
-- this script reaches an EXISTING one via `CREATE TABLE IF NOT EXISTS`;
-- both reach the SAME end state. Named `NNNN_<name>_upgrade.sql` (design
-- §8.1 item 1) so the static ledger-discipline scanner (`tests/test_
-- platform_upgrade_ledger_scan.py`) picks it up.
--
-- WHAT THIS DOES: creates `public._mdb_idempotency (key text PRIMARY
-- KEY, digest text NOT NULL, response_json text NOT NULL, created_at_ms
-- bigint NOT NULL)` (idempotent -- `CREATE TABLE IF NOT EXISTS`) in the
-- named application's own database, grants the runtime role full DML on
-- it (`SELECT`/`INSERT`/`UPDATE`/`DELETE` -- UNLIKE `_mdb_schema_
-- revision`/`_mdb_field_types`, which the runtime role never touches:
-- `ApplicationCell.transact`'s own idempotency lookup/reap/write all run
-- over the RUNTIME connection, the same one its own data DML already
-- uses, I-1), and records THIS script's own number (10) in the
-- per-application ledger unconditionally.
--
-- IDEMPOTENT: `CREATE TABLE IF NOT EXISTS` + `ON CONFLICT (upgrade_
-- number) DO NOTHING` on the ledger INSERT -- safe to re-run against the
-- same application any number of times. The `GRANT` statements are
-- idempotent by nature (re-granting an already-held privilege is a
-- harmless no-op).
--
-- WHY A SCRIPT, NOT A FUNCTION: reaching the target application's own
-- database requires actually being connected to it (`\c` below), the
-- same reason `0003_provision_application.sql`'s own header gives.

\set ON_ERROR_STOP on

SELECT database_name, runtime_role, developer_role FROM mitatedb_registry.applications
    WHERE application_id = :'app_id' \gset

\c :database_name

-- Same temporary-membership ritual as `0009_field_constraints_upgrade.
-- sql`'s own header comment explains (PostgreSQL 16's own ownership-
-- transfer hardening) -- needed here too, since `_mdb_idempotency` is
-- owned by the developer role.
GRANT :"developer_role" TO CURRENT_USER WITH SET TRUE;

BEGIN;
SET LOCAL ROLE :"developer_role";

-- Same shape `0003_provision_application.sql`'s own revision creates for
-- a brand-new application (design D-5) -- added here for an EXISTING one
-- that predates that revision. `IF NOT EXISTS` makes this a harmless
-- no-op against a database this WP's own updated `0003` already
-- provisioned.
CREATE TABLE IF NOT EXISTS public._mdb_idempotency (
    key            text        PRIMARY KEY,
    digest         text        NOT NULL,
    response_json  text        NOT NULL,
    created_at_ms  bigint      NOT NULL
);

-- UNLIKE `_mdb_schema_revision`/`_mdb_field_types` (developer-connection
-- only), the runtime role writes and reads this table directly --
-- `ApplicationCell.transact`'s own idempotency lookup/reap/write all run
-- over `self._runtime`, the same connection its own data DML already
-- runs on (design D-5's own "record は data tx と同一 tx で書く" applied
-- to the mutate path). Explicit `GRANT` here (rather than relying on
-- `ALTER DEFAULT PRIVILEGES`, which only reaches tables created AFTER it
-- was set) because this table is being retrofitted onto an application
-- whose own `ALTER DEFAULT PRIVILEGES` ran years before this table
-- existed to be covered by it.
GRANT SELECT, INSERT, UPDATE, DELETE ON public._mdb_idempotency TO :"runtime_role";

-- This script's own number, unconditionally (design §8.1: static scanner
-- requires ONE statement targeting this table to contain BOTH `ON
-- CONFLICT` and the bare integer literal `10`, de-zero-padded).
INSERT INTO public._mdb_platform_upgrades (upgrade_number, script_name)
VALUES (10, '0010_idempotency_records_upgrade.sql')
ON CONFLICT (upgrade_number) DO NOTHING;

COMMIT;
-- `SET LOCAL ROLE` above reverted automatically at `COMMIT`; the temporary
-- membership itself is revoked explicitly below rather than left to
-- accrue.
REVOKE :"developer_role" FROM CURRENT_USER;

\c mitatedb_platform
