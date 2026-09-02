"""Durable-audit dispatch: the coalescing denial router, the bounded
buffer + overflow alert, and the pre-commit hook builder (design docs/
design/PHASE4_DURABLE_AUDIT_SINK_V1.md D-2/D-3/D-4, work order WP-3(a)).

Independent implementation of r2db-api's own dispatch logic
(`r2db_api.service`'s `_PreCommitHook`/`_AuditBuffer`/`_DenialCoalescer`,
R-2's closing paragraph: no code sharing between peers) -- same safety
properties, realized as one small, explicit `AuditRouter` object instead
of being folded into a single per-process facade class, because this peer
has no r2db-style single `DataService` facade: authentication/
authorization live in `auth.CredentialStore`/`credential_store_postgres.
PostgresCredentialStore`, and data operations live in `cell.
ApplicationCell` -- two independently-testable objects, not one. `main.
build_app` constructs exactly ONE `AuditRouter` per process (mirroring
r2db-api's `DataService` being one-per-process; the coalescer/buffer below
are explicitly documented as process-local, D-3/D-4's own "review N-4"
instruction) and hands the SAME instance to every `ApplicationCell`/
credential store it builds, so `(application_id, actor_id, operation,
reason_code)` coalescing keys and buffer capacity are shared across every
application this process serves, not duplicated per cell.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Any, Callable, Optional

from .application_audit import (DEFAULT_AUDIT_BUFFER_CAPACITY,
                                DEFAULT_AUDIT_FLUSH_INTERVAL_S,
                                DEFAULT_DENIAL_COALESCE_WINDOW_S,
                                ApplicationAuditEvent, ApplicationAuditSink,
                                coalesced_count)
from .audit_hook import ApplicationAuditHook
from .errors import AuditSinkUnavailable

_logger = logging.getLogger(__name__)

# Phase 4 (design D-3; WP-2(a) review J-2, supervisor ruling 2026-09-02,
# folded in from the outset per this WP's own发注 instruction to pre-empt
# the WP-2(a)/(b) review findings): an INCLUSION set -- the 6 contract
# codes D-3's own range table names (authentication/authorization denial,
# `FORBIDDEN`, `APPLICATION_DISABLED`, a revoked credential, `DESTRUCTIVE_
# CONFIRMATION_REQUIRED`) are the only reason codes this router treats as
# fail-closed/coalesced-durable. Every other code -- `VALIDATION_FAILED`/
# `LIMIT_EXCEEDED`/`CAPABILITY_UNSUPPORTED`/`NOT_FOUND`/`AUTH_STATE_
# UNAVAILABLE`/`CONFLICT`/`PRECONDITION_FAILED`/`SERVICE_UNAVAILABLE` and
# anything else this peer can raise -- is out of scope for durable/
# buffered recording (D-3's own "除外列挙ではなく包含列挙" ruling: an
# exclusion-list reading would let `SERVICE_UNAVAILABLE` produced by the
# audit pipeline's OWN failure re-enter as a "new" denial and write a
# THIRD durable row for one operation, D-10's own prohibited case (ii)).
#
# This peer's own `http.py::_CLASSIFY_ORDER` never actually constructs an
# `AUTH_REQUIRED` (missing bearer token, `http.py::_CredentialMissing`,
# raised before `HttpService.authenticate` ever calls a credential store)
# or an `AUTH_REVOKED`/`APPLICATION_DISABLED` (both fold into a single
# `AuthenticationError` -> `AUTH_INVALID` at this peer's own credential
# stores today, per `http.py`'s own documented "known divergence from
# r2db-api" comment) -- all three names stay in this set anyway, matching
# D-3's own table by name rather than by "what this peer happens to
# reach today": a future call site that DOES construct one of them (or a
# future widening of this peer's own credential-store denial vocabulary)
# is durable/coalesced automatically, with no separate set to remember to
# update. `test_durable_denial_codes_match_the_design_d3_table`
# (`tests/test_application_audit.py`) fixes this set against D-3's table
# by name.
DURABLE_DENIAL_CODES = frozenset({
    "AUTH_REQUIRED",
    "AUTH_INVALID",
    "AUTH_REVOKED",
    "FORBIDDEN",
    "APPLICATION_DISABLED",
    "DESTRUCTIVE_CONFIRMATION_REQUIRED",
})

# Phase 4 (design §7.4/D-4): fixed, no-interpolation log messages -- the
# design's own instruction ("可変部に実データを載せない"). A fixed string
# also means these two call sites can never accidentally leak a
# client-supplied value into process logs.
_BUFFER_OVERFLOW_LOG_MESSAGE = "application_audit buffer overflow: events were dropped"
_ALERT_WRITE_FAILED_LOG_MESSAGE = "application_audit overflow-alert row could not be written; retrying with backoff"
_ALERT_WRITE_RECOVERED_LOG_MESSAGE = "application_audit overflow-alert row recorded; pending overflow cleared"
_COALESCE_AGGREGATE_WRITE_FAILED_LOG_MESSAGE = "application_audit coalesced-denial summary row could not be written; retrying"
_COALESCE_AGGREGATE_WRITE_RECOVERED_LOG_MESSAGE = "application_audit coalesced-denial summary row recorded; retry cleared"

# Phase 4 (design §7.4, review m-4): exponential backoff for the sticky
# overflow-alert retry, capped at 60s -- an unbounded equal-interval retry
# against a durably-failing sink would itself become a logging DoS. The
# FLOOR for this backoff is the flush interval (`_AuditBuffer`'s own
# `alert_min_interval_s`) -- no alert attempt is ever spaced closer
# together than the composition root's own flush cadence.
_ALERT_BACKOFF_CAP_S = 60.0


class _PreCommitHook:
    """The concrete `ApplicationAuditHook` `AuditRouter.make_pre_commit_
    hook` returns (design D-2/D-10) -- every field the durable row needs is
    already bound here at construction time; the caller (a backend method,
    or `cell.ApplicationCell.transact`) supplies none of it, only the
    fail-closed/buffer-class decision (D-2's normative rule: the
    confirmation choke for a batch, unconditionally for schema
    operations)."""

    __slots__ = ("_sink", "_fields")

    def __init__(self, sink: Any, fields: dict[str, Any]) -> None:
        self._sink = sink
        self._fields = fields

    def pre_commit(self) -> None:
        try:
            self._sink.append(outcome="allow", count=None, **self._fields)
        except Exception as exc:
            raise AuditSinkUnavailable(
                "the durable audit sink could not record this operation; it was not submitted"
            ) from exc

    def commit_failed(self) -> None:
        # D-2's error-row rule: best-effort from the response's point of
        # view (the caller fails `AuditSinkUnavailable` regardless of
        # whether this succeeds -- the data commit already failed either
        # way) -- any exception here is swallowed, never re-raised.
        try:
            self._sink.append(outcome="error", reason_code="commit_failed", count=None, **self._fields)
        except Exception:
            pass


class _AuditBuffer:
    """Phase 4 (design D-4/§7.3/§7.4): the bounded in-memory buffer for
    ordinary (buffer-class) data-operation success events, plus the
    overflow-alert sticky-retry state. Independent implementation of
    r2db-api's own `service._AuditBuffer` -- identical safety properties
    (threshold + periodic flush, tx-isolated flush, N-1/N-2's dropped-
    count and alert-rate-limiting discipline), same structure, adapted to
    stand alone rather than be nested inside a facade class.

    Process-local (D-4's own "review N-4" instruction): capacity is
    per-process, not per-deployment -- a multi-instance deployment's real
    bound is `capacity * <max instances>`, runbook (WP-4) territory, not
    code.
    """

    _FLUSH_THRESHOLD_FRACTION = 0.8

    def __init__(
        self, sink: Any, *, capacity: int, clock: Callable[[], float],
        alert_min_interval_s: float = DEFAULT_AUDIT_FLUSH_INTERVAL_S,
    ) -> None:
        self._sink = sink
        self._capacity = max(1, capacity)
        self._flush_threshold = max(1, int(self._capacity * self._FLUSH_THRESHOLD_FRACTION))
        self._clock = clock
        self._alert_min_interval_s = max(0.0, alert_min_interval_s)
        self._lock = threading.Lock()
        self._events: list[ApplicationAuditEvent] = []
        self._dropped_total = 0
        self._alert_pending = False
        self._alert_next_retry_at = 0.0
        self._alert_backoff_s = self._alert_min_interval_s
        self._alert_failure_logged = False
        self._flush_currently_failing = False

    def push(self, event: ApplicationAuditEvent) -> None:
        overflowed = False
        trigger_flush = False
        with self._lock:
            if len(self._events) >= self._capacity:
                self._events.pop(0)
                self._dropped_total += 1
                self._alert_pending = True
                overflowed = True
            self._events.append(event)
            if len(self._events) >= self._flush_threshold:
                trigger_flush = True
        if overflowed:
            # §7.4: fixed message, no interpolation -- logged every time an
            # event is actually, irrevocably evicted (not merely retained
            # for retry), since each eviction is itself a new, permanent
            # loss.
            _logger.error(_BUFFER_OVERFLOW_LOG_MESSAGE)
        if trigger_flush:
            # Threshold flush (§7.3's "periodic OR threshold" latitude) --
            # outside the lock (already released above), on the calling
            # thread.
            self.flush()

    def pending_count(self) -> int:
        with self._lock:
            return len(self._events)

    def flush(self) -> None:
        """D-4/§7.3: called on demand (tests, the adapter privilege hook,
        `AuditRouter.flush`), periodically (a composition root's own
        background thread), and from `push()` at the threshold -- these
        THREE call sites can race each other on independent threads at
        any moment (review B-2, major, supervisor ruling 2026-09-03).
        Writes the current buffer contents as one batch, then attempts
        the sticky overflow-alert retry -- always in that order, always
        on a connection/transaction of its own (`sink.append`/
        `append_many` each open their own connection --
        `PostgresApplicationAuditSink`'s own docstring).

        Reentrancy (review B-2): the pending batch is SWAPPED OUT of
        `self._events` under the lock -- `self._events` is replaced with
        a fresh empty list and the PREVIOUS list becomes `pending` --
        rather than merely snapshotting a copy (`list(self._events)`)
        while leaving the originals in place for a later `del [:n]` to
        remove. The prior snapshot-then-delete shape let two concurrent
        `flush()` calls both snapshot the SAME still-present events
        before either one's own (slower) I/O completed and removed them,
        writing every event in that overlap durably TWICE -- measured
        directly: a periodic-flush thread and a threshold-triggered flush
        on a request thread, racing on the same buffer, doubled every
        buffered event (D-10's own prohibited case (ii), recurring here
        at the buffer-flush layer instead of the pre-commit-hook layer
        D-10 already covers). With the swap, two concurrent `flush()`
        calls always take DISJOINT batches -- whichever call's swap runs
        first empties the list; the other's own swap (immediately after,
        still inside its own lock acquisition) sees only whatever was
        pushed in between, never the same events again. A failed batch
        write puts its own (still-unwritten) batch back -- PREPENDED, so
        it is retried before anything pushed while the failed I/O was in
        flight -- rather than discarding it or alerting on its own.

        Review B-3 (blocker, supervisor ruling 2026-09-03, adjudicated
        (a) -- same fix, same strength as r2db-api's own identical B-1-on-
        B-2 patch, `scratchpad/r2db-flush-reentrancy.patch`): while this
        method holds `pending` outside `self._events` (the swap that
        fixes the double-write above), `push()` sees an empty (or merely
        in-flight-refilled) buffer and does not evict against `pending`'s
        own size -- capacity is enforced only against whatever is
        CURRENTLY sitting in `self._events`. A naive, unconditional
        restore-on-failure (`self._events = pending + self._events`)
        could therefore exceed `_capacity` by up to `len(pending)`, and
        because the surviving overflow is never itself re-evicted by a
        later `push()` (each `push()` only ever evicts ONE item, the one
        IT just added), a sustained sink outage would let the buffer grow
        WITHOUT BOUND across repeated failed flushes -- breaking D-4's
        "bounded in-memory buffer" and D-1 review M-5's capacity-side
        availability argument, and doing so SILENTLY: no `push()` eviction
        fires during this growth, so `_dropped_total` never increments and
        the overflow alert (D-4) never appears even though evidence is
        unboundedly accumulating in memory. So the restore truncates back
        down to `_capacity`, dropping from the FRONT (oldest first,
        matching `push()`'s own `pop(0)` FIFO discipline) -- and, exactly
        like a genuine `push()`-path eviction, counts only what was
        ACTUALLY, irrevocably discarded here (never the merely-retried
        remainder) in `_dropped_total`, sets `_alert_pending`, and logs
        the same fixed overflow message.
        """
        with self._lock:
            pending = self._events
            self._events = []
        if not pending:
            self._retry_alert()
            return
        try:
            self._sink.append_many(pending)
        except Exception:
            truncated = 0
            with self._lock:
                # N-1/N-2: put the un-written batch back rather than
                # discarding it -- it is retried by the next flush, not
                # counted in `_dropped_total` (nothing has actually been
                # lost) and nothing new to alert or log about on this
                # path alone. Prepended ahead of anything a concurrent
                # `push()` added to `self._events` while this I/O was in
                # flight, so flush order still matches arrival order.
                self._events = pending + self._events
                self._flush_currently_failing = True
                # B-3: re-impose the capacity bound `push()` could not
                # enforce while this batch was held outside `self._events`
                # -- drop the oldest overflow, exactly the FIFO discipline
                # `push()`'s own eviction branch uses, and count ONLY this
                # genuine, irrevocable loss (the rest is still a retained
                # retry, not a drop).
                overflow = len(self._events) - self._capacity
                if overflow > 0:
                    del self._events[:overflow]
                    truncated = overflow
                    self._dropped_total += truncated
                    self._alert_pending = True
            if truncated:
                _logger.error(_BUFFER_OVERFLOW_LOG_MESSAGE)
            # `push()`'s own eviction branch is the only OTHER source of
            # genuine, irrevocable loss.
        else:
            with self._lock:
                # Review B-3 (supervisor ruling 2026-09-03, "後勝ちレース
                # 防止"): a CONCURRENT flush() covering a DIFFERENT
                # (disjoint) batch may be failing right now -- this call's
                # own success says nothing about that. Only clear the
                # failing flag once the buffer this call can actually
                # observe is empty (nothing left retained, nothing new
                # sitting unflushed); otherwise leave the flag as it
                # already is rather than blindly forcing it to `False` and
                # letting a genuinely-failing concurrent flush's own
                # backoff get reset to the floor by a race.
                if not self._events:
                    self._flush_currently_failing = False
        self._retry_alert()

    def _retry_alert(self) -> None:
        with self._lock:
            if not self._alert_pending:
                return
            now = self._clock()
            if now < self._alert_next_retry_at:
                return
            count = self._dropped_total
            flush_failing = self._flush_currently_failing
        try:
            self._sink.append(
                event_class="security_control_failure", request_id=str(uuid.uuid4()), application_id=None,
                actor_type="system", actor_id=None, role=None, operation="audit_buffer",
                target_kind="audit_sink", outcome="deny", reason_code="audit_buffer_overflow",
                target_id=None, count=coalesced_count(count),
            )
        except Exception:
            with self._lock:
                self._alert_backoff_s = min(_ALERT_BACKOFF_CAP_S, max(self._alert_min_interval_s, self._alert_backoff_s * 2))
                self._alert_next_retry_at = self._clock() + self._alert_backoff_s
                self._alert_failure_logged = True
            # This branch is only ever reached once the backoff interval
            # has already elapsed (the early return above enforces that),
            # so logging unconditionally here already matches "first
            # attempt, then once per backoff interval".
            _logger.error(_ALERT_WRITE_FAILED_LOG_MESSAGE)
            return
        with self._lock:
            # SUBTRACT exactly the `count` this alert row just reported,
            # never blindly reset to 0 -- more drops can have accumulated
            # (a concurrent eviction) between reading `count` above and
            # this INSERT completing.
            self._dropped_total -= count
            if self._dropped_total <= 0:
                self._dropped_total = 0
                self._alert_pending = False
            # The backoff is keyed to whether the buffer FLUSH is
            # currently failing, not to whether this alert row's own
            # INSERT just succeeded -- a healthy alert path must not be
            # used to re-trigger a fresh attempt every `alert_min_
            # interval_s` forever while the underlying flush stays broken.
            if flush_failing:
                self._alert_backoff_s = min(_ALERT_BACKOFF_CAP_S, max(self._alert_min_interval_s, self._alert_backoff_s * 2))
            else:
                self._alert_backoff_s = self._alert_min_interval_s
            self._alert_next_retry_at = self._clock() + self._alert_backoff_s
            was_logged = self._alert_failure_logged
            self._alert_failure_logged = False
        if was_logged:
            _logger.error(_ALERT_WRITE_RECOVERED_LOG_MESSAGE)


class _DenialCoalescer:
    """Phase 4 (design D-3/P4-D3): the coalescing state for fail-closed-
    class denials. Independent implementation of r2db-api's own
    `service._DenialCoalescer` -- identical safety properties (per-key
    locking so a same-key concurrent caller never observes "a window
    already exists" before the first occurrence's own durable INSERT has
    resolved; a failed aggregate-row write is requeued, never silently
    discarded; a shutdown flush covers every open window, not only
    expired ones), same structure, adapted to stand alone.

    Keyed by `(application_id, actor_id or "unknown", operation,
    reason_code)`, window `W` seconds: the first occurrence of a new key
    writes a durable row synchronously (fail-closed -- `route()` raises
    `errors.AuditSinkUnavailable` if that write fails); every occurrence
    after that, within the same window, only increments an in-memory
    counter. When the window is later found expired (lazily, on the next
    `route()` call for THAT key, or explicitly via `flush_expired()`/
    `flush_all()`), a second row -- carrying the repeat count in `count`
    -- is written for that key, if there were any repeats at all.

    Process-local (D-3's own "review N-4" instruction): a shared store is
    never consulted, so the same key can legitimately produce one row per
    process/instance.
    """

    def __init__(self, sink: Any, *, window_s: float, clock: Callable[[], float]) -> None:
        self._sink = sink
        self._window_s = window_s
        self._clock = clock
        self._lock = threading.Lock()
        self._windows: dict[tuple[Any, ...], dict[str, Any]] = {}
        self._key_locks: dict[tuple[Any, ...], threading.Lock] = {}
        self._key_lock_refcount: dict[tuple[Any, ...], int] = {}
        self._aggregate_write_failing = False

    def _acquire_key_lock(self, key: tuple[Any, ...]) -> threading.Lock:
        with self._lock:
            lock = self._key_locks.setdefault(key, threading.Lock())
            self._key_lock_refcount[key] = self._key_lock_refcount.get(key, 0) + 1
            return lock

    def _release_key_lock_ref(self, key: tuple[Any, ...]) -> None:
        with self._lock:
            remaining = self._key_lock_refcount.get(key, 1) - 1
            if remaining <= 0:
                self._key_lock_refcount.pop(key, None)
                if key not in self._windows:
                    self._key_locks.pop(key, None)
            else:
                self._key_lock_refcount[key] = remaining

    def _requeue_failed_aggregate(self, key: tuple[Any, ...], state: dict[str, Any]) -> None:
        """Called only while holding this KEY's OWN `key_lock`, right
        after its aggregate-row write attempt raised -- puts
        `state["repeat_count"]` back where a future flush (periodic,
        explicit, shutdown, or the very next `route()` call for this same
        key) will retry it, instead of discarding it."""
        with self._lock:
            existing = self._windows.get(key)
            if existing is not None:
                existing["repeat_count"] += state["repeat_count"]
            else:
                self._windows[key] = state

    def _note_aggregate_write_result(self, succeeded: bool) -> None:
        """Fixed-message `logging.error`, only on a failing<->healthy
        state transition -- not once per attempt, which would reproduce
        the exact logging-DoS risk the overflow-alert path already
        closes."""
        log_message: Optional[str] = None
        with self._lock:
            if succeeded:
                if self._aggregate_write_failing:
                    self._aggregate_write_failing = False
                    log_message = _COALESCE_AGGREGATE_WRITE_RECOVERED_LOG_MESSAGE
            else:
                if not self._aggregate_write_failing:
                    self._aggregate_write_failing = True
                    log_message = _COALESCE_AGGREGATE_WRITE_FAILED_LOG_MESSAGE
        if log_message is not None:
            _logger.error(log_message)

    def route(self, *, key: tuple[Any, ...], fields: dict[str, Any]) -> None:
        now = self._clock()
        key_lock = self._acquire_key_lock(key)
        try:
            with key_lock:
                with self._lock:
                    state = self._windows.get(key)
                    if state is not None and now - state["window_start"] < self._window_s:
                        state["repeat_count"] += 1
                        return
                    expired_state = state
                    if expired_state is not None:
                        del self._windows[key]
                if expired_state is not None and expired_state["repeat_count"] > 0:
                    # This key's own window had already expired (nobody
                    # had routed it since) -- flush its repeat-summary row
                    # first, still under this key's own lock.
                    try:
                        self._sink.append(count=coalesced_count(expired_state["repeat_count"]), **expired_state["fields"])
                    except Exception:
                        self._requeue_failed_aggregate(key, expired_state)
                        self._note_aggregate_write_result(False)
                    else:
                        self._note_aggregate_write_result(True)
                # New (or freshly-expired-and-reopened) window: the
                # synchronous, fail-closed first-occurrence INSERT.
                try:
                    self._sink.append(count=None, **fields)
                except Exception as exc:
                    raise AuditSinkUnavailable(
                        "the durable audit sink could not record this denial; it was refused"
                    ) from exc
                with self._lock:
                    # If the inline expired-window flush just above
                    # failed, it already requeued the still-unwritten
                    # repeat count into `self._windows[key]`. Merge
                    # instead of overwriting: carry the requeued
                    # `repeat_count` forward into the fresh window rather
                    # than resetting it to 0.
                    requeued = self._windows.get(key)
                    carried_repeat_count = requeued["repeat_count"] if requeued is not None else 0
                    self._windows[key] = {"window_start": now, "repeat_count": carried_repeat_count, "fields": fields}
        finally:
            self._release_key_lock_ref(key)

    def flush_expired(self) -> None:
        now = self._clock()
        self._flush_keys(lambda key, state: now - state["window_start"] >= self._window_s)

    def flush_all(self) -> None:
        """Forces EVERY currently-open window to be flushed, expired or
        not -- used only at graceful shutdown. Once a process is about to
        stop, there is no "wait for the window to naturally expire"
        future left; D-3 only sanctions losing counts to an actual crash,
        never to an orderly stop."""
        self._flush_keys(lambda key, state: True)

    def _flush_keys(self, is_due: "Callable[[tuple[Any, ...], dict[str, Any]], bool]") -> None:
        due: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        with self._lock:
            for key in list(self._windows.keys()):
                state = self._windows[key]
                if is_due(key, state):
                    due.append((key, state))
                    del self._windows[key]
        for key, state in due:
            if state["repeat_count"] <= 0:
                continue
            key_lock = self._acquire_key_lock(key)
            try:
                with key_lock:
                    try:
                        self._sink.append(count=coalesced_count(state["repeat_count"]), **state["fields"])
                    except Exception:
                        self._requeue_failed_aggregate(key, state)
                        self._note_aggregate_write_result(False)
                    else:
                        self._note_aggregate_write_result(True)
            finally:
                self._release_key_lock_ref(key)


def _now_iso() -> str:
    from datetime import datetime, timezone as _tz
    return datetime.now(_tz.utc).isoformat()


class AuditRouter:
    """Phase 4 (design D-2/D-3/D-4): the one shared, per-process object
    `main.build_app`/`control_composition.build_control_service`-adjacent
    composition constructs and hands to every `auth.CredentialStore`/
    `credential_store_postgres.PostgresCredentialStore`/`cell.
    ApplicationCell` it builds. Bundles the durable sink, the bounded
    buffer, and the denial coalescer behind three small entry points --
    the MitateDB-shaped equivalent of what r2db-api's own `DataService`
    does internally in `_event`/`_denial_event`/`_make_audit_hook`.
    """

    def __init__(
        self, durable_sink: Any = None, *, buffer_capacity: int = DEFAULT_AUDIT_BUFFER_CAPACITY,
        denial_coalesce_window_s: float = DEFAULT_DENIAL_COALESCE_WINDOW_S,
        alert_min_interval_s: float = DEFAULT_AUDIT_FLUSH_INTERVAL_S,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self._durable_sink = durable_sink if durable_sink is not None else ApplicationAuditSink()
        clock = clock or time.monotonic
        self._buffer = _AuditBuffer(self._durable_sink, capacity=buffer_capacity, clock=clock, alert_min_interval_s=alert_min_interval_s)
        self._coalescer = _DenialCoalescer(self._durable_sink, window_s=denial_coalesce_window_s, clock=clock)

    @property
    def durable_sink(self) -> Any:
        return self._durable_sink

    def make_pre_commit_hook(
        self, *, event_class: str, request_id: Optional[str], application_id: Optional[str],
        actor_type: Optional[str], actor_id: Optional[str], role: Optional[str], operation: str,
        target_kind: Optional[str], target_id: Optional[str] = None,
    ) -> ApplicationAuditHook:
        """Phase 4 (design D-2): builds the `ApplicationAuditHook` a
        backend method or `cell.ApplicationCell.transact` calls itself,
        immediately before its own commit point. Every field the durable
        row needs is already resolved here."""
        fields = {
            "event_class": event_class, "request_id": request_id, "application_id": application_id,
            "actor_type": actor_type, "actor_id": actor_id, "role": role, "operation": operation,
            "target_kind": target_kind, "target_id": target_id,
        }
        return _PreCommitHook(self._durable_sink, fields)

    def route_denial(
        self, *, reason_code: Optional[str], event_class: str, request_id: Optional[str],
        application_id: Optional[str], actor_type: Optional[str], actor_id: Optional[str],
        role: Optional[str], operation: str, target_kind: Optional[str], target_id: Optional[str] = None,
    ) -> None:
        """Phase 4 (design D-3): the shared fail-closed/coalesced-denial
        dispatch. `reason_code` outside `DURABLE_DENIAL_CODES` (the
        inclusion set) returns without any durable/buffered record at all
        -- these denials stay recorded ONLY in this peer's own pre-
        existing 6-field `audit.AuditSink`, which every call site keeps
        appending to unconditionally, unchanged, alongside this call
        (D-10's own instruction)."""
        if reason_code not in DURABLE_DENIAL_CODES:
            return
        key = (application_id, actor_id or "unknown", operation, reason_code)
        fields = {
            "event_class": event_class, "request_id": request_id, "application_id": application_id,
            "actor_type": actor_type, "actor_id": actor_id, "role": role, "operation": operation,
            "target_kind": target_kind, "outcome": "deny", "reason_code": reason_code, "target_id": target_id,
        }
        self._coalescer.route(key=key, fields=fields)

    def push_buffer_event(
        self, *, event_class: str, request_id: Optional[str], application_id: Optional[str],
        actor_type: Optional[str], actor_id: Optional[str], role: Optional[str], operation: str,
        target_kind: Optional[str], target_id: Optional[str] = None,
    ) -> None:
        """Phase 4 (design D-4/§7.3): enqueues an ordinary (buffer-class)
        data-operation success event -- `outcome="allow"` always; this
        method exists only for events D-2's dispatch rule places in the
        buffer-class bucket (query/insert/update success; catalog reads
        have no MitateDB equivalent)."""
        self._buffer.push(ApplicationAuditEvent(
            event_id=str(uuid.uuid4()), event_class=event_class, occurred_at=_now_iso(), request_id=request_id,
            application_id=application_id, actor_type=actor_type, actor_id=actor_id, role=role,
            operation=operation, target_kind=target_kind, outcome="allow", reason_code=None, target_id=target_id,
        ))

    def flush(self, *, force_expire_denial_windows: bool = False) -> None:
        """Phase 4 (design D-4/§7.3/§7.4): synchronously drains the
        bounded buffer, retries the sticky overflow-alert row if one is
        pending and due, and sweeps denial-coalescing windows. Called on
        demand by this repository's own tests and by a composition root's
        periodic timer alike.

        `force_expire_denial_windows=True`: flushes EVERY currently-open
        denial-coalescing window, expired or not -- used exactly once, by
        a composition root's graceful-shutdown path."""
        self._buffer.flush()
        if force_expire_denial_windows:
            self._coalescer.flush_all()
        else:
            self._coalescer.flush_expired()

    def pending_buffer_count(self) -> int:
        return self._buffer.pending_count()


__all__ = [
    "DURABLE_DENIAL_CODES",
    "AuditRouter",
]
