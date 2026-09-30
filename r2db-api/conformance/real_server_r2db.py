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

import contextlib
import fcntl
import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping, Optional, Sequence

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


# Same knob `conformance_adapter_r2db_http.py`/`tests/test_postgres.py`
# already use for "where is the admin/superuser PostgreSQL connection for
# this repository's own throwaway-provisioning tests" -- deliberately
# reused rather than inventing a fourth name for the identical question.
ADMIN_DSN_ENV = "R2DB_TEST_ADMIN_DSN"

# This launcher's own prefix shape, distinct from every other throwaway-
# prefix convention already in this repository ("r2dbtest*"/"r2dbsvc*"/
# "r2dbmig*"/"r2dbhttp*") so its own startup-time sweep (`_sweep_stale`)
# can never collide with (and drop) a concurrently-running sibling
# adapter's own throwaway platform on a shared local cluster.
_PREFIX_TAG = "r2dbc26"

# Cross-process advisory-lock directory for `_claim_prefix_lock`/`_release_
# prefix_lock` below (F2, WP-6c review 2026-09-09) -- peer-scoped so this
# launcher's own lock files can never collide with MitateDB-api's own,
# even though `_PREFIX_TAG` already makes that collision impossible on its
# own (belt-and-suspenders, negligible cost).
_LOCK_DIR = Path(tempfile.gettempdir()) / f"conformance-{_PREFIX_TAG}-locks"


class LauncherStartupError(RuntimeError):
    """Raised on any failure to bring this launcher's real composition
    roots up -- never converted to a skip anywhere in this module (mirrors
    `socket_harness.HarnessStartupError`'s own discipline)."""


def _admin_dsn() -> str:
    dsn = os.environ.get(ADMIN_DSN_ENV)
    if not dsn:
        raise RuntimeError(
            f"{ADMIN_DSN_ENV} is not set (or is empty). "
            "tools/testpg/dsa_testpg.py sets it for each test run; "
            "there is no shared-cluster default."
        )
    return dsn


def _dsn_with(base_dsn: str, **overrides: str) -> str:
    params = conninfo_to_dict(base_dsn)
    params.update(overrides)
    return make_conninfo(**params)


# ---------------------------------------------------------------------------
# design D-4 (裁定 14/23): a tiny stdlib-only HTTP client for the
# real requests the new condition's own hold/probe methods below issue
# against THIS launcher's own running composition root -- never `httpx`
# (this file's own precedent, unlike the adapter's), mirroring `socket_
# harness.wait_until_ready`'s own bare `urllib` use.
# ---------------------------------------------------------------------------


def _get_json(url: str, bearer: str, *, timeout: float = 30.0) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"authorization": f"Bearer {bearer}"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
    return json.loads(raw) if raw else {}


def _post_json(url: str, bearer: str, body: dict[str, Any], *, timeout: float = 30.0) -> dict[str, Any]:
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url, method="POST", data=data,
        headers={"authorization": f"Bearer {bearer}", "content-type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
    return json.loads(raw) if raw else {}


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
    """Runs the REAL `python -m r2db_api.ops` CLI as a real subprocess
    (design D-1 (B) 1: "実 CLI で") -- `env` is merged over a copy of this
    launcher process' own OS environment, with both peers' own env-var
    prefixes scrubbed first (F6, WP-6c review 2026-09-09; see
    `_scrub_peer_env_prefixes`'s own docstring), so this CLI invocation
    sees the same PATH/venv-derived environment the eventual app
    subprocess will, but none of either peer's own ambient config leaking
    in from the operator's shell. Never raises on a non-zero exit -- the
    fail-fast test needs the raw `CompletedProcess` to inspect `returncode`
    /`stderr` itself."""
    full_env = _scrub_peer_env_prefixes(os.environ)
    full_env.update(_with_pythonpath(dict(env)))
    return subprocess.run(
        [sys.executable, "-m", "r2db_api.ops", *args],
        capture_output=True, text=True, env=full_env,
    )


def _run_preflight(module: str, env: Mapping[str, str]) -> subprocess.CompletedProcess:
    """Runs the documented composition root's own entry (`python -m
    <module> --preflight`) as a real, separate, SHORT-LIVED subprocess --
    the SAME env (scrubbed/PYTHONPATH-prepended the same way `_run_ops`
    already does) the eventual long-lived uvicorn subprocess for that SAME
    module gets, so a fail-fast (F-15/F-16/F-18/registry/pepper/the
    workers-vs-ceiling check a future WP adds) is observed in exactly the
    shape a real `ExecStartPre=`/CMD-prefixed deployment would hit it,
    before any worker ever binds a socket. `--preflight` is accepted even
    before `main.py`/`control_main.py` gain a dedicated CLI branch for it:
    `sys.argv` today simply never reads it, never silently swallowed by an
    existing argument parser that would otherwise reject an unknown flag.

    What this actually checks TODAY differs by module: `r2db_api.main`
    and `mitatedb_api.main`/`mitatedb_api.control_main` all build their own
    `app` at IMPORT time (a bare module-level `app = build_app()`/`app =
    build_control_app()`), so running any of those three directly already
    exercises every startup-time check `build_app()`/`build_control_app()`
    makes, exiting non-zero with the SAME `PlatformDeclarationError`/
    `RuntimeError` a normal startup would raise (printed to stderr with
    its own raising source line, including its own `code=\"F-15\"`/
    `\"F-16\"` keyword argument text) on failure. `r2db_api.control_main`
    is the ONE exception: its own `app` is built LAZILY, through a module
    `__getattr__` a bare `python -m r2db_api.control_main` import never
    triggers (no code anywhere in that module ever reads `.app` for its
    own sake) -- this call therefore checks NOTHING for r2db's own control
    plane today and exits 0 unconditionally, whatever `env` holds."""
    full_env = _scrub_peer_env_prefixes(os.environ)
    full_env.update(_with_pythonpath(dict(env)))
    return subprocess.run(
        [sys.executable, "-m", module, "--preflight"],
        capture_output=True, text=True, env=full_env, timeout=60,
    )


def _write_access_log_config(config_path: Path, log_path: Path) -> None:
    """design D-4 (裁定 17/32): a `logging.config.dictConfig`-
    shaped JSON file that adds a `FileHandler` for uvicorn's own `uvicorn.
    access` logger, formatted to carry `%(process)d` -- the responding
    worker's own pid -- on every access-log line, and writes it to `log_
    path` regardless of this subprocess' own stdout/stderr (`start_
    uvicorn_subprocess` redirects both to `DEVNULL`). Handed to uvicorn via
    the `UVICORN_LOG_CONFIG` ENV variable (click's own `auto_envvar_prefix
    = \"UVICORN\"`, `uvicorn/main.py`), never a `--log-config` argv literal
    this file's own touched-paths list never asked `socket_harness.start_
    uvicorn_subprocess` to grow a passthrough for. Each worker under a
    `--workers >= 2` supervisor re-applies this SAME config independently
    (`Config.load()` runs once per worker process), so every worker's own
    pid appears distinctly (measured directly, 監督実施 2026-09-28: `PID=
    <pid> <host>:<port> - \"GET ...\"` lines, one worker per accepted
    connection)."""
    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"r113_pid_access": {"format": "PID=%(process)d %(message)s"}},
        "handlers": {
            "r113_access_file": {
                "class": "logging.FileHandler",
                "filename": str(log_path),
                "formatter": "r113_pid_access",
            },
        },
        "loggers": {
            "uvicorn.access": {"handlers": ["r113_access_file"], "level": "INFO", "propagate": False},
        },
    }
    config_path.write_text(json.dumps(config))


_ACCESS_LOG_LINE_RE = re.compile(r"^PID=(\d+) .*\" (\d+)\s*$")


def _access_log_line_count(log_path: Path) -> int:
    """Current number of lines in `log_path` (0 when it does not exist
    yet) -- a caller takes this BEFORE its own drive so it can later read
    only the lines a specific drive itself appended (`since=`, below)."""
    if not log_path.exists():
        return 0
    return len(log_path.read_text().splitlines())


def _access_log_pids_for_status(log_path: Path, status: int, *, since: int = 0) -> list[int]:
    """Reads back `log_path` (written by the `_write_access_log_config`
    config above) and returns the responding worker's own pid for every
    line, AFTER the first `since` lines, whose HTTP status matches
    `status`, in file order (one entry per request, duplicates included --
    the caller decides whether it cares about the SET of pids or the
    COUNT of matching lines). `since` (default 0, the whole file) lets a
    caller scope this to lines its OWN drive appended, excluding earlier
    unrelated traffic (fixture setup, an earlier drive in the same
    module)."""
    pids: list[int] = []
    if not log_path.exists():
        return pids
    for line in log_path.read_text().splitlines()[since:]:
        match = _ACCESS_LOG_LINE_RE.match(line.strip())
        if match is None:
            continue
        pid, status_text = int(match.group(1)), int(match.group(2))
        if status_text == status:
            pids.append(pid)
    return pids


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
    control_dsn: str
    api_dsn: str
    controlplane_dsn: str
    auditreader_dsn: str
    schema: str
    platform_db: str
    app_pepper: str
    control_pepper: str


@dataclass(frozen=True)
class _AppInfo:
    slug: str
    runtime_dsn: str
    developer_dsn: str


@dataclass
class _EntityLockHold:
    """Handle returned by `RealServerR2db.hold_entity_storage_lock`
    (design 裁定14) -- `hold_s` is the computed upper bound
    (完了条件 7) the holder thread will release by itself if `release_
    now()` is never called."""

    hold_s: float
    _thread: threading.Thread
    _release_now: threading.Event

    def release_now(self) -> None:
        self._release_now.set()
        self._thread.join(timeout=10.0)


def _bootstrap_platform(prefix: str, admin_dsn: str, script_dir: Path) -> _Platform:
    """Runs the real migrations `0001`..`0003`, `0005`..`0008`, `0012`,
    `0013` (with the literal token `r2dbsvc` textually replaced by
    `prefix`) through the real `psql` binary. `0004` (deprovision) is not
    needed -- this launcher's own teardown drops the whole prefix at once
    (`_sweep_prefix`), never one application at a time. `0008`/`0012` (the
    `platform_declarations` table + its `process_ceilings` key) ARE run
    here, unlike `conformance_adapter_r2db_http.py`'s own `_bootstrap_
    platform` -- that adapter injects `surfaces` directly and never goes
    through the declaration table at all (LQ4-11, design D-4); this
    launcher's whole point is exercising that exact table through the
    real `ops declare-surfaces`/`declare-process-ceilings` CLI.

    Phase 10 WP-4g (test-fixture-blast-radius fix, mirrors WP-4f's own
    fix to every OTHER real-PG fixture this repository has): `0013_role_
    connection_limits.sql` raises `r2dbsvc_api`/`r2dbsvc_controlplane`'s
    own `CONNECTION LIMIT` (and `begin_provision_application`'s own
    per-application default, for every application provisioned AFTER
    this point) to each role's real pool-composition floor. Without it,
    this launcher's own `r2dbsvc_api` role is left at 0005's original
    `CONNECTION LIMIT 10` -- below `check_role_connection_limits`'s own
    floor of 64 -- and EVERY real composition-root startup this launcher
    ever attempts fails fast on F-16 regardless of anything a caller
    does afterward (WP-4f's own investigated-and-fixed conformance
    finding, just never previously applied to this file, which predates
    that WP by one merge). Run immediately after `0012` (order relative
    to `0009`/`0010`/`0011` does not matter, this file's own header) and,
    critically, BEFORE `_provision_app` is ever called for this
    platform -- `begin_provision_application`'s replaced definition
    (section 3 of `0013`) is what gives every application THIS launcher
    provisions its own `CONNECTION LIMIT 36` from the moment it is
    created, never the pre-0013 `20`/`10` defaults `0002`/`0006` would
    otherwise leave it at."""
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
        "0014_auditreader_statement_timeout.sql",
        "0008_platform_declarations_and_writer_timeouts.sql",
        "0012_process_ceilings.sql",
        "0013_role_connection_limits.sql",
        # design D-3 (1): the credential-keyed
        # `requests_per_minute` rate table -- depends only on 0005 above.
        "0015_credential_request_rate.sql",
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
    _run_psql(control_dsn, rewritten["0014_auditreader_statement_timeout.sql"])
    _run_psql(
        control_dsn, rewritten["0008_platform_declarations_and_writer_timeouts.sql"],
        {"api_role": api_role, "controlplane_role": controlplane_role},
    )
    _run_psql(control_dsn, rewritten["0012_process_ceilings.sql"])
    _run_psql(control_dsn, rewritten["0013_role_connection_limits.sql"])
    _run_psql(control_dsn, rewritten["0015_credential_request_rate.sql"])

    # design D-3 (5): `check_role_connection_limits` (F-16) multiplies
    # the controlplane/auditreader floors (`_CONTROLPLANE_ROLE_POOL_FLOOR`/
    # `_AUDITREADER_ROLE_POOL_FLOOR`, 16/4) by `process_ceilings.control`;
    # 0013's own CONNECTION LIMIT (20/5) covers a control ceiling of 1
    # only. This launcher's conformance lifecycle declares a control
    # ceiling of 2, so both roles are set here, once, up front, to values
    # that meet the F-16 floors for 2 control processes (16*2=32,
    # 4*2=8) -- the provisioning step any deployment declaring
    # `process_ceilings.control` >= 2 needs (F-16 otherwise stops control
    # startup and reports the exact floor).
    with psycopg.connect(control_dsn) as _conn:
        with _conn.cursor() as _cur:
            _cur.execute(sql.SQL("ALTER ROLE {} CONNECTION LIMIT 32").format(sql.Identifier(controlplane_role)))
            _cur.execute(sql.SQL("ALTER ROLE {} CONNECTION LIMIT 8").format(sql.Identifier(auditreader_role)))
        _conn.commit()

    return _Platform(
        prefix=prefix,
        admin_dsn=admin_dsn,
        control_dsn=control_dsn,
        api_dsn=_dsn_with(admin_dsn, user=api_role, password=api_password, dbname=platform_db),
        controlplane_dsn=_dsn_with(admin_dsn, user=controlplane_role, password=controlplane_password, dbname=platform_db),
        auditreader_dsn=_dsn_with(admin_dsn, user=auditreader_role, password=auditreader_password, dbname=platform_db),
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
        self._prefix: Optional[str] = None
        self._prefix_lock = None
        self._platform: Optional[_Platform] = None
        self._app: Optional[_AppInfo] = None
        self._control_credential_id: Optional[str] = None
        self._control_secret: Optional[str] = None
        self._runtime_secret: Optional[str] = None
        # 完了条件 14/15: a developer credential, issued
        # alongside the runtime one, so `create_probe_entity` can call the
        # real `POST /v1/schema/operations` endpoint (schema operations
        # require a developer credential, never runtime).
        self._developer_secret: Optional[str] = None
        self._data_handle: Optional[sh.UvicornSubprocessHandle] = None
        self._control_handle: Optional[sh.UvicornSubprocessHandle] = None
        # design D-3 (2') / 完了条件 4: an `mkdtemp`ed-per-
        # `start()` directory (mode 0700 by `mkdtemp`'s own default),
        # handed to the data plane via `R2DB_SLOT_DIR` -- design D-3 wires it
        # into `concurrency`'s host-shared slot. `stop()` removes it.
        self._slot_dir: Optional[Path] = None
        # 完了条件 6: the data plane's own pid-tagged access
        # log path (`_write_access_log_config`) -- `stop()` removes the
        # small config file that names it (`_access_log_config_path`), the
        # log itself lives in `_script_dir` and is swept with it.
        self._access_log_path: Optional[Path] = None
        self._access_log_config_path: Optional[Path] = None
        # The data plane's own most recent preflight `CompletedProcess`
        # (argv/returncode/stdout/stderr) -- `data_preflight_result`
        # exposes it so a test can confirm the preflight one-shot itself
        # actually ran (not merely that an event label was recorded).
        self._data_preflight_result: Optional[subprocess.CompletedProcess] = None
        # The data plane's own declared ceiling and worker count from the
        # most recent `start()`/`restart()` call -- `data_multi_process_
        # mapping_configured()` reads both.
        self._last_data_ceiling: Optional[int] = None
        self._last_data_workers: Optional[int] = None
        # The coalescing window (ms) the most recent `start()` declared
        # through `ops declare-coalescing-window`; `None` when that call
        # was not asked for one (the platform's own default then applies).
        self._declared_coalescing_window_ms: Optional[int] = None
        # R-44 WP-3 (e), W44-3-9: the data/control upstream port
        # reservations this launcher itself owns for its whole lifetime --
        # `start()` mints both and `restart()` hands the SAME two objects
        # back to `start_uvicorn_subprocess(reserved=...)` (never a fresh
        # `reserve_port()`), so a restart never re-opens the bind-race
        # window `port=<int>` re-binding used to leave; `stop()` closes
        # both.
        self._data_reservation: Optional[sh.ReservedPort] = None
        self._control_reservation: Optional[sh.ReservedPort] = None
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
        self._prefix = f"{_PREFIX_TAG}{secrets.token_hex(8)}"
        self._prefix_lock = _claim_prefix_lock(self._prefix)
        self._platform = _bootstrap_platform(self._prefix, _admin_dsn(), self._script_dir)
        self._app = _provision_app(self._platform, self._script_dir, "c26app")
        issued = _run_ops(_ops_env(self._platform), "issue-credential", self._app.slug, "runtime")
        if issued.returncode != 0:
            raise LauncherStartupError(f"issue-credential failed:\n{issued.stdout}\n{issued.stderr}")
        self._runtime_secret = _parse_issued_secret(issued.stdout)
        # 完了条件 14/15: a developer credential too --
        # `create_probe_entity` needs one (schema operations are refused
        # for a runtime credential, C-02/C-14).
        issued_developer = _run_ops(_ops_env(self._platform), "issue-credential", self._app.slug, "developer")
        if issued_developer.returncode != 0:
            raise LauncherStartupError(f"issue-credential (developer) failed:\n{issued_developer.stdout}\n{issued_developer.stderr}")
        self._developer_secret = _parse_issued_secret(issued_developer.stdout)
        bootstrapped = _run_ops(_ops_env(self._platform), "bootstrap")
        if bootstrapped.returncode != 0:
            raise LauncherStartupError(f"ops bootstrap failed:\n{bootstrapped.stdout}\n{bootstrapped.stderr}")
        self._control_secret = _parse_issued_secret(bootstrapped.stdout)
        # `control_bearer` alone cannot self-rotate: the control plane's
        # must_rotate gate requires the rotate path's `credential_id` to
        # equal this credential's own id, and the contract forbids
        # deriving `credential_id` from the secret -- so this reads the
        # id off the same `ops bootstrap` output `control_bearer` above
        # already reads, rather than parsing it out of the secret.
        for line in bootstrapped.stdout.splitlines():
            if line.startswith("credential_id: "):
                self._control_credential_id = line[len("credential_id: "):]
                break
        else:
            raise LauncherStartupError(f"could not find a 'credential_id: ' line in ops output:\n{bootstrapped.stdout}")

    # -- events (design D-1 (B) 1's own ordering, test 1) -------------

    def startup_events(self) -> list[str]:
        return [label for label, _ in self._events]

    def _record(self, label: str) -> None:
        self._events.append((label, time.monotonic()))

    # -- per-process env (F8, WP-6c review 2026-09-09: `start()` and
    # `restart()` build the IDENTICAL two dicts -- a single place for each
    # avoids the drift risk of fixing one copy and not the other; mirrors
    # MitateDB-api's own `_app_env`/`_control_env` shape) ----------------

    def _app_env(self) -> dict[str, str]:
        assert self._platform is not None and self._app is not None
        slug_upper = self._app.slug.upper()
        return {
            "R2DB_CREDENTIAL_PEPPER": self._platform.app_pepper,
            "R2DB_PLATFORM_DSN": self._platform.api_dsn,
            "R2DB_PLATFORM_SCHEMA": self._platform.schema,
            "R2DB_SERVE_APPS": self._app.slug,
            f"R2DB_APP_{slug_upper}_RUNTIME_DSN": self._app.runtime_dsn,
            f"R2DB_APP_{slug_upper}_DEVELOPER_DSN": self._app.developer_dsn,
            "R2DB_CONTROL_PLANE_STATUS": "enabled",
        }

    def _control_env(self) -> dict[str, str]:
        assert self._platform is not None
        return {
            "R2DB_CREDENTIAL_PEPPER": self._platform.app_pepper,
            "R2DB_CONTROL_CREDENTIAL_PEPPER": self._platform.control_pepper,
            "R2DB_CONTROLPLANE_DSN": self._platform.controlplane_dsn,
            "R2DB_PLATFORM_SCHEMA": self._platform.schema,
            "R2DB_AUDIT_DSN": self._platform.auditreader_dsn,
        }

    # -- SQL read-back of what was actually declared (F1, WP-6c review
    # 2026-09-09) -----------------------------------------------------

    def read_declared_surfaces(self) -> dict[str, Any]:
        """Reads the `surfaces` row directly from `platform_declarations`
        over SQL -- never through the served capabilities document --
        using the SAME `control_dsn` connection `_bootstrap_platform`
        itself used to create that table (schema owner, so no separate
        GRANT bookkeeping is needed here). This is completion condition
        2's own decisive cross-check (design D-1 (B) 2): the value a
        served capabilities document reports for `surfaces` must not only
        be self-consistent between planes but must actually MATCH what
        `ops declare-surfaces` persisted, not something the launcher's
        own `data_base_url`/`control_base_url` PROPERTIES independently
        computed."""
        assert self._platform is not None
        with psycopg.connect(self._platform.control_dsn) as conn:
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

    # -- per-start data-plane env (workers/slot directory/access log,
    # design D-3 (2')/D-4 ----------------------------------------------

    def _data_env(self, *, workers: int) -> dict[str, str]:
        assert self._slot_dir is not None and self._access_log_config_path is not None
        env = dict(self._app_env())
        env["R2DB_WORKERS"] = str(workers)
        env["R2DB_SLOT_DIR"] = str(self._slot_dir)
        env["UVICORN_LOG_CONFIG"] = str(self._access_log_config_path)
        return env

    def _control_env_with_workers(self) -> dict[str, str]:
        # 監督裁定 4 (§6.1): control plane also passes `--workers` from the
        # SAME env-variable shape, always 1 (`R2DB_CONTROL_WORKERS`) --
        # `--workers` is never lifted above 1 here.
        env = dict(self._control_env())
        env["R2DB_CONTROL_WORKERS"] = "1"
        return env

    # -- start/restart/stop --------------------------------------------

    def start(
        self, *, ceilings: Mapping[str, int], workers: int = 1,
        coalescing_window_ms: Optional[int] = None,
        audit_writer_timeouts_ms: Optional[tuple[int, int]] = None,
    ) -> None:
        """`coalescing_window_ms` (declared through the real `ops
        declare-coalescing-window`) and `audit_writer_timeouts_ms` (a
        `(statement, idle)` pair declared through the real `ops
        set-platform-timeouts`, which is what the served `visibility_lag_ms`
        derives from) are the two knobs a condition that reads audit
        evidence back through `audit_query` turns to keep its own poll
        short; both default to `None`, which leaves the platform's own
        declarations untouched."""
        if self._started:
            raise LauncherStartupError("start() called while already started -- call stop() or restart() first")
        self._events = []
        self._last_data_ceiling = ceilings["data"]
        self._last_data_workers = workers
        self._declared_coalescing_window_ms = coalescing_window_ms
        # F3 correction (WP-6c review 2026-09-09): the ENTIRE body below
        # -- `_ensure_provisioned()` (which can itself leave a throwaway
        # platform DB/role behind if it fails partway), the port
        # reservation, both `declare-*` CLI calls, both uvicorn
        # subprocess starts, and the nginx/readiness sequence -- is now
        # inside this one `try`, so ANY failure anywhere in `start()`
        # (not merely the previous nginx-onward slice) runs the FULL
        # `self.stop()` (never just `_best_effort_stop_processes()`): a
        # caller that only sees an exception out of `start()` never calls
        # `stop()` itself (there is nothing "started" to stop, from its
        # own point of view), so this is the only place such residue is
        # ever swept. `reservation` is tracked outside the `try` so the
        # `except` clause can always close it, however far execution got.
        reservation: Optional[sh.ReservedPort] = None
        try:
            self._ensure_provisioned()
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
                raise LauncherStartupError(f"declare-surfaces failed:\n{surfaces_result.stdout}\n{surfaces_result.stderr}")
            self._record("declare_surfaces")

            ceilings_result = _run_ops(
                _ops_env(self._platform), "declare-process-ceilings",
                "--data", str(ceilings["data"]), "--control", str(ceilings["control"]),
            )
            if ceilings_result.returncode != 0:
                raise LauncherStartupError(f"declare-process-ceilings failed:\n{ceilings_result.stdout}\n{ceilings_result.stderr}")
            self._record("declare_process_ceilings")

            if coalescing_window_ms is not None:
                window_result = _run_ops(
                    _ops_env(self._platform), "declare-coalescing-window", "--ms", str(coalescing_window_ms),
                )
                if window_result.returncode != 0:
                    raise LauncherStartupError(
                        f"declare-coalescing-window failed:\n{window_result.stdout}\n{window_result.stderr}"
                    )
                self._record("declare_coalescing_window")
            if audit_writer_timeouts_ms is not None:
                timeouts_result = _run_ops(
                    _ops_env(self._platform), "set-platform-timeouts",
                    "--statement-ms", str(audit_writer_timeouts_ms[0]), "--idle-ms", str(audit_writer_timeouts_ms[1]),
                )
                if timeouts_result.returncode != 0:
                    raise LauncherStartupError(
                        f"set-platform-timeouts failed:\n{timeouts_result.stdout}\n{timeouts_result.stderr}"
                    )
                self._record("set_platform_timeouts")

            assert self._script_dir is not None
            # design D-3 (2') / 完了条件 4/6: a fresh slot directory
            # (also re-minted on every `restart()`, below) and an
            # access-log config that keeps naming the same log file for
            # this instance's whole lifetime.
            self._slot_dir = Path(tempfile.mkdtemp(prefix="r2db-c26-slots-"))
            self._access_log_path = self._script_dir / "uvicorn-data-access.log"
            self._access_log_config_path = self._script_dir / "uvicorn-data-access-logconfig.json"
            _write_access_log_config(self._access_log_config_path, self._access_log_path)

            pidfile_data = self._script_dir / "uvicorn-data.pid"
            pidfile_control = self._script_dir / "uvicorn-control.pid"

            # design D-1 (裁定 26): a preflight one-shot for
            # EACH plane, in the SAME env its own long-lived uvicorn
            # subprocess below gets, before that subprocess ever starts --
            # `build_app()`'s startup-time checks are observed here, not
            # only inside the (harder to distinguish) supervisor.
            data_env = self._data_env(workers=workers)
            preflight_data = _run_preflight("r2db_api.main", data_env)
            self._data_preflight_result = preflight_data
            if preflight_data.returncode != 0:
                raise LauncherStartupError(
                    f"preflight (r2db_api.main) failed:\n{preflight_data.stdout}\n{preflight_data.stderr}"
                )
            self._record("preflight_data")
            control_env = self._control_env_with_workers()
            preflight_control = _run_preflight("r2db_api.control_main", control_env)
            if preflight_control.returncode != 0:
                raise LauncherStartupError(
                    f"preflight (r2db_api.control_main) failed:\n{preflight_control.stdout}\n{preflight_control.stderr}"
                )
            self._record("preflight_control")

            # R-44 WP-3 (e): each upstream gets its OWN `reserve_port()`
            # reservation, held by THIS launcher (never the handle -- W44-
            # 3-5's own caller-owns-when-reserved-is-given rule) for as
            # long as the surface lives, so `restart()` below can hand the
            # identical reservation back in rather than re-binding a bare
            # port number.
            self._data_reservation = sh.reserve_port()
            with _peer_env_prefixes_removed_from_os_environ():
                self._data_handle = sh.start_uvicorn_subprocess(
                    "r2db_api.main:app", pidfile=pidfile_data,
                    reserved=self._data_reservation, env=_with_pythonpath(data_env),
                    workers=workers,
                )
            self._record("uvicorn_data_start")
            self._control_reservation = sh.reserve_port()
            with _peer_env_prefixes_removed_from_os_environ():
                self._control_handle = sh.start_uvicorn_subprocess(
                    "r2db_api.control_main:app", pidfile=pidfile_control,
                    reserved=self._control_reservation, env=_with_pythonpath(control_env),
                    workers=1,
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

            sh.wait_until_ready(f"{data_base_url}/capabilities", label="r2db data")
            self._record("readiness_data")
            sh.wait_until_ready(f"{control_base_url}/capabilities", label="r2db control")
            self._record("readiness_control")
        except BaseException:
            if reservation is not None:
                reservation.close()
            self.stop()
            raise

        self._started = True

    def restart(self, *, ceilings: Mapping[str, int], workers: int = 1) -> None:
        """Re-declares `process_ceilings` (real CLI), then stops and
        restarts ONLY the two uvicorn subprocesses, on the SAME ports --
        nginx (and therefore the already-declared `surfaces` URL) is left
        untouched, matching a real redeploy that restarts the app
        processes behind a stable reverse proxy. `declare-process-
        ceilings` is written to the REAL, DB-side table via the real CLI
        BEFORE either process restarts (design D-5 (ii): "起動時スナップ
        ショットのため" -- the new value only takes effect once both
        processes come back up). The slot directory is re-minted here too
        (a fresh `mkdtemp`, the old one removed) -- both `start()` and
        `restart()` are their own "起動", each with its own directory; the
        access-log config keeps naming the SAME log file for this
        instance's whole lifetime (`stop()` removes both)."""
        if not self._started:
            raise LauncherStartupError("restart() called before start()")
        assert self._platform is not None and self._app is not None
        assert self._data_handle is not None and self._control_handle is not None
        self._last_data_ceiling = ceilings["data"]
        self._last_data_workers = workers

        ceilings_result = _run_ops(
            _ops_env(self._platform), "declare-process-ceilings",
            "--data", str(ceilings["data"]), "--control", str(ceilings["control"]),
        )
        if ceilings_result.returncode != 0:
            raise LauncherStartupError(f"declare-process-ceilings failed:\n{ceilings_result.stdout}\n{ceilings_result.stderr}")
        self._record("declare_process_ceilings_restart")

        # R-44 WP-3 (e), W44-3-9: the SAME two reservations `start()`
        # minted are handed back in below (never a fresh `reserve_port()`
        # / a bare `port=<int>` re-bind) -- this is what actually closes
        # the bind-race window a restart used to re-open (W44-3-5's own
        # reason 1: nginx's conf already names these upstream ports and
        # never reloads).
        assert self._data_reservation is not None and self._control_reservation is not None
        self._data_handle.stop()
        self._control_handle.stop()

        # Both uvicorn subprocesses are down now -- safe to remove the
        # OLD slot directory and mint a fresh one for this restart (裁定
        # 27's own "起動ごとの mkdtemp" applies to `restart()` too, not
        # only the launcher's first `start()`).
        assert self._slot_dir is not None
        shutil.rmtree(self._slot_dir, ignore_errors=True)
        self._slot_dir = Path(tempfile.mkdtemp(prefix="r2db-c26-slots-"))

        assert self._script_dir is not None
        data_env = self._data_env(workers=workers)
        preflight_data = _run_preflight("r2db_api.main", data_env)
        self._data_preflight_result = preflight_data
        if preflight_data.returncode != 0:
            raise LauncherStartupError(
                f"preflight (r2db_api.main, restart) failed:\n{preflight_data.stdout}\n{preflight_data.stderr}"
            )
        self._record("preflight_data_restart")
        control_env = self._control_env_with_workers()
        preflight_control = _run_preflight("r2db_api.control_main", control_env)
        if preflight_control.returncode != 0:
            raise LauncherStartupError(
                f"preflight (r2db_api.control_main, restart) failed:\n{preflight_control.stdout}\n{preflight_control.stderr}"
            )
        self._record("preflight_control_restart")

        with _peer_env_prefixes_removed_from_os_environ():
            self._data_handle = sh.start_uvicorn_subprocess(
                "r2db_api.main:app", pidfile=self._script_dir / "uvicorn-data.pid",
                reserved=self._data_reservation, env=_with_pythonpath(data_env),
                workers=workers,
            )
        self._record("uvicorn_data_restart")
        with _peer_env_prefixes_removed_from_os_environ():
            self._control_handle = sh.start_uvicorn_subprocess(
                "r2db_api.control_main:app", pidfile=self._script_dir / "uvicorn-control.pid",
                reserved=self._control_reservation, env=_with_pythonpath(control_env),
                workers=1,
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
        # R-44 WP-3 (e), W44-3-5: this launcher (never the handle) owns
        # the data/control port reservations for its whole lifetime --
        # closing them here, alongside the two uvicorn subprocesses and
        # nginx above, is what actually releases the ports; `start_
        # uvicorn_subprocess(reserved=...)` never closes a caller-supplied
        # reservation itself.
        for reservation in (self._data_reservation, self._control_reservation):
            if reservation is not None:
                try:
                    reservation.close()
                except Exception:  # noqa: BLE001
                    pass

    def stop(self) -> None:
        """Stops both uvicorn subprocesses and nginx, then drops the
        throwaway platform (every database/role under this run's own
        prefix). Idempotent -- a second call with nothing left running is
        a no-op. F3 correction (WP-6c review 2026-09-09): sweeps by
        `self._prefix` (set the moment a prefix is minted in `_ensure_
        provisioned`, before `_bootstrap_platform` even runs) rather than
        `self._platform.prefix`, and always via the module-level `_admin_
        dsn()` -- so a `start()` that failed WHILE `_bootstrap_platform`
        itself was still running (leaving `self._platform` unset) still
        gets its partial DB/role residue swept and its own prefix lock
        released here, not left behind."""
        self._best_effort_stop_processes()
        self._data_handle = None
        self._control_handle = None
        self._data_reservation = None
        self._control_reservation = None
        self._nginx = None
        if self._nginx_prefix_dir is not None:
            shutil.rmtree(self._nginx_prefix_dir, ignore_errors=True)
            self._nginx_prefix_dir = None
        # 完了条件 4: the per-instance slot directory never
        # outlives this launcher instance.
        if self._slot_dir is not None:
            shutil.rmtree(self._slot_dir, ignore_errors=True)
            self._slot_dir = None
        self._access_log_path = None
        self._access_log_config_path = None
        self._data_preflight_result = None
        self._last_data_ceiling = None
        self._last_data_workers = None
        self._declared_coalescing_window_ms = None
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
        self._developer_secret = None
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

    def issue_runtime_credential(self) -> str:
        """Issues a NEW, independent runtime credential for the served
        application and returns its bearer -- distinct from `runtime_
        bearer` (the one `_ensure_provisioned` mints once). A caller
        exercising a request-rate-scoped observation uses one of these,
        never shared with any other observation, so two observations
        never count against the same credential's own window."""
        assert self._platform is not None and self._app is not None
        issued = _run_ops(_ops_env(self._platform), "issue-credential", self._app.slug, "runtime")
        if issued.returncode != 0:
            raise LauncherStartupError(f"issue-credential (extra runtime) failed:\n{issued.stdout}\n{issued.stderr}")
        return _parse_issued_secret(issued.stdout)

    def issue_runtime_credential_with_id(self) -> tuple[str, str]:
        """Like `issue_runtime_credential`, but also returns the new
        credential's own id -- `(credential_id, bearer)` -- which is the
        `actor_id` every audit event that credential produces carries."""
        assert self._platform is not None and self._app is not None
        issued = _run_ops(_ops_env(self._platform), "issue-credential", self._app.slug, "runtime")
        if issued.returncode != 0:
            raise LauncherStartupError(f"issue-credential (extra runtime) failed:\n{issued.stdout}\n{issued.stderr}")
        for line in issued.stdout.splitlines():
            if line.startswith("credential_id: "):
                return line[len("credential_id: "):], _parse_issued_secret(issued.stdout)
        raise LauncherStartupError(f"could not find a 'credential_id: ' line in ops output:\n{issued.stdout}")

    def issue_audit_credential(self) -> str:
        """Issues a NEW `role=audit` control-plane credential (out of
        band, `ops issue-audit-credential`) and returns its bearer -- the
        only kind of control credential `audit_query` answers to without a
        rotation first."""
        assert self._platform is not None
        issued = _run_ops(_ops_env(self._platform), "issue-audit-credential")
        if issued.returncode != 0:
            raise LauncherStartupError(f"issue-audit-credential failed:\n{issued.stdout}\n{issued.stderr}")
        return _parse_issued_secret(issued.stdout)

    @property
    def control_bearer(self) -> str:
        assert self._control_secret is not None
        return self._control_secret

    @property
    def control_credential_id(self) -> str:
        assert self._control_credential_id is not None
        return self._control_credential_id

    @property
    def developer_bearer(self) -> str:
        assert self._developer_secret is not None
        return self._developer_secret

    @property
    def data_preflight_result(self) -> subprocess.CompletedProcess:
        """The data plane's own most recent preflight `CompletedProcess`
        -- `.args` names the real argv (`--preflight`/`r2db_api.main`
        included), `.returncode`/`.stdout`/`.stderr` are the real
        subprocess result, so a caller can confirm the preflight one-shot
        genuinely ran rather than merely trusting a recorded event
        label."""
        assert self._data_preflight_result is not None
        return self._data_preflight_result

    def data_multi_process_mapping_configured(self) -> bool:
        """True exactly when the most recent `start()`/`restart()` call
        configured the data plane the way design 裁定27 requires for its
        `limit_enforcement` mapping to read `enforced`: the slot directory
        conveyed (always true once this launcher has started at all) AND
        this supervisor's own `workers` equal to the declared data-plane
        `process_ceilings` value. Used to cross-check a served `enforced`/
        `deployment_required` declaration against what THIS launcher
        actually configured (design 裁定12: a peer may honestly declare
        either at ceiling >= 2; `enforced` binds the new condition, `
        deployment_required` does not) -- never trusted blindly either
        way: a declared `enforced` while this returns `False`, or a
        declared `deployment_required` while this returns `True`, are
        both a mismatch a caller must treat as a failure, not a silent
        skip."""
        return (
            self._slot_dir is not None
            and self._last_data_ceiling is not None
            and self._last_data_workers is not None
            and self._last_data_workers == self._last_data_ceiling
        )

    def data_rate_row_configured(self) -> bool:
        """design D-3 (4), 裁定 18/27: `requests_per_minute`'s own mapping
        to `enforced` depends ONLY on whether the PostgreSQL-backed
        rate-row strategy is wired at all -- never on `workers` vs.
        `process_ceilings`, unlike `concurrency`'s own host-shared slot
        (`data_multi_process_mapping_configured`). This class always
        starts the documented, real production composition root, which
        always wires that strategy once its own migration exists (there
        is no env toggle that turns it off) -- this accessor is therefore
        unconditionally `True` here. A FUTURE launcher kind that starts a
        composition root known to keep the rate window in-memory (never
        wiring the PostgreSQL-backed strategy) would return `False`
        instead; nothing this class represents does that."""
        return True

    def coalescing_window_ms(self) -> int:
        """The coalescing window (ms) the most recent `start()` declared;
        `start()` must have been given one."""
        assert self._declared_coalescing_window_ms is not None, "start() was not given a coalescing_window_ms"
        return self._declared_coalescing_window_ms

    # -- worker processes of the data plane (uvicorn `--workers >= 2`) --

    def worker_pids(self) -> list[int]:
        """The pids of the data plane's worker processes, sorted: every
        live member of the supervisor's own process group except the
        supervisor itself and the `multiprocessing` resource tracker the
        supervisor starts for its spawned workers (measured: a
        `--workers 2` group holds the supervisor, that tracker and the two
        workers, all under the one pgid)."""
        assert self._data_handle is not None
        supervisor_pid = self._data_handle.process.pid
        members = sh._pids_with_pgid(supervisor_pid)
        excluded = {supervisor_pid}
        excluded.update(pid for pid in members if "multiprocessing.resource_tracker" in sh._process_cmdline(pid))
        return sorted(pid for pid in members if pid not in excluded)

    def kill_workers(self, pids: Sequence[int], *, timeout_s: float = 60.0) -> list[int]:
        """SIGKILLs each pid in `pids` (each must be a member of the data
        plane's process group other than the supervisor), then waits until
        each is gone (`os.kill(pid, 0)` raises `ProcessLookupError`: the
        supervisor has reaped it) and until the supervisor has started
        replacements, i.e. `worker_pids()` again lists as many workers as
        the last `start()`/`restart()` asked for and none of the killed
        ones. Returns the replacement pids, sorted. A replacement is listed
        as soon as its process exists, before it serves. The signal goes out
        before any wait, so the gap between a caller's last response and
        the kill stays short."""
        assert self._data_handle is not None and self._last_data_workers is not None
        supervisor_pid = self._data_handle.process.pid
        members = set(sh._pids_with_pgid(supervisor_pid))
        refused = [pid for pid in pids if pid == supervisor_pid or pid not in members]
        if refused:
            raise LauncherStartupError(f"kill_workers: {refused!r} are not workers of this launcher's data plane")
        for pid in pids:
            os.kill(pid, signal.SIGKILL)
        deadline = time.monotonic() + timeout_s
        while True:
            gone = []
            for pid in pids:
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    gone.append(pid)
            current = self.worker_pids()
            if len(gone) == len(pids) and len(current) == self._last_data_workers and not set(current) & set(pids):
                return [pid for pid in current if pid not in members]
            if time.monotonic() >= deadline:
                raise LauncherStartupError(
                    f"kill_workers: after {timeout_s}s {len(pids) - len(gone)} killed worker(s) were still present "
                    f"or the supervisor had not restored {self._last_data_workers} workers (now {current!r})"
                )
            time.sleep(0.2)

    # -- pid-tagged data-plane access log --

    def access_log_line_count(self) -> int:
        """Current line count of the data plane's own access log -- a
        caller takes this BEFORE its own drive so `access_log_pids_for_
        status(..., since=...)` can later read only the lines that drive
        itself appended."""
        assert self._access_log_path is not None
        return _access_log_line_count(self._access_log_path)

    def access_log_pids_for_status(self, status: int, *, since: int = 0) -> list[int]:
        assert self._access_log_path is not None
        return _access_log_pids_for_status(self._access_log_path, status, since=since)

    # -- new condition (a)/(b) support (design D-4) --

    def create_probe_entity(self, entity_name: str, field_names: Sequence[str]) -> None:
        """A real `POST /v1/schema/operations` call, under the developer
        credential, creating `entity_name` with `field_names` (untyped --
        `json`, contract default) -- so `hold_entity_storage_lock` below
        has a REAL table to lock (a freshly provisioned application starts
        with none)."""
        _post_json(
            f"{self.data_base_url}/schema/operations", self.developer_bearer,
            {"operation": "create_entity", "entity": entity_name, "fields": list(field_names)},
        )

    def _locking_dsn(self) -> str:
        assert self._platform is not None and self._app is not None
        database = conninfo_to_dict(self._app.runtime_dsn)["dbname"]
        return _dsn_with(self._platform.admin_dsn, dbname=database)

    def _application_role_statement_timeout_ms(self) -> float:
        assert self._app is not None
        with psycopg.connect(self._app.runtime_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT setting FROM pg_settings WHERE name = 'statement_timeout'")
                (value,) = cur.fetchone()
        value_ms = int(value)
        # `0` means "disabled" (no timeout), never "instant" -- excluded
        # from the `min()` below via +inf, not treated as the tightest
        # bound.
        return float(value_ms) if value_ms > 0 else float("inf")

    def _declared_execution_ms(self, *, bearer: Optional[str] = None) -> float:
        doc = _get_json(f"{self.data_base_url}/capabilities", bearer or self.runtime_bearer)
        return float(doc["limits"]["execution_ms"])

    def retained_lock_hold_s(self, *, bearer: Optional[str] = None) -> float:
        """完了条件 7: strictly shorter than min(declared `execution_ms`,
        the application runtime role's own real `statement_timeout`) -- a
        real margin (half), never equal to either. `bearer` (default the
        launcher's own `runtime_bearer`) lets a caller read the document
        under a credential OTHER than the shared default one, so this
        call's own GET does not count against a rate observation another
        caller is making with the default credential."""
        bound_s = min(self._application_role_statement_timeout_ms(), self._declared_execution_ms(bearer=bearer)) / 1000.0
        return bound_s * 0.5

    def hold_entity_storage_lock(self, entity_name: str, *, bearer: Optional[str] = None) -> _EntityLockHold:
        """Opens ITS OWN privileged connection (never the served
        application's own runtime/developer role -- the admin DSN,
        redirected at the application's own database) and holds `entity_
        name`'s own table under `LOCK TABLE ... IN ACCESS EXCLUSIVE MODE`
        for up to `retained_lock_hold_s()` seconds (or until `.release_
        now()` is called, whichever is first) in a background thread, so
        the caller can drive concurrent requests against `entity_name`
        WHILE the lock is held. `application_name` names this launcher's
        own pid (`\"r2db:lockholder:<pid>\"`) -- distinct from either
        plane's own served connections (`\"r2db:<plane>:<pid>\"`), so
        `lock_waiter_application_names` below never counts the holder
        itself as a waiter. `bearer` is forwarded to `retained_lock_hold_
        s()` only (this method itself never authenticates as the served
        application)."""
        hold_s = self.retained_lock_hold_s(bearer=bearer)
        started = threading.Event()
        release_now = threading.Event()
        error: list[BaseException] = []

        def _worker() -> None:
            try:
                conn = psycopg.connect(self._locking_dsn(), application_name=f"r2db:lockholder:{os.getpid()}")
            except BaseException as exc:  # noqa: BLE001 -- reported to the caller via `error`, never raised here
                error.append(exc)
                started.set()
                return
            try:
                try:
                    with conn.cursor() as cur:
                        cur.execute(sql.SQL("LOCK TABLE {} IN ACCESS EXCLUSIVE MODE").format(sql.Identifier(entity_name)))
                except BaseException as exc:  # noqa: BLE001 -- reported to the caller via `error`, never raised here
                    error.append(exc)
                    return
                started.set()
                release_now.wait(timeout=hold_s)
            finally:
                if not started.is_set():
                    started.set()
                conn.rollback()
                conn.close()

        thread = threading.Thread(target=_worker, name="r2db-lockholder", daemon=True)
        thread.start()
        if not started.wait(timeout=10.0):
            raise LauncherStartupError(f"hold_entity_storage_lock({entity_name!r}) never acquired its lock within 10s")
        if error:
            raise LauncherStartupError(f"hold_entity_storage_lock({entity_name!r}) failed: {error[0]!r}")
        return _EntityLockHold(hold_s=hold_s, _thread=thread, _release_now=release_now)

    def lock_waiter_application_names(self, entity_name: str) -> list[str]:
        """The distinct `application_name` values of every session
        currently WAITING to acquire a lock on `entity_name`'s own
        relation (`pg_locks` joined to `pg_stat_activity`, `granted =
        false`) -- read from the SAME privileged connection kind `hold_
        entity_storage_lock` uses, a fresh one each call (never held
        open)."""
        with psycopg.connect(self._locking_dsn()) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT DISTINCT a.application_name "
                    "FROM pg_locks l JOIN pg_stat_activity a ON a.pid = l.pid "
                    "WHERE l.relation = %s::regclass AND l.granted = false",
                    [entity_name],
                )
                return [row[0] for row in cur.fetchall()]

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
            slug_upper = app.slug.upper()
            f15_slot_dir = Path(tempfile.mkdtemp(prefix="r2db-c26-f15-slots-"))
            try:
                env = _scrub_peer_env_prefixes(os.environ)
                env.update(_with_pythonpath({
                    "R2DB_CREDENTIAL_PEPPER": platform.app_pepper,
                    "R2DB_PLATFORM_DSN": platform.api_dsn,
                    "R2DB_PLATFORM_SCHEMA": platform.schema,
                    "R2DB_SERVE_APPS": app.slug,
                    f"R2DB_APP_{slug_upper}_RUNTIME_DSN": app.runtime_dsn,
                    f"R2DB_APP_{slug_upper}_DEVELOPER_DSN": app.developer_dsn,
                    "R2DB_CONTROL_PLANE_STATUS": "enabled",
                    "R2DB_WORKERS": "1",
                    "R2DB_SLOT_DIR": str(f15_slot_dir),
                }))
                # `process_ceilings` is deliberately never declared above --
                # `build_app()` must fail fast (F-15) at IMPORT time, which
                # means the uvicorn *process itself* never reaches "serving"
                # -- `subprocess.run` (not the harness' fire-and-forget
                # `Popen`) is used here specifically so this call blocks until
                # that failure actually happens and captures its real stderr.
                # R-44 WP-3 (e), R-19: a `reserve_port()` reservation, handed
                # to uvicorn via `--fd`/`pass_fds` (never a bare `--port`), so
                # this fail-fast observation is never confused with a lost
                # bind race against some concurrent xdist worker's own
                # harness surface.
                f15_reservation = sh.reserve_port()
                try:
                    f15_fd = f15_reservation.sock.fileno()
                    result = subprocess.run(
                        [sys.executable, "-m", "uvicorn", "r2db_api.main:app", "--host", "127.0.0.1", "--fd", str(f15_fd)],
                        env=env, capture_output=True, text=True, timeout=30, pass_fds=(f15_fd,),
                    )
                finally:
                    f15_reservation.close()
                return result
            finally:
                shutil.rmtree(f15_slot_dir, ignore_errors=True)
        finally:
            _sweep_prefix(_admin_dsn(), prefix)
            _release_prefix_lock(prefix, lock)
            shutil.rmtree(script_dir, ignore_errors=True)

    def attempt_start_without_process_ceilings_multi_worker(self, *, workers: int = 2) -> subprocess.CompletedProcess:
        """C-26 (5)'s `workers >= 2` form (design D-1, 裁定 26, 完了条件
        13): the SAME shape as `attempt_start_without_process_ceilings`
        above (a separate, independent throwaway platform, `surfaces`
        declared, `process_ceilings` deliberately never declared), but
        this time via the `preflight` one-shot (`_run_preflight`) instead
        of a direct `python -m uvicorn ...` run -- the workers >= 2
        startup FORM is "preflight -> supervisor" (裁定 26), and this
        method deliberately never reaches the second half: the supervisor
        (`start_uvicorn_subprocess`) is structurally never even called
        here, mirroring exactly what `start()`'s own preflight-failure
        path does (raise before ever starting a supervisor)."""
        script_dir = Path(tempfile.mkdtemp(prefix="r2db-c26-f15w-"))
        prefix = f"{_PREFIX_TAG}{secrets.token_hex(8)}f15w"
        lock = _claim_prefix_lock(prefix)
        try:
            platform = _bootstrap_platform(prefix, _admin_dsn(), script_dir)
            app = _provision_app(platform, script_dir, "f15wapp")
            surfaces = _run_ops(
                _ops_env(platform), "declare-surfaces",
                "--data-base-url", "http://127.0.0.1:1/v1",
                "--control-base-url", "http://127.0.0.1:1/control/v1",
            )
            if surfaces.returncode != 0:
                raise LauncherStartupError(f"declare-surfaces failed:\n{surfaces.stdout}\n{surfaces.stderr}")
            slug_upper = app.slug.upper()
            slot_dir = Path(tempfile.mkdtemp(prefix="r2db-c26-f15w-slots-"))
            try:
                env = {
                    "R2DB_CREDENTIAL_PEPPER": platform.app_pepper,
                    "R2DB_PLATFORM_DSN": platform.api_dsn,
                    "R2DB_PLATFORM_SCHEMA": platform.schema,
                    "R2DB_SERVE_APPS": app.slug,
                    f"R2DB_APP_{slug_upper}_RUNTIME_DSN": app.runtime_dsn,
                    f"R2DB_APP_{slug_upper}_DEVELOPER_DSN": app.developer_dsn,
                    "R2DB_CONTROL_PLANE_STATUS": "enabled",
                    "R2DB_WORKERS": str(workers),
                    "R2DB_SLOT_DIR": str(slot_dir),
                }
                # `process_ceilings` is deliberately never declared above
                # -- the preflight one-shot must fail fast (F-15) the
                # SAME way a direct `python -m uvicorn ...` run does
                # (`attempt_start_without_process_ceilings`'s own
                # docstring): both paths hit the SAME `build_app()`.
                return _run_preflight("r2db_api.main", env)
            finally:
                shutil.rmtree(slot_dir, ignore_errors=True)
        finally:
            _sweep_prefix(_admin_dsn(), prefix)
            _release_prefix_lock(prefix, lock)
            shutil.rmtree(script_dir, ignore_errors=True)

    def attempt_control_preflight_without_process_ceilings(self) -> subprocess.CompletedProcess:
        """The control plane's own preflight one-shot, run with NO
        `process_ceilings` row declared -- the SAME shape as `attempt_
        start_without_process_ceilings` above, but targets `r2db_api.
        control_main` directly through `_run_preflight` (never a bare
        `python -m uvicorn ...`, since what this observes is the
        preflight ENTRY itself, not uvicorn's own import-time behavior).
        `_run_preflight`'s own docstring states the current gap: r2db's
        control plane builds `app` lazily, so this call is a no-op that
        exits 0 regardless of `env` today -- this method makes that gap
        directly observable by a test, not merely documented."""
        script_dir = Path(tempfile.mkdtemp(prefix="r2db-c26-f15c-"))
        prefix = f"{_PREFIX_TAG}{secrets.token_hex(8)}f15c"
        lock = _claim_prefix_lock(prefix)
        try:
            platform = _bootstrap_platform(prefix, _admin_dsn(), script_dir)
            surfaces = _run_ops(
                _ops_env(platform), "declare-surfaces",
                "--data-base-url", "http://127.0.0.1:1/v1",
                "--control-base-url", "http://127.0.0.1:1/control/v1",
            )
            if surfaces.returncode != 0:
                raise LauncherStartupError(f"declare-surfaces failed:\n{surfaces.stdout}\n{surfaces.stderr}")
            env = {
                "R2DB_CREDENTIAL_PEPPER": platform.app_pepper,
                "R2DB_CONTROL_CREDENTIAL_PEPPER": platform.control_pepper,
                "R2DB_CONTROLPLANE_DSN": platform.controlplane_dsn,
                "R2DB_PLATFORM_SCHEMA": platform.schema,
                "R2DB_CONTROL_WORKERS": "1",
            }
            # `process_ceilings` is deliberately never declared above.
            return _run_preflight("r2db_api.control_main", env)
        finally:
            _sweep_prefix(_admin_dsn(), prefix)
            _release_prefix_lock(prefix, lock)
            shutil.rmtree(script_dir, ignore_errors=True)

    def attempt_start_with_lowered_role_limit(self) -> SimpleNamespace:
        """F-16 observation (Phase 10 WP-4g, supervisor ruling 2026-09-09):
        builds a SEPARATE, independent throwaway platform (own prefix),
        with `surfaces`/`process_ceilings` both declared NORMALLY (so
        nothing other than the role limit itself is a reason this
        composition root could fail to start), provisions one
        application, then lowers that application's own `<prefix>_app_
        <slug>_runtime` role's real PostgreSQL `CONNECTION LIMIT` below
        `check_role_connection_limits`'s own declared-concurrency floor.
        This role is deliberately chosen over the platform-wide
        `<prefix>_api` role `attempt_start_without_process_ceilings`
        never touches: `main.py`'s own `_cell_factory` (the only thing
        that ever opens a REAL connection as this application's runtime
        role, via `PostgresCell`) is defined but not yet CALLED at the
        point the F-16 check itself runs (`main.py`'s own step 6b, before
        step 8's eager per-application cell loop) -- lowering this role's
        limit can therefore never itself break some OTHER pool this
        attempt still needs (the platform-wide credential-store/audit-
        sink pools all run as the DIFFERENT `<prefix>_api` role).

        Runs `python -m uvicorn r2db_api.main:app` directly (blocking
        `subprocess.run`, real stderr captured -- mirrors `attempt_start_
        without_process_ceilings`'s own reasoning) with the role lowered:
        this composition root must fail fast (F-16) at import time.
        Restores the SAME role's `CONNECTION LIMIT` to `-1` (unlimited)
        and starts the IDENTICAL composition root again (this time via
        `socket_harness.start_uvicorn_subprocess` + `wait_until_ready`,
        dialed directly at uvicorn's own bound port -- never through
        nginx or the declared-but-unreachable `surfaces` URL this method
        never binds), proving the fail-fast this observes is genuinely
        CONDITIONED on the lowered limit, not some unrelated breakage of
        this throwaway platform. Always tears its own throwaway platform
        (and the restored-attempt uvicorn subprocess, if still running)
        down before returning, whichever branch this reached."""
        script_dir = Path(tempfile.mkdtemp(prefix="r2db-c26-f16-"))
        prefix = f"{_PREFIX_TAG}{secrets.token_hex(8)}f16"
        lock = _claim_prefix_lock(prefix)
        restored_handle: Optional[sh.UvicornSubprocessHandle] = None
        f16_slot_dir: Optional[Path] = None
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

            runtime_role = f"{prefix}_app_{app.slug}_runtime"
            slug_upper = app.slug.upper()
            f16_slot_dir = Path(tempfile.mkdtemp(prefix="r2db-c26-f16-slots-"))
            env = _scrub_peer_env_prefixes(os.environ)
            env.update(_with_pythonpath({
                "R2DB_CREDENTIAL_PEPPER": platform.app_pepper,
                "R2DB_PLATFORM_DSN": platform.api_dsn,
                "R2DB_PLATFORM_SCHEMA": platform.schema,
                "R2DB_SERVE_APPS": app.slug,
                f"R2DB_APP_{slug_upper}_RUNTIME_DSN": app.runtime_dsn,
                f"R2DB_APP_{slug_upper}_DEVELOPER_DSN": app.developer_dsn,
                "R2DB_CONTROL_PLANE_STATUS": "enabled",
                "R2DB_WORKERS": "1",
                "R2DB_SLOT_DIR": str(f16_slot_dir),
            }))

            admin = psycopg.connect(_admin_dsn(), autocommit=True)
            try:
                with admin.cursor() as cur:
                    cur.execute(sql.SQL("ALTER ROLE {} CONNECTION LIMIT 1").format(sql.Identifier(runtime_role)))
            finally:
                admin.close()

            # R-44 WP-3 (e), R-19: same treatment as `attempt_start_
            # without_process_ceilings`'s own F-15 call above -- a
            # `reserve_port()` reservation handed to uvicorn via `--fd`/
            # `pass_fds`, never a bare `--port`.
            lowered_reservation = sh.reserve_port()
            try:
                lowered_fd = lowered_reservation.sock.fileno()
                lowered_result = subprocess.run(
                    [sys.executable, "-m", "uvicorn", "r2db_api.main:app", "--host", "127.0.0.1", "--fd", str(lowered_fd)],
                    env=env, capture_output=True, text=True, timeout=30, pass_fds=(lowered_fd,),
                )
            finally:
                lowered_reservation.close()

            admin = psycopg.connect(_admin_dsn(), autocommit=True)
            try:
                with admin.cursor() as cur:
                    cur.execute(sql.SQL("ALTER ROLE {} CONNECTION LIMIT -1").format(sql.Identifier(runtime_role)))
            finally:
                admin.close()

            # R-44 WP-3 (e), W44-3-10: `reserved` is omitted -- `start_
            # uvicorn_subprocess` mints its own `reserve_port()` reservation
            # and the returned handle owns it (closed by `restored_handle.
            # stop()` below).
            with _peer_env_prefixes_removed_from_os_environ():
                restored_handle = sh.start_uvicorn_subprocess(
                    "r2db_api.main:app", pidfile=script_dir / "uvicorn-f16-restored.pid", env=env,
                )
            restored_started = False
            try:
                sh.wait_until_ready(f"http://127.0.0.1:{restored_handle.port}/v1/capabilities", label="r2db f16 restored")
                restored_started = True
            except Exception:  # noqa: BLE001 -- reported to the caller as `restored_started=False`, not raised
                restored_started = False

            return SimpleNamespace(lowered=lowered_result, restored_started=restored_started)
        finally:
            if restored_handle is not None:
                restored_handle.stop()
            if f16_slot_dir is not None:
                shutil.rmtree(f16_slot_dir, ignore_errors=True)
            _sweep_prefix(_admin_dsn(), prefix)
            _release_prefix_lock(prefix, lock)
            shutil.rmtree(script_dir, ignore_errors=True)
