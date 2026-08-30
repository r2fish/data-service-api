"""`FoundationConfig` field-level validation (WP-5 review finding m-1).

`FoundationConfig.from_env` already validates `MITATEDB_CONTROL_PLANE_
STATUS` against the two-member vocabulary (`config.py`'s own R-9 comment),
but that check only runs on the env-var construction path. Both
conformance adapters (`conformance_adapter_mitatedb.py`/`conformance_
adapter_mitatedb_http.py`) construct `FoundationConfig(control_plane_
status=...)` directly, bypassing `from_env` entirely -- R-7's "宣言値が
単一ソースから出ることを構造で保証する" is only as strong as the weakest
constructor path, so `__post_init__` on the dataclass itself is the
single place BOTH paths funnel through.
"""
from __future__ import annotations

import pytest

from mitatedb_api.config import FoundationConfig
from mitatedb_api.errors import ValidationError


def test_direct_construction_rejects_an_invalid_control_plane_status() -> None:
    with pytest.raises(ValidationError, match="control_plane_status"):
        FoundationConfig(control_plane_status="garbage")


def test_direct_construction_accepts_unavailable() -> None:
    config = FoundationConfig(control_plane_status="unavailable")
    assert config.control_plane_status == "unavailable"


def test_direct_construction_accepts_enabled() -> None:
    config = FoundationConfig(control_plane_status="enabled")
    assert config.control_plane_status == "enabled"


def test_default_construction_is_unavailable_and_valid() -> None:
    assert FoundationConfig().control_plane_status == "unavailable"


def test_from_env_still_rejects_invalid_values_too(monkeypatch) -> None:
    """R-9's own double-coverage: the env-var boundary keeps its own
    early, loud check (not removed by this WP-5 review finding) --
    unaffected by `__post_init__` existing."""
    with pytest.raises(ValidationError, match="MITATEDB_CONTROL_PLANE_STATUS"):
        FoundationConfig.from_env({"MITATEDB_CONTROL_PLANE_STATUS": "ENABLED"})
