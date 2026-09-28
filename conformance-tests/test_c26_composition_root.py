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
import time
import urllib.request
from types import SimpleNamespace
from typing import Any

import psycopg
import pytest

from conftest import ROOT, registered_composition_roots

pytestmark = pytest.mark.condition("C-26")


def _get_json(url: str, bearer: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"authorization": f"Bearer {bearer}"})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read())


#: design D-3 (4), 裁定 18/27: `concurrency`'s own mapping depends on
#: workers vs. `process_ceilings` (`data_multi_process_mapping_
#: configured`); `requests_per_minute`'s own mapping depends ONLY on
#: whether the PostgreSQL-backed rate-row strategy is wired at all,
#: regardless of workers/ceiling (`data_rate_row_configured`). Kept as an
#: explicit table (rather than an `if/elif` buried in the cross-check
#: function below) so a THIRD class arriving later fails loudly (`KeyError`)
#: instead of silently reusing the wrong accessor.
_ACCESSOR_FOR_LIMIT_CLASS: dict[str, str] = {
    "concurrency": "data_multi_process_mapping_configured",
    "requests_per_minute": "data_rate_row_configured",
}


def configured_for_limit_class(launcher: Any, limit_class: str) -> bool:
    """Dispatches to the ONE accessor `limit_class`'s own `limit_
    enforcement` mapping actually depends on (`_ACCESSOR_FOR_LIMIT_CLASS`
    above) and calls it. Callers needing a POINT-IN-TIME snapshot (design
    裁定27's `concurrency` condition changes across a `restart()`) call
    this at the moment that matters, e.g. right after the relevant
    `start()`/`restart()`; `requests_per_minute`'s own accessor is
    constant for a real-server launcher (裁定18), so calling it at test
    time is always safe."""
    accessor_name = _ACCESSOR_FOR_LIMIT_CLASS[limit_class]
    return getattr(launcher, accessor_name)()


def cross_check_limit_enforcement_declaration(
    value: str, *, configured: bool, limit_class: str, form_label: str,
) -> bool:
    """Design 裁定12: at ceiling >= 2, a peer may honestly declare either
    `enforced` or `deployment_required` for `limit_class` -- `enforced`
    binds the new shared-limit conditions (design D-4), a peer declaring
    `deployment_required` stays conformant without them ("現行どおり適
    合"). Cross-checked against `configured` (`configured_for_limit_
    class()`'s own return value -- whichever of `data_multi_process_
    mapping_configured()`/`data_rate_row_configured()` actually governs
    `limit_class`, design 裁定18/27) so neither direction can pass
    silently (`OPERATING_CONDITIONS.md` §1.5 の 32, no vacuous pass): a
    peer declaring `enforced` while `configured` is `False`, or declaring
    `deployment_required` while it is `True`, both fail here. Mirrors
    `test_c30_keyset_paging.py`'s own `observed_branch` cross-check shape
    (a real value compared against what the caller's own setup implies,
    never accepted unconditionally either way). Returns `True` when the
    caller should drive the shared-limit condition's own body (the
    `enforced` branch), `False` when it should record the `deployment_
    required` branch and pass without driving it."""
    assert value in ("enforced", "deployment_required"), (
        f"{form_label} {limit_class}: limit_enforcement was {value!r}, expected 'enforced' or 'deployment_required'"
    )
    if configured:
        assert value == "enforced", (
            f"{form_label} {limit_class}: this launcher configured the wiring its own mapping requires for "
            f"'enforced' ({_ACCESSOR_FOR_LIMIT_CLASS[limit_class]}() == True), but the served document declares "
            f"{value!r} instead"
        )
        return True
    assert value == "deployment_required", (
        f"{form_label} {limit_class}: this launcher did NOT configure the wiring its own mapping requires "
        f"({_ACCESSOR_FOR_LIMIT_CLASS[limit_class]}() == False), but the served document declares {value!r} "
        f"instead of 'deployment_required'"
    )
    return False


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
        # Captured HERE, before `restart()` below overwrites `data_
        # preflight_result` with its OWN preflight's result.
        data_preflight_result_after_first_start = launcher.data_preflight_result
        data_doc_1 = _get_json(f"{launcher.data_base_url}/capabilities", launcher.runtime_bearer)
        control_doc_1 = _get_json(f"{launcher.control_base_url}/capabilities", launcher.control_bearer)
        smoke_result = _run_deploy_smoke(data_base_url=launcher.data_base_url, bearer=launcher.runtime_bearer)

        launcher.restart(ceilings={"data": 2, "control": 2})
        data_doc_2 = _get_json(f"{launcher.data_base_url}/capabilities", launcher.runtime_bearer)
        control_doc_2 = _get_json(f"{launcher.control_base_url}/capabilities", launcher.control_bearer)

        yield SimpleNamespace(
            launcher=launcher,
            events=events_after_first_start,
            data_preflight_result_after_first_start=data_preflight_result_after_first_start,
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
    can read. Non-vacuity: at least one observation on each side.

    F1 differential review (2026-09-09): the dial target for (2) is the
    SERVED `surfaces.data`/`surfaces.control` value read from the
    capabilities document -- never the launcher's own `data_base_url`/
    `control_base_url` PROPERTIES, which are computed independently of
    what `ops declare-surfaces` actually persisted and therefore stay
    "correct" even when a composition root declared a DIFFERENT,
    unreachable URL (the original, vacuous form of this test: mutating
    `real_server_r2db.py`'s own `start()` so `--control-base-url` names
    `http://127.0.0.1:1/control/v1` -- a well-formed but unreachable URL,
    unrelated to the real deployment -- left all six C-26 assertions
    green, because nothing ever dialed the declared value itself). Both
    planes read the SAME single `platform_declarations` row (design
    D-2(c)), so agreement between the two documents alone cannot by
    itself catch a wrong-but-mutually-consistent declaration; this also
    reads the row back directly over SQL, and -- decisively -- DIALS the
    served value itself, so a declaration naming an unreachable URL fails
    HERE."""
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

    # (2) both planes answer over real TCP with a readable document ...
    assert "contract_version" in lifecycle.data_doc_1, lifecycle.data_doc_1
    assert "contract_version" in lifecycle.control_doc_1, lifecycle.control_doc_1
    assert lifecycle.data_base_url.startswith("http://127.0.0.1:")
    assert lifecycle.control_base_url.startswith("http://127.0.0.1:")

    # ... and the `surfaces` THEY SERVE is what this test actually dials
    # (F1): both planes' own documents must agree with each other, agree
    # with the row `ops declare-surfaces` actually wrote (read back
    # directly over SQL, never trusted from the CLI's own exit code
    # alone), and -- the decisive check -- answer over real TCP when
    # dialed AT THAT SERVED VALUE.
    data_surfaces = lifecycle.data_doc_1["surfaces"]
    control_surfaces = lifecycle.control_doc_1["surfaces"]
    assert data_surfaces == control_surfaces, (
        f"data plane and control plane served different 'surfaces': "
        f"{data_surfaces!r} != {control_surfaces!r}"
    )
    recorded = lifecycle.launcher.read_declared_surfaces()
    assert data_surfaces == recorded, (
        f"served 'surfaces' {data_surfaces!r} does not match the row SQL-read "
        f"back from platform_declarations {recorded!r}"
    )
    declared_data_url = data_surfaces["data"]["base_url"]
    declared_control_url = data_surfaces["control"]["base_url"]

    redialed_data = _get_json(f"{declared_data_url}/capabilities", lifecycle.launcher.runtime_bearer)
    assert "contract_version" in redialed_data, redialed_data
    redialed_control = _get_json(f"{declared_control_url}/capabilities", lifecycle.launcher.control_bearer)
    assert "contract_version" in redialed_control, redialed_control


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
# design D-3 (4) (裁定 27/35): 3 real startup forms -- completion
# conditions 8-12. Never shares a launcher instance with `lifecycle` above.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def multi_worker_ceiling_forms(launcher_class: type) -> SimpleNamespace:
    """Drives ONE launcher instance through 3 real startup forms --
    (ceiling=1, workers=1), (ceiling=2, workers=2), (ceiling=2, workers=1)
    -- capturing each form's own served capabilities documents (裁定 35:
    the 3 forms C-26 (4) now observes)."""
    launcher = launcher_class()
    launcher.start(ceilings={"data": 1, "control": 1}, workers=1)
    try:
        data_doc_ceiling1_workers1 = _get_json(f"{launcher.data_base_url}/capabilities", launcher.runtime_bearer)
        control_doc_ceiling1_workers1 = _get_json(f"{launcher.control_base_url}/capabilities", launcher.control_bearer)
        concurrency_configured_ceiling1_workers1 = configured_for_limit_class(launcher, "concurrency")

        launcher.restart(ceilings={"data": 2, "control": 2}, workers=2)
        data_doc_ceiling2_workers2 = _get_json(f"{launcher.data_base_url}/capabilities", launcher.runtime_bearer)
        control_doc_ceiling2_workers2 = _get_json(f"{launcher.control_base_url}/capabilities", launcher.control_bearer)
        # Captured HERE, before the next `restart()` below overwrites
        # `data_preflight_result`/`data_multi_process_mapping_configured`
        # with the workers=1 leg's own result. `requests_per_minute`'s own
        # accessor (`data_rate_row_configured`) is constant for a real-
        # server launcher (裁定18) so it needs no per-form snapshot at all
        # -- only `concurrency`'s own (`data_multi_process_mapping_
        # configured`, which tracks workers vs. ceiling) does.
        data_preflight_result_workers2 = launcher.data_preflight_result
        concurrency_configured_ceiling2_workers2 = configured_for_limit_class(launcher, "concurrency")

        launcher.restart(ceilings={"data": 2, "control": 2}, workers=1)
        data_doc_ceiling2_workers1 = _get_json(f"{launcher.data_base_url}/capabilities", launcher.runtime_bearer)
        concurrency_configured_ceiling2_workers1 = configured_for_limit_class(launcher, "concurrency")

        yield SimpleNamespace(
            launcher=launcher,
            data_doc_ceiling1_workers1=data_doc_ceiling1_workers1,
            control_doc_ceiling1_workers1=control_doc_ceiling1_workers1,
            concurrency_configured_ceiling1_workers1=concurrency_configured_ceiling1_workers1,
            data_doc_ceiling2_workers2=data_doc_ceiling2_workers2,
            control_doc_ceiling2_workers2=control_doc_ceiling2_workers2,
            concurrency_configured_ceiling2_workers2=concurrency_configured_ceiling2_workers2,
            data_doc_ceiling2_workers1=data_doc_ceiling2_workers1,
            concurrency_configured_ceiling2_workers1=concurrency_configured_ceiling2_workers1,
            data_preflight_result_workers2=data_preflight_result_workers2,
        )
    finally:
        launcher.stop()


def test_c26_ceiling1_workers1_all_classes_enforced(multi_worker_ceiling_forms: SimpleNamespace) -> None:
    """Completion condition 8: ceiling=1/workers=1 -- data `concurrency`,
    data `requests_per_minute`, and control `control_requests_per_minute`
    are all `enforced`."""
    data_doc = multi_worker_ceiling_forms.data_doc_ceiling1_workers1
    control_doc = multi_worker_ceiling_forms.control_doc_ceiling1_workers1
    concurrency = data_doc["limit_enforcement"]["concurrency"]
    requests_per_minute = data_doc["limit_enforcement"]["requests_per_minute"]
    control_requests_per_minute = control_doc["limit_enforcement"]["control_requests_per_minute"]
    assert concurrency == "enforced", f"ceiling=1/workers=1 concurrency was {concurrency!r}, expected 'enforced'"
    assert requests_per_minute == "enforced", (
        f"ceiling=1/workers=1 requests_per_minute was {requests_per_minute!r}, expected 'enforced'"
    )
    assert control_requests_per_minute == "enforced", (
        f"ceiling=1/workers=1 control_requests_per_minute was {control_requests_per_minute!r}, expected 'enforced'"
    )


def test_c26_ceiling2_workers2_concurrency_declaration_matches_wiring(multi_worker_ceiling_forms: SimpleNamespace) -> None:
    """Completion condition 9 (design 裁定 12/27, slot directory wired to
    workers=2): ceiling=2/workers=2 -- data `concurrency`'s own `enforced`/
    `deployment_required` declaration is cross-checked against whether
    this launcher actually configured the wiring 裁定27 requires, rather
    than asserted unconditionally (裁定12: a peer honestly declaring
    `deployment_required` at ceiling >= 2 stays conformant; this row's own
    obligation, for such a peer, is only this mapping cross-check)."""
    ns = multi_worker_ceiling_forms
    value = ns.data_doc_ceiling2_workers2["limit_enforcement"]["concurrency"]
    cross_check_limit_enforcement_declaration(
        value, configured=ns.concurrency_configured_ceiling2_workers2,
        limit_class="concurrency", form_label="ceiling=2/workers=2",
    )


def test_c26_ceiling2_workers1_concurrency_deployment_required(multi_worker_ceiling_forms: SimpleNamespace) -> None:
    """Completion condition 10 (裁定 27, honest sub-declared workers):
    ceiling=2/workers=1 -- data `concurrency` is `deployment_required`
    (the ceiling exceeds this supervisor's own worker count -- a second
    process could be on a DIFFERENT host, where the slot would not be
    shared)."""
    value = multi_worker_ceiling_forms.data_doc_ceiling2_workers1["limit_enforcement"]["concurrency"]
    assert value == "deployment_required", f"ceiling=2/workers=1 concurrency was {value!r}, expected 'deployment_required'"


def test_c26_ceiling2_requests_per_minute_declaration_matches_wiring_both_worker_forms(
    multi_worker_ceiling_forms: SimpleNamespace,
) -> None:
    """Completion condition 11 (design D-3 (4), 裁定 12/18/27): at
    ceiling=2, `requests_per_minute`'s own declaration is cross-checked on
    BOTH worker forms (workers=2 and workers=1) -- never asserted
    unconditionally (裁定12). Unlike `concurrency` (completion condition
    9), `requests_per_minute`'s own mapping depends ONLY on whether the
    PostgreSQL-backed rate-row strategy is wired (裁定18), never on
    workers vs. ceiling -- so `configured_for_limit_class(launcher,
    "requests_per_minute")` (constant `True` for this real-server
    launcher, `data_rate_row_configured()`) is read fresh for BOTH forms,
    never the workers-vs-ceiling-sensitive `concurrency` accessor."""
    ns = multi_worker_ceiling_forms
    rate_configured = configured_for_limit_class(ns.launcher, "requests_per_minute")
    for label, doc in (
        ("workers=2", ns.data_doc_ceiling2_workers2),
        ("workers=1", ns.data_doc_ceiling2_workers1),
    ):
        value = doc["limit_enforcement"]["requests_per_minute"]
        cross_check_limit_enforcement_declaration(
            value, configured=rate_configured, limit_class="requests_per_minute", form_label=f"ceiling=2 ({label})",
        )


def test_c26_control_ceiling2_deployment_required(multi_worker_ceiling_forms: SimpleNamespace) -> None:
    """Completion condition 12: control ceiling=2 (control workers always
    1) -- `control_requests_per_minute` is `deployment_required` (control
    plane's 2 classes stay in-memory, unchanged by this WP)."""
    value = multi_worker_ceiling_forms.control_doc_ceiling2_workers2["limit_enforcement"]["control_requests_per_minute"]
    assert value == "deployment_required", f"control ceiling=2 control_requests_per_minute was {value!r}, expected 'deployment_required'"


def test_c26_slot_directory_is_per_instance_and_removed_on_stop(launcher_class: type) -> None:
    """Completion condition 4 (design D-3 (2'), 裁定 27): two DIFFERENT
    launcher instances, each started with ceiling=2/workers=2 (the ONLY
    form the `concurrency` mapping declares `enforced` for, 裁定 27 --
    ceiling=1/workers=2 would fail a future workers <= ceiling startup
    check for an unrelated reason), get a DIFFERENT slot directory (mode
    0700), and neither directory survives `stop()`. Self-contained -- its
    own two launcher instances, never shared with `lifecycle`/`multi_
    worker_ceiling_forms` above."""
    launcher_a = launcher_class()
    launcher_b = launcher_class()
    launcher_a.start(ceilings={"data": 2, "control": 2}, workers=2)
    try:
        launcher_b.start(ceilings={"data": 2, "control": 2}, workers=2)
        try:
            slot_a = launcher_a._slot_dir  # noqa: SLF001 -- residue/identity observation only
            slot_b = launcher_b._slot_dir  # noqa: SLF001
            assert slot_a is not None and slot_b is not None
            assert slot_a != slot_b, f"two launcher instances share the same slot directory: {slot_a!r}"
            assert slot_a.exists() and slot_b.exists()
            assert (slot_a.stat().st_mode & 0o777) == 0o700, (
                f"{slot_a} mode is {oct(slot_a.stat().st_mode & 0o777)}, expected 0700"
            )
        finally:
            launcher_b.stop()
        assert not slot_b.exists(), f"{slot_b} still exists after stop()"
    finally:
        launcher_a.stop()
    assert not slot_a.exists(), f"{slot_a} still exists after stop()"


def test_c26_preflight_precedes_data_uvicorn_start(lifecycle: SimpleNamespace) -> None:
    """Completion condition 5 (design 裁定 26): the preflight one-shot
    ACTUALLY ran (its own real argv/returncode, not merely a recorded
    event label) and precedes the data plane's own uvicorn start, in the
    real recorded event order `lifecycle` already captures."""
    events = lifecycle.events
    assert "preflight_data" in events, f"'preflight_data' never recorded; events were {events!r}"
    assert events.index("preflight_data") < events.index("uvicorn_data_start"), (
        f"preflight_data did not precede uvicorn_data_start: {events!r}"
    )
    result = lifecycle.data_preflight_result_after_first_start
    assert "--preflight" in result.args, f"preflight argv carries no --preflight: {result.args!r}"
    assert any(arg.endswith(".main") for arg in result.args), (
        f"preflight argv carries no '<package>.main' module argument: {result.args!r}"
    )
    assert result.returncode == 0, (
        f"data plane preflight exited {result.returncode} (expected 0) on a normally-declared "
        f"deployment: stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_c26_preflight_precedes_data_uvicorn_start_with_workers_2(multi_worker_ceiling_forms: SimpleNamespace) -> None:
    """Same observation as `test_c26_preflight_precedes_data_uvicorn_start`
    above, on the `workers >= 2` startup form (`multi_worker_ceiling_
    forms`'s own ceiling=2/workers=2 leg) -- preflight is not only a
    workers=1 behavior."""
    result = multi_worker_ceiling_forms.data_preflight_result_workers2
    assert "--preflight" in result.args, f"preflight argv carries no --preflight: {result.args!r}"
    assert any(arg.endswith(".main") for arg in result.args), (
        f"preflight argv carries no '<package>.main' module argument: {result.args!r}"
    )
    assert result.returncode == 0, (
        f"data plane preflight exited {result.returncode} (expected 0) on a normally-declared "
        f"deployment: stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_c26_access_log_pids_are_readable_for_200_responses(lifecycle: SimpleNamespace) -> None:
    """Completion condition 6 (design 裁定 17): the data plane's own
    pid-tagged access log is saved and readable, with a real pid attached
    to at least one `200` response row (`lifecycle`'s own dials already
    generate one)."""
    pids = lifecycle.launcher.access_log_pids_for_status(200)
    assert pids, "access_log_pids_for_status(200) observed 0 rows (空振り -- nothing was exercised)"


def test_c26_retained_lock_hold_is_strictly_below_the_safe_bound(lifecycle: SimpleNamespace) -> None:
    """Completion condition 7 (design 裁定 14): the launcher's own
    retained-lock upper bound is strictly shorter than min(declared
    `execution_ms`, the application role's own real `statement_timeout`)
    -- a real margin, never equal to either."""
    launcher = lifecycle.launcher
    hold_s = launcher.retained_lock_hold_s()
    execution_ms = lifecycle.data_doc_1["limits"]["execution_ms"]
    statement_timeout_ms = launcher._application_role_statement_timeout_ms()  # noqa: SLF001
    bound_s = min(execution_ms, statement_timeout_ms) / 1000.0
    assert hold_s < bound_s, f"retained_lock_hold_s()={hold_s} is not strictly below the safe bound {bound_s}"


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


def test_c26_missing_declaration_fails_fast_multi_worker(launcher_class: type) -> None:
    """Completion condition 13 (design D-1, 裁定 26): the `workers >= 2`
    startup FORM (preflight -> supervisor) also fails fast on a missing
    `process_ceilings` declaration -- the preflight one-shot itself fails,
    and the supervisor never even starts (structurally: `attempt_start_
    without_process_ceilings_multi_worker` never calls `start_uvicorn_
    subprocess` at all on this path -- there is no `Popen`/pid to assert
    "never started" against; the absence of that call IS the proof).
    Self-contained, mirrors `test_c26_missing_declaration_fails_fast`
    above."""
    launcher = launcher_class()
    result = launcher.attempt_start_without_process_ceilings_multi_worker(workers=2)
    assert result.returncode != 0, (
        f"a workers=2 composition root with no process_ceilings declaration started "
        f"successfully (returncode 0) instead of failing fast: stdout={result.stdout!r}"
    )
    assert "F-15" in result.stderr, (
        f"expected an F-15 (contract 1.8.0's own process_ceilings fail-fast) message on stderr; "
        f"got returncode={result.returncode} stderr does not mention F-15: {result.stderr!r}"
    )


def test_c26_control_preflight_fails_fast_on_missing_declaration(launcher_class: type) -> None:
    """The control plane's own preflight one-shot, run with no
    `process_ceilings` row declared, fails fast (F-15) the same way the
    data plane's own preflight already does. `RealServer*.attempt_control_
    preflight_without_process_ceilings`'s own docstring states the
    current per-peer split this observes directly: r2db's own control
    plane builds `app` lazily (a module `__getattr__`, never triggered by
    a bare import), so this call is currently a no-op that always exits 0
    -- expected red on r2db until `control_main.py` gains a dedicated
    `--preflight` entry that actually builds `app`. MitateDB's own control
    plane builds `app` eagerly at import time already, so this call is
    expected green there today."""
    launcher = launcher_class()
    result = launcher.attempt_control_preflight_without_process_ceilings()
    assert result.returncode != 0, (
        f"a control plane with no process_ceilings declaration exited 0 (preflight did not check anything) "
        f"instead of failing fast: stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "F-15" in result.stderr, (
        f"expected an F-15 message on stderr; got returncode={result.returncode} stderr does not mention "
        f"F-15: {result.stderr!r}"
    )


# ---------------------------------------------------------------------------
# Phase 10 WP-4g (supervisor ruling 2026-09-09): F-16 (role CONNECTION
# LIMIT below its own real pool-composition floor) also fails fast at
# composition-root startup -- added to this same module (rather than a
# separate one) because it drives the identical real-process launcher
# shape completion condition 5 above already established, just with a
# different `attempt_start_*` helper.
# ---------------------------------------------------------------------------


def test_c26_role_connection_limit_below_pool_floor_fails_fast(launcher_class: type) -> None:
    """A composition root started while its own served application's
    runtime role has a PostgreSQL `CONNECTION LIMIT` set below `check_
    role_connection_limits`'s own declared-concurrency floor fails fast
    (F-16) -- stderr names it, never a silent start under a role limit a
    real burst of concurrent requests could exceed. Restoring that same
    role's limit (`CONNECTION LIMIT -1`, unlimited) and starting the
    IDENTICAL composition root again succeeds -- proving the fail-fast
    above was genuinely conditioned on the lowered limit, not some
    unrelated breakage of this throwaway platform. Self-contained: this
    test builds its own separate throwaway platform (`attempt_start_
    with_lowered_role_limit`'s own docstring), independent of `lifecycle`
    above, and tears it down again before returning either way."""
    launcher = launcher_class()
    observation = launcher.attempt_start_with_lowered_role_limit()
    assert observation.lowered.returncode != 0, (
        f"a composition root started with its own served application's runtime role CONNECTION LIMIT "
        f"below the real pool-composition floor started successfully (returncode 0) instead of failing "
        f"fast: stdout={observation.lowered.stdout!r}"
    )
    assert "F-16" in observation.lowered.stderr, (
        f"expected an F-16 (role CONNECTION LIMIT below its own real pool-composition floor) message on "
        f"stderr; got returncode={observation.lowered.returncode} stderr does not mention F-16: "
        f"{observation.lowered.stderr!r}"
    )
    assert observation.restored_started, (
        "the identical composition root did not start after the lowered role's CONNECTION LIMIT was "
        "restored to -1 (unlimited) -- the F-16 fail-fast above may not be genuinely conditioned on the "
        "lowered limit"
    )


# ---------------------------------------------------------------------------
# Completion condition 6 (design D-1 (B) 6)
# ---------------------------------------------------------------------------


def test_c26_no_residue_after_shutdown(launcher_class: type) -> None:
    """After `stop()`, neither uvicorn subprocess nor nginx is still
    alive, no port either of them held still has a listener, and (review
    finding N3, started at ceiling=2/workers=2 specifically for this) NOT
    ANY of the data plane's own worker CHILDREN survive either -- the
    data plane's own process GROUP (`_pids_with_pgid`, `socket_harness`)
    has 0 live members, never just its recorded leader pid. Self-
    contained -- its own launcher instance, started and stopped entirely
    within this one test, never shared with `lifecycle` above (whose own
    teardown happens at MODULE end, too late for this test to observe
    independently).

    F4 differential review (2026-09-09): design D-1 (B) 6 / §9 completion
    gate 2 promise "no process and no bound port behind", but residue is
    not only a process or a port -- the throwaway platform DATABASE/ROLE
    and the two temp directories (`_script_dir`, `_nginx_prefix_dir`)
    `stop()` is supposed to remove are just as much "residue" and were
    previously left to manual gate inspection only. This now observes
    both directly."""
    import socket_harness as sh

    launcher = launcher_class()
    launcher.start(ceilings={"data": 2, "control": 2}, workers=2)

    data_pid = launcher._data_handle.process.pid  # noqa: SLF001 -- residue observation only
    control_pid = launcher._control_handle.process.pid  # noqa: SLF001
    nginx_pid = launcher._nginx.process.pid  # noqa: SLF001
    ports = [launcher._data_handle.port, launcher._control_handle.port, launcher._listen_port]  # noqa: SLF001
    # `data_pid` IS the data plane's own pgid (`start_new_session=True`,
    # `socket_harness.start_uvicorn_subprocess`'s own docstring) -- checked
    # non-vacuously BEFORE `stop()` (>= 2 members: the supervisor plus at
    # least one real worker) so the post-stop 0-members assertion below is
    # not vacuously true of a group that was never actually populated.
    data_group_before = sh._pids_with_pgid(data_pid)  # noqa: SLF001
    assert len(data_group_before) >= 2, (
        f"data plane pgid {data_pid} had only {data_group_before!r} member(s) before stop() "
        f"(空振り -- expected >= 2 at workers=2: the supervisor plus >= 1 worker)"
    )
    # R-44 WP-3 (e): local references to the two OWNED `ReservedPort`
    # objects, kept alive independently of `launcher._data_reservation`/
    # `_control_reservation` (which `stop()` sets to `None`) -- `ReservedPort`
    # itself defines no `__del__`; it is the `socket.socket` object it wraps
    # (`.sock`) that has its OWN finalizer, and CPython's refcounting would
    # drop the last reference to that socket (and therefore run that
    # finalizer, closing the underlying fd) the INSTANT the launcher's own
    # attribute is nulled, even if `stop()` itself never called `.close()`
    # explicitly; holding a SEPARATE reference here is what lets `.sock.
    # fileno()` below observe `stop()`'s own explicit close (or its
    # absence) rather than an accidental GC side effect that would
    # otherwise mask that same absence.
    data_reservation = launcher._data_reservation  # noqa: SLF001
    control_reservation = launcher._control_reservation  # noqa: SLF001
    prefix = launcher._prefix  # noqa: SLF001
    script_dir = launcher._script_dir  # noqa: SLF001
    nginx_prefix_dir = launcher._nginx_prefix_dir  # noqa: SLF001
    module = sys.modules[launcher_class.__module__]
    admin_dsn = module._admin_dsn()  # noqa: SLF001 -- R-44 WP-3: no shared-cluster default left to fall back to

    launcher.stop()

    for pid, label in ((data_pid, "data uvicorn"), (control_pid, "control uvicorn"), (nginx_pid, "nginx")):
        alive = _pid_alive(pid)
        assert not alive, f"{label} (pid {pid}) is still alive after stop()"

    data_group_after = sh._pids_with_pgid(data_pid)  # noqa: SLF001
    assert data_group_after == [], (
        f"data plane pgid {data_pid} still has member(s) after stop() (nor any of its own workers): "
        f"{data_group_after!r}"
    )

    for port in ports:
        assert not sh._port_has_listener(port), f"port {port} still has a listener after stop()"  # noqa: SLF001

    for reservation, label in ((data_reservation, "data"), (control_reservation, "control")):
        assert reservation is not None, f"{label} reservation was never captured"
        assert reservation.sock.fileno() == -1, (
            f"{label} reservation's own socket is still open (fd {reservation.sock.fileno()}) after stop()"
        )

    # F4: the throwaway platform DB/role and both temp dirs are gone too.
    assert prefix is not None
    assert script_dir is not None and not script_dir.exists(), f"{script_dir} still exists after stop()"
    assert nginx_prefix_dir is not None and not nginx_prefix_dir.exists(), (
        f"{nginx_prefix_dir} still exists after stop()"
    )
    admin = psycopg.connect(admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute("SELECT count(*) FROM pg_database WHERE datname LIKE %s", [f"{prefix}%"])
            assert cur.fetchone()[0] == 0, f"a database under prefix {prefix!r} still exists after stop()"
            cur.execute("SELECT count(*) FROM pg_roles WHERE rolname LIKE %s", [f"{prefix}%"])
            assert cur.fetchone()[0] == 0, f"a role under prefix {prefix!r} still exists after stop()"
    finally:
        admin.close()


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


# ---------------------------------------------------------------------------
# F3 differential review (2026-09-09): a `start()` that fails partway
# through leaves no residue behind either (design §9 completion gate 2)
# ---------------------------------------------------------------------------


def test_c26_start_failure_leaves_no_residue(launcher_class: type, monkeypatch: pytest.MonkeyPatch) -> None:
    """Before this fix, `start()`'s own `try/except -> self.stop()` wrapped
    only its nginx/readiness tail -- `_ensure_provisioned()` (which can
    itself leave a throwaway platform DB/role behind), the port
    reservation, and both `start_uvicorn_subprocess` calls all ran OUTSIDE
    that `try`, so a failure at any of those earlier points left the
    throwaway platform database/role, an ALREADY-STARTED uvicorn
    subprocess, or the reserved-but-never-bound port socket behind. This
    test injects a real fault purely in this TEST (never in the launcher's
    own implementation): the FIRST `start_uvicorn_subprocess` call (data)
    is allowed to actually run (spawning a real subprocess), the SECOND
    (control) is made to raise -- exactly the "already-started data
    uvicorn" scenario design §9 completion gate 2 names -- and asserts
    that after the resulting `start()` failure, nothing survives: no
    throwaway platform DB/role, no already-started uvicorn subprocess,
    and no still-open reserved port. Self-contained -- its own launcher
    instance, never shared with `lifecycle`."""
    import socket_harness as sh

    module = sys.modules[launcher_class.__module__]
    original_reserve_port = sh.reserve_port
    original_start_uvicorn_subprocess = sh.start_uvicorn_subprocess
    original_claim_prefix_lock = module._claim_prefix_lock
    captured: dict[str, Any] = {"uvicorn_calls": 0, "reservation_ports": []}

    def _capturing_reserve_port():
        # R-44 WP-3 (e), R-5: `start()` now reserves THREE ports before
        # nginx ever starts -- its own listen port (first), then the
        # data/control upstream reservations `start_uvicorn_subprocess(
        # reserved=...)` consumes (second/third) -- and the injected
        # failure below happens on the SECOND `start_uvicorn_subprocess`
        # call (control), i.e. AFTER all three `reserve_port()` calls have
        # already happened. Recording every call in a LIST (never
        # overwriting a single slot) is what lets this test still observe
        # the EARLIER reservations once the count grows past 1 -- a bare
        # single-slot capture would silently stop observing them the
        # instant a second/third call occurred.
        reservation = original_reserve_port()
        captured["reservation_ports"].append(reservation.port)
        return reservation

    def _flaky_start_uvicorn_subprocess(*args, **kwargs):
        captured["uvicorn_calls"] += 1
        if captured["uvicorn_calls"] == 1:
            handle = original_start_uvicorn_subprocess(*args, **kwargs)
            captured["data_handle"] = handle
            return handle
        raise sh.HarnessStartupError("injected failure for F3 residue test (second uvicorn start)")

    def _capturing_claim_prefix_lock(prefix: str):
        # Captures THIS test's own minted prefix (F3, WP-6c review
        # 2026-09-09 follow-up): `lifecycle` above is a MODULE-scoped
        # fixture indirectly parametrized by the SESSION-scoped `launcher_
        # class`, so pytest keeps it alive (never torn down) until every
        # OTHER item sharing that same `launcher_class` value -- including
        # this one -- has run; its own still-alive platform therefore
        # matches `module._PREFIX_TAG` too. Checking residue against that
        # bare tag would wrongly fail on `lifecycle`'s own, still-
        # legitimately-running platform -- exactly the class of mistake F2
        # fixed in the launcher itself. Scoping the check to THIS test's
        # own prefix (captured here, at the moment `_ensure_provisioned`
        # mints and locks it) avoids that false positive.
        captured["prefix"] = prefix
        return original_claim_prefix_lock(prefix)

    monkeypatch.setattr(module.sh, "reserve_port", _capturing_reserve_port)
    monkeypatch.setattr(module.sh, "start_uvicorn_subprocess", _flaky_start_uvicorn_subprocess)
    monkeypatch.setattr(module, "_claim_prefix_lock", _capturing_claim_prefix_lock)

    launcher = launcher_class()
    with pytest.raises(sh.HarnessStartupError):
        launcher.start(ceilings={"data": 1, "control": 1})

    # the launcher's own state is fully unwound.
    assert launcher._platform is None  # noqa: SLF001
    assert launcher._prefix is None  # noqa: SLF001
    assert launcher._script_dir is None  # noqa: SLF001
    assert launcher._nginx_prefix_dir is None  # noqa: SLF001
    assert launcher._data_handle is None  # noqa: SLF001
    assert launcher._control_handle is None  # noqa: SLF001
    assert launcher._data_reservation is None  # noqa: SLF001 -- R-44 WP-3 (e)
    assert launcher._control_reservation is None  # noqa: SLF001

    # the ALREADY-STARTED data uvicorn subprocess (started before the
    # SECOND uvicorn start injected its own failure) was actually killed,
    # not merely dereferenced.
    data_pid = captured["data_handle"].process.pid
    assert not _pid_alive(data_pid), f"data uvicorn (pid {data_pid}) is still alive after a failed start()"

    # R-44 WP-3 (e), R-5: every one of the 3 `reserve_port()` calls
    # `start()` made before the injected failure (nginx's own listen port,
    # then the data/control upstream reservations) was genuinely released
    # -- named individually rather than folded into one generic loop, so
    # nginx's own listen port (the FIRST reservation `start()` ever makes,
    # design's own fixed ordering) is checked by name, not merely as "one
    # of the ports".
    assert len(captured["reservation_ports"]) == 3, (
        f"expected exactly 3 reserve_port() calls (nginx listen + data + control) before the "
        f"injected failure, got {captured['reservation_ports']!r}"
    )
    nginx_listen_reservation_port, data_reservation_port, control_reservation_port = captured["reservation_ports"]
    assert not sh._port_has_listener(nginx_listen_reservation_port), (  # noqa: SLF001
        f"nginx's own listen port {nginx_listen_reservation_port} (reserved but never bound by nginx, "
        f"since the injected failure happens before nginx ever starts) still has a listener after a "
        f"failed start()"
    )
    for port in (data_reservation_port, control_reservation_port):
        assert not sh._port_has_listener(port), (  # noqa: SLF001
            f"upstream reservation port {port} still has a listener after a failed start()"
        )

    # No throwaway platform database/role under THIS test's own prefix
    # survives either -- never the whole `_PREFIX_TAG` tag (see
    # `_capturing_claim_prefix_lock`'s own docstring for why that would be
    # wrong while `lifecycle`'s own platform is still alive). A brief poll
    # (rather than one instantaneous check) extends `_sweep_prefix`'s own
    # in-process retry loop the same tolerance for a backend connection
    # Postgres has not yet noticed is closed.
    prefix = captured["prefix"]
    admin_dsn = module._admin_dsn()  # noqa: SLF001 -- R-44 WP-3: no shared-cluster default left to fall back to
    deadline = time.monotonic() + 20.0
    remaining_databases = remaining_roles = None
    while time.monotonic() < deadline:
        admin = psycopg.connect(admin_dsn, autocommit=True)
        try:
            with admin.cursor() as cur:
                cur.execute("SELECT count(*) FROM pg_database WHERE datname LIKE %s", [f"{prefix}%"])
                remaining_databases = cur.fetchone()[0]
                cur.execute("SELECT count(*) FROM pg_roles WHERE rolname LIKE %s", [f"{prefix}%"])
                remaining_roles = cur.fetchone()[0]
        finally:
            admin.close()
        if remaining_databases == 0 and remaining_roles == 0:
            break
        time.sleep(1.0)
    assert remaining_databases == 0, f"a failed start() left a throwaway platform database under {prefix!r} behind"
    assert remaining_roles == 0, f"a failed start() left a throwaway platform role under {prefix!r} behind"


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
