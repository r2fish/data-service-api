"""Self-tests for `conformance-tests/socket_harness.py` (WP-3, design
`docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md` D-2/D-3) and the two
port-level completion conditions that land in this file rather than in
`socket_harness.py` itself: `ConformanceAdapter.transport_kind` having no
default (adapter.py, design D-1 (A) 4), and the hook-extraction non-
vacuity check on `isolated_application_surface()` (design D-1 (A) 6).

None of this module has contract-level meaning -- it tests the process/
port/reverse-proxy plumbing itself, never a condition ID (no
`pytestmark = pytest.mark.condition(...)` here, unlike every `test_cNN_*`
module in this directory).

Every real ASGI app used below is a tiny, self-contained, dependency-free
callable (no Starlette/FastAPI) so these tests exercise exactly the
harness, not a peer's own product code.
"""
from __future__ import annotations

import asyncio
import atexit
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
from pathlib import Path

import pytest

import socket_harness as sh
from adapter import ConformanceAdapter, fresh_identifier
from conftest import registered_adapters
from test_c05_limit_declaration_agreement import _provision_pair


# ---------------------------------------------------------------------------
# shared test fixtures: tiny ASGI apps
# ---------------------------------------------------------------------------


def _json_app(*, capabilities_status: int = 401, body_bound: "int | None" = None, always_500: bool = False, hang: bool = False):
    """A minimal ASGI 3 callable serving the three routes these tests
    need: `GET /v1/capabilities` and `GET /control/v1/capabilities`
    (readiness's own target, design D-1 (A) 5) and `POST .../echo` (the
    large-body / proxy-shadow tests). `capabilities_status` mimics a real
    deployment's real "no Authorization -> 401" answer; `always_500`
    mimics a broken app (import/construction failure surfaced as every
    request 500ing); `hang` never answers at all; `body_bound` makes the
    echo route answer a STRUCTURED 413 (mirroring
    `errors.details_vocabulary`'s `limit_class` shape) for a body larger
    than the bound, `200` otherwise -- the same "app decides, not nginx"
    shape design D-3 exists to preserve.
    """

    async def app(scope, receive, send):
        if scope["type"] != "http":
            return
        if hang:
            await asyncio.sleep(3600)
        if always_500:
            body = json.dumps({"error": "boom"}).encode()
            await send({"type": "http.response.start", "status": 500, "headers": [(b"content-type", b"application/json")]})
            await send({"type": "http.response.body", "body": body})
            return

        path = scope["path"]
        method = scope["method"]

        if method == "GET" and path in ("/v1/capabilities", "/control/v1/capabilities"):
            body = json.dumps({"contract_version": "0.0.0-harness-selftest"}).encode()
            await send({
                "type": "http.response.start", "status": capabilities_status,
                "headers": [(b"content-type", b"application/json")],
            })
            await send({"type": "http.response.body", "body": body})
            return

        if method == "POST" and path.endswith("/echo"):
            data = bytearray()
            more_body = True
            while more_body:
                message = await receive()
                data += message.get("body", b"")
                more_body = message.get("more_body", False)
            if body_bound is not None and len(data) > body_bound:
                payload = json.dumps({"code": "LIMIT_EXCEEDED", "limit_class": "request_bytes"}).encode()
                await send({
                    "type": "http.response.start", "status": 413,
                    "headers": [(b"content-type", b"application/json")],
                })
                await send({"type": "http.response.body", "body": payload})
                return
            payload = json.dumps({"received": len(data)}).encode()
            await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"application/json")]})
            await send({"type": "http.response.body", "body": payload})
            return

        await send({"type": "http.response.start", "status": 404, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    return app


def _post(url: str, body: bytes, *, timeout: float = 15.0):
    import urllib.error
    import urllib.request

    request = urllib.request.Request(url, data=body, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.headers.get("Content-Type", ""), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("Content-Type", ""), exc.read()


def _get(url: str, *, timeout: float = 5.0):
    import urllib.error
    import urllib.request

    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def _child_pids(parent_pid: int, *, timeout_s: float = 3.0) -> "list[int]":
    """Direct child pids of `parent_pid`, polling briefly (`pgrep -P`,
    available on both this repository's macOS dev machines and the Linux
    CI runner) because a just-`Popen`ed nginx master has not necessarily
    forked its own worker yet the instant this is first called."""
    deadline = time.monotonic() + timeout_s
    while True:
        result = subprocess.run(
            ["pgrep", "-P", str(parent_pid)], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        )
        pids = [int(p) for p in result.stdout.split()]
        if pids or time.monotonic() >= deadline:
            return pids
        time.sleep(0.05)


# ---------------------------------------------------------------------------
# completion condition 1: readiness is a real HTTP status check
# ---------------------------------------------------------------------------


def test_readiness_rejects_a_failing_app():
    """Design D-1 (A) 5: readiness answers `ready` only on an HTTP status
    < 500 -- an app that fails to import/construct (simulated here as an
    app that answers every request with a real 500) must never look
    ready, even though nginx itself is up and happily accepting the TCP
    connection on its behalf.

    mutation (`socket_harness.py`): weaken `wait_until_ready` to accept a
    bare successful TCP connect instead of checking the HTTP status --
    this test goes red because the mutated check would report `ready`
    the instant nginx's own listener accepts a connection, never noticing
    the app's own 500.
    """
    broken = _json_app(always_500=True)
    healthy = _json_app()
    surface = sh.RealSocketSurface(
        data_app=broken, control_app=healthy,
        upstream_timeout_s=0.6, surface_budget_s=5.0, graceful_shutdown_s=0.2,
    )
    start = time.monotonic()
    with pytest.raises(sh.HarnessStartupError):
        _ = surface.data_base_url
    elapsed = time.monotonic() - start
    assert elapsed < 4.0, f"must fail within its own upstream budget, not hang (took {elapsed}s)"
    surface.stop()  # tolerates an already-stopped surface (best-effort)


def test_wait_until_ready_times_out_when_nothing_listens():
    """`wait_until_ready` on its own, against a port nothing is bound to:
    must raise `HarnessStartupError` at (approximately) its own
    `timeout_s`, never hang. Fast, isolated coverage of the readiness
    primitive itself, independent of a full surface."""
    port = sh.free_port()
    start = time.monotonic()
    with pytest.raises(sh.HarnessStartupError):
        sh.wait_until_ready(f"http://127.0.0.1:{port}/v1/capabilities", timeout_s=0.5, label="nothing-listening")
    elapsed = time.monotonic() - start
    assert elapsed < 2.0


# ---------------------------------------------------------------------------
# completion condition 2: the surface-level startup budget
# ---------------------------------------------------------------------------


def test_surface_startup_budget_is_enforced():
    """Design D-2 (a): a whole SURFACE (2 uvicorn + 1 nginx) must fail
    within its OWN budget even when each individual upstream's own
    readiness timeout is much larger -- the surface budget is a separate,
    independently-enforced ceiling, not merely a re-statement of "2 *
    upstream timeout".

    mutation (`socket_harness.py`): make the per-upstream budget in
    `_start` unbounded by `surface_budget_s` (e.g. always pass
    `self.upstream_timeout_s` unshrunk) -- this test goes red because it
    sets `upstream_timeout_s` far larger than `surface_budget_s` and
    asserts the surface fails close to the SMALL budget, not the large
    one.
    """
    hang = _json_app(hang=True)
    surface = sh.RealSocketSurface(
        data_app=hang, control_app=hang,
        upstream_timeout_s=5.0, surface_budget_s=0.3, graceful_shutdown_s=0.2,
    )
    start = time.monotonic()
    with pytest.raises(sh.HarnessStartupError):
        _ = surface.data_base_url
    elapsed = time.monotonic() - start
    assert elapsed < 3.0, (
        f"took {elapsed}s -- the surface_budget_s=0.3 ceiling must dominate the much larger "
        "upstream_timeout_s=5.0, not the other way around"
    )


# ---------------------------------------------------------------------------
# completion conditions 3 / 4: nginx conf -- temp paths + client_max_body_size
# ---------------------------------------------------------------------------


def test_large_body_reaches_the_app_through_the_proxy(tmp_path):
    """Design D-2 (b) / D-3: the rendered conf names prefix-scoped
    `pid`/`error_log`/`client_body_temp_path`/`proxy_temp_path` (never
    nginx's own compiled-in, potentially root-owned defaults), and a body
    far larger than 1 MiB reaches the app unchanged (`client_max_body_size
    0`).

    mutation (`socket_harness.py`): drop the `client_body_temp_path`/
    `proxy_temp_path`/`pid`/`error_log` lines from `render_nginx_conf`'s
    own template -- this test goes red on the structural assertions below
    (the directives are simply absent from the rendered text). This is a
    deliberately PORTABLE mutation trigger (a string check on the
    rendered conf), not a live permission failure: whether OMITTING these
    directives actually breaks a live request depends on whether this
    host's own compiled-in nginx defaults happen to be root-owned (true on
    a CI runner's apt-installed nginx, per design D-2's own note; NOT
    true on this repository's Homebrew-installed dev-machine nginx, whose
    compiled defaults are already owned by the invoking user) --
    `OPERATING_CONDITIONS.md` section 2 item 8 documents this exact dev/
    CI nginx asymmetry.
    """
    app = _json_app(body_bound=None)
    surface = sh.RealSocketSurface(data_app=app, control_app=app, work_dir=tmp_path / "surface")
    base_url = surface.data_base_url  # forces start

    conf_text = (surface._prefix / "nginx.conf").read_text()
    prefix_str = str(surface._prefix)
    for directive, expected_fragment in (
        ("pid", f"pid {prefix_str}/nginx.pid;"),
        ("error_log", f"error_log {prefix_str}/error.log;"),
        ("access_log off", "access_log off;"),
        ("client_body_temp_path", f"client_body_temp_path {prefix_str}/client_body_temp;"),
        ("proxy_temp_path", f"proxy_temp_path {prefix_str}/proxy_temp;"),
    ):
        assert expected_fragment in conf_text, f"{directive}: {expected_fragment!r} missing from rendered conf"

    big_body = os.urandom(2 * 1024 * 1024)  # 2 MiB, comfortably over the 1 MiB app-level convention
    status, content_type, payload = _post(base_url + "/echo", big_body)
    assert status == 200, f"large body must reach the app, got status {status}: {payload!r}"
    assert json.loads(payload)["received"] == len(big_body)

    surface.stop()


def test_proxy_does_not_shadow_the_app_bound(tmp_path):
    """Design D-3: `client_max_body_size 0` means the APP's own bound is
    always what decides a body-size denial -- never nginx's bare (HTML,
    unstructured) 413. This test drives a body larger than the app's own
    declared bound but smaller than nginx's ordinary compiled-in default
    (1m), asserting the STRUCTURED denial (JSON, `limit_class`) reaches
    the client.

    mutation (`socket_harness.py`): set `client_max_body_size` in
    `render_nginx_conf`'s default to something SMALLER than the app's own
    bound used here (8_000 bytes) -- this test goes red because nginx
    itself would then answer its own bare 413 (a non-JSON body) before
    the request ever reaches the app.
    """
    app_bound = 4096
    app = _json_app(body_bound=app_bound)
    surface = sh.RealSocketSurface(data_app=app, control_app=app, work_dir=tmp_path / "surface")
    base_url = surface.data_base_url

    body = os.urandom(8_000)  # > app_bound, comfortably < nginx's ordinary 1m default
    status, content_type, payload = _post(base_url + "/echo", body)
    assert status == 413, f"expected the app's own structured 413, got {status}: {payload!r}"
    assert "json" in content_type.lower(), f"expected a JSON body (the app deciding), got Content-Type {content_type!r}"
    decoded = json.loads(payload)
    assert decoded.get("limit_class") == "request_bytes", decoded

    surface.stop()


# ---------------------------------------------------------------------------
# completion condition 5: `nginx -t` before start
# ---------------------------------------------------------------------------


def test_invalid_conf_fails_before_start(tmp_path):
    """Design D-2 (b): `nginx -t` runs BEFORE nginx is ever started with
    `-g 'daemon off;'` -- an invalid conf fails loudly, and never leaves
    an nginx process behind to clean up.

    mutation (`socket_harness.py`): make `check_nginx_config` an early
    `return` (never actually invoking `nginx -t`) -- this test goes red
    (`DID NOT RAISE HarnessStartupError`) because nothing would then
    detect the invalid conf at all before this test's own `pytest.raises`
    assertion.
    """
    prefix = tmp_path / "conf_check"
    prefix.mkdir()
    (prefix / "client_body_temp").mkdir()
    (prefix / "proxy_temp").mkdir()
    conf_path = prefix / "nginx.conf"
    conf_path.write_text("this is not a valid nginx conf {{{\n")

    nginx_bin = sh.find_nginx_binary()
    with pytest.raises(sh.HarnessStartupError, match="nginx -t"):
        sh.check_nginx_config(nginx_bin, conf_path, prefix)

    # No pidfile must exist -- `check_nginx_config` never starts a process.
    assert not (prefix / "nginx.pid").exists()


def test_missing_nginx_binary_fails_hard(monkeypatch):
    """Design D-3 / `OPERATING_CONDITIONS.md` section 1.3 item 26: nginx
    absent is a hard failure, never a skip.

    mutation: none listed for this test in the work order's own table (it
    realizes design D-3's own general "no skip" requirement, exercised
    directly here rather than via a completion-condition-numbered
    mutation)."""
    monkeypatch.delenv("NGINX_BIN", raising=False)
    monkeypatch.setenv("PATH", "")
    with pytest.raises(sh.HarnessStartupError):
        sh.find_nginx_binary()


# ---------------------------------------------------------------------------
# completion condition 6: no process/port residue (normal stop / atexit /
# startup sweep)
# ---------------------------------------------------------------------------


def test_no_process_or_port_residue(tmp_path):
    """Design D-2 (d): `.stop()` unconditionally kills the nginx process
    and stops both uvicorn threads; the listen port is released.

    mutation (`socket_harness.py`): remove the kill call(s) inside
    `RealSocketSurface._stop_best_effort` (e.g. skip `self._nginx.stop()`
    or the two uvicorn-handle `.stop()` calls) -- this test goes red
    because the nginx process would still be running (`poll() is None`)
    and/or the listen port would still accept connections after
    `.stop()` returns.
    """
    app = _json_app()
    surface = sh.RealSocketSurface(data_app=app, control_app=app, work_dir=tmp_path / "surface")
    _ = surface.data_base_url  # forces start
    listen_port = int(surface.base_url.rsplit(":", 1)[1])
    nginx_process = surface._nginx.process
    data_thread = surface._data_handle.thread
    control_thread = surface._control_handle.thread

    surface.stop()

    assert nginx_process.poll() is not None, "nginx process must have exited after stop()"
    assert not data_thread.is_alive(), "data uvicorn thread must have stopped after stop()"
    assert not control_thread.is_alive(), "control uvicorn thread must have stopped after stop()"
    with pytest.raises(OSError):
        with socket.create_connection(("127.0.0.1", listen_port), timeout=1.0):
            pass


def test_stop_removes_the_mkdtemp_base_dir_it_owns():
    """F-6 差し戻し (監督裁定 2026-09-08, item 6): a `RealSocketSurface`
    that mints its OWN `tempfile.mkdtemp(prefix="conf-socket-")` base dir
    (no caller-supplied `work_dir`) must have that directory gone after a
    normal `.stop()`. `_owns_base_dir`/`_base_dir`'s own docstring
    (`socket_harness.py`, on the `RealSocketSurface` dataclass) names
    exactly this property, but every other test in this module passes its
    own `work_dir` (never removed by design, since it is caller-owned) --
    none of them exercises the `_owns_base_dir is True` branch at all.

    mutation (`socket_harness.py`): remove the `shutil.rmtree(self.
    _base_dir, ...)` call from `_stop_best_effort` (or leave `_owns_base_
    dir` always `False`) -- this test goes red because the directory
    would still exist after `.stop()`.
    """
    app = _json_app()
    surface = sh.RealSocketSurface(data_app=app, control_app=app)  # no work_dir -- owns its own mkdtemp base dir
    try:
        _ = surface.data_base_url  # forces start
        base_dir = surface._base_dir
        assert base_dir is not None and base_dir.exists(), "the surface must have minted its own base dir"

        surface.stop()

        assert not base_dir.exists(), "stop() must remove the mkdtemp base dir this instance created for itself"
    finally:
        if surface._base_dir is not None and surface._base_dir.exists():
            shutil.rmtree(surface._base_dir, ignore_errors=True)


def test_stop_preserves_the_port_ledger_when_a_sigkilled_nginx_master_leaves_a_surviving_worker():
    """N-1 差し戻し (監督裁定 2026-09-08): a `SIGKILL` sent DIRECTLY to the
    nginx MASTER pid (never a path `.stop()`/`_terminate_then_kill` itself
    takes -- this stands in for an external actor, e.g. an OOM killer or a
    bare `kill -9`, doing exactly this to the real master process) gives
    the master no chance to signal its own children: the worker (a
    SEPARATE pid, reparented, invisible to a marker-scoped `pgrep` because
    nginx rewrites a worker's own argv to the fixed string `nginx: worker
    process`) survives and keeps listening on the surface's own recorded
    port -- measured directly (`{scratchpad}/phase10/wp3-review-2.md`'s
    own orphan-worker measurement).

    `.stop()` must neither (a) return as though nothing were wrong, nor
    (b) remove the `ports.json` ledger / base dir the CI residue check
    (F-3) relies on to catch exactly this shape -- doing either would make
    this residue invisible in precisely the run (a killed master) where
    the check matters most.

    mutation (`socket_harness.py`): make `_stop_best_effort` remove the
    ledger/base dir unconditionally (never checking `_port_has_listener`
    against `self._ports`) -- this test goes red because the ledger would
    be gone and/or `.stop()` would return normally despite the orphaned
    worker still listening.
    """
    app = _json_app()
    surface = sh.RealSocketSurface(data_app=app, control_app=app)  # owns its own mkdtemp base dir
    worker_pids: "list[int]" = []
    try:
        _ = surface.data_base_url  # forces start
        base_dir = surface._base_dir
        ports_file = surface._prefix / "ports.json"
        assert ports_file.exists()
        listen_port = int(surface.base_url.rsplit(":", 1)[1])

        master_pid = surface._nginx.process.pid
        worker_pids = _child_pids(master_pid)
        assert worker_pids, "the rendered conf's `worker_processes 1` must have produced a real worker child"

        os.kill(master_pid, signal.SIGKILL)
        surface._nginx.process.wait(timeout=5.0)  # reap our own direct child so .poll() reflects the kill

        # Sanity: the worker really is still alive and still holds the
        # listen port -- exactly the real-world shape this test exists to
        # exercise, not merely assumed.
        with socket.create_connection(("127.0.0.1", listen_port), timeout=2.0):
            pass

        with pytest.raises(RuntimeError, match="still have a listener"):
            surface.stop()

        assert base_dir.exists(), "the ledger's base dir must survive while a recorded port still has a listener"
        assert ports_file.exists(), "ports.json must not be removed while a recorded port still has a listener"
    finally:
        for pid in worker_pids:
            with sh._suppress(ProcessLookupError):
                os.kill(pid, signal.SIGKILL)
        for pid in worker_pids:
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.05)
        surface._data_handle = None  # already gone via the failed .stop() above; avoid a second stop attempt
        surface._control_handle = None
        surface._nginx = None
        if surface._base_dir is not None and surface._base_dir.exists():
            shutil.rmtree(surface._base_dir, ignore_errors=True)


def test_atexit_registers_a_cleanup_callback_on_start(tmp_path):
    """Design D-2 (e): starting a surface registers exactly one `atexit`
    callback -- the abnormal-exit path is wired to the SAME
    `_stop_best_effort` method the normal `.stop()` path calls (code
    inspection: `RealSocketSurface._start` has exactly one
    `atexit.register` call site, `self._stop_best_effort`), never a
    second, independently-written cleanup routine that could drift from
    it -- so `test_no_process_or_port_residue`'s own coverage of the kill
    logic applies to the abnormal-exit path too. (`atexit.unregister`'s
    own removal-by-equality is not exercised here -- measured directly on
    this interpreter to not actually shrink `_ncallbacks()`, a platform
    quirk unrelated to this harness; counting registrations is sufficient
    to detect the mutation this condition cares about.)"""
    app = _json_app()
    surface = sh.RealSocketSurface(data_app=app, control_app=app, work_dir=tmp_path / "surface")
    before = atexit._ncallbacks()  # noqa: SLF001 - the only introspection primitive `atexit` exposes
    _ = surface.data_base_url
    after_start = atexit._ncallbacks()  # noqa: SLF001
    assert after_start == before + 1, "starting a surface must register exactly one atexit callback"
    surface.stop()


def test_atexit_registered_callback_actually_cleans_up_when_invoked(tmp_path, monkeypatch):
    """F-5 差し戻し (監督裁定 2026-09-08): the test immediately above only
    counts registrations -- it never actually calls the function `atexit.
    register` was given and checks that calling it cleans anything up. A
    mutation that registers some OTHER, no-op callable (still exactly ONE
    registration, so the count-only test above stays green) would leave a
    real abnormal-exit leaving nginx/uvicorn running forever. This test
    captures the EXACT callable `atexit.register` is called with and
    invokes it directly (never `surface.stop()`), then asserts the same
    residue-gone properties `test_no_process_or_port_residue` checks.

    mutation (`socket_harness.py`): change the `atexit.register(self.
    _stop_best_effort)` call site in `_start` to register a no-op (e.g.
    `atexit.register(lambda: None)`) instead -- this test goes red because
    invoking the captured callback then leaves the nginx process and both
    uvicorn threads running.
    """
    registered: list = []
    original_register = atexit.register

    def spy_register(func, *args, **kwargs):
        registered.append(func)
        return original_register(func, *args, **kwargs)

    monkeypatch.setattr(atexit, "register", spy_register)
    app = _json_app()
    surface = sh.RealSocketSurface(data_app=app, control_app=app, work_dir=tmp_path / "surface")
    _ = surface.data_base_url  # forces start, registers the real atexit callback
    assert registered, "starting a surface must register an atexit callback"

    listen_port = int(surface.base_url.rsplit(":", 1)[1])
    nginx_process = surface._nginx.process
    data_thread = surface._data_handle.thread
    control_thread = surface._control_handle.thread

    registered[-1]()  # the SAME callable atexit would invoke on abnormal exit -- never surface.stop()

    assert nginx_process.poll() is not None, "the registered atexit callback must have stopped nginx"
    assert not data_thread.is_alive(), "the registered atexit callback must have stopped the data uvicorn"
    assert not control_thread.is_alive(), "the registered atexit callback must have stopped the control uvicorn"
    with pytest.raises(OSError):
        with socket.create_connection(("127.0.0.1", listen_port), timeout=1.0):
            pass
    surface._started = False  # already stopped via the captured callback above, not surface.stop()


def test_startup_sweep_kills_orphans(tmp_path):
    """Design D-2 (f): a pidfile left under a prefix directory by a
    PREVIOUS run that exited without running any Python cleanup at all
    names a live process that `sweep_orphans` kills on the NEXT run that
    reuses (or inspects) that same prefix.

    mutation (`socket_harness.py`): remove the kill call(s) from
    `sweep_orphans` -- this test goes red because the dummy process would
    still be alive after the sweep.

    F-4 差し戻し (監督裁定 2026-09-08): `sweep_orphans` now also requires
    the pid's own cmdline to carry this harness's marker (owner check,
    see `test_sweep_orphans_never_kills_a_pid_whose_cmdline_lacks_the_
    marker`) -- so the dummy process here is started with `sh.
    NGINX_PREFIX_MARKER` as an explicit extra argv element (harmless to a
    bare `python -c ...sleep...` script, which never inspects `sys.argv`)
    purely so its own real cmdline contains the marker, exactly like a
    genuine orphaned harness process's argv would.
    """
    prefix = tmp_path / "orphan_prefix"
    prefix.mkdir()
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)", sh.NGINX_PREFIX_MARKER])
    # Reap eagerly in the background so this process's own death is
    # observable via `poll()`/`os.kill(pid, 0)` immediately -- without a
    # live reaper, a SIGTERM'd DIRECT CHILD of this test process would
    # linger as a zombie (still "alive" to `kill(pid, 0)`) until reaped,
    # which is a self-test artifact, not a property of a genuine orphan
    # (an orphan is reparented to init/launchd, which reaps it for real).
    reaper = threading.Thread(target=process.wait, daemon=True)
    reaper.start()
    (prefix / "orphan.pid").write_text(str(process.pid))

    killed = sh.sweep_orphans(prefix)

    assert process.pid in killed
    reaper.join(timeout=5.0)
    assert process.poll() is not None, "the orphaned dummy process must be dead after sweep_orphans"
    assert not (prefix / "orphan.pid").exists()


# ---------------------------------------------------------------------------
# completion condition 7: lazy startup
# ---------------------------------------------------------------------------


def test_lazy_start_does_not_launch_on_build(tmp_path, monkeypatch):
    """Design D-2 (g): constructing a `RealSocketSurface` must not itself
    start anything -- only reading `.data_base_url`/`.control_base_url`
    does.

    mutation (`socket_harness.py`): start eagerly in `__post_init__` (or
    equivalent) instead of on first property access -- this test goes red
    because `start_uvicorn_thread` would then have been called before
    this test ever touches `.data_base_url`.
    """
    calls: list[str] = []
    original = sh.start_uvicorn_thread

    def spy(*args, **kwargs):
        calls.append("called")
        return original(*args, **kwargs)

    monkeypatch.setattr(sh, "start_uvicorn_thread", spy)
    app = _json_app()
    surface = sh.RealSocketSurface(data_app=app, control_app=app, work_dir=tmp_path / "surface")

    assert not calls, "constructing a RealSocketSurface must not start any uvicorn"
    assert surface.started is False

    _ = surface.data_base_url

    assert calls, "reading .data_base_url must start the surface"
    assert surface.started is True

    surface.stop()


# ---------------------------------------------------------------------------
# completion condition 8: `transport_kind` is an abstract attribute with
# no default
# ---------------------------------------------------------------------------


def test_every_registered_adapter_declares_transport_kind():
    """adapter.py port v1.14 (design D-1 (A) 4): every currently
    registered adapter declares a `transport_kind` of one of the three
    contract-independent vocabulary words, AND the port (`ConformanceAdapter`
    itself) carries no default for it -- a subclass that forgets to
    declare it must fail loudly (an `AttributeError`), never silently
    inherit some fallback value.

    mutation (`conformance-tests/adapter.py`): give `transport_kind` a
    real default (e.g. `transport_kind: str = "asgi"`) on the ABC itself
    -- this test goes red on the second assertion below, because the
    mutated line becomes a real class attribute (present in
    `vars(ConformanceAdapter)`), not a bare annotation.
    """
    adapters = registered_adapters()
    assert adapters, "no adapters registered -- vacuous"
    valid = {"in_process", "asgi", "socket"}
    for name, adapter_obj in adapters.items():
        value = getattr(adapter_obj, "transport_kind", None)
        assert value in valid, f"{name}: transport_kind={value!r} is not one of {valid}"

    assert "transport_kind" not in vars(ConformanceAdapter), (
        "ConformanceAdapter.transport_kind carries a default value on the ABC itself -- it must "
        "stay a bare annotation (no assignment) so a subclass that forgets to declare it fails "
        "loudly instead of silently inheriting a fallback"
    )


# ---------------------------------------------------------------------------
# completion condition 11: isolated surfaces go through the same hooks
# ---------------------------------------------------------------------------


_ASGI_ADAPTER_NAMES: tuple[str, ...] = tuple(
    name for name, obj in registered_adapters().items() if getattr(obj, "transport_kind", None) == "asgi"
)
assert _ASGI_ADAPTER_NAMES, (
    "no registered adapter declares transport_kind == 'asgi' -- test_isolated_surface_goes_through_"
    "the_hooks would collect zero items, which is silent vacuity by construction"
)


@pytest.mark.parametrize("adapter_name", _ASGI_ADAPTER_NAMES)
def test_isolated_surface_goes_through_the_hooks(adapter_name: str, monkeypatch):
    """Design D-1 (A) 6 point (c): `isolated_application_surface()` must
    build its own client through the SAME `_build_client` hook the shared
    surface's own `__init__` uses -- never a direct `httpx.AsyncClient(...)`
    construction that bypasses it (the socket adapter, WP-4, overrides
    `_build_client` precisely so its own isolated surface gets its own
    dedicated uvicorn+nginx instead of silently sharing the parent's).

    mutation (`conformance_adapter_r2db_http.py` or
    `conformance_adapter_mitatedb_http.py`): revert
    `isolated_application_surface`'s own client construction to a direct,
    hook-bypassing `httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
    base_url=BASE_URL)` -- this test goes red because the spy installed on
    `_build_client` is then never called.
    """
    adapter_obj = registered_adapters()[adapter_name]
    cls = type(adapter_obj)
    calls: list[int] = []
    original = cls._build_client

    def spy(self, app, base_url, _original=original, _calls=calls):
        _calls.append(1)
        return _original(self, app, base_url)

    monkeypatch.setattr(cls, "_build_client", spy)
    with adapter_obj.isolated_application_surface():
        pass
    assert calls, f"{adapter_name}: isolated_application_surface() must call self._build_client()"


@pytest.mark.parametrize("adapter_name", _ASGI_ADAPTER_NAMES)
def test_isolated_surface_surfaces_value_hook_is_load_bearing(adapter_name: str, monkeypatch):
    """F-1 差し戻し (監督裁定 2026-09-08): the spy test immediately above
    only proves `_build_client` is CALLED -- it cannot prove `_surfaces_
    value()` is the thing that actually reaches the wire, because the
    default `_surfaces_value()` body is a fixed module constant: a bypass
    that hands `isolated_application_surface()`'s own `DataService`/
    `HttpService` composition the SAME constant directly, never calling
    `iso._surfaces_value()` at all, is byte-identical in every OBSERVABLE
    response and therefore invisible to any behavioral assertion -- only a
    structural substitution closes it. This test monkeypatches `_surfaces_
    value()` itself to return a SENTINEL `surfaces` object and asserts the
    isolated surface's own real, live `capability_document()` echoes that
    exact sentinel back -- which is only possible if the isolated
    surface's own composition actually called `iso._surfaces_value()`
    (design D-1 (A) 6 point (c)).

    mutation (`conformance_adapter_r2db_http.py::isolated_application_surface` /
    `conformance_adapter_mitatedb_http.py::isolated_application_surface`): revert
    `isolated_application_surface`'s own `surfaces=iso._surfaces_value()`
    (r2db) / `_iso_surfaces = iso._surfaces_value()` (MitateDB) to a
    direct reference to this module's own unchanged `_SURFACES` constant /
    `_DATA_SURFACE_BASE_URL`+`_CONTROL_SURFACE_BASE_URL` literals -- this
    test goes red because the isolated surface's own real capability
    document then reports the UNCHANGED module constant instead of this
    test's own monkeypatched sentinel.
    """
    adapter_obj = registered_adapters()[adapter_name]
    cls = type(adapter_obj)
    sentinel = {
        "data": {"base_url": "http://sentinel-iso.conformance.invalid/v1"},
        "control": {"base_url": "http://sentinel-iso.conformance.invalid/control/v1"},
    }
    monkeypatch.setattr(cls, "_surfaces_value", lambda self: sentinel)
    with adapter_obj.isolated_application_surface() as iso:
        doc = iso.capability_document()
        assert doc.get("surfaces") == sentinel, (
            f"{adapter_name}: isolated_application_surface() must build its surfaces object through "
            f"self._surfaces_value(), not a direct module constant -- got {doc.get('surfaces')!r}"
        )


@pytest.mark.parametrize("adapter_name", _ASGI_ADAPTER_NAMES)
def test_isolated_surface_resets_surface_state_before_composition(adapter_name: str, monkeypatch):
    """F-2 (b) 監督裁定 2026-09-08: `isolated_application_surface()` must
    call `iso._reset_surface_state()` on the fresh `copy.copy(self)`
    instance, immediately after the copy and before that copy's own
    composition begins -- the hook a socket-adapter subclass (WP-4) uses
    to give its OWN copy a dedicated port reservation / server state
    instead of silently sharing whatever `copy.copy`'s shallow semantics
    carried over from the parent surface.

    mutation (`conformance_adapter_r2db_http.py` /
    `conformance_adapter_mitatedb_http.py`): remove the `iso._reset_
    surface_state()` call site immediately after `iso = copy.copy(self)`
    in `isolated_application_surface` -- this test goes red because the
    spy installed on `_reset_surface_state` is then never called.
    """
    adapter_obj = registered_adapters()[adapter_name]
    cls = type(adapter_obj)
    calls: list[int] = []
    original = cls._reset_surface_state

    def spy(self, _original=original, _calls=calls):
        _calls.append(1)
        return _original(self)

    monkeypatch.setattr(cls, "_reset_surface_state", spy)
    with adapter_obj.isolated_application_surface():
        pass
    assert calls, f"{adapter_name}: isolated_application_surface() must call iso._reset_surface_state()"


# ---------------------------------------------------------------------------
# F-10 (監督裁定 2026-09-08): `hold_in_flight`'s own real HTTP requests must
# also be built through the `_build_client` hook, not a direct,
# hook-bypassing `httpx.AsyncClient(ASGITransport(...))` construction --
# otherwise a socket-adapter override of `_build_client` (WP-4) would leave
# `hold_in_flight` alone still dialing in-process, never a real socket.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("adapter_name", _ASGI_ADAPTER_NAMES)
def test_hold_in_flight_goes_through_the_build_client_hook(adapter_name: str, monkeypatch):
    """F-10 差し戻し (監督裁定 2026-09-08): `_hold_in_flight_via_http_
    requests` (r2db) / `_hold_in_flight_via_http_requests_over_stalled_
    gate` (MitateDB) used to build each held request's own client with a
    direct, hook-bypassing `httpx.AsyncClient(transport=httpx.
    ASGITransport(app=app), base_url=BASE_URL)` -- the ONE remaining
    construction site design D-1 (A) 6's own hook extraction (`_build_
    client`) missed. A socket-adapter override (WP-4) of `_build_client`
    would then still leave `hold_in_flight`'s own held requests dialing
    in-process ASGI, the one primitive on the whole isolated surface that
    would silently NOT go through the real socket -- while every other
    call site (`__init__`, `isolated_application_surface`,
    `isolated_control_surface`) correctly would.

    mutation (`conformance_adapter_r2db_http.py` /
    `conformance_adapter_mitatedb_http.py`): revert the `build_client(app,
    BASE_URL)` call inside `_hold_in_flight_via_http_requests`'s (or the
    MitateDB twin's) own `_run()`/`_once()` back to a direct `httpx.
    AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL)`
    -- this test goes red because the spy installed on `self._build_client`
    is then never called while `hold_in_flight`'s own held request runs.
    """
    adapter_obj = registered_adapters()[adapter_name]
    cls = type(adapter_obj)
    calls: list[int] = []
    original = cls._build_client

    def spy(self, app, base_url, _original=original, _calls=calls):
        _calls.append(1)
        return _original(self, app, base_url)

    with adapter_obj.isolated_application_surface() as iso:
        dev, rt, _ = _provision_pair(iso)
        entity = fresh_identifier("f10hook")
        iso.create_entity(dev, entity, {"label": "text"})

        # Only spy from here on -- `isolated_application_surface()`'s own
        # `_build_client` call (already covered by `test_isolated_surface_
        # goes_through_the_hooks` above) must not be counted as evidence
        # for THIS test's own claim about `hold_in_flight` specifically.
        monkeypatch.setattr(cls, "_build_client", spy)
        with iso.hold_in_flight(rt, 1) as held:
            assert held >= 1, f"{adapter_name}: hold_in_flight held zero requests -- nothing was exercised"

    assert calls, f"{adapter_name}: hold_in_flight must build its real HTTP client through self._build_client"


# ---------------------------------------------------------------------------
# subprocess-version uvicorn launcher (design D-2 -- placed and tested by
# this WP; used for real by the C-26 launchers, WP-6c)
# ---------------------------------------------------------------------------


_PROBE_APP_SOURCE = textwrap.dedent(
    """\
    async def app(scope, receive, send):
        if scope["type"] != "http":
            return
        await send({"type": "http.response.start", "status": 401, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})
    """
)


def test_uvicorn_subprocess_starts_becomes_ready_and_stops(tmp_path):
    """The subprocess-version launcher (design D-2 (a), "本WPでは関数を置
    きテストする") starts a REAL, separate OS process, answers readiness
    through a plain (proxy-less) direct dial, and leaves no residue after
    `.stop()`."""
    module_path = tmp_path / "conf_socket_probe_app.py"
    module_path.write_text(_PROBE_APP_SOURCE)

    handle = sh.start_uvicorn_subprocess(
        "conf_socket_probe_app:app",
        pidfile=tmp_path / "probe.pid",
        cwd=tmp_path,
    )
    try:
        sh.wait_until_ready(f"http://127.0.0.1:{handle.port}/anything", timeout_s=10.0, label="probe-subprocess")
        status, body = _get(f"http://127.0.0.1:{handle.port}/anything")
        assert status == 401
    finally:
        handle.stop()

    assert handle.process.poll() is not None, "subprocess uvicorn must have exited after stop()"
    assert not handle.pidfile.exists()


# ---------------------------------------------------------------------------
# R-44 WP-3 (e), W44-3-5/W44-3-10 (監督裁定 2026-09-16): the subprocess-
# version launcher now hands a `reserve_port()` reservation to uvicorn via
# `--fd`/`pass_fds` (never a bare `--port <number>`), and the FORMER `port:
# Optional[int]` parameter is removed outright.
# ---------------------------------------------------------------------------


def test_uvicorn_subprocess_serves_on_the_reserved_socket(tmp_path, monkeypatch):
    """The subprocess launcher's DEFAULT path (`reserved` omitted) hands
    its own `reserve_port()` reservation to uvicorn via `--fd`/`pass_fds`
    -- read directly off a monkeypatched `subprocess.Popen` (never source
    text, `OPERATING_CONDITIONS.md` §1.7 の 52), then confirms uvicorn
    genuinely serves on it.

    mutation (`socket_harness.py`): replace the `"--fd", str(fd)` pair in
    `start_uvicorn_subprocess`'s own argv with `"--port", str(bound_port)`
    -- this test goes red because the captured argv no longer contains
    `--fd` at all.
    """
    module_path = tmp_path / "conf_socket_probe_app_fd.py"
    module_path.write_text(_PROBE_APP_SOURCE)
    real_popen = sh.subprocess.Popen
    captured: dict = {}

    def _capturing_popen(argv, *args, **kwargs):
        captured["argv"] = list(argv)
        captured["pass_fds"] = kwargs.get("pass_fds")
        return real_popen(argv, *args, **kwargs)

    monkeypatch.setattr(sh.subprocess, "Popen", _capturing_popen)
    handle = sh.start_uvicorn_subprocess(
        "conf_socket_probe_app_fd:app", pidfile=tmp_path / "probe_fd.pid", cwd=tmp_path,
    )
    try:
        assert "--fd" in captured["argv"], f"argv carries no --fd: {captured['argv']!r}"
        fd_index = captured["argv"].index("--fd")
        fd_value = int(captured["argv"][fd_index + 1])
        assert captured["pass_fds"] is not None and fd_value in captured["pass_fds"], (
            f"pass_fds {captured['pass_fds']!r} does not include its own --fd value {fd_value}"
        )
        assert "--port" not in captured["argv"], f"argv still carries --port: {captured['argv']!r}"
        sh.wait_until_ready(f"http://127.0.0.1:{handle.port}/anything", timeout_s=10.0, label="probe-fd")
        status, _ = _get(f"http://127.0.0.1:{handle.port}/anything")
        assert status == 401
    finally:
        handle.stop()


def test_start_uvicorn_subprocess_never_closes_a_caller_supplied_reservation(tmp_path):
    """W44-3-10 / W44-3-5: when the CALLER supplies its own `reserved=`,
    ownership stays with the caller -- neither `start_uvicorn_subprocess`
    nor the returned handle's own `.stop()` may close it (a C-26 launcher
    holds this SAME reservation across a `restart()`'s stop-then-start).

    mutation (`socket_harness.py`): flip the ownership condition in
    `start_uvicorn_subprocess` (the `if reserved is not None:` branch) so
    a caller-supplied `reserved` is ALSO treated as owned by the handle --
    this test goes red because `reserved.sock.fileno()` becomes `-1`
    (closed) after `handle.stop()` below.
    """
    module_path = tmp_path / "conf_socket_probe_app_owned.py"
    module_path.write_text(_PROBE_APP_SOURCE)
    reserved = sh.reserve_port()
    handle = sh.start_uvicorn_subprocess(
        "conf_socket_probe_app_owned:app", pidfile=tmp_path / "probe_owned.pid",
        reserved=reserved, cwd=tmp_path,
    )
    try:
        sh.wait_until_ready(f"http://127.0.0.1:{handle.port}/anything", timeout_s=10.0, label="probe-owned")
    finally:
        handle.stop()
    assert reserved.sock.fileno() != -1, (
        "start_uvicorn_subprocess must never close a caller-supplied reservation"
    )
    reserved.close()


def test_uvicorn_subprocess_releases_its_own_reservation_on_stop(tmp_path):
    """W44-3-10: when `reserved` is OMITTED, `start_uvicorn_subprocess`
    mints its own reservation and the returned HANDLE owns it -- `.stop()`
    must close it, never leave it dangling.

    mutation (`socket_harness.py`): drop the `if self._owned_reservation
    is not None: self._owned_reservation.close()` line from `UvicornSub
    processHandle.stop()` -- this test goes red on both assertions below.
    """
    module_path = tmp_path / "conf_socket_probe_app_default.py"
    module_path.write_text(_PROBE_APP_SOURCE)
    handle = sh.start_uvicorn_subprocess(
        "conf_socket_probe_app_default:app", pidfile=tmp_path / "probe_default.pid", cwd=tmp_path,
    )
    port = handle.port
    owned = handle._owned_reservation  # noqa: SLF001 -- residue observation only
    assert owned is not None, "the default path must own a reservation"
    sh.wait_until_ready(f"http://127.0.0.1:{port}/anything", timeout_s=10.0, label="probe-default")
    handle.stop()
    assert owned.sock.fileno() == -1, "start_uvicorn_subprocess's own reservation must be closed on stop()"
    assert not sh._port_has_listener(port), f"port {port} still has a listener after stop()"  # noqa: SLF001


def test_start_uvicorn_subprocess_has_no_port_argument():
    """W44-3-10 (監督裁定 2026-09-16): the former `port: Optional[int]`
    parameter is removed outright -- no caller in this repository was left
    after W44-3-9 moved every real call site onto `reserved=`.

    mutation (`socket_harness.py`): re-add `port: Optional[int] = None,`
    to `start_uvicorn_subprocess`'s own signature -- this test goes red
    because `"port"` then reappears in `inspect.signature(...).parameters`.
    """
    import inspect

    params = inspect.signature(sh.start_uvicorn_subprocess).parameters
    assert "port" not in params, f"start_uvicorn_subprocess still has a 'port' parameter: {params!r}"


def test_start_uvicorn_subprocess_closes_its_own_reservation_when_popen_fails(monkeypatch, tmp_path):
    """コードレビュー1回目差し戻し2(監督裁定2026-09-16): `reserve_port()`で
    採番した直後、`subprocess.Popen`/`pidfile.write_text`のいずれかが送出
    すると、handleが返らないので`owned_reservation`を閉じる先が無く、予約
    したソケットがlistenしたまま漏れていた。`start_uvicorn_subprocess`の
    `try`/`except BaseException:`が、例外経路でも`owned_reservation`(既定
    経路でこの関数自身が採番したもの)を閉じることを直接確認する。

    mutation (`socket_harness.py`): `start_uvicorn_subprocess`の
    `except BaseException:`節の`owned_reservation.close()`を`pass`に置き
    換える -- このテストは、`Popen`失敗後も予約ソケットがまだlistenして
    いる(closeされていない)ことを検出して赤になる。
    """
    real_reserve_port = sh.reserve_port
    captured: dict = {}

    def _capturing_reserve_port():
        reservation = real_reserve_port()
        captured["reservation"] = reservation
        return reservation

    def _raising_popen(*args, **kwargs):
        raise OSError("injected Popen failure for the exception-safety test")

    monkeypatch.setattr(sh, "reserve_port", _capturing_reserve_port)
    monkeypatch.setattr(sh.subprocess, "Popen", _raising_popen)

    with pytest.raises(OSError):
        sh.start_uvicorn_subprocess(
            "conf_socket_probe_app_exc:app", pidfile=tmp_path / "probe_exc.pid", cwd=tmp_path,
        )

    reservation = captured.get("reservation")
    assert reservation is not None, "reserve_port() was never called on the default (owned) path"
    assert reservation.sock.fileno() == -1, (
        "start_uvicorn_subprocess must close its own reservation when Popen raises, "
        f"but fd is {reservation.sock.fileno()} (still open)"
    )


# ---------------------------------------------------------------------------
# design D-1 (監督裁定 19/26/27/33): `--workers`, the process-
# group supervisor start, pgid-recording pidfile, pgid-based `sweep_
# orphans`. Completion conditions 1-3.
# ---------------------------------------------------------------------------


def _pids_in_group(pgid: int) -> "list[int]":
    """Every currently-live pid whose OWN process group is `pgid`, read via
    `ps -e -o pid=,pgid=` -- works unmodified on both this repository's own
    macOS dev machines and Linux CI, unlike `/proc`-based enumeration.
    Observation-only test helper -- never part of `socket_harness.py`'s own
    product surface."""
    result = subprocess.run(
        ["ps", "-e", "-o", "pid=,pgid="], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
    )
    pids: list[int] = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        try:
            pid, group = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        if group == pgid:
            pids.append(pid)
    return pids


def _wait_for_group_size(pgid: int, *, at_least: int, timeout_s: float = 15.0) -> "list[int]":
    deadline = time.monotonic() + timeout_s
    members: list[int] = []
    while time.monotonic() < deadline:
        members = _pids_in_group(pgid)
        if len(members) >= at_least:
            return members
        time.sleep(0.1)
    return members


def test_start_uvicorn_subprocess_always_passes_workers_even_at_the_default(tmp_path, monkeypatch):
    """Completion condition 1 (design D-1, 監督裁定 19): `--workers <n>` is
    ALWAYS a literal argv pair, even when the caller omits `workers`
    entirely (default 1) -- never left to uvicorn's own bare-omitted
    default.

    mutation (`socket_harness.py`): only append `"--workers", str(workers)`
    when `workers != 1` -- this test goes red because the default call's
    own captured argv no longer carries `--workers` at all.
    """
    module_path = tmp_path / "conf_socket_probe_app_workers_default.py"
    module_path.write_text(_PROBE_APP_SOURCE)
    real_popen = sh.subprocess.Popen
    captured: dict = {}

    def _capturing_popen(argv, *args, **kwargs):
        captured["argv"] = list(argv)
        return real_popen(argv, *args, **kwargs)

    monkeypatch.setattr(sh.subprocess, "Popen", _capturing_popen)
    handle = sh.start_uvicorn_subprocess(
        "conf_socket_probe_app_workers_default:app", pidfile=tmp_path / "probe_workers_default.pid", cwd=tmp_path,
    )
    try:
        sh.wait_until_ready(f"http://127.0.0.1:{handle.port}/anything", timeout_s=10.0, label="probe-workers-default")
        assert "--workers" in captured["argv"], f"argv carries no --workers at all: {captured['argv']!r}"
        idx = captured["argv"].index("--workers")
        assert captured["argv"][idx + 1] == "1", f"default --workers value was {captured['argv'][idx + 1]!r}, expected '1'"
    finally:
        handle.stop()


def test_start_uvicorn_subprocess_workers_two_starts_a_supervisor_with_two_children(tmp_path):
    """Completion condition 1's own `n = 2` half: the supervisor's own
    process group carries EXACTLY 2 real uvicorn worker children -- their
    own cmdline carries "multiprocessing-fork" (`multiprocessing.spawn.
    spawn_main`'s own argv marker). Never merely ">= 3 total members":
    `multiprocessing`'s own "spawn" start method (this repository's macOS
    dev machines' default) also starts a `resource_tracker` helper
    process in the SAME pgid -- not a uvicorn worker at all -- which a
    bare member-count check cannot tell apart from a genuine 3rd worker."""
    module_path = tmp_path / "conf_socket_probe_app_workers_two.py"
    module_path.write_text(_PROBE_APP_SOURCE)
    handle = sh.start_uvicorn_subprocess(
        "conf_socket_probe_app_workers_two:app", pidfile=tmp_path / "probe_workers_two.pid",
        cwd=tmp_path, workers=2,
    )
    try:
        sh.wait_until_ready(f"http://127.0.0.1:{handle.port}/anything", timeout_s=10.0, label="probe-workers-two")
        pgid = handle.process.pid
        deadline = time.monotonic() + 15.0
        workers: list[int] = []
        while time.monotonic() < deadline:
            members = _pids_in_group(pgid)
            workers = [pid for pid in members if pid != pgid and "multiprocessing-fork" in sh._process_cmdline(pid)]
            if len(workers) >= 2:
                break
            time.sleep(0.1)
        assert len(workers) == 2, (
            f"process group {pgid} carries {len(workers)} real uvicorn worker(s) (cmdline-verified), "
            f"expected exactly 2: {workers!r}"
        )
    finally:
        handle.stop()


def test_uvicorn_subprocess_stop_signals_the_whole_process_group(tmp_path, monkeypatch):
    """Completion condition 2 (design 裁定 19): `stop()` signals the WHOLE
    process group via `os.killpg`, not merely the supervisor's own pid --
    after `stop()`, zero processes remain in that pgid.

    mutation (`socket_harness.py`): revert `UvicornSubprocessHandle.stop()`
    to `_terminate_then_kill(self.process, ...)` (a single-pid signal) --
    this test goes red because `os.killpg` is never called at all.
    """
    module_path = tmp_path / "conf_socket_probe_app_stop_group.py"
    module_path.write_text(_PROBE_APP_SOURCE)
    handle = sh.start_uvicorn_subprocess(
        "conf_socket_probe_app_stop_group:app", pidfile=tmp_path / "probe_stop_group.pid",
        cwd=tmp_path, workers=2,
    )
    sh.wait_until_ready(f"http://127.0.0.1:{handle.port}/anything", timeout_s=10.0, label="probe-stop-group")
    _wait_for_group_size(handle.process.pid, at_least=3)
    pgid = handle.process.pid
    real_killpg = sh.os.killpg
    killpg_calls: list[tuple] = []

    def _capturing_killpg(target_pgid, sig):
        killpg_calls.append((target_pgid, sig))
        return real_killpg(target_pgid, sig)

    monkeypatch.setattr(sh.os, "killpg", _capturing_killpg)
    handle.stop()

    assert killpg_calls, "UvicornSubprocessHandle.stop() never called os.killpg at all"
    assert killpg_calls[0] == (pgid, signal.SIGTERM), f"first os.killpg call was {killpg_calls[0]!r}, expected SIGTERM on {pgid}"
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline and _pids_in_group(pgid):
        time.sleep(0.1)
    assert _pids_in_group(pgid) == [], f"process group {pgid} still has member(s) after stop(): {_pids_in_group(pgid)!r}"


def test_sweep_orphans_reaches_a_replaced_worker_via_the_recorded_pgid(tmp_path):
    """Completion condition 3 (design 裁定 33): the pidfile records the
    supervisor's own PGID (not a worker's own pid, which uvicorn's `Multi
    process.keep_subprocess_alive` silently replaces on a crash) -- after
    one worker is SIGKILLed and uvicorn has replaced it with a new child
    (same pgid, different pid), `sweep_orphans` reading that SAME pidfile
    still reaches and kills the WHOLE group, including the replacement.

    mutation (`socket_harness.py`): `pidfile.write_text(str(process.pid))`
    -> `pidfile.write_text(str(process.pid + 1))` (a stale/wrong value,
    standing in for "recorded the wrong process") -- this test goes red
    because `sweep_orphans` can no longer resolve a real pgid from the
    pidfile's own content, so the replaced worker (and its supervisor)
    survive the sweep.
    """
    module_path = tmp_path / "conf_socket_probe_app_pgid_sweep.py"
    module_path.write_text(_PROBE_APP_SOURCE)
    pidfile = tmp_path / "probe_pgid_sweep.pid"
    handle = sh.start_uvicorn_subprocess(
        "conf_socket_probe_app_pgid_sweep:app", pidfile=pidfile, cwd=tmp_path, workers=2,
    )
    try:
        sh.wait_until_ready(f"http://127.0.0.1:{handle.port}/anything", timeout_s=10.0, label="probe-pgid-sweep")
        pgid = handle.process.pid
        members = _wait_for_group_size(pgid, at_least=3)
        assert len(members) >= 3, f"process group {pgid} never reached 3 members: {members!r}"
        # `multiprocessing`'s own "spawn" start method (this repository's
        # macOS dev machines' default) also starts a `resource_tracker`
        # helper process in the SAME pgid -- invisible to uvicorn's own
        # `Multiprocess` bookkeeping, so killing it is never "replaced".
        # A real worker's own cmdline carries "multiprocessing-fork"
        # (`multiprocessing.spawn.spawn_main`'s own argv marker); this
        # selects one of THOSE, never the supervisor or the tracker.
        worker_pids = [
            pid for pid in members
            if pid != pgid and "multiprocessing-fork" in sh._process_cmdline(pid)
        ]
        assert worker_pids, f"no real uvicorn worker (multiprocessing-fork) found among group members {members!r}"
        killed_worker = worker_pids[0]
        original_members = set(members)
        os.kill(killed_worker, signal.SIGKILL)

        # Wait for uvicorn's own supervisor to notice and spawn a
        # replacement (`Multiprocess.keep_subprocess_alive`, polled every
        # 0.5s) -- a NEW pid (never among the ORIGINAL members) must join
        # the SAME pgid. The killed worker's own pid may still be visible
        # to `ps` as a zombie until reaped (not checked here -- that is
        # orthogonal to whether a replacement was actually spawned).
        deadline = time.monotonic() + 15.0
        replaced_pid = None
        while time.monotonic() < deadline:
            current = _pids_in_group(pgid)
            new_pids = set(current) - original_members
            if new_pids:
                replaced_pid = next(iter(new_pids))
                break
            time.sleep(0.2)
        assert replaced_pid is not None, (
            f"uvicorn never replaced the SIGKILLed worker {killed_worker} "
            f"(original members {sorted(original_members)!r}, last observed: {_pids_in_group(pgid)!r})"
        )

        killed = sh.sweep_orphans(tmp_path, marker="conf_socket_probe_app_pgid_sweep")
        assert pgid in killed, f"sweep_orphans did not report signalling pgid {pgid}: {killed!r}"

        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            # `handle.process.poll()` (this test's own still-live `Popen`
            # object, never reaped by `sweep_orphans` itself, which never
            # held a `Popen` handle at all -- only the bare pid from the
            # pidfile) actually reaps the supervisor once it has exited;
            # without this, its own zombie entry keeps showing up in `ps`
            # (and therefore `_pids_in_group`) forever, since nothing else
            # in this process ever calls `wait()`/`poll()` on it.
            handle.process.poll()
            if not _pids_in_group(pgid):
                break
            time.sleep(0.1)
        assert _pids_in_group(pgid) == [], (
            f"process group {pgid} still has member(s) after sweep_orphans: {_pids_in_group(pgid)!r}"
        )
        assert not pidfile.exists()
    finally:
        with _suppress_test_teardown_errors():
            handle.stop()


class _suppress_test_teardown_errors:
    """Local, minimal `contextlib.suppress(Exception)` for this test's own
    best-effort `finally` cleanup (the group is normally already empty by
    that point -- this only guards against `stop()` re-raising on an
    already-fully-torn-down handle)."""

    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type, exc, tb) -> bool:
        return exc_type is not None and issubclass(exc_type, Exception)


# ---------------------------------------------------------------------------
# F-2 (a) (監督裁定 2026-09-08): a port can be RESERVED (bound + listening)
# before the server that will answer on it starts, and handed straight to
# uvicorn's own `Server.run(sockets=[...])`.
# ---------------------------------------------------------------------------


def test_reserve_port_returns_a_live_listening_socket():
    """`reserve_port()` itself: unlike `free_port` (bind-and-release), the
    returned socket is still bound and LISTENING the instant this function
    returns -- a second bind attempt on the same port must fail immediately
    (`OSError`, address already in use), never silently succeed."""
    reserved = sh.reserve_port()
    try:
        with pytest.raises(OSError):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.bind(("127.0.0.1", reserved.port))
    finally:
        reserved.close()


def test_uvicorn_thread_serves_on_a_pre_reserved_socket():
    """Design ruling F-2 (a): `start_uvicorn_thread(..., reserved=...)`
    must hand uvicorn's OWN `Server.run(sockets=[...])` the EXACT socket
    `reserve_port()` already bound and is listening on -- never silently
    fall back to binding a fresh port of its own. This is what lets a
    caller (the socket adapter, WP-4) commit a REAL, already-owned port
    number to a `_surfaces_value()` URL at COMPOSITION time, before the
    uvicorn thread that will actually answer requests on it has even
    started.

    mutation (`socket_harness.py`): make `start_uvicorn_thread` ignore
    `reserved` and always bind a fresh `free_port()` of its own instead --
    this test goes red on the first assertion below because the returned
    handle's own `.port` would then almost certainly differ from `reserved.
    port` (an independent freshly-bound ephemeral port), and even in the
    astronomically unlikely case the two numbers coincided, the SECOND
    assertion (a real dial against `reserved.port`) would still fail: the
    mutation never accepts connections on the socket `reserve_port()`
    itself is holding open, so the real request below would hang until its
    own timeout and raise.

    N-2 差し戻し (監督裁定 2026-09-08): the two assertions above both stay
    GREEN under a DIFFERENT mutation that closes `reserved.sock` and hands
    uvicorn `sockets=None` instead (letting uvicorn bind a FRESH socket of
    its own on the SAME port NUMBER, `config.port=reserved.port`) -- the
    port number still matches and a real dial still succeeds, because
    uvicorn is genuinely listening, just on a socket object it bound
    itself rather than the one `reserve_port()` handed it (exactly the
    bind-and-close TOCTOU window F-2 (a) exists to close). The structural
    asserts below close that gap directly: `asyncio.loop.create_server(
    sock=...)` (what `Server.run(sockets=[...])` ends up calling, measured
    directly against this venv's own installed uvicorn/asyncio) never
    re-binds -- it keeps using the EXACT socket object passed in (`asyncio.
    base_events.BaseEventLoop.create_server`'s own source: the `sock is
    not None` branch does `sockets = [sock]`, no new `socket.socket(...)`
    call at all), so the fd `Server.servers[0].sockets[0]` (an `asyncio.
    trsock.TransportSocket` WRAPPING that same fd, never `is`-identical to
    the raw `socket.socket` -- fileno comparison, not object identity, is
    what actually pins this) must be the SAME fd `reserved.sock` itself
    still holds open.

    mutation (`socket_harness.py`): in `start_uvicorn_thread`, when
    `reserved` is given, close `reserved.sock` and pass `sockets=None`
    (falling through to a fresh `config.port=reserved.port` bind) instead
    of `sockets=[reserved.sock]` -- this test goes red on the structural
    asserts below because the serving socket's fd is then DIFFERENT from
    `reserved.sock`'s own (freshly bound by uvicorn itself), and `reserved.
    sock.fileno()` is `-1` (closed).
    """
    app = _json_app()
    reserved = sh.reserve_port()
    reserved_fileno = reserved.sock.fileno()
    handle = sh.start_uvicorn_thread(app, reserved=reserved, start_timeout_s=10.0)
    try:
        assert handle.port == reserved.port, (
            f"start_uvicorn_thread(reserved=...) must serve on the RESERVED port, "
            f"got handle.port={handle.port} != reserved.port={reserved.port}"
        )
        status, body = _get(f"http://127.0.0.1:{reserved.port}/v1/capabilities", timeout=10.0)
        assert status == 401

        assert handle.server.servers, "uvicorn must have created at least one real asyncio server"
        serving_sockets = handle.server.servers[0].sockets
        serving_filenos = {s.fileno() for s in (serving_sockets or ())}
        assert reserved.sock.fileno() != -1, (
            "the reserved socket must still be OPEN (never closed then re-bound) while uvicorn serves on it"
        )
        assert reserved_fileno in serving_filenos, (
            f"start_uvicorn_thread(reserved=...) must hand uvicorn the EXACT reserved socket's own fd "
            f"({reserved_fileno}) -- uvicorn must never close it and bind a fresh one of its own on the "
            f"same port number (N-2 差し戻し, 監督裁定 2026-09-08); serving fds were {serving_filenos!r}"
        )
    finally:
        handle.stop()


def test_start_uvicorn_thread_serves_on_a_port_it_reserved_itself(monkeypatch):
    """R-44 WP-3 (e), R-8 (design §3.2's own named most-frequent-path
    finding): the DEFAULT path (`reserved` AND `port` both omitted) now
    calls `reserve_port()` internally, never `free_port()` -- the same
    TOCTOU-closing behavior a caller-supplied `reserved=` already got,
    just minted here instead.

    mutation (`socket_harness.py`): revert `start_uvicorn_thread`'s
    default branch back to `free_port()` -- this test goes red because
    `counters["free"]` becomes 1 (asserted to stay 0 below) while
    `counters["reserve"]` stays 0 (asserted to become 1).
    """
    app = _json_app()
    real_reserve_port = sh.reserve_port
    real_free_port = sh.free_port
    counters = {"reserve": 0, "free": 0}

    def _counting_reserve_port():
        counters["reserve"] += 1
        return real_reserve_port()

    def _counting_free_port():
        counters["free"] += 1
        return real_free_port()

    monkeypatch.setattr(sh, "reserve_port", _counting_reserve_port)
    monkeypatch.setattr(sh, "free_port", _counting_free_port)

    handle = sh.start_uvicorn_thread(app, start_timeout_s=10.0)
    try:
        assert counters["reserve"] == 1, f"expected exactly one reserve_port() call, got {counters!r}"
        assert counters["free"] == 0, f"expected free_port() never called on the default path, got {counters!r}"
        status, _ = _get(f"http://127.0.0.1:{handle.port}/v1/capabilities", timeout=10.0)
        assert status == 401
    finally:
        handle.stop()
        # R-8: `.stop()` is idempotent (uvicorn's own shutdown already
        # closes the reservation's socket) -- a second call must not raise.
        handle.stop()


def test_start_nginx_with_bind_retry_moves_to_a_different_port_when_the_first_bind_fails(monkeypatch):
    """F-2 (a) 後半差し戻し (監督裁定 2026-09-08): nginx's own listen port
    is reserved (bind+listen, then close) rather than picked with a bare
    `free_port()` -- but nginx cannot accept a pre-opened socket the way
    uvicorn can, so between that reservation's own `.close()` and nginx's
    own later real `bind()` there is a real (if narrow) window a
    concurrent process can win. This test occupies the FIRST port `reserve_
    port()` would hand back with a real, live listening socket held open
    for the duration -- standing in for exactly that concurrent winner --
    and asserts `start_nginx_with_bind_retry` detects nginx's resulting
    immediate exit and retries EXACTLY ONCE on a freshly reserved,
    genuinely free port, ending up actually serving there.

    【追記 2026-09-16、R-44 Q-8(依頼者裁定)】this test only forces ONE
    failure, so it still observes exactly one retry (2 total `reserve_
    port()` calls) even under the revised 3-attempt policy -- it is not
    itself a claim that one retry is the maximum; see `test_start_nginx_
    with_bind_retry_succeeds_on_the_third_port` (a 3rd-attempt success)
    and `test_start_nginx_with_bind_retry_gives_up_after_three_attempts`
    (all 3 exhausted) for the fuller policy.

    mutation (`socket_harness.py`): remove the retry loop from `start_
    nginx_with_bind_retry` (raise/fail on the first attempt instead) --
    this test goes red because `RealSocketSurface.base_url` then raises
    `HarnessStartupError` instead of succeeding on the second port.
    """
    occupied = sh.reserve_port()  # stands in for a concurrent winner of the bind race
    real_reserve_port = sh.reserve_port
    call_count = {"n": 0, "nginx": 0}

    def fake_reserve_port():
        call_count["n"] += 1
        # R-44 WP-3 (e), R-8: `RealSocketSurface._start()` now ALSO calls
        # `reserve_port()` for its own data/control uvicorn upstreams
        # (`start_uvicorn_thread`'s own new default path) BEFORE it ever
        # reaches nginx -- always exactly 2 such calls, in that fixed
        # order, before this function's own retry loop begins. Only calls
        # AFTER those 2 are "nginx calls" for the purpose of this test.
        if call_count["n"] <= 2:
            return real_reserve_port()
        call_count["nginx"] += 1
        if call_count["nginx"] == 1:
            # A throwaway, never-bound socket object -- only `.port` and
            # `.close()` (a no-op close of an unbound socket) are ever
            # touched by the code under test; the ACTUAL occupancy of
            # `occupied.port` comes from `occupied`'s own real listening
            # socket, held open by this test for the duration.
            return sh.ReservedPort(port=occupied.port, sock=socket.socket(socket.AF_INET, socket.SOCK_STREAM))
        return real_reserve_port()

    monkeypatch.setattr(sh, "reserve_port", fake_reserve_port)
    app = _json_app()
    surface = sh.RealSocketSurface(data_app=app, control_app=app)
    try:
        base_url = surface.base_url  # forces start; must succeed via the retry
        listen_port = int(base_url.rsplit(":", 1)[1])

        assert listen_port != occupied.port, (
            "the surface must have moved to a DIFFERENT port after the first bind failed"
        )
        assert call_count["nginx"] == 2, (
            "exactly one retry (2 total nginx-side reserve_port() calls) must have occurred in THIS "
            "scenario (one forced failure) -- this is a per-scenario count, not a claim that one retry "
            "is the global maximum (up to 2 retries/3 attempts are now possible, R-44 Q-8)"
        )
        status, _ = _get(f"{base_url}/v1/capabilities", timeout=10.0)
        assert status == 401
    finally:
        surface.stop()
        occupied.close()


def test_start_nginx_with_bind_retry_succeeds_on_the_third_port(monkeypatch):
    """R-44 Q-8 (依頼者裁定 2026-09-16): `start_nginx_with_bind_retry` goes
    through a genuine 3RD attempt -- the first two reserved ports are both
    occupied by a real, live listening socket (standing in for two
    concurrent winners of the bind race), the third is left free.

    mutation (`socket_harness.py`): change `NGINX_BIND_MAX_ATTEMPTS = 3` to
    `NGINX_BIND_MAX_ATTEMPTS = 2` -- both the retry loop's own range AND
    the give-up check are derived from this ONE constant (never a
    separately hardcoded `3`), so this test goes red because `start_nginx_
    with_bind_retry` then gives up (raises `HarnessStartupError`) after
    only 2 attempts, before ever reaching the 3rd (genuinely free)
    reserved port.
    """
    occupied_1 = sh.reserve_port()
    occupied_2 = sh.reserve_port()
    real_reserve_port = sh.reserve_port
    call_count = {"n": 0, "nginx": 0}

    def fake_reserve_port():
        call_count["n"] += 1
        if call_count["n"] <= 2:  # the surface's own data/control upstream reservations, R-8
            return real_reserve_port()
        call_count["nginx"] += 1
        if call_count["nginx"] == 1:
            return sh.ReservedPort(port=occupied_1.port, sock=socket.socket(socket.AF_INET, socket.SOCK_STREAM))
        if call_count["nginx"] == 2:
            return sh.ReservedPort(port=occupied_2.port, sock=socket.socket(socket.AF_INET, socket.SOCK_STREAM))
        return real_reserve_port()

    monkeypatch.setattr(sh, "reserve_port", fake_reserve_port)
    app = _json_app()
    surface = sh.RealSocketSurface(data_app=app, control_app=app)
    try:
        base_url = surface.base_url
        listen_port = int(base_url.rsplit(":", 1)[1])
        assert listen_port not in (occupied_1.port, occupied_2.port), (
            "the surface must have moved past BOTH occupied ports to the 3rd, genuinely free one"
        )
        assert call_count["nginx"] == 3, (
            f"expected exactly 3 nginx-side reserve_port() calls (2 failures + 1 success), "
            f"got {call_count['nginx']}"
        )
        status, _ = _get(f"{base_url}/v1/capabilities", timeout=10.0)
        assert status == 401
    finally:
        surface.stop()
        occupied_1.close()
        occupied_2.close()


def test_start_nginx_with_bind_retry_gives_up_after_three_attempts(tmp_path, monkeypatch):
    """R-44 Q-8: all 3 attempts occupied -> `HarnessStartupError`, and
    there is no 4th attempt (`reserve_port()` is called exactly 3 times on
    nginx's own side, never a 4th).

    mutation (`socket_harness.py`): change `NGINX_BIND_MAX_ATTEMPTS = 3` to
    `NGINX_BIND_MAX_ATTEMPTS = 4` -- this test goes red because a 4th
    nginx-side `reserve_port()` call occurs (asserted not to, below) and
    the surface then succeeds on that 4th, still-free port instead of
    raising.
    """
    occupied = [sh.reserve_port() for _ in range(3)]
    real_reserve_port = sh.reserve_port
    call_count = {"n": 0, "nginx": 0}

    def fake_reserve_port():
        call_count["n"] += 1
        if call_count["n"] <= 2:  # the surface's own data/control upstream reservations, R-8
            return real_reserve_port()
        call_count["nginx"] += 1
        if call_count["nginx"] <= 3:
            return sh.ReservedPort(
                port=occupied[call_count["nginx"] - 1].port,
                sock=socket.socket(socket.AF_INET, socket.SOCK_STREAM),
            )
        return real_reserve_port()

    monkeypatch.setattr(sh, "reserve_port", fake_reserve_port)
    app = _json_app()
    prefix = tmp_path / "nginx-give-up"
    prefix.mkdir()
    surface = sh.RealSocketSurface(data_app=app, control_app=app, work_dir=prefix)
    try:
        with pytest.raises(sh.HarnessStartupError):
            surface.base_url
        assert call_count["nginx"] == 3, (
            f"expected exactly 3 nginx-side reserve_port() calls (no 4th attempt), got {call_count['nginx']}"
        )
    finally:
        surface.stop()
        for reservation in occupied:
            reservation.close()


def test_failed_nginx_attempts_keep_their_error_logs(tmp_path, monkeypatch):
    """R-44 Q-8: each FAILED attempt's own `error.log` is preserved under
    an attempt-numbered file (`error.attempt<N>.log`) -- never overwritten
    by the next attempt's own truncate-then-retry.

    mutation (`socket_harness.py`): replace the `(prefix / f"error.
    attempt{attempt}.log").write_text(attempt_log_text)` line with `pass`
    -- this test goes red because no `error.attempt*.log` file exists
    after the 3-attempt exhaustion below.
    """
    occupied = [sh.reserve_port() for _ in range(3)]
    real_reserve_port = sh.reserve_port
    call_count = {"n": 0, "nginx": 0}

    def fake_reserve_port():
        call_count["n"] += 1
        if call_count["n"] <= 2:  # the surface's own data/control upstream reservations, R-8
            return real_reserve_port()
        call_count["nginx"] += 1
        if call_count["nginx"] <= 3:
            return sh.ReservedPort(
                port=occupied[call_count["nginx"] - 1].port,
                sock=socket.socket(socket.AF_INET, socket.SOCK_STREAM),
            )
        return real_reserve_port()

    monkeypatch.setattr(sh, "reserve_port", fake_reserve_port)
    app = _json_app()
    prefix = tmp_path / "nginx-keep-logs"
    prefix.mkdir()
    surface = sh.RealSocketSurface(data_app=app, control_app=app, work_dir=prefix)
    try:
        with pytest.raises(sh.HarnessStartupError):
            surface.base_url
        harness_prefix = prefix / sh.NGINX_PREFIX_MARKER
        preserved = sorted(harness_prefix.glob("error.attempt*.log"))
        assert len(preserved) == 3, f"expected 3 preserved per-attempt error.log files, got {preserved!r}"
        for log_path in preserved:
            assert log_path.read_text(), f"{log_path} must not be empty"
    finally:
        surface.stop()
        for reservation in occupied:
            reservation.close()


# ---------------------------------------------------------------------------
# F-3 / F-4 (監督裁定 2026-09-08): `sweep_orphans` never signals a pid it
# does not recognize as its own (owner check via the process's own cmdline).
# ---------------------------------------------------------------------------


def test_sweep_orphans_never_kills_a_pid_whose_cmdline_lacks_the_marker():
    """F-4 差し戻し (監督裁定 2026-09-08): a pidfile naming a pid that has
    since been REUSED by an unrelated process (its cmdline carries none of
    this harness's own marker) must never be signalled -- only its own
    stale pidfile RECORD is removed. Without this owner check, a caller
    that reuses a fixed `work_dir` across runs (WP-4/WP-6c, design D-2
    (f)'s own documented future use) could have `sweep_orphans` kill a
    completely unrelated process that happened to reuse a dead harness
    pid.

    mutation (`socket_harness.py`): drop the `marker not in _process_
    cmdline(pid)` owner check from `sweep_orphans` (i.e. unconditionally
    `os.kill` every pid a pidfile names) -- this test goes red because the
    unrelated dummy process below (no marker anywhere in its own argv)
    would then be killed.
    """
    tmp_root = Path(tempfile.mkdtemp(prefix="conf-socket-sweep-owner-"))
    prefix = tmp_root / "orphan_prefix"
    prefix.mkdir()
    try:
        # A live process with NO marker anywhere in its own cmdline --
        # this is exactly what an unrelated process that happens to reuse
        # a stale pidfile's pid looks like.
        process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        reaper = threading.Thread(target=process.wait, daemon=True)
        reaper.start()
        (prefix / "unrelated.pid").write_text(str(process.pid))

        try:
            killed = sh.sweep_orphans(prefix)

            assert process.pid not in killed, "sweep_orphans must not signal a pid lacking its own marker"
            assert process.poll() is None, "the unrelated (unmarked) process must still be alive"
            assert not (prefix / "unrelated.pid").exists(), "the stale pidfile record must still be removed"
        finally:
            process.terminate()
            reaper.join(timeout=5.0)
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_sweep_orphans_never_signals_a_non_positive_pid(monkeypatch, tmp_path):
    """監督裁定 2026-09-08 U-12 / external review 2 R-27: a pidfile whose
    parsed pid is `<= 0` must be treated as never ours -- explicitly, and
    BEFORE the owner check -- because `os.kill(0, sig)` signals this whole
    process group and `os.kill(-1, sig)` every process this user may
    signal. `0` and `-1` below exercise that guard directly; a third
    pidfile names a real, positive pid (this test's own parent process)
    that certainly exists but carries none of this harness's marker, so it
    is caught by the ALREADY-tested owner check (see `test_sweep_orphans_
    never_kills_a_pid_whose_cmdline_lacks_the_marker`) rather than the new
    `pid <= 0` guard -- included here to confirm the two paths agree on
    the observable outcome (nothing signalled, pidfile gone).

    mutation (`socket_harness.py`): remove the `pid <= 0` guard -- this
    test goes red because `_process_cmdline(0)` or `_process_cmdline(-1)`
    is then called (asserted never to happen below) and, on a marker
    match, `os.kill` would be reached with a non-positive pid (asserted to
    raise below rather than silently signal something).
    """
    prefix = tmp_path / "orphan_prefix"
    prefix.mkdir()
    (prefix / "zero.pid").write_text("0")
    (prefix / "negative.pid").write_text("-1")
    (prefix / "reused.pid").write_text(str(os.getppid()))

    real_process_cmdline = sh._process_cmdline

    def guarded_process_cmdline(pid):
        if pid <= 0:
            pytest.fail(f"_process_cmdline must never be called with a non-positive pid, got {pid}")
        return real_process_cmdline(pid)

    kill_calls: list[tuple[int, int]] = []

    def guarded_kill(pid, sig):
        if pid <= 0:
            raise AssertionError(f"os.kill must never be called with a non-positive pid, got {pid}")
        kill_calls.append((pid, sig))

    monkeypatch.setattr(sh, "_process_cmdline", guarded_process_cmdline)
    monkeypatch.setattr(sh.os, "kill", guarded_kill)

    killed = sh.sweep_orphans(prefix)

    assert killed == []
    assert kill_calls == [], "sweep_orphans must not signal any of these three pidfiles"
    assert not (prefix / "zero.pid").exists()
    assert not (prefix / "negative.pid").exists()
    assert not (prefix / "reused.pid").exists()


# ---------------------------------------------------------------------------
# `free_port` sanity
# ---------------------------------------------------------------------------


def test_free_port_returns_a_bindable_port():
    port = sh.free_port()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", port))  # must not raise


# ---------------------------------------------------------------------------
# R-44 WP-3 (e), R-19: the C-26 launchers' own F-15/F-16 blocking
# `subprocess.run` call sites hand uvicorn a `reserve_port()` reservation
# via `--fd`/`pass_fds`, never a bare `--port <number>`.
# ---------------------------------------------------------------------------


def test_f15_and_f16_paths_hand_their_reserved_socket_to_uvicorn(launcher_class: type, monkeypatch: pytest.MonkeyPatch) -> None:
    """R-19 (design D-7): `attempt_start_without_process_ceilings` (F-15)
    and `attempt_start_with_lowered_role_limit`'s own first, fail-fast
    `subprocess.run` call (F-16-lowered) both build their blocking
    `python -m uvicorn` invocation around a `reserve_port()`-owned socket
    -- read directly off a monkeypatched `subprocess.run` (never the
    source text, `OPERATING_CONDITIONS.md` §1.7 の 52), which delegates
    through to the REAL `subprocess.run` so both real, blocking calls
    still genuinely happen (a real throwaway platform is still
    provisioned and torn down by each `attempt_start_*` call below).

    mutation (`real_server_r2db.py`): replace the F-16-lowered
    `subprocess.run` call's `"--fd", str(lowered_fd)` with `"--port",
    str(lowered_reservation.port)` -- this test goes red on the r2db
    side's F-16-lowered assertion below because the captured argv no
    longer contains `--fd` at all.

    Each `attempt_start_*` call ALSO runs several other real `subprocess.
    run` calls first (`psql` against the throwaway platform's own
    migrations, the real `ops declare-surfaces`/`declare-process-
    ceilings` CLI) -- all captured by the SAME process-wide `subprocess.
    run` patch (monkeypatching a module object patches every importer of
    it, `subprocess` included).

    【改訂 2026-09-16、コードレビュー 1 回目差し戻し 5、監督裁定】the
    previous form read `calls[-1]` (the LAST captured call) on the
    assumption that nothing after the uvicorn invocation ever calls
    `subprocess.run` again -- true today for both `attempt_start_*`
    methods, but a proxy for the property this test actually cares about
    ("uvicorn was launched via `--fd`"), not that property itself
    (`OPERATING_CONDITIONS.md` §1.7 の 52): a FUTURE `finally`/cleanup
    step that also called `subprocess.run` would silently make this
    assertion read the WRONG call, going red for a call-ORDER reason
    unrelated to `--fd`/`pass_fds` at all. This filters `calls` down to
    the ones whose own argv actually names `uvicorn` and asserts there is
    EXACTLY ONE such call, then reads THAT one -- independent of where in
    the call sequence it happened to land.
    """
    module = sys.modules[launcher_class.__module__]
    real_run = module.subprocess.run
    calls: list[dict] = []

    def _capturing_run(argv, *args, **kwargs):
        calls.append({"argv": list(argv), "pass_fds": kwargs.get("pass_fds")})
        return real_run(argv, *args, **kwargs)

    monkeypatch.setattr(module.subprocess, "run", _capturing_run)

    def _assert_the_uvicorn_call_uses_fd(label: str) -> None:
        uvicorn_calls = [c for c in calls if "uvicorn" in c["argv"]]
        assert len(uvicorn_calls) == 1, (
            f"{label}: expected exactly one subprocess.run call whose argv names 'uvicorn', "
            f"got {len(uvicorn_calls)}: {uvicorn_calls!r}"
        )
        call = uvicorn_calls[0]
        argv = call["argv"]
        assert "--fd" in argv, f"{label} argv carries no --fd: {argv!r}"
        fd_index = argv.index("--fd")
        fd_value = int(argv[fd_index + 1])
        assert call["pass_fds"] is not None and fd_value in call["pass_fds"], (
            f"{label} pass_fds {call['pass_fds']!r} does not include its own --fd value {fd_value}"
        )
        assert "--port" not in argv, f"{label} argv still carries --port: {argv!r}"

    launcher_f15 = launcher_class()
    launcher_f15.attempt_start_without_process_ceilings()
    _assert_the_uvicorn_call_uses_fd("F-15")

    calls.clear()
    launcher_f16 = launcher_class()
    launcher_f16.attempt_start_with_lowered_role_limit()
    _assert_the_uvicorn_call_uses_fd("F-16-lowered")
