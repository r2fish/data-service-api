"""A reference client that composes every request from the contract document
alone.

Inputs: the contract (`spec/data-service-api.v1.json`) and its derived
operation catalog (`spec/OPERATION_CATALOG.json`) as two parsed documents, the
base URL of the surface the credential is for, one bearer secret, and a send
function. The send function is the only way out of this module:

    send(method, url, headers, body) -> (status, headers, body)

`headers` is a tuple of (name, value) pairs, `body` is `bytes` or `None`, and
the return value is the status, the response's (name, value) pairs and its
body as `bytes`. The function carries the request exactly as given and
follows no redirect; this module never reads the status.

What the module does, each step from a statement the contract makes:

- It names no operation, path, method, schema or header shape the contract
  does not state. The operation to call is a caller-supplied catalog name; its
  method, path, roles and schema names are read from the catalog.
- The URL of an operation is formed as `versioning.url_composition` states:
  the base URL of the operation's surface, minus that surface's own base path
  at its end, plus the operation's whole path. An entry derived from
  `control_endpoints` is named with the `control.` prefix
  (`definitions.OperationCatalogEntry.description`) and belongs to the control
  surface; an entry of `endpoints` whose name `control_endpoints` also carries
  is an alias, for which no URL is formed. Where the base URL does not end in
  its surface's base path, or the surface is not declared, nothing is sent.
- A placeholder in a path is filled with the caller's value, percent-encoded
  so that every character outside the unreserved set is encoded
  (`endpoint_fields_note.path`).
- The credential header is `Authorization` with the scheme from
  `security.schemes.application_credential` and the secret, separated by one
  space. A body is sent with `Content-Type` set to `media_type`.
- Every request body is validated against the operation's request schema
  before it is sent; nothing is sent for a body that does not conform.
- A response is classified by the media type of its `Content-Type`, parameters
  ignored and compared case-insensitively (`errors.response_classification`):
  `errors.content_type` is a failure read by its `code` once the body has the
  keys and value types `errors.shape` names; `media_type` is a success read
  against the operation's response schema; every other response, and every one
  of these that does not meet its condition, is a failure the client does not
  interpret and reads neither a `code` nor a result from. The HTTP status
  decides nothing.
- The first exchange is the capability document: its operation name comes from
  the caller like any other, its response is validated against that operation's
  response schema and only then read for `contract_version`, `role` and
  `surfaces`. Until it has been read, no other operation is sent. The contract
  version of the contract, of the catalog and of the document must agree. The
  role the document states is the role the credential has; an operation whose
  catalog roles do not include it is not sent.
- `operation_catalog_url` is never requested; the catalog is an input.

A failure carries no secret: an exception built here names no header value,
no response body and no response header.

`OUT_OF_CONTRACT_KNOWLEDGE` lists what this module knows that no contract
statement provides. `test_reference_client.py` reads this module's source and
holds every string constant in it to a closed set.
"""
from __future__ import annotations

import ipaddress
import json
from collections.abc import Callable, Iterable, Mapping
from string import Formatter
from typing import Any
from urllib.parse import quote, urlsplit

from schema_check import validate

Send = Callable[[str, str, tuple, bytes | None], tuple]

CONTROL_PREFIX = "control."
AUTHORIZATION = "Authorization"
CONTENT_TYPE = "Content-Type"

# What this client does that the contract does not state. Each key names a row
# of the reference-client design's table of knowledge outside the contract.
OUT_OF_CONTRACT_KNOWLEDGE = {
    "N-15": (
        "A base URL that is not https carries no credential, except that http "
        "is accepted when its host is a loopback address, localhost or a name "
        "under .invalid, so that the plugs the conformance suite runs, which "
        "do not terminate TLS, can be driven."
    ),
}


class ReferenceClientError(Exception):
    """Base of every failure this module raises."""


class RequestRefused(ReferenceClientError):
    """Nothing was sent: the request could not be formed from the contract, or
    the client is not in a state to send it."""


class ContractMismatch(ReferenceClientError):
    """The capability document does not agree with the contract in hand."""


class ResponseFailure(ReferenceClientError):
    """A request was sent and its response is a failure."""


class ProblemResponse(ResponseFailure):
    """A failure the contract defines: `code` was read from a body that has the
    shape `errors.shape` names. `problem` is that parsed body; it is not part
    of the exception's text."""

    def __init__(self, code: str, problem: Mapping) -> None:
        super().__init__(code)
        self.code = code
        self.problem = problem


class UninterpretedResponse(ResponseFailure):
    """A failure the client does not interpret; it carries no `code`."""


class ReferenceClient:
    def __init__(
        self,
        contract: Mapping,
        catalog: Mapping,
        base_url: str,
        secret: str,
        send: Send,
    ) -> None:
        self._contract = contract
        self._catalog = catalog
        self._send = send
        self._data_base_url = base_url
        self._control_base_url: str | None = None
        self._entries = {entry["name"]: entry for entry in catalog["operations"]}
        scheme = contract["security"]["schemes"]["application_credential"]["scheme"]
        self._authorization = " ".join((scheme, secret))
        self._role: str | None = None

    def __repr__(self) -> str:
        return type(self).__name__

    @property
    def role(self) -> str | None:
        return self._role

    def fetch_capabilities(self, operation: str) -> dict:
        """Send the capability-document operation, validate its response
        against that operation's response schema, then read it. Until this has
        returned, `call` sends nothing."""
        self._role = None
        self._control_base_url = None
        versions = {self._contract["contract_version"], self._catalog["contract_version"]}
        if len(versions) != 1:
            raise ContractMismatch("the contract and its operation catalog declare different contract versions")
        document = self._exchange(operation, None, None)
        if not isinstance(document, dict) or document.get("contract_version") not in versions:
            raise ContractMismatch("the capability document declares another contract version than the contract")
        role = document.get("role")
        if not isinstance(role, str):
            raise ContractMismatch("the capability document names no role")
        surfaces = document.get("surfaces")
        control = surfaces.get("control") if isinstance(surfaces, dict) else None
        self._control_base_url = control["base_url"] if isinstance(control, dict) else None
        self._role = role
        return document

    def call(self, operation: str, *, path_values: Mapping[str, str] | None = None, body: Any = None) -> Any:
        """Send one operation and return its parsed success body. A failure
        raises: `RequestRefused` before anything is sent, `ProblemResponse` for
        a failure read by its `code`, `UninterpretedResponse` otherwise."""
        if self._role is None:
            raise RequestRefused("the capability document has not been read")
        return self._exchange(operation, path_values, body)

    def _exchange(self, operation: str, path_values: Mapping[str, str] | None, body: Any) -> Any:
        entry, on_control = self._locate(operation)
        if self._role is not None and self._role not in entry["roles"]:
            raise RequestRefused("the credential's role is not among the operation's roles")
        base_url, base_path = self._surface(on_control)
        url = self._compose(base_url, base_path, entry["path"], path_values)
        self._require_secure(url)
        request_schema = self._schema(entry["request_schema"])
        response_schema = self._schema(entry["response_schema"])
        headers = [(AUTHORIZATION, self._authorization)]
        payload = None
        if request_schema is None:
            if body is not None:
                raise RequestRefused("the operation takes no request body")
        else:
            if body is None:
                raise RequestRefused("the operation requires a request body")
            violations = validate(body, request_schema, self._contract)
            if violations:
                raise RequestRefused(
                    "the request body does not conform to the operation's request schema at: "
                    + ", ".join(violation.path for violation in violations)
                )
            payload = json.dumps(body).encode()
            headers.append((CONTENT_TYPE, self._contract["media_type"]))
        _status, response_headers, raw = self._send(entry["method"], url, tuple(headers), payload)
        return self._read(response_headers, raw, response_schema)

    def _locate(self, operation: str) -> tuple[Mapping, bool]:
        entry = self._entries.get(operation)
        if entry is None:
            raise RequestRefused("the operation is not in the operation catalog")
        if operation.startswith(CONTROL_PREFIX):
            if operation[len(CONTROL_PREFIX):] not in self._contract["control_endpoints"]:
                raise RequestRefused("the operation is not derived from the contract's control endpoints")
            return entry, True
        if operation not in self._contract["endpoints"]:
            raise RequestRefused("the operation is not derived from the contract's endpoints")
        if operation in self._contract["control_endpoints"]:
            raise RequestRefused("the operation is an alias for which no URL is formed")
        return entry, False

    def _surface(self, on_control: bool) -> tuple[str, str]:
        versioning = self._contract["versioning"]
        if on_control:
            if self._control_base_url is None:
                raise RequestRefused("the control surface is not declared")
            return self._control_base_url, versioning["control_base_path"]
        return self._data_base_url, versioning["base_path"]

    @staticmethod
    def _compose(base_url: str, base_path: str, path: str, path_values: Mapping[str, str] | None) -> str:
        if not base_url.endswith(base_path):
            raise RequestRefused("the base URL does not end with its surface's base path")
        values = dict(path_values or {})
        filled = ""
        placeholders = []
        for literal, field, _spec, _conversion in Formatter().parse(path):
            filled += literal
            if field is not None:
                placeholders.append(field)
                if not isinstance(values.get(field), str):
                    raise RequestRefused("a placeholder of the path has no string value")
                filled += quote(values[field], safe="")
        if set(values) != set(placeholders):
            raise RequestRefused("the values given do not match the path's placeholders")
        return base_url[: len(base_url) - len(base_path)] + filled

    @staticmethod
    def _require_secure(url: str) -> None:
        parts = urlsplit(url)
        if parts.scheme == "https":
            return
        if parts.scheme == "http" and _is_test_host(parts.hostname):
            return
        raise RequestRefused("the URL is not https and its host is not one a test plug is reached at")

    def _schema(self, name: str | None) -> Mapping | None:
        if name is None:
            return None
        schema = self._contract["schemas"].get(name)
        if schema is None:
            raise RequestRefused("the operation names a schema the contract does not define")
        return schema

    def _read(self, headers: Iterable, raw: Any, response_schema: Mapping | None) -> Any:
        media_type = _media_type(headers)
        if media_type is None or not isinstance(raw, (bytes, bytearray)):
            raise UninterpretedResponse("the response has no media type to classify it by")
        failure = media_type == self._contract["errors"]["content_type"].lower()
        if not failure and media_type != self._contract["media_type"].lower():
            raise UninterpretedResponse("the response's media type is neither a failure's nor a success's")
        try:
            parsed = json.loads(raw)
        except ValueError:
            raise UninterpretedResponse("the response body is not JSON") from None
        if failure:
            shape = self._contract["errors"]["shape"]
            if not isinstance(parsed, dict) or any(
                key not in parsed or validate(parsed[key], {"type": kind}, self._contract)
                for key, kind in shape.items()
            ):
                raise UninterpretedResponse("the failure body does not have the shape the contract names")
            raise ProblemResponse(parsed["code"], parsed)
        if response_schema is None or validate(parsed, response_schema, self._contract):
            raise UninterpretedResponse("the success body does not conform to the operation's response schema")
        return parsed


def _media_type(headers: Iterable) -> str | None:
    for name, value in headers:
        if name.lower() == CONTENT_TYPE.lower():
            return value.split(";")[0].strip().lower()
    return None


def _is_test_host(host: str | None) -> bool:
    if host is None:
        return False
    if host == "localhost" or host.endswith(".invalid"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False
