"""Coverage guard (WP-2.5 review M-1, docs/design/
MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md): `conformance_adapter_mitatedb.py`'s
`public_operation_callables()` is the evidence surface every independent
absence claim on this peer is checked against on the common conformance
port -- `signature_forbids_parameters` for C-03's native-command-surface
check and every `SurfaceAbsent` re-verification (C-11/C-14/C-15/C-17), and
`declared_surface >= public_surface_set` for C-11/C-14/C-15's own
re-verification that a `SurfaceAbsent` claim did not shrink its evidence
surface below the peer's real one. If that hand-written list ever misses a
real public method, every one of those checks silently inspects less than
this peer's actual public surface while still claiming full coverage --
exactly the "uncertainty silently becomes permission" failure design
principle 4 forbids, just one level removed from the checks themselves.

This was a live gap, not a hypothetical one: at the time of the WP-2.5
review, `public_operation_callables()` already omitted `ApplicationRuntime.
capabilities` (pre-existing, always public) and `ApplicationDeveloper.
create_entity`/`add_field` (added by phase 3 WP-1's P3-D1 schema-envelope
exception) -- both fixed in the same commit as this test.

This test pins the list mechanically: it introspects `ApplicationRuntime`/
`ApplicationDeveloper`'s own real, non-underscore, plain-function members
(`vars(cls)`, not `dir()`/`inspect.getmembers` -- so a method is required
exactly once, on the class that actually defines it, and a data descriptor
like `ApplicationRuntime.principal` -- a `property`, not a function, and not
itself an "operation" a caller invokes -- is correctly excluded) and
requires `public_operation_callables()` to be a superset of that real
membership. A future method added to either class without a matching
`public_operation_callables()` update fails this test immediately, rather
than silently degrading every downstream absence claim's evidence quality.
"""
from __future__ import annotations

import inspect
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "conformance"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import conformance_adapter_mitatedb as _adapter_module  # noqa: E402
from mitatedb_api.cell import ApplicationDeveloper, ApplicationRuntime  # noqa: E402


def _own_public_functions(cls: type) -> dict[str, object]:
    """`cls`'s own (not inherited) public (no leading underscore) plain
    functions -- i.e. ordinary instance methods, excluding properties and
    other non-function descriptors (`vars(cls)`, not `dir()`, so a member
    `cls` merely inherits from a base class is not double-counted here;
    the base class's own call to this helper already covers it)."""
    return {
        name: member
        for name, member in vars(cls).items()
        if not name.startswith("_") and inspect.isfunction(member)
    }


def test_public_operation_callables_covers_every_application_runtime_and_developer_method() -> None:
    expected_by_class = {
        ApplicationRuntime: _own_public_functions(ApplicationRuntime),
        ApplicationDeveloper: _own_public_functions(ApplicationDeveloper),
    }

    # Vacuity guard (design principle 4, "skip is fail" applied to a static
    # introspection too): if this ever finds zero real public methods on
    # either class, either the introspection itself is broken (a class
    # rename, a switch away from plain functions to some other descriptor
    # kind) or the classes were emptied out, either of which this test must
    # notice rather than vacuously pass.
    for cls, members in expected_by_class.items():
        assert members, (
            f"introspection found zero own public plain-function members on {cls.__qualname__} -- "
            "scanner assumption or class structure changed"
        )

    expected = set(expected_by_class[ApplicationRuntime].values()) | set(
        expected_by_class[ApplicationDeveloper].values()
    )

    adapter = _adapter_module.build_adapter()
    try:
        declared = set(adapter.public_operation_callables())
    finally:
        adapter.close()

    missing = expected - declared
    assert not missing, (
        "public_operation_callables() is missing real public method(s): "
        f"{sorted(fn.__qualname__ for fn in missing)} -- every downstream absence/native-surface check "
        "(C-03/C-11/C-14/C-15/C-17) relies on this list being a complete evidence surface"
    )
