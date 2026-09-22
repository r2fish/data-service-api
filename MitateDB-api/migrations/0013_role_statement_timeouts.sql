-- MitateDB-api PostgreSQL provisioning -- 0013: bounds every statement
-- `mitatedbsvc_auditreader` and every provisioned application's own
-- runtime/developer role runs without an explicit deadline (the writer
-- roles, `mitatedbsvc_api`/`mitatedbsvc_controlplane`, already carry a
-- role-level `statement_timeout` from `0007_platform_declarations.sql`;
-- this file closes the same gap for the three role classes 0007 does
-- not touch). R-87 (2026-09-23): 8 of the developer role's own
-- statements -- backend_postgres.py's developer-connection catalog
-- reads -- carry no explicit deadline either, but since R-87 each
-- issues its own per-transaction SET LOCAL statement_timeout/
-- lock_timeout, so this role-level bound no longer applies to them.
--
-- WHO RUNS THIS: the operator, connected to the `mitatedb_platform`
-- database AS the `mitatedbsvc_provision` role -- the same role/connection
-- 0002/0005/0007/0011/0012 already run as.
--
--   psql "$MITATEDB_PROVISION_DSN" -v ON_ERROR_STOP=1 -f 0013_role_statement_timeouts.sql
--
-- `-v ON_ERROR_STOP=1` must be passed on every `-f` invocation -- without
-- it, psql exits 0 even when a statement in this file errors out.
--
-- ORDER: this file must run after `0005_application_audit.sql` -- section
-- 1 below alters `mitatedbsvc_auditreader`, the role 0005 creates; running
-- this file before 0005 fails with an undefined-role error. This file
-- must also run after `0012_role_connection_limits.sql` -- both `CREATE
-- OR REPLACE` the identical `begin_provision_application` function, and
-- applying 0012 alone after this file would drop the `statement_timeout`
-- lines below from every FUTURE application's own role creation (existing
-- roles already carry the setting from section 1/2 below and are
-- unaffected). The only compensation for an out-of-order re-application
-- of 0012 alone is the next `inventory` run, which reports the new
-- application's item (6) as `unknown` again until this file runs once
-- more.
--
-- PERMISSIONS: PostgreSQL 16 grants `ALTER ROLE ... SET` only to a role
-- holding CREATEROLE with ADMIN OPTION on the target role -- CREATEROLE
-- carries that option automatically on a role it created itself. This
-- file's own `ALTER ROLE mitatedbsvc_auditreader` therefore succeeds only
-- when the CONNECTING role is the same role that created `mitatedbsvc_
-- auditreader` (normally `0005_application_audit.sql`'s own applier); a
-- cluster where a different role created it must grant ADMIN OPTION
-- explicitly first, or this file fails and rolls back with it (see
-- TRANSACTIONALITY below). Section 2 and section 3's own per-application
-- `ALTER ROLE`/`CREATE ROLE` statements carry the identical assumption
-- for each application's own runtime/developer role -- satisfied when the
-- CONNECTING role is the same role that ran every earlier `begin_
-- provision_application` call (normally `mitatedbsvc_provision`,
-- CREATEROLE's own implicit grant on a role it created).
--
-- TRANSACTIONALITY: the whole file -- section 1, section 2, and section
-- 3 -- runs inside one transaction. A permission failure anywhere in it
-- rolls back everything already applied in this run, leaving nothing
-- changed rather than a half-applied state.
--
-- IDEMPOTENCY: every `ALTER ROLE ... SET statement_timeout` re-applies
-- to the same terminal state every time it runs. The per-application
-- loop (section 2) and the `CREATE OR REPLACE FUNCTION` (section 3) are
-- likewise idempotent.
--
-- COMPATIBILITY WITH THE ALREADY-DEPLOYED MitateDB-api INSTANCE: ADDITIVE
-- ONLY -- adds a role-level session bound, drops nothing, revokes
-- nothing.

\set ON_ERROR_STOP on

BEGIN;

-- ===========================================================================
-- 1: mitatedbsvc_auditreader -- the one platform-plane role 0007 never
-- touches (0007 only ever names `:"api_role"`/`:"controlplane_role"`).
-- The auditreader's own monitoring/audit-reading queries otherwise run
-- with no statement-level bound at all.
-- ===========================================================================

ALTER ROLE mitatedbsvc_auditreader SET statement_timeout = '5000ms';

-- ===========================================================================
-- 2: every ALREADY-PROVISIONED application's own runtime/developer
-- roles. Mirrors 0012's own section 2: `mitatedb_registry.applications`
-- is a two-state registry, so this loop filters out rows registered but
-- never (yet) provisioned, and skips a role name the catalog no longer
-- carries (a deprovisioned application whose registry row still exists)
-- so one missing role can never abort the whole migration.
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
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = app.runtime_role) THEN
            EXECUTE format('ALTER ROLE %I SET statement_timeout = %L', app.runtime_role, '5000ms');
        END IF;
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = app.developer_role) THEN
            EXECUTE format('ALTER ROLE %I SET statement_timeout = %L', app.developer_role, '5000ms');
        END IF;
    END LOOP;
END;
$$;

-- ===========================================================================
-- 3: FUTURE applications -- `begin_provision_application` sets the same
-- role-level bound at provisioning time from now on. `CREATE OR REPLACE
-- FUNCTION` mirrors 0012's own definition verbatim -- the ONLY change is
-- the four `ALTER ROLE ... SET statement_timeout` statements below (one
-- per role, in both the `CREATE ROLE` branch AND its own `duplicate_
-- object` / `ALTER ROLE` retry-safety fallback). Runs inside the SAME
-- transaction as section 1 and section 2 above -- see TRANSACTIONALITY.
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
        EXECUTE format('ALTER ROLE %I SET statement_timeout = %L', v_runtime_role, '5000ms');
    EXCEPTION WHEN duplicate_object THEN
        EXECUTE format(
            'ALTER ROLE %I LOGIN PASSWORD %L CONNECTION LIMIT 36',
            v_runtime_role, p_runtime_password
        );
        EXECUTE format('ALTER ROLE %I SET statement_timeout = %L', v_runtime_role, '5000ms');
    END;
    BEGIN
        EXECUTE format(
            'CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT CONNECTION LIMIT 36',
            v_developer_role, p_developer_password
        );
        EXECUTE format('ALTER ROLE %I SET statement_timeout = %L', v_developer_role, '5000ms');
    EXCEPTION WHEN duplicate_object THEN
        EXECUTE format(
            'ALTER ROLE %I LOGIN PASSWORD %L CONNECTION LIMIT 36',
            v_developer_role, p_developer_password
        );
        EXECUTE format('ALTER ROLE %I SET statement_timeout = %L', v_developer_role, '5000ms');
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

COMMIT;
