"""ASGI HTTP boundary over the MitateDB-api foundation (WP-3, docs/design/
MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md v1.2 R-5).

This module owns the HTTP surface only -- authority, structured-operation
validation, and value-domain enforcement all stay in `cell.py`/
`backend_sqlite.py`/`backend_postgres.py`/`auth.py`/
`credential_store_postgres.py` (R-3's own seam split); this file only
translates the contract's endpoint table (`spec/data-service-api.v1.json`)
onto a `HttpService` (below) and maps outcomes to
`application/problem+json`.

Independent implementation (R-2's closing paragraph: no code sharing
between peers): this is not a port of `r2db_api.http`. It follows the same
GENERAL shape (Starlette ASGI app, contract-driven top-level shape
checking, an ASGI-receive-loop byte-bound middleware) because both peers
share the same execution-environment parts by design decision (D-B), not
because either file's own code was copied.

Request shapes are not re-declared with a second (pydantic) type system:
`spec/data-service-api.v1.json` is read at import time and used as the
single source of truth for which top-level request fields are accepted.
"""
from __future__ import annotations

import json
from importlib import resources
from typing import Any, Awaitable, Callable, Mapping

from starlette.applications import Starlette
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .auth import Role
from .backend import UNCHANGED
from .cell import ApplicationDeveloper, ApplicationRuntime, Filter
from .errors import (AuditSinkUnavailable, AuthenticationError,
                     AuthorizationError, AuthorizationStateUnavailable,
                     CapabilityError, ConflictError,
                     DestructiveConfirmationRequired, FoundationError,
                     NotFoundError, PlatformUpgradePending,
                     PreconditionFailedError, ResourceLimitError,
                     StorageConfigurationError, ValidationError)

PROBLEM_CONTENT_TYPE = "application/problem+json"

# --------------------------------------------------------------------------
# Contract as the single source of truth for request shapes (Phase 6
# WP-0, design D-4(b)).
#
# `spec/data-service-api.v1.json` in the common repository remains the
# authored source of truth (CLAUDE.md: this package must not become the
# implicit owner of the public contract). What ships inside this
# distribution is a byte-identical packaged *copy*
# (`mitatedb_api/contract/data-service-api.v1.json`, wired in as package
# data in `pyproject.toml`), loaded via `importlib.resources` so a unit
# installed or copied onto the VPS without the sibling `spec/` checkout
# still imports -- this replaces the prior repository-relative lookup
# (`Path(__file__).resolve()` walked three parent directories up to
# `"spec"`), which broke the moment this package was installed/copied
# anywhere that checkout was not a sibling three directories up (the
# known coupling design D-4(b) closes). `r2db_api.http`'s own loader took
# the identical repository-relative form as a FALLBACK behind its
# packaged copy (never this package's own primary path, which had no
# packaged copy to fall back to before this WP); the supervisor's own WP-0
# peer-symmetry ruling (2026-09-04) removed that fallback too, so both
# peers now resolve the contract exclusively through `importlib.
# resources` against their own packaged copy, no fallback on either side.
# `tests/test_http.py::test_packaged_contract_copy_is_byte_identical_to_
# spec_source_of_truth` asserts the packaged copy never silently drifts
# from `spec/`.
# --------------------------------------------------------------------------

_CONTRACT_PATH = resources.files("mitatedb_api.contract").joinpath("data-service-api.v1.json")
_CONTRACT = json.loads(_CONTRACT_PATH.read_text())
_SCHEMAS = _CONTRACT["schemas"]
_DEFINITIONS = _CONTRACT["definitions"]

# --------------------------------------------------------------------------
# HTTP status <-> contract error code (R-5 m-12: cross-peer status
# agreement is tracked conformance evidence, contract errors.http_status_
# note). Every code this peer can actually emit is listed here, mapped to
# the SAME status r2db-api's own call sites use for that code (grep'd from
# r2db-api/src/r2db_api/*.py's own `fail(...)`/`FoundationError(...)`
# call sites -- r2db-api itself is not imported or modified, only read for
# this cross-check per the task brief). No divergence was needed: every
# code below agrees with r2db-api's own mapping. This peer simply never
# emits several contract codes at all (AUTH_REVOKED, APPLICATION_DISABLED,
# SCOPE_MISMATCH, ATOMICITY_FAILED, IDENTIFIER_INVALID -- `auth.py`/
# `credential_store_postgres.py` fold "revoked"/"disabled" into a single
# `AuthenticationError` -> AUTH_INVALID, and `identifiers.py` raises the
# same `ValidationError` -> VALIDATION_FAILED for a malformed identifier
# as for any other malformed shape); that is a pre-existing fact about
# this peer's own error vocabulary, not something WP-3 narrows, and is
# reported to the requester as a known divergence (not a status mismatch
# -- there is nothing to compare a peer never emits).
#
# Phase 9 WP-3b (design D-4/D-3 (6), 追補 2 S-h): PRECONDITION_FAILED is
# no longer in that "never emits" set -- `errors.PreconditionFailedError`
# (a stale `plan` token) is this peer's first real source of it, mapped
# to 412 -- the SAME status `r2db-api/src/r2db_api/structured.py`/
# `postgres.py` already use for their own (row-level) `PRECONDITION_
# FAILED` `fail(..., status=412)` call sites (cross-peer status
# agreement, R-5 m-12).
_STATUS_BY_CODE: dict[str, int] = {
    "AUTH_REQUIRED": 401,
    "AUTH_INVALID": 401,
    "AUTH_STATE_UNAVAILABLE": 503,
    "FORBIDDEN": 403,
    "VALIDATION_FAILED": 400,
    "CAPABILITY_UNSUPPORTED": 400,
    "NOT_FOUND": 404,
    "CONFLICT": 409,
    "PRECONDITION_FAILED": 412,
    "LIMIT_EXCEEDED": 413,
    "DESTRUCTIVE_CONFIRMATION_REQUIRED": 409,
    "SERVICE_UNAVAILABLE": 503,
}

# `errors.FoundationError` subclass -> contract code, evaluated in order
# (mirrors `conformance_adapter_mitatedb.py::_CLASSIFY_ORDER`, extended
# with `StorageConfigurationError` -- unreachable on the in-process
# adapter's own SQLite backend, real on this HTTP composition's PostgreSQL
# backend/credential store -- mapped to `SERVICE_UNAVAILABLE` per that
# class' own documented proposal, `errors.py`). Phase 4 (design PHASE4_
# DURABLE_AUDIT_SINK_V1.md D-2/D-3): `AuditSinkUnavailable` is likewise
# mapped to `SERVICE_UNAVAILABLE` -- a durable-audit-sink failure on a
# fail-closed-class operation or denial, distinct from both
# `StorageConfigurationError` (a permanent DATA-backend privilege defect)
# and `AuthorizationStateUnavailable` (the credential store's own
# unreachability). Listed explicitly here (not left to the exhaustive-by-
# construction fallback in `_classify` below) so that fallback's own
# "pragma: no cover" comment stays true.
_CLASSIFY_ORDER: tuple[tuple[type[FoundationError], str], ...] = (
    (AuthorizationStateUnavailable, "AUTH_STATE_UNAVAILABLE"),
    (StorageConfigurationError, "SERVICE_UNAVAILABLE"),
    (AuditSinkUnavailable, "SERVICE_UNAVAILABLE"),
    (AuthenticationError, "AUTH_INVALID"),
    (AuthorizationError, "FORBIDDEN"),
    (CapabilityError, "CAPABILITY_UNSUPPORTED"),
    (ValidationError, "VALIDATION_FAILED"),
    (ResourceLimitError, "LIMIT_EXCEEDED"),
    (DestructiveConfirmationRequired, "DESTRUCTIVE_CONFIRMATION_REQUIRED"),
    # Phase 9 WP-3b (design D-4/D-3 (6), 追補 2 S-h): a stale `plan` --
    # a real, present precondition denial, checked at the
    # `destructive_confirmation.evaluation_order` precondition stage
    # (after confirmation validity, D-4 (2)) -- classifies before
    # `ConflictError`/`NotFoundError` here, matching this table's own
    # existing convention of listing the more specific denial first
    # (`DestructiveConfirmationRequired` already precedes `ConflictError`
    # immediately above); no ordering ambiguity arises in practice, since
    # no call site ever raises more than one of these for a single
    # request.
    (PreconditionFailedError, "PRECONDITION_FAILED"),
    (ConflictError, "CONFLICT"),
    (NotFoundError, "NOT_FOUND"),
)


def _classify(exc: FoundationError) -> str:
    for exc_type, code in _CLASSIFY_ORDER:
        if isinstance(exc, exc_type):
            return code
    return "SERVICE_UNAVAILABLE"  # pragma: no cover - exhaustive by construction


def _problem(code: str, message: str, *, request_id: str, details: Mapping[str, Any] | None = None) -> JSONResponse:
    body = {"type": code, "code": code, "message": message, "request_id": request_id, "details": dict(details or {})}
    return JSONResponse(body, status_code=_STATUS_BY_CODE.get(code, 400), media_type=PROBLEM_CONTENT_TYPE)


def _problem_for_exception(exc: FoundationError, request_id: str) -> JSONResponse:
    code = _classify(exc)
    # SI-10: never surface `str(exc)`/SQL/connection details/exception
    # internals on the wire. Every code below gets a fixed, static,
    # non-interpolated message; the only per-request data that ever
    # reaches a response body is `details`, which is itself already
    # constrained to the safe, structured shape `errors.
    # ResourceLimitError`/`errors.DestructiveConfirmationRequired` publish
    # (`limit_class` / the four declare-and-echo keys) -- never the raw
    # exception message.
    #
    # Q4 rework (supervisor ruling 2026-09-05, H-1; design §3.8's own
    # "F-12だけは...API応答として利用者に届く"): `PlatformUpgradePending`
    # is the ONE exception this exemption applies to -- `isinstance`
    # (never the classified `code`, which is the same `SERVICE_UNAVAILABLE`
    # every OTHER `StorageConfigurationError` also classifies to) narrows
    # to exactly this subclass, so this stays a one-exception carve-out,
    # not a hole every current or future `StorageConfigurationError` site
    # falls through. `platform_upgrades._f12_message`'s own construction
    # already excludes DSN/credential/internal-hostname/declared-value
    # text -- only the missing upgrade numbers and the next `ops` command
    # appear -- so `str(exc)` is safe to surface verbatim here.
    if isinstance(exc, PlatformUpgradePending):
        return _problem(code, str(exc), request_id=request_id, details=getattr(exc, "details", None))
    message = {
        "AUTH_STATE_UNAVAILABLE": "Authorization state is unavailable.",
        "SERVICE_UNAVAILABLE": "The service is temporarily unavailable.",
        "AUTH_INVALID": "Credential is not valid.",
        "FORBIDDEN": "This operation is not permitted for this credential.",
        "CAPABILITY_UNSUPPORTED": "This capability is not supported.",
        "VALIDATION_FAILED": "The request failed validation.",
        "LIMIT_EXCEEDED": "The request exceeds a configured resource limit.",
        "DESTRUCTIVE_CONFIRMATION_REQUIRED": "This destructive operation requires the current confirmation phrase.",
        "PRECONDITION_FAILED": "The declared precondition no longer holds.",
        "CONFLICT": "The request conflicts with existing state.",
        "NOT_FOUND": "The requested resource was not found.",
    }.get(code, "The request could not be completed.")
    details = getattr(exc, "details", None)
    return _problem(code, message, request_id=request_id, details=details)


def _generic_service_unavailable(request_id: str) -> JSONResponse:
    # SI-10: an uncaught, non-FoundationError exception must never reach
    # the client as a traceback or internal message. The real exception is
    # deliberately discarded here (never interpolated into the response,
    # never logged by this layer) rather than risking an unsafe partial
    # rendering of it.
    return _problem("SERVICE_UNAVAILABLE", "The service is temporarily unavailable.", request_id=request_id)


# --------------------------------------------------------------------------
# Byte bound before parsing (SI-08) + per-request id.
# --------------------------------------------------------------------------

REQUEST_ID_HEADER = b"x-request-id"


class RequestByteBoundMiddleware:
    """Enforces `limits.request_bytes` before the wrapped app runs.

    The bound is measured from actual bytes received in the ASGI receive
    loop, never from the `Content-Length` header (a chunked body or a
    lying header must still be bounded). The whole body is drained and
    measured here before the wrapped Starlette app is invoked at all; an
    over-bound request never reaches Starlette's own routing/body-parsing
    machinery, so this is a real, structural pre-parse rejection, not a
    late check performed after JSON decoding.
    """

    def __init__(self, app: ASGIApp, *, request_bytes_limit: int) -> None:
        self.app = app
        self._limit = request_bytes_limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        import uuid

        request_id = uuid.uuid4().hex
        state = scope.setdefault("state", {})
        state["request_id"] = request_id

        buffered: list[Message] = []
        total = 0
        exceeded = False
        exceeded_more_body = False
        while True:
            message = await receive()
            if message.get("type") == "http.request":
                total += len(message.get("body", b""))
                if total > self._limit:
                    exceeded = True
                    exceeded_more_body = bool(message.get("more_body", False))
                    break
                buffered.append(message)
                if not message.get("more_body", False):
                    break
            else:
                buffered.append(message)
                break

        if exceeded:
            # m-6 (independent review): drain the REST of the client's
            # body before answering, discarding every remaining chunk, so
            # no unread bytes are ever left on the connection. Harmless
            # under `httpx.ASGITransport` (this repository's own tests,
            # and both conformance adapters, drive this middleware exactly
            # that way -- an in-process transport with no real socket to
            # leave dangling), but load-bearing under a real ASGI server
            # (uvicorn): leaving unread bytes after sending a response
            # risks the server treating them as the start of the NEXT
            # request on a keep-alive connection, or having to reset the
            # connection outright either way. Only drains when the chunk
            # that tipped the limit itself declared `more_body: true` --
            # calling `receive()` again after a chunk that already
            # declared the body complete is not meaningful ASGI protocol
            # use and is skipped entirely.
            still_more = exceeded_more_body
            while still_more:
                message = await receive()
                still_more = message.get("type") == "http.request" and bool(message.get("more_body", False))
            error = ResourceLimitError("request body exceeds the configured resource limit", limit_class="request_bytes")
            await self._send_directly(send, error, request_id)
            return

        iterator = iter(buffered)

        async def replay_receive() -> Message:
            try:
                return next(iterator)
            except StopIteration:
                return await receive()

        async def guarded_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((REQUEST_ID_HEADER, request_id.encode()))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, replay_receive, guarded_send)

    @staticmethod
    async def _send_directly(send: Send, error: ResourceLimitError, request_id: str) -> None:
        """Sends a problem+json response without a Starlette Request/
        Response object -- used only for the byte-bound rejection, which
        happens before the wrapped Starlette app is ever invoked."""
        response = _problem_for_exception(error, request_id)
        headers = [
            (b"content-type", PROBLEM_CONTENT_TYPE.encode() + b"; charset=utf-8"),
            (REQUEST_ID_HEADER, request_id.encode()),
        ]
        body = response.body
        headers.append((b"content-length", str(len(body)).encode()))
        await send({"type": "http.response.start", "status": response.status_code, "headers": headers})
        await send({"type": "http.response.body", "body": body})


# --------------------------------------------------------------------------
# Shape checking against the contract (mirrors r2db_api.http's identical
# technique, read-only reference per the task brief -- independently
# implemented here, not copied): reject an unknown top-level field or a
# missing required one, per `additionalProperties: false` + `required`.
# --------------------------------------------------------------------------


def _check_object_shape(value: Any, schema: Mapping[str, Any], *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError(f"{label} must be an object")
    allowed = set(schema.get("properties", {}))
    extra = set(value) - allowed
    if extra:
        raise ValidationError(f"{label} contains unsupported fields: {sorted(extra)}")
    missing = set(schema.get("required", [])) - set(value)
    if missing:
        raise ValidationError(f"{label} is missing required fields: {sorted(missing)}")
    return value


def _deny_provisional_field(field_name: str) -> None:
    """Contract 1.7.0 provisional gate (design docs/design/
    PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md §3 D-1 (3); work
    order docs/work-orders/WORK_ORDER_PHASE9_CONTRACT_170_V1.md §2 WP-1 (9)):
    `_check_object_shape` above now accepts `dry_run`/`plan`/`budget`/
    `enum`/`nullable`/`field_constraints`/`SchemaOperationRequest.
    idempotency_key` (the packaged contract copy is already 1.7.0). This
    peer's own `constraint_declarations` capability flipped to `enabled`
    in the WP-3a commit (`enum`/`nullable`/`field_constraints` removed
    from `_PROVISIONAL_UNSUPPORTED_*_FIELDS` below, same commit), and
    `dry_run` flips to `enabled` in THIS commit (WP-3b: `dry_run`/`plan`
    removed from `_PROVISIONAL_UNSUPPORTED_*_FIELDS` below, same commit
    as `cell.py`'s own real dry_run/plan behavior, P-3) -- `budget`/
    `idempotency_key` remain `unavailable` (WP-3d/WP-3c), so accepting
    either of THOSE and silently ignoring it would still be a P-3
    violation (declaration says `unavailable`, behavior accepts the
    field). `details` is set directly
    on the raised instance (rather than a new `CapabilityError.__init__`
    parameter) so this gate does not preempt WP-3e's own planned `details`
    attribute rollout for `CapabilityError`/`ValidationError` (D-3 (5));
    `_problem_for_exception` already surfaces any `getattr(exc, "details",
    None)` regardless of how it was set.
    """
    err = CapabilityError(f"{field_name} is not supported by this peer")
    err.details = {"violated_declaration": "capability", "field": field_name}
    raise err


# Phase 9 WP-3b: `dry_run`/`plan` removed -- `post_mutate`/`post_cross_
# entity_mutate` below now pass both through to `session.transact()` for
# real instead of gating them here. `budget` stays gated (WP-3d).
_PROVISIONAL_UNSUPPORTED_MUTATION_REQUEST_FIELDS = ("budget",)
_PROVISIONAL_UNSUPPORTED_QUERY_REQUEST_FIELDS = ("budget",)
# Phase 9 WP-3a (design docs/design/
# PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md D-1 (4)):
# `field_constraints`/`enum`/`nullable` removed from this gate -- same
# commit as `constraint_declarations` flipping to `enabled` below
# (`cell.py::ApplicationRuntime.capabilities`) and the real enforcement
# each governs. Phase 9 WP-3b: `dry_run`/`plan` removed too -- same
# commit as `dry_run` flipping to `enabled` and `post_schema` below
# passing both through to `create_entity`/`add_field`/`alter_field` for
# real. `budget`/`idempotency_key` are UNCHANGED -- their own
# capabilities stay `unavailable` until WP-3d/WP-3e.
_PROVISIONAL_UNSUPPORTED_SCHEMA_OPERATION_REQUEST_FIELDS = (
    "budget", "idempotency_key",
)


def _deny_first_provisional_field(body: Mapping[str, Any], field_names: tuple[str, ...]) -> None:
    for field_name in field_names:
        if field_name in body:
            _deny_provisional_field(field_name)


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", ""))


async def _read_json_object(request: Request) -> dict[str, Any]:
    try:
        payload = await request.json()
    except json.JSONDecodeError as exc:
        raise ValidationError("request body must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValidationError("request body must be a JSON object")
    return payload


# --------------------------------------------------------------------------
# Authentication: `Authorization: Bearer <credential_id>.<secret>`.
#
# WP-3 design decision (reported to the requester, §4 of the completion
# report -- the design document specifies "Authorization ヘッダの
# credential" but does not fix a wire encoding for THIS peer specifically):
# `auth.CredentialStore.authenticate`/`credential_store_postgres.
# PostgresCredentialStore.authenticate` both look a credential up by an
# explicit `(credential_id, secret)` PAIR (`WHERE credential_id = ...`,
# unlike r2db-api's own verifier-keyed single-secret lookup) -- there is no
# way to authenticate with `secret` alone on this peer. The bearer token
# is therefore the two values joined by a single `.`:
# `credential_id + "." + secret`. This is unambiguous: `credential_id`
# (`secrets.token_hex(12)`) and `secret` (`secrets.token_urlsafe(32)`) are
# both produced by this peer's own issuance path and neither alphabet ever
# contains `.`, so `token.split(".", 1)` always recovers the original pair
# exactly. A future in-band `/control/v1 issue_credential` (WP-4/5) would
# need to publish this SAME composite as its own `CredentialIssued.secret`
# field (the contract does not require any particular internal structure
# for that opaque string) for a real client to construct a usable bearer
# token at all.
# --------------------------------------------------------------------------


class _CredentialMissing(Exception):
    """No `Authorization` header (or no usable bearer token in it) was
    presented at all -- distinct from a token that WAS presented but is
    wrong/malformed (`_CredentialMalformed`), matching contract
    `errors.codes`' own distinction between `AUTH_REQUIRED` and
    `AUTH_INVALID`."""


class _CredentialMalformed(Exception):
    """Phase 6 WP-3 差し戻し 最終ラウンド (supervisor ruling 2026-09-04,
    裁定 1): kept only as a documented historical marker -- no code on
    this peer constructs this exception any more. Before this round, this
    HTTP boundary split a presented bearer itself and raised this class
    for an unparseable shape; splitting now happens exactly once, inside
    the credential store (`auth.CredentialStore.authenticate`/
    `credential_store_postgres.PostgresCredentialStore.authenticate`), so
    a malformed bearer reaches this boundary as an ordinary `Authentication
    Error` (`AUTH_INVALID`) instead -- `_endpoint`'s own `except` clause
    below still names this class for defense-in-depth, but the branch is
    unreachable in practice."""


def _extract_bearer(request: Request) -> str | None:
    header = request.headers.get("authorization")
    if not header:
        return None
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


# --------------------------------------------------------------------------
# HttpService: the one object `create_app` needs from a composition root
# (`main.py` for a real deployment, the conformance adapter for the suite).
# Deliberately NOT `service.MitateDataService` -- that class's own
# `open_session` resolves a cell from an in-process `ControlPlane.cells`
# dict built at `provision_application` time (an in-memory SQLite
# composition, R-3's own "SQLite backend stays local-foundation-only"
# rule) has no notion of "look up this application's own PostgreSQL DSNs
# from the platform registry"; that resolution is this class' own job,
# parameterized by a `cell_factory` callable exactly like r2db-api's own
# composition root (`r2db_api.main.build_app`'s `_cell_factory`,
# independently arrived at here rather than shared code).
# --------------------------------------------------------------------------


class HttpService:
    """Composition-root-agnostic session/session-authority resolution for
    the HTTP surface: given a real `credential_store` (the WP-2
    `PostgresCredentialStore`, in a real deployment) and a `cell_factory`
    that builds a backend-bound `ApplicationCell` for a resolved
    `application_id`, this class authenticates a bearer token into a real
    `ApplicationRuntime`/`ApplicationDeveloper` session object -- the same
    session types `cell.py` already defines, unchanged.
    """

    def __init__(self, credential_store: Any, cell_factory: Callable[[str], Any], *, audit_router: Any = None) -> None:
        self._credentials = credential_store
        self._cell_factory = cell_factory
        # Phase 4 (design docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md D-3;
        # review m-1, folded into M-3, supervisor ruling 2026-09-03):
        # `AUTH_REQUIRED` is in `audit_dispatch.DURABLE_DENIAL_CODES` (D-3's
        # own inclusion table -- "認証系 2 コード相当"), but this peer only
        # ever constructs it HERE (`_CredentialMissing`, below) -- strictly
        # before any credential store is ever consulted (no bearer token
        # at all was presented). Without a router here, a durable-range
        # code declared in the vocabulary would have no emit site ever
        # reachable in this peer's real deployment topology at all.
        # `None` (the default) keeps every pre-Phase-4 caller of this
        # constructor (this repository's own tests, the in-process
        # conformance adapter, which has no HTTP surface at all) working
        # unchanged -- a missing router simply means this ONE denial class
        # stays undurable, exactly like every OTHER call site before this
        # WP wired a router in.
        self._audit_router = audit_router

    def authenticate(self, bearer_token: str | None, *, request_id: str | None = None) -> ApplicationRuntime:
        """Phase 6 WP-3 差し戻し 最終ラウンド (supervisor ruling 2026-09-04,
        裁定 1): this HTTP boundary never splits the presented bearer
        itself any more -- it passes `bearer_token` straight through to
        `self._credentials.authenticate` (`auth.CredentialStore`/
        `credential_store_postgres.PostgresCredentialStore`, whichever
        this service was composed with), which is the single choke point
        that calls `split_bearer_locator` exactly once. A malformed
        bearer is no longer distinguished HERE at all -- it reaches the
        store like any other credential and comes back as an ordinary,
        unattributed `AuthenticationError` (`AUTH_INVALID`), durably
        routed by the store's own pre-auth branch (mirrors r2db-api's
        own `http.py::authenticate`, which never pre-splits either)."""
        if bearer_token is None:
            if self._audit_router is not None:
                # Review m-1/M-3: no bearer token was presented at all --
                # there is no credential_id to record (unlike B-1's
                # concern, there is no client-CLAIMED id here either), so
                # `actor_id`/`target_id` are `None` and the coalescing key
                # collapses to `(None, "unknown", "authenticate",
                # "AUTH_REQUIRED")`, mirroring the pre-auth treatment B-1
                # already established for a present-but-wrong credential.
                self._audit_router.route_denial(
                    reason_code="AUTH_REQUIRED", event_class="authentication_denied", request_id=request_id,
                    application_id=None, actor_type="unknown", actor_id=None, role=None,
                    operation="authenticate", target_kind="credential", target_id=None,
                )
            raise _CredentialMissing()
        principal = self._credentials.authenticate(bearer_token, request_id=request_id)
        cell = self._cell_factory(principal.application_id)
        guard = self._credentials.assert_active
        if principal.role == Role.DEVELOPER:
            return ApplicationDeveloper(cell, principal, guard, request_id=request_id)
        return ApplicationRuntime(cell, principal, guard, request_id=request_id)


Handler = Callable[[Request], Awaitable[Response]]


def _endpoint(handler: Handler) -> Handler:
    async def wrapped(request: Request) -> Response:
        request_id = _request_id(request)
        try:
            return await handler(request)
        except _CredentialMissing:
            return _problem("AUTH_REQUIRED", "Authentication is required.", request_id=request_id)
        except _CredentialMalformed:
            return _problem("AUTH_INVALID", "Credential is not valid.", request_id=request_id)
        except FoundationError as exc:
            return _problem_for_exception(exc, request_id)
        except Exception:
            return _generic_service_unavailable(request_id)

    return wrapped


async def _http_exception_handler(request: Request, exc: StarletteHTTPException) -> Response:
    request_id = _request_id(request)
    code = "NOT_FOUND" if exc.status_code in (404, 405) else "VALIDATION_FAILED"
    return _problem(code, "The requested resource or method is not available.", request_id=request_id)


async def _unhandled_exception_handler(request: Request, exc: Exception) -> Response:
    return _generic_service_unavailable(_request_id(request))


def _authenticate(request: Request) -> ApplicationRuntime:
    # Review M-2 (major, supervisor ruling 2026-09-03, "完全案"): threads
    # this same request's own `request_id` (`_request_id`, already
    # generated by the byte-limiting ASGI middleware and returned as the
    # `x-request-id` response header) into the credential-store
    # authenticate call -- every call site below reaches `_request_id
    # (request)` independently too, for its own subsequent session
    # operation, so a single request's own durable rows (an `AUTH_
    # INVALID`/`AUTH_REQUIRED` denial here, or an `allow` row from the
    # operation that follows) all carry the identical value.
    service: HttpService = request.app.state.service
    return service.authenticate(_extract_bearer(request), request_id=_request_id(request))


# --------------------------------------------------------------------------
# field_type mapping (§2 of the design doc): contract `field_type` enum
# (string/integer/number/boolean/object/array) -> this peer's own field
# type vocabulary (`cell._FIELD_TYPE_VOCABULARY`: text/integer/real/
# boolean/json).
# --------------------------------------------------------------------------

_CONTRACT_FIELD_TYPE_TO_MITATEDB = {
    "string": "text",
    "integer": "integer",
    "number": "real",
    "boolean": "boolean",
    "object": "json",
    "array": "json",
    # Phase 6 WP-3 (design D-3, item (i)): the contract's 7th `field_type`
    # member -- physically the SAME `json` (TEXT) column `object`/`array`
    # already use; the declared-type REGISTRY (`cell.py`/`backend_*.py`,
    # `field_types.py`), never this map, is what recovers which of the
    # three a field actually is.
    "json": "json",
}

# `SchemaOperationRequest.operation`'s full contract enum. Only
# `create_entity`/`add_field` execute; every other member is a real,
# present denial (`CAPABILITY_UNSUPPORTED`) once this endpoint is mounted
# -- C-17's new present-denial form (design R-8 item 1), never
# `SurfaceAbsent` here (that claim belongs only to the in-process adapter,
# which genuinely has no schema-operations HTTP entry point at all).
_SCHEMA_OPERATIONS = {"create_entity", "add_field", "alter_field", "create_index", "drop_index", "drop_entity"}


def _predicate_to_filter(item: Any) -> Filter:
    _check_object_shape(item, _DEFINITIONS["Predicate"], label="where item")
    return Filter(item["field"], item["operator"], item.get("value"))


def _order_items(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        raise ValidationError("order_by must be an array")
    for item in raw:
        _check_object_shape(item, _DEFINITIONS["Order"], label="order_by item")
    return raw


# --------------------------------------------------------------------------
# Endpoints (spec/data-service-api.v1.json -> "endpoints").
# --------------------------------------------------------------------------


@_endpoint
async def get_capabilities(request: Request) -> Response:
    # M-9 (design §2): application authentication ONLY. This process holds
    # no control-credential store at all (R-4's own process-role
    # separation), so there is structurally no way to accept a control
    # credential here even as a co-hosting convenience.
    session = _authenticate(request)
    document = dict(session.capabilities(request_id=_request_id(request)))
    # Phase 8 WP-1a rework 1 (裁定 1, 監督裁定 2026-09-06): `request_bytes`
    # is `enforced` from `cell.py`'s own single-source declaration on BOTH
    # surfaces (the in-process structural estimate `ApplicationCell.
    # _limit_gate` runs is transport-independent) -- the former
    # enforcement-layer override that used to flip this key from
    # `unavailable` to `enforced` for the HTTP surface only is REMOVED in
    # this same commit (R-3: a meaningless, redundant re-declaration of
    # what the single source of truth already says, once that source
    # itself says `enforced`).
    #
    # `operation_depth` is now the SAME -- `cell.py`'s own single-source
    # declaration is `enforced` on BOTH surfaces too (see `cell.py::
    # ApplicationRuntime.capabilities()`'s own `limit_enforcement.
    # operation_depth` comment for why the WP-1a report's original
    # "in-process has no request dict" premise was factually wrong:
    # `_check_operation_depth` genuinely runs, in-process included, on
    # every request shape `_limit_gate`'s own callers build -- `insert`'s
    # own `{"collection": ..., "values": ...}` is a real request dict, not
    # an absent one). This wire layer therefore no longer overrides
    # `operation_depth` either, for the identical reason it stopped
    # overriding `request_bytes` above.
    return JSONResponse(document, status_code=200)


@_endpoint
async def post_query(request: Request) -> Response:
    session = _authenticate(request)
    entity = request.path_params["entity"]
    body = await _read_json_object(request)
    _check_object_shape(body, _SCHEMAS["QueryRequest"], label="QueryRequest")
    _deny_first_provisional_field(body, _PROVISIONAL_UNSUPPORTED_QUERY_REQUEST_FIELDS)

    select = body["select"]
    where_raw = body.get("where")
    filters = [_predicate_to_filter(item) for item in where_raw] if where_raw is not None else None

    order_by_raw = body.get("order_by")
    order_by = _order_items(order_by_raw) if order_by_raw is not None else None

    page = body.get("page")
    page_size = None
    if page is not None:
        _check_object_shape(page, _DEFINITIONS["Page"], label="page")
        if "cursor" in page:
            # WP-3 design decision (reported to the requester): `page.
            # cursor` has no implementation on this peer -- there is no
            # opaque-cursor pagination state anywhere in `cell.py`/either
            # backend. Presenting one is refused deterministically and
            # classified `CAPABILITY_UNSUPPORTED`: cursor-based pagination
            # is a real, optional target shape this contract defines
            # (`QueryResult.next_page`) that this peer simply does not
            # execute, matching `capability_status.rules`' own "optional
            # target operations ... must fail with CAPABILITY_UNSUPPORTED"
            # -- not a malformed request (`VALIDATION_FAILED`), and not a
            # structural absence (the field IS a real, accepted part of
            # this endpoint's own request shape; it is refused only once
            # actually presented, after shape/auth, before execution).
            # Left to a future capability-envelope decision whether to
            # implement cursor pagination at all (design v1.2 §7 ledger).
            raise CapabilityError("page.cursor is not supported by this peer")
        if "size" in page:
            page_size = page["size"]

    rows = session.read(entity, fields=list(select), filters=filters, order_by=order_by, limit=page_size,
                        request_id=_request_id(request))
    return JSONResponse({"items": rows, "next_page": None}, status_code=200)


def _mutation_item(entity: str, raw: Mapping[str, Any]) -> dict[str, Any]:
    _check_object_shape(raw, _DEFINITIONS["Mutation"], label="mutation operation")
    # Phase 9 WP-3b rework (M-6): `values` is unconditionally present here
    # (`raw.get("values") or {}`, never conditional on `"values" in raw`)
    # -- this is this peer's own INTERNAL execution-item vocabulary
    # (`ApplicationCell.transact`'s `_TRANSACT_*_KEYS`/`_plan_operation`
    # consume it via `.get("values")` either way, so an absent key would
    # have executed identically), not something the plan digest reads any
    # more (WP-3b closure, H-2): `_mutation_digest_item` immediately below
    # builds the digest's own per-operation object straight from `raw`,
    # BEFORE this forcing, so an omitted `values` and an explicit `values:
    # {}` stay two different digested requests regardless of what this
    # execution item itself always carries.
    item: dict[str, Any] = {"type": raw["operation"], "collection": entity, "values": dict(raw.get("values") or {})}
    if "where" in raw:
        item["filters"] = [_predicate_to_filter(w) for w in raw["where"]]
    if "expected_revision" in raw:
        item["expected_revision"] = raw["expected_revision"]
    if "unique_key" in raw:
        item["unique_key"] = raw["unique_key"]
    if "destructive" in raw:
        item["destructive"] = raw["destructive"]
    if "confirmation" in raw:
        # Contract field name `confirmation` -> this peer's own
        # transact()/delete() keyword `confirm` (pre-existing naming,
        # unchanged by this WP).
        item["confirm"] = raw["confirmation"]
    return item


def _mutation_digest_item(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Phase 9 WP-3b closure (追補 2, H-2): the plan digest's own per-
    operation object -- unlike `_mutation_item` above (this peer's
    INTERNAL execution vocabulary: `type`/`collection`/`filters`/
    `confirm`, `values` forced present unconditionally), this is the
    contract-level `Mutation`/`ScopedMutation` object AS THE CLIENT
    PRESENTED IT: `raw` has already passed `_check_object_shape` against
    that exact schema (`_mutation_item`'s own first line, called
    immediately before or after this one at every call site), so it
    carries only contract-named keys already -- a plain shallow copy, no
    key renamed, no optional backfilled, no key forced present. `values`
    in particular stays ABSENT here when the request omitted it (WP-3b
    review A-3.3: an omitting request and a `values: {}` request must NOT
    collide on one plan token -- the exact defect class M-2 already closed
    for schema `field_constraints`). `where`'s own predicate objects stay
    plain dicts (never converted to a `Filter` dataclass, unlike `_
    mutation_item`'s `filters`) -- JSON-native by construction, so no
    `default=` hook is ever needed feeding this into `cell.py::normalize_
    request_for_plan` (G-4)."""
    return dict(raw)


def _mutation_outcome(items: list[dict[str, Any]], results: list[Any], *,
                      dry_run: bool = False) -> tuple[int, bool, str | None]:
    """Phase 9 WP-3b: shared by `post_mutate`/`post_cross_entity_mutate`
    -- `affected` exactly as both computed it before this WP (`zip`
    truncates to `len(items)`, so this is unaffected by `cell.py::
    ApplicationCell.transact`'s own dry-run envelope, appended -- when
    present -- one entry PAST the last real per-item result). `committed`/
    `plan` are read off that trailing envelope (a dict `transact()` itself
    never returns for a real, non-dry-run request, design D-4 (4)).

    Rework (Minor m-4, review): `committed`'s own default is `not
    dry_run` -- matching the in-process port's own identical `envelope.
    get("committed", not dry_run)` (`conformance/conformance_adapter_
    mitatedb.py::_mutation_result_to_mapping`) -- rather than the
    previous unconditional `True`. `transact()` always appends the
    envelope for a dry run (so `envelope.get("committed", ...)` finds a
    real `False` there in practice either way) and never for a real
    call, where `results[-1]` is instead a real per-item result dict
    (e.g. `{"deleted": n}`) that happens to carry no `committed` key --
    this default is only ever consulted in that second case, and `dry_run`
    is always `False` there too, so the two defaults agree in every
    reachable case today; aligning them removes a latent trap for
    whichever future change makes them diverge."""
    affected = 0
    for item, result in zip(items, results):
        if item["type"] == "insert":
            affected += 1
        elif isinstance(result, dict):
            affected += result.get("updated", result.get("deleted", 0))
    envelope = results[-1] if results and isinstance(results[-1], dict) else {}
    return affected, envelope.get("committed", not dry_run), envelope.get("plan")


@_endpoint
async def post_mutate(request: Request) -> Response:
    session = _authenticate(request)
    entity = request.path_params["entity"]
    body = await _read_json_object(request)
    # `_check_object_shape` against `MutationRequest` (`additionalProperties:
    # false`, properties: operations/transaction/idempotency_key) is what
    # makes a smuggled body `entity` field an unknown-field rejection
    # (`endpoints.mutate.semantics`: "The body carries no entity field; a
    # body entity field is rejected as an unknown field.") -- `entity`
    # is simply not in this schema's own property set.
    _check_object_shape(body, _SCHEMAS["MutationRequest"], label="MutationRequest")
    if "idempotency_key" in body:
        _deny_provisional_field("idempotency_key")
    _deny_first_provisional_field(body, _PROVISIONAL_UNSUPPORTED_MUTATION_REQUEST_FIELDS)
    # `transaction_raw` (rework, G-1): the digest must commit to the
    # request AS PRESENTED -- an omitted `transaction` and one explicitly
    # spelling out the deployed default (`"atomic"`) are two DIFFERENT
    # requests (contract `structured_operations.dry_run.plan`: "a real
    # request differing from the dry run in any of them is a different
    # request"), so `session.transact` below is given the RAW,
    # unbackfilled value -- `None` when the client omitted the key --
    # never this method's own resolved `transaction` (backfilled to
    # `"atomic"` purely for THIS validation step, unchanged from before
    # this rework). C-22 (10)'s own MitateDB-api-http leg is what caught
    # this: presenting a dry run's plan back with `transaction: "atomic"`
    # newly ADDED must be refused, and it silently was not while `session.
    # transact` received the backfilled value on BOTH the dry run and the
    # apply alike (both always "atomic", so nothing ever differed).
    transaction_raw = body.get("transaction")
    transaction = transaction_raw if transaction_raw is not None else "atomic"
    if transaction == "best_effort":
        # `best_effort_transactions: unavailable` (cell.py's own
        # declaration, unchanged) -- `transact()` has no partial-result
        # execution mode at all; presenting `best_effort` is a real,
        # optional-target-shape refusal, not a malformed request.
        raise CapabilityError("best_effort transactions are not supported by this peer")
    if transaction != "atomic":
        raise ValidationError("transaction mode is not supported")

    operations = body.get("operations")
    if not isinstance(operations, list) or not operations:
        raise ValidationError("operations must be a non-empty array")
    items = [_mutation_item(entity, op) for op in operations]
    # `digest_items` (WP-3b closure, H-2): the SAME `operations` list,
    # built into the CONTRACT-shaped digest object instead of the
    # execution item `_mutation_item` builds -- see `_mutation_digest_
    # item`'s own docstring.
    digest_items = [_mutation_digest_item(op) for op in operations]

    # Phase 9 WP-3b (design D-4): `dry_run`/`plan` now reach `transact()`
    # for real -- both defaulted to their own byte-compatible absence
    # (`False`/`None`) above, so an unchanged (pre-WP-3b) caller's own
    # request is unaffected.
    results = session.transact(
        items, request_id=_request_id(request),
        dry_run=body.get("dry_run", False), plan=body.get("plan"),
        # Phase 9 WP-3b rework (M-4/G-1): `transaction_raw` (NOT the
        # backfilled `transaction` above) now reaches `session.transact`
        # -- `None` when the request omitted the key, `"atomic"` only
        # when the request actually named it -- so the digest commits to
        # what the request presented, not this endpoint's own resolved
        # default. `post_cross_entity_mutate` below has no `transaction`
        # field on `ScopedMutationRequest` at all, so it never passes one.
        transaction=transaction_raw,
        # `entity`/`digest_operations` (WP-3b closure, H-1/H-2): `entity`
        # is this endpoint's own URL path segment -- `MutationRequest` has
        # no `entity` property of its own (it is implicit from the path),
        # so it is hoisted to the digest object's own TOP level here
        # (`cell.py::ApplicationCell.transact`'s own `entity` keyword) --
        # an entity substitution between a dry run and its apply must fail
        # closed (H-1). `digest_operations=digest_items` supplies the
        # CONTRACT-shaped per-operation objects built above, so `cell.py`
        # never falls back to reconstructing them from `items`' own
        # internal execution vocabulary.
        entity=entity, digest_operations=digest_items,
    )
    affected, committed, plan_token = _mutation_outcome(items, results, dry_run=body.get("dry_run", False))
    response: dict[str, Any] = {"committed": committed, "affected": affected}
    if plan_token is not None:
        response["plan"] = plan_token
    return JSONResponse(response, status_code=200)


def _scoped_mutation_item(raw: Mapping[str, Any]) -> dict[str, Any]:
    """P35 WP-2 (R-3, design docs/design/PHASE35_CROSS_ENTITY_AND_
    CONTRACT_130_V1.md §2): the cross-entity counterpart of
    `_mutation_item` above -- reads `entity` from EACH operation itself
    (contract `ScopedMutation`, `Mutation` + a required `entity`) instead
    of a single URL path segment shared by the whole request. Otherwise
    identical field-by-field mapping onto `ApplicationCell.transact`'s own
    operation-dict vocabulary (`_TRANSACT_INSERT_KEYS`/`_TRANSACT_UPDATE_
    KEYS`/`_TRANSACT_DELETE_KEYS` in `cell.py`) -- an unsupported key
    (`expected_revision`/`unique_key`) still rides along here exactly as
    `_mutation_item` lets it, so `transact()`'s own single choke refuses
    it with `CAPABILITY_UNSUPPORTED`, not a second copy of that refusal
    at this layer."""
    _check_object_shape(raw, _DEFINITIONS["ScopedMutation"], label="cross-entity mutation operation")
    # Phase 9 WP-3b rework (M-6/G-1): same reasoning as `_mutation_item`'s
    # own identical comment -- `values` always present.
    item: dict[str, Any] = {"type": raw["operation"], "collection": raw["entity"], "values": dict(raw.get("values") or {})}
    if "where" in raw:
        item["filters"] = [_predicate_to_filter(w) for w in raw["where"]]
    if "expected_revision" in raw:
        item["expected_revision"] = raw["expected_revision"]
    if "unique_key" in raw:
        item["unique_key"] = raw["unique_key"]
    if "destructive" in raw:
        item["destructive"] = raw["destructive"]
    if "confirmation" in raw:
        item["confirm"] = raw["confirmation"]
    return item


@_endpoint
async def post_cross_entity_mutate(request: Request) -> Response:
    """P35 WP-2 (R-3/R-5): `cross_entity_mutation` is now `enabled`
    (`cell.py::ApplicationRuntime.capabilities()`, same commit) -- this
    endpoint dispatches for real instead of raising an unconditional
    `CapabilityError`. `session.transact` is the SAME two-pass entry
    point (`cell.py::ApplicationCell.transact`) the per-entity
    `POST /v1/data/{entity}/mutations` endpoint already uses; the only
    difference at this layer is where each operation's own `collection`
    comes from (per-operation `entity`, via `_scoped_mutation_item`,
    rather than one shared URL path segment).

    `idempotency_key` is refused exactly like `post_mutate` does (P35-D3)
    -- `ScopedMutationRequest` declares the same optional field, this
    peer implements it nowhere. There is no `transaction` field on
    `ScopedMutationRequest` at all (unlike `MutationRequest`) -- a
    cross-entity batch has no `best_effort` mode to refuse here.

    Response body is `{"committed", "affected"}` ONLY -- no
    `assigned_addresses` (design M-6: this peer declares
    `row_addressability`/`application_catalog` unavailable, so it has no
    address-field vocabulary it could honestly attach to a response;
    matches `post_mutate`'s own response shape exactly).
    """
    session = _authenticate(request)
    body = await _read_json_object(request)
    _check_object_shape(body, _SCHEMAS["ScopedMutationRequest"], label="ScopedMutationRequest")
    if "idempotency_key" in body:
        _deny_provisional_field("idempotency_key")
    _deny_first_provisional_field(body, _PROVISIONAL_UNSUPPORTED_MUTATION_REQUEST_FIELDS)

    operations = body.get("operations")
    if not isinstance(operations, list) or not operations:
        raise ValidationError("operations must be a non-empty array")
    items = [_scoped_mutation_item(op) for op in operations]
    # `digest_items` (WP-3b closure, H-1/H-2): built straight from `raw`
    # per operation -- `ScopedMutation` already names `entity` as one of
    # its own contract properties, so each digest item carries its own
    # target entity without this endpoint needing a top-level `entity`
    # keyword the way `post_mutate` above does (`_mutation_digest_item`
    # is the SAME helper `post_mutate` uses -- it does no `Mutation`-vs-
    # `ScopedMutation`-specific work of its own, just a shallow copy of
    # whatever contract-shaped keys `raw` already carries).
    digest_items = [_mutation_digest_item(op) for op in operations]

    results = session.transact(
        items, request_id=_request_id(request),
        dry_run=body.get("dry_run", False), plan=body.get("plan"),
        digest_operations=digest_items,
    )
    affected, committed, plan_token = _mutation_outcome(items, results, dry_run=body.get("dry_run", False))
    response: dict[str, Any] = {"committed": committed, "affected": affected}
    if plan_token is not None:
        response["plan"] = plan_token
    return JSONResponse(response, status_code=200)


@_endpoint
async def get_catalog(request: Request) -> Response:
    # Phase 6 WP-3 (design D-3): `application_catalog: enabled`
    # (`cell.py`'s own declaration, same commit) -- `session.catalog()`
    # returns the SAME 3-key `EntityDescriptor` shape (`entity`/`fields`/
    # `field_types`) for every entity, backed by the declared-type
    # registry.
    session = _authenticate(request)
    entities = session.catalog(request_id=_request_id(request))
    # `CatalogDocument.application_scope` is required alongside `entities`
    # -- every other endpoint's own response already carries this same
    # value (`get_capabilities`'s `application_scope` key, `cell.py::
    # ApplicationRuntime.capabilities()`), read from the SAME `Application
    # Runtime.application_id` property, never re-derived.
    return JSONResponse({"application_scope": session.principal.application_id, "entities": entities}, status_code=200)


@_endpoint
async def post_schema(request: Request) -> Response:
    session = _authenticate(request)
    body = await _read_json_object(request)
    _check_object_shape(body, _SCHEMAS["SchemaOperationRequest"], label="SchemaOperationRequest")
    _deny_first_provisional_field(body, _PROVISIONAL_UNSUPPORTED_SCHEMA_OPERATION_REQUEST_FIELDS)
    # Phase 5 WP-3 (design docs/design/PHASE5_CONTRACT_150_AND_LIMIT_RANGE_
    # V1.md D-1, (d') -- a request body carrying a key literally named
    # "operation" would otherwise be indistinguishable, to the generalized
    # audit-vocabulary scanner, from an audit-field `operation` local
    # variable; renamed (never behavior -- the `_SCHEMA_OPERATIONS` gate
    # below is unchanged) so this local variable never collides with that
    # name.
    schema_operation = body.get("operation")
    if schema_operation not in _SCHEMA_OPERATIONS:
        raise ValidationError("unsupported schema operation")
    entity = body["entity"]

    # Contract `endpoints.schema.auth`: "developer" -- the WHOLE endpoint
    # requires developer authority, not only the two operations this peer
    # executes. Checked once, uniformly, before dispatching on `operation`
    # -- a runtime credential presenting ANY schema operation (including
    # one of the present-denial operations below) gets `FORBIDDEN`, never
    # `CAPABILITY_UNSUPPORTED` (which would incorrectly suggest the
    # operation itself, rather than this credential's own role, is what
    # is refused). `isinstance` (not a bare method call) because
    # `ApplicationRuntime` has no `create_entity`/`add_field` method at
    # all -- calling one directly on a runtime session would raise
    # `AttributeError`, not this peer's own `AuthorizationError`.
    if not isinstance(session, ApplicationDeveloper):
        raise AuthorizationError("developer authority required")

    # `digest_extra` (WP-3b closure, H-3 (b)): `destructive`/`confirmation`/
    # `revision`/`index`/`unique` are real `SchemaOperationRequest`
    # properties (`_check_object_shape` above already lets them through)
    # that `create_entity`/`add_field`/`alter_field` below never read --
    # they carry no meaning for any of the three real operations this
    # dispatcher executes today -- but the contract still requires the
    # plan token to commit to "every other field" the request presented
    # (structured_operations.dry_run.plan). Forwarded to `cell.py`
    # verbatim, unread and unvalidated here beyond the shape check above;
    # whichever of the 5 the request did not carry stays entirely absent
    # (G-1's own "省略された optional は key ごと無し" -- never backfilled
    # to `None`/a default).
    digest_extra = {key: body[key] for key in ("destructive", "confirmation", "revision", "index", "unique")
                    if key in body}

    if schema_operation == "create_entity":
        # M-3 (independent review): `SchemaOperationRequest.field_type` is
        # a valid top-level property of this request shape (the contract
        # gives it no per-operation `if`/`then` narrowing that would
        # forbid it on `create_entity`), so `_check_object_shape` above
        # accepts a request carrying it here. Silently ignoring it would
        # accept a request this peer cannot honor as if it had succeeded:
        # a caller naming `field_type: "integer"` alongside `fields:
        # ["rank"]` would see `committed: true` yet `rank` is actually
        # created as `text` (P3-D1's own untyped-equivalent mapping,
        # below) -- confirmed empirically before this fix, a later insert
        # of an integer value into `rank` failed with `VALIDATION_FAILED`
        # despite the caller having explicitly declared its intended type
        # up front and been told the operation committed. `field_type` has
        # no per-field association on `create_entity` at all (only a
        # single, request-level slot -- see the comment below), so there
        # is no way to honor it here; refusing it explicitly, before any
        # entity is created, is the same "reject an unread capability-
        # shaped key before execution" discipline `cell.py`'s own
        # `_TRANSACT_INSERT_KEYS` already applies to `transact()`.
        if "field_type" in body:
            raise CapabilityError("create_entity cannot honor a request-level field_type for its fields array")
        fields_raw = body.get("fields")
        field_types_raw = body.get("field_types")
        # Phase 6 WP-3 (design D-3, decision (iv)): `field_types` is an
        # OPTIONAL, PARTIAL map (field name -> one of the contract's 7
        # `field_type` words) -- never required, never honored silently
        # when malformed (the 3 invalid cases below are all
        # `VALIDATION_FAILED`, matching `EntityDescriptor.field_types`'s
        # own description: "none of the three is silently ignored").
        if field_types_raw is not None and fields_raw is None:
            # (c) field_types sent without fields.
            raise ValidationError("field_types requires fields to be present")
        # P3-D1 (design §0 exception, WP-1): the contract's `fields` on
        # `create_entity` is a bare array of NAMES (no per-field
        # `field_type` slot on `fields` itself) -- `SchemaOperationRequest.
        # field_type` (singular, scalar) is a single, request-level value
        # with no per-field association, refused above; `field_types`
        # (plural, this WP) is the per-field carrier instead.
        if fields_raw is not None:
            if not isinstance(fields_raw, list) or not fields_raw:
                raise ValidationError("fields must be a non-empty array")
            # Defensive, pre-execution shape check: a non-string (or
            # unhashable) element here would otherwise raise a raw
            # `TypeError` building the dict below, escaping as an
            # UNCLASSIFIED-looking `SERVICE_UNAVAILABLE` instead of a
            # proper `VALIDATION_FAILED` -- and, more importantly, doing
            # so BEFORE `session.create_entity` is ever called, so no
            # entity is created either way (this check exists for correct
            # classification, not for structural-integrity safety, which
            # already held without it).
            for item in fields_raw:
                if not isinstance(item, str):
                    raise ValidationError("each field name must be a string")
            field_types_map: dict[str, str] = {}
            if field_types_raw is not None:
                if not isinstance(field_types_raw, dict):
                    raise ValidationError("field_types must be an object")
                for name, declared_type in field_types_raw.items():
                    if name not in fields_raw:
                        # (a) field_types names a field not in fields.
                        raise ValidationError(f"field_types names {name!r}, which is not in fields")
                    if declared_type not in _CONTRACT_FIELD_TYPE_TO_MITATEDB:
                        # (b) field_types value outside the vocabulary.
                        raise ValidationError(f"field_types[{name!r}] is not a supported field_type")
                    field_types_map[name] = declared_type
            # Decision (ii): a field named in `fields` but not in
            # `field_types` (or every field, when `field_types` is absent
            # entirely) defaults to `json` -- the MitateDB behaviour
            # change (α): the physical, DDL-facing type for such a field
            # is now `json` (`_CONTRACT_FIELD_TYPE_TO_MITATEDB["json"]`),
            # not the pre-WP-3 hardcoded `text`.
            contract_field_types = {name: field_types_map.get(name, "json") for name in fields_raw}
            fields = {name: _CONTRACT_FIELD_TYPE_TO_MITATEDB[contract_field_types[name]] for name in fields_raw}
        else:
            fields = None
            contract_field_types = None
        # Phase 9 WP-3a (design docs/design/
        # PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md D-2 (1)):
        # `field_constraints` is passed through verbatim -- `cell.py::
        # ApplicationCell.create_collection`/`.create_entity` do the real
        # validation (partial-vs-`fields` cross-check, `enum` member/type/
        # limit checks) and resolution to a total map; this HTTP layer
        # does not re-validate its shape beyond `_check_object_shape`'s
        # own top-level key check above.
        field_constraints = body.get("field_constraints")
        # Phase 9 WP-3b (design D-4): `create_entity` now returns
        # `{"revision", "descriptor", "committed"}` for real (`cell.py::
        # ApplicationCell.create_collection`) -- read DIRECTLY off that
        # same-transaction result rather than the separate, uncounted
        # `_post_schema_revision()` readback the two branches below used
        # to need (m-2/裁定 3, pre-WP-3b): a dry run rolls the write back
        # before this call even returns, so a SEPARATE post-call read
        # here would race a concurrent writer and could report a revision
        # this dry run's own `plan` was never computed against.
        # Phase 9 WP-3b rework (M-2/G-1): `field_types=` below is the RAW,
        # PARTIAL declaration the caller actually presented (`field_types_
        # map`, only the names `field_types_raw` itself named -- `None`
        # when the request omitted `field_types` entirely), never `
        # contract_field_types` (the TOTAL, `json`-backfilled map decision
        # (ii) above builds so `fields`'s own foundation-type choice below
        # has a value for every name). `cell.py::ApplicationCell.create_
        # collection` backfills the SAME missing names to `json` on its
        # own (via `FOUNDATION_TYPE_TO_CONTRACT_TYPE`, deriving it from
        # the foundation type `fields` already carries for that name) --
        # so the entity this call creates is byte-identical either way;
        # only the `plan` DIGEST changes, from committing to the resolved
        # total map (WP-3b review M-2: a request omitting `field_types`
        # and one explicitly spelling out the same defaults used to
        # collide on one token) to committing to what the request itself
        # named.
        # `operation` NOT forwarded here (WP-3b closure, H-4): `cell.py::
        # ApplicationCell.create_collection`'s own keyword-only PARAMETER
        # default (`operation="create_entity"`) already supplies the
        # correct digest value for this branch -- this call is only ever
        # reached when `schema_operation == "create_entity"` (the `if`
        # above), so the two are provably always equal; a genuine
        # variable forward from `schema_operation` here would itself be a
        # NEW `test_audit_query.py` scanner violation (a `operation=`
        # keyword call site whose value's own Name id is not literally
        # "operation" is never a recognized safe forward, regardless of
        # what it holds) -- the SAME shape of problem `_NON_AUDIT_
        # OPERATION_LITERALS` used to work around differently, which H-4
        # asks not to reintroduce.
        result = session.create_entity(
            entity, fields, field_types=(field_types_map if field_types_raw is not None else None),
            field_constraints=field_constraints,
            dry_run=body.get("dry_run", False), plan=body.get("plan"),
            request_id=_request_id(request), digest_extra=digest_extra)
        response: dict[str, Any] = {"committed": result["committed"], "revision": result["revision"]}
        if result.get("descriptor") is not None:
            response["descriptor"] = result["descriptor"]
        if result.get("plan") is not None:
            response["plan"] = result["plan"]
        return JSONResponse(response, status_code=200)

    if schema_operation == "add_field":
        field = body.get("field")
        if not isinstance(field, str):
            raise ValidationError("add_field requires field")
        field_type_raw = body.get("field_type")
        # WP-3a rework 3 (real, measured bug): `SchemaOperationRequest.
        # field_type` is NOT globally `required` (only `operation`/`entity`
        # are, `contract/data-service-api.v1.json`'s own `schemas.
        # SchemaOperationRequest.required`), and contract `field_types`'s
        # own description states the general rule this peer's
        # `create_entity` branch above already honors for `fields`/`field_
        # types`: "A field created without a declared type has type json
        # -- this names an existing default rather than introducing a new
        # one." `add_field`'s own singular `field_type` is that identical
        # rule applied to the one field it adds -- an omitted `field_type`
        # must default to `json`, not be refused. This peer used to refuse
        # every field_type-omitting `add_field` with a bare, details-less
        # `VALIDATION_FAILED` ("field and a supported field_type"), a real
        # divergence from `r2db-api` (`postgres.py`'s own comment: "`add_
        # field` with no `field_type` ... keep[s] the pre-CCR-13 default,
        # JSONB") and from this peer's OWN in-process surface (`cell.py::
        # ApplicationDeveloper.add_field`'s `field_type` keyword already
        # accepts `None`-derived `"json"` via the conformance port's own
        # `foundation_type = ... if field_type is not None else "json"`
        # translation). A field_type that IS present and outside the
        # 7-word vocabulary is still refused, unchanged.
        if field_type_raw is not None and field_type_raw not in _CONTRACT_FIELD_TYPE_TO_MITATEDB:
            raise ValidationError("field_type is not a supported field_type")
        field_type = field_type_raw if field_type_raw is not None else "json"
        # Phase 9 WP-3a (design D-2 (1)): `enum`/`nullable` passed through
        # verbatim -- `cell.py::ApplicationCell.add_field` does the real
        # validation, same reasoning as `create_entity`'s own identical
        # comment above.
        # Phase 9 WP-3b: same reasoning as `create_entity` above -- read
        # `revision`/`descriptor`/`committed`/`plan` directly off this
        # same-transaction result, not a separate post-call readback.
        result = session.add_field(
            entity, field, _CONTRACT_FIELD_TYPE_TO_MITATEDB[field_type],
            # `contract_type=field_type_raw` (WP-3b closure, H-3 (a)): the
            # RAW value the request actually carried -- `None` when
            # `field_type` was omitted -- NOT `field_type` (this method's
            # own local, backfilled to `"json"` two lines above for
            # EXECUTION purposes only). `cell.py::ApplicationCell.add_
            # field`'s own digest now reads straight off this argument,
            # present in the digest only when not `None`; passing the
            # backfilled value here would make an omitting request and one
            # explicitly spelling out `field_type: "json"` collide on one
            # plan token (reproduced: `audit_probe_wp3b.py` P-B).
            contract_type=field_type_raw, enum=body.get("enum"), nullable=body.get("nullable"),
            dry_run=body.get("dry_run", False), plan=body.get("plan"),
            request_id=_request_id(request), digest_extra=digest_extra)
        response = {"committed": result["committed"], "revision": result["revision"]}
        if result.get("descriptor") is not None:
            response["descriptor"] = result["descriptor"]
        if result.get("plan") is not None:
            response["plan"] = result["plan"]
        return JSONResponse(response, status_code=200)

    if schema_operation == "alter_field":
        # Phase 9 WP-3a (design D-2 (5)/(6)): present-denial (design R-8
        # item 1, C-17) removed for THIS operation -- `alter_field` is now
        # a real, executed request. `create_index`/`drop_index`/
        # `drop_entity` still fall through to the present-denial `raise`
        # below, unchanged by this WP.
        field = body.get("field")
        if not isinstance(field, str):
            raise ValidationError("alter_field requires field")
        # Code review §2 A / 監督裁定 A (2026-09-07): `body.get("enum",
        # UNCHANGED)` -- NOT a plain `body.get("enum")` -- is the one
        # place on the wire this distinction can still be made: `dict.
        # get(key, default)` returns `default` ONLY when `key` is absent
        # from `body`, so an omitted `enum` reaches `session.alter_field`
        # as the `UNCHANGED` sentinel (leaves the field's `enum` as it
        # is) while a present `"enum": null` reaches it as a real `None`
        # (clears it) -- the contract's own `SchemaOperationRequest.enum`
        # is already `["array", "null"]` in this WP's own packaged
        # contract copy, so `_check_object_shape` above lets a literal
        # `"enum": null` through the shape layer, reaching this line as
        # the real `None` that means "clear it".
        result = session.alter_field(
            entity, field, enum=body.get("enum", UNCHANGED), nullable=body.get("nullable"),
            field_type=body.get("field_type"), dry_run=body.get("dry_run", False), plan=body.get("plan"),
            request_id=_request_id(request), digest_extra=digest_extra)
        response = {"committed": result["committed"], "revision": result["revision"]}
        if result.get("descriptor") is not None:
            response["descriptor"] = result["descriptor"]
        if result.get("plan") is not None:
            response["plan"] = result["plan"]
        return JSONResponse(response, status_code=200)

    # C-17 present-denial form (design R-8 item 1): `create_index`/
    # `drop_index`/`drop_entity` are all real, contract-shaped requests
    # this real dispatcher receives and refuses -- never a structural
    # absence on this composition, since the entry point genuinely exists
    # and executes for `create_entity`/`add_field`/`alter_field` above.
    raise CapabilityError(f"schema operation {schema_operation!r} is not supported by this peer")


@_endpoint
async def post_audit_query(request: Request) -> Response:
    # `audit_query: unavailable` (cell.py's own declaration, unchanged this
    # WP) -- authenticate with the same application-credential path as
    # every other endpoint (fail closed on missing/invalid credentials
    # first), but never execute: the contract requires control/audit
    # authority for this endpoint and this process holds no control-
    # credential store at all (R-4's own process-role separation).
    _authenticate(request)
    raise CapabilityError("audit evidence query requires control/audit authority this peer does not expose here")


# --------------------------------------------------------------------------
# App assembly.
# --------------------------------------------------------------------------

_ROUTES = [
    Route("/v1/capabilities", get_capabilities, methods=["GET"]),
    Route("/v1/data/{entity}/query", post_query, methods=["POST"]),
    Route("/v1/data/{entity}/mutations", post_mutate, methods=["POST"]),
    # Fixed 3-segment path, distinct from the 4-segment `/v1/data/{entity}/
    # mutations` above at the routing level regardless of declaration
    # order -- mirrors r2db_api.http's identical routing-collision note.
    Route("/v1/data/mutations", post_cross_entity_mutate, methods=["POST"]),
    Route("/v1/catalog", get_catalog, methods=["GET"]),
    Route("/v1/schema/operations", post_schema, methods=["POST"]),
    Route("/v1/audit/query", post_audit_query, methods=["POST"]),
]


def create_app(service: HttpService, *, request_bytes_limit: int, lifespan: Any = None) -> ASGIApp:
    """Build the ASGI application exposing `service` over the contract's
    HTTP surface. The returned callable is `RequestByteBoundMiddleware`
    wrapping a Starlette application, so SI-08's request-byte bound is
    enforced before any Starlette routing or body parsing runs.
    """
    app = Starlette(
        routes=_ROUTES,
        exception_handlers={
            StarletteHTTPException: _http_exception_handler,
            Exception: _unhandled_exception_handler,
        },
        lifespan=lifespan,
    )
    app.state.service = service
    return RequestByteBoundMiddleware(app, request_bytes_limit=request_bytes_limit)
