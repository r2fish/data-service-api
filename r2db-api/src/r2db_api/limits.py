"""Finite, discoverable resource bounds."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Callable

from .errors import fail


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

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if not isinstance(value, int) or value <= 0:
                raise ValueError(f"resource limit {name} must be finite and positive")

    def as_dict(self) -> dict[str, int]:
        return asdict(self)

    def check(self, kind: str, actual: int) -> None:
        bound = self.as_dict().get(kind)
        if bound is None:
            fail("VALIDATION_FAILED", "Unknown resource class.", details={"field": kind})
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
                    fail("VALIDATION_FAILED", "Cyclic request structures are not supported.")
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
                fail("VALIDATION_FAILED", "Request contains an unsupported value type.")
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
                fail("VALIDATION_FAILED", "Cyclic request structures are not supported.")
            seen.add(marker)
            next_depth = current + 1
            if next_depth > self.operation_depth:
                fail("LIMIT_EXCEEDED", "Operation nesting exceeds the configured limit.", status=413, details={"resource": "operation_depth", "limit_class": "operation_depth", "limit": self.operation_depth})
            children = item.values() if isinstance(item, dict) else item
            stack.extend((child, next_depth) for child in children)


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

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if not isinstance(value, int) or value <= 0:
                raise ValueError(f"control-plane limit {name} must be finite and positive")

    def as_dict(self) -> dict[str, int]:
        return asdict(self)
