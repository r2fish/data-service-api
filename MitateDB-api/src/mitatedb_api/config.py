"""Finite, deployment-configurable resource bounds."""

from dataclasses import dataclass
import os
from typing import Optional

from .errors import ResourceLimitError, ValidationError
from .surfaces import build_surfaces, validate_control_base_url, validate_data_base_url


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
