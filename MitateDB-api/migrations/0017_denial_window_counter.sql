-- MitateDB-api PostgreSQL provisioning -- 0017: refusal-window counter
--
-- WHO RUNS THIS: the operator, connected to `mitatedb_platform` AS the
-- `mitatedbsvc_provision` role -- the SAME connection shape 0005/0007/
-- 0011/0012/0013/0014/0016 already document. Run once, after 0005 (this
-- file references `mitatedb_registry.application_audit` and the
-- `mitatedbsvc_auditreader` role, both created there); order relative to
-- the other platform single-shot migrations does not matter. No psql
-- variables are required:
--
--   python -m mitatedb_api.ops apply-platform-migration 0017_denial_window_counter.sql --lock-timeout <value>
--   (see MitateDB-api/docs/cloud-run-cloud-sql.md)
--
-- `-v ON_ERROR_STOP=1` must be passed on every `-f` invocation -- without
-- it, psql exits 0 even when a statement in this file errors out.
--
-- WHAT THIS FILE DOES: gives the count of refused requests a home in the
-- platform database, so that a service process that stops without a
-- graceful shutdown loses no count of a refusal whose response it had
-- already returned. Repeated refusals of the same kind (same application,
-- actor, operation and reason code) inside one time window are represented
-- by ONE `application_audit` row for the first refusal plus ONE counter row
-- here; every later refusal in the window adds one to that counter row
-- BEFORE its response is returned.
--
--   1. `mitatedb_registry.denial_window_counter` -- one row per (composite
--      key, window). The composite key `denial_key` folds the key parts
--      into one text value: a JSON array of the window length in
--      milliseconds, the application id (a refusal with no application
--      folds to JSON null, distinct from every real id), the actor id (no
--      actor folds to the text `unknown`), the operation and the reason
--      code. The window length is part of the key, so two processes that
--      run with different declared window lengths (a length changed while
--      processes restart one by one) never share a counter row: a row is
--      only ever added to by callers that agree on when it ends.
--      `window_start` is the wall-clock instant the window began, aligned to the window length (the
--      database's `clock_timestamp()` truncated to a multiple of the
--      length), `window_end` the instant it ends. `occurrences` counts every
--      refusal of the window including the first. The row also stores the
--      first refusal's fields and the `event_id` of the summary event
--      `audit_query` returns for the window, fixed when the row is created
--      so a reader's cursor stays stable across reads.
--   2. `mitatedb_registry.denial_window_record(...)` -- the only way the
--      data plane touches that table. It runs as its owner (SECURITY
--      DEFINER), so `mitatedbsvc_api` needs no privilege on the counter
--      table at all and can neither lower, delete, nor rewrite a count (a
--      counter row is audit evidence, unlike the `requests_per_minute` rate
--      row 0016 keeps). The function is one statement for the caller, run
--      in autocommit: the first refusal of a window creates the counter row
--      and writes that refusal's own `application_audit` row in the same
--      statement; every later one adds one to `occurrences`, and raises
--      (the caller's refusal becomes a 503) if that row is gone. The
--      primary key `(denial_key, window_start)` serializes two concurrent first
--      refusals of one key, so a window holds exactly one counter row and
--      one first-refusal row however many callers race.
--   3. `audit_query` reads the counter rows of CLOSED windows -- those whose
--      `window_end` is older than `now() - visibility_lag_ms` -- as summary
--      events, through `mitatedbsvc_auditreader`'s new SELECT.
--
-- PERMISSIONS: `mitatedbsvc_api` gets EXECUTE on the function and nothing
-- on the table. PUBLIC has neither (EXECUTE on the function is revoked from
-- PUBLIC explicitly: a new function is executable by PUBLIC by default).
-- `mitatedbsvc_auditreader` gets SELECT on the table. The table and the
-- function are owned by the schema's owner role, never by the role that
-- happens to run this file: the ownership is set explicitly below, so a run
-- as a more privileged administrative role leaves the definer function
-- owned by the role that owns `application_audit` and its sequence, and by
-- no wider role. On a platform provisioned by 0001/0002 the schema's owner
-- is `mitatedbsvc_provision`, the role that runs this file.
--
-- SECURITY DEFINER hygiene: `search_path` is pinned to `pg_catalog, pg_temp`
-- on the function and every object it names is schema-qualified, so a
-- caller cannot redirect a name the function resolves.
--
-- IDEMPOTENCY: `CREATE TABLE IF NOT EXISTS`, `CREATE OR REPLACE FUNCTION`
-- (owner and grants survive it; the `REVOKE`/`GRANT` statements below run
-- again and change nothing), `ALTER ... OWNER TO` the current owner, and
-- `GRANT` are all safe to re-run.
--
-- COMPATIBILITY WITH AN ALREADY-DEPLOYED INSTANCE: ADDITIVE ONLY -- one new
-- table, one new function, and grants naming only those two objects. No
-- existing table is altered, no existing grant is changed or revoked. The
-- rows of a data plane that has not yet been upgraded keep working: it
-- never calls the function. Rollback: dropping the function and the table
-- restores the prior state exactly.

\set ON_ERROR_STOP on

BEGIN;

CREATE TABLE IF NOT EXISTS mitatedb_registry.denial_window_counter (
    denial_key       text        NOT NULL,
    window_start     timestamptz NOT NULL,
    window_end       timestamptz NOT NULL,
    occurrences      integer     NOT NULL,
    summary_event_id text        NOT NULL,
    event_class      text        NOT NULL,
    occurred_at      timestamptz NOT NULL,
    request_id       text,
    application_id   text,
    actor_type       text,
    actor_id         text,
    role             text,
    operation        text        NOT NULL,
    target_kind      text,
    reason_code      text,
    target_id        text,
    PRIMARY KEY (denial_key, window_start),
    CONSTRAINT denial_window_counter_occurrences_positive CHECK (occurrences >= 1),
    CONSTRAINT denial_window_counter_window_ordered       CHECK (window_end > window_start),
    CONSTRAINT denial_window_counter_len_event_class      CHECK (length(event_class)    <= 64),
    CONSTRAINT denial_window_counter_len_request_id       CHECK (length(request_id)     <= 256),
    CONSTRAINT denial_window_counter_len_application_id   CHECK (length(application_id) <= 256),
    CONSTRAINT denial_window_counter_len_actor_type       CHECK (length(actor_type)     <= 64),
    CONSTRAINT denial_window_counter_len_actor_id         CHECK (length(actor_id)       <= 256),
    CONSTRAINT denial_window_counter_len_role             CHECK (length(role)           <= 64),
    CONSTRAINT denial_window_counter_len_operation        CHECK (length(operation)      <= 64),
    CONSTRAINT denial_window_counter_len_target_kind      CHECK (length(target_kind)    <= 64),
    CONSTRAINT denial_window_counter_len_reason_code      CHECK (length(reason_code)    <= 128),
    CONSTRAINT denial_window_counter_len_target_id        CHECK (length(target_id)      <= 256)
);

REVOKE ALL ON TABLE mitatedb_registry.denial_window_counter FROM PUBLIC;

-- `denial_window_record`: the window is aligned to the clock (the
-- database's `clock_timestamp()`, the same clock the audit rows' own
-- `recorded_at` uses, truncated to a multiple of `p_window_ms`), so every
-- data-plane process, whatever its own clock, agrees on which window a
-- refusal belongs to. A window length of 0 declares "no coalescing": the
-- refusal is written as an ordinary `application_audit` row and no counter
-- row exists.
--
-- The first refusal of a (key, window) pair inserts the counter row with
-- `ON CONFLICT DO NOTHING` and, only when that insert took effect
-- (`ROW_COUNT` = 1), writes its own audit row. A concurrent first refusal
-- of the same key blocks on the primary key until the winner commits, then
-- inserts nothing and adds one to `occurrences` instead, so the window
-- holds one counter row and one first-refusal row. A refusal that finds the
-- row already there adds one to it. `occurrences` therefore counts the
-- first refusal too; `audit_query` reports `occurrences - 1` repeats as the
-- summary event's `count`, and none at all when `occurrences` is 1.
--
-- `event_id` is the 32-character lowercase hex form of a random UUID, the
-- form every other `application_audit` row of this peer carries.
CREATE OR REPLACE FUNCTION mitatedb_registry.denial_window_record(
    p_window_ms      integer,
    p_event_class    text,
    p_occurred_at    timestamptz,
    p_request_id     text,
    p_application_id text,
    p_actor_type     text,
    p_actor_id       text,
    p_role           text,
    p_operation      text,
    p_target_kind    text,
    p_reason_code    text,
    p_target_id      text
) RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
    v_now            timestamptz := clock_timestamp();
    v_now_ms         bigint;
    v_start_ms       bigint;
    v_window_start   timestamptz;
    v_key            text;
    v_inserted       bigint;
BEGIN
    IF p_window_ms IS NULL OR p_window_ms < 0 THEN
        RAISE EXCEPTION 'denial_window_record: the window length must be a non-negative number of milliseconds';
    END IF;

    IF p_window_ms > 0 THEN
        v_now_ms := floor(extract(epoch FROM v_now) * 1000)::bigint;
        v_start_ms := v_now_ms - (v_now_ms % p_window_ms);
        v_window_start := timestamptz 'epoch' + (v_start_ms * interval '1 millisecond');
        v_key := jsonb_build_array(p_window_ms, p_application_id, coalesce(p_actor_id, 'unknown'), p_operation, p_reason_code)::text;

        INSERT INTO mitatedb_registry.denial_window_counter (
            denial_key, window_start, window_end, occurrences, summary_event_id,
            event_class, occurred_at, request_id, application_id, actor_type, actor_id,
            role, operation, target_kind, reason_code, target_id
        ) VALUES (
            v_key, v_window_start, v_window_start + (p_window_ms * interval '1 millisecond'), 1,
            replace(gen_random_uuid()::text, '-', ''),
            p_event_class, coalesce(p_occurred_at, v_now), p_request_id, p_application_id, p_actor_type, p_actor_id,
            p_role, p_operation, p_target_kind, p_reason_code, p_target_id
        )
        ON CONFLICT (denial_key, window_start) DO NOTHING;
        GET DIAGNOSTICS v_inserted = ROW_COUNT;

        IF v_inserted = 0 THEN
            UPDATE mitatedb_registry.denial_window_counter
               SET occurrences = occurrences + 1
             WHERE denial_key = v_key
               AND window_start = v_window_start;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'denial_window_record: the counter row of the window is gone, the refusal was not counted';
            END IF;
            RETURN;
        END IF;
    END IF;

    INSERT INTO mitatedb_registry.application_audit (
        event_id, event_class, occurred_at, request_id, application_id, actor_type, actor_id,
        role, operation, target_kind, outcome, reason_code, target_id, count
    ) VALUES (
        replace(gen_random_uuid()::text, '-', ''), p_event_class, coalesce(p_occurred_at, v_now), p_request_id,
        p_application_id, p_actor_type, p_actor_id,
        p_role, p_operation, p_target_kind, 'deny', p_reason_code, p_target_id, NULL
    );
END;
$fn$;

-- The owner is the schema's owner role whichever role runs this file. Read
-- from the catalog, never from `current_user`: a run as an administrative
-- role must not leave a definer function owned by that role.
DO $own$
DECLARE
    v_owner name;
BEGIN
    SELECT pg_get_userbyid(nspowner) INTO v_owner FROM pg_namespace WHERE nspname = 'mitatedb_registry';
    EXECUTE format('ALTER TABLE mitatedb_registry.denial_window_counter OWNER TO %I', v_owner);
    EXECUTE format(
        'ALTER FUNCTION mitatedb_registry.denial_window_record(integer, text, timestamptz, text, text, text, text, text, text, text, text, text) OWNER TO %I',
        v_owner
    );
END;
$own$;

REVOKE ALL ON FUNCTION mitatedb_registry.denial_window_record(integer, text, timestamptz, text, text, text, text, text, text, text, text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION mitatedb_registry.denial_window_record(integer, text, timestamptz, text, text, text, text, text, text, text, text, text) TO mitatedbsvc_api;

GRANT SELECT ON mitatedb_registry.denial_window_counter TO mitatedbsvc_auditreader;

COMMIT;
