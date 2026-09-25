"""Design docs/design/PHASE11_KEYSET_PAGING_V1.md D-2a: `backend_sqlite.py`
orders keyset reads with explicit `NULLS FIRST`/`NULLS LAST` clauses, a
piece of SQL syntax SQLite only understands from version 3.30 onward
(earlier versions raise a syntax error on `NULLS FIRST`/`NULLS LAST`).
This pins the interpreter actually running the tests to that floor, since
the CI runner's own sqlite version has not been measured directly
(supervisor ruling on the WP-4 code-review's "measured against both CI
Python jobs" claim, which no run of this suite had performed).

A regression here means either an older interpreter shipped underneath
this repository's own tooling, or `sqlite3` binds against an older linked
library -- in both cases every keyset-ordered SQLite read would fail with
a live syntax error, not a silently wrong NULL placement.
"""
from __future__ import annotations

import sqlite3


def test_sqlite_version_meets_the_nulls_first_last_floor():
    assert sqlite3.sqlite_version_info >= (3, 30, 0), (
        f"sqlite3.sqlite_version_info={sqlite3.sqlite_version_info!r} is below "
        "3.30, the first version to understand the NULLS FIRST/NULLS LAST "
        "syntax backend_sqlite.py's keyset ORDER BY clauses depend on "
        "(design docs/design/PHASE11_KEYSET_PAGING_V1.md D-2a)"
    )
