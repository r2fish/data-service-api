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
import json
import os
import subprocess
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


def test_pool_row_format_is_stable_for_a_role_pool_entry():
    """R-78 completion condition 8: `_format_pool_row`'s ROLE-shaped
    column names/order/formatting for a `r2db_api.postgres._RolePool.
    stats()`-shaped dict (six keys, `size`/`in_use_peak` present, no
    `lock_acquire_count`).

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


def test_pool_row_format_is_stable_for_a_lock_entry():
    """R-78 completion condition 8: `_format_pool_row`'s LOCK-shaped
    column names/order/formatting for a `mitatedb_api.cell.
    _CountingRLock.stats()`-shaped dict (four keys, `lock_acquire_count`
    present, no `size`/`in_use_peak`) -- `lock=` replaces `role=` and
    there is no `size=`/`in_use_peak=` column, since neither concept
    applies to a mutex."""
    stats = {"lock_acquire_count": 5, "wait_count": 1, "wait_total_ms": 3.0, "wait_max_ms": 3.0}
    line = pb._format_pool_row("MitateDB-api", "MitateDB-api-http", "mutate", "app1", stats)
    assert line == (
        "POOL peer=MitateDB-api plug=MitateDB-api-http op=mutate lock=app1 "
        "acquire=5 waits=1 wait_total_ms=3.000 wait_max_ms=3.000"
    )


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


def test_roundtrip_probes_prepared_stats_exactly_twice_per_op(capsys):
    """WO §2.2 completion condition 3 (design review 1 M-3): a `--roundtrip`
    op calls `prepared_stats()` exactly twice -- once as the PRE baseline
    (`_roundtrip_pre_probe`), once as the POST value `_emit_prepared_rows`
    already uses for its own `PREPARED` lines -- and the `ROUNDTRIP conn=`
    lines are built from that SAME POST return value, never a third call.

    mutation M3 (`tools/perf_baseline.py`): call `prepared_stats()` once
    more for the `ROUNDTRIP` lines instead of reusing `_emit_prepared_
    rows`' own return value -- this test's own `len(call_log) == 2`
    assertion goes red (3 calls instead of 2)."""
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
    assert len(call_log) == 2
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


def test_default_run_probes_prepared_stats_exactly_once_per_op(capsys):
    """WO §2.2 completion condition 21b (design review 1 M-5): with
    `--roundtrip` absent, `prepared_stats()` is called exactly once per
    op (POST only) -- the PRE probe never runs outside the flag, so
    R-79's own established `POOL lock=` `acquire`/`PREPARED` baseline
    stays undisturbed.

    mutation M18 (`tools/perf_baseline.py`): run the PRE probe regardless
    of `roundtrip_enabled` -- this test's own `len(call_log) == 1`
    assertion goes red (2 calls instead of 1)."""
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
    assert len(call_log) == 1


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
