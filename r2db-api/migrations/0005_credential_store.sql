-- r2db-api PostgreSQL provisioning -- 0005: credential store + read-only
-- API role
--
-- WHO RUNS THIS: the operator, connected to the `r2dbsvc_platform` database
-- (created by 0001) AS the `r2dbsvc_control` role -- the same role/connection
-- 0002 already runs as. Run once, after 0002 (order relative to 0003/0004
-- does not matter -- this file is control-plane bootstrap, independent of
-- any one application):
--
--   psql "$R2DBSVC_CONTROL_DSN" -v api_password="$R2DBSVC_API_PASSWORD" \
--     -f 0005_credential_store.sql
--
-- `R2DBSVC_API_PASSWORD` is an environment-variable *name*; see
-- r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md §9. This file never
-- contains a real credential.
--
-- WHAT THIS FILE DOES (design docs/design/
-- R2DB_CREDENTIAL_PERSISTENCE_AND_COMPOSITION_ROOT_V1.md, decisions
-- P2-D1/P2-D2/P2-D3): before this migration, the only place a credential's
-- verifier or an application's enabled/disabled state existed was
-- `r2db_api.auth.CredentialStore`'s in-memory Python dict -- gone on every
-- process restart, and never shared between processes. This file persists
-- exactly that same state (never more: no new lifecycle states, no
-- control-credential type -- see the design doc's §0 "契約判断からの独立
-- という制約") into `r2dbsvc_registry`, and provisions the one new,
-- strictly read-only login role (`r2dbsvc_api`) the running `r2db-api` API
-- process itself connects as to read it back on every request
-- (`r2db_api.credential_store.PostgresCredentialStore`).
--
-- IDEMPOTENCY: `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` / `CREATE TABLE
-- IF NOT EXISTS` are natively idempotent. `CREATE ROLE` has no `IF NOT
-- EXISTS` form, so it uses the same conditional-`\gexec` idiom
-- `0001_bootstrap_control_plane.sql` already established for
-- `r2dbsvc_control` (see that file's header for why `:'api_password'`
-- expands into a plain, non-dollar-quoted statement rather than a `DO $$
-- ... $$` block). `GRANT` is naturally idempotent (granting an
-- already-held privilege is a no-op, never an error). Re-running this file
-- after it has already succeeded is a no-op.

\set ON_ERROR_STOP on

-- P2-D2: application disablement must be persisted, not left in the
-- `r2db_api.service.DataService._disabled_apps` in-memory set alone -- a
-- process restart would otherwise silently re-enable a CLI-disabled
-- application (fail-open). `applications.enabled` mirrors that in-memory
-- set's meaning exactly; it is not a new lifecycle state.
ALTER TABLE r2dbsvc_registry.applications
    ADD COLUMN IF NOT EXISTS enabled boolean NOT NULL DEFAULT true;

-- P2-D1: the record shape mirrors `r2db_api.auth.CredentialRecord`
-- (credential_id / application / role / verifier / enabled / revoked)
-- field-for-field, plus `created_at`/`updated_at` for audit-adjacent
-- bookkeeping only -- no new lifecycle state (no expiry, no pending, no
-- rotation lineage) is invented here. Only the verifier
-- (HMAC-SHA256(pepper, secret)) is ever stored; the secret itself is shown
-- once, at issue/rotate time, by `python -m r2db_api.ops`, and is never
-- written anywhere.
--
-- `role` is restricted to `runtime`/`developer` by the same `CHECK` the
-- application layer already enforces (`r2db_api.auth.CredentialStore.add`);
-- a control-credential role is deliberately not a value this column
-- accepts yet -- see this design's §0: that type is added, additively, only
-- once CCR-14 is resolved.
--
-- `application_slug ... ON DELETE RESTRICT` (not `CASCADE`): the CCR-14
-- lessons-learned record documents a previous implementation's `CASCADE`
-- silently severing the audit trail's link from a credential back to its
-- application the moment that application row was deleted. This
-- implementation's application rows are never deleted in the first place
-- (`enabled = false` is the terminal state, per P2-D2) -- `RESTRICT` is
-- still the right default in case that ever changes, so a future deletion
-- attempt fails loudly instead of quietly orphaning credential history.
--
-- `verifier ... UNIQUE`: authentication is an equality lookup on this
-- column (`PostgresCredentialStore.authenticate`), never a full scan --
-- `UNIQUE` is both the index that makes that lookup fast and a structural
-- guarantee that two credentials can never collide on the same verifier.
CREATE TABLE IF NOT EXISTS r2dbsvc_registry.credentials (
    credential_id    text PRIMARY KEY,
    application_slug text NOT NULL
        REFERENCES r2dbsvc_registry.applications(application_slug) ON DELETE RESTRICT,
    role             text NOT NULL CHECK (role IN ('runtime', 'developer')),
    verifier         text NOT NULL UNIQUE,
    enabled          boolean NOT NULL DEFAULT true,
    revoked          boolean NOT NULL DEFAULT false,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now()
);

-- `r2dbsvc_registry` has never granted anything to `PUBLIC` (0002 already
-- revokes it for the schema and `applications`); the newly created
-- `credentials` table inherits that closed-by-default posture -- no
-- explicit `REVOKE` is needed for a table nothing has ever been granted on.

-- P2-D3: the API process's own login role -- strictly read-only. It is
-- never granted `INSERT`/`UPDATE`/`DELETE` on anything, never `CREATEDB`/
-- `CREATEROLE`, and is a completely different role from `r2dbsvc_control`
-- (which keeps those privileges and remains operator/CLI-only, §5.3 C-2).
-- A compromise of the running API process therefore cannot alter a
-- credential's `enabled`/`revoked` state or an application's `enabled`
-- flag -- it can only read the state `python -m r2db_api.ops` (connected as
-- `r2dbsvc_control`) already wrote, which is the actual substance of
-- least-privilege here, not merely a naming convention.
--
-- CONNECTION LIMIT 10: this role is used by exactly one small, dedicated
-- pool per API process (`R2DB_PLATFORM_POOL_SIZE`, default 4 --
-- `r2db_api.credential_store.PostgresCredentialStore`), not per-application
-- like `r2dbsvc_app_*_runtime`/`_developer` (0002's `CONNECTION LIMIT 20`/
-- `10`) -- one process needs at most one such pool regardless of how many
-- applications it serves, so a modest fixed ceiling is enough headroom
-- without being unbounded.
SELECT format(
    'CREATE ROLE r2dbsvc_api LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT CONNECTION LIMIT 10',
    :'api_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'r2dbsvc_api')
\gexec

GRANT CONNECT ON DATABASE r2dbsvc_platform TO r2dbsvc_api;
GRANT USAGE ON SCHEMA r2dbsvc_registry TO r2dbsvc_api;
GRANT SELECT ON r2dbsvc_registry.applications TO r2dbsvc_api;
GRANT SELECT ON r2dbsvc_registry.credentials TO r2dbsvc_api;

-- Deprovisioning guard, called by `0004_deprovision_application.sql`
-- immediately after `begin_deprovision_application` and before anything
-- destructive runs (review-reported gap): without this check,
-- `DROP DATABASE`/`DROP ROLE` in 0004 would already have succeeded by the
-- time `finish_deprovision_application`'s registry `DELETE` hit this
-- table's `application_slug` foreign key (`ON DELETE RESTRICT`, by design
-- -- see this file's header) and failed -- leaving the registry claiming
-- the application is still provisioned even though its database and roles
-- are already gone, with any of its credentials, wrongly, still able to
-- authenticate against a `PostgresCredentialStore` that only ever checks
-- `applications.enabled`, never whether the underlying database still
-- exists. This function turns that into a clean, upfront refusal that
-- touches nothing.
--
-- Defined here (0005), not inline in 0004, so `:'app_slug'` is bound as a
-- real function argument at the call site (`SELECT r2dbsvc_registry.
-- assert_no_credentials_for_deprovision(:'app_slug')`, a plain top-level
-- statement) rather than needing to expand inside a dollar-quoted PL/pgSQL
-- body -- which it structurally cannot: psql's `:'var'` substitution
-- happens on the raw input stream before it is ever sent to the server,
-- and deliberately does not reach inside `$$ ... $$` (see 0001's header
-- for the full reasoning, confirmed empirically while writing this file).
--
-- `0004` only calls this function when `to_regprocedure` finds it defined
-- (see that file's own comment) -- a platform database that has never had
-- `0005` applied at all (e.g. `r2db-api/tests/test_postgres.py`'s own
-- `platform` fixture, which deliberately bootstraps only `0001`-`0004` to
-- exercise `PostgresCell`/provisioning independent of credential
-- persistence) never attempts to call it, and `0003`/`0004`'s original
-- behaviour is completely unchanged there. This function's own body can
-- therefore assume `r2dbsvc_registry.credentials` exists -- if it is ever
-- reached at all, `0005` has already run.
CREATE OR REPLACE FUNCTION r2dbsvc_registry.assert_no_credentials_for_deprovision(p_app_slug text) RETURNS void
LANGUAGE plpgsql
AS $fn$
DECLARE
    v_count integer;
BEGIN
    SELECT count(*) INTO v_count FROM r2dbsvc_registry.credentials WHERE application_slug = p_app_slug;
    IF v_count > 0 THEN
        RAISE EXCEPTION 'application % still has % credential row(s) referencing it -- revoke it first (python -m r2db_api.ops revoke-credential <credential_id>), then delete the row (python -m r2db_api.ops delete-credential <credential_id>) before deprovisioning', p_app_slug, v_count;
    END IF;
END;
$fn$;

REVOKE ALL ON FUNCTION r2dbsvc_registry.assert_no_credentials_for_deprovision(text) FROM PUBLIC;
