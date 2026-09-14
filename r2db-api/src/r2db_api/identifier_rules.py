"""r2db identifier syntax and reserved-name rules: the identifier pattern
and length bound, plus reserved-prefix/reserved-name rejection for
entities, fields, and indexes (ST4).

This is a pure leaf: every check here is a closed-form test of an
identifier string against a compiled pattern, a fixed length bound, or a
fixed prefix/frozenset -- it opens no connection, reads no catalog, and
consults no request/limits/principal state. The choke points that decide
*when* an identifier-syntax check applies to a given request position
(`Predicate.validate`, `bind_mutation`, `bind_schema_operation`, and
`PostgresCell`'s own DDL layer, all in their own modules) remain outside
this leaf.
"""
from __future__ import annotations

import re

from .errors import fail, violation

IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
# PostgreSQL's own identifier limit, and the bound MitateDB-api already
# enforces (`^[a-z][a-z0-9_]{0,62}$`). This is a structural syntax policy on
# identifiers, not a deployment-tunable resource class from the contract's
# `limits.classes`, so it lives here as a constant rather than in
# ResourceLimits; the contract permits a stricter per-implementation
# identifier policy.
MAX_IDENTIFIER_LENGTH = 63

# Contract 1.1.0 (CCR-13, R2DB_CCR13_STORAGE_V1.md R-3): the server-assigned
# row address `id` and any implementation-internal name starting with this
# prefix (e.g. the invisible revision column `_r2db_revision`) are reserved.
# A client may never declare a field, entity, or index using either form --
# this is what keeps the reservation a checked, fail-closed property instead
# of a convention two backends could silently drift on (R-3, M-9: both cells
# share this exact policy; R-5 extends the `_r2db` prefix reservation to
# index names too -- WP-2 review minor (d)).
_RESERVED_PREFIX = "_r2db"


# WP-2e rework (audit-wp2e.md D-3, ruling L-3): `field` is now REQUIRED
# (never a default) on every identifier-syntax helper below -- the exact
# request-internal path (`errors.details_vocabulary.VALIDATION_FAILED.
# field`'s own convention, "/"-separated from the request body root, no
# leading "/") carrying the identifier under check, batch index included
# wherever the caller has one (`operations/<i>/...`). A REQUIRED keyword-
# only parameter (not a default of `None`/`"identifier"`) is deliberate:
# it makes forgetting to supply a real path a call-site TypeError, not a
# silently-wrong literal `"identifier"` that matches no request key (the
# exact D-3 finding this rework closes).
def validate_identifier(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value) or len(value) > MAX_IDENTIFIER_LENGTH:
        fail("IDENTIFIER_INVALID", "Identifier has an unsupported format.", details=violation("identifier_syntax", field=field))
    return value


def _reject_reserved_field(name: str, *, field: str) -> None:
    if name == "id" or name.startswith(_RESERVED_PREFIX):
        fail("IDENTIFIER_INVALID", "Identifier is reserved for internal use.", details=violation("identifier_syntax", field=field))


def _reject_reserved_prefix(name: str, *, field: str) -> None:
    """Prefix-only reservation, used for entity names and (WP-2 review
    minor (d)) index names -- unlike `_reject_reserved_field`, `id` itself
    is not reserved here (an entity or index literally named `id` does not
    collide with the per-row address column)."""
    if name.startswith(_RESERVED_PREFIX):
        fail("IDENTIFIER_INVALID", "Identifier is reserved for internal use.", details=violation("identifier_syntax", field=field))


# WP-2(b) review B-2 (major, supervisor ruling 2026-09-03 -- "義務として
# 実装する"): contract 1.4.0 `structured_operations.reserved_entity_names_
# note` (unconditional item 6) states "audit_events is reserved across
# implementations as an entity/collection name ... both peers already
# refuse this exact name defensively". That was true for MitateDB
# (`backend_sqlite._RESERVED` / `backend_postgres._RESERVED_EXACT`) but NOT
# for r2db-api before this fix -- `_reject_reserved_prefix` above only ever
# rejected the `_r2db` PREFIX, never this one exact name, so `create_entity`
# with `entity="audit_events"` was silently ACCEPTED. EXACT match only
# (never a prefix) -- an application legitimately owning e.g.
# "audit_events_archive" must not be blocked; the contract's own text names
# this one literal string, not a namespace.
_RESERVED_ENTITY_NAMES = frozenset({"audit_events"})


def _reject_reserved_entity_name(name: str, *, field: str) -> None:
    if name in _RESERVED_ENTITY_NAMES:
        fail("IDENTIFIER_INVALID", "Identifier is reserved for internal use.", details=violation("identifier_syntax", field=field))
