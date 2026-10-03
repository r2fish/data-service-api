"""Finite, discoverable resource bounds."""
from __future__ import annotations

from dataclasses import dataclass, asdict, replace
from typing import Any, Callable, Mapping

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
        """Refuses with `LIMIT_EXCEEDED` / `execution_ms` once less than 1 ms of the request's budget remains, reading the clock once and never touching the database. The threshold is the smallest remaining budget a whole-millisecond statement bound can express."""
        if (deadline - clock()) * 1000 < 1:
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


#: (design docs/design/MULTI_PROCESS_WORKER_V0_1.md D-3 (5)):
#: the constant added to the real effective thread limit --
#: `role_pool_size`'s own docstring below spells out what the 2 extra
#: connections are for (this process' own platform rate statement,
#: `credential_store.PostgresCredentialStore.record_rate_and_check`, and one
#: spare).
_POOL_SIZE_HEADROOM = 2


def thread_limit_from_env(env: Mapping[str, str], name: str, default: int) -> int:
    """(design D-3 (5)): the env-declared-thread-limit reader
    `r2db_api.control_main`'s own startup and `r2db_api.ops`'s own
    `verify-declarations` operator diagnostic both read `R2DB_THREAD_
    LIMIT` through directly. `r2db_api.main`'s own startup keeps its OWN
    body of the same reader instead (a registered isomorphism target
    against MitateDB-api's own same-named function, and an AST-isolated-
    exec unit-test subject, `tests/test_threadpool_offload.py`) --
    `tests/test_threadpool_offload.py::test_thread_limit_from_env_agrees_
    with_the_shared_limits_reader` pins that the two bodies agree on
    every input rather than letting them
    diverge silently. Unset or empty falls back to `default`; a non-empty
    value that is not a positive integer stops the caller (`ValueError`
    naming `name`) rather than silently degrading -- this sizes a
    worker-thread pool (`role_pool_size`), a resource dimension a
    deployer's typo should never silently mis-size.
    """
    raw = env.get(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{name} must be a positive integer, got {raw!r}") from None
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer, got {raw!r}")
    return value


def role_pool_size(thread_limit: int) -> int:
    """(design D-3 (5)): the per-served-application PostgreSQL role pool
    capacity (runtime AND developer -- `r2db_api.postgres.PostgresCell`
    takes one `pool_size` for both roles) AND `r2db_api.main`'s own
    platform pool (`R2DB_PLATFORM_POOL_SIZE`'s own default) both derive
    from `thread_limit` -- the effective, env-overridden `ThreadLimit
    Middleware` value (`http.py`'s own `create_app(..., thread_limit=)`).

    Basis: the number of connections ONE process can genuinely have in
    flight at once is bounded by how many worker THREADS that process'
    own event loop ever hands a synchronous request section to (`run_in_
    threadpool`, `http.py`) -- `thread_limit` is that real per-process
    ceiling. `ResourceLimits.concurrency` is the deployment-wide
    admission bound every worker process enforces TOGETHER (the host-
    shared slot directory), never a per-process connection ceiling, so
    it is not the basis this function reads. `thread_limit + 2` (the
    `+ 2` headroom below: this process' own platform rate statement,
    and one spare connection) lets
    `process_ceilings.data` processes share `max_connections` without
    the connection-budget arithmetic scaling with the declared
    `concurrency` bound (design's own "宣言値 L は接続予算に入らない
    (slot は接続を持たない)").

    A per-application pool sized below the real number of requests that
    application can present to it at once turns a declared 429 LIMIT_
    EXCEEDED into a pool-wait-timeout 503 instead (`postgres.py`'s own
    `_DEFAULT_ACQUIRE_TIMEOUT_S`) -- `_RolePool.connection()` times out
    and fails closed at 503 well under the declared bound. The real
    per-process ceiling on simultaneous borrows is `thread_limit` (a
    `run_in_threadpool` caller waits for a free WORKER THREAD before it
    can ever reach the pool at all, `http.py`'s own `ThreadLimit
    Middleware`); `concurrency` bounds admission across every worker
    process together (the host-shared slot directory), not simultaneous
    DB borrows by any one process -- so this function sizes the pool
    from `thread_limit`, not from `concurrency`.
    `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md`'s role-pool-ceiling
    note carries the resulting `max_connections` arithmetic.
    """
    if isinstance(thread_limit, bool) or not isinstance(thread_limit, int) or thread_limit < 1:
        raise ValueError(f"thread_limit must be a positive integer, got {thread_limit!r}")
    return thread_limit + _POOL_SIZE_HEADROOM


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

# Phase 9 R-5/R-6 pair-closing commit (peer symmetry with MitateDB-api's
# own `config._BUDGET_CLASS_TO_FIELD`): the budget-class-name -> dataclass-
# field-name lookup `narrow_limits_by_budget` below reads through `getattr`/
# the `replace(deployed, **narrowed)` call, so the pinned function's own
# body never has to know whether a class name and its deployment field
# happen to share a spelling. On THIS peer they always do (`ResourceLimits`
# was named field-for-field after `limits.classes`, D-6's own applicable-
# classes table above); this identity table exists only so the technique
# itself -- not merely its outcome -- matches MitateDB-api's `Foundation
# Config`, whose fields do NOT share the budget classes' own spelling
# (`max_result_rows`, not `result_items`). A peer-specific VALUE table
# (like `_BUDGET_APPLICABLE_CLASSES` above), intentionally kept OUTSIDE
# the isomorphism-pinned function body.
_BUDGET_CLASS_TO_FIELD: dict[str, str] = {
    "result_items": "result_items",
    "execution_ms": "execution_ms",
    "batch_items": "batch_items",
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


def _budget_denied(message: str, field: str, **extra: Any) -> None:
    """Phase 9 R-5/R-6 pair-closing commit: the ONE place `narrow_limits_
    by_budget` below turns a budget-shape violation into this peer's own
    denial (`fail()`, `VALIDATION_FAILED`) -- pulled out of the pinned
    function body itself (isomorphism table row `narrow_limits_by_budget`,
    `tests/test_audit_query.py`) so that body's own text never has to
    spell either peer's own exception vocabulary. MitateDB-api's `config.
    py` places an identically-named, identically-signatured wrapper next
    to its own `narrow_limits_by_budget` that raises `errors.
    ValidationError` instead -- the two wrappers are deliberately NOT
    pinned isomorphic to each other (only the function that calls them,
    identically, is); each is free to stay exactly as small as its own
    peer's error type requires."""
    fail("VALIDATION_FAILED", message, details={"violated_declaration": "budget", "field": field, **extra})


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
    <class>` -- never silently clamped or ignored. `budget is None` OR
    `{}` (no class named at all -- Phase 9 R-5/R-6 pair-closing commit,
    matching MitateDB-api's own established behaviour) returns `deployed`
    itself unchanged -- no new object, no validation cost paid.

    Peer-symmetry note (isomorphism table row, `tests/test_audit_query.
    py`): isomorphic to MitateDB-api's own `config.narrow_limits_by_
    budget(deployed, budget, endpoint_kind)` -- same name, same 3-argument
    signature, same behaviour. No code is shared between peers; `_budget_
    denied`/`_BUDGET_CLASS_TO_FIELD` immediately above absorb the two
    peers' own exception vocabulary and dataclass-field-naming difference
    OUTSIDE this body, mirroring `validate_enum_declaration`'s own `_fail_
    constraint_declaration` precedent above in this same module.
    """
    if not budget:
        return deployed
    if not isinstance(budget, dict):
        _budget_denied("budget must be an object.", "budget")
    applicable = _BUDGET_APPLICABLE_CLASSES.get(endpoint_kind, frozenset())
    narrowed: dict[str, int] = {}
    for class_name, requested in budget.items():
        if class_name not in applicable:
            _budget_denied(
                "budget names a resource class that does not apply to this endpoint.",
                f"budget/{class_name}",
            )
        # Ruling J-2 (WP-2cd audit N-2, monitor's (α)): the non-integer leg
        # is split from the `< 1` leg so ONLY the former carries `declared_
        # type`/`observed_type` -- ruling B-1's own parenthetical ("declared_
        # type / observed_type は非整数のときのみ") read literally, and now
        # matching MitateDB's identical 2-branch shape (`config.py`'s own
        # `narrow_limits_by_budget`) so the SAME rejection returns the SAME
        # `details` shape on both peers.
        if not isinstance(requested, int) or isinstance(requested, bool):
            _budget_denied(
                "budget values must be integers of at least 1.",
                f"budget/{class_name}",
                declared_type="integer", observed_type=_json_type_name(requested),
            )
        if requested < 1:
            _budget_denied("budget values must be integers of at least 1.", f"budget/{class_name}")
        field_name = _BUDGET_CLASS_TO_FIELD[class_name]
        deployed_value = getattr(deployed, field_name)
        if requested > deployed_value:
            _budget_denied(
                "budget exceeds this deployment's own declared value for this resource class.",
                f"budget/{class_name}",
            )
        # P-5/D-6 (3): downward-only -- `min` never `max` (C-24 variant 1).
        narrowed[field_name] = min(deployed_value, requested)
    return replace(deployed, **narrowed)


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
    # order WP-2(b) / P4-D4 item 8): `audit_query`'s own pre-auth
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
