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
--
-- LIVE-CONNECTION HANDLING (design docs/design/DEPROVISION_FORCED_DROP_
-- V0_1.md v1.0, D-2R): inside the `\if :{?database_name}` branch below,
-- three stages precede the terminate/drop steps that were already here --
-- pre-check, temporary self-grant, `ALLOW_CONNECTIONS false` -- so that a
-- runtime-role connection this application's own Data service pool is
-- still holding does not make this script fail (§3.3 of that design memo:
-- retrying alone cannot fix this, since production deprovisioning has no
-- retry loop). `WITH (FORCE)` was considered and rejected (X-5 there): it
-- is refused outright by a lingering autovacuum worker (M-11), where a
-- plain `DROP DATABASE` is not (M-12). None of the three new stages apply
-- to the `\else` branch below (no database exists there to hold a live
-- connection, protect, or reconnect to).

\set ON_ERROR_STOP on

SELECT * FROM mitatedb_registry.begin_deprovision_application(:'app_id') \gset

-- `\if :{?database_name}` (psql's own "is this variable currently set"
-- test): `\gset` leaves a variable UNSET when its source column is SQL
-- NULL, which is exactly the two-state "registered but never provisioned"
-- case this branch exists to handle.
\if :{?database_name}

-- LIVE-CONNECTION PRE-CHECK (D-2R stage (2), design H-2): before any of
-- the stages below changes anything, refuse if this database has a
-- connection open under any role other than this application's own
-- runtime/developer role or the executing role itself.
-- `usesysid IS NOT NULL` excludes background workers (autovacuum reports
-- `usesysid IS NULL`); `usename`/`usesysid` are already readable here,
-- without anything the temporary grant stage below adds (H-2). Written
-- as
-- `format()` + `\gexec`, not a literal `DO $$ ... $$` block, because psql
-- does not expand its own `:'variable'` syntax inside a dollar-quoted
-- string (design F-2) -- `format()`'s `%L` bakes the fixed,
-- role-name-free exception text into the generated `DO` block's source
-- before `\gexec` runs it, so no psql variable ever needs to appear
-- inside the dollar quotes. Diagnosis is the operator's own
-- `pg_stat_activity` read (this migration set's runbook), not this
-- exception's own message -- only "it stopped" and "nothing changed" are
-- meant to be relied on, not PostgreSQL's own `DETAIL:` text.
SELECT CASE WHEN EXISTS (
                 SELECT 1 FROM pg_stat_activity
                 WHERE datname = :'database_name'
                   AND pid <> pg_backend_pid()
                   AND usesysid IS NOT NULL
                   AND usename NOT IN (:'runtime_role', :'developer_role', CURRENT_USER)
             )
            THEN format('DO $check$ BEGIN RAISE EXCEPTION %L; END $check$',
                         'deprovision refused: a connection to this database is held by a role other than this application''s own runtime/developer role or the executing role -- close it, then retry')
            ELSE 'SELECT 1'
       END
\gexec

-- TEMPORARY SELF-GRANT (D-2R stage (3), design M-7/H-1): grants each of
-- this application's still-existing roles to `CURRENT_USER` (the
-- executing role) `WITH INHERIT TRUE, SET FALSE`. `mitatedbsvc_provision`
-- already holds ADMIN OPTION on both (it `CREATE ROLE`d them itself, in
-- 0003), so this needs no privilege it does not already have, and no
-- cluster-wide predefined role (`pg_signal_backend` et al.) is used
-- anywhere in this file. `SET FALSE` deliberately withholds `SET ROLE`
-- (never needed here). Grant, use, explicit revoke is this repository's
-- own established shape for a role's own temporary self-elevation (0003's
-- `GRANT :"developer_role" TO CURRENT_USER WITH SET TRUE` immediately
-- before, and `REVOKE ... FROM CURRENT_USER` immediately after, its own
-- one use) -- `DROP ROLE` below is this grant's own revoke, on the normal
-- path; a run that stops before reaching it leaves the grant standing
-- (design §4.1), removable by hand with plain `REVOKE ... FROM
-- CURRENT_USER` (M-13). This grant is what lets the narrowed terminate
-- below succeed against this application's own live backends -- H-1
-- exercises it against three open connections plus a client reconnecting
-- every 0.1 s (four terminated in that run), with an autovacuum worker
-- left alone. Each `EXISTS` guard skips a role
-- that is already gone (a retried run after a prior attempt got partway
-- through `DROP ROLE` below) rather than failing on `GRANT`'s own
-- missing-role error -- the same non-existence idiom this file's own
-- `0013_role_statement_timeouts.sql`/`0014_role_connection_limits_rollout.
-- sql` per-role loops already use (`0012_role_connection_limits.sql`'s own
-- per-role loop has no such existence check).
SELECT CASE WHEN EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'runtime_role')
            THEN format('GRANT %I TO CURRENT_USER WITH INHERIT TRUE, SET FALSE', :'runtime_role')
            ELSE 'SELECT 1'
       END
\gexec

SELECT CASE WHEN EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'developer_role')
            THEN format('GRANT %I TO CURRENT_USER WITH INHERIT TRUE, SET FALSE', :'developer_role')
            ELSE 'SELECT 1'
       END
\gexec

-- CLOSE THE RECONNECT WINDOW (D-2R stage (4), design H-1/F-1): flips this
-- database to refuse new connections before the narrowed terminate below
-- runs, so a client racing to reconnect in the gap between that terminate
-- and `DROP DATABASE` cannot re-open one -- the same gap `WITH (FORCE)`
-- was considered for and rejected over (design §4 D-2, X-5). No extra
-- privilege is needed: `mitatedbsvc_provision` is this database's OWNER
-- (0003 creates it with no explicit `OWNER` clause, so ownership defaults
-- to the executing role). The `pg_database` existence check (F-1) is what
-- keeps a retry safe after an earlier attempt already got past `DROP
-- DATABASE` below (design §4.1) -- an unconditional `ALTER DATABASE`
-- would otherwise fail every later attempt with `database "..." does not
-- exist` and this script could never complete.
SELECT CASE WHEN EXISTS (SELECT 1 FROM pg_database WHERE datname = :'database_name')
            THEN format('ALTER DATABASE %I WITH ALLOW_CONNECTIONS false', :'database_name')
            ELSE 'SELECT 1'
       END
\gexec

-- Terminate any lingering ordinary client backends against this
-- application's database before dropping it -- a pooled `PostgresBackend`
-- connection this process itself just closed can take a brief moment to
-- fully disappear from `pg_stat_activity` from the server's point of
-- view, which would otherwise race `DROP DATABASE` into `database "..."
-- is being accessed by other users`. Harmless (and a no-op) if nothing is
-- connected. By this point `ALLOW_CONNECTIONS false` above has already
-- closed off any new connection, so this only has to clear whatever was
-- already open when this script started (H-1). `AND backend_type =
-- 'client backend'` deliberately excludes background workers (autovacuum
-- in particular): terminating one requires true superuser, which
-- `mitatedbsvc_provision` deliberately is not, so attempting it would
-- itself fail with `permission denied to terminate process`. Autovacuum
-- on a table or two in a freshly created, still-tiny database finishes in
-- well under a second on its own; `tests/test_postgres.py`'s own
-- deprovisioning helper retries this whole script with a short backoff on
-- exactly the `is being accessed by other users` outcome that outliving
-- it can still produce.
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
