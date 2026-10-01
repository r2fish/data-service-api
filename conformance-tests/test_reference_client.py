"""Unit tests for `reference_client.py`, driven by a recording fake send
function, and the static pin on that module's source.

These are suite self-tests, not condition tests: they carry no
`@pytest.mark.condition(...)` marker. They never reach a peer; the fake send
function returns scripted responses and records every request it is handed.

A test that pins a failure also pins the failure's kind. The client has two
kinds of failure that follow a send: `ProblemResponse`, which read a `code`
from a body that has the shape `errors.shape` names, and
`UninterpretedResponse`, which read nothing and carries no `code`. A failure
before any send is `RequestRefused`; a capability document that disagrees with
the contract is `ContractMismatch`. Asserting only "an exception" would let a
change that swaps the kind of a failure pass.

The static pin (`test_client_source_holds_to_the_closed_set_of_literals`)
reads the client's source and holds every string and bytes constant in it
(module, class and function docstrings excepted) to one of four kinds:

- a key name that is the last segment of a dotted path in
  `CONTRACT_KEY_PATHS`, each of which this module resolves in the contract or
  the catalog (`test_every_contract_key_path_resolves`);
- a literal in `PROSE_LITERALS`, each with where the contract (or, for the
  scheme and host words, the client's own `OUT_OF_CONTRACT_KNOWLEDGE` row)
  states it;
- a constant that is a part of the text of a failure: a string, the constant
  part of an f-string, or a `join` separator, in the arguments of an
  exception's construction that is itself the operand of a `raise`, the
  exception being a class defined in the client. A key or call argument inside
  such an argument is held to the other kinds; `.args` and `__doc__` are not
  used in the client, so a text cannot be carried out of its `raise`;
- a key or value of `OUT_OF_CONTRACT_KNOWLEDGE` itself.

A constant equal to any operation name, method or path in the catalog, to the
name without its `control.` prefix, or to the name of any schema or definition
in the contract is red in every kind (`forbidden_names`). The client may import
only the standard library and `schema_check`.
"""
from __future__ import annotations

import ast
import copy
import json
import sys
from pathlib import Path

import pytest

import reference_client
from adapter import REPO_ROOT, load_contract
from reference_client import (
    ContractMismatch,
    ProblemResponse,
    ReferenceClient,
    ReferenceClientError,
    RequestRefused,
    UninterpretedResponse,
)
from schema_check import validate

CONTRACT = load_contract()
CATALOG = json.loads((REPO_ROOT / "spec" / "OPERATION_CATALOG.json").read_text())

DATA_BASE = "https://db.example.invalid/tenant-a/v1"
CONTROL_BASE = "https://db.example.invalid/tenant-a/control/v1"
SECRET = "sentinel-secret-7d2e41"
CAPABILITIES = "capabilities"
CONTROL_CAPABILITIES = "control.control_capabilities"
MEDIA_TYPE = CONTRACT["media_type"]
PROBLEM_TYPE = CONTRACT["errors"]["content_type"]

# The right-hand column of the design's table of knowledge outside the
# contract, after the contract states everything else: one row.
SECTION_4_1_ROWS = frozenset({"N-15"})

# (document, dotted path). `*` stands for every element of a list. A string the
# client carries as a key name must be the last segment of one of these.
CONTRACT_KEY_PATHS = (
    ("contract", "contract_version"),
    ("contract", "media_type"),
    ("contract", "security"),
    ("contract", "security.schemes"),
    ("contract", "security.schemes.application_credential"),
    ("contract", "security.schemes.application_credential.scheme"),
    ("contract", "versioning"),
    ("contract", "versioning.base_path"),
    ("contract", "versioning.control_base_path"),
    ("contract", "endpoints"),
    ("contract", "control_endpoints"),
    ("contract", "schemas"),
    ("contract", "errors"),
    ("contract", "errors.content_type"),
    ("contract", "errors.shape"),
    ("contract", "errors.shape.code"),
    ("contract", "errors.codes"),
    ("contract", "schemas.CapabilityDocument.type"),
    ("contract", "schemas.CapabilityDocument.properties.role"),
    ("contract", "schemas.CapabilityDocument.properties.surfaces"),
    ("contract", "schemas.CapabilityDocument.properties.surfaces.properties.control"),
    ("contract", "schemas.CapabilityDocument.properties.surfaces.properties.control.properties.base_url"),
    ("catalog", "contract_version"),
    ("catalog", "operations"),
    ("catalog", "operations.*.name"),
    ("catalog", "operations.*.method"),
    ("catalog", "operations.*.path"),
    ("catalog", "operations.*.roles"),
    ("catalog", "operations.*.request_schema"),
    ("catalog", "operations.*.response_schema"),
)

# (literal, where it comes from, a path in the contract whose string value
# contains the literal -- or None). A source that is "client table" is the
# literal's presence in `OUT_OF_CONTRACT_KNOWLEDGE["N-15"]`.
PROSE_LITERALS = (
    ("Authorization", "security.schemes.application_credential.description: 'Authorization: Bearer <secret>'",
     "security.schemes.application_credential.description"),
    ("Content-Type", "media_type_note: 'named in that request's Content-Type header'", "media_type_note"),
    ("control.", "definitions.OperationCatalogEntry.description: the prefix of an entry derived from control_endpoints",
     "definitions.OperationCatalogEntry.description"),
    (" ", "security.schemes.application_credential.description: 'Bearer <secret>', scheme and secret one space apart",
     "security.schemes.application_credential.description"),
    (";", "errors.response_classification: 'parameters such as charset ignored' -- the delimiter HTTP semantics "
     "(external_standards) puts before a media type's parameters", None),
    ("", "endpoint_fields_note.path: every character outside the unreserved set is encoded, so no character is "
     "kept safe; also the empty start of the path being filled", None),
    ("https", "client table N-15", "client table"),
    ("http", "client table N-15", "client table"),
    (".invalid", "client table N-15", "client table"),
)


# ---------------------------------------------------------------------------
# A recording fake send function and the documents it serves
# ---------------------------------------------------------------------------


class Wire:
    """Records every request and answers each from a script, in order. A send
    with nothing left to answer it is a test failure."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.sent = []

    def __call__(self, method, url, headers, body):
        self.sent.append((method, url, headers, body))
        assert self.responses, f"unscripted send: {method} {url}"
        return self.responses.pop(0)

    @property
    def urls(self):
        return [url for _method, url, _headers, _body in self.sent]


def respond(document, *, content_type=MEDIA_TYPE, status=200, headers=()):
    pairs = (("Content-Type", content_type),) if content_type is not None else ()
    return status, pairs + tuple(headers), json.dumps(document).encode()


def problem_body(code="VALIDATION_FAILED", **override):
    body = {"type": "about:blank", "code": code, "message": "synthetic failure", "request_id": "req-0001", "details": {}}
    body.update(override)
    return body


def capability_document(*, role="runtime", version=None, control_base=CONTROL_BASE, **extra):
    document = {
        "contract_version": version or CONTRACT["contract_version"],
        "capabilities": {"structured_query": {"status": "enabled"}},
        "limits": {"batch_items": 100},
        "limit_enforcement": {"batch_items": "enforced"},
        "authorization_propagation_bound_ms": 0,
        "role": role,
        "surfaces": {"data": {"base_url": DATA_BASE}},
    }
    if control_base is not None:
        document["surfaces"]["control"] = {"base_url": control_base}
    document.update(extra)
    return document


QUERY_RESULT = {"items": [], "next_page": None}
QUERY_BODY = {"select": ["id"]}


def build(*responses, base_url=DATA_BASE, contract=CONTRACT, catalog=CATALOG, secret=SECRET):
    wire = Wire(*responses)
    return ReferenceClient(contract, catalog, base_url, secret, wire), wire


def ready(*responses, role="runtime", **document_options):
    """A client whose capability document has been read; the first recorded
    request is that read."""
    client, wire = build(respond(capability_document(role=role, **document_options)), *responses)
    client.fetch_capabilities(CAPABILITIES)
    assert len(wire.sent) == 1
    return client, wire


def raised(function, expected=ReferenceClientError):
    with pytest.raises(expected) as info:
        function()
    return info.value


# ---------------------------------------------------------------------------
# Behaviour
# ---------------------------------------------------------------------------


def test_request_body_that_violates_its_schema_is_refused_before_anything_is_sent():
    client, wire = ready(respond(QUERY_RESULT))
    cases = {
        "required key missing": ("query", {"entity": "notes"}, {}),
        "unknown key": ("query", {"entity": "notes"}, {"select": ["id"], "bogus": 1}),
        "bound exceeded": ("query", {"entity": "notes"}, {"select": ["id"] * 101}),
        "maxLength exceeded": (
            "mutate",
            {"entity": "notes"},
            {"operations": [{"operation": "insert", "values": {"a": 1}}], "idempotency_key": "k" * 129},
        ),
        "maxProperties exceeded": (
            "mutate",
            {"entity": "notes"},
            {"operations": [{"operation": "insert", "values": {f"f{i}": i for i in range(101)}}]},
        ),
    }
    for label, (operation, values, body) in cases.items():
        error = raised(lambda: client.call(operation, path_values=values, body=body))
        assert type(error) is RequestRefused, label
    assert len(wire.sent) == 1, "a refused request was sent"
    # A conforming body goes out exactly once, so the refusals above are the
    # schema's doing and not a client that refuses everything.
    assert client.call("query", path_values={"entity": "notes"}, body=QUERY_BODY) == QUERY_RESULT
    assert len(wire.sent) == 2


def test_success_response_that_violates_its_schema_is_an_uninterpreted_failure():
    client, wire = ready(respond({"items": []}), respond(QUERY_RESULT))
    error = raised(lambda: client.call("query", path_values={"entity": "notes"}, body=QUERY_BODY))
    assert type(error) is UninterpretedResponse
    assert not hasattr(error, "code")
    assert len(wire.sent) == 2
    assert client.call("query", path_values={"entity": "notes"}, body=QUERY_BODY) == QUERY_RESULT


def test_urls_are_formed_from_the_surface_base_url_minus_its_own_base_path():
    for data_base, control_base, expected_data, expected_control in (
        (
            DATA_BASE,
            CONTROL_BASE,
            ["https://db.example.invalid/tenant-a/v1/capabilities", "https://db.example.invalid/tenant-a/v1/data/notes/query"],
            ["https://db.example.invalid/tenant-a/v1/capabilities", "https://db.example.invalid/tenant-a/control/v1/capabilities"],
        ),
        (
            "https://db.example.invalid/v1",
            "https://db.example.invalid/control/v1",
            ["https://db.example.invalid/v1/capabilities", "https://db.example.invalid/v1/data/notes/query"],
            ["https://db.example.invalid/v1/capabilities", "https://db.example.invalid/control/v1/capabilities"],
        ),
    ):
        data, data_wire = build(
            respond(capability_document(role="developer", control_base=control_base)),
            respond(QUERY_RESULT),
            base_url=data_base,
        )
        data.fetch_capabilities(CAPABILITIES)
        data.call("query", path_values={"entity": "notes"}, body=QUERY_BODY)
        assert data_wire.urls == expected_data

        control, control_wire = build(
            respond(capability_document(role="control", control_base=control_base)),
            respond(capability_document(role="control", control_base=control_base)),
            base_url=data_base,
        )
        control.fetch_capabilities(CAPABILITIES)
        control.call(CONTROL_CAPABILITIES)
        assert control_wire.urls == expected_control


def test_placeholder_values_are_percent_encoded_in_the_recorded_url():
    values = {
        "a/b": "a%2Fb",
        "a?b": "a%3Fb",
        "a#b": "a%23b",
        "a%b": "a%25b",
        "a b": "a%20b",
        "plain_1": "plain_1",
    }
    client, wire = ready(*[respond(QUERY_RESULT) for _ in values])
    for value in values:
        client.call("query", path_values={"entity": value}, body=QUERY_BODY)
    assert wire.urls[1:] == [f"{DATA_BASE}/data/{encoded}/query" for encoded in values.values()]


def test_authorization_header_is_built_from_the_contract_scheme():
    scheme = CONTRACT["security"]["schemes"]["application_credential"]["scheme"]
    client, wire = ready(respond(QUERY_RESULT))
    client.call("query", path_values={"entity": "notes"}, body=QUERY_BODY)
    assert wire.sent[0][2] == (("Authorization", f"{scheme} {SECRET}"),)
    assert wire.sent[1][2][0] == ("Authorization", f"{scheme} {SECRET}")
    assert wire.sent[0][2][0][1].startswith("Bearer ")

    other = copy.deepcopy(CONTRACT)
    other["security"]["schemes"]["application_credential"]["scheme"] = "Opaque"
    client, wire = build(respond(capability_document()), contract=other)
    client.fetch_capabilities(CAPABILITIES)
    assert wire.sent[0][2] == (("Authorization", f"Opaque {SECRET}"),)


def test_capability_document_declaring_another_contract_version_is_refused_at_the_first_step():
    client, wire = build(respond(capability_document(version="0.0.1")))
    error = raised(lambda: client.fetch_capabilities(CAPABILITIES))
    assert type(error) is ContractMismatch
    assert client.role is None
    assert len(wire.sent) == 1
    assert type(raised(lambda: client.call("query", path_values={"entity": "notes"}, body=QUERY_BODY))) is RequestRefused

    other_catalog = dict(CATALOG, contract_version="0.0.1")
    client, wire = build(respond(capability_document()), catalog=other_catalog)
    assert type(raised(lambda: client.fetch_capabilities(CAPABILITIES))) is ContractMismatch
    assert wire.sent == []

    client, wire = build(respond(capability_document()))
    assert client.fetch_capabilities(CAPABILITIES)["contract_version"] == CONTRACT["contract_version"]
    assert client.role == "runtime"


def test_no_failure_text_carries_the_secret():
    def scenario_refused_body():
        client, _wire = ready()
        client.call("query", path_values={"entity": "notes"}, body={})

    def scenario_role():
        client, _wire = ready()
        client.call("schema", body={"operation": "create_entity", "entity": "notes"})

    def scenario_unknown_operation():
        client, _wire = ready()
        client.call("no_such_operation")

    def scenario_placeholder():
        client, _wire = ready()
        client.call("query", path_values={}, body=QUERY_BODY)

    def scenario_insecure_url():
        client, _wire = build(base_url="http://db.example.test/v1")
        client.fetch_capabilities(CAPABILITIES)

    def scenario_version():
        client, _wire = build(respond(capability_document(version="0.0.1")))
        client.fetch_capabilities(CAPABILITIES)

    def scenario_problem():
        client, _wire = ready(respond(problem_body(), content_type=PROBLEM_TYPE, status=409))
        client.call("query", path_values={"entity": "notes"}, body=QUERY_BODY)

    def scenario_uninterpreted():
        client, _wire = ready(respond(QUERY_RESULT, content_type="text/html", status=404))
        client.call("query", path_values={"entity": "notes"}, body=QUERY_BODY)

    def scenario_schema_violation():
        client, _wire = ready(respond({"items": []}))
        client.call("query", path_values={"entity": "notes"}, body=QUERY_BODY)

    scenarios = [
        scenario_refused_body,
        scenario_role,
        scenario_unknown_operation,
        scenario_placeholder,
        scenario_insecure_url,
        scenario_version,
        scenario_problem,
        scenario_uninterpreted,
        scenario_schema_violation,
    ]
    client, wire = ready()
    assert SECRET in wire.sent[0][2][0][1], "the secret under test is not the one the client sends"
    for scenario in scenarios:
        error = raised(scenario)
        for text in (str(error), repr(error), repr(error.args)):
            assert SECRET not in text, scenario.__name__
    assert SECRET not in repr(client) and SECRET not in str(client)


def test_failure_content_type_with_a_parameter_is_read_by_its_code():
    client, _wire = ready(respond(problem_body("CODE_ONE"), content_type=f"{PROBLEM_TYPE}; charset=utf-8", status=409))
    error = raised(lambda: client.call("query", path_values={"entity": "notes"}, body=QUERY_BODY))
    assert type(error) is ProblemResponse
    assert error.code == "CODE_ONE"
    assert error.problem["message"] == "synthetic failure"


def test_response_that_is_neither_failure_nor_success_is_an_uninterpreted_failure():
    client, wire = ready(respond(QUERY_RESULT, content_type="text/html", status=404))
    error = raised(lambda: client.call("query", path_values={"entity": "notes"}, body=QUERY_BODY))
    assert type(error) is UninterpretedResponse
    assert not hasattr(error, "code")
    assert len(wire.sent) == 2
    # A body that has the shape of a failure is not read for its code when the
    # media type is not the contract's failure type.
    client, _wire = ready(respond(problem_body("CODE_FOUR"), content_type="text/html", status=409))
    error = raised(lambda: client.call("query", path_values={"entity": "notes"}, body=QUERY_BODY))
    assert type(error) is UninterpretedResponse
    assert not hasattr(error, "code")


def test_uninterpreted_failure_text_carries_neither_the_response_body_nor_its_headers():
    body_marker = "body-marker-5b1c"
    header_marker = "header-marker-9e07"
    responses = [
        (404, (("Content-Type", "text/html"), ("X-Marker", header_marker)), f"<html>{body_marker}</html>".encode()),
        (200, (("X-Marker", header_marker),), f'{{"items": [], "next_page": null, "x": "{body_marker}"}}'.encode()),
        (502, (("Content-Type", MEDIA_TYPE), ("X-Marker", header_marker)), f"{body_marker} not json".encode()),
    ]
    for response in responses:
        client, _wire = ready(response)
        error = raised(lambda: client.call("query", path_values={"entity": "notes"}, body=QUERY_BODY))
        assert type(error) is UninterpretedResponse
        for text in (str(error), repr(error), repr(error.args)):
            assert body_marker not in text and header_marker not in text


def test_failure_body_is_read_by_its_code_whatever_the_status():
    client, _wire = ready(respond(problem_body("CODE_TWO"), content_type=PROBLEM_TYPE, status=200))
    error = raised(lambda: client.call("query", path_values={"entity": "notes"}, body=QUERY_BODY))
    assert type(error) is ProblemResponse
    assert error.code == "CODE_TWO"
    # And the other way: a success body is a success whatever the status.
    client, _wire = ready(respond(QUERY_RESULT, status=409))
    assert client.call("query", path_values={"entity": "notes"}, body=QUERY_BODY) == QUERY_RESULT


def test_declared_operation_catalog_url_is_never_requested():
    catalog_url = "https://cdn.example.invalid/catalog/operation-catalog.json"
    client, wire = ready(
        respond(QUERY_RESULT),
        respond(QUERY_RESULT),
        operation_catalog_url=catalog_url,
    )
    client.call("query", path_values={"entity": "notes"}, body=QUERY_BODY)
    assert len(wire.sent) == 2
    assert all(catalog_url not in url for url in wire.urls)
    assert all(not url.startswith("https://cdn.example.invalid") for url in wire.urls)


def test_table_of_knowledge_outside_the_contract_has_exactly_the_expected_rows():
    table = reference_client.OUT_OF_CONTRACT_KNOWLEDGE
    assert set(table) == SECTION_4_1_ROWS
    assert all(isinstance(value, str) and value for value in table.values())


def test_base_url_that_is_not_https_is_refused_unless_it_is_a_test_host():
    for refused in (
        "http://db.example.test/v1",
        "ftp://db.example.invalid/v1",
        "http://[2001:db8::7]/v1",
        "http://localhost/v1",
        "http://localhost:8080/v1",
    ):
        client, wire = build(base_url=refused)
        error = raised(lambda: client.fetch_capabilities(CAPABILITIES))
        assert type(error) is RequestRefused, refused
        assert wire.sent == [], refused
    for allowed in ("http://db.example.invalid/v1", "http://127.0.0.1:8080/v1", "http://[::1]:8080/v1"):
        client, wire = build(respond(capability_document()), base_url=allowed)
        client.fetch_capabilities(CAPABILITIES)
        assert wire.urls == [f"{allowed}/capabilities"], allowed


def test_base_url_that_does_not_end_with_the_base_path_is_refused_before_sending():
    for refused in (
        "https://db.example.invalid",
        "https://db.example.invalid/tenant-a",
        "https://db.example.invalid/tenant-a/v1/",
        "https://db.example.invalid/tenant-a/v1/extra",
    ):
        client, wire = build(base_url=refused)
        error = raised(lambda: client.fetch_capabilities(CAPABILITIES))
        assert type(error) is RequestRefused, refused
        assert wire.sent == [], refused


def test_base_url_with_a_query_or_a_fragment_is_refused_before_sending():
    data_refused = (
        "https://db.example.invalid/x?q=/v1",
        "https://db.example.invalid/x#/v1",
        "https://db.example.invalid/v1?q=/v1",
        "https://db.example.invalid/v1#/v1",
        "https://db.example.invalid/v1?",
        "https://db.example.invalid/v1#",
    )
    for refused in data_refused:
        client, wire = build(base_url=refused)
        error = raised(lambda: client.fetch_capabilities(CAPABILITIES))
        assert type(error) is RequestRefused, refused
        assert wire.sent == [], refused
    # The same check holds for the control surface's base URL, which the
    # capability document declares.
    for refused in (
        "https://db.example.invalid/control/v1?q=/control/v1",
        "https://db.example.invalid/control/v1#/control/v1",
        "https://db.example.invalid/x?q=/control/v1",
    ):
        client, wire = ready(role="control", control_base=refused)
        error = raised(lambda: client.call(CONTROL_CAPABILITIES))
        assert type(error) is RequestRefused, refused
        assert len(wire.sent) == 1, refused


def test_control_operation_is_refused_when_the_document_declares_no_control_surface():
    client, wire = ready(role="control", control_base=None)
    error = raised(lambda: client.call(CONTROL_CAPABILITIES))
    assert type(error) is RequestRefused
    assert len(wire.sent) == 1


def test_alias_operation_is_refused_without_sending_even_where_the_control_surface_is_declared():
    audit_body = {"limit": 10}
    assert validate(audit_body, CONTRACT["schemas"]["AuditQueryRequest"], CONTRACT) == []
    client, wire = ready(respond({"events": []}), respond({"events": []}), role="control")
    error = raised(lambda: client.call("audit_query", body=audit_body))
    assert type(error) is RequestRefused
    assert len(wire.sent) == 1
    # The same body, named by the control endpoint the alias stands for, is sent.
    assert client.call("control.audit_query", body=audit_body) == {"events": []}
    assert wire.urls[-1] == f"{CONTROL_BASE}/audit/query"
    assert "audit_query" in CONTRACT["endpoints"] and "audit_query" in CONTRACT["control_endpoints"]


def test_operation_whose_roles_exclude_the_documents_role_is_refused_without_sending():
    client, wire = ready(role="runtime")
    error = raised(lambda: client.call("schema", body={"operation": "create_entity", "entity": "notes"}))
    assert type(error) is RequestRefused
    assert len(wire.sent) == 1
    developer, developer_wire = ready(
        respond({"committed": True, "revision": "r1"}),
        role="developer",
    )
    developer.call("schema", body={"operation": "create_entity", "entity": "notes"})
    assert len(developer_wire.sent) == 2


def test_request_with_a_body_carries_the_media_type_as_its_content_type():
    client, wire = ready(respond(QUERY_RESULT), respond(capability_document()))
    client.call("query", path_values={"entity": "notes"}, body=QUERY_BODY)
    client.call(CAPABILITIES)
    with_body, without_body = wire.sent[1], wire.sent[2]
    assert ("Content-Type", MEDIA_TYPE) in with_body[2]
    assert json.loads(with_body[3]) == QUERY_BODY
    assert all(name != "Content-Type" for name, _value in without_body[2])
    assert without_body[3] is None
    assert MEDIA_TYPE == "application/json"


def test_failure_content_type_is_compared_without_regard_to_case():
    client, _wire = ready(respond(problem_body("CODE_THREE"), content_type="Application/Problem+JSON", status=409))
    error = raised(lambda: client.call("query", path_values={"entity": "notes"}, body=QUERY_BODY))
    assert type(error) is ProblemResponse
    assert error.code == "CODE_THREE"
    client, _wire = ready(respond(QUERY_RESULT, content_type="APPLICATION/JSON"))
    assert client.call("query", path_values={"entity": "notes"}, body=QUERY_BODY) == QUERY_RESULT


def test_response_without_a_content_type_is_an_uninterpreted_failure():
    client, wire = ready(respond(QUERY_RESULT, content_type=None))
    error = raised(lambda: client.call("query", path_values={"entity": "notes"}, body=QUERY_BODY))
    assert type(error) is UninterpretedResponse
    assert not hasattr(error, "code")
    assert len(wire.sent) == 2
    client, _wire = ready(respond(problem_body("CODE_FIVE"), content_type=None, status=409))
    error = raised(lambda: client.call("query", path_values={"entity": "notes"}, body=QUERY_BODY))
    assert type(error) is UninterpretedResponse
    assert not hasattr(error, "code")


def test_response_with_two_content_type_headers_is_an_uninterpreted_failure():
    # Each body is one the first header's type reads and the last header's type
    # does not, or the other way round, so taking either header alone would
    # turn the response into a result or a `code`.
    problem = json.dumps(problem_body("CODE_SIX")).encode()
    result = json.dumps(QUERY_RESULT).encode()
    pairs = (("Content-Type", PROBLEM_TYPE), ("Content-Type", MEDIA_TYPE))
    cases = 0
    for headers in (pairs, pairs[::-1]):
        for body in (problem, result):
            client, wire = ready((409, headers, body))
            error = raised(lambda: client.call("query", path_values={"entity": "notes"}, body=QUERY_BODY))
            assert type(error) is UninterpretedResponse
            assert not hasattr(error, "code")
            assert len(wire.sent) == 2
            cases += 1
    assert cases == 4


def test_failure_body_that_does_not_have_the_named_shape_is_not_read_for_a_code():
    keys = list(CONTRACT["errors"]["shape"])
    assert "code" in keys and len(keys) > 1
    bodies = []
    for missing in keys:
        if missing != "code":
            body = problem_body()
            del body[missing]
            bodies.append(body)
    bodies.append(problem_body(details="not an object"))
    bodies.append(problem_body(code=12))
    bodies.append(["not", "an", "object"])
    for body in bodies:
        client, _wire = ready(respond(body, content_type=PROBLEM_TYPE, status=409))
        error = raised(lambda: client.call("query", path_values={"entity": "notes"}, body=QUERY_BODY))
        assert type(error) is UninterpretedResponse
        assert not hasattr(error, "code")


def test_redirect_is_not_followed():
    target = "https://elsewhere.example.invalid/landing"
    client, wire = ready(
        (302, (("Location", target),), b""),
        respond(QUERY_RESULT),
    )
    error = raised(lambda: client.call("query", path_values={"entity": "notes"}, body=QUERY_BODY))
    assert type(error) is UninterpretedResponse
    assert len(wire.sent) == 2
    assert target not in wire.urls


def test_no_operation_is_sent_before_the_capability_document_has_been_read():
    client, wire = build(respond({"items": []}))
    error = raised(lambda: client.call("query", path_values={"entity": "notes"}, body=QUERY_BODY))
    assert type(error) is RequestRefused
    assert wire.sent == []

    # A capability response that violates its schema is not read, even though
    # it carries a role and the contract version.
    invalid = capability_document(role="developer", surprise="not in the schema")
    assert validate(invalid, CONTRACT["schemas"]["CapabilityDocument"], CONTRACT)
    client, wire = build(respond(invalid), respond(QUERY_RESULT))
    error = raised(lambda: client.fetch_capabilities(CAPABILITIES))
    assert type(error) is UninterpretedResponse
    assert client.role is None
    assert type(raised(lambda: client.call("query", path_values={"entity": "notes"}, body=QUERY_BODY))) is RequestRefused
    assert len(wire.sent) == 1

    client, wire = ready(respond(QUERY_RESULT))
    assert client.call("query", path_values={"entity": "notes"}, body=QUERY_BODY) == QUERY_RESULT


def test_problem_text_names_a_code_only_when_the_contract_lists_it():
    listed = sorted(CONTRACT["errors"]["codes"])[0]
    client, _wire = ready(respond(problem_body(listed), content_type=PROBLEM_TYPE, status=409))
    error = raised(lambda: client.call("query", path_values={"entity": "notes"}, body=QUERY_BODY))
    assert type(error) is ProblemResponse
    assert error.code == listed
    assert listed in str(error) and listed in repr(error)

    # A peer, or something ahead of it, that writes the request's credential
    # into `code` gets it nowhere in the text; the attribute still reads it.
    echoed = f"Bearer {SECRET}"
    for unlisted in (SECRET, echoed):
        client, _wire = ready(respond(problem_body(unlisted), content_type=PROBLEM_TYPE, status=409))
        error = raised(lambda: client.call("query", path_values={"entity": "notes"}, body=QUERY_BODY))
        assert type(error) is ProblemResponse
        assert error.code == unlisted
        assert error.problem["code"] == unlisted
        for text in (str(error), repr(error), repr(error.args)):
            assert SECRET not in text


def test_request_body_that_json_cannot_carry_is_refused_before_sending():
    client, wire = ready(respond(QUERY_RESULT))
    for value in (float("nan"), float("inf"), float("-inf")):
        body = {"operations": [{"operation": "insert", "values": {"a": value}}]}
        assert validate(body, CONTRACT["schemas"]["MutationRequest"], CONTRACT) == []
        error = raised(lambda: client.call("mutate", path_values={"entity": "notes"}, body=body))
        assert type(error) is RequestRefused
    assert len(wire.sent) == 1


def test_response_body_with_nan_infinity_or_too_deep_nesting_is_an_uninterpreted_failure():
    depth = 100_000
    bodies = (
        b'{"items": [NaN], "next_page": null}',
        b'{"items": [Infinity], "next_page": null}',
        b'{"items": [-Infinity], "next_page": null}',
        b'{"items": ' + b"[" * depth + b"]" * depth + b', "next_page": null}',
    )
    for body in bodies:
        client, wire = ready((200, (("Content-Type", MEDIA_TYPE),), body))
        error = raised(lambda: client.call("query", path_values={"entity": "notes"}, body=QUERY_BODY))
        assert type(error) is UninterpretedResponse
        assert not hasattr(error, "code")
        assert len(wire.sent) == 2


def test_capability_document_without_a_role_is_refused_and_leaves_the_client_unready():
    document = capability_document()
    del document["role"]
    assert validate(document, CONTRACT["schemas"]["CapabilityDocument"], CONTRACT) == []
    client, wire = build(respond(document))
    error = raised(lambda: client.fetch_capabilities(CAPABILITIES))
    assert type(error) is ContractMismatch
    assert client.role is None
    error = raised(lambda: client.call("query", path_values={"entity": "notes"}, body=QUERY_BODY))
    assert type(error) is RequestRefused
    assert len(wire.sent) == 1


# ---------------------------------------------------------------------------
# Static pin on the client's source
# ---------------------------------------------------------------------------


def _resolve_nodes(document, dotted):
    nodes = [document]
    for segment in dotted.split("."):
        following = []
        for node in nodes:
            if segment == "*":
                if not isinstance(node, list) or not node:
                    return None
                following.extend(node)
            elif isinstance(node, dict) and segment in node:
                following.append(node[segment])
            else:
                return None
        nodes = following
    return nodes


def _documents():
    return {"contract": CONTRACT, "catalog": CATALOG}


def key_names(paths):
    return {path.split(".")[-1] for _document, path in paths}


def forbidden_names(contract, catalog):
    names = set()
    for entry in catalog["operations"]:
        names |= {entry["name"], entry["method"], entry["path"]}
        if entry["name"].startswith("control."):
            names.add(entry["name"][len("control."):])
    return names | set(contract["schemas"]) | set(contract["definitions"])


def _exception_class_names(tree):
    names = {"Exception", "BaseException"}
    classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    grew = True
    defined = set()
    while grew:
        grew = False
        for node in classes:
            bases = {base.id for base in node.bases if isinstance(base, ast.Name)}
            if node.name not in defined and bases and bases <= names:
                names.add(node.name)
                defined.add(node.name)
                grew = True
    return defined


def _docstring_ids(tree):
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                ids.add(id(first.value))
    return ids


def _sentence_part_ids(expression):
    """The string constants of `expression` that are parts of a sentence: a
    string, the constant part of an f-string, either side of a `+`, either
    branch of a conditional, the receiver of a `join`. What an index, a call
    argument or an f-string's expression holds is not a part."""
    ids = set()

    def visit(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            ids.add(id(node))
        elif isinstance(node, ast.JoinedStr):
            ids.update(id(part) for part in node.values if isinstance(part, ast.Constant))
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            visit(node.left)
            visit(node.right)
        elif isinstance(node, ast.IfExp):
            visit(node.body)
            visit(node.orelse)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "join":
            visit(node.func.value)

    visit(expression)
    return ids


def literal_violations(source, *, key_tails, prose, forbidden, stdlib=None):
    """Every way `source` leaves the closed set, each as a short text."""
    stdlib = sys.stdlib_module_names if stdlib is None else stdlib
    tree = ast.parse(source)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] not in stdlib | {"schema_check"}:
                    found.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.level or (node.module or "").split(".")[0] not in stdlib | {"schema_check"}:
                found.append(f"from {'.' * node.level}{node.module} import ...")
        elif isinstance(node, ast.Attribute) and node.attr in ("args", "__doc__"):
            found.append(f"{node.lineno}: .{node.attr} carries a text out of where it is written")
    docstrings = _docstring_ids(tree)
    sentence_parts = set()
    exception_names = _exception_class_names(tree)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Raise)
            and isinstance(node.exc, ast.Call)
            and isinstance(node.exc.func, ast.Name)
            and node.exc.func.id in exception_names
        ):
            for argument in node.exc.args:
                sentence_parts |= _sentence_part_ids(argument)
    in_table = set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "OUT_OF_CONTRACT_KNOWLEDGE" for target in node.targets
        ):
            in_table |= {id(inner) for inner in ast.walk(node.value)}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, (str, bytes)) and id(node) not in docstrings):
            continue
        value = node.value
        if value in forbidden:
            found.append(f"{node.lineno}: {value!r} is a name or path the contract and catalog define")
        elif id(node) in sentence_parts or id(node) in in_table:
            continue
        elif value not in key_tails and value not in prose:
            found.append(f"{node.lineno}: {value!r} is in no allowed set")
    return found


def _checked_constants(source):
    tree = ast.parse(source)
    docstrings = _docstring_ids(tree)
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, (str, bytes)) and id(node) not in docstrings
    ]


def test_every_contract_key_path_resolves():
    assert CONTRACT_KEY_PATHS
    documents = _documents()
    for document, path in CONTRACT_KEY_PATHS:
        assert _resolve_nodes(documents[document], path) is not None, f"{document}: {path}"
    assert not (key_names(CONTRACT_KEY_PATHS) & forbidden_names(CONTRACT, CATALOG))


def test_client_source_holds_to_the_closed_set_of_literals():
    source = Path(reference_client.__file__).read_text()
    key_tails = key_names(CONTRACT_KEY_PATHS)
    prose = {literal for literal, _origin, _path in PROSE_LITERALS}
    forbidden = forbidden_names(CONTRACT, CATALOG)
    assert not (prose & forbidden)

    # The client holds to the closed set.
    assert literal_violations(source, key_tails=key_tails, prose=prose, forbidden=forbidden) == []

    # The prose table's rows state where each literal comes from, and the
    # place resolves.
    client_text = reference_client.OUT_OF_CONTRACT_KNOWLEDGE["N-15"]
    for literal, origin, path in PROSE_LITERALS:
        assert origin
        if path == "client table":
            assert literal in client_text, literal
        elif path is not None:
            [node] = _resolve_nodes(CONTRACT, path)
            assert isinstance(node, str) and literal in node, (literal, path)

    # No row of either table is an unused permission.
    present = set(_checked_constants(source))
    assert present, "the client holds no string constant to check"
    assert key_tails <= present, sorted(key_tails - present)
    assert prose <= present, sorted(prose - present)

    # The check sees what it must: each of these planted violations is found.
    options = {"key_tails": key_tails, "prose": prose, "forbidden": forbidden}
    exception_prefix = "class Failure(Exception):\n    pass\n"
    planted = {
        "a catalog path": 'x = "/v1/capabilities"\n',
        "an operation name": 'x = "capabilities"\n',
        "an unlisted literal": 'x = "unlisted-literal"\n',
        "a bytes literal": 'x = b"unlisted"\n',
        "an f-string's constant part": 'x = f"unlisted{y}"\n',
        "a getattr name": 'x = getattr(y, "unlisted")\n',
        "a string given to an ordinary call": 'x = print("unlisted sentence")\n',
        "an operation name inside an exception": exception_prefix + 'raise Failure("capabilities")\n',
        "a key inside an exception's argument": exception_prefix + 'raise Failure(y["unlisted_key"], "a sentence")\n',
        "a call argument inside an exception's argument": exception_prefix + 'raise Failure(y.get("unlisted_key"))\n',
        "an exception built outside a raise": exception_prefix + 'x = Failure("unlisted sentence")\n',
        "an exception's text carried out by .args": exception_prefix + 'x = Failure("a sentence").args\n',
        "a docstring carried out by __doc__": 'def f():\n    "unlisted"\n\n\nx = f.__doc__\n',
        "an import of the adapter": "import adapter\n",
        "a from-import of the adapter": "from adapter import load_contract\n",
        "a relative import": "from . import sibling\n",
        "an import of a third-party package": "import httpx\n",
    }
    for label, planted_source in planted.items():
        assert literal_violations(planted_source, **options), label
    allowed = {
        "a docstring": '"""A sentence that is not a literal."""\nx = 1\n',
        "an exception's text": exception_prefix + 'raise Failure("an unlisted sentence " + ", ".join(y))\n',
        "an exception's f-string": exception_prefix + 'raise Failure(f"unlisted {y} sentence")\n',
        "a key name": 'x = y["role"]\n',
        "a prose literal": 'x = y.startswith("control.")\n',
        "the schema_check import": "from schema_check import validate\n",
        "a standard library import": "import json\nfrom urllib.parse import quote\n",
    }
    for label, allowed_source in allowed.items():
        assert literal_violations(allowed_source, **options) == [], label
