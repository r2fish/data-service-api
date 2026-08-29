"""Finite, deployment-configurable resource bounds."""

from dataclasses import dataclass
import os

from .errors import ResourceLimitError, ValidationError


@dataclass(frozen=True)
class FoundationConfig:
    """Bounds used by the local foundation.

    These are deliberately finite defaults, not a final public-contract
    number. A future HTTP adapter may expose the profile through the common
    capability-discovery contract.
    """

    max_batch_items: int = 100
    max_result_rows: int = 500
    max_fields: int = 64
    max_filter_terms: int = 32
    max_request_bytes: int = 1_048_576
    max_schema_objects: int = 128

    @classmethod
    def from_env(cls, environ=None):
        values = dict(os.environ if environ is None else environ)
        names = {
            "max_batch_items": "MITATEDB_MAX_BATCH_ITEMS",
            "max_result_rows": "MITATEDB_MAX_RESULT_ROWS",
            "max_fields": "MITATEDB_MAX_FIELDS",
            "max_filter_terms": "MITATEDB_MAX_FILTER_TERMS",
            "max_request_bytes": "MITATEDB_MAX_REQUEST_BYTES",
            "max_schema_objects": "MITATEDB_MAX_SCHEMA_OBJECTS",
        }
        parsed = {}
        for field, name in names.items():
            raw = values.get(name)
            if raw is None:
                continue
            try:
                number = int(raw)
            except (TypeError, ValueError):
                raise ValidationError("invalid resource limit")
            if number <= 0:
                raise ValidationError("resource limits must be positive")
            parsed[field] = number
        return cls(**parsed)

    def validate_request_size(self, size):
        """Reject a body before parsing or dispatching it."""
        if not isinstance(size, int) or size < 0 or size > self.max_request_bytes:
            # Clean 1:1 correspondence with contract `limits.classes`:
            # this is the same finite byte bound `capabilities().limits`
            # publishes as `request_bytes` (WP-5 Q1-D7(B)).
            raise ResourceLimitError("request size limit exceeded", limit_class="request_bytes")
