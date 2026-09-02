"""ASGI HTTP boundary over `ControlPlaneService` (CCR-14 WP-4).

Design this file is written against: docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md
v1.6, R-1 (independent ASGI app)/R-2/R-8 (auth store separation)/R-9
(capability discovery stays a deployer declaration -- untouched here)/R-11
(deterrence declarations), §2 (the endpoint table and the common processing
order), §3 (`AuthorityTopology` -- extended in `topology.py`, not here), §5's
WP-4 row, §8 m-7 (401 code non-fixation)/m-8 (`test_topology.py` parity,
also not this file)/m-10 (no module-level app -- that is `control_main.py`'s
job), and §12.5 (the WP-3 handoff this file implements: `ControlPlaneService`'s
9 public methods already take `secret` + already-validated arguments and
return a contract-shaped dict or raise `FoundationError` with R-11's
declaration already attached in `details` -- this module's only real job is
(a) shape-checking a request body against the contract's own request schema
*before* calling the one composed service method that does rate-limit +
auth + gate + capability-refusal + target-resolution + limit-check + execute
+ audit internally in a single call (§12.5: "HTTP 層は details を
problem+json へ転写するだけ -- 意味論を bind 層に持ち込まない"), and
(b) shape-checking the dict a service method returns before it reaches a
client, as a defense-in-depth backstop against a future service bug (this
one is new relative to the data plane -- `http.py` never does this on a
response, only a request).

R-1: this is an ASGI app **independent** of `http.py`'s data-plane one --
no route, no handler function, and no authentication code is shared between
the two. What *is* shared (design's own explicit list) is imported directly
from `.http`: `RequestByteBoundMiddleware` (R-8 -- the identical byte-bound +
per-request-id middleware, wrapped around this app exactly as it wraps the
data-plane one), `_check_object_shape` + the module-level `_SCHEMAS`/
`_DEFINITIONS` the contract is loaded into at `http.py`'s import time (§2:
"制御面 schema 群に適用" -- reusing the already-loaded contract rather than
loading `spec/data-service-api.v1.json` a second time here), the
`application/problem+json` helpers (`_problem_response`, the generic-503
SI-10 safety net, the `_endpoint` FoundationError-to-problem decorator), the
bearer-extraction helper (`_extract_bearer` -- Authorization header only,
never a path/query/body field, same SI-06 discipline as the data plane), and
the JSON-object body reader. Every one of these names is a plain top-level
function/class in `http.py` with no `__all__` restricting it -- Python does
not block an explicit `from .http import _name` for a single-leading-
underscore name (only a wildcard `import *` skips those), so this reuse
needs, and makes, zero changes to `http.py` itself (the WP-4 work order
permits an "export tidying" change there; none turned out to be necessary).

`http.py`'s 401 responses carry no `WWW-Authenticate` header today (checked
directly against that file and its own test suite before writing this
module) -- this module deliberately does not invent one either, so its 401
form stays byte-for-byte the data plane's *actual* convention rather than an
assumed one.

**Round-2 review MAJOR-1**: every handler below calls `ControlPlaneService.
check_rate()` as its *first* statement -- before extracting the bearer
token, before reading or shape-checking any request body -- and then passes
`rate_precharged=True` to the one `ControlPlaneService` method it calls
afterward (see that method's own docstring, `control_plane.py`). Independent
review measured that an unauthenticated, malformed-body flood against the 3
body-carrying endpoints (`register_application`/`issue_credential`/
`revoke_credential`) previously returned `VALIDATION_FAILED` from the HTTP-
layer shape check *without ever touching the rate window* -- an unbounded
unauthenticated path under a `limit_enforcement: "enforced"` capability
declaration (design §2's canonical order is rate -> byte bound -> auth ->
shape, and the shape check on these 3 endpoints necessarily runs before the
one composed service call that used to be the only place `_check_rate` ran
-- see the "processing order" note further down this docstring for why that
part of the ordering is otherwise correct and stays that way). This is a
fix, not a reordering of shape-vs-auth: shape checking still happens before
the service call (and therefore before authentication) for the reasons
below; only the rate charge itself now happens earlier still, ahead of
shape checking too.

Note (not a fix, accepted as-is): the byte-bound 413 path still precedes
the rate window structurally -- `RequestByteBoundMiddleware` wraps the
entire Starlette app, including every route handler's `check_rate()` call,
so an over-bound body is rejected by the middleware before any handler code
(and therefore before `check_rate()`) ever runs. This mirrors the data
plane's own middleware-before-everything placement exactly (`http.py`'s
`RequestByteBoundMiddleware` docstring) and was reviewed and accepted as
data-plane parity, not a gap: a byte-bound rejection is a fixed, structural
403-free 413 with no unbounded-request-volume concern of its own (the
`Content-Length`-independent measurement itself already bounds the work
done per rejected request).
"""
from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Any, Callable

from starlette.applications import Starlette
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from starlette.types import ASGIApp

from .control_plane import ControlPlaneService
from .errors import fail
from .http import (
    RequestByteBoundMiddleware,
    _check_object_shape,
    _endpoint,
    _extract_bearer,
    _http_exception_handler,
    _read_json_object,
    _request_id,
    _SCHEMAS,
    _unhandled_exception_handler,
)

# --------------------------------------------------------------------------
# Byte bound (R-8: "同一のものを装着" -- the same middleware class, wrapped
# the same way). `RequestByteBoundMiddleware` only ever reads one attribute
# (`.request_bytes`) off whatever object it is given.
#
# Phase 3.5 WP-4 (design §4 "L4", review M-2/M-3): this used to be a
# module-level `ResourceLimits()` constant -- a second, independently
# defaulted byte bound with no relationship at all to the `ControlPlaneLimits`
# object `ControlPlaneService.capabilities()` discovers through. Single-
# sourced now: `create_control_app` below reads `control_service.limits`
# (the exact `ControlPlaneLimits` instance the service enforces internally,
# `ControlPlaneService.limits` property) and wraps the middleware with THAT
# object directly -- `ControlPlaneLimits.request_bytes` defaults to the same
# numeric value `ResourceLimits().request_bytes` always had (1 MiB), so this
# is a declaration of an existing fact, not a behavior change; but mutating
# a service's configured `request_bytes` now changes both the declared limit
# and the enforced bound from the one place that value lives, which the old
# two-separate-objects shape could never guarantee.
# --------------------------------------------------------------------------


def _check_response_shape(value: dict[str, Any], schema: dict[str, Any], *, label: str) -> None:
    """Response-side shape guard (§2, WP-4 test item 3): `ControlPlaneService`'s
    own outputs are already contract-shaped by construction, but this is a
    defense-in-depth backstop against a future service bug shipping a
    malformed dict straight to a client. A shape mismatch here is *never*
    the caller's fault (unlike a request-body shape mismatch, which is), so
    it is deliberately not surfaced as `_check_object_shape`'s own
    `VALIDATION_FAILED`/400.

    Round-2 review MINOR-3: this does **not** reuse `_check_object_shape`
    itself (which unconditionally rejects an unknown top-level key) --
    unlike every one of this file's *request* schemas (all of which declare
    `additionalProperties: false` in the contract), the contract's response
    schemas are additive-by-default (a future response field is not a
    contract-breaking change). Only `CapabilityDocument`, among the 7
    response schemas this module checks, declares `additionalProperties:
    false` itself, so it is the one response shape still checked for
    extras; every other response schema here is checked for missing
    *required* fields only.

    Round-2 review MINOR-4 (WP-3's own MI-9 precedent): either failure kind
    is folded into the exact same cause-neutral SI-10 text `http.py`'s own
    generic 503 uses, never a bespoke message naming the schema/field/label
    that actually failed -- `label` exists only for a future caller to
    correlate a failure with its call site via server-side logging, not to
    put a hint into the client-facing response.
    """
    ok = isinstance(value, dict)
    if ok:
        missing = set(schema.get("required", [])) - set(value)
        ok = not missing
        if ok and schema.get("additionalProperties") is False:
            extra = set(value) - set(schema.get("properties", {}))
            ok = not extra
    if not ok:
        fail("SERVICE_UNAVAILABLE", "The service is temporarily unavailable.", status=503)


async def _read_json_object_or_empty(request: Request) -> dict[str, Any]:
    """For the path-parameter operations the contract gives no request
    schema at all (disable/enable/rotate) or an all-optional one (revoke's
    `CredentialRevokeRequest`) -- design §1.2/§2: "body なし or 空 body を許
    す". An absent body must not be forced through `_read_json_object`'s
    `request.json()` call, which raises on empty input; `Request.body()`
    caches the raw bytes, so calling it first here and then (only when
    non-empty) delegating to `_read_json_object` never double-reads the
    stream.
    """
    raw = await request.body()
    if not raw:
        return {}
    return await _read_json_object(request)


# --------------------------------------------------------------------------
# Endpoints (spec/data-service-api.v1.json -> "control_endpoints"). Each
# handler's only judgment calls are (1) which contract request schema (if
# any) to shape-check the body against before calling the one corresponding
# `ControlPlaneService` method, and (2) which contract response schema to
# shape-check that method's return value against before it becomes a
# `JSONResponse`. Every actual authorization/gate/limit/audit/declaration
# decision happens inside that single service call (§3, §12.5) -- these
# handlers never inspect a `FoundationError` they catch (the shared
# `_endpoint` decorator, imported from `.http`, turns any of them into
# `application/problem+json` with the service's own `details` transcribed
# unchanged, exactly like the data plane).
# --------------------------------------------------------------------------


@_endpoint
async def get_control_capabilities(request: Request) -> Response:
    service: ControlPlaneService = request.app.state.control_service
    service.check_rate()  # MAJOR-1 (round-2 review): charged before anything else, see module header
    secret = _extract_bearer(request)
    document = service.capabilities(secret, request_id=_request_id(request), rate_precharged=True)
    # Phase 3.5 WP-4 (design §4 "L4", MitateDB-parity two-layer form): the
    # HTTP-layer enforcement fact, added on top of the service-layer default
    # (`"unavailable"`) in the same commit as the real enforcement it
    # declares (`RequestByteBoundMiddleware`, mounted by `create_control_app`
    # below with this exact same service's own `limits.request_bytes`).
    # `isinstance`/`.get(...)` guarded rather than a bare `document[...]`
    # subscript: a malformed response from a broken/stub service (this
    # module's own `_check_response_shape` backstop below is what is
    # actually supposed to catch that) must still reach that shape check --
    # never raise a fresh, unrelated `KeyError` from this override first.
    if isinstance(document, dict) and isinstance(document.get("limit_enforcement"), dict):
        document = {**document, "limit_enforcement": {**document["limit_enforcement"], "request_bytes": "enforced"}}
    _check_response_shape(document, _SCHEMAS["CapabilityDocument"], label="CapabilityDocument")
    return JSONResponse(document, status_code=200)


@_endpoint
async def post_register_application(request: Request) -> Response:
    service: ControlPlaneService = request.app.state.control_service
    service.check_rate()  # MAJOR-1: before the body is even read -- see module header
    secret = _extract_bearer(request)
    body = await _read_json_object(request)
    _check_object_shape(body, _SCHEMAS["ApplicationRegistrationRequest"], label="ApplicationRegistrationRequest")
    result = service.register_application(secret, body.get("application_id"), request_id=_request_id(request), rate_precharged=True)
    _check_response_shape(result, _SCHEMAS["ApplicationStateResult"], label="ApplicationStateResult")
    return JSONResponse(result, status_code=200)


@_endpoint
async def get_list_applications(request: Request) -> Response:
    service: ControlPlaneService = request.app.state.control_service
    service.check_rate()  # MAJOR-1
    secret = _extract_bearer(request)
    result = service.list_applications(secret, request_id=_request_id(request), rate_precharged=True)
    _check_response_shape(result, _SCHEMAS["ApplicationsResult"], label="ApplicationsResult")
    return JSONResponse(result, status_code=200)


async def _set_application_enabled(request: Request, enabled: bool) -> Response:
    service: ControlPlaneService = request.app.state.control_service
    service.check_rate()  # MAJOR-1
    secret = _extract_bearer(request)
    application_id = request.path_params["application_id"]
    result = service.set_application_enabled(secret, application_id, enabled, request_id=_request_id(request), rate_precharged=True)
    _check_response_shape(result, _SCHEMAS["ApplicationStateResult"], label="ApplicationStateResult")
    return JSONResponse(result, status_code=200)


@_endpoint
async def post_disable_application(request: Request) -> Response:
    return await _set_application_enabled(request, False)


@_endpoint
async def post_enable_application(request: Request) -> Response:
    return await _set_application_enabled(request, True)


@_endpoint
async def post_issue_credential(request: Request) -> Response:
    service: ControlPlaneService = request.app.state.control_service
    service.check_rate()  # MAJOR-1: before the body is even read -- see module header
    secret = _extract_bearer(request)
    body = await _read_json_object(request)
    _check_object_shape(body, _SCHEMAS["CredentialIssueRequest"], label="CredentialIssueRequest")
    result = service.issue_credential(secret, body.get("application_id"), body.get("role"), request_id=_request_id(request), rate_precharged=True)
    _check_response_shape(result, _SCHEMAS["CredentialIssued"], label="CredentialIssued")
    return JSONResponse(result, status_code=200)


@_endpoint
async def get_list_credentials(request: Request) -> Response:
    service: ControlPlaneService = request.app.state.control_service
    service.check_rate()  # MAJOR-1
    secret = _extract_bearer(request)
    result = service.list_credentials(secret, request_id=_request_id(request), rate_precharged=True)
    _check_response_shape(result, _SCHEMAS["CredentialsResult"], label="CredentialsResult")
    return JSONResponse(result, status_code=200)


@_endpoint
async def post_rotate_credential(request: Request) -> Response:
    service: ControlPlaneService = request.app.state.control_service
    service.check_rate()  # MAJOR-1
    secret = _extract_bearer(request)
    credential_id = request.path_params["credential_id"]
    result = service.rotate_credential(secret, credential_id, request_id=_request_id(request), rate_precharged=True)
    _check_response_shape(result, _SCHEMAS["CredentialRotated"], label="CredentialRotated")
    return JSONResponse(result, status_code=200)


@_endpoint
async def post_revoke_credential(request: Request) -> Response:
    service: ControlPlaneService = request.app.state.control_service
    service.check_rate()  # MAJOR-1: before the body is even read -- see module header
    secret = _extract_bearer(request)
    credential_id = request.path_params["credential_id"]
    body = await _read_json_object_or_empty(request)
    _check_object_shape(body, _SCHEMAS["CredentialRevokeRequest"], label="CredentialRevokeRequest")
    result = service.revoke_credential(
        secret, credential_id, destructive=body.get("destructive"), confirmation=body.get("confirmation"), request_id=_request_id(request), rate_precharged=True
    )
    _check_response_shape(result, _SCHEMAS["CredentialStateResult"], label="CredentialStateResult")
    return JSONResponse(result, status_code=200)


async def _set_credential_enabled(request: Request, enabled: bool) -> Response:
    service: ControlPlaneService = request.app.state.control_service
    service.check_rate()  # MAJOR-1
    secret = _extract_bearer(request)
    credential_id = request.path_params["credential_id"]
    result = service.set_credential_enabled(secret, credential_id, enabled, request_id=_request_id(request), rate_precharged=True)
    _check_response_shape(result, _SCHEMAS["CredentialStateResult"], label="CredentialStateResult")
    return JSONResponse(result, status_code=200)


@_endpoint
async def post_disable_credential(request: Request) -> Response:
    return await _set_credential_enabled(request, False)


@_endpoint
async def post_enable_credential(request: Request) -> Response:
    return await _set_credential_enabled(request, True)


# --------------------------------------------------------------------------
# Phase 4 WP-2(b) (design D-5): `audit_query` -- two paths, ONE handler.
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


@_endpoint
async def post_audit_query(request: Request) -> Response:
    service: ControlPlaneService = request.app.state.control_service
    # `audit_requests_per_minute` -- its OWN window, charged before ANYTHING
    # else (D-5: "両パス専用の pre-auth 固定窓"), never `check_rate()`
    # (`control_requests_per_minute` is a DIFFERENT counter this handler
    # must never touch -- design M-8 / P4-D4 item 8: a high-frequency
    # audit poller must not be able to exhaust the window a break-glass
    # `revoke_credential` depends on).
    service.check_audit_rate()
    secret = _extract_bearer(request)
    # `AuditQueryRequest`'s own contract schema has no `required` entries
    # at all (every field optional) -- the same all-optional shape
    # `CredentialRevokeRequest` has, so an absent body is read the same way
    # (`_read_json_object_or_empty`, this module's own helper above).
    body = await _read_json_object_or_empty(request)
    _check_object_shape(body, _SCHEMAS["AuditQueryRequest"], label="AuditQueryRequest")
    result = service.audit_query(secret, body, request_id=_request_id(request), rate_precharged=True)
    _check_response_shape(result, _SCHEMAS["AuditResult"], label="AuditResult")
    return JSONResponse(result, status_code=200)


# --------------------------------------------------------------------------
# App assembly -- the contract's 11 `control_endpoints` plus `audit_query`'s
# own 2 paths (`/control/v1/audit/query` and its pre-1.4.0 alias `/v1/
# audit/query`, D-5), 13 routes total. `/v1/audit/query` is this route
# table's ONE deliberate `/v1/...`-shaped path (WP-4 test item 7's original
# "no data-plane path" rule now has this one named exception, not a
# silently weakened check -- `test_control_http.py::
# test_control_and_data_plane_route_tables_are_disjoint` asserts it by
# name); `http.py`'s own `_ROUTES` still contains no `/control` path at
# all, unchanged.
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
    # Phase 4 WP-2(b) (design D-5): registered unconditionally -- even when
    # AUDIT DSN is unset, so an unprovided `audit_query` answers `CAPABILITY_
    # UNSUPPORTED` after authenticating, never a bare 404 (D-5 M-4). Both
    # resolve to the SAME handler, `post_audit_query` (this module's own
    # docstring above explains the two-path rationale).
    Route("/control/v1/audit/query", post_audit_query, methods=["POST"]),
    Route("/v1/audit/query", post_audit_query, methods=["POST"]),
]


def create_control_app(control_service: ControlPlaneService, *, lifespan: Callable[[Starlette], AbstractAsyncContextManager[None]] | None = None) -> ASGIApp:
    """Build the ASGI application exposing `control_service` over the
    contract's `/control/v1` HTTP surface.

    R-1: independent of `http.py`'s `create_app` -- distinct `Starlette`
    instance, distinct route table, no shared handler/auth code (only the
    generic byte-bound/problem-response/shape-check *machinery* is reused,
    per this module's own header). `lifespan` has the exact same shape and
    default as `create_app`'s own parameter, for the same reason: `control_
    main.build_control_app` (WP-4, this same phase) needs an ASGI shutdown
    hook to release the Postgres store pools it constructs, and every
    existing/future caller that does not pass one (this file's own test
    suite) is unaffected by the parameter's mere existence.
    """
    app = Starlette(
        routes=_ROUTES,
        exception_handlers={
            StarletteHTTPException: _http_exception_handler,
            Exception: _unhandled_exception_handler,
        },
        lifespan=lifespan,
    )
    app.state.control_service = control_service
    # Phase 3.5 WP-4 (§4 "L4", single source): `control_service.limits` is
    # the exact `ControlPlaneLimits` instance this service enforces
    # internally and discovers through `capabilities()` -- never a second,
    # independently constructed `ResourceLimits()`.
    return RequestByteBoundMiddleware(app, control_service.limits)


__all__ = ["create_control_app"]
