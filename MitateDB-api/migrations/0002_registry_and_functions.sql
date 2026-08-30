-- MitateDB-api PostgreSQL provisioning -- 0002: platform registry (R-4) +
-- provisioning helper functions
--
-- WHO RUNS THIS: the operator, connected to the `mitatedb_platform`
-- database (created by 0001) AS the `mitatedbsvc_provision` role -- never
-- as the cluster superuser, and never as either the application-plane or
-- control-plane process. Run once, after 0001.
--
--   psql "$MITATEDBSVC_PROVISION_DSN" -f 0002_registry_and_functions.sql
--
-- R-4 (design v1.1): four tables, one schema (`mitatedb_registry`), never
-- reachable from any application-facing request path:
--
--   applications        | application_id, enabled, allocated database name
--                        | (NULLABLE -- two-state registry, see below)
--   credentials         | application credential digest/role/state; write:
--                        | control-plane process role; read-only:
--                        | application-plane process role (`authenticate`)
--   control_credentials | control credential digest/must_rotate/state;
--                        | write+read: control-plane process role only
--   control_audit       | contract `audit.fields`' 12 columns + a server-
--                        | assigned `recorded_at` + a monotonic `audit_seq`
--                        | (independent review M-1: a stable, gap-free
--                        | ordering column C-15's own prefix-strict
--                        | comparison needs -- `recorded_at` alone is a
--                        | wall-clock timestamp, which is not guaranteed
--                        | strictly monotonic/unique across concurrent
--                        | inserts); INSERT-only for the control-plane
--                        | process role (no SELECT/UPDATE/DELETE grant of
--                        | any kind -- append-only by privilege, not merely
--                        | by application-code convention)
--
-- TWO-STATE REGISTRY (R-4, WP-0 M-11): `applications.database_name` (and
-- its `runtime_role`/`developer_role` companions) is NULLABLE. A row can
-- exist in "registered, unprovisioned" state (created by `begin_
-- provision_application` below, `database_name IS NULL`) before
-- `finish_provision_application` fills in the allocated names once 0003's
-- database/role creation has fully succeeded -- so a crash partway
-- through 0003 never leaves the registry claiming an application is fully
-- provisioned when it is not (mirrors r2db-api's own begin/finish split,
-- `R2DB_CCR14_CONTROL_PLANE_V1.md`'s crash-safety correction, arrived at
-- independently here for MitateDB-api's own registry rather than shared
-- code). `finish_deprovision_application` below unconditionally DELETEs
-- the row regardless of whether it ever reached "provisioned" -- so a
-- registered-but-never-provisioned row can also be fully removed (a
-- requirement, not an edge case this design treats as out of scope: a
-- control plane that registers an application and then fails/refuses to
-- ever provision it must still be able to clean up that row).
--
-- WP-1 SCOPING NOTE (this migration set's own honest boundary): the
-- actual `/control/v1 register_application` in-band endpoint that would
-- create a "registered, unprovisioned" row ahead of, and independently
-- from, provisioning is control-plane product code that does not exist
-- yet (WP-4/5). For THIS WP, `begin_provision_application` below performs
-- both roles at once (registers the row if it does not already exist,
-- THEN begins provisioning it) -- a deliberate, temporary combination that
-- keeps the registry's own SCHEMA already two-state-shaped (satisfying
-- R-4's own schema requirement) while the actual control-plane code that
-- will call `register` and `provision` as two independently-triggerable
-- steps is built in a later WP. This function remains safe to call again
-- later (WP-4) exactly as it is: a control-plane `register_application`
-- endpoint can simply INSERT the same "registered, database_name NULL"
-- row this function's own registration branch already produces, and this
-- function's provisioning branch is unaffected either way.
--
-- WHY THE PROVISIONING FLOW IS FUNCTIONS HERE BUT A SCRIPT IN 0003/0004:
-- `CREATE DATABASE`/`DROP DATABASE` cannot run inside a transaction block
-- (which every statement inside a plpgsql function body implicitly is),
-- so they cannot be part of these functions. What IS safely transactional
-- -- creating the two per-application login roles, and registry
-- bookkeeping -- stays here as functions; 0003/0004 call these to bracket
-- their own top-level `CREATE DATABASE`/`DROP DATABASE` statements.

\set ON_ERROR_STOP on

-- m-3 (independent review): symmetry with 0003's own tenant-database
-- treatment of `public` -- this connection is already to the PLATFORM
-- database itself (`mitatedb_platform`), whose own default `public`
-- schema (created automatically by `CREATE DATABASE` in 0001, still owned
-- by `mitatedbsvc_provision` at this point) is otherwise left with
-- PostgreSQL's default wide-open `PUBLIC` privileges. Nothing this
-- migration set uses lives in `public` here (registry objects live in the
-- dedicated `mitatedb_registry` schema below) -- closing it removes an
-- unused, unintentionally-open surface on the platform database itself.
REVOKE ALL ON SCHEMA public FROM PUBLIC;

CREATE SCHEMA IF NOT EXISTS mitatedb_registry AUTHORIZATION mitatedbsvc_provision;

CREATE TABLE IF NOT EXISTS mitatedb_registry.applications (
    application_id  text PRIMARY KEY CHECK (application_id ~ '^[a-z][a-z0-9_]{0,32}$'),
    enabled         boolean NOT NULL DEFAULT TRUE,
    -- Two-state registry (R-4, WP-0 M-11): NULL until provisioning
    -- completes (`finish_provision_application` below).
    database_name   text UNIQUE,
    runtime_role    text UNIQUE,
    developer_role  text UNIQUE,
    registered_at   timestamptz NOT NULL DEFAULT now(),
    provisioned_at  timestamptz
);

-- WP-2 (design v1.2 R-4/§3, credential store persistence): `enabled` and
-- `revoked` are two INDEPENDENT booleans, matching contract
-- `CredentialsResult`/`CredentialStateResult` (spec/data-service-api.v1.
-- json), both of which require BOTH keys, always present, never merged
-- into one. `enabled` is the reversible operational state (`disable`/
-- `enable` toggle it, WP-2's own `PostgresCredentialStore`); `revoked` is
-- terminal (contract `lifecycle.credential`: "Revocation is terminal: a
-- revoked credential can never be made valid again, and enable reverses
-- disable only") -- once `TRUE`, nothing in this migration set or in
-- `credential_store_postgres.py` ever sets it back to `FALSE` (no
-- un-revoke SQL statement exists anywhere in this repository).
CREATE TABLE IF NOT EXISTS mitatedb_registry.credentials (
    credential_id  text PRIMARY KEY,
    application_id text NOT NULL REFERENCES mitatedb_registry.applications (application_id),
    role           text NOT NULL CHECK (role IN ('runtime', 'developer')),
    digest         bytea NOT NULL,
    enabled        boolean NOT NULL DEFAULT TRUE,
    revoked        boolean NOT NULL DEFAULT FALSE,
    expires_at     timestamptz,
    issued_at      timestamptz NOT NULL DEFAULT now()
);

-- WP-4 correction (design v1.2 R-4 item 1, "control credential store 二重
-- 実装 + parity"): this table originally (WP-1) had no `revoked` column at
-- all -- an oversight discovered while implementing WP-4's own `control_
-- auth.ControlCredentialStore`/`control_credential_store_postgres.
-- PostgresControlCredentialStore` pair, which requires the SAME independent
-- enabled/revoked shape the sibling `credentials` table above already has
-- (contract `CredentialsResult`/`CredentialStateResult` require both keys
-- for every credential row regardless of kind). Added in place rather than
-- as a separate follow-up migration: no real deployment has ever run this
-- migration set against a persistent Cloud SQL instance yet (`security/
-- CONTROL_MAPPING.md`'s own "Cloud SQL 実機 evidence は配備時まで absent"
-- disclosure) -- every test harness in this repository re-runs the full
-- 0001-0004 sequence from scratch against a throwaway-prefixed database on
-- every run, so there is no live incremental-migration history this
-- in-place edit could silently break. As with `credentials.revoked`
-- immediately above: nothing in this migration set or in `control_
-- credential_store_postgres.py` ever sets this back to `FALSE` (no
-- un-revoke SQL statement exists anywhere in this repository).
CREATE TABLE IF NOT EXISTS mitatedb_registry.control_credentials (
    credential_id text PRIMARY KEY,
    digest        bytea NOT NULL,
    must_rotate   boolean NOT NULL DEFAULT TRUE,
    enabled       boolean NOT NULL DEFAULT TRUE,
    revoked       boolean NOT NULL DEFAULT FALSE,
    issued_at     timestamptz NOT NULL DEFAULT now()
);

-- Contract `audit.fields` (spec/data-service-api.v1.json), verbatim column
-- names, plus a server-assigned `recorded_at` distinct from the caller's
-- own logical `occurred_at`, plus a monotonic `audit_seq` (R-4/independent
-- review M-1: "12列 + recorded_at + 採番列"). `audit_seq` is a `bigserial`
-- -- a PostgreSQL sequence guarantees each value handed out is strictly
-- greater than every value already handed out, even under concurrent
-- inserts, which neither `event_id` (an opaque, caller-supplied string)
-- nor `recorded_at`/`occurred_at` (wall-clock timestamps, not guaranteed
-- unique or monotonic across concurrent transactions) can promise on their
-- own -- exactly the stable, gap-tolerant-but-never-out-of-order ordering
-- C-15's own prefix-strict comparison needs. Populated only by WP-4's
-- control-plane product code -- this WP creates the durable,
-- privilege-shaped table only.
CREATE TABLE IF NOT EXISTS mitatedb_registry.control_audit (
    audit_seq     bigserial UNIQUE,
    event_id      text PRIMARY KEY,
    event_class   text NOT NULL,
    occurred_at   timestamptz NOT NULL,
    request_id    text,
    application_id text,
    actor_type    text,
    actor_id      text,
    role          text,
    operation     text NOT NULL,
    target_kind   text,
    outcome       text NOT NULL,
    reason_code   text,
    recorded_at   timestamptz NOT NULL DEFAULT now()
);

REVOKE ALL ON SCHEMA mitatedb_registry FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA mitatedb_registry FROM PUBLIC;

-- Process-role separation (R-4): a login role per PROCESS, never per
-- request, and never carrying provisioning authority (CREATEDB/
-- CREATEROLE stay exclusively on `mitatedbsvc_provision`, 0001).
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mitatedbsvc_api') THEN
        CREATE ROLE mitatedbsvc_api LOGIN PASSWORD NULL NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT CONNECTION LIMIT 20;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mitatedbsvc_controlplane') THEN
        CREATE ROLE mitatedbsvc_controlplane LOGIN PASSWORD NULL NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT CONNECTION LIMIT 10;
    END IF;
END
$$;

-- `CREATE ROLE ... LOGIN PASSWORD NULL` above deliberately creates a role
-- with NO usable password (a real operator sets one with `ALTER ROLE ...
-- PASSWORD '<secret>'` immediately after, out of band -- never written to
-- this repository). `\gexec`-based idempotent `ALTER ROLE PASSWORD` is
-- intentionally NOT automated here: rotating either process role's own
-- password is an operator action with its own runbook step (WP-6), not
-- something a re-run of this migration file should silently redo.

GRANT CONNECT ON DATABASE mitatedb_platform TO mitatedbsvc_api;
GRANT CONNECT ON DATABASE mitatedb_platform TO mitatedbsvc_controlplane;
GRANT USAGE ON SCHEMA mitatedb_registry TO mitatedbsvc_api;
GRANT USAGE ON SCHEMA mitatedb_registry TO mitatedbsvc_controlplane;

-- Application-plane process role (R-4): READ-ONLY on `applications`/
-- `credentials` (its own `authenticate()` path, WP-2), and NO grant of
-- any kind on `control_credentials`/`control_audit` -- it has no SQL
-- operation available against either table, not merely a convention not
-- to use one.
GRANT SELECT ON mitatedb_registry.applications TO mitatedbsvc_api;
GRANT SELECT ON mitatedb_registry.credentials TO mitatedbsvc_api;

-- Control-plane process role (R-4): full lifecycle authority on
-- `applications`/`credentials`/`control_credentials`, but `control_audit`
-- is INSERT-only -- no SELECT/UPDATE/DELETE grant at all, so this role
-- structurally cannot read back, alter, or erase its own audit trail
-- (append-only by privilege, not by application-code discipline; WP-4's
-- product code inherits this as a hard boundary, not a convention it
-- could accidentally violate).
GRANT SELECT, INSERT, UPDATE ON mitatedb_registry.applications TO mitatedbsvc_controlplane;
GRANT SELECT, INSERT, UPDATE ON mitatedb_registry.credentials TO mitatedbsvc_controlplane;
GRANT SELECT, INSERT, UPDATE ON mitatedb_registry.control_credentials TO mitatedbsvc_controlplane;
GRANT INSERT ON mitatedb_registry.control_audit TO mitatedbsvc_controlplane;
-- `audit_seq bigserial`'s own implicit sequence needs an explicit `USAGE`
-- grant separate from the table's own `INSERT` grant above -- PostgreSQL
-- does not fold "may call nextval() for this column's identity sequence"
-- into a plain table-level `INSERT` grant for a non-owner role.
GRANT USAGE ON SEQUENCE mitatedb_registry.control_audit_audit_seq_seq TO mitatedbsvc_controlplane;

-- R-1 (independent review M-3, generalized by round-2 M-6 -- this
-- supersedes the original `assert_role_is_not_member_of(p_role,
-- p_forbidden_role)`; m-9's own suggestion to widen detection to
-- `pg_has_role(..., 'MEMBER')` -- transitive membership -- is ABSORBED by
-- this generalization rather than applied on top of it: a role with ZERO
-- direct memberships in ANY group has no transitive membership in any
-- group either, by construction, so checking "zero memberships" already
-- implies "not transitively a member of `cloudsqlsuperuser`" and every
-- other named role at once).
--
-- M-6 (independent review round 2, real finding): the original narrower
-- check missed a real containment hole. `begin_provision_application`'s
-- own `CREATE ROLE ... EXCEPTION WHEN duplicate_object -> ALTER ROLE`
-- fallback (M-2) only ever touches `LOGIN`/`PASSWORD`/`CONNECTION LIMIT`
-- -- confirmed empirically while fixing M-2 (a non-superuser executor
-- cannot even REDUNDANTLY restate `NOSUPERUSER` via `ALTER ROLE`). If a
-- role bearing this application's own EXPECTED derived name already
-- existed with `INHERIT` and membership in some unrelated ("foreign")
-- group -- a hijack scenario, or simply a leftover from an unrelated
-- prior use of the same cluster -- that fallback would silently ADOPT it
-- as this application's own runtime/developer role, attributes and group
-- memberships intact, defeating R-1's own containment claim the moment
-- that foreign group carried any privilege at all.
--
-- This function checks BOTH halves fail-closed, after EITHER the
-- `CREATE ROLE` or the `ALTER ROLE` fallback branch has run: (1) the
-- four attributes a freshly `CREATE ROLE`d application role always has --
-- `NOSUPERUSER`/`NOCREATEDB`/`NOCREATEROLE`/`LOGIN` (`NOT rolcanlogin`
-- would mean this role could never even authenticate, equally wrong) --
-- and (2) zero rows in `pg_auth_members` naming this role as a MEMBER of
-- anything. Deliberately does NOT try to remediate via `ALTER`/`REVOKE`
-- (a non-superuser executor cannot safely strip `SUPERUSER`/`CREATEDB`/
-- `CREATEROLE` from a role that already has one of them -- the same
-- privilege boundary M-2's own `ALTER ROLE` fallback had to work around
-- by never restating those attributes at all) -- it only ever VERIFIES
-- and, on any violation, `RAISE EXCEPTION`s to abort the whole
-- provisioning attempt (fail-closed: an operator must resolve the
-- pre-existing role by hand before retrying, not have this migration set
-- guess how).
CREATE OR REPLACE FUNCTION mitatedb_registry.assert_role_has_no_memberships(p_role text) RETURNS void
LANGUAGE plpgsql
AS $fn$
DECLARE
    v_rolsuper boolean;
    v_rolcreatedb boolean;
    v_rolcreaterole boolean;
    v_rolinherit boolean;
    v_rolcanlogin boolean;
    v_membership_count integer;
BEGIN
    SELECT rolsuper, rolcreatedb, rolcreaterole, rolinherit, rolcanlogin
    INTO v_rolsuper, v_rolcreatedb, v_rolcreaterole, v_rolinherit, v_rolcanlogin
    FROM pg_roles WHERE rolname = p_role;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'role % does not exist', p_role;
    END IF;

    -- The four attribute checks mirror this SAME migration's own
    -- `CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB
    -- NOCREATEROLE NOINHERIT CONNECTION LIMIT ...` statement below
    -- exactly -- `rolinherit` MUST be false (`NOINHERIT`) here too, not
    -- only the three privilege-escalation attributes: an `INHERIT` role
    -- automatically exercises every privilege of every group it is ever
    -- (even later) made a member of without a separate `SET ROLE`, which
    -- is exactly the silent-adoption risk this whole function exists to
    -- catch.
    IF v_rolsuper OR v_rolcreatedb OR v_rolcreaterole OR v_rolinherit OR NOT v_rolcanlogin THEN
        RAISE EXCEPTION
            'role % has unexpected attributes (rolsuper=%, rolcreatedb=%, rolcreaterole=%, rolinherit=%, rolcanlogin=%) -- refusing to provision (fail-closed, R-1/M-6)',
            p_role, v_rolsuper, v_rolcreatedb, v_rolcreaterole, v_rolinherit, v_rolcanlogin;
    END IF;

    SELECT count(*) INTO v_membership_count
    FROM pg_auth_members m
    JOIN pg_roles member ON member.oid = m.member
    WHERE member.rolname = p_role;

    IF v_membership_count > 0 THEN
        RAISE EXCEPTION
            'role % has % unexpected group membership(s) -- refusing to provision (fail-closed, R-1/M-6)',
            p_role, v_membership_count;
    END IF;
END;
$fn$;

REVOKE ALL ON FUNCTION mitatedb_registry.assert_role_has_no_memberships(text) FROM PUBLIC;

-- Step 1 of provisioning (called by 0003, before `CREATE DATABASE`): see
-- this file's header for the WP-1 scoping note on why this ALSO performs
-- registration. Validates the application id against the CONTRACT's own
-- stricter `control_plane.identifiers` rule (`^[a-z][a-z0-9_]{0,32}$` --
-- deliberately narrower than `mitatedb_api.identifiers._IDENTIFIER`'s
-- general `{0,62}` rule, per spec/data-service-api.v1.json's own
-- reasoning: an application_id becomes platform namespace material,
-- where length decoration makes the general rule unsafe -- P3 WP-1 round
-- 2 instruction #2), derives this application's own database/role names,
-- and creates the two login roles -- but does NOT yet mark the
-- application provisioned (that is `finish_provision_application`,
-- called only once 0003's database/schema setup has fully succeeded).
CREATE OR REPLACE FUNCTION mitatedb_registry.begin_provision_application(
    p_app_id text,
    p_runtime_password text,
    p_developer_password text
) RETURNS TABLE(database_name text, runtime_role text, developer_role text)
LANGUAGE plpgsql
AS $fn$
DECLARE
    v_database_name text := 'mitatedb_app_' || p_app_id;
    v_runtime_role text := v_database_name || '_rt';
    v_developer_role text := v_database_name || '_dv';
BEGIN
    IF p_app_id !~ '^[a-z][a-z0-9_]{0,32}$' THEN
        RAISE EXCEPTION 'invalid application_id: %', p_app_id;
    END IF;

    -- P3 WP-1 round 2 instruction #2: a NAMEDATALEN (63-byte) truncation
    -- accident must fail loudly, not silently truncate two DIFFERENT
    -- application databases' derived role names down to the same 63-byte
    -- prefix. `v_developer_role` is always the longest of the three
    -- derived names (`v_database_name` + `_dv`, longer than `_rt`), so
    -- checking it alone covers all three. Under this migration set's own
    -- own prefix-replacement convention (this file's header), the
    -- production stem (`mitatedb_app_..._dv`, ~15 fixed bytes plus
    -- `p_app_id`) and the test harness's own throwaway prefix (`tests/
    -- test_postgres.py`, deliberately kept short, see that file's own
    -- header) both stay well under this bound even at `p_app_id`'s own
    -- maximum length (33 bytes) -- this check exists as an explicit,
    -- fail-loud proof of that fact, not merely an assumption, and would
    -- catch a FUTURE prefix convention change that broke it.
    IF octet_length(v_developer_role) > 63 THEN
        RAISE EXCEPTION 'derived role name exceeds PostgreSQL NAMEDATALEN (63 bytes): %', v_developer_role;
    END IF;

    IF p_runtime_password IS NULL OR p_developer_password IS NULL
       OR length(p_runtime_password) < 16 OR length(p_developer_password) < 16 THEN
        RAISE EXCEPTION 'runtime/developer passwords must be supplied and at least 16 characters';
    END IF;

    IF EXISTS (
        SELECT 1 FROM mitatedb_registry.applications a
        WHERE a.application_id = p_app_id AND a.database_name IS NOT NULL
    ) THEN
        RAISE EXCEPTION 'application already provisioned: %', p_app_id;
    END IF;

    -- Two-state registration (see this file's header WP-1 scoping note):
    -- create the "registered, unprovisioned" row if this application_id
    -- has never been seen before. A row that already exists with
    -- `database_name IS NULL` (a previous provisioning attempt that
    -- failed before `finish_provision_application` ran) is left as-is and
    -- this call proceeds to (re-)attempt role creation.
    INSERT INTO mitatedb_registry.applications (application_id)
    VALUES (p_app_id)
    ON CONFLICT (application_id) DO NOTHING;

    -- M-2 (independent review): crash-retry safety. A previous attempt at
    -- this SAME application_id may already have created these two roles
    -- (this function's own registration INSERT above is `ON CONFLICT DO
    -- NOTHING`-idempotent, but a bare `CREATE ROLE` is not -- a retry
    -- after a crash between role creation and `finish_provision_
    -- application` used to fail outright on `duplicate_object`, wedging
    -- the ghost row permanently). `EXCEPTION WHEN duplicate_object` here
    -- falls back to `ALTER ROLE`, resetting the role's password to
    -- exactly what THIS call supplied -- so a retry both succeeds AND
    -- leaves the caller able to actually authenticate with the password
    -- it just generated (not silently stuck with whichever password an
    -- earlier, abandoned attempt happened to pick).
    --
    -- The `ALTER ROLE` fallback deliberately does NOT re-specify
    -- `NOSUPERUSER`/`NOCREATEDB`/`NOCREATEROLE`/`NOINHERIT` (only `LOGIN
    -- PASSWORD ... CONNECTION LIMIT ...`, unlike the `CREATE ROLE` branch
    -- above): confirmed empirically while writing this migration --
    -- PostgreSQL refuses ANY `ALTER ROLE` statement that even
    -- REDUNDANTLY restates the `SUPERUSER`/`NOSUPERUSER` attribute
    -- (`permission denied to alter role ... Only roles with the
    -- SUPERUSER attribute may change the SUPERUSER attribute`) from a
    -- non-superuser executor, even when the value being set is identical
    -- to the role's own current one -- `mitatedbsvc_provision` is
    -- deliberately never superuser (0001's own role definition), so this
    -- clause must be dropped from the fallback entirely. The other three
    -- attributes were already set correctly by whichever `CREATE ROLE`
    -- created this role in the first place and are not being changed, so
    -- omitting them here changes nothing about the role's own privileges.
    BEGIN
        EXECUTE format(
            'CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT CONNECTION LIMIT 20',
            v_runtime_role, p_runtime_password
        );
    EXCEPTION WHEN duplicate_object THEN
        EXECUTE format(
            'ALTER ROLE %I LOGIN PASSWORD %L CONNECTION LIMIT 20',
            v_runtime_role, p_runtime_password
        );
    END;
    BEGIN
        EXECUTE format(
            'CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT CONNECTION LIMIT 10',
            v_developer_role, p_developer_password
        );
    EXCEPTION WHEN duplicate_object THEN
        EXECUTE format(
            'ALTER ROLE %I LOGIN PASSWORD %L CONNECTION LIMIT 10',
            v_developer_role, p_developer_password
        );
    END;

    -- M-3/M-6 (independent review, R-1 explicit requirement): see this
    -- function's own preceding `assert_role_has_no_memberships`
    -- definition -- fires fail-closed for EITHER role if it (already
    -- existed and) carries `SUPERUSER`/`CREATEDB`/`CREATEROLE`/`INHERIT`
    -- or ANY group membership at all, which subsumes the original M-3
    -- concern (a `cloudsqlsuperuser` membership specifically) as one
    -- instance of the general case.
    PERFORM mitatedb_registry.assert_role_has_no_memberships(v_runtime_role);
    PERFORM mitatedb_registry.assert_role_has_no_memberships(v_developer_role);

    -- m-11 (independent review round 2): write the derived role names
    -- into the registry row NOW, while `database_name` is still NULL
    -- (the two-state "unprovisioned" marker, R-4) -- not only at
    -- `finish_provision_application` time. Without this, a crash between
    -- here and `finish_provision_application` left `0004_deprovision_
    -- application.sql`'s own `begin_deprovision_application` unable to
    -- discover these two ALREADY-CREATED roles at all (it reads role
    -- names FROM this table), leaking them forever even though the
    -- REGISTRY row itself could still be cleaned up. `database_name`
    -- itself is deliberately left untouched here -- it stays the ONLY
    -- signal `0004`'s own `\if :{?database_name}` branch uses to decide
    -- whether a database (and not just roles) needs dropping.
    UPDATE mitatedb_registry.applications
    SET runtime_role = v_runtime_role, developer_role = v_developer_role
    WHERE application_id = p_app_id;

    RETURN QUERY SELECT v_database_name, v_runtime_role, v_developer_role;
END;
$fn$;

REVOKE ALL ON FUNCTION mitatedb_registry.begin_provision_application(text, text, text) FROM PUBLIC;

-- Step 2 of provisioning (called by 0003, once the database and its
-- `public` schema/role setup have fully succeeded): fills in the
-- previously-NULL allocated names, completing the two-state transition.
CREATE OR REPLACE FUNCTION mitatedb_registry.finish_provision_application(
    p_app_id text,
    p_database_name text,
    p_runtime_role text,
    p_developer_role text
) RETURNS void
LANGUAGE plpgsql
AS $fn$
BEGIN
    UPDATE mitatedb_registry.applications
    SET database_name = p_database_name,
        runtime_role = p_runtime_role,
        developer_role = p_developer_role,
        provisioned_at = now()
    WHERE application_id = p_app_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'application not registered: %', p_app_id;
    END IF;
END;
$fn$;

REVOKE ALL ON FUNCTION mitatedb_registry.finish_provision_application(text, text, text, text) FROM PUBLIC;

-- Step 1 of deprovisioning (called by 0004, before any destructive
-- statement): looks up the registered names for an application_id.
-- Raises loudly (aborting 0004, `ON_ERROR_STOP`) if the application was
-- never registered at all -- deprovisioning something that was never
-- registered is an operator error worth surfacing, not a condition worth
-- silently absorbing. `database_name` in the returned row MAY be NULL (a
-- registered-but-never-provisioned application, R-4's own two-state
-- registry) -- 0004 uses that to skip its own database/role-drop steps
-- for such a row while still letting `finish_deprovision_application`
-- remove it (C-14 vector 5's own cleanup requirement: "登録のみでDBを
-- 持たない行も撤去できること").
CREATE OR REPLACE FUNCTION mitatedb_registry.begin_deprovision_application(p_app_id text)
RETURNS TABLE(database_name text, runtime_role text, developer_role text)
LANGUAGE plpgsql
AS $fn$
BEGIN
    RETURN QUERY
        SELECT a.database_name, a.runtime_role, a.developer_role
        FROM mitatedb_registry.applications a
        WHERE a.application_id = p_app_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'application not registered: %', p_app_id;
    END IF;
END;
$fn$;

REVOKE ALL ON FUNCTION mitatedb_registry.begin_deprovision_application(text) FROM PUBLIC;

-- Step 2 of deprovisioning (called by 0004, once any database/roles that
-- existed have been dropped): unconditionally removes the registry row,
-- whether or not it ever reached "provisioned" (see this function's own
-- header note above `begin_deprovision_application`).
--
-- M-4 (independent review, adjudicated): the previous revision required a
-- separate `assert_no_credentials_for_deprovision` guard BEFORE any
-- destructive step, refusing to deprovision an application with any
-- surviving `credentials` row. Removed: deprovisioning IS the terminal,
-- whole-namespace removal of an application (its database and both roles
-- are being dropped by 0004 in the same run), so removing its remaining
-- `credentials` rows in the SAME step is not in tension with revoke's own
-- terminality (SI-13) -- a credential belonging to an application that no
-- longer exists at all is not "un-revoked", it is removed along with the
-- namespace it was ever scoped to. `control_audit` (the durable evidence
-- trail) is NEVER touched here -- only `credentials` (the live
-- authentication material) and the `applications` row itself, both
-- deleted together as ONE plpgsql function body (a single top-level
-- statement's implicit transaction), so a crash between the two deletes
-- is not possible. `mitatedbsvc_controlplane` (the control-plane PROCESS
-- role) still has no `DELETE` grant on `credentials` at all (0002's own
-- grants above) -- only `mitatedbsvc_provision` (the provisioning
-- role that OWNS this function and the whole schema) can ever reach this
-- path, exactly the same authority `0004`'s other destructive steps
-- (`DROP DATABASE`/`DROP ROLE`) already require.
CREATE OR REPLACE FUNCTION mitatedb_registry.finish_deprovision_application(p_app_id text) RETURNS void
LANGUAGE plpgsql
AS $fn$
BEGIN
    DELETE FROM mitatedb_registry.credentials WHERE application_id = p_app_id;
    DELETE FROM mitatedb_registry.applications WHERE application_id = p_app_id;
END;
$fn$;

REVOKE ALL ON FUNCTION mitatedb_registry.finish_deprovision_application(text) FROM PUBLIC;
