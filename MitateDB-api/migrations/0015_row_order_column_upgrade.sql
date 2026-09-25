-- MitateDB-api PostgreSQL upgrade -- 0015: add the internal row-order
-- column `_mdb_row` (design docs/design/PHASE11_KEYSET_PAGING_V1.md D-2)
-- to every declared collection table in an application provisioned
-- BEFORE this WP.
--
-- WHO RUNS THIS: the operator/deploy tooling (or `python -m mitatedb_api.
-- ops upgrade-applications --lock-timeout <v>`, design D-4), connected to
-- `mitatedb_platform` as `mitatedbsvc_provision`, once per EXISTING
-- application whose own ledger does not yet carry this script's own
-- number (a database provisioned by the UPDATED `0003_provision_
-- application.sql` never runs this script against a real column gap --
-- every collection it creates already carries this column via `backend_
-- postgres.py::PostgresBackend.create_collection`; running this script
-- against one is then a harmless no-op over zero tables, see IDEMPOTENT
-- below):
--
--   psql "$MITATEDB_PROVISION_DSN" -v app_id='acme' \
--     -f 0015_row_order_column_upgrade.sql
--
-- CLASSIFICATION (design §9 WP-3, §8.1): a per-application UPGRADE
-- script -- `create_collection`'s own `CREATE TABLE` (this SAME WP)
-- reaches a NEWLY created collection, this script reaches every
-- EXISTING collection table an EXISTING application already carries; both
-- reach the SAME end state. Named `NNNN_<name>_upgrade.sql` (design §8.1
-- item 1) so the static ledger-discipline scanner (`tests/test_platform_
-- upgrade_ledger_scan.py`) picks it up.
--
-- WHAT THIS DOES: enumerates every table this application's own `public`
-- schema carries that is a declared COLLECTION -- a `BASE TABLE` in
-- `information_schema.tables`, excluding this package's own `_mdb_`-
-- prefixed bookkeeping tables and the reserved name `audit_events`
-- (`postgres_reserved_names.py`:14). There is no path that creates any
-- OTHER table in an application database through this package's own
-- normal request-handling code (R-1's own database-per-application
-- containment), so this enumeration is a SUPERSET of the declared-
-- collection set (safe against, e.g., a table a direct/raw connection
-- created outside this package's own code paths). For each one, runs
-- `ALTER TABLE ... ADD COLUMN IF NOT
-- EXISTS _mdb_row BIGINT GENERATED ALWAYS AS IDENTITY` -- the SAME
-- column definition `create_collection` gives a brand-new collection.
-- PostgreSQL numbers the collection's own EXISTING rows itself, in an
-- order that is stable but not necessarily insertion order (design §10
-- の 6, MitateDB-api/README.md's own upgrade-section disclosure). Then
-- records THIS script's own number (15) in the per-application ledger
-- unconditionally.
--
-- LOCK: every collection this application owns is rewritten inside ONE
-- transaction, so the ACCESS EXCLUSIVE lock each `ADD COLUMN ...
-- GENERATED ALWAYS AS IDENTITY` takes is held for the whole run -- total
-- hold time is proportional to the application's own data volume (design
-- §10 の 13, MitateDB-api/README.md's own upgrade-section disclosure).
-- `--lock-timeout` (`ops upgrade-applications`) bounds only the
-- ACQUISITION of each lock, never how long it is then held.
--
-- IDEMPOTENT: `ADD COLUMN IF NOT EXISTS` per table + `ON CONFLICT
-- (upgrade_number) DO NOTHING` on the ledger INSERT -- safe to re-run
-- against the same application any number of times.
--
-- WHY A SCRIPT, NOT A FUNCTION: reaching the target application's own
-- database requires actually being connected to it (`\c` below), the
-- same reason `0003_provision_application.sql`'s own header gives.

\set ON_ERROR_STOP on

SELECT database_name, developer_role FROM mitatedb_registry.applications
    WHERE application_id = :'app_id' \gset

\c :database_name

-- Same temporary-membership ritual as `0009_field_constraints_upgrade.
-- sql`'s own header comment explains (PostgreSQL 16's own ownership-
-- transfer hardening) -- needed here too, since every collection table is
-- owned by the developer role.
GRANT :"developer_role" TO CURRENT_USER WITH SET TRUE;

BEGIN;
SET LOCAL ROLE :"developer_role";

-- Column-level GRANTs do not exist on this table set: the runtime role's
-- existing table-level `ALTER DEFAULT PRIVILEGES` grant (`0003`) already
-- covers every column a table carries, this new one included, so no
-- GRANT statement is needed alongside the `ALTER TABLE` below.
DO $$
DECLARE
    collection_name text;
BEGIN
    FOR collection_name IN
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
          AND left(table_name, 5) <> '_mdb_'
          AND table_name <> 'audit_events'
    LOOP
        EXECUTE format(
            'ALTER TABLE public.%I ADD COLUMN IF NOT EXISTS _mdb_row BIGINT GENERATED ALWAYS AS IDENTITY',
            collection_name
        );
    END LOOP;
END $$;

-- This script's own number, unconditionally (design §8.1: static scanner
-- requires ONE statement targeting this table to contain BOTH `ON
-- CONFLICT` and the bare integer literal `15`, de-zero-padded).
INSERT INTO public._mdb_platform_upgrades (upgrade_number, script_name)
VALUES (15, '0015_row_order_column_upgrade.sql')
ON CONFLICT (upgrade_number) DO NOTHING;

COMMIT;
-- `SET LOCAL ROLE` above reverted automatically at `COMMIT`; the temporary
-- membership itself is revoked explicitly below rather than left to
-- accrue.
REVOKE :"developer_role" FROM CURRENT_USER;

\c mitatedb_platform
