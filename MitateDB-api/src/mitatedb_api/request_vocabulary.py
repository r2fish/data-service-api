"""MitateDB-api request-facing vocabulary constants (CE5).

A pure leaf: the transact() operation vocabulary, the per-operation-type
key sets, the field-type and filter-operator vocabularies, and the delete
consequence text `ApplicationCell` (`cell.py`) reads by name -- no logic
beyond the literals themselves."""

# The common contract's own mutation vocabulary
# (`structured_operations.allowed_mutations`). Of the four names, only
# `upsert` is still refused unconditionally by `transact()` below (in `cell.py`) -- this
# peer has no `upsert` anywhere on its public surface, dedicated method or
# batch alike. Presenting `upsert` to `transact()` is a capability gap in
# this entry point, not a malformed/unrecognized request, so it is
# distinguished from a name outside this vocabulary entirely (still
# `ValidationError`).
#
# P3 WP-1 (round 2 instruction #3), UPDATE by P3-D2 (design v1.2 R-5,
# WP-1.5): this seam refactor originally kept `transact()`'s own
# mixed-batch semantics IDENTICAL to before the refactor -- `update`/
# `delete`/`upsert` were ALL refused unconditionally here (in `cell.py`), on BOTH
# backends, regardless of what else shared the batch. That was a known,
# tracked, open contract-interpretation question
# (`docs/design/DESTRUCTIVE_CONFIRMATION_V1.md` §8.1(b): is the contract's
# "A batch is atomic unless explicitly declared best_effort" language
# scoped to whichever operation types a given peer's OWN batch dispatcher
# happens to execute, or to the general mutation vocabulary regardless of
# batch-specific support?) that WP-1 deliberately left open, ordering its
# resolution separately as "WP-1.5". WP-1.5 (P3-D2, design v1.2 second
# round B-2) resolves it for THIS peer by converging real behavior onto
# the existing declaration (`atomic_mutation.operations: ["insert",
# "update", "delete"]`, unchanged by this WP -- no capability envelope
# expansion): `transact()` now executes `update`/`delete` for real,
# atomically with everything else in the same batch, through the
# identical backend-independent validation/confirmation logic the
# dedicated `update`/`delete` methods already use (`_validate_update`/
# `_validate_delete_confirmation`, shared via `_plan_operation` below (in `cell.py`)
# since P35 WP-2's own two-pass restructuring -- there is no second,
# batch-specific copy of any of that logic). Both
# contract readings §8.1(b) considers are therefore simultaneously true
# for this peer post-WP-1.5 (the batch dispatcher itself executes
# update/delete, AND the general vocabulary is executed via a real entry
# point) -- the interpretation question itself is not resolved at the
# contract level (that CCR stays on the tracked-questions ledger for the
# requester), but it no longer has any REAL consequence on this peer,
# because both answers now agree. `upsert` alone remains a real capability
# gap (`CapabilityError`), since no execution path for it exists anywhere
# on this peer, batched or not. The actual EXECUTION each of `insert`/
# `update`/`delete` delegates to (`self._backend.insert_in_transaction`/
# `update_in_transaction`/`delete_in_transaction`) is backend-swappable,
# as it already was for `insert` alone before this WP.
_CONTRACT_MUTATION_VOCABULARY = {"insert", "update", "upsert", "delete"}

# The only operation-dict keys `_plan_operation`'s "insert" branch below (in `cell.py`)
# actually reads. Any other key (`expected_revision`, `idempotency_key`, or
# any other capability this entry point does not implement) must be rejected
# before this operation's own row is ever built -- silently ignoring an
# unrecognized key would let a request carrying a real semantic (a revision
# precondition, in particular) execute as if that semantic were honored,
# when it was never even inspected. Contract `versioning.unknown_capability`:
# "The service returns CAPABILITY_UNSUPPORTED without executing a fallback."
# Phase 9 WP-3c (design D-5, I-1/I-3; 監督裁定集約 rulings-r5-r6.md I-1):
# `idempotency_key` is now a real, recognized key on every operation type
# -- the port's own `fold_batch_idempotency_key` (`conformance-tests/
# adapter.py`) folds ONE batch-wide key onto EVERY operation dict before
# ever calling `ApplicationCell.transact` (never this method's own
# `idempotency_key=` keyword, which exists for a caller -- `http.py::
# post_mutate`/`post_cross_entity_mutate` -- that already has the SINGLE
# request-level value in hand and need not repeat it onto every item).
# `transact()` itself derives its own `idempotency_key` from the FIRST
# operation that carries one whenever its own keyword argument is `None`
# (see its own docstring) -- this key set's only job is to keep that
# per-operation carrier from being rejected as an unrecognized field by
# the excess-key checks below (in `cell.py`); `_plan_operation` never reads it into any
# execution payload (every branch extracts fields by explicit name, never
# `**operation`).
_TRANSACT_INSERT_KEYS = {"type", "collection", "values", "idempotency_key"}

# P3-D2 (WP-1.5): same "reject an unread capability-shaped key before
# execution" reasoning as `_TRANSACT_INSERT_KEYS` above, for the two
# newly-converged operation types. `values` is accepted on the "delete"
# key set even though delete execution never reads it -- contract
# `Mutation` (spec `definitions.Mutation`) declares `values` as a generic
# property of every mutation operation, delete included (no per-operation
# `if`/`then` narrows it away for `"operation": "delete"`), so a
# well-formed delete request naming an empty `values: {}` is ordinary wire
# shape, not a capability-gap signal -- exactly the same treatment r2db-api
# independently gives the identical wire shape for its own delete.
# m-4 (independent review, WP-1.5 follow-up): this is also a real
# IMPLEMENTATION-LEVEL necessity, not merely a contract-shape nicety --
# `conformance/conformance_adapter_mitatedb.py::attempt_batch_with_
# addresses` builds every batch item's `"values"` key unconditionally
# (`dict(op.values or {})`, regardless of `op.operation`), so a `delete`
# BatchOperation ALWAYS carries a `"values"` key on the wire, empty or
# not. If this key set rejected it, the C-06 V2b-wire vector (and
# `_batch_delete_capability_absent`'s own probe) could never reach this
# peer's real batch-delete entry point at all -- accepting `values` here
# is therefore a necessary condition for that adapter's batch-delete path
# to be exercisable, not just a permissive reading of the contract shape.
# Neither key set lists `expected_revision`/`unique_key`: those remain a
# real capability gap on `update`/`delete` here exactly as they already
# are on `insert` above (this peer implements no revision-precondition/
# uniqueness concept anywhere).
_TRANSACT_UPDATE_KEYS = {"type", "collection", "values", "filters", "idempotency_key"}
_TRANSACT_DELETE_KEYS = {"type", "collection", "values", "filters", "destructive", "confirm", "idempotency_key"}

# Foundation field-type vocabulary. This is a shared, backend-independent
# VOCABULARY (which declared type names this API accepts at all) -- the
# mapping from one of these names to a backend's own NATIVE column type
# syntax is each backend's own concern (`backend_sqlite._TYPES` /
# `backend_postgres._TYPES`) (in `postgres_types.py`), since the two engines' native type systems
# differ (R-3: execution, including physical schema, is backend-specific;
# only the request-level vocabulary is shared).
_FIELD_TYPE_VOCABULARY = frozenset({"text", "integer", "real", "boolean", "json"})

# Conformance-review finding (WP-5a, C-12 reverse condition): every one of
# these three is a real member of the common contract's own filter-operator
# vocabulary (`structured_operations.allowed_query_operators`) that this
# peer declares `unsupported` in its own `structured_query` capability
# entry below (in `capabilities_document.py`) -- `capability_status.rules`: "optional target operations
# ... must fail with CAPABILITY_UNSUPPORTED". `matches` already raised
# `CapabilityError` correctly; `contains`/`is_null` used to fall through to
# the generic "not a filter operator this peer implements at all" branch
# below (in `cell.py`) and raise `ValidationError` (-> `VALIDATION_FAILED`) instead -- a
# real, observable mismatch between this peer's own declaration and its
# own behavior, discovered by the common conformance suite's C-12 reverse
# direction (`conformance-tests/test_c12_capability_agreement.py`)
# presenting a real, contract-shaped request rather than assuming this
# peer's behavior. All three now share one code path in `_bind_filters`
# below (in `cell.py`).
_UNSUPPORTED_CONTRACT_OPERATORS = {"contains", "matches", "is_null"}

# WP-5 (docs/design/DESTRUCTIVE_CONFIRMATION_V1.md R-5, contract
# `destructive_confirmation`): declare-and-echo confirmation for `delete`,
# this peer's only destructive operation (`drop_entity`/`drop_index` are
# `SurfaceAbsent` -- `create_collection` has no drop parameter anywhere on
# this peer's public surface -- and `revoke_credential`'s "last control
# credential" gate is a control-plane concept this peer's provisioning
# facade does not implement at all, per its own `control_plane:
# unavailable` capability declaration).
#
# P3 WP-1 (round 2 instruction #5) UPDATE: the paragraph immediately below
# this one used to conclude that NO state fingerprint was needed in the
# delete phrase, on the strength of this peer having no way to mutate an
# existing collection's shape at all. `add_field` (this same WP) breaks
# that premise directly -- it IS "another schema change" on an existing
# collection, the exact dimension the original argument depended on being
# absent. The phrase construction below therefore now DOES include a
# state fingerprint (`@schema_revision=<n>`, `_delete_confirmation_phrase`),
# bumped by both `create_collection` and `add_field` (`backend.
# StorageBackend.schema_revision`/each backend's own bump-on-DDL) -- the
# same shape as r2db-api's own Q1-D10 answer to an analogous question for
# ITS OWN, different, real capability (that peer's own drop+recreate of an
# entity under the same name), independently arrived at here for a
# different real capability (`add_field`) reaching the same underlying
# risk (a delete confirmation issued against one schema shape, then
# replayed after the schema changed underneath it). Contract
# `phrase_construction` does not fix the phrase's own spelling (Q1-D2), so
# adding this segment is not a compatibility break.
#
# ORIGINAL REASONING (kept for its own continuing scope -- collection
# EXISTENCE/RE-CREATION, as opposed to an existing collection's shape):
# this peer still has no `drop_entity`/`drop_collection` of any kind
# (`create_collection` raises `ConflictError` if the name already exists,
# and there is no `drop_entity` anywhere on this peer's public surface --
# confirmed by source inspection: `capabilities().schema_operations.
# unsupported` lists `drop_entity` itself), so a collection can still never
# be dropped and recreated under the same name for the rest of this
# process's lifetime -- unlike r2db-api's own re-creatable entities, which
# is what Q1-D10 was originally answering. The schema-revision fingerprint
# added by this WP subsumes that concern anyway (a collection's own
# revision only ever increases; there is no operation on this peer that
# could make an old revision number become live again).
_DELETE_CONSEQUENCE = (
    "The rows matching this delete's filters are permanently removed from "
    "the collection; there is no in-band restore path."
)
# No reversible_alternative and no recovery for the same reason r2db-api's
# OWN data-plane delete declares both null (Q1-D6): this peer has no
# durable, queryable audit trail an operator could use to reconstruct
# removed rows, and no soft-delete/undo mechanism of any kind -- claiming
# either would be untrue.
