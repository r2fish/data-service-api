"""Application facade and separately held Control/Provisioning authority."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import threading
import time
from typing import Any, Callable, Iterator
import uuid

from .audit import ApplicationAuditSink, AuditEvent, AuditSink
from .audit_hook import ApplicationAuditHook
from .auth import AuthContext, CredentialStore
from .backend import StorageBackend
from .errors import FoundationError, fail
from .limits import ResourceLimits
from .structured import ApplicationCell, parse_predicate
from .topology import AuthorityTopology

_logger = logging.getLogger(__name__)

# Phase 4 (design PHASE4_DURABLE_AUDIT_SINK_V1.md D-3; WP-2(a) review J-2,
# supervisor ruling 2026-09-02): an INCLUSION set -- only a denial whose
# reason_code is one of these 6 (D-3's own range table, SI-14's minimal
# event class: authentication/authorization denial) is fail-closed/
# coalesced-durable. Every other reason_code -- D-3's originally-named 4
# non-durable codes (`VALIDATION_FAILED`/`LIMIT_EXCEEDED`/`CAPABILITY_
# UNSUPPORTED`/`NOT_FOUND`) AND everything else this facade can raise
# (`CONFLICT`, `PRECONDITION_FAILED`, `SERVICE_UNAVAILABLE`, `AUTH_STATE_
# UNAVAILABLE`, ...) -- is out of scope for durable/buffered recording
# (review N-2: buffering them would just let the flow problem D-3 exists to
# bound come back through the buffer instead). An exclusion-list reading
# (only the named 4 are non-durable, everything else durable) was this
# module's first implementation; the review's B-1 finding showed it lets a
# `SERVICE_UNAVAILABLE` produced by the audit pipeline's OWN failure re-enter
# as a "new" denial, writing a THIRD durable row for one operation (D-10's
# own prohibited case (ii)) -- switching to inclusion closes that path
# structurally (`SERVICE_UNAVAILABLE` was never in D-3's fail-closed list to
# begin with). `test_durable_denial_codes_match_the_design_d3_table`
# (`tests/test_application_audit.py`) fixes this set against D-3's table by
# name.
_DURABLE_DENIAL_CODES = frozenset({
    "AUTH_REQUIRED",       # 認証系 (AUTH_REQUIRED/AUTH_INVALID相当)
    "AUTH_INVALID",        # 認証系, and also covers this codebase's "credential disabled" case
    "AUTH_REVOKED",        # credential の revoked
    "FORBIDDEN",           # FORBIDDEN, and also this facade's "privilege denial" (schema())
    "APPLICATION_DISABLED",  # APPLICATION_DISABLED
    "DESTRUCTIVE_CONFIRMATION_REQUIRED",  # DESTRUCTIVE_CONFIRMATION_REQUIRED
})

# Phase 4 (design D-2/D-10): a `FoundationError.details` marker this
# module's own audit-hook/denial-routing code sets on a `SERVICE_UNAVAILABLE`
# it raises BECAUSE the durable audit pipeline itself just failed (a
# pre-commit sink failure, a post-commit `error`-row write, a coalesced-
# denial first-insert failure). `_event`'s own deny-dispatch checks this
# marker and skips routing such a denial through `_route_denial` again --
# without it, the generic `except FoundationError` handler every public
# method already has would treat this SERVICE_UNAVAILABLE as a brand-new
# denial needing its own durable write, producing a second (or third)
# durable row for what D-10 requires stays at most one (+ the D-2 error-row
# exception).
_AUDIT_SINK_ORIGIN = "audit_sink"

# Phase 4 (design D-3): the coalescing window (D-3/P4-D3, confirmed value).
_DENIAL_COALESCE_WINDOW_S = 60.0

# Phase 4 (design D-4): the bounded buffer's default capacity (implementation
# discretion per the design -- "既定 1000、実装裁量で設定可").
_DEFAULT_AUDIT_BUFFER_CAPACITY = 1000

# Phase 4 (design §7.3/§7.4; WP-2(a) fix round 2 review N-2, N-6): ONE
# constant serving two roles by construction, not by coincidence of two
# independently-set literals agreeing -- (i) `_AuditBuffer`'s own default
# minimum interval between overflow-alert-row attempts (N-2: "1 alert row
# per flush interval per process"), and (ii) the default periodic
# buffer-flush interval `r2db_api.main`'s composition-root background
# thread uses (imports this name directly rather than defining its own).
_DEFAULT_AUDIT_FLUSH_INTERVAL_S = 2.0

# Phase 4 WP-2(b) review B-1 (major, supervisor ruling 2026-09-03): the
# durable `count` column's own semantics -- "the number of occurrences this
# ONE row represents; when that number is 1, the column is absent (NULL)"
# (contract `audit.query_event_fields_note`: "present only on an event
# representing more than one coalesced occurrence, absent -- never zero or
# one -- otherwise"). Both call sites that can ever pass a real integer here
# -- `_DenialCoalescer`'s aggregate (repeat-count) row and `_AuditBuffer`'s
# overflow-alert row -- route the raw tally through this one function
# instead of writing it verbatim, so "exactly one repeat/one drop" always
# renders as an ordinary NULL-count row, never a literal `count=1` a reader
# would have to special-case.
def _coalesced_count(occurrences: int) -> int | None:
    return occurrences if occurrences >= 2 else None

# Phase 4 (design §7.4/D-4): fixed, no-interpolation log messages -- the
# design's own instruction ("可変部に実データを載せない"). A fixed string
# also means these two call sites can never accidentally leak a client-
# supplied value (application_id, secret fragment, filter content) into
# process logs.
_BUFFER_OVERFLOW_LOG_MESSAGE = "application_audit buffer overflow: events were dropped"
_ALERT_WRITE_FAILED_LOG_MESSAGE = "application_audit overflow-alert row could not be written; retrying with backoff"
_ALERT_WRITE_RECOVERED_LOG_MESSAGE = "application_audit overflow-alert row recorded; pending overflow cleared"

# Phase 4 (WP-2(a) fix round 3, review D-1): fixed, no-interpolation log
# messages for the denial-coalescer's own aggregate (repeat-count summary)
# row write path -- mirrors `_ALERT_WRITE_FAILED_LOG_MESSAGE`/`_ALERT_
# WRITE_RECOVERED_LOG_MESSAGE`'s identical state-transition-only discipline
# (N-2), applied to `_DenialCoalescer._note_aggregate_write_result`.
_COALESCE_AGGREGATE_WRITE_FAILED_LOG_MESSAGE = "application_audit coalesced-denial summary row could not be written; retrying"
_COALESCE_AGGREGATE_WRITE_RECOVERED_LOG_MESSAGE = "application_audit coalesced-denial summary row recorded; retry cleared"

# Phase 4 (design §7.4, review m-4): exponential backoff for the sticky
# overflow-alert retry, capped at 60s -- an unbounded equal-interval retry
# against a durably-failing sink would itself become a logging DoS (the
# same flow problem D-3 bounds for denials, recurring on the alert path).
# The FLOOR for this backoff is `_DEFAULT_AUDIT_FLUSH_INTERVAL_S`
# (`_AuditBuffer`'s own `alert_min_interval_s`, WP-2(a) fix round 2 review
# N-2), not a separate, smaller initial value -- no alert attempt is ever
# spaced closer together than the composition root's own flush cadence.
_ALERT_BACKOFF_CAP_S = 60.0


def _now_iso() -> str:
    """The same `occurred_at` construction `audit.AuditSink.append`/
    `audit.ControlAuditSink.append` already use -- factored out here so
    `_event`'s own buffer-class `AuditEvent` construction (below) matches
    it exactly, byte for byte."""
    return datetime.now(timezone.utc).isoformat()

# Default cell factory (design D-1 step 2): builds the existing in-memory
# `ApplicationCell`, unchanged, so every caller that does not pass
# `cell_factory` gets exactly today's behavior. A deployment that wants
# `PostgresCell` (or any other `StorageBackend`) instead passes its own
# factory -- `DataService` itself never imports `postgres.py` or references
# PostgreSQL, keeping this module backend-agnostic (D-1: "in-memory backend
# and PostgreSQL backend pass through the same validation boundary" without
# either backend leaking into this facade).
CellFactory = Callable[[str, dict[str, list[dict[str, Any]]] | None], StorageBackend]


def _default_cell_factory(application_id: str, entities: dict[str, list[dict[str, Any]]] | None) -> StorageBackend:
    return ApplicationCell(application_id, entities or {})


@dataclass(frozen=True)
class QueryPage:
    """`DataService.query_page`'s own return shape, matching
    `spec/data-service-api.v1.json`'s `QueryResult` (CCR-13 WP-4 introduced
    `items`/`next_page`; WP-5 adds `revisions`, index-aligned with `items`,
    now that `revision_preconditions` is declared `enabled`). `next_page`
    is the opaque cursor for the next page (`QueryOutcome.next_cursor`,
    `r2db_api.structured`), or `None` when this was the last page.
    """

    items: list[dict[str, Any]]
    next_page: str | None
    revisions: list[str]


@dataclass(frozen=True)
class MutationResult:
    """`DataService.mutate_result`'s own return shape, matching
    `spec/data-service-api.v1.json`'s `MutationResult`. Mirrors the
    `query`/`query_page` split (WP-4): `mutate` below stays byte-for-byte
    backward compatible (a bare `int`, the affected count) for every
    existing caller (`tests/test_foundation.py`, the in-process conformance
    adapter); this richer shape reaches only the HTTP boundary, which needs
    `assigned_addresses` to build the contract's own response. `entity` is
    never present on any element here (contract: only the cross-entity
    endpoint's own elements name their entity; this is the per-entity
    endpoint's shape).

    `committed`/`plan` (contract 1.7.0, D-4, WP-2b): before WP-2b, every
    caller reaching this point had necessarily committed (an atomic batch
    that failed partway through never returns anything, it raises), so
    `http.post_mutate` hardcoded `committed: True` itself and this
    dataclass carried no such field at all. `committed` now reports the
    real decision (`False` only for a `dry_run` that reached the "would
    succeed" decision); `plan` carries the deterministic token computed
    for it -- `DataService.mutate_result` only ever sets `plan` on a
    `dry_run` response (`None` for a real commit, D-4 (3): a real
    response's shape stays otherwise unchanged from before this version).

    `assigned_addresses` (review round F-6, `{scratchpad}/rulings-r4.md`):
    `None` exactly on a `dry_run` response -- `http.post_mutate` omits the
    key itself then, rather than carrying an empty list, matching the
    contract's "does not carry" wording. A real commit always gets a list
    (possibly empty, when the batch assigned no address), unchanged from
    before this version.
    """

    affected: int
    assigned_addresses: list[dict[str, Any]] | None
    committed: bool = True
    plan: str | None = None


class _PreCommitHook:
    """Phase 4 (design D-2/D-10): the concrete `ApplicationAuditHook`
    `DataService` builds per fail-closed-class request and hands to
    `StorageBackend.transact`/`apply_schema` as `audit_hook`. Every field
    the durable row needs (`event_class`/`request_id`/`application_id`/
    `actor_type`/`actor_id`/`role`/`operation`/`target_kind`/`target_id`)
    is already bound here at construction time -- the backend itself
    supplies none of it, only the fail-closed/buffer-class decision (D-2's
    normative rule: the confirmation choke for `transact`, unconditional
    for `apply_schema`).
    """

    __slots__ = ("_sink", "_fields")

    def __init__(self, sink: Any, fields: dict[str, Any]) -> None:
        self._sink = sink
        self._fields = fields

    def pre_commit(self) -> None:
        try:
            self._sink.append(outcome="allow", count=None, **self._fields)
        except Exception:
            fail(
                "SERVICE_UNAVAILABLE",
                "The durable audit sink could not record this operation; it was not submitted.",
                status=503,
                details={"origin": _AUDIT_SINK_ORIGIN},
            )

    def commit_failed(self) -> None:
        # D-2's error-row rule: best-effort from the response's point of
        # view (the caller fails SERVICE_UNAVAILABLE regardless of whether
        # this succeeds -- the data commit already failed either way) --
        # any exception here is swallowed, never re-raised, so a backend's
        # own `except psycopg.Error` clause always reaches its own `fail()`
        # call next, not this method's failure.
        try:
            self._sink.append(outcome="error", reason_code="commit_failed", count=None, **self._fields)
        except Exception:
            pass


class _AuditBuffer:
    """Phase 4 (design D-4/§7.3/§7.4): the bounded in-memory buffer for
    ordinary (buffer-class) data-operation success events, plus the
    overflow-alert sticky-retry state. Owns its own lock; the durable I/O
    `flush()` performs happens on the calling thread using `sink.append`/
    `append_many`, each of which opens its own connection/transaction (D-1's
    `PostgresApplicationAuditSink` docstring) -- this is what makes "a
    flush never shares a transaction with a fail-closed write" (D-4)
    automatic rather than something this class has to arrange.

    Process-local (review N-4): capacity is per-process, not per-deployment
    -- a multi-instance deployment's real bound is `capacity * <max
    instances>`, which is runbook (§9.3), not code, territory.

    WP-2(a) review M-2: §7.3 names TWO flush triggers, "periodic" and
    "threshold" -- a prior revision implemented only the periodic one (the
    composition root's background timer). `push()` now also triggers a
    flush, synchronously, in the caller's own thread, the moment the buffer
    reaches `_FLUSH_THRESHOLD_FRACTION` of capacity -- "その場で" (right
    there), the simpler of the two options §7.3's own review text
    sanctioned. Under a healthy sink this keeps the buffer far below
    capacity, so overflow becomes a genuine signal that the sink cannot
    keep up, not an artifact of the periodic timer's own interval.

    `flush()` does not unconditionally empty `self._events` before
    attempting the write -- a FAILED `append_many` leaves those events in
    place (retried by the next flush) instead of discarding them outright,
    so a transient I/O failure does not permanently destroy buffered
    evidence a later retry might still durably record.

    WP-2(a) fix round 2 review (N-1/N-2): a RETAINED event is, by
    definition, NOT lost -- it is still sitting in `self._events`, waiting
    for the next flush attempt. Counting it in `_dropped_total` (a prior
    revision did, via `+= len(pending)` on every failed `append_many`) both
    mislabels "not yet flushed" as "dropped" (N-1: the same event, retried
    and failing repeatedly, gets counted again and again) AND -- combined
    with a failed flush marking the alert pending -- lets a single
    threshold-triggered flush failure emit its own alert-row *attempt* on
    every subsequent buffer-class request (N-2: a `push()` on every
    request, no bound on request rate). `_dropped_total` now increments
    ONLY where an event is actually, irrevocably discarded: `push()`'s own
    eviction branch (capacity reached, oldest event evicted to make room).
    A failed `append_many` retains its batch and adjusts NEITHER
    `_dropped_total` NOR `_alert_pending` on its own -- there is nothing
    new to alert about merely because a retry is still pending, and the
    ALREADY-pending alert (if any, from a genuine eviction) is independently
    rate-limited below regardless of how often `flush()` itself is retried.

    Alert-row EMISSION RATE is bounded independently of eviction/flush-retry
    rate (N-2): `_alert_min_interval_s` (constructor parameter, matching the
    composition root's own periodic-flush interval, default 2.0s) is a
    hard floor under `_alert_backoff_s` -- no two alert attempts are ever
    less than `_alert_min_interval_s` apart, "1 alert row attempt per flush
    interval per process" even while eviction is ongoing. The backoff is
    keyed to whether the underlying buffer FLUSH is currently succeeding
    (`_flush_currently_failing`, updated by every `flush()` call), not to
    whether the alert row's own INSERT succeeded: an alert row can itself
    write successfully while the buffer flush keeps failing (evidence keeps
    being evicted) -- in that case the backoff still grows, so a healthy
    alert-write path does not let a broken buffer-flush path re-trigger a
    fresh alert attempt every `_alert_min_interval_s` forever at the
    fastest allowed rate; it backs off further, same as an outright alert
    failure. The backoff only resets to the floor once the buffer flush
    itself is observed healthy again.
    """

    # Review M-2's own suggested value ("k は 0.8 等").
    _FLUSH_THRESHOLD_FRACTION = 0.8

    def __init__(self, sink: Any, *, capacity: int, clock: Callable[[], float], alert_min_interval_s: float = _DEFAULT_AUDIT_FLUSH_INTERVAL_S) -> None:
        self._sink = sink
        self._capacity = max(1, capacity)
        self._flush_threshold = max(1, int(self._capacity * self._FLUSH_THRESHOLD_FRACTION))
        self._clock = clock
        self._alert_min_interval_s = max(0.0, alert_min_interval_s)
        self._lock = threading.Lock()
        self._events: list[AuditEvent] = []
        self._dropped_total = 0
        self._alert_pending = False
        self._alert_next_retry_at = 0.0
        self._alert_backoff_s = self._alert_min_interval_s
        self._alert_failure_logged = False
        # N-2: tracks whether the most recent `flush()` attempt's own
        # `append_many` succeeded or failed -- independent of the alert
        # row's own write outcome, and read by `_retry_alert` to decide
        # whether the backoff may reset.
        self._flush_currently_failing = False

    def push(self, event: AuditEvent) -> None:
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
            # event is actually, irrevocably evicted (N-1: not merely
            # retained-for-retry), since each eviction is itself a new,
            # permanent loss.
            _logger.error(_BUFFER_OVERFLOW_LOG_MESSAGE)
        if trigger_flush:
            # M-2: threshold flush -- see class docstring. Outside the lock
            # (already released above), on the calling thread.
            self.flush()

    def pending_count(self) -> int:
        with self._lock:
            return len(self._events)

    def flush(self) -> None:
        """D-4/§7.3: called on demand (tests, the adapter privilege hook),
        periodically (composition root), and now also from `push()` at the
        threshold (M-2). Writes the current buffer contents as one batch,
        then attempts the sticky overflow-alert retry -- always in that
        order, always on a connection/transaction of its own. A failed
        batch write leaves the events in place for the next attempt
        (retained, not counted as dropped -- N-1) rather than discarding
        them or alerting on its own.

        WP-3(a) review B-2 (reentrancy): the periodic-flush thread
        (composition root) and a request-path threshold flush (`push()`,
        M-2 above) can call this method concurrently on the SAME buffer.
        `pending` is therefore SWAPPED OUT of `self._events` under a
        single lock acquisition (not merely copied) -- this, not a
        separate "flush in progress" flag, is what makes two concurrent
        `flush()` calls durably write disjoint (usually one full, one
        empty) sets of events instead of both durably writing the SAME
        events (the double-row bug this review found, reproduced verbatim
        by `test_concurrent_periodic_and_threshold_flush_never_double_
        writes_pending_events`). A concurrent call that finds `self.
        _events` already emptied by the swap simply has nothing to flush
        and returns without ever touching the sink -- it is not blocked or
        serialized behind the in-flight I/O, so this stays lock-free
        across the network round trip exactly as before.

        A failed `append_many` puts `pending` BACK -- prepended, so it
        precedes (in flush order) anything pushed while this I/O was in
        flight -- preserving N-1's retain discipline (retained events are
        never counted as dropped) and `_dropped_total`'s accuracy (a
        retained batch is not itself a loss) exactly as the prior
        read-then-delete version did.

        WP-3(a) review B-1 (blocker, on the B-2 fix above): while this
        method holds `pending` outside `self._events`, `push()` sees an
        empty (or merely in-flight-refilled) buffer and does not evict --
        capacity is enforced only against whatever is currently sitting in
        `self._events`. A naive unconditional `pending + self._events`
        restore on failure can therefore exceed `_capacity` (up to
        `len(pending)` extra), and because the surviving overflow is never
        itself re-evicted by a later `push()` (each `push()` only ever
        evicts ONE item, the one IT just added), a sink outage would let
        the buffer grow WITHOUT BOUND across repeated failed flushes --
        breaking D-4's "bounded in-memory buffer" and D-1 review M-5's
        capacity-side availability argument, and doing so *silently*: no
        `push()` eviction fires during this growth, so `_dropped_total`
        never increments and the overflow alert (D-4) never appears even
        though evidence is unboundedly accumulating in memory. So the
        restore truncates back down to `_capacity`, dropping from the
        FRONT (oldest first, matching `push()`'s own `pop(0)` FIFO
        discipline) -- and, exactly like a genuine `push()`-path eviction,
        counts only what was ACTUALLY, irrevocably discarded here (never
        the merely-retried remainder) in `_dropped_total`, sets
        `_alert_pending`, and logs the same fixed overflow message.
        """
        with self._lock:
            pending = self._events
            self._events = []
        if pending:
            try:
                self._sink.append_many(pending)
            except Exception:
                truncated = 0
                with self._lock:
                    self._flush_currently_failing = True
                    # N-1/N-2: put the un-written batch back rather than
                    # discarding it -- it is retried by the next flush, not
                    # counted in `_dropped_total` (nothing has actually been
                    # lost) and nothing new to alert or log about on this
                    # path alone. Prepended ahead of anything a concurrent
                    # `push()` added to `self._events` while this I/O was in
                    # flight, so flush order still matches arrival order.
                    self._events = pending + self._events
                    # B-1: re-impose the capacity bound `push()` could not
                    # enforce while this batch was held outside
                    # `self._events` -- drop the oldest overflow, exactly
                    # the FIFO discipline `push()`'s own eviction branch
                    # uses, and count ONLY this genuine, irrevocable loss
                    # (the rest is still a retained retry, not a drop).
                    overflow = len(self._events) - self._capacity
                    if overflow > 0:
                        del self._events[:overflow]
                        truncated = overflow
                        self._dropped_total += truncated
                        self._alert_pending = True
                if truncated:
                    _logger.error(_BUFFER_OVERFLOW_LOG_MESSAGE)
                # `push()`'s own eviction branch is the only OTHER source
                # of genuine, irrevocable loss.
            else:
                with self._lock:
                    # P4-D15 (WP-B2): `_flush_currently_failing` clears
                    # unconditionally on ANY successful `append_many` --
                    # not gated on `self._events` being empty. Under
                    # sustained push load the buffer is rarely empty even
                    # once the sink has genuinely recovered (M-2's
                    # threshold flush keeps refilling it), so the prior
                    # "only when empty" gate left the flag -- and the
                    # alert backoff it feeds, see `_retry_alert` below --
                    # stuck at the sink-broken state long after recovery.
                    #
                    # Completion-order semantics absorb the WP-3(a) review
                    # m-1 race this replaces: a DIFFERENT, still-failing
                    # concurrent flush (disjoint batch, per the B-2 swap
                    # above) sets this back to True in its own failure
                    # branch whenever IT completes -- whichever flush
                    # completes LAST wins, exactly as with any other
                    # unsynchronized shared-state update. A brief window
                    # where this reads False while that concurrent failure
                    # is still in flight does not weaken the alert-rate
                    # guarantee: `_retry_alert`'s own `alert_min_interval_s`
                    # floor on `alert_next_retry_at` still bounds attempts
                    # to at most one per flush interval regardless of how
                    # many times this flag flips in between (§7.4's "at
                    # most 1 alert row per flush interval" is enforced by
                    # that floor, not by this flag).
                    #
                    # Accepted tradeoff (P4-D15): if the sink is FLAPPING
                    # (success and failure completing alternately), the
                    # backoff resets to the floor on every success, so the
                    # observed alert-row rate can rise from "stuck at the
                    # 60s backoff cap" up to "one per alert_min_interval_s"
                    # (2.0s by default). This is intentional -- evidence
                    # (`count`) reaches the durable table sooner from a
                    # partially-working sink, and the declared bound itself
                    # (at most 1 row per flush interval) still holds; only
                    # the realized rate moves toward that bound instead of
                    # sitting far under it.
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
                event_class="security_control_failure",
                request_id=str(uuid.uuid4()),
                application_id=None,
                actor_type="system",
                actor_id=None,
                role=None,
                operation="audit_buffer",
                target_kind="audit_sink",
                outcome="deny",
                reason_code="audit_buffer_overflow",
                target_id=None,
                count=_coalesced_count(count),
            )
        except Exception:
            with self._lock:
                self._alert_backoff_s = min(_ALERT_BACKOFF_CAP_S, max(self._alert_min_interval_s, self._alert_backoff_s * 2))
                self._alert_next_retry_at = self._clock() + self._alert_backoff_s
                self._alert_failure_logged = True
            # §7.4/review m-4: this branch is only ever reached once the
            # backoff interval has already elapsed (the early return above
            # enforces that), so logging unconditionally here already
            # matches "first attempt, then once per backoff interval" --
            # no separate first-attempt bookkeeping is needed.
            _logger.error(_ALERT_WRITE_FAILED_LOG_MESSAGE)
            return
        with self._lock:
            # Review m-1: SUBTRACT exactly the `count` this alert row just
            # reported, never blindly reset to 0 -- more drops can have
            # accumulated (a concurrent eviction) between reading `count`
            # above and this INSERT completing; resetting to 0
            # unconditionally would silently lose track of those,
            # understating a later alert row's own `count`. If drops
            # remain, the alert stays pending (and will fire again once
            # the backoff/rate-limit conditions allow) for the remainder.
            self._dropped_total -= count
            if self._dropped_total <= 0:
                self._dropped_total = 0
                self._alert_pending = False
            # N-2: the backoff is keyed to whether the BUFFER FLUSH is
            # currently failing, not to whether this alert row's own
            # INSERT just succeeded. If the flush is still failing (more
            # evictions can still be coming), keep backing off -- exactly
            # like an alert-write failure would -- so a healthy alert path
            # cannot be used to re-trigger a fresh attempt every single
            # `_alert_min_interval_s` for as long as the underlying sink
            # stays broken. Only reset to the floor once the flush itself
            # is observed healthy.
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
    class denials. Process-local (review N-4: a shared store is never
    consulted, so the same key can legitimately produce one row per
    process/instance, not one row per deployment).

    Keyed by `(application_id, actor_id or "unknown", operation,
    reason_code)`, window `W` seconds: the first occurrence of a new key
    writes a durable row synchronously (fail-closed -- `route()` raises
    `SERVICE_UNAVAILABLE` if that write fails); every occurrence after that,
    within the same window, only increments an in-memory counter. When the
    window is later found expired (lazily, on the next `route()` call for
    THAT key, or explicitly via `flush_expired()`/`flush_all()`), a second
    row -- carrying the repeat count in `count` -- is written for that key,
    if there were any repeats at all; zero-repeat windows are simply
    dropped with no second write.

    WP-2(a) review B-2 (fail-closed correctness): a same-key concurrent
    `route()` call must never observe "a window already exists" (and take
    the fast `repeat_count += 1` path) before the FIRST occurrence's own
    durable INSERT has actually resolved -- otherwise a fail-closed denial
    flood racing a sink outage could return an ordinary-looking denial
    response, never even attempting its own durable write, while the
    window's supposed first row was never actually recorded (§9.2 property
    1's fail-closed guarantee would then hold only single-threaded).

    WP-2(a) fix round 2, supervisor ruling on review m-2: PER-KEY locking,
    not a single process-wide lock held across I/O. `self._lock` (process-
    wide) protects ONLY `self._windows`/`self._key_locks`/`self._key_lock_
    refcount` dict structure -- it is acquired only for brief, non-blocking
    dict reads/writes, NEVER across a durable INSERT. Each coalescing key
    gets its own `threading.Lock` (`self._key_locks`, created on first use),
    held across that ONE key's own first-occurrence INSERT (and its own
    expired-window aggregate flush, if one is due) -- this is what still
    gives B-2 its correctness guarantee (a same-key concurrent caller
    blocks on that key's own lock until the in-flight attempt resolves)
    WITHOUT serializing unrelated keys against each other. The periodic
    sweep (`flush_expired()`/`flush_all()`) collects expired keys/state
    under the process lock and performs each one's INSERT under that SAME
    key's own per-key lock (never the process lock) -- this is what lets a
    concurrent `route()` call for that key correctly serialize against the
    sweep too (WP-2(a) fix round 3, review D-1 -- see `_requeue_failed_
    aggregate`'s own docstring for why this matters).

    WP-2(a) fix round 3, review D-1 (major): a failed aggregate-row write
    (the repeat-count summary row for an expired window) must never
    silently discard that repeat count -- see `_requeue_failed_aggregate`.
    A round-2 revision deleted the due window from `self._windows` before
    attempting its write and simply dropped it on failure (`except:
    continue`/`pass`), reasoning that re-inserting after releasing the
    process lock would race a concurrent `route()` for the same key; that
    race is real, but per-key locking (already required for B-2/m-2) is
    exactly what closes it -- the requeue now happens under the SAME key's
    lock the write attempt itself ran under, so no concurrent `route()`
    call for that key can be in flight at that moment.

    Review D-2 (minor): `self._key_locks` entries are pruned via reference
    counting (`_acquire_key_lock`/`_release_key_lock_ref`) once a key has
    no outstanding lock user AND no window left for it -- never while a
    lock might still be in use (which would let a fresh `route()` call
    silently start using a NEW, different `Lock` object for the same key,
    defeating serialization entirely).
    """

    def __init__(self, sink: Any, *, window_s: float, clock: Callable[[], float]) -> None:
        self._sink = sink
        self._window_s = window_s
        self._clock = clock
        self._lock = threading.Lock()
        self._windows: dict[tuple[Any, ...], dict[str, Any]] = {}
        self._key_locks: dict[tuple[Any, ...], threading.Lock] = {}
        self._key_lock_refcount: dict[tuple[Any, ...], int] = {}
        # Review D-1: tracks whether the MOST RECENT aggregate-row write
        # attempt (from any key) failed -- a single, process-wide flag,
        # deliberately mirroring `_AuditBuffer`'s own N-2 state-transition
        # logging discipline (log only on failing<->healthy transitions,
        # never once per attempt).
        self._aggregate_write_failing = False

    def _acquire_key_lock(self, key: tuple[Any, ...]) -> threading.Lock:
        with self._lock:
            lock = self._key_locks.setdefault(key, threading.Lock())
            self._key_lock_refcount[key] = self._key_lock_refcount.get(key, 0) + 1
            return lock

    def _release_key_lock_ref(self, key: tuple[Any, ...]) -> None:
        """Review D-2: only prunes `self._key_locks[key]` when this is the
        LAST outstanding reference (refcount reaches 0) AND no window
        remains for the key -- see class docstring for why both conditions
        are required for this to be safe."""
        with self._lock:
            remaining = self._key_lock_refcount.get(key, 1) - 1
            if remaining <= 0:
                self._key_lock_refcount.pop(key, None)
                if key not in self._windows:
                    self._key_locks.pop(key, None)
            else:
                self._key_lock_refcount[key] = remaining

    def _requeue_failed_aggregate(self, key: tuple[Any, ...], state: dict[str, Any]) -> None:
        """WP-2(a) fix round 3, review D-1: called only while holding this
        KEY's OWN `key_lock` (both call sites below), right after its
        aggregate-row write attempt raised -- puts `state["repeat_count"]`
        back where a future flush (periodic, explicit, shutdown, or the
        very next `route()` call for this same key) will retry it, instead
        of discarding it. Two cases, both safe specifically BECAUSE the
        caller holds this key's lock (no concurrent `route()`/sweep call
        for the SAME key can be observing or mutating `self._windows[key]`
        at this exact moment -- see class docstring):

        - A fresh window has already been opened for this key by a
          concurrent `route()` call in the meantime (its own first-
          occurrence row is already durable) -- merge the failed repeat
          count into it rather than overwriting.
        - No window exists for this key right now -- re-register one
          carrying just the failed repeat count, with the SAME (already
          past) `window_start` it had, so it reads as immediately "due"
          again for both a future sweep and the next `route()` call for
          this key (which flushes an expired window inline before opening
          a fresh one, the same code path that calls this method).
        """
        with self._lock:
            existing = self._windows.get(key)
            if existing is not None:
                existing["repeat_count"] += state["repeat_count"]
            else:
                self._windows[key] = state

    def _note_aggregate_write_result(self, succeeded: bool) -> None:
        """Review D-1: fixed-message `logging.error`, only on a failing<->
        healthy state TRANSITION (N-2's own established discipline) -- not
        once per attempt, which would reproduce the exact logging-DoS risk
        N-2 already closed for the buffer-overflow alert path."""
        log_message: str | None = None
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
                    # This key's own window had already expired (nobody had
                    # routed it since) -- flush its repeat-summary row
                    # first, still under this key's own lock.
                    try:
                        self._sink.append(count=_coalesced_count(expired_state["repeat_count"]), **expired_state["fields"])
                    except Exception:
                        self._requeue_failed_aggregate(key, expired_state)
                        self._note_aggregate_write_result(False)
                    else:
                        self._note_aggregate_write_result(True)
                # New (or freshly-expired-and-reopened) window: the
                # synchronous, fail-closed first-occurrence INSERT.
                try:
                    self._sink.append(count=None, **fields)
                except Exception:
                    fail(
                        "SERVICE_UNAVAILABLE",
                        "The durable audit sink could not record this denial; it was refused.",
                        status=503,
                        details={"origin": _AUDIT_SINK_ORIGIN},
                    )
                with self._lock:
                    # WP-2(a) fix round 4 (spot-check, major): if the
                    # inline expired-window flush just above failed, it
                    # already requeued the still-unwritten repeat count
                    # into `self._windows[key]` (via `_requeue_failed_
                    # aggregate`, under this SAME key_lock -- no other
                    # thread can have touched this key's entry since). A
                    # prior revision overwrote that unconditionally here,
                    # silently discarding the requeued count the moment the
                    # aggregate write failed but the very next first-
                    # occurrence write succeeded. Merge instead: carry the
                    # requeued `repeat_count` forward into the fresh
                    # window rather than resetting it to 0.
                    requeued = self._windows.get(key)
                    carried_repeat_count = requeued["repeat_count"] if requeued is not None else 0
                    self._windows[key] = {"window_start": now, "repeat_count": carried_repeat_count, "fields": fields}
        finally:
            self._release_key_lock_ref(key)

    def flush_expired(self) -> None:
        """Periodic/explicit sweep: only windows whose `window_s` has
        actually elapsed. Collects them under the process lock (a brief,
        non-blocking dict operation), then performs each key's own INSERT
        under that SAME key's own per-key lock (m-2/D-1) -- never the
        process lock, and never unprotected against a concurrent `route()`
        call for the same key."""
        now = self._clock()
        self._flush_keys(lambda key, state: now - state["window_start"] >= self._window_s)

    def flush_all(self) -> None:
        """WP-2(a) fix round 2, review N-4: force EVERY currently-open
        window to be flushed, expired or not -- used only at graceful
        shutdown. Once this process is about to stop, there is no "wait
        for the window to naturally expire" future left; treating every
        window as due now is what keeps a shutdown from silently
        discarding an in-progress window's accumulated repeat count (D-3
        only ever sanctions losing counts to an actual crash, never to an
        orderly stop)."""
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
                        self._sink.append(count=_coalesced_count(state["repeat_count"]), **state["fields"])
                    except Exception:
                        # Review D-1: never silently drop this repeat count
                        # -- put it back where a future attempt (this same
                        # sweep's own next pass, a later explicit/periodic
                        # flush, or the next `route()` call for this key)
                        # will retry it. Safe specifically because this
                        # happens under THIS key's own lock (no concurrent
                        # `route()`/sweep call for the SAME key can be
                        # touching `self._windows[key]` right now).
                        self._requeue_failed_aggregate(key, state)
                        self._note_aggregate_write_result(False)
                    else:
                        self._note_aggregate_write_result(True)
            finally:
                self._release_key_lock_ref(key)

class DataService:
    """Public application facade; control state is deliberately private."""

    def __init__(self, credentials: CredentialStore, limits: ResourceLimits | None = None, topology: AuthorityTopology | None = None, audit: AuditSink | None = None, initial_cells: dict[str, StorageBackend] | None = None, clock: Callable[[], float] | None = None, cell_factory: CellFactory | None = None, control_plane_status: str = "unavailable", durable_audit: Any | None = None, audit_buffer_capacity: int = _DEFAULT_AUDIT_BUFFER_CAPACITY, denial_coalesce_window_s: float = _DENIAL_COALESCE_WINDOW_S, audit_alert_min_interval_s: float = _DEFAULT_AUDIT_FLUSH_INTERVAL_S, surfaces: dict[str, Any] | None = None) -> None:
        # R-9 (CCR-14 WP-5, design docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md
        # §1: "capability 申告は環境変数由来で composition root 注入"):
        # whether this application-plane process' own `capabilities()`
        # declares `control_plane: enabled` is a *deployer* fact this class
        # cannot know on its own (a separated `/control/v1` deployment, the
        # default, means the application-plane process has no idea whether a
        # control-plane process is running anywhere at all) -- it is
        # constructor-injected, defaulting to the safe, honest `unavailable`
        # so nothing short of an explicit composition-root decision
        # (`main.py`, reading `R2DB_CONTROL_PLANE_STATUS`) ever declares
        # `enabled`. Validated here too (not only at `main.py`'s env-parsing
        # boundary) so any other caller constructing a `DataService` directly
        # (this repository's own tests, the WP-5 in-process conformance
        # adapter) gets the same fail-loud guard against a typo'd status
        # string, rather than silently publishing an invalid capability
        # value.
        if control_plane_status not in {"enabled", "unavailable"}:
            raise ValueError("control_plane_status must be 'enabled' or 'unavailable'")
        self._control_plane_status = control_plane_status
        # Phase 6 WP-2 (design D-2): `surfaces` is constructor-injected,
        # same "deployer-declared, not derived" discipline as `control_
        # plane_status` immediately above -- `main.py` (the real
        # composition root) is the one caller that validates the two
        # `R2DB_*_BASE_URL` environment variables' SHAPE at startup and
        # assembles this dict from them; this class only ever echoes
        # whatever it was given, verbatim, in `capabilities()` below. `None`
        # (the default -- every pre-WP-2 caller, including this
        # repository's own unit tests that construct `DataService` directly
        # without opting in) omits the `surfaces` key from the response
        # entirely, never a `"surfaces": None` value (contract `Capability
        # Document.surfaces` is an optional key, not a nullable one).
        self._surfaces = surfaces
        self._credentials = credentials
        self.limits = limits or ResourceLimits()
        self.topology = topology or AuthorityTopology()
        self._audit = audit or AuditSink()
        # Phase 4 (design PHASE4_DURABLE_AUDIT_SINK_V1.md D-1/D-10): the
        # durable-designated sink -- `ApplicationAuditSink` (in-memory,
        # fault-injectable) by default, or a caller-supplied
        # `PostgresApplicationAuditSink` (`credential_store.py`, wired by
        # `main.py`'s composition root). `self._audit` above is untouched
        # and stays the sole recorder for D-3's non-durable denial classes
        # (everything outside `_DURABLE_DENIAL_CODES`'s inclusion list,
        # J-2 -- D-10's own instruction) -- this is a SEPARATE sink, not a
        # replacement.
        self._durable_audit = durable_audit if durable_audit is not None else ApplicationAuditSink()
        self._audit_buffer = _AuditBuffer(self._durable_audit, capacity=audit_buffer_capacity, clock=clock or time.monotonic, alert_min_interval_s=audit_alert_min_interval_s)
        self._denial_coalescer = _DenialCoalescer(self._durable_audit, window_s=denial_coalesce_window_s, clock=clock or time.monotonic)
        self._cell_factory: CellFactory = cell_factory or _default_cell_factory
        self._cells: dict[str, StorageBackend] = dict(initial_cells or {})
        self._disabled_apps: set[str] = set()
        self._active = 0
        self._active_lock = threading.Lock()
        self._rate_lock = threading.Lock()
        self._rate_windows: dict[str, list[float]] = {}
        self._clock = clock or time.monotonic
        self.topology.validate()

    def authenticate(self, secret: str | None, *, request_id: str | None = None) -> AuthContext:
        rid = request_id or str(uuid.uuid4())
        try:
            context = self._credentials.authenticate(secret)
            if context.application_id in self._disabled_apps:
                fail("APPLICATION_DISABLED", "Application is disabled.", status=403)
            self._event(context, operation="authenticate", outcome="allow", target_kind="application", event_class="authentication", request_id=rid)
            return context
        except FoundationError as exc:
            # Phase 4 (design D-2/D-3): the legacy in-memory `self._audit`
            # append is unchanged (pre-Phase-4 behaviour, this repository's
            # own tests read it back via `ControlAuthority.audit_events()`)
            # -- `_denial_event` below ADDS the durable/coalesced dispatch
            # every other public method's `except FoundationError` reaches
            # through `_event`'s own deny branch; this call site cannot use
            # `_event` itself because authentication has not yet resolved a
            # `canonical`/`AuthContext` to build one from.
            self._audit.append(event_class="authentication_denial", request_id=rid, application_id=None, actor_type="unknown", actor_id=None, role=None, operation="authenticate", target_kind="application", outcome="deny", reason_code=exc.code)
            self._denial_event(
                event_class="authentication_denial", request_id=rid, application_id=None,
                actor_type="unknown", actor_id=None, role=None, operation="authenticate",
                target_kind="application", reason_code=exc.code, target_id=None, details=exc.details,
            )
            raise

    def capabilities(self, context: AuthContext) -> dict[str, Any]:
        with self._slot(context) as canonical:
            # CCR-13 WP-5b: the WP-2-through-WP-5 provisional gate (design
            # R2DB_CCR13_STORAGE_V1.md §3) is removed in this same commit
            # (see `query`/`mutate`/`schema`/`catalog` below) -- this
            # declaration update is what makes that removal honest rather
            # than a new C-12 "declared unavailable, executes anyway" gap.
            # Contract 1.7.0 (D-2 (5), WP-2a): `alter_field` joins the
            # developer-only schema-operation set -- `R-2` constraint
            # declarations are enforced now (see `constraint_declarations`
            # below), so it is no longer accurate to list it under
            # `unsupported`.
            schema_ops = ["create_entity", "add_field", "alter_field", "create_index", "drop_index", "drop_entity"] if canonical.role == "developer" else []
            document: dict[str, Any] = {
                # Phase 4 WP-2(b) (P4-D4, contract `versioning.
                # version_binding`), flipped to 1.5.0 in phase 5 WP-2,
                # flipped to 1.6.0 in phase 6 WP-2 (design docs/design/
                # PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md, subordinate
                # ruling 11): unconditional -- every deployment of this
                # data-plane host declares 1.6.0 now, whether or not
                # the CONTROL host alongside it has AUDIT DSN configured
                # (`audit_query` stays `unavailable` right below,
                # unchanged: this host never provides it, D-5's own
                # "declaration = real behavior" rule). This same commit
                # ships every 1.6.0 behavioral obligation this host owns
                # (locator-form credentials, `surfaces`, `field_types`) --
                # the flip is never ahead of the behavior it declares.
                "contract_version": "1.6.0",
                "capabilities": {
                    "structured_query": {"status": "enabled", "operators": ["eq", "ne", "lt", "lte", "gt", "gte", "in", "contains", "matches", "is_null"]},
                    # Contract 1.1.0 (CCR-13, `structured_operations.
                    # upsert`): `upsert`'s existence test is the entity's
                    # own declared domain uniqueness (`EntityDescriptor.
                    # unique_keys`, `application_catalog` below) -- an
                    # entity with no declared uniqueness key still refuses
                    # `upsert` with `CAPABILITY_UNSUPPORTED` (structured.py::
                    # bind_mutation/_apply_upsert), but that is a per-entity
                    # condition the catalog itself communicates, not a
                    # service-wide gap `atomic_mutation` needs to qualify.
                    "atomic_mutation": {"status": "enabled", "operations": ["insert", "update", "upsert", "delete"]},
                    "application_catalog": {"status": "enabled"},
                    "schema_operations": {"status": "partial", "operations": schema_ops, "unsupported": ["jobs"]},
                    "audit_query": {"status": "unavailable", "authority": "control_or_audit"},
                    "best_effort_transactions": {"status": "unavailable"},
                    "idempotency": {"status": "unavailable"},
                    "revision_preconditions": {"status": "enabled"},
                    "row_addressability": {"status": "enabled"},
                    # `cross_entity_mutation` needs the new `POST /v1/data/
                    # mutations` endpoint (stubbed in `http.py` as
                    # CAPABILITY_UNSUPPORTED, not executable), so it stays
                    # `unavailable` here: it has no executable operation at
                    # all. (`control_plane`, immediately below, is NOT in
                    # the same position any more: CCR-14 shipped the
                    # `/control/v1` surface as a separate process, and its
                    # status is the deployer's own R-9 declaration -- the
                    # pre-CCR-14 wording that once grouped the two as "both
                    # remain unavailable" was corrected 2026-09-05.)
                    "cross_entity_mutation": {"status": "unavailable"},
                    # R-9: reflects this instance's own constructor-injected
                    # deployer declaration -- never hardcoded (see __init__'s
                    # comment on this field).
                    "control_plane": {"status": self._control_plane_status},
                    # Contract 1.7.0 (subordinate ruling 12, D-1 (3)): three
                    # new capabilities, honestly declared `unavailable`
                    # until each one's own capability WP flips it, in the
                    # SAME commit as the provisional gate that rejects
                    # every field it governs (`schema`/`mutate_result`/
                    # `_query_outcome` above, `http.py`'s `post_mutate`/
                    # `post_query`) -- P-3 (宣言と挙動は同一コミット).
                    #
                    # WP-2a: `constraint_declarations` is `enabled` --
                    # `field_constraints`/`enum`/`nullable`/`alter_field`
                    # are no longer in `_PROVISIONAL_UNSUPPORTED_SCHEMA_
                    # FIELDS` (removed in this same commit) and are now
                    # enforced (`structured.py`/`postgres.py`).
                    "constraint_declarations": {"status": "enabled"},
                    # WP-2b: `dry_run` is `enabled` -- `dry_run`/`plan` are
                    # no longer in `_PROVISIONAL_UNSUPPORTED_SCHEMA_FIELDS`
                    # (schema side) and `mutate_result`/`_mutate_outcome`
                    # (mutation side) no longer refuse them outright, in
                    # this same commit as `structured.py`/`postgres.py`'s
                    # own real dry_run/plan enforcement (D-4). WP-2d
                    # (`request_budget`) flips its own entry the same way,
                    # in its own commit.
                    "dry_run": {"status": "enabled"},
                    "request_budget": {"status": "unavailable"},
                },
                "limits": self.limits.as_dict(),
                "limit_enforcement": {name: "reference_wall_clock" if name == "execution_ms" else "enforced" for name in self.limits.as_dict()},
                # `_check()` (called by `_slot()` above) re-validates
                # credential/application authorization state on every
                # single application-plane operation; there is no cache, so
                # revoke/disable/state-unavailable propagation is
                # synchronous (see also the identical reasoning in
                # `conformance/conformance_adapter_r2db.py`'s
                # `propagation_bound_ms()`).
                "authorization_propagation_bound_ms": 0,
                "application_scope": canonical.application_id,
                "role": canonical.role
            }
            # Phase 6 WP-2 (design D-2): `surfaces` is an optional key --
            # present only when this instance was constructed with one
            # (`__init__`'s own comment on `self._surfaces`). Never a
            # `"surfaces": None` entry.
            if self._surfaces is not None:
                document["surfaces"] = self._surfaces
            return document

    def query(self, context: AuthContext, entity: str, *, select: list[str], where: list[dict[str, Any]] | None = None, page_size: int = 100, order_by: list[dict[str, Any]] | None = None, cursor: str | None = None, request_id: str | None = None) -> list[dict[str, Any]]:
        """Plain-item-list form, unchanged in shape since before CCR-13
        (every existing caller -- `tests/test_foundation.py`, the in-process
        conformance adapter -- keeps working against exactly this return
        type). `order_by`/`cursor` (CCR-13 WP-4) are accepted here too (so
        this method alone is enough to exercise/test them against the
        facade), but the pagination continuation itself only reaches a
        caller through `query_page` below, which `http.post_query` uses.
        """
        return list(self._query_outcome(context, entity, select=select, where=where, page_size=page_size, order_by=order_by, cursor=cursor, request_id=request_id).items)

    def query_page(self, context: AuthContext, entity: str, *, select: list[str], where: list[dict[str, Any]] | None = None, page_size: int = 100, order_by: list[dict[str, Any]] | None = None, cursor: str | None = None, request_id: str | None = None, budget: dict[str, int] | None = None) -> "QueryPage":
        """The HTTP-facing shape (`{items, next_page, revisions}`,
        `spec/data-service-api.v1.json`'s `QueryResult`) -- used by `http.
        post_query` instead of `query` above, since building a real
        `next_page`/`revisions` needs `QueryOutcome.next_cursor`/
        `.revisions`, which the plain-list `query()` deliberately does not
        expose (kept byte-for-byte backward compatible with every pre-
        CCR-13 caller). `revisions` is always index-aligned with `items`:
        `revision_preconditions` is declared `enabled`, and every entity
        both cells provision is `mutable`, so a query response always
        carries revisions (R-4).

        `budget` (contract 1.7.0, `QueryRequest.budget`): provisional gate
        only (docs/work-orders/WORK_ORDER_PHASE9_CONTRACT_170_V1.md §2 WP-1
        (9)) -- this foundation declares `request_budget` `unavailable`, so
        any caller-supplied `budget` is refused outright rather than
        silently accepted-and-ignored, matching this method's own existing
        `idempotency_key`-style present-denial precedent
        (`http.py:post_mutate`). WP-2d gives this parameter real narrowing
        semantics in the same commit it flips `request_budget` to `enabled`.
        """
        outcome = self._query_outcome(context, entity, select=select, where=where, page_size=page_size, order_by=order_by, cursor=cursor, request_id=request_id, budget=budget)
        return QueryPage(items=list(outcome.items), next_page=outcome.next_cursor, revisions=list(outcome.revisions or []))

    def _query_outcome(self, context: AuthContext, entity: str, *, select: list[str], where: list[dict[str, Any]] | None, page_size: int, order_by: list[dict[str, Any]] | None, cursor: str | None, request_id: str | None, budget: dict[str, int] | None = None):
        rid = request_id or str(uuid.uuid4())
        if budget is not None:
            # Provisional gate (contract 1.7.0 D-1 (3)): `request_budget` is
            # declared `unavailable` (service.py's `capabilities()`) -- this
            # fires before the rate/concurrency slot is entered, mirroring
            # the existing `idempotency_key` present-denial's unaudited,
            # pre-slot placement (`http.py:post_mutate`) rather than the
            # slot-scoped `VALIDATION_FAILED`s below.
            fail(
                "CAPABILITY_UNSUPPORTED",
                "Request budgets are not supported by this foundation.",
                details={"violated_declaration": "capability", "field": "budget"},
            )
        try:
            with self._slot(context) as canonical:
                if not isinstance(select, list) or not isinstance(page_size, int) or isinstance(page_size, bool):
                    fail("VALIDATION_FAILED", "Projection and page size have invalid types.")
                if where is not None and not isinstance(where, list):
                    fail("VALIDATION_FAILED", "Filter must be a list.")
                if order_by is not None and not isinstance(order_by, list):
                    fail("VALIDATION_FAILED", "order_by must be a list.")
                if cursor is not None and not isinstance(cursor, str):
                    fail("VALIDATION_FAILED", "Cursor must be a string.")
                request = {"entity": entity, "select": select, "where": where or [], "page_size": page_size, "order_by": order_by or [], "cursor": cursor}
                self.limits.check_request(request)
                self.limits.check_depth(request)
                predicates = [parse_predicate(item) for item in (where or [])]
                deadline = self._clock() + self.limits.execution_ms / 1000
                outcome = self._cells[canonical.application_id].query(
                    entity, select=select, where=predicates, page_size=page_size, order_by=order_by, cursor=cursor, limits=self.limits, deadline=deadline, clock=self._clock
                )
                # Phase 4 (design D-2 §7.3): `query` never passes through
                # the confirmation choke -- always buffer-class.
                self._event(canonical, operation="query", outcome="allow", target_kind="entity", event_class="data_operation", request_id=rid)
                return outcome
        except FoundationError as exc:
            self._event(context, operation="query", outcome="deny", target_kind="entity", reason_code=exc.code, event_class="authorization_denial", request_id=rid, details=exc.details)
            raise

    def mutate(self, context: AuthContext, entity: str, operations: list[dict[str, Any]], *, transaction: str = "atomic", request_id: str | None = None) -> int:
        """Plain affected-count form, unchanged in shape since before
        CCR-13 (every existing caller -- `tests/test_foundation.py`, the
        in-process conformance adapter -- keeps working against exactly
        this return type). `mutate_result` below is the richer shape
        `http.post_mutate` uses.
        """
        return self._mutate_outcome(context, entity, operations, transaction=transaction, request_id=request_id).affected

    def mutate_result(self, context: AuthContext, entity: str, operations: list[dict[str, Any]], *, transaction: str | None = None, request_id: str | None = None, dry_run: bool = False, plan: str | None = None, budget: dict[str, int] | None = None) -> "MutationResult":
        """The HTTP-facing shape (`{affected, assigned_addresses}`,
        `spec/data-service-api.v1.json`'s `MutationResult`) -- used by
        `http.post_mutate` instead of `mutate` above, mirroring the
        `query`/`query_page` split (WP-4/WP-5).

        `dry_run`/`plan` (contract 1.7.0, D-4, WP-2b): real, given full
        effect below -- `capabilities().dry_run` is `enabled` as of this
        commit. `budget` (R-6) remains provisional -- `request_budget`
        stays `unavailable` until WP-2d, and this capability gate fires
        on a bare `budget` unconditionally, `plan` or no `plan`
        (supervisor ruling F-1, `{scratchpad}/rulings-r4.md`: D-4 (2)/
        addendum 2 S-l place `budget` validity in the request's own
        validation stage -- the same stage as shape/capability, before
        target-existence -- and `destructive_confirmation.evaluation_
        order` puts precondition evaluation, where `plan` is checked,
        AFTER that stage, never before it. A request carrying `budget`
        with `plan` attached is therefore refused here, at the
        capability gate, before `plan` is ever examined -- exactly like
        the query-side `_query_outcome` gate above, which this mirrors).
        This closes the review-round window (WP-2b F-1) in which a
        client could read a schema revision off a plain dry run's own
        `plan` token, recompute a `plan` for a `budget`-carrying body by
        the contract's own published digest rule, and have `budget`
        silently accepted-and-ignored on the resulting apply --
        `request_budget: unavailable` staying true requires this gate to
        run first.
        """
        if budget is not None:
            fail(
                "CAPABILITY_UNSUPPORTED",
                "budget is not supported by this foundation.",
                details={"violated_declaration": "capability", "field": "budget"},
            )
        outcome = self._mutate_outcome(context, entity, operations, transaction=transaction, request_id=request_id, dry_run=dry_run, plan=plan, budget=budget)
        return MutationResult(
            affected=outcome.affected,
            # D-4 (3)/A-9: a dry-run mutation result never carries
            # `assigned_addresses` -- the addresses a real execution would
            # assign are not settled (an insert may still have tentatively
            # consumed real id-sequence values, F-15, but this response
            # never reports them). Review round F-6: `None`, not `[]` --
            # `http.post_mutate` omits the key itself on `None`, matching
            # the contract's "does not carry" wording.
            assigned_addresses=None if dry_run else list(outcome.assigned_addresses or []),
            committed=outcome.committed,
            plan=outcome.plan if dry_run else None,
        )

    def _mutate_outcome(self, context: AuthContext, entity: str, operations: list[dict[str, Any]], *, transaction: str | None, request_id: str | None, dry_run: bool = False, plan: str | None = None, budget: dict[str, int] | None = None):
        rid = request_id or str(uuid.uuid4())
        try:
            with self._slot(context) as canonical:
                # G-1 (`{scratchpad}/rulings-r4.md` addendum): `transaction`
                # is never a contract-level *default* -- `None` here means
                # the caller's own request object never carried the key at
                # all (both `http.post_mutate` and the in-process port omit
                # the kwarg rather than resolving it to `"atomic"` before
                # this call). `resolved_transaction` is used for every
                # behavioural decision (the capability gate below); the
                # RAW `transaction` value (still `None` when omitted) is
                # what `plan_request` below reflects, so a request that
                # carried `transaction: "atomic"` explicitly digests
                # differently from one that omitted the key entirely, even
                # though both behave identically otherwise.
                resolved_transaction = transaction if transaction is not None else "atomic"
                if resolved_transaction != "atomic":
                    fail("CAPABILITY_UNSUPPORTED", "This foundation exposes atomic transactions only.")
                if not isinstance(operations, list):
                    fail("VALIDATION_FAILED", "Mutations must be a list.")
                request = {"entity": entity, "operations": operations}
                self.limits.check_request(request)
                self.limits.check_depth(request)
                deadline = self._clock() + self.limits.execution_ms / 1000
                # Contract 1.7.0 (D-4 (7)/S-a, WP-2b): the contract-level
                # request object a `plan` commits to -- `operations`/
                # `transaction`/`budget`, never `entity` (`MutationRequest`
                # has no `entity` property at all; it is a URL path
                # segment, not a body field) and never `dry_run`/`plan`
                # themselves (S-a's own exclusion pair, applied again
                # defensively inside `normalize_request_for_plan`).
                # G-1: `transaction` is included only when the caller's own
                # request object actually carried the key (see above) --
                # never the resolved/defaulted value.
                plan_request: dict[str, Any] = {"operations": operations}
                if transaction is not None:
                    plan_request["transaction"] = transaction
                if budget is not None:
                    plan_request["budget"] = budget
                # Phase 4 (design D-2/D-10), extended by D-4 (4)/U-2 = (A)
                # (WP-2b): the hook is only ever USED by the backend when
                # this batch turns out to pass through the confirmation
                # choke (a confirmed `delete`) -- building it unconditionally
                # here is cheap (no I/O happens until/unless `pre_commit()`
                # is actually called) and keeps this call site identical
                # regardless of what the batch turns out to contain,
                # matching `schema`'s own unconditional hook below. A
                # `dry_run`, though, never gets one AT ALL -- not merely
                # one that is never called -- so no audit line can ever be
                # written for it, by construction (U-2 = (A): "監査行を一切
                # 書かない", not "書くが呼ばない").
                hook = None if dry_run else self._make_audit_hook(canonical, event_class="data_operation", operation="mutate", target_kind="entity", request_id=rid)
                outcome = self._cells[canonical.application_id].transact(
                    entity, operations, self.limits, deadline=deadline, clock=self._clock, audit_hook=hook,
                    dry_run=dry_run, plan=plan, plan_request=plan_request,
                )
                # D-4 (4)/U-2 = (A): a dry_run that reached this point
                # reached the "would succeed" decision -- no audit event
                # (buffer-class OR the legacy in-memory sink `_event`
                # itself unconditionally appends to) is written for it.
                # D-10: `outcome.destructive` reports whether the backend's
                # pre-commit hook already durably recorded this batch --
                # `already_durable` tells `_event` to skip the buffer-class
                # enqueue in that case (at most one durable row per
                # operation).
                if not dry_run:
                    self._event(canonical, operation="mutate", outcome="allow", target_kind="entity", event_class="data_operation", request_id=rid, already_durable=outcome.destructive)
                return outcome
        except FoundationError as exc:
            self._event(context, operation="mutate", outcome="deny", target_kind="entity", reason_code=exc.code, event_class="operation_denial", request_id=rid, details=exc.details)
            raise

    # Contract 1.7.0 provisional gate (D-1 (3), work order §2 WP-1 (9)):
    # every one of these fields is schema-accepted (the packaged contract
    # copy is already 1.7.0) but not yet capability-enabled -- passing one
    # through unrejected would be a P-3 violation (declaring `unavailable`
    # while quietly accepting the field). WP-2a already removed `field_
    # constraints`/`enum`/`nullable` from this tuple (`constraint_
    # declarations` is `enabled`, `alter_field` is enforced). WP-2b removes
    # `dry_run`/`plan` in this same commit (`dry_run` is now `enabled`).
    # WP-2c (`idempotency_key`) and WP-2d (`budget`) each remove their own
    # remaining name in their own commit, the same way.
    _PROVISIONAL_UNSUPPORTED_SCHEMA_FIELDS = ("budget", "idempotency_key")

    def schema(self, context: AuthContext, operation: dict[str, Any] | None, *, request_id: str | None = None) -> "SchemaOutcome":
        """Always returns `SchemaOutcome` (`.committed`/`.revision`/
        `.descriptor`/`.plan`, contract 1.7.0, D-4, WP-2b) -- a pure
        passthrough of `ApplicationCell.apply_schema`/`PostgresCell.
        apply_schema`'s own return, which review round F-8
        (`{scratchpad}/rulings-r4.md`) unified to one shape regardless of
        whether `operation` carries `dry_run`/`plan`. Every pre-1.7.0
        direct caller of this method (`tests/test_foundation.py`,
        `tests/test_constraints_declaration.py`) reads `.revision` off
        the result; the in-process conformance adapter's own `hasattr(
        result, "revision")` branch already handles a non-`int` result
        unchanged (it never assumed `int`).
        """
        rid = request_id or str(uuid.uuid4())
        if isinstance(operation, dict):
            for provisional_field in self._PROVISIONAL_UNSUPPORTED_SCHEMA_FIELDS:
                if provisional_field in operation:
                    fail(
                        "CAPABILITY_UNSUPPORTED",
                        f"{provisional_field} is not supported by this foundation.",
                        details={"violated_declaration": "capability", "field": provisional_field},
                    )
        # Contract 1.7.0 (D-4, WP-2b): `SchemaOperationRequest` is the
        # single flat operation object itself (no separate `operations`
        # wrapper the way `MutationRequest` has) -- `dry_run`/`plan` are
        # simply keys already present on `operation`, read here (before
        # `_slot`, matching the provisional-gate check just above) so the
        # audit-hook/dispatch decisions below can already act on them.
        dry_run = bool(isinstance(operation, dict) and operation.get("dry_run", False))
        plan = operation.get("plan") if isinstance(operation, dict) else None
        try:
            with self._slot(context) as canonical:
                if not isinstance(operation, dict):
                    fail("VALIDATION_FAILED", "Schema operation must be an object.")
                # Authority is checked before touching request content at
                # all, so a non-developer credential gets FORBIDDEN/403 for
                # any schema operation, before any shape/capability
                # question is even considered. Unaffected by `dry_run`
                # (D-4 (2): a dry run walks the SAME gates a real request
                # does, no early-out).
                if canonical.role != "developer":
                    fail("FORBIDDEN", "Developer authority is required for schema operations.", status=403)
                self.limits.check_request(operation)
                self.limits.check_depth(operation)
                deadline = self._clock() + self.limits.execution_ms / 1000
                # Contract 1.7.0 (D-4 (7)/S-a, WP-2b): the contract-level
                # request object a `plan` commits to -- `operation` itself
                # already IS that object (`SchemaOperationRequest`'s own
                # flat shape), minus `plan`/`dry_run` (S-a's exclusion
                # pair, applied again defensively inside `normalize_
                # request_for_plan`).
                plan_request = {key: value for key, value in operation.items() if key not in ("plan", "dry_run")}
                # Phase 4 (design D-2, item 2): unconditionally fail-closed
                # -- every schema operation, not only a confirmed destructive
                # one (unlike `mutate` above). Extended by D-4 (4)/U-2 = (A)
                # (WP-2b): a `dry_run` never gets a hook AT ALL -- not
                # merely one that is never called -- so no audit line can
                # ever be written for it, by construction.
                hook = None if dry_run else self._make_audit_hook(canonical, event_class="privilege_sensitive", operation="schema", target_kind="entity", request_id=rid)
                outcome = self._cells[canonical.application_id].apply_schema(
                    operation, developer=canonical.role == "developer", limits=self.limits, deadline=deadline,
                    clock=self._clock, audit_hook=hook, dry_run=dry_run, plan=plan, plan_request=plan_request,
                )
                # D-4 (4)/U-2 = (A): no audit event at all for a dry_run
                # that reached this point (the "would succeed" decision).
                if not dry_run:
                    self._event(canonical, operation="schema", outcome="allow", target_kind="entity", event_class="privilege_sensitive", request_id=rid, already_durable=True)
                return outcome
        except FoundationError as exc:
            self._event(context, operation="schema", outcome="deny", target_kind="entity", reason_code=exc.code, event_class="privilege_denial", request_id=rid, details=exc.details)
            raise

    def catalog(self, context: AuthContext, *, request_id: str | None = None) -> dict[str, Any]:
        rid = request_id or str(uuid.uuid4())
        try:
            with self._slot(context) as canonical:
                # The full CCR-13 `EntityDescriptor` shape (mutation_class/
                # address_fields/address_reuse/unique_keys) -- `row_
                # addressability` is now declared `enabled`, so this
                # publishes exactly what the cell itself already computes,
                # with no narrowing.
                entities = self._cells[canonical.application_id].catalog()
                # Phase 4 (design D-2 §7.3): `catalog` never passes through
                # the confirmation choke -- always buffer-class.
                self._event(canonical, operation="catalog", outcome="allow", target_kind="entity", event_class="data_operation", request_id=rid)
                return {"application_scope": canonical.application_id, "entities": entities}
        except FoundationError as exc:
            self._event(context, operation="catalog", outcome="deny", target_kind="entity", reason_code=exc.code, event_class="authorization_denial", request_id=rid, details=exc.details)
            raise

    def deny_unsupported(self, context: AuthContext, *, operation: str, message: str, request_id: str | None = None) -> None:
        """Refuse a capability this foundation does not implement, while
        still passing through `_slot`'s rate/concurrency accounting and
        emitting a denial audit event -- exactly like every other
        application-plane method below, instead of being a bare pre-`_slot`
        `fail()` call that an unauthenticated-looking credential could
        spend for free (review R12).

        `http.py`'s `post_audit_query`/`post_cross_entity_mutate` stub
        handlers use this for the two contract endpoints this foundation
        declares `unavailable`/has no execution path for at all
        (`audit_query`, `cross_entity_mutation`); this always raises
        `CAPABILITY_UNSUPPORTED`, it never returns.

        Phase 4 (design D-3): this denial's `reason_code` is always
        `CAPABILITY_UNSUPPORTED` -- not in D-3's durable-code inclusion list, so
        `_event`'s deny dispatch never routes it through the durable/
        coalesced path (unchanged from pre-Phase-4 behaviour: this method
        never wrote a durable row before this WP either).
        """
        rid = request_id or str(uuid.uuid4())
        try:
            with self._slot(context):
                fail("CAPABILITY_UNSUPPORTED", message)
        except FoundationError as exc:
            self._event(context, operation=operation, outcome="deny", target_kind="entity", reason_code=exc.code, event_class="operation_denial", request_id=rid, details=exc.details)
            raise

    @contextmanager
    def _slot(self, context: AuthContext) -> Iterator[AuthContext]:
        canonical = self._check(context)
        self._acquire_rate(canonical)
        with self._active_lock:
            if self._active >= self.limits.concurrency:
                fail("LIMIT_EXCEEDED", "Concurrency limit exceeded.", status=429, details={"resource": "concurrency", "limit_class": "concurrency", "limit": self.limits.concurrency})
            self._active += 1
        try:
            yield canonical
        finally:
            with self._active_lock:
                self._active -= 1

    def _check(self, context: AuthContext) -> AuthContext:
        if not isinstance(context, AuthContext):
            fail("AUTH_INVALID", "Authentication context is invalid.", status=401)
        canonical = self._credentials.assert_active(context)
        if canonical.application_id in self._disabled_apps:
            fail("APPLICATION_DISABLED", "Application is disabled.", status=403)
        if canonical.application_id not in self._cells:
            fail("FORBIDDEN", "Application scope is unavailable.", status=403)
        return canonical

    def _acquire_rate(self, context: AuthContext) -> None:
        now = self._clock()
        with self._rate_lock:
            window = self._rate_windows.setdefault(context.credential_id, [])
            window[:] = [stamp for stamp in window if now - stamp < 60]
            if len(window) >= self.limits.requests_per_minute:
                fail("LIMIT_EXCEEDED", "Request rate limit exceeded.", status=429, details={"resource": "requests_per_minute", "limit_class": "requests_per_minute", "limit": self.limits.requests_per_minute})
            window.append(now)

    def _event(self, context: AuthContext, *, operation: str, outcome: str, target_kind: str, reason_code: str | None = None, event_class: str, request_id: str | None = None, target_id: str | None = None, already_durable: bool = False, details: dict[str, Any] | None = None) -> None:
        """The single dispatch point every public method above calls,
        both on success (`outcome="allow"`) and on denial
        (`outcome="deny"`). Always appends to the pre-existing legacy
        in-memory `self._audit` first, unconditionally (D-10: this sink's
        behaviour is completely unaffected by anything below) -- then
        applies Phase 4's durable-recording dispatch (design D-2/D-3/D-4):

        - `already_durable=True` (only ever passed by `mutate`/`schema`
          above, when the backend's own pre-commit hook already durably
          recorded this exact event): return immediately. D-10's "at most
          one durable row per operation" rule.
        - `outcome == "deny"`: `details["origin"] == "audit_sink"` (D-2)
          means this denial's `SERVICE_UNAVAILABLE` was produced by the
          audit pipeline itself already failing to record this very
          operation (a pre-commit sink failure, a commit-failure error-row
          write, a coalesced-denial first-insert failure) -- routing it
          through `_route_denial` again would be a second (or third)
          durable write for what is still logically one operation, so this
          returns without doing anything further. Otherwise, any reason
          code outside D-3's durable-code inclusion list (`_DURABLE_
          DENIAL_CODES`, J-2 -- not merely the 4 originally named) returns
          without any durable/buffered
          record at all; every other reason code is fail-closed-class and
          goes through the coalescing denial router (which may itself
          raise `SERVICE_UNAVAILABLE`).
        - `outcome == "allow"`: buffer-class (D-4) -- `query`/`catalog`
          always reach here (they never pass through the confirmation
          choke), and `mutate` reaches here only when its batch did NOT
          (`already_durable=False`).
        """
        canonical = self._credentials.canonical_context(context)
        application_id = canonical.application_id if canonical else None
        actor_type = "application_credential" if canonical else "unknown"
        actor_id = canonical.credential_id if canonical else None
        role = canonical.role if canonical else None
        rid = request_id or str(uuid.uuid4())
        self._audit.append(event_class=event_class, request_id=rid, application_id=application_id, actor_type=actor_type, actor_id=actor_id, role=role, operation=operation, target_kind=target_kind, outcome=outcome, reason_code=reason_code, target_id=target_id)
        if already_durable:
            return
        if outcome == "deny":
            if details and details.get("origin") == _AUDIT_SINK_ORIGIN:
                return
            if reason_code not in _DURABLE_DENIAL_CODES:
                return
            self._denial_event(
                event_class=event_class, request_id=rid, application_id=application_id, actor_type=actor_type,
                actor_id=actor_id, role=role, operation=operation, target_kind=target_kind, reason_code=reason_code,
                target_id=target_id, details=None,
            )
            return
        # outcome == "allow": D-4's buffer is scoped to `data_operation`
        # successes only (§7.3's own text: "通常のdata-operation成功event
        # のみ") -- `query`/`catalog` always land here as `data_operation`,
        # and `mutate` lands here only when it was NOT destructive
        # (`already_durable=False`, checked above). `authenticate`'s own
        # success (`event_class="authentication"`) is a distinct event
        # class outside that scope: it is not a data operation, and D-2's
        # rule never names it as fail-closed either, so it stays exactly
        # where it already was pre-Phase-4 -- the legacy in-memory sink
        # only (already appended above), no durable/buffered record at all.
        if event_class != "data_operation":
            return
        self._audit_buffer.push(
            AuditEvent(
                event_id=str(uuid.uuid4()), event_class=event_class, occurred_at=_now_iso(), request_id=rid,
                application_id=application_id, actor_type=actor_type, actor_id=actor_id, role=role,
                operation=operation, target_kind=target_kind, outcome=outcome, reason_code=reason_code,
                target_id=target_id,
            )
        )

    def _denial_event(self, *, event_class: str, request_id: str, application_id: str | None, actor_type: str, actor_id: str | None, role: str | None, operation: str, target_kind: str | None, reason_code: str | None, target_id: str | None, details: dict[str, Any] | None) -> None:
        """The shared fail-closed/coalesced-denial dispatch (design D-3),
        used both by `_event`'s own deny branch and by `authenticate`'s
        except clause (which has no `canonical`/`AuthContext` to route
        through `_event` at all -- authentication itself is what failed).
        `details` mirrors `_event`'s own audit-sink-origin short-circuit.
        """
        if details and details.get("origin") == _AUDIT_SINK_ORIGIN:
            return
        if reason_code not in _DURABLE_DENIAL_CODES:
            return
        key = (application_id, actor_id or "unknown", operation, reason_code)
        fields = {
            "event_class": event_class, "request_id": request_id, "application_id": application_id,
            "actor_type": actor_type, "actor_id": actor_id, "role": role, "operation": operation,
            "target_kind": target_kind, "outcome": "deny", "reason_code": reason_code, "target_id": target_id,
        }
        self._denial_coalescer.route(key=key, fields=fields)

    def _make_audit_hook(self, canonical: AuthContext, *, event_class: str, operation: str, target_kind: str, request_id: str) -> ApplicationAuditHook:
        """Phase 4 (design D-2): builds the `ApplicationAuditHook` passed
        to `StorageBackend.transact`/`apply_schema` as `audit_hook` --
        every field the durable row needs is already resolved here (this
        is `DataService`'s own job; the backend has no identity/request
        context of its own beyond what it is given).
        """
        fields = {
            "event_class": event_class, "request_id": request_id, "application_id": canonical.application_id,
            "actor_type": "application_credential", "actor_id": canonical.credential_id, "role": canonical.role,
            "operation": operation, "target_kind": target_kind, "target_id": None,
        }
        return _PreCommitHook(self._durable_audit, fields)

    def flush_audit_buffer(self, *, force_expire_denial_windows: bool = False) -> None:
        """Phase 4 (design D-4/§7.3/§7.4): synchronously drains the
        bounded buffer (writing it as one batch), retries the sticky
        overflow-alert row if one is pending and due, and sweeps
        denial-coalescing windows (writing their repeat-count summary row,
        D-3). Called on demand by this repository's own tests and by a
        composition root's periodic timer alike -- there is nothing
        time-sensitive about calling this more or less often beyond how
        promptly buffered/coalesced evidence becomes durable (D-4's own
        "periodic or threshold" flush-trigger latitude).

        `force_expire_denial_windows=True` (WP-2(a) fix round 2, review
        N-4): flushes EVERY currently-open denial-coalescing window,
        expired or not, instead of only expired ones -- used exactly once,
        by a composition root's graceful-shutdown path. Without this, a
        window still short of its own `window_s` at the moment the process
        stops loses its accumulated repeat count entirely (D-3 only
        sanctions losing counts to an actual crash, not to an orderly
        stop); the default (periodic timer, explicit test calls) stays
        `False` -- an in-progress window still has a legitimate future to
        expire into naturally and must not be cut short just because
        something else happened to call this method.
        """
        self._audit_buffer.flush()
        if force_expire_denial_windows:
            self._denial_coalescer.flush_all()
        else:
            self._denial_coalescer.flush_expired()

    def _register_application(self, application_id: str, entities: dict[str, list[dict[str, Any]]] | None = None) -> None:
        if application_id in self._cells:
            fail("CONFLICT", "Application already exists.", status=409)
        self._cells[application_id] = self._cell_factory(application_id, entities)

    def _set_application_disabled(self, application_id: str, disabled: bool) -> None:
        if application_id not in self._cells:
            fail("NOT_FOUND", "Application was not found.", status=404)
        if disabled:
            self._disabled_apps.add(application_id)
        else:
            self._disabled_apps.discard(application_id)


class ControlAuthority:
    """Trusted lifecycle authority; it is not an application API capability."""

    def __init__(self, service: DataService) -> None:
        self._service = service

    def register_application(self, application_id: str, *, entities: dict[str, list[dict[str, Any]]] | None = None) -> None:
        try:
            self._service._register_application(application_id, entities)
            self._control_event(operation="register_application", outcome="allow", target=application_id, event_class="application_lifecycle")
        except FoundationError as exc:
            self._control_event(operation="register_application", outcome="deny", target=application_id, reason_code=exc.code, event_class="control_failure")
            raise

    def set_application_enabled(self, application_id: str, enabled: bool) -> None:
        try:
            if not isinstance(enabled, bool):
                fail("VALIDATION_FAILED", "Application enabled state must be boolean.")
            self._service._set_application_disabled(application_id, not enabled)
            self._control_event(operation="enable_application" if enabled else "disable_application", outcome="allow", target=application_id, event_class="application_lifecycle")
        except FoundationError as exc:
            self._control_event(operation="enable_application" if enabled else "disable_application", outcome="deny", target=application_id, reason_code=exc.code, event_class="control_failure")
            raise

    def set_credential_state(self, credential_id: str, *, enabled: bool | None = None, revoked: bool | None = None, work: Any = None) -> None:
        """`work` is keyword-only and defaults to `None` (CCR-14 WP-3): when
        omitted, this method self-manages exactly as before -- opens its own
        `unit_of_work()`, commits/reverts exactly one call's worth of state,
        and every pre-WP-3 caller (this repository's own tests, the
        in-process conformance adapter) keeps working unchanged. When a
        caller supplies its own already-open `work` handle (`ControlPlane
        Service`'s in-memory backend, WP-3: it needs the credential-state
        change and its own `control_audit` sink append to land in the *same*
        transaction, R-6), this method uses that handle directly instead of
        opening a second one -- never both. `work`'s type is deliberately
        untyped (`Any`) rather than importing `auth._InMemoryWork`/
        `credential_store._PostgresWork` here: this module stays agnostic to
        which store implementation (in-memory or PostgreSQL) it is holding,
        exactly as it already is everywhere else (`self._service._credentials`
        is never type-narrowed in this class)."""
        try:
            if work is not None:
                self._service._credentials.set_state(credential_id, enabled=enabled, revoked=revoked, work=work)
            else:
                # R-6/§8 B-2: chase `CredentialStore`/`PostgresCredentialStore`'s
                # new `unit_of_work()`-required call form -- semantics are
                # unchanged (this still commits/reverts exactly one call's
                # worth of state, same as before WP-2; `ControlAuthority`'s own
                # audit trail stays on the existing in-memory `AuditSink` below,
                # not on the new `control_audit` table, which only `ops.py`'s
                # ritual/CLI-path writes to in this work package).
                with self._service._credentials.unit_of_work() as own_work:
                    self._service._credentials.set_state(credential_id, enabled=enabled, revoked=revoked, work=own_work)
            self._control_event(operation="set_credential_state", outcome="allow", target=credential_id, event_class="credential_lifecycle")
        except FoundationError as exc:
            self._control_event(operation="set_credential_state", outcome="deny", target=credential_id, reason_code=exc.code, event_class="control_failure")
            raise

    def issue_credential(self, credential_id: str, application_id: str, role: str, secret: str, *, work: Any = None) -> str:
        """`work` is keyword-only, defaulting to `None` -- see `set_credential_
        state`'s docstring immediately above for the full CCR-14 WP-3
        rationale; identical reasoning applies here.

        Rework (coordinator item 3, 2026-09-04 review): returns the
        composed bearer `self._service._credentials.add(...)` itself now
        returns (design D-1(c) "合成は store/service 層のみ" principle) --
        this out-of-band lifecycle-authority entry point is an issuance
        point (the conformance in-process plug's own privileged-setup
        `issue_credential` calls this directly, `ops.py` does not use this
        method at all -- see that module's own `cmd_issue_credential`,
        which calls the store's `add` directly and gets the same composed
        return value there). Every pre-WP-2 caller that ignored the
        previous `None` return is unaffected (Python permits discarding a
        return value freely) -- `test_control_authority_work_parameter_
        defaults_preserve_existing_callers` pins this explicitly.
        """
        try:
            if application_id not in self._service._cells:
                fail("NOT_FOUND", "Application was not found.", status=404)
            if work is not None:
                bearer = self._service._credentials.add(credential_id, application_id, role, secret, work=work)
            else:
                with self._service._credentials.unit_of_work() as own_work:
                    bearer = self._service._credentials.add(credential_id, application_id, role, secret, work=own_work)
            self._control_event(operation="issue_credential", outcome="allow", target=application_id, event_class="credential_lifecycle")
            return bearer
        except FoundationError as exc:
            self._control_event(operation="issue_credential", outcome="deny", target=application_id, reason_code=exc.code, event_class="control_failure")
            raise

    def audit_events(self) -> tuple[Any, ...]:
        """Read-only evidence view; application facade has no audit accessor."""
        return self._service._audit.events()

    def delete_audit(self) -> None:
        try:
            self._service._audit.delete()
        except PermissionError:
            self._control_event(operation="delete_audit", outcome="deny", target="audit", reason_code="AUDIT_APPEND_ONLY", event_class="control_failure")
            raise

    def set_authorization_state_available(self, available: bool) -> None:
        try:
            if not isinstance(available, bool):
                fail("VALIDATION_FAILED", "Authorization state availability must be boolean.")
            self._service._credentials.available = available
            self._control_event(operation="set_authorization_state_available", outcome="allow", target="authorization", event_class="control_state")
        except FoundationError as exc:
            self._control_event(operation="set_authorization_state_available", outcome="deny", target="authorization", reason_code=exc.code, event_class="control_failure")
            raise

    def _control_event(self, *, operation: str, outcome: str, target: str, reason_code: str | None = None, event_class: str) -> None:
        target_app = target if target in self._service._cells else self._service._credentials.application_id_for(target)
        self._service._audit.append(event_class=event_class, request_id=str(uuid.uuid4()), application_id=target_app, actor_type="control_authority", actor_id=None, role="control", operation=operation, target_kind="application_or_credential", outcome=outcome, reason_code=reason_code)
