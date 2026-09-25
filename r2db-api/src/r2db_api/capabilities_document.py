"""r2db-api capability-document assembly for `DataService.capabilities` (SV2).

A pure leaf: builds the capability document from explicit arguments only,
never reading `AuthContext`/`self` -- the facade keeps the authorization
slot and passes it the principal and deployment values it already holds."""
from __future__ import annotations

from typing import Any

# Phase 10 WP-6a (design D-5(ii), contract 1.8.0): this plane's own region (ii) -- limit classes bound by in-memory, per-process state (`self._rate_windows`/`self._active`, both below) (in `service.py`), the only classes whose `limit_enforcement` mapping actually depends on `process_ceiling`. Every other `ResourceLimits` class is either region (i) (request-scoped, unaffected regardless of process count) or region (iii) (`idempotency_entries`, bound in PostgreSQL -- `enforced` regardless of `process_ceiling`, design; the count lock itself is scope, not this WP's).
# history: CH-0174
_IN_MEMORY_PROCESS_WIDE_LIMIT_CLASSES = frozenset({"requests_per_minute", "concurrency"})


def build_capabilities_document(
    *,
    role: str,
    application_id: str,
    limits: Any,
    control_plane_status: str,
    process_ceiling: int,
    surfaces: dict[str, Any] | None,
    operation_catalog_url: str | None = None,
) -> dict[str, Any]:
    # CCR-13 WP-5b: the WP-2-through-WP-5 provisional gate (design
    # R2DB_CCR13_STORAGE_V1.md §3) is removed in this same commit
    # (see `query`/`mutate`/`schema`/`catalog` below) (in `service.py`) -- this
    # declaration update is what makes that removal honest rather
    # than a new C-12 "declared unavailable, executes anyway" gap.
    # Contract 1.7.0: `alter_field` joins the developer-only schema-operation set -- `R-2` constraint declarations are enforced now (see `constraint_declarations` below), so it is no longer accurate to list it under `unsupported`.
    # history: CH-0143
    schema_ops = ["create_entity", "add_field", "alter_field", "create_index", "drop_index", "drop_entity"] if role == "developer" else []
    document: dict[str, Any] = {
        # Phase 4 WP-2(b) (P4-D4, contract `versioning.
        # version_binding`), flipped to 1.5.0 in phase 5 WP-2,
        # flipped to 1.6.0 in phase 6 WP-2 (design docs/design/
        # PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md, subordinate
        # ruling 11): unconditional -- every deployment of this
        # data-plane host declares 1.6.0 now, whether or not
        # the CONTROL host alongside it has AUDIT DSN configured
        # (`audit_query` stays `unavailable` right below,
        # unchanged: this host never provides it, D-5's own
        # "declaration = real behavior" rule).
        #
        # Flipped to 1.7.0 in phase 9 WP-2e (design docs/design/PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md D-1 (5)): the SAME commit as this host's own R-3 (`errors.details_vocabulary` 4-key details) and R-7 (`request_id` on every successful result) implementation -- the two 1.7.0 UNCONDITIONAL obligations -- never ahead of the behavior it declares (D-1 (7)'s xfail(strict=True) version gate is exactly what would catch that ordering mistake).
        #
        # Phase 10 WP-6a/pair-closing: flipped again to 1.8.0 in the SAME commit as this host's own `process_ceilings` mapping -- the version's one unconditional obligation, `limit_enforcement_scoped_to_deployment_behind_base_url` -- never ahead of the behavior it declares.
        #
        # This host also declares contract 1.9.0 in the same commit as `common_baseline`'s operations all being genuinely executable (no status below moves) and `operation_catalog_url` (below) actually serving the byte-identical derived catalog (`http.py::get_operation_catalog`) -- the version's two unconditional obligations, never ahead of the behavior they declare. `control_plane.py`'s own control-plane document flips in the same commit too (C-19's cross-plane version match).
        #
        # This host also declares contract 1.10.0 in the same commit as its own keyset paging behavior -- query results totally ordered, a stateless page.cursor with next_page, cursor binding, and a page.size default -- 1.10.0's own conditional obligations, bound while structured_query stays enabled here, never ahead of the behavior they declare.
        #
        # This host also declares contract 1.11.0 in the same commit as its own undeclared-field refusal alignment -- a select entry, a where predicate's field, an order_by entry's field, or a mutation's values key that names a field this entity does not declare is refused with VALIDATION_FAILED, violated_declaration request_schema and field naming the position -- 1.11.0's own unconditional obligation, never ahead of the behavior it declares.
        # history: CH-0142
        "contract_version": "1.11.0",
        "capabilities": {
            "structured_query": {"status": "enabled", "operators": ["eq", "ne", "lt", "lte", "gt", "gte", "in", "contains", "matches", "is_null"]},
            # Contract 1.1.0 (CCR-13, `structured_operations.
            # upsert`): `upsert`'s existence test is the entity's
            # own declared domain uniqueness (`EntityDescriptor.
            # unique_keys`, `application_catalog` below) -- an
            # entity with no declared uniqueness key still refuses
            # `upsert` with `CAPABILITY_UNSUPPORTED` (structured.py::
            # bind_mutation (now in `mutation_binding.py`)/_apply_upsert), but that is a per-entity
            # condition the catalog itself communicates, not a
            # service-wide gap `atomic_mutation` needs to qualify.
            "atomic_mutation": {"status": "enabled", "operations": ["insert", "update", "upsert", "delete"]},
            "application_catalog": {"status": "enabled"},
            "schema_operations": {"status": "partial", "operations": schema_ops, "unsupported": ["jobs"]},
            "audit_query": {"status": "unavailable", "authority": "control_or_audit"},
            "best_effort_transactions": {"status": "unavailable"},
            # WP-2c (contract 1.7.0, D-5, ruling I-10/I-12): `enabled`
            # -- the same commit that removes the `idempotency_key`
            # provisional gate (`schema()`'s `_PROVISIONAL_UNSUPPORTED_
            # SCHEMA_FIELDS`/`http.py`'s `post_mutate`) and gives it
            # real record-and-replay effect (`structured.py`/
            # `postgres.py`). `limits.idempotency_entries`/
            # `idempotency_retention_ms` reach `capabilities()`'s
            # `limits`/`limit_enforcement` documents automatically,
            # through `ResourceLimits.as_dict()` below (ruling I-10/
            # S-f -- C-05 V1 (e)'s `_CAPABILITY_CONDITIONED` requires
            # both the moment this flips).
            "idempotency": {"status": "enabled"},
            "revision_preconditions": {"status": "enabled"},
            "row_addressability": {"status": "enabled"},
            # `cross_entity_mutation` needs the new `POST /v1/data/mutations` endpoint (stubbed in `http.py` as CAPABILITY_UNSUPPORTED, not executable), so it stays `unavailable` here: it has no executable operation at all. (`control_plane`, immediately below, is NOT in the same position any more: CCR-14 shipped the surface as a separate process, and its status is the deployer's own declaration -- the pre-CCR-14 wording that once grouped the two as "both remain unavailable" was corrected)
            # history: CH-0141
            "cross_entity_mutation": {"status": "unavailable"},
            # reflects this instance's own constructor-injected deployer declaration -- never hardcoded (see __init__'s comment on this field) (in `service.py`).
            # history: CH-0140
            "control_plane": {"status": control_plane_status},
            # Contract 1.7.0 (subordinate ruling 12): each of the three capabilities below is declared `enabled` in the same commit that removes the provisional gate rejecting every field it governs (`schema`/`mutate_result`/`_query_outcome` below, `http.py`'s `post_mutate`/`post_query`) (in `service.py`) -- P-3 (宣言と挙動は同一コミット).
            #
            # `constraint_declarations` is `enabled` -- `field_constraints`/`enum`/`nullable`/`alter_field` are no longer in `_PROVISIONAL_UNSUPPORTED_SCHEMA_FIELDS` (removed in this same commit) and are now enforced (`structured.py`/`postgres.py`).
            # history: CH-0139
            "constraint_declarations": {"status": "enabled"},
            # `dry_run` is `enabled` -- `dry_run`/`plan` are no longer in `_PROVISIONAL_UNSUPPORTED_SCHEMA_FIELDS` (schema side) and `mutate_result`/`_mutate_outcome` (mutation side) no longer refuse them outright, in this same commit as `structured.py`/`postgres.py`'s own real dry_run/plan enforcement. WP-2d
            # (`request_budget`) flips its own entry the same way,
            # in its own commit.
            # history: CH-0138
            "dry_run": {"status": "enabled"},
            # WP-2d (contract 1.7.0, D-6, ruling B-4): `enabled` --
            # the same commit that removes every `budget` provisional
            # gate (`_query_outcome`/`mutate_result`/`schema()`'s
            # `_PROVISIONAL_UNSUPPORTED_SCHEMA_FIELDS`) and gives it
            # real narrowing effect via `narrow_limits_by_budget`
            # (`limits.py`).
            "request_budget": {"status": "enabled"},
        },
        "limits": limits.as_dict(),
        # `idempotency_retention_ms` joins `execution_ms` in the `reference_wall_clock` set -- both are wall-clock DURATIONS a deployment cannot drive to a deterministic N/N+1 boundary within a bounded test run (unlike every COUNT-valued class here, `idempotency_entries` included, which genuinely IS `enforced`: a record's own retention window is checked lazily, against real elapsed time, not a request-counted budget).
        # Phase 10 WP-6a (design D-5(ii), contract 1.8.0): three regions, not two. Region (i) (request-scoped: every class
        # below not named in the other two sets) is unaffected by
        # `process_ceiling` -- unchanged from before this WP.
        # Region (ii) (`requests_per_minute`/`concurrency` --
        # bound by in-memory, per-process state, `self._rate_
        # windows`/`self._active`) reads `enforced` only while
        # `process_ceiling == 1` and `deployment_required` once it
        # is `>= 2` (contract 1.8.0's own enforcement-scope
        # definition: a per-process bound is `enforced` for the
        # whole deployment only while exactly one process may
        # serve this plane's base URL). Region (iii)
        # (`idempotency_entries` -- bound in PostgreSQL,
        # `postgres.py`'s own `_idempotency_reserve`) stays
        # `enforced` regardless of `process_ceiling` -- this class
        # does not resolve within one request.
        # history: CH-0137
        "limit_enforcement": {
            name: (
                "reference_wall_clock" if name in ("execution_ms", "idempotency_retention_ms")
                else ("enforced" if process_ceiling <= 1 else "deployment_required") if name in _IN_MEMORY_PROCESS_WIDE_LIMIT_CLASSES
                else "enforced"
            )
            for name in limits.as_dict()
        },
        # `_check()` (called by `_slot()` above) (in `service.py`) re-validates
        # credential/application authorization state on every
        # single application-plane operation; there is no cache, so
        # revoke/disable/state-unavailable propagation is
        # synchronous (see also the identical reasoning in
        # `conformance/conformance_adapter_r2db.py`'s
        # `propagation_bound_ms()`).
        "authorization_propagation_bound_ms": 0,
        "application_scope": application_id,
        "role": role
    }
    # `surfaces` is an optional key -- present only when this instance was constructed with one (`__init__`'s own comment on `self._surfaces`) (in `service.py`). Never a
    # `"surfaces": None` entry.
    # history: CH-0136
    if surfaces is not None:
        document["surfaces"] = surfaces
    # Same constructor-injected, echo-only discipline as `surfaces`
    # immediately above -- optional key, present only when this instance
    # was constructed with one. `main.py` (the real composition root)
    # reads `R2DB_OPERATION_CATALOG_URL`; the conformance adapters inject
    # a synthetic (in-process plugs) or a dialable (socket plugs) value
    # directly.
    if operation_catalog_url is not None:
        document["operation_catalog_url"] = operation_catalog_url
    return document
