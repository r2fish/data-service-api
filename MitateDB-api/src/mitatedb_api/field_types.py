"""Contract field-type vocabulary and declared-type value validation
(Phase 6 WP-3, design docs/design/PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md
D-3, G3).

Contract 1.6.0's `field_type` enum gains a seventh member, `json` (any
JSON value); this module is the ONE place that vocabulary lives on this
peer, and the ONE place a value is checked against a DECLARED member of it
-- the `_prepare_values`/`_bind_filters` choke point in `cell.py` (R-2/B-1
style: this is the same kind of backend-independent, single-point
validation `r2db_api.structured._check_type` already is for that peer,
independently arrived at here, R-2's own closing paragraph). Backend
domain checks (`backend_postgres.py`) stay as defence-in-depth UNDER this
layer, never instead of it.

``CONTRACT_TYPES`` is this peer's own copy of the contract's
``schemas.SchemaOperationRequest.properties.field_type`` enum -- kept as a
literal tuple (not read from the packaged contract at runtime) because it
is also this module's own registry vocabulary, load-bearing for the SQL
this peer writes (a CHECK constraint) -- `tests/test_foundation.py`'s
sibling contract-vocabulary pin tests (e.g. `test_conformance_public_
surface_coverage.py`) are what catches this copy drifting from the
contract itself.
"""
from __future__ import annotations

from typing import Any

from .errors import ValidationError

#: Contract 1.6.0 `field_type` enum (`schemas.SchemaOperationRequest.
#: properties.field_type.enum` / `definitions.EntityDescriptor.properties.
#: field_types` values) -- 7 members, `json` the newest.
CONTRACT_TYPES = ("string", "integer", "number", "boolean", "object", "array", "json")

#: This peer's own foundation/physical vocabulary (`cell._FIELD_TYPE_
#: VOCABULARY`) that a contract type maps onto for DDL purposes. `object`/
#: `array`/`json` all share the physical `json` (TEXT) column -- the
#: declared-type REGISTRY (not this map, and not the physical column) is
#: what recovers which of the three a field actually is (design §1.5
#: finding 1b/2).
CONTRACT_TYPE_TO_FOUNDATION_TYPE = {
    "string": "text",
    "integer": "integer",
    "number": "real",
    "boolean": "boolean",
    "object": "json",
    "array": "json",
    "json": "json",
}

#: The inverse, used ONLY as the derived/default declared contract type
#: for a field created through a pre-1.6.0-shaped call that names a
#: FOUNDATION type directly and supplies no explicit contract type
#: (`cell.ApplicationCell.create_collection`/`add_field`'s own direct
#: callers -- this repository's own tests, the in-process conformance
#: adapter's `create_collection`). `object`/`array` cannot be recovered
#: this way (both collapse to foundation `json`); a caller that needs
#: that distinction must supply an explicit contract type instead. This
#: is the SAME backfill rule the `0006` upgrade script applies to
#: existing columns (design §1.5 finding 2a) -- one table, two use sites.
FOUNDATION_TYPE_TO_CONTRACT_TYPE = {
    "text": "string",
    "integer": "integer",
    "real": "number",
    "boolean": "boolean",
    "json": "json",
}


def check_declared_value(value: Any, declared_type: "str | None") -> None:
    """The cell-layer choke point itself (design G3): raises `errors.
    ValidationError` when `value` does not match `declared_type` (one of
    `CONTRACT_TYPES`). `declared_type` of `None` (no registry row -- must
    not occur for a field this peer itself created after this WP, but
    tolerated defensively) skips the check entirely, matching this
    foundation's own pre-D-3 behaviour for that field. `json` never
    rejects: it is "any JSON value", and every value reaching this point
    has ALREADY passed `ApplicationCell._normalize_value`'s own upstream
    shape check (str/int/float/bool/None/dict/list only), so it is
    already JSON-representable by construction.

    `bool` is checked before `int` in every branch that needs it -- in
    Python, `isinstance(True, int)` is `True`, so an unguarded `integer`/
    `number` check would silently accept a `bool` (mirrors r2db-api's own
    `structured._check_type`, independently applied here).
    """
    if declared_type is None or declared_type == "json":
        return
    # M-5 precedent (`backend_postgres._validate_value_domain`): SQL NULL
    # is valid for any column regardless of its declared type -- this
    # foundation defines no NOT NULL constraint anywhere
    # (`migrations/0003_provision_application.sql`), so a value that
    # normalized to `None` must never be rejected here, for any declared
    # type.
    if value is None:
        return
    if declared_type == "string":
        ok = isinstance(value, str)
    elif declared_type == "integer":
        ok = isinstance(value, int) and not isinstance(value, bool)
    elif declared_type == "number":
        ok = isinstance(value, (int, float)) and not isinstance(value, bool)
    elif declared_type == "boolean":
        ok = isinstance(value, bool)
    elif declared_type == "object":
        ok = isinstance(value, dict)
    elif declared_type == "array":
        ok = isinstance(value, list)
    else:
        raise ValidationError(f"unknown declared field type {declared_type!r}")
    if not ok:
        raise ValidationError(f"value does not match the declared field type {declared_type!r}")
