-- MitateDB-api PostgreSQL provisioning -- 0012: role `CONNECTION LIMIT`
-- raised to match each role's own real pool composition (Phase 10 phase,
-- work order WP-4f, supervisor ruling 2026-09-09; peer-symmetric with
-- r2db-api's own `0013_role_connection_limits.sql` -- same role classes,
-- same arithmetic, no code shared between peers, requester ruling
-- 2026-09-03)
--
-- WHO RUNS THIS: the operator, connected to the `mitatedb_platform`
-- database AS the `mitatedbsvc_provision` role -- the same role/connection
-- 0002/0005/0007/0011 already run as. Run once, any time after `0002`
-- exists (L-4 correction, WP-4 integration review 2026-09-10, peer-
-- symmetric with r2db-api's own same-numbered correction) -- never on
-- `0007`/`0011`, which this file neither reads nor writes: sections 1
-- and 3 `ALTER`/replace against `mitatedbsvc_api`/`mitatedbsvc_
-- controlplane` and `begin_provision_application` (all three created by
-- `0002` itself), and section 2 reads that same migration's own
-- `applications` table. `0005` has no object this file's own statements
-- reference, but every fixture applies it in this position anyway
-- (operator sequence parity); order relative to 0006/0007/0008/0009/
-- 0010/0011 does not matter at all -- this is a platform single-shot
-- migration, those are either platform declarations/process-ceiling
-- migrations or per-application upgrade scripts. This header previously
-- said "after 0011", which was never true):
--
--   psql "$MITATEDB_PROVISION_DSN" -v ON_ERROR_STOP=1 -f 0012_role_connection_limits.sql
--
-- `-v ON_ERROR_STOP=1` must be passed on every `-f` invocation -- without
-- it, psql exits 0 even when a statement in this file errors out.
--
-- WHAT THIS FILE DOES AND WHY (r2db-api's own WP-4e finding, WP-4f ruling
-- point 1 -- applied symmetrically to this peer): the conformance
-- investigation on r2db-api's own `[r2db-api-socket]` plug traced a real
-- production defect (not a test-harness artifact) to a PostgreSQL role's
-- `CONNECTION LIMIT` sitting below the real worst-case number of
-- simultaneous connections the process using that role can open. This
-- peer's own architecture differs in mechanism (this peer's platform-plane
-- stores mostly open one connection per call rather than r2db-api's
-- persistent `_RolePool`, and `mitatedb_api.main`'s own per-application
-- `PostgresBackend` never pools at all -- see `mitatedb_api.config.role_
-- pool_size`'s own docstring) but the same worst-case-concurrent-
-- connections-vs-role-limit shape applies once real concurrency reaches
-- these roles (Phase 10 WP-8b: this peer's own handlers now delegate their
-- synchronous section to the threadpool too), so the SAME four role
-- classes are raised to the SAME floor, peer-symmetrically:
--
--   * `mitatedbsvc_api` -- `mitatedb_api.main`'s own platform pool
--     (`PostgresCredentialStore`'s `BoundedConnectionPool`, pool-sized to
--     the declared `max_concurrency` ceiling since Phase 10 WP-4e, default
--     32, `mitatedb_api.config.role_pool_size`) PLUS `Postgres
--     ApplicationAuditSink`'s own per-write transient connections against
--     the SAME role (worst case, one per in-flight request, also bounded
--     by `max_concurrency`) -- 2 x 32 = 64, against a `CONNECTION LIMIT`
--     of only 20 (`0002_registry_and_functions.sql`).
--   * `mitatedbsvc_controlplane` -- this process' own 4 platform-plane
--     stores (`PostgresApplicationRegistry`/`PostgresCredentialRegistry`/
--     `PostgresControlCredentialStore`/the `control_audit` writer),
--     peer-symmetric worst case with r2db-api's own measured 16 (4 stores
--     x 4), against a `CONNECTION LIMIT` of only 10.
--   * every served application's own `<id>_rt`/`<id>_dv` roles -- peer-
--     symmetric with r2db-api's own `PostgresCell` pool sizing (this
--     peer's equivalent worst case, one connection per in-flight request,
--     bounded by the SAME declared `max_concurrency` ceiling, default 32)
--     -- against `CONNECTION LIMIT` 20/10 respectively (migration 0002).
--
-- Floor = (worst-case pool composition) + 4 (the same fixed operator-
-- headroom margin r2db-api's own `0013_role_connection_limits.sql`
-- applies). Full arithmetic recorded in `MitateDB-api/docs/`'s own
-- provisioning runbook, "role CONNECTION LIMIT" table:
--
--   mitatedbsvc_api           20 -> 68   (2 stores x concurrency 32 = 64, +4)
--   mitatedbsvc_controlplane  10 -> 20   (4 stores x fixed floor 16, +4)
--   <id>_rt (runtime)         20 -> 36   (1 store x concurrency 32 = 32, +4)
--   <id>_dv (developer)       10 -> 36   (1 store x concurrency 32 = 32, +4)
--
-- `mitatedbsvc_provision` (short-lived, one-shot CLI/provisioning
-- connections only -- no persistent pool at all; current `CONNECTION
-- LIMIT 5` already comfortably covers realistic concurrent operator/CI
-- usage) and `mitatedbsvc_auditreader` (1 store x fixed floor 4; current
-- `CONNECTION LIMIT 5` already >= that) are deliberately left untouched --
-- like every other migration in this set, this file only ever `ALTER`s a
-- role whose CURRENT limit is BELOW its own computed floor.
--
-- `ops verify-declarations` (new check F-16, `mitatedb_api.platform_
-- declarations.check_role_connection_limits`) reads each of these roles'
-- OWN `pg_catalog.pg_roles.rolconnlimit` back and compares it against the
-- SAME pool-composition arithmetic this migration bakes in MINUS the
-- fixed +4 operator-headroom margin (L-1, WP-4 integration review
-- 2026-09-10, peer-symmetric with r2db-api's own same-numbered note):
-- F-16 checks the bare "worst-case pool" floor -- e.g. 64 for
-- `mitatedbsvc_api`, not this migration's own 68 -- a strictly WEAKER,
-- never stronger, bound than what this migration bakes in; harmless in
-- effect, since this migration's own +4 margin already clears F-16's
-- floor with room to spare, but the two are not the identical formula.
--
-- IDEMPOTENCY: every `ALTER ROLE ... CONNECTION LIMIT <n>` re-applies to
-- the same terminal state every time it runs. The per-application loop
-- below (section 2, already-provisioned applications) and the `CREATE OR
-- REPLACE FUNCTION` (section 3, future applications) are likewise
-- idempotent.
--
-- COMPATIBILITY WITH THE ALREADY-DEPLOYED MitateDB-api INSTANCE: ADDITIVE
-- ONLY -- raises four connection ceilings, lowers none, drops nothing,
-- revokes nothing. `max_connections` must be re-checked against a cluster
-- already close to its own configured ceiling (`SHOW max_connections;`).

\set ON_ERROR_STOP on

BEGIN;

-- ===========================================================================
-- 1: platform-plane roles (one instance each, not per-application)
-- ===========================================================================

ALTER ROLE mitatedbsvc_api CONNECTION LIMIT 68;
ALTER ROLE mitatedbsvc_controlplane CONNECTION LIMIT 20;

-- ===========================================================================
-- 2: every ALREADY-PROVISIONED application's own runtime/developer roles.
-- `mitatedb_registry.applications` is a two-state registry (0002's own
-- header) -- a row registered but never (yet) provisioned has `runtime_
-- role`/`developer_role` still NULL, so this loop filters those out
-- explicitly (unlike r2db-api's own single-state registry, where a row's
-- mere existence already implies both columns are populated).
-- ===========================================================================

DO $$
DECLARE
    app record;
BEGIN
    FOR app IN
        SELECT runtime_role, developer_role
        FROM mitatedb_registry.applications
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
-- the new floor from now on. `CREATE OR REPLACE FUNCTION` mirrors 0002's
-- own definition verbatim -- the ONLY change is the four `CONNECTION
-- LIMIT` literals below (both the `CREATE ROLE` branch AND its own
-- `duplicate_object` / `ALTER ROLE` retry-safety fallback, M-2's own
-- comment in 0002). Left as a separate top-level statement outside the
-- `BEGIN`/`COMMIT` above, matching 0002's own convention of never
-- wrapping `CREATE FUNCTION` inside an explicit transaction block here.
-- ===========================================================================

CREATE OR REPLACE FUNCTION mitatedb_registry.begin_provision_application(
    p_app_id text,
    p_runtime_password text,
    p_developer_password text
) RETURNS TABLE(database_name text, runtime_role text, developer_role text)
LANGUAGE plpgsql
AS $fn$
DECLARE
    v_database_name text := 'mitatedb_app_' || p_app_id;
    v_runtime_role text := v_database_name || '_rt';
    v_developer_role text := v_database_name || '_dv';
BEGIN
    IF p_app_id !~ '^[a-z][a-z0-9_]{0,32}$' THEN
        RAISE EXCEPTION 'invalid application_id: %', p_app_id;
    END IF;

    -- Unchanged from 0002: NAMEDATALEN fail-loud check, same rationale.
    IF octet_length(v_developer_role) > 63 THEN
        RAISE EXCEPTION 'derived role name exceeds PostgreSQL NAMEDATALEN (63 bytes): %', v_developer_role;
    END IF;

    IF p_runtime_password IS NULL OR p_developer_password IS NULL
       OR length(p_runtime_password) < 16 OR length(p_developer_password) < 16 THEN
        RAISE EXCEPTION 'runtime/developer passwords must be supplied and at least 16 characters';
    END IF;

    IF EXISTS (
        SELECT 1 FROM mitatedb_registry.applications a
        WHERE a.application_id = p_app_id AND a.database_name IS NOT NULL
    ) THEN
        RAISE EXCEPTION 'application already provisioned: %', p_app_id;
    END IF;

    INSERT INTO mitatedb_registry.applications (application_id)
    VALUES (p_app_id)
    ON CONFLICT (application_id) DO NOTHING;

    -- Unchanged from 0002 (M-2): crash-retry safety via `duplicate_object`
    -- -> `ALTER ROLE` fallback, which deliberately does NOT re-specify
    -- `NOSUPERUSER`/`NOCREATEDB`/`NOCREATEROLE`/`NOINHERIT` -- see 0002's
    -- own comment for why (`mitatedbsvc_provision` is never superuser).
    BEGIN
        EXECUTE format(
            'CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT CONNECTION LIMIT 36',
            v_runtime_role, p_runtime_password
        );
    EXCEPTION WHEN duplicate_object THEN
        EXECUTE format(
            'ALTER ROLE %I LOGIN PASSWORD %L CONNECTION LIMIT 36',
            v_runtime_role, p_runtime_password
        );
    END;
    BEGIN
        EXECUTE format(
            'CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT CONNECTION LIMIT 36',
            v_developer_role, p_developer_password
        );
    EXCEPTION WHEN duplicate_object THEN
        EXECUTE format(
            'ALTER ROLE %I LOGIN PASSWORD %L CONNECTION LIMIT 36',
            v_developer_role, p_developer_password
        );
    END;

    PERFORM mitatedb_registry.assert_role_has_no_memberships(v_runtime_role);
    PERFORM mitatedb_registry.assert_role_has_no_memberships(v_developer_role);

    UPDATE mitatedb_registry.applications
    SET runtime_role = v_runtime_role, developer_role = v_developer_role
    WHERE application_id = p_app_id;

    RETURN QUERY SELECT v_database_name, v_runtime_role, v_developer_role;
END;
$fn$;

REVOKE ALL ON FUNCTION mitatedb_registry.begin_provision_application(text, text, text) FROM PUBLIC;
