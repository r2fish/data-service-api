"""Phase 4 WP-2(b) (design docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md D-5/
D-6): `audit_query`'s cursor codec and its in-memory read surface.

This module deliberately imports no `psycopg` (mirroring `audit.py`'s own
"this top-level package stays importable without psycopg installed"
property, `r2db_api/__init__.py`'s header) -- `credential_store.py`'s
`PostgresAuditQueryStore` is this module's Postgres-backed sibling, holding
the identical `(recorded_at, plane, event_id)`-ordered, cursor-paged, lag-
filtered semantics against real SQL instead of two in-memory lists (D-10
parity: `r2db-api/tests/test_audit_query.py::
test_in_memory_and_postgres_audit_query_semantics_have_parity` runs the
SAME assertions against both).

Cursor (D-6): an OPAQUE token encoding `(recorded_at, plane, event_id)` --
never an `event_id` alone (`event_id`'s uniqueness is only guaranteed within
one durable table's own PRIMARY KEY; the `control_audit`/`application_audit`
UNION has no cross-table uniqueness guarantee on `event_id`, contract
`audit.query_ordering`). A client must never construct or interpret this
string -- `decode_cursor` accepts only what `encode_cursor` produced,
raising on anything else, mapped by `ControlPlaneService.audit_query` to
`VALIDATION_FAILED` (never a 500/`AttributeError`/`KeyError` escaping this
module for a malformed or foreign token).
"""
from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol, Sequence

# WP-2(b) fix round 2 (coordinator item H): the SINGLE source for the
# denial-coalescing window (`DECLARED_COALESCING_WINDOW_MS`, below) --
# `control_plane.py` already imports `from .service import ControlAuthority`,
# so this module importing `service.py` too introduces no new dependency
# and no import cycle (`service.py` itself imports none of `audit.py`'s
# siblings that lead back here -- verified directly, not assumed).
from .service import _DENIAL_COALESCE_WINDOW_S

# D-7: the vocabulary this peer's `audit_query` reader can ever surface,
# across BOTH `control_audit` (control_plane.py's own `_deny`/
# `_write_state_audit` call sites) and `application_audit` (service.py's
# `_event`/`_denial_event` call sites) --
# `capabilities().audit_query.event_classes` publishes exactly this set
# (`control_plane.py`), and `r2db-api/tests/test_audit_query.py::
# test_declared_event_classes_cover_every_emittable_class` fixes it against
# both modules' own real `event_class=` literals by name, so a future new
# call site with an unlisted class is caught here, not silently under-
# declared. "authentication" (successful auth, `service.py`'s `_event`
# call at "authentication") is deliberately EXCLUDED: it never reaches the
# durable sink at all (`_event`'s own comment: "no durable record at
# all"), so it can never actually appear through `audit_query`.
DECLARED_AUDIT_EVENT_CLASSES = frozenset(
    {
        # application-plane (service.py) -- durable-eligible only.
        "data_operation",
        "privilege_sensitive",
        "authorization_denial",
        "operation_denial",
        "privilege_denial",
        "authentication_denial",
        "security_control_failure",
        # control-plane (control_plane.py) -- every `control_audit` row is
        # durable by construction (no coalescing on this plane).
        "application_lifecycle",
        "capability_denial",
        "control_credential_lifecycle",
        "credential_lifecycle",
    }
)

# Phase 5 WP-2 (design docs/design/PHASE5_CONTRACT_150_AND_LIMIT_RANGE_V1.md
# D-1, contract 1.5.0 subordinate ruling 10 item 1): the `operation`
# vocabulary this peer's `audit_query` reader can ever surface -- same
# declare-the-hazard posture as `DECLARED_AUDIT_EVENT_CLASSES` above, and
# fixed against the real source by the SAME generalized AST scanner
# (`r2db-api/tests/test_audit_query.py`'s `U == D | N` equality, now
# parameterized over `event_class`/`operation`/`target_kind` instead of
# `event_class` alone). Deliberately EXCLUDES 4 words -- 3 for one reason,
# 1 for a DIFFERENT reason (fix-round M-1, Opus review):
# - `delete_audit`, `set_authorization_state_available`, `set_credential_
#   state`: each is real (found by the scanner's own unfiltered walk) but
#   every one of its emit sites is `ControlAuthority._control_event`
#   (`service.py`), which writes ONLY to the legacy in-memory `AuditSink`,
#   never to `control_audit`/`application_audit` (`ControlAuthority.
#   _control_event`'s own docstring: "ControlAuthority's own audit trail
#   stays on the existing in-memory AuditSink ... not on the new
#   control_audit table").
# - `control_capabilities`: a DIFFERENT shape of non-durability (fix-round
#   M-1) -- its only 2 emit sites (`control_plane.py`'s `capabilities()`
#   method, `_authorize_role(context, operation="control_capabilities",
#   ...)` and `_gate_must_rotate(context, operation="control_capabilities",
#   ...)`) can NEVER reach a `_deny` call for this operation AT ALL, on any
#   role or must_rotate state -- not merely "reaches a non-durable sink".
#   `_authorize_role`'s own deny condition is `role == "audit" and
#   operation not in _AUDIT_ROLE_ALLOWED_OPERATIONS`; `"control_
#   capabilities"` is a PERMANENT member of that allow-list (`control_
#   plane.py`'s own `_AUDIT_ROLE_ALLOWED_OPERATIONS`), so the condition is
#   never true for it. `_gate_must_rotate`'s own body opens with `if
#   operation == "control_capabilities": return` -- an unconditional early
#   return before its own `_deny` call. No other emit site anywhere in the
#   package ever passes this literal (`grep` real-source confirmed). See
#   `test_audit_query.py`'s own `test_control_capabilities_operation_has_
#   no_reachable_deny_branch` for the structural + behavioral fixed proof
#   (this word has no failure mode to durably record in the first place,
#   so it is not exercised by the OTHER 3 words' runtime-observation test).
# `authenticate` is NOT excluded, unlike the original 8-word candidate
# list's naive reading (design §1.4 の 8) might suggest --
# `DataService.authenticate`'s SUCCESS event (`_event(...,
# event_class="authentication")`) is indeed non-durable-only, but its
# FAILURE path (`except FoundationError`, `_denial_event(event_class=
# "authentication_denial", operation="authenticate", ...)`) durably routes
# through the coalescing denial router whenever `exc.code` is one of
# `_DURABLE_DENIAL_CODES` (`AUTH_REQUIRED`/`AUTH_INVALID`/`AUTH_REVOKED`
# among them) -- an actually-observed durable row is what caught this
# during WP-2 (`conformance-tests/test_c09_audit_evidence.py`'s own
# declaration-agreement vector), confirming the design's own "N は実行時
# テストで確定する" discipline is load-bearing, not a formality.
DECLARED_AUDIT_OPERATIONS = frozenset(
    {
        "audit_buffer",
        "audit_query",
        "authenticate",
        "bootstrap_control_credential",
        "catalog",
        "control_authenticate",
        "cross_entity_mutate",
        "delete_credential",
        "disable_application",
        "disable_credential",
        "enable_application",
        "enable_control_credential",
        "enable_credential",
        "freeze_issuance",
        "issue_audit_credential",
        "issue_credential",
        "list_applications",
        "list_credentials",
        "mutate",
        "query",
        "register_application",
        "reset_control_credentials",
        "revoke_credential",
        "rotate_control_credential",
        "rotate_credential",
        "schema",
        "unfreeze_issuance",
    }
)

# Phase 5 WP-2 (same design/ruling as `DECLARED_AUDIT_OPERATIONS` above):
# the `target_kind` vocabulary. Deliberately EXCLUDES `application_or_
# credential` -- its only emit site is `ControlAuthority._control_event`
# (`service.py`, hardcoded), the same non-durable-only legacy sink
# described above.
DECLARED_AUDIT_TARGET_KINDS = frozenset(
    {
        "application",
        "audit_sink",
        "control_credential",
        "credential",
        "entity",
    }
)

# Ruling J-4 (WP-2cd audit N-5, contract 1.7.0 D-5 (1)(v)): the `outcome`
# vocabulary this peer's real source ever emits on an `AuditEvent` -- unlike
# `event_class`/`operation`/`target_kind` above, this is NOT itself a
# contract-declared capability field (`query_operation_vocabulary`/`query_
# target_kind_vocabulary` name only those three; `outcome` has no `.audit_
# query.outcomes` counterpart in `spec/data-service-api.v1.json`), so this
# constant is a peer-local pin only -- never published through
# `capabilities()`. "allow"/"deny" are the pre-Phase-4 pair; "error" is
# D-2's own durable commit-failure row (`_PreCommitHook.commit_failed`/
# `postgres.py`'s own `except psycopg.Error` clauses); "replayed" (WP-2cd,
# ruling J-4) is the newest member -- a resend answered from an idempotency
# record, which must never be indistinguishable from "no evidence at all"
# for a destructive operation (SI-14). `r2db-api/tests/test_idempotency_
# records.py::test_declared_audit_outcomes_include_replayed` fixes this
# set, via the SAME generalized AST scanner (`_field_literal_union`) the
# 3 constants above already use, against every real `outcome=` literal in
# `src/r2db_api/` -- no separate N (non-durable exclusion) set is needed
# here: every outcome word this package ever emits reaches a durable or
# legacy sink by construction (there is no non-durable-only `outcome=` call
# site the way `operation`/`target_kind` each have a few).
DECLARED_AUDIT_OUTCOMES = frozenset({"allow", "deny", "error", "replayed"})

# D-3 (P4-D3, confirmed value) -- the denial-coalescing window. Declared in
# `capabilities().audit_query.coalescing_window_ms` (control_plane.py) so a
# consumer can interpret a `count`-bearing coalesced row's own time span
# without guessing it. DERIVED from `_DENIAL_COALESCE_WINDOW_S` (imported
# above) -- the single real enforced value -- rather than a second,
# independently-maintained literal that could silently drift from it.
# `r2db-api/tests/test_audit_query.py::
# test_declared_coalescing_window_ms_matches_the_design_value` fixes the
# declared capability value against this same derivation.
DECLARED_COALESCING_WINDOW_MS = int(_DENIAL_COALESCE_WINDOW_S * 1000)

_CURSOR_KEYS = ("recorded_at", "plane", "event_id")


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def encode_cursor(recorded_at: datetime, plane: str, event_id: str) -> str:
    """Opaque, base64url-encoded JSON -- deliberately not a bare delimited
    string (an `event_id`/`plane` value can never contain a delimiter that
    would need escaping, since this is JSON, not string concatenation)."""
    payload = {"recorded_at": _to_utc(recorded_at).isoformat(), "plane": plane, "event_id": event_id}
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_cursor(token: str) -> tuple[datetime, str, str]:
    """Raises `ValueError` on anything that is not a cursor this module's
    own `encode_cursor` produced -- the caller (`ControlPlaneService.
    audit_query`) maps this to `VALIDATION_FAILED`, never lets it escape as
    an unclassified 500."""
    if not isinstance(token, str) or not token:
        raise ValueError("cursor must be a non-empty string")
    try:
        raw = base64.urlsafe_b64decode(token.encode("ascii"))
        payload = json.loads(raw)
    except Exception as exc:  # noqa: BLE001 -- any decode failure is a bad cursor, not a bug here
        raise ValueError("cursor is not a valid opaque token") from exc
    if not isinstance(payload, dict) or set(payload) != set(_CURSOR_KEYS):
        raise ValueError("cursor payload has an unexpected shape")
    plane = payload["plane"]
    event_id = payload["event_id"]
    if not isinstance(plane, str) or plane not in ("control", "application") or not isinstance(event_id, str):
        raise ValueError("cursor payload has an unexpected shape")
    try:
        recorded_at = datetime.fromisoformat(payload["recorded_at"])
    except Exception as exc:  # noqa: BLE001
        raise ValueError("cursor recorded_at is not a valid timestamp") from exc
    return _to_utc(recorded_at), plane, event_id


class AuditQueryReader(Protocol):
    """The call surface `ControlPlaneService.audit_query` needs from a
    reader -- `PostgresAuditQueryStore` (credential_store.py) and
    `InMemoryAuditQueryStore` (below) both implement it (D-10 parity)."""

    def query(
        self, *, event_classes: Sequence[str] | None, after: tuple[datetime, str, str] | None, limit: int, visibility_lag_ms: int
    ) -> list[dict[str, Any]]: ...


def _summary_dict(event: Any, window_end: datetime) -> dict[str, Any]:
    """A refusal-window summary event as the plain-dict shape
    `InMemoryAuditQueryStore.query` returns: `recorded_at` is the end of
    the window the summary stands for, not the event's own `occurred_at`
    (the first refusal's), so the summary sorts where the closed window
    ends."""
    row = _event_dict(event, plane="application")
    assert row is not None  # the sink's own `occurred_at` is always ISO-8601
    row["recorded_at"] = _to_utc(window_end)
    return row


def _event_dict(event: Any, *, plane: str) -> dict[str, Any] | None:
    """Reads an `audit.AuditEvent` dataclass instance's fields into the
    plain-dict shape `InMemoryAuditQueryStore.query` returns -- `occurred_at`
    doubles as this in-memory reader's own `recorded_at` proxy (D-6's
    visibility-lag/cursor semantics; in-memory writes are synchronous, so
    there is no separate "transaction commits later than its own
    timestamp" hazard the real `clock_timestamp()` column exists to guard
    against on Postgres -- see this module's own header)."""
    try:
        recorded_at = datetime.fromisoformat(event.occurred_at)
    except (ValueError, TypeError):
        return None
    return {
        "event_id": event.event_id,
        "event_class": event.event_class,
        "occurred_at": event.occurred_at,
        "request_id": event.request_id,
        "application_id": event.application_id,
        "actor_type": event.actor_type,
        "actor_id": event.actor_id,
        "role": event.role,
        "operation": event.operation,
        "target_kind": event.target_kind,
        "outcome": event.outcome,
        "reason_code": event.reason_code,
        "target_id": event.target_id,
        "count": event.count,
        "recorded_at": _to_utc(recorded_at),
        "plane": plane,
    }


class InMemoryAuditQueryStore:
    """D-10's in-memory reader pair -- UNIONs `control_audit`'s in-memory
    half (`audit.ControlAuditSink`) and `application_audit`'s in-memory
    half (`audit.ApplicationAuditSink`), applying the identical
    `(recorded_at, plane, event_id)` order, opaque-cursor paging, and
    visibility-lag filtering `PostgresAuditQueryStore` applies via SQL. The
    application plane's refusal-window summary events come from the sink's
    own tally table (`ApplicationAuditSink.denial_window_summaries`), where
    the Postgres reader reads the counter table.

    Constructed once by both the in-process conformance adapter (WP-1's
    own `conformance_adapter_r2db.py`, wired this WP) and (only for the
    control-plane's OWN peer-local in-memory-backend tests) `r2db-api/
    tests/test_audit_query.py` -- never by `control_main.py`, which always
    talks to a real Postgres platform database when `audit_query` is
    `enabled`.
    """

    def __init__(self, control_audit: Any, application_audit: Any) -> None:
        self._control_audit = control_audit
        self._application_audit = application_audit

    def query(
        self, *, event_classes: Sequence[str] | None, after: tuple[datetime, str, str] | None, limit: int, visibility_lag_ms: int
    ) -> list[dict[str, Any]]:
        threshold = datetime.now(timezone.utc) - timedelta(milliseconds=visibility_lag_ms)
        class_filter = set(event_classes) if event_classes is not None else None
        rows: list[dict[str, Any]] = []
        for plane, sink in (("control", self._control_audit), ("application", self._application_audit)):
            # `sink._events` (private list of `AuditEvent`), not `.events()`
            # (which returns `None`-filtered `MappingProxyType`s that would
            # lose fields this reader always needs, e.g. an `outcome` that
            # happens never to be `None` is fine, but the *filtering itself*
            # is the wrong shape for this reader -- it wants every field by
            # name, present or not). Mirrors this package's own established
            # `# noqa: SLF001` reach-in convention for same-package private
            # state (e.g. `control_plane.InMemoryControlBackend`).
            for event in list(sink._events):  # noqa: SLF001
                row = _event_dict(event, plane=plane)
                if row is None:
                    continue
                if row["recorded_at"] >= threshold:
                    continue
                if class_filter is not None and row["event_class"] not in class_filter:
                    continue
                if after is not None and (row["recorded_at"], row["plane"], row["event_id"]) <= after:
                    continue
                rows.append(row)
        # The summary events of the application plane's closed refusal
        # windows: read from the sink's own table of window tallies, the
        # in-memory counterpart of the counter table the Postgres reader
        # adds to its UNION.
        for summary, window_end in self._application_audit.denial_window_summaries(closed_before=threshold):
            row = _summary_dict(summary, window_end)
            if class_filter is not None and row["event_class"] not in class_filter:
                continue
            if after is not None and (row["recorded_at"], row["plane"], row["event_id"]) <= after:
                continue
            rows.append(row)
        rows.sort(key=lambda row: (row["recorded_at"], row["plane"], row["event_id"]))
        return rows[:limit]


__all__ = [
    "DECLARED_AUDIT_EVENT_CLASSES",
    "DECLARED_AUDIT_OPERATIONS",
    "DECLARED_AUDIT_TARGET_KINDS",
    "DECLARED_AUDIT_OUTCOMES",
    "DECLARED_COALESCING_WINDOW_MS",
    "AuditQueryReader",
    "InMemoryAuditQueryStore",
    "encode_cursor",
    "decode_cursor",
]
