-- r2db-api PostgreSQL provisioning -- 0001: control-plane bootstrap
--
-- WHO RUNS THIS: a cluster administrator (e.g. the PostgreSQL superuser, or
-- an existing role with CREATEROLE and CREATEDB), connected as themselves.
-- This file is NEVER executed by the r2db-api application process, and the
-- application process never holds a credential capable of running it
-- (design D-3 / §5.3 C-2: "provisioning is run by an operator with a
-- different credential, not by the API process").
--
-- WHAT THIS FILE DOES: creates exactly one new login role
-- (`r2dbsvc_control`) and exactly one new database (`r2dbsvc_platform`).
-- Both names carry the `r2dbsvc_` prefix used by every object this
-- migration set creates, chosen specifically so nothing here can collide
-- with the already-running old r2db-api deployment on the existing VPS
-- (§5.3 C-1: "database name, role names, ... must all be distinctly
-- namespaced"). `r2dbsvc_control` is *not* superuser and cannot create
-- other databases beyond this one -- see the role definition below for the
-- exact privilege set and why each one is there.
--
-- IDEMPOTENCY: `CREATE ROLE`/`CREATE DATABASE` have no `IF NOT EXISTS` form
-- in PostgreSQL, so this file uses a `DO` block (roles) and a catalog check
-- (database) instead. Re-running this file is a no-op if 0001 already
-- succeeded.
--
-- Run with, e.g.:
--   psql "$R2DBSVC_BOOTSTRAP_ADMIN_DSN" \
--     -v control_password="$R2DBSVC_CONTROL_PASSWORD" \
--     -f 0001_bootstrap_control_plane.sql
--
-- `R2DBSVC_BOOTSTRAP_ADMIN_DSN` and `R2DBSVC_CONTROL_PASSWORD` are
-- environment-variable *names*; see r2db-api/docs/ for the full runbook.
-- This file never contains a real credential.
--
-- (The role-creation statement below uses psql's own `:'control_password'`
-- variable interpolation rather than a `DO $$ ... $$` block: psql expands
-- `:'var'` by substituting the raw input stream before it is ever sent to
-- the server, and it deliberately does NOT expand inside a dollar-quoted
-- function/DO body -- doing so would make it look like the password could
-- be dynamic SQL text influencing that body, which is exactly the kind of
-- thing D-4 asks this codebase to avoid. Expanding it into a plain,
-- non-dollar-quoted statement keeps the substitution visibly a single bind-
-- like value, not code.)

\set ON_ERROR_STOP on

-- LOGIN:        it authenticates the provisioning/migration process.
-- CREATEROLE:   it must create per-application runtime/developer roles
--               (0002's provisioning function).
-- NOSUPERUSER:  never superuser -- it must remain a bounded, auditable
--               role, not a bypass of every other control.
-- NOCREATEDB:   application onboarding is schema-per-application inside the
--               one `r2dbsvc_platform` database created below, not
--               database-per-application, so no further database-creation
--               capability is needed after this bootstrap step.
-- NOINHERIT:    this role's privileges are exactly what is granted to it
--               directly, never implicitly widened by future group-role
--               membership.
SELECT format(
    'CREATE ROLE r2dbsvc_control LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB CREATEROLE NOINHERIT CONNECTION LIMIT 5',
    :'control_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'r2dbsvc_control')
\gexec

-- `CREATE DATABASE` cannot run inside a transaction block/DO block, so its
-- idempotency check is a plain conditional `\gexec` this file emits SQL
-- text for and immediately executes. This is a standard psql idiom, not a
-- server-side extension.
SELECT format('CREATE DATABASE r2dbsvc_platform OWNER r2dbsvc_control TEMPLATE template0 ENCODING ''UTF8''')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'r2dbsvc_platform')
\gexec

-- No other role may connect to the platform database by default; access is
-- granted explicitly, per role, by 0002's provisioning function.
REVOKE ALL ON DATABASE r2dbsvc_platform FROM PUBLIC;
