"""MitateDB-api (socket) plug for the common conformance port -- the 6th
registry entry (Phase 10 WP-4b, `docs/design/PHASE10_DEPLOYMENT_EVIDENCE_
V1.md` D-1 (A)).

This is a *third* adapter for the same peer as `conformance_adapter_
mitatedb.py` (in-process) and `conformance_adapter_mitatedb_http.py`
(`httpx.ASGITransport`, no real socket): this module changes ONLY the
transport those two hooks (`_build_client`/`_surfaces_value`, WP-3,
`conformance-tests/socket_harness.py`) control -- the composition (data
service, control service, DB isolation, credential stores, limits) is
100% inherited, unchanged, from `MitateDBHttpConformanceAdapter` (design
D-1 (A) 1: "composition は既存 HTTP adapter と同一であり... 変わるのは
transport だけ"). Every `httpx.AsyncClient` this plug hands out dials a
REAL loopback TCP socket through a REAL nginx reverse proxy in front of a
REAL uvicorn thread serving the SAME composed ASGI app object the HTTP
plug would have served in-process -- real HTTP/1.1 framing, a real
proxy, real connection concurrency.

Independent implementation (P-6, mirrors `conformance_adapter_mitatedb_
http.py`'s own docstring convention): this file follows the same GENERAL
shape `r2db-api/conformance/conformance_adapter_r2db_socket.py` (WP-4a)
is expected to because both peers share the same conformance-harness
*pattern* by design decision (`docs/design/PHASE10_DEPLOYMENT_EVIDENCE_
V1.md` D-2, U-4), never because any of this file's own code was copied
from that one -- this file was written without reading WP-4a's own
output (parallel worktree, not yet merged as of this writing).

One real nginx+uvicorn PAIR per distinct composed ASGI app object
(`_AppSocketSurface` below), not one shared nginx fronting both planes:
`docs/design/CONFORMANCE_ADAPTER_V1.md` section 24.3 explicitly frees a
`transport_kind == "socket"` override from `conformance-tests/socket_
harness.py`'s own `RealSocketSurface` convenience shape ("this hook
never requires, and no caller may assume, that a single shared nginx
instance fronts two upstreams"). This shape is what lets `_surfaces_
value()` commit a REAL, already-reserved port number to the `data`/
`control` URLs it declares (needed synchronously, at `__init__` time,
well before either composed app object exists -- fed straight into the
`platform_declarations` DB row `_bootstrap_platform` seeds) without
requiring `conformance-tests/socket_harness.py`'s own `RealSocketSurface`
to accept an externally pre-committed listen port (it does not expose
one; its own listen port is chosen internally, only once `_start()`
actually runs). Reusing `conformance-tests/socket_harness.py`'s own
PUBLIC primitives directly (`reserve_port`, `render_nginx_conf`, `check_
nginx_config`, `start_nginx`, `start_uvicorn_thread`, `wait_until_ready`,
`NGINX_PREFIX_MARKER`, `HarnessStartupError`) needs no change to that
module at all -- see `_AppSocketSurface._start()` below.

Lazy (design D-2 (g)): `conformance-tests/conftest.py`'s own `_discover_
and_build()` builds EVERY registered adapter's Python object on EVERY
xdist worker, so this plug's own `reserve_port()` calls (cheap: a bare
loopback bind+listen, no process) happen on every worker regardless of
whether that worker's own tests ever touch "MitateDB-api-socket" -- this
is an unavoidable consequence of the (WP-3-approved, here left
unmodified) base class's own `__init__`, which always needs a concrete
`surfaces` value to seed the platform-declarations row. The actually
expensive resources -- the real uvicorn thread and the real nginx
subprocess -- stay fully deferred until the FIRST real HTTP request a
client this plug built ever sends (`_LazyDialTransport.handle_async_
request`), never merely at adapter-object-construction time.

Synthetic values only: every hostname here is a loopback literal
(`127.0.0.1`); no real hostname, credential, or deployment value is ever
written to this file (`CLAUDE.md` Public Repository Security Gate).
"""
from __future__ import annotations

import atexit
import os
import shutil
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

# Same bootstrap convention `conformance_adapter_mitatedb_http.py` already
# uses for `conformance-tests/adapter.py` -- `conformance-tests` also
# carries `conformance-tests/socket_harness.py` (WP-3), which this module
# needs directly (not merely transitively via the HTTP plug, which never
# imports it).
if "socket_harness" not in sys.modules:
    _conformance_tests_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "conformance-tests")
    )
    if os.path.isdir(_conformance_tests_dir) and _conformance_tests_dir not in sys.path:
        sys.path.insert(0, _conformance_tests_dir)

import socket_harness as sh  # noqa: E402

# `conformance_adapter_mitatedb_http` lives in THIS SAME directory
# (`MitateDB-api/conformance/`) -- `conftest.py`'s own `_discover_and_
# build()` already put this directory on `sys.path` (via the PRECEDING
# "MitateDB-api"/"MitateDB-api-http" registry entries, processed before
# whatever position this module's own "MitateDB-api-socket" entry occupies
# in `registry.json`'s array -- the identical bootstrap the HTTP plug's own
# module docstring already documents for itself, WP-0 m-1), but this import
# is written to be robust to being loaded standalone too (e.g. a future
# direct `import conformance_adapter_mitatedb_socket` from a script, not
# only from `conftest.py`).
if os.path.dirname(__file__) not in sys.path:
    sys.path.insert(0, os.path.dirname(__file__))

from conformance_adapter_mitatedb_http import MitateDBHttpConformanceAdapter  # noqa: E402

from adapter import ConformanceAdapter  # noqa: E402  -- return-type annotation only


class _AppSocketSurface:
    """One real loopback nginx process fronting one real loopback uvicorn
    thread that serves exactly ONE composed ASGI app object.

    Both of the rendered nginx conf's own locations (`/v1/` and
    `/control/v1/`, `conformance-tests/socket_harness.py::render_nginx_
    conf`) proxy to the SAME single upstream port here -- deliberately
    (design `docs/design/CONFORMANCE_ADAPTER_V1.md` section 24.3: "free to
    give EACH app its own dedicated uvicorn + its own dedicated nginx ...
    this hook never requires ... a single shared nginx instance fronts two
    upstreams"). Only one of the two locations is ever actually dialed for
    a given app (a data-shaped app only ever answers under `/v1/...`, a
    control-shaped app only under `/control/v1/...`); the other is simply
    never hit by anything that holds this surface's own `base_url`.

    Lazy (design D-2 (g)): `listen_reservation` (the port `base_url`
    commits to) is bound+listening from the moment this object is
    constructed -- cheap, no process -- but the real uvicorn thread and
    nginx subprocess this surface fronts are not started until `ensure_
    started()` is first called, from `_LazyDialTransport.handle_async_
    request` below, i.e. the first REAL request a client backed by this
    surface actually sends.

    Reference-counted (`acquire`/`release`): several distinct httpx
    clients can share the SAME surface over its lifetime -- `hold_in_
    flight`'s own N concurrently-held clients against the SAME `self._app`
    (`docs/design/CONFORMANCE_ADAPTER_V1.md` section 24.3's `hold_in_
    flight` note: a socket-adapter override of `_build_client` must reach
    `hold_in_flight`'s own held requests too) all share the ONE surface
    `MitateDBSocketConformanceAdapter._socket_surface_for` builds for
    `self._app`. The real server is stopped only once EVERY client that
    was ever handed this surface has closed (refcount reaches 0), never on
    the first one of several concurrent siblings to close.
    """

    def __init__(self, app: Any, listen_reservation: "sh.ReservedPort") -> None:
        self.app = app
        self._listen_reservation: Optional["sh.ReservedPort"] = listen_reservation
        self.base_url = f"http://127.0.0.1:{listen_reservation.port}"
        self._lock = threading.Lock()
        self._started = False
        self._refcount = 0
        self._uvicorn_handle: Optional["sh.UvicornThreadHandle"] = None
        self._nginx_handle: Optional["sh.NginxHandle"] = None
        self._base_dir: Optional[Path] = None
        self._atexit_registered = False

    def acquire(self) -> None:
        with self._lock:
            self._refcount += 1

    def release(self) -> None:
        with self._lock:
            self._refcount = max(0, self._refcount - 1)
            should_stop = self._refcount == 0 and self._started
        if should_stop:
            self.stop()

    def ensure_started(self) -> None:
        if self._started:
            return
        with self._lock:
            if self._started:
                return
            self._start()
            self._started = True

    def _start(self) -> None:
        nginx_bin = sh.find_nginx_binary()  # fails fast, before any process starts (design D-3)
        base_dir = Path(tempfile.mkdtemp(prefix="conf-socket-"))
        self._base_dir = base_dir
        prefix = base_dir / sh.NGINX_PREFIX_MARKER
        prefix.mkdir(parents=True, exist_ok=True)
        (prefix / "client_body_temp").mkdir(parents=True, exist_ok=True)
        (prefix / "proxy_temp").mkdir(parents=True, exist_ok=True)
        try:
            # The upstream (uvicorn) port is a plain, freely-chosen loopback
            # port (`start_uvicorn_thread`'s own `free_port()` fallback,
            # mirroring `RealSocketSurface`'s identical, harness-accepted
            # choice for its own two upstreams) -- only the EXTERNALLY
            # dialed `listen_port` below needs to be the specific number
            # `_surfaces_value()` already committed to a declared URL.
            # 【追記 2026-09-16、R-44 WP-3 (e)、R-8、監督裁定 W44-3-14】
            # `start_uvicorn_thread` の既定経路は `free_port()` ではなく
            # `reserve_port()` に改められた(`conformance-tests/socket_
            # harness.py` の `start_uvicorn_thread`)。この呼び出しに `port=`/
            # `reserved=` を渡していないこの1行は、いまは `reserve_port()`
            # で採番される。
            self._uvicorn_handle = sh.start_uvicorn_thread(self.app)

            assert self._listen_reservation is not None, "_AppSocketSurface._start() called twice"
            listen_port = self._listen_reservation.port
            # Close the reservation right before nginx's own real bind --
            # narrows (never eliminates) the TOCTOU window, the same
            # pattern `socket_harness.start_nginx_with_bind_retry` uses for
            # its OWN internally-chosen port. Unlike that helper, this
            # class does not retry on a lost bind race: the port number was
            # already committed to a declared `surfaces` value (and, for
            # the data/control slots, already baked into the platform-
            # declarations DB row) before this method ever runs, so
            # silently moving to a different port on retry would make the
            # declared value and the real listener disagree. A lost race
            # on a freshly reserved ephemeral port is rare enough in this
            # suite's own single-adapter-per-xdist-worker shape that a hard
            # failure (never a skip, design `OPERATING_CONDITIONS.md`
            # section 1.3 item 26) is the correct trade-off here; see this
            # WP's own completion report for the measured absence of any
            # such failure across the runs that produced it.
            self._listen_reservation.close()
            self._listen_reservation = None

            conf_text = sh.render_nginx_conf(
                prefix=prefix, listen_port=listen_port,
                data_port=self._uvicorn_handle.port, control_port=self._uvicorn_handle.port,
            )
            conf_path = prefix / "nginx.conf"
            conf_path.write_text(conf_text)
            sh.check_nginx_config(nginx_bin, conf_path, prefix)  # nginx -t, before start (design D-2 (b))
            self._nginx_handle = sh.start_nginx(nginx_bin, conf_path, prefix)
            if not self._atexit_registered:
                atexit.register(self.stop)
                self._atexit_registered = True

            # Readiness probe path is always `/v1/...` regardless of
            # whether this particular surface fronts a data-shaped or a
            # control-shaped app: `wait_until_ready`'s own criterion is
            # "HTTP status < 500" (design D-1 (A) 5), which a genuinely
            # broken (import/construction-failed) app fails on ANY path,
            # matched route or not, while a merely-unmatched route on a
            # healthy app cleanly answers 404 (< 500) -- so this probe
            # still proves "nginx + uvicorn + the app object are up and
            # answering over a real socket" for either app shape without
            # this class needing to know which shape `self.app` is.
            sh.wait_until_ready(f"{self.base_url}/v1/capabilities", label=f"mitatedb-socket-surface-{id(self.app)}")
        except BaseException:
            self._stop_best_effort()
            raise

    def stop(self) -> None:
        with self._lock:
            self._stop_best_effort()
            self._started = False

    def _stop_best_effort(self) -> None:
        errors: list[str] = []
        if self._nginx_handle is not None:
            try:
                self._nginx_handle.stop()
            except Exception as exc:  # noqa: BLE001 - report, never swallow
                errors.append(f"nginx: {exc!r}")
            self._nginx_handle = None
        if self._uvicorn_handle is not None:
            try:
                self._uvicorn_handle.stop()
            except Exception as exc:  # noqa: BLE001
                errors.append(f"uvicorn: {exc!r}")
            self._uvicorn_handle = None
        if self._listen_reservation is not None:
            self._listen_reservation.close()
            self._listen_reservation = None
        if self._base_dir is not None:
            shutil.rmtree(self._base_dir, ignore_errors=True)
            self._base_dir = None
        if errors:
            raise RuntimeError(f"_AppSocketSurface.stop(): {'; '.join(errors)}")


class _LazyDialTransport(httpx.AsyncBaseTransport):
    """The httpx transport `MitateDBSocketConformanceAdapter._build_client`
    hands back for every app. Constructing this (and the `httpx.
    AsyncClient` wrapped around it) touches no real process -- the real
    server behind it starts on the FIRST real request (design D-2 (g)).
    `aclose()` releases this ONE client's own reference on the shared
    surface (`_AppSocketSurface`'s own docstring); the real server is
    stopped only once every client sharing it has closed.

    A fresh `httpx.AsyncHTTPTransport()` (and its own real TCP connection)
    is opened and closed for EVERY single request, never held open and
    reused across requests -- measured directly (this WP's own first full-
    suite run against the base class, unmodified): `MitateDBHttpConformance
    Adapter.isolated_application_surface()` gives its own `iso` a FRESH
    `iso._loop` (`asyncio.new_event_loop()`) but deliberately does NOT
    rebuild `iso._control_client` (a shallow-copy alias of the SHARED
    surface's own, already-built one -- that method's own extensive
    comment: only the DATA-plane pieces are fresh, control stays shared by
    design). A REUSED `httpx.AsyncHTTPTransport`'s own underlying `httpcore`
    connection carries an `anyio`-backend `asyncio.Event` that binds itself
    to whichever event loop FIRST awaits it and then raises `RuntimeError:
    ... is bound to a different event loop` the instant a DIFFERENT loop
    (`iso._loop`, dialing the SAME shared `_control_client` object via
    `iso.control_credential()`/`scanning.control_credential()`) tries to
    reuse it -- `httpx.ASGITransport` (the default this hook replaces) has
    no such loop-bound state at all, so this cross-loop reuse was already
    latent in the base class's own design and simply never surfaced before
    a REAL socket transport (with a real, loop-affine `httpcore` connection)
    existed to expose it. Opening fresh per request trades away HTTP
    keep-alive between separate requests through the same long-lived
    client object for correctness across this pre-existing sharing pattern;
    see this WP's own completion report for the measured cost and the
    open question of whether `isolated_application_surface()` should
    instead give `iso` its own fresh control client too (out of this WP's
    own touch scope -- that method is inherited, unmodified, design D-1
    (A) 1).
    """

    def __init__(self, surface: _AppSocketSurface) -> None:
        self._surface = surface
        self._closed = False

    async def handle_async_request(self, request: "httpx.Request") -> "httpx.Response":
        self._surface.ensure_started()
        async with httpx.AsyncHTTPTransport() as real:
            response = await real.handle_async_request(request)
            # Force the body to be fully read (materialized into the
            # response object itself) BEFORE this `async with` block closes
            # `real` below -- a streaming response body read lazily by the
            # CALLER (outside this method, after `real` has already closed
            # its own connection) would otherwise fail or hang.
            await response.aread()
            return response

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._surface.release()


class MitateDBSocketConformanceAdapter(MitateDBHttpConformanceAdapter):
    """Connects the common conformance port to MitateDB-api's real HTTP +
    PostgreSQL stack over a REAL loopback socket, fronted by a REAL nginx
    reverse proxy (design D-1 (A)). Everything about the composition
    (data/control services, DB isolation, credential stores, limits,
    audit wiring) is inherited unchanged from `MitateDBHttpConformance
    Adapter` -- this subclass overrides only the three WP-3 hooks
    (`transport_kind`, `_build_client`, `_surfaces_value`) plus `_reset_
    surface_state` (design `docs/design/CONFORMANCE_ADAPTER_V1.md` section
    24.3) and `close` (to additionally stop the real OS resources this
    subclass's own hooks introduce, which the base class knows nothing
    about).
    """

    name = "MitateDB-api (socket)"
    # design D-1 (A) 4: a real loopback TCP socket, fronted by a real
    # reverse proxy (`conformance-tests/socket_harness.py`).
    transport_kind = "socket"

    # ------------------------------------------------------------------
    # hooks (design D-1 (A) 6 / WP-3)
    # ------------------------------------------------------------------

    def _surfaces_value(self) -> Dict[str, Dict[str, str]]:
        """Reserves (bind+listen, no process -- `socket_harness.reserve_
        port()`) the two REAL loopback ports this plug's own nginx
        instances will listen on, and declares them here -- called once,
        synchronously, from the base class's own `__init__` (`surfaces =
        self._surfaces_value()`) well before either composed ASGI app
        object exists, and its return value is baked directly into the
        `platform_declarations` DB row `_bootstrap_platform` seeds and
        into this instance's own `FoundationConfig` (the base class's own
        docstring on this hook). The reservations are held open
        (`self._data_listen_reservation`/`self._control_listen_
        reservation`) until each one's own `_AppSocketSurface` actually
        starts nginx on that exact port (`_AppSocketSurface._start`),
        which is what lets this method return the plug's own FINAL, real,
        dialable URL synchronously -- without ever needing `conformance-
        tests/socket_harness.py`'s own `RealSocketSurface` (whose listen
        port is chosen internally, only once IT starts) to expose a way to
        pre-commit an externally-chosen listen port.
        """
        self._ensure_socket_registry()
        data_port = self._reserve_named_port("_data_listen_reservation")
        control_port = self._reserve_named_port("_control_listen_reservation")
        return {
            "data": {"base_url": f"http://127.0.0.1:{data_port}/v1"},
            "control": {"base_url": f"http://127.0.0.1:{control_port}/control/v1"},
        }

    def _operation_catalog_url_value(self) -> str:
        """Override (design docs/design/PHASE11_MIN_COMMON_PROFILE_V1.md
        D-5): a real, dialable loopback URL against the SAME real nginx
        `_surfaces_value` above reserves the data-plane port for --
        `_reserve_named_port` is idempotent (returns the already-
        committed port on a second call), so this never allocates a
        second, independent port. C-29's stage (ii) dials THIS URL for
        real.

        Not cached (mirrors `conformance_adapter_r2db_socket.py`'s own
        identically-purposed sibling): a value cached
        in `self.__dict__` BEFORE `isolated_application_surface()`'s own
        `copy.copy(self)` runs is carried forward into the isolated
        copy's `__dict__` by that shallow copy, unaffected by `_reset_
        surface_state()`'s own port reservations. `_reserve_named_port`
        is itself idempotent, so re-deriving on every call is cheap and
        carries no risk of its own.

        Removing the cache here is NOT, by itself, what keeps the
        isolated copy's own DATA document from declaring the PARENT's
        port: `_application_config.operation_catalog_url` is a plain
        dataclass field, read verbatim at document-build time (never a
        live call to this hook) -- `isolated_application_surface()`'s own
        `replace(..., operation_catalog_url=iso._operation_catalog_
        url_value())` is what actually gives the isolated copy's config
        its own, freshly reserved value; this hook returning a fresh
        (never cached) value each time is what makes THAT explicit call
        observe the isolated copy's own port rather than a stale one."""
        self._ensure_socket_registry()
        data_port = self._reserve_named_port("_data_listen_reservation")
        return f"http://127.0.0.1:{data_port}/v1/operation-catalog"

    def _build_client(self, app: Any, base_url: str) -> httpx.AsyncClient:
        """Ignores the `base_url` argument (always this plug's own
        synthetic `BASE_URL` module constant, unchanged from the HTTP
        plug -- irrelevant here) and returns a client that dials `app`'s
        own dedicated real socket surface instead (`_socket_surface_for`).
        Every construction site the base class's own `__init__`/`close`/
        `isolated_control_surface`/`isolated_application_surface`/`hold_
        in_flight` realization already routes through this ONE hook
        (design D-1 (A) 6, `docs/design/CONFORMANCE_ADAPTER_V1.md` section
        24.3's own "every construction site... now goes through one of
        these hooks" list) -- this override never needs to touch any of
        those call sites itself.
        """
        self._ensure_socket_registry()
        surface = self._socket_surface_for(app)
        surface.acquire()
        return httpx.AsyncClient(transport=_LazyDialTransport(surface), base_url=surface.base_url)

    def _reset_surface_state(self) -> None:
        """Called on `isolated_application_surface()`'s own fresh `copy.
        copy(self)` instance, immediately after the copy and before that
        copy's own composition begins (design `docs/design/CONFORMANCE_
        ADAPTER_V1.md` section 24.3, monitor 裁定 2026-09-08 F-2 (b)).
        `copy.copy` is a SHALLOW copy: without this override, the isolated
        copy's own `_socket_surfaces`/`_data_listen_reservation`/`_
        control_listen_reservation` would still be the SAME objects as the
        shared surface's own -- the isolated copy's own `_surfaces_value()`
        call (`isolated_application_surface`'s own `_iso_surfaces = iso.
        _surfaces_value()`) would then silently reuse the PARENT's already-
        reserved ports/surfaces instead of reserving its own, and the
        isolated surface would end up serving `iso._app` behind the
        PARENT's real nginx+uvicorn pair -- exactly the "隔離面が親の共有
        appをserveしたまま緑で通りC-05の隔離駆動が無音で誤る" failure
        design D-1 (A) 6 names. Resetting every one of these to fresh,
        empty state here is what forces `iso`'s own subsequent `_surfaces_
        value()`/`_build_client()` calls to reserve and start a dedicated
        uvicorn+nginx pair of their own instead.
        """
        self._socket_lock = threading.Lock()
        self._socket_surfaces: Dict[int, _AppSocketSurface] = {}
        self._data_listen_reservation: Optional["sh.ReservedPort"] = None
        self._control_listen_reservation: Optional["sh.ReservedPort"] = None

    # ------------------------------------------------------------------
    # adapter-internal plumbing (never port-visible)
    # ------------------------------------------------------------------

    def _ensure_socket_registry(self) -> None:
        """Lazily runs `_reset_surface_state()`'s own initialization on
        the FIRST call for a given instance -- the shared (non-isolated)
        top-level instance never has `_reset_surface_state()` called on it
        directly (only `isolated_application_surface()`'s own copy does),
        so it needs this separate lazy-init path instead."""
        if getattr(self, "_socket_surfaces", None) is None:
            self._reset_surface_state()

    def _reserve_named_port(self, attr: str) -> int:
        reservation = getattr(self, attr)
        if reservation is None:
            reservation = sh.reserve_port()
            setattr(self, attr, reservation)
        return reservation.port

    def _socket_surface_for(self, app: Any) -> _AppSocketSurface:
        """Returns the (possibly freshly-built) `_AppSocketSurface` for
        `app`, keyed by object identity -- `hold_in_flight`'s own repeated
        calls (design `docs/design/CONFORMANCE_ADAPTER_V1.md` section
        24.3) pass the SAME `self._app`/`iso._app` object every time and
        must reuse the SAME surface, never build a new real server pair
        per held request.

        `app is self._app` / `app is self._control_app` (whichever `self`
        this method runs on -- the shared instance or an isolated copy)
        picks up the port `_surfaces_value()` already reserved and
        declared for that plane; any OTHER app object (as of this WP, only
        `isolated_control_surface`'s own ephemeral, per-call control
        composition) gets a freshly reserved, undeclared port of its own
        -- nothing ever checks THAT app's own `base_url` against a
        `surfaces` document, so there is nothing for it to agree with.
        """
        key = id(app)
        with self._socket_lock:
            surface = self._socket_surfaces.get(key)
            if surface is not None:
                return surface
            if app is getattr(self, "_app", None):
                reservation = self._data_listen_reservation
                assert reservation is not None, (
                    "MitateDBSocketConformanceAdapter._build_client: the data-plane port reservation is "
                    "missing -- _surfaces_value() must run before self._app is built (base class __init__ "
                    "order, unchanged by this subclass)"
                )
            elif app is getattr(self, "_control_app", None):
                reservation = self._control_listen_reservation
                assert reservation is not None, (
                    "MitateDBSocketConformanceAdapter._build_client: the control-plane port reservation is "
                    "missing -- _surfaces_value() must run before self._control_app is built (base class "
                    "__init__ order, unchanged by this subclass)"
                )
            else:
                reservation = sh.reserve_port()
            surface = _AppSocketSurface(app, reservation)
            self._socket_surfaces[key] = surface
            return surface

    def close(self) -> None:
        """Stops every real socket surface this instance ever built, in
        addition to everything the base class's own `close()` already
        tears down. The base class's own `close()` closes `self._client`/
        `self._control_client`, which (via `_LazyDialTransport.aclose()`)
        already releases this instance's OWN reference on the data/control
        surfaces -- bringing a well-behaved run's refcount to 0 and
        stopping them. This override's own explicit sweep over `self.
        _socket_surfaces` is the defensive backstop for anything that
        reference-counting alone would miss (an `isolated_control_
        surface()` caller whose own `finally` never ran because of an
        earlier, unrelated exception, for instance) -- real OS resources
        (a listening nginx, a bound uvicorn thread) must never be left
        behind at session end regardless of how a test above them failed.
        """
        errors: list[str] = []
        try:
            super().close()
        except Exception as exc:  # noqa: BLE001 - report, never let it hide the sweep below
            errors.append(f"super().close(): {exc!r}")
        for surface in list(getattr(self, "_socket_surfaces", {}) .values()):
            if not surface._started:  # noqa: SLF001 - adapter-internal, same convention this file's own base class uses elsewhere
                continue
            try:
                surface.stop()
            except Exception as exc:  # noqa: BLE001
                errors.append(f"socket surface for app id {id(surface.app)}: {exc!r}")
        for attr in ("_data_listen_reservation", "_control_listen_reservation"):
            reservation = getattr(self, attr, None)
            if reservation is not None:
                reservation.close()
                setattr(self, attr, None)
        if errors:
            raise RuntimeError("MitateDBSocketConformanceAdapter.close(): " + "; ".join(errors))


def build_adapter() -> ConformanceAdapter:
    return MitateDBSocketConformanceAdapter()
