"""C-26 composition-root launcher for r2db-api (design docs/design/
PHASE10_DEPLOYMENT_EVIDENCE_V1.md D-1 (B), work order docs/work-orders/
WORK_ORDER_PHASE10_DEPLOYMENT_EVIDENCE_V1.md WP-6c).

This is NOT a conformance adapter (it is never registered under `registry.
json`'s `adapters` section, and it does not implement -- or subclass --
`ConformanceAdapter`, `conformance-tests/adapter.py`). It is a separate
kind of test fixture: a launcher that starts the DOCUMENTED, real
composition roots (`r2db_api.main:app` / `r2db_api.control_main:app`) as
real, separate OS processes, from a documented environment ALONE, fronted
by a real nginx -- exactly the shape a systemd unit + reverse proxy would
in a real deployment (`r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md`).
`conformance-tests/registry.json`'s new `composition_roots` section
registers this class; `conformance-tests/test_c26_composition_root.py`
drives it.

What this module deliberately does NOT do (design D-1 (B) 1, "壊すとどう
見えるか"): it never imports `r2db_api.main`/`r2db_api.control_main` into
this process and never starts the ADAPTER's own composition (the in-
process/ASGI-transport composition `conformance_adapter_r2db_http.py`
builds) -- doing so would make this launcher indistinguishable from the
existing HTTP plug and defeat C-26's whole purpose, which is proving the
DOCUMENTED, real-process composition root actually starts, from ITS OWN
documented environment, unassisted.

Throwaway-platform provisioning below (`_bootstrap_platform`/
`_provision_pg_app`/`_sweep_prefix`) deliberately duplicates -- rather than
imports -- the shape `conformance_adapter_r2db_http.py` already
establishes for the identical purpose (own admin-DSN env var, own prefix
convention, real `psql` against the real migration files). This keeps the
two files independently readable and avoids this launcher inheriting that
3700-line file's own adapter-specific import chain (`adapter.py`,
`httpx`, `r2db_api.control_main`'s own module-level `app = build_control_
app()` triggered at import time) purely to reuse a handful of small SQL-
running helpers. Both files are still the SAME peer's own conformance
fixtures (not a peer-independence violation, P-6 binds peer `src`/`tests`
code, not this kind of shared-within-peer test plumbing).

Ordering this launcher enforces on every `start()`/`restart()` (design D-1
(B) 1, "順序は「free port 予約 → declare → uvicorn subprocess → nginx →
readiness」"): nginx's own listen port is reserved FIRST (so the
`surfaces` URL declared below is the SAME URL nginx will actually answer
on); `ops declare-surfaces`/`declare-process-ceilings` are then run as
real, separate `python -m r2db_api.ops` subprocesses (never a Python
function call into that module -- design's "実 CLI で" is load-bearing:
this is the same operator-facing binary a real deployment runs, not this
launcher's own re-implementation of what it does); only THEN are the two
uvicorn subprocesses started, then nginx (bound to the port already
reserved above), then this launcher waits for both upstreams to answer
through nginx. `startup_events` (a list of `(label, monotonic_time)`
pairs) records this sequence so `test_c26_composition_root.py` can assert
the real order without depending on wall-clock timing assumptions of its
own.
"""
from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

if "socket_harness" not in sys.modules:
    _conformance_tests = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "conformance-tests")
    )
    if os.path.isdir(_conformance_tests) and _conformance_tests not in sys.path:
        sys.path.insert(0, _conformance_tests)

import socket_harness as sh  # noqa: E402

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"

# Load-bearing (measured directly, not a style choice): the shared `.venv`
# holds an EDITABLE install of `r2db_api` whose own `.pth` file in
# `site-packages` names the SHARED CHECKOUT's `r2db-api/src` -- a
# `sys.path` entry that sorts AFTER this worktree's own directories for an
# ordinary `import r2db_api` in THIS process, but that ordering is
# meaningless to a brand-new `python -m ...` SUBPROCESS, which starts
# `sys.path` from `site-packages` outward and has never heard of this
# worktree at all. Without forcing `PYTHONPATH` below, every `ops`
# subprocess and every uvicorn subprocess this launcher starts would
# silently import the SHARED CHECKOUT's `r2db_api`, not this worktree's
# own -- defeating the entire point of a WP-specific worktree (`git
# worktree`'s own isolation) for exactly the composition roots this WP
# exists to prove. Prepended (never a bare overwrite) so a caller with a
# legitimate PYTHONPATH already set of their own is still honored, after
# this worktree's own `src`.
_WORKTREE_SRC = str(Path(__file__).resolve().parents[1] / "src")


def _with_pythonpath(env: dict[str, str]) -> dict[str, str]:
    existing = os.environ.get("PYTHONPATH")
    merged = dict(env)
    merged["PYTHONPATH"] = _WORKTREE_SRC if not existing else f"{_WORKTREE_SRC}{os.pathsep}{existing}"
    return merged

# Same knob `conformance_adapter_r2db_http.py`/`tests/test_postgres.py`
# already use for "where is the admin/superuser PostgreSQL connection for
# this repository's own throwaway-provisioning tests" -- deliberately
# reused rather than inventing a fourth name for the identical question.
ADMIN_DSN_ENV = "R2DB_TEST_ADMIN_DSN"
ADMIN_DSN_DEFAULT = "host=/tmp port=5432 dbname=postgres"

# This launcher's own prefix shape, distinct from every other throwaway-
# prefix convention already in this repository ("r2dbtest*"/"r2dbsvc*"/
# "r2dbmig*"/"r2dbhttp*") so its own startup-time sweep (`_sweep_stale`)
# can never collide with (and drop) a concurrently-running sibling
# adapter's own throwaway platform on a shared local cluster.
_PREFIX_TAG = "r2dbc26"


class LauncherStartupError(RuntimeError):
    """Raised on any failure to bring this launcher's real composition
    roots up -- never converted to a skip anywhere in this module (mirrors
    `socket_harness.HarnessStartupError`'s own discipline)."""


def _admin_dsn() -> str:
    return os.environ.get(ADMIN_DSN_ENV, ADMIN_DSN_DEFAULT)


def _dsn_with(base_dsn: str, **overrides: str) -> str:
    params = conninfo_to_dict(base_dsn)
    params.update(overrides)
    return make_conninfo(**params)


def _run_psql(dsn: str, path: Path, variables: Optional[dict[str, str]] = None) -> None:
    command = ["psql", dsn, "-v", "ON_ERROR_STOP=1"]
    for key, value in (variables or {}).items():
        command += ["-v", f"{key}={value}"]
    command += ["-f", str(path)]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise LauncherStartupError(f"psql failed running {path.name}:\n{result.stdout}\n{result.stderr}")


def _run_ops(env: Mapping[str, str], *args: str) -> subprocess.CompletedProcess:
    """Runs the REAL `python -m r2db_api.ops` CLI as a real subprocess
    (design D-1 (B) 1: "実 CLI で") -- `env` is merged over a copy of this
    launcher process' own OS environment (mirrors `socket_harness.start_
    uvicorn_subprocess`'s identical merge, so this CLI invocation sees the
    same PATH/venv-derived environment the eventual app subprocess will).
    Never raises on a non-zero exit -- the fail-fast test needs the raw
    `CompletedProcess` to inspect `returncode`/`stderr` itself."""
    full_env = dict(os.environ)
    full_env.update(_with_pythonpath(dict(env)))
    return subprocess.run(
        [sys.executable, "-m", "r2db_api.ops", *args],
        capture_output=True, text=True, env=full_env,
    )


def _sweep_prefix(admin_dsn: str, prefix: str) -> None:
    """Drops every database and cluster-global role whose name starts with
    `prefix` -- this launcher's own equivalent of `conformance_adapter_
    r2db_http.py::_sweep_prefix`, trimmed to what a fresh single-
    application throwaway platform can actually accumulate (no per-
    application connection-pool retry loop is needed here: this launcher
    never opens its own pooled connections against the provisioned
    application's database, only the two uvicorn subprocesses do, and
    both are always stopped before this runs)."""
    admin = psycopg.connect(admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute("SELECT datname FROM pg_database WHERE datname LIKE %s", [f"{prefix}%"])
            databases = sorted(row[0] for row in cur.fetchall())
            for database in databases:
                for attempt in range(8):
                    cur.execute(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = %s AND pid <> pg_backend_pid() AND backend_type = 'client backend'",
                        [database],
                    )
                    try:
                        cur.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(database)))
                        break
                    except psycopg.errors.ObjectInUse:
                        admin.rollback()
                        time.sleep(0.2 * (attempt + 1))

            cur.execute("SELECT rolname FROM pg_roles WHERE rolname LIKE %s", [f"{prefix}%"])
            roles = [row[0] for row in cur.fetchall()]
            for role in roles:
                cur.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))
    finally:
        admin.close()


def _sweep_stale(admin_dsn: str) -> None:
    """Startup-time sweep of a PREVIOUS run's residue (this launcher's own
    prefix pattern only -- never a bare wildcard). No advisory-lock guard
    against a genuinely-concurrent sibling run is needed here (unlike
    `conformance_adapter_r2db_http.py`'s own `_sweep_stale_artifacts`):
    every prefix this launcher ever generates carries its own fresh
    `secrets.token_hex`, so two launcher instances never share one, and
    `test_c26_composition_root.py` runs each launcher's own tests in its
    own dedicated `xdist_group` (never two workers touching the SAME
    launcher instance's platform at once)."""
    admin = psycopg.connect(admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute("SELECT datname FROM pg_database WHERE datname LIKE %s", [f"{_PREFIX_TAG}%"])
            stale_prefixes = {row[0].split("_platform")[0] for row in cur.fetchall() if "_platform" in row[0]}
    finally:
        admin.close()
    for prefix in stale_prefixes:
        _sweep_prefix(admin_dsn, prefix)


@dataclass(frozen=True)
class _Platform:
    prefix: str
    admin_dsn: str
    control_dsn: str
    api_dsn: str
    controlplane_dsn: str
    schema: str
    platform_db: str
    app_pepper: str
    control_pepper: str


@dataclass(frozen=True)
class _AppInfo:
    slug: str
    runtime_dsn: str
    developer_dsn: str


def _bootstrap_platform(prefix: str, admin_dsn: str, script_dir: Path) -> _Platform:
    """Runs the real migrations `0001`..`0003`, `0005`..`0008`, `0012`
    (with the literal token `r2dbsvc` textually replaced by `prefix`)
    through the real `psql` binary. `0004` (deprovision) is not needed --
    this launcher's own teardown drops the whole prefix at once (`_sweep_
    prefix`), never one application at a time. `0008`/`0012` (the
    `platform_declarations` table + its `process_ceilings` key) ARE run
    here, unlike `conformance_adapter_r2db_http.py`'s own `_bootstrap_
    platform` -- that adapter injects `surfaces` directly and never goes
    through the declaration table at all (LQ4-11, design D-4); this
    launcher's whole point is exercising that exact table through the
    real `ops declare-surfaces`/`declare-process-ceilings` CLI."""
    control_role = f"{prefix}_control"
    api_role = f"{prefix}_api"
    controlplane_role = f"{prefix}_controlplane"
    auditreader_role = f"{prefix}_auditreader"
    platform_db = f"{prefix}_platform"
    schema = f"{prefix}_registry"
    control_password = secrets.token_urlsafe(24)
    api_password = secrets.token_urlsafe(24)
    controlplane_password = secrets.token_urlsafe(24)
    auditreader_password = secrets.token_urlsafe(24)

    rewritten: dict[str, Path] = {}
    for name in (
        "0001_bootstrap_control_plane.sql",
        "0002_provisioning_functions.sql",
        "0003_provision_application.sql",
        "0005_credential_store.sql",
        "0006_control_plane_http.sql",
        "0007_application_audit.sql",
        "0008_platform_declarations_and_writer_timeouts.sql",
        "0012_process_ceilings.sql",
    ):
        text = (MIGRATIONS_DIR / name).read_text().replace("r2dbsvc", prefix)
        out = script_dir / name
        out.write_text(text)
        rewritten[name] = out

    _run_psql(admin_dsn, rewritten["0001_bootstrap_control_plane.sql"], {"control_password": control_password})
    control_dsn = _dsn_with(admin_dsn, user=control_role, password=control_password, dbname=platform_db)
    _run_psql(control_dsn, rewritten["0002_provisioning_functions.sql"])
    _run_psql(control_dsn, rewritten["0005_credential_store.sql"], {"api_password": api_password})
    _run_psql(control_dsn, rewritten["0006_control_plane_http.sql"], {"controlplane_password": controlplane_password})
    _run_psql(control_dsn, rewritten["0007_application_audit.sql"], {"auditreader_password": auditreader_password})
    _run_psql(
        control_dsn, rewritten["0008_platform_declarations_and_writer_timeouts.sql"],
        {"api_role": api_role, "controlplane_role": controlplane_role},
    )
    _run_psql(control_dsn, rewritten["0012_process_ceilings.sql"])

    return _Platform(
        prefix=prefix,
        admin_dsn=admin_dsn,
        control_dsn=control_dsn,
        api_dsn=_dsn_with(admin_dsn, user=api_role, password=api_password, dbname=platform_db),
        controlplane_dsn=_dsn_with(admin_dsn, user=controlplane_role, password=controlplane_password, dbname=platform_db),
        schema=schema,
        platform_db=platform_db,
        app_pepper=f"launcher-app-pepper-{secrets.token_hex(8)}",
        control_pepper=f"launcher-control-pepper-{secrets.token_hex(8)}",
    )


def _provision_app(platform: _Platform, script_dir: Path, slug: str) -> _AppInfo:
    text = (MIGRATIONS_DIR / "0003_provision_application.sql").read_text().replace("r2dbsvc", platform.prefix)
    script = script_dir / f"0003_provision_application_{slug}.sql"
    script.write_text(text)
    runtime_password = secrets.token_urlsafe(24)
    developer_password = secrets.token_urlsafe(24)
    _run_psql(platform.control_dsn, script, {
        "app_slug": slug, "runtime_password": runtime_password, "developer_password": developer_password,
    })
    database = f"{platform.prefix}_app_{slug}"
    return _AppInfo(
        slug=slug,
        runtime_dsn=_dsn_with(platform.admin_dsn, user=f"{database}_runtime", password=runtime_password, dbname=database),
        developer_dsn=_dsn_with(platform.admin_dsn, user=f"{database}_developer", password=developer_password, dbname=database),
    )


def _ops_env(platform: _Platform) -> dict[str, str]:
    return {
        "R2DB_CONTROL_DSN": platform.control_dsn,
        "R2DB_CREDENTIAL_PEPPER": platform.app_pepper,
        "R2DB_CONTROL_CREDENTIAL_PEPPER": platform.control_pepper,
        "R2DB_PLATFORM_SCHEMA": platform.schema,
    }


def _parse_issued_secret(stdout: str) -> str:
    for line in stdout.splitlines():
        if line.startswith("secret: "):
            return line[len("secret: "):]
    raise LauncherStartupError(f"could not find a 'secret: ' line in ops output:\n{stdout}")


class RealServerR2db:
    """The C-26 launcher registered for r2db-api (`conformance-tests/
    registry.json`'s `composition_roots` section names this class).
    Provisioning (throwaway platform + one application + credentials) is
    lazy -- it happens on the first `start()` call, not at construction --
    so `conformance-tests/conftest.py` can construct one instance per
    xdist worker at collection time (mirroring `_discover_and_build`'s own
    eager-but-inert adapter construction, design D-2 (g)) without paying
    for a real PostgreSQL round-trip on a worker whose own tests never
    call `start()`."""

    name = "r2db-api"

    def __init__(self) -> None:
        self._script_dir: Optional[Path] = None
        self._platform: Optional[_Platform] = None
        self._app: Optional[_AppInfo] = None
        self._control_credential_id: Optional[str] = None
        self._control_secret: Optional[str] = None
        self._runtime_secret: Optional[str] = None
        self._data_handle: Optional[sh.UvicornSubprocessHandle] = None
        self._control_handle: Optional[sh.UvicornSubprocessHandle] = None
        self._nginx: Optional[sh.NginxHandle] = None
        self._nginx_prefix_dir: Optional[Path] = None
        self._listen_port: Optional[int] = None
        self._events: list[tuple[str, float]] = []
        self._started = False

    # -- provisioning (lazy, once) ------------------------------------

    def _ensure_provisioned(self) -> None:
        if self._platform is not None:
            return
        _sweep_stale(_admin_dsn())
        self._script_dir = Path(tempfile.mkdtemp(prefix="r2db-c26-scripts-"))
        prefix = f"{_PREFIX_TAG}{secrets.token_hex(8)}"
        self._platform = _bootstrap_platform(prefix, _admin_dsn(), self._script_dir)
        self._app = _provision_app(self._platform, self._script_dir, "c26app")
        issued = _run_ops(_ops_env(self._platform), "issue-credential", self._app.slug, "runtime")
        if issued.returncode != 0:
            raise LauncherStartupError(f"issue-credential failed:\n{issued.stdout}\n{issued.stderr}")
        self._runtime_secret = _parse_issued_secret(issued.stdout)
        bootstrapped = _run_ops(_ops_env(self._platform), "bootstrap")
        if bootstrapped.returncode != 0:
            raise LauncherStartupError(f"ops bootstrap failed:\n{bootstrapped.stdout}\n{bootstrapped.stderr}")
        self._control_secret = _parse_issued_secret(bootstrapped.stdout)

    # -- events (design D-1 (B) 1's own ordering, test 1) -------------

    def startup_events(self) -> list[str]:
        return [label for label, _ in self._events]

    def _record(self, label: str) -> None:
        self._events.append((label, time.monotonic()))

    # -- start/restart/stop --------------------------------------------

    def start(self, *, ceilings: Mapping[str, int]) -> None:
        if self._started:
            raise LauncherStartupError("start() called while already started -- call stop() or restart() first")
        self._ensure_provisioned()
        self._events = []
        assert self._platform is not None and self._app is not None

        reservation = sh.reserve_port()
        listen_port = reservation.port
        data_base_url = f"http://127.0.0.1:{listen_port}/v1"
        control_base_url = f"http://127.0.0.1:{listen_port}/control/v1"

        surfaces_result = _run_ops(
            _ops_env(self._platform), "declare-surfaces",
            "--data-base-url", data_base_url, "--control-base-url", control_base_url,
        )
        if surfaces_result.returncode != 0:
            reservation.close()
            raise LauncherStartupError(f"declare-surfaces failed:\n{surfaces_result.stdout}\n{surfaces_result.stderr}")
        self._record("declare_surfaces")

        ceilings_result = _run_ops(
            _ops_env(self._platform), "declare-process-ceilings",
            "--data", str(ceilings["data"]), "--control", str(ceilings["control"]),
        )
        if ceilings_result.returncode != 0:
            reservation.close()
            raise LauncherStartupError(f"declare-process-ceilings failed:\n{ceilings_result.stdout}\n{ceilings_result.stderr}")
        self._record("declare_process_ceilings")

        slug_upper = self._app.slug.upper()
        app_env = {
            "R2DB_CREDENTIAL_PEPPER": self._platform.app_pepper,
            "R2DB_PLATFORM_DSN": self._platform.api_dsn,
            "R2DB_PLATFORM_SCHEMA": self._platform.schema,
            "R2DB_SERVE_APPS": self._app.slug,
            f"R2DB_APP_{slug_upper}_RUNTIME_DSN": self._app.runtime_dsn,
            f"R2DB_APP_{slug_upper}_DEVELOPER_DSN": self._app.developer_dsn,
            "R2DB_CONTROL_PLANE_STATUS": "enabled",
        }
        control_env = {
            "R2DB_CONTROLPLANE_DSN": self._platform.controlplane_dsn,
            "R2DB_CONTROL_CREDENTIAL_PEPPER": self._platform.control_pepper,
            "R2DB_CREDENTIAL_PEPPER": self._platform.app_pepper,
            "R2DB_PLATFORM_SCHEMA": self._platform.schema,
        }

        assert self._script_dir is not None
        pidfile_data = self._script_dir / "uvicorn-data.pid"
        pidfile_control = self._script_dir / "uvicorn-control.pid"
        self._data_handle = sh.start_uvicorn_subprocess(
            "r2db_api.main:app", pidfile=pidfile_data, env=_with_pythonpath(app_env),
        )
        self._record("uvicorn_data_start")
        self._control_handle = sh.start_uvicorn_subprocess(
            "r2db_api.control_main:app", pidfile=pidfile_control, env=_with_pythonpath(control_env),
        )
        self._record("uvicorn_control_start")

        try:
            nginx_bin = sh.find_nginx_binary()
            nginx_dir = Path(tempfile.mkdtemp(prefix="conf-socket-"))
            prefix_dir = nginx_dir / sh.NGINX_PREFIX_MARKER
            prefix_dir.mkdir(parents=True, exist_ok=True)
            (prefix_dir / "client_body_temp").mkdir(parents=True, exist_ok=True)
            (prefix_dir / "proxy_temp").mkdir(parents=True, exist_ok=True)
            self._nginx_prefix_dir = nginx_dir
            reservation.close()
            conf_path = prefix_dir / "nginx.conf"
            conf_path.write_text(sh.render_nginx_conf(
                prefix=prefix_dir, listen_port=listen_port,
                data_port=self._data_handle.port, control_port=self._control_handle.port,
            ))
            sh.check_nginx_config(nginx_bin, conf_path, prefix_dir)
            self._nginx = sh.start_nginx(nginx_bin, conf_path, prefix_dir)
            self._listen_port = listen_port
            self._record("nginx_start")

            sh.wait_until_ready(f"{data_base_url}/capabilities", label="r2db data")
            self._record("readiness_data")
            sh.wait_until_ready(f"{control_base_url}/capabilities", label="r2db control")
            self._record("readiness_control")
        except BaseException:
            # Full `stop()` (never just `_best_effort_stop_processes()`) --
            # a failed `start()` can leave the throwaway platform database
            # this call's own `_ensure_provisioned()` already created; a
            # caller that only sees an exception out of `start()` never
            # calls `stop()` itself (there is nothing "started" to stop,
            # from its own point of view), so this is the only place that
            # residue is ever swept.
            self.stop()
            raise

        self._started = True

    def restart(self, *, ceilings: Mapping[str, int]) -> None:
        """Re-declares `process_ceilings` (real CLI), then stops and
        restarts ONLY the two uvicorn subprocesses, on the SAME ports --
        nginx (and therefore the already-declared `surfaces` URL) is left
        untouched, matching a real redeploy that restarts the app
        processes behind a stable reverse proxy. `declare-process-
        ceilings` is written to the REAL, DB-side table via the real CLI
        BEFORE either process restarts (design D-5 (ii): "起動時スナップ
        ショットのため" -- the new value only takes effect once both
        processes come back up)."""
        if not self._started:
            raise LauncherStartupError("restart() called before start()")
        assert self._platform is not None and self._app is not None
        assert self._data_handle is not None and self._control_handle is not None

        ceilings_result = _run_ops(
            _ops_env(self._platform), "declare-process-ceilings",
            "--data", str(ceilings["data"]), "--control", str(ceilings["control"]),
        )
        if ceilings_result.returncode != 0:
            raise LauncherStartupError(f"declare-process-ceilings failed:\n{ceilings_result.stdout}\n{ceilings_result.stderr}")
        self._record("declare_process_ceilings_restart")

        data_port = self._data_handle.port
        control_port = self._control_handle.port
        self._data_handle.stop()
        self._control_handle.stop()

        slug_upper = self._app.slug.upper()
        app_env = {
            "R2DB_CREDENTIAL_PEPPER": self._platform.app_pepper,
            "R2DB_PLATFORM_DSN": self._platform.api_dsn,
            "R2DB_PLATFORM_SCHEMA": self._platform.schema,
            "R2DB_SERVE_APPS": self._app.slug,
            f"R2DB_APP_{slug_upper}_RUNTIME_DSN": self._app.runtime_dsn,
            f"R2DB_APP_{slug_upper}_DEVELOPER_DSN": self._app.developer_dsn,
            "R2DB_CONTROL_PLANE_STATUS": "enabled",
        }
        control_env = {
            "R2DB_CONTROLPLANE_DSN": self._platform.controlplane_dsn,
            "R2DB_CONTROL_CREDENTIAL_PEPPER": self._platform.control_pepper,
            "R2DB_CREDENTIAL_PEPPER": self._platform.app_pepper,
            "R2DB_PLATFORM_SCHEMA": self._platform.schema,
        }
        assert self._script_dir is not None
        self._data_handle = sh.start_uvicorn_subprocess(
            "r2db_api.main:app", pidfile=self._script_dir / "uvicorn-data.pid", port=data_port, env=_with_pythonpath(app_env),
        )
        self._record("uvicorn_data_restart")
        self._control_handle = sh.start_uvicorn_subprocess(
            "r2db_api.control_main:app", pidfile=self._script_dir / "uvicorn-control.pid", port=control_port, env=_with_pythonpath(control_env),
        )
        self._record("uvicorn_control_restart")

        sh.wait_until_ready(f"{self.data_base_url}/capabilities", label="r2db data (restart)")
        sh.wait_until_ready(f"{self.control_base_url}/capabilities", label="r2db control (restart)")

    def _best_effort_stop_processes(self) -> None:
        for handle in (self._data_handle, self._control_handle):
            if handle is not None:
                try:
                    handle.stop()
                except Exception:  # noqa: BLE001
                    pass
        if self._nginx is not None:
            try:
                self._nginx.stop()
            except Exception:  # noqa: BLE001
                pass

    def stop(self) -> None:
        """Stops both uvicorn subprocesses and nginx, then drops the
        throwaway platform (every database/role under this run's own
        prefix). Idempotent -- a second call with nothing left running is
        a no-op."""
        self._best_effort_stop_processes()
        self._data_handle = None
        self._control_handle = None
        self._nginx = None
        if self._nginx_prefix_dir is not None:
            shutil.rmtree(self._nginx_prefix_dir, ignore_errors=True)
            self._nginx_prefix_dir = None
        if self._platform is not None:
            _sweep_prefix(self._platform.admin_dsn, self._platform.prefix)
        if self._script_dir is not None:
            shutil.rmtree(self._script_dir, ignore_errors=True)
            self._script_dir = None
        self._platform = None
        self._app = None
        self._started = False
        self._listen_port = None

    # -- observation surface for the tests ------------------------------

    @property
    def data_base_url(self) -> str:
        assert self._listen_port is not None
        return f"http://127.0.0.1:{self._listen_port}/v1"

    @property
    def control_base_url(self) -> str:
        assert self._listen_port is not None
        return f"http://127.0.0.1:{self._listen_port}/control/v1"

    @property
    def runtime_bearer(self) -> str:
        assert self._runtime_secret is not None
        return self._runtime_secret

    @property
    def control_bearer(self) -> str:
        assert self._control_secret is not None
        return self._control_secret

    def attempt_start_without_process_ceilings(self) -> subprocess.CompletedProcess:
        """Design D-1 (B) 5 / completion condition 5: builds a SEPARATE,
        independent throwaway platform (own prefix), declares `surfaces`
        but deliberately never runs `declare-process-ceilings`, then
        attempts a single, short-lived `python -m uvicorn r2db_api.main:
        app` run directly (never through `socket_harness.start_uvicorn_
        subprocess`, whose own stdout/stderr are `DEVNULL` -- this needs
        the real stderr text). Always tears its own throwaway platform
        down again before returning, success or failure alike."""
        script_dir = Path(tempfile.mkdtemp(prefix="r2db-c26-f15-"))
        prefix = f"{_PREFIX_TAG}{secrets.token_hex(8)}f15"
        try:
            platform = _bootstrap_platform(prefix, _admin_dsn(), script_dir)
            app = _provision_app(platform, script_dir, "f15app")
            surfaces = _run_ops(
                _ops_env(platform), "declare-surfaces",
                "--data-base-url", "http://127.0.0.1:1/v1",
                "--control-base-url", "http://127.0.0.1:1/control/v1",
            )
            if surfaces.returncode != 0:
                raise LauncherStartupError(f"declare-surfaces failed:\n{surfaces.stdout}\n{surfaces.stderr}")
            slug_upper = app.slug.upper()
            env = dict(os.environ)
            env.update(_with_pythonpath({
                "R2DB_CREDENTIAL_PEPPER": platform.app_pepper,
                "R2DB_PLATFORM_DSN": platform.api_dsn,
                "R2DB_PLATFORM_SCHEMA": platform.schema,
                "R2DB_SERVE_APPS": app.slug,
                f"R2DB_APP_{slug_upper}_RUNTIME_DSN": app.runtime_dsn,
                f"R2DB_APP_{slug_upper}_DEVELOPER_DSN": app.developer_dsn,
                "R2DB_CONTROL_PLANE_STATUS": "enabled",
            }))
            # `process_ceilings` is deliberately never declared above --
            # `build_app()` must fail fast (F-15) at IMPORT time, which
            # means the uvicorn *process itself* never reaches "serving"
            # -- `subprocess.run` (not the harness' fire-and-forget
            # `Popen`) is used here specifically so this call blocks until
            # that failure actually happens and captures its real stderr.
            free_port = sh.free_port()
            result = subprocess.run(
                [sys.executable, "-m", "uvicorn", "r2db_api.main:app", "--host", "127.0.0.1", "--port", str(free_port)],
                env=env, capture_output=True, text=True, timeout=30,
            )
            return result
        finally:
            _sweep_prefix(_admin_dsn(), prefix)
            shutil.rmtree(script_dir, ignore_errors=True)
