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
from .audit_counts import _coalesced_count
from .auth import AuthContext, CredentialStore
from .backend import StorageBackend
from .errors import FoundationError, fail, observed_type_of, violation
from .limits import ResourceLimits, narrow_limits_by_budget
from .structured import ApplicationCell, fold_operation_idempotency_keys, parse_predicate
from .topology import AuthorityTopology

_logger = logging.getLogger(__name__)

# Phase 4 (design PHASE4_DURABLE_AUDIT_SINK_V1.md D-3; WP-2(a) review J-2,
# supervisor ruling 2026-09-02): an INCLUSION set -- only a denial whose
# reason_code is one of these 6 (D-3's own range table, SI-14's minimal
# event class: authentication/authorization denial) is fail-closed/
# coalesced-durable. Every other reason_code -- D-3's originally-named 4 non-durable codes (`VALIDATION_FAILED`/`LIMIT_EXCEEDED`/`CAPABILITY_UNSUPPORTED`/`NOT_FOUND`) AND everything else this facade can raise (`CONFLICT`, `PRECONDITION_FAILED`, `SERVICE_UNAVAILABLE`, `AUTH_STATE_UNAVAILABLE`, ...) -- is out of scope for durable/buffered recording (N-2: buffering them would just let the flow problem exists to bound come back through the buffer instead). An exclusion-list reading
# (only the named 4 are non-durable, everything else durable) was this
# module's first implementation; the review's B-1 finding showed it lets a
# `SERVICE_UNAVAILABLE` produced by the audit pipeline's OWN failure re-enter
# as a "new" denial, writing a THIRD durable row for one operation (D-10's
# own prohibited case (ii)) -- switching to inclusion closes that path
# structurally (`SERVICE_UNAVAILABLE` was never in D-3's fail-closed list to
# begin with). `test_durable_denial_codes_match_the_design_d3_table` fixes this set against D-3's table by name.
# history: CH-0178
_DURABLE_DENIAL_CODES = frozenset({
    "AUTH_REQUIRED",       # 認証系 (AUTH_REQUIRED/AUTH_INVALID相当)
    "AUTH_INVALID",        # 認証系, and also covers this codebase's "credential disabled" case
    "AUTH_REVOKED",        # credential の revoked
    "FORBIDDEN",           # FORBIDDEN, and also this facade's "privilege denial" (schema())
    "APPLICATION_DISABLED",  # APPLICATION_DISABLED
    "DESTRUCTIVE_CONFIRMATION_REQUIRED",  # DESTRUCTIVE_CONFIRMATION_REQUIRED
})

# a `FoundationError.details` marker this module's own audit-hook/denial-routing code sets on a `SERVICE_UNAVAILABLE` it raises BECAUSE the durable audit pipeline itself just failed (a pre-commit sink failure, a post-commit `error`-row write, a coalesced-denial first-insert failure). `_event`'s own deny-dispatch checks this marker and skips routing such a denial through `_route_denial` again -- without it, the generic `except FoundationError` handler every public method already has would treat this SERVICE_UNAVAILABLE as a brand-new denial needing its own durable write, producing a second (or third) durable row for what D-10 requires stays at most one (+ the error-row exception).
# history: CH-0177
_AUDIT_SINK_ORIGIN = "audit_sink"

# the coalescing window (D-3/P4-D3, confirmed value).
# history: CH-0176
_DENIAL_COALESCE_WINDOW_S = 60.0

# the bounded buffer's default capacity (implementation discretion per the design -- "既定 1000、実装裁量で設定可").
# history: CH-0175
_DEFAULT_AUDIT_BUFFER_CAPACITY = 1000

# Phase 4 (design §7.3/§7.4; WP-2(a) fix round 2 review N-2, N-6): ONE
# constant serving two roles by construction, not by coincidence of two
# independently-set literals agreeing -- (i) `_AuditBuffer`'s own default
# minimum interval between overflow-alert-row attempts (N-2: "1 alert row
# per flush interval per process"), and (ii) the default periodic
# buffer-flush interval `r2db_api.main`'s composition-root background
# thread uses (imports this name directly rather than defining its own).
_DEFAULT_AUDIT_FLUSH_INTERVAL_S = 2.0

# Phase 10 WP-6a (design, contract 1.8.0): this plane's own region (ii) -- limit classes bound by in-memory, per-process state (`self._rate_windows`/`self._active`, both below), the only classes whose `limit_enforcement` mapping actually depends on `process_ceiling`. Every other `ResourceLimits` class is either region (i) (request-scoped, unaffected regardless of process count) or region (iii) (`idempotency_entries`, bound in PostgreSQL -- `enforced` regardless of `process_ceiling`, design; the count lock itself is scope, not this WP's).
# history: CH-0174
_IN_MEMORY_PROCESS_WIDE_LIMIT_CLASSES = frozenset({"requests_per_minute", "concurrency"})

# `_coalesced_count`'s own comment (Phase 4 WP-2(b) review B-1) moved with
# it to `audit_counts.py` when that helper was extracted.
# history: CH-0179

# Phase 4 (design §7.4/D-4): fixed, no-interpolation log messages -- the
# design's own instruction ("可変部に実データを載せない"). A fixed string
# also means these two call sites can never accidentally leak a client-
# supplied value (application_id, secret fragment, filter content) into
# process logs.
_BUFFER_OVERFLOW_LOG_MESSAGE = "application_audit buffer overflow: events were dropped"
_ALERT_WRITE_FAILED_LOG_MESSAGE = "application_audit overflow-alert row could not be written; retrying with backoff"
_ALERT_WRITE_RECOVERED_LOG_MESSAGE = "application_audit overflow-alert row recorded; pending overflow cleared"

# fixed, no-interpolation log messages for the denial-coalescer's own aggregate (repeat-count summary) row write path -- mirrors `_ALERT_WRITE_FAILED_LOG_MESSAGE`/`_ALERT_WRITE_RECOVERED_LOG_MESSAGE`'s identical state-transition-only discipline, applied to `_DenialCoalescer._note_aggregate_write_result`.
# history: CH-0173
_COALESCE_AGGREGATE_WRITE_FAILED_LOG_MESSAGE = "application_audit coalesced-denial summary row could not be written; retrying"
_COALESCE_AGGREGATE_WRITE_RECOVERED_LOG_MESSAGE = "application_audit coalesced-denial summary row recorded; retry cleared"

# exponential backoff for the sticky overflow-alert retry, capped at 60s -- an unbounded equal-interval retry against a durably-failing sink would itself become a logging DoS (the same flow problem bounds for denials, recurring on the alert path).
# The FLOOR for this backoff is `_DEFAULT_AUDIT_FLUSH_INTERVAL_S`
# (`_AuditBuffer`'s own `alert_min_interval_s`, WP-2(a) fix round 2 review
# N-2), not a separate, smaller initial value -- no alert attempt is ever
# spaced closer together than the composition root's own flush cadence.
# history: CH-0172
_ALERT_BACKOFF_CAP_S = 60.0


def _now_iso() -> str:
    """The same `occurred_at` construction `audit.AuditSink.append`/
    `audit.ControlAuditSink.append` already use -- factored out here so
    `_event`'s own buffer-class `AuditEvent` construction (below) matches
    it exactly, byte for byte."""
    return datetime.now(timezone.utc).isoformat()

# Default cell factory (design step 2): builds the existing in-memory `ApplicationCell`, unchanged, so every caller that does not pass `cell_factory` gets exactly today's behavior. A deployment that wants
# `PostgresCell` (or any other `StorageBackend`) instead passes its own
# factory -- `DataService` itself never imports `postgres.py` or references
# PostgreSQL, keeping this module backend-agnostic (D-1: "in-memory backend
# and PostgreSQL backend pass through the same validation boundary" without
# either backend leaking into this facade).
# history: CH-0171
CellFactory = Callable[[str, dict[str, list[dict[str, Any]]] | None], StorageBackend]


def _default_cell_factory(application_id: str, entities: dict[str, list[dict[str, Any]]] | None) -> StorageBackend:
    return ApplicationCell(application_id, entities or {})


@dataclass(frozen=True)
class QueryPage:
    """`DataService.query_page`'s own return shape, matching `spec/data-service-api.v1.json`'s `QueryResult` (CCR-13 introduced `items`/`next_page` adds `revisions`, index-aligned with `items`, now that `revision_preconditions` is declared `enabled`). `next_page`
    is the opaque cursor for the next page (`QueryOutcome.next_cursor`,
    `r2db_api.structured`), or `None` when this was the last page.

    History: CH-0170
    """

    items: list[dict[str, Any]]
    next_page: str | None
    revisions: list[str]
    # Contract 1.7.0: the same `request_id` this query's own audit event (`_query_outcome`'s `_event` call) carries -- generated once, in `query_page` itself, before `_query_outcome` runs, so both this field and that audit event see the identical value.
    # history: CH-0169
    request_id: str | None = None


@dataclass(frozen=True)
class MutationResult:
    """`DataService.mutate_result`'s own return shape, matching
    `spec/data-service-api.v1.json`'s `MutationResult`. Mirrors the `query`/`query_page` split: `mutate` below stays byte-for-byte backward compatible (a bare `int`, the affected count) for every existing caller (the in-process conformance adapter); this richer shape reaches only the HTTP boundary, which needs `assigned_addresses` to build the contract's own response. `entity` is
    never present on any element here (contract: only the cross-entity
    endpoint's own elements name their entity; this is the per-entity
    endpoint's shape).

    `committed`/`plan` (contract 1.7.0, D-4): before WP-2b, every caller reaching this point had necessarily committed (an atomic batch that failed partway through never returns anything, it raises), so `http.post_mutate` hardcoded `committed: True` itself and this dataclass carried no such field at all. `committed` now reports the
    real decision (`False` only for a `dry_run` that reached the "would
    succeed" decision); `plan` carries the deterministic token computed
    for it -- `DataService.mutate_result` only ever sets `plan` on a
    `dry_run` response (`None` for a real commit, D-4 (3): a real
    response's shape stays otherwise unchanged from before this version).

    `None` exactly on a `dry_run` response -- `http.post_mutate` omits the key itself then, rather than carrying an empty list, matching the contract's "does not carry" wording. A real commit always gets a list
    (possibly empty, when the batch assigned no address), unchanged from
    before this version.

    History: CH-0168
    """

    affected: int
    assigned_addresses: list[dict[str, Any]] | None
    committed: bool = True
    plan: str | None = None
    # Contract 1.7.0: `outcome.request_id` -- this execution's own value for a real commit/dry_run, or the ORIGINAL execution's own value for an idempotency replay (`MutationOutcome.request_id`'s own comment). Never regenerated here.
    # history: CH-0167
    request_id: str | None = None


class _PreCommitHook:
    """the concrete `ApplicationAuditHook` `DataService` builds per fail-closed-class request and hands to `StorageBackend.transact`/`apply_schema` as `audit_hook`. Every field
    the durable row needs (`event_class`/`request_id`/`application_id`/
    `actor_type`/`actor_id`/`role`/`operation`/`target_kind`/`target_id`)
    is already bound here at construction time -- the backend itself
    supplies none of it, only the fail-closed/buffer-class decision (D-2's
    normative rule: the confirmation choke for `transact`, unconditional
    for `apply_schema`).

    History: CH-0166
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
        # best-effort from the response's point of view (the caller fails SERVICE_UNAVAILABLE regardless of whether this succeeds -- the data commit already failed either way) -- any exception here is swallowed, never re-raised, so a backend's own `except psycopg.Error` clause always reaches its own `fail()` call next, not this method's failure.
        # history: CH-0165
        try:
            self._sink.append(outcome="error", reason_code="commit_failed", count=None, **self._fields)
        except Exception:
            pass


class _AuditBuffer:
    """Phase 4 (design D-4/§7.3/§7.4): the bounded in-memory buffer for
    ordinary (buffer-class) data-operation success events, plus the
    overflow-alert sticky-retry state. Owns its own lock; the durable I/O `flush()` performs happens on the calling thread using `sink.append`/ `append_many`, each of which opens its own connection/transaction (D-1's `PostgresApplicationAuditSink` docstring) -- this is what makes "a flush never shares a transaction with a fail-closed write" automatic rather than something this class has to arrange.

    capacity is per-process, not per-deployment -- a multi-instance deployment's real bound is `capacity * <max instances>`, which is runbook (§9.3), not code, territory.

    §7.3 names TWO flush triggers, "periodic" and "threshold" -- a prior revision implemented only the periodic one (the composition root's background timer). `push()` now also triggers a
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

    a RETAINED event is, by definition, NOT lost -- it is still sitting in `self._events`, waiting for the next flush attempt. Counting it in `_dropped_total` (a prior
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

    Alert-row EMISSION RATE is bounded independently of eviction/flush-retry rate: `_alert_min_interval_s` (constructor parameter, matching the composition root's own periodic-flush interval, default 2.0s) is a hard floor under `_alert_backoff_s` -- no two alert attempts are ever less than `_alert_min_interval_s` apart, "1 alert row attempt per flush interval per process" even while eviction is ongoing. The backoff is
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

    History: CH-0164
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
        # tracks whether the most recent `flush()` attempt's own `append_many` succeeded or failed -- independent of the alert row's own write outcome, and read by `_retry_alert` to decide whether the backoff may reset.
        # history: CH-0163
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
            # threshold flush -- see class docstring. Outside the lock
            # (already released above), on the calling thread.
            # history: CH-0162
            self.flush()

    def pending_count(self) -> int:
        with self._lock:
            return len(self._events)

    def flush(self) -> None:
        """D-4/§7.3: called on demand (tests, the adapter privilege hook), periodically (composition root), and now also from `push()` at the threshold. Writes the current buffer contents as one batch,
        then attempts the sticky overflow-alert retry -- always in that
        order, always on a connection/transaction of its own. A failed batch write leaves the events in place for the next attempt (retained, not counted as dropped --) rather than discarding them or alerting on its own.

        the periodic-flush thread (composition root) and a request-path threshold flush (`push()`, M-2 above) can call this method concurrently on the SAME buffer.
        `pending` is therefore SWAPPED OUT of `self._events` under a single lock acquisition (not merely copied) -- this, not a separate "flush in progress" flag, is what makes two concurrent `flush()` calls durably write disjoint (usually one full, one empty) sets of events instead of both durably writing the SAME events (the double-row bug this found, reproduced verbatim by `test_concurrent_periodic_and_threshold_flush_never_double_writes_pending_events`). A concurrent call that finds `self.
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

        WP-3(a) review B-1 (on the fix above): while this method holds `pending` outside `self._events`, `push()` sees an empty (or merely in-flight-refilled) buffer and does not evict -- capacity is enforced only against whatever is currently sitting in `self._events`. A naive unconditional `pending + self._events` restore on failure can therefore exceed `_capacity` (up to `len(pending)` extra), and because the surviving overflow is never itself re-evicted by a later `push()` (each `push()` only ever evicts ONE item, the one IT just added), a sink outage would let the buffer grow WITHOUT BOUND across repeated failed flushes -- breaking D-4's "bounded in-memory buffer" and D-1 review M-5's capacity-side availability argument, and doing so *silently*: no `push()` eviction fires during this growth, so `_dropped_total` never increments and the overflow alert never appears even though evidence is unboundedly accumulating in memory. So the
        restore truncates back down to `_capacity`, dropping from the
        FRONT (oldest first, matching `push()`'s own `pop(0)` FIFO
        discipline) -- and, exactly like a genuine `push()`-path eviction,
        counts only what was ACTUALLY, irrevocably discarded here (never
        the merely-retried remainder) in `_dropped_total`, sets
        `_alert_pending`, and logs the same fixed overflow message.

        History: CH-0161
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
                    # put the un-written batch back rather than discarding it -- it is retried by the next flush, not counted in `_dropped_total` (nothing has actually been lost) and nothing new to alert or log about on this path alone. Prepended ahead of anything a concurrent
                    # `push()` added to `self._events` while this I/O was in
                    # flight, so flush order still matches arrival order.
                    # history: CH-0160
                    self._events = pending + self._events
                    # re-impose the capacity bound `push()` could not enforce while this batch was held outside `self._events` -- drop the oldest overflow, exactly the FIFO discipline `push()`'s own eviction branch uses, and count ONLY this genuine, irrevocable loss (the rest is still a retained retry, not a drop).
                    # history: CH-0159
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
                    # `_flush_currently_failing` clears unconditionally on ANY successful `append_many` -- not gated on `self._events` being empty. Under
                    # sustained push load the buffer is rarely empty even
                    # once the sink has genuinely recovered (M-2's
                    # threshold flush keeps refilling it), so the prior
                    # "only when empty" gate left the flag -- and the
                    # alert backoff it feeds, see `_retry_alert` below --
                    # stuck at the sink-broken state long after recovery.
                    #
                    # Completion-order semantics absorb the WP-3(a) review m-1 race this replaces: a DIFFERENT, still-failing concurrent flush (disjoint batch, per the swap above) sets this back to True in its own failure branch whenever IT completes -- whichever flush completes LAST wins, exactly as with any other unsynchronized shared-state update. A brief window
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
                    # history: CH-0158
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
            # this branch is only ever reached once the backoff interval has already elapsed (the early return above enforces that), so logging unconditionally here already matches "first attempt, then once per backoff interval" -- no separate first-attempt bookkeeping is needed.
            # history: CH-0157
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
            # the backoff is keyed to whether the BUFFER FLUSH is currently failing, not to whether this alert row's own INSERT just succeeded. If the flush is still failing (more
            # evictions can still be coming), keep backing off -- exactly
            # like an alert-write failure would -- so a healthy alert path
            # cannot be used to re-trigger a fresh attempt every single
            # `_alert_min_interval_s` for as long as the underlying sink
            # stays broken. Only reset to the floor once the flush itself
            # is observed healthy.
            # history: CH-0156
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
    class denials. a shared store is never consulted, so the same key can legitimately produce one row per process/instance, not one row per deployment).

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

    a same-key concurrent `route()` call must never observe "a window already exists" (and take the fast `repeat_count += 1` path) before the FIRST occurrence's own durable INSERT has actually resolved -- otherwise a fail-closed denial flood racing a sink outage could return an ordinary-looking denial response, never even attempting its own durable write, while the window's supposed first row was never actually recorded (§9.2 property 1's fail-closed guarantee would then hold only single-threaded).

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

    a failed aggregate-row write (the repeat-count summary row for an expired window) must never silently discard that repeat count -- see `_requeue_failed_aggregate`.
    A round-2 revision deleted the due window from `self._windows` before
    attempting its write and simply dropped it on failure (`except:
    continue`/`pass`), reasoning that re-inserting after releasing the
    process lock would race a concurrent `route()` for the same key; that
    race is real, but per-key locking (already required for B-2/m-2) is
    exactly what closes it -- the requeue now happens under the SAME key's
    lock the write attempt itself ran under, so no concurrent `route()`
    call for that key can be in flight at that moment.

    `self._key_locks` entries are pruned via reference counting (`_acquire_key_lock`/`_release_key_lock_ref`) once a key has no outstanding lock user AND no window left for it -- never while a lock might still be in use (which would let a fresh `route()` call silently start using a NEW, different `Lock` object for the same key, defeating serialization entirely).

    History: CH-0155
    """

    def __init__(self, sink: Any, *, window_s: float, clock: Callable[[], float]) -> None:
        self._sink = sink
        self._window_s = window_s
        self._clock = clock
        self._lock = threading.Lock()
        self._windows: dict[tuple[Any, ...], dict[str, Any]] = {}
        self._key_locks: dict[tuple[Any, ...], threading.Lock] = {}
        self._key_lock_refcount: dict[tuple[Any, ...], int] = {}
        # tracks whether the MOST RECENT aggregate-row write attempt (from any key) failed -- a single, process-wide flag, deliberately mirroring `_AuditBuffer`'s own N-2 state-transition logging discipline (log only on failing<->healthy transitions, never once per attempt).
        # history: CH-0154
        self._aggregate_write_failing = False

    def _acquire_key_lock(self, key: tuple[Any, ...]) -> threading.Lock:
        with self._lock:
            lock = self._key_locks.setdefault(key, threading.Lock())
            self._key_lock_refcount[key] = self._key_lock_refcount.get(key, 0) + 1
            return lock

    def _release_key_lock_ref(self, key: tuple[Any, ...]) -> None:
        """only prunes `self._key_locks[key]` when this is the LAST outstanding reference (refcount reaches 0) AND no window remains for the key -- see class docstring for why both conditions are required for this to be safe.

        History: CH-0153
        """
        with self._lock:
            remaining = self._key_lock_refcount.get(key, 1) - 1
            if remaining <= 0:
                self._key_lock_refcount.pop(key, None)
                if key not in self._windows:
                    self._key_locks.pop(key, None)
            else:
                self._key_lock_refcount[key] = remaining

    def _requeue_failed_aggregate(self, key: tuple[Any, ...], state: dict[str, Any]) -> None:
        """called only while holding this KEY's OWN `key_lock` (both call sites below), right after its aggregate-row write attempt raised -- puts `state["repeat_count"]` back where a future flush (periodic, explicit, shutdown, or the very next `route()` call for this same key) will retry it, instead of discarding it. Two cases, both safe specifically BECAUSE the
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

        History: CH-0152
        """
        with self._lock:
            existing = self._windows.get(key)
            if existing is not None:
                existing["repeat_count"] += state["repeat_count"]
            else:
                self._windows[key] = state

    def _note_aggregate_write_result(self, succeeded: bool) -> None:
        """fixed-message `logging.error`, only on a failing<-> healthy state TRANSITION (N-2's own established discipline) -- not once per attempt, which would reproduce the exact logging-DoS risk N-2 already closed for the buffer-overflow alert path.

        History: CH-0151
        """
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
        """force EVERY currently-open window to be flushed, expired or not -- used only at graceful shutdown. Once this process is about to stop, there is no "wait for the window to naturally expire" future left; treating every window as due now is what keeps a shutdown from silently discarding an in-progress window's accumulated repeat count (only ever sanctions losing counts to an actual crash, never to an orderly stop).

        History: CH-0150
        """
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
                        # never silently drop this repeat count -- put it back where a future attempt (this same sweep's own next pass, a later explicit/periodic flush, or the next `route()` call for this key) will retry it. Safe specifically because this
                        # happens under THIS key's own lock (no concurrent
                        # `route()`/sweep call for the SAME key can be
                        # touching `self._windows[key]` right now).
                        # history: CH-0149
                        self._requeue_failed_aggregate(key, state)
                        self._note_aggregate_write_result(False)
                    else:
                        self._note_aggregate_write_result(True)
            finally:
                self._release_key_lock_ref(key)

class DataService:
    """Public application facade; control state is deliberately private."""

    def __init__(self, credentials: CredentialStore, limits: ResourceLimits | None = None, topology: AuthorityTopology | None = None, audit: AuditSink | None = None, initial_cells: dict[str, StorageBackend] | None = None, clock: Callable[[], float] | None = None, cell_factory: CellFactory | None = None, control_plane_status: str = "unavailable", durable_audit: Any | None = None, audit_buffer_capacity: int = _DEFAULT_AUDIT_BUFFER_CAPACITY, denial_coalesce_window_s: float = _DENIAL_COALESCE_WINDOW_S, audit_alert_min_interval_s: float = _DEFAULT_AUDIT_FLUSH_INTERVAL_S, surfaces: dict[str, Any] | None = None, process_ceiling: int = 1) -> None:
        # R-9 (CCR-14, design docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md §1: "capability 申告は環境変数由来で composition root 注入"): whether this application-plane process' own `capabilities()` declares `control_plane: enabled` is a *deployer* fact this class cannot know on its own (a separated deployment, the default, means the application-plane process has no idea whether a control-plane process is running anywhere at all) -- it is constructor-injected, defaulting to the safe, honest `unavailable` so nothing short of an explicit composition-root decision (reading `R2DB_CONTROL_PLANE_STATUS`) ever declares `enabled`. Validated here too (not only at `main.py`'s env-parsing boundary) so any other caller constructing a `DataService` directly (this repository's own tests, the in-process conformance adapter) gets the same fail-loud guard against a typo'd status string, rather than silently publishing an invalid capability value.
        # history: CH-0148
        if control_plane_status not in {"enabled", "unavailable"}:
            raise ValueError("control_plane_status must be 'enabled' or 'unavailable'")
        self._control_plane_status = control_plane_status
        # `surfaces` is constructor-injected, same "deployer-declared, not derived" discipline as `control_plane_status` immediately above -- `main.py` (the real composition root) is the one caller that validates the two `R2DB_*_BASE_URL` environment variables' SHAPE at startup and assembles this dict from them; this class only ever echoes whatever it was given, verbatim, in `capabilities()` below. `None` (the default -- every caller, including this repository's own unit tests that construct `DataService` directly without opting in) omits the `surfaces` key from the response entirely, never a `"surfaces": None` value (contract `CapabilityDocument.surfaces` is an optional key, not a nullable one).
        # history: CH-0147
        self._surfaces = surfaces
        # Phase 10 WP-6a (design, contract 1.8.0): the deployer's own declared ceiling on how many processes may serve THIS plane's `surfaces` base URL at the same time -- constructor-injected, same "deployer-declared, not derived" discipline as `control_plane_status`/`surfaces` above. `main.py` (the real
        # composition root) is the one caller that resolves this from the
        # DB-side `process_ceilings` declaration (`platform_declarations.
        # read_platform_declarations(...).process_ceilings.data`) at
        # startup; every other caller (this repository's own unit tests,
        # the in-process conformance adapter) keeps the default `1` --
        # the single-process assumption every pre-Phase-10 caller already
        # made implicitly, so this default changes no existing behavior.
        # Validated here (not only at `main.py`'s own read/validate
        # boundary via `platform_declarations.validate_process_ceilings_
        # value`) so any other direct caller gets the same fail-loud guard
        # against a non-positive value, rather than silently publishing a
        # nonsensical `limit_enforcement` mapping.
        # history: CH-0146
        if isinstance(process_ceiling, bool) or not isinstance(process_ceiling, int) or process_ceiling < 1:
            raise ValueError("process_ceiling must be a positive integer")
        self._process_ceiling = process_ceiling
        self._credentials = credentials
        self.limits = limits or ResourceLimits()
        self.topology = topology or AuthorityTopology()
        self._audit = audit or AuditSink()
        # Phase 4 (design PHASE4_DURABLE_AUDIT_SINK_V1.md D-1/D-10): the
        # durable-designated sink -- `ApplicationAuditSink` (in-memory,
        # fault-injectable) by default, or a caller-supplied
        # `PostgresApplicationAuditSink` (`credential_store.py`, wired by
        # `main.py`'s composition root). `self._audit` above is untouched and stays the sole recorder for D-3's non-durable denial classes (everything outside `_DURABLE_DENIAL_CODES`'s inclusion list -- D-10's own instruction) -- this is a SEPARATE sink, not a replacement.
        # history: CH-0145
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
            # the legacy in-memory `self._audit` append is unchanged (pre-Phase-4 behaviour, this repository's own tests read it back via `ControlAuthority.audit_events()`) -- `_denial_event` below ADDS the durable/coalesced dispatch every other public method's `except FoundationError` reaches through `_event`'s own deny branch; this call site cannot use `_event` itself because authentication has not yet resolved a `canonical`/`AuthContext` to build one from.
            # history: CH-0144
            self._audit.append(event_class="authentication_denial", request_id=rid, application_id=None, actor_type="unknown", actor_id=None, role=None, operation="authenticate", target_kind="application", outcome="deny", reason_code=exc.code)
            self._denial_event(
                event_class="authentication_denial", request_id=rid, application_id=None,
                actor_type="unknown", actor_id=None, role=None, operation="authenticate",
                target_kind="application", reason_code=exc.code, target_id=None, details=exc.details,
            )
            raise

    def capabilities(self, context: AuthContext, *, concurrency_precharged: bool = False) -> dict[str, Any]:
        with self._slot(context, concurrency_precharged=concurrency_precharged) as canonical:
            # CCR-13 WP-5b: the WP-2-through-WP-5 provisional gate (design
            # R2DB_CCR13_STORAGE_V1.md §3) is removed in this same commit
            # (see `query`/`mutate`/`schema`/`catalog` below) -- this
            # declaration update is what makes that removal honest rather
            # than a new C-12 "declared unavailable, executes anyway" gap.
            # Contract 1.7.0: `alter_field` joins the developer-only schema-operation set -- `R-2` constraint declarations are enforced now (see `constraint_declarations` below), so it is no longer accurate to list it under `unsupported`.
            # history: CH-0143
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
                # "declaration = real behavior" rule).
                #
                # Flipped to 1.7.0 in phase 9 WP-2e (design docs/design/ PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md): the SAME commit as this host's own R-3 (`errors.details_vocabulary` 4-key details) and R-7 (`request_id` on every successful result) implementation -- the two 1.7.0 UNCONDITIONAL obligations -- never ahead of the behavior it declares (D-1 (7)'s xfail(strict=True) version gate is exactly what would catch that ordering mistake).
                #
                # Phase 10 WP-6a/pair-closing: flipped again to 1.8.0 in the SAME commit as this host's own `process_ceilings` mapping -- the version's one unconditional obligation, `limit_enforcement_scoped_to_deployment_behind_base_url` -- never ahead of the behavior it declares.
                # history: CH-0142
                "contract_version": "1.8.0",
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
                    # WP-2c (contract 1.7.0, D-5, ruling I-10/I-12): `enabled`
                    # -- the same commit that removes the `idempotency_key`
                    # provisional gate (`schema()`'s `_PROVISIONAL_UNSUPPORTED_
                    # SCHEMA_FIELDS`/`http.py`'s `post_mutate`) and gives it
                    # real record-and-replay effect (`structured.py`/
                    # `postgres.py`). `limits.idempotency_entries`/
                    # `idempotency_retention_ms` reach `capabilities()`'s
                    # `limits`/`limit_enforcement` documents automatically,
                    # through `ResourceLimits.as_dict()` below (ruling I-10/
                    # S-f -- C-05 V1 (e)'s `_CAPABILITY_CONDITIONED` requires
                    # both the moment this flips).
                    "idempotency": {"status": "enabled"},
                    "revision_preconditions": {"status": "enabled"},
                    "row_addressability": {"status": "enabled"},
                    # `cross_entity_mutation` needs the new `POST /v1/data/ mutations` endpoint (stubbed in as CAPABILITY_UNSUPPORTED, not executable), so it stays `unavailable` here: it has no executable operation at all. (`control_plane`, immediately below, is NOT in the same position any more: CCR-14 shipped the surface as a separate process, and its status is the deployer's own declaration -- the pre-CCR-14 wording that once grouped the two as "both remain unavailable" was corrected)
                    # history: CH-0141
                    "cross_entity_mutation": {"status": "unavailable"},
                    # reflects this instance's own constructor-injected deployer declaration -- never hardcoded (see __init__'s comment on this field).
                    # history: CH-0140
                    "control_plane": {"status": self._control_plane_status},
                    # Contract 1.7.0 (subordinate ruling 12): three new capabilities, honestly declared `unavailable` until each one's own capability WP flips it, in the SAME commit as the provisional gate that rejects every field it governs (`schema`/`mutate_result`/ `_query_outcome` above, `http.py`'s `post_mutate`/ `post_query`) -- P-3 (宣言と挙動は同一コミット).
                    #
                    # `constraint_declarations` is `enabled` -- `field_constraints`/`enum`/`nullable`/`alter_field` are no longer in `_PROVISIONAL_UNSUPPORTED_SCHEMA_FIELDS` (removed in this same commit) and are now enforced (`structured.py`/`postgres.py`).
                    # history: CH-0139
                    "constraint_declarations": {"status": "enabled"},
                    # `dry_run` is `enabled` -- `dry_run`/`plan` are no longer in `_PROVISIONAL_UNSUPPORTED_SCHEMA_FIELDS` (schema side) and `mutate_result`/`_mutate_outcome` (mutation side) no longer refuse them outright, in this same commit as `structured.py`/`postgres.py`'s own real dry_run/plan enforcement. WP-2d
                    # (`request_budget`) flips its own entry the same way,
                    # in its own commit.
                    # history: CH-0138
                    "dry_run": {"status": "enabled"},
                    # WP-2d (contract 1.7.0, D-6, ruling B-4): `enabled` --
                    # the same commit that removes every `budget` provisional
                    # gate (`_query_outcome`/`mutate_result`/`schema()`'s
                    # `_PROVISIONAL_UNSUPPORTED_SCHEMA_FIELDS`) and gives it
                    # real narrowing effect via `narrow_limits_by_budget`
                    # (`limits.py`).
                    "request_budget": {"status": "enabled"},
                },
                "limits": self.limits.as_dict(),
                # `idempotency_retention_ms` joins `execution_ms` in the `reference_wall_clock` set -- both are wall-clock DURATIONS a deployment cannot drive to a deterministic N/N+1 boundary within a bounded test run (unlike every COUNT-valued class here, `idempotency_entries` included, which genuinely IS `enforced`: a record's own retention window is checked lazily, against real elapsed time, not a request-counted budget).
                # Phase 10 WP-6a (design, contract 1.8.0): three regions, not two. Region (i) (request-scoped: every class
                # below not named in the other two sets) is unaffected by
                # `process_ceiling` -- unchanged from before this WP.
                # Region (ii) (`requests_per_minute`/`concurrency` --
                # bound by in-memory, per-process state, `self._rate_
                # windows`/`self._active`) reads `enforced` only while
                # `process_ceiling == 1` and `deployment_required` once it
                # is `>= 2` (contract 1.8.0's own enforcement-scope
                # definition: a per-process bound is `enforced` for the
                # whole deployment only while exactly one process may
                # serve this plane's base URL). Region (iii)
                # (`idempotency_entries` -- bound in PostgreSQL,
                # `postgres.py`'s own `_idempotency_reserve`) stays
                # `enforced` regardless of `process_ceiling` -- this class
                # does not resolve within one request.
                # history: CH-0137
                "limit_enforcement": {
                    name: (
                        "reference_wall_clock" if name in ("execution_ms", "idempotency_retention_ms")
                        else ("enforced" if self._process_ceiling <= 1 else "deployment_required") if name in _IN_MEMORY_PROCESS_WIDE_LIMIT_CLASSES
                        else "enforced"
                    )
                    for name in self.limits.as_dict()
                },
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
            # `surfaces` is an optional key -- present only when this instance was constructed with one (`__init__`'s own comment on `self._surfaces`). Never a
            # `"surfaces": None` entry.
            # history: CH-0136
            if self._surfaces is not None:
                document["surfaces"] = self._surfaces
            return document

    def query(self, context: AuthContext, entity: str, *, select: list[str], where: list[dict[str, Any]] | None = None, page_size: int = 100, order_by: list[dict[str, Any]] | None = None, cursor: str | None = None, request_id: str | None = None) -> list[dict[str, Any]]:
        """Plain-item-list form, unchanged in shape since before CCR-13 (every existing caller --, the in-process conformance adapter -- keeps working against exactly this return type). `order_by`/`cursor` (CCR-13) are accepted here too (so this method alone is enough to exercise/test them against the facade), but the pagination continuation itself only reaches a caller through `query_page` below, which `http.post_query` uses.

        History: CH-0135
        """
        return list(self._query_outcome(context, entity, select=select, where=where, page_size=page_size, order_by=order_by, cursor=cursor, request_id=request_id).items)

    def query_page(self, context: AuthContext, entity: str, *, select: list[str], where: list[dict[str, Any]] | None = None, page_size: int = 100, order_by: list[dict[str, Any]] | None = None, cursor: str | None = None, request_id: str | None = None, budget: dict[str, int] | None = None, concurrency_precharged: bool = False) -> "QueryPage":
        """The HTTP-facing shape (`{items, next_page, revisions}`,
        `spec/data-service-api.v1.json`'s `QueryResult`) -- used by `http.
        post_query` instead of `query` above, since building a real
        `next_page`/`revisions` needs `QueryOutcome.next_cursor`/
        `.revisions`, which the plain-list `query()` deliberately does not
        expose (kept byte-for-byte backward compatible with every pre-
        CCR-13 caller). `revisions` is always index-aligned with `items`: `revision_preconditions` is declared `enabled`, and every entity both cells provision is `mutable`, so a query response always carries revisions.

        `budget` (contract 1.7.0, `QueryRequest.budget`): real, given full effect by `_query_outcome` below via `limits.narrow_limits_by_budget` -- `capabilities().request_budget` is `enabled` as of this commit. `result_items`/`execution_ms` are the two classes a query's own `budget` may narrow; an applicable-but-invalid or inapplicable `budget` is refused `VALIDATION_FAILED` before target existence.

        History: CH-0134
        """
        # Contract 1.7.0: resolved HERE, once, so the SAME value both reaches `QueryPage.request_id` below and is the one `_query_outcome` uses for its own audit event -- the generation point for the request/response pair a caller sees, never re-derived a second time for the response body (Q-1: "HTTP 層は 再生成しない" generalizes to "no layer re-derives it").
        # history: CH-0133
        rid = request_id or str(uuid.uuid4())
        outcome = self._query_outcome(context, entity, select=select, where=where, page_size=page_size, order_by=order_by, cursor=cursor, request_id=rid, budget=budget, concurrency_precharged=concurrency_precharged)
        return QueryPage(items=list(outcome.items), next_page=outcome.next_cursor, revisions=list(outcome.revisions or []), request_id=rid)

    def _query_outcome(self, context: AuthContext, entity: str, *, select: list[str], where: list[dict[str, Any]] | None, page_size: int, order_by: list[dict[str, Any]] | None, cursor: str | None, request_id: str | None, budget: dict[str, int] | None = None, concurrency_precharged: bool = False):
        rid = request_id or str(uuid.uuid4())
        try:
            with self._slot(context, concurrency_precharged=concurrency_precharged) as canonical:
                if not isinstance(select, list) or not isinstance(page_size, int) or isinstance(page_size, bool):
                    fail("VALIDATION_FAILED", "Projection and page size have invalid types.", details=violation("request_schema"))
                if where is not None and not isinstance(where, list):
                    fail("VALIDATION_FAILED", "Filter must be a list.", details=violation("request_schema", field="where", declared_type="array", observed_type=observed_type_of(where)))
                if order_by is not None and not isinstance(order_by, list):
                    fail("VALIDATION_FAILED", "order_by must be a list.", details=violation("request_schema", field="order_by", declared_type="array", observed_type=observed_type_of(order_by)))
                if cursor is not None and not isinstance(cursor, str):
                    fail("VALIDATION_FAILED", "Cursor must be a string.", details=violation("request_schema", field="cursor", declared_type="string", observed_type=observed_type_of(cursor)))
                request = {"entity": entity, "select": select, "where": where or [], "page_size": page_size, "order_by": order_by or [], "cursor": cursor}
                self.limits.check_request(request)
                self.limits.check_depth(request)
                # Contract 1.7.0 (addendum 2 S-l, ruling): `request_budget` is `enabled` -- `budget` validity (applicable class / integer >= 1 / not above the deployed bound) is checked here, at request-shape time, before target existence -- the SAME single point every endpoint uses (`limits.narrow_limits_by_budget`) to turn `budget` into the "effective limits" every existing check point below reads, without any of them being rewritten.
                # history: CH-0132
                effective_limits = narrow_limits_by_budget(self.limits, budget, "query")
                predicates = [parse_predicate(item) for item in (where or [])]
                deadline = self._clock() + effective_limits.execution_ms / 1000
                outcome = self._cells[canonical.application_id].query(
                    entity, select=select, where=predicates, page_size=page_size, order_by=order_by, cursor=cursor, limits=effective_limits, deadline=deadline, clock=self._clock
                )
                # `query` never passes through the confirmation choke -- always buffer-class.
                # history: CH-0131
                self._event(canonical, operation="query", outcome="allow", target_kind="entity", event_class="data_operation", request_id=rid)
                return outcome
        except FoundationError as exc:
            self._event(context, operation="query", outcome="deny", target_kind="entity", reason_code=exc.code, event_class="authorization_denial", request_id=rid, details=exc.details)
            raise

    def mutate(self, context: AuthContext, entity: str, operations: list[dict[str, Any]], *, transaction: str = "atomic", request_id: str | None = None) -> int:
        """Plain affected-count form, unchanged in shape since before CCR-13 (every existing caller --, the in-process conformance adapter -- keeps working against exactly this return type). `mutate_result` below is the richer shape
        `http.post_mutate` uses.

        History: CH-0130
        """
        return self._mutate_outcome(context, entity, operations, transaction=transaction, request_id=request_id).affected

    def mutate_result(self, context: AuthContext, entity: str, operations: list[dict[str, Any]], *, transaction: str | None = None, request_id: str | None = None, dry_run: bool = False, plan: str | None = None, budget: dict[str, int] | None = None, idempotency_key: str | None = None, concurrency_precharged: bool = False) -> "MutationResult":
        """The HTTP-facing shape (`{affected, assigned_addresses}`, `spec/data-service-api.v1.json`'s `MutationResult`) -- used by `http.post_mutate` instead of `mutate` above, mirroring the `query`/`query_page` split.

        `dry_run`/`plan` (contract 1.7.0, D-4): real, given full effect below -- `capabilities().dry_run` is `enabled` as of this commit. `budget` (contract 1.7.0, D-6) and `idempotency_key` (contract 1.7.0, D-5) are likewise real as of this commit -- `capabilities().request_budget`/`.idempotency` are both `enabled`; `_mutate_outcome` below validates/narrows `budget` and consults/records `idempotency_key` at exactly the request stages `narrow_limits_by_budget`'s/`transact`'s own comments describe.

        History: CH-0129
        """
        outcome = self._mutate_outcome(context, entity, operations, transaction=transaction, request_id=request_id, dry_run=dry_run, plan=plan, budget=budget, idempotency_key=idempotency_key, concurrency_precharged=concurrency_precharged)
        return MutationResult(
            # Contract 1.7.0: `outcome.request_id` -- THIS execution's own value for a real commit/dry_run, or the ORIGINAL execution's own value for an idempotency replay (`MutationOutcome.request_id`'s own comment) -- never the resend's own `rid` (which `_mutate_outcome` below already used for the resend's own, separate audit event).
            # history: CH-0128
            request_id=outcome.request_id,
            affected=outcome.affected,
            # D-4 (3)/A-9: a dry-run mutation result never carries `assigned_addresses` -- the addresses a real execution would assign are not settled (an insert may still have tentatively consumed real id-sequence values, but this response never reports them). `None`, not `[]` -- `http.post_mutate` omits the key itself on `None`, matching the contract's "does not carry" wording.
            # history: CH-0127
            assigned_addresses=None if dry_run else list(outcome.assigned_addresses or []),
            committed=outcome.committed,
            plan=outcome.plan if dry_run else None,
        )

    def _mutate_outcome(self, context: AuthContext, entity: str, operations: list[dict[str, Any]], *, transaction: str | None, request_id: str | None, dry_run: bool = False, plan: str | None = None, budget: dict[str, int] | None = None, idempotency_key: str | None = None, concurrency_precharged: bool = False):
        rid = request_id or str(uuid.uuid4())
        try:
            with self._slot(context, concurrency_precharged=concurrency_precharged) as canonical:
                # `transaction` is never a contract-level *default* -- `None` here means the caller's own request object never carried the key at all (both `http.post_mutate` and the in-process port omit the kwarg rather than resolving it to `"atomic"` before this call). `resolved_transaction` is used for every
                # behavioural decision (the capability gate below); the
                # RAW `transaction` value (still `None` when omitted) is
                # what `plan_request` below reflects, so a request that
                # carried `transaction: "atomic"` explicitly digests
                # differently from one that omitted the key entirely, even
                # though both behave identically otherwise.
                # history: CH-0126
                resolved_transaction = transaction if transaction is not None else "atomic"
                if resolved_transaction != "atomic":
                    fail("CAPABILITY_UNSUPPORTED", "This foundation exposes atomic transactions only.", details=violation("capability", field="transaction"))
                if not isinstance(operations, list):
                    fail("VALIDATION_FAILED", "Mutations must be a list.", details=violation("request_schema", field="operations"))
                # Ruling I-12/port v1.11 compatibility: an HTTP-originated
                # call always supplies `idempotency_key` directly (the
                # contract-level `MutationRequest.idempotency_key`); the
                # in-process port instead carries a request's single,
                # uniform key duplicated onto every operation item (this
                # peer's own internal, non-HTTP mutation-item shape,
                # `conformance/conformance_adapter_r2db.py`'s `_build_
                # mutation_item`) -- folded here ONLY when the explicit
                # parameter is absent, never overriding it.
                effective_idempotency_key = idempotency_key if idempotency_key is not None else fold_operation_idempotency_keys(operations)
                request = {"entity": entity, "operations": operations}
                self.limits.check_request(request)
                self.limits.check_depth(request)
                # Contract 1.7.0 (addendum 2 S-l, ruling): see `_query_outcome`'s identical comment -- the SAME single point (`narrow_limits_by_budget`) every endpoint uses, checked here at request-shape time, before target-existence.
                # history: CH-0125
                effective_limits = narrow_limits_by_budget(self.limits, budget, "mutate")
                deadline = self._clock() + effective_limits.execution_ms / 1000
                # Contract 1.7.0 (S-a): the contract-level request object a `plan` commits to -- `operations`/ `transaction`/`budget`, plus this request's own target `entity` (addendum 2: "computed from the request itself" includes the request's URL path segment, not only its body -- `MutationRequest` itself has no `entity` property, but the plan digest is not scoped to `MutationRequest` alone). Placed at the
                # object's own top level so a plan captured for one entity's
                # dry_run, presented against a DIFFERENT entity's apply
                # (identical `operations`/`transaction`/`budget`, identical
                # schema_revision), fails PRECONDITION_FAILED fail-closed,
                # rather than being silently honored. `dry_run`/`plan`
                # themselves are excluded (S-a's own exclusion pair, applied
                # again defensively inside `normalize_request_for_plan`).
                # `transaction` is included only when the caller's own request object actually carried the key (see above) -- never the resolved/defaulted value.
                # history: CH-0124
                plan_request: dict[str, Any] = {"entity": entity, "operations": operations}
                if transaction is not None:
                    plan_request["transaction"] = transaction
                if budget is not None:
                    plan_request["budget"] = budget
                # `idempotency_key` is INCLUDED in the plan digest (only `plan`/`dry_run` are excluded there, `normalize_request_for_plan`'s own 2-key exclusion) even though it is excluded from its OWN digest (`normalize_request_for_idempotency`'s 3-key exclusion, `idempotency_digest` below) -- a `plan` token captured with one key (or none) must not verify against a request presenting a different one.
                # history: CH-0123
                if effective_idempotency_key is not None:
                    plan_request["idempotency_key"] = effective_idempotency_key
                # Phase 4, extended by D-4 (4)/U-2 = (A): the hook is only ever USED by the backend when this batch turns out to pass through the confirmation choke (a confirmed `delete`) -- building it unconditionally here is cheap (no I/O happens until/unless `pre_commit()` is actually called) and keeps this call site identical regardless of what the batch turns out to contain, matching `schema`'s own unconditional hook below. A
                # `dry_run`, though, never gets one AT ALL -- not merely
                # one that is never called -- so no audit line can ever be
                # written for it, by construction (U-2 = (A): "監査行を一切
                # 書かない", not "書くが呼ばない").
                # history: CH-0122
                hook = None if dry_run else self._make_audit_hook(canonical, event_class="data_operation", operation="mutate", target_kind="entity", request_id=rid)
                outcome = self._cells[canonical.application_id].transact(
                    entity, operations, effective_limits, deadline=deadline, clock=self._clock, audit_hook=hook,
                    dry_run=dry_run, plan=plan, plan_request=plan_request, idempotency_key=effective_idempotency_key,
                    request_id=rid,
                )
                # D-4 (4)/U-2 = (A): a dry_run that reached this point
                # reached the "would succeed" decision -- no audit event
                # (buffer-class OR the legacy in-memory sink `_event`
                # itself unconditionally appends to) is written for it.
                # `outcome.destructive` reports whether the backend's pre-commit hook already durably recorded this batch -- `already_durable` tells `_event` to skip the buffer-class enqueue in that case (at most one durable row per operation). Contract 1.7.0 (D-5 (1)(v), ruling I-11/J-4, WP-2c/WP-2cd): `outcome.replayed` -- a resend answered from an idempotency record still earns its OWN audit line (SI-14 audit N-5: a destructive resend must never return `committed: true` while leaving zero evidence of its own that this Application was touched at time T) -- `outcome="replayed"`, never `"allow"`, keeps a resend distinguishable from a genuine new execution in the audit trail itself; it carries THIS resend's own `request_id` (never the original), and, like every event this method emits, never the `idempotency_key` value. Always
                # `already_durable=False`: a replay never invokes the
                # pre-commit hook (nothing below the idempotency lookup
                # executed), so no durable row has already been written for
                # THIS event the way a genuinely destructive fresh commit's
                # hook already wrote one for its own.
                # history: CH-0121
                if not dry_run:
                    if outcome.replayed:
                        self._event(canonical, operation="mutate", outcome="replayed", target_kind="entity", event_class="data_operation", request_id=rid, already_durable=False)
                    else:
                        self._event(canonical, operation="mutate", outcome="allow", target_kind="entity", event_class="data_operation", request_id=rid, already_durable=outcome.destructive)
                return outcome
        except FoundationError as exc:
            self._event(context, operation="mutate", outcome="deny", target_kind="entity", reason_code=exc.code, event_class="operation_denial", request_id=rid, details=exc.details)
            raise

    def schema(self, context: AuthContext, operation: dict[str, Any] | None, *, request_id: str | None = None, concurrency_precharged: bool = False) -> "SchemaOutcome":
        """Always returns `SchemaOutcome` (`.committed`/`.revision`/ `.descriptor`/`.plan`, contract 1.7.0, D-4) -- a pure passthrough of `ApplicationCell.apply_schema`/`PostgresCell.apply_schema`'s own return, which review round F-8 unified to one shape regardless of whether `operation` carries `dry_run`/`plan`. Every pre-1.7.0 direct caller of this method reads `.revision` off the result; the in-process conformance adapter's own `hasattr( result, "revision")` branch already handles a non-`int` result unchanged (it never assumed `int`).

        `budget`/`idempotency_key` (contract 1.7.0, D-6/D-5): both real as of this commit -- the provisional gate that used to reject either field outright (`_PROVISIONAL_UNSUPPORTED_SCHEMA_FIELDS`) is removed in this same commit as `capabilities().request_budget`/`.idempotency` both flipping to `enabled`.

        History: CH-0120
        """
        rid = request_id or str(uuid.uuid4())
        # Contract 1.7.0: `SchemaOperationRequest` is the single flat operation object itself (no separate `operations` wrapper the way `MutationRequest` has) -- `dry_run`/`plan` are simply keys already present on `operation`, read here (before `_slot`) so the audit-hook/dispatch decisions below can already act on them.
        # history: CH-0119
        dry_run = bool(isinstance(operation, dict) and operation.get("dry_run", False))
        plan = operation.get("plan") if isinstance(operation, dict) else None
        try:
            with self._slot(context, concurrency_precharged=concurrency_precharged) as canonical:
                if not isinstance(operation, dict):
                    fail("VALIDATION_FAILED", "Schema operation must be an object.", details=violation("request_schema"))
                # Authority is checked before touching request content at
                # all, so a non-developer credential gets FORBIDDEN/403 for
                # any schema operation, before any shape/capability
                # question is even considered. a dry run walks the SAME gates a real request does, no early-out).
                # history: CH-0118
                if canonical.role != "developer":
                    fail("FORBIDDEN", "Developer authority is required for schema operations.", status=403)
                self.limits.check_request(operation)
                self.limits.check_depth(operation)
                # Contract 1.7.0 (addendum 2 S-l, ruling): see `_query_outcome`'s identical comment.
                # history: CH-0117
                effective_limits = narrow_limits_by_budget(self.limits, operation.get("budget"), "schema")
                deadline = self._clock() + effective_limits.execution_ms / 1000
                # Contract 1.7.0 (S-a): the contract-level request object a `plan` commits to -- `operation` itself already IS that object (`SchemaOperationRequest`'s own flat shape), minus `plan`/`dry_run` (S-a's exclusion pair, applied again defensively inside `normalize_request_for_plan`). `idempotency_key`, when present, stays IN this object (only `plan`/`dry_run` are excluded here) -- `idempotency_digest` below applies its own, separate 3-key exclusion.
                # history: CH-0116
                plan_request = {key: value for key, value in operation.items() if key not in ("plan", "dry_run")}
                idempotency_key = operation.get("idempotency_key")
                # unconditionally fail-closed -- every schema operation, not only a confirmed destructive one (unlike `mutate` above). Extended by D-4 (4)/U-2 = (A): a `dry_run` never gets a hook AT ALL -- not merely one that is never called -- so no audit line can ever be written for it, by construction.
                # history: CH-0115
                hook = None if dry_run else self._make_audit_hook(canonical, event_class="privilege_sensitive", operation="schema", target_kind="entity", request_id=rid)
                outcome = self._cells[canonical.application_id].apply_schema(
                    operation, developer=canonical.role == "developer", limits=effective_limits, deadline=deadline,
                    clock=self._clock, audit_hook=hook, dry_run=dry_run, plan=plan, plan_request=plan_request,
                    idempotency_key=idempotency_key, request_id=rid,
                )
                # D-4 (4)/U-2 = (A): no audit event at all for a dry_run
                # that reached this point (the "would succeed" decision).
                # Ruling I-11/J-4 (D-5 (1)(v), WP-2c/WP-2cd): a replay
                # (`outcome.replayed`) still earns its own `outcome=
                # "replayed"` line -- see `_mutate_outcome`'s identical
                # comment (a resent `drop_entity` must not return
                # `committed: true` with zero evidence of its own). Unlike
                # a genuine schema commit (`already_durable=True` -- the
                # pre-commit hook already wrote the durable row
                # synchronously), a replay never invoked that hook at all,
                # so `already_durable=False` here.
                if not dry_run:
                    if outcome.replayed:
                        self._event(canonical, operation="schema", outcome="replayed", target_kind="entity", event_class="privilege_sensitive", request_id=rid, already_durable=False)
                    else:
                        self._event(canonical, operation="schema", outcome="allow", target_kind="entity", event_class="privilege_sensitive", request_id=rid, already_durable=True)
                return outcome
        except FoundationError as exc:
            self._event(context, operation="schema", outcome="deny", target_kind="entity", reason_code=exc.code, event_class="privilege_denial", request_id=rid, details=exc.details)
            raise

    def catalog(self, context: AuthContext, *, request_id: str | None = None, concurrency_precharged: bool = False) -> dict[str, Any]:
        rid = request_id or str(uuid.uuid4())
        try:
            with self._slot(context, concurrency_precharged=concurrency_precharged) as canonical:
                # The full CCR-13 `EntityDescriptor` shape (mutation_class/
                # address_fields/address_reuse/unique_keys) -- `row_
                # addressability` is now declared `enabled`, so this
                # publishes exactly what the cell itself already computes,
                # with no narrowing.
                entities = self._cells[canonical.application_id].catalog()
                # `catalog` never passes through the confirmation choke -- always buffer-class.
                # history: CH-0114
                self._event(canonical, operation="catalog", outcome="allow", target_kind="entity", event_class="data_operation", request_id=rid)
                return {"application_scope": canonical.application_id, "entities": entities}
        except FoundationError as exc:
            self._event(context, operation="catalog", outcome="deny", target_kind="entity", reason_code=exc.code, event_class="authorization_denial", request_id=rid, details=exc.details)
            raise

    def deny_unsupported(self, context: AuthContext, *, operation: str, message: str, request_id: str | None = None, concurrency_precharged: bool = False) -> None:
        """Refuse a capability this foundation does not implement, while still passing through `_slot`'s rate/concurrency accounting and emitting a denial audit event -- exactly like every other application-plane method below, instead of being a bare pre-`_slot` `fail()` call that an unauthenticated-looking credential could spend for free (R12).

        `http.py`'s `post_audit_query`/`post_cross_entity_mutate` stub
        handlers use this for the two contract endpoints this foundation
        declares `unavailable`/has no execution path for at all
        (`audit_query`, `cross_entity_mutation`); this always raises
        `CAPABILITY_UNSUPPORTED`, it never returns.

        this denial's `reason_code` is always `CAPABILITY_UNSUPPORTED` -- not in D-3's durable-code inclusion list, so `_event`'s deny dispatch never routes it through the durable/ coalesced path (unchanged from pre-Phase-4 behaviour: this method never wrote a durable row before this WP either).

        History: CH-0113
        """
        rid = request_id or str(uuid.uuid4())
        try:
            with self._slot(context, concurrency_precharged=concurrency_precharged):
                # the request AS A WHOLE is what is unsupported here (this foundation has no execution path for the endpoint at all) -- `field` is omitted, matching `errors.details_vocabulary.CAPABILITY_UNSUPPORTED`'s own "omitted where the request as a whole is what is unsupported" clause.
                # history: CH-0112
                fail("CAPABILITY_UNSUPPORTED", message, details=violation("capability"))
        except FoundationError as exc:
            self._event(context, operation=operation, outcome="deny", target_kind="entity", reason_code=exc.code, event_class="operation_denial", request_id=rid, details=exc.details)
            raise

    @contextmanager
    def _slot(self, context: AuthContext, *, concurrency_precharged: bool = False) -> Iterator[AuthContext]:
        """`concurrency_precharged` mirrors `ControlPlaneService.check_rate()`'s own `rate_precharged` parameter (`control_plane.py::check_rate`'s docstring) -- an HTTP caller that already reserved this SAME deployment's own concurrency slot BEFORE authentication (via `acquire_concurrency_slot()` below, called from `http.py` ahead of `_authenticate`) passes `concurrency_precharged=True` into the eventual `DataService` call so this method does not reserve a SECOND slot for the identical logical request -- otherwise every HTTP request would cost 2 units of `limits.concurrency` instead of 1, halving the deployment's own real capacity relative to its declaration (completion condition 3). Every OTHER caller (this
        repository's own tests, the in-process conformance adapter, which
        call a `DataService` method directly with no pre-auth reservation
        of their own) keeps the default `False` -- unchanged from before
        this WP: `_check`/`_acquire_rate` run exactly as before, and the
        concurrency slot is still acquired HERE, inside this method, in
        exactly the same relative position (after `_check`/`_acquire_rate`,
        around the caller's own business logic) `hold_in_flight`'s own
        stall point already depends on (`conformance-tests/adapter.py`'s
        `hold_in_flight` docstring: "AFTER the concurrency counter is
        acquired and BEFORE DB execution").

        `_check`/`_acquire_rate` stay POST-authentication in every case:
        `_acquire_rate` is keyed by `context.credential_id` (`_acquire_
        rate`'s own signature), which does not exist before authentication
        resolves one -- only the credential-independent concurrency bound
        can be, and now is, taken before authentication.

        History: CH-0111
        """
        canonical = self._check(context)
        self._acquire_rate(canonical)
        if concurrency_precharged:
            yield canonical
            return
        with self._active_lock:
            if self._active >= self.limits.concurrency:
                fail("LIMIT_EXCEEDED", "Concurrency limit exceeded.", status=429, details={"resource": "concurrency", "limit_class": "concurrency", "limit": self.limits.concurrency})
            self._active += 1
        try:
            yield canonical
        finally:
            with self._active_lock:
                self._active -= 1

    @contextmanager
    def acquire_concurrency_slot(self) -> Iterator[None]:
        """pre-authentication concurrency admission for the HTTP surface -- mirrors `ControlPlaneService.check_rate()`'s own pre-auth admission shape on the control plane (`control_http.py`'s module header: "charged before anything else, including authentication"), applied here to `concurrency` rather than `requests_per_minute` (this class alone is credential-independent, so it alone can be evaluated before a credential is known at all -- see `_slot`'s own docstring).

        `http.py` enters this BEFORE calling `_authenticate`, and holds it
        for the caller's own ENTIRE request -- authentication, body
        parsing, and the eventual `DataService` business call, which
        itself passes `concurrency_precharged=True` into `_slot` so the
        SAME single reservation is never taken twice for one request
        (`_slot`'s own docstring). With this reservation taken first, at most `limits.
        concurrency` requests -- authenticated or not -- are ever
        in-flight at once, so demand on `_authenticate`'s own platform
        pool is bounded by the SAME declared class a caller's own
        `capabilities()` document already advertises as `concurrency`.

        A refusal here raises `fail()` directly, exactly like `_slot`'s
        own concurrency branch did before this WP -- no `_event`/durable-
        audit call runs between this raise and the ASGI layer's own
        `except FoundationError` (`http.py::_endpoint`), so this denial is
        never durably audited, the same "rate-class pre-auth denial is
        never durably audited" rule `_acquire_rate`'s own denial already
        followed (there is no `context`/`canonical` to attribute it to
        yet in any case).

        Deliberately its OWN copy of the check-then-increment block `_slot` above also carries (not a shared helper the two call into) -- `tests/test_threadpool_offload.py::test_slot_check_then_increment_is_lexically_inside_the_active_lock` pins that exact block LEXICALLY INSIDE `_slot` itself (an AST scan), so factoring it out into a shared private method would have turned that pre-existing, unrelated test red as a side effect of this WP -- an acceptable small duplication (four lines) rather than disturbing a pinned mutation-test shape this WP does not own.

        History: CH-0110
        """
        with self._active_lock:
            if self._active >= self.limits.concurrency:
                fail("LIMIT_EXCEEDED", "Concurrency limit exceeded.", status=429, details={"resource": "concurrency", "limit_class": "concurrency", "limit": self.limits.concurrency})
            self._active += 1
        try:
            yield
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
        (`outcome="deny"`). Always appends to the pre-existing legacy in-memory `self._audit` first, unconditionally (D-10: this sink's behaviour is completely unaffected by anything below) -- then applies Phase 4's durable-recording dispatch:

        - `already_durable=True` (only ever passed by `mutate`/`schema`
          above, when the backend's own pre-commit hook already durably
          recorded this exact event): return immediately. D-10's "at most
          one durable row per operation" rule.
        - `outcome == "deny"`: `details["origin"] == "audit_sink"` means this denial's `SERVICE_UNAVAILABLE` was produced by the audit pipeline itself already failing to record this very operation (a pre-commit sink failure, a commit-failure error-row write, a coalesced-denial first-insert failure) -- routing it through `_route_denial` again would be a second (or third) durable write for what is still logically one operation, so this returns without doing anything further. Otherwise, any reason code outside D-3's durable-code inclusion list (`_DURABLE_DENIAL_CODES` -- not merely the 4 originally named) returns without any durable/buffered record at all; every other reason code is fail-closed-class and goes through the coalescing denial router (which may itself raise `SERVICE_UNAVAILABLE`).
        - `outcome == "allow"`: buffer-class -- `query`/`catalog` always reach here (they never pass through the confirmation choke), and `mutate` reaches here only when its batch did NOT (`already_durable=False`).

        History: CH-0109
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
        """The shared fail-closed/coalesced-denial dispatch, used both by `_event`'s own deny branch and by `authenticate`'s except clause (which has no `canonical`/`AuthContext` to route through `_event` at all -- authentication itself is what failed).
        `details` mirrors `_event`'s own audit-sink-origin short-circuit.

        History: CH-0108
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
        """builds the `ApplicationAuditHook` passed to `StorageBackend.transact`/`apply_schema` as `audit_hook` -- every field the durable row needs is already resolved here (this is `DataService`'s own job; the backend has no identity/request context of its own beyond what it is given).

        History: CH-0107
        """
        fields = {
            "event_class": event_class, "request_id": request_id, "application_id": canonical.application_id,
            "actor_type": "application_credential", "actor_id": canonical.credential_id, "role": canonical.role,
            "operation": operation, "target_kind": target_kind, "target_id": None,
        }
        return _PreCommitHook(self._durable_audit, fields)

    def flush_audit_buffer(self, *, force_expire_denial_windows: bool = False) -> None:
        """Phase 4 (design D-4/§7.3/§7.4): synchronously drains the bounded buffer (writing it as one batch), retries the sticky overflow-alert row if one is pending and due, and sweeps denial-coalescing windows (writing their repeat-count summary row). Called on demand by this repository's own tests and by a
        composition root's periodic timer alike -- there is nothing
        time-sensitive about calling this more or less often beyond how
        promptly buffered/coalesced evidence becomes durable (D-4's own
        "periodic or threshold" flush-trigger latitude).

        flushes EVERY currently-open denial-coalescing window, expired or not, instead of only expired ones -- used exactly once, by a composition root's graceful-shutdown path. Without this, a window still short of its own `window_s` at the moment the process stops loses its accumulated repeat count entirely (only sanctions losing counts to an actual crash, not to an orderly stop); the default (periodic timer, explicit test calls) stays `False` -- an in-progress window still has a legitimate future to expire into naturally and must not be cut short just because something else happened to call this method.

        History: CH-0106
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
                fail("VALIDATION_FAILED", "Application enabled state must be boolean.", details=violation("request_schema", field="enabled", declared_type="boolean", observed_type=observed_type_of(enabled)))
            self._service._set_application_disabled(application_id, not enabled)
            self._control_event(operation="enable_application" if enabled else "disable_application", outcome="allow", target=application_id, event_class="application_lifecycle")
        except FoundationError as exc:
            self._control_event(operation="enable_application" if enabled else "disable_application", outcome="deny", target=application_id, reason_code=exc.code, event_class="control_failure")
            raise

    def set_credential_state(self, credential_id: str, *, enabled: bool | None = None, revoked: bool | None = None, work: Any = None) -> None:
        """`work` is keyword-only and defaults to `None` (CCR-14): when omitted, this method self-manages exactly as before -- opens its own `unit_of_work()`, commits/reverts exactly one call's worth of state, and every pre-WP-3 caller (this repository's own tests, the in-process conformance adapter) keeps working unchanged. When a caller supplies its own already-open `work` handle (`ControlPlaneService`'s in-memory backend it needs the credential-state change and its own `control_audit` sink append to land in the *same* transaction), this method uses that handle directly instead of opening a second one -- never both. `work`'s type is deliberately
        untyped (`Any`) rather than importing `auth._InMemoryWork`/
        `credential_store._PostgresWork` here: this module stays agnostic to
        which store implementation (in-memory or PostgreSQL) it is holding,
        exactly as it already is everywhere else (`self._service._credentials`
        is never type-narrowed in this class).

        History: CH-0105
        """
        try:
            if work is not None:
                self._service._credentials.set_state(credential_id, enabled=enabled, revoked=revoked, work=work)
            else:
                # R-6/§8 B-2: chase `CredentialStore`/`PostgresCredentialStore`'s new `unit_of_work()`-required call form -- semantics are unchanged (this still commits/reverts exactly one call's worth of state, same as before; `ControlAuthority`'s own audit trail stays on the existing in-memory `AuditSink` below, not on the new `control_audit` table, which only `ops.py`'s ritual/CLI-path writes to in this work package).
                # history: CH-0104
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

        Rework (coordinator item 3): returns the composed bearer `self._service._credentials.add(...)` itself now returns (design "合成は store/service 層のみ" principle) -- this out-of-band lifecycle-authority entry point is an issuance point (the conformance in-process plug's own privileged-setup `issue_credential` calls this directly does not use this method at all -- see that module's own `cmd_issue_credential`, which calls the store's `add` directly and gets the same composed return value there). Every pre-WP-2 caller that ignored the
        previous `None` return is unaffected (Python permits discarding a
        return value freely) -- `test_control_authority_work_parameter_
        defaults_preserve_existing_callers` pins this explicitly.

        History: CH-0103
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
                fail("VALIDATION_FAILED", "Authorization state availability must be boolean.", details=violation("request_schema", field="available", declared_type="boolean", observed_type=observed_type_of(available)))
            self._service._credentials.available = available
            self._control_event(operation="set_authorization_state_available", outcome="allow", target="authorization", event_class="control_state")
        except FoundationError as exc:
            self._control_event(operation="set_authorization_state_available", outcome="deny", target="authorization", reason_code=exc.code, event_class="control_failure")
            raise

    def _control_event(self, *, operation: str, outcome: str, target: str, reason_code: str | None = None, event_class: str) -> None:
        target_app = target if target in self._service._cells else self._service._credentials.application_id_for(target)
        self._service._audit.append(event_class=event_class, request_id=str(uuid.uuid4()), application_id=target_app, actor_type="control_authority", actor_id=None, role="control", operation=operation, target_kind="application_or_credential", outcome=outcome, reason_code=reason_code)
