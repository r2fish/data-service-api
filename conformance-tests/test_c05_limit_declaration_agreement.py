"""C-05 -- resource-limit declaration agreement (SI-08).

design: docs/design/PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md
D-6 (a), registered in `conformance-tests/CONDITIONS.md`. Every test here
carries `@pytest.mark.condition("C-05")` via the module-level `pytestmark`.

Structure (D-6.1): same "declare-first, non-enabled side does not skip"
shape `test_c17_declaration_agreement.py`'s own module docstring already
establishes for this repository.

  - **V1** (`test_c05_v1_*`): self-consistency of a single capability
    document -- (a) `limits`/`limit_enforcement` keys are drawn from
    `limits.classes`; (b) every `limits`-valued class has a
    `limit_enforcement` entry; (c) an `enforced`/`reference_wall_clock`
    entry has a finite (`>= 1`) `limits` value; (d) an
    `unavailable`/`deployment_required` entry is NOT required to have one
    (this is the (d) rule this file protects, not enforces); (e) the fixed
    9 (+ capability-conditioned 3) application-plane classes each carry an
    explicit `limit_enforcement` entry -- a COMMON-SUITE-ADDED requirement,
    not a contract obligation (design D-6.1's own "位置づけ" paragraph).
    Runs against BOTH planes: application (`capability_document()`,
    required set = the fixed 9 + capability-conditioned 3) and control
    (`control_capabilities()`, required set = C-14's own 3 driven classes
    (`applications`/`credentials_per_application`/`control_requests_per_
    minute`) + `audit_query`-conditioned `audit_requests_per_minute` --
    差し戻し指示 2: this control-plane required set is asserted HERE, by
    this same (e) mechanism, not merely left to C-14's own position-drive
    to imply).
  - **V2** (`test_c05_v2_*`): the peer's declared bound and the peer's real
    refusal position agree, driven against `adapter.isolated_application_
    surface()` (port v1.11) -- never the shared, session-scoped adapter.
    Driven set = (this plug's own `enforced` declaration) ∩ (a class this
    file can construct a real drive for) -- derived at test time, never a
    fixed list (design D-6.1 V2,禁止事項 2). Per-plug non-vacuity: each
    adapter's own test asserts at least one class was actually driven.
  - **V3** (`test_c05_v3_*`): a STATIC parametrize over the fixed 9 ×
    4 plugs (36 cases) -- "this class is not `unavailable`" -- with
    `xfail(strict=True)` statically pre-attached to the 9 cases currently
    known to be `unavailable` (design's own L7-1 next-phase candidate).
    The base list is NOT derived from any adapter's live declaration
    (design D-6.1 V3/禁止事項 3): deriving it would make the xfail-driven
    "撤去の合図" (an `unavailable` class flipping to something else XPASSes
    the case, and `strict=True` turns that XPASS red) impossible to detect,
    since the case would simply stop being collected instead.

Every test function in this module makes a genuine assertion against every
plug it applies to, never a bare pass-through (design principle 4 / this
repository's "空振り禁止" discipline).
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from adapter import (
    BatchOperation,
    ConformanceAdapter,
    ConformanceDenial,
    ScopedBatchOperation,
    fresh_identifier,
    load_contract,
)
from conftest import registered_adapters

pytestmark = pytest.mark.condition("C-05")

# design D-6.1 (condition 13(a), mirrors test_c14_authority_boundary.py's
# own identical `_MAX_EXERCISABLE_LIMIT`): a conformance build's SI-08
# resource bounds must be small enough to actually drive over in one test
# run -- a bound only theoretically finite is unexercisable in practice.
_MAX_EXERCISABLE_LIMIT = 200

# design D-6.1 "必須エントリ集合 = 固定 9 + capability 条件付き 3"
# (裁定 S-2). Applies to the APPLICATION plane only (V1 (e)).
_FIXED_NINE = (
    "request_bytes", "batch_items", "result_items", "query_complexity",
    "execution_ms", "concurrency", "requests_per_minute", "schema_objects",
    "operation_depth",
)

_CAPABILITY_CONDITIONED = {
    "batch_entities": "cross_entity_mutation",
    "idempotency_entries": "idempotency",
    "idempotency_retention_ms": "idempotency",
}

# design D-6.1 (e)'s control-plane substitute: the 3 classes C-14 vector 5
# already position-drives, plus `audit_requests_per_minute` (conditioned
# on `audit_query`, not itself driven by C-05). 差し戻し指示 2: this
# constant is asserted by `test_c05_v1_control_plane_self_consistency`
# below via `_assert_v1_self_consistency`'s `required_fixed`/
# `audit_conditioned` parameters -- it was previously defined but never
# passed to any assertion, which is not a permitted "declare but skip"
# outcome for a required-entry set (監督裁定: 不実施の選択肢は採らない).
_CONTROL_REQUIRED_FIXED = ("applications", "credentials_per_application", "control_requests_per_minute")

# WP-4c (2026-09-08): updated from the original 4-plug tuple to the
# current 6-plug registry (`r2db-api-socket`/`MitateDB-api-socket` added
# by WP-4a/WP-4b). Still a STATIC pin, not derived from `registered_
# adapters()` -- design D-6.1 V3/禁止事項 3 requires V3's own parametrize
# base to be a literal tuple asserted (below, in `test_c05_all_plug_
# names_match_the_registry`) against the live registry, precisely so a
# plug rename/removal/addition that this tuple is NOT updated to match
# is caught as a mismatch rather than silently narrowing (or padding)
# V3's own coverage to whatever the registry happens to contain.
_ALL_PLUG_NAMES = (
    "r2db-api", "r2db-api-http", "r2db-api-socket",
    "MitateDB-api", "MitateDB-api-http", "MitateDB-api-socket",
)


# ---------------------------------------------------------------------------
# shared helpers
# ---------------------------------------------------------------------------


def _limits_classes() -> frozenset[str]:
    return frozenset(load_contract()["limits"]["classes"])


def _assert_v1_self_consistency(
    document: dict,
    *,
    adapter_name: str,
    plane: str,
    required_fixed: tuple[str, ...] = (),
    capability_conditioned: dict[str, str] | None = None,
    audit_conditioned: bool = False,
) -> None:
    classes = _limits_classes()
    limits = document.get("limits", {}) or {}
    enforcement = document.get("limit_enforcement", {}) or {}

    # (a) contract capability_status.rules #4 (1.2.0 obligation).
    unknown_enforcement = set(enforcement) - classes
    assert not unknown_enforcement, (
        f"{adapter_name} ({plane}): limit_enforcement has keys outside limits.classes: {unknown_enforcement!r}"
    )
    unknown_limits = set(limits) - classes
    assert not unknown_limits, (
        f"{adapter_name} ({plane}): limits has keys outside limits.classes: {unknown_limits!r}"
    )

    # (b) contract rule "Every discovered finite limit names its
    # enforcement layer".
    for cls, value in limits.items():
        assert cls in enforcement, (
            f"{adapter_name} ({plane}): limits[{cls!r}]={value!r} has no corresponding limit_enforcement entry (V1 (b))"
        )

    # (c) `enforced`/`reference_wall_clock` -> finite (>= 1) limits value.
    # `deployment_required` is deliberately excluded (design D-6.1's own
    # B-7 finding: the contract does not require a value there, and
    # requiring one would make the HONEST declaration the one that fails).
    for cls, status in enforcement.items():
        if status in ("enforced", "reference_wall_clock"):
            value = limits.get(cls)
            assert isinstance(value, int) and not isinstance(value, bool) and value >= 1, (
                f"{adapter_name} ({plane}): limit_enforcement[{cls!r}]={status!r} but limits[{cls!r}]={value!r} "
                "is not a finite (>= 1) integer (V1 (c))"
            )

    # (d) is a NON-constraint (design's own裁定 S-1): `unavailable`/
    # `deployment_required` MAY carry a `limits` value or not -- there is
    # nothing to assert here beyond NOT accidentally re-imposing the
    # withdrawn rule. The non-mutation control below (test_c05_v1_d_
    # unavailable_class_may_still_publish_a_limits_value) is what protects
    # this.

    # (e) required-entry sets: application plane's fixed 9 (+ capability-
    # conditioned 3), or control plane's own 3 fixed + `audit_query`-
    # conditioned `audit_requests_per_minute` (差し戻し指示 2: this control-
    # plane set was previously declared as a module constant
    # (`_CONTROL_REQUIRED_FIXED`) but never actually wired into any
    # assertion -- "宣言存在" without enforcement is not an option here;
    # both planes' required sets go through the SAME two code paths below).
    for cls in required_fixed:
        assert cls in enforcement, (
            f"{adapter_name} ({plane}): required class {cls!r} has no explicit limit_enforcement entry (V1 (e))"
        )
    if capability_conditioned:
        capabilities = document.get("capabilities", {}) or {}
        for cls, capability in capability_conditioned.items():
            capability_status = capabilities.get(capability, {}).get("status", "unavailable")
            if capability_status != "unavailable":
                assert cls in enforcement, (
                    f"{adapter_name} ({plane}): capability {capability!r} is {capability_status!r} (not "
                    f"unavailable) but conditioned class {cls!r} has no explicit limit_enforcement entry (V1 (e))"
                )
    if audit_conditioned:
        capabilities = document.get("capabilities", {}) or {}
        audit_status = capabilities.get("audit_query", {}).get("status", "unavailable")
        if audit_status != "unavailable":
            assert "audit_requests_per_minute" in enforcement, (
                f"{adapter_name} ({plane}): capability 'audit_query' is {audit_status!r} (not unavailable) but "
                "conditioned class 'audit_requests_per_minute' has no explicit limit_enforcement entry (V1 (e))"
            )


def _control_plane_status(adapter: ConformanceAdapter) -> str:
    return adapter.capability_document().get("capabilities", {}).get("control_plane", {}).get("status", "unavailable")


def _assert_limit_exceeded(denial: ConformanceDenial, cls: str, *, adapter_name: str) -> None:
    assert denial.code == "LIMIT_EXCEEDED", f"{adapter_name}: expected LIMIT_EXCEEDED, got {denial.code!r}"
    # design D-6.1 V2 / contract errors.details_vocabulary.LIMIT_EXCEEDED.
    # limit_class ("string, required", 1.2.0 unconditional obligation,
    # versioning.version_binding) -- HARD here, required for both the
    # two-sided and one-sided forms (D-6.4).
    assert denial.details.get("limit_class") == cls, (
        f"{adapter_name}: LIMIT_EXCEEDED details.limit_class={denial.details.get('limit_class')!r}, expected {cls!r}"
    )


def _provision_pair(iso: ConformanceAdapter, *, app_id: str | None = None) -> tuple[object, object, str]:
    """Provisions one throwaway application on the ISOLATED instance and
    returns (developer_session, runtime_session, application_id). `app_id`
    is normally left to be generated fresh here; WP-4 rework's (e) test
    (below) passes one in explicitly so it can compute the PostgreSQL
    `datname` this specific application will provision BEFORE calling this
    function, and reuse that same identifier for its own before/during/
    after resource counts (完了条件 15 / F1 差し戻し 2 巡目)."""
    if app_id is None:
        app_id = fresh_identifier("c05app")
    iso.provision_application(app_id)
    dev_handle = iso.issue_credential(app_id, "developer")
    rt_handle = iso.issue_credential(app_id, "runtime")
    return iso.authenticate(dev_handle), iso.authenticate(rt_handle), app_id


# ---------------------------------------------------------------------------
# V2 per-class drivers. Each returns True iff it actually drove `cls` on
# this plug (the declaration says `enforced` AND this file can construct a
# real request for it) -- False means "correctly not applicable here",
# never an error. Each opens its OWN isolated_application_surface() (port
# v1.11 docstring's own documented choice, design condition 13(b)): no
# cross-class rate-window headroom arithmetic is needed because no two
# classes' drives ever share one isolated instance.
# ---------------------------------------------------------------------------


def _drive_batch_items(adapter: ConformanceAdapter) -> bool:
    with adapter.isolated_application_surface() as iso:
        doc = iso.capability_document()
        if doc.get("limit_enforcement", {}).get("batch_items") != "enforced":
            return False
        bound = doc["limits"]["batch_items"]
        assert bound <= _MAX_EXERCISABLE_LIMIT, f"{adapter.name}: batch_items={bound} exceeds {_MAX_EXERCISABLE_LIMIT}"
        dev, rt, _ = _provision_pair(iso)
        entity = fresh_identifier("c05bi")
        iso.create_entity(dev, entity, {"label": "text"})

        ok_ops = [BatchOperation(operation="insert", values={"label": "x"}) for _ in range(bound)]
        affected, _addr = iso.attempt_batch_with_addresses(rt, entity, ok_ops)
        assert affected == bound, f"{adapter.name}: batch of exactly {bound} items did not fully succeed"

        bad_ops = [BatchOperation(operation="insert", values={"label": "x"}) for _ in range(bound + 1)]
        with pytest.raises(ConformanceDenial) as excinfo:
            iso.attempt_batch_with_addresses(rt, entity, bad_ops)
        _assert_limit_exceeded(excinfo.value, "batch_items", adapter_name=adapter.name)
        return True


def _schema_objects_unit_cost(adapter: ConformanceAdapter) -> int:
    # Measured empirically (WP-4), not assumed (D-6.2's own instruction):
    # `r2db-api` (`structured.py::apply_schema`) counts a `create_entity`
    # as `1 + len(fields)` objects -- but this file's own `create_entity`
    # port call adds an AUTOMATIC `id: integer` address field on top of
    # whatever fields it is given (confirmed by inspecting `cell.schema`
    # after a real call: `{"id": "integer", "label": "string"}` for a
    # single declared field), so a one-declared-field entity actually
    # costs 1 (entity) + 2 (id + label) = 3, not 2. `MitateDB-api`
    # (`backend_sqlite.py::schema_count`) counts one object per real
    # SQLite table, regardless of field count -- confirmed empirically to
    # be exactly 1 per entity. Both plugs of each peer share their own
    # peer's real backend/counting code, so this is a per-PEER fact
    # (`adapter.name` here names which real counting rule applies), not
    # adapter-branching for its own sake.
    return 3 if adapter.name.startswith("r2db-api") else 1


def _drive_schema_objects(adapter: ConformanceAdapter) -> bool:
    with adapter.isolated_application_surface() as iso:
        doc = iso.capability_document()
        if doc.get("limit_enforcement", {}).get("schema_objects") != "enforced":
            return False
        bound = doc["limits"]["schema_objects"]
        assert bound <= _MAX_EXERCISABLE_LIMIT, f"{adapter.name}: schema_objects={bound} exceeds {_MAX_EXERCISABLE_LIMIT}"
        unit = _schema_objects_unit_cost(adapter)
        expected_successes = bound // unit
        dev, _rt, _ = _provision_pair(iso)

        successes = 0
        denial: ConformanceDenial | None = None
        for _ in range(expected_successes + 2):
            entity = fresh_identifier("c05so")
            try:
                iso.create_entity(dev, entity, {"label": "text"})
                successes += 1
            except ConformanceDenial as exc:
                denial = exc
                break
        assert denial is not None, f"{adapter.name}: schema_objects bound {bound!r} was never hit"
        _assert_limit_exceeded(denial, "schema_objects", adapter_name=adapter.name)
        assert successes == expected_successes, (
            f"{adapter.name}: expected exactly {expected_successes} successful create_entity calls "
            f"(bound={bound}, unit_cost={unit}) before LIMIT_EXCEEDED, got {successes}"
        )
        return True


def _drive_operation_depth(adapter: ConformanceAdapter) -> bool:
    """Phase 8 WP-1b (R-A 監督裁定 2026-09-06): recipe replaced. The
    pre-WP-1b recipe (flat insert = declared bound 4, the same insert
    plus a `where` filter = bound+1) forced the isolated profile's
    `operation_depth` down to 4 -- but at 4, EVERY `where`-carrying
    mutation (`update`/`delete`, MitateDB's own only destructive
    operation included) sits at REAL depth 5 on the wire and was
    therefore spuriously `LIMIT_EXCEEDED`(`operation_depth`) on the
    isolated surface, not merely the deliberately-oversized N+1 probe
    (measured, WP-1a rework: `MitateDB-api-http`'s own real `delete()`
    probe in `test_c04_unsupported_and_safe_errors.py` was failing for
    exactly this reason). The isolated profile's `operation_depth` is
    raised to 5 (every adapter's own isolated-profile comment) and this
    driver's own recipe moves onto a genuinely valid, `where`-carrying
    mutation instead of a structurally-invalid one.

    New recipe: N is an ordinary `update` with a real, scalar `where`
    filter -- measured (below) to sit EXACTLY at real depth 5 on every
    plug (`{"entity":..., "operations": [{"operation": "update",
    "values": {...}, "where": [{"field":..., "operator": "eq", "value":
    ...}]}]}`: request(1)->operations list(2)->operation dict(3)->where
    list(4)->predicate dict(5) -- identical structure/depth on r2db (this
    is r2db's own SOLE mutation dispatch shape, both plugs) and on
    MitateDB (the real HTTP wire dispatch, `http.py::post_mutate`'s own
    `_mutation_item`/`session.transact()`, and -- as of this WP --
    the in-process plug's own `attempt_mutation`, routed through the
    SAME `transact()` entry point for `operation="update"` with a filter,
    `conformance_adapter_mitatedb.py::_attempt_mutation_outcome`'s own
    comment has the full trace). N+1 is the SAME update with its
    predicate's `value` itself replaced by a one-element container (a
    list) -- adds exactly one nesting level (the predicate dict's own
    `value` slot, checked at nesting level 6) -- deterministically
    `LIMIT_EXCEEDED`(`operation_depth`), before any content validation of
    that (semantically invalid for an `eq` predicate) container value
    ever runs, on every plug this driver is invoked against -- the depth
    check precedes content validation on both peers (r2db `service.py`'s
    own call order; MitateDB `cell.py::ApplicationCell._limit_gate`'s
    identical ordering, Phase 8 WP-1a D-1)."""
    with adapter.isolated_application_surface() as iso:
        doc = iso.capability_document()
        if doc.get("limit_enforcement", {}).get("operation_depth") != "enforced":
            return False
        # 差し戻し指示 5(c) (unchanged rationale, carried over WP-1b): read
        # the declared bound from the capability document (never trust it
        # only by comment) and assert BOTH the same exercisability
        # ceiling every other count-valued driver in this file asserts
        # AND the "update+where sits at exactly the declared bound"
        # premise the N/N+1 recipe below depends on.
        bound = doc["limits"]["operation_depth"]
        assert bound <= _MAX_EXERCISABLE_LIMIT, f"{adapter.name}: operation_depth={bound} exceeds {_MAX_EXERCISABLE_LIMIT}"
        assert bound == 5, (
            f"{adapter.name}: operation_depth isolated profile bound is {bound}, but this driver's update-"
            "with-where recipe is measured (this module's own docstring above) to sit at real depth 5 -- "
            "update BOTH the isolated profile's operation_depth and this assertion together if the "
            "recipe's measured depth ever changes"
        )
        dev, rt, _ = _provision_pair(iso)
        entity = fresh_identifier("c05od")
        iso.create_entity(dev, entity, {"label": "text"})
        iso.insert(rt, entity, {"label": "seed"})

        # N: an ordinary, genuinely valid `update` with a real scalar
        # `where` filter -- by construction of the isolated profile's own
        # `operation_depth` bound, this sits EXACTLY at the declared
        # position (this driver's own docstring / each plug's own module
        # comment / the bound-vs-recipe assertion above). Content is as
        # valid as it looks: the filter matches the row just inserted.
        iso.attempt_mutation(rt, entity, "update", values={"label": "n"}, where_field="label", where_value="seed")

        # N+1: the SAME update, with the where-clause's own `value`
        # replaced by a one-element list -- adds exactly one nesting
        # level under the predicate dict. See this function's own
        # docstring for why the observed denial is deterministically
        # LIMIT_EXCEEDED, never VALIDATION_FAILED, on every plug.
        with pytest.raises(ConformanceDenial) as excinfo:
            iso.attempt_mutation(rt, entity, "update", values={"label": "n"}, where_field="label", where_value=["seed"])
        _assert_limit_exceeded(excinfo.value, "operation_depth", adapter_name=adapter.name)
        return True


def _drive_requests_per_minute(adapter: ConformanceAdapter) -> bool:
    with adapter.isolated_application_surface() as iso:
        doc = iso.capability_document()
        if doc.get("limit_enforcement", {}).get("requests_per_minute") != "enforced":
            return False
        bound = doc["limits"]["requests_per_minute"]
        assert bound <= _MAX_EXERCISABLE_LIMIT, f"{adapter.name}: requests_per_minute={bound} exceeds {_MAX_EXERCISABLE_LIMIT}"
        dev, rt, _ = _provision_pair(iso)
        entity = fresh_identifier("c05rpm")
        # `create_entity` runs under the DEVELOPER credential's own,
        # separate rate window (r2db `service.py::_acquire_rate` keys by
        # `credential_id`) -- it does not consume any of the RUNTIME
        # window this drive measures, so no headroom subtraction is
        # needed for it (condition 13(b)'s own "検算した headroom 前提").
        iso.create_entity(dev, entity, {"label": "text"})

        # Measured (WP-4, r2db-api-http): `r2db-api-http`'s own
        # `authenticate()` (above, via `_provision_pair`) is a REAL
        # `GET /v1/capabilities` round trip under the SAME runtime
        # credential -- it consumes exactly 1 unit of the SAME rate
        # window this drive measures (unlike the in-process plugs' own
        # `authenticate()`, a bare local lookup that never touches
        # `_slot()`/`_acquire_rate` at all), because r2db's own
        # capabilities-equivalent call passes through the SAME `_slot`
        # every other application-plane operation does.
        #
        # Re-measured for MitateDB-api-http (Phase 8 WP-1a rework 1,
        # 裁定 3, 監督裁定 2026-09-06, design D-2 "検査の形" `already_
        # consumed`再測定, work order §2 WP-1a 完了条件 13): the WP-1a
        # report's original measurement here (`ApplicationRuntime.
        # capabilities()` deliberately NOT wrapped by `_limit_gate`, so
        # `already_consumed=0` on this plug) was true of THAT commit but
        # is no longer true after 裁定 3 -- `capabilities()`/`catalog()`/
        # `schema_revision()` are now wrapped by `_limit_gate` (rate/
        # concurrency only) on BOTH MitateDB surfaces, matching r2db's own
        # `capabilities()` (`service.py:877`, inside `_slot`) -- so
        # `HttpService.authenticate`'s own `GET /v1/capabilities` round
        # trip now consumes exactly 1 unit of the SAME `requests_per_
        # minute` window this drive measures, under the SAME runtime
        # credential, on `MitateDB-api-http` too. Confirmed empirically
        # (WP-1a rework report): at `bound=50`, `MitateDB-api-http`
        # observes exactly `49` successful inserts before the denial, not
        # `50`. `already_consumed` is therefore `1` for EVERY HTTP plug
        # (both peers alike) and `0` for every in-process plug (both
        # peers' own in-process `authenticate()` stays a bare local
        # lookup that never touches the gate at all) -- a genuinely
        # TRANSPORT-specific fact now, not a peer-specific one; the
        # earlier peer-name pin (`adapter.name == "r2db-api
        # (http+postgres)"`) is reverted to the general, transport-keyed
        # check it replaced.
        #
        # WP-4c rework (監督裁定 wp4b-rulings.md 項 1, `OPERATING_
        # CONDITIONS.md` §1.7 の 52 -- 代理指標を使わない): `"http" in
        # adapter.name` was itself still a NAME-based proxy for the real
        # property this correction depends on -- whether `authenticate()`
        # makes a REAL wire round trip through the SAME rate-limited
        # `_slot`/`_acquire_rate` path, which is a fact about the
        # adapter's TRANSPORT, not its name. `r2db-api-socket`/`MitateDB-
        # api-socket` (real TCP through nginx + uvicorn) make exactly the
        # same real `GET /v1/capabilities` round trip an HTTP plug does,
        # but their registry names contain no `"http"` substring at all
        # (`"r2db-api-socket"`, `"MitateDB-api-socket"`) -- so the old
        # name-based proxy was ALREADY WRONG for the socket plugs
        # (`already_consumed` silently stayed `0`, undercounting by
        # exactly the 1 unit `authenticate()` really consumes, producing
        # `expected 50, got 49` on socket plugs). The property that
        # actually decides this is `adapter.transport_kind`: `"asgi"`
        # (existing HTTP plugs) and `"socket"` (new real-TCP plugs) both
        # go through real wire framing for `authenticate()`'s `GET /v1/
        # capabilities`; `"in_process"` does not.
        already_consumed = 1 if adapter.transport_kind in ("asgi", "socket") else 0
        expected_successes = bound - already_consumed

        successes = 0
        denial: ConformanceDenial | None = None
        for _ in range(bound + 5):
            try:
                iso.insert(rt, entity, {"label": "x"})
                successes += 1
            except ConformanceDenial as exc:
                denial = exc
                break
        assert denial is not None, f"{adapter.name}: requests_per_minute bound {bound!r} was never hit"
        _assert_limit_exceeded(denial, "requests_per_minute", adapter_name=adapter.name)
        assert successes == expected_successes, (
            f"{adapter.name}: expected exactly {expected_successes} successful inserts before LIMIT_EXCEEDED "
            f"(bound={bound}, already_consumed={already_consumed}), got {successes}"
        )
        return True


def _drive_batch_entities(adapter: ConformanceAdapter) -> bool:
    with adapter.isolated_application_surface() as iso:
        doc = iso.capability_document()
        if doc.get("limit_enforcement", {}).get("batch_entities") != "enforced":
            return False
        if doc.get("capabilities", {}).get("cross_entity_mutation", {}).get("status", "unavailable") == "unavailable":
            return False
        bound = doc["limits"]["batch_entities"]
        assert bound <= _MAX_EXERCISABLE_LIMIT, f"{adapter.name}: batch_entities={bound} exceeds {_MAX_EXERCISABLE_LIMIT}"
        dev, rt, _ = _provision_pair(iso)
        entities = [fresh_identifier("c05be") for _ in range(bound + 1)]
        for entity in entities:
            iso.create_entity(dev, entity, {"label": "text"})

        ok_ops = [ScopedBatchOperation(operation="insert", entity=entities[i], values={"label": "x"}) for i in range(bound)]
        affected = iso.attempt_cross_entity_batch(rt, ok_ops)
        assert affected == bound, f"{adapter.name}: cross-entity batch of exactly {bound} entities did not fully succeed"

        bad_ops = [ScopedBatchOperation(operation="insert", entity=entities[i], values={"label": "x"}) for i in range(bound + 1)]
        with pytest.raises(ConformanceDenial) as excinfo:
            iso.attempt_cross_entity_batch(rt, bad_ops)
        _assert_limit_exceeded(excinfo.value, "batch_entities", adapter_name=adapter.name)
        return True


def _drive_request_bytes(adapter: ConformanceAdapter) -> bool:
    with adapter.isolated_application_surface() as iso:
        doc = iso.capability_document()
        if doc.get("limit_enforcement", {}).get("request_bytes") != "enforced":
            return False
        bound = doc["limits"]["request_bytes"]
        # `_MAX_EXERCISABLE_LIMIT` is not applied here (unlike every
        # COUNT-valued class below): it is a count-class ceiling ("a
        # theoretically-finite bound too large to actually drive over in
        # one test run" -- C-14:476's own rationale), and a byte-valued
        # class needs a materially larger absolute number to leave
        # ordinary setup traffic (this profile's own `create_entity`/
        # `insert` calls) room to fit under it at all -- this file's own
        # small profile uses 4096, not <= 200, for exactly that reason.
        # One-sidedness (a clearly-oversized request is refused) does not
        # depend on the bound's own absolute size the way position-exact
        # two-sided drives do.
        dev, rt, _ = _provision_pair(iso)
        entity = fresh_identifier("c05rby")
        iso.create_entity(dev, entity, {"label": "text"})

        # one-sided (D-6.2): minimal safe request succeeds...
        iso.insert(rt, entity, {"label": "x"})
        # ...a request clearly, unambiguously past the bound is refused
        # (both peers' own byte-estimate formulas agree a value this much
        # larger than the bound overflows it -- design D-6.2's own
        # "明らかな超過").
        huge = "x" * (bound * 20 + 1000)
        with pytest.raises(ConformanceDenial) as excinfo:
            iso.insert(rt, entity, {"label": huge})
        _assert_limit_exceeded(excinfo.value, "request_bytes", adapter_name=adapter.name)
        return True


def _drive_result_items(adapter: ConformanceAdapter) -> bool:
    """Phase 8 WP-1b (R-C, port v1.12 L7-21): two-sided on all 4 plugs, as
    of port v1.12's own `limit` optional field on `select_eq`. Previously
    one-sided and peer-name-excluded to `r2db-api` alone (this port had
    no way at all to carry a client-requested page size to MitateDB's own
    REQUESTED-limit-value check, `cell.py::ApplicationCell.read`'s own
    `limit > self.config.max_result_rows` guard) -- `select_eq`'s new
    `limit` keyword removes that port-shape gap entirely, and the two
    peers' own real checks (measured, design D-2/§6.2) agree at the
    SAME N/N+1 position for this recipe: r2db checks `min(len(rows),
    page_size)` against the bound (`postgres.py:1069`/`structured.py:
    1198`) -- with `bound+1` ACTUAL rows present, `min(bound+1,
    page_size)` equals `page_size` for both `page_size=bound` (succeeds)
    and `page_size=bound+1` (denied); MitateDB checks the REQUESTED
    `limit` value directly, independent of how many rows actually match
    (`cell.py`'s own guard fires before the backend read runs at all) --
    so both peers deny the SAME `page_size=bound+1` request and permit
    the SAME `page_size=bound` one.

    Phase 8 WP-1 rework 3 (裁定 4(乙), 監督裁定 2026-09-07): the table gets
    exactly `bound + 1` matching rows inserted ONCE, and the two calls
    below differ ONLY in the `limit` they request -- the success call
    uses `limit=bound`, the denied call uses `limit=bound+1`, against the
    SAME unchanged row count both times. The earlier recipe instead held
    the row count fixed at `limit` for each call (insert `bound` rows,
    drive `limit=bound`; insert one more, drive `limit=bound+1`), which
    left `limit` un-load-bearing on r2db-api specifically: mutation-
    verified (dropping r2db in-process `select_eq`'s own `limit` kwarg
    entirely, defaulting `page_size` to `DataService.query`'s own
    pre-existing default of 100) that the OLD recipe stayed green even
    with `limit` completely ignored, because r2db's own check compares
    the ACTUAL returned row count against the bound, and the actual row
    count alone (bound vs. bound+1) already determined the N/N+1 outcome
    regardless of what page size was requested -- the default of 100 was
    generously larger than either row count either way. Fixing the row
    count at `bound + 1` for BOTH calls removes that degree of freedom:
    if `limit` were ignored now, the success call's own default page size
    (100) would return all `bound + 1` matching rows, which exceeds the
    bound and would wrongly deny the success call -- `limit` is therefore
    now load-bearing on r2db-api too, not only on MitateDB-api (where the
    REQUESTED `limit` value was always checked directly, independent of
    row count, and remains so under this recipe)."""
    with adapter.isolated_application_surface() as iso:
        doc = iso.capability_document()
        if doc.get("limit_enforcement", {}).get("result_items") != "enforced":
            return False
        bound = doc["limits"]["result_items"]
        assert bound <= _MAX_EXERCISABLE_LIMIT, f"{adapter.name}: result_items={bound} exceeds {_MAX_EXERCISABLE_LIMIT}"
        dev, rt, _ = _provision_pair(iso)
        entity = fresh_identifier("c05ri")
        iso.create_entity(dev, entity, {"probe": "text"})
        # `bound + 1` matching rows, inserted exactly once -- the row
        # count never changes between the two calls below (see this
        # function's own docstring, 裁定 4(乙)).
        for _ in range(bound + 1):
            iso.insert(rt, entity, {"probe": "same"})

        # N: `limit=bound` against `bound + 1` actual matching rows -- both
        # peers' own checks agree this succeeds ONLY because `limit`
        # itself caps what is considered (r2db: `page_size` bounds the
        # actual query result to `bound` rows before the length check
        # runs; MitateDB: the requested value is checked directly against
        # the bound, before the backend read even runs).
        rows = iso.select_eq(rt, entity, ["probe"], "probe", "same", limit=bound)
        assert len(rows) == bound, f"{adapter.name}: expected exactly {bound} matching rows at page size {bound}, got {len(rows)}"

        # N+1: the SAME `bound + 1` actual matching rows, `limit=bound+1`
        # -- both peers' own checks agree this is denied (see this
        # function's own docstring for why the two peers' real check
        # shapes agree at this exact position).
        with pytest.raises(ConformanceDenial) as excinfo:
            iso.select_eq(rt, entity, ["probe"], "probe", "same", limit=bound + 1)
        _assert_limit_exceeded(excinfo.value, "result_items", adapter_name=adapter.name)
        return True


def _drive_query_complexity(adapter: ConformanceAdapter) -> bool:
    """Phase 8 WP-1b (R-C, port v1.12 L7-21): peer-name exclusion removed
    (this driver now runs, and observes, on every plug whose declaration
    is `enforced`) -- but the recipe STAYS ONE-SIDED, a CONCLUSION, not an
    artifact of the exclusion that used to sit here (design D-2's own
    "算術的理由": r2db's metric is `len(where) + len(select) +
    order_by_count`, MitateDB's is `len(filters)` alone -- a single
    identical request cannot occupy the SAME N/N+1 position on both
    peers' own arithmetic at once). Driven via port v1.12's own
    `attempt_filter(..., extra_predicates=...)` (L7-21) instead of the
    pre-v1.12 recipe's `select`-list-length trick (which only ever
    inflated r2db's own metric; MitateDB's metric ignores `select`
    length entirely) -- predicate COUNT inflates both peers' own metric
    (`len(where)` directly for r2db, `len(filters)` directly for
    MitateDB), so the SAME request construction now drives both.

    Both sides are constructed RELATIVE TO `bound` (not a small fixed
    constant) -- `bound - 1` total predicates for the safe side, `bound
    + 1` for the refused side -- deliberately, not merely for tightness:
    a fixed, bound-independent safe request (e.g. always exactly 1
    predicate) would never notice a peer that declares a `query_
    complexity` bound larger than what it actually enforces (a real,
    observed WP-1b mutation: inflating a declared bound by 1 while the
    real check stays at the OLD value). Scaling with `bound` keeps this
    one-sided check honest about the declared VALUE itself, not merely
    about "some construction gets refused eventually"."""
    with adapter.isolated_application_surface() as iso:
        doc = iso.capability_document()
        if doc.get("limit_enforcement", {}).get("query_complexity") != "enforced":
            return False
        bound = doc["limits"]["query_complexity"]
        assert bound <= _MAX_EXERCISABLE_LIMIT, f"{adapter.name}: query_complexity={bound} exceeds {_MAX_EXERCISABLE_LIMIT}"
        assert bound >= 2, f"{adapter.name}: query_complexity={bound} is too small for this driver's bound-1/bound+1 recipe"
        dev, rt, _ = _provision_pair(iso)
        entity = fresh_identifier("c05qc")
        iso.create_entity(dev, entity, {"probe": "text"})
        iso.insert(rt, entity, {"probe": "x"})

        # one-sided (D-6.2, capability-判定化, not peer-name exclusion):
        # `bound - 1` total predicates (the primary + `bound - 2` extra)
        # is a safe request that stays under the bound on both peers'
        # own real metrics -- MitateDB: `len(filters) = bound - 1 <=
        # bound`; r2db: `len(where) + len(select) + order_by = (bound -
        # 1) + 1 + 0 = bound <= bound` (this profile's own single-field
        # `select` contributes exactly 1 -- the tightest margin r2db's
        # own metric allows without a peer-specific offset, D-2's own
        # "算術的理由").
        safe_extra = [("probe", "eq", "x") for _ in range(bound - 2)]
        iso.attempt_filter(rt, entity, ["probe"], "probe", "eq", "x", extra_predicates=safe_extra)

        # ...`bound + 1` total predicates (one past the safe side above)
        # is refused on every plug -- MitateDB's own `len(filters)`
        # metric exceeds `bound` by exactly 1; r2db's own `len(where)`
        # term ALONE already exceeds `bound` by 1 too (`order_by`/
        # `select` need not even be considered). This does not attempt
        # to make the two peers' N/N+1 POSITIONS coincide (this
        # function's own docstring: they cannot, by construction), only
        # that both refuse a request exactly 1 past their own declared
        # bound -- tight enough that an inflated declaration is caught
        # on the safe side above instead of masked by a generous margin.
        refused_extra = [("probe", "eq", "x") for _ in range(bound)]
        with pytest.raises(ConformanceDenial) as excinfo:
            iso.attempt_filter(rt, entity, ["probe"], "probe", "eq", "x", extra_predicates=refused_extra)
        _assert_limit_exceeded(excinfo.value, "query_complexity", adapter_name=adapter.name)
        return True


def _drive_concurrency(adapter: ConformanceAdapter) -> bool:
    """Phase 8 WP-1b (R-C, port v1.12 D-2): the ONE application-plane
    class no prior port revision could drive at all -- `port.hold_in_
    flight(session, n)` (new in v1.12) genuinely holds `n` real
    application-plane requests in-flight (see that method's own
    docstring, `adapter.py`, for the exact stop-point contract every
    plug realizes it against). Recipe: bound N held in flight -> N+1st
    ordinary request denied (`concurrency`) -> release -> the N held
    requests all complete successfully AND an ordinary request succeeds
    again."""
    with adapter.isolated_application_surface() as iso:
        doc = iso.capability_document()
        if doc.get("limit_enforcement", {}).get("concurrency") != "enforced":
            return False
        bound = doc["limits"]["concurrency"]
        assert bound <= _MAX_EXERCISABLE_LIMIT, f"{adapter.name}: concurrency={bound} exceeds {_MAX_EXERCISABLE_LIMIT}"
        assert bound >= 1, f"{adapter.name}: concurrency bound {bound!r} is not >= 1 -- cannot hold anything in flight"

        dev, rt, _ = _provision_pair(iso)
        entity = fresh_identifier("c05cc")
        iso.create_entity(dev, entity, {"label": "text"})

        # Rate headroom (design D-2 検査の形): r2db's own `_slot` checks
        # `requests_per_minute` BEFORE `concurrency` -- if this drive's
        # own `bound` held requests plus the N+1 probe below would
        # exhaust the SAME runtime credential's rate window first, the
        # observed denial would be `requests_per_minute`, not
        # `concurrency`, for a reason unrelated to what this driver
        # means to exercise. `create_entity` above runs under the
        # DEVELOPER credential's own separate window (unrelated to `rt`'s
        # own), so no headroom needs subtracting for it.
        if doc.get("limit_enforcement", {}).get("requests_per_minute") == "enforced":
            rpm_bound = doc["limits"]["requests_per_minute"]
            assert rpm_bound >= bound + 1, (
                f"{adapter.name}: requests_per_minute headroom ({rpm_bound}) is not >= concurrency bound+1 "
                f"({bound + 1}) -- the N+1 probe below could be denied by requests_per_minute instead of "
                "concurrency, making the observed denial ambiguous"
            )

        # Phase 8 WP-1 rework 3 (裁定 5, 監督裁定 2026-09-07): `held` is the
        # `as`-bound value `hold_in_flight` itself yields -- the REAL,
        # measured count of requests that reached the stall point
        # (`entered_count`, from each realization's own `threading.
        # Semaphore`-driven wait loop), never a copy of `bound` assigned
        # by this test. The previous `held = bound; assert held >= 1` was
        # a tautology restating `bound >= 1` (already asserted above) --
        # it would stay green even if `hold_in_flight` held ZERO requests
        # in practice, because `held` was never anything but `bound`
        # itself. Asserting the yielded value instead makes this a
        # genuine non-vacuity check on the primitive's own real behavior.
        with iso.hold_in_flight(rt, bound) as held:
            assert held >= 1, f"{adapter.name}: hold_in_flight held zero requests -- nothing was exercised"
            with pytest.raises(ConformanceDenial) as excinfo:
                iso.insert(rt, entity, {"label": "n_plus_1"})
            _assert_limit_exceeded(excinfo.value, "concurrency", adapter_name=adapter.name)
        # Released: `hold_in_flight.__exit__` has already joined every one
        # of the `bound` held requests and re-raised on any failure (its
        # own docstring's "抜ける時点で n 個の完了を待ち合わせる") -- an
        # ordinary request succeeding again, right after, is this
        # driver's own OBSERVABLE confirmation that release genuinely
        # freed the counter back down (a broken realization that does
        # not actually wait for the held requests to unwind would still
        # be occupying the counter here, denying this exact call).
        iso.insert(rt, entity, {"label": "after_release"})
        return True


_V2_DRIVERS = {
    "batch_items": _drive_batch_items,
    "schema_objects": _drive_schema_objects,
    "operation_depth": _drive_operation_depth,
    "requests_per_minute": _drive_requests_per_minute,
    "batch_entities": _drive_batch_entities,
    "request_bytes": _drive_request_bytes,
    "result_items": _drive_result_items,
    "query_complexity": _drive_query_complexity,
    "concurrency": _drive_concurrency,
}


# ---------------------------------------------------------------------------
# V1 -- self-consistency (application plane always; control plane if
# provided, else uniform absence).
# ---------------------------------------------------------------------------


def test_c05_fixed_nine_is_pinned() -> None:
    """差し戻し指示 9 (review mutation A, supervisor supplement 2026-09-06):
    a bare `len(_FIXED_NINE) == 9` check does not catch one class silently
    dropped (or swapped for a same-length substitute) from the tuple --
    fewer required V1 (e) classes get checked and fewer V3 cases get
    COLLECTED, so nothing goes red; `_FIXED_NINE`'s own exact content, not
    merely its length, must be pinned (same rationale as this
    repository's own `_ISOMORPHIC_TARGETS` pin,
    `tests/test_audit_query.py::test_isomorphic_target_table_is_pinned_
    to_its_current_67_rows`). Observed directly (review mutation A, before
    this test existed): removing `operation_depth` from `_FIXED_NINE` with
    nothing else changed left the ENTIRE C-05 module green (49 passed, 7
    xfailed -- 2 fewer than baseline's 51 passed/9 xfailed, but zero
    failures) -- this test exists precisely so that drop is caught here,
    not silently absorbed as "fewer cases collected"."""
    assert _FIXED_NINE == (
        "request_bytes", "batch_items", "result_items", "query_complexity",
        "execution_ms", "concurrency", "requests_per_minute", "schema_objects",
        "operation_depth",
    )
    assert len(_FIXED_NINE) == 9


def test_c05_all_plug_names_match_the_registry() -> None:
    """差し戻し指示 8: `_ALL_PLUG_NAMES` (the static base V3 parametrizes
    over, design D-6.1 V3/禁止事項 3 -- deliberately NOT derived from
    `registered_adapters()` for V3's own parametrize base, see this
    module's own docstring) must still independently agree with the LIVE
    registry's own key set, or V3 silently stops covering a plug that was
    renamed, removed, or added without this tuple being updated to match
    -- the same "pin the constant, don't just trust it" rationale as
    `test_c05_fixed_nine_is_pinned` above, applied to the OTHER static
    base this file hard-codes.

    WP-4c (2026-09-08): updated 4 -> 6 for the `r2db-api-socket`/
    `MitateDB-api-socket` plugs WP-4a/WP-4b registered (design §6.1's own
    6-plug registry table)."""
    assert frozenset(_ALL_PLUG_NAMES) == frozenset(registered_adapters().keys())
    assert len(_ALL_PLUG_NAMES) == 6


# Phase 8 WP-1 rework 3 (裁定 1, 監督裁定 2026-09-07): the sentence below is
# a literal, character-for-character copy of docs/design/PHASE8_EFFECTIVE_
# BOUNDS_AND_HYGIENE_V1.md §3 D-2 決定 1's own decision text (via the
# supervisor's own confirmed-text copy of it) -- pinned here so this test
# fails loud the moment `ConformanceAdapter.hold_in_flight`'s own port
# docstring (`adapter.py`) stops carrying it unparaphrased. 常設規律 4
# forbids paraphrasing a confirmed decision; this constant itself must
# therefore never be edited to "improve" wording -- only to follow a new,
# later, equally-verbatim supervisor ruling that supersedes this one.
_HOLD_IN_FLIGHT_RULING_SENTENCE_VERBATIM = (
    "n 個の application plane 要求を、service の in-flight 窓の内側で停止させ"
    "たまま保持する。保持中に n+1 個目を出すと `LIMIT_EXCEEDED`(`concurrency`)"
    " で拒否される。解放後、保持していた n 個はすべて正常に完了する"
)


def test_c05_hold_in_flight_port_docstring_carries_the_ruling_sentence_verbatim() -> None:
    """裁定 1 (監督裁定 2026-09-07): `phase8-ruling-verbatim.txt`'s own
    confirmed `hold_in_flight` decision sentence must appear in `Conformance
    Adapter.hold_in_flight`'s own port-level docstring UNPARAPHRASED --
    `CONFORMANCE_ADAPTER_V1.md` §22.1 already claims this ("carried into
    the port docstring unparaphrased, per 常設規律 4"); this test is what
    makes that claim checked, not merely asserted in prose. A plain
    substring check (not a word-diff/fuzzy match) is deliberate: anything
    short of an exact, contiguous character match IS a paraphrase for this
    purpose."""
    doc = ConformanceAdapter.hold_in_flight.__doc__ or ""
    occurrences = doc.count(_HOLD_IN_FLIGHT_RULING_SENTENCE_VERBATIM)
    assert occurrences >= 1, (
        "ConformanceAdapter.hold_in_flight's own docstring no longer carries "
        "the confirmed ruling sentence verbatim (observed count "
        f"{occurrences}) -- 常設規律 4 violation"
    )


def test_c05_v1_application_plane_self_consistency(adapter: ConformanceAdapter) -> None:
    document = adapter.capability_document()
    _assert_v1_self_consistency(
        document,
        adapter_name=adapter.name,
        plane="application",
        required_fixed=_FIXED_NINE,
        capability_conditioned=_CAPABILITY_CONDITIONED,
    )


def test_c05_v1_control_plane_self_consistency(adapter: ConformanceAdapter) -> None:
    if _control_plane_status(adapter) != "enabled":
        # Uniform absence, mirrors test_c14_authority_boundary.py's own
        # `_assert_uniform_absence_form` shape -- no currently-registered
        # adapter takes this branch (all 4 declare `control_plane:
        # enabled`), kept honest for a future peer that does not.
        with pytest.raises((ConformanceDenial,)):
            adapter.control_capabilities(adapter.issue_credential(fresh_identifier("c05absent"), "runtime"))
        return
    control_actor = adapter.control_credential()
    document = adapter.control_capabilities(control_actor)
    _assert_v1_self_consistency(
        document,
        adapter_name=adapter.name,
        plane="control",
        required_fixed=_CONTROL_REQUIRED_FIXED,
        audit_conditioned=True,
    )


def test_c05_v1_d_unavailable_class_may_still_publish_a_limits_value(adapter: ConformanceAdapter) -> None:
    """Non-mutation control (D-6.11 / 裁定 S-1): a `limits` value +
    `limit_enforcement: unavailable` on the SAME class is a positively
    honest declaration ("this surface publishes a bound, but has no
    enforcement layer for it"), not a contradiction -- the WITHDRAWN rule
    ("unavailable classes carry no limits value") must not have silently
    come back. Phase 8 WP-1 rework 3 (裁定 3, 監督裁定 2026-09-07,
    correcting this docstring's own stale claim): no adapter currently
    registered exhibits this combination any more. `MitateDB-api`
    (in-process)'s own former `request_bytes` case (`cell.py:1491`
    published a value, `:1502` declared `unavailable`, at the time this
    docstring was first written) was WP-1a's own one currently-registered
    instance; Phase 8 WP-1a rework 1 (裁定 1, 監督裁定 2026-09-06) then
    flipped this same peer's `operation_depth` to `enforced` too, so the
    combination this test protects is now observed on none of the 4 plugs
    (see this function's own body comment below for the measured trace).

    差し戻し指示 6 (review finding F6): the previous body's only assertion
    was a bare `assert True` inside an `if` -- a tautology that would stay
    green NO MATTER WHAT `_assert_v1_self_consistency` did internally,
    directly contradicting this test's own (now corrected) docstring claim
    that it protects against (d)'s withdrawn rule being re-imposed INSIDE
    that helper. Made genuinely effective the one way that still applies
    now that the combination is vacuous on every plug: actually CALL
    `_assert_v1_self_consistency` (with `required_fixed=()` / `capability_
    conditioned=None` / `audit_conditioned=False` -- this function's own
    defaults, deliberately keeping (e)'s required-entry sets out of scope,
    since this control is about (d) alone) against a document this
    adapter's own real declaration may carry such a combination on --
    if a future edit ever added a rejection of the unavailable+value
    combination inside that helper, THIS call raises and this test goes
    red, exactly what the docstring claims. The former second half (a
    non-vacuity assertion on `MitateDB-api` specifically) is REMOVED
    below, for the same reason this docstring's opening paragraph now
    states: the combination it checked for is no longer observed
    anywhere."""
    document = adapter.capability_document()
    _assert_v1_self_consistency(document, adapter_name=adapter.name, plane="application")

    # Phase 8 WP-1a (design D-1 "検査の形"/work order §2 WP-1a 完了条件 10):
    # the V1 statistical-control assert this block used to carry ("at
    # least one unavailable/deployment_required class still publishes a
    # `limits` value") is REMOVED in the same commit that flips `request_
    # bytes` to `enforced` on this peer -- that flip was the combination's
    # ONE currently-registered real-world instance AT THE TIME (this
    # test's own former docstring named it explicitly). Phase 8 WP-1a
    # rework 1 (裁定 1, 監督裁定 2026-09-06) then flipped this same peer's
    # `operation_depth` to `enforced` too (measured: `_check_operation_
    # depth` genuinely runs in-process via `_limit_gate`, wired at
    # `cell.py:531`, and traverses the real request dict every in-process
    # `insert`/`update`/`delete`/`transact` call site builds -- see that
    # class's own `limit_enforcement` comment, `cell.py:1875-1926` (now in `capabilities_document.py`), for
    # the full trace), so as of Phase 8 WP-1 rework 3 (裁定 3, 監督裁定
    # 2026-09-07) the combination is observed on NEITHER class, on NO
    # plug. The PROPOSITION this control protected -- V1 (d): an
    # `unavailable`/`deployment_required` entry MAY still carry a `limits`
    # value, it is not REQUIRED to -- remains fully enforced by `_assert_
    # v1_self_consistency` above (every plug, unconditionally); only the
    # non-vacuity OBSERVATION that some real declaration exercises that
    # allowance is what this WP removes.


# ---------------------------------------------------------------------------
# V2 -- declared bound vs. real refusal position, per plug.
# ---------------------------------------------------------------------------


def test_c05_v2_declaration_and_position_agree(adapter: ConformanceAdapter) -> None:
    """This is THE completion-condition-12 test (差し戻し指示 7): the
    per-plug non-vacuity assert below is what satisfies work order
    completion condition 12 ("V2 の per-plug 非空性") and is exercised by
    mutation 7 (a plug's declaration flattened to all-`unavailable` drives
    zero classes here and this assertion goes red). `test_c05_v2_per_plug_
    nonvacuity_would_be_caught`, previously a second module-level function,
    ran the IDENTICAL computation (same `_V2_DRIVERS` sweep, same `len(...)
    >= 1` shape) a second time against the same unmodified adapter and was
    removed (review finding F7: a real duplicate, not an independent
    check) -- one assertion, this one, now carries condition 12 alone."""
    driven = {name: driver(adapter) for name, driver in _V2_DRIVERS.items()}
    driven_classes = sorted(name for name, ok in driven.items() if ok)
    # per-plug non-vacuity (condition 12, C-17:182-218 precedent): a
    # session-crossing aggregate guard does not work under `-n 5
    # --dist loadgroup` (each plug is its own xdist group/worker) -- this
    # asserts non-vacuity WITHIN this one plug's own test.
    assert driven_classes, f"{adapter.name}: test_c05_v2's own sweep drove zero classes -- would be vacuous"


# ---------------------------------------------------------------------------
# L7-21 (Phase 8 WP-1b, R-C, design D-2 実装の形 (c)): peer-name-gated
# drive-or-not is closed as a STATIC property of this module's own source,
# not merely an absence observed at runtime on the currently-registered
# plugs (6 as of WP-4c). Two propositions, each its own test (design's
# own instruction: do NOT collapse this into "zero `adapter.name.
# startswith(` in the whole file" -- that form would also flag the 2
# allowlisted, genuinely peer-specific FACTS below, none of which decide
# "drive or not").
# ---------------------------------------------------------------------------

# The allowlist (design D-2 実装の形 (c) 表, WP-1b): every remaining
# `adapter.name` READ in this module that survives after `_drive_result_
# items`'/`_drive_query_complexity`'s own peer-name exclusions are
# removed (this WP) and `test_c05:646-659`'s V1 statistical control is
# removed (WP-1a) -- 2 functions, each reading `adapter.name` for a
# genuine peer-specific FACT (a counting rule, an observation-mechanism
# difference), never to decide whether a class is driven at all.
#
# WP-4c rework (監督裁定 wp4b-rulings.md 項 1): `_drive_requests_per_
# minute` is REMOVED from this allowlist -- its own `already_consumed`
# correction no longer reads `adapter.name` at all (it reads `adapter.
# transport_kind`, a non-name property; see that function's own updated
# comment). Leaving a stale entry here would fail this module's own
# `test_c05_l7_21_adapter_name_reads_are_allowlisted` second assertion
# (every allowlist entry must be backed by a real-code `adapter.name`
# match).
_ADAPTER_NAME_READ_ALLOWLIST = {
    "_schema_objects_unit_cost": (
        "peer ごとの実測計数規則 (r2db は entity+field 数で 3、MitateDB は table 1 個で 1) -- "
        "駆動可否ではなく期待値の計算である"
    ),
    "test_c05_e_isolated_application_surface_releases_resources": (
        "MitateDB in-process (SQLite) 固有の資源解放観測経路 -- 駆動可否ではなく観測手段の違いである"
    ),
}

# Phase 8 WP-1 rework 2 (裁定 5, 監督裁定 2026-09-07): replaces the prior
# `_ADAPTER_NAME_DECISION_PATTERN` regex-over-raw-source approach, which
# the review found matched inside COMMENTS and DOCSTRINGS as readily as
# inside real code (a function whose only real-code `adapter.name` read
# is `"http" in adapter.name` -- a membership test the regex's own
# `.startswith(`/`==` alternation never covered -- passed the old scan
# only because an unrelated comment a few lines above happened to
# contain the literal text `adapter.name == "r2db-api (http+postgres)"`
# -- a citation of a name this WP's own predecessor already removed,
# not a live decision). This visitor walks REAL AST NODES only
# (`ast.Compare`/`ast.Call`) -- a comment or docstring is not parsed
# into any node at all, so it structurally cannot produce a match here.


def _is_adapter_name_attr(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "name"
        and isinstance(node.value, ast.Name)
        and node.value.id == "adapter"
    )


class _AdapterNameReadVisitor(ast.NodeVisitor):
    """L7-21 (ii) (design D-2 実装の形 (c), 裁定 5 訂正): walks every
    `ast.FunctionDef` / `ast.AsyncFunctionDef` scope AND module-level
    (top-level, outside any function -- `<module>`) statements, and
    records a match only for a genuine peer-name EQUALITY (`adapter.name
    == "..."`), MEMBERSHIP (`"..." in adapter.name`), or PREFIX
    (`adapter.name.startswith(...)`) test found as a real `ast.Compare`/
    `ast.Call` node -- never a textual scan over the function's raw
    source (which would also match inside a comment or docstring; see
    this module's own history for why that mattered). Each match is
    attributed to its own INNERMOST enclosing function/async-function
    name (or `"<module>"`)."""

    def __init__(self) -> None:
        self.matches: list[tuple[str, int]] = []
        self._scope_stack: list[str] = ["<module>"]

    def _enter_scope(self, node: ast.AST, name: str) -> None:
        self._scope_stack.append(name)
        self.generic_visit(node)
        self._scope_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._enter_scope(node, node.name)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self._enter_scope(node, node.name)

    def visit_Compare(self, node: ast.Compare) -> None:  # noqa: N802
        operands = [node.left, *node.comparators]
        if any(_is_adapter_name_attr(operand) for operand in operands):
            if any(isinstance(op, (ast.Eq, ast.In)) for op in node.ops):
                self.matches.append((self._scope_stack[-1], node.lineno))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "startswith"
            and _is_adapter_name_attr(node.func.value)
        ):
            self.matches.append((self._scope_stack[-1], node.lineno))
        self.generic_visit(node)


def _if_gates_return_false_on_adapter_name(if_node: ast.If) -> bool:
    """Real-AST check (裁定 5, 監督裁定 2026-09-07): does this `If` node's
    own `test` read `adapter.name` in a genuine peer-name equality
    (`==`)/membership (`in`)/prefix (`.startswith(`) comparison -- the
    SAME `ast.Compare`/`ast.Call` shapes `_AdapterNameReadVisitor` above
    recognizes for L7-21 (ii), reused here rather than re-implemented --
    AND does its own `body` (the statements INSIDE the `if`, not any
    nested scope) contain a bare `return False`. This is the "drive or
    not, decided by which peer this is" shape L7-21 (i) forbids inside a
    `_V2_DRIVERS` function body."""
    test_visitor = _AdapterNameReadVisitor()
    test_visitor.visit(if_node.test)
    if not test_visitor.matches:
        return False
    return any(
        isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Constant) and stmt.value.value is False
        for stmt in if_node.body
    )


def test_c05_l7_21_v2_drivers_do_not_gate_drive_or_not_on_peer_name() -> None:
    """L7-21 (i) (design D-2 実装の形 (c)): none of `_V2_DRIVERS`' own
    driver function BODIES contains an early `if <adapter.name
    comparison>: return False` -- whether a class is driven at all is
    decided purely by this plug's own LIVE declaration
    (`limit_enforcement`) and (for `result_items`/`query_complexity`)
    port v1.12's own optional fields, never by which peer this is.

    Phase 8 WP-1 rework 3 (裁定 5, 監督裁定 2026-09-07): replaces the
    prior TEXT-line scan (`inspect.getsource(...).splitlines()` + string
    `in`/`==` matching over raw source text) with the SAME real-AST-node
    discipline `test_c05_l7_21_adapter_name_reads_are_allowlisted` (L7-21
    (ii), immediately below) already uses, via the shared `_AdapterName
    ReadVisitor` -- the prior text scan was asymmetric with (ii) exactly
    the way (ii)'s own docstring criticizes the OLD regex-over-raw-source
    approach it replaced: a comment or docstring line containing the
    literal text `adapter.name`/`return False` is not an AST node and
    structurally cannot match here, unlike a plain text scan.

    Mutation (design's own): reintroduce `if not adapter.name.startswith
    ("r2db-api"): return False` at the top of `_drive_result_items` ->
    this test goes red."""
    assert _V2_DRIVERS, "no V2 drivers registered -- this scan would be vacuous"
    offenders = []
    for name, driver in _V2_DRIVERS.items():
        func_node = ast.parse(inspect.getsource(driver)).body[0]
        assert isinstance(func_node, (ast.FunctionDef, ast.AsyncFunctionDef)), (
            f"{name}: expected a plain function definition, got {type(func_node).__name__}"
        )
        if any(
            isinstance(node, ast.If) and _if_gates_return_false_on_adapter_name(node)
            for node in ast.walk(func_node)
        ):
            offenders.append(name)
    assert not offenders, (
        f"V2 driver(s) still gate whether they drive at all on adapter.name: {offenders!r} -- decide via "
        "this plug's own live declaration/port capability instead"
    )


def test_c05_l7_21_adapter_name_reads_are_allowlisted() -> None:
    """L7-21 (ii) (design D-2 実装の形 (c), 裁定 5 訂正 監督裁定
    2026-09-07): every peer-name equality/membership/prefix test this
    module's own source performs against the adapter's own `name`
    attribute, found by `_AdapterNameReadVisitor` as a REAL `ast.Compare`
    (`==`/`in`) or `ast.Call` (`.startswith(`) node -- never a comment or
    docstring, which are not AST nodes at all -- is inside one of the 3
    allowlisted scopes above. The walk covers `ast.FunctionDef`,
    `ast.AsyncFunctionDef`, AND module-level (top-level) statements
    (`裁定 5`: the prior scan covered only `ast.FunctionDef`). A SECOND
    assertion (`裁定 5`) closes the inverse gap the prior scan's own
    review finding exposed: every allowlist entry must itself be hit by
    a REAL-CODE match, not merely declared -- `_drive_requests_per_
    minute`'s own real code (`"http" in adapter.name`) previously only
    satisfied the old regex-over-raw-source scan via an unrelated
    COMMENT a few lines above it (a citation of a peer-name literal this
    WP's predecessor already removed); this visitor's own `ast.Compare`
    handling for `ast.In` now matches that real code directly, so the
    allowlist entry is backed by an actual finding, not a comment
    artifact. Mutation (design's own): add a fresh MitateDB-api
    name-equality test inside some OTHER function in this file -> the
    first assertion goes red. Mutation (裁定 5's own): remove `ast.In`
    from `_AdapterNameReadVisitor.visit_Compare`'s accepted ops -> the
    second assertion goes red (`_drive_requests_per_minute` loses its
    only real-code match). (This docstring itself deliberately never
    spells the two matched code shapes out adjacently -- doing so would
    make this very test flag its own function.)"""
    source = Path(__file__).read_text()
    tree = ast.parse(source)
    visitor = _AdapterNameReadVisitor()
    visitor.visit(tree)
    assert visitor.matches, (
        "no peer-name equality/membership/prefix reads found in real code at all -- this scan would be vacuous"
    )
    matched_scopes = {scope for scope, _ in visitor.matches}
    offenders = sorted(matched_scopes - set(_ADAPTER_NAME_READ_ALLOWLIST))
    assert not offenders, f"peer-name equality/membership/prefix read outside the allowlist, in: {offenders!r}"
    unmatched_allowlist_entries = sorted(set(_ADAPTER_NAME_READ_ALLOWLIST) - matched_scopes)
    assert not unmatched_allowlist_entries, (
        f"allowlist entrie(s) with no REAL-CODE adapter.name match at all (comment-only citation, or stale "
        f"after an edit): {unmatched_allowlist_entries!r}"
    )


# ---------------------------------------------------------------------------
# V3 -- fail-loud: the fixed 9 are never `unavailable`, STATIC parametrize.
# ---------------------------------------------------------------------------

# Phase 8 WP-1a (design D-1, U-1 (A) 依頼者裁定 2026-09-06): 8 of the
# original 9 xfail'd (plug, class) pairs are REMOVED in this same commit
# as their enforcement -- `requests_per_minute`/`concurrency`/`request_
# bytes` are now genuinely `enforced` on BOTH MitateDB plugs (`cell.py`'s
# own `_LimitStateHolder`/`_measure_request_bytes`), and `execution_ms`
# is now genuinely declared `reference_wall_clock` (no longer bare
# `unavailable`) on both, matching r2db's own identical declaration.
#
# `("MitateDB-api", "operation_depth")` was, at that point, the ONE pair
# WP-1a's own report left xfail'd -- that report's own premise ("in-
# process has no request dict to bound, because `insert`/`update`/
# `delete` take positional/keyword ARGUMENTS, not a single dict") was
# factually wrong, per the code review that sent WP-1a back: `_limit_gate`
# is passed a REAL dict on every one of those call sites (`insert` builds
# `{"collection": ..., "values": ...}`, `cell.py:770`; `update`/`delete`
# likewise). Phase 8 WP-1a rework 1 (裁定 1, 監督裁定 2026-09-06) wired
# `_check_operation_depth` into `_limit_gate` (`cell.py:531`) for BOTH
# surfaces and measured it directly: with the default `max_operation_
# depth=8`, a bare `session.insert("t", {"doc": <7-levels-deep value>})`
# deterministically raises `LIMIT_EXCEEDED`/`operation_depth`, in-process,
# no HTTP transport involved. `("MitateDB-api", "operation_depth")` is
# therefore ALSO removed -- `cell.py`'s own `limit_enforcement` comment
# (`cell.py:1875-1926`) (now in `capabilities_document.py`) has the full trace, including the one real
# asymmetry that DOES remain between the two surfaces (which port
# ENTRY POINT a depth attack must use, not whether the peer enforces the
# bound at all).
# `("MitateDB-api-http", "operation_depth")` was already removed for its
# own, unrelated reason: `http.py::get_capabilities` overrides this one
# key to `enforced` for the HTTP surface (same override shape `request_
# bytes` used to need before this WP, now retired for THAT class since
# its own base declaration is symmetric).
#
# Net effect, Phase 8 WP-1 rework 3 (裁定 3, 監督裁定 2026-09-07): all 9
# of the original xfail'd pairs are now removed -- every one of the fixed
# 9 classes is non-`unavailable` on all 4 registered plugs (V3: `xfail`
# count is 0, `test_c05_v3_fixed_nine_are_not_unavailable` collects no
# `xfail`-marked case at all; see `CONDITIONS.md`'s own C-05 row).
_V3_KNOWN_UNAVAILABLE = frozenset()


def _v3_cases():
    for plug in _ALL_PLUG_NAMES:
        for cls in _FIXED_NINE:
            marks = []
            if (plug, cls) in _V3_KNOWN_UNAVAILABLE:
                marks.append(pytest.mark.xfail(
                    strict=True,
                    reason=(
                        "L7-1 (design docs/design/PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md "
                        f"§11): {plug} does not yet implement application-plane {cls!r} enforcement -- "
                        "next-phase candidate. strict=True: the day this class flips to enforced/reference_"
                        "wall_clock, this case XPASSes and turns red, forcing the xfail's removal in the same "
                        "commit as the implementation (§7.4)."
                    ),
                ))
            yield pytest.param(plug, cls, marks=marks, id=f"{plug}-{cls}")


# 差し戻し指示 3: module-scope cache keyed by plug name -- V3 collects 9
# cases (one per `_FIXED_NINE` class) for EACH of the 4 plugs, and the
# un-cached form called `adapter.capability_document()` fresh in every one
# of those 36 cases (9 real round trips per plug on an HTTP plug, only 4 of
# which are ever actually needed). This module is imported fresh per xdist
# worker process (`-n 5 --dist loadgroup`), so the cache's scope is
# naturally "once per plug per worker" -- never stale across a real run,
# never shared incorrectly across workers.
_V3_DOCUMENT_CACHE: dict[str, dict] = {}


def _v3_document(plug_name: str) -> dict:
    if plug_name not in _V3_DOCUMENT_CACHE:
        adapter = registered_adapters()[plug_name]
        _V3_DOCUMENT_CACHE[plug_name] = adapter.capability_document()
    return _V3_DOCUMENT_CACHE[plug_name]


@pytest.mark.parametrize("plug_name,cls", list(_v3_cases()))
def test_c05_v3_fixed_nine_are_not_unavailable(plug_name: str, cls: str) -> None:
    document = _v3_document(plug_name)
    status = document.get("limit_enforcement", {}).get(cls)
    assert status != "unavailable", (
        f"{plug_name}: fixed class {cls!r} is declared 'unavailable' -- SI-08 fail-loud violation "
        "unless this (plug, class) pair is in _V3_KNOWN_UNAVAILABLE with a strict xfail"
    )


# ---------------------------------------------------------------------------
# (e) -- isolated surface resource release (D-6.6).
# ---------------------------------------------------------------------------


def test_c05_e_isolated_application_surface_releases_resources(adapter: ConformanceAdapter) -> None:
    live_count = getattr(adapter, "_live_pg_backend_count", None)
    if live_count is not None:
        # WP-4 rework (完了条件 15 / F1 差し戻し 2 巡目, 監査 wp4-audit.md
        # §2): a bare "count everything under this run's prefix" pattern
        # ALSO counted the shared PLATFORM database (`<prefix>_platform`),
        # where the shared control stack's own lazily-opened connections
        # live -- setup traffic THIS test itself drives (`issue_credential`/
        # `authenticate` against the isolated instance's `copy.copy`-shared
        # control plane) opens those in-band, inside the measurement
        # window, making `before`/`after` depend on whether an earlier
        # test in the same worker process had already warmed that shared
        # pool. Scoping the pattern to ONLY the one application database
        # THIS test's own isolated instance will provision (`_provision_
        # pg_app`'s own `<prefix>_app_<application_id>` naming, computed
        # here BEFORE provisioning so `before` reflects a database that
        # does not exist yet -- a nonexistent `datname` simply matches
        # zero `pg_stat_activity` rows) removes the shared control pool
        # from every one of these three counts entirely.
        app_id = fresh_identifier("c05app")
        datname_like = f"{adapter._platform.prefix}_app_{app_id}"  # noqa: SLF001 -- duck-typed access to the shared platform prefix, same convention this file already uses for the MitateDB in-process branch below.
        before = live_count(datname_like)
        # 差し戻し指示 1 (review finding, mutD): both HTTP plugs' own
        # isolated_application_surface() cleanup closes each cell's pool
        # FIRST, then calls deprovision_application() (which DROPs the
        # per-application database). A plug that skips the close step
        # leaves live backends against that database, so deprovision's own
        # DROP fails at the psql level ("being accessed by other users")
        # and RAISES -- observed directly by mutating away the `cell.
        # close()` step on either HTTP plug: the exception propagated
        # through a bare `with` statement as an unrelated psql
        # RuntimeError, and this test's own `after == before` assertion
        # was never reached at all. Driving `__enter__`/`__exit__` by hand
        # decouples the resource-leak measurement from deprovision's own
        # success: `after` is captured (and asserted on) EVEN WHEN
        # `__exit__` itself subsequently raises, so it is the LEAK
        # (`after != before`) that goes red here, not deprovision's
        # downstream failure to drop a still-in-use database. A body
        # exception (the `during > before` assertion, or any port call
        # above it) is never swallowed -- it is forwarded to `__exit__` via
        # the ordinary context-manager protocol (real exc_info, not
        # `None, None, None`) and then re-raised unchanged.
        cm = adapter.isolated_application_surface()
        iso = cm.__enter__()
        try:
            dev, rt, _ = _provision_pair(iso, app_id=app_id)
            entity = fresh_identifier("c05e")
            iso.create_entity(dev, entity, {"label": "text"})
            iso.insert(rt, entity, {"label": "x"})
            during = live_count(datname_like)
            assert during > before, f"{adapter.name}: isolated surface opened no observable PG backend at all"
        except BaseException as exc:
            cm.__exit__(type(exc), exc, exc.__traceback__)
            raise
        cleanup_error: Exception | None = None
        try:
            cm.__exit__(None, None, None)
        except Exception as exc:  # noqa: BLE001 -- deliberately not
            # re-raised: this is the ONE exception this test exists to
            # NOT let mask the resource-leak assertion below (see comment
            # above). Recorded for the assertion message, never silently
            # dropped.
            cleanup_error = exc
        after = live_count(datname_like)
        assert after == before, (
            f"{adapter.name}: live PG backend count did not return to baseline after isolated_application_"
            f"surface() exit (before={before}, during={during}, after={after})"
            + (f"; __exit__ itself also raised: {cleanup_error!r}" if cleanup_error is not None else "")
        )
        return

    if adapter.name == "MitateDB-api":
        with adapter.isolated_application_surface() as iso:
            dev, rt, _ = _provision_pair(iso)
            entity = fresh_identifier("c05e")
            iso.create_entity(dev, entity, {"label": "text"})
            cells = list(iso._control.cells.values())  # noqa: SLF001
            assert cells, f"{adapter.name}: isolated surface provisioned no cell at all"
            connections = [cell._backend._db for cell in cells]  # noqa: SLF001
            for conn in connections:
                # Alive while the `with` block is open.
                conn.execute("SELECT 1")
        for conn in connections:
            with pytest.raises(Exception):  # sqlite3.ProgrammingError on a closed connection
                conn.execute("SELECT 1")
        return

    # `r2db-api` (in-process): D-6.6's own supervisor note -- genuinely no
    # external resource exists at all ("資源ゼロ"). Observed via Python
    # object liveness instead (D-6.5 addendum (3)).
    import gc
    import weakref

    with adapter.isolated_application_surface() as iso:
        ref = weakref.ref(iso)
        dev, rt, _ = _provision_pair(iso)
        entity = fresh_identifier("c05e")
        iso.create_entity(dev, entity, {"label": "text"})
        iso.insert(rt, entity, {"label": "x"})
        assert ref() is not None
    del iso
    gc.collect()
    assert ref() is None, f"{adapter.name}: isolated adapter instance was not released after context exit"
