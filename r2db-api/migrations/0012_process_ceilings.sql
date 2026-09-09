-- r2db-api PostgreSQL provisioning -- 0012: widen platform_declarations.key
-- to admit 'process_ceilings' (Phase 10 phase, design docs/design/
-- PHASE10_DEPLOYMENT_EVIDENCE_V1.md D-5(ii), work order
-- docs/work-orders/WORK_ORDER_PHASE10_DEPLOYMENT_EVIDENCE_V1.md WP-6a; same
-- mechanism as Q4 D-2, docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md D-2(a))
--
-- WHO RUNS THIS: the operator, connected to the `r2dbsvc_platform` database
-- AS the `r2dbsvc_control` role -- the same role/connection 0002/0005/0006/
-- 0007/0008 already run as. Run once, after 0008 (order relative to
-- 0009/0010/0011 does not matter -- this is a platform single-shot
-- migration, those are per-application upgrade scripts, design SS8.1 rule
-- 2):
--
--   psql "$R2DBSVC_CONTROL_DSN" -v ON_ERROR_STOP=1 -f 0012_process_ceilings.sql
--
-- `-v ON_ERROR_STOP=1` must be passed on every `-f` invocation -- without
-- it, psql exits 0 even when a statement in this file errors out.
--
-- WHAT THIS FILE DOES (design D-5(ii); this is a PLATFORM SINGLE-SHOT
-- migration, not a per-application upgrade script -- it never touches an
-- application database, and its own filename deliberately does NOT end in
-- `_upgrade.sql`, so the Q4 WP-0 static per-application-upgrade-script
-- scanner never treats this file as one):
--
--   1. Widens `platform_declarations_key_check` (0008) to admit the new
--      key `process_ceilings` -- the deployer's own declaration of the
--      maximum number of processes that may serve each plane's declared
--      `surfaces` base URL at the same time (contract 1.8.0's enforcement-
--      scope definition; `{"data": <int >= 1>, "control": <int >= 1>}`).
--      This constraint has a NAME (`platform_declarations_key_check`,
--      0008's own comment: "because a future migration that adds a fourth
--      key must DROP CONSTRAINT/ADD CONSTRAINT by name, and out-of-place
--      edits to an already-shipped migration are forbidden") -- this file
--      is exactly that future migration, adding a FIFTH key.
--
--      Like every other key this table has ever admitted, `value`'s own
--      well-formedness is deliberately NOT a second `CHECK` here -- design
--      D-5(ii)/Q4 D-2(a)/(d) keeps that validation in ONE place, Python
--      (`r2db_api.platform_declarations.validate_process_ceilings_value`),
--      exercised on both the write path (`ops declare-process-ceilings`)
--      and the read path (both composition roots' own startup).
--
--   2. Seeds NOTHING -- `process_ceilings`, like `surfaces` (0008's own
--      comment: "surfaces is deployment-specific and deliberately NOT
--      seeded"), is deployment-specific: a deployment applying this
--      migration for the first time must run `ops declare-process-
--      ceilings --data <N> --control <N>` next, before either process
--      will start (the row's own absence is fail-fast, F-15).
--
-- IDEMPOTENCY: `ALTER TABLE ... DROP CONSTRAINT IF EXISTS ... ADD
-- CONSTRAINT` re-applies to the same terminal state every time (the
-- `CHECK`'s own admitted-key list is fixed text, not derived from any
-- variable this file takes -- it takes none).
--
-- COMPATIBILITY WITH THE ALREADY-DEPLOYED r2db-api INSTANCE: ADDITIVE
-- ONLY. This file widens one existing `CHECK` constraint (strictly
-- admitting one more value than before -- every row this constraint
-- already accepted, it still accepts); it ALTERs no other table, DROPs no
-- table, and REVOKEs nothing.

\set ON_ERROR_STOP on

BEGIN;

-- ===========================================================================
-- 1: widen platform_declarations.key (design D-5(ii))
-- ===========================================================================

ALTER TABLE r2dbsvc_registry.platform_declarations
    DROP CONSTRAINT IF EXISTS platform_declarations_key_check;

ALTER TABLE r2dbsvc_registry.platform_declarations
    ADD CONSTRAINT platform_declarations_key_check
    CHECK (key IN ('surfaces', 'audit_coalescing_window_ms', 'audit_writer_roles', 'process_ceilings'));

COMMIT;
