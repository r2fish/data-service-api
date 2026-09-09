"""r2db-api (socket+nginx+postgres) plug for the common conformance port --
the 5th plug (design `docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md` D-1
(A), work order WP-4a).

This is a *third* adapter for the r2db-api peer. Where
`conformance_adapter_r2db_http.py`'s `R2DBHttpConformanceAdapter` drives the
real ASGI app through `httpx.ASGITransport` (in-process, no real socket),
this module is that SAME class with only the transport layer replaced: a
real loopback TCP socket, fronted by a real nginx reverse proxy
(`conformance-tests/socket_harness.py`, design D-2/D-3). Composition
(`DataService`, `ControlAuthority`, real `PostgresCell`s against a real,
throwaway-provisioned local PostgreSQL 16 database, DB isolation via
`__init__`'s own admin-DSN bootstrap/advisory-lock/migration path) is
INHERITED UNCHANGED -- this file overrides only the three hooks
`conformance_adapter_r2db_http.py`'s `R2DBHttpConformanceAdapter` exposes
for exactly this purpose (design D-1 (A) 6, `docs/design/
CONFORMANCE_ADAPTER_V1.md` section 24.3): `_build_client`, `_surfaces_
value`, `_reset_surface_state`.

Module name matters: `conformance-tests/registry.json`'s new
`r2db-api-socket` entry declares this module as
`conformance_adapter_r2db_socket`; `conftest.py` discovers it the same way
it discovers `conformance_adapter_r2db_http` -- by adding `r2db-api/
conformance/`'s directory to `sys.path` (already done by the time this
entry is processed, since `r2db-api`'s own entry precedes this one in
registry.json) and a plain `importlib.import_module(...)`.

Why a custom surface class instead of `socket_harness.RealSocketSurface`
(design `CONFORMANCE_ADAPTER_V1.md` section 24.3: "RealSocketSurface is
ONE way to satisfy this hook's contract, not the contract itself"):

  - `_surfaces_value()` (no `app` parameter) is called from WITHIN
    `R2DBHttpConformanceAdapter.__init__` BEFORE either the data or the
    control ASGI app object exists yet (`DataService(..., surfaces=self.
    _surfaces_value())` composes the data app; `_build_control_stack`'s own
    `assemble_control_stack(..., surfaces=self._surfaces_value())` composes
    the control app) -- so whatever URL it reports must already be REAL and
    COMMITTED (design D-1 (A) 2/D-4: "自分のnginxのURL") before any server
    answering on it has started. `RealSocketSurface` only knows its own
    nginx listen port lazily, the first time `.base_url` is read (by
    design, so a worker that never touches this plug never starts a real
    process) -- there is no way to ask it "what port will you eventually
    use" without also triggering the real, eager startup `_surfaces_value`
    must not perform. `socket_harness.reserve_port()` (F-2 (a)) is the
    documented primitive for exactly this split: commit a real, already-
    owned port number now; start the real server on it later.
  - The control-plane app object is periodically REBUILT in place
    (`_privileged_control_send`'s own `_CONTROL_REBUILD_THRESHOLD`, a fresh
    `ControlPlaneService` for a fresh in-memory rate window) while this
    plug's own `surfaces.control.base_url` -- already reported by an
    earlier `_surfaces_value()` call, possibly already consumed by a C-19
    real dial -- must keep answering. `_DeclaredSocketSurface.rebind_app`
    below (WP-4c, item 4 fix) swaps the served app in place via a thin
    `_AppDispatch` indirection, WITHOUT restarting the upstream uvicorn or
    the nginx in front of it: an earlier revision of this method did
    restart both on every such rebuild, which required a fresh readiness
    poll against `/control/v1/capabilities` -- unauthenticated GETs that
    (measured, this WP) each consume one unit of the control plane's own
    global, pre-auth `control_requests_per_minute` window, causing a
    `LIMIT_EXCEEDED` cascade under `-n 5 --dist loadgroup` CPU contention.
    See `_AppDispatch`'s own docstring for the full trace.

Every construction site in the inherited `__init__`/`isolated_control_
surface`/`isolated_application_surface`/`hold_in_flight` that calls `self.
_build_client(app, base_url)` continues to work unmodified (design's own
"composition は既存 HTTP adapter と同一であり... 変わるのは transport だ
け") -- this file never touches `conformance_adapter_r2db_http.py` itself.

Design ambiguity carried forward, reported rather than silently resolved
(常設規律 5, `OPERATING_CONDITIONS.md` section 1.7 item 52's sibling
discipline for a decision outside this file's own discretion): design D-1
(A) 1 says the inherited DB-isolation machinery's throwaway PostgreSQL
prefix should become "socket用の別系統" (a separate lineage) from the HTTP
plug's own `r2dbhttp<hex>` family. `R2DBHttpConformanceAdapter.__init__`
bakes the literal `"r2dbhttp"` head directly into a local variable AND into
three module-level stale-artifact regexes (`_STALE_PLATFORM_DB_PATTERN`
etc.) that a subclass cannot parameterize without overriding `__init__` in
full (duplicating ~260 lines of real PostgreSQL bootstrap/advisory-lock/
migration code this WP's own charter forbids touching in the base file and
whose own hook-based, minimal-diff extraction WP-3 specifically did to
AVOID a second copy of exactly this logic). This file inherits `__init__`
unmodified instead, accepting the SAME literal prefix family as the HTTP
plug: concurrent construction of same-family instances is already the
EXISTING, tested behavior under `-n 5 --dist loadgroup` (`conftest.py`'s
own `_discover_and_build()` builds every registered adapter, `r2db-api-http`
included, on every worker), made safe by `secrets.token_hex(4)`'s own
32-bit-random suffix plus the session-scoped PostgreSQL advisory lock
`_sweep_stale_artifacts`'s own docstring documents (ledger item L2) --
mechanisms this file changes nothing about. Completion condition 7's own
non-vacuity test below exercises that inherited mechanism directly
(concurrent bootstrap of an HTTP-plug instance and a socket-plug instance)
rather than asserting a literal string difference this file does not
introduce. Flagged for supervisor review rather than either silently
duplicating `__init__` or silently leaving the property untested.
"""
from __future__ import annotations

import atexit
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

import httpx

# Same fallback-sys.path convention `conformance_adapter_r2db_http.py`
# itself uses, needed only when this file is exercised standalone (outside
# `conftest.py`'s own discovery, which already puts both `conformance-
# tests/` and this file's own directory on `sys.path`).
if "adapter" not in sys.modules:
    _conformance_tests = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "conformance-tests")
    )
    if os.path.isdir(_conformance_tests) and _conformance_tests not in sys.path:
        sys.path.insert(0, _conformance_tests)

import socket_harness  # noqa: E402 -- conformance-tests/socket_harness.py (WP-3)
from adapter import ConformanceAdapter  # noqa: E402

from conformance_adapter_r2db_http import R2DBHttpConformanceAdapter  # noqa: E402


class _AppDispatch:
    """WP-4c (2026-09-08, item 4 -- `control_requests_per_minute` cascade
    root cause): the ONE ASGI callable `socket_harness.start_uvicorn_
    thread` is ever handed for a given `_DeclaredSocketSurface`, forwarding
    every request to whichever real app object `rebind_app` currently
    designates (`self.app`, swapped in place).

    Without this indirection, `_DeclaredSocketSurface.rebind_app` had to
    STOP and RESTART the real uvicorn thread and the nginx in front of it
    every time the bound app object changed identity -- which happens on
    every `_privileged_control_send` periodic rebuild (`conformance_
    adapter_r2db_http.py`'s own `_CONTROL_REBUILD_THRESHOLD`, a fresh
    `ControlPlaneService` + fresh in-memory rate window every 40 privileged
    calls). Each such restart required a fresh `socket_harness.wait_until_
    ready` readiness poll against BOTH `/v1/capabilities` and `/control/
    v1/capabilities` -- real, unauthenticated GET requests. Measured
    (this WP): `r2db_api.control_plane.ControlPlaneService.capabilities`
    calls `self._check_rate()` BEFORE `self._authenticate(...)`
    (`r2db-api/src/r2db_api/control_plane.py:691-693`) -- so EVERY one of
    those readiness-poll GETs against `/control/v1/capabilities` consumes
    one unit of the control plane's own GLOBAL, pre-auth `control_
    requests_per_minute` window, the SAME window every ordinary
    control-plane test call also draws from. Under CPU contention (this
    dev machine running 5 xdist workers plus a second worktree's own
    concurrent suite, observed directly), a slow restart's own poll
    retries (every 50ms, up to 30s per endpoint) can burn most of a
    freshly-reset window's budget purely on self-inflicted polling before
    any real test assertion ever runs against it -- tripping
    `LIMIT_EXCEEDED` for whatever ordinary test happens to run next.
    Never present on the ASGI-transport plug (`httpx.ASGITransport` has no
    real process to restart or poll at all), which is why only this plug
    showed the cascade.

    Indirection removes the restart -- and therefore the poll -- from the
    app-swap path entirely: the real uvicorn thread and nginx process for
    a given surface start exactly ONCE (the first time that surface is
    dialed) and never again; `rebind_app` on an already-started surface
    becomes a plain attribute assignment, generating no HTTP traffic of
    any kind. `MitateDB-api-socket`'s own surface (`_AppSocketSurface`,
    `conformance_adapter_mitatedb_socket.py`) does not need the equivalent
    fix: it has no periodic control-app-rebuild mechanism at all
    (`conformance_adapter_mitatedb_http.py` carries no `_CONTROL_REBUILD_
    THRESHOLD`/`_privileged_control_send`), so its control app object
    never changes identity mid-session.
    """

    __slots__ = ("app",)

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        await self.app(scope, receive, send)


class _DeclaredSocketSurface:
    """One data-plane OR control-plane real socket surface, dedicated to a
    single ASGI app at a time: a real loopback nginx (its OWN listen port
    reserved EAGERLY at construction, before any app object need exist --
    see this module's own docstring) fronting a real uvicorn thread bound
    to that app. Both `location /v1/` and `location /control/v1/` in the
    rendered conf point at the SAME single upstream (`socket_harness.
    render_nginx_conf`'s own `data_port`/`control_port` parameters both
    given this surface's one upstream port) -- design `CONFORMANCE_
    ADAPTER_V1.md` section 24.3's own explicit permission: "this hook never
    requires... that a single shared nginx instance fronts two upstreams
    the way `RealSocketSurface` happens to compose them". Whichever path
    prefix the bound app does not itself implement simply 404s through the
    unused location -- never dialed by anything that uses this surface for
    its documented role.

    Lazy at the PROCESS/THREAD level (design D-2 (g)): the port NUMBER is
    committed the instant this object is constructed (`socket_harness.
    reserve_port()`, a bind+listen with no process spawned), but no uvicorn
    thread or nginx process starts until `.base_url` is first read (via
    `_LazySocketClient.send` below, itself deferred to the first real HTTP
    request a built client actually sends) or `rebind_app` is called on an
    already-started instance.
    """

    def __init__(self, *, label: str) -> None:
        self._label = label
        self._reservation: socket_harness.ReservedPort = socket_harness.reserve_port()
        self._declared_port: int = self._reservation.port
        self.declared_base_url = f"http://127.0.0.1:{self._declared_port}"
        self._app: Any = None
        self._dispatch: Optional[_AppDispatch] = None
        self._started = False
        self._uvicorn: Optional[socket_harness.UvicornThreadHandle] = None
        self._nginx: Optional[socket_harness.NginxHandle] = None
        self._base_dir: Optional[Path] = None

    def rebind_app(self, app: Any) -> None:
        """Associates this surface with `app`. Before the first real start,
        this only records `app` for `_ensure_started` to use. After a real
        start, this WP-4c (item 4) fix swaps `self._dispatch.app` in
        place -- see `_AppDispatch`'s own docstring for why an already-
        running surface never needs to stop/restart its real uvicorn/nginx
        just because the bound app object's identity changed (the
        control-plane periodic-rebuild path, design's own docstring
        above)."""
        if app is self._app:
            return
        self._app = app
        if self._dispatch is not None:
            self._dispatch.app = app

    @property
    def base_url(self) -> str:
        self._ensure_started()
        return self.declared_base_url

    def _ensure_started(self) -> None:
        if self._started:
            return
        if self._app is None:
            raise AssertionError(
                f"_DeclaredSocketSurface({self._label!r}): base_url read before rebind_app(app) was ever called"
            )
        deadline = time.monotonic() + socket_harness.SURFACE_STARTUP_BUDGET_S
        nginx_bin = socket_harness.find_nginx_binary()  # fails fast, before any process starts
        base_dir = Path(tempfile.mkdtemp(prefix="conf-socket-adapter-"))
        prefix = base_dir / socket_harness.NGINX_PREFIX_MARKER
        prefix.mkdir(parents=True, exist_ok=True)
        (prefix / "client_body_temp").mkdir(parents=True, exist_ok=True)
        (prefix / "proxy_temp").mkdir(parents=True, exist_ok=True)
        socket_harness.sweep_orphans(prefix)  # design D-2 (f): a no-op on a freshly minted prefix
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise socket_harness.HarnessStartupError(
                    f"{self._label} surface: startup budget exceeded before any process started"
                )
            # WP-4c (item 4): wrap in `_AppDispatch` rather than handing
            # `self._app` to uvicorn directly -- `rebind_app` on this
            # (now-started) surface swaps `self._dispatch.app` in place
            # instead of restarting this uvicorn thread/nginx process.
            self._dispatch = _AppDispatch(self._app)
            uvicorn_handle = socket_harness.start_uvicorn_thread(
                self._dispatch, start_timeout_s=min(socket_harness.UPSTREAM_READY_TIMEOUT_S, remaining),
            )
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise socket_harness.HarnessStartupError(
                    f"{self._label} surface: startup budget exceeded starting the upstream uvicorn"
                )
            # Commit the reservation now: bind-and-release narrows, but does
            # not eliminate, the TOCTOU window before nginx's own real
            # bind() (same trade-off `start_nginx_with_bind_retry` itself
            # accepts) -- unlike that harness function, this surface must
            # bind THIS EXACT port (already declared, possibly already
            # dialed by a caller), so there is no "pick a different port
            # and retry" fallback available; a lost race fails this
            # surface's startup loudly instead (design's own "skipは never
            # a valid outcome").
            self._reservation.close()
            conf_path = prefix / "nginx.conf"
            conf_text = socket_harness.render_nginx_conf(
                prefix=prefix, listen_port=self._declared_port,
                data_port=uvicorn_handle.port, control_port=uvicorn_handle.port,
            )
            conf_path.write_text(conf_text)
            socket_harness.check_nginx_config(nginx_bin, conf_path, prefix)  # nginx -t before start
            nginx_handle = socket_harness.start_nginx(nginx_bin, conf_path, prefix)
            atexit.register(self._stop_best_effort)

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise socket_harness.HarnessStartupError(
                    f"{self._label} surface: startup budget exceeded before readiness checks began"
                )
            socket_harness.wait_until_ready(
                f"{self.declared_base_url}/v1/capabilities",
                timeout_s=min(socket_harness.UPSTREAM_READY_TIMEOUT_S, remaining), label=f"{self._label}-v1",
            )
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise socket_harness.HarnessStartupError(
                    f"{self._label} surface: startup budget exceeded between readiness checks"
                )
            socket_harness.wait_until_ready(
                f"{self.declared_base_url}/control/v1/capabilities",
                timeout_s=min(socket_harness.UPSTREAM_READY_TIMEOUT_S, remaining), label=f"{self._label}-control",
            )

            self._uvicorn = uvicorn_handle
            self._nginx = nginx_handle
            self._base_dir = base_dir
            self._started = True
        except BaseException:
            try:
                self._stop_best_effort()
            except Exception:  # noqa: BLE001 -- the ORIGINAL failure is what propagates
                pass
            raise

    def stop(self) -> None:
        self._stop_best_effort()

    def _stop_best_effort(self) -> None:
        errors: list[str] = []
        if self._nginx is not None:
            try:
                self._nginx.stop()
            except Exception as exc:  # noqa: BLE001
                errors.append(f"nginx: {exc!r}")
            self._nginx = None
        if self._uvicorn is not None:
            try:
                self._uvicorn.stop()
            except Exception as exc:  # noqa: BLE001
                errors.append(f"uvicorn: {exc!r}")
            self._uvicorn = None
        if not self._started:
            # Never actually bound to a real server (construction failed,
            # or this surface was never dialed at all) -- release the bare
            # reservation instead of leaving it open.
            self._reservation.close()
        if self._base_dir is not None:
            shutil.rmtree(self._base_dir, ignore_errors=True)
            self._base_dir = None
        self._started = False
        if errors:
            raise RuntimeError(
                f"_DeclaredSocketSurface({self._label!r}).stop(): {'; '.join(errors)}"
            )


#: Never actually dialed -- `_LazySocketClient.send` below always rewrites
#: `request.url`'s scheme/host/port to the bound surface's real, lazily-
#: started address before the request leaves this client. Mirrors the
#: existing ASGI-transport plug's own `BASE_URL` module constant (a
#: likewise-never-resolved placeholder host), applied here so `httpx.
#: AsyncClient.__init__` has a syntactically valid `base_url` to store
#: without that construction itself triggering any real startup.
_PENDING_BASE_URL = "http://socket-pending.conformance.invalid"


class _LazySocketClient(httpx.AsyncClient):
    """Returned by `_build_client` below. Two properties the default ASGI-
    transport client (`httpx.AsyncClient(transport=httpx.ASGITransport(...))`)
    does not need and this real-socket override must supply itself:

    - Lazy dialing (design D-2 (g)): reading `surface.base_url` at
      CONSTRUCTION time (i.e. inside `_build_client`, called from within
      `R2DBHttpConformanceAdapter.__init__`) would force every registered
      adapter's own `__init__` -- run eagerly on every xdist worker,
      design's own note on `conftest.py`'s `_discover_and_build()` -- to
      start a real nginx+uvicorn pair even on a worker whose own tests
      never touch this plug. Overriding `send()` instead defers that first
      real dial to the first ACTUAL request any caller sends through this
      client.
    - A FRESH, one-shot `httpx.AsyncHTTPTransport` per `send()` call,
      never a persistent connection pool held on `self` across calls
      (unlike a plain `httpx.AsyncClient`'s own default behavior): measured
      directly (this WP), `isolated_application_surface()`'s inherited,
      unmodified body gives its own `copy.copy(self)` a BRAND NEW `iso.
      _loop = asyncio.new_event_loop()` while ALIASING `iso._control_
      client` -- the SAME client OBJECT the PARENT adapter already used,
      under the PARENT's OWN, different `self._loop`. A real TCP
      connection pool is loop-affine: httpcore/anyio's own internal
      synchronization primitives bind to whichever loop was actually
      running when a connection was first opened, so reusing one already-
      warmed persistent pool from a SECOND loop raises `RuntimeError:
      <Event...> is bound to a different event loop` the instant that
      second loop tries to read from it -- reproduced directly against the
      real control client (`a.capability_document()` from the parent,
      THEN `iso.capability_document()` reusing the same, now cross-loop,
      `_control_client`). An ASGI-transport client has no such state (no
      real connection at all, `ASGITransport` calls the app in-process
      fresh every request) -- this hazard is specific to a REAL socket.
      Opening a fresh transport per call means no state ever crosses a
      `send()` boundary, so it dials fresh, entirely within whichever loop
      is CURRENTLY running this particular call -- correctness over
      keep-alive reuse, an acceptable trade for a conformance suite (never
      the throughput-measuring perf harness, design D-12: "同一plugの版間
      差分のみを並記し plug間の比較はしない").
    - Optional surface teardown on `aclose()` (`stop_surface_on_close`):
      `True` only for a surface dedicated to a single caller that never
      shares it with a concurrently-running second client (`isolated_
      control_surface`'s own one-off control app, whose single `client`
      local variable is the only handle ever built against it) -- `aclose()`
      then also stops that surface's own uvicorn+nginx immediately, rather
      than letting it accumulate, unstopped, until the whole adapter's own
      final `close()`. `False` everywhere else: the two long-lived,
      adapter-scoped data/control surfaces; every one of `hold_in_flight`'s
      own short-lived clients built against the SAME shared data surface
      (stopping on the FIRST held request's own `aclose()` would sever the
      OTHER, still in-flight, held requests sharing that same surface); and
      an `isolated_application_surface()` copy's own dedicated data surface
      (`hold_in_flight` can be called ON such a copy too, with the same
      concurrent-sharing hazard) -- these are instead swept once, at the
      TRUE original adapter's own final `close()`, via `_all_socket_
      surfaces` (`R2DBSocketConformanceAdapter._register_surface`).
    """

    def __init__(self, surface: _DeclaredSocketSurface, *, stop_surface_on_close: bool) -> None:
        # `base_url=_PENDING_BASE_URL` only backs `build_request()`'s own
        # URL-joining logic -- the `transport=` this constructs (an
        # ordinary, default `httpx.AsyncHTTPTransport`, since none is
        # given) is NEVER dialed: `send()` below always opens its own,
        # separate, one-shot transport instead. `aclose()` still closes
        # this unused one (cheap: it never opened a real connection).
        super().__init__(base_url=_PENDING_BASE_URL)
        self._wp4a_surface = surface
        self._wp4a_stop_on_close = stop_surface_on_close

    async def send(self, request: httpx.Request, **kwargs: Any) -> httpx.Response:
        real_base = httpx.URL(self._wp4a_surface.base_url)  # lazy: first call only actually starts anything
        request.url = request.url.copy_with(scheme=real_base.scheme, host=real_base.host, port=real_base.port)
        transport = httpx.AsyncHTTPTransport()
        try:
            response = await transport.handle_async_request(request)
            await response.aread()  # fully materialize the body before this one-shot transport closes
            return response
        finally:
            await transport.aclose()

    async def aclose(self) -> None:
        try:
            await super().aclose()
        finally:
            if self._wp4a_stop_on_close:
                self._wp4a_surface.stop()


class R2DBSocketConformanceAdapter(R2DBHttpConformanceAdapter):
    """The r2db-api real-socket plug (design D-1 (A)): `R2DBHttpConformance
    Adapter`'s exact composition, fronted by a real loopback nginx instead
    of an in-process ASGI transport. See this module's own docstring for
    why a custom surface class, not `socket_harness.RealSocketSurface`,
    realizes the two hooks below."""

    # `"http"` is deliberately part of this string, not merely descriptive:
    # `test_c05_limit_declaration_agreement.py`'s own `_drive_requests_
    # per_minute` (allowlisted, `_ADAPTER_NAME_READ_ALLOWLIST`) computes
    # `already_consumed = 1 if "http" in adapter.name else 0` -- a
    # deliberately transport-specific (not peer-specific) correction for
    # "does authenticate() consume 1 unit of the SAME requests_per_minute
    # window this drive measures". This plug's inherited `authenticate()`
    # makes exactly that same real round trip (over a REAL socket, real
    # HTTP wire protocol, even more literally "http" than the ASGI-
    # transport plug's own in-process call) -- measured directly (this
    # WP): 49 successes at bound=50 confirm `already_consumed=1` applies
    # here too. Naming this plug so the SAME allowlisted heuristic already
    # covers it needs no change to that (out-of-WP-4a-scope) test file.
    name = "r2db-api (socket+nginx+http+postgres)"
    # design D-1 (A) 4 / CONFORMANCE_ADAPTER_V1.md section 24.1: the third
    # of the three closed-vocabulary values, declared by this plug alone.
    transport_kind = "socket"

    # Class-level defaults (never a real per-instance value until the first
    # `_surfaces_value()`/`_build_client()` call lazily creates one) --
    # mirrors `transport_kind`'s own "declare once, read via `self.`"
    # convention, but WITH a real default (`None`), unlike that bare
    # annotation: every instance legitimately starts in the same "nothing
    # built yet" state, there is no "forgot to declare" failure mode to
    # guard here.
    _data_surface: Optional[_DeclaredSocketSurface] = None
    _control_surface: Optional[_DeclaredSocketSurface] = None
    def _register_surface(self, surface: _DeclaredSocketSurface) -> None:
        # `self.__dict__.setdefault` (never a class-level mutable default):
        # a `copy.copy(self)` (isolated_application_surface) shallow-copies
        # this list REFERENCE, so a surface an isolated copy registers here
        # lands in the SAME list the ORIGINAL, long-lived adapter's own
        # `close()` sweeps below -- a deliberate safety net (F-3-style
        # belt-and-suspenders) alongside `_LazySocketClient.aclose()`'s own
        # immediate teardown for transient surfaces, not a substitute for
        # it: a surface whose owning client's `aclose()` never ran (an
        # exception mid-test skips it, say) is still swept exactly once
        # more at `close()` (`.stop()` is idempotent).
        surfaces = self.__dict__.setdefault("_all_socket_surfaces", [])
        surfaces.append(surface)

    def _ensure_declared_surfaces(self) -> None:
        if self.__dict__.get("_data_surface") is None:
            self._data_surface = _DeclaredSocketSurface(label="data")
            self._register_surface(self._data_surface)
        if self.__dict__.get("_control_surface") is None:
            self._control_surface = _DeclaredSocketSurface(label="control")
            self._register_surface(self._control_surface)

    def _surfaces_value(self) -> dict:
        """Override (design D-1 (A) 2/D-4): a real, dialable loopback URL
        -- this surface's OWN nginx -- instead of the inherited synthetic,
        non-dialable `_SURFACES` constant. Ports are committed (`socket_
        harness.reserve_port()`, inside `_DeclaredSocketSurface.__init__`)
        the first time this is called, which is BEFORE either app object
        exists (see this module's own docstring) -- no real process starts
        here, only the port numbers."""
        self._ensure_declared_surfaces()
        return {
            "data": {"base_url": f"{self._data_surface.declared_base_url}/v1"},
            "control": {"base_url": f"{self._control_surface.declared_base_url}/control/v1"},
        }

    def _build_client(self, app: Any, base_url: str) -> httpx.AsyncClient:
        """Override (design D-1 (A) 1/6): every call site inherited from
        `R2DBHttpConformanceAdapter` (`__init__`'s own data/control
        clients, the control-plane rebuild path, `isolated_control_
        surface`, `isolated_application_surface`, `hold_in_flight`'s own
        held requests) reaches this. `base_url` (the module's synthetic
        `BASE_URL` constant) is ignored, same as the inherited default
        body already does -- see that method's own docstring for why.

        Role is inferred from identity against `self._app`/`self._control_
        app`, both of which the inherited call sites always assign BEFORE
        calling `self._build_client(...)` for them (`__init__:1118-1120`,
        `:1186-1187`, `_privileged_control_send`'s own rebuild): matching
        `self._app` reuses (or, on a control-plane rebuild, in-place
        RE-DISPATCHES -- WP-4c item 4: no restart, see `_AppDispatch`'s own
        docstring) the ONE data surface this instance holds (`self.
        _data_surface` -- the shared, long-lived one for the original
        adapter; an isolated copy's own dedicated one instead, per `_reset_
        surface_state` below); matching `self._control_app` does the same
        for `self._control_surface`. `_DeclaredSocketSurface.rebind_app` is
        itself already a no-op when handed the SAME app object again (see
        that method), so every REPEAT call for a role already bound --
        `hold_in_flight`'s own several concurrent held requests included --
        simply reuses the one real, already-running upstream that role's
        surface fronts: this hook's only job is routing an inherited call
        site to a real socket instead of an in-process ASGI transport
        (monitor 裁定 2026-09-08, superseding an earlier revision of this
        method that additionally spun up a dedicated, one-off uvicorn+nginx
        pair for every such repeat call -- an extension `docs/design/
        PHASE10_DEPLOYMENT_EVIDENCE_V1.md` D-1 (A) never specified; ruled
        out-of-design and removed). `DataService`'s own in-memory
        `concurrency` counter (the thing `hold_in_flight` exists to
        observe, design D-12) lives on the ONE shared `self._app`/`self.
        _service` object regardless of how many transports dial it, so
        nothing here needs a per-request surface to observe it correctly.

        Anything else (a fresh, ad-hoc app from `isolated_control_surface`)
        gets its own dedicated, throwaway surface, stopped the instant its
        own client's `aclose()` runs."""
        self._ensure_declared_surfaces()
        if app is getattr(self, "_app", None):
            self._data_surface.rebind_app(app)
            return _LazySocketClient(self._data_surface, stop_surface_on_close=False)
        if app is getattr(self, "_control_app", None):
            self._control_surface.rebind_app(app)
            return _LazySocketClient(self._control_surface, stop_surface_on_close=False)
        surface = _DeclaredSocketSurface(label="transient")
        surface.rebind_app(app)
        self._register_surface(surface)
        return _LazySocketClient(surface, stop_surface_on_close=True)

    def _reset_surface_state(self) -> None:
        """Override (monitor 裁定 2026-09-08, F-2 (b); design D-1 (A) 6
        point (c)): called on `isolated_application_surface()`'s own fresh
        `copy.copy(self)`, immediately after the copy and before that
        copy's own composition begins. `copy.copy` is shallow: without
        this, `iso._data_surface` would silently ALIAS the PARENT's own
        live, already-running data surface -- the isolated copy's own
        subsequent `iso._build_client(app, BASE_URL)` call (for its own
        fresh, isolated data app) would then `rebind_app` the PARENT's
        real nginx/uvicorn onto the isolated app, an in-place substitution
        that would leave the shared surface serving the WRONG app for
        every other concurrent/later user of it (exactly the failure design
        D-1 (A) 6 names: "隔離面が親の共有appをserveしたまま緑で通り C-05
        の隔離駆動が無音で誤る"). Setting `_data_surface = None` forces
        `_ensure_declared_surfaces()` to build this copy its OWN dedicated
        surface instead. `_control_surface` is deliberately left aliased --
        `isolated_application_surface()` never rebuilds the control plane
        at all (it stays genuinely shared/borrowed from the parent, per
        that method's own docstring), so nothing here should give it a
        separate one."""
        self._data_surface = None

    def close(self) -> None:
        try:
            super().close()
        finally:
            surfaces = list(self.__dict__.get("_all_socket_surfaces", []))
            errors: list[str] = []
            for surface in surfaces:
                try:
                    surface.stop()
                except Exception as exc:  # noqa: BLE001 -- report, never swallow
                    errors.append(repr(exc))
            if errors:
                raise RuntimeError(
                    "R2DBSocketConformanceAdapter.close(): socket surface stop() failure(s): "
                    + "; ".join(errors)
                )


def build_adapter() -> ConformanceAdapter:
    return R2DBSocketConformanceAdapter()
