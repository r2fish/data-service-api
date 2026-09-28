-- r2db-api PostgreSQL provisioning -- 0015: credential-keyed
-- `requests_per_minute` rate row (design docs/design/
-- MULTI_PROCESS_WORKER_V0_1.md D-3 (1), 監督裁定 3/15/30/34/37, work order
-- docs/work-orders/WORK_ORDER_R113_MULTI_PROCESS_WORKER_V1.md WP-2)
--
-- WHO RUNS THIS: the operator, connected to the `r2dbsvc_platform` database
-- AS the `r2dbsvc_control` role -- the same role/connection 0002/0005/0006/
-- 0007/0008/0012/0013/0014 already run as. Run once, after 0005 (this file
-- references `r2dbsvc_registry.credentials`, created there; order relative
-- to 0006/0007/0008/0012/0013/0014 does not matter -- this is a platform
-- single-shot migration, independent of the control-plane/audit/
-- declaration machinery those files own):
--
--   python -m r2db_api.ops apply-platform-migration 0015_credential_request_rate.sql --lock-timeout <value>
--   (see POSTGRES_PROVISIONING_RUNBOOK.md)
--
-- `-v ON_ERROR_STOP=1` must be passed on every `-f` invocation -- without
-- it, psql exits 0 even when a statement in this file errors out.
--
-- WHAT THIS FILE DOES: creates one platform-schema table,
-- `r2dbsvc_registry.credential_request_rate`, that lets every data-plane
-- process serving this deployment share ONE credential-keyed
-- `requests_per_minute` count instead of each process keeping its own
-- in-memory window (design D-3 (1)/裁定15) -- the multi-process worker
-- gap the sibling `concurrency` bound closes with a host-shared file lock
-- (`r2db_api.concurrency_slots`) instead, since a PostgreSQL round trip
-- ahead of authentication would let an unauthenticated flood amplify
-- against this platform database (design 条件 5).
--
-- ROW SHAPE (design D-3 (1) v0.5, 裁定 34/37): one row per credential.
-- `base_s` (bigint) is the Unix second the row's own window is currently
-- anchored to; `counts` (`int[61]`, fixed length -- the current integer
-- second plus the 60 immediately before it, 裁定34) holds one admitted-
-- request count per second, indexed by `second mod 61` (a ring, 監督裁定
-- 3). `base_s` only ever advances (`GREATEST`, 裁定37: a request that
-- arrives holding an OLDER second than the row's current `base_s` --
-- because it waited behind this row's own lock -- never rewinds the
-- window); the fixed length keeps every UPDATE's own cost independent of
-- the declared `requests_per_minute` bound (裁定30), unlike the
-- `timestamptz[]` shape an earlier revision of this design considered
-- (design D-3 (1)'s own v0.3 text, superseded).
--
-- PERMISSIONS (design D-3 (1)): `r2dbsvc_api` -- the SAME strictly
-- least-privilege login role `0005_credential_store.sql` already
-- provisions for the data-plane process' own read-only credential lookups
-- -- gets SELECT/INSERT/UPDATE on this ONE table, and nothing more: no
-- DELETE (rows are reclaimed structurally, by the `ON DELETE CASCADE`
-- below, never by this role issuing its own delete), no TRUNCATE. No
-- OTHER role (`r2dbsvc_control`, `r2dbsvc_controlplane`,
-- `r2dbsvc_auditreader`, or any per-application runtime/developer role)
-- is granted anything on this table at all -- `r2dbsvc_registry` has never
-- granted anything to `PUBLIC` (0002's own header), so this new table
-- inherits that closed-by-default posture for every role this file does
-- not name explicitly.
--
-- `ON DELETE CASCADE` (unlike `credentials.application_slug`'s own
-- `ON DELETE RESTRICT` to `applications`, 0005's header): this row is
-- pure derived rate-accounting state for exactly one credential, carrying
-- no audit trail of its own (the durable audit sink already records every
-- request `credential_request_rate` ever counted) -- deleting the
-- credential a rate row belongs to should never be blocked by, or leave
-- behind, a rate row for a credential that no longer exists.
--
-- IDEMPOTENCY: `CREATE TABLE IF NOT EXISTS` + `GRANT` (granting an
-- already-held privilege is a no-op) -- safe to re-run.
--
-- COMPATIBILITY WITH THE ALREADY-DEPLOYED r2db-api INSTANCE: ADDITIVE
-- ONLY -- adds one new table and three new privileges on it, revokes
-- nothing, alters no existing table.

\set ON_ERROR_STOP on

BEGIN;

CREATE TABLE IF NOT EXISTS r2dbsvc_registry.credential_request_rate (
    credential_id text   PRIMARY KEY
        REFERENCES r2dbsvc_registry.credentials(credential_id) ON DELETE CASCADE,
    base_s        bigint NOT NULL,
    counts        int[]  NOT NULL CHECK (array_length(counts, 1) = 61)
);

GRANT SELECT, INSERT, UPDATE ON r2dbsvc_registry.credential_request_rate TO r2dbsvc_api;

-- `credential_request_rate_admit` (design D-3 (1) v0.5's own "1 文の骨子"
-- realized as a single SECURITY INVOKER PL/pgSQL function, rather than a
-- literal `INSERT ... ON CONFLICT ... WHERE ... RETURNING` at the call
-- site): `r2db_api.credential_store.PostgresCredentialStore.record_rate_
-- and_check` calls this with exactly one round trip
-- (`SELECT r2dbsvc_registry.credential_request_rate_admit($1, $2)`),
-- under the SAME autocommit connection/role (`r2dbsvc_api`) the read
-- path already uses -- this function's own `FOR UPDATE` row lock is
-- released the instant the call returns (there is no enclosing multi-
-- statement transaction to hold it open across). Runs SECURITY INVOKER
-- (the default -- never declared SECURITY DEFINER), so it needs no
-- privilege beyond the table grant immediately above.
--
-- Ring math (裁定 3/30/34/37): reads the row `FOR UPDATE`, computes
-- `shift = LEAST(61, GREATEST(0, now_s - base_s))`, zeroes the `shift`
-- positions immediately after the row's OWN `base_s` (a ring index,
-- `(base_s + k) % 61` for `k` in `1..shift`; `shift = 61` zeroes every
-- position at once rather than looping 61 times to the same effect),
-- advances `base_s` to `GREATEST(base_s, now_s)` (monotonic -- a request
-- that waited behind this row's own lock and now holds an OLDER second
-- than a concurrent winner already committed never rewinds the window),
-- and increments the position at the NEW `base_s mod 61`. Returns
-- `true` (and persists the write) when the running total across all 61
-- positions was strictly below `p_limit` before this increment; `false`
-- (and persists NOTHING -- the row keeps its prior `base_s`/`counts`
-- untouched) otherwise, mirroring the literal template's own `WHERE
-- <sum> < $L` -- a denied request never advances or zeroes the window a
-- later request depends on.
CREATE OR REPLACE FUNCTION r2dbsvc_registry.credential_request_rate_admit(
    p_credential_id text,
    p_limit integer
) RETURNS boolean
LANGUAGE plpgsql
AS $fn$
DECLARE
    v_now_s      bigint;
    v_now_idx    integer;
    v_base_s     bigint;
    v_new_base_s bigint;
    v_counts     int[];
    v_shift      bigint;
    v_old_idx    integer;
    v_total      integer;
    v_i          integer;
BEGIN
    v_now_s := floor(extract(epoch FROM clock_timestamp()))::bigint;

    SELECT base_s, counts INTO v_base_s, v_counts
      FROM r2dbsvc_registry.credential_request_rate
     WHERE credential_id = p_credential_id
       FOR UPDATE;

    IF NOT FOUND THEN
        v_counts := array_fill(0, ARRAY[61]);
        v_now_idx := v_now_s % 61;
        v_counts[v_now_idx + 1] := 1;
        INSERT INTO r2dbsvc_registry.credential_request_rate (credential_id, base_s, counts)
        VALUES (p_credential_id, v_now_s, v_counts);
        RETURN true;
    END IF;

    v_shift := LEAST(61, GREATEST(0, v_now_s - v_base_s));
    IF v_shift >= 61 THEN
        v_counts := array_fill(0, ARRAY[61]);
    ELSIF v_shift > 0 THEN
        v_old_idx := v_base_s % 61;
        FOR v_i IN 1..v_shift LOOP
            v_counts[((v_old_idx + v_i) % 61) + 1] := 0;
        END LOOP;
    END IF;
    v_new_base_s := GREATEST(v_base_s, v_now_s);
    v_now_idx := v_new_base_s % 61;

    v_total := 0;
    FOR v_i IN 1..61 LOOP
        v_total := v_total + v_counts[v_i];
    END LOOP;

    IF v_total >= p_limit THEN
        RETURN false;
    END IF;

    v_counts[v_now_idx + 1] := v_counts[v_now_idx + 1] + 1;
    UPDATE r2dbsvc_registry.credential_request_rate
       SET base_s = v_new_base_s, counts = v_counts
     WHERE credential_id = p_credential_id;
    RETURN true;
END;
$fn$;

REVOKE ALL ON FUNCTION r2dbsvc_registry.credential_request_rate_admit(text, integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION r2dbsvc_registry.credential_request_rate_admit(text, integer) TO r2dbsvc_api;

COMMIT;
