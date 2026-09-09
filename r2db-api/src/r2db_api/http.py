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
from contextlib import AbstractAsyncContextManager
from importlib import resources
from typing import Any, Awaitable, Callable

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .auth import AuthContext
from .errors import FoundationError, fail, observed_type_of, violation
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
# drift apart.
#
# Phase 6 WP-0 (peer-symmetry ruling, 2026-09-04): a repository-relative
# fallback (`Path(__file__).resolve()` walked three parent directories up
# to `"spec"`) used to sit here for a repository checkout that had not
# synced the packaged copy. Removed -- this package's own byte-identical
# test already makes
# staleness between the two copies impossible, so the fallback existed
# only to paper over an out-of-sync checkout, the same known coupling
# design D-4(b) closes for MitateDB-api's own `mitatedb_api.http`. Running
# from a source checkout (this repository's own tests included) still
# works: `resources.files("r2db_api.contract")` resolves directly against
# `src/r2db_api/contract/` on disk in that case, no install step required.
# --------------------------------------------------------------------------

_PACKAGED_CONTRACT_PATH = "data-service-api.v1.json"


def _load_contract_text() -> str:
    return resources.files("r2db_api.contract").joinpath(_PACKAGED_CONTRACT_PATH).read_text()


_CONTRACT = json.loads(_load_contract_text())
_SCHEMAS = _CONTRACT["schemas"]
_DEFINITIONS = _CONTRACT["definitions"]


def _schema_property_type_name(schema: dict[str, Any], key: str) -> str | None:
    """The `declared_type` word (D-3 (2): field-type vocabulary, or the
    JSON type this contract's own request schema names) for a `schema`'s
    `properties[key].type` -- a bare string (`"string"`) or a `[type,
    "null"]` pair (this contract's own optional-property convention). Falls
    back to `None` (key omitted from the resulting `details`) when the
    property schema names no single JSON type -- WP-2e never guesses.
    """
    prop = schema.get("properties", {}).get(key)
    if not isinstance(prop, dict):
        return None
    raw = prop.get("type")
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        non_null = [t for t in raw if t != "null"]
        if len(non_null) == 1 and isinstance(non_null[0], str):
            return non_null[0]
    return None


def _check_object_shape(value: Any, schema: dict[str, Any], *, label: str, own_path: str | None = None) -> dict[str, Any]:
    """Reject unknown top-level fields and missing required fields per `schema`.

    This is the boundary that guarantees a client-supplied `application_id`,
    `role`, `database`, or `schema` field in a request body is rejected
    outright rather than silently accepted -- the contract's
    `structured_operations.scope` note and SI-06 require that such fields
    never be authority, and `additionalProperties: false` on these schemas
    means they are not even valid input. Deep validation of nested
    values (predicates, mutations, identifiers, operators) is intentionally
    left to `structured.py`, which already owns it.

    Contract 1.7.0 (D-3, WP-2e): every denial here is `violated_
    declaration: request_schema` (`errors.details_vocabulary`) -- `own_path`
    is this VALUE's own request-internal path (`None` for the request body
    itself; `"page"` for the nested `QueryRequest.page` object) and a
    child key's own path is `own_path + "/" + key"` (or bare `key` at the
    top level). `field` is carried only when the violation is attributable
    to exactly ONE position (D-3 (4)): a lone unknown field, a lone missing
    required field, or `value` itself failing the object check. `declared_
    type`/`observed_type` are carried only for a VALUE-type violation
    (`value` itself is not an object, or a required field is entirely
    absent) -- never for an unknown-field denial (D-3 (4): the contract's
    request schema names no type for a field it does not know).
    """
    if not isinstance(value, dict):
        fail(
            "VALIDATION_FAILED", f"{label} must be an object.",
            details=violation("request_schema", field=own_path, declared_type="object", observed_type=observed_type_of(value)),
        )
    allowed = set(schema.get("properties", {}))
    extra = set(value) - allowed
    if extra:
        sole = next(iter(extra)) if len(extra) == 1 else None
        field = (f"{own_path}/{sole}" if own_path else sole) if sole is not None else None
        fail("VALIDATION_FAILED", f"{label} contains unsupported fields.", details=violation("request_schema", field=field))
    missing = set(schema.get("required", [])) - set(value)
    if missing:
        sole = next(iter(missing)) if len(missing) == 1 else None
        if sole is not None:
            field = f"{own_path}/{sole}" if own_path else sole
            fail(
                "VALIDATION_FAILED", f"{label} is missing required fields.",
                details=violation("request_schema", field=field, declared_type=_schema_property_type_name(schema, sole), observed_type="absent"),
            )
        fail("VALIDATION_FAILED", f"{label} is missing required fields.", details=violation("request_schema"))
    # WP-2e rework (audit-wp2e.md I-4, ruling L-4/V-6 (iii)): leg (iii) --
    # a property that IS present (so neither the unknown-field nor the
    # missing-field leg above ever sees it) but whose VALUE's JSON type
    # does not match `schema`'s own declared type for it. Before this leg
    # existed, a request like `{"where": "not-a-list"}` fell all the way
    # through to `service.py`'s own bare `fail("VALIDATION_FAILED", ...,
    # details={})` (the exact I-4 finding) -- this leg now catches it here
    # instead, with the full 4-key form. `_schema_property_type_name`
    # already strips this contract's own `[type, "null"]` optional-
    # property convention down to the single non-null word for `declared_
    # type`'s own value; the type-membership check below instead compares
    # against the FULL raw type list (`null` included when the property
    # allows it) so an explicit `null` on an optional property is never
    # mistaken for a type violation.
    for key, raw_value in value.items():
        if key not in allowed:
            continue  # unknown key -- already rejected by the leg above
        prop = schema.get("properties", {}).get(key)
        raw_type = prop.get("type") if isinstance(prop, dict) else None
        if isinstance(raw_type, str):
            allowed_types = {raw_type}
        elif isinstance(raw_type, list):
            allowed_types = {t for t in raw_type if isinstance(t, str)}
        else:
            allowed_types = None
        if not allowed_types:
            continue  # property names no single JSON type -- never guessed (WP-2e)
        observed_type = observed_type_of(raw_value)
        if observed_type in allowed_types:
            continue
        field = f"{own_path}/{key}" if own_path else key
        fail(
            "VALIDATION_FAILED", f"{label} has a field of the wrong type.",
            details=violation("request_schema", field=field, declared_type=_schema_property_type_name(schema, key), observed_type=observed_type),
        )
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
                details={"resource": "request_bytes", "limit_class": "request_bytes", "limit": bound},
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
        fail("VALIDATION_FAILED", "Request body must be valid JSON.", details=violation("request_schema"))
        raise  # unreachable; fail() always raises
    if not isinstance(payload, dict):
        fail("VALIDATION_FAILED", "Request body must be a JSON object.", details=violation("request_schema"))
    return payload


# --------------------------------------------------------------------------
# Endpoints (spec/data-service-api.v1.json -> "endpoints").
#
# Phase 10 WP-8a (design D-8 (3)): every synchronous section below --
# `_authenticate` (a real psycopg round trip through `PostgresCredentialStore`
# in the production composition, `postgres.py`'s `_RolePool`/
# `SharedPoolManager`) and each `DataService` call (the query/mutate/schema
# execution itself) -- runs via `starlette.concurrency.run_in_threadpool`,
# never directly on the event-loop thread. The one `await` each handler
# below performs for its own request body (`_read_json_object`) is left
# untouched on the loop; delegation begins only once that read has already
# completed, never around it, so a handler whose contract shape needs the
# body first (`post_query`/`post_mutate`/`post_schema`) offloads in two
# separate calls -- one for `_authenticate` (which this contract's own
# "authenticate before validating the body" ordering places BEFORE the
# read), one for the shape-check + `DataService` call (placed after) --
# rather than reordering authentication behind body parsing. A handler with
# no body to read (`get_capabilities`/`get_catalog`/
# `post_cross_entity_mutate`/`post_audit_query`) offloads the whole
# authenticate-then-call sequence in one `run_in_threadpool` call, since
# there is no `await` in between to delegate around.
#
# `run_in_threadpool` draws from anyio's default worker-thread limiter
# (default capacity 40, `anyio.to_thread.current_default_thread_limiter().
# total_tokens`). Phase 10 WP-8a review F-7 (supervisor ruling
# 2026-09-08): capacity 40 does NOT bound this delegation's own
# worker-thread demand at `ResourceLimits.concurrency` (32) simultaneous
# requests -- `_authenticate` occupies a worker thread BEFORE `DataService.
# _slot` ever takes a concurrency slot (so demand at the declared ceiling
# is "32 in-flight requests + however many authentications are
# concurrently in progress", not simply 32), and the limiter itself is one
# event-loop-wide resource shared with every other `run_in_threadpool`
# caller in this process, not one dedicated to this module. What IS true:
# exhausting it does not deadlock -- a caller unable to get a worker thread
# right away waits for one to free up (the same fail-open-to-latency,
# never-a-hang shape `_RolePool`'s own `acquire_timeout` already has), it
# does not hang forever or crash the process.
# --------------------------------------------------------------------------


@_endpoint
async def get_capabilities(request: Request) -> Response:
    service: DataService = request.app.state.service

    def _run() -> dict[str, Any]:
        context = _authenticate(request, service)
        return service.capabilities(context)

    document = await run_in_threadpool(_run)
    return JSONResponse(document, status_code=200)


@_endpoint
async def post_query(request: Request) -> Response:
    service: DataService = request.app.state.service
    context = await run_in_threadpool(_authenticate, request, service)
    entity = request.path_params["entity"]
    body = await _read_json_object(request)

    def _run() -> "QueryPage":
        _check_object_shape(body, _SCHEMAS["QueryRequest"], label="QueryRequest")
        # CCR-13 WP-4/WP-5: `order_by`/`page.cursor` are delegated to
        # `DataService.query_page`, which passes them to the underlying cell
        # (`structured.py`'s shared `_resolve_order_by`/`_decode_cursor`
        # validate the shapes).
        kwargs: dict[str, Any] = {"select": body.get("select"), "where": body.get("where"), "order_by": body.get("order_by")}
        page = body.get("page")
        if page is not None:
            _check_object_shape(page, _DEFINITIONS["Page"], label="page", own_path="page")
            if "size" in page:
                kwargs["page_size"] = page["size"]
            if "cursor" in page:
                kwargs["cursor"] = page["cursor"]
        # Contract 1.7.0 (D-6, WP-2d): `budget` is real as of this commit
        # (`capabilities().request_budget` is `enabled`) -- passed through to
        # `query_page`, which narrows the deployed bound by it.
        return service.query_page(context, entity, request_id=_request_id(request), budget=body.get("budget"), **kwargs)

    result = await run_in_threadpool(_run)
    # CCR-13 WP-5: `revisions` (index-aligned with `items`) now reaches the
    # response -- `revision_preconditions` is declared `enabled`. Contract
    # 1.7.0 (D-7, WP-2e): `request_id` -- `result.request_id`, the SAME
    # value `query_page` handed `_query_outcome` for its own audit event;
    # this layer never re-derives it.
    return JSONResponse(
        {"items": result.items, "next_page": result.next_page, "revisions": result.revisions, "request_id": result.request_id},
        status_code=200,
    )


@_endpoint
async def post_mutate(request: Request) -> Response:
    service: DataService = request.app.state.service
    context = await run_in_threadpool(_authenticate, request, service)
    entity = request.path_params["entity"]
    body = await _read_json_object(request)

    def _run() -> "MutationResult":
        _check_object_shape(body, _SCHEMAS["MutationRequest"], label="MutationRequest")
        # G-1 (`{scratchpad}/rulings-r4.md` addendum): a `plan`'s digest
        # commits to the request object exactly as received -- a body that
        # omits `transaction` must digest differently from one that spells
        # out `transaction: "atomic"` explicitly, even though both behave
        # identically. So `transaction` is passed to `mutate_result` ONLY
        # when the body actually carried the key (mirroring how the
        # in-process port already omits its own `transaction` kwarg when
        # the caller didn't supply one) -- never resolved to `"atomic"`
        # here first.
        mutate_kwargs: dict[str, Any] = {}
        if "transaction" in body:
            transaction = body["transaction"]
            if transaction not in {"atomic", "best_effort"}:
                fail("VALIDATION_FAILED", "Transaction mode is not supported.", details=violation("request_schema", field="transaction"))
            mutate_kwargs["transaction"] = transaction
        # Contract 1.7.0 (D-4/D-5/D-6, WP-2b/WP-2c/WP-2d): `dry_run`/`plan`/
        # `budget`/`idempotency_key` are all real as of this commit
        # (`capabilities().dry_run`/`.request_budget`/`.idempotency` are all
        # `enabled`) -- passed through to `mutate_result`, which gives each
        # its full effect.
        return service.mutate_result(
            context,
            entity,
            body.get("operations"),
            request_id=_request_id(request),
            dry_run=body.get("dry_run", False),
            plan=body.get("plan"),
            budget=body.get("budget"),
            idempotency_key=body.get("idempotency_key"),
            **mutate_kwargs,
        )

    result = await run_in_threadpool(_run)
    # CCR-13 WP-5: `assigned_addresses` now reaches the response, in
    # operation order (insert, and insert-resolved upsert, only) -- the
    # per-entity endpoint's own elements never carry an `entity` key
    # (contract: only the cross-entity endpoint's elements do). Contract
    # 1.7.0 (D-4, WP-2b): `committed` now reports the real decision
    # (`result.committed` -- unconditionally `True` for every request that
    # reaches this point without `dry_run`, exactly the value this
    # response hardcoded before this version, so a real apply's response
    # is unchanged); `plan` is included only when the result actually
    # carries one (a dry-run response, D-4 (3)). Review round F-6
    # (`{scratchpad}/rulings-r4.md`): `assigned_addresses` is omitted
    # (the key itself, not merely emptied) on a `dry_run` response --
    # `result.assigned_addresses` is `None` exactly then -- matching the
    # contract's "does not carry" wording and `descriptor`/`plan`'s own
    # present-only-when-settled treatment.
    # Contract 1.7.0 (D-7, WP-2e): `request_id` -- `result.request_id`,
    # already the ORIGINAL execution's own value on an idempotency replay
    # (`MutationResult.request_id`'s own comment) -- this layer never
    # regenerates it.
    response: dict[str, Any] = {"committed": result.committed, "affected": result.affected, "request_id": result.request_id}
    if result.assigned_addresses is not None:
        response["assigned_addresses"] = result.assigned_addresses
    if result.plan is not None:
        response["plan"] = result.plan
    return JSONResponse(response, status_code=200)


@_endpoint
async def get_catalog(request: Request) -> Response:
    service: DataService = request.app.state.service

    def _run() -> dict[str, Any]:
        context = _authenticate(request, service)
        return service.catalog(context, request_id=_request_id(request))

    document = await run_in_threadpool(_run)
    return JSONResponse(document, status_code=200)


@_endpoint
async def post_schema(request: Request) -> Response:
    service: DataService = request.app.state.service
    context = await run_in_threadpool(_authenticate, request, service)
    body = await _read_json_object(request)

    def _run() -> "SchemaOutcome":
        _check_object_shape(body, _SCHEMAS["SchemaOperationRequest"], label="SchemaOperationRequest")
        return service.schema(context, body, request_id=_request_id(request))

    outcome = await run_in_threadpool(_run)
    # Contract 1.7.0 (D-4, WP-2b): `service.schema` always returns
    # `SchemaOutcome` (review round F-8, `{scratchpad}/rulings-r4.md`
    # unified this away from a bare-`int`-or-`SchemaOutcome` dual shape).
    # `descriptor`/`plan` are included only when actually present (a
    # dry-run response, D-4 (3); a real response's shape stays unchanged
    # besides `committed`, which is unconditionally `True` for a real
    # apply that reaches this point).
    # Contract 1.7.0 (D-7, WP-2e): `request_id` -- `outcome.request_id`,
    # already the ORIGINAL execution's own value on an idempotency replay.
    response: dict[str, Any] = {"committed": outcome.committed, "revision": str(outcome.revision), "request_id": outcome.request_id}
    if outcome.descriptor is not None:
        response["descriptor"] = outcome.descriptor
    if outcome.plan is not None:
        response["plan"] = outcome.plan
    return JSONResponse(response, status_code=200)


@_endpoint
async def post_cross_entity_mutate(request: Request) -> Response:
    service: DataService = request.app.state.service
    # Contract 1.1.0 (CCR-15): `POST /v1/data/mutations` defines the shape
    # of one atomic mutation unit across multiple entities
    # (`ScopedMutationRequest`/`ScopedMutation`), availability declared via
    # the `cross_entity_mutation` capability. This foundation declares that
    # capability `unavailable` (service.py's `capabilities()`) and has no
    # cross-entity execution path on `DataService` at all -- this handler
    # exists only so the route itself resolves (distinctly from
    # `POST /v1/data/{entity}/mutations`, see `tests/test_http.py`'s
    # routing-collision test) and responds with the correct, contract-
    # defined failure shape, never a 404/405 that would look like the
    # endpoint does not exist per the contract at all.
    #
    # Same "authenticate first, then refuse" shape as `post_audit_query`
    # below: an unauthenticated/invalid/revoked credential still gets
    # AUTH_* first, exactly like every executing endpoint, rather than a
    # capability answer that would distinguish "endpoint exists but
    # unsupported" from "you are not authenticated" for a caller who is
    # not authenticated at all. The request body is deliberately never
    # read -- there is nothing to validate for an operation this
    # foundation never executes. `deny_unsupported` (not a bare `fail()`)
    # so this stub still passes through `_slot`'s rate/concurrency
    # accounting and emits a denial audit event, exactly like every
    # executing endpoint (review R12) -- a caller cannot spend requests
    # against this stub for free just because it never executes anything.
    def _run() -> None:
        context = _authenticate(request, service)
        service.deny_unsupported(
            context,
            operation="cross_entity_mutate",
            message="Cross-entity atomic mutation is not available; this foundation does not implement the cross_entity_mutation capability.",
            request_id=_request_id(request),
        )

    await run_in_threadpool(_run)
    raise AssertionError("unreachable")


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
    # `deny_unsupported`, not a bare `fail()`, for the same reason as
    # `post_cross_entity_mutate` above (review R12): this stub still counts
    # against the caller's rate/concurrency budget and emits a denial audit
    # event.
    def _run() -> None:
        context = _authenticate(request, service)
        service.deny_unsupported(
            context,
            operation="audit_query",
            message="Audit evidence query requires separately authenticated control/audit authority "
            "that this foundation does not expose over the application-facing HTTP surface.",
            request_id=_request_id(request),
        )

    await run_in_threadpool(_run)
    raise AssertionError("unreachable")


# --------------------------------------------------------------------------
# App assembly.
# --------------------------------------------------------------------------

_ROUTES = [
    Route("/v1/capabilities", get_capabilities, methods=["GET"]),
    Route("/v1/data/{entity}/query", post_query, methods=["POST"]),
    Route("/v1/data/{entity}/mutations", post_mutate, methods=["POST"]),
    # Fixed 3-segment path, distinct from the 4-segment `/v1/data/{entity}/
    # mutations` above at the routing level regardless of declaration order
    # -- an entity literally named "mutations" resolves to
    # `/v1/data/mutations/mutations` (4 segments, `post_mutate`, `entity=
    # "mutations"`), never to this route. `tests/test_http.py` asserts both
    # directions.
    Route("/v1/data/mutations", post_cross_entity_mutate, methods=["POST"]),
    Route("/v1/catalog", get_catalog, methods=["GET"]),
    Route("/v1/schema/operations", post_schema, methods=["POST"]),
    Route("/v1/audit/query", post_audit_query, methods=["POST"]),
]


def create_app(service: DataService, *, lifespan: Callable[[Starlette], AbstractAsyncContextManager[None]] | None = None) -> ASGIApp:
    """Build the ASGI application exposing `service` over the contract's HTTP surface.

    The returned callable is `RequestByteBoundMiddleware` wrapping a
    Starlette application, so SI-08's request-byte bound is enforced before
    any Starlette routing or body parsing runs.

    `lifespan` is optional and defaults to Starlette's own no-op lifespan,
    same as before this parameter existed -- every existing caller
    (`tests/test_http.py`, both conformance adapters) is unaffected. It
    exists for `r2db_api.main`'s composition root (design docs/design/
    R2DB_CREDENTIAL_PERSISTENCE_AND_COMPOSITION_ROOT_V1.md, P2-D5), which
    needs an ASGI shutdown hook to release `PostgresCell`'s shared pool
    manager and the platform credential store's own pool. An ASGI
    `"lifespan"`-scope event bypasses `RequestByteBoundMiddleware` entirely
    (it only intercepts `scope["type"] == "http"`, see that class'
    `__call__` above), so wiring a lifespan into the wrapped Starlette
    application here is sufficient for uvicorn's lifespan protocol to reach
    it with no other change to this middleware.
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
    return RequestByteBoundMiddleware(app, service.limits)
