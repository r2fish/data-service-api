-- r2db-api PostgreSQL provisioning -- 0014: role-level `statement_timeout`
-- on `r2dbsvc_auditreader` (design docs/design/
-- R2DB_AUDIT_READER_STATEMENT_TIMEOUT_V0_1.md D-1, work order docs/
-- work-orders/WORK_ORDER_R56_R2DB_AUDIT_READER_TIMEOUT_V1.md WP-1)
--
-- WHO RUNS THIS: the operator, connected to the `r2dbsvc_platform` database
-- AS the same role that created `r2dbsvc_auditreader` (normally
-- `r2dbsvc_control`, `0007_application_audit.sql`'s own applier). Run
-- once, after 0007:
--
--   psql "$R2DBSVC_CONTROL_DSN" -v ON_ERROR_STOP=1 -f 0014_auditreader_statement_timeout.sql
--
-- `-v ON_ERROR_STOP=1` must be passed on every `-f` invocation -- without
-- it, psql exits 0 even when a statement in this file errors out.
--
-- ORDER: this file must run after `0007_application_audit.sql`, the
-- migration that creates `r2dbsvc_auditreader`; running this file before
-- 0007 fails with an undefined-role error and rolls back with it (see
-- TRANSACTIONALITY below). Order relative to `0008`/`0012`/`0013` does not
-- matter -- this is a platform single-shot migration touching only the
-- reader role, independent of the writer-role/connection-limit machinery
-- those files own.
--
-- PERMISSIONS: PostgreSQL 16 grants `ALTER ROLE ... SET` only to a role
-- holding CREATEROLE with ADMIN OPTION on the target role -- CREATEROLE
-- carries that option automatically on a role it created itself. This
-- file's own `ALTER ROLE r2dbsvc_auditreader` therefore succeeds only when
-- the CONNECTING role is the same role that created `r2dbsvc_auditreader`;
-- a cluster where a different role created it must grant ADMIN OPTION
-- explicitly first, or this file fails and rolls back with it.
--
-- TRANSACTIONALITY: the whole file runs inside one transaction
-- (`BEGIN`/`COMMIT`) -- a permission or undefined-role failure leaves
-- nothing changed rather than a half-applied state.
--
-- IDEMPOTENCY: `ALTER ROLE ... SET` is an assignment, not an increment --
-- re-running this file leaves the same terminal value every time.
--
-- COMPATIBILITY WITH THE ALREADY-DEPLOYED r2db-api INSTANCE: ADDITIVE
-- ONLY -- adds a role-level session bound, drops nothing, revokes nothing.
--
-- ROLE SETTINGS TAKE EFFECT AT LOGIN, NOT ON AN ALREADY-OPEN CONNECTION:
-- `_RolePool` (r2db_api/postgres.py) holds reader connections open for the
-- life of the process, and never re-reads role settings on an existing
-- connection. Applying this file changes the effective statement_timeout
-- only for connections opened AFTER it runs -- restart the process that
-- holds the reader's own connection pool (control) once this file has
-- been applied, so every open reader connection is replaced by one that
-- actually carries this value.

\set ON_ERROR_STOP on

BEGIN;

ALTER ROLE r2dbsvc_auditreader SET statement_timeout = '5000ms';

COMMIT;
