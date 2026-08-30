-- MitateDB-api PostgreSQL provisioning -- 0001: platform bootstrap
--
-- WHO RUNS THIS: a cluster administrator (e.g. the PostgreSQL superuser, or
-- an existing role with CREATEROLE and CREATEDB), connected as themselves.
-- This file is NEVER executed by either the application-plane or
-- control-plane process, and neither process ever holds a credential
-- capable of running it (R-4, design docs/design/
-- MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md v1.1: "provisioning権限
-- (CREATEDB/CREATEROLEを持つ例 mitatedbsvc_provision) は儀式/provisioning
-- CLIのみが保持し、どちらのAPIプロセスにも渡さない").
--
-- WHAT THIS FILE DOES: creates exactly one new login role
-- (`mitatedbsvc_provision`) and exactly one new database
-- (`mitatedb_platform`, which holds only platform bookkeeping -- see
-- 0002's four registry tables -- never application data; application data
-- lives one database per application, see 0003/0004).
--
-- CLOUD SQL 適合語彙 (R-1): every management statement in this whole
-- migration set (0001-0004) is drawn from the following allowlist, none of
-- which requires PostgreSQL superuser -- only `cloudsqlsuperuser` (Cloud
-- SQL's own bounded admin-equivalent role) or a role with the specific
-- attributes each statement itself needs:
--   CREATE/DROP DATABASE, CREATE/DROP ROLE, GRANT/REVOKE (including
--   `GRANT <role> TO CURRENT_USER WITH SET TRUE`, a PostgreSQL 16+
--   construct -- this is why PostgreSQL 16 is the version this migration
--   set targets, not merely the version it happens to have been tested
--   against), CONNECTION LIMIT, REVOKE ALL ON SCHEMA public FROM PUBLIC,
--   ALTER SCHEMA public OWNER TO <role>, SET LOCAL ROLE <role>, ALTER
--   DEFAULT PRIVILEGES FOR ROLE <role> IN SCHEMA public,
--   pg_terminate_backend (Cloud SQL requires the executing role be a
--   `pg_signal_backend` member for this one -- a runbook/operator
--   precondition, not something this SQL can grant itself).
-- No superuser-only feature (untrusted procedural languages, ALTER
-- SYSTEM, event triggers, etc.) is used anywhere in this migration set.
-- Evidence status (honest, per R-1): every statement above has been
-- exercised only against a local PostgreSQL 16 cluster (Homebrew,
-- `host=/tmp port=5432`) by `tests/test_postgres.py` -- Cloud SQL
-- production evidence is `absent` until deployment-time verification
-- (`security/CONTROL_MAPPING.md`), tracked in the runbook (WP-6).
--
-- Both names below carry the `mitatedb`/`mitatedbsvc` prefix used by
-- every object this migration set creates -- one shared literal token,
-- written as ONE substitutable stem (R-4 "prefix 置換方式"): every
-- occurrence of the literal text `mitatedb` in this file (and 0002-0004)
-- is the SAME token, whether it appears alone (`mitatedb_platform`,
-- `mitatedb_app_...`) or as a prefix of a longer literal
-- (`mitatedbsvc_provision` = `mitatedb` + `svc_provision`) -- a test
-- harness that textually replaces every occurrence of `mitatedb` with a
-- throwaway prefix (`tests/test_postgres.py`, mirroring r2db-api's own
-- `r2dbsvc` -> `r2dbtest<hex>` convention with an intentionally SHORTER
-- replacement value, see that file's own header) transforms every name in
-- this whole migration set consistently, in one pass, with no per-name
-- special-casing.
--
-- `mitatedbsvc_provision` is *not* superuser -- see the role definition
-- below for the exact privilege set and why each one is there.
--
-- IDEMPOTENCY: `CREATE ROLE`/`CREATE DATABASE` have no `IF NOT EXISTS` form
-- in PostgreSQL, so this file uses a conditional-DDL `\gexec` idiom for
-- each (the same standard psql idiom r2db-api's own `0001_bootstrap_
-- control_plane.sql` uses, independently arrived at here rather than
-- copied -- R-2's own "no code sharing between peers" principle, applied
-- here to the migrations set too). Re-running this file is a no-op if
-- 0001 already succeeded.
--
-- Run with, e.g.:
--   psql "$MITATEDBSVC_BOOTSTRAP_ADMIN_DSN" \
--     -v provision_password="$MITATEDBSVC_PROVISION_PASSWORD" \
--     -f 0001_bootstrap_platform.sql
--
-- `MITATEDBSVC_BOOTSTRAP_ADMIN_DSN` and `MITATEDBSVC_PROVISION_PASSWORD`
-- are environment-variable *names*; this file never contains a real
-- credential.

\set ON_ERROR_STOP on

-- LOGIN:        it authenticates the provisioning/migration process.
-- CREATEROLE:   it must create per-application runtime/developer roles
--               (0003/0004) and the two platform process roles (0002).
-- NOSUPERUSER:  never superuser -- it must remain a bounded, auditable
--               role, not a bypass of every other control.
-- CREATEDB:     database-per-application (R-1) means provisioning an
--               application means creating a new PostgreSQL database,
--               not just a schema inside one shared platform database --
--               this role is what runs `CREATE DATABASE` for each one
--               (0003). It is never handed to either the application-
--               plane or control-plane process (R-4).
-- NOINHERIT:    this role's privileges are exactly what is granted to it
--               directly, never implicitly widened by future group-role
--               membership.
SELECT format(
    'CREATE ROLE mitatedbsvc_provision LOGIN PASSWORD %L NOSUPERUSER CREATEDB CREATEROLE NOINHERIT CONNECTION LIMIT 5',
    :'provision_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mitatedbsvc_provision')
\gexec

-- `CREATE DATABASE` cannot run inside a transaction block/DO block, so its
-- idempotency check is a plain conditional `\gexec` this file emits SQL
-- text for and immediately executes.
SELECT format('CREATE DATABASE mitatedb_platform OWNER mitatedbsvc_provision TEMPLATE template0 ENCODING ''UTF8''')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'mitatedb_platform')
\gexec

-- No other role may connect to the platform database by default; access
-- is granted explicitly, per process role, by 0002.
REVOKE ALL ON DATABASE mitatedb_platform FROM PUBLIC;
