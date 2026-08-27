"""Canonical append-only security event sink for the foundation."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any
import uuid


FORBIDDEN = ("credential", "token", "password", "secret", "private_key", "sql", "row_value")


@dataclass(frozen=True)
class AuditEvent:
    event_id: str
    event_class: str
    occurred_at: str
    request_id: str
    application_id: str | None
    actor_type: str
    actor_id: str | None
    role: str | None
    operation: str
    target_kind: str | None
    outcome: str
    reason_code: str | None

    def as_dict(self) -> MappingProxyType:
        return MappingProxyType({k: v for k, v in self.__dict__.items() if v is not None})


class AuditSink:
    """Append-only in-memory sink; production must supply external governance."""

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def append(self, *, event_class: str, request_id: str, application_id: str | None, actor_type: str, actor_id: str | None, role: str | None, operation: str, target_kind: str | None, outcome: str, reason_code: str | None = None, **extra: Any) -> AuditEvent:
        if any(k.lower() in FORBIDDEN for k in extra):
            raise ValueError("forbidden audit field")
        event = AuditEvent(str(uuid.uuid4()), event_class, datetime.now(timezone.utc).isoformat(), request_id, application_id, actor_type, actor_id, role, operation, target_kind, outcome, reason_code)
        self._events.append(event)
        return event

    def events(self) -> tuple[MappingProxyType, ...]:
        return tuple(event.as_dict() for event in self._events)

    def delete(self, *_: Any, **__: Any) -> None:
        raise PermissionError("audit sink is append-only")
