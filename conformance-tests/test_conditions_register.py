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

Phase 7 WP-7 (i) extension (design docs/design/PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md
D-7): CONDITIONS.md's rows were split into a short current-state cell plus a
`[history](CONDITIONS_HISTORY.md#<id>)` link to verbatim historical text
moved into a companion file. The mechanical guarantees that split depends on
are pinned below: every row's link resolves to a real companion heading,
the companion has exactly the main table's IDs (no more, no fewer), no
table cell exceeds the agreed length cap, and no ID row is duplicated
(the dict-based parser above would otherwise silently keep only the last
one).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

CONDITIONS_PATH = Path(__file__).parent / "CONDITIONS.md"
CONDITIONS_HISTORY_PATH = Path(__file__).parent / "CONDITIONS_HISTORY.md"

# Design D-7: the cap applies per cell, not per row. Set PER FILE (差し戻し
# rework round 3, 監督裁定 2026-09-06, item C-1): CONDITIONS.md's own longest
# cell is far shorter than CONTROL_MAPPING.md's (SI-14's r2db-api cell), so a
# single cap shared across both files left this file's own re-accumulation
# guard almost inert (5.7x headroom over the measured max). Each register
# file therefore carries its own constant, measured independently.
#
# Measured 2026-09-06 (after restoring the four dropped-constraint items
# A-1..A-4 and four lower-severity ones, A-5, that this same rework round
# put back onto their current rows): this file's own longest cell is
# C-09's Status cell at 2,948 characters (C-19: 2,942). MAX_CELL_LENGTH = 3,000 is that
# measurement plus a 58-character margin. This same (ID, length, cap, date)
# record is also written to CONDITIONS.md's own preamble (before its table,
# per instruction B-2), so the two stay in agreement rather than one
# drifting silently out of date the way this comment's own predecessor
# value (12,631 / a shared 14,300 cap) did.
MAX_CELL_LENGTH = 3000

_HISTORY_LINK_RE = re.compile(r"\[history\]\(CONDITIONS_HISTORY\.md#([a-z0-9\-]+)\)")
_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def _github_slug(text: str) -> str:
    """Approximate GitHub's own heading-anchor slug algorithm: lowercase,
    drop anything that is not a word character/space/hyphen, then turn
    spaces into hyphens. ID-only headings (`## SI-14`, `## C-19`) reduce to
    a plain lowercase of the ID, so this is intentionally simple -- but it
    is still the slugifier, not a hardcoded id->slug table, so a heading
    that grows a title (`## SI-14 -- Title`) changes its own slug and a
    link written against the bare ID stops resolving."""
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


def _parse_conditions_md() -> dict[str, str]:
    """Parse CONDITIONS.md's markdown table into {condition_id: status}."""
    table_lines = _table_lines(CONDITIONS_PATH)
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


def _parse_conditions_rows() -> list[dict[str, str]]:
    """Parse CONDITIONS.md into a list of {column_name: cell_text} dicts,
    one per data row, preserving row order and every column (not just ID
    and Status) -- used by the WP-7 (i) mechanical checks below, which
    reason over the whole row (cell-length cap, the history link, which can
    live in any cell) rather than only the two columns the traceability
    checks above need."""
    table_lines = _table_lines(CONDITIONS_PATH)
    if len(table_lines) < 2:
        raise AssertionError(f"{CONDITIONS_PATH} contains no markdown table to parse")
    header = _split_table_row(table_lines[0])
    rows: list[dict[str, str]] = []
    for line in table_lines[2:]:
        cells = _split_table_row(line)
        if len(cells) != len(header):
            continue
        rows.append(dict(zip(header, cells)))
    return rows


def _companion_heading_slugs(path: Path) -> set[str]:
    text = path.read_text()
    return {_github_slug(m.group(1)) for m in _HEADING_RE.finditer(text)}


def _companion_sections(path: Path) -> dict[str, str]:
    """{heading_slug: section_body} for every '## <heading>' section in a
    companion file -- the body is everything between that heading line and
    the next '## ' heading (or end of file), with a trailing '---'
    separator line stripped off since it is pure markdown furniture, not
    section content."""
    text = path.read_text()
    matches = list(_HEADING_RE.finditer(text))
    sections: dict[str, str] = {}
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end]
        # drop a single trailing '---' separator line (with surrounding
        # blank lines), which is not section content.
        body = re.sub(r"\n\s*---\s*\n?\s*$", "", body)
        sections[_github_slug(m.group(1))] = body.strip()
    return sections


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
    # L7-23 (Phase 8 WP-2, design D-3): running this file on its own
    # collects zero @pytest.mark.condition(...) markers, because every
    # marked test lives in OTHER files under conformance-tests/. Before
    # this guard, that produced a misleading red (or worse, a vacuous
    # green -- see test_every_marked_condition_id_is_registered_in_conditions_md
    # and test_every_marked_condition_id_maps_to_an_executable_status
    # below, which pass trivially against an empty `marked_ids` set) that
    # looked like "all 20 conditions are missing their marker" instead of
    # what actually happened: this test is meaningless outside the full
    # conformance run. Fail loud with the real reason instead of skipping
    # (constant discipline 1, no vacuous pass).
    assert ids, (
        "_collect_marked_condition_ids observed 0 @pytest.mark.condition(...) "
        "ids. This test is only meaningful evaluated inside a full "
        "conformance-tests/ run (or the whole repository root suite) -- "
        "every @pytest.mark.condition(...) marker lives in OTHER files in "
        "this directory, not in test_conditions_register.py itself. Run it "
        "together with the rest of conformance-tests/, not standalone."
    )
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


def test_every_marked_condition_id_maps_to_an_executable_status(request: pytest.FixtureRequest):
    """The reverse direction of `test_every_executable_condition_has_a_marked_test`
    (supervisor-authorized scope extension, WP-1 fix-round item 10):
    that check only ever catches an ID that CONDITIONS.md calls executable
    but the suite does not mark -- removing an ID from CONDITIONS.md's own
    "executable" set can only shrink that check's set difference, never
    grow it, so a condition's status silently regressing (e.g. reverted to
    "not yet executable") while its test file and `@pytest.mark.
    condition(...)` markers are still collected and passing goes entirely
    undetected by that check alone (measured directly: CCR-14 WP-1 fix-round
    mutation M6 demonstrated exactly this gap). This test closes it: every
    condition id actually carried by a collected marker must map to a
    CONDITIONS.md row whose Status starts with `executable`.

    Scope assumption, stated explicitly: `@pytest.mark.condition(...)`
    markers are used only within `conformance-tests/` today (the
    peer-local suites under `r2db-api/tests/`/`MitateDB-api/tests/` do not
    use this marker at all). If that ever changes, this check simply
    quantifies over whatever the collected session actually carries --
    no assumption here needs updating.
    """
    statuses = _parse_conditions_md()
    marked_ids = _collect_marked_condition_ids(request)
    not_executable = {
        cid for cid in marked_ids
        if not statuses.get(cid, "").strip().lower().startswith("executable")
    }
    assert not not_executable, (
        f"@pytest.mark.condition(...) id(s) are collected/marked in the suite, but {CONDITIONS_PATH} does "
        f"not record an 'executable' Status for them (either missing entirely or downgraded): "
        f"{sorted(not_executable)}"
    )


# ---------------------------------------------------------------------------
# Phase 7 WP-7 (i): current-conclusions/history split, mechanical fixation.
# ---------------------------------------------------------------------------

def test_conditions_md_has_a_single_table():
    """D-7's `CONDITIONS.md` decision ("the file has exactly one `|`-started
    table") is load-bearing for every parser above and below -- a second
    table (e.g. the update-convention preamble written as a table instead
    of prose) would silently corrupt header/divider detection. Checked
    directly: every `|`-prefixed line in the file must be part of one
    contiguous block."""
    text = CONDITIONS_PATH.read_text()
    lines = text.splitlines()
    pipe_line_nums = [i for i, line in enumerate(lines) if line.strip().startswith("|")]
    assert pipe_line_nums, f"{CONDITIONS_PATH} has no '|'-started table at all"
    span = pipe_line_nums[-1] - pipe_line_nums[0] + 1
    assert span == len(pipe_line_nums), (
        f"{CONDITIONS_PATH} appears to have more than one '|'-started table "
        f"(pipe-prefixed lines are not contiguous): {pipe_line_nums}"
    )


def test_conditions_md_has_no_duplicate_ids():
    """The pre-existing `_parse_conditions_md` dict comprehension silently
    keeps only the last row for a repeated ID (`result[cid] = status`) --
    this test makes a repeated ID row a hard failure instead, since D-7
    splitting a row across two ID rows (rather than one row plus a history
    link) would otherwise regress silently."""
    rows = _parse_conditions_rows()
    ids = [row["ID"] for row in rows if row.get("ID")]
    duplicates = sorted({cid for cid in ids if ids.count(cid) > 1})
    assert not duplicates, f"duplicate ID row(s) in {CONDITIONS_PATH}: {duplicates}"


def test_conditions_md_cells_do_not_exceed_the_length_cap():
    """D-7 machine fixation item 4: the length cap applies per CELL, not
    per row -- a single long cell must fail even if every other cell in
    that row is short."""
    rows = _parse_conditions_rows()
    offenders = [
        (row.get("ID", "?"), column, len(value))
        for row in rows
        for column, value in row.items()
        if len(value) > MAX_CELL_LENGTH
    ]
    assert not offenders, (
        f"cell(s) in {CONDITIONS_PATH} exceed the {MAX_CELL_LENGTH}-character cap "
        f"(id, column, length): {offenders}"
    )


def test_every_conditions_row_has_a_resolving_history_link():
    """D-7 machine fixation items 1-2: every ID row carries a
    `[history](CONDITIONS_HISTORY.md#<slug>)` link, and the link fragment
    must resolve to a REAL companion heading (slug equality), not merely to
    the existence of *some* heading with that ID's text somewhere in the
    title."""
    rows = _parse_conditions_rows()
    companion_slugs = _companion_heading_slugs(CONDITIONS_HISTORY_PATH)
    missing_link: list[str] = []
    unresolved: list[tuple[str, str]] = []
    for row in rows:
        cid = row.get("ID", "?")
        row_text = " ".join(row.values())
        match = _HISTORY_LINK_RE.search(row_text)
        if not match:
            missing_link.append(cid)
            continue
        if match.group(1) not in companion_slugs:
            unresolved.append((cid, match.group(1)))
    assert not missing_link, f"row(s) in {CONDITIONS_PATH} have no [history](...) link: {missing_link}"
    assert not unresolved, (
        f"row(s) in {CONDITIONS_PATH} whose history link fragment does not resolve to a heading "
        f"in {CONDITIONS_HISTORY_PATH} (id, fragment): {unresolved}"
    )


def test_conditions_history_has_exactly_the_main_tables_ids():
    """D-7 machine fixation item 2, the coverage half: the companion has a
    heading for every ID in the main table, and no extra ones (the
    "过不足なし" requirement) -- an extra heading would usually mean a
    stale ID left behind after a row was renamed or removed."""
    rows = _parse_conditions_rows()
    main_slugs = {_github_slug(row["ID"]) for row in rows if row.get("ID")}
    companion_slugs = _companion_heading_slugs(CONDITIONS_HISTORY_PATH)
    missing = sorted(main_slugs - companion_slugs)
    extra = sorted(companion_slugs - main_slugs)
    assert not missing and not extra, (
        f"mismatch between {CONDITIONS_PATH} IDs and {CONDITIONS_HISTORY_PATH} headings: "
        f"missing_from_companion={missing} extra_in_companion={extra}"
    )


def test_conditions_history_every_heading_section_is_non_empty():
    """WP-7 差し戻し rework, 監督裁定 2026-09-06 item 3(e): a heading with an
    empty body underneath it (a mutation deleting a section's content but
    leaving the '## <ID>' marker behind) would still satisfy every other
    check above -- the ID-set-equality check only looks at heading text,
    never at what follows it. This closes that "空振り" gap: every
    companion heading's own section body (up to the next heading) must be
    non-empty after stripping whitespace and the trailing '---' separator.
    A row with genuinely nothing moved out of it still carries an explicit
    placeholder sentence ("No historical narrative was separated out of
    this row's current text...") rather than an empty section, by design."""
    sections = _companion_sections(CONDITIONS_HISTORY_PATH)
    empty = sorted(slug for slug, body in sections.items() if not body)
    assert not empty, (
        f"{CONDITIONS_HISTORY_PATH} has heading(s) with an empty section body: {empty}"
    )
