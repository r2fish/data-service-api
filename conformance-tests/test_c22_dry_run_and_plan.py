"""C-22 -- `dry_run` reaches the decision a real request would reach and
leaves no externally visible state change; `plan` is deterministic, honored
against unchanged schema, and refused with `PRECONDITION_FAILED` once
stale (SI-11, SI-15, SI-08).

design: docs/design/PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md
D-4, §6.2 "C-22 dry_run", registered in `conformance-tests/CONDITIONS.md`.
Every test here carries `@pytest.mark.condition("C-22")` via the
module-level `pytestmark`.

Declare-first, capability `dry_run` (contract 1.7.0, new), written in the
C-07 (ii)/C-20 declare-first house style: ONE test branches internally on
the plug's own declared status (never `pytest.skip`), records `observed_
branch`, and cross-checks it against the branch the declaration implies:

  - `unavailable` branch: a mutation carrying `dry_run: true` (or a bare
    `plan`) is refused with `CAPABILITY_UNSUPPORTED` before execution --
    zero rows changed.
  - `enabled`/`partial`/`planned` branch ("dry_run_enabled"): decision
    agreement, refusal side (design C-22 (1), WP-1b rework: authorization,
    destructive confirmation, precondition and limit each refuse a
    dry_run request with the SAME code the identical real request gets;
    the precondition/limit sub-legs are themselves declare-first on
    `revision_preconditions`/`request_budget` and disclosed, not silently
    run, where either is `unavailable` on this plug), decision agreement
    (success side: `affected` matches the real request, `committed:
    false`), external-effect absence (rows/catalog/revision unchanged;
    audit unchanged where `audit_query` is available -- declare-first on
    that capability too, disclosed as observed out of scope otherwise),
    no `assigned_addresses` on a dry-run mutation result, a schema dry
    run's `descriptor` matching the real apply's post-apply catalog while
    its `revision` stays the PRE-apply value, plan determinism (two dry
    runs of the identical request return the identical token), plan
    validity (the same plan against unchanged schema lets the real
    request through), plan staleness after a schema change and after a
    body change alike (`PRECONDITION_FAILED`, `violated_declaration:
    plan`), the digest's own scope -- a `transaction: "atomic"`-only
    change under the same plan (an always-available `MutationRequest` key,
    run unconditionally) and, where this plug declares `request_budget` as
    anything other than `unavailable`, a `budget`-only change too -- each
    also triggers staleness, proof the digest is not `operations`-only,
    and the one externally observable ordering fact (D-4(2)): a stale plan
    on an UNCONFIRMED destructive operation is refused for the missing
    confirmation first, not for the stale plan -- proved via `drop_entity`
    where this plug provides it, a destructive `delete` dry run otherwise
    (declare-first on `capabilities.schema_operations`, WP-1c rework).

**Disclosed (D-4 開示事項, carried into this row)**: address-sequence
consumption by a dry run is possible but not asserted here (permitted, not
required); `plan` commits to the Application's own schema revision, so a
schema operation on any OTHER entity of the same Application also
invalidates it (fail-closed, not a defect); `plan` is not an authorization
snapshot. **WP-1b rework, disclosed scope limits**: the (1) authorization
sub-leg accepts `SurfaceAbsent` from BOTH the dry_run and the real probe
alike (a plug whose session-role model has no real per-role entry point at
all for the probe this leg uses, e.g. a session type structurally lacking
the method, rather than a peer denial) -- never from only one side, which
would itself be a real finding. The (1) precondition/limit sub-legs are
narrowed to the plugs that declare `revision_preconditions`/`request_
budget` as anything other than `unavailable`, disclosed rather than run
unconditionally. **WP-1c rework, disclosed scope limits**: the (10)
digest-scope leg's `budget` half is narrowed the same way `request_
budget` already narrows the (1) limit sub-leg above -- a plug refusing
any `budget`-carrying request outright (provisional gate, D-1) can never
reach this leg's own `PRECONDITION_FAILED`; the `transaction` half is
never narrowed. The (11) ordering leg's destructive primitive is
declare-first on `capabilities.schema_operations` (`drop_entity` in its
own `unsupported` list, or the whole surface `unavailable`, falls back to
`delete`); a `SurfaceAbsent` from a `drop_entity` this plug's declaration
did NOT name unsupported is tolerated the same way rather than failing
this leg -- the declared-vs-actual disagreement it would represent is
test_c06_destructive_confirmation.py's own territory.
"""
from __future__ import annotations

import pytest

from adapter import (
    VALID_CONFIRMATION,
    BatchOperation,
    ConformanceAdapter,
    ConformanceDenial,
    SurfaceAbsent,
    fresh_identifier,
)
from conftest import provision_pair

pytestmark = pytest.mark.condition("C-22")


def _status(adapter: ConformanceAdapter) -> str:
    return adapter.capability_document().get("capabilities", {}).get("dry_run", {}).get("status", "unavailable")


def _capability_status(adapter: ConformanceAdapter, name: str) -> str:
    return adapter.capability_document().get("capabilities", {}).get(name, {}).get("status", "unavailable")


def _drop_entity_declared_unsupported(adapter: ConformanceAdapter) -> bool:
    """(11) ordering, declare-first branch: `capabilities.schema_operations`
    (test_c06_destructive_confirmation.py's own `_schema_operations_
    capability`/`_assert_drop_entity_absence_agrees_with_declaration`,
    mirrored here rather than imported -- this module stays independent of
    that file's own destructive-confirmation fixtures) says `drop_entity`
    is NOT a real primitive on this plug either by declaring the whole
    surface `unavailable` or by naming `drop_entity` in its own
    `unsupported` list (MitateDB-api's real declaration, measured:
    `status: "partial"`, `unsupported` includes `"drop_entity"`)."""
    schema_ops = adapter.capability_document().get("capabilities", {}).get("schema_operations", {})
    return schema_ops.get("status", "unavailable") == "unavailable" or "drop_entity" in (
        schema_ops.get("unsupported") or []
    )


def _assert_dry_run_matches_real_refusal(adapter: ConformanceAdapter, label: str, call) -> None:
    """(1) decision agreement, refusal side (design D-4(2)/C-22 (1)): `call`
    is a zero-arg callable taking one keyword, `dry_run`, and presenting
    the SAME request either way -- a request this suite constructs so it
    is refused regardless of `dry_run`. Since a refused request never
    executes, presenting it twice (once `dry_run=True`, once `dry_run=
    False`) is safe: both must be refused, and with the identical code.
    `SurfaceAbsent` (a structural absence, not a peer denial -- e.g. no
    real per-plug entry point exists at all for the probe this leg uses)
    is accepted from BOTH calls alike, never from only one -- a genuine
    denial on one side and a structural absence on the other would itself
    be evidence dry_run is NOT walking the same real gates a real request
    does."""
    dry_outcome: ConformanceDenial | SurfaceAbsent
    try:
        call(dry_run=True)
    except ConformanceDenial as exc:
        dry_outcome = exc
    except SurfaceAbsent as exc:
        dry_outcome = exc
    else:
        raise AssertionError(f"{adapter.name}: C-22 (1) {label}: the dry_run=True probe was not refused at all")

    real_outcome: ConformanceDenial | SurfaceAbsent
    try:
        call(dry_run=False)
    except ConformanceDenial as exc:
        real_outcome = exc
    except SurfaceAbsent as exc:
        real_outcome = exc
    else:
        raise AssertionError(f"{adapter.name}: C-22 (1) {label}: the dry_run=False probe was not refused at all")

    if isinstance(dry_outcome, SurfaceAbsent) or isinstance(real_outcome, SurfaceAbsent):
        assert isinstance(dry_outcome, SurfaceAbsent) and isinstance(real_outcome, SurfaceAbsent), (
            f"{adapter.name}: C-22 (1) {label}: dry_run={dry_outcome!r} vs real={real_outcome!r} -- one side hit a "
            "real peer refusal while the other found no real entry point at all; dry_run must walk the SAME gate"
        )
        return

    assert dry_outcome.code == real_outcome.code, (
        f"{adapter.name}: C-22 (1) {label}: dry_run refused with {dry_outcome.code!r}, the identical real request "
        f"with {real_outcome.code!r} -- dry_run must reach the SAME refusal a real request would"
    )


def _expected_branch_for_status(status: str) -> str:
    return "unavailable" if status == "unavailable" else "dry_run_enabled"


def _revision_of(result: dict) -> str:
    """The response `revision` of a real, successful `schema_operation_
    with_result` call. `SchemaOperationResult.revision` (spec/data-
    service-api.v1.json `schemas.SchemaOperationResult`) is `required`
    and always present on a real response -- unlike `EntityDescriptor`,
    which carries no `revision` property at all (`definitions.
    EntityDescriptor`, `additionalProperties: false`), and unlike
    `CatalogDocument`, which carries no document-level revision either.
    A catalog row's `.get("revision")` is therefore always `None`; this
    helper is the ONLY contract-defined way to observe a real revision
    value."""
    revision = result.get("revision")
    assert revision is not None, f"schema_operation_with_result carries no 'revision' -- {result!r}"
    return revision


def _revision_advanced_by_one(before: str, after: str) -> bool:
    """True when `after` is exactly one real commit ahead of `before`.

    Both currently-registered peers keep their schema revision as a
    monotonic integer counter incremented by exactly one per committed
    schema operation (`r2db-api/src/r2db_api/structured.py:1583`
    `self.schema_revision += 1`; `MitateDB-api/src/mitatedb_api/
    backend_sqlite.py:207`/`:250` `self._schema_revision += 1`; the
    Postgres backends mirror this via `_bump_revision`/`_bump_schema_
    revision`), and `SchemaOperationResult.revision` reports that
    counter stringified (`schema_operation_with_result`'s own
    docstring, `conformance-tests/adapter.py`). Comparing
    `int(after) == int(before) + 1` catches a CONFLICT-refused (or
    CAPABILITY_UNSUPPORTED-refused) `alter_field` that silently also
    bumps the counter -- exactly the mutation design docs/design/
    PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md's C-20 (6)
    row guards against (monotone S-g) -- as a delta of 2 rather than 1,
    when exactly one real, harmless schema commit is known to separate
    `before` and `after`."""
    return int(after) == int(before) + 1


def test_c22_dry_run_and_plan(adapter: ConformanceAdapter, isolated) -> None:
    iso = isolated
    status = _status(adapter)
    developer, runtime, _app_id = provision_pair(iso, app_prefix="c22")
    entity = fresh_identifier("c22")
    iso.create_entity(developer, entity, {"label": "text"})
    count_before_all = iso.count(runtime, entity)

    observed_branch: str
    if status == "unavailable":
        with pytest.raises(ConformanceDenial) as ei:
            iso.attempt_mutation_with_result(
                runtime, entity, "insert", values={"label": "x"}, where_field=None, where_value=None, dry_run=True,
            )
        assert ei.value.code == "CAPABILITY_UNSUPPORTED", (
            f"{adapter.name}: dry_run is 'unavailable', but a dry_run=true request was refused with "
            f"{ei.value.code!r} instead of CAPABILITY_UNSUPPORTED"
        )
        assert iso.count(runtime, entity) == count_before_all, (
            f"{adapter.name}: a request refused as unavailable must have zero side effects"
        )

        with pytest.raises(ConformanceDenial) as ei_plan:
            iso.attempt_mutation_with_result(
                runtime, entity, "insert", values={"label": "y"}, where_field=None, where_value=None,
                plan="whatever-opaque-token",
            )
        assert ei_plan.value.code == "CAPABILITY_UNSUPPORTED", (
            f"{adapter.name}: a bare 'plan' was refused with {ei_plan.value.code!r} instead of "
            "CAPABILITY_UNSUPPORTED while dry_run is unavailable"
        )
        assert iso.count(runtime, entity) == count_before_all
        observed_branch = "unavailable"
    else:
        # (1) decision agreement, refusal side (design D-4(2)): for each of
        # authorization/destructive-confirmation/precondition/limit, a
        # dry_run request and the identical real request return the SAME
        # refusal code. Each sub-leg is itself declare-first on the
        # capability the refusal in question depends on -- exactly the
        # same per-plug non-vacuity discipline this whole file already
        # uses for `dry_run` itself -- and is disclosed, not silently
        # skipped, where that capability is not available on this plug.

        # authorization: a runtime credential attempting a developer-only
        # schema operation (design's own FORBIDDEN example, `structured_
        # operations.dry_run.decision`'s "authorization refusals"). Some
        # plugs have no real per-role entry point at all for this probe
        # (`SurfaceAbsent`, e.g. a session type that structurally lacks the
        # method) -- `_assert_dry_run_matches_real_refusal` accepts that
        # from BOTH sides alike, never only one.
        auth_field = fresh_identifier("c22authfield")

        def _auth_probe(*, dry_run: bool) -> None:
            iso.schema_operation_with_result(
                runtime, entity, "add_field", field=auth_field, field_type="string", dry_run=dry_run,
            )

        _assert_dry_run_matches_real_refusal(adapter, "authorization", _auth_probe)

        # destructive confirmation: an UNCONFIRMED destructive delete is
        # refused DESTRUCTIVE_CONFIRMATION_REQUIRED regardless of dry_run
        # -- no capability gate (every registered plug supports `delete`).
        confirm_marker = fresh_identifier("c22confirm")

        def _confirm_probe(*, dry_run: bool) -> None:
            iso.attempt_mutation_with_result(
                runtime, entity, "delete", values=None, where_field="label", where_value=confirm_marker,
                destructive=True, dry_run=dry_run,
            )

        _assert_dry_run_matches_real_refusal(adapter, "destructive confirmation", _confirm_probe)

        # precondition: an `expected_revision` that cannot match is
        # refused PRECONDITION_FAILED, but only where the plug declares
        # `revision_preconditions` as anything other than `unavailable`
        # (the same declare-first gate `test_c18_revision_precondition_
        # semantics.py` already uses) -- disclosed, not silently run, on
        # the plug(s) where it does not apply.
        if _capability_status(adapter, "revision_preconditions") != "unavailable":
            precond_marker = fresh_identifier("c22precond")
            # Seed a real row to update against (test_c18_revision_
            # precondition_semantics.py's own `test_revision_mismatch_is_
            # precondition_failed` recipe: `update` + a matching `where`,
            # never `insert`, which has no existing row for a precondition
            # to be checked against in the first place).
            iso.attempt_mutation(
                runtime, entity, "insert", values={"label": precond_marker}, where_field=None, where_value=None,
            )

            def _precondition_probe(*, dry_run: bool) -> None:
                iso.attempt_mutation_with_result(
                    runtime, entity, "update", values={"label": precond_marker}, where_field="label",
                    where_value=precond_marker, expected_revision=fresh_identifier("c22bogusrev"), dry_run=dry_run,
                )

            _assert_dry_run_matches_real_refusal(adapter, "precondition", _precondition_probe)
        # else: disclosed in this row's own C-22 CONDITIONS.md entry --
        # `revision_preconditions: unavailable` on this plug leaves this
        # sub-leg unobserved here (C-18 is its own territory).

        # limit: a `budget.batch_items` narrower than the request's own
        # operation count is refused LIMIT_EXCEEDED, but only where the
        # plug declares `request_budget` as anything other than
        # `unavailable` -- disclosed, not silently run, otherwise (C-24's
        # own declare-first gate covers `request_budget`'s own semantics;
        # this leg only needs ONE reliable narrowed-bound refusal, not the
        # full C-24 vector).
        if _capability_status(adapter, "request_budget") != "unavailable":
            limit_marker_a = fresh_identifier("c22limita")
            limit_marker_b = fresh_identifier("c22limitb")
            limit_marker_c = fresh_identifier("c22limitc")

            def _limit_probe(*, dry_run: bool) -> None:
                iso.attempt_batch_with_result(
                    runtime, entity,
                    [
                        BatchOperation(operation="insert", values={"label": limit_marker_a}),
                        BatchOperation(operation="insert", values={"label": limit_marker_b}),
                        BatchOperation(operation="insert", values={"label": limit_marker_c}),
                    ],
                    dry_run=dry_run, budget={"batch_items": 2},
                )

            _assert_dry_run_matches_real_refusal(adapter, "limit", _limit_probe)
        # else: disclosed -- `request_budget: unavailable` on this plug
        # leaves this sub-leg unobserved here.

        marker = fresh_identifier("c22row")
        insert_kwargs = dict(
            session=runtime, entity=entity, operation="insert",
            values={"label": marker}, where_field=None, where_value=None,
        )

        # (3) external-effect absence, audit half (design §6.2 C-22 (3),
        # §5 U-2 = (A)): where `audit_query` is available, a dry run
        # writes no audit event either -- snapshotted around the SAME two
        # dry runs (6) below drives, rather than a separate probe, so this
        # leg costs no extra request. Declare-first on `audit_query`
        # (matching test_c09's own convention); where it is not available
        # on this plug, this leg is disclosed as observed out of scope,
        # not silently skipped.
        audit_status = _capability_status(adapter, "audit_query")
        audit_count_before: int | None = None
        if audit_status != "unavailable":
            control_actor = iso.control_credential()
            try:
                audit_count_before = len(iso.audit_query(control_actor, {"limit": 1000}).get("events", []))
            except SurfaceAbsent:
                # design §8.4's extended SurfaceAbsent meaning: declared
                # available yet structurally absent is itself a genuine
                # finding, not this leg's concern -- test_c09's own
                # territory. Leave this leg unobserved here too.
                audit_count_before = None

        # (3) external-effect absence, row-count half: snapshotted
        # immediately before the SAME two dry runs (6) below drives --
        # never `count_before_all` (captured before this entity had any
        # rows at all), which the (1) precondition sub-leg above may
        # already have moved on by exactly one real, harmless seed insert
        # (declare-first on `revision_preconditions`, lines 281-301) on a
        # plug where that sub-leg actually runs. The dry_run-must-not-
        # change-state assertion below is about the two dry runs
        # themselves, not about the sub-legs that preceded them, so its
        # baseline is retaken right here, immediately before them --
        # mirroring the audit half's own before/after bracket above.
        count_before_dry_run = iso.count(runtime, entity)

        # (6) plan determinism: two dry runs of the identical request
        # return the identical token.
        dry1 = iso.attempt_mutation_with_result(**insert_kwargs, dry_run=True)
        dry2 = iso.attempt_mutation_with_result(**insert_kwargs, dry_run=True)

        if audit_count_before is not None:
            audit_count_after = len(iso.audit_query(control_actor, {"limit": 1000}).get("events", []))
            assert audit_count_after == audit_count_before, (
                f"{adapter.name}: C-22 (3) audit invariant: audit_query reported {audit_count_before} events "
                f"before two dry runs and {audit_count_after} after -- a dry run must write no audit event "
                "(design §5 U-2 = (A))"
            )
        assert dry1.get("committed") is False, f"{adapter.name}: dry-run result carries committed={dry1.get('committed')!r}"
        assert dry1.get("affected") == 1, f"{adapter.name}: dry-run 'affected' does not report what a real insert would: {dry1!r}"
        assert dry1.get("assigned_addresses") in (None, []), (
            f"{adapter.name}: a dry-run mutation result must not carry assigned_addresses -- {dry1!r}"
        )
        plan = dry1.get("plan")
        assert plan, f"{adapter.name}: a dry-run result carries no 'plan' -- {dry1!r}"
        assert dry2.get("plan") == plan, (
            f"{adapter.name}: two dry runs of the identical request returned different plans -- "
            f"{plan!r} vs {dry2.get('plan')!r}"
        )

        # (3) external-effect absence.
        assert iso.count(runtime, entity) == count_before_dry_run, (
            f"{adapter.name}: a dry run changed row count ({count_before_dry_run} -> {iso.count(runtime, entity)})"
        )
        assert iso.select_eq(runtime, entity, ["label"], "label", marker) == [], (
            f"{adapter.name}: a dry-run insert left a real, readable row behind"
        )

        # (7) plan valid: the same plan against unchanged schema lets the
        # real request through.
        real = iso.attempt_mutation_with_result(**insert_kwargs, plan=plan)
        assert real.get("committed") is not False, f"{adapter.name}: a real apply reported committed=False -- {real!r}"
        assert real.get("affected") == 1, real
        assert len(iso.select_eq(runtime, entity, ["label"], "label", marker)) == 1, (
            f"{adapter.name}: the real apply carrying a valid plan did not actually commit"
        )

        # (9) plan mismatch: a DIFFERENT body presented with a plan taken
        # for another body is refused, never silently accepted.
        other_marker = fresh_identifier("c22other")
        with pytest.raises(ConformanceDenial) as ei_body:
            iso.attempt_mutation_with_result(
                runtime, entity, "insert", values={"label": other_marker}, where_field=None, where_value=None,
                plan=plan,
            )
        assert ei_body.value.code == "PRECONDITION_FAILED", (
            f"{adapter.name}: a plan taken for one body, presented with a different body -> "
            f"{ei_body.value.code!r}, expected PRECONDITION_FAILED"
        )
        assert ei_body.value.details.get("violated_declaration") == "plan", ei_body.value.details

        # (8) plan staleness after a schema change.
        marker2 = fresh_identifier("c22row2")
        insert2_kwargs = dict(
            session=runtime, entity=entity, operation="insert",
            values={"label": marker2}, where_field=None, where_value=None,
        )
        plan2 = iso.attempt_mutation_with_result(**insert2_kwargs, dry_run=True).get("plan")
        assert plan2, f"{adapter.name}: a second dry run carries no plan"
        iso.schema_operation_with_result(developer, entity, "add_field", field=fresh_identifier("c22f"), field_type="string")
        with pytest.raises(ConformanceDenial) as ei_stale:
            iso.attempt_mutation_with_result(**insert2_kwargs, plan=plan2)
        assert ei_stale.value.code == "PRECONDITION_FAILED", (
            f"{adapter.name}: a plan taken before a schema change, presented after it -> "
            f"{ei_stale.value.code!r}, expected PRECONDITION_FAILED"
        )
        assert ei_stale.value.details.get("violated_declaration") == "plan", ei_stale.value.details
        assert iso.select_eq(runtime, entity, ["label"], "label", marker2) == [], (
            f"{adapter.name}: the stale-plan apply must not have executed"
        )

        # (10) digest scope: proof the digest is not operations-only. The
        # always-available sub-leg uses `transaction` -- `MutationRequest`'s
        # own PRE-EXISTING optional key, not behind any declare-first
        # capability gate the way `budget` is behind `request_budget` --
        # so it runs unconditionally, on every plug: the SAME plan
        # re-presented with `transaction: "atomic"` ADDED (the peer's own
        # default value, semantically a no-op) must still be refused
        # PRECONDITION_FAILED, proving the digest covers more than
        # `operations` regardless of what this plug declares.
        marker3 = fresh_identifier("c22row3")
        insert3_kwargs = dict(
            session=runtime, entity=entity, operation="insert",
            values={"label": marker3}, where_field=None, where_value=None,
        )
        plan3 = iso.attempt_mutation_with_result(**insert3_kwargs, dry_run=True).get("plan")
        assert plan3, f"{adapter.name}: a third dry run carries no plan"
        with pytest.raises(ConformanceDenial) as ei_transaction:
            iso.attempt_mutation_with_result(**insert3_kwargs, plan=plan3, transaction="atomic")
        assert ei_transaction.value.code == "PRECONDITION_FAILED", (
            f"{adapter.name}: the same plan re-presented with an ADDED transaction: 'atomic' (the peer's own "
            f"default value, nothing else different) -> {ei_transaction.value.code!r}, expected "
            "PRECONDITION_FAILED (the plan digest must cover transaction too, not operations-only)"
        )
        assert ei_transaction.value.details.get("violated_declaration") == "plan", ei_transaction.value.details

        # Declare-first (this row's own C-22 CONDITIONS.md addendum): the
        # budget-carrying sub-leg only where this plug declares `request_
        # budget` as anything other than `unavailable` -- a plug that
        # refuses a request CARRYING `budget` at all with CAPABILITY_
        # UNSUPPORTED before precondition evaluation (provisional gate,
        # design D-1) can never reach THIS leg's own PRECONDITION_FAILED;
        # disclosed, not silently run, exactly like the (1) precondition/
        # limit sub-legs above. The `transaction` sub-leg above already
        # proves the digest is not `operations`-only unconditionally, so
        # this half adds coverage rather than being load-bearing alone.
        if _capability_status(adapter, "request_budget") != "unavailable":
            marker4 = fresh_identifier("c22row4")
            insert4_kwargs = dict(
                session=runtime, entity=entity, operation="insert",
                values={"label": marker4}, where_field=None, where_value=None,
            )
            plan4 = iso.attempt_mutation_with_result(**insert4_kwargs, dry_run=True).get("plan")
            assert plan4, f"{adapter.name}: a fourth dry run carries no plan"
            # Declaration-based, not a fixed value: this leg only needs the
            # ADDED budget to be in-bound (so the refusal it drives is the
            # digest's own PRECONDITION_FAILED, never an out-of-bound
            # VALIDATION_FAILED reached first) -- this deployment's own
            # declared `execution_ms` bound, never a hardcoded literal,
            # which a narrow isolation profile can sit below.
            declared_execution_ms = iso.capability_document().get("limits", {}).get("execution_ms")
            assert isinstance(declared_execution_ms, int), (
                f"{adapter.name}: capability_document()['limits']['execution_ms'] is not an int -- "
                f"{adapter.capability_document().get('limits')!r}"
            )
            with pytest.raises(ConformanceDenial) as ei_budget:
                iso.attempt_mutation_with_result(
                    **insert4_kwargs, plan=plan4, budget={"execution_ms": declared_execution_ms},
                )
            assert ei_budget.value.code == "PRECONDITION_FAILED", (
                f"{adapter.name}: the same plan re-presented with an ADDED budget (nothing else different) -> "
                f"{ei_budget.value.code!r}, expected PRECONDITION_FAILED (the plan digest must cover budget too)"
            )
            assert ei_budget.value.details.get("violated_declaration") == "plan", ei_budget.value.details
        # else: disclosed in this row's own C-22 CONDITIONS.md entry --
        # `request_budget: unavailable` on this plug leaves the budget half
        # of this leg unobserved here (the `transaction` half above still
        # runs unconditionally, on every plug, regardless).

        # (5) schema dry run: descriptor matches the post-apply catalog;
        # revision stays the PRE-apply value (design D-4 S-j / §6.2 C-22
        # (5)). A catalog row's `.get("revision")` is always `None`:
        # `EntityDescriptor` (spec/data-service-api.v1.json `definitions.
        # EntityDescriptor`, `additionalProperties: false`) carries no
        # `revision` key at all, so comparing against it would assert
        # nothing (see `_revision_of`'s docstring above, mirrored from
        # `test_c20_constraint_declaration_agreement.py`, same name/
        # content there). `SchemaOperationResult.revision` (`required`)
        # is the only contract-defined way to observe a real revision, so
        # this leg brackets the dry run with two harmless real `add_
        # field` commits instead: the FIRST establishes R ("now"), the
        # dry run's own `revision` must equal R (not the not-yet-
        # established post-apply value), and the SECOND establishes
        # R+1, proving the dry run itself did not advance the counter.
        schema_field = fresh_identifier("c22sf")
        revision_r = _revision_of(
            iso.schema_operation_with_result(
                developer, entity, "add_field", field=fresh_identifier("c22sfa"), field_type="string",
            )
        )
        schema_dry = iso.schema_operation_with_result(
            developer, entity, "add_field", field=schema_field, field_type="string", dry_run=True,
        )
        assert schema_dry.get("revision") == revision_r, (
            f"{adapter.name}: a dry-run schema operation must report the PRE-apply (current) revision -- "
            f"expected {revision_r!r}, got {schema_dry.get('revision')!r}"
        )
        descriptor = schema_dry.get("descriptor")
        assert isinstance(descriptor, dict) and schema_field in descriptor.get("fields", []), (
            f"{adapter.name}: a dry-run schema operation's 'descriptor' does not name the field it would "
            f"add -- {descriptor!r}"
        )
        catalog_after_dry = {row["entity"]: row for row in iso.catalog_document(developer)["entities"]}
        assert schema_field not in catalog_after_dry[entity]["fields"], (
            f"{adapter.name}: a dry-run add_field left a real field behind"
        )
        revision_r_plus_1 = _revision_of(
            iso.schema_operation_with_result(developer, entity, "add_field", field=schema_field, field_type="string")
        )
        assert _revision_advanced_by_one(revision_r, revision_r_plus_1), (
            f"{adapter.name}: the dry-run schema operation must not itself advance the real revision counter -- "
            f"{revision_r!r} then {revision_r_plus_1!r} after exactly one further real commit, expected a "
            "one-commit advance"
        )
        catalog_after = {row["entity"]: row for row in iso.catalog_document(developer)["entities"]}
        assert schema_field in catalog_after[entity]["fields"], (
            f"{adapter.name}: the real (non-dry-run) add_field did not actually add the field"
        )

        # (11) ordering: a stale plan on an UNCONFIRMED destructive
        # operation is refused for the missing confirmation first, never
        # PRECONDITION_FAILED (design D-4(2)). The plan itself must come
        # from a CONFIRMED dry run: an unconfirmed destructive dry run
        # reaches the SAME refusal a real unconfirmed request would
        # (D-4(2)'s own "dry_run subject to the same gates" rule), so it
        # never returns a plan at all -- only a confirmed dry run reaches
        # the "would succeed" decision that carries one. Declare-first on
        # WHICH destructive primitive proves it: `drop_entity` where this
        # plug provides it, a destructive `delete` dry run otherwise
        # (every registered plug supports `delete`; D-4(2)'s own ordering
        # fact does not depend on which destructive primitive carries it).
        # `drop_entity` absence is read from `capabilities.schema_
        # operations` first (`_drop_entity_declared_unsupported`); a
        # `SurfaceAbsent` from the real call despite a declaration that did
        # not name it is tolerated the SAME way, never a hard failure of
        # this leg -- the declared-vs-actual mismatch it would represent is
        # test_c06_destructive_confirmation.py's own V6/M-6 territory, not
        # this leg's concern. Exactly one of the two forms is expected to
        # actually run per plug; `observed_ordering_form` records which.
        observed_ordering_form: str | None = None
        if not _drop_entity_declared_unsupported(adapter):
            doomed_entity = fresh_identifier("c22doomed")
            try:
                iso.create_entity(developer, doomed_entity, {"label": "text"})
                stale_plan = iso.schema_operation_with_result(
                    developer, doomed_entity, "drop_entity", destructive=True, confirmation=VALID_CONFIRMATION,
                    dry_run=True,
                ).get("plan")
                assert stale_plan, f"{adapter.name}: a CONFIRMED dry-run drop_entity carries no plan"
                iso.schema_operation_with_result(
                    developer, entity, "add_field", field=fresh_identifier("c22f2"), field_type="string",
                )
                with pytest.raises(ConformanceDenial) as ei_order:
                    iso.schema_operation_with_result(
                        developer, doomed_entity, "drop_entity", destructive=True, plan=stale_plan,
                    )
                assert ei_order.value.code == "DESTRUCTIVE_CONFIRMATION_REQUIRED", (
                    f"{adapter.name}: an UNCONFIRMED destructive drop_entity carrying a now-stale plan -> "
                    f"{ei_order.value.code!r}, expected DESTRUCTIVE_CONFIRMATION_REQUIRED (confirmation precedes "
                    "precondition evaluation, design D-4(2)/destructive_confirmation.evaluation_order)"
                )
                assert doomed_entity in iso.entities(developer), (
                    f"{adapter.name}: the unconfirmed drop_entity executed"
                )
                observed_ordering_form = "drop_entity"
            except SurfaceAbsent:
                observed_ordering_form = None

        if observed_ordering_form is None:
            # drop_entity unavailable (declared unsupported, or a
            # SurfaceAbsent this leg tolerates the same way): the identical
            # ordering fact via a CONFIRMED destructive `delete` dry run
            # instead -- same shape, confirmed-dry-run-then-stale-then-
            # unconfirmed-replay -- against a real row rather than a
            # doomed entity.
            order_marker = fresh_identifier("c22order")
            iso.attempt_mutation(
                runtime, entity, "insert", values={"label": order_marker}, where_field=None, where_value=None,
            )
            stale_delete_plan = iso.attempt_mutation_with_result(
                runtime, entity, "delete", values=None, where_field="label", where_value=order_marker,
                destructive=True, confirmation=VALID_CONFIRMATION, dry_run=True,
            ).get("plan")
            assert stale_delete_plan, f"{adapter.name}: a CONFIRMED dry-run destructive delete carries no plan"
            iso.schema_operation_with_result(
                developer, entity, "add_field", field=fresh_identifier("c22f2b"), field_type="string",
            )
            with pytest.raises(ConformanceDenial) as ei_order_delete:
                iso.attempt_mutation_with_result(
                    runtime, entity, "delete", values=None, where_field="label", where_value=order_marker,
                    destructive=True, plan=stale_delete_plan,
                )
            assert ei_order_delete.value.code == "DESTRUCTIVE_CONFIRMATION_REQUIRED", (
                f"{adapter.name}: an UNCONFIRMED destructive delete carrying a now-stale plan -> "
                f"{ei_order_delete.value.code!r}, expected DESTRUCTIVE_CONFIRMATION_REQUIRED (confirmation "
                "precedes precondition evaluation, design D-4(2)/destructive_confirmation.evaluation_order)"
            )
            assert iso.select_eq(runtime, entity, ["label"], "label", order_marker) != [], (
                f"{adapter.name}: the unconfirmed destructive delete executed -- row {order_marker!r} is gone"
            )
            observed_ordering_form = "delete"

        assert observed_ordering_form in ("drop_entity", "delete"), (
            f"{adapter.name}: C-22 (11) ordering leg recorded no observed form -- this test's own per-plug "
            "non-vacuity requirement"
        )

        observed_branch = "dry_run_enabled"

    expected_branch = _expected_branch_for_status(status)
    assert observed_branch == expected_branch, (
        f"{adapter.name}: dry_run status {status!r} recorded branch {observed_branch!r}, expected "
        f"{expected_branch!r} -- this test's own per-plug non-vacuity requirement"
    )
