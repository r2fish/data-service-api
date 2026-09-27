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
import multiprocessing
import os
import platform
import queue
import resource
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Iterator

ROOT = Path(__file__).resolve().parents[1]
CONFORMANCE_TESTS_DIR = ROOT / "conformance-tests"
REGISTRY_PATH = CONFORMANCE_TESTS_DIR / "registry.json"
TESTPG_DIR = ROOT / "tools" / "testpg"
# This file's OWN directory -- on `sys.path` unconditionally
# (never only when run as `__main__`), so a `--real-server` child process
# spawned via `_REAL_SERVER_MP_CONTEXT` (`forkserver`, below) can `import
# perf_baseline` fresh and find THIS SAME file even when a test harness
# loaded it under a file-based module alias rather than running it as a
# script.
_TOOLS_DIR = Path(__file__).resolve().parent

if str(CONFORMANCE_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(CONFORMANCE_TESTS_DIR))
if str(TESTPG_DIR) not in sys.path:
    sys.path.insert(0, str(TESTPG_DIR))
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

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

# R-80 (WO §1.2 D-1, designレビュー1のH-1): the `ROUNDTRIP` poll's own
# fixed timing -- `pg_stat_clear_snapshot()` then a minimum 12s wait
# before ANY confirmation is even considered (a flat window was measured
# unstable for less, WO §1.3 (5)/(5b)), 1s between reads thereafter, and
# a 30s ceiling past which the last-seen value is printed with `stale=1`
# rather than blocked on forever. Never exposed as a CLI flag (WO §2.1
# only asks for `--roundtrip`; these three stay fixed).
_ROUNDTRIP_MIN_WAIT_S = 12.0
_ROUNDTRIP_POLL_INTERVAL_S = 1.0
_ROUNDTRIP_MAX_WAIT_S = 30.0


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


class RealServerMeasurementFailure(RuntimeError):
    """Work order `docs/work-orders/WORK_ORDER_R101_SERIALIZATION_ATTRIBUTION_V1.md` §7.3 D-15: raised anywhere along `--real-server`'s
    own setup (resolving this deployment's own `application_id`, issuing
    a developer credential, creating the measurement entity, seeding its
    one row, the K=1 sanity query) or measurement (any query response
    other than 200, condition 143) path. `_run_real_server` catches only
    this, prints it, and returns a non-zero exit WITHOUT ever printing a
    `REALPERF`/`REALCPU` line -- the two lines are printed together, from
    one return value, or not at all."""


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


def _resolve_app_db_and_matcher(cell: Any, app_id: str) -> "tuple[str | None, Callable[[dict], bool]]":
    """R-80 (WO §1.2 D-2, §1.3 (8)): resolves the application database
    NAME for `ROUNDTRIP`'s `db=app` row, and a matching function that
    decides -- given one connection dict `<adapter>.prepared_stats()`
    returned -- whether that connection's own probe `commit()` belongs to
    THIS application (WO §1.2 D-1's own "probe が実際に走った接続の本数"
    correction, 設計レビュー1のM-4's own derivation rule). Two forms,
    tried in order, never a peer-name literal (mirrors `_resolve_cell`'s
    own precedent immediately above in this file):

    - **r2db form**: `cell._runtime_dsn` (`r2db_api.postgres.PostgresCell`)
      is a real DSN string, parsed with `psycopg.conninfo.conninfo_to_dict`
      for `dbname` (WO §1.3 (8)'s own literal instruction). r2db's own
      `label` carries `<application_id>/<role>@<pid>`
      (`SharedPoolManager.prepared_stats`) -- the matcher is a `<app_id>/`
      prefix check, since a pool's own idle-connection count varies and
      cannot be predicted ahead of a probe.
    - **MitateDB form**: the resolved backend object's own `_runtime`
      (`mitatedb_api.backend_postgres.PostgresBackend`) has a public
      `.info.dbname` (psycopg's own public `ConnectionInfo`, never a
      private psycopg attribute -- WO §1.1 (e)). Unlike r2db, MitateDB
      always holds exactly 2 persistent connections per cell (`_runtime`/
      `_developer`, `backend_postgres.py`:358) -- their own `.info.
      backend_pid` (also public, cached client-side, no extra round trip)
      is read directly to build the exact 2 labels (`runtime@<pid>`/
      `developer@<pid>`) THIS cell's own backend would produce, so a
      capability-probe application's own cell (a second, unrelated
      application `capability_document()` may have provisioned, WO §1.3
      (8)'s own "cross_entity が作る 2 つ目の application") never gets
      counted here even though the adapter's own `prepared_stats()`
      aggregates every open cell.

    Returns `(None, <a matcher that always returns False>)` when neither
    form resolves -- never raises (completion condition 12b)."""
    runtime_dsn = getattr(cell, "_runtime_dsn", None)
    if runtime_dsn is not None:
        from psycopg.conninfo import conninfo_to_dict

        app_db = conninfo_to_dict(runtime_dsn).get("dbname")
        prefix = f"{app_id}/"
        return app_db, (lambda stats, _prefix=prefix: stats.get("label", "").startswith(_prefix))
    backend = _resolve_backend_object(cell)
    runtime_conn = getattr(backend, "_runtime", None)
    info = getattr(runtime_conn, "info", None) if runtime_conn is not None else None
    if info is not None:
        app_db = info.dbname
        own_labels: set[str] = set()
        for role_name in ("runtime", "developer"):
            conn = getattr(backend, f"_{role_name}", None)
            if conn is not None:
                own_labels.add(f"{role_name}@{conn.info.backend_pid}")
        frozen = frozenset(own_labels)
        return app_db, (lambda stats, _labels=frozen: stats.get("label") in _labels)
    return None, (lambda stats: False)


def _resolve_platform_db(adapter_obj: Any) -> "str | None":
    """R-80 (WO §1.2 D-2, §1.3 (8)): the platform database NAME for
    `ROUNDTRIP`'s `db=platform` row -- both http plugs' own `_Platform.
    platform_db` (`conformance_adapter_r2db_http.py`/`conformance_adapter_
    mitatedb_http.py`), the socket plugs inheriting it unchanged. `None`
    when the adapter carries no `_platform` at all (completion condition
    12b's own "どちらの形でも解決できない")."""
    platform = getattr(adapter_obj, "_platform", None)
    return getattr(platform, "platform_db", None) if platform is not None else None


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


def _capture_dbtime_pre(adapter_obj: Any) -> "dict | None":
    """One PRE snapshot, taken by `_measure_op` right after warmup and
    right before the measured `_run_concurrent` call, on both branches.
    `None` when `adapter_obj` has no `prepared_stats` (every plug this
    tool does not add DBTIME to -- mirrors `_emit_prepared_rows`'s own
    identical skip): no `prepared_stats()`/`platform_db_time_stats()`
    call is attempted at all in that case. Otherwise this is the ONE
    `prepared_stats()` call this function itself makes; the POST half is
    a separate, later call from `_emit_measurement_rows` (never this
    function) -- together exactly 2 per op without `--roundtrip`, 3 with
    it (`_roundtrip_pre_probe`'s own PRE call is the third, taken before
    this one, in `_measure_op_and_emit`)."""
    prepared_stats = getattr(adapter_obj, "prepared_stats", None)
    if prepared_stats is None:
        return None
    conn_stats = prepared_stats()
    platform_db_time_stats = getattr(adapter_obj, "platform_db_time_stats", None)
    platform_stats = platform_db_time_stats() if platform_db_time_stats is not None else None
    return {"conn_stats": conn_stats, "platform_stats": platform_stats}


def _measure_op(
    fn: Callable[[], None], *, warmup: int, n: int, concurrency: int, counter: _CallCounter, adapter_obj: "ConformanceAdapter",
) -> tuple[list[float], list[float], dict]:
    """Measures one (plug, op): `n` samples, each a GROUP of `concurrency`
    simultaneous requests dispatched via `_run_concurrent`, preceded by
    `warmup` such groups (not timed, not counted). Returns `(durations_
    ms, calls, measured)`, `durations_ms`/`calls` one entry per sample --
    `n` of each, never the raw `--n`/`--warmup` CLI arguments echoed
    through (WP-5 rework ruling item 1, unchanged by WP-7: `len(durations_
    ms)` IS the `n=` a printed row carries).

    `measured` is a plain dict -- `wall_ms` (the
    sum of the MEASURED group durations only, never warmup's), `cpu_
    total_ms`/`cpu_main_ms` (`resource.getrusage(RUSAGE_SELF)`'s own
    `ru_utime + ru_stime` and `time.thread_time()`, each a difference
    taken strictly around the measured `_run_concurrent` call below, never
    warmup's), and `dbtime_pre` (`_capture_dbtime_pre`'s own return value,
    taken at that same boundary: after warmup, before measured). Both
    reads are taken on THIS process/thread regardless of which branch
    runs below -- the real-loop branch's own `adapter_obj._loop.run_
    until_complete` and the trivial-loop branch's own `asyncio.new_event_
    loop()` both still execute on the SAME OS thread this function itself
    runs on.

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

        dbtime_pre = _capture_dbtime_pre(adapter_obj)

        measured_requests = [_capture_one_request(adapter_obj, fn) for _ in range(n * concurrency)]
        measured_groups = [
            [_replay_factory(adapter_obj, r) for r in measured_requests[i : i + concurrency]]
            for i in range(0, len(measured_requests), concurrency)
        ]
        # CPU reads start HERE, after every measured request's own capture
        # (`_capture_one_request`, main-thread work building the request
        # object) has already happened -- never before it: a capture is
        # not part of the measured window, so its own CPU must not land in
        # `cpu_total_ms`/`cpu_main_ms` either.
        cpu_before = resource.getrusage(resource.RUSAGE_SELF)
        thread_before = time.thread_time()
        durations, group_calls = _run_concurrent(adapter_obj._loop, measured_groups, counter=counter)  # noqa: SLF001

        thread_after = time.thread_time()
        cpu_after = resource.getrusage(resource.RUSAGE_SELF)
    else:

        def _trivial_factory() -> Any:
            async def _one() -> None:
                fn()

            return _one()

        loop = asyncio.new_event_loop()
        try:
            warmup_groups = [[_trivial_factory for _ in range(concurrency)] for _ in range(warmup)]
            _run_concurrent(loop, warmup_groups)

            dbtime_pre = _capture_dbtime_pre(adapter_obj)

            measured_groups = [[_trivial_factory for _ in range(concurrency)] for _ in range(n)]
            # Same boundary as the real-loop branch above (CPU reads right
            # before the measured `_run_concurrent` call, after the
            # measured groups are already built) -- an in_process plug's
            # own group construction is trivial (bare closure references),
            # so both branches read CPU at the same boundary, keeping
            # their own shapes aligned.
            cpu_before = resource.getrusage(resource.RUSAGE_SELF)
            thread_before = time.thread_time()
            durations, group_calls = _run_concurrent(loop, measured_groups, counter=counter)

            thread_after = time.thread_time()
            cpu_after = resource.getrusage(resource.RUSAGE_SELF)
        finally:
            loop.close()
    rows_durations, rows_calls = _rows_from_groups(durations, group_calls, concurrency)
    cpu_total_ms = ((cpu_after.ru_utime + cpu_after.ru_stime) - (cpu_before.ru_utime + cpu_before.ru_stime)) * 1000.0
    cpu_main_ms = (thread_after - thread_before) * 1000.0
    measured = {
        "wall_ms": sum(durations),
        "cpu_total_ms": cpu_total_ms,
        "cpu_main_ms": cpu_main_ms,
        "dbtime_pre": dbtime_pre,
    }
    return rows_durations, rows_calls, measured


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


def _format_cpu_row(peer: str, plug: str, op: str, m: dict) -> str:
    """One `CPU` line per (plug, op) -- always the FIRST line of that op's
    own block (before `POOL`/`DBTIME`/`PREPARED`/`ROUNDTRIP`). `m` is the
    `measurement` dict `_measure_op_and_emit` builds: `concurrency`,
    `thread_limit` (already resolved to the literal string `"default"`
    when the plug's own `perf_thread_limit()` is absent or returns
    `None`), `requests` (measured requests only, `n * concurrency`),
    `wall_ms` (the measured group durations' own sum), `cpu_total_ms`/
    `cpu_main_ms` (`resource.getrusage`/`time.thread_time` differences
    around that same measured window). `cpu_other_ms` is computed here,
    not stored in `m`: `cpu_total_ms - cpu_main_ms`, the CPU this process
    spent OUTSIDE the calling thread (anyio worker threads, or a socket
    plug's own uvicorn thread)."""
    cpu_other_ms = m["cpu_total_ms"] - m["cpu_main_ms"]
    return (
        f"CPU peer={peer} plug={plug} op={op} concurrency={m['concurrency']} "
        f"thread_limit={m['thread_limit']} requests={m['requests']} "
        f"wall_ms={m['wall_ms']:.3f} cpu_total_ms={m['cpu_total_ms']:.3f} "
        f"cpu_main_ms={m['cpu_main_ms']:.3f} cpu_other_ms={cpu_other_ms:.3f}"
    )


def _format_pool_row(peer: str, plug: str, op: str, key: str, stats: dict) -> str:
    """R-78 (D-2): one `POOL` line for one entry of a plug's own `pool_
    stats()`. Two shapes, chosen by which keys `stats` carries -- never by
    `peer`/`plug` name, so a future third pool/lock shape is refused
    loudly (`KeyError`) rather than silently misprinted:

    - A ROLE row (`stats` has `lock_acquire_count` absent, `acquire_count`/
      `size`/`in_use_peak` present -- `r2db_api.postgres._RolePool.stats()`'s
      own six keys): `role=<key> size=<n> acquire=<n> waits=<n> wait_
      total_ms=<x.xxx> wait_max_ms=<x.xxx> in_use_peak=<n>`.
    - A LOCK row (`stats` has `lock_acquire_count` -- `mitatedb_api.cell.
      _CountingRLock.stats()`'s own four keys, no pool `size`/`in_use_peak`
      concept for a mutex): `lock=<key> acquire=<n> waits=<n> wait_total_
      ms=<x.xxx> wait_max_ms=<x.xxx>`."""
    if "lock_acquire_count" in stats:
        return (
            f"POOL peer={peer} plug={plug} op={op} lock={key} "
            f"acquire={stats['lock_acquire_count']} waits={stats['wait_count']} "
            f"wait_total_ms={stats['wait_total_ms']:.3f} wait_max_ms={stats['wait_max_ms']:.3f}"
        )
    return (
        f"POOL peer={peer} plug={plug} op={op} role={key} size={stats['size']} "
        f"acquire={stats['acquire_count']} waits={stats['wait_count']} "
        f"wait_total_ms={stats['wait_total_ms']:.3f} wait_max_ms={stats['wait_max_ms']:.3f} "
        f"in_use_peak={stats['in_use_peak']}"
    )


def _emit_pool_rows(peer: str, plug: str, op: str, adapter_obj: Any) -> None:
    """R-78 (D-2): print one `POOL` line per entry `adapter_obj.pool_
    stats()` returns, called once per (plug, op) from inside `_measure_
    plug` itself, as a side effect -- NOT interleaved with `PERF` lines:
    `_measure_plug` returns its `PERF` row dicts to `_run`'s own loop,
    which prints them only after `_measure_plug` (and every `_emit_pool_
    rows` call inside it) has already returned, so every `POOL` line for a
    given plug prints as one block BEFORE that plug's own `PERF` lines,
    never interleaved with them one (plug, op) at a time. Called
    unconditionally, for every transport (monitor 裁定 2026-09-23: a
    socket-transport plug shares the same in-process cell/pool object as
    its `-http` counterpart -- see `tools/PERF_BASELINE_README.md` -- so
    there is no transport this should ever skip). Adapters with no `pool_
    stats` method (every plug this WP does not touch) are silently
    skipped, exactly like this tool already skips the MitateDB `cross_
    entity` op for plugs without that capability."""
    pool_stats = getattr(adapter_obj, "pool_stats", None)
    if pool_stats is None:
        return
    for key, stats in pool_stats().items():
        print(_format_pool_row(peer, plug, op, key, stats))


def _format_dbtime_app_row(
    peer: str, plug: str, op: str, concurrency: int, requests: int, conns: int, gone: int, db_calls: int, txns: int, db_wall_ms: float,
) -> str:
    """One `DBTIME ... scope=app` line: the application-database round
    trips a measured window's own connections spent, from the PRE/POST
    difference of `prepared_stats()` (`db_wall_ms`/`txn_count`, matched by
    connection `label`)."""
    return (
        f"DBTIME peer={peer} plug={plug} op={op} concurrency={concurrency} scope=app "
        f"conns={conns} gone={gone} db_calls={db_calls} txns={txns} "
        f"db_wall_ms={db_wall_ms:.3f} db_wall_ms_per_req={_per_request(db_wall_ms, requests):.3f}"
    )


def _format_dbtime_platform_row(
    peer: str, plug: str, op: str, concurrency: int, requests: int,
    sessions: int, connect_wall_ms: float, db_calls: int, txns: int, db_wall_ms: float,
) -> str:
    """One `DBTIME ... scope=platform` line: the platform-side (credential
    store / durable audit sink) round trips, from the PRE/POST difference
    of `platform_db_time_stats()`. `db_calls` is the PRE/POST delta of the
    platform accessor's own `execute_count + executemany_count` sum (the
    same pair `scope=app` diffs per connection, folded here across every
    platform-side connection instead). `db_wall_ms_per_req` divides by
    `db_wall_ms + connect_wall_ms`, folding the connect cost into the same
    per-request denominator `scope=app` uses for its own round-trip-only
    wall time."""
    return (
        f"DBTIME peer={peer} plug={plug} op={op} concurrency={concurrency} scope=platform "
        f"sessions={sessions} connect_wall_ms={connect_wall_ms:.3f} db_calls={db_calls} txns={txns} "
        f"db_wall_ms={db_wall_ms:.3f} db_wall_ms_per_req={_per_request(db_wall_ms + connect_wall_ms, requests):.3f}"
    )


def _emit_dbtime_rows(
    peer: str, plug: str, op: str, measurement: dict, post_conn_stats: "list[dict]", post_platform_stats: "dict | None",
) -> None:
    """Prints `DBTIME scope=app` (always, when reached at all -- see
    `_emit_measurement_rows`'s own `prepared_stats` gate) and `DBTIME
    scope=platform` (only when `post_platform_stats` is not `None`, i.e.
    `adapter_obj` also has `platform_db_time_stats`). `scope=app`'s own
    `conns=`/`gone=`/`db_calls=`/`txns=`/`db_wall_ms=` are all PRE/POST
    differences matched by connection `label` -- a label present only in
    the POST snapshot (a connection opened during the measured window)
    treats its own PRE value as 0 (never carried over from a different
    label); a label present only in the PRE snapshot (a connection closed
    during the window) counts toward `gone=` and contributes nothing to
    the sums."""
    dbtime_pre = measurement["dbtime_pre"]
    pre_conn_stats = (dbtime_pre or {}).get("conn_stats") or []
    pre_by_label = {c["label"]: c for c in pre_conn_stats}
    post_labels = {c["label"] for c in post_conn_stats}
    gone = sum(1 for label in pre_by_label if label not in post_labels)
    db_calls = 0
    txns = 0
    db_wall_ms = 0.0
    for c in post_conn_stats:
        pre = pre_by_label.get(c["label"])
        pre_calls = (pre["execute_count"] + pre["executemany_count"]) if pre is not None else 0
        db_calls += (c["execute_count"] + c["executemany_count"]) - pre_calls
        # `.get(..., 0/0.0)`, not `[...]`: a stub `prepared_stats()` result
        # (any `tools/tests/test_perf_baseline.py` fixture that omits
        # `db_wall_ms`/`txn_count`) carries neither key -- reads as 0/0.0
        # rather than raising `KeyError`, exactly like a fresh connection
        # with no traffic yet would.
        txns += c.get("txn_count", 0) - (pre.get("txn_count", 0) if pre is not None else 0)
        db_wall_ms += c.get("db_wall_ms", 0.0) - (pre.get("db_wall_ms", 0.0) if pre is not None else 0.0)
    print(_format_dbtime_app_row(
        peer, plug, op, measurement["concurrency"], measurement["requests"], len(post_conn_stats), gone, db_calls, txns, db_wall_ms,
    ))
    if post_platform_stats is not None:
        pre_platform = (dbtime_pre or {}).get("platform_stats") or {
            "sessions": 0, "connect_wall_ms": 0.0, "db_wall_ms": 0.0, "txn_count": 0, "db_calls": 0,
        }
        sessions = post_platform_stats["sessions"] - pre_platform["sessions"]
        connect_wall_ms = post_platform_stats["connect_wall_ms"] - pre_platform["connect_wall_ms"]
        platform_txns = post_platform_stats["txn_count"] - pre_platform["txn_count"]
        platform_db_wall_ms = post_platform_stats["db_wall_ms"] - pre_platform["db_wall_ms"]
        platform_db_calls = post_platform_stats.get("db_calls", 0) - pre_platform.get("db_calls", 0)
        print(_format_dbtime_platform_row(
            peer, plug, op, measurement["concurrency"], measurement["requests"],
            sessions, connect_wall_ms, platform_db_calls, platform_txns, platform_db_wall_ms,
        ))


def _format_prepared_row(peer: str, plug: str, op: str, conn_stats: dict) -> str:
    """R-79 (WO §1.2 D-3): one `PREPARED` line for one connection-shaped
    dict `<adapter>.prepared_stats()` returns (11 keys, WO §1.2 D-2).
    Column names are `executes=`/`executemany=` -- never `statements=`,
    which would collide with two different meanings ("statements
    executed" vs. "statements currently prepared", design review 1 M-7).
    `share` is `prepared_execs / executes`, printed `0.000`-formatted,
    `0.000` when `executes == 0` (never a `ZeroDivisionError`) -- a LOWER
    BOUND on how much of this connection's traffic actually landed on a
    prepared statement (WO §1.2 D-3: statements psycopg's own rollback-
    triggered `DEALLOCATE ALL` already cleared are not counted here, and
    the denominator also includes statements that can never themselves
    become prepared -- `SET LOCAL`, DDL, `prepare=False` reads -- so
    `share` structurally never reaches `1.000`; design review 1 M-8).
    `transaction_status`/`probed`/`error` are dict keys, never columns on
    this line (WO §1.2 D-3's own explicit carve-out)."""
    executes = conn_stats["execute_count"]
    share = (conn_stats["prepared_execs"] / executes) if executes else 0.0
    return (
        f"PREPARED peer={peer} plug={plug} op={op} conn={conn_stats['label']} "
        f"executes={executes} executemany={conn_stats['executemany_count']} "
        f"prepared={conn_stats['prepared']} prepared_execs={conn_stats['prepared_execs']} "
        f"share={share:.3f}"
    )


def _format_prepstmt_row(peer: str, plug: str, op: str, conn_label: str, stmt: dict) -> str:
    """R-79 (WO §1.2 D-3): one `PREPSTMT` line per prepared statement a
    connection's own `prepared_statements` list carries (only printed
    when `--prepared-detail` is given). `stmt=` collapses every run of
    whitespace in the statement's own first-80-characters text to a
    single space (WO §1.2 D-3's own "空白を 1 つに畳む") -- the dict's own
    `statement` value (from `psycopg_counting.probe_prepared_statements`)
    is already truncated to 80 characters; this only normalizes
    whitespace, it does not re-truncate."""
    collapsed = " ".join(stmt["statement"].split())
    return (
        f"PREPSTMT peer={peer} plug={plug} op={op} conn={conn_label} "
        f"name={stmt['name']} generic={stmt['generic_plans']} custom={stmt['custom_plans']} "
        f"stmt={collapsed}"
    )


def _emit_prepared_rows(
    peer: str, plug: str, op: str, adapter_obj: Any, *, detail: bool, conn_stats: "list[dict] | None" = None,
) -> "list[dict] | None":
    """R-79 (WO §1.2 D-3): print one `PREPARED` line per connection `adapter_
    obj.prepared_stats()` returns (skipped entirely, no exception, for a
    plug with no such method -- every plug this WP does not touch, mirrors
    `_emit_pool_rows` immediately above), called once per (plug, op) from
    inside `_measure_plug`, AFTER that (plug, op)'s own `_emit_pool_rows`
    call -- WO §1.2 D-3's own "same op の POOL 行の後に置く". Like `_emit_
    pool_rows`, this runs unconditionally for every transport: a socket-
    transport plug shares the same in-process cell/pool object as its
    `-http` counterpart, so there is no transport this should ever skip
    (completion condition 20). `PREPSTMT` lines (one per prepared
    statement on a connection) print only when `detail` is true
    (`--prepared-detail`, completion condition 19) -- never otherwise.

    R-80 (WO §1.2 D-1, §2.1's own "prepared_stats() の戻り値を `_emit_
    prepared_rows` と新しい emit で共有する"): returns the exact list
    `prepared_stats()` produced (or `None` when the plug has none) instead
    of discarding it -- the ONE probe call this makes is reused by `_emit_
    measurement_rows`' own `ROUNDTRIP` `conn=` rows below, so a `--roundtrip`
    run still calls `prepared_stats()` only once per op on this, the POST
    side (completion condition 3).

    `conn_stats`, when given (not `None`), is used AS-IS instead of
    calling `adapter_obj.prepared_stats()` again -- lets `_emit_
    measurement_rows` share the ONE POST call across a `DBTIME scope=app`
    line and these `PREPARED` lines rather than probing twice for one op.
    `conn_stats=None` (any caller that does not itself share a POST
    snapshot) fetches it here instead, once."""
    if conn_stats is None:
        prepared_stats = getattr(adapter_obj, "prepared_stats", None)
        if prepared_stats is None:
            return None
        conn_stats = prepared_stats()
    conn_stats_list = conn_stats
    for conn_stats in conn_stats_list:
        print(_format_prepared_row(peer, plug, op, conn_stats))
        if detail:
            for stmt in conn_stats["prepared_statements"]:
                print(_format_prepstmt_row(peer, plug, op, conn_stats["label"], stmt))
    return conn_stats_list


# ---------------------------------------------------------------------
# ROUNDTRIP (R-80, WO §1.2 D-1): per-connection statement deltas and
# per-database transaction/session deltas, printed only under
# `--roundtrip`. Two row shapes -- `conn=` (one per connection `prepared_
# stats()` returned, D-1 (i)) and `db=` (one per resolved database name,
# D-1 (ii)) -- both taken as a PRE (immediately before `_measure_op`
# starts timing) minus POST (immediately after) difference, never a
# running total (completion condition 4).
# ---------------------------------------------------------------------


def _per_request(value: float, requests: int) -> float:
    """The `_per_req=` denominator every `ROUNDTRIP` column shares:
    `value / requests`, `0.0` when `requests == 0` (completion condition
    6) -- never a bare division that would raise `ZeroDivisionError` for
    a `--warmup 0 --n 0` run."""
    return (value / requests) if requests else 0.0


def _format_roundtrip_conn_row(peer: str, plug: str, op: str, requests: int, label: str, stmts: int) -> str:
    """WO §1.2 D-1 (i): one `ROUNDTRIP conn=` line -- `peer`/`plug`/`op`/
    `requests`/`conn`/`stmts`/`stmts_per_req`, in that exact order
    (completion condition 1)."""
    return (
        f"ROUNDTRIP peer={peer} plug={plug} op={op} requests={requests} "
        f"conn={label} stmts={stmts} stmts_per_req={_per_request(stmts, requests):.2f}"
    )


def _format_roundtrip_db_row(
    peer: str, plug: str, op: str, requests: int, db: str, xacts: int, sessions: int, stale: bool,
) -> str:
    """WO §1.2 D-1 (ii): one `ROUNDTRIP db=` line -- `peer`/`plug`/`op`/
    `requests`/`db`/`xacts`/`xacts_per_req`/`sessions`/`sessions_per_req`/
    `stale`, in that exact order (completion condition 2). `stale` prints
    as the literal `0`/`1`, never `True`/`False` (WO §1.2 D-1's own
    `stale=<0|1>`)."""
    return (
        f"ROUNDTRIP peer={peer} plug={plug} op={op} requests={requests} "
        f"db={db} xacts={xacts} xacts_per_req={_per_request(xacts, requests):.2f} "
        f"sessions={sessions} sessions_per_req={_per_request(sessions, requests):.2f} stale={int(stale)}"
    )


def _emit_roundtrip_conn_rows(
    peer: str, plug: str, op: str, requests: int,
    pre_conn_stats: "list[dict] | None", post_conn_stats: "list[dict] | None",
) -> None:
    """WO §1.2 D-1 (i): one `conn=` line per entry of `post_conn_stats` (the
    SAME return value `_emit_prepared_rows` already printed `PREPARED`
    lines from, above -- never a second `prepared_stats()` call). `stmts`
    is `post.execute_count` minus the SAME connection's own `pre.
    execute_count` (matched by `label`) -- `0` when that label is absent
    from `pre_conn_stats` (a fresh connection since the pre-probe: WO
    §6.1 起草時の裁定 7, completion condition 5b), never the value carried
    over from a DIFFERENT label. Prints nothing, raises nothing, when
    `post_conn_stats` is `None` (no `prepared_stats()` on this plug at
    all -- completion condition 14, mirrors `_emit_prepared_rows`'s own
    identical skip)."""
    if post_conn_stats is None:
        return
    baseline_by_label = {stats["label"]: stats["execute_count"] for stats in (pre_conn_stats or [])}
    for stats in post_conn_stats:
        label = stats["label"]
        stmts = stats["execute_count"] - baseline_by_label.get(label, 0)
        print(_format_roundtrip_conn_row(peer, plug, op, requests, label, stmts))


def _clear_pg_stat_snapshot(admin_conn: Any) -> None:
    """WO §1.2 D-1 (ii)(a): `pg_stat_clear_snapshot()` on the harness's own
    admin connection (never a plug's own connection -- WO §1.1 (b))."""
    with admin_conn.cursor() as cur:
        cur.execute("SELECT pg_stat_clear_snapshot()")


def _read_db_stats(admin_conn: Any, db_names: "list[str]") -> "dict[str, tuple[int, int, int]]":
    """One read of `(xact_commit, xact_rollback, sessions)` per name in
    `db_names`, via the harness's own admin connection -- a database with
    no matching row (should not happen for a resolved name, but never
    raises) reads as `(0, 0, 0)`."""
    with admin_conn.cursor() as cur:
        cur.execute(
            "SELECT datname, xact_commit, xact_rollback, sessions FROM pg_stat_database WHERE datname = ANY(%s)",
            (list(db_names),),
        )
        rows = cur.fetchall()
    seen = {name: (commit, rollback, sessions) for name, commit, rollback, sessions in rows}
    return {name: seen.get(name, (0, 0, 0)) for name in db_names}


def _poll_pg_stat_database(
    db_names: "list[str]", *, read_stats: "Callable[[list[str]], dict[str, tuple[int, int, int]]]",
    clear_snapshot: "Callable[[], None]", min_wait: float, poll_interval: float, max_wait: float,
    sleep: "Callable[[float], None]" = time.sleep, now: "Callable[[], float]" = time.monotonic,
) -> "dict[str, dict]":
    """WO §1.2 D-1 (ii)(a)(b)(c), 設計レビュー1のH-1: `clear_snapshot()`
    once, then reads `db_names` every `poll_interval` seconds, per-name,
    until EITHER (confirmed) that name's own value has stayed identical
    for 3 consecutive reads AND at least `min_wait` seconds have elapsed
    since the clear (`stale=False`), OR `max_wait` seconds have elapsed,
    in which case every still-unconfirmed name is returned at its last-
    seen value with `stale=True` (completion conditions 11, 22a, 22b).
    "Stable from the very first read" does NOT confirm before `min_wait`
    (completion condition 11 -- WO §1.3 (5b)'s own run 1: a flat +5 for 20
    seconds was NOT the true +101). `sleep`/`now` are injectable (real-
    time-free tests, completion condition 11's own "時計と待ちを注入する
    か").

    `db_names` is de-duplicated (order preserved) before anything else
    (コードレビュー 2026-09-24 差し戻し 5): `confirmed`/`streak` are
    already keyed by NAME, so a caller passing the SAME real database
    name twice (`db_names={"app": "x", "platform": "x"}`, a degenerate
    but not impossible resolution) would otherwise never reach `len(
    confirmed) >= len(db_names)` -- the duplicate collapses to ONE
    `confirmed` entry while `len(db_names)` still counts it twice,
    forcing every such poll to run out the clock to `max_wait` and
    report `stale=1` even after genuinely confirming."""
    db_names = list(dict.fromkeys(db_names))
    clear_snapshot()
    start = now()
    last = read_stats(db_names)
    streak = {name: 1 for name in db_names}
    confirmed: "dict[str, dict]" = {}
    while True:
        elapsed = now() - start
        for name in db_names:
            if name in confirmed:
                continue
            if streak[name] >= 3 and elapsed >= min_wait:
                confirmed[name] = {"values": last[name], "stale": False}
        if len(confirmed) >= len(db_names):
            break
        if elapsed >= max_wait:
            for name in db_names:
                if name not in confirmed:
                    confirmed[name] = {"values": last[name], "stale": True}
            break
        sleep(poll_interval)
        current = read_stats(db_names)
        for name in db_names:
            if name in confirmed:
                continue
            if current[name] == last[name]:
                streak[name] += 1
            else:
                streak[name] = 1
        last = current
    return confirmed


def _probe_correction_count(conn_stats: "list[dict]", matcher: "Callable[[dict], bool]") -> int:
    """WO §1.2 D-1's own "probe が実際に走った接続の本数" -- how many
    entries of `conn_stats` were both actually probed (`probed` true,
    `psycopg_counting.probe_prepared_statements`'s own early-return for a
    non-IDLE connection never calls `commit()`) AND, per `matcher`, belong
    to the database this correction is being subtracted from (設計レビュー
    1のM-4's own derivation rule, `_resolve_app_db_and_matcher`
    above)."""
    return sum(1 for stats in conn_stats if stats.get("probed") and matcher(stats))


def _emit_roundtrip_db_rows(
    peer: str, plug: str, op: str, requests: int, db_names: "dict[str, str]",
    pre_db_values: "dict[str, dict] | None", post_db_values: "dict[str, dict] | None",
    post_conn_stats: "list[dict] | None", correction_matcher: "Callable[[dict], bool] | None",
    *, pre_probe_conn_stats: "list[dict] | None" = None,
) -> None:
    """WO §1.2 D-1 (ii): one `db=` line per resolved kind in `db_names`
    (`"app"`/`"platform"`) present in both `pre_db_values`/`post_db_
    values`. `xacts` is `Δxact_commit + Δxact_rollback` (completion
    condition 8) MINUS the POST probe's own correction (completion
    condition 9) -- `db=platform`'s own correction is always 0 (WO §1.2
    D-1: neither peer's platform/credential connections are ever probed),
    `db=app`'s is `_probe_correction_count(post_conn_stats,
    correction_matcher)` PLUS, when `pre_probe_conn_stats` is given,
    `_probe_correction_count(pre_probe_conn_stats, correction_matcher)`
    -- `DBTIME`'s own PRE snapshot (taken inside `_measure_op`, between
    `ROUNDTRIP`'s own PRE poll and the measured window) probes every IDLE
    application connection it reaches exactly like the shared POST
    snapshot does, and each such probe's own `commit()` lands inside the
    SAME `ROUNDTRIP` window, so its `xact_commit` also needs subtracting.
    `pre_probe_conn_stats=None` (any caller that does not supply it) skips
    this second subtraction entirely. `sessions` is `Δsessions`, unconnected. Prints
    nothing for a kind whose read is missing from either side (never
    raises `KeyError`).

    `stale` is the LOGICAL OR of the PRE and POST reads' own `stale`
    (コードレビュー 2026-09-24 差し戻し 1): a `Δ` built from one settled
    read and one that hit the 30s ceiling is exactly as unsettled as one
    built from two unsettled reads -- either side alone being `stale=1`
    means this row's own delta cannot be trusted as a final value."""
    if post_db_values is None:
        return
    for kind, _db_name in db_names.items():
        pre_entry = (pre_db_values or {}).get(kind)
        post_entry = post_db_values.get(kind)
        if pre_entry is None or post_entry is None:
            continue
        pre_commit, pre_rollback, pre_sessions = pre_entry["values"]
        post_commit, post_rollback, post_sessions = post_entry["values"]
        xacts = (post_commit - pre_commit) + (post_rollback - pre_rollback)
        if kind == "app" and post_conn_stats is not None and correction_matcher is not None:
            xacts -= _probe_correction_count(post_conn_stats, correction_matcher)
            if pre_probe_conn_stats is not None:
                xacts -= _probe_correction_count(pre_probe_conn_stats, correction_matcher)
        sessions = post_sessions - pre_sessions
        stale = bool(pre_entry["stale"]) or bool(post_entry["stale"])
        print(_format_roundtrip_db_row(peer, plug, op, requests, kind, xacts, sessions, stale))


def _roundtrip_pre_probe(
    adapter_obj: Any, *, admin_conn: Any, db_names: "dict[str, str]", min_wait: float, poll_interval: float, max_wait: float,
) -> "tuple[list[dict] | None, dict[str, dict] | None]":
    """WO §1.2 D-1, 設計レビュー1のM-3 (全 op に一般化): the PRE half of a
    single op's pre/post pair -- one `prepared_stats()` call (mirrors
    `_emit_prepared_rows`'s own POST call; together exactly 2 per op,
    completion condition 3), and, when `db_names` resolved at least one
    kind, one full `_poll_pg_stat_database` cycle so the PRE baseline is
    itself a settled (not mid-flush) value -- never a bare single read
    (WO §1.3 (5b): an unsettled read would double-count the PREVIOUS op's
    still-pending commits as this op's own)."""
    prepared_stats = getattr(adapter_obj, "prepared_stats", None)
    conn_stats = prepared_stats() if prepared_stats is not None else None
    db_values = None
    if db_names:
        # `_poll_pg_stat_database` is keyed by the REAL database name (it
        # knows nothing of "app"/"platform" -- that vocabulary is this
        # file's own, not `pg_stat_database`'s) -- re-key its result back
        # to `db_names`' own kind ("app"/"platform") here, once, so every
        # OTHER caller (`_emit_roundtrip_db_rows`) can go on using the
        # kind alone, exactly like `db_names` itself.
        by_dbname = _poll_pg_stat_database(
            list(db_names.values()),
            read_stats=lambda dbs: _read_db_stats(admin_conn, dbs),
            clear_snapshot=lambda: _clear_pg_stat_snapshot(admin_conn),
            min_wait=min_wait, poll_interval=poll_interval, max_wait=max_wait,
        )
        db_values = {kind: by_dbname[db_name] for kind, db_name in db_names.items()}
    return conn_stats, db_values


def _emit_measurement_rows(
    peer: str, plug: str, op: str, adapter_obj: Any, *, prepared_detail: bool,
    roundtrip: "dict | None" = None, measurement: "dict | None" = None,
) -> "list[dict] | None":
    """R-79 (WO §1.2 D-3, rework item (C)): the ONE call site
    `_measure_plug` uses per (plug, op) -- always `_emit_pool_rows` FIRST,
    then `_emit_prepared_rows` (WO §1.2 D-3's own "同じ op の POOL 行の後
    に置く"). Pinning the order here, in a single small function both
    `_measure_plug` and `tools/tests/test_perf_baseline.py` call directly,
    means a test can observe the real order the measurement loop itself
    produces -- not a copy of the same two calls re-typed in the test,
    which could drift from `_measure_plug`'s own call order unnoticed.

    R-80 (WO §1.2 D-1, §2.1's own "`_emit_measurement_rows` に3つ目の emit
    を足す"): when `roundtrip` is given (a plain dict built by `_measure_
    plug`/tests -- `requests`/`pre_conn_stats`/`pre_db_values`/
    `admin_conn`/`db_names`/`correction_matcher`/`min_wait`/
    `poll_interval`/`max_wait`), prints `ROUNDTRIP` rows AFTER the
    `PREPARED` rows above (completion condition 13) -- the POST probe
    reused from `_emit_prepared_rows`'s own return value, and a fresh
    POST `_poll_pg_stat_database` cycle. `roundtrip=None` (the default --
    every call site `--roundtrip` did not ask for) emits nothing new at
    all, byte-identical to the pre-R-80 function (completion condition
    21a/21b).

    `measurement`, when given (a plain dict `_measure_op_and_emit` builds
    from `_measure_op`'s own return value plus `concurrency`/`requests`/
    `thread_limit`), prints one `CPU` line FIRST -- before `POOL` -- then,
    when `adapter_obj` has `prepared_stats`, fetches the POST `prepared_
    stats()` snapshot itself (right after `_emit_pool_rows`, preserving
    the existing pool-then-prepared call order) and prints `DBTIME`
    line(s) from the PRE/POST difference, BEFORE handing that SAME POST
    snapshot to `_emit_prepared_rows` below via its own `conn_stats`
    parameter -- one POST `prepared_stats()` call shared by `DBTIME
    scope=app` and every `PREPARED` line, never two. `measurement=None`
    (any call site that does not supply it) emits no `CPU`/`DBTIME` line
    at all and fetches nothing extra."""
    if measurement is not None:
        print(_format_cpu_row(peer, plug, op, measurement))
    _emit_pool_rows(peer, plug, op, adapter_obj)
    post_conn_stats = None
    if measurement is not None:
        prepared_stats = getattr(adapter_obj, "prepared_stats", None)
        if prepared_stats is not None:
            post_conn_stats = prepared_stats()
            platform_db_time_stats = getattr(adapter_obj, "platform_db_time_stats", None)
            post_platform_stats = platform_db_time_stats() if platform_db_time_stats is not None else None
            _emit_dbtime_rows(peer, plug, op, measurement, post_conn_stats, post_platform_stats)
    post_conn_stats = _emit_prepared_rows(peer, plug, op, adapter_obj, detail=prepared_detail, conn_stats=post_conn_stats)
    if roundtrip is not None:
        requests = roundtrip["requests"]
        _emit_roundtrip_conn_rows(peer, plug, op, requests, roundtrip["pre_conn_stats"], post_conn_stats)
        db_names = roundtrip["db_names"]
        if db_names:
            admin_conn = roundtrip["admin_conn"]
            # Same re-keying as `_roundtrip_pre_probe` above (real database
            # name -> "app"/"platform" kind) -- kept in sync deliberately,
            # since `_emit_roundtrip_db_rows` below looks its two inputs up
            # by kind, not by database name.
            by_dbname = _poll_pg_stat_database(
                list(db_names.values()),
                read_stats=lambda dbs: _read_db_stats(admin_conn, dbs),
                clear_snapshot=lambda: _clear_pg_stat_snapshot(admin_conn),
                min_wait=roundtrip["min_wait"], poll_interval=roundtrip["poll_interval"], max_wait=roundtrip["max_wait"],
            )
            post_db_values = {kind: by_dbname[db_name] for kind, db_name in db_names.items()}
            dbtime_pre = (measurement or {}).get("dbtime_pre")
            pre_probe_conn_stats = dbtime_pre.get("conn_stats") if dbtime_pre is not None else None
            _emit_roundtrip_db_rows(
                peer, plug, op, requests, db_names, roundtrip["pre_db_values"], post_db_values,
                post_conn_stats, roundtrip["correction_matcher"],
                pre_probe_conn_stats=pre_probe_conn_stats,
            )
    return post_conn_stats


def _measure_op_and_emit(
    fn: Callable[[], None], *, peer: str, plug: str, op: str,
    warmup: int, n: int, concurrency: int, counter: _CallCounter, adapter_obj: Any, prepared_detail: bool,
    roundtrip_enabled: bool, admin_conn: Any, db_names: "dict[str, str]",
    correction_matcher: "Callable[[dict], bool] | None", min_wait: float, poll_interval: float, max_wait: float,
    after_measure: "Callable[[list[float]], None] | None" = None,
) -> "tuple[list[float], list[float]]":
    """R-80 (WO §1.2 D-1, §2.1): runs one (plug, op)'s `_measure_op` call
    and its trailing `_emit_measurement_rows` call as one unit, with the
    `ROUNDTRIP` PRE half (`_roundtrip_pre_probe`) taken immediately BEFORE
    `_measure_op` starts timing and the POST half taken from inside `_emit_
    measurement_rows` immediately after -- factored out once so every one
    of `_measure_plug`'s own 4 op blocks (query/mutate/batch/cross_entity)
    wires PRE/POST the same way, rather than 4 near-identical copies.

    `roundtrip_enabled=False` (every call site when `--roundtrip` was not
    given) skips the ROUNDTRIP PRE probe/poll entirely -- no `db=` poll
    ever touches `admin_conn` (completion condition 21a). `prepared_
    stats()` is still called twice per op in that case (a separate DBTIME
    PRE snapshot inside `_measure_op` itself, plus the POST call below) --
    completion condition 21b's own count.

    `after_measure`, when given, runs on the measured `calls` list right
    after `_measure_op` returns but BEFORE any emission -- `_measure_plug`'s
    own `query` block uses this for `_run_self_check`. **順序は保存されて
    いる**: `_run_self_check` runs after `_measure_op` and before `_emit_
    measurement_rows`'s own prints, in the same position relative to every
    printed line; its only position relative to `_measure_plug`'s own `_row(
    ...)`/`rows.append(...)` (no side effect of their own) differs, running
    before them rather than after.

    Builds `measurement` (`wall_ms`/`cpu_total_ms`/`cpu_main_ms`/`dbtime_
    pre` from `_measure_op`'s own third return value, plus `concurrency`,
    `requests=n * concurrency` -- MEASURED requests only, never `warmup`'s,
    unlike `roundtrip`'s own `(warmup + n) * concurrency`, and `thread_
    limit` from `adapter_obj.perf_thread_limit()` when present, else the
    literal string `"default"`) and always passes it to `_emit_
    measurement_rows`, which is what actually prints the `CPU`/`DBTIME`
    lines -- this function itself has no keyword toggle for that; every
    call, direct or through `_measure_plug`, gets it."""
    pre_conn_stats: "list[dict] | None" = None
    pre_db_values: "dict[str, dict] | None" = None
    if roundtrip_enabled:
        pre_conn_stats, pre_db_values = _roundtrip_pre_probe(
            adapter_obj, admin_conn=admin_conn, db_names=db_names,
            min_wait=min_wait, poll_interval=poll_interval, max_wait=max_wait,
        )
    durations, calls, measured = _measure_op(
        fn, warmup=warmup, n=n, concurrency=concurrency, counter=counter, adapter_obj=adapter_obj,
    )
    if after_measure is not None:
        after_measure(calls)
    roundtrip: "dict | None" = None
    if roundtrip_enabled:
        roundtrip = {
            "requests": (warmup + n) * concurrency,
            "pre_conn_stats": pre_conn_stats,
            "pre_db_values": pre_db_values,
            "admin_conn": admin_conn,
            "db_names": db_names,
            "correction_matcher": correction_matcher,
            "min_wait": min_wait,
            "poll_interval": poll_interval,
            "max_wait": max_wait,
        }
    accessor = getattr(adapter_obj, "perf_thread_limit", None)
    thread_limit = accessor() if accessor is not None else None
    measurement = {
        "concurrency": concurrency,
        "requests": n * concurrency,
        "thread_limit": thread_limit if thread_limit is not None else "default",
        "wall_ms": measured["wall_ms"],
        "cpu_total_ms": measured["cpu_total_ms"],
        "cpu_main_ms": measured["cpu_main_ms"],
        "dbtime_pre": measured["dbtime_pre"],
    }
    _emit_measurement_rows(
        peer, plug, op, adapter_obj, prepared_detail=prepared_detail, roundtrip=roundtrip, measurement=measurement,
    )
    return durations, calls


# ---------------------------------------------------------------------
# one plug's own full measurement
# ---------------------------------------------------------------------


def _measure_plug(
    name: str, adapter_obj: ConformanceAdapter, *, warmup: int, n: int, concurrency: int, prepared_detail: bool = False,
    roundtrip: bool = False, admin_conn: Any = None,
    min_wait: float = _ROUNDTRIP_MIN_WAIT_S, poll_interval: float = _ROUNDTRIP_POLL_INTERVAL_S,
    max_wait: float = _ROUNDTRIP_MAX_WAIT_S,
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

        # R-80 (WO §1.2 D-2): resolved ONCE per plug (never per op) --
        # `db_names`/`correction_matcher` stay fixed for this cell's whole
        # lifetime. Empty `db_names` (neither form resolved) means every
        # op's `db=` emission below is a silent no-op (completion
        # condition 12b), computed only when `roundtrip` is actually on.
        db_names: "dict[str, str]" = {}
        correction_matcher: "Callable[[dict], bool] | None" = None
        if roundtrip:
            app_db, correction_matcher = _resolve_app_db_and_matcher(cell, app_id)
            if app_db is not None:
                db_names["app"] = app_db
            platform_db = _resolve_platform_db(adapter_obj)
            if platform_db is not None:
                db_names["platform"] = platform_db

        rows: list[dict] = []
        with _backend_call_counter(cell) as counter:
            # --- query ---
            query_runtime = adapter_obj.authenticate(adapter_obj.issue_credential(app_id, "runtime"))

            def _do_query() -> None:
                adapter_obj.select_eq(query_runtime, entity, ["label"], "label", "perf-seed")

            durations, calls = _measure_op_and_emit(
                _do_query, peer=peer, plug=name, op="query",
                warmup=warmup, n=n, concurrency=concurrency, counter=counter, adapter_obj=adapter_obj,
                prepared_detail=prepared_detail, roundtrip_enabled=roundtrip, admin_conn=admin_conn,
                db_names=db_names, correction_matcher=correction_matcher,
                min_wait=min_wait, poll_interval=poll_interval, max_wait=max_wait,
                after_measure=lambda c: _run_self_check(name, c),
            )
            query_row = _row(peer, name, transport, "query", durations, calls, concurrency)
            rows.append(query_row)

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

            durations, calls = _measure_op_and_emit(
                _do_mutate, peer=peer, plug=name, op="mutate",
                warmup=warmup, n=n, concurrency=concurrency, counter=counter, adapter_obj=adapter_obj,
                prepared_detail=prepared_detail, roundtrip_enabled=roundtrip, admin_conn=admin_conn,
                db_names=db_names, correction_matcher=correction_matcher,
                min_wait=min_wait, poll_interval=poll_interval, max_wait=max_wait,
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

            durations, calls = _measure_op_and_emit(
                _do_batch, peer=peer, plug=name, op="batch",
                warmup=warmup, n=n, concurrency=concurrency, counter=counter, adapter_obj=adapter_obj,
                prepared_detail=prepared_detail, roundtrip_enabled=roundtrip, admin_conn=admin_conn,
                db_names=db_names, correction_matcher=correction_matcher,
                min_wait=min_wait, poll_interval=poll_interval, max_wait=max_wait,
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

                durations, calls = _measure_op_and_emit(
                    _do_cross_entity, peer=peer, plug=name, op="cross_entity",
                    warmup=warmup, n=n, concurrency=concurrency, counter=counter, adapter_obj=adapter_obj,
                    prepared_detail=prepared_detail, roundtrip_enabled=roundtrip, admin_conn=admin_conn,
                    db_names=db_names, correction_matcher=correction_matcher,
                    min_wait=min_wait, poll_interval=poll_interval, max_wait=max_wait,
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
    # R-79 (WO §1.2 D-3, completion condition 19): off by default -- one
    # `PREPSTMT` line per prepared statement per connection is far more
    # output than the summary `PREPARED` line above it, and is only useful
    # when inspecting exactly WHICH statements are prepared (WO §1.2 D-3's
    # own "判定は share の大小ではなく PREPSTMT の一覧で行う").
    parser.add_argument(
        "--prepared-detail", action="store_true",
        help="also print one PREPSTMT line per prepared statement per connection (default: off)",
    )
    # R-80 (WO §1.2 D-1, completion condition 21a): off by default -- the
    # `pg_stat_database` confirm-wait this adds (12-30s per pre/post read,
    # WO §6.1 設計レビュー1のH-1) would otherwise slow down every ordinary
    # run, not just one taken specifically to look at round-trip counts.
    parser.add_argument(
        "--roundtrip", action="store_true",
        help=(
            "also print ROUNDTRIP lines (per-connection statement deltas and per-database "
            "transaction/session deltas, WO §1.2 D-1) -- default off, since the pg_stat_database "
            "confirm-wait this adds costs several seconds per (plug, op)"
        ),
    )
    # Work order `docs/work-orders/WORK_ORDER_R101_SERIALIZATION_ATTRIBUTION_V1.md` §7.3 D-15: measures a real, separately-started
    # composition root (`conformance-tests/registry.json`'s own
    # `composition_roots` entry named PEER, the SAME C-26 launcher
    # `conformance-tests/test_c26_composition_root.py` drives) instead of
    # the 6 registered conformance plugs -- `None` (default) keeps every
    # existing run exactly as it was. `--concurrency`/`--n`/`--warmup`
    # above are shared with this path unchanged; `--client-processes`
    # below is the one flag this path alone reads.
    parser.add_argument(
        "--real-server", type=str, default=None, metavar="PEER",
        help=(
            "measure a real, separately-started composition root (registry.json's own "
            "composition_roots entry PEER) instead of the 6 conformance plugs -- prints "
            "REALPERF/REALCPU lines only, never PERF/CPU/POOL/DBTIME/PREPARED/ROUNDTRIP (work order "
            "docs/work-orders/WORK_ORDER_R101_SERIALIZATION_ATTRIBUTION_V1.md §7.3 D-15)"
        ),
    )
    parser.add_argument(
        "--client-processes", type=int, default=8, metavar="N",
        help=(
            "OS client processes --real-server dispatches --concurrency K requests across "
            "(default 8); the actual count used is min(N, K)"
        ),
    )
    return parser


def _roundtrip_enabled(args: argparse.Namespace) -> bool:
    """R-80 (WO §1.2 D-1, completion condition 21a): `--roundtrip` alone
    gates every `ROUNDTRIP`-related code path in this file (the PRE probe/
    poll, the admin connection, every `ROUNDTRIP` print) -- split out as
    its own function so a test can pin the exact gating decision without
    running `_run`/`main` end-to-end against a real registry."""
    return bool(args.roundtrip)


# ---------------------------------------------------------------------
# Work order `docs/work-orders/WORK_ORDER_R101_SERIALIZATION_ATTRIBUTION_V1.md` §7.3 D-15: `--real-server` -- measures a real,
# separately-started composition root (the C-26 launcher, `registry.json`'s
# own `composition_roots` section) instead of the 6 registered conformance
# plugs `_run` above measures. Never both in the same invocation: `main()`
# branches on `args.real_server` before either path is entered.
# ---------------------------------------------------------------------

_REAL_SERVER_ENTITY = "dsaperfreal"
_REAL_SERVER_FIELD = "label"
_REAL_SERVER_BARRIER_TIMEOUT_S = 60.0
_REAL_SERVER_QUEUE_TIMEOUT_S = 60.0

# `forkserver`, never the default `fork`: forking directly from THIS
# process after it has already made HTTP calls is a known fork-after-
# network hazard. `_warm_forkserver` below starts the forkserver helper
# before this run's first HTTP call -- every child process is forked
# from that helper, never from this process.
_REAL_SERVER_MP_CONTEXT = multiprocessing.get_context("forkserver")
_real_server_forkserver_warmed = False


def _real_server_forkserver_noop() -> None:
    """A trivial, picklable target -- used only to force `forkserver`'s
    own helper process to start, in `_warm_forkserver` below."""
    return None


def _warm_forkserver() -> None:
    """Starts `_REAL_SERVER_MP_CONTEXT`'s own `forkserver` helper process
    if it has not already started -- a no-op on every call after the
    first. `_run_real_server` calls this before any HTTP setup call:
    without this, a child process hung mid-import on macOS during
    development when the helper started after the first HTTP call
    instead."""
    global _real_server_forkserver_warmed
    if _real_server_forkserver_warmed:
        return
    warmup_process = _REAL_SERVER_MP_CONTEXT.Process(target=_real_server_forkserver_noop)
    warmup_process.start()
    warmup_process.join()
    _real_server_forkserver_warmed = True


def _num_real_server_clients(client_processes: int, concurrency: int) -> int:
    """The work order's D-15: the ACTUAL client-process count for one `--real-server` run --
    never more OS processes than there are requests to spread across them
    (its completion conditions 132/133/168: `min(client_processes,
    concurrency)`)."""
    return min(client_processes, concurrency)


def _distribute_group_counts(concurrency: int, n_children: int) -> "list[int]":
    """The work order's D-15: how many of one group's `concurrency` requests each of `n_
    children` client processes sends, in the SAME order those processes
    are started in. `concurrency // n_children` each, with the remainder
    (`concurrency % n_children`) giving the FIRST that many children one
    EXTRA request apiece (its completion condition 169) -- never the last."""
    base, remainder = divmod(concurrency, n_children)
    return [base + 1 if i < remainder else base for i in range(n_children)]


def _group_wall_ms(start_ns: int, completion_ns: "list[int]") -> float:
    """The work order's D-15: one group's own wall-clock span -- the LATEST child's own
    completion time (`time.time_ns()`, never an average of them) minus the
    single shared start (the MINIMUM of the children's own `time.
    time_ns()`, each read immediately after ITS OWN `multiprocessing.
    Barrier.wait()` returns, never the parent's -- its completion condition
    135). Milliseconds, like every other `_ms` value this file prints."""
    return (max(completion_ns) - start_ns) / 1_000_000.0


def _format_realperf_row(
    peer: str, concurrency: int, client_processes: int, n: int, p50_ms: float, p95_ms: float,
) -> str:
    """The work order's D-15's own literal format -- its completion condition 139. `plug=` is
    always `<peer>-real`: a real-server run is its own transport, never one
    of the 6 registered plugs' own names."""
    return (
        f"REALPERF peer={peer} plug={peer}-real transport=real-server op=query "
        f"concurrency={concurrency} client_processes={client_processes} n={n} "
        f"p50_ms={p50_ms:.3f} p95_ms={p95_ms:.3f}"
    )


def _format_realcpu_row(
    peer: str, concurrency: int, client_processes: int, requests: int, wall_ms: float, cpu_client_ms: float,
) -> str:
    """The work order's D-15's own literal format -- its completion condition 140. The floor's
    own visualization (D-16), never a judgement this tool itself makes
    (P-8)."""
    return (
        f"REALCPU peer={peer} plug={peer}-real op=query concurrency={concurrency} "
        f"client_processes={client_processes} requests={requests} wall_ms={wall_ms:.3f} "
        f"cpu_client_ms={cpu_client_ms:.3f}"
    )


def _load_composition_root_class(registry_path: Path, peer: str) -> type:
    """The work order's D-15: reads ONLY `registry_path`'s own `composition_roots` section
    (never `adapters` -- `--real-server` never builds one of the 6
    registered conformance plugs, its completion condition 170/127) for the
    entry named `peer`, discovering the launcher CLASS exactly the way
    `conformance-tests/conftest.py`'s own `_discover_composition_roots`
    does (`<peer>/conformance` added to `sys.path`, the module imported,
    the class read off it by name) -- never an instance: starting it is
    `_run_real_server`'s own job, once, after this returns."""
    data = json.loads(registry_path.read_text())
    for entry in data.get("composition_roots", []):
        if entry["name"] != peer:
            continue
        conformance_dir = str(ROOT / entry["name"] / "conformance")
        if conformance_dir not in sys.path:
            sys.path.insert(0, conformance_dir)
        module = importlib.import_module(entry["module"])
        return getattr(module, entry["launcher_class"])
    raise RealServerMeasurementFailure(
        f"--real-server {peer!r}: no composition_roots entry named {peer!r} in {registry_path}"
    )


def _real_server_request(method: str, url: str, *, bearer: str, body: "dict | None" = None) -> "tuple[int, Any]":
    """The work order's D-15's own one-shot setup calls (never the measured `query` traffic
    below, which goes through real, concurrent `httpx.AsyncClient` calls in
    the child processes instead): a single synchronous request, `urllib`
    only (this file's own standard-library-only-at-the-top convention,
    module docstring) -- mirrors `tools/deploy_smoke.py`'s own `_request`,
    a separate copy rather than an import (that tool is a standalone
    operational aid, not a dependency of this one)."""
    data = None
    headers = {"Authorization": f"Bearer {bearer}"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            status = response.status
            raw = response.read()
    except urllib.error.HTTPError as exc:
        status = exc.code
        raw = exc.read()
    except (urllib.error.URLError, OSError) as exc:
        raise RealServerMeasurementFailure(f"{method} {url} failed: {exc}") from exc
    try:
        parsed = json.loads(raw) if raw else None
    except json.JSONDecodeError as exc:
        raise RealServerMeasurementFailure(f"{method} {url} returned a non-JSON body: {exc}") from exc
    return status, parsed


def _resolve_application_id(data_base_url: str, runtime_bearer: str) -> str:
    """The work order's D-15: this deployment's own `application_id`, needed to build the
    `POST /control/v1/credentials` body below -- the launcher's own
    observation surface (`data_base_url`/`control_base_url`/`runtime_
    bearer`/`control_bearer`) names no such property, so this reads it the
    one documented way an authenticated application credential can (`GET
    /v1/capabilities`'s own `application_scope`, `r2db_api.capabilities_
    document`:144 / `mitatedb_api.capabilities_document`:421 -- the SAME
    field `runtime`/`developer` role always carries)."""
    status, document = _real_server_request("GET", f"{data_base_url}/capabilities", bearer=runtime_bearer)
    if status != 200 or not isinstance(document, dict) or not document.get("application_scope"):
        raise RealServerMeasurementFailure(
            f"GET /v1/capabilities -> {status}, could not resolve this deployment's own application_id"
        )
    return document["application_scope"]


def _rotate_control_credential(control_base_url: str, control_bearer: str, control_credential_id: str) -> str:
    """The launcher's own `control_bearer` is `must_rotate=true` (`ops bootstrap`'s own
    printed warning) -- the only operations it authorizes are `GET /control/v1/capabilities`
    and rotating itself, so this MUST run before any other control-plane call
    (`issue_credential` included) can succeed. `POST /control/v1/credentials/
    {credential_id}/rotate`, no request body, path `credential_id` the launcher's own
    `control_credential_id` (the rotate path requires the path id to equal the
    presented credential's own id; the contract forbids deriving that id from the
    secret, so this never parses `control_bearer` itself). Returns the new secret --
    every control-plane call after this uses it, never the original `control_bearer`."""
    status, document = _real_server_request(
        "POST", f"{control_base_url}/credentials/{control_credential_id}/rotate", bearer=control_bearer,
    )
    if status != 200 or not isinstance(document, dict) or not document.get("secret"):
        raise RealServerMeasurementFailure(
            f"POST /control/v1/credentials/{control_credential_id}/rotate -> {status}, could not rotate the launcher's own control credential"
        )
    return document["secret"]


def _issue_developer_credential(control_base_url: str, control_bearer: str, application_id: str) -> str:
    """The work order's D-15: `POST /control/v1/credentials`, `role=developer`, authorized
    by the rotated control credential `_rotate_control_credential` just returned --
    its completion conditions 164/165 (the entity/row setup right after this reuses
    the returned secret, never `control_bearer`/`runtime_bearer`)."""
    status, document = _real_server_request(
        "POST", f"{control_base_url}/credentials", bearer=control_bearer,
        body={"application_id": application_id, "role": "developer"},
    )
    if status != 200 or not isinstance(document, dict) or not document.get("secret"):
        raise RealServerMeasurementFailure(
            f"POST /control/v1/credentials -> {status}, could not issue a developer credential"
        )
    return document["secret"]


def _prepare_real_server_entity(data_base_url: str, developer_bearer: str, entity: str, field: str) -> None:
    """The work order's D-15: creates the one measurement entity and seeds its one row,
    both with the developer credential `_issue_developer_credential` just
    returned (its completion condition 165) -- never `control_bearer`/
    `runtime_bearer`."""
    status, _document = _real_server_request(
        "POST", f"{data_base_url}/schema/operations", bearer=developer_bearer,
        body={"operation": "create_entity", "entity": entity, "fields": [field], "field_types": {field: "string"}},
    )
    if status != 200:
        raise RealServerMeasurementFailure(f"POST /v1/schema/operations -> {status}, could not create {entity!r}")
    status, _document = _real_server_request(
        "POST", f"{data_base_url}/data/{entity}/mutations", bearer=developer_bearer,
        body={"operations": [{"operation": "insert", "values": {field: "perfbase-real-seed"}}]},
    )
    if status != 200:
        raise RealServerMeasurementFailure(f"POST /v1/data/{entity}/mutations -> {status}, could not seed {entity!r}")


def _confirm_first_query(data_base_url: str, runtime_bearer: str, entity: str, field: str) -> None:
    """The work order's D-15: the K=1 sanity query -- one real `query`, with the `runtime_
    bearer` every measured request below also uses (its completion condition
    166), BEFORE any concurrent measurement starts. `OC` 1.5-32 (空振り禁
    止): 200 alone is not enough -- a 200 with zero rows is refused exactly
    like a non-200 status is (its completion condition 167), never silently
    measured as if it were a real read."""
    status, document = _real_server_request(
        "POST", f"{data_base_url}/data/{entity}/query", bearer=runtime_bearer, body={"select": [field]},
    )
    if status != 200:
        raise RealServerMeasurementFailure(f"POST /v1/data/{entity}/query (K=1 sanity check) -> {status} (expected 200)")
    items = document.get("items") if isinstance(document, dict) else None
    if not isinstance(items, list) or not items:
        raise RealServerMeasurementFailure(
            f"POST /v1/data/{entity}/query (K=1 sanity check) -> 200 but zero rows -- refusing an empty measurement"
        )


def _real_server_client_worker(
    count: int, query_url: str, bearer: str, field: str, barrier: Any, result_queue: Any,
) -> None:
    """The work order's D-15: one client OS process's own share of one group -- `count`
    real `query` requests, fired together via exactly ONE `asyncio.gather`
    call (never one `await` at a time -- its completion condition 134), after
    `barrier.wait()` releases every client process (and the parent, which
    is a party too) together. A per-request failure (a non-2xx status, or
    the connection dropping mid-flight) is caught HERE and turned into a
    status this worker reports back (`599` for a transport-level failure
    that never got a real HTTP status at all) -- it never raises out of
    this function, which would otherwise leave the parent's own
    `result_queue.get()` for this group waiting forever. Completion
    times are `time.time_ns()` only (never `time.perf_counter()`, which
    cannot be compared across process boundaries -- its completion condition
    136); CPU is this process's own `resource.getrusage(RUSAGE_SELF)`
    difference across the SAME `asyncio.gather` call (`ru_utime +
    ru_stime`, the same pair `_measure_op`'s own `cpu_total_ms` reads)."""
    import httpx  # noqa: PLC0415 -- lazy, real-transport dependency (module docstring)

    async def _one(client: "httpx.AsyncClient") -> "tuple[int, int | None]":
        try:
            response = await client.post(query_url, json={"select": [field]}, headers={"Authorization": f"Bearer {bearer}"})
        except Exception:  # noqa: BLE001 - a transport failure is a reported status, never an uncaught worker crash
            return 599, None
        rows: "int | None" = None
        if response.status_code == 200:
            try:
                items = response.json().get("items")
                rows = len(items) if isinstance(items, list) else None
            except Exception:  # noqa: BLE001 - an unparseable 200 body is reported, not raised
                rows = None
        return response.status_code, rows

    async def _run_group() -> None:
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                barrier.wait(timeout=_REAL_SERVER_BARRIER_TIMEOUT_S)
            except threading.BrokenBarrierError:
                return
            started_ns = time.time_ns()
            before = resource.getrusage(resource.RUSAGE_SELF)
            results = await asyncio.gather(*(_one(client) for _ in range(count)))
            completed_ns = time.time_ns()
            after = resource.getrusage(resource.RUSAGE_SELF)
            cpu_ms = ((after.ru_utime + after.ru_stime) - (before.ru_utime + before.ru_stime)) * 1000.0
            result_queue.put({
                "t0": started_ns,
                "t1": completed_ns,
                "cpu_ms": cpu_ms,
                "statuses": [status for status, _rows in results],
                "row_counts": [rows for _status, rows in results],
                "pid": os.getpid(),
            })

    asyncio.run(_run_group())


def _run_one_real_server_group(
    query_url: str, bearer: str, field: str, counts: "list[int]", n_children: int,
) -> dict:
    """The work order's D-15: one group (warmup or measured) -- spawns `n_children` fresh
    OS processes via `_REAL_SERVER_MP_CONTEXT` (`forkserver`, warmed by
    `_run_real_server`'s own `_warm_forkserver` call before this is ever
    reached), a `Barrier(n_children + 1)` the parent is itself a party of
    (`multiprocessing.Barrier`'s own re-entrant `.wait()`, its
    completion condition 136), and one shared `Queue` every child's
    single result lands on. The parent calls `barrier.wait()` too,
    only to release the barrier -- its own return from that call is
    never read as a timestamp.
    `start_ns` is the MINIMUM of the children's own `t0` (each child's
    own `time.time_ns()`, read immediately after ITS OWN `barrier.wait()`
    returns) -- never the parent's, which lags the first child to resume
    by however long the parent itself takes to wake and re-schedule.
    Every child process is joined (and, if still alive past its own
    timeout, terminated) in
    `finally`, whether this group succeeded or not -- a broken barrier or
    a queue timeout never leaves an orphaned child process behind."""
    ctx = _REAL_SERVER_MP_CONTEXT
    barrier = ctx.Barrier(n_children + 1)
    result_queue: Any = ctx.Queue()
    processes = [
        ctx.Process(target=_real_server_client_worker, args=(counts[i], query_url, bearer, field, barrier, result_queue))
        for i in range(n_children)
    ]
    for process in processes:
        process.start()
    try:
        try:
            barrier.wait(timeout=_REAL_SERVER_BARRIER_TIMEOUT_S)
        except threading.BrokenBarrierError as exc:
            raise RealServerMeasurementFailure(f"real-server client processes did not start together in time: {exc}") from exc
        try:
            messages = [result_queue.get(timeout=_REAL_SERVER_QUEUE_TIMEOUT_S) for _ in range(n_children)]
        except queue.Empty as exc:
            raise RealServerMeasurementFailure(f"a real-server client process did not report a result in time: {exc}") from exc
    finally:
        for process in processes:
            process.join(timeout=30)
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
    start_ns = min(message["t0"] for message in messages)
    completion_ns = [message["t1"] for message in messages]
    return {
        "wall_ms": _group_wall_ms(start_ns, completion_ns),
        "cpu_client_ms": sum(message["cpu_ms"] for message in messages),
        "statuses": [status for message in messages for status in message["statuses"]],
        "client_processes": len({message["pid"] for message in messages}),
        "messages": messages,
    }


def _measure_real_server(
    *, query_url: str, bearer: str, field: str, warmup: int, n: int, concurrency: int, n_children: int, counts: "list[int]",
) -> dict:
    """The work order's D-15: `warmup + n` groups, each one call to `_run_one_real_server_
    group` -- warmup groups run identically but never enter the returned
    `p50_ms`/`p95_ms`/`wall_ms`/`cpu_client_ms`/`requests`/`client_
    processes` (its completion condition 137, the same warmup/measured split
    `_measure_op` already applies to the 6 registered plugs). Any non-200
    status anywhere -- warmup or measured -- aborts the WHOLE run
    (its completion condition 143): no `REALPERF`/`REALCPU` line is ever
    built from a partially-failed measurement. `requests` is the number
    of MEASURED responses this run actually observed, never `n *
    concurrency`'s own formula alone -- a run that observed fewer than
    that (`OC` 1.5-32, the same guard its completion condition 167's own
    K=1 check already applies) aborts too, refusing to print a row that
    undercounts its own measurement. `client_processes` is the FIRST
    measured group's own observed distinct child-process count (`_run_
    one_real_server_group`'s own `client_processes`), never the caller's
    precomputed `n_children` -- a regression that spawns fewer real
    child processes than `n_children` says is now visible in the printed
    row, not just in an unobserved argument."""
    measured_wall_ms: "list[float]" = []
    cpu_client_ms_total = 0.0
    measured_requests = 0
    client_processes: "int | None" = None
    for index in range(warmup + n):
        is_warmup = index < warmup
        group = _run_one_real_server_group(query_url, bearer, field, counts, n_children)
        for status in group["statuses"]:
            if status != 200:
                raise RealServerMeasurementFailure(f"query response status {status} (expected 200)")
        if not is_warmup:
            measured_wall_ms.append(group["wall_ms"])
            cpu_client_ms_total += group["cpu_client_ms"]
            measured_requests += len(group["statuses"])
            if client_processes is None:
                client_processes = group["client_processes"]
    expected_requests = n * concurrency
    if measured_requests < expected_requests:
        raise RealServerMeasurementFailure(
            f"measured only {measured_requests} query responses, expected {expected_requests} "
            f"(n={n} x concurrency={concurrency}) -- refusing a short measurement"
        )
    sorted_wall_ms = sorted(measured_wall_ms)
    return {
        "n": len(measured_wall_ms),
        "p50_ms": _percentile(sorted_wall_ms, 50),
        "p95_ms": _percentile(sorted_wall_ms, 95),
        "wall_ms": sum(measured_wall_ms),
        "cpu_client_ms": cpu_client_ms_total,
        "requests": measured_requests,
        "client_processes": client_processes,
    }


def _measure_real_server_and_emit(launcher: Any, args: argparse.Namespace) -> None:
    """The work order's D-15's own full sequence, in order: rotate the launcher's own
    control credential (it starts `must_rotate=true`, and no other control-plane
    call succeeds until this runs) -> resolve `application_id` -> issue a
    developer credential (with the ROTATED control credential, never the
    original `control_bearer`) -> create the entity and seed its one row
    -> the K=1 sanity query -> the real `--client-processes`/`--
    concurrency` measurement -> print `REALPERF` then `REALCPU`, with
    nothing printed between or before them past `PERFRUN` (its
    completion condition 171 -- `main()` prints `PERFRUN` before this
    function is ever reached). Raises `RealServerMeasurementFailure`
    (never prints either line) for any failure along the way --
    `_run_real_server` is
    the one place that catches it."""
    rotated_control_bearer = _rotate_control_credential(launcher.control_base_url, launcher.control_bearer, launcher.control_credential_id)
    application_id = _resolve_application_id(launcher.data_base_url, launcher.runtime_bearer)
    developer_bearer = _issue_developer_credential(launcher.control_base_url, rotated_control_bearer, application_id)
    _prepare_real_server_entity(launcher.data_base_url, developer_bearer, _REAL_SERVER_ENTITY, _REAL_SERVER_FIELD)
    _confirm_first_query(launcher.data_base_url, launcher.runtime_bearer, _REAL_SERVER_ENTITY, _REAL_SERVER_FIELD)
    n_children = _num_real_server_clients(args.client_processes, args.concurrency)
    counts = _distribute_group_counts(args.concurrency, n_children)
    query_url = f"{launcher.data_base_url}/data/{_REAL_SERVER_ENTITY}/query"
    result = _measure_real_server(
        query_url=query_url, bearer=launcher.runtime_bearer, field=_REAL_SERVER_FIELD,
        warmup=args.warmup, n=args.n, concurrency=args.concurrency, n_children=n_children, counts=counts,
    )
    print(_format_realperf_row(args.real_server, args.concurrency, result["client_processes"], result["n"], result["p50_ms"], result["p95_ms"]))
    print(_format_realcpu_row(args.real_server, args.concurrency, result["client_processes"], result["requests"], result["wall_ms"], result["cpu_client_ms"]))


def _run_real_server(args: argparse.Namespace) -> int:
    """The work order's D-15: `--real-server`'s own entry point, called by `main()` in
    place of `_run` -- never both (its completion condition 144). Discovers
    and starts the launcher (`ceilings={"data": 1, "control": 1}`,
    its completion condition 128); a failure discovering/starting it (a
    registry lookup miss, for instance) is reported and returns 1, the
    same as a measurement failure below, never an uncaught traceback out
    of `main()`. Once started, `launcher.stop()` is ALWAYS called exactly
    once (its completion conditions 129/130), success or failure -- outside
    the second `try`, which wraps only the post-`start()` work, so a
    `start()` failure (which every launcher's own `start()` already
    resolves with its own internal `stop()` before re-raising) is never
    double-stopped."""
    _warm_forkserver()
    try:
        launcher_cls = _load_composition_root_class(args.registry, args.real_server)
        launcher = launcher_cls()
        launcher.start(ceilings={"data": 1, "control": 1})
    except RealServerMeasurementFailure as exc:
        print(f"perf_baseline: {exc}", file=sys.stderr)
        return 1
    try:
        _measure_real_server_and_emit(launcher, args)
    except RealServerMeasurementFailure as exc:
        print(f"perf_baseline: {exc}", file=sys.stderr)
        return 1
    finally:
        launcher.stop()
    return 0


def _run(args: argparse.Namespace) -> int:
    built = _discover_and_build(args.registry)
    exit_code = 0
    roundtrip = _roundtrip_enabled(args)
    admin_conn: Any = None
    try:
        if roundtrip:
            # R-80 (WO §1.2 D-1 (ii)): the harness's OWN admin connection
            # to the throwaway cluster's `postgres` db (never a plug's own
            # connection) -- opened only under `--roundtrip`, so a default
            # run never even dials it (completion condition 21a). `main()`
            # has already written the owned cluster's own env (including
            # `dsa_testpg.R2DB_DSN`, the SAME dsn value `MITATEDB_DSN`
            # carries) into `os.environ` by the time `_run` is reached.
            import psycopg

            admin_conn = psycopg.connect(os.environ[dsa_testpg.R2DB_DSN], autocommit=True)
        for name, adapter_obj in built:
            try:
                for row in _measure_plug(
                    name, adapter_obj, warmup=args.warmup, n=args.n, concurrency=args.concurrency,
                    prepared_detail=args.prepared_detail,
                    roundtrip=roundtrip, admin_conn=admin_conn,
                ):
                    print(_format_row(row))
            except (SelfCheckFailure, UnknownAdapterShape) as exc:
                print(f"perf_baseline: {exc}", file=sys.stderr)
                exit_code = 1
    finally:
        if admin_conn is not None:
            with contextlib.suppress(Exception):
                admin_conn.close()
        for _name, adapter_obj in built:
            with contextlib.suppress(Exception):
                adapter_obj.close()
    return exit_code


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.concurrency < 1:
        parser.error("--concurrency must be >= 1")
    if args.client_processes < 1:
        parser.error("--client-processes must be >= 1")
    if args.real_server and args.n < 1:
        # The work order's D-15 measures MEASURED groups only; at
        # `--n 0` `_measure_real_server`'s own `client_processes` is
        # never set (no measured group ever runs to set it), printing
        # `client_processes=None` -- refuse before that, the same way
        # `--concurrency`/`--client-processes` already refuse below 1.
        parser.error("--n must be >= 1 for --real-server")

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
                    # Work order `docs/work-orders/WORK_ORDER_R101_SERIALIZATION_ATTRIBUTION_V1.md`
                    # §7.3 D-15 (§9.2 completion condition 145): the
                    # `--real-server` path runs under the SAME exclusive lock
                    # and throwaway cluster as the 6-plug path below -- never
                    # both in one invocation (§9.2 completion condition 144).
                    if args.real_server:
                        return _run_real_server(args)
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
