"""Host-shared `concurrency` admission (design docs/design/
MULTI_PROCESS_WORKER_V0_1.md D-3 (2)/(2')).

A deployment's declared `concurrency` bound is a count of in-flight
requests the whole deployment must never exceed at once. A single-process
composition root holds that count in memory; once `--workers N` (N >= 2)
serves the SAME base URL from N processes, an in-memory counter is no
longer shared -- each worker admits up to the declared bound
INDEPENDENTLY, so the deployment as a whole can run up to N times over.

This module closes that gap with a small number of `slot-<i>` files inside
one directory the deployer names (`R2DB_SLOT_DIR`) -- one file per unit of
the declared bound. A request holds `concurrency` by taking an exclusive,
non-blocking `flock()` on exactly one of those files for the request's own
duration; releasing is a plain `close()`. Every worker process on the SAME
host opens the SAME directory, so the kernel -- not this process' own
memory -- is what makes the bound hold across every worker. `fcntl.flock`
is a stdlib-only mechanism (no new dependency), and it is released
automatically if the holding process dies (crash safety) -- unlike
a row held in PostgreSQL, which a crashed connection's own server-side
cleanup must first notice.

Every acquisition scans the `slot-<i>` files while it holds an exclusive
`flock()` on one more file in the same directory, `scan` (a name no
`slot-<i>` file and not `selfcheck` share, opened with the same flags
and mode). Every `slot-<i>` lock is taken by `HostSharedConcurrencySlots.
acquire` alone, and only under `scan`, so while one scan runs no other
acquisition takes a slot: a slot the scan sees held was already held
when the scan started, and "every slot held" is never reported while
fewer than `limit` requests hold one. `scan` is closed right after the
scan -- as soon as one slot is taken or every slot is seen held -- so no
request holds `scan` while it runs, and releasing a slot takes no lock
at all (a plain `close()`). A direct `flock()` probe of a `slot-<i>`
file from outside this module (a test observing which slots are held)
bypasses `scan`, so it is sound only while no acquisition runs
concurrently with it.

Stdlib only. Every syscall in this module runs on the event-loop thread
(design §9 (i)). A free slot is never waited for: a directory whose
slots are all held is refused at once with `LimitExceeded`. `scan` is
waited for, with a deadline -- `LOCK_EX | LOCK_NB` is retried every
`_SCAN_LOCK_INTERVAL_S` until `_SCAN_LOCK_TIMEOUT_S` has passed, then
`SlotBackendError` (fail-closed, the caller's existing 503) -- and the
event loop is blocked for that wait, so a process frozen while it holds
`scan` (SIGSTOP, a debugger) stalls every other acquisition on this host
for at most that deadline each, never indefinitely. With `scan`
uncontended, an acquisition that finds every slot held costs `3 * limit
+ 3` syscalls -- one `open`/`flock`/`close` triple for `scan` and one for
each rejected `slot-<i>` candidate (L = 32 is 99).
"""
from __future__ import annotations

import errno
import fcntl
import os
import secrets
import stat
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator

#: the one file `selfcheck_slot_locking` below opens twice in the same
#: process -- deliberately never one of the `slot-<i>` files a real
#: request might be holding at the same moment this self-check runs
#: (design: "自己検査は専用ファイル selfcheck を使い、slot-<i> を
#: 開かない").
SELFCHECK_FILENAME = "selfcheck"

#: the one file `HostSharedConcurrencySlots.acquire` holds an exclusive
#: lock on while it scans the `slot-<i>` files -- a name distinct from
#: every `slot-<i>` file and from `SELFCHECK_FILENAME`, so holding it is
#: never counted as holding a slot.
SCAN_FILENAME = "scan"

#: how long `acquire` keeps retrying the `scan` lock before it fails
#: closed with `SlotBackendError`, in seconds.
_SCAN_LOCK_TIMEOUT_S = 1.0

#: the pause between two attempts at the `scan` lock, in seconds.
_SCAN_LOCK_INTERVAL_S = 0.0002

#: `open()`'s own flag set for the self-check file, the `scan` file and
#: every `slot-<i>` file: `O_NOFOLLOW` refuses a symlink planted in the
#: slot directory, `O_CLOEXEC` keeps a held slot's own fd from
#: leaking into a child process this one might spawn later,
#: `O_CREAT | O_RDWR` opens-or-creates the file this
#: process itself owns (mode 0600, passed to `os.open` separately below).
_OPEN_FLAGS = os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC

#: the mode every file this module creates gets -- helper-owned, not
#: world- or group-readable (design D-3 (2')).
_FILE_MODE = 0o600

#: `flock(LOCK_EX | LOCK_NB)`'s own "the lock is held by someone else"
#: errno set -- anything else (a syscall filter faking
#: `EPERM`, for one measured example) is a backend
#: failure, never read as "held".
_HELD_ERRNOS = frozenset({errno.EWOULDBLOCK, errno.EAGAIN, errno.EACCES})


class SlotDirectoryError(RuntimeError):
    """A startup-time failure of the configured slot directory itself
    (missing, wrong owner, wrong mode, or a self-check that could not
    prove real mutual exclusion) -- always raised before a composition
    root ever starts serving, never per-request."""


class LimitExceeded(Exception):
    """`HostSharedConcurrencySlots.acquire` raises this when every slot
    among `limit` is currently held by some other in-flight request --
    the caller maps this to the `concurrency` `LIMIT_EXCEEDED` denial,
    exactly the meaning the pre-existing in-memory counter's own refusal
    already carried."""


class SlotBackendError(RuntimeError):
    """`HostSharedConcurrencySlots.acquire` raises this for any errno
    other than the `_HELD_ERRNOS` set above, for a file it cannot open,
    and when the `scan` lock is not obtained within
    `_SCAN_LOCK_TIMEOUT_S` -- fail-closed: the caller
    maps this to the SAME 503 SERVICE_UNAVAILABLE an
    existing PostgreSQL backend failure already produces, never silently
    treated as either 'admitted' or 'held'."""


def check_slot_directory(path: Path) -> None:
    """Startup-time checks only (design D-3 (2') "build_app() は検査だけ
    する"): `path` exists, is a directory, is owned by this process' own
    effective uid, and is mode 0700 -- raises `SlotDirectoryError` naming
    the failure otherwise. Never creates `path` itself -- a directory
    `build_app()` had to create on its own could differ across the
    several worker processes a `--workers N` supervisor starts (design's
    own "worker ごとに別の directory が起きる経路を作らない")."""
    try:
        info = path.stat()
    except OSError as exc:
        raise SlotDirectoryError(f"slot directory {path} does not exist or is not accessible: {exc}") from exc
    if not stat.S_ISDIR(info.st_mode):
        raise SlotDirectoryError(f"slot directory {path} is not a directory")
    if info.st_uid != os.geteuid():
        raise SlotDirectoryError(
            f"slot directory {path} is owned by uid {info.st_uid}, not this process' own effective uid {os.geteuid()}"
        )
    mode = stat.S_IMODE(info.st_mode)
    if mode != 0o700:
        raise SlotDirectoryError(f"slot directory {path} has mode {oct(mode)}, expected 0700")


def selfcheck_slot_locking(path: Path) -> None:
    """Startup-time self-check (design D-3 (2')): opens `path`'s own
    dedicated `selfcheck` file TWICE, in this SAME process, takes
    `LOCK_EX` on the first open, then requires the second open's
    `LOCK_EX | LOCK_NB` to be rejected with one of `_HELD_ERRNOS`. A
    `flock()` faked by an `fcntl()`-based emulation layer, a syscall
    filter, or a sandbox that silently no-ops locking would let the
    second attempt succeed instead -- caught here, at startup, rather
    than as a real double-admission the first time two genuinely
    concurrent requests race for the same slot (design's own "本番の
    HAVE_FLOCK の未確認も覆う"). Raises `SlotDirectoryError` on any
    outcome other than "the second lock attempt was correctly rejected".
    """
    target = path / SELFCHECK_FILENAME
    first_fd = os.open(str(target), _OPEN_FLAGS, _FILE_MODE)
    try:
        fcntl.flock(first_fd, fcntl.LOCK_EX)
        second_fd = os.open(str(target), _OPEN_FLAGS, _FILE_MODE)
        try:
            try:
                fcntl.flock(second_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                if exc.errno not in _HELD_ERRNOS:
                    raise SlotDirectoryError(
                        f"slot directory {path} self-check: unexpected errno {exc.errno} from a second "
                        f"exclusive lock attempt on the same file"
                    ) from exc
                # Correctly rejected -- flock() genuinely excludes here.
            else:
                raise SlotDirectoryError(
                    f"slot directory {path} self-check: a second exclusive lock on the same file, in this "
                    f"same process, was NOT rejected -- flock() does not exclude on this filesystem/kernel"
                )
        finally:
            os.close(second_fd)
    finally:
        os.close(first_fd)


def _slot_path(directory: Path, index: int) -> Path:
    return directory / f"slot-{index}"


class HostSharedConcurrencySlots:
    """Bound to one slot directory (already checked by `check_slot_
    directory`/`selfcheck_slot_locking` at startup) -- `acquire(limit)`
    below is the per-request admission gate `DataService` calls once for
    every request while this deployment declares `concurrency` `enforced`
    across its own workers (design D-3 (4))."""

    def __init__(self, directory: Path, *, random_below: Callable[[int], int] = secrets.randbelow) -> None:
        self._directory = directory
        # the search start point follows a random source -- injectable
        # so a test can observe it, never hardcoded to 0.
        self._random_below = random_below

    def _lock_scan_file(self) -> int:
        """Opens `scan` fresh for this one call -- never an fd shared with
        another call, so two threads of this same process exclude each
        other exactly as two processes do (a `flock()` lock belongs to the
        open file description) -- and takes its exclusive lock, retrying
        `LOCK_EX | LOCK_NB` every `_SCAN_LOCK_INTERVAL_S` while the errno
        is one of `_HELD_ERRNOS`. Returns the locked fd; the caller closes
        it. Raises `SlotBackendError`, with the fd already closed, when
        the open fails (a symlink planted as `scan` included), at once on
        any other errno, and when `_SCAN_LOCK_TIMEOUT_S` passes with
        `scan` still held elsewhere -- that message names the expired
        `scan` deadline. Any other exception raised while it waits (a
        `KeyboardInterrupt` raised during the pause between two attempts
        included) also closes the fd before it propagates."""
        path = self._directory / SCAN_FILENAME
        try:
            scan_fd = os.open(str(path), _OPEN_FLAGS, _FILE_MODE)
        except OSError as exc:
            raise SlotBackendError(f"could not open scan file {path}: {exc}") from exc
        try:
            deadline = time.monotonic() + _SCAN_LOCK_TIMEOUT_S
            while True:
                try:
                    fcntl.flock(scan_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as exc:
                    if exc.errno not in _HELD_ERRNOS:
                        raise SlotBackendError(f"unexpected errno {exc.errno} from scan file {path}") from exc
                    if time.monotonic() >= deadline:
                        raise SlotBackendError(
                            f"scan file {path}: lock deadline of {_SCAN_LOCK_TIMEOUT_S}s expired while another "
                            f"acquisition held it"
                        ) from exc
                    time.sleep(_SCAN_LOCK_INTERVAL_S)
                    continue
                return scan_fd
        except BaseException:
            os.close(scan_fd)
            raise

    @contextmanager
    def acquire(self, limit: int) -> Iterator[None]:
        """Holds exactly one of `slot-0` .. `slot-<limit - 1>` for the
        duration of the `with` block. Takes the `scan` lock first
        (`_lock_scan_file`), then starts the search at a random index and
        tries each of the `limit` slots at most once with `LOCK_EX |
        LOCK_NB`; `scan` is closed right after that search, before the
        `with` body runs, whether a slot was taken or not. Raises
        `LimitExceeded` if every slot is already held -- without waiting
        for one to become free -- and `SlotBackendError` on any other
        failure, a `scan` lock not obtained within its deadline included.
        Every fd is opened fresh for this call: each REJECTED candidate's
        fd is closed before the next one is tried (no open fd accumulates
        across rejections), a candidate's fd is also closed when its own
        `flock()` raises anything else (a `KeyboardInterrupt` included),
        the `scan` fd is closed on every path out of the search, and the
        held slot's own fd is closed in `finally` -- on the happy path and
        on an exception raised inside the `with` block. An exception
        delivered asynchronously (a signal handler's `KeyboardInterrupt`)
        in the instant between an `open()` or a successful `flock()`
        returning and the `try` that owns its fd still leaks that fd --
        Python gives no way to close that window."""
        if limit < 1:
            raise ValueError(f"limit must be a positive integer, got {limit!r}")
        scan_fd = self._lock_scan_file()
        held_fd: int | None = None
        try:
            start = self._random_below(limit)
            for offset in range(limit):
                index = (start + offset) % limit
                path = _slot_path(self._directory, index)
                try:
                    candidate_fd = os.open(str(path), _OPEN_FLAGS, _FILE_MODE)
                except OSError as exc:
                    raise SlotBackendError(f"could not open slot file {path}: {exc}") from exc
                try:
                    fcntl.flock(candidate_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as exc:
                    os.close(candidate_fd)
                    if exc.errno in _HELD_ERRNOS:
                        continue
                    raise SlotBackendError(f"unexpected errno {exc.errno} from slot file {path}") from exc
                except BaseException:
                    os.close(candidate_fd)
                    raise
                held_fd = candidate_fd
                break
        finally:
            os.close(scan_fd)
        if held_fd is None:
            raise LimitExceeded(f"no slot available among {limit} in {self._directory}")
        try:
            yield
        finally:
            os.close(held_fd)
