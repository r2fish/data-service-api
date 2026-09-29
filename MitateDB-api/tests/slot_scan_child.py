"""The body of the second process `test_r113_multi_process_wiring.py`'s
cross-process `scan` test starts with the `spawn` start method. Kept in
its own module, importing only `mitatedb_api.concurrency_slots`, so the
spawned interpreter never imports that test module (and its PostgreSQL
fixtures) just to unpickle this function.

Every wait here is bounded by `timeout_s`."""
from __future__ import annotations

import fcntl
import os
from pathlib import Path


def acquire_after_scan(slot_dir, limit, start, timeout_s, progressed, acquired, release, report) -> None:
    """Acquires one of `limit` slots in `slot_dir`, the search starting at
    `start`. Puts `("module", <concurrency_slots.__file__>)` on `report`
    first, so the parent can check this process ran the same module file
    it did. Sets `progressed` the first time its `scan` lock attempt finds
    `scan` held, and again once it holds a slot or has failed; sets
    `acquired` once it holds a slot, then holds it until `release` is set.
    Ends by putting `("outcome", "acquired" | "refused" | <repr>)`."""
    from mitatedb_api import concurrency_slots

    report.put(("module", os.path.realpath(concurrency_slots.__file__)))
    concurrency_slots._SCAN_LOCK_TIMEOUT_S = timeout_s
    scan_path = Path(slot_dir) / concurrency_slots.SCAN_FILENAME
    real_flock = fcntl.flock

    def _observing_flock(fd, operation):
        try:
            return real_flock(fd, operation)
        except OSError as exc:
            if exc.errno in concurrency_slots._HELD_ERRNOS and os.fstat(fd).st_ino == os.stat(scan_path).st_ino:
                progressed.set()
            raise

    fcntl.flock = _observing_flock
    slots = concurrency_slots.HostSharedConcurrencySlots(Path(slot_dir), random_below=lambda n: start)
    try:
        with slots.acquire(limit):
            acquired.set()
            progressed.set()
            release.wait(timeout_s)
        outcome = "acquired"
    except concurrency_slots.LimitExceeded:
        outcome = "refused"
    except Exception as exc:  # reported to the parent, never raised in this process
        outcome = repr(exc)
    progressed.set()
    report.put(("outcome", outcome))
