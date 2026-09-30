"""Application facade and separately held Control/Provisioning authority."""
from __future__ import annotations

from contextlib import contextmanager
import logging
import threading
import time
from typing import Any, Callable, Iterator
import uuid

from .audit import ApplicationAuditSink, AuditSink
from .audit_counts import _coalesced_count
from .auth import AuthContext, CredentialStore
from .backend import StorageBackend
from .capabilities_document import build_capabilities_document
from . import concurrency_slots
from .errors import FoundationError, fail, observed_type_of, violation
from .limits import ResourceLimits, narrow_limits_by_budget
from .paging import MAX_PAGE_SIZE
from .request_shape import _check_mutation_request_shape, _check_query_request_shape
from .service_results import MutationResult, QueryPage
from .structured import ApplicationCell, fold_operation_idempotency_keys, parse_predicate
from .topology import AuthorityTopology

_logger = logging.getLogger(__name__)

#: the fixed start of the WARNING line written where a slot backend
#: failure becomes a 503 (`DataService._slot` and `DataService.
#: acquire_concurrency_slot`).
_SLOT_FAILURE_LOG_PREFIX = "r2db_api: concurrency slot backend failed, answering SERVICE_UNAVAILABLE"

#: this process' one writer of that line, shared by both of those
#: mapping points -- at most one line per interval
#: (`concurrency_slots.BackendFailureLog`).
_SLOT_FAILURE_LOG = concurrency_slots.BackendFailureLog(_logger, _SLOT_FAILURE_LOG_PREFIX)

# Phase 4 (design PHASE4_DURABLE_AUDIT_SINK_V1.md D-3; WP-2(a) review J-2,
# supervisor ruling 2026-09-02): an INCLUSION set -- only a denial whose
# reason_code is one of these 6 (D-3's own range table, SI-14's minimal
# event class: authentication/authorization denial) is fail-closed/
# coalesced-durable. Every other reason_code -- D-3's originally-named 4 non-durable codes (`VALIDATION_FAILED`/`LIMIT_EXCEEDED`/`CAPABILITY_UNSUPPORTED`/`NOT_FOUND`) AND everything else this facade can raise (`CONFLICT`, `PRECONDITION_FAILED`, `SERVICE_UNAVAILABLE`, `AUTH_STATE_UNAVAILABLE`, ...) -- is out of scope for durable recording (N-2: recording them would just let the flow problem exists to bound come back). An exclusion-list reading
# (only the named 4 are non-durable, everything else durable) was this
# module's first implementation; the review's B-1 finding showed it lets a
# `SERVICE_UNAVAILABLE` produced by the audit pipeline's OWN failure re-enter
# as a "new" denial, writing a THIRD durable row for one operation (D-10's
# own prohibited case (ii)) -- switching to inclusion closes that path
# structurally (`SERVICE_UNAVAILABLE` was never in D-3's fail-closed list to
# begin with). `test_durable_denial_codes_match_the_design_d3_table` (`tests/test_application_audit.py`) fixes this set against D-3's table by name.
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

# The default interval of the composition root's periodic sweep of the
# denial-coalescing windows (`DataService.flush_audit_buffer`); a latency
# knob only -- it decides how soon an expired window's repeat-count
# summary row is written, never whether a denial is recorded.
_DEFAULT_AUDIT_FLUSH_INTERVAL_S = 2.0

# `_coalesced_count`'s own comment (Phase 4 WP-2(b) review B-1) moved with
# it to `audit_counts.py` when that helper was extracted.
# history: CH-0179

# fixed, no-interpolation log messages for the denial-coalescer's own aggregate (repeat-count summary) row write path -- follows a state-transition-only discipline (logged on failing<->healthy transitions, never once per attempt), applied to `_DenialCoalescer._note_aggregate_write_result`.
# history: CH-0173
_COALESCE_AGGREGATE_WRITE_FAILED_LOG_MESSAGE = "application_audit coalesced-denial summary row could not be written; retrying"
_COALESCE_AGGREGATE_WRITE_RECOVERED_LOG_MESSAGE = "application_audit coalesced-denial summary row recorded; retry cleared"

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


class _PreCommitHook:
    """the concrete `ApplicationAuditHook` `DataService` builds per fail-closed-class request and hands to `StorageBackend.transact`/`apply_schema` as `audit_hook`. Every field
    the durable row needs (`event_class`/`request_id`/`application_id`/
    `actor_type`/`actor_id`/`role`/`operation`/`target_kind`/`target_id`)
    is already bound here at construction time -- the backend itself
    supplies none of it, only the moment (every real batch for `transact`,
    unconditional for `apply_schema`).

    History: CH-0166
    """

    __slots__ = ("_sink", "_fields", "fired")

    def __init__(self, sink: Any, fields: dict[str, Any]) -> None:
        self._sink = sink
        self._fields = fields
        # `True` once `pre_commit()` has durably recorded the `allow` row, so the caller can tell a batch whose row is already written from one whose backend never called the hook.
        self.fired = False

    def pre_commit(self) -> None:
        try:
            self._sink.append(outcome="allow", count=None, **self._fields)
            self.fired = True
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
        # tracks whether the MOST RECENT aggregate-row write attempt (from any key) failed -- a single, process-wide flag, logging only on failing<->healthy transitions, never once per attempt.
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
        """fixed-message `logging.error`, only on a failing<-> healthy state TRANSITION (N-2's own established discipline) -- not once per attempt, which would let a persistently failing sink flood the log.

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

    def __init__(self, credentials: CredentialStore, limits: ResourceLimits | None = None, topology: AuthorityTopology | None = None, audit: AuditSink | None = None, initial_cells: dict[str, StorageBackend] | None = None, clock: Callable[[], float] | None = None, cell_factory: CellFactory | None = None, control_plane_status: str = "unavailable", durable_audit: Any | None = None, denial_coalesce_window_s: float = _DENIAL_COALESCE_WINDOW_S, surfaces: dict[str, Any] | None = None, process_ceiling: int = 1, operation_catalog_url: str | None = None, rate: Any | None = None, concurrency_slots: Any | None = None, concurrency_configured: bool = False) -> None:
        # R-9 (CCR-14, design docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md §1: "capability 申告は環境変数由来で composition root 注入"): whether this application-plane process' own `capabilities()` declares `control_plane: enabled` is a *deployer* fact this class cannot know on its own (a separated deployment, the default, means the application-plane process has no idea whether a control-plane process is running anywhere at all) -- it is constructor-injected, defaulting to the safe, honest `unavailable` so nothing short of an explicit composition-root decision (`main.py`, reading `R2DB_CONTROL_PLANE_STATUS`) ever declares `enabled`. Validated here too (not only at `main.py`'s env-parsing boundary) so any other caller constructing a `DataService` directly (this repository's own tests, the in-process conformance adapter) gets the same fail-loud guard against a typo'd status string, rather than silently publishing an invalid capability value.
        # history: CH-0148
        if control_plane_status not in {"enabled", "unavailable"}:
            raise ValueError("control_plane_status must be 'enabled' or 'unavailable'")
        self._control_plane_status = control_plane_status
        # `surfaces` is constructor-injected, same "deployer-declared, not derived" discipline as `control_plane_status` immediately above -- `main.py` (the real composition root) is the one caller that validates the two `R2DB_*_BASE_URL` environment variables' SHAPE at startup and assembles this dict from them; this class only ever echoes whatever it was given, verbatim, in `capabilities()` below. `None` (the default -- every caller, including this repository's own unit tests that construct `DataService` directly without opting in) omits the `surfaces` key from the response entirely, never a `"surfaces": None` value (contract `CapabilityDocument.surfaces` is an optional key, not a nullable one).
        # history: CH-0147
        self._surfaces = surfaces
        # Same constructor-injected, echo-only discipline as `surfaces`
        # immediately above (design docs/design/PHASE11_MIN_COMMON_PROFILE_V1.md
        # D-5) -- `main.py` reads
        # `R2DB_OPERATION_CATALOG_URL`; this class only ever echoes
        # whatever it was given, verbatim, in `capabilities()` below.
        # `None` (the default) omits the `operation_catalog_url` key
        # entirely.
        self._operation_catalog_url = operation_catalog_url
        # Phase 10 WP-6a (design D-5(ii), contract 1.8.0): the deployer's own declared ceiling on how many processes may serve THIS plane's `surfaces` base URL at the same time -- constructor-injected, same "deployer-declared, not derived" discipline as `control_plane_status`/`surfaces` above. `main.py` (the real
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
        self._denial_coalescer = _DenialCoalescer(self._durable_audit, window_s=denial_coalesce_window_s, clock=clock or time.monotonic)
        self._cell_factory: CellFactory = cell_factory or _default_cell_factory
        self._cells: dict[str, StorageBackend] = dict(initial_cells or {})
        self._disabled_apps: set[str] = set()
        self._active = 0
        self._active_lock = threading.Lock()
        self._rate_lock = threading.Lock()
        self._rate_windows: dict[str, list[float]] = {}
        self._clock = clock or time.monotonic
        # design D-3: the 2-strategy region (ii)
        # wiring -- `rate`/`concurrency_slots` default to `None` (this
        # repository's own unit tests and the in-process conformance
        # adapter never pass either): `_acquire_rate`/`acquire_
        # concurrency_slot`/`_slot` below run their in-memory branch
        # whenever the corresponding object is `None`. `rate` (when given) is a `PostgresCredentialStore`-
        # shaped object exposing `record_rate_and_check(credential_id,
        # limit) -> bool`; `concurrency_slots` is a `concurrency_slots.
        # HostSharedConcurrencySlots`-shaped object exposing `acquire(limit)`
        # as a context manager. `concurrency_configured` is a SEPARATE
        # boolean (never derived from `concurrency_slots is not None`
        # alone): whether `capabilities().limit_enforcement.
        # concurrency` may honestly read `enforced` depends on this
        # supervisor's own workers vs. the declared ceiling too, a
        # comparison only the composition root (`main.py`) can make --
        # this class enforces the wired mechanism whenever it is given
        # one, REGARDLESS of this flag (an honest `deployment_required`
        # declaration does not mean the local host-shared bound stops
        # working, only that ANOTHER host might not share it).
        self._rate = rate
        self._concurrency_slots = concurrency_slots
        if concurrency_configured and concurrency_slots is None:
            raise ValueError(
                "concurrency_configured=True requires a concurrency_slots object -- "
                "declaring the host-shared bound configured without wiring the mechanism "
                "that shares it would let capabilities().limit_enforcement.concurrency read "
                "\"enforced\" for a process-local counter no other worker shares"
            )
        self._concurrency_configured = concurrency_configured
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
            return build_capabilities_document(
                role=canonical.role,
                application_id=canonical.application_id,
                limits=self.limits,
                control_plane_status=self._control_plane_status,
                process_ceiling=self._process_ceiling,
                surfaces=self._surfaces,
                operation_catalog_url=self._operation_catalog_url,
                rate_configured=self._rate is not None,
                concurrency_configured=self._concurrency_configured,
            )

    def operation_catalog(self, context: AuthContext, *, concurrency_precharged: bool = False) -> None:
        """Design D-5, contract 1.9.0 `endpoints.operation_catalog`:
        authorization/rate gate only -- the SAME
        `_slot()` gate `capabilities()` immediately above goes through
        (design §8.2, SI-08's existing request-rate bound applies
        unchanged), so `requests_per_minute`/`concurrency` are charged
        for this endpoint exactly like every other data-plane operation.
        The served bytes are the packaged `contract/OPERATION_CATALOG.
        json`, read verbatim by `http.py`'s own handler and by the
        in-process conformance adapter's port v1.17 `operation_catalog_
        document()` -- there is nothing `DataService`-scoped to compute
        or return here.
        """
        with self._slot(context, concurrency_precharged=concurrency_precharged):
            return None

    def query(self, context: AuthContext, entity: str, *, select: list[str], where: list[dict[str, Any]] | None = None, page_size: int | None = None, order_by: list[dict[str, Any]] | None = None, cursor: str | None = None, request_id: str | None = None) -> list[dict[str, Any]]:
        """Plain-item-list form, unchanged in shape since before CCR-13 (every existing caller -- `tests/test_foundation.py`, the in-process conformance adapter -- keeps working against exactly this return type). `order_by`/`cursor` (CCR-13) are accepted here too (so this method alone is enough to exercise/test them against the facade), but the pagination continuation itself only reaches a caller through `query_page` below, which `http.post_query` uses.

        Keyset paging (design D-1 (2a), D-3 (9)): `page_size` of `None` (the
        default, and what a request that omits `page.size` resolves to)
        is answered as though it carried the least of the contract
        maximum, this deployment's own declared `limits.result_items`,
        and the request's own `budget.result_items` where it carries one
        -- resolved once, in `_query_outcome` below, after `budget` has
        already narrowed the effective limits.

        History: CH-0135
        """
        return list(self._query_outcome(context, entity, select=select, where=where, page_size=page_size, order_by=order_by, cursor=cursor, request_id=request_id).items)

    def query_page(self, context: AuthContext, entity: str, *, select: list[str], where: list[dict[str, Any]] | None = None, page_size: int | None = None, order_by: list[dict[str, Any]] | None = None, cursor: str | None = None, request_id: str | None = None, budget: dict[str, int] | None = None, concurrency_precharged: bool = False) -> "QueryPage":
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
        # Contract 1.7.0: resolved HERE, once, so the SAME value both reaches `QueryPage.request_id` below and is the one `_query_outcome` uses for its own audit event -- the generation point for the request/response pair a caller sees, never re-derived a second time for the response body (Q-1: "HTTP 層は再生成しない" generalizes to "no layer re-derives it").
        # history: CH-0133
        rid = request_id or str(uuid.uuid4())
        outcome = self._query_outcome(context, entity, select=select, where=where, page_size=page_size, order_by=order_by, cursor=cursor, request_id=rid, budget=budget, concurrency_precharged=concurrency_precharged)
        return QueryPage(items=list(outcome.items), next_page=outcome.next_cursor, revisions=list(outcome.revisions or []), request_id=rid)

    def _query_outcome(self, context: AuthContext, entity: str, *, select: list[str], where: list[dict[str, Any]] | None, page_size: int | None, order_by: list[dict[str, Any]] | None, cursor: str | None, request_id: str | None, budget: dict[str, int] | None = None, concurrency_precharged: bool = False):
        rid = request_id or str(uuid.uuid4())
        try:
            with self._slot(context, concurrency_precharged=concurrency_precharged) as canonical:
                _check_query_request_shape(select, where, page_size, order_by, cursor)
                request = {"entity": entity, "select": select, "where": where or [], "page_size": page_size, "order_by": order_by or [], "cursor": cursor}
                self.limits.check_request(request)
                self.limits.check_depth(request)
                # Contract 1.7.0 (addendum 2 S-l, ruling): `request_budget` is `enabled` -- `budget` validity (applicable class / integer >= 1 / not above the deployed bound) is checked here, at request-shape time, before target existence -- the SAME single point every endpoint uses (`limits.narrow_limits_by_budget`) to turn `budget` into the "effective limits" every existing check point below reads, without any of them being rewritten.
                # history: CH-0132
                effective_limits = narrow_limits_by_budget(self.limits, budget, "query")
                # Keyset paging (design D-1 (2a), D-3 (9)): a request that omits
                # `page.size` is resolved to the least of the contract
                # maximum, the deployed `limits.result_items`, and the
                # request's own `budget.result_items` -- computed AFTER
                # `budget` has already narrowed `effective_limits` above,
                # so a smaller `budget.result_items` shrinks the default
                # page too, and `LIMIT_EXCEEDED` never fires on the
                # resolved default (the minimum of the three is always
                # <= each of them).
                resolved_page_size = page_size if page_size is not None else min(MAX_PAGE_SIZE, effective_limits.result_items)
                predicates = [parse_predicate(item) for item in (where or [])]
                deadline = self._clock() + effective_limits.execution_ms / 1000
                outcome = self._cells[canonical.application_id].query(
                    entity, select=select, where=predicates, page_size=resolved_page_size, order_by=order_by, cursor=cursor, limits=effective_limits, deadline=deadline, clock=self._clock
                )
                # `query` writes its event synchronously, before the result is returned.
                # history: CH-0131
                self._event(canonical, operation="query", outcome="allow", target_kind="entity", event_class="data_operation", request_id=rid)
                return outcome
        except FoundationError as exc:
            self._event(context, operation="query", outcome="deny", target_kind="entity", reason_code=exc.code, event_class="authorization_denial", request_id=rid, details=exc.details)
            raise

    def mutate(self, context: AuthContext, entity: str, operations: list[dict[str, Any]], *, transaction: str = "atomic", request_id: str | None = None) -> int:
        """Plain affected-count form, unchanged in shape since before CCR-13 (every existing caller -- `tests/test_foundation.py`, the in-process conformance adapter -- keeps working against exactly this return type). `mutate_result` below is the richer shape
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
            # D-4 (3)/A-9: a dry-run mutation result never carries `assigned_addresses` -- the addresses a real execution would assign are not settled (an insert may still have tentatively consumed real id-sequence values, F-15, but this response never reports them). `None`, not `[]` -- `http.post_mutate` omits the key itself on `None`, matching the contract's "does not carry" wording.
            # history: CH-0127
            assigned_addresses=None if dry_run else list(outcome.assigned_addresses or []),
            committed=outcome.committed,
            plan=outcome.plan if dry_run else None,
        )

    def _mutate_outcome(self, context: AuthContext, entity: str, operations: list[dict[str, Any]], *, transaction: str | None, request_id: str | None, dry_run: bool = False, plan: str | None = None, budget: dict[str, int] | None = None, idempotency_key: str | None = None, concurrency_precharged: bool = False):
        rid = request_id or str(uuid.uuid4())
        try:
            with self._slot(context, concurrency_precharged=concurrency_precharged) as canonical:
                _check_mutation_request_shape(transaction, operations)
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
                # Contract 1.7.0 (D-4 (7)/S-a, WP-2b): the contract-level request object a `plan` commits to -- `operations`/`transaction`/`budget`, plus this request's own target `entity` (addendum 2: "computed from the request itself" includes the request's URL path segment, not only its body -- `MutationRequest` itself has no `entity` property, but the plan digest is not scoped to `MutationRequest` alone). Placed at the
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
                # Phase 4, extended by D-4 (4)/U-2 = (A): the backend calls the hook as the last statement of every real (non-`dry_run`) batch, so the `allow` row is durable before the data commit -- the same path `schema`'s own hook below takes. A
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
                # (durable OR the legacy in-memory sink `_event`
                # itself unconditionally appends to) is written for it.
                # `hook.fired` reports whether the backend's pre-commit hook already durably recorded this batch -- `already_durable` tells `_event` to skip its own synchronous write in that case (at most one durable row per operation); a backend that never called the hook leaves the row to `_event`, which writes it before the response. Contract 1.7.0 (D-5 (1)(v), ruling I-11/J-4, WP-2c/WP-2cd): `outcome.replayed` -- a resend answered from an idempotency record still earns its OWN audit line (SI-14 audit N-5: a destructive resend must never return `committed: true` while leaving zero evidence of its own that this Application was touched at time T) -- `outcome="replayed"`, never `"allow"`, keeps a resend distinguishable from a genuine new execution in the audit trail itself; it carries THIS resend's own `request_id` (never the original), and, like every event this method emits, never the `idempotency_key` value. Always
                # `already_durable=False`: a replay never invokes the
                # pre-commit hook (nothing below the idempotency lookup
                # executed), so no durable row has already been written for
                # THIS event the way a fresh commit's
                # hook already wrote one for its own.
                # history: CH-0121
                if not dry_run:
                    if outcome.replayed:
                        self._event(canonical, operation="mutate", outcome="replayed", target_kind="entity", event_class="data_operation", request_id=rid, already_durable=False)
                    else:
                        self._event(canonical, operation="mutate", outcome="allow", target_kind="entity", event_class="data_operation", request_id=rid, already_durable=hook is not None and hook.fired)
                return outcome
        except FoundationError as exc:
            self._event(context, operation="mutate", outcome="deny", target_kind="entity", reason_code=exc.code, event_class="operation_denial", request_id=rid, details=exc.details)
            raise

    def schema(self, context: AuthContext, operation: dict[str, Any] | None, *, request_id: str | None = None, concurrency_precharged: bool = False) -> "SchemaOutcome":
        """Always returns `SchemaOutcome` (`.committed`/`.revision`/`.descriptor`/`.plan`, contract 1.7.0, D-4) -- a pure passthrough of `ApplicationCell.apply_schema`/`PostgresCell.apply_schema`'s own return, which review round F-8 unified to one shape regardless of whether `operation` carries `dry_run`/`plan`. Every pre-1.7.0 direct caller of this method (`tests/test_foundation.py`; `tests/test_constraints_declaration.py` reads `.revision` only off `cell.apply_schema`) reads `.revision` off the result; the in-process conformance adapter's own `hasattr(result, "revision")` branch already handles a non-`int` result unchanged (it never assumed `int`).

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
                # Contract 1.7.0 (D-4 (7)/S-a, WP-2b): the contract-level request object a `plan` commits to -- `operation` itself already IS that object (`SchemaOperationRequest`'s own flat shape), minus `plan`/`dry_run` (S-a's exclusion pair, applied again defensively inside `normalize_request_for_plan`). `idempotency_key`, when present, stays IN this object (only `plan`/`dry_run` are excluded here) -- `idempotency_digest` below applies its own, separate 3-key exclusion.
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
                # a genuine schema commit (whose pre-commit hook already
                # wrote the durable row synchronously, `hook.fired`), a
                # replay never invoked that hook at all, so
                # `already_durable=False` here.
                if not dry_run:
                    if outcome.replayed:
                        self._event(canonical, operation="schema", outcome="replayed", target_kind="entity", event_class="privilege_sensitive", request_id=rid, already_durable=False)
                    else:
                        self._event(canonical, operation="schema", outcome="allow", target_kind="entity", event_class="privilege_sensitive", request_id=rid, already_durable=hook is not None and hook.fired)
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
                entities = self._cells[canonical.application_id].catalog(self.limits)
                # `catalog` writes its event synchronously, before the result is returned.
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

        this denial's `reason_code` is always `CAPABILITY_UNSUPPORTED` -- not in D-3's durable-code inclusion list, so `_event`'s deny dispatch never routes it through the durable/coalesced path (unchanged from pre-Phase-4 behaviour: this method never wrote a durable row before this WP either).

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
        # design D-3 (2): whenever a host-shared
        # slot directory is wired (`self._concurrency_slots is not None`),
        # this non-precharged caller (a direct `DataService` caller --
        # this repository's own tests, the in-process conformance
        # adapter -- never an HTTP request, which always precharges via
        # `acquire_concurrency_slot()` below before reaching here) is
        # admitted through the SAME mechanism, never the in-memory
        # counter. The pinned in-memory check-then-increment block below
        # is unchanged, lexically intact, for the unwired path.
        if self._concurrency_slots is not None:
            try:
                with self._concurrency_slots.acquire(self.limits.concurrency):
                    yield canonical
                return
            except concurrency_slots.LimitExceeded:
                fail("LIMIT_EXCEEDED", "Concurrency limit exceeded.", status=429, details={"resource": "concurrency", "limit_class": "concurrency", "limit": self.limits.concurrency})
            except concurrency_slots.SlotBackendError as exc:
                _SLOT_FAILURE_LOG.note(exc)
                fail("SERVICE_UNAVAILABLE", "The database could not complete the request.", status=503)
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
        # same host-shared-slot branch `_slot` above carries (its
        # own docstring) -- deliberately its own copy too, for the same
        # reason the in-memory copy right below is (this method's own
        # docstring).
        if self._concurrency_slots is not None:
            try:
                with self._concurrency_slots.acquire(self.limits.concurrency):
                    yield
                return
            except concurrency_slots.LimitExceeded:
                fail("LIMIT_EXCEEDED", "Concurrency limit exceeded.", status=429, details={"resource": "concurrency", "limit_class": "concurrency", "limit": self.limits.concurrency})
            except concurrency_slots.SlotBackendError as exc:
                _SLOT_FAILURE_LOG.note(exc)
                fail("SERVICE_UNAVAILABLE", "The database could not complete the request.", status=503)
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
        # design D-3 (1): whenever a PostgreSQL-backed
        # rate row is wired (`self._rate is not None`), every worker this
        # deployment runs shares ONE credential-keyed count instead of
        # each keeping its own in-memory window below. Called AFTER
        # `_check`'s own authentication borrow has already returned its
        # connection (`_slot`'s own `canonical = self._check(context);
        # self._acquire_rate(canonical)`, sequential, never nested).
        if self._rate is not None:
            admitted = self._rate.record_rate_and_check(context.credential_id, self.limits.requests_per_minute)
            if not admitted:
                fail("LIMIT_EXCEEDED", "Request rate limit exceeded.", status=429, details={"resource": "requests_per_minute", "limit_class": "requests_per_minute", "limit": self.limits.requests_per_minute})
            return
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
        - `outcome == "deny"`: `details["origin"] == "audit_sink"` means this denial's `SERVICE_UNAVAILABLE` was produced by the audit pipeline itself already failing to record this very operation (a pre-commit sink failure, a commit-failure error-row write, a coalesced-denial first-insert failure) -- routing it through `_route_denial` again would be a second (or third) durable write for what is still logically one operation, so this returns without doing anything further. Otherwise, any reason code outside D-3's durable-code inclusion list (`_DURABLE_DENIAL_CODES` -- not merely the 4 originally named) returns without any durable record at all; every other reason code is fail-closed-class and goes through the coalescing denial router (which may itself raise `SERVICE_UNAVAILABLE`).
        - `outcome == "allow"` (any class but `authentication`) or `"replayed"` (any class): written synchronously to the durable sink before the caller's response is returned -- `query`/`catalog`, a `mutate` whose backend did not already record it (`already_durable=False`), and every replay. A sink failure raises `SERVICE_UNAVAILABLE` (fail-closed), so a response is only ever returned for an operation whose event is durable.

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
        # `authenticate`'s own success (`event_class="authentication"`) is not a
        # data operation, and no rule names it fail-closed either, so it stays
        # in the legacy in-memory sink only (already appended above), with no
        # durable record at all. Every other `allow` reaches the durable sink
        # here unless its backend's pre-commit hook already wrote it
        # (`already_durable`); a `replayed` line is durable for every class.
        if outcome == "allow" and event_class == "authentication":
            return
        try:
            self._durable_audit.append(
                event_class=event_class, request_id=rid, application_id=application_id, actor_type=actor_type,
                actor_id=actor_id, role=role, operation=operation, target_kind=target_kind, outcome=outcome,
                reason_code=reason_code, target_id=target_id, count=None,
            )
        except Exception:
            fail(
                "SERVICE_UNAVAILABLE",
                "The durable audit sink could not record this operation; the response was withheld.",
                status=503,
                details={"origin": _AUDIT_SINK_ORIGIN},
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

    def _make_audit_hook(self, canonical: AuthContext, *, event_class: str, operation: str, target_kind: str, request_id: str) -> _PreCommitHook:
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
        """Phase 4 (design D-4/§7.3/§7.4): sweeps denial-coalescing windows (writing their repeat-count summary row). Ordinary events are written before their response is returned, so no buffer is left to drain here. Called on demand by this repository's own tests and by a
        composition root's periodic timer alike -- there is nothing
        time-sensitive about calling this more or less often beyond how
        promptly a window's repeat count becomes durable.

        flushes EVERY currently-open denial-coalescing window, expired or not, instead of only expired ones -- used exactly once, by a composition root's graceful-shutdown path. Without this, a window still short of its own `window_s` at the moment the process stops loses its accumulated repeat count entirely (only sanctions losing counts to an actual crash, not to an orderly stop); the default (periodic timer, explicit test calls) stays `False` -- an in-progress window still has a legitimate future to expire into naturally and must not be cut short just because something else happened to call this method.

        History: CH-0106
        """
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

        Rework (coordinator item 3): returns the composed bearer `self._service._credentials.add(...)` itself now returns (design D-1(c) "合成は store/service 層のみ" principle) -- this out-of-band lifecycle-authority entry point is an issuance point (the conformance in-process plug's own privileged-setup `issue_credential` calls this directly, `ops.py` does not use this method at all -- see that module's own `cmd_issue_credential`, which calls the store's `add` directly and gets the same composed return value there). Every pre-WP-2 caller that ignored the
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
