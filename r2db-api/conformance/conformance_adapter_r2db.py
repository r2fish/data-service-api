"""r2db-api plug for the common conformance port.

Module name matters here: `conformance-tests/registry.json` declares this
peer's module as `conformance_adapter_r2db`, and
`conformance-tests/conftest.py` discovers it by adding this file's
directory to `sys.path` and calling
`importlib.import_module("conformance_adapter_r2db")` -- a plain name
lookup, not a path load -- so this file must keep this exact basename.

This module owns the connection between the common port
(`conformance-tests/adapter.py`, importable as top-level module `adapter`,
NORMATIVE per docs/design/CONFORMANCE_ADAPTER_V1.md section 4) and this
peer's own foundation. It does not redefine or reinterpret the port's value
types or ABC signatures; it only implements them against `r2db_api`.

Synthetic values only: application ids, credential ids and secrets used
here are conformance-suite fixtures, never real deployment values (CLAUDE.md
Public Repository Security Gate).
"""
from __future__ import annotations

import os
import sys
import uuid
from dataclasses import replace
from typing import Any, Callable, Mapping, Sequence

# The common port lives at conformance-tests/adapter.py. When the combined
# suite runs from the repository root (root pyproject.toml pythonpath,
# or conftest.py's own top-level `from adapter import ConformanceAdapter`
# which runs before any peer conformance/ directory is added to sys.path),
# `import adapter` already resolves there and is cached in sys.modules.
# This fallback only matters when this file is loaded standalone (e.g. a
# direct file load for local exercising of this adapter alone).
if "adapter" not in sys.modules:
    _conformance_tests = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "conformance-tests")
    )
    if os.path.isdir(_conformance_tests) and _conformance_tests not in sys.path:
        sys.path.insert(0, _conformance_tests)

from adapter import (  # noqa: E402
    UNCLASSIFIED,
    VALID_CONFIRMATION,
    ConformanceAdapter,
    ConformanceDenial,
    CredentialHandle,
    Fixture,
    PayloadNotExpressible,
    ScopeView,
    TamperVector,
)

from r2db_api import ControlAuthority, CredentialStore, DataService  # noqa: E402
from r2db_api.errors import FoundationError  # noqa: E402


class R2DBConformanceAdapter(ConformanceAdapter):
    """Connects the common conformance port to the r2db-api foundation.

    A "session" for this peer is an `AuthContext`. Control-plane operations
    go through `ControlAuthority`, which is never reachable from the
    application-facing `DataService` surface (see r2db_api.topology).
    """

    name = "r2db-api"

    def __init__(self) -> None:
        # Synthetic pepper for this conformance run only; never a real
        # deployment secret and never read from the environment.
        self._credentials = CredentialStore(pepper="synthetic-conformance-pepper-r2db-0000")
        self._service = DataService(self._credentials)
        self._control = ControlAuthority(self._service)
        self._counter = 0

    # ------------------------------------------------------------------
    # control plane
    # ------------------------------------------------------------------
    def provision_application(self, application_id: str) -> None:
        self._control.register_application(application_id, entities={})

    def issue_credential(self, application_id: str, role: str) -> CredentialHandle:
        self._counter += 1
        credential_id = f"conf-cred-{application_id}-{role}-{self._counter}"
        secret = f"conf-secret-{self._counter}-{uuid.uuid4().hex}"
        self._control.issue_credential(credential_id, application_id, role, secret)
        return CredentialHandle(credential_ref=credential_id, application_id=application_id, role=role, secret=secret)

    def revoke_credential(self, handle: CredentialHandle) -> None:
        self._control.set_credential_state(handle.credential_ref, revoked=True)

    def disable_application(self, application_id: str) -> None:
        self._control.set_application_enabled(application_id, enabled=False)

    def enable_application(self, application_id: str) -> None:
        self._control.set_application_enabled(application_id, enabled=True)

    def set_authorization_state_available(self, available: bool) -> None:
        self._control.set_authorization_state_available(available)

    def propagation_bound_ms(self) -> int:
        # DataService._check() calls CredentialStore.assert_active() on
        # every single application-plane operation (see service.py _slot /
        # _check); there is no cached/derived authorization state, so
        # revoke/disable/state-unavailable propagation is synchronous.
        return 0

    def capability_document(self) -> Mapping[str, Any]:
        # `DataService.capabilities()` is scoped to an authenticated
        # session (contract `endpoints.capabilities.auth`: "application or
        # control"), so this provisions a disposable application/credential
        # solely to obtain the peer's own real capability document -- it
        # does not fabricate one in the adapter.
        self._counter += 1
        probe_app = f"conf_capability_probe_{self._counter}_{uuid.uuid4().hex[:8]}"
        self.provision_application(probe_app)
        handle = self.issue_credential(probe_app, "runtime")
        session = self.authenticate(handle)
        return self._call(lambda: self._service.capabilities(session))

    # ------------------------------------------------------------------
    # application plane
    # ------------------------------------------------------------------
    def authenticate(self, handle: CredentialHandle) -> object:
        return self._call(lambda: self._service.authenticate(handle.secret))

    def scope_of(self, session: object) -> ScopeView:
        return ScopeView(application_id=session.application_id, role=session.role)

    def create_entity(self, session, entity: str, fields: Mapping[str, str]) -> None:
        self._call(lambda: self._service.schema(
            session, {"operation": "create_entity", "entity": entity, "fields": list(fields.keys())}
        ))

    def insert(self, session, entity: str, values: Mapping[str, Any]) -> None:
        self._call(lambda: self._service.mutate(
            session, entity, [{"operation": "insert", "values": dict(values)}]
        ))

    def select_eq(self, session, entity: str, select: Sequence[str], field: str | None, value: Any) -> list[dict]:
        where = [{"field": field, "operator": "eq", "value": value}] if field is not None else None
        return self._call(lambda: self._service.query(session, entity, select=list(select), where=where))

    def delete(self, session, entity: str, field: str, value: Any, *, destructive: bool, confirmation: str | None) -> int:
        # VALID_CONFIRMATION sentinel protocol (design section 10.1):
        # `destructive` always passes through faithfully; `confirmation`
        # None means "supply nothing", VALID_CONFIRMATION means "supply
        # this peer's own required token" ("DELETE" for r2db-api), and any
        # other string passes through verbatim so a wrong token is still
        # observable as a wrong token to this peer's own validation.
        peer_confirmation = "DELETE" if confirmation is VALID_CONFIRMATION else confirmation
        operation: dict[str, Any] = {
            "operation": "delete",
            "where": [{"field": field, "operator": "eq", "value": value}],
            "destructive": destructive,
        }
        if peer_confirmation is not None:
            operation["confirmation"] = peer_confirmation
        return self._call(lambda: self._service.mutate(session, entity, [operation]))

    def count(self, session, entity: str) -> int:
        def op() -> int:
            canonical = self._service._check(session)
            cell = self._service._cells.get(canonical.application_id)
            return len(cell.entities.get(entity, [])) if cell is not None else 0
        return self._call(op)

    def entities(self, session) -> set[str]:
        # Uses the peer's public catalog operation. This previously reached
        # into DataService's private cell map because no public catalog
        # existed -- an adapter compensating for a peer gap, which design
        # section 10.5 forbids. DataService.catalog() now exists, so the
        # adapter observes the peer the way an application caller does.
        def op() -> set[str]:
            document = self._service.catalog(session)
            return {item["entity"] for item in document["entities"]}
        return self._call(op)

    # ------------------------------------------------------------------
    # attack-surface declarations
    # ------------------------------------------------------------------
    def native_command_surface(self) -> None:
        return None

    def public_operation_callables(self) -> Sequence[Callable]:
        # The genuine application-facing surface: everything an
        # authenticated application credential can reach through
        # DataService. ControlAuthority is deliberately excluded; it is a
        # separate, non-application-facing authority (topology.py).
        return [
            self._service.authenticate,
            self._service.capabilities,
            self._service.query,
            self._service.mutate,
            self._service.schema,
        ]

    def tamper_vectors(self, fixture: Fixture) -> Sequence[TamperVector]:
        session_a = fixture.runtime_a

        def forged_scope_attempt() -> None:
            # Same credential id, application_id renamed to the other
            # application: exactly the r2db-specific guidance in the task
            # brief and the scenario r2db-api/tests/test_foundation.py
            # already exercises for its own suite.
            forged = replace(session_a, application_id=fixture.app_b)
            self._call(lambda: self._service.query(forged, fixture.shared_entity, select=["id"]))

        def role_elevation_attempt() -> None:
            # Same credential id, role self-declared as "developer" while
            # the backing credential is actually "runtime".
            forged = replace(session_a, role="developer")
            self._call(lambda: self._service.schema(
                forged, {"operation": "create_entity", "entity": "conf_role_elevation_probe", "fields": ["id"]}
            ))

        def request_field_scope_attempt() -> None:
            # A legitimate, untampered session, but the request body itself
            # carries a smuggled scope-looking field. The mutation shape
            # validator rejects any key outside its known operation shape.
            operation = {"operation": "insert", "values": {"id": 999}, "application_id": fixture.app_b}
            self._call(lambda: self._service.mutate(session_a, fixture.shared_entity, [operation]))

        def cross_application_handle_attempt() -> None:
            # A legitimate, untampered session for A reaching straight for
            # an entity that only exists in B's cell.
            self._call(lambda: self._service.query(session_a, fixture.b_only_entity, select=["id"]))

        return [
            TamperVector(
                kind="forged_scope_object",
                name="r2db_forged_application_id_on_auth_context",
                disposition="must_deny",
                attempt=forged_scope_attempt,
            ),
            TamperVector(
                kind="role_elevation",
                name="r2db_forged_developer_role_on_auth_context",
                disposition="must_deny",
                attempt=role_elevation_attempt,
            ),
            TamperVector(
                kind="request_field_scope",
                name="r2db_smuggled_application_id_in_mutation_body",
                disposition="must_deny",
                attempt=request_field_scope_attempt,
            ),
            TamperVector(
                kind="cross_application_handle",
                name="r2db_runtime_a_reaches_b_only_entity",
                disposition="must_deny",
                attempt=cross_application_handle_attempt,
            ),
        ]

    def identifier_positions(self, fixture: Fixture) -> Mapping[str, Callable[[Any], Any]]:
        runtime_a = fixture.runtime_a
        developer_a = fixture.developer_a

        def entity_probe(payload: Any) -> Any:
            return self._call(lambda: self._service.query(runtime_a, payload, select=["id"]))

        def select_field_probe(payload: Any) -> Any:
            return self._call(lambda: self._service.query(runtime_a, fixture.shared_entity, select=[payload]))

        def filter_field_probe(payload: Any) -> Any:
            return self._call(lambda: self._service.query(
                runtime_a, fixture.shared_entity, select=["id"],
                where=[{"field": payload, "operator": "eq", "value": 1}],
            ))

        def insert_field_probe(payload: Any) -> Any:
            # `payload` becomes a dict key here; an unhashable NON_STRING
            # payload (e.g. [], {}) cannot even be placed at this position --
            # the request can't be constructed, so this is a harness-level
            # impossibility, not an observation of this peer's validation
            # (design section 10.3).
            try:
                hash(payload)
            except TypeError as exc:
                raise PayloadNotExpressible(
                    "insert_field", payload, "payload is unhashable and this position is a mapping key"
                ) from exc
            return self._call(lambda: self._service.mutate(
                runtime_a, fixture.shared_entity, [{"operation": "insert", "values": {payload: "x"}}]
            ))

        def schema_entity_probe(payload: Any) -> Any:
            return self._call(lambda: self._service.schema(
                developer_a, {"operation": "create_entity", "entity": payload, "fields": ["id"]}
            ))

        def schema_field_probe(payload: Any) -> Any:
            return self._call(lambda: self._service.schema(
                developer_a, {"operation": "add_field", "entity": fixture.shared_entity, "field": payload}
            ))

        return {
            "entity": entity_probe,
            "select_field": select_field_probe,
            "filter_field": filter_field_probe,
            "insert_field": insert_field_probe,
            "schema_entity": schema_entity_probe,
            "schema_field": schema_field_probe,
        }

    def value_positions(self, fixture: Fixture) -> Mapping[str, Callable[[Any], Any]]:
        # Round-tripping a value payload means genuinely writing a row into
        # shared_entity itself. That is intentional: C-03's structural
        # integrity check (design section 5.2 item 5) only requires the
        # *identifier* corpus to leave shared_entity's row count untouched;
        # the value corpus is expected to grow it as proof of a successful,
        # safely-bound write (only the entity *set* must stay stable across
        # the value corpus too).
        runtime_a = fixture.runtime_a
        entity = fixture.shared_entity

        def insert_value_probe(payload: Any) -> Any:
            def op() -> Any:
                marker = f"probe-{uuid.uuid4().hex}"
                self._service.mutate(runtime_a, entity, [
                    {"operation": "insert", "values": {"probe_key": marker, "probe_value": payload}}
                ])
                rows = self._service.query(
                    runtime_a, entity, select=["probe_value"],
                    where=[{"field": "probe_key", "operator": "eq", "value": marker}],
                )
                return rows[0]["probe_value"] if rows else None
            return self._call(op)

        def filter_value_probe(payload: Any) -> Any:
            def op() -> Any:
                marker = f"probe-{uuid.uuid4().hex}"
                self._service.mutate(runtime_a, entity, [
                    {"operation": "insert", "values": {"probe_key": marker, "probe_value": payload}}
                ])
                rows = self._service.query(
                    runtime_a, entity, select=["probe_value"],
                    where=[
                        {"field": "probe_key", "operator": "eq", "value": marker},
                        {"field": "probe_value", "operator": "eq", "value": payload},
                    ],
                )
                return rows[0]["probe_value"] if rows else None
            return self._call(op)

        return {
            "insert_value": insert_value_probe,
            "filter_value": filter_value_probe,
        }

    # ------------------------------------------------------------------
    # normalization
    # ------------------------------------------------------------------
    def classify(self, exc: BaseException) -> str:
        if isinstance(exc, FoundationError):
            return exc.code
        # A native, non-FoundationError failure is not a denial this
        # adapter can vouch for as a rejection -- laundering it into a
        # plausible-looking contract code would hide a peer crash behind a
        # passing test (design section 10.2). Report it as unclassified so
        # the suite's code-membership check fails loudly instead.
        return UNCLASSIFIED

    # ------------------------------------------------------------------
    # construction
    # ------------------------------------------------------------------
    def build_fixture(self) -> Fixture:
        # conftest.py's `adapter` fixture is session-scoped but `fx` (which
        # calls this method) is function-scoped, so build_fixture() runs
        # once per test function against the same long-lived adapter
        # instance. Application ids must therefore be fresh on every call,
        # not fixed literals, or the second call's provision_application()
        # collides with the first (CONFLICT).
        self._counter += 1
        suffix = f"{self._counter}_{uuid.uuid4().hex[:8]}"
        app_a, app_b = f"conf_app_a_{suffix}", f"conf_app_b_{suffix}"
        self.provision_application(app_a)
        self.provision_application(app_b)

        fields = {"id": "integer", "label": "text", "probe_key": "text", "probe_value": "text"}
        shared_entity = "shared_items"
        a_only_entity = "a_only_items"
        b_only_entity = "b_only_items"

        dev_a_handle = self.issue_credential(app_a, "developer")
        dev_b_handle = self.issue_credential(app_b, "developer")
        developer_a = self.authenticate(dev_a_handle)
        developer_b = self.authenticate(dev_b_handle)

        self.create_entity(developer_a, shared_entity, fields)
        self.create_entity(developer_a, a_only_entity, fields)
        self.create_entity(developer_b, shared_entity, fields)
        self.create_entity(developer_b, b_only_entity, fields)

        self.insert(developer_a, shared_entity, {"id": 1, "label": "seed-a", "probe_key": "seed", "probe_value": "seed-a"})
        self.insert(developer_b, shared_entity, {"id": 1, "label": "seed-b", "probe_key": "seed", "probe_value": "seed-b"})
        self.insert(developer_a, a_only_entity, {"id": 1, "label": "a-only", "probe_key": "seed", "probe_value": "a-only"})
        self.insert(developer_b, b_only_entity, {"id": 1, "label": "b-only", "probe_key": "seed", "probe_value": "b-only"})

        runtime_a_handle = self.issue_credential(app_a, "runtime")
        runtime_b_handle = self.issue_credential(app_b, "runtime")
        runtime_a = self.authenticate(runtime_a_handle)
        runtime_b = self.authenticate(runtime_b_handle)

        return Fixture(
            adapter=self,
            app_a=app_a,
            app_b=app_b,
            runtime_a=runtime_a,
            developer_a=developer_a,
            runtime_b=runtime_b,
            shared_entity=shared_entity,
            a_only_entity=a_only_entity,
            b_only_entity=b_only_entity,
        )

    def close(self) -> None:
        # In-memory-only foundation; nothing external to release.
        pass

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------
    def _call(self, fn: Callable[[], Any]) -> Any:
        try:
            return fn()
        except FoundationError as exc:
            raise self._deny(exc) from exc
        except (TypeError, ValueError) as exc:
            raise self._deny(exc) from exc

    def _deny(self, exc: BaseException) -> ConformanceDenial:
        return ConformanceDenial(code=self.classify(exc), adapter=self.name, native_type=type(exc).__name__)


def build_adapter() -> ConformanceAdapter:
    return R2DBConformanceAdapter()
