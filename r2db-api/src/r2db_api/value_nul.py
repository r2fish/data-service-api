"""Pure detection of NUL characters in JSON-compatible values."""
from __future__ import annotations

from typing import Any


def _contains_nul(value: Any) -> bool:
    """`True` if `value` (or, recursively, any string nested inside a
    dict/list) contains a U+0000 (NUL) character. PostgreSQL's `text`/
    `jsonb` storage cannot hold a NUL byte at all (`invalid byte sequence
    for encoding`/`unsupported Unicode escape sequence`) -- another
    decisive client bug (R-7 addendum, WP-3 review blocker-2) that must be
    refused deterministically here, not discovered as a database error.
    """
    if isinstance(value, str):
        return "\x00" in value
    if isinstance(value, dict):
        return any(_contains_nul(key) or _contains_nul(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_nul(item) for item in value)
    return False
