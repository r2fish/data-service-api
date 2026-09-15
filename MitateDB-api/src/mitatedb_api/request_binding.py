"""MitateDB request-value normalization and predicate-value checking (CE6
の一部).

A pure leaf: `_check_predicate_value` wraps `field_types.check_declared_
value` with a predicate's own request-relative value path;
`_normalize_value`/`_normalize_value_for_storage` shape-check and
canonicalize a value for the active backend's own `encode_value` to
finish. All three are deterministic functions over already-passed
arguments, consulting no connection, catalog, clock, principal, or
transaction -- `ApplicationCell` (`cell.py`) keeps the delegation
attributes (every `self.` call site is unchanged) and everything
that reads the backend catalog (`_bind_filters`, `_prepare_values`, and
the other CE6 methods) remains in `cell.py`.
"""
from __future__ import annotations

import json

from .errors import ValidationError, violation
from .field_types import check_declared_value


def _check_predicate_value(value, declared_type, value_path):
    """Phase 9 WP-3e (design D-3 (2)): `field_types.check_declared_
    value` (the SAME choke point `_prepare_values`'s write side uses,
    `constraints=None` here -- D-2 (2): "query の predicate 値は
    enum を検査しない") has no request-path context of its own; this
    wrapper attaches the predicate's own request-relative VALUE path
    (WP-3e rework T2, 追補 M-4: `where/<i>/value`, `_bind_filters`'s
    own caller-supplied path -- never the bare field name, which
    names a POSITION, not the value being checked) the same way
    `_prepare_values`'s own `except ValidationError` clause does for
    the write side."""
    try:
        check_declared_value(value, declared_type)
    except ValidationError as exc:
        details = getattr(exc, "details", None)
        if isinstance(details, dict) and "field" not in details:
            details["field"] = value_path
        raise


def _normalize_value(value):
    """Backend-independent shape check/normalization (R-3): a
    dict/list value becomes canonical JSON text; every other accepted
    Python type (`bool`/`str`/`int`/`float`/`None`) passes through
    unchanged for the active backend's own `encode_value` to finish
    (backend-specific bind encoding AND backend-specific value-domain
    validation, e.g. PostgreSQL's embedded-NUL rejection -- see
    `backend_postgres.PostgresBackend.encode_value`)."""
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"), sort_keys=True)
    if isinstance(value, (bool, str, int, float)) or value is None:
        return value
    # WP-3e rework T1 (追補 L-1): unreachable in practice -- a JSON
    # request body decodes only into dict/list/bool/str/int/float/
    # None, exactly the accepted set above -- kept `request_schema`
    # (no `field`: this static method has no request-relative path
    # of its own, `_prepare_values`'s own catch clause is what
    # attaches one for its own `field_type` choke point, D-2 (3))
    # rather than removed, matching this class's own defensive style (`ApplicationCell`, in `cell.py`).
    raise ValidationError(
        "unsupported value",
        details=violation("request_schema"),
    )


def _normalize_value_for_storage(value, declared_type):
    """Phase 6 WP-3 (design D-3, F2): `declared_type` (one of
    `field_types.CONTRACT_TYPES`, or `None`) has ALREADY been checked
    against `value` by `field_types.check_declared_value` before this
    runs. For `object`/`array`/`json` -- the three contract types this
    peer stores as physical `json` (TEXT) -- every value (not only
    dict/list; `str`/`int`/`float`/`bool` too) becomes canonical JSON
    text, so the read side can UNCONDITIONALLY `json.loads()` it back
    and recover the exact original value (a plain string written to a
    `json`-declared field must round-trip as that same string, not
    get confused with a `string`-declared field's own literal text).
    `None` (SQL NULL) is never encoded -- NULL is valid for any
    declared type (`field_types.check_declared_value`'s own identical
    precedent) and stays NULL, never becomes the JSON text `"null"`.
    Every other declared type (`string`/`integer`/`number`/`boolean`,
    or `None` -- no registry row, backward compatible) falls back to
    `_normalize_value` unchanged."""
    if value is not None and declared_type in ("object", "array", "json"):
        return json.dumps(value, separators=(",", ":"), sort_keys=True)
    return _normalize_value(value)
