"""C-35 -- a client holding only the contract (`spec/data-service-api.v1.json`
and its derived `spec/OPERATION_CATALOG.json`), a deployment's
`surfaces.data.base_url` and one authorized application credential at a time
composes every request of the one `common_baseline` turn C-28 drives, and
completes that turn against every wire-transport adapter (SI-05, SI-09,
SI-10, SI-11, SI-14).

design: docs/design/REFERENCE_CLIENT_V0_1.md D-3 / D-4 / D-4a / D-5 / D-6, 5
(the table of steps and where each is composed from), 7, 11 (honest scope),
registered in `conformance-tests/CONDITIONS.md`. Every test here carries
`@pytest.mark.condition("C-35")` via the module-level `pytestmark`.

**ONE test function per wire plug, ONE scenario, the same 12 steps C-28
drives, in the same order**, but through two `ReferenceClient` instances
(`conformance-tests/reference_client.py`) instead of the port's own
operation methods: one holds the runtime secret of the Application and one
the developer secret, each only its own secret and each only a send
function. A step names an operation and states the intent of a body; the
client composes method, URL, headers and body from the contract and sends
nothing a request schema refuses. Which instance sends an operation is read
from the catalog's `roles` for that operation (runtime when the operation
accepts it, developer otherwise).

**What the port supplies is `provision_application` and `wire_entry`
only.** `wire_entry` (port v1.21) gives the declared data base URL, a send
function and the two secrets; this module hands `entry.send` to a client and
never calls it (a recording wrapper, `Recorder`, is the send function the
client holds, and only the client calls it). The entry's declaration of
which secret is the runtime one and which the developer one is NOT given to
a client: step (1) reads each client's `role` from the capability document
its secret obtained, and the test asserts that role equals what the entry
declares for that secret, that the entry's `base_url` equals the
`surfaces.data.base_url` the document declares, and that the contract's, the
catalog's and the document's `contract_version` agree.

**Selection happens once, at module import**: the registered adapters whose
declared `transport_kind` is not `in_process` (the two `asgi` and the two
`socket` plugs) are selected from the built registry and asserted there to
number four (`_WIRE_ADAPTER_NAMES`); `adapter` is parametrized indirectly
over them. Nothing below the selection branches on an adapter's name, its
`transport_kind` or a host. Each item also asserts that its own `xdist_group`
marker names the adapter it was parametrized with
(`conftest.py`'s `pytest_collection_modifyitems` derives the group from the
`adapter` parameter): an item that did not take `adapter` that way would
fall into the shared `registry-guards` group, whose members start no real
process.

**Every request this scenario makes goes through a client**, and the static
pin in `test_reference_client.py`
(`test_c35_turn_reaches_the_wire_only_through_the_client`) reads this
module's source for it: no call of a `.send`, no import of an HTTP or socket
library, no use of the isolated surface beyond `provision_application` and
`wire_entry`, no branch on an adapter, an entry or a host.

**Observation, not skipping.** `Journal` records, per step, each exchange the
wire carried (the HTTP method, the URL and the response's media type, never a
request header) and each explicit observation of a step that sends nothing
(step 5 repairs a request body from a diagnosis and sends nothing). Each
exchange is checked as it is attributed to a step: a response a client
classified as a success carried `media_type`, one it classified as a failure
carried `errors.content_type`. The turn ends by asserting that every step
observed at least one thing; that every step that expects a success observed
one and every step that expects a refusal observed one; and that every
request a recorder carried is one the journal attributes to a step.

Secrets: a failure text names the adapter, the step and values the scenario
itself produced; a `WireEntry`'s secret fields are `repr=False` and no
assertion here compares one.
"""
from __future__ import annotations

import copy
import json
from collections import Counter, defaultdict
from dataclasses import dataclass

import pytest

from adapter import REPO_ROOT, fresh_identifier, load_contract
from conftest import registered_adapters
from reference_client import ProblemResponse, ReferenceClient

_WIRE_ADAPTER_NAMES: tuple[str, ...] = tuple(
    name for name, obj in registered_adapters().items() if obj.transport_kind != "in_process"
)
assert len(_WIRE_ADAPTER_NAMES) == 4, (
    f"expected exactly four registered adapters whose transport_kind is not 'in_process' "
    f"(the two asgi and the two socket plugs), found {len(_WIRE_ADAPTER_NAMES)}: {_WIRE_ADAPTER_NAMES!r}"
)

pytestmark = [
    pytest.mark.condition("C-35"),
    pytest.mark.parametrize("adapter", _WIRE_ADAPTER_NAMES, indirect=True),
]

CONTRACT = load_contract()
CATALOG = json.loads((REPO_ROOT / "spec" / "OPERATION_CATALOG.json").read_text())
_ROLES_OF = {entry["name"]: entry["roles"] for entry in CATALOG["operations"]}

# The baseline query operators, read from the contract as C-28 reads them:
# `common_baseline.operations` names the included operators only in prose,
# so the included set is the full vocabulary (a real JSON array) minus the
# three operators `common_baseline.outside` names.
_OUTSIDE_BASELINE_OPERATORS = ("contains", "matches", "is_null")
_BASELINE_OPERATORS = tuple(
    op for op in CONTRACT["structured_operations"]["allowed_query_operators"]
    if op not in _OUTSIDE_BASELINE_OPERATORS
)
_BASELINE_CAPABILITIES = tuple(CONTRACT["common_baseline"]["capabilities"])

# The key of a confirmation denial's details that carries the phrase to echo
# (`destructive_confirmation.denial.details_keys` names it; step (11) asserts so).
_PHRASE_KEY = "required_confirmation"

_STEPS = tuple(range(1, 13))
_STEPS_THAT_FAIL = (4, 11)
_STEPS_THAT_SEND_NOTHING = (5,)
_STEPS_THAT_SUCCEED = tuple(step for step in _STEPS if step not in (4, 5))


@dataclass(frozen=True)
class Exchange:
    method: str
    url: str
    status: int
    media_type: str | None


def _media_type_of(headers) -> str | None:
    found = [value for header_name, value in headers if header_name.lower() == "content-type"]
    if len(found) != 1:
        return None
    return found[0].split(";")[0].strip().lower()


class Recorder:
    """The send function a client holds. It hands each request on, unchanged,
    to the entry's send function and records method, URL, status and the
    response's media type -- never a request header, so no credential."""

    def __init__(self, send) -> None:
        self._send = send
        self.exchanges: list[Exchange] = []

    def __call__(self, method, url, headers, body):
        status, response_headers, response_body = self._send(method, url, headers, body)
        self.exchanges.append(Exchange(method, url, status, _media_type_of(response_headers)))
        return status, response_headers, response_body


class Journal:
    """What the turn observed, per step."""

    def __init__(self) -> None:
        self.successes: dict[int, list[Exchange]] = defaultdict(list)
        self.failures: dict[int, list[Exchange]] = defaultdict(list)
        self.observations: Counter[int] = Counter()

    def attributed(self) -> int:
        return sum(len(v) for v in self.successes.values()) + sum(len(v) for v in self.failures.values())


class Turn:
    """Two clients and the journal. A step asks for an operation by name; the
    client that sends it is the first of (runtime, developer) whose `role`,
    read from its own capability document, the catalog lists for it."""

    def __init__(self, adapter_name: str, clients: dict[str, tuple[ReferenceClient, Recorder]]) -> None:
        self.adapter_name = adapter_name
        self.clients = clients
        self.journal = Journal()

    def _client_for(self, step: int, operation: str) -> tuple[ReferenceClient, Recorder]:
        roles = _ROLES_OF[operation]
        for client, recorder in self.clients.values():
            if client.role in roles:
                return client, recorder
        pytest.fail(f"{self.adapter_name}: C-35 step ({step}): no client holds a role the catalog lists for {operation!r}")

    def _attribute(self, step: int, recorder: Recorder, before: int, *, failure: bool) -> Exchange:
        new = recorder.exchanges[before:]
        assert len(new) == 1, f"{self.adapter_name}: C-35 step ({step}): one call carried {len(new)} requests, not 1"
        exchange = new[0]
        expected = (CONTRACT["errors"]["content_type"] if failure else CONTRACT["media_type"]).lower()
        assert exchange.media_type == expected, (
            f"{self.adapter_name}: C-35 step ({step}): a response the client classified as a "
            f"{'failure' if failure else 'success'} carried media type {exchange.media_type!r}, not {expected!r}"
        )
        (self.journal.failures if failure else self.journal.successes)[step].append(exchange)
        return exchange

    def fetch(self, step: int, role: str, operation: str) -> dict:
        client, recorder = self.clients[role]
        before = len(recorder.exchanges)
        document = client.fetch_capabilities(operation)
        self._attribute(step, recorder, before, failure=False)
        return document

    def call(self, step: int, operation: str, **kwargs):
        client, recorder = self._client_for(step, operation)
        before = len(recorder.exchanges)
        result = client.call(operation, **kwargs)
        self._attribute(step, recorder, before, failure=False)
        return result

    def denied(self, step: int, operation: str, **kwargs) -> ProblemResponse:
        client, recorder = self._client_for(step, operation)
        before = len(recorder.exchanges)
        with pytest.raises(ProblemResponse) as info:
            client.call(operation, **kwargs)
        self._attribute(step, recorder, before, failure=True)
        return info.value

    def observe(self, step: int) -> None:
        self.journal.observations[step] += 1


def _own_group(request: pytest.FixtureRequest) -> str:
    """The name of the adapter this item was parametrized with, after
    asserting that the item's own `xdist_group` marker names it and that it is
    one the module selected."""
    callspec = getattr(request.node, "callspec", None)
    assert callspec is not None, f"{request.node.nodeid}: not parametrized"
    parametrized = callspec.params.get("adapter")
    marker = request.node.get_closest_marker("xdist_group")
    assert marker is not None, f"{request.node.nodeid}: carries no xdist_group marker"
    assert marker.kwargs.get("name") == parametrized, (
        f"{request.node.nodeid}: xdist_group is {marker.kwargs.get('name')!r}, adapter parameter {parametrized!r}"
    )
    assert parametrized in _WIRE_ADAPTER_NAMES, f"{request.node.nodeid}: {parametrized!r} is not a selected wire adapter"
    return parametrized


def _rows(turn: Turn, step: int, entity: str, where_value, field: str) -> list:
    """The rows of `entity` whose `field` equals `where_value`, read through a
    query a client composes."""
    result = turn.call(
        step, "query", path_values={"entity": entity},
        body={"select": [field], "where": [{"field": field, "operator": "eq", "value": where_value}]},
    )
    return result["items"]


def test_c35_reference_client_turn(isolated, request: pytest.FixtureRequest) -> None:
    plug = _own_group(request)

    application_id = fresh_identifier("c35")
    isolated.provision_application(application_id)
    entry = isolated.wire_entry(application_id)

    runtime_recorder, developer_recorder = Recorder(entry.send), Recorder(entry.send)
    runtime_client = ReferenceClient(CONTRACT, CATALOG, entry.base_url, entry.runtime_secret, runtime_recorder)
    developer_client = ReferenceClient(CONTRACT, CATALOG, entry.base_url, entry.developer_secret, developer_recorder)
    turn = Turn(plug, {"runtime": (runtime_client, runtime_recorder), "developer": (developer_client, developer_recorder)})

    # ------------------------------------------------------------------
    # Step (1): read capabilities and the contract version, once per client.
    # The role each client reads must be the role the entry declares for the
    # secret it holds (the declaration is never given to a client); the base
    # URL the document declares must be the entry's; the three contract
    # versions must agree.
    # ------------------------------------------------------------------
    documents = {}
    for declared_role in ("runtime", "developer"):
        document = turn.fetch(1, declared_role, "capabilities")
        documents[declared_role] = document
        assert turn.clients[declared_role][0].role == declared_role, (
            f"{plug}: C-35 step (1): the client holding the entry's {declared_role} secret read "
            f"role {turn.clients[declared_role][0].role!r} from the capability document"
        )
        assert document["surfaces"]["data"]["base_url"] == entry.base_url, (
            f"{plug}: C-35 step (1): the {declared_role} document declares a data base URL other than the "
            f"entry's ({document['surfaces']['data']['base_url']!r} vs {entry.base_url!r})"
        )
        assert document["contract_version"] == CONTRACT["contract_version"] == CATALOG["contract_version"], (
            f"{plug}: C-35 step (1): contract_version differs between the document "
            f"({document['contract_version']!r}), the contract ({CONTRACT['contract_version']!r}) and the "
            f"catalog ({CATALOG['contract_version']!r})"
        )
        turn.observe(1)
    capabilities = documents["runtime"].get("capabilities", {})
    for capability in _BASELINE_CAPABILITIES:
        status = capabilities.get(capability, {}).get("status", "unavailable")
        assert status != "unavailable", (
            f"{plug}: C-35 step (1): baseline capability {capability!r} is declared unavailable -- "
            f"capabilities[{capability!r}]={capabilities.get(capability)!r}"
        )

    # ------------------------------------------------------------------
    # Step (2): developer creates an entity carrying an enum and a
    # nullable: false field.
    # ------------------------------------------------------------------
    entity = fresh_identifier("c35e")
    enum_field, nonnull_field, sort_field = "status", "req", "seq"
    created = turn.call(
        2, "schema",
        body={
            "operation": "create_entity",
            "entity": entity,
            "fields": [enum_field, nonnull_field, sort_field],
            "field_types": {enum_field: "string", nonnull_field: "string", sort_field: "integer"},
            "field_constraints": {enum_field: {"enum": ["a", "b"]}, nonnull_field: {"nullable": False}},
        },
    )
    assert created.get("request_id"), f"{plug}: C-35 step (2): a successful create_entity result carries no request_id -- {created!r}"

    # ------------------------------------------------------------------
    # Step (3): runtime reads the catalog.
    # ------------------------------------------------------------------
    catalog_document = turn.call(3, "catalog")
    row = {r["entity"]: r for r in catalog_document["entities"]}[entity]
    declared_enum = (row.get("field_constraints") or {}).get(enum_field, {}).get("enum")
    assert declared_enum == ["a", "b"], (
        f"{plug}: C-35 step (3): catalog does not report {entity!r}.{enum_field}'s own declared enum "
        f"-- {row.get('field_constraints')!r}"
    )

    # ------------------------------------------------------------------
    # Step (4): build an insert from the catalog alone, carrying a value
    # outside the declared enum; the refusal names the position, never the
    # value. One body is built here and used again in step (5).
    # ------------------------------------------------------------------
    marker = fresh_identifier("c35row")
    rejected_value = "outside-the-catalog-enum"
    bad_values = {enum_field: rejected_value, nonnull_field: marker, sort_field: 1}
    body = {"operations": [{"operation": "insert", "values": dict(bad_values)}]}
    denial = turn.denied(4, "mutate", path_values={"entity": entity}, body=copy.deepcopy(body))
    assert denial.code == "VALIDATION_FAILED", (
        f"{plug}: C-35 step (4): an enum-violating insert was refused with {denial.code!r}, not VALIDATION_FAILED"
    )
    details = denial.problem["details"]
    assert details.get("violated_declaration") == "enum", f"{plug}: C-35 step (4): {details!r} lacks violated_declaration=enum"
    # SI-10: the refusal's whole body (message included) never carries the
    # rejected value, never offers a declared enum member as a replacement,
    # and keeps its details inside the contract's own vocabulary.
    assert rejected_value not in json.dumps(denial.problem), (
        f"{plug}: C-35 step (4) SI-10: the rejected value {rejected_value!r} is disclosed in the refusal -- {denial.problem!r}"
    )
    assert not any(isinstance(v, str) and v in declared_enum for v in details.values()), (
        f"{plug}: C-35 step (4) SI-10: the refusal discloses a declared enum member as a suggested replacement -- {details!r}"
    )
    vocabulary = CONTRACT["errors"]["details_vocabulary"]
    allowed_detail_keys = set(vocabulary["VALIDATION_FAILED"]) | set(vocabulary["common_optional"])
    assert set(details) <= allowed_detail_keys, (
        f"{plug}: C-35 step (4) SI-10: refusal details keys {sorted(details)!r} are outside the contract's own "
        f"VALIDATION_FAILED vocabulary {sorted(allowed_detail_keys)!r}"
    )
    # The nullable half of the baseline's last item, as an independent send.
    null_denial = turn.denied(
        4, "mutate", path_values={"entity": entity},
        body={"operations": [{"operation": "insert", "values": {enum_field: declared_enum[0], nonnull_field: None, sort_field: 2}}]},
    )
    assert null_denial.code == "VALIDATION_FAILED", (
        f"{plug}: C-35 step (4) nullable: a null on a nullable:false field was refused with {null_denial.code!r}, "
        "not VALIDATION_FAILED"
    )
    assert null_denial.problem["details"].get("violated_declaration") == "nullable", (
        f"{plug}: C-35 step (4) nullable: {null_denial.problem['details']!r} lacks violated_declaration=nullable"
    )
    assert len(turn.journal.failures[4]) == 2 and not turn.journal.successes[4], (
        f"{plug}: C-35 step (4): expected exactly two refusals and no success, journal holds "
        f"{len(turn.journal.failures[4])} and {len(turn.journal.successes[4])}"
    )

    # ------------------------------------------------------------------
    # Step (5): repair the SAME request body from the diagnosis alone --
    # `details.field` is a '/'-separated path from the request body root --
    # touching only the position it names. Nothing is sent in this step.
    # ------------------------------------------------------------------
    fixed_value = declared_enum[0]
    field_path = details.get("field")
    assert field_path, f"{plug}: C-35 step (5): the enum refusal carries no details.field to repair from"
    parts = field_path.split("/")
    try:
        target = body
        for part in parts[:-1]:
            target = target[int(part)] if part.isdigit() else target[part]
        leaf = parts[-1]
        resolved = target[int(leaf)] if leaf.isdigit() else target[leaf]
    except (KeyError, IndexError, TypeError) as exc:
        pytest.fail(
            f"{plug}: C-35 step (5): details.field {field_path!r} does not resolve against the SAME request body "
            f"step (4) sent -- body={body!r}, error={exc!r}"
        )
    assert resolved == rejected_value, (
        f"{plug}: C-35 step (5): details.field {field_path!r} does not resolve, inside the SAME request body step (4) "
        f"sent, to the value that was rejected -- resolved {resolved!r}, expected {rejected_value!r} (body={body!r})"
    )
    if leaf.isdigit():
        target[int(leaf)] = fixed_value
    else:
        target[leaf] = fixed_value
    repaired_values = body["operations"][0]["values"]
    assert repaired_values == {**bad_values, enum_field: fixed_value}, (
        f"{plug}: C-35 step (5): the repaired request body diverges from step (4)'s own body beyond the single "
        f"diagnosed position -- repaired={repaired_values!r}, step (4)={bad_values!r}"
    )
    turn.observe(5)

    # ------------------------------------------------------------------
    # Step (6): the repaired request with the idempotency_key step (7) will
    # send, as a dry run.
    # ------------------------------------------------------------------
    key = fresh_identifier("c35key")
    dry = turn.call(
        6, "mutate", path_values={"entity": entity},
        body={"operations": [{"operation": "insert", "values": dict(repaired_values)}], "idempotency_key": key, "dry_run": True},
    )
    assert dry.get("committed") is False, f"{plug}: C-35 step (6): dry_run=true result carries committed={dry.get('committed')!r}"
    assert dry.get("affected") == 1, (
        f"{plug}: C-35 step (6): dry_run=true result carries affected={dry.get('affected')!r}, not 1 (the real send's row count)"
    )
    plan = dry.get("plan")
    assert plan, f"{plug}: C-35 step (6): a dry-run result carries no 'plan' -- {dry!r}"
    rows_after_dry_run = _rows(turn, 6, entity, marker, nonnull_field)
    assert rows_after_dry_run == [], f"{plug}: C-35 step (6): dry_run=true left a real, readable row behind -- {rows_after_dry_run!r}"

    # ------------------------------------------------------------------
    # Step (7): the same request, the same key, presenting step (6)'s plan.
    # ------------------------------------------------------------------
    real_body = {"operations": [{"operation": "insert", "values": dict(repaired_values)}], "idempotency_key": key, "plan": plan}
    real = turn.call(7, "mutate", path_values={"entity": entity}, body=real_body)
    assert real.get("committed") is True, (
        f"{plug}: C-35 step (7): the real send under step (6)'s own idempotency_key and plan carries "
        f"committed={real.get('committed')!r}, not True"
    )
    first_request_id = real.get("request_id")
    assert first_request_id, f"{plug}: C-35 step (7): a real, successful insert carries no request_id -- {real!r}"
    rows_after_real_send = _rows(turn, 7, entity, marker, nonnull_field)
    assert len(rows_after_real_send) == 1, f"{plug}: C-35 step (7): the real send did not leave exactly one row -- {rows_after_real_send!r}"

    # ------------------------------------------------------------------
    # Step (8): resend the same key and body; the first execution's own
    # request_id comes back and no second row appears.
    # ------------------------------------------------------------------
    resend = turn.call(
        8, "mutate", path_values={"entity": entity},
        body={"operations": [{"operation": "insert", "values": dict(repaired_values)}], "idempotency_key": key},
    )
    assert resend.get("request_id") == first_request_id, (
        f"{plug}: C-35 step (8): a same-key/same-body resend carries request_id {resend.get('request_id')!r}, "
        f"not the FIRST execution's own {first_request_id!r}"
    )
    rows_after_resend = _rows(turn, 8, entity, marker, nonnull_field)
    assert len(rows_after_resend) == 1, f"{plug}: C-35 step (8): a same-key/same-body resend must not add a second row -- {rows_after_resend!r}"

    # ------------------------------------------------------------------
    # Step (9): each baseline operator under order_by, a page.size and a
    # budget.result_items, chained R < page.size <= budget.result_items <=
    # limits.result_items (the bound read from the capability document step
    # (1) obtained, never a literal).
    # ------------------------------------------------------------------
    declared_result_items = documents["runtime"].get("limits", {}).get("result_items")
    assert isinstance(declared_result_items, int) and declared_result_items >= 3, (
        f"{plug}: C-35 step (9): the capability document declares no usable limits.result_items -- "
        f"{documents['runtime'].get('limits')!r}"
    )
    extra_rows = min(3, declared_result_items - 2)
    max_sort = 1 + extra_rows
    # Inserted in descending order so the stored sequence is not already
    # ascending by `sort_field` (a peer that drops `order_by` could otherwise
    # pass the ascending check by coincidence).
    for value in range(max_sort, 1, -1):
        turn.call(
            9, "mutate", path_values={"entity": entity},
            body={"operations": [{"operation": "insert", "values": {
                enum_field: fixed_value, nonnull_field: fresh_identifier("c35fill"), sort_field: value,
            }}]},
        )
    page_size = max_sort + 1
    budget_result_items = page_size
    assert page_size <= budget_result_items <= declared_result_items, (
        f"{plug}: C-35 step (9): the chain page.size<=budget.result_items<=limits.result_items does not hold for "
        f"page_size={page_size}, budget={budget_result_items}, declared={declared_result_items}"
    )
    all_sort_values = set(range(1, max_sort + 1))
    operator_probe_values: dict[str, object] = {
        "eq": 1, "ne": 1, "lt": max_sort, "lte": max_sort, "gt": 1, "gte": 1, "in": [1],
    }
    expected_by_operator: dict[str, set[int]] = {
        "eq": {1},
        "in": {1},
        "ne": all_sort_values - {1},
        "gt": all_sort_values - {1},
        "lt": all_sort_values - {max_sort},
        "lte": set(all_sort_values),
        "gte": set(all_sort_values),
    }
    assert _BASELINE_OPERATORS, "C-35 step (9): the baseline operator set must not be empty"
    operators_observed = 0
    for operator in _BASELINE_OPERATORS:
        operators_observed += 1
        result = turn.call(
            9, "query", path_values={"entity": entity},
            body={
                "select": [nonnull_field, sort_field],
                "where": [{"field": sort_field, "operator": operator, "value": operator_probe_values[operator]}],
                "order_by": [{"field": sort_field, "direction": "asc"}],
                "page": {"size": page_size},
                "budget": {"result_items": budget_result_items},
            },
        )
        items = result["items"]
        assert items, f"{plug}: C-35 step (9): operator {operator!r} matched zero rows -- {result!r}"
        assert len(items) < page_size, (
            f"{plug}: C-35 step (9): operator {operator!r} returned {len(items)} rows, not strictly less than its own "
            f"page.size={page_size}"
        )
        seq_values = [item[sort_field] for item in items]
        assert seq_values == sorted(seq_values), (
            f"{plug}: C-35 step (9): operator {operator!r} under order_by did not return rows in ascending "
            f"{sort_field!r} order -- {seq_values!r}"
        )
        assert set(seq_values) == expected_by_operator[operator], (
            f"{plug}: C-35 step (9): operator {operator!r} matched {set(seq_values)!r}, not the expected "
            f"{expected_by_operator[operator]!r}"
        )
    assert operators_observed == len(_BASELINE_OPERATORS), (
        f"{plug}: C-35 step (9): only {operators_observed} of {len(_BASELINE_OPERATORS)} baseline operators were observed"
    )

    # ------------------------------------------------------------------
    # Step (10): update by predicate.
    # ------------------------------------------------------------------
    updated_marker = marker + "_upd"
    updated = turn.call(
        10, "mutate", path_values={"entity": entity},
        body={"operations": [{
            "operation": "update",
            "values": {nonnull_field: updated_marker},
            "where": [{"field": nonnull_field, "operator": "eq", "value": marker}],
        }]},
    )
    assert updated.get("affected") == 1, f"{plug}: C-35 step (10): predicate update affected {updated.get('affected')!r} rows, not 1"
    assert len(_rows(turn, 10, entity, updated_marker, nonnull_field)) == 1, (
        f"{plug}: C-35 step (10): predicate update did not actually change the row"
    )

    # ------------------------------------------------------------------
    # Step (11): delete by predicate under declare-and-echo -- the request is
    # refused with the contract's confirmation denial, the phrase to echo is
    # read from that refusal's own details (never written here), and the same
    # request is sent again with `destructive` and that phrase.
    # ------------------------------------------------------------------
    confirmation = CONTRACT["destructive_confirmation"]
    delete_operation = {
        "operation": "delete",
        "where": [{"field": nonnull_field, "operator": "eq", "value": updated_marker}],
    }
    unconfirmed = turn.denied(11, "mutate", path_values={"entity": entity}, body={"operations": [dict(delete_operation)]})
    assert unconfirmed.code == confirmation["denial"]["code"], (
        f"{plug}: C-35 step (11): an unconfirmed predicate delete was refused with {unconfirmed.code!r}, "
        f"not {confirmation['denial']['code']!r}"
    )
    assert _PHRASE_KEY in confirmation["denial"]["details_keys"], (
        f"{plug}: C-35 step (11): the contract's confirmation denial does not name {_PHRASE_KEY!r} among its details keys"
    )
    assert set(confirmation["denial"]["details_keys"]) <= set(unconfirmed.problem["details"]), (
        f"{plug}: C-35 step (11): the confirmation denial lacks a key the contract names -- "
        f"{sorted(unconfirmed.problem['details'])!r}"
    )
    required = unconfirmed.problem["details"][_PHRASE_KEY]
    assert isinstance(required, str) and required, f"{plug}: C-35 step (11): the denial's declared confirmation is not a non-empty string"
    assert len(_rows(turn, 11, entity, updated_marker, nonnull_field)) == 1, (
        f"{plug}: C-35 step (11): the refused delete removed the row"
    )
    deleted = turn.call(
        11, "mutate", path_values={"entity": entity},
        body={"operations": [{**delete_operation, "destructive": True, "confirmation": required}]},
    )
    assert deleted.get("affected") == 1, (
        f"{plug}: C-35 step (11): confirmed predicate delete affected {deleted.get('affected')!r} rows, not 1"
    )
    assert _rows(turn, 11, entity, updated_marker, nonnull_field) == [], (
        f"{plug}: C-35 step (11): confirmed predicate delete did not actually remove the row"
    )

    # ------------------------------------------------------------------
    # Step (12): the final query agrees with the consequences of (7), (10)
    # and (11): only the fill rows of step (9) remain.
    # ------------------------------------------------------------------
    final = turn.call(
        12, "query", path_values={"entity": entity},
        body={"select": [sort_field], "page": {"size": page_size}},
    )
    assert len(final["items"]) == extra_rows, (
        f"{plug}: C-35 step (12): final row count {len(final['items'])} does not match step (9)'s fill rows "
        f"({extra_rows}) -- the step (7) row must have been updated (10) then deleted (11)"
    )

    # ------------------------------------------------------------------
    # The journal: every step observed something, every step that expects a
    # success observed one, every classified response carried the media type
    # that classification names, and every request a recorder carried is one
    # a step accounts for.
    # ------------------------------------------------------------------
    journal = turn.journal
    for step in _STEPS:
        observed = len(journal.successes[step]) + len(journal.failures[step]) + journal.observations[step]
        assert observed >= 1, f"{plug}: C-35 step ({step}): the turn observed nothing in this step"
    for step in _STEPS_THAT_SUCCEED:
        assert journal.successes[step], f"{plug}: C-35 step ({step}): no response the client classified as a success"
    for step in _STEPS_THAT_FAIL:
        assert journal.failures[step], f"{plug}: C-35 step ({step}): no response the client classified as a failure"
    for step in _STEPS_THAT_SEND_NOTHING:
        assert not journal.successes[step] and not journal.failures[step] and journal.observations[step] >= 1, (
            f"{plug}: C-35 step ({step}): a step that sends nothing must observe, and only observe"
        )
    assert journal.attributed() == len(runtime_recorder.exchanges) + len(developer_recorder.exchanges), (
        f"{plug}: C-35: the recorders carried {len(runtime_recorder.exchanges) + len(developer_recorder.exchanges)} "
        f"requests, the steps account for {journal.attributed()}"
    )
    assert developer_recorder.exchanges and runtime_recorder.exchanges
