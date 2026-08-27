"""Traceability check between CONDITIONS.md and the executable suite
(design docs/design/CONFORMANCE_ADAPTER_V1.md section 9).

Two directions are checked, both derived from live sources rather than a
hardcoded id list:

1. Every condition ID marked `executable` (or a status string containing
   that word, e.g. "executable (both peers)") in CONDITIONS.md's `Status`
   column has at least one test in the suite carrying a matching
   `@pytest.mark.condition(...)` marker.
2. Every `@pytest.mark.condition(...)` id actually used anywhere in the
   collected suite exists as a row in CONDITIONS.md.

CONDITIONS.md does not yet have a `Status` column as of this writing (design
section 9 adds it in a later step). Per the implementation instructions,
this parser reads a `Status` column and fails with a clear, actionable
message when the column is absent, rather than working around its absence --
so the CONDITIONS.md -> executable-suite wiring stays explicit.
"""
from __future__ import annotations

from pathlib import Path

import pytest

CONDITIONS_PATH = Path(__file__).parent / "CONDITIONS.md"


def _parse_conditions_md() -> dict[str, str]:
    """Parse CONDITIONS.md's markdown table into {condition_id: status}."""
    text = CONDITIONS_PATH.read_text()
    table_lines = [line for line in text.splitlines() if line.strip().startswith("|")]
    if len(table_lines) < 2:
        raise AssertionError(f"{CONDITIONS_PATH} contains no markdown table to parse")

    header_cells = [c.strip() for c in table_lines[0].strip().strip("|").split("|")]
    if "ID" not in header_cells:
        raise AssertionError(f"{CONDITIONS_PATH}'s table has no 'ID' column: {header_cells}")
    if "Status" not in header_cells:
        raise AssertionError(
            f"{CONDITIONS_PATH}'s table has no 'Status' column. Design section 9 "
            "(docs/design/CONFORMANCE_ADAPTER_V1.md) requires CONDITIONS.md to record "
            "each condition's executable status before this traceability check can "
            "run; add a 'Status' column (e.g. 'executable (both peers)', "
            "'not yet executable') and re-run."
        )

    id_idx = header_cells.index("ID")
    status_idx = header_cells.index("Status")

    result: dict[str, str] = {}
    # table_lines[0] is the header row, table_lines[1] is the '---' divider.
    for line in table_lines[2:]:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) <= max(id_idx, status_idx):
            continue
        cid = cells[id_idx]
        status = cells[status_idx]
        if cid:
            result[cid] = status
    return result


def _collect_marked_condition_ids(request: pytest.FixtureRequest) -> set[str]:
    """All condition ids used via @pytest.mark.condition(...) anywhere in
    the collected session, gathered from the live pytest collection rather
    than by re-scanning source files -- so this stays correct as tests are
    added, renamed, or removed."""
    ids: set[str] = set()
    for item in request.session.items:
        marker = item.get_closest_marker("condition")
        if marker and marker.args:
            ids.add(marker.args[0])
    return ids


def test_conditions_md_status_column_is_parseable():
    statuses = _parse_conditions_md()
    assert statuses, f"no condition rows parsed from {CONDITIONS_PATH}"


def test_every_executable_condition_has_a_marked_test(request: pytest.FixtureRequest):
    statuses = _parse_conditions_md()
    # `startswith`, not a substring test: a status like "not yet executable"
    # or "not executable" must NOT count as executable just because it
    # contains that word.
    executable_ids = {cid for cid, status in statuses.items() if status.strip().lower().startswith("executable")}
    marked_ids = _collect_marked_condition_ids(request)
    missing = executable_ids - marked_ids
    assert not missing, (
        f"condition(s) marked executable in {CONDITIONS_PATH} have no "
        f"@pytest.mark.condition(...) test in the collected suite: {sorted(missing)}"
    )


def test_every_marked_condition_id_is_registered_in_conditions_md(request: pytest.FixtureRequest):
    statuses = _parse_conditions_md()
    marked_ids = _collect_marked_condition_ids(request)
    unknown = marked_ids - set(statuses)
    assert not unknown, (
        f"@pytest.mark.condition(...) id(s) used in the suite are not rows in "
        f"{CONDITIONS_PATH}: {sorted(unknown)}"
    )
