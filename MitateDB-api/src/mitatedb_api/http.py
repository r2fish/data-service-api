"""
ASGI HTTP boundary over the MitateDB-api foundation (docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md v1.2 R-5).

This module owns the HTTP surface only -- authority, structured-operation validation, and value-domain enforcement all stay in `cell.py`/`backend_sqlite.py`/`backend_postgres.py`/`auth.py`/`credential_store_postgres.py` (R-3's own seam split); this file only translates the contract's endpoint table (`spec/data-service-api.v1.json`) onto a `HttpService` (below) and maps outcomes to `application/problem+json`.

Independent implementation (R-2's closing paragraph: no code sharing between peers): this is not a port of `r2db_api.http`. It follows the same GENERAL shape (Starlette ASGI app, contract-driven top-level shape checking, an ASGI-receive-loop byte-bound middleware) because both peers share the same execution-environment parts by design decision (D-B), not because either file's own code was copied.

Request shapes are not re-declared with a second (pydantic) type system: `spec/data-service-api.v1.json` is read at import time and used as the single source of truth for which top-level request fields are accepted.

History: CH-0182
"""
from __future__ import annotations

from contextlib import contextmanager
import json
from importlib import resources
from typing import Any, Awaitable, Callable, Iterator, Mapping

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
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
                     StorageConfigurationError, ValidationError,
                     observed_type_of, violation)

PROBLEM_CONTENT_TYPE = "application/problem+json"

# -------------------------------------------------------------------------- Contract as the single source of truth for request shapes (Phase 6 WP-0, design D-4(b)).
#
# `spec/data-service-api.v1.json` in the common repository remains the authored source of truth (CLAUDE.md: this package must not become the implicit owner of the public contract). What ships inside this distribution is a byte-identical packaged *copy* (wired in as package data in `pyproject.toml`), loaded via `importlib.resources` so a unit installed or copied onto the VPS without the sibling `spec/` checkout still imports -- this replaces the prior repository-relative lookup (`Path(__file__).resolve()` walked three parent directories up to `"spec"`), which broke the moment this package was installed/copied anywhere that checkout was not a sibling three directories up (the known coupling design D-4(b) closes). `r2db_api.http`'s own loader took the identical repository-relative form as a FALLBACK behind its packaged copy (never this package's own primary path, which had no packaged copy to fall back to before this WP); the supervisor's own WP-0 peer-symmetry ruling removed that fallback too, so both peers now resolve the contract exclusively through `importlib.resources` against their own packaged copy, no fallback on either side. `tests/test_http.py::test_packaged_contract_copy_is_byte_identical_to_spec_source_of_truth` asserts the packaged copy never silently drifts from `spec/`. --------------------------------------------------------------------------
# history: CH-0183

_CONTRACT_PATH = resources.files("mitatedb_api.contract").joinpath("data-service-api.v1.json")
_CONTRACT = json.loads(_CONTRACT_PATH.read_text())
_SCHEMAS = _CONTRACT["schemas"]
_DEFINITIONS = _CONTRACT["definitions"]

# -------------------------------------------------------------------------- HTTP status <-> contract error code (m-12: cross-peer status agreement is tracked conformance evidence, contract errors.http_status_note). Every code this peer can actually emit is listed here, mapped to the SAME status r2db-api's own call sites use for that code (grep'd from r2db-api/src/r2db_api/*.py's own `fail(...)`/`FoundationError(...)` call sites -- r2db-api itself is not imported or modified, only read for this cross-check per the task brief). No divergence was needed: every code below agrees with r2db-api's own mapping. This peer simply never emits several contract codes at all (AUTH_REVOKED, APPLICATION_DISABLED, SCOPE_MISMATCH, ATOMICITY_FAILED, IDENTIFIER_INVALID --/ `credential_store_postgres.py` fold "revoked"/"disabled" into a single `AuthenticationError` -> AUTH_INVALID, and `identifiers.py` raises the same `ValidationError` -> VALIDATION_FAILED for a malformed identifier as for any other malformed shape); that is a pre-existing fact about this peer's own error vocabulary, not something WP-3 narrows, and is reported to the requester as a known divergence (not a status mismatch -- there is nothing to compare a peer never emits).
#
# Phase 9 WP-3b (design, 追補 2 S-h): PRECONDITION_FAILED is no longer in that "never emits" set -- `errors.PreconditionFailedError` (a stale `plan` token) is this peer's first real source of it, mapped to 412 -- the SAME status `r2db-api/src/r2db_api/structured.py`/`postgres.py` already use for their own (row-level) `PRECONDITION_FAILED` `fail(..., status=412)` call sites (cross-peer status agreement m-12).
# history: CH-0184
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

# `errors.FoundationError` subclass -> contract code, evaluated in order (mirrors `conformance_adapter_mitatedb.py::_CLASSIFY_ORDER`, extended with `StorageConfigurationError` -- unreachable on the in-process adapter's own SQLite backend, real on this HTTP composition's PostgreSQL backend/credential store -- mapped to `SERVICE_UNAVAILABLE` per that class' own documented proposal). Phase 4 (design PHASE4_DURABLE_AUDIT_SINK_V1.md D-2/D-3): `AuditSinkUnavailable` is likewise mapped to `SERVICE_UNAVAILABLE` -- a durable-audit-sink failure on a fail-closed-class operation or denial, distinct from both `StorageConfigurationError` (a permanent DATA-backend privilege defect) and `AuthorizationStateUnavailable` (the credential store's own unreachability). Listed explicitly here (not left to the exhaustive-by-construction fallback in `_classify` below) so that fallback's own "pragma: no cover" comment stays true.
# history: CH-0185
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
    # Phase 9 WP-3b (design, 追補 2 S-h): a stale `plan` -- a real, present precondition denial, checked at the `destructive_confirmation.evaluation_order` precondition stage (after confirmation validity) -- classifies before `ConflictError`/`NotFoundError` here, matching this table's own existing convention of listing the more specific denial first (`DestructiveConfirmationRequired` already precedes `ConflictError` immediately above); no ordering ambiguity arises in practice, since no call site ever raises more than one of these for a single request.
    # history: CH-0186
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
    # SI-10: never surface `str(exc)`/SQL/connection details/exception internals on the wire. Every code below gets a fixed, static, non-interpolated message; the only per-request data that ever reaches a response body is `details`, which is itself already constrained to the safe, structured shape `errors.ResourceLimitError`/`errors.DestructiveConfirmationRequired` publish (`limit_class` / the four declare-and-echo keys) -- never the raw exception message.
    #
    # Q4 rework (design §3.8's own "F-12だけは...API応答として利用者に届く"): `PlatformUpgradePending` is the ONE exception this exemption applies to -- `isinstance` (never the classified `code`, which is the same `SERVICE_UNAVAILABLE` every OTHER `StorageConfigurationError` also classifies to) narrows to exactly this subclass, so this stays a one-exception carve-out, not a hole every current or future `StorageConfigurationError` site falls through. `platform_upgrades._f12_message`'s own construction already excludes DSN/credential/internal-hostname/declared-value text -- only the missing upgrade numbers and the next `ops` command appear -- so `str(exc)` is safe to surface verbatim here.
    # history: CH-0187
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
            # m-6 (independent): drain the REST of the client's body before answering, discarding every remaining chunk, so no unread bytes are ever left on the connection. Harmless under `httpx.ASGITransport` (this repository's own tests, and both conformance adapters, drive this middleware exactly that way -- an in-process transport with no real socket to leave dangling), but load-bearing under a real ASGI server (uvicorn): leaving unread bytes after sending a response risks the server treating them as the start of the NEXT request on a keep-alive connection, or having to reset the connection outright either way. Only drains when the chunk that tipped the limit itself declared `more_body: true` -- calling `receive()` again after a chunk that already declared the body complete is not meaningful ASGI protocol use and is skipped entirely.
            # history: CH-0188
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


def _schema_property_type_name(schema: Mapping[str, Any], key: str) -> "str | None":
    """The `declared_type` word (design D-3 (2): field-type vocabulary,
    or the JSON type this contract's own request schema names) for a
    `schema`'s `properties[key].type` -- a bare string (`"string"`) or a
    `[type, "null"]` pair (this contract's own optional-property
    convention). Falls back to `None` (key omitted from the resulting
    `details`) when the property schema names no single JSON type --
    mirrors r2db-api's own `http._schema_property_type_name`."""
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


def _schema_property_type_mismatch(value: Any, prop: Any) -> bool:
    """
    WP-3e rework T2 (追補): does `value`'s own JSON type fail to match `prop["type"]` (a bare string, or this contract's `[type, "null"]` union convention -- `_schema_property_type_name`'s own sibling reader)? A property schema naming no single JSON type at all (a `$ref` object like `QueryRequest.page`, or an `enum`-only scalar like `SchemaOperationRequest.operation`) never mismatches here -- this leg is deliberately confined to a JSON TYPE violation, never an enum-membership or nested-shape one (those stay exactly where they already lived, downstream of this shape layer).

    History: CH-0189
    """
    if not isinstance(prop, dict):
        return False
    raw = prop.get("type")
    if isinstance(raw, str):
        allowed = {raw}
    elif isinstance(raw, list):
        allowed = {t for t in raw if isinstance(t, str)}
    else:
        return False
    if not allowed:
        return False
    return observed_type_of(value) not in allowed


def _check_object_shape(
    value: Any, schema: Mapping[str, Any], *, label: str, own_path: "str | None" = None,
) -> Mapping[str, Any]:
    """
    Reject unknown top-level fields and missing required fields per `schema`.

    Phase 9 WP-3e: every denial here is `violated_declaration: request_schema` (`errors.details_vocabulary`) -- mirrors r2db-api's own `http._check_object_shape` (task brief: "同型に揃え る"). `own_path` is this VALUE's own request-internal path (`None` for the request body itself; `"page"` for the nested `QueryRequest.page` object for one batch item) and a child key's own path is `own_path + "/" + key` (or the bare `key` at the top level). `field` is carried only when the violation is attributable to exactly ONE position: a lone unknown field, a lone missing required field, or `value` itself failing the object check. `declared_type`/`observed_type` are carried only for a VALUE-type violation (`value` itself is not an object, or a required field is entirely absent) -- never for an unknown-field denial (D-3 (4): the contract's request schema names no type for a field it does not know).

    History: CH-0190
    """
    if not isinstance(value, dict):
        raise ValidationError(
            f"{label} must be an object",
            details=violation(
                "request_schema", field=own_path, declared_type="object", observed_type=observed_type_of(value),
            ),
        )
    allowed = set(schema.get("properties", {}))
    extra = set(value) - allowed
    if extra:
        sole = next(iter(extra)) if len(extra) == 1 else None
        field = (f"{own_path}/{sole}" if own_path else sole) if sole is not None else None
        raise ValidationError(
            f"{label} contains unsupported fields: {sorted(extra)}",
            details=violation("request_schema", field=field),
        )
    missing = set(schema.get("required", [])) - set(value)
    if missing:
        sole = next(iter(missing)) if len(missing) == 1 else None
        if sole is not None:
            field = f"{own_path}/{sole}" if own_path else sole
            raise ValidationError(
                f"{label} is missing required fields: {sorted(missing)}",
                details=violation(
                    "request_schema", field=field,
                    declared_type=_schema_property_type_name(schema, sole), observed_type="absent",
                ),
            )
        raise ValidationError(
            f"{label} is missing required fields: {sorted(missing)}",
            details=violation("request_schema"),
        )
    # WP-3e rework T2 (追補): the leg this function used to lack -- a key that IS declared by `schema` and IS present in `value`, whose own VALUE's JSON type does not match what `schema` declares for it (design D-3 (2)/(4)'s own "値の型の違反のときだけ型対" rule, V-6 applied to this shape layer, not only to `cell.py`'s downstream choke points). Checked in a stable (sorted) key order so a request violating more than one property's type still reports the SAME one deterministically. `missing`-before-`value` (checked above "検査順序は欠落検査 -> 値検査") already guarantees every key this loop inspects is genuinely present, never `absent`. Before this leg existed, a request like `{"select": "abc"}` sailed through this function unchecked (a known JSON type property carrying the WRONG JSON type is not "unknown" and not "missing") and reached a later choke point with no `details` at all, or -- worse, `values: "x"`, `dict("x")` -- an unhandled exception before any `ValidationError` was ever raised.
    # history: CH-0191
    for key in sorted(value):
        prop = schema.get("properties", {}).get(key)
        if _schema_property_type_mismatch(value[key], prop):
            field = f"{own_path}/{key}" if own_path else key
            raise ValidationError(
                f"{label}.{key} has the wrong type",
                details=violation(
                    "request_schema", field=field,
                    declared_type=_schema_property_type_name(schema, key),
                    observed_type=observed_type_of(value[key]),
                ),
            )
    return value


def _deny_provisional_field(field_name: str) -> None:
    """
    Contract 1.7.0 provisional gate (design docs/design/PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md §3; work order docs/work-orders/WORK_ORDER_PHASE9_CONTRACT_170_V1.md §2): `_check_object_shape` above now accepts `dry_run`/`plan`/`budget`/`enum`/`nullable`/`field_constraints`/`SchemaOperationRequest.idempotency_key` (the packaged contract copy is already 1.7.0). This peer's own `constraint_declarations` capability flipped to `enabled` in the WP-3a commit (`enum`/`nullable`/`field_constraints` removed from `_PROVISIONAL_UNSUPPORTED_*_FIELDS` below, same commit), and `dry_run` flips to `enabled` in THIS commit (`dry_run`/`plan` removed from `_PROVISIONAL_UNSUPPORTED_*_FIELDS` below, same commit as `cell.py`'s own real dry_run/plan behavior, P-3) -- `budget`/`idempotency_key` remain `unavailable`, so accepting either of THOSE and silently ignoring it would still be a P-3 violation (declaration says `unavailable`, behavior accepts the field).

    Phase 9 WP-3e: `details` is now passed through `CapabilityError.__init__` itself -- the attribute-assignment escape hatch this function's own pre-WP-3e docstring described (`err.details = {...}` after construction) is gone. Every 1.7.0 capability this gate ever covered is `enabled` as of this WP (`_PROVISIONAL_UNSUPPORTED_*_FIELDS` below are all empty tuples), so this function currently has no reachable call site -- left in place, undeleted, as the standing mechanism the next provisional capability would reuse (mirrors `cell.py`'s identical in-process counterpart) (in `provisional_gate.py`). `_problem_for_exception` already surfaces any `getattr(exc, "details", None)` regardless of how it was set.

    History: CH-0192
    """
    raise CapabilityError(
        f"{field_name} is not supported by this peer",
        details={"violated_declaration": "capability", "field": field_name},
    )


# Phase 9 WP-3b: `dry_run`/`plan` removed -- `post_mutate`/`post_cross_
# entity_mutate` below now pass both through to `session.transact()` for
# real instead of gating them here. Phase 9 WP-3c/WP-3d: `idempotency_
# key`/`budget` removed too -- both now pass through for real, same
# commit as `idempotency`/`request_budget` flipping to `enabled`
# (`cell.py::ApplicationRuntime.capabilities`).
_PROVISIONAL_UNSUPPORTED_MUTATION_REQUEST_FIELDS = ()
_PROVISIONAL_UNSUPPORTED_QUERY_REQUEST_FIELDS = ()
# Phase 9 WP-3a (design docs/design/PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md): `field_constraints`/`enum`/`nullable` removed from this gate -- same commit as `constraint_declarations` flipping to `enabled` below (`cell.py::ApplicationRuntime.capabilities`) and the real enforcement each governs. Phase 9 WP-3b: `dry_run`/`plan` removed too -- same commit as `dry_run` flipping to `enabled` and `post_schema` below passing both through to `create_entity`/`add_field`/`alter_field` for real. Phase 9 WP-3c/WP-3d: `idempotency_key`/`budget` removed too -- same reasoning as the mutation/query gates immediately above.
# history: CH-0193
_PROVISIONAL_UNSUPPORTED_SCHEMA_OPERATION_REQUEST_FIELDS = ()


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
        raise ValidationError(
            "request body must be valid JSON", details=violation("request_schema"),
        ) from exc
    if not isinstance(payload, dict):
        raise ValidationError("request body must be a JSON object", details=violation("request_schema"))
    return payload


# -------------------------------------------------------------------------- Authentication: `Authorization: Bearer <credential_id>.<secret>`.
#
# WP-3 design decision (reported to the requester, §4 of the completion report -- the design document specifies "Authorization ヘッダの credential" but does not fix a wire encoding for THIS peer specifically): `auth.CredentialStore.authenticate`/`credential_store_postgres.PostgresCredentialStore.authenticate` both look a credential up by an explicit `(credential_id, secret)` PAIR (`WHERE credential_id = ...`, unlike r2db-api's own verifier-keyed single-secret lookup) -- there is no way to authenticate with `secret` alone on this peer. The bearer token is therefore the two values joined by a single `.`: `credential_id + "." + secret`. This is unambiguous: `credential_id` (`secrets.token_hex(12)`) and `secret` (`secrets.token_urlsafe(32)`) are both produced by this peer's own issuance path and neither alphabet ever contains `.`, so `token.split(".", 1)` always recovers the original pair exactly. A future in-band `/control/v1 issue_credential` would need to publish this SAME composite as its own `CredentialIssued.secret` field (the contract does not require any particular internal structure for that opaque string) for a real client to construct a usable bearer token at all. --------------------------------------------------------------------------
# history: CH-0194


class _CredentialMissing(Exception):
    """No `Authorization` header (or no usable bearer token in it) was
    presented at all -- distinct from a token that WAS presented but is
    wrong/malformed (`_CredentialMalformed`), matching contract
    `errors.codes`' own distinction between `AUTH_REQUIRED` and
    `AUTH_INVALID`."""


class _CredentialMalformed(Exception):
    """
    Phase 6 WP-3 差し戻し 最終ラウンド (裁定 1): kept only as a documented historical marker -- no code on this peer constructs this exception any more. Before this round, this HTTP boundary split a presented bearer itself and raised this class for an unparseable shape; splitting now happens exactly once, inside the credential store (`auth.CredentialStore.authenticate`/`credential_store_postgres.PostgresCredentialStore.authenticate`), so a malformed bearer reaches this boundary as an ordinary `AuthenticationError` (`AUTH_INVALID`) instead -- `_endpoint`'s own `except` clause below still names this class for defense-in-depth, but the branch is unreachable in practice.

    History: CH-0195
    """


def _extract_bearer(request: Request) -> str | None:
    header = request.headers.get("authorization")
    if not header:
        return None
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


# -------------------------------------------------------------------------- HttpService: the one object `create_app` needs from a composition root (for a real deployment, the conformance adapter for the suite). Deliberately NOT `service.MitateDataService` -- that class's own `open_session` resolves a cell from an in-process `ControlPlane.cells` dict built at `provision_application` time (an in-memory SQLite composition, R-3's own "SQLite backend stays local-foundation-only" rule) has no notion of "look up this application's own PostgreSQL DSNs from the platform registry"; that resolution is this class' own job, parameterized by a `cell_factory` callable exactly like r2db-api's own composition root (`r2db_api.main.build_app`'s `_cell_factory`, independently arrived at here rather than shared code). --------------------------------------------------------------------------
# history: CH-0196


class HttpService:
    """
    Composition-root-agnostic session/session-authority resolution for the HTTP surface: given a real `credential_store` (the `PostgresCredentialStore`, in a real deployment) and a `cell_factory` that builds a backend-bound `ApplicationCell` for a resolved `application_id`, this class authenticates a bearer token into a real `ApplicationRuntime`/`ApplicationDeveloper` session object -- the same session types `cell.py` already defines, unchanged.

    History: CH-0197
    """

    def __init__(self, credential_store: Any, cell_factory: Callable[[str], Any], *, audit_router: Any = None, limit_holder: Any = None, max_concurrency: "int | None" = None) -> None:
        self._credentials = credential_store
        self._cell_factory = cell_factory
        # Phase 10 WP-8c (design --): `limit_holder`/`max_concurrency` are the SAME `_LimitStateHolder` instance (and its own declared `concurrency` bound) `main.build_app` already constructs and injects into every `ApplicationCell` it builds (`main.py`'s own comment on `limit_holder`) -- given here too so `acquire_concurrency_slot` below can reserve a slot on that EXACT SAME counter, before authentication, using the deployment's own real declared bound (never a value re-derived or guessed here).
        #
        # FAIL CLOSED, not fail open: round-1 review found this pair silently no-op'd `acquire_concurrency_slot` below when omitted -- a future refactor of `main.py`'s own wiring (e.g. dropping these two keywords from its `HttpService(...)` call) would then have disabled the real deployment's own pre-authentication concurrency admission with NO test turning red, since every existing caller tolerated `None`. Round 2 (this ruling) removes that silent tolerance: EVERY caller of this constructor must now supply both, or construction itself raises immediately, loudly, before any request is ever served.
        #
        # Disclosed scope limit (report, "設計への疑義", carried forward from): BOTH conformance HTTP adapter's own `HttpService(...)` call sites (`conformance_adapter_mitatedb_http.py`, untouched by this WP -- design boundary "conformance adapters は 触らない") still omit these two keywords, so this fail-closed constructor now raises there too -- that harness's own fixture construction breaks under this change. This is a KNOWN, REPORTED consequence, not an oversight: fixing it means adding `limit_holder=`/`max_concurrency=` to those two call sites, which is an edit to a file this WP's own manifest explicitly places out of scope; the supervisor's own round-2 ruling defers that wiring to the integration branch that folds this WP in.
        # history: CH-0198
        if limit_holder is None or max_concurrency is None:
            raise RuntimeError(
                "HttpService requires both limit_holder and max_concurrency to be supplied at "
                "construction time (Phase 10 WP-8c review F-2, supervisor ruling 2026-09-09): a "
                "silently no-op pre-authentication concurrency admission is no longer permitted -- "
                "fail closed, not fail open. Pass the SAME _LimitStateHolder every ApplicationCell "
                "this HttpService serves already shares, and this deployment's own declared "
                "FoundationConfig.max_concurrency."
            )
        self._limit_holder = limit_holder
        self._max_concurrency = max_concurrency
        # Phase 4 (design docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md D-3 m-1, folded into M-3): `AUTH_REQUIRED` is in `audit_dispatch.DURABLE_DENIAL_CODES` (D-3's own inclusion table -- "認証系 2 コード相当"), but this peer only ever constructs it HERE (`_CredentialMissing`, below) -- strictly before any credential store is ever consulted (no bearer token at all was presented). Without a router here, a durable-range code declared in the vocabulary would have no emit site ever reachable in this peer's real deployment topology at all. `None` (the default) keeps every pre-Phase-4 caller of this constructor (this repository's own tests, the in-process conformance adapter, which has no HTTP surface at all) working unchanged -- a missing router simply means this ONE denial class stays undurable, exactly like every OTHER call site before this WP wired a router in.
        # history: CH-0199
        self._audit_router = audit_router

    def authenticate(self, bearer_token: str | None, *, request_id: str | None = None) -> ApplicationRuntime:
        """
        Phase 6 WP-3 差し戻し 最終ラウンド (裁定 1): this HTTP boundary never splits the presented bearer itself any more -- it passes `bearer_token` straight through to `self._credentials.authenticate` (`auth.CredentialStore`/`credential_store_postgres.PostgresCredentialStore`, whichever this service was composed with), which is the single choke point that calls `split_bearer_locator` exactly once. A malformed bearer is no longer distinguished HERE at all -- it reaches the store like any other credential and comes back as an ordinary, unattributed `AuthenticationError` (`AUTH_INVALID`), durably routed by the store's own pre-auth branch (mirrors r2db-api's own `http.py::authenticate`, which never pre-splits either).

        History: CH-0200
        """
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

    @contextmanager
    def acquire_concurrency_slot(self) -> "Iterator[None]":
        """
        Phase 10 WP-8c (design; fail-closed as of): pre-authentication concurrency admission -- mirrors r2db `service.py::DataService.acquire_concurrency_slot`'s own identical purpose. `http.py`'s own route handlers below enter this BEFORE calling `_authenticate`, and hold it for the caller's own ENTIRE request; the eventual `ApplicationCell._limit_gate` call this request reaches (through `ApplicationRuntime`/`ApplicationDeveloper`) recognizes the slot is already held (`cell.py`'s own `_CONCURRENCY_RESERVED` `ContextVar`) and does not reserve a second one.

        `__init__`'s own fail-closed guard guarantees `self._limit_holder`/`self._max_concurrency` are never `None` here -- there is no more no-op branch to fall through to; an instance that could not be given both never exists in the first place. `main.py`'s real composition root wires both, so the real deployment gets the real admission check; the conformance HTTP adapter's own `HttpService(...)` construction (untouched by this WP) now fails at CONSTRUCTION time instead of silently disabling this check -- `__init__`'s own comment discloses that consequence.

        History: CH-0201
        """
        with self._limit_holder.acquire_concurrency_slot(self._max_concurrency):
            yield


Handler = Callable[[Request], Awaitable[Response]]

# WP-8b: every endpoint below delegates its own synchronous section (authenticate / cell call / psycopg) to `starlette.concurrency.run_in_threadpool` so a slow request no longer serializes the whole event loop behind it (D-8 (2)'s own measured trigger: a single-process `hold_in_flight(n>1)` could not exceed in-flight=1 before this WP). `run_in_threadpool` runs on anyio's default worker limiter (40 threads unless the composition root raises `anyio.to_thread.current_default_thread_limiter().total_tokens`, which this WP does not do) -- a declared `concurrency` bound above 40 is therefore capped by that worker pool, not by `_LimitStateHolder.concurrency_slot`, on a single process (a fact only, not a change this WP makes to any limit declaration).
# history: CH-0202


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
    # Review M-2 (major, "完全案"): threads this same request's own `request_id` (`_request_id`, already generated by the byte-limiting ASGI middleware and returned as the `x-request-id` response header) into the credential-store authenticate call -- every call site below reaches `_request_id (request)` independently too, for its own subsequent session operation, so a single request's own durable rows (an `AUTH_INVALID`/`AUTH_REQUIRED` denial here, or an `allow` row from the operation that follows) all carry the identical value.
    # history: CH-0203
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
    # Phase 6 WP-3 (design D-3, item (i)): the contract's 7th `field_type` member -- physically the SAME `json` (TEXT) column `object`/`array` already use; the declared-type REGISTRY (`cell.py`, `field_types.py`), never this map, is what recovers which of the three a field actually is.
    # history: CH-0204
    "json": "json",
}

# `SchemaOperationRequest.operation`'s full contract enum. Only `create_entity`/`add_field` execute; every other member is a real, present denial (`CAPABILITY_UNSUPPORTED`) once this endpoint is mounted -- C-17's new present-denial form (design R-8 item 1), never `SurfaceAbsent` here (that claim belongs only to the in-process adapter, which genuinely has no schema-operations HTTP entry point at all).
# history: CH-0205
_SCHEMA_OPERATIONS = {"create_entity", "add_field", "alter_field", "create_index", "drop_index", "drop_entity"}


def _predicate_to_filter(item: Any, *, own_path: "str | None" = None) -> Filter:
    _check_object_shape(item, _DEFINITIONS["Predicate"], label="where item", own_path=own_path)
    return Filter(item["field"], item["operator"], item.get("value"))


def _order_items(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        raise ValidationError(
            "order_by must be an array",
            details=violation("request_schema", field="order_by", declared_type="array", observed_type=observed_type_of(raw)),
        )
    for index, item in enumerate(raw):
        _check_object_shape(item, _DEFINITIONS["Order"], label="order_by item", own_path=f"order_by/{index}")
    return raw


# -------------------------------------------------------------------------- Endpoints (spec/data-service-api.v1.json -> "endpoints").
#
# Phase 10 WP-8c: every handler below now enters `service.acquire_concurrency_slot()` as its OWN first statement, before `_authenticate` -- the data-plane evaluation order is now BYTE BOUND (`RequestByteBoundMiddleware`, this module's `create_app`) -> CONCURRENCY SLOT -> AUTHENTICATION -> body read -> rate/business (`ApplicationCell._limit_gate`, still entered post-authentication -- `cell.py`'s own `_CONCURRENCY_RESERVED` `ContextVar` recognizes the slot is already held and does not reserve a second one). This mirrors r2db `http.py`'s own identical module-header comment verbatim in structure (independent realization, no code shared between peers -- R-2's closing paragraph): `concurrency` alone is credential-independent, so it alone can be evaluated before a credential is known at all; the rate window stays keyed by `credential_id` and therefore stays post-auth (`_LimitStateHolder.acquire_rate`).
#
# `acquire_concurrency_slot()` is held for the caller's own ENTIRE request -- across both `run_in_threadpool` calls a body-carrying handler makes -- via a plain synchronous `with` entered on the event-loop thread: `starlette.concurrency.run_in_threadpool` (`anyio.to_thread.run_sync`) copies the CURRENT `contextvars.Context` into the worker thread it runs on, so a value/lock held on the event-loop thread still correctly spans two separate offloaded calls that may each land on a different physical OS thread. --------------------------------------------------------------------------
# history: CH-0206


@_endpoint
async def get_capabilities(request: Request) -> Response:
    # M-9 (design §2): application authentication ONLY. This process holds no control-credential store at all (R-4's own process-role separation), so there is structurally no way to accept a control credential here even as a co-hosting convenience.
    #
    # WP-8b: this endpoint reads no request body, so its whole synchronous section -- `_authenticate` (a real `PostgresCredentialStore` round trip on this HTTP composition) and `session.capabilities` together -- is delegated to `starlette.concurrency.run_in_threadpool` as one unit, freeing the event-loop thread for other requests' own ASGI I/O while this one runs.
    # history: CH-0207
    service: HttpService = request.app.state.service
    with service.acquire_concurrency_slot():
        def _sync() -> dict[str, Any]:
            session = _authenticate(request)
            return dict(session.capabilities(request_id=_request_id(request)))

        document = await run_in_threadpool(_sync)
    # Phase 8 WP-1a rework 1 (裁定 1): `request_bytes` is `enforced` from `cell.py`'s own single-source declaration on BOTH surfaces (the in-process structural estimate `ApplicationCell._limit_gate` runs is transport-independent) -- the former enforcement-layer override that used to flip this key from `unavailable` to `enforced` for the HTTP surface only is REMOVED in this same commit (R-3: a meaningless, redundant re-declaration of what the single source of truth already says, once that source itself says `enforced`).
    #
    # `operation_depth` is now the SAME -- `cell.py`'s own single-source declaration is `enforced` on BOTH surfaces too (see `cell.py:: ApplicationRuntime.capabilities()`'s own `limit_enforcement.operation_depth` comment for why the WP-1a report's original "in-process has no request dict" premise was factually wrong: `_check_operation_depth` genuinely runs, in-process included, on every request shape `_limit_gate`'s own callers build -- `insert`'s own `{"collection": ..., "values": ...}` is a real request dict, not an absent one). This wire layer therefore no longer overrides `operation_depth` either, for the identical reason it stopped overriding `request_bytes` above.
    # history: CH-0208
    return JSONResponse(document, status_code=200)


@_endpoint
async def post_query(request: Request) -> Response:
    # WP-8b: `_authenticate` is delegated on its OWN, before the body is even read -- `test_unauthenticated_malformed_json_body_is_auth_required_not_validation_failed` pins authentication strictly before shape/JSON validation; folding it into the tail delegation below would mean reading the body (on the loop) before ever authenticating, reordering that fail-closed guarantee. Body reading itself (`_read_json_object`, immediately below) stays a plain `await` on the event loop, never delegated.
    # history: CH-0209
    service: HttpService = request.app.state.service
    with service.acquire_concurrency_slot():
        session = await run_in_threadpool(_authenticate, request)
        entity = request.path_params["entity"]
        body = await _read_json_object(request)

        # WP-8b: everything below is synchronous -- shape/capability checks,
        # then `session.read` (a real cell/psycopg call on this HTTP
        # composition) -- and is delegated to `run_in_threadpool` as one unit,
        # started only once the async body read above has completed.
        def _sync() -> list[Any]:
            _check_object_shape(body, _SCHEMAS["QueryRequest"], label="QueryRequest")
            _deny_first_provisional_field(body, _PROVISIONAL_UNSUPPORTED_QUERY_REQUEST_FIELDS)

            select = body["select"]
            where_raw = body.get("where")
            filters = (
                [_predicate_to_filter(item, own_path=f"where/{i}") for i, item in enumerate(where_raw)]
                if where_raw is not None else None
            )

            order_by_raw = body.get("order_by")
            order_by = _order_items(order_by_raw) if order_by_raw is not None else None

            page = body.get("page")
            page_size = None
            if page is not None:
                _check_object_shape(page, _DEFINITIONS["Page"], label="page", own_path="page")
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
                    raise CapabilityError(
                        "page.cursor is not supported by this peer",
                        details=violation("capability", field="page/cursor"),
                    )
                if "size" in page:
                    page_size = page["size"]

            # Phase 9 WP-3d: `budget` now reaches `session.read` for real -- `ApplicationRuntime.read` (`cell.py`) is what turns it into `effective_limits` (`config.narrow_limits_by_budget`, `endpoint_kind="query"`) and validates it.
            # history: CH-0210
            return session.read(entity, fields=list(select), filters=filters, order_by=order_by, limit=page_size,
                                request_id=_request_id(request), budget=body.get("budget"))

        # Phase 9 WP-3e (design D-7 (2)/(3), Q-1/Q-2): `request_id` on the
        # response is `_request_id(request)` -- the SAME per-request value
        # already passed into `session.read` above (this layer's own uuid,
        # minted once at the ASGI middleware, never regenerated here) --
        # `ApplicationCell.read` has no return-shape room to echo a value
        # back through (a bare row list, unlike `transact`'s/the schema
        # methods' own dict/list-with-envelope returns), so this endpoint
        # reads its own already-held local value instead of `rows`.
        rows = await run_in_threadpool(_sync)
    return JSONResponse({"items": rows, "next_page": None, "request_id": _request_id(request)}, status_code=200)


def _mutation_item(entity: str, raw: Mapping[str, Any], *, index: int) -> dict[str, Any]:
    own_path = f"operations/{index}"
    _check_object_shape(raw, _DEFINITIONS["Mutation"], label="mutation operation", own_path=own_path)
    # Phase 9 WP-3b rework: `values` is unconditionally present here (`raw.get("values") or {}`, never conditional on `"values" in raw`) -- this is this peer's own INTERNAL execution-item vocabulary (`ApplicationCell.transact`'s `_TRANSACT_*_KEYS`/`_plan_operation` consume it via `.get("values")` either way, so an absent key would have executed identically), not something the plan digest reads any more (closure): `_mutation_digest_item` immediately below builds the digest's own per-operation object straight from `raw`, BEFORE this forcing, so an omitted `values` and an explicit `values: {}` stay two different digested requests regardless of what this execution item itself always carries.
    # history: CH-0211
    item: dict[str, Any] = {"type": raw["operation"], "collection": entity, "values": dict(raw.get("values") or {})}
    if "where" in raw:
        item["filters"] = [
            _predicate_to_filter(w, own_path=f"{own_path}/where/{i}") for i, w in enumerate(raw["where"])
        ]
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
    """
    Phase 9 WP-3b closure (追補 2): the plan digest's own per-operation object -- unlike `_mutation_item` above (this peer's INTERNAL execution vocabulary: `type`/`collection`/`filters`/`confirm`, `values` forced present unconditionally), this is the contract-level `Mutation`/`ScopedMutation` object AS THE CLIENT PRESENTED IT: `raw` has already passed `_check_object_shape` against that exact schema (`_mutation_item`'s own first line, called immediately before or after this one at every call site), so it carries only contract-named keys already -- a plain shallow copy, no key renamed, no optional backfilled, no key forced present. `values` in particular stays ABSENT here when the request omitted it (A-3.3: an omitting request and a `values: {}` request must NOT collide on one plan token -- the exact defect class already closed for schema `field_constraints`). `where`'s own predicate objects stay plain dicts (never converted to a `Filter` dataclass, unlike `_ mutation_item`'s `filters`) -- JSON-native by construction, so no `default=` hook is ever needed feeding this into `cell.py::normalize_request_for_plan`.

    History: CH-0212
    """
    return dict(raw)


def _mutation_outcome(items: list[dict[str, Any]], results: list[Any], *,
                      dry_run: bool = False) -> tuple[int, bool, str | None, str | None]:
    """
    Phase 9 WP-3b: shared by `post_mutate`/`post_cross_entity_mutate` -- `affected` exactly as both computed it before this WP (`zip` truncates to `len(items)`, so this is unaffected by `cell.py:: ApplicationCell.transact`'s own dry-run envelope, appended -- when present -- one entry PAST the last real per-item result). `committed`/`plan` are read off that trailing envelope (a dict `transact()` itself never returns for a real, non-dry-run request, design D-4 (4)).

    Phase 9 WP-3e (design D-7 (2)/(3), Q-1/Q-2): `request_id` is this tuple's new 4th element, read off the SAME `envelope` -- for a dry run that is the trailing envelope `cell.py::ApplicationCell.transact` always appends; for a real commit, `results[-1]` IS one real operation's own per-item dict, but `cell.py`'s own commit path now folds `request_id` into it, in place (never a new trailing entry there, unlike the dry-run envelope -- see that method's own comment for why: `len(results)` is load-bearing for the pre-v1.13 port).

    Rework (Minor m-4): `committed`'s own default is `not dry_run` -- matching the in-process port's own identical `envelope.get("committed", not dry_run)` -- rather than the previous unconditional `True`. `transact()` always appends the envelope for a dry run (so `envelope.get("committed", ...)` finds a real `False` there in practice either way) and never for a real call, where `results[-1]` is instead a real per-item result dict (e.g. `{"deleted": n}`) that happens to carry no `committed` key -- this default is only ever consulted in that second case, and `dry_run` is always `False` there too, so the two defaults agree in every reachable case today; aligning them removes a latent trap for whichever future change makes them diverge.

    History: CH-0213
    """
    affected = 0
    for item, result in zip(items, results):
        if item["type"] == "insert":
            affected += 1
        elif isinstance(result, dict):
            affected += result.get("updated", result.get("deleted", 0))
    envelope = results[-1] if results and isinstance(results[-1], dict) else {}
    return affected, envelope.get("committed", not dry_run), envelope.get("plan"), envelope.get("request_id")


@_endpoint
async def post_mutate(request: Request) -> Response:
    # WP-8b: see `post_query`'s own identical comment -- `_authenticate` is delegated on its own, before the body is read, to keep the fail-closed auth-before-shape/JSON-validation ordering intact.
    # history: CH-0214
    service: HttpService = request.app.state.service
    with service.acquire_concurrency_slot():
        session = await run_in_threadpool(_authenticate, request)
        entity = request.path_params["entity"]
        body = await _read_json_object(request)

        # WP-8b: shape/capability checks and the real `session.transact` call
        # (cell/psycopg) are delegated together, as one unit, after the async
        # body read above completes.
        def _sync() -> tuple[int, bool, "str | None", "str | None"]:
            # `_check_object_shape` against `MutationRequest` (`additionalProperties:
            # false`, properties: operations/transaction/idempotency_key) is what
            # makes a smuggled body `entity` field an unknown-field rejection
            # (`endpoints.mutate.semantics`: "The body carries no entity field; a
            # body entity field is rejected as an unknown field.") -- `entity`
            # is simply not in this schema's own property set.
            _check_object_shape(body, _SCHEMAS["MutationRequest"], label="MutationRequest")
            _deny_first_provisional_field(body, _PROVISIONAL_UNSUPPORTED_MUTATION_REQUEST_FIELDS)
            # `transaction_raw` (rework): the digest must commit to the request AS PRESENTED -- an omitted `transaction` and one explicitly spelling out the deployed default (`"atomic"`) are two DIFFERENT requests (contract `structured_operations.dry_run.plan`: "a real request differing from the dry run in any of them is a different request"), so `session.transact` below is given the RAW, unbackfilled value -- `None` when the client omitted the key -- never this method's own resolved `transaction` (backfilled to `"atomic"` purely for THIS validation step, unchanged from before this rework). C-22 (10)'s own MitateDB-api-http leg is what caught this: presenting a dry run's plan back with `transaction: "atomic"` newly ADDED must be refused, and it silently was not while `session.transact` received the backfilled value on BOTH the dry run and the apply alike (both always "atomic", so nothing ever differed).
            # history: CH-0215
            transaction_raw = body.get("transaction")
            transaction = transaction_raw if transaction_raw is not None else "atomic"
            if transaction == "best_effort":
                # `best_effort_transactions: unavailable` (cell.py's own
                # declaration, unchanged) -- `transact()` has no partial-result
                # execution mode at all; presenting `best_effort` is a real,
                # optional-target-shape refusal, not a malformed request.
                raise CapabilityError(
                    "best_effort transactions are not supported by this peer",
                    details=violation("capability", field="transaction"),
                )
            if transaction != "atomic":
                # An out-of-vocabulary `transaction` value entirely (neither
                # `atomic` nor `best_effort`, the contract's own 2-member enum) --
                # `request_schema`, not `capability` (mirrors the analogous
                # distinction `cell.py::_plan_operation`'s own final fallback
                # draws between an unimplemented-but-real vocabulary member and a
                # value outside the vocabulary altogether).
                raise ValidationError(
                    "transaction mode is not supported",
                    details=violation("request_schema", field="transaction"),
                )

            operations = body.get("operations")
            if not isinstance(operations, list) or not operations:
                raise ValidationError(
                    "operations must be a non-empty array",
                    details=violation("request_schema", field="operations"),
                )
            items = [_mutation_item(entity, op, index=i) for i, op in enumerate(operations)]
            # `digest_items` (closure): the SAME `operations` list, built into the CONTRACT-shaped digest object instead of the execution item `_mutation_item` builds -- see `_mutation_digest_item`'s own docstring.
            # history: CH-0216
            digest_items = [_mutation_digest_item(op) for op in operations]

            # Phase 9 WP-3b: `dry_run`/`plan` now reach `transact()` for real -- both defaulted to their own byte-compatible absence (`False`/`None`) above, so an unchanged caller's own request is unaffected.
            # history: CH-0217
            results = session.transact(
                items, request_id=_request_id(request),
                dry_run=body.get("dry_run", False), plan=body.get("plan"),
                # Phase 9 WP-3b rework: `transaction_raw` (NOT the backfilled `transaction` above) now reaches `session.transact` -- `None` when the request omitted the key, `"atomic"` only when the request actually named it -- so the digest commits to what the request presented, not this endpoint's own resolved default. `post_cross_entity_mutate` below has no `transaction` field on `ScopedMutationRequest` at all, so it never passes one.
                # history: CH-0218
                transaction=transaction_raw,
                # `entity`/`digest_operations` (closure): `entity` is this endpoint's own URL path segment -- `MutationRequest` has no `entity` property of its own (it is implicit from the path), so it is hoisted to the digest object's own TOP level here (`cell.py::ApplicationCell.transact`'s own `entity` keyword) -- an entity substitution between a dry run and its apply must fail closed. `digest_operations=digest_items` supplies the CONTRACT-shaped per-operation objects built above, so `cell.py` never falls back to reconstructing them from `items`' own internal execution vocabulary.
                # history: CH-0219
                entity=entity, digest_operations=digest_items,
                # Phase 9 WP-3c/WP-3d: `idempotency_key`/`budget` now reach `session.transact` for real -- both are the SINGLE request-level `MutationRequest` values (never per-operation on this endpoint's own wire shape), passed straight through as this method's own keywords (never folded onto `items`, unlike the in-process port's own convention -- see `cell.py:: ApplicationCell.transact`'s own docstring for why both entry points converge correctly either way).
                # history: CH-0220
                idempotency_key=body.get("idempotency_key"), budget=body.get("budget"),
            )
            return _mutation_outcome(items, results, dry_run=body.get("dry_run", False))

        affected, committed, plan_token, mutation_request_id = await run_in_threadpool(_sync)
    response: dict[str, Any] = {"committed": committed, "affected": affected}
    if plan_token is not None:
        response["plan"] = plan_token
    # Phase 9 WP-3e (design D-7 (2)/(3), Q-1/Q-2): `mutation_request_id`
    # -- the SAME value `cell.py::ApplicationCell.transact` resolved and
    # used for this request's own audit event -- never `_request_id
    # (request)` again here (this layer does not regenerate).
    response["request_id"] = mutation_request_id
    return JSONResponse(response, status_code=200)


def _scoped_mutation_item(raw: Mapping[str, Any], *, index: int) -> dict[str, Any]:
    """
    P35 WP-2 (R-3, design docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md §2): the cross-entity counterpart of `_mutation_item` above -- reads `entity` from EACH operation itself (contract `ScopedMutation`, `Mutation` + a required `entity`) instead of a single URL path segment shared by the whole request. Otherwise identical field-by-field mapping onto `ApplicationCell.transact`'s own operation-dict vocabulary (`_TRANSACT_INSERT_KEYS`/`_TRANSACT_UPDATE_KEYS`/`_TRANSACT_DELETE_KEYS` in `cell.py`) -- an unsupported key (`expected_revision`/`unique_key`) still rides along here exactly as `_mutation_item` lets it, so `transact()`'s own single choke refuses it with `CAPABILITY_UNSUPPORTED`, not a second copy of that refusal at this layer.

    History: CH-0221
    """
    own_path = f"operations/{index}"
    _check_object_shape(raw, _DEFINITIONS["ScopedMutation"], label="cross-entity mutation operation", own_path=own_path)
    # Phase 9 WP-3b rework: same reasoning as `_mutation_item`'s own identical comment -- `values` always present.
    # history: CH-0222
    item: dict[str, Any] = {"type": raw["operation"], "collection": raw["entity"], "values": dict(raw.get("values") or {})}
    if "where" in raw:
        item["filters"] = [
            _predicate_to_filter(w, own_path=f"{own_path}/where/{i}") for i, w in enumerate(raw["where"])
        ]
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
    """
    P35 WP-2: `cross_entity_mutation` is now `enabled` (`cell.py::ApplicationRuntime.capabilities()`, same commit) -- this endpoint dispatches for real instead of raising an unconditional `CapabilityError`. `session.transact` is the SAME two-pass entry point (`cell.py::ApplicationCell.transact`) the per-entity `POST /v1/data/{entity}/mutations` endpoint already uses; the only difference at this layer is where each operation's own `collection` comes from (per-operation `entity`, via `_scoped_mutation_item`, rather than one shared URL path segment).

    Phase 9 WP-3c/WP-3d: `idempotency_key`/`budget` now reach `session.transact` for real, exactly like `post_mutate` above (I-9: this peer's own `transact()` dispatcher is shared by both endpoints, so both honor them identically). There is no `transaction` field on `ScopedMutationRequest` at all (unlike `MutationRequest`) -- a cross-entity batch has no `best_effort` mode to refuse here.

    Response body is `{"committed", "affected"}` ONLY -- no `assigned_addresses` (design M-6: this peer declares `row_addressability`/`application_catalog` unavailable, so it has no address-field vocabulary it could honestly attach to a response; matches `post_mutate`'s own response shape exactly).

    History: CH-0223
    """
    # WP-8b: same split as `post_mutate` above -- `_authenticate` delegated on its own before the body is read (fail-closed auth-before-shape ordering preserved), then the shape check plus the real `session.transact` call delegated together, after the async body read.
    # history: CH-0224
    service: HttpService = request.app.state.service
    with service.acquire_concurrency_slot():
        session = await run_in_threadpool(_authenticate, request)
        body = await _read_json_object(request)

        def _sync() -> tuple[int, bool, "str | None", "str | None"]:
            _check_object_shape(body, _SCHEMAS["ScopedMutationRequest"], label="ScopedMutationRequest")
            _deny_first_provisional_field(body, _PROVISIONAL_UNSUPPORTED_MUTATION_REQUEST_FIELDS)

            operations = body.get("operations")
            if not isinstance(operations, list) or not operations:
                raise ValidationError(
                    "operations must be a non-empty array",
                    details=violation("request_schema", field="operations"),
                )
            items = [_scoped_mutation_item(op, index=i) for i, op in enumerate(operations)]
            # `digest_items` (closure): built straight from `raw` per operation -- `ScopedMutation` already names `entity` as one of its own contract properties, so each digest item carries its own target entity without this endpoint needing a top-level `entity` keyword the way `post_mutate` above does (`_mutation_digest_item` is the SAME helper `post_mutate` uses -- it does no `Mutation`-vs- `ScopedMutation`-specific work of its own, just a shallow copy of whatever contract-shaped keys `raw` already carries).
            # history: CH-0225
            digest_items = [_mutation_digest_item(op) for op in operations]

            results = session.transact(
                items, request_id=_request_id(request),
                dry_run=body.get("dry_run", False), plan=body.get("plan"),
                digest_operations=digest_items,
                idempotency_key=body.get("idempotency_key"), budget=body.get("budget"),
            )
            return _mutation_outcome(items, results, dry_run=body.get("dry_run", False))

        affected, committed, plan_token, mutation_request_id = await run_in_threadpool(_sync)
    response: dict[str, Any] = {"committed": committed, "affected": affected}
    if plan_token is not None:
        response["plan"] = plan_token
    # Phase 9 WP-3e (design D-7 (2)/(3), Q-1/Q-2): `mutation_request_id`
    # -- the SAME value `cell.py::ApplicationCell.transact` resolved and
    # used for this request's own audit event -- never `_request_id
    # (request)` again here (this layer does not regenerate).
    response["request_id"] = mutation_request_id
    return JSONResponse(response, status_code=200)


@_endpoint
async def get_catalog(request: Request) -> Response:
    # Phase 6 WP-3: `application_catalog: enabled` (`cell.py`'s own declaration, same commit) -- `session.catalog()` returns the SAME 3-key `EntityDescriptor` shape (`entity`/`fields`/`field_types`) for every entity, backed by the declared-type registry.
    #
    # WP-8b: no request body -- `_authenticate` and `session.catalog` are delegated together, as one unit, same shape as `get_capabilities` above. `session` itself is returned alongside `entities` (never re-authenticated on the loop) since `session.principal.application_id` is read below, after this call returns.
    # history: CH-0226
    service: HttpService = request.app.state.service
    with service.acquire_concurrency_slot():
        def _sync() -> tuple[Any, list[Any]]:
            session = _authenticate(request)
            return session, session.catalog(request_id=_request_id(request))

        session, entities = await run_in_threadpool(_sync)
    # `CatalogDocument.application_scope` is required alongside `entities`
    # -- every other endpoint's own response already carries this same
    # value (`get_capabilities`'s `application_scope` key, `cell.py::
    # ApplicationRuntime.capabilities()`), read from the SAME `Application
    # Runtime.application_id` property, never re-derived.
    return JSONResponse({"application_scope": session.principal.application_id, "entities": entities}, status_code=200)


@_endpoint
async def post_schema(request: Request) -> Response:
    # WP-8b: `_authenticate` delegated on its own, before the body is read -- same fail-closed ordering rationale as `post_query`/`post_mutate` above.
    # history: CH-0227
    service: HttpService = request.app.state.service
    with service.acquire_concurrency_slot():
        session = await run_in_threadpool(_authenticate, request)
        body = await _read_json_object(request)

        # WP-8b: shape/authority checks and the real `session.create_entity`/
        # `add_field`/`alter_field` calls (cell/psycopg) are delegated together,
        # as one unit, after the async body read above completes. Returns the
        # already-built `Response` directly -- constructing a `JSONResponse`
        # does no I/O, so building it inside the worker thread is harmless.
        def _sync() -> Response:
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
                # A value outside the contract's own 6-member `operation` enum
                # entirely -- `_check_object_shape` above does not validate enum
                # membership (only top-level key presence), so a genuinely
                # unrecognized string still reaches here; `request_schema`, not
                # `capability` (mirrors `post_mutate`'s own analogous "out-of-
                # vocabulary transaction value" distinction above).
                raise ValidationError(
                    "unsupported schema operation", details=violation("request_schema", field="operation"),
                )
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

            # `digest_extra` (WP-3b closure, H-3 (b); Phase 9 WP-3d rework):
            # `destructive`/`confirmation`/`revision`/`index`/`unique`/`budget`
            # are real `SchemaOperationRequest` properties (`_check_object_shape`
            # above already lets them through) that `create_entity`/`add_field`/
            # `alter_field` below never read INTO the digest as a NAMED key of
            # their own (`budget` IS read structurally, by `ApplicationDeveloper`
            # above, to build `effective_limits` -- but the digest itself must
            # still commit to the RAW value the request presented, per contract
            # `structured_operations.idempotency.record`: "every other field,
            # including budget ... is part of what a resend must match") -- the
            # contract requires the plan/idempotency digest to commit to "every
            # other field" the request presented (`structured_operations.dry_run.
            # plan`) regardless. Forwarded to `cell.py` verbatim, unread and
            # unvalidated here beyond the shape check above; whichever of the 6
            # the request did not carry stays entirely absent (G-1's own "省略さ
            # れた optional は key ごと無し" -- never backfilled to `None`/a
            # default).
            digest_extra = {
                key: body[key] for key in ("destructive", "confirmation", "revision", "index", "unique", "budget")
                if key in body
            }

            if schema_operation == "create_entity":
                # M-3 (independent): `SchemaOperationRequest.field_type` is a valid top-level property of this request shape (the contract gives it no per-operation `if`/`then` narrowing that would forbid it on `create_entity`), so `_check_object_shape` above accepts a request carrying it here. Silently ignoring it would accept a request this peer cannot honor as if it had succeeded: a caller naming `field_type: "integer"` alongside `fields: ["rank"]` would see `committed: true` yet `rank` is actually created as `text` (P3-D1's own untyped-equivalent mapping, below) -- confirmed empirically before this fix, a later insert of an integer value into `rank` failed with `VALIDATION_FAILED` despite the caller having explicitly declared its intended type up front and been told the operation committed. `field_type` has no per-field association on `create_entity` at all (only a single, request-level slot -- see the comment below), so there is no way to honor it here; refusing it explicitly, before any entity is created, is the same "reject an unread capability-shaped key before execution" discipline `cell.py`'s own `_TRANSACT_INSERT_KEYS` already applies to `transact()`.
                # history: CH-0228
                if "field_type" in body:
                    raise CapabilityError(
                        "create_entity cannot honor a request-level field_type for its fields array",
                        details=violation("capability", field="field_type"),
                    )
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
                    raise ValidationError(
                        "field_types requires fields to be present", details=violation("request_schema", field="field_types"),
                    )
                # P3-D1 (design §0 exception): the contract's `fields` on `create_entity` is a bare array of NAMES (no per-field `field_type` slot on `fields` itself) -- `SchemaOperationRequest.field_type` (singular, scalar) is a single, request-level value with no per-field association, refused above; `field_types` (plural, this WP) is the per-field carrier instead.
                # history: CH-0229
                if fields_raw is not None:
                    if not isinstance(fields_raw, list) or not fields_raw:
                        raise ValidationError(
                            "fields must be a non-empty array", details=violation("request_schema", field="fields"),
                        )
                    # Defensive, pre-execution shape check: a non-string (or
                    # unhashable) element here would otherwise raise a raw
                    # `TypeError` building the dict below, escaping as an
                    # UNCLASSIFIED-looking `SERVICE_UNAVAILABLE` instead of a
                    # proper `VALIDATION_FAILED` -- and, more importantly, doing
                    # so BEFORE `session.create_entity` is ever called, so no
                    # entity is created either way (this check exists for correct
                    # classification, not for structural-integrity safety, which
                    # already held without it).
                    for field_index, item in enumerate(fields_raw):
                        if not isinstance(item, str):
                            raise ValidationError(
                                "each field name must be a string",
                                details=violation(
                                    "request_schema", field=f"fields/{field_index}",
                                    declared_type="string", observed_type=observed_type_of(item),
                                ),
                            )
                    field_types_map: dict[str, str] = {}
                    if field_types_raw is not None:
                        if not isinstance(field_types_raw, dict):
                            raise ValidationError(
                                "field_types must be an object", details=violation("request_schema", field="field_types"),
                            )
                        for name, declared_type in field_types_raw.items():
                            if name not in fields_raw:
                                # (a) field_types names a field not in fields --
                                # a declaration naming a field the request does
                                # not create, `constraint_declaration`'s own 4th
                                # named case (mirrors `cell.py`'s identical
                                # `field_constraints` treatment).
                                raise ValidationError(
                                    f"field_types names {name!r}, which is not in fields",
                                    details=violation("constraint_declaration", field=f"field_types/{name}"),
                                )
                            if declared_type not in _CONTRACT_FIELD_TYPE_TO_MITATEDB:
                                # (b) field_types value outside the 7-word
                                # vocabulary -- not a violation about the VALUE's
                                # own JSON type (a syntactically valid string can
                                # still name no real field-type word), so
                                # `declared_type`/`observed_type` are omitted, the
                                # same "unrecognized member of a fixed word list"
                                # treatment `field_constraints`'s own unknown-key
                                # denials above already use.
                                raise ValidationError(
                                    f"field_types[{name!r}] is not a supported field_type",
                                    details=violation("request_schema", field=f"field_types/{name}"),
                                )
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
                # Phase 9 WP-3a (design docs/design/PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md): `field_constraints` is passed through verbatim -- `cell.py:: ApplicationCell.create_collection`/`.create_entity` do the real validation (partial-vs-`fields` cross-check, `enum` member/type/limit checks) and resolution to a total map; this HTTP layer does not re-validate its shape beyond `_check_object_shape`'s own top-level key check above.
                # history: CH-0230
                field_constraints = body.get("field_constraints")
                # Phase 9 WP-3b: `create_entity` now returns `{"revision", "descriptor", "committed"}` for real (`cell.py:: ApplicationCell.create_collection`) -- read DIRECTLY off that same-transaction result rather than the separate, uncounted `_post_schema_revision()` readback the two branches below used to need (m-2/裁定 3): a dry run rolls the write back before this call even returns, so a SEPARATE post-call read here would race a concurrent writer and could report a revision this dry run's own `plan` was never computed against. Phase 9 WP-3b rework: `field_types=` below is the RAW, PARTIAL declaration the caller actually presented (`field_types_map`, only the names `field_types_raw` itself named -- `None` when the request omitted `field_types` entirely), never `contract_field_types` (the TOTAL, `json`-backfilled map decision (ii) above builds so `fields`'s own foundation-type choice below has a value for every name). `cell.py::ApplicationCell.create_collection` backfills the SAME missing names to `json` on its own (via `FOUNDATION_TYPE_TO_CONTRACT_TYPE`, deriving it from the foundation type `fields` already carries for that name) -- so the entity this call creates is byte-identical either way; only the `plan` DIGEST changes, from committing to the resolved total map (M-2: a request omitting `field_types` and one explicitly spelling out the same defaults used to collide on one token) to committing to what the request itself named. `operation` NOT forwarded here (closure): `cell.py:: ApplicationCell.create_collection`'s own keyword-only PARAMETER default (`operation="create_entity"`) already supplies the correct digest value for this branch -- this call is only ever reached when `schema_operation == "create_entity"` (the `if` above), so the two are provably always equal; a genuine variable forward from `schema_operation` here would itself be a NEW `test_audit_query.py` scanner violation (a `operation=` keyword call site whose value's own Name id is not literally "operation" is never a recognized safe forward, regardless of what it holds) -- the SAME shape of problem `_NON_AUDIT_OPERATION_LITERALS` used to work around differently, which H-4 asks not to reintroduce.
                # history: CH-0231
                result = session.create_entity(
                    entity, fields, field_types=(field_types_map if field_types_raw is not None else None),
                    field_constraints=field_constraints,
                    dry_run=body.get("dry_run", False), plan=body.get("plan"),
                    request_id=_request_id(request), digest_extra=digest_extra,
                    idempotency_key=body.get("idempotency_key"), budget=body.get("budget"))
                response: dict[str, Any] = {"committed": result["committed"], "revision": result["revision"]}
                if result.get("descriptor") is not None:
                    response["descriptor"] = result["descriptor"]
                if result.get("plan") is not None:
                    response["plan"] = result["plan"]
                # Phase 9 WP-3e (design D-7 (2)/(3), Q-1/Q-2): `result["request_id"]`
                # -- the SAME value `cell.py`'s own schema-operation methods
                # resolved and used for this request's own audit event -- never
                # `_request_id(request)` again here (this layer does not
                # regenerate).
                response["request_id"] = result["request_id"]
                return JSONResponse(response, status_code=200)

            if schema_operation == "add_field":
                field = body.get("field")
                if not isinstance(field, str):
                    # `field` is globally optional on `SchemaOperationRequest`
                    # (only `operation`/`entity` are `required`) but conditionally
                    # required for THIS operation -- `observed_type` is `absent`
                    # when the request omitted the key entirely, the value's own
                    # JSON type otherwise (design D-3 (2)'s "欠落" convention).
                    raise ValidationError(
                        "add_field requires field",
                        details=violation(
                            "request_schema", field="field", declared_type="string",
                            observed_type="absent" if "field" not in body else observed_type_of(field),
                        ),
                    )
                field_type_raw = body.get("field_type")
                # WP-3a rework 3 (real, measured bug): `SchemaOperationRequest.field_type` is NOT globally `required` (only `operation`/`entity` are, `contract/data-service-api.v1.json`'s own `schemas.SchemaOperationRequest.required`), and contract `field_types`'s own description states the general rule this peer's `create_entity` branch above already honors for `fields`/`field_types`: "A field created without a declared type has type json -- this names an existing default rather than introducing a new one." `add_field`'s own singular `field_type` is that identical rule applied to the one field it adds -- an omitted `field_type` must default to `json`, not be refused. This peer used to refuse every field_type-omitting `add_field` with a bare, details-less `VALIDATION_FAILED` ("field and a supported field_type"), a real divergence from `r2db-api` (`postgres.py`'s own comment: "`add_field` with no `field_type` ... keep[s] the pre-CCR-13 default, JSONB") and from this peer's OWN in-process surface (`cell.py:: ApplicationDeveloper.add_field`'s `field_type` keyword already accepts `None`-derived `"json"` via the conformance port's own `foundation_type = ... if field_type is not None else "json"` translation). A field_type that IS present and outside the 7-word vocabulary is still refused, unchanged.
                # history: CH-0232
                if field_type_raw is not None and field_type_raw not in _CONTRACT_FIELD_TYPE_TO_MITATEDB:
                    # Mirrors `create_entity`'s own `field_types[name]`-outside-
                    # vocabulary treatment above: not a value-type violation
                    # (`field_type_raw` may well be a syntactically valid string),
                    # so `declared_type`/`observed_type` are omitted.
                    raise ValidationError(
                        "field_type is not a supported field_type",
                        details=violation("request_schema", field="field_type"),
                    )
                field_type = field_type_raw if field_type_raw is not None else "json"
                # Phase 9 WP-3a: `enum`/`nullable` passed through verbatim -- `cell.py::ApplicationCell.add_field` does the real validation, same reasoning as `create_entity`'s own identical comment above. Phase 9 WP-3b: same reasoning as `create_entity` above -- read `revision`/`descriptor`/`committed`/`plan` directly off this same-transaction result, not a separate post-call readback.
                # history: CH-0233
                result = session.add_field(
                    entity, field, _CONTRACT_FIELD_TYPE_TO_MITATEDB[field_type],
                    # `contract_type=field_type_raw` (WP-3b closure, H-3 (a)): the RAW value the request actually carried -- `None` when `field_type` was omitted -- NOT `field_type` (this method's own local, backfilled to `"json"` two lines above for EXECUTION purposes only). `cell.py::ApplicationCell.add_field`'s own digest now reads straight off this argument, present in the digest only when not `None`; passing the backfilled value here would make an omitting request and one explicitly spelling out `field_type: "json"` collide on one plan token (reproduced: P-B).
                    # history: CH-0234
                    contract_type=field_type_raw, enum=body.get("enum"), nullable=body.get("nullable"),
                    dry_run=body.get("dry_run", False), plan=body.get("plan"),
                    request_id=_request_id(request), digest_extra=digest_extra,
                    idempotency_key=body.get("idempotency_key"), budget=body.get("budget"))
                response = {"committed": result["committed"], "revision": result["revision"]}
                if result.get("descriptor") is not None:
                    response["descriptor"] = result["descriptor"]
                if result.get("plan") is not None:
                    response["plan"] = result["plan"]
                # Phase 9 WP-3e (design D-7 (2)/(3), Q-1/Q-2): `result["request_id"]`
                # -- the SAME value `cell.py`'s own schema-operation methods
                # resolved and used for this request's own audit event -- never
                # `_request_id(request)` again here (this layer does not
                # regenerate).
                response["request_id"] = result["request_id"]
                return JSONResponse(response, status_code=200)

            if schema_operation == "alter_field":
                # Phase 9 WP-3a (design D-2 (5)/(6)): present-denial (design R-8 item 1, C-17) removed for THIS operation -- `alter_field` is now a real, executed request. `create_index`/`drop_index`/`drop_entity` still fall through to the present-denial `raise` below, unchanged by this WP.
                # history: CH-0235
                field = body.get("field")
                if not isinstance(field, str):
                    raise ValidationError(
                        "alter_field requires field",
                        details=violation(
                            "request_schema", field="field", declared_type="string",
                            observed_type="absent" if "field" not in body else observed_type_of(field),
                        ),
                    )
                # Code review §2 A / 監督裁定 A: `body.get("enum", UNCHANGED)` -- NOT a plain `body.get("enum")` -- is the one place on the wire this distinction can still be made: `dict.get(key, default)` returns `default` ONLY when `key` is absent from `body`, so an omitted `enum` reaches `session.alter_field` as the `UNCHANGED` sentinel (leaves the field's `enum` as it is) while a present `"enum": null` reaches it as a real `None` (clears it) -- the contract's own `SchemaOperationRequest.enum` is already `["array", "null"]` in this WP's own packaged contract copy, so `_check_object_shape` above lets a literal `"enum": null` through the shape layer, reaching this line as the real `None` that means "clear it".
                # history: CH-0236
                result = session.alter_field(
                    entity, field, enum=body.get("enum", UNCHANGED), nullable=body.get("nullable"),
                    field_type=body.get("field_type"), dry_run=body.get("dry_run", False), plan=body.get("plan"),
                    request_id=_request_id(request), digest_extra=digest_extra,
                    idempotency_key=body.get("idempotency_key"), budget=body.get("budget"))
                response = {"committed": result["committed"], "revision": result["revision"]}
                if result.get("descriptor") is not None:
                    response["descriptor"] = result["descriptor"]
                if result.get("plan") is not None:
                    response["plan"] = result["plan"]
                # Phase 9 WP-3e (design D-7 (2)/(3), Q-1/Q-2): `result["request_id"]`
                # -- the SAME value `cell.py`'s own schema-operation methods
                # resolved and used for this request's own audit event -- never
                # `_request_id(request)` again here (this layer does not
                # regenerate).
                response["request_id"] = result["request_id"]
                return JSONResponse(response, status_code=200)

            # C-17 present-denial form (design R-8 item 1): `create_index`/`drop_index`/`drop_entity` are all real, contract-shaped requests this real dispatcher receives and refuses -- never a structural absence on this composition, since the entry point genuinely exists and executes for `create_entity`/`add_field`/`alter_field` above.
            # history: CH-0237
            raise CapabilityError(
                f"schema operation {schema_operation!r} is not supported by this peer",
                details=violation("capability", field="operation"),
            )

        return await run_in_threadpool(_sync)


@_endpoint
async def post_audit_query(request: Request) -> Response:
    # `audit_query: unavailable` (cell.py's own declaration, unchanged this WP) -- authenticate with the same application-credential path as every other endpoint (fail closed on missing/invalid credentials first), but never execute: the contract requires control/audit authority for this endpoint and this process holds no control-credential store at all (R-4's own process-role separation).
    #
    # WP-8b: `_authenticate` delegated like every other endpoint's own auth call -- the `raise` immediately below does no I/O of its own, so it stays a plain synchronous statement on the loop, not a second delegation.
    #
    # Phase 10 WP-8c: wrapped in `acquire_concurrency_slot()` like every other endpoint in this module, for the SAME uniform pre-authentication ordering (condition 5) -- even though this endpoint's own `_authenticate` call is the only gate it ever passes through (unchanged, pre-existing design: this stub never reaches `session.capabilities`/`.transact`/etc., so it never touches `ApplicationCell._limit_gate` either, before or after this WP).
    # history: CH-0238
    service: HttpService = request.app.state.service
    with service.acquire_concurrency_slot():
        await run_in_threadpool(_authenticate, request)
        raise CapabilityError(
            "audit evidence query requires control/audit authority this peer does not expose here",
            details=violation("capability"),
        )


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
