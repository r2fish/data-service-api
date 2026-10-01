"""C-27 -- same-key concurrent requests are serialized: at most one execution
per idempotency key, decided deterministically via the `hold_after_
idempotency_lookup` adapter hook (port v1.15), never via a bare
`time.sleep()` race.

design: docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md §3 D-13, especially
the "実装の形 (6d-ii) の確定" subsection (監督確定 2026-09-09), §6.2 "C-27"
row, registered in `conformance-tests/CONDITIONS.md`. Work order
`docs/work-orders/WORK_ORDER_PHASE10_DEPLOYMENT_EVIDENCE_V1.md` WP-6d-ii.
Every test here carries `@pytest.mark.condition("C-27")` via the
module-level `pytestmark`, except the two synthetic unit tests at the
bottom (the version gate's own non-vacuity guard and the hook's own
non-vacuity guard), which exercise this file's own helpers directly and
carry no condition marker of their own (mirroring `test_c06_destructive_
confirmation.py`'s own `test_contract_version_at_least_*` convention: a
plain helper unit test, not itself evidence for a registered condition).

Four observations (design D-13 "実装の形 (6d-ii) の確定" (5)), every one
driven against a fresh `isolated_application_surface()` (C-05's own V2
driver convention), with the held request ("A") and the concurrent,
waiting request ("B") issued from the TEST's own separate OS threads --
`hold_after_idempotency_lookup` itself never issues a request (the one
structural difference from `hold_in_flight`, design D-13 same subsection
(2)):

  (i)   same digest -- exactly one execution (one effect row, one audit
        event where `audit_query` answers for real); B replays A's own
        `request_id`. B is confirmed NOT to have completed while A was
        held (`_BLOCKED_PROOF_WINDOW_S`, the same shape both peers' own
        `tests/test_idempotency_concurrency.py::_assert_second_call_is_
        blocked` already uses).
  (ii)  different digest -- exactly one execution; B is refused CONFLICT
        / `violated_declaration: idempotency_key`.
  (iii) two DIFFERENT keys sent concurrently with this deployment's own
        declared `idempotency_entries` bound at E-1 committed keys --
        exactly one of A/B is refused LIMIT_EXCEEDED / `limit_class:
        idempotency_entries`; the other succeeds; the effect-row count
        matches that split.
  (iv)  A is admitted, then genuinely FAILS (a contract-defined refusal,
        never a plug-specific failure injection) -- it leaves no record,
        so B (same key, valid body) executes as a brand-new request, not
        a replay and not a CONFLICT.

Version gate (design D-13 "実装の形 (6d-ii) の確定" (6)): C-27 binds a
plug only once it declares `contract_version >= 1.8.0` AND `idempotency`
as anything other than `unavailable` -- both readings taken from the
plug's own current declaration, never from its name. A plug declaring
BELOW 1.8.0 while still advertising `idempotency` is a contract
inconsistency this suite fails loudly on (`pytest.fail`), never masks
with `skip`/`xfail` (`OPERATING_CONDITIONS.md` §1.3 の 26). Both
registered peers declare 1.8.0 with `idempotency` enabled (WP-6a/6b), so
every one of the 4 registered plugs (6 once the two socket plugs, which
inherit this hook unchanged, are counted) drives every observation below
-- `test_c27_drives_on_every_registered_plug` is this file's own
non-vacuity guard for that fact.

**Mutation scope per plug** (carried into `CONDITIONS.md`'s own C-27
row; design `docs/design/MITATEDB_APPLICATION_SERIALIZATION_V0_1.md`
section 6, the C-27 row): on `MitateDB-api-http` no cell lock exists, so
the PostgreSQL transaction-scoped advisory locks `idempotency_begin`/
`idempotency_reserve` take are the only serializer of the two concurrent
requests, also inside one process -- making the per-key lock shared
turns (i) red, and making the count lock shared turns (iii) red. On the
in-process `MitateDB-api` plug the `SQLiteBackend` holds one `RLock` for
each request scope, and removing it turns (i) red. The same advisory
locks across TWO cells sharing one PostgreSQL-backed Application are
pinned by the PEER-LOCAL `MitateDB-api/tests/test_idempotency_
concurrency.py`, a shape this common suite does not construct (a single
deployment served by exactly one process here). The `r2db-api-http` row
of the same table pins r2db's own advisory locks inside this suite.
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

pytestmark = pytest.mark.condition("C-27")

# Generous bound for the held request to actually reach the end of its own
# idempotency admission window -- matches `hold_in_flight`'s own realizations'
# `_HOLD_IN_FLIGHT_ENTRY_TIMEOUT_S` (adapter-internal plumbing across all 4
# registered plugs).
_HOLD_TIMEOUT_S = 30.0
# How long the main thread waits, WHILE the held request is deliberately
# paused, to confirm the concurrent second request has NOT completed --
# proof it is genuinely blocked on the same lock, not merely slower by luck.
# Same value and rationale as both peers' own `tests/test_idempotency_
# concurrency.py::_BLOCKED_PROOF_WINDOW_S`.
_BLOCKED_PROOF_WINDOW_S = 0.3


class _ThreadResult:
    """Collects the outcome of a port-level call issued from its own OS
    thread (design D-13 "実装の形 (6d-ii) の確定" (2): the caller, never
    the hook, issues both the held request and the concurrent one)."""

    def __init__(self) -> None:
        self.done = threading.Event()
        self.value: Any = None
        self.error: BaseException | None = None

    def join(self, timeout: float) -> Any:
        assert self.done.wait(timeout=timeout), (
            "the concurrently-issued request never completed within the wait window -- either genuinely "
            "hung, or the hold this test set up was never released"
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


def _assert_not_yet_done(result: _ThreadResult, *, adapter_name: str, what: str) -> None:
    time.sleep(_BLOCKED_PROOF_WINDOW_S)
    assert not result.done.is_set(), (
        f"{adapter_name}: {what} completed WHILE the first request was still held at the end of its own "
        "idempotency admission window -- the two concurrent same-key requests are not actually serialized"
    )


#: Memoizes `_gate`'s own result per adapter NAME for the lifetime of this
#: worker process (`conformance-tests/conftest.py:96`'s own xdist-group-by-
#: adapter-param assignment keeps every one of this file's tests for a
#: given plug on the SAME worker, so this cache is never read across a
#: process boundary). `capability_document()` on the HTTP plugs issues a
#: REAL, fresh control-plane credential every call (measured: this file's
#: own repeated per-test gate check, uncached, tripped `LIMIT_EXCEEDED` on
#: the shared adapter's own control-plane rate window within seconds) --
#: `contract_version`/`idempotency` status are session-constant
#: declarations, never a value that changes mid-run, so caching costs
#: nothing this suite's own declare-first discipline needs.
_GATE_CACHE: dict[str, str] = {}


def _gate(adapter: ConformanceAdapter) -> str:
    """C-27's own condition-executable version gate (design D-13 "実装の
    形 (6d-ii) の確定" (6)). Returns `"drive"` when this plug's OWN
    current declaration is both `contract_version >= 1.8.0` and
    `idempotency` != `unavailable`; `"not_applicable"` when either
    reading says this plug is out of scope. Both readings come from the
    live declaration -- this function never branches on `adapter.name`
    (`OPERATING_CONDITIONS.md` §1.7 の 52); `adapter.name` is used only
    as this function's own cache key and in failure messages.

    A plug declaring BELOW 1.8.0 while still advertising `idempotency`
    as anything other than `unavailable` is a genuine contract
    inconsistency (1.8.0's own conditional obligation `idempotency_
    concurrent_same_key_sends_serialized` could not even be STATED pre-
    1.8.0) -- `pytest.fail`, never `pytest.skip`/`xfail`
    (`OPERATING_CONDITIONS.md` §1.3 の 26): masking this behind a skip
    would silently accept an unverifiable claim instead of surfacing it.
    """
    cached = _GATE_CACHE.get(adapter.name)
    if cached is not None:
        return cached
    document = adapter.capability_document()
    contract_version = document["contract_version"]
    status = document.get("capabilities", {}).get("idempotency", {}).get("status", "unavailable")
    at_least_180 = contract_version_at_least(contract_version, "1.8.0")
    if not at_least_180 and status != "unavailable":
        pytest.fail(
            f"{adapter.name}: declares contract_version {contract_version!r} (below 1.8.0) while "
            f"idempotency is {status!r} -- C-27 is 1.8.0's own conditional obligation "
            "'idempotency_concurrent_same_key_sends_serialized' made executable; a plug cannot advertise "
            "idempotency without also being bound by this, so this inconsistency fails loudly rather than "
            "being masked by skip/xfail"
        )
    result = "not_applicable" if (not at_least_180 or status == "unavailable") else "drive"
    _GATE_CACHE[adapter.name] = result
    return result


_DEFAULT_AUDIT_QUERY_PAGE_LIMIT = 1000

#: Memoizes the audit_query CONTROL-plane declaration (status + declared
#: `max_limit`) per adapter name -- same rationale and lifetime as
#: `_GATE_CACHE` above. `control_capabilities()`/`control_credential()`
#: are both real control-plane round trips (the latter's own docstring:
#: "never a memoized value from an earlier call" for VALIDITY, which this
#: cache respects by re-fetching a fresh credential per USE below -- only
#: the STATUS/`max_limit` reading, a session-constant declaration, is
#: memoized here). Mirrors `test_c25_result_request_id.py`'s own
#: `_audit_query_control_state` (this file's own copy, no cross-file
#: import of test helpers, this suite's own convention).
_AUDIT_STATE_CACHE: dict[str, tuple[str, int]] = {}


def _audit_query_control_state(session_adapter: ConformanceAdapter) -> tuple[str, int]:
    cached = _AUDIT_STATE_CACHE.get(session_adapter.name)
    if cached is not None:
        return cached
    control_actor = session_adapter.control_credential()
    document = session_adapter.control_capabilities(control_actor)
    audit_query_capability = document.get("capabilities", {}).get("audit_query", {})
    status = audit_query_capability.get("status", "unavailable")
    max_limit = audit_query_capability.get("max_limit", _DEFAULT_AUDIT_QUERY_PAGE_LIMIT)
    if not isinstance(max_limit, int) or max_limit <= 0:
        max_limit = _DEFAULT_AUDIT_QUERY_PAGE_LIMIT
    result = (status, max_limit)
    _AUDIT_STATE_CACHE[session_adapter.name] = result
    return result


def _audit_query_status(session_adapter: ConformanceAdapter) -> str:
    return _audit_query_control_state(session_adapter)[0]


def _count_execution_audit_events(session_adapter: ConformanceAdapter, request_id: str) -> int:
    """Best-effort secondary evidence for observation (i) (design D-13
    "実装の形 (6d-ii) の確定" (5) row (i)): where `audit_query` answers
    for real, counts the events carrying this execution's own
    `request_id` -- reusing only reads the port already exposes (`audit_
    query`/`audit_visibility_lag_ms`), the same
    declare-first, bounded-poll shape `test_c25_result_request_id.py`'s
    own `_find_audit_event_by_request_id` establishes (this file's own
    smaller copy).

    Pages at the plug's own declared `audit_query.max_limit` (never a
    small fixed page size): under the full suite's own parallel load
    (`-n 5 --dist loadgroup`), the audit log this control actor reads is
    shared with every OTHER concurrently-running test against the same
    adapter, so it can be growing far faster than a small fixed page
    could ever catch up to -- measured directly (a fixed `limit: 200`,
    re-polled with a sleep after EVERY page including non-empty ones,
    read 0 matches within a 15s deadline under `-n 5`, while the
    identical scenario run alone always found the event within 1s).
    Only sleeps once a page comes back SHORTER than requested (caught up
    to the log's own live edge, `completeness_note`'s "keep polling ...
    until a page comes back empty/short") -- never between two pages
    that are still draining backlog, so this genuinely converges once it
    reaches the live edge instead of endlessly restarting a losing race
    against a page too small to keep up."""
    control_actor = session_adapter.control_credential()
    _status, page_limit = _audit_query_control_state(session_adapter)
    lag_s = session_adapter.audit_visibility_lag_ms() / 1000.0
    poll_interval_s = max(0.3, lag_s)
    deadline_s = time.monotonic() + lag_s + 15.0
    after: str | None = None
    matches = 0
    while True:
        request: dict[str, Any] = {"limit": page_limit}
        if after is not None:
            request["after"] = after
        try:
            events = session_adapter.audit_query(control_actor, request).get("events", [])
        except ConformanceDenial as denial:
            if denial.code == "LIMIT_EXCEEDED" and time.monotonic() < deadline_s:
                time.sleep(poll_interval_s)
                continue
            raise
        for event in events:
            if event.get("request_id") == request_id:
                matches += 1
        if events:
            after = events[-1].get("cursor")
        caught_up = len(events) < page_limit
        if matches or time.monotonic() >= deadline_s:
            return matches
        if caught_up:
            time.sleep(poll_interval_s)


def _assert_single_execution_audit_event(iso: ConformanceAdapter, request_id: str | None) -> None:
    if request_id is None:
        return
    status = _audit_query_status(iso)
    if status not in ("enabled", "partial"):
        return
    matches = _count_execution_audit_events(iso, request_id)
    assert matches == 1, (
        f"{iso.name}: expected exactly one execution audit event carrying request_id {request_id!r}, "
        f"found {matches}"
    )


def test_c27_drives_on_every_registered_plug() -> None:
    """Non-vacuity guard (完了条件 6): every registered plug's own C-27
    gate resolves to `"drive"` -- 0 excluded, 0 skipped, 0 xfailed. A
    branch that silently excludes one plug by name turns this red."""
    for name, registered_adapter in registered_adapters().items():
        gate = _gate(registered_adapter)
        assert gate == "drive", (
            f"{name}: expected C-27 to drive on every registered plug (contract_version >= 1.8.0 and "
            f"idempotency declared something other than unavailable) -- got {gate!r}"
        )


def test_c27_version_gate_fails_a_plug_declaring_below_180_with_idempotency() -> None:
    """完了条件 11: the version gate `pytest.fail`s (never skips/xfails) a
    synthetic plug declaring below 1.8.0 while advertising `idempotency`.
    A fed, duck-typed stand-in -- no real registered plug is below 1.8.0
    after WP-6a/6b, so this guard cannot otherwise be driven."""

    class _FakeAdapter:
        name = "synthetic-below-1.8.0-with-idempotency"

        def capability_document(self) -> dict[str, Any]:
            return {"contract_version": "1.7.0", "capabilities": {"idempotency": {"status": "enabled"}}}

    with pytest.raises(pytest.fail.Exception):
        _gate(_FakeAdapter())


def test_c27_hold_timeout_fails_loudly(adapter: ConformanceAdapter, isolated) -> None:
    """完了条件 7' / 12: `IdempotencyHold.wait_until_held` raises
    `AssertionError` (never hangs, never skips) when the held request
    never actually reaches the stall point -- here, simply because no
    request carrying the armed key is ever issued at all."""
    if _gate(adapter) != "drive":
        return
    iso = isolated
    developer, runtime, _app_id = provision_pair(iso, app_prefix="c27hold")
    entity = fresh_identifier("c27hold")
    iso.create_entity(developer, entity, {"label": "text"})
    key = fresh_identifier("c27holdkey")

    with iso.hold_after_idempotency_lookup(runtime, key) as hold:
        with pytest.raises(AssertionError):
            hold.wait_until_held(timeout_s=0.2)


def test_c27_same_digest_executes_once(adapter: ConformanceAdapter, isolated) -> None:
    """完了条件 1 / 4': observation (i)."""
    if _gate(adapter) != "drive":
        return
    iso = isolated
    developer, runtime, _app_id = provision_pair(iso, app_prefix="c27i")
    entity = fresh_identifier("c27i")
    iso.create_entity(developer, entity, {"label": "text"})
    key = fresh_identifier("c27ikey")
    marker = fresh_identifier("c27irow")

    def _issue() -> Mapping[str, Any]:
        return iso.attempt_batch_with_result(
            runtime, entity, [BatchOperation(operation="insert", values={"label": marker}, idempotency_key=key)],
        )

    with iso.hold_after_idempotency_lookup(runtime, key) as hold:
        a = _issue_on_thread(_issue)
        # The work order's mutation ("戻り値を定数 1 にする" -- hard-code
        # the return value to the constant 1) is unfalsifiable at exactly
        # one held request; the "measured, not echoed" property is
        # instead pinned by the no-op-hook mutation M5, which fails at
        # the timeout (supervisor ruling 2026-09-10: accepted).
        assert hold.wait_until_held(timeout_s=_HOLD_TIMEOUT_S) == 1
        b = _issue_on_thread(_issue)
        _assert_not_yet_done(b, adapter_name=adapter.name, what="the same-key/same-body resend")

    a_result = a.join(timeout=_HOLD_TIMEOUT_S)
    b_result = b.join(timeout=_HOLD_TIMEOUT_S)

    assert a_result.get("affected") == 1, f"{adapter.name}: the held request itself did not execute -- {a_result!r}"
    assert b_result.get("affected") == a_result.get("affected") and b_result.get("assigned_addresses") == a_result.get(
        "assigned_addresses"
    ), (
        f"{adapter.name}: the concurrent same-key/same-body resend did not replay the same result -- "
        f"{a_result!r} vs {b_result!r}"
    )
    assert b_result.get("request_id") == a_result.get("request_id"), (
        f"{adapter.name}: the replay must carry the ORIGINAL execution's own request_id -- "
        f"first={a_result.get('request_id')!r}, resend={b_result.get('request_id')!r}"
    )
    assert len(iso.select_eq(runtime, entity, ["label"], "label", marker)) == 1, (
        f"{adapter.name}: the concurrent same-key/same-body resend must not have executed a second insert"
    )
    _assert_single_execution_audit_event(iso, a_result.get("request_id"))


def test_c27_different_digest_conflicts(adapter: ConformanceAdapter, isolated) -> None:
    """完了条件 2 / 4': observation (ii)."""
    if _gate(adapter) != "drive":
        return
    iso = isolated
    developer, runtime, _app_id = provision_pair(iso, app_prefix="c27ii")
    entity = fresh_identifier("c27ii")
    iso.create_entity(developer, entity, {"label": "text"})
    key = fresh_identifier("c27iikey")
    marker_a = fresh_identifier("c27iirowa")
    marker_b = fresh_identifier("c27iirowb")

    def _issue_a() -> Mapping[str, Any]:
        return iso.attempt_batch_with_result(
            runtime, entity, [BatchOperation(operation="insert", values={"label": marker_a}, idempotency_key=key)],
        )

    def _issue_b() -> Mapping[str, Any]:
        return iso.attempt_batch_with_result(
            runtime, entity, [BatchOperation(operation="insert", values={"label": marker_b}, idempotency_key=key)],
        )

    with iso.hold_after_idempotency_lookup(runtime, key) as hold:
        a = _issue_on_thread(_issue_a)
        assert hold.wait_until_held(timeout_s=_HOLD_TIMEOUT_S) == 1
        b = _issue_on_thread(_issue_b)
        _assert_not_yet_done(b, adapter_name=adapter.name, what="the same-key/different-body resend")

    a_result = a.join(timeout=_HOLD_TIMEOUT_S)
    with pytest.raises(ConformanceDenial) as ei:
        b.join(timeout=_HOLD_TIMEOUT_S)
    assert ei.value.code == "CONFLICT", (
        f"{adapter.name}: same idempotency_key, different body, sent concurrently -> {ei.value.code!r}, "
        "expected CONFLICT"
    )
    assert ei.value.details.get("violated_declaration") == "idempotency_key", ei.value.details

    assert a_result.get("affected") == 1
    assert len(iso.select_eq(runtime, entity, ["label"], "label", marker_a)) == 1
    assert iso.select_eq(runtime, entity, ["label"], "label", marker_b) == [], (
        f"{adapter.name}: the CONFLICT-refused body must not have been written under a different row"
    )


def test_c27_entries_bound_holds_under_concurrency(adapter: ConformanceAdapter, isolated) -> None:
    """完了条件 3' / 4' / 7': observation (iii)."""
    if _gate(adapter) != "drive":
        return
    iso = isolated
    declared_entries = iso.capability_document().get("limits", {}).get("idempotency_entries")
    # Exercisability cap (mirrors test_c23_idempotency_semantics.py's own
    # identical `_MAX_EXERCISABLE_IDEMPOTENCY_ENTRIES` discipline): a
    # deployment declaring a large bound (production default 10000) is
    # NOT driven here -- driving it would mean thousands of committed
    # keys per run.
    _MAX_EXERCISABLE_IDEMPOTENCY_ENTRIES = 200
    if (
        not isinstance(declared_entries, int)
        or not (1 <= declared_entries <= _MAX_EXERCISABLE_IDEMPOTENCY_ENTRIES)
    ):
        # OPERATING_CONDITIONS.md item 26: skip turns "unverified" into
        # "permitted"; a condition that cannot be verified fails, never
        # skips. A plug declaring `idempotency` enabled without a real,
        # small (int) `idempotency_entries` bound in `limits` cannot have
        # this leg exercised at all, so it fails loudly rather than
        # silently passing this test.
        pytest.fail(
            f"{adapter.name}: declared limits.idempotency_entries={declared_entries!r} is not a "
            f"verifiable int in 1..{_MAX_EXERCISABLE_IDEMPOTENCY_ENTRIES} -- cannot exercise the "
            "concurrent count-bound leg"
        )
    developer, runtime, _app_id = provision_pair(iso, app_prefix="c27iii")
    entity = fresh_identifier("c27iii")
    iso.create_entity(developer, entity, {"label": "text"})
    for i in range(declared_entries - 1):
        iso.attempt_batch_with_result(
            runtime, entity,
            [
                BatchOperation(
                    operation="insert", values={"label": fresh_identifier(f"c27iiiprefillrow{i}")},
                    idempotency_key=fresh_identifier(f"c27iiiprefillkey{i}"),
                )
            ],
        )

    key_a = fresh_identifier("c27iiikeya")
    key_b = fresh_identifier("c27iiikeyb")
    marker_a = fresh_identifier("c27iiirowa")
    marker_b = fresh_identifier("c27iiirowb")

    def _issue_a() -> Mapping[str, Any]:
        return iso.attempt_batch_with_result(
            runtime, entity, [BatchOperation(operation="insert", values={"label": marker_a}, idempotency_key=key_a)],
        )

    def _issue_b() -> Mapping[str, Any]:
        return iso.attempt_batch_with_result(
            runtime, entity, [BatchOperation(operation="insert", values={"label": marker_b}, idempotency_key=key_b)],
        )

    # The hold is armed on key_a -- A is the request this test holds at
    # the end of its own admission window (design D-13 "実装の形 (6d-ii)
    # の確定" (3): the count reservation, not merely the lookup, must
    # already be taken by the time B is sent, or B would race unheld and
    # this leg would not actually exercise the count-bound lock at all).
    with iso.hold_after_idempotency_lookup(runtime, key_a) as hold:
        a = _issue_on_thread(_issue_a)
        assert hold.wait_until_held(timeout_s=_HOLD_TIMEOUT_S) == 1
        b = _issue_on_thread(_issue_b)
        _assert_not_yet_done(b, adapter_name=adapter.name, what="the concurrent, distinct-key request")

    outcomes: dict[str, Mapping[str, Any]] = {}
    errors: dict[str, ConformanceDenial] = {}
    for name, result in (("a", a), ("b", b)):
        try:
            outcomes[name] = result.join(timeout=_HOLD_TIMEOUT_S)
        except ConformanceDenial as exc:
            errors[name] = exc

    assert len(errors) == 1, (
        f"{adapter.name}: expected exactly ONE of the two concurrent, distinct-key requests to be refused "
        f"LIMIT_EXCEEDED at the declared idempotency_entries bound ({declared_entries}) -- "
        f"outcomes={outcomes!r} errors={errors!r}"
    )
    ((loser_name, loser_exc),) = errors.items()
    assert loser_exc.code == "LIMIT_EXCEEDED", (
        f"{adapter.name}: the losing concurrent request -> {loser_exc.code!r}, expected LIMIT_EXCEEDED"
    )
    assert loser_exc.details.get("limit_class") == "idempotency_entries", loser_exc.details
    winner_name = "b" if loser_name == "a" else "a"
    assert outcomes[winner_name].get("affected") == 1, (
        f"{adapter.name}: the winning concurrent request did not actually insert -- {outcomes[winner_name]!r}"
    )
    # Effect-row evidence keyed by marker, not a total `count()`:
    # `select_eq` on each request's own distinct marker names the row
    # this request produced and no other, the same convention
    # test_c23_idempotency_semantics.py already uses throughout (a total
    # count would also have to reason about every other row the
    # collection holds).
    winner_marker = marker_a if winner_name == "a" else marker_b
    loser_marker = marker_b if winner_name == "a" else marker_a
    assert len(iso.select_eq(runtime, entity, ["label"], "label", winner_marker)) == 1, (
        f"{adapter.name}: the winning concurrent request's own row is missing"
    )
    assert iso.select_eq(runtime, entity, ["label"], "label", loser_marker) == [], (
        f"{adapter.name}: the LIMIT_EXCEEDED-refused concurrent request must not have written a row"
    )


def test_c27_failed_first_attempt_lets_the_second_execute_as_new(adapter: ConformanceAdapter, isolated) -> None:
    """完了条件 4' (新規, v1.5): observation (iv)."""
    if _gate(adapter) != "drive":
        return
    iso = isolated
    developer, runtime, _app_id = provision_pair(iso, app_prefix="c27iv")
    entity = fresh_identifier("c27iv")
    iso.create_entity(developer, entity, {"label": "text"})
    key = fresh_identifier("c27ivkey")
    bad_field = fresh_identifier("c27ivnosuch")
    marker = fresh_identifier("c27ivrow")

    def _issue_failing() -> Mapping[str, Any]:
        # Admitted (the key-carrying item passes the idempotency lookup),
        # then genuinely FAILS -- a contract-defined refusal (an
        # unrecognized field alongside the keyed item, the SAME shape
        # test_c23_idempotency_semantics.py's own (v) sub-case already
        # uses), never a plug-specific failure injection (design D-13
        # "実装の形 (6d-ii) の確定" (5) 表, observation (iv)).
        return iso.attempt_batch_with_result(
            runtime, entity,
            [
                BatchOperation(operation="insert", values={"label": marker}, idempotency_key=key),
                BatchOperation(operation="insert", values={bad_field: "x"}, idempotency_key=key),
            ],
        )

    def _issue_second() -> Mapping[str, Any]:
        return iso.attempt_batch_with_result(
            runtime, entity, [BatchOperation(operation="insert", values={"label": marker}, idempotency_key=key)],
        )

    with iso.hold_after_idempotency_lookup(runtime, key) as hold:
        a = _issue_on_thread(_issue_failing)
        assert hold.wait_until_held(timeout_s=_HOLD_TIMEOUT_S) == 1
        b = _issue_on_thread(_issue_second)
        _assert_not_yet_done(b, adapter_name=adapter.name, what="the second, same-key request sent while the first was still held")

    with pytest.raises(ConformanceDenial):
        a.join(timeout=_HOLD_TIMEOUT_S)
    b_result = b.join(timeout=_HOLD_TIMEOUT_S)
    assert b_result.get("affected") == 1, (
        f"{adapter.name}: the second request, sent while the first (same key) was admitted but then FAILED, "
        f"must execute as a genuinely NEW request (not a replay, not a CONFLICT) -- {b_result!r}"
    )
    assert len(iso.select_eq(runtime, entity, ["label"], "label", marker)) == 1
