"""Pure normalization helpers for request-structure traversal."""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any


def _as_traversable(item: Any) -> Any:
    """Convert dataclass instances to dictionaries for generic traversal."""
    if is_dataclass(item) and not isinstance(item, type):
        return asdict(item)
    return item
