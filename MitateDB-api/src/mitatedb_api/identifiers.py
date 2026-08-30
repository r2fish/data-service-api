"""Validation for identifiers used by structured storage operations.

R-3 (docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md, WP-1 backend seam):
the syntax allowlist below is shared by every backend (SQLite and
PostgreSQL alike -- both engines' own identifier grammars are a strict
subset of what this regex allows, so validating against it before any
backend ever sees the name is safe for either). The RESERVED-name set is
backend-specific (SQLite's own `sqlite_sequence` means nothing to
PostgreSQL, and PostgreSQL's own `pg_`-prefixed catalog namespace means
nothing to SQLite) and therefore lives on each backend class instead (see
`backend_sqlite.SQLiteBackend.check_reserved` /
`backend_postgres.PostgresBackend.check_reserved`), not here.
"""

import re

from .errors import ValidationError

_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{0,62}$")


def validate_identifier(value, label="identifier"):
    """Syntax-only check (the allowlist every backend shares). Does not
    check backend-specific reserved names -- callers that need that must
    also call the active backend's own ``check_reserved`` (see
    ``cell.ApplicationCell._identifier``, the single place both checks are
    always applied together for every identifier this foundation accepts).
    """
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValidationError("invalid " + label)
    return value


def quote_identifier(value, label="identifier"):
    """SQLite-style ANSI double-quote composition. This is used only by
    the SQLite backend: PostgreSQL statements are never assembled by
    string-embedding a quoted identifier (R-2 choke point) -- the
    PostgreSQL backend composes identifiers exclusively via
    ``psycopg.sql.Identifier`` instead, after the same syntax check plus
    its own live-catalog check.
    """
    return '"' + validate_identifier(value, label).replace('"', '""') + '"'
