"""Durable-audit dispatch: the refusal-window counter call and the pre-commit
hook builder, plus the synchronous writers for an ordinary data-operation
event and for a replayed one (design D-2/D-3).

Independent implementation of r2db-api's own dispatch logic
(`r2db_api.service`'s `_PreCommitHook`/`_denial_event`, R-2's closing
paragraph: no code sharing between peers) -- same safety properties,
realized as one small, explicit `AuditRouter` object instead of being
folded into a single per-process facade class, because this peer has no
r2db-style single `DataService` facade: authentication/authorization live
in `auth.CredentialStore`/`credential_store_postgres.
PostgresCredentialStore`, and data operations live in `cell.
ApplicationCell` -- two independently-testable objects, not one. `main.
build_app` constructs exactly ONE `AuditRouter` per process (mirroring
r2db-api's `DataService` being one-per-process) and hands the SAME
instance to every `ApplicationCell`/credential store it builds.

A refusal's count is not kept here: `route_denial` hands each durable
refusal to the sink's `record_denial`, which adds it to the refusal-window
counter in the platform database before the response is returned, so the
`(application_id, actor_id, operation, reason_code)` windows are shared by
every process of the deployment and nothing about them lives in this one.
"""
from __future__ import annotations

from typing import Any, Optional

from .application_audit import DEFAULT_DENIAL_COALESCE_WINDOW_S, ApplicationAuditSink
from .audit_hook import ApplicationAuditHook
from .errors import AuditSinkUnavailable

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


class AuditRouter:
    """The one shared, per-process object `main.build_app`/
    `control_composition.build_control_service`-adjacent composition
    constructs and hands to every `auth.CredentialStore`/
    `credential_store_postgres.PostgresCredentialStore`/`cell.
    ApplicationCell` it builds. Bundles the durable sink and the refusal-
    window length behind a few small entry points -- the MitateDB-shaped
    equivalent of what r2db-api's own `DataService` does internally in
    `_event`/`_denial_event`/`_make_audit_hook`. Every event, and every
    refusal's count, is written to the sink synchronously, before the
    response it describes is returned.
    """

    def __init__(
        self, durable_sink: Any = None, *,
        denial_coalesce_window_s: float = DEFAULT_DENIAL_COALESCE_WINDOW_S,
    ) -> None:
        self._durable_sink = durable_sink if durable_sink is not None else ApplicationAuditSink()
        self._denial_window_ms = int(round(denial_coalesce_window_s * 1000))
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
        (D-10's own instruction). Every other refusal is counted in the
        durable refusal window before its response is returned; a count
        that cannot be recorded raises `errors.AuditSinkUnavailable`."""
        if reason_code not in DURABLE_DENIAL_CODES:
            return
        fields = {
            "event_class": event_class, "request_id": request_id, "application_id": application_id,
            "actor_type": actor_type, "actor_id": actor_id, "role": role, "operation": operation,
            "target_kind": target_kind, "reason_code": reason_code, "target_id": target_id,
        }
        try:
            self._durable_sink.record_denial(window_ms=self._denial_window_ms, **fields)
        except Exception as exc:
            raise AuditSinkUnavailable(
                "the durable audit sink could not record this denial; it was refused"
            ) from exc

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


__all__ = [
    "DURABLE_DENIAL_CODES",
    "AuditRouter",
]
