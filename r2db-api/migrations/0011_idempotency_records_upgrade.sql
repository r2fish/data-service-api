-- r2db-api PostgreSQL upgrade -- 0011: adds the per-application
-- idempotency-record side table (contract 1.7.0 R-5, design docs/design/
-- PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md §3 D-5, work
-- order docs/work-orders/WORK_ORDER_PHASE9_CONTRACT_170_V1.md §2 WP-2c).
-- Mirrors `0010_field_constraints_upgrade.sql`'s own structure and
-- reasoning almost verbatim -- see that file's header for the full
-- rationale of every grant/revoke below, repeated only where this
-- script's own content differs.
--
-- WHO RUNS THIS: the operator/deploy tooling (or `python -m r2db_api.ops
-- upgrade-applications`, which runs this exact script once per
-- application whose own ledger does not yet record upgrade `11`),
-- connected to `r2dbsvc_platform` as `r2dbsvc_control`:
--
--   psql "$R2DBSVC_CONTROL_DSN" -v app_slug='myapp' \
--     -f 0011_idempotency_records_upgrade.sql
--
-- CLASSIFICATION (design §8.1's own naming regime): a per-application
-- UPGRADE script, the same class as `0009`/`0010` -- distinct from the
-- one-time platform/per-application migrations already applied and from
-- `0003_provision_application.sql` itself, a TEMPLATE this same WP
-- revises so a NEWLY provisioned application gets this table/ledger
-- entry directly, pre-seeded. `0003`'s revision and this script are
-- issued as a PAIR (the `0009`/`0003`, `0010`/`0003` precedent): a new
-- application reaches the table via `0003`, an existing one via this
-- script -- both reach the SAME end state
-- (`tests/test_platform_upgrade_ledger_scan.py::test_real_migrations_
-- three_way_match` holds both to the identical `{9, 10, 11}` number set).
--
-- WHAT THIS DOES: creates `public._r2db_idempotency` (idempotent) in the
-- named application's own database if missing, records upgrade `11` in
-- the platform-upgrade ledger (`ON CONFLICT (upgrade_number) DO NOTHING`
-- -- also idempotent), and re-installs `public._r2db_missing_rls` with
-- `CREATE OR REPLACE VIEW` so this application's own copy also excludes
-- this newly created table from its own RLS-coverage check.
--
-- NO EARLY-QUIT SKIP PATH (design D-3(c) point 3, same reasoning as
-- `0009`/`0010`'s own header): this script carries none of psql's own
-- backslash-q meta-command literally, anywhere.
--
-- IDEMPOTENT: `CREATE TABLE IF NOT EXISTS` + `ON CONFLICT (upgrade_
-- number) DO NOTHING` + `CREATE OR REPLACE VIEW` -- safe to re-run
-- against the same application any number of times.
--
-- ATOMIC (design D-3(c) point 1): the table's creation, the ledger
-- INSERT recording upgrade `11`, and the `_r2db_missing_rls`
-- redefinition all run inside the SAME `BEGIN ... COMMIT` block below.
--
-- SIDE-TABLE SHAPE (D-5 (1)(i)/(6)): `idempotency_key` primary key,
-- `request_digest` (the sha256 hex `structured_operations.idempotency.
-- record` describes), `kind` ("mutation"/"schema", which payload shape
-- `response` carries), `response` (jsonb -- exactly what a replay needs
-- to answer verbatim, ruling I-8: the ORIGINAL `MutationOutcome`'s
-- `affected`/`assigned_addresses`, or the ORIGINAL `SchemaOutcome`'s
-- `revision`), and `expires_at` (when this record stops being "present",
-- ruling I-6 -- compared against PostgreSQL's own `now()`, not a client
-- clock, since this table is shared by concurrent requests unlike
-- `ApplicationCell`'s single-process dict). No `recorded_at` column: the
-- ONLY consumer of a record's age is the `expires_at` comparison itself,
-- computed once at write time (`now() + idempotency_retention_ms`) -- a
-- separate `recorded_at` would be redundant state to keep in sync.
--
-- WHY NO EXPLICIT GRANT/REVOKE BLOCK (unlike `0010`'s own `_r2db_field_
-- constraints`, which explicitly narrows the runtime role down to
-- `SELECT`-only): THIS table is written by BOTH roles at request time --
-- the runtime role (`transact`, a single-entity/cross-entity mutation)
-- AND the developer role (`apply_schema`, a schema operation) -- unlike
-- `_r2db_field_constraints`, which only the developer role ever writes.
-- `0003`'s own standing `ALTER DEFAULT PRIVILEGES FOR ROLE developer_role
-- IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO
-- runtime_role` already grants the runtime role exactly the four DML
-- privileges this table's own access pattern needs (`SELECT`/`INSERT`
-- always, `DELETE` for the lazy-reclaim sweep, `UPDATE` unused but
-- harmless) the instant this table is created under the developer role
-- below -- no separate grant/revoke narrowing is correct here, unlike
-- `_r2db_field_constraints`'s intentionally read-only-to-runtime shape.
--
-- NO ROW LEVEL SECURITY (same reasoning as `_r2db_platform_upgrades`/
-- `_r2db_field_constraints`'s own identical choice, design D-3(a)'s own
-- note): this table's own access pattern (both roles, one application's
-- own database, D-3 database-per-application) needs no per-row isolation
-- of its own beyond the DATABASE-level isolation every application
-- already has.

\set ON_ERROR_STOP on

SELECT database_name, runtime_role, developer_role FROM r2dbsvc_registry.applications
    WHERE application_slug = :'app_slug' \gset

\c :database_name

-- Same temporary-membership ritual `0003_provision_application.sql`'s own
-- header comment explains (PostgreSQL 16's own ownership-transfer
-- hardening) -- needed here too, since the table below must be owned by
-- the developer role, not by `r2dbsvc_control`.
GRANT :"developer_role" TO CURRENT_USER WITH SET TRUE;

BEGIN;
SET LOCAL ROLE :"developer_role";

CREATE TABLE IF NOT EXISTS public._r2db_idempotency (
    idempotency_key text        PRIMARY KEY,
    request_digest  text        NOT NULL,
    kind            text        NOT NULL,
    response        jsonb       NOT NULL,
    expires_at      timestamptz NOT NULL
);
-- Ruling I-6: the lazy reclaim (`DELETE ... WHERE expires_at <= now()`,
-- `PostgresCell._idempotency_lookup`/`_idempotency_reserve`) scans this
-- column on every lookup -- an index keeps that scan cheap regardless of
-- how many elapsed records have accumulated between reclaims.
CREATE INDEX IF NOT EXISTS _r2db_idempotency_expires_at_idx ON public._r2db_idempotency (expires_at);
GRANT SELECT ON public._r2db_idempotency TO SESSION_USER;
GRANT USAGE  ON SCHEMA public TO SESSION_USER;
INSERT INTO public._r2db_platform_upgrades (upgrade_number, script_name)
    VALUES (11, '0011_idempotency_records_upgrade.sql')
    ON CONFLICT (upgrade_number) DO NOTHING;

-- Design D-3(e)(ii) (same reasoning as `0009`/`0010`'s own identical
-- block): `CREATE OR REPLACE VIEW` re-installs the view with this table
-- added to the exclusion list -- the template (`0003`) and every
-- per-application upgrade script that touches this view must always
-- carry the exact same body.
CREATE OR REPLACE VIEW public._r2db_missing_rls AS
    SELECT c.relname AS table_name
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relkind = 'r'
      AND c.relname NOT IN ('_r2db_schema_revision', '_r2db_platform_upgrades', '_r2db_field_constraints', '_r2db_idempotency')
      AND (c.relrowsecurity = false OR c.relforcerowsecurity = false);
GRANT SELECT ON public._r2db_missing_rls TO :"runtime_role";

COMMIT;
-- `SET LOCAL ROLE` above reverted automatically at `COMMIT`; the temporary
-- membership itself is revoked explicitly below rather than left to accrue
-- (mirrors `0003_provision_application.sql`'s own closing comment).
REVOKE :"developer_role" FROM CURRENT_USER;

\c r2dbsvc_platform
