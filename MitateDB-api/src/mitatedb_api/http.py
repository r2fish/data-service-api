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
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping

from starlette.applications import Starlette
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .auth import Role
from .cell import ApplicationDeveloper, ApplicationRuntime, Filter
from .errors import (AuditSinkUnavailable, AuthenticationError,
                     AuthorizationError, AuthorizationStateUnavailable,
                     CapabilityError, ConflictError,
                     DestructiveConfirmationRequired, FoundationError,
                     NotFoundError, ResourceLimitError,
                     StorageConfigurationError, ValidationError)

PROBLEM_CONTENT_TYPE = "application/problem+json"

_CONTRACT_PATH = Path(__file__).resolve().parents[3] / "spec" / "data-service-api.v1.json"
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
# SCOPE_MISMATCH, PRECONDITION_FAILED, ATOMICITY_FAILED, IDENTIFIER_INVALID
# -- `auth.py`/`credential_store_postgres.py` fold "revoked"/"disabled"
# into a single `AuthenticationError` -> AUTH_INVALID, and `identifiers.py`
# raises the same `ValidationError` -> VALIDATION_FAILED for a malformed
# identifier as for any other malformed shape); that is a pre-existing
# fact about this peer's own error vocabulary, not something WP-3 narrows,
# and is reported to the requester as a known divergence (not a status
# mismatch -- there is nothing to compare a peer never emits).
_STATUS_BY_CODE: dict[str, int] = {
    "AUTH_REQUIRED": 401,
    "AUTH_INVALID": 401,
    "AUTH_STATE_UNAVAILABLE": 503,
    "FORBIDDEN": 403,
    "VALIDATION_FAILED": 400,
    "CAPABILITY_UNSUPPORTED": 400,
    "NOT_FOUND": 404,
    "CONFLICT": 409,
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
    message = {
        "AUTH_STATE_UNAVAILABLE": "Authorization state is unavailable.",
        "SERVICE_UNAVAILABLE": "The service is temporarily unavailable.",
        "AUTH_INVALID": "Credential is not valid.",
        "FORBIDDEN": "This operation is not permitted for this credential.",
        "CAPABILITY_UNSUPPORTED": "This capability is not supported.",
        "VALIDATION_FAILED": "The request failed validation.",
        "LIMIT_EXCEEDED": "The request exceeds a configured resource limit.",
        "DESTRUCTIVE_CONFIRMATION_REQUIRED": "This destructive operation requires the current confirmation phrase.",
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
    """A bearer token was presented but does not have this peer's own
    `<credential_id>.<secret>` shape -- structurally cannot be valid, so
    this is classified `AUTH_INVALID` (a credential WAS presented) rather
    than `AUTH_REQUIRED` (no credential was presented at all)."""


def _extract_bearer(request: Request) -> str | None:
    header = request.headers.get("authorization")
    if not header:
        return None
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def _split_bearer(token: str) -> tuple[str, str]:
    if "." not in token:
        raise _CredentialMalformed()
    credential_id, _, secret = token.partition(".")
    if not credential_id or not secret:
        raise _CredentialMalformed()
    return credential_id, secret


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
        credential_id, secret = _split_bearer(bearer_token)
        principal = self._credentials.authenticate(credential_id, secret, request_id=request_id)
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
    # R-7: the enforcement side of `request_bytes` is a fact about THIS
    # HTTP composition (the middleware below genuinely measures and
    # enforces it), not about `cell.py`'s own backend-independent
    # declaration -- `ApplicationRuntime.capabilities()` remains the
    # single source of truth for capability CONTENT (R-3); this is the
    # one enforcement-layer fact the wire adds on top, in the same commit
    # as the real enforcement it declares.
    document = {**document, "limit_enforcement": {**document["limit_enforcement"], "request_bytes": "enforced"}}
    return JSONResponse(document, status_code=200)


@_endpoint
async def post_query(request: Request) -> Response:
    session = _authenticate(request)
    entity = request.path_params["entity"]
    body = await _read_json_object(request)
    _check_object_shape(body, _SCHEMAS["QueryRequest"], label="QueryRequest")

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
    item: dict[str, Any] = {"type": raw["operation"], "collection": entity}
    if "values" in raw:
        item["values"] = raw["values"]
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
        raise CapabilityError("idempotency_key is not supported by this peer")
    transaction = body.get("transaction", "atomic")
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

    results = session.transact(items, request_id=_request_id(request))
    affected = 0
    for item, result in zip(items, results):
        if item["type"] == "insert":
            affected += 1
        elif isinstance(result, dict):
            affected += result.get("updated", result.get("deleted", 0))
    return JSONResponse({"committed": True, "affected": affected}, status_code=200)


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
    item: dict[str, Any] = {"type": raw["operation"], "collection": raw["entity"]}
    if "values" in raw:
        item["values"] = raw["values"]
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
        raise CapabilityError("idempotency_key is not supported by this peer")

    operations = body.get("operations")
    if not isinstance(operations, list) or not operations:
        raise ValidationError("operations must be a non-empty array")
    items = [_scoped_mutation_item(op) for op in operations]

    results = session.transact(items, request_id=_request_id(request))
    affected = 0
    for item, result in zip(items, results):
        if item["type"] == "insert":
            affected += 1
        elif isinstance(result, dict):
            affected += result.get("updated", result.get("deleted", 0))
    return JSONResponse({"committed": True, "affected": affected}, status_code=200)


@_endpoint
async def get_catalog(request: Request) -> Response:
    # `application_catalog: unavailable` (cell.py's own declaration,
    # unchanged this WP) -- there is no public "list collections"
    # operation on this peer at all.
    _authenticate(request)
    raise CapabilityError("application catalog discovery is not available on this peer")


@_endpoint
async def post_schema(request: Request) -> Response:
    session = _authenticate(request)
    body = await _read_json_object(request)
    _check_object_shape(body, _SCHEMAS["SchemaOperationRequest"], label="SchemaOperationRequest")
    operation = body.get("operation")
    if operation not in _SCHEMA_OPERATIONS:
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

    if operation == "create_entity":
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
        # P3-D1 (design §0 exception, WP-1): the contract's `fields` on
        # `create_entity` is a bare array of NAMES (no per-field
        # `field_type` slot) -- `SchemaOperationRequest.field_type` is a
        # single, request-level value with no per-field association, so a
        # mixed-type entity can only be built as `create_entity` (fields
        # omitted or name-only) followed by one `add_field` per typed
        # field (the r2db-http-established form the design doc itself
        # names). WP-3 design decision (reported to the requester): a
        # name-only `fields` array here has no type information to honor
        # at all, so every named field is created as this peer's own
        # `text` type -- the same "untyped-equivalent" treatment r2db-api
        # gives a type-less `create_entity` field (its own `field_type is
        # None` "JSONB-equivalent" branch, `structured.py::_check_type`) --
        # rather than silently guessing at a narrower type this peer's own
        # backends could reject the caller's real first write against.
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
            fields = {name: "text" for name in fields_raw}
        else:
            fields = None
        session.create_entity(entity, fields, request_id=_request_id(request))
        # m-2 (independent review): the peer's REAL current schema-revision
        # counter (`ApplicationRuntime.schema_revision()`, the same value
        # `cell.py`'s own delete-confirmation fingerprint reads) -- never a
        # hardcoded placeholder that would falsely claim the same "revision"
        # after every schema change.
        return JSONResponse({"committed": True, "revision": str(session.schema_revision(request_id=_request_id(request)))}, status_code=200)

    if operation == "add_field":
        field = body.get("field")
        field_type = body.get("field_type")
        if not isinstance(field, str) or field_type not in _CONTRACT_FIELD_TYPE_TO_MITATEDB:
            raise ValidationError("add_field requires field and a supported field_type")
        session.add_field(entity, field, _CONTRACT_FIELD_TYPE_TO_MITATEDB[field_type], request_id=_request_id(request))
        return JSONResponse({"committed": True, "revision": str(session.schema_revision(request_id=_request_id(request)))}, status_code=200)

    # C-17 present-denial form (design R-8 item 1): `alter_field`/
    # `create_index`/`drop_index`/`drop_entity` are all real, contract-
    # shaped requests this real dispatcher receives and refuses -- never a
    # structural absence on this composition, since the entry point
    # genuinely exists and executes for the two operations above.
    raise CapabilityError(f"schema operation {operation!r} is not supported by this peer")


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
