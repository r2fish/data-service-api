"""`surfaces` validation and construction (Phase 6 WP-3, design docs/design/
PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md D-2).

Contract 1.6.0 `CapabilityDocument.surfaces` names the absolute base URLs
at which this deployment's own surfaces are reached, AS DECLARED BY THE
DEPLOYER -- never derived, never inferred from the URL a client happened
to use. This peer's data-plane process (`main.py`) and control-plane
process (`control_main.py`/`control_composition.py`) are two separate OS
processes, neither of which ever connects to the other's own host (design
§1.5 finding 7) -- so there is no way for either to derive the other's
base URL. Both are instead given the SAME two environment variables,
`MITATEDB_DATA_BASE_URL` / `MITATEDB_CONTROL_BASE_URL`, and each
independently validates and echoes back only its OWN process' declared
values.

What a single process CAN verify, at startup, is the FORM of the value(s)
it was given: an absolute URL, ending at the right `versioning.base_path`
(`/v1`) or `versioning.control_base_path` (`/control/v1`), with no
trailing slash (`base_url + "/capabilities"` must never produce a doubled
slash). Whether the DATA process' and CONTROL process' own declarations
actually agree with each other is the deployer's own responsibility
(design D-2 (b)/(c)) -- this module never cross-validates, and no
component here ever reaches across processes to check.
"""
from __future__ import annotations

from typing import Optional
from urllib.parse import urlsplit

#: `versioning.base_path` (spec/data-service-api.v1.json).
DATA_SUFFIX = "/v1"
#: `versioning.control_base_path` (spec/data-service-api.v1.json).
CONTROL_SUFFIX = "/control/v1"


def _validate_surface_base_url(name: str, raw: str, *, suffix: str) -> str:
    """Phase 6 WP-3 差し戻し 最終ラウンド (supervisor ruling 2026-09-04,
    裁定 8): renamed from `_validate_base_url` to the same name AND the
    same `(name, raw, *, suffix)` parameter shape as r2db-api's own
    `main.py`/`control_main.py::_validate_surface_base_url` (that peer's
    own WP-2 realization of this identical D-2 obligation, duplicated
    verbatim across its two composition-root files rather than shared --
    this peer keeps its own one-module realization, `surfaces.py`, R-2's
    "no code sharing BETWEEN peers" principle governing only that, never
    a peer's own internal module layout).

    Checked as four independent conditions -- absent/non-string (the
    caller's own concern in practice; every real call site here only
    ever passes a non-empty `raw`), absolute URL (scheme + host), no
    trailing slash (`base_url + "/capabilities"` must never produce a
    doubled slash, F12 (ii)), and the required suffix -- so a value like
    `https://h/v1/` (the CORRECT suffix plus one trailing slash) is
    caught by the DEDICATED trailing-slash check, never silently
    absorbed by the suffix check's own slash-tolerant reading.
    """
    if not isinstance(raw, str) or not raw:
        raise ValueError(f"{name} must be a non-empty absolute URL")
    parsed = urlsplit(raw)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"{name} must be an absolute URL (scheme and host), got {raw!r}")
    if raw.endswith("/"):
        raise ValueError(f"{name} must not end with a trailing slash, got {raw!r}")
    if not raw.endswith(suffix):
        raise ValueError(f"{name} must end with {suffix!r}, got {raw!r}")
    # Mirrors r2db-api's own identical guard (coordinator item 7(ii)):
    # `/control/v1` itself ends with the substring `/v1`, so the DATA
    # suffix check alone (`suffix == DATA_SUFFIX`) would ACCEPT a value
    # that is actually a control-surface URL (e.g. `https://h/control/
    # v1`). Exclusive in one direction only: `MITATEDB_CONTROL_BASE_URL`
    # needs no symmetric guard -- a bare `/v1`-ending value never
    # satisfies its own `suffix == CONTROL_SUFFIX` check in the first
    # place, so it is already rejected by the ordinary suffix check above.
    if suffix == DATA_SUFFIX and raw.endswith(CONTROL_SUFFIX):
        raise ValueError(f"{name} must end with {suffix!r}, not {CONTROL_SUFFIX!r}, got {raw!r}")
    return raw


def validate_data_base_url(value: Optional[str], *, var_name: str = "MITATEDB_DATA_BASE_URL") -> Optional[str]:
    """Form-only check (never reachability). `None` passes through
    unchanged -- callers that require presence (a real deployment's own
    startup path) check for `None` themselves; this function's only job
    is validating the SHAPE of a value that is actually present."""
    if value is None:
        return None
    return _validate_surface_base_url(var_name, value, suffix=DATA_SUFFIX)


def validate_control_base_url(value: Optional[str], *, var_name: str = "MITATEDB_CONTROL_BASE_URL") -> Optional[str]:
    if value is None:
        return None
    return _validate_surface_base_url(var_name, value, suffix=CONTROL_SUFFIX)


def build_surfaces(*, data_url: Optional[str], control_url: Optional[str]) -> Optional[dict]:
    """The `surfaces` object for a `CapabilityDocument`, or `None` to omit
    the key entirely (used only where neither URL is configured -- a
    real 1.6.0 deployment always supplies `data_url` at minimum, since
    `surfaces.data` is an unconditional 1.6.0 obligation; the `None`
    escape hatch exists so pre-1.6.0-style construction paths that never
    set either variable keep working). `data` is included whenever
    `data_url` is given; `control` is included only when `control_url`
    is given (contract: a deployment declaring `control_plane` as
    `unavailable` omits `surfaces.control`)."""
    if data_url is None and control_url is None:
        return None
    surfaces: dict = {}
    if data_url is not None:
        surfaces["data"] = {"base_url": data_url}
    if control_url is not None:
        surfaces["control"] = {"base_url": control_url}
    return surfaces
