# r2db-api/http.py -- code-comment history

Companion for `r2db-api/src/r2db_api/http.py` per `docs/code-history/README.md`.

## CH-0544

- moved from: `src/r2db_api/http.py` (`<module>`)
- parent commit: `2e746cc`
- kind: comment

```
# --------------------------------------------------------------------------
# Endpoints (spec/data-service-api.v1.json -> "endpoints").
#
# Phase 10 WP-8a (design D-8 (3)): every synchronous section below --
# `_authenticate` (a real psycopg round trip through `PostgresCredentialStore`
# in the production composition, `postgres.py`'s `_RolePool`/
# `SharedPoolManager`) and each `DataService` call (the query/mutate/schema
# execution itself) -- runs via `starlette.concurrency.run_in_threadpool`,
# never directly on the event-loop thread. The one `await` each handler
# below performs for its own request body (`_read_json_object`) is left
# untouched on the loop; delegation begins only once that read has already
# completed, never around it, so a handler whose contract shape needs the
# body first (`post_query`/`post_mutate`/`post_schema`) offloads in two
# separate calls -- one for `_authenticate` (which this contract's own
# "authenticate before validating the body" ordering places BEFORE the
# read), one for the shape-check + `DataService` call (placed after) --
# rather than reordering authentication behind body parsing. A handler with
# no body to read (`get_capabilities`/`get_catalog`/
# `post_cross_entity_mutate`/`post_audit_query`) offloads the whole
# authenticate-then-call sequence in one `run_in_threadpool` call, since
# there is no `await` in between to delegate around.
#
# `run_in_threadpool` draws from anyio's default worker-thread limiter
# (default capacity 40, `anyio.to_thread.current_default_thread_limiter().
# total_tokens`). Phase 10 WP-8a review F-7 (supervisor ruling
# 2026-09-08): capacity 40 does NOT bound this delegation's own
# worker-thread demand at `ResourceLimits.concurrency` (32) simultaneous
# requests -- `_authenticate` occupies a worker thread BEFORE `DataService.
# _slot` ever takes a concurrency slot (so demand at the declared ceiling
# is "32 in-flight requests + however many authentications are
# concurrently in progress", not simply 32), and the limiter itself is one
# event-loop-wide resource shared with every other `run_in_threadpool`
# caller in this process, not one dedicated to this module. What IS true:
# exhausting it does not deadlock -- a caller unable to get a worker thread
# right away waits for one to free up (the same fail-open-to-latency,
# never-a-hang shape `_RolePool`'s own `acquire_timeout` already has), it
# does not hang forever or crash the process.
#
# Phase 10 WP-8c (design D-8 (3), review F-2): every handler below now
# enters `service.acquire_concurrency_slot()` as its OWN first statement,
# before `_authenticate` -- the data-plane evaluation order is now BYTE
# BOUND (RequestByteBoundMiddleware, defined above in this module and
# applied by this module's own `create_app`, not `main.py`) -> CONCURRENCY
# SLOT -> AUTHENTICATION -> body read -> rate/business (`DataService._slot`, still
# entered post-authentication, via `concurrency_precharged=True` so the
# same single reservation is never taken twice). This mirrors the control
# plane's own pre-auth admission shape (`control_http.py`'s module header:
# "check_rate() ... charged before anything else, including
# authentication"), applied to `concurrency` rather than `requests_per_
# minute` here -- `concurrency` alone is credential-independent, so it
# alone can be evaluated before a credential is known at all; the rate
# window stays keyed by `credential_id` and therefore stays post-auth
# (`DataService._acquire_rate`, `DataService._slot`'s own docstring).
# Closes review F-2's own measured gap: before this WP, an unauthenticated
# flood of invalid bearer tokens never touched the concurrency counter at
# all -- `_authenticate`'s own worker-thread and platform-credential-pool
# demand grew unbounded by `limits.concurrency`, up to anyio's own
# thread-limiter ceiling (40), while legitimate authenticated callers
# could see `AUTH_STATE_UNAVAILABLE`/503 once the platform pool (default
# size 4) was exhausted. `acquire_concurrency_slot()` is held for the
# caller's own ENTIRE request -- across both `run_in_threadpool` calls a
# body-carrying handler makes (`_authenticate`, then `_run`) -- via a
# `with` statement that never returns control to this coroutine until the
# whole request is done; Starlette's `run_in_threadpool` (`anyio.to_thread.
# run_sync`) copies the CURRENT `contextvars.Context` into the worker
# thread it runs on, so a plain synchronous `with` entered on the event-
# loop thread, wrapping two SEPARATE `await run_in_threadpool(...)` calls
# that may each land on a different physical OS thread, still correctly
# spans both -- the lock this context manager holds is a `threading.Lock`
# on the shared `DataService` instance, not anything thread-affine.
# --------------------------------------------------------------------------
```
