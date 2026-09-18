-- MitateDB-api PostgreSQL provisioning -- 0014: raises the same four
-- role classes `0012_role_connection_limits.sql` raises, plus
-- `mitatedbsvc_auditreader`, to the concurrent demand of TWO revisions
-- of the same process serving traffic at once during a rollout window
-- (design `docs/design/MITATEDB_ROLLOUT_CONNECTION_LIMITS_V0_1.md` §4
-- candidate (a)).
--
-- WHO RUNS THIS: the operator, connected to the `mitatedb_platform`
-- database AS the `mitatedbsvc_provision` role -- the same role/
-- connection 0002/0005/0007/0011/0012/0013 already run as.
--
--   psql "$MITATEDB_PROVISION_DSN" -v ON_ERROR_STOP=1 -f 0014_role_connection_limits_rollout.sql
--
-- `-v ON_ERROR_STOP=1` must be passed on every `-f` invocation -- without
-- it, psql exits 0 even when a statement in this file errors out.
--
-- ORDER: this file must run after `0005_application_audit.sql` -- section
-- 1 below alters `mitatedbsvc_auditreader`, the role 0005 creates;
-- running this file before 0005 fails with an undefined-role error. This
-- file must also run after `0012_role_connection_limits.sql` AND
-- `0013_role_statement_timeouts.sql` -- the numbered set's own order is
-- `0012` -> `0013` -> `0014`. Both 0012 and 0013 `CREATE OR REPLACE` the
-- identical `begin_provision_application` function; this file does the
-- same, and its own replacement carries BOTH the raised `CONNECTION
-- LIMIT` (this file's own subject) AND the `statement_timeout` setting
-- 0013 added (0013:157,163,170,176). An out-of-order re-application of
-- `0012` ALONE after this file lowers `mitatedbsvc_api`/`mitatedbsvc_
-- controlplane` AND every EXISTING application's own runtime/developer
-- role back to 0012's own values (68/20/36 -- 0012:70-73), and drops the
-- `statement_timeout` setting 0013 added from every FUTURE application's
-- own role creation (0012's own `CREATE OR REPLACE FUNCTION` never
-- carries that line); `mitatedbsvc_auditreader` is unaffected, since
-- 0012 never alters it. An out-of-order re-application of `0013` ALONE
-- after this file leaves every EXISTING role's `CONNECTION LIMIT` and
-- `statement_timeout` unchanged, and only lowers the `CONNECTION LIMIT`
-- (to 36, 0012's own inherited value, which 0013 never changes) for
-- every FUTURE application's own role creation -- that FUTURE role still
-- carries `statement_timeout`, since 0013's own function replacement
-- already sets it. Both cases are compensated by re-applying this file
-- once more.
--
-- `mitatedbsvc_auditreader` IS ALTERED BELOW, unlike
-- `0012_role_connection_limits.sql`, whose own header (0012:78-79)
-- states `mitatedbsvc_auditreader` is deliberately left untouched
-- because a `CONNECTION LIMIT` of 5 already exceeds the single-process
-- floor of 4. That statement is accurate for ONE process; it is
-- overwritten here, not erased, because a rollout window runs TWO
-- revisions of the same process concurrently, doubling the role's own
-- real demand to 2 x 4 = 8 (+4 margin = 12), which the single-process
-- `CONNECTION LIMIT` of 5 no longer covers (design `docs/design/
-- MITATEDB_ROLLOUT_CONNECTION_LIMITS_V0_1.md` §4, 2026-09-18).
--
-- PERMISSIONS: PostgreSQL 16 grants `ALTER ROLE` (including a bare
-- `CONNECTION LIMIT` change) only to a role holding CREATEROLE with
-- ADMIN OPTION on the target role -- CREATEROLE carries that option
-- automatically on a role it created itself. This file's own `ALTER
-- ROLE` statements therefore succeed only when the CONNECTING role is
-- the same role that created each target role (normally
-- `mitatedbsvc_provision`, the applier of 0002/0005/every earlier
-- `begin_provision_application` call).
--
-- TRANSACTIONALITY: the whole file -- every role-class `ALTER ROLE`,
-- the per-application loop, and the `CREATE OR REPLACE FUNCTION` --
-- runs inside ONE transaction. A permission failure anywhere in it rolls
-- back everything already applied in this run, leaving nothing changed
-- rather than a half-applied state (mirrors 0013's own TRANSACTIONALITY
-- section; unlike 0012, whose own `CREATE OR REPLACE FUNCTION` sits
-- outside its `BEGIN`/`COMMIT`).
--
-- IDEMPOTENCY: every `ALTER ROLE ... CONNECTION LIMIT <n>` re-applies to
-- the same terminal state every time it runs. The per-application loop
-- below and the `CREATE OR REPLACE FUNCTION` are likewise idempotent.
--
-- COMPATIBILITY WITH THE ALREADY-DEPLOYED MitateDB-api INSTANCE:
-- ADDITIVE ONLY -- raises four connection ceilings further, lowers
-- none, drops nothing, revokes nothing. `max_connections` must be
-- re-checked against a cluster already close to its own configured
-- ceiling (`SHOW max_connections;`).

\set ON_ERROR_STOP on

BEGIN;

-- ===========================================================================
-- 1: platform-plane roles (one instance each, not per-application) --
-- including `mitatedbsvc_auditreader`, see the header note above.
-- ===========================================================================

ALTER ROLE mitatedbsvc_api CONNECTION LIMIT 132;
ALTER ROLE mitatedbsvc_controlplane CONNECTION LIMIT 36;
ALTER ROLE mitatedbsvc_auditreader CONNECTION LIMIT 12;

-- ===========================================================================
-- 2: every ALREADY-PROVISIONED application's own runtime/developer
-- roles. Mirrors 0012's own section 2 and 0013's own section 2:
-- `mitatedb_registry.applications` is a two-state registry, so this
-- loop filters out rows registered but never (yet) provisioned, and
-- skips a role name the catalog no longer carries (a deprovisioned
-- application whose registry row still exists) so one missing role can
-- never abort the whole migration.
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
            EXECUTE format('ALTER ROLE %I CONNECTION LIMIT 68', app.runtime_role);
        END IF;
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = app.developer_role) THEN
            EXECUTE format('ALTER ROLE %I CONNECTION LIMIT 68', app.developer_role);
        END IF;
    END LOOP;
END;
$$;

-- ===========================================================================
-- 3: FUTURE applications -- `begin_provision_application` provisions
-- with the new floor from now on. `CREATE OR REPLACE FUNCTION` mirrors
-- 0013's own definition verbatim -- the ONLY change is the four
-- `CONNECTION LIMIT` literals below (both the `CREATE ROLE` branch AND
-- its own `duplicate_object` / `ALTER ROLE` retry-safety fallback);
-- 0013's own `statement_timeout` lines are kept unchanged (see ORDER
-- above). Runs inside the SAME transaction as sections 1 and 2 above.
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
            'CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT CONNECTION LIMIT 68',
            v_runtime_role, p_runtime_password
        );
        EXECUTE format('ALTER ROLE %I SET statement_timeout = %L', v_runtime_role, '5000ms');
    EXCEPTION WHEN duplicate_object THEN
        EXECUTE format(
            'ALTER ROLE %I LOGIN PASSWORD %L CONNECTION LIMIT 68',
            v_runtime_role, p_runtime_password
        );
        EXECUTE format('ALTER ROLE %I SET statement_timeout = %L', v_runtime_role, '5000ms');
    END;
    BEGIN
        EXECUTE format(
            'CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT CONNECTION LIMIT 68',
            v_developer_role, p_developer_password
        );
        EXECUTE format('ALTER ROLE %I SET statement_timeout = %L', v_developer_role, '5000ms');
    EXCEPTION WHEN duplicate_object THEN
        EXECUTE format(
            'ALTER ROLE %I LOGIN PASSWORD %L CONNECTION LIMIT 68',
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
