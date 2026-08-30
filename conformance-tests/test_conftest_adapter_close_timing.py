"""Regression guard for `conftest.py`'s `adapter` fixture close-timing fix
(WP-2.5c review item 1, docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md
R-8).

The bug: a `scope="session"` fixture that ALSO carries `params=...` is torn
down PER PARAM, not once for the whole session -- pytest's default test-item
reordering groups every test sharing one param value together and finalizes
that param's fixture instance as soon as the LAST test needing it finishes,
which can be long before the session itself ends (whenever collection moves
on to the next param group). `conftest.py`'s `adapter` fixture used to call
`adapter_obj.close()` in its own finalizer -- so a registry-wide guard that
reads `registered_adapters()` directly (bypassing the `adapter` fixture),
running after an earlier param group's tests have already finished, could
observe an already-`close()`'d adapter. The fix moves every `close()` call
into a separate, NON-parametrized, autouse session fixture
(`_close_all_adapters_at_session_end`), whose own single finalizer genuinely
runs only once the whole session's fixture stack unwinds.

This is a timing property of pytest's own fixture-teardown machinery, not
something a single, direct unit test can observe without actually running a
nested pytest session with multiple param groups and inspecting the ORDER
of `use`/`close` events across it -- hence `pytester` (pytest's own built-in
plugin for testing pytest plugins/conftests), rather than a distilled
same-process assertion. The inner replica below deliberately does NOT import
the real `conftest.py`/`registry.json`/real adapters (which would drag in
real PostgreSQL provisioning into a nested session, just to test a pure
fixture-scoping property): it reproduces the exact bug-class shape --
`scope="session"` + `params` + a per-param close -- with fake, in-memory-only
adapters, and asserts the same before/after behavior this file's own
`test_conftest_close_all_adapters_visits_every_built_adapter` (below)
confirms directly against the REAL `_close_all_adapters()`.
"""
from __future__ import annotations

import textwrap

import pytest

import conftest

pytest_plugins = ["pytester"]


_CORRECT_INNER_CONFTEST = textwrap.dedent('''
    """Replica of conftest.py's FIXED pattern: `adapter` never closes its
    own param; a separate, non-parametrized, autouse session fixture closes
    everything once, at true session end."""
    import pytest

    _NAMES = ["adapter_a", "adapter_b"]
    _EVENTS = []

    class _FakeAdapter:
        def __init__(self, name):
            self.name = name
        def close(self):
            _EVENTS.append(f"close:{self.name}")

    _BY_NAME = {name: _FakeAdapter(name) for name in _NAMES}

    @pytest.fixture(scope="session", params=_NAMES, ids=_NAMES)
    def adapter(request):
        _EVENTS.append(f"use:{request.param}")
        return _BY_NAME[request.param]

    @pytest.fixture(scope="session", autouse=True)
    def _close_all_adapters_at_session_end():
        yield
        for obj in _BY_NAME.values():
            obj.close()

    def pytest_sessionfinish(session, exitstatus):
        import pathlib
        pathlib.Path("events.log").write_text("\\n".join(_EVENTS))
''')

# MUTATION replica: the exact bug this WP-2.5c item fixes -- `close()`
# called from the `adapter` fixture's OWN per-param finalizer, no separate
# session-end fixture at all. Used only to prove the test below actually
# distinguishes fixed-from-buggy, not to assert this shape is ever correct.
_BUGGY_INNER_CONFTEST = textwrap.dedent('''
    """Replica of conftest.py's PRE-WP-2.5c bug: `adapter` closes its own
    param in its own finalizer -- torn down per param-group rotation, not
    at true session end."""
    import pytest

    _NAMES = ["adapter_a", "adapter_b"]
    _EVENTS = []

    class _FakeAdapter:
        def __init__(self, name):
            self.name = name
        def close(self):
            _EVENTS.append(f"close:{self.name}")

    _BY_NAME = {name: _FakeAdapter(name) for name in _NAMES}

    @pytest.fixture(scope="session", params=_NAMES, ids=_NAMES)
    def adapter(request):
        _EVENTS.append(f"use:{request.param}")
        obj = _BY_NAME[request.param]
        yield obj
        obj.close()

    def pytest_sessionfinish(session, exitstatus):
        import pathlib
        pathlib.Path("events.log").write_text("\\n".join(_EVENTS))
''')

_INNER_TEST = textwrap.dedent('''
    def test_one(adapter):
        pass

    def test_two(adapter):
        pass
''')


def _run_and_read_events(pytester, conftest_source: str) -> list[str]:
    pytester.makeconftest(conftest_source)
    pytester.makepyfile(test_inner=_INNER_TEST)
    result = pytester.runpytest()
    result.assert_outcomes(passed=4)  # 2 tests x 2 params
    return (pytester.path / "events.log").read_text().splitlines()


def test_session_end_fixture_defers_close_past_every_param_rotation(pytester) -> None:
    """The FIXED pattern: no `use:` event may ever occur after the FIRST
    `close:` event -- i.e. every param's tests run to completion (both
    adapters used, by both tests) before either adapter is closed at all.
    This is the real, positive property `conftest.py`'s fix establishes."""
    events = _run_and_read_events(pytester, _CORRECT_INNER_CONFTEST)
    close_indices = [i for i, e in enumerate(events) if e.startswith("close:")]
    assert close_indices, f"no close: event recorded at all -- session-end fixture never ran: {events!r}"
    first_close_index = close_indices[0]
    use_events_after_first_close = [e for e in events[first_close_index:] if e.startswith("use:")]
    assert not use_events_after_first_close, (
        f"a fixture 'use' event occurred after the first 'close' event -- an adapter was closed before "
        f"every param's tests finished: {events!r}"
    )
    assert {e for e in events if e.startswith("close:")} == {"close:adapter_a", "close:adapter_b"}, (
        f"expected both adapters closed exactly once by session end, got: {events!r}"
    )


def test_buggy_per_param_close_pattern_is_actually_caught_by_the_same_check(pytester) -> None:
    """Mutation-injection control (WP-2.5c completion condition (i)): re-runs
    the identical harness against the PRE-fix bug shape
    (`_BUGGY_INNER_CONFTEST`) and confirms the SAME invariant the test above
    checks is violated -- i.e. this file's own check has real detection
    power, not merely a check that happens to hold for the fixed shape by
    construction. `adapter_a`'s `close:` event must land BEFORE `adapter_b`
    is ever used, exactly the early-close defect `registered_adapters()`
    callers could observe mid-session."""
    events = _run_and_read_events(pytester, _BUGGY_INNER_CONFTEST)
    assert "close:adapter_a" in events and "use:adapter_b" in events, (
        f"test setup problem: expected both adapter_a's close and adapter_b's use in the event log: {events!r}"
    )
    assert events.index("close:adapter_a") < events.index("use:adapter_b"), (
        f"expected the buggy per-param-close pattern to close adapter_a BEFORE adapter_b is ever used "
        f"(demonstrating the exact defect the WP-2.5c fix removes) -- got: {events!r}"
    )


# ---------------------------------------------------------------------------
# Direct test of the REAL `_close_all_adapters()` (not a replica): confirms
# it visits every entry in `_BUILT_ADAPTERS` and tolerates one failing
# `close()` without abandoning the rest (WP-2.5c: "close の冪等性・例外時も
# 他を閉じる form").
# ---------------------------------------------------------------------------


class _FakeAdapterAlwaysCloses:
    def __init__(self, name: str) -> None:
        self.name = name
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _FakeAdapterRaisesOnClose:
    def __init__(self, name: str) -> None:
        self.name = name
        self.close_attempted = False

    def close(self) -> None:
        self.close_attempted = True
        raise RuntimeError(f"{self.name}: simulated close() failure")


def test_close_all_adapters_visits_every_adapter_even_if_one_raises(monkeypatch) -> None:
    good_a = _FakeAdapterAlwaysCloses("good_a")
    bad = _FakeAdapterRaisesOnClose("bad")
    good_b = _FakeAdapterAlwaysCloses("good_b")
    monkeypatch.setattr(conftest, "_BUILT_ADAPTERS", [("good_a", good_a), ("bad", bad), ("good_b", good_b)])

    with pytest.raises(RuntimeError, match=r"bad: close\(\) failed"):
        conftest._close_all_adapters()

    assert good_a.closed, "an adapter registered BEFORE the one that raised was never closed"
    assert bad.close_attempted, "the raising adapter's close() was never even attempted"
    assert good_b.closed, "an adapter registered AFTER the one that raised was never closed -- one failure must not abort the rest"
