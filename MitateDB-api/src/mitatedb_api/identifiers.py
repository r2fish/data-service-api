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

    Phase 9 WP-3e (design D-3 (6), work order completion condition 3'):
    this peer never emits the common contract's `IDENTIFIER_INVALID` code
    at all (L9-2a, unchanged by this WP) -- every identifier syntax
    violation this function raises stays `VALIDATION_FAILED`, but now
    carries the SAME `violated_declaration: "identifier_syntax"` word
    `IDENTIFIER_INVALID` would have carried on r2db-api. `field` is
    `label` itself -- this call's own caller already names the position
    the identifier occupies (`"collection"`/`"field"`/`"application_id"`,
    the bare, request-relative words `cell.py::ApplicationCell._identifier`
    already passes at every call site) rather than a synthesized generic
    literal -- a deliberate, disclosed difference from r2db-api's own
    choice for `IDENTIFIER_INVALID` (`structured.validate_identifier`,
    which always carries the fixed literal `field="identifier"`
    regardless of context): both are conformant (the design fixes only
    the closed vocabulary and the path-format rule, not which specific
    position string a peer chooses), but this peer's choice keeps the
    per-call-site position information r2db-api's own simplification
    discards. Reported in the WP-3e completion report as a two-sided
    disclosure (両論)."""
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValidationError(
            "invalid " + label,
            details={"violated_declaration": "identifier_syntax", "field": label},
        )
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
