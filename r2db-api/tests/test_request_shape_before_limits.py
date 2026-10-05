"""R-39 CS-1 (work order docs/work-orders/WORK_ORDER_R39_TEST_GAPS_V1.md
C1-10a..C1-10c): `DataService.query` / `.mutate` report a request-shape
violation BEFORE a resource limit when a request is both malformed and
over a limit. The gap was recorded by `MODULE_REFACT_ARCHITECTURE_V1.md`
section 10.9 row 24; the order itself ("shape check -> `limits.check_request`
-> `limits.check_depth`") is the current code's, at
`service._query_outcome` and `_mutate_outcome`.

`test_foundation.py`'s `test_request_shape_denials_carry_code_details_and_
order` fixes each shape denial alone and the capability-before-operations
order; the limit tests there (`_limited`) drive a limit alone. This file
drives the pair together, each with its control: the same limit exceeded
by an otherwise well-formed request is `LIMIT_EXCEEDED`, so the shape
denial is the order's doing and not the limit's absence.

`_limited` below is a local copy of `test_foundation.py`'s helper of the
same name (an existing test file is not edited by this change).
"""
from __future__ import annotations

import pytest

from r2db_api import ControlAuthority, CredentialStore, DataService
from r2db_api.errors import FoundationError
from r2db_api.limits import ResourceLimits


def _limited(**kwargs):
    credentials = CredentialStore(pepper="limit-pepper")
    with credentials.unit_of_work() as work:
        credentials.add("limit-cred", "limit-app", "runtime", "limit-secret", work=work)
    service = DataService(credentials, limits=ResourceLimits(**kwargs))
    ControlAuthority(service).register_application("limit-app", entities={"items": [{}, {}]})
    return service, service.authenticate("limit-cred.limit-secret")


def _deep(levels: int) -> dict:
    root: dict = {}
    cursor = root
    for _ in range(levels):
        cursor["next"] = {}
        cursor = cursor["next"]
    return root


def test_query_shape_violation_is_reported_before_request_bytes_exceeded() -> None:
    """C1-10a: `request_bytes=100`; `select="x" * 1000` (not a list) is
    `VALIDATION_FAILED` / `request_schema`, not `LIMIT_EXCEEDED`. Control:
    a well-formed query with a 1000-character where value is
    `LIMIT_EXCEEDED` / `request_bytes`."""
    service, context = _limited(request_bytes=100)
    with pytest.raises(FoundationError) as excinfo:
        service.query(context, "items", select="x" * 1000)
    assert excinfo.value.code == "VALIDATION_FAILED"
    assert excinfo.value.details == {"violated_declaration": "request_schema"}

    with pytest.raises(FoundationError) as excinfo:
        service.query(context, "items", select=["id"], where=[{"field": "id", "operator": "eq", "value": "x" * 1000}])
    assert excinfo.value.code == "LIMIT_EXCEEDED"
    assert excinfo.value.details["limit_class"] == "request_bytes"


def test_query_shape_violation_is_reported_before_depth_exceeded() -> None:
    """C1-10b: default limits; `page_size=True` together with a where
    value nested 1200 deep is `VALIDATION_FAILED` / `request_schema`, not
    `LIMIT_EXCEEDED`. Control: a valid `page_size` with the same deep
    value is `LIMIT_EXCEEDED` / `operation_depth`."""
    service, context = _limited()
    deep_where = [{"field": "id", "operator": "eq", "value": _deep(1200)}]
    with pytest.raises(FoundationError) as excinfo:
        service.query(context, "items", select=["id"], where=deep_where, page_size=True)
    assert excinfo.value.code == "VALIDATION_FAILED"
    assert excinfo.value.details == {"violated_declaration": "request_schema"}

    with pytest.raises(FoundationError) as excinfo:
        service.query(context, "items", select=["id"], where=deep_where, page_size=5)
    assert excinfo.value.code == "LIMIT_EXCEEDED"
    assert excinfo.value.details["limit_class"] == "operation_depth"


def test_mutate_shape_violation_is_reported_before_request_bytes_exceeded() -> None:
    """C1-10c: `request_bytes=100`; `operations="x" * 1000` (not a list)
    is `VALIDATION_FAILED` / `request_schema` at `operations`, and an
    unsupported `transaction` with the same oversize `operations` is
    `CAPABILITY_UNSUPPORTED` at `transaction` -- neither is
    `LIMIT_EXCEEDED`. Control: a well-formed insert with a 1000-character
    value is `LIMIT_EXCEEDED` / `request_bytes`."""
    service, context = _limited(request_bytes=100)
    with pytest.raises(FoundationError) as excinfo:
        service.mutate(context, "items", "x" * 1000)
    assert excinfo.value.code == "VALIDATION_FAILED"
    assert excinfo.value.details == {"violated_declaration": "request_schema", "field": "operations"}

    with pytest.raises(FoundationError) as excinfo:
        service.mutate(context, "items", "x" * 1000, transaction="best_effort")
    assert excinfo.value.code == "CAPABILITY_UNSUPPORTED"
    assert excinfo.value.details == {"violated_declaration": "capability", "field": "transaction"}

    with pytest.raises(FoundationError) as excinfo:
        service.mutate(context, "items", [{"operation": "insert", "values": {"a": "x" * 1000}}])
    assert excinfo.value.code == "LIMIT_EXCEEDED"
    assert excinfo.value.details["limit_class"] == "request_bytes"
