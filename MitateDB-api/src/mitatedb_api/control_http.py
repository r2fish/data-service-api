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

from typing import Any, Awaitable, Callable, Mapping

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from starlette.types import ASGIApp

from .control_plane import ControlPlaneService
from .errors import (AuditReaderUnavailable, AuthenticationError,
                     AuthenticationRequiredError, AuthorizationError,
                     AuthorizationStateUnavailable, CapabilityError,
                     ConflictError, DestructiveConfirmationRequired,
                     FoundationError, NotFoundError, ResourceLimitError,
                     StorageConfigurationError, ValidationError, violation,
                     observed_type_of)
from .http import (PROBLEM_CONTENT_TYPE, RequestByteBoundMiddleware,
                   _extract_bearer, _read_json_object, _request_id,
                   _schema_property_type_name)
# Phase 6 WP-0 (design D-4(b)): `_SCHEMAS` is imported from `.http` rather
# than this module loading its own second, independent copy of the
# contract -- `.http` already owns the packaged-copy / `importlib.
# resources` load (this peer's own single source of truth for the parsed
# contract), and a second, separately-maintained repository-relative
# lookup here (`Path(__file__).resolve()` walked three parent directories
# up to `"spec"`) was the SAME known coupling design D-4(b) closes in
# `http.py` -- fixing only one of the two call sites would have left this
# one silently broken the moment this package was installed/copied
# anywhere the `spec/` checkout was not a sibling three directories up.
# Mirrors r2db-api's own `r2db_api.control_http`, which already imports
# `_SCHEMAS` from `r2db_api.http` for the identical reason (this module's
# own docstring above: "no code sharing between peers" governs code
# shared BETWEEN the two peers, not a peer's own two files reusing each
# other's already-loaded module state).
from .http import _SCHEMAS

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
    # `AuditReaderUnavailable` (audit_query.PostgresAuditQueryStore.query's
    # own psycopg.Error path other than InsufficientPrivilege): mapped to
    # the same SERVICE_UNAVAILABLE code, and listed explicitly here (not
    # left to the exhaustive-by-construction fallback in `_classify`
    # below) so that fallback's own "pragma: no cover" comment stays true
    # -- the same discipline `http.py::_CLASSIFY_ORDER` already applies
    # for `AuditSinkUnavailable`.
    (AuditReaderUnavailable, "SERVICE_UNAVAILABLE"),
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
    """追補 4 O-1 (版フリップ監査 §14 疑義 1/§16, `{scratchpad}/rulings-r3-
    r7-flip.md`): mirrors `http.py`'s own data-plane `_check_object_shape`
    (V-6/L-4 rework) -- every denial here now carries `violated_
    declaration: request_schema` too. Every call site in this module
    passes `value` as the control-plane request BODY itself (never a
    nested object), so there is no narrower `own_path` than the request
    root: `field` is omitted for the "must be an object" leg (the whole
    body is what failed, D-3 (4): a violation not attributable to one
    position), and is the sole offending TOP-LEVEL key for the unknown-
    field/missing-field legs (`None` when more than one key is at fault,
    matching `_prepare_values`'s own "single unknown field names it,
    multiple omit it" convention, V-6)."""
    if not isinstance(value, dict):
        raise ValidationError(
            f"{label} must be an object",
            details=violation("request_schema", declared_type="object", observed_type=observed_type_of(value)),
        )
    allowed = set(schema.get("properties", {}))
    extra = set(value) - allowed
    if extra:
        sole = next(iter(extra)) if len(extra) == 1 else None
        raise ValidationError(
            f"{label} contains unsupported fields: {sorted(extra)}",
            details=violation("request_schema", field=sole),
        )
    missing = set(schema.get("required", [])) - set(value)
    if missing:
        sole = next(iter(missing)) if len(missing) == 1 else None
        if sole is not None:
            raise ValidationError(
                f"{label} is missing required fields: {sorted(missing)}",
                details=violation(
                    "request_schema", field=sole,
                    declared_type=_schema_property_type_name(schema, sole), observed_type="absent",
                ),
            )
        raise ValidationError(
            f"{label} is missing required fields: {sorted(missing)}",
            details=violation("request_schema"),
        )
    return value


def _bearer(request: Request) -> str | None:
    """Phase 6 WP-3 差し戻し 最終ラウンド (supervisor ruling 2026-09-04,
    裁定 1): this HTTP boundary never splits the presented bearer itself
    any more -- it is a thin wrapper over `http.py::_extract_bearer`
    (`None` when no bearer token is present at all), returning the
    presented token VERBATIM. Every handler below forwards this value,
    unsplit, straight to `ControlPlaneService`, which forwards it
    unchanged to `self._backend.authenticate_control`
    (`control_auth.ControlCredentialStore.authenticate`/
    `control_credential_store_postgres.PostgresControlCredentialStore.
    authenticate`) -- the single choke point that calls `split_bearer_
    locator` exactly once. A malformed bearer is no longer distinguished
    HERE: it reaches `ControlPlaneService._authenticate` like any other
    credential and comes back as an ordinary, durably-audited `AUTH_
    INVALID` (`ControlPlaneService.deny_malformed_credential`'s own
    separate pre-emptive routing is therefore no longer reachable from
    this module and has been retired -- the standard `_authenticate`
    except-`AuthenticationError` path already records the identical
    denial shape)."""
    return _extract_bearer(request)


Handler = Callable[[Request], Awaitable[Response]]


def _endpoint(handler: Handler) -> Handler:
    async def wrapped(request: Request) -> Response:
        request_id = _request_id(request)
        try:
            return await handler(request)
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


# WP-8b (design D-8 (3)): every handler below delegates its own
# synchronous section (rate precharge / `_service(request).<op>` -- a real
# `ControlPlaneService` call, itself Postgres-backed on this HTTP
# composition) to `starlette.concurrency.run_in_threadpool`, same
# rationale/limiter-size fact as `http.py`'s own identical module-level
# comment. A handler with a request body delegates `_precharge`/`_bearer`
# on their own, BEFORE the body is read -- `_precharge`'s own docstring
# ("rate-limit runs before EVERYTHING else, including reading ... the
# request body") is what fixes that ordering, not this WP -- then
# delegates the shape check plus the real service call together, after
# the async body read.


@_endpoint
async def get_control_capabilities(request: Request) -> Response:
    def _sync() -> dict[str, Any]:
        _precharge(request)
        secret = _bearer(request)
        document = request.app.state.control_service.control_capabilities(
            secret, rate_precharged=True)
        # R-7: the HTTP-layer enforcement fact, added on top of the
        # service-layer default (`unavailable`) in the same commit as the real
        # enforcement it declares (`RequestByteBoundMiddleware` below).
        return {**document, "limit_enforcement": {**document["limit_enforcement"], "request_bytes": "enforced"}}

    document = await run_in_threadpool(_sync)
    return JSONResponse(document, status_code=200)


@_endpoint
async def post_register_application(request: Request) -> Response:
    await run_in_threadpool(_precharge, request)
    secret = _bearer(request)
    body = await _read_json_object(request)

    def _sync() -> dict[str, Any]:
        _check_object_shape(body, _SCHEMAS["ApplicationRegistrationRequest"], label="ApplicationRegistrationRequest")
        return _service(request).register_application(
            secret, body.get("application_id"), rate_precharged=True)

    result = await run_in_threadpool(_sync)
    return JSONResponse(result, status_code=200)


@_endpoint
async def get_list_applications(request: Request) -> Response:
    def _sync() -> dict[str, Any]:
        _precharge(request)
        secret = _bearer(request)
        return _service(request).list_applications(secret, rate_precharged=True)

    result = await run_in_threadpool(_sync)
    return JSONResponse(result, status_code=200)


@_endpoint
async def post_disable_application(request: Request) -> Response:
    def _sync() -> dict[str, Any]:
        _precharge(request)
        secret = _bearer(request)
        application_id = request.path_params["application_id"]
        return _service(request).set_application_enabled(
            secret, application_id, False, rate_precharged=True)

    result = await run_in_threadpool(_sync)
    return JSONResponse(result, status_code=200)


@_endpoint
async def post_enable_application(request: Request) -> Response:
    def _sync() -> dict[str, Any]:
        _precharge(request)
        secret = _bearer(request)
        application_id = request.path_params["application_id"]
        return _service(request).set_application_enabled(
            secret, application_id, True, rate_precharged=True)

    result = await run_in_threadpool(_sync)
    return JSONResponse(result, status_code=200)


@_endpoint
async def post_issue_credential(request: Request) -> Response:
    await run_in_threadpool(_precharge, request)
    secret = _bearer(request)
    body = await _read_json_object(request)

    def _sync() -> dict[str, Any]:
        _check_object_shape(body, _SCHEMAS["CredentialIssueRequest"], label="CredentialIssueRequest")
        return _service(request).issue_credential(
            secret, body.get("application_id"), body.get("role"), rate_precharged=True)

    result = await run_in_threadpool(_sync)
    return JSONResponse(result, status_code=200)


@_endpoint
async def get_list_credentials(request: Request) -> Response:
    def _sync() -> dict[str, Any]:
        _precharge(request)
        secret = _bearer(request)
        return _service(request).list_credentials(secret, rate_precharged=True)

    result = await run_in_threadpool(_sync)
    return JSONResponse(result, status_code=200)


@_endpoint
async def post_rotate_credential(request: Request) -> Response:
    def _sync() -> dict[str, Any]:
        _precharge(request)
        secret = _bearer(request)
        target_credential_id = request.path_params["credential_id"]
        return _service(request).rotate_credential(secret, target_credential_id, rate_precharged=True)

    result = await run_in_threadpool(_sync)
    return JSONResponse(result, status_code=200)


@_endpoint
async def post_revoke_credential(request: Request) -> Response:
    await run_in_threadpool(_precharge, request)
    secret = _bearer(request)
    target_credential_id = request.path_params["credential_id"]
    raw_body = await request.body()
    body: dict[str, Any] = {}
    if raw_body:
        body = await _read_json_object(request)

    def _sync() -> dict[str, Any]:
        if raw_body:
            _check_object_shape(body, _SCHEMAS["CredentialRevokeRequest"], label="CredentialRevokeRequest")
        return _service(request).revoke_credential(
            secret, target_credential_id,
            destructive=body.get("destructive"), confirmation=body.get("confirmation"), rate_precharged=True)

    result = await run_in_threadpool(_sync)
    return JSONResponse(result, status_code=200)


@_endpoint
async def post_disable_credential(request: Request) -> Response:
    def _sync() -> dict[str, Any]:
        _precharge(request)
        secret = _bearer(request)
        target_credential_id = request.path_params["credential_id"]
        return _service(request).set_credential_enabled(
            secret, target_credential_id, False, rate_precharged=True)

    result = await run_in_threadpool(_sync)
    return JSONResponse(result, status_code=200)


@_endpoint
async def post_enable_credential(request: Request) -> Response:
    def _sync() -> dict[str, Any]:
        _precharge(request)
        secret = _bearer(request)
        target_credential_id = request.path_params["credential_id"]
        return _service(request).set_credential_enabled(
            secret, target_credential_id, True, rate_precharged=True)

    result = await run_in_threadpool(_sync)
    return JSONResponse(result, status_code=200)


# --------------------------------------------------------------------------
# Phase 4 WP-3(b) (design D-5): `audit_query` -- two paths, ONE handler.
# `/control/v1/audit/query` is the canonical location (contract 1.4.0
# `control_endpoints.audit_query`); `/v1/audit/query` is the pre-1.4.0
# `endpoints.audit_query` path, retained here as an alias of the identical
# operation for one further minor version (contract `endpoints.audit_query.
# deprecation_note`) -- D-5's own rationale for serving it from the CONTROL
# host, not the data-plane one: a single-ingress deployment that routes by
# path prefix (`/v1/*` -> data-plane, `/control/v1/*` -> control-plane)
# would otherwise never be able to reach `audit_query` through the alias at
# all, and a deployment that firewalls `/control/v1/*` to a management
# network only would otherwise leave `/v1/audit/query` outside that
# boundary. Registering both here, pointed at the identical handler, makes
# `/control/v1/audit/query` the correct path under EITHER convention.
# --------------------------------------------------------------------------


def _precharge_audit(request: Request) -> None:
    """`audit_requests_per_minute` -- its OWN window, charged before
    ANYTHING else (design D-5 asked for a pre-auth window of its own; it is counted as a sliding one), never `_precharge`
    (`control_requests_per_minute` is a DIFFERENT counter this handler must
    never touch -- design M-8 / P4-D4 item 8: a high-frequency audit
    poller must not be able to exhaust the window a break-glass `revoke_
    credential` depends on)."""
    _service(request).check_audit_rate()


@_endpoint
async def post_audit_query(request: Request) -> Response:
    # WP-8b (design D-8 (3)): `_precharge_audit` delegated on its own,
    # before the body is read (same ordering rationale as `_precharge`
    # above); the real `audit_query` service call is delegated together
    # with the optional shape check, after the async body read.
    await run_in_threadpool(_precharge_audit, request)
    secret = _bearer(request)
    # `AuditQueryRequest`'s own contract schema has no `required` entries
    # at all (every field optional) -- read the same way `post_revoke_
    # credential` reads its own optional body above.
    raw_body = await request.body()
    body: dict[str, Any] = {}
    if raw_body:
        body = await _read_json_object(request)

    def _sync() -> dict[str, Any]:
        if raw_body:
            _check_object_shape(body, _SCHEMAS["AuditQueryRequest"], label="AuditQueryRequest")
        return _service(request).audit_query(secret, body, rate_precharged=True)

    result = await run_in_threadpool(_sync)
    return JSONResponse(result, status_code=200)


# --------------------------------------------------------------------------
# App assembly (WP-5 flip: mounted by `control_main.build_control_app`).
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
    # Phase 4 WP-3(b) (design D-5): registered unconditionally -- even when
    # AUDIT DSN is unset, so an unprovided `audit_query` answers `CAPABILITY_
    # UNSUPPORTED` after authenticating, never a bare 404 (D-5 M-4). Both
    # resolve to the SAME handler, `post_audit_query` (this module's own
    # comment above explains the two-path rationale). This is the ONE
    # deliberate `/v1/...`-shaped path in this route table (`tests/test_
    # audit_query.py::test_control_and_data_plane_route_tables_are_
    # disjoint_except_the_audit_query_alias` asserts it by name);
    # `http.py`'s own `_ROUTES` still contains no `/control` path at all,
    # unchanged.
    Route("/control/v1/audit/query", post_audit_query, methods=["POST"]),
    Route("/v1/audit/query", post_audit_query, methods=["POST"]),
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
