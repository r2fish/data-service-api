"""Composition root for the `/control/v1` ASGI process (WP-5 flip, design
v1.2 R-6/R-7/R-9).

**Deployment default (R-6/R-9)**: `mitatedb_api.main` (the application-plane
process, `uvicorn mitatedb_api.main:app`) and this module (the control-plane
process, `uvicorn mitatedb_api.control_main:app`) are the SAME image, TWO
entrypoints, meant to run as separate processes/services by default (R-6:
"独立 ASGI app...同居可能な構造にはするが既定は分離"). A single conformance
build MAY assemble both in one Python process (`MitateDB-api-http`'s own
conformance adapter does exactly that), but this module itself never assumes
that: it has no reference to `main.py`'s own module-level `app` and does not
need one.

This module is a NEW file, not an addition to `main.py`'s own `build_app`/
module-level `app` (design v1.2 §5's own single-commit flip rule, applied
here the same way r2db-api's sibling `r2db_api.control_main` already keeps
`R2DB_CONTROLPLANE_DSN` etc. out of `r2db_api.main`'s own import-time
requirements): `main.py`'s own `app = build_app()` statement runs at import
time and is exercised by every application-plane test in this repository
(`test_main.py`'s own `main_module` fixture) with an environment that never
sets `MITATEDB_CONTROLPLANE_DSN`/`MITATEDB_CONTROL_CREDENTIAL_PEPPER` as
REQUIRED values -- putting a module-level `app = build_control_app()`
statement directly inside `main.py` would make importing that module alone
fail startup validation for every one of those existing tests. Keeping the
control-plane entrypoint in its own module, with its own module-level `app`,
is what lets each process' own required-environment contract stay exactly
as narrow as that process' own job (mirrors r2db-api's identical file
split, not code sharing with it -- the composition logic below reuses only
THIS peer's own `control_composition.build_control_service`/`control_http.
create_control_app`).

Environment variable contract: identical to `control_composition.
build_control_service`'s own documented contract (`MITATEDB_CREDENTIAL_PEPPER`,
`MITATEDB_CONTROL_CREDENTIAL_PEPPER`, `MITATEDB_CONTROLPLANE_DSN`,
`MITATEDB_PLATFORM_SCHEMA`, the four `MITATEDB_CONTROL_*_LIMIT` knobs) --
this module adds no new variable of its own beyond what mounting the ASGI
app itself requires.

R-6's own "control discovery (`control_capabilities`) は `request_bytes` を
最初から宣言する" instruction is realized here by sizing
`RequestByteBoundMiddleware`'s own byte bound from the SAME
`ControlPlaneLimits.request_bytes` value `control_capabilities()` publishes
(`ControlPlaneService.limits`, WP-5) -- never a second, independently
configured number (R-7's own "宣言値と enforce 値が同一ソースから出る" rule,
applied here to the control plane exactly as `main.py` already applies it to
the application plane's own `request_bytes` enforcement).
"""
from __future__ import annotations

import os
from typing import Mapping

from starlette.types import ASGIApp

from .control_composition import build_control_service
from .control_http import create_control_app


def build_control_app(env: Mapping[str, str] | None = None) -> ASGIApp:
    """Assembles the `/control/v1` ASGI app from `env` (defaults to
    `os.environ`). Factored out of the module-level `app` below so this
    repository's own tests can exercise the full environment-validation and
    assembly logic -- including `build_control_service`'s own required-env
    and pepper-separation failure paths -- without importing this module at
    all (which would otherwise require a real control-plane environment at
    import time, mirroring `main.build_app`'s own identical reason for
    factoring `build_app` out from its own module-level `app`)."""
    env = env if env is not None else os.environ
    service = build_control_service(env)
    return create_control_app(service, request_bytes_limit=service.limits.request_bytes)


# WP-5 flip (design v1.2 §5): the literal uvicorn/systemd entry point for
# the control-plane process, `uvicorn mitatedb_api.control_main:app` (or any
# ASGI server pointed at this module) -- landed in the same single commit
# that flips `cell.py`'s `control_plane` declaration to read from
# `config.control_plane_status` instead of a hardcoded `"unavailable"`
# literal (R-7's "宣言変更と mount...が単一コミットで同時に動く" rule).
app = build_control_app()

__all__ = ["build_control_app", "app"]
