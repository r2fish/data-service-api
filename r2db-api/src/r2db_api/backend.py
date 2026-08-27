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

from .limits import ResourceLimits
from .structured import ApplicationCell, Predicate


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
        deadline: float | None = None,
        clock: Callable[[], float] | None = None,
    ) -> list[dict[str, Any]]:
        """Return at most `page_size` rows, projected to `select`."""
        ...

    def transact(
        self,
        entity: str,
        operations: list[dict[str, Any]],
        limits: ResourceLimits,
        *,
        deadline: float | None = None,
        clock: Callable[[], float] | None = None,
    ) -> int:
        """Apply a batch of mutation operations as one atomic unit (D-5:
        one request maps to one transaction) and return the affected row
        count. Any operation failing rolls back the whole batch.
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
    ) -> int:
        """Apply one schema-changing operation and return the new schema
        revision. `developer` is the caller's already-authenticated
        authority (SI-03); a backend must reject when it is False even if
        every other input is well-formed.
        """
        ...

    def catalog(self) -> list[dict[str, Any]]:
        """List this application's entities and their known fields."""
        ...


# `ApplicationCell` is the reference/test-double implementation of
# `StorageBackend` (D-1: "InMemoryCell <- existing structured.py, kept as a
# test double"). This assertion makes that conformance a checked fact: it
# fails at import time -- and therefore fails the whole test suite -- the
# moment `ApplicationCell`'s call surface drifts from the protocol, instead
# of silently going stale as a comment would.
assert issubclass(ApplicationCell, StorageBackend), "ApplicationCell must conform to StorageBackend (design D-1)"

__all__ = ["StorageBackend"]
