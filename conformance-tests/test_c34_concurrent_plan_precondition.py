"""C-34 -- a `plan`'s precondition stays true under a concurrent schema
operation against the same Application, decided deterministically via the
`hold_after_plan_verification` adapter hook (port v1.20), never via a bare
`time.sleep()` race.

design: docs/design/MITATEDB_APPLICATION_SERIALIZATION_V0_1.md section 9
(`conformance-tests/` paragraph) and section 11.1 (Q-5); registered in
`conformance-tests/CONDITIONS.md`. Work order
`docs/work-orders/WORK_ORDER_R102_APPLICATION_SERIALIZATION_V1.md` M-13.
Every test here carries `@pytest.mark.condition("C-34")` via the
module-level `pytestmark`.

The shape is C-27's (`test_c27_concurrent_same_key.py`): the held schema
operation ("A") and the concurrent one ("B") are both issued from the
TEST's own OS threads -- the hook itself never issues a request -- and B
is confirmed NOT to have completed while A was held
(`_BLOCKED_PROOF_WINDOW_S`, the window C-27 uses).

One observation, driven against a fresh `isolated_application_surface()`
(C-05's own V2 driver convention):

  * A is `add_field` on entity E1 carrying the `plan` a dry run of that
    same request returned at revision R, held after its plan has been
    checked against the Application's current revision and before it has
    executed any DDL.
  * B is a schema operation on a DIFFERENT entity E2 of the same
    Application, issued while A is held. Different, because the
    Application's revision, plan token and schema object count are
    Application-wide: serializing two operations on the SAME entity does
    not show that an operation on another entity cannot slip in between
    A's check and A's DDL.
  * After the hold is released, exactly one of two outcomes is accepted.
    Serialized: B had not completed while A was held, A and B both
    succeed, the revision advanced by two (R + 2) and both fields exist.
    Refused: A is refused `PRECONDITION_FAILED` naming `plan`, adds
    nothing to E1, and B's field exists (R + 1). Anything else -- in
    particular B completing while A was held and A then succeeding -- is
    a `plan` honored against a revision other than the one it was
    checked against.

Version gate: C-34 binds a plug that declares `dry_run` as anything other
than `unavailable` (`plan` exists only with `dry_run`), read from the
plug's own current declaration, never from its name.
`test_c34_drives_on_every_registered_plug` is this file's own non-vacuity
guard: on every registered plug the gate resolves to `drive` AND the
plug's hook is realized (arming it yields a handle).

Plugs that do not hold a schema operation without a `plan`: the two r2db
realizations stall where the operation has read the revision its `plan` is
checked against, which a schema operation carrying neither `plan` nor
`dry_run` never does before its DDL. This file therefore always issues A
with a `plan`.
"""
from __future__ import annotations

import threading
from typing import Any, Callable, Mapping

import pytest

from adapter import (
    ConformanceAdapter,
    ConformanceDenial,
    fresh_identifier,
)
from conftest import provision_pair

pytestmark = pytest.mark.condition("C-34")

# Generous bound for A to reach the stall point -- the same value and
# rationale as C-27's `_HOLD_TIMEOUT_S`.
_HOLD_TIMEOUT_S = 30.0
# How long the main thread waits, WHILE A is deliberately held, to see
# whether B has completed -- the same value and rationale as C-27's
# `_BLOCKED_PROOF_WINDOW_S`.
_BLOCKED_PROOF_WINDOW_S = 0.3


class _ThreadResult:
    """Collects the outcome of a port-level call issued from its own OS
    thread (the caller, never the hook, issues both A and B)."""

    def __init__(self) -> None:
        self.done = threading.Event()
        self.value: Any = None
        self.error: BaseException | None = None

    def join(self, timeout: float) -> Any:
        assert self.done.wait(timeout=timeout), (
            "the concurrently-issued schema operation never completed within the wait window -- either "
            "genuinely hung, or the hold this test set up was never released"
        )
        if self.error is not None:
            raise self.error
        return self.value


def _issue_on_thread(fn: Callable[[], Any]) -> _ThreadResult:
    result = _ThreadResult()

    def _run() -> None:
        try:
            result.value = fn()
        except BaseException as exc:  # noqa: BLE001 -- collected, never swallowed; re-raised by `.join()`.
            result.error = exc
        finally:
            result.done.set()

    threading.Thread(target=_run, daemon=True).start()
    return result


def _completed_within_window(result: _ThreadResult) -> bool:
    """True when `result`'s call finished inside `_BLOCKED_PROOF_WINDOW_S`."""
    return result.done.wait(timeout=_BLOCKED_PROOF_WINDOW_S)


#: Memoizes `_gate`'s result per adapter NAME for the lifetime of this
#: worker process -- the same rationale as C-27's `_GATE_CACHE`:
#: `capability_document()` on an HTTP plug issues a real, fresh
#: control-plane credential every call, and the `dry_run` status is a
#: session-constant declaration.
_GATE_CACHE: dict[str, str] = {}


def _gate(adapter: ConformanceAdapter) -> str:
    """`"drive"` when this plug's own current declaration has `dry_run` as
    anything other than `unavailable` (a `plan` is only ever presented with
    `dry_run`); `"not_applicable"` otherwise. Read from the live
    declaration, never from `adapter.name`, which is only the cache key."""
    cached = _GATE_CACHE.get(adapter.name)
    if cached is not None:
        return cached
    status = adapter.capability_document().get("capabilities", {}).get("dry_run", {}).get("status", "unavailable")
    result = "not_applicable" if status == "unavailable" else "drive"
    _GATE_CACHE[adapter.name] = result
    return result


def _revision(result: Mapping[str, Any]) -> int:
    revision = result.get("revision")
    assert revision is not None, f"a schema operation's result carries no 'revision' -- {result!r}"
    return int(revision)


def _fields_of(iso: ConformanceAdapter, developer: object, entity: str) -> list[str]:
    rows = {row["entity"]: row for row in iso.catalog_document(developer)["entities"]}
    return list(rows[entity]["fields"])


def test_c34_drives_on_every_registered_plug(adapter: ConformanceAdapter, isolated) -> None:
    """Non-vacuity guard: on this plug the C-34 gate resolves to `"drive"`
    (0 excluded, 0 skipped, 0 xfailed) and the plug's
    `hold_after_plan_verification` is realized -- arming it yields a
    handle whose `wait_until_held` exists. The node is collected once per
    registered plug (the `adapter` fixture's own parametrization)."""
    assert _gate(adapter) == "drive", (
        f"{adapter.name}: expected C-34 to drive on every registered plug (dry_run declared something "
        "other than unavailable)"
    )
    developer, _runtime, _app_id = provision_pair(isolated, app_prefix="c34guard")
    with isolated.hold_after_plan_verification(developer) as hold:
        assert callable(getattr(hold, "wait_until_held", None)), (
            f"{adapter.name}: hold_after_plan_verification yielded {hold!r}, which has no wait_until_held"
        )


def test_c34_hold_timeout_fails_loudly(adapter: ConformanceAdapter, isolated) -> None:
    """`PlanVerificationHold.wait_until_held` raises `AssertionError` (never
    hangs, never skips) when no schema operation ever reaches the stall
    point -- here because none is issued at all."""
    if _gate(adapter) != "drive":
        return
    iso = isolated
    developer, _runtime, _app_id = provision_pair(iso, app_prefix="c34hold")
    entity = fresh_identifier("c34hold")
    iso.create_entity(developer, entity, {"label": "text"})

    with iso.hold_after_plan_verification(developer) as hold:
        with pytest.raises(AssertionError):
            hold.wait_until_held(timeout_s=0.2)


def test_c34_concurrent_schema_operation_keeps_plan_precondition(adapter: ConformanceAdapter, isolated) -> None:
    if _gate(adapter) != "drive":
        return
    iso = isolated
    developer, _runtime, _app_id = provision_pair(iso, app_prefix="c34")
    entity_a = fresh_identifier("c34ea")
    entity_b = fresh_identifier("c34eb")
    iso.create_entity(developer, entity_a, {"label": "text"})
    iso.create_entity(developer, entity_b, {"label": "text"})
    field_a = fresh_identifier("c34fa")
    field_b = fresh_identifier("c34fb")

    dry = iso.schema_operation_with_result(
        developer, entity_a, "add_field", field=field_a, field_type="string", dry_run=True,
    )
    plan = dry.get("plan")
    assert plan, f"{adapter.name}: a dry-run add_field returned no plan -- {dry!r}"
    revision_r = _revision(dry)

    def _issue_a() -> Mapping[str, Any]:
        return iso.schema_operation_with_result(
            developer, entity_a, "add_field", field=field_a, field_type="string", plan=plan,
        )

    def _issue_b() -> Mapping[str, Any]:
        return iso.schema_operation_with_result(
            developer, entity_b, "add_field", field=field_b, field_type="string",
        )

    with iso.hold_after_plan_verification(developer) as hold:
        a = _issue_on_thread(_issue_a)
        assert hold.wait_until_held(timeout_s=_HOLD_TIMEOUT_S) == 1
        b = _issue_on_thread(_issue_b)
        b_completed_while_a_held = _completed_within_window(b)

    a_result: Mapping[str, Any] | None = None
    a_denial: ConformanceDenial | None = None
    try:
        a_result = a.join(timeout=_HOLD_TIMEOUT_S)
    except ConformanceDenial as denial:
        a_denial = denial
    b_result = b.join(timeout=_HOLD_TIMEOUT_S)

    final = _revision(
        iso.schema_operation_with_result(
            developer, entity_a, "add_field", field=fresh_identifier("c34fc"), field_type="string", dry_run=True,
        )
    )
    fields_a = _fields_of(iso, developer, entity_a)
    fields_b = _fields_of(iso, developer, entity_b)
    assert field_b in fields_b, f"{adapter.name}: B's own schema operation did not commit -- {b_result!r}"

    if a_denial is None:
        assert a_result is not None
        assert not b_completed_while_a_held, (
            f"{adapter.name}: a schema operation against another entity of the same Application completed "
            "while the first was held after its plan had been checked and before any DDL, and the first then "
            "succeeded -- its plan was honored against a revision other than the one it was checked against"
        )
        assert field_a in fields_a, f"{adapter.name}: A reported success but its field is missing -- {a_result!r}"
        assert sorted((_revision(a_result), _revision(b_result))) == [revision_r + 1, revision_r + 2], (
            f"{adapter.name}: expected the two schema operations to advance the revision from {revision_r} to "
            f"{revision_r + 2} one by one, got A={_revision(a_result)} B={_revision(b_result)}"
        )
        assert final == revision_r + 2, (
            f"{adapter.name}: the revision after both operations is {final}, expected {revision_r + 2}"
        )
    else:
        assert a_denial.code == "PRECONDITION_FAILED", (
            f"{adapter.name}: the held schema operation was refused with {a_denial.code!r}, expected success "
            "or PRECONDITION_FAILED"
        )
        assert a_denial.details.get("violated_declaration") == "plan", (
            f"{adapter.name}: PRECONDITION_FAILED does not name the plan -- {a_denial.details!r}"
        )
        assert field_a not in fields_a, (
            f"{adapter.name}: A was refused PRECONDITION_FAILED but its field was added anyway"
        )
        assert final == revision_r + 1, (
            f"{adapter.name}: A was refused and B committed, so the revision must be {revision_r + 1}, got {final}"
        )
