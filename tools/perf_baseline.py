#!/usr/bin/env python3
"""perf_baseline.py -- WP-5 R-12 performance baseline harness.

design: docs/design/PHASE8_EFFECTIVE_BOUNDS_AND_HYGIENE_V1.md D-6.
work order: docs/work-orders/WORK_ORDER_PHASE8_EFFECTIVE_BOUNDS_V1.md WP-5.

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
other than `unavailable` -- currently the two MitateDB peer plugs; a
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

Standard library only, at the top of this file (tools/ convention, see
`tools/public_value_scan.py`'s own module docstring) -- everything this
tool actually touches beyond the standard library (httpx, psycopg, ...)
arrives transitively through the conformance adapters it imports, never
as a new dependency of this file itself.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime
import importlib
import inspect
import json
import math
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Iterator

ROOT = Path(__file__).resolve().parents[1]
CONFORMANCE_TESTS_DIR = ROOT / "conformance-tests"
REGISTRY_PATH = CONFORMANCE_TESTS_DIR / "registry.json"

if str(CONFORMANCE_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(CONFORMANCE_TESTS_DIR))

from adapter import (  # noqa: E402  (path insertion above must run first)
    BatchOperation,
    ConformanceAdapter,
    ScopedBatchOperation,
    fresh_identifier,
)

_BATCH_OPS = 5  # design D-6 decision 1: batch op count is fixed at 5.
_CROSS_ENTITY_OPS = 2  # not fixed by design; this tool's own choice -- see
# the completion report's "design との食い違い" section (2 entities, 1
# insert each, the smallest request that is genuinely cross-entity).


class SelfCheckFailure(RuntimeError):
    """Raised when the backend-call counting proxy observed zero calls for
    a `query` request -- the one non-emptiness self-check this tool
    performs (work order WP-5 completion condition 1). `main()` turns
    this into a non-zero exit, never a silent pass."""


class UnknownAdapterShape(RuntimeError):
    """Raised when a registered plug's registry name and its built
    adapter object's own structural shape disagree about which of the two
    forms this tool currently knows how to classify (WP-5 rework ruling
    item 4). `main()` turns this into a non-zero exit, never a silent
    guess -- see `_classify_plug`'s own docstring for why guessing here is
    unsafe (a real socket plug, L7-2, could plausibly reuse the same httpx
    client shape an ASGI plug uses)."""


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


def _classify_plug(plug_name: str, adapter_obj: ConformanceAdapter) -> tuple[str, str]:
    """Returns `(peer, transport)` for one registered plug.

    WP-5 rework ruling item 4: this used to be two separate functions
    (`_peer_of` deriving the peer column from the name string alone,
    `_transport_of` deriving the transport column from the built object's
    attribute shape alone) that silently fell back to `in-process`/the
    name unchanged for anything that did not match. That is unsafe: a
    real socket plug (L7-2) whose httpx client also happens to set
    `_loop`/`_client` (very plausible -- a real-socket httpx transport is
    still an httpx client) would get mislabeled `asgi-inprocess`, and if
    its registry name does not end in '-http' (e.g. a '-socket' suffix)
    it would also get a stray brand-new peer column instead of being
    grouped with its own in-process sibling. Both used to happen with no
    error -- a wrong row would simply be printed into a public record.

    This tool currently knows exactly two shapes, and now REQUIRES the
    name and the object's own attributes to agree about which one a plug
    is, refusing (raising `UnknownAdapterShape`, turned into a non-zero
    exit by `main()`) anything else rather than guessing:

    - in-process: registry name has no '-http' suffix AND the built
      adapter object exposes neither `_loop` nor `_client`.
    - asgi-inprocess: registry name ends in '-http' AND the built adapter
      object exposes both `_loop` and `_client` (every currently
      registered HTTP plug's own ASGITransport-backed httpx client, set
      in `__init__`).

    Extend this function explicitly -- do not just widen the fallback --
    when L7-2 registers its first real socket plug; see
    `tools/PERF_BASELINE_README.md`."""
    has_http_shape = hasattr(adapter_obj, "_loop") and hasattr(adapter_obj, "_client")
    is_http_name = plug_name.endswith(_HTTP_NAME_SUFFIX)
    if is_http_name and has_http_shape:
        return plug_name[: -len(_HTTP_NAME_SUFFIX)], "asgi-inprocess"
    if not is_http_name and not has_http_shape:
        return plug_name, "in-process"
    raise UnknownAdapterShape(
        f"{plug_name}: registry name has a '-http' suffix ({is_http_name}) but the built "
        f"adapter object's own httpx-client shape (_loop/_client present) is {has_http_shape} -- "
        "these disagree, so this tool refuses to guess a peer/transport label for it "
        "(this tool currently only knows the plain in-process shape and the '-http' + "
        "ASGITransport httpx-client shape; see tools/PERF_BASELINE_README.md)"
    )


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


def _measure(fn: Callable[[], None], *, warmup: int, n: int, counter: _CallCounter) -> tuple[list[float], list[int]]:
    import time

    for _ in range(warmup):
        fn()
    durations_ms: list[float] = []
    call_counts: list[int] = []
    for _ in range(n):
        before = counter.count
        t0 = time.perf_counter()
        fn()
        t1 = time.perf_counter()
        durations_ms.append((t1 - t0) * 1000.0)
        call_counts.append(counter.count - before)
    return durations_ms, call_counts


def _row(peer: str, plug: str, transport: str, op: str, durations_ms: list[float], calls: list[int]) -> dict:
    """`n` is the ACTUAL number of samples `_measure` collected
    (`len(durations_ms)`), never the raw `--n` CLI argument passed
    straight through -- WP-5 rework ruling item 1. A CLI-argument
    pass-through cannot detect a `_measure` change (e.g. warmup samples
    leaking into the measured set) that shifts the real sample count,
    because the printed `n=` would stay whatever `--n` said regardless of
    what was actually aggregated."""
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
    }


def _format_row(row: dict) -> str:
    return (
        f"PERF peer={row['peer']} plug={row['plug']} transport={row['transport']} "
        f"op={row['op']} n={row['n']} p50_ms={row['p50_ms']:.3f} "
        f"p95_ms={row['p95_ms']:.3f} backend_calls={row['backend_calls']:.2f}"
    )


# ---------------------------------------------------------------------
# one plug's own full measurement
# ---------------------------------------------------------------------


def _measure_plug(name: str, adapter_obj: ConformanceAdapter, *, warmup: int, n: int) -> list[dict]:
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

            durations, calls = _measure(_do_query, warmup=warmup, n=n, counter=counter)
            query_row = _row(peer, name, transport, "query", durations, calls)
            rows.append(query_row)
            _run_self_check(name, calls)

            # --- mutate ---
            # WP-5 rework ruling item 2: every value `fresh_identifier`
            # would generate is materialized into a plain list BEFORE
            # `_measure` starts timing anything -- the measured closure
            # below only indexes into it. A generator expression handed
            # straight to `iter()` looks pre-built but is not: its body
            # (the `fresh_identifier()` call) still runs lazily on each
            # `next()`, i.e. inside the timed window, which is exactly the
            # defect this ruling item corrects.
            mutate_runtime = adapter_obj.authenticate(adapter_obj.issue_credential(app_id, "runtime"))
            mutate_values = [fresh_identifier("perfmv") for _ in range(warmup + n)]
            mutate_values_iter = iter(mutate_values)

            def _do_mutate() -> None:
                adapter_obj.insert(mutate_runtime, entity, {"label": next(mutate_values_iter)})

            durations, calls = _measure(_do_mutate, warmup=warmup, n=n, counter=counter)
            rows.append(_row(peer, name, transport, "mutate", durations, calls))

            # --- batch (5 operations, design D-6 decision 1) ---
            batch_runtime = adapter_obj.authenticate(adapter_obj.issue_credential(app_id, "runtime"))
            # Pre-build every operation list OUTSIDE the timed window (audit
            # WP-5 finding: constructing the BatchOperation objects inside the
            # closure cost 2.4-4.7% of the in-process p50) -- the timed region
            # is the adapter call alone.
            batch_ops_per_call = [
                [
                    BatchOperation(operation="insert", values={"label": fresh_identifier("perfbv")})
                    for _ in range(_BATCH_OPS)
                ]
                for _ in range(warmup + n)
            ]
            batch_ops_iter = iter(batch_ops_per_call)

            def _do_batch() -> None:
                adapter_obj.attempt_batch_with_addresses(batch_runtime, entity, next(batch_ops_iter))

            durations, calls = _measure(_do_batch, warmup=warmup, n=n, counter=counter)
            rows.append(_row(peer, name, transport, "batch", durations, calls))

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
                    for _ in range(warmup + n)
                ]
                cross_ops_iter = iter(cross_ops_per_call)

                def _do_cross_entity() -> None:
                    adapter_obj.attempt_cross_entity_batch(cross_runtime, next(cross_ops_iter))

                durations, calls = _measure(_do_cross_entity, warmup=warmup, n=n, counter=counter)
                rows.append(_row(peer, name, transport, "cross_entity", durations, calls))
        return rows
    finally:
        with contextlib.suppress(Exception):
            adapter_obj.deprovision_application(app_id)


def _run_self_check(plug_name: str, query_calls: list[int]) -> None:
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--n", type=int, default=200, help="measured iterations per (plug, op) (default: 200)")
    parser.add_argument("--warmup", type=int, default=20, help="warmup iterations per (plug, op), not measured (default: 20)")
    parser.add_argument(
        "--registry", type=Path, default=REGISTRY_PATH,
        help="override registry.json path (scratchpad testing only -- conformance-tests/registry.json itself is never written by this tool)",
    )
    args = parser.parse_args(argv)

    print(_perfrun_line())

    built = _discover_and_build(args.registry)
    exit_code = 0
    try:
        for name, adapter_obj in built:
            try:
                for row in _measure_plug(name, adapter_obj, warmup=args.warmup, n=args.n):
                    print(_format_row(row))
            except (SelfCheckFailure, UnknownAdapterShape) as exc:
                print(f"perf_baseline: {exc}", file=sys.stderr)
                exit_code = 1
    finally:
        for _name, adapter_obj in built:
            with contextlib.suppress(Exception):
                adapter_obj.close()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
