-- MitateDB-api PostgreSQL provisioning -- 0005: application-plane durable
-- audit sink (phase 4)
--
-- WHO RUNS THIS: the operator, connected to the `mitatedb_platform`
-- database (created by 0001) AS the `mitatedbsvc_provision` role -- the
-- same role/connection 0002 already runs as. Run once, after 0002 (0003/
-- 0004 are per-application provisioning scripts, unrelated to this file's
-- own schema-level scope):
--
--   psql "$MITATEDBSVC_PROVISION_DSN" -f 0005_application_audit.sql
--
-- After this file has run, an operator sets the new reader role's
-- password out of band (mirrors 0002's own `mitatedbsvc_api`/
-- `mitatedbsvc_controlplane` convention -- this file deliberately creates
-- `mitatedbsvc_auditreader` with `PASSWORD NULL`, never a real credential
-- written to this file):
--
--   ALTER ROLE mitatedbsvc_auditreader PASSWORD '<generated secret>';
--
-- See MitateDB-api/docs/cloud-run-cloud-sql.md for the environment
-- variable name (`MITATEDB_AUDIT_DSN`) this reader role's DSN is
-- eventually configured under -- that wiring is WP-3(b), not this file.
--
-- WHAT THIS FILE DOES (design docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md
-- D-1/D-3/D-4/D-9, work order docs/work-orders/
-- PHASE4_DURABLE_AUDIT_SINK_WORK_ORDER.md WP-3(a)): application-plane
-- events (fail-closed schema/destructive operations, coalesced denials,
-- buffer-overflow alerts, and -- P4-D5 -- ordinary query/insert/update
-- successes) have had nowhere durable to land: `mitatedb_api.audit.
-- AuditSink` is in-memory only, lost on every process restart, exactly
-- the gap 0002's own `control_audit` table already closed for the
-- control plane. This file closes the same gap for the application
-- plane:
--
--   1. (D-1/design §6.2) `application_audit` -- a durable, append-only
--      sink for application-plane audit events, shaped like
--      `control_audit` (0002) plus two new columns: `audit_seq` (an
--      insertion-order debugging aid local to this one table -- a future
--      `audit_query` surface's own total order, a WP-3(b) concern, is
--      `(recorded_at, plane, event_id)`, not this column) and `count`
--      ("this row represents `count` occurrences, NULL means 1" -- used
--      only by D-3's coalesced-denial summary rows and D-4's
--      buffer-overflow alert rows; every other row leaves it NULL).
--      `recorded_at DEFAULT clock_timestamp()`, deliberately NOT `now()`
--      (D-6: `now()` is transaction-start time, which would let a
--      long-held writer transaction's row be skipped by a future
--      `audit_query` cursor that has already moved past it --
--      `clock_timestamp()` is the actual INSERT-execution instant).
--      `event_id` is `text` (application-generated, `uuid.uuid4().hex` --
--      matching `control_audit.event_id`'s own `text` type, 0002; peer
--      symmetry with r2db-api's own `uuid` column type is NOT attempted
--      here -- this is a pre-existing, unrelated non-symmetry this WP does
--      not touch, design §6.2's own explicit note).
--   2. (D-1/§6.1 note 2, review M-5) length `CHECK` constraints on every
--      `text` column -- the first of three layers bounding the new attack
--      surface this file opens (`mitatedbsvc_api` gains INSERT on a
--      platform-DB table for the first time ever): 1 row's size is capped
--      here; 1 operation's row count is capped by application code (D-2:
--      at most one durable row per operation; D-3: coalescing bounds
--      denial-flood rows to at most 2 per process per 60s window; D-4: a
--      bounded in-memory buffer bounds ordinary-event rows); operational
--      monitoring of platform-DB capacity is the third layer (runbook,
--      WP-4).
--   3. (D-1/§6.2) `mitatedbsvc_api` (the existing, already-deployed
--      data-plane process role -- 0002) gets INSERT-only on this one new
--      table, plus USAGE on its sequence. No SELECT/UPDATE/DELETE: this
--      role can append evidence but never read, alter, or erase it back
--      out -- the identical append-only-by-grant posture 0002 already
--      established for `mitatedbsvc_controlplane` on `control_audit`.
--   4. (D-5/§6.2) `mitatedbsvc_auditreader` -- a brand-new, SELECT-only
--      login role, held only by the (still WP-3(b), not built by this
--      file) control-HTTP-surface's own `audit_query` reader -- never by
--      the data-plane process (`mitatedbsvc_api`) and never by the
--      control-plane process (`mitatedbsvc_controlplane`, 0002), which
--      receives NO grant on either audit table at all from this file.
--      This role can read `control_audit` AND `application_audit` (both
--      live in this one schema, D-1(b): a single DB connection is what
--      lets a future `audit_query` answer from both planes at once) but
--      can create nothing, alter nothing, and hold no other role's
--      membership -- enforced structurally by `CREATE ROLE ...
--      NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT`, and BACKSTOPPED
--      (Cloud SQL note below) by this file's own call to `mitatedb_
--      registry.assert_role_has_no_memberships` (0002), the SAME
--      fail-closed check 0002's own `begin_provision_application` already
--      applies to every per-application role.
--
-- CLOUD SQL NOTE (design §6.2 "Cloud SQL 固有の注意"): the new reader
-- role MUST be created by this file's own `CREATE ROLE` statement below,
-- never via the Cloud SQL Users API/Console -- a role created through
-- that path becomes a member of Cloud SQL's own `cloudsqlsuperuser`
-- role, which silently defeats `REVOKE ALL ... FROM PUBLIC`-based
-- containment (0002's own identical warning for `mitatedbsvc_api`/
-- `mitatedbsvc_controlplane`, restated here because this file introduces
-- a THIRD role subject to the same risk). This file's own closing
-- `assert_role_has_no_memberships` call is the fail-closed backstop: if
-- an operator ever DOES create `mitatedbsvc_auditreader` through the
-- Cloud SQL Console before running this file, the idempotent `CREATE
-- ROLE ... IF NOT EXISTS` guard below silently no-ops (leaving the
-- Console-created, `cloudsqlsuperuser`-tainted role in place) and this
-- assertion then aborts the whole migration with a loud `RAISE
-- EXCEPTION`, rather than silently granting SELECT on two audit tables
-- to a role that can already read (or worse) everything else in the
-- cluster.
--
-- IDEMPOTENCY: `CREATE TABLE IF NOT EXISTS` is natively idempotent. The
-- `CREATE ROLE` below uses the same conditional `pg_roles` existence
-- check 0002's own two `CREATE ROLE` statements already use. `GRANT` is
-- naturally idempotent. Re-running this file after it has already
-- succeeded is a no-op (the closing `assert_role_has_no_memberships`
-- call re-verifies the SAME two conditions every time, harmlessly, since
-- nothing in a successful prior run of this file could have changed
-- either).
--
-- COMPATIBILITY WITH THE ALREADY-DEPLOYED MitateDB-api INSTANCE (D-9;
-- this peer's own "no deployed instance" premise expired 2026-09-01,
-- first real Cloud SQL/Cloud Run deployment, commit `51d9c1e`'s sibling
-- for this peer -- see `docs/cloud-run-cloud-sql.md`), verified as a
-- logged, per-object confirmation rather than the bare assertion "additive
-- only":
--   * `mitatedb_registry.applications`, `.credentials`, `.control_
--     credentials`, `.control_audit` -- NONE of these four existing
--     tables is named in any `ALTER`/`DROP`/`REVOKE` statement anywhere
--     in this file. This file's only `CREATE TABLE` names a table
--     (`application_audit`) that does not exist in any of 0001-0004.
--   * `mitatedbsvc_api`'s existing GRANTs (0002: `SELECT` on
--     `applications`/`credentials`, `CONNECT` on `mitatedb_platform`,
--     `USAGE` on `mitatedb_registry`) are untouched -- this file only
--     ADDS `INSERT` on the new `application_audit` table plus `USAGE` on
--     its own new sequence, naming no other privilege on any other
--     object.
--   * `mitatedbsvc_controlplane`'s existing GRANTs (0002: `SELECT`/
--     `INSERT`/`UPDATE` on `applications`/`credentials`/`control_
--     credentials`, `INSERT` + sequence `USAGE` on `control_audit`) are
--     untouched by this file -- this file grants `mitatedbsvc_
--     controlplane` NOTHING at all on the new table (D-5: the control
--     HTTP process's future `audit_query` reader is the SEPARATE
--     `mitatedbsvc_auditreader` role/DSN, never the control-plane
--     process's own connection).
--   * `control_audit`'s own existing GRANTs (0002 lines 266/271:
--     `INSERT` to `mitatedbsvc_controlplane`, sequence `USAGE` to the
--     same role) are untouched by this file; this file only ADDS a
--     third grantee's `SELECT` (`mitatedbsvc_auditreader`) alongside
--     them below, never removing or narrowing either existing grant.
--   * `mitatedb_registry.assert_role_has_no_memberships` (0002) is
--     `CREATE OR REPLACE FUNCTION`d there, not redefined here -- this
--     file only CALLS it (a read-only verification, `SELECT ...`),
--     naming no `CREATE OR REPLACE`/`DROP FUNCTION` statement of its own.
--   * Idempotent (see above): re-running this file against an instance
--     that already has it applied is a no-op.
--   * Rollback: dropping the new table, its implicit sequence, and the
--     new role restores the prior state exactly; no data written by
--     0001-0004 depends on any of the three.

\set ON_ERROR_STOP on

-- ===========================================================================
-- 1.1: application_audit (D-1/design §6.2)
-- ===========================================================================

CREATE TABLE IF NOT EXISTS mitatedb_registry.application_audit (
    audit_seq      bigserial UNIQUE,
    event_id       text PRIMARY KEY,
    event_class    text NOT NULL,
    occurred_at    timestamptz NOT NULL,
    request_id     text,
    application_id text,
    actor_type     text,
    actor_id       text,
    role           text,
    operation      text NOT NULL,
    target_kind    text,
    outcome        text NOT NULL,
    reason_code    text,
    target_id      text,
    -- D-3/D-4: "this row represents `count` occurrences; NULL means 1" --
    -- set only on a D-3 coalesced-denial summary row or a D-4 buffer-
    -- overflow alert row; NULL on every other event. Not added to
    -- `control_audit` (0002): the control plane has neither coalescing
    -- nor a buffer, so the column would be permanently NULL there and
    -- would also disturb this peer's own 13-field exact-match tests for
    -- the (unrelated) control_audit shape.
    count          integer,
    -- D-6: `clock_timestamp()`, NOT `now()` (`now()` is transaction-start
    -- time -- a long-held writer transaction would let its own row be
    -- skipped by a future `audit_query` cursor already past that
    -- instant; see this file's header note 1 and design D-6 point 1).
    recorded_at    timestamptz NOT NULL DEFAULT clock_timestamp(),

    -- Review M-5: length CHECKs on every text column -- see this file's
    -- header note 2 for the three-layer capacity-bounding rationale
    -- these belong to. Values mirror r2db-api's own identical `0007_
    -- application_audit.sql` CHECKs one-for-one (an independently
    -- authored table of the same shape, not shared code) -- this table
    -- carries the identical 13 contract `audit.fields` columns, so the
    -- identical per-column bound applies.
    CONSTRAINT application_audit_len_event_class    CHECK (length(event_class)    <= 64),
    CONSTRAINT application_audit_len_request_id     CHECK (length(request_id)     <= 256),
    CONSTRAINT application_audit_len_application_id CHECK (length(application_id) <= 256),
    CONSTRAINT application_audit_len_actor_type     CHECK (length(actor_type)     <= 64),
    CONSTRAINT application_audit_len_actor_id       CHECK (length(actor_id)       <= 256),
    CONSTRAINT application_audit_len_role           CHECK (length(role)           <= 64),
    CONSTRAINT application_audit_len_operation      CHECK (length(operation)      <= 64),
    CONSTRAINT application_audit_len_target_kind    CHECK (length(target_kind)    <= 64),
    CONSTRAINT application_audit_len_outcome        CHECK (length(outcome)        <= 32),
    CONSTRAINT application_audit_len_reason_code    CHECK (length(reason_code)    <= 128),
    CONSTRAINT application_audit_len_target_id      CHECK (length(target_id)      <= 256),
    -- D-3/D-4: `count`, when set at all, is a positive occurrence count --
    -- never zero or negative (a row that represents zero occurrences has
    -- no reason to exist; a negative count is nonsensical). NULL (the
    -- "ordinary single event" case) always passes this CHECK.
    CONSTRAINT application_audit_count_positive     CHECK (count IS NULL OR count > 0)
);

REVOKE ALL ON mitatedb_registry.application_audit FROM PUBLIC;

-- ===========================================================================
-- 1.2: mitatedbsvc_api -- INSERT-only on application_audit (D-1/§6.2 note 3)
-- ===========================================================================

-- Append-only by grant, from the process role that is already the sole
-- data-plane writer: it can add evidence but can never read, alter, or
-- erase it back out. `mitatedbsvc_api` keeps every pre-existing grant
-- (0002's SELECT on `applications`/`credentials`) untouched -- this is
-- additive.
GRANT INSERT ON mitatedb_registry.application_audit TO mitatedbsvc_api;

-- `audit_seq bigserial`'s own implicit sequence needs an explicit
-- `USAGE` grant separate from the table's own `INSERT` grant --
-- PostgreSQL does not fold "may call nextval() for this column's
-- identity sequence" into a plain table-level `INSERT` grant for a
-- non-owner role (mirrors 0002 line 271's identical grant for
-- `control_audit`'s own sequence).
GRANT USAGE ON SEQUENCE mitatedb_registry.application_audit_audit_seq_seq TO mitatedbsvc_api;

-- ===========================================================================
-- 1.3: role mitatedbsvc_auditreader + GRANTs (D-5/§6.2 note 4)
-- ===========================================================================

-- Process-role creation (mirrors 0002's own two `CREATE ROLE ... LOGIN
-- PASSWORD NULL ...` statements one-for-one): a login role per SURFACE
-- (the future `audit_query` reader), never per request, and never
-- carrying provisioning authority.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mitatedbsvc_auditreader') THEN
        CREATE ROLE mitatedbsvc_auditreader LOGIN PASSWORD NULL
            NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT CONNECTION LIMIT 5;
    END IF;
END
$$;

-- `CREATE ROLE ... LOGIN PASSWORD NULL` above deliberately creates a role
-- with NO usable password -- a real operator sets one with `ALTER ROLE
-- ... PASSWORD '<secret>'` immediately after, out of band, exactly as
-- 0002's own header documents for `mitatedbsvc_api`/`mitatedbsvc_
-- controlplane`. Never written to this repository.

GRANT CONNECT ON DATABASE mitatedb_platform TO mitatedbsvc_auditreader;
GRANT USAGE ON SCHEMA mitatedb_registry TO mitatedbsvc_auditreader;

-- D-5(b): reads BOTH planes over one DB connection -- `control_audit`'s
-- own existing GRANTs (0002: INSERT-only to `mitatedbsvc_controlplane`)
-- are untouched by this ADD; this is a third grantee's SELECT alongside
-- them, not a replacement.
GRANT SELECT ON mitatedb_registry.control_audit     TO mitatedbsvc_auditreader;
GRANT SELECT ON mitatedb_registry.application_audit TO mitatedbsvc_auditreader;

-- `mitatedbsvc_auditreader` never receives INSERT/UPDATE/DELETE on
-- either audit table, never receives any GRANT on `applications`/
-- `credentials`/`control_credentials` at all, and never receives
-- `CREATEDB`/`CREATEROLE`/`SUPERUSER` (it is granted no role attribute
-- beyond its own `CREATE ROLE ... LOGIN` statement above, which grants
-- none of those). A compromised `audit_query` reader connection can only
-- ever SELECT `control_audit`/`application_audit` -- it cannot write
-- anywhere, read credential state, or escalate through a role/sequence/
-- function grant that does not exist for it.

-- Fail-closed backstop (Cloud SQL note above, D-9): the SAME containment
-- assertion 0002's own `begin_provision_application` already applies to
-- every per-application runtime/developer role, applied here to this
-- new platform-level role too -- aborts the whole migration (`RAISE
-- EXCEPTION`) if `mitatedbsvc_auditreader` is not EXACTLY what the
-- `CREATE ROLE` statement above would have produced (no memberships, no
-- SUPERUSER/CREATEDB/CREATEROLE, LOGIN-capable) -- e.g. if an operator
-- pre-created it via the Cloud SQL Console (which would silently make it
-- a `cloudsqlsuperuser` member).
SELECT mitatedb_registry.assert_role_has_no_memberships('mitatedbsvc_auditreader');
