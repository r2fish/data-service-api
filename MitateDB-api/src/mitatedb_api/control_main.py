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

import asyncio
import os
import sys
from typing import Mapping

from starlette.types import ASGIApp

from .control_composition import build_control_service
from .control_http import create_control_app
from .pool import set_connection_application_name


def _workers_from_env(env: Mapping[str, str], name: str) -> int:
    """(design docs/design/MULTI_PROCESS_WORKER_V0_1.md D-1): identical
    discipline to `mitatedb_api.main._workers_from_env` -- `name` must be
    set, non-empty, and a positive integer; unset/empty/`0`/negative/
    non-numeric all stop startup naming `name`. `MITATEDB_CONTROL_WORKERS`
    is always `1` in a real deployment (this composition root never
    serves more than one worker) -- checked here, and again against
    `process_ceilings.control` inside `build_control_service`, rather than
    assumed."""
    raw = env.get(name)
    if not raw:
        raise RuntimeError(f"{name} is required to start mitatedb_api.control_main:build_control_app")
    try:
        value = int(raw)
    except ValueError:
        raise RuntimeError(f"{name} must be a positive integer, got {raw!r}") from None
    if value <= 0:
        raise RuntimeError(f"{name} must be a positive integer, got {raw!r}")
    return value


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
    # design D-1: always explicit, always `1` in a real deployment --
    # `build_control_service` compares it against the declared
    # `process_ceilings.control` once that is read.
    workers = _workers_from_env(env, "MITATEDB_CONTROL_WORKERS")
    # design D-4: every connection this control-plane process opens from
    # here on carries this `application_name` (`pool.py`'s own
    # module-level toggle) -- set here, in the real control-plane entry,
    # never inside `build_control_service`, which a conformance adapter
    # also calls inside a process that serves the data plane too.
    set_connection_application_name(f"MitateDB-api:control:{os.getpid()}")
    service = build_control_service(env, workers=workers)
    return create_control_app(service, request_bytes_limit=service.limits.request_bytes)


# WP-5 flip (design v1.2 §5): the literal uvicorn/systemd entry point for
# the control-plane process, `uvicorn mitatedb_api.control_main:app` (or any
# ASGI server pointed at this module) -- landed in the same single commit
# that flips `cell.py`'s `control_plane` declaration to read from
# `config.control_plane_status` instead of a hardcoded `"unavailable"`
# literal (R-7's "宣言変更と mount...が単一コミットで同時に動く" rule).
app = build_control_app()

__all__ = ["build_control_app", "app"]


# design docs/design/MULTI_PROCESS_WORKER_V0_1.md D-1: the `--preflight`
# one-shot entry. `python -m mitatedb_api.control_main --preflight`
# imports this module -- whose own module-level `app = build_control_
# app()` above already runs every startup-time check (`build_control_
# service`: F-1/F-2/F-8/F-3/F-3c/F-4/F-4b/F-5/F-13/F-7/F-9/F-10/F-11/
# F-15/F-16/F-18 and the workers-vs-ceiling check) exactly once and
# raises on an unsound environment -- Python's own unhandled-exception
# exit (non-zero, traceback on stderr) is the outcome for that path. The
# entry below reuses that same `app`, never building a second one.
async def _run_lifespan_once(asgi_app: ASGIApp) -> None:
    """Identical to `mitatedb_api.main._run_lifespan_once` (own copy, no
    code sharing between composition roots' own entry points): drives one
    ASGI `lifespan` startup+shutdown cycle against `asgi_app` without ever
    serving a request."""
    to_app: "asyncio.Queue[dict[str, str]]" = asyncio.Queue()
    from_app: "asyncio.Queue[dict[str, str]]" = asyncio.Queue()

    async def receive() -> dict[str, str]:
        return await to_app.get()

    async def send(message: dict[str, str]) -> None:
        await from_app.put(message)

    task = asyncio.ensure_future(asgi_app({"type": "lifespan"}, receive, send))
    await to_app.put({"type": "lifespan.startup"})
    startup_result = await from_app.get()
    if startup_result["type"] == "lifespan.startup.failed":
        raise RuntimeError(startup_result.get("message") or "lifespan startup failed")
    await to_app.put({"type": "lifespan.shutdown"})
    shutdown_result = await from_app.get()
    await task
    if shutdown_result["type"] == "lifespan.shutdown.failed":
        raise RuntimeError(shutdown_result.get("message") or "lifespan shutdown failed")


if __name__ == "__main__" and "--preflight" in sys.argv:
    asyncio.run(_run_lifespan_once(app))
    sys.exit(0)
