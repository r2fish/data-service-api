#!/usr/bin/env python3
"""perf_baseline.py -- WP-5 R-12 performance baseline harness.

design: docs/design/PHASE8_EFFECTIVE_BOUNDS_AND_HYGIENE_V1.md D-6.
work order: docs/work-orders/WORK_ORDER_PHASE8_EFFECTIVE_BOUNDS_V1.md WP-5.

Phase 10 WP-7 (design docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md D-8 /
D-12, work order docs/work-orders/WORK_ORDER_PHASE10_DEPLOYMENT_EVIDENCE_V1.md
WP-7) adds `--concurrency K`: every measured sample becomes a GROUP of `K`
requests dispatched together via a single `asyncio.gather` call on the
plug's own event loop (never OS threads -- threads would mix client-side
GIL contention into a measurement whose whole point is server-side event
loop serialization) and timed as one group (start of the gather to the
last member's own completion). `K == 1` walks this identical code path
with singleton groups -- there is no separate, bypassing sequential
branch for it. Defaults are `--n 100 --warmup 10` (WP-7; lowered from the
prior `--n 200 --warmup 20` default -- see `main()`'s own argparse help
and D-8 (1) for why: at `--concurrency 3`, `(n + warmup) * concurrency`
real requests land on ONE credential, and the prior default would put
that past the shared surface's default `requests_per_minute` bound).

**Judgement rule (fixed BEFORE any measurement is taken, design D-8 (2),
U-2; WP-7 completion condition 6)**: if a socket-transport plug's own
`K=3` `p50_ms` exceeds 2x its own `K=1` `p50_ms` for the SAME (peer,
plug, op), that is treated as evidence of server-side event-loop
serialization under concurrent load, and WP-8 (threadpool delegation) is
warranted in this phase; otherwise the measurement is recorded only. This
script does not evaluate or print that comparison itself (P-8: no
thresholds anywhere in this tool) -- applying the rule to two runs' own
`PERF` lines is the supervisor's own recorded judgement. See also
`tools/PERF_BASELINE_README.md`'s own copy of this same rule.

Imports each registered peer's own conformance adapter (`conformance-tests/
registry.json`, read the same way `conformance-tests/conftest.py`'s own
`_load_registry`/`_discover_and_build` do -- this file never hardcodes a
plug or module name; growing the registry grows this tool's own output
with no code change here) and, for every plug, runs three operations --
`query` (`select_eq`, one predicate), `mutate` (`insert`, one operation),
`batch` (`attempt_batch_with_addresses`, a single-entity atomic batch of
exactly 5 operations) -- warmup + N times each, reporting p50/p95 latency
(ms) and the mean number of backend calls per request (`backend_calls`).
A fourth operation, `cross_entity` (`attempt_cross_entity_batch`), is only
measured for a plug that declares `cross_entity_mutation` as something
other than `unavailable` -- currently the three MitateDB-api plugs
(in-process, `-http`, `-socket`); a
plug declaring it `unavailable` (currently both r2db peer plugs) never
gets a `cross_entity` row, because the cost of a request that is refused
before any real work happens is not a performance number (decision 1).

This is NOT a test and NOT a gate. It places NO threshold on anything
(P-8) -- there is no pass/fail judgement here beyond one narrow self-check
(see `_run_self_check` below) that the backend-call counting proxy itself
is not silently counting zero. Every other completion condition for this
tool is a documentation/format match, checked by audit, not by this
script (work order WP-5 completion conditions 2-8).

`backend_calls` is a call count, not a round-trip count: for a PostgreSQL-
backed plug it counts real `psycopg.Cursor.execute`/`.executemany` calls
(a single logical request can and does drive more than one), for the
in-memory (r2db peer, in-process) and SQLite (MitateDB peer, in-process)
plugs it counts calls to the backend/cell object's own public methods
instead -- there is no lower-level "statement" concept to count there.
See `tools/PERF_BASELINE_README.md` for the full limitations list.

Usage:
    ./.venv/bin/python tools/perf_baseline.py [--n N] [--warmup N] [--registry PATH]

WP-2 (docs/work-orders/WORK_ORDER_R44_TEST_PG_ISOLATION_V1.md §3.1 (d)):
measurement runs against this tool's own throwaway PostgreSQL cluster
(`tools/testpg/dsa_testpg.py`'s own `cluster()`), started only after taking
the exclusive suite lock (`dsa_testpg.suite_lock`) -- the same lock
`tools/dev/gate.py` takes, so a perf run and a gate run (or two perf runs)
can never overlap. `main()` returns exit 75 when that lock times out (never
silently degrades to measuring against whatever PostgreSQL happens to be
reachable).

Standard library only, at the top of this file (tools/ convention, see
`tools/public_value_scan.py`'s own module docstring) -- everything this
tool actually touches beyond the standard library (httpx, psycopg, ...)
arrives transitively through the conformance adapters it imports, never
as a new dependency of this file itself.
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import datetime
import importlib
import inspect
import json
import math
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Iterator

ROOT = Path(__file__).resolve().parents[1]
CONFORMANCE_TESTS_DIR = ROOT / "conformance-tests"
REGISTRY_PATH = CONFORMANCE_TESTS_DIR / "registry.json"
TESTPG_DIR = ROOT / "tools" / "testpg"

if str(CONFORMANCE_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(CONFORMANCE_TESTS_DIR))
if str(TESTPG_DIR) not in sys.path:
    sys.path.insert(0, str(TESTPG_DIR))

from adapter import (  # noqa: E402  (path insertion above must run first)
    BatchOperation,
    ConformanceAdapter,
    ScopedBatchOperation,
    fresh_identifier,
)
import dsa_testpg  # noqa: E402  (WP-2, docs/work-orders/WORK_ORDER_R44_TEST_PG_ISOLATION_V1.md §3.1 (d):
# perf_baseline measures against its own throwaway cluster, under the
# exclusive suite lock -- never the shared local PostgreSQL)

REFUSED = 75  # matches tools/dev/_devlib.py's own REFUSED; this file stays
# standard-library only at the top (module docstring) and does not import
# tools/dev, so this is a local literal, not an import of dl.REFUSED.

_BATCH_OPS = 5  # design D-6 decision 1: batch op count is fixed at 5.
_CROSS_ENTITY_OPS = 2  # not fixed by design; this tool's own choice -- see
# the completion report's "design との食い違い" section (2 entities, 1
# insert each, the smallest request that is genuinely cross-entity).


class SelfCheckFailure(RuntimeError):
    """Raised when the backend-call counting proxy observed zero calls for
    a `query` request -- the one non-emptiness self-check this tool
    performs (work order WP-5 completion condition 1). `main()` turns
    this into a non-zero exit, never a silent pass."""


class _CapturedRequest(Exception):
    """Internal control-flow signal, never surfaced past `_capture_one_
    request` (below): raised by the stub this tool temporarily installs
    over an adapter's own `httpx.AsyncClient.send` to grab the exact
    `httpx.Request` object a single op call was about to send, WITHOUT
    sending it -- see `_capture_one_request`'s own docstring for why."""

    def __init__(self, request: Any) -> None:
        super().__init__("internal: a real httpx.Request was captured, not an error")
        self.request = request


class UnknownAdapterShape(RuntimeError):
    """Raised when a registered plug's registry name and its own declared
    `transport_kind` (`adapter.py` port v1.14, design D-1 (A) 4) disagree
    about which transport this tool currently knows how to classify (WP-5
    rework ruling item 4; reworked in Phase 10 WP-3, design D-12, to read
    the declaration instead of the built object's own attribute shape --
    a real socket plug's httpx client can plausibly set the same `_loop`/
    `_client` attributes an ASGI plug's does, so attribute shape alone
    was never safe to guess from). `main()` turns this into a non-zero
    exit, never a silent guess -- see `_classify_plug`'s own docstring
    for the exact agreement this checks."""


# ---------------------------------------------------------------------
# registry discovery (mirrors conformance-tests/conftest.py's own
# `_load_registry`/`_discover_and_build`, procedure-for-procedure -- a
# separate copy, not an import of conftest.py itself, so this tool never
# depends on pytest being importable/configured).
# ---------------------------------------------------------------------


def _load_registry(registry_path: Path) -> list[dict]:
    data = json.loads(registry_path.read_text())
    return data["adapters"]


def _discover_and_build(registry_path: Path) -> list[tuple[str, ConformanceAdapter]]:
    built: list[tuple[str, ConformanceAdapter]] = []
    required_failures: list[str] = []
    for entry in _load_registry(registry_path):
        name = entry["name"]
        module_name = entry["module"]
        required = bool(entry.get("required", False))
        # `conformance-tests/conftest.py` gets this peer's own `src`
        # directory on `sys.path` for free, via pytest's own `pythonpath`
        # ini option (root `pyproject.toml`'s `[tool.pytest.ini_options]`)
        # -- this standalone script has no pytest session to do that for
        # it, so it adds the same directory itself, derived the same way
        # (`ROOT / <registry-supplied name> / "src"`) as the conformance
        # directory just below, never a hardcoded peer path.
        src_dir = str(ROOT / name / "src")
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)
        conformance_dir = str(ROOT / name / "conformance")
        if conformance_dir not in sys.path:
            sys.path.insert(0, conformance_dir)
        try:
            module = importlib.import_module(module_name)
            adapter_obj = module.build_adapter()
        except Exception as exc:  # noqa: BLE001 - report, mirrors conftest.py
            if required:
                required_failures.append(f"{name} ({module_name}): {exc!r}")
            continue
        if not isinstance(adapter_obj, ConformanceAdapter):
            message = f"{name} ({module_name}).build_adapter() did not return a ConformanceAdapter (got {type(adapter_obj)!r})"
            if required:
                required_failures.append(message)
            continue
        built.append((name, adapter_obj))
    if required_failures:
        for _name, _adapter in built:
            with contextlib.suppress(Exception):
                _adapter.close()
        raise RuntimeError(
            "required conformance adapter(s) failed to import or build:\n"
            + "\n".join(f"  - {f}" for f in required_failures)
        )
    return built


_HTTP_NAME_SUFFIX = "-http"
_SOCKET_NAME_SUFFIX = "-socket"

# Phase 10 WP-3 (design docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md
# D-12): the printed `transport=` label for each of `ConformanceAdapter.
# transport_kind`'s 3 declared values (`adapter.py` port v1.14). A fixed,
# 1:1 mapping -- never a re-derived guess -- so the label an adapter's
# OWN declaration resolves to never depends on this tool's own naming
# taste. `"in-process"`/`"asgi-inprocess"` are the SAME literal label
# text this tool printed before this revision (existing 4 plugs' own
# output is unchanged, byte-for-byte); `"socket"` is the one genuinely
# new label this revision adds (no currently-registered plug declares it
# yet -- WP-4 registers the first one).
_TRANSPORT_LABELS: dict[str, str] = {
    "in_process": "in-process",
    "asgi": "asgi-inprocess",
    "socket": "socket",
}

# Which registry-name suffix each declared `transport_kind` is expected
# to carry -- `None` means "no suffix at all" (the two in-process plugs).
_EXPECTED_NAME_SUFFIX: dict[str, "str | None"] = {
    "in_process": None,
    "asgi": _HTTP_NAME_SUFFIX,
    "socket": _SOCKET_NAME_SUFFIX,
}


def _classify_plug(plug_name: str, adapter_obj: ConformanceAdapter) -> tuple[str, str]:
    """Returns `(peer, transport)` for one registered plug.

    Phase 10 WP-3 rework (design D-12, monitor 裁定 2026-09-08,
    `OPERATING_CONDITIONS.md` section 1.7 item 52 -- "代理指標を使わな
    い"): this used to classify a plug by re-deriving its transport from
    the BUILT OBJECT'S OWN attribute shape (`hasattr(adapter_obj,
    "_loop")`/`"_client"`) combined with a name-suffix guess -- a proxy
    for the real, contract-independent property this tool actually cares
    about (design D-1 (A) 4's own `transport_kind` declaration). That
    proxy was already measured unsafe for a real socket plug (WP-5
    rework ruling item 4: a real-socket httpx client also sets `_loop`/
    `_client`, so attribute shape alone cannot distinguish `asgi` from
    `socket` at all). This revision reads `adapter_obj.transport_kind`
    directly instead -- the SAME attribute `test_c19_client_self_
    sufficiency.py`'s own real-dial branch and this adapter's own
    `test_socket_harness.py` self-test key off -- and still cross-checks
    it against the registry NAME's own suffix convention (never trusting
    either signal alone): a plug whose name and declaration disagree
    still raises `UnknownAdapterShape` (turned into a non-zero exit by
    `main()`) rather than guessing.

    - `"in_process"`: registry name has NEITHER a `-http` NOR a `-socket`
      suffix.
    - `"asgi"`: registry name ends in `-http`.
    - `"socket"`: registry name ends in `-socket`.

    A plug declaring a `transport_kind` outside this 3-word vocabulary
    (a typo, or a future 4th value this tool has not been extended for)
    also raises `UnknownAdapterShape` -- extend this function's own
    `_TRANSPORT_LABELS`/`_EXPECTED_NAME_SUFFIX` tables explicitly, do not
    widen either check into a fallback; see
    `tools/PERF_BASELINE_README.md`."""
    declared = getattr(adapter_obj, "transport_kind", None)
    label = _TRANSPORT_LABELS.get(declared)
    if label is None:
        raise UnknownAdapterShape(
            f"{plug_name}: transport_kind={declared!r} is not one of {sorted(_TRANSPORT_LABELS)} -- "
            "this tool refuses to guess a transport label for an undeclared or unrecognized value "
            "(see tools/PERF_BASELINE_README.md)"
        )
    expected_suffix = _EXPECTED_NAME_SUFFIX[declared]
    if expected_suffix is None:
        name_agrees = not (plug_name.endswith(_HTTP_NAME_SUFFIX) or plug_name.endswith(_SOCKET_NAME_SUFFIX))
        peer = plug_name
    else:
        name_agrees = plug_name.endswith(expected_suffix)
        peer = plug_name[: -len(expected_suffix)] if name_agrees else plug_name
    if not name_agrees:
        raise UnknownAdapterShape(
            f"{plug_name}: declares transport_kind={declared!r} but its registry name does not carry "
            f"the expected suffix ({expected_suffix!r}) -- these disagree, so this tool refuses to "
            "guess a peer/transport label for it (see tools/PERF_BASELINE_README.md)"
        )
    return peer, label


# ---------------------------------------------------------------------
# backend-call counting (design D-6 decision 2: wrap the backend/cell/
# connection object the plug itself constructs; never touch product code)
# ---------------------------------------------------------------------


class _CallCounter:
    __slots__ = ("count",)

    def __init__(self) -> None:
        self.count = 0


def _resolve_cell(adapter_obj: ConformanceAdapter, app_id: str) -> Any:
    """Locates the storage cell object backing `app_id`, trying every
    attribute shape this repository's own currently-registered platforms
    use (design D-6's own precedent, the MitateDB peer's
    `tests/test_postgres.py:595-607`, reaches into the equivalent private
    attribute directly). Tried in order, first match wins; never a
    peer-name literal -- these are internal attribute names, not
    plug/peer identifiers."""
    service = getattr(adapter_obj, "_service", None)
    if service is not None:
        cells = getattr(service, "_cells", None)
        if isinstance(cells, dict) and app_id in cells:
            return cells[app_id]
    control = getattr(adapter_obj, "_control", None)
    if control is not None:
        cells = getattr(control, "cells", None)
        if isinstance(cells, dict) and app_id in cells:
            return cells[app_id]
    cells = getattr(adapter_obj, "_cells", None)
    if isinstance(cells, dict) and app_id in cells:
        return cells[app_id]
    raise RuntimeError(
        f"{adapter_obj.name}: could not resolve a storage cell object for application {app_id!r} "
        "via any known attribute path (_service._cells / _control.cells / _cells)"
    )


def _resolve_backend_object(cell: Any) -> Any:
    """The object whose own methods represent 'the backend' for counting
    purposes: the cell itself when it directly implements the storage
    surface (the r2db peer's own `ApplicationCell`/`PostgresCell`), or
    the cell's own inner `_backend` when the cell is a thin wrapper
    around one (the MitateDB peer's own `ApplicationCell` always holds a
    `_backend`: `SQLiteBackend` or `PostgresBackend`)."""
    inner = getattr(cell, "_backend", None)
    return inner if inner is not None else cell


def _is_postgres_backed(backend_obj: Any) -> bool:
    """Structural, not name-based: true when the concrete object this run
    actually built lives in a module whose name says 'postgres' (`r2db_
    api.postgres.PostgresCell`, `mitatedb_api.backend_postgres.
    PostgresBackend`), false for the in-memory/SQLite reference
    implementations (`r2db_api.structured.ApplicationCell`, `mitatedb_
    api.backend_sqlite.SQLiteBackend`)."""
    return "postgres" in type(backend_obj).__module__.lower()


def _public_callable_names(obj: Any) -> list[str]:
    """Public METHODS only -- not merely 'public and callable' (`inspect.
    getattr_static` inspects the class-level descriptor without invoking
    it, so a `@property` returning something that happens itself to be
    callable, such as `SQLiteBackend.raw_connection` returning a raw
    `sqlite3.Connection` -- whose instances are themselves callable, a
    CPython implementation detail unrelated to this backend's own public
    surface -- is correctly excluded rather than mistaken for a method
    and setattr'd over (a `property` has no setter here, which would
    raise)."""
    names: list[str] = []
    for name in dir(obj):
        if name.startswith("_"):
            continue
        try:
            static_value = inspect.getattr_static(obj, name)
        except AttributeError:
            continue
        if isinstance(static_value, property) or not (
            inspect.isfunction(static_value) or inspect.ismethod(static_value)
        ):
            continue
        try:
            bound_value = getattr(obj, name)
        except Exception:  # noqa: BLE001 - a misbehaving accessor must not abort discovery
            continue
        if callable(bound_value):
            names.append(name)
    return names


@contextlib.contextmanager
def _wrap_all_public_methods(obj: Any, counter: _CallCounter) -> Iterator[None]:
    """In-memory/SQLite path (design D-6: 'backend メソッド'): counts one
    call per invocation of any public method the backend/cell object
    exposes. Instance-level attribute overrides only (never touches the
    class), restored unconditionally on exit."""
    names = _public_callable_names(obj)
    originals: dict[str, Callable] = {}
    for name in names:
        original = getattr(obj, name)
        originals[name] = original

        def _make(orig: Callable) -> Callable:
            def _wrapped(*args: Any, **kwargs: Any) -> Any:
                counter.count += 1
                return orig(*args, **kwargs)

            return _wrapped

        setattr(obj, name, _make(original))
    try:
        yield
    finally:
        for name in originals:
            with contextlib.suppress(AttributeError):
                delattr(obj, name)


@contextlib.contextmanager
def _count_psycopg_cursor_calls(counter: _CallCounter) -> Iterator[None]:
    """PostgreSQL path (design D-6: 'cursor の実行'): counts one call per
    real `psycopg.Cursor.execute`/`.executemany` call, process-wide but
    scoped tightly to this context manager's own lifetime and restored
    unconditionally on exit. Safe because this harness runs exactly one
    op loop at a time, sequentially, in a single thread -- never two
    PostgreSQL-backed measurement windows overlapping. `psycopg` is not a
    new dependency of this file: it is already imported (transitively, by
    whichever HTTP-plug adapter module is under measurement) by the time
    this is reached."""
    import psycopg

    real_execute = psycopg.Cursor.execute
    real_executemany = psycopg.Cursor.executemany

    def _counting_execute(self: Any, *args: Any, **kwargs: Any) -> Any:
        counter.count += 1
        return real_execute(self, *args, **kwargs)

    def _counting_executemany(self: Any, *args: Any, **kwargs: Any) -> Any:
        counter.count += 1
        return real_executemany(self, *args, **kwargs)

    psycopg.Cursor.execute = _counting_execute  # type: ignore[method-assign]
    psycopg.Cursor.executemany = _counting_executemany  # type: ignore[method-assign]
    try:
        yield
    finally:
        psycopg.Cursor.execute = real_execute  # type: ignore[method-assign]
        psycopg.Cursor.executemany = real_executemany  # type: ignore[method-assign]


@contextlib.contextmanager
def _backend_call_counter(cell: Any) -> Iterator[_CallCounter]:
    counter = _CallCounter()
    backend_obj = _resolve_backend_object(cell)
    if _is_postgres_backed(backend_obj):
        with _count_psycopg_cursor_calls(counter):
            yield counter
    else:
        with _wrap_all_public_methods(backend_obj, counter):
            yield counter


# ---------------------------------------------------------------------
# timing
# ---------------------------------------------------------------------


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    k = (len(sorted_values) - 1) * (pct / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_values[int(k)]
    return sorted_values[f] * (c - k) + sorted_values[c] * (k - f)


# ---------------------------------------------------------------------
# concurrency dispatch (Phase 10 WP-7, design D-8 (1)/(2)).
#
# A "sample" this tool measures is now a GROUP of `concurrency` requests
# fired together; `_run_concurrent` is the ONE place that ever calls
# `asyncio.gather` -- every group, at every `concurrency` value including
# 1, goes through it (WP-7 completion condition 2: no separate
# sequential branch for the singleton case). Real per-request overlap
# only actually occurs for a plug with a real event loop of its own
# (`adapter_obj._loop`/`_client`, i.e. `transport_kind` in
# {"asgi", "socket"}) -- an `in_process` plug has no async boundary
# anywhere in its own call chain to overlap on at all, so its own groups
# reduce to running their `concurrency` members one after another
# regardless of the value (documented, not a bug: see
# `tools/PERF_BASELINE_README.md`).
# ---------------------------------------------------------------------


def _run_concurrent(
    loop: "asyncio.AbstractEventLoop", groups: list[list[Callable[[], Any]]], *, counter: "_CallCounter | None" = None,
) -> tuple[list[float], list[float]]:
    """Runs each group of zero-arg coroutine factories via exactly ONE
    `asyncio.gather` call on `loop`, timing the GROUP's own wall-clock
    span (from just before the `gather` call to every member of it
    completing) -- never a per-member time, and never a sequential
    `await` of the group's own members one at a time (WP-7 completion
    condition 1). A group of size 1 walks this identical call (condition
    2).

    When `counter` is given, `calls[i]` is the raw `counter` delta
    observed strictly around group `i`'s own `gather` call -- exact and
    attributable to that group alone only when nothing else touches
    `counter` concurrently with it (always true for a singleton group,
    or for a group with no real async I/O to overlap with at all; see
    call sites in `_measure_op` for how each case is actually used).
    Without a `counter`, `calls` is a same-length list of zeros.
    """
    async def _gather_group(group: list[Callable[[], Any]]) -> None:
        # `asyncio.gather` is called from INSIDE a coroutine that is
        # itself already running on `loop` (via `run_until_complete`
        # below) -- never at module level before the loop is running --
        # so it always binds to the SAME `loop` this function was handed,
        # never an ambient "current" loop resolved some other way.
        await asyncio.gather(*(factory() for factory in group))

    durations: list[float] = []
    calls: list[float] = []
    for group in groups:
        before = counter.count if counter is not None else 0
        t0 = time.perf_counter()
        loop.run_until_complete(_gather_group(group))
        durations.append((time.perf_counter() - t0) * 1000.0)
        calls.append(float(counter.count - before) if counter is not None else 0.0)
    return durations, calls


def _rows_from_groups(durations: list[float], group_calls: list[float], concurrency: int) -> tuple[list[float], list[float]]:
    """`durations`/`group_calls` carry one entry per SAMPLE (a group of
    `concurrency` simultaneous requests). Returns `durations` unchanged
    and a same-length `calls` list holding the PER-REQUEST average
    (never the per-group raw total), so a printed row's `backend_calls`
    means the same thing at every `--concurrency` value: calls per ONE
    logical request, not per `concurrency` of them fired at once.

    At `concurrency == 1` each group already IS exactly one request, so
    `group_calls` is already an exact per-request value -- unchanged from
    the pre-WP-7 per-sample semantics `_run_self_check` relies on (WP-5
    rework ruling item 5). At `concurrency > 1`, a single group's own
    `group_calls[i]` cannot be safely divided among that group's own
    `concurrency` constituent requests -- they genuinely overlap in time
    by design, which is the entire point of this measurement -- so this
    instead spreads the RUN'S OWN total observed calls evenly across
    every sample: a documented relaxation of the per-sample self-check's
    precision for `concurrency > 1` only (see `_run_self_check`'s own
    docstring and `tools/PERF_BASELINE_README.md`)."""
    if concurrency == 1:
        return durations, list(group_calls)
    total = sum(group_calls)
    avg_per_request = (total / (len(durations) * concurrency)) if durations else 0.0
    return durations, [avg_per_request] * len(durations)


def _check_response(adapter_obj: "ConformanceAdapter", response: Any, request: Any) -> None:
    """The one correctness check this tool's own concurrent replay makes
    on a real response (below the level of `ConformanceAdapter._send`'s
    own `ConformanceDenial` machinery, which this tool deliberately does
    not reconstruct here -- see `_capture_one_request`'s own docstring):
    a non-2xx/3xx status means this run is not measuring the happy path
    it claims to, so it aborts loudly rather than silently timing a
    denial."""
    if response.status_code >= 400:
        raise RuntimeError(
            f"{adapter_obj.name}: concurrent replay got HTTP {response.status_code} for "
            f"{request.method} {request.url} -- perf_baseline measures the happy path only"
        )


def _capture_one_request(adapter_obj: "ConformanceAdapter", fn: Callable[[], None]) -> Any:
    """Calls `fn()` (one of `_measure_plug`'s own `_do_query`/`_do_mutate`
    /`_do_batch`/`_do_cross_entity` closures) exactly once, with `adapter_
    obj._client.send` temporarily swapped for a stub that raises `_
    CapturedRequest(request)` the instant it is reached INSTEAD of
    sending it, and returns that captured `httpx.Request` object.

    Every op this tool measures reaches `ConformanceAdapter._send` (r2db/
    MitateDB HTTP adapters, `conformance/conformance_adapter_*_http.py`)
    -- and therefore `self._client.send(...)` -- exactly once per call
    (`_query_request`/`_mutate_request`/`_cross_mutate` each make exactly
    one `self._send(...)` call), so this always raises before `fn()`
    would return normally. This is what makes `--concurrency K > 1`
    possible at all for a plug backed by a real `httpx.AsyncClient`: the
    adapter's own single, shared `self._loop.run_until_complete` call
    inside `_run` cannot itself hold more than one request in flight
    (design D-2, the SAME constraint documented on `hold_in_flight`'s own
    real-HTTP realization in those same adapter files) -- capturing the
    already-built `httpx.Request` FIRST and dispatching several of them
    together afterward, via `_run_concurrent`, is what sidesteps that
    single-call-at-a-time shape without touching the adapter's own
    source (WP-7 触らないファイル).

    This never touches adapter SOURCE: it swaps an INSTANCE attribute on
    the `httpx.AsyncClient` object the adapter itself already
    constructed, restored unconditionally in `finally` -- the same "wrap
    the object the plug itself built, never its class or its source"
    discipline `_wrap_all_public_methods`/`_count_psycopg_cursor_calls`
    (above) already use for backend-call counting.

    A `fn()` that returns normally without ever reaching `_client.send`
    would be a real bug in this tool's own op closures (every one of them
    is written to make exactly one such call) -- raising `RuntimeError`
    rather than returning `None` keeps that failure loud, not silent."""
    client = adapter_obj._client  # noqa: SLF001 -- see docstring
    original_send = client.send

    async def _stub_send(request: Any, *args: Any, **kwargs: Any) -> Any:
        raise _CapturedRequest(request)

    client.send = _stub_send
    try:
        fn()
    except _CapturedRequest as captured:
        return captured.request
    else:
        raise RuntimeError(
            f"{adapter_obj.name}: op closure returned without ever calling _client.send() -- "
            "cannot capture a request to replay concurrently"
        )
    finally:
        client.send = original_send


def _replay_factory(adapter_obj: "ConformanceAdapter", request: Any) -> Callable[[], Any]:
    """Builds the zero-arg coroutine factory `_run_concurrent` calls once
    per group member: sends the ALREADY-CAPTURED `request` for real, via
    the adapter's own (by now restored to original) `_client.send`, and
    applies `_check_response`. A fresh coroutine object is returned on
    every call (never a single, once-awaitable coroutine reused across
    groups)."""

    async def _send_one() -> None:
        response = await adapter_obj._client.send(request)  # noqa: SLF001 -- see _capture_one_request
        _check_response(adapter_obj, response, request)

    return _send_one


def _measure_op(
    fn: Callable[[], None], *, warmup: int, n: int, concurrency: int, counter: _CallCounter, adapter_obj: "ConformanceAdapter",
) -> tuple[list[float], list[float]]:
    """Measures one (plug, op): `n` samples, each a GROUP of `concurrency`
    simultaneous requests dispatched via `_run_concurrent`, preceded by
    `warmup` such groups (not timed, not counted). Returns `(durations_
    ms, calls)`, one entry per sample -- `n` of each, never the raw `--n`/
    `--warmup` CLI arguments echoed through (WP-5 rework ruling item 1,
    unchanged by WP-7: `len(durations_ms)` IS the `n=` a printed row
    carries).

    Two dispatch shapes, chosen by whether `adapter_obj` has a real event
    loop of its own (see this section's own module-level comment):
    `_capture_one_request`/`_replay_factory` (real `httpx.AsyncClient`
    plugs) or a trivial same-loop wrapper around `fn()` itself
    (`in_process` plugs, no real I/O to overlap regardless of
    `concurrency`)."""
    has_real_loop = getattr(adapter_obj, "_loop", None) is not None and getattr(adapter_obj, "_client", None) is not None
    if has_real_loop:
        warmup_requests = [_capture_one_request(adapter_obj, fn) for _ in range(warmup * concurrency)]
        warmup_groups = [
            [_replay_factory(adapter_obj, r) for r in warmup_requests[i : i + concurrency]]
            for i in range(0, len(warmup_requests), concurrency)
        ]
        _run_concurrent(adapter_obj._loop, warmup_groups)  # noqa: SLF001 -- discard timings/calls

        measured_requests = [_capture_one_request(adapter_obj, fn) for _ in range(n * concurrency)]
        measured_groups = [
            [_replay_factory(adapter_obj, r) for r in measured_requests[i : i + concurrency]]
            for i in range(0, len(measured_requests), concurrency)
        ]
        durations, group_calls = _run_concurrent(adapter_obj._loop, measured_groups, counter=counter)  # noqa: SLF001
    else:

        def _trivial_factory() -> Any:
            async def _one() -> None:
                fn()

            return _one()

        loop = asyncio.new_event_loop()
        try:
            warmup_groups = [[_trivial_factory for _ in range(concurrency)] for _ in range(warmup)]
            _run_concurrent(loop, warmup_groups)
            measured_groups = [[_trivial_factory for _ in range(concurrency)] for _ in range(n)]
            durations, group_calls = _run_concurrent(loop, measured_groups, counter=counter)
        finally:
            loop.close()
    return _rows_from_groups(durations, group_calls, concurrency)


def _row(
    peer: str, plug: str, transport: str, op: str, durations_ms: list[float], calls: list[float], concurrency: int,
) -> dict:
    """`n` is the ACTUAL number of samples measured
    (`len(durations_ms)`), never the raw `--n` CLI argument passed
    straight through -- WP-5 rework ruling item 1. A CLI-argument
    pass-through cannot detect a measurement change (e.g. warmup samples
    leaking into the measured set) that shifts the real sample count,
    because the printed `n=` would stay whatever `--n` said regardless of
    what was actually aggregated.

    `concurrency` (Phase 10 WP-7, design D-8/D-12) is the `--concurrency`
    value every sample this row summarizes was measured at -- see
    `_format_row`'s own docstring for where it lands on the printed
    line."""
    sorted_durations = sorted(durations_ms)
    avg_calls = (sum(calls) / len(calls)) if calls else 0.0
    return {
        "peer": peer,
        "plug": plug,
        "transport": transport,
        "op": op,
        "n": len(durations_ms),
        "p50_ms": _percentile(sorted_durations, 50),
        "p95_ms": _percentile(sorted_durations, 95),
        "backend_calls": avg_calls,
        "concurrency": concurrency,
    }


def _format_row(row: dict) -> str:
    """WP-7 completion condition 4: every column this function printed
    before WP-7 (`peer`/`plug`/`transport`/`op`/`n`/`p50_ms`/`p95_ms`/
    `backend_calls`) keeps its exact name, order, and `:.3f`/`:.2f`
    formatting -- `concurrency` is appended as a NEW, final column, never
    inserted between existing ones."""
    return (
        f"PERF peer={row['peer']} plug={row['plug']} transport={row['transport']} "
        f"op={row['op']} n={row['n']} p50_ms={row['p50_ms']:.3f} "
        f"p95_ms={row['p95_ms']:.3f} backend_calls={row['backend_calls']:.2f} "
        f"concurrency={row['concurrency']}"
    )


# ---------------------------------------------------------------------
# one plug's own full measurement
# ---------------------------------------------------------------------


def _measure_plug(
    name: str, adapter_obj: ConformanceAdapter, *, warmup: int, n: int, concurrency: int,
) -> list[dict]:
    peer, transport = _classify_plug(name, adapter_obj)
    app_id = fresh_identifier("perfbase")
    adapter_obj.provision_application(app_id)
    try:
        developer = adapter_obj.authenticate(adapter_obj.issue_credential(app_id, "developer"))
        entity = fresh_identifier("perfq")
        adapter_obj.create_entity(developer, entity, {"label": "text"})

        seed_runtime = adapter_obj.authenticate(adapter_obj.issue_credential(app_id, "runtime"))
        adapter_obj.insert(seed_runtime, entity, {"label": "perf-seed"})

        cell = _resolve_cell(adapter_obj, app_id)
        rows: list[dict] = []
        with _backend_call_counter(cell) as counter:
            # --- query ---
            query_runtime = adapter_obj.authenticate(adapter_obj.issue_credential(app_id, "runtime"))

            def _do_query() -> None:
                adapter_obj.select_eq(query_runtime, entity, ["label"], "label", "perf-seed")

            durations, calls = _measure_op(
                _do_query, warmup=warmup, n=n, concurrency=concurrency, counter=counter, adapter_obj=adapter_obj,
            )
            query_row = _row(peer, name, transport, "query", durations, calls, concurrency)
            rows.append(query_row)
            _run_self_check(name, calls)

            # --- mutate ---
            # WP-5 rework ruling item 2: every value `fresh_identifier`
            # would generate is materialized into a plain list BEFORE
            # `_measure_op` starts timing anything -- the measured closure
            # below only indexes into it. A generator expression handed
            # straight to `iter()` looks pre-built but is not: its body
            # (the `fresh_identifier()` call) still runs lazily on each
            # `next()`, i.e. inside the timed window, which is exactly the
            # defect this ruling item corrects.
            #
            # WP-7: sized `(warmup + n) * concurrency`, not `warmup + n` --
            # at `concurrency > 1` every one of the `warmup + n` SAMPLES is
            # itself a group of `concurrency` real, distinct requests (design
            # D-8 (1)'s own "(n + warmup) * concurrency" accounting, the same
            # arithmetic that rules out the pre-WP-7 `--n 200 --warmup 20`
            # default at `--concurrency 3`), each needing its own fresh value.
            mutate_runtime = adapter_obj.authenticate(adapter_obj.issue_credential(app_id, "runtime"))
            mutate_values = [fresh_identifier("perfmv") for _ in range((warmup + n) * concurrency)]
            mutate_values_iter = iter(mutate_values)

            def _do_mutate() -> None:
                adapter_obj.insert(mutate_runtime, entity, {"label": next(mutate_values_iter)})

            durations, calls = _measure_op(
                _do_mutate, warmup=warmup, n=n, concurrency=concurrency, counter=counter, adapter_obj=adapter_obj,
            )
            rows.append(_row(peer, name, transport, "mutate", durations, calls, concurrency))

            # --- batch (5 operations, design D-6 decision 1) ---
            batch_runtime = adapter_obj.authenticate(adapter_obj.issue_credential(app_id, "runtime"))
            # Pre-build every operation list OUTSIDE the timed window (audit
            # WP-5 finding: constructing the BatchOperation objects inside the
            # closure cost 2.4-4.7% of the in-process p50) -- the timed region
            # is the adapter call alone. WP-7: `(warmup + n) * concurrency`
            # entries, same reason as `mutate_values` above.
            batch_ops_per_call = [
                [
                    BatchOperation(operation="insert", values={"label": fresh_identifier("perfbv")})
                    for _ in range(_BATCH_OPS)
                ]
                for _ in range((warmup + n) * concurrency)
            ]
            batch_ops_iter = iter(batch_ops_per_call)

            def _do_batch() -> None:
                adapter_obj.attempt_batch_with_addresses(batch_runtime, entity, next(batch_ops_iter))

            durations, calls = _measure_op(
                _do_batch, warmup=warmup, n=n, concurrency=concurrency, counter=counter, adapter_obj=adapter_obj,
            )
            rows.append(_row(peer, name, transport, "batch", durations, calls, concurrency))

            # --- cross_entity (MitateDB 2 plug only; design D-6 decision 1) ---
            capabilities = adapter_obj.capability_document().get("capabilities", {})
            cross_status = capabilities.get("cross_entity_mutation", {}).get("status", "unavailable")
            if cross_status != "unavailable":
                entity_b = fresh_identifier("perfx")
                adapter_obj.create_entity(developer, entity_b, {"label": "text"})
                cross_runtime = adapter_obj.authenticate(adapter_obj.issue_credential(app_id, "runtime"))
                cross_ops_per_call = [
                    [
                        ScopedBatchOperation(operation="insert", entity=entity, values={"label": fresh_identifier("perfcv")}),
                        ScopedBatchOperation(operation="insert", entity=entity_b, values={"label": fresh_identifier("perfcv")}),
                    ]
                    for _ in range((warmup + n) * concurrency)
                ]
                cross_ops_iter = iter(cross_ops_per_call)

                def _do_cross_entity() -> None:
                    adapter_obj.attempt_cross_entity_batch(cross_runtime, next(cross_ops_iter))

                durations, calls = _measure_op(
                    _do_cross_entity, warmup=warmup, n=n, concurrency=concurrency, counter=counter, adapter_obj=adapter_obj,
                )
                rows.append(_row(peer, name, transport, "cross_entity", durations, calls, concurrency))
        return rows
    finally:
        with contextlib.suppress(Exception):
            adapter_obj.deprovision_application(app_id)


def _run_self_check(plug_name: str, query_calls: list[float]) -> None:
    """Work order WP-5 completion condition 1, per WP-5 rework ruling item
    5: the requirement's own words are 'query 1回に対して backend_calls
    >= 1' -- EVERY individual `query` sample's own observed call count,
    not the N-sample average that used to be checked here. An average
    can be >= 1 while up to N-1 of the individual samples were actually
    0 (e.g. 199 zero-call samples and 1 real one out of N=200 still
    averages to 1.00); checking `min(query_calls) >= 1` cannot be fooled
    that way. This is the ONLY judgement this tool makes (P-8: no
    thresholds) -- it is still non-emptiness only, just per-sample rather
    than on the aggregate."""
    lowest = min(query_calls) if query_calls else 0
    if lowest < 1:
        raise SelfCheckFailure(
            f"{plug_name}: self-check failed -- query backend_calls min={lowest} < 1 over {len(query_calls)} samples "
            "(at least one query request the counting proxy observed made zero backend calls; "
            "it is not wired to anything real for that sample)"
        )


# ---------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------


def _is_worktree_dirty() -> bool:
    """True when `git status --porcelain` prints anything at all (tracked
    changes, staged changes, or untracked files) for this working tree.
    Used only to decide whether to append `-dirty` to the `commit=` field
    (WP-5 rework ruling item 6) -- never raises past this function, a
    missing/unusable git binary is treated as "cannot tell, assume not
    dirty" rather than aborting the run."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=ROOT, capture_output=True, text=True, timeout=10, check=True,
        )
        return bool(result.stdout.strip())
    except Exception:  # noqa: BLE001 - a missing git binary must not crash the harness
        return False


def _git_short_sha() -> str:
    """The `commit=` field. WP-5 rework ruling item 6: a `-dirty` suffix
    is appended when the working tree has uncommitted changes (tracked or
    untracked) -- otherwise a completion-gate audit comparing `commit=`
    against the gate-time branch head (work order WP-5 completion
    condition 7) cannot tell a clean gate-time run apart from one taken
    against a dirty tree that happens to share the same HEAD sha."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT, capture_output=True, text=True, timeout=10, check=True,
        )
        sha = result.stdout.strip()
    except Exception:  # noqa: BLE001 - a missing git binary must not crash the harness
        return "unknown"
    if not sha:
        return "unknown"
    return f"{sha}-dirty" if _is_worktree_dirty() else sha


def _perfrun_line() -> str:
    uname = platform.uname()
    host = f"{uname.system}/{uname.machine}"
    py = platform.python_version()
    date = datetime.date.today().isoformat()
    commit = _git_short_sha()
    return f"PERFRUN host={host} python={py} commit={commit} date={date}"


def _build_parser() -> argparse.ArgumentParser:
    """Split out of `main()` so `tools/tests/test_perf_baseline.py` can
    assert the default `--n`/`--warmup` values (WP-7 completion condition
    3) without running the tool end-to-end against the real registry."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    # WP-7 (design D-8 (1)): lowered from the pre-Phase-10 200/20 default --
    # at `--concurrency 3`, `(n + warmup) * concurrency` real requests land
    # on ONE credential; 200/20 would put that at 660, past the shared
    # surface's default `requests_per_minute` bound of 600
    # (`r2db-api/src/r2db_api/limits.py:18`; the effective bound in play is
    # the shared surface's own default `concurrency=32` at `:17`, not any
    # isolated-profile value). 100/10 stays at 330, safely under it.
    parser.add_argument("--n", type=int, default=100, help="measured samples per (plug, op) (default: 100)")
    parser.add_argument("--warmup", type=int, default=10, help="warmup samples per (plug, op), not measured (default: 10)")
    parser.add_argument(
        "--concurrency", type=int, default=1,
        help=(
            "requests fired together (via asyncio.gather, on the plug's own event loop) per measured "
            "sample; K=1 (default) and K>1 walk the identical dispatch path (design D-8 (1)/(2), WP-7)"
        ),
    )
    parser.add_argument(
        "--registry", type=Path, default=REGISTRY_PATH,
        help="override registry.json path (scratchpad testing only -- conformance-tests/registry.json itself is never written by this tool)",
    )
    return parser


def _run(args: argparse.Namespace) -> int:
    built = _discover_and_build(args.registry)
    exit_code = 0
    try:
        for name, adapter_obj in built:
            try:
                for row in _measure_plug(name, adapter_obj, warmup=args.warmup, n=args.n, concurrency=args.concurrency):
                    print(_format_row(row))
            except (SelfCheckFailure, UnknownAdapterShape) as exc:
                print(f"perf_baseline: {exc}", file=sys.stderr)
                exit_code = 1
    finally:
        for _name, adapter_obj in built:
            with contextlib.suppress(Exception):
                adapter_obj.close()
    return exit_code


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.concurrency < 1:
        parser.error("--concurrency must be >= 1")

    print(_perfrun_line())

    stage = "lock"
    try:
        with dsa_testpg.suite_lock(exclusive=True, wait=dsa_testpg.DEFAULT_LOCK_WAIT):
            stage = "cluster"
            with dsa_testpg.cluster() as c:
                stage = "run"
                cluster_env = c.env()
                restore_names = set(cluster_env) | {"PGPASSWORD"}
                saved_env = {name: os.environ.get(name) for name in restore_names}  # None means the name was absent before
                try:
                    os.environ.update(cluster_env)
                    os.environ.pop("PGPASSWORD", None)
                    return _run(args)
                finally:
                    for name, value in saved_env.items():  # put the caller's own environment back, always
                        if value is None:
                            os.environ.pop(name, None)
                        else:
                            os.environ[name] = value
    except dsa_testpg.TestPgError as exc:
        print(f"perf_baseline: {exc}", file=sys.stderr)
        return REFUSED if stage == "lock" else 1


if __name__ == "__main__":
    raise SystemExit(main())
