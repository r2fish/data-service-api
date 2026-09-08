"""tools/tests/test_perf_baseline.py -- pytest coverage for
tools/perf_baseline.py's own `_classify_plug` (Phase 10 WP-3, design
docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md D-12).

Deliberately NOT under `conformance-tests/` and NOT discoverable by the
root suite: `tools/` is not in pyproject.toml's `[tool.pytest.ini_options]
testpaths` (same convention as `tools/tests/test_check_doc_refs.py`).
`_classify_plug` itself needs no real registered adapter/Postgres at all
-- it only reads a plain attribute and a name string -- so every test
below drives it with a minimal duck-typed stand-in (`types.
SimpleNamespace`), never a real `ConformanceAdapter`.

Run directly:
    ./.venv/bin/python -m pytest tools/tests/test_perf_baseline.py -q
"""
from __future__ import annotations

import importlib.util
import sys
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
