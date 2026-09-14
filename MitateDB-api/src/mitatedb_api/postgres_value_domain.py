"""Pure domain checks for values sent to the PostgreSQL backend."""
from __future__ import annotations

from .errors import ValidationError, observed_type_of, violation


_INT_DOMAIN_RANGES = {
    "int32": (-2147483648, 2147483647),
    "int64": (-9223372036854775808, 9223372036854775807),
}


def _check_domain(value, domain, *, field=None, declared_type=None):
    """B-1 (i): the actual value-domain gate, a pure function (m-8).
    Runs BEFORE any statement reaches PostgreSQL, so a type-mismatched
    value never gets the chance to raise `InvalidTextRepresentation`/
    `NumericValueOutOfRange`/etc. at the driver level. Every rejection
    message here starts with "value" and says "does not match"/"is out of
    range" -- deliberately worded differently from the layer (ii)
    backstop's own generic "storage backend rejected the request" (every
    DML/DDL method's final `except psycopg.Error` branch, in `backend_
    postgres.py`), so a test can tell WHICH layer actually caught a given
    case (m-8 (ii)).

    `field`/`declared_type`: same 追補 4 O-2 threading as `_validate_value_
    domain` above (in `backend_postgres.py`; this is that function's own
    callee, `field`/`declared_type` pass straight through unchanged)."""
    if domain in ("string", "object", "array", "json"):
        # See `_TEXT_DOMAIN_BY_DECLARED_TYPE`'s own comment (in
        # `backend_postgres.py`): the real object-vs-array-vs-json shape
        # check already ran at the cell layer (design G3) -- by this
        # point every one of these four declared types is physically a
        # plain `str` (JSON text for the three non-`string` members).
        if not isinstance(value, str):
            raise ValidationError(
                "value does not match the declared field type",
                details=violation("field_type", field=field, declared_type=declared_type, observed_type=observed_type_of(value)),
            )
        return value
    if domain in _INT_DOMAIN_RANGES:
        if not isinstance(value, int):
            raise ValidationError(
                "value does not match the declared field type",
                details=violation("field_type", field=field, declared_type=declared_type, observed_type=observed_type_of(value)),
            )
        low, high = _INT_DOMAIN_RANGES[domain]
        if not (low <= value <= high):
            raise ValidationError(
                "value is out of range for the declared field type",
                details=violation("field_type", field=field, declared_type=declared_type, observed_type=observed_type_of(value)),
            )
        return value
    if domain == "float":
        if not isinstance(value, (int, float)):
            raise ValidationError(
                "value does not match the declared field type",
                details=violation("field_type", field=field, declared_type=declared_type, observed_type=observed_type_of(value)),
            )
        return float(value)
    return value
