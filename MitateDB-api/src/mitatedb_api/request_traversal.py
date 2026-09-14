"""Pure normalization helpers for request-structure traversal."""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any


def _as_traversable(item: Any) -> Any:
    """Phase 8 WP-1a (design D-1): `_measure_request_bytes`/`_check_
    operation_depth` below (in `request_limits.py`) traverse the JSON-safe request
    structures this module's own gate (`cell.py`) builds internally (a
    plain dict of the method's own arguments) -- but those arguments
    legitimately carry this module's own (`cell.py`) `Filter` frozen
    dataclass (both `read`/`update`/`delete`/`transact` reach the gate
    with `filters` already bound to `Filter` instances, never plain
    dicts -- see `http.py::_predicate_to_filter`/the in-process
    conformance adapter, both of which construct `Filter` objects before
    calling into this module (`cell.py`)). A generic
    dataclass -> dict conversion here (rather than a `Filter`-specific
    special case) keeps both traversal functions correct for any
    dataclass value a future request shape might carry, with no second,
    type-specific branch to keep in sync."""
    if is_dataclass(item) and not isinstance(item, type):
        return asdict(item)
    return item
