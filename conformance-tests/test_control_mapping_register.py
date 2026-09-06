"""Mechanical fixation for `security/CONTROL_MAPPING.md`'s current/history
split (phase 7 WP-7 (i), design
docs/design/PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md D-7).

`CONTROL_MAPPING.md` has no code today that parses it (no `@pytest.mark`
wiring the way `CONDITIONS.md` has `condition` markers) -- this file is the
first machine-readable check placed against it, and it carries no condition
ID of its own (`@pytest.mark.condition(...)` is not applied to anything
here; these tests check the DOCUMENT, not a behavioral condition).

`CONTROL_MAPPING.md`'s table has 4 columns (`Invariant`, `r2db-api
control/evidence`, `MitateDB-api control/evidence`, `Common conformance
evidence`) and no separate `ID` column -- each row's Security Invariant id
(`SI-00` .. `SI-15`) is the leading token of the `Invariant` cell's text
(e.g. `SI-00 Single-Compromise Containment`). The checks below mirror
`test_conditions_register.py`'s own WP-7 (i) checks: every row's
`[history](CONTROL_MAPPING_HISTORY.md#<slug>)` link resolves to a real
companion heading, the companion has exactly the main table's IDs (no more,
no fewer), no cell exceeds the agreed length cap, and no SI id is
duplicated.
"""
from __future__ import annotations

import re
from pathlib import Path

CONTROL_MAPPING_PATH = Path(__file__).parent.parent / "security" / "CONTROL_MAPPING.md"
CONTROL_MAPPING_HISTORY_PATH = Path(__file__).parent.parent / "security" / "CONTROL_MAPPING_HISTORY.md"

# Design D-7: the cap applies per cell, not per row. Set PER FILE (差し戻し
# rework round 3, 監督裁定 2026-09-06, item C-1): a single cap shared with
# CONDITIONS.md left THAT file's own re-accumulation guard almost inert
# (its longest cell has 5.7x headroom under a cap sized for this file), so
# each register file now carries its own constant, measured independently.
#
# Measured 2026-09-06 (after restoring the dropped SI-14 r2db-api items
# A-3/A-4 -- the exclusion-list rationale/asymmetry note and the
# process-local deployment-ceiling note -- that this same rework round put
# back onto the current row): this file's own longest cell is SI-14's
# r2db-api control/evidence cell at 15,065 characters. MAX_CELL_LENGTH =
# 15,200 is that measurement plus a 135-character margin. This same (ID,
# length, cap, date) record is also written to CONTROL_MAPPING.md's own
# preamble (before its table, per instruction B-2) -- the recorded
# measurement instruction B-2 flagged as dangling now resolves there, not
# in the design doc (design section 13's own recording is a supervisor
# WP-8 action, not this implementation pass's).
MAX_CELL_LENGTH = 15200

_ID_RE = re.compile(r"^(SI-\d+)\b")
_HISTORY_LINK_RE = re.compile(r"\[history\]\(CONTROL_MAPPING_HISTORY\.md#([a-z0-9\-]+)\)")
_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def _github_slug(text: str) -> str:
    """Same approximation of GitHub's heading-anchor slug algorithm as
    `test_conditions_register.py::_github_slug` -- lowercase, drop
    anything that is not a word character/space/hyphen, spaces to
    hyphens. Duplicated rather than imported: each register test is meant
    to stand alone and not depend on the other table's parser module."""
    text = text.strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    text = re.sub(r"\s+", "-", text)
    return text


def _split_table_row(line: str) -> list[str]:
    s = line.strip()
    inner = s[1:-1] if s.startswith("|") and s.endswith("|") else s.strip("|")
    return [c.strip() for c in inner.split("|")]


def _table_lines(path: Path) -> list[str]:
    text = path.read_text()
    return [line for line in text.splitlines() if line.strip().startswith("|")]


def _parse_control_mapping_rows() -> list[dict[str, str]]:
    """Parse CONTROL_MAPPING.md's table into a list of {column_name:
    cell_text} dicts, one per SI row, plus a derived "ID" key (the leading
    `SI-\\d+` token of the Invariant cell)."""
    table_lines = _table_lines(CONTROL_MAPPING_PATH)
    if len(table_lines) < 2:
        raise AssertionError(f"{CONTROL_MAPPING_PATH} contains no markdown table to parse")
    header = _split_table_row(table_lines[0])
    rows: list[dict[str, str]] = []
    for line in table_lines[2:]:
        cells = _split_table_row(line)
        if len(cells) != len(header):
            continue
        row = dict(zip(header, cells))
        match = _ID_RE.match(row.get("Invariant", ""))
        row["ID"] = match.group(1) if match else ""
        rows.append(row)
    return rows


def _companion_heading_slugs(path: Path) -> set[str]:
    text = path.read_text()
    return {_github_slug(m.group(1)) for m in _HEADING_RE.finditer(text)}


def _companion_sections(path: Path) -> dict[str, str]:
    """{heading_slug: section_body} for every '## <heading>' section in a
    companion file -- mirrors `test_conditions_register.py::
    _companion_sections` (duplicated, not imported, per this file's own
    stand-alone-register-test convention). The body is everything between
    a heading line and the next '## ' heading (or EOF), with a trailing
    '---' separator line stripped off as pure markdown furniture."""
    text = path.read_text()
    matches = list(_HEADING_RE.finditer(text))
    sections: dict[str, str] = {}
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end]
        body = re.sub(r"\n\s*---\s*\n?\s*$", "", body)
        sections[_github_slug(m.group(1))] = body.strip()
    return sections


def test_control_mapping_md_has_a_single_table():
    """Same load-bearing single-table assumption as CONDITIONS.md's own
    register test -- checked directly rather than assumed, since a second
    `|`-started block (e.g. the update-convention preamble written as a
    table instead of prose) would silently corrupt header/divider
    detection."""
    text = CONTROL_MAPPING_PATH.read_text()
    lines = text.splitlines()
    pipe_line_nums = [i for i, line in enumerate(lines) if line.strip().startswith("|")]
    assert pipe_line_nums, f"{CONTROL_MAPPING_PATH} has no '|'-started table at all"
    span = pipe_line_nums[-1] - pipe_line_nums[0] + 1
    assert span == len(pipe_line_nums), (
        f"{CONTROL_MAPPING_PATH} appears to have more than one '|'-started table "
        f"(pipe-prefixed lines are not contiguous): {pipe_line_nums}"
    )


def test_control_mapping_md_is_parseable():
    rows = _parse_control_mapping_rows()
    assert rows, f"no rows parsed from {CONTROL_MAPPING_PATH}"
    assert all(row["ID"] for row in rows), (
        f"row(s) in {CONTROL_MAPPING_PATH} have no leading SI-NN id in their Invariant cell: "
        f"{[row.get('Invariant') for row in rows if not row['ID']]}"
    )


def test_control_mapping_md_has_no_duplicate_ids():
    """No existing parser reads this file at all (unlike CONDITIONS.md's
    dict-based silent-overwrite parser), so this is the first place a
    repeated SI id would ever be caught."""
    rows = _parse_control_mapping_rows()
    ids = [row["ID"] for row in rows if row["ID"]]
    duplicates = sorted({cid for cid in ids if ids.count(cid) > 1})
    assert not duplicates, f"duplicate SI id row(s) in {CONTROL_MAPPING_PATH}: {duplicates}"


def test_control_mapping_md_cells_do_not_exceed_the_length_cap():
    """D-7 machine fixation item 4: the length cap applies per CELL, not
    per row (`CONTROL_MAPPING.md` has 4 columns; only the Invariant-name
    column is expected to stay short)."""
    rows = _parse_control_mapping_rows()
    offenders = [
        (row["ID"], column, len(value))
        for row in rows
        for column, value in row.items()
        if column != "ID" and len(value) > MAX_CELL_LENGTH
    ]
    assert not offenders, (
        f"cell(s) in {CONTROL_MAPPING_PATH} exceed the {MAX_CELL_LENGTH}-character cap "
        f"(id, column, length): {offenders}"
    )


def test_every_control_mapping_row_has_a_resolving_history_link():
    """D-7 machine fixation items 1-2: every SI row carries a
    `[history](CONTROL_MAPPING_HISTORY.md#<slug>)` link (placed in the
    "Common conformance evidence" column by convention, but this check
    searches the whole row so it does not depend on that convention
    holding), and the link fragment must resolve to a REAL companion
    heading (slug equality)."""
    rows = _parse_control_mapping_rows()
    companion_slugs = _companion_heading_slugs(CONTROL_MAPPING_HISTORY_PATH)
    missing_link: list[str] = []
    unresolved: list[tuple[str, str]] = []
    for row in rows:
        cid = row["ID"]
        row_text = " ".join(v for k, v in row.items() if k != "ID")
        match = _HISTORY_LINK_RE.search(row_text)
        if not match:
            missing_link.append(cid)
            continue
        if match.group(1) not in companion_slugs:
            unresolved.append((cid, match.group(1)))
    assert not missing_link, f"row(s) in {CONTROL_MAPPING_PATH} have no [history](...) link: {missing_link}"
    assert not unresolved, (
        f"row(s) in {CONTROL_MAPPING_PATH} whose history link fragment does not resolve to a heading "
        f"in {CONTROL_MAPPING_HISTORY_PATH} (id, fragment): {unresolved}"
    )


def test_control_mapping_history_has_exactly_the_main_tables_ids():
    """D-7 machine fixation item 2, the coverage half: the companion has a
    heading for every SI id in the main table, and no extra ones."""
    rows = _parse_control_mapping_rows()
    main_slugs = {_github_slug(row["ID"]) for row in rows if row["ID"]}
    companion_slugs = _companion_heading_slugs(CONTROL_MAPPING_HISTORY_PATH)
    missing = sorted(main_slugs - companion_slugs)
    extra = sorted(companion_slugs - main_slugs)
    assert not missing and not extra, (
        f"mismatch between {CONTROL_MAPPING_PATH} IDs and {CONTROL_MAPPING_HISTORY_PATH} headings: "
        f"missing_from_companion={missing} extra_in_companion={extra}"
    )


def test_control_mapping_history_every_heading_section_is_non_empty():
    """WP-7 差し戻し rework, 監督裁定 2026-09-06 item 3(e): mirrors
    `test_conditions_register.py::test_conditions_history_every_heading_section_is_non_empty`.
    The ID-set-equality check above only looks at heading TEXT -- a
    mutation that deletes a section's body while leaving its '## SI-NN'
    marker behind would still pass every other check in this file. Every
    companion heading's section body (up to the next heading, trailing
    '---' separator excluded) must be non-empty after stripping
    whitespace. A row with genuinely nothing moved out of it still carries
    an explicit placeholder sentence ("Nothing to move for this row...")
    rather than an empty section, by design."""
    sections = _companion_sections(CONTROL_MAPPING_HISTORY_PATH)
    empty = sorted(slug for slug, body in sections.items() if not body)
    assert not empty, (
        f"{CONTROL_MAPPING_HISTORY_PATH} has heading(s) with an empty section body: {empty}"
    )
