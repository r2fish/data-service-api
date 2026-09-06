"""Register test for `spec/CONTRACT_HISTORY.md`, the R-10 (A) provenance
companion (design docs/design/PHASE8_EFFECTIVE_BOUNDS_AND_HYGIENE_V1.md §3
D-4, requester ruling §5 U-2 = (A); work order
docs/work-orders/WORK_ORDER_PHASE8_EFFECTIVE_BOUNDS_V1.md WP-3).

U-2 = (A) means the contract JSON (`spec/data-service-api.v1.json`, and both
peers' packaged copies) is byte-unchanged by this phase -- see the existing
byte-identity tests (`r2db-api/tests/test_http.py`,
`MitateDB-api/tests/test_http.py`) and `conformance-tests/test_contract.py`
(also unchanged). What this file's tests fix instead is that the companion
(`spec/CONTRACT_HISTORY.md`) exactly and correctly indexes every
provenance-marker-carrying value already inside the contract, so that a
future value newly carrying such a marker cannot land without a matching
companion section.

The scanner below is not a new invention: it is the SAME marker-pattern
regex family the design doc's Appendix A prototype
({scratchpad}/r10_marker_inventory.py) used to produce the verbatim
inventory that D-4 and U-2 are based on, moved here verbatim per phase 8
standing discipline 5 ("static rules move from a verbatim prototype into the
design/suite, unchanged"). It is intentionally permissive (it flags
"ruling", not just "subordinate ruling N") to over-collect rather than
under-collect -- under-collection would let a marker slip through
unindexed.

Four things are fixed, matching WP-3's completion conditions 1-4:
  1. The scanner's set of "JSON paths carrying >=1 marker" equals the
     companion's set of `## <json_path>` heading text, exactly (no more, no
     fewer) -- and that set is non-empty (an empty-set vacuous pass would
     repeat the L7-23 trap).
  2. The companion has no duplicate headings.
  3. Every heading's section body is non-empty.
  4. Every subordinate-ruling reference a section names actually exists as
     a numbered item under `spec/CCR_DISPOSITION.md`'s
     "### 従属判断 -- すべて裁定済み" heading.

No `@pytest.mark.condition(...)` marker is used anywhere in this file (design
§6.5/§6.6: this WP does not add a new common CONDITIONS.md row).

Two more standing tests were added on code-review remand (supervisor rework 1,
2026-09-06, rulings 1 and 3): quote-vs-contract verbatim drift (ruling 1 -- a
named, granted exception to standing discipline 9, since it enforces standing
disciplines 1/3 rather than adding a new kind of check) and "Introduced in"
vs. a quote's own "Since X.Y.Z" marker (ruling 3). Ruling 2 dropped the line
number a "従属判断 N" reference used to carry (see the note above
`_RULING_REF_RE`); ruling 4 was a wording-only fix to
`spec/CONTRACT_HISTORY.md` and `spec/README.md`, not to this file.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

CONTRACT_PATH = Path(__file__).parent.parent / "spec" / "data-service-api.v1.json"
COMPANION_PATH = Path(__file__).parent.parent / "spec" / "CONTRACT_HISTORY.md"
CCR_DISPOSITION_PATH = Path(__file__).parent.parent / "spec" / "CCR_DISPOSITION.md"

# ---------------------------------------------------------------------------
# The marker-pattern scanner, moved verbatim (regexes unchanged) from the
# design-doc Appendix A prototype ({scratchpad}/r10_marker_inventory.py).
# ---------------------------------------------------------------------------

_PATTERNS = {
    "Since 1.x.y": re.compile(r"Since 1\.\d+\.\d+"),
    "subordinate ruling N": re.compile(r"subordinate ruling[s]? \d+"),
    "superseded": re.compile(r"superseded"),
    "supersedes": re.compile(r"supersedes"),
    "ruling": re.compile(r"ruling"),
    "Phase N": re.compile(r"Phase \d"),
    "WP-N": re.compile(r"WP-\d"),
    "date YYYY-MM-DD": re.compile(r"20\d\d-\d\d-\d\d"),
    "CCR-N": re.compile(r"CCR-\d+"),
    "historical": re.compile(r"historical"),
    "previously": re.compile(r"previously"),
    "formerly": re.compile(r"formerly"),
    "was (leading)": re.compile(r"(?:^|[.!?]\s+|\"\s*|\(\s*)was "),
}


def _walk(node, path):
    """Yield (path_str, value) for every leaf in a JSON tree, using the same
    dotted/bracket path grammar as the Appendix A prototype (e.g.
    'a.b[3].c')."""
    if isinstance(node, dict):
        for k, v in node.items():
            child_path = f"{path}.{k}" if path else k
            yield from _walk(v, child_path)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            child_path = f"{path}[{i}]"
            yield from _walk(v, child_path)
    else:
        yield (path, node)


def _find_matches(value) -> list[str]:
    if not isinstance(value, str):
        return []
    return [name for name, rx in _PATTERNS.items() if rx.search(value)]


def _scanner_paths() -> set[str]:
    """The set of JSON paths in the live contract whose value matches >=1
    provenance-marker pattern."""
    contract = json.loads(CONTRACT_PATH.read_text())
    return {path for path, value in _walk(contract, "") if _find_matches(value)}


# ---------------------------------------------------------------------------
# Companion (spec/CONTRACT_HISTORY.md) parsing.
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
# Supervisor rework 1 (2026-09-06), ruling 2: a "従属判断 N — spec/CCR_DISPOSITION.md:LINE"
# reference used to carry a line number, but that number was never checked (the
# original review's MUT-C mutation -- rewriting the line number -- passed all 5
# original tests) and a single line inserted anywhere above in
# spec/CCR_DISPOSITION.md would silently shift every one of the 33 references at
# once. Rather than add a check that only re-derives a fragile line number, the
# ruling drops the line number from the reference entirely: a section now names
# only "従属判断 N", and the existing check below (the number is a real numbered
# item under CCR_DISPOSITION.md's subordinate-ruling heading) is the only
# validation this reference needs.
_RULING_REF_RE = re.compile(r"従属判断\s+(\d+)")


def _companion_heading_list() -> list[str]:
    """Raw heading text for every `## ...` heading, in file order, WITHOUT
    deduplication -- duplicate-detection needs the raw list, not a set."""
    text = COMPANION_PATH.read_text()
    return [m.group(1) for m in _HEADING_RE.finditer(text)]


def _companion_sections() -> dict[str, str]:
    """{heading_text: section_body} for every '## <heading>' section --
    the body is everything between that heading line and the next '## '
    heading (or end of file). Last-one-wins on a duplicate heading is fine
    here because duplication itself is caught separately by
    `test_contract_history_companion_has_no_duplicate_headings`."""
    text = COMPANION_PATH.read_text()
    matches = list(_HEADING_RE.finditer(text))
    sections: dict[str, str] = {}
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[m.group(1)] = text[start:end].strip()
    return sections


# ---------------------------------------------------------------------------
# CCR_DISPOSITION.md subordinate-ruling numbered-item scan (Appendix A §A.3a
# method, moved verbatim): find "### 従属判断" then, strictly after it, every
# line starting "N. **" at top level.
# ---------------------------------------------------------------------------

_SUBORDINATE_HEADING_MARKER = "### 従属判断"
_NUMBERED_ITEM_RE = re.compile(r"^(\d{1,2})\.\s+\*\*")


def _subordinate_ruling_numbers() -> set[int]:
    lines = CCR_DISPOSITION_PATH.read_text().splitlines()
    heading_line_idx = None
    for i, line in enumerate(lines, start=1):
        if line.strip().startswith(_SUBORDINATE_HEADING_MARKER):
            heading_line_idx = i
            break
    assert heading_line_idx is not None, (
        f"{CCR_DISPOSITION_PATH} has no '{_SUBORDINATE_HEADING_MARKER}' heading"
    )
    numbers: set[int] = set()
    for i, line in enumerate(lines, start=1):
        if i <= heading_line_idx:
            continue
        m = _NUMBERED_ITEM_RE.match(line)
        if m:
            numbers.add(int(m.group(1)))
    return numbers


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_scanner_finds_at_least_one_marker_carrying_json_path():
    """Non-空振り guard (standing discipline 1 / L7-23's own lesson): the
    scanner must not itself return an empty set -- an empty set on both
    sides of the equality check below would make that check vacuously pass
    without ever exercising anything."""
    paths = _scanner_paths()
    assert len(paths) >= 1, (
        f"the marker scanner found 0 JSON paths in {CONTRACT_PATH} -- an empty "
        "result would make the set-equality register test vacuously pass"
    )


def test_contract_history_companion_heading_set_matches_the_scanner():
    """Completion condition 1: the scanner-derived set of marker-carrying
    JSON paths equals the companion's set of `## <json_path>` headings,
    exactly."""
    scanner_paths = _scanner_paths()
    companion_paths = set(_companion_heading_list())
    missing_from_companion = sorted(scanner_paths - companion_paths)
    extra_in_companion = sorted(companion_paths - scanner_paths)
    assert not missing_from_companion and not extra_in_companion, (
        f"mismatch between the marker scanner's JSON-path set and "
        f"{COMPANION_PATH}'s heading set: "
        f"missing_from_companion={missing_from_companion} "
        f"extra_in_companion={extra_in_companion}"
    )


def test_contract_history_companion_has_no_duplicate_headings():
    """Completion condition 2."""
    headings = _companion_heading_list()
    duplicates = sorted({h for h in headings if headings.count(h) > 1})
    assert not duplicates, f"duplicate heading(s) in {COMPANION_PATH}: {duplicates}"


def test_contract_history_companion_every_section_is_non_empty():
    """Completion condition 3."""
    sections = _companion_sections()
    empty = sorted(path for path, body in sections.items() if not body)
    assert not empty, f"{COMPANION_PATH} has heading(s) with an empty section body: {empty}"


def test_contract_history_companion_ruling_references_exist_in_ccr_disposition():
    """Completion condition 4: every subordinate-ruling reference named in a
    companion section (a "従属判断 N" line -- supervisor rework 1 ruling 2
    dropped the trailing line number these once carried, see the note above
    `_RULING_REF_RE`) must name an N that actually exists as a numbered item
    under `spec/CCR_DISPOSITION.md`'s "### 従属判断 -- すべて裁定済み"
    heading, and every section must name at least one such reference."""
    valid_numbers = _subordinate_ruling_numbers()
    assert valid_numbers, f"found 0 numbered subordinate rulings in {CCR_DISPOSITION_PATH}"

    sections = _companion_sections()
    no_reference: list[str] = []
    invalid_references: list[tuple[str, int]] = []
    for path, body in sections.items():
        refs = _RULING_REF_RE.findall(body)
        if not refs:
            no_reference.append(path)
            continue
        for n_str in refs:
            n = int(n_str)
            if n not in valid_numbers:
                invalid_references.append((path, n))

    assert not no_reference, (
        f"{COMPANION_PATH} section(s) with no '従属判断 N' reference: {sorted(no_reference)}"
    )
    assert not invalid_references, (
        f"{COMPANION_PATH} section(s) reference a subordinate ruling number that is not "
        f"a numbered item in {CCR_DISPOSITION_PATH} (json_path, ruling_number): "
        f"{sorted(invalid_references)}"
    )


# ---------------------------------------------------------------------------
# Supervisor rework 1 (2026-09-06), rulings 1 and 3: two more standing tests,
# added on code-review remand. The original register test (above) fixed the
# *set* of anchors and the *presence* of a ruling reference and a non-empty
# body, but nothing checked that a section's quoted text is still what the
# contract JSON actually says, or that its "Introduced in" field is still
# consistent with the "Since X.Y.Z" the quote itself names -- both of these
# can drift silently (the original review's MUT-A and a version-rewrite
# mutation each passed all 5 original tests). Ruling 1 is a granted, named
# exception to standing discipline 9 (do not add checks beyond what the
# design ordered without a ruling): it is not a new mechanism, only standing
# disciplines 1 (verbatim) and 3 (no drift) applied to this file's own
# quotes, using the same `_walk` the scanner already uses.
# ---------------------------------------------------------------------------


def _contract_values_by_path() -> dict[str, object]:
    """Every leaf (path, value) in the live contract JSON, keyed by path --
    the same `_walk(contract, "")` the scanner uses, just kept as a dict
    instead of filtered down to marker-carrying paths."""
    contract = json.loads(CONTRACT_PATH.read_text())
    return dict(_walk(contract, ""))


def _companion_quotes() -> dict[str, str]:
    """{heading_text: quoted text} -- the content of each section's single
    '> '-prefixed quote line, with the leading '> ' (or bare '>') stripped.
    Every section currently holds its quote as one (long) line, not a
    wrapped multi-line blockquote; this helper asserts that shape holds
    rather than silently reading only the first of several lines."""
    sections = _companion_sections()
    quotes: dict[str, str] = {}
    for path, body in sections.items():
        quote_lines = [ln for ln in body.splitlines() if ln.startswith(">")]
        assert len(quote_lines) == 1, (
            f"{COMPANION_PATH} section '## {path}' has {len(quote_lines)} lines "
            "starting with '>' -- expected exactly 1 (a single-line quote block); "
            "this helper only reads a single quote line per section"
        )
        line = quote_lines[0]
        quotes[path] = line[2:] if line.startswith("> ") else line[1:]
    return quotes


def test_contract_history_companion_quote_matches_the_contract_value_verbatim():
    """Ruling 1: for every `## <json_path>` section, the section's quoted
    text must byte-match the live value at that JSON path in the contract
    (via the same `_walk` the scanner uses). A quote that has drifted from
    the contract value it claims to be a verbatim copy of is exactly the
    L7-23-shaped risk this companion exists to avoid -- the register test
    above fixes only the anchor *set*, not the anchor *content*."""
    contract_values = _contract_values_by_path()
    quotes = _companion_quotes()
    assert quotes, f"found 0 quoted sections in {COMPANION_PATH}"

    mismatched: list[str] = []
    for path, quote in quotes.items():
        contract_value = contract_values.get(path)
        if contract_value != quote:
            contract_len = len(contract_value) if isinstance(contract_value, str) else -1
            mismatched.append(
                f"{path} (companion quote {len(quote)} chars, contract value {contract_len} chars)"
            )
    assert not mismatched, (
        f"{COMPANION_PATH} section(s) whose quoted text does not byte-match the "
        f"live value at that JSON path in {CONTRACT_PATH}: {mismatched}"
    )


_INTRODUCED_IN_RE = re.compile(r"\*\*Introduced in:\*\*\s*(.+)")
_SINCE_VERSION_RE = re.compile(r"Since (\d+\.\d+\.\d+)")
_SINGLE_VERSION_RE = re.compile(r"^contract (\d+\.\d+\.\d+)$")
_VERSION_RANGE_RE = re.compile(r"^contract (\d+\.\d+\.\d+) through (\d+\.\d+\.\d+) \(cumulative\)$")


def _version_tuple(v: str) -> tuple[int, int, int]:
    major, minor, patch = v.split(".")
    return (int(major), int(minor), int(patch))


def _companion_introduced_in() -> dict[str, str]:
    """{heading_text: the '**Introduced in:**' field's value text}."""
    sections = _companion_sections()
    result: dict[str, str] = {}
    for path, body in sections.items():
        m = _INTRODUCED_IN_RE.search(body)
        assert m, f"{COMPANION_PATH} section '## {path}' has no '**Introduced in:**' line"
        result[path] = m.group(1).strip()
    return result


def test_contract_history_companion_introduced_in_agrees_with_a_since_marker_when_present():
    """Ruling 3 (design D-4 decision 3(iii) was previously checked only for
    non-emptiness): for every section whose quote names a "Since X.Y.Z"
    marker, the '**Introduced in:**' field must be consistent with X.Y.Z --
    either equal to it (the ordinary single-version case), or containing it
    within the field's own declared range (the one cumulative case,
    `versioning.version_binding`, whose value is a single paragraph spanning
    contract 1.2.0 through 1.6.0 and embeds one later "Since 1.5.0" clause
    added by a revision still under that same paragraph). A section whose
    quote names no "Since X.Y.Z" gets no machine check here -- format-only,
    already covered by the non-empty check above. 17 sections are
    machine-checked this way; the other 12 are not (matching the review's
    count)."""
    quotes = _companion_quotes()
    introduced_in = _companion_introduced_in()

    mismatched: list[str] = []
    checked = 0
    for path, quote in sorted(quotes.items()):
        since_versions = sorted(set(_SINCE_VERSION_RE.findall(quote)))
        if not since_versions:
            continue
        checked += 1
        field = introduced_in[path]
        single_m = _SINGLE_VERSION_RE.match(field)
        range_m = _VERSION_RANGE_RE.match(field)
        if single_m:
            ok = all(v == single_m.group(1) for v in since_versions)
        elif range_m:
            lo, hi = _version_tuple(range_m.group(1)), _version_tuple(range_m.group(2))
            ok = all(lo <= _version_tuple(v) <= hi for v in since_versions)
        else:
            ok = False
        if not ok:
            mismatched.append(f"{path} (Since {since_versions}, Introduced in {field!r})")

    assert checked == 17, (
        f"expected 17 sections whose quote names a 'Since X.Y.Z' marker (the "
        f"review's count), found {checked}: {sorted(p for p, q in quotes.items() if _SINCE_VERSION_RE.search(q))}"
    )
    assert not mismatched, (
        f"{COMPANION_PATH} section(s) whose 'Since X.Y.Z' marker disagrees with their "
        f"'**Introduced in:**' field: {mismatched}"
    )
