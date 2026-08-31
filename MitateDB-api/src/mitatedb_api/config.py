"""Finite, deployment-configurable resource bounds."""

from dataclasses import dataclass
import os

from .errors import ResourceLimitError, ValidationError


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
        return cls(**parsed)

    def validate_request_size(self, size):
        """Reject a body before parsing or dispatching it."""
        if not isinstance(size, int) or size < 0 or size > self.max_request_bytes:
            # Clean 1:1 correspondence with contract `limits.classes`:
            # this is the same finite byte bound `capabilities().limits`
            # publishes as `request_bytes` (WP-5 Q1-D7(B)).
            raise ResourceLimitError("request size limit exceeded", limit_class="request_bytes")
