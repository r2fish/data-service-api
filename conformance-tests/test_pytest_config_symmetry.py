"""Pytest configuration symmetry (Phase 7 WP-6, docs/work-orders/WORK_ORDER_
PHASE7_EVIDENCE_AND_PUBLICATION_V1.md, D-4(b)(iii); supervisor ruling
correction note 8 / design section L7-19).

`filterwarnings = ["error::DeprecationWarning", "ignore:.*BlockingPortal.*:
DeprecationWarning:starlette.testclient"]` must appear, byte-for-byte
identical once parsed, in all three of:

  - the repository-root `pyproject.toml`
  - `r2db-api/pyproject.toml`
  - `MitateDB-api/pyproject.toml`

This is not decorative symmetry: which of the three files' `[tool.pytest.
ini_options]` table actually governs a given pytest invocation depends on
the rootdir pytest resolves for that invocation's arguments (e.g. `pytest
r2db-api/tests` from the repository root resolves `r2db-api/` itself as
rootdir and uses `r2db-api/pyproject.toml`, not the root file) -- so all
three must carry the same setting for the DeprecationWarning-as-error
policy to hold regardless of how a peer's suite is invoked.

The `ignore` entry is scoped to a single known upstream warning (starlette.
testclient's own module-level `anyio.abc.BlockingPortal` alias access,
emitted once at import time independent of `httpx2`'s presence); a blanket
ignore is prohibited by the same ruling that authorizes this narrow one.

Test 1 (`test_all_three_files_are_readable_and_carry_two_entries`) checks
each file's `filterwarnings` value against the literal form the ruling
fixes above (hardcoded: exactly two entries, entry 0 ==
`"error::DeprecationWarning"`, entry 1 containing both `BlockingPortal`
and `starlette.testclient`) -- the value is still read live from disk
rather than inlined as a Python constant, so a file that stops declaring
it (or mis-declares it) fails loudly rather than silently matching. Test 2
(`test_filterwarnings_is_identical_across_root_and_both_peers`) instead
performs a live pairwise comparison of the three files' actual values
against each other, so a future change made to only one or two of the
three -- even one that still happens to satisfy test 1's fixed form --
is caught as a divergence.

`test_conftest_py_is_byte_identical_across_the_three_pytest_roots` (work
order docs/work-orders/WORK_ORDER_R44_TEST_PG_ISOLATION_V1.md §2.3, design
docs/design/TEST_POSTGRES_ISOLATION_V0_1.md v0.2 D-1) extends the same
"three roots must agree" principle to `conftest.py`, which each of the
three roots now also carries: it starts (or attaches to) this run's
throwaway PostgreSQL 16 cluster, and its content must be identical for the
same reason as `filterwarnings` above -- whichever root a given invocation
resolves, the same launcher call must run.

`test_pytest_configure_fixup_restores_conformance_tests_own_conftest`
(review finding M-7) pins the `pytest_configure` hook each of the three
`conftest.py` files also carries -- a fixup for a SEPARATE, pytest-native
hazard the three files' own existence creates: none of the four
`conftest.py`s now in this repository (these three, plus `conformance-
tests/conftest.py`, pre-existing) sits inside a Python package (no
`__init__.py` above any of them), so pytest gives all four the identical
module name `"conftest"` (`_pytest/config/__init__.py::
PytestPluginManager._importconftest`'s own comment: "conftest.py files
there are not in a Python package all have module name 'conftest', and
thus conflict with each other"). In a whole-repository run, whichever one
loads LAST (`pyproject.toml`'s `testpaths` order: `MitateDB-api/conftest.py`
today) silently overwrites `sys.modules["conftest"]`, breaking every
`conformance-tests/test_c*.py` module's own `from conftest import ...`
(~20 of them; `test_conftest_adapter_close_timing.py` does `import
conftest` the same way). The fixup restores it in `pytest_configure`,
which pytest guarantees runs only after every initial conftest.py is
already loaded and before collection imports any test module.

Reproduced in a `pytester` sandbox (following `test_conftest_adapter_
close_timing.py`'s own established pattern for a sys.modules-timing-
sensitive regression) rather than asserted against the live outer session,
because the bug only manifests when ALL FOUR real conftest.py's load
together in `testpaths` order -- true for a whole-repository run, but NOT
for a narrowly-targeted single-test invocation (`tools/dev/mutate.py`'s
own mechanism), so a live-session assertion would not reliably catch a
regression under mutation testing. The sandbox's own "peer_b/conftest.py"
carries the REAL `pytest_configure` function's source, read from this
repository's own `conftest.py` at test-run time (not a hand-copied
replica) -- so a mutation to the real function is what this test actually
detects.
"""
from __future__ import annotations

import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover -- this repository requires Python >=3.11
    import tomli as tomllib  # type: ignore[no-redef]

pytest_plugins = ["pytester"]

ROOT = Path(__file__).resolve().parents[1]

CONFIG_PATHS = {
    "root": ROOT / "pyproject.toml",
    "r2db-api": ROOT / "r2db-api" / "pyproject.toml",
    "MitateDB-api": ROOT / "MitateDB-api" / "pyproject.toml",
}

CONFTEST_PATHS = {
    "root": ROOT / "conftest.py",
    "r2db-api": ROOT / "r2db-api" / "conftest.py",
    "MitateDB-api": ROOT / "MitateDB-api" / "conftest.py",
}


def _read_filterwarnings(path: Path) -> list[str]:
    if not path.is_file():
        raise AssertionError(f"{path} does not exist")
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    try:
        value = data["tool"]["pytest"]["ini_options"]["filterwarnings"]
    except KeyError as exc:
        raise AssertionError(
            f"{path} has no [tool.pytest.ini_options].filterwarnings entry"
        ) from exc
    if not isinstance(value, list):
        raise AssertionError(
            f"{path}'s [tool.pytest.ini_options].filterwarnings is not a list: {value!r}"
        )
    return value


def test_all_three_files_are_readable_and_carry_two_entries():
    """No-op-proof: each of the three files parses, has the key, and the
    key's value has exactly the two entries the ruling specifies (a file
    with zero or one entries, or a stray third one, must fail here rather
    than pass by accident)."""
    for label, path in CONFIG_PATHS.items():
        entries = _read_filterwarnings(path)
        assert len(entries) == 2, (
            f"{path} (peer: {label}) has {len(entries)} filterwarnings entries, expected 2: {entries!r}"
        )
        assert entries[0] == "error::DeprecationWarning", (
            f"{path} (peer: {label}) entry 0 is {entries[0]!r}, expected 'error::DeprecationWarning'"
        )
        assert "BlockingPortal" in entries[1] and "starlette.testclient" in entries[1], (
            f"{path} (peer: {label}) entry 1 is {entries[1]!r}, expected the narrow "
            "starlette.testclient BlockingPortal ignore"
        )


def test_filterwarnings_is_identical_across_root_and_both_peers():
    values = {label: _read_filterwarnings(path) for label, path in CONFIG_PATHS.items()}
    root_value = values["root"]
    mismatched = {
        label: value for label, value in values.items() if value != root_value
    }
    assert not mismatched, (
        "filterwarnings diverges across root/r2db-api/MitateDB-api pyproject.toml files; "
        f"root={root_value!r}, mismatched={mismatched!r}"
    )


def test_conftest_py_is_byte_identical_across_the_three_pytest_roots():
    """Work order §2.3: the three `conftest.py` files (repository root,
    r2db-api/, MitateDB-api/) must be byte-for-byte identical, exactly like
    `filterwarnings` above. Reads raw bytes (not text/parsed content), so a
    line-ending or encoding divergence invisible to a text diff still
    fails this."""
    missing = {label: path for label, path in CONFTEST_PATHS.items() if not path.is_file()}
    assert not missing, f"conftest.py missing at: {missing!r}"
    contents = {label: path.read_bytes() for label, path in CONFTEST_PATHS.items()}
    root_bytes = contents["root"]
    assert root_bytes, f"{CONFTEST_PATHS['root']} is empty"
    mismatched = {label: len(b) for label, b in contents.items() if b != root_bytes}
    assert not mismatched, (
        "conftest.py diverges across root/r2db-api/MitateDB-api; "
        f"root is {len(root_bytes)} bytes, mismatched byte-lengths={mismatched!r}"
    )


_PYTEST_CONFIGURE_MARKER = "def pytest_configure(config) -> None:"


def _pytest_configure_source() -> str:
    """The real `pytest_configure` function's source, read from this
    repository's own `conftest.py` -- it is the LAST top-level definition
    in the file, so slicing from the marker to EOF is exact (review M-7:
    "the exact code copied from this repository's own conftest.py", not a
    hand-written replica of the bug's shape)."""
    text = CONFTEST_PATHS["root"].read_text(encoding="utf-8")
    if _PYTEST_CONFIGURE_MARKER not in text:
        raise AssertionError(
            f"{CONFTEST_PATHS['root']} no longer defines {_PYTEST_CONFIGURE_MARKER!r}"
        )
    return text[text.index(_PYTEST_CONFIGURE_MARKER):]


def test_pytest_configure_fixup_restores_conformance_tests_own_conftest(pytester):
    """See the module docstring's last paragraph. Reproduces the exact
    module-name collision (_pytest/config/__init__.py's own documented
    behavior for package-less conftest.py's) with a minimal, throwaway
    layout: "conformance-tests/" (matching this repository's own directory
    name literally, since the real `pytest_configure` looks for it by that
    exact relative path) loads FIRST and defines `MARKER`; two further
    sibling, package-less conftest.py's ("peer_a/", "peer_b/") load after
    it, in `testpaths` order, matching this repository's own `testpaths =
    ["conformance-tests", "r2db-api/tests", "MitateDB-api/tests"]` --
    "peer_b" carries the REAL fixup (this repository's own MitateDB-api/
    conftest.py is the one actually loaded last).

    Without the fixup, `conformance-tests/test_victim.py`'s own `from
    conftest import MARKER` would resolve to "peer_b"'s own (unrelated)
    module and fail to collect -- proving the hazard is real, not just
    demonstrating the fix in isolation, is left to `test_pytest_config_
    symmetry.py`'s own git history / the mutation this row adds; this test
    always runs the FIXED path and asserts it passes."""
    root = pytester.path

    (root / "conftest.py").write_text("", encoding="utf-8")

    (root / "conformance-tests").mkdir()
    (root / "conformance-tests" / "conftest.py").write_text(
        "MARKER = 'conformance_tests_own_value'\n", encoding="utf-8"
    )
    (root / "conformance-tests" / "test_victim.py").write_text(
        "from conftest import MARKER\n\n\n"
        "def test_marker_is_the_conformance_tests_one():\n"
        "    assert MARKER == 'conformance_tests_own_value'\n",
        encoding="utf-8",
    )

    (root / "peer_a").mkdir()
    (root / "peer_a" / "conftest.py").write_text("PEER_A = True\n", encoding="utf-8")
    (root / "peer_a" / "tests").mkdir()
    # Deliberately DIFFERENT basenames from peer_b's own dummy test below:
    # neither "peer_a/tests/" nor "peer_b/tests/" is a Python package (no
    # __init__.py), and unlike conftest.py, pytest does NOT special-case a
    # basename collision between two ordinary test modules -- same-named
    # "test_dummy.py" in both would itself raise a collection-time
    # `import file mismatch`, unrelated to the fixup this test exists to
    # pin.
    (root / "peer_a" / "tests" / "test_peer_a_dummy.py").write_text("def test_dummy():\n    pass\n", encoding="utf-8")

    (root / "peer_b").mkdir()
    (root / "peer_b" / "conftest.py").write_text(
        "import os\n"
        "import sys\n"
        "from pathlib import Path\n\n"
        "_repo_root = Path(__file__).resolve().parent.parent\n\n"
        + _pytest_configure_source(),
        encoding="utf-8",
    )
    (root / "peer_b" / "tests").mkdir()
    (root / "peer_b" / "tests" / "test_peer_b_dummy.py").write_text("def test_dummy():\n    pass\n", encoding="utf-8")

    (root / "pytest.ini").write_text(
        "[pytest]\ntestpaths =\n    conformance-tests\n    peer_a/tests\n    peer_b/tests\n",
        encoding="utf-8",
    )

    result = pytester.runpytest("-q")
    result.assert_outcomes(passed=3)
    assert result.ret == 0
