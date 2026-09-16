"""Finite, deployment-configurable resource bounds."""

from dataclasses import dataclass, replace
import os
from typing import Any, Optional

from .errors import ResourceLimitError, ValidationError
from .surfaces import validate_control_base_url, validate_data_base_url


@dataclass(frozen=True)
class FoundationConfig:
    """Bounds used by the local foundation.

    These are deliberately finite defaults, not a final public-contract
    number. A future HTTP adapter may expose the profile through the common
    capability-discovery contract.
    """

    max_batch_items: int = 100
    # P35 WP-2 (R-2, design docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_
    # 130_V1.md §2): bounds the number of DISTINCT collection names
    # `ApplicationCell.transact` may reference across one batch -- the
    # same entity may repeat across multiple operations without counting
    # twice (`batch_items` above already bounds total operation count,
    # independently). Default 10 is the client-requested value (P35-D2,
    # design §6) -- the contract's own non-normative reference profile
    # (`limits.example_profile.batch_entities: 4`) is a different,
    # unrelated number this deployment declaration does not have to match.
    max_batch_entities: int = 10
    max_result_rows: int = 500
    max_fields: int = 64
    max_filter_terms: int = 32
    max_request_bytes: int = 1_048_576
    max_schema_objects: int = 128
    # Phase 8 WP-1a (design docs/design/PHASE8_EFFECTIVE_BOUNDS_AND_
    # HYGIENE_V1.md D-1, work order L7-1): the 4 application-plane
    # resource classes this deployment declaration previously left
    # entirely unimplemented (`cell.py`'s own prior "next-phase candidate
    # L7-1" comment). Deliberately finite, deployment-configurable
    # defaults -- same convention as every other `max_*` field above --
    # never a final public-contract number. `max_requests_per_minute` and
    # `max_concurrency` are r2db-matching in MEANING (P-6: same contract
    # semantics, independent realization) -- a credential-keyed 60s
    # sliding window and a process-wide in-flight counter respectively
    # (design D-1 "カウンタのスコープ").
    #
    # Phase 8 WP-1a rework 1 (裁定 6, 監督裁定 2026-09-06): the code
    # review that sent this WP back found the ORIGINAL wording here
    # ("not in numeric default -- r2db's own `ResourceLimits` defaults
    # are unrelated deployment numbers this peer does not have to
    # match") stated the opposite of the measured fact -- all 4 of these
    # defaults are IDENTICAL, digit for digit, to r2db's own
    # `ResourceLimits` defaults (`r2db-api/src/r2db_api/limits.py:16-20
    # `: `requests_per_minute=600`, `concurrency=32`, `execution_ms=5_000`,
    # `operation_depth=8`). This is a deliberate, unforced coincidence in
    # each peer's own independent "reasonable deployment default" choice
    # (P-6: the CONTRACT semantics match by design; a shared default
    # NUMBER matching too is not itself required by anything, but nothing
    # here relies on it staying that way either -- an operator is free to
    # configure either peer's own value independently, exactly like
    # `max_batch_entities`'s own precedent above; this comment only
    # corrects the earlier, factually-backwards claim, it does not
    # introduce a new coupling). `max_execution_ms` bounds the wall-clock
    # deadline
    # `cell.py`'s own limit gate computes and hands to the storage
    # backend (`backend_postgres.py`'s `SET LOCAL statement_timeout`/
    # `lock_timeout`, `backend_sqlite.py`'s app-side check) -- declared
    # `reference_wall_clock`, never `enforced` (design D-1: wall-clock
    # cannot construct a deterministic N+1, matching r2db's own
    # `execution_ms` declaration). `max_operation_depth` bounds the
    # recursive nesting `cell.py`'s own gate measures on the request
    # structure it builds internally for insert/read/update/delete/
    # transact/schema calls (r2db `limits.py::check_depth`-equivalent,
    # independent realization, P-6).
    max_requests_per_minute: int = 600
    max_concurrency: int = 32
    max_execution_ms: int = 5_000
    max_operation_depth: int = 8
    # Phase 9 WP-3a (design docs/design/
    # PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md §5 U-1 = (β)):
    # the one new limit class this WP's own `enum` constraint introduces --
    # bounds how many members a single field's declared `enum` may carry,
    # never bytes (member length is bounded by `max_request_bytes` above,
    # like every other request-carried string). `example_profile` in the
    # contract's own non-normative reference is 64 (U-1 確定); this
    # deployment default matches it, same convention as every other
    # `max_*` field above (a deployment-configurable number, not a final
    # public-contract one).
    max_enum_members: int = 64
    # Phase 9 WP-3c (design docs/design/
    # PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md D-5, 追補 2
    # S-f; 監督裁定集約 rulings-r5-r6.md I-10): the two `idempotency`
    # limit classes -- `idempotency_entries` bounds how many retained
    # records this Application may hold at once (checked, after lazily
    # reclaiming elapsed ones, at the lookup stage, before execution);
    # `idempotency_retention_ms` bounds how long a record answers a
    # resend before it is treated as absent. Same deployment-configurable-
    # default convention as every other `max_*`/count field above --
    # `example_profile` in the contract's own non-normative reference is
    # `10000`/`86400000` (`spec/data-service-api.v1.json` `limits.
    # example_profile`), and this deployment default matches it verbatim.
    idempotency_entries: int = 10_000
    idempotency_retention_ms: int = 86_400_000
    # WP-5 (design v1.2 R-7): "control_plane は WP-5 の flip まで両
    # composition とも unavailable のまま。flip は...単一コミットで行う".
    # Defaults `"unavailable"` so an operator who does not explicitly opt
    # in (`MITATEDB_CONTROL_PLANE_STATUS=enabled`) sees no behavior change
    # at all -- the single source of truth for this declaration
    # (`cell.py::ApplicationRuntime.capabilities()`, R-3) reads this field,
    # never a second, independently-drifting copy.
    control_plane_status: str = "unavailable"

    # Phase 6 WP-3 (design D-2): the deployer's own declaration of where
    # THIS process' data surface (and, when known, the sibling control
    # surface) is reached -- `cell.ApplicationRuntime.capabilities()`'s
    # single source of truth for `CapabilityDocument.surfaces`, mirroring
    # `control_plane_status` immediately above (composition-root-injected,
    # never a hardcoded literal). `None` for either omits `surfaces`
    # (`data_base_url` unset) or `surfaces.control` (`control_base_url`
    # unset) entirely -- see `surfaces.build_surfaces`.
    data_base_url: Optional[str] = None
    control_base_url: Optional[str] = None

    _VALID_CONTROL_PLANE_STATUSES = ("enabled", "unavailable")

    def __post_init__(self) -> None:
        # Reviewer finding m-1 (WP-5 review): `from_env` validates
        # `MITATEDB_CONTROL_PLANE_STATUS` against this same vocabulary, but
        # a construction that bypasses `from_env` entirely -- both
        # conformance adapters build `FoundationConfig(control_plane_
        # status=...)` directly -- reached the dataclass with no
        # validation at all. R-7's "宣言値が単一ソースから出ることを構造で
        # 保証する" is only as strong as the weakest constructor path, so
        # the check belongs on the field itself, not only at the env-var
        # boundary (which stays, for early/loud startup failure -- this is
        # deliberate double coverage, not redundancy to remove).
        if self.control_plane_status not in self._VALID_CONTROL_PLANE_STATUSES:
            raise ValidationError(
                f"control_plane_status must be one of {self._VALID_CONTROL_PLANE_STATUSES!r}, "
                f"got {self.control_plane_status!r}"
            )
        # Phase 6 WP-3 (design D-2): form-only, structural (applies on
        # every construction path, `from_env` included -- see this
        # dataclass' own m-1 finding above `control_plane_status` for why
        # the check belongs on the field itself). Presence (a real
        # deployment's own `MITATEDB_DATA_BASE_URL`/`_CONTROL_BASE_URL`
        # being required at all) is `from_env`'s own job below, not this
        # constructor's -- many callers (every pre-1.6.0-style direct
        # construction, this repository's own tests) legitimately build a
        # `FoundationConfig` with neither set.
        try:
            validate_data_base_url(self.data_base_url)
            validate_control_base_url(self.control_base_url)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

    @classmethod
    def from_env(cls, environ=None, *, data_base_url: Optional[str] = None, control_base_url: Optional[str] = None):
        """Q4 phase (design docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md D-2):
        `data_base_url`/`control_base_url` are now REQUIRED keyword
        arguments the caller (composition root) must already have read,
        validated, and cross-checked against `MITATEDB_CONTROL_PLANE_
        STATUS` (F-6) via `platform_declarations.read_platform_
        declarations`/`check_control_surface_consistency` BEFORE calling
        this factory -- `environ` no longer supplies either value
        (`MITATEDB_DATA_BASE_URL`/`MITATEDB_CONTROL_BASE_URL` are REMOVED
        env vars, F-2: rejected whenever defined, whatever their value).
        Every OTHER field below is unaffected -- still read from
        `environ` exactly as before."""
        values = dict(os.environ if environ is None else environ)
        names = {
            "max_batch_items": "MITATEDB_MAX_BATCH_ITEMS",
            "max_batch_entities": "MITATEDB_MAX_BATCH_ENTITIES",
            "max_result_rows": "MITATEDB_MAX_RESULT_ROWS",
            "max_fields": "MITATEDB_MAX_FIELDS",
            "max_filter_terms": "MITATEDB_MAX_FILTER_TERMS",
            "max_request_bytes": "MITATEDB_MAX_REQUEST_BYTES",
            "max_schema_objects": "MITATEDB_MAX_SCHEMA_OBJECTS",
            # Phase 8 WP-1a (L7-1): same env-var convention as every field
            # above -- an unset env var keeps the dataclass default.
            "max_requests_per_minute": "MITATEDB_MAX_REQUESTS_PER_MINUTE",
            "max_concurrency": "MITATEDB_MAX_CONCURRENCY",
            "max_execution_ms": "MITATEDB_MAX_EXECUTION_MS",
            "max_operation_depth": "MITATEDB_MAX_OPERATION_DEPTH",
            # Phase 9 WP-3a (design §5 U-1 = (β)): same env-var convention
            # as every field above -- an unset env var keeps the dataclass
            # default (64).
            "max_enum_members": "MITATEDB_MAX_ENUM_MEMBERS",
            # Phase 9 WP-3c (design §5 U-1 = (β) sibling convention): same
            # env-var pattern as every field above -- an unset env var
            # keeps the dataclass default.
            "idempotency_entries": "MITATEDB_IDEMPOTENCY_ENTRIES",
            "idempotency_retention_ms": "MITATEDB_IDEMPOTENCY_RETENTION_MS",
        }
        parsed = {}
        for field, name in names.items():
            raw = values.get(name)
            if raw is None:
                continue
            try:
                number = int(raw)
            except (TypeError, ValueError):
                raise ValidationError("invalid resource limit")
            if number <= 0:
                raise ValidationError("resource limits must be positive")
            parsed[field] = number
        # R-9 runbook invariant 3 ("control service を停止/未配備にする場合
        # は data 面の control_plane 宣言 env を同時に変更する"): a
        # deployer declaration, not a detected fact -- this process cannot
        # verify on its own whether a `/control/v1` process
        # (`control_main.py`) is actually reachable. Rejects any value
        # outside the two-member vocabulary at startup (loud, never a
        # silent fallback) rather than only at first capabilities() read.
        control_plane_status = values.get("MITATEDB_CONTROL_PLANE_STATUS") or "unavailable"
        if control_plane_status not in cls._VALID_CONTROL_PLANE_STATUSES:
            raise ValidationError(
                f"MITATEDB_CONTROL_PLANE_STATUS must be one of {cls._VALID_CONTROL_PLANE_STATUSES!r}, "
                f"got {control_plane_status!r}"
            )
        parsed["control_plane_status"] = control_plane_status
        # Q4 phase (design D-2, requester ruling 2026-09-05 overriding
        # Phase 6 supervisor ruling 5 -- see this module's own historical
        # note below): `data_base_url`/`control_base_url` are no longer
        # read from `environ` at all -- the caller (`main.build_app`) has
        # already read+validated them from `<registry>.
        # platform_declarations` (D-2) and cross-checked `control_base_
        # url`'s presence against `MITATEDB_CONTROL_PLANE_STATUS` (F-6,
        # `platform_declarations.check_control_surface_consistency`)
        # BEFORE calling this factory -- so by the time `from_env` runs,
        # either both already agree, or `build_app` has already raised.
        # `surfaces.data` is still an unconditional 1.6.0 obligation, now
        # enforced by F-3 (the platform_declarations row's own
        # required-presence check) rather than by this factory.
        #
        # Historical note (superseded, kept for the historical record --
        # design D-2(f) explicitly requires recording this override, not
        # silently dropping the old comment): Phase 6 WP-3 差し戻し 最終
        # ラウンド (supervisor ruling 2026-09-04, 裁定 5) had this factory
        # itself silently drop a stale `MITATEDB_CONTROL_BASE_URL` env
        # value whenever `control_plane_status == "unavailable"` ("a
        # stale/leftover value from a previous configuration...is never
        # adopted"). Q4 D-2(f) (requester ruling 2026-09-05) OVERRIDES
        # that ruling: the single declaration now lives in ONE row shared
        # by both processes, so a mismatch is no longer something either
        # process may silently ignore -- `check_control_surface_
        # consistency` (called by `main.build_app` before this factory)
        # raises F-6 instead.
        if not data_base_url:
            raise ValidationError("surfaces.data is required (declared in <registry>.platform_declarations)")
        parsed["data_base_url"] = data_base_url
        if control_plane_status != "unavailable" and control_base_url:
            parsed["control_base_url"] = control_base_url
        return cls(**parsed)

    def validate_request_size(self, size):
        """Reject a body before parsing or dispatching it."""
        if not isinstance(size, int) or size < 0 or size > self.max_request_bytes:
            # Clean 1:1 correspondence with contract `limits.classes`:
            # this is the same finite byte bound `capabilities().limits`
            # publishes as `request_bytes` (WP-5 Q1-D7(B)).
            raise ResourceLimitError("request size limit exceeded", limit_class="request_bytes")


def role_pool_size(config: "FoundationConfig") -> int:
    """Phase 10 WP-4e (supervisor ruling 2026-09-09, 同型 with r2db-api's
    `r2db_api.limits.role_pool_size`): the platform pool's own floor
    (`main.py`'s `pool.BoundedConnectionPool`, backing `PostgresCredential
    Store`'s authentication reads) must be at least the declared `max_
    concurrency` ceiling -- the SAME reasoning r2db-api's sibling function
    already documents in full: once concurrent requests' authentication
    reads can genuinely reach this pool at once (`http.py`'s own
    `run_in_threadpool` delegation), a pool sized below the declared
    bound times out waiting for a pooled connection and fails closed with
    `AUTH_STATE_UNAVAILABLE` well under that bound, instead of a client
    ever seeing the declared 429 `LIMIT_EXCEEDED` at the real ceiling.

    Unlike r2db-api, this peer's per-application data path is NOT pooled
    at all (`backend_postgres.PostgresBackend`: two fixed, persistent
    connections per served application, serialized by `cell.py`'s own
    request-wide lock, WP-8b) -- there is no per-application counterpart
    to this function on this peer, only this one platform-pool consumer.
    """
    return config.max_concurrency


# Phase 9 WP-3d (design D-6, 追補 R-g; 監督裁定集約 rulings-r5-r6.md B-1/
# B-2/B-5): contract class name -> the `FoundationConfig` field it
# narrows. Only the three budgetable classes (`limits.request_budget`:
# "Three classes are budgetable in this version: result_items,
# execution_ms and batch_items") have an entry -- every other
# `limits.classes` member is never budgetable and is refused by
# `_BUDGET_APPLICABLE_CLASSES` below before this map is ever consulted.
_BUDGET_CLASS_TO_FIELD = {
    "result_items": "max_result_rows",
    "execution_ms": "max_execution_ms",
    "batch_items": "max_batch_items",
}

# Design D-6 (2)'s own apply table: which of the three budgetable classes
# has meaning on which endpoint kind. `query` never accepts `batch_items`
# (nothing to batch); `mutate`/`cross_entity` never accept `result_items`
# (D-6: "result_items is not budgetable on a mutation ... this version
# does not give one request a way to narrow how many rows its own
# mutation may affect", L9-11); `schema` accepts only `execution_ms`
# (there is no `result_items`/`batch_items` dimension to a single schema
# operation). `mutate` and `cross_entity` share one entry -- both route
# through the identical `ApplicationCell.transact` apply table (裁定
# B-1's own single row for both).
_BUDGET_APPLICABLE_CLASSES = {
    "query": frozenset({"result_items", "execution_ms"}),
    "mutate": frozenset({"execution_ms", "batch_items"}),
    "cross_entity": frozenset({"execution_ms", "batch_items"}),
    "schema": frozenset({"execution_ms"}),
}


def _json_type_name(value: Any) -> str:
    """Contract `errors.details_vocabulary.VALIDATION_FAILED.observed_
    type`'s own vocabulary: "the JSON type of the value actually received
    (string, integer, number, boolean, object, array or null)". Only
    reached from `narrow_limits_by_budget` below, for a `budget/<class>`
    value that failed the `isinstance(int) and not bool` test. Mirrors
    r2db's identical `_json_type_name` (`limits.py`) -- same 7-way
    mapping, same lowercase-leading-underscore naming convention (Phase 9
    R-5/R-6 pair-closing commit: renamed from `_JSON_TYPE_NAME`, and the
    `bool` special case folded IN here rather than left to the caller's
    own ternary, so `narrow_limits_by_budget`'s own pinned body can call
    this the same single way both peers do)."""
    if isinstance(value, bool):
        return "boolean"
    if value is None:
        return "null"
    if isinstance(value, str):
        return "string"
    if isinstance(value, float):
        return "number"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "integer"


def _budget_denied(message: str, field: str, **extra: Any) -> None:
    """Phase 9 R-5/R-6 pair-closing commit: the ONE place `narrow_limits_
    by_budget` below turns a budget-shape violation into this peer's own
    denial (`errors.ValidationError`) -- pulled out of the pinned function
    body itself (isomorphism table row `narrow_limits_by_budget`, `tests/
    test_audit_query.py`) so that body's own text never has to spell
    either peer's own exception vocabulary. r2db-api's `limits.py` places
    an identically-named, identically-signatured wrapper next to its own
    `narrow_limits_by_budget` that calls `fail()` instead -- the two
    wrappers are deliberately NOT pinned isomorphic to each other (only
    the function that calls them, identically, is); each is free to stay
    exactly as small as its own peer's error type requires."""
    raise ValidationError(message, details={"violated_declaration": "budget", "field": field, **extra})


def narrow_limits_by_budget(deployed: FoundationConfig, budget: dict[str, Any] | None, endpoint_kind: str) -> FoundationConfig:
    """Phase 9 WP-3d (design D-6, 追補 R-g/S-l; 監督裁定集約 rulings-r5-
    r6.md B-1/B-2/B-5): the ONE point that turns a request's own optional
    `budget` object into the `effective_limits` every existing check
    point (`ApplicationCell._limit_gate`'s own deadline, `transact`'s own
    `batch_items` check, `read`'s own `result_items` check) reads instead
    of `self.config` directly -- no check point is individually rewritten
    to know about `budget` (B-2: "検査点を個別に書き換えない"). `budget is
    None` OR `{}` (the overwhelming common case -- every pre-WP-3d caller)
    returns `deployed` UNCHANGED (identity-shaped narrowing), so a caller
    that never presents a budget sees exactly the deployed profile it
    always did (completion condition 2, the positive control).

    Validity (checked HERE, at the request's own validation stage, before
    target existence / destructive confirmation / precondition -- design
    D-6: "a budget is checked where this contract's own request shape is
    checked"): a `budget` key naming a class `endpoint_kind` does not
    accept, or carrying a value that is not a positive `int`, or carrying
    a value ABOVE `deployed`'s own declared bound for that class, is
    refused with `errors.ValidationError` (`VALIDATION_FAILED`),
    `details.violated_declaration: "budget"`, `details.field:
    "budget/<class>"` -- `declared_type`/`observed_type` are added ONLY
    for the non-integer case (design D-3's own rule: those two keys are
    "required where violated_declaration is field_type or nullable" and
    every other required-4-key code; `budget` is not one of the three
    codes D-3 (4) names, so this function follows the narrower, explicit
    contract text instead: "it is not ignored" -- and never manufactures
    `declared_type`/`observed_type` for an out-of-range-but-integer or an
    inapplicable-class violation, matching WP-3a's own `field_constraints`
    precedent for a shape violation that is not about a value's type).
    `budget` never RAISES a bound (a `budget.<class>` above the deployed
    value is refused outright, never silently clamped down to the
    deployed value) -- only the SMALLER of the two, per class, is ever
    adopted (design D-6: "the bound in force ... is the smaller of the
    deployment's declared value ... and the requested value").

    Every class `budget` does not name keeps `deployed`'s own value --
    this is a NARROWING, never a second, independent declaration.

    Peer-symmetry note (isomorphism table row, `tests/test_audit_query.
    py`, Phase 9 R-5/R-6 pair-closing commit): isomorphic to r2db-api's
    own `limits.narrow_limits_by_budget(deployed, budget, endpoint_kind)`
    -- same name, same 3-argument signature, same behaviour. No code is
    shared between peers; `_budget_denied`/`_BUDGET_CLASS_TO_FIELD`
    immediately above absorb the two peers' own exception vocabulary and
    dataclass-field-naming difference OUTSIDE this body."""
    if not budget:
        return deployed
    if not isinstance(budget, dict):
        _budget_denied("budget must be an object.", "budget")
    applicable = _BUDGET_APPLICABLE_CLASSES.get(endpoint_kind, frozenset())
    narrowed: dict[str, int] = {}
    for class_name, requested in budget.items():
        if class_name not in applicable:
            _budget_denied(
                "budget names a resource class that does not apply to this endpoint.",
                f"budget/{class_name}",
            )
        # Ruling J-2 (WP-2cd audit N-2, monitor's (α)): the non-integer leg
        # is split from the `< 1` leg so ONLY the former carries `declared_
        # type`/`observed_type` -- ruling B-1's own parenthetical ("declared_
        # type / observed_type は非整数のときのみ") read literally, and now
        # matching MitateDB's identical 2-branch shape (`config.py`'s own
        # `narrow_limits_by_budget`) so the SAME rejection returns the SAME
        # `details` shape on both peers.
        if not isinstance(requested, int) or isinstance(requested, bool):
            _budget_denied(
                "budget values must be integers of at least 1.",
                f"budget/{class_name}",
                declared_type="integer", observed_type=_json_type_name(requested),
            )
        if requested < 1:
            _budget_denied("budget values must be integers of at least 1.", f"budget/{class_name}")
        field_name = _BUDGET_CLASS_TO_FIELD[class_name]
        deployed_value = getattr(deployed, field_name)
        if requested > deployed_value:
            _budget_denied(
                "budget exceeds this deployment's own declared value for this resource class.",
                f"budget/{class_name}",
            )
        # P-5/D-6 (3): downward-only -- `min` never `max` (C-24 variant 1).
        narrowed[field_name] = min(deployed_value, requested)
    return replace(deployed, **narrowed)
