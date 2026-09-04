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
    def from_env(cls, environ=None):
        values = dict(os.environ if environ is None else environ)
        names = {
            "max_batch_items": "MITATEDB_MAX_BATCH_ITEMS",
            "max_batch_entities": "MITATEDB_MAX_BATCH_ENTITIES",
            "max_result_rows": "MITATEDB_MAX_RESULT_ROWS",
            "max_fields": "MITATEDB_MAX_FIELDS",
            "max_filter_terms": "MITATEDB_MAX_FILTER_TERMS",
            "max_request_bytes": "MITATEDB_MAX_REQUEST_BYTES",
            "max_schema_objects": "MITATEDB_MAX_SCHEMA_OBJECTS",
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
        # Phase 6 WP-3 (design D-2): `surfaces.data` is an unconditional
        # 1.6.0 obligation -- a REAL deployment (this factory's own
        # purpose) must always supply `MITATEDB_DATA_BASE_URL`.
        # `MITATEDB_CONTROL_BASE_URL` is required only when this same
        # process declares `control_plane` other than `unavailable`
        # (the contract's own conditional-on-a-control-surface framing) --
        # a data-plane process with no sibling control process has
        # nothing to declare there.
        data_base_url = values.get("MITATEDB_DATA_BASE_URL")
        if not data_base_url:
            raise ValidationError("MITATEDB_DATA_BASE_URL is required")
        control_base_url = values.get("MITATEDB_CONTROL_BASE_URL")
        if control_plane_status != "unavailable" and not control_base_url:
            raise ValidationError(
                "MITATEDB_CONTROL_BASE_URL is required when MITATEDB_CONTROL_PLANE_STATUS is not 'unavailable'"
            )
        try:
            parsed["data_base_url"] = validate_data_base_url(data_base_url)
            # WP-3 差し戻し 最終ラウンド (supervisor ruling 2026-09-04,
            # 裁定 5, review F6): a deployment that declares `control_
            # plane: unavailable` must never surface `surfaces.control`
            # (contract 1.6.0: "a deployment declaring control_plane
            # unavailable omits surfaces.control entirely") -- even when
            # `MITATEDB_CONTROL_BASE_URL` happens to be set in the
            # environment (a stale/leftover value from a previous
            # configuration, say), it is never adopted while `control_
            # plane_status == "unavailable"`. Mirrors r2db-api's own
            # `main.py::_surfaces`: `if control_plane_status !=
            # "unavailable": ...` gates `surfaces["control"]` identically.
            if control_plane_status != "unavailable" and control_base_url:
                parsed["control_base_url"] = validate_control_base_url(control_base_url)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        return cls(**parsed)

    def validate_request_size(self, size):
        """Reject a body before parsing or dispatching it."""
        if not isinstance(size, int) or size < 0 or size > self.max_request_bytes:
            # Clean 1:1 correspondence with contract `limits.classes`:
            # this is the same finite byte bound `capabilities().limits`
            # publishes as `request_bytes` (WP-5 Q1-D7(B)).
            raise ResourceLimitError("request size limit exceeded", limit_class="request_bytes")
