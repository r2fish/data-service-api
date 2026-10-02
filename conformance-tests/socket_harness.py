"""Common process/port/reverse-proxy harness for the real-socket
conformance plugs and the C-26 composition-root launchers (WP-3, design
`docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md` D-2).

This module owns exactly the plumbing D-2 assigns to it -- process/port/
proxy management that carries no contract-level meaning of its own:

  (a) uvicorn -- a THREAD-version launcher (`start_uvicorn_thread`, used by
      the socket adapters WP-4 adds: the composition they front is already
      held in-process, so `_resolve_cell`/`backend_calls` (design D-12)
      keep working) and a SUBPROCESS-version launcher
      (`start_uvicorn_subprocess`, used by the C-26 composition-root
      launchers WP-6c adds: those launchers start a REAL, separate OS
      process with no in-process handle held open at all, D-1 (B)) --
      both with the same readiness contract (`wait_until_ready`) and the
      same stop discipline (graceful shutdown, then a bounded wait, then
      an unconditional kill).
  (b) nginx -- conf rendering (`render_nginx_conf`), a mandatory
      `nginx -t` syntax check before anything starts (`check_nginx_config`),
      and process management (`start_nginx`).
  (c) a free-port finder (`free_port`).
  (d) a certain kill on stop (every `stop()`/`close()` method below is
      unconditional: SIGTERM, wait, then SIGKILL if still alive).
  (e) `atexit` registration for the abnormal-exit path (every long-lived
      handle registers its own best-effort cleanup the instant it holds a
      real OS resource).
  (f) a startup-time sweep of orphaned processes left by a PREVIOUS run
      that exited without running any Python cleanup at all (a killed
      process, an interpreter crash) -- `sweep_orphans` reads pidfiles
      under a given prefix directory and kills whatever pid each one
      names -- but ONLY when that pid's own command line still carries
      this harness's own marker (owner check, monitor 裁定 2026-09-08,
      F-4): a pid a stale pidfile names that has since been reused by an
      unrelated process is never signalled. A recorded pid
      that is ALSO its own process group's leader (`start_uvicorn_
      subprocess`'s own supervisors, always their own session/group)
      is signalled as a whole GROUP (`os.killpg`), reaching worker
      children too; every other pidfile writer (nginx) keeps the
      single-pid `os.kill` this always used.
  (g) lazy startup -- `RealSocketSurface` binds no port and spawns no
      process until `.data_base_url`/`.control_base_url` is first read.
      `conformance-tests/conftest.py`'s `_discover_and_build()` builds
      EVERY registered adapter's Python object at collection time, on
      EVERY xdist worker (design review 2 finding 5) -- without this
      laziness, a worker whose own tests never touch a given socket plug
      would still pay for that plug's own nginx + 2 uvicorn processes.
      Building the adapter OBJECT stays eager (unchanged, and cheap: it is
      plain Python composition, same as the two existing in-process/ASGI
      plugs); only the real sockets/processes are deferred.
  (h) port reservation (`reserve_port`, monitor 裁定 2026-09-08, F-2 (a))
      -- unlike `free_port` (bind-and-release), binds AND listens
      immediately, so a caller can commit the real, already-owned port
      number to a declared URL before the server that will answer on it
      has even started; `start_uvicorn_thread(..., reserved=...)` hands
      the reservation's own live socket straight to uvicorn's own
      `Server.run(sockets=[...])`, which never re-binds. nginx's own
      listen port is likewise reserved (bind, then close -- nginx cannot
      accept a pre-opened socket the way uvicorn can) via `start_nginx_
      with_bind_retry` (F-2 (a) 後半差し戻し, 監督裁定 2026-09-08), which
      retries EXACTLY ONCE on a freshly reserved port if nginx exits
      immediately (a lost bind race) on the first one. 【追記 2026-09-16、
      R-44 Q-8(依頼者裁定)】改訂され、いまは 3 回まで試行する
      (`start_nginx_with_bind_retry`'s own docstring)。
  (i) a port ledger (`RealSocketSurface._start`'s own `ports.json`, F-3)
      -- every port a surface claims (nginx's own listen port, and both
      upstreams') is recorded under the SAME marker-bearing prefix
      directory the residue check already scopes to, so a CI/completion-
      gate check can confirm none of them still has a listener even where
      a killed nginx MASTER leaves an unmarked WORKER process behind
      (nginx rewrites a worker's own argv to `nginx: worker process`,
      invisible to a marker-scoped `pgrep`).
  (j) that same ledger is also read back, live, by `_stop_best_effort`
      itself (N-1 差し戻し, 監督裁定 2026-09-08): a killed nginx MASTER's
      `.stop()`/atexit path can report a clean exit while an orphaned,
      unmarked WORKER it never got the chance to signal still listens on
      the ledger's own listen port -- `_stop_best_effort` confirms every
      ledgered port is actually free (`_port_has_listener`) before
      removing the ledger/base dir; if any is still listening, the ledger
      is left in place for the CI residue check (i) to find, and `.stop()`
      raises instead of returning as though nothing were wrong.

Nothing in this module has contract-level meaning (design U-4's own
ruling: "プロセス管理は契約上の意味を持たない試験基盤である") -- it is
shared directly between the two peers' conformance plugs, unlike peer
`src/`/`tests/` code, which the peer-independence regulation (P-6) does
bind.

`skip` is never a valid outcome anywhere in this module: a missing nginx
binary, a conf that fails `nginx -t`, or a surface that never becomes
ready within its budget all raise `HarnessStartupError` (design D-3,
`OPERATING_CONDITIONS.md` section 1.3 item 26 -- "an environment that
could not be checked" is never recorded as "passed").
"""
from __future__ import annotations

import atexit
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, List, Mapping, Optional, Sequence

import uvicorn

# ---------------------------------------------------------------------------
# Budgets (design D-1 (A) 5, D-2 (a))
# ---------------------------------------------------------------------------

#: Upper bound for ONE upstream (one uvicorn, dialed through its own nginx
#: `location`) to answer `GET .../capabilities` with an HTTP status < 500.
#: Design D-1 (A) 5.
UPSTREAM_READY_TIMEOUT_S = 30.0

#: Upper bound for a whole SURFACE (2 uvicorn upstreams + 1 nginx) to reach
#: readiness on both upstreams. Independent of, and smaller in practice
#: than, "2 * UPSTREAM_READY_TIMEOUT_S" -- design D-2 (a): "面としての上限
#: は別に要る". Both budgets are enforced; whichever elapses first fails
#: the surface.
SURFACE_STARTUP_BUDGET_S = 60.0

#: `proxy_read_timeout` for the rendered conf (design D-3): must exceed
#: every registered peer's own `execution_ms` default (5_000 ms, both
#: r2db-api's `ResourceLimits.execution_ms` and MitateDB-api's
#: `FoundationConfig.max_execution_ms`) with a real margin, never merely
#: equal to it.
DEFAULT_PROXY_READ_TIMEOUT_S = 20

#: Literal substring every `RealSocketSurface`-started nginx process's own
#: command line carries (design D-11 (2), D-2 (f)) -- always the final
#: path segment of the prefix directory passed to `nginx -p`, regardless
#: of what base directory a caller supplies. A CI/completion-gate residue
#: check greps process listings for this one marker rather than a bare
#: `nginx`, which would also match an unrelated process on a shared
#: runner/dev machine.
NGINX_PREFIX_MARKER = "conformance-socket-harness"


class HarnessStartupError(RuntimeError):
    """Raised on any startup failure this harness detects -- a missing
    nginx binary, an invalid conf, a surface that exceeds its startup
    budget. Never caught anywhere in this module or its callers and
    converted to a skip (design D-3, `OPERATING_CONDITIONS.md` section 1.3
    item 26)."""


# ---------------------------------------------------------------------------
# (c) free port
# ---------------------------------------------------------------------------


def free_port() -> int:
    """Returns a currently-unused loopback TCP port. Bind-and-release: the
    port is genuinely free at the instant of this call, subject to the
    ordinary TOCTOU window any such primitive has -- the caller binds it
    again (via uvicorn/nginx) immediately afterward."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@dataclass
class ReservedPort:
    """A loopback TCP port bound and LISTENING immediately (monitor 裁定
    2026-09-08, F-2 (a)) -- unlike `free_port` (bind-and-release, a pure
    TOCTOU-bounded number), this keeps the real listening socket open and
    claimed until `.sock` is handed to a real server (`start_uvicorn_
    thread`'s own `reserved=` parameter passes it straight to `uvicorn.
    Server.run(sockets=[...])`) or `.close()` is called. This is what lets
    a caller commit a REAL, already-owned port number to a `_surfaces_
    value()` URL at COMPOSITION time -- before the server that will answer
    on it has even started (design D-2 (g)'s own lazy-startup requirement
    still holds: nothing here spawns a process, only a bare `socket.bind`+
    `listen`, the same primitive `free_port` already uses)."""

    port: int
    sock: socket.socket

    def close(self) -> None:
        with _suppress(OSError):
            self.sock.close()


def reserve_port() -> ReservedPort:
    """Binds and LISTENs on a fresh loopback port, returning both the port
    number and the live socket (monitor 裁定 2026-09-08, F-2 (a)). The
    caller owns the returned socket: either hand it to `start_uvicorn_
    thread(..., reserved=...)` (which passes it straight to uvicorn's own
    `Server.run(sockets=[...])`, so uvicorn never re-binds) or call `.close()`
    to release it unused."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    return ReservedPort(port=sock.getsockname()[1], sock=sock)


def _port_has_listener(port: int, *, host: str = "127.0.0.1") -> bool:
    """`True` when something is currently listening on `host:port` --
    tested by attempting our OWN bind (with `SO_REUSEADDR`, the same
    option `free_port`/`reserve_port` already set): a bind that FAILS
    (`OSError`, address in use) means a real listener still holds the
    port; a bind that SUCCEEDS means nothing does (and this function
    releases it again immediately, `SO_REUSEADDR` never lets it linger).
    Used by `RealSocketSurface._stop_best_effort` (N-1 差し戻し, 監督裁定
    2026-09-08) to confirm every port this surface ever claimed has
    genuinely been released before removing that surface's own port
    ledger/base dir -- `.stop()` on the surface's OWN handles can return
    without error while an ORPHANED nginx WORKER (left behind by a
    SIGKILL on the master, which gets no chance to signal its own
    children) still answers on the listen port; this is what catches
    that case instead of silently trusting the handles' own exit codes."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host, port))
        except OSError:
            return True
        return False


# ---------------------------------------------------------------------------
# (b) nginx -- binary discovery, conf rendering, `-t`, process management
# ---------------------------------------------------------------------------


def find_nginx_binary() -> str:
    """`NGINX_BIN` env or PATH (design D-3). Raises `HarnessStartupError`
    -- never skips -- when neither resolves: nginx is a required
    dependency of this harness, not an optional one (design D-3, `A-6`
    rejects the "skip if nginx is absent" alternative)."""
    env_bin = os.environ.get("NGINX_BIN")
    if env_bin:
        if shutil.which(env_bin) or Path(env_bin).is_file():
            return env_bin
        raise HarnessStartupError(
            f"NGINX_BIN={env_bin!r} does not resolve to an executable file"
        )
    found = shutil.which("nginx")
    if found:
        return found
    raise HarnessStartupError(
        "nginx is a required dependency of the conformance socket harness "
        "(design D-3) and was not found via the NGINX_BIN environment "
        "variable or PATH; this is a hard failure, never a skip "
        "(OPERATING_CONDITIONS.md section 1.3 item 26)"
    )


# Rendered with `str.format`; nginx's own braces are doubled below.
# Mirrors `r2db-api/deploy/nginx/r2dbsvc-api-8443.conf.example`'s two
# `location` blocks (proxy_pass / proxy_http_version 1.1 / Host /
# X-Real-IP / X-Forwarded-For / X-Forwarded-Proto / X-Request-Id "" on
# both), TLS removed (design D-3, section 4 A-8: "conformance に TLS を
# 張る" is out of scope here) and listen/upstream/paths and the prefix-
# scoped process directives (design D-2 (b)) substituted in.
# `Host` is `$http_host` (the client's own `Host` header, port included),
# not `$host` (the name alone, as the example carried until ledger R-121):
# the upstream builds a redirect's `Location` from the `Host` it receives,
# and the surface's declared base URL carries a non-default port, so with
# `$host` a client that followed the upstream's own trailing-slash redirect
# would be sent to the scheme's default port -- another service than the
# one it dialed. Measured over both socket plugs and both `location`s by
# `test_wire_entry.py::test_socket_redirect_location_keeps_the_declared_authority`.
_NGINX_CONF_TEMPLATE = """\
pid {pid_path};
error_log {error_log_path};
worker_processes 1;

events {{
    worker_connections 128;
}}

http {{
    access_log off;
    client_body_temp_path {client_body_temp_path};
    proxy_temp_path {proxy_temp_path};

    # design D-3: 0 (unlimited) rather than a finite generous value --
    # `request_bytes` may move without this conf needing to track it; the
    # app's own `RequestByteBoundMiddleware`-equivalent is always the one
    # deciding, never nginx's own 413. Load-bearing together with the two
    # temp-path directives above: an unlimited body is always buffered to
    # a temp FILE once it exceeds nginx's in-memory buffer, so without an
    # explicit, writable-by-this-user temp path, a large body would 500 at
    # nginx's own compiled-in (often root-owned) default location instead
    # of reaching the app at all.
    client_max_body_size {client_max_body_size};

    server {{
        listen 127.0.0.1:{listen_port};

        location /v1/ {{
            proxy_pass http://127.0.0.1:{data_port};
            proxy_http_version 1.1;
            proxy_set_header Host $http_host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $remote_addr;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_set_header X-Request-Id "";
            proxy_read_timeout {read_timeout}s;
        }}

        location /control/v1/ {{
            proxy_pass http://127.0.0.1:{control_port};
            proxy_http_version 1.1;
            proxy_set_header Host $http_host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $remote_addr;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_set_header X-Request-Id "";
            proxy_read_timeout {read_timeout}s;
        }}

        location / {{
            return 404;
        }}
    }}
}}
"""


def render_nginx_conf(
    *,
    prefix: Path,
    listen_port: int,
    data_port: int,
    control_port: int,
    read_timeout_s: int = DEFAULT_PROXY_READ_TIMEOUT_S,
    client_max_body_size: str = "0",
) -> str:
    """Renders the conformance nginx conf (design D-2 (b) / D-3). `prefix`
    names an existing, writable-by-this-user directory; `pid`/`error_log`/
    the two temp paths are all placed directly under it (never left to
    nginx's own compiled-in defaults, which on a CI runner's non-root
    invocation name root-owned paths -- design D-2's own note)."""
    return _NGINX_CONF_TEMPLATE.format(
        pid_path=str(prefix / "nginx.pid"),
        error_log_path=str(prefix / "error.log"),
        client_body_temp_path=str(prefix / "client_body_temp"),
        proxy_temp_path=str(prefix / "proxy_temp"),
        client_max_body_size=client_max_body_size,
        listen_port=listen_port,
        data_port=data_port,
        control_port=control_port,
        read_timeout=read_timeout_s,
    )


def check_nginx_config(nginx_bin: str, conf_path: Path, prefix: Path) -> None:
    """`nginx -t` (design D-2 (b): "起動前に `nginx -t` を通す"). Raises
    `HarnessStartupError` with nginx's own stderr on failure -- called
    BEFORE any process is started, so an invalid conf never leaves a
    half-started surface behind."""
    result = subprocess.run(
        [nginx_bin, "-p", str(prefix), "-c", str(conf_path), "-t"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if result.returncode != 0:
        raise HarnessStartupError(
            f"nginx -t rejected the generated conf ({conf_path}):\n{result.stdout}"
        )


def _terminate_then_kill(process: subprocess.Popen, *, timeout_s: float = 10.0) -> None:
    """Unconditional stop (design D-2 (d)): SIGTERM, a bounded wait, then
    SIGKILL if still alive. Tolerates a process that already exited."""
    if process.poll() is not None:
        return
    try:
        process.send_signal(signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=timeout_s)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        process.kill()
    except ProcessLookupError:
        return
    with _suppress(subprocess.TimeoutExpired):
        process.wait(timeout=timeout_s)


def _terminate_then_kill_group(process: subprocess.Popen, *, timeout_s: float = 10.0) -> None:
    """Same unconditional stop discipline as `_terminate_then_kill` (design
    D-2 (d): SIGTERM, a bounded wait, then SIGKILL if still alive), but
    signals the WHOLE process GROUP via `os.killpg(process.pid, ...)`
    rather than `process`'s own pid alone -- correct ONLY because every
    caller (`UvicornSubprocessHandle.stop()`) started `process` with
    `start_new_session=True`, so `process.pid` is guaranteed to already be
    that group's own pgid (never some unrelated, pre-existing group this
    would otherwise blast). Reaches worker children a `--workers >= 2`
    supervisor forked -- `process.send_signal`/`.kill()` (this module's own
    `_terminate_then_kill`) only ever reach the supervisor itself, never
    its children, which would then be orphaned still serving on the
    now-stopped listener's own fd. Tolerates a group that is already gone
    (`ProcessLookupError` -- e.g. every member exited on its own) and one
    whose only remaining member(s) are zombies (`PermissionError` --
    `killpg` finds no live member left to actually signal, `sweep_
    orphans`'s own identical measured behavior above); a caller reaching
    this a second time (e.g. `restart()`'s own preflight failure, followed
    by its own `except: self.stop()`, followed by the ORIGINAL caller's
    own `stop()`) is exactly this shape, not a defect."""
    if process.poll() is not None:
        with _suppress(ProcessLookupError, PermissionError):
            os.killpg(process.pid, signal.SIGKILL)
        return
    with _suppress(ProcessLookupError, PermissionError):
        os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=timeout_s)
        return
    except subprocess.TimeoutExpired:
        pass
    with _suppress(ProcessLookupError, PermissionError):
        os.killpg(process.pid, signal.SIGKILL)
    with _suppress(subprocess.TimeoutExpired):
        process.wait(timeout=timeout_s)


class _suppress:
    """Minimal `contextlib.suppress` re-implementation kept local so this
    module has no import-order dependency on `contextlib` beyond the
    stdlib itself (kept trivial deliberately)."""

    def __init__(self, *exceptions: type[BaseException]):
        self._exceptions = exceptions

    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type, exc, tb) -> bool:
        return exc_type is not None and issubclass(exc_type, self._exceptions)


@dataclass
class NginxHandle:
    """A running nginx instance started via `start_nginx`."""

    process: subprocess.Popen
    prefix: Path
    conf_path: Path
    pidfile: Path

    def stop(self, *, timeout_s: float = 10.0) -> None:
        _terminate_then_kill(self.process, timeout_s=timeout_s)
        with _suppress(FileNotFoundError):
            self.pidfile.unlink()


def start_nginx(nginx_bin: str, conf_path: Path, prefix: Path) -> NginxHandle:
    """Starts nginx in the foreground (`-g 'daemon off;'`, design D-2 (b))
    so this harness's own `subprocess.Popen` handle is nginx's REAL master
    process, not a throwaway parent that immediately exits after forking
    nginx's own daemon -- the handle above must name a process this
    harness can actually terminate. `-e <prefix>/error.log` sets nginx's
    OWN startup-time error log (before it has even parsed the conf's
    `error_log` directive), so a conf parse failure before that directive
    takes effect is never written to nginx's compiled-in (often root-
    owned) default log path. Caller must have already run
    `check_nginx_config` -- this function does not re-check the conf."""
    pidfile = prefix / "nginx.pid"
    process = subprocess.Popen(
        [
            nginx_bin,
            "-p", str(prefix),
            "-c", str(conf_path),
            "-e", str(prefix / "error.log"),
            "-g", "daemon off;",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # nginx itself writes its OWN pidfile (the conf's `pid` directive) once
    # the master process is up; this harness also records the
    # `subprocess.Popen`'s own pid immediately, so `sweep_orphans` (f) has
    # something to read even if nginx crashes before writing its own file.
    pidfile.write_text(str(process.pid))
    return NginxHandle(process=process, prefix=prefix, conf_path=conf_path, pidfile=pidfile)


#: How long to wait, after `start_nginx` returns, before deciding nginx is
#: genuinely up rather than mid-exit from a failed `bind()` (F-2 (a) 後半,
#: 監督裁定 2026-09-08). A lost bind race fails inside nginx's own
#: `bind()` syscall and the master exits almost immediately; this is
#: comfortably longer than that while staying small enough that a
#: successful start (the overwhelming common case, paid on every
#: `RealSocketSurface` in this file's own self-tests) is not meaningfully
#: slowed down.
NGINX_BIND_RETRY_CHECK_S = 0.3

#: R-44 Q-8 (依頼者裁定 2026-09-16): total number of bind attempts `start_
#: nginx_with_bind_retry` makes before giving up. The loop bound AND the
#: give-up check below are BOTH derived from this SAME constant (never a
#: separate literal `3` hardcoded at the give-up check) -- a give-up
#: condition hardcoded independently of the loop's own range would keep
#: firing at the SAME attempt number even if the range were later widened
#: (or narrowed), silently decoupling "how many attempts the loop can
#: make" from "when it actually gives up" -- exactly the shape a mutation
#: on the loop range alone would then fail to observe at all.
NGINX_BIND_MAX_ATTEMPTS = 3


def start_nginx_with_bind_retry(
    nginx_bin: str,
    prefix: Path,
    *,
    data_port: int,
    control_port: int,
    read_timeout_s: int = DEFAULT_PROXY_READ_TIMEOUT_S,
    client_max_body_size: str = "0",
    check_s: float = NGINX_BIND_RETRY_CHECK_S,
) -> "tuple[NginxHandle, int]":
    """F-2 (a) 後半差し戻し (監督裁定 2026-09-08): reserves nginx's OWN
    listen port via `reserve_port()` -- bind AND listen immediately, then
    `.close()` right before rendering the conf (a narrower TOCTOU window
    than `free_port()`'s bind-only release, though still not zero: nginx
    itself does the real, later `bind()`) -- renders the conf, runs the
    mandatory `nginx -t` (`check_nginx_config`, unconditionally, on EVERY
    attempt including the retry -- design D-2 (b) never has an exception
    for a retried attempt), and starts nginx.

    A lost bind race is detected by WATCHING `error.log` during `check_s`
    for nginx's own `bind() to ... failed` line -- measured directly
    against this repository's own installed nginx: on `EADDRINUSE` nginx
    logs that line INSTANTLY (a syscall failure, no delay) but then
    retries the bind SEVERAL more times with ~500ms sleeps between
    attempts before actually giving up and exiting on its own (several
    real seconds later) -- waiting OUT that whole internal retry-and-
    give-up sequence on every genuine collision would make `check_s`
    (paid, if only as a `time.sleep`-shaped cost, on every SUCCESSFUL
    surface start too -- the overwhelmingly common case) far too
    expensive. Detecting the FIRST log line instead and proactively
    killing nginx right then (rather than waiting for its own internal
    retries to exhaust) is what lets `check_s` stay small. If nginx exits
    on its own within `check_s` for any OTHER reason, that is treated
    identically (a failure -- `process.poll() is not None`).

    Either way, this function retries EXACTLY ONCE on a freshly reserved
    port. A second failure raises `HarnessStartupError` with the failed
    attempt's own `error.log` contents; there is no third attempt (裁定の
    文言どおり「1 回だけ」).

    【追記 2026-09-16、R-44 Q-8(依頼者裁定)】上の「EXACTLY ONCE」/「1 回だ
    け」は 2026-09-08 時点の裁定の記録として残す。裁定は同日 R-44 Q-8 で改
    訂され、以下は **3 回** まで試行する。失敗した試行ごとの `error.log`
    は `error.attempt<N>.log`(`prefix` 配下)として個別に残る -- 次の試行
    の開始時に `error.log` 自体は毎回truncateされるが(同じ理由: 前の試行
    の "bind() ... failed" 行を次の試行の判定が誤検知しないため)、その直
    前に読み取った内容は上書きされずに退避される。3 回目の失敗で送出する
    `HarnessStartupError` は全試行分の `error.log` を含む。4 回目の試行は
    無い。"""
    failed_attempt_logs: list[str] = []
    for attempt in range(1, NGINX_BIND_MAX_ATTEMPTS + 1):
        reservation = reserve_port()
        listen_port = reservation.port
        reservation.close()  # bind/close reservation -- narrows, does not eliminate, the TOCTOU window

        conf_path = prefix / "nginx.conf"
        conf_text = render_nginx_conf(
            prefix=prefix,
            listen_port=listen_port,
            data_port=data_port,
            control_port=control_port,
            read_timeout_s=read_timeout_s,
            client_max_body_size=client_max_body_size,
        )
        conf_path.write_text(conf_text)
        check_nginx_config(nginx_bin, conf_path, prefix)  # nginx -t, every attempt, before start

        # Truncated (never merely left over from a PREVIOUS attempt) --
        # `-e <prefix>/error.log` names the SAME path on every attempt,
        # and nginx OPENS IT FOR APPEND, so a retry's own poll below would
        # otherwise see attempt 1's own already-logged "bind() ... failed"
        # line and misdiagnose attempt 2 (which may have genuinely
        # succeeded) as a repeat failure. The PREVIOUS attempt's own text
        # (if any) was already copied out to its own `error.attempt<N>.log`
        # below before this truncation runs.
        error_log = prefix / "error.log"
        error_log.write_text("")

        handle = start_nginx(nginx_bin, conf_path, prefix)
        bind_failed = False
        deadline = time.monotonic() + check_s
        while time.monotonic() < deadline:
            if handle.process.poll() is not None:
                bind_failed = True
                break
            if error_log.exists():
                try:
                    log_text = error_log.read_text()
                except OSError:
                    log_text = ""
                if "bind()" in log_text and "failed" in log_text:
                    bind_failed = True
                    break
            time.sleep(0.02)
        if not bind_failed:
            return handle, listen_port

        # Either nginx already exited on its own, or it logged a bind
        # failure and is mid-way through its own internal retry-and-
        # give-up loop -- terminate it NOW rather than waiting that out.
        _terminate_then_kill(handle.process, timeout_s=5.0)
        with _suppress(FileNotFoundError):
            handle.pidfile.unlink()
        attempt_log_text = error_log.read_text() if error_log.exists() else "(no error.log)"
        # R-44 Q-8 (依頼者裁定 2026-09-16): preserve THIS failed attempt's
        # own error.log under an attempt-numbered name -- never overwritten
        # by the next attempt's own truncate-then-retry above -- so a 3rd-
        # attempt exhaustion's final HarnessStartupError can quote every
        # attempt, not only the last.
        (prefix / f"error.attempt{attempt}.log").write_text(attempt_log_text)
        failed_attempt_logs.append(f"attempt {attempt} (port {listen_port}):\n{attempt_log_text}")
        if attempt == NGINX_BIND_MAX_ATTEMPTS:
            raise HarnessStartupError(
                f"nginx failed to bind a port even after {NGINX_BIND_MAX_ATTEMPTS} attempts on freshly "
                f"reserved ports -- error.log from every attempt:\n" + "\n\n".join(failed_attempt_logs)
            )
    raise AssertionError("unreachable")  # pragma: no cover


# ---------------------------------------------------------------------------
# (a) uvicorn -- thread version (socket adapters, WP-4) and subprocess
# version (C-26 launchers, WP-6c)
# ---------------------------------------------------------------------------


@dataclass
class UvicornThreadHandle:
    """A uvicorn server bound to a loopback port on a background thread
    inside THIS process."""

    server: "uvicorn.Server"
    thread: threading.Thread
    port: int
    # R-44 WP-3 (e), R-8: set only on the DEFAULT path (neither `reserved`
    # nor `port` given to `start_uvicorn_thread`) -- this handle then owns
    # the reservation `start_uvicorn_thread` minted for itself and closes
    # it in `stop()` below. `None` on every other path (a caller-supplied
    # `reserved`/`port` is never this handle's to close).
    _owned_reservation: Optional[ReservedPort] = field(default=None, repr=False)

    def stop(self, *, timeout_s: float = 10.0) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=timeout_s)
        if self.thread.is_alive():
            raise HarnessStartupError(
                f"uvicorn thread on port {self.port} did not stop within {timeout_s}s"
            )
        # R-8: idempotent -- uvicorn's own `Server.run(sockets=[...])`
        # already closes every socket it was handed as part of its own
        # shutdown (measured directly against this venv's installed
        # uvicorn), so this is very often closing an already-closed
        # socket; `ReservedPort.close()` suppresses `OSError`, and a
        # second call to THIS `stop()` (idempotent itself: `self.thread.
        # join()` on an already-joined thread is a safe no-op) closes the
        # same (already-closed) reservation again just as harmlessly.
        if self._owned_reservation is not None:
            self._owned_reservation.close()


def start_uvicorn_thread(
    app: Any,
    *,
    port: Optional[int] = None,
    reserved: Optional[ReservedPort] = None,
    start_timeout_s: float = UPSTREAM_READY_TIMEOUT_S,
    graceful_shutdown_s: float = 5.0,
) -> UvicornThreadHandle:
    """(a) thread-version uvicorn launcher -- used by the socket adapters
    (design D-1 (A)): `app` is the SAME composed ASGI app object the
    adapter already holds in-process (the composition itself never
    changes -- design D-1 (A) 1, "composition は既存 HTTP adapter と同一
    であり... 変わるのは transport だけ"), bound to a real loopback socket
    on a dedicated background thread so a real client (through nginx) can
    dial it.

    `reserved` (monitor 裁定 2026-09-08, F-2 (a)): when given, this is a
    `ReservedPort` (`reserve_port()`) whose ALREADY-bound, already-
    listening socket is handed straight to uvicorn's own `Server.run(
    sockets=[...])` -- uvicorn never calls `bind()` itself, so the port
    number the caller already committed elsewhere (e.g. a `_surfaces_
    value()` URL built before this function is even called) is
    GUARANTEED to be the one the server actually answers on. Mutually
    exclusive with `port` (an explicit `port=` with no `reserved` keeps
    the pre-existing bind-inside-uvicorn behavior).

    【追記 2026-09-16、R-44 WP-3 (e)、R-8】When BOTH `reserved` and `port`
    are omitted, this function now reserves its own port via `reserve_
    port()` (never `free_port()`'s bind-and-release) -- the same TOCTOU-
    closing behavior a caller-supplied `reserved` already gets, just
    minted here instead. The returned handle OWNS this reservation and
    closes it in `.stop()`. `free_port()` itself is unchanged and still
    used directly by this module's own health test
    (`test_socket_harness.py`'s `test_free_port_returns_a_bindable_port`).

    `graceful_shutdown_s` is uvicorn's own `timeout_graceful_shutdown`
    (its default, unset, is `None` -- an UNBOUNDED wait for in-flight
    requests to finish on `should_exit`, measured directly: a stalled
    handler otherwise keeps `UvicornThreadHandle.stop()` blocked
    indefinitely, which is exactly the "kill" this harness's own (d)
    responsibility exists to make unconditional). A real, finite value
    here is what lets `.stop()`'s own bounded `thread.join(timeout_s=...)`
    actually mean something."""
    owned_reservation: Optional[ReservedPort] = None
    sockets: Optional[List[socket.socket]]
    if reserved is not None:
        bound_port = reserved.port
        sockets = [reserved.sock]
    elif port is not None:
        bound_port = port
        sockets = None
    else:
        owned_reservation = reserve_port()
        bound_port = owned_reservation.port
        sockets = [owned_reservation.sock]
    # コードレビュー 1 回目差し戻し 2 (監督裁定 2026-09-16): `uvicorn.Config`/
    # `uvicorn.Server`/`Thread.start()` のいずれかが送出すると、それまでは
    # handle が返らないので `owned_reservation` を閉じる先が無く、予約した
    # ソケットが listen したまま漏れていた。ここから `return` までを 1 つの
    # `try` で囲み、`except BaseException:` で一元的に閉じてから re-raise
    # する(旧来 `server.started is False` の分岐にだけあった close はこの
    # 一元処理に統合し、重複させない)。
    try:
        config = uvicorn.Config(
            app, host="127.0.0.1", port=bound_port, log_level="warning", lifespan="off",
            timeout_graceful_shutdown=graceful_shutdown_s,
        )
        server = uvicorn.Server(config)
        thread = threading.Thread(
            target=lambda: server.run(sockets=sockets),
            name=f"socket-harness-uvicorn-{bound_port}", daemon=True,
        )
        thread.start()
        deadline = time.monotonic() + start_timeout_s
        while not server.started and time.monotonic() < deadline and thread.is_alive():
            time.sleep(0.02)
        if not server.started:
            server.should_exit = True
            thread.join(timeout=5.0)
            raise HarnessStartupError(
                f"uvicorn did not start on 127.0.0.1:{bound_port} within {start_timeout_s}s"
            )
    except BaseException:
        if owned_reservation is not None:
            owned_reservation.close()
        raise
    return UvicornThreadHandle(server=server, thread=thread, port=bound_port, _owned_reservation=owned_reservation)


@dataclass
class UvicornSubprocessHandle:
    """A uvicorn server running as a real, separate OS process -- used by
    the C-26 composition-root launchers (design D-1 (B)), which must start
    a peer's `<peer>.main:app`/`<peer>.control_main:app` with NO in-process
    hand held open at all.

    design D-1 (監督裁定 19/33): this process is ALWAYS its own
    session/process-group leader (`start_new_session=True` in `subprocess.
    Popen`, below), so `process.pid` doubles as this group's own pgid --
    true whether `workers` is 1 (a lone process, its own one-member group)
    or >= 2 (a uvicorn `Multiprocess` supervisor whose forked workers
    inherit that SAME pgid, never their own). `stop()` therefore signals
    the whole GROUP (`os.killpg`), not merely the supervisor's own pid --
    the only way to reach worker children uvicorn itself spawned."""

    process: subprocess.Popen
    port: int
    pidfile: Path
    # R-44 WP-3 (e), W44-3-10: set only on the DEFAULT path (`reserved`
    # omitted from `start_uvicorn_subprocess`) -- this handle then owns
    # the reservation and closes it in `stop()`. `None` when the caller
    # supplied its own `reserved=`: ownership stays with the caller (a
    # C-26 launcher holds it for its whole lifetime so `restart()` can
    # reuse it -- W44-3-5), and this `stop()` never touches it.
    _owned_reservation: Optional["ReservedPort"] = field(default=None, repr=False)

    def stop(self, *, timeout_s: float = 10.0) -> None:
        _terminate_then_kill_group(self.process, timeout_s=timeout_s)
        with _suppress(FileNotFoundError):
            self.pidfile.unlink()
        if self._owned_reservation is not None:
            self._owned_reservation.close()


def start_uvicorn_subprocess(
    app_import_string: str,
    *,
    pidfile: Path,
    reserved: Optional[ReservedPort] = None,
    env: Optional[Mapping[str, str]] = None,
    cwd: Optional[Path] = None,
    workers: int = 1,
) -> UvicornSubprocessHandle:
    """(a) subprocess-version uvicorn launcher (design D-2: "subprocess版
    はC-26(B)が使う"). Launches `app_import_string` (e.g.
    "r2db_api.main:app") with `python -m uvicorn` (the shared venv's own
    interpreter, `sys.executable` -- never a bare `uvicorn` off PATH,
    which could resolve to a different environment) as a genuinely
    separate process. `pidfile` records this process' own pgid (see
    `UvicornSubprocessHandle`'s own docstring) for the startup-time orphan
    sweep (f); the caller is responsible for polling readiness via `wait_
    until_ready` -- this function only starts the process, it does not
    itself block on readiness (the two peers' own composition roots take
    different amounts of time to become reachable, and a caller may want
    to start both upstreams before waiting on either).

    design D-1 (監督裁定 19/26/27/33): `workers` (default 1) is
    ALWAYS passed as a literal `--workers <n>` argv pair -- even at the
    default, so a caller never depends on uvicorn's own bare-`--workers`-
    omitted default staying 1. `n >= 2` makes uvicorn start its own
    `Multiprocess` supervisor (`uvicorn/supervisors/multiprocess.py`) in
    THIS process, forking/spawning `n` worker children that inherit the
    `--fd` socket this function already binds below -- unaffected by
    `workers`, since `Config.bind_socket()` binds once, in the supervisor,
    before any worker exists. This process is started in its OWN new
    session (`start_new_session=True`) specifically so its pid is also a
    fresh pgid no other process could already belong to -- worker
    children (forked/spawned by the supervisor, never `setsid`'d
    themselves) inherit that SAME pgid, letting `stop()`/`sweep_orphans`
    reach every worker via one `os.killpg` even after uvicorn's own
    `restart_all()` has silently replaced one.

    【追記 2026-09-16、R-44 WP-3 (e)、W44-3-5、W44-3-10】`reserved` (a
    `ReservedPort` from `reserve_port()`) is handed to the child via
    `--fd <reserved.sock.fileno()>` + `pass_fds=(fileno,)` -- the SAME fd
    number in the child as in this process (`pass_fds` never renumbers),
    measured directly against this venv's installed uvicorn (F-16 spike,
    監督実施 2026-09-16): the child genuinely serves on it. Ownership of
    a CALLER-supplied `reserved` stays with the CALLER (W44-3-5's own
    deviation from design D-7's "parent closes its own copy after
    startup" -- a C-26 launcher's `restart()` needs the SAME reservation
    to still be open across a stop/start of this function, or the bind-
    race window a `port=<int>` re-bind used to leave would come back);
    this function/handle never closes it. When `reserved` is omitted,
    this function mints its OWN reservation via `reserve_port()` and the
    RETURNED HANDLE owns it (closed by `UvicornSubprocessHandle.stop()`).
    The former `port: Optional[int]` parameter is removed outright (W44-
    3-10, 監督裁定 2026-09-16): after W44-3-9 moved every real caller in
    this repository onto `reserved=`, no caller of this parameter was
    left, and keeping it would leave a bind-race-prone re-bind-by-number
    path selectable again in the future."""
    owned_reservation: Optional[ReservedPort] = None
    if reserved is not None:
        reservation = reserved
    else:
        reservation = reserve_port()
        owned_reservation = reservation
    bound_port = reservation.port
    fd = reservation.sock.fileno()
    # コードレビュー 1 回目差し戻し 2 (監督裁定 2026-09-16): `subprocess.
    # Popen`/`pidfile.write_text` のいずれかが送出すると、それまでは handle
    # が返らないので `owned_reservation` を閉じる先が無く、予約したソケッ
    # トが listen したまま漏れていた。ここから `return` までを 1 つの
    # `try` で囲み、`except BaseException:` で `owned_reservation is not
    # None` のときだけ閉じてから re-raise する。
    try:
        merged_env = dict(os.environ)
        if env:
            merged_env.update(env)
        process = subprocess.Popen(
            [
                sys.executable, "-m", "uvicorn", app_import_string, "--host", "127.0.0.1",
                "--fd", str(fd), "--workers", str(workers),
            ],
            env=merged_env,
            cwd=str(cwd) if cwd is not None else None,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            pass_fds=(fd,),
            # 裁定 19: a fresh session/process group, so
            # `process.pid` is also this group's own pgid -- see this
            # function's own docstring and `UvicornSubprocessHandle`'s.
            start_new_session=True,
        )
        # This process' own pid IS this group's own pgid (start_new_
        # session=True above) -- recording it is recording the pgid, not
        # merely "the child's pid", which is what `stop()`/`sweep_orphans`
        # need: a worker child uvicorn's own supervisor replaces later
        # (`Multiprocess.keep_subprocess_alive`/`restart_all`) never
        # invalidates this value, since it always inherits the SAME pgid
        # (裁定 33).
        pidfile.write_text(str(process.pid))
    except BaseException:
        if owned_reservation is not None:
            owned_reservation.close()
        raise
    return UvicornSubprocessHandle(process=process, port=bound_port, pidfile=pidfile, _owned_reservation=owned_reservation)


# ---------------------------------------------------------------------------
# readiness (design D-1 (A) 5)
# ---------------------------------------------------------------------------


def wait_until_ready(url: str, *, timeout_s: float = UPSTREAM_READY_TIMEOUT_S, label: str = "upstream") -> None:
    """Polls `GET url` with NO `Authorization` header until it answers
    with an HTTP status < 500 (design D-1 (A) 5: "status < 500. 期待は
    401"), or raises `HarnessStartupError` once `timeout_s` elapses.
    Deliberately real HTTP through whatever sits in front of `url`
    (nginx, in this harness's own use) -- a bare TCP connect would miss an
    app that fails to import/construct and answers every request with a
    500 (or never accepts the TCP connection nginx itself accepted on its
    behalf, in which case this simply keeps timing out and still fails
    correctly)."""
    deadline = time.monotonic() + timeout_s
    last_error: Optional[BaseException] = None
    while time.monotonic() < deadline:
        try:
            request = urllib.request.Request(url, method="GET")
            try:
                with urllib.request.urlopen(request, timeout=1.0) as response:
                    status = response.status
            except urllib.error.HTTPError as http_error:
                status = http_error.code
            if status < 500:
                return
            last_error = RuntimeError(f"{url} answered status {status} (>= 500)")
        except OSError as exc:
            last_error = exc
        time.sleep(0.05)
    detail = f" (last observation: {last_error!r})" if last_error is not None else ""
    raise HarnessStartupError(
        f"{label}: {url} did not answer with an HTTP status < 500 within {timeout_s}s{detail}"
    )


# ---------------------------------------------------------------------------
# (f) startup-time orphan sweep
# ---------------------------------------------------------------------------


def _process_cmdline(pid: int) -> str:
    """Best-effort full command line for `pid` as one string; `""` when it
    cannot be determined (already dead, permission denied, or -- treated
    identically -- a platform this falls through to `ps` for and `ps`
    itself finds nothing). Linux: reads `/proc/<pid>/cmdline` directly (its
    NUL-separated argv, joined with spaces) -- no subprocess. Anything
    else (this repository's own macOS dev machines included, which have no
    `/proc`): `ps -p <pid> -o command=`, a real subprocess, only reached
    where `/proc` does not exist."""
    proc_cmdline = Path(f"/proc/{pid}/cmdline")
    if proc_cmdline.exists():
        try:
            return proc_cmdline.read_bytes().replace(b"\x00", b" ").decode(errors="replace")
        except OSError:
            return ""
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        )
    except OSError:
        return ""
    return result.stdout.strip()


def _pids_with_pgid(pgid: int) -> list[int]:
    """Every currently-live pid whose OWN process group is `pgid`, read via
    `ps -e -o pid=,pgid=` -- unlike `os.getpgid(specific_pid)`, this finds
    every member of a group even when the ONE pid originally used to name
    that group (its former leader) has since exited: a pgid is a plain
    number the kernel keeps allocated as long as ANY member remains, not
    something tied to one specific still-living pid. Used by `sweep_
    orphans` to recognize a group whose OWN leader died (e.g. SIGKILLed)
    while worker children under the SAME pgid are still alive."""
    try:
        result = subprocess.run(
            ["ps", "-e", "-o", "pid=,pgid="], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        )
    except OSError:
        return []
    members: list[int] = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        try:
            member_pid, member_pgid = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        if member_pgid == pgid:
            members.append(member_pid)
    return members


def sweep_orphans(prefix_root: Path, *, marker: str = NGINX_PREFIX_MARKER) -> Sequence[int]:
    """Reads every `*.pid`/`*.pidfile` file directly under `prefix_root`
    and kills (SIGTERM, then SIGKILL if still alive after a short wait)
    the pid each one names -- but ONLY when that pid's own command line
    still contains `marker` (owner check, monitor 裁定 2026-09-08, F-4): a
    pidfile whose named pid has been REUSED by an unrelated process since
    the file was written is never signalled -- the stale pidfile RECORD is
    still removed either way, but a live process this harness does not
    recognize as its own is left running. Design D-2 (f): "自分の prefix
    配下の pidfile を見て孤児を kill する" -- a previous run of THIS
    harness that exited without running any Python cleanup at all (a
    killed process, an interpreter crash) leaves exactly this shape
    behind: a live process (still carrying this harness's own marker
    somewhere in its argv -- `NGINX_PREFIX_MARKER` for nginx, the default)
    and a pidfile naming it, both still under a prefix directory a fresh
    run is about to reuse or has just created. A parsed pid `<= 0` is
    treated as never ours, explicitly and before any owner check
    (監督裁定 2026-09-08 U-12 / external review 2 R-27): `os.kill(0, ...)`
    signals this whole process group and `os.kill(-1, ...)` every process
    this user may signal, so such a value is neither looked up via
    `_process_cmdline` nor ever passed to `os.kill` -- only the stale
    pidfile record is removed. Tolerates a pid that no longer exists
    (already dead -- `_process_cmdline` returns `""`, which never contains
    a non-empty `marker`, so this is handled by the SAME owner-check
    branch, not a separate code path) and a pidfile that races out from
    under this function. Returns the pids this call actually signalled
    (for tests to observe).

    Known gaps (review finding F14, measured, ruled: documented rather
    than papered over with a check that cannot actually work -- `OC`
    §1.12 の 71): a group whose recorded pid (its own former leader, a
    `start_uvicorn_subprocess` supervisor) has ITSELF already died --
    e.g. SIGKILLed directly, bypassing this harness -- while worker
    children it spawned survive under the SAME pgid is NOT recognized as
    ours and is never swept, even though live members remain. This
    function's own owner check reads only the recorded pid's own cmdline
    for `marker`; a real uvicorn worker's own cmdline (`multiprocessing-
    fork`) and the `multiprocessing` "spawn" start method's own
    `resource_tracker` helper process never carry this harness's own
    marker anywhere in their own argv, so checking a surviving member's
    cmdline instead of the (now-unreadable) leader's cannot establish
    ownership either -- there is no marker left anywhere in the group
    once its leader is gone. Closing this would need a different
    ownership record entirely (e.g. a marker written into the pidfile's
    own name/contents alongside the pgid, checked without depending on
    any one member's cmdline), not a code change to this owner check
    alone."""
    killed: list[int] = []
    if not prefix_root.exists():
        return killed
    pidfiles = list(prefix_root.glob("*.pid")) + list(prefix_root.glob("*.pidfile"))
    for pidfile in pidfiles:
        try:
            pid_text = pidfile.read_text().strip()
        except FileNotFoundError:
            continue
        if not pid_text:
            with _suppress(FileNotFoundError):
                pidfile.unlink()
            continue
        try:
            pid = int(pid_text.split()[0])
        except ValueError:
            with _suppress(FileNotFoundError):
                pidfile.unlink()
            continue
        if pid <= 0:
            # Never ours by construction: os.kill(0, ...) hits this whole
            # process group and os.kill(-1, ...) every process this user
            # may signal. Skip the owner check entirely -- do not even
            # look up its command line -- and just drop the stale record.
            with _suppress(FileNotFoundError):
                pidfile.unlink()
            continue
        leader_cmdline = _process_cmdline(pid)
        # `_pids_with_pgid` still finds every surviving group member (used
        # below, ONLY once ownership is already established from the
        # recorded pid's own cmdline, to decide whether a since-died
        # leader's own surviving children must be reached via `killpg`) --
        # it is NOT used to widen ownership itself (review finding F14,
        # this function's own docstring `Known gaps`): a surviving
        # member's cmdline never carries `marker` either, so checking it
        # cannot recognize a group whose leader already died.
        surviving_group_members = _pids_with_pgid(pid)
        if marker not in leader_cmdline:
            # Not (recognizably) ours: either already dead, or a DIFFERENT
            # process has since reused this pid. Never signal it -- only
            # the stale pidfile record is cleaned up.
            with _suppress(FileNotFoundError):
                pidfile.unlink()
            continue
        # A pidfile this recorded pid is ALSO the pgid of (i.e. it is its
        # OWN process group's leader) belongs to a `start_uvicorn_
        # subprocess` supervisor (this module's own `start_new_session=
        # True` guarantees pid == pgid for exactly those) -- signalling
        # the whole GROUP (`os.killpg`) is what reaches any worker
        # children it spawned, including one uvicorn's own `Multiprocess.
        # keep_subprocess_alive`/`restart_all` silently replaced after
        # this pidfile was written (a replacement child inherits the SAME
        # pgid, never a fresh one, so this stays correct across that
        # replacement). A pid that is NOT its own pgid (every OTHER
        # pidfile writer in this module -- nginx, started with no
        # `start_new_session`, shares the caller's own ambient group) is
        # never group-killed here: `os.getpgid(pid)` returning something
        # other than `pid` itself means signalling THAT group would reach
        # processes this harness does not own at all (potentially this
        # very interpreter).
        try:
            is_group_leader = os.getpgid(pid) == pid
        except ProcessLookupError:
            # A genuine TOCTOU race, not the leader-already-dead Known
            # gap above (ownership was JUST established from this SAME
            # pid's own, then-live cmdline, above) -- the leader died in
            # the brief window between that check and this one.
            # `killpg(pid, ...)` still reaches every surviving member
            # sharing that SAME pgid number (`surviving_group_members`,
            # checked non-empty here), so this is treated the same as "is
            # its own pgid", not as "nothing left to kill".
            is_group_leader = bool(surviving_group_members)
        try:
            if is_group_leader:
                os.killpg(pid, signal.SIGTERM)
            else:
                os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        else:
            killed.append(pid)
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    break
                except PermissionError:
                    # This loop's own call is `os.kill(pid, 0)`, never
                    # `killpg` -- measured on macOS (this repository's own
                    # dev machines): once every member of `pid`'s own
                    # group is a ZOMBIE (exited but not yet reaped by its
                    # real parent), `os.kill(pid, 0)` on the zombie leader
                    # itself still SUCCEEDS (a zombie's pid entry still
                    # exists), so a zombie-only group does NOT raise
                    # `PermissionError` here at all -- it runs the full 5s
                    # wait instead. The only way THIS `kill(pid, 0)` call
                    # raises `PermissionError` is a DIFFERENT, unrelated
                    # process now holding this reused pid (owned by
                    # another user) -- never "no live member to signal",
                    # which is what the escalation `killpg`'s own
                    # `PermissionError` (suppressed below) actually means.
                    # Treated the same as "gone" here too: this harness no
                    # longer owns whatever now holds this pid.
                    break
                time.sleep(0.05)
            else:
                # Same group-of-zombies-only shape the wait loop above
                # measures: the 5s deadline can be reached with the
                # leader still passing `kill(pid, 0)` (a zombie), and the
                # escalation `killpg`/`kill` below then raises the SAME
                # `PermissionError` for the SAME reason (no live member
                # left to signal).
                with _suppress(ProcessLookupError, PermissionError):
                    if is_group_leader:
                        os.killpg(pid, signal.SIGKILL)
                    else:
                        os.kill(pid, signal.SIGKILL)
        with _suppress(FileNotFoundError):
            pidfile.unlink()
    return killed


# ---------------------------------------------------------------------------
# (g) lazy startup -- the full "one surface" orchestration socket adapters
# use (design D-1 (A) / D-2)
# ---------------------------------------------------------------------------


@dataclass
class RealSocketSurface:
    """Orchestrates one full surface -- two uvicorn upstreams (data +
    control) fronted by one nginx reverse proxy, all loopback-only -- for
    a socket adapter (design D-1 (A)). Lazy (g): nothing binds a port or
    spawns a process until `.data_base_url`/`.control_base_url` is first
    read; a caller that never reads either property never starts
    anything.

    `data_app`/`control_app` are the SAME composed ASGI app objects the
    owning adapter already holds in-process -- this class only adds a
    real socket + reverse proxy in front of them, it never re-composes
    anything (design D-1 (A) 1).

    `surface_budget_s`/`upstream_timeout_s` default to the design's own
    real budgets (`SURFACE_STARTUP_BUDGET_S`/`UPSTREAM_READY_TIMEOUT_S`)
    and are overridable ONLY so this module's own self-tests
    (`test_socket_harness.py`) can exercise the enforcement path without
    each such test actually waiting out the real 60s/30s budgets -- every
    real caller (the socket adapters, WP-4) uses the defaults.
    """

    data_app: Any
    control_app: Any
    read_timeout_s: int = DEFAULT_PROXY_READ_TIMEOUT_S
    client_max_body_size: str = "0"
    surface_budget_s: float = SURFACE_STARTUP_BUDGET_S
    upstream_timeout_s: float = UPSTREAM_READY_TIMEOUT_S
    graceful_shutdown_s: float = 5.0
    work_dir: Optional[Path] = None

    _started: bool = field(default=False, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _data_handle: Optional[UvicornThreadHandle] = field(default=None, init=False, repr=False)
    _control_handle: Optional[UvicornThreadHandle] = field(default=None, init=False, repr=False)
    _nginx: Optional[NginxHandle] = field(default=None, init=False, repr=False)
    _prefix: Optional[Path] = field(default=None, init=False, repr=False)
    _base_url: Optional[str] = field(default=None, init=False, repr=False)
    _atexit_registered: bool = field(default=False, init=False, repr=False)
    # F-6 (監督裁定 2026-09-08): the `tempfile.mkdtemp(prefix="conf-socket-")`
    # base directory this instance created for itself (never set when the
    # caller supplied its own `work_dir` -- a caller-owned directory is
    # never removed by this class). `_stop_best_effort` removes it so a
    # real caller (WP-4's own socket adapter, one throwaway `mkdtemp` per
    # surface start) does not accumulate one leftover directory per surface
    # for the life of the process.
    _base_dir: Optional[Path] = field(default=None, init=False, repr=False)
    _owns_base_dir: bool = field(default=False, init=False, repr=False)
    # N-1 差し戻し (監督裁定 2026-09-08): every port `_start` ever recorded
    # to `ports.json` (nginx's own listen port plus both upstreams') --
    # kept on the instance, not just on disk, so `_stop_best_effort` can
    # confirm every one of them has a genuine listener before it removes
    # the ledger/base dir a CI residue check would otherwise rely on.
    _ports: List[int] = field(default_factory=list, init=False, repr=False)

    def _ensure_started(self) -> None:
        if self._started:
            return
        with self._lock:
            if self._started:
                return
            self._start()
            self._started = True

    def _start(self) -> None:
        deadline = time.monotonic() + self.surface_budget_s
        nginx_bin = find_nginx_binary()  # fails fast, before any process starts

        # `NGINX_PREFIX_MARKER` is always the LAST path segment of `prefix`,
        # regardless of what `work_dir` a caller supplies (this module's
        # own self-tests pass a `tmp_path`-derived one) -- every nginx
        # process this class starts therefore carries this literal
        # substring somewhere in its own `-p <prefix>`/`-c <prefix>/...`
        # command-line argv. This is what lets a residue check (the CI
        # `conformance` job's own end-of-job step, design D-11 (2)) find
        # every harness-started nginx by a `pgrep -f` on this ONE marker,
        # rather than a bare `pgrep nginx` that would also match an
        # unrelated nginx process on the same runner (design's own
        # "prefix でスコープしない pgrep は runner の無関係なプロセスに
        # 当たる").
        if self.work_dir is not None:
            base_dir = Path(self.work_dir)
            self._owns_base_dir = False
        else:
            base_dir = Path(tempfile.mkdtemp(prefix="conf-socket-"))
            self._owns_base_dir = True
        self._base_dir = base_dir
        prefix = base_dir / NGINX_PREFIX_MARKER
        prefix.mkdir(parents=True, exist_ok=True)
        (prefix / "client_body_temp").mkdir(parents=True, exist_ok=True)
        (prefix / "proxy_temp").mkdir(parents=True, exist_ok=True)
        self._prefix = prefix

        # (f) startup-time sweep: a no-op on a freshly minted prefix, but
        # load-bearing when a caller reuses `work_dir` across runs (this
        # class's own self-test does exactly that to observe sweeping).
        sweep_orphans(prefix)

        # Everything from here on holds a real OS resource (a thread bound
        # to a real port, a real nginx process) the instant it succeeds --
        # ANY failure partway through (a budget overrun, `nginx -t`
        # rejecting the conf, a readiness timeout) must tear down whatever
        # was already started before propagating, or a failed `_start()`
        # itself becomes a residue source (exactly the property the
        # completion-gate's own residue check exists to catch).
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise HarnessStartupError("surface startup budget exceeded before any process started")

            self._data_handle = start_uvicorn_thread(
                self.data_app, start_timeout_s=min(self.upstream_timeout_s, remaining),
                graceful_shutdown_s=self.graceful_shutdown_s,
            )
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise HarnessStartupError("surface startup budget exceeded starting the data uvicorn")

            self._control_handle = start_uvicorn_thread(
                self.control_app, start_timeout_s=min(self.upstream_timeout_s, remaining),
                graceful_shutdown_s=self.graceful_shutdown_s,
            )
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise HarnessStartupError("surface startup budget exceeded starting the control uvicorn")

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise HarnessStartupError("surface startup budget exceeded before nginx started")

            # F-2 (a) 後半差し戻し (監督裁定 2026-09-08): nginx's own
            # listen port is reserved (bind+listen, then close -- narrower
            # than a bare `free_port()`'s bind-only release) rather than
            # picked with `free_port()` directly, and a lost bind race
            # (another process, most plausibly a concurrent xdist worker's
            # own harness surface, claims the port between the
            # reservation's own close and nginx's own later real bind)
            # gets exactly ONE retry on a freshly reserved port --
            # `start_nginx_with_bind_retry`'s own docstring.
            # 【追記 2026-09-16、R-44 Q-8(依頼者裁定)】`NGINX_BIND_MAX_
            # ATTEMPTS`(= 3)回まで試行する形に改められた。`nginx -t`
            # still runs before every attempt, retry included (design D-2
            # (b) has no exception for a retried attempt).
            self._nginx, listen_port = start_nginx_with_bind_retry(
                nginx_bin, prefix,
                data_port=self._data_handle.port,
                control_port=self._control_handle.port,
                read_timeout_s=self.read_timeout_s,
                client_max_body_size=self.client_max_body_size,
            )
            if not self._atexit_registered:
                atexit.register(self._stop_best_effort)
                self._atexit_registered = True

            # F-3 (監督裁定 2026-09-08): every port this surface actually
            # ended up claiming (nginx's own REAL listen port -- the one
            # it is actually bound to after any F-2 (a) retry above, never
            # the first reservation if a retry occurred -- and both
            # upstreams'), recorded as a ledger under the SAME marker-
            # bearing `prefix` directory the residue check already scopes
            # to via `NGINX_PREFIX_MARKER` -- a CI/completion-gate residue
            # check can list every `ports.json` this job's harness runs
            # wrote (glob `<tmp>/conf-socket-*/conformance-socket-harness/
            # ports.json`) and confirm none of the recorded ports still
            # has a listener (`ss -ltn`), independent of and in addition
            # to the marker-scoped `pgrep` on the nginx MASTER process --
            # nginx rewrites a WORKER's own argv to `nginx: worker
            # process`, which carries no marker at all, so a killed
            # master that leaves an orphaned worker behind is invisible to
            # the pgrep-on-marker check alone (F-3's own review finding).
            # Kept on `self._ports` too (N-1 差し戻し, 監督裁定 2026-09-08),
            # not merely written to disk: `_stop_best_effort` reads it back
            # from the instance to confirm every one of these ports has
            # genuinely stopped listening before it removes this ledger.
            self._ports = sorted({listen_port, self._data_handle.port, self._control_handle.port})
            (prefix / "ports.json").write_text(json.dumps(self._ports))

            self._base_url = f"http://127.0.0.1:{listen_port}"

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise HarnessStartupError("surface startup budget exceeded before readiness checks began")
            wait_until_ready(
                f"{self._base_url}/v1/capabilities",
                timeout_s=min(self.upstream_timeout_s, remaining),
                label="data",
            )

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise HarnessStartupError("surface startup budget exceeded between data and control readiness")
            wait_until_ready(
                f"{self._base_url}/control/v1/capabilities",
                timeout_s=min(self.upstream_timeout_s, remaining),
                label="control",
            )
        except BaseException:
            try:
                self._stop_best_effort()
            except Exception:  # noqa: BLE001 - the ORIGINAL failure is what propagates
                pass
            raise

    @property
    def base_url(self) -> str:
        self._ensure_started()
        assert self._base_url is not None
        return self._base_url

    @property
    def data_base_url(self) -> str:
        return f"{self.base_url}/v1"

    @property
    def control_base_url(self) -> str:
        return f"{self.base_url}/control/v1"

    @property
    def started(self) -> bool:
        """Observability hook for tests (design (g)'s own non-vacuity
        requirement): `True` only after a real port/process has actually
        been touched, never merely after construction."""
        return self._started

    def stop(self) -> None:
        with self._lock:
            self._stop_best_effort()
            self._started = False

    def _stop_best_effort(self) -> None:
        errors: list[str] = []
        if self._nginx is not None:
            try:
                self._nginx.stop()
            except Exception as exc:  # noqa: BLE001 - report, never swallow
                errors.append(f"nginx: {exc!r}")
            self._nginx = None
        for attr in ("_data_handle", "_control_handle"):
            handle = getattr(self, attr)
            if handle is not None:
                try:
                    handle.stop()
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{attr}: {exc!r}")
                setattr(self, attr, None)
        # N-1 差し戻し (監督裁定 2026-09-08): the two handle-stop loops
        # above can each report a CLEAN exit (`.poll()`/thread-joined)
        # while a recorded port still has a real listener on it -- exactly
        # what happens when the nginx MASTER is SIGKILLed (no chance to
        # signal its own children) and a WORKER survives, still bound to
        # the listen port, still carrying no marker in its own argv
        # (nginx rewrites a worker's argv to the fixed string `nginx:
        # worker process`). `NginxHandle.stop()`/`UvicornThreadHandle.
        # stop()` only observe THEIR OWN handle's exit, never the actual
        # port -- so this checks every port `_start` ever recorded
        # (`self._ports`) directly, independent of what the handles
        # reported. Deliberately checked BEFORE the base-dir removal
        # below, and gates it: this ledger (`ports.json`, under
        # `self._prefix`, itself under `self._base_dir`) is exactly what a
        # CI/completion-gate residue check (F-3) reads to catch this
        # orphaned-worker shape -- silently removing it here (the
        # unconditional `rmtree` this replaces) would make the very
        # residue that check exists to catch invisible to it, in exactly
        # the run (a killed master) where the check matters most.
        residual_ports = [port for port in self._ports if _port_has_listener(port)]
        if residual_ports:
            errors.append(
                f"port(s) {residual_ports} still have a listener after stop() -- the port ledger "
                f"at {self._prefix} was intentionally NOT removed (N-1 差し戻し, 監督裁定 2026-09-08); "
                "this is the shape a SIGKILLed nginx master with a surviving, unmarked worker takes"
            )
        # F-6 (監督裁定 2026-09-08): remove the `mkdtemp` base directory
        # THIS instance created for itself -- never a caller-supplied
        # `work_dir` (`_owns_base_dir` is only ever `True` when `self.
        # work_dir is None` in `_start`), and never while `residual_ports`
        # above is non-empty (N-1). Best-effort and idempotent: a second
        # `_stop_best_effort()` call (e.g. both `.stop()` and the atexit
        # path) finds nothing left to remove.
        elif self._owns_base_dir and self._base_dir is not None:
            shutil.rmtree(self._base_dir, ignore_errors=True)
            self._owns_base_dir = False
        if errors:
            raise RuntimeError(f"socket_harness.RealSocketSurface.stop(): {'; '.join(errors)}")
