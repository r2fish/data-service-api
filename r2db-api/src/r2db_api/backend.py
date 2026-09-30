"""`StorageBackend` protocol (design D-1).

`DataService` (owned elsewhere -- not modified by this module) calls exactly
four methods on whatever cell it holds per application: `query`, `transact`,
`apply_schema`, and `catalog`. This module names that call surface as an
explicit `Protocol` so a second implementation (`r2db_api.postgres.PostgresCell`)
can be swapped in without `DataService` changing at all.

The protocol intentionally matches `ApplicationCell` (`r2db_api.structured`)
signature-for-signature; `ApplicationCell` is declared conforming below via
a runtime `issubclass` assertion, so import-time drift between the two is a
hard failure rather than an informal claim.

This module does not itself validate anything. The validation/planning
boundary that every backend must cross (identifier syntax, operator
allowlist, mutation shape, destructive confirmation, limit application) lives
in `r2db_api.structured` and is shared by every backend -- see the module
docstring there ("Shared validation/planning boundary"). A backend with its
own private copy of that logic is exactly the split-brain design D-1 forbids.
"""
from __future__ import annotations

from typing import Any, Callable, Protocol, runtime_checkable

from .audit_hook import ApplicationAuditHook
from .limits import ResourceLimits
from .structured import ApplicationCell, MutationOutcome, Predicate, QueryOutcome, SchemaOutcome

# `QueryOutcome`/`MutationOutcome`/`SchemaOutcome` (CCR-13, docs/design/
# R2DB_CCR13_STORAGE_V1.md §3; `SchemaOutcome` added by contract 1.7.0 D-4,
# WP-2b) are defined in `structured.py` (now in `storage_outcomes.py`) -- the module that already owns the
# shared validation/planning boundary and is where `ApplicationCell` actually
# constructs them -- and re-exported here so this module remains the single
# place that names the full `StorageBackend` call surface, inputs and
# outputs alike. (Defining them here and importing them into `structured.py`
# instead would create a import cycle: this module already imports
# `ApplicationCell` from `structured.py` at module load time.)


@runtime_checkable
class StorageBackend(Protocol):
    """One application's storage, behind the validated-plan boundary.

    Every method receives already-validated inputs from `DataService`
    (`entity`/`select`/`where` etc. have already passed through
    `r2db_api.structured`'s shared validators, or -- for `transact`/
    `apply_schema`, whose per-item/per-operation shape can only be checked
    once the backend's own catalog is known -- the backend is expected to
    call those shared validators itself before touching storage). A
    conforming backend must not accept a raw SQL/command string anywhere in
    this surface.
    """

    def query(
        self,
        entity: str,
        *,
        select: list[str],
        where: list[Predicate],
        page_size: int,
        limits: ResourceLimits,
        order_by: list[dict[str, Any]] | None = None,
        cursor: str | None = None,
        deadline: float | None = None,
        clock: Callable[[], float] | None = None,
    ) -> QueryOutcome:
        """Return at most `page_size` rows, projected to `select`, plus
        (CCR-13) their revisions and pagination continuation. `order_by`/
        `cursor` are optional (a backend that does not implement them yet
        may reject a non-None value with `CAPABILITY_UNSUPPORTED`).
        """
        ...

    def transact(
        self,
        entity: str,
        operations: list[dict[str, Any]],
        limits: ResourceLimits,
        *,
        deadline: float | None = None,
        clock: Callable[[], float] | None = None,
        audit_hook: ApplicationAuditHook | None = None,
        dry_run: bool = False,
        plan: str | None = None,
        plan_request: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        request_id: str | None = None,
    ) -> MutationOutcome:
        """Apply a batch of mutation operations as one atomic unit (D-5:
        one request maps to one transaction) and return the affected row
        count, plus (CCR-13) any addresses resolved for insert. Any
        operation failing rolls back the whole batch.

        Phase 4 (design PHASE4_DURABLE_AUDIT_SINK_V1.md D-2/D-10):
        `audit_hook`, when given, is called exactly once for every real
        batch (a `dry_run` never reaches it) -- as the LAST thing this
        method does before its own commit point, whether or not the batch
        passed through the `DESTRUCTIVE_CONFIRMATION_V1` choke.
        `MutationOutcome.destructive` still reports whether it did (a
        `delete` operation's `require_destructive_confirmation` call did
        not raise), and the hook's own `fired` flag tells the caller
        (`DataService`) that this method already durably recorded the batch
        (D-10: at most one durable row per operation). See
        `audit_hook.py` for the full call contract (`pre_commit`/`commit_
        failed`, rollback-on-raise, error-row rule).

        `dry_run`/`plan`/`plan_request` (contract 1.7.0, D-4, WP-2b): a
        backend decides commit vs. rollback at a SINGLE tx-exit point,
        after every operation in the batch has tentatively succeeded, not
        mid-batch -- `dry_run` walks every gate a real request would (no
        early-out) and then rolls back instead of committing, leaving no
        externally visible state change (no row, no revision, and no
        audit event: `audit_hook` is never called at all for a `dry_run`
        -- not merely built and left uncalled -- so `caller` must pass
        `audit_hook=None` itself whenever `dry_run` is true). `plan`,
        when given, is verified against a token this same tx-exit point
        recomputes from `plan_request` (the contract-level request object,
        never a raw body) and the Application's own current schema
        revision; a mismatch is `PRECONDITION_FAILED`. A caller presenting
        neither `dry_run` nor `plan` sees behaviour identical to before
        this version.
        """
        ...

    def apply_schema(
        self,
        operation: dict[str, Any],
        *,
        developer: bool,
        limits: ResourceLimits,
        deadline: float | None = None,
        clock: Callable[[], float] | None = None,
        audit_hook: ApplicationAuditHook | None = None,
        dry_run: bool = False,
        plan: str | None = None,
        plan_request: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        request_id: str | None = None,
    ) -> SchemaOutcome:
        """Apply one schema-changing operation and return a `SchemaOutcome`
        (`.committed`/`.revision`/`.descriptor`/`.plan`). `developer` is
        the caller's already-authenticated authority (SI-03); a backend
        must reject when it is False even if every other input is
        well-formed.

        Phase 4 (design PHASE4_DURABLE_AUDIT_SINK_V1.md D-2): every schema
        operation is fail-closed class (D-2's normative rule, item 2 --
        unconditional, unlike `transact`'s confirmation-choke gate), so
        `audit_hook`, when given, is always called as the last thing this
        method does before its own commit point. See `audit_hook.py` for
        the full call contract.

        `dry_run`/`plan`/`plan_request` (contract 1.7.0, D-4, WP-2b):
        identical single-tx-exit-point discipline to `transact` above --
        `dry_run` rolls back instead of committing (`schema_revision` is
        never advanced, `audit_hook` is never called), and `.revision` on
        a `dry_run` outcome is the revision as it stood when the request
        was decided, never the value the operation would establish
        (addendum 2 S-j; `.descriptor` reports the entity as it WOULD
        read afterwards). `plan` is verified the same way `transact`
        verifies it. Every caller returns `SchemaOutcome` uniformly --
        review round F-8 (`{scratchpad}/rulings-r4.md`): a bare `int`
        return, conditioned on whether the SAME request happened to carry
        a `plan`, is not this protocol's shape. `DataService.schema`
        (`service.py`) is a pure passthrough of this return value and,
        since F-8, also always returns `SchemaOutcome` -- WP-2b 監査 N-7
        (`{scratchpad}/audit-wp2b.md`): there is no remaining pre-1.7.0
        bare-`int` surface anywhere on that call, at this boundary or
        `DataService`'s own; every pre-1.7.0 direct caller now reads
        `.revision` off the `SchemaOutcome` instead of comparing the
        result itself to an `int`.
        """
        ...

    def catalog(self, limits: ResourceLimits | None = None) -> list[dict[str, Any]]:
        """List this application's entities and their known fields."""
        ...


# `ApplicationCell` is the reference/test-double implementation of
# `StorageBackend` (D-1: "InMemoryCell <- existing structured.py, kept as a
# test double"). This assertion makes that conformance a checked fact: it
# fails at import time -- and therefore fails the whole test suite -- the
# moment `ApplicationCell`'s call surface drifts from the protocol, instead
# of silently going stale as a comment would.
assert issubclass(ApplicationCell, StorageBackend), "ApplicationCell must conform to StorageBackend (design D-1)"

__all__ = ["StorageBackend", "QueryOutcome", "MutationOutcome"]
