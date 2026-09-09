"""tools/tests/test_perf_baseline.py -- pytest coverage for
tools/perf_baseline.py's own `_classify_plug` (Phase 10 WP-3, design
docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md D-12) and, from Phase 10
WP-7 onward, its `--concurrency K` dispatch (design D-8, work order
docs/work-orders/WORK_ORDER_PHASE10_DEPLOYMENT_EVIDENCE_V1.md WP-7).

Deliberately NOT under `conformance-tests/` and NOT discoverable by the
root suite: `tools/` is not in pyproject.toml's `[tool.pytest.ini_options]
testpaths` (same convention as `tools/tests/test_check_doc_refs.py`).
None of this file needs a real registered adapter/Postgres at all -- the
WP-7 tests below drive `perf_baseline.py`'s own dispatch primitives
(`_run_concurrent`, `_row`/`_format_row`, `_build_parser`) directly with
minimal fakes, never a real `ConformanceAdapter` or network call, exactly
like the pre-existing `_classify_plug` tests already do with `types.
SimpleNamespace`.

Run directly:
    ./.venv/bin/python -m pytest tools/tests/test_perf_baseline.py -q
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[1] / "perf_baseline.py"
_spec = importlib.util.spec_from_file_location("perf_baseline", _MODULE_PATH)
pb = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("perf_baseline", pb)
_spec.loader.exec_module(pb)  # type: ignore[union-attr]


def _fake(transport_kind: "str | None", **extra):
    if transport_kind is None:
        return SimpleNamespace(**extra)
    return SimpleNamespace(transport_kind=transport_kind, **extra)


def test_classify_plug_reads_the_declaration():
    """`_classify_plug` reads `adapter_obj.transport_kind` -- not the
    object's own attribute SHAPE (`_loop`/`_client`) -- to decide the
    printed transport label. The fake "socket" object below deliberately
    ALSO carries the `_loop`/`_client` attributes an ASGI plug's own
    client sets, to prove the classification follows the declaration, not
    the shape.

    mutation (`tools/perf_baseline.py`): revert `_classify_plug` to its
    pre-WP-3 form (classify by `hasattr(adapter_obj, "_loop")`/
    `"_client"` instead of reading `transport_kind`) -- this test goes
    red because the mutated code would misclassify the fake "socket"
    object below as `asgi-inprocess` (it has the ASGI attribute shape),
    never seeing its `socket`-declared `transport_kind` at all.
    """
    fake_socket_adapter = _fake("socket", _loop=object(), _client=object())
    peer, transport = pb._classify_plug("r2db-api-socket", fake_socket_adapter)
    assert peer == "r2db-api"
    assert transport == "socket"

    peer, transport = pb._classify_plug("r2db-api-http", _fake("asgi"))
    assert peer == "r2db-api"
    assert transport == "asgi-inprocess"

    peer, transport = pb._classify_plug("r2db-api", _fake("in_process"))
    assert peer == "r2db-api"
    assert transport == "in-process"

    peer, transport = pb._classify_plug("MitateDB-api-socket", _fake("socket"))
    assert peer == "MitateDB-api"
    assert transport == "socket"


def test_classify_plug_rejects_a_name_declaration_mismatch():
    """A plug whose registry name and declared `transport_kind` disagree
    is refused, never silently guessed (design D-12's own "従来どおり
    UnknownAdapterShapeで非0終了する")."""
    with pytest.raises(pb.UnknownAdapterShape):
        pb._classify_plug("r2db-api-http", _fake("in_process"))
    with pytest.raises(pb.UnknownAdapterShape):
        pb._classify_plug("r2db-api", _fake("asgi"))
    with pytest.raises(pb.UnknownAdapterShape):
        pb._classify_plug("r2db-api-socket", _fake("asgi"))


def test_classify_plug_rejects_an_undeclared_or_unrecognized_transport_kind():
    """A plug that declares no `transport_kind` at all, or a value outside
    the 3-word vocabulary, is refused -- never silently classified as
    `in-process` by default (the pre-port-v1.14 ABC had no such attribute
    to read at all)."""
    with pytest.raises(pb.UnknownAdapterShape):
        pb._classify_plug("r2db-api", SimpleNamespace())
    with pytest.raises(pb.UnknownAdapterShape):
        pb._classify_plug("r2db-api", _fake("carrier-pigeon"))


# ---------------------------------------------------------------------
# Phase 10 WP-7 -- `--concurrency K` (design D-8, work order WP-7).
# ---------------------------------------------------------------------


def _sleepy_factory(seconds: float) -> "Callable[[], object]":
    async def _one() -> None:
        await asyncio.sleep(seconds)

    def _factory() -> object:
        return _one()

    return _factory


def test_concurrency_issues_requests_simultaneously():
    """WP-7 completion condition 1: `_run_concurrent` fires a group's own
    members TOGETHER via one `asyncio.gather` call, not one after another.

    Three 60ms-sleep factories dispatched as ONE group of 3 must finish in
    close to 60ms, not close to 180ms.

    mutation (`tools/perf_baseline.py`): replace `_run_concurrent`'s own
    `await asyncio.gather(*(factory() for factory in group))` with a
    sequential loop (`for factory in group: await factory()`) -- this test
    goes red because a 3-member group would then take ~3x as long as a
    1-member group, failing the `< 2x` assertion below (chosen with slack
    above the ideal ~1x so ordinary scheduling jitter cannot flake it,
    while still being far under the ~3x a sequential-await regression
    would produce)."""
    loop = asyncio.new_event_loop()
    try:
        seconds = 0.06
        one_factory = _sleepy_factory(seconds)
        durations_single, _ = pb._run_concurrent(loop, [[one_factory]])
        durations_group, _ = pb._run_concurrent(loop, [[one_factory, one_factory, one_factory]])
    finally:
        loop.close()
    assert durations_group[0] < 2 * durations_single[0]


def test_k1_uses_the_same_path_as_kn():
    """WP-7 completion condition 2: a group of size 1 walks the identical
    `asyncio.gather` call `_run_concurrent` uses for any other group size
    -- never a separate, bypassing branch for the singleton case.

    mutation (`tools/perf_baseline.py`): special-case group-of-1 in `_run_
    concurrent` to `loop.run_until_complete(factory())` directly, skipping
    `asyncio.gather` entirely -- this test goes red because the spy below
    would then record zero `asyncio.gather` calls for the size-1 group."""
    calls: list[int] = []
    real_gather = asyncio.gather

    def _spy_gather(*aws, **kwargs):
        calls.append(len(aws))
        return real_gather(*aws, **kwargs)

    loop = asyncio.new_event_loop()
    factory = _sleepy_factory(0.001)
    try:
        pb.asyncio.gather = _spy_gather
        pb._run_concurrent(loop, [[factory]])
        pb._run_concurrent(loop, [[factory, factory, factory]])
    finally:
        pb.asyncio.gather = real_gather
        loop.close()
    assert calls == [1, 3], (
        f"expected one asyncio.gather call for the size-1 group and one for the size-3 group, got {calls!r} "
        "-- a size-1 group must go through the SAME asyncio.gather call other sizes do"
    )


def test_default_n_stays_under_the_rate_bound():
    """WP-7 completion condition 3: defaults are `--n 100 --warmup 10`
    (design D-8 (1)) -- at `--concurrency 3` this keeps `(n + warmup) *
    concurrency` (330) under the shared surface's default `requests_per_
    minute` bound (600); the pre-WP-7 default (`--n 200 --warmup 20`)
    would put that at 660, past the bound.

    mutation (`tools/perf_baseline.py`): restore the pre-WP-7 defaults
    (200/20) -- this test goes red directly on the asserted default
    values."""
    parser = pb._build_parser()
    assert parser.get_default("n") == 100
    assert parser.get_default("warmup") == 10
    assert parser.get_default("concurrency") == 1


def test_perf_row_format_is_stable():
    """WP-7 completion condition 4: every column `_format_row` printed
    before WP-7 keeps its exact name/order/formatting; `concurrency` is a
    NEW column appended at the end, never inserted between existing ones.

    mutation (`tools/perf_baseline.py`): rename an existing column in `_
    format_row` (e.g. `backend_calls` -> `calls`, or reorder `p50_ms`/
    `p95_ms`) -- this test goes red on the exact-string comparison below."""
    row = pb._row("r2db-api", "r2db-api-socket", "socket", "query", [1.0, 2.0, 3.0], [1.0, 1.0, 1.0], 3)
    line = pb._format_row(row)
    assert line == (
        "PERF peer=r2db-api plug=r2db-api-socket transport=socket op=query n=3 "
        "p50_ms=2.000 p95_ms=2.900 backend_calls=1.00 concurrency=3"
    )
