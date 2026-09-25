"""r2db page size, order_by, and keyset cursor pagination: the contract
`Page.size` ceiling, order_by field/direction validation and its `id`
tie-breaker, the D-6 cursor codec (`encode_page_cursor`/
`decode_page_cursor`) and binding hash (`canonical_page_binding`), and the
r2db-side decode-and-check wrapper `decode_and_check_page_cursor` that
turns a bad cursor into the single D-1 (5) refusal (ST7).

This is a pure leaf: `validate_page_size` is a closed-form comparison of
its own `page_size` argument against a fixed contract ceiling; `_resolve_
order_by` validates and normalizes an already-parsed order_by list against
an already-known field set, delegating identifier syntax to `validate_
identifier` (in `identifier_rules.py`); and `encode_page_cursor`/`decode_
page_cursor`/`canonical_page_binding`/`decode_and_check_page_cursor` are
total, deterministic functions over their own arguments alone. None of
these open a connection, read a catalog, or consult any request/limits/
principal state beyond the `ResourceLimits` object `validate_page_size`
takes. The choke point that decides *when* a page is fetched
(`ApplicationCell.query`/`PostgresCell.query`) remains in its own module.
"""
from __future__ import annotations

import base64
import hashlib
import json
from typing import Any, Sequence

from .errors import FoundationError, fail, violation
from .identifier_rules import validate_identifier
from .limits import ResourceLimits
from .value_types import _check_type


# --- page size (contract `Page.size`) ---------------------------------------

# `spec/data-service-api.v1.json`'s `Page.size` schema: `{"minimum": 1,
# "maximum": 1000}` -- a fixed contract ceiling, independent of
# `ResourceLimits.result_items` (a deployment-tunable resource class that
# could in principle be configured to any positive value). A client
# request for a page outside the contract's own declared range is a
# request outside the contract's own vocabulary (`VALIDATION_FAILED` /
# `request_schema` / `page/size`), not a resource a deployment could
# simply raise or lower (design D-3 (8)).
MAX_PAGE_SIZE = 1000


def validate_page_size(page_size: int, limits: ResourceLimits) -> None:
    if page_size <= 0 or page_size > MAX_PAGE_SIZE:
        fail("VALIDATION_FAILED", "Page size is outside the contract's declared range.", details=violation("request_schema", field="page/size"))


# --- order_by / cursor pagination (R-6, keyset paging D-3) -----------------------

MAX_ORDER_BY_FIELDS = 10


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
            # Contract 1.11.0 (subordinate ruling 16): an undeclared field
            # name here is a request_schema violation naming the position
            # (`order_by/<i>/field`) -- NOT_FOUND is not a conforming
            # refusal of it at this position
            # (errors.details_vocabulary.undeclared_field).
            if field_name not in known_fields:
                fail("VALIDATION_FAILED", "Field is not declared.", details=violation("request_schema", field=f"order_by/{i}/field"))
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


def canonical_page_binding(application_id: str, entity: str, where: Sequence[tuple[str, str, Any]], order_by: Sequence[tuple[str, str]]) -> str:
    """The hash a page cursor is bound to (design D-3 (3), D-6): the
    Application scope, the entity, `where`'s own (field, operator, value)
    triples normalized to a value-order-independent form, and `order_by`'s
    own (field, direction) pairs (which are not normalized, since their
    order decides the result order itself).
    """
    normalized_where = sorted([field, operator, json.dumps(value, sort_keys=True, default=str)] for field, operator, value in where)
    payload = {"application": application_id, "entity": entity, "where": normalized_where, "order_by": [list(item) for item in order_by]}
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def encode_page_cursor(values: list[Any], binding: str) -> str:
    """The opaque `page.cursor` token (design D-6): the ordering values of
    the last item of a page, together with the binding hash they were
    minted under. Holds no server-side state; `values`/`binding` are
    caller-supplied, so this function alone never knows what either one
    means.
    """
    payload = json.dumps({"v": values, "b": binding}, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def decode_page_cursor(cursor: Any, expected_binding: str) -> list[Any]:
    """The inverse of `encode_page_cursor`: recovers the ordering values a
    cursor carries, once its own binding hash matches `expected_binding`.
    Raises `ValueError` on any failure -- not a string, not decodable, the
    wrong shape, or a binding that does not match -- and never distinguishes
    which one to its caller; the caller maps `ValueError` to its own
    contract-level refusal (design D-6 (b)).
    """
    if not isinstance(cursor, str) or not cursor:
        raise ValueError("cursor is not a non-empty string")
    padded = cursor + "=" * (-len(cursor) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        payload = json.loads(raw)
    except Exception as exc:
        raise ValueError("cursor could not be decoded") from exc
    if not isinstance(payload, dict) or set(payload) != {"v", "b"}:
        raise ValueError("cursor shape is not supported")
    values = payload["v"]
    binding = payload["b"]
    if not isinstance(values, list):
        raise ValueError("cursor values are not a list")
    if not isinstance(binding, str) or binding != expected_binding:
        raise ValueError("cursor binding does not match the current query")
    return values


def decode_and_check_page_cursor(cursor: Any, binding: str, order_spec: list[tuple[str, str]], field_types: dict[str, str | None]) -> list[Any]:
    """r2db's own wrapper around `decode_page_cursor` (not one of the
    isomorphic-pinned D-6 functions): decodes `cursor` against `binding`,
    then checks the decoded ordering values against `order_spec` (design
    D-3 (4a)) -- the count must match `order_spec` (tie-break included) and
    each value must satisfy `_check_type` for its own column's declared
    type. Any failure along the way -- decode, binding mismatch, count, or
    type -- collapses to the single D-1 (5) refusal (`VALIDATION_FAILED` /
    `request_schema` / `page/cursor`); the caller never learns which one.
    """
    ok = True
    values: list[Any] = []
    try:
        values = decode_page_cursor(cursor, binding)
    except ValueError:
        ok = False
    if ok and len(values) != len(order_spec):
        ok = False
    if ok:
        try:
            for value, (field_name, _direction) in zip(values, order_spec):
                _check_type(value, field_types.get(field_name), "page/cursor")
        except FoundationError:
            ok = False
    if not ok:
        fail("VALIDATION_FAILED", "Cursor does not match this query's own order.", details=violation("request_schema", field="page/cursor"))
    return values
