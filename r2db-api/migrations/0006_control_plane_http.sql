-- r2db-api PostgreSQL provisioning -- 0006: control-plane HTTP surface
-- storage (CCR-14 WP-2)
--
-- WHO RUNS THIS: the operator, connected to the `r2dbsvc_platform` database
-- (created by 0001) AS the `r2dbsvc_control` role -- the same role/connection
-- 0002/0005 already run as. Run once, after 0002 and 0005:
--
--   psql "$R2DBSVC_CONTROL_DSN" -v controlplane_password="$R2DBSVC_CONTROLPLANE_PASSWORD" \
--     -f 0006_control_plane_http.sql
--
-- `R2DBSVC_CONTROLPLANE_PASSWORD` is an environment-variable *name*; see
-- r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md. This file never contains a
-- real credential.
--
-- WHAT THIS FILE DOES (design docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md,
-- WP-2 row of §5 -- R-2/R-3/R-4/R-5/R-6/R-10): CCR-14 introduces a public
-- `/control/v1` HTTP surface (built in a later WP) whose storage needs are
-- laid down here, ahead of that surface, so this migration -- like every
-- other one in this set -- can be reviewed and applied independently of the
-- application code that will eventually use it:
--
--   1. (R-4/§8 B-1) `applications` becomes two-state: a row can now be
--      *registered* (exists, no provisioning columns set) as well as
--      *provisioned* (the pre-existing all-columns-set state). The v1 schema
--      made `database_name`/`runtime_role`/`developer_role`/`provisioned_at`
--      `NOT NULL`, which cannot represent "registered, not yet provisioned"
--      at all -- registering with placeholder values would have permanently
--      blocked real provisioning for that slug (0002's own
--      `already provisioned` guard). `begin_provision_application`/
--      `begin_deprovision_application` are revised to understand the new
--      state.
--   2. (R-2) `control_credentials` -- a table structurally incapable of
--      holding an application credential (no `application_slug` column at
--      all, unlike `credentials`) or of being confused with one (`role`
--      does not exist as a column here either -- there is nothing to set to
--      `'control'`).
--   3. (R-6) `control_audit` -- a durable, append-only sink for
--      control-plane audit events (contract `audit.fields`, all 12 named
--      columns, plus `recorded_at`). Existing `r2db_api.audit.AuditSink` is
--      in-memory only, which cannot satisfy contract `audit.sink_failure_
--      policy`'s fail-closed requirement for a public HTTP control surface.
--   4. (R-3) `r2dbsvc_controlplane` -- the new least-privilege login role
--      the (still not-yet-built) control-plane HTTP process will connect
--      as. Never `r2dbsvc_control` (the operator/CLI role 0002/0003/0004/
--      0005 already use) -- a long-lived public-facing HTTP process must
--      not carry that role's provisioning authority. Every `GRANT` below is
--      commented with the contract/design requirement it exists for; the
--      absence of a grant is as load-bearing as its presence (see §7 of the
--      design: this table is "the safety of the whole design" -- reviewed
--      accordingly).
--
-- IDEMPOTENCY: `ALTER TABLE ... ALTER COLUMN ... DROP NOT NULL`/`DROP
-- DEFAULT` are natively idempotent (a no-op if already dropped, never an
-- error). `CREATE TABLE IF NOT EXISTS` is natively idempotent. `ADD
-- CONSTRAINT` has no `IF NOT EXISTS` form in PostgreSQL (confirmed
-- empirically against the PostgreSQL 16 server this file was developed
-- against: `ALTER TABLE ... ADD CONSTRAINT IF NOT EXISTS ...` is a syntax
-- error, unlike `CREATE TABLE`/`CREATE SCHEMA`), so its idempotency is a
-- `pg_constraint` catalog check inside a `DO $$ ... $$` block, the same
-- "check the catalog, then act" idiom `0004`'s `to_regprocedure` check
-- already uses for a different catalog. `CREATE OR REPLACE FUNCTION` is
-- natively idempotent and -- confirmed against PostgreSQL's own documented
-- behaviour -- does not reset a function's ACL, so the `REVOKE ALL ... FROM
-- PUBLIC` `0002` already applied to `begin_provision_application`/
-- `begin_deprovision_application` survives this file's `CREATE OR REPLACE`
-- of both. `CREATE ROLE` uses the same conditional-`\gexec` idiom `0001`/
-- `0005` already established. `GRANT` is naturally idempotent. Re-running
-- this file after it has already succeeded is a no-op.

\set ON_ERROR_STOP on

-- ===========================================================================
-- 1.1: `applications` two-state (R-4, §8 B-1)
-- ===========================================================================

ALTER TABLE r2dbsvc_registry.applications ALTER COLUMN database_name DROP NOT NULL;
ALTER TABLE r2dbsvc_registry.applications ALTER COLUMN runtime_role DROP NOT NULL;
ALTER TABLE r2dbsvc_registry.applications ALTER COLUMN developer_role DROP NOT NULL;
ALTER TABLE r2dbsvc_registry.applications ALTER COLUMN provisioned_at DROP NOT NULL;
-- The `DEFAULT now()` on `provisioned_at` is dropped too: a *registration*
-- INSERT (no provisioning columns supplied) must leave `provisioned_at`
-- NULL, not have it silently default to the registration timestamp -- which
-- would make the row's own provisioning-state test (below) always read
-- "provisioned" the instant a registration INSERT ran, defeating the whole
-- point of this two-state change.
ALTER TABLE r2dbsvc_registry.applications ALTER COLUMN provisioned_at DROP DEFAULT;

-- "Provisioned" is judged solely by `database_name IS NOT NULL` -- no new
-- status column is introduced (design's own explicit instruction). This
-- CHECK is what makes the two representable states ("registered": all four
-- NULL; "provisioned": all four NOT NULL) the *only* representable states --
-- a half-filled row (e.g. `database_name` set but `runtime_role` still NULL)
-- can never exist, so every reader of this table (this file's own revised
-- functions, `r2db_api.main`'s startup registry read, a future `/control/v1`
-- HTTP handler) can test provisioning state with one `IS NOT NULL` check and
-- trust the other three columns agree.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'applications_registration_state_check'
          AND conrelid = 'r2dbsvc_registry.applications'::regclass
    ) THEN
        ALTER TABLE r2dbsvc_registry.applications
            ADD CONSTRAINT applications_registration_state_check
            CHECK (
                (database_name IS NULL AND runtime_role IS NULL AND developer_role IS NULL AND provisioned_at IS NULL)
                OR
                (database_name IS NOT NULL AND runtime_role IS NOT NULL AND developer_role IS NOT NULL AND provisioned_at IS NOT NULL)
            );
    END IF;
END;
$$;

-- Step 1 of provisioning, revised for the two-state registry (round 2 of
-- the independent review, ruling (B) -- see this file's header and the
-- WP-2 implementation report's Round 2 section for the full history). The
-- round-1 revision of this function had `begin_provision_application`
-- itself `UPDATE` a pre-existing registered row's four provisioning
-- columns, *before* `CREATE DATABASE` (0003) had run at all -- which
-- narrowed the original crash-safety property (0002's own header: "a crash
-- partway through 0003 never leaves the registry claiming an application is
-- fully provisioned when its database/schema setup did not complete") for
-- that one path. Ruling (B) rejects that trade: **this function now writes
-- NOTHING to `applications`, in every case** -- it does exactly two things,
-- neither of which is a registry write:
--
--   1. the already-provisioned guard: raises `'application already
--      provisioned: %'` only when a row exists for this slug AND its
--      `database_name IS NOT NULL`. A registered-only row (exists, `database_
--      name IS NULL`) or no row at all both pass this guard untouched --
--      the two are deliberately not distinguished here any more, because
--      neither case needs `begin` to do anything different for it.
--   2. the two `CREATE ROLE` statements (unchanged).
--
-- `FOR UPDATE` still locks a pre-existing row for the duration of this
-- function, serializing concurrent `begin_provision_application` calls
-- against the same slug; `FOUND` (not a hand-rolled `v_row_found boolean`
-- flag) is used to test row existence -- a bare `SELECT ... INTO target`
-- assigns `NULL` to every target on zero rows (not the target's `DECLARE`
-- default), which made the round-1 revision's `v_row_found AND ...` guard
-- correct only by three-valued-logic coincidence (`NULL AND x` is `NULL`,
-- which is falsy in an `IF`, same outcome as `false AND x` -- reviewer
-- MI-4). `FOUND` has no such trap.
--
-- With this function writing nothing, `finish_provision_application`
-- (below, also revised) becomes the *only* place `applications` is ever
-- written during provisioning, for both the operator-first (no
-- pre-existing row) and registered-row flows alike -- so the original
-- crash-safety property now holds identically for both: a crash any time
-- before `finish` runs (including one between this function's `CREATE
-- ROLE` statements and 0003's `CREATE DATABASE`) leaves `applications`
-- exactly as it was before `begin` ran (no row, or still a registered-only
-- row) -- never a false claim of provisioning. The §4.3 "crash-safety
-- narrowing" caveat recorded in the WP-2 implementation report's Round 1
-- section is superseded by this change; that report's Round 2 section
-- records the supersession explicitly.
--
-- KNOWN, UNCHANGED, PRE-EXISTING WART (not fixed here -- a WP-6 runbook
-- item, not code): a crash between this function's two `CREATE ROLE`
-- statements and `finish_provision_application` leaves the two login roles
-- created but no registry claim of provisioning at all (`applications`
-- correctly still shows "not provisioned", so no request is ever routed
-- against a half-provisioned application -- the safety property above
-- holds) -- but the two roles themselves are now residue: a later
-- provisioning retry for the same slug fails at `CREATE ROLE ... already
-- exists` until an operator manually drops them. This exact residue-on-
-- crash risk already existed for the *pre-0006* single-state registry (the
-- original `begin_provision_application`, `0002`, has the identical
-- structure: `CREATE ROLE` before any registry write) -- 0006 does not
-- introduce it and is not the right place to fix it; it belongs in the
-- provisioning runbook (WP-6) as an operator recovery step, not a code
-- change to this function.
CREATE OR REPLACE FUNCTION r2dbsvc_registry.begin_provision_application(
    p_app_slug text,
    p_runtime_password text,
    p_developer_password text
) RETURNS TABLE(database_name text, runtime_role text, developer_role text)
LANGUAGE plpgsql
AS $fn$
DECLARE
    v_database_name text := 'r2dbsvc_app_' || p_app_slug;
    v_runtime_role text := 'r2dbsvc_app_' || p_app_slug || '_runtime';
    v_developer_role text := 'r2dbsvc_app_' || p_app_slug || '_developer';
    v_existing_database_name text;
BEGIN
    -- Unchanged from 0002: same identifier syntax policy, same password
    -- length floor.
    IF p_app_slug !~ '^[a-z][a-z0-9_]{0,32}$' THEN
        RAISE EXCEPTION 'invalid application slug: %', p_app_slug;
    END IF;
    IF p_runtime_password IS NULL OR p_developer_password IS NULL OR length(p_runtime_password) < 16 OR length(p_developer_password) < 16 THEN
        RAISE EXCEPTION 'runtime/developer passwords must be supplied and at least 16 characters';
    END IF;

    SELECT a.database_name INTO v_existing_database_name
        FROM r2dbsvc_registry.applications a
        WHERE a.application_slug = p_app_slug
        FOR UPDATE;
    IF FOUND AND v_existing_database_name IS NOT NULL THEN
        RAISE EXCEPTION 'application already provisioned: %', p_app_slug;
    END IF;

    EXECUTE format(
        'CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT CONNECTION LIMIT 20',
        v_runtime_role, p_runtime_password
    );
    EXECUTE format(
        'CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT CONNECTION LIMIT 10',
        v_developer_role, p_developer_password
    );

    RETURN QUERY SELECT v_database_name, v_runtime_role, v_developer_role;
END;
$fn$;

-- Step 2 of provisioning, revised (ruling (B)): this is now the *only*
-- place `applications` is written during provisioning (see `begin_
-- provision_application`'s header above), for both the operator-first and
-- registered-row flows, via an explicit two-branch shape -- no `ON
-- CONFLICT` anywhere:
--
--   UPDATE ... SET database_name = ..., ... WHERE application_slug = ...
--                                          AND database_name IS NULL;
--   IF NOT FOUND THEN INSERT ... END IF;
--
-- Three cases:
--   (i)   no row at all (operator-first)   -- `UPDATE` matches zero rows
--                                              (no row to match at all) ->
--                                              `NOT FOUND` -> the `INSERT`
--                                              runs, exactly as the
--                                              pre-0006 single-state
--                                              version already did.
--   (ii)  registered-only row              -- `UPDATE` matches (`database_
--         (`database_name IS NULL`)           name IS NULL` is satisfied)
--                                              and fills all four columns
--                                              in place -> `FOUND` -> the
--                                              `INSERT` is skipped.
--   (iii) already-provisioned row          -- `UPDATE`'s `WHERE ... AND
--         (`database_name IS NOT NULL`)       database_name IS NULL` does
--                                              not match this row (0 rows
--                                              affected) -> `NOT FOUND` ->
--                                              falls into the `INSERT`
--                                              branch -> `INSERT` with this
--                                              already-existing `application_
--                                              slug` hits the `PRIMARY KEY`
--                                              constraint and raises
--                                              loudly. This is deliberate,
--                                              not a bug: case (iii) can
--                                              only be reached here if a
--                                              row was already fully
--                                              provisioned by the time
--                                              `finish` runs for the *same*
--                                              slug again (a caller bypassing
--                                              `begin`'s guard, or a true
--                                              race), and the correct
--                                              response to that is a loud,
--                                              unhandled conflict -- never a
--                                              silent no-op. The round-1
--                                              revision's `ON CONFLICT
--                                              (application_slug) DO
--                                              NOTHING` was rejected here
--                                              specifically because it also
--                                              silently masked a *different*
--                                              race: a registration landing
--                                              between `begin` and `finish`
--                                              for the *same* slug that
--                                              `begin` originally saw as "no
--                                              row at all" -- under `ON
--                                              CONFLICT DO NOTHING`, that
--                                              registration's row would have
--                                              blocked `finish`'s `INSERT`
--                                              and been left registered-only
--                                              forever, even though
--                                              provisioning had actually
--                                              succeeded. The two-branch
--                                              `UPDATE`-then-`INSERT` shape
--                                              fixes this: that scenario is
--                                              case (ii) from `finish`'s own
--                                              point of view (the row now
--                                              exists with `database_name
--                                              IS NULL` by the time `finish`
--                                              runs, regardless of whether
--                                              it existed when `begin` ran),
--                                              so the `UPDATE` branch
--                                              correctly completes it. See
--                                              `test_control_plane_store.py::
--                                              test_finish_completes_a_
--                                              registration_that_arrived_
--                                              between_begin_and_finish`.
--
-- `provisioned_at` is supplied explicitly (`now()`) in both branches, not
-- left to a column `DEFAULT` -- this migration drops `provisioned_at`'s own
-- `DEFAULT now()` (§1.1 above) precisely so a *registration*-only INSERT
-- (elsewhere, `application_slug`-only, no provisioning columns at all)
-- cannot silently acquire a provisioning timestamp it never earned.
CREATE OR REPLACE FUNCTION r2dbsvc_registry.finish_provision_application(
    p_app_slug text,
    p_database_name text,
    p_runtime_role text,
    p_developer_role text
) RETURNS void
LANGUAGE plpgsql
AS $fn$
BEGIN
    UPDATE r2dbsvc_registry.applications
        SET database_name = p_database_name, runtime_role = p_runtime_role, developer_role = p_developer_role, provisioned_at = now()
        WHERE application_slug = p_app_slug AND database_name IS NULL;
    IF NOT FOUND THEN
        INSERT INTO r2dbsvc_registry.applications (application_slug, database_name, runtime_role, developer_role, provisioned_at)
        VALUES (p_app_slug, p_database_name, p_runtime_role, p_developer_role, now());
    END IF;
END;
$fn$;

-- Step 1 of deprovisioning, revised: a registered-only row (`database_name
-- IS NULL`) must not be treated as a deprovisioning target -- design §7:
-- "登録済みのみの行は deprovision 対象にならない". The added `WHERE
-- a.database_name IS NOT NULL` means such a row simply does not match this
-- `SELECT`, so `NOT FOUND` fires -- the exact same `'application not
-- provisioned: %'` exception the "no row at all" case already raised,
-- reached through the same code path rather than a second, duplicated
-- `RAISE`. This closes the accident this function's revision exists to
-- prevent at the function level: a registered-only row's `database_name`
-- is NULL, and letting it reach `0004`'s `DROP DATABASE :"database_name"`
-- unchecked would attempt `DROP DATABASE NULL`, not a graceful refusal.
CREATE OR REPLACE FUNCTION r2dbsvc_registry.begin_deprovision_application(p_app_slug text)
RETURNS TABLE(database_name text, runtime_role text, developer_role text)
LANGUAGE plpgsql
AS $fn$
BEGIN
    RETURN QUERY
        SELECT a.database_name, a.runtime_role, a.developer_role
        FROM r2dbsvc_registry.applications a
        WHERE a.application_slug = p_app_slug AND a.database_name IS NOT NULL;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'application not provisioned: %', p_app_slug;
    END IF;
END;
$fn$;

-- `finish_deprovision_application` is unchanged (deletes the row outright;
-- a deprovisioned application's slug becomes free to register/provision
-- again from scratch, exactly as before this migration).

-- ===========================================================================
-- 1.2: control_credentials (R-2)
-- ===========================================================================

-- No `application_slug` column at all -- structurally incapable of
-- representing an application credential or of being confused with one.
-- `role` (the `credentials` table's `CHECK (role IN ('runtime',
-- 'developer'))` column) is likewise absent here: there is no column a
-- future `role = 'control'` value could ever be written to on this table,
-- and `credentials.role`'s own CHECK is left completely untouched by this
-- migration -- a control credential cannot enter `credentials` and an
-- application credential cannot enter `control_credentials`, by table shape,
-- not by application-level discipline alone.
CREATE TABLE IF NOT EXISTS r2dbsvc_registry.control_credentials (
    credential_id text PRIMARY KEY,      -- 'ctl_' + 16 hex
    verifier      text NOT NULL UNIQUE,
    enabled       boolean NOT NULL DEFAULT true,
    revoked       boolean NOT NULL DEFAULT false,
    must_rotate   boolean NOT NULL DEFAULT true,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now()
);
-- No explicit `REVOKE ... FROM PUBLIC` needed here -- same reasoning
-- `0005_credential_store.sql` already documents for `credentials`: a newly
-- created table inherits the closed-by-default posture nothing has ever
-- granted anything to `PUBLIC` on, in this schema.

-- ===========================================================================
-- 1.3: control_audit (R-6)
-- ===========================================================================

-- Contract `audit.fields`' 12 named fields, plus `recorded_at` (the DB-side
-- insertion timestamp -- distinct from `occurred_at`, the application-side
-- event timestamp `r2db_api.audit.AuditEvent` already computes; §8 M-9 of
-- the control-plane design: v1's in-memory `AuditEvent` already carries
-- both under those exact names). Nullability mirrors `AuditEvent`'s own
-- field types one-for-one (`r2db_api/audit.py`): the dataclass fields typed
-- plain `str` here are `NOT NULL`; the ones typed `str | None` allow NULL.
-- `event_id` is the contract's own event identifier, generated
-- application-side (`uuid.uuid4()`, matching `AuditSink.append`) and
-- supplied as this table's primary key -- never a server-generated
-- `gen_random_uuid()` default, so an application-side retry after a failed
-- INSERT and a later successful one can never collide on two different
-- server-assigned ids for what the application intended as one event.
CREATE TABLE IF NOT EXISTS r2dbsvc_registry.control_audit (
    event_id       uuid PRIMARY KEY,
    event_class    text NOT NULL,
    occurred_at    timestamptz NOT NULL,
    request_id     text NOT NULL,
    application_id text,
    actor_type     text NOT NULL,
    actor_id       text,
    role           text,
    operation      text NOT NULL,
    target_kind    text,
    outcome        text NOT NULL,
    reason_code    text,
    recorded_at    timestamptz NOT NULL DEFAULT now()
);
-- Same closed-by-default reasoning as `control_credentials` above -- no
-- explicit `REVOKE ... FROM PUBLIC` needed.

-- ===========================================================================
-- 1.4: role r2dbsvc_controlplane + GRANTs (R-3 -- "本設計の安全の要"; every
-- line below is commented with the exact design requirement it satisfies,
-- per the design's own instruction that this table be reviewed against the
-- contract line by line)
-- ===========================================================================

SELECT format(
    'CREATE ROLE r2dbsvc_controlplane LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT CONNECTION LIMIT 10',
    :'controlplane_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'r2dbsvc_controlplane')
\gexec

GRANT CONNECT ON DATABASE r2dbsvc_platform TO r2dbsvc_controlplane;
GRANT USAGE ON SCHEMA r2dbsvc_registry TO r2dbsvc_controlplane;

-- R-3: `applications` -- SELECT/INSERT/UPDATE (register a new slug; flip
-- `enabled`). Deliberately no DELETE: this design's `application_deletion`
-- stays out of v1 scope (contract), and the control-plane process must
-- never be able to remove a registry row -- `disable` is the only terminal
-- state it can reach.
GRANT SELECT, INSERT, UPDATE ON r2dbsvc_registry.applications TO r2dbsvc_controlplane;

-- R-3: `credentials` -- SELECT/INSERT/UPDATE (issue/rotate/revoke/disable/
-- enable *application* credentials, in-band). Deliberately no DELETE:
-- `delete-credential` (a genuinely destructive, irreversible row removal;
-- see `credential_store.py::PostgresCredentialStore.delete`'s own
-- docstring) stays a CLI-only, out-of-band operation not reachable from the
-- control-plane process at all.
GRANT SELECT, INSERT, UPDATE ON r2dbsvc_registry.credentials TO r2dbsvc_controlplane;

-- R-3: `control_credentials` -- SELECT/UPDATE only. Deliberately NO INSERT:
-- the only way a control_credentials row can ever be created is the
-- out-of-band bootstrap/reset ritual (`python -m r2db_api.ops`, connected as
-- `r2dbsvc_control`, never as `r2dbsvc_controlplane`) -- this is the
-- database-privilege half of "control credential issuance is out-of-band
-- only" (spec/CCR_DISPOSITION.md's "案B"), independent of and in addition to
-- the application-level enforcement (no in-band issue endpoint/CLI
-- subcommand exists for `role=control` at all). No DELETE either: a revoked
-- control credential's row stays on record, exactly like a revoked
-- application credential's.
GRANT SELECT, UPDATE ON r2dbsvc_registry.control_credentials TO r2dbsvc_controlplane;

-- R-3/R-6: `control_audit` -- INSERT only. No SELECT/UPDATE/DELETE: the
-- control-plane process can append audit events but can never read, alter,
-- or erase them back out -- append-only is enforced at the database-
-- privilege level for this role, not merely by application code choosing
-- not to call an UPDATE/DELETE it could otherwise issue. (This append-only
-- guarantee holds specifically *from this role*; the schema owner,
-- `r2dbsvc_control`, retains owner-level privilege over this table by
-- normal PostgreSQL ownership semantics -- see the next GRANT's comment.)
GRANT INSERT ON r2dbsvc_registry.control_audit TO r2dbsvc_controlplane;

-- m-3 (design §8/§1 R-3): `r2dbsvc_control` (the out-of-band ritual/CLI
-- role -- also 0002/0003/0004's provisioning role, and this schema's owner
-- via 0002's `CREATE SCHEMA ... AUTHORIZATION r2dbsvc_control`) is given an
-- *explicit* INSERT grant on `control_audit` here too -- `python -m
-- r2db_api.ops`'s bootstrap/reset/break-glass commands write canonical
-- audit events into this same table, and that must not rely on schema-owner
-- privilege implicitly covering it. Owner privilege happens to make this
-- grant redundant in practice (an owner can always INSERT into its own
-- table), but the design explicitly calls for stating it, not assuming it:
-- a future change to who owns this schema, or to how `r2dbsvc_control`
-- itself is granted, must not silently revoke the CLI's ability to write
-- audit rows as a side effect nobody noticed.
GRANT INSERT ON r2dbsvc_registry.control_audit TO r2dbsvc_control;

-- m-5 (design §1 R-3/§7, a reviewer confirmation item, not a statement this
-- file needs to make in SQL): no `GRANT EXECUTE` on any provisioning
-- function (`begin_provision_application`, `finish_provision_application`,
-- `begin_deprovision_application`, `finish_deprovision_application`, or
-- `0005`'s `assert_no_credentials_for_deprovision`) to `r2dbsvc_controlplane`
-- appears anywhere in this file, and no `GRANT` on any `SEQUENCE`/`FUNCTION`
-- object appears anywhere in this file at all (`control_credentials`/
-- `control_audit` both use application-generated `text`/`uuid` primary
-- keys, never a `SERIAL`/`IDENTITY` column, so no sequence exists to grant
-- on in the first place). `r2dbsvc_controlplane` also never receives
-- `CREATEDB`/`CREATEROLE`/`SUPERUSER` (it is not granted any role attribute
-- beyond its own `CREATE ROLE ... LOGIN` statement above, which grants
-- none of those). A control-plane process compromised end-to-end can only
-- ever reach the six privileges explicitly listed above -- it cannot create
-- a control credential, drop an application, run a provisioning function,
-- or escalate through role/sequence/function grants that do not exist.
