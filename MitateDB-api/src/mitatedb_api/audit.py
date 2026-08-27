"""Append-only, secret-free security event evidence."""

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Optional


@dataclass(frozen=True)
class AuditEvent:
    event_type: str
    application_id: Optional[str]
    credential_id: Optional[str]
    outcome: str
    detail: str
    occurred_at: str


class AuditSink:
    """Small local evidence sink; production wiring must be append-only."""

    __slots__ = ("__events", "__lock")

    _SAFE_DETAILS = {
        "", "role=runtime", "role=developer", "state_unavailable",
        "invalid_or_disabled", "schema_change", "create_collection",
        "delete_rows",
    }
    _SAFE_EVENTS = {
        "credential_issued", "credential_revoked", "application_disabled",
        "authorization_state_failure", "authentication_denied",
        "authentication_succeeded", "authorization_denied", "schema_change",
        "destructive_data_operation",
    }

    def __init__(self):
        self.__events = ()
        self.__lock = Lock()

    def record(self, event_type, application_id=None, credential_id=None,
               outcome="success", detail=""):
        # Callers pass classifications and safe metadata only. Values, SQL,
        # tokens and exception text are intentionally not accepted here.
        safe_event = event_type if isinstance(event_type, str) and event_type in self._SAFE_EVENTS else "unclassified"
        safe_detail = detail if isinstance(detail, str) and detail in self._SAFE_DETAILS else "unspecified"
        event = AuditEvent(
            event_type=safe_event,
            application_id=application_id,
            credential_id=credential_id,
            outcome=outcome,
            detail=safe_detail,
            occurred_at=datetime.now(timezone.utc).isoformat(),
        )
        with self.__lock:
            self.__events = self.__events + (event,)

    def snapshot(self):
        with self.__lock:
            return self.__events
