-- MitateDB-api PostgreSQL provisioning -- 0011: process_ceilings platform
-- declaration (Phase 10 WP-6b, design docs/design/
-- PHASE10_DEPLOYMENT_EVIDENCE_V1.md v1.x D-5 (ii)/(iii); mechanism mirrors
-- Q4 D-2, docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md)
--
-- WHO RUNS THIS: the operator, connected to `mitatedb_platform` AS the
-- `mitatedbsvc_provision` role -- the SAME connection shape 0001/0007
-- already document. `mitatedb_registry.platform_declarations` must
-- already exist (0007). No psql variables are required:
--
--   psql "$MITATEDB_PROVISION_DSN" -f MitateDB-api/migrations/0011_process_ceilings.sql
--
-- WHAT THIS FILE DOES:
--
--   Widens `platform_declarations.key`'s own CHECK constraint
--   (`platform_declarations_key_check`, 0007) to also accept the literal
--   `'process_ceilings'` -- the deployer's own declaration of how many
--   processes may serve each plane's (`data`/`control`) base URL at the
--   same time (design D-5 (ii): `{"data": <int >= 1>, "control": <int >=
--   1>}`, the SAME shape `surfaces` already uses -- U-5: "新しい形を発明
--   しない"). 0007's own constraint is a NAMED constraint specifically so
--   a LATER migration widening the key vocabulary (this file) can `DROP
--   CONSTRAINT`/`ADD CONSTRAINT` it by that exact name, rather than
--   depending on a processsor-generated name (0007's own header, design
--   制約 1: shipped migrations are never edited in place).
--
--   This file does NOT seed a `process_ceilings` row -- like `surfaces`
--   (0007's own header: "deployment-specific and is deliberately NOT
--   seeded"), the number of processes a deployment runs is a deployment-
--   specific fact the operator declares with `python -m mitatedb_api.ops
--   declare-process-ceilings --data <N> --control <N>` after applying
--   this migration. An un-declared `process_ceilings` row fails startup
--   loudly (F-15), rather than serving a wrong/absent default.
--
--   No value-level `CHECK` is added for the `process_ceilings` VALUE
--   itself (only the `key` vocabulary is widened here) -- value
--   validation is Python-side, in `platform_declarations.
--   validate_process_ceilings_value`, the SAME function both the write
--   path (`ops declare-process-ceilings`) and the read path (both
--   composition roots) call (Q4 D-2(d)'s own regularity, applied to this
--   new key).
--
-- NAMING (design §8.1 point 2 / Q4 D-3 (d), WP-0's own static per-
-- application-upgrade-ledger scanner): this file's own name deliberately
-- does NOT end in `_upgrade.sql` -- it is a platform single-shot
-- migration (widens a platform-wide CHECK constraint once), not a per-
-- application upgrade script the scanner should walk.
--
-- CLOUD SQL 適合語彙 (R-1, mirrors 0001-0007): `ALTER TABLE ... DROP
-- CONSTRAINT` / `ALTER TABLE ... ADD CONSTRAINT ... CHECK (...)` are both
-- drawn from the same Cloud-SQL-compatible allowlist 0001's own header
-- documents -- no superuser-only feature is used here.

\set ON_ERROR_STOP on

BEGIN;

ALTER TABLE mitatedb_registry.platform_declarations
    DROP CONSTRAINT platform_declarations_key_check;

ALTER TABLE mitatedb_registry.platform_declarations
    ADD CONSTRAINT platform_declarations_key_check
    CHECK (key IN ('surfaces', 'audit_coalescing_window_ms', 'audit_writer_roles', 'process_ceilings'));

COMMIT;
