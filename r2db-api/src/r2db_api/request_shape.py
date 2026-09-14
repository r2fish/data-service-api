"""r2db-api query/mutation request-shape checks for `DataService._query_
outcome`/`_mutate_outcome` (SV3).

A pure leaf: checks the shape of a query or mutation request from its own
explicit arguments only, raising through `.errors.fail` on a violation and
returning nothing on success."""
from __future__ import annotations

from typing import Any

from .errors import fail, observed_type_of, violation


def _check_query_request_shape(select: list[str], where: list[dict[str, Any]] | None, page_size: int, order_by: list[dict[str, Any]] | None, cursor: str | None) -> None:
    if not isinstance(select, list) or not isinstance(page_size, int) or isinstance(page_size, bool):
        fail("VALIDATION_FAILED", "Projection and page size have invalid types.", details=violation("request_schema"))
    if where is not None and not isinstance(where, list):
        fail("VALIDATION_FAILED", "Filter must be a list.", details=violation("request_schema", field="where", declared_type="array", observed_type=observed_type_of(where)))
    if order_by is not None and not isinstance(order_by, list):
        fail("VALIDATION_FAILED", "order_by must be a list.", details=violation("request_schema", field="order_by", declared_type="array", observed_type=observed_type_of(order_by)))
    if cursor is not None and not isinstance(cursor, str):
        fail("VALIDATION_FAILED", "Cursor must be a string.", details=violation("request_schema", field="cursor", declared_type="string", observed_type=observed_type_of(cursor)))


def _check_mutation_request_shape(transaction: str | None, operations: list[dict[str, Any]]) -> None:
    # `transaction` is never a contract-level *default* -- `None` here means the caller's own request object never carried the key at all (both `http.post_mutate` and the in-process port omit the kwarg rather than resolving it to `"atomic"` before this call). `resolved_transaction` is used for every
    # behavioural decision (the capability gate below); the
    # RAW `transaction` value (still `None` when omitted) is
    # what `plan_request` below (in `service.py`) reflects, so a request that
    # carried `transaction: "atomic"` explicitly digests
    # differently from one that omitted the key entirely, even
    # though both behave identically otherwise.
    # history: CH-0126
    resolved_transaction = transaction if transaction is not None else "atomic"
    if resolved_transaction != "atomic":
        fail("CAPABILITY_UNSUPPORTED", "This foundation exposes atomic transactions only.", details=violation("capability", field="transaction"))
    if not isinstance(operations, list):
        fail("VALIDATION_FAILED", "Mutations must be a list.", details=violation("request_schema", field="operations"))
