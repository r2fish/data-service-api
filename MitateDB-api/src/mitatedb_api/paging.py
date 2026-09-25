"""MitateDB keyset page cursor codec and binding hash (design docs/design/
PHASE11_KEYSET_PAGING_V1.md D-2b.5, D-6): `encode_page_cursor`/`decode_
page_cursor`/`canonical_page_binding`, isomorphic-pinned against
`r2db_api.paging`'s own same-named functions (`MitateDB-api/tests/
test_audit_query.py`'s `_ISOMORPHIC_TARGETS`).

A pure leaf: every function here is a total, deterministic function over
its own explicitly-passed arguments alone -- no connection, catalog,
clock, or principal state. `cell.ApplicationCell.read_page` is the one
choke point that decides when a page is fetched and what these functions'
own arguments are; this module never opens a connection or reads the
active backend's catalog.
"""
from __future__ import annotations

import base64
import hashlib
import json
from typing import Any, Sequence


def canonical_page_binding(application_id: str, entity: str, where: Sequence[tuple[str, str, Any]], order_by: Sequence[tuple[str, str]]) -> str:
    """The hash a page cursor is bound to (design D-2b.5, D-6): the
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
