#!/usr/bin/env python3
"""dsa_testpg.py -- a throwaway PostgreSQL 16 cluster, one per pytest run.

Design docs/design/TEST_POSTGRES_ISOLATION_V0_1.md (v0.2) D-1..D-4, D-8 in
part. Work order docs/work-orders/WORK_ORDER_R44_TEST_PG_ISOLATION_V1.md §2.1.
Standard library only (D-1: the launcher is not a pytest plugin and is not
installed into the shared `.venv`, so it must run with nothing but the
interpreter each `conftest.py` already has).

Every connection this module hands out is a unix-socket connection to a
cluster this process started (or, for `owned:`/`external`, one a cousin
process started) under a per-user throwaway base directory -- never the
shared local PostgreSQL (`host=/tmp port=5432`) the standing MitateDB-api
service and other sessions' tests use. `TestPgError` messages never carry a
DSN or password (work order §2.1): the only things a message may show are a
socket directory path and the tail of `postgres.log`.

Three ways to get a cluster:

  - `ensure_for_pytest()` -- called at import time by the three `conftest.py`
    files (design D-1: before `pytest_configure`, because
    `conformance-tests/conftest.py` connects to PostgreSQL at ITS OWN import
    time). Idempotent; implements the decision table in `_MODE_DOC` below.
  - `start()` / `cluster()` (context manager) -- direct Python API for a
    non-pytest caller (`tools/dev/gate.py`, `tools/perf_baseline.py`, the
    integration tests in `conformance-tests/test_testpg_cluster.py`).
    `tools/dev/gate.py` and `tools/perf_baseline.py` also take `suite_lock()`
    exclusively around their own run (work order §3.1 (a)); every owned-mode
    `ensure_for_pytest()` run takes it shared for its own whole lifetime.
  - `python tools/testpg/dsa_testpg.py run -- <command...>` -- starts a
    cluster, execs `<command...>` with its environment, stops the cluster,
    and returns the command's exit code.

Lifecycle (design D-3): a small watchdog process (this same file, invoked
as `--watchdog RUN_DIR`) holds the read end of a pipe whose write end the
starting process keeps open for as long as it is alive. EOF on that pipe --
which the OS delivers whether the starting process exits normally or is
SIGKILLed, since either way it stops holding its copy of the write end --
tells the watchdog to shut the postmaster down and remove `RUN_DIR`. That
is the ONLY path that stops a cluster; `Cluster.stop()` only closes the
pipe and waits for the watchdog to finish. `sweep()` (run at the start of
every `start()`, and via the `sweep` CLI subcommand) is the safety net for
a starting process that never got to close its pipe cleanly at all (e.g. an
interpreter crash before `Cluster.stop()` could even run): it uses
`flock(2)` on each run directory's own `owner.lock`, never a bare pid
check, so a dead owner is recognized even if its pid was already recycled.
"""
from __future__ import annotations

import atexit
import dataclasses
import fcntl
import json
import os
import re
import secrets
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path


class TestPgError(Exception):
    """A precondition, startup, or teardown failure. The message may name a
    socket directory path or quote the tail of `postgres.log`; it must never
    contain a DSN or a password (work order §2.1)."""


class SuiteLockUnavailable(TestPgError):
    """The suite lock could not be taken: the wait ran out, or another LIVE
    gate already holds `gate.intent`. R-44 WP-4 (work order §5.1 (b) 4):
    split out of `TestPgError` so the tools that take the exclusive lock
    (`gate.py`, `perf_baseline.py`, `fold.py --apply`) can answer 75 (refused
    to start, try later) for this and only this, and 78 (a precondition is
    wrong: a symlinked or foreign-owned base dir, a cluster that will not
    start) for every other `TestPgError`. A subclass, so every existing
    `except TestPgError` and `pytest.raises(TestPgError)` still matches."""


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PORT = 5432
SUPERUSER = "postgres"  # design §6 Q-7: local matches CI, no OS-user superuser
MAJOR_VERSION = 16

READY_TIMEOUT = 30.0     # work order §2.1: pg_isready poll ceiling
TERM_TIMEOUT = 10.0      # watchdog: SIGTERM grace period
QUIT_TIMEOUT = 5.0       # watchdog: SIGQUIT grace period; also sweep()'s own
STOP_TIMEOUT = 30.0      # Cluster.stop(): ceiling to wait for the watchdog
SOCKET_PATH_LIMIT = 103  # work order §2.1 (measured 88 bytes under $TMPDIR, §3.4)

STAGING_PREFIX = ".starting-"  # review B-3: sweep()'s "run-*" glob never matches this prefix
STAGING_STALE_AGE = 60.0       # seconds; sweep()'s ceiling before treating a ".starting-*" as abandoned

ENV_MODE = "DSA_TEST_PG"
ENV_BINDIR = "DSA_TEST_PG_BINDIR"
ENV_REPORT = "DSA_TEST_PG_REPORT"
R2DB_DSN = "R2DB_TEST_ADMIN_DSN"
MITATEDB_DSN = "MITATEDB_TEST_ADMIN_DSN"
_DSN_NAMES = (R2DB_DSN, MITATEDB_DSN)

# Work order §3.1 (a) (WP-2, docs/work-orders/WORK_ORDER_R44_TEST_PG_ISOLATION_V1.md,
# design docs/design/TEST_POSTGRES_ISOLATION_V0_1.md v0.2 D-5/D-6, decision Q-2 (a)):
# the exclusive/shared suite lock that replaces the old `ps`-based "other pytest"
# poll and the gate-hold flag file. `SUITE_LOCK_NAME`/`GATE_INTENT_NAME` live
# directly under the base dir (never inside a `run-*` run directory), so
# `sweep()`'s own `run-*`/`.starting-*` globs never touch them.
SUITE_LOCK_NAME = "suite.lock"
GATE_INTENT_NAME = "gate.intent"
DEFAULT_LOCK_WAIT = 1800.0  # tools/dev's own --wait default budget elsewhere; the
# fallback used here when a caller does not say how long to wait
_LOCK_POLL = 0.2  # suite lock acquisition's own retry interval
ENV_LOCK_WAIT = "DSA_TEST_PG_LOCK_WAIT"  # pt.py/mutate.py forward their own --wait
# through this env var to the pytest subprocess's owned-mode lock acquisition
# below (work order §3.1 (c): "--wait は「gate の排他ロックが解けるまでの待ち」に意味を変える")
ENV_LOCK_HELD = "DSA_TEST_PG_LOCK_HELD"  # review B-1 (WP-2): set by gate.py (and any other
# exclusive holder that spawns an owned-mode NESTED pytest -- e.g. the root suite's own
# conformance-tests/test_testpg_cluster.py, which launches a genuine owned-mode controller
# as a subprocess) on the child's env. An ancestor process already holds the suite lock for
# this whole process tree, so the owned branch below must not try to acquire it again --
# doing so would DEADLOCK, not merely double-lock: the ancestor is itself blocked inside the
# very suite run this child is part of, so it can never release the lock for the child to
# wait out. Never stripped by that test's own `_clean_dsa_env()` (a fixed name list plus
# `PYTEST_*`, `conformance-tests/test_testpg_cluster.py:44-47`) -- verified by reading, not
# something this WP is allowed to edit (conformance-tests/ is WP-2's own "触らないファイル").


# ---------------------------------------------------------------------------
# The cluster handle
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class Cluster:
    """A running throwaway cluster. Fields prefixed `_` are plumbing for
    `stop()`, not part of the connection contract (that is `env()`)."""

    run_dir: Path
    socket_dir: Path
    password: str = dataclasses.field(repr=False)  # review M-6: must never reach a pytest assertion repr
    postmaster_pid: int
    _watchdog: subprocess.Popen = dataclasses.field(repr=False)
    _pipe_w: int = dataclasses.field(repr=False)
    _lock_fd: int = dataclasses.field(repr=False)
    _stopped: bool = dataclasses.field(default=False, repr=False)

    def env(self) -> dict[str, str]:
        """Variables a child process needs to reach THIS cluster, including
        with no host of its own written down (work order §2.1's connection-
        info table). DSNs never carry a password -- `PGPASSFILE` is the only
        path a password travels."""
        host = str(self.socket_dir)
        dsn = f"host={host} port={PORT} dbname=postgres user={SUPERUSER}"
        return {
            R2DB_DSN: dsn,
            MITATEDB_DSN: dsn,
            "PGHOST": host,
            "PGPORT": str(PORT),
            "PGUSER": SUPERUSER,
            "PGPASSFILE": str(self.run_dir / "pgpass"),
        }

    def stop(self) -> None:
        """Close the pipe the watchdog is reading and wait for it to finish
        tearing the cluster down (design D-3: the watchdog is the single
        path that stops a postmaster and removes `run_dir`; this method
        does not touch either itself). Idempotent."""
        if self._stopped:
            return
        self._stopped = True
        os.close(self._pipe_w)
        try:
            self._watchdog.wait(timeout=STOP_TIMEOUT)
        except subprocess.TimeoutExpired as exc:
            raise TestPgError(
                f"watchdog for {self.run_dir} did not exit within {STOP_TIMEOUT}s"
            ) from exc
        finally:
            # Best-effort reap of the postmaster: it is a direct child of
            # THIS process (design D-2, not the watchdog's child), so once
            # the watchdog's own signals have stopped it, only this process
            # can collect its exit status. Never blocks: by the time the
            # watchdog itself has exited, the postmaster is already gone or
            # never will be reaped by us at all (both harmless).
            try:
                os.waitpid(self.postmaster_pid, os.WNOHANG)
            except ChildProcessError:
                pass
            try:
                os.close(self._lock_fd)
            except OSError:
                pass


@contextmanager
def cluster():
    """`with cluster() as c:` -- start a throwaway cluster and guarantee
    `stop()` on the way out, including on an exception."""
    c = start()
    try:
        yield c
    finally:
        c.stop()


# ---------------------------------------------------------------------------
# suite_lock(): exclusive (gate.py / perf_baseline.py) vs shared (every other
# owned-mode pytest run) mutual exclusion (work order §3.1 (a)). This is a
# real flock(2), not a re-checked file: once a caller decides to acquire, the
# flock call itself is what serializes concurrent acquirers, so there is no
# gap between "checked" and "got it" the way there would be with a plain
# file-existence check. `gate.intent` exists only to stop a steady stream of
# NEW shared acquisitions from starving a pending exclusive one (flock is not
# guaranteed fair): a shared acquirer waits for it to stop being LIVE before
# even trying to flock `suite.lock` -- liveness is itself verified by a
# flock ON the intent file (review M-1, `_intent_is_live()` below), never
# merely inferred from the file's existence, so a gate that died without
# running its own cleanup (`kill -9`, a crash) cannot wedge every future
# acquirer forever.
# ---------------------------------------------------------------------------

def _intent_path(base: Path) -> Path:
    return base / GATE_INTENT_NAME


def _suite_lock_path(base: Path) -> Path:
    return base / SUITE_LOCK_NAME


def _intent_is_live(intent: Path) -> bool:
    """True only if a REAL, live gate holds `gate.intent`'s own flock
    (review M-1): liveness must be VERIFIED, never merely inferred from the
    file's existence -- the exclusive branch below used to create it with
    `O_EXCL` and remove it only from `release()`, so a gate killed with
    `kill -9` (or a machine crash mid-gate) left the file behind forever;
    every subsequent shared acquirer then spun for its own full `wait`
    budget, every new gate was refused immediately, and `gate_running()`
    reported READY-blocking forever -- the whole machine wedged.

    A file whose flock CAN be taken (`LOCK_EX|LOCK_NB` succeeds) is stale:
    the kernel already dropped whatever lock a dead process held, exactly
    as for `owner.lock`/`sweep()` (`_looks_like_our_postmaster`'s own
    reasoning). This function reclaims that flock just long enough to
    confirm staleness, then releases it and removes the file -- so callers
    (a shared waiter, `gate_running()`, `sweep()`) never have to special-
    case "stale" themselves; they simply see "not live" and proceed."""
    try:
        fd = os.open(intent, os.O_RDWR)
    except OSError:
        return False  # already gone -- never existed, or another racer's own cleanup
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True  # a live gate holds it
        fcntl.flock(fd, fcntl.LOCK_UN)
        intent.unlink(missing_ok=True)
        return False
    finally:
        os.close(fd)


class _SuiteLockHandle:
    """What `_acquire_suite_lock()` returns. `release()` is idempotent so it
    is safe both from a `with suite_lock(...):` block's own `finally` and
    from `stop_owned()` (owned-mode `ensure_for_pytest()` holds one of these
    across the whole pytest run, past any single `with` block)."""

    def __init__(self, fd: int, intent_fd: int | None, intent: Path | None) -> None:
        self._fd = fd
        self._intent_fd = intent_fd
        self._intent = intent
        self._released = False

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        try:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
        finally:
            os.close(self._fd)
            if self._intent_fd is not None:
                try:
                    fcntl.flock(self._intent_fd, fcntl.LOCK_UN)
                finally:
                    os.close(self._intent_fd)
                    if self._intent is not None:
                        self._intent.unlink(missing_ok=True)


def _acquire_suite_lock(exclusive: bool, wait: float, base: Path | None = None) -> _SuiteLockHandle:
    """`wait` is one shared budget covering both phases below (never two
    separate `wait`-length waits stacked). Exclusive: claims `gate.intent`'s
    OWN flock first -- `TestPgError` immediately (no waiting) if a LIVE gate
    already holds it (work order §3.1 (b): "gate は... 排他ロックを取る"),
    reclaiming it silently if it is merely a stale leftover (review M-1) --
    then flocks `LOCK_EX` on `suite.lock`. Shared: waits for the intent to
    stop being LIVE (`_intent_is_live()`, not mere existence), then flocks
    `LOCK_SH`. Either flock acquisition polls `LOCK_NB` at `_LOCK_POLL`
    (`fcntl.flock` has no native timeout) and raises `SuiteLockUnavailable`
    (a `TestPgError` subclass; R-44 WP-4: a bad base dir from `_base_dir()`
    stays a plain `TestPgError`) past the deadline, cleaning up whatever this
    call itself created (the intent file/flock, the open fd) before
    re-raising -- never leaves a stray `gate.intent` or leaks an fd on a
    timeout."""
    base = _base_dir() if base is None else base
    deadline = time.monotonic() + wait
    intent = _intent_path(base)
    intent_fd = None
    if exclusive:
        intent_fd = os.open(intent, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(intent_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(intent_fd)
            raise SuiteLockUnavailable(f"gate intent already present (another gate running?): {intent}")
        # Own the flock now (freshly created, or reclaimed from a stale leftover either way) --
        # record OUR pid so a future stale-check has something meaningful to have overwritten.
        os.ftruncate(intent_fd, 0)
        os.write(intent_fd, str(os.getpid()).encode("ascii"))
    else:
        while _intent_is_live(intent):
            if time.monotonic() >= deadline:
                raise SuiteLockUnavailable(f"timed out after {wait}s waiting for gate intent to clear: {intent}")
            time.sleep(_LOCK_POLL)
    lock_path = _suite_lock_path(base)
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    want = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
    try:
        while True:
            try:
                fcntl.flock(fd, want | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise SuiteLockUnavailable(
                        f"timed out after {wait}s waiting for the "
                        f"{'exclusive' if exclusive else 'shared'} suite lock: {lock_path}"
                    )
                time.sleep(_LOCK_POLL)
    except BaseException:
        os.close(fd)
        if intent_fd is not None:
            fcntl.flock(intent_fd, fcntl.LOCK_UN)
            os.close(intent_fd)
            intent.unlink(missing_ok=True)
        raise
    return _SuiteLockHandle(fd, intent_fd, intent if intent_fd is not None else None)


@contextmanager
def suite_lock(exclusive: bool, wait: float, base: Path | None = None):
    """`with suite_lock(True, 1800):` -- gate.py / perf_baseline.py's own
    single-run exclusivity. Every other pytest run's own shared hold is
    taken directly via `_acquire_suite_lock()` by `ensure_for_pytest()`
    instead (see its own call site below), not through this context
    manager, because it must outlive any single `with` block: it is held
    for the whole pytest run and released by `stop_owned()`."""
    handle = _acquire_suite_lock(exclusive, wait, base)
    try:
        yield
    finally:
        handle.release()


def _resolve_base_dir_readonly(uid: int | None = None, tmp_root: Path | None = None) -> Path | None:
    """Same path formula as `_base_dir()`, but NEVER creates anything
    (review MINOR-4): `gate_running()` is documented read-only, and
    `_base_dir()` itself always `mkdir`s (side effect a probe must not
    have). Returns None when the base dir does not exist yet (or fails
    `_base_dir()`'s own symlink/foreign-owner checks -- a probe reports
    "not running" rather than raising)."""
    uid = os.getuid() if uid is None else uid
    tmp_root = tmp_root if tmp_root is not None else Path(tempfile.gettempdir())
    base = tmp_root / f"dsa-testpg-{uid}"
    try:
        if not base.is_dir():
            return None
        st = base.lstat()
        if stat.S_ISLNK(st.st_mode) or st.st_uid != uid:
            return None
    except OSError:
        return None
    return base


def gate_running(base: Path | None = None) -> tuple[bool, str]:
    """Non-blocking, read-only probe for `tools/dev/handover_ready.py` (work
    order §3.1 (c): replaces its old "no pytest process" + "gate-hold flag
    absent" pair with this single check). True when `gate.intent` is LIVE
    (review M-1: verified via `_intent_is_live()`, not mere existence -- a
    stale intent from a crashed gate is cleaned up as a side effect and
    correctly reported as "not running"), or when `suite.lock` exists and a
    SHARED lock attempt on it (`LOCK_SH|LOCK_NB`) is refused, which only an
    EXCLUSIVE holder can cause. R-44 WP-4 (work order §5.1 (b) 1, §4.1;
    code review 1): the probe is a SHARED attempt, not the old exclusive
    one, because an exclusive attempt also fails whenever any ordinary
    owned-mode pytest run holds the shared side, which made a plain test
    run block a handover (measured 2026-09-16); a shared holder alone is
    therefore `(False, "")`. The lock attempt is kept next to the intent
    check because the intent alone is not proof: a gate's intent file can be
    unlinked by a racing release or a racing stale-reclaim while that gate
    still holds `suite.lock` exclusively (reviewer reproduction, WP-4; the
    unlink race itself is left as an observation). Never blocks, never
    waits, and (review MINOR-4) never CREATES the base dir or any file, so
    this probe can neither delay a real waiter nor materialize state that
    was never there; a successful attempt is released immediately."""
    if base is None:
        base = _resolve_base_dir_readonly()
        if base is None:
            return False, ""
    elif not base.is_dir():
        return False, ""
    intent = _intent_path(base)
    if intent.exists() and _intent_is_live(intent):
        return True, f"gate intent present: {intent}"
    lock_path = _suite_lock_path(base)
    if not lock_path.exists():
        return False, ""
    fd = os.open(lock_path, os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
    except BlockingIOError:
        return True, f"exclusive suite lock held: {lock_path}"
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False, ""
    finally:
        os.close(fd)


# ---------------------------------------------------------------------------
# Binary discovery and version check
# ---------------------------------------------------------------------------

def _bindir() -> Path:
    """`DSA_TEST_PG_BINDIR` if set, else `pg_config --bindir`, else PATH
    (an empty `Path("")` -- `_binary()` below then passes the bare name,
    letting the OS resolve it via PATH)."""
    explicit = os.environ.get(ENV_BINDIR)
    if explicit:
        return Path(explicit)
    try:
        proc = subprocess.run(["pg_config", "--bindir"], capture_output=True, text=True, check=True)
        return Path(proc.stdout.strip())
    except (OSError, subprocess.CalledProcessError):
        return Path("")


def _binary(bindir: Path, name: str) -> str:
    return str(bindir / name) if str(bindir) else name


_VERSION_RE = re.compile(r"PostgreSQL\)\s+(\d+)")


def parse_major_version(version_output: str) -> int | None:
    """The leading major-version number of `postgres --version`'s stdout
    (e.g. `postgres (PostgreSQL) 16.14` -> 16), or None if unparseable.
    A standalone function so the unit tests can feed literal strings
    without running a real `postgres` binary."""
    m = _VERSION_RE.search(version_output)
    return int(m.group(1)) if m else None


def _check_version(bindir: Path) -> None:
    exe = _binary(bindir, "postgres")
    try:
        proc = subprocess.run([exe, "--version"], capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise TestPgError(f"cannot run '{exe} --version': {exc}") from exc
    major = parse_major_version(proc.stdout)
    if major != MAJOR_VERSION:
        raise TestPgError(
            f"'{exe} --version' reports {proc.stdout.strip()!r}, need major version {MAJOR_VERSION}"
        )


# ---------------------------------------------------------------------------
# Base directory (design D-2: user-scoped, under $TMPDIR, never a fixed
# name under /tmp and never Drive-synced)
# ---------------------------------------------------------------------------

def _base_dir(uid: int | None = None, tmp_root: Path | None = None) -> Path:
    """`uid`/`tmp_root` are overridable only so `tools/tests/test_testpg.py`
    can exercise the ownership/symlink checks below against a `tmp_path`
    without being able to actually own a directory as a different uid; real
    callers always take the defaults (the real caller's uid, `tempfile.
    gettempdir()`)."""
    uid = os.getuid() if uid is None else uid
    tmp_root = tmp_root if tmp_root is not None else Path(tempfile.gettempdir())
    base = tmp_root / f"dsa-testpg-{uid}"
    try:
        base.mkdir(mode=0o700)
        os.chmod(base, 0o700)  # mkdir's mode is subject to umask
    except FileExistsError:
        st = base.lstat()
        if stat.S_ISLNK(st.st_mode):
            raise TestPgError(f"base dir is a symlink, refusing to use it: {base}")
        if st.st_uid != uid:
            raise TestPgError(f"base dir is owned by another user, refusing to use it: {base}")
    return base


def _clean_env() -> dict[str, str]:
    """The caller's environment with every `PG*` variable removed (so a
    stray `PGHOST`/`PGPASSFILE` etc. from an outer cluster's env never
    leaks into `initdb`/`postgres`) and `LC_ALL=en_US.UTF-8` forced --
    without it, `postgres` exits with "postmaster became multithreaded
    during startup" on macOS (design §3.4, D-2)."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("PG")}
    env["LC_ALL"] = "en_US.UTF-8"
    return env


# ---------------------------------------------------------------------------
# pid / ps helpers shared by sweep() and the watchdog
# ---------------------------------------------------------------------------

def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, just not signalable by us -- still alive
    return True


_PROC_ROOT = Path("/proc")


def _ps_args(pid: int, proc_root: Path = _PROC_ROOT) -> str | None:
    """`pid`'s full command line as one string, or None when it cannot be
    read (no such process, or a zombie, whose argv is gone). Where
    `proc_root` exists (Linux), reads `<proc_root>/<pid>/cmdline` -- the
    NUL-separated argv, joined with spaces -- the same form
    `conformance-tests/socket_harness.py` reads (on the Linux CI runner
    the earlier `ps -o args=` form reported a live process as not ours;
    why was not measured). Elsewhere (macOS, which has no `/proc`):
    `ps -ww -o args= -p <pid>`, `-ww` so the line is never cut to a
    terminal width."""
    if proc_root.is_dir():
        try:
            raw = (proc_root / str(pid) / "cmdline").read_bytes()
        except OSError:
            return None
        return raw.replace(b"\x00", b" ").decode(errors="replace").strip() or None
    proc = subprocess.run(["ps", "-ww", "-o", "args=", "-p", str(pid)], capture_output=True, text=True)
    out = proc.stdout.strip()
    return out or None


def _looks_like_our_postmaster(pid: int, data_dir: Path) -> bool:
    """Guards every signal this module sends to a pid it did not just fork
    itself: its argv (`_ps_args`) must still name THIS run's data directory, so a
    pid recycled by an unrelated process after the real postmaster already
    exited is never signalled (work order §2.1: "pid 再利用の防止")."""
    if not _pid_alive(pid):
        return False
    args = _ps_args(pid)
    return args is not None and str(data_dir) in args


def _signal_and_wait(pid: int, sig: int, timeout: float, alive=_pid_alive) -> bool:
    """Send `sig` (skipped if `alive(pid)` is already False) then poll
    `alive` for it to become False. Returns True once confirmed gone.

    `alive` defaults to a bare pid check, but the watchdog and `sweep()`
    instead pass an identity check bound to the run's own data directory
    (review M-1): once signalled, the postmaster becomes a zombie whose
    parent (the process that forked it, design D-2 -- never this function's
    own caller) has not reaped it yet, and `kill(pid, 0)` on a zombie still
    succeeds -- a bare liveness poll would then burn this function's full
    `timeout` on every single clean stop. The argv read for a zombie no
    longer names the data directory, so `_looks_like_our_postmaster`
    correctly reports it as gone immediately instead."""
    if not alive(pid):
        return True
    try:
        os.kill(pid, sig)
    except ProcessLookupError:
        return True
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not alive(pid):
            return True
        time.sleep(0.1)
    return not alive(pid)


def _read_meta(run_dir: Path) -> dict | None:
    try:
        return json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def _log_tail(log_path: Path, lines: int = 40) -> str:
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "(no log)"
    return "\n".join(text.splitlines()[-lines:])


# ---------------------------------------------------------------------------
# sweep(): clean up run directories a dead starting process left behind
# ---------------------------------------------------------------------------

def sweep(base: Path | None = None) -> None:
    """Remove every `run-*` directory under the base dir whose `owner.lock`
    is NOT held by a live process (work order §2.1). A directory whose lock
    IS held is a live run and is never touched, so this is safe to call
    from any process at any time, including concurrently with a live run's
    own `start()`.

    `base` defaults through `_base_dir()` -- not a re-derived copy of its
    formula -- so the symlink/foreign-owner guard applies here too (review
    B-2: the previous re-derivation bypassed it, including for the public
    `sweep` CLI subcommand, and `rmtree` is exactly the operation that
    guard exists to gate). A caller that already validated a `base` (or is
    a test exercising a `tmp_path`) may still pass one explicitly.

    Also cleans up a stale `gate.intent` (review M-1: a gate `kill -9`ed or
    crashed leaves that file behind, and only its own `release()` used to
    remove it -- `_intent_is_live()` verifies liveness via flock and
    unlinks the file itself when it is stale; a live one is left alone)."""
    base = _base_dir() if base is None else base
    if not base.is_dir():
        return
    for run_dir in sorted(base.glob("run-*")):
        _sweep_one(run_dir)
    for staging_dir in sorted(base.glob(f"{STAGING_PREFIX}*")):
        _sweep_stale_staging(staging_dir)
    intent = _intent_path(base)
    if intent.exists():
        _intent_is_live(intent)  # review M-1: side effect only -- unlinks it if stale, leaves a live one alone


def _sweep_stale_staging(staging_dir: Path) -> None:
    """A `.starting-*` directory (see `start()`/`_start_in()`) is the brief
    window between `mkdtemp` and the rename to `run-*` (review B-3) --
    `sweep()`'s own `run-*` glob above never matches it, by construction,
    so a starting process that crashes inside that window (before it can
    even take its own lock and rename) would otherwise leak forever.
    Age-gated, not lock-gated: at this stage the directory may not even
    have an `owner.lock` yet, so a concurrent, still-in-progress `start()`
    is protected by staleness alone -- STAGING_STALE_AGE is far above the
    ~1s `initdb` + `postgres` startup this window actually spans (design
    §3.4)."""
    try:
        age = time.time() - staging_dir.stat().st_mtime
    except OSError:
        return
    if age < STAGING_STALE_AGE:
        return
    shutil.rmtree(staging_dir, ignore_errors=True)


def _sweep_one(run_dir: Path) -> None:
    lock_path = run_dir / "owner.lock"
    try:
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    except OSError:
        return  # cannot even open the lock file -- leave the directory alone
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return  # a live process holds the lock: this is a live run, not dead
        _terminate_if_ours(run_dir)
        shutil.rmtree(run_dir, ignore_errors=True)
    finally:
        os.close(fd)  # also releases the flock


def _terminate_if_ours(run_dir: Path) -> None:
    """Only reached once the owner is confirmed dead (the lock was free).
    Stops the abandoned postmaster (SIGQUIT, then SIGKILL if it is still
    alive after QUIT_TIMEOUT) -- but only when `_looks_like_our_postmaster`
    still recognizes the pid, so a reused pid is never signalled. Polls
    that same identity check (not bare liveness) while waiting, for the
    same zombie reason as the watchdog (review M-1)."""
    meta = _read_meta(run_dir)
    pid = meta.get("pid") if meta else None
    if not isinstance(pid, int) or not _looks_like_our_postmaster(pid, run_dir / "data"):
        return
    data_dir = run_dir / "data"

    def alive(p: int) -> bool:
        return _looks_like_our_postmaster(p, data_dir)

    if _signal_and_wait(pid, signal.SIGQUIT, QUIT_TIMEOUT, alive=alive):
        return
    _signal_and_wait(pid, signal.SIGKILL, QUIT_TIMEOUT, alive=alive)


# ---------------------------------------------------------------------------
# Watchdog (this file, invoked as `--watchdog RUN_DIR`)
# ---------------------------------------------------------------------------

def _watchdog_main(run_dir: Path) -> int:
    """Block reading stdin until EOF, then stop the postmaster and remove
    `run_dir`. EOF arrives however the starting process stops holding its
    copy of the pipe's write end -- a clean `Cluster.stop()` closing it
    explicitly, a normal interpreter exit, or a SIGKILL the OS cannot
    intercept but which still closes every fd of the dying process (design
    D-3)."""
    while True:
        if not os.read(0, 4096):
            break
    meta = _read_meta(run_dir)
    pid = meta.get("pid") if meta else None
    if isinstance(pid, int) and _looks_like_our_postmaster(pid, run_dir / "data"):
        data_dir = run_dir / "data"

        def alive(p: int) -> bool:
            return _looks_like_our_postmaster(p, data_dir)

        # SIGTERM (10s) -> SIGQUIT (5s) -> SIGKILL (work order §2.1). Polls
        # identity, not bare liveness (review M-1): after a signal the
        # postmaster becomes a zombie until the STARTING process (this
        # watchdog's own sibling, never this watchdog itself) reaps it, and
        # a zombie still answers kill(pid, 0) -- the argv read for a
        # zombie no longer names the data directory, so the identity check
        # reports it gone immediately instead of burning the full timeout
        # on every single clean stop.
        if not _signal_and_wait(pid, signal.SIGTERM, TERM_TIMEOUT, alive=alive):
            if not _signal_and_wait(pid, signal.SIGQUIT, QUIT_TIMEOUT, alive=alive):
                _signal_and_wait(pid, signal.SIGKILL, QUIT_TIMEOUT, alive=alive)
    shutil.rmtree(run_dir, ignore_errors=True)
    return 0


# ---------------------------------------------------------------------------
# start(): initdb, postgres, wait-ready, pgpass, watchdog
# ---------------------------------------------------------------------------

def start() -> Cluster:
    """Start a brand-new throwaway cluster and return its handle. Sweeps
    dead run directories first (best-effort; a sweep failure never blocks
    starting a new cluster)."""
    try:
        sweep()
    except OSError:
        pass
    bindir = _bindir()
    _check_version(bindir)
    base = _base_dir()
    # Created under STAGING_PREFIX, not "run-": sweep()'s own "run-*" glob
    # (above) cannot see this directory yet, so a concurrent sweep() in
    # another process can never rmtree it before it holds its own lock
    # (review B-3 -- the previous code was visible to glob("run-*") from
    # `mkdtemp` alone, before `flock` ever ran).
    staging = Path(tempfile.mkdtemp(prefix=STAGING_PREFIX, dir=str(base)))
    return _start_in(staging, base, bindir)


def _socket_path(socket_dir: Path) -> Path:
    """`<socket_dir>/.s.PGSQL.<PORT>` -- the actual unix socket `postgres`
    creates. Raises if it would exceed `SOCKET_PATH_LIMIT` bytes (work
    order §2.1; measured 88 bytes under `$TMPDIR`, design §3.4)."""
    path = socket_dir / f".s.PGSQL.{PORT}"
    if len(str(path).encode("utf-8")) > SOCKET_PATH_LIMIT:
        raise TestPgError(f"socket path would exceed {SOCKET_PATH_LIMIT} bytes: {socket_dir}")
    return path


def _write_pgpass(pgpass_path: Path, socket_dir: Path, password: str) -> None:
    pgpass_path.write_text(f"{socket_dir}:{PORT}:*:{SUPERUSER}:{password}\n", encoding="utf-8")
    os.chmod(pgpass_path, 0o600)  # work order §2.1: pgpass is 0600


def _start_in(staging: Path, base: Path, bindir: Path) -> Cluster:
    """`staging` is the `STAGING_PREFIX`-named directory `start()` just
    `mkdtemp`ed. Takes the lock, publishes it as `run-*` (review B-3), then
    does the rest of startup. On ANY failure past that point -- including
    one raised while cleaning up an earlier failure -- stops a postmaster
    that was already spawned, closes the lock fd, and removes whatever
    directory currently exists, so a failed `start()` never leaves a
    running postmaster, a leaked fd, or a data directory with nothing left
    to own it (review M-5)."""
    current_dir = staging
    lock_fd = None
    postmaster: subprocess.Popen | None = None
    try:
        lock_fd = os.open(staging / "owner.lock", os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)  # held for this Cluster's whole life

        run_dir = base / ("run-" + staging.name[len(STAGING_PREFIX):])
        staging.rename(run_dir)  # atomic; the lock fd follows the inode (review B-3)
        current_dir = run_dir

        socket_dir = run_dir / "s"
        socket_dir.mkdir(mode=0o700)
        os.chmod(socket_dir, 0o700)
        _socket_path(socket_dir)  # raises before anything else starts if it would be too long

        data_dir = run_dir / "data"
        password = secrets.token_urlsafe(32)
        pwfile = run_dir / "initdb-pwfile"
        pwfile.write_text(password + "\n", encoding="utf-8")
        os.chmod(pwfile, 0o600)
        try:
            _run_initdb(bindir, data_dir, pwfile)
        finally:
            pwfile.unlink(missing_ok=True)  # work order §2.1: gone immediately after initdb

        log_path = run_dir / "postgres.log"
        postmaster = _spawn_postgres(bindir, data_dir, socket_dir, log_path)
        (run_dir / "meta.json").write_text(json.dumps({"pid": postmaster.pid}), encoding="utf-8")
        _wait_ready(bindir, socket_dir, postmaster, log_path)

        _write_pgpass(run_dir / "pgpass", socket_dir, password)

        read_end, write_end = os.pipe()
        try:
            watchdog = subprocess.Popen(
                [sys.executable, str(Path(__file__).resolve()), "--watchdog", str(run_dir)],
                stdin=read_end, start_new_session=True, close_fds=True,
            )
        finally:
            os.close(read_end)  # the watchdog holds its own duplicate

        return Cluster(
            run_dir=run_dir, socket_dir=socket_dir, password=password,
            postmaster_pid=postmaster.pid, _watchdog=watchdog, _pipe_w=write_end, _lock_fd=lock_fd,
        )
    except BaseException:
        if postmaster is not None and postmaster.poll() is None:
            _signal_and_wait(postmaster.pid, signal.SIGQUIT, QUIT_TIMEOUT)
            _signal_and_wait(postmaster.pid, signal.SIGKILL, QUIT_TIMEOUT)
            try:
                os.waitpid(postmaster.pid, 0)
            except ChildProcessError:
                pass
        if lock_fd is not None:
            try:
                os.close(lock_fd)
            except OSError:
                pass
        shutil.rmtree(current_dir, ignore_errors=True)
        raise


def _run_initdb(bindir: Path, data_dir: Path, pwfile: Path) -> None:
    exe = _binary(bindir, "initdb")
    cmd = [exe, "-D", str(data_dir), "-U", SUPERUSER, "--auth=scram-sha-256",
           f"--pwfile={pwfile}", "--locale=en_US.UTF-8", "--encoding=UTF8"]
    proc = subprocess.run(cmd, env=_clean_env(), capture_output=True, text=True)
    if proc.returncode != 0:
        raise TestPgError(f"initdb failed (exit {proc.returncode}): {proc.stderr.strip()[-2000:]}")


def _postgres_argv(bindir: Path, data_dir: Path, socket_dir: Path) -> list[str]:
    """The `postgres` command line, split out from `_spawn_postgres` so
    `tools/tests/test_testpg.py` can assert on the declared `-c` settings
    (review M-2/row 3) without spawning a real server."""
    exe = _binary(bindir, "postgres")
    return [
        exe, "-D", str(data_dir),
        "-c", "listen_addresses=",
        "-c", f"unix_socket_directories={socket_dir}",
        "-c", "unix_socket_permissions=0700",
        "-c", f"port={PORT}",
        "-c", "max_connections=300",
        "-c", "TimeZone=Asia/Tokyo",
    ]


def _spawn_postgres(bindir: Path, data_dir: Path, socket_dir: Path, log_path: Path) -> subprocess.Popen:
    cmd = _postgres_argv(bindir, data_dir, socket_dir)
    with open(log_path, "wb") as log:
        # postgres -- direct child of THIS process, never through pg_ctl
        # (design D-2: pg_ctl's own setsid detaches it further, so a SIGKILL
        # of the starting process would not reach it at all).
        return subprocess.Popen(cmd, env=_clean_env(), stdout=log, stderr=subprocess.STDOUT,
                                 start_new_session=True, close_fds=True)


def _wait_ready(bindir: Path, socket_dir: Path, postmaster: subprocess.Popen, log_path: Path) -> None:
    exe = _binary(bindir, "pg_isready")
    deadline = time.monotonic() + READY_TIMEOUT
    while time.monotonic() < deadline:
        if postmaster.poll() is not None:
            raise TestPgError(
                f"postgres exited during startup (code {postmaster.returncode}); "
                f"log tail:\n{_log_tail(log_path)}"
            )
        proc = subprocess.run([exe, "-h", str(socket_dir), "-p", str(PORT), "-d", "postgres"],
                              capture_output=True)
        if proc.returncode == 0:
            return
        time.sleep(0.1)
    raise TestPgError(f"postgres not ready within {READY_TIMEOUT}s; log tail:\n{_log_tail(log_path)}")


# ---------------------------------------------------------------------------
# ensure_for_pytest(): the conftest.py entry point
# ---------------------------------------------------------------------------

_MODE_DOC = """Decision table for DSA_TEST_PG (work order §2.1):

  DSA_TEST_PG=external          -> both DSNs + PGHOST + PGPORT must already be set, or fail;
                                   each DSN's host= must be present and equal PGHOST, its port=
                                   (when written) equal PGPORT, else fail (names, never values)
  DSA_TEST_PG=owned:...         -> both DSNs + PGPASSFILE must be set; do not start
  this process is really an
    xdist worker, DSA_TEST_PG
    neither above               -> fail (a worker must inherit its controller's mode)
  DSA_TEST_PG unset, a DSN set  -> fail (ambiguous: which one wins?)
  DSA_TEST_PG unset, no DSN set -> start a cluster; export its env; DSA_TEST_PG=owned:<run dir>
  DSA_TEST_PG = anything else   -> fail
"""

_owned_cluster: Cluster | None = None  # non-None only in the process that itself started one
_owned_lock: "_SuiteLockHandle | None" = None  # the shared suite lock that process holds for the run's whole life


def _is_xdist_worker() -> bool:
    """True only when THIS process actually IS a pytest-xdist worker --
    not merely when `PYTEST_XDIST_WORKER` happens to be present in
    `os.environ`, which is also true of a plain, standalone `python -m
    pytest` a test running INSIDE a worker spawns as a subprocess with
    `env=os.environ` (or a filtered copy that forgot to drop it): that
    child inherits the variable but is not itself a worker, and must not
    be refused for merely looking like a stale one (follow-up finding,
    gate run 2026-09-16: `conformance-tests/test_testpg_cluster.py`'s own
    nested-pytest tests failed exactly this way under `-n 5 --dist
    loadgroup`). `xdist.remote` is the module pytest-xdist's own worker
    bootstrap imports into a REAL worker's interpreter (execnet's remote
    side); a process that was never launched as a worker never imports
    it."""
    return "xdist.remote" in sys.modules


def ensure_for_pytest() -> None:
    """Idempotent. Called at import time by each of the three `conftest.py`
    files (design D-1). See `_MODE_DOC` for the full decision table."""
    global _owned_cluster, _owned_lock
    if _owned_cluster is not None:
        return  # this process already started one; the root+peer conftest both import this module

    mode = os.environ.get(ENV_MODE)

    if mode == "external":
        # R-44 WP-4 (work order §5.1 (b) 5, §4.1 R-10): PGHOST and PGPORT too.
        # A connection that writes no host of its own falls through to PGHOST;
        # without it that connection would reach libpq's default socket, i.e.
        # whatever cluster the machine happens to serve there. gate.py,
        # perf_baseline.py and `_cli_run` already pass both via `Cluster.env()`.
        _require_env((*_DSN_NAMES, "PGHOST", "PGPORT"), "DSA_TEST_PG=external")
        # Code review 1: being SET is not enough -- a shell that still exports
        # PGHOST / PGPORT of the shared cluster while the DSNs name another
        # one would pass, and a connection that writes no host reaches the
        # shared cluster. So each DSN's own host= / port= must agree with them.
        _check_external_dsns_agree_with_pghost()
        # Work order §3.1 (a): never take the shared lock here. This is the
        # mode gate.py itself launches its own child pytest with, WHILE
        # already holding the exclusive lock -- flock(2)'s per-open-file-
        # description semantics mean a second, same-process acquisition
        # attempt on the same lock file (even just LOCK_SH) would block
        # forever, deadlocking gate against itself.
        return

    if mode is not None and mode.startswith("owned:"):
        _require_env((*_DSN_NAMES, "PGPASSFILE"), f"DSA_TEST_PG={mode}")
        return

    if os.environ.get("PYTEST_XDIST_WORKER") and _is_xdist_worker():
        raise TestPgError(
            "an xdist worker must inherit DSA_TEST_PG=external or owned:... from its "
            f"controller (pytest-xdist/execnet pass the controller's own os.environ down), "
            f"not decide on its own -- got DSA_TEST_PG={mode!r}"
        )

    if mode is None:
        if os.environ.get(R2DB_DSN) or os.environ.get(MITATEDB_DSN):
            raise TestPgError(
                f"{R2DB_DSN} or {MITATEDB_DSN} is set but DSA_TEST_PG is not -- ambiguous "
                "whether to use that DSN or start a throwaway cluster; set DSA_TEST_PG=external "
                "to use it, or unset it to start a throwaway cluster"
            )
        # Work order §3.1 (a): owned mode is the ONLY branch that takes the
        # shared suite lock -- held for the run's whole life, released by
        # stop_owned() below. Acquired BEFORE start() so a process that
        # would have to wait for a running gate never spins up (and then
        # tears down) a cluster it could not actually use meanwhile.
        #
        # review B-1: unless an ANCESTOR process already holds the suite
        # lock for this whole process tree (DSA_TEST_PG_LOCK_HELD -- set by
        # gate.py on the env of the pytest child it launches with
        # DSA_TEST_PG=external, and inherited from there by any owned-mode
        # pytest THAT process spawns in turn, e.g. conformance-tests/
        # test_testpg_cluster.py's own nested-controller tests). Acquiring
        # again here would not merely double-lock: the ancestor is itself
        # blocked inside the very suite run this process is part of, so it
        # can never release the lock for this wait to succeed -- a genuine
        # deadlock, not a slow path.
        lock = None
        if not os.environ.get(ENV_LOCK_HELD):
            try:
                wait = float(os.environ.get(ENV_LOCK_WAIT, DEFAULT_LOCK_WAIT))
            except ValueError as exc:
                raise TestPgError(f"{ENV_LOCK_WAIT}={os.environ[ENV_LOCK_WAIT]!r} is not a number") from exc
            lock = _acquire_suite_lock(exclusive=False, wait=wait)
        try:
            c = start()
        except BaseException:
            if lock is not None:
                lock.release()
            raise
        _owned_cluster = c
        _owned_lock = lock
        os.environ.update(c.env())
        os.environ.pop("PGPASSWORD", None)  # never let a stray password override PGPASSFILE
        os.environ[ENV_MODE] = f"owned:{c.run_dir.name}"
        atexit.register(stop_owned)  # safety net; pytest_unconfigure calls stop_owned() too
        report = os.environ.get(ENV_REPORT)
        if report:
            Path(report).write_text(str(c.run_dir), encoding="utf-8")
        return

    raise TestPgError(f"unrecognized {ENV_MODE}={mode!r}")


_CONNINFO_PAIR = re.compile(r"(\w+)\s*=\s*('(?:[^'\\]|\\.)*'|\S*)")


def _conninfo_values(dsn: str) -> dict[str, str] | None:
    """The `key=value` pairs of a libpq key/value conninfo string (a
    single-quoted value loses its quotes and backslash escapes); None for a
    URI-form DSN, which this repository never uses and `external` refuses."""
    if dsn.lstrip().lower().startswith(("postgres://", "postgresql://")):
        return None
    out: dict[str, str] = {}
    for key, raw in _CONNINFO_PAIR.findall(dsn):
        if len(raw) >= 2 and raw[0] == raw[-1] == "'":
            raw = re.sub(r"\\(.)", r"\1", raw[1:-1])
        out[key] = raw
    return out


def _check_external_dsns_agree_with_pghost() -> None:
    """R-44 WP-4 code review 1 (work order §5.1 (b) 5): in `external` mode
    each DSN's `host=` must be present and equal `PGHOST`, and its `port=`,
    when written, must equal `PGPORT`. A mismatch fails naming the two
    variables only -- never a value (a DSN can carry a password). A DSN
    with no `host=` is refused (a host-less connection in `external` falls
    through to PGHOST/libpq's default socket); a URI-form DSN is refused."""
    for name in _DSN_NAMES:
        pairs = _conninfo_values(os.environ[name])
        if pairs is None:
            raise TestPgError(f"DSA_TEST_PG=external: {name} is not in key=value form (URI-form DSNs are refused)")
        if "host" not in pairs:
            raise TestPgError(f"DSA_TEST_PG=external: {name} writes no host= (a host-less DSN would fall through to PGHOST)")
        if pairs["host"] != os.environ["PGHOST"]:
            raise TestPgError(f"DSA_TEST_PG=external: the host= of {name} does not match PGHOST")
        if "port" in pairs and pairs["port"] != os.environ["PGPORT"]:
            raise TestPgError(f"DSA_TEST_PG=external: the port= of {name} does not match PGPORT")


def _require_env(names, context: str) -> None:
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        raise TestPgError(f"{context} requires {', '.join(missing)} to be set")


def stop_owned() -> None:
    """Stop the cluster THIS process started via `ensure_for_pytest()`, if
    any (idempotent -- safe to call from both `pytest_unconfigure` and the
    `atexit` safety net), and release the shared suite lock that same call
    took (work order §3.1 (a))."""
    global _owned_cluster, _owned_lock
    if _owned_cluster is None:
        return
    c, _owned_cluster = _owned_cluster, None
    lock, _owned_lock = _owned_lock, None
    try:
        c.stop()
    finally:
        if lock is not None:
            lock.release()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli_run(command: list[str]) -> int:
    with cluster() as c:
        env = {**os.environ, **c.env(), ENV_MODE: "external"}
        env.pop("PGPASSWORD", None)
        proc = subprocess.run(command, env=env)
    return proc.returncode


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["--watchdog"]:
        if len(argv) != 2:
            print("usage: dsa_testpg.py --watchdog RUN_DIR", file=sys.stderr)
            return 2
        return _watchdog_main(Path(argv[1]))
    if argv[:1] == ["sweep"]:
        sweep()
        return 0
    if argv[:1] == ["run"]:
        rest = argv[1:]
        if rest[:1] == ["--"]:
            rest = rest[1:]
        if not rest:
            print("usage: dsa_testpg.py run -- <command...>", file=sys.stderr)
            return 2
        try:
            return _cli_run(rest)
        except TestPgError as exc:
            print(f"dsa_testpg: {exc}", file=sys.stderr)
            return 1
    print("usage: dsa_testpg.py run -- <command...> | sweep", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
