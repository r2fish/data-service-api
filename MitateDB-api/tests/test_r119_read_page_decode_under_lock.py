"""Ledger R-119 (design docs/design/MITATEDB_APPLICATION_SERIALIZATION_V0_1.md
section 2.3, hole 1): `ApplicationCell.read_page`'s response decode
(`_decode_rows` -> `backend.field_types`, a developer-connection catalog
SELECT that commits on `PostgresBackend`) runs INSIDE the cell's own
request-wide lock -- the same scope every other catalog read of the
request already holds -- never after the lock (and the concurrency gate)
has been released.

Completion condition (ledger row): the decode's catalog read is performed
under the lock. Checked with an in-process cell whose backend's
`field_types` is wrapped by a spy that asks, from a SECOND thread, whether
`cell._lock` can be taken non-blockingly at that moment: `False` means the
request thread still holds it.

Mutation (ledger row): move `rows = self._decode_rows(collection, rows)`
in `cell.py`'s `read_page` back out of the outer `with self._lock:` block
(dedent it to method level, after the gate) -- `held_during_decode` then
records `True` for the probe (the lock was free) and this test goes red.
"""
import os
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mitatedb_api import Role
from mitatedb_api.auth import Principal
from mitatedb_api.cell import ApplicationCell
from mitatedb_api.field_types import CONTRACT_TYPE_TO_FOUNDATION_TYPE


def _lock_is_free_from_another_thread(lock) -> bool:
    """`True` iff a thread OTHER than the caller can take `lock` right now
    (a non-blocking acquire from a helper thread succeeds and is released
    at once). An `RLock` held by the calling thread reads as held here,
    because the helper is a different thread."""
    outcome = {}

    def probe():
        got = lock.acquire(blocking=False)
        outcome["free"] = got
        if got:
            lock.release()

    t = threading.Thread(target=probe)
    t.start()
    t.join()
    return outcome["free"]


def test_read_page_decodes_its_rows_while_still_holding_the_cell_lock():
    cell = ApplicationCell("r119app")
    developer = Principal(application_id="r119app", credential_id="dev", role=Role.DEVELOPER)
    runtime = Principal(application_id="r119app", credential_id="rt", role=Role.RUNTIME)
    contract_types = {"title": "string", "flags": "object"}
    fields = {name: CONTRACT_TYPE_TO_FOUNDATION_TYPE[t] for name, t in contract_types.items()}
    cell.create_collection(developer, "notes", fields, field_types=contract_types)
    cell.insert(runtime, "notes", {"title": "a", "flags": {"k": 1}})

    backend = cell._backend  # noqa: SLF001 -- test-only reach-in, same convention as test_r78_pool_wait_stats.py
    real_field_types = backend.field_types
    lock_free_during_decode = []

    def spying_field_types(collection):
        lock_free_during_decode.append(_lock_is_free_from_another_thread(cell._lock))  # noqa: SLF001
        return real_field_types(collection)

    backend.field_types = spying_field_types
    try:
        items, next_page = cell.read_page(runtime, "notes")
    finally:
        backend.field_types = real_field_types

    assert items == [{"title": "a", "flags": {"k": 1}}]
    assert next_page is None
    # The decode's own catalog read happened at least once (no silent
    # no-op), and every such read saw the cell lock still held by the
    # request thread.
    assert len(lock_free_during_decode) >= 1
    assert lock_free_during_decode == [False] * len(lock_free_during_decode)
