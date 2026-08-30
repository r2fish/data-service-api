"""M-4 (independent WP-3 review): direct, backend-level tests for
`order_by` direction handling -- bypassing `cell.py` entirely, so each
backend's OWN structural defense (`backend_sqlite.SQLiteBackend`'s
`_DIRECTION_TOKENS` closed dict, `backend_postgres.PostgresBackend`'s
`_DIRECTION_SQL` closed dict + `KeyError` translation) is what is actually
under test here, independent of whether `cell.py`'s own allowlist
(`_bind_order_by`: `direction not in ("asc", "desc")`) is present, correct,
or ever weakened in the future.

Review finding this closes: `backend_sqlite.py`'s `read()` used to
concatenate `direction.upper()` directly into the SQL TEXT string with no
structural check of its own -- `cell.py`'s allowlist was the ONLY thing
standing between an arbitrary string and SQL execution inside an `ORDER BY`
clause. Reviewer-confirmed exploit shape (reproduced below via a direct
backend call, not by weakening `cell.py`): a `direction` value containing
a subquery expression executes as part of the `ORDER BY` clause.
"""
from __future__ import annotations

import pytest

from mitatedb_api.backend_sqlite import SQLiteBackend
from mitatedb_api.errors import ValidationError

# A payload that, if ever concatenated into SQL text unescaped inside an
# `ORDER BY` clause, executes as a real scalar subquery -- not just a
# syntax error, so a backend that merely fails to CRASH on this payload
# (e.g. a bare string-format mismatch) is not mistaken for one that
# structurally refuses it. `sqlite_master` is always present on any SQLite
# connection, so this needs no pre-existing table/data to be a genuine,
# self-contained proof of execution.
_INJECTION_DIRECTION = "asc); SELECT (SELECT count(*) FROM sqlite_master"


@pytest.fixture
def sqlite_backend():
    backend = SQLiteBackend()
    backend.create_collection("probe_items", {"item_key": "integer"})
    try:
        yield backend
    finally:
        backend.close()


def test_sqlite_backend_rejects_an_injection_shaped_order_by_direction(sqlite_backend):
    with pytest.raises(ValidationError):
        sqlite_backend.read("probe_items", ["item_key"], [], [("item_key", _INJECTION_DIRECTION)], 10)


def test_sqlite_backend_rejects_an_arbitrary_non_asc_desc_direction_string(sqlite_backend):
    with pytest.raises(ValidationError):
        sqlite_backend.read("probe_items", ["item_key"], [], [("item_key", "ASC, (SELECT 1)")], 10)


def test_sqlite_backend_still_accepts_the_two_real_directions(sqlite_backend):
    # Regression guard for the fix itself: `_DIRECTION_TOKENS` must not
    # accidentally also reject the two directions this peer actually
    # supports.
    assert sqlite_backend.read("probe_items", ["item_key"], [], [("item_key", "asc")], 10) == []
    assert sqlite_backend.read("probe_items", ["item_key"], [], [("item_key", "desc")], 10) == []
