"""MitateDB provisional-capability gate (CE4).

This is a pure leaf: `_deny_provisional_field` is a total, deterministic
denial constructor over an already-known field name, consulting no
connection, catalog, clock, or global state. The choke points that would
decide WHEN to call it (`ApplicationRuntime`/`ApplicationDeveloper`, in
`cell.py`) remain in their own module.
"""
from __future__ import annotations

from .errors import CapabilityError


def _deny_provisional_field(field_name):
    """Contract 1.7.0 provisional gate (design docs/design/
    PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md §3 D-1 (3); work
    order docs/work-orders/WORK_ORDER_PHASE9_CONTRACT_170_V1.md §2 WP-1 (9)):
    in-process counterpart of `http.py::_deny_provisional_field`. Every
    1.7.0 capability this gate ever covered (`constraint_declarations`
    WP-3a, `dry_run` WP-3b, `idempotency` WP-3c, `request_budget` WP-3d)
    is `enabled` as of this WP -- both this function's own module-level
    caller list (`ApplicationRuntime`/`ApplicationDeveloper`'s own
    keyword-only-field gates below (in `cell.py`)) and `http.py`'s equivalent are now
    empty tuples, so this function currently has no reachable call site
    at all. Left in place (never deleted) as the standing mechanism the
    NEXT provisional capability this contract adds would reuse -- deleting
    live, documented, zero-risk dead code would satisfy no completion
    condition, only look like it did (mirrors r2db-api's own stale-
    literal precedent, `structured.py`'s own `SCHEMA_OPERATIONS`
    constant).

    Phase 9 WP-3e (design D-3 (5), V-7): `details` is now passed through
    `CapabilityError.__init__` itself -- the attribute-assignment escape
    hatch this function's own pre-WP-3e docstring described (`err.details
    = {...}` after construction) is gone; this is the isomorphic
    counterpart of `http.py::_deny_provisional_field`'s identical
    change."""
    raise CapabilityError(
        f"{field_name} is not supported by this peer",
        details={"violated_declaration": "capability", "field": field_name},
    )
