"""C-31 -- a request naming a field its entity does not declare is refused
uniformly at four of the five positions the contract names (SI-05, SI-10);
the fifth is pinned by each peer's own unit test (see below).

Registered in `conformance-tests/CONDITIONS.md`. Every test here carries
`@pytest.mark.condition("C-31")` via the module-level `pytestmark`.

Contract 1.11.0 (CCR_DISPOSITION.md subordinate ruling 16) unifies both
peers' refusal of an undeclared field name at four of the five positions
the contract names -- a query's `select` entry, a query's `where`
predicate field, a query's `order_by` entry field, and a mutation's
`values` key -- on `VALIDATION_FAILED`, `violated_declaration:
request_schema`, `field` naming the position, with `declared_type`/
`observed_type` both absent (no declaration exists for a name the entity
never declared). The fifth position (a mutation's own `where` predicate
field, `operations/<i>/where/<j>/field`) is not driven through this file's
own port calls; it is pinned instead by a dedicated unit test in each
peer's own `tests/test_denial_details_and_request_id.py`. Driven through
the existing `query_page` (select/where/order_by) and `attempt_mutation`
(values) ports -- no new port method.

Version-gated exactly like C-30 -- branches on the plug's own declared
`contract_version` (`adapter.parse_semver`, never a string compare), with
the runtime-attached `xfail` read at execution time
(`request.node.add_marker`). Every node here is `xfail(strict=False)`: an
early implementation may already answer this shape honestly ahead of its
own declaration, and this suite must not call that a bug.

Non-vacuity: the undeclared name sits at index 1 (or, for `values`, a
second key) of a request whose index 0 (or first key) is a genuinely
declared field, so the expected position can never be confused with the
container's own path; the (b) leg replaces the undeclared name with a
second declared field and asserts a real success (an item/affected count),
never merely the absence of an exception.
"""
from __future__ import annotations

import pytest

from adapter import BatchOperation, ConformanceAdapter, ConformanceDenial, fresh_identifier, parse_semver
from conftest import assert_details_vocabulary_values_safe, provision_pair

pytestmark = pytest.mark.condition("C-31")


_OBSERVED_BRANCH = "undeclared_field_refusal_1_11_0"


def _expected_branch_for_pre_1_11_0(pre_1_11_0: bool) -> str:
    return "pre_1_11_0" if pre_1_11_0 else _OBSERVED_BRANCH


def _pre_1_11_0_reason(adapter: ConformanceAdapter, contract_version: str) -> str:
    return (
        f"{adapter.name} declares contract_version {contract_version!r} (< 1.11.0) -- the undeclared-field "
        "refusal alignment is a 1.11.0 obligation (CCR_DISPOSITION.md subordinate ruling 16); this branch is "
        "expected to fail (not merely skip) until this peer's own version-flip commit lands, per the contract's "
        "own 1.11.0-only retroactivity rule."
    )


def _cross_check_observed_branch(adapter: ConformanceAdapter, pre_1_11_0: bool, contract_version: str) -> None:
    """Done ONLY in the `>= 1.11.0` branch -- an unconditional check would
    make `expected_branch` always disagree with a hardcoded `observed_
    branch` in the `< 1.11.0` branch, making a genuine strict XPASS
    structurally impossible there (mirrors `test_c30_keyset_paging.py`'s
    own `_cross_check_observed_branch`)."""
    if pre_1_11_0:
        return
    observed_branch = _OBSERVED_BRANCH
    expected_branch = _expected_branch_for_pre_1_11_0(pre_1_11_0)
    assert observed_branch == expected_branch, (
        f"{adapter.name}: contract_version {contract_version!r} implies branch {expected_branch!r}, but the "
        f"full body completed without any refusal -- observed {observed_branch!r}"
    )


def _mark_pre_1_11_0_xfail(adapter: ConformanceAdapter, request: pytest.FixtureRequest) -> tuple[bool, str]:
    contract_version = adapter.capability_document()["contract_version"]
    pre_1_11_0 = parse_semver(contract_version) < (1, 11, 0)
    if pre_1_11_0:
        request.node.add_marker(pytest.mark.xfail(reason=_pre_1_11_0_reason(adapter, contract_version), strict=False))
    return pre_1_11_0, contract_version


def _assert_undeclared_field_denial(denial: ConformanceDenial, *, expected_field: str, adapter_name: str) -> None:
    assert denial.code == "VALIDATION_FAILED", f"{adapter_name}: {denial.code!r}"
    assert denial.details.get("violated_declaration") == "request_schema", denial.details
    assert denial.details.get("field") == expected_field, denial.details
    assert "declared_type" not in denial.details, denial.details
    assert "observed_type" not in denial.details, denial.details
    # (c): details carries no key outside the vocabulary and no value the
    # request did not itself supply -- exactly the 2 keys this denial
    # requires, nothing else.
    assert set(denial.details.keys()) == {"violated_declaration", "field"}, denial.details
    assert_details_vocabulary_values_safe(denial.details, adapter_name=adapter_name)


# ---------------------------------------------------------------------------
# select/<i>
# ---------------------------------------------------------------------------


def test_c31_select_names_the_undeclared_entrys_index(
    adapter: ConformanceAdapter, isolated: ConformanceAdapter, request: pytest.FixtureRequest,
) -> None:
    iso = isolated
    pre_1_11_0, contract_version = _mark_pre_1_11_0_xfail(adapter, request)

    developer, runtime, _app_id = provision_pair(iso, app_prefix="c31s")
    entity = fresh_identifier("c31s")
    iso.create_entity(developer, entity, {"a": "text", "b": "text"})
    iso.insert(runtime, entity, {"a": "x", "b": "y"})

    with pytest.raises(ConformanceDenial) as denial:
        iso.query_page(runtime, entity, ["a", "ghost"])
    _assert_undeclared_field_denial(denial.value, expected_field="select/1", adapter_name=adapter.name)

    # (b): the same request naming only declared fields succeeds.
    items, _next_page = iso.query_page(runtime, entity, ["a", "b"])
    assert len(items) >= 1, f"{adapter.name}: the declared-field replacement returned no items"

    _cross_check_observed_branch(adapter, pre_1_11_0, contract_version)


# ---------------------------------------------------------------------------
# where/<i>/field
# ---------------------------------------------------------------------------


def test_c31_where_names_the_undeclared_predicates_field(
    adapter: ConformanceAdapter, isolated: ConformanceAdapter, request: pytest.FixtureRequest,
) -> None:
    iso = isolated
    pre_1_11_0, contract_version = _mark_pre_1_11_0_xfail(adapter, request)

    developer, runtime, _app_id = provision_pair(iso, app_prefix="c31w")
    entity = fresh_identifier("c31w")
    iso.create_entity(developer, entity, {"a": "text", "b": "text"})
    iso.insert(runtime, entity, {"a": "x", "b": "y"})

    with pytest.raises(ConformanceDenial) as denial:
        iso.query_page(runtime, entity, ["a"], where=[("a", "eq", "x"), ("ghost", "eq", "z")])
    _assert_undeclared_field_denial(denial.value, expected_field="where/1/field", adapter_name=adapter.name)

    # (b): the same request naming only declared fields succeeds.
    items, _next_page = iso.query_page(runtime, entity, ["a"], where=[("a", "eq", "x"), ("b", "eq", "y")])
    assert len(items) >= 1, f"{adapter.name}: the declared-field replacement returned no items"

    _cross_check_observed_branch(adapter, pre_1_11_0, contract_version)


# ---------------------------------------------------------------------------
# order_by/<i>/field
# ---------------------------------------------------------------------------


def test_c31_order_by_names_the_undeclared_entrys_field(
    adapter: ConformanceAdapter, isolated: ConformanceAdapter, request: pytest.FixtureRequest,
) -> None:
    iso = isolated
    pre_1_11_0, contract_version = _mark_pre_1_11_0_xfail(adapter, request)

    developer, runtime, _app_id = provision_pair(iso, app_prefix="c31o")
    entity = fresh_identifier("c31o")
    iso.create_entity(developer, entity, {"a": "text", "b": "text"})
    iso.insert(runtime, entity, {"a": "x", "b": "y"})

    with pytest.raises(ConformanceDenial) as denial:
        iso.query_page(runtime, entity, ["a"], order_by=[("a", "asc"), ("ghost", "asc")])
    _assert_undeclared_field_denial(denial.value, expected_field="order_by/1/field", adapter_name=adapter.name)

    # (b): the same request naming only declared fields succeeds.
    items, _next_page = iso.query_page(runtime, entity, ["a"], order_by=[("a", "asc"), ("b", "asc")])
    assert len(items) >= 1, f"{adapter.name}: the declared-field replacement returned no items"

    _cross_check_observed_branch(adapter, pre_1_11_0, contract_version)


# ---------------------------------------------------------------------------
# operations/<i>/values/<name>
# ---------------------------------------------------------------------------


def test_c31_values_names_the_undeclared_keys_own_name(
    adapter: ConformanceAdapter, isolated: ConformanceAdapter, request: pytest.FixtureRequest,
) -> None:
    iso = isolated
    pre_1_11_0, contract_version = _mark_pre_1_11_0_xfail(adapter, request)

    developer, runtime, _app_id = provision_pair(iso, app_prefix="c31v")
    entity = fresh_identifier("c31v")
    iso.create_entity(developer, entity, {"a": "text", "b": "text"})

    # A 2-operation batch: the FIRST operation names only declared fields,
    # the SECOND carries the undeclared key -- so the expected position is
    # operations/1/values/<name>, never operations/0/..., pinning the
    # batch's own operation index rather than a constant.
    operations = [
        BatchOperation(operation="insert", values={"a": "x"}),
        BatchOperation(operation="insert", values={"a": "y", "ghost": "z"}),
    ]
    with pytest.raises(ConformanceDenial) as denial:
        iso.attempt_batch_with_addresses(runtime, entity, operations)
    _assert_undeclared_field_denial(denial.value, expected_field="operations/1/values/ghost", adapter_name=adapter.name)

    # (b): the SAME 2-operation batch with the undeclared key replaced by a
    # second declared field succeeds -- both keys of the 2nd operation's
    # 2-key values object are declared, so a refusal that singles out one
    # declared key (a regression that would still pass a 1-key (b) leg) is
    # caught here.
    operations_b = [
        BatchOperation(operation="insert", values={"a": "x"}),
        BatchOperation(operation="insert", values={"a": "y", "b": "w"}),
    ]
    affected, _addresses = iso.attempt_batch_with_addresses(runtime, entity, operations_b)
    assert affected >= 2, f"{adapter.name}: the declared-field replacement batch affected {affected!r} rows, expected >= 2"

    _cross_check_observed_branch(adapter, pre_1_11_0, contract_version)
