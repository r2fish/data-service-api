-- r2db-api PostgreSQL provisioning -- 0002: application provisioning API
--
-- WHO RUNS THIS: the operator, connected to the `r2dbsvc_platform` database
-- (created by 0001) AS the `r2dbsvc_control` role -- never as the cluster
-- superuser, and never as the r2db-api application process. Run once, after
-- 0001, to install the provisioning/deprovisioning functions; those
-- functions are then what actually onboards/removes an application, and
-- are themselves idempotent-safe to call as new applications are added
-- (this file's own DDL is `CREATE SCHEMA IF NOT EXISTS` / `CREATE OR
-- REPLACE FUNCTION`, so re-running this file is also a no-op beyond
-- refreshing the function bodies).
--
--   psql "$R2DBSVC_CONTROL_DSN" -f 0002_provisioning_functions.sql
--
-- `R2DBSVC_CONTROL_DSN` is an environment-variable name (the DSN for the
-- `r2dbsvc_control` role against `r2dbsvc_platform`); see r2db-api/docs/.
--
-- WHAT "PROVISIONING ONE APPLICATION" MEANS (design D-3's three layers):
--   1. namespace  -- one PostgreSQL schema, `r2dbsvc_app_<slug>`, owned by
--                    that application's own developer role. The schema name
--                    is assigned here, by the control plane, from an
--                    operator-supplied slug -- never derived from anything
--                    an application client sends at request time.
--   2. privilege   -- two login roles: `..._runtime` (DML only: SELECT /
--                    INSERT / UPDATE / DELETE on the schema's tables, no
--                    CREATE) and `..._developer` (owns the schema, so it
--                    can DDL within it; still NOSUPERUSER / NOCREATEDB /
--                    NOCREATEROLE). Neither role can see or touch any other
--                    application's schema: no grant ever mentions a schema
--                    that isn't its own.
--   3. RLS         -- `PostgresCell._create_entity` (application code, not
--                    this file) additionally enables and FORCEs row-level
--                    security on every table it creates, with a policy
--                    naming exactly these two roles. This file creates the
--                    one RLS-protected table it owns directly
--                    (`_r2db_schema_revision`) the same way, so the pattern
--                    is consistent between provisioning-time and
--                    request-time table creation.
--
-- Connection pooling note (ties to `r2db_api.postgres._RolePool`): each
-- application's `runtime`/`developer` roles get their own dedicated login
-- credentials here specifically so the Python layer can hold one
-- connection pool per role, authenticated directly as that role, and never
-- issue `SET ROLE`. See `r2db_api/postgres.py`'s `_RolePool` docstring for
-- why that avoids the pool release-time reset hazard D-3 calls out, rather
-- than relying on remembering to reset a shared connection.

\set ON_ERROR_STOP on

CREATE SCHEMA IF NOT EXISTS r2dbsvc_registry AUTHORIZATION r2dbsvc_control;

-- Bookkeeping only: which application slugs have been provisioned, and the
-- schema/role names that resulted. Never reachable from any application
-- request path (SI-02: this schema has no application-facing role granted
-- anything on it at all).
CREATE TABLE IF NOT EXISTS r2dbsvc_registry.applications (
    application_slug text PRIMARY KEY,
    schema_name       text NOT NULL UNIQUE,
    runtime_role      text NOT NULL UNIQUE,
    developer_role    text NOT NULL UNIQUE,
    provisioned_at    timestamptz NOT NULL DEFAULT now()
);

REVOKE ALL ON SCHEMA r2dbsvc_registry FROM PUBLIC;
REVOKE ALL ON r2dbsvc_registry.applications FROM PUBLIC;

CREATE OR REPLACE FUNCTION r2dbsvc_registry.provision_application(
    p_app_slug text,
    p_runtime_password text,
    p_developer_password text
) RETURNS void
LANGUAGE plpgsql
AS $fn$
DECLARE
    v_schema text := 'r2dbsvc_app_' || p_app_slug;
    v_runtime_role text := 'r2dbsvc_app_' || p_app_slug || '_runtime';
    v_developer_role text := 'r2dbsvc_app_' || p_app_slug || '_developer';
BEGIN
    -- Same identifier syntax policy the application layer enforces
    -- (`r2db_api.structured.validate_identifier`'s pattern, restated here
    -- in SQL because this function is the actual point where the slug
    -- becomes catalog objects): lower-case only, so it can never collide
    -- case-insensitively with an unquoted identifier, and bounded so the
    -- resulting role/schema names stay under PostgreSQL's 63-byte
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

    -- 0001 revoked PUBLIC's default CONNECT on `r2dbsvc_platform`, so every
    -- application role needs it granted explicitly -- otherwise neither
    -- role can open a connection at all, regardless of what it is later
    -- granted inside its own schema.
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), v_runtime_role);
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), v_developer_role);

    -- PostgreSQL 16 auto-grants the role creator ADMIN OPTION on a role it
    -- creates, but deliberately not SET/INHERIT (this was a PG16 change
    -- specifically to avoid silently widening a CREATEROLE role's standing
    -- authority). `CREATE SCHEMA ... AUTHORIZATION` and `SET ROLE` both
    -- need SET, so it is granted explicitly here, used for exactly the
    -- statements below that must run *as* the developer role to be owned
    -- by it, and revoked again before this function returns -- so
    -- `r2dbsvc_control` never holds standing membership in any
    -- application's developer role between provisioning calls.
    EXECUTE format('GRANT %I TO %I WITH SET TRUE', v_developer_role, current_user);

    -- The developer role owns its own schema outright: that ownership *is*
    -- its DDL authority, scoped to exactly this one schema (SI-03: schema-
    -- changing capability requires elevated authority, and that authority
    -- cannot reach any other application's schema because ownership of one
    -- schema grants nothing on another). A freshly created schema has no
    -- PUBLIC privileges by default (unlike a freshly created database,
    -- which is why 0001 revokes those explicitly) so there is nothing to
    -- revoke here.
    EXECUTE format('CREATE SCHEMA %I AUTHORIZATION %I', v_schema, v_developer_role);

    -- Everything from here through `RESET ROLE` below creates objects
    -- *inside* that schema, which requires schema-owner-level privilege --
    -- so it runs as the developer role itself (`SET LOCAL ROLE`, scoped to
    -- this function's own transaction; there is no `RESET ROLE` needed for
    -- a *pooled connection*'s sake the way `r2db_api.postgres._RolePool`
    -- cares about, because this is a one-shot provisioning call, never a
    -- connection any application request reuses).
    EXECUTE format('SET LOCAL ROLE %I', v_developer_role);

    -- Runtime gets USAGE (can resolve names inside the schema) but is never
    -- granted CREATE on it, so it structurally cannot issue DDL there --
    -- independent of, and in addition to, the application-layer
    -- `developer: bool` check in `bind_schema_operation`.
    EXECUTE format('GRANT USAGE ON SCHEMA %I TO %I', v_schema, v_runtime_role);

    -- Schema-revision bookkeeping table, created directly here (not left to
    -- application code) so every provisioned application starts at
    -- revision 0 with its RLS policy already in place, matching the
    -- pattern `PostgresCell._create_entity` uses for entity tables it
    -- creates later.
    EXECUTE format(
        'CREATE TABLE %I._r2db_schema_revision (id boolean PRIMARY KEY DEFAULT TRUE, revision bigint NOT NULL DEFAULT 0, CONSTRAINT _r2db_schema_revision_singleton CHECK (id))',
        v_schema
    );
    EXECUTE format('INSERT INTO %I._r2db_schema_revision (id, revision) VALUES (TRUE, 0)', v_schema);
    EXECUTE format('ALTER TABLE %I._r2db_schema_revision ENABLE ROW LEVEL SECURITY', v_schema);
    EXECUTE format('ALTER TABLE %I._r2db_schema_revision FORCE ROW LEVEL SECURITY', v_schema);
    EXECUTE format(
        'CREATE POLICY schema_revision_application_isolation ON %I._r2db_schema_revision USING (current_user IN (%L, %L)) WITH CHECK (current_user IN (%L, %L))',
        v_schema, v_runtime_role, v_developer_role, v_runtime_role, v_developer_role
    );
    EXECUTE format('GRANT SELECT, UPDATE ON %I._r2db_schema_revision TO %I', v_schema, v_runtime_role);

    -- From here on, any table the developer role creates in this schema
    -- (i.e. every entity table `PostgresCell.apply_schema`'s `create_entity`
    -- path creates at request time) automatically grants the runtime role
    -- DML -- and only DML, never DDL -- the moment it exists, with no
    -- per-table grant statement required from the application process.
    EXECUTE format(
        'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA %I GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO %I',
        v_developer_role, v_schema, v_runtime_role
    );

    RESET ROLE;
    EXECUTE format('REVOKE %I FROM %I', v_developer_role, current_user);

    INSERT INTO r2dbsvc_registry.applications (application_slug, schema_name, runtime_role, developer_role)
    VALUES (p_app_slug, v_schema, v_runtime_role, v_developer_role);
END;
$fn$;

REVOKE ALL ON FUNCTION r2dbsvc_registry.provision_application(text, text, text) FROM PUBLIC;

CREATE OR REPLACE FUNCTION r2dbsvc_registry.deprovision_application(p_app_slug text) RETURNS void
LANGUAGE plpgsql
AS $fn$
DECLARE
    v_schema text;
    v_runtime_role text;
    v_developer_role text;
BEGIN
    SELECT schema_name, runtime_role, developer_role
    INTO v_schema, v_runtime_role, v_developer_role
    FROM r2dbsvc_registry.applications
    WHERE application_slug = p_app_slug;

    IF NOT FOUND THEN
        RETURN;
    END IF;

    -- Dropping the schema is an ownership-level operation, same reasoning
    -- as `provision_application` above: briefly assume the developer role
    -- (which owns it) rather than rely on `r2dbsvc_control` holding any
    -- standing broader privilege.
    EXECUTE format('GRANT %I TO %I WITH SET TRUE', v_developer_role, current_user);
    EXECUTE format('SET LOCAL ROLE %I', v_developer_role);
    EXECUTE format('DROP SCHEMA IF EXISTS %I CASCADE', v_schema);
    RESET ROLE;

    -- Dropping the roles outright removes every *membership* grant
    -- involving them (including the temporary one just above) automatically
    -- -- but not privileges granted *to* them on objects outside the schema
    -- just dropped, notably `GRANT CONNECT ON DATABASE` from provisioning.
    -- Postgres only lets the grantor (or someone with grant option) revoke
    -- that, not the grantee itself even if impersonated, so it is revoked
    -- here explicitly, as `r2dbsvc_control` (the original grantor), before
    -- `DROP ROLE` -- otherwise `DROP ROLE` fails with "cannot be dropped
    -- because some objects depend on it".
    EXECUTE format('REVOKE CONNECT ON DATABASE %I FROM %I', current_database(), v_runtime_role);
    EXECUTE format('REVOKE CONNECT ON DATABASE %I FROM %I', current_database(), v_developer_role);
    EXECUTE format('DROP ROLE IF EXISTS %I', v_runtime_role);
    EXECUTE format('DROP ROLE IF EXISTS %I', v_developer_role);
    DELETE FROM r2dbsvc_registry.applications WHERE application_slug = p_app_slug;
END;
$fn$;

REVOKE ALL ON FUNCTION r2dbsvc_registry.deprovision_application(text) FROM PUBLIC;
