-- r2db-api PostgreSQL provisioning -- 0008: platform declarations table +
-- audit writer role timeouts + audit_writer_roles declaration (Q4 phase,
-- design docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md D-1/D-2, work order
-- docs/work-orders/WORK_ORDER_Q4_DB_SIDE_SINGLE_TRUTH_V1.md WP-1; rework
-- round, supervisor ruling 2026-09-05 -- rulings-q4-writer-roles.md D-2(h))
--
-- WHO RUNS THIS: the operator, connected to the `r2dbsvc_platform` database
-- (created by 0001) AS the `r2dbsvc_control` role -- the same role/connection
-- 0002/0005/0006/0007 already run as. Run once, after 0007:
--
--   psql "$R2DBSVC_CONTROL_DSN" -v ON_ERROR_STOP=1 -f 0008_platform_declarations_and_writer_timeouts.sql \
--        -v api_role=r2dbsvc_api -v controlplane_role=r2dbsvc_controlplane
--
-- `-v ON_ERROR_STOP=1` (WP-4 rework round 2, supervisor ruling 2026-09-06,
-- wp4-rework-2.md #2) must be passed on every `-f` invocation -- without
-- it, psql exits 0 even when a statement in this file errors out.
--
-- `-v api_role=...`/`-v controlplane_role=...` (rework round, D-2(h) point
-- 1: "migration は psql 変数で role 名を受ける既存様式に従う", the SAME
-- style 0001's own `:'control_password'`/0004's own `-v app_slug=...` /
-- `-v app_id=...` already use) name the two service writer roles this file
-- both (a) issues `ALTER ROLE ... SET` for and (b) seeds into the new
-- `audit_writer_roles` declaration row -- from the SAME two variables, in
-- the SAME transaction, so the ALTER ROLE targets and the seeded row can
-- never independently drift (D-2(h) point 1: "ALTER ROLE と seed は同じ
-- migration の同じトランザクション内").
--
-- WHAT THIS FILE DOES (design D-1/D-2; this is a PLATFORM SINGLE-SHOT
-- migration, not a per-application upgrade script -- it never touches an
-- application database, and its own filename deliberately does NOT end in
-- `_upgrade.sql`, design SS8.1 rule 2, so the Q4 WP-0 static per-application-
-- upgrade-script scanner never treats this file as one):
--
--   1. (D-1(a)) `ALTER ROLE ... SET` -- fixes `statement_timeout`/
--      `idle_in_transaction_session_timeout` for the two SERVICE writer
--      roles named by `:api_role`/`:controlplane_role` (production:
--      `r2dbsvc_api`, the `application_audit` writer; `r2dbsvc_
--      controlplane`, the `control_audit` writer) as PostgreSQL role
--      settings -- the single source of truth this phase moves the
--      `visibility_lag_ms` declaration onto. Both processes stop issuing a
--      per-connection SESSION `SET` for these two settings; each writer
--      process instead double-checks, at startup, that its own login role's
--      actual effective value agrees with what this migration declared
--      (design D-1(b), `r2db_api.platform_declarations.check_writer_role_
--      timeouts`, called synchronously from `r2db_api.main.build_app`/
--      `r2db_api.control_main.build_control_app`). The chosen default,
--      `5000ms`/`5000ms`, is IDENTICAL to the two SESSION-level defaults
--      this phase replaces -- shipping this migration changes NO
--      observable behavior for an already-running deployment (design WP-1
--      "出荷時に挙動は変わらない").
--
--      NOTE (design SS3.11 point 1): `ALTER ROLE ... SET` bounds the named
--      role's ENTIRE connection lifetime, not only the connection this
--      phase cares about -- `r2dbsvc_api` is also the credential-store read
--      role (0005), and `r2dbsvc_controlplane` is also the control-plane
--      registry read/write role (0006). 5000ms is generous for the short,
--      indexed statements either role issues elsewhere in this schema.
--
--   2. (D-2(a)) `platform_declarations` -- a new table, the single source of
--      truth for `surfaces`, `audit_coalescing_window_ms`, and (D-2(h))
--      `audit_writer_roles`. `key` is closed by a NAMED `CHECK`
--      (`platform_declarations_key_check` -- named, not left to a generated
--      name, because a future migration that adds a fourth key must `DROP
--      CONSTRAINT`/`ADD CONSTRAINT` by name, and out-of-place edits to an
--      already-shipped migration are forbidden, work order SS7 rule 2).
--      `value`'s own well-formedness is deliberately NOT a second `CHECK`
--      here -- design D-2(a)/(d) puts that validation in ONE place, Python
--      (`r2db_api.platform_declarations.validate_surfaces_value`/
--      `validate_coalescing_window_value`/`validate_audit_writer_roles_
--      value`), exercised on both the write path (`ops declare-surfaces`/
--      `ops declare-coalescing-window`) and the read path (both
--      composition roots' own startup).
--
--      Only `audit_coalescing_window_ms` and `audit_writer_roles` are
--      seeded here (`surfaces` is deployment-specific and deliberately NOT
--      seeded, design D-2(c)). `audit_coalescing_window_ms` seeds at the
--      SAME value (`60000`) `r2db_api.audit_query.DECLARED_COALESCING_
--      WINDOW_MS` already ships as a Python constant -- behavior-preserving.
--      `audit_writer_roles` seeds `[:api_role, :controlplane_role]` -- the
--      SAME two role names the `ALTER ROLE` statements above just targeted
--      (D-2(h) point 1) -- via `ON CONFLICT (key) DO UPDATE`, not `DO
--      NOTHING`: unlike `audit_coalescing_window_ms` (a value an operator
--      may deliberately change later via `ops declare-coalescing-window`,
--      which this migration must never clobber on a second apply),
--      `audit_writer_roles` has no other writer at all -- ops issues no
--      `declare-audit-writer-roles` subcommand (design D-2(h) point 4: "ops
--      に書き込みサブコマンドを設けない") -- so re-applying this SAME
--      migration with the SAME variables is the only way this row ever
--      changes, and it must always re-converge to whatever `:api_role`/
--      `:controlplane_role` say (idempotent re-apply, condition 19).
--
--   3. GRANTs -- `platform_declarations` is `REVOKE ALL ... FROM PUBLIC`
--      (closed-by-default, matching every other table this schema has ever
--      created) with `SELECT` granted to exactly the two platform roles
--      that read it at startup (`:api_role`, `:controlplane_role`). Writes
--      happen ONLY through `ops declare-surfaces`/`ops declare-coalescing-
--      window`, connected as the schema owner (`r2dbsvc_control`, the
--      provision role that runs this very file) -- no other role is ever
--      granted INSERT/UPDATE/DELETE on this table.
--
-- IDEMPOTENCY: `ALTER ROLE ... SET` is an assignment, not an increment --
-- re-running it leaves the same terminal value (design D-1(a) "上書き代入
-- であり、再実行しても同じ終状態になる"). `CREATE TABLE IF NOT EXISTS`, the
-- window seed's `ON CONFLICT (key) DO NOTHING`, and the `audit_writer_
-- roles` seed's `ON CONFLICT (key) DO UPDATE` are all natively idempotent
-- (re-applying this file with the SAME `-v` values leaves an identical
-- terminal state; `GRANT`/`REVOKE` are naturally idempotent too). Wrapped
-- in one transaction (`BEGIN`/`COMMIT`) so the `ALTER ROLE` statements and
-- the `audit_writer_roles` seed either all apply or none do -- D-2(h)
-- point 1's "同じトランザクション内" requirement.
--
-- COMPATIBILITY WITH THE ALREADY-DEPLOYED r2db-api INSTANCE: ADDITIVE ONLY.
-- This file creates one new table (`platform_declarations`) and changes
-- role-level session defaults for two already-existing roles; it ALTERs no
-- existing table, DROPs nothing, and REVOKEs no existing GRANT from any
-- role other than the brand-new table's own default (`PUBLIC`, which never
-- held anything on a table that did not exist a moment before).

\set ON_ERROR_STOP on

BEGIN;

-- ===========================================================================
-- 1: writer role timeouts (D-1(a))
-- ===========================================================================

ALTER ROLE :"api_role"          SET statement_timeout                   = '5000ms';
ALTER ROLE :"api_role"          SET idle_in_transaction_session_timeout = '5000ms';
ALTER ROLE :"controlplane_role" SET statement_timeout                   = '5000ms';
ALTER ROLE :"controlplane_role" SET idle_in_transaction_session_timeout = '5000ms';

-- ===========================================================================
-- 2: platform_declarations (D-2(a), D-2(h))
-- ===========================================================================

CREATE TABLE IF NOT EXISTS r2dbsvc_registry.platform_declarations (
    key        text PRIMARY KEY
               CONSTRAINT platform_declarations_key_check
               CHECK (key IN ('surfaces', 'audit_coalescing_window_ms', 'audit_writer_roles')),
    value      jsonb       NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

REVOKE ALL   ON r2dbsvc_registry.platform_declarations FROM PUBLIC;
GRANT SELECT ON r2dbsvc_registry.platform_declarations TO :"api_role";
GRANT SELECT ON r2dbsvc_registry.platform_declarations TO :"controlplane_role";

-- Seed the coalescing window at its current shipped default (`r2db_api.
-- audit_query.DECLARED_COALESCING_WINDOW_MS` == 60000) -- behavior-
-- preserving for an already-running deployment. `surfaces` is deliberately
-- NOT seeded (deployment-specific, design D-2(c)): a deployment applying
-- this migration for the first time must run `ops declare-surfaces` next
-- (design SS9.1 step 2) before either process will start (F-3).
INSERT INTO r2dbsvc_registry.platform_declarations (key, value)
VALUES ('audit_coalescing_window_ms', to_jsonb(60000))
ON CONFLICT (key) DO NOTHING;

-- D-2(h) point 1: seeds the SAME two role names the `ALTER ROLE` statements
-- above just targeted, from the SAME `:api_role`/`:controlplane_role`
-- variables -- `ON CONFLICT ... DO UPDATE` (not `DO NOTHING`) so a second
-- apply of this migration re-converges this row to whatever role names
-- were passed this time (there is no other writer for this row; ops issues
-- no dedicated subcommand for it, design D-2(h) point 4).
INSERT INTO r2dbsvc_registry.platform_declarations (key, value)
VALUES ('audit_writer_roles', to_jsonb(ARRAY[:'api_role', :'controlplane_role']))
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now();

COMMIT;
