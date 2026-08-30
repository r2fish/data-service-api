"""Pure, DB-free unit test for `conformance_adapter_mitatedb_http.py`'s own
`_prefix_like_pattern` (WP-3 mutation-testing target: "adapter sweep の
prefix 無条件化").

`_sweep_prefix` uses this function's return value as the SQL `LIKE`
pattern scoping which databases/roles it enumerates before dropping them
-- a real, destructive operation against a real, shared local PostgreSQL
cluster. This test deliberately never calls `_sweep_prefix` itself (doing
so with an unconditional `%` pattern would drop every unrelated database/
role on a shared cluster); it only exercises the pure pattern-computation
function, which is exactly where the "sweep の prefix 無条件化" mutation
lives.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "conformance"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "conformance-tests"))

import conformance_adapter_mitatedb_http as m  # noqa: E402


def test_prefix_like_pattern_is_scoped_to_the_given_prefix() -> None:
    assert m._prefix_like_pattern("mitatedbhttpabcd1234") == "mitatedbhttpabcd1234%"


def test_prefix_like_pattern_never_degrades_to_an_unconditional_wildcard() -> None:
    pattern = m._prefix_like_pattern("mitatedbhttpabcd1234")
    assert pattern != "%"
    assert pattern.startswith("mitatedbhttpabcd1234")


def test_prefix_like_pattern_rejects_an_empty_prefix_rather_than_silently_matching_everything() -> None:
    import pytest

    with pytest.raises(ValueError):
        m._prefix_like_pattern("")
