"""C-07 -- atomic operations commit wholly or roll back; retries use
declared idempotency/preconditions (SI-11).

design: docs/design/PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md
D-6.7 / D-6.11, registered in `conformance-tests/CONDITIONS.md`, supervisor
ruling S-4. Every test here carries `@pytest.mark.condition("C-07")` via
the module-level `pytestmark`.

Two vectors, mirroring C-16's own "V1 positive / V2 atomicity" house style
but scoped to a SINGLE entity's own batch dispatcher
(`attempt_batch_with_addresses`, no capability gate) rather than
`attempt_cross_entity_batch` (gated on `cross_entity_mutation`, C-16's own
territory -- not duplicated here):

  (i) **atomicity**: a single-entity batch mixing one valid insert and one
      invalid item (an unknown field name) is refused wholly, with ZERO
      rows written -- confirmed by a real read (`count`), not merely by
      the denial itself. The denial's own CODE is not pinned to one exact
      value here (measured through contract 1.10.0: `r2db-api`/
      `r2db-api-http` answered `NOT_FOUND` for an unknown field name in
      this position, `MitateDB-api`/`MitateDB-api-http` answered
      `VALIDATION_FAILED`; contract 1.11.0 (subordinate ruling 16, the
      undeclared-field refusal alignment) unifies both peers on
      `VALIDATION_FAILED` for this exact probe -- pinning the exact code
      is C-03/C-17's/C-31's own territory, not C-07's atomicity
      proposition) -- any contract error code is still accepted, so the
      assertion here stays squarely about the rollback, not the code.
  (ii) **idempotency declaration branch** (C-17-shaped declare-first,
       supervisor ruling S-4): both currently-registered peers declare
       `idempotency: unavailable` (design D-6.7's own module note). The
       `unavailable` branch asserts a request carrying `idempotency_key`
       (port v1.11's own `BatchOperation.idempotency_key`) is refused with
       `CAPABILITY_UNSUPPORTED` *before* execution, with zero side
       effects -- never skipped. The `unavailable`-other branch (currently
       unreached by any registered adapter, kept honest for a future one)
       asserts a resend of the SAME key returns the SAME result. Per-plug
       non-vacuity (`test_c17_declaration_agreement.py::test_declared_entities_satisfy_declaration_required_completeness` precedent): each plug's own test asserts
       that ONE of the two branches was actually observed within that
       plug's own run -- a session-crossing aggregate guard does not work
       under `-n 5 --dist loadgroup` (each plug is its own xdist group).

Uses `conftest.isolated`/`provision_pair` (port v1.11's own `isolated_
application_surface()`, C-05's primitive) rather than the ordinary `fx`
fixture: this condition needs one ordinary, working application, and `fx`
used per test with no teardown permanently grows the session-scoped
adapter's own `applications` registry (measured, WP-5) -- see `conftest.
isolated`'s own docstring for the full, four-round measurement history.
Every `attempt_batch_with_addresses` call in this file uses a flat
`values` dict (no `where` filter), which stays within the isolated
profile's own small `operation_depth` bound on every plug that enforces
it -- see `conftest.provision_pair`'s own docstring for the pitfall this
file avoids.
"""
from __future__ import annotations

import pytest

from adapter import BatchOperation, ConformanceAdapter, ConformanceDenial, fresh_identifier, load_contract_error_codes
from conftest import provision_pair

pytestmark = pytest.mark.condition("C-07")


def _idempotency_status(adapter: ConformanceAdapter) -> str:
    return adapter.capability_document().get("capabilities", {}).get("idempotency", {}).get("status", "unavailable")


def _expected_branch_for_status(status: str) -> str:
    """WP-5 rework (review finding 4): the branch a plug declaring
    `status` SHOULD take, computed independently of whichever string
    literal a given `if/else` arm happens to assign to `observed_branch`.
    Used to replace `assert observed_branch is not None` -- an assertion
    the previous `if/else` could never fail (both arms assigned a
    non-`None` string), so it never actually exercised anything. Cross-
    checking the string a branch assigned against what this function says
    it SHOULD have assigned turns this back into a real, falsifiable
    check: a mutation that swaps which literal either arm assigns (e.g. a
    copy-paste error making the 'unavailable' arm record 'retry_same_
    result') is caught here even though the arm's own content assertions
    (the CAPABILITY_UNSUPPORTED code check, or the resend-equality check)
    are unrelated to and do not themselves catch that particular mistake."""
    return "unavailable" if status == "unavailable" else "retry_same_result"


def test_c07_i_single_entity_batch_with_one_invalid_item_rolls_back_fully(
    adapter: ConformanceAdapter, isolated
) -> None:
    iso = isolated
    developer, runtime, _app_id = provision_pair(iso, app_prefix="c07atomic")
    entity = fresh_identifier("c07atomic")
    iso.create_entity(developer, entity, {"label": "text"})
    count_before = iso.count(runtime, entity)

    bad_field = fresh_identifier("c07_nosuchfield")
    with pytest.raises(ConformanceDenial) as ei:
        iso.attempt_batch_with_addresses(runtime, entity, [
            BatchOperation(operation="insert", values={"label": "ok-one"}),
            BatchOperation(operation="insert", values={bad_field: "x"}),
        ])
    assert ei.value.code in load_contract_error_codes(), f"denial code {ei.value.code!r} is not a contract error code"
    count_after = iso.count(runtime, entity)
    assert count_after == count_before, (
        f"{adapter.name}: row count changed ({count_before} -> {count_after}) despite the whole batch being "
        "denied -- the valid item was not rolled back alongside the invalid one"
    )


def test_c07_ii_idempotency_declaration_branch(adapter: ConformanceAdapter, isolated) -> None:
    iso = isolated
    status = _idempotency_status(adapter)
    developer, runtime, _app_id = provision_pair(iso, app_prefix="c07idem")
    entity = fresh_identifier("c07idem")
    iso.create_entity(developer, entity, {"label": "text"})
    count_before = iso.count(runtime, entity)

    observed_branch: str | None = None
    if status == "unavailable":
        key = fresh_identifier("c07key")
        with pytest.raises(ConformanceDenial) as ei:
            iso.attempt_batch_with_addresses(runtime, entity, [
                BatchOperation(operation="insert", values={"label": "x"}, idempotency_key=key),
            ])
        assert ei.value.code == "CAPABILITY_UNSUPPORTED", (
            f"{adapter.name}: idempotency is declared 'unavailable', but a request carrying idempotency_key "
            f"was refused with {ei.value.code!r} instead of CAPABILITY_UNSUPPORTED"
        )
        count_after = iso.count(runtime, entity)
        assert count_after == count_before, (
            f"{adapter.name}: row count changed ({count_before} -> {count_after}) despite an idempotency_"
            "key-bearing request being refused as unavailable -- it must carry zero side effects"
        )
        observed_branch = "unavailable"
    else:
        key = fresh_identifier("c07key")
        affected1, addresses1 = iso.attempt_batch_with_addresses(runtime, entity, [
            BatchOperation(operation="insert", values={"label": "x"}, idempotency_key=key),
        ])
        affected2, addresses2 = iso.attempt_batch_with_addresses(runtime, entity, [
            BatchOperation(operation="insert", values={"label": "x"}, idempotency_key=key),
        ])
        assert affected1 == affected2 and addresses1 == addresses2, (
            f"{adapter.name}: idempotency is declared {status!r} (not 'unavailable'), but resending the same "
            f"idempotency_key returned a different result ({affected1!r}/{addresses1!r} vs "
            f"{affected2!r}/{addresses2!r})"
        )
        observed_branch = "retry_same_result"

    # WP-5 rework (review finding 4): replaces `assert observed_branch is
    # not None`, which the exhaustive if/else above could never fail
    # (both arms always assign a non-None string -- see `_expected_
    # branch_for_status`'s own docstring for why that made the old
    # assertion structurally dead). Cross-checking the recorded branch
    # against the declaration-derived expectation is genuinely
    # falsifiable: a mutation that scrambles which literal either arm
    # assigns is caught here.
    expected_branch = _expected_branch_for_status(status)
    assert observed_branch == expected_branch, (
        f"{adapter.name}: idempotency status {status!r} recorded branch {observed_branch!r}, expected "
        f"{expected_branch!r} -- this test's own per-plug non-vacuity requirement"
    )
