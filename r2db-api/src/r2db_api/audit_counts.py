"""Pure audit-event count representation helpers."""
from __future__ import annotations


# Phase 4 WP-2(b) review B-1 (major, supervisor ruling 2026-09-03): the
# durable `count` column's own semantics -- "the number of occurrences this
# ONE row represents; when that number is 1, the column is absent (NULL)"
# (contract `audit.query_event_fields_note`: "present only on an event
# representing more than one coalesced occurrence, absent -- never zero or
# one -- otherwise"). Every call site that can ever pass a real integer here
# (in `service.py`) -- `_DenialCoalescer`'s aggregate (repeat-count) row --
# routes the raw tally through this one function instead of writing it
# verbatim, so "exactly one repeat" always renders as an ordinary
# NULL-count row, never a literal `count=1` a reader would have to
# special-case.
def _coalesced_count(occurrences: int) -> int | None:
    return occurrences if occurrences >= 2 else None
