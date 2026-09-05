-- MitateDB-api PostgreSQL provisioning -- 0007: platform declarations +
-- writer-role timeouts + audit_writer_roles (Q4 phase, design docs/design/
-- Q4_DB_SIDE_SINGLE_TRUTH_V1.md v1.3 D-1/D-2/D-2(h))
--
-- WHO RUNS THIS: the operator, connected to `mitatedb_platform` AS the
-- `mitatedbsvc_provision` role -- the SAME connection shape 0002 already
-- documents. `mitatedb_registry` must already exist as the owning schema
-- (0002). This file's own `ALTER ROLE` targets are named by psql
-- VARIABLE, not hardcoded -- pass them with `-v` (existing style, 0001's
-- `-v provision_password=…` / 0004's `-v app_id=…`):
--
--   psql "$MITATEDB_PROVISION_DSN" \
--     -v api_role='mitatedbsvc_api' -v controlplane_role='mitatedbsvc_controlplane' \
--     -f 0007_platform_declarations.sql
--
-- (production deployments pass exactly those two literal values -- design
-- §3.10's own "本番の seed 値"; a test harness passes its own throwaway-
-- prefixed role names instead, D-2(h) 5: "逐語の本番 role 名をテストへ
-- 焼き付けない").
--
-- WHAT THIS FILE DOES:
--
--   (a) `ALTER ROLE :"api_role"/:"controlplane_role" SET …` (an
--       idempotent overwrite -- re-running this file twice ends at the
--       SAME `pg_db_role_setting` state) fixes the two audit-writer
--       timeouts as PostgreSQL role settings on both service writer
--       roles -- the single source `platform_declarations.py::read_
--       declared_role_timeouts`/`check_writer_role_timeouts`/`derive_
--       visibility_lag_ms` now read from, replacing this repository's
--       former per-connection `SET SESSION` (design D-1(b)). The shipped
--       default (5000ms/5000ms) matches the PRE-Q4 `SET SESSION` default
--       exactly (`application_audit.DEFAULT_AUDIT_STATEMENT_TIMEOUT_MS`/
--       `_IDLE_TIMEOUT_MS`) -- no behavior change at ship time. Change
--       with `python -m mitatedb_api.ops set-platform-timeouts
--       --statement-ms <N> --idle-ms <N>` (never by hand-editing role
--       settings -- that command is the one place both roles are changed
--       together, reading its OWN target roles from the `audit_writer_
--       roles` row this same file seeds below, design D-2(h) 4).
--
--   (b) `CREATE TABLE mitatedb_registry.platform_declarations` -- the
--       single source of `surfaces`, `audit_coalescing_window_ms`, AND
--       `audit_writer_roles` (design D-2/D-2(h)), replacing the
--       `MITATEDB_DATA_BASE_URL`/`MITATEDB_CONTROL_BASE_URL`/`MITATEDB_
--       AUDIT_STATEMENT_TIMEOUT_MS`/`MITATEDB_AUDIT_IDLE_TIMEOUT_MS` env
--       vars this same phase removes. `key` is closed by a NAMED check
--       constraint (`platform_declarations_key_check`) -- named because
--       a future migration that widens the key vocabulary must `DROP
--       CONSTRAINT / ADD CONSTRAINT` this exact name (0001-0006 are
--       shipped and never edited in place, design 制約 2). Value-level
--       validation (jsonb shape/range) is NOT a DB-level CHECK (monitor
--       ruling 2026-09-05) -- it is Python-side, in `platform_
--       declarations.validate_surfaces_value`/`validate_coalescing_
--       window_value`/`validate_audit_writer_roles_value`, the SAME
--       three functions both the write path (`ops declare-surfaces`/
--       `declare-coalescing-window`, and this migration itself for
--       `audit_writer_roles`) and the read path (both composition roots)
--       call, so a hand-edited row is validated identically to a
--       migration/`ops`-written one. `audit_coalescing_window_ms` is
--       seeded with the current shipped default (60000, `audit_query.
--       DEFAULT_COALESCING_WINDOW_MS`) -- `surfaces` is deployment-
--       specific and is deliberately NOT seeded (a real deployment
--       declares it with `python -m mitatedb_api.ops declare-surfaces
--       --data-base-url <URL> [--control-base-url <URL>]`; an
--       un-declared `surfaces` row fails startup loudly, design F-3,
--       rather than serving a wrong/absent default). `SELECT` only is
--       granted to the two service roles -- writes go through this
--       migration (`audit_writer_roles`) and `ops` (`surfaces`/`audit_
--       coalescing_window_ms`) only, as the table owner
--       (`mitatedbsvc_provision`).
--
--   (c) `audit_writer_roles` (design D-2(h) 1, monitor ruling
--       2026-09-05): seeded in the SAME transaction as (a)'s two `ALTER
--       ROLE` statements, from the SAME two psql variables -- so the
--       role names `ALTER ROLE` fixed timeouts on and the role names
--       `audit_writer_roles` declares as this deployment's audit writers
--       can never drift apart. `ON CONFLICT (key) DO UPDATE` (not `DO
--       NOTHING`) -- like (a)'s `ALTER ROLE … SET`, re-running this file
--       with the SAME two variables ends at the SAME row; re-running it
--       with DIFFERENT variables (an operator renaming a role, say)
--       updates the row to match, keeping this file the single place
--       both the role settings AND the role-name declaration change
--       together.
--
-- NAMING (design §8.1 point 2, WP-0's own static per-application-upgrade-
-- ledger scanner): this file's own name deliberately does NOT end in
-- `_upgrade.sql` -- it is a platform single-shot migration, not a
-- per-application upgrade script the scanner should walk.
--
-- CLOUD SQL 適合語彙 (R-1, mirrors 0001-0006): every statement below
-- (`ALTER ROLE ... SET`, `CREATE TABLE`, `REVOKE`/`GRANT`, `INSERT ...
-- ON CONFLICT`) is drawn from the same Cloud-SQL-compatible allowlist
-- 0001's own header documents -- no superuser-only feature is used here.

\set ON_ERROR_STOP on

BEGIN;

ALTER ROLE :"api_role"          SET statement_timeout                   = '5000ms';
ALTER ROLE :"api_role"          SET idle_in_transaction_session_timeout = '5000ms';
ALTER ROLE :"controlplane_role" SET statement_timeout                   = '5000ms';
ALTER ROLE :"controlplane_role" SET idle_in_transaction_session_timeout = '5000ms';

CREATE TABLE IF NOT EXISTS mitatedb_registry.platform_declarations (
    key        text PRIMARY KEY
               CONSTRAINT platform_declarations_key_check
               CHECK (key IN ('surfaces', 'audit_coalescing_window_ms', 'audit_writer_roles')),
    value      jsonb       NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
REVOKE ALL   ON mitatedb_registry.platform_declarations FROM PUBLIC;
GRANT SELECT ON mitatedb_registry.platform_declarations TO :"api_role";
GRANT SELECT ON mitatedb_registry.platform_declarations TO :"controlplane_role";

-- Deployment-specific `surfaces` is intentionally NOT seeded here -- see
-- this file's own header. Only the window's current shipped default is.
INSERT INTO mitatedb_registry.platform_declarations (key, value)
VALUES ('audit_coalescing_window_ms', to_jsonb(60000))
ON CONFLICT (key) DO NOTHING;

-- D-2(h) 1: the SAME two variables (a)'s `ALTER ROLE` statements above
-- used -- never a separately-typed literal.
INSERT INTO mitatedb_registry.platform_declarations (key, value)
VALUES ('audit_writer_roles', to_jsonb(ARRAY[:'api_role', :'controlplane_role']))
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now();

COMMIT;
