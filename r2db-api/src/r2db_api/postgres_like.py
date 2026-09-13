"""Pure escaping for PostgreSQL literal-substring matching."""
from __future__ import annotations


def _escape_like_literal(value: str) -> str:
    """Escape backslash before LIKE's percent and underscore wildcards."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
