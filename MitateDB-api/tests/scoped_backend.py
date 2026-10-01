"""Test helper: call a `PostgresBackend` method in a request scope of its own.

A backend method takes the `RequestScope` of the request it runs in
(`scope=`); a test that drives one method directly, outside any cell, has no
request. `scoped(backend).field_types("things")` opens a scope, calls the
method with it and closes the scope, which returns the connections and rolls
back whatever the call left uncommitted -- exactly what one request would do.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator
from unittest.mock import patch

from mitatedb_api.psycopg_counting import CountingConnection

# Methods that are not storage calls: passed through without a scope.
_PLAIN = frozenset({
    "request_scope", "close", "check_reserved", "encode_value", "prepared_stats", "pool_stats",
    "schema_lock_stats", "verify_platform_upgrades", "lock_schema", "lock_entities",
})
# Methods that need the runtime connection as well, and the scope kind each opens.
_KIND = {"read": "query", "delete": "dml", "insert_in_transaction": "dml", "update_in_transaction": "dml",
         "delete_in_transaction": "dml", "record_idempotency": "dml", "commit": "dml", "rollback": "dml",
         "begin": "dml"}


class _Scoped:
    def __init__(self, backend: Any) -> None:
        self._backend = backend

    def __getattr__(self, name: str) -> Any:
        attribute = getattr(self._backend, name)
        if name in _PLAIN or not callable(attribute):
            return attribute

        def call(*args: Any, **kwargs: Any) -> Any:
            with self._backend.request_scope(_KIND.get(name, "schema")) as scope:
                return attribute(*args, scope=scope, **kwargs)

        return call


def scoped(backend: Any) -> Any:
    return _Scoped(backend)


@contextmanager
def commits_failing(backend: Any, role: str, failure: BaseException, *, after: int = 0) -> Iterator[dict]:
    """While active, `commit()` on every connection `backend`'s `role` pool
    (`"developer"` / `"runtime"`) hands out from now on raises `failure`,
    from the `after + 1`-th commit on; `calls["n"]` counts the commits seen.
    The connections are pooled, so no attribute of the backend can be
    patched to stand in for "its" connection: the commit of whichever
    connection the next request borrows is what fails.
    """
    pool = getattr(backend, f"_{role}_pool")
    real_acquire = pool.acquire
    real_commit = CountingConnection.commit
    marked: set[int] = set()
    calls = {"n": 0}

    def acquire(*args: Any, **kwargs: Any) -> Any:
        conn = real_acquire(*args, **kwargs)
        marked.add(id(conn))
        return conn

    def commit(self: Any, *args: Any, **kwargs: Any) -> Any:
        if id(self) in marked:
            calls["n"] += 1
            if calls["n"] > after:
                raise failure
        return real_commit(self, *args, **kwargs)

    with patch.object(pool, "acquire", acquire), patch.object(CountingConnection, "commit", commit):
        yield calls
