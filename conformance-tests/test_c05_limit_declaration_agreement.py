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

_ALL_PLUG_NAMES = ("r2db-api", "r2db-api-http", "MitateDB-api", "MitateDB-api-http")


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
    with adapter.isolated_application_surface() as iso:
        doc = iso.capability_document()
        if doc.get("limit_enforcement", {}).get("operation_depth") != "enforced":
            return False
        # 差し戻し指示 5(c): read the declared bound from the capability
        # document (never trust it only by comment) and assert BOTH the
        # same exercisability ceiling every other count-valued driver in
        # this file asserts (mirrors `test_c14_authority_boundary.py:141`/
        # `:476`'s own identical `_MAX_EXERCISABLE_LIMIT` check) AND the
        # "flat insert sits at exactly the declared bound" premise the
        # N/N+1 recipe below depends on -- silently trusting the prose
        # comment (review finding F5(c): no bound was ever read here at
        # all) would let a profile/port-shape drift go undetected.
        bound = doc["limits"]["operation_depth"]
        assert bound <= _MAX_EXERCISABLE_LIMIT, f"{adapter.name}: operation_depth={bound} exceeds {_MAX_EXERCISABLE_LIMIT}"
        # A flat `{"entity": ..., "operations": [{"operation": "insert",
        # "values": {field: value}}]}` mutation request is measured
        # (`r2db-api/src/r2db_api/limits.py::check_depth`, `service.py`'s
        # own `_mutate_outcome`) to sit at REAL depth 4: the request dict
        # itself (1) -> its `operations` list (2) -> one operation dict
        # (3) -> that operation's own `values` dict (4). Both r2db
        # conformance plugs' own isolated profiles declare
        # `operation_depth=4` (`conformance_adapter_r2db.py:149`/
        # `conformance_adapter_r2db_http.py:759`) for exactly this reason
        # -- asserting the correspondence here, not only stating it in a
        # comment, is what turns "flat insert = declared N" into a real,
        # checkable premise rather than an assumption this driver's N/N+1
        # recipe silently depends on.
        assert bound == 4, (
            f"{adapter.name}: operation_depth isolated profile bound is {bound}, but this driver's flat-"
            "insert recipe is measured (r2db limits.py::check_depth) to sit at real depth 4 -- update BOTH "
            "the isolated profile's operation_depth and this assertion together if the recipe's measured "
            "depth ever changes"
        )
        dev, rt, _ = _provision_pair(iso)
        entity = fresh_identifier("c05od")
        iso.create_entity(dev, entity, {"label": "text"})

        # N: an ordinary, flat insert -- by construction of the isolated
        # profile's own `operation_depth` bound, this is EXACTLY at the
        # declared position (adapter.py's own isolated_application_
        # surface() docstring / each plug's own module comment / the
        # bound-vs-recipe assertion above).
        iso.attempt_mutation(rt, entity, "insert", values={"label": "x"}, where_field=None, where_value=None)

        # N+1: the SAME insert, with an added `where` filter -- adds one
        # nesting level. `insert` does not accept a filter at all
        # (semantically invalid), but `check_depth` runs BEFORE that
        # content check on both peers (r2db `service.py`'s own call
        # order; MitateDB has no such check at all -- excluded above by
        # its own `unavailable` declaration), so the REAL, observed
        # denial is deterministically LIMIT_EXCEEDED, never
        # VALIDATION_FAILED.
        with pytest.raises(ConformanceDenial) as excinfo:
            iso.attempt_mutation(rt, entity, "insert", values={"label": "x"}, where_field="label", where_value="x")
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

        # Measured (WP-4): both HTTP plugs' own `authenticate()` (above,
        # via `_provision_pair`) is a REAL `GET /v1/capabilities` round
        # trip under the SAME runtime credential -- it consumes exactly 1
        # unit of the SAME rate window this drive measures (unlike the
        # in-process plugs' own `authenticate()`, a bare local lookup that
        # never touches `_slot()`/`_acquire_rate` at all). The exact
        # position this drive must observe is therefore `bound - 1` on an
        # HTTP plug, `bound` on an in-process one.
        already_consumed = 1 if "http" in adapter.name else 0
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
    # design D-6.2: one-sided ONLY on `r2db-api` (both plugs) -- MitateDB's
    # own `result_items` enforcement (`cell.py`) triggers on the
    # REQUESTED page/limit value, which this port's `select_eq`/`attempt_
    # filter` never expose a parameter for at all; there is structurally
    # no request this file can construct through the port that would ever
    # reach MitateDB's own check. Disclosed in CONDITIONS.md's C-05 row
    # (differs from the design's own draft table, which did not carry
    # this port-shape detail -- 両側化ではなく「駆動しない」への格下げで
    # あり、理由を開示する, 完了条件16).
    if not adapter.name.startswith("r2db-api"):
        return False
    with adapter.isolated_application_surface() as iso:
        doc = iso.capability_document()
        if doc.get("limit_enforcement", {}).get("result_items") != "enforced":
            return False
        bound = doc["limits"]["result_items"]
        assert bound <= _MAX_EXERCISABLE_LIMIT, f"{adapter.name}: result_items={bound} exceeds {_MAX_EXERCISABLE_LIMIT}"
        dev, rt, _ = _provision_pair(iso)
        entity = fresh_identifier("c05ri")
        iso.create_entity(dev, entity, {"probe": "text"})
        for _ in range(bound):
            iso.insert(rt, entity, {"probe": "same"})

        rows = iso.select_eq(rt, entity, ["probe"], "probe", "same")
        assert len(rows) == bound, f"{adapter.name}: expected exactly {bound} matching rows, got {len(rows)}"

        iso.insert(rt, entity, {"probe": "same"})
        with pytest.raises(ConformanceDenial) as excinfo:
            iso.select_eq(rt, entity, ["probe"], "probe", "same")
        _assert_limit_exceeded(excinfo.value, "result_items", adapter_name=adapter.name)
        return True


def _drive_query_complexity(adapter: ConformanceAdapter) -> bool:
    # design D-6.2: one-sided ONLY on `r2db-api` (both plugs) -- r2db's own
    # complexity metric (`len(where) + len(select) + order_by_count`,
    # `structured.py`) can be driven purely through `select_eq`'s own
    # `select` list length; MitateDB's own metric is `len(filters)` ONLY
    # (`cell.py`), and this port's `select_eq`/`attempt_filter` can never
    # present more than ONE filter predicate in a single call, so no
    # request this file can construct through the port ever reaches
    # MitateDB's own check either. Same disclosed downgrade as
    # `result_items` above.
    if not adapter.name.startswith("r2db-api"):
        return False
    with adapter.isolated_application_surface() as iso:
        doc = iso.capability_document()
        if doc.get("limit_enforcement", {}).get("query_complexity") != "enforced":
            return False
        bound = doc["limits"]["query_complexity"]
        assert bound <= _MAX_EXERCISABLE_LIMIT, f"{adapter.name}: query_complexity={bound} exceeds {_MAX_EXERCISABLE_LIMIT}"
        dev, rt, _ = _provision_pair(iso)
        entity = fresh_identifier("c05qc")
        field_names = [f"f{i}" for i in range(bound + 2)]
        iso.create_entity(dev, entity, {name: "text" for name in field_names})
        iso.insert(rt, entity, {name: "x" for name in field_names})

        iso.select_eq(rt, entity, [field_names[0]], None, None)

        with pytest.raises(ConformanceDenial) as excinfo:
            iso.select_eq(rt, entity, field_names, None, None)
        _assert_limit_exceeded(excinfo.value, "query_complexity", adapter_name=adapter.name)
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
    base this file hard-codes."""
    assert frozenset(_ALL_PLUG_NAMES) == frozenset(registered_adapters().keys())
    assert len(_ALL_PLUG_NAMES) == 4


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
    come back. `MitateDB-api` (in-process)'s own real `request_bytes`
    (`cell.py:1491` publishes a value, `:1502` declares `unavailable`) is
    the one currently-registered case.

    差し戻し指示 6 (review finding F6): the previous body's only assertion
    was a bare `assert True` inside an `if` -- a tautology that would stay
    green NO MATTER WHAT `_assert_v1_self_consistency` did internally,
    directly contradicting this test's own (now corrected) docstring claim
    that it protects against (d)'s withdrawn rule being re-imposed INSIDE
    that helper. Made genuinely effective two ways: (1) actually CALL
    `_assert_v1_self_consistency` (with `required_fixed=()` / `capability_
    conditioned=None` / `audit_conditioned=False` -- this function's own
    defaults, deliberately keeping (e)'s required-entry sets out of scope,
    since this control is about (d) alone) against a document this
    adapter's own real declaration may carry such a combination on --
    if a future edit ever added a rejection of the unavailable+value
    combination inside that helper, THIS call raises and this test goes
    red, exactly what the docstring claims; (2) a real, non-tautological
    non-vacuity assertion on `MitateDB-api` specifically (the one plug the
    docstring already names as genuinely non-vacuous) that the combination
    is actually observed -- harmless on every other plug, per the
    docstring, because `required=False` there, not because the assertion
    itself is vacuous."""
    document = adapter.capability_document()
    _assert_v1_self_consistency(document, adapter_name=adapter.name, plane="application")

    limits = document.get("limits", {}) or {}
    enforcement = document.get("limit_enforcement", {}) or {}
    found = any(
        status in ("unavailable", "deployment_required") and cls in limits
        for cls, status in enforcement.items()
    )
    if adapter.name == "MitateDB-api":
        assert found, (
            f"{adapter.name}: expected an unavailable/deployment_required class to still publish a "
            "limits value (cell.py's own request_bytes) -- this is the ONE currently-registered case "
            "this control test exists to protect"
        )


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
# V3 -- fail-loud: the fixed 9 are never `unavailable`, STATIC parametrize.
# ---------------------------------------------------------------------------

# design D-6.1 V3 / §7.4: MitateDB in-process is `unavailable` for 5 of the
# fixed 9 (execution_ms/concurrency/requests_per_minute/operation_depth --
# L7-1 -- plus request_bytes, which this peer's own `request_bytes: value +
# unavailable` in-process declaration means V3 (unlike V1 (d)) treats as
# indistinguishable from "not implemented", D-6.1 V3's own final
# paragraph); MitateDB HTTP is `unavailable` for 4 (request_bytes is
# `enforced` there, `http.py:591`'s own override). Total 5 + 4 = 9.
# `operation_depth`'s branch was MEASURED (WP-4, not assumed): no code
# path anywhere in `MitateDB-api/src` bounds operation/filter nesting
# depth at all (contrast r2db's real, enforced `limits.py:88-90`).
_V3_KNOWN_UNAVAILABLE = frozenset({
    ("MitateDB-api", "execution_ms"),
    ("MitateDB-api", "concurrency"),
    ("MitateDB-api", "requests_per_minute"),
    ("MitateDB-api", "operation_depth"),
    ("MitateDB-api", "request_bytes"),
    ("MitateDB-api-http", "execution_ms"),
    ("MitateDB-api-http", "concurrency"),
    ("MitateDB-api-http", "requests_per_minute"),
    ("MitateDB-api-http", "operation_depth"),
})


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
