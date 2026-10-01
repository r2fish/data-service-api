# src/mitatedb_api/config.py -- code-comment history

Companion for `src/mitatedb_api/config.py` per `docs/code-history/README.md`.

## CH-0549

- moved from: `src/mitatedb_api/config.py` (`role_pool_size`)
- parent commit: `ddf9c73`
- kind: docstring

```
(design docs/design/MULTI_PROCESS_WORKER_V0_1.md D-3 (5)): the
platform pool's own default size (`main.py`'s `pool.BoundedConnection
Pool`, backing `PostgresCredentialStore`'s authentication reads and
its `requests_per_minute` rate statement) derives from `thread_limit`
-- the effective, env-overridden `ThreadLimitMiddleware` value
(`http.py`'s own `create_app(..., thread_limit=)`).

Basis: once concurrent requests' authentication reads can genuinely
reach this pool at once (`http.py`'s own `run_in_threadpool`
delegation), a pool sized below the number of requests that can
borrow from it at once times out waiting for a pooled connection and
fails closed with `AUTH_STATE_UNAVAILABLE` well under the declared
bound, instead of a client ever seeing the declared `LIMIT_EXCEEDED`
at the real ceiling. The number of connections ONE process can
genuinely borrow at once is bounded by how many worker THREADS that
process' own event loop hands a synchronous request section to --
`thread_limit` -- never by `max_concurrency`, the deployment-wide
admission bound every worker process enforces TOGETHER (the
host-shared slot directory), which holds no connection of its own.
Every platform-pool borrower on this peer is such a request thread
(the authentication borrow is returned before the rate statement
borrows), so `thread_limit + 2` (`_POOL_SIZE_HEADROOM`) covers the
real simultaneous borrows with 2 to spare, and `process_ceilings.
data` processes share `max_connections` without the budget scaling
with the declared `concurrency` bound.

This peer's per-application data path is NOT pooled at all
(`backend_postgres.PostgresBackend`: two fixed, persistent connections
per served application per process, serialized by `cell.py`'s own
request-wide lock) -- there is no per-application counterpart to this
function on this peer, only this one platform-pool consumer.
```

### correction: 2026-10-01

- reason: each served application's backend now holds one pool per role sized by this function, and the cell holds no request-wide lock

old:
```
This peer's per-application data path is NOT pooled at all (`backend_postgres.PostgresBackend`: two fixed, persistent connections per served application per process, serialized by `cell.py`'s own request-wide lock) -- there is no per-application counterpart to this function on this peer, only this one platform-pool consumer.
```

new:
```
This peer's per-application data path uses the same size: each served application's `backend_postgres.PostgresBackend` holds one pool per role (runtime, developer) of up to this many connections (`main.py` passes it as `pool_size=`), and a request borrows at most one connection per role from them; `cell.py` holds no request-wide lock.
```
