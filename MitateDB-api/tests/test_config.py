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


# ---------------------------------------------------------------------------
# Phase 6 WP-3 追補 (mutation-testing finding, supervisor ruling 2026-09-04):
# work order §4 WP-3 完了条件5 ("`surfaces` 環境変数の起動時検査 -- 相対URL
# / 誤った終端 / 末尾スラッシュ付き / 不在 の各形が起動時に失敗すること (4
# 形が個別ケース)") had NO test anywhere in this peer's suite before this
# addition -- `surfaces.py`'s own `_validate_base_url` (called from
# `FoundationConfig.from_env` via `validate_data_base_url`) already
# implements all 4 checks, but nothing exercised them: mutating any ONE of
# `_validate_base_url`'s branches (confirmed for the trailing-slash check)
# passed the full existing suite. This is a test gap, not a product-code
# gap -- the 4 cases below close it (`MITATEDB_DATA_BASE_URL`, the
# variable every real deployment supplies unconditionally, contract 1.6.0
# subordinate ruling 11 item 2). Product code is untouched.
# ---------------------------------------------------------------------------

_VALID_DATA_BASE_URL = "https://mitatedb.example.invalid/v1"


def test_from_env_rejects_a_relative_data_base_url() -> None:
    with pytest.raises(ValidationError, match="MITATEDB_DATA_BASE_URL"):
        FoundationConfig.from_env({"MITATEDB_DATA_BASE_URL": "/v1"})


def test_from_env_rejects_a_data_base_url_with_the_wrong_suffix() -> None:
    with pytest.raises(ValidationError, match="MITATEDB_DATA_BASE_URL"):
        FoundationConfig.from_env({"MITATEDB_DATA_BASE_URL": "https://mitatedb.example.invalid/v2"})


def test_from_env_rejects_a_data_base_url_with_a_trailing_slash() -> None:
    """Matches the SPECIFIC "trailing slash" message, not merely the
    variable name -- ANY value ending in "/" also fails the (separate)
    required-suffix check below it (`"...v1/".endswith("/v1")` is False),
    so a generic `match="MITATEDB_DATA_BASE_URL"` would stay green even if
    the dedicated trailing-slash check (`surfaces.py`'s own F12 (ii)
    branch) were deleted outright -- the suffix check would silently catch
    the same input for a DIFFERENT reason and this test would never
    observe the deletion. Matching the exact message this one branch
    raises is the only black-box way to pin it independently."""
    with pytest.raises(ValidationError, match="trailing slash"):
        FoundationConfig.from_env({"MITATEDB_DATA_BASE_URL": "https://mitatedb.example.invalid/v1/"})


def test_from_env_rejects_an_absent_data_base_url() -> None:
    with pytest.raises(ValidationError, match="MITATEDB_DATA_BASE_URL"):
        FoundationConfig.from_env({})


def test_from_env_accepts_a_well_formed_data_base_url() -> None:
    config = FoundationConfig.from_env({"MITATEDB_DATA_BASE_URL": _VALID_DATA_BASE_URL})
    assert config.data_base_url == _VALID_DATA_BASE_URL


# ---------------------------------------------------------------------------
# WP-3 差し戻し 最終ラウンド (supervisor ruling 2026-09-04, 裁定 4, review
# F5): the DATA-side block above pins all 4 malformed forms for
# `MITATEDB_DATA_BASE_URL`, but `MITATEDB_CONTROL_BASE_URL` had NO negative
# tests at all -- `validate_control_base_url` (`surfaces.py`) shares the
# exact same `_validate_base_url` machinery, so this is the identical 4-form
# gap, on the CONTROL side, plus the "declared but absent while control_
# plane_status != unavailable" case `validate_control_base_url` alone
# cannot catch (that precondition is `from_env`'s own job, see `config.py`).
# Mutating `surfaces.validate_control_base_url`'s body to `return value`
# (bypassing `_validate_base_url` entirely) passed the full pre-existing
# suite -- confirmed below (report's own mutation log).
# ---------------------------------------------------------------------------

_VALID_CONTROL_BASE_URL = "https://mitatedb.example.invalid/control/v1"


def test_from_env_rejects_a_relative_control_base_url() -> None:
    with pytest.raises(ValidationError, match="MITATEDB_CONTROL_BASE_URL"):
        FoundationConfig.from_env({
            "MITATEDB_DATA_BASE_URL": _VALID_DATA_BASE_URL,
            "MITATEDB_CONTROL_PLANE_STATUS": "enabled",
            "MITATEDB_CONTROL_BASE_URL": "/control/v1",
        })


def test_from_env_rejects_a_control_base_url_with_the_wrong_suffix() -> None:
    with pytest.raises(ValidationError, match="MITATEDB_CONTROL_BASE_URL"):
        FoundationConfig.from_env({
            "MITATEDB_DATA_BASE_URL": _VALID_DATA_BASE_URL,
            "MITATEDB_CONTROL_PLANE_STATUS": "enabled",
            "MITATEDB_CONTROL_BASE_URL": "https://mitatedb.example.invalid/v1",
        })


def test_from_env_rejects_a_control_base_url_with_a_trailing_slash() -> None:
    """Same discipline as the DATA-side trailing-slash test above -- matches
    the SPECIFIC message, not merely the variable name, since the (separate)
    required-suffix check would otherwise silently catch the same input for
    a different reason and mask a deleted trailing-slash branch."""
    with pytest.raises(ValidationError, match="trailing slash"):
        FoundationConfig.from_env({
            "MITATEDB_DATA_BASE_URL": _VALID_DATA_BASE_URL,
            "MITATEDB_CONTROL_PLANE_STATUS": "enabled",
            "MITATEDB_CONTROL_BASE_URL": "https://mitatedb.example.invalid/control/v1/",
        })


def test_from_env_rejects_an_absent_control_base_url_when_control_plane_is_not_unavailable() -> None:
    with pytest.raises(ValidationError, match="MITATEDB_CONTROL_BASE_URL"):
        FoundationConfig.from_env({
            "MITATEDB_DATA_BASE_URL": _VALID_DATA_BASE_URL,
            "MITATEDB_CONTROL_PLANE_STATUS": "enabled",
        })


def test_from_env_accepts_a_well_formed_control_base_url() -> None:
    config = FoundationConfig.from_env({
        "MITATEDB_DATA_BASE_URL": _VALID_DATA_BASE_URL,
        "MITATEDB_CONTROL_PLANE_STATUS": "enabled",
        "MITATEDB_CONTROL_BASE_URL": _VALID_CONTROL_BASE_URL,
    })
    assert config.control_base_url == _VALID_CONTROL_BASE_URL


# ---------------------------------------------------------------------------
# WP-3 差し戻し 最終ラウンド (裁定 5, review F6): a deployment declaring
# `control_plane: unavailable` must never surface `surfaces.control` --
# `MITATEDB_CONTROL_BASE_URL` being present in the environment (a stale
# leftover from a previous configuration, say) must not resurrect it.
# ---------------------------------------------------------------------------


def test_from_env_omits_control_base_url_when_control_plane_status_is_unavailable_even_if_set() -> None:
    config = FoundationConfig.from_env({
        "MITATEDB_DATA_BASE_URL": _VALID_DATA_BASE_URL,
        "MITATEDB_CONTROL_PLANE_STATUS": "unavailable",
        "MITATEDB_CONTROL_BASE_URL": _VALID_CONTROL_BASE_URL,
    })
    assert config.control_base_url is None


def test_from_env_rejects_a_data_base_url_ending_in_the_control_suffix() -> None:
    """裁定 4 (F5): data/control 終端の相互排他 -- `/control/v1` itself
    ends with the substring `/v1`, so `MITATEDB_DATA_BASE_URL`'s own
    `suffix="/v1"` check ALONE would accept a value that is actually a
    control-surface URL. Mirrors r2db-api's own identical guard
    (coordinator item 7(ii))."""
    with pytest.raises(ValidationError, match="MITATEDB_DATA_BASE_URL"):
        FoundationConfig.from_env({"MITATEDB_DATA_BASE_URL": "https://mitatedb.example.invalid/control/v1"})


def test_from_env_accepts_a_control_base_url_ending_in_the_control_suffix_even_though_it_also_ends_in_v1() -> None:
    """The exclusivity guard is one-directional only (`surfaces.py`'s own
    `_validate_surface_base_url` docstring) -- `MITATEDB_CONTROL_BASE_URL`
    needs no symmetric guard, since a bare `/v1`-ending value never
    satisfies its own `suffix == CONTROL_SUFFIX` check in the first
    place. This is the well-formed control case, included here to pin
    that the new guard does not over-reject it."""
    config = FoundationConfig.from_env({
        "MITATEDB_DATA_BASE_URL": _VALID_DATA_BASE_URL,
        "MITATEDB_CONTROL_PLANE_STATUS": "enabled",
        "MITATEDB_CONTROL_BASE_URL": _VALID_CONTROL_BASE_URL,
    })
    assert config.control_base_url == _VALID_CONTROL_BASE_URL


def test_from_env_omits_control_base_url_by_default_when_control_plane_status_is_absent() -> None:
    """`MITATEDB_CONTROL_PLANE_STATUS` unset defaults to `"unavailable"`
    (`config.py`'s own R-9 default) -- the same omission must hold then
    too, not only when the status is set explicitly."""
    config = FoundationConfig.from_env({
        "MITATEDB_DATA_BASE_URL": _VALID_DATA_BASE_URL,
        "MITATEDB_CONTROL_BASE_URL": _VALID_CONTROL_BASE_URL,
    })
    assert config.control_plane_status == "unavailable"
    assert config.control_base_url is None
