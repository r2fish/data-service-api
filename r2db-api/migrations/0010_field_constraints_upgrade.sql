-- r2db-api PostgreSQL upgrade -- 0010: adds the per-application field-
-- constraints declaration registry (contract 1.7.0 R-2, design docs/
-- design/PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md §3 D-2,
-- work order docs/work-orders/WORK_ORDER_PHASE9_CONTRACT_170_V1.md §2
-- WP-2a). Mirrors `0009_platform_upgrades_ledger_upgrade.sql`'s own
-- structure and reasoning almost verbatim -- see that file's header for
-- the full rationale of every grant/revoke below, repeated only where
-- this script's own content differs.
--
-- WHO RUNS THIS: the operator/deploy tooling (or `python -m r2db_api.ops
-- upgrade-applications`, which runs this exact script once per
-- application whose own ledger does not yet record upgrade `10`),
-- connected to `r2dbsvc_platform` as `r2dbsvc_control`:
--
--   psql "$R2DBSVC_CONTROL_DSN" -v app_slug='myapp' \
--     -f 0010_field_constraints_upgrade.sql
--
-- CLASSIFICATION (design §8.1's own naming regime): a per-application
-- UPGRADE script, the same class as `0009` -- distinct from the one-time
-- platform/per-application migrations already applied and from `0003_
-- provision_application.sql` itself, a TEMPLATE this same WP revises so
-- a NEWLY provisioned application gets this table/ledger entry directly,
-- pre-seeded. `0003`'s revision and this script are issued as a PAIR
-- (the `0009`/`0003` precedent, "テンプレート改訂とper-app upgrade
-- scriptは対で出す"): a new application reaches the registry via `0003`,
-- an existing one via this script -- both reach the SAME end state
-- (`tests/test_platform_upgrade_ledger_scan.py::test_real_migrations_
-- three_way_match` holds both to the identical `{9, 10}` number set).
--
-- WHAT THIS DOES: creates `public._r2db_field_constraints` (idempotent)
-- in the named application's own database if missing, records upgrade
-- `10` in the platform-upgrade ledger (`ON CONFLICT (upgrade_number) DO
-- NOTHING` -- also idempotent), and re-installs `public._r2db_missing_
-- rls` with `CREATE OR REPLACE VIEW` so this application's own copy also
-- excludes this newly created table from its own RLS-coverage check.
--
-- NO EARLY-QUIT SKIP PATH (design D-3(c) point 3, same reasoning as
-- `0009`'s own header): this script carries none of psql's own
-- backslash-q meta-command literally, anywhere.
--
-- IDEMPOTENT: `CREATE TABLE IF NOT EXISTS` + `ON CONFLICT (upgrade_
-- number) DO NOTHING` + `CREATE OR REPLACE VIEW` -- safe to re-run
-- against the same application any number of times.
--
-- ATOMIC (design D-3(c) point 1): the table's creation/grants, the
-- ledger INSERT recording upgrade `10`, and the `_r2db_missing_rls`
-- redefinition all run inside the SAME `BEGIN ... COMMIT` block below.
--
-- SIDE-TABLE SHAPE (D-2 (4), (6)): `(entity_name, field_name)` primary
-- key, `nullable` (always present, `nullable: true` is the version-wide
-- default even before any row exists for a field) and `enum_values`
-- (jsonb array, `NULL` when no `enum` is declared). A row exists ONLY
-- for a field something was actually declared on (`r2db_api.structured.
-- FieldConstraints.is_declared`) -- a field with no row reports the
-- default. Physical column constraints (NOT NULL/CHECK) are deliberately
-- never added anywhere (§4 A-1); this table is the sole source of truth
-- `PostgresCell._load_field_constraints`/`_write_field_constraints` read
-- and write, never re-derived from `information_schema`.
--
-- WHY A SCRIPT, NOT A FUNCTION: reaching the target application's own
-- database requires actually being connected to it (`\c` below), the
-- same reason `0003_provision_application.sql`'s own header gives.

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

-- Design D-2 (4): no RLS on this table, same reasoning as `_r2db_
-- platform_upgrades`'s own identical note in `0009`/`0003` -- this
-- table's own access pattern (schema-operation-time reads/writes through
-- the developer role, and read-only lookups through the runtime role at
-- request time) needs no per-application row isolation of its own beyond
-- the DATABASE-level isolation every application already has (D-3 database-
-- per-application), and `FORCE ROW LEVEL SECURITY` would apply even to
-- this table's OWNER (the developer role), which is exactly the role
-- every write here (`apply_schema`'s `create_entity`/`add_field`/`alter_
-- field` branches) goes through.
CREATE TABLE IF NOT EXISTS public._r2db_field_constraints (
    entity_name text    NOT NULL,
    field_name  text    NOT NULL,
    nullable    boolean NOT NULL DEFAULT true,
    enum_values jsonb,
    PRIMARY KEY (entity_name, field_name)
);
-- Mirrors `0009`'s own identical revoke/grant block: `ALTER DEFAULT
-- PRIVILEGES FOR ROLE developer_role` (already standing, from this
-- application's own earlier `0003` run) would otherwise auto-grant the
-- runtime role full DML on this brand-new table the instant it is
-- created -- explicitly revoked, then granted back exactly `SELECT`
-- (runtime only ever READS declared constraints, at query/mutate/catalog
-- time; only the developer role, via a schema operation, ever writes
-- here).
REVOKE ALL    ON public._r2db_field_constraints FROM :"runtime_role";
GRANT  SELECT ON public._r2db_field_constraints TO :"runtime_role";
GRANT  SELECT ON public._r2db_field_constraints TO SESSION_USER;
GRANT  USAGE  ON SCHEMA public TO SESSION_USER;
INSERT INTO public._r2db_platform_upgrades (upgrade_number, script_name)
    VALUES (10, '0010_field_constraints_upgrade.sql')
    ON CONFLICT (upgrade_number) DO NOTHING;

-- Design D-3(e)(ii) (same reasoning as `0009`'s own identical block):
-- `CREATE OR REPLACE VIEW` re-installs the view with this table added to
-- the exclusion list -- the template (`0003`) and every per-application
-- upgrade script that touches this view must always carry the exact same
-- body.
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
-- membership itself is revoked explicitly below rather than left to accrue
-- (mirrors `0003_provision_application.sql`'s own closing comment).
REVOKE :"developer_role" FROM CURRENT_USER;

\c r2dbsvc_platform
