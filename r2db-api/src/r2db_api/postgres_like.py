"""Pure escaping for PostgreSQL literal-substring matching."""
from __future__ import annotations


def _escape_like_literal(value: str) -> str:
    """Q-2 (案i): `contains` is literal substring containment -- no
    character of the value is ever interpreted as a `LIKE` wildcard. `\\`
    must be escaped first, before `%`/`_`, so a value already containing a
    backslash does not have that backslash re-interpreted as escaping the
    `%`/`_` markers this function itself inserts.
    """
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
