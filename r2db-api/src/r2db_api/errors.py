"""Safe public errors; internal exceptions are deliberately not serialized."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FoundationError(Exception):
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    status: int = 400

    def __post_init__(self) -> None:
        super().__init__(self.message)

    def problem(self, request_id: str = "") -> dict[str, Any]:
        return {"type": "https://example.invalid/problems/" + self.code.lower(), "code": self.code, "message": self.message, "request_id": request_id, "details": self.details}


def fail(code: str, message: str, *, status: int = 400, details: dict[str, Any] | None = None) -> None:
    raise FoundationError(code, message, details or {}, status)


# --------------------------------------------------------------------------
# Contract 1.7.0 (D-3, WP-2e): `errors.details_vocabulary`'s 4-key form
# (`violated_declaration`/`field`/`declared_type`/`observed_type`) is built
# at every choke-point / request-shape-layer `fail()` call site through this
# one helper, never assembled ad hoc at each site -- so the "omit the key
# rather than carry a null placeholder" rule (D-3 (4)) can never drift
# between call sites. Backend-layer defence-in-depth `fail()` calls
# (D-3 (5), `errors.details_vocabulary.layer_rule`) do not use this helper
# and pass no `details` at all (or a details dict outside this vocabulary,
# e.g. `LIMIT_EXCEEDED.limit_class`).
# --------------------------------------------------------------------------


def violation(
    violated_declaration: str,
    *,
    field: str | None = None,
    declared_type: str | None = None,
    observed_type: str | None = None,
) -> dict[str, Any]:
    """Build a `details` dict using exactly the 4 keys `errors.
    details_vocabulary` names for `VALIDATION_FAILED`/`IDENTIFIER_INVALID`/
    `CAPABILITY_UNSUPPORTED` -- omitting any key whose value is `None`
    rather than carrying it as an explicit null (the required-key rules,
    D-3 (4), are stated as key ABSENCE/PRESENCE, not as a null value)."""
    details: dict[str, Any] = {"violated_declaration": violated_declaration}
    if field is not None:
        details["field"] = field
    if declared_type is not None:
        details["declared_type"] = declared_type
    if observed_type is not None:
        details["observed_type"] = observed_type
    return details


def observed_type_of(value: Any) -> str:
    """The `errors.details_vocabulary` `observed_type` vocabulary word for
    a JSON-decoded Python value -- `string`/`integer`/`number`/`boolean`/
    `object`/`array`/`null`. `bool` is checked before `int` (a Python
    `bool` is an `int` subclass); a request that omits a value entirely is
    `"absent"`, named explicitly at each such call site rather than through
    this function (there is no absent *value* to inspect)."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "string"  # pragma: no cover - unreachable for JSON-decoded input
