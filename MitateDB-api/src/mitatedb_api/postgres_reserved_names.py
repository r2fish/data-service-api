"""Pure PostgreSQL reserved-name checks."""
from __future__ import annotations

from .errors import ValidationError, violation

# R-3 (design v1.1 §0/R-4 WP-0 m-7): backend-specific reserved names.
# `audit_events` mirrors the SQLite backend's own defensive reservation
# (against a future local audit-table name collision); the `pg_` PREFIX
# rule is PostgreSQL-specific -- every name PostgreSQL's own system
# catalog uses starts with it (`pg_class`, `pg_attribute`, ...), and it is
# not expressible as a plain set-membership check, which is why
# `check_reserved` is a method rather than a published `frozenset` (unlike
# the exact-match-only SQLite backend).
_RESERVED_EXACT = frozenset({"audit_events"})
_RESERVED_PREFIX = "pg_"


def _check_reserved_name(value, label):
    if value in _RESERVED_EXACT or value.startswith(_RESERVED_PREFIX):
        raise ValidationError(
            "reserved " + label,
            details=violation("identifier_syntax", field=label),
        )
