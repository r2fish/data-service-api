"""Phase 8 WP-1a peer-local tests (design docs/design/
PHASE8_EFFECTIVE_BOUNDS_AND_HYGIENE_V1.md D-1, work order §2 WP-1a):
MitateDB application-plane limit enforcement for the 4 previously-
`unavailable` classes -- `requests_per_minute` / `concurrency` /
`execution_ms` / `operation_depth` -- plus the `request_bytes` in-process
副項目.

Complements the common conformance suite's own `test_c05_limit_
declaration_agreement.py` (declared-vs-driven position agreement, driven
against ALL 4 plugs through the common port): that file proves the
DECLARED bound and the REAL refusal position agree, per class,
independently of this peer's own internal mechanics. This file fixes the
mechanics THAT file cannot see -- the gate's real ORDER (rpm ->
concurrency -> request_bytes -> operation_depth -> deadline), the
limit-state holder's PROCESS-WIDE scope (never per-application, never
per-request), the `finally`-guaranteed concurrency release under
genuine concurrent load, the PostgreSQL `execution_ms` real timeout
mapping, and the `request_bytes` two-layer (HTTP middleware + in-process
structural estimate) response identity.

Naming (work order §0.0 (6)): this file is limit-系, kept distinct from
WP-4's ops-系 test files in this same directory (both add files under
`MitateDB-api/tests/`, and must not write into the same file).

Non-vacuity (常設規律 1): every new test here asserts a genuine, directly
observed fact (a real in-flight count, a real denial's `limit_class`,
a real identical response shape) -- never a bare pass-through.
"""
from __future__ import annotations

import json
import threading
import time
import types

import psycopg
import pytest

from mitatedb_api.auth import Principal, Role
from mitatedb_api.backend_postgres import PostgresBackend
from mitatedb_api.cell import ApplicationCell, Filter, _LimitStateHolder, _measure_request_bytes
from mitatedb_api.config import FoundationConfig
from mitatedb_api.credential_store_postgres import PostgresCredentialStore
from mitatedb_api.errors import ResourceLimitError, ValidationError
from mitatedb_api.http import HttpService, create_app
from mitatedb_api.service import MitateDataService, ProvisioningFacade

# Relative imports (not bare `from test_http import ...` / `from
# test_postgres import ...`): `test_http.py`'s own module docstring
# explains why a bare import risks resolving to r2db-api's own
# same-named module under the combined root suite -- this file reuses
# that same established convention, not a new one.
from .test_http import _create_entity, _post  # noqa: F401
from .test_postgres import app_a, close_cell, make_cell, platform  # noqa: F401


def _principal(app_id="app1", credential_id="cred1", role=Role.RUNTIME):
    return Principal(application_id=app_id, credential_id=credential_id, role=role)


# ---------------------------------------------------------------------------
# order: requests_per_minute -> concurrency -> request_bytes ->
# operation_depth (design D-1 "順序", work order 完了条件 7 / 変異 7)
# ---------------------------------------------------------------------------


def test_gate_denies_requests_per_minute_before_request_bytes():
    """A request that is BOTH rate-exhausted AND byte-oversized is denied
    `requests_per_minute`, never `request_bytes` -- proving the rate
    window is checked before the structural byte estimate (design D-1's
    own real order, mirroring r2db `service.py::_slot`'s `_acquire_rate`
    before `check_request`). Mutation 7 (design table): swap the gate's
    own byte-check-before-rate-check and this goes red (the denial flips
    to `request_bytes`)."""
    config = FoundationConfig(max_requests_per_minute=1, max_concurrency=10, max_request_bytes=150, max_operation_depth=10)
    cell = ApplicationCell("app1", config)
    dev = _principal(credential_id="dev1", role=Role.DEVELOPER)
    runtime = _principal(credential_id="rt1", role=Role.RUNTIME)
    cell.create_collection(dev, "t", {"a": "text"})
    # Consumes the sole requests_per_minute unit on `runtime`'s own
    # window with an ordinary, in-bound insert.
    cell.insert(runtime, "t", {"a": "y"})
    # The rate window is now exhausted; this payload is ALSO structurally
    # far over max_request_bytes=150 (a 1000-char string estimates to
    # 1000*4=4000 bytes). If request_bytes were checked first, this would
    # be denied `request_bytes` instead.
    huge_value = "x" * 1000
    with pytest.raises(ResourceLimitError) as excinfo:
        cell.insert(runtime, "t", {"a": huge_value})
    assert excinfo.value.details == {"limit_class": "requests_per_minute"}


def test_gate_denies_requests_per_minute_before_concurrency():
    """Phase 8 WP-1a rework 1 (裁定 4, 監督裁定 2026-09-06): a request that
    is BOTH rate-exhausted (THIS credential's own window) AND
    concurrency-exhausted (the process-wide in-flight slot, held for real
    by a genuinely DIFFERENT credential) is denied `requests_per_minute`,
    never `concurrency` -- proving the rate window is checked before the
    concurrency slot (design D-1's own real order, r2db `service.py::
    _slot`'s `_acquire_rate` call, `:1156-1163`, preceding its own
    concurrency-counter acquisition, `:1133-1144`).

    Pre-rework, this specific pair of classes had no peer-local test at
    all -- the code review that sent this WP back found that swapping
    `_limit_gate`'s own `acquire_rate`/`concurrency_slot` call order left
    `MitateDB-api/tests` and `test_c05_limit_declaration_agreement.py`
    both fully green (only `request_bytes`-vs-rate and `request_bytes`-
    vs-`operation_depth` were actually locked). Mutation (裁定 4 再実行
    instruction): swap the two lines `_limit_gate` checks in and this
    test goes red (the denial flips to `concurrency`).

    Supervisor ruling 2026-09-09 update (Phase 10 WP-8c review F-3): this
    ruling (裁定 4, 監督裁定 2026-09-06, restated verbatim above) governs
    the CELL-LEVEL order this test itself exercises -- a direct, in-
    process call into `cell._limit_gate`, reaching neither `http.py` nor
    any HTTP boundary at all -- and that order is UNCHANGED by Phase 10
    WP-8c: this test stays green, verbatim, with no edit to its own body.

    On the HTTP PLANE specifically, WP-8c introduced a pre-authentication,
    deployment-wide `concurrency` slot (`HttpService.acquire_concurrency_
    slot()`, taken BEFORE `_authenticate`, `http.py`'s own module-header
    comment) that is now evaluated ahead of the per-credential `requests_
    per_minute` window, which stays keyed by credential and therefore
    stays reachable only AFTER authentication succeeds. Consequently, ON
    THE HTTP PLANE ONLY, a request that is BOTH rate-exhausted AND
    concurrency-exhausted is now denied `concurrency`, NOT `requests_per_
    minute` -- the OPPOSITE of 裁定 4's own cell-level order restated
    above. This is not a contradiction of 裁定 4 (which remains fully
    true for the cell-level call this test itself makes); it is a
    SEPARATE, ADDITIONAL ruling that fixes the HTTP-plane order
    specifically, pinned by `test_preauth_concurrency_bound.py::test_
    http_plane_denies_concurrency_before_requests_per_minute` in THIS
    peer's own test suite (and its isomorphic r2db counterpart, same
    test name)."""
    config = FoundationConfig(max_requests_per_minute=1, max_concurrency=1, max_request_bytes=1_000_000, max_operation_depth=10)
    cell = ApplicationCell("app1", config)
    dev = _principal(credential_id="dev-rate-vs-conc", role=Role.DEVELOPER)
    runtime = _principal(credential_id="rt-rate-vs-conc", role=Role.RUNTIME)
    cell.create_collection(dev, "t", {"a": "text"})
    # Consumes the sole requests_per_minute unit on `runtime`'s own window.
    cell.insert(runtime, "t", {"a": "y"})

    holder = cell._ApplicationCell__limit_holder  # noqa: SLF001
    entered = threading.Event()
    release = threading.Event()

    def hold():
        # A genuinely DIFFERENT credential -- its own rate window is
        # untouched, so it can enter the gate and hold the sole
        # concurrency slot for real (concurrency is process-wide, never
        # per-credential -- design D-1's own decision).
        with cell._limit_gate(_principal(credential_id="holder-cred-rvc"), request=None):
            entered.set()
            release.wait(timeout=5)

    holder_thread = threading.Thread(target=hold)
    holder_thread.start()
    try:
        assert entered.wait(timeout=5), "holder thread never entered the gate"
        assert holder._active == 1, f"expected 1 request genuinely held in-flight, got {holder._active}"

        # `runtime`'s own rate window is exhausted AND the sole
        # concurrency slot is held by someone else, at the same instant --
        # if rate is checked first, this denies `requests_per_minute`
        # without the concurrency counter ever being consulted.
        with pytest.raises(ResourceLimitError) as excinfo:
            cell.insert(runtime, "t", {"a": "z"})
        assert excinfo.value.details == {"limit_class": "requests_per_minute"}
    finally:
        release.set()
        holder_thread.join(timeout=5)
    assert not holder_thread.is_alive()
    assert holder._active == 0


def test_gate_denies_concurrency_before_request_bytes():
    """A concurrency-exhausted cell denies a SECOND, byte-oversized
    request for `concurrency`, not `request_bytes` -- proving concurrency
    is checked before the structural byte estimate. The in-flight hold is
    REAL (a second thread genuinely inside `_limit_gate`, confirmed via
    the holder's own `_active` counter before proceeding), not simulated."""
    config = FoundationConfig(max_requests_per_minute=100, max_concurrency=1, max_request_bytes=150, max_operation_depth=10)
    cell = ApplicationCell("app1", config)
    dev = _principal(credential_id="dev2", role=Role.DEVELOPER)
    cell.create_collection(dev, "t", {"a": "text"})
    holder = cell._ApplicationCell__limit_holder  # noqa: SLF001 - white-box peer-local test

    entered = threading.Event()
    release = threading.Event()

    def hold():
        with cell._limit_gate(_principal(credential_id="holder-cred"), request=None):
            entered.set()
            release.wait(timeout=5)

    holder_thread = threading.Thread(target=hold)
    holder_thread.start()
    try:
        assert entered.wait(timeout=5), "holder thread never entered the gate"
        assert holder._active == 1, f"expected 1 request genuinely held in-flight, got {holder._active}"

        huge_value = "x" * 1000
        with pytest.raises(ResourceLimitError) as excinfo:
            cell.insert(dev, "t", {"a": huge_value})
        assert excinfo.value.details == {"limit_class": "concurrency"}
    finally:
        release.set()
        holder_thread.join(timeout=5)
    assert not holder_thread.is_alive()
    assert holder._active == 0


def test_gate_denies_request_bytes_before_operation_depth():
    """A request that is BOTH byte-oversized AND depth-oversized is
    denied `request_bytes`, never `operation_depth`. The SAME request
    shape is then shown to genuinely violate `operation_depth` too, once
    `max_request_bytes` is raised out of the way -- proving the first
    result is really about ORDER, not about this shape never being able
    to trip the depth check at all."""
    deep_and_big = {"a": {"b": {"c": "x" * 200}}}  # depth 4 (dict->dict->dict->str), ~800 structural bytes

    tight_bytes = FoundationConfig(max_requests_per_minute=100, max_concurrency=10, max_request_bytes=150, max_operation_depth=2)
    cell = ApplicationCell("app1", tight_bytes)
    dev = _principal(credential_id="dev3", role=Role.DEVELOPER)
    cell.create_collection(dev, "t", {"a": "json"})
    with pytest.raises(ResourceLimitError) as excinfo:
        cell.insert(dev, "t", deep_and_big)
    assert excinfo.value.details == {"limit_class": "request_bytes"}

    loose_bytes = FoundationConfig(max_requests_per_minute=100, max_concurrency=10, max_request_bytes=1_000_000, max_operation_depth=2)
    cell2 = ApplicationCell("app1", loose_bytes)
    dev2 = _principal(credential_id="dev4", role=Role.DEVELOPER)
    cell2.create_collection(dev2, "t", {"a": "json"})
    with pytest.raises(ResourceLimitError) as excinfo2:
        cell2.insert(dev2, "t", deep_and_big)
    assert excinfo2.value.details == {"limit_class": "operation_depth"}


def test_gate_denies_operation_depth_before_budget_validation():
    """Phase 9 WP-3cd closure (監督裁定集約 rulings-r5-r6.md K-1): a
    `transact` request that is BOTH depth-oversized AND carries an
    invalid `budget` (here, `execution_ms` above this deployment's own
    declared bound) is denied `operation_depth`, never `VALIDATION_
    FAILED` for `budget` -- proving `narrow_limits_by_budget`'s own
    validity check now runs AFTER `requests_per_minute`/`concurrency`/
    `request_bytes`/`operation_depth` (`_limit_gate`), matching r2db's
    own `_slot` -> `check_request` -> `check_depth` -> `narrow_limits_by_
    budget` order (audit-wp3cd.md §3 N-3: MitateDB used to validate
    `budget` at the FACADE layer, before this gate was ever entered --
    an observable peer asymmetry this closure fixes). The SAME request
    shape is then shown to genuinely violate the budget bound too, once
    `max_operation_depth` is raised out of the way -- proving the first
    result is really about ORDER, not about this shape never being able
    to trip the budget check at all. Mutation: revert `_limit_gate`'s own
    `narrow_limits_by_budget` call to run BEFORE `_check_operation_depth`
    (or move it back to the facade layer, before `_gate` is entered) and
    this goes red (the denial flips to `VALIDATION_FAILED`)."""
    deep = {"a": {"b": {"c": "x"}}}  # depth 4 (dict->dict->dict->str)

    tight_depth = FoundationConfig(
        max_requests_per_minute=100, max_concurrency=10, max_request_bytes=1_000_000,
        max_operation_depth=2, max_execution_ms=5_000)
    cell = ApplicationCell("app1", tight_depth)
    dev = _principal(credential_id="dev5", role=Role.DEVELOPER)
    runtime = _principal(credential_id="rt5", role=Role.RUNTIME)
    cell.create_collection(dev, "t", {"a": "json"})
    with pytest.raises(ResourceLimitError) as excinfo:
        cell.transact(
            runtime, [{"type": "insert", "collection": "t", "values": deep}],
            budget={"execution_ms": 1_000_000})
    assert excinfo.value.details == {"limit_class": "operation_depth"}

    loose_depth = FoundationConfig(
        max_requests_per_minute=100, max_concurrency=10, max_request_bytes=1_000_000,
        max_operation_depth=10, max_execution_ms=5_000)
    cell2 = ApplicationCell("app1", loose_depth)
    dev2 = _principal(credential_id="dev6", role=Role.DEVELOPER)
    runtime2 = _principal(credential_id="rt6", role=Role.RUNTIME)
    cell2.create_collection(dev2, "t", {"a": "json"})
    with pytest.raises(ValidationError) as excinfo2:
        cell2.transact(
            runtime2, [{"type": "insert", "collection": "t", "values": deep}],
            budget={"execution_ms": 1_000_000})
    assert excinfo2.value.details["violated_declaration"] == "budget"


def test_measure_request_bytes_rejects_a_container_with_too_many_elements_before_the_running_total_would():
    """`_measure_request_bytes`'s own per-container element-count early-
    reject (`len(item) > bound // 8`) is evaluated on a container's own
    entry -- BEFORE any of its children's cost is added to the running
    total. It catches a shape the running-total check ALONE never would:
    an EMPTY (or near-empty) container costs only `2`, cheaper than any
    scalar's flat `8` -- so a container holding many EMPTY sub-containers
    can have an excessive ELEMENT COUNT while its total structural cost
    stays comfortably under `bound`. 20,000 empty sub-lists: total sum
    (`2 + 20_000 * 2 = 40_002`) stays under `bound=100_000`, but the
    element count (20,000) exceeds `bound // 8 = 12_500` -- only the
    early-reject (design D-1 実装の形, work order 完了条件 4 / 変異 4) can
    catch this shape; removing it (measured directly, WP-1a) lets the
    running-total check alone pass it through structurally (this exact
    request measures to well under `bound` by total bytes alone)."""
    bound = 100_000
    request = {"items": [[] for _ in range(20_000)]}
    with pytest.raises(ResourceLimitError) as excinfo:
        _measure_request_bytes(request, bound)
    assert excinfo.value.details == {"limit_class": "request_bytes"}


# ---------------------------------------------------------------------------
# concurrency: N held -> N+1 denied -> released -> all N complete (design
# D-1 実装の形 2, work order 完了条件 2 / 変異 2)
# ---------------------------------------------------------------------------


def test_concurrency_holds_n_then_denies_nplus1_then_releases_all_n():
    config = FoundationConfig(max_concurrency=2)
    cell = ApplicationCell("app1", config)
    principal = _principal()
    holder = cell._ApplicationCell__limit_holder  # noqa: SLF001

    barrier = threading.Barrier(2, timeout=5)
    release = threading.Event()
    completed: list[int] = []

    def hold():
        with cell._limit_gate(principal, request=None):
            barrier.wait()
            release.wait(timeout=5)
        completed.append(threading.get_ident())

    threads = [threading.Thread(target=hold) for _ in range(2)]
    for t in threads:
        t.start()

    # Non-vacuity: the barrier only releases once BOTH threads have
    # reached the held state together, and this loop additionally
    # confirms the holder's own counter genuinely reflects 2 in-flight.
    deadline = time.monotonic() + 5
    while holder._active < 2 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert holder._active == 2, f"expected 2 requests genuinely held in-flight, got {holder._active}"

    with pytest.raises(ResourceLimitError) as excinfo:
        with cell._limit_gate(principal, request=None):
            pass  # pragma: no cover - never reached, denied on entry
    assert excinfo.value.details == {"limit_class": "concurrency"}

    release.set()
    for t in threads:
        t.join(timeout=5)
    assert len(completed) == 2, "both held requests must complete once released"
    assert holder._active == 0, "the in-flight counter must return to 0 after release"

    # After release, a fresh request succeeds again (the slot is real,
    # not permanently poisoned).
    with cell._limit_gate(principal, request=None):
        pass


def test_concurrency_is_released_on_the_exception_path_too():
    """`finally`-guaranteed release (design D-1 実装の形 2): a request
    that fails AFTER acquiring its concurrency slot (a validation error
    inside the gated body) still releases the slot -- proving the release
    is unconditional, not only on the success path."""
    config = FoundationConfig(max_concurrency=1)
    cell = ApplicationCell("app1", config)
    principal = _principal()
    holder = cell._ApplicationCell__limit_holder  # noqa: SLF001

    with pytest.raises(Exception):  # noqa: B017 - any exception mid-gate must still release
        with cell._limit_gate(principal, request=None):
            assert holder._active == 1, "the slot must be held while the gated body runs"
            raise RuntimeError("simulated failure inside the gated body")
    assert holder._active == 0, "the slot must be released even when the gated body raises"


# ---------------------------------------------------------------------------
# limit-state holder: 1 process (composition root) = 1 holder, shared
# across every application it provisions (design D-1, work order 完了条件
# 6 / 変異 6)
# ---------------------------------------------------------------------------


def test_limit_holder_is_shared_across_applications_in_one_process():
    """`ProvisioningFacade` builds exactly ONE `_LimitStateHolder`
    (`service.py::ProvisioningFacade.__init__`) and injects it into
    every `ApplicationCell` it provisions -- design D-1's own "1プロセス
    1個" decision. Two DIFFERENT applications' own credentials therefore
    share the SAME process-wide in-flight counter. Mutation 6 (design
    table): move the holder's construction into `ApplicationCell.
    __init__` instead (per-application) and this test goes red -- each
    application would get its own, independent counter, so application
    B's own insert would never observe application A's in-flight
    request at all."""
    config = FoundationConfig(max_concurrency=1)
    facade = ProvisioningFacade("synthetic-test-pepper-0123456789ab", config)
    facade.provision_application("app_a")
    facade.provision_application("app_b")
    holder_a = facade.cells["app_a"]._ApplicationCell__limit_holder  # noqa: SLF001
    holder_b = facade.cells["app_b"]._ApplicationCell__limit_holder  # noqa: SLF001
    assert holder_a is holder_b, "every ApplicationCell this facade provisions must share ONE holder"

    _, dev_a_secret = facade.issue_credential("app_a", Role.DEVELOPER)
    _, dev_b_secret = facade.issue_credential("app_b", Role.DEVELOPER)
    service = MitateDataService(facade)
    session_a = service.open_session(dev_a_secret)
    session_a.create_collection("t", {"label": "text"})
    session_b = service.open_session(dev_b_secret)
    session_b.create_collection("t", {"label": "text"})

    release = threading.Event()
    entered = threading.Event()

    def hold():
        with facade.cells["app_a"]._limit_gate(_principal(app_id="app_a", credential_id="holder-cred"), request=None):
            entered.set()
            release.wait(timeout=5)

    holder_thread = threading.Thread(target=hold)
    holder_thread.start()
    try:
        assert entered.wait(timeout=5)
        assert holder_a._active == 1

        # Application B's OWN developer session -- a genuinely different
        # application, different credential -- must ALSO be denied
        # concurrency, proving the counter is process-wide.
        with pytest.raises(ResourceLimitError) as excinfo:
            session_b.create_collection("u", {"label": "text"})
        assert excinfo.value.details == {"limit_class": "concurrency"}
    finally:
        release.set()
        holder_thread.join(timeout=5)
    assert holder_a._active == 0


# ---------------------------------------------------------------------------
# execution_ms: real PostgreSQL lock_timeout (design D-1 実装の形 3, work
# order 完了条件 3 / 変異 3). Requires `MITATEDB_TEST_ADMIN_DSN` (or the
# default local socket) -- fails loudly, never skips (README's own policy).
# ---------------------------------------------------------------------------


def test_execution_ms_pg_lock_timeout_maps_to_limit_exceeded(platform, app_a):
    """`backend_postgres.py`'s own `SET LOCAL lock_timeout`, computed
    from the residual budget `ApplicationCell._limit_gate`'s own
    `deadline` still has: a real row lock held open by a SEPARATE
    connection makes `cell.update(...)` block until that computed
    timeout, at which point PostgreSQL's own `LockNotAvailable` is
    mapped to `LIMIT_EXCEEDED`/`execution_ms` -- not an unclassified
    hang or a raw driver exception. Mutation 3 (design table): remove the
    `SET LOCAL`-setting line and this update instead blocks indefinitely
    (this test's own `pytest.raises` never fires, and the test times out
    instead of passing) -- this test goes red."""
    config = FoundationConfig(max_execution_ms=300)
    cell = make_cell(app_a, config)
    dev = _principal(app_id=app_a.app_id, credential_id="dev-pg-execms", role=Role.DEVELOPER)
    runtime = _principal(app_id=app_a.app_id, credential_id="rt-pg-execms", role=Role.RUNTIME)
    try:
        cell.create_collection(dev, "locked_rows", {"label": "text"})
        cell.insert(runtime, "locked_rows", {"label": "x"})

        locker = psycopg.connect(app_a.runtime_dsn, autocommit=False)
        try:
            with locker.cursor() as cur:
                cur.execute("SELECT * FROM locked_rows FOR UPDATE")
            start = time.monotonic()
            with pytest.raises(ResourceLimitError) as excinfo:
                cell.update(runtime, "locked_rows", {"label": "y"}, [Filter("label", "eq", "x")])
            elapsed = time.monotonic() - start
            assert excinfo.value.details == {"limit_class": "execution_ms"}
            # The block must have genuinely waited close to the configured
            # budget (not returned instantly for an unrelated reason) --
            # a generous lower bound avoids CI-timing flakiness while
            # still ruling out an immediate, budget-independent denial.
            assert elapsed >= 0.05, f"denial returned suspiciously fast ({elapsed}s) for a 300ms budget"
        finally:
            locker.rollback()
            locker.close()
    finally:
        close_cell(cell)


def test_execution_ms_pg_lock_timeout_maps_to_limit_exceeded_via_transact(platform, app_a):
    """Phase 8 WP-1a rework 1 (裁定 2, 監督裁定 2026-09-06): the SAME
    mapping the test immediately above proves for the STANDALONE `cell.
    update()` path (`PostgresBackend.update()`), proven here for the
    TRANSACT path instead (`cell.transact()` -> `PostgresBackend.
    update_in_transaction()`) -- the code review that sent this WP back
    found the mapping present on the four standalone methods but ABSENT
    on `insert_in_transaction`/`update_in_transaction`/`delete_
    in_transaction`, and every HTTP mutation (`http.py::post_mutate`'s
    own `_mutation_item`/`transact()` call, insert included) reaches the
    database through this exact family -- so the pre-rework gap left the
    whole HTTP mutation surface unable to ever observe a real
    `LIMIT_EXCEEDED`/`execution_ms` denial, only the in-process
    surface's own direct `cell.update()`/`.insert()`/`.delete()` calls
    could.

    Mutation (裁定 2 再実行 instruction): remove the `SET LOCAL`-setting
    line `PostgresBackend.begin()` runs (the batch-wide timeout this
    transact path relies on, module comment above `_timeout_ms`) and
    this update instead blocks indefinitely -- this test's own
    `pytest.raises` never fires and the test times out, going red."""
    config = FoundationConfig(max_execution_ms=300)
    cell = make_cell(app_a, config)
    dev = _principal(app_id=app_a.app_id, credential_id="dev-pg-execms-tx", role=Role.DEVELOPER)
    runtime = _principal(app_id=app_a.app_id, credential_id="rt-pg-execms-tx", role=Role.RUNTIME)
    try:
        cell.create_collection(dev, "locked_rows_tx", {"label": "text"})
        cell.insert(runtime, "locked_rows_tx", {"label": "x"})

        locker = psycopg.connect(app_a.runtime_dsn, autocommit=False)
        try:
            with locker.cursor() as cur:
                cur.execute("SELECT * FROM locked_rows_tx FOR UPDATE")
            start = time.monotonic()
            with pytest.raises(ResourceLimitError) as excinfo:
                cell.transact(runtime, [
                    {"type": "update", "collection": "locked_rows_tx", "values": {"label": "y"},
                     "filters": [Filter("label", "eq", "x")]},
                ])
            elapsed = time.monotonic() - start
            assert excinfo.value.details == {"limit_class": "execution_ms"}
            assert elapsed >= 0.05, f"denial returned suspiciously fast ({elapsed}s) for a 300ms budget"
        finally:
            locker.rollback()
            locker.close()
    finally:
        close_cell(cell)


# ---------------------------------------------------------------------------
# request_bytes dual layer: HTTP middleware (real bytes) and in-process
# structural estimate answer identically (design D-1, work order 完了条件
# 8 / 変異 8).
# ---------------------------------------------------------------------------


def test_request_bytes_dual_layer_responses_are_identical(platform, app_a):
    """design D-1 "HTTP面の二重化について": the ASGI byte-count middleware
    (real bytes, `http.py:208`) and the in-process structural estimate
    (`cell.py::_measure_request_bytes`, reached via `ApplicationCell.
    _limit_gate`) measure DIFFERENT quantities of the SAME class --
    "whichever crosses its own bound first rejects". This fixture sets
    the middleware's own bound (`request_bytes_limit`) LARGER than the
    structural estimate's own bound (`FoundationConfig.max_request_
    bytes`), so both layers are independently exercisable within ONE
    fixture: a request whose REAL bytes exceed `request_bytes_limit` is
    caught by the middleware before a session is even reached; a request
    whose real bytes stay under that bound but whose STRUCTURAL estimate
    (str: `len * 4`) exceeds the smaller `max_request_bytes` is caught by
    the in-process gate instead. Mutation 8 (design table): change the
    gate's own `limit_class` for this rejection to something other than
    `"request_bytes"` and the second response's `details.limit_class`
    assertion below goes red."""
    read_store = PostgresCredentialStore(
        platform.api_dsn, pepper="synthetic-test-pepper-mitatedb-http-limits-0000", schema=platform.registry_schema,
    )
    write_store = PostgresCredentialStore(
        platform.controlplane_dsn, pepper="synthetic-test-pepper-mitatedb-http-limits-0000", schema=platform.registry_schema,
    )
    config = FoundationConfig(max_request_bytes=400)
    backend = PostgresBackend(app_a.runtime_dsn, app_a.developer_dsn)
    # Phase 10 WP-8c review F-2 (supervisor ruling 2026-09-09): `HttpService`
    # now fails closed at construction time unless BOTH `limit_holder`/
    # `max_concurrency` are supplied (`http.py::HttpService.__init__`'s own
    # comment) -- an explicit `_LimitStateHolder`, shared with `cell` below,
    # and this test's own `config.max_concurrency` (unset here, so the
    # dataclass default, 32 -- irrelevant to what this test actually
    # exercises, `request_bytes`, but still required to construct).
    limit_holder = _LimitStateHolder()
    cell = ApplicationCell(app_a.app_id, config, backend=backend, limit_holder=limit_holder)

    def _cell_factory(application_id: str) -> ApplicationCell:
        assert application_id == app_a.app_id
        return cell

    service = HttpService(read_store, _cell_factory, limit_holder=limit_holder, max_concurrency=config.max_concurrency)
    # Deliberately LARGER than config.max_request_bytes=400 -- see this
    # test's own docstring for why the gap between the two bounds is what
    # makes both layers independently exercisable.
    app = create_app(service, request_bytes_limit=4000)
    _, runtime_bearer = write_store.issue(app_a.app_id, Role.RUNTIME)
    _, developer_bearer = write_store.issue(app_a.app_id, Role.DEVELOPER)
    stack = types.SimpleNamespace(app=app, runtime_bearer=runtime_bearer, developer_bearer=developer_bearer)

    try:
        _create_entity(stack, "dual_layer_target", fields=["label"])

        # Layer 1 (ASGI middleware): real bytes clearly over 4000, sent
        # as a raw body (never even valid JSON) -- proves the rejection
        # happens before parsing, exactly like the middleware's own
        # existing tests in test_http.py.
        middleware_denial = _post(
            stack, "/v1/data/dual_layer_target/mutations", bearer=stack.runtime_bearer,
            content=b" " * 4500, headers={"content-type": "application/json"},
        )
        assert middleware_denial.status_code == 413
        middleware_body = middleware_denial.json()
        assert middleware_body["code"] == "LIMIT_EXCEEDED"
        assert middleware_body["details"]["limit_class"] == "request_bytes"

        # Layer 2 (in-process structural estimate): a well-formed request
        # whose real byte count stays comfortably under 4000, but whose
        # structural estimate (a 200-char string * 4 = 800, over
        # max_request_bytes=400) the gate itself rejects.
        payload = {"operations": [{"operation": "insert", "values": {"label": "x" * 200}}]}
        assert len(json.dumps(payload).encode("utf-8")) < 4000
        gate_denial = _post(stack, "/v1/data/dual_layer_target/mutations", bearer=stack.runtime_bearer, json_body=payload)
        assert gate_denial.status_code == 413, gate_denial.text
        gate_body = gate_denial.json()
        assert gate_body["code"] == "LIMIT_EXCEEDED"
        assert gate_body["details"]["limit_class"] == "request_bytes"

        # Identical response shape from both layers.
        assert middleware_denial.status_code == gate_denial.status_code
        assert middleware_body["code"] == gate_body["code"]
        assert set(middleware_body.keys()) == set(gate_body.keys())
    finally:
        backend.close()
        read_store.close()
        write_store.close()


# ---------------------------------------------------------------------------
# isolated profile: all 4 new field values stay exercisable (design D-1
# 実装の形 7, work order 完了条件 12 / 変異 11). `_drive_concurrency`'s own
# `bound <= _MAX_EXERCISABLE_LIMIT` assert (`test_c05_limit_declaration_
# agreement.py`) does not exist until WP-1b -- the design's own mutation
# table explicitly permits a peer-local profile check as this WP's own
# observation form instead ("1a時点ではpeer-localのprofile検査で赤にする
# 形でもよい"). Measured (WP-1a): raising `max_concurrency` to 201 in the
# in-process isolated profile does NOT currently turn anything red in
# either `conformance-tests/test_c05_limit_declaration_agreement.py` or
# `MitateDB-api/tests` (verified directly, then reverted) -- there is
# genuinely no other WP-1a-scoped assertion that would catch this
# regression, which is exactly why this test exists.
# ---------------------------------------------------------------------------


def test_isolated_profile_new_fields_stay_within_the_exercisable_ceiling():
    import os
    import sys

    conformance_dir = os.path.join(os.path.dirname(__file__), "..", "conformance")
    if conformance_dir not in sys.path:
        sys.path.insert(0, conformance_dir)
    conformance_tests_dir = os.path.join(os.path.dirname(__file__), "..", "..", "conformance-tests")
    if conformance_tests_dir not in sys.path:
        sys.path.insert(0, conformance_tests_dir)
    import conformance_adapter_mitatedb as m

    adapter = m.MitateDBConformanceAdapter()
    with adapter.isolated_application_surface() as iso:
        config = iso._control.config  # noqa: SLF001 - white-box peer-local test
        assert config.max_requests_per_minute <= 200
        assert config.max_concurrency <= 200
        assert config.max_operation_depth <= 200
        # `max_concurrency` is specifically small (a real thread/connection
        # count `hold_in_flight`, WP-1b, will actually hold open) -- not
        # merely under the generic ceiling.
        assert config.max_concurrency <= 10, (
            f"max_concurrency={config.max_concurrency} is not a small, realistic in-flight count"
        )
        # Phase 8 WP-1a rework 1 (裁定 6, 監督裁定 2026-09-06): the code
        # review that sent this WP back found this test asserted NOTHING
        # about `max_execution_ms` -- a count-valued `_MAX_EXERCISABLE_
        # LIMIT` ceiling does not apply to it (it is `reference_wall_
        # clock`, a millisecond budget, never driven position-exact by
        # V2), but it must still be a genuinely positive, finite budget
        # (V1 (c)) that stays comfortably larger than a slow CI iteration
        # (this profile's own module comment in `conformance_adapter_
        # mitatedb.py::isolated_application_surface`, avoiding a false,
        # CI-flaky `execution_ms` denial on ordinary isolated-profile
        # traffic) without being absurdly large either.
        assert 0 < config.max_execution_ms <= 60_000, (
            f"max_execution_ms={config.max_execution_ms} is not a small, positive millisecond budget"
        )
