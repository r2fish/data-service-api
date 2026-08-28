"""MitateDB-api plug for the common conformance port.

Module name matters here: `conformance-tests/registry.json` declares this
peer's module as `conformance_adapter_mitatedb`, and
`conformance-tests/conftest.py` discovers it by adding this file's
directory to `sys.path` and calling
`importlib.import_module("conformance_adapter_mitatedb")` -- a plain name
lookup, not a path load -- so this file must keep this exact basename.

This module owns the connection between the common port
(`conformance-tests/adapter.py`, importable as top-level module `adapter`,
NORMATIVE per docs/design/CONFORMANCE_ADAPTER_V1.md section 4) and this
peer's own foundation. It does not redefine or reinterpret the port's value
types or ABC signatures; it only implements them against `mitatedb_api`.

Synthetic values only: application ids, credential ids and secrets used
here are conformance-suite fixtures, never real deployment values (CLAUDE.md
Public Repository Security Gate). Identifiers are kept lowercase
(`^[a-z][a-z0-9_]{0,62}$`) per this peer's stricter catalog policy and per
design doc section 4.2 / section 8 finding 2.
"""
from __future__ import annotations

import os
import sqlite3
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
    CATALOG_SURFACE_ABSENT,
    UNCLASSIFIED,
    VALID_CONFIRMATION,
    BatchOperation,
    ConformanceAdapter,
    ConformanceDenial,
    CredentialHandle,
    Fixture,
    PayloadNotExpressible,
    ScopeView,
    SurfaceAbsent,
    TamperVector,
)

from mitatedb_api import ControlPlane, Filter, MitateDataService, Role  # noqa: E402
from mitatedb_api.cell import ApplicationDeveloper, ApplicationRuntime  # noqa: E402
from mitatedb_api.errors import (  # noqa: E402
    AuthenticationError,
    AuthorizationError,
    AuthorizationStateUnavailable,
    CapabilityError,
    ConflictError,
    FoundationError,
    NotFoundError,
    ResourceLimitError,
    ValidationError,
)
from mitatedb_api.service import MitateDataService as _MitateDataServiceClass  # noqa: E402,F401

_CLASSIFY_ORDER = (
    (AuthorizationStateUnavailable, "AUTH_STATE_UNAVAILABLE"),
    (AuthenticationError, "AUTH_INVALID"),
    (AuthorizationError, "FORBIDDEN"),
    (CapabilityError, "CAPABILITY_UNSUPPORTED"),
    (ValidationError, "VALIDATION_FAILED"),
    (ResourceLimitError, "LIMIT_EXCEEDED"),
    (ConflictError, "CONFLICT"),
    (NotFoundError, "NOT_FOUND"),
)


class MitateDBConformanceAdapter(ConformanceAdapter):
    """Connects the common conformance port to the MitateDB-api foundation.

    A "session" for this peer is an `ApplicationRuntime` /
    `ApplicationDeveloper`. Control-plane operations go through
    `ControlPlane`, which a session object has no way to reach (cell.py
    sessions only ever hold a cell handle and a Principal).
    """

    name = "MitateDB-api"

    def __init__(self) -> None:
        # Synthetic pepper for this conformance run only; never a real
        # deployment secret and never read from the environment.
        self._control = ControlPlane("synthetic-conformance-pepper-mitatedb-0000000")
        self._service = MitateDataService(self._control)
        self._counter = 0

    # ------------------------------------------------------------------
    # control plane
    # ------------------------------------------------------------------
    def provision_application(self, application_id: str) -> None:
        self._control.provision_application(application_id)

    def issue_credential(self, application_id: str, role: str) -> CredentialHandle:
        role_enum = role if isinstance(role, Role) else Role(role)
        credential_id, secret = self._control.issue_credential(application_id, role_enum)
        return CredentialHandle(credential_ref=credential_id, application_id=application_id, role=role_enum.value, secret=secret)

    def revoke_credential(self, handle: CredentialHandle) -> None:
        self._control.revoke_credential(handle.credential_ref)

    def disable_application(self, application_id: str) -> None:
        self._control.disable_application(application_id)

    def enable_application(self, application_id: str) -> None:
        # ControlPlane exposes no facade method for this (see
        # service.py); the credential store itself does.
        self._control.credentials.enable_application(application_id)

    def set_authorization_state_available(self, available: bool) -> None:
        self._control.credentials.authorization_state_available = bool(available)

    def propagation_bound_ms(self) -> int:
        # CredentialStore.assert_active() is invoked by the session's guard
        # on every single operation (cell.py ApplicationRuntime.__authorize),
        # re-checking enabled/revoked/disabled/expiry state each time. There
        # is no cache, so propagation is synchronous.
        return 0

    def capability_document(self) -> Mapping[str, Any]:
        # `ApplicationRuntime.capabilities()` is scoped to an authenticated
        # session (contract `endpoints.capabilities.auth`: "application or
        # control"), so this provisions a disposable application/credential
        # solely to obtain the peer's own real capability document -- it
        # does not fabricate one in the adapter.
        self._counter += 1
        probe_app = f"conf_capability_probe_{self._counter}_{uuid.uuid4().hex[:8]}"
        self.provision_application(probe_app)
        handle = self.issue_credential(probe_app, "runtime")
        session = self.authenticate(handle)
        return self._call(lambda: session.capabilities())

    # ------------------------------------------------------------------
    # application plane
    # ------------------------------------------------------------------
    def authenticate(self, handle: CredentialHandle) -> object:
        return self._call(lambda: self._service.open_session(handle.credential_ref, handle.secret))

    def scope_of(self, session: object) -> ScopeView:
        principal = session.principal
        role_value = principal.role.value if isinstance(principal.role, Role) else principal.role
        return ScopeView(application_id=principal.application_id, role=role_value)

    def create_entity(self, session, entity: str, fields: Mapping[str, str]) -> None:
        def op() -> None:
            if not hasattr(session, "create_collection"):
                # A runtime session genuinely has no schema-mutation method;
                # this is the same authority boundary the real developer
                # path enforces (cell.py _require_developer), spelled out
                # explicitly rather than relying on AttributeError.
                raise AuthorizationError("developer authority required")
            session.create_collection(entity, dict(fields))
        self._call(op)

    def insert(self, session, entity: str, values: Mapping[str, Any]) -> None:
        self._call(lambda: session.insert(entity, dict(values)))

    def select_eq(self, session, entity: str, select: Sequence[str], field: str | None, value: Any) -> list[dict]:
        filters = [Filter(field, "eq", value)] if field is not None else None
        return self._call(lambda: session.read(entity, fields=list(select), filters=filters))

    def attempt_filter(
        self, session, entity: str, select: Sequence[str], field: str, operator: str, value: Any
    ) -> list[dict]:
        # Same real `session.read()` entry point `select_eq` above already
        # uses, generalized to an arbitrary operator -- an operator this
        # peer does not implement (`contains`/`matches`/`is_null`, all
        # declared `unsupported` in its own `structured_query` capability
        # entry) is presented here exactly as a real client attempting it
        # would be, and whatever `cell.py::_where` itself produces is
        # returned, never fabricated.
        filters = [Filter(field, operator, value)]
        return self._call(lambda: session.read(entity, fields=list(select), filters=filters))

    def delete(self, session, entity: str, field: str, value: Any, *, destructive: bool, confirmation: str | None) -> int:
        # VALID_CONFIRMATION sentinel protocol (design section 10.1):
        # `confirmation=None` supplies no confirmation (this peer's
        # `confirm` stays falsy), VALID_CONFIRMATION supplies this peer's
        # own required token (its boolean `confirm=True`), and any other
        # string passes through verbatim so a wrong token is still
        # observable to this peer's own validation rather than silently
        # upgraded. This peer's `delete()` has no separate `destructive`
        # parameter -- deletion is unconditionally destructive and gated
        # by `confirm` alone -- so there is nothing further for the port's
        # `destructive` flag to faithfully pass through to here.
        if confirmation is VALID_CONFIRMATION:
            peer_confirm: Any = True
        elif confirmation is None:
            peer_confirm = False
        else:
            peer_confirm = confirmation
        filters = [Filter(field, "eq", value)]

        def op() -> int:
            result = session.delete(entity, filters, confirm=peer_confirm)
            return result["deleted"]
        return self._call(op)

    def count(self, session, entity: str) -> int:
        # session.read() already re-checks authorization on every call
        # (cell.py ApplicationRuntime.__authorize -> assert_active), so a
        # revoked/disabled/unavailable session correctly denies here too.
        return self._call(lambda: len(session.read(entity)))

    def entities(self, session) -> set[str]:
        # There is no public "list collections" operation on this peer
        # (cell.py exposes create/insert/read/update/delete/transact only),
        # so this reaches into the cell's own storage handle for the actual
        # listing -- but only after an explicit assert_active() call, so a
        # revoked/disabled/unavailable session is denied here exactly as it
        # would be for any other session operation, instead of silently
        # reading internal state past the authorization boundary.
        def op() -> set[str]:
            principal = session.principal
            self._control.credentials.assert_active(principal)
            cell = self._control.cells.get(principal.application_id)
            if cell is None:
                return set()
            rows = cell._db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
            return {row["name"] for row in rows}
        return self._call(op)

    def catalog_document(self, session) -> str:
        # There is no public "list collections"/catalog operation anywhere
        # on this peer's surface (cell.py exposes create_collection/insert/
        # read/update/delete/transact only -- confirmed by source
        # inspection, and `capabilities()` itself declares
        # `application_catalog: unavailable`, cell.py's own comment: "No
        # public 'list collections' operation exists on this peer"). This
        # is a structural absence, not a denial this adapter observed from
        # a real call, so per the port's contract this returns the
        # sentinel rather than assembling a `CatalogDocument`-shaped dict
        # out of `entities()`'s own internal sqlite_master reach-around
        # (which exists only to serve this adapter's own `entities()`
        # port method, not as a peer-provided discovery surface an
        # application caller could reach).
        return CATALOG_SURFACE_ABSENT

    def _attempt_mutation_outcome(
        self,
        session,
        entity: str,
        operation: str,
        *,
        values: Mapping[str, Any] | None,
        where_field: str | None,
        where_value: Any,
        expected_revision: str | None,
        unique_key: str | None,
    ) -> int:
        filters = [Filter(where_field, "eq", where_value)] if where_field is not None else None

        if expected_revision is not None or unique_key is not None:
            # Conformance-review finding (correction B-2): this is a real,
            # present entry point for a revision precondition (and, port
            # v1.3, for `unique_key`), not a structural absence.
            # `ApplicationRuntime.transact`/`ApplicationCell.transact`
            # already accepts an arbitrary operation-dict shape (exactly
            # what the `upsert` branch below relies on) -- so either extra
            # key is presented as a real field on that dict, exactly as a
            # real client attempting the contract's vocabulary would, and
            # this adapter returns whatever `transact()` itself produces.
            # An earlier revision of this method instead raised
            # `SurfaceAbsent` for `expected_revision` on the strength of
            # `session.insert`/`.update`/`.delete` alone having no such
            # parameter -- but `transact()` is a real, present dispatcher
            # those three dedicated methods do not exhaust, and (before
            # `cell.py` was fixed) it silently ignored this exact key on an
            # "insert" operation, committing the row with the precondition
            # never even inspected. That was the real non-conformance C-18
            # exists to catch; declaring it `SurfaceAbsent` would have
            # hidden it behind a fabricated claim of absence, which design
            # principle 4 forbids as surely as fabricating a denial does.
            # This peer has no uniqueness-key concept at all, so a real
            # `unique_key` value here is expected to be refused (there is
            # no declared key it could ever name) -- but that refusal must
            # still come from presenting it to this real dispatcher, not
            # from this adapter deciding the answer itself.
            item: dict[str, Any] = {"type": operation, "collection": entity, "values": dict(values or {})}
            if expected_revision is not None:
                item["expected_revision"] = expected_revision
            if unique_key is not None:
                item["unique_key"] = unique_key
            if filters is not None:
                item["filters"] = filters

            def dispatched_op() -> int:
                results = session.transact([item])
                return len(results)
            return self._call(dispatched_op)

        if operation == "insert":
            def insert_op() -> int:
                session.insert(entity, dict(values or {}))
                return 1
            return self._call(insert_op)

        if operation == "update":
            def update_op() -> int:
                if filters is None:
                    raise ValidationError("update requires a non-empty filter")
                result = session.update(entity, dict(values or {}), filters)
                return result["updated"]
            return self._call(update_op)

        if operation == "delete":
            def delete_op() -> int:
                if filters is None:
                    raise ValidationError("delete requires a non-empty filter")
                result = session.delete(entity, filters, confirm=True)
                return result["deleted"]
            return self._call(delete_op)

        if operation == "upsert":
            # There is no dedicated `upsert` method anywhere on this peer,
            # but `ApplicationRuntime.transact`/`ApplicationCell.transact`
            # *is* a real, present operation dispatcher that accepts an
            # arbitrary `"type"` string -- so this presents `"upsert"` to
            # it exactly as a real client attempting the contract's
            # `upsert` vocabulary would (review finding: an adapter that
            # denies this without ever presenting it to the peer hides
            # whatever the peer's own dispatcher actually does with it,
            # which is precisely what C-12 exists to observe. See `cell.
            # py::transact` / `errors.CapabilityError` for this peer's own
            # real answer).
            def upsert_op() -> int:
                results = session.transact([
                    {"type": "upsert", "collection": entity, "values": dict(values or {})}
                ])
                return len(results)
            return self._call(upsert_op)

        # Any other operation name is outside the common contract's
        # mutation vocabulary entirely (insert/update/upsert/delete);
        # there is no peer call this adapter could present it to that
        # would mean anything.
        raise ConformanceDenial(code="CAPABILITY_UNSUPPORTED", adapter=self.name, native_type="")

    def attempt_mutation(
        self,
        session,
        entity: str,
        operation: str,
        *,
        values: Mapping[str, Any] | None,
        where_field: str | None,
        where_value: Any,
        expected_revision: str | None = None,
        unique_key: str | None = None,
    ) -> int:
        return self._attempt_mutation_outcome(
            session, entity, operation, values=values, where_field=where_field, where_value=where_value,
            expected_revision=expected_revision, unique_key=unique_key,
        )

    def attempt_mutation_with_addresses(
        self,
        session,
        entity: str,
        operation: str,
        *,
        values: Mapping[str, Any] | None,
        where_field: str | None,
        where_value: Any,
        expected_revision: str | None = None,
        unique_key: str | None = None,
    ) -> tuple[int, list[Mapping[str, Any]] | None]:
        affected = self._attempt_mutation_outcome(
            session, entity, operation, values=values, where_field=where_field, where_value=where_value,
            expected_revision=expected_revision, unique_key=unique_key,
        )
        # None, always: none of `session.insert`/`.update`/`.delete`/
        # `.transact`'s real return shapes (`{"rowid": ...}`, `{"updated":
        # ...}`, `{"deleted": ...}`, a results list) carry anything shaped
        # like the contract's `assigned_addresses` -- consistent with this
        # peer declaring `row_addressability: unavailable`. `insert()`'s
        # own `rowid` is a SQLite-internal artifact, not a published
        # address; synthesizing `[{"address": {"rowid": ...}}]` from it
        # would be this adapter fabricating an addressability concept the
        # peer itself does not declare or publish to a real caller.
        return affected, None

    def attempt_batch_with_addresses(
        self, session, entity: str, operations: Sequence[BatchOperation]
    ) -> tuple[int, list[Mapping[str, Any]] | None]:
        # `ApplicationRuntime.transact`/`ApplicationCell.transact` is the
        # *only* real multi-operation atomic dispatcher this peer has --
        # there is no other call that could receive more than one operation
        # at once -- so every operation in the batch is presented to it
        # together, in one real call, exactly as `_attempt_mutation_
        # outcome`'s own `expected_revision`/`unique_key` branch already
        # does for a single operation. This peer's `transact()` only ever
        # truly executes a `"insert"` item; every other type in the same
        # vocabulary (`update`/`delete`/`upsert`) is refused with
        # `CapabilityError` regardless of what else is in the batch
        # (`cell.py`'s own op-type dispatch) -- so a real mixed batch
        # (insert alongside update/delete) is genuinely refused here, never
        # silently split into several single-operation calls this adapter
        # stitches together itself, which would prove nothing real about
        # this peer's own (lack of) batch-mixing support.
        items: list[dict[str, Any]] = []
        for op in operations:
            item: dict[str, Any] = {"type": op.operation, "collection": entity, "values": dict(op.values or {})}
            if op.expected_revision is not None:
                item["expected_revision"] = op.expected_revision
            if op.unique_key is not None:
                item["unique_key"] = op.unique_key
            if op.where_field is not None:
                item["filters"] = [Filter(op.where_field, "eq", op.where_value)]
            if op.destructive:
                item["destructive"] = True
                if op.confirmation is VALID_CONFIRMATION:
                    item["confirm"] = True
                elif op.confirmation is not None:
                    item["confirm"] = op.confirmation
            items.append(item)

        def op() -> int:
            results = session.transact(items)
            return len(results)
        affected = self._call(op)
        return affected, None

    def create_unique_index(self, session, entity: str, index: str, fields: Sequence[str]) -> None:
        # `session` is unavailable-regardless of *any* session (the answer
        # is peer-wide, not session-scoped), kept only to match this ABC
        # method's signature -- the same convention `catalog_document`
        # above already follows for its own unused `session` parameter.
        # `entity`/`index`/`fields` are named in the raised exception's
        # `reason` immediately below rather than left unused: a caller
        # debugging why a *specific* index attempt reported "absent" can
        # see what was actually asked for, not just that something was.
        #
        # `ApplicationDeveloper.create_collection(name, fields)` is this
        # peer's only schema-mutation call, and it has no parameter for
        # indexes of any kind -- unlike `r2db-api`'s single generic
        # `schema()` dispatcher, there is no entry point on this peer's
        # public surface (confirmed by source inspection of cell.py: no
        # other developer-facing method exists) that could even receive an
        # index-creation request. Structurally absent, not denied -- see
        # `SurfaceAbsent`'s docstring for why this must not become a
        # fabricated `ConformanceDenial` instead.
        raise SurfaceAbsent(
            self.name, "create_unique_index",
            "ApplicationDeveloper.create_collection has no index/uniqueness parameter, and no other "
            f"schema-operation call exists on this peer (requested: entity={entity!r}, index={index!r}, "
            f"fields={list(fields)!r})",
            # This peer's entire public application-facing surface (the
            # same list `public_operation_callables()` below declares for
            # C-03's native-command-surface check), so a consumer can
            # independently verify -- via `signature_forbids_parameters` --
            # that none of it accepts an index/uniqueness-shaped parameter,
            # rather than take this claim on its word (design section 4.3 /
            # `SurfaceAbsent`'s own docstring).
            surface=self.public_operation_callables(),
            forbidden_parameters=["index", "unique"],
        )

    def query_with_revisions(
        self, session, entity: str, select: Sequence[str], field: str | None, value: Any
    ) -> tuple[list[dict], list[str] | None]:
        # `ApplicationCell.read()`'s own return type is a bare
        # `[dict(row) for row in rows]` list, not a wrapping object -- so
        # `None` here observes that real return shape having structurally
        # no slot a `revisions` key could ever occupy, the same reasoning
        # as `conformance_adapter_r2db.py`'s identical comment (contrast
        # `conformance_adapter_r2db_http.py`, whose response *is* a JSON
        # object and which inspects a real `result.get("revisions")`
        # instead of asserting `None` unlooked-at -- conformance-review
        # correction M-1).
        items = self.select_eq(session, entity, select, field, value)
        return items, None

    # ------------------------------------------------------------------
    # attack-surface declarations
    # ------------------------------------------------------------------
    def native_command_surface(self) -> None:
        return None

    def public_operation_callables(self) -> Sequence[Callable]:
        # The genuine application-facing surface: everything an
        # authenticated application credential can reach. ControlPlane is
        # deliberately excluded; a session object has no reference to it.
        return [
            _MitateDataServiceClass.open_session,
            ApplicationRuntime.insert,
            ApplicationRuntime.read,
            ApplicationRuntime.update,
            ApplicationRuntime.delete,
            ApplicationRuntime.transact,
            ApplicationDeveloper.create_collection,
        ]

    def tamper_vectors(self, fixture: Fixture) -> Sequence[TamperVector]:
        runtime_a = fixture.runtime_a

        def forged_scope_attempt() -> None:
            # Reach the target application's cell directly and construct a
            # runtime bound to a forged Principal: same (real) credential
            # id, application_id renamed to the other application. This is
            # exactly the guidance for this peer in the task brief, since
            # Principal (unlike r2db's AuthContext) is never itself handed
            # to a public method as a request argument.
            principal = runtime_a.principal
            forged_principal = replace(principal, application_id=fixture.app_b)
            target_cell = self._control.cells[fixture.app_b]

            def op() -> None:
                forged_runtime = ApplicationRuntime(target_cell, forged_principal, self._control.credentials.assert_active)
                forged_runtime.read(fixture.shared_entity)
            self._call(op)

        def role_elevation_attempt() -> None:
            # Same real runtime credential id, role self-declared as
            # developer.
            principal = runtime_a.principal
            forged_principal = replace(principal, role=Role.DEVELOPER)
            own_cell = self._control.cells[fixture.app_a]

            def op() -> None:
                forged_developer = ApplicationDeveloper(own_cell, forged_principal, self._control.credentials.assert_active)
                forged_developer.create_collection("conf_role_elevation_probe", {"id": "integer"})
            self._call(op)

        def request_field_scope_attempt() -> None:
            # A legitimate, untampered session, but the request body itself
            # carries a smuggled scope-looking field. Unknown-field
            # validation rejects it the same way it would reject any other
            # bogus column name.
            self._call(lambda: runtime_a.insert(fixture.shared_entity, {"probe_value": "x", "application_id": fixture.app_b}))

        def cross_application_handle_attempt() -> None:
            # A legitimate, untampered session for A reaching straight for
            # a collection that only exists in B's cell.
            self._call(lambda: runtime_a.read(fixture.b_only_entity))

        return [
            TamperVector(
                kind="forged_scope_object",
                name="mitatedb_forged_principal_application_id",
                disposition="must_deny",
                attempt=forged_scope_attempt,
            ),
            TamperVector(
                kind="role_elevation",
                name="mitatedb_forged_principal_developer_role",
                disposition="must_deny",
                attempt=role_elevation_attempt,
            ),
            TamperVector(
                kind="request_field_scope",
                name="mitatedb_smuggled_application_id_in_insert_values",
                disposition="must_deny",
                attempt=request_field_scope_attempt,
            ),
            TamperVector(
                kind="cross_application_handle",
                name="mitatedb_runtime_a_reaches_b_only_collection",
                disposition="must_deny",
                attempt=cross_application_handle_attempt,
            ),
        ]

    def credential_reactivation_vectors(self, handle: CredentialHandle) -> Sequence[TamperVector]:
        # `auth.py`'s `CredentialStore` has no un-revoke/enable-credential
        # call at all (`revoke()` is one-way; the only other state-mutating
        # methods that touch a credential's own row are `issue()`, which
        # always mints a brand-new `credential_id` with no parameter to
        # force reuse of an existing one). The one real control-plane call
        # that *could* plausibly be mistaken for a reactivation path is
        # `enable_application`, since applications and credentials are
        # separate flags on this peer (`_Credential.enabled` vs.
        # `_applications[...]`) -- exercised here as a real attempt rather
        # than assumed safe.
        def enable_application_after_revoke_attempt() -> None:
            # `enable_application` only ever flips the *application*-level
            # flag (`_applications[...]`); it never touches a credential's
            # own `enabled` state (`_Credential.enabled`, set False by
            # `revoke()`) at all, so this call itself never raises -- it is
            # a real, no-op-for-this-purpose control-plane call, not a
            # denied one. `must_ignore` is the correct disposition:
            # C-13's own must_ignore handling re-authenticates afterward
            # and asserts the credential is still refused, which is the
            # actual proof this attempt did not reactivate anything; that
            # post-condition check does not belong inside attempt() itself
            # (design docs/design/CONFORMANCE_CONDITIONS_V1_1.md section 2:
            # must_ignore's attempt() "may succeed").
            self._control.credentials.enable_application(handle.application_id)

        return [
            TamperVector(
                kind="credential_reactivation",
                name="mitatedb_enable_application_does_not_reactivate_revoked_credential",
                disposition="must_ignore",
                attempt=enable_application_after_revoke_attempt,
            ),
            TamperVector(
                kind="credential_reactivation",
                name="mitatedb_credential_store_has_no_reactivation_call",
                disposition="structurally_absent",
                surface=[
                    self._control.credentials.issue,
                    self._control.credentials.revoke,
                    self._control.credentials.disable_application,
                    self._control.credentials.enable_application,
                    self._control.credentials.provision_application,
                    self._control.credentials.authenticate,
                    self._control.credentials.assert_active,
                ],
                forbidden_parameters=["enabled", "revoked", "reactivate", "unrevoke", "un_revoke"],
            ),
        ]

    def identifier_positions(self, fixture: Fixture) -> Mapping[str, Callable[[Any], Any]]:
        runtime_a = fixture.runtime_a
        developer_a = fixture.developer_a

        def entity_probe(payload: Any) -> Any:
            return self._call(lambda: runtime_a.read(payload))

        def select_field_probe(payload: Any) -> Any:
            return self._call(lambda: runtime_a.read(fixture.shared_entity, fields=[payload]))

        def filter_field_probe(payload: Any) -> Any:
            return self._call(lambda: runtime_a.read(fixture.shared_entity, filters=[Filter(payload, "eq", 1)]))

        def _require_hashable(position: str, payload: Any) -> None:
            # An unhashable NON_STRING payload (e.g. [], {}) cannot even be
            # placed at a mapping-key position -- the request can't be
            # constructed, so this is a harness-level impossibility, not an
            # observation of this peer's validation (design section 10.3).
            try:
                hash(payload)
            except TypeError as exc:
                raise PayloadNotExpressible(
                    position, payload, "payload is unhashable and this position is a mapping key"
                ) from exc

        def insert_field_probe(payload: Any) -> Any:
            _require_hashable("insert_field", payload)
            return self._call(lambda: runtime_a.insert(fixture.shared_entity, {payload: "x"}))

        def schema_entity_probe(payload: Any) -> Any:
            return self._call(lambda: developer_a.create_collection(payload, {"id": "integer"}))

        def schema_field_probe(payload: Any) -> Any:
            _require_hashable("schema_field", payload)
            name = "conf_schema_field_probe_" + uuid.uuid4().hex[:8]
            return self._call(lambda: developer_a.create_collection(name, {payload: "text"}))

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
                marker = "probe-" + uuid.uuid4().hex
                runtime_a.insert(entity, {"probe_key": marker, "probe_value": payload})
                rows = runtime_a.read(entity, fields=["probe_value"], filters=[Filter("probe_key", "eq", marker)])
                return rows[0]["probe_value"] if rows else None
            return self._call(op)

        def filter_value_probe(payload: Any) -> Any:
            def op() -> Any:
                marker = "probe-" + uuid.uuid4().hex
                runtime_a.insert(entity, {"probe_key": marker, "probe_value": payload})
                rows = runtime_a.read(entity, fields=["probe_value"], filters=[
                    Filter("probe_key", "eq", marker),
                    Filter("probe_value", "eq", payload),
                ])
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
        # Only this peer's own declared error base class (FoundationError,
        # via the type-ordered table above) is converted to a contract
        # code. Anything else -- e.g. a raw sqlite3.Error that escaped this
        # peer's FoundationError boundary -- is not a denial this adapter
        # can vouch for; laundering it into VALIDATION_FAILED would hide a
        # peer crash (or an unclassified defect) behind a passing test
        # (design section 10.2). Report it as unclassified instead.
        if isinstance(exc, FoundationError):
            for exc_type, code in _CLASSIFY_ORDER:
                if isinstance(exc, exc_type):
                    return code
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
        # raises "application already provisioned". Identifiers stay
        # lowercase per this peer's stricter catalog policy.
        self._counter += 1
        suffix = f"{self._counter}_{uuid.uuid4().hex[:8]}"
        app_a, app_b = f"conf_app_a_{suffix}", f"conf_app_b_{suffix}"
        self.provision_application(app_a)
        self.provision_application(app_b)

        # `item_key`, not `id`: the common fixture must not use `id` as an
        # ordinary field name (port v1.2 coordinated revision, docs/design/
        # CONFORMANCE_ADAPTER_V1.md section 12 / docs/design/
        # R2DB_CCR13_STORAGE_V1.md R-3) -- `r2db-api` reserves it as its
        # server-assigned address column. `MitateDB-api` itself does not
        # reserve `id` (this peer's own throwaway probe entities elsewhere
        # in this file may still use it freely), but the *shared* fixture
        # entities below must use a name safe on every registered peer.
        fields = {"item_key": "integer", "label": "text", "probe_key": "text", "probe_value": "text"}
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

        self.insert(developer_a, shared_entity, {"item_key": 1, "label": "seed-a", "probe_key": "seed", "probe_value": "seed-a"})
        self.insert(developer_b, shared_entity, {"item_key": 1, "label": "seed-b", "probe_key": "seed", "probe_value": "seed-b"})
        self.insert(developer_a, a_only_entity, {"item_key": 1, "label": "a-only", "probe_key": "seed", "probe_value": "a-only"})
        self.insert(developer_b, b_only_entity, {"item_key": 1, "label": "b-only", "probe_key": "seed", "probe_value": "b-only"})

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
        # In-memory sqlite (":memory:") per cell; nothing external to
        # release, and each build_adapter() call gets a fresh ControlPlane.
        pass

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------
    def _call(self, fn: Callable[[], Any]) -> Any:
        try:
            return fn()
        except FoundationError as exc:
            raise self._deny(exc) from exc
        except (TypeError, ValueError, sqlite3.Error) as exc:
            # TypeError/ValueError: malformed structural input at the
            # Python level (e.g. an unhashable field-name payload).
            # sqlite3.Error: this peer's storage driver rejects some
            # malformed values (e.g. an embedded NUL byte) below the
            # FoundationError boundary; cell.py only translates
            # sqlite3.IntegrityError/DatabaseError, not the full driver
            # hierarchy, so this adapter must still classify it rather than
            # let it leak past the port as a raw driver exception.
            raise self._deny(exc) from exc

    def _deny(self, exc: BaseException) -> ConformanceDenial:
        return ConformanceDenial(code=self.classify(exc), adapter=self.name, native_type=type(exc).__name__)


def build_adapter() -> ConformanceAdapter:
    return MitateDBConformanceAdapter()
