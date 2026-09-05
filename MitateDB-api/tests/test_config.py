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

Q4 phase (design docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md D-2, work order
§4 WP-2 変更対象 E): `from_env` no longer reads `MITATEDB_DATA_BASE_URL`/
`MITATEDB_CONTROL_BASE_URL` from `environ` at all -- those two REMOVED env
vars are rejected at composition-root startup (F-2,
`platform_declarations.reject_removed_surface_env`), and the caller
(`main.build_app`) now reads+validates `surfaces` from `<registry>.
platform_declarations` (F-3/F-5) BEFORE calling `from_env`, passing the
already-validated values as the `data_base_url`/`control_base_url` keyword
arguments this factory now requires. The 4-form format-validation gap this
file's own Phase 6 WP-3 追補 closed (relative URL / wrong suffix /
trailing slash / cross-suffix exclusivity) moved WITH the validation call
site -- it is now `test_platform_declarations.py::test_validate_surfaces_*`
(the same `surfaces.py` validators, called from `platform_declarations.
validate_surfaces_value` instead of from `config.py`). What THIS file still
owns is `from_env`'s own remaining logic: the `control_plane_status`
two-member vocabulary check (unaffected by this phase) and the "`control_
base_url` is silently dropped whenever `control_plane_status ==
'unavailable'`, even if a non-`None` value was passed in" gate -- design
D-2(f) explicitly says this gate itself did NOT move (`main.build_app`'s
own `check_control_surface_consistency` raises F-6 BEFORE `from_env` is
ever reached whenever the two disagree, so by the time `from_env` runs
they already agree or the process has already failed to start) -- kept
here as a second, structural line of defense on the dataclass' own
narrowest construction path, exactly like the pre-existing `control_plane_
status` double-coverage above.
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
        FoundationConfig.from_env({"MITATEDB_CONTROL_PLANE_STATUS": "ENABLED"}, data_base_url="https://h/v1")


_VALID_DATA_BASE_URL = "https://mitatedb.example.invalid/v1"
_VALID_CONTROL_BASE_URL = "https://mitatedb.example.invalid/control/v1"


def test_from_env_rejects_an_absent_data_base_url() -> None:
    """Q4 phase: `data_base_url=None` now means the CALLER never had a
    `surfaces.data` row to give it (F-3 would already have fired inside
    `main.build_app`, well before this call -- but `from_env` itself still
    refuses to construct a `FoundationConfig` with no data surface at
    all, a second, narrower line of defense)."""
    with pytest.raises(ValidationError, match="surfaces.data"):
        FoundationConfig.from_env({})


def test_from_env_accepts_a_well_formed_data_base_url() -> None:
    config = FoundationConfig.from_env({}, data_base_url=_VALID_DATA_BASE_URL)
    assert config.data_base_url == _VALID_DATA_BASE_URL


def test_from_env_accepts_a_well_formed_control_base_url() -> None:
    config = FoundationConfig.from_env(
        {"MITATEDB_CONTROL_PLANE_STATUS": "enabled"},
        data_base_url=_VALID_DATA_BASE_URL, control_base_url=_VALID_CONTROL_BASE_URL,
    )
    assert config.control_base_url == _VALID_CONTROL_BASE_URL


# ---------------------------------------------------------------------------
# WP-3 差し戻し 最終ラウンド (裁定 5, review F6) -- Q4 D-2(f) OVERRIDES this
# ruling for the REMOVED-env-var read (see `config.py`'s own historical
# note), but the underlying STRUCTURAL gate on `from_env` itself (never
# surface a non-`None` `control_base_url` argument while `control_plane_
# status == "unavailable"`) is a deliberately-kept second line of defense
# -- `main.build_app`'s own F-6 check (`check_control_surface_consistency`)
# already refuses to reach this call at all when the two disagree, so this
# assertion documents that `from_env` does not ALSO silently trust a
# caller that (incorrectly) called it directly with mismatched arguments.
# ---------------------------------------------------------------------------


def test_from_env_omits_control_base_url_when_control_plane_status_is_unavailable_even_if_given() -> None:
    config = FoundationConfig.from_env(
        {"MITATEDB_CONTROL_PLANE_STATUS": "unavailable"},
        data_base_url=_VALID_DATA_BASE_URL, control_base_url=_VALID_CONTROL_BASE_URL,
    )
    assert config.control_base_url is None


def test_from_env_omits_control_base_url_by_default_when_control_plane_status_is_absent() -> None:
    """`MITATEDB_CONTROL_PLANE_STATUS` unset defaults to `"unavailable"`
    (`config.py`'s own R-9 default) -- the same omission must hold then
    too, not only when the status is set explicitly."""
    config = FoundationConfig.from_env(
        {}, data_base_url=_VALID_DATA_BASE_URL, control_base_url=_VALID_CONTROL_BASE_URL,
    )
    assert config.control_plane_status == "unavailable"
    assert config.control_base_url is None
