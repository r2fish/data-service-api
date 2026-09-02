"""Pre-commit application-audit hook protocol (design docs/design/
PHASE4_DURABLE_AUDIT_SINK_V1.md D-2/D-10, work order WP-3(a)).

Independent implementation of r2db-api's own `r2db_api.audit_hook` module
(R-2's closing paragraph: no code sharing between peers) -- same call
contract, adapted to this peer's own structure: `backend_postgres.
PostgresBackend`/`backend_sqlite.SQLiteBackend` accept an optional
`audit_hook` argument of this shape on `create_collection`/`add_field`/
`delete` (the three backend methods that commit their OWN atomic DDL/DML
statement internally); `cell.ApplicationCell.transact` builds one and
calls it itself, immediately before its own `self._backend.commit()` call,
since that batch orchestration -- unlike the three single-operation backend
methods above -- lives in `cell.py`, not in either backend module (R-3's
own seam split: backend-independent orchestration stays in the seam,
backend-specific execution stays in the backend).

Call contract, honoured identically by every call site above (D-10
parity):

- `pre_commit()` is called as the LAST thing done before the caller's own
  commit point. It performs (or raises attempting) a synchronous, durable,
  already-committed INSERT on an entirely separate connection to the
  platform database -- so a raise here is caught by whatever
  rollback-on-exception machinery the caller already has for its OWN data
  transaction, with no special-casing needed at the call site beyond
  "call it, let a raise propagate, then roll back". `pre_commit()` never
  raises a bare `psycopg.Error`/`sqlite3.Error` -- any underlying failure
  is translated to `errors.AuditSinkUnavailable` by the closure
  `audit_dispatch.AuditRouter` builds, so a caller's own
  `except psycopg.Error`/`except sqlite3.DatabaseError` clauses never
  mistake an audit-sink failure for a data-connection failure.
- `commit_failed()` is called only when the caller's OWN commit
  subsequently fails, AFTER `pre_commit()` already returned successfully
  (reachable on `backend_postgres.PostgresBackend`/`cell.ApplicationCell`'s
  own PostgreSQL-backed `transact()` batch path; never reachable on
  `backend_sqlite.SQLiteBackend`, which has no separate commit step that
  can itself fail once `pre_commit()` has returned -- mirroring
  `structured.ApplicationCell.transact`'s identical, documented absence of
  a `commit_failed()` call on r2db-api's own in-memory backend). It
  durably records an `outcome="error"` row for the SAME operation's fields
  (D-2's error-row rule). The caller fails the response
  `errors.AuditSinkUnavailable` (-> contract `SERVICE_UNAVAILABLE`)
  regardless of whether this call itself succeeds -- the data commit
  already failed either way; this call's own success/failure is only
  test-observable (D-2's own documented limit: `error` rows cover a clean
  commit failure while the process survives, not a process-loss crash
  between the two writes). `commit_failed()` never raises -- any
  underlying failure is swallowed internally by the same closure.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ApplicationAuditHook(Protocol):
    def pre_commit(self) -> None: ...

    def commit_failed(self) -> None: ...


__all__ = ["ApplicationAuditHook"]
