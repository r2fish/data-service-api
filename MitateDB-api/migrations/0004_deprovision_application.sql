-- MitateDB-api PostgreSQL provisioning -- 0004: deprovision one
-- application (database-per-application, R-1)
--
-- WHO RUNS THIS: the operator/deploy tooling, connected to the
-- `mitatedb_platform` database as `mitatedbsvc_provision`:
--
--   psql "$MITATEDBSVC_PROVISION_DSN" -v app_id='acme' \
--     -f 0004_deprovision_application.sql
--
-- Drops that application's entire database (every table in it -- dropping
-- the database drops everything inside it) and both its login roles, if
-- it was ever provisioned. Never touches any other application's
-- database, role, or data.
--
-- TWO-STATE CLEANUP (R-4, C-14 vector 5's own requirement, "登録のみで
-- DBを持たない行も撤去できること"): `begin_deprovision_application`
-- (0002) may return a NULL `database_name` for an application that was
-- registered but never successfully provisioned (a previous 0003 attempt
-- crashed before `finish_provision_application` ran, or -- once WP-4's
-- own `/control/v1 register_application` exists -- an application that
-- was registered in-band and never provisioned at all). This script's
-- `\if :{?database_name}` branch below skips the DATABASE-drop step
-- entirely in that case, while `finish_deprovision_application` still
-- unconditionally removes the registry row -- so a registration-only row
-- is fully removable, not stuck.
--
-- GHOST ROLE RECLAIM (m-11, independent review round 2): `begin_
-- provision_application` (0002) now writes `runtime_role`/
-- `developer_role` into the registry row as soon as it creates those two
-- roles, WHILE `database_name` is still NULL -- so a crash between role
-- creation and `finish_provision_application` leaves a row with real,
-- non-NULL role names but a NULL `database_name`. The nested `\if
-- :{?runtime_role}` branch below handles exactly this: no database to
-- drop, but the two ALREADY-CREATED roles are dropped anyway, so nothing
-- is leaked. A row that was registered but `begin_provision_application`
-- was NEVER even called for it (both `database_name` AND `runtime_role`/
-- `developer_role` all NULL) correctly falls all the way through to
-- "nothing to drop at all".
--
-- CREDENTIAL CLEANUP (M-4, independent review, adjudicated -- supersedes
-- this file's own previous "credential-residue guard" revision, which
-- REFUSED to deprovision an application with any surviving `credentials`
-- row instead): `finish_deprovision_application` (0002) now deletes that
-- application's `credentials` rows itself, in the SAME step it removes
-- the `applications` row -- deprovisioning is this application's own
-- terminal, whole-namespace removal (its database and both roles are
-- dropped below), so its credential rows going with it is not in tension
-- with revoke's own terminality (SI-13): a credential scoped to an
-- application that no longer exists is removed along with the namespace
-- it was ever valid within, not "un-revoked". `control_audit` (the
-- durable evidence trail) is never touched by this script.
--
-- WHY A SCRIPT, NOT A FUNCTION: `DROP DATABASE` has the identical
-- transaction-block restriction `CREATE DATABASE` does (0003's header).

\set ON_ERROR_STOP on

SELECT * FROM mitatedb_registry.begin_deprovision_application(:'app_id') \gset

-- `\if :{?database_name}` (psql's own "is this variable currently set"
-- test): `\gset` leaves a variable UNSET when its source column is SQL
-- NULL, which is exactly the two-state "registered but never provisioned"
-- case this branch exists to handle.
\if :{?database_name}

-- Terminate any lingering ordinary client backends against this
-- application's database before dropping it -- a pooled `PostgresBackend`
-- connection this process itself just closed can take a brief moment to
-- fully disappear from `pg_stat_activity` from the server's point of
-- view, which would otherwise race `DROP DATABASE` into `database "..."
-- is being accessed by other users`. Harmless (and a no-op) if nothing is
-- connected. `AND backend_type = 'client backend'` deliberately excludes
-- background workers (autovacuum in particular): terminating one
-- requires true superuser, which `mitatedbsvc_provision` deliberately is
-- not, so attempting it would itself fail with `permission denied to
-- terminate process`. Autovacuum on a table or two in a freshly created,
-- still-tiny database finishes in well under a second on its own;
-- `tests/test_postgres.py`'s own deprovisioning helper retries this whole
-- script with a short backoff on exactly the `is being accessed by other
-- users` outcome that outliving it can still produce.
SELECT pg_terminate_backend(pid) FROM pg_stat_activity
    WHERE datname = :'database_name' AND pid <> pg_backend_pid() AND backend_type = 'client backend';

DROP DATABASE IF EXISTS :"database_name";
DROP ROLE IF EXISTS :"runtime_role";
DROP ROLE IF EXISTS :"developer_role";

\else

-- m-11: no database was ever created for this application, but
-- `begin_provision_application` may still have created its two roles
-- before whatever crashed/never-finished this attempt (see this file's
-- own header). Drop them directly -- no database, no `pg_terminate_
-- backend`/`DROP DATABASE` step is applicable or needed.
\if :{?runtime_role}
\echo 'mitatedb-api: application was never fully provisioned -- dropping its already-created roles only'
DROP ROLE IF EXISTS :"runtime_role";
DROP ROLE IF EXISTS :"developer_role";
\else
\echo 'mitatedb-api: application was registered but never provisioned at all -- nothing to drop'
\endif

\endif

SELECT mitatedb_registry.finish_deprovision_application(:'app_id');
