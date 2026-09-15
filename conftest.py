"""Byte-for-byte identical across the repository root, `r2db-api/`, and
`MitateDB-api/` (`conformance-tests/test_pytest_config_symmetry.py` checks
this). Starts -- or attaches to -- this pytest run's throwaway PostgreSQL 16
cluster before any other `conftest.py` or test module runs.

Why at import time, not a `pytest_configure` hook: `conformance-tests/
conftest.py` builds every registered adapter at ITS OWN import time, and
each adapter connects to PostgreSQL immediately. pytest imports every
initial `conftest.py` before it calls `pytest_configure`, so a hook here
would run too late (design docs/design/TEST_POSTGRES_ISOLATION_V0_1.md v0.2
D-1, review finding B-1).

Why one identical copy at each of the three pytest roots: `pytest
r2db-api/tests/...` (or `cd MitateDB-api && pytest tests/`) resolves that
peer's own `pyproject.toml` `[tool.pytest.ini_options]` as pytest's rootdir
-- and pytest's default `confcutdir` (the boundary of upward conftest
search) is that same rootdir, so a peer-rooted run never imports this
repository's OWN root `conftest.py` at all (design D-1, review finding
B-2). Each of the three roots therefore needs its own copy that finds the
launcher the same way: by walking UP from its own location.

`pytest_configure` below is NOT part of the launcher's own job (that is
only the module-level `ensure_for_pytest()` call and `pytest_unconfigure`).
It works around a separate, pytest-native footgun that adding these three
files exposes: none of the four conftest.py's now in this repository
(these three, plus `conformance-tests/conftest.py`, pre-existing) sits in a
Python package (no `__init__.py` anywhere above them), so pytest gives all
four the SAME module name, literally `"conftest"`
(`_pytest/config/__init__.py::PytestPluginManager._importconftest`'s own
comment: "conftest.py files there are not in a Python package all have
module name 'conftest', and thus conflict with each other"). In a
whole-repository run, pytest loads all four as INITIAL conftests (before
any test module import); whichever loads LAST simply overwrites
`sys.modules["conftest"]`, and per `pyproject.toml`'s `testpaths` order
that is always one of THESE three, never `conformance-tests/conftest.py`
itself. Every `conformance-tests/test_c*.py` module does `from conftest
import ...` expecting ITS OWN local conftest.py -- collection (which
imports those test modules) happens after every initial conftest and after
`pytest_configure`, so fixing `sys.modules["conftest"]` here, once, before
collection starts, is both safe (pytest's own bookkeeping for already-
loaded conftests is keyed by absolute path, not this name) and sufficient.
Matched by `os.path.samefile` (not string equality) against every already-
registered plugin, so it is unaffected by how each path happens to be
spelled. A no-op whenever `conformance-tests/conftest.py` was never loaded
in this session (a peer-only run) or already owns the name.

Work order docs/work-orders/WORK_ORDER_R44_TEST_PG_ISOLATION_V1.md §2.2.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _load_dsa_testpg():
    here = Path(__file__).resolve().parent
    for directory in (here, *here.parents):
        candidate = directory / "tools" / "testpg" / "dsa_testpg.py"
        if candidate.is_file():
            module_dir = str(candidate.parent)
            if module_dir not in sys.path:
                sys.path.insert(0, module_dir)
            import dsa_testpg
            return dsa_testpg, directory
    raise ImportError(f"tools/testpg/dsa_testpg.py not found above {here}")


dsa_testpg, _repo_root = _load_dsa_testpg()
dsa_testpg.ensure_for_pytest()


def pytest_unconfigure(config) -> None:  # noqa: ARG001 -- pytest's own hook signature
    dsa_testpg.stop_owned()


def pytest_configure(config) -> None:
    """See the module docstring's last paragraph. Runs once every initial
    conftest.py is already loaded (pytest's own guarantee for this hook),
    strictly before collection imports any `conformance-tests/test_c*.py`
    module."""
    target = _repo_root / "conformance-tests" / "conftest.py"
    if not target.is_file():
        return
    current = sys.modules.get("conftest")
    if current is not None and getattr(current, "__file__", None):
        try:
            if os.path.samefile(current.__file__, target):
                return  # already correct
        except OSError:
            pass
    for plugin in config.pluginmanager.get_plugins():
        plugin_file = getattr(plugin, "__file__", None)
        if not plugin_file:
            continue
        try:
            if os.path.samefile(plugin_file, target):
                sys.modules["conftest"] = plugin
                return
        except OSError:
            continue
