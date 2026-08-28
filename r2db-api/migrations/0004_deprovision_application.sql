-- r2db-api PostgreSQL provisioning -- 0004: deprovision one application
-- (database-per-application, architecture §8 "D-3 改訂")
--
-- WHO RUNS THIS: the operator/deploy tooling, connected to the
-- `r2dbsvc_platform` database as `r2dbsvc_control`:
--
--   psql "$R2DBSVC_CONTROL_DSN" -v app_slug='myapp' \
--     -f 0004_deprovision_application.sql
--
-- Drops that application's entire database (every table in it, `CASCADE`
-- is implicit -- dropping the database drops everything inside it) and
-- both its login roles. Never touches any other application's database,
-- role, or data.
--
-- WHY A SCRIPT, NOT A FUNCTION: `DROP DATABASE` has the identical
-- transaction-block restriction `CREATE DATABASE` does (see 0002/0003's
-- header comments) -- it cannot run inside a plpgsql function body.
--
-- BEHAVIOUR CHANGE FROM THE PREVIOUS (schema-per-application)
-- `deprovision_application`: that function silently returned (a no-op) if
-- the slug was not registered. `begin_deprovision_application` (0002) now
-- raises instead, which -- combined with `\set ON_ERROR_STOP on` below --
-- aborts this script loudly on an unknown slug rather than silently
-- succeeding at nothing. Deprovisioning something that was never
-- provisioned is treated as an operator error worth surfacing, not a
-- condition worth absorbing.
--
-- NO EXPLICIT `REVOKE CONNECT ... FROM <role>` STEP IS NEEDED HERE (the
-- previous schema-per-application version needed one, to work around
-- PostgreSQL refusing to `DROP ROLE` a role that still held a privilege
-- grant made by someone else, e.g. its `CONNECT` grant on the *shared*
-- platform database that kept existing across every application's
-- deprovisioning). Database-per-application removes that hazard
-- structurally: the `CONNECT` grant this application's roles hold is on
-- *this application's own database*, which `DROP DATABASE` below removes
-- outright, ACL entries included, before `DROP ROLE` ever runs -- so there
-- is nothing left for a role to still be "holding" by the time it is
-- dropped.
--
-- CREDENTIAL-RESIDUE GUARD (review-reported gap, fixed here): a surviving
-- `r2dbsvc_registry.credentials` row for this slug used to let this
-- script's destructive steps below (`DROP DATABASE`/`DROP ROLE`) succeed,
-- only for `finish_deprovision_application`'s registry `DELETE` at the very
-- end to then fail on that row's foreign key -- leaving the database and
-- roles gone, but the registry still claiming the application is
-- provisioned and its credentials still valid (able to authenticate).
-- `r2dbsvc_registry.assert_no_credentials_for_deprovision`
-- (`0005_credential_store.sql`) closes that gap by checking this
-- *immediately* after `begin_deprovision_application` below, before
-- `pg_terminate_backend`/`DROP DATABASE`/`DROP ROLE` -- anything at all --
-- ever runs, and raises loudly (aborting this whole script, `ON_ERROR_STOP`)
-- if any credential still references this slug.
--
-- Called conditionally, via `to_regprocedure` + `\gexec` (the same
-- conditional-DDL idiom `0001`/`0003` already use for their own
-- catalog-checked steps): a platform database that has never had `0005`
-- applied at all has no such function to call, and this deliberately skips
-- the check rather than failing on a missing function -- `0003`/`0004`
-- must keep working entirely on their own for a deployment (or test suite,
-- e.g. `r2db-api/tests/test_postgres.py`) that provisions/deprovisions
-- applications without ever adopting the credential store.

\set ON_ERROR_STOP on

SELECT * FROM r2dbsvc_registry.begin_deprovision_application(:'app_slug') \gset

SELECT CASE WHEN to_regprocedure('r2dbsvc_registry.assert_no_credentials_for_deprovision(text)') IS NOT NULL
            THEN format('SELECT r2dbsvc_registry.assert_no_credentials_for_deprovision(%L)', :'app_slug')
            ELSE 'SELECT 1' -- 0005 was never applied on this platform database -- nothing to check
       END
\gexec

-- Terminate any lingering ordinary client backends against this
-- application's database before dropping it -- a pooled `PostgresCell`
-- connection this process itself just closed can take a brief moment to
-- fully disappear from `pg_stat_activity` from the server's point of view,
-- which would otherwise race `DROP DATABASE` into `database "..." is being
-- accessed by other users`. Harmless (and a no-op) if nothing is
-- connected.
--
-- `AND backend_type = 'client backend'` deliberately excludes background
-- workers (autovacuum in particular, which reports `usename IS NULL` and
-- routinely visits a freshly churned database's system catalogs --
-- `pg_auth_members`/`pg_shdepend`/`pg_database` -- right after this
-- script's own `CREATE ROLE`/`CREATE DATABASE` above): PostgreSQL refuses
-- `pg_terminate_backend` against a background worker for any role short of
-- true superuser, which `r2dbsvc_control` deliberately is not (this
-- migration set's whole point), so attempting it here would itself fail
-- with `permission denied to terminate process` -- confirmed empirically
-- while writing this file, under the load this repository's own
-- injection-payload parametrized tests generate. Autovacuum on a table or
-- two in a freshly created, still-tiny database finishes in well under a
-- second on its own; `r2db-api/tests/test_postgres.py::deprovision_app`
-- and `conformance_adapter_r2db_http.py::_sweep_prefix` both already retry
-- this whole script/statement with a short backoff on exactly the
-- `is being accessed by other users` outcome that a still-running
-- autovacuum worker (now correctly left untouched, not fought over)
-- produces, so simply waiting it out on retry is sufficient -- no
-- elevated privilege is needed or requested.
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :'database_name' AND pid <> pg_backend_pid() AND backend_type = 'client backend';

DROP DATABASE IF EXISTS :"database_name";
DROP ROLE IF EXISTS :"runtime_role";
DROP ROLE IF EXISTS :"developer_role";

SELECT r2dbsvc_registry.finish_deprovision_application(:'app_slug');
