"""C-26 composition-root launcher for MitateDB-api (design docs/design/
PHASE10_DEPLOYMENT_EVIDENCE_V1.md D-1 (B), work order docs/work-orders/
WORK_ORDER_PHASE10_DEPLOYMENT_EVIDENCE_V1.md WP-6c).

Peer counterpart of `r2db-api/conformance/real_server_r2db.py` -- see that
module's own top-of-file docstring for the shared rationale (this is not a
`ConformanceAdapter`, never registered under `registry.json`'s `adapters`
section; throwaway-platform provisioning below duplicates rather than
imports `conformance_adapter_mitatedb_http.py`'s own equivalent, for the
same reason: avoiding that ~3000-line file's own adapter-specific import
chain). No code is shared BETWEEN the two peers' own launcher modules
(P-6) -- the same-named methods below (`start`/`restart`/`stop`/
`startup_events`/`data_base_url`/`control_base_url`/`attempt_start_
without_process_ceilings`) are independently implemented against this
peer's own migrations/CLI/composition roots.

One structural difference from r2db-api, load-bearing here: this peer has
no `ops issue-credential` CLI subcommand (`MitateDB-api/src/mitatedb_api/
ops.py` never defines one -- applications issue runtime/developer
credentials only in-band, through the running control-plane HTTP surface,
or out-of-band via the `PostgresCredentialStore` Python class directly,
exactly as `conformance_adapter_mitatedb_http.py`'s own `issue_credential`
method does). Since this launcher's own runtime credential must exist
BEFORE the control-plane HTTP surface is even started (`ops bootstrap` /
`declare-surfaces` / `declare-process-ceilings` all run before either
uvicorn subprocess), it uses that same out-of-band `PostgresCredentialStore
(...).issue(...)` call the HTTP adapter already establishes as this peer's
own precedent for "issue a credential without a running server" -- never a
new capability this launcher invents, and never a change to `src/`.
"""
from __future__ import annotations

import contextlib
import fcntl
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
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

# F7 correction (WP-6c review 2026-09-09): this comment previously
# claimed (unmeasured, under this module's OWN prior docstring) that an
# ordinary `import mitatedb_api` in THIS process would silently prefer
# the shared checkout's editable install over this worktree's own copy.
# Measured directly under the actual `pytest` invocation this module is
# always imported through: `pyproject.toml`'s own `[tool.pytest.ini_
# options] pythonpath = ["r2db-api/src", "MitateDB-api/src", "conformance-
# tests"]` already prepends THIS worktree's `MitateDB-api/src` ahead of
# the shared `.venv`'s `site-packages` (where the editable install's own
# `.pth` file lives) at session start, so `import mitatedb_api.credential_
# store_postgres` below already resolves against this worktree's own copy
# WITHOUT the explicit `sys.path.insert` this block performs -- confirmed
# by reading back `mitatedb_api.__file__` under a real collection of this
# suite. This insert is therefore redundant under every actual pytest run
# of this module and is kept ONLY as a defensive fallback for a
# hypothetical import of this module OUTSIDE that pytest session (e.g. a
# bare `python -c "import real_server_mitatedb"` with no `pythonpath` ini
# option in effect) -- never "load-bearing" the way the prior text of this
# comment claimed. `_WORKTREE_SRC`/`_with_pythonpath` below remain the
# genuinely load-bearing half of this same concern: pytest's own
# `pythonpath` option affects only THIS process' `sys.path`, never a
# freshly spawned SUBPROCESS's, which starts from `site-packages` outward
# and has never heard of this worktree at all.
_worktree_src = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if _worktree_src not in sys.path:
    sys.path.insert(0, _worktree_src)

from mitatedb_api.credential_store_postgres import PostgresCredentialStore  # noqa: E402

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"

ADMIN_DSN_ENV = "MITATEDB_TEST_ADMIN_DSN"
ADMIN_DSN_DEFAULT = "host=/tmp port=5432 dbname=postgres"

# See `_worktree_src`'s own comment above for the in-process half of this
# problem; this is the SUBPROCESS half -- every `ops`/uvicorn subprocess
# this launcher starts must resolve `import mitatedb_api` against THIS
# worktree's own `src`, never the shared checkout's, whatever this
# process' own `sys.path` cache already decided for itself.
_WORKTREE_SRC = _worktree_src


def _with_pythonpath(env: dict[str, str]) -> dict[str, str]:
    existing = os.environ.get("PYTHONPATH")
    merged = dict(env)
    merged["PYTHONPATH"] = _WORKTREE_SRC if not existing else f"{_WORKTREE_SRC}{os.pathsep}{existing}"
    return merged


# Both peers' own env-var prefixes -- stripped from whatever this launcher
# inherits from ITS OWN OS environment before layering its own explicit,
# fully-documented dict on top (F6, WP-6c review 2026-09-09). This
# module's own docstring claims each subprocess starts "from a documented
# environment ALONE"; an ambient `R2DB_*`/`MITATEDB_*` value already set
# in the shell that launched this test suite (a leftover from an
# operator's own manual testing, or the OTHER peer's own value on a
# shared dev host) would otherwise silently satisfy a key this launcher's
# own dict below forgot to pass, making that gap invisible instead of
# failing loudly.
_PEER_ENV_PREFIXES = ("R2DB_", "MITATEDB_")


def _scrub_peer_env_prefixes(env: Mapping[str, str]) -> dict[str, str]:
    return {key: value for key, value in env.items() if not key.startswith(_PEER_ENV_PREFIXES)}


@contextlib.contextmanager
def _peer_env_prefixes_removed_from_os_environ():
    """Temporarily removes every ambient `R2DB_*`/`MITATEDB_*` key from
    THIS process' own `os.environ` for the duration of the `with` block --
    `socket_harness.start_uvicorn_subprocess` (outside this WP's own 7
    touched files, never edited here) always merges a fresh `dict(os.
    environ)` under its own caller-supplied `env=` mapping, so this is the
    only lever available to keep an ambient value under either prefix from
    reaching a uvicorn subprocess this launcher starts (see
    `_scrub_peer_env_prefixes`'s own docstring for why that matters).
    `subprocess.Popen` (which `start_uvicorn_subprocess` calls) copies its
    `env=` mapping at call time, so restoring the removed keys immediately
    after it returns cannot affect the already-spawned child."""
    removed = {key: os.environ.pop(key) for key in list(os.environ) if key.startswith(_PEER_ENV_PREFIXES)}
    try:
        yield
    finally:
        os.environ.update(removed)


# Distinct from "mitatedbtest*"/"mitatedbhttp*" (this repository's other
# throwaway-prefix conventions) so this launcher's own startup sweep can
# never collide with a concurrently-running sibling's platform.
_PREFIX_TAG = "mtdbc26"

# Cross-process advisory-lock directory for `_claim_prefix_lock`/`_release_
# prefix_lock` below (F2, WP-6c review 2026-09-09) -- peer-scoped so this
# launcher's own lock files can never collide with r2db-api's own, even
# though `_PREFIX_TAG` already makes that collision impossible on its own
# (belt-and-suspenders, negligible cost).
_LOCK_DIR = Path(tempfile.gettempdir()) / f"conformance-{_PREFIX_TAG}-locks"


class LauncherStartupError(RuntimeError):
    """Raised on any failure to bring this launcher's real composition
    roots up -- never converted to a skip anywhere in this module."""


def _admin_dsn() -> str:
    return os.environ.get(ADMIN_DSN_ENV, ADMIN_DSN_DEFAULT)


def _dsn_with(base_dsn: str, **overrides: str) -> str:
    params = conninfo_to_dict(base_dsn)
    params.update(overrides)
    return make_conninfo(**params)


def _lock_path(prefix: str) -> Path:
    return _LOCK_DIR / f"{prefix}.lock"


def _claim_prefix_lock(prefix: str):
    """Best-effort, cross-process advisory lock (`fcntl.flock`, non-
    blocking) proving no OTHER live process is currently using `prefix`
    (F2, WP-6c review 2026-09-09): `_sweep_stale` must drop ONLY genuinely
    orphaned residue -- a run that crashed without ever calling `stop()`
    -- never a SIBLING launcher instance's own currently-alive platform,
    just because both happen to share this launcher's own `_PREFIX_TAG`.
    Held from the moment a fresh prefix is minted (`_ensure_provisioned`/
    `attempt_start_without_process_ceilings`) until `stop()` releases it;
    the OS releases the flock automatically even if this process is
    SIGKILLed, so a prefix left behind by a crash is always claimable
    again by the next sweep. Returns the open file handle (kept open --
    closing it releases the lock) on success, `None` if another live
    process already holds it."""
    _LOCK_DIR.mkdir(parents=True, exist_ok=True)
    handle = open(_lock_path(prefix), "w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def _release_prefix_lock(prefix: str, handle) -> None:
    if handle is None:
        return
    try:
        fcntl.flock(handle, fcntl.LOCK_UN)
    finally:
        handle.close()
    with contextlib.suppress(OSError):
        _lock_path(prefix).unlink()


def _run_psql(dsn: str, path: Path, variables: Optional[dict[str, str]] = None) -> None:
    command = ["psql", dsn, "-v", "ON_ERROR_STOP=1"]
    for key, value in (variables or {}).items():
        command += ["-v", f"{key}={value}"]
    command += ["-f", str(path)]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise LauncherStartupError(f"psql failed running {path.name}:\n{result.stdout}\n{result.stderr}")


def _run_ops(env: Mapping[str, str], *args: str) -> subprocess.CompletedProcess:
    """Real `python -m mitatedb_api.ops` subprocess (design D-1 (B) 1:
    "実 CLI で") -- `env` is merged over a copy of this launcher process'
    own OS environment, with both peers' own env-var prefixes scrubbed
    first (F6, WP-6c review 2026-09-09; see `_scrub_peer_env_prefixes`'s
    own docstring). Never raises on non-zero exit, the fail-fast test
    needs the raw result."""
    full_env = _scrub_peer_env_prefixes(os.environ)
    full_env.update(_with_pythonpath(dict(env)))
    return subprocess.run(
        [sys.executable, "-m", "mitatedb_api.ops", *args],
        capture_output=True, text=True, env=full_env,
    )


def _sweep_prefix(admin_dsn: str, prefix: str) -> None:
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
    prefix pattern only -- never a bare wildcard). F2 correction (WP-6c
    review 2026-09-09): every prefix this launcher generates DOES carry
    its own fresh `secrets.token_hex`, so two launcher instances never
    generate the SAME prefix -- but that alone does not stop this sweep
    from dropping a DIFFERENT, still-alive prefix it happens to find
    already sitting in `pg_database` (e.g. a sibling launcher instance
    provisioned moments earlier and not yet stopped, on a shared local
    cluster): the query below matches on `_PREFIX_TAG` alone, with no way
    to tell "mine, not yet created" apart from "a live sibling's, already
    running" from the database's own point of view. `_claim_prefix_lock`
    resolves that: a prefix currently held by a live process (anywhere on
    this machine, from the moment it is minted in `_ensure_provisioned`/
    `attempt_start_without_process_ceilings` until `stop()` releases it)
    is skipped here, never swept -- only a prefix whose OWN lock is
    claimable (its holder already exited, crashed or otherwise) is
    genuine residue."""
    admin = psycopg.connect(admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute("SELECT datname FROM pg_database WHERE datname LIKE %s", [f"{_PREFIX_TAG}%"])
            stale_prefixes = {row[0].split("_platform")[0] for row in cur.fetchall() if "_platform" in row[0]}
    finally:
        admin.close()
    for prefix in stale_prefixes:
        lock = _claim_prefix_lock(prefix)
        if lock is None:
            # A live process still holds this prefix's own lock -- it is
            # currently in use by a sibling launcher instance, never
            # stale (F2).
            continue
        try:
            _sweep_prefix(admin_dsn, prefix)
        finally:
            _release_prefix_lock(prefix, lock)


@dataclass(frozen=True)
class _Platform:
    prefix: str
    admin_dsn: str
    provision_dsn: str
    api_dsn: str
    controlplane_dsn: str
    schema: str
    platform_db: str
    app_pepper: str
    control_pepper: str


@dataclass(frozen=True)
class _AppInfo:
    application_id: str
    runtime_dsn: str
    developer_dsn: str


def _bootstrap_platform(prefix: str, admin_dsn: str, script_dir: Path) -> _Platform:
    """Runs `0001`/`0002`/`0005`/`0007`/`0011`/`0012` (with the literal
    token `mitatedb` textually replaced by `prefix`) through the real
    `psql` binary. `0003`/`0004` are kept for per-application provisioning
    only. Unlike `conformance_adapter_mitatedb_http.py`'s own `_bootstrap_
    platform`, `surfaces`/`process_ceilings` are NEVER seeded here via raw
    SQL -- this launcher's whole point is exercising the real `ops
    declare-surfaces`/`declare-process-ceilings` CLI against this exact
    table (design D-1 (B) 1).

    Phase 10 WP-4g (test-fixture-blast-radius fix, peer-symmetric with
    `real_server_r2db.py::_bootstrap_platform`'s own identical fix, and
    mirroring WP-4f's own fix to every OTHER real-PG fixture this
    repository has): `0012_role_connection_limits.sql` raises `mitatedb
    svc_api`/`mitatedbsvc_controlplane`'s own `CONNECTION LIMIT` (and the
    provisioning function's own per-application default, for every
    application provisioned AFTER this point) to each role's real
    pool-composition floor. Without it, this launcher's own `<prefix>svc_
    api` role is left below `check_role_connection_limits`'s own floor,
    and EVERY real composition-root startup this launcher ever attempts
    fails fast on F-16 regardless of anything a caller does afterward.
    Run immediately after `0011` and, critically, BEFORE `_provision_app`
    is ever called for this platform, mirroring the r2db-api launcher's
    own reasoning for why ordering matters here."""
    provision_password = secrets.token_urlsafe(24)
    api_password = secrets.token_urlsafe(24)
    controlplane_password = secrets.token_urlsafe(24)
    auditreader_password = secrets.token_urlsafe(24)

    rewritten: dict[str, Path] = {}
    for name in (
        "0001_bootstrap_platform.sql",
        "0002_registry_and_functions.sql",
        "0003_provision_application.sql",
        "0005_application_audit.sql",
        "0007_platform_declarations.sql",
        "0011_process_ceilings.sql",
        "0012_role_connection_limits.sql",
    ):
        text = (MIGRATIONS_DIR / name).read_text().replace("mitatedb", prefix)
        out = script_dir / name
        out.write_text(text)
        rewritten[name] = out

    provision_role = f"{prefix}svc_provision"
    platform_db = f"{prefix}_platform"
    api_role = f"{prefix}svc_api"
    controlplane_role = f"{prefix}svc_controlplane"
    auditreader_role = f"{prefix}svc_auditreader"
    schema = f"{prefix}_registry"

    _run_psql(admin_dsn, rewritten["0001_bootstrap_platform.sql"], {"provision_password": provision_password})
    provision_dsn = _dsn_with(admin_dsn, user=provision_role, password=provision_password, dbname=platform_db)
    _run_psql(provision_dsn, rewritten["0002_registry_and_functions.sql"])
    _run_psql(provision_dsn, rewritten["0005_application_audit.sql"])
    _run_psql(provision_dsn, rewritten["0007_platform_declarations.sql"], {"api_role": api_role, "controlplane_role": controlplane_role})
    _run_psql(provision_dsn, rewritten["0011_process_ceilings.sql"])
    _run_psql(provision_dsn, rewritten["0012_role_connection_limits.sql"])

    admin = psycopg.connect(admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} PASSWORD {}").format(sql.Identifier(api_role), sql.Literal(api_password)))
            cur.execute(sql.SQL("ALTER ROLE {} PASSWORD {}").format(sql.Identifier(controlplane_role), sql.Literal(controlplane_password)))
            cur.execute(sql.SQL("ALTER ROLE {} PASSWORD {}").format(sql.Identifier(auditreader_role), sql.Literal(auditreader_password)))
    finally:
        admin.close()

    return _Platform(
        prefix=prefix,
        admin_dsn=admin_dsn,
        provision_dsn=provision_dsn,
        api_dsn=_dsn_with(admin_dsn, user=api_role, password=api_password, dbname=platform_db),
        controlplane_dsn=_dsn_with(admin_dsn, user=controlplane_role, password=controlplane_password, dbname=platform_db),
        schema=schema,
        platform_db=platform_db,
        app_pepper=f"launcher-app-pepper-{secrets.token_hex(8)}",
        control_pepper=f"launcher-control-pepper-{secrets.token_hex(8)}",
    )


def _provision_app(platform: _Platform, script_dir: Path, application_id: str) -> _AppInfo:
    text = (MIGRATIONS_DIR / "0003_provision_application.sql").read_text().replace("mitatedb", platform.prefix)
    script = script_dir / f"0003_provision_application_{application_id}.sql"
    script.write_text(text)
    runtime_password = secrets.token_urlsafe(24)
    developer_password = secrets.token_urlsafe(24)
    _run_psql(platform.provision_dsn, script, {
        "app_id": application_id, "runtime_password": runtime_password, "developer_password": developer_password,
    })
    database = f"{platform.prefix}_app_{application_id}"
    return _AppInfo(
        application_id=application_id,
        runtime_dsn=_dsn_with(platform.admin_dsn, user=f"{database}_rt", password=runtime_password, dbname=database),
        developer_dsn=_dsn_with(platform.admin_dsn, user=f"{database}_dv", password=developer_password, dbname=database),
    )


def _ops_env(platform: _Platform) -> dict[str, str]:
    return {
        "MITATEDB_PROVISION_DSN": platform.provision_dsn,
        "MITATEDB_CONTROLPLANE_DSN": platform.controlplane_dsn,
        "MITATEDB_CREDENTIAL_PEPPER": platform.app_pepper,
        "MITATEDB_CONTROL_CREDENTIAL_PEPPER": platform.control_pepper,
        "MITATEDB_PLATFORM_SCHEMA": platform.schema,
    }


def _parse_issued_secret(stdout: str) -> str:
    for line in stdout.splitlines():
        if line.startswith("secret: "):
            return line[len("secret: "):]
    raise LauncherStartupError(f"could not find a 'secret: ' line in ops output:\n{stdout}")


def _issue_runtime_credential(platform: _Platform, application_id: str) -> str:
    """Out-of-band issuance (this peer's own precedent, `conformance_
    adapter_mitatedb_http.py::issue_credential`'s identical construction)
    -- there is no `ops issue-credential` CLI on this peer (see module
    docstring)."""
    store = PostgresCredentialStore(platform.controlplane_dsn, pepper=platform.app_pepper, schema=platform.schema)
    _credential_id, bearer = store.issue(application_id, "runtime")
    return bearer


class RealServerMitateDB:
    """The C-26 launcher registered for MitateDB-api. Provisioning is
    lazy -- see `RealServerR2db`'s identical docstring for why."""

    name = "MitateDB-api"

    def __init__(self) -> None:
        self._script_dir: Optional[Path] = None
        self._prefix: Optional[str] = None
        self._prefix_lock = None
        self._platform: Optional[_Platform] = None
        self._app: Optional[_AppInfo] = None
        self._control_secret: Optional[str] = None
        self._runtime_secret: Optional[str] = None
        self._data_handle: Optional[sh.UvicornSubprocessHandle] = None
        self._control_handle: Optional[sh.UvicornSubprocessHandle] = None
        self._nginx: Optional[sh.NginxHandle] = None
        self._nginx_prefix_dir: Optional[Path] = None
        self._listen_port: Optional[int] = None
        self._events: list[tuple[str, float]] = []
        self._started = False

    def _ensure_provisioned(self) -> None:
        if self._platform is not None:
            return
        _sweep_stale(_admin_dsn())
        self._script_dir = Path(tempfile.mkdtemp(prefix="mitatedb-c26-scripts-"))
        self._prefix = f"{_PREFIX_TAG}{secrets.token_hex(8)}"
        self._prefix_lock = _claim_prefix_lock(self._prefix)
        self._platform = _bootstrap_platform(self._prefix, _admin_dsn(), self._script_dir)
        self._app = _provision_app(self._platform, self._script_dir, "c26app")
        self._runtime_secret = _issue_runtime_credential(self._platform, self._app.application_id)
        bootstrapped = _run_ops(_ops_env(self._platform), "bootstrap")
        if bootstrapped.returncode != 0:
            raise LauncherStartupError(f"ops bootstrap failed:\n{bootstrapped.stdout}\n{bootstrapped.stderr}")
        self._control_secret = _parse_issued_secret(bootstrapped.stdout)

    def startup_events(self) -> list[str]:
        return [label for label, _ in self._events]

    def _record(self, label: str) -> None:
        self._events.append((label, time.monotonic()))

    # -- SQL read-back of what was actually declared (F1, WP-6c review
    # 2026-09-09) -- see `RealServerR2db.read_declared_surfaces`'s
    # identical docstring; this peer's own owner connection is `provision_
    # dsn`, not `control_dsn`. -----------------------------------------

    def read_declared_surfaces(self) -> dict[str, Any]:
        assert self._platform is not None
        with psycopg.connect(self._platform.provision_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("SELECT value FROM {}.platform_declarations WHERE key = 'surfaces'").format(
                        sql.Identifier(self._platform.schema)
                    )
                )
                row = cur.fetchone()
        if row is None:
            raise LauncherStartupError("no 'surfaces' row found in platform_declarations")
        return row[0]

    def _app_env(self) -> dict[str, str]:
        assert self._platform is not None and self._app is not None
        app_id_upper = self._app.application_id.upper()
        return {
            "MITATEDB_CREDENTIAL_PEPPER": self._platform.app_pepper,
            "MITATEDB_PLATFORM_DSN": self._platform.api_dsn,
            "MITATEDB_PLATFORM_SCHEMA": self._platform.schema,
            "MITATEDB_SERVE_APPS": self._app.application_id,
            f"MITATEDB_APP_{app_id_upper}_RUNTIME_DSN": self._app.runtime_dsn,
            f"MITATEDB_APP_{app_id_upper}_DEVELOPER_DSN": self._app.developer_dsn,
            "MITATEDB_CONTROL_PLANE_STATUS": "enabled",
        }

    def _control_env(self) -> dict[str, str]:
        assert self._platform is not None
        return {
            "MITATEDB_CREDENTIAL_PEPPER": self._platform.app_pepper,
            "MITATEDB_CONTROL_CREDENTIAL_PEPPER": self._platform.control_pepper,
            "MITATEDB_CONTROLPLANE_DSN": self._platform.controlplane_dsn,
            "MITATEDB_PLATFORM_SCHEMA": self._platform.schema,
        }

    def start(self, *, ceilings: Mapping[str, int]) -> None:
        if self._started:
            raise LauncherStartupError("start() called while already started -- call stop() or restart() first")
        self._events = []
        # F3 correction (WP-6c review 2026-09-09): see `RealServerR2db.
        # start`'s identical comment -- the ENTIRE body below is now
        # inside this one `try`, so ANY failure anywhere in `start()` runs
        # the FULL `self.stop()`, never just `_best_effort_stop_
        # processes()`.
        reservation: Optional[sh.ReservedPort] = None
        try:
            self._ensure_provisioned()
            assert self._platform is not None

            reservation = sh.reserve_port()
            listen_port = reservation.port
            data_base_url = f"http://127.0.0.1:{listen_port}/v1"
            control_base_url = f"http://127.0.0.1:{listen_port}/control/v1"

            surfaces_result = _run_ops(
                _ops_env(self._platform), "declare-surfaces",
                "--data-base-url", data_base_url, "--control-base-url", control_base_url,
            )
            if surfaces_result.returncode != 0:
                raise LauncherStartupError(f"declare-surfaces failed:\n{surfaces_result.stdout}\n{surfaces_result.stderr}")
            self._record("declare_surfaces")

            ceilings_result = _run_ops(
                _ops_env(self._platform), "declare-process-ceilings",
                "--data", str(ceilings["data"]), "--control", str(ceilings["control"]),
            )
            if ceilings_result.returncode != 0:
                raise LauncherStartupError(f"declare-process-ceilings failed:\n{ceilings_result.stdout}\n{ceilings_result.stderr}")
            self._record("declare_process_ceilings")

            assert self._script_dir is not None
            with _peer_env_prefixes_removed_from_os_environ():
                self._data_handle = sh.start_uvicorn_subprocess(
                    "mitatedb_api.main:app", pidfile=self._script_dir / "uvicorn-data.pid", env=_with_pythonpath(self._app_env()),
                )
            self._record("uvicorn_data_start")
            with _peer_env_prefixes_removed_from_os_environ():
                self._control_handle = sh.start_uvicorn_subprocess(
                    "mitatedb_api.control_main:app", pidfile=self._script_dir / "uvicorn-control.pid", env=_with_pythonpath(self._control_env()),
                )
            self._record("uvicorn_control_start")

            nginx_bin = sh.find_nginx_binary()
            nginx_dir = Path(tempfile.mkdtemp(prefix="conf-socket-"))
            prefix_dir = nginx_dir / sh.NGINX_PREFIX_MARKER
            prefix_dir.mkdir(parents=True, exist_ok=True)
            (prefix_dir / "client_body_temp").mkdir(parents=True, exist_ok=True)
            (prefix_dir / "proxy_temp").mkdir(parents=True, exist_ok=True)
            self._nginx_prefix_dir = nginx_dir
            reservation.close()
            reservation = None
            conf_path = prefix_dir / "nginx.conf"
            conf_path.write_text(sh.render_nginx_conf(
                prefix=prefix_dir, listen_port=listen_port,
                data_port=self._data_handle.port, control_port=self._control_handle.port,
            ))
            sh.check_nginx_config(nginx_bin, conf_path, prefix_dir)
            self._nginx = sh.start_nginx(nginx_bin, conf_path, prefix_dir)
            self._listen_port = listen_port
            self._record("nginx_start")

            sh.wait_until_ready(f"{data_base_url}/capabilities", label="mitatedb data")
            self._record("readiness_data")
            sh.wait_until_ready(f"{control_base_url}/capabilities", label="mitatedb control")
            self._record("readiness_control")
        except BaseException:
            if reservation is not None:
                reservation.close()
            self.stop()
            raise

        self._started = True

    def restart(self, *, ceilings: Mapping[str, int]) -> None:
        if not self._started:
            raise LauncherStartupError("restart() called before start()")
        assert self._platform is not None
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

        assert self._script_dir is not None
        with _peer_env_prefixes_removed_from_os_environ():
            self._data_handle = sh.start_uvicorn_subprocess(
                "mitatedb_api.main:app", pidfile=self._script_dir / "uvicorn-data.pid", port=data_port, env=_with_pythonpath(self._app_env()),
            )
        self._record("uvicorn_data_restart")
        with _peer_env_prefixes_removed_from_os_environ():
            self._control_handle = sh.start_uvicorn_subprocess(
                "mitatedb_api.control_main:app", pidfile=self._script_dir / "uvicorn-control.pid", port=control_port, env=_with_pythonpath(self._control_env()),
            )
        self._record("uvicorn_control_restart")

        sh.wait_until_ready(f"{self.data_base_url}/capabilities", label="mitatedb data (restart)")
        sh.wait_until_ready(f"{self.control_base_url}/capabilities", label="mitatedb control (restart)")

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
        """F3 correction (WP-6c review 2026-09-09): see `RealServerR2db.
        stop`'s identical docstring -- sweeps by `self._prefix` (set the
        moment a prefix is minted, before `_bootstrap_platform` even
        runs) via the module-level `_admin_dsn()`, so a `start()` that
        failed while `_bootstrap_platform` itself was still running
        (leaving `self._platform` unset) still gets its partial residue
        swept and its own prefix lock released here."""
        self._best_effort_stop_processes()
        self._data_handle = None
        self._control_handle = None
        self._nginx = None
        if self._nginx_prefix_dir is not None:
            shutil.rmtree(self._nginx_prefix_dir, ignore_errors=True)
            self._nginx_prefix_dir = None
        if self._prefix is not None:
            _sweep_prefix(_admin_dsn(), self._prefix)
            _release_prefix_lock(self._prefix, self._prefix_lock)
        self._prefix = None
        self._prefix_lock = None
        if self._script_dir is not None:
            shutil.rmtree(self._script_dir, ignore_errors=True)
            self._script_dir = None
        self._platform = None
        self._app = None
        self._started = False
        self._listen_port = None

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
        """Design D-1 (B) 5 / completion condition 5. See `RealServerR2db.
        attempt_start_without_process_ceilings`'s identical docstring."""
        script_dir = Path(tempfile.mkdtemp(prefix="mitatedb-c26-f15-"))
        prefix = f"{_PREFIX_TAG}{secrets.token_hex(8)}f15"
        lock = _claim_prefix_lock(prefix)
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
            app_id_upper = app.application_id.upper()
            env = _scrub_peer_env_prefixes(os.environ)
            env.update(_with_pythonpath({
                "MITATEDB_CREDENTIAL_PEPPER": platform.app_pepper,
                "MITATEDB_PLATFORM_DSN": platform.api_dsn,
                "MITATEDB_PLATFORM_SCHEMA": platform.schema,
                "MITATEDB_SERVE_APPS": app.application_id,
                f"MITATEDB_APP_{app_id_upper}_RUNTIME_DSN": app.runtime_dsn,
                f"MITATEDB_APP_{app_id_upper}_DEVELOPER_DSN": app.developer_dsn,
                "MITATEDB_CONTROL_PLANE_STATUS": "enabled",
            }))
            free_port = sh.free_port()
            result = subprocess.run(
                [sys.executable, "-m", "uvicorn", "mitatedb_api.main:app", "--host", "127.0.0.1", "--port", str(free_port)],
                env=env, capture_output=True, text=True, timeout=30,
            )
            return result
        finally:
            _sweep_prefix(_admin_dsn(), prefix)
            _release_prefix_lock(prefix, lock)
            shutil.rmtree(script_dir, ignore_errors=True)

    def attempt_start_with_lowered_role_limit(self) -> SimpleNamespace:
        """F-16 observation (Phase 10 WP-4g, supervisor ruling 2026-09-09,
        peer-symmetric with `RealServerR2db.attempt_start_with_lowered_
        role_limit`'s own identical reasoning). Builds a SEPARATE,
        independent throwaway platform (own prefix), with `surfaces`/
        `process_ceilings` both declared NORMALLY, provisions one
        application, then lowers that application's own `<prefix>_app_
        <id>_rt` role's real PostgreSQL `CONNECTION LIMIT` below `check_
        role_connection_limits`'s own declared-concurrency floor. This
        role is chosen over the platform-wide `<prefix>svc_api` role
        `attempt_start_without_process_ceilings` never touches:
        `main.py`'s own `credentials`/`ApplicationCell`s (the only things
        that ever open a REAL connection as this application's runtime
        role) are constructed strictly AFTER `declarations_conn` (the
        connection the F-16 check itself runs on) is closed -- lowering
        this role's limit can therefore never itself break the platform-
        wide pools this attempt still needs.

        Runs `python -m uvicorn mitatedb_api.main:app` directly (blocking
        `subprocess.run`, real stderr captured) with the role lowered:
        this composition root must fail fast (F-16) at import time.
        Restores the SAME role's `CONNECTION LIMIT` to `-1` (unlimited)
        and starts the IDENTICAL composition root again (via `socket_
        harness.start_uvicorn_subprocess` + `wait_until_ready`, dialed
        directly at uvicorn's own bound port -- never through nginx or
        the declared-but-unreachable `surfaces` URL this method never
        binds), proving the fail-fast this observes is genuinely
        CONDITIONED on the lowered limit. Always tears its own throwaway
        platform (and the restored-attempt uvicorn subprocess, if still
        running) down before returning, whichever branch this reached."""
        script_dir = Path(tempfile.mkdtemp(prefix="mitatedb-c26-f16-"))
        prefix = f"{_PREFIX_TAG}{secrets.token_hex(8)}f16"
        lock = _claim_prefix_lock(prefix)
        restored_handle: Optional[sh.UvicornSubprocessHandle] = None
        try:
            platform = _bootstrap_platform(prefix, _admin_dsn(), script_dir)
            app = _provision_app(platform, script_dir, "f16app")
            surfaces = _run_ops(
                _ops_env(platform), "declare-surfaces",
                "--data-base-url", "http://127.0.0.1:1/v1",
                "--control-base-url", "http://127.0.0.1:1/control/v1",
            )
            if surfaces.returncode != 0:
                raise LauncherStartupError(f"declare-surfaces failed:\n{surfaces.stdout}\n{surfaces.stderr}")
            ceilings = _run_ops(
                _ops_env(platform), "declare-process-ceilings", "--data", "1", "--control", "1",
            )
            if ceilings.returncode != 0:
                raise LauncherStartupError(f"declare-process-ceilings failed:\n{ceilings.stdout}\n{ceilings.stderr}")

            runtime_role = f"{prefix}_app_{app.application_id}_rt"
            app_id_upper = app.application_id.upper()
            env = _scrub_peer_env_prefixes(os.environ)
            env.update(_with_pythonpath({
                "MITATEDB_CREDENTIAL_PEPPER": platform.app_pepper,
                "MITATEDB_PLATFORM_DSN": platform.api_dsn,
                "MITATEDB_PLATFORM_SCHEMA": platform.schema,
                "MITATEDB_SERVE_APPS": app.application_id,
                f"MITATEDB_APP_{app_id_upper}_RUNTIME_DSN": app.runtime_dsn,
                f"MITATEDB_APP_{app_id_upper}_DEVELOPER_DSN": app.developer_dsn,
                "MITATEDB_CONTROL_PLANE_STATUS": "enabled",
            }))

            admin = psycopg.connect(_admin_dsn(), autocommit=True)
            try:
                with admin.cursor() as cur:
                    cur.execute(sql.SQL("ALTER ROLE {} CONNECTION LIMIT 1").format(sql.Identifier(runtime_role)))
            finally:
                admin.close()

            lowered_port = sh.free_port()
            lowered_result = subprocess.run(
                [sys.executable, "-m", "uvicorn", "mitatedb_api.main:app", "--host", "127.0.0.1", "--port", str(lowered_port)],
                env=env, capture_output=True, text=True, timeout=30,
            )

            admin = psycopg.connect(_admin_dsn(), autocommit=True)
            try:
                with admin.cursor() as cur:
                    cur.execute(sql.SQL("ALTER ROLE {} CONNECTION LIMIT -1").format(sql.Identifier(runtime_role)))
            finally:
                admin.close()

            restored_port = sh.free_port()
            with _peer_env_prefixes_removed_from_os_environ():
                restored_handle = sh.start_uvicorn_subprocess(
                    "mitatedb_api.main:app", pidfile=script_dir / "uvicorn-f16-restored.pid",
                    port=restored_port, env=env,
                )
            restored_started = False
            try:
                sh.wait_until_ready(f"http://127.0.0.1:{restored_port}/v1/capabilities", label="mitatedb f16 restored")
                restored_started = True
            except Exception:  # noqa: BLE001 -- reported to the caller as `restored_started=False`, not raised
                restored_started = False

            return SimpleNamespace(lowered=lowered_result, restored_started=restored_started)
        finally:
            if restored_handle is not None:
                restored_handle.stop()
            _sweep_prefix(_admin_dsn(), prefix)
            _release_prefix_lock(prefix, lock)
            shutil.rmtree(script_dir, ignore_errors=True)
