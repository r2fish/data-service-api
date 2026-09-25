"""MitateDB-api capability-document assembly for `ApplicationRuntime.
capabilities()` (CE7). A pure leaf: builds the capability document from
explicit arguments only, never reading `self`/`principal`/`Role` -- the
facade computes the `Role`-dependent value and passes it as an argument
with no default (W3-10)."""

from .backend import SQL_OPERATOR_TOKENS
from .surfaces import build_surfaces


def _surfaces_document_fragment(config):
    """Phase 6 WP-3 (design D-2): `{"surfaces": {...}}` when this process'
    own `config.data_base_url` is set, or `{}` (the key omitted entirely)
    when it is not -- meant to be splatted (`**`) directly into a
    `CapabilityDocument` dict literal. Never derives or infers either URL
    (`surfaces.build_surfaces`'s own docstring) -- both come straight from
    this SAME `FoundationConfig`, the single source of truth `control_
    plane_status` immediately above already uses."""
    surfaces = build_surfaces(data_url=config.data_base_url, control_url=config.control_base_url)
    return {"surfaces": surfaces} if surfaces is not None else {}


def _operation_catalog_url_fragment(config):
    """Same splat-friendly, key-omitted-when-unset shape as `_surfaces_
    document_fragment` immediately above -- `config.operation_catalog_url`
    is constructor-injected (`FoundationConfig.from_env`'s own
    `MITATEDB_OPERATION_CATALOG_URL`, or a direct value for a conformance
    adapter), never derived or hardcoded here."""
    url = config.operation_catalog_url
    return {"operation_catalog_url": url} if url is not None else {}


def build_capabilities_document(*, is_developer, role, application_id, cell_config, process_ceiling):
    config = cell_config
    # Phase 10 WP-6b (design D-5 (ii)): region (ii) of the 3-region
    # map -- the two in-memory-per-process-bound classes below
    # (`concurrency`/`requests_per_minute`, `_LimitStateHolder`'s own
    # docstring: "process-wide (one per composition root)") degrade
    # from `enforced` to `deployment_required` once more than one
    # process may serve this deployment's data-plane base URL at the
    # same time -- region (i) (every other class in `limit_
    # enforcement` below) is UNAFFECTED by ceiling (it is bound
    # per-request, not per-process).
    _in_memory_enforcement = "enforced" if process_ceiling <= 1 else "deployment_required"
    return {
        # Phase 4 WP-3(b) (P4-D4, contract `versioning.version_
        # binding`), flipped to 1.5.0 in Phase 5 WP-3 (design D-1,
        # subordinate ruling 10 item 1): unconditional -- every
        # deployment of this data-plane host declares 1.5.0 now,
        # whether or not the CONTROL host alongside it has AUDIT DSN
        # configured (`audit_query` stays `unavailable` right below,
        # unchanged: this host never provides it, D-5's own
        # "declaration = real behavior" rule -- design docs/design/
        # PHASE4_DURABLE_AUDIT_SINK_V1.md §7.5 "data-plane ホスト
        # (不変)"). `operations`/`target_kinds` are NOT declared here
        # -- this host's own `audit_query` stays `unavailable`, and
        # declaring a vocabulary for a surface this host never
        # provides would contradict declare-the-hazard (design D-1).
        # Phase 6 WP-3 (design D-1/D-2/D-3, subordinate ruling 11):
        # flipped to 1.6.0 -- same commit as `surfaces` (already
        # present, WP-3 D-2), the declared-type registry, and this
        # capability's own flip immediately below (declaration and
        # real behaviour land together, unconditionally -- every
        # deployment of this data-plane host declares 1.6.0 now).
        #
        # Phase 9 WP-3e (design D-1 (5)/(7), F-1): flipped to 1.7.0 --
        # SAME commit as this WP's own R-3 (`errors.details_
        # vocabulary`'s 4-key form on every VALIDATION_FAILED/
        # CAPABILITY_UNSUPPORTED this peer emits) and R-7
        # (`request_id` on every successful `QueryResult`/
        # `MutationResult`/`SchemaOperationResult`) implementation --
        # the two 1.7.0 UNCONDITIONAL obligations (`versioning.
        # version_binding`'s own "(a)"/"(b)" pair). D-1 (7): a peer
        # must never flip its own declared `contract_version` ahead
        # of the real behavior it claims -- C-21/C-25's own version-
        # gated `xfail(strict=True)` is the machine-enforced form of
        # that rule (this WP's own report measures both sides of it:
        # the pre-flip state with R-3/R-7 behavior already wired in
        # but this literal still `1.6.0`, C-21/C-25 XPASS(strict) RED
        # on this peer's 2 plugs; this flip landing in the SAME
        # commit as R-3/R-7 is what makes that measurement moot in
        # the delivered state).
        #
        # Flipped again to 1.8.0 in phase 10 WP-6b/pair-closing (design
        # D-5 (v)): the SAME commit as this host's own `process_
        # ceilings` mapping (D-5 (ii)) -- never ahead of the behavior
        # it declares.
        #
        # This host also declares contract 1.9.0 in the same commit as
        # `common_baseline`'s operations all being genuinely executable
        # (no status below moves) and `operation_catalog_url` (below)
        # actually serving the byte-identical derived catalog
        # (`http.py::get_operation_catalog`) -- the version's two
        # unconditional obligations, never ahead of the behavior they
        # declare. `control_plane.py`'s own control-plane document flips
        # in the same commit too (C-19's cross-plane version match).
        #
        # This host also declares contract 1.10.0 in the same commit as
        # its own keyset paging behavior -- query results totally
        # ordered, a stateless page.cursor with next_page, cursor
        # binding, and a page.size default -- 1.10.0's own conditional
        # obligations, bound while structured_query stays declared other
        # than unavailable (partial) here, never ahead of the behavior
        # they declare.
        #
        # This host also declares contract 1.11.0 in the same commit as
        # its own undeclared-field refusal alignment across all five
        # positions the contract names -- a select entry names its own
        # index (select/<i>), matching where/order_by/mutation-where,
        # and a mutation's values key names itself
        # (operations/<i>/values/<name>) -- each refused with
        # VALIDATION_FAILED, violated_declaration request_schema and
        # field naming the position -- 1.11.0's own unconditional
        # obligation, never ahead of the behavior it declares.
        # history: CH-0542
        "contract_version": "1.11.0",
        "capabilities": {
            "structured_query": {"status": "partial", "operators": list(SQL_OPERATOR_TOKENS), "unsupported": ["contains", "matches", "is_null"]},
            "atomic_mutation": {"status": "partial", "operations": ["insert", "update", "delete"], "unsupported": ["upsert"]},
            # Phase 6 WP-3 (design D-3): flipped to `enabled` --
            # `GET /v1/catalog` (`http.py::get_catalog`) now answers
            # for real, backed by the declared-type registry
            # (`ApplicationCell.catalog`, same commit).
            "application_catalog": {"status": "enabled"},
            # P3-D1 (design v1.1 §0 exception, WP-1): `add_field` is
            # now a real, developer-only, executed capability on both
            # backends -- declaration and implementation land in this
            # same commit (design v1.1 principle: "宣言と実挙動は単一
            # コミットでしか同時に動かさない").
            # Phase 9 WP-3a (design docs/design/
            # PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md
            # D-2 (5)): `alter_field` moves from `unsupported` into
            # `operations` -- it is now a real, developer-only,
            # executed capability (redeclaring a field's own `enum`/
            # `nullable`), same commit as its own implementation
            # (P-3), matching `add_field`'s own P3-D1 precedent above.
            "schema_operations": {"status": "partial", "operations": ["create_entity", "add_field", "alter_field"] if is_developer else [], "unsupported": ["create_index", "drop_index", "drop_entity", "jobs"]},
            "audit_query": {"status": "unavailable", "authority": "control_or_audit"},
            "best_effort_transactions": {"status": "unavailable"},
            # Phase 9 WP-3c (design D-5, 追補 2 S-f; 監督裁定集約
            # rulings-r5-r6.md I-10/I-12): flipped to `enabled` --
            # `transact` (single-entity and cross-entity),
            # `create_entity`/`add_field`/`alter_field` all record
            # and honor `idempotency_key` for real as of this SAME
            # commit, and the corresponding `http.py`/`cell.py`
            # present-denial gates are removed in it too (I-12: same
            # commit as this flip, C-05 `_CAPABILITY_CONDITIONED`
            # requires `limits.idempotency_entries`/`idempotency_
            # retention_ms` to be declared alongside it -- see
            # `limits`/`limit_enforcement` below, same commit).
            "idempotency": {"status": "enabled"},
            "revision_preconditions": {"status": "unavailable"},
            "row_addressability": {"status": "unavailable"},
            # P35 WP-2 (R-5, design docs/design/PHASE35_CROSS_ENTITY_
            # AND_CONTRACT_130_V1.md v1.2 §2/§0): flipped from
            # "unavailable" -- `transact()` executes real, atomic,
            # multi-entity batches as of this WP (two-pass,
            # `_plan_operation`), and the HTTP surface (`http.py::
            # post_cross_entity_mutate`) now dispatches to it instead
            # of an unconditional `CapabilityError`. `upsert` remains
            # a real capability gap here exactly as it is for the
            # single-entity path (P35-D3), refused by the same
            # `transact()` choke, not a second one -- declared
            # truthfully via `unsupported` below (coordinator
            # adjudication, P35 WP-2 follow-up: an earlier two-key
            # form omitting `unsupported` was not intended -- `upsert`
            # is a real member of `ScopedMutation.operation`'s own
            # enum that this peer refuses, and the sibling capability
            # already declares that exact refusal).
            #
            # Status is `"partial"`, not `"enabled"` (independent
            # review M-1, WP-2 follow-up): this key set -- same
            # `operations` vocabulary, same `unsupported: ["upsert"]`
            # -- is now IDENTICAL to `atomic_mutation`'s own entry
            # above in every field except its own name, and that
            # sibling capability declares `"partial"` for this exact
            # combination (a vocabulary with one real, permanent
            # capability gap in it). Declaring `"enabled"` here for
            # the identical situation would have been this peer
            # contradicting its own declaration convention -- the
            # v1.1 design text that said `"enabled"` was itself the
            # self-contradiction the review caught, not a deliberate
            # distinction from `atomic_mutation`'s own status.
            "cross_entity_mutation": {"status": "partial", "operations": ["insert", "update", "delete"], "unsupported": ["upsert"]},
            # WP-5 (design v1.2 R-7 flip): single source of truth is
            # `config.control_plane_status`, composition-root-injected
            # (`FoundationConfig.from_env`'s own `MITATEDB_CONTROL_
            # PLANE_STATUS`, or a direct constructor value for a
            # conformance adapter) -- never a hardcoded literal here,
            # so the declaration and whatever `/control/v1` surface
            # this deployment/adapter actually runs cannot drift apart
            # (R-7: "宣言値と enforce 値が同一ソースから出ることを構造
            # で保証する").
            "control_plane": {"status": config.control_plane_status},
            # Contract 1.7.0 (subordinate ruling 12, D-1 (3)): three new
            # capabilities, honestly declared `unavailable` in the SAME
            # commit as the provisional gate rejecting every field each
            # one governs (`ApplicationRuntime.read`/`.transact`,
            # `ApplicationDeveloper.create_entity`/`.add_field` above (in `cell.py`);
            # `http.py`'s `post_query`/`post_mutate`/
            # `post_cross_entity_mutate`/`post_schema`) -- P-3. WP-3a
            # (`constraint_declarations`), WP-3b (`dry_run`) and WP-3d
            # (`request_budget`) each flip their own entry in the same
            # commit that removes the corresponding gate above (in `cell.py`).
            #
            # Phase 9 WP-3a: flipped to `enabled` -- `enum`/`nullable`
            # declaration, enforcement (`field_types.check_declared_
            # value`'s new `constraints` argument), catalog round-trip
            # (`catalog()`'s new `field_constraints` key), and
            # `alter_field` all land in this SAME commit as this flip
            # (D-1 (4): "宣言と挙動は同一コミットである").
            "constraint_declarations": {"status": "enabled"},
            # Phase 9 WP-3b: flipped to `enabled` -- `ApplicationRuntime.
            # transact`/`ApplicationDeveloper.create_entity`/`.add_
            # field`/`.alter_field` above (in `cell.py`) all execute `dry_run`/`plan`
            # for real now (`cell.py::ApplicationCell.transact`/
            # `.create_collection`/`.add_field`/`.alter_field`), and
            # the corresponding `http.py` gate rows are removed, in
            # this SAME commit (D-1 (4)).
            "dry_run": {"status": "enabled"},
            # Phase 9 WP-3d (design D-6, B-4): flipped to `enabled` --
            # `read`/`transact`/`create_entity`/`add_field`/
            # `alter_field` all narrow their own effective bound by a
            # request-presented `budget` for real as of this SAME
            # commit (`config.narrow_limits_by_budget`), and the
            # corresponding `http.py` present-denial gate rows are
            # removed in it too.
            "request_budget": {"status": "enabled"},
        },
        **_surfaces_document_fragment(config),
        **_operation_catalog_url_fragment(config),
        "limits": {
            "batch_items": config.max_batch_items,
            # P35 WP-2 (R-2): distinct-entity bound for `transact()`
            # batches -- see `FoundationConfig.max_batch_entities`'s
            # own comment for why the default (10) is deployment-
            # declared and unrelated to the contract's own non-
            # normative `limits.example_profile.batch_entities: 4`.
            "batch_entities": config.max_batch_entities,
            "result_items": config.max_result_rows,
            "query_complexity": config.max_filter_terms,
            "request_bytes": config.max_request_bytes,
            "schema_objects": config.max_schema_objects,
            # Phase 8 WP-1a (design docs/design/PHASE8_EFFECTIVE_
            # BOUNDS_AND_HYGIENE_V1.md D-1): the 4 application-plane
            # classes this peer previously left entirely unimplemented
            # (see this dict's own sibling `limit_enforcement` block
            # below for the per-class enforcement story). Values come
            # from `FoundationConfig`'s own new fields -- the single
            # source of truth `_limit_gate`/`backend_postgres.py`
            # actually enforce against, never a second, independently
            # drifting literal.
            "execution_ms": config.max_execution_ms,
            "concurrency": config.max_concurrency,
            "requests_per_minute": config.max_requests_per_minute,
            # Phase 8 WP-1a rework 1 (裁定 1, 監督裁定 2026-09-06):
            # published on BOTH surfaces, matching every sibling class
            # above -- `_check_operation_depth` genuinely runs (via
            # `_limit_gate`) on both, so `operation_depth` moved from
            # `unavailable` to `enforced` below, and V1 (c) requires an
            # `enforced` entry to carry this finite value. See
            # `limit_enforcement` below for the full empirical trace.
            "operation_depth": config.max_operation_depth,
            # Phase 9 WP-3a (design §5 U-1 = (β)): the one new class
            # this WP introduces -- bounds how many members a single
            # field's declared `enum` may carry. Same commit as the
            # `constraint_declarations` flip and the real enforcement in
            # `_resolve_field_constraints`/`add_field`/`alter_field`
            # above (`_resolve_field_constraints` in `constraint_resolution.py`) (D-1 (4)).
            "enum_members": config.max_enum_members,
            # Phase 9 WP-3c (design D-5, 追補 2 S-f; 監督裁定集約
            # rulings-r5-r6.md I-10): the two `idempotency` limit
            # classes -- declared in the SAME commit as the
            # `idempotency` capability flip above (C-05 V1 (e)'s own
            # `_CAPABILITY_CONDITIONED` requirement).
            "idempotency_entries": config.idempotency_entries,
            "idempotency_retention_ms": config.idempotency_retention_ms,
        },
        "limit_enforcement": {
            "batch_items": "enforced",
            "batch_entities": "enforced",
            "result_items": "enforced",
            "query_complexity": "enforced",
            # Phase 8 WP-1a (design D-1): `ApplicationCell._limit_gate`
            # now measures every request's own structural byte estimate
            # (`_measure_request_bytes`) on BOTH the in-process and HTTP
            # surface -- the same gate every method below (in `cell.py`) passes
            # through, unconditionally on transport. `http.py`'s own
            # former enforcement-layer override (unconditionally
            # flipping this one key to `"enforced"` for the HTTP
            # surface only, because in-process was genuinely
            # unenforced) is removed in this same commit -- keeping it
            # would have been a meaningless, redundant re-declaration
            # of what this single source of truth already says (R-3).
            "request_bytes": "enforced",
            "schema_objects": "enforced",
            # Phase 8 WP-1a (design D-1 "実装の形" `execution_ms` row):
            # `_limit_gate` computes a wall-clock deadline
            # (`time.monotonic() + max_execution_ms`) and hands it to
            # `self._backend` on every call; `backend_postgres.py`
            # additionally converts it into a real `SET LOCAL
            # statement_timeout`/`lock_timeout`, `backend_sqlite.py`
            # checks it app-side (no native timeout API to delegate
            # to). Declared `reference_wall_clock`, never `enforced` --
            # matching r2db's own identical declaration
            # (`r2db_api/service.py:936-937`) -- because a wall-clock
            # budget cannot be driven to a deterministic N/N+1
            # boundary the way a COUNT-valued bound can (design §4).
            "execution_ms": "reference_wall_clock",
            # Phase 8 WP-1a (design D-1): `_LimitStateHolder.
            # concurrency_slot` (one holder per process/composition
            # root, injected into every `ApplicationCell` -- never
            # per-application, never per-request) now bounds in-flight
            # application-plane requests for real, released in a
            # `finally` on every exit path (success or exception).
            # Phase 10 WP-6b (design D-5 (ii)): that per-process bound
            # only describes the WHOLE deployment while exactly one
            # process may serve this base URL -- `_in_memory_
            # enforcement` (computed above from the deployer's own
            # declared `process_ceilings.data`) degrades this to
            # `deployment_required` once more than one process may.
            "concurrency": _in_memory_enforcement,
            # Phase 8 WP-1a (design D-1): `_LimitStateHolder.
            # acquire_rate` now bounds a credential-keyed 60s sliding
            # window for real. Phase 10 WP-6b: same ceiling-dependent
            # degradation as `concurrency` immediately above.
            "requests_per_minute": _in_memory_enforcement,
            # Phase 8 WP-1a rework 1 (裁定 1, 監督裁定 2026-09-06):
            # `enforced` on BOTH surfaces -- `_check_operation_depth`
            # (module-level, above (in `request_limits.py`)) is wired into `_limit_gate`
            # (`:531`) (in `cell.py`) and genuinely bounds nesting on EVERY request
            # shape every method below (in `cell.py`) builds, in-process included.
            #
            # The WP-1a report's original claim here ("in-process has
            # no request dict to bound, because `insert`/`update`/
            # `delete` take positional/keyword ARGUMENTS, not a single
            # dict") was factually wrong, per the code review that sent
            # this WP back: `_limit_gate` is passed a REAL dict on
            # every one of those call sites -- `insert` builds
            # `{"collection": collection, "values": values}` (`:770`) (in `cell.py`),
            # `update` builds `{"collection": ..., "values": ...,
            # "filters": ...}` (`:832`) (in `cell.py`), `delete` and `transact`
            # likewise -- and `_check_operation_depth` traverses that
            # dict exactly like it traverses any other. Measured
            # directly (WP-1a rework report): with the default
            # `max_operation_depth=8`, a bare `session.insert("t",
            # {"doc": <a value nested 7 dict/list levels deep>})`
            # deterministically raises `LIMIT_EXCEEDED` with
            # `details.limit_class == "operation_depth"` -- no HTTP
            # transport, no `transact()`, involved at all.
            #
            # The asymmetry the ORIGINAL U-1 ruling text anticipated
            # ("in-process 経路に要求 dict が無い形であれば...") does not
            # apply here -- that premise (no request dict in-process)
            # does not hold, so the rework ruling (裁定 1) directs this
            # WP not to invoke that escape hatch. What DOES differ
            # between the two surfaces is only WHICH nesting position a
            # depth attack has to use to reach the same bound: the
            # in-process `insert`/`update`/`delete` methods have no
            # parameter position for an added `where`/`filters` clause
            # on `insert` specifically (so a depth attack against THAT
            # one operation, via THAT one added nesting level, can only
            # be presented through `session.transact()`, exactly like
            # the HTTP surface's own `post_mutate` always does) -- but
            # arbitrarily deep VALUE content (e.g. a nested JSON
            # column) is a real, present nesting vector on every
            # in-process entry point already, and that is what the
            # measurement above exercises. `test_c05_limit_declaration_
            # agreement.py::_drive_operation_depth`'s own flat-insert-
            # plus-`where` recipe is confirmed (WP-1a rework report) to
            # drive this class successfully for `MitateDB-api` too, via
            # `iso.attempt_mutation`'s "insert"+`where_field` path,
            # which the in-process conformance adapter itself routes
            # through `session.transact()` whenever a filter is
            # supplied for `insert` -- the SAME dispatcher
            # `expected_revision`/`unique_key` already route through,
            # for the SAME "present it to the real dispatcher, do not
            # decide the answer in the adapter" reason (this module's
            # own (in `cell.py`) pre-existing comment on that dispatcher).
            "operation_depth": "enforced",
            # Phase 9 WP-3a: `_resolve_field_constraints`/`add_field`/
            # `alter_field` above (`_resolve_field_constraints` in `constraint_resolution.py`) check `enum_members` before anything
            # is created or altered -- genuinely `enforced` on both
            # surfaces (in-process and HTTP alike route through the
            # same `cell.py` methods).
            "enum_members": "enforced",
            # Phase 9 WP-3c (design D-5, I-10): `_idempotency_check`
            # (`cell.py`) genuinely refuses a new record with
            # `LIMIT_EXCEEDED`/`idempotency_entries` once this
            # Application's own retained-record count (after
            # reclaiming elapsed ones) meets the deployed bound --
            # deterministically `enforced`, same as every other
            # COUNT-valued class above. `idempotency_retention_ms` is
            # a wall-clock DURATION, not a count -- like `execution_
            # ms`, it cannot be driven to a deterministic N/N+1
            # boundary within a test's own bounded run time (non
            # vacuity note, work order §2 WP-3c: "retention の期限切れ
            # 検査は行わない"), so it is declared `reference_wall_
            # clock`, matching `execution_ms`'s own identical
            # reasoning above. WP-6d-i (design D-5 (ii) addendum (1))
            # is what keeps this bound genuinely `enforced` under
            # concurrent writers on the PostgreSQL backend (on THIS
            # peer: a session-level `pg_advisory_lock` taken in
            # `backend_postgres.py::idempotency_reserve`, the count
            # committed right after it, and the lock released by
            # `idempotency_unlock` on the bound connection -- a
            # platform-specific realization, design D-13, distinct from
            # r2db's same-transaction xact lock); this declaration site
            # itself predates that WP and
            # is unchanged by it, since the class was already
            # `enforced` for the single-writer case this dict-literal
            # declares.
            "idempotency_entries": "enforced",
            "idempotency_retention_ms": "reference_wall_clock",
        },
        # `CredentialStore.assert_active` (auth.py) is invoked by
        # `__authorize` above (in `cell.py`) on every single session operation, with
        # no cache: revoke/disable/state-unavailable propagation is
        # synchronous.
        "authorization_propagation_bound_ms": 0,
        "application_scope": application_id,
        "role": role
    }
