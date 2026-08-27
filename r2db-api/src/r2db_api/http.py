"""ASGI HTTP boundary over `DataService` (docs/design/R2DB_SERVICE_LAYER_ARCHITECTURE.md, D-2).

This module owns the HTTP surface only. All authority, structured-operation
validation, and resource-limit enforcement below the byte-bound stays in
`DataService` / `structured.py` / `limits.py` / `auth.py`; this file does not
duplicate that logic, it only translates the contract's endpoint table
(`spec/data-service-api.v1.json`) onto `DataService` calls and maps outcomes
to `application/problem+json`.

Request shapes are not re-declared with a second (pydantic) type system.
`spec/data-service-api.v1.json` is loaded at import time and used as the
single source of truth for which top-level request fields are accepted,
matching D-2's reason for choosing Starlette over FastAPI.
"""
from __future__ import annotations

import json
import uuid
from importlib import resources
from pathlib import Path
from typing import Any, Awaitable, Callable

from starlette.applications import Starlette
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .auth import AuthContext
from .errors import FoundationError, fail
from .service import DataService

PROBLEM_CONTENT_TYPE = "application/problem+json"
REQUEST_ID_HEADER = b"x-request-id"

# --------------------------------------------------------------------------
# Contract as the single source of truth for request shapes (D-2).
#
# `spec/data-service-api.v1.json` in the common repository remains the
# authored source of truth (CLAUDE.md: this package must not become the
# implicit owner of the public contract). What ships inside this
# distribution is a byte-identical packaged *copy*
# (`r2db_api/contract/data-service-api.v1.json`, wired in as package data
# in `pyproject.toml`), loaded via `importlib.resources` so a unit installed
# or copied onto the VPS without the sibling `spec/` checkout (§5.3, C-1)
# still imports. `tests/test_http.py` asserts the packaged copy is
# byte-identical to the checkout's `spec/`, so the two can never silently
# drift apart. Running from a repository checkout without having synced the
# packaged copy still works via the fallback below.
# --------------------------------------------------------------------------

_PACKAGED_CONTRACT_PATH = "data-service-api.v1.json"
_REPO_CONTRACT_PATH = Path(__file__).resolve().parents[3] / "spec" / "data-service-api.v1.json"


def _load_contract_text() -> str:
    try:
        packaged = resources.files("r2db_api.contract").joinpath(_PACKAGED_CONTRACT_PATH)
        if packaged.is_file():
            return packaged.read_text()
    except (ModuleNotFoundError, FileNotFoundError, NotADirectoryError):
        pass
    return _REPO_CONTRACT_PATH.read_text()


_CONTRACT = json.loads(_load_contract_text())
_SCHEMAS = _CONTRACT["schemas"]
_DEFINITIONS = _CONTRACT["definitions"]


def _check_object_shape(value: Any, schema: dict[str, Any], *, label: str) -> dict[str, Any]:
    """Reject unknown top-level fields and missing required fields per `schema`.

    This is the boundary that guarantees a client-supplied `application_id`,
    `role`, `database`, or `schema` field in a request body is rejected
    outright rather than silently accepted -- the contract's
    `structured_operations.scope` note and SI-06 require that such fields
    never be authority, and `additionalProperties: false` on these schemas
    means they are not even valid input. Deep validation of nested
    values (predicates, mutations, identifiers, operators) is intentionally
    left to `structured.py`, which already owns it.
    """
    if not isinstance(value, dict):
        fail("VALIDATION_FAILED", f"{label} must be an object.")
    allowed = set(schema.get("properties", {}))
    extra = set(value) - allowed
    if extra:
        fail("VALIDATION_FAILED", f"{label} contains unsupported fields.", details={"fields": sorted(extra)})
    missing = set(schema.get("required", [])) - set(value)
    if missing:
        fail("VALIDATION_FAILED", f"{label} is missing required fields.", details={"fields": sorted(missing)})
    return value


# --------------------------------------------------------------------------
# Byte bound before parsing (SI-08) + per-request id.
# --------------------------------------------------------------------------


class RequestByteBoundMiddleware:
    """Enforces `ResourceLimits.request_bytes` before the wrapped app runs.

    The bound is measured from actual bytes received in the ASGI receive
    loop, never from the `Content-Length` header (a chunked body or a lying
    header must still be bounded). The entire body is drained and measured
    here, in this middleware, before the wrapped Starlette application is
    even invoked for an in-bound request; for an over-bound request the
    Starlette application is never invoked at all, so its body parser never
    sees the oversized body and Starlette's own error-handling machinery
    (`ServerErrorMiddleware`) never gets a chance to substitute a different
    response for the deterministic 413 this middleware sends.

    This also mints the per-request `request_id` (D-2) and stamps it into
    `scope["state"]` before the wrapped app runs, and into every outgoing
    response header, including responses produced entirely inside the
    wrapped app (success and error alike).
    """

    def __init__(self, app: ASGIApp, limits: Any) -> None:
        self.app = app
        self._limits = limits

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = uuid.uuid4().hex
        state = scope.setdefault("state", {})
        state["request_id"] = request_id

        bound = self._limits.request_bytes
        buffered: list[Message] = []
        total = 0
        exceeded = False

        while True:
            message = await receive()
            if message.get("type") == "http.request":
                total += len(message.get("body", b""))
                if total > bound:
                    exceeded = True
                    break
                buffered.append(message)
                if not message.get("more_body", False):
                    break
            else:
                # e.g. http.disconnect before the body completed.
                buffered.append(message)
                break

        if exceeded:
            error = FoundationError(
                "LIMIT_EXCEEDED",
                "Request body exceeds the configured resource limit.",
                status=413,
                details={"resource": "request_bytes", "limit": bound},
            )
            await _send_problem_directly(send, error, request_id)
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


async def _send_problem_directly(send: Send, error: FoundationError, request_id: str) -> None:
    """Send an `application/problem+json` response without a Starlette Request/Response.

    Used only for the byte-bound rejection, which happens before the
    wrapped Starlette application is invoked.
    """
    payload = json.dumps(error.problem(request_id)).encode("utf-8")
    headers = [
        (b"content-type", PROBLEM_CONTENT_TYPE.encode() + b"; charset=utf-8"),
        (b"content-length", str(len(payload)).encode()),
        (REQUEST_ID_HEADER, request_id.encode()),
    ]
    await send({"type": "http.response.start", "status": error.status, "headers": headers})
    await send({"type": "http.response.body", "body": payload})


# --------------------------------------------------------------------------
# Safe error responses (SI-10).
# --------------------------------------------------------------------------


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", ""))


def _problem_response(error: FoundationError, request_id: str) -> JSONResponse:
    return JSONResponse(error.problem(request_id), status_code=error.status, media_type=PROBLEM_CONTENT_TYPE)


def _generic_service_unavailable(request_id: str) -> JSONResponse:
    # SI-10: an uncaught exception must never reach the client as a traceback
    # or internal message. The real exception is deliberately discarded here
    # (not interpolated into the response, not logged by this layer) rather
    # than risking a partial/unsafe rendering of it.
    safe = FoundationError("SERVICE_UNAVAILABLE", "The service is temporarily unavailable.", status=503)
    return _problem_response(safe, request_id)


Handler = Callable[[Request], Awaitable[Response]]


def _endpoint(handler: Handler) -> Handler:
    async def wrapped(request: Request) -> Response:
        request_id = _request_id(request)
        try:
            return await handler(request)
        except FoundationError as exc:
            return _problem_response(exc, request_id)
        except Exception:
            return _generic_service_unavailable(request_id)

    return wrapped


async def _http_exception_handler(request: Request, exc: StarletteHTTPException) -> Response:
    request_id = _request_id(request)
    code = "NOT_FOUND" if exc.status_code in (404, 405) else "VALIDATION_FAILED"
    error = FoundationError(code, "The requested resource or method is not available.", status=exc.status_code)
    return _problem_response(error, request_id)


async def _unhandled_exception_handler(request: Request, exc: Exception) -> Response:
    return _generic_service_unavailable(_request_id(request))


# --------------------------------------------------------------------------
# Auth: scope is server-bound (SI-06).
# --------------------------------------------------------------------------


def _extract_bearer(request: Request) -> str | None:
    """Only the `Authorization: Bearer` header selects a credential.

    No path segment, query parameter, or body field is ever consulted here;
    `DataService.authenticate` resolves application/role from the credential
    alone, and every handler below authenticates before looking at the body.
    """
    header = request.headers.get("authorization")
    if not header:
        return None
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def _authenticate(request: Request, service: DataService) -> AuthContext:
    return service.authenticate(_extract_bearer(request), request_id=_request_id(request))


async def _read_json_object(request: Request) -> dict[str, Any]:
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        fail("VALIDATION_FAILED", "Request body must be valid JSON.")
        raise  # unreachable; fail() always raises
    if not isinstance(payload, dict):
        fail("VALIDATION_FAILED", "Request body must be a JSON object.")
    return payload


# --------------------------------------------------------------------------
# Endpoints (spec/data-service-api.v1.json -> "endpoints").
# --------------------------------------------------------------------------


@_endpoint
async def get_capabilities(request: Request) -> Response:
    service: DataService = request.app.state.service
    context = _authenticate(request, service)
    document = service.capabilities(context)
    return JSONResponse(document, status_code=200)


@_endpoint
async def post_query(request: Request) -> Response:
    service: DataService = request.app.state.service
    context = _authenticate(request, service)
    entity = request.path_params["entity"]
    body = await _read_json_object(request)
    _check_object_shape(body, _SCHEMAS["QueryRequest"], label="QueryRequest")
    if "order_by" in body:
        fail("CAPABILITY_UNSUPPORTED", "Result ordering is not supported by this foundation.")
    kwargs: dict[str, Any] = {"select": body.get("select"), "where": body.get("where")}
    page = body.get("page")
    if page is not None:
        _check_object_shape(page, _DEFINITIONS["Page"], label="page")
        if "cursor" in page:
            fail("CAPABILITY_UNSUPPORTED", "Cursor-based pagination is not supported by this foundation.")
        if "size" in page:
            kwargs["page_size"] = page["size"]
    items = service.query(context, entity, request_id=_request_id(request), **kwargs)
    return JSONResponse({"items": items, "next_page": None}, status_code=200)


@_endpoint
async def post_mutate(request: Request) -> Response:
    service: DataService = request.app.state.service
    context = _authenticate(request, service)
    entity = request.path_params["entity"]
    body = await _read_json_object(request)
    _check_object_shape(body, _SCHEMAS["MutationRequest"], label="MutationRequest")
    if "idempotency_key" in body:
        fail("CAPABILITY_UNSUPPORTED", "Idempotency keys are not supported by this foundation.")
    transaction = body.get("transaction", "atomic")
    if transaction not in {"atomic", "best_effort"}:
        fail("VALIDATION_FAILED", "Transaction mode is not supported.")
    affected = service.mutate(context, entity, body.get("operations"), transaction=transaction, request_id=_request_id(request))
    return JSONResponse({"committed": True, "affected": affected}, status_code=200)


@_endpoint
async def get_catalog(request: Request) -> Response:
    service: DataService = request.app.state.service
    context = _authenticate(request, service)
    document = service.catalog(context, request_id=_request_id(request))
    return JSONResponse(document, status_code=200)


@_endpoint
async def post_schema(request: Request) -> Response:
    service: DataService = request.app.state.service
    context = _authenticate(request, service)
    body = await _read_json_object(request)
    _check_object_shape(body, _SCHEMAS["SchemaOperationRequest"], label="SchemaOperationRequest")
    revision = service.schema(context, body, request_id=_request_id(request))
    return JSONResponse({"committed": True, "revision": str(revision)}, status_code=200)


@_endpoint
async def post_audit_query(request: Request) -> Response:
    service: DataService = request.app.state.service
    # Authenticate with the same application-credential path as every other
    # endpoint (fail closed on missing/invalid/revoked credentials first),
    # but never execute: the contract requires control/audit authority for
    # this endpoint, this foundation has no such credential type, and
    # DataService deliberately exposes no audit accessor on its public
    # facade (only ControlAuthority.audit_events() does, which is not wired
    # into this ASGI app). No application credential -- runtime or
    # developer -- can reach audit evidence through this endpoint.
    _authenticate(request, service)
    fail(
        "CAPABILITY_UNSUPPORTED",
        "Audit evidence query requires separately authenticated control/audit authority "
        "that this foundation does not expose over the application-facing HTTP surface.",
    )
    raise AssertionError("unreachable")


# --------------------------------------------------------------------------
# App assembly.
# --------------------------------------------------------------------------

_ROUTES = [
    Route("/v1/capabilities", get_capabilities, methods=["GET"]),
    Route("/v1/data/{entity}/query", post_query, methods=["POST"]),
    Route("/v1/data/{entity}/mutations", post_mutate, methods=["POST"]),
    Route("/v1/catalog", get_catalog, methods=["GET"]),
    Route("/v1/schema/operations", post_schema, methods=["POST"]),
    Route("/v1/audit/query", post_audit_query, methods=["POST"]),
]


def create_app(service: DataService) -> ASGIApp:
    """Build the ASGI application exposing `service` over the contract's HTTP surface.

    The returned callable is `RequestByteBoundMiddleware` wrapping a
    Starlette application, so SI-08's request-byte bound is enforced before
    any Starlette routing or body parsing runs.
    """
    app = Starlette(
        routes=_ROUTES,
        exception_handlers={
            StarletteHTTPException: _http_exception_handler,
            Exception: _unhandled_exception_handler,
        },
    )
    app.state.service = service
    return RequestByteBoundMiddleware(app, service.limits)
