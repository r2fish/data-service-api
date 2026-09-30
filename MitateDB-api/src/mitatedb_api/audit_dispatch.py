"""Durable-audit dispatch: the coalescing denial router and the pre-commit
hook builder, plus the synchronous writers for an ordinary data-operation
event and for a replayed one (design D-2/D-3).

Independent implementation of r2db-api's own dispatch logic
(`r2db_api.service`'s `_PreCommitHook`/`_DenialCoalescer`, R-2's closing
paragraph: no code sharing between peers) -- same safety properties,
realized as one small, explicit `AuditRouter` object instead of being
folded into a single per-process facade class, because this peer has no
r2db-style single `DataService` facade: authentication/authorization live
in `auth.CredentialStore`/`credential_store_postgres.
PostgresCredentialStore`, and data operations live in `cell.
ApplicationCell` -- two independently-testable objects, not one. `main.
build_app` constructs exactly ONE `AuditRouter` per process (mirroring
r2db-api's `DataService` being one-per-process; the coalescer below is
explicitly documented as process-local, D-3's own "review N-4"
instruction) and hands the SAME instance to every `ApplicationCell`/
credential store it builds, so `(application_id, actor_id, operation,
reason_code)` coalescing keys are shared across every application this
process serves, not duplicated per cell.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Optional

from .application_audit import (DEFAULT_DENIAL_COALESCE_WINDOW_S,
                                ApplicationAuditSink, coalesced_count)
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
# anything else this peer can raise -- is out of scope for durable
# recording (D-3's own "除外列挙ではなく包含列挙" ruling: an
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

# Fixed, no-interpolation log messages -- a fixed string also means these
# two call sites can never accidentally leak a client-supplied value into
# process logs.
_COALESCE_AGGREGATE_WRITE_FAILED_LOG_MESSAGE = "application_audit coalesced-denial summary row could not be written; retrying"
_COALESCE_AGGREGATE_WRITE_RECOVERED_LOG_MESSAGE = "application_audit coalesced-denial summary row recorded; retry cleared"


class _PreCommitHook:
    """The concrete `ApplicationAuditHook` `AuditRouter.make_pre_commit_
    hook` returns (design D-2/D-10) -- every field the durable row needs is
    already bound here at construction time; the caller (a backend method,
    or `cell.ApplicationCell.transact`) supplies none of it, only the moment
    (every real batch, every single-row write, every delete and every schema
    operation)."""

    __slots__ = ("_sink", "_fields", "fired", "_error_attempted")

    def __init__(self, sink: Any, fields: dict[str, Any]) -> None:
        self._sink = sink
        self._fields = fields
        # `True` once `pre_commit()` has durably recorded the `allow` row, so a caller that only sees a failure surface (a backend that raises past its own error-row handling) can still tell whether an `error` row is owed.
        self.fired = False
        self._error_attempted = False

    def pre_commit(self) -> None:
        try:
            self._sink.append(outcome="allow", count=None, **self._fields)
        except Exception as exc:
            raise AuditSinkUnavailable(
                "the durable audit sink could not record this operation; it was not submitted"
            ) from exc
        self.fired = True

    def commit_failed(self) -> None:
        # D-2's error-row rule: best-effort from the response's point of
        # view (the caller fails `AuditSinkUnavailable` regardless of
        # whether this succeeds -- the data commit already failed either
        # way) -- any exception here is swallowed, never re-raised. At
        # most one attempt per operation, so a backend that already
        # recorded the row and a caller that records it again on the way
        # out never write two.
        if self._error_attempted:
            return
        self._error_attempted = True
        try:
            self._sink.append(outcome="error", reason_code="commit_failed", count=None, **self._fields)
        except Exception:
            pass


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
        state transition -- not once per attempt, which would let a
        persistently failing sink flood the log."""
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


class AuditRouter:
    """The one shared, per-process object `main.build_app`/
    `control_composition.build_control_service`-adjacent composition
    constructs and hands to every `auth.CredentialStore`/
    `credential_store_postgres.PostgresCredentialStore`/`cell.
    ApplicationCell` it builds. Bundles the durable sink and the denial
    coalescer behind a few small entry points -- the MitateDB-shaped
    equivalent of what r2db-api's own `DataService` does internally in
    `_event`/`_denial_event`/`_make_audit_hook`. Every event other than a
    denial's later repeats is written to the sink synchronously, before
    the response it describes is returned.
    """

    def __init__(
        self, durable_sink: Any = None, *,
        denial_coalesce_window_s: float = DEFAULT_DENIAL_COALESCE_WINDOW_S,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self._durable_sink = durable_sink if durable_sink is not None else ApplicationAuditSink()
        clock = clock or time.monotonic
        self._coalescer = _DenialCoalescer(self._durable_sink, window_s=denial_coalesce_window_s, clock=clock)
        # Phase 4 WP-3(b) (design D-5, r2db-api WP-2(b) review item H: avoid
        # the "coalescing_window_ms declared as a bare literal, never bound
        # to the REAL configured window" gap from the start): the actual
        # window this instance enforces, readable by a composition root that
        # wants to declare the value it is TRULY running with (this WP's own
        # `audit_query.py` derives its default from `DEFAULT_DENIAL_COALESCE_
        # WINDOW_S`, but a caller that overrides `denial_coalesce_window_s`
        # here must be able to derive a matching declaration too, not fall
        # back to the module default).
        self._denial_coalesce_window_s = denial_coalesce_window_s

    @property
    def durable_sink(self) -> Any:
        return self._durable_sink

    @property
    def denial_coalesce_window_s(self) -> float:
        return self._denial_coalesce_window_s

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
        inclusion set) returns without any durable record at all
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

    def write_event(
        self, *, event_class: str, request_id: Optional[str], application_id: Optional[str],
        actor_type: Optional[str], actor_id: Optional[str], role: Optional[str], operation: str,
        target_kind: Optional[str], target_id: Optional[str] = None,
    ) -> None:
        """Writes one ordinary data-operation event (`outcome="allow"`)
        to the durable sink, synchronously, before the caller returns its
        response -- a `read_page` (`query`) whose event is not durable is
        not answered. Raises `errors.AuditSinkUnavailable` (never
        swallowed) when the sink cannot record it, so the operation fails
        closed instead of answering with no evidence. A write that has a
        data commit of its own to order against goes through the
        pre-commit hook (`make_pre_commit_hook`) instead."""
        try:
            self._durable_sink.append(
                event_class=event_class, request_id=request_id, application_id=application_id,
                actor_type=actor_type, actor_id=actor_id, role=role, operation=operation,
                target_kind=target_kind, outcome="allow", reason_code=None, target_id=target_id, count=None,
            )
        except Exception as exc:
            raise AuditSinkUnavailable(
                "the durable audit sink could not record this operation; it was not answered"
            ) from exc

    def write_replayed_fail_closed_event(
        self, *, event_class: str, request_id: Optional[str], application_id: Optional[str],
        actor_type: Optional[str], actor_id: Optional[str], role: Optional[str], operation: str,
        target_kind: Optional[str], target_id: Optional[str] = None,
    ) -> None:
        """A single durable row -- `outcome="replayed"` -- for an
        idempotency REPLAY (a schema operation, `event_class=
        "schema_change"`, or a mutate batch, `event_class=
        "data_operation"`), written synchronously, immediately, exactly
        like `_PreCommitHook.pre_commit()` writes a fresh operation's own
        `outcome="allow"` row: a resent request that answers from a
        retained record must never return `committed: true` while
        leaving zero durable evidence this Application was touched at
        time T (SI-14). `request_id` is THIS replay request's own id,
        never the original's. Raises `errors.AuditSinkUnavailable` (never
        swallowed, matching `pre_commit()`'s own identical raise) when
        the durable sink itself cannot record it -- the replay is NOT
        answered in that case, rather than silently succeeding with zero
        evidence. Nothing below the idempotency lookup executed for a
        replay, so there is no LATER commit point this row could be
        deferred past -- it is written here, once, before the replay
        response is returned."""
        try:
            self._durable_sink.append(
                event_class=event_class, request_id=request_id, application_id=application_id,
                actor_type=actor_type, actor_id=actor_id, role=role, operation=operation,
                target_kind=target_kind, outcome="replayed", reason_code=None, target_id=target_id, count=None,
            )
        except Exception as exc:
            raise AuditSinkUnavailable(
                "the durable audit sink could not record this replay; it was not answered"
            ) from exc

    def flush(self, *, force_expire_denial_windows: bool = False) -> None:
        """Sweeps denial-coalescing windows (writing their repeat-count
        summary row). Ordinary events are written before their response is
        returned, so no buffer is left to drain here. Called on demand by
        this repository's own tests and by a composition root's periodic
        timer alike.

        `force_expire_denial_windows=True`: flushes EVERY currently-open
        denial-coalescing window, expired or not -- used exactly once, by
        a composition root's graceful-shutdown path."""
        if force_expire_denial_windows:
            self._coalescer.flush_all()
        else:
            self._coalescer.flush_expired()


__all__ = [
    "DURABLE_DENIAL_CODES",
    "AuditRouter",
]
