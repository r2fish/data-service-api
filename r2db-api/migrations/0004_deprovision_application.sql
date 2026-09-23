-- r2db-api PostgreSQL provisioning -- 0004: deprovision one application
-- (database-per-application, architecture §8 "D-3 改訂")
--
-- WHO RUNS THIS: the operator/deploy tooling, connected to the
-- `r2dbsvc_platform` database as `r2dbsvc_control` (R-90 WP-2: via
-- `ops deprovision`, gated by a confirmation phrase -- see
-- POSTGRES_PROVISIONING_RUNBOOK.md section 5):
--
--   python -m r2db_api.ops deprovision myapp --confirm <phrase> \
--     --lock-timeout <value>
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
-- *immediately* after `begin_deprovision_application` below, before any of
-- this script's later stages -- the live-connection pre-check, the
-- temporary self-grant, `ALLOW_CONNECTIONS`, `pg_terminate_backend`/`DROP
-- DATABASE`/`DROP ROLE` -- anything at all -- ever runs, and raises loudly
-- (aborting this whole script, `ON_ERROR_STOP`) if any credential still
-- references this slug.
--
-- Called conditionally, via `to_regprocedure` + `\gexec` (the same
-- conditional-DDL idiom `0001`/`0003` already use for their own
-- catalog-checked steps): a platform database that has never had `0005`
-- applied at all has no such function to call, and this deliberately skips
-- the check rather than failing on a missing function -- `0003`/`0004`
-- must keep working entirely on their own for a deployment (or test suite,
-- e.g. `r2db-api/tests/test_postgres.py`) that provisions/deprovisions
-- applications without ever adopting the credential store.
--
-- LIVE-CONNECTION HANDLING (design docs/design/DEPROVISION_FORCED_DROP_
-- V0_1.md v1.0, D-2R): the three stages below this comment -- pre-check,
-- temporary self-grant, `ALLOW_CONNECTIONS false` -- exist so that a
-- runtime-role connection this application's own Data service pool is
-- still holding does not make this script fail (§3.3 of that design memo:
-- retrying alone cannot fix this, since production deprovisioning has no
-- retry loop). `WITH (FORCE)` was considered and rejected (X-5 there): it
-- is refused outright by a lingering autovacuum worker (M-11), where a
-- plain `DROP DATABASE` is not (M-12).

\set ON_ERROR_STOP on

SELECT * FROM r2dbsvc_registry.begin_deprovision_application(:'app_slug') \gset

SELECT CASE WHEN to_regprocedure('r2dbsvc_registry.assert_no_credentials_for_deprovision(text)') IS NOT NULL
            THEN format('SELECT r2dbsvc_registry.assert_no_credentials_for_deprovision(%L)', :'app_slug')
            ELSE 'SELECT 1' -- 0005 was never applied on this platform database -- nothing to check
       END
\gexec

-- LIVE-CONNECTION PRE-CHECK (D-2R stage (2), design H-2): before any of
-- the stages below changes anything, refuse if this database has a
-- connection open under any role other than this application's own
-- runtime/developer role or the executing role itself.
-- `usesysid IS NOT NULL` excludes background workers (autovacuum reports
-- `usesysid IS NULL`); `usename`/`usesysid` are already readable here,
-- without anything the temporary grant stage (3) below adds (H-2).
-- Written as
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
-- executing role) `WITH INHERIT TRUE, SET FALSE`. `r2dbsvc_control`
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
-- missing-role error -- the same non-existence idiom
-- `MitateDB-api/migrations/0013_role_statement_timeouts.sql`/`0014_role_
-- connection_limits_rollout.sql`'s own per-role loops use, on MitateDB's
-- side of this repository.
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
-- privilege is needed: `r2dbsvc_control` is this database's OWNER (0003
-- creates it with no explicit `OWNER` clause, so ownership defaults to
-- the executing role). The `pg_database` existence check (F-1) is what
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
-- application's database before dropping it -- a pooled `PostgresCell`
-- connection this process itself just closed can take a brief moment to
-- fully disappear from `pg_stat_activity` from the server's point of view,
-- which would otherwise race `DROP DATABASE` into `database "..." is being
-- accessed by other users`. Harmless (and a no-op) if nothing is
-- connected. By this point `ALLOW_CONNECTIONS false` above has already
-- closed off any new connection, so this only has to clear whatever was
-- already open when this script started (H-1).
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
