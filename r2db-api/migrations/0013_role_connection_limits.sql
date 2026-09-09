-- r2db-api PostgreSQL provisioning -- 0013: role `CONNECTION LIMIT` raised
-- to match each role's own real pool composition (Phase 10 phase, work
-- order WP-4f, supervisor ruling 2026-09-09, following the WP-4e
-- conformance investigation's own finding -- see that WP's report)
--
-- WHO RUNS THIS: the operator, connected to the `r2dbsvc_platform` database
-- AS the `r2dbsvc_control` role -- the same role/connection 0002/0005/0006/
-- 0007/0008/0012 already run as. Run once, any time after `0002`/`0005`/
-- `0006`/`0007` exist (L-4 correction, WP-4 integration review
-- 2026-09-10) -- never on `0008`/`0012`, which this file neither reads
-- nor writes: sections 1 and 3 `ALTER`/replace against `r2dbsvc_api`
-- (0005) and `r2dbsvc_controlplane` (0006), section 2 reads `0002`'s own
-- `applications` table, and every fixture and this runbook's own §5
-- "Order of operations"/§4 apply this migration right after `0007` (the
-- same four migrations, in the same order, every time) -- order relative
-- to 0008/0009/0010/0011/0012 does not matter at all: this is a platform
-- single-shot migration, those are either platform declarations/process-
-- ceiling migrations or per-application upgrade scripts, design SS8.1
-- rule 2. This header previously said "after 0012", which was never
-- true:
--
--   psql "$R2DBSVC_CONTROL_DSN" -v ON_ERROR_STOP=1 -f 0013_role_connection_limits.sql
--
-- `-v ON_ERROR_STOP=1` must be passed on every `-f` invocation -- without
-- it, psql exits 0 even when a statement in this file errors out.
--
-- WHAT THIS FILE DOES AND WHY (WP-4e's own finding, WP-4f ruling point 1):
-- the conformance investigation that found the 6-plug gate's own
-- `[r2db-api-socket]` C-14/C-24/C-25 residue traced it to a REAL
-- production defect, not a test-harness artifact -- `r2db_api.
-- control_main`'s own control-plane process opens 4 Postgres stores
-- (`applications`/`credentials`/`control_credentials`/`audit`) against the
-- SAME `r2dbsvc_controlplane` role, each with its own pool (fixed
-- `pool_size` 4, WP-4e's own investigated-and-reverted default -- see that
-- process' own `build_control_app` comment), for a real worst case of
-- 4 stores x 4 = 16 simultaneous connections -- already exceeding
-- `0006_control_plane_http.sql`'s own `CONNECTION LIMIT 10` with a SINGLE
-- control-plane process, no test harness involved at all. The identical
-- shape recurs for two more role classes:
--
--   * `r2dbsvc_api` -- `r2db_api.main`'s own `credentials` + `durable_
--     audit` stores, EACH pool-sized to the declared `ResourceLimits.
--     concurrency` ceiling since Phase 10 WP-4e (default 32, `r2db_api.
--     limits.role_pool_size`) -- 2 stores x 32 = 64, against a
--     `CONNECTION LIMIT` of only 10 (`0005_credential_store.sql`).
--   * every served application's own `<slug>_runtime`/`<slug>_developer`
--     roles -- `r2db_api.postgres.PostgresCell`'s own pool, ALSO sized to
--     `concurrency` since Phase 10 WP-8a (default 32) -- against
--     `CONNECTION LIMIT` 20/10 respectively (migrations 0002/0006).
--
-- This migration raises exactly these four role classes to a floor of
-- (worst-case pool composition) + 4 (a fixed operator-headroom margin --
-- room for one interactive `psql`/diagnostic connection alongside the
-- pool at its own declared peak, the same margin applied uniformly across
-- every role this file touches). Full arithmetic recorded in
-- `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` section 4's own
-- "role CONNECTION LIMIT" table:
--
--   r2dbsvc_api           10 -> 68   (2 stores x concurrency 32 = 64, +4)
--   r2dbsvc_controlplane  10 -> 20   (4 stores x fixed pool_size 4 = 16, +4)
--   <slug>_runtime        20 -> 36   (1 store x concurrency 32 = 32, +4)
--   <slug>_developer      10 -> 36   (1 store x concurrency 32 = 32, +4)
--
-- `r2dbsvc_control` (short-lived, one-shot CLI/provisioning connections
-- only -- no persistent pool at all; current `CONNECTION LIMIT 5` already
-- comfortably covers realistic concurrent operator/CI usage) and
-- `r2dbsvc_auditreader` (1 store x fixed `pool_size` 4 = 4; current
-- `CONNECTION LIMIT 5` already >= that) are deliberately left untouched --
-- like every other migration in this set, this file only ever `ALTER`s a
-- role whose CURRENT limit is BELOW its own computed floor.
--
-- `ops verify-declarations` (new check F-16, `r2db_api.platform_
-- declarations.check_role_connection_limits`) reads each of these roles'
-- OWN `pg_catalog.pg_roles.rolconnlimit` back and compares it against the
-- SAME pool-composition arithmetic this migration bakes in MINUS the
-- fixed +4 operator-headroom margin (L-1, WP-4 integration review
-- 2026-09-10: F-16 checks the bare "worst-case pool" floor -- e.g. 64 for
-- `r2dbsvc_api`, not this migration's own 68 -- a strictly WEAKER, never
-- stronger, bound than what this migration bakes in; harmless in effect,
-- since this migration's own +4 margin already clears F-16's floor with
-- room to spare, but the two are not the identical formula), so a future
-- deployment that raises `ResourceLimits.concurrency` without a follow-up
-- migration like this one is caught at verify time instead of silently
-- reopening this exact failure mode.
--
-- IDEMPOTENCY: every `ALTER ROLE ... CONNECTION LIMIT <n>` re-applies to
-- the same terminal state every time it runs. The per-application loop
-- below (section 2, already-provisioned applications) and the `CREATE OR
-- REPLACE FUNCTION` (section 3, future applications) are likewise
-- idempotent -- re-running this file changes nothing beyond re-asserting
-- the same numbers.
--
-- COMPATIBILITY WITH THE ALREADY-DEPLOYED r2db-api INSTANCE: ADDITIVE
-- ONLY -- raises four connection ceilings, lowers none, drops nothing,
-- revokes nothing. `max_connections` must be re-checked against the
-- runbook's own updated worked example before applying this migration to
-- a cluster already close to its own configured ceiling (`SHOW max_
-- connections;`).

\set ON_ERROR_STOP on

BEGIN;

-- ===========================================================================
-- 1: platform-plane roles (one instance each, not per-application)
-- ===========================================================================

ALTER ROLE r2dbsvc_api CONNECTION LIMIT 68;
ALTER ROLE r2dbsvc_controlplane CONNECTION LIMIT 20;

-- ===========================================================================
-- 2: every ALREADY-PROVISIONED application's own runtime/developer roles.
-- `r2dbsvc_registry.applications` is a two-state registry (0006's own
-- header, section 1.1) -- a row registered via `register_application`
-- but never (yet) provisioned has `runtime_role`/`developer_role` still
-- NULL (0006 explicitly `DROP NOT NULL`s both columns), so this loop
-- filters those out explicitly, the same way r2db-api's own F-16 query
-- (`platform_declarations.py`) and MitateDB-api's `0012_role_connection_
-- limits.sql` section 2 both already do.
-- ===========================================================================

DO $$
DECLARE
    app record;
BEGIN
    FOR app IN
        SELECT runtime_role, developer_role
        FROM r2dbsvc_registry.applications
        WHERE runtime_role IS NOT NULL AND developer_role IS NOT NULL
    LOOP
        EXECUTE format('ALTER ROLE %I CONNECTION LIMIT 36', app.runtime_role);
        EXECUTE format('ALTER ROLE %I CONNECTION LIMIT 36', app.developer_role);
    END LOOP;
END;
$$;

COMMIT;

-- ===========================================================================
-- 3: FUTURE applications -- `begin_provision_application` provisions with
-- the new floor from now on. `CREATE OR REPLACE FUNCTION` mirrors 0006's
-- own replacement of 0002's original definition (same identifier/password
-- validation, same `FOR UPDATE` two-state duplicate check 0006 introduced
-- -- the ONLY change from 0006's own body is the two `CONNECTION LIMIT`
-- literals below). Left as a separate top-level statement outside the
-- `BEGIN`/`COMMIT` above, matching 0002/0006's own convention of never
-- wrapping `CREATE FUNCTION` inside an explicit transaction block here.
-- ===========================================================================

CREATE OR REPLACE FUNCTION r2dbsvc_registry.begin_provision_application(
    p_app_slug text,
    p_runtime_password text,
    p_developer_password text
) RETURNS TABLE(database_name text, runtime_role text, developer_role text)
LANGUAGE plpgsql
AS $fn$
DECLARE
    v_database_name text := 'r2dbsvc_app_' || p_app_slug;
    v_runtime_role text := 'r2dbsvc_app_' || p_app_slug || '_runtime';
    v_developer_role text := 'r2dbsvc_app_' || p_app_slug || '_developer';
    v_existing_database_name text;
BEGIN
    -- Unchanged from 0006: same identifier syntax policy, same password
    -- length floor, same two-state duplicate check.
    IF p_app_slug !~ '^[a-z][a-z0-9_]{0,32}$' THEN
        RAISE EXCEPTION 'invalid application slug: %', p_app_slug;
    END IF;
    IF p_runtime_password IS NULL OR p_developer_password IS NULL OR length(p_runtime_password) < 16 OR length(p_developer_password) < 16 THEN
        RAISE EXCEPTION 'runtime/developer passwords must be supplied and at least 16 characters';
    END IF;

    SELECT a.database_name INTO v_existing_database_name
        FROM r2dbsvc_registry.applications a
        WHERE a.application_slug = p_app_slug
        FOR UPDATE;
    IF FOUND AND v_existing_database_name IS NOT NULL THEN
        RAISE EXCEPTION 'application already provisioned: %', p_app_slug;
    END IF;

    EXECUTE format(
        'CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT CONNECTION LIMIT 36',
        v_runtime_role, p_runtime_password
    );
    EXECUTE format(
        'CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT CONNECTION LIMIT 36',
        v_developer_role, p_developer_password
    );

    RETURN QUERY SELECT v_database_name, v_runtime_role, v_developer_role;
END;
$fn$;

REVOKE ALL ON FUNCTION r2dbsvc_registry.begin_provision_application(text, text, text) FROM PUBLIC;
