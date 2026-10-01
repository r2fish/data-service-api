"""tools/tests/test_perf_baseline.py -- pytest coverage for
tools/perf_baseline.py's own `_classify_plug` (Phase 10 WP-3, design
docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md D-12) and, from Phase 10
WP-7 onward, its `--concurrency K` dispatch (design D-8, work order
docs/work-orders/WORK_ORDER_PHASE10_DEPLOYMENT_EVIDENCE_V1.md WP-7).

From R-80 onward, also covers the `ROUNDTRIP` lines (docs/work-orders/
WORK_ORDER_R80_ROUNDTRIP_MEASUREMENT_V1.md §1.2 D-1, §2.2) -- format,
pre/post diffing, the `pg_stat_database` confirm-wait poll, and the
`--roundtrip` flag gate. All of it via stubs/fakes, exactly like the
R-78/R-79 tests above: no real registered adapter or PostgreSQL.

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
import contextlib
import importlib.util
import itertools
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
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


def test_pool_row_format_is_stable_for_a_role_pool_entry():
    """`_format_pool_row`'s ROLE-shaped column names/order/formatting for a
    role pool's `stats()` dict (six keys, `size`/`in_use_peak` present) --
    the shape both peers' role pools print.

    mutation M8 (`tools/perf_baseline.py`): rename one column (e.g.
    `wait_max_ms=` -> `max_wait_ms=`) -- this test goes red on the
    exact-string comparison below."""
    stats = {
        "size": 4, "acquire_count": 7, "wait_count": 2,
        "wait_total_ms": 12.5, "wait_max_ms": 9.25, "in_use_peak": 3,
    }
    line = pb._format_pool_row("r2db-api", "r2db-api-http", "query", "app1/runtime", stats)
    assert line == (
        "POOL peer=r2db-api plug=r2db-api-http op=query role=app1/runtime "
        "size=4 acquire=7 waits=2 wait_total_ms=12.500 wait_max_ms=9.250 in_use_peak=3"
    )


def test_pool_row_format_is_stable_for_a_schema_lock_entry():
    """`_format_pool_row`'s SCHEMA LOCK column names/order/formatting for a
    `PostgresBackend.schema_lock_stats()`-shaped dict (four keys, no `size`
    / `in_use_peak`) -- `schema_lock=` replaces `role=` and there is no
    `size=`/`in_use_peak=` column, since neither concept applies to a lock.
    The shape is chosen by the keys alone: the same peer, plug and op print
    a role row for a six-key dict.

    mutation V75 (`tools/perf_baseline.py`): print the schema lock shape
    with the role row's `role=` label -- this test goes red on the
    exact-string comparison below."""
    stats = {"acquire_count": 5, "wait_count": 1, "wait_total_ms": 3.0, "wait_max_ms": 3.0}
    line = pb._format_pool_row("MitateDB-api", "MitateDB-api-http", "mutate", "app1", stats)
    assert line == (
        "POOL peer=MitateDB-api plug=MitateDB-api-http op=mutate schema_lock=app1 "
        "acquire=5 waits=1 wait_total_ms=3.000 wait_max_ms=3.000"
    )
    role_stats = {
        "size": 4, "acquire_count": 5, "wait_count": 0, "wait_total_ms": 0.0, "wait_max_ms": 0.0, "in_use_peak": 1,
    }
    role_line = pb._format_pool_row("MitateDB-api", "MitateDB-api-http", "mutate", "app1/runtime", role_stats)
    assert role_line.startswith("POOL peer=MitateDB-api plug=MitateDB-api-http op=mutate role=app1/runtime size=4 ")
    assert "schema_lock=" not in role_line


def test_pool_row_refuses_a_stats_dict_of_a_third_shape():
    """A dict with neither a role pool's keys nor a schema lock's four is
    refused with `KeyError`, not printed in the nearest shape."""
    with pytest.raises(KeyError):
        pb._format_pool_row("MitateDB-api", "MitateDB-api-http", "query", "app1", {"hits": 3})
    with pytest.raises(KeyError):
        pb._format_pool_row("MitateDB-api", "MitateDB-api-http", "query", "app1", {"size": 2, "acquire_count": 1})


def test_emit_pool_rows_prints_nothing_when_the_plug_has_no_pool_stats():
    """R-78 completion condition 8: a plug without `pool_stats` (every
    plug this WP does not touch) is silently skipped -- no `POOL` line at
    all, and no exception."""
    stub = SimpleNamespace(transport_kind="in_process")
    pb._emit_pool_rows("r2db-api", "r2db-api", "query", stub)


def test_emit_pool_rows_prints_a_line_per_entry_even_for_a_socket_transport_plug(capsys):
    """R-78 completion condition 10: a stub declaring `transport_kind ==
    "socket"` (a socket-transport plug) still gets its `POOL` line(s) --
    there is no transport this tool skips (monitor 裁定 2026-09-23).

    mutation M9 (`tools/perf_baseline.py`): make `_emit_pool_rows` return
    early for any plug name ending in `-socket` -- this test's stub plug
    is named `r2db-api-socket`, so the assertion below (a POOL line is
    printed) goes red."""
    stub = SimpleNamespace(
        transport_kind="socket",
        pool_stats=lambda: {"app1/runtime": {
            "size": 2, "acquire_count": 1, "wait_count": 0, "wait_total_ms": 0.0, "wait_max_ms": 0.0, "in_use_peak": 1,
        }},
    )
    pb._emit_pool_rows("r2db-api", "r2db-api-socket", "query", stub)
    out = capsys.readouterr().out
    assert out.count("POOL ") == 1
    assert "role=app1/runtime" in out


def test_prepared_detail_flag_defaults_to_false():
    """R-79 (WO §1.2 D-3, completion condition 19): `--prepared-detail` is
    off by default -- `PREPSTMT` lines are opt-in."""
    parser = pb._build_parser()
    assert parser.get_default("prepared_detail") is False
    args = parser.parse_args(["--prepared-detail"])
    assert args.prepared_detail is True


def test_prepared_row_format_is_stable():
    """R-79 completion condition 18: `_format_prepared_row`'s own column
    names/order/formatting -- `executes=`/`executemany=` (never
    `statements=`, design review 1 M-7), `share` = `prepared_execs /
    executes` printed `0.000`-formatted.

    mutation M18 (`tools/perf_baseline.py`): rename one column (e.g.
    `prepared_execs=` -> `execs=`) -- this test's own exact-string
    comparison goes red."""
    conn_stats = {
        "label": "app1/runtime@4242", "execute_count": 8, "executemany_count": 0,
        "prepared": 1, "prepared_execs": 3,
    }
    line = pb._format_prepared_row("r2db-api", "r2db-api-http", "query", conn_stats)
    assert line == (
        "PREPARED peer=r2db-api plug=r2db-api-http op=query conn=app1/runtime@4242 "
        "executes=8 executemany=0 prepared=1 prepared_execs=3 share=0.375"
    )


def test_prepared_row_share_is_zero_when_executes_is_zero():
    """R-79 completion condition 18: `share` is `0.000` (never a
    `ZeroDivisionError`) when a connection's own `execute_count` is 0 --
    a freshly-opened connection this op never used."""
    conn_stats = {
        "label": "app1/runtime@1", "execute_count": 0, "executemany_count": 0,
        "prepared": 0, "prepared_execs": 0,
    }
    line = pb._format_prepared_row("r2db-api", "r2db-api-http", "query", conn_stats)
    assert line.endswith("share=0.000")


def test_prepstmt_row_format_collapses_whitespace():
    """R-79 completion condition 19: `_format_prepstmt_row`'s own `stmt=`
    collapses every run of whitespace in the statement's own text to a
    single space."""
    stmt = {"name": "_pg3_0", "generic_plans": 2, "custom_plans": 1, "statement": "SELECT   1\n   WHERE $1 = $2"}
    line = pb._format_prepstmt_row("r2db-api", "r2db-api-http", "query", "app1/runtime@4242", stmt)
    assert line == (
        "PREPSTMT peer=r2db-api plug=r2db-api-http op=query conn=app1/runtime@4242 "
        "name=_pg3_0 generic=2 custom=1 stmt=SELECT 1 WHERE $1 = $2"
    )


def test_emit_prepared_rows_prints_nothing_when_the_plug_has_no_prepared_stats():
    """R-79 (mirrors R-78's `test_emit_pool_rows_prints_nothing_when_the_
    plug_has_no_pool_stats` immediately above): a plug without `prepared_
    stats` is silently skipped -- no `PREPARED` line, no exception."""
    stub = SimpleNamespace(transport_kind="in_process")
    pb._emit_prepared_rows("r2db-api", "r2db-api", "query", stub, detail=True)


def test_emit_prepared_rows_prints_prepstmt_lines_only_with_detail_flag(capsys):
    """R-79 completion condition 19: `PREPSTMT` lines print only when
    `detail=True` -- never otherwise, even when the connection dict
    carries `prepared_statements`.

    mutation M19 (`tools/perf_baseline.py`): make `_emit_prepared_rows`
    print `PREPSTMT` lines unconditionally, regardless of `detail` --
    this test's own `detail=False` branch (`PREPSTMT count == 0`) goes
    red."""
    stub = SimpleNamespace(
        transport_kind="in_process",
        prepared_stats=lambda: [{
            "label": "app1/runtime@1", "execute_count": 6, "executemany_count": 0,
            "prepared": 1, "prepared_execs": 1,
            "prepared_statements": [
                {"name": "_pg3_0", "generic_plans": 0, "custom_plans": 1, "statement": "SELECT 1"},
            ],
        }],
    )
    pb._emit_prepared_rows("r2db-api", "r2db-api", "query", stub, detail=False)
    out = capsys.readouterr().out
    assert out.count("PREPARED ") == 1
    assert out.count("PREPSTMT ") == 0

    pb._emit_prepared_rows("r2db-api", "r2db-api", "query", stub, detail=True)
    out = capsys.readouterr().out
    assert out.count("PREPARED ") == 1
    assert out.count("PREPSTMT ") == 1


def test_emit_prepared_rows_prints_for_socket_transport_plug(capsys):
    """R-79 completion condition 20: a stub declaring `transport_kind ==
    "socket"` still gets its `PREPARED` line(s) -- there is no transport
    this tool skips (mirrors R-78's own identical POOL-line test above).

    mutation M20 (`tools/perf_baseline.py`): make `_emit_prepared_rows`
    return early for any plug name ending in `-socket` -- this test's
    own stub plug is named `r2db-api-socket`, so the assertion below (a
    `PREPARED` line is printed) goes red."""
    stub = SimpleNamespace(
        transport_kind="socket",
        prepared_stats=lambda: [{
            "label": "app1/runtime@1", "execute_count": 1, "executemany_count": 0,
            "prepared": 0, "prepared_execs": 0, "prepared_statements": [],
        }],
    )
    pb._emit_prepared_rows("r2db-api", "r2db-api-socket", "query", stub, detail=False)
    out = capsys.readouterr().out
    assert out.count("PREPARED ") == 1


def test_emit_measurement_rows_prints_pool_lines_before_prepared_lines(capsys):
    """R-79 (WO §1.2 D-3, rework item (C)): `_emit_measurement_
    rows` -- the ONE call site `_measure_plug` itself uses per (plug, op)
    -- prints a (plug, op)'s own `POOL` line(s) BEFORE its `PREPARED`
    line(s), never the other way around. Calls the real function under
    test directly (not a re-typed copy of its own two calls), so this
    observes `_measure_plug`'s own actual emit order, not merely this
    test's own assumption about it.

    mutation M24 (`tools/perf_baseline.py`): swap the two calls inside
    `_emit_measurement_rows` (`_emit_prepared_rows` before `_emit_pool_
    rows`) -- this test's own `pool_idx < prepared_idx` assertion goes
    red (`PREPARED ` now prints first)."""
    stub = SimpleNamespace(
        transport_kind="in_process",
        pool_stats=lambda: {"app1/runtime": {
            "size": 2, "acquire_count": 1, "wait_count": 0, "wait_total_ms": 0.0, "wait_max_ms": 0.0, "in_use_peak": 1,
        }},
        prepared_stats=lambda: [{
            "label": "app1/runtime@1", "execute_count": 1, "executemany_count": 0,
            "prepared": 0, "prepared_execs": 0, "prepared_statements": [],
        }],
    )
    pb._emit_measurement_rows("r2db-api", "r2db-api", "query", stub, prepared_detail=False)
    out = capsys.readouterr().out
    pool_idx = out.index("POOL ")
    prepared_idx = out.index("PREPARED ")
    assert pool_idx < prepared_idx


_FAKE_CLUSTER_ENV = {
    "R2DB_TEST_ADMIN_DSN": "host=/fake/s port=5432 dbname=postgres user=postgres",
    "MITATEDB_TEST_ADMIN_DSN": "host=/fake/s port=5432 dbname=postgres user=postgres",
    "PGHOST": "/fake/s", "PGPORT": "5432", "PGUSER": "postgres", "PGPASSFILE": "/fake/pgpass",
}


def test_perf_baseline_takes_the_exclusive_lock_and_uses_its_own_cluster(tmp_path, monkeypatch):
    """WP-2 (docs/work-orders/WORK_ORDER_R44_TEST_PG_ISOLATION_V1.md §3.1
    table row 8): perf_baseline.py takes the exclusive suite lock around its
    own measurement run AND measures against its own dedicated cluster, not
    whatever `R2DB_TEST_ADMIN_DSN`/`PGHOST` etc. happened to already be in
    the environment (review test-gap 6: a prior version of this test faked
    `Cluster.env()` as `{}`, so nothing distinguished "used the cluster's
    own connection env" from "used none at all").

    Lock: proven from a second process's shared acquisition timing out
    against the SAME (tmp_path, never the machine's real per-uid) base dir
    while `main()` is "running" (the fake cluster's own context manager does
    the probe synchronously, since the exclusive lock is already held by the
    time `dsa_testpg.cluster()` is even reached).
    Dedicated cluster: `_run` (the actual measurement entry point) is spied
    on to capture `os.environ` at the moment it is called, and asserted to
    carry the fake cluster's own `PGHOST`/`PGPASSFILE`/DSNs -- not whatever
    `main()` was invoked with.
    `--registry` points at an empty adapters list so no real adapter/
    Postgres is ever touched.

    mutation 1 (`tools/perf_baseline.py`): remove the `with dsa_testpg.
    suite_lock(...):` wrapper in `main()` -- red because the probe
    subprocess's shared acquisition would then succeed (exit 0) instead of
    timing out (exit 75).
    mutation 2 (`tools/perf_baseline.py`): drop `os.environ.update(c.env())`
    -- red because `seen_env` would then miss the fake cluster's own
    `PGHOST`/`PGPASSFILE`.
    """
    base = tmp_path / "base"
    base.mkdir()
    monkeypatch.setattr(pb.dsa_testpg, "_base_dir", lambda *a, **k: base)

    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"adapters": []}), encoding="utf-8")

    script = (
        "import pathlib, sys; sys.path.insert(0, %r); import dsa_testpg\n"
        "try:\n"
        "    with dsa_testpg.suite_lock(False, 0.3, base=pathlib.Path(%r)):\n"
        "        pass\n"
        "except dsa_testpg.TestPgError:\n"
        "    sys.exit(75)\n"
        "sys.exit(0)\n"
    ) % (str(pb.TESTPG_DIR), str(base))

    class _FakeCluster:
        def env(self):
            return dict(_FAKE_CLUSTER_ENV)

    @contextlib.contextmanager
    def fake_cluster():
        probe = subprocess.run([sys.executable, "-c", script])
        assert probe.returncode == 75, (
            "a second process's shared acquisition must time out while perf_baseline holds the exclusive lock"
        )
        yield _FakeCluster()

    monkeypatch.setattr(pb.dsa_testpg, "cluster", fake_cluster)

    seen_env: dict[str, str] = {}
    real_run = pb._run

    def spy_run(args):
        seen_env.update(os.environ)
        return real_run(args)

    monkeypatch.setattr(pb, "_run", spy_run)

    code = pb.main(["--registry", str(registry)])
    assert code == 0
    for key, value in _FAKE_CLUSTER_ENV.items():
        assert seen_env.get(key) == value, f"_run saw {key}={seen_env.get(key)!r}, expected the cluster's own {value!r}"
    # The exclusive lock is released on the way out: a fresh shared acquisition now succeeds.
    handle = pb.dsa_testpg._acquire_suite_lock(exclusive=False, wait=1.0, base=base)
    handle.release()


def _fake_cluster_cm():
    class _FakeCluster:
        def env(self):
            return dict(_FAKE_CLUSTER_ENV)

    @contextlib.contextmanager
    def fake_cluster():
        yield _FakeCluster()

    return fake_cluster


def test_perf_baseline_restores_the_environment_it_borrowed(tmp_path, monkeypatch):
    """R-58 WP-1 completion condition 1 (docs/work-orders/
    WORK_ORDER_R58_PERF_BASELINE_ENV_RESTORE_V1.md §2.2): `main()` writes
    the owned cluster's own connection env directly into `os.environ` (the
    two DSN names, `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSFILE`, and drops
    `PGPASSWORD`) so `_run()`'s adapters can reach it, but must put the
    caller's own process state back once the cluster is no longer live:
    names that existed before the call (`PGPASSWORD`/`PGPASSFILE`,
    sentineled here) keep their exact sentinel value afterward, and names
    the cluster added that were absent before (`PGHOST`, `PGPORT`,
    `PGUSER`, the two DSN names) are absent again.

    M1 (`tools/perf_baseline.py`, docs/work-orders/
    WORK_ORDER_R58_PERF_BASELINE_ENV_RESTORE_V1.md §2.3): drop the
    `finally` restore loop entirely -- red because the sentinel
    `PGPASSWORD`/`PGPASSFILE` values are gone and the fake cluster's own
    DSN names are still present after `main()` returns.
    M1b (`tools/perf_baseline.py`, same work order §2.3): restore every
    borrowed name except `PGPASSWORD` -- red because `PGPASSWORD` stays
    absent (`main()` popped it) instead of coming back as the sentinel.
    """
    base = tmp_path / "base"
    base.mkdir()
    monkeypatch.setattr(pb.dsa_testpg, "_base_dir", lambda *a, **k: base)

    for name in _FAKE_CLUSTER_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PGPASSWORD", "sentinel-password")
    monkeypatch.setenv("PGPASSFILE", "sentinel-pgpassfile")

    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"adapters": []}), encoding="utf-8")

    monkeypatch.setattr(pb.dsa_testpg, "cluster", _fake_cluster_cm())

    code = pb.main(["--registry", str(registry)])
    assert code == 0

    observed = 0
    assert os.environ.get("PGPASSWORD") == "sentinel-password"
    observed += 1
    assert os.environ.get("PGPASSFILE") == "sentinel-pgpassfile"
    observed += 1
    for name in _FAKE_CLUSTER_ENV:
        if name == "PGPASSFILE":
            continue  # sentineled and checked above; the fake cluster's own value must not survive it either
        assert name not in os.environ, f"{name} leaked the fake cluster's own value after main() returned"
        observed += 1
    assert observed == len(_FAKE_CLUSTER_ENV) + 1


@pytest.mark.parametrize(
    "raiser,expected_code",
    [
        (lambda args: (_ for _ in ()).throw(RuntimeError("synthetic failure from _run")), None),
        (lambda args: (_ for _ in ()).throw(pb.dsa_testpg.TestPgError("synthetic")), 1),
    ],
)
def test_perf_baseline_restores_the_environment_when_run_raises(tmp_path, monkeypatch, raiser, expected_code):
    """R-58 WP-1 completion condition 2 (docs/work-orders/
    WORK_ORDER_R58_PERF_BASELINE_ENV_RESTORE_V1.md §2.2): the same restore
    as the previous test's completion condition 1 also happens when
    `_run()` raises -- both a plain exception (propagates out of `main()`)
    and a `dsa_testpg.TestPgError` (caught by `main()`'s own outer
    `except`, returning 1 since the failure is past the `lock` stage).

    M2 (`tools/perf_baseline.py`, docs/work-orders/
    WORK_ORDER_R58_PERF_BASELINE_ENV_RESTORE_V1.md §2.3): move the restore
    loop from `finally` to after `return _run(args)` on the success path
    only -- red because both parametrizations here leak the fake
    cluster's own `PGHOST`/DSN names (the restore never runs on either
    exception path).
    """
    base = tmp_path / "base"
    base.mkdir()
    monkeypatch.setattr(pb.dsa_testpg, "_base_dir", lambda *a, **k: base)

    for name in _FAKE_CLUSTER_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PGPASSWORD", "sentinel-password-2")

    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"adapters": []}), encoding="utf-8")

    monkeypatch.setattr(pb.dsa_testpg, "cluster", _fake_cluster_cm())
    monkeypatch.setattr(pb, "_run", raiser)

    if expected_code is None:
        with pytest.raises(RuntimeError, match="synthetic failure from _run"):
            pb.main(["--registry", str(registry)])
    else:
        assert pb.main(["--registry", str(registry)]) == expected_code

    observed = 0
    assert os.environ.get("PGPASSWORD") == "sentinel-password-2"
    observed += 1
    for name in _FAKE_CLUSTER_ENV:
        assert name not in os.environ, f"{name} leaked the fake cluster's own value after main() raised"
        observed += 1
    assert observed == len(_FAKE_CLUSTER_ENV) + 1


# ---------------------------------------------------------------------
# R-80 -- ROUNDTRIP lines (WO §1.2 D-1, §2.2).
# ---------------------------------------------------------------------


def test_roundtrip_conn_row_format_is_stable():
    """WO §2.2 completion condition 1: `_format_roundtrip_conn_row`'s own
    column names/order/formatting -- `peer`/`plug`/`op`/`requests`/`conn`/
    `stmts`/`stmts_per_req`.

    mutation M1 (`tools/perf_baseline.py`): rename a column in `_format_
    roundtrip_conn_row` (e.g. `stmts_per_req=` -> `per_req=`) -- this
    test's own exact-string comparison goes red."""
    line = pb._format_roundtrip_conn_row("r2db-api", "r2db-api-http", "query", 10, "app1/runtime@42", 6)
    assert line == (
        "ROUNDTRIP peer=r2db-api plug=r2db-api-http op=query requests=10 "
        "conn=app1/runtime@42 stmts=6 stmts_per_req=0.60"
    )


def test_roundtrip_db_row_format_is_stable():
    """WO §2.2 completion condition 2: `_format_roundtrip_db_row`'s own
    column names/order/formatting -- `peer`/`plug`/`op`/`requests`/`db`/
    `xacts`/`xacts_per_req`/`sessions`/`sessions_per_req`/`stale`, `db`
    being one of the two literal words `app`/`platform`.

    mutation M2 (`tools/perf_baseline.py`): rename a column (e.g.
    `sessions_per_req=` -> `sess_per_req=`) -- this test's own exact-
    string comparison goes red."""
    line = pb._format_roundtrip_db_row("r2db-api", "r2db-api-http", "query", 10, "app", 12, 3, False)
    assert line == (
        "ROUNDTRIP peer=r2db-api plug=r2db-api-http op=query requests=10 "
        "db=app xacts=12 xacts_per_req=1.20 sessions=3 sessions_per_req=0.30 stale=0"
    )
    line = pb._format_roundtrip_db_row("MitateDB-api", "MitateDB-api-http", "query", 10, "platform", 1, 1, True)
    assert line.endswith("stale=1")


def test_roundtrip_probes_prepared_stats_exactly_three_times_per_op(capsys):
    """WO §2.2 completion condition 3 (design review 1 M-3), updated by
    R-101 WP-1 completion condition 50: a `--roundtrip` op calls `prepared_
    stats()` exactly three times -- the ROUNDTRIP PRE baseline (`_roundtrip_
    pre_probe`), a separate DBTIME PRE snapshot inside `_measure_op` itself
    (taken after warmup, before the measured window), and the ONE shared
    POST call `_emit_measurement_rows` makes for `DBTIME scope=app` and
    `PREPARED` together -- and the `ROUNDTRIP conn=` lines are built from
    that SAME POST return value, never a fourth call.

    mutation M3 (`tools/perf_baseline.py`): call `prepared_stats()` once
    more for the `ROUNDTRIP` lines instead of reusing the shared POST
    value -- this test's own `len(call_log) == 3` assertion goes red (4
    calls instead of 3)."""
    call_log: list[int] = []

    def prepared_stats():
        call_log.append(1)
        return [{
            "label": "app1/runtime@1", "execute_count": len(call_log), "executemany_count": 0,
            "prepared": 0, "prepared_execs": 0, "prepared_statements": [], "probed": True,
        }]

    stub = SimpleNamespace(transport_kind="in_process", prepared_stats=prepared_stats)
    pb._measure_op_and_emit(
        lambda: None, peer="r2db-api", plug="r2db-api", op="query",
        warmup=0, n=1, concurrency=1, counter=pb._CallCounter(), adapter_obj=stub,
        prepared_detail=False, roundtrip_enabled=True, admin_conn=None, db_names={},
        correction_matcher=None, min_wait=0.0, poll_interval=0.0, max_wait=0.0,
    )
    assert len(call_log) == 3
    out = capsys.readouterr().out
    assert out.count("PREPARED ") == 1
    assert out.count("ROUNDTRIP ") == 1


def test_roundtrip_conn_stmts_is_a_difference_not_a_cumulative_value(capsys):
    """WO §2.2 completion condition 4: `stmts` is `post.execute_count`
    minus the SAME label's own `pre.execute_count` -- never the raw
    cumulative `execute_count` carried straight through.

    mutation M4 (`tools/perf_baseline.py`): use `stats["execute_count"]`
    directly for `stmts`, ignoring `pre_conn_stats` -- this test's own
    `stmts=6` assertion goes red (would read `stmts=56`)."""
    pre = [{"label": "app1/runtime@1", "execute_count": 50, "probed": True}]
    post = [{"label": "app1/runtime@1", "execute_count": 56, "probed": True}]
    pb._emit_roundtrip_conn_rows("r2db-api", "r2db-api", "query", 10, pre, post)
    out = capsys.readouterr().out
    assert "stmts=6 " in out


def test_roundtrip_conn_baseline_is_this_ops_own_pre_probe_not_the_previous_ops_post(capsys):
    """WO §2.2 completion condition 5a (design review 1 M-3): the baseline
    for op N's own `stmts` is op N's own PRE probe, taken immediately
    before `_measure_op` starts -- activity BETWEEN two ops (credential
    issuance, `authenticate`, `create_entity`) that bumps `execute_count`
    must not leak into the NEXT op's own `stmts`.

    mutation M5 (`tools/perf_baseline.py`): drop the PRE probe and use the
    PREVIOUS op's own POST value as the baseline instead -- this test's
    own `stmts=0` assertion for op 2 goes red (would read `stmts=15`,
    since the previous op's own POST was 5 and the between-ops activity
    bumped the stub to 20)."""
    counts = {"n": 5}

    def prepared_stats():
        return [{
            "label": "app1/runtime@1", "execute_count": counts["n"], "executemany_count": 0,
            "prepared": 0, "prepared_execs": 0, "prepared_statements": [], "probed": True,
        }]

    stub = SimpleNamespace(transport_kind="in_process", prepared_stats=prepared_stats)
    common = dict(
        warmup=0, n=1, concurrency=1, adapter_obj=stub, prepared_detail=False,
        roundtrip_enabled=True, admin_conn=None, db_names={}, correction_matcher=None,
        min_wait=0.0, poll_interval=0.0, max_wait=0.0,
    )
    pb._measure_op_and_emit(lambda: None, peer="r2db-api", plug="r2db-api", op="query", counter=pb._CallCounter(), **common)
    counts["n"] = 20  # between-ops activity this run's own credential/entity calls would cause
    capsys.readouterr()
    pb._measure_op_and_emit(lambda: None, peer="r2db-api", plug="r2db-api", op="mutate", counter=pb._CallCounter(), **common)
    out = capsys.readouterr().out
    line = next(l for l in out.splitlines() if l.startswith("ROUNDTRIP") and "op=mutate" in l and "conn=" in l)
    assert "stmts=0 " in line


def test_roundtrip_conn_baseline_is_zero_for_a_reconnected_label(capsys):
    """WO §2.2 completion condition 5b (起草時の裁定7): when the PRE probe
    has no entry for a POST label at all (a reconnect changed the label's
    own pid), the baseline is 0 -- never an exception, never a different
    label's own value.

    mutation M19 (`tools/perf_baseline.py`): drop the row for a label
    absent from `pre_conn_stats` instead of using baseline 0 -- this
    test's own `conn=app1/runtime@2` assertion goes red (the line is
    missing entirely)."""
    pre = [{"label": "app1/runtime@1", "execute_count": 99, "probed": True}]
    post = [{"label": "app1/runtime@2", "execute_count": 3, "probed": True}]
    pb._emit_roundtrip_conn_rows("r2db-api", "r2db-api", "query", 10, pre, post)
    out = capsys.readouterr().out
    assert "conn=app1/runtime@2 stmts=3 " in out


def test_roundtrip_per_req_is_zero_point_zero_when_requests_is_zero(capsys):
    """WO §2.2 completion condition 6: `stmts_per_req`/`xacts_per_req`/
    `sessions_per_req` are `value / requests`, printed `0.00` (never a
    `ZeroDivisionError`) when `requests == 0`.

    mutation M6 (`tools/perf_baseline.py`): make `_per_request` divide
    unconditionally -- this test raises `ZeroDivisionError` instead of
    printing `0.00` (red either way)."""
    pb._emit_roundtrip_conn_rows("r2db-api", "r2db-api", "query", 0, [], [{"label": "a@1", "execute_count": 5, "probed": True}])
    db_names = {"app": "appdb"}
    pre_db = {"app": {"values": (0, 0, 0), "stale": False}}
    post_db = {"app": {"values": (5, 1, 2), "stale": False}}
    pb._emit_roundtrip_db_rows("r2db-api", "r2db-api", "query", 0, db_names, pre_db, post_db, None, None)
    out = capsys.readouterr().out
    assert "stmts_per_req=0.00" in out
    assert "xacts_per_req=0.00" in out
    assert "sessions_per_req=0.00" in out


def test_roundtrip_requests_is_warmup_plus_n_times_concurrency(capsys):
    """WO §2.2 completion condition 7: `requests` is `(warmup + n) *
    concurrency` -- a DIFFERENT value from the `PERF` line's own `n=`
    (the measured-sample count alone).

    mutation M7 (`tools/perf_baseline.py`): use `n * concurrency` for
    `requests`, dropping `warmup` -- this test's own `requests=14`
    assertion goes red (would read `requests=8`)."""
    stub = SimpleNamespace(
        transport_kind="in_process",
        prepared_stats=lambda: [{
            "label": "a@1", "execute_count": 1, "executemany_count": 0,
            "prepared": 0, "prepared_execs": 0, "prepared_statements": [], "probed": True,
        }],
    )
    pb._measure_op_and_emit(
        lambda: None, peer="r2db-api", plug="r2db-api", op="query",
        warmup=3, n=4, concurrency=2, counter=pb._CallCounter(), adapter_obj=stub,
        prepared_detail=False, roundtrip_enabled=True, admin_conn=None, db_names={},
        correction_matcher=None, min_wait=0.0, poll_interval=0.0, max_wait=0.0,
    )
    out = capsys.readouterr().out
    line = next(l for l in out.splitlines() if l.startswith("ROUNDTRIP") and "conn=" in l)
    assert "requests=14 " in line


def test_roundtrip_db_xacts_is_commit_plus_rollback_delta(capsys):
    """WO §2.2 completion condition 8: `xacts` is `Δxact_commit +
    Δxact_rollback`, `sessions` is `Δsessions`, both measured against the
    SAME op's own PRE read.

    mutation M8 (`tools/perf_baseline.py`): drop `Δxact_rollback` from
    `xacts` -- this test's own `xacts=18` assertion goes red (would read
    `xacts=15`)."""
    pre_db = {"app": {"values": (10, 2, 1), "stale": False}}
    post_db = {"app": {"values": (25, 5, 1), "stale": False}}
    pb._emit_roundtrip_db_rows("r2db-api", "r2db-api", "query", 10, {"app": "appdb"}, pre_db, post_db, None, None)
    out = capsys.readouterr().out
    assert "xacts=18 " in out
    assert "sessions=0 " in out


def test_roundtrip_db_app_xacts_subtracts_only_this_apps_own_probes(capsys):
    """WO §2.2 completion condition 9 (design review 1 M-4): `db=app`'s
    own `xacts` is reduced by the count of POST-probed connections the
    correction matcher says belong to THIS application (never a different
    application's own label) -- `db=platform`'s own correction is always
    0.

    mutation M9 (`tools/perf_baseline.py`): drop the subtraction entirely
    -- this test's own `xacts=3` assertion for `db=app` goes red (would
    read `xacts=5`, the un-corrected commit delta)."""
    pre_db = {"app": {"values": (0, 0, 0), "stale": False}, "platform": {"values": (0, 0, 0), "stale": False}}
    post_db = {"app": {"values": (5, 0, 0), "stale": False}, "platform": {"values": (5, 0, 0), "stale": False}}
    post_conn_stats = [
        {"label": "app1/runtime@1", "probed": True},
        {"label": "app1/runtime@2", "probed": True},
        {"label": "app2/runtime@9", "probed": True},  # a DIFFERENT application -- must not be counted
    ]
    matcher = lambda stats: stats["label"].startswith("app1/")  # noqa: E731 - test-local, mirrors production shape
    pb._emit_roundtrip_db_rows(
        "r2db-api", "r2db-api", "query", 10, {"app": "appdb", "platform": "platformdb"},
        pre_db, post_db, post_conn_stats, matcher,
    )
    out = capsys.readouterr().out
    lines = {l.split("db=", 1)[1].split()[0]: l for l in out.splitlines()}
    assert "xacts=3 " in lines["app"]
    assert "xacts=5 " in lines["platform"]


def test_roundtrip_db_app_xacts_also_subtracts_the_dbtime_pre_probe(capsys):
    """WO §1.2 D-1 (i, 案 (a)): `db=app`'s own `xacts` correction
    subtracts BOTH probes that land inside a `--roundtrip` window -- the
    shared POST snapshot (already covered by `test_roundtrip_db_app_
    xacts_subtracts_only_this_apps_own_probes` above) and `DBTIME`'s own
    separate PRE snapshot, passed in via the `pre_probe_conn_stats`
    keyword. Every other test in this module calls `_emit_roundtrip_db_
    rows` without that keyword, so its default (`None`) leaves the
    correction unchanged for them.

    mutation M107 (`tools/perf_baseline.py`): drop the `pre_probe_conn_
    stats` subtraction -- this test's own `xacts=1` assertion goes red
    (would read `xacts=2`, the POST-only correction)."""
    pre_db = {"app": {"values": (0, 0, 0), "stale": False}}
    post_db = {"app": {"values": (3, 0, 0), "stale": False}}
    post_conn_stats = [{"label": "app1/runtime@1", "probed": True}]
    pre_probe_conn_stats = [{"label": "app1/runtime@2", "probed": True}]
    matcher = lambda stats: stats["label"].startswith("app1/")  # noqa: E731 - test-local, mirrors production shape
    pb._emit_roundtrip_db_rows(
        "r2db-api", "r2db-api", "query", 10, {"app": "appdb"},
        pre_db, post_db, post_conn_stats, matcher,
        pre_probe_conn_stats=pre_probe_conn_stats,
    )
    out = capsys.readouterr().out
    assert "xacts=1 " in out


def test_poll_clears_snapshot_before_reading_stats():
    """WO §2.2 completion condition 10: `_poll_pg_stat_database` calls
    `clear_snapshot()` before its first `read_stats()` call -- observed
    via the exact call order a fake admin connection's own stand-ins
    receive.

    mutation M10 (`tools/perf_baseline.py`): drop the `clear_snapshot()`
    call from `_poll_pg_stat_database` -- this test's own `order[0] ==
    "clear"` assertion goes red (the log would start with `"read"`, or be
    empty of `"clear"` entirely)."""
    order: list[str] = []

    def clear_snapshot() -> None:
        order.append("clear")

    def read_stats(dbs):
        order.append("read")
        return {d: (1, 0, 1) for d in dbs}

    pb._poll_pg_stat_database(
        ["app"], read_stats=read_stats, clear_snapshot=clear_snapshot,
        min_wait=0.0, poll_interval=0.0, max_wait=0.0, sleep=lambda s: None, now=lambda: 0.0,
    )
    assert order[0] == "clear"
    assert "read" in order


def test_poll_does_not_confirm_before_the_minimum_wait_even_when_stable(capsys):
    """WO §2.2 completion condition 11 (design review 1 H-1): a value that
    is stable from the very FIRST read must not confirm before `min_wait`
    seconds have elapsed since the clear -- WO §1.3 (5b)'s own run 1 (a
    flat `+5` sat unchanged for 20 real seconds while the true value was
    `+101`).

    mutation M11 (`tools/perf_baseline.py`): drop the `elapsed >= min_
    wait` half of the confirm condition (confirm on 3-in-a-row alone) --
    this test's own `fake_clock["t"] >= 5.0` assertion goes red (the fake
    clock would stop advancing after only 3 reads, well under 5.0)."""
    fake_clock = {"t": 0.0}

    def now() -> float:
        return fake_clock["t"]

    def sleep(seconds: float) -> None:
        fake_clock["t"] += seconds

    def read_stats(dbs):
        return {"app": (2, 0, 1)}

    result = pb._poll_pg_stat_database(
        ["app"], read_stats=read_stats, clear_snapshot=lambda: None,
        min_wait=5.0, poll_interval=1.0, max_wait=30.0, sleep=sleep, now=now,
    )
    assert result["app"]["stale"] is False
    assert fake_clock["t"] >= 5.0


def test_poll_marks_a_confirmed_result_as_not_stale():
    """WO §2.2 completion condition 22a: a value that DOES confirm (3-in-
    a-row after `min_wait`) is returned with `stale=False`.

    mutation M21 (`tools/perf_baseline.py`): mark every result `stale=True`
    unconditionally, even a confirmed one -- this test's own `stale is
    False` assertion goes red."""
    fake_clock = {"t": 0.0}
    result = pb._poll_pg_stat_database(
        ["app"], read_stats=lambda dbs: {"app": (2, 0, 1)}, clear_snapshot=lambda: None,
        min_wait=1.0, poll_interval=1.0, max_wait=30.0,
        sleep=lambda s: fake_clock.__setitem__("t", fake_clock["t"] + s), now=lambda: fake_clock["t"],
    )
    assert result["app"]["stale"] is False


def test_poll_marks_a_timed_out_result_as_stale():
    """WO §2.2 completion condition 22b: a value that never stops changing
    is returned, at its LAST-seen value, with `stale=True` once `max_wait`
    is reached -- never blocked on forever.

    mutation M17 (`tools/perf_baseline.py`): drop the `max_wait` branch so
    a never-stabilizing poll returns `stale=False` (or loops forever) --
    this test's own `stale is True` assertion goes red."""
    counter = {"i": 0}

    def read_stats(dbs):
        counter["i"] += 1
        return {"app": (counter["i"], 0, 1)}  # always different -- never stabilizes

    fake_clock = {"t": 0.0}
    result = pb._poll_pg_stat_database(
        ["app"], read_stats=read_stats, clear_snapshot=lambda: None,
        min_wait=1.0, poll_interval=1.0, max_wait=3.0,
        sleep=lambda s: fake_clock.__setitem__("t", fake_clock["t"] + s), now=lambda: fake_clock["t"],
    )
    assert result["app"]["stale"] is True


def test_resolve_app_db_and_platform_db_use_the_two_known_forms():
    """WO §2.2 completion condition 12a (WO §1.3 (8)): `db=` resolution
    tries the r2db form (`cell._runtime_dsn`, a DSN string) and the
    MitateDB form (backend's own `_runtime.info.dbname`) -- both yield an
    application DB name, and `_platform.platform_db` yields the platform
    DB name.

    mutation M12 (`tools/perf_baseline.py`): drop the MitateDB form
    (`_runtime.info.dbname`) from `_resolve_app_db_and_matcher` -- this
    test's own `app_db_mitate == "mdb_app1"` assertion goes red (would
    read `None`)."""
    r2db_cell = SimpleNamespace(_runtime_dsn="host=/x port=5432 dbname=perf_app1 user=runtime")
    app_db_r2db, matcher_r2db = pb._resolve_app_db_and_matcher(r2db_cell, "app1")
    assert app_db_r2db == "perf_app1"
    assert matcher_r2db({"label": "app1/runtime@1"}) is True
    assert matcher_r2db({"label": "app2/runtime@1"}) is False

    backend = SimpleNamespace(
        _runtime=SimpleNamespace(info=SimpleNamespace(dbname="mdb_app1", backend_pid=111)),
        _developer=SimpleNamespace(info=SimpleNamespace(dbname="mdb_app1", backend_pid=222)),
    )
    mitate_cell = SimpleNamespace(_backend=backend)
    app_db_mitate, matcher_mitate = pb._resolve_app_db_and_matcher(mitate_cell, "app1")
    assert app_db_mitate == "mdb_app1"
    assert matcher_mitate({"label": "runtime@111"}) is True
    assert matcher_mitate({"label": "developer@222"}) is True
    assert matcher_mitate({"label": "runtime@999"}) is False

    adapter_stub = SimpleNamespace(_platform=SimpleNamespace(platform_db="perf_platform"))
    assert pb._resolve_platform_db(adapter_stub) == "perf_platform"


def test_resolve_app_db_returns_none_without_exception_for_an_unknown_shape():
    """WO §2.2 completion condition 12b: a cell/backend matching NEITHER
    known form resolves to `(None, <a matcher that always says False>)` --
    never an exception.

    mutation M20 (`tools/perf_baseline.py`): raise when neither form
    resolves -- this test's own call goes red with an unhandled
    exception instead of returning `(None, ...)`."""
    weird_cell = SimpleNamespace()
    app_db, matcher = pb._resolve_app_db_and_matcher(weird_cell, "app1")
    assert app_db is None
    assert matcher({"label": "anything"}) is False


def test_emit_measurement_rows_prints_roundtrip_conn_lines_after_prepared_lines(capsys):
    """WO §2.2 completion condition 13: `ROUNDTRIP` lines print AFTER the
    same op's own `PREPARED` lines -- `POOL` -> `PREPARED` -> `ROUNDTRIP`.

    mutation M13 (`tools/perf_baseline.py`): print the `ROUNDTRIP conn=`
    lines from inside `_emit_measurement_rows` BEFORE calling `_emit_
    prepared_rows` -- this test's own `prepared_idx < roundtrip_idx`
    assertion goes red."""
    stub = SimpleNamespace(
        transport_kind="in_process",
        prepared_stats=lambda: [{
            "label": "app1/runtime@1", "execute_count": 5, "executemany_count": 0,
            "prepared": 0, "prepared_execs": 0, "prepared_statements": [], "probed": True,
        }],
    )
    roundtrip = {
        "requests": 10, "pre_conn_stats": None, "pre_db_values": None, "admin_conn": None,
        "db_names": {}, "correction_matcher": None, "min_wait": 0.0, "poll_interval": 0.0, "max_wait": 0.0,
    }
    pb._emit_measurement_rows("r2db-api", "r2db-api", "query", stub, prepared_detail=False, roundtrip=roundtrip)
    out = capsys.readouterr().out
    prepared_idx = out.index("PREPARED ")
    roundtrip_idx = out.index("ROUNDTRIP ")
    assert prepared_idx < roundtrip_idx


def test_roundtrip_conn_rows_are_absent_when_the_plug_has_no_prepared_stats(capsys):
    """WO §2.2 completion condition 14: a plug without `prepared_stats`
    (every plug this WP does not touch) gets zero `ROUNDTRIP conn=` lines
    -- no exception, mirrors `PREPARED`'s own identical skip.

    mutation M14 (`tools/perf_baseline.py`, shared with R-79's own
    `_emit_prepared_rows`): drop the `getattr(..., None)` default so a
    plug without `prepared_stats` raises `AttributeError` instead -- this
    test's own call goes red with an unhandled exception."""
    stub = SimpleNamespace(transport_kind="in_process")  # no prepared_stats attribute at all
    roundtrip = {
        "requests": 5, "pre_conn_stats": None, "pre_db_values": None, "admin_conn": None,
        "db_names": {}, "correction_matcher": None, "min_wait": 0.0, "poll_interval": 0.0, "max_wait": 0.0,
    }
    pb._emit_measurement_rows("r2db-api", "r2db-api", "query", stub, prepared_detail=False, roundtrip=roundtrip)
    out = capsys.readouterr().out
    assert "ROUNDTRIP" not in out


def test_roundtrip_rows_print_for_a_socket_transport_plug(capsys):
    """WO §2.2 completion condition 15: a stub declaring `transport_kind
    == "socket"` still gets its `ROUNDTRIP` line(s) -- there is no
    transport this tool skips (mirrors R-78/R-79's own identical tests).

    mutation M15 (`tools/perf_baseline.py`): suppress `ROUNDTRIP` output
    for any plug name ending in `-socket` -- this test's own stub plug
    is named `r2db-api-socket`, so the assertion below goes red."""
    stub = SimpleNamespace(
        transport_kind="socket",
        prepared_stats=lambda: [{
            "label": "app1/runtime@1", "execute_count": 3, "executemany_count": 0,
            "prepared": 0, "prepared_execs": 0, "prepared_statements": [], "probed": True,
        }],
    )
    roundtrip = {
        "requests": 3, "pre_conn_stats": None, "pre_db_values": None, "admin_conn": None,
        "db_names": {}, "correction_matcher": None, "min_wait": 0.0, "poll_interval": 0.0, "max_wait": 0.0,
    }
    pb._emit_measurement_rows("r2db-api", "r2db-api-socket", "query", stub, prepared_detail=False, roundtrip=roundtrip)
    out = capsys.readouterr().out
    assert out.count("ROUNDTRIP ") == 1


def test_roundtrip_enabled_follows_the_flag_only():
    """WO §2.2 completion condition 21a: `--roundtrip` (default off)
    alone decides `_roundtrip_enabled`.

    mutation M16 (`tools/perf_baseline.py`): make `_roundtrip_enabled`
    always return `True` -- this test's own `is False` assertion for the
    no-flag case goes red."""
    parser = pb._build_parser()
    assert parser.get_default("roundtrip") is False
    args_default = parser.parse_args([])
    assert pb._roundtrip_enabled(args_default) is False
    args_on = parser.parse_args(["--roundtrip"])
    assert pb._roundtrip_enabled(args_on) is True


def test_roundtrip_disabled_never_touches_the_admin_connection_and_prints_nothing(capsys):
    """WO §2.2 completion condition 21a (second half): with `roundtrip_
    enabled=False`, `_measure_op_and_emit` never calls anything on
    `admin_conn` (a poison stand-in here that raises if touched at all)
    and prints no `ROUNDTRIP` line."""
    class _Poison:
        def cursor(self):  # pragma: no cover - must never be reached
            raise AssertionError("admin connection must not be used when roundtrip is disabled")

    stub = SimpleNamespace(
        transport_kind="in_process",
        prepared_stats=lambda: [{
            "label": "app1/runtime@1", "execute_count": 1, "executemany_count": 0,
            "prepared": 0, "prepared_execs": 0, "prepared_statements": [], "probed": True,
        }],
    )
    pb._measure_op_and_emit(
        lambda: None, peer="r2db-api", plug="r2db-api", op="query",
        warmup=0, n=1, concurrency=1, counter=pb._CallCounter(), adapter_obj=stub,
        prepared_detail=False, roundtrip_enabled=False, admin_conn=_Poison(), db_names={"app": "x"},
        correction_matcher=None, min_wait=0.0, poll_interval=0.0, max_wait=0.0,
    )
    out = capsys.readouterr().out
    assert "ROUNDTRIP" not in out


def test_default_run_probes_prepared_stats_exactly_twice_per_op(capsys):
    """WO §2.2 completion condition 21b (design review 1 M-5), updated by
    R-101 WP-1 completion condition 36: with `--roundtrip` absent,
    `prepared_stats()` is called exactly twice per op -- a DBTIME PRE
    snapshot inside `_measure_op` (after warmup, before the measured
    window) and the POST call `_emit_measurement_rows` shares between
    `DBTIME scope=app` and `PREPARED` -- the ROUNDTRIP PRE probe never
    runs outside `--roundtrip`, so R-79's own established `POOL`
    `acquire`/`PREPARED` baseline stays undisturbed by that flag.

    mutation M31 (`tools/perf_baseline.py`): drop the PRE `prepared_
    stats()` call inside `_measure_op` -- this test's own `len(call_log)
    == 2` assertion goes red (1 call instead of 2)."""
    call_log: list[int] = []

    def prepared_stats():
        call_log.append(1)
        return [{
            "label": "a@1", "execute_count": 1, "executemany_count": 0,
            "prepared": 0, "prepared_execs": 0, "prepared_statements": [], "probed": True,
        }]

    stub = SimpleNamespace(transport_kind="in_process", prepared_stats=prepared_stats)
    pb._measure_op_and_emit(
        lambda: None, peer="r2db-api", plug="r2db-api", op="query",
        warmup=0, n=1, concurrency=1, counter=pb._CallCounter(), adapter_obj=stub,
        prepared_detail=False, roundtrip_enabled=False, admin_conn=None, db_names={},
        correction_matcher=None, min_wait=0.0, poll_interval=0.0, max_wait=0.0,
    )
    assert len(call_log) == 2


def test_emit_measurement_rows_reads_roundtrip_db_poll_by_real_name_and_prints_by_kind(monkeypatch, capsys):
    """R-80 regression (実機確認 2026-09-24 で発見): `_poll_pg_stat_database`
    returns its result keyed by the REAL database name it queried, never
    by the logical kind (`"app"`/`"platform"`) -- `_emit_measurement_rows`
    must re-key that result back to kind before handing it to `_emit_
    roundtrip_db_rows`, which looks its two inputs up by kind alone. The
    stub poll below returns two DIFFERENT real names (`realapp_db`/
    `realplatform_db`) rather than echoing "app"/"platform" straight
    back, so a missing re-key is actually exercised, not masked.

    mutation M22 (`tools/perf_baseline.py`): drop the re-keying dict
    comprehension in `_emit_measurement_rows`'s own `ROUNDTRIP` block
    (`post_db_values = by_dbname` instead of `{kind: by_dbname[db_name]
    for kind, db_name in db_names.items()}`) -- this test's own `db=app`/
    `db=platform` line-count assertions go red (both real names are
    absent from `db_names`' own kind vocabulary, so `_emit_roundtrip_db_
    rows`'s own per-kind lookups miss and print nothing)."""
    def fake_poll(names, **kwargs):
        return {name: {"values": (1, 0, 1), "stale": False} for name in names}

    monkeypatch.setattr(pb, "_poll_pg_stat_database", fake_poll)

    stub = SimpleNamespace(
        transport_kind="in_process",
        prepared_stats=lambda: [{
            "label": "app1/runtime@1", "execute_count": 1, "executemany_count": 0,
            "prepared": 0, "prepared_execs": 0, "prepared_statements": [], "probed": True,
        }],
    )
    roundtrip = {
        "requests": 1, "pre_conn_stats": None,
        "pre_db_values": {
            "app": {"values": (0, 0, 0), "stale": False},
            "platform": {"values": (0, 0, 0), "stale": False},
        },
        "admin_conn": None,
        "db_names": {"app": "realapp_db", "platform": "realplatform_db"},
        "correction_matcher": None, "min_wait": 0.0, "poll_interval": 0.0, "max_wait": 0.0,
    }
    pb._emit_measurement_rows("r2db-api", "r2db-api", "query", stub, prepared_detail=False, roundtrip=roundtrip)
    out = capsys.readouterr().out
    assert out.count("db=app ") == 1
    assert out.count("db=platform ") == 1


# ---------------------------------------------------------------------
# R-80 rework -- コードレビュー差し戻し (2026-09-24)。
# ---------------------------------------------------------------------


def test_roundtrip_db_stale_is_the_or_of_pre_and_post(capsys):
    """コードレビュー差し戻し 1 (2026-09-24): a `db=` row's own `stale` is
    the LOGICAL OR of the PRE read's own `stale` and the POST read's own
    `stale` -- either half being unsettled makes the whole `Δ` unsettled.
    Two cases: POST alone `stale=True`, and PRE alone `stale=True`.

    mutation M23 (`tools/perf_baseline.py`): hardcode `stale = False` --
    both cases' own `"stale=1"` assertions go red.
    mutation M24 (`tools/perf_baseline.py`): use `bool(post_entry["stale"])`
    alone (ignore PRE) -- the PRE-only case's own `"stale=1"` assertion
    goes red (POST alone still shows `stale=1`, masking a POST-only bug,
    which is exactly why both cases are asserted here)."""
    pre_post_stale = {"app": {"values": (0, 0, 0), "stale": False}}
    post_stale = {"app": {"values": (1, 0, 0), "stale": True}}
    pb._emit_roundtrip_db_rows("r2db-api", "r2db-api", "query", 1, {"app": "x"}, pre_post_stale, post_stale, None, None)
    out = capsys.readouterr().out
    assert "stale=1" in out

    pre_stale = {"app": {"values": (0, 0, 0), "stale": True}}
    post_not_stale = {"app": {"values": (1, 0, 0), "stale": False}}
    pb._emit_roundtrip_db_rows("r2db-api", "r2db-api", "query", 1, {"app": "x"}, pre_stale, post_not_stale, None, None)
    out = capsys.readouterr().out
    assert "stale=1" in out


def test_roundtrip_db_app_correction_ignores_unprobed_connections(capsys):
    """コードレビュー差し戻し 2 (2026-09-24): `_probe_correction_count`
    only counts a connection whose own `probed` is true -- adding an
    otherwise-matching connection with `probed=False` (left alone by the
    probe because it was not IDLE, `psycopg_counting.probe_prepared_
    statements`'s own early return) must not change the correction.

    mutation M25 (`tools/perf_baseline.py`): drop the `stats.get(
    "probed") and` half of `_probe_correction_count`'s own generator
    condition -- this test's own `xacts=4` assertion goes red (would
    read `xacts=3`, since the unprobed connection gets counted too)."""
    pre_db = {"app": {"values": (0, 0, 0), "stale": False}}
    post_db = {"app": {"values": (5, 0, 0), "stale": False}}
    post_conn_stats = [
        {"label": "app1/runtime@1", "probed": True},
        {"label": "app1/runtime@2", "probed": False},  # left alone by the probe -- must not count
    ]
    matcher = lambda stats: stats["label"].startswith("app1/")  # noqa: E731 - test-local
    pb._emit_roundtrip_db_rows(
        "r2db-api", "r2db-api", "query", 10, {"app": "appdb"}, pre_db, post_db, post_conn_stats, matcher,
    )
    out = capsys.readouterr().out
    assert "xacts=4 " in out


def test_roundtrip_wait_defaults_are_12_and_30_seconds():
    """コードレビュー差し戻し 3 (2026-09-24): the minimum wait (12.0s) and
    the ceiling (30.0s) this file's own `ROUNDTRIP` poll uses are pinned
    directly (WO §1.2 D-1, WO §6.1 設計レビュー1のH-1).

    mutation M26 (`tools/perf_baseline.py`): change `_ROUNDTRIP_MIN_WAIT_S`
    from `12.0` to `0.0` -- this test's own `== 12.0` assertion goes red."""
    assert pb._ROUNDTRIP_MIN_WAIT_S == 12.0
    assert pb._ROUNDTRIP_MAX_WAIT_S == 30.0


def test_poll_confirms_when_two_kinds_resolve_to_the_same_database_name():
    """コードレビュー差し戻し 5 (2026-09-24): `db=app`/`db=platform`
    resolving to the SAME real database name (a degenerate but not
    impossible case) must not prevent the poll from ever confirming --
    `db_names` is de-duplicated before `confirmed`/`streak` are built.

    mutation M27 (`tools/perf_baseline.py`): drop the de-duplication line
    -- this test's own `stale is False` (and `fake_clock["t"] < 3.0`,
    never reaching `max_wait`) assertions go red: the duplicate name
    makes `len(confirmed)` (1, unique) permanently short of `len(
    db_names)` (2, with the duplicate), so the poll runs out the clock to
    `max_wait` and reports `stale=True` even though the value settled
    immediately."""
    fake_clock = {"t": 0.0}

    def read_stats(dbs):
        return {d: (1, 0, 1) for d in dbs}

    result = pb._poll_pg_stat_database(
        ["same_db", "same_db"], read_stats=read_stats, clear_snapshot=lambda: None,
        min_wait=1.0, poll_interval=1.0, max_wait=3.0,
        sleep=lambda s: fake_clock.__setitem__("t", fake_clock["t"] + s), now=lambda: fake_clock["t"],
    )
    assert result["same_db"]["stale"] is False
    assert fake_clock["t"] < 3.0


# ---------------------------------------------------------------------
# R-101 WP-1: `CPU`/`DBTIME` rows (D-1/D-2) -- format, PRE/POST windows,
# ordering, and the `thread_limit=`/`requests=` denominators.
# ---------------------------------------------------------------------


def test_cpu_row_format_matches_the_declared_columns():
    """Completion condition 40: the `CPU` line's own column names/order
    match the declared format exactly, and `cpu_other_ms` is `cpu_total_ms
    - cpu_main_ms`.

    mutation M34 (`tools/perf_baseline.py`): rename `cpu_main_ms=` to
    `main_cpu_ms=` in `_format_cpu_row` -- this test's own equality
    assertion goes red.
    mutation M36 (`tools/perf_baseline.py`): make `cpu_other_ms` print
    `cpu_total_ms` unchanged instead of the difference -- this test's own
    `cpu_other_ms=40.000` assertion goes red (would read `50.000`)."""
    m = {"concurrency": 4, "thread_limit": 40, "requests": 400, "wall_ms": 62.7, "cpu_total_ms": 50.0, "cpu_main_ms": 10.0}
    line = pb._format_cpu_row("r2db-api", "r2db-api-http", "query", m)
    assert line == (
        "CPU peer=r2db-api plug=r2db-api-http op=query concurrency=4 thread_limit=40 "
        "requests=400 wall_ms=62.700 cpu_total_ms=50.000 cpu_main_ms=10.000 cpu_other_ms=40.000"
    )


def test_dbtime_app_row_format_matches_the_declared_columns():
    """Completion condition 28: the `DBTIME ... scope=app` line's own
    column names/order match the declared format.

    mutation M23 (`tools/perf_baseline.py`): rename `gone=` to `lost=` in
    `_format_dbtime_app_row` -- this test's own equality assertion goes
    red."""
    line = pb._format_dbtime_app_row(
        "r2db-api", "r2db-api", "query", concurrency=1, requests=10, conns=3, gone=1, db_calls=5, txns=2, db_wall_ms=12.5,
    )
    assert line == (
        "DBTIME peer=r2db-api plug=r2db-api op=query concurrency=1 scope=app "
        "conns=3 gone=1 db_calls=5 txns=2 db_wall_ms=12.500 db_wall_ms_per_req=1.250"
    )


def test_dbtime_platform_row_format_matches_the_declared_columns():
    """Completion condition 29: the `DBTIME ... scope=platform` line's own
    column names/order match the declared format, and `db_wall_ms_per_req`
    folds `connect_wall_ms` into the numerator.

    mutation M24 (`tools/perf_baseline.py`): rename `connect_wall_ms=` to
    `connect_ms=` in `_format_dbtime_platform_row` -- this test's own
    equality assertion goes red.
    mutation M29 (`tools/perf_baseline.py`): drop `connect_wall_ms` from
    the `db_wall_ms_per_req` division -- this test's own
    `db_wall_ms_per_req=1.000` assertion goes red (would read `0.600`)."""
    line = pb._format_dbtime_platform_row(
        "r2db-api", "r2db-api", "query", concurrency=1, requests=10,
        sessions=2, connect_wall_ms=4.0, db_calls=0, txns=3, db_wall_ms=6.0,
    )
    assert line == (
        "DBTIME peer=r2db-api plug=r2db-api op=query concurrency=1 scope=platform "
        "sessions=2 connect_wall_ms=4.000 db_calls=0 txns=3 db_wall_ms=6.000 db_wall_ms_per_req=1.000"
    )


def test_dbtime_app_db_wall_ms_is_a_pre_post_difference(capsys):
    """Completion condition 30: `scope=app`'s own `db_wall_ms`/`txns`/
    `db_calls` are POST minus PRE, matched by connection `label` --
    never the raw POST value.

    mutation M25 (`tools/perf_baseline.py`): use the POST value directly
    for `db_wall_ms` in `_emit_dbtime_rows`, without subtracting PRE --
    this test's own `db_wall_ms=40.000` assertion goes red (would read
    `140.000`)."""
    measurement = {
        "concurrency": 1, "requests": 1,
        "dbtime_pre": {
            "conn_stats": [{"label": "a@1", "execute_count": 10, "executemany_count": 0, "db_wall_ms": 100.0, "txn_count": 5}],
            "platform_stats": None,
        },
    }
    post = [{"label": "a@1", "execute_count": 16, "executemany_count": 0, "db_wall_ms": 140.0, "txn_count": 7}]
    pb._emit_dbtime_rows("r2db-api", "r2db-api", "query", measurement, post, None)
    out = capsys.readouterr().out
    assert "db_wall_ms=40.000" in out


def test_dbtime_app_treats_a_connection_new_since_pre_as_a_zero_baseline(capsys):
    """Completion condition 31 (空振り禁止): a connection `label` present
    only in the POST snapshot (opened during the measured window) is
    still counted into `scope=app`'s own sums, its own PRE treated as 0 --
    never dropped from the aggregation.

    mutation M26 (`tools/perf_baseline.py`): skip a POST-only label
    entirely in `_emit_dbtime_rows`'s own aggregation loop -- this test's
    own `db_wall_ms=9.000` assertion goes red (would read `0.000`)."""
    measurement = {"concurrency": 1, "requests": 1, "dbtime_pre": {"conn_stats": [], "platform_stats": None}}
    post = [{"label": "new@9", "execute_count": 3, "executemany_count": 0, "db_wall_ms": 9.0, "txn_count": 1}]
    pb._emit_dbtime_rows("r2db-api", "r2db-api", "query", measurement, post, None)
    out = capsys.readouterr().out
    assert "conns=1" in out
    assert "db_wall_ms=9.000" in out


def test_dbtime_app_conns_counts_every_post_label_including_new_ones(capsys):
    """Completion condition 32: `conns=` is the number of labels in the
    POST snapshot alone -- including one absent from PRE -- never the
    intersection of PRE and POST.

    mutation M27 (`tools/perf_baseline.py`): compute `conns=` as `len(pre_
    by_label.keys() & post_labels)` (the intersection) instead of `len(
    post_conn_stats)` -- this test's own `conns=2` assertion goes red
    (would read `conns=1`)."""
    measurement = {
        "concurrency": 1, "requests": 1,
        "dbtime_pre": {
            "conn_stats": [{"label": "a@1", "execute_count": 1, "executemany_count": 0, "db_wall_ms": 1.0, "txn_count": 1}],
            "platform_stats": None,
        },
    }
    post = [
        {"label": "a@1", "execute_count": 2, "executemany_count": 0, "db_wall_ms": 2.0, "txn_count": 2},
        {"label": "new@2", "execute_count": 1, "executemany_count": 0, "db_wall_ms": 1.0, "txn_count": 1},
    ]
    pb._emit_dbtime_rows("r2db-api", "r2db-api", "query", measurement, post, None)
    out = capsys.readouterr().out
    assert "conns=2" in out


def test_dbtime_app_gone_counts_connections_missing_from_post(capsys):
    """Completion condition 33: `gone=` is the number of labels present
    only in the PRE snapshot (closed during the measured window).

    mutation M28 (`tools/perf_baseline.py`): hardcode `gone=0` in `_emit_
    dbtime_rows` -- this test's own `gone=1` assertion goes red."""
    measurement = {
        "concurrency": 1, "requests": 1,
        "dbtime_pre": {
            "conn_stats": [
                {"label": "a@1", "execute_count": 1, "executemany_count": 0, "db_wall_ms": 1.0, "txn_count": 1},
                {"label": "closed@2", "execute_count": 1, "executemany_count": 0, "db_wall_ms": 1.0, "txn_count": 1},
            ],
            "platform_stats": None,
        },
    }
    post = [{"label": "a@1", "execute_count": 2, "executemany_count": 0, "db_wall_ms": 2.0, "txn_count": 2}]
    pb._emit_dbtime_rows("r2db-api", "r2db-api", "query", measurement, post, None)
    out = capsys.readouterr().out
    assert "gone=1" in out


def test_dbtime_rows_absent_when_the_plug_has_no_prepared_stats(capsys):
    """Completion condition 35 (mirrors R-79's own identical skip): a plug
    with no `prepared_stats` gets zero `DBTIME` lines and no exception,
    even though `measurement` (the `CPU` row's own data) is given.

    mutation M30 (`tools/perf_baseline.py`): call `_emit_dbtime_rows`
    unconditionally in `_emit_measurement_rows`, regardless of whether
    `adapter_obj` has `prepared_stats` -- this test's own `"DBTIME" not in
    out` assertion goes red (`AttributeError`/a stray `DBTIME` line)."""
    stub = SimpleNamespace(transport_kind="in_process")
    measurement = {
        "concurrency": 1, "requests": 1, "thread_limit": "default",
        "wall_ms": 0.0, "cpu_total_ms": 0.0, "cpu_main_ms": 0.0, "dbtime_pre": None,
    }
    pb._emit_measurement_rows("r2db-api", "r2db-api", "query", stub, prepared_detail=False, measurement=measurement)
    out = capsys.readouterr().out
    assert "DBTIME" not in out
    assert "CPU " in out


def test_dbtime_pre_snapshot_in_the_in_process_branch_is_after_warmup_before_measured():
    """Completion condition 37: on the in_process branch, the DBTIME PRE
    snapshot is taken after every warmup group has run and before the
    first measured group.

    mutation M32 (`tools/perf_baseline.py`): move `_capture_dbtime_pre`'s
    own call to before the warmup `_run_concurrent` line in the in_process
    branch of `_measure_op` -- this test's own `call_log[:pre_idx] ==
    ["call", "call"]` assertion goes red (`pre_idx` would be `0`)."""
    call_log: list[str] = []

    def fn() -> None:
        call_log.append("call")

    def prepared_stats():
        call_log.append("pre")
        return []

    stub = SimpleNamespace(transport_kind="in_process", prepared_stats=prepared_stats)
    pb._measure_op(fn, warmup=2, n=3, concurrency=1, counter=pb._CallCounter(), adapter_obj=stub)
    assert call_log.count("call") == 5
    pre_idx = call_log.index("pre")
    assert call_log[:pre_idx] == ["call", "call"]
    assert call_log[pre_idx + 1:] == ["call", "call", "call"]


def test_dbtime_pre_snapshot_in_the_real_loop_branch_is_after_warmup_before_measured():
    """Completion condition 38: on the real-loop (asgi/socket) branch, the
    DBTIME PRE snapshot is taken after warmup's own `_run_concurrent` call
    and before the measured one -- the SAME property condition 37 pins
    for the in_process branch, observed through a real `httpx.AsyncClient`
    + a real fresh event loop this time (never a mock): each request
    actually reaches a tiny ASGI app, which records a `"call"` tag in the
    SAME `call_log` the stub's own `prepared_stats()` records a `"pre"`
    tag into, so their real relative order is observable, not merely
    their total count (a mutation that only reorders WHEN `prepared_
    stats()` runs, without changing HOW MANY times it runs, would be
    invisible to a bare count).

    mutation M33 (`tools/perf_baseline.py`): move `_capture_dbtime_pre`'s
    own call to before the warmup `_run_concurrent` line in the real-loop
    branch of `_measure_op` -- this test's own `call_log[:pre_idx] ==
    ["call", "call"]` assertion goes red (`pre_idx` would be `0`)."""
    call_log: list[str] = []

    async def _logging_asgi_app(scope, receive, send) -> None:
        call_log.append("call")
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    def prepared_stats():
        call_log.append("pre")
        return []

    loop = asyncio.new_event_loop()
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=_logging_asgi_app), base_url="http://perfbaselinetest.invalid")
    stub = SimpleNamespace(transport_kind="asgi", _loop=loop, _client=client, prepared_stats=prepared_stats)

    def fn() -> None:
        request = client.build_request("GET", "/")
        loop.run_until_complete(client.send(request))

    try:
        pb._measure_op(fn, warmup=2, n=1, concurrency=1, counter=pb._CallCounter(), adapter_obj=stub)
    finally:
        loop.run_until_complete(client.aclose())
        loop.close()

    assert call_log.count("call") == 3
    pre_idx = call_log.index("pre")
    assert call_log[:pre_idx] == ["call", "call"]
    assert call_log[pre_idx + 1:] == ["call"]


def test_cpu_window_excludes_warmup_from_the_total(monkeypatch):
    """Completion condition 43: the CPU difference is taken strictly
    around the measured `_run_concurrent` call -- warmup's own CPU is
    never included.

    mutation M37 (`tools/perf_baseline.py`): move the `cpu_before`/
    `thread_before` reads to before the warmup `_run_concurrent` call in
    `_measure_op` -- this test's own `cpu_total_ms == pytest.approx(20.0)`
    assertion goes red (would read `50.0`, warmup's own 3 ticks folded
    in)."""
    counter = {"n": 0}

    def fake_getrusage(who):
        return SimpleNamespace(ru_utime=counter["n"] * 0.01, ru_stime=0.0)

    monkeypatch.setattr(pb.resource, "getrusage", fake_getrusage)
    monkeypatch.setattr(pb.time, "thread_time", lambda: counter["n"] * 0.01)

    def fn() -> None:
        counter["n"] += 1

    stub = SimpleNamespace(transport_kind="in_process")
    _, _, measured = pb._measure_op(fn, warmup=3, n=2, concurrency=1, counter=pb._CallCounter(), adapter_obj=stub)
    assert measured["cpu_total_ms"] == pytest.approx(20.0)
    assert measured["cpu_main_ms"] == pytest.approx(20.0)


def test_cpu_main_ms_is_the_thread_time_difference_not_getrusage(monkeypatch):
    """完了条件 42 の 2 つ目の部分 (コードレビュー 2 差し戻し 3 指摘 3):
    `cpu_main_ms` is `time.thread_time()`'s own difference across the
    measured window, never derived from `resource.getrusage`'s reading --
    distinct fake clocks on the two calls here, unlike `test_cpu_window_
    excludes_warmup_from_the_total` above (which advances both by the
    same amount and so cannot tell the two sources apart).

    mutation M108 (`tools/perf_baseline.py`): compute `cpu_main_ms` from
    `cpu_total_ms` instead of the `time.thread_time()` difference -- this
    test's own `cpu_main_ms == pytest.approx(2.0)` assertion goes red
    (would read `100.0`, `cpu_total_ms`'s own value)."""
    getrusage_values = iter([SimpleNamespace(ru_utime=0.0, ru_stime=0.0), SimpleNamespace(ru_utime=0.05, ru_stime=0.05)])
    monkeypatch.setattr(pb.resource, "getrusage", lambda who: next(getrusage_values))
    thread_time_values = iter([0.0, 0.002])
    monkeypatch.setattr(pb.time, "thread_time", lambda: next(thread_time_values))
    stub = SimpleNamespace(transport_kind="in_process")
    _, _, measured = pb._measure_op(lambda: None, warmup=0, n=1, concurrency=1, counter=pb._CallCounter(), adapter_obj=stub)
    assert measured["cpu_total_ms"] == pytest.approx(100.0)
    assert measured["cpu_main_ms"] == pytest.approx(2.0)


def test_cpu_wall_ms_is_the_measured_group_durations_only(monkeypatch):
    """Completion condition 44: the `CPU` row's own `wall_ms` is the sum
    of the MEASURED group durations only -- never warmup's.

    mutation M38 (`tools/perf_baseline.py`): compute `wall_ms` from every
    group `_run_concurrent` timed (warmup included) instead of the
    measured list alone -- this test's own `wall_ms == pytest.approx(
    5000.0)` assertion goes red (would read `105000.0`, the 100s warmup
    group folded in)."""
    perf_values = iter([0.0, 100.0, 100.0, 102.0, 102.0, 105.0])
    monkeypatch.setattr(pb.time, "perf_counter", lambda: next(perf_values))
    stub = SimpleNamespace(transport_kind="in_process")
    _, _, measured = pb._measure_op(lambda: None, warmup=1, n=2, concurrency=1, counter=pb._CallCounter(), adapter_obj=stub)
    assert measured["wall_ms"] == pytest.approx(5000.0)


def test_cpu_row_appears_for_an_in_process_plug(capsys):
    """Completion condition 45: the `CPU` row is printed for every plug,
    including an in_process one with no real event loop of its own.

    mutation M39 (`tools/perf_baseline.py`): print the `CPU` row only when
    `adapter_obj` has `_loop` -- this test's own `out.count("CPU ") == 1`
    assertion goes red (0 instead of 1)."""
    stub = SimpleNamespace(transport_kind="in_process")
    pb._measure_op_and_emit(
        lambda: None, peer="r2db-api", plug="r2db-api", op="query",
        warmup=0, n=1, concurrency=1, counter=pb._CallCounter(), adapter_obj=stub,
        prepared_detail=False, roundtrip_enabled=False, admin_conn=None, db_names={},
        correction_matcher=None, min_wait=0.0, poll_interval=0.0, max_wait=0.0,
    )
    out = capsys.readouterr().out
    assert out.count("CPU ") == 1


def test_cpu_row_prints_before_pool_dbtime_prepared_and_roundtrip(capsys):
    """Completion conditions 46/47: `CPU` prints before `POOL`, `DBTIME`
    prints after `POOL` and before `PREPARED`, and `ROUNDTRIP` prints
    last -- `CPU` -> `POOL` -> `DBTIME` -> `PREPARED` -> `ROUNDTRIP`.

    mutation M40 (`tools/perf_baseline.py`): print the `CPU` row from
    `_emit_measurement_rows` AFTER the `ROUNDTRIP` block instead of first
    -- this test's own `cpu_idx < pool_idx` assertion goes red.
    mutation M41 (`tools/perf_baseline.py`): print `DBTIME` lines from
    `_emit_measurement_rows` AFTER calling `_emit_prepared_rows` instead
    of before -- this test's own `dbtime_idx < prepared_idx` assertion
    goes red."""
    stub = SimpleNamespace(
        transport_kind="in_process",
        pool_stats=lambda: {"app1/runtime": {
            "size": 1, "acquire_count": 1, "wait_count": 0, "wait_total_ms": 0.0, "wait_max_ms": 0.0, "in_use_peak": 1,
        }},
        prepared_stats=lambda: [{
            "label": "app1/runtime@1", "execute_count": 1, "executemany_count": 0,
            "prepared": 0, "prepared_execs": 0, "prepared_statements": [], "probed": True,
            "db_wall_ms": 1.0, "txn_count": 1,
        }],
    )
    pb._measure_op_and_emit(
        lambda: None, peer="r2db-api", plug="r2db-api", op="query",
        warmup=0, n=1, concurrency=1, counter=pb._CallCounter(), adapter_obj=stub,
        prepared_detail=False, roundtrip_enabled=True, admin_conn=None, db_names={},
        correction_matcher=None, min_wait=0.0, poll_interval=0.0, max_wait=0.0,
    )
    out = capsys.readouterr().out
    cpu_idx = out.index("CPU ")
    pool_idx = out.index("POOL ")
    dbtime_idx = out.index("DBTIME ")
    prepared_idx = out.index("PREPARED ")
    roundtrip_idx = out.index("ROUNDTRIP ")
    assert cpu_idx < pool_idx < dbtime_idx < prepared_idx < roundtrip_idx


def test_measurement_requests_is_n_times_concurrency_never_warmup_plus_n(capsys):
    """Completion condition 48: `CPU`/`DBTIME`'s own `requests=` is `n *
    concurrency` (measured requests only) -- never `(warmup + n) *
    concurrency`, unlike `ROUNDTRIP`'s own `requests=`.

    mutation M42 (`tools/perf_baseline.py`): compute `measurement["
    requests"]` as `(warmup + n) * concurrency` in `_measure_op_and_emit`
    -- this test's own `requests=6` assertion goes red (would read
    `requests=21`)."""
    stub = SimpleNamespace(transport_kind="in_process")
    pb._measure_op_and_emit(
        lambda: None, peer="r2db-api", plug="r2db-api", op="query",
        warmup=5, n=2, concurrency=3, counter=pb._CallCounter(), adapter_obj=stub,
        prepared_detail=False, roundtrip_enabled=False, admin_conn=None, db_names={},
        correction_matcher=None, min_wait=0.0, poll_interval=0.0, max_wait=0.0,
    )
    out = capsys.readouterr().out
    assert "requests=6" in out
    assert "requests=21" not in out


def test_measurement_thread_limit_resolution(capsys):
    """Completion condition 41: `thread_limit=` reads the plug's own
    `perf_thread_limit()` when present and non-`None`, and falls back to
    the literal `default` both when the accessor is absent and when it
    returns `None`.

    mutation M35 (`tools/perf_baseline.py`): make `_measure_op_and_emit`
    always resolve `thread_limit` to `"default"`, never calling `adapter_
    obj.perf_thread_limit()` at all -- this test's own `"thread_limit=4"
    in out` assertion goes red (only `"thread_limit=default"` would ever
    appear)."""
    def _run(stub) -> str:
        pb._measure_op_and_emit(
            lambda: None, peer="r2db-api", plug="r2db-api", op="query",
            warmup=0, n=1, concurrency=1, counter=pb._CallCounter(), adapter_obj=stub,
            prepared_detail=False, roundtrip_enabled=False, admin_conn=None, db_names={},
            correction_matcher=None, min_wait=0.0, poll_interval=0.0, max_wait=0.0,
        )
        return capsys.readouterr().out

    assert "thread_limit=default" in _run(SimpleNamespace(transport_kind="in_process"))
    assert "thread_limit=default" in _run(SimpleNamespace(transport_kind="in_process", perf_thread_limit=lambda: None))
    assert "thread_limit=4" in _run(SimpleNamespace(transport_kind="in_process", perf_thread_limit=lambda: 4))


# ---------------------------------------------------------------------
# R-101 WP-1 差し戻し 2 (code review 1, F1/F4): the real-loop branch's own
# CPU window must exclude request capture, and the diff-computation tests
# below exercise `_emit_dbtime_rows`/`_measure_op` themselves rather than
# a formatter called with already-subtracted numbers.
# ---------------------------------------------------------------------


def test_cpu_window_in_the_real_loop_branch_excludes_capture(monkeypatch):
    """F1 (code review 1, highest priority): the real-loop branch's own
    CPU window starts AFTER every measured request has been captured
    (`_capture_one_request`, main-thread work building the request
    object) -- never before. `resource.getrusage`/`time.thread_time` are
    monkeypatched to a counter `fn` itself advances once per capture
    (never per real send, which goes through `_replay_factory` instead),
    so a capture folded into the window would show up as a nonzero delta.

    mutation (reviewer RV1, `tools/perf_baseline.py`): move `cpu_before`/
    `thread_before` back to right after warmup's own `_run_concurrent`
    call (before measured capture) -- this test's own `cpu_total_ms ==
    0.0` assertion goes red (the 3 measured captures would be counted).
    mutation (`tools/perf_baseline.py`): move the reads to before warmup's
    own `_run_concurrent` call entirely -- also goes red (warmup's own 2
    captures would be counted too)."""
    counter = {"n": 0}

    def fake_getrusage(who):
        return SimpleNamespace(ru_utime=counter["n"] * 0.01, ru_stime=0.0)

    monkeypatch.setattr(pb.resource, "getrusage", fake_getrusage)
    monkeypatch.setattr(pb.time, "thread_time", lambda: counter["n"] * 0.01)

    async def _noop_app(scope, receive, send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    loop = asyncio.new_event_loop()
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=_noop_app), base_url="http://perfbaselinetest.invalid")
    stub = SimpleNamespace(transport_kind="asgi", _loop=loop, _client=client)

    def fn() -> None:
        counter["n"] += 1  # simulates a capture's own main-thread CPU cost
        request = client.build_request("GET", "/")
        loop.run_until_complete(client.send(request))

    try:
        _, _, measured = pb._measure_op(fn, warmup=2, n=3, concurrency=1, counter=pb._CallCounter(), adapter_obj=stub)
    finally:
        loop.run_until_complete(client.aclose())
        loop.close()
    assert measured["cpu_total_ms"] == 0.0
    assert measured["cpu_main_ms"] == 0.0


def test_dbtime_platform_values_are_pre_post_differences_through_emit(capsys):
    """F4(a) (code review 1): `scope=platform`'s own `sessions`/`connect_
    wall_ms`/`db_calls`/`txns`/`db_wall_ms` are PRE/POST differences
    computed by `_emit_dbtime_rows` itself -- calling `_format_dbtime_
    platform_row` directly with already-subtracted numbers (completion
    condition 29's own test) cannot catch a missing subtraction upstream.

    mutation RV2 (`tools/perf_baseline.py`): use `post_platform_stats[
    "sessions"]` directly, without subtracting `pre_platform["sessions"]`
    -- this test's own `sessions=1` assertion goes red (would read
    `sessions=6`)."""
    measurement = {
        "concurrency": 1, "requests": 1,
        "dbtime_pre": {"conn_stats": [], "platform_stats": {
            "sessions": 5, "connect_wall_ms": 10.0, "db_wall_ms": 20.0, "txn_count": 3, "db_calls": 7,
        }},
    }
    post_platform_stats = {"sessions": 6, "connect_wall_ms": 14.0, "db_wall_ms": 26.0, "txn_count": 5, "db_calls": 10}
    pb._emit_dbtime_rows("r2db-api", "r2db-api", "query", measurement, [], post_platform_stats)
    out = capsys.readouterr().out
    assert "sessions=1 " in out
    assert "connect_wall_ms=4.000" in out
    assert "db_calls=3 " in out
    assert "txns=2 " in out
    assert "db_wall_ms=6.000 " in out


def test_dbtime_app_txns_and_db_calls_are_pre_post_differences(capsys):
    """F4(b) (code review 1): `scope=app`'s own `txns`/`db_calls` are
    PRE/POST differences too -- completion condition 30's own existing
    test pins only `db_wall_ms`.

    mutation RV4 (`tools/perf_baseline.py`): use the POST value directly
    for `txns`, without subtracting PRE -- this test's own `txns=2`
    assertion goes red (would read `txns=9`)."""
    measurement = {
        "concurrency": 1, "requests": 1,
        "dbtime_pre": {
            "conn_stats": [{"label": "a@1", "execute_count": 3, "executemany_count": 0, "db_wall_ms": 1.0, "txn_count": 7}],
            "platform_stats": None,
        },
    }
    post = [{"label": "a@1", "execute_count": 8, "executemany_count": 0, "db_wall_ms": 2.0, "txn_count": 9}]
    pb._emit_dbtime_rows("r2db-api", "r2db-api", "query", measurement, post, None)
    out = capsys.readouterr().out
    assert "db_calls=5 " in out
    assert "txns=2 " in out


def test_cpu_total_ms_includes_both_ru_utime_and_ru_stime(monkeypatch):
    """F4(c) (code review 1): `cpu_total_ms` is the `ru_utime + ru_stime`
    difference -- completion condition 42's own existing test used a stub
    with `ru_stime=0` on both reads, which cannot catch a mutation that
    drops `ru_stime` from the sum entirely.

    mutation RV3 (`tools/perf_baseline.py`): compute `cpu_total_ms` from
    `ru_utime` alone -- this test's own `cpu_total_ms == pytest.approx(
    1500.0)` assertion goes red (would read `1000.0`)."""
    values = iter([
        SimpleNamespace(ru_utime=1.0, ru_stime=0.5),
        SimpleNamespace(ru_utime=2.0, ru_stime=1.0),
    ])
    monkeypatch.setattr(pb.resource, "getrusage", lambda who: next(values))
    monkeypatch.setattr(pb.time, "thread_time", lambda: 0.0)
    stub = SimpleNamespace(transport_kind="in_process")
    _, _, measured = pb._measure_op(lambda: None, warmup=0, n=1, concurrency=1, counter=pb._CallCounter(), adapter_obj=stub)
    assert measured["cpu_total_ms"] == pytest.approx(1500.0)


# ---------------------------------------------------------------------
# Work order `docs/work-orders/WORK_ORDER_R101_SERIALIZATION_
# ATTRIBUTION_V1.md` §7.3 D-15 -- `--real-server`. Every test below
# drives `pb._run_real_server`/`pb._measure_real_server`/`pb._run_one_
# real_server_group` against a REAL, standard-library `http.server`
# stub (a separate OS process, `_start_realserver_stub_server` below --
# never a background thread in THIS process: a background thread
# before this file's own `forkserver`-based children start can wedge a
# child before it ever reaches its own `barrier.wait()`) and a stub
# launcher (a small generated module, `_write_realserver_stub_registry`
# below, with class-level `START_CALLS`/`STOP_CALLS` lists this process
# can read directly since the launcher itself runs in-process, unlike
# the HTTP stub).
# ---------------------------------------------------------------------

_REALSERVER_STUB_SERVER_SCRIPT = 'import http.server\nimport json\nimport os\nimport sys\nimport threading\nimport time\n\nconfig = json.loads(open(sys.argv[1], "r", encoding="utf-8").read())\nlog_path = sys.argv[2]\n_log_lock = threading.Lock()\n_counters_lock = threading.Lock()\n_counters = {"query_calls": 0}\n_rotation_lock = threading.Lock()\n_rotation_state = {"rotated": False, "new_control_secret": None}\n\n\ndef _append_log(entry):\n    with _log_lock:\n        with open(log_path, "a", encoding="utf-8") as f:\n            f.write(json.dumps(entry) + "\\n")\n\n\nclass Handler(http.server.BaseHTTPRequestHandler):\n    server_version = "realserverstub/1.0"\n    protocol_version = "HTTP/1.1"\n\n    def log_message(self, fmt, *args):\n        pass\n\n    def _read_body(self):\n        length = int(self.headers.get("Content-Length", 0))\n        raw = self.rfile.read(length) if length else b""\n        return json.loads(raw) if raw else {}\n\n    def _send(self, status, obj):\n        body = json.dumps(obj).encode("utf-8")\n        self.send_response(status)\n        self.send_header("Content-Type", "application/json")\n        self.send_header("Content-Length", str(len(body)))\n        self.end_headers()\n        self.wfile.write(body)\n\n    def do_GET(self):\n        start = time.time()\n        if self.path == "/v1/capabilities":\n            self._send(200, {\n                "application_scope": config.get("application_id", "perfapp"),\n                "contract_version": "1.11.0", "capabilities": {}, "limits": {},\n                "limit_enforcement": {}, "authorization_propagation_bound_ms": 0,\n            })\n        else:\n            self._send(404, {})\n        _append_log({\n            "path": self.path, "method": "GET",\n            "authorization": self.headers.get("Authorization"),\n            "start_ts": start, "end_ts": time.time(), "pid": os.getpid(),\n        })\n\n    def do_POST(self):\n        body = self._read_body()\n        path = self.path\n        start = time.time()\n        if path.startswith("/control/v1/credentials/") and path.endswith("/rotate"):\n            target_id = path[len("/control/v1/credentials/"):-len("/rotate")]\n            expected_id = config.get("control_credential_id", "ctl1")\n            new_secret = config.get("new_control_secret", "rotated-control-secret")\n            if target_id == expected_id:\n                with _rotation_lock:\n                    _rotation_state["rotated"] = True\n                    _rotation_state["new_control_secret"] = new_secret\n                self._send(200, {"credential_id": target_id, "secret": new_secret})\n            else:\n                self._send(403, {"error": "denied"})\n            _append_log({\n                "path": path, "method": "POST", "authorization": self.headers.get("Authorization"),\n                "start_ts": start, "end_ts": time.time(), "pid": os.getpid(),\n            })\n            return\n        if path == "/control/v1/credentials":\n            auth = self.headers.get("Authorization", "")\n            bearer = auth[len("Bearer "):] if auth.startswith("Bearer ") else auth\n            with _rotation_lock:\n                rotated = _rotation_state["rotated"]\n                new_secret = _rotation_state["new_control_secret"]\n            if not rotated or bearer != new_secret:\n                self._send(403, {"error": "must_rotate"})\n            else:\n                status = config.get("credential_status", 200)\n                if status == 200:\n                    self._send(200, {\n                        "credential_id": "cred1", "application_id": body.get("application_id"),\n                        "role": body.get("role"), "secret": "dev-secret-xyz",\n                    })\n                else:\n                    self._send(status, {"error": "denied"})\n            _append_log({\n                "path": path, "method": "POST", "authorization": self.headers.get("Authorization"),\n                "body": body, "start_ts": start, "end_ts": time.time(), "pid": os.getpid(),\n            })\n            return\n        if path == "/v1/schema/operations":\n            status = config.get("schema_status", 200)\n            if status == 200:\n                self._send(200, {"committed": True, "revision": "1", "request_id": "r1"})\n            else:\n                self._send(status, {"error": "denied"})\n            _append_log({\n                "path": path, "method": "POST", "authorization": self.headers.get("Authorization"),\n                "body": body, "start_ts": start, "end_ts": time.time(), "pid": os.getpid(),\n            })\n            return\n        if path.endswith("/mutations"):\n            status = config.get("mutation_status", 200)\n            if status == 200:\n                self._send(200, {"committed": True, "affected": 1, "request_id": "r2"})\n            else:\n                self._send(status, {"error": "denied"})\n            _append_log({\n                "path": path, "method": "POST", "authorization": self.headers.get("Authorization"),\n                "body": body, "start_ts": start, "end_ts": time.time(), "pid": os.getpid(),\n            })\n            return\n        if path.endswith("/query"):\n            with _counters_lock:\n                idx = _counters["query_calls"]\n                _counters["query_calls"] += 1\n            status = config.get("query_status_override", {}).get(str(idx), config.get("query_status", 200))\n            rows = config.get("query_rows_override", {}).get(str(idx), config.get("query_rows", 1))\n            delay_ms = config.get("query_delay_override", {}).get(str(idx), config.get("query_delay_ms", 0))\n            if delay_ms:\n                time.sleep(delay_ms / 1000.0)\n            if config.get("drop_at_index") == idx:\n                _append_log({\n                    "path": path, "method": "POST", "authorization": self.headers.get("Authorization"),\n                    "start_ts": start, "end_ts": time.time(), "pid": os.getpid(),\n                    "call_index": idx, "dropped": True,\n                })\n                self.close_connection = True\n                return\n            if status == 200:\n                self._send(200, {"items": [{"label": "x"} for _ in range(rows)], "request_id": "r3"})\n            else:\n                self._send(status, {"error": "denied"})\n            if idx in config.get("unparseable_log_indices", []):\n                with _log_lock:\n                    with open(log_path, "a", encoding="utf-8") as f:\n                        f.write("unparseable access line\\n")\n                return\n            _append_log({\n                "path": path, "method": "POST", "authorization": self.headers.get("Authorization"),\n                "start_ts": start, "end_ts": time.time(), "pid": os.getpid(), "call_index": idx,\n                "status": status,\n            })\n            return\n        self._send(404, {})\n        _append_log({\n            "path": path, "method": "POST", "authorization": self.headers.get("Authorization"),\n            "start_ts": start, "end_ts": time.time(), "pid": os.getpid(),\n        })\n\n\nhttpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)\nprint(httpd.server_port, flush=True)\nhttpd.serve_forever()\n'

_REALSERVER_STUB_LAUNCHER_TEMPLATE = 'import os\nimport signal\nimport subprocess\nimport sys\n\n\nclass StubLauncher:\n    name = {peer!r}\n    START_CALLS = []\n    START_WORKERS = []\n    STOP_CALLS = []\n\n    def __init__(self):\n        self._group_leader = None\n\n    def start(self, *, ceilings, workers=1):\n        type(self).START_CALLS.append(dict(ceilings))\n        type(self).START_WORKERS.append(workers)\n        self._group_leader = subprocess.Popen([sys.executable, \"-c\", \"import time; time.sleep(300)\"], start_new_session=True)\n\n    def stop(self):\n        type(self).STOP_CALLS.append(True)\n        if self._group_leader is not None:\n            try:\n                os.killpg(self._group_leader.pid, signal.SIGKILL)\n            except ProcessLookupError:\n                pass\n            self._group_leader.wait(timeout=30)\n            self._group_leader = None\n\n    def access_log_line_count(self):\n        return 0\n\n    def access_log_pids_for_status(self, status, *, since=0):\n        return []\n\n    @property\n    def data_base_url(self):\n        return {data_base_url!r}\n\n    @property\n    def control_base_url(self):\n        return {control_base_url!r}\n\n    @property\n    def runtime_bearer(self):\n        return {runtime_bearer!r}\n\n    @property\n    def control_bearer(self):\n        return {control_bearer!r}\n\n    @property\n    def control_credential_id(self):\n        return {control_credential_id!r}\n'

_realserver_module_counter = itertools.count()


def _start_realserver_stub_server(tmp_path, config):
    script_path = tmp_path / "realserver_stub_server.py"
    if not script_path.exists():
        script_path.write_text(_REALSERVER_STUB_SERVER_SCRIPT, encoding="utf-8")
    idx = next(_realserver_module_counter)
    config_path = tmp_path / f"realserver_stub_config_{idx}.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    log_path = tmp_path / f"realserver_stub_log_{idx}.jsonl"
    log_path.write_text("", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, str(script_path), str(config_path), str(log_path)],
        stdout=subprocess.PIPE, text=True,
    )
    port = int(proc.stdout.readline().strip())
    base_url = f"http://127.0.0.1:{port}"
    return base_url, log_path, proc


def _stop_realserver_stub_server(proc):
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)


def _read_realserver_log(log_path):
    lines = [line for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [json.loads(line) for line in lines]


def _write_realserver_stub_registry(
    tmp_path, *, peer, base_url, runtime_bearer="runtime-secret", control_bearer="control-secret", control_credential_id="ctl1",
):
    idx = next(_realserver_module_counter)
    module_name = f"realserver_stub_launcher_{idx}"
    stub_dir = tmp_path / "realserver_stub_registry"
    stub_dir.mkdir(exist_ok=True)
    module_src = _REALSERVER_STUB_LAUNCHER_TEMPLATE.format(
        peer=peer, data_base_url=f"{base_url}/v1", control_base_url=f"{base_url}/control/v1",
        runtime_bearer=runtime_bearer, control_bearer=control_bearer, control_credential_id=control_credential_id,
    )
    (stub_dir / f"{module_name}.py").write_text(module_src, encoding="utf-8")
    if str(stub_dir) not in sys.path:
        sys.path.insert(0, str(stub_dir))
    registry_path = stub_dir / f"{module_name}_registry.json"
    registry_path.write_text(json.dumps({
        "adapters": [],
        "composition_roots": [{"name": peer, "module": module_name, "launcher_class": "StubLauncher"}],
    }), encoding="utf-8")
    launcher_module = importlib.import_module(module_name)
    return registry_path, launcher_module.StubLauncher


def _realserver_args(pb_module, *, peer, registry_path, client_processes=None, concurrency=1, warmup=0, n=1):
    argv = ["--real-server", peer, "--concurrency", str(concurrency), "--warmup", str(warmup), "--n", str(n), "--registry", str(registry_path)]
    if client_processes is not None:
        argv += ["--client-processes", str(client_processes)]
    return pb_module._build_parser().parse_args(argv)


def _realserver_setup(tmp_path, config=None, *, peer="stubpeer", **launcher_kwargs):
    base_url, log_path, proc = _start_realserver_stub_server(tmp_path, config or {})
    registry_path, launcher_cls = _write_realserver_stub_registry(tmp_path, peer=peer, base_url=base_url, **launcher_kwargs)
    return base_url, log_path, proc, registry_path, launcher_cls


def test_real_server_starts_the_named_launcher(tmp_path):
    """Completion condition 127: `--real-server <peer>` instantiates and
    starts the `composition_roots` entry named `peer`.

    mutation M170 (`tools/perf_baseline.py`): `_load_composition_root_
    class` ignores `registry_path`'s own entries and imports a fixed
    module name instead -- red because this test's own peer/module never
    exists under that fixed name, so `_run_real_server` raises an import
    error instead of ever calling `StubLauncher.start`."""
    base_url, log_path, proc, registry_path, launcher_cls = _realserver_setup(tmp_path)
    try:
        args = _realserver_args(pb, peer="stubpeer", registry_path=registry_path, client_processes=1, concurrency=1)
        code = pb._run_real_server(args)
        assert code == 0
        assert len(launcher_cls.START_CALLS) == 1
    finally:
        _stop_realserver_stub_server(proc)


def test_real_server_start_ceilings_are_one_and_one(tmp_path):
    """Completion condition 128: `launcher.start` is called with
    `ceilings={"data": 1, "control": 1}`.

    mutation M171 (`tools/perf_baseline.py`): pass `ceilings={"data": 2,
    "control": 1}` -- red because this test's own `== {"data": 1,
    "control": 1}` assertion observes `2` instead."""
    base_url, log_path, proc, registry_path, launcher_cls = _realserver_setup(tmp_path)
    try:
        args = _realserver_args(pb, peer="stubpeer", registry_path=registry_path, client_processes=1, concurrency=1)
        pb._run_real_server(args)
        assert launcher_cls.START_CALLS == [{"data": 1, "control": 1}]
    finally:
        _stop_realserver_stub_server(proc)


def test_real_server_stops_exactly_once_on_mid_measurement_failure(tmp_path):
    """Completion condition 129: a failure partway through measurement
    (here, the SECOND measured query response is a 500) still calls
    `launcher.stop()` exactly once.

    mutation M172 (`tools/perf_baseline.py`): move the `launcher.stop()`
    call so it only runs on the success path -- red because this test's
    own failing run observes `STOP_CALLS == []` instead of one call."""
    config = {"query_status_override": {"2": 500}}
    base_url, log_path, proc, registry_path, launcher_cls = _realserver_setup(tmp_path, config)
    try:
        args = _realserver_args(pb, peer="stubpeer", registry_path=registry_path, client_processes=2, concurrency=2, warmup=0, n=1)
        code = pb._run_real_server(args)
        assert code != 0
        assert len(launcher_cls.STOP_CALLS) == 1
    finally:
        _stop_realserver_stub_server(proc)


def test_real_server_stops_exactly_once_on_success(tmp_path):
    """Completion condition 130: a normal, fully successful run also
    calls `launcher.stop()` exactly once.

    mutation M173 (`tools/perf_baseline.py`): drop the success-path
    `launcher.stop()` call -- red because this test's own `STOP_CALLS ==
    [True]` assertion observes `[]` instead."""
    base_url, log_path, proc, registry_path, launcher_cls = _realserver_setup(tmp_path)
    try:
        args = _realserver_args(pb, peer="stubpeer", registry_path=registry_path, client_processes=1, concurrency=1)
        code = pb._run_real_server(args)
        assert code == 0
        assert launcher_cls.STOP_CALLS == [True]
    finally:
        _stop_realserver_stub_server(proc)


def test_real_server_measures_only_query(tmp_path, capsys):
    """Completion condition 131: after entity/row setup, every data-plane
    request the stub observed is a `query` request, and exactly one
    `REALPERF` line (`op=query`) is printed.

    mutation M174 (`tools/perf_baseline.py`): also measure a second op
    (e.g. `insert`) -- red because this test's own count of `REALPERF`
    lines in stdout is no longer exactly 1."""
    base_url, log_path, proc, registry_path, launcher_cls = _realserver_setup(tmp_path)
    try:
        args = _realserver_args(pb, peer="stubpeer", registry_path=registry_path, client_processes=1, concurrency=1, warmup=0, n=1)
        code = pb._run_real_server(args)
        assert code == 0
        out = capsys.readouterr().out
        realperf_lines = [line for line in out.splitlines() if line.startswith("REALPERF")]
        assert len(realperf_lines) == 1
        assert "op=query" in realperf_lines[0]
        entries = _read_realserver_log(log_path)
        mutation_idx = next(i for i, e in enumerate(entries) if e["path"].endswith("/mutations"))
        for entry in entries[mutation_idx + 1:]:
            assert entry["path"].endswith("/query")
    finally:
        _stop_realserver_stub_server(proc)


def _spy_group_client_pids(monkeypatch):
    """Test helper: wraps `pb._run_one_real_server_group` so a test can
    inspect each call's own OBSERVED `messages` (each carrying the real
    OS `pid` the SAME call actually spawned that child under) after the
    run -- a real process boundary, never a value this helper computes
    independently. Returns the list of per-call `messages` lists, in
    call order (index 0 = the first group, warmup or not)."""
    observed = []
    real_run_group = pb._run_one_real_server_group

    def _spy(*a, **k):
        result = real_run_group(*a, **k)
        observed.append(result["messages"])
        return result

    monkeypatch.setattr(pb, "_run_one_real_server_group", _spy)
    return observed


def test_real_server_default_client_processes_is_eight(tmp_path, capsys, monkeypatch):
    """Completion condition 132: at `--concurrency 32` with `--client-
    processes` omitted, 8 distinct client OS processes are observed, and
    the printed `REALPERF` line carries `client_processes=8` (the SAME
    observed count, `_measure_real_server`'s own `client_processes` --
    never a `min(client_processes, concurrency)` formula the printed row
    could drift from, code review 1 F1).

    mutation M175 (`tools/perf_baseline.py`): change `--client-processes`'s
    own default to `4` -- red because this test's own `client_
    processes=8` assertion observes `client_processes=4` instead.
    mutation RV1-132 (`tools/perf_baseline.py`): `_spawn_real_server_
    clients` always spawns exactly TWO real child processes regardless of
    its own `n_children` argument -- red because `_run_one_real_server_
    group` still waits for 8 (the caller's own `n_children`) queue
    messages that only 2 real processes ever send, so `result_queue.
    get()` times out after `_REAL_SERVER_QUEUE_TIMEOUT_S` (60s) and
    `_run_real_server` returns 1; this test's own `assert code == 0`
    fails on that non-zero exit, well before it ever reaches the
    `client_processes=8`/pid-count assertions below."""
    observed_pids = _spy_group_client_pids(monkeypatch)
    base_url, log_path, proc, registry_path, launcher_cls = _realserver_setup(tmp_path)
    try:
        args = _realserver_args(pb, peer="stubpeer", registry_path=registry_path, concurrency=32, warmup=0, n=1)
        code = pb._run_real_server(args)
        assert code == 0
        out = capsys.readouterr().out
        realperf_line = next(line for line in out.splitlines() if line.startswith("REALPERF"))
        assert "client_processes=8" in realperf_line
        entries = _read_realserver_log(log_path)
        measured_query_entries = [e for e in entries if e["path"].endswith("/query") and e.get("call_index", 0) >= 1]
        assert len(measured_query_entries) == 32
        observed_child_pids = {message["pid"] for message in observed_pids[-1]}
        assert len(observed_child_pids) == 8
        assert os.getpid() not in observed_child_pids
    finally:
        _stop_realserver_stub_server(proc)


def test_real_server_k1_uses_one_client_process(tmp_path, capsys, monkeypatch):
    """Completion condition 133: at `--concurrency 1`, exactly one client
    process is used (`min(8, 1)`), and `REALPERF` carries `client_
    processes=1` -- the SAME observed count (code review 1 F1).

    mutation M176 (`tools/perf_baseline.py`): always start `--client-
    processes` children regardless of `K` -- red because this test's own
    `client_processes=1` assertion observes `client_processes=8` instead.
    mutation RV1-133 (`tools/perf_baseline.py`): `_spawn_real_server_
    clients` always spawns exactly TWO real child processes regardless of
    its own `n_children` argument -- red because this test's own
    observed pid count (a real OS-process boundary, never a formula)
    becomes 2, not 1, and `client_processes=1` no longer holds
    either."""
    observed_pids = _spy_group_client_pids(monkeypatch)
    base_url, log_path, proc, registry_path, launcher_cls = _realserver_setup(tmp_path)
    try:
        args = _realserver_args(pb, peer="stubpeer", registry_path=registry_path, concurrency=1, warmup=0, n=1)
        code = pb._run_real_server(args)
        assert code == 0
        out = capsys.readouterr().out
        realperf_line = next(line for line in out.splitlines() if line.startswith("REALPERF"))
        assert "client_processes=1" in realperf_line
        observed_child_pids = {message["pid"] for message in observed_pids[-1]}
        assert len(observed_child_pids) == 1
        assert os.getpid() not in observed_child_pids
    finally:
        _stop_realserver_stub_server(proc)


def test_real_server_client_process_pids_are_stable_across_every_group(tmp_path, monkeypatch):
    """The work order's §6.1 監督裁定 17 (D-15a): one run's own client OS processes are
    spawned exactly ONCE (`_spawn_real_server_clients`) and serve every group of that run --
    warmup AND measured alike -- never respawned per group. Pinned against the REAL,
    observed OS `pid` each group's own messages carry (`_spy_group_client_pids`, a real
    process boundary, never a value this test computes independently): across a run with
    two warmup groups and two measured groups, the pid SET observed in every single group
    is identical to the pid set observed in the first. After the run, every one of those
    pids is actually dead (`os.kill(pid, 0)` raises `ProcessLookupError`) -- `_stop_real_
    server_clients` (called from `_measure_real_server`'s own `finally`) has already
    joined them by the time `_run_real_server` returns, never left running past that point.

    mutation M215 (`tools/perf_baseline.py`): spawn a fresh set of client processes for
    every group instead of once for the whole run -- red because this test's own per-group
    pid-set equality assertion fails (each group's own observed pid set becomes disjoint
    from the first group's).
    mutation M217 (`tools/perf_baseline.py`): `_stop_real_server_clients` returns
    immediately, without ever calling `barrier.abort()` or joining a process -- red because
    this test's own `os.kill(pid, 0)` check finds a live process instead of `ProcessLookup
    Error` (the children only exit later, on their own 60s barrier timeout, well after this
    test has already made its assertion)."""
    observed_pids = _spy_group_client_pids(monkeypatch)
    base_url, log_path, proc, registry_path, launcher_cls = _realserver_setup(tmp_path)
    try:
        args = _realserver_args(pb, peer="stubpeer", registry_path=registry_path, client_processes=2, concurrency=2, warmup=2, n=2)
        code = pb._run_real_server(args)
        assert code == 0
        assert len(observed_pids) == 4
        first_group_pids = {message["pid"] for message in observed_pids[0]}
        assert len(first_group_pids) == 2
        for messages in observed_pids[1:]:
            assert {message["pid"] for message in messages} == first_group_pids
        for pid in first_group_pids:
            with pytest.raises(ProcessLookupError):
                os.kill(pid, 0)
    finally:
        _stop_realserver_stub_server(proc)


def test_real_server_group_sends_k_requests_concurrently(tmp_path):
    """Completion condition 134: a measured group's own `K` requests are
    genuinely simultaneous -- with each `/query` response held for 50ms,
    the maximum observed in-flight overlap among them is `K`.

    mutation M177 (`tools/perf_baseline.py`): a child sends its own share
    one request at a time (sequential `await`) instead of via one `gather`
    -- red because this test's own observed max overlap drops below `K`."""
    config = {"query_delay_ms": 50}
    base_url, log_path, proc, registry_path, launcher_cls = _realserver_setup(tmp_path, config)
    try:
        args = _realserver_args(pb, peer="stubpeer", registry_path=registry_path, client_processes=2, concurrency=4, warmup=0, n=1)
        code = pb._run_real_server(args)
        assert code == 0
        entries = _read_realserver_log(log_path)
        query_entries = [e for e in entries if e["path"].endswith("/query")]
        events = []
        for e in query_entries:
            events.append((e["start_ts"], 1))
            events.append((e["end_ts"], -1))
        events.sort()
        current = 0
        peak = 0
        for _, delta in events:
            current += delta
            peak = max(peak, current)
        assert peak == 4
    finally:
        _stop_realserver_stub_server(proc)


def test_group_wall_ms_is_max_completion_minus_start():
    """Completion condition 135: `_group_wall_ms` is the LATEST completion
    time minus the single shared start, never an average.

    mutation M178 (`tools/perf_baseline.py`): average the completion times
    instead of taking their max -- red because this test's own known
    input (`start=1_000_000`, completions `[1_500_000, 1_200_000,
    1_800_000]`) would then read `0.5` ms, not `0.8` ms."""
    result = pb._group_wall_ms(1_000_000, [1_500_000, 1_200_000, 1_800_000])
    assert result == pytest.approx(0.8)


def test_real_server_group_start_is_the_min_of_childrens_own_time_ns(tmp_path):
    """Completion condition 135/136 (code review 1 F5, supervisor
    ruling -- 採る): a group's own start is the MINIMUM of the
    children's own `time.time_ns()`, each read immediately after ITS
    OWN `multiprocessing.Barrier.wait()` returns -- never the parent's
    own post-barrier `time.time_ns()`, which lags the first child to
    resume by however long the parent itself takes to wake and
    re-schedule. Pinned against `_run_one_real_server_group`'s own
    real, per-child `t0`/`t1` (`messages`) -- an independent ground
    truth this test computes `wall_ms` from itself, never a value this
    test fabricates. The work order's §6.1 監督裁定 17: the client
    processes are spawned once (`_spawn_real_server_clients`) and
    stopped once (`_stop_real_server_clients`), around the single
    `_run_one_real_server_group` call this test makes.

    mutation M210 (`tools/perf_baseline.py`): use the PARENT's own
    `time.time_ns()`, read after `result_queue.get()` has already
    collected every child's report, as the group's start instead --
    red because this test's own `wall_ms == pytest.approx(expected_
    wall_ms)` assertion (computed from the children's own reported
    `t0`/`t1`) no longer holds (the parent's own late timestamp makes
    the printed span far shorter than the real one)."""
    base_url, log_path, proc, registry_path, launcher_cls = _realserver_setup(tmp_path)
    try:
        query_url = f"{base_url}/v1/data/dsaperfreal/query"
        processes, barrier, result_queue = pb._spawn_real_server_clients(query_url, "runtime-secret", "label", [1, 1], 2)
        try:
            result = pb._run_one_real_server_group(barrier, result_queue, 2)
        finally:
            pb._stop_real_server_clients(processes, barrier)
        min_child_t0 = min(message["t0"] for message in result["messages"])
        max_child_t1 = max(message["t1"] for message in result["messages"])
        expected_wall_ms = (max_child_t1 - min_child_t0) / 1_000_000.0
        assert result["wall_ms"] == pytest.approx(expected_wall_ms)
    finally:
        _stop_realserver_stub_server(proc)


def test_real_server_warmup_group_excluded_from_realperf(tmp_path):
    """Completion condition 137: a slow WARMUP group never enters the
    printed `REALPERF` distribution -- only the measured group's own
    (fast) wall time does.

    mutation M179 (`tools/perf_baseline.py`): fold the warmup group's own
    wall time into the measured distribution too -- red because this
    test's own `p95_ms < 100` assertion would instead observe a value
    inflated by the warmup group's own 200ms delay."""
    config = {"query_delay_override": {"0": 200, "1": 200}}
    base_url, log_path, proc, registry_path, launcher_cls = _realserver_setup(tmp_path, config)
    try:
        args = _realserver_args(pb, peer="stubpeer", registry_path=registry_path, client_processes=2, concurrency=2, warmup=1, n=1)
        result = pb._measure_real_server(
            query_url=f"{base_url}/v1/data/dsaperfreal/query", bearer="runtime-secret", field="label",
            warmup=args.warmup, n=args.n, concurrency=args.concurrency,
            n_children=pb._num_real_server_clients(args.client_processes, args.concurrency),
            counts=pb._distribute_group_counts(args.concurrency, pb._num_real_server_clients(args.client_processes, args.concurrency)),
        )
        assert result["p95_ms"] < 100.0
    finally:
        _stop_realserver_stub_server(proc)


def test_measure_real_server_percentiles_use_percentile(monkeypatch):
    """Completion condition 138: `p50_ms`/`p95_ms` are `_percentile` of the
    measured group wall times -- pinned via a monkeypatched `_run_one_
    real_server_group` so the input list is exactly known (no real HTTP).

    mutation M180 (`tools/perf_baseline.py`): print the MEAN of the
    measured wall times as `p50_ms` -- red because this test's own
    known, ASYMMETRIC input (`[10, 20, 100]`) has a true median
    (`_percentile(..., 50)`) of `20.0` but a mean of `43.33`; the
    mutation would observe the latter, failing the `p50_ms ==
    pytest.approx(20.0)` assertion (a symmetric input, where the two
    coincide, could not catch this)."""
    walls = iter([{"wall_ms": 10.0, "cpu_client_ms": 0.0, "statuses": [200], "client_processes": 1},
                  {"wall_ms": 20.0, "cpu_client_ms": 0.0, "statuses": [200], "client_processes": 1},
                  {"wall_ms": 100.0, "cpu_client_ms": 0.0, "statuses": [200], "client_processes": 1}])
    monkeypatch.setattr(pb, "_run_one_real_server_group", lambda *a, **k: next(walls))
    result = pb._measure_real_server(
        query_url="http://example.invalid/v1/data/e/query", bearer="x", field="label",
        warmup=0, n=3, concurrency=1, n_children=1, counts=[1],
    )
    assert result["p50_ms"] == pytest.approx(20.0)
    assert result["p95_ms"] == pytest.approx(92.0)


def test_format_realperf_row_is_stable():
    """Completion condition 139: `REALPERF`'s own literal column names,
    order, and formatting (work order `docs/work-orders/WORK_ORDER_
    R101_SERIALIZATION_ATTRIBUTION_V1.md` §7.3 D-15).

    mutation M181 (`tools/perf_baseline.py`): rename the `client_
    processes=` column to `clients=` -- red because this test's own
    substring assertion for `client_processes=8` is absent from the
    mutated line."""
    line = pb._format_realperf_row("r2db-api", 32, 8, 15, 12.345, 20.5)
    assert line == (
        "REALPERF peer=r2db-api plug=r2db-api-real transport=real-server op=query "
        "concurrency=32 client_processes=8 n=15 p50_ms=12.345 p95_ms=20.500"
    )


def test_format_realcpu_row_is_stable():
    """Completion condition 140: `REALCPU`'s own literal column names,
    order, and formatting (work order `docs/work-orders/WORK_ORDER_
    R101_SERIALIZATION_ATTRIBUTION_V1.md` §7.3 D-15).

    mutation M182 (`tools/perf_baseline.py`): rename `cpu_client_ms=` to
    `client_cpu_ms=` -- red because this test's own exact-string
    assertion no longer matches."""
    line = pb._format_realcpu_row("r2db-api", 32, 8, 480, 123.456, 78.9)
    assert line == (
        "REALCPU peer=r2db-api plug=r2db-api-real op=query concurrency=32 "
        "client_processes=8 requests=480 wall_ms=123.456 cpu_client_ms=78.900"
    )


_REALSERVER_BUSY_LOOP_ITERATIONS_PER_REQUEST = 300_000


def _stub_busy_loop_client_worker(count, _query_url, _bearer, _field, barrier, result_queue):
    """Test-only child worker (completion condition 141, code review 1
    F2; loop shape from the work order's §6.1 監督裁定 17): burns a
    FIXED, known amount of CPU per request via a tight loop instead of
    making a real HTTP call, so a test can independently cross-check
    `_run_one_real_server_group`'s own `getrusage`-based `cpu_ms`
    against a `time.process_time()` ground truth this worker reports
    back alongside it -- never the real `_one`/httpx path. Serves every
    group (warmup or measured alike) the SAME persistent child process
    would, running the SAME loop each time; only the caller decides
    which served groups count as measured. Runs until the parent's own
    `barrier.abort()` breaks it out of its next `barrier.wait()`."""
    while True:
        try:
            barrier.wait(timeout=60.0)
        except pb.threading.BrokenBarrierError:
            return
        started_ns = pb.time.time_ns()
        before_rusage = pb.resource.getrusage(pb.resource.RUSAGE_SELF)
        before_process_time = pb.time.process_time()
        total = 0
        for _ in range(count):
            for _ in range(_REALSERVER_BUSY_LOOP_ITERATIONS_PER_REQUEST):
                total += 1
        after_rusage = pb.resource.getrusage(pb.resource.RUSAGE_SELF)
        after_process_time = pb.time.process_time()
        cpu_ms = ((after_rusage.ru_utime + after_rusage.ru_stime) - (before_rusage.ru_utime + before_rusage.ru_stime)) * 1000.0
        process_time_ms = (after_process_time - before_process_time) * 1000.0
        result_queue.put({
            "t0": started_ns,
            "t1": pb.time.time_ns(),
            "cpu_ms": cpu_ms,
            "statuses": [200] * count,
            "row_counts": [1] * count,
            "pid": os.getpid(),
            "process_time_ms": process_time_ms,
        })


def test_real_server_cpu_client_ms_is_the_childrens_own_rusage_sum(tmp_path, capsys, monkeypatch):
    """Completion condition 141: `cpu_client_ms` is the SUM of the
    MEASURED children's own `getrusage(RUSAGE_SELF)` deltas, excluding
    warmup -- pinned against `_stub_busy_loop_client_worker` (a
    known, fixed amount of CPU per request) so this test can
    independently verify the printed `cpu_client_ms` against a `time.
    process_time()` ground truth within ±20%, and confirm it stays
    SMALLER than that ground truth with the warmup group's own CPU
    folded in too (code review 1 F2; the supervisor's ruling drops the
    earlier 'parent's own startup CPU' comparison this test used to
    rely on).

    mutation M183 (`tools/perf_baseline.py`): report the PARENT's own
    `RUSAGE_SELF` delta as `cpu_client_ms` instead of the children's sum
    -- red because the printed value no longer tracks the known,
    per-child busy-loop ground truth at all.
    mutation M209 (`tools/perf_baseline.py`): fold the warmup group's
    own `cpu_client_ms` into the total too -- red because the printed
    value then EXCEEDS the measured-only ground truth."""
    base_url, log_path, proc, registry_path, launcher_cls = _realserver_setup(tmp_path)
    monkeypatch.setattr(pb, "_real_server_client_worker", _stub_busy_loop_client_worker)
    observed_groups = []
    real_run_group = pb._run_one_real_server_group

    def _spy_run_group(*a, **k):
        result = real_run_group(*a, **k)
        observed_groups.append(result)
        return result

    monkeypatch.setattr(pb, "_run_one_real_server_group", _spy_run_group)
    try:
        args = _realserver_args(pb, peer="stubpeer", registry_path=registry_path, client_processes=2, concurrency=4, warmup=1, n=1)
        code = pb._run_real_server(args)
        assert code == 0
        out = capsys.readouterr().out
        realcpu_line = next(line for line in out.splitlines() if line.startswith("REALCPU"))
        printed_cpu_ms = float(realcpu_line.split("cpu_client_ms=")[1])
        assert len(observed_groups) == 2
        warmup_ground_truth = sum(m["process_time_ms"] for m in observed_groups[0]["messages"])
        measured_ground_truth = sum(m["process_time_ms"] for m in observed_groups[1]["messages"])
        assert measured_ground_truth > 0.0
        assert printed_cpu_ms == pytest.approx(measured_ground_truth, rel=0.2)
        assert printed_cpu_ms < measured_ground_truth + warmup_ground_truth
    finally:
        _stop_realserver_stub_server(proc)


def test_real_server_warmup_import_cost_does_not_leak_into_measured_cpu(tmp_path, monkeypatch):
    """The work order's §6.1 監督裁定 17 (D-15a): a client
    process's own one-time httpcore anyio-backend import (paid once, on the FIRST real
    request any persistent client process ever sends, never per group) lands inside
    whichever group happens first -- a warmup group, for this `--warmup 1` run -- and is
    EXCLUDED from every later group's own `cpu_client_ms`, because the CPU baseline is
    taken FRESH at the top of every group (never held over from an earlier one). Pinned
    against the REAL child worker (`_real_server_client_worker`, never a synthetic
    stand-in, which cannot exercise httpcore's own real import cost) via `_run_one_real_
    server_group`'s own reported per-group `cpu_client_ms` (`_spy_group_client_pids`'s own
    spy wrapper, reused here for its `messages`): the warmup group's own summed `cpu_
    client_ms` is larger than EVERY measured group's own.

    mutation M216 (`tools/perf_baseline.py`): take the CPU baseline once, before the
    child's own per-group loop starts, instead of freshly at the top of every iteration --
    red because every group's own reported `cpu_ms` becomes CUMULATIVE from that one stale
    baseline (it never stops including the warmup group's own import cost, and keeps
    growing group over group), so the first measured group's own `cpu_client_ms` exceeds
    the warmup group's instead of staying smaller."""
    observed_groups = []
    real_run_group = pb._run_one_real_server_group

    def _spy(*a, **k):
        result = real_run_group(*a, **k)
        observed_groups.append(result)
        return result

    monkeypatch.setattr(pb, "_run_one_real_server_group", _spy)
    base_url, log_path, proc, registry_path, launcher_cls = _realserver_setup(tmp_path)
    try:
        args = _realserver_args(pb, peer="stubpeer", registry_path=registry_path, client_processes=1, concurrency=1, warmup=1, n=2)
        code = pb._run_real_server(args)
        assert code == 0
        assert len(observed_groups) == 3
        warmup_cpu_ms = observed_groups[0]["cpu_client_ms"]
        measured_cpu_ms = [g["cpu_client_ms"] for g in observed_groups[1:]]
        assert measured_cpu_ms  # OC 1.5-32 (空振り禁止): at least one measured group observed
        assert all(warmup_cpu_ms > m for m in measured_cpu_ms)
    finally:
        _stop_realserver_stub_server(proc)


def test_measure_real_server_requests_and_wall_ms_are_measured_only(monkeypatch):
    """Completion condition 142: `requests=` is the number of MEASURED
    responses actually observed (`n * concurrency` when every measured
    group is complete, never a bare formula on its own -- code review 1
    F6), `wall_ms=` is the sum of MEASURED group walls only -- pinned
    via a monkeypatched `_run_one_real_server_group` with a huge,
    distinguishable warmup wall time.

    mutation M184 (`tools/perf_baseline.py`): fold the warmup group's
    own responses into `requests=` too -- red because this test's own
    `result["requests"] == 6` assertion (n=2, concurrency=3) would
    instead observe `9` (warmup=1)."""
    groups = iter([
        {"wall_ms": 9999.0, "cpu_client_ms": 0.0, "statuses": [200, 200, 200], "client_processes": 1},
        {"wall_ms": 10.0, "cpu_client_ms": 0.0, "statuses": [200, 200, 200], "client_processes": 1},
        {"wall_ms": 20.0, "cpu_client_ms": 0.0, "statuses": [200, 200, 200], "client_processes": 1},
    ])
    monkeypatch.setattr(pb, "_run_one_real_server_group", lambda *a, **k: next(groups))
    result = pb._measure_real_server(
        query_url="http://example.invalid/v1/data/e/query", bearer="x", field="label",
        warmup=1, n=2, concurrency=3, n_children=1, counts=[3],
    )
    assert result["requests"] == 6
    assert result["wall_ms"] == pytest.approx(30.0)


def test_measure_real_server_aborts_on_a_short_measurement(monkeypatch):
    """Code review 1 F6 (`OC` 1.5-32): a run whose measured groups
    report fewer responses than `n * concurrency` refuses to print a
    row that would understate its own measurement -- it raises
    `RealServerMeasurementFailure` instead."""
    groups = iter([
        {"wall_ms": 10.0, "cpu_client_ms": 0.0, "statuses": [200, 200], "client_processes": 1},
    ])
    monkeypatch.setattr(pb, "_run_one_real_server_group", lambda *a, **k: next(groups))
    with pytest.raises(pb.RealServerMeasurementFailure):
        pb._measure_real_server(
            query_url="http://example.invalid/v1/data/e/query", bearer="x", field="label",
            warmup=0, n=1, concurrency=3, n_children=1, counts=[3],
        )


def test_real_server_aborts_without_output_on_non_200(tmp_path, capsys):
    """Completion condition 143: any non-200 `query` response aborts the
    WHOLE run -- no `REALPERF`/`REALCPU` line, a non-zero exit, and
    `stop()` still called.

    mutation M185 (`tools/perf_baseline.py`): never check the response
    status code at all -- red because this test's own `code != 0` and
    `no REALPERF/REALCPU line` assertions would instead observe a
    (wrong) successful, 0-exit run with both lines printed."""
    config = {"query_status_override": {"1": 500}}
    base_url, log_path, proc, registry_path, launcher_cls = _realserver_setup(tmp_path, config)
    try:
        args = _realserver_args(pb, peer="stubpeer", registry_path=registry_path, client_processes=1, concurrency=1, warmup=0, n=1)
        code = pb._run_real_server(args)
        assert code != 0
        out = capsys.readouterr().out
        assert "REALPERF" not in out
        assert "REALCPU" not in out
        assert launcher_cls.STOP_CALLS == [True]
    finally:
        _stop_realserver_stub_server(proc)


def test_real_server_flag_absent_prints_no_real_lines(tmp_path, capsys, monkeypatch):
    """Completion condition 144 (v1.0 §1.1 (f)): without `--real-server`,
    `main()` never prints `REALPERF`/`REALCPU` and never instantiates the
    stub launcher -- pinned by spying on `pb._load_composition_root_
    class` itself (the real-server path's own entry point into the
    registry), never on a registry entry name matching `args.real_
    server`'s own `None` default, which no real peer name ever does and
    would only red via an unrelated `RealServerMeasurementFailure`
    lookup-miss instead of the assertion below (code review 1 F3).

    mutation M186 (`tools/perf_baseline.py`): run the real-server path
    even when `--real-server` was not given -- red because this test's
    own `load_calls == []` assertion (was the real-server registry
    lookup ever entered at all) observes a call instead."""
    base_url, log_path, proc, registry_path, launcher_cls = _realserver_setup(tmp_path)
    load_calls = []
    real_load = pb._load_composition_root_class

    def _spy_load(*a, **k):
        load_calls.append(True)
        return real_load(*a, **k)

    monkeypatch.setattr(pb, "_load_composition_root_class", _spy_load)
    try:
        base = tmp_path / "pgbase"
        base.mkdir()
        monkeypatch.setattr(pb.dsa_testpg, "_base_dir", lambda *a, **k: base)
        monkeypatch.setattr(pb.dsa_testpg, "cluster", _fake_cluster_cm())
        code = pb.main(["--registry", str(registry_path)])
        assert code == 0
        out = capsys.readouterr().out
        assert "REALPERF" not in out
        assert "REALCPU" not in out
        assert load_calls == []
        assert launcher_cls.START_CALLS == []
    finally:
        _stop_realserver_stub_server(proc)


def test_real_server_path_runs_under_the_suite_lock_and_owned_cluster(tmp_path, monkeypatch):
    """Completion condition 145: `--real-server` runs under the SAME
    exclusive `dsa_testpg.suite_lock` and owned `dsa_testpg.cluster` the
    6-plug path does -- both are spied (delegating to the real/faked
    implementation) so this test can assert `["lock", "cluster"]` was the
    real ENTRY order, never assert on a side effect (a probe subprocess)
    that a mutation moving the whole dispatch earlier would just skip
    right past.

    mutation M187 (`tools/perf_baseline.py`): dispatch `_run_real_server`
    immediately after `print(_perfrun_line())`, before `dsa_testpg.suite_
    lock`/`cluster` are ever reached -- red because this test's own
    `calls == ["lock", "cluster"]` assertion observes `[]` instead (a
    `--real-server` run that returns without ever entering either)."""
    base_url, log_path, proc, registry_path, launcher_cls = _realserver_setup(tmp_path)
    try:
        base = tmp_path / "pgbase2"
        base.mkdir()
        monkeypatch.setattr(pb.dsa_testpg, "_base_dir", lambda *a, **k: base)

        calls: list[str] = []
        real_suite_lock = pb.dsa_testpg.suite_lock

        @contextlib.contextmanager
        def spy_suite_lock(*a, **k):
            calls.append("lock")
            with real_suite_lock(*a, **k):
                yield

        fake_cluster = _fake_cluster_cm()

        @contextlib.contextmanager
        def spy_cluster():
            calls.append("cluster")
            with fake_cluster() as c:
                yield c

        monkeypatch.setattr(pb.dsa_testpg, "suite_lock", spy_suite_lock)
        monkeypatch.setattr(pb.dsa_testpg, "cluster", spy_cluster)

        code = pb.main(["--real-server", "stubpeer", "--client-processes", "1", "--registry", str(registry_path)])
        assert code == 0
        assert calls == ["lock", "cluster"]
    finally:
        _stop_realserver_stub_server(proc)


def test_real_server_issues_developer_credential_before_entity(tmp_path):
    """Completion condition 164: before entity setup, the stub observes a
    `POST /control/v1/credentials` (role `developer`) authorized by the
    launcher's own control credential, rotated first (the launcher's
    `control_bearer` starts `must_rotate=true` and cannot authorize
    `issue_credential` on its own).

    mutation M201 (`tools/perf_baseline.py`): never issue a developer
    credential -- use `runtime_bearer` for the schema operation instead --
    red because this test's own log-based assertion (a credentials POST
    with `Authorization: Bearer rotated-control-secret` precedes the
    schema POST) finds no such entry at all."""
    base_url, log_path, proc, registry_path, launcher_cls = _realserver_setup(tmp_path)
    try:
        args = _realserver_args(pb, peer="stubpeer", registry_path=registry_path, client_processes=1, concurrency=1)
        code = pb._run_real_server(args)
        assert code == 0
        entries = _read_realserver_log(log_path)
        cred_idx = next(i for i, e in enumerate(entries) if e["path"] == "/control/v1/credentials")
        schema_idx = next(i for i, e in enumerate(entries) if e["path"] == "/v1/schema/operations")
        assert cred_idx < schema_idx
        assert entries[cred_idx]["authorization"] == "Bearer rotated-control-secret"
        assert entries[cred_idx]["body"]["role"] == "developer"
    finally:
        _stop_realserver_stub_server(proc)


def test_real_server_rotates_the_control_credential_before_issuing_developer_credential(tmp_path):
    """the work order's §6.1 監督裁定 15 (the rotate step of the credential
    flow, completion condition 164's side): before the developer
    credential is issued, the stub observes a `POST /control/v1/
    credentials/<control_credential_id>/rotate` authorized by the
    launcher's own (pre-rotation) `control_bearer` -- the launcher's
    control credential starts `must_rotate=true`, so no other control-
    plane call (`issue_credential` included) succeeds until this runs.

    mutation M212 (`tools/perf_baseline.py`): drop the rotate call
    entirely -- red because the stub's must_rotate gate then 403s the
    developer-credential POST (it never observes a rotated secret), so
    `code == 0` goes red before this test's own log-based rotate
    assertion is ever reached."""
    base_url, log_path, proc, registry_path, launcher_cls = _realserver_setup(tmp_path)
    try:
        args = _realserver_args(pb, peer="stubpeer", registry_path=registry_path, client_processes=1, concurrency=1)
        code = pb._run_real_server(args)
        assert code == 0
        entries = _read_realserver_log(log_path)
        rotate_idx = next(i for i, e in enumerate(entries) if e["path"] == "/control/v1/credentials/ctl1/rotate")
        cred_idx = next(i for i, e in enumerate(entries) if e["path"] == "/control/v1/credentials")
        assert rotate_idx < cred_idx
        assert entries[rotate_idx]["authorization"] == "Bearer control-secret"
    finally:
        _stop_realserver_stub_server(proc)


def test_real_server_issues_developer_credential_with_the_rotated_secret(tmp_path):
    """the work order's §6.1 監督裁定 15 (the rotate step of the credential
    flow, completion condition 164's side): the developer-credential
    issuance is authorized by the NEW secret the rotate call returned --
    never the launcher's original `control_bearer`.

    mutation M213 (`tools/perf_baseline.py`): issue the developer
    credential with the launcher's original `control_bearer` instead of
    the rotated secret -- red because the stub's must_rotate gate 403s
    any credentials POST that does not carry the post-rotate secret, so
    `code == 0` goes red before this test's own `Authorization`
    assertion is even reached."""
    base_url, log_path, proc, registry_path, launcher_cls = _realserver_setup(
        tmp_path, {"new_control_secret": "rotated-secret-for-this-test"},
    )
    try:
        args = _realserver_args(pb, peer="stubpeer", registry_path=registry_path, client_processes=1, concurrency=1)
        code = pb._run_real_server(args)
        assert code == 0
        entries = _read_realserver_log(log_path)
        cred_entry = next(e for e in entries if e["path"] == "/control/v1/credentials")
        assert cred_entry["authorization"] == "Bearer rotated-secret-for-this-test"
    finally:
        _stop_realserver_stub_server(proc)


def test_real_server_rotate_uses_the_launchers_own_control_credential_id(tmp_path):
    """the work order's §6.1 監督裁定 15 (the rotate step of the credential
    flow, completion condition 164's side): the rotate call's path
    `credential_id` is read from the launcher's own `control_credential_
    id` -- never a fixed literal -- so a launcher whose id differs from
    the common default still rotates successfully.

    mutation M214 (`tools/perf_baseline.py`): rotate a fixed literal id
    (the common default `"ctl1"`) instead of reading `launcher.control_
    credential_id` -- red because this test's launcher/stub pair share a
    DIFFERENT id (`"custom-ctl-id-7"`), so the fixed-literal rotate call
    403s against the stub's own `control_credential_id` check and the
    whole run fails (`code == 0` goes red)."""
    base_url, log_path, proc, registry_path, launcher_cls = _realserver_setup(
        tmp_path, {"control_credential_id": "custom-ctl-id-7"}, control_credential_id="custom-ctl-id-7",
    )
    try:
        args = _realserver_args(pb, peer="stubpeer", registry_path=registry_path, client_processes=1, concurrency=1)
        code = pb._run_real_server(args)
        assert code == 0
        entries = _read_realserver_log(log_path)
        assert any(e["path"] == "/control/v1/credentials/custom-ctl-id-7/rotate" for e in entries)
    finally:
        _stop_realserver_stub_server(proc)


def test_real_server_schema_and_seed_use_the_developer_credential(tmp_path):
    """Completion condition 165: the schema operation and the row-seeding
    mutation both carry the developer credential's own secret, never
    `control_bearer`/`runtime_bearer`.

    mutation M202 (`tools/perf_baseline.py`): use `control_bearer` for the
    schema operation and the row seed -- red because this test's own
    `Authorization` assertions (`Bearer dev-secret-xyz`) observe `Bearer
    control-secret` instead."""
    base_url, log_path, proc, registry_path, launcher_cls = _realserver_setup(tmp_path)
    try:
        args = _realserver_args(pb, peer="stubpeer", registry_path=registry_path, client_processes=1, concurrency=1)
        code = pb._run_real_server(args)
        assert code == 0
        entries = _read_realserver_log(log_path)
        schema_entry = next(e for e in entries if e["path"] == "/v1/schema/operations")
        mutation_entry = next(e for e in entries if e["path"].endswith("/mutations"))
        assert schema_entry["authorization"] == "Bearer dev-secret-xyz"
        assert mutation_entry["authorization"] == "Bearer dev-secret-xyz"
    finally:
        _stop_realserver_stub_server(proc)


def test_real_server_query_requests_use_the_runtime_credential(tmp_path):
    """Completion condition 166: every measured `query` request (K=1
    sanity check included) carries the launcher's own `runtime_bearer`.

    mutation M203 (`tools/perf_baseline.py`): use the developer credential
    for the measurement `query` calls -- red because this test's own
    `all(... == "Bearer runtime-secret")` assertion over the stub's
    `/query` log entries finds a `Bearer dev-secret-xyz` entry instead."""
    base_url, log_path, proc, registry_path, launcher_cls = _realserver_setup(tmp_path)
    try:
        args = _realserver_args(pb, peer="stubpeer", registry_path=registry_path, client_processes=1, concurrency=1, warmup=0, n=2)
        code = pb._run_real_server(args)
        assert code == 0
        entries = _read_realserver_log(log_path)
        query_entries = [e for e in entries if e["path"].endswith("/query")]
        assert len(query_entries) >= 1
        assert all(e["authorization"] == "Bearer runtime-secret" for e in query_entries)
    finally:
        _stop_realserver_stub_server(proc)


def test_real_server_refuses_a_200_with_zero_rows(tmp_path, capsys):
    """Completion condition 167 (`OC` 1.5-32): the K=1 sanity query
    returning 200 with zero rows aborts the run exactly like a non-200
    status would -- no `REALPERF`/`REALCPU`, non-zero exit, `stop()`
    still called.

    mutation M204 (`tools/perf_baseline.py`): only check the status code,
    never the row count -- red because this test's own `code != 0`
    assertion would instead observe a (wrongly) successful run."""
    config = {"query_rows_override": {"0": 0}}
    base_url, log_path, proc, registry_path, launcher_cls = _realserver_setup(tmp_path, config)
    try:
        args = _realserver_args(pb, peer="stubpeer", registry_path=registry_path, client_processes=1, concurrency=1)
        code = pb._run_real_server(args)
        assert code != 0
        out = capsys.readouterr().out
        assert "REALPERF" not in out
        assert "REALCPU" not in out
        assert launcher_cls.STOP_CALLS == [True]
    finally:
        _stop_realserver_stub_server(proc)


def test_real_server_client_processes_flag_caps_at_k(tmp_path, capsys, monkeypatch):
    """Completion condition 168: `--client-processes 8` with `K=4` uses 4
    children (`min(8, 4)`), and `REALPERF` carries `client_processes=4`
    -- the SAME observed count (code review 1 F1).

    mutation M205 (`tools/perf_baseline.py`): use `N` (the flag's own
    value) directly instead of `min(N, K)` -- red because this test's own
    `client_processes=4` assertion observes `client_processes=8` instead.
    mutation RV1-168 (`tools/perf_baseline.py`): `_spawn_real_server_
    clients` always spawns exactly TWO real child processes regardless of
    its own `n_children` argument -- red because `_run_one_real_server_
    group` still waits for 4 (the caller's own `n_children`) queue
    messages that only 2 real processes ever send, so `result_queue.
    get()` times out after `_REAL_SERVER_QUEUE_TIMEOUT_S` (60s) and
    `_run_real_server` returns 1; this test's own `assert code == 0`
    fails on that non-zero exit, well before it ever reaches the
    `client_processes=4`/pid-count assertions below."""
    observed_pids = _spy_group_client_pids(monkeypatch)
    base_url, log_path, proc, registry_path, launcher_cls = _realserver_setup(tmp_path)
    try:
        args = _realserver_args(pb, peer="stubpeer", registry_path=registry_path, client_processes=8, concurrency=4, warmup=0, n=1)
        code = pb._run_real_server(args)
        assert code == 0
        out = capsys.readouterr().out
        realperf_line = next(line for line in out.splitlines() if line.startswith("REALPERF"))
        assert "client_processes=4" in realperf_line
        observed_child_pids = {message["pid"] for message in observed_pids[-1]}
        assert len(observed_child_pids) == 4
        assert os.getpid() not in observed_child_pids
    finally:
        _stop_realserver_stub_server(proc)


def test_distribute_group_counts_gives_the_remainder_to_the_first_children():
    """Completion condition 169: `K=10, N=4` distributes `[3, 3, 2, 2]` --
    the remainder (2) goes to the FIRST 2 children, never the last.

    mutation M206 (`tools/perf_baseline.py`): give the remainder to the
    LAST children instead -- red because this test's own `== [3, 3, 2,
    2]` assertion would instead observe `[2, 2, 3, 3]`."""
    assert pb._distribute_group_counts(10, 4) == [3, 3, 2, 2]


def test_real_server_never_builds_registered_adapters(tmp_path):
    """Completion condition 170: `--real-server` never builds a registered
    `adapters` entry -- the registry's own `adapters` list can carry a
    stub adapter that RECORDS if it were ever built, and it never is.

    mutation M207 (`tools/perf_baseline.py`): also call `_discover_and_
    build` for `--real-server` -- red because this test's own stub
    adapter module records a `build_adapter()` call that should never
    happen."""
    base_url, log_path, proc, registry_path, launcher_cls = _realserver_setup(tmp_path)
    try:
        stub_dir = registry_path.parent
        idx = next(_realserver_module_counter)
        adapter_module_name = f"realserver_stub_adapter_{idx}"
        record_path = stub_dir / f"{adapter_module_name}_built.json"
        (stub_dir / f"{adapter_module_name}.py").write_text(
            "import json, pathlib\n"
            f"RECORD_PATH = pathlib.Path({str(record_path)!r})\n"
            "def build_adapter():\n"
            "    RECORD_PATH.write_text('built')\n"
            "    raise RuntimeError('a --real-server run must never reach this')\n",
            encoding="utf-8",
        )
        data = json.loads(registry_path.read_text())
        data["adapters"] = [{"name": "stubadapter", "module": adapter_module_name, "required": False}]
        registry_path.write_text(json.dumps(data), encoding="utf-8")

        args = _realserver_args(pb, peer="stubpeer", registry_path=registry_path, client_processes=1, concurrency=1)
        code = pb._run_real_server(args)
        assert code == 0
        assert not record_path.exists()
    finally:
        _stop_realserver_stub_server(proc)


def test_real_server_prints_realperf_and_realcpu_as_one_block_after_perfrun(tmp_path, capsys, monkeypatch):
    """Completion condition 171: `PERFRUN` precedes `REALPERF`/`REALCPU`,
    and the two `REAL*` lines are adjacent -- no other line between them.

    mutation M208 (`tools/perf_baseline.py`): print `REALPERF`/`REALCPU`
    BEFORE `PERFRUN` -- red because this test's own ordering assertion
    (the `PERFRUN` line's own index is less than `REALPERF`'s) fails."""
    base_url, log_path, proc, registry_path, launcher_cls = _realserver_setup(tmp_path)
    try:
        base = tmp_path / "pgbase3"
        base.mkdir()
        monkeypatch.setattr(pb.dsa_testpg, "_base_dir", lambda *a, **k: base)
        monkeypatch.setattr(pb.dsa_testpg, "cluster", _fake_cluster_cm())
        code = pb.main(["--real-server", "stubpeer", "--client-processes", "1", "--registry", str(registry_path)])
        assert code == 0
        out = capsys.readouterr().out
        lines = out.splitlines()
        perfrun_idx = next(i for i, line in enumerate(lines) if line.startswith("PERFRUN"))
        realperf_idx = next(i for i, line in enumerate(lines) if line.startswith("REALPERF"))
        realcpu_idx = next(i for i, line in enumerate(lines) if line.startswith("REALCPU"))
        assert perfrun_idx < realperf_idx
        assert realcpu_idx == realperf_idx + 1
    finally:
        _stop_realserver_stub_server(proc)


def test_real_server_n_must_be_at_least_one(capsys):
    """Code review 1 re-check observation (差し戻し 2 (5)): at `--n 0`
    under `--real-server`, no measured group would ever run, so
    `_measure_real_server`'s own `client_processes` would stay `None`
    (never set by any measured group) and `REALPERF`/`REALCPU` would
    print `client_processes=None` -- refused up front instead, the same
    way `--concurrency`/`--client-processes` already refuse below 1.
    Raised before any registry/network access, so no stub server or
    registry is needed here.

    mutation M211 (`tools/perf_baseline.py`): drop the `--n >= 1` check
    for `--real-server` -- red because this test's own `SystemExit`
    assertion (`pb.main` exits 2 via `argparse`'s own `parser.error`)
    no longer holds."""
    with pytest.raises(SystemExit) as exc_info:
        pb.main(["--real-server", "stubpeer", "--n", "0", "--registry", "/nonexistent/registry.json"])
    assert exc_info.value.code == 2
    err = capsys.readouterr().err
    assert "--n must be >= 1" in err


# ---------------------------------------------------------------------
# `--real-server <peer> --workers N`. A second stub launcher
# (`_REALSERVER_GROUP_STUB_LAUNCHER_TEMPLATE`) starts a REAL process
# group on `start()`: a supervisor in its own session that forks
# `workers` children, the same shape a uvicorn `--workers N` supervisor
# has, and stops it with `os.killpg` on `stop()`. Its access-log methods
# read the stub HTTP server's own JSONL log -- each line's pid and the
# status the server recorded as sent -- so the per-worker counts come
# from a real responding pid; a line that is not JSON is never returned
# for any status.
# ---------------------------------------------------------------------

_REALSERVER_GROUP_STUB_LAUNCHER_TEMPLATE = '''
import json
import os
import signal
import subprocess
import sys
import time

_SUPERVISOR = (
    "import os, signal, sys, time\\n"
    "children = []\\n"
    "for _ in range(int(sys.argv[1])):\\n"
    "    pid = os.fork()\\n"
    "    if pid == 0:\\n"
    "        while True:\\n"
    "            time.sleep(60)\\n"
    "    children.append(pid)\\n"
    "def _stop(signum, frame):\\n"
    "    for child in children:\\n"
    "        try:\\n"
    "            os.kill(child, signal.SIGTERM)\\n"
    "        except ProcessLookupError:\\n"
    "            pass\\n"
    "    for child in children:\\n"
    "        try:\\n"
    "            os.waitpid(child, 0)\\n"
    "        except ChildProcessError:\\n"
    "            pass\\n"
    "    os._exit(0)\\n"
    "signal.signal(signal.SIGTERM, _stop)\\n"
    "while True:\\n"
    "    time.sleep(60)\\n"
)

# A supervisor that forks its workers into its own group and then exits:
# the workers keep the group, the supervisor stays an unreaped zombie
# child of the process that started it.
_EXITING_SUPERVISOR = (
    "import os, sys, time\\n"
    "for _ in range(int(sys.argv[1])):\\n"
    "    if os.fork() == 0:\\n"
    "        while True:\\n"
    "            time.sleep(60)\\n"
    "os._exit(0)\\n"
)


def _group_members(pgid):
    out = subprocess.run(["ps", "-A", "-o", "pid=,pgid="], capture_output=True, text=True).stdout
    members = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 2 and int(parts[1]) == pgid:
            members.append(int(parts[0]))
    return members


def _is_zombie(pid):
    out = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True, timeout=30).stdout
    return out.strip().startswith("Z")


_LAST_STABLE = {{}}


def _read_log_lines(path):
    with open(path, "r", encoding="utf-8") as f:
        return [line for line in f.read().splitlines() if line.strip()]


def _stable_log_lines(path):
    # The stub HTTP server appends its log line after it has answered, so
    # a read waits until the file stops growing; a read equal to the last
    # stable one returns at once.
    last = _read_log_lines(path)
    if _LAST_STABLE.get(path) == last:
        return last
    deadline = time.monotonic() + 5.0
    while True:
        time.sleep(0.3)
        lines = _read_log_lines(path)
        if lines == last or time.monotonic() >= deadline:
            _LAST_STABLE[path] = lines
            return lines
        last = lines


class StubLauncher:
    name = {peer!r}
    START_CALLS = []
    START_WORKERS = []
    START_ENVIRON = []
    GROUP_MEMBERS_AT_START = []
    SUPERVISORS = []
    STOP_CALLS = []
    EXITED_LEADER_GROUPS = []
    LEAVE_GROUP_RUNNING = {leave_group_running!r}
    ZOMBIE_ON_STOP = {zombie_on_stop!r}
    LEADER_EXITS_DURING_START = {leader_exits_during_start!r}

    def __init__(self):
        self._supervisor = None

    def start(self, *, ceilings, workers=1):
        cls = type(self)
        cls.START_CALLS.append(dict(ceilings))
        cls.START_WORKERS.append(workers)
        cls.START_ENVIRON.append(dict(os.environ))
        self._supervisor = subprocess.Popen(
            [sys.executable, "-c", _SUPERVISOR, str(workers)], start_new_session=True,
        )
        cls.SUPERVISORS.append(self._supervisor)
        members = []
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            members = _group_members(self._supervisor.pid)
            if len(members) >= workers + 1:
                break
            time.sleep(0.05)
        cls.GROUP_MEMBERS_AT_START.append(len(members))
        if cls.LEADER_EXITS_DURING_START:
            # A second group whose leader exits before start() returns;
            # stop() below never signals it.
            exiting = subprocess.Popen(
                [sys.executable, "-c", _EXITING_SUPERVISOR, str(workers)], start_new_session=True,
            )
            cls.SUPERVISORS.append(exiting)
            cls.EXITED_LEADER_GROUPS.append(exiting.pid)
            deadline = time.monotonic() + 30.0
            while time.monotonic() < deadline:
                if _is_zombie(exiting.pid) and len(_group_members(exiting.pid)) >= workers + 1:
                    break
                time.sleep(0.05)

    def stop(self):
        type(self).STOP_CALLS.append(True)
        if self._supervisor is None or type(self).LEAVE_GROUP_RUNNING:
            return
        if type(self).ZOMBIE_ON_STOP:
            # SIGKILL the whole group and never wait(): the supervisor
            # stays a zombie child of this process (its own pgid), and
            # its worker, reparented, is reaped by the system.
            os.killpg(self._supervisor.pid, signal.SIGKILL)
            self._supervisor = None
            return
        try:
            os.killpg(self._supervisor.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        self._supervisor.wait(timeout=30)
        self._supervisor = None

    def access_log_line_count(self):
        return len(_stable_log_lines({server_log!r}))

    def access_log_pids_for_status(self, status, *, since=0):
        pids = []
        for line in _stable_log_lines({server_log!r})[since:]:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if entry.get("dropped"):
                continue
            if entry.get("status") == status:
                pids.append(entry["pid"])
        return pids

    @property
    def data_base_url(self):
        return {data_base_url!r}

    @property
    def control_base_url(self):
        return {control_base_url!r}

    @property
    def runtime_bearer(self):
        return "runtime-secret"

    @property
    def control_bearer(self):
        return "control-secret"

    @property
    def control_credential_id(self):
        return "ctl1"
'''


def _realserver_group_setup(
    tmp_path, config=None, *, peer="stubpeer", leave_group_running=False, zombie_on_stop=False,
    leader_exits_during_start=False,
):
    config = config or {}
    base_url, log_path, proc = _start_realserver_stub_server(tmp_path, config)
    idx = next(_realserver_module_counter)
    module_name = f"realserver_group_stub_launcher_{idx}"
    stub_dir = tmp_path / "realserver_group_stub_registry"
    stub_dir.mkdir(exist_ok=True)
    module_src = _REALSERVER_GROUP_STUB_LAUNCHER_TEMPLATE.format(
        peer=peer, leave_group_running=leave_group_running, zombie_on_stop=zombie_on_stop,
        leader_exits_during_start=leader_exits_during_start, server_log=str(log_path),
        data_base_url=f"{base_url}/v1", control_base_url=f"{base_url}/control/v1",
    )
    (stub_dir / f"{module_name}.py").write_text(module_src, encoding="utf-8")
    if str(stub_dir) not in sys.path:
        sys.path.insert(0, str(stub_dir))
    registry_path = stub_dir / f"{module_name}_registry.json"
    registry_path.write_text(json.dumps({
        "adapters": [],
        "composition_roots": [{"name": peer, "module": module_name, "launcher_class": "StubLauncher"}],
    }), encoding="utf-8")
    launcher_cls = importlib.import_module(module_name).StubLauncher
    return log_path, proc, registry_path, launcher_cls


def _kill_stub_groups(launcher_cls):
    """Test cleanup: kills every stub supervisor's process group that is
    still alive (a run that never stopped its launcher leaves one)."""
    import signal

    for supervisor in launcher_cls.SUPERVISORS:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(supervisor.pid, signal.SIGKILL)
        with contextlib.suppress(subprocess.TimeoutExpired):
            supervisor.wait(timeout=10)


def _realserver_workers_args(pb_module, *, registry_path, workers=None, concurrency=1, warmup=0, n=1, client_processes=1):
    argv = [
        "--real-server", "stubpeer", "--concurrency", str(concurrency), "--warmup", str(warmup), "--n", str(n),
        "--client-processes", str(client_processes), "--registry", str(registry_path),
    ]
    if workers is not None:
        argv += ["--workers", str(workers)]
    return pb_module._build_parser().parse_args(argv)


def test_real_server_workers_starts_the_launcher_with_n_workers_and_data_ceiling_n(tmp_path):
    """`--real-server <peer> --workers 4` starts the launcher with
    `workers=4` and declared ceilings data = 4, control = 1, and the
    launcher's own supervisor then runs 4 children (the stub's real
    process group has 5 members: the supervisor plus 4).

    mutation M146 (`tools/perf_baseline.py`): call `launcher.start`
    without `workers=` -- red because `START_WORKERS` observes `[1]` and
    the group has 2 members instead of 5."""
    log_path, proc, registry_path, launcher_cls = _realserver_group_setup(tmp_path)
    try:
        args = _realserver_workers_args(pb, registry_path=registry_path, workers=4)
        code = pb._run_real_server(args)
        assert code == 0
        assert launcher_cls.START_CALLS == [{"data": 4, "control": 1}]
        assert launcher_cls.START_WORKERS == [4]
        assert launcher_cls.GROUP_MEMBERS_AT_START == [5]
    finally:
        _kill_stub_groups(launcher_cls)
        _stop_realserver_stub_server(proc)


def test_real_server_workers_without_real_server_is_an_argument_error(tmp_path, capsys, monkeypatch):
    """`--workers` without `--real-server` is an argument error (exit 2),
    raised before the suite lock, the cluster or any registry access.

    mutation M147 (`tools/perf_baseline.py`): drop the `--workers requires
    --real-server` check -- red because `main()` then runs the 6-plug
    path against the empty registry and returns 0 instead of exiting 2."""
    base = tmp_path / "pgbase-workers"
    base.mkdir()
    monkeypatch.setattr(pb.dsa_testpg, "_base_dir", lambda *a, **k: base)
    monkeypatch.setattr(pb.dsa_testpg, "cluster", _fake_cluster_cm())
    registry = tmp_path / "registry-empty.json"
    registry.write_text(json.dumps({"adapters": []}), encoding="utf-8")
    with pytest.raises(SystemExit) as exc_info:
        pb.main(["--workers", "2", "--registry", str(registry)])
    assert exc_info.value.code == 2
    assert "--workers requires --real-server" in capsys.readouterr().err


def test_real_server_workers_must_be_at_least_one(capsys):
    """`--real-server --workers 0` is an argument error (exit 2), refused
    the same way `--client-processes 0` is."""
    with pytest.raises(SystemExit) as exc_info:
        pb.main(["--real-server", "stubpeer", "--workers", "0", "--registry", "/nonexistent/registry.json"])
    assert exc_info.value.code == 2
    assert "--workers must be >= 1" in capsys.readouterr().err


def _realworkers_lines(out):
    return [line for line in out.splitlines() if line.startswith("REALWORKERS ")]


def test_real_server_output_carries_the_worker_count(tmp_path, capsys):
    """The run's output carries N: a `--workers 1` run and a `--workers 4`
    run differ in their output by `workers=1` / `workers=4`, and each run
    prints exactly one line naming its own N.

    mutation M148 (`tools/perf_baseline.py`): drop `workers=` from the
    `REALWORKERS` line -- red because neither run's output then contains
    `workers=<N>`."""
    outputs = {}
    for workers in (1, 4):
        base_url, log_path, proc, registry_path, launcher_cls = _realserver_setup(tmp_path)
        try:
            args = _realserver_workers_args(pb, registry_path=registry_path, workers=workers)
            code = pb._run_real_server(args)
            assert code == 0
            assert launcher_cls.START_WORKERS == [workers]
            outputs[workers] = capsys.readouterr().out
        finally:
            _stop_realserver_stub_server(proc)
    for workers, out in outputs.items():
        lines = _realworkers_lines(out)
        assert len(lines) == 1, out
        assert f" workers={workers} " in lines[0]
    assert _realworkers_lines(outputs[1]) != _realworkers_lines(outputs[4])


def test_real_server_prints_per_worker_200_counts_after_the_run(tmp_path, capsys):
    """After the run, one `REALWORKERS` line follows `REALPERF`/`REALCPU`
    and carries, per responding pid from the launcher's access log, the
    number of 200 responses of the warmup and measured groups only: here
    (1 + 2) groups x K=2 = 6, all from the stub server's own pid, the 6
    setup requests before the first warmup group excluded.

    mutation M149 (`tools/perf_baseline.py`): never print the
    `REALWORKERS` line -- red because no such line is found."""
    log_path, proc, registry_path, launcher_cls = _realserver_group_setup(tmp_path)
    try:
        args = _realserver_workers_args(pb, registry_path=registry_path, workers=2, concurrency=2, warmup=1, n=2)
        code = pb._run_real_server(args)
        assert code == 0
        lines = capsys.readouterr().out.splitlines()
        realworkers = [i for i, line in enumerate(lines) if line.startswith("REALWORKERS ")]
        assert len(realworkers) == 1, lines
        realcpu_idx = next(i for i, line in enumerate(lines) if line.startswith("REALCPU "))
        assert realworkers[0] == realcpu_idx + 1
        assert lines[realworkers[0]] == (
            f"REALWORKERS peer=stubpeer plug=stubpeer-real workers=2 concurrency=2 pids=1 "
            f"accepted_200={proc.pid}:6 non_200=- unclassified=0"
        )
    finally:
        _kill_stub_groups(launcher_cls)
        _stop_realserver_stub_server(proc)


def test_real_server_stopped_run_still_prints_its_worker_line(tmp_path, capsys):
    """A run a non-200 response stops still prints its `REALWORKERS` line
    (with its N), never `REALPERF`/`REALCPU`, and exits non-zero."""
    config = {"query_status_override": {"1": 429}}
    base_url, log_path, proc, registry_path, launcher_cls = _realserver_setup(tmp_path, config)
    try:
        args = _realserver_workers_args(pb, registry_path=registry_path, workers=4)
        code = pb._run_real_server(args)
        assert code != 0
        captured = capsys.readouterr()
        assert "REALPERF" not in captured.out
        assert "REALCPU" not in captured.out
        lines = _realworkers_lines(captured.out)
        assert len(lines) == 1
        assert " workers=4 " in lines[0]
        assert "status 429" in captured.err
    finally:
        _stop_realserver_stub_server(proc)


def test_format_realworkers_row_is_stable():
    """`REALWORKERS`'s own column names, order and formatting: counts per
    pid in ascending pid order and per non-200 status in ascending status
    order, `-` for either when there is none, `unclassified=` always
    last."""
    assert pb._format_realworkers_row("r2db-api", 4, 8, [12, 11, 12, 13], {429: 2, 404: 1}, 0) == (
        "REALWORKERS peer=r2db-api plug=r2db-api-real workers=4 concurrency=8 pids=3 "
        "accepted_200=11:1,12:2,13:1 non_200=404:1,429:2 unclassified=0"
    )
    assert pb._format_realworkers_row("MitateDB-api", 1, 1, [], {}, 3) == (
        "REALWORKERS peer=MitateDB-api plug=MitateDB-api-real workers=1 concurrency=1 pids=0 "
        "accepted_200=- non_200=- unclassified=3"
    )


def test_real_server_does_not_override_concurrency_in_the_launcher_env(tmp_path):
    """The environment the launcher starts in carries no `concurrency`
    override: no variable whose name contains `CONCURRENCY` differs
    between the caller's own environment and the one `start()` observed.

    mutation M150 (`tools/perf_baseline.py`): set
    `os.environ["MITATEDB_MAX_CONCURRENCY"] = "64"` just before
    `launcher.start` -- red because `start()` observes that variable."""
    log_path, proc, registry_path, launcher_cls = _realserver_group_setup(tmp_path)
    env_before = dict(os.environ)
    try:
        args = _realserver_workers_args(pb, registry_path=registry_path, workers=2)
        code = pb._run_real_server(args)
        assert code == 0
        assert len(launcher_cls.START_ENVIRON) == 1
        env_at_start = launcher_cls.START_ENVIRON[0]
        changed = {k for k in set(env_before) | set(env_at_start) if env_before.get(k) != env_at_start.get(k)}
        assert not [k for k in changed if "CONCURRENCY" in k.upper()], changed
    finally:
        for key in [k for k in os.environ if "CONCURRENCY" in k.upper()]:
            if key in env_before:
                os.environ[key] = env_before[key]
            else:
                del os.environ[key]
        _kill_stub_groups(launcher_cls)
        _stop_realserver_stub_server(proc)


def _stub_group_members(pgid):
    out = subprocess.run(["ps", "-A", "-o", "pid=,pgid="], capture_output=True, text=True, check=True).stdout
    return [int(parts[0]) for parts in (line.split() for line in out.splitlines()) if len(parts) == 2 and int(parts[1]) == pgid]


def test_real_server_leaves_no_launcher_process_group_member_after_the_run(tmp_path, monkeypatch):
    """After a `--workers 4` run, the launcher's own process group has 0
    processes, its 4 children included; the group had 5 members
    while the run was up, so the 0 is not a group that never existed.

    mutation M153 (`tools/perf_baseline.py`): never call
    `launcher.stop()` after the run -- red because the group keeps its 5
    members and the run returns 1."""
    monkeypatch.setattr(pb, "_PROCESS_GROUP_DRAIN_TIMEOUT_S", 2.0)
    log_path, proc, registry_path, launcher_cls = _realserver_group_setup(tmp_path)
    try:
        args = _realserver_workers_args(pb, registry_path=registry_path, workers=4)
        code = pb._run_real_server(args)
        assert launcher_cls.GROUP_MEMBERS_AT_START == [5]
        assert len(launcher_cls.SUPERVISORS) == 1
        assert _stub_group_members(launcher_cls.SUPERVISORS[0].pid) == []
        assert code == 0
    finally:
        _kill_stub_groups(launcher_cls)
        _stop_realserver_stub_server(proc)


def test_real_server_reports_a_launcher_process_group_left_running(tmp_path, capsys, monkeypatch):
    """A launcher whose `stop()` leaves its process group running makes
    the run return 1 and name the remaining pids on stderr -- the check
    runs on the process table, not on the launcher's own word.

    mutation M153b (`tools/perf_baseline.py`): skip the residue report
    (`if residue:` never true) -- red because the run then returns 0."""
    monkeypatch.setattr(pb, "_PROCESS_GROUP_DRAIN_TIMEOUT_S", 0.5)
    log_path, proc, registry_path, launcher_cls = _realserver_group_setup(tmp_path, leave_group_running=True)
    try:
        args = _realserver_workers_args(pb, registry_path=registry_path, workers=2)
        code = pb._run_real_server(args)
        assert launcher_cls.STOP_CALLS == [True]
        pgid = launcher_cls.SUPERVISORS[0].pid
        assert len(_stub_group_members(pgid)) == 3
        assert code == 1
        err = capsys.readouterr().err
        assert f"launcher process group(s) [{pgid}] still have process(es) after stop()" in err
    finally:
        _kill_stub_groups(launcher_cls)
        _stop_realserver_stub_server(proc)


def test_real_server_without_workers_starts_one_worker(tmp_path, capsys):
    """Without `--workers`, the launcher starts with `workers=1` and
    ceilings data = 1, control = 1, and the run prints `workers=1`."""
    base_url, log_path, proc, registry_path, launcher_cls = _realserver_setup(tmp_path)
    try:
        args = _realserver_workers_args(pb, registry_path=registry_path)
        code = pb._run_real_server(args)
        assert code == 0
        assert launcher_cls.START_CALLS == [{"data": 1, "control": 1}]
        assert launcher_cls.START_WORKERS == [1]
        lines = _realworkers_lines(capsys.readouterr().out)
        assert len(lines) == 1
        assert " workers=1 " in lines[0]
    finally:
        _stop_realserver_stub_server(proc)


def test_real_server_prints_per_status_non_200_counts_after_the_run(tmp_path, capsys):
    """A run a non-200 response stops still counts, from the launcher's
    access log, every non-200 response of its groups per status: here
    both requests of the one measured group (K=2) answer 429, so the
    `REALWORKERS` line carries `non_200=429:2` and no 200 at all.

    mutation M149b (`tools/perf_baseline.py`): never count non-200
    statuses (`_access_log_non_200_counts` counts nothing) -- red because
    the line then carries `non_200=-`."""
    config = {"query_status_override": {"1": 429, "2": 429}}
    log_path, proc, registry_path, launcher_cls = _realserver_group_setup(tmp_path, config)
    try:
        args = _realserver_workers_args(pb, registry_path=registry_path, workers=2, concurrency=2, n=1)
        code = pb._run_real_server(args)
        assert code == 1
        lines = _realworkers_lines(capsys.readouterr().out)
        assert lines == [
            "REALWORKERS peer=stubpeer plug=stubpeer-real workers=2 concurrency=2 pids=0 accepted_200=- "
            "non_200=429:2 unclassified=0"
        ]
    finally:
        _kill_stub_groups(launcher_cls)
        _stop_realserver_stub_server(proc)


def test_real_server_refuses_a_start_with_no_observable_launcher_process_group(tmp_path, capsys, monkeypatch):
    """A launcher after whose `start()` no process group of its own is
    observed is refused: the run returns 1 with a message on stderr,
    measures nothing (no `REALPERF`/`REALCPU`/`REALWORKERS`) and still
    stops the launcher -- never a 0 from a residue check that observed
    nothing.

    mutation M153c (`tools/perf_baseline.py`): drop the no-group check --
    red because the run then measures and returns 0."""
    base_url, log_path, proc, registry_path, launcher_cls = _realserver_setup(tmp_path)

    def _start_without_processes(self, *, ceilings, workers=1):
        type(self).START_CALLS.append(dict(ceilings))

    monkeypatch.setattr(launcher_cls, "start", _start_without_processes)
    try:
        args = _realserver_workers_args(pb, registry_path=registry_path, workers=2)
        code = pb._run_real_server(args)
        captured = capsys.readouterr()
        assert launcher_cls.START_CALLS == [{"data": 2, "control": 1}]
        assert launcher_cls.STOP_CALLS == [True]
        assert code == 1
        assert "could not observe any launcher process group after start()" in captured.err
        assert "REALPERF" not in captured.out
        assert "REALWORKERS" not in captured.out
    finally:
        _stop_realserver_stub_server(proc)


def test_real_server_reports_zombies_without_counting_them_as_residue(tmp_path, capsys, monkeypatch):
    """A launcher group member that has exited but is not reaped (a
    zombie) is not residue: the run returns 0 and reports the zombie
    count on stderr as reaped-pending.

    mutation M153z (`tools/perf_baseline.py`): count zombies as residue --
    red because the run then returns 1."""
    monkeypatch.setattr(pb, "_PROCESS_GROUP_DRAIN_TIMEOUT_S", 2.0)
    log_path, proc, registry_path, launcher_cls = _realserver_group_setup(tmp_path, zombie_on_stop=True)
    try:
        args = _realserver_workers_args(pb, registry_path=registry_path, workers=1)
        code = pb._run_real_server(args)
        err = capsys.readouterr().err
        pgid = launcher_cls.SUPERVISORS[0].pid
        stat = subprocess.run(["ps", "-o", "stat=", "-p", str(pgid)], capture_output=True, text=True).stdout.strip()
        assert stat.startswith("Z"), stat
        assert f"launcher process group(s) [{pgid}] have 1 zombie process(es) after stop() (reaped-pending" in err
        assert code == 0
    finally:
        _kill_stub_groups(launcher_cls)
        _stop_realserver_stub_server(proc)


def test_real_server_counts_every_non_200_status_of_a_run(tmp_path, capsys):
    """Every non-200 status of a run is counted, the last one read
    included: the one measured group (K=3) answers 429, 429 and 500, so
    the `REALWORKERS` line carries `non_200=429:2,500:1`.

    mutation M149c (`tools/perf_baseline.py`): stop the status reads one
    line early (`if remaining <= 1:`) -- red because the 500 is then
    never read and the line carries `non_200=429:2 unclassified=1`."""
    config = {"query_status_override": {"1": 429, "2": 429, "3": 500}}
    log_path, proc, registry_path, launcher_cls = _realserver_group_setup(tmp_path, config)
    try:
        args = _realserver_workers_args(pb, registry_path=registry_path, workers=2, concurrency=3, n=1)
        code = pb._run_real_server(args)
        assert code == 1
        lines = _realworkers_lines(capsys.readouterr().out)
        assert lines == [
            "REALWORKERS peer=stubpeer plug=stubpeer-real workers=2 concurrency=3 pids=0 accepted_200=- "
            "non_200=429:2,500:1 unclassified=0"
        ]
    finally:
        _kill_stub_groups(launcher_cls)
        _stop_realserver_stub_server(proc)


def test_real_server_reports_access_log_lines_no_status_read_returned(tmp_path, capsys):
    """An access-log line of the run that no status read returns is
    counted as `unclassified=`: of the one measured group's 3 requests
    (K=3, all 200), the server writes 1 line that is not parseable, so the
    `REALWORKERS` line carries 2 accepted 200s and `unclassified=1`.

    mutation M149d (`tools/perf_baseline.py`): always print
    `unclassified=0` -- red because the line then carries
    `unclassified=0`."""
    config = {"unparseable_log_indices": [2]}
    log_path, proc, registry_path, launcher_cls = _realserver_group_setup(tmp_path, config)
    try:
        args = _realserver_workers_args(pb, registry_path=registry_path, workers=2, concurrency=3, n=1)
        code = pb._run_real_server(args)
        assert code == 0
        lines = _realworkers_lines(capsys.readouterr().out)
        assert lines == [
            f"REALWORKERS peer=stubpeer plug=stubpeer-real workers=2 concurrency=3 pids=1 "
            f"accepted_200={proc.pid}:2 non_200=- unclassified=1"
        ]
    finally:
        _kill_stub_groups(launcher_cls)
        _stop_realserver_stub_server(proc)


def test_real_server_stopped_run_prints_its_concurrency(tmp_path, capsys):
    """A run a non-200 response stops prints no `REALPERF`, and its
    `REALWORKERS` line still carries the run's K (`concurrency=3`).

    mutation M148b (`tools/perf_baseline.py`): drop `concurrency=` from
    the `REALWORKERS` line -- red because the line then has no
    ` concurrency=3 `."""
    config = {"query_status_override": {"1": 429}}
    base_url, log_path, proc, registry_path, launcher_cls = _realserver_setup(tmp_path, config)
    try:
        args = _realserver_workers_args(pb, registry_path=registry_path, workers=2, concurrency=3)
        code = pb._run_real_server(args)
        assert code != 0
        captured = capsys.readouterr()
        assert "REALPERF" not in captured.out
        lines = _realworkers_lines(captured.out)
        assert len(lines) == 1
        assert " workers=2 concurrency=3 " in lines[0]
    finally:
        _stop_realserver_stub_server(proc)


def test_real_server_reports_workers_left_by_a_supervisor_that_exited_during_start(tmp_path, capsys, monkeypatch):
    """A launcher process group whose leader exits during `start()` (an
    unreaped zombie child of this process) while its workers keep running
    is still checked after `stop()`: with a `stop()` that never signals
    that group, the run returns 1 and names the workers on stderr.

    mutation M153d (`tools/perf_baseline.py`): leave zombie leaders out of
    the launcher's process groups (`and not zombie`) -- red because the
    group is then never checked and the run returns 0."""
    monkeypatch.setattr(pb, "_PROCESS_GROUP_DRAIN_TIMEOUT_S", 0.5)
    log_path, proc, registry_path, launcher_cls = _realserver_group_setup(tmp_path, leader_exits_during_start=True)
    try:
        args = _realserver_workers_args(pb, registry_path=registry_path, workers=2)
        code = pb._run_real_server(args)
        err = capsys.readouterr().err
        assert len(launcher_cls.EXITED_LEADER_GROUPS) == 1
        pgid = launcher_cls.EXITED_LEADER_GROUPS[0]
        left = [pid for pid in _stub_group_members(pgid) if pid != pgid]
        assert len(left) == 2
        assert code == 1
        assert f"process(es) after stop(): {sorted(left)}" in err
    finally:
        _kill_stub_groups(launcher_cls)
        _stop_realserver_stub_server(proc)
