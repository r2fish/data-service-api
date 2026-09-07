"""Finite, discoverable resource bounds."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Callable

from .errors import fail, violation


@dataclass(frozen=True)
class ResourceLimits:
    request_bytes: int = 1_048_576
    batch_items: int = 100
    result_items: int = 1_000
    query_complexity: int = 50
    execution_ms: int = 5_000
    concurrency: int = 32
    requests_per_minute: int = 600
    schema_objects: int = 1_000
    operation_depth: int = 8
    # Contract 1.7.0 (D-2 (7), §5 U-1 = (β), WP-2a): field-level `enum`
    # declaration cardinality -- how many members one field's declared
    # `enum` may carry. Default matches `limits.example_profile.
    # enum_members` in `spec/data-service-api.v1.json` verbatim, the same
    # convention every other field above already follows. Enforced through
    # the SAME generic `check()`/`as_dict()` machinery below -- no special-
    # cased method needed, exactly like every other COUNT-valued class.
    enum_members: int = 64
    # Contract 1.7.0 (D-5 (5)/S-f, WP-2c): Application-scoped idempotency
    # record bounds -- `idempotency_entries` (how many live, unexpired
    # records one Application may hold at once) and `idempotency_retention_
    # ms` (how long a record stays live after it is written). Defaults
    # match `limits.example_profile.idempotency_entries`/`.idempotency_
    # retention_ms` verbatim (`spec/data-service-api.v1.json`, 10000 /
    # 86400000). `idempotency_entries` is enforced through the SAME generic
    # `check()` machinery every other COUNT-valued class already uses
    # (`ApplicationCell`/`PostgresCell`'s own idempotency reservation calls
    # `limits.check("idempotency_entries", ...)`, ruling I-6); `idempotency_
    # retention_ms` is a duration, read directly (never through `check()`)
    # wherever a record's own expiry is computed. Declaring both in this
    # same commit as `capabilities().idempotency` flipping to `enabled` is
    # what C-05 V1 (e) (`_CAPABILITY_CONDITIONED`) requires -- both keys
    # automatically reach `capabilities()`'s `limits`/`limit_enforcement`
    # documents through `as_dict()` below, with no separate wiring needed.
    idempotency_entries: int = 10_000
    idempotency_retention_ms: int = 86_400_000

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if not isinstance(value, int) or value <= 0:
                raise ValueError(f"resource limit {name} must be finite and positive")

    def as_dict(self) -> dict[str, int]:
        return asdict(self)

    def check(self, kind: str, actual: int) -> None:
        bound = self.as_dict().get(kind)
        if bound is None:
            fail("VALIDATION_FAILED", "Unknown resource class.", details=violation("budget", field=kind))
        if actual < 0 or actual > bound:
            fail("LIMIT_EXCEEDED", "Request exceeds the configured resource limit.", status=413, details={"resource": kind, "limit_class": kind, "limit": bound})

    def check_request(self, request: Any) -> None:
        # Iterative bounded measurement avoids recursive repr() and avoids
        # materializing oversized serialized request bodies.
        bound = self.request_bytes
        total = 0
        stack = [request]
        seen: set[int] = set()
        while stack:
            item = stack.pop()
            if isinstance(item, (dict, list, tuple, set)):
                marker = id(item)
                if marker in seen:
                    fail("VALIDATION_FAILED", "Cyclic request structures are not supported.", details=violation("request_schema"))
                seen.add(marker)
            if isinstance(item, dict):
                total += 2
                if len(item) > bound // 8:
                    fail("LIMIT_EXCEEDED", "Request exceeds the configured resource limit.", status=413, details={"resource": "request_bytes", "limit_class": "request_bytes", "limit": bound})
                stack.extend(item.keys())
                stack.extend(item.values())
            elif isinstance(item, (list, tuple, set)):
                total += 2
                if len(item) > bound // 8:
                    fail("LIMIT_EXCEEDED", "Request exceeds the configured resource limit.", status=413, details={"resource": "request_bytes", "limit_class": "request_bytes", "limit": bound})
                stack.extend(item)
            elif isinstance(item, str):
                total += len(item) * 4
            elif isinstance(item, (bytes, bytearray)):
                total += len(item)
            elif item is None or isinstance(item, (bool, int, float)):
                total += 8
            else:
                fail("VALIDATION_FAILED", "Request contains an unsupported value type.", details=violation("request_schema"))
            if total > bound:
                fail("LIMIT_EXCEEDED", "Request exceeds the configured resource limit.", status=413, details={"resource": "request_bytes", "limit_class": "request_bytes", "limit": bound})

    def check_deadline(self, deadline: float, clock: Callable[[], float]) -> None:
        if clock() > deadline:
            fail("LIMIT_EXCEEDED", "Operation exceeds the execution budget.", status=413, details={"resource": "execution_ms", "limit_class": "execution_ms", "limit": self.execution_ms})

    def check_depth(self, value: Any) -> None:
        stack = [(value, 0)]
        seen: set[int] = set()
        while stack:
            item, current = stack.pop()
            if not isinstance(item, (dict, list, tuple, set)):
                continue
            marker = id(item)
            if marker in seen:
                fail("VALIDATION_FAILED", "Cyclic request structures are not supported.", details=violation("request_schema"))
            seen.add(marker)
            next_depth = current + 1
            if next_depth > self.operation_depth:
                fail("LIMIT_EXCEEDED", "Operation nesting exceeds the configured limit.", status=413, details={"resource": "operation_depth", "limit_class": "operation_depth", "limit": self.operation_depth})
            children = item.values() if isinstance(item, dict) else item
            stack.extend((child, next_depth) for child in children)


# Contract 1.7.0 (D-6 (2), addendum R-g, WP-2d): the applicability table --
# which `budget` classes carry meaning on which endpoint. `mutate`/`cross_
# entity_mutate` share the identical pair (D-6's own v1.1 revision, review
# round M3/supervisor ruling R-g: `result_items` bounds a QUERY's returned
# rows, never a mutation's own `affected` count -- this version gives no
# request a way to narrow that). r2db has no executable `cross_entity_
# mutate` path (`capabilities().cross_entity_mutation` is `unavailable`,
# `http.py:post_cross_entity_mutate` is a stub), so only "query"/"mutate"/
# "schema" are ever passed as `endpoint_kind` in practice -- the fourth key
# is carried here anyway so this table stays the complete D-6 (2) table,
# not a peer-narrowed subset a future cross-entity WP would have to widen.
_BUDGET_APPLICABLE_CLASSES: dict[str, frozenset[str]] = {
    "query": frozenset({"result_items", "execution_ms"}),
    "mutate": frozenset({"execution_ms", "batch_items"}),
    "cross_entity_mutate": frozenset({"execution_ms", "batch_items"}),
    "schema": frozenset({"execution_ms"}),
}


def _json_type_name(value: Any) -> str:
    """Ruling J-2/contract `errors.details_vocabulary.VALIDATION_FAILED.
    observed_type`'s own vocabulary: "the JSON type of the value actually
    received (string, integer, number, boolean, object, array or null)".
    Only reached from `narrow_limits_by_budget` below, for a `budget/
    <class>` value that failed the `isinstance(int) and not bool` test --
    `bool` is handled by its own caller (JSON `true`/`false` is contract
    type `boolean`, never `integer`, even though Python's `bool` is an
    `int` subclass), so this function itself never needs to special-case
    it. Mirrors MitateDB's identical `_JSON_TYPE_NAME` (`config.py`) --
    same 7-way mapping, this peer's own naming convention (lowercase,
    leading underscore) rather than a verbatim port of the name."""
    if isinstance(value, bool):
        return "boolean"
    if value is None:
        return "null"
    if isinstance(value, str):
        return "string"
    if isinstance(value, float):
        return "number"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "integer"


def narrow_limits_by_budget(deployed: ResourceLimits, budget: dict[str, Any] | None, endpoint_kind: str) -> ResourceLimits:
    """Contract 1.7.0 (D-6, addendum 2 S-l, work order §2 WP-2d, ruling
    B-2/B-5): the SINGLE point that turns one request's own `budget` into
    the "effective limits" every existing check point downstream reads --
    `ApplicationCell`/`PostgresCell`'s `query`/`transact`/`apply_schema`
    already take a `limits: ResourceLimits` argument and call `.check(...)`
    on it; this function's caller (`service.py`) passes ITS return value in
    place of the deployed `self.limits` at exactly one call site per
    endpoint, rather than any downstream check point being rewritten to
    know about `budget` at all. This is what makes "a check point budget
    forgot to narrow" structurally impossible, not merely tested against
    (D-6 (2)'s own "検査点を個別に書き換えない").

    Validates in the same pass (addendum 2 S-l: budget validity is checked
    at request-shape time, before target existence/confirmation/
    precondition): a class `budget` names that `endpoint_kind` has no
    meaning for, a value that is not a plain positive int, or a value
    above `deployed`'s own declared bound for that class, is refused with
    `VALIDATION_FAILED`/`violated_declaration: budget`/`field: budget/
    <class>` -- never silently clamped or ignored. `budget is None` (the
    ordinary, unbudgeted request) returns `deployed` itself unchanged --
    no new object, no validation cost paid.
    """
    if budget is None:
        return deployed
    if not isinstance(budget, dict):
        fail("VALIDATION_FAILED", "budget must be an object.", details={"violated_declaration": "budget", "field": "budget"})
    applicable = _BUDGET_APPLICABLE_CLASSES.get(endpoint_kind, frozenset())
    deployed_values = deployed.as_dict()
    narrowed_values = dict(deployed_values)
    for class_name, requested in budget.items():
        if class_name not in applicable:
            fail(
                "VALIDATION_FAILED", "budget names a resource class that does not apply to this endpoint.",
                details={"violated_declaration": "budget", "field": f"budget/{class_name}"},
            )
        # Ruling J-2 (WP-2cd audit N-2, monitor's (α)): the non-integer leg
        # is split from the `< 1` leg so ONLY the former carries `declared_
        # type`/`observed_type` -- ruling B-1's own parenthetical ("declared_
        # type / observed_type は非整数のときのみ") read literally, and now
        # matching MitateDB's identical 2-branch shape (`config.py`'s own
        # `narrow_limits_by_budget`) so the SAME rejection returns the SAME
        # `details` shape on both peers.
        if not isinstance(requested, int) or isinstance(requested, bool):
            fail(
                "VALIDATION_FAILED", "budget values must be integers of at least 1.",
                details={
                    "violated_declaration": "budget", "field": f"budget/{class_name}",
                    "declared_type": "integer", "observed_type": _json_type_name(requested),
                },
            )
        if requested < 1:
            fail(
                "VALIDATION_FAILED", "budget values must be integers of at least 1.",
                details={"violated_declaration": "budget", "field": f"budget/{class_name}"},
            )
        if requested > deployed_values[class_name]:
            fail(
                "VALIDATION_FAILED", "budget exceeds this deployment's own declared value for this resource class.",
                details={"violated_declaration": "budget", "field": f"budget/{class_name}"},
            )
        # P-5/D-6 (3): downward-only -- `min` never `max` (C-24 variant 1).
        narrowed_values[class_name] = min(deployed_values[class_name], requested)
    return ResourceLimits(**narrowed_values)


@dataclass(frozen=True)
class ControlPlaneLimits:
    """CCR-14 WP-3, R-7: the 3 control-plane resource classes (contract
    `limits.classes`' control-plane subset -- `applications`, `credentials_
    per_application`, `control_requests_per_minute`). A separate, smaller
    dataclass from `ResourceLimits` above rather than folding these 3 fields
    into it: the two are enforced by two different services (`DataService`
    vs. the new `ControlPlaneService`) against two different resource
    universes, and design docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md §1 R-7
    describes them as the control plane's "own" bounds, discovered through
    the control plane's own `GET /control/v1/capabilities` -- not a subset a
    caller could confuse with `ResourceLimits.as_dict()`'s application-plane
    keys. Defaults are the contract's own `example_profile` values for
    exactly these 3 keys (`spec/data-service-api.v1.json`). Deployment-
    profile injection (environment-variable driven) is a composition-root
    concern (WP-4/5, `R2DB_CONTROL_LIMIT_*` per the design) -- this WP only
    injects the profile object itself, mirroring `ResourceLimits`'s own
    established convention.
    """

    applications: int = 100
    credentials_per_application: int = 10
    control_requests_per_minute: int = 60
    # Phase 3.5 WP-4 (design PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md §4
    # "L4", DESTRUCTIVE_CONFIRMATION_V1.md §8.1(d)): the control plane's own
    # `request_bytes` byte bound, discoverable through `GET /control/v1/
    # capabilities` the same way the 3 fields above already are. Defaults to
    # the exact value `control_http.py` has enforced since WP-4 (`ResourceLimits().
    # request_bytes`, 1 MiB) -- this is a declaration of an existing fact, not
    # a behavior change; `control_http.py` is revised in this same commit to
    # read this field instead of constructing its own separate `ResourceLimits()`,
    # so the declared and enforced numbers can never drift apart (single
    # source, mirroring MitateDB-api's identical `ControlPlaneLimits.
    # request_bytes` field).
    request_bytes: int = 1_048_576
    # Phase 4 WP-2(b) (design PHASE4_DURABLE_AUDIT_SINK_V1.md D-5, work
    # order WP-2(b) / P4-D4 item 8): `audit_query`'s own pre-auth fixed
    # window -- a SEPARATE counter from `control_requests_per_minute`
    # above, never sharing its bucket (`ControlPlaneService.
    # check_audit_rate`/`_check_audit_rate`, `control_plane.py`). Default
    # matches `control_requests_per_minute`'s own default (60) -- both are
    # deployer-tunable via the identical env-var convention
    # (`R2DB_CONTROL_LIMIT_AUDIT_REQUESTS_PER_MINUTE`, `control_main.py`).
    audit_requests_per_minute: int = 60

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if not isinstance(value, int) or value <= 0:
                raise ValueError(f"control-plane limit {name} must be finite and positive")

    def as_dict(self) -> dict[str, int]:
        return asdict(self)
