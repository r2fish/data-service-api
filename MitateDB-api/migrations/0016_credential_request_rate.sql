-- MitateDB-api PostgreSQL provisioning -- 0016: credential-keyed
-- `requests_per_minute` rate row (design docs/design/
-- MULTI_PROCESS_WORKER_V0_1.md D-3 (1))
--
-- WHO RUNS THIS: the operator, connected to `mitatedb_platform` AS the
-- `mitatedbsvc_provision` role -- the SAME connection shape 0005/0007/
-- 0011/0012/0013/0014 already document. Run once, after 0002 (this file
-- references `mitatedb_registry.credentials`, created there); order
-- relative to 0005/0007/0011/0012/0013/0014 does not matter -- this is a
-- platform single-shot migration, independent of the declaration/role
-- machinery those files own. No psql variables are required:
--
--   python -m mitatedb_api.ops apply-platform-migration 0016_credential_request_rate.sql --lock-timeout <value>
--   (see MitateDB-api/docs/cloud-run-cloud-sql.md)
--
-- `-v ON_ERROR_STOP=1` must be passed on every `-f` invocation -- without
-- it, psql exits 0 even when a statement in this file errors out.
--
-- WHAT THIS FILE DOES: creates one platform-schema table,
-- `mitatedb_registry.credential_request_rate`, that lets every data-plane
-- process serving this deployment share ONE credential-keyed
-- `requests_per_minute` count instead of each process keeping its own
-- in-memory window -- the multi-process worker gap the sibling
-- `concurrency` bound closes with a host-shared file lock
-- (`mitatedb_api.concurrency_slots`) instead, since a PostgreSQL round
-- trip ahead of authentication would let an unauthenticated flood
-- amplify against this platform database.
--
-- ROW SHAPE: one row per credential. `base_s` (bigint) is the Unix second
-- the row's own window is currently anchored to; `counts` (`int[61]`,
-- fixed length -- the current integer second plus the 60 immediately
-- before it) holds one admitted-request count per second, indexed by
-- `second mod 61` (a ring). `base_s` only ever advances (`GREATEST`: a
-- request that arrives holding an OLDER second than the row's current
-- `base_s` -- because it waited behind this row's own lock -- never
-- rewinds the window); the fixed length keeps every UPDATE's own cost
-- independent of the declared `requests_per_minute` bound. At the window
-- edge the ring counts up to one second more than 60 s, so it may refuse
-- slightly early but never admits past the declared bound.
--
-- PERMISSIONS: `mitatedbsvc_api` -- the SAME least-privilege login role
-- 0002 already provisions for the data-plane process' own read-only
-- credential lookups -- gets SELECT/INSERT/UPDATE on this ONE table, and
-- nothing more: no DELETE (rows are reclaimed structurally, by the
-- `ON DELETE CASCADE` below, never by this role issuing its own delete),
-- no TRUNCATE. No OTHER role (`mitatedbsvc_controlplane`,
-- `mitatedbsvc_auditreader`, or any per-application runtime/developer
-- role) is granted anything on this table at all -- 0002 revokes every
-- `PUBLIC` privilege on `mitatedb_registry`, so this new table keeps that
-- closed-by-default posture for every role this file does not name.
--
-- `ON DELETE CASCADE`: this row is pure derived rate-accounting state for
-- exactly one credential, carrying no audit trail of its own -- deleting
-- the credential a rate row belongs to is never blocked by, and never
-- leaves behind, a rate row for a credential that no longer exists.
--
-- NAMING: this file's own name deliberately does NOT end in
-- `_upgrade.sql` -- it is a platform single-shot migration, not a per-
-- application upgrade script the per-application upgrade-ledger scanner
-- walks.
--
-- IDEMPOTENCY: `CREATE TABLE IF NOT EXISTS`, `CREATE OR REPLACE FUNCTION`
-- and `GRANT` (granting an already-held privilege is a no-op) -- safe to
-- re-run.
--
-- COMPATIBILITY WITH AN ALREADY-DEPLOYED INSTANCE: ADDITIVE ONLY -- adds
-- one new table, one new function and their privileges, revokes nothing
-- anyone already had, alters no existing table.

\set ON_ERROR_STOP on

BEGIN;

CREATE TABLE IF NOT EXISTS mitatedb_registry.credential_request_rate (
    credential_id text   PRIMARY KEY
        REFERENCES mitatedb_registry.credentials(credential_id) ON DELETE CASCADE,
    base_s        bigint NOT NULL,
    counts        int[]  NOT NULL CHECK (array_length(counts, 1) = 61)
);

REVOKE ALL ON mitatedb_registry.credential_request_rate FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE ON mitatedb_registry.credential_request_rate TO mitatedbsvc_api;

-- `credential_request_rate_admit`: the rate count as ONE round trip
-- (`SELECT mitatedb_registry.credential_request_rate_admit($1, $2)`),
-- called by `mitatedb_api.credential_store_postgres.
-- PostgresCredentialStore.record_rate_and_check` on the platform pool's
-- own autocommit connection (`mitatedbsvc_api`) -- this function's own
-- `FOR UPDATE` row lock is released the instant the call returns (there
-- is no enclosing multi-statement transaction to hold it open across).
-- SECURITY INVOKER (the default -- never declared SECURITY DEFINER), so
-- it needs no privilege beyond the table grant immediately above.
--
-- First admission for a credential with no row yet: `INSERT ... ON
-- CONFLICT (credential_id) DO NOTHING` first, then a `SELECT ... FOR
-- UPDATE` re-read. Two concurrent first requests for the same credential
-- never both INSERT into a unique-key failure: the losing transaction
-- blocks on the winning transaction's row lock instead, and once the
-- winner commits, the loser's own re-read sees the committed row and runs
-- the same ring math as any other request for this credential.
--
-- Ring math: reads the row `FOR UPDATE`, computes `shift = LEAST(61,
-- GREATEST(0, now_s - base_s))`, zeroes the `shift` positions right after
-- the row's OWN `base_s` (ring index `(base_s + k) % 61` for `k` in
-- `1..shift`; `shift = 61` zeroes every position at once), advances
-- `base_s` to `GREATEST(base_s, now_s)` (monotonic), and increments the
-- position at the NEW `base_s mod 61`. Returns `true` (and persists the
-- write) when the running total across all 61 positions was strictly
-- below `p_limit` before this increment; `false` (and persists NOTHING
-- -- the row keeps its prior `base_s`/`counts`) otherwise. `clock_
-- timestamp()` is read exactly once per call.
CREATE OR REPLACE FUNCTION mitatedb_registry.credential_request_rate_admit(
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

    INSERT INTO mitatedb_registry.credential_request_rate (credential_id, base_s, counts)
    VALUES (p_credential_id, v_now_s, array_fill(0, ARRAY[61]))
    ON CONFLICT (credential_id) DO NOTHING;

    SELECT base_s, counts INTO v_base_s, v_counts
      FROM mitatedb_registry.credential_request_rate
     WHERE credential_id = p_credential_id
       FOR UPDATE;

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
    UPDATE mitatedb_registry.credential_request_rate
       SET base_s = v_new_base_s, counts = v_counts
     WHERE credential_id = p_credential_id;
    RETURN true;
END;
$fn$;

REVOKE ALL ON FUNCTION mitatedb_registry.credential_request_rate_admit(text, integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION mitatedb_registry.credential_request_rate_admit(text, integer) TO mitatedbsvc_api;

COMMIT;
