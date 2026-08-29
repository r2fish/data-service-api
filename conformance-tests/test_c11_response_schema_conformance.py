"""C-11 extension -- real response schema conformance (SI-08, SI-15) for the
contract's now-closed response schemas.

design: docs/design/DESTRUCTIVE_CONFIRMATION_V1.md R-1 / subordinate ruling
7(A) (`spec/CCR_DISPOSITION.md`'s "従属判断 -- すべて裁定済み" item 7): 11
previously-open response schemas (`QueryResult`, `MutationResult`,
`CatalogDocument`, `SchemaOperationResult`, `AuditResult`,
`ApplicationStateResult`, `ApplicationsResult`, `CredentialIssued`,
`CredentialsResult`, `CredentialRotated`, `CredentialStateResult`) plus
`definitions.EntityDescriptor` and the request schema `AuditQueryRequest`
were closed with `additionalProperties: false` in contract 1.2.0, and a
follow-up fix-round additionally closed four nested "row" schemas
(`ApplicationsResult.applications[]`, `CredentialsResult.credentials[]`,
`MutationResult.assigned_addresses[]`, `definitions.EntityDescriptor.
unique_keys[]`) while deliberately leaving four other nested/free-form spots
open (`CapabilityDocument`'s three keyed dictionaries and each capability
entry's own value schema, `MutationResult.assigned_addresses[].address`,
`AuditResult.events[]`, `Mutation`/`ScopedMutation.values` -- each carries
its own `description` annotation in the contract explaining why). Ruling
7(A) requires the SAME commit to add a reverse-validation check -- real
response documents from a genuinely running peer, validated against the
now-closed schema via `schema_check.assert_valid` -- so the closure is
proven to match what implementations actually emit today, not merely
declared in the contract.

This module is a new file (not an extension of
`test_c11_document_conformance.py`'s own body) so that file's existing,
already-passing tests are never at risk of an unrelated edit; it reuses the
SAME `@pytest.mark.condition("C-11")` marker rather than registering a new
condition ID, since this is additional schema-conformance coverage for the
same discovery/document-shape concern C-11 already owns (no CONDITIONS.md or
registry.json condition-ID change is needed for that reason; CONDITIONS.md's
own C-11 row IS updated to describe this file's real, as-tested coverage).

No `pytest.skip` appears anywhere in this file (fix-round M-6): an earlier
revision used `pytest.skip` both for a peer whose control plane is
genuinely absent (MitateDB-api) and for a missing optional raw-accessor
method, and an independent review correctly flagged both as design-
principle-4 violations -- a skip takes an absence claim on faith instead of
checking it, or silently converts "nothing was validated" into "passed".
Every path below either runs a real, adapter-independent assertion (the
`SurfaceAbsent` claim gets the same 3-part re-verification
`test_c14_authority_boundary.py`'s `_assert_control_operation_absent_or_
uniformly_refused` already applies to every other control-plane absence
claim on this port) or fails loudly (a missing raw-accessor method is an
`AssertionError`, never a quiet pass).

Coverage decisions (reported in full to the WP-1 requester, per its own
reporting requirement):

- `CatalogDocument` (and, via its `entities` array, `EntityDescriptor`) needs
  NO new test here: `test_c11_document_conformance.py`'s existing
  `test_catalog_document_conforms_to_schema_or_is_honestly_absent` already
  calls `assert_valid` against a real `catalog_document()` for every
  registered adapter (all 3 adapters currently registered), and it did so
  before this closure too -- once the contract schema itself closed, that
  existing test started exercising the closed shape automatically, with no
  code change of its own required.
- `ApplicationStateResult`, `CredentialRotated`, `CredentialStateResult` are
  reachable, UNMODIFIED, through the existing abstract `ConformanceAdapter`
  port itself (`register_application_inband`/`set_application_enabled_
  inband`, `rotate_credential`, `revoke_credential_inband`/
  `set_credential_enabled_inband` -- every one of these already returns the
  peer's real response object, per each method's own docstring on
  `conformance-tests/adapter.py`) -- so the check below runs against EVERY
  registered adapter that provides a real control plane: both `r2db-api`
  adapters (2 of 3 registered), as of WP-5. `MitateDB-api` (the 3rd) has no
  control-plane surface at all; that claim is independently re-verified
  below, not taken on faith.
- `QueryResult`, `MutationResult`, `SchemaOperationResult`, `ApplicationsResult`,
  `CredentialIssued`, `CredentialsResult` have NO abstract-port method that
  returns the real response body unmodified (the port's own methods for
  these -- `select_eq`/`attempt_mutation`/`create_entity`/`list_applications`/
  `issue_credential_inband`/`list_credentials` -- all deliberately unwrap or
  normalize the real response for the port's own typed return shape, by
  design; extending the frozen port ABC to stop doing that is a separate,
  coordinated design revision, R-6/port v1.6, not this WP). Per this WP's own
  instruction ("少なくとも r2db HTTP adapter経由の実 JSON 応答"), this file
  reaches a small set of NON-normative, additive raw-accessor methods added
  directly on `r2db-api (http+postgres)`'s own concrete plug
  (`r2db-api/conformance/conformance_adapter_r2db_http.py`) -- see that
  file's own "WP-1" comment block -- via `getattr(...)` duck-typing. Only
  `r2db-api (http+postgres)` (1 of 3 registered adapters) provides them
  today; if NO registered adapter provided a given accessor, the
  corresponding test below fails loudly (never skips) -- this is currently
  unreachable in practice (r2db-api (http+postgres) always provides all six),
  but the failure path exists in case that ever regresses.
- `AuditResult` has NO reverse-validation coverage anywhere in this suite:
  every registered implementation currently declares `audit_query`
  unavailable (`capability_status.defined.audit_query`), and no adapter (any
  peer, in-process or HTTP) presents any request to the contract's
  `POST /v1/audit/query` endpoint at all today -- `control_audit_events()`
  on this port reads each peer's durable sink directly, never through that
  endpoint, and no other method exists that could. There is consequently no
  real document of this shape for any registered peer to produce yet; this
  is reported as a genuine, currently-unfillable gap, not a peer-specific
  exclusion the WP-1 design's own "in-process adapter が契約形状の文書を作ら
  ない箇所は対象外で良い" carve-out covers. Closing it is deferred to
  whichever future phase actually implements an audit sink/query surface
  (tracked informally as "phase 4" in the handover material) -- there is
  nothing for this WP to validate against before that lands.
"""
from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

import pytest

from conftest import registered_adapters
from adapter import (
    ConformanceDenial,
    SurfaceAbsent,
    fresh_identifier,
    load_contract,
    signature_forbids_parameters,
)
from schema_check import assert_valid, validate

pytestmark = pytest.mark.condition("C-11")


# --- shared helpers ---------------------------------------------------------


def _find_adapter_with(method_name: str) -> tuple[str | None, Any, Callable | None]:
    """Registry-wide (not fixture-parametrized) lookup for one of the
    optional, non-normative raw-accessor methods described in this module's
    docstring. Not every registered adapter provides these. Returns
    `(name, adapter_obj, bound_method)`, or `(None, None, None)` if no
    registered adapter currently does."""
    for name, obj in registered_adapters().items():
        method = getattr(obj, method_name, None)
        if method is not None:
            return name, obj, method
    return None, None, None


def _require_adapter_with(method_name: str, schema_name: str) -> tuple[str, Any, Callable]:
    """Like `_find_adapter_with`, but fails loudly (never skips) when no
    registered adapter provides `method_name` (fix-round M-6): a silent skip
    here would let the corresponding schema closure go entirely unverified
    against any real response, which is exactly the "uncertainty silently
    becomes permission" failure design principle 4
    (`docs/design/CONFORMANCE_ADAPTER_V1.md`) forbids."""
    name, obj, method = _find_adapter_with(method_name)
    if obj is None:
        raise AssertionError(
            f"no registered adapter exposes {method_name}() -- WP-1 reverse-validation for "
            f"{schema_name} has no real document to validate against the closed schema. This "
            "fails the suite rather than skipping: at least one registered adapter must supply "
            "a real document for every closed response schema (vacuity guard, mirrors "
            "test_c11_document_conformance.py's own registry-wide check for CatalogDocument)."
        )
    return name, obj, method


def _require_attr(obj: Any, adapter_name: str, method_name: str, sibling_method_name: str) -> Callable:
    """Fails loudly (fix-round n-1) if `obj` does not carry `method_name`,
    instead of a bare, unguarded attribute access that would raise an
    uninformative AttributeError. Used for the raw-accessor methods that are
    always expected to exist together on the same adapter object once one of
    them (`sibling_method_name`) has already been confirmed present."""
    method = getattr(obj, method_name, None)
    if method is None:
        raise AssertionError(
            f"{adapter_name}: exposes {sibling_method_name}() but not {method_name}() -- WP-1's "
            "raw-accessor block on this adapter is internally inconsistent"
        )
    return method


def _assert_surface_absent_claim(adapter_name: str, exc: SurfaceAbsent, public_surface: Sequence[Callable]) -> None:
    """Independently re-verifies a `SurfaceAbsent` claim rather than taking
    it on faith (fix-round M-6 item 1) -- the same 3-part check
    `test_c14_authority_boundary.py`'s `_assert_control_operation_absent_or_
    uniformly_refused` already applies to every other control-plane absence
    claim on this port (design docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md
    WP-1 independent review major M-7). Reproduced here (not imported) to
    keep this file's own plumbing self-contained, matching this suite's
    existing convention of each test module owning its own helpers.
    """
    violations = set(signature_forbids_parameters(exc.surface, exc.forbidden_parameters))
    exempt = set(exc.exempt_parameters)
    assert violations == exempt, (
        f"{adapter_name}: SurfaceAbsent's signature_forbids_parameters violations {sorted(violations)!r} "
        f"do not exactly equal its declared exempt_parameters {sorted(exempt)!r} -- an unexempted "
        "violation means a real parameter could carry the absent capability (claim false); a stale or "
        "padded exemption naming a parameter that is not actually a violation is itself suspect"
    )
    declared = {f.lower() for f in exc.forbidden_parameters}
    assert {"credential", "control"} <= declared, (
        f"{adapter_name}: SurfaceAbsent's forbidden_parameters {exc.forbidden_parameters!r} does not "
        "include both 'credential' and 'control' -- a narrower fragment set could pass "
        "signature_forbids_parameters vacuously without covering the control-plane vocabulary this claim "
        "is supposed to rule out"
    )
    declared_surface = set(exc.surface)
    public_surface_set = set(public_surface)
    assert declared_surface >= public_surface_set, (
        f"{adapter_name}: SurfaceAbsent's declared surface omits "
        f"{[c for c in public_surface_set if c not in declared_surface]!r} of the peer's own real "
        "public_operation_callables() -- shrinking the evidence surface below the peer's real public "
        "surface would let a genuine control-plane-shaped parameter elsewhere on the peer go unchecked"
    )


# --- QueryResult / MutationResult / SchemaOperationResult (r2db http only) --


def test_query_result_conforms_to_closed_schema():
    name, obj, raw_query_result = _require_adapter_with("raw_query_result", "QueryResult")
    contract = load_contract()
    schema = contract["schemas"]["QueryResult"]
    fx = obj.build_fixture()
    document = raw_query_result(fx.runtime_a, fx.shared_entity, ["item_key", "label", "probe_key", "probe_value"])
    assert_valid(document, schema, contract, label=f"{name} raw_query_result()")


def test_mutation_result_conforms_to_closed_schema():
    name, obj, raw_mutation_result = _require_adapter_with("raw_mutation_result", "MutationResult")
    contract = load_contract()
    schema = contract["schemas"]["MutationResult"]
    fx = obj.build_fixture()
    operation = {
        "operation": "insert",
        "values": {"item_key": 424242, "label": "wp1-probe", "probe_key": "wp1", "probe_value": "wp1-probe"},
    }
    document = raw_mutation_result(fx.runtime_a, fx.a_only_entity, [operation])
    assert_valid(document, schema, contract, label=f"{name} raw_mutation_result()")


def test_schema_operation_result_conforms_to_closed_schema():
    name, obj, raw_schema_operation_result = _require_adapter_with("raw_schema_operation_result", "SchemaOperationResult")
    contract = load_contract()
    schema = contract["schemas"]["SchemaOperationResult"]
    fx = obj.build_fixture()
    fresh_field = fresh_identifier("wp1field")
    body = {"operation": "add_field", "entity": fx.a_only_entity, "field": fresh_field, "field_type": "string"}
    document = raw_schema_operation_result(fx.developer_a, body)
    assert_valid(document, schema, contract, label=f"{name} raw_schema_operation_result()")


# --- ApplicationsResult / CredentialIssued / CredentialsResult (r2db http) --


def test_control_plane_envelope_and_issuance_responses_conform_to_closed_schema():
    name, obj, raw_list_applications = _require_adapter_with(
        "raw_list_applications", "ApplicationsResult/CredentialIssued/CredentialsResult"
    )
    # fix-round n-1: `raw_issue_credential`/`raw_list_credentials` get the
    # same fail-loud treatment as `raw_list_applications` above, rather than
    # a bare, unguarded attribute access.
    raw_issue_credential = _require_attr(obj, name, "raw_issue_credential", "raw_list_applications")
    raw_list_credentials = _require_attr(obj, name, "raw_list_credentials", "raw_list_applications")

    contract = load_contract()
    try:
        actor = obj.control_credential()
    except (SurfaceAbsent, ConformanceDenial) as exc:
        raise AssertionError(
            f"{name}: control_credential() raised {type(exc).__name__} even though this adapter "
            "provides raw_list_applications() -- a peer whose raw-accessor block exists is expected "
            "to have a real, usable control plane; this is a genuine finding, not something to skip"
        ) from exc

    applications_doc = raw_list_applications(actor)
    assert_valid(applications_doc, contract["schemas"]["ApplicationsResult"], contract, label=f"{name} raw_list_applications()")

    fx = obj.build_fixture()
    issued_doc = raw_issue_credential(actor, fx.app_a, "runtime")
    assert_valid(issued_doc, contract["schemas"]["CredentialIssued"], contract, label=f"{name} raw_issue_credential()")

    credentials_doc = raw_list_credentials(actor)
    assert_valid(credentials_doc, contract["schemas"]["CredentialsResult"], contract, label=f"{name} raw_list_credentials()")


# --- ApplicationStateResult / CredentialRotated / CredentialStateResult ----
# (any adapter with a real, in-band control plane -- both r2db-api adapters
# as of WP-5; independently re-verified, never skipped, for a peer whose
# control-plane surface is genuinely absent -- MitateDB-api today)


def test_application_state_and_credential_lifecycle_responses_conform_to_closed_schema(adapter, fx):
    contract = load_contract()
    try:
        actor = adapter.control_credential()
    except SurfaceAbsent as exc:
        # fix-round M-6 item 1: independently re-verify this claim instead
        # of skipping past it.
        _assert_surface_absent_claim(adapter.name, exc, adapter.public_operation_callables())
        return

    fresh_app = fresh_identifier("wp1app")
    registered = adapter.register_application_inband(actor, fresh_app)
    assert_valid(
        registered, contract["schemas"]["ApplicationStateResult"], contract,
        label=f"{adapter.name} register_application_inband()",
    )

    disabled_app = adapter.set_application_enabled_inband(actor, fresh_app, False)
    assert_valid(
        disabled_app, contract["schemas"]["ApplicationStateResult"], contract,
        label=f"{adapter.name} set_application_enabled_inband(False)",
    )

    # A fresh, disposable application credential -- never fx's own shared
    # runtime/developer sessions -- so this test's rotate/disable/revoke
    # sequence cannot disturb any other test sharing this session-scoped
    # adapter/fixture's state.
    fresh_credential = adapter.issue_credential(fx.app_a, "runtime")

    rotated = adapter.rotate_credential(actor, fresh_credential.credential_ref)
    assert isinstance(rotated, Mapping), f"{adapter.name}: rotate_credential() did not return a real mapping response"
    assert_valid(
        rotated, contract["schemas"]["CredentialRotated"], contract,
        label=f"{adapter.name} rotate_credential()",
    )

    disabled_cred = adapter.set_credential_enabled_inband(actor, fresh_credential.credential_ref, False)
    assert_valid(
        disabled_cred, contract["schemas"]["CredentialStateResult"], contract,
        label=f"{adapter.name} set_credential_enabled_inband(False)",
    )

    revoked_cred = adapter.revoke_credential_inband(
        actor, fresh_credential.credential_ref, destructive=False, confirmation=None,
    )
    assert_valid(
        revoked_cred, contract["schemas"]["CredentialStateResult"], contract,
        label=f"{adapter.name} revoke_credential_inband()",
    )


# --- M-7 positive control: the newly-closed nested row schemas actually ----
# reject an excess key, not merely declare additionalProperties: false with
# nothing ever exercising it.


def test_nested_row_schemas_reject_an_excess_key():
    """Schema-shape check against synthetic instances (`schema_check.
    validate`), independent of any adapter -- validating the CONTRACT's own
    closure directly, the same way `test_schema_check.py`'s own unit tests
    exercise contract schema shape. Covers all four row schemas the fix-round
    closed: `MutationResult.assigned_addresses[]`, `ApplicationsResult.
    applications[]`, `CredentialsResult.credentials[]`, and
    `definitions.EntityDescriptor.unique_keys[]`."""
    contract = load_contract()

    mutation_result = contract["schemas"]["MutationResult"]
    tampered_addresses = {
        "committed": True, "affected": 1,
        "assigned_addresses": [{"address": {"item_key": 1}, "bogus_extra_key": "x"}],
    }
    assert validate(tampered_addresses, mutation_result, contract), (
        "MutationResult.assigned_addresses[] must reject an excess key"
    )

    applications_result = contract["schemas"]["ApplicationsResult"]
    tampered_applications = {"applications": [{"application_id": "a", "enabled": True, "bogus_extra_key": "x"}]}
    assert validate(tampered_applications, applications_result, contract), (
        "ApplicationsResult.applications[] must reject an excess key"
    )

    credentials_result = contract["schemas"]["CredentialsResult"]
    tampered_credentials = {
        "credentials": [
            {"credential_id": "c", "role": "runtime", "enabled": True, "revoked": False, "bogus_extra_key": "x"}
        ],
    }
    assert validate(tampered_credentials, credentials_result, contract), (
        "CredentialsResult.credentials[] must reject an excess key"
    )

    entity_descriptor = contract["definitions"]["EntityDescriptor"]
    tampered_entity = {
        "entity": "notes", "fields": ["id"],
        "unique_keys": [{"name": "uk", "fields": ["id"], "bogus_extra_key": "x"}],
    }
    assert validate(tampered_entity, entity_descriptor, contract), (
        "EntityDescriptor.unique_keys[] must reject an excess key"
    )
