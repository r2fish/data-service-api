import pytest
from dataclasses import replace
import json
from pathlib import Path
import threading
import time

from r2db_api import ControlAuthority, CredentialStore, DataService
from r2db_api.errors import FoundationError
from r2db_api.limits import ResourceLimits


@pytest.fixture
def service():
    credentials = CredentialStore(pepper="test-pepper")
    credentials.add("cred-a", "app-a", "runtime", "secret-a")
    credentials.add("cred-b", "app-b", "runtime", "secret-b")
    credentials.add("dev-a", "app-a", "developer", "dev-secret-a")
    service = DataService(credentials)
    control = ControlAuthority(service)
    control.register_application("app-a", entities={"notes": [{"id": 1, "body": "a"}]})
    control.register_application("app-b", entities={"notes": [{"id": 2, "body": "b"}]})
    return service


def test_server_bound_scope_and_isolation(service):
    a = service.authenticate("secret-a")
    with pytest.raises(FoundationError) as tampered:
        service.query(replace(a, application_id="app-b"), "notes", select=["id"])
    assert tampered.value.code == "SCOPE_MISMATCH"
    assert service.query(a, "notes", select=["id"]) == [{"id": 1}]
    with pytest.raises(FoundationError) as exc:
        service.query(a, "notes", select=["id"], where=[{"field": "application_id", "operator": "eq", "value": "app-b"}])
    # The supplied field is merely a data predicate; it cannot switch cells.
    assert exc.value.code == "NOT_FOUND" or exc.value.code == "VALIDATION_FAILED"


def test_runtime_developer_separation_and_structured_validation(service):
    runtime = service.authenticate("secret-a")
    with pytest.raises(FoundationError) as exc:
        service.schema(runtime, {"operation": "create_entity", "entity": "new_entity"})
    assert exc.value.code == "FORBIDDEN"
    developer = service.authenticate("dev-secret-a")
    assert service.schema(developer, {"operation": "create_entity", "entity": "new_entity"}) == 1
    with pytest.raises(FoundationError):
        service.query(runtime, "notes;drop", select=["id"])


def test_atomic_rollback_and_explicit_destructive_operation(service):
    runtime = service.authenticate("secret-a")
    with pytest.raises(FoundationError):
        service.mutate(runtime, "notes", [{"operation": "insert", "values": {"id": 3}}, {"operation": "unsupported"}])
    assert service.query(runtime, "notes", select=["id"]) == [{"id": 1}]
    with pytest.raises(FoundationError) as exc:
        service.mutate(runtime, "notes", [{"operation": "delete", "where": [{"field": "id", "operator": "eq", "value": 1}]}])
    assert exc.value.code == "DESTRUCTIVE_CONFIRMATION_REQUIRED"
    with pytest.raises(FoundationError) as unsupported:
        service.mutate(runtime, "notes", [{"operation": "insert", "values": {"id": 3}}], transaction="best_effort")
    assert unsupported.value.code == "CAPABILITY_UNSUPPORTED"


def test_runtime_unknown_entity_and_failed_mutation_leave_no_ghost(service):
    runtime = service.authenticate("secret-a")
    with pytest.raises(FoundationError) as unknown:
        service.mutate(runtime, "ghost", [{"operation": "insert", "values": {"id": 1}}])
    assert unknown.value.code == "NOT_FOUND"
    with pytest.raises(FoundationError) as absent:
        service.query(runtime, "ghost", select=["id"])
    assert absent.value.code == "NOT_FOUND"
    with pytest.raises(FoundationError):
        service.mutate(runtime, "notes", [{"operation": "insert", "values": {"id": 2}}, {"operation": "insert", "values": {"unknown_field": 3}}])
    assert service.query(runtime, "notes", select=["id"]) == [{"id": 1}]


def test_developer_schema_catalog_controls_fields(service):
    developer = service.authenticate("dev-secret-a")
    assert service.schema(developer, {"operation": "add_field", "entity": "notes", "field": "tag"}) == 1
    runtime = service.authenticate("secret-a")
    with pytest.raises(FoundationError) as field_error:
        service.mutate(runtime, "notes", [{"operation": "insert", "values": {"unlisted": "x"}}])
    assert field_error.value.code == "NOT_FOUND"
    with pytest.raises(FoundationError) as malformed:
        service.schema(developer, None)
    assert malformed.value.code == "VALIDATION_FAILED"
    with pytest.raises(FoundationError):
        service.schema(developer, {"operation": "create_entity", "entity": "partial", "fields": ["ok", "bad-field;"]})
    with pytest.raises(FoundationError) as ghost:
        service.query(runtime, "partial", select=["ok"])
    assert ghost.value.code == "NOT_FOUND"


def test_revoke_disable_and_unavailable_state_fail_closed(service):
    runtime = service.authenticate("secret-a")
    control = ControlAuthority(service)
    control.set_credential_state("cred-a", revoked=True)
    with pytest.raises(FoundationError) as exc:
        service.query(runtime, "notes", select=["id"])
    assert exc.value.code == "AUTH_REVOKED"
    control.set_credential_state("cred-a", revoked=False)
    control.set_application_enabled("app-a", enabled=False)
    with pytest.raises(FoundationError) as exc:
        service.query(runtime, "notes", select=["id"])
    assert exc.value.code == "APPLICATION_DISABLED"
    control.set_application_enabled("app-a", enabled=True)
    control.set_authorization_state_available(False)
    with pytest.raises(FoundationError) as exc:
        service.query(runtime, "notes", select=["id"])
    assert exc.value.code == "AUTH_STATE_UNAVAILABLE"


def test_finite_limits_are_enforced_and_discoverable(service):
    runtime = service.authenticate("secret-a")
    response = service.capabilities(runtime)
    assert all(value > 0 for value in response["limits"].values())
    assert response["capabilities"]["structured_query"]["status"] == "enabled"
    assert response["capabilities"]["audit_query"]["status"] == "unavailable"
    assert set(response["limit_enforcement"].values()) <= {"enforced", "reference_wall_clock", "deployment_required", "unavailable"}
    with pytest.raises(FoundationError) as exc:
        service.query(runtime, "notes", select=["id"], page_size=0)
    assert exc.value.code == "LIMIT_EXCEEDED"


def test_audit_is_append_only_and_secret_free(service):
    assert not hasattr(service, "audit")
    assert not hasattr(service, "credentials")
    runtime = service.authenticate("secret-a")
    service.query(runtime, "notes", select=["id"])
    events = ControlAuthority(service).audit_events()
    assert events
    assert all(not any(token in str(event).lower() for token in ("secret-a", "password", "sql", "row_value")) for event in events)
    with pytest.raises(PermissionError):
        ControlAuthority(service).delete_audit()
    tamper_failures = [event for event in ControlAuthority(service).audit_events() if event.get("operation") == "delete_audit"]
    assert tamper_failures and tamper_failures[-1]["reason_code"] == "AUDIT_APPEND_ONLY"


def test_control_lifecycle_and_failures_are_canonical_audit_events(service):
    control = ControlAuthority(service)
    control.set_application_enabled("app-a", enabled=False)
    control.set_application_enabled("app-a", enabled=True)
    control.set_credential_state("cred-a", revoked=True)
    with pytest.raises(FoundationError):
        control.set_credential_state("missing-credential", revoked=True)
    events = control.audit_events()
    classes = [event["event_class"] for event in events]
    assert "application_lifecycle" in classes
    assert "credential_lifecycle" in classes
    assert "control_failure" in classes
    credential_events = [event for event in events if event["event_class"] == "credential_lifecycle"]
    assert credential_events and credential_events[-1]["application_id"] == "app-a"
    assert all(event.get("actor_type") == "control_authority" for event in events if event["event_class"] in {"application_lifecycle", "credential_lifecycle", "control_failure"})
    assert all("secret" not in str(event).lower() for event in events)


def test_malformed_inputs_fail_with_safe_foundation_errors(service):
    runtime = service.authenticate("secret-a")
    cases = [
        lambda: service.query(runtime, "notes", select="id"),
        lambda: service.query(runtime, "notes", select=["id"], where=[{}]),
        lambda: service.query(runtime, "notes", select=["id"], where=[{"field": "id"}]),
        lambda: service.mutate(runtime, "notes", None),
        lambda: service.schema(runtime, None),
    ]
    for case in cases:
        with pytest.raises(FoundationError) as error:
            case()
        assert error.value.code in {"VALIDATION_FAILED", "FORBIDDEN"}
        problem = error.value.problem("fixture-request")
        assert set(problem) == {"type", "code", "message", "request_id", "details"}


def _limited(**kwargs):
    credentials = CredentialStore(pepper="limit-pepper")
    credentials.add("limit-cred", "limit-app", "runtime", "limit-secret")
    service = DataService(credentials, limits=ResourceLimits(**kwargs))
    ControlAuthority(service).register_application("limit-app", entities={"items": [{"id": 1}, {"id": 2}]})
    return service, service.authenticate("limit-secret")


def test_request_body_limit_has_a_deterministic_boundary():
    service, context = _limited(request_bytes=10)
    with pytest.raises(FoundationError) as error:
        service.query(context, "items", select=["id"])
    assert error.value.code == "LIMIT_EXCEEDED"


def test_deep_cyclic_and_oversized_requests_are_rejected_without_recursion_or_repr():
    service, context = _limited()
    deep: dict[str, object] = {}
    cursor = deep
    for _ in range(1200):
        cursor["next"] = {}
        cursor = cursor["next"]
    with pytest.raises(FoundationError) as deep_error:
        service.query(context, "items", select=["id"], where=[{"field": "id", "operator": "eq", "value": deep}])
    assert deep_error.value.code == "LIMIT_EXCEEDED"

    service, context = _limited()
    cyclic: list[object] = []
    cyclic.append(cyclic)
    with pytest.raises(FoundationError) as cycle_error:
        service.query(context, "items", select=["id"], where=[{"field": "id", "operator": "eq", "value": cyclic}])
    assert cycle_error.value.code == "VALIDATION_FAILED"

    service, context = _limited()
    with pytest.raises(FoundationError) as size_error:
        service.query(context, "items", select=["id"], where=[{"field": "id", "operator": "eq", "value": "x" * 2_000_000}])
    assert size_error.value.code == "LIMIT_EXCEEDED"


def test_r2_capability_artifact_matches_discovery_status_vocabulary():
    artifact = json.loads((Path(__file__).parents[1] / "config" / "capabilities.json").read_text())
    assert artifact["implementation"] == "r2db_foundation"
    assert set(artifact["enabled"]).isdisjoint(artifact["unavailable"])
    assert set(artifact["limit_enforcement"].values()) <= {"enforced", "reference_wall_clock", "deployment_required", "unavailable"}


def test_capability_response_matches_common_capability_document_schema(service):
    contract = json.loads((Path(__file__).parents[2] / "spec" / "data-service-api.v1.json").read_text())
    schema = contract["schemas"]["CapabilityDocument"]
    runtime = service.authenticate("secret-a")
    response = service.capabilities(runtime)
    assert set(schema["required"]).issubset(response)
    statuses = set(contract["capability_status"]["status_enum"])
    enforcement = set(contract["capability_status"]["enforcement_enum"])
    assert all(item["status"] in statuses for item in response["capabilities"].values())
    assert set(response["limits"]) == set(response["limit_enforcement"])
    assert all(value in enforcement for value in response["limit_enforcement"].values())


def test_rate_limit_is_atomic_for_concurrent_requests():
    service, context = _limited(requests_per_minute=1)
    barrier = threading.Barrier(3)
    outcomes: list[str] = []

    def request() -> None:
        barrier.wait()
        try:
            service.query(context, "items", select=["id"])
            outcomes.append("ok")
        except FoundationError as error:
            outcomes.append(error.code)

    threads = [threading.Thread(target=request) for _ in range(2)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join()
    assert outcomes.count("ok") == 1
    assert outcomes.count("LIMIT_EXCEEDED") == 1
    denied = [event for event in ControlAuthority(service).audit_events() if event.get("outcome") == "deny"]
    assert denied and denied[-1]["reason_code"] == "LIMIT_EXCEEDED"


def test_schema_deadline_failure_rolls_back_entity_catalog_and_revision():
    clock_values = iter([0.0, 0.0, 0.0, 0.01])
    service, context = _limited(execution_ms=1)
    ControlAuthority(service).issue_credential("schema-dev", "limit-app", "developer", "schema-dev-secret")
    developer = service.authenticate("schema-dev-secret")
    service._clock = lambda: next(clock_values)
    with pytest.raises(FoundationError) as error:
        service.schema(developer, {"operation": "create_entity", "entity": "deadline_entity", "fields": ["value"]})
    assert error.value.code == "LIMIT_EXCEEDED"
    service._clock = time.monotonic
    with pytest.raises(FoundationError) as absent:
        service.query(context, "deadline_entity", select=["value"])
    assert absent.value.code == "NOT_FOUND"


def test_every_advertised_resource_limit_has_a_deterministic_boundary():
    service, context = _limited(batch_items=1)
    with pytest.raises(FoundationError) as error:
        service.mutate(context, "items", [{"operation": "insert", "values": {"id": 3}}, {"operation": "insert", "values": {"id": 4}}])
    assert error.value.code == "LIMIT_EXCEEDED"

    service, context = _limited(result_items=1)
    with pytest.raises(FoundationError) as error:
        service.mutate(context, "items", [{"operation": "delete", "where": [{"field": "id", "operator": "in", "value": [1, 2]}], "destructive": True, "confirmation": "DELETE"}])
    assert error.value.code == "LIMIT_EXCEEDED"

    service, context = _limited(query_complexity=1)
    with pytest.raises(FoundationError) as error:
        service.query(context, "items", select=["id"], where=[{"field": "id", "operator": "eq", "value": 1}])
    assert error.value.code == "LIMIT_EXCEEDED"

    service, context = _limited(operation_depth=2)
    with pytest.raises(FoundationError) as error:
        service.query(context, "items", select=["id"], where=[{"field": "id", "operator": "eq", "value": {"nested": {"too_deep": True}}}])
    assert error.value.code == "LIMIT_EXCEEDED"

    service, context = _limited(schema_objects=1)
    ControlAuthority(service).issue_credential("limit-dev", "limit-app", "developer", "limit-dev-secret")
    dev_context = service.authenticate("limit-dev-secret")
    with pytest.raises(FoundationError) as error:
        service.schema(dev_context, {"operation": "add_field", "entity": "items", "field": "new_field"})
    assert error.value.code == "LIMIT_EXCEEDED"
    with pytest.raises(FoundationError) as no_side_effect:
        service.query(context, "items", select=["new_field"])
    assert no_side_effect.value.code == "NOT_FOUND"

    clock_values = iter([0.0, 0.0, 0.01])
    service, context = _limited(execution_ms=1)
    service._clock = lambda: next(clock_values)
    with pytest.raises(FoundationError) as error:
        service.query(context, "items", select=["id"])
    assert error.value.code == "LIMIT_EXCEEDED"

    service, context = _limited(concurrency=1)
    service._active = 1
    with pytest.raises(FoundationError) as error:
        service.query(context, "items", select=["id"])
    assert error.value.code == "LIMIT_EXCEEDED"

    service, context = _limited(requests_per_minute=1)
    service.query(context, "items", select=["id"])
    with pytest.raises(FoundationError) as error:
        service.query(context, "items", select=["id"])
    assert error.value.code == "LIMIT_EXCEEDED"
