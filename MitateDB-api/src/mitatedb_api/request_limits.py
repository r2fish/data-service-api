"""MitateDB request-size and operation-depth limit checks (CE2).

This is a pure leaf: `_measure_request_bytes` and `_check_operation_depth`
are total, deterministic structural walks over an already-traversable
request (via `request_traversal._as_traversable`), using only the
explicit `bound` each caller passes in -- no connection, no catalog read,
no request/limits/principal state beyond that argument. The choke point
that decides WHEN these run, in what order, and what a denial from either
of them means for the rest of the gate (`ApplicationCell._limit_gate`, in
`cell.py`) remains in its own module.
"""
from __future__ import annotations

from .errors import ResourceLimitError, ValidationError, violation
from .request_traversal import _as_traversable


def _measure_request_bytes(request, bound):
    """r2db `limits.py::ResourceLimits.check_request` (`:37-70`) and this
    peer's own structural estimate (design D-1 "実現方式") are
    independent realizations of the SAME measurement (P-6): str is
    `len * 4`, bytes is `len`, a scalar/`None`/bool is 8, a container
    (dict/list/tuple/set) costs 2 plus an early per-container
    `bound // 8` element-count reject -- so both peers refuse the same
    clearly-oversized request shape at the same class (`request_bytes`),
    even though neither shares code. Raises `errors.ResourceLimitError`
    (`limit_class="request_bytes"`) the moment either the running total or
    a single container's own element count crosses `bound`.

    Cycle detection is scoped to the CURRENT ANCESTOR PATH (each stack
    frame carries its own `frozenset` of container ids seen on the way
    down to it), not to every container ever visited across the whole
    structure -- the same object legitimately appearing more than once as
    UNRELATED siblings (e.g. a batch built from `[operation] * n`, a real
    shape this package's own tests construct) is not a cycle and must not
    be rejected as one; only a container that is its own ancestor (truly
    self-referential) is."""
    total = 0
    stack = [(request, frozenset())]
    while stack:
        raw_item, ancestors = stack.pop()
        item = _as_traversable(raw_item)
        child_ancestors = ancestors
        if isinstance(item, (dict, list, tuple, set)):
            marker = id(item)
            if marker in ancestors:
                # WP-3e rework T1 (追補 L-1): `request_schema`, no `field`
                # -- this walk has no request-relative path to attribute
                # a cycle to (an id()-keyed ancestor stack, not a
                # positional traversal), mirrors r2db-api's own bare
                # `violation("request_schema")` sites for a shape defect
                # that is not about any one field.
                raise ValidationError(
                    "cyclic request structures are not supported",
                    details=violation("request_schema"),
                )
            child_ancestors = ancestors | {marker}
        if isinstance(item, dict):
            total += 2
            if len(item) > bound // 8:
                raise ResourceLimitError("request size limit exceeded", limit_class="request_bytes")
            stack.extend((k, child_ancestors) for k in item.keys())
            stack.extend((v, child_ancestors) for v in item.values())
        elif isinstance(item, (list, tuple, set)):
            total += 2
            if len(item) > bound // 8:
                raise ResourceLimitError("request size limit exceeded", limit_class="request_bytes")
            stack.extend((c, child_ancestors) for c in item)
        elif isinstance(item, str):
            total += len(item) * 4
        elif isinstance(item, (bytes, bytearray)):
            total += len(item)
        elif item is None or isinstance(item, (bool, int, float)):
            total += 8
        else:
            total += 8
        if total > bound:
            raise ResourceLimitError("request size limit exceeded", limit_class="request_bytes")


def _check_operation_depth(request, bound):
    """r2db `limits.py::ResourceLimits.check_depth` (`:77-90`), same
    "independent realization of the same contract-level measurement"
    relationship as `_measure_request_bytes` above (P-6): counts nesting
    levels across dict/list/tuple/set containers (a `Filter` dataclass
    counts as one such container, via `_as_traversable`), raising
    `errors.ResourceLimitError` (`limit_class="operation_depth"`) the
    moment the nesting exceeds `bound`. Runs BEFORE any content
    validation of `request` (design D-1 "検査の形": the depth check is
    part of the gate, which runs before `_prepare_values`/`_bind_filters`/
    `_validate_update`/`_validate_delete_confirmation`), mirroring r2db's
    own call order (`service.py`: `check_request` / `check_depth` both
    precede the backend dispatch that would otherwise reject a malformed
    shape first).

    Cycle detection is scoped to the current ancestor path, exactly like
    `_measure_request_bytes` above -- see that function's own docstring
    for why (the same object appearing more than once as unrelated
    siblings, e.g. `[operation] * n`, is not a cycle)."""
    stack = [(request, 0, frozenset())]
    while stack:
        raw_item, current, ancestors = stack.pop()
        item = _as_traversable(raw_item)
        if not isinstance(item, (dict, list, tuple, set)):
            continue
        marker = id(item)
        if marker in ancestors:
            # WP-3e rework T1 (追補 L-1): mirrors `_measure_request_
            # bytes`'s own identical site immediately above.
            raise ValidationError(
                "cyclic request structures are not supported",
                details=violation("request_schema"),
            )
        child_ancestors = ancestors | {marker}
        next_depth = current + 1
        if next_depth > bound:
            raise ResourceLimitError("operation nesting exceeds the configured limit", limit_class="operation_depth")
        children = item.values() if isinstance(item, dict) else item
        stack.extend((child, next_depth, child_ancestors) for child in children)
