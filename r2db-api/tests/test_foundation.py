import base64
import pytest
from dataclasses import replace
import json
from pathlib import Path
import threading
import time

from r2db_api import ControlAuthority, CredentialStore, DataService
from r2db_api.errors import FoundationError
from r2db_api.limits import ResourceLimits
from r2db_api.structured import (
    ApplicationCell,
    Predicate,
    QueryOutcome,
    delete_confirmation_phrase,
    drop_entity_confirmation_phrase,
    drop_index_confirmation_phrase,
)


def _delete_phrase(entity: str, where: list[dict], schema_revision: int = 0) -> str:
    """Test-local helper (WP-3, declare-and-echo effectivization; `schema_
    revision` parameter added per Opus review minor m-2/Q1-D10, which folded
    the Application's schema_revision into the delete phrase too): computes
    the REAL, current `delete` confirmation phrase from the same shared
    function `structured.py`'s own `require_destructive_confirmation` call
    site uses, rather than a hardcoded literal (the old fixed `"DELETE"`
    token this WP retires) -- every local test that exercises a real
    destructive `delete` now echoes this exact phrase back. `schema_
    revision` defaults to `0` -- every call site below either passes the
    real cell's own `cell.schema_revision` explicitly, or (the `service`-
    fixture-based call sites) never performs a schema operation before its
    own delete call, so the freshly-provisioned cell's schema_revision is
    genuinely still `0` at that point."""
    return delete_confirmation_phrase(entity, [Predicate(field=p["field"], operator=p["operator"], value=p.get("value")) for p in where], schema_revision)


@pytest.fixture
def service():
    credentials = CredentialStore(pepper="test-pepper")
    with credentials.unit_of_work() as work:
        credentials.add("cred-a", "app-a", "runtime", "secret-a", work=work)
    with credentials.unit_of_work() as work:
        credentials.add("cred-b", "app-b", "runtime", "secret-b", work=work)
    with credentials.unit_of_work() as work:
        credentials.add("dev-a", "app-a", "developer", "dev-secret-a", work=work)
    service = DataService(credentials)
    control = ControlAuthority(service)
    # Contract 1.1.0 (CCR-13, docs/design/R2DB_CCR13_STORAGE_V1.md R-3):
    # `id` is now the server-assigned row address, so seed fixtures no
    # longer supply it -- each cell auto-assigns it (starting at 1) via the
    # normal insert path (m-9). app-a's and app-b's `notes` are separate
    # `ApplicationCell`s with independent counters, so both seeded rows get
    # `id == 1` in their own cell.
    control.register_application("app-a", entities={"notes": [{"body": "a"}]})
    control.register_application("app-b", entities={"notes": [{"body": "b"}]})
    return service


def test_server_bound_scope_and_isolation(service):
    a = service.authenticate("cred-a.secret-a")
    with pytest.raises(FoundationError) as tampered:
        service.query(replace(a, application_id="app-b"), "notes", select=["id"])
    assert tampered.value.code == "SCOPE_MISMATCH"
    assert service.query(a, "notes", select=["id"]) == [{"id": 1}]
    with pytest.raises(FoundationError) as exc:
        service.query(a, "notes", select=["id"], where=[{"field": "application_id", "operator": "eq", "value": "app-b"}])
    # The supplied field is merely a data predicate; it cannot switch cells.
    assert exc.value.code == "NOT_FOUND" or exc.value.code == "VALIDATION_FAILED"


def test_runtime_developer_separation_and_structured_validation(service):
    runtime = service.authenticate("cred-a.secret-a")
    with pytest.raises(FoundationError) as exc:
        service.schema(runtime, {"operation": "create_entity", "entity": "new_entity"})
    assert exc.value.code == "FORBIDDEN"
    developer = service.authenticate("dev-a.dev-secret-a")
    assert service.schema(developer, {"operation": "create_entity", "entity": "new_entity"}).revision == 1
    with pytest.raises(FoundationError):
        service.query(runtime, "notes;drop", select=["id"])


def test_atomic_rollback_and_explicit_destructive_operation(service):
    runtime = service.authenticate("cred-a.secret-a")
    with pytest.raises(FoundationError):
        service.mutate(runtime, "notes", [{"operation": "insert", "values": {"body": "c"}}, {"operation": "unsupported"}])
    assert service.query(runtime, "notes", select=["id"]) == [{"id": 1}]
    with pytest.raises(FoundationError) as exc:
        service.mutate(runtime, "notes", [{"operation": "delete", "where": [{"field": "id", "operator": "eq", "value": 1}]}])
    assert exc.value.code == "DESTRUCTIVE_CONFIRMATION_REQUIRED"
    with pytest.raises(FoundationError) as unsupported:
        service.mutate(runtime, "notes", [{"operation": "insert", "values": {"body": "c"}}], transaction="best_effort")
    assert unsupported.value.code == "CAPABILITY_UNSUPPORTED"


def test_insert_or_update_supplying_the_server_assigned_id_is_rejected(service):
    """R-3, property 4: `id` is always server-assigned; a client can read
    it (select/where/order_by) but never write it, on any mutation."""
    runtime = service.authenticate("cred-a.secret-a")
    with pytest.raises(FoundationError) as exc:
        service.mutate(runtime, "notes", [{"operation": "insert", "values": {"id": 99, "body": "x"}}])
    assert exc.value.code == "VALIDATION_FAILED"
    with pytest.raises(FoundationError) as exc:
        service.mutate(runtime, "notes", [{"operation": "update", "where": [{"field": "id", "operator": "eq", "value": 1}], "values": {"id": 2}}])
    assert exc.value.code == "VALIDATION_FAILED"
    assert service.query(runtime, "notes", select=["id"]) == [{"id": 1}]


def test_insert_with_a_filter_is_validation_failed(service):
    """WP-2 review M-4: `insert`'s `where` used to be parsed and then
    silently never used by any backend's insert path -- the same
    silent-ignore shape upsert's own `where` rejection closes, closed
    symmetrically for insert."""
    runtime = service.authenticate("cred-a.secret-a")
    with pytest.raises(FoundationError) as exc:
        service.mutate(runtime, "notes", [{"operation": "insert", "values": {"body": "z"}, "where": [{"field": "id", "operator": "eq", "value": 1}]}])
    assert exc.value.code == "VALIDATION_FAILED"
    assert service.query(runtime, "notes", select=["id"]) == [{"id": 1}]


def test_runtime_unknown_entity_and_failed_mutation_leave_no_ghost(service):
    runtime = service.authenticate("cred-a.secret-a")
    with pytest.raises(FoundationError) as unknown:
        service.mutate(runtime, "ghost", [{"operation": "insert", "values": {}}])
    assert unknown.value.code == "NOT_FOUND"
    with pytest.raises(FoundationError) as absent:
        service.query(runtime, "ghost", select=["id"])
    assert absent.value.code == "NOT_FOUND"
    with pytest.raises(FoundationError):
        service.mutate(runtime, "notes", [{"operation": "insert", "values": {"body": "c"}}, {"operation": "insert", "values": {"unknown_field": 3}}])
    assert service.query(runtime, "notes", select=["id"]) == [{"id": 1}]


def test_developer_schema_catalog_controls_fields(service):
    developer = service.authenticate("dev-a.dev-secret-a")
    assert service.schema(developer, {"operation": "add_field", "entity": "notes", "field": "tag"}).revision == 1
    runtime = service.authenticate("cred-a.secret-a")
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
    runtime = service.authenticate("cred-a.secret-a")
    control = ControlAuthority(service)
    control.set_credential_state("cred-a", revoked=True)
    with pytest.raises(FoundationError) as exc:
        service.query(runtime, "notes", select=["id"])
    assert exc.value.code == "AUTH_REVOKED"
    # Revocation is terminal (contract 1.1.0 lifecycle.credential): cred-a
    # cannot come back, so the rest of this test continues on a freshly
    # issued credential rather than un-revoking cred-a for fixture
    # convenience (docs/design/CONFORMANCE_CONDITIONS_V1_1.md section 5).
    control.issue_credential("cred-a2", "app-a", "runtime", "secret-a2")
    runtime2 = service.authenticate("cred-a2.secret-a2")
    control.set_application_enabled("app-a", enabled=False)
    with pytest.raises(FoundationError) as exc:
        service.query(runtime2, "notes", select=["id"])
    assert exc.value.code == "APPLICATION_DISABLED"
    control.set_application_enabled("app-a", enabled=True)
    control.set_authorization_state_available(False)
    with pytest.raises(FoundationError) as exc:
        service.query(runtime2, "notes", select=["id"])
    assert exc.value.code == "AUTH_STATE_UNAVAILABLE"


def test_revoked_credential_cannot_be_un_revoked(service):
    """Contract 1.1.0 lifecycle.credential: revocation is terminal. No
    control-plane call -- including a later `revoked=False` -- may clear it.
    """
    runtime = service.authenticate("cred-a.secret-a")
    control = ControlAuthority(service)
    control.set_credential_state("cred-a", revoked=True)
    with pytest.raises(FoundationError) as exc:
        control.set_credential_state("cred-a", revoked=False)
    assert exc.value.code == "VALIDATION_FAILED"
    # Still revoked: the rejected un-revoke attempt did not weaken anything.
    with pytest.raises(FoundationError) as exc:
        service.query(runtime, "notes", select=["id"])
    assert exc.value.code == "AUTH_REVOKED"
    # enabled=True alone (no revoked=False) is accepted -- it is a distinct,
    # non-terminal flag -- but does not undo the terminal revocation.
    control.set_credential_state("cred-a", enabled=True)
    with pytest.raises(FoundationError) as exc:
        service.query(runtime, "notes", select=["id"])
    assert exc.value.code == "AUTH_REVOKED"


def test_unrevoked_credential_enabled_false_true_round_trip_still_allowed(service):
    """The terminal-revoke rule is scoped to `revoked`; disable/re-enable of
    a never-revoked credential is unaffected."""
    control = ControlAuthority(service)
    control.set_credential_state("cred-a", enabled=False)
    with pytest.raises(FoundationError) as exc:
        service.authenticate("cred-a.secret-a")
    assert exc.value.code == "AUTH_INVALID"
    control.set_credential_state("cred-a", revoked=False)  # no-op: never revoked
    control.set_credential_state("cred-a", enabled=True)
    assert service.authenticate("cred-a.secret-a").application_id == "app-a"


def test_authenticate_fails_closed_for_disabled_application(service):
    control = ControlAuthority(service)
    control.set_application_enabled("app-a", enabled=False)
    with pytest.raises(FoundationError) as exc:
        service.authenticate("cred-a.secret-a")
    assert exc.value.code == "APPLICATION_DISABLED"
    denials = [event for event in control.audit_events() if event.get("operation") == "authenticate" and event.get("outcome") == "deny"]
    assert denials and denials[-1]["reason_code"] == "APPLICATION_DISABLED"
    control.set_application_enabled("app-a", enabled=True)
    assert service.authenticate("cred-a.secret-a").application_id == "app-a"


def test_data_plane_capabilities_declares_contract_1_6_0(service):
    """Phase 6 WP-2 (design D-5, version_binding): `DataService.
    capabilities()` declares `contract_version: "1.6.0"` -- the data-plane
    half of the flip (`ControlPlaneService`'s own equivalent pin lives in
    `test_control_plane_service.py`/`test_audit_query.py`). Two SEPARATE
    pins for the two planes -- a mutation reverting only one plane's flip
    (work order mutation 15) turns exactly one of the two red, never
    both.

    Phase 9 WP-2e (design D-1 (5)): re-flipped to 1.7.0 in the same commit
    as the R-3/R-7 behavior this WP ships -- function name kept (matching
    this file's own precedent of retaining an earlier version's name on a
    since-re-flipped pin, e.g. `test_control_capabilities_declares_
    contract_version_1_5_0` in `test_audit_query.py`, which already
    asserted 1.6.0 before this WP)."""
    runtime = service.authenticate("cred-a.secret-a")
    document = service.capabilities(runtime)
    assert document["contract_version"] == "1.7.0"


def test_catalog_returns_shaped_document_scoped_to_application(service):
    """CCR-13 WP-5b: `row_addressability` is declared `enabled`, so
    `DataService.catalog()` publishes the full `EntityDescriptor` shape
    `ApplicationCell.catalog()` itself computes -- no narrowing."""
    runtime = service.authenticate("cred-a.secret-a")
    document = service.catalog(runtime)
    # Phase 6 WP-2 (design D-3(iii)): `field_types` is now a real key on
    # every entity descriptor -- `body` was created with no declared type,
    # so it reports `json` (decision (ii)'s default); `id` is always
    # `integer` (server-assigned address). Contract 1.7.0 (D-2 (1), WP-2a):
    # `field_constraints` is now a real key too -- total over `fields`,
    # `nullable: true` and no `enum` for every field here (nothing was
    # ever declared).
    assert document == {
        "application_scope": "app-a",
        "entities": [
            {
                "entity": "notes",
                "fields": ["body", "id"],
                "field_types": {"body": "json", "id": "integer"},
                "field_constraints": {"body": {"nullable": True}, "id": {"nullable": True}},
                "mutation_class": "mutable",
                "address_fields": ["id"],
                "address_reuse": "never",
                "unique_keys": [],
            }
        ],
    }
    other = service.authenticate("cred-b.secret-b")
    assert service.catalog(other) == {
        "application_scope": "app-b",
        "entities": [
            {
                "entity": "notes",
                "fields": ["body", "id"],
                "field_types": {"body": "json", "id": "integer"},
                "field_constraints": {"body": {"nullable": True}, "id": {"nullable": True}},
                "mutation_class": "mutable",
                "address_fields": ["id"],
                "address_reuse": "never",
                "unique_keys": [],
            }
        ],
    }


def test_catalog_denied_for_revoked_credential_exactly_as_query(service):
    runtime = service.authenticate("cred-a.secret-a")
    control = ControlAuthority(service)
    control.set_credential_state("cred-a", revoked=True)
    with pytest.raises(FoundationError) as exc:
        service.catalog(runtime)
    assert exc.value.code == "AUTH_REVOKED"


def test_finite_limits_are_enforced_and_discoverable(service):
    runtime = service.authenticate("cred-a.secret-a")
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
    runtime = service.authenticate("cred-a.secret-a")
    service.query(runtime, "notes", select=["id"])
    events = ControlAuthority(service).audit_events()
    assert events
    assert all(not any(token in str(event).lower() for token in ("cred-a.secret-a", "password", "sql", "row_value")) for event in events)
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
    runtime = service.authenticate("cred-a.secret-a")
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
    with credentials.unit_of_work() as work:
        credentials.add("limit-cred", "limit-app", "runtime", "limit-secret", work=work)
    service = DataService(credentials, limits=ResourceLimits(**kwargs))
    # Two seed rows, unnamed (id is server-assigned): the first two inserted
    # get id 1 and id 2 respectively, exactly what every test below assumes.
    ControlAuthority(service).register_application("limit-app", entities={"items": [{}, {}]})
    return service, service.authenticate("limit-cred.limit-secret")


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


def test_r2_capability_artifact_matches_real_capabilities_response(service):
    """WP-5 final review finding: the artifact test above only ever checked
    `config/capabilities.json` for *internal* self-consistency (enabled/
    unavailable disjoint, valid enforcement vocabulary) -- it never compared
    the artifact against what `DataService.capabilities()` itself actually
    declares. That let the artifact go stale: `revision_preconditions`/
    `ordering`/`cursor_pagination`/`schema.create_index`/`schema.drop_index`
    all stayed listed `unavailable` well after CCR-13 made every one of them
    real, executable capabilities. This test compares every name the
    artifact mentions against a real, authenticated `capabilities()`
    response, so a future drift between this file and the actual
    declaration fails loudly instead of silently.
    """
    artifact = json.loads((Path(__file__).parents[1] / "config" / "capabilities.json").read_text())
    developer = service.authenticate("dev-a.dev-secret-a")
    response = service.capabilities(developer)
    capabilities = response["capabilities"]

    schema_ops = capabilities["schema_operations"]
    enabled_schema_ops = set(schema_ops.get("operations", []))
    unsupported_schema_ops = set(schema_ops.get("unsupported", []))

    def is_enabled(name: str) -> bool:
        if name in ("ordering", "cursor_pagination"):
            # Neither `order_by` nor cursor pagination is a capability name
            # of its own in the common contract -- both are query-shape
            # features gated by `structured_query` alone (service.py's own
            # capabilities() comment: "structured_query: enabled (order_by
            # / pagination が実行可能になったため)").
            return capabilities["structured_query"]["status"] == "enabled"
        if name.startswith("schema."):
            operation = name.split(".", 1)[1]
            if operation in enabled_schema_ops:
                return True
            if operation in unsupported_schema_ops:
                return False
            raise AssertionError(
                f"schema operation {operation!r} (from capabilities.json's {name!r}) is named in neither "
                "schema_operations.operations nor .unsupported"
            )
        entry = capabilities.get(name)
        assert entry is not None, f"capabilities.json names {name!r}, which is not a key in the real capabilities() response"
        return entry["status"] == "enabled"

    for name in artifact["enabled"]:
        assert is_enabled(name), f"config/capabilities.json declares {name!r} enabled, but capabilities() disagrees"
    for name in artifact["unavailable"]:
        assert not is_enabled(name), f"config/capabilities.json declares {name!r} unavailable, but capabilities() reports it enabled"


def test_r2_capability_artifact_names_every_real_capability(service):
    """R-9 (CCR-14 WP-5, design docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md
    §1): closes the write-forgot-to-update-artifact detection gap the
    forward test above cannot catch on its own -- that test only ever walks
    names the artifact ALREADY mentions, so a capability added to the real
    `capabilities()` response without a matching artifact update goes
    unnoticed forever (the same "book-keeping never gets forced to stay
    honest" shape design's own C-12 reverse check already closes for a
    different pair of documents). This is the reverse direction: every
    capability name the real response actually carries must be named in the
    artifact somewhere (`enabled` or `unavailable`) -- membership only, not
    which bucket, since `test_r2_capability_artifact_matches_real_
    capabilities_response` above already pins the correct bucket for every
    name that test walks.
    """
    artifact = json.loads((Path(__file__).parents[1] / "config" / "capabilities.json").read_text())
    declared = set(artifact["enabled"]) | set(artifact["unavailable"])
    developer = service.authenticate("dev-a.dev-secret-a")
    response = service.capabilities(developer)
    capabilities = response["capabilities"]

    schema_ops = capabilities["schema_operations"]
    real_schema_names = {f"schema.{op}" for op in schema_ops.get("operations", [])} | {f"schema.{op}" for op in schema_ops.get("unsupported", [])}
    real_names = {name for name in capabilities if name != "schema_operations"} | real_schema_names

    for name in sorted(real_names):
        assert name in declared, (
            f"capabilities() response names {name!r}, which config/capabilities.json does not mention in "
            "either 'enabled' or 'unavailable' -- the artifact was not updated alongside a new/changed "
            "capability (R-9's own reverse-lookup detection gap)"
        )


def test_capability_response_matches_common_capability_document_schema(service):
    contract = json.loads((Path(__file__).parents[2] / "spec" / "data-service-api.v1.json").read_text())
    schema = contract["schemas"]["CapabilityDocument"]
    runtime = service.authenticate("cred-a.secret-a")
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
    developer = service.authenticate("schema-dev.schema-dev-secret")
    service._clock = lambda: next(clock_values)
    with pytest.raises(FoundationError) as error:
        service.schema(developer, {"operation": "create_entity", "entity": "deadline_entity", "fields": ["value"]})
    assert error.value.code == "LIMIT_EXCEEDED"
    service._clock = time.monotonic
    with pytest.raises(FoundationError) as absent:
        service.query(context, "deadline_entity", select=["value"])
    assert absent.value.code == "NOT_FOUND"


def test_delete_rejects_truthy_non_boolean_destructive_before_confirmation(service):
    """Review blocker B-1 (data plane -- `bind_mutation`'s pre-existing
    `isinstance(bool)` check, structured.py:229, newly locked down by a
    real test): a truthy-but-non-boolean `destructive` (the string
    `"true"`) must be rejected as `VALIDATION_FAILED` -- never silently
    coerced by a loose `bool(...)` cast into a real destructive delete.
    The real, currently-valid confirmation phrase is supplied anyway (so
    this test proves the TYPE check denies it, not merely a missing/wrong
    confirmation), and the row is not deleted."""
    runtime = service.authenticate("cred-a.secret-a")
    before = service.query(runtime, "notes", select=["id"])
    where = [{"field": "id", "operator": "eq", "value": 1}]
    phrase = _delete_phrase("notes", where)
    with pytest.raises(FoundationError) as exc:
        service.mutate(runtime, "notes", [{"operation": "delete", "where": where, "destructive": "true", "confirmation": phrase}])
    assert exc.value.code == "VALIDATION_FAILED"
    assert service.query(runtime, "notes", select=["id"]) == before


def test_drop_entity_rejects_truthy_non_boolean_destructive_before_confirmation():
    """Review blocker B-1 (schema plane -- `bind_schema_operation`'s new
    `isinstance(bool)` check, symmetric with `bind_mutation`'s): same
    truthy-non-boolean rejection, for `drop_entity`."""
    cell = _cell()
    _create_entity(cell, "widgets")
    phrase = drop_entity_confirmation_phrase("widgets", cell.schema_revision)
    with pytest.raises(FoundationError) as exc:
        cell.apply_schema({"operation": "drop_entity", "entity": "widgets", "destructive": "true", "confirmation": phrase}, developer=True, limits=LIMITS)
    assert exc.value.code == "VALIDATION_FAILED"
    assert any(item["entity"] == "widgets" for item in cell.catalog())


def test_drop_index_rejects_truthy_non_boolean_destructive_before_confirmation():
    """Review blocker B-1 (schema plane, `drop_index` twin of the
    `drop_entity` test immediately above)."""
    cell = _cell()
    _create_entity(cell, "widgets")
    _add_field(cell, "widgets", "tag")
    _create_index(cell, "widgets", "by_tag", ["tag"], unique=True)
    phrase = drop_index_confirmation_phrase("widgets", "by_tag", cell.schema_revision)
    with pytest.raises(FoundationError) as exc:
        cell.apply_schema({"operation": "drop_index", "entity": "widgets", "index": "by_tag", "destructive": "true", "confirmation": phrase}, developer=True, limits=LIMITS)
    assert exc.value.code == "VALIDATION_FAILED"
    assert cell.catalog()[0]["unique_keys"] == [{"name": "by_tag", "fields": ["tag"]}]


def test_delete_phrase_invalidated_by_drop_recreate_of_the_same_entity_under_the_same_name():
    """Opus review minor m-2, monitor decision Q1-D10 (reviewer's own
    measured scenario): probe a `delete` phrase for `widgets` at its
    current schema_revision, `drop_entity` `widgets`, `create_entity`
    `widgets` again (same name -- contract `phrase_construction` rule (b):
    re-creation under the same name must invalidate any previously-valid
    phrase for that name). Before this fix, the where-digest-only delete
    phrase had no state fingerprint at all, so the OLD phrase, echoed
    against the freshly re-created entity's identical-looking delete
    request, would incorrectly still validate -- this asserts it is now
    denied instead."""
    cell = _cell()
    _create_entity(cell, "widgets")
    cell.transact("widgets", [{"operation": "insert", "values": {}}], LIMITS)
    where = [{"field": "id", "operator": "eq", "value": 1}]
    old_phrase = _delete_phrase("widgets", where, cell.schema_revision)

    cell.apply_schema(
        {"operation": "drop_entity", "entity": "widgets", "destructive": True, "confirmation": drop_entity_confirmation_phrase("widgets", cell.schema_revision)},
        developer=True, limits=LIMITS,
    )
    _create_entity(cell, "widgets")
    cell.transact("widgets", [{"operation": "insert", "values": {}}], LIMITS)  # the re-created entity's own fresh row (address restarts at 1)

    with pytest.raises(FoundationError) as exc:
        cell.transact("widgets", [{"operation": "delete", "where": where, "destructive": True, "confirmation": old_phrase}], LIMITS)
    assert exc.value.code == "DESTRUCTIVE_CONFIRMATION_REQUIRED"
    # the re-created entity's own fresh row survives the denied attempt.
    assert cell.query("widgets", select=["id"], where=[], page_size=10, limits=LIMITS).items == [{"id": 1}]


def test_mutation_values_over_100_fields_is_validation_failed_not_limit_exceeded(service):
    """Opus review minor m-3: a bidirectional test for the Q1-D8
    reclassification (structured.py:212) -- this was not actually covered
    by any existing test before this review round. A `Mutation.values`
    exceeding the contract's own fixed `maxProperties: 100` shape bound is
    `VALIDATION_FAILED` (400), never `LIMIT_EXCEEDED` (a deployment-tunable
    `limits.classes` resource this is not), with `details == {"field":
    "values"}`. This check runs before the per-key `known_fields`
    membership loop (structured.py), so the 101 field names here never
    need to correspond to any real declared field."""
    runtime = service.authenticate("cred-a.secret-a")
    too_many_values = {f"field_{i}": i for i in range(101)}
    with pytest.raises(FoundationError) as exc:
        service.mutate(runtime, "notes", [{"operation": "insert", "values": too_many_values}])
    assert exc.value.code == "VALIDATION_FAILED"
    assert exc.value.code != "LIMIT_EXCEEDED"
    assert exc.value.details == {"field": "values"}


def test_every_advertised_resource_limit_has_a_deterministic_boundary():
    service, context = _limited(batch_items=1)
    with pytest.raises(FoundationError) as error:
        service.mutate(context, "items", [{"operation": "insert", "values": {"id": 3}}, {"operation": "insert", "values": {"id": 4}}])
    assert error.value.code == "LIMIT_EXCEEDED"
    # Opus review M-1(b): a representative behavioral (runtime) assertion of
    # `limit_class` on a real response -- this one exercises `ResourceLimits.
    # check`'s own dynamic `kind`-as-limit_class call site (limits.py:35),
    # the one non-literal case `test_limit_class_vocabulary.py`'s static
    # scan allowlists by name.
    assert error.value.details["limit_class"] == "batch_items"

    service, context = _limited(result_items=1)
    with pytest.raises(FoundationError) as error:
        where = [{"field": "id", "operator": "in", "value": [1, 2]}]
        service.mutate(context, "items", [{"operation": "delete", "where": where, "destructive": True, "confirmation": _delete_phrase("items", where)}])
    assert error.value.code == "LIMIT_EXCEEDED"
    assert error.value.details["limit_class"] == "result_items"

    service, context = _limited(query_complexity=1)
    with pytest.raises(FoundationError) as error:
        service.query(context, "items", select=["id"], where=[{"field": "id", "operator": "eq", "value": 1}])
    assert error.value.code == "LIMIT_EXCEEDED"
    assert error.value.details["limit_class"] == "query_complexity"

    service, context = _limited(operation_depth=2)
    with pytest.raises(FoundationError) as error:
        service.query(context, "items", select=["id"], where=[{"field": "id", "operator": "eq", "value": {"nested": {"too_deep": True}}}])
    assert error.value.code == "LIMIT_EXCEEDED"

    service, context = _limited(schema_objects=1)
    ControlAuthority(service).issue_credential("limit-dev", "limit-app", "developer", "limit-dev-secret")
    dev_context = service.authenticate("limit-dev.limit-dev-secret")
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


def test_upsert_is_capability_unsupported_without_a_declared_unique_key_and_rejects_the_whole_batch(service):
    # Contract 1.1.0 (CCR-13, R-5) ties upsert's meaning to a declared
    # domain uniqueness key; `notes` here declares none, so upsert must be
    # refused as CAPABILITY_UNSUPPORTED -- and, independently, WP-2 review
    # blocker B-1's provisional gate in `DataService.mutate()` refuses
    # *every* upsert unconditionally until WP-5 (see the dedicated gate
    # tests further below), so this same assertion is now doubly true. The
    # upsert is deliberately the *second* operation: the preceding insert
    # must roll back with it (failure-before-execution, no partial commit).
    runtime = service.authenticate("cred-a.secret-a")
    with pytest.raises(FoundationError) as exc:
        service.mutate(runtime, "notes", [
            {"operation": "insert", "values": {"body": "before-upsert"}},
            {"operation": "upsert", "values": {"body": "x"}},
        ])
    assert exc.value.code == "CAPABILITY_UNSUPPORTED"
    remaining = service.query(runtime, "notes", select=["id"], where=[{"field": "body", "operator": "eq", "value": "before-upsert"}])
    assert remaining == [], "the batch's preceding insert must not survive the rejected upsert"


def test_reserved_identifier_names_are_rejected_for_entities_and_fields(service):
    developer = service.authenticate("dev-a.dev-secret-a")
    with pytest.raises(FoundationError) as exc:
        service.schema(developer, {"operation": "create_entity", "entity": "_r2db_evil"})
    assert exc.value.code == "IDENTIFIER_INVALID"
    with pytest.raises(FoundationError) as exc:
        service.schema(developer, {"operation": "create_entity", "entity": "widgets_a", "fields": ["id"]})
    assert exc.value.code == "IDENTIFIER_INVALID"
    with pytest.raises(FoundationError) as exc:
        service.schema(developer, {"operation": "create_entity", "entity": "widgets_b", "fields": ["_r2db_x"]})
    assert exc.value.code == "IDENTIFIER_INVALID"
    service.schema(developer, {"operation": "create_entity", "entity": "widgets_c"})
    with pytest.raises(FoundationError) as exc:
        service.schema(developer, {"operation": "add_field", "entity": "widgets_c", "field": "id"})
    assert exc.value.code == "IDENTIFIER_INVALID"
    with pytest.raises(FoundationError) as exc:
        service.schema(developer, {"operation": "add_field", "entity": "widgets_c", "field": "_r2db_y"})
    assert exc.value.code == "IDENTIFIER_INVALID"


def test_audit_events_entity_name_is_reserved_by_exact_match_only(service):
    """WP-2(b) review B-2 (major, supervisor ruling 2026-09-03): contract
    1.4.0 `structured_operations.reserved_entity_names_note` (unconditional
    item 6) requires `audit_events` to be refused as an entity name. EXACT
    match only -- `audit_events_archive` (a superstring, not the reserved
    name itself) must still be accepted, proving this is not accidentally a
    prefix rule."""
    developer = service.authenticate("dev-a.dev-secret-a")
    with pytest.raises(FoundationError) as exc:
        service.schema(developer, {"operation": "create_entity", "entity": "audit_events"})
    assert exc.value.code == "IDENTIFIER_INVALID"
    # Accepted: not the reserved name itself, only a superstring of it.
    service.schema(developer, {"operation": "create_entity", "entity": "audit_events_archive"})


def test_audit_events_is_reserved_at_every_entity_identifier_position(service):
    """WP-2(b) fix round 2 (coordinator item C): the reservation must fire
    at EVERY entity-identifier position -- add_field/drop_entity/
    create_index/drop_index/query/mutate -- not only at create_entity,
    matching MitateDB's own `cell._identifier()` "reject at every
    identifier position" line. Each of these previously fell through to a
    generic NOT_FOUND (no real entity of that name can ever exist) instead
    of the reserved-name refusal itself."""
    developer = service.authenticate("dev-a.dev-secret-a")
    runtime = service.authenticate("cred-a.secret-a")

    with pytest.raises(FoundationError) as exc:
        service.schema(developer, {"operation": "add_field", "entity": "audit_events", "field": "x"})
    assert exc.value.code == "IDENTIFIER_INVALID"

    with pytest.raises(FoundationError) as exc:
        service.schema(developer, {"operation": "drop_entity", "entity": "audit_events", "destructive": True, "confirmation": "whatever"})
    assert exc.value.code == "IDENTIFIER_INVALID"

    with pytest.raises(FoundationError) as exc:
        service.schema(developer, {"operation": "create_index", "entity": "audit_events", "index": "ix1", "fields": ["x"]})
    assert exc.value.code == "IDENTIFIER_INVALID"

    with pytest.raises(FoundationError) as exc:
        service.schema(developer, {"operation": "drop_index", "entity": "audit_events", "index": "ix1"})
    assert exc.value.code == "IDENTIFIER_INVALID"

    with pytest.raises(FoundationError) as exc:
        service.query(runtime, "audit_events", select=["id"])
    assert exc.value.code == "IDENTIFIER_INVALID"

    with pytest.raises(FoundationError) as exc:
        service.mutate(runtime, "audit_events", [{"operation": "insert", "values": {"body": "x"}}])
    assert exc.value.code == "IDENTIFIER_INVALID"


# ==========================================================================
# CCR-13 (docs/design/R2DB_CCR13_STORAGE_V1.md, work package WP-2, plus its
# review corrigenda in §9): typed columns, reserved names, indexes/
# uniqueness, upsert re-enablement, expected_revision, order_by, and cursor
# pagination on `ApplicationCell`.
#
# WP-2 review blocker B-1 added a provisional gate to `DataService` (§3,
# "WP-2〜WP-5 の乖離封鎖") that refuses `expected_revision`/`upsert` on
# `mutate()`, `create_index`/`drop_index`/`field_type` on `schema()`, and
# narrows `catalog()`'s published shape -- all until `capabilities()` is
# updated in the same commit as WP-5. Every test below that exercises one
# of those (now-gated) features therefore constructs an `ApplicationCell`
# directly, exactly like `test_postgres.py` does for `PostgresCell`, so it
# observes the underlying engine behaviour ungated. The gate itself is
# tested separately, through `service`, in the dedicated section at the end
# of this file.
# ==========================================================================

LIMITS = ResourceLimits()


def _cell(entities: dict | None = None) -> ApplicationCell:
    return ApplicationCell("engine-app", dict(entities) if entities else {})


def _create_entity(cell: ApplicationCell, entity: str, fields: tuple = ()) -> None:
    cell.apply_schema({"operation": "create_entity", "entity": entity, "fields": list(fields)}, developer=True, limits=LIMITS)


def _add_field(cell: ApplicationCell, entity: str, field_name: str, field_type: str | None = None) -> None:
    op = {"operation": "add_field", "entity": entity, "field": field_name}
    if field_type is not None:
        op["field_type"] = field_type
    cell.apply_schema(op, developer=True, limits=LIMITS)


def _create_index(cell: ApplicationCell, entity: str, index: str, fields: list, *, unique: bool = False) -> None:
    cell.apply_schema({"operation": "create_index", "entity": entity, "index": index, "fields": list(fields), "unique": unique}, developer=True, limits=LIMITS)


def test_application_cell_catalog_returns_the_full_entity_descriptor_shape():
    """The full CCR-13 `EntityDescriptor` shape (docs/design/
    R2DB_CCR13_STORAGE_V1.md §2/R-1): every entity is `mutable`, addressed
    by server-assigned `id`, never reuses an address, and (once declared)
    surfaces its unique keys. `DataService.catalog()`'s own narrower,
    gated published shape is covered separately by
    `test_catalog_returns_shaped_document_scoped_to_application` above."""
    cell = _cell({"notes": [{"body": "a"}]})
    # Phase 6 WP-2 (design D-3(iii)): `field_types` added -- `body` was
    # created with no declared type, so it reports `json` (decision (ii)'s
    # default); `id` is always `integer`. Contract 1.7.0 (D-2 (1), WP-2a):
    # `field_constraints` added too -- total, `nullable: true` and no
    # `enum` for both fields here (nothing was ever declared).
    assert cell.catalog() == [
        {
            "entity": "notes",
            "fields": ["body", "id"],
            "field_types": {"body": "json", "id": "integer"},
            "field_constraints": {"body": {"nullable": True}, "id": {"nullable": True}},
            "mutation_class": "mutable",
            "address_fields": ["id"],
            "address_reuse": "never",
            "unique_keys": [],
        }
    ]
    _add_field(cell, "notes", "email")
    _create_index(cell, "notes", "by_email", ["email"], unique=True)
    entity = cell.catalog()[0]
    assert entity["unique_keys"] == [{"name": "by_email", "fields": ["email"]}]


def test_field_type_is_only_accepted_by_add_field():
    cell = _cell()
    with pytest.raises(FoundationError) as exc:
        cell.apply_schema({"operation": "create_entity", "entity": "typed_reject", "field_type": "integer"}, developer=True, limits=LIMITS)
    assert exc.value.code == "VALIDATION_FAILED"
    _create_entity(cell, "typed_reject")
    with pytest.raises(FoundationError) as exc:
        _add_field(cell, "typed_reject", "n", "not-a-real-type")
    assert exc.value.code == "VALIDATION_FAILED"


# ===========================================================================
# Phase 6 WP-2 (design docs/design/PHASE6_CONTRACT_160_CLIENT_DISCOVERY_
# V1.md D-3): `create_entity`'s optional `field_types` request key, the
# catalog's own `field_types` reporting (both already exercised incidentally
# by the tests above, via the shared `service`/`_cell` fixtures' own catalog
# assertions) -- this section is the dedicated, exhaustive coverage: the 3
# invalid shapes, the declaration round-trip, the `json` default + its NUL
# regression guard, and the `fields`-only (1.5.0) request's continued
# validity.
# ===========================================================================


def test_create_entity_field_types_names_a_field_not_present_in_fields_is_validation_failed():
    """Design D-3(iv) invalid case (a): a `field_types` key naming a field
    `fields` never declared."""
    cell = _cell()
    with pytest.raises(FoundationError) as exc:
        cell.apply_schema(
            {"operation": "create_entity", "entity": "bad_a", "fields": ["a"], "field_types": {"b": "string"}},
            developer=True, limits=LIMITS,
        )
    assert exc.value.code == "VALIDATION_FAILED"
    # No side effect: the entity must not have been partially created.
    assert cell.catalog() == []


@pytest.mark.parametrize("bad_value", ["unknown", ["string"], {"x": 1}, 1, None, True])
def test_create_entity_field_types_value_outside_the_seven_word_vocabulary_is_validation_failed(bad_value):
    """Design D-3(iv) invalid case (b): a `field_types` value the contract's
    7-word enum does not carry -- both a wrong-but-string word (`"unknown"`)
    and, coordinator F2 (2026-09-04 review): a genuinely non-string value
    (list/dict/int/None/bool). Before the fix, a non-string value made
    `if declared_type not in FIELD_TYPES:` raise `TypeError: unhashable
    type` for the unhashable cases (`list`/`dict`) -- an uncaught exception
    `http.py`'s `_endpoint` maps to a bare 503, not this method's own
    `VALIDATION_FAILED` (design D-3(iv)(b) requires `VALIDATION_FAILED`
    for every non-conforming value, not merely the hashable ones)."""
    cell = _cell()
    with pytest.raises(FoundationError) as exc:
        cell.apply_schema(
            {"operation": "create_entity", "entity": "bad_b", "fields": ["a"], "field_types": {"a": bad_value}},
            developer=True, limits=LIMITS,
        )
    assert exc.value.code == "VALIDATION_FAILED"
    assert cell.catalog() == []


@pytest.mark.parametrize("bad_value", ["unknown", ["string"], {"x": 1}, 1, None, True])
def test_add_field_field_type_value_outside_the_seven_word_vocabulary_is_validation_failed(bad_value):
    """Coordinator F2: the identical isinstance-first guard on `add_field`'s
    scalar `field_type` (`structured.py:702`'s sibling to the create_entity
    fix above) -- a pre-existing (not a WP-2 regression) hole the review
    named as closeable in the same fix."""
    cell = _cell()
    _create_entity(cell, "bad_scalar")
    with pytest.raises(FoundationError) as exc:
        cell.apply_schema(
            {"operation": "add_field", "entity": "bad_scalar", "field": "n", "field_type": bad_value},
            developer=True, limits=LIMITS,
        )
    assert exc.value.code == "VALIDATION_FAILED"


def test_create_entity_field_types_without_fields_is_validation_failed():
    """Design D-3(iv) invalid case (c): `field_types` sent without `fields`
    at all -- never silently ignored (the exact MitateDB-observed defect
    this rule closes, design section 1.5 item 1)."""
    cell = _cell()
    with pytest.raises(FoundationError) as exc:
        cell.apply_schema(
            {"operation": "create_entity", "entity": "bad_c", "field_types": {"a": "string"}},
            developer=True, limits=LIMITS,
        )
    assert exc.value.code == "VALIDATION_FAILED"
    assert cell.catalog() == []


def test_create_entity_field_types_declaration_round_trips_through_the_catalog():
    """Design D-3(iv): a type declared via `create_entity`'s `field_types`
    (or `add_field`'s scalar `field_type`) is reported back unchanged by the
    catalog -- for every one of the 6 non-`json` words at once (a field
    named `untyped` is deliberately left out of `field_types`, to also
    exercise decision (ii)'s default in the same call as the round-trip)."""
    cell = _cell()
    declared = {"s": "string", "i": "integer", "n": "number", "b": "boolean", "o": "object", "a": "array"}
    cell.apply_schema(
        {"operation": "create_entity", "entity": "typed", "fields": [*declared, "untyped"], "field_types": declared},
        developer=True, limits=LIMITS,
    )
    cell.apply_schema({"operation": "add_field", "entity": "typed", "field": "explicit_json", "field_type": "json"}, developer=True, limits=LIMITS)
    field_types = cell.catalog()[0]["field_types"]
    assert field_types == {**declared, "untyped": "json", "explicit_json": "json", "id": "integer"}


def test_add_field_declared_type_round_trips_through_the_catalog_for_every_non_json_word():
    """Design D-3(iv): `add_field`'s own scalar `field_type` declaration
    round-trips through the catalog unchanged -- for each of the 6 non-
    `json` words individually (distinct from the `create_entity`-time
    `field_types` round-trip test above, which never exercises `add_field`
    for anything but the `json` word itself)."""
    cell = _cell()
    _create_entity(cell, "af_typed")
    for name, field_type in (("s", "string"), ("i", "integer"), ("n", "number"), ("b", "boolean"), ("o", "object"), ("a", "array")):
        _add_field(cell, "af_typed", name, field_type)
        reported = cell.catalog()[0]["field_types"][name]
        assert reported == field_type, f"add_field declared {field_type!r} for {name!r} but catalog reports {reported!r}"


def test_create_entity_fields_only_request_stays_valid_and_creates_json_fields():
    """Design D-3(iv): `field_types` is never required -- a `fields`-only
    `create_entity` (the 1.5.0 request shape) stays valid unchanged, and
    every field it creates is `json` (decision (ii))."""
    cell = _cell()
    cell.apply_schema({"operation": "create_entity", "entity": "legacy_shape", "fields": ["x", "y"]}, developer=True, limits=LIMITS)
    entity = cell.catalog()[0]
    assert entity["fields"] == ["id", "x", "y"]
    assert entity["field_types"] == {"id": "integer", "x": "json", "y": "json"}


def test_declared_json_field_accepts_and_round_trips_every_json_shape_and_rejects_nul():
    """Design D-3(ii)/G11: a field explicitly declared `json` behaves
    identically to an untyped field -- accepts every JSON shape, and (the
    NUL-regression this decision's own docstring names) still refuses a
    NUL byte, exactly like an untyped field does. Value round-trip is
    exercised at the mutation layer (`bind_mutation`/`_check_type`), not
    the catalog -- this cell has no storage backend, so this test checks
    what CAN be checked without one: acceptance/rejection at bind time.
    """
    from r2db_api.structured import _check_type

    cell = _cell()
    cell.apply_schema(
        {"operation": "create_entity", "entity": "jsonized", "fields": ["j"], "field_types": {"j": "json"}},
        developer=True, limits=LIMITS,
    )
    declared_type = cell.schema["jsonized"]["j"]
    assert declared_type is None  # G11: explicit "json" collapses to the internal untyped representation
    # Every JSON shape is accepted (no exception raised).
    for value in (["a", "b"], {"k": "v"}, "text", 3.14, True, None):
        _check_type(value, declared_type, "j")
    # A NUL byte is refused for the SAME reason an untyped field refuses one
    # (design's own regression concern: an explicit "json" declaration must
    # not accidentally widen past what untyped already permitted).
    with pytest.raises(FoundationError) as exc:
        _check_type("bad\x00value", declared_type, "j")
    assert exc.value.code == "VALIDATION_FAILED"
    with pytest.raises(FoundationError) as exc:
        _check_type({"k": "bad\x00value"}, declared_type, "j")
    assert exc.value.code == "VALIDATION_FAILED"


def test_typed_columns_validate_values_on_write_and_predicate():
    cell = _cell()
    _create_entity(cell, "typed")
    for name, field_type in (("i", "integer"), ("n", "number"), ("b", "boolean"), ("s", "string"), ("o", "object"), ("a", "array")):
        _add_field(cell, "typed", name, field_type)
    good = {"i": 1, "n": 1.5, "b": True, "s": "x", "o": {"k": 1}, "a": [1, 2]}
    cell.transact("typed", [{"operation": "insert", "values": good}], LIMITS)
    assert cell.query("typed", select=["i", "n", "b", "s", "o", "a"], where=[], page_size=10, limits=LIMITS).items == [good]
    bad_cases = {"i": "not-an-int", "n": "not-a-number", "b": "not-a-bool", "s": 5, "o": [1], "a": {"k": 1}}
    for field_name, bad_value in bad_cases.items():
        with pytest.raises(FoundationError) as exc:
            cell.transact("typed", [{"operation": "insert", "values": {field_name: bad_value}}], LIMITS)
        assert exc.value.code == "VALIDATION_FAILED"
    with pytest.raises(FoundationError) as exc:
        cell.query("typed", select=["i"], where=[Predicate("i", "eq", "nope")], page_size=10, limits=LIMITS)
    assert exc.value.code == "VALIDATION_FAILED"


def test_typed_integer_and_number_columns_reject_boolean_values():
    """`isinstance(True, int)` is `True` in Python -- bool must be excluded
    from integer/number explicitly, not accepted as a numeric 0/1."""
    cell = _cell()
    _create_entity(cell, "numeric")
    _add_field(cell, "numeric", "i", "integer")
    _add_field(cell, "numeric", "n", "number")
    with pytest.raises(FoundationError) as exc:
        cell.transact("numeric", [{"operation": "insert", "values": {"i": True}}], LIMITS)
    assert exc.value.code == "VALIDATION_FAILED"
    with pytest.raises(FoundationError) as exc:
        cell.transact("numeric", [{"operation": "insert", "values": {"n": False}}], LIMITS)
    assert exc.value.code == "VALIDATION_FAILED"


def test_null_is_allowed_for_any_declared_type():
    cell = _cell()
    _create_entity(cell, "nullable")
    _add_field(cell, "nullable", "i", "integer")
    cell.transact("nullable", [{"operation": "insert", "values": {"i": None}}], LIMITS)
    assert cell.query("nullable", select=["i"], where=[], page_size=10, limits=LIMITS).items == [{"i": None}]


def test_in_operator_type_checks_each_element():
    cell = _cell()
    _create_entity(cell, "ints")
    _add_field(cell, "ints", "i", "integer")
    cell.transact("ints", [{"operation": "insert", "values": {"i": 1}}], LIMITS)
    with pytest.raises(FoundationError) as exc:
        cell.query("ints", select=["i"], where=[Predicate("i", "in", [1, "two"])], page_size=10, limits=LIMITS)
    assert exc.value.code == "VALIDATION_FAILED"


def test_create_index_and_unique_conflict_on_insert_and_update():
    cell = _cell()
    _create_entity(cell, "accounts")
    _add_field(cell, "accounts", "email")
    revision = cell.apply_schema({"operation": "create_index", "entity": "accounts", "index": "by_email", "fields": ["email"], "unique": True}, developer=True, limits=LIMITS).revision
    assert isinstance(revision, int)
    entity = cell.catalog()[0]
    assert entity["unique_keys"] == [{"name": "by_email", "fields": ["email"]}]

    cell.transact("accounts", [{"operation": "insert", "values": {"email": "a@example.invalid"}}], LIMITS)
    with pytest.raises(FoundationError) as exc:
        cell.transact("accounts", [{"operation": "insert", "values": {"email": "a@example.invalid"}}], LIMITS)
    assert exc.value.code == "CONFLICT"
    assert exc.value.details == {"index": "by_email"}

    cell.transact("accounts", [{"operation": "insert", "values": {"email": "b@example.invalid"}}], LIMITS)
    with pytest.raises(FoundationError) as exc:
        cell.transact("accounts", [{"operation": "update", "where": [{"field": "email", "operator": "eq", "value": "b@example.invalid"}], "values": {"email": "a@example.invalid"}}], LIMITS)
    assert exc.value.code == "CONFLICT"

    with pytest.raises(FoundationError) as exc:
        cell.apply_schema({"operation": "create_index", "entity": "accounts", "index": "by_email", "fields": ["email"]}, developer=True, limits=LIMITS)
    assert exc.value.code == "CONFLICT"
    with pytest.raises(FoundationError) as exc:
        cell.apply_schema({"operation": "create_index", "entity": "accounts", "index": "by_ghost", "fields": ["ghost"]}, developer=True, limits=LIMITS)
    assert exc.value.code == "NOT_FOUND"


def test_unique_index_with_null_key_field_never_conflicts():
    """WP-2 review M-13: the SQL unique-index convention (NULL is distinct
    from NULL) is a fixed, dedicated test, not just an assertion folded
    into another test's setup."""
    cell = _cell()
    _create_entity(cell, "accounts")
    _add_field(cell, "accounts", "email")
    _create_index(cell, "accounts", "by_email", ["email"], unique=True)
    cell.transact("accounts", [{"operation": "insert", "values": {}}, {"operation": "insert", "values": {}}], LIMITS)
    rows = cell.query("accounts", select=["id", "email"], where=[], page_size=10, limits=LIMITS).items
    assert [row["email"] for row in rows] == [None, None]


def test_create_index_rejects_reserved_prefix_double_underscore_oversized_name_id_field_and_bad_field_counts():
    cell = _cell()
    _create_entity(cell, "shapes")
    _add_field(cell, "shapes", "tag")
    with pytest.raises(FoundationError) as exc:
        cell.apply_schema({"operation": "create_index", "entity": "shapes", "index": "_r2db_evil", "fields": ["tag"]}, developer=True, limits=LIMITS)
    assert exc.value.code == "IDENTIFIER_INVALID"
    with pytest.raises(FoundationError) as exc:
        cell.apply_schema({"operation": "create_index", "entity": "shapes", "index": "bad__name", "fields": ["tag"]}, developer=True, limits=LIMITS)
    assert exc.value.code == "VALIDATION_FAILED"
    with pytest.raises(FoundationError) as exc:
        cell.apply_schema({"operation": "create_index", "entity": "shapes", "index": "n" * 60, "fields": ["tag"]}, developer=True, limits=LIMITS)
    assert exc.value.code == "VALIDATION_FAILED"
    with pytest.raises(FoundationError) as exc:
        cell.apply_schema({"operation": "create_index", "entity": "shapes", "index": "empty_fields", "fields": []}, developer=True, limits=LIMITS)
    assert exc.value.code == "VALIDATION_FAILED"
    with pytest.raises(FoundationError) as exc:
        cell.apply_schema({"operation": "create_index", "entity": "shapes", "index": "too_many", "fields": ["tag"] * 17}, developer=True, limits=LIMITS)
    assert exc.value.code == "VALIDATION_FAILED"
    with pytest.raises(FoundationError) as exc:
        # WP-2 review M-5: `id` is an address, not a domain uniqueness
        # declaration.
        cell.apply_schema({"operation": "create_index", "entity": "shapes", "index": "by_id", "fields": ["id"]}, developer=True, limits=LIMITS)
    assert exc.value.code == "VALIDATION_FAILED"


def test_create_index_unique_rejects_when_existing_data_has_duplicates():
    cell = _cell()
    _create_entity(cell, "dupes")
    _add_field(cell, "dupes", "tag")
    cell.transact("dupes", [{"operation": "insert", "values": {"tag": "x"}}], LIMITS)
    cell.transact("dupes", [{"operation": "insert", "values": {"tag": "x"}}], LIMITS)
    with pytest.raises(FoundationError) as exc:
        cell.apply_schema({"operation": "create_index", "entity": "dupes", "index": "by_tag", "fields": ["tag"], "unique": True}, developer=True, limits=LIMITS)
    assert exc.value.code == "CONFLICT"
    assert exc.value.status == 409  # WP-2 review M-1: unified with every other CONFLICT


def test_index_and_unique_keys_are_rejected_outside_create_index():
    """WP-2 review M-3: `index`/`unique` are meaningful only to
    `create_index` (`drop_index` additionally accepts `index` as the name
    to drop, but never `unique`) -- the same "don't silently tolerate an
    unused key" principle `field_type` already gets."""
    cell = _cell()
    _create_entity(cell, "widgets")
    with pytest.raises(FoundationError) as exc:
        cell.apply_schema({"operation": "add_field", "entity": "widgets", "field": "tag", "unique": True}, developer=True, limits=LIMITS)
    assert exc.value.code == "VALIDATION_FAILED"
    with pytest.raises(FoundationError) as exc:
        cell.apply_schema({"operation": "add_field", "entity": "widgets", "field": "tag", "index": "by_tag"}, developer=True, limits=LIMITS)
    assert exc.value.code == "VALIDATION_FAILED"
    with pytest.raises(FoundationError) as exc:
        cell.apply_schema({"operation": "drop_index", "entity": "widgets", "index": "by_tag", "unique": True}, developer=True, limits=LIMITS)
    assert exc.value.code == "VALIDATION_FAILED"


def test_schema_operation_revision_key_is_capability_unsupported():
    """WP-2 review minor (e): `revision` was previously an accepted-but-
    unused key -- silently tolerating it is exactly the gap `field_type`'s
    own precedent closes."""
    cell = _cell()
    with pytest.raises(FoundationError) as exc:
        cell.apply_schema({"operation": "create_entity", "entity": "widgets", "revision": "1"}, developer=True, limits=LIMITS)
    assert exc.value.code == "CAPABILITY_UNSUPPORTED"


def test_drop_index_requires_destructive_confirmation():
    cell = _cell()
    _create_entity(cell, "idx_target")
    _add_field(cell, "idx_target", "tag")
    _create_index(cell, "idx_target", "by_tag", ["tag"], unique=True)
    with pytest.raises(FoundationError) as exc:
        cell.apply_schema({"operation": "drop_index", "entity": "idx_target", "index": "by_tag"}, developer=True, limits=LIMITS)
    assert exc.value.code == "DESTRUCTIVE_CONFIRMATION_REQUIRED"
    phrase = exc.value.details["required_confirmation"]
    assert phrase == drop_index_confirmation_phrase("idx_target", "by_tag", cell.schema_revision)
    cell.apply_schema({"operation": "drop_index", "entity": "idx_target", "index": "by_tag", "destructive": True, "confirmation": phrase}, developer=True, limits=LIMITS)
    assert cell.catalog()[0]["unique_keys"] == []
    with pytest.raises(FoundationError) as exc:
        cell.apply_schema({"operation": "drop_index", "entity": "idx_target", "index": "by_tag", "destructive": True, "confirmation": phrase}, developer=True, limits=LIMITS)
    assert exc.value.code == "NOT_FOUND"


def _notes_cell_with_two_unique_keys() -> ApplicationCell:
    """Section 0.5 Q-1, adjudicated 案B (2026-08-28, contract addendum to
    1.1.0): `notes` declares two uniqueness keys (`by_body` on `body`,
    `by_email` on `email`), so `upsert` on it must name the deciding key
    via `unique_key`."""
    cell = _cell({"notes": [{"body": "a"}]})
    _add_field(cell, "notes", "email")
    _create_index(cell, "notes", "by_body", ["body"], unique=True)
    _create_index(cell, "notes", "by_email", ["email"], unique=True)
    return cell


def test_upsert_on_multi_key_entity_without_unique_key_is_validation_failed():
    cell = _notes_cell_with_two_unique_keys()
    with pytest.raises(FoundationError) as exc:
        cell.transact("notes", [{"operation": "upsert", "values": {"body": "z", "email": "z@example.invalid"}}], LIMITS)
    assert exc.value.code == "VALIDATION_FAILED"


def test_upsert_on_multi_key_entity_with_unknown_unique_key_name_is_not_found():
    cell = _notes_cell_with_two_unique_keys()
    with pytest.raises(FoundationError) as exc:
        cell.transact("notes", [{"operation": "upsert", "unique_key": "no_such_key", "values": {"body": "z", "email": "z@example.invalid"}}], LIMITS)
    assert exc.value.code == "NOT_FOUND"


def test_upsert_on_multi_key_entity_resolves_using_the_named_key_only():
    """A match on the *other* declared key must not resolve the upsert to
    an update -- only the explicitly named key decides existence. `body` is
    also uniquely keyed here, so the new row deliberately uses a distinct
    body value -- this test's point is key *selection*, not a second,
    unrelated uniqueness conflict on `by_body`."""
    cell = _notes_cell_with_two_unique_keys()
    # Seeded row already has body "a" (fixture) and no email. Upserting by
    # `by_email` with a fresh email must insert a new row (matching on
    # `by_body` is not even considered), not update the seeded row.
    cell.transact("notes", [{"operation": "upsert", "unique_key": "by_email", "values": {"body": "new-body", "email": "new@example.invalid"}}], LIMITS)
    rows = cell.query("notes", select=["id", "body", "email"], where=[], page_size=10, limits=LIMITS).items
    assert len(rows) == 2
    bodies_by_email = {row["email"]: row["body"] for row in rows}
    assert bodies_by_email == {None: "a", "new@example.invalid": "new-body"}

    # Now upsert by `by_email` again on the same email: this must update
    # the row just inserted, not the original seeded row.
    cell.transact("notes", [{"operation": "upsert", "unique_key": "by_email", "values": {"body": "changed", "email": "new@example.invalid"}}], LIMITS)
    rows = cell.query("notes", select=["body", "email"], where=[], page_size=10, limits=LIMITS).items
    bodies_by_email = {row["email"]: row["body"] for row in rows}
    assert bodies_by_email == {None: "a", "new@example.invalid": "changed"}


def test_upsert_conflicts_on_a_declared_key_other_than_the_selected_one():
    """WP-2 review M-13: selecting a key with `unique_key` only decides
    *existence* -- every declared unique key is still enforced on write,
    including ones the selection did not name. `details` carries only the
    index name, never the colliding value (`errors.disclosure`)."""
    cell = _notes_cell_with_two_unique_keys()
    cell.transact("notes", [{"operation": "upsert", "unique_key": "by_email", "values": {"body": "unique-1", "email": "one@example.invalid"}}], LIMITS)
    with pytest.raises(FoundationError) as exc:
        cell.transact("notes", [{"operation": "upsert", "unique_key": "by_email", "values": {"body": "unique-1", "email": "two@example.invalid"}}], LIMITS)
    assert exc.value.code == "CONFLICT"
    assert exc.value.details == {"index": "by_body"}


def test_upsert_on_single_key_entity_accepts_explicit_matching_unique_key():
    cell = _cell({"notes": [{"body": "a"}]})
    _create_index(cell, "notes", "by_body", ["body"], unique=True)
    outcome = cell.transact("notes", [{"operation": "upsert", "unique_key": "by_body", "values": {"body": "a"}}], LIMITS)
    assert outcome.affected == 1  # resolves to updating the seeded body="a" row
    assert cell.query("notes", select=["id"], where=[], page_size=10, limits=LIMITS).items == [{"id": 1}]


def test_upsert_on_single_key_entity_with_wrong_unique_key_name_is_not_found():
    cell = _cell({"notes": [{"body": "a"}]})
    _create_index(cell, "notes", "by_body", ["body"], unique=True)
    with pytest.raises(FoundationError) as exc:
        cell.transact("notes", [{"operation": "upsert", "unique_key": "not_by_body", "values": {"body": "a"}}], LIMITS)
    assert exc.value.code == "NOT_FOUND"


def test_unique_key_is_rejected_on_insert_update_and_delete():
    cell = _cell({"notes": [{"body": "a"}]})
    with pytest.raises(FoundationError) as exc:
        cell.transact("notes", [{"operation": "insert", "values": {"body": "z"}, "unique_key": "by_body"}], LIMITS)
    assert exc.value.code == "VALIDATION_FAILED"
    with pytest.raises(FoundationError) as exc:
        cell.transact("notes", [{"operation": "update", "where": [{"field": "id", "operator": "eq", "value": 1}], "values": {"body": "z"}, "unique_key": "by_body"}], LIMITS)
    assert exc.value.code == "VALIDATION_FAILED"
    with pytest.raises(FoundationError) as exc:
        where = [{"field": "id", "operator": "eq", "value": 1}]
        cell.transact("notes", [{"operation": "delete", "where": where, "unique_key": "by_body", "destructive": True, "confirmation": _delete_phrase("notes", where, cell.schema_revision)}], LIMITS)
    assert exc.value.code == "VALIDATION_FAILED"


def test_composite_unique_key_enforces_uniqueness_and_supports_upsert():
    """WP-2 review M-13: a multi-field declared uniqueness key."""
    cell = _cell()
    _create_entity(cell, "memberships")
    _add_field(cell, "memberships", "org")
    _add_field(cell, "memberships", "user")
    _add_field(cell, "memberships", "role")
    _create_index(cell, "memberships", "by_org_user", ["org", "user"], unique=True)
    cell.transact("memberships", [{"operation": "insert", "values": {"org": "acme", "user": "ann", "role": "member"}}], LIMITS)
    with pytest.raises(FoundationError) as exc:
        cell.transact("memberships", [{"operation": "insert", "values": {"org": "acme", "user": "ann", "role": "admin"}}], LIMITS)
    assert exc.value.code == "CONFLICT"
    # A different user in the same org does not collide -- it is the pair
    # that is unique, not either field alone.
    cell.transact("memberships", [{"operation": "insert", "values": {"org": "acme", "user": "bob", "role": "member"}}], LIMITS)

    outcome = cell.transact("memberships", [{"operation": "upsert", "values": {"org": "acme", "user": "ann", "role": "owner"}}], LIMITS)
    assert outcome.affected == 1
    assert outcome.assigned_addresses == []  # resolved to update, not insert
    rows = cell.query("memberships", select=["org", "user", "role"], where=[Predicate("user", "eq", "ann")], page_size=10, limits=LIMITS).items
    assert rows == [{"org": "acme", "user": "ann", "role": "owner"}]


def test_upsert_with_one_declared_key_resolves_to_insert_then_update_with_assigned_addresses():
    cell = _cell()
    _create_entity(cell, "people")
    _add_field(cell, "people", "email")
    _add_field(cell, "people", "name")
    _create_index(cell, "people", "by_email", ["email"], unique=True)

    outcome = cell.transact("people", [{"operation": "upsert", "values": {"email": "a@example.invalid", "name": "Ann"}}], LIMITS)
    assert outcome.affected == 1
    assert outcome.assigned_addresses == [{"address": {"id": 1}}]

    outcome2 = cell.transact("people", [{"operation": "upsert", "values": {"email": "a@example.invalid", "name": "Ann2"}}], LIMITS)
    assert outcome2.affected == 1
    assert outcome2.assigned_addresses == []  # resolved to update, not insert
    rows = cell.query("people", select=["id", "name"], where=[], page_size=10, limits=LIMITS)
    assert rows.items == [{"id": 1, "name": "Ann2"}]

    with pytest.raises(FoundationError) as exc:
        cell.transact(
            "people",
            [{"operation": "upsert", "values": {"email": "a@example.invalid", "name": "Ann3"}, "where": [{"field": "name", "operator": "eq", "value": "Ann2"}]}],
            LIMITS,
        )
    assert exc.value.code == "VALIDATION_FAILED"

    with pytest.raises(FoundationError) as exc:
        cell.transact("people", [{"operation": "upsert", "values": {"name": "NoEmail"}}], LIMITS)
    assert exc.value.code == "VALIDATION_FAILED"


# --- CCR-13 §0.5 Q-2: `contains` literal semantics and `matches` wildcard --


def test_contains_is_a_literal_substring_and_never_interprets_wildcards():
    """Q-2 (案i): no character of the value is ever interpreted as a
    wildcard -- Python's `in` on strings is already exactly this."""
    cell = _cell()
    _create_entity(cell, "items")
    _add_field(cell, "items", "label")
    cell.transact(
        "items",
        [
            {"operation": "insert", "values": {"label": "50% off"}},
            {"operation": "insert", "values": {"label": "50X off"}},
            {"operation": "insert", "values": {"label": "under_score"}},
            {"operation": "insert", "values": {"label": "underxscore"}},
        ],
        LIMITS,
    )
    rows = cell.query("items", select=["label"], where=[Predicate("label", "contains", "50%")], page_size=10, limits=LIMITS)
    assert {r["label"] for r in rows.items} == {"50% off"}
    rows = cell.query("items", select=["label"], where=[Predicate("label", "contains", "er_sc")], page_size=10, limits=LIMITS)
    assert {r["label"] for r in rows.items} == {"under_score"}


def test_matches_wildcard_semantics_and_case_sensitivity():
    """Q-2 (補足案): `%` = any sequence (including empty), `_` = exactly
    one character, `\\` escapes the following character; case-sensitive."""
    cell = _cell()
    _create_entity(cell, "items")
    _add_field(cell, "items", "label")
    cell.transact(
        "items",
        [
            {"operation": "insert", "values": {"label": "hello"}},
            {"operation": "insert", "values": {"label": "help"}},
            {"operation": "insert", "values": {"label": "HELLO"}},
            {"operation": "insert", "values": {"label": "hxllo"}},
            {"operation": "insert", "values": {"label": "100% sure"}},
        ],
        LIMITS,
    )
    rows = cell.query("items", select=["label"], where=[Predicate("label", "matches", "hel%")], page_size=10, limits=LIMITS)
    assert {r["label"] for r in rows.items} == {"hello", "help"}  # not "HELLO"
    rows = cell.query("items", select=["label"], where=[Predicate("label", "matches", "h_llo")], page_size=10, limits=LIMITS)
    assert {r["label"] for r in rows.items} == {"hello", "hxllo"}
    rows = cell.query("items", select=["label"], where=[Predicate("label", "matches", "100\\% sure")], page_size=10, limits=LIMITS)
    assert {r["label"] for r in rows.items} == {"100% sure"}
    # An unmatched trailing pattern (no wildcard at all) is a plain exact
    # match, and a pattern that matches nothing raises nothing (empty
    # result, not an error).
    rows = cell.query("items", select=["label"], where=[Predicate("label", "matches", "nope")], page_size=10, limits=LIMITS)
    assert rows.items == []


def test_contains_and_matches_reject_non_string_values():
    """Q-2: both operators' value is always a plain string, independent of
    the target field's own declared type."""
    cell = _cell()
    _create_entity(cell, "items")
    _add_field(cell, "items", "label")
    with pytest.raises(FoundationError) as exc:
        cell.query("items", select=["label"], where=[Predicate("label", "contains", 5)], page_size=10, limits=LIMITS)
    assert exc.value.code == "VALIDATION_FAILED"
    with pytest.raises(FoundationError) as exc:
        cell.query("items", select=["label"], where=[Predicate("label", "matches", 5)], page_size=10, limits=LIMITS)
    assert exc.value.code == "VALIDATION_FAILED"


def test_matches_pattern_ending_in_an_unescaped_backslash_is_validation_failed():
    """WP-3 review blocker-2 (Q-2 adjudication 5): a pattern ending in a
    lone, unescaped backslash is malformed grammar -- PostgreSQL's own LIKE
    behaviour for this depends on the data it happens to be compared
    against, which the contract resolves by rejecting it deterministically
    here instead. An even number of trailing backslashes (all paired
    escapes) is fine."""
    cell = _cell()
    _create_entity(cell, "items")
    _add_field(cell, "items", "label")
    cell.transact("items", [{"operation": "insert", "values": {"label": "a"}}], LIMITS)
    with pytest.raises(FoundationError) as exc:
        cell.query("items", select=["label"], where=[Predicate("label", "matches", "a\\")], page_size=10, limits=LIMITS)
    assert exc.value.code == "VALIDATION_FAILED"
    with pytest.raises(FoundationError) as exc:
        cell.query("items", select=["label"], where=[Predicate("label", "matches", "a\\\\\\")], page_size=10, limits=LIMITS)
    assert exc.value.code == "VALIDATION_FAILED"
    # An even count of trailing backslashes is well-formed (each pair is a
    # single escaped literal backslash) -- must not be rejected.
    rows = cell.query("items", select=["label"], where=[Predicate("label", "matches", "a\\\\")], page_size=10, limits=LIMITS)
    assert rows.items == []


def test_integer_field_value_out_of_bigint_range_is_validation_failed():
    """R-7 addendum (WP-3 review blocker-2): a JSON integer with no
    fixed width passes a bare `isinstance(int)` check but PostgreSQL's
    `bigint` cannot store it -- the shared boundary must reject this
    itself, deterministically, rather than let each backend discover it
    independently (or not at all, for `ApplicationCell`)."""
    cell = _cell()
    _create_entity(cell, "readings")
    _add_field(cell, "readings", "n", "integer")
    too_big = 2**63
    too_small = -(2**63) - 1
    for bad in (too_big, too_small):
        with pytest.raises(FoundationError) as exc:
            cell.transact("readings", [{"operation": "insert", "values": {"n": bad}}], LIMITS)
        assert exc.value.code == "VALIDATION_FAILED"
        # Contract 1.7.0 (D-2 (3), monitor ruling M-3/D, rulings-wp2a-
        # review.md): `field` is now the request-internal path through the
        # choke point's shared `field_name` argument, not the bare entity
        # field name -- the single insert here is always index 0.
        # Contract 1.7.0 (D-3, WP-2e): out-of-range is a `field_type`
        # violation -- `declared_type`/`observed_type` both "integer" (the
        # JSON type matches; only the magnitude does not).
        assert exc.value.details == {
            "field": "operations/0/values/n", "violated_declaration": "field_type",
            "declared_type": "integer", "observed_type": "integer",
        }
        rendered = repr(exc.value)
        assert str(bad) not in rendered
    # The boundary values themselves are valid.
    cell.transact("readings", [{"operation": "insert", "values": {"n": 2**63 - 1}}, {"operation": "insert", "values": {"n": -(2**63)}}], LIMITS)
    rows = {row["n"] for row in cell.query("readings", select=["n"], where=[], page_size=10, limits=LIMITS).items}
    assert rows == {2**63 - 1, -(2**63)}
    # Also checked as a predicate value and as an `in`-list element
    # (corrigendum m-7 parity).
    with pytest.raises(FoundationError) as exc:
        cell.query("readings", select=["n"], where=[Predicate("n", "eq", too_big)], page_size=10, limits=LIMITS)
    assert exc.value.code == "VALIDATION_FAILED"
    with pytest.raises(FoundationError) as exc:
        cell.query("readings", select=["n"], where=[Predicate("n", "in", [1, too_big])], page_size=10, limits=LIMITS)
    assert exc.value.code == "VALIDATION_FAILED"


def test_nul_byte_is_rejected_in_string_object_array_and_untyped_values():
    """R-7 addendum (WP-3 review blocker-2): a U+0000 anywhere inside a
    string/object/array/untyped value is a value PostgreSQL's `text`/
    `jsonb` storage cannot hold at all -- refused deterministically in the
    shared boundary, never left for a backend to discover as its own
    runtime error."""
    cell = _cell()
    _create_entity(cell, "docs")
    for name, field_type in (("s", "string"), ("o", "object"), ("a", "array"), ("u", None)):
        _add_field(cell, "docs", name, field_type)
    bad_values = {"s": "has\x00nul", "o": {"k": "has\x00nul"}, "a": ["has\x00nul"], "u": "has\x00nul"}
    # Contract 1.7.0 (D-3, WP-2e): a typed field's NUL-byte refusal is a
    # `field_type` violation (same error code/disclosure shape as the type
    # check itself, `_check_type`'s own docstring) -- `declared_type`/
    # `observed_type` both name the field's own type. The untyped field
    # ("u", `field_type=None`) has no declared type to violate, so its
    # denial stays the bare `field` form (no `violated_declaration`).
    declared_types = {"s": "string", "o": "object", "a": "array"}
    for field_name, bad_value in bad_values.items():
        with pytest.raises(FoundationError) as exc:
            cell.transact("docs", [{"operation": "insert", "values": {field_name: bad_value}}], LIMITS)
        assert exc.value.code == "VALIDATION_FAILED"
        # Monitor ruling M-3/D: request-internal path, not a bare field name.
        if field_name in declared_types:
            assert exc.value.details == {
                "field": f"operations/0/values/{field_name}", "violated_declaration": "field_type",
                "declared_type": declared_types[field_name], "observed_type": declared_types[field_name],
            }
        else:
            assert exc.value.details == {"field": f"operations/0/values/{field_name}"}
        assert "\x00" not in repr(exc.value)
    # Untyped field: NUL nested inside a dict/list value too.
    with pytest.raises(FoundationError) as exc:
        cell.transact("docs", [{"operation": "insert", "values": {"u": {"nested": ["has\x00nul"]}}}], LIMITS)
    assert exc.value.code == "VALIDATION_FAILED"


def test_expected_revision_containing_nul_is_validation_failed():
    cell = _cell()
    _create_entity(cell, "docs")
    _add_field(cell, "docs", "body")
    cell.transact("docs", [{"operation": "insert", "values": {"body": "v1"}}], LIMITS)
    with pytest.raises(FoundationError) as exc:
        cell.transact(
            "docs",
            [{"operation": "update", "where": [{"field": "id", "operator": "eq", "value": 1}], "values": {"body": "v2"}, "expected_revision": "has\x00nul"}],
            LIMITS,
        )
    assert exc.value.code == "VALIDATION_FAILED"


def test_contains_and_matches_pattern_containing_nul_is_validation_failed():
    cell = _cell()
    _create_entity(cell, "items")
    _add_field(cell, "items", "label")
    with pytest.raises(FoundationError) as exc:
        cell.query("items", select=["label"], where=[Predicate("label", "contains", "has\x00nul")], page_size=10, limits=LIMITS)
    assert exc.value.code == "VALIDATION_FAILED"
    with pytest.raises(FoundationError) as exc:
        cell.query("items", select=["label"], where=[Predicate("label", "matches", "has\x00nul")], page_size=10, limits=LIMITS)
    assert exc.value.code == "VALIDATION_FAILED"


# --- WP-3 review D-1~D-4: predicate semantics unified with SQL's own
# three-valued logic ----------------------------------------------------


def test_contains_and_matches_exclude_null_rows_instead_of_raising():
    """WP-3 review D-1: a nullable column with at least one NULL row used
    to make the *entire query* raise VALIDATION_FAILED for `contains`
    (`expected in None` -- a TypeError) -- this was a reference-
    implementation bug, narrower than the deployed PostgreSQL backend,
    where a NULL row is simply excluded (SQL: `NULL LIKE pattern` is
    UNKNOWN). `matches` gets the identical fix."""
    cell = _cell()
    _create_entity(cell, "items")
    _add_field(cell, "items", "label")
    cell.transact(
        "items",
        [
            {"operation": "insert", "values": {"label": "hello"}},
            {"operation": "insert", "values": {"label": None}},
        ],
        LIMITS,
    )
    rows = cell.query("items", select=["label"], where=[Predicate("label", "contains", "ell")], page_size=10, limits=LIMITS)
    assert rows.items == [{"label": "hello"}]
    rows = cell.query("items", select=["label"], where=[Predicate("label", "matches", "hel%")], page_size=10, limits=LIMITS)
    assert rows.items == [{"label": "hello"}]


def test_contains_and_matches_apply_to_typed_non_string_columns_via_text_form():
    """WP-3 review D-1~D-4: "型付き非文字列列にも text 表現で適用可" --
    matching `PostgresCell`'s own `::text`/`#>> '{}'` behaviour for the
    unambiguous cases (booleans, plain integers)."""
    cell = _cell()
    _create_entity(cell, "readings")
    _add_field(cell, "readings", "n", "integer")
    _add_field(cell, "readings", "flag", "boolean")
    cell.transact(
        "readings",
        [
            {"operation": "insert", "values": {"n": 12345, "flag": True}},
            {"operation": "insert", "values": {"n": 999, "flag": False}},
        ],
        LIMITS,
    )
    rows = cell.query("readings", select=["n"], where=[Predicate("n", "contains", "234")], page_size=10, limits=LIMITS)
    assert rows.items == [{"n": 12345}]
    rows = cell.query("readings", select=["flag"], where=[Predicate("flag", "matches", "tr%")], page_size=10, limits=LIMITS)
    assert rows.items == [{"flag": True}]


def test_ne_excludes_null_rows_per_sql_three_valued_logic():
    """WP-3 review D-1~D-4: `NULL <> value` is UNKNOWN in SQL, not "not
    equal because it's a different Python value" -- a NULL row must never
    match `ne`."""
    cell = _cell()
    _create_entity(cell, "items")
    _add_field(cell, "items", "tag")
    cell.transact(
        "items",
        [
            {"operation": "insert", "values": {"tag": "a"}},
            {"operation": "insert", "values": {"tag": "b"}},
            {"operation": "insert", "values": {"tag": None}},
        ],
        LIMITS,
    )
    rows = cell.query("items", select=["tag"], where=[Predicate("tag", "ne", "a")], page_size=10, limits=LIMITS)
    assert {r["tag"] for r in rows.items} == {"b"}  # not the NULL row


def test_in_excludes_null_rows_even_when_the_list_itself_contains_null():
    """WP-3 review D-1~D-4: `NULL IN (...)` is always UNKNOWN/excluded in
    SQL, even if the list contains a literal null."""
    cell = _cell()
    _create_entity(cell, "items")
    _add_field(cell, "items", "tag")
    cell.transact(
        "items",
        [
            {"operation": "insert", "values": {"tag": "a"}},
            {"operation": "insert", "values": {"tag": None}},
        ],
        LIMITS,
    )
    rows = cell.query("items", select=["tag"], where=[Predicate("tag", "in", ["a", None])], page_size=10, limits=LIMITS)
    assert rows.items == [{"tag": "a"}]


def test_eq_and_ne_reject_a_null_predicate_value():
    """WP-3 confirmation review N-3: `= NULL`/`<> NULL` is always UNKNOWN
    in SQL -- silently and permanently matching zero rows -- so this is
    refused deterministically (`is_null` is the correct operator for a
    null check) rather than left to quietly return an empty result
    forever."""
    cell = _cell()
    _create_entity(cell, "items")
    _add_field(cell, "items", "tag")
    cell.transact("items", [{"operation": "insert", "values": {"tag": None}}], LIMITS)
    with pytest.raises(FoundationError) as exc:
        cell.query("items", select=["tag"], where=[Predicate("tag", "eq", None)], page_size=10, limits=LIMITS)
    assert exc.value.code == "VALIDATION_FAILED"
    assert exc.value.details == {"field": "tag"}
    with pytest.raises(FoundationError) as exc:
        cell.query("items", select=["tag"], where=[Predicate("tag", "ne", None)], page_size=10, limits=LIMITS)
    assert exc.value.code == "VALIDATION_FAILED"
    # is_null is the correct, accepted way to ask this.
    rows = cell.query("items", select=["tag"], where=[Predicate("tag", "is_null")], page_size=10, limits=LIMITS)
    assert rows.items == [{"tag": None}]


def _docs_cell() -> ApplicationCell:
    cell = _cell()
    _create_entity(cell, "docs")
    _add_field(cell, "docs", "body")
    return cell


def _row_revision(cell: ApplicationCell, entity: str, row_id: int) -> str:
    rows = cell.query(entity, select=["id"], where=[Predicate("id", "eq", row_id)], page_size=10, limits=LIMITS)
    return rows.revisions[0]


def test_expected_revision_on_insert_is_validation_failed():
    cell = _docs_cell()
    with pytest.raises(FoundationError) as exc:
        cell.transact("docs", [{"operation": "insert", "values": {"body": "v1"}, "expected_revision": "anything"}], LIMITS)
    assert exc.value.code == "VALIDATION_FAILED"


def test_expected_revision_mismatch_is_precondition_failed():
    cell = _docs_cell()
    cell.transact("docs", [{"operation": "insert", "values": {"body": "v1"}}], LIMITS)
    with pytest.raises(FoundationError) as exc:
        cell.transact("docs", [{"operation": "update", "where": [{"field": "id", "operator": "eq", "value": 1}], "values": {"body": "v2"}, "expected_revision": "not-the-real-revision"}], LIMITS)
    assert exc.value.code == "PRECONDITION_FAILED"


def test_expected_revision_with_no_predicate_match_is_not_found():
    cell = _docs_cell()
    cell.transact("docs", [{"operation": "insert", "values": {"body": "v1"}}], LIMITS)
    revision = _row_revision(cell, "docs", 1)
    with pytest.raises(FoundationError) as exc:
        cell.transact("docs", [{"operation": "update", "where": [{"field": "id", "operator": "eq", "value": 999}], "values": {"body": "v2"}, "expected_revision": revision}], LIMITS)
    assert exc.value.code == "NOT_FOUND"
    with pytest.raises(FoundationError) as exc:
        where = [{"field": "id", "operator": "eq", "value": 999}]
        cell.transact("docs", [{"operation": "delete", "where": where, "expected_revision": revision, "destructive": True, "confirmation": _delete_phrase("docs", where, cell.schema_revision)}], LIMITS)
    assert exc.value.code == "NOT_FOUND"


def test_expected_revision_success_rotates_revision_and_leaves_other_rows_unaffected():
    cell = _docs_cell()
    cell.transact("docs", [{"operation": "insert", "values": {"body": "v1"}}, {"operation": "insert", "values": {"body": "other"}}], LIMITS)
    revision_1 = _row_revision(cell, "docs", 1)
    revision_2_before = _row_revision(cell, "docs", 2)

    outcome = cell.transact("docs", [{"operation": "update", "where": [{"field": "id", "operator": "eq", "value": 1}], "values": {"body": "v2"}, "expected_revision": revision_1}], LIMITS)
    assert outcome.affected == 1
    assert _row_revision(cell, "docs", 1) != revision_1
    assert _row_revision(cell, "docs", 2) == revision_2_before

    with pytest.raises(FoundationError) as exc:
        cell.transact("docs", [{"operation": "update", "where": [{"field": "id", "operator": "eq", "value": 1}], "values": {"body": "v3"}, "expected_revision": revision_1}], LIMITS)
    assert exc.value.code == "PRECONDITION_FAILED"


def test_expected_revision_without_precondition_zero_row_update_and_delete_still_succeed():
    cell = _docs_cell()
    outcome = cell.transact("docs", [{"operation": "update", "where": [{"field": "id", "operator": "eq", "value": 999}], "values": {"body": "v2"}}], LIMITS)
    assert outcome.affected == 0
    where = [{"field": "id", "operator": "eq", "value": 999}]
    outcome = cell.transact("docs", [{"operation": "delete", "where": where, "destructive": True, "confirmation": _delete_phrase("docs", where, cell.schema_revision)}], LIMITS)
    assert outcome.affected == 0


def test_expected_revision_on_empty_values_update_is_validation_failed():
    cell = _docs_cell()
    cell.transact("docs", [{"operation": "insert", "values": {"body": "v1"}}], LIMITS)
    revision = _row_revision(cell, "docs", 1)
    with pytest.raises(FoundationError) as exc:
        cell.transact("docs", [{"operation": "update", "where": [{"field": "id", "operator": "eq", "value": 1}], "values": {}, "expected_revision": revision}], LIMITS)
    assert exc.value.code == "VALIDATION_FAILED"


def test_expected_revision_predicate_matching_several_rows_affects_only_the_revision_row():
    cell = _docs_cell()
    cell.transact(
        "docs",
        [
            {"operation": "insert", "values": {"body": "shared"}},
            {"operation": "insert", "values": {"body": "shared"}},
            {"operation": "insert", "values": {"body": "shared"}},
        ],
        LIMITS,
    )
    revision_2 = _row_revision(cell, "docs", 2)
    outcome = cell.transact("docs", [{"operation": "update", "where": [{"field": "body", "operator": "eq", "value": "shared"}], "values": {"body": "updated"}, "expected_revision": revision_2}], LIMITS)
    assert outcome.affected == 1
    rows = cell.query("docs", select=["id", "body"], where=[], page_size=10, limits=LIMITS).items
    assert {row["id"]: row["body"] for row in rows} == {1: "shared", 2: "updated", 3: "shared"}


def test_type_mismatch_is_validation_failed_even_with_a_matching_precondition():
    """R-7, corrigendum M-9: a type mismatch (client bug) is refused before
    a precondition is even evaluated -- never surfaced as PRECONDITION_
    FAILED/NOT_FOUND, both of which read as "retry" to an AI agent client
    and could never actually succeed on retry."""
    cell = _docs_cell()
    cell.transact("docs", [{"operation": "insert", "values": {"body": "v1"}}], LIMITS)
    revision = _row_revision(cell, "docs", 1)
    with pytest.raises(FoundationError) as exc:
        cell.transact(
            "docs",
            [{"operation": "update", "where": [{"field": "id", "operator": "eq", "value": "not-an-int"}], "values": {"body": "v2"}, "expected_revision": revision}],
            LIMITS,
        )
    assert exc.value.code == "VALIDATION_FAILED"


def test_destructive_confirmation_is_checked_before_precondition_evaluation():
    cell = _docs_cell()
    cell.transact("docs", [{"operation": "insert", "values": {"body": "v1"}}], LIMITS)
    with pytest.raises(FoundationError) as exc:
        cell.transact("docs", [{"operation": "delete", "where": [{"field": "id", "operator": "eq", "value": 1}], "expected_revision": "wrong-revision"}], LIMITS)
    assert exc.value.code == "DESTRUCTIVE_CONFIRMATION_REQUIRED"
    assert cell.query("docs", select=["id"], where=[], page_size=10, limits=LIMITS).items == [{"id": 1}]


def test_upsert_expected_revision_never_resolves_to_insert():
    cell = _cell()
    _create_entity(cell, "people")
    _add_field(cell, "people", "email")
    _create_index(cell, "people", "by_email", ["email"], unique=True)
    with pytest.raises(FoundationError) as exc:
        cell.transact("people", [{"operation": "upsert", "values": {"email": "new@example.invalid"}, "expected_revision": "anything"}], LIMITS)
    assert exc.value.code == "NOT_FOUND"
    assert cell.query("people", select=["id"], where=[], page_size=10, limits=LIMITS).items == []


def _numbered_cell(count: int) -> ApplicationCell:
    cell = _cell()
    _create_entity(cell, "items")
    _add_field(cell, "items", "n")
    operations = [{"operation": "insert", "values": {"n": n}} for n in range(count)]
    cell.transact("items", operations, LIMITS)
    return cell


def test_order_by_sorts_and_appends_id_when_absent():
    cell = _numbered_cell(3)  # n = 0, 1, 2 with id = 1, 2, 3 respectively
    descending = cell.query("items", select=["n"], where=[], page_size=10, limits=LIMITS, order_by=[{"field": "n", "direction": "desc"}])
    assert descending.items == [{"n": 2}, {"n": 1}, {"n": 0}]
    default_order = cell.query("items", select=["id"], where=[], page_size=10, limits=LIMITS)
    assert default_order.items == [{"id": 1}, {"id": 2}, {"id": 3}]


def test_order_by_unknown_field_is_not_found():
    cell = _numbered_cell(1)
    with pytest.raises(FoundationError) as exc:
        cell.query("items", select=["n"], where=[], page_size=10, limits=LIMITS, order_by=[{"field": "ghost", "direction": "asc"}])
    assert exc.value.code == "NOT_FOUND"


def test_order_by_rejects_a_repeated_field():
    cell = _numbered_cell(1)
    with pytest.raises(FoundationError) as exc:
        cell.query("items", select=["n"], where=[], page_size=10, limits=LIMITS, order_by=[{"field": "n", "direction": "asc"}, {"field": "n", "direction": "desc"}])
    assert exc.value.code == "VALIDATION_FAILED"


def test_order_by_null_placement_matches_postgresql_defaults():
    """WP-2 review M-6: NULL sorts last for ascending, first for
    descending -- PostgreSQL's own default (`NULLS LAST`/`NULLS FIRST`)."""
    cell = _cell()
    _create_entity(cell, "tasks")
    _add_field(cell, "tasks", "priority", "integer")
    cell.transact(
        "tasks",
        [
            {"operation": "insert", "values": {"priority": 2}},
            {"operation": "insert", "values": {"priority": None}},
            {"operation": "insert", "values": {"priority": 1}},
        ],
        LIMITS,
    )
    ascending = cell.query("tasks", select=["priority"], where=[], page_size=10, limits=LIMITS, order_by=[{"field": "priority", "direction": "asc"}])
    assert ascending.items == [{"priority": 1}, {"priority": 2}, {"priority": None}]
    descending = cell.query("tasks", select=["priority"], where=[], page_size=10, limits=LIMITS, order_by=[{"field": "priority", "direction": "desc"}])
    assert descending.items == [{"priority": None}, {"priority": 2}, {"priority": 1}]


def test_order_by_untyped_column_uses_jsonb_cross_type_order():
    """WP-2 review M-6: an untyped (JSONB-equivalent) column's cross-type
    ascending order is String < Number < Boolean < Array < Object."""
    cell = _cell()
    _create_entity(cell, "mixed")
    _add_field(cell, "mixed", "value")
    cell.transact(
        "mixed",
        [
            {"operation": "insert", "values": {"value": {"k": 1}}},
            {"operation": "insert", "values": {"value": [1]}},
            {"operation": "insert", "values": {"value": True}},
            {"operation": "insert", "values": {"value": 1}},
            {"operation": "insert", "values": {"value": "x"}},
        ],
        LIMITS,
    )
    ascending = cell.query("mixed", select=["value"], where=[], page_size=10, limits=LIMITS, order_by=[{"field": "value", "direction": "asc"}])
    assert ascending.items == [{"value": "x"}, {"value": 1}, {"value": True}, {"value": [1]}, {"value": {"k": 1}}]


def test_order_by_clause_count_is_charged_to_query_complexity():
    cell = _cell()
    _create_entity(cell, "items")
    _add_field(cell, "items", "n")
    with pytest.raises(FoundationError) as exc:
        cell.query(
            "items",
            select=["n"],
            where=[],
            page_size=10,
            limits=ResourceLimits(query_complexity=1),
            order_by=[{"field": "n", "direction": "asc"}],
        )
    assert exc.value.code == "LIMIT_EXCEEDED"


def test_cursor_pagination_pages_through_results_and_signals_has_more():
    cell = _numbered_cell(5)
    first = cell.query("items", select=["n"], where=[], page_size=2, limits=LIMITS)
    assert first.items == [{"n": 0}, {"n": 1}]
    assert first.has_more is True
    assert first.next_cursor is not None
    second = cell.query("items", select=["n"], where=[], page_size=2, limits=LIMITS, cursor=first.next_cursor)
    assert second.items == [{"n": 2}, {"n": 3}]
    assert second.has_more is True
    third = cell.query("items", select=["n"], where=[], page_size=2, limits=LIMITS, cursor=second.next_cursor)
    assert third.items == [{"n": 4}]
    assert third.has_more is False
    assert third.next_cursor is None


def test_cursor_shape_mismatch_and_malformed_cursor_are_rejected():
    cell = _numbered_cell(5)
    first = cell.query("items", select=["n"], where=[], page_size=2, limits=LIMITS)
    with pytest.raises(FoundationError) as exc:
        cell.query("items", select=["id", "n"], where=[], page_size=2, limits=LIMITS, cursor=first.next_cursor)
    assert exc.value.code == "VALIDATION_FAILED"
    with pytest.raises(FoundationError) as exc:
        cell.query("items", select=["n"], where=[], page_size=2, limits=LIMITS, cursor="not-a-valid-cursor")
    assert exc.value.code == "VALIDATION_FAILED"


def _forge_cursor(payload) -> str:
    blob = json.dumps(payload).encode("utf-8")
    return base64.urlsafe_b64encode(blob).decode("ascii").rstrip("=")


def _decode_cursor_shape(cursor: str) -> str:
    padded = cursor + "=" * (-len(cursor) % 4)
    return json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))["q"]


def test_cursor_rejects_negative_offset_overflow_and_non_dict_payload():
    """WP-2 review M-13: R-6's offset bound (0 <= offset <= 10^9) and
    payload shape are checked explicitly, not only via a garbage string."""
    cell = _numbered_cell(3)
    first = cell.query("items", select=["n"], where=[], page_size=2, limits=LIMITS)
    shape = _decode_cursor_shape(first.next_cursor)

    with pytest.raises(FoundationError) as exc:
        cell.query("items", select=["n"], where=[], page_size=2, limits=LIMITS, cursor=_forge_cursor({"o": -1, "q": shape}))
    assert exc.value.code == "VALIDATION_FAILED"

    with pytest.raises(FoundationError) as exc:
        cell.query("items", select=["n"], where=[], page_size=2, limits=LIMITS, cursor=_forge_cursor({"o": 10**9 + 1, "q": shape}))
    assert exc.value.code == "VALIDATION_FAILED"

    with pytest.raises(FoundationError) as exc:
        cell.query("items", select=["n"], where=[], page_size=2, limits=LIMITS, cursor=_forge_cursor(["not", "a", "dict"]))
    assert exc.value.code == "VALIDATION_FAILED"


def test_page_size_over_the_contract_maximum_is_validation_failed():
    """WP-4 review minor-1: `Page.size`'s contract maximum (1000,
    `spec/data-service-api.v1.json`) is enforced in the shared boundary,
    independent of whatever `ResourceLimits.result_items` a deployment
    happens to configure (this fixture's default is also 1000, so a
    request for 1001 is unambiguously over the *contract's* own ceiling,
    not merely this deployment's)."""
    cell = _numbered_cell(1)
    with pytest.raises(FoundationError) as exc:
        cell.query("items", select=["n"], where=[], page_size=1001, limits=LIMITS)
    assert exc.value.code == "VALIDATION_FAILED"
    # The boundary value itself is accepted (rejected only for exceeding
    # it, not merely being large).
    cell.query("items", select=["n"], where=[], page_size=1000, limits=LIMITS)


def test_cursor_shape_hash_is_bound_to_application_and_entity():
    """WP-2 review minor (a): a cursor minted under one Application/entity
    must not validate against another's query of the same select/where/
    order_by/size shape."""
    cell_a = _numbered_cell(3)
    cursor = cell_a.query("items", select=["n"], where=[], page_size=2, limits=LIMITS).next_cursor

    other_app = _numbered_cell(3)
    other_app.application_id = "different-engine-app"
    with pytest.raises(FoundationError) as exc:
        other_app.query("items", select=["n"], where=[], page_size=2, limits=LIMITS, cursor=cursor)
    assert exc.value.code == "VALIDATION_FAILED"

    cell_a2 = _cell()
    _create_entity(cell_a2, "items")
    _add_field(cell_a2, "items", "n")
    _create_entity(cell_a2, "other_entity")
    _add_field(cell_a2, "other_entity", "n")
    cell_a2.transact("other_entity", [{"operation": "insert", "values": {"n": 0}}, {"operation": "insert", "values": {"n": 1}}, {"operation": "insert", "values": {"n": 2}}], LIMITS)
    with pytest.raises(FoundationError) as exc:
        cell_a2.query("other_entity", select=["n"], where=[], page_size=2, limits=LIMITS, cursor=cursor)
    assert exc.value.code == "VALIDATION_FAILED"


def test_query_revisions_are_index_aligned_with_items():
    cell = _numbered_cell(3)
    outcome = cell.query("items", select=["id", "n"], where=[], page_size=10, limits=LIMITS)
    assert len(outcome.revisions) == len(outcome.items)
    assert len(set(outcome.revisions)) == len(outcome.items)  # every row has a distinct revision
    for revision in outcome.revisions:
        assert isinstance(revision, str) and revision


def test_id_is_never_reused_after_delete_a_failed_batch_or_entity_recreation():
    cell = _cell()
    _create_entity(cell, "widgets")
    cell.transact("widgets", [{"operation": "insert", "values": {}}, {"operation": "insert", "values": {}}], LIMITS)
    where = [{"field": "id", "operator": "eq", "value": 2}]
    cell.transact("widgets", [{"operation": "delete", "where": where, "destructive": True, "confirmation": _delete_phrase("widgets", where, cell.schema_revision)}], LIMITS)
    cell.transact("widgets", [{"operation": "insert", "values": {}}], LIMITS)
    ids = sorted(row["id"] for row in cell.query("widgets", select=["id"], where=[], page_size=10, limits=LIMITS).items)
    assert ids == [1, 3]  # id 2 is gone forever, never reused within this entity's lifetime

    # A failed batch containing an insert still consumes the id (mirrors
    # PostgreSQL's own non-transactional identity sequence, R-1).
    with pytest.raises(FoundationError):
        cell.transact("widgets", [{"operation": "insert", "values": {}}, {"operation": "unsupported"}], LIMITS)
    cell.transact("widgets", [{"operation": "insert", "values": {}}], LIMITS)
    ids_after = sorted(row["id"] for row in cell.query("widgets", select=["id"], where=[], page_size=10, limits=LIMITS).items)
    assert ids_after == [1, 3, 5]  # id 4 was consumed and gapped by the rolled-back batch

    # drop_entity + recreate is a new entity: addressing restarts at 1.
    cell.apply_schema({"operation": "drop_entity", "entity": "widgets", "destructive": True, "confirmation": drop_entity_confirmation_phrase("widgets", cell.schema_revision)}, developer=True, limits=LIMITS)
    _create_entity(cell, "widgets")
    cell.transact("widgets", [{"operation": "insert", "values": {}}], LIMITS)
    assert cell.query("widgets", select=["id"], where=[], page_size=10, limits=LIMITS).items == [{"id": 1}]


def test_schema_objects_limit_charges_indexes_and_recovers_capacity_after_drop_index():
    """WP-2 review M-2 (an index is a real resource, counted like entities/
    fields already were) plus confirmation-review fix M-D(d): actually
    drive the limit to LIMIT_EXCEEDED by stacking indexes up to the cap,
    then prove `drop_index` frees exactly one slot back."""
    cell = _cell()
    _create_entity(cell, "widgets")
    _add_field(cell, "widgets", "tag")
    _add_field(cell, "widgets", "other")
    # entity(1) + id(1) + tag(1) + other(1) = 4 objects before any index.
    limits = ResourceLimits(schema_objects=5)
    cell.apply_schema({"operation": "create_index", "entity": "widgets", "index": "by_tag", "fields": ["tag"]}, developer=True, limits=limits)  # 4 + 1 = 5, at the cap
    with pytest.raises(FoundationError) as exc:
        cell.apply_schema({"operation": "create_index", "entity": "widgets", "index": "by_other", "fields": ["other"]}, developer=True, limits=limits)  # would be 6 > 5
    assert exc.value.code == "LIMIT_EXCEEDED"
    assert set(cell.indexes["widgets"]) == {"by_tag"}  # the rejected create_index left no trace

    # Dropping the first index frees exactly one slot back (5 -> 4), so the
    # second create_index -- identical in every other respect -- now fits.
    cell.apply_schema({"operation": "drop_index", "entity": "widgets", "index": "by_tag", "destructive": True, "confirmation": drop_index_confirmation_phrase("widgets", "by_tag", cell.schema_revision)}, developer=True, limits=limits)
    cell.apply_schema({"operation": "create_index", "entity": "widgets", "index": "by_other", "fields": ["other"]}, developer=True, limits=limits)
    assert set(cell.indexes["widgets"]) == {"by_other"}


def test_query_outcome_rejects_revisions_not_index_aligned_with_items():
    """WP-2 review M-10's invariant, confirmed as a checked failure
    (confirmation-review fix M-D(a)): `revisions`, when supplied at all,
    must be exactly as long as `items` -- `None` (unmaintained) is the only
    other accepted shape."""
    with pytest.raises(ValueError):
        QueryOutcome(items=[{}], revisions=[])


def test_update_value_type_mismatch_is_validation_failed():
    """R-7, corrigendum M-9 (confirmation-review fix M-D(b)): the write-
    values type check that M-9 moved ahead of target-row search/precondition
    resolution is exercised directly here, on a plain `update` with no
    precondition at all -- proving the relocated check is still reached on
    that path, not only when a precondition happens to be present."""
    cell = _cell()
    _create_entity(cell, "typed")
    _add_field(cell, "typed", "i", "integer")
    cell.transact("typed", [{"operation": "insert", "values": {"i": 1}}], LIMITS)
    with pytest.raises(FoundationError) as exc:
        cell.transact("typed", [{"operation": "update", "where": [{"field": "id", "operator": "eq", "value": 1}], "values": {"i": "not-an-int"}}], LIMITS)
    assert exc.value.code == "VALIDATION_FAILED"
    # No side effect: the mismatched value was never written.
    assert cell.query("typed", select=["i"], where=[], page_size=10, limits=LIMITS).items == [{"i": 1}]


def test_transact_checks_deadline_before_each_operation_not_only_the_whole_batch():
    """WP-2 review M-2's per-operation deadline check (confirmation-review
    fix M-D(c)): using the same `_clock` injection pattern as `test_schema_
    deadline_failure_rolls_back_entity_catalog_and_revision` above, prove
    the deadline is re-checked *between* operations in one batch, not only
    once before/after the whole thing -- the second insert must never even
    be attempted."""
    cell = _cell()
    _create_entity(cell, "items")
    # Consumed in order: (1) the top-of-`transact()` check, (2) the
    # per-operation check before the first insert (both pass, deadline
    # 0.01), (3) the per-operation check before the second insert (0.02 >
    # 0.01 -- fails here, before the second insert is ever attempted).
    clock_values = iter([0.0, 0.0, 0.02])
    with pytest.raises(FoundationError) as exc:
        cell.transact(
            "items",
            [{"operation": "insert", "values": {}}, {"operation": "insert", "values": {}}],
            LIMITS,
            deadline=0.01,
            clock=lambda: next(clock_values),
        )
    assert exc.value.code == "LIMIT_EXCEEDED"
    # Whole-batch rollback: not even the first (otherwise valid) insert survives.
    assert cell.query("items", select=["id"], where=[], page_size=10, limits=LIMITS).items == []


# ==========================================================================
# CCR-13 WP-5b (docs/design/R2DB_CCR13_STORAGE_V1.md §3): the WP-2-through-
# WP-5 provisional `DataService` gate is removed, and `capabilities()`
# catches up in the same commit. These tests go through `service` (not a
# raw `ApplicationCell`) to prove the vocabulary the gate used to refuse is
# now genuinely reachable at the facade -- `matches`/`expected_revision`/
# `upsert`/`create_index`/`drop_index`/`field_type`/the full catalog
# declaration all execute through `service` exactly as the direct-cell
# tests above already proved `ApplicationCell` itself could.
# ==========================================================================


def test_service_query_matches_filter_executes(service):
    runtime = service.authenticate("cred-a.secret-a")
    assert service.query(runtime, "notes", select=["body"], where=[{"field": "body", "operator": "matches", "value": "a%"}]) == [{"body": "a"}]
    assert service.query(runtime, "notes", select=["body"], where=[{"field": "body", "operator": "matches", "value": "z%"}]) == []


def test_service_mutate_update_and_delete_where_matches_executes(service):
    """`update`/`delete`'s own `operation.where` accepts `matches` too, not
    only `query()`'s predicates."""
    runtime = service.authenticate("cred-a.secret-a")
    affected = service.mutate(runtime, "notes", [{"operation": "update", "where": [{"field": "body", "operator": "matches", "value": "a%"}], "values": {"body": "renamed"}}])
    assert affected == 1
    assert service.query(runtime, "notes", select=["body"]) == [{"body": "renamed"}]
    where = [{"field": "body", "operator": "matches", "value": "rename%"}]
    affected = service.mutate(
        runtime,
        "notes",
        [{"operation": "delete", "where": where, "destructive": True, "confirmation": _delete_phrase("notes", where)}],
    )
    assert affected == 1
    assert service.query(runtime, "notes", select=["body"]) == []


def test_service_mutate_expected_revision_executes(service):
    runtime = service.authenticate("cred-a.secret-a")
    revision = service.query_page(runtime, "notes", select=["id"], where=[{"field": "id", "operator": "eq", "value": 1}]).revisions[0]
    affected = service.mutate(runtime, "notes", [{"operation": "update", "where": [{"field": "id", "operator": "eq", "value": 1}], "values": {"body": "z"}, "expected_revision": revision}])
    assert affected == 1
    with pytest.raises(FoundationError) as exc:
        service.mutate(runtime, "notes", [{"operation": "update", "where": [{"field": "id", "operator": "eq", "value": 1}], "values": {"body": "y"}, "expected_revision": revision}])
    assert exc.value.code == "PRECONDITION_FAILED"


def test_service_mutate_upsert_executes_with_a_declared_unique_key(service):
    developer = service.authenticate("dev-a.dev-secret-a")
    service.schema(developer, {"operation": "add_field", "entity": "notes", "field": "tag"})
    service.schema(developer, {"operation": "create_index", "entity": "notes", "index": "by_tag", "fields": ["tag"], "unique": True})
    runtime = service.authenticate("cred-a.secret-a")
    result = service.mutate_result(runtime, "notes", [{"operation": "upsert", "values": {"tag": "z"}}])
    assert result.affected == 1
    assert result.assigned_addresses == [{"address": {"id": 2}}]  # id 1 is the seeded row (tag is null, does not match "z")
    result2 = service.mutate_result(runtime, "notes", [{"operation": "upsert", "values": {"tag": "z", "body": "updated"}}])
    assert result2.affected == 1
    assert result2.assigned_addresses == []  # resolved to update, not insert


def test_service_mutate_upsert_without_a_declared_key_is_still_capability_unsupported(service):
    """Upsert's per-entity precondition (a declared uniqueness key) is a
    real, entity-scoped condition, unaffected by the gate's removal --
    `notes` here declares no unique key at all."""
    runtime = service.authenticate("cred-a.secret-a")
    with pytest.raises(FoundationError) as exc:
        service.mutate(runtime, "notes", [{"operation": "upsert", "values": {"body": "x"}}])
    assert exc.value.code == "CAPABILITY_UNSUPPORTED"


def test_service_schema_create_index_and_drop_index_execute(service):
    developer = service.authenticate("dev-a.dev-secret-a")
    service.schema(developer, {"operation": "add_field", "entity": "notes", "field": "tag"})
    revision = service.schema(developer, {"operation": "create_index", "entity": "notes", "index": "by_tag", "fields": ["tag"], "unique": True}).revision
    assert isinstance(revision, int)
    runtime = service.authenticate("cred-a.secret-a")
    assert service.catalog(runtime)["entities"][0]["unique_keys"] == [{"name": "by_tag", "fields": ["tag"]}]
    with pytest.raises(FoundationError) as exc:
        service.schema(developer, {"operation": "drop_index", "entity": "notes", "index": "by_tag", "destructive": True})
    assert exc.value.code == "DESTRUCTIVE_CONFIRMATION_REQUIRED"
    phrase = exc.value.details["required_confirmation"]
    service.schema(developer, {"operation": "drop_index", "entity": "notes", "index": "by_tag", "destructive": True, "confirmation": phrase})
    assert service.catalog(runtime)["entities"][0]["unique_keys"] == []


def test_service_non_developer_create_index_is_forbidden(service):
    """Developer authority is still required for schema operations,
    unaffected by the gate's removal (`bind_schema_operation`'s own
    authority check, not the removed gate, is what enforces this)."""
    runtime = service.authenticate("cred-a.secret-a")
    with pytest.raises(FoundationError) as exc:
        service.schema(runtime, {"operation": "create_index", "entity": "notes", "index": "by_body", "fields": ["body"]})
    assert exc.value.code == "FORBIDDEN"


def test_service_schema_field_type_executes(service):
    developer = service.authenticate("dev-a.dev-secret-a")
    assert service.schema(developer, {"operation": "add_field", "entity": "notes", "field": "n", "field_type": "integer"}).revision == 1
    runtime = service.authenticate("cred-a.secret-a")
    service.mutate(runtime, "notes", [{"operation": "update", "where": [{"field": "id", "operator": "eq", "value": 1}], "values": {"n": 5}}])
    assert service.query(runtime, "notes", select=["n"]) == [{"n": 5}]
    with pytest.raises(FoundationError) as exc:
        service.mutate(runtime, "notes", [{"operation": "update", "where": [{"field": "id", "operator": "eq", "value": 1}], "values": {"n": "not-an-int"}}])
    assert exc.value.code == "VALIDATION_FAILED"


# ==========================================================================
# CCR-13 WP-4/WP-5b: `order_by`/cursor pagination delegated through
# `DataService.query`/`query_page`.
# ==========================================================================


def test_service_query_order_by_sorts_and_query_page_reports_pagination(service):
    runtime = service.authenticate("cred-a.secret-a")
    service.mutate(runtime, "notes", [{"operation": "insert", "values": {"body": "z"}}, {"operation": "insert", "values": {"body": "m"}}])

    ascending = service.query(runtime, "notes", select=["body"], order_by=[{"field": "body", "direction": "asc"}])
    assert ascending == [{"body": "a"}, {"body": "m"}, {"body": "z"}]

    # `query_page` (the shape `http.post_query` actually uses) reports a
    # real `next_page` when more rows remain, and `None` on the last page.
    first = service.query_page(runtime, "notes", select=["id"], order_by=[{"field": "id", "direction": "asc"}], page_size=2)
    assert first.items == [{"id": 1}, {"id": 2}]
    assert first.next_page is not None
    second = service.query_page(runtime, "notes", select=["id"], order_by=[{"field": "id", "direction": "asc"}], page_size=2, cursor=first.next_page)
    assert second.items == [{"id": 3}]
    assert second.next_page is None


def test_service_query_cursor_from_a_different_entity_is_rejected(service):
    runtime = service.authenticate("cred-a.secret-a")
    developer = service.authenticate("dev-a.dev-secret-a")
    service.schema(developer, {"operation": "create_entity", "entity": "widgets", "fields": ["name"]})
    service.mutate(runtime, "notes", [{"operation": "insert", "values": {"body": "z"}}])

    page = service.query_page(runtime, "notes", select=["id"], order_by=[{"field": "id", "direction": "asc"}], page_size=1)
    assert page.next_page is not None
    with pytest.raises(FoundationError) as exc:
        service.query_page(runtime, "widgets", select=["name"], order_by=[{"field": "id", "direction": "asc"}], page_size=1, cursor=page.next_page)
    assert exc.value.code == "VALIDATION_FAILED"


def test_service_query_matches_filter_combines_with_order_by(service):
    """WP-5b: `matches` and `order_by`/cursor are all reachable through the
    same facade call now -- previously (WP-4) this combination would have
    hit the (now-removed) `matches` gate even though `order_by` itself was
    already open."""
    runtime = service.authenticate("cred-a.secret-a")
    service.mutate(runtime, "notes", [{"operation": "insert", "values": {"body": "another"}}])
    items = service.query(runtime, "notes", select=["body"], where=[{"field": "body", "operator": "matches", "value": "a%"}], order_by=[{"field": "id", "direction": "asc"}])
    assert items == [{"body": "a"}, {"body": "another"}]
