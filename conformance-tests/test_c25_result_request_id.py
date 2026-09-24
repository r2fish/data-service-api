"""C-25 -- every successful result a peer declaring contract 1.7.0 returns
carries `request_id`; distinct executions carry distinct values; where
`audit_query` is available, a mutation's value is the value its own audit
events carry (SI-14).

design: docs/design/PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md
D-7, §6.2 "C-25 成功応答の request_id", registered in `conformance-tests/
CONDITIONS.md`. Every test here carries `@pytest.mark.condition("C-25")`
via the module-level `pytestmark`.

Unconditional 1.7.0 obligation (D-1(2)), version-gated exactly like C-21 --
branches on the plug's own declared `contract_version` (`adapter.parse_
semver`, never a string compare), with the runtime-attached `xfail(strict=
True)` read at execution time (`request.node.add_marker`, work order §0.4
item 4):

  - `contract_version < (1, 7, 0)`: `xfail(strict=True)`; the body below
    still runs for real, so an early implementation would XPASS and, under
    `strict=True`, turn that into a hard failure (D-1(7)).
  - `>= (1, 7, 0)`: (1) `QueryResult`/`MutationResult`/`SchemaOperationResult`
    all carry `request_id`; (2) two consecutive, distinct executions carry
    distinct values; (3) where `audit_query` is not `unavailable`, a
    mutation's own `request_id` matches the `request_id` its own audit
    event carries; (4) (WP-1b rework) where `idempotency` is not
    `unavailable`, a resend answered from an idempotency record carries
    the ORIGINAL execution's own `request_id`, not a new one -- this
    row's own proposition on the correlation side, declared-first on
    `idempotency` independently of C-23's own test file.

**Disclosed**: audit correlation (3) is observed only on the plug(s) for
which `audit_query` answers for real -- "green on 4 plugs" here does not,
by itself, mean "audit-correlated on 4 plugs"; which plugs actually reach
(3) is recorded in `conformance-tests/CONDITIONS.md`'s own C-25 row, not
silently assumed uniform. (4) is observed only on the plug(s) for which
`idempotency` is not `unavailable`, recorded the same way.
"""
from __future__ import annotations

import time
from typing import Any, Mapping

import pytest

from adapter import ConformanceAdapter, ConformanceDenial, fresh_identifier, parse_semver
from conftest import provision_pair, registered_adapters

pytestmark = pytest.mark.condition("C-25")


_DEFAULT_AUDIT_QUERY_PAGE_LIMIT = 1000


def _audit_query_control_state(adapter: ConformanceAdapter) -> tuple[str, int]:
    """C-25 (3)'s driving condition (Phase 10 WP-5a, design docs/design/
    PHASE10_DEPLOYMENT_EVIDENCE_V1.md §3 D-10): reads `audit_query`'s
    status AND its declared `max_limit` off the plug's own CONTROL-plane
    discovery (`control_capabilities()`, via `control_credential()`) --
    NEVER the data-plane `capability_document()`, which every registered
    plug declares `unavailable` on by product-code constant (both peers
    return `{"status": "unavailable", "authority": "control_or_audit"}`
    from their data-plane `capabilities()`; `r2db-api/src/r2db_api/
    service.py`, `MitateDB-api/src/mitatedb_api/cell.py`). D-10's own
    rationale: `audit_query`'s authority is `control_or_audit` -- control
    HOSTING is what makes it "available" for C-25's purposes, not the
    data-plane document. Mirrors `test_c09_audit_evidence.py`'s own
    `_audit_query_declaration` helper (same read; this file's own copy,
    per this suite's no-cross-file-import-of-test-helpers convention).
    Supersedes this file's former `_audit_query_status` (data-plane
    read), which made C-25 (3) vacuously never drive on any of the 4
    then-registered plugs (L9-15 -- every plug declares data-plane
    `audit_query: unavailable` as a constant, so the old driving
    condition was always false).

    Reading status and `max_limit` off the SAME discovery call (Phase 10
    WP-5a review L-2) means the drain page size actually tracks the
    plug's own declared bound instead of a hardcoded constant that could
    silently outrun a lower deployed `max_limit` (`VALIDATION_FAILED`) or
    undercount a raised one (`page_limit` never used the ONE canonical
    reading before this fix). Falls back to `_DEFAULT_AUDIT_QUERY_PAGE_
    LIMIT` when the plug's own discovery omits `max_limit` or publishes a
    non-positive value -- both peers' control-plane discovery documents
    do publish it (`control_plane.py`'s own `_MAX_AUDIT_QUERY_LIMIT`), so
    the fallback is a defensive default, not the normal path."""
    control_actor = adapter.control_credential()
    document = adapter.control_capabilities(control_actor)
    audit_query = document.get("capabilities", {}).get("audit_query", {})
    status = audit_query.get("status", "unavailable")
    max_limit = audit_query.get("max_limit", _DEFAULT_AUDIT_QUERY_PAGE_LIMIT)
    if not isinstance(max_limit, int) or max_limit <= 0:
        max_limit = _DEFAULT_AUDIT_QUERY_PAGE_LIMIT
    return status, max_limit


def _audit_query_status_control(adapter: ConformanceAdapter) -> str:
    """Thin wrapper over `_audit_query_control_state` for the (still
    common) callers that only need the status half -- the module-level
    non-vacuity guard below, and this file's own H-1 divergence check."""
    return _audit_query_control_state(adapter)[0]


def _expected_branch_for_pre_1_7_0(pre_1_7_0: bool) -> str:
    return "pre_1_7_0" if pre_1_7_0 else "request_id_present"


def _find_audit_event_by_request_id(
    reader: ConformanceAdapter, request_id: str, deadline_ms: int, page_limit: int,
) -> tuple[Mapping[str, Any] | None, int, int]:
    """Pages FORWARD through the audit log (the contract's own fixed
    ascending total order, `(recorded_at, plane, event_id)` -- oldest
    first) using the `after`-cursor pagination `capabilities().
    audit_query.completeness_note` documents, until the event carrying
    `request_id` is found or `deadline_ms` is exhausted. Returns `(event
    -or-None, waited_ms, events_scanned)`. Always walks from the front
    (`after=None`) on a first call -- Phase 10 WP-5a review M-2: an
    earlier revision kept a cross-call `after`-cursor cache keyed by
    `adapter.name`, but the full suite never actually calls this helper
    more than once per (worker, plug) (measured), so the cache was dead
    state that was never read; it is removed rather than kept unread, and
    its key/value mismatch (keyed by `adapter.name` but valued by `iso`'s
    own log position -- wrong once two `iso` compositions for the same
    plug are drained in one worker) goes with it.

    `page_limit` (the caller's own reading of the plug's declared
    `audit_query.max_limit`, Phase 10 WP-5a review L-2 --
    `_audit_query_control_state`) drains a large backlog in a handful of
    round trips rather than many; a page shorter than the requested limit
    means this poll has caught up to the live edge of the log
    (`completeness_note`'s own "keep polling ... until a page comes back
    empty"), at which point this helper falls back to re-polling the SAME
    `after` position (a cursor "always resolves", per that same note)
    until the target event surfaces (visibility_lag_ms) or the deadline
    is spent.

    Fetches ONE `control_credential()` for the whole drain and reuses it
    across pages (Phase 10 WP-5a review M-1 -- reused rather than
    refetched every page, which was roughly doubling this helper's own
    control-plane request count for no benefit the vast majority of the
    time); only refetches on `AUTH_INVALID`, since this adapter's own
    `control_credential()` can still silently self-repair/rotate the live
    credential on some internal condition mid-drain, invalidating an
    actor captured earlier in the SAME drain. The poll interval backs off
    (250ms, doubling, capped at 2s) once caught up to the live edge,
    rather than a fixed 250ms sleep, to cut the request rate further
    while still resolving quickly for a low-lag deployment. A
    `LIMIT_EXCEEDED` `ConformanceDenial` while draining (this plug's own
    `control_requests_per_minute`, shared with every other control-plane
    caller in this same rolling window) backs off and retries rather than
    propagating. A drain that needs more than `_MAX_CONTROL_REQUESTS`
    control-plane round trips FAILS outright (never silently skips) --
    Phase 10 WP-5a review M-1: that many round trips against a
    `control_requests_per_minute=200`-class plug risks tripping
    `LIMIT_EXCEEDED` for OTHER control-plane tests sharing the same
    rolling window, which is a real cost worth surfacing as a hard
    failure of this helper's own request budget, not something to retry
    past silently.
    """
    _MAX_CONTROL_REQUESTS = 40
    waited_ms = 0
    poll_interval_s = 0.25
    max_poll_interval_s = 2.0
    rate_limit_backoff_s = 3.0
    after: str | None = None
    scanned = 0
    # Overall wall-clock backstop, independent of `deadline_ms` (which
    # only bounds the visibility-lag WAITING once caught up to the live
    # edge): draining an unexpectedly huge backlog, or riding out a
    # rate-limit cooldown, must not spin forever.
    started = time.monotonic()
    max_total_s = 90.0
    control_actor = reader.control_credential()
    control_requests_made = 0
    while True:
        request: dict[str, Any] = {"limit": page_limit}
        if after is not None:
            request["after"] = after
        control_requests_made += 1
        assert control_requests_made <= _MAX_CONTROL_REQUESTS, (
            f"{getattr(reader, 'name', reader)!r}: audit drain for request_id {request_id!r} exceeded "
            f"{_MAX_CONTROL_REQUESTS} control-plane requests without reaching the live edge or the "
            "target event -- Phase 10 WP-5a review M-1's request-budget bound (a hard failure, not a "
            "skip: this many round trips risks tripping LIMIT_EXCEEDED for other control-plane tests "
            "sharing this plug's rolling window)"
        )
        try:
            events = reader.audit_query(control_actor, request).get("events", [])
        except ConformanceDenial as denial:
            if denial.code == "AUTH_INVALID":
                control_actor = reader.control_credential()
                continue
            if denial.code != "LIMIT_EXCEEDED" or time.monotonic() - started >= max_total_s:
                raise
            time.sleep(rate_limit_backoff_s)
            continue
        scanned += len(events)
        for event in events:
            if event.get("request_id") == request_id:
                return event, waited_ms, scanned
        if events:
            after = events[-1].get("cursor")
        caught_up = len(events) < page_limit
        if time.monotonic() - started >= max_total_s:
            return None, waited_ms, scanned
        if caught_up:
            if waited_ms >= deadline_ms:
                return None, waited_ms, scanned
            time.sleep(poll_interval_s)
            waited_ms += int(poll_interval_s * 1000)
            poll_interval_s = min(poll_interval_s * 2, max_poll_interval_s)
        # else: a full page came back -- more of the backlog likely
        # remains, so loop again immediately (no sleep) to drain it.


def test_c25_result_request_id(adapter: ConformanceAdapter, isolated, request: pytest.FixtureRequest) -> None:
    iso = isolated
    contract_version = adapter.capability_document()["contract_version"]
    pre_1_7_0 = parse_semver(contract_version) < (1, 7, 0)
    if pre_1_7_0:
        request.node.add_marker(pytest.mark.xfail(
            reason=(
                f"{adapter.name} declares contract_version {contract_version!r} (< 1.7.0) -- carrying "
                "request_id on every successful result is an unconditional 1.7.0 obligation (design "
                "D-1(2)/D-7); this branch is expected to fail (not merely skip) until this peer's own "
                "version-flip commit lands, per D-1(7)."
            ),
            strict=True,
        ))

    developer, runtime, _app_id = provision_pair(iso, app_prefix="c25")
    entity = fresh_identifier("c25")
    iso.create_entity(developer, entity, {"label": "text"})

    if pre_1_7_0:
        # Work order §6 訂正註 7 (supervisor ruling, post-WP-1-audit,
        # 2026-09-07): a non-asserting RECORD only, not part of the
        # xfail(strict=True) node's pass/fail body -- see test_c21's
        # identical treatment for the reasoning (audit mutation E3/E2: an
        # assert here gives the xfail-marked node an always-available way
        # to fail for a reason OTHER than the real request_id check below,
        # masking a genuinely early implementation instead of exposing it
        # as a strict XPASS). The real, unconditional detection is the
        # body's own `assert request_id1` / `assert request_id2` further
        # down, which only pass for real once R-7 is wired in.
        pre_marker = fresh_identifier("c25pre")
        pre_result = iso.attempt_mutation_with_result(
            runtime, entity, "insert", values={"label": pre_marker}, where_field=None, where_value=None,
        )
        _already_has_request_id = bool(pre_result.get("request_id"))  # recorded, never asserted

    # (1)/(2) MutationResult: two distinct executions carry distinct,
    # present request_id values.
    marker1 = fresh_identifier("c25m1")
    marker2 = fresh_identifier("c25m2")
    result1 = iso.attempt_mutation_with_result(
        runtime, entity, "insert", values={"label": marker1}, where_field=None, where_value=None,
    )
    result2 = iso.attempt_mutation_with_result(
        runtime, entity, "insert", values={"label": marker2}, where_field=None, where_value=None,
    )
    request_id1, request_id2 = result1.get("request_id"), result2.get("request_id")
    assert request_id1, f"{adapter.name}: a successful MutationResult carries no request_id -- {result1!r}"
    assert request_id2, f"{adapter.name}: a successful MutationResult carries no request_id -- {result2!r}"
    assert request_id1 != request_id2, (
        f"{adapter.name}: two distinct mutation executions carried the SAME request_id {request_id1!r}"
    )

    # (1) QueryResult.
    query_result = iso.query_with_budget(runtime, entity, ["label"], "label", marker1)
    assert query_result.get("request_id"), (
        f"{adapter.name}: a successful QueryResult carries no request_id -- {query_result!r}"
    )

    # (1) SchemaOperationResult.
    schema_field = fresh_identifier("c25sf")
    schema_result = iso.schema_operation_with_result(
        developer, entity, "add_field", field=schema_field, field_type="string",
    )
    assert schema_result.get("request_id"), (
        f"{adapter.name}: a successful SchemaOperationResult carries no request_id -- {schema_result!r}"
    )

    # (3) audit correlation -- Phase 10 WP-5a (design D-10): driven by the
    # plug's own CONTROL-plane discovery declaring audit_query enabled/
    # partial, never by the data-plane capability_document() (which is a
    # constant "unavailable" on every registered plug -- L9-15). Read
    # against `iso` (the isolated_application_surface() yield the mutation
    # itself was made through), NEVER the shared, session-scoped `adapter`:
    # for the 2 in-process plugs, `iso` is a wholly separate composition
    # with its own private control-plane/audit sink (adapter.py's own
    # isolated_application_surface() docstring), so `adapter.audit_query()`
    # can never see an event `iso` recorded -- discovered empirically while
    # implementing this WP (this exact code path never ran before D-10,
    # since the old data-plane driving condition was a constant
    # "unavailable" on every plug, L9-15).
    audit_status, page_limit = _audit_query_control_state(iso)
    # H-1 (Phase 10 WP-5a review, supervisor ruling 2026-09-08): the branch
    # below drives off `iso`'s OWN control-plane discovery, never the
    # session adapter's -- for the 2 in-process plugs `iso` is a wholly
    # separate composition with its own private control plane (see the
    # comment further down), so a discovery mismatch between the two is
    # exactly the gap the former module-level-only non-vacuity guard could
    # not see (it only ever read the session adapter/registry): if `iso`'s
    # own discovery drifts to `unavailable` while the session adapter
    # still declares `audit_query` enabled/partial, this test would
    # silently fall into the `not_driven` branch and pass, while the
    # module-level guard -- reading only the session adapter -- would
    # still see `enabled` and stay green. Asserting the two agree, in the
    # SAME parametrized test that actually drives off `iso`, closes that
    # gap per-plug rather than only at the whole-registry level.
    session_audit_status = _audit_query_status_control(adapter)
    assert audit_status == session_audit_status, (
        f"{adapter.name}: iso's own control-plane audit_query status {audit_status!r} disagrees "
        f"with the session adapter's {session_audit_status!r} -- an isolated composition must not "
        "drift from the plug's own declared control-plane surface (Phase 10 WP-5a review H-1)"
    )
    # Non-vacuity, asserted from WITHIN this per-plug test (in addition to
    # the whole-registry module-level guard below): `registered_adapters()`
    # is built once at collection time and is complete within any single
    # xdist WORKER process regardless of which condition-group that worker
    # is running (conftest.py's own module comment), so reading it here
    # never depends on, or needs to cross, an xdist test-distribution
    # group boundary.
    registry_audit_statuses = {
        name: _audit_query_status_control(adapter_obj) for name, adapter_obj in registered_adapters().items()
    }
    enabled_in_registry = [name for name, status in registry_audit_statuses.items() if status in ("enabled", "partial")]
    assert enabled_in_registry, (
        "no registered adapter's CONTROL-plane discovery declares audit_query enabled/partial -- "
        f"C-25 (3) would be vacuously skipped on every plug -- {registry_audit_statuses!r}"
    )
    audit_driven = audit_status in ("enabled", "partial")
    audit_expected_branch = "correlated" if audit_driven else "not_driven"
    audit_observed_branch = "not_driven"
    if audit_driven:
        iso.flush_audit_buffer()
        # Wait up to audit_visibility_lag_ms() + 2000ms (capped 30000ms)
        # once caught up to the live edge of the log, mirroring test_c09_
        # audit_evidence.py's own `_require_nonvacuous_provided` idiom
        # (poll on the DECLARED lag, never a fixed sleep). Measured
        # (Phase 10 WP-5a review L-1 -- corrects this comment's former,
        # inaccurate claim that the peers themselves differ here): BOTH
        # in-process peers declare `visibility_lag_ms` 0, and BOTH http
        # plugs declare 11000 on this deployment -- the lag is a property
        # of the http adapter (network + buffering), not of either peer,
        # so a row `flush_audit_buffer()` just made durable can still be
        # excluded from `audit_query` for that long on the http plugs
        # (the completeness_note's own "rows within visibility_lag_ms of
        # the current time are not yet returned").
        #
        # R-105 correction (design docs/design/SLOW_CALL_PHASE_TESTS_V0_1.
        # md D-1): both http plugs now declare the conformance-deployment
        # value 4000, not 11000 -- r2db-api's HTTP plug still declares it
        # as a fixed adapter-own constant sum (`CONFORMANCE_AUDIT_
        # STATEMENT_TIMEOUT_MS` + `CONFORMANCE_AUDIT_IDLE_TIMEOUT_MS` +
        # margin, unchanged in character from the value L-1 above
        # describes); MitateDB-api's HTTP plug has derived this value from
        # `pg_db_role_setting` since the Q4 phase (design D-1(c)) -- R-105
        # changes only the seeded numbers that its bootstrap's own `ALTER
        # ROLE` places on the `api`/`controlplane` writer roles (5000/5000
        # -> `CONFORMANCE_AUDIT_*` 1000/2000). L-1's "not of either peer"
        # still describes a property of the deployment, not of the peer
        # product -- what changed is the number, not the mechanism.
        #
        # `_find_audit_event_by_request_id` pages the FULL log forward
        # (also discovered empirically, running inside the full suite: a
        # single `{"limit": 200}` no-`after` query only ever sees the
        # OLDEST 200 rows, which a session with hundreds of prior
        # control-plane events never includes this test's own fresh one
        # in -- see that helper's own docstring).
        deadline_ms = min(iso.audit_visibility_lag_ms() + 2000, 30000)
        matched_event, waited_ms, scanned = _find_audit_event_by_request_id(
            iso, request_id1, deadline_ms, page_limit=page_limit,
        )
        # Completion condition 9 (work order §2 WP-5 table): observed_
        # branch is set from the ACTUAL poll outcome, deliberately a
        # 3rd, distinct value ("no_match_found") when driven but
        # unmatched -- NEVER collapsed straight to "correlated" here --
        # so the single assert below (mirroring test_c09_audit_evidence.
        # py's own individual guard, `test_c09_declared_capability_
        # implies_provided_branch`'s `assert form == "provided"`) is the
        # SOLE detector: dropping it would let a driven-but-uncorrelated
        # plug pass silently, which is exactly what this condition
        # closes (`{adapter.name}: ... after polling {waited_ms}ms`
        # below records the real diagnostic that assert used to carry).
        audit_observed_branch = "correlated" if matched_event is not None else "no_match_found"
        audit_poll_detail = (
            f"after polling {waited_ms}ms (deadline {deadline_ms}ms; scanned {scanned} total events "
            "across the paginated log)"
        )
    else:
        audit_poll_detail = "not driven -- no query was made"
    # observed_branch must equal the branch this plug's OWN control-plane
    # declaration implies -- mirrors test_c09_audit_evidence.py's
    # individual guard, applied to C-25 (3)'s own correlation
    # proposition. This is the ONLY assert covering (3); a mutation that
    # collapses audit_observed_branch straight to audit_expected_branch
    # (or drops this line) makes a driven-but-uncorrelated plug pass
    # silently -- the failure mode L9-15 left undetected.
    assert audit_observed_branch == audit_expected_branch, (
        f"{adapter.name}: control-plane audit_query status {audit_status!r} implies branch "
        f"{audit_expected_branch!r}, but the body observed {audit_observed_branch!r} -- {audit_poll_detail} "
        f"(mutation's own request_id {request_id1!r})"
    )

    # (4) idempotency correlation (design §6.2 C-25 (4), WP-1b rework): a
    # request answered from an idempotency record is not a new execution
    # and carries the ORIGINAL execution's own request_id -- this is C-23
    # (i)'s own property, but observed here from the request_id side
    # (this row's own proposition, not C-23's), so declare-first on
    # `idempotency` rather than assume it from C-23's own test file.
    idempotency_status = (
        adapter.capability_document().get("capabilities", {}).get("idempotency", {}).get("status", "unavailable")
    )
    if idempotency_status != "unavailable":
        replay_key = fresh_identifier("c25idemkey")
        replay_marker = fresh_identifier("c25idemrow")
        first_replay = iso.attempt_mutation_with_result(
            runtime, entity, "insert", values={"label": replay_marker}, where_field=None, where_value=None,
            idempotency_key=replay_key,
        )
        second_replay = iso.attempt_mutation_with_result(
            runtime, entity, "insert", values={"label": replay_marker}, where_field=None, where_value=None,
            idempotency_key=replay_key,
        )
        assert first_replay.get("request_id"), (
            f"{adapter.name}: the original, key-bearing execution carries no request_id -- {first_replay!r}"
        )
        assert second_replay.get("request_id") == first_replay.get("request_id"), (
            f"{adapter.name}: a resend answered from an idempotency record must carry the ORIGINAL "
            f"execution's own request_id, not a new one -- first={first_replay.get('request_id')!r}, "
            f"resend={second_replay.get('request_id')!r}"
        )

    # Work order §6 訂正註 7 (supervisor ruling, post-WP-1-audit,
    # 2026-09-07): the declaration-derived `observed_branch` cross-check
    # (C-07 (ii)'s own `_expected_branch_for_status` form) is done ONLY in
    # the `>= 1.7.0` branch -- see test_c21's identical treatment for the
    # reasoning (audit mutation E3/E2: with this unconditional, `expected_
    # branch` is always "pre_1_7_0" in the `< 1.7.0` branch while `observed_
    # branch` is always hardcoded "request_id_present", so the assert
    # ALWAYS raised there regardless of what the body actually observed,
    # making a genuine strict XPASS structurally impossible). In the
    # `< 1.7.0` branch the body's own unconditional `assert request_id1` /
    # `assert request_id2` above are the entire detection mechanism.
    if not pre_1_7_0:
        observed_branch = "request_id_present"
        expected_branch = _expected_branch_for_pre_1_7_0(pre_1_7_0)
        assert observed_branch == expected_branch, (
            f"{adapter.name}: contract_version {contract_version!r} implies branch {expected_branch!r}, but the "
            f"full body completed without any refusal -- observed {observed_branch!r} (an early implementation "
            "ahead of this peer's own version-flip commit, D-1(7))"
        )


def test_c25_audit_query_control_plane_driven_plugs_is_non_vacuous():
    """Completion condition 8 (Phase 10 WP-5a, work order §2 WP-5 table,
    design D-10): C-25 (3)'s driving condition -- CONTROL-plane discovery
    declaring `audit_query` enabled/partial -- must actually drive at
    least 1 registered plug. An empty set here would make the
    per-adapter correlation check in `test_c25_result_request_id` above
    vacuously take the `not_driven` branch on every plug -- exactly
    L9-15's prior state, where the driving condition was the DATA-plane
    `capability_document()` (a constant `unavailable` on every
    then-registered plug). The target set is derived mechanically from
    the live registry (`registered_adapters()`), never a hardcoded
    adapter-name list -- mirrors `test_c09_audit_evidence.py`'s own
    whole-registry guard shape."""
    driven: list[str] = []
    for name, adapter_obj in registered_adapters().items():
        if _audit_query_status_control(adapter_obj) in ("enabled", "partial"):
            driven.append(name)
    assert driven, (
        "no registered adapter's CONTROL-plane discovery declares audit_query enabled/partial -- "
        "C-25 (3) would be vacuously skipped on every plug (the L9-15 state this WP-5a closes)"
    )
