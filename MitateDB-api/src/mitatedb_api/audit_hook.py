"""Pre-commit application-audit hook protocol (design docs/design/
PHASE4_DURABLE_AUDIT_SINK_V1.md D-2/D-10, work order WP-3(a)).

Independent implementation of r2db-api's own `r2db_api.audit_hook` module
(R-2's closing paragraph: no code sharing between peers) -- same call
contract, adapted to this peer's own structure: `backend_postgres.
PostgresBackend`/`backend_sqlite.SQLiteBackend` accept an optional
`audit_hook` argument of this shape on `create_collection`/`add_field`/
`alter_field_constraints`/`delete` (the four backend methods that commit
their OWN atomic DDL/DML statement internally); `cell.ApplicationCell.
transact` and its single-row `insert`/`update` path
(`_write_row_before_commit`) build one and call it themselves,
immediately before their own `self._backend.commit()` call, since that
orchestration -- unlike the four single-operation backend methods above --
lives in `cell.py`, not in either backend module (R-3's own seam split:
backend-independent orchestration stays in the seam, backend-specific
execution stays in the backend).

Call contract, honoured identically by every call site above (D-10
parity):

- `pre_commit()` is called immediately before the caller's own commit
  point, after every statement of the caller's transaction except the
  ones the order below names. It performs (or raises attempting) a
  synchronous, durable, already-committed INSERT on an entirely separate
  connection to the platform database -- so a raise here is caught by
  whatever rollback-on-exception machinery the caller already has for its
  OWN data transaction, with no special-casing needed at the call site
  beyond "call it, let a raise propagate, then roll back".
  `pre_commit()` never raises a bare `psycopg.Error`/`sqlite3.Error` --
  any underlying failure is translated to `errors.AuditSinkUnavailable`
  by the closure `audit_dispatch.AuditRouter` builds, so a caller's own
  `except psycopg.Error`/`except sqlite3.DatabaseError` clauses never
  mistake an audit-sink failure for a data-connection failure. The order
  differs by call site: `transact` records its idempotency entry first and
  calls `pre_commit()` last, the single-row write (which has no idempotency
  entry) calls `pre_commit()` last after its statement; the schema
  operations `create_collection`/`add_field`/`alter_field_constraints`
  call `pre_commit()` first and record the idempotency entry after it, so
  a failure of that record write comes after the `allow` row and is
  covered by `commit_failed()` below.
- `commit_failed()` is called at most once per operation, and only after
  `pre_commit()` already returned successfully: on every path that leaves
  the caller without its data committed -- a failed, cancelled or
  lock-timed-out commit, a failed idempotency record write, and a
  rollback that itself fails because the connection was lost. Its call
  sites are the four backend methods' own failure branches (PostgreSQL),
  `cell.ApplicationCell._error_row_once_fired` (around every backend call
  that takes the hook), the `transact` batch path and the single-row write
  path (both reach it on the SQLite backend too). It durably records
  an `outcome="error"` row for the SAME operation's fields (D-2's
  error-row rule). The caller fails the response
  `errors.AuditSinkUnavailable` (-> contract `SERVICE_UNAVAILABLE`)
  regardless of whether this call itself succeeds -- the data commit
  already failed either way; this call's own success/failure is only
  test-observable (D-2's own documented limit: `error` rows cover a
  failure the service sees while the process survives, not a process-loss
  crash between the two writes; and a connection lost during the commit
  itself leaves the commit's outcome unknown, so the row means "the
  service did not see it commit"). `commit_failed()` never raises -- any
  underlying failure is swallowed internally by the same closure.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ApplicationAuditHook(Protocol):
    def pre_commit(self) -> None: ...

    def commit_failed(self) -> None: ...


__all__ = ["ApplicationAuditHook"]
