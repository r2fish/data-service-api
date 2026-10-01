"""Ledger R-119 (design docs/design/MITATEDB_APPLICATION_SERIALIZATION_V0_1.md
section 2.3, hole 1; D-5): `ApplicationCell.read_page`'s response decode
reads no catalog after the request's scope has ended. The declared types the
rows are decoded with are read in the scope, with the request's other
catalog reads, and `_decode_rows` uses them; nothing the request does on a
backend connection happens after its scope returned the connections and
released the concurrency gate.

Completion condition: every `backend.field_types` call a `read_page` makes
carries the request's scope and happens while that scope is open, at least
one such call happens (no silent no-op), and the decoded response is right
(JSON-typed fields restored). Checked with an in-process cell whose
backend's `request_scope` is wrapped to count how many scopes are open and
whose `field_types` is wrapped by a spy that records, per call, whether a
scope was passed and whether one was open.

Mutation (ledger row): read the decode's catalog back out of the scope --
drop the `declared_types = self._backend.field_types(collection, scope=
scope)` line in `cell.py`'s `read_page` and decode after the `with
self._backend.request_scope(...)` block with `self._decode_rows(rows,
self._backend.field_types(collection))`; the spy then records a call with
no scope and no open scope, and this test goes red.
"""
import os
import sys
from contextlib import contextmanager

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mitatedb_api import Role
from mitatedb_api.auth import Principal
from mitatedb_api.cell import ApplicationCell
from mitatedb_api.field_types import CONTRACT_TYPE_TO_FOUNDATION_TYPE


def test_read_page_reads_the_catalog_only_inside_its_request_scope():
    cell = ApplicationCell("r119app")
    developer = Principal(application_id="r119app", credential_id="dev", role=Role.DEVELOPER)
    runtime = Principal(application_id="r119app", credential_id="rt", role=Role.RUNTIME)
    contract_types = {"title": "string", "flags": "object"}
    fields = {name: CONTRACT_TYPE_TO_FOUNDATION_TYPE[t] for name, t in contract_types.items()}
    cell.create_collection(developer, "notes", fields, field_types=contract_types)
    cell.insert(runtime, "notes", {"title": "a", "flags": {"k": 1}})

    backend = cell._backend  # noqa: SLF001 -- test-only reach-in, same convention as test_r78_pool_wait_stats.py
    real_request_scope = backend.request_scope
    real_field_types = backend.field_types
    open_scopes = {"n": 0}
    calls = []

    @contextmanager
    def counting_request_scope(*args, **kwargs):
        with real_request_scope(*args, **kwargs) as scope:
            open_scopes["n"] += 1
            try:
                yield scope
            finally:
                open_scopes["n"] -= 1

    def spying_field_types(collection, *, scope=None):
        calls.append({"scope_passed": scope is not None, "scope_open": open_scopes["n"] > 0})
        return real_field_types(collection, scope=scope)

    backend.request_scope = counting_request_scope
    backend.field_types = spying_field_types
    try:
        items, next_page = cell.read_page(runtime, "notes")
    finally:
        backend.request_scope = real_request_scope
        backend.field_types = real_field_types

    assert items == [{"title": "a", "flags": {"k": 1}}]
    assert next_page is None
    # The decode's declared types were read at least once (no silent
    # no-op), and every such read carried the request's scope and happened
    # while it was open.
    assert len(calls) >= 1
    assert calls == [{"scope_passed": True, "scope_open": True}] * len(calls)
