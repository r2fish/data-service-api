"""Application-bound structured data cell.

Each cell owns one storage handle. Sessions never accept an application ID;
the application scope comes from the authenticated Principal and the cell
selected by the service. No database-native command is part of this API.

R-3 seam (docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md, WP-1): this
module owns every backend-INDEPENDENT concern -- principal authorization,
request shape/limit validation, identifier syntax validation, capability
declaration (the single source of truth is `ApplicationRuntime.
capabilities()` below), error classification (the `errors.FoundationError`
hierarchy), and declare-and-echo confirmation-phrase construction. Actual
storage EXECUTION is delegated to a `backend.StorageBackend`-shaped object
(`backend_sqlite.SQLiteBackend` -- the default, and the only backend this
WP wires into the public in-process composition -- or
`backend_postgres.PostgresBackend`, exercised directly by
`tests/test_postgres.py`). Swapping which backend answers a given
`ApplicationCell`'s calls is therefore a single-argument change
(`ApplicationCell(..., backend=...)`); this file itself never imports
`sqlite3`/`psycopg` or references either driver's own exception types.
"""

from contextlib import contextmanager
from dataclasses import asdict, dataclass, is_dataclass
import hashlib
import json
import time
from threading import Lock, RLock

from .audit import AuditSink
from .audit_dispatch import AuditRouter
from .auth import Principal, Role
from .backend import SQL_OPERATOR_TOKENS
from .backend_sqlite import SQLiteBackend
from .config import FoundationConfig
from .errors import (AuditSinkUnavailable, AuthorizationError, CapabilityError,
                     ConflictError, DestructiveConfirmationRequired, NotFoundError,
                     ResourceLimitError, ValidationError)
from .field_types import FOUNDATION_TYPE_TO_CONTRACT_TYPE, check_declared_value
from .identifiers import validate_identifier
from .surfaces import build_surfaces

# The common contract's own mutation vocabulary
# (`structured_operations.allowed_mutations`). Of the four names, only
# `upsert` is still refused unconditionally by `transact()` below -- this
# peer has no `upsert` anywhere on its public surface, dedicated method or
# batch alike. Presenting `upsert` to `transact()` is a capability gap in
# this entry point, not a malformed/unrecognized request, so it is
# distinguished from a name outside this vocabulary entirely (still
# `ValidationError`).
#
# P3 WP-1 (round 2 instruction #3), UPDATE by P3-D2 (design v1.2 R-5,
# WP-1.5): this seam refactor originally kept `transact()`'s own
# mixed-batch semantics IDENTICAL to before the refactor -- `update`/
# `delete`/`upsert` were ALL refused unconditionally here, on BOTH
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
# `_validate_delete_confirmation`, shared via `_plan_operation` below
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

# The only operation-dict keys `_plan_operation`'s "insert" branch below
# actually reads. Any other key (`expected_revision`, `idempotency_key`, or
# any other capability this entry point does not implement) must be rejected
# before this operation's own row is ever built -- silently ignoring an
# unrecognized key would let a request carrying a real semantic (a revision
# precondition, in particular) execute as if that semantic were honored,
# when it was never even inspected. Contract `versioning.unknown_capability`:
# "The service returns CAPABILITY_UNSUPPORTED without executing a fallback."
_TRANSACT_INSERT_KEYS = {"type", "collection", "values"}

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
_TRANSACT_UPDATE_KEYS = {"type", "collection", "values", "filters"}
_TRANSACT_DELETE_KEYS = {"type", "collection", "values", "filters", "destructive", "confirm"}

# Foundation field-type vocabulary. This is a shared, backend-independent
# VOCABULARY (which declared type names this API accepts at all) -- the
# mapping from one of these names to a backend's own NATIVE column type
# syntax is each backend's own concern (`backend_sqlite._TYPES` /
# `backend_postgres._TYPES`), since the two engines' native type systems
# differ (R-3: execution, including physical schema, is backend-specific;
# only the request-level vocabulary is shared).
_FIELD_TYPE_VOCABULARY = frozenset({"text", "integer", "real", "boolean", "json"})

# Conformance-review finding (WP-5a, C-12 reverse condition): every one of
# these three is a real member of the common contract's own filter-operator
# vocabulary (`structured_operations.allowed_query_operators`) that this
# peer declares `unsupported` in its own `structured_query` capability
# entry below -- `capability_status.rules`: "optional target operations
# ... must fail with CAPABILITY_UNSUPPORTED". `matches` already raised
# `CapabilityError` correctly; `contains`/`is_null` used to fall through to
# the generic "not a filter operator this peer implements at all" branch
# below and raise `ValidationError` (-> `VALIDATION_FAILED`) instead -- a
# real, observable mismatch between this peer's own declaration and its
# own behavior, discovered by the common conformance suite's C-12 reverse
# direction (`conformance-tests/test_c12_capability_agreement.py`)
# presenting a real, contract-shaped request rather than assuming this
# peer's behavior. All three now share one code path in `_bind_filters`
# below.
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


def _canonical_where_json(filters):
    """Canonical JSON serialization of a `delete` request's own selection
    (contract `phrase_construction` rule "scope-included"): each `Filter`
    becomes a key-sorted object; the outer list's own ORDER is preserved,
    not sorted (an intentional choice, matching r2db-api's own documented
    n-6 finding: two requests presenting the identical predicate set in a
    different order are treated as different requests, not folded onto one
    phrase -- this peer does not treat where-clause order as insignificant
    on the caller's behalf).

    Deliberately no `default=str` (r2db-api WP-3 followup m-7): every
    `Filter.value` reaching this point has already passed `_bind_filters`'s
    own `ApplicationCell._normalize_value` (dict/list/bool/str/int/float/
    None only, raising `ValidationError` for anything else) by
    construction -- `delete` below always calls this on the caller's own,
    un-encoded `filters` argument BEFORE `_bind_filters` runs, but the same
    shape guarantee already holds because `delete` requires `filters` be a
    non-empty list of `Filter` instances first -- so a value this
    `json.dumps` cannot serialize natively would mean that invariant broke
    elsewhere; surfacing that as an immediate `TypeError` here is more
    honest than silently collapsing it into a string that could coincide
    with a different value's own string form.
    """
    payload = [{"field": f.field, "operator": f.operator, "value": f.value} for f in filters]
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _delete_confirmation_phrase(collection, filters, schema_revision):
    """`DELETE <collection> @where=<digest16> @schema_revision=<n>` --
    digest16 is the first 16 hex characters of the SHA-256 of
    `_canonical_where_json(filters)`; `schema_revision` is this
    application's current schema-revision counter (P3 WP-1 round 2
    instruction #5 -- see the module-level comment above
    `_DELETE_CONSEQUENCE` for why this was added). `collection` must
    already be identifier-validated by the caller (contract
    `phrase_construction` rule "only identifier-validated target names")
    -- `ApplicationCell.delete` below always calls this only after
    `ApplicationCell._identifier(collection, ...)` has succeeded.

    Length: identifiers are bounded to 63 characters
    (`identifiers._IDENTIFIER`), so `"DELETE " (7) + collection (63) +
    " @where=" (8) + digest16 (16) = 94` (the original, pre-schema-
    revision proof) `+ " @schema_revision=" (18) + digits(schema_revision)`.
    `schema_revision` is a plain, monotonically-increasing non-negative
    counter incremented once per `create_collection`/`add_field` call this
    process ever makes -- bounding its own decimal digit count to 144
    (`94 + 18 + 144 = 256`, exactly the contract `confirmation` field's own
    `maxLength`) covers every value up to `10**144`, a number of schema
    mutations no real process could ever perform (bounded, in this
    foundation, by `FoundationConfig.max_schema_objects`/`max_fields`
    per application in the first place) -- so the bounded-digest escape
    hatch contract `phrase_construction` rule "bounded" describes is never
    actually needed on this peer, exactly as the original (pre-schema-
    revision) proof already concluded. n-1 correction (independent
    review, carried forward unchanged): the `assert` below is NOT itself
    what proves this invariant -- `assert` statements are stripped
    entirely when Python runs under `-O`/`PYTHONOPTIMIZE`, so it must
    never be the only thing standing between this function and an
    over-length phrase. The real proof is the arithmetic above; the assert
    is a development-time backstop that fixes this reasoning in an
    executable form, not a substitute for it, and not load-bearing under
    `-O`.
    """
    digest = hashlib.sha256(_canonical_where_json(filters).encode("utf-8")).hexdigest()[:16]
    phrase = "DELETE " + collection + " @where=" + digest + " @schema_revision=" + str(schema_revision)
    assert len(phrase) <= 256, "delete confirmation phrase exceeds contract confirmation maxLength"
    return phrase


@dataclass(frozen=True)
class Filter:
    field: str
    operator: str
    value: object


def _as_traversable(item):
    """Phase 8 WP-1a (design D-1): `_measure_request_bytes`/`_check_
    operation_depth` below traverse the JSON-safe request structures this
    module's own gate builds internally (a plain dict of the method's own
    arguments) -- but those arguments legitimately carry this module's own
    `Filter` frozen dataclass (both `read`/`update`/`delete`/`transact`
    reach the gate with `filters` already bound to `Filter` instances,
    never plain dicts -- see `http.py::_predicate_to_filter`/the
    in-process conformance adapter, both of which construct `Filter`
    objects before calling into this module). A generic dataclass ->
    dict conversion here (rather than a `Filter`-specific special case)
    keeps both traversal functions correct for any dataclass value a
    future request shape might carry, with no second, type-specific
    branch to keep in sync."""
    if is_dataclass(item) and not isinstance(item, type):
        return asdict(item)
    return item


def _measure_request_bytes(request, bound):
    """r2db `limits.py::ResourceLimits.check_request` (`:37-70`) and this
    peer's own structural estimate (design D-1 "実現方式") are
    independent realizations of the SAME measurement (P-6): str is
    `len * 4`, bytes is `len`, a scalar/`None`/bool is 8, a container
    (dict/list/tuple/set) costs 2 plus an early per-container
    `bound // 8` element-count reject -- so both peers refuse the same
    clearly-oversized request shape at the same class (`request_bytes`),
    even though neither shares code. Raises `errors.ResourceLimitError`
    (`limit_class="request_bytes"`) the moment either the running total or
    a single container's own element count crosses `bound`.

    Cycle detection is scoped to the CURRENT ANCESTOR PATH (each stack
    frame carries its own `frozenset` of container ids seen on the way
    down to it), not to every container ever visited across the whole
    structure -- the same object legitimately appearing more than once as
    UNRELATED siblings (e.g. a batch built from `[operation] * n`, a real
    shape this package's own tests construct) is not a cycle and must not
    be rejected as one; only a container that is its own ancestor (truly
    self-referential) is."""
    total = 0
    stack = [(request, frozenset())]
    while stack:
        raw_item, ancestors = stack.pop()
        item = _as_traversable(raw_item)
        child_ancestors = ancestors
        if isinstance(item, (dict, list, tuple, set)):
            marker = id(item)
            if marker in ancestors:
                raise ValidationError("cyclic request structures are not supported")
            child_ancestors = ancestors | {marker}
        if isinstance(item, dict):
            total += 2
            if len(item) > bound // 8:
                raise ResourceLimitError("request size limit exceeded", limit_class="request_bytes")
            stack.extend((k, child_ancestors) for k in item.keys())
            stack.extend((v, child_ancestors) for v in item.values())
        elif isinstance(item, (list, tuple, set)):
            total += 2
            if len(item) > bound // 8:
                raise ResourceLimitError("request size limit exceeded", limit_class="request_bytes")
            stack.extend((c, child_ancestors) for c in item)
        elif isinstance(item, str):
            total += len(item) * 4
        elif isinstance(item, (bytes, bytearray)):
            total += len(item)
        elif item is None or isinstance(item, (bool, int, float)):
            total += 8
        else:
            total += 8
        if total > bound:
            raise ResourceLimitError("request size limit exceeded", limit_class="request_bytes")


def _check_operation_depth(request, bound):
    """r2db `limits.py::ResourceLimits.check_depth` (`:77-90`), same
    "independent realization of the same contract-level measurement"
    relationship as `_measure_request_bytes` above (P-6): counts nesting
    levels across dict/list/tuple/set containers (a `Filter` dataclass
    counts as one such container, via `_as_traversable`), raising
    `errors.ResourceLimitError` (`limit_class="operation_depth"`) the
    moment the nesting exceeds `bound`. Runs BEFORE any content
    validation of `request` (design D-1 "検査の形": the depth check is
    part of the gate, which runs before `_prepare_values`/`_bind_filters`/
    `_validate_update`/`_validate_delete_confirmation`), mirroring r2db's
    own call order (`service.py`: `check_request` / `check_depth` both
    precede the backend dispatch that would otherwise reject a malformed
    shape first).

    Cycle detection is scoped to the current ancestor path, exactly like
    `_measure_request_bytes` above -- see that function's own docstring
    for why (the same object appearing more than once as unrelated
    siblings, e.g. `[operation] * n`, is not a cycle)."""
    stack = [(request, 0, frozenset())]
    while stack:
        raw_item, current, ancestors = stack.pop()
        item = _as_traversable(raw_item)
        if not isinstance(item, (dict, list, tuple, set)):
            continue
        marker = id(item)
        if marker in ancestors:
            raise ValidationError("cyclic request structures are not supported")
        child_ancestors = ancestors | {marker}
        next_depth = current + 1
        if next_depth > bound:
            raise ResourceLimitError("operation nesting exceeds the configured limit", limit_class="operation_depth")
        children = item.values() if isinstance(item, dict) else item
        stack.extend((child, next_depth, child_ancestors) for child in children)


class _LimitStateHolder:
    """Phase 8 WP-1a (design D-1 "置き場は実装WPが新設する (1プロセス1個)"):
    the process-wide (one per composition root / one per isolated
    conformance-adapter instance) limit-enforcement STATE this WP adds --
    as distinct from the per-request CHECKS (`_measure_request_bytes`/
    `_check_operation_depth` above), which need no shared state at all.

    Holds exactly two things, both scoped per design D-1 "カウンタの
    スコープ": (i) a `requests_per_minute` sliding window PER CREDENTIAL
    (`principal.credential_id`-keyed, r2db `service.py::_acquire_rate`
    `:1156-1163` equivalent), and (ii) a single `concurrency` in-flight
    counter for the WHOLE deployment/process (r2db `service.py::_slot`
    `:1133-1144` equivalent) -- never per-application, never per-request.

    Deliberately NOT a method on `ApplicationRuntime` (rebuilt fresh on
    every request -- `__slots__` has no room, design D-1 "状態の置き場")
    and NOT a method on a single `ApplicationCell` (would only bound one
    application's own traffic, not the deployment as a whole). Built
    exactly once by the composition root (`main.build_app`) or by a
    conformance adapter's own `__init__`/`isolated_application_surface`,
    and injected into every `ApplicationCell` that instance constructs --
    the same one-per-process injection shape `audit_dispatch.AuditRouter`
    already established (`cell.py`'s own pre-existing `:308-318` comment,
    `main.py`'s identical wiring)."""

    def __init__(self):
        self._rate_windows: dict = {}
        self._rate_lock = Lock()
        self._active = 0
        self._active_lock = Lock()

    def acquire_rate(self, credential_id, bound):
        now = time.monotonic()
        with self._rate_lock:
            window = self._rate_windows.setdefault(credential_id, [])
            window[:] = [stamp for stamp in window if now - stamp < 60]
            if len(window) >= bound:
                raise ResourceLimitError("request rate limit exceeded", limit_class="requests_per_minute")
            window.append(now)

    @contextmanager
    def concurrency_slot(self, bound):
        with self._active_lock:
            if self._active >= bound:
                raise ResourceLimitError("concurrency limit exceeded", limit_class="concurrency")
            self._active += 1
        try:
            yield
        finally:
            with self._active_lock:
                self._active -= 1


class ApplicationCell:
    """A private application storage boundary.

    The default backend (`backend_sqlite.SQLiteBackend`) is used only as a
    deterministic local foundation backend. `backend_postgres.
    PostgresBackend` is the production-shaped Cloud SQL adapter (WP-1);
    both keep this class's own authority shape identical, never exposing a
    raw database connection to Application code.
    """

    def __init__(self, application_id, config=None, audit=None, guard=None, backend=None,
                 audit_router=None, limit_holder=None):
        validate_identifier(application_id, "application_id")
        self.application_id = application_id
        self.config = config or FoundationConfig()
        self.__record = (audit or AuditSink()).record
        self.__guard = guard
        self._backend = backend if backend is not None else SQLiteBackend()
        # Phase 4 (design docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md
        # D-1/D-10): the durable-audit dispatch router -- a caller-shared
        # `audit_dispatch.AuditRouter` (`main.build_app` constructs exactly
        # ONE per process and hands it to every `ApplicationCell` AND
        # every credential store it builds, so denial coalescing and the
        # buffer are shared process-wide, not duplicated per cell) or a
        # private default (in-memory, unshared -- every pre-Phase-4 caller
        # of this constructor that does not pass this parameter gets a
        # working, isolated durable trail nobody else observes, exactly
        # like `audit=None` already defaults to a private `AuditSink()`).
        self.__audit_router = audit_router if audit_router is not None else AuditRouter()
        # Back-compat surface for `conformance/conformance_adapter_
        # mitatedb.py::entities()`'s own pre-existing direct `cell._db.
        # execute(...)` reach-around (predates this WP's seam refactor;
        # that adapter is unaffected by this WP and keeps working
        # unchanged because `SQLiteBackend.raw_connection` republishes the
        # exact same `sqlite3.Connection` this attribute used to hold
        # directly). Backends with no such raw handle (`PostgresBackend`)
        # leave this `None` -- nothing in this WP relies on it for that
        # backend.
        self._db = getattr(self._backend, "raw_connection", None)
        self._lock = RLock()
        # Phase 8 WP-1a (design D-1): `None` (every pre-WP-1a caller --
        # this repository's own tests, any direct construction) gets a
        # PRIVATE, unshared holder -- exactly like `audit_router=None`
        # already defaults to a private `AuditRouter()` two lines above --
        # so a lone `ApplicationCell()` still enforces its own 4 classes
        # correctly, just without sharing state with any sibling cell (the
        # composition root is what actually needs the SHARED instance;
        # see `main.py`/`service.py`/both conformance adapters, which all
        # construct exactly one holder and pass it to every cell they
        # build).
        self.__limit_holder = limit_holder if limit_holder is not None else _LimitStateHolder()

    @contextmanager
    def _limit_gate(self, principal, request=None, *, request_id=None):
        """Phase 8 WP-1a rework 1 (裁定 5, 監督裁定 2026-09-06; design D-1
        "順序"/"実装の形"): the single choke every application-plane
        operation below (`insert`/`read`/`update`/`delete`/`transact`,
        `catalog`/`schema_revision` immediately above, `ApplicationRuntime.
        capabilities()`, and `ApplicationDeveloper`'s own schema
        operations) passes through, immediately after its own
        `_require_data`/`_require_developer` call -- in the r2db-matching
        order `requests_per_minute -> concurrency -> request_bytes ->
        operation_depth -> deadline` (r2db `service.py::_slot`
        `:1133-1144`/`:1156-1163`, `_query_outcome`/`_mutate_outcome`
        `:996-999`/`:1037-1039`).

        `request` is the JSON-safe structure this call's own arguments
        amount to (built by the caller, immediately before this is
        entered) -- `None` for an operation with no client-supplied
        structure to bound (`catalog`/`schema_revision`/`capabilities`):
        those still pass through the rate/concurrency wrap (mirrors r2db
        `catalog()`/`schema()`/`capabilities()`, which all wrap with
        `_slot` but never call `check_request`/`check_depth`), just never
        the request_bytes/operation_depth checks. (裁定 5 correction: an
        earlier revision of this docstring already stated this, but the
        code did not yet match it -- `catalog`/`schema_revision`/
        `capabilities` were NOT actually wrapped by this gate until this
        rework commit; see each of those three methods' own docstrings
        for the measured, pre-rework gap this closes.)

        Yields the computed wall-clock `deadline` (`time.monotonic()`
        seconds) for the caller to hand to `self._backend`."""
        self.__limit_holder.acquire_rate(principal.credential_id, self.config.max_requests_per_minute)
        with self.__limit_holder.concurrency_slot(self.config.max_concurrency):
            if request is not None:
                _measure_request_bytes(request, self.config.max_request_bytes)
                _check_operation_depth(request, self.config.max_operation_depth)
            deadline = time.monotonic() + self.config.max_execution_ms / 1000
            yield deadline

    def _make_audit_hook(self, principal, *, event_class, operation, target_kind, target_id=None, request_id=None):
        """Phase 4 (design D-2): builds the `audit_hook.ApplicationAuditHook`
        a backend method (or `transact` below) calls itself, immediately
        before its own commit point. Every field the durable row needs is
        already resolved here -- the backend/batch loop supplies none of
        it, only the fail-closed/buffer-class decision itself."""
        return self.__audit_router.make_pre_commit_hook(
            event_class=event_class, request_id=request_id, application_id=self.application_id,
            actor_type="application_credential", actor_id=getattr(principal, "credential_id", None),
            role=getattr(getattr(principal, "role", None), "value", None), operation=operation,
            target_kind=target_kind, target_id=target_id,
        )

    def _route_delete_confirmation_denial(self, principal, collection, *, request_id=None):
        """Phase 4 (design D-3): `DESTRUCTIVE_CONFIRMATION_REQUIRED` is
        one of D-3's own durable-range denial codes -- routed (coalesced)
        through the same `audit_dispatch.AuditRouter` every other durable
        denial uses. Called from both `delete`'s own dedicated call site
        and `transact`'s pass-1 planning loop (`_plan_operation`'s delete
        branch raises the identical `errors.DestructiveConfirmationRequired`
        through the SAME `_validate_delete_confirmation` choke -- there is
        no second copy of this dispatch)."""
        self.__audit_router.route_denial(
            reason_code="DESTRUCTIVE_CONFIRMATION_REQUIRED", event_class="destructive_data_operation",
            request_id=request_id, application_id=self.application_id, actor_type="application_credential",
            actor_id=getattr(principal, "credential_id", None),
            role=getattr(getattr(principal, "role", None), "value", None), operation="delete",
            target_kind="collection", target_id=collection,
        )

    def _push_data_operation_event(self, principal, *, operation, target_id=None, request_id=None):
        """Phase 4 (design D-4/P4-D5): buffer-class emit for an ordinary
        (successful) data operation -- query/insert/update. Unlike
        r2db-api, this peer recorded NONE of these before Phase 4 (design
        §7.3: "現状は未記録"); this is the new emit site P4-D5 requires so
        both peers record the identical event stream."""
        self.__audit_router.push_buffer_event(
            event_class="data_operation", request_id=request_id, application_id=self.application_id,
            actor_type="application_credential", actor_id=getattr(principal, "credential_id", None),
            role=getattr(getattr(principal, "role", None), "value", None), operation=operation,
            target_kind="collection", target_id=target_id,
        )

    def _identifier(self, value, label="identifier"):
        """The one place BOTH stages of identifier validation are always
        applied together (R-3): the shared syntax allowlist
        (`identifiers.validate_identifier`), then this cell's own active
        backend's reserved-name check (`backend.StorageBackend.
        check_reserved` -- backend-specific: SQLite's own `sqlite_
        sequence`/PostgreSQL's own `pg_`-prefixed catalog namespace mean
        nothing to the other engine, R-3 WP-0 m-7)."""
        validate_identifier(value, label)
        self._backend.check_reserved(value, label)
        return value

    def create_collection(self, principal, name, fields, destructive=False, *, request_id=None, field_types=None):
        """Phase 6 WP-3 (design D-3): `field_types`, when given, is a
        `{field_name: contract_type}` map (the 7-word contract vocabulary,
        `field_types.CONTRACT_TYPES`) -- the declared type this call
        records in the registry for that field. A field named in `fields`
        but NOT in `field_types` (or every field, when `field_types` is
        `None` -- every pre-1.6.0-shaped direct caller: this repository's
        own tests, the in-process conformance adapter) gets its declared
        contract type DERIVED from the foundation type it was given
        (`field_types.FOUNDATION_TYPE_TO_CONTRACT_TYPE`) -- the same
        backfill rule `migrations/0006_...upgrade_declared_types.sql`
        applies to pre-existing columns (design §1.5 finding 2a)."""
        self._require_developer(principal, request_id=request_id)
        request = {"name": name, "fields": fields}
        with self._limit_gate(principal, request, request_id=request_id) as deadline:
            name = self._identifier(name, "collection")
            if not isinstance(fields, dict) or not fields:
                raise ValidationError("fields must be a non-empty object")
            if len(fields) > self.config.max_fields:
                # Q1-D11 (design v1.5 §7, supersedes the WP-5 body's own
                # `query_complexity` tagging): this bounds how many columns a
                # single collection DEFINITION may name in one `create_
                # collection` call -- a one-time shape bound on the request
                # itself, not a repeated, finite-resource consumption class.
                raise ValidationError("field limit exceeded")
            if self._backend.schema_count() >= self.config.max_schema_objects:
                raise ResourceLimitError("schema object limit exceeded", limit_class="schema_objects")
            validated_fields = {}
            declared_types = {}
            for field, field_type in fields.items():
                field = self._identifier(field, "field")
                if field_type not in _FIELD_TYPE_VOCABULARY:
                    raise ValidationError("unsupported field type")
                validated_fields[field] = field_type
                declared_types[field] = (
                    field_types.get(field) if field_types is not None and field in field_types
                    else FOUNDATION_TYPE_TO_CONTRACT_TYPE[field_type]
                )
            # Phase 4 (design D-2 item 2): every schema operation is
            # unconditionally fail-closed class -- the hook's own `pre_commit()`
            # is called by `self._backend.create_collection` itself, as the
            # last thing it does before its own commit point.
            hook = self._make_audit_hook(
                principal, event_class="schema_change", operation="create_collection",
                target_kind="collection", target_id=name, request_id=request_id,
            )
            with self._lock:
                self._backend.create_collection(
                    name, validated_fields, field_types=declared_types, audit_hook=hook, deadline=deadline)
        self.__record("schema_change", self.application_id,
                      principal.credential_id, detail="create_collection")

    def create_entity(self, principal, name, fields=None, *, request_id=None, field_types=None):
        """Wire-shaped counterpart of `create_collection`, matching
        contract `SchemaOperationRequest`'s own OPTIONAL `fields` (P3 WP-1
        round 2 instruction #6): `SchemaOperationRequest` allows `fields`
        to be omitted for `create_entity` (present-time `minItems: 1`
        only constrains it when it IS supplied). This foundation has no
        row-addressability concept to build a genuinely columnless table
        around (`row_addressability: unavailable`, unchanged by this WP),
        so an omitted `fields` is accepted as "an entity carrying only a
        base identity column" -- realized here as the narrowest concrete
        shape this foundation already has a real, tested meaning for: a
        single `id: integer` field, via the SAME `create_collection` path
        every other shape uses (no new backend primitive, no new column
        concept). This is a NEW, ADDITIONAL method -- `create_collection`
        itself keeps rejecting an empty/missing `fields` outright
        (`ValidationError`) for every existing caller (direct foundation
        use, the in-process conformance adapter, `tests/test_foundation.
        py`); nothing about its own behavior changes.
        """
        if fields is None:
            fields = {"id": "integer"}
        return self.create_collection(principal, name, fields, request_id=request_id, field_types=field_types)

    def add_field(self, principal, collection, field, field_type, *, request_id=None, contract_type=None):
        """P3-D1 (design v1.1 §0 exception, WP-1): the one capability-
        envelope addition this phase makes -- `schema_operations.add_field`,
        developer-only, on BOTH backends (declaration and implementation
        land in this same commit). Adds one column to an EXISTING
        collection; see the module-level comment above `_DELETE_
        CONSEQUENCE` for why this is also what makes a schema-revision
        fingerprint necessary in the `delete` confirmation phrase.

        Phase 6 WP-3 (design D-3): `contract_type`, when given, is the
        7-word contract vocabulary type this call records in the
        registry for `field` (`http.py`'s own `add_field` handler always
        supplies it -- `SchemaOperationRequest.field_type` is required
        there). `None` (every pre-1.6.0-shaped direct caller) derives it
        from `field_type` via the same backfill rule `create_collection`
        uses.
        """
        self._require_developer(principal, request_id=request_id)
        request = {"collection": collection, "field": field, "field_type": field_type}
        with self._limit_gate(principal, request, request_id=request_id) as deadline:
            collection = self._identifier(collection, "collection")
            field = self._identifier(field, "field")
            if field_type not in _FIELD_TYPE_VOCABULARY:
                raise ValidationError("unsupported field type")
            declared_type = contract_type if contract_type is not None else FOUNDATION_TYPE_TO_CONTRACT_TYPE[field_type]
            # Q1-D11-consistent shape bound (same reasoning as `create_
            # collection`'s own field-count check above): the total column
            # count this collection would carry AFTER this call mirrors the
            # same fixed contract shape dimension `max_fields` already gates
            # at definition time -- not a repeated, finite-resource
            # consumption class, so `ValidationError`, not `ResourceLimitError`
            # (keeps `test_limit_class_vocabulary.py`'s own AST-scanned
            # `ResourceLimitError` call-site count unaffected by this WP).
            current = self._backend.field_domains(collection)  # NotFoundError if `collection` does not exist
            if len(current) >= self.config.max_fields:
                raise ValidationError("field limit exceeded")
            # Phase 4 (design D-2 item 2): same unconditional fail-closed
            # pre-commit hook as `create_collection` above.
            hook = self._make_audit_hook(
                principal, event_class="schema_change", operation="add_field",
                target_kind="collection", target_id=collection, request_id=request_id,
            )
            with self._lock:
                # ConflictError if `field` already exists
                self._backend.add_field(
                    collection, field, field_type, contract_type=declared_type, audit_hook=hook, deadline=deadline)
        self.__record("schema_change", self.application_id,
                      principal.credential_id, detail="add_field")

    def schema_revision(self, principal, *, request_id=None):
        """m-2 (independent WP-3 review): the SAME monotonically-increasing
        counter `_validate_delete_confirmation` already reads to fingerprint
        a delete confirmation phrase (`_delete_confirmation_phrase`), now
        also exposed as a read-only, authorized query -- so the HTTP
        surface's `SchemaOperationResult.revision` field can report this
        peer's REAL current schema-revision value after a `create_entity`/
        `add_field` call, rather than a hardcoded placeholder that would
        never actually change (a false declaration: the contract's own
        `SchemaOperationResult.revision` field implies a real, observable
        value, and always returning the same literal after every schema
        change is not honest about what the peer just did).

        Phase 8 WP-1a rework 1 (裁定 3, 監督裁定 2026-09-06): WRAPPED by
        `_limit_gate` (rate/concurrency only -- `request=None`, exactly
        like `catalog` immediately below and r2db's own `catalog()`/
        `schema()`, which wrap `_slot` but never call `check_request`/
        `check_depth`, `service.py:996-1000`/`:1072-1074`): this is a
        real, client-callable, authenticated application-plane query
        (`ApplicationRuntime.schema_revision()`, the in-process port's own
        `session.schema_revision()`), not exempt from the request-rate/
        concurrency bound SI-08 requires on every credentialed call --
        r2db's own equivalent (`schema()`/`catalog()`) is bound this way
        too (`service.py:1133-1144`/`:1156-1163`'s `_slot`), so leaving
        THIS peer's version unbound left an authenticated credential able
        to hit `schema_revision`/`catalog` at unlimited rate/concurrency
        while every other application-plane call was bound -- a real,
        peer-specific gap the code review that sent this WP back found
        (measured: `rpm=50` with `catalog()` called 500 times in a row,
        zero denials, zero window consumption, pre-rework).

        `http.py::post_schema`'s OWN post-op revision readback does NOT
        go through this method any more -- see `_schema_revision_
        uncounted` below and `ApplicationRuntime._post_schema_revision`'s
        own docstring for why that separate, ungated internal accessor
        exists (this method's own gating would otherwise silently double
        the effective `requests_per_minute`/`concurrency` cost of every
        HTTP schema operation relative to the in-process surface, whose
        own `create_entity`/`add_field` never make this extra call at
        all -- the SAME asymmetry finding the WP-1a report already made,
        just resolved the other way: gate the real client-facing query,
        exempt the internal wire-formatting readback, rather than
        exempting both)."""
        self._require_data(principal, request_id=request_id)
        with self._limit_gate(principal, None, request_id=request_id):
            return self._schema_revision_uncounted()

    def _schema_revision_uncounted(self):
        """Phase 8 WP-1a rework 1 (裁定 3): the actual backend read
        `schema_revision` above now wraps with `_limit_gate` -- this
        private accessor is the UNGATED remainder, called ONLY by
        `ApplicationRuntime._post_schema_revision` (`http.py::post_schema`'s
        own post-op revision readback, never a client-initiated call in
        its own right: it reports the real consequence of the
        `create_entity`/`add_field` call that ALREADY passed through the
        gate earlier in this SAME request, not a second, independent
        client request of its own). Deliberately takes no `principal` --
        callers are expected to have already authorized/gated the
        surrounding operation; this is a pure backend read, nothing more."""
        with self._lock:
            return self._backend.schema_revision()

    def catalog(self, principal, *, request_id=None):
        """Phase 6 WP-3 (design D-3): `application_catalog`'s own real
        implementation (`cell.py::ApplicationRuntime.capabilities()`'s
        sibling flip, same commit -- `http.py::get_catalog`). Returns
        `[{"entity": ..., "fields": [...], "field_types": {...}}, ...]`,
        sorted by entity name for a deterministic response -- EXACTLY the
        contract `definitions.EntityDescriptor`'s three unconditional/
        `application_catalog`-conditional keys this peer can honestly
        populate (`mutation_class`/`address_fields`/`address_reuse`/
        `unique_keys` are all OMITTED -- `row_addressability:
        unavailable`, design §1.5 finding 4).

        Phase 8 WP-1a rework 1 (裁定 3): WRAPPED by `_limit_gate`
        (rate/concurrency only -- `request=None`, no client-supplied
        structure to bound with `request_bytes`/`operation_depth`) --
        see `schema_revision`'s own docstring immediately above for the
        full reasoning (r2db bounds its own `catalog()` the same way,
        `service.py:1079` inside `_slot`; this peer's own pre-rework
        `catalog()` did not, a real, measured gap)."""
        self._require_data(principal, request_id=request_id)
        with self._limit_gate(principal, None, request_id=request_id):
            with self._lock:
                all_types = self._backend.all_field_types()
        return [
            {"entity": entity, "fields": sorted(types), "field_types": dict(types)}
            for entity, types in sorted(all_types.items())
        ]

    def insert(self, principal, collection, values, *, request_id=None):
        self._require_data(principal, request_id=request_id)
        with self._limit_gate(principal, {"collection": collection, "values": values}, request_id=request_id) as deadline:
            collection, fields, params = self._prepare_values(collection, values)
            with self._lock:
                result = self._backend.insert(collection, fields, params, deadline=deadline)
        # Phase 4 (design D-4/P4-D5): buffer-class success emit -- a NEW
        # emit site (this peer recorded no query/insert/update success
        # before Phase 4).
        self._push_data_operation_event(principal, operation="insert", target_id=collection, request_id=request_id)
        return result

    def read(self, principal, collection, fields=None, filters=None,
             order_by=None, limit=None, *, request_id=None):
        self._require_data(principal, request_id=request_id)
        request = {"collection": collection, "fields": fields, "filters": filters, "order_by": order_by, "limit": limit}
        with self._limit_gate(principal, request, request_id=request_id) as deadline:
            collection = self._identifier(collection, "collection")
            selected = self._select_fields(collection, fields)
            bound_filters = self._bind_filters(collection, filters)
            order = self._bind_order_by(collection, order_by)
            if limit is None:
                limit = self.config.max_result_rows
            if not isinstance(limit, int) or limit <= 0 or limit > self.config.max_result_rows:
                raise ResourceLimitError("result limit exceeded", limit_class="result_items")
            with self._lock:
                rows = self._backend.read(collection, selected, bound_filters, order, limit, deadline=deadline)
        rows = self._decode_rows(collection, rows)
        # Phase 4 (design D-4/P4-D5): buffer-class success emit -- "query"
        # is this peer's own contract-vocabulary operation name for this
        # method (`read`, internally), matching r2db-api's identical
        # `operation="query"` durable-row value for the same conceptual
        # event.
        self._push_data_operation_event(principal, operation="query", target_id=collection, request_id=request_id)
        return rows

    def _validate_update(self, collection, values, filters):
        """m-1 (independent review, P3-D2 follow-up): the single choke
        BOTH `ApplicationCell.update` below AND `transact()`'s own
        batch-embedded update branch (`_plan_operation`, since P35 WP-2's
        two-pass restructuring) pass through -- identical four-step validation (non-empty `filters`
        shape check -> `_prepare_values` -> non-empty `fields` check ->
        `_bind_filters`), so a batch-embedded update is held to exactly
        the same mass-operation guard as the dedicated method, never a
        looser one. Mirrors `_validate_delete_confirmation`'s own role for
        `delete` -- there is no second definition of this validation
        anywhere in this file.

        Returns `(collection, fields, values_params, bound_filters)` on
        success. Does not execute the update itself and does not touch
        `self._lock`/the backend's own transaction state -- callers own
        both, same division of responsibility as
        `_validate_delete_confirmation`.
        """
        if not isinstance(filters, list) or not filters:
            raise ValidationError("update requires non-empty filters")
        collection, fields, values_params = self._prepare_values(collection, values)
        if not fields:
            raise ValidationError("values must be non-empty")
        bound_filters = self._bind_filters(collection, filters)
        return collection, fields, values_params, bound_filters

    def update(self, principal, collection, values, filters, *, request_id=None):
        self._require_data(principal, request_id=request_id)
        request = {"collection": collection, "values": values, "filters": filters}
        with self._limit_gate(principal, request, request_id=request_id) as deadline:
            collection, fields, values_params, bound_filters = self._validate_update(collection, values, filters)
            with self._lock:
                result = self._backend.update(collection, fields, values_params, bound_filters, deadline=deadline)
        # Phase 4 (design D-4/P4-D5): buffer-class success emit.
        self._push_data_operation_event(principal, operation="update", target_id=collection, request_id=request_id)
        return result

    def _validate_delete_confirmation(self, collection, filters, destructive, confirm):
        """P3-D2 (design v1.2 R-5, WP-1.5): the single choke BOTH
        `ApplicationCell.delete` below AND `transact()`'s own
        batch-embedded delete branch (`_plan_operation`, since P35 WP-2's
        two-pass restructuring) pass through -- identical shape checks, identical schema-revision-
        fingerprinted phrase construction (`_delete_confirmation_phrase`),
        identical exact-match comparison, identical four-key `details`
        shape on failure. A batch-embedded delete is therefore held to
        EXACTLY the same declare-and-echo requirement as the dedicated
        method, never a looser one -- there is no second, batch-specific
        copy of this logic anywhere in this file.

        `destructive` missing is equivalent to `False` (contract
        `valid_confirmation`); a valid confirmation requires BOTH
        `destructive is True` AND `confirm` to exactly equal the server's
        own currently-recomputed `required_confirmation` for this exact
        request (Unicode code point sequence, no normalization -- a plain
        `!=` string comparison already has this property). A non-bool
        `destructive`/non-str `confirm` is a shape defect
        (`ValidationError`), not a confirmation mismatch -- truthy
        acceptance of either is exactly the defect WP-0/WP-3's own B-1
        finding (r2db-api) forbids, applied here identically (WP-5 R-5).

        Returns `(collection, bound_filters)` on success; raises
        `DestructiveConfirmationRequired` otherwise. Does not execute the
        delete itself and does not touch `self._lock`/the backend's own
        transaction state -- callers own both.

        m-1 correction (independent review, P35 WP-2 follow-up): the
        dedicated `delete()` method still wraps its own `with self._lock:`
        AFTER this returns (no open batch transaction at that point).
        `transact()`'s own batch-embedded call site is DIFFERENT since
        P35 WP-2's two-pass restructuring (R-1): it now runs from
        `_plan_operation`, during pass 1 -- OUTSIDE `self._lock` entirely,
        and BEFORE `self._backend.begin()` is ever called (`self._lock`/
        `begin()` are only acquired afterward, once the whole batch has
        planned successfully, at the start of pass 2). This method itself
        is unaffected by that change (it never touched lock/transaction
        state either way), but the earlier claim that `transact()` "is
        already holding `self._lock` and has already called `begin()`
        before this is ever reached" describes the pre-WP-2, single-pass
        call site and is no longer true of the current one.
        """
        if not isinstance(destructive, bool):
            raise ValidationError("destructive must be a boolean")
        if confirm is not None and not isinstance(confirm, str):
            raise ValidationError("confirm must be a string")
        # B-3 (WP-0/WP-5): identifier + filter-shape validation (which,
        # via `_bind_filters`'s own `field_domains` call, also performs the
        # contract's own "target-existence checks" step) must complete
        # BEFORE the confirmation check below -- a phrase must never
        # reflect an unvalidated client-supplied collection name back to
        # the client, and evaluation_order requires target existence to be
        # settled before confirmation validity is evaluated.
        collection = self._identifier(collection, "collection")
        if not isinstance(filters, list) or not filters:
            raise ValidationError("delete requires non-empty filters")
        bound_filters = self._bind_filters(collection, filters)
        schema_revision = self._backend.schema_revision()
        phrase = _delete_confirmation_phrase(collection, filters, schema_revision)
        if destructive is not True or confirm != phrase:
            raise DestructiveConfirmationRequired(
                "destructive operation requires the current confirmation phrase",
                details={
                    "required_confirmation": phrase,
                    "consequence": _DELETE_CONSEQUENCE,
                    "reversible_alternative": None,
                    "recovery": None,
                },
            )
        return collection, bound_filters

    def delete(self, principal, collection, filters, *, destructive=False, confirm=None, request_id=None):
        """Contract `destructive_confirmation`: `delete` is this peer's
        only destructive operation (see the module-level comment above
        `_DELETE_CONSEQUENCE` for why `drop_entity`/`drop_index`/the
        control-plane revoke gate are all structurally absent here, not
        merely unimplemented). See `_validate_delete_confirmation` above
        for the actual confirmation semantics -- shared verbatim with
        `transact()`'s own batch-embedded delete (P3-D2, WP-1.5).
        """
        self._require_data(principal, request_id=request_id)
        request = {"collection": collection, "filters": filters, "destructive": destructive, "confirm": confirm}
        with self._limit_gate(principal, request, request_id=request_id) as deadline:
            try:
                collection, bound_filters = self._validate_delete_confirmation(
                    collection, filters, destructive, confirm)
            except DestructiveConfirmationRequired:
                # Phase 4 (design D-3): `DESTRUCTIVE_CONFIRMATION_REQUIRED` is
                # a durable-range denial code -- routed (coalesced) before
                # re-raising, unchanged, to the caller.
                self._route_delete_confirmation_denial(principal, collection, request_id=request_id)
                raise
            # Phase 4 (design D-2 item 1): delete is fail-closed class only
            # once it has passed the confirmation choke (this point) -- the
            # hook's own `pre_commit()` is called by `self._backend.delete`
            # itself, as the last thing it does before its own commit point.
            hook = self._make_audit_hook(
                principal, event_class="destructive_data_operation", operation="delete",
                target_kind="collection", target_id=collection, request_id=request_id,
            )
            with self._lock:
                result = self._backend.delete(collection, bound_filters, audit_hook=hook, deadline=deadline)
        self.__record("destructive_data_operation", self.application_id,
                      principal.credential_id, detail="delete_rows")
        return result

    def _plan_operation(self, operation):
        """P35 WP-2 (R-1, design docs/design/PHASE35_CROSS_ENTITY_AND_
        CONTRACT_130_V1.md §2): builds one fully-bound, side-effect-free
        plan step for a single `transact()` operation-dict -- identical
        shape/capability checks and identical validation chokes
        (`_prepare_values`/`_validate_update`/`_validate_delete_
        confirmation`, the pre-existing `_TRANSACT_*_KEYS` excess-key
        checks) as before this WP, just no longer interleaved with any
        OTHER operation's own execution. Never touches the DML
        (`_runtime`) transaction state (no `begin`/`commit`/`rollback`,
        no `..._in_transaction` call) -- m-3 correction (independent
        review, P35 WP-2 follow-up): this is narrower than "never touches
        `self._backend`'s transaction state" -- on the PostgreSQL backend,
        the read-only catalog calls this method makes (`field_domains`/
        `schema_revision`, via `_prepare_values`/`_bind_filters`/
        `_validate_delete_confirmation`) run on the SEPARATE developer
        connection (`backend_postgres.PostgresBackend._developer`) and DO
        commit there (a real, distinct transaction lifecycle from the
        runtime/DML connection's `begin()`/`commit()`/`rollback()` that
        pass 2 alone governs) -- exactly the same pre-existing
        `field_domains`/`schema_revision` behavior every single-operation
        method (`insert`/`update`/`delete`/`read`) already has outside
        any lock (module-level "PG 留意" note above `_DELETE_CONSEQUENCE`
        / design §2's own PG note), not a new side effect this WP
        introduces.

        Returns `("insert" | "update" | "delete", payload)` on success,
        `payload` a plain tuple of exactly the arguments the matching
        backend `..._in_transaction` method needs. Raises the identical
        `FoundationError` subclass, for the identical reason, that the
        pre-WP-2 in-loop branch below used to raise for this same
        operation shape -- this is a relocation of that logic, not a
        second copy of it (the module's own `_TRANSACT_INSERT_KEYS`/
        `_TRANSACT_UPDATE_KEYS`/`_TRANSACT_DELETE_KEYS`/
        `_CONTRACT_MUTATION_VOCABULARY` constants are unchanged, and
        `_prepare_values`/`_validate_update`/`_validate_delete_
        confirmation` are the exact same single chokes `insert`/`update`/
        `delete` above also use)."""
        if not isinstance(operation, dict):
            raise ValidationError("unsupported transaction operation")
        op_type = operation.get("type")
        if op_type == "insert":
            if set(operation) - _TRANSACT_INSERT_KEYS:
                # A well-formed "insert" carrying an extra, unrecognized
                # key (e.g. `expected_revision`) is a capability gap, not
                # a malformed request -- same reasoning as the
                # `update`/`delete` branches below, and the `upsert`
                # branch further down, which refuse this way for the
                # operation *type* itself.
                raise CapabilityError(
                    "transact does not support additional fields on operation type 'insert'"
                )
            collection, fields, params = self._prepare_values(operation["collection"], operation["values"])
            return ("insert", (collection, fields, params))
        if op_type == "update":
            if set(operation) - _TRANSACT_UPDATE_KEYS:
                raise CapabilityError(
                    "transact does not support additional fields on operation type 'update'"
                )
            collection, fields, values_params, bound_filters = self._validate_update(
                operation.get("collection"), operation.get("values"), operation.get("filters"))
            return ("update", (collection, fields, values_params, bound_filters))
        if op_type == "delete":
            if set(operation) - _TRANSACT_DELETE_KEYS:
                raise CapabilityError(
                    "transact does not support additional fields on operation type 'delete'"
                )
            collection, bound_filters = self._validate_delete_confirmation(
                operation.get("collection"), operation.get("filters"),
                destructive=operation.get("destructive", False),
                confirm=operation.get("confirm"))
            return ("delete", (collection, bound_filters))
        if op_type in _CONTRACT_MUTATION_VOCABULARY:
            # Only "upsert" ever reaches here -- P3-D2 (WP-1.5) converged
            # `update`/`delete` to real execution above. Per
            # `capability_status.rules` ("optional target operations ...
            # must fail with CAPABILITY_UNSUPPORTED"), this is a
            # capability gap, not a malformed request.
            raise CapabilityError(f"transact does not support operation type {op_type!r}")
        raise ValidationError("unsupported transaction operation")

    @staticmethod
    def _distinct_batch_entities(operations):
        """P35 WP-2 (R-2): the set of DISTINCT `collection` names named
        across the raw, not-yet-validated operation dicts -- the same
        entity may repeat across multiple operations without counting
        twice (contract `endpoints.cross_entity_mutate.semantics`:
        "batch_entities bounds the number of distinct entity names
        referenced across operations[] ... the same entity may appear in
        more than one operation, and total operation count remains
        bounded by batch_items independently"). Deliberately reads the
        RAW dicts (a non-dict operation is simply skipped here -- its own
        malformed shape is a `_plan_operation` concern, reached
        immediately after this check) rather than the validated plan, so
        this whole-batch shape bound is evaluated symmetrically with the
        `batch_items` check immediately above it in `transact()`: both
        are checked before any single operation's own validation begins.

        Independent review B-1 (WP-2 follow-up): a `collection` value
        that is present but not itself a string (e.g. `["t"]`, `{}`) must
        be SKIPPED here too, not added to the set -- adding an unhashable
        value would raise a bare `TypeError` out of this whole-batch
        pre-check, before `_plan_operation` ever gets a chance to
        classify that same malformed operation as an ordinary
        `ValidationError` (its own proper job). This mirrors the
        non-dict-operation skip immediately above: a shape defect at
        THIS layer is deferred to `_plan_operation`, never raised here as
        an unclassified exception.
        """
        names = set()
        for operation in operations:
            if isinstance(operation, dict):
                name = operation.get("collection")
                if isinstance(name, str):
                    names.add(name)
        return names

    def transact(self, principal, operations, *, request_id=None):
        """P3-D2 (design v1.2 R-5, WP-1.5): `insert`/`update`/`delete` all
        execute for real here, atomically with everything else in the
        same batch -- converging this entry point's real behavior onto
        the existing `atomic_mutation.operations` declaration (unchanged
        by this WP). `upsert` alone remains a real capability gap: no
        execution path for it exists anywhere on this peer.

        The whole batch commits or rolls back as one unit (contract "A
        batch is atomic unless explicitly declared best_effort" --
        `best_effort_transactions: unavailable`, unchanged): a mid-batch
        failure of ANY kind (a shape defect, a missing/wrong destructive
        confirmation, a unique-constraint conflict, a collection that does
        not exist) discards every write already performed earlier in the
        SAME batch, insert included -- `self._backend.rollback()` in the
        `except` clause below is the one and only rollback point for the
        whole batch, reached from every operation type's own failure path.

        P35 WP-2 (R-1, design docs/design/PHASE35_CROSS_ENTITY_AND_
        CONTRACT_130_V1.md §2, P35-D9/P35-D10/P35-D11): two-pass as of
        this WP -- ALL operations across ALL entities are validated first
        (`self._plan_operation`, side-effect-free, building a fully-bound
        execution plan), and `self._backend.begin()` is never called at
        all until that whole-batch validation pass has succeeded end to
        end. Only then does the second pass execute the plan inside the
        begin/commit/rollback envelope below. This entry point is shared
        by both the single-entity HTTP path (`http.py::post_mutate`) and
        the cross-entity one (`http.py::post_cross_entity_mutate`) --
        neither is a second copy of this method, so both are two-pass by
        construction. Atomicity itself (all-or-nothing) is UNCHANGED by
        this restructuring; the one externally-observable consequence
        (P35-D9) is that a batch mixing an operation that would have
        failed at BACKEND EXECUTION time with a LATER operation that
        fails VALIDATION now surfaces the validation error (previously,
        the earlier operation's execution-time error could surface first,
        after already having reached the backend, since the old single
        pass validated-then-executed each operation in strict order
        before ever looking at the next one's own type) -- the validation
        error winning is the contract-required priority
        (`transactions.cross_entity`), adopted deliberately (M-7). The
        internal ordering itself (validate-all, then execute-all) is not
        black-box observable and is not a conformance-suite concern
        (P35-D10) -- it is pinned locally, structurally, by this
        package's own tests (a wrapped/monkeypatched backend proving zero
        `..._in_transaction`/`begin` calls happen when a later operation
        fails validation).
        """
        self._require_data(principal, request_id=request_id)
        request = {"operations": operations}
        with self._limit_gate(principal, request, request_id=request_id) as deadline:
            if not isinstance(operations, list) or not operations:
                raise ValidationError("operations must be a non-empty list")
            if len(operations) > self.config.max_batch_items:
                raise ResourceLimitError("batch limit exceeded", limit_class="batch_items")
            if len(self._distinct_batch_entities(operations)) > self.config.max_batch_entities:
                raise ResourceLimitError("batch entity limit exceeded", limit_class="batch_entities")

            # Pass 1: validate every operation, across every entity, before
            # any execution begins (P35-D9/P35-D10 above). Nothing below this
            # line has touched `self._backend`'s own transaction state yet.
            # Phase 4 (design D-3): `_plan_operation`'s own delete branch may
            # raise `DestructiveConfirmationRequired` (via `_validate_delete_
            # confirmation`, the same choke `delete()` uses) -- routed
            # (coalesced) here, at the one call site with `principal` in
            # scope, mirroring `delete()`'s own identical wrapping.
            plan = []
            for operation in operations:
                try:
                    plan.append(self._plan_operation(operation))
                except DestructiveConfirmationRequired:
                    collection = operation.get("collection") if isinstance(operation, dict) else None
                    self._route_delete_confirmation_denial(principal, collection, request_id=request_id)
                    raise

            # Phase 4 (design D-2's normative rule): the confirmation choke,
            # not `event_class`, is the fail-closed/buffer-class dispatch
            # point -- a batch containing at least one "delete" kind is
            # fail-closed class for the WHOLE batch (D-10: at most one durable
            # row per operation, so the batch gets exactly one pre-commit row,
            # never one per individual delete inside it); a batch with none is
            # buffer-class (P4-D5's new emit site).
            destructive = any(kind == "delete" for kind, _ in plan)
            hook = None
            if destructive:
                hook = self._make_audit_hook(
                    principal, event_class="destructive_data_operation", operation="transact",
                    target_kind="collection", target_id=None, request_id=request_id,
                )

            # Pass 2: execute the fully-bound plan inside the begin/commit/
            # rollback envelope -- unchanged from before this WP other than
            # reading its arguments from `plan` instead of re-validating them
            # from the raw operation dicts inline.
            with self._lock:
                self._backend.begin(deadline=deadline)
                # Phase 4 (design D-2, review M-6): `hook_fired` distinguishes
                # "the durable pre-commit write itself failed" (nothing was
                # committed to correct -- the batch is simply refused) from
                # "the durable write succeeded but this backend's own commit
                # then failed" (D-2's error-row case) -- mirrors `backend_
                # postgres.PostgresBackend`'s identical single-operation
                # pattern, here at the batch level since `transact`'s own
                # begin/commit/rollback envelope lives in `cell.py`, not
                # either backend module.
                hook_fired = False
                try:
                    results = []
                    for kind, payload in plan:
                        if kind == "insert":
                            collection, fields, params = payload
                            results.append(self._backend.insert_in_transaction(collection, fields, params))
                        elif kind == "update":
                            collection, fields, values_params, bound_filters = payload
                            results.append(self._backend.update_in_transaction(
                                collection, fields, values_params, bound_filters))
                        else:  # "delete"
                            collection, bound_filters = payload
                            results.append(self._backend.delete_in_transaction(collection, bound_filters))
                    # Phase 4 (design D-2/D-10): the pre-commit hook is the
                    # LAST thing this method does before its own commit point
                    # -- a raise here (an `errors.AuditSinkUnavailable`) is
                    # caught by the `except Exception` below, which rolls
                    # back exactly like any other mid-batch failure (fail-
                    # closed by construction). The pre-existing 6-field-sink
                    # `destructive_data_operation` record (below, post-commit)
                    # is unaffected either way (D-10: that sink's own
                    # behaviour is completely unchanged by this WP).
                    if destructive and hook is not None:
                        hook.pre_commit()
                        hook_fired = True
                    self._backend.commit()
                except Exception as exc:
                    # Independent review B-2 (WP-2 follow-up -- the
                    # atomicity hole, largest safety fix of that review):
                    # rollback is now UNCONDITIONAL. The pre-fix `except`
                    # tuple listed only `errors.FoundationError` subclasses;
                    # a non-`FoundationError` exception reaching this point
                    # used to skip `self._backend.rollback()` entirely and
                    # escape this method uncaught -- measured concretely: a
                    # lone UTF-16 surrogate code point in a value's own text
                    # (e.g. `"\ud800"`) escapes both backend drivers' own
                    # parameter-binding step as a raw `UnicodeEncodeError`
                    # (neither a `sqlite3.Error` nor a `psycopg.Error`
                    # subclass), on BOTH backends. With the pre-fix narrow
                    # `except`, that left every EARLIER, individually-valid
                    # operation's own write sitting UNCOMMITTED but already
                    # VISIBLE on this same connection (both SQLite and
                    # PostgreSQL give a transaction read-your-own-writes
                    # visibility before `COMMIT`) -- a real partial-effect
                    # breach of the "whole batch commits or rolls back as one
                    # unit" invariant this method's own docstring promises.
                    # B-2(ii) below (`encode_value`, both backends) now closes
                    # THIS specific case deterministically at validation time
                    # (pass 1, before `self._backend.begin()` is ever called),
                    # but the unconditional rollback here is the actual safety
                    # backstop -- it must hold for ANY exception a backend
                    # could ever raise during pass 2, known or not, not only
                    # the one concrete case that happened to be found.
                    #
                    # P3-D2 (WP-1.5) / m-2 (WP-2 review correction):
                    # `DestructiveConfirmationRequired` is not actually
                    # reachable from pass 2 at all -- `_plan_operation` (pass
                    # 1) is the ONLY site that ever evaluates a destructive
                    # confirmation (`_validate_delete_confirmation`), so a
                    # schema change racing pass 1/pass 2 (§2 PG note) surfaces
                    # here as a `NotFoundError`/`ConflictError` from the
                    # backend's own DML instead (the table/column the plan
                    # was bound against no longer matches reality), never as
                    # a re-evaluated confirmation mismatch; it stays listed
                    # here only for defensive symmetry with `_plan_operation`'s
                    # own vocabulary, not because this `except Exception:`
                    # needs it to reach that branch specifically (every
                    # `Exception` already does). `ConflictError`/`NotFoundError`
                    # (a unique-constraint conflict / a collection that
                    # stopped existing between this call's own validation pass
                    # and its execution pass) and `ValidationError`/
                    # `ResourceLimitError`/`CapabilityError` (this file names
                    # no backend-native exception type at all -- every backend
                    # translates its own low-level, EXPECTED failures into
                    # this shared `errors.FoundationError` vocabulary before
                    # this point) remain the classified, expected outcomes;
                    # anything else (like the `UnicodeEncodeError` above, pre
                    # B-2(ii)) rolls back and re-raises unclassified, exactly
                    # as before -- this method itself never reclassifies an
                    # exception type, only guarantees rollback runs first.
                    self._backend.rollback()
                    # Phase 4 (design D-2, error-row rule): `hook_fired` is
                    # only `True` once the durable pre-commit row has already
                    # committed on its own (separate) connection -- so an
                    # exception reaching here after that point can only be
                    # this method's own `self._backend.commit()` failing.
                    # Record the durable `outcome="error"` row for the same
                    # operation's fields (still fail-closed: `commit_failed()`
                    # never raises -- see `audit_hook.py` -- but the response
                    # is `AuditSinkUnavailable` regardless of whether that
                    # write itself succeeds).
                    if hook_fired:
                        hook.commit_failed()
                        raise AuditSinkUnavailable(
                            "the durable audit sink recorded this batch but the data commit failed"
                        ) from exc
                    raise
                # Phase 4 (design D-10): the pre-existing 6-field-sink record
                # is unconditional and unchanged -- it fires for a
                # batch-embedded delete exactly as it did before this WP,
                # now safely AFTER `self._backend.commit()` has actually
                # succeeded (no `pending_audit` deferral needed any more: the
                # hook above already gave the durable trail its own, separate,
                # PRE-commit guarantee, so this post-commit legacy record
                # never needs to claim a write a later operation rolled back
                # -- if we are here at all, `self._backend.commit()` already
                # succeeded for the whole batch).
                if destructive:
                    self.__record("destructive_data_operation", self.application_id,
                                  principal.credential_id, detail="delete_rows")
                else:
                    # Phase 4 (design D-4/P4-D5): a non-destructive batch
                    # (insert/update only) is buffer-class -- exactly ONE
                    # `data_operation` event for the whole batch (D-10: at
                    # most one durable row per operation), mirroring
                    # r2db-api's own identical "one row per mutate batch"
                    # rule.
                    self._push_data_operation_event(principal, operation="transact", target_id=None, request_id=request_id)
                return results

    def _select_fields(self, collection, requested):
        available = self._backend.field_domains(collection)
        if requested is None:
            return list(available)
        if not isinstance(requested, list) or not requested:
            raise ValidationError("fields must be a non-empty list")
        if len(requested) > self.config.max_fields:
            # Q1-D11 (design v1.5 §7): read-projection width is a shape
            # bound on the request's own `fields` list, mirroring contract
            # `QueryRequest.select.maxItems`.
            raise ValidationError("field limit exceeded")
        result = []
        for field in requested:
            field = self._identifier(field, "field")
            if field not in available:
                raise ValidationError("unknown field")
            result.append(field)
        return result

    def _decode_rows(self, collection, rows):
        """Phase 6 WP-3 (design D-3, F2/F3): the read-side counterpart of
        `_normalize_value_for_storage` -- restores a physical value to its
        declared contract shape, backend-independently (both `backend_
        sqlite.py`/`backend_postgres.py`'s own `read()` return the SAME
        physical representation this undoes: canonical JSON text for
        `object`/`array`/`json`, `0`/`1` for `boolean`). A field with no
        registry row (`None`, backward compatible) or declared `string`/
        `integer`/`number` passes through unchanged. `None` (SQL NULL)
        always passes through unchanged, for every declared type."""
        declared_types = self._backend.field_types(collection)
        json_types = ("object", "array", "json")
        for row in rows:
            for field, value in row.items():
                if value is None:
                    continue
                declared_type = declared_types.get(field)
                if declared_type in json_types:
                    row[field] = json.loads(value)
                elif declared_type == "boolean":
                    row[field] = bool(value)
        return rows

    # WP-3 (design docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md v1.2
    # R-5/§2): the HTTP `/v1/data/{entity}/query` endpoint maps contract
    # `QueryRequest.order_by` -- an ARRAY of `Order` objects
    # (`definitions.Order`, `maxItems: 10`), i.e. multi-field sort -- onto
    # this seam. `_bind_order_by` therefore accepts three shapes and always
    # returns either `None` or a non-empty LIST of `(field, direction)`
    # tuples (never a bare tuple any more): `None` (no ordering), a single
    # `{"field": ..., "direction": ...}` object (the pre-WP-3 shape --
    # `tests/test_postgres.py`'s own existing call and every other
    # pre-existing caller keep working unchanged, now normalized to a
    # one-element list internally), or a list of such objects (the new,
    # contract-shaped multi-field form). Both backends' own `read()` were
    # updated in the same commit to consume this unified list-or-None
    # shape (`backend_sqlite.py`/`backend_postgres.py`).
    _MAX_ORDER_BY_TERMS = 10  # mirrors contract `definitions.QueryRequest.order_by.maxItems`

    def _bind_order_by(self, collection, order_by):
        if order_by is None:
            return None
        if isinstance(order_by, dict):
            order_by = [order_by]
        if not isinstance(order_by, list) or not order_by:
            raise ValidationError("order_by must be an object or a non-empty list of objects")
        if len(order_by) > self._MAX_ORDER_BY_TERMS:
            raise ValidationError("order_by term limit exceeded")
        available = self._backend.field_domains(collection)
        bound = []
        for item in order_by:
            if not isinstance(item, dict):
                raise ValidationError("order_by must be an object or a non-empty list of objects")
            field = self._identifier(item.get("field"), "order field")
            if field not in available:
                raise ValidationError("unknown order field")
            direction = item.get("direction", "asc")
            if direction not in ("asc", "desc"):
                raise ValidationError("invalid order direction")
            bound.append((field, direction))
        return bound

    def _prepare_values(self, collection, values):
        collection = self._identifier(collection, "collection")
        available = self._backend.field_domains(collection)
        # Phase 6 WP-3 (design D-3, G3): the PRIMARY, backend-independent
        # declared-type choke point -- `field_types.check_declared_value`
        # runs BEFORE `encode_value` on every backend (sqlite included,
        # where `field_domains` alone enforces nothing at all, `available`
        # above being all-`None` there). Backend domain validation stays
        # underneath this as defence-in-depth (`encode_value` itself),
        # never a substitute for it.
        declared_types = self._backend.field_types(collection)
        if not isinstance(values, dict) or not values:
            raise ValidationError("values must be a non-empty object")
        if len(values) > self.config.max_fields:
            # Q1-D11 (design v1.5 §7): write-payload width (insert/update/
            # transact-insert) mirrors contract `Mutation.values.
            # maxProperties: 100` directly.
            raise ValidationError("field limit exceeded")
        fields = []
        params = []
        for field, value in values.items():
            field = self._identifier(field, "field")
            if field not in available:
                raise ValidationError("unknown field")
            fields.append(field)
            declared_type = declared_types.get(field)
            check_declared_value(value, declared_type)
            # B-1 (independent review round 2): `available[field]` is this
            # field's own value-domain category from the active backend's
            # live catalog (`None` on SQLite -- domain validation skipped
            # there, matching its own unchanged external behavior) --
            # passed through so a type-mismatched value (e.g. a string for
            # a declared-`integer` column) is rejected deterministically
            # here, before any statement reaches PostgreSQL.
            params.append(self._backend.encode_value(
                self._normalize_value_for_storage(value, declared_type), domain=available[field]))
        return collection, fields, params

    def _bind_filters(self, collection, filters):
        if filters is None:
            return []
        if not isinstance(filters, list) or len(filters) > self.config.max_filter_terms:
            # Clean 1:1 correspondence: this is the same shape dimension
            # r2db-api's own `query_complexity` metric folds `len(where)`
            # into, and `capabilities()` below publishes this exact bound
            # (`config.max_filter_terms`) under the `query_complexity` key.
            raise ResourceLimitError("filter limit exceeded", limit_class="query_complexity")
        available = self._backend.field_domains(collection)
        # Phase 6 WP-3 (design D-3, G3): same choke point `_prepare_values`
        # above uses.
        declared_types = self._backend.field_types(collection)
        bound = []
        for item in filters:
            if not isinstance(item, Filter):
                raise ValidationError("filters must contain Filter values")
            field = self._identifier(item.field, "filter field")
            if item.operator in _UNSUPPORTED_CONTRACT_OPERATORS:
                # Contract 1.1.0 (CCR-13, §0.5 Q-2 adjudication): `contains`/
                # `matches`/`is_null` are real members of the common
                # contract's own filter-operator vocabulary but this peer
                # simply does not execute any of the three -- a positive,
                # honest refusal (`CapabilityError`), checked ahead of the
                # field-existence check below (a refusal this
                # unconditional must not depend on whether the named field
                # happens to exist).
                raise CapabilityError(f"{item.operator} is not supported by this foundation")
            if field not in available:
                raise ValidationError("invalid filter")
            if item.operator not in SQL_OPERATOR_TOKENS:
                # A genuinely unrecognized operator string, outside the
                # common contract's vocabulary entirely (every contract
                # member this peer does not implement is handled by the
                # `_UNSUPPORTED_CONTRACT_OPERATORS` branch above instead).
                raise ValidationError("invalid filter")
            if item.operator == "in":
                if not isinstance(item.value, list) or not item.value:
                    raise ValidationError("in filter requires values")
                if len(item.value) > self.config.max_batch_items:
                    # Reuses `config.max_batch_items` itself (not a
                    # separate `max_filter_terms`-style bound).
                    raise ResourceLimitError("filter value limit exceeded", limit_class="batch_items")
                # B-1: every element compares against the SAME column, so
                # they all share that column's own domain.
                domain = available[field]
                declared_type = declared_types.get(field)
                for v in item.value:
                    check_declared_value(v, declared_type)
                encoded = [
                    self._backend.encode_value(self._normalize_value_for_storage(v, declared_type), domain=domain)
                    for v in item.value
                ]
                bound.append(Filter(field, "in", encoded))
            else:
                declared_type = declared_types.get(field)
                check_declared_value(item.value, declared_type)
                encoded = self._backend.encode_value(
                    self._normalize_value_for_storage(item.value, declared_type), domain=available[field])
                bound.append(Filter(field, item.operator, encoded))
        return bound

    @staticmethod
    def _normalize_value(value):
        """Backend-independent shape check/normalization (R-3): a
        dict/list value becomes canonical JSON text; every other accepted
        Python type (`bool`/`str`/`int`/`float`/`None`) passes through
        unchanged for the active backend's own `encode_value` to finish
        (backend-specific bind encoding AND backend-specific value-domain
        validation, e.g. PostgreSQL's embedded-NUL rejection -- see
        `backend_postgres.PostgresBackend.encode_value`)."""
        if isinstance(value, (dict, list)):
            return json.dumps(value, separators=(",", ":"), sort_keys=True)
        if isinstance(value, (bool, str, int, float)) or value is None:
            return value
        raise ValidationError("unsupported value")

    @classmethod
    def _normalize_value_for_storage(cls, value, declared_type):
        """Phase 6 WP-3 (design D-3, F2): `declared_type` (one of
        `field_types.CONTRACT_TYPES`, or `None`) has ALREADY been checked
        against `value` by `field_types.check_declared_value` before this
        runs. For `object`/`array`/`json` -- the three contract types this
        peer stores as physical `json` (TEXT) -- every value (not only
        dict/list; `str`/`int`/`float`/`bool` too) becomes canonical JSON
        text, so the read side can UNCONDITIONALLY `json.loads()` it back
        and recover the exact original value (a plain string written to a
        `json`-declared field must round-trip as that same string, not
        get confused with a `string`-declared field's own literal text).
        `None` (SQL NULL) is never encoded -- NULL is valid for any
        declared type (`field_types.check_declared_value`'s own identical
        precedent) and stays NULL, never becomes the JSON text `"null"`.
        Every other declared type (`string`/`integer`/`number`/`boolean`,
        or `None` -- no registry row, backward compatible) falls back to
        `_normalize_value` unchanged."""
        if value is not None and declared_type in ("object", "array", "json"):
            return json.dumps(value, separators=(",", ":"), sort_keys=True)
        return cls._normalize_value(value)

    def _require_data(self, principal, *, request_id=None):
        if self.__guard is not None:
            # Review M-2 (major, supervisor ruling 2026-09-03, "完全案"):
            # `guard` is always `auth.CredentialStore.assert_active` or
            # `credential_store_postgres.PostgresCredentialStore.
            # assert_active` in every real construction of this class
            # (`main.py`/`service.py` -- the only two call sites that ever
            # pass a non-`None` guard, verified by source inspection),
            # both of which accept this same `request_id` keyword after
            # this WP's changes -- so a session re-check failure's own
            # durable denial row carries the SAME request_id as the
            # operation that triggered the re-check.
            self.__guard(principal, request_id=request_id)
        if not isinstance(principal, Principal) or principal.application_id != self.application_id:
            # Review M-3 (major, supervisor ruling 2026-09-03): this is
            # SI-00's own application-boundary check ("this credential's
            # own `application_id` does not match the cell it is being
            # used against") -- the single most evidence-worthy `FORBIDDEN`
            # this peer can produce, and previously recorded on NO audit
            # surface at all (neither the 6-field sink nor the durable
            # one). `FORBIDDEN` is in D-3's own inclusion table
            # unconditionally; routed (coalesced) here, the one choke
            # point every public data-operation method (`insert`/`read`/
            # `update`/`delete`/`transact`/`schema_revision`, and `_require_
            # developer` itself) already passes through. (Scoped to the
            # durable D-3 path only, per review M-3's own literal
            # instruction -- the pre-existing 6-field sink's own
            # `_SAFE_DETAILS` vocabulary has no accurate label for a
            # generic access denial, so this does not invent one there.)
            self.__audit_router.route_denial(
                reason_code="FORBIDDEN", event_class="authorization_denied", request_id=request_id,
                application_id=self.application_id, actor_type="application_credential",
                actor_id=getattr(principal, "credential_id", None), role=None, operation="access",
                target_kind="collection", target_id=None,
            )
            raise AuthorizationError("application scope denied")
        if principal.role not in (Role.RUNTIME, Role.DEVELOPER):
            self.__audit_router.route_denial(
                reason_code="FORBIDDEN", event_class="authorization_denied", request_id=request_id,
                application_id=self.application_id, actor_type="application_credential",
                actor_id=principal.credential_id, role=None, operation="access",
                target_kind="collection", target_id=None,
            )
            raise AuthorizationError("role denied")

    def _require_developer(self, principal, *, request_id=None):
        self._require_data(principal, request_id=request_id)
        if principal.role != Role.DEVELOPER:
            self.__record("authorization_denied", self.application_id,
                          getattr(principal, "credential_id", None),
                          outcome="denied", detail="schema_change")
            # Phase 4 (design D-3): `FORBIDDEN` is a durable-range denial
            # code -- routed (coalesced) alongside the pre-existing
            # 6-field sink append above, unconditionally (D-10: this
            # sink's own behaviour is completely unaffected).
            self.__audit_router.route_denial(
                reason_code="FORBIDDEN", event_class="authorization_denied", request_id=request_id,
                application_id=self.application_id, actor_type="application_credential",
                actor_id=getattr(principal, "credential_id", None),
                role=getattr(getattr(principal, "role", None), "value", None),
                operation="schema", target_kind="collection", target_id=None,
            )
            raise AuthorizationError("developer authority required")


class ApplicationRuntime:
    """Runtime data authority; schema mutation is intentionally absent."""

    __slots__ = ("__cell", "__principal", "__guard")

    def __init__(self, cell, principal, guard=None, *, request_id=None):
        cell._require_data(principal, request_id=request_id)
        self.__cell, self.__principal, self.__guard = cell, principal, guard

    @property
    def principal(self):
        return self.__principal

    def __authorize(self, *, request_id=None):
        if self.__guard is not None:
            self.__guard(self.__principal, request_id=request_id)

    def schema_revision(self, *, request_id=None):
        self.__authorize(request_id=request_id)
        return self.__cell.schema_revision(self.__principal, request_id=request_id)

    def _post_schema_revision(self, *, request_id=None):
        """Phase 8 WP-1a rework 1 (裁定 3, 監督裁定 2026-09-06): the
        UNGATED counterpart of `schema_revision` above, for exactly one
        caller -- `http.py::post_schema`'s own post-op revision readback,
        immediately after a `create_entity`/`add_field` call that has
        ALREADY passed through `_limit_gate` earlier in this SAME wire
        request. That readback is not itself a second client request (no
        `GET .../schema-revision` endpoint exists; nothing on the wire
        asks for it independently of the schema-mutation call it reports
        the consequence of) -- routing it through the now-gated
        `schema_revision()` above would silently double the effective
        `requests_per_minute`/`concurrency` cost of every HTTP schema
        operation relative to the in-process surface, whose own
        `create_entity`/`add_field` never make this extra call at all
        (the asymmetry the original WP-1a report measured; 裁定 3 resolves
        it by gating the real client-facing query and exempting only
        this one internal wire-formatting readback, rather than exempting
        both, since `catalog`/`schema_revision` themselves ARE real,
        independently client-callable queries r2db bounds too)."""
        self.__authorize(request_id=request_id)
        return self.__cell._schema_revision_uncounted()  # noqa: SLF001

    def insert(self, collection, values, *, request_id=None):
        self.__authorize(request_id=request_id)
        return self.__cell.insert(self.__principal, collection, values, request_id=request_id)

    def read(self, collection, fields=None, filters=None, order_by=None, limit=None, *, request_id=None):
        self.__authorize(request_id=request_id)
        return self.__cell.read(self.__principal, collection, fields, filters, order_by, limit, request_id=request_id)

    def catalog(self, *, request_id=None):
        self.__authorize(request_id=request_id)
        return self.__cell.catalog(self.__principal, request_id=request_id)

    def update(self, collection, values, filters, *, request_id=None):
        self.__authorize(request_id=request_id)
        return self.__cell.update(self.__principal, collection, values, filters, request_id=request_id)

    def delete(self, collection, filters, *, destructive=False, confirm=None, request_id=None):
        self.__authorize(request_id=request_id)
        return self.__cell.delete(self.__principal, collection, filters,
                                  destructive=destructive, confirm=confirm, request_id=request_id)

    def transact(self, operations, *, request_id=None):
        self.__authorize(request_id=request_id)
        return self.__cell.transact(self.__principal, operations, request_id=request_id)

    def capabilities(self, *, request_id=None):
        """Minimal capability/discovery document, per this session's own
        server-bound scope. Statuses reflect what this foundation actually
        executes today, not the common contract's peer-target surface: an
        operation this foundation cannot run is never advertised "enabled"
        (spec `capability_status.rules`).

        This is the single source of truth for this peer's declared
        capability document (R-3): both the SQLite-backed in-process
        composition and the PostgreSQL-backed composition
        (`tests/test_postgres.py`) share this exact method -- there is no
        second copy anywhere that could drift out of agreement with it.

        Phase 8 WP-1a rework 1 (裁定 3, 監督裁定 2026-09-06): WRAPPED by
        `_limit_gate` (rate/concurrency only -- `request=None`) for the
        SAME reason as `ApplicationCell.catalog`/`.schema_revision`
        (those methods' own docstrings carry the full trace): r2db bounds
        its own `capabilities()` this way too (`service.py:877` inside
        `_slot`), and this is a real, client-callable, authenticated
        query, not a discovery-time exemption -- the pre-rework version
        left it entirely outside the gate (measured, pre-rework:
        `rpm=50` with 500 consecutive `capabilities()` calls, zero
        denials)."""
        self.__authorize(request_id=request_id)
        principal = self.__principal
        with self.__cell._limit_gate(principal, None, request_id=request_id):  # noqa: SLF001
            return self.__build_capabilities_document(principal)

    def __build_capabilities_document(self, principal):
        is_developer = principal.role == Role.DEVELOPER
        config = self.__cell.config
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
            "contract_version": "1.6.0",
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
                "schema_operations": {"status": "partial", "operations": ["create_entity", "add_field"] if is_developer else [], "unsupported": ["alter_field", "create_index", "drop_index", "drop_entity", "jobs"]},
                "audit_query": {"status": "unavailable", "authority": "control_or_audit"},
                "best_effort_transactions": {"status": "unavailable"},
                "idempotency": {"status": "unavailable"},
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
                "control_plane": {"status": config.control_plane_status}
            },
            **_surfaces_document_fragment(config),
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
            },
            "limit_enforcement": {
                "batch_items": "enforced",
                "batch_entities": "enforced",
                "result_items": "enforced",
                "query_complexity": "enforced",
                # Phase 8 WP-1a (design D-1): `ApplicationCell._limit_gate`
                # now measures every request's own structural byte estimate
                # (`_measure_request_bytes`) on BOTH the in-process and HTTP
                # surface -- the same gate every method below passes
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
                "concurrency": "enforced",
                # Phase 8 WP-1a (design D-1): `_LimitStateHolder.
                # acquire_rate` now bounds a credential-keyed 60s sliding
                # window for real.
                "requests_per_minute": "enforced",
                # Phase 8 WP-1a rework 1 (裁定 1, 監督裁定 2026-09-06):
                # `enforced` on BOTH surfaces -- `_check_operation_depth`
                # (module-level, above) is wired into `_limit_gate`
                # (`:531`) and genuinely bounds nesting on EVERY request
                # shape every method below builds, in-process included.
                #
                # The WP-1a report's original claim here ("in-process has
                # no request dict to bound, because `insert`/`update`/
                # `delete` take positional/keyword ARGUMENTS, not a single
                # dict") was factually wrong, per the code review that sent
                # this WP back: `_limit_gate` is passed a REAL dict on
                # every one of those call sites -- `insert` builds
                # `{"collection": collection, "values": values}` (`:770`),
                # `update` builds `{"collection": ..., "values": ...,
                # "filters": ...}` (`:832`), `delete` and `transact`
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
                # own pre-existing comment on that dispatcher).
                "operation_depth": "enforced",
            },
            # `CredentialStore.assert_active` (auth.py) is invoked by
            # `__authorize` above on every single session operation, with
            # no cache: revoke/disable/state-unavailable propagation is
            # synchronous.
            "authorization_propagation_bound_ms": 0,
            "application_scope": principal.application_id,
            "role": principal.role.value
        }


class ApplicationDeveloper(ApplicationRuntime):
    """Developer authority adds structured schema operations only."""

    def create_collection(self, name, fields, *, request_id=None, field_types=None):
        self._ApplicationRuntime__authorize(request_id=request_id)
        return self._ApplicationRuntime__cell.create_collection(
            self._ApplicationRuntime__principal, name, fields, request_id=request_id, field_types=field_types)

    def create_entity(self, name, fields=None, *, request_id=None, field_types=None):
        self._ApplicationRuntime__authorize(request_id=request_id)
        return self._ApplicationRuntime__cell.create_entity(
            self._ApplicationRuntime__principal, name, fields, request_id=request_id, field_types=field_types)

    def add_field(self, collection, field, field_type, *, request_id=None, contract_type=None):
        self._ApplicationRuntime__authorize(request_id=request_id)
        return self._ApplicationRuntime__cell.add_field(
            self._ApplicationRuntime__principal, collection, field, field_type,
            request_id=request_id, contract_type=contract_type)
