-- r2db-api PostgreSQL provisioning -- 0002: control-plane registry + role
-- provisioning helpers
--
-- WHO RUNS THIS: the operator, connected to the `r2dbsvc_platform` database
-- (created by 0001) AS the `r2dbsvc_control` role -- never as the cluster
-- superuser, and never as the r2db-api application process. Run once, after
-- 0001, to install the registry table and the functions below; those
-- functions are then called by 0003/0004 (once per application onboarded/
-- removed). This file's own DDL is `CREATE SCHEMA IF NOT EXISTS` / `CREATE
-- OR REPLACE FUNCTION`, so re-running it is a no-op beyond refreshing the
-- function bodies.
--
-- WP-4 rework round 2 (supervisor ruling 2026-09-06, wp4-rework-2.md #2):
-- `-v ON_ERROR_STOP=1` must be passed on every `-f` invocation -- without
-- it, psql exits 0 even when a statement in this file errors out.
--
--   psql "$R2DBSVC_CONTROL_DSN" -v ON_ERROR_STOP=1 -f 0002_provisioning_functions.sql
--
-- `R2DBSVC_CONTROL_DSN` is an environment-variable name (the DSN for the
-- `r2dbsvc_control` role against `r2dbsvc_platform`); see r2db-api/docs/.
--
-- WHY THIS FILE NO LONGER CONTAINS THE FULL PROVISIONING FLOW (architecture
-- §8 "D-3 改訂" -- database-per-application): the previous revision of this
-- file provisioned an application entirely inside one plpgsql function
-- (`provision_application`), because schema/role/RLS objects can all be
-- created transactionally. Database-per-application breaks that: `CREATE
-- DATABASE` (and `DROP DATABASE`, for deprovisioning) MUST run as its own
-- top-level statement -- PostgreSQL explicitly refuses to run either
-- "inside a transaction block", which every statement inside a plpgsql
-- function body implicitly is. There is no workaround that keeps
-- provisioning a single atomic function call once a database, not just a
-- schema, is being created. 0001 already had to work around this exact
-- constraint for `r2dbsvc_platform` itself, via psql's `\gexec`, rather
-- than a function -- this file now applies that same idiom, at
-- application-onboarding scale, in 0003/0004.
--
-- What stays here, as functions, is exactly the part that *is* safely
-- transactional: creating the two login roles (a plain `CREATE ROLE`, no
-- transaction-block restriction) and registry bookkeeping. 0003/0004 call
-- these functions for that part, and handle `CREATE DATABASE`/`DROP
-- DATABASE` and the objects that must be created *inside* the new database
-- (which requires a `\c` reconnect -- another thing no single function
-- call can do, since one PostgreSQL connection cannot switch which
-- database it is connected to) as plain top-level SQL in a psql script.
--
-- Provisioning is therefore now a "begin" function (validate + create
-- roles + compute names, but do NOT yet register the application) followed
-- by 0003's script-level database/schema setup, followed by a "finish"
-- function (register in the registry) -- so a crash partway through 0003
-- never leaves the registry claiming an application is fully provisioned
-- when its database/schema setup did not complete. Deprovisioning mirrors
-- this: "begin" looks up the names (and fails loudly if the slug is not
-- registered -- a deliberate behavioural change from the previous
-- single-function `deprovision_application`, which silently no-op'd on an
-- unknown slug; see the runbook), 0004 drops the database/roles, and
-- "finish" removes the registry row only once that has succeeded.

\set ON_ERROR_STOP on

CREATE SCHEMA IF NOT EXISTS r2dbsvc_registry AUTHORIZATION r2dbsvc_control;

-- Bookkeeping only: which application slugs have been provisioned, and the
-- database/role names that resulted. Never reachable from any application
-- request path (SI-02: this schema has no application-facing role granted
-- anything on it at all). `database_name` replaces the previous
-- `schema_name` column: every application now gets one dedicated database
-- (its entities live in that database's `public` schema, not in a
-- control-plane-assigned schema name inside a shared database).
CREATE TABLE IF NOT EXISTS r2dbsvc_registry.applications (
    application_slug text PRIMARY KEY,
    database_name     text NOT NULL UNIQUE,
    runtime_role      text NOT NULL UNIQUE,
    developer_role    text NOT NULL UNIQUE,
    provisioned_at    timestamptz NOT NULL DEFAULT now()
);

REVOKE ALL ON SCHEMA r2dbsvc_registry FROM PUBLIC;
REVOKE ALL ON r2dbsvc_registry.applications FROM PUBLIC;

-- Step 1 of provisioning (called by 0003, before `CREATE DATABASE`):
-- validates the slug and passwords, creates the two login roles, and
-- returns the computed database/role names -- but does NOT yet write a
-- registry row, since the database those names refer to does not exist
-- yet. `0003_provision_application.sql` captures this function's output
-- via psql's `\gset` and uses it for every subsequent step.
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
BEGIN
    -- Same identifier syntax policy the application layer enforces
    -- (`r2db_api.structured.validate_identifier`'s pattern, restated here
    -- in SQL because this function is the actual point where the slug
    -- becomes catalog objects): lower-case only, so it can never collide
    -- case-insensitively with an unquoted identifier, and bounded so the
    -- resulting database/role names stay under PostgreSQL's 63-byte
    -- identifier limit once the `r2dbsvc_app_..._developer` decoration is
    -- added.
    IF p_app_slug !~ '^[a-z][a-z0-9_]{0,32}$' THEN
        RAISE EXCEPTION 'invalid application slug: %', p_app_slug;
    END IF;
    IF EXISTS (SELECT 1 FROM r2dbsvc_registry.applications WHERE application_slug = p_app_slug) THEN
        RAISE EXCEPTION 'application already provisioned: %', p_app_slug;
    END IF;
    IF p_runtime_password IS NULL OR p_developer_password IS NULL OR length(p_runtime_password) < 16 OR length(p_developer_password) < 16 THEN
        RAISE EXCEPTION 'runtime/developer passwords must be supplied and at least 16 characters';
    END IF;

    EXECUTE format(
        'CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT CONNECTION LIMIT 20',
        v_runtime_role, p_runtime_password
    );
    EXECUTE format(
        'CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT CONNECTION LIMIT 10',
        v_developer_role, p_developer_password
    );

    RETURN QUERY SELECT v_database_name, v_runtime_role, v_developer_role;
END;
$fn$;

REVOKE ALL ON FUNCTION r2dbsvc_registry.begin_provision_application(text, text, text) FROM PUBLIC;

-- Step 2 of provisioning (called by 0003, once the database and its
-- `public` schema/role setup have fully succeeded): records the
-- now-complete application in the registry.
CREATE OR REPLACE FUNCTION r2dbsvc_registry.finish_provision_application(
    p_app_slug text,
    p_database_name text,
    p_runtime_role text,
    p_developer_role text
) RETURNS void
LANGUAGE plpgsql
AS $fn$
BEGIN
    INSERT INTO r2dbsvc_registry.applications (application_slug, database_name, runtime_role, developer_role)
    VALUES (p_app_slug, p_database_name, p_runtime_role, p_developer_role);
END;
$fn$;

REVOKE ALL ON FUNCTION r2dbsvc_registry.finish_provision_application(text, text, text, text) FROM PUBLIC;

-- Step 1 of deprovisioning (called by 0004, before `DROP DATABASE`): looks
-- up the registered names for a slug. Unlike the previous single-function
-- `deprovision_application`, this raises loudly (`ON_ERROR_STOP` then
-- aborts 0004) rather than silently no-op'ing when the slug is not
-- registered -- see this file's header note.
CREATE OR REPLACE FUNCTION r2dbsvc_registry.begin_deprovision_application(p_app_slug text)
RETURNS TABLE(database_name text, runtime_role text, developer_role text)
LANGUAGE plpgsql
AS $fn$
BEGIN
    RETURN QUERY
        SELECT a.database_name, a.runtime_role, a.developer_role
        FROM r2dbsvc_registry.applications a
        WHERE a.application_slug = p_app_slug;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'application not provisioned: %', p_app_slug;
    END IF;
END;
$fn$;

REVOKE ALL ON FUNCTION r2dbsvc_registry.begin_deprovision_application(text) FROM PUBLIC;

-- Step 2 of deprovisioning (called by 0004, once the database has been
-- dropped and both roles removed): removes the registry row.
CREATE OR REPLACE FUNCTION r2dbsvc_registry.finish_deprovision_application(p_app_slug text) RETURNS void
LANGUAGE plpgsql
AS $fn$
BEGIN
    DELETE FROM r2dbsvc_registry.applications WHERE application_slug = p_app_slug;
END;
$fn$;

REVOKE ALL ON FUNCTION r2dbsvc_registry.finish_deprovision_application(text) FROM PUBLIC;
