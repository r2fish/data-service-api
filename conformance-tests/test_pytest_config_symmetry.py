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
"""
from __future__ import annotations

import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover -- this repository requires Python >=3.11
    import tomli as tomllib  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parents[1]

CONFIG_PATHS = {
    "root": ROOT / "pyproject.toml",
    "r2db-api": ROOT / "r2db-api" / "pyproject.toml",
    "MitateDB-api": ROOT / "MitateDB-api" / "pyproject.toml",
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
