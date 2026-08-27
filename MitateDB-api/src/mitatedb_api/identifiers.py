"""Validation for identifiers used by structured storage operations."""

import re

from .errors import ValidationError

_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
_RESERVED = {"sqlite_sequence", "audit_events"}


def validate_identifier(value, label="identifier"):
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValidationError("invalid " + label)
    if value in _RESERVED:
        raise ValidationError("reserved " + label)
    return value


def quote_identifier(value, label="identifier"):
    return '"' + validate_identifier(value, label).replace('"', '""') + '"'
