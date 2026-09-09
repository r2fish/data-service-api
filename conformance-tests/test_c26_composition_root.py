"""C-26 "配備 composition の証拠" (design docs/design/
PHASE10_DEPLOYMENT_EVIDENCE_V1.md D-1 (B), work order docs/work-orders/
WORK_ORDER_PHASE10_DEPLOYMENT_EVIDENCE_V1.md WP-6c).

Drives every launcher registered in `conformance-tests/registry.json`'s
own `composition_roots` section (`conftest.py`'s `launcher_class` fixture)
through the six observations design D-1 (B) states:

  1. real startup order (declare before uvicorn before nginx before
     readiness).
  2. `surfaces.data`/`surfaces.control`, read from the peer's OWN
     declaration table (via the composition root's own real startup
     path -- never injected by this test), each answer over real TCP.
  3. `tools/deploy_smoke.py`, run as a real subprocess, exits 0 against
     the running deployment.
  4. `process_ceilings` declared 1 vs. 2 (one real restart in between)
     exhibits the `limit_enforcement` mapping those ceilings imply.
  5. a missing `process_ceilings` declaration makes startup fail fast,
     never start on a default.
  6. shutdown leaves no process and no bound port behind.

This module is never a `ConformanceAdapter` plug and takes no `adapter`/
`fx` fixture -- it is a wholly separate kind of fixture (real subprocess
composition roots, not the common port), so none of `conftest.py`'s
adapter-scoped machinery (`_wp5_application_residue_guard`, the C-10
scanning proxy, etc.) applies to it.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from types import SimpleNamespace
from typing import Any

import pytest

from conftest import ROOT, registered_composition_roots

pytestmark = pytest.mark.condition("C-26")


def _get_json(url: str, bearer: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"authorization": f"Bearer {bearer}"})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read())


def _run_deploy_smoke(*, data_base_url: str, bearer: str) -> subprocess.CompletedProcess:
    """Completion condition 3 (design D-1 (B) 3): `tools/deploy_smoke.py`
    run as a real, SEPARATE subprocess (never imported and called as a
    function) against the launcher's own running deployment. The bearer
    secret is passed through an environment variable NAME, per that
    tool's own SI-10 contract (`--api-key-env`) -- never as a literal
    argument. `deploy_smoke.py` appends its own `/v1/...` paths, so it
    wants the bare origin, not the launcher's own `.data_base_url`
    (already suffixed `/v1`)."""
    origin = data_base_url.rsplit("/v1", 1)[0]
    env = dict(os.environ)
    env["C26_SMOKE_BASE_URL"] = origin
    env["C26_SMOKE_API_KEY"] = bearer
    return subprocess.run(
        [
            sys.executable, str(ROOT / "tools" / "deploy_smoke.py"),
            "--base-url-env", "C26_SMOKE_BASE_URL",
            "--api-key-env", "C26_SMOKE_API_KEY",
            # A freshly provisioned application has zero entities -- stage
            # 3 genuinely cannot be performed at all, which is not itself
            # a failure of this launcher's own composition root (design
            # tools/deploy_smoke.py's own WP-4 rework #5 distinction).
            "--allow-empty-catalog",
        ],
        env=env, capture_output=True, text=True, timeout=30,
    )


@pytest.fixture(scope="module")
def lifecycle(launcher_class: type) -> SimpleNamespace:
    """Runs ONE launcher through its whole real-startup life cycle ONCE
    per module (session-scoped `launcher_class` parametrizes this
    indirectly, so `conftest.py`'s `pytest_collection_modifyitems` sees a
    `launcher_class` callspec param on every test using this fixture and
    places it in its own `c26-<peer>` xdist group, design D-1 (B) 8) --
    real provisioning + two real restarts is too expensive to redo per
    test function. Every test below reads its own slice of the captured
    `SimpleNamespace`; none of them re-drives the launcher itself except
    the fully self-contained fail-fast/residue tests, which build and
    tear down their OWN separate instance (never sharing this one)."""
    launcher = launcher_class()
    launcher.start(ceilings={"data": 1, "control": 1})
    try:
        events_after_first_start = list(launcher.startup_events())
        data_doc_1 = _get_json(f"{launcher.data_base_url}/capabilities", launcher.runtime_bearer)
        control_doc_1 = _get_json(f"{launcher.control_base_url}/capabilities", launcher.control_bearer)
        smoke_result = _run_deploy_smoke(data_base_url=launcher.data_base_url, bearer=launcher.runtime_bearer)

        launcher.restart(ceilings={"data": 2, "control": 2})
        data_doc_2 = _get_json(f"{launcher.data_base_url}/capabilities", launcher.runtime_bearer)
        control_doc_2 = _get_json(f"{launcher.control_base_url}/capabilities", launcher.control_bearer)

        yield SimpleNamespace(
            launcher=launcher,
            events=events_after_first_start,
            data_base_url=launcher.data_base_url,
            control_base_url=launcher.control_base_url,
            data_doc_1=data_doc_1,
            control_doc_1=control_doc_1,
            data_doc_2=data_doc_2,
            control_doc_2=control_doc_2,
            smoke_result=smoke_result,
        )
    finally:
        launcher.stop()


# ---------------------------------------------------------------------------
# Completion conditions 1 and 2 (design D-1 (B) 1-2)
# ---------------------------------------------------------------------------


def test_c26_declared_surfaces_are_served(lifecycle: SimpleNamespace) -> None:
    """(1) startup order is "declare -> uvicorn -> nginx -> readiness".
    (2) the `surfaces.data`/`surfaces.control` URLs the launcher itself
    declared through the real `ops declare-surfaces` CLI answer over real
    TCP, on BOTH planes, with a document a brand new client (this test's
    own `urllib` call, never the launcher's own provisioning connections)
    can read. Non-vacuity: at least one observation on each side."""
    events = lifecycle.events
    assert events, "no startup events were recorded at all"

    def _index(label: str) -> int:
        assert label in events, f"{label!r} never recorded; events were {events!r}"
        return events.index(label)

    # (1) real ordering: every declare event precedes every uvicorn start,
    # which precedes nginx, which precedes both readiness checks.
    last_declare = max(_index("declare_surfaces"), _index("declare_process_ceilings"))
    first_uvicorn = min(_index("uvicorn_data_start"), _index("uvicorn_control_start"))
    nginx_index = _index("nginx_start")
    first_readiness = min(_index("readiness_data"), _index("readiness_control"))
    assert last_declare < first_uvicorn, f"declare did not precede uvicorn start: {events!r}"
    assert first_uvicorn < nginx_index, f"uvicorn start did not precede nginx: {events!r}"
    assert nginx_index < first_readiness, f"nginx start did not precede readiness: {events!r}"

    # (2) both planes answer over real TCP with a readable document.
    assert "contract_version" in lifecycle.data_doc_1, lifecycle.data_doc_1
    assert "contract_version" in lifecycle.control_doc_1, lifecycle.control_doc_1
    assert lifecycle.data_base_url.startswith("http://127.0.0.1:")
    assert lifecycle.control_base_url.startswith("http://127.0.0.1:")


# ---------------------------------------------------------------------------
# Completion condition 3 (design D-1 (B) 3)
# ---------------------------------------------------------------------------


def test_c26_deploy_smoke_is_green(lifecycle: SimpleNamespace) -> None:
    """`tools/deploy_smoke.py`, run as a real subprocess against this
    launcher's own real, running deployment, exits 0."""
    result = lifecycle.smoke_result
    assert result.returncode == 0, (
        f"deploy_smoke.py exited {result.returncode} (expected 0): "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "stage1 capabilities" in result.stdout


# ---------------------------------------------------------------------------
# Completion condition 4 (design D-1 (B) 4, SI-08)
# ---------------------------------------------------------------------------


def test_c26_ceiling_maps_to_limit_enforcement(lifecycle: SimpleNamespace) -> None:
    """`process_ceilings` declared as 1, then as 2 (one real restart in
    between -- design's own "宣言値 -> limit_enforcement の写像が実起動で
    成立すること"), exhibits the mapping both planes' own `capability_
    status.rules` promise: `enforced` at ceiling 1, `deployment_required`
    at ceiling >= 2, for the in-memory-per-process-bound limit classes
    (`requests_per_minute` on the data plane, `control_requests_per_
    minute` on the control plane)."""
    data_1 = lifecycle.data_doc_1["limit_enforcement"]["requests_per_minute"]
    data_2 = lifecycle.data_doc_2["limit_enforcement"]["requests_per_minute"]
    control_1 = lifecycle.control_doc_1["limit_enforcement"]["control_requests_per_minute"]
    control_2 = lifecycle.control_doc_2["limit_enforcement"]["control_requests_per_minute"]

    assert data_1 == "enforced", f"ceiling=1 data requests_per_minute was {data_1!r}, expected 'enforced'"
    assert data_2 == "deployment_required", f"ceiling=2 data requests_per_minute was {data_2!r}, expected 'deployment_required'"
    assert control_1 == "enforced", f"ceiling=1 control_requests_per_minute was {control_1!r}, expected 'enforced'"
    assert control_2 == "deployment_required", f"ceiling=2 control_requests_per_minute was {control_2!r}, expected 'deployment_required'"


# ---------------------------------------------------------------------------
# Completion condition 5 (design D-1 (B) 5)
# ---------------------------------------------------------------------------


def test_c26_missing_declaration_fails_fast(launcher_class: type) -> None:
    """A composition root started with NO `process_ceilings` row declared
    fails fast (F-15, contract 1.8.0's own unconditional obligation) --
    never silently starts and serves on some default. Self-contained: this
    test builds its own separate throwaway platform (`attempt_start_
    without_process_ceilings`'s own docstring), independent of `lifecycle`
    above, and tears it down again before returning either way."""
    launcher = launcher_class()
    result = launcher.attempt_start_without_process_ceilings()
    assert result.returncode != 0, (
        f"a composition root with no process_ceilings declaration started "
        f"successfully (returncode 0) instead of failing fast: stdout={result.stdout!r}"
    )
    assert "F-15" in result.stderr, (
        f"expected an F-15 (contract 1.8.0's own process_ceilings fail-fast) message on stderr; "
        f"got returncode={result.returncode} stderr does not mention F-15"
    )


# ---------------------------------------------------------------------------
# Completion condition 6 (design D-1 (B) 6)
# ---------------------------------------------------------------------------


def test_c26_no_residue_after_shutdown(launcher_class: type) -> None:
    """After `stop()`, neither uvicorn subprocess nor nginx is still
    alive, and no port either of them held still has a listener. Self-
    contained -- its own launcher instance, started and stopped entirely
    within this one test, never shared with `lifecycle` above (whose own
    teardown happens at MODULE end, too late for this test to observe
    independently)."""
    launcher = launcher_class()
    launcher.start(ceilings={"data": 1, "control": 1})

    data_pid = launcher._data_handle.process.pid  # noqa: SLF001 -- residue observation only
    control_pid = launcher._control_handle.process.pid  # noqa: SLF001
    nginx_pid = launcher._nginx.process.pid  # noqa: SLF001
    ports = [launcher._data_handle.port, launcher._control_handle.port, launcher._listen_port]  # noqa: SLF001

    launcher.stop()

    import socket_harness as sh

    for pid, label in ((data_pid, "data uvicorn"), (control_pid, "control uvicorn"), (nginx_pid, "nginx")):
        alive = _pid_alive(pid)
        assert not alive, f"{label} (pid {pid}) is still alive after stop()"

    for port in ports:
        assert not sh._port_has_listener(port), f"port {port} still has a listener after stop()"  # noqa: SLF001


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


# ---------------------------------------------------------------------------
# Completion condition 7 (design D-1 (B) 7, non-vacuity; registry-guards
# group -- no `adapter`/`launcher_class` param of its own)
# ---------------------------------------------------------------------------


def test_c26_composition_roots_registry_has_at_least_two() -> None:
    """Non-vacuity guard: `composition_roots` names at least two entries
    (both peers), read directly from the live registry -- a single-peer
    registration can never make this condition pass on one launcher's
    evidence alone."""
    roots = registered_composition_roots()
    assert len(roots) >= 2, f"composition_roots has only {len(roots)} entr(y/ies): {sorted(roots)!r}"


# ---------------------------------------------------------------------------
# Completion condition 8 (design D-1 (B) 8)
# ---------------------------------------------------------------------------


def test_c26_items_are_grouped_per_launcher(request: pytest.FixtureRequest, launcher_class: type) -> None:
    """Every C-26 item carries its own `xdist_group` named `c26-<peer>`
    (`conftest.py`'s own `pytest_collection_modifyitems`) -- never the
    shared `registry-guards` group every whole-registry vacuity guard
    (e.g. the previous test, which takes no `launcher_class`/`adapter`
    param at all) falls into. Takes the `launcher_class` fixture itself
    (cheap -- returns a class, no I/O) purely so THIS test's own item is
    parametrized the identical way `conftest.py`'s hook keys off of, then
    reads its own node's marker back directly: if the work order's own
    mutation target (`conftest.py`: removing the C-26 group assignment)
    is applied, this item falls back to the shared `registry-guards`
    group and the name assertion below goes red."""
    marker = request.node.get_closest_marker("xdist_group")
    assert marker is not None, f"{request.node.nodeid} carries no xdist_group marker at all"
    peer_name = request.node.callspec.params["launcher_class"]
    assert marker.kwargs.get("name") == f"c26-{peer_name}", (
        f"{request.node.nodeid} carries xdist_group {marker.kwargs.get('name')!r}, "
        f"expected 'c26-{peer_name}'"
    )
