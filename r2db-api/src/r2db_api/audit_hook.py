"""Pre-commit application-audit hook protocol (design PHASE4_DURABLE_
AUDIT_SINK_V1.md D-2/D-10).

`StorageBackend.transact`/`apply_schema` (`backend.py`) accept an optional
`audit_hook` argument of this shape. `DataService` (`service.py`) builds one
per request, with every field the durable row needs already bound in a
closure -- the backend itself has no idea what `request_id`/`application_id`/
`actor_id`/... to write, only whether *this particular call* is fail-closed
class (D-2's normative rule: the `DESTRUCTIVE_CONFIRMATION_V1` choke for
`transact`, unconditionally for `apply_schema`).

Call contract, both backends (`structured.ApplicationCell`, `postgres.
PostgresCell`) honour identically (D-10 parity):

- `pre_commit()` is called as the LAST thing the backend does before its own
  commit point (`ApplicationCell`: right before returning; `PostgresCell`:
  the last statement inside `with conn.transaction():`). It performs (or
  raises attempting) a synchronous, durable, already-committed INSERT on an
  entirely separate connection to the platform database -- so a raise here
  is caught by whatever rollback-on-exception machinery the backend already
  has for its OWN data transaction (`ApplicationCell`'s before/except
  restore, `PostgresCell`'s `conn.transaction()` context manager), with no
  special-casing needed at the call site beyond "call it, let a raise
  propagate". `pre_commit()` never raises a bare `psycopg.Error` -- any
  underlying failure is translated to `errors.FoundationError("SERVICE_
  UNAVAILABLE", ..., status=503)` by the closure `DataService` builds, so a
  backend's own `except psycopg.Error` clauses never mistake an audit-sink
  failure for a data-connection failure.
- `commit_failed()` is called only when the backend's OWN commit
  subsequently fails, AFTER `pre_commit()` already returned successfully
  (only reachable for `PostgresCell` -- `ApplicationCell` has no separate
  commit step that can fail once `pre_commit()` has returned, so it never
  calls this method at all). It durably records an `outcome="error"` row
  for the SAME `request_id` (D-2's error-row rule). The backend fails the
  response `SERVICE_UNAVAILABLE` regardless of whether this call itself
  succeeds -- the data commit already failed either way; this call's own
  success/failure is only test-observable (D-2's own documented limit:
  `error` rows cover a clean commit failure while the process survives, not
  a process-loss crash between the two writes).
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ApplicationAuditHook(Protocol):
    def pre_commit(self) -> None: ...

    def commit_failed(self) -> None: ...


__all__ = ["ApplicationAuditHook"]
