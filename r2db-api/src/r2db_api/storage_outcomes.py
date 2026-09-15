"""r2db-api storage-backend result shapes for `StorageBackend.query`/
`.transact`/`.apply_schema` (ST10).

A pure leaf: three frozen dataclasses with no logic beyond their own field
defaults and `QueryOutcome`'s `__post_init__` invariant check."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


# --- CCR-13 return shapes (design R2DB_CCR13_STORAGE_V1.md §3, revised per
# WP-2 review M-10) ----------------------------------------------------------
#
# `StorageBackend.query`/`.transact` now carry more than a bare list/count:
# per-row revisions + a continuation signal for query, and resolved insert
# addresses for transact. These are plain frozen dataclasses -- an earlier
# revision made them `list`/`int` subclasses so old equality comparisons
# (`rows == [...]`, `affected == 3`) would keep passing unchanged, but that
# is exactly the "empty green" M-10 flagged: an assertion that never looks
# at `.revisions`/`.assigned_addresses` cannot fail when those fields are
# wrong. Every caller (`service.py`, `postgres.py`'s shim, `ApplicationCell`
# itself, and both `test_foundation.py` and `test_postgres.py`'s direct
# `query()`/`transact()` call sites) is updated to read `.items`/`.affected`
# explicitly instead.


@dataclass(frozen=True)
class QueryOutcome:
    """`query()`'s result: projected rows, plus (CCR-13) their per-row
    revisions (index-aligned with `items`) and pagination continuation.
    `revisions` is `None` when a backend does not maintain revisions yet
    (e.g. `PostgresCell`'s WP-2 shim, which has no revision column until
    WP-3) -- never a wrong-length placeholder list, which `__post_init__`
    enforces as a checked invariant rather than a convention. `has_more` is
    the boolean signal from R-6 (`page.size` window was exceeded by the
    look-ahead fetch); `next_cursor`, when not `None`, is the ready-to-
    return opaque cursor a caller can hand straight to `next_page`.
    """

    items: list[dict[str, Any]]
    revisions: list[str] | None = None
    has_more: bool = False
    next_cursor: str | None = None

    def __post_init__(self) -> None:
        if self.revisions is not None and len(self.revisions) != len(self.items):
            raise ValueError("QueryOutcome.revisions must be None (unmaintained) or index-aligned with items")


@dataclass(frozen=True)
class MutationOutcome:
    """`transact()`'s result: the affected-row count, plus (CCR-13) the
    addresses `transact` resolved for insert (and insert-resolved upsert)
    operations, in operation order.

    `assigned_addresses` is `None` when a backend does not maintain
    addresses yet (`PostgresCell`'s WP-2 shim, symmetric with `QueryOutcome.
    revisions`'s own `None` sentinel) -- distinct from `[]`, which means the
    backend does maintain them and this particular batch simply resolved no
    insert (every operation was an update/delete, or an upsert that
    resolved to update).
    """

    affected: int
    assigned_addresses: list[dict[str, Any]] | None = None
    # Phase 4 (design PHASE4_DURABLE_AUDIT_SINK_V1.md D-2/D-10): whether
    # this batch passed through the `DESTRUCTIVE_CONFIRMATION_V1` choke
    # (a confirmed `delete`) -- the fail-closed/buffer-class dispatch
    # point. `True` means the backend already durably recorded this batch
    # via its `audit_hook` pre-commit call; `DataService` must not also
    # enqueue it on the bounded buffer (D-10: at most one durable row per
    # operation).
    destructive: bool = False
    # Contract 1.7.0 (D-4, WP-2b): `committed` is `False` only for a
    # `dry_run` that reached the "would succeed" decision (rolled back at
    # `transact`'s own single tx-exit point, never a mid-loop branch) --
    # `True` for every real apply, exactly what `MutationResult.committed`
    # (contract) reports. `plan` is the deterministic token this batch's
    # own tx-exit point computed (D-4 (7)/S-a) -- present whenever a
    # caller supplied `plan_request` to `transact`, `None` otherwise
    # (`DataService.mutate_result` only ever surfaces it on a `dry_run`
    # response, D-4 (3): a real response echoes `None`, keeping its shape
    # byte-identical to pre-1.7.0 besides `committed`).
    committed: bool = True
    plan: str | None = None
    # Contract 1.7.0 (D-5 (1)(viii), ruling I-3/I-8, WP-2c): `True` only
    # for a result answered from a retained idempotency record -- nothing
    # below `transact`'s own idempotency lookup (target existence,
    # confirmation, precondition, execution) ran to produce it. `service.
    # py` reads this to skip writing a NEW audit event for the replay (a
    # resend never earns a second audit row of its own, D-5 (1)(v):
    # "監査行にkeyを載せない" -- the ONLY audit trail a resend has is the
    # original execution's own event, correlated through `request_id`).
    replayed: bool = False
    # Contract 1.7.0 (D-7, WP-2e): the `request_id` `MutationResult`
    # carries (`service.py`'s own `DataService.mutate_result` is a pure
    # passthrough of this field). For a genuine execution (real commit or
    # `dry_run`), this is THIS call's own `request_id` -- the same value
    # the audit event `_mutate_outcome` writes carries. For a REPLAY
    # (`replayed=True`), this is the ORIGINAL execution's own `request_id`,
    # read back from the idempotency record's payload (D-7 (3): "a
    # response returned from an idempotency record ... the original
    # execution's own, not a new one") -- never this resend's own `rid`,
    # which is used only for the resend's OWN, separate audit event.
    request_id: str | None = None


@dataclass(frozen=True)
class SchemaOutcome:
    """Contract 1.7.0 (D-4, WP-2b): `apply_schema`'s return shape -- the
    schema-side sibling of `MutationOutcome` above, reporting `committed`/
    `descriptor`/`plan` alongside `revision`. Returned uniformly, whether
    or not the request carried `dry_run`/`plan` (review round F-8,
    `{scratchpad}/rulings-r4.md`) -- every pre-1.7.0 caller of `apply_
    schema`/`DataService.schema` now reads `outcome.revision` in place of
    what used to be a bare `int`.

    `committed`: `False` only for a `dry_run` that reached the "would
    succeed" decision (rolled back at `apply_schema`'s own single
    tx-exit point); `True` for every real apply.
    `revision`: the schema revision this result reports -- the CURRENT
    (pre-apply) value for a dry run (D-4 (3), addendum 2 S-j: "not the
    revision the operation would establish"), the newly-established value
    for a committed real apply (identical to the pre-1.7.0 bare `int`).
    `descriptor`: the target entity's own descriptor -- as it would read
    afterwards, for a dry run that leaves the entity in place; `None` for
    a dry-run `drop_entity` (nothing to describe afterwards) and for
    every real (non-dry-run) apply (contract `SchemaOperationResult.
    descriptor` is optional either way; a real apply's response keeps its
    pre-1.7.0 shape besides `committed`, D-4 (3)'s own asymmetry with
    `assigned_addresses`).
    `plan`: the deterministic token this operation's own tx-exit point
    computed -- `None` unless `plan_request` was given to `apply_schema`;
    `DataService.schema` only ever surfaces it on a `dry_run` response.
    """

    committed: bool
    revision: int
    descriptor: dict[str, Any] | None = None
    plan: str | None = None
    # Contract 1.7.0 (D-5 (1)(viii), ruling I-3/I-8, WP-2c): see
    # `MutationOutcome.replayed`'s identical comment.
    replayed: bool = False
    # Contract 1.7.0 (D-7, WP-2e): see `MutationOutcome.request_id`'s
    # identical comment -- this call's own `request_id` for a genuine
    # execution (real commit or `dry_run`), the ORIGINAL execution's own
    # (read back from the idempotency record) for a replay.
    request_id: str | None = None
