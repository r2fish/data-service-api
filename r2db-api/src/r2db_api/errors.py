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
