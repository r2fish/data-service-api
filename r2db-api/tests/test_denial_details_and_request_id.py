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
from r2db_api import platform_upgrades


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


def test_present_field_with_wrong_json_type_is_a_request_schema_type_violation(service):
    """WP-2e rework (audit-wp2e.md I-4, ruling L-4/V-6 (iii)): before this
    leg existed, a PRESENT top-level field of the wrong JSON type fell all
    the way through `_check_object_shape`'s two other legs (neither the
    unknown-field nor the missing-field leg matches a present, wrong-typed
    key) into `service.py`'s own bare `fail(..., details={})` -- caught
    here instead, at the request-shape choke point, with the full 4-key
    form (`declared_type`/`observed_type` both carried, matching D-3 (4)'s
    `field_type`-shaped rule -- this leg reuses `request_schema` rather
    than `field_type` since it is a request SHAPE violation, not a
    declared entity-field-type violation)."""
    response = _http_mutate(service, {"operations": "not-a-list"})
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "VALIDATION_FAILED"
    details = body["details"]
    assert details == {
        "violated_declaration": "request_schema", "field": "operations",
        "declared_type": "array", "observed_type": "string",
    }, details


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
# WP-2e rework (audit-wp2e.md D-3, ruling L-3): IDENTIFIER_INVALID/
# CAPABILITY_UNSUPPORTED's own `field` is a REQUEST-INTERNAL PATH (D-3
# (4)'s own V-3 convention, "/"-separated from the request body root),
# never the literal string `"identifier"` the pre-rework build returned
# from all 4 identifier-syntax call sites -- `"identifier"` names no key
# in ANY request body, so it satisfied the contract's "string, required"
# shape while carrying no actual diagnostic value. Batch index is
# reflected wherever the violation is inside one `operations/<i>` item.
# ---------------------------------------------------------------------------


def test_identifier_invalid_field_is_a_request_path_not_the_literal_identifier(service, developer):
    """`entity` -- not `"identifier"` -- for a malformed top-level
    `entity` key."""
    with pytest.raises(FoundationError) as exc:
        service.schema(developer, {"operation": "create_entity", "entity": "not a valid identifier!"})
    assert exc.value.code == "IDENTIFIER_INVALID"
    assert exc.value.details.get("field") == "entity"


def test_identifier_invalid_field_reflects_batch_index_for_a_mutation_values_key(service, runtime):
    """`operations/<i>/values/<name>` (V-3's own worked example) for a
    malformed key inside ONE mutation item of a multi-item batch -- proves
    the batch position is real, not just a fixed prefix, by putting the
    bad key at index 1 (not 0) and asserting the path names index 1."""
    with pytest.raises(FoundationError) as exc:
        service.mutate(
            runtime, "notes",
            [
                {"operation": "insert", "values": {"body": "ok"}},
                {"operation": "insert", "values": {"not a valid identifier!": "x"}},
            ],
        )
    assert exc.value.code == "IDENTIFIER_INVALID"
    assert exc.value.details.get("violated_declaration") == "identifier_syntax"
    assert exc.value.details.get("field") == "operations/1/values/not a valid identifier!"


def test_identifier_invalid_field_reflects_batch_index_for_a_mutation_unique_key(service, runtime):
    """`bind_mutation`'s own `unique_key` shape check (name well-formed)
    runs unconditionally whenever the key is present on an `upsert` item,
    before any catalog lookup -- no declared uniqueness key/index is
    needed to reach it."""
    with pytest.raises(FoundationError) as exc:
        service.mutate(
            runtime, "notes",
            [
                {"operation": "insert", "values": {"body": "ok"}},
                {"operation": "upsert", "values": {"body": "b"}, "unique_key": "not a valid identifier!"},
            ],
        )
    assert exc.value.code == "IDENTIFIER_INVALID"
    assert exc.value.details.get("field") == "operations/1/unique_key"


def test_identifier_invalid_field_reflects_batch_index_for_a_mutation_where_predicate(service, runtime):
    with pytest.raises(FoundationError) as exc:
        service.mutate(
            runtime, "notes",
            [
                {"operation": "insert", "values": {"body": "ok"}},
                {"operation": "update", "where": [{"field": "not a valid identifier!", "operator": "eq", "value": "x"}], "values": {"body": "y"}},
            ],
        )
    assert exc.value.code == "IDENTIFIER_INVALID"
    assert exc.value.details.get("field") == "operations/1/where/0/field"


# ---------------------------------------------------------------------------
# Completion condition 4: CAPABILITY_UNSUPPORTED always carries
# `violated_declaration: capability`.
# ---------------------------------------------------------------------------


def test_capability_unsupported_carries_violated_declaration(service, runtime):
    with pytest.raises(FoundationError) as exc:
        service.mutate(runtime, "notes", [{"operation": "insert", "values": {"body": "c"}}], transaction="best_effort")
    assert exc.value.code == "CAPABILITY_UNSUPPORTED"
    assert exc.value.details.get("violated_declaration") == "capability"


def test_capability_unsupported_field_reflects_batch_index_for_an_unsupported_mutation_operation(service, runtime):
    """WP-2e rework (ruling L-3): `bind_mutation`'s own `CAPABILITY_
    UNSUPPORTED` for an operation name outside `MUTATION_OPERATIONS` also
    names a request-internal, batch-indexed path -- `operations/<i>/
    operation`, not a bare `"operation"`."""
    with pytest.raises(FoundationError) as exc:
        service.mutate(
            runtime, "notes",
            [
                {"operation": "insert", "values": {"body": "ok"}},
                {"operation": "replace", "values": {"body": "x"}},
            ],
        )
    assert exc.value.code == "CAPABILITY_UNSUPPORTED"
    assert exc.value.details.get("field") == "operations/1/operation"


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
#
# WP-2e rework (audit-wp2e.md I-6, ruling L-1 / D-1 = (A)): D-1 settled that
# EVERY choke-point / request-shape site -- including `limits.py`'s cyclic-
# structure and unsupported-value-type refusals this test used to pin --
# now carries `violated_declaration`. A pin against `limits.py` would
# therefore freeze those two sites' now-fixed omission rather than
# distinguish "layer that reads declarations" from "layer that doesn't".
# The only denials `errors.details_vocabulary.layer_rule` still exempts are
# genuine backend-layer defence-in-depth in `postgres.py`, reachable only
# through a real PostgreSQL connection (`PostgresCell`, never in-process).
# This test therefore moved to `test_postgres.py` (`test_postgres_data_
# error_from_an_out_of_range_number_value_is_validation_failed`), which
# already exercises `PostgresCell._fail_client_value` -- the one site
# `layer_rule` actually protects -- through a real `psycopg.errors.
# DataError`; it now also asserts the no-`violated_declaration` invariant
# this test used to.
# ---------------------------------------------------------------------------


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


def test_idempotency_replay_of_a_pre_1_7_0_record_falls_back_to_the_resend_own_request_id(service, runtime):
    """WP-2e rework (audit-wp2e.md I-1, ruling L-6): a record written by a
    pre-contract-1.7.0 build never had a `request_id` in its stored
    payload at all -- `payload.get("request_id")` on such a record is
    `None`, and the contract's `MutationResult.request_id` is `"type":
    "string"` (null not permitted). Q-4's own rule ("replay は元実行の
    request_id") governs only when the ORIGINAL execution's value IS on
    record; a record with none is treated as having none, and the resend's
    OWN `request_id` is used instead -- never a `None` reaching the
    response. Simulates the pre-1.7.0 record shape directly (§3-B probe
    procedure) by deleting `request_id` from the stored payload after a
    normal insert-and-record, exactly what a record written before this
    contract version would already look like on disk/in-memory."""
    key = "wp2e-idem-key-pre-1-7-0"
    first = service.mutate_result(runtime, "notes", [{"operation": "insert", "values": {"body": "pre170"}}], idempotency_key=key)
    assert first.request_id
    cell = service._cells[runtime.application_id]
    record = cell._idempotency[key]
    del record.payload["request_id"]
    assert "request_id" not in record.payload  # simulated pre-1.7.0 record shape
    second = service.mutate_result(runtime, "notes", [{"operation": "insert", "values": {"body": "pre170"}}], idempotency_key=key)
    assert second.request_id is not None
    assert second.request_id != first.request_id  # the record had none recorded -- this resend's own value is used
    assert second.affected == first.affected == 1  # still a replay, not a second insert


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


def test_http_query_and_schema_responses_never_regenerate_request_id(service, developer):
    """WP-2e rework (audit-wp2e.md I-2, ruling L-7): completion condition 9
    (`request_id` never re-derived by the HTTP layer) previously had ONLY
    the mutations endpoint under real observation -- a mutation to
    `http.py:post_query`'s own `"request_id": result.request_id` that
    substitutes a freshly-minted `uuid.uuid4().hex` instead was not
    detected by ANY peer-local or conformance test (audit finding,
    实測: 335 passed with that mutation live). Query (`POST /v1/data/
    {entity}/query`) and schema (`POST /v1/schema/operations`) are pinned
    here the SAME way -- `x-request-id` header == body `request_id` --
    closing that observation gap for all 3 data-plane endpoints."""
    from starlette.testclient import TestClient
    from r2db_api.http import create_app

    app = create_app(service)
    client = TestClient(app)
    headers = {"Authorization": "Bearer dev-a.dev-secret-a"}

    query_response = client.post("/v1/data/notes/query", headers=headers, json={"select": ["id"]})
    assert query_response.status_code == 200
    query_body = query_response.json()
    assert query_body.get("request_id"), query_body
    assert query_response.headers.get("x-request-id") == query_body["request_id"]

    schema_response = client.post(
        "/v1/schema/operations",
        headers=headers,
        json={"operation": "add_field", "entity": "notes", "field": "wp2e_rework_tag", "field_type": "string"},
    )
    assert schema_response.status_code == 200
    schema_body = schema_response.json()
    assert schema_body.get("request_id"), schema_body
    assert schema_response.headers.get("x-request-id") == schema_body["request_id"]


# ---------------------------------------------------------------------------
# Completion condition 10: `contract_version` reads 1.7.0 on both the data
# plane (`DataService.capabilities`) and the control plane
# (`ControlPlaneService.capabilities`) -- C-19's own data/control match.
# ---------------------------------------------------------------------------


def test_contract_version_is_1_7_0_on_data_plane(service, runtime):
    document = service.capabilities(runtime)
    assert document["contract_version"] == "1.7.0"


# ---------------------------------------------------------------------------
# Completion condition 11: `ops verify-declarations` checks that the
# contract 1.7.0 "enabled" declaration is TRUE of the deployed state --
# `check_contract_170_declarations` (F-14).
#
# WP-2e rework (audit-wp2e.md D-2, ruling L-2 = (A)): `check_contract_170_
# resource_limits` was replaced (never renamed in place -- the old
# function constructed its OWN default `ResourceLimits()` and could
# therefore never actually observe a broken one; `PlatformDeclarationError
# (code="F-14")` could never be raised through the real `ops verify-
# declarations` path, only through a synthetic direct call). The new
# function takes the caller's own served capabilities document and
# deployed `ResourceLimits` as arguments (never builds either itself), and
# additionally checks EVERY registered application's own per-application
# upgrade ledger against `platform_upgrades.PLATFORM_UPGRADE_NUMBERS` --
# the one part of F-14 a real deployment can actually fail. That ledger
# check needs a real PostgreSQL connection per application and is
# therefore exercised in `test_ops_upgrade.py` (`test_verify_declarations_
# f14_fails_when_an_application_has_not_applied_every_upgrade`), not here.
# ---------------------------------------------------------------------------


def _ok_capabilities_document():
    return {"capabilities": {name: {"status": "enabled"} for name in platform_declarations._CONTRACT_170_ENABLED_CAPABILITIES}}


def test_verify_declarations_accepts_the_shipped_default_state():
    platform_declarations.check_contract_170_declarations(
        _ok_capabilities_document(), ResourceLimits(), {}, platform_upgrades.PLATFORM_UPGRADE_NUMBERS,
    )  # must not raise; {} = no registered applications to check


@pytest.mark.parametrize("capability_name", list(platform_declarations._CONTRACT_170_ENABLED_CAPABILITIES))
def test_verify_declarations_rejects_a_capability_not_declared_enabled(capability_name):
    document = _ok_capabilities_document()
    document["capabilities"][capability_name] = {"status": "unavailable"}
    with pytest.raises(platform_declarations.PlatformDeclarationError) as exc:
        platform_declarations.check_contract_170_declarations(
            document, ResourceLimits(), {}, platform_upgrades.PLATFORM_UPGRADE_NUMBERS,
        )
    assert exc.value.code == "F-14"
    assert capability_name in str(exc.value)


@pytest.mark.parametrize("field_name", ["enum_members", "idempotency_entries", "idempotency_retention_ms"])
def test_verify_declarations_rejects_a_non_positive_new_limit(field_name):
    """`ResourceLimits.__post_init__` (`r2db_api/limits.py:48-51`) already
    refuses to CONSTRUCT an instance carrying a non-positive value for any
    class, including these three -- so this can never observe one through
    a real `ResourceLimits` object in this process. Exercised here against
    a minimal duck-typed stand-in (only `getattr(limits, name)` is read,
    `check_contract_170_declarations` never asserts `isinstance(limits,
    ResourceLimits)`) so the CHECK FUNCTION's own logic is still under
    real, falsifiable test -- this is the honest scope of what this half
    of F-14 can catch: a REGRESSION in a caller that stops going through
    `ResourceLimits.__post_init__` at all, not a live `ResourceLimits`
    instance in today's process."""
    import types
    bad = types.SimpleNamespace(**{**ResourceLimits().as_dict(), field_name: 0})
    with pytest.raises(platform_declarations.PlatformDeclarationError) as exc:
        platform_declarations.check_contract_170_declarations(
            _ok_capabilities_document(), bad, {}, platform_upgrades.PLATFORM_UPGRADE_NUMBERS,
        )
    assert exc.value.code == "F-14"


def test_verify_declarations_rejects_an_application_missing_a_required_upgrade():
    """The set-difference half of F-14 (ruling L-2): an application whose
    own ledger is missing even one required number fails closed, naming
    that application and its pending numbers -- duck-typed against
    `platform_upgrades.PLATFORM_UPGRADE_NUMBERS` itself so this stays
    correct if a future WP grows that set."""
    incomplete = frozenset(platform_upgrades.PLATFORM_UPGRADE_NUMBERS - {min(platform_upgrades.PLATFORM_UPGRADE_NUMBERS)})
    with pytest.raises(platform_declarations.PlatformDeclarationError) as exc:
        platform_declarations.check_contract_170_declarations(
            _ok_capabilities_document(), ResourceLimits(),
            {"complete-app": platform_upgrades.PLATFORM_UPGRADE_NUMBERS, "lagging-app": incomplete},
            platform_upgrades.PLATFORM_UPGRADE_NUMBERS,
        )
    assert exc.value.code == "F-14"
    assert "lagging-app" in str(exc.value)
    assert "complete-app" not in str(exc.value)


def test_verify_declarations_treats_a_missing_ledger_as_every_number_pending():
    """`None` (`platform_upgrades.read_applied_upgrade_numbers`'s own "no
    ledger table at all" sentinel) means every required number is
    pending -- the same convention `platform_upgrades.pending_upgrade_
    numbers` already uses, not a separate silent-pass special case."""
    with pytest.raises(platform_declarations.PlatformDeclarationError) as exc:
        platform_declarations.check_contract_170_declarations(
            _ok_capabilities_document(), ResourceLimits(), {"unprovisioned-app": None}, platform_upgrades.PLATFORM_UPGRADE_NUMBERS,
        )
    assert exc.value.code == "F-14"
    assert "unprovisioned-app" in str(exc.value)


def test_verify_declarations_exit_code_table_has_f14():
    assert r2db_ops._VERIFY_DECLARATIONS_EXIT_CODES["F-14"] not in (
        code for name, code in r2db_ops._VERIFY_DECLARATIONS_EXIT_CODES.items() if name != "F-14"
    )


def test_contract_170_capabilities_document_declares_every_required_capability_enabled():
    """WP-2e rework (ruling L-2): `ops._contract_170_capabilities_document`
    is the REAL `DataService.capabilities()` output for a throwaway
    in-memory application -- not a hand-written stand-in -- so this pins
    that the production code path actually satisfies F-14's own
    requirement, catching a future regression in `service.py` the same
    gate operators already run would catch."""
    document = r2db_ops._contract_170_capabilities_document()
    platform_declarations.check_contract_170_declarations(
        document, ResourceLimits(), {}, platform_upgrades.PLATFORM_UPGRADE_NUMBERS,
    )  # must not raise
