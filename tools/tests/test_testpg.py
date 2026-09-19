"""tools/tests/test_testpg.py -- unit coverage for tools/testpg/dsa_testpg.py
that never touches a real PostgreSQL server (work order docs/work-orders/
WORK_ORDER_R44_TEST_PG_ISOLATION_V1.md §2.4, design docs/design/
TEST_POSTGRES_ISOLATION_V0_1.md v0.2). The real-cluster behavior (a
connection actually reaching the started cluster, teardown on context-exit
and on SIGKILL, the two nested-pytest scenarios) is
conformance-tests/test_testpg_cluster.py instead.

Covers: the full `ensure_for_pytest()` decision table, `Cluster.env()`'s
shape (no password in either DSN, not even in `repr()`), `pgpass` content
and 0600 permission, the declared `postgres -c` settings (review M-2/row
3), the socket-path length ceiling, the base directory's owner/symlink
checks, `sweep()` (a live lock is left alone; a dead owner's directory is
removed; a pid that does not look like ours is never signalled), and
postgres major-version parsing/gating (16.14 accepted, 15.x rejected).

Not under `conformance-tests/` and not in the root suite's `testpaths`
(same convention as tools/tests/test_dev_tools.py); `tools/tests/pytest.ini`
is what keeps a run of this directory from starting a cluster of its own
(work order §2.3).

Run directly:
    ./.venv/bin/python -m pytest tools/tests/test_testpg.py -q
"""
from __future__ import annotations

import fcntl
import importlib.util
import json
import os
import stat
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import pytest

_MOD_PATH = Path(__file__).resolve().parents[1] / "testpg" / "dsa_testpg.py"


def _load():
    spec = importlib.util.spec_from_file_location("dsa_testpg_under_test", _MOD_PATH)
    mod = importlib.util.module_from_spec(spec)
    # Registered in sys.modules BEFORE exec (not just as this function's own
    # local `mod`): dsa_testpg.py's `@dataclasses.dataclass` combined with
    # `from __future__ import annotations` makes `dataclasses` resolve each
    # field's string annotation via `sys.modules[cls.__module__]` while the
    # class body executes, so the module must already be findable there.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


dsa = _load()

# WP-2 (docs/work-orders/WORK_ORDER_R44_TEST_PG_ISOLATION_V1.md §3.1 (a)):
# captured BEFORE the autouse fixture below patches `dsa._acquire_suite_lock`
# to a no-op -- the handful of tests that actually exercise real locking call
# this directly (always with an explicit tmp_path `base`), bypassing the
# patched module attribute entirely.
_real_acquire_suite_lock = dsa._acquire_suite_lock


class _FakeLockHandle:
    """What the autouse fixture's own `_acquire_suite_lock` stub hands back:
    a harmless no-op `release()`, so `ensure_for_pytest()`'s owned-mode path
    (and `stop_owned()`) work without ever touching a real lock file."""

    def release(self) -> None:
        pass


_ENV_NAMES = (dsa.ENV_MODE, dsa.R2DB_DSN, dsa.MITATEDB_DSN, dsa.ENV_BINDIR, dsa.ENV_REPORT, dsa.ENV_LOCK_WAIT,
              dsa.ENV_LOCK_HELD, "PYTEST_XDIST_WORKER", "PGHOST", "PGPORT", "PGUSER", "PGPASSFILE", "PGPASSWORD")


def _isolated_state_setup(monkeypatch) -> dict[str, str | None]:
    """The `_isolated_state` fixture's own setup half, factored out so a
    test can drive it directly with its own `MonkeyPatch` instance (see
    `test_isolated_state_teardown_restores_the_pre_fixture_environment_
    after_an_owned_mode_run` below) instead of only through the autouse
    fixture. Returns each of `_ENV_NAMES`' pre-call state (`None` if the
    name was absent), for `_isolated_state_teardown` to put back."""
    pre_state = {name: os.environ.get(name) for name in _ENV_NAMES}
    for name in _ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(dsa, "_acquire_suite_lock", lambda *a, **k: _FakeLockHandle())
    dsa._owned_cluster = None
    dsa._owned_lock = None
    return pre_state


def _isolated_state_teardown(pre_state: dict[str, str | None]) -> None:
    """The `_isolated_state` fixture's own teardown half. Stops a REAL
    cluster if one is somehow left behind in `dsa._owned_cluster` --
    normally impossible (every test that reaches the "start a cluster"
    branch replaces `dsa.start` with a fake first), but a future change to
    `ensure_for_pytest()`'s own ordering could let a real `start()` run
    before a test gets the chance to install its fake; this keeps such a
    bug from leaking a real postgres process.

    The final restore loop is independent of `monkeypatch`: a test that
    drives `ensure_for_pytest()` into its owned-mode branch (with a faked
    `start()`) exercises `dsa_testpg.py`'s own direct
    `os.environ.update(...)`/`os.environ[...] = ...` writes, which
    `monkeypatch.delenv`/`setenv` never records an undo for when the name
    was already absent going in -- so this puts each name's own captured
    pre-fixture state back explicitly, rather than relying on
    `monkeypatch`'s own bookkeeping to have seen every write."""
    if dsa._owned_cluster is not None:
        try:
            dsa._owned_cluster.stop()
        except Exception:
            pass
    if dsa._owned_lock is not None:
        try:
            dsa._owned_lock.release()
        except Exception:
            pass
    dsa._owned_cluster = None
    dsa._owned_lock = None
    for name, value in pre_state.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


@pytest.fixture(autouse=True)
def _isolated_state(monkeypatch):
    """Every decision-table test starts from a clean slate: none of the
    module's own env vars set, and no `_owned_cluster` / `_owned_lock` left
    over from a previous test (the real module keeps that as global state,
    exactly as a single pytest process would across its three conftest.py
    imports).

    `_acquire_suite_lock` is stubbed to a harmless no-op EVERY test (never
    the machine's real, per-uid base dir -- shared with any concurrently
    running gate.py / pytest on this machine): the lock-specific tests below
    call `_real_acquire_suite_lock` directly instead, always against an
    explicit tmp_path `base`. See `_isolated_state_setup`/
    `_isolated_state_teardown` for what each half actually does."""
    pre_state = _isolated_state_setup(monkeypatch)
    yield
    _isolated_state_teardown(pre_state)


# ---------------------------------------------------------------------------
# ensure_for_pytest() decision table
# ---------------------------------------------------------------------------

def test_external_with_both_dsns_is_accepted_and_does_not_start(monkeypatch):
    monkeypatch.setenv(dsa.ENV_MODE, "external")
    monkeypatch.setenv(dsa.R2DB_DSN, "host=/x port=5432 dbname=postgres user=postgres")
    monkeypatch.setenv(dsa.MITATEDB_DSN, "host=/x port=5432 dbname=postgres user=postgres")
    monkeypatch.setattr(dsa, "start", lambda: pytest.fail("must not start a cluster"))
    dsa.ensure_for_pytest()  # does not raise
    assert dsa._owned_cluster is None


def test_external_mode_takes_no_lock(monkeypatch):
    """work order §3.1 (a): `ensure_for_pytest()` in `external` mode must
    never call `_acquire_suite_lock` at all -- gate.py already holds the
    exclusive lock for the pytest run it is about to launch with
    DSA_TEST_PG=external, and flock's own per-open-file-description
    semantics mean a second, same-process acquisition attempt on the same
    lock file (even just LOCK_SH) would block forever, deadlocking gate
    against itself.

    mutation (`dsa_testpg.py`): make external ALSO take the lock -- this
    test goes red because `_acquire_suite_lock` would then be called at all.
    """
    monkeypatch.setenv(dsa.ENV_MODE, "external")
    monkeypatch.setenv(dsa.R2DB_DSN, "host=/x port=5432 dbname=postgres user=postgres")
    monkeypatch.setenv(dsa.MITATEDB_DSN, "host=/x port=5432 dbname=postgres user=postgres")
    monkeypatch.setattr(dsa, "_acquire_suite_lock", lambda *a, **k: pytest.fail("must not take any lock in external mode"))
    dsa.ensure_for_pytest()  # does not raise


def test_external_missing_a_dsn_fails(monkeypatch):
    monkeypatch.setenv(dsa.ENV_MODE, "external")
    monkeypatch.setenv(dsa.R2DB_DSN, "host=/x port=5432 dbname=postgres user=postgres")
    with pytest.raises(dsa.TestPgError, match=dsa.MITATEDB_DSN):
        dsa.ensure_for_pytest()


def test_owned_with_both_dsns_and_pgpassfile_is_accepted_and_does_not_start(monkeypatch):
    monkeypatch.setenv(dsa.ENV_MODE, "owned:run-abc123")
    monkeypatch.setenv(dsa.R2DB_DSN, "host=/x port=5432 dbname=postgres user=postgres")
    monkeypatch.setenv(dsa.MITATEDB_DSN, "host=/x port=5432 dbname=postgres user=postgres")
    monkeypatch.setenv("PGPASSFILE", "/x/pgpass")
    monkeypatch.setattr(dsa, "start", lambda: pytest.fail("must not start a cluster"))
    dsa.ensure_for_pytest()
    assert dsa._owned_cluster is None


def test_owned_missing_pgpassfile_fails(monkeypatch):
    monkeypatch.setenv(dsa.ENV_MODE, "owned:run-abc123")
    monkeypatch.setenv(dsa.R2DB_DSN, "host=/x port=5432 dbname=postgres user=postgres")
    monkeypatch.setenv(dsa.MITATEDB_DSN, "host=/x port=5432 dbname=postgres user=postgres")
    with pytest.raises(dsa.TestPgError, match="PGPASSFILE"):
        dsa.ensure_for_pytest()


def test_xdist_worker_without_external_or_owned_fails(monkeypatch):
    # A GENUINE worker: both the env var xdist sets AND the module only a
    # real worker's own bootstrap imports (`_is_xdist_worker()`).
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw0")
    monkeypatch.setitem(sys.modules, "xdist.remote", object())
    with pytest.raises(dsa.TestPgError, match="xdist worker"):
        dsa.ensure_for_pytest()


def test_xdist_worker_with_external_is_fine(monkeypatch):
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw0")
    monkeypatch.setenv(dsa.ENV_MODE, "external")
    monkeypatch.setenv(dsa.R2DB_DSN, "host=/x port=5432 dbname=postgres user=postgres")
    monkeypatch.setenv(dsa.MITATEDB_DSN, "host=/x port=5432 dbname=postgres user=postgres")
    dsa.ensure_for_pytest()  # does not raise


def test_unset_mode_with_a_dsn_set_is_ambiguous_and_fails(monkeypatch):
    monkeypatch.setenv(dsa.R2DB_DSN, "host=/x port=5432 dbname=postgres user=postgres")
    with pytest.raises(dsa.TestPgError, match="ambiguous"):
        dsa.ensure_for_pytest()


def test_unset_mode_with_only_the_other_dsn_set_is_also_ambiguous_and_fails(monkeypatch):
    monkeypatch.setenv(dsa.MITATEDB_DSN, "host=/x port=5432 dbname=postgres user=postgres")
    with pytest.raises(dsa.TestPgError, match="ambiguous"):
        dsa.ensure_for_pytest()


def test_unrecognized_mode_fails(monkeypatch):
    monkeypatch.setenv(dsa.ENV_MODE, "bogus-value")
    with pytest.raises(dsa.TestPgError, match="unrecognized"):
        dsa.ensure_for_pytest()


class _FakeCluster:
    def __init__(self, run_dir):
        self.run_dir = run_dir
        self.stopped = False

    def env(self):
        return {
            dsa.R2DB_DSN: "host=/fake/s port=5432 dbname=postgres user=postgres",
            dsa.MITATEDB_DSN: "host=/fake/s port=5432 dbname=postgres user=postgres",
            "PGHOST": "/fake/s", "PGPORT": "5432", "PGUSER": "postgres",
            "PGPASSFILE": str(self.run_dir / "pgpass"),
        }

    def stop(self):
        self.stopped = True


def test_unset_mode_with_no_dsn_starts_a_cluster_and_exports_its_env(monkeypatch, tmp_path):
    fake = _FakeCluster(tmp_path / "run-fakeid")
    monkeypatch.setattr(dsa, "start", lambda: fake)
    registered = []
    monkeypatch.setattr(dsa.atexit, "register", lambda fn: registered.append(fn))
    monkeypatch.setenv("PGPASSWORD", "must-be-removed")

    # work order §3.1 (a): owned mode takes the shared suite lock for the
    # run's whole life -- a distinguishable fake (not the autouse default)
    # so this test can see it was actually acquired and later released.
    lock_calls = []

    class _TrackedLock:
        def __init__(self):
            self.released = False

        def release(self):
            self.released = True

    tracked = _TrackedLock()

    def fake_acquire(exclusive, wait, base=None):
        lock_calls.append((exclusive, wait))
        return tracked

    monkeypatch.setattr(dsa, "_acquire_suite_lock", fake_acquire)

    dsa.ensure_for_pytest()

    assert dsa._owned_cluster is fake
    assert dsa._owned_lock is tracked
    assert lock_calls == [(False, dsa.DEFAULT_LOCK_WAIT)]
    assert os.environ[dsa.ENV_MODE] == "owned:run-fakeid"
    assert os.environ["PGHOST"] == "/fake/s"
    assert os.environ[dsa.R2DB_DSN] == fake.env()[dsa.R2DB_DSN]
    assert "PGPASSWORD" not in os.environ
    assert registered == [dsa.stop_owned]

    # A second call in the same process is a no-op (idempotent): the
    # module already owns a cluster, so `start` must not run again.
    monkeypatch.setattr(dsa, "start", lambda: pytest.fail("must not start twice"))
    dsa.ensure_for_pytest()
    assert dsa._owned_cluster is fake
    assert len(lock_calls) == 1  # no second acquisition either

    dsa.stop_owned()
    assert fake.stopped
    assert tracked.released
    assert dsa._owned_cluster is None
    assert dsa._owned_lock is None
    dsa.stop_owned()  # idempotent


def test_isolated_state_teardown_restores_the_pre_fixture_environment_after_an_owned_mode_run(tmp_path):
    """R-58 WP-1b completion condition 7 (docs/work-orders/
    WORK_ORDER_R58_PERF_BASELINE_ENV_RESTORE_V1.md, coordinator ruling
    (d)): starting from none of `_ENV_NAMES` set (the outer autouse
    `_isolated_state` fixture already guarantees this for every test),
    running `ensure_for_pytest()`'s owned-mode branch through a fake
    `start()` and then this fixture's own teardown must leave none of
    `_ENV_NAMES` in `os.environ` -- not merely "no worse than before",
    since before was already clean.

    Drives `_isolated_state_setup`/`_isolated_state_teardown` directly
    with an own `MonkeyPatch` instance (rather than a second nested pytest
    run) so this one test can observe `os.environ` on both sides of the
    teardown call.

    mutation M4 (`tools/tests/test_testpg.py`): drop the final restore
    loop from `_isolated_state_teardown` -- red because `PGHOST` (etc.)
    stays set in `os.environ` after teardown returns.
    """
    for name in _ENV_NAMES:
        assert name not in os.environ, f"{name} was already set before this test started"

    inner_monkeypatch = pytest.MonkeyPatch()
    try:
        pre_state = _isolated_state_setup(inner_monkeypatch)
        assert all(value is None for value in pre_state.values())

        fake = _FakeCluster(tmp_path / "run-fakeid-cc7")
        inner_monkeypatch.setattr(dsa, "start", lambda: fake)
        inner_monkeypatch.setattr(dsa.atexit, "register", lambda fn: None)

        dsa.ensure_for_pytest()
        # Not vacuous: confirms the owned-mode branch actually wrote to
        # os.environ before checking that teardown undoes it.
        assert os.environ.get("PGHOST") == "/fake/s"

        _isolated_state_teardown(pre_state)

        for name in _ENV_NAMES:
            assert name not in os.environ, f"{name} leaked into os.environ after teardown"
    finally:
        inner_monkeypatch.undo()


def test_unset_mode_honors_the_lock_wait_env_var(monkeypatch, tmp_path):
    fake = _FakeCluster(tmp_path / "run-fakeid-waitenv")
    monkeypatch.setattr(dsa, "start", lambda: fake)
    monkeypatch.setattr(dsa.atexit, "register", lambda fn: None)
    monkeypatch.setenv(dsa.ENV_LOCK_WAIT, "42.5")
    seen = {}

    def fake_acquire(exclusive, wait, base=None):
        seen["wait"] = wait
        return _FakeLockHandle()

    monkeypatch.setattr(dsa, "_acquire_suite_lock", fake_acquire)

    dsa.ensure_for_pytest()

    assert seen["wait"] == 42.5
    dsa.stop_owned()


def test_unset_mode_skips_the_lock_when_an_ancestor_already_holds_it(monkeypatch, tmp_path):
    """review B-1: gate.py (or any owned-mode pytest THIS process's own
    suite spawns as a genuine nested subprocess, e.g. conformance-tests/
    test_testpg_cluster.py's nested-controller tests) sets DSA_TEST_PG_
    LOCK_HELD on the child's env -- an ancestor already holds the suite
    lock for this whole process tree, so acquiring it again here would
    deadlock (the ancestor cannot release it until this very process tree,
    including this child, finishes). The owned branch must still start a
    cluster and export its env; it just must not touch the lock.

    mutation (`dsa_testpg.py`): remove the `if not os.environ.get(ENV_LOCK_
    HELD):` guard (always acquire) -- this test goes red because
    `_acquire_suite_lock` would then be called despite the env var."""
    fake = _FakeCluster(tmp_path / "run-fakeid-lockheld")
    monkeypatch.setattr(dsa, "start", lambda: fake)
    monkeypatch.setattr(dsa.atexit, "register", lambda fn: None)
    monkeypatch.setenv(dsa.ENV_LOCK_HELD, "1")
    monkeypatch.setattr(dsa, "_acquire_suite_lock", lambda *a, **k: pytest.fail("must not take the lock when an ancestor already holds it"))

    dsa.ensure_for_pytest()

    assert dsa._owned_cluster is fake
    assert dsa._owned_lock is None
    assert os.environ[dsa.ENV_MODE] == "owned:run-fakeid-lockheld"
    dsa.stop_owned()  # idempotent even with no lock to release
    assert dsa._owned_cluster is None


def test_unset_mode_with_no_dsn_writes_the_report_file_when_requested(monkeypatch, tmp_path):
    fake = _FakeCluster(tmp_path / "run-fakeid2")
    monkeypatch.setattr(dsa, "start", lambda: fake)
    monkeypatch.setattr(dsa.atexit, "register", lambda fn: None)
    report = tmp_path / "report.txt"
    monkeypatch.setenv(dsa.ENV_REPORT, str(report))

    dsa.ensure_for_pytest()

    assert report.read_text(encoding="utf-8") == str(fake.run_dir)
    dsa.stop_owned()


def test_owned_and_external_do_not_write_the_report_file(monkeypatch, tmp_path):
    report = tmp_path / "report.txt"
    monkeypatch.setenv(dsa.ENV_REPORT, str(report))
    monkeypatch.setenv(dsa.ENV_MODE, "external")
    monkeypatch.setenv(dsa.R2DB_DSN, "host=/x port=5432 dbname=postgres user=postgres")
    monkeypatch.setenv(dsa.MITATEDB_DSN, "host=/x port=5432 dbname=postgres user=postgres")
    dsa.ensure_for_pytest()
    assert not report.exists()


def test_stale_xdist_worker_env_without_real_worker_module_starts(monkeypatch, tmp_path):
    """Review follow-up (gate run 2026-09-16, `-n 5 --dist loadgroup`):
    `PYTEST_XDIST_WORKER` can be present in `os.environ` merely because a
    CHILD process inherited it from a parent that was itself a real
    worker -- a plain `python -m pytest` subprocess a test running inside
    a worker spawns (`conformance-tests/test_testpg_cluster.py`'s own
    nested-pytest tests) is not itself a worker just because it sees that
    variable, and must still reach the ambiguous-DSN / start-a-cluster
    branches below, not the worker-only fail. `_is_xdist_worker()` must
    say False here even with the env var present, since `xdist.remote`
    (forced absent below, regardless of whatever this actual test run's
    own ambient state happens to be) was never imported."""
    monkeypatch.delitem(sys.modules, "xdist.remote", raising=False)
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw0")
    fake = _FakeCluster(tmp_path / "run-stalemarker")
    monkeypatch.setattr(dsa, "start", lambda: fake)
    monkeypatch.setattr(dsa.atexit, "register", lambda fn: None)

    dsa.ensure_for_pytest()  # does not raise; starts (via the fake) instead

    assert dsa._owned_cluster is fake
    dsa.stop_owned()


# ---------------------------------------------------------------------------
# Cluster.env() shape
# ---------------------------------------------------------------------------

def test_cluster_env_dsn_carries_no_password(tmp_path):
    c = dsa.Cluster(
        run_dir=tmp_path, socket_dir=tmp_path / "s", password="s3cr3t-would-be-bad-to-leak",
        postmaster_pid=1, _watchdog=None, _pipe_w=-1, _lock_fd=-1,
    )
    env = c.env()
    assert set(env) == {dsa.R2DB_DSN, dsa.MITATEDB_DSN, "PGHOST", "PGPORT", "PGUSER", "PGPASSFILE"}
    assert "s3cr3t-would-be-bad-to-leak" not in " ".join(env.values())
    assert "password" not in env[dsa.R2DB_DSN]
    assert env[dsa.R2DB_DSN] == env[dsa.MITATEDB_DSN] == f"host={tmp_path / 's'} port=5432 dbname=postgres user=postgres"
    assert env["PGHOST"] == str(tmp_path / "s")
    assert env["PGPORT"] == "5432"
    assert env["PGUSER"] == "postgres"
    assert env["PGPASSFILE"] == str(tmp_path / "pgpass")
    # review M-6: the password must never reach a dataclass repr either --
    # pytest prints reprs of local variables in assertion failures/tracebacks.
    assert "s3cr3t-would-be-bad-to-leak" not in repr(c)


# ---------------------------------------------------------------------------
# pgpass content and permissions
# ---------------------------------------------------------------------------

def test_write_pgpass_content_and_mode(tmp_path):
    socket_dir = tmp_path / "s"
    pgpass = tmp_path / "pgpass"
    dsa._write_pgpass(pgpass, socket_dir, "the-password")
    assert pgpass.read_text(encoding="utf-8") == f"{socket_dir}:5432:*:postgres:the-password\n"
    assert stat.S_IMODE(pgpass.stat().st_mode) == 0o600


# ---------------------------------------------------------------------------
# postgres argv (review M-2/row 3): pins the declared `-c` settings without
# spawning a real server -- the integration-level proof that they actually
# take effect (via `pg_settings.source = 'command line'`) is
# conformance-tests/test_testpg_cluster.py's own
# test_no_host_connection_reaches_the_run_cluster_with_declared_settings.
# ---------------------------------------------------------------------------

def test_postgres_argv_carries_the_declared_c_settings(tmp_path):
    data_dir = tmp_path / "data"
    socket_dir = tmp_path / "s"
    argv = dsa._postgres_argv(Path(""), data_dir, socket_dir)
    assert "listen_addresses=" in argv
    assert f"unix_socket_directories={socket_dir}" in argv
    assert "unix_socket_permissions=0700" in argv
    assert "port=5432" in argv
    assert "max_connections=300" in argv
    assert "TimeZone=Asia/Tokyo" in argv


# ---------------------------------------------------------------------------
# Socket path length ceiling
# ---------------------------------------------------------------------------

def test_socket_path_within_limit_is_accepted():
    # A short, fixed path -- not pytest's own `tmp_path` fixture, whose own
    # generated directory (`pytest-of-<user>/pytest-<N>/<test id>/`) is
    # itself long enough to exceed SOCKET_PATH_LIMIT on some machines/CI
    # runners, which would make this "accepted" case flaky for a reason
    # that has nothing to do with `_socket_path` itself. `_socket_path`
    # does no filesystem I/O, so a real directory is not needed.
    short_dir = Path("/tmp/dsa-testpg-unit/s")
    path = dsa._socket_path(short_dir)
    assert path == short_dir / ".s.PGSQL.5432"


def test_socket_path_beyond_limit_is_rejected(tmp_path):
    long_dir = tmp_path / ("x" * 200)
    with pytest.raises(dsa.TestPgError, match="socket path"):
        dsa._socket_path(long_dir)


# ---------------------------------------------------------------------------
# Base directory: owner and symlink checks
# ---------------------------------------------------------------------------

def test_base_dir_creates_0700_and_is_idempotent(tmp_path):
    uid = os.getuid()
    first = dsa._base_dir(uid=uid, tmp_root=tmp_path)
    second = dsa._base_dir(uid=uid, tmp_root=tmp_path)
    assert first == second == tmp_path / f"dsa-testpg-{uid}"
    assert stat.S_IMODE(first.stat().st_mode) == 0o700


def test_base_dir_rejects_a_symlink(tmp_path):
    real_uid = os.getuid()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    link = tmp_path / f"dsa-testpg-{real_uid}"
    link.symlink_to(elsewhere)
    with pytest.raises(dsa.TestPgError, match="symlink"):
        dsa._base_dir(uid=real_uid, tmp_root=tmp_path)


def test_base_dir_rejects_a_directory_owned_by_another_user(tmp_path):
    other_uid = os.getuid() + 1  # this test process is guaranteed not to own a dir "as" this uid
    (tmp_path / f"dsa-testpg-{other_uid}").mkdir(mode=0o700)
    with pytest.raises(dsa.TestPgError, match="another user"):
        dsa._base_dir(uid=other_uid, tmp_root=tmp_path)


# ---------------------------------------------------------------------------
# postgres major-version parsing and gating
# ---------------------------------------------------------------------------

def test_parse_major_version():
    assert dsa.parse_major_version("postgres (PostgreSQL) 16.14") == 16
    assert dsa.parse_major_version("postgres (PostgreSQL) 15.7") == 15
    assert dsa.parse_major_version("postgres (PostgreSQL) 16.14 (Homebrew)") == 16
    assert dsa.parse_major_version("not a version string") is None


def _fake_binary(tmp_path: Path, name: str, version_line: str) -> Path:
    script = tmp_path / name
    script.write_text(f"#!/bin/sh\necho '{version_line}'\n", encoding="utf-8")
    script.chmod(0o755)
    return tmp_path


def test_check_version_accepts_16(tmp_path):
    bindir = _fake_binary(tmp_path, "postgres", "postgres (PostgreSQL) 16.14")
    dsa._check_version(bindir)  # does not raise


def test_check_version_rejects_15(tmp_path):
    bindir = _fake_binary(tmp_path, "postgres", "postgres (PostgreSQL) 15.7")
    with pytest.raises(dsa.TestPgError, match="16"):
        dsa._check_version(bindir)


# ---------------------------------------------------------------------------
# sweep()
# ---------------------------------------------------------------------------

def _fake_run_dir(base: Path) -> Path:
    run_dir = base / f"run-{uuid.uuid4().hex[:8]}"
    (run_dir / "data").mkdir(parents=True)
    return run_dir


def test_sweep_leaves_a_live_locked_run_alone(tmp_path):
    run_dir = _fake_run_dir(tmp_path)
    lock_fd = os.open(run_dir / "owner.lock", os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)  # held for the whole test: a "live" owner
    try:
        dsa.sweep(tmp_path)
        assert run_dir.is_dir()
    finally:
        os.close(lock_fd)


def test_sweep_removes_a_dead_run_but_never_signals_a_pid_that_does_not_match(tmp_path):
    run_dir = _fake_run_dir(tmp_path)
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    try:
        (run_dir / "meta.json").write_text(json.dumps({"pid": proc.pid}), encoding="utf-8")
        # owner.lock intentionally left unlocked: this run "looks dead" to sweep().
        dsa.sweep(tmp_path)
        assert not run_dir.exists()
        assert proc.poll() is None, "a pid whose ps args do not name this run's data dir must never be signalled"
    finally:
        proc.kill()
        proc.wait(timeout=10)


def test_sweep_signals_and_removes_a_dead_run_whose_pid_still_matches(tmp_path):
    run_dir = _fake_run_dir(tmp_path)
    data_dir = run_dir / "data"
    # The fake "postmaster"'s own argv carries the data dir path, exactly like
    # a real `postgres -D <data_dir> ...` would -- this is what
    # `_looks_like_our_postmaster` actually greps `ps` output for.
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)", str(data_dir)])
    try:
        (run_dir / "meta.json").write_text(json.dumps({"pid": proc.pid}), encoding="utf-8")
        dsa.sweep(tmp_path)
        assert not run_dir.exists()
        assert proc.wait(timeout=10) is not None  # SIGQUIT terminated it
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)


def test_sweep_of_a_missing_base_dir_is_a_silent_no_op(tmp_path):
    dsa.sweep(tmp_path / "does-not-exist")  # does not raise


def test_sweep_leaves_a_fresh_starting_directory_alone(tmp_path):
    """Review B-3: `start()` publishes a new run under `STAGING_PREFIX`
    (not `run-*`) until it holds its own lock, precisely so a concurrent
    `sweep()` elsewhere can never `rmtree` it out from under a start() in
    progress. `sweep()`'s `run-*` glob already can't match this prefix;
    this pins that a FRESH `.starting-*` -- possibly with no `owner.lock`
    at all yet -- survives `sweep()` too (age-gated, not lock-gated)."""
    staging = tmp_path / f"{dsa.STAGING_PREFIX}freshrun"
    staging.mkdir()
    dsa.sweep(tmp_path)
    assert staging.is_dir()


def test_sweep_removes_a_stale_starting_directory(tmp_path):
    """The other half of B-3: a `.starting-*` directory old enough that its
    own starting process could only have crashed (STAGING_STALE_AGE is far
    above the ~1s mkdtemp-to-rename window) is not left to leak forever."""
    staging = tmp_path / f"{dsa.STAGING_PREFIX}crashedrun"
    staging.mkdir()
    old = time.time() - dsa.STAGING_STALE_AGE - 5
    os.utime(staging, (old, old))
    dsa.sweep(tmp_path)
    assert not staging.exists()


# ---------------------------------------------------------------------------
# _looks_like_our_postmaster (direct coverage; also exercised via sweep() above)
# ---------------------------------------------------------------------------

def test_looks_like_our_postmaster(tmp_path):
    marker = tmp_path / "marker-data-dir"
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)", str(marker)])
    try:
        assert dsa._looks_like_our_postmaster(proc.pid, marker) is True
        assert dsa._looks_like_our_postmaster(proc.pid, tmp_path / "other-dir") is False
    finally:
        proc.kill()
        proc.wait(timeout=10)
    assert dsa._looks_like_our_postmaster(proc.pid, marker) is False  # dead now


# ---------------------------------------------------------------------------
# suite_lock() / gate_running() (work order §3.1 (a), WP-2). Every test below
# passes an explicit tmp_path `base` (or calls `_real_acquire_suite_lock`
# directly, bypassing the autouse fixture's no-op stub) -- never the real,
# per-uid base dir this machine's other concurrent sessions share.
# ---------------------------------------------------------------------------

def test_suite_lock_exclusive_excludes_shared(tmp_path):
    """Uses `_real_acquire_suite_lock` directly on BOTH sides -- not
    `dsa.suite_lock`, whose internal call to `_acquire_suite_lock` is a bare
    module-global lookup the autouse fixture above has stubbed to a no-op
    for every test (necessarily, to keep `ensure_for_pytest()`'s owned-mode
    path from touching a real lock); going through the wrapper here would
    silently exercise the fake, not the real locking logic under test."""
    base = tmp_path / "base"
    base.mkdir()
    handle = _real_acquire_suite_lock(exclusive=True, wait=5.0, base=base)
    try:
        with pytest.raises(dsa.TestPgError, match="timed out"):
            _real_acquire_suite_lock(exclusive=False, wait=0.3, base=base)
    finally:
        handle.release()


def test_suite_lock_shared_allows_concurrent_shared(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    h1 = _real_acquire_suite_lock(exclusive=False, wait=1.0, base=base)
    try:
        h2 = _real_acquire_suite_lock(exclusive=False, wait=1.0, base=base)
        h2.release()
    finally:
        h1.release()


def test_suite_lock_context_manager_acquires_and_releases(tmp_path, monkeypatch):
    """Coverage for the `suite_lock()` context-manager wrapper itself
    (rather than `_acquire_suite_lock` directly): restores the real
    `_acquire_suite_lock` for this one test only, since `dsa.suite_lock`
    calls it by its own bare module-global name."""
    monkeypatch.setattr(dsa, "_acquire_suite_lock", _real_acquire_suite_lock)
    base = tmp_path / "base"
    base.mkdir()
    intent = dsa._intent_path(base)
    with dsa.suite_lock(True, 5.0, base=base):
        assert intent.exists()
    assert not intent.exists()


def test_suite_lock_second_exclusive_is_refused_immediately(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    handle = _real_acquire_suite_lock(exclusive=True, wait=5.0, base=base)
    try:
        with pytest.raises(dsa.TestPgError, match="gate intent already present"):
            _real_acquire_suite_lock(exclusive=True, wait=0.3, base=base)
    finally:
        handle.release()


def test_shared_lock_waits_for_gate_intent(tmp_path):
    """WP-2 §3.1 table row 5: a shared acquisition waits for `gate.intent`
    to stop being LIVE before even trying to flock (gate-starvation
    prevention) -- a genuinely live intent (review M-1: its own flock
    actually held, not merely the file existing; a bare `write_text` alone
    is now correctly treated as stale and would proceed immediately, see
    the dedicated stale-intent tests below).

    mutation (`dsa_testpg.py`): remove the `while _intent_is_live(intent):
    ...` wait -- this test goes red because a shared acquisition would then
    succeed immediately despite a live intent.
    """
    base = tmp_path / "base"
    base.mkdir()
    holder = _real_acquire_suite_lock(exclusive=True, wait=1.0, base=base)
    try:
        with pytest.raises(dsa.TestPgError, match="gate intent"):
            _real_acquire_suite_lock(exclusive=False, wait=0.3, base=base)
    finally:
        holder.release()


def test_shared_lock_proceeds_once_gate_intent_clears(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    holder = _real_acquire_suite_lock(exclusive=True, wait=1.0, base=base)

    def release_soon():
        time.sleep(0.2)
        holder.release()

    threading.Thread(target=release_soon, daemon=True).start()
    handle = _real_acquire_suite_lock(exclusive=False, wait=5.0, base=base)
    handle.release()


def test_stale_gate_intent_does_not_block_a_shared_acquisition(tmp_path):
    """review M-1: a stale `gate.intent` (present, but no live flock -- a
    crashed gate's own leftover) must not make a shared acquirer wait at
    all, and is cleaned up as a side effect.

    mutation (`dsa_testpg.py`): make `_intent_is_live()` return True
    whenever the file merely exists (drop the flock check) -- this test
    goes red because the acquisition would then time out instead of
    succeeding immediately."""
    base = tmp_path / "base"
    base.mkdir()
    intent = dsa._intent_path(base)
    intent.write_text("")
    handle = _real_acquire_suite_lock(exclusive=False, wait=0.5, base=base)
    handle.release()
    assert not intent.exists()


def test_stale_gate_intent_does_not_refuse_a_new_gate(tmp_path):
    """review M-1: a stale `gate.intent` must not refuse a NEW gate's own
    exclusive acquisition either -- it is silently reclaimed (stamped with
    the new gate's own pid) rather than treated as "another gate running"."""
    base = tmp_path / "base"
    base.mkdir()
    intent = dsa._intent_path(base)
    intent.write_text("")
    handle = _real_acquire_suite_lock(exclusive=True, wait=0.5, base=base)
    try:
        assert intent.read_text() == str(os.getpid())
    finally:
        handle.release()
    assert not intent.exists()


def test_gate_running_detects_a_live_intent_and_a_live_lock(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    assert dsa.gate_running(base=base) == (False, "")

    # review M-1: a LIVE intent (its own flock actually held) -- not merely a file that exists.
    handle = _real_acquire_suite_lock(exclusive=True, wait=1.0, base=base)
    try:
        running, reason = dsa.gate_running(base=base)
        assert running and "gate intent" in reason
    finally:
        handle.release()
    assert dsa.gate_running(base=base) == (False, "")

    lock_path = dsa._suite_lock_path(base)
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        running, reason = dsa.gate_running(base=base)
        assert running and "suite lock held" in reason
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    assert dsa.gate_running(base=base) == (False, "")


def test_gate_running_reports_a_stale_intent_as_not_running_and_cleans_it_up(tmp_path):
    """review M-1: `gate_running()` must VERIFY liveness (a real flock on
    the intent file), never merely infer it from the file's existence -- a
    stale `gate.intent` (a `kill -9`ed or crashed gate's own leftover, no
    live flock) must report `(False, "")`, not wedge `handover_ready.py`
    into NOT READY forever, and is removed here as a side effect.

    mutation (`dsa_testpg.py`): make `gate_running()` treat mere existence
    of `gate.intent` as live again (drop the `_intent_is_live()` call) --
    this test goes red because a stale file would then report `True`."""
    base = tmp_path / "base"
    base.mkdir()
    intent = dsa._intent_path(base)
    intent.write_text("")
    assert dsa.gate_running(base=base) == (False, "")
    assert not intent.exists()


def test_gate_running_never_blocks_or_leaves_the_lock_held(tmp_path):
    """gate_running() is read-only: a caller must be able to acquire the
    exclusive lock immediately afterward, proving the probe released
    whatever it (possibly) took."""
    base = tmp_path / "base"
    base.mkdir()
    assert dsa.gate_running(base=base) == (False, "")
    handle = _real_acquire_suite_lock(exclusive=True, wait=0.3, base=base)
    handle.release()
