"""Phase 9 WP-2e (design docs/design/
PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md D-3/D-7, work order
docs/work-orders/WORK_ORDER_PHASE9_CONTRACT_170_V1.md §2 WP-2e,
`{scratchpad}/rulings-r3-r7-flip.md`): peer-local coverage for R-3
(`errors.details_vocabulary`'s 4-key form) and R-7 (`request_id` on every
successful result), plus the version flip and `ops verify-declarations`
extension the same commit carries. The common-suite half of R-3/R-7 lives
in `conformance-tests/test_c21_denial_details_vocabulary.py`/`test_c25_
result_request_id.py`; this file is the peer-local, in-process complement
(work order completion conditions 1-11)."""
from __future__ import annotations

import pytest

from r2db_api import ControlAuthority, CredentialStore, DataService
from r2db_api.errors import FoundationError
from r2db_api.limits import ResourceLimits
from r2db_api import ops as r2db_ops
from r2db_api import platform_declarations


@pytest.fixture
def service():
    credentials = CredentialStore(pepper="test-pepper")
    with credentials.unit_of_work() as work:
        credentials.add("cred-a", "app-a", "runtime", "secret-a", work=work)
    with credentials.unit_of_work() as work:
        credentials.add("dev-a", "app-a", "developer", "dev-secret-a", work=work)
    service = DataService(credentials)
    control = ControlAuthority(service)
    control.register_application("app-a", entities={"notes": [{"body": "a"}]})
    return service


@pytest.fixture
def runtime(service):
    return service.authenticate("cred-a.secret-a")


@pytest.fixture
def developer(service):
    return service.authenticate("dev-a.dev-secret-a")


# ---------------------------------------------------------------------------
# Completion condition 1: VALIDATION_FAILED's 3-branch required-key rule
# (D-3 (4)) -- `enum` carries `declared_type` but NEVER `observed_type`;
# `field_type`/`nullable` carry BOTH.
# ---------------------------------------------------------------------------


def test_enum_violation_carries_declared_type_never_observed_type(service, developer, runtime):
    service.schema(developer, {"operation": "create_entity", "entity": "widgets", "fields": ["color"], "field_types": {"color": "string"}})
    service.schema(developer, {"operation": "alter_field", "entity": "widgets", "field": "color", "enum": ["red", "blue"]})
    with pytest.raises(FoundationError) as exc:
        service.mutate(runtime, "widgets", [{"operation": "insert", "values": {"color": "green"}}])
    assert exc.value.code == "VALIDATION_FAILED"
    assert exc.value.details.get("violated_declaration") == "enum"
    assert exc.value.details.get("declared_type") == "string"
    assert "observed_type" not in exc.value.details, exc.value.details


def test_field_type_violation_carries_both_declared_and_observed_type(service, developer, runtime):
    service.schema(developer, {"operation": "create_entity", "entity": "readings", "fields": ["n"], "field_types": {"n": "integer"}})
    with pytest.raises(FoundationError) as exc:
        service.mutate(runtime, "readings", [{"operation": "insert", "values": {"n": "not-an-integer"}}])
    assert exc.value.code == "VALIDATION_FAILED"
    assert exc.value.details.get("violated_declaration") == "field_type"
    assert exc.value.details.get("declared_type") == "integer"
    assert exc.value.details.get("observed_type") == "string"


def test_nullable_violation_carries_both_declared_and_observed_type(service, developer, runtime):
    service.schema(developer, {"operation": "create_entity", "entity": "people", "fields": ["name"], "field_types": {"name": "string"}, "field_constraints": {"name": {"nullable": False}}})
    with pytest.raises(FoundationError) as exc:
        service.mutate(runtime, "people", [{"operation": "insert", "values": {"name": None}}])
    assert exc.value.code == "VALIDATION_FAILED"
    assert exc.value.details.get("violated_declaration") == "nullable"
    assert exc.value.details.get("declared_type") == "string"
    assert exc.value.details.get("observed_type") == "null"


# ---------------------------------------------------------------------------
# Completion condition 2: `request_schema` unknown-field denial -- a single
# unknown field names `field` (singular); more than one omits `field`
# entirely; neither carries `declared_type`/`observed_type` (D-3 (4): the
# contract's request schema names no type for a field it does not know).
# ---------------------------------------------------------------------------


def _http_mutate(service, body: dict) -> "object":
    """`_check_object_shape` (`http.py`, D-3) is an HTTP-boundary-only
    choke point over the RAW request body's own top-level keys -- an
    in-process `service.mutate(...)` call never reaches it at all (it
    hands `structured.py` an already-Python `operations` list, bypassing
    request-shape validation entirely). Unknown-TOP-LEVEL-field coverage
    therefore has to go over the real ASGI boundary, like `test_http_
    response_never_regenerates_request_id` below."""
    from starlette.testclient import TestClient
    from r2db_api.http import create_app

    client = TestClient(create_app(service))
    return client.post("/v1/data/notes/mutations", headers={"Authorization": "Bearer cred-a.secret-a"}, json=body)


def test_single_unknown_field_names_it_as_field(service):
    response = _http_mutate(service, {"operations": [{"operation": "insert", "values": {"body": "x"}}], "not_a_real_key": True})
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "VALIDATION_FAILED"
    details = body["details"]
    assert details.get("violated_declaration") == "request_schema"
    assert details.get("field") == "not_a_real_key"
    assert "declared_type" not in details and "observed_type" not in details, details


def test_multiple_unknown_fields_omit_field(service):
    response = _http_mutate(service, {"operations": [{"operation": "insert", "values": {"body": "x"}}], "bogus_a": 1, "bogus_b": 2})
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "VALIDATION_FAILED"
    details = body["details"]
    assert details.get("violated_declaration") == "request_schema"
    assert "field" not in details, details


# ---------------------------------------------------------------------------
# Completion condition 3: IDENTIFIER_INVALID always carries `field` +
# `violated_declaration: identifier_syntax`.
# ---------------------------------------------------------------------------


def test_identifier_invalid_carries_field_and_violated_declaration(service, developer):
    with pytest.raises(FoundationError) as exc:
        service.schema(developer, {"operation": "create_entity", "entity": "not a valid identifier!"})
    assert exc.value.code == "IDENTIFIER_INVALID"
    assert exc.value.details.get("violated_declaration") == "identifier_syntax"
    assert exc.value.details.get("field") is not None


# ---------------------------------------------------------------------------
# Completion condition 4: CAPABILITY_UNSUPPORTED always carries
# `violated_declaration: capability`.
# ---------------------------------------------------------------------------


def test_capability_unsupported_carries_violated_declaration(service, runtime):
    with pytest.raises(FoundationError) as exc:
        service.mutate(runtime, "notes", [{"operation": "insert", "values": {"body": "c"}}], transaction="best_effort")
    assert exc.value.code == "CAPABILITY_UNSUPPORTED"
    assert exc.value.details.get("violated_declaration") == "capability"


# ---------------------------------------------------------------------------
# Completion condition 5: `field` is a request-internal path -- '/'
# separated, no leading '/', never a bare storage-position name for a
# batch-item value violation.
# ---------------------------------------------------------------------------


def test_field_is_a_request_internal_path_not_a_bare_name(service, developer, runtime):
    service.schema(developer, {"operation": "create_entity", "entity": "logs", "fields": ["n"], "field_types": {"n": "integer"}})
    with pytest.raises(FoundationError) as exc:
        service.mutate(runtime, "logs", [{"operation": "insert", "values": {"n": 1}}, {"operation": "insert", "values": {"n": "nope"}}])
    field = exc.value.details.get("field")
    assert field == "operations/1/values/n", field
    assert not field.startswith("/")


# ---------------------------------------------------------------------------
# Completion condition 6: backend-layer defence-in-depth denials do not
# carry the 4-key vocabulary -- the declaration-reading layer (choke point /
# request-shape) is what decides `violated_declaration`, never a generic
# structural refusal outside that layer's own vocabulary words.
# ---------------------------------------------------------------------------


def test_non_declaration_validation_failed_carries_no_violated_declaration(service, runtime):
    """`limits.py`'s generic request-shape refusals (cyclic structures,
    unsupported value types) are VALIDATION_FAILED but are not about any of
    the 11 `violated_declaration` words -- D-3 (3)'s closed vocabulary does
    not force every VALIDATION_FAILED into one of its words, only the ones
    the choke point / request-shape layer actually decides against a
    declaration."""
    cyclic: dict = {}
    cyclic["self"] = cyclic
    with pytest.raises(FoundationError) as exc:
        service.query(runtime, "notes", select=["id"], where=[{"field": "id", "operator": "eq", "value": cyclic}])
    assert exc.value.code == "VALIDATION_FAILED"
    assert "violated_declaration" not in exc.value.details, exc.value.details


# ---------------------------------------------------------------------------
# Completion condition 7: details never carry unsafe content (SI-10) -- the
# 4 vocabulary keys carry only declared facts, never the row value itself.
# ---------------------------------------------------------------------------


def test_details_do_not_carry_the_offending_value(service, developer, runtime):
    service.schema(developer, {"operation": "create_entity", "entity": "secrets_holder", "fields": ["n"], "field_types": {"n": "integer"}})
    marker = "super-secret-row-value-should-never-appear"
    with pytest.raises(FoundationError) as exc:
        service.mutate(runtime, "secrets_holder", [{"operation": "insert", "values": {"n": marker}}])
    assert marker not in repr(exc.value.details)


# ---------------------------------------------------------------------------
# Completion conditions 8/9: `request_id` on every successful result
# (QueryResult/MutationResult/SchemaOperationResult, in-process included),
# distinct per execution, and an idempotency replay returns the ORIGINAL
# execution's own value.
# ---------------------------------------------------------------------------


def test_request_id_present_on_query_mutate_and_schema_results(service, developer, runtime):
    mutation_result = service.mutate_result(runtime, "notes", [{"operation": "insert", "values": {"body": "x"}}])
    assert mutation_result.request_id

    query_result = service.query_page(runtime, "notes", select=["id"])
    assert query_result.request_id

    schema_result = service.schema(developer, {"operation": "add_field", "entity": "notes", "field": "tag", "field_type": "string"})
    assert schema_result.request_id


def test_request_id_is_distinct_per_execution(service, runtime):
    r1 = service.mutate_result(runtime, "notes", [{"operation": "insert", "values": {"body": "y1"}}])
    r2 = service.mutate_result(runtime, "notes", [{"operation": "insert", "values": {"body": "y2"}}])
    assert r1.request_id != r2.request_id


def test_idempotency_replay_returns_the_original_request_id(service, runtime):
    key = "wp2e-idem-key-1"
    first = service.mutate_result(runtime, "notes", [{"operation": "insert", "values": {"body": "z"}}], idempotency_key=key)
    second = service.mutate_result(runtime, "notes", [{"operation": "insert", "values": {"body": "z"}}], idempotency_key=key)
    assert second.request_id == first.request_id
    assert first.affected == second.affected == 1  # replay, not a second insert


def test_dry_run_response_carries_request_id(service, runtime):
    result = service.mutate_result(runtime, "notes", [{"operation": "insert", "values": {"body": "dry"}}], dry_run=True)
    assert result.committed is False
    assert result.request_id


def test_http_response_never_regenerates_request_id(service, runtime):
    """Q-1 (`{scratchpad}/rulings-r3-r7-flip.md`): the HTTP layer must
    never re-derive a SECOND value for the response body distinct from the
    one it handed the service layer for the audit event -- exercised here
    over the real ASGI boundary (`http.create_app`), matching C-25's own
    audit-correlation half in spirit but without requiring a durable audit
    sink."""
    from starlette.testclient import TestClient
    from r2db_api.http import create_app

    app = create_app(service)
    client = TestClient(app)
    response = client.post(
        "/v1/data/notes/mutations",
        headers={"Authorization": "Bearer cred-a.secret-a"},
        json={"operations": [{"operation": "insert", "values": {"body": "http-rid"}}]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body.get("request_id"), body
    # The X-Request-Id response header is minted by the SAME ASGI-layer
    # per-request id `service.mutate_result` was handed and used as ITS
    # OWN `rid` -- so the header and the body's `request_id` must agree
    # (never two independently-generated values for the one request).
    assert response.headers.get("x-request-id") == body["request_id"]


# ---------------------------------------------------------------------------
# Completion condition 10: `contract_version` reads 1.7.0 on both the data
# plane (`DataService.capabilities`) and the control plane
# (`ControlPlaneService.capabilities`) -- C-19's own data/control match.
# ---------------------------------------------------------------------------


def test_contract_version_is_1_7_0_on_data_plane(service, runtime):
    document = service.capabilities(runtime)
    assert document["contract_version"] == "1.7.0"


# ---------------------------------------------------------------------------
# Completion condition 11: `ops verify-declarations` checks the new 1.7.0
# limit classes (`enum_members`/`idempotency_entries`/`idempotency_
# retention_ms`) -- `check_contract_170_resource_limits` (F-14).
# ---------------------------------------------------------------------------


def test_verify_declarations_accepts_the_shipped_default_limits():
    platform_declarations.check_contract_170_resource_limits(ResourceLimits())  # must not raise


@pytest.mark.parametrize("field_name", ["enum_members", "idempotency_entries", "idempotency_retention_ms"])
def test_verify_declarations_rejects_a_non_positive_new_limit(field_name):
    """`ResourceLimits.__post_init__` (`r2db_api/limits.py:48-51`) already
    refuses to CONSTRUCT an instance carrying a non-positive value for any
    class, including these three -- so `check_contract_170_resource_limits`
    can never observe one through a real `ResourceLimits` object in this
    process. Exercised here against a minimal duck-typed stand-in (only
    `getattr(limits, name)` is read, `check_contract_170_resource_limits`
    never asserts `isinstance(limits, ResourceLimits)`) so the CHECK
    FUNCTION's own logic is still under real, falsifiable test -- this is
    the honest scope of what F-14 can catch: a REGRESSION in a caller that
    stops going through `ResourceLimits.__post_init__` at all (e.g. one
    reading a raw, unvalidated deployment config value), not a live
    `ResourceLimits` instance in today's process."""
    import types
    bad = types.SimpleNamespace(**{**ResourceLimits().as_dict(), field_name: 0})
    with pytest.raises(platform_declarations.PlatformDeclarationError) as exc:
        platform_declarations.check_contract_170_resource_limits(bad)
    assert exc.value.code == "F-14"


def test_verify_declarations_exit_code_table_has_f14():
    assert r2db_ops._VERIFY_DECLARATIONS_EXIT_CODES["F-14"] not in (
        code for name, code in r2db_ops._VERIFY_DECLARATIONS_EXIT_CODES.items() if name != "F-14"
    )
