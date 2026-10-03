"""C-36 -- a request whose `execution_ms` budget is already spent when it
reaches the point where its next statement would be issued ends
deterministically: it issues no statement, answers `LIMIT_EXCEEDED` with
`details.limit_class: execution_ms`, and leaves no row, no schema change
and no idempotency record. Decided by three adapter holds, never by a bare
`time.sleep()` race against the clock.

design: docs/design/EXPIRED_REQUEST_SEMANTICS_V0_1.md D-2, D-7 and
sections 6.2-6.4, registered in `conformance-tests/CONDITIONS.md`; the
contract text it checks is `limits.execution_ms` and the
`versioning.obligations` entry that goes with it (contract 1.16.0).
Work order `docs/work-orders/WORK_ORDER_R42_EXPIRED_REQUEST_SEMANTICS_V1.md`.
Every test here carries `@pytest.mark.condition("C-36")` via the
module-level `pytestmark`.

Three vectors, each driven against a fresh `isolated_application_surface()`
(C-05's own V2 driver convention), each paired with a positive control (the
same hold under a budget that is not spent: the request completes and its
effect stays -- `docs/design/CONFORMANCE_ADAPTER_V1.md` section 2's rule
that a negative test comes with a positive control). The held request is
issued from the TEST's own OS thread; no primitive here issues a request of
its own.

  (i)   After the request's bounds are fixed and before its first
        connection (`hold_after_admission`, port v1.22). Held for 100 ms
        under `budget.execution_ms = 1`, the mutation is refused once
        released, and -- where the plug can count -- issued no statement
        after the release. The positive control holds a request carrying
        the deployment's own declared `execution_ms` for the same 100 ms:
        it completes, its row stays, and on the PostgreSQL plugs it issued
        at least one statement after the release (so the count is not a
        constant 0).
  (ii)  Between two statements of a multi-statement request
        (`hold_after_idempotency_lookup`). A mutation carrying an
        idempotency key and `budget.execution_ms = B` is held at the end of
        its admission window, for B + B / 5 counted from the moment it
        signals it is held, then released: it is refused, leaves no row,
        issued no statement after the release, and the same key resent
        WITHOUT the budget (a different digest) is a new execution, not a
        `CONFLICT` -- no record was left.
  (iii) Before the first DDL statement of a schema operation
        (`hold_after_plan_verification`). A schema operation presenting a
        `plan` that a dry run of the same request, under the same budget,
        returned BEFORE the hold was armed, held the same way, is refused,
        issued no statement after the release, and moves no revision.

A request that is refused BEFORE it reaches the stall point (a budget too
small to get there) is not a pass: every wait below is for "held" OR "the
request completed", and the request completing first fails the test at
once, without waiting out `wait_until_held`'s 30 s. B is `_B_MS`; the hold
after the signal is B + B / 5 (design D-7).

What each vector can and cannot show. The refusal after the release is
monotonic in load -- a request released later than its budget finds it spent
whatever the machine is doing -- so those assertions do not flake. The
vectors do not show that the stall point is reached, or that the dry run
and the resend succeed, under any load: those depend on B being long
enough, and a miss fails the test loudly instead of passing it. On the two
in-process plugs `statements_after_release()` is `None` (no PostgreSQL
statement to count) and the test reads the error code and the effect only.

Version gate (design D-7): C-36 binds a plug once it declares
`contract_version >= 1.16.0`, read from the plug's own live declaration,
never from its name. `_binds_contract_version` is that predicate;
`test_c36_version_gate_binds_1_16_0_and_not_1_15_0` pins it against
synthetic declarations (a 1.15.0 declaration is not bound), and
`test_c36_drives_on_every_registered_plug` is this file's own non-vacuity
guard: every registered plug (six) is bound, so no plug is silently left
out. `test_c36_guard_names_a_plug_the_gate_does_not_bind` pins the guard's
own judgment against a synthetic registry.

Not gated by the version: the three `test_c36_statement_count_is_wired_on_*`
tests and `test_c36_admission_hold_fails_loudly_and_passes_other_requests_
through`. They check the port v1.22 primitives themselves (that each of the
three holds reaches its stall point, that the count its handle returns is
not a constant 0, that a catalog read passes through an armed admission
hold), which hold on a plug whatever contract version it declares.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable, Mapping

import pytest

from adapter import (
    BatchOperation,
    ConformanceAdapter,
    ConformanceDenial,
    contract_version_at_least,
    fresh_identifier,
)
from conftest import provision_pair, registered_adapters

pytestmark = pytest.mark.condition("C-36")

#: The contract version from which a plug carries `limits.execution_ms`'s
#: statement of what a spent budget does.
_MINIMUM_CONTRACT_VERSION = "1.16.0"
#: The number of plugs this suite registers (two in-process, two http, two
#: socket); the guard asserts all of them are bound.
_REGISTERED_PLUG_COUNT = 6
#: Generous bound for the held request to reach its stall point, and for a
#: released request to finish -- the same value and rationale as C-27's
#: `_HOLD_TIMEOUT_S`.
_HOLD_TIMEOUT_S = 30.0
#: One poll of "held, or has the request completed" while waiting for the
#: stall point.
_POLL_S = 0.05
#: How long the (i) request is held before the release (design D-7: 100 ms).
_ADMISSION_HOLD_S = 0.1
#: The budget B of vectors (ii) and (iii), in ms: long enough that the
#: request reaches its stall point under a loaded machine (design D-7), and
#: the hold after the stall signal, B + B / 5. The longest time measured from
#: issuing a request to its stall point was 239.4 ms under a load average of 11
#: to 26 and 84.5 ms under a load like the completion gate's (`CONDITIONS.md`,
#: C-36 Status).
_B_MS = 500
_HOLD_AFTER_SIGNAL_S = (_B_MS + _B_MS // 5) / 1000.0


def _binds_contract_version(contract_version: str) -> bool:
    """C-36's own version gate: `True` iff a declaration of `contract_version`
    is bound by this condition."""
    return contract_version_at_least(contract_version, _MINIMUM_CONTRACT_VERSION)


#: Memoizes each plug's declared `contract_version` per adapter NAME for the
#: lifetime of this worker process -- the same rationale as C-27's
#: `_GATE_CACHE`: `capability_document()` on an HTTP plug issues a real,
#: fresh control-plane credential every call, and `contract_version` is a
#: session-constant declaration.
_VERSION_CACHE: dict[str, str] = {}


def _declared_version(adapter: ConformanceAdapter) -> str:
    cached = _VERSION_CACHE.get(adapter.name)
    if cached is None:
        cached = adapter.capability_document()["contract_version"]
        _VERSION_CACHE[adapter.name] = cached
    return cached


def _gate(adapter: ConformanceAdapter) -> str:
    """`"drive"` when this plug's own current declaration is bound by C-36,
    `"not_applicable"` otherwise. Read from the live declaration, never from
    `adapter.name`, which is only the cache key."""
    return "drive" if _binds_contract_version(_declared_version(adapter)) else "not_applicable"


def _unbound_plugs(declared_versions: Mapping[str, str]) -> list[str]:
    """The names, among `declared_versions` (plug name -> declared
    `contract_version`), of the plugs the gate does not bind."""
    return sorted(name for name, version in declared_versions.items() if not _binds_contract_version(version))


def test_c36_version_gate_binds_1_16_0_and_not_1_15_0() -> None:
    """The gate's predicate against synthetic declarations: 1.16.0 and later
    are bound, 1.15.0 -- the version before the statement of what a spent
    budget does -- is not, and neither is any earlier one. A gate that bound
    everything would silently drive C-36 against a plug that never promised
    it."""
    assert _binds_contract_version("1.16.0") is True
    assert _binds_contract_version("1.17.0") is True
    assert _binds_contract_version("2.0.0") is True
    assert _binds_contract_version("1.15.0") is False, "a 1.15.0 declaration must not be bound by C-36"
    assert _binds_contract_version("1.9.0") is False


def test_c36_guard_names_a_plug_the_gate_does_not_bind() -> None:
    """The guard's own judgment against a synthetic registry: a plug whose
    declaration the gate does not bind is named, and a registry of bound
    plugs names none. A guard that always found nothing would never fail."""
    assert _unbound_plugs({"old": "1.15.0", "new": "1.16.0"}) == ["old"]
    assert _unbound_plugs({"a": "1.16.0", "b": "1.17.0"}) == []


def test_c36_drives_on_every_registered_plug() -> None:
    """Non-vacuity guard: every registered plug's own declaration is bound
    by C-36 -- 0 excluded, 0 skipped, 0 xfailed -- and the registry holds
    the six plugs this suite expects, so an empty or shrunken registry
    cannot pass either. The set of plugs the gate is asked about is the
    registry itself, so a guard that looks at an empty set turns red too. A
    branch that silently excludes one plug turns this red."""
    registered = registered_adapters()
    assert len(registered) == _REGISTERED_PLUG_COUNT, (
        f"expected {_REGISTERED_PLUG_COUNT} registered plugs, found {len(registered)}: {sorted(registered)}"
    )
    declared = {name: _declared_version(adapter) for name, adapter in registered.items()}
    assert sorted(declared) == sorted(registered), (
        f"the set of plugs the gate was asked about {sorted(declared)} is not the registry {sorted(registered)}"
    )
    unbound = _unbound_plugs(declared)
    assert not unbound, (
        f"C-36 is bound from contract_version {_MINIMUM_CONTRACT_VERSION}; these plugs declare less and would be "
        f"left out: { {name: declared[name] for name in unbound} }"
    )


class _ThreadResult:
    """Collects the outcome of a port-level call issued from its own OS
    thread (the caller, never a hold, issues the held request)."""

    def __init__(self) -> None:
        self.done = threading.Event()
        self.value: Any = None
        self.error: BaseException | None = None

    def join(self, timeout: float) -> Any:
        assert self.done.wait(timeout=timeout), (
            "the held request never completed within the wait window -- either genuinely hung, or the hold "
            "this test set up was never released"
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


def _outcome(result: _ThreadResult) -> Any:
    """The held request's own result once it has completed: its return
    value, or the `ConformanceDenial` it was refused with. Any other
    exception is a failure of the plug, not an outcome, and propagates."""
    try:
        return result.join(timeout=_HOLD_TIMEOUT_S)
    except ConformanceDenial as denial:
        return denial


def _describe(outcome: Any) -> str:
    if isinstance(outcome, ConformanceDenial):
        return f"refused {outcome.code!r} {outcome.details!r}"
    return f"returned {outcome!r}"


def _await_stall(hold: Any, result: _ThreadResult, *, adapter_name: str, what: str) -> None:
    """Waits for `what` to reach the stall point of `hold`, or for the
    request to complete -- whichever comes first. The request completing
    first (refused or not) fails at once: it was decided before the stall
    point, so nothing below observes what this vector is about
    (`OPERATING_CONDITIONS.md` §1.5 の 32). Never waits out `wait_until_held`'s
    own 30 s."""
    deadline = time.monotonic() + _HOLD_TIMEOUT_S
    while True:
        if result.done.is_set():
            raise AssertionError(
                f"{adapter_name}: {what} completed before it reached the stall point -- "
                f"{_describe(_outcome(result))}; the vector observes nothing"
            )
        try:
            hold.wait_until_held(timeout_s=_POLL_S)
            return
        except AssertionError:
            if time.monotonic() >= deadline:
                raise


def _hold_for(seconds: float) -> None:
    """Waits `seconds` on the monotonic clock."""
    start = time.monotonic()
    while time.monotonic() - start < seconds:
        time.sleep(0.01)


def _declared_execution_ms(iso: ConformanceAdapter) -> int:
    """This deployment's own declared `limits.execution_ms`, read from its
    capability document, never a fixed literal (C-24's lesson: a narrow
    isolation profile's bound must not fall below a hardcoded test value)."""
    declared = iso.capability_document().get("limits", {}).get("execution_ms")
    assert isinstance(declared, int), f"{iso.name}: capability_document()['limits']['execution_ms'] is not an int -- {declared!r}"
    return declared


def _assert_statement_count(adapter: ConformanceAdapter, statements: int | None, *, refused: bool) -> None:
    """`statements` is what `statements_after_release()` returned. On a plug
    that runs against PostgreSQL it is an integer: 0 after a refusal, and at
    least 1 after a request that completed (so a count that is a constant 0
    fails the positive control). On the in-process plugs it is `None` and the
    caller decides from the code and the effect alone."""
    if adapter.transport_kind == "in_process":
        assert statements is None, (
            f"{adapter.name}: an in-process plug has no PostgreSQL statement to count and must report None, "
            f"not {statements!r}"
        )
        return
    assert statements is not None, f"{adapter.name}: a PostgreSQL plug must report a statement count, got None"
    if refused:
        assert statements == 0, (
            f"{adapter.name}: the refused request issued {statements} statement(s) after it was released; a request "
            "whose budget is spent must issue none"
        )
    else:
        assert statements >= 1, (
            f"{adapter.name}: the request that completed issued {statements} statement(s) after it was released; "
            "expected at least one (a count that stays 0 observes nothing)"
        )


def _assert_refused_for_execution_ms(adapter: ConformanceAdapter, outcome: Any) -> None:
    assert isinstance(outcome, ConformanceDenial), (
        f"{adapter.name}: the request released after its budget was spent was not refused -- {_describe(outcome)}"
    )
    assert outcome.code == "LIMIT_EXCEEDED", f"{adapter.name}: expected LIMIT_EXCEEDED, got {_describe(outcome)}"
    assert outcome.details.get("limit_class") == "execution_ms", (
        f"{adapter.name}: LIMIT_EXCEEDED does not name execution_ms -- {outcome.details!r}"
    )


def _assert_completed(adapter: ConformanceAdapter, outcome: Any) -> None:
    assert not isinstance(outcome, ConformanceDenial), (
        f"{adapter.name}: the positive control (the same hold under a budget that is not spent) was refused -- "
        f"{_describe(outcome)}"
    )


def _rows(iso: ConformanceAdapter, runtime: object, entity: str, marker: str) -> int:
    return len(iso.select_eq(runtime, entity, ["label"], "label", marker))


def _revision(result: Mapping[str, Any]) -> int:
    revision = result.get("revision")
    assert revision is not None, f"a schema operation's result carries no 'revision' -- {result!r}"
    return int(revision)


def _fields_of(iso: ConformanceAdapter, developer: object, entity: str) -> list[str]:
    rows = {row["entity"]: row for row in iso.catalog_document(developer)["entities"]}
    return list(rows[entity]["fields"])


def test_c36_statement_count_is_wired_on_the_admission_hold(adapter: ConformanceAdapter, isolated) -> None:
    """The statement count of `hold_after_admission`, independent of the
    contract version (it is a port v1.22 fact, not a statement of the
    contract): a mutation with no budget, held and released at once,
    completes and on the PostgreSQL plugs issued at least one statement
    after the release; on the in-process plugs the count is `None`. A handle
    whose count is a constant 0 fails here."""
    outcome, statements, rows = _vector_i(adapter, isolated, budget_ms=None, hold_s=0.0)
    _assert_completed(adapter, outcome)
    _assert_statement_count(adapter, statements, refused=False)
    assert rows == 1, f"{adapter.name}: the completed mutation left {rows} row(s), expected 1"


def test_c36_statement_count_is_wired_on_the_idempotency_hold(adapter: ConformanceAdapter, isolated) -> None:
    """The same wiring check for `hold_after_idempotency_lookup`'s handle: a
    keyed mutation with no budget, held at the end of its admission window
    and released at once, completes and (PostgreSQL plugs) issued at least
    one statement after the release."""
    outcome, statements, rows, _resend, _rows_now = _vector_ii(adapter, isolated, budget_ms=None, hold_s=0.0)
    _assert_completed(adapter, outcome)
    _assert_statement_count(adapter, statements, refused=False)
    assert rows == 1, f"{adapter.name}: the completed mutation left {rows} row(s), expected 1"


def test_c36_statement_count_is_wired_on_the_plan_verification_hold(adapter: ConformanceAdapter, isolated) -> None:
    """The same wiring check for `hold_after_plan_verification`'s handle: a
    plan-bearing schema operation with no budget, held before its first DDL
    statement and released at once, completes and (PostgreSQL plugs) issued
    at least one statement after the release."""
    outcome, statements, revision_before, _revision_after, field_present = _vector_iii(
        adapter, isolated, budget_ms=None, hold_s=0.0,
    )
    _assert_completed(adapter, outcome)
    _assert_statement_count(adapter, statements, refused=False)
    assert field_present, f"{adapter.name}: the completed schema operation did not add its field"


def test_c36_admission_hold_fails_loudly_and_passes_other_requests_through(adapter: ConformanceAdapter, isolated) -> None:
    """`AdmissionHold.wait_until_held` raises `AssertionError` (never hangs,
    never skips) when no request ever reaches the stall point, and a request
    that is none of a query, a mutation or a schema operation -- a catalog
    read -- passes through the armed hold instead of being held. The catalog
    read is issued on its own thread and waited for with the same timeout as
    every other vector, so a plug that holds it fails the test instead of
    hanging it."""
    iso = isolated
    developer, runtime, _app_id = provision_pair(iso, app_prefix="c36hold")
    entity = fresh_identifier("c36hold")
    iso.create_entity(developer, entity, {"label": "text"})

    with iso.hold_after_admission(runtime) as hold:
        catalog = _issue_on_thread(lambda: iso.catalog_document(developer)).join(timeout=_HOLD_TIMEOUT_S)
        assert entity in {row["entity"] for row in catalog["entities"]}, (
            f"{adapter.name}: a catalog read did not complete while the admission hold was armed"
        )
        with pytest.raises(AssertionError):
            hold.wait_until_held(timeout_s=0.2)


def _budget_of(budget_ms: int | None) -> Mapping[str, int] | None:
    return None if budget_ms is None else {"execution_ms": budget_ms}


def _vector_i(
    adapter: ConformanceAdapter, iso: ConformanceAdapter, *, budget_ms: int | None, hold_s: float = _ADMISSION_HOLD_S,
) -> tuple[Any, int | None, int]:
    developer, runtime, _app_id = provision_pair(iso, app_prefix="c36i")
    entity = fresh_identifier("c36i")
    iso.create_entity(developer, entity, {"label": "text"})
    marker = fresh_identifier("c36irow")

    def _issue() -> Mapping[str, Any]:
        return iso.attempt_batch_with_result(
            runtime, entity, [BatchOperation(operation="insert", values={"label": marker})],
            budget=_budget_of(budget_ms),
        )

    with iso.hold_after_admission(runtime) as hold:
        a = _issue_on_thread(_issue)
        _await_stall(hold, a, adapter_name=adapter.name, what="the mutation")
        _hold_for(hold_s)
    outcome = _outcome(a)
    return outcome, hold.statements_after_release(), _rows(iso, runtime, entity, marker)


def test_c36_i_budget_spent_before_the_first_connection_issues_no_statement(adapter: ConformanceAdapter, isolated) -> None:
    """(i): `budget.execution_ms = 1`, held 100 ms after the bounds are fixed
    and before the first connection, then released -> `LIMIT_EXCEEDED` /
    `execution_ms`, no row, and on the PostgreSQL plugs no statement after
    the release."""
    if _gate(adapter) != "drive":
        return
    outcome, statements, rows = _vector_i(adapter, isolated, budget_ms=1)
    _assert_refused_for_execution_ms(adapter, outcome)
    _assert_statement_count(adapter, statements, refused=True)
    assert rows == 0, f"{adapter.name}: the refused mutation left {rows} row(s)"


def test_c36_i_positive_control_same_hold_under_a_budget_that_is_not_spent(adapter: ConformanceAdapter, isolated) -> None:
    """(i) positive control: the same 100 ms hold under the deployment's own
    declared `execution_ms` -> the mutation completes, its row stays, and on
    the PostgreSQL plugs it issued at least one statement after the
    release."""
    if _gate(adapter) != "drive":
        return
    outcome, statements, rows = _vector_i(adapter, isolated, budget_ms=_declared_execution_ms(isolated))
    _assert_completed(adapter, outcome)
    assert outcome.get("affected") == 1, f"{adapter.name}: expected one affected row, got {outcome!r}"
    _assert_statement_count(adapter, statements, refused=False)
    assert rows == 1, f"{adapter.name}: the completed mutation left {rows} row(s), expected 1"


def _vector_ii(
    adapter: ConformanceAdapter, iso: ConformanceAdapter, *, budget_ms: int | None, hold_s: float,
) -> tuple[Any, int | None, int, Callable[[], Mapping[str, Any]], Callable[[], int]]:
    developer, runtime, _app_id = provision_pair(iso, app_prefix="c36ii")
    entity = fresh_identifier("c36ii")
    iso.create_entity(developer, entity, {"label": "text"})
    key = fresh_identifier("c36iikey")
    marker = fresh_identifier("c36iirow")

    def _operations() -> list[BatchOperation]:
        return [BatchOperation(operation="insert", values={"label": marker}, idempotency_key=key)]

    def _issue() -> Mapping[str, Any]:
        return iso.attempt_batch_with_result(runtime, entity, _operations(), budget=_budget_of(budget_ms))

    def _resend_without_budget() -> Mapping[str, Any]:
        return iso.attempt_batch_with_result(runtime, entity, _operations())

    with iso.hold_after_idempotency_lookup(runtime, key) as hold:
        a = _issue_on_thread(_issue)
        _await_stall(hold, a, adapter_name=adapter.name, what="the keyed mutation")
        _hold_for(hold_s)
    outcome = _outcome(a)
    return (
        outcome, hold.statements_after_release(), _rows(iso, runtime, entity, marker),
        _resend_without_budget, lambda: _rows(iso, runtime, entity, marker),
    )


def test_c36_ii_budget_spent_between_statements_leaves_nothing(adapter: ConformanceAdapter, isolated) -> None:
    """(ii): a keyed mutation under `budget.execution_ms = B`, held at the end
    of its idempotency admission window for B + B / 5 from its signal, then
    released -> `LIMIT_EXCEEDED` / `execution_ms`, no row, no statement after
    the release, and the same key resent WITHOUT the budget is a new
    execution (a record left behind would answer `CONFLICT`, the digest
    having changed)."""
    if _gate(adapter) != "drive":
        return
    outcome, statements, rows, resend, rows_now = _vector_ii(adapter, isolated, budget_ms=_B_MS, hold_s=_HOLD_AFTER_SIGNAL_S)
    _assert_refused_for_execution_ms(adapter, outcome)
    _assert_statement_count(adapter, statements, refused=True)
    assert rows == 0, f"{adapter.name}: the refused mutation left {rows} row(s)"
    try:
        resent = resend()
    except ConformanceDenial as denial:
        raise AssertionError(
            f"{adapter.name}: the same key resent without the budget was refused {denial.code!r} "
            f"{denial.details!r}; a request refused for execution_ms must leave no idempotency record"
        ) from denial
    assert resent.get("affected") == 1, f"{adapter.name}: the resend did not execute as a new request -- {resent!r}"
    assert rows_now() == 1, f"{adapter.name}: the resend left {rows_now()} row(s), expected 1"


def test_c36_ii_positive_control_same_hold_under_a_budget_that_is_not_spent(adapter: ConformanceAdapter, isolated) -> None:
    """(ii) positive control: the same keyed mutation and the same hold
    (B + B / 5 from the signal) under the deployment's own declared
    `execution_ms` -> it completes, its row stays, and on the PostgreSQL
    plugs it issued at least one statement after the release."""
    if _gate(adapter) != "drive":
        return
    outcome, statements, rows, _resend, _rows_now = _vector_ii(
        adapter, isolated, budget_ms=_declared_execution_ms(isolated), hold_s=_HOLD_AFTER_SIGNAL_S,
    )
    _assert_completed(adapter, outcome)
    assert outcome.get("affected") == 1, f"{adapter.name}: expected one affected row, got {outcome!r}"
    _assert_statement_count(adapter, statements, refused=False)
    assert rows == 1, f"{adapter.name}: the completed mutation left {rows} row(s), expected 1"


def _vector_iii(
    adapter: ConformanceAdapter, iso: ConformanceAdapter, *, budget_ms: int | None, hold_s: float,
) -> tuple[Any, int | None, int, int, bool]:
    developer, _runtime, _app_id = provision_pair(iso, app_prefix="c36iii")
    entity = fresh_identifier("c36iii")
    iso.create_entity(developer, entity, {"label": "text"})
    field = fresh_identifier("c36iiif")
    budget = _budget_of(budget_ms)
    # The plan comes from a dry run of the same request under the same budget
    # (a plan commits to the request including its budget), and is taken
    # BEFORE the hold is armed.
    dry = iso.schema_operation_with_result(
        developer, entity, "add_field", field=field, field_type="string", dry_run=True, budget=budget,
    )
    plan = dry.get("plan")
    assert plan, f"{adapter.name}: a dry-run add_field under budget {budget!r} returned no plan -- {dry!r}"
    revision_before = _revision(dry)

    def _issue() -> Mapping[str, Any]:
        return iso.schema_operation_with_result(
            developer, entity, "add_field", field=field, field_type="string", plan=plan, budget=budget,
        )

    with iso.hold_after_plan_verification(developer) as hold:
        a = _issue_on_thread(_issue)
        _await_stall(hold, a, adapter_name=adapter.name, what="the schema operation")
        _hold_for(hold_s)
    outcome = _outcome(a)
    statements = hold.statements_after_release()
    probe = iso.schema_operation_with_result(
        developer, entity, "add_field", field=fresh_identifier("c36iiig"), field_type="string", dry_run=True,
    )
    revision_after = _revision(probe)
    field_present = field in _fields_of(iso, developer, entity)
    return outcome, statements, revision_before, revision_after, field_present


def test_c36_iii_budget_spent_before_the_first_ddl_moves_no_revision(adapter: ConformanceAdapter, isolated) -> None:
    """(iii): a schema operation presenting a `plan` from a dry run under the
    same `budget.execution_ms = B`, held after its plan check and before its
    first DDL statement for B + B / 5 from its signal, then released ->
    `LIMIT_EXCEEDED` / `execution_ms`, no statement after the release, no
    field added, and the Application's revision does not move."""
    if _gate(adapter) != "drive":
        return
    outcome, statements, revision_before, revision_after, field_present = _vector_iii(
        adapter, isolated, budget_ms=_B_MS, hold_s=_HOLD_AFTER_SIGNAL_S,
    )
    _assert_refused_for_execution_ms(adapter, outcome)
    _assert_statement_count(adapter, statements, refused=True)
    assert not field_present, f"{adapter.name}: the refused schema operation added its field anyway"
    assert revision_after == revision_before, (
        f"{adapter.name}: the refused schema operation moved the revision from {revision_before} to {revision_after}"
    )


def test_c36_iii_positive_control_same_hold_under_a_budget_that_is_not_spent(adapter: ConformanceAdapter, isolated) -> None:
    """(iii) positive control: the same plan-bearing schema operation and the
    same hold under the deployment's own declared `execution_ms` (the plan
    taken again under that budget by its own dry run) -> it completes, its
    field is added, the revision moves by one, and on the PostgreSQL plugs it
    issued at least one statement after the release."""
    if _gate(adapter) != "drive":
        return
    outcome, statements, revision_before, revision_after, field_present = _vector_iii(
        adapter, isolated, budget_ms=_declared_execution_ms(isolated), hold_s=_HOLD_AFTER_SIGNAL_S,
    )
    _assert_completed(adapter, outcome)
    _assert_statement_count(adapter, statements, refused=False)
    assert field_present, f"{adapter.name}: the completed schema operation did not add its field"
    assert _revision(outcome) == revision_before + 1, (
        f"{adapter.name}: expected the completed schema operation to commit revision {revision_before + 1}, "
        f"got {_revision(outcome)}"
    )
    assert revision_after == revision_before + 1, (
        f"{adapter.name}: the revision after the completed schema operation is {revision_after}, "
        f"expected {revision_before + 1}"
    )
