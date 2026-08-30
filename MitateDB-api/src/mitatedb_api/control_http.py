"""`/control/v1` ASGI app (design v1.2 R-6/R-7, WP-4).

**Not mounted anywhere** in this WP -- `main.py` never imports this module,
and no composition root serves it (design R-7: "declared-unavailable form
(b) の状態を一瞬も経由しない" -- mounting this before the WP-5 flip commit
would make `control_plane` a real, reachable surface while the capability
document still declared it `unavailable`, the exact authenticity gap R-7
forbids). `test_control_http_unmounted.py` fixes this fact with a
regression test. This module exists, and is directly testable via `httpx`/
`ASGITransport` against `create_control_app(...)` called by hand, purely so
WP-5's mount is a one-line composition-root change rather than new code
written under time pressure at flip time.

Same GENERAL shape as `http.py` (Starlette ASGI app, contract-driven
top-level shape checking, problem+json errors) -- reuses several of that
module's own generic ASGI utilities directly (`RequestByteBoundMiddleware`,
the bearer-token extraction helpers, the request-id plumbing, the error
problem-body renderer) rather than re-implementing byte-for-byte
equivalents: these are internal infrastructure of THIS peer's own HTTP
surface, shared between its two ASGI apps exactly as any two endpoints of
one application would share a request-parsing helper -- R-2's "no code
sharing between peers" principle does not apply to a peer's own two files.
The actual control-plane REQUEST/RESPONSE handling below (route table,
request-shape checks against contract `ApplicationRegistrationRequest`/
`CredentialIssueRequest`/`CredentialRevokeRequest`, dispatch onto
`control_plane.ControlPlaneService`) is new code, independent of
`r2db_api.control_http` (read only as a reference for the task).
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
from starlette.types import ASGIApp

from .control_plane import ControlPlaneService
from .errors import (AuthenticationError, AuthenticationRequiredError,
                     AuthorizationError, AuthorizationStateUnavailable,
                     CapabilityError, ConflictError,
                     DestructiveConfirmationRequired, FoundationError,
                     NotFoundError, ResourceLimitError,
                     StorageConfigurationError, ValidationError)
from .http import (PROBLEM_CONTENT_TYPE, RequestByteBoundMiddleware,
                   _CredentialMalformed, _CredentialMissing, _extract_bearer,
                   _read_json_object, _request_id, _split_bearer)

_CONTRACT_PATH = Path(__file__).resolve().parents[3] / "spec" / "data-service-api.v1.json"
_CONTRACT = json.loads(_CONTRACT_PATH.read_text())
_SCHEMAS = _CONTRACT["schemas"]

# Control-plane-specific status map: `AUTH_REQUIRED` is added on top of
# `http.py`'s own table (the app-plane emits it too, but via a DIFFERENT
# code path -- `_CredentialMissing` mapped inline, never through this peer's
# `_classify`/`errors.py` hierarchy at all -- so it never needed an entry
# there; this module's own `AuthenticationRequiredError` DOES flow through
# this table, since `ControlPlaneService` itself raises it as a real
# `errors.FoundationError` subclass, R-4/testability: WP-4's tests call the
# service directly with no HTTP boundary at all).
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

# `errors.FoundationError` subclass -> contract code. `AuthenticationRequiredError`
# is checked BEFORE its own base class `AuthenticationError` -- both `isinstance`
# checks would otherwise match a `AuthenticationRequiredError` instance, and
# tuple order is how `_classify` below picks the more specific one.
_CLASSIFY_ORDER: tuple[tuple[type[FoundationError], str], ...] = (
    (AuthorizationStateUnavailable, "AUTH_STATE_UNAVAILABLE"),
    (StorageConfigurationError, "SERVICE_UNAVAILABLE"),
    (AuthenticationRequiredError, "AUTH_REQUIRED"),
    (AuthenticationError, "AUTH_INVALID"),
    (AuthorizationError, "FORBIDDEN"),
    (CapabilityError, "CAPABILITY_UNSUPPORTED"),
    (ValidationError, "VALIDATION_FAILED"),
    (ResourceLimitError, "LIMIT_EXCEEDED"),
    (DestructiveConfirmationRequired, "DESTRUCTIVE_CONFIRMATION_REQUIRED"),
    (ConflictError, "CONFLICT"),
    (NotFoundError, "NOT_FOUND"),
)

_MESSAGE_BY_CODE = {
    "AUTH_REQUIRED": "Authentication is required.",
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
}


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
    message = _MESSAGE_BY_CODE.get(code, "The request could not be completed.")
    details = getattr(exc, "details", None)
    return _problem(code, message, request_id=request_id, details=details)


def _generic_service_unavailable(request_id: str) -> JSONResponse:
    return _problem("SERVICE_UNAVAILABLE", "The service is temporarily unavailable.", request_id=request_id)


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


def _bearer_pair(request: Request) -> tuple[str | None, str | None]:
    """Returns `(credential_id, secret)`, or `(None, None)` when no bearer
    token is present at all. Raises `_CredentialMalformed` (reused from
    `http.py`) for a present-but-unparseable token -- classified
    `AUTH_INVALID`, same as the application plane (a malformed credential
    was presented, distinct from none at all)."""
    token = _extract_bearer(request)
    if token is None:
        return None, None
    return _split_bearer(token)


Handler = Callable[[Request], Awaitable[Response]]


def _endpoint(handler: Handler) -> Handler:
    async def wrapped(request: Request) -> Response:
        request_id = _request_id(request)
        try:
            return await handler(request)
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


def _service(request: Request) -> ControlPlaneService:
    return request.app.state.control_service


def _precharge(request: Request) -> None:
    """R-6 evaluation order: rate-limit runs before EVERYTHING else,
    including reading the Authorization header or the request body. Called
    at the very top of every handler below, uniformly -- every subsequent
    `ControlPlaneService` call in this module passes `rate_precharged=True`
    so the window is never charged twice for one logical request."""
    _service(request).check_rate()


# --------------------------------------------------------------------------
# Endpoints (spec/data-service-api.v1.json -> "control_endpoints").
# --------------------------------------------------------------------------


@_endpoint
async def get_control_capabilities(request: Request) -> Response:
    _precharge(request)
    credential_id, secret = _bearer_pair(request)
    document = request.app.state.control_service.control_capabilities(
        credential_id, secret, rate_precharged=True)
    # R-7: the HTTP-layer enforcement fact, added on top of the
    # service-layer default (`unavailable`) in the same commit as the real
    # enforcement it declares (`RequestByteBoundMiddleware` below).
    document = {**document, "limit_enforcement": {**document["limit_enforcement"], "request_bytes": "enforced"}}
    return JSONResponse(document, status_code=200)


@_endpoint
async def post_register_application(request: Request) -> Response:
    _precharge(request)
    credential_id, secret = _bearer_pair(request)
    body = await _read_json_object(request)
    _check_object_shape(body, _SCHEMAS["ApplicationRegistrationRequest"], label="ApplicationRegistrationRequest")
    result = _service(request).register_application(
        credential_id, secret, body.get("application_id"), rate_precharged=True)
    return JSONResponse(result, status_code=200)


@_endpoint
async def get_list_applications(request: Request) -> Response:
    _precharge(request)
    credential_id, secret = _bearer_pair(request)
    result = _service(request).list_applications(credential_id, secret, rate_precharged=True)
    return JSONResponse(result, status_code=200)


@_endpoint
async def post_disable_application(request: Request) -> Response:
    _precharge(request)
    credential_id, secret = _bearer_pair(request)
    application_id = request.path_params["application_id"]
    result = _service(request).set_application_enabled(
        credential_id, secret, application_id, False, rate_precharged=True)
    return JSONResponse(result, status_code=200)


@_endpoint
async def post_enable_application(request: Request) -> Response:
    _precharge(request)
    credential_id, secret = _bearer_pair(request)
    application_id = request.path_params["application_id"]
    result = _service(request).set_application_enabled(
        credential_id, secret, application_id, True, rate_precharged=True)
    return JSONResponse(result, status_code=200)


@_endpoint
async def post_issue_credential(request: Request) -> Response:
    _precharge(request)
    credential_id, secret = _bearer_pair(request)
    body = await _read_json_object(request)
    _check_object_shape(body, _SCHEMAS["CredentialIssueRequest"], label="CredentialIssueRequest")
    result = _service(request).issue_credential(
        credential_id, secret, body.get("application_id"), body.get("role"), rate_precharged=True)
    return JSONResponse(result, status_code=200)


@_endpoint
async def get_list_credentials(request: Request) -> Response:
    _precharge(request)
    credential_id, secret = _bearer_pair(request)
    result = _service(request).list_credentials(credential_id, secret, rate_precharged=True)
    return JSONResponse(result, status_code=200)


@_endpoint
async def post_rotate_credential(request: Request) -> Response:
    _precharge(request)
    credential_id, secret = _bearer_pair(request)
    target_credential_id = request.path_params["credential_id"]
    result = _service(request).rotate_credential(credential_id, secret, target_credential_id, rate_precharged=True)
    return JSONResponse(result, status_code=200)


@_endpoint
async def post_revoke_credential(request: Request) -> Response:
    _precharge(request)
    credential_id, secret = _bearer_pair(request)
    target_credential_id = request.path_params["credential_id"]
    raw_body = await request.body()
    body: dict[str, Any] = {}
    if raw_body:
        body = await _read_json_object(request)
        _check_object_shape(body, _SCHEMAS["CredentialRevokeRequest"], label="CredentialRevokeRequest")
    result = _service(request).revoke_credential(
        credential_id, secret, target_credential_id,
        destructive=body.get("destructive"), confirmation=body.get("confirmation"), rate_precharged=True)
    return JSONResponse(result, status_code=200)


@_endpoint
async def post_disable_credential(request: Request) -> Response:
    _precharge(request)
    credential_id, secret = _bearer_pair(request)
    target_credential_id = request.path_params["credential_id"]
    result = _service(request).set_credential_enabled(
        credential_id, secret, target_credential_id, False, rate_precharged=True)
    return JSONResponse(result, status_code=200)


@_endpoint
async def post_enable_credential(request: Request) -> Response:
    _precharge(request)
    credential_id, secret = _bearer_pair(request)
    target_credential_id = request.path_params["credential_id"]
    result = _service(request).set_credential_enabled(
        credential_id, secret, target_credential_id, True, rate_precharged=True)
    return JSONResponse(result, status_code=200)


# --------------------------------------------------------------------------
# App assembly. NEVER called from `main.py` in this WP -- see module
# docstring.
# --------------------------------------------------------------------------

_ROUTES = [
    Route("/control/v1/capabilities", get_control_capabilities, methods=["GET"]),
    Route("/control/v1/applications", post_register_application, methods=["POST"]),
    Route("/control/v1/applications", get_list_applications, methods=["GET"]),
    Route("/control/v1/applications/{application_id}/disable", post_disable_application, methods=["POST"]),
    Route("/control/v1/applications/{application_id}/enable", post_enable_application, methods=["POST"]),
    Route("/control/v1/credentials", post_issue_credential, methods=["POST"]),
    Route("/control/v1/credentials", get_list_credentials, methods=["GET"]),
    Route("/control/v1/credentials/{credential_id}/rotate", post_rotate_credential, methods=["POST"]),
    Route("/control/v1/credentials/{credential_id}/revoke", post_revoke_credential, methods=["POST"]),
    Route("/control/v1/credentials/{credential_id}/disable", post_disable_credential, methods=["POST"]),
    Route("/control/v1/credentials/{credential_id}/enable", post_enable_credential, methods=["POST"]),
]


def create_control_app(service: ControlPlaneService, *, request_bytes_limit: int, lifespan: Any = None) -> ASGIApp:
    """Builds the `/control/v1` ASGI application. Deliberately named
    differently from `http.create_app` (application plane) so a
    composition root cannot accidentally wire the wrong one to the wrong
    port/service (`main.py` does not call this function at all in this
    WP -- `test_control_http_unmounted.py` fixes that fact)."""
    app = Starlette(
        routes=_ROUTES,
        exception_handlers={
            StarletteHTTPException: _http_exception_handler,
            Exception: _unhandled_exception_handler,
        },
        lifespan=lifespan,
    )
    app.state.control_service = service
    return RequestByteBoundMiddleware(app, request_bytes_limit=request_bytes_limit)


__all__ = ["create_control_app"]
