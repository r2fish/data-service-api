"""Pure domain checks for values sent to the PostgreSQL backend."""
from __future__ import annotations

from .errors import ValidationError, observed_type_of, violation


_INT_DOMAIN_RANGES = {
    "int32": (-2147483648, 2147483647),
    "int64": (-9223372036854775808, 9223372036854775807),
}


def _check_domain(value, domain, *, field=None, declared_type=None):
    """Validate a resolved PostgreSQL value domain without database I/O."""
    if domain in ("string", "object", "array", "json"):
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
