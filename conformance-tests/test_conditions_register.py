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

Known gaps (recorded per docs/work-orders/OPERATING_CONDITIONS.md 1.12-71:
a gap that cannot let a contract violation or a Security Invariant breach
through the completion gate is recorded here and not filed in the ledger):
    1. not detected: a test-name reference written in any shape other
       than the 5 backtick forms.
       why: `_extract_references` reads backtick spans only, and inside
       them only D-3's 5 forms.
       caught by: `test_conditions_md_has_no_test_name_token_outside_
       backticks` (a naked `test_` token anywhere is red) and
       `test_conditions_md_allowlist_matches_known_non_test_name_spans`
       (a backtick span holding `test_` that matches none of the 5 forms
       is red unless allowlisted); a sentence that names a test without
       any `test_` token at all is left to review.
    2. not detected: which file a path-omitted bare name means when two
       directories hold the same basename.
       why: the path-omitted forms resolve by basename across the 4 test
       directories.
       caught by: the resolver itself -- a non-unique basename fails
       with "ambiguous basename" instead of resolving to one of them, so
       this is never silent.
    3. not detected: whether a cited test actually DRIVES the condition
       it is cited for.
       why: resolution only proves that the def exists at that path.
       caught by: the `@pytest.mark.condition(...)` matching in both
       directions (the two checks at the top of this file) and the
       acceptance audit.
    4. not detected: the one allowlisted span D-3 (f) records
       (`pytest_collection_modifyitems`) -- it is never resolved.
       why: it holds `test_` but matches none of the 5 forms.
       caught by: that allowlist being pinned as an exact set, so a
       second such span is red and needs its own explicit commit.
    5. not detected: whether a row's Invariants column names the right
       Security Invariants for its own Condition text.
       why: this file reads only the ID and Status columns; Invariants is
       never parsed by either direction above.
       caught by: the acceptance audit, reading the Condition text and
       the Invariants column together against the supervisor ruling that
       fixed the value (e.g. C-31's own ruling 6).
"""
from __future__ import annotations

import ast
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


# ---------------------------------------------------------------------------
# R-74 (docs/work-orders/WORK_ORDER_R74_CONDITIONS_TEST_NAME_RESOLUTION_V1.md):
# resolve every backtick test-name reference CONDITIONS.md's Evidence/Status
# prose makes against the real `def`/`async def`s in the 4 test directories,
# the same property R-64 fixed for CONTROL_MAPPING.md's own SI-structured
# prose -- but CONDITIONS.md is one flat table with no SI/peer partition, its
# own dominant reference shape is a bare *file* name (a whole-suite
# reference), and it also uses a 3-level `path::Class::method` form R-64
# never had to resolve. This section is deliberately self-contained: it does
# not import anything from test_control_mapping_register.py (design D-1),
# so a change to that file's own private index/resolve shape cannot silently
# break this one.
# ---------------------------------------------------------------------------

# D-3: the ONE file this check reads -- never a glob, never
# CONDITIONS_HISTORY_PATH (the verbatim archive of superseded claims, where a
# since-renamed test name is CORRECT to find, D-2).
TEST_NAME_RESOLUTION_TARGET_PATH = CONDITIONS_PATH

# D-1: the 4 test directories a `def`/`async def` index is built over (`ast`,
# not pytest collection, which needs PostgreSQL/a DSN -- OPERATING_CONDITIONS
# section 2 item 12).
_TEST_DIR_KEYS = ("r2db-api", "MitateDB-api", "conformance-tests", "tools/tests")
_REPO_ROOT = CONDITIONS_PATH.parent.parent
_TEST_DIRS = {
    "r2db-api": _REPO_ROOT / "r2db-api" / "tests",
    "MitateDB-api": _REPO_ROOT / "MitateDB-api" / "tests",
    "conformance-tests": _REPO_ROOT / "conformance-tests",
    "tools/tests": _REPO_ROOT / "tools" / "tests",
}
# The rel-path prefix each dir_key's own files carry -- used only to tell
# "a directory-carrying path outside all 4 directories" (D-5's dedicated
# `not indexed` reason) apart from "inside a known directory but that exact
# file is missing there" (`file not found`).
_DIR_PREFIXES = {
    "r2db-api": "r2db-api/tests/",
    "MitateDB-api": "MitateDB-api/tests/",
    "conformance-tests": "conformance-tests/",
    "tools/tests": "tools/tests/",
}

# D-3: extraction is limited to spans whose name (or, for the bare-file form,
# whose path basename) starts with `test_` -- a span that does not is not a
# test-name reference at all (D-3 (e); CONDITIONS.md's C-12 row's `cell.py::_where`
# is the real example: an implementation-code citation, not a test).
_THREE_LEVEL_FORM_RE = re.compile(r"^(\S+\.py)::([A-Za-z_]\w*)::(test_\w+)$")
_FULL_FORM_RE = re.compile(r"^(\S+\.py)::(test_\w+)$")
_BARE_COLON_FORM_RE = re.compile(r"^::(test_\w+)$")
_BARE_NAME_FORM_RE = re.compile(r"^(test_\w+)$")
_BARE_FILE_FORM_RE = re.compile(r"^(\S*/)?(test_\w+\.py)$")

# D-3 (f): spans containing `test_` that match none of the 5 forms above --
# measured directly against the current file: exactly one, the conftest.py
# hook name cited in the C-26 row's own Evidence prose. A new reference shape
# entering the document changes this set and must be triaged by hand (either
# widen the rules above, or add the new span here).
_KNOWN_NON_TEST_NAME_SPANS = frozenset({"pytest_collection_modifyitems"})

# D-4: one floor per reference form, each today's observed count (5 / 2 /
# 1 / 24 / 44 for full/three-level/bare-`::`/bare-name/bare-file) minus a
# margin -- the bare-`::` form's margin is 0 since only one occurrence
# exists today, so any loss of it must already be a red. To re-measure,
# run this file's own `_find_references` against CONDITIONS.md and count
# by form; a floor must never guard only against zero (OPERATING_CONDITIONS
# section 1.5 item 32).
FULL_FORM_FLOOR = 4
THREE_LEVEL_FORM_FLOOR = 1
BARE_COLON_FORM_FLOOR = 1
BARE_NAME_FORM_FLOOR = 20
BARE_FILE_FORM_FLOOR = 40
# D-2 (完了条件 8): at least one reference must be found OUTSIDE the `|`-started
# table -- measured directly against the current file: 3 (the preamble's own
# two citations of this file's name, plus the Update convention's `[history]`
# sentence's own file-name mention).
OUT_OF_TABLE_FORM_FLOOR = 1


def _iter_defs_in_file(path: Path) -> dict[str | None, set[str]]:
    """D-1: `{class name or None: {def names}}` for one file -- module-level
    `def`/`async def` go under `None`, a module-level class's own directly
    nested `def`/`async def` go under that class's name (never a further-
    nested function, which pytest cannot collect as its own item). The
    per-file MAPPING this returns disagrees in *shape* with
    test_control_mapping_register.py's own def index (a flat `{def names}`
    set per file, no class distinction) -- that file only ever needs "is
    this name a def anywhere in this file", CONDITIONS.md's own 3-level
    `path::Class::method` references need the class kept (D-1)."""
    try:
        tree = ast.parse(path.read_text())
    except (SyntaxError, UnicodeDecodeError):
        return {None: set()}
    entry: dict[str | None, set[str]] = {None: set()}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            entry[None].add(node.name)
        elif isinstance(node, ast.ClassDef):
            entry[node.name] = {
                child.name for child in node.body if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
    return entry


def _build_def_index() -> dict[str, dict[str, dict[str | None, set[str]]]]:
    """D-1: `dir_key -> {repository-relative posix path: per-file class/def
    map}`, one entry per `*.py` file anywhere under each of the 4 test
    directories (`rglob`)."""
    index: dict[str, dict[str, dict[str | None, set[str]]]] = {}
    for dir_key in _TEST_DIR_KEYS:
        entries: dict[str, dict[str | None, set[str]]] = {}
        dir_path = _TEST_DIRS[dir_key]
        if dir_path.is_dir():
            for f in sorted(dir_path.rglob("*.py")):
                if "__pycache__" in f.parts:
                    continue
                rel = f.relative_to(_REPO_ROOT).as_posix()
                entries[rel] = _iter_defs_in_file(f)
        index[dir_key] = entries
    return index


def _names_in_entry(entry: dict[str | None, set[str]]) -> set[str]:
    names: set[str] = set()
    for names_here in entry.values():
        names |= names_here
    return names


def _is_outside_known_dirs(path_str: str) -> bool:
    """D-3/D-5: a directory-carrying `path_str` that does not start with any
    of the 4 directories' own rel-path prefix is not indexed at all -- a
    different failure than a real path inside one of the 4 whose file simply
    does not exist there."""
    return not any(path_str.startswith(prefix) for prefix in _DIR_PREFIXES.values())


def _candidates_for_path(index, path_str: str) -> list[tuple[str, str]]:
    """D-3 (a)/(d): a directory-carrying `path_str` resolves against the
    exact rel path in any of the 4 directories; a directory-omitted
    `path_str` (a bare basename) resolves against every file across all 4
    directories whose own basename matches -- CONDITIONS.md's rows are not
    partitioned by peer (D-3 (c)'s own note), so nothing here is peer-scoped
    the way test_control_mapping_register.py's bare-form resolution is."""
    if "/" in path_str:
        for dir_key, entries in index.items():
            if path_str in entries:
                return [(dir_key, path_str)]
        return []
    return [
        (dir_key, rel)
        for dir_key, entries in index.items()
        for rel in entries
        if rel.rsplit("/", 1)[-1] == path_str
    ]


def _resolve_full(index, path_str: str, name: str) -> tuple[bool, str]:
    """D-3 (a)."""
    if "/" in path_str and _is_outside_known_dirs(path_str):
        return False, "not indexed (outside the 4 test directories)"
    candidates = _candidates_for_path(index, path_str)
    if not candidates:
        return False, "file not found"
    if len(candidates) > 1:
        return False, "ambiguous basename"
    dir_key, rel = candidates[0]
    if name not in _names_in_entry(index[dir_key][rel]):
        return False, "def not found"
    return True, ""


def _resolve_three(index, path_str: str, class_name: str, method_name: str) -> tuple[bool, str]:
    """D-3 (b): the file's MODULE-level class `class_name` must carry
    `method_name` directly (never a nested class, which `_iter_defs_in_file`
    never descends into)."""
    if "/" in path_str and _is_outside_known_dirs(path_str):
        return False, "not indexed (outside the 4 test directories)"
    candidates = _candidates_for_path(index, path_str)
    if not candidates:
        return False, "file not found"
    if len(candidates) > 1:
        return False, "ambiguous basename"
    dir_key, rel = candidates[0]
    entry = index[dir_key][rel]
    if class_name not in entry:
        return False, "class not found"
    if method_name not in entry[class_name]:
        return False, "def not found"
    return True, ""


def _resolve_bare(index, name: str) -> bool:
    """D-3 (c): `name` is a `def` somewhere in the whole index -- which
    file is not checked (D-1's own stated limit, same as R-64's bare-form
    resolution)."""
    return any(name in _names_in_entry(entry) for entries in index.values() for entry in entries.values())


def _resolve_bare_file(index, path_str: str) -> tuple[bool, str]:
    """D-3 (d): a whole-file reference -- uniqueness of a path-omitted
    basename is NOT required (D-3 (d)'s own note: today's 13 path-omitted
    bare file names are each unique, but this form does not assert it)."""
    if "/" in path_str and _is_outside_known_dirs(path_str):
        return False, "not indexed (outside the 4 test directories)"
    candidates = _candidates_for_path(index, path_str)
    if not candidates:
        return False, "file not found"
    return True, ""


def _extract_references(line: str) -> tuple[list[tuple], list[str]]:
    """The 5 reference shapes D-3 defines, extracted from one line's own
    backtick spans, plus (separately) every span that contains `test_` but
    matches none of the 5 -- D-3 (f)'s allowlist candidates. A span with no
    `test_` anywhere (D-3 (e), an implementation-code citation) is not
    yielded at all, in either list."""
    refs: list[tuple] = []
    allow: list[str] = []
    for span in re.findall(r"`([^`]+)`", line):
        m = _THREE_LEVEL_FORM_RE.match(span)
        if m:
            refs.append(("three",) + m.groups())
            continue
        m = _FULL_FORM_RE.match(span)
        if m:
            refs.append(("full",) + m.groups())
            continue
        m = _BARE_COLON_FORM_RE.match(span)
        if m:
            refs.append(("bare_colon", m.group(1)))
            continue
        m = _BARE_NAME_FORM_RE.match(span)
        if m:
            refs.append(("bare_name", m.group(1)))
            continue
        m = _BARE_FILE_FORM_RE.match(span)
        if m:
            refs.append(("bare_file", (m.group(1) or "") + m.group(2)))
            continue
        if "test_" in span:
            allow.append(span)
    return refs, allow


def _iter_nonblank_lines(text: str):
    """D-2: every non-blank line, not only `|`-started table rows -- the
    real file's own preamble carries 3 test-name references outside the
    table (three places in `conformance-tests/CONDITIONS.md`)."""
    for i, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        yield i, line


def _is_table_line(line: str) -> bool:
    return line.strip().startswith("|")


def _find_references(text: str):
    """`(line_num, ref)` for every extracted reference, and `(line_num,
    span)` for every D-3 (f) allowlist candidate, scanning every non-blank
    line of `text` (D-2)."""
    refs: list[tuple[int, tuple]] = []
    allow: list[tuple[int, str]] = []
    for line_num, line in _iter_nonblank_lines(text):
        line_refs, line_allow = _extract_references(line)
        refs.extend((line_num, r) for r in line_refs)
        allow.extend((line_num, a) for a in line_allow)
    return refs, allow


def _resolve_ref(index, ref: tuple) -> tuple[bool, str, str]:
    kind = ref[0]
    if kind == "three":
        _kind, path_str, class_name, method_name = ref
        ok, reason = _resolve_three(index, path_str, class_name, method_name)
        span = f"{path_str}::{class_name}::{method_name}"
    elif kind == "full":
        _kind, path_str, name = ref
        ok, reason = _resolve_full(index, path_str, name)
        span = f"{path_str}::{name}"
    elif kind == "bare_colon":
        _kind, name = ref
        resolved = _resolve_bare(index, name)
        ok, reason, span = resolved, ("" if resolved else "def not found"), f"::{name}"
    elif kind == "bare_name":
        _kind, name = ref
        resolved = _resolve_bare(index, name)
        ok, reason, span = resolved, ("" if resolved else "def not found"), name
    elif kind == "bare_file":
        _kind, path_str = ref
        ok, reason = _resolve_bare_file(index, path_str)
        span = path_str
    else:  # pragma: no cover -- _extract_references only ever yields these 5 kinds
        raise AssertionError(f"unknown reference kind: {kind!r}")
    return ok, reason, span


def _find_unresolved_references(text: str, index, source_name: str | None = None) -> list[str]:
    """D-5: one message per unresolved reference, never folded/summarized,
    so every offender is visible from one failed assertion. `source_name`
    defaults to `TEST_NAME_RESOLUTION_TARGET_PATH.name` (`CONDITIONS.md`,
    not the absolute path); a caller passing synthetic fixture text supplies
    its own label instead, so a fixture's violation never LOOKS like a real
    CONDITIONS.md line number."""
    if source_name is None:
        source_name = TEST_NAME_RESOLUTION_TARGET_PATH.name
    violations: list[str] = []
    refs, _allow = _find_references(text)
    for line_num, ref in refs:
        ok, reason, span = _resolve_ref(index, ref)
        if not ok:
            violations.append(f"{source_name}:{line_num}: `{span}` ({reason})")
    return violations


def test_test_name_resolution_target_path_is_pinned_to_conditions_md_only():
    """D-2/D-3: the object of this check is ONE constant, pinned by direct
    equality, never
    CONDITIONS_HISTORY_PATH (the verbatim archive of superseded claims,
    where an unresolvable old test name is CORRECT to find)."""
    assert TEST_NAME_RESOLUTION_TARGET_PATH == CONDITIONS_PATH
    assert TEST_NAME_RESOLUTION_TARGET_PATH != CONDITIONS_HISTORY_PATH


def test_conditions_md_test_name_def_index_has_at_least_one_entry_per_directory():
    """D-4: the `ast` index itself must not be silently empty in any of the
    4 directories -- judged on the number of indexed DEF NAMES, not on dict
    truthiness (`{None: set()}` is itself a non-empty dict even when the
    set it holds is empty, so a naive `any(index.get(dir_key, {}).values())`
    would pass vacuously as soon as a directory has one file, indexed or
    not)."""
    index = _build_def_index()
    empty_dirs = [
        dir_key
        for dir_key in _TEST_DIR_KEYS
        if not any(_names_in_entry(entry) for entry in index.get(dir_key, {}).values())
    ]
    assert not empty_dirs, f"directory key(s) with zero indexed test defs: {empty_dirs}"


def test_conditions_md_every_test_name_reference_resolves():
    """D-3/D-6: the real file's every test-name reference resolves.
    Measured directly against the current file: 0 unresolved references."""
    text = TEST_NAME_RESOLUTION_TARGET_PATH.read_text()
    index = _build_def_index()
    violations = _find_unresolved_references(text, index)
    assert violations == [], "\n".join(violations)


def test_conditions_md_test_name_reference_extraction_meets_the_floor():
    """D-4: the reference extraction must not go silently empty on the real
    file -- one floor per form."""
    text = TEST_NAME_RESOLUTION_TARGET_PATH.read_text()
    refs, _allow = _find_references(text)
    counts = {"three": 0, "full": 0, "bare_colon": 0, "bare_name": 0, "bare_file": 0}
    for _line_num, ref in refs:
        counts[ref[0]] += 1
    assert counts["full"] >= FULL_FORM_FLOOR, f"full-form reference count {counts['full']} below floor {FULL_FORM_FLOOR}"
    assert counts["three"] >= THREE_LEVEL_FORM_FLOOR, (
        f"3-level reference count {counts['three']} below floor {THREE_LEVEL_FORM_FLOOR}"
    )
    assert counts["bare_colon"] >= BARE_COLON_FORM_FLOOR, (
        f"bare '::' reference count {counts['bare_colon']} below floor {BARE_COLON_FORM_FLOOR}"
    )
    assert counts["bare_name"] >= BARE_NAME_FORM_FLOOR, (
        f"bare-name reference count {counts['bare_name']} below floor {BARE_NAME_FORM_FLOOR}"
    )
    assert counts["bare_file"] >= BARE_FILE_FORM_FLOOR, (
        f"bare-file reference count {counts['bare_file']} below floor {BARE_FILE_FORM_FLOOR}"
    )


def test_conditions_md_allowlist_matches_known_non_test_name_spans():
    """D-3 (f): every span containing `test_` that matches none of the 5
    reference forms must be an already-known, triaged one -- both
    directions of the diff are reported: a span the document carries that
    `_KNOWN_NON_TEST_NAME_SPANS` does not (untriaged), and a span
    `_KNOWN_NON_TEST_NAME_SPANS` carries that the document no longer does
    (stale)."""
    text = TEST_NAME_RESOLUTION_TARGET_PATH.read_text()
    _refs, allow = _find_references(text)
    allow_spans = {span for _line_num, span in allow}
    untriaged = sorted(allow_spans - _KNOWN_NON_TEST_NAME_SPANS)
    stale = sorted(_KNOWN_NON_TEST_NAME_SPANS - allow_spans)
    assert allow_spans == _KNOWN_NON_TEST_NAME_SPANS, (
        f"allowlist mismatch -- untriaged span(s) in the document but not in "
        f"_KNOWN_NON_TEST_NAME_SPANS: {untriaged}; span(s) in "
        f"_KNOWN_NON_TEST_NAME_SPANS but no longer in the document: {stale}"
    )


def test_conditions_md_has_out_of_table_test_name_references():
    """D-2: the real file carries at least one test-name reference OUTSIDE
    the `|`-started table -- measured directly: 3 (in `conformance-tests/CONDITIONS.md`)."""
    text = TEST_NAME_RESOLUTION_TARGET_PATH.read_text()
    out_of_table = [
        (line_num, ref)
        for line_num, line in _iter_nonblank_lines(text)
        if not _is_table_line(line)
        for ref in _extract_references(line)[0]
    ]
    assert len(out_of_table) >= OUT_OF_TABLE_FORM_FLOOR, (
        f"expected at least {OUT_OF_TABLE_FORM_FLOOR} out-of-table reference(s), found {len(out_of_table)}"
    )


def test_fixture_out_of_table_line_reference_is_scanned():
    """D-2: a non-blank line that does not start with `|` is still scanned
    for test-name references."""
    text = "A prose paragraph outside the table cites `test_totally_fake_outside_table_reference` as evidence.\n"
    violations = _find_unresolved_references(text, {}, source_name="fixture")
    assert violations, "expected the out-of-table paragraph line's fake reference to be flagged"
    assert violations[0].startswith("fixture:"), violations[0]


def test_fixture_async_def_test_is_indexed_and_resolves():
    """D-1: an `async def` test must be indexed. This uses a real one
    (`r2db-api/tests/test_preauth_concurrency_bound.py::
    test_unauthenticated_flood_is_bounded_by_concurrency`, `async def`, no
    sync alias) in a synthetic document line, since none of CONDITIONS.md's
    own real references happen to name an async-only def today."""
    index = _build_def_index()
    text = (
        "A synthetic evidence line cites `r2db-api/tests/test_preauth_concurrency_bound.py::"
        "test_unauthenticated_flood_is_bounded_by_concurrency` as async-only coverage.\n"
    )
    violations = _find_unresolved_references(text, index, source_name="fixture")
    assert violations == [], "\n".join(violations)


def test_fixture_implementation_code_reference_is_not_extracted():
    """D-3 (e): a backtick span whose name has no `test_` prefix (and whose
    path's own basename does not either) is never extracted as a reference
    at all -- matches the real file's own `cell.py::_where` (CONDITIONS.md's
    C-12 row)."""
    refs, allow = _extract_references("An implementation-code citation `cell.py::_where`, no test_ prefix anywhere.")
    assert refs == []
    assert allow == []


def _fake_index(**dir_entries):
    """`{dir_key: {rel_path: {class-or-None: {def names}}}}`, the same shape
    `_build_def_index` returns, built by hand so the fixture tests below
    never touch the real filesystem."""
    return dir_entries


def test_fixture_full_form_unknown_file_does_not_resolve():
    """D-3 (a): a real def name against a path that is not indexed."""
    index = _fake_index(**{"r2db-api": {"r2db-api/tests/test_real.py": {None: {"test_real"}}}})
    ok, reason = _resolve_full(index, "r2db-api/tests/test_fake.py", "test_real")
    assert not ok
    assert reason == "file not found"


def test_fixture_full_form_unknown_def_does_not_resolve():
    """D-3 (a): a real path with a def name that is not one of its own."""
    index = _fake_index(**{"r2db-api": {"r2db-api/tests/test_real.py": {None: {"test_real"}}}})
    ok, reason = _resolve_full(index, "r2db-api/tests/test_real.py", "test_fake")
    assert not ok
    assert reason == "def not found"


def test_fixture_three_level_form_unknown_class_does_not_resolve():
    """D-3 (b): the file exists and carries a class, but not the one the
    reference names."""
    index = _fake_index(**{"MitateDB-api": {"MitateDB-api/tests/test_real.py": {"RealTests": {"test_real"}}}})
    ok, reason = _resolve_three(index, "MitateDB-api/tests/test_real.py", "FakeTests", "test_real")
    assert not ok
    assert reason == "class not found"


def test_fixture_path_outside_the_4_test_directories_is_not_indexed():
    """D-5: a directory-carrying path outside all 4 test directories gets
    its own reason, distinct from `file not found`."""
    ok, reason = _resolve_full(_fake_index(), "some_other_place/tests/test_outside.py", "test_outside")
    assert not ok
    assert reason == "not indexed (outside the 4 test directories)"


# 完了条件 15 (指示書 §2.3): no `test_[a-z0-9_]+`-shaped token appears
# OUTSIDE a backtick span anywhere in CONDITIONS.md. A token like that would
# name a test but escape every extraction/resolution check above entirely,
# since `_extract_references` only ever looks inside backtick spans. The
# left word boundary `(?<![A-Za-z0-9_])` keeps a longer identifier that
# merely CONTAINS `test_` (e.g. `pytest_collection_modifyitems`) from being
# read as its own naked reference; the character set stays `[a-z0-9_]`
# since every real test name is snake_case.
_NAKED_TEST_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_])test_[a-z0-9_]+")


def _find_naked_test_tokens(text: str) -> list[tuple[int, str]]:
    """`(line_num, token)` for every `test_[a-z0-9_]+` token found OUTSIDE a
    backtick span, on every non-blank line (D-2)."""
    naked: list[tuple[int, str]] = []
    for line_num, line in _iter_nonblank_lines(text):
        stripped = re.sub(r"`[^`]*`", "", line)
        naked.extend((line_num, m.group(0)) for m in _NAKED_TEST_TOKEN_RE.finditer(stripped))
    return naked


def test_conditions_md_has_no_test_name_token_outside_backticks():
    """Completion condition 15: measured directly against the current
    file: 0 naked `test_`-shaped tokens."""
    text = TEST_NAME_RESOLUTION_TARGET_PATH.read_text()
    naked = _find_naked_test_tokens(text)
    assert naked == [], f"test_-shaped token(s) found outside backticks: {naked}"


def test_fixture_naked_test_name_token_outside_backticks_is_detected():
    """Completion condition 15: a `test_`-shaped token with no surrounding
    backticks is flagged."""
    text = "A prose line mentions test_naked_reference_without_backticks directly.\n"
    naked = _find_naked_test_tokens(text)
    assert naked, "expected the un-backticked test_ token to be flagged"
