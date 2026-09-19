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
