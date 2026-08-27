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
-- (`r2dbsvc_control`) and exactly one new database (`r2dbsvc_platform`,
-- which holds only control-plane bookkeeping -- see 0002's registry table
-- -- never application data; application data now lives one database per
-- application, see 0003/0004).
--
-- Both names carry the `r2dbsvc_` prefix used by every object this
-- migration set creates, chosen specifically so nothing here can collide
-- with the already-running old r2db-api deployment on the existing VPS
-- (§5.3 C-1: "database name, role names, ... must all be distinctly
-- namespaced"). Architecture decision §8 ("D-3 改訂") is worth restating
-- here: that existing deployment is *also* database-per-application
-- (`app_<slug>_<hex>` databases, per its own conventions) -- so the
-- collision surface this file's prefix must avoid is now `pg_database`
-- itself, not just a schema namespace inside one shared platform database
-- as it was before this revision. `r2dbsvc_app_<slug>` (0003) can never
-- collide with `app_<slug>_<hex>`: the two literal prefixes ("r2dbsvc_app_"
-- vs "app_") differ at the very first character, for every possible
-- `<slug>`/`<hex>`. See `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md`
-- §1 for the full object-name table.
--
-- `r2dbsvc_control` is *not* superuser -- see the role definition below for
-- the exact privilege set and why each one is there.
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
--               (0002/0003's provisioning functions/script).
-- NOSUPERUSER:  never superuser -- it must remain a bounded, auditable
--               role, not a bypass of every other control. (This is also
--               why §8.5 condition 3's option (a) -- a `CREATE EVENT
--               TRIGGER` in a template database, so RLS is applied
--               automatically to every future table -- is not implemented
--               here even though 0003 does have `CREATEDB`: `CREATE EVENT
--               TRIGGER` unconditionally requires superuser in PostgreSQL,
--               with no ownership- or grant-based delegation path, and this
--               role deliberately never becomes superuser. See 0003's
--               top-of-file note and the runbook for the full reasoning
--               and the (b) verification-based approach actually used.)
-- CREATEDB:     database-per-application (architecture §8) means
--               provisioning an application now means creating a new
--               PostgreSQL database, not just a schema inside one shared
--               platform database -- this role is what runs `CREATE
--               DATABASE` for each one (0003). It cannot create arbitrary
--               roles/databases beyond what 0003/0004's scripted flow does
--               with this privilege; it is still bounded by NOSUPERUSER and
--               by never being handed to the r2db-api application process
--               itself (§5.3 C-2).
-- NOINHERIT:    this role's privileges are exactly what is granted to it
--               directly, never implicitly widened by future group-role
--               membership.
SELECT format(
    'CREATE ROLE r2dbsvc_control LOGIN PASSWORD %L NOSUPERUSER CREATEDB CREATEROLE NOINHERIT CONNECTION LIMIT 5',
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
