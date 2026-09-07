"""C-25 -- every successful result a peer declaring contract 1.7.0 returns
carries `request_id`; distinct executions carry distinct values; where
`audit_query` is available, a mutation's value is the value its own audit
events carry (SI-14).

design: docs/design/PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md
D-7, §6.2 "C-25 成功応答の request_id", registered in `conformance-tests/
CONDITIONS.md`. Every test here carries `@pytest.mark.condition("C-25")`
via the module-level `pytestmark`.

Unconditional 1.7.0 obligation (D-1(2)), version-gated exactly like C-21 --
branches on the plug's own declared `contract_version` (`adapter.parse_
semver`, never a string compare), with the runtime-attached `xfail(strict=
True)` read at execution time (`request.node.add_marker`, work order §0.4
item 4):

  - `contract_version < (1, 7, 0)`: `xfail(strict=True)`; the body below
    still runs for real, so an early implementation would XPASS and, under
    `strict=True`, turn that into a hard failure (D-1(7)).
  - `>= (1, 7, 0)`: (1) `QueryResult`/`MutationResult`/`SchemaOperationResult`
    all carry `request_id`; (2) two consecutive, distinct executions carry
    distinct values; (3) where `audit_query` is not `unavailable`, a
    mutation's own `request_id` matches the `request_id` its own audit
    event carries; (4) (WP-1b rework) where `idempotency` is not
    `unavailable`, a resend answered from an idempotency record carries
    the ORIGINAL execution's own `request_id`, not a new one -- this
    row's own proposition on the correlation side, declared-first on
    `idempotency` independently of C-23's own test file.

**Disclosed**: audit correlation (3) is observed only on the plug(s) for
which `audit_query` answers for real -- "green on 4 plugs" here does not,
by itself, mean "audit-correlated on 4 plugs"; which plugs actually reach
(3) is recorded in `conformance-tests/CONDITIONS.md`'s own C-25 row, not
silently assumed uniform. (4) is observed only on the plug(s) for which
`idempotency` is not `unavailable`, recorded the same way.
"""
from __future__ import annotations

import pytest

from adapter import ConformanceAdapter, ConformanceDenial, fresh_identifier, parse_semver
from conftest import provision_pair

pytestmark = pytest.mark.condition("C-25")


def _audit_query_status(adapter: ConformanceAdapter) -> str:
    return adapter.capability_document().get("capabilities", {}).get("audit_query", {}).get("status", "unavailable")


def _expected_branch_for_pre_1_7_0(pre_1_7_0: bool) -> str:
    return "pre_1_7_0" if pre_1_7_0 else "request_id_present"


def test_c25_result_request_id(adapter: ConformanceAdapter, isolated, request: pytest.FixtureRequest) -> None:
    iso = isolated
    contract_version = adapter.capability_document()["contract_version"]
    pre_1_7_0 = parse_semver(contract_version) < (1, 7, 0)
    if pre_1_7_0:
        request.node.add_marker(pytest.mark.xfail(
            reason=(
                f"{adapter.name} declares contract_version {contract_version!r} (< 1.7.0) -- carrying "
                "request_id on every successful result is an unconditional 1.7.0 obligation (design "
                "D-1(2)/D-7); this branch is expected to fail (not merely skip) until this peer's own "
                "version-flip commit lands, per D-1(7)."
            ),
            strict=True,
        ))

    developer, runtime, _app_id = provision_pair(iso, app_prefix="c25")
    entity = fresh_identifier("c25")
    iso.create_entity(developer, entity, {"label": "text"})

    if pre_1_7_0:
        # Work order §6 訂正註 7 (supervisor ruling, post-WP-1-audit,
        # 2026-09-07): a non-asserting RECORD only, not part of the
        # xfail(strict=True) node's pass/fail body -- see test_c21's
        # identical treatment for the reasoning (audit mutation E3/E2: an
        # assert here gives the xfail-marked node an always-available way
        # to fail for a reason OTHER than the real request_id check below,
        # masking a genuinely early implementation instead of exposing it
        # as a strict XPASS). The real, unconditional detection is the
        # body's own `assert request_id1` / `assert request_id2` further
        # down, which only pass for real once R-7 is wired in.
        pre_marker = fresh_identifier("c25pre")
        pre_result = iso.attempt_mutation_with_result(
            runtime, entity, "insert", values={"label": pre_marker}, where_field=None, where_value=None,
        )
        _already_has_request_id = bool(pre_result.get("request_id"))  # recorded, never asserted

    # (1)/(2) MutationResult: two distinct executions carry distinct,
    # present request_id values.
    marker1 = fresh_identifier("c25m1")
    marker2 = fresh_identifier("c25m2")
    result1 = iso.attempt_mutation_with_result(
        runtime, entity, "insert", values={"label": marker1}, where_field=None, where_value=None,
    )
    result2 = iso.attempt_mutation_with_result(
        runtime, entity, "insert", values={"label": marker2}, where_field=None, where_value=None,
    )
    request_id1, request_id2 = result1.get("request_id"), result2.get("request_id")
    assert request_id1, f"{adapter.name}: a successful MutationResult carries no request_id -- {result1!r}"
    assert request_id2, f"{adapter.name}: a successful MutationResult carries no request_id -- {result2!r}"
    assert request_id1 != request_id2, (
        f"{adapter.name}: two distinct mutation executions carried the SAME request_id {request_id1!r}"
    )

    # (1) QueryResult.
    query_result = iso.query_with_budget(runtime, entity, ["label"], "label", marker1)
    assert query_result.get("request_id"), (
        f"{adapter.name}: a successful QueryResult carries no request_id -- {query_result!r}"
    )

    # (1) SchemaOperationResult.
    schema_field = fresh_identifier("c25sf")
    schema_result = iso.schema_operation_with_result(
        developer, entity, "add_field", field=schema_field, field_type="string",
    )
    assert schema_result.get("request_id"), (
        f"{adapter.name}: a successful SchemaOperationResult carries no request_id -- {schema_result!r}"
    )

    # (3) audit correlation, where audit_query is not unavailable.
    audit_status = _audit_query_status(adapter)
    if audit_status != "unavailable":
        control_actor = adapter.control_credential()
        adapter.flush_audit_buffer()
        events = adapter.audit_query(control_actor, {"limit": 200}).get("events", [])
        matching = [e for e in events if e.get("request_id") == request_id1]
        assert matching, (
            f"{adapter.name}: audit_query is {audit_status!r} but no audit event carries the mutation's "
            f"own request_id {request_id1!r} (scanned {len(events)} recent events)"
        )

    # (4) idempotency correlation (design §6.2 C-25 (4), WP-1b rework): a
    # request answered from an idempotency record is not a new execution
    # and carries the ORIGINAL execution's own request_id -- this is C-23
    # (i)'s own property, but observed here from the request_id side
    # (this row's own proposition, not C-23's), so declare-first on
    # `idempotency` rather than assume it from C-23's own test file.
    idempotency_status = (
        adapter.capability_document().get("capabilities", {}).get("idempotency", {}).get("status", "unavailable")
    )
    if idempotency_status != "unavailable":
        replay_key = fresh_identifier("c25idemkey")
        replay_marker = fresh_identifier("c25idemrow")
        first_replay = iso.attempt_mutation_with_result(
            runtime, entity, "insert", values={"label": replay_marker}, where_field=None, where_value=None,
            idempotency_key=replay_key,
        )
        second_replay = iso.attempt_mutation_with_result(
            runtime, entity, "insert", values={"label": replay_marker}, where_field=None, where_value=None,
            idempotency_key=replay_key,
        )
        assert first_replay.get("request_id"), (
            f"{adapter.name}: the original, key-bearing execution carries no request_id -- {first_replay!r}"
        )
        assert second_replay.get("request_id") == first_replay.get("request_id"), (
            f"{adapter.name}: a resend answered from an idempotency record must carry the ORIGINAL "
            f"execution's own request_id, not a new one -- first={first_replay.get('request_id')!r}, "
            f"resend={second_replay.get('request_id')!r}"
        )

    # Work order §6 訂正註 7 (supervisor ruling, post-WP-1-audit,
    # 2026-09-07): the declaration-derived `observed_branch` cross-check
    # (C-07 (ii)'s own `_expected_branch_for_status` form) is done ONLY in
    # the `>= 1.7.0` branch -- see test_c21's identical treatment for the
    # reasoning (audit mutation E3/E2: with this unconditional, `expected_
    # branch` is always "pre_1_7_0" in the `< 1.7.0` branch while `observed_
    # branch` is always hardcoded "request_id_present", so the assert
    # ALWAYS raised there regardless of what the body actually observed,
    # making a genuine strict XPASS structurally impossible). In the
    # `< 1.7.0` branch the body's own unconditional `assert request_id1` /
    # `assert request_id2` above are the entire detection mechanism.
    if not pre_1_7_0:
        observed_branch = "request_id_present"
        expected_branch = _expected_branch_for_pre_1_7_0(pre_1_7_0)
        assert observed_branch == expected_branch, (
            f"{adapter.name}: contract_version {contract_version!r} implies branch {expected_branch!r}, but the "
            f"full body completed without any refusal -- observed {observed_branch!r} (an early implementation "
            "ahead of this peer's own version-flip commit, D-1(7))"
        )
