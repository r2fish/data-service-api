"""r2db page size, order_by, and cursor pagination: the contract `Page.
size` ceiling, order_by field/direction validation and its `id` tie-
breaker, and cursor shape hashing/encoding/decoding (ST7).

This is a pure leaf: `validate_page_size` is a closed-form comparison of
its own `page_size` argument against a fixed contract ceiling and the
caller's own explicitly-passed `ResourceLimits` (work order §2's E
classification -- a deployment's resource limits are an explicit
argument here, never read from global/service state); `_resolve_order_by`
validates and normalizes an already-parsed order_by list against an
already-known field set, delegating identifier syntax to
`validate_identifier` (in `identifier_rules.py`); and `_shape_hash`/
`_encode_cursor`/`_decode_cursor` are total, deterministic functions over
their own arguments alone. None of the five opens a connection, reads a
catalog, or consults any request/limits/principal state beyond the
`ResourceLimits` object a caller passes in. The choke point that decides
*when* a page is fetched (`ApplicationCell.query`, in `structured.py`)
remains in its own module.
"""
from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from .errors import fail, violation
from .identifier_rules import validate_identifier
from .limits import ResourceLimits


# --- page size (contract `Page.size`) ---------------------------------------

# `spec/data-service-api.v1.json`'s `Page.size` schema: `{"minimum": 1,
# "maximum": 1000}` -- a fixed contract ceiling, independent of
# `ResourceLimits.result_items` (a deployment-tunable resource class that
# could in principle be configured to any positive value). A client
# request for a page larger than the contract itself allows is a request
# outside the contract's own vocabulary (`VALIDATION_FAILED`), not a
# resource a deployment could simply raise (WP-4 review minor-1).
MAX_PAGE_SIZE = 1000


def validate_page_size(page_size: int, limits: ResourceLimits) -> None:
    if page_size <= 0:
        fail("LIMIT_EXCEEDED", "Page size must be positive.", status=413, details={"resource": "result_items", "limit_class": "result_items", "limit": limits.result_items})
    if page_size > MAX_PAGE_SIZE:
        fail("VALIDATION_FAILED", "Page size exceeds the contract maximum.", details=violation("budget", field="page_size"))


# --- order_by / cursor pagination (R-6) ------------------------------------

MAX_ORDER_BY_FIELDS = 10
MAX_CURSOR_OFFSET = 10**9


def _resolve_order_by(order_by: Any, known_fields: set[str]) -> list[tuple[str, str]]:
    spec: list[tuple[str, str]] = []
    if order_by is not None:
        if not isinstance(order_by, list) or len(order_by) > MAX_ORDER_BY_FIELDS:
            fail("VALIDATION_FAILED", "order_by must be a bounded list.", details=violation("request_schema", field="order_by"))
        seen_fields: set[str] = set()
        for i, item in enumerate(order_by):
            if not isinstance(item, dict) or "field" not in item or set(item) - {"field", "direction"}:
                fail("VALIDATION_FAILED", "order_by entry shape is not supported.", details=violation("request_schema", field="order_by"))
            # Ruling N-1: container position (the order_by entry itself,
            # "order_by/<i>" -- N-1's own example), not "order_by/<i>/field"
            # (which would only be the literal key name "field", but N-1's
            # worked examples are followed verbatim).
            field_name = validate_identifier(item["field"], field=f"order_by/{i}")
            if field_name not in known_fields:
                fail("NOT_FOUND", "Field was not found.", status=404)
            if field_name in seen_fields:
                # WP-2 review minor (b): a field named twice is always
                # either redundant or self-contradictory (opposite
                # directions) -- reject rather than silently keep only one.
                fail("VALIDATION_FAILED", "order_by must not repeat a field.", details=violation("request_schema", field="order_by"))
            seen_fields.add(field_name)
            direction = item.get("direction", "asc")
            if direction not in ("asc", "desc"):
                fail("VALIDATION_FAILED", "order_by direction must be asc or desc.", details=violation("enum", field="order_by/direction", declared_type="string"))
            spec.append((field_name, direction))
    if not any(field_name == "id" for field_name, _ in spec):
        # R-6: deterministic ordering requires a total order; `id` is the
        # one column every row differs on, so it is appended (ascending)
        # whenever the caller's own order_by does not already mention it.
        spec.append(("id", "asc"))
    return spec


def _shape_hash(application_id: str, entity: str, select: list[str], where: list[Predicate], order_spec: list[tuple[str, str]], size: int) -> str:
    payload = {
        # WP-2 review minor (a): binding the hash to the Application scope
        # and entity too (not just select/where/order_by/size) means a
        # cursor minted under one application/entity can never even
        # coincidentally validate against another's query of the same
        # select/where/order_by/size shape.
        "application": application_id,
        "entity": entity,
        "select": list(select),
        "where": [[p.field, p.operator, p.value] for p in where],
        "order_by": [list(item) for item in order_spec],
        "size": size,
    }
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def _encode_cursor(offset: int, shape: str) -> str:
    payload = json.dumps({"o": offset, "q": shape}, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_cursor(cursor: Any, expected_shape: str) -> int:
    if not isinstance(cursor, str) or not cursor:
        fail("VALIDATION_FAILED", "Cursor is not valid.", details=violation("request_schema", field="cursor"))
    padded = cursor + "=" * (-len(cursor) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        payload = json.loads(raw)
    except Exception:
        fail("VALIDATION_FAILED", "Cursor could not be decoded.", details=violation("request_schema", field="cursor"))
    if not isinstance(payload, dict) or set(payload) != {"o", "q"}:
        fail("VALIDATION_FAILED", "Cursor shape is not supported.", details=violation("request_schema", field="cursor"))
    offset = payload["o"]
    shape = payload["q"]
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0 or offset > MAX_CURSOR_OFFSET:
        fail("VALIDATION_FAILED", "Cursor offset is out of range.", details=violation("request_schema", field="cursor"))
    if not isinstance(shape, str) or shape != expected_shape:
        # R-6, corrigendum m-3: a cursor minted for a different query shape
        # (different select/where/order_by/size) never silently pages
        # through the wrong result set -- it fails loudly instead.
        fail("VALIDATION_FAILED", "Cursor does not match the current query shape.", details=violation("request_schema", field="cursor"))
    return offset
