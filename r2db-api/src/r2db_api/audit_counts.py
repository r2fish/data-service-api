"""Pure audit-event count representation helpers."""
from __future__ import annotations


def _coalesced_count(occurrences: int) -> int | None:
    """Represent singleton events as an absent count, never literal one."""
    return occurrences if occurrences >= 2 else None
