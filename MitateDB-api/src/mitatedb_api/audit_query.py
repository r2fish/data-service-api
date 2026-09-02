"""`audit_query`'s cursor codec, declared vocabulary, and read surfaces
(design docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md D-5/D-6, work order
WP-3(b)).

Independent implementation of r2db-api's own `r2db_api.audit_query`/
`r2db_api.credential_store.PostgresAuditQueryStore` (R-2's closing
paragraph: no code sharing between peers) -- same D-6 semantics (opaque,
filter-independent keyset cursor over `(recorded_at, plane, event_id)`;
`plane` derived from which table a row came from, never a stored column),
adapted to this peer's own shapes: `event_id` is `text` (not `uuid`,
`control_audit`/`application_audit`'s own pre-existing non-symmetry with
r2db, migration `0005_application_audit.sql`'s own header note), and this
module imports `psycopg` unconditionally at module scope -- matching this
peer's own established convention (`control_audit.py`/`application_audit.py`
both do the same, unlike r2db-api's deferred-import discipline for its own
top-level package).

Cursor (D-6): an OPAQUE token encoding `(recorded_at, plane, event_id)` --
never an `event_id` alone (`event_id` is unique only within one durable
table's own PRIMARY KEY; the `control_audit`/`application_audit` UNION has
no cross-table uniqueness guarantee on `event_id`, contract `audit.
query_ordering`). `decode_cursor` accepts only what `encode_cursor` produced,
raising `ValueError` on anything else -- `ControlPlaneService.audit_query`
maps this to `VALIDATION_FAILED`, never letting it escape as an unclassified
500.
"""
from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol, Sequence

import psycopg
from psycopg import sql

from .application_audit import APPLICATION_AUDIT_FIELDS, DEFAULT_DENIAL_COALESCE_WINDOW_S
from .control_audit import CONTROL_AUDIT_FIELDS
from .errors import ValidationError
from .identifiers import validate_identifier

DEFAULT_SCHEMA = "mitatedb_registry"

# D-7: the vocabulary this peer's `audit_query` reader can ever surface,
# across BOTH `control_audit` (`control_plane.py`'s own `event_class=`
# literals -- every control-plane state change/denial is durable by
# construction, no buffer/coalescing on that plane) and `application_audit`
# (`application_audit.DECLARED_AUDIT_EVENT_CLASSES`, this peer's own
# already-declared application-plane vocabulary, WP-3(a)) plus the one
# additional class WP-3(a) already emits from the buffer-overflow-alert
# path, `security_control_failure` (already a member of that set).
# `tests/test_audit_query.py::test_declared_event_classes_cover_every_
# emittable_class` fixes this against BOTH modules' real emit call sites
# via an AST walk that resolves positional args, keyword args, AND
# `.append(event_class=...)` forms alike (mirroring r2db-api's WP-2(b)
# fix-round-2 AST scanner, not its earlier, narrower one -- this peer never
# ships the narrower version at all).
_CONTROL_PLANE_EVENT_CLASSES = frozenset(
    {
        "authentication_denial",
        "authorization_denial",
        "capability_denial",
        "application_lifecycle",
        "credential_lifecycle",
        "control_credential_lifecycle",
    }
)


def _application_event_classes() -> frozenset:
    from .application_audit import DECLARED_AUDIT_EVENT_CLASSES

    return DECLARED_AUDIT_EVENT_CLASSES


DECLARED_AUDIT_EVENT_CLASSES = _CONTROL_PLANE_EVENT_CLASSES | _application_event_classes()

# D-3 (P4-D3, confirmed value): the denial-coalescing window's DEFAULT.
# Declared in `capabilities().audit_query.coalescing_window_ms` via a
# constructor parameter derived from the REAL `AuditRouter.denial_coalesce_
# window_s` a composition root is actually running with (never hardcoded
# here as the sole source -- `control_composition.build_control_service`
# reads this constant only as ITS OWN fallback default, exactly the same
# "same env name/same default constant, both processes must agree" pattern
# already established for `visibility_lag_ms`'s two writer timeouts).
DEFAULT_COALESCING_WINDOW_MS = int(DEFAULT_DENIAL_COALESCE_WINDOW_S * 1000)

_CURSOR_KEYS = ("recorded_at", "plane", "event_id")


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def encode_cursor(recorded_at: datetime, plane: str, event_id: str) -> str:
    """Opaque, base64url-encoded JSON -- deliberately not a bare delimited
    string (JSON, not string concatenation, so no field value can ever
    require escaping)."""
    payload = {"recorded_at": _to_utc(recorded_at).isoformat(), "plane": plane, "event_id": event_id}
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_cursor(token: str) -> "tuple[datetime, str, str]":
    """Raises `ValueError` on anything that is not a cursor this module's
    own `encode_cursor` produced -- the caller (`ControlPlaneService.
    audit_query`) maps this to `VALIDATION_FAILED`, never lets it escape."""
    if not isinstance(token, str) or not token:
        raise ValueError("cursor must be a non-empty string")
    try:
        raw = base64.urlsafe_b64decode(token.encode("ascii"))
        payload = json.loads(raw)
    except Exception as exc:  # noqa: BLE001 -- any decode failure is a bad cursor
        raise ValueError("cursor is not a valid opaque token") from exc
    if not isinstance(payload, dict) or set(payload) != set(_CURSOR_KEYS):
        raise ValueError("cursor payload has an unexpected shape")
    plane = payload["plane"]
    event_id = payload["event_id"]
    if not isinstance(plane, str) or plane not in ("control", "application") or not isinstance(event_id, str):
        raise ValueError("cursor payload has an unexpected shape")
    try:
        recorded_at = datetime.fromisoformat(payload["recorded_at"])
    except Exception as exc:  # noqa: BLE001
        raise ValueError("cursor recorded_at is not a valid timestamp") from exc
    return _to_utc(recorded_at), plane, event_id


class AuditQueryReader(Protocol):
    """The call surface `ControlPlaneService.audit_query` needs from a
    reader -- `PostgresAuditQueryStore` and `InMemoryAuditQueryStore`
    (below) both implement it (D-10 parity)."""

    def query(
        self, *, event_classes: "Sequence[str] | None", after: "tuple[datetime, str, str] | None",
        limit: int, visibility_lag_ms: int,
    ) -> "list[dict[str, Any]]": ...


def _control_event_dict(event: Any) -> "dict[str, Any] | None":
    try:
        recorded_at = datetime.fromisoformat(event.occurred_at)
    except (ValueError, TypeError):
        return None
    return {
        "event_id": event.event_id, "event_class": event.event_class, "occurred_at": event.occurred_at,
        "request_id": event.request_id, "application_id": event.application_id, "actor_type": event.actor_type,
        "actor_id": event.actor_id, "role": event.role, "operation": event.operation,
        "target_kind": event.target_kind, "outcome": event.outcome, "reason_code": event.reason_code,
        "target_id": event.target_id, "count": None, "recorded_at": _to_utc(recorded_at), "plane": "control",
    }


def _application_event_dict(event: Any) -> "dict[str, Any] | None":
    try:
        recorded_at = datetime.fromisoformat(event.occurred_at)
    except (ValueError, TypeError):
        return None
    return {
        "event_id": event.event_id, "event_class": event.event_class, "occurred_at": event.occurred_at,
        "request_id": event.request_id, "application_id": event.application_id, "actor_type": event.actor_type,
        "actor_id": event.actor_id, "role": event.role, "operation": event.operation,
        "target_kind": event.target_kind, "outcome": event.outcome, "reason_code": event.reason_code,
        "target_id": event.target_id, "count": event.count, "recorded_at": _to_utc(recorded_at), "plane": "application",
    }


class InMemoryAuditQueryStore:
    """D-10's in-memory reader pair -- UNIONs `control_audit`'s in-memory
    half (`control_audit.ControlAuditSink.snapshot()`) and `application_
    audit`'s in-memory half (`application_audit.ApplicationAuditSink.
    events()`), applying the identical `(recorded_at, plane, event_id)`
    order, opaque-cursor paging, and visibility-lag filtering `Postgres
    AuditQueryStore` applies via SQL.

    Constructed by the in-process conformance adapter and by this peer's
    own peer-local in-memory-backend tests -- never by `control_
    composition.build_control_service`, which always talks to a real
    Postgres platform database when `audit_query` is `enabled`.
    """

    def __init__(self, control_audit: Any, application_audit: Any) -> None:
        self._control_audit = control_audit
        self._application_audit = application_audit

    def query(
        self, *, event_classes: "Sequence[str] | None", after: "tuple[datetime, str, str] | None",
        limit: int, visibility_lag_ms: int,
    ) -> "list[dict[str, Any]]":
        threshold = datetime.now(timezone.utc) - timedelta(milliseconds=visibility_lag_ms)
        class_filter = set(event_classes) if event_classes is not None else None
        rows: list[dict[str, Any]] = []
        for event in self._control_audit.snapshot():
            row = _control_event_dict(event)
            if row is None:
                continue
            rows.append(row)
        for event in self._application_audit.events():
            row = _application_event_dict(event)
            if row is None:
                continue
            rows.append(row)
        filtered: list[dict[str, Any]] = []
        for row in rows:
            if row["recorded_at"] >= threshold:
                continue
            if class_filter is not None and row["event_class"] not in class_filter:
                continue
            if after is not None and (row["recorded_at"], row["plane"], row["event_id"]) <= after:
                continue
            filtered.append(row)
        filtered.sort(key=lambda row: (row["recorded_at"], row["plane"], row["event_id"]))
        return filtered[:limit]


# Phase 4 WP-3(b) (design D-5/D-6): the `audit_query` UNION -- `event_id` is
# `text` natively on BOTH tables for this peer (no `::text` cast needed,
# unlike r2db-api's own `uuid` columns). `control_audit` carries no `count`
# column (its own header note; the control plane has neither coalescing nor
# a buffer) -- its half of the UNION selects a literal `NULL::integer`.
# `ROW(...) > ROW(...)` is PostgreSQL's native lexicographic tuple
# comparison, expressing exclusive keyset paging against the full
# `(recorded_at, plane, event_id)` order directly (see r2db-api's own
# `PostgresAuditQueryStore` for the fuller rationale -- read only as a
# reference, this SQL is independently authored for this peer's own column
# types).
_AUDIT_QUERY_UNION_SQL = """
WITH filtered AS (
    SELECT event_id, event_class, occurred_at, request_id, application_id,
           actor_type, actor_id, role, operation, target_kind, outcome, reason_code, target_id,
           NULL::integer AS count, recorded_at, 'control'::text AS plane
    FROM {control_table}
    WHERE recorded_at < %(threshold)s
      AND (%(classes)s::text[] IS NULL OR event_class = ANY(%(classes)s::text[]))
      AND (
        %(after_recorded_at)s::timestamptz IS NULL
        OR ROW(recorded_at, 'control'::text, event_id)
           > ROW(%(after_recorded_at)s::timestamptz, %(after_plane)s::text, %(after_event_id)s::text)
      )
    UNION ALL
    SELECT event_id, event_class, occurred_at, request_id, application_id,
           actor_type, actor_id, role, operation, target_kind, outcome, reason_code, target_id,
           count, recorded_at, 'application'::text AS plane
    FROM {application_table}
    WHERE recorded_at < %(threshold)s
      AND (%(classes)s::text[] IS NULL OR event_class = ANY(%(classes)s::text[]))
      AND (
        %(after_recorded_at)s::timestamptz IS NULL
        OR ROW(recorded_at, 'application'::text, event_id)
           > ROW(%(after_recorded_at)s::timestamptz, %(after_plane)s::text, %(after_event_id)s::text)
      )
)
SELECT event_id, event_class, occurred_at, request_id, application_id, actor_type, actor_id, role,
       operation, target_kind, outcome, reason_code, target_id, count, recorded_at, plane
FROM filtered
ORDER BY recorded_at, plane, event_id
LIMIT %(row_limit)s
"""

_AUDIT_QUERY_ROW_COLUMNS = (
    "event_id", "event_class", "occurred_at", "request_id", "application_id", "actor_type", "actor_id",
    "role", "operation", "target_kind", "outcome", "reason_code", "target_id", "count", "recorded_at", "plane",
)

# Sanity cross-check, module import time: both tables' own field tuples
# (imported above) must agree with the 13 shared columns this UNION reads
# from each -- a future edit to either table's field list that this module
# does not follow would otherwise silently read/write the wrong columns.
assert set(CONTROL_AUDIT_FIELDS) <= set(_AUDIT_QUERY_ROW_COLUMNS)
assert set(APPLICATION_AUDIT_FIELDS) <= set(_AUDIT_QUERY_ROW_COLUMNS)


class PostgresAuditQueryStore:
    """Phase 4 WP-3(b) (design D-5/D-6): `audit_query`'s Postgres reader --
    the dedicated, SELECT-only `mitatedbsvc_auditreader` role (migration
    `0005_application_audit.sql` §1.3), reading BOTH `control_audit` and
    `application_audit` over one connection (D-1(b): a single platform DB
    is what makes this possible without an N-database fan-out). Never
    shares a DSN/role with any writer role or with `mitatedbsvc_
    controlplane` (D-5's own "別 DSN" requirement -- `mitatedbsvc_
    controlplane` receives no grant on either audit table at all, migration
    0005 §1.3 note 4).

    `InMemoryAuditQueryStore` (above) is this class's in-memory pair
    (D-10) -- both implement the same `AuditQueryReader` call surface and
    are exercised by the identical parity test (`tests/test_audit_query.py::
    test_in_memory_and_postgres_audit_query_semantics_have_parity`).
    """

    def __init__(self, dsn: str, *, schema: str = DEFAULT_SCHEMA, connect_timeout: int = 5) -> None:
        validate_identifier(schema, "schema")
        self._dsn = dsn
        self._connect_timeout = connect_timeout
        self._control_table = sql.Identifier(schema, "control_audit")
        self._application_table = sql.Identifier(schema, "application_audit")

    def query(
        self, *, event_classes: "Sequence[str] | None", after: "tuple[datetime, str, str] | None",
        limit: int, visibility_lag_ms: int,
    ) -> "list[dict[str, Any]]":
        threshold = datetime.now(timezone.utc) - timedelta(milliseconds=visibility_lag_ms)
        params: dict[str, Any] = {
            "threshold": threshold,
            "classes": list(event_classes) if event_classes is not None else None,
            "after_recorded_at": after[0] if after is not None else None,
            "after_plane": after[1] if after is not None else None,
            "after_event_id": after[2] if after is not None else None,
            "row_limit": limit,
        }
        statement = sql.SQL(_AUDIT_QUERY_UNION_SQL).format(
            control_table=self._control_table, application_table=self._application_table)
        conn = psycopg.connect(self._dsn, connect_timeout=self._connect_timeout)
        try:
            with conn.cursor() as cur:
                cur.execute(statement, params)
                raw_rows = cur.fetchall()
        finally:
            conn.close()
        rows: list[dict[str, Any]] = []
        for raw in raw_rows:
            row = dict(zip(_AUDIT_QUERY_ROW_COLUMNS, raw))
            rec = row["recorded_at"]
            row["recorded_at"] = rec if rec.tzinfo is not None else rec.replace(tzinfo=timezone.utc)
            occurred = row["occurred_at"]
            row["occurred_at"] = occurred.isoformat() if hasattr(occurred, "isoformat") else occurred
            rows.append(row)
        return rows


def validate_audit_event_classes(value: Any, *, max_classes: int) -> "list[str] | None":
    """D-6: `event_classes` is a FILTER, not a vocabulary check -- an
    unknown class is never `VALIDATION_FAILED`, it simply matches no row
    (D-7: the vocabulary is declared, not contract-enumerated)."""
    if value is None:
        return None
    if not isinstance(value, list) or len(value) > max_classes or not all(isinstance(item, str) for item in value):
        raise ValidationError(f"event_classes must be an array of at most {max_classes} strings")
    return value


def validate_audit_after(value: Any) -> "tuple[datetime, str, str] | None":
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValidationError("after must be a string")
    try:
        return decode_cursor(value)
    except ValueError as exc:
        raise ValidationError("after is not a valid opaque cursor") from exc


def validate_audit_limit(value: Any, *, default: int, maximum: int) -> int:
    if value is None:
        return default
    if not isinstance(value, int) or isinstance(value, bool) or value < 1 or value > maximum:
        raise ValidationError(f"limit must be an integer between 1 and {maximum}")
    return value


def shape_audit_query_row(row: "dict[str, Any]") -> "dict[str, Any]":
    """Turns one reader row (`AuditQueryReader.query`'s own dict shape --
    13 contract `audit.fields` + `count` + `recorded_at` + `plane`) into
    one `AuditResult.events[]` element: adds the opaque `cursor` (D-6),
    formats `recorded_at` as ISO-8601, and omits every optional field that
    is `None`."""
    recorded_at = row["recorded_at"]
    cursor = encode_cursor(recorded_at, row["plane"], row["event_id"])
    out: dict[str, Any] = {
        "event_id": row["event_id"],
        "event_class": row["event_class"],
        "occurred_at": row["occurred_at"],
        "operation": row["operation"],
        "outcome": row["outcome"],
        # D-6: `plane` is the read surface's own derived value (which UNION
        # half a row came from) -- never a stored column a writer could set.
        "plane": row["plane"],
        "recorded_at": recorded_at.isoformat() if hasattr(recorded_at, "isoformat") else recorded_at,
        "cursor": cursor,
    }
    for key in ("request_id", "application_id", "actor_type", "actor_id", "role", "target_kind", "reason_code", "target_id", "count"):
        value = row.get(key)
        if value is not None:
            out[key] = value
    return out


__all__ = [
    "DEFAULT_SCHEMA",
    "DECLARED_AUDIT_EVENT_CLASSES",
    "DEFAULT_COALESCING_WINDOW_MS",
    "AuditQueryReader",
    "InMemoryAuditQueryStore",
    "PostgresAuditQueryStore",
    "encode_cursor",
    "decode_cursor",
    "validate_audit_event_classes",
    "validate_audit_after",
    "validate_audit_limit",
    "shape_audit_query_row",
]
