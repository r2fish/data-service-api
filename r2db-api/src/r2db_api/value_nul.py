"""Pure detection of NUL characters in JSON-compatible values."""
from __future__ import annotations

from typing import Any


def _contains_nul(value: Any) -> bool:
    """Return whether a string, dict, or list recursively contains U+0000."""
    if isinstance(value, str):
        return "\x00" in value
    if isinstance(value, dict):
        return any(_contains_nul(key) or _contains_nul(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_nul(item) for item in value)
    return False
