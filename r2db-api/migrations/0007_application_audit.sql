-- r2db-api PostgreSQL provisioning -- 0007: application-plane durable audit
-- sink (phase 4)
--
-- WHO RUNS THIS: the operator, connected to the `r2dbsvc_platform` database
-- (created by 0001) AS the `r2dbsvc_control` role -- the same role/connection
-- 0002/0005/0006 already run as. Run once, after 0006:
--
--   psql "$R2DBSVC_CONTROL_DSN" -v auditreader_password="$R2DBSVC_AUDITREADER_PASSWORD" \
--     -f 0007_application_audit.sql
--
-- `R2DBSVC_AUDITREADER_PASSWORD` is an environment-variable *name*; see
-- r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md. This file never contains a
-- real credential.
--
-- WHAT THIS FILE DOES (design docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md
-- D-1/D-3/D-4/D-9, work order docs/work-orders/
-- PHASE4_DURABLE_AUDIT_SINK_WORK_ORDER.md WP-2(a)): application-plane
-- events (fail-closed operations, coalesced denials, buffer-overflow
-- alerts) have had nowhere durable to land -- `r2db_api.audit.AuditSink` is
-- in-memory only, lost on every process restart, exactly the gap 0006's
-- `control_audit` already closed for the control plane. This file closes
-- the same gap for the application plane:
--
--   1. (D-1/§6.1) `application_audit` -- a durable, append-only sink for
--      application-plane audit events, shaped like `control_audit` (0006)
--      plus two new columns: `audit_seq` (an insertion-order debugging aid
--      local to this one table; `audit_query`'s own total order, a WP-2(b)
--      concern, is `(recorded_at, plane, event_id)`, not this column) and
--      `count` ("this row represents `count` occurrences, NULL means 1" --
--      used only by D-3's coalesced-denial summary rows and D-4's
--      buffer-overflow alert rows; every other row leaves it NULL).
--      `recorded_at DEFAULT clock_timestamp()`, deliberately NOT `now()`
--      (D-6: `now()` is transaction-start time, which would let a
--      long-held writer transaction's row be skipped by an `audit_query`
--      cursor that has already moved past it -- `clock_timestamp()` is the
--      actual INSERT-execution instant).
--   2. (D-1/§6.1, review M-5) length `CHECK` constraints on every `text`
--      column -- the first of three layers bounding the new attack surface
--      this file opens (`r2dbsvc_api` gains INSERT on a platform-DB table
--      for the first time ever): 1 row's size is capped here; 1 operation's
--      row count is capped by application code (D-2: at most one durable
--      row per operation; D-3: coalescing bounds denial-flood rows to one
--      per process per 60s window; D-4: a bounded in-memory buffer bounds
--      ordinary-event rows); operational monitoring of platform-DB capacity
--      is the third layer (runbook, WP-4).
--   3. (D-1/§6.1) `r2dbsvc_api` (the existing, already-deployed data-plane
--      process role -- 0005) gets INSERT-only on this one new table, plus
--      USAGE on its sequence. No SELECT/UPDATE/DELETE: this role can append
--      evidence but never read, alter, or erase it back out -- the
--      identical append-only-by-grant posture 0006 already established for
--      `r2dbsvc_controlplane` on `control_audit`.
--   4. (D-1/§6.1) `r2dbsvc_control` (the out-of-band ritual/CLI role, and
--      this schema's owner) gets an *explicit* INSERT grant here too, for
--      the same reason 0006's header documents for its own identical grant
--      on `control_audit`: a future bootstrap/reset/break-glass CLI command
--      that writes a canonical application-plane audit row must not rely on
--      implicit owner privilege.
--   5. (D-5/§6.1) `r2dbsvc_auditreader` -- a brand-new, SELECT-only login
--      role, held only by the (still WP-2(b), not built by this file)
--      control-HTTP-surface's `audit_query` reader -- never by the
--      data-plane process (`r2dbsvc_api`) and never by the control-plane
--      process (`r2dbsvc_controlplane`, 0006), which receives NO grant on
--      either audit table at all. This role can read `control_audit` AND
--      `application_audit` (both live in this one schema, D-1(b): a single
--      DB connection is what lets `audit_query` answer from both planes at
--      once) but can create nothing, alter nothing, and hold no other
--      role's membership (`assert_role_has_no_memberships`-equivalent
--      discipline; this peer's provisioning has no such helper function
--      yet -- LOGIN/NOSUPERUSER/NOCREATEDB/NOCREATEROLE/NOINHERIT already
--      rule out the escalation paths that function exists to backstop for
--      MitateDB's Cloud-SQL-Console risk, which does not apply here: every
--      role in this file is created by this SQL, never by an external
--      console).
--
-- IDEMPOTENCY: `CREATE TABLE IF NOT EXISTS` is natively idempotent. `CREATE
-- ROLE` uses the same conditional-`\gexec` idiom 0001/0005/0006 already
-- established. `GRANT` is naturally idempotent. Re-running this file after
-- it has already succeeded is a no-op.
--
-- COMPATIBILITY WITH THE ALREADY-DEPLOYED r2db-api INSTANCE (D-9; this
-- peer's "no deployed instance" premise expired 2026-09-01, first real
-- Cloud SQL/Cloud Run deployment, commit `51d9c1e`):
--   * ADDITIVE ONLY. This file creates one new table (`application_audit`),
--     one new sequence (`application_audit_audit_seq_seq`, implicit from
--     the table's own `bigserial` column), one new role
--     (`r2dbsvc_auditreader`), and new GRANTs naming only these new
--     objects. It ALTERs no existing table (`applications`/`credentials`/
--     `control_credentials`/`control_audit` are none of them touched), DROPs
--     nothing, and REVOKEs nothing.
--   * No existing GRANT changes, named explicitly: `r2dbsvc_api`'s existing
--     SELECT on `applications`/`credentials` (0005) is untouched, and this
--     file adds INSERT on `application_audit` only -- no other privilege on
--     any other table. `r2dbsvc_controlplane`'s six privileges (0006 §1.4)
--     are untouched; this file grants it nothing at all (D-5: the control
--     HTTP process reads audit evidence over the SEPARATE `r2dbsvc_
--     auditreader` DSN, never its own `r2dbsvc_controlplane` connection).
--     `control_audit`'s own existing GRANTs (INSERT-only to
--     `r2dbsvc_controlplane`/`r2dbsvc_control`, 0006 §1.4) are untouched;
--     this file only ADDS a third grantee's SELECT (`r2dbsvc_auditreader`)
--     alongside them, never removing or narrowing either existing grant.
--   * Idempotent (see above): re-running this file against an instance that
--     already has it applied is a no-op.
--   * Rollback: dropping the new table, its implicit sequence, and the new
--     role restores the prior state exactly; no data written by earlier
--     migrations depends on any of the three.

\set ON_ERROR_STOP on

-- ===========================================================================
-- 1.1: application_audit (D-1/§6.1)
-- ===========================================================================

CREATE TABLE IF NOT EXISTS r2dbsvc_registry.application_audit (
    audit_seq      bigserial UNIQUE,
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
    target_id      text,
    -- D-3/D-4: "this row represents `count` occurrences; NULL means 1" --
    -- set only on a D-3 coalesced-denial summary row or a D-4 buffer-
    -- overflow alert row; NULL on every other event. Not added to
    -- `control_audit` (0006): the control plane has neither coalescing
    -- nor a buffer, so the column would be permanently NULL there and
    -- would also disturb MitateDB's 13-field exact-match tests for the
    -- (unrelated) control_audit shape.
    count          integer,
    -- D-6: `clock_timestamp()`, NOT `now()` (`now()` is transaction-start
    -- time -- a long-held writer transaction would let its own row be
    -- skipped by an `audit_query` cursor already past that instant; see
    -- this file's header note 1 and design D-6 point 1).
    recorded_at    timestamptz NOT NULL DEFAULT clock_timestamp(),

    -- Review M-5: length CHECKs on every text column -- see this file's
    -- header note 2 for the three-layer capacity-bounding rationale these
    -- belong to. Values mirror 0006's `control_audit` CHECKs one-for-one
    -- (`event_class`/`request_id`/`application_id`/`actor_type`/`actor_id`/
    -- `role`/`operation`/`target_kind`/`outcome`/`reason_code`/`target_id`)
    -- -- this table carries the identical 13 contract `audit.fields`
    -- columns, so the identical per-column bound applies.
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
-- Same closed-by-default reasoning 0006's `control_audit`/`control_
-- credentials` already document -- no explicit `REVOKE ... FROM PUBLIC`
-- needed for a newly created table nothing has ever granted `PUBLIC`
-- anything on, in this schema.

-- ===========================================================================
-- 1.2: r2dbsvc_api -- INSERT-only on application_audit (D-1/§6.1 note 3)
-- ===========================================================================

-- Append-only by grant, from the process role that is already the sole
-- data-plane writer: it can add evidence but can never read, alter, or
-- erase it back out. `r2dbsvc_api` keeps every pre-existing grant (0005's
-- SELECT on `applications`/`credentials`) untouched -- this is additive.
GRANT INSERT ON r2dbsvc_registry.application_audit TO r2dbsvc_api;
GRANT USAGE ON SEQUENCE r2dbsvc_registry.application_audit_audit_seq_seq TO r2dbsvc_api;

-- Note 4: explicit INSERT for the out-of-band CLI role too, for the exact
-- reason 0006 §1.4's `control_audit` grant to `r2dbsvc_control` documents
-- -- a future bootstrap/reset/break-glass command that writes a canonical
-- application-plane audit row must not rely on implicit schema-owner
-- privilege.
GRANT INSERT ON r2dbsvc_registry.application_audit TO r2dbsvc_control;

-- ===========================================================================
-- 1.3: role r2dbsvc_auditreader + GRANTs (D-5/§6.1 note 5)
-- ===========================================================================

SELECT format(
    'CREATE ROLE r2dbsvc_auditreader LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT CONNECTION LIMIT 5',
    :'auditreader_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'r2dbsvc_auditreader')
\gexec

GRANT CONNECT ON DATABASE r2dbsvc_platform TO r2dbsvc_auditreader;
GRANT USAGE ON SCHEMA r2dbsvc_registry TO r2dbsvc_auditreader;

-- D-5(b): reads BOTH planes over one DB connection -- `control_audit`'s own
-- existing GRANTs (0006 §1.4: INSERT-only to `r2dbsvc_controlplane`/
-- `r2dbsvc_control`) are untouched by this ADD; this is a third grantee's
-- SELECT alongside them, not a replacement.
GRANT SELECT ON r2dbsvc_registry.control_audit      TO r2dbsvc_auditreader;
GRANT SELECT ON r2dbsvc_registry.application_audit  TO r2dbsvc_auditreader;

-- Note 5 (reviewer confirmation item, not a statement this file needs to
-- make in SQL beyond the role-attribute list above): `r2dbsvc_auditreader`
-- never receives INSERT/UPDATE/DELETE on either audit table, never
-- receives any GRANT on `applications`/`credentials`/`control_credentials`
-- at all, and never receives `CREATEDB`/`CREATEROLE`/`SUPERUSER` (it is
-- granted no role attribute beyond its own `CREATE ROLE ... LOGIN`
-- statement above, which grants none of those). A compromised `audit_query`
-- reader connection can only ever SELECT `control_audit`/`application_
-- audit` -- it cannot write anywhere, read credential state, or escalate
-- through a role/sequence/function grant that does not exist for it.
