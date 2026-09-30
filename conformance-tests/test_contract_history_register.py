"""Register test for `spec/CONTRACT_HISTORY.md`, the R-10 (A) provenance
companion (design docs/design/PHASE8_EFFECTIVE_BOUNDS_AND_HYGIENE_V1.md §3
D-4, requester ruling §5 U-2 = (A); work order
docs/work-orders/WORK_ORDER_PHASE8_EFFECTIVE_BOUNDS_V1.md WP-3), REVISED for
contract 1.7.0's R-10 (B) prefix/insert removal (design docs/design/
PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md §3 D-9; work order
docs/work-orders/WORK_ORDER_PHASE9_CONTRACT_170_V1.md §2 WP-1 (6)).

Through contract 1.6.0, every provenance-marker-carrying contract value
carried its marker prefix/clause inline, so this file's scanner and every
comparison against `CONTRACT_HISTORY.md`'s quotes operated on the live
contract JSON's own values directly. Contract 1.7.0 removed the marker
prefix/insert from 26 of those 29 values (`spec/CONTRACT_HISTORY_MANIFEST.
json`), leaving `CONTRACT_HISTORY.md`'s own quotes holding the PRE-strip
text. Every scan and every quote comparison below is therefore now done
against the REVERSE-APPLIED value -- the manifest's `stripped_prefix` /
`stripped_insert` (and, for the entries that have one, `rewrite`) restored
onto today's live contract value at that path -- not the raw live value.
For the 3 `unstripped: true` manifest entries, reverse-apply is a no-op, so
this is unchanged behavior for them.

A new, additional assertion (not present through 1.6.0) is added at the
bottom of this file: the RAW (un-restored) contract JSON must have 0
scanner hits outside the 3 `unstripped: true` paths -- this is what makes a
half-finished strip (marker text left behind by accident) fail loudly here
rather than only via a stale `CONTRACT_HISTORY.md` quote.

The scanner itself (the `_PATTERNS` regex family) is UNCHANGED from phase 8
-- moved here again verbatim; only what it is run against has changed.

Six things are fixed:
  1. The scanner's set of "JSON paths carrying >=1 marker", computed against
     REVERSE-APPLIED values, equals the companion's set of `## <json_path>`
     heading text, exactly.
  2. The companion has no duplicate headings.
  3. Every heading's section body is non-empty.
  4. Every subordinate-ruling reference a section names actually exists as
     a numbered item under `spec/CCR_DISPOSITION.md`'s
     "### 従属判断 -- すべて裁定済み" heading.
  5. Every `## <json_path>` section's quote byte-matches the REVERSE-APPLIED
     contract value at that path (`assert checked == 17` for the "Since
     X.Y.Z" vs "Introduced in" cross-check runs unmodified against these
     same reverse-applied values).
  6. (new, contract 1.7.0) The RAW contract JSON has 0 scanner hits outside
     the 3 `unstripped: true` manifest paths.

No `@pytest.mark.condition(...)` marker is used anywhere in this file
(design §6.5/§6.6: this WP does not add a new common CONDITIONS.md row).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

CONTRACT_PATH = Path(__file__).parent.parent / "spec" / "data-service-api.v1.json"
COMPANION_PATH = Path(__file__).parent.parent / "spec" / "CONTRACT_HISTORY.md"
CCR_DISPOSITION_PATH = Path(__file__).parent.parent / "spec" / "CCR_DISPOSITION.md"
MANIFEST_PATH = Path(__file__).parent.parent / "spec" / "CONTRACT_HISTORY_MANIFEST.json"

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


# ---------------------------------------------------------------------------
# spec/CONTRACT_HISTORY_MANIFEST.json (contract 1.7.0, R-10 (B)) and the
# reverse-apply ("restore") this file needs to run the scanner and the
# companion-quote comparison against pre-strip text.
# ---------------------------------------------------------------------------


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _restore(path: str, value, manifest: dict):
    """Reverse contract 1.7.0's R-10 (B) prefix/insert removal at `path`, if
    any is recorded for it. Non-string values, and paths the manifest does
    not name at all, pass through unchanged -- the manifest only ever names
    the 29 provenance-marker-carrying string values (design Appendix B)."""
    if not isinstance(value, str):
        return value
    entry = manifest.get(path)
    if entry is None or entry.get("unstripped"):
        return value
    restored = value
    rewrite = entry.get("rewrite")
    if rewrite:
        to, frm = rewrite["to"], rewrite["from"]
        assert to in restored, f"{path}: rewrite.to {to!r} not found in live value -- manifest is stale"
        restored = restored.replace(to, frm, 1)
    insert = entry.get("stripped_insert")
    if insert:
        # `stripped_insert_suffix_length` names how many characters
        # followed the removed insert in the original (pre-strip) value,
        # measured from the end of the value back to the insertion point --
        # since removing a chunk never changes the characters that came
        # after it, that same length identifies the correct re-insertion
        # point in today's (stripped) value too: splice `insert` back in at
        # position len(restored) - suffix_length.
        suffix_length = entry.get("stripped_insert_suffix_length")
        assert suffix_length is not None, f"{path}: has stripped_insert but no stripped_insert_suffix_length"
        assert 0 <= suffix_length <= len(restored), (
            f"{path}: stripped_insert_suffix_length {suffix_length} out of range for a "
            f"{len(restored)}-character value -- manifest is stale relative to the live contract"
        )
        split_at = len(restored) - suffix_length
        restored = restored[:split_at] + insert + restored[split_at:]
    prefix = entry.get("stripped_prefix")
    if prefix:
        restored = prefix + restored
    return restored


def _scanner_paths() -> set[str]:
    """The set of JSON paths in the live contract whose REVERSE-APPLIED
    value matches >=1 provenance-marker pattern."""
    contract = json.loads(CONTRACT_PATH.read_text())
    manifest = _manifest()
    return {
        path
        for path, value in _walk(contract, "")
        if _find_matches(_restore(path, value, manifest))
    }


# ---------------------------------------------------------------------------
# Companion (spec/CONTRACT_HISTORY.md) parsing.
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
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
        f"the marker scanner found 0 JSON paths (reverse-applied) in {CONTRACT_PATH} -- an empty "
        "result would make the set-equality register test vacuously pass"
    )
    assert len(paths) == 29, f"expected 29 marker-carrying JSON paths (reverse-applied), found {len(paths)}: {sorted(paths)}"


def test_contract_history_companion_heading_set_matches_the_scanner():
    """Completion condition 1: the scanner-derived (reverse-applied) set of
    marker-carrying JSON paths equals the companion's set of `##
    <json_path>` headings, exactly."""
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
    companion section (a "従属判断 N" line) must name an N that actually
    exists as a numbered item under `spec/CCR_DISPOSITION.md`'s "### 従属判断
    -- すべて裁定済み" heading, and every section must name at least one such
    reference."""
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
# Quote-vs-contract verbatim drift and "Introduced in" checks -- run against
# REVERSE-APPLIED values as of contract 1.7.0 (previously the raw live
# value, through contract 1.6.0).
# ---------------------------------------------------------------------------


def _contract_values_by_path() -> dict[str, object]:
    """Every leaf (path, value) in the live contract JSON, REVERSE-APPLIED,
    keyed by path."""
    contract = json.loads(CONTRACT_PATH.read_text())
    manifest = _manifest()
    return {path: _restore(path, value, manifest) for path, value in _walk(contract, "")}


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
    """Ruling 1 (phase 8 supervisor rework 1): for every `## <json_path>`
    section, the section's quoted text must byte-match the REVERSE-APPLIED
    value at that JSON path in the contract -- i.e. the pre-1.7.0-strip
    text, reconstructed from today's live contract value via
    `spec/CONTRACT_HISTORY_MANIFEST.json`."""
    contract_values = _contract_values_by_path()
    quotes = _companion_quotes()
    assert quotes, f"found 0 quoted sections in {COMPANION_PATH}"

    mismatched: list[str] = []
    for path, quote in quotes.items():
        contract_value = contract_values.get(path)
        if contract_value != quote:
            contract_len = len(contract_value) if isinstance(contract_value, str) else -1
            mismatched.append(
                f"{path} (companion quote {len(quote)} chars, reverse-applied contract value {contract_len} chars)"
            )
    assert not mismatched, (
        f"{COMPANION_PATH} section(s) whose quoted text does not byte-match the "
        f"REVERSE-APPLIED value at that JSON path in {CONTRACT_PATH}: {mismatched}"
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
    """Ruling 3 (phase 8 supervisor rework 1): for every section whose quote
    names a "Since X.Y.Z" marker, the '**Introduced in:**' field must be
    consistent with X.Y.Z -- either equal to it, or containing it within
    the field's own declared range (the one cumulative case,
    `versioning.version_binding`, now `contract 1.2.0 through 1.7.0
    (cumulative)`). `assert checked == 17` is unchanged by contract 1.7.0:
    none of 1.7.0's own new prose uses a literal "Since 1.7.0" phrasing
    (design docs/design/PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.
    md §3 D-8's version_binding paragraph says "Only an implementation
    declaring 1.7.0 ...", never "Since 1.7.0"), so the set of sections whose
    quote contains a "Since X.Y.Z" substring is unchanged from phase 8's own
    count."""
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
        f"expected 17 sections whose quote names a 'Since X.Y.Z' marker (unchanged from phase 8), "
        f"found {checked}: {sorted(p for p, q in quotes.items() if _SINCE_VERSION_RE.search(q))}"
    )
    assert not mismatched, (
        f"{COMPANION_PATH} section(s) whose 'Since X.Y.Z' marker disagrees with their "
        f"'**Introduced in:**' field: {mismatched}"
    )


# ---------------------------------------------------------------------------
# New for contract 1.7.0 (R-10 (B)): the RAW (un-restored) contract JSON
# must have 0 scanner hits outside the 3 `unstripped: true` manifest paths
# -- this is what catches a strip that was started but not completed (marker
# text accidentally left behind in the live contract body).
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Phase 10 WP-5a (contract 1.8.0, design docs/design/
# PHASE10_DEPLOYMENT_EVIDENCE_V1.md §3 D-5 (i), CCR_DISPOSITION.md
# subordinate ruling 13): contract 1.8.0 introduces 3 new contract values
# ((1) capability_status.rules' new array element, (2) limits.profile's
# appended sentence, (3) versioning.obligations' 1.8.0 entry) that --
# unlike every "## <json_path>" section above -- carry NO "Since
# X.Y.Z"/"subordinate ruling N"-shaped provenance marker of their own
# (verified: 0 scanner-pattern hits on all 3). An earlier revision of this
# WP recorded that provenance as a free-standing "### " (3-hash) anchor
# section in the companion, deliberately outside this file's "## <json_
# path>" heading-set-equality check, with 3 dedicated tests here pinning
# that anchor's text, its subordinate-ruling reference, and its
# non-membership in the manifest. Supervisor ruling 2026-09-08 (WP-5a
# review, CONTRACT_HISTORY "### " free anchor disposition) rejected that
# shape: a second, unregistered heading kind left this register's own "2
# sets match exactly" guarantee with an escape hatch for any anchor added
# the same way later, and `## versioning.version_binding` already carries
# subordinate ruling 13 in its own listing (it is one of 1.8.0's own 4
# pieces of prose). The 3 new marker-free values' provenance, and the
# monitor-finalized anchor sentence itself, are now recorded verbatim in
# `## versioning.version_binding`'s own "Revision note" instead -- inside
# the existing, already-registered section, not a new heading -- so no
# dedicated test is needed here: the ordinary `## <json_path>` register
# checks above (heading-set equality, quote-verbatim, ruling-reference
# validity) already cover that section, unchanged.
# ---------------------------------------------------------------------------


def test_stripped_contract_has_zero_scanner_hits_outside_the_unstripped_paths():
    """New assert (work order §2 WP-1 (6) / (18)): scan the RAW contract
    JSON (no reverse-apply) and require that every path the scanner still
    flags is one of the manifest's `unstripped: true` paths -- i.e. that
    R-10 (B) actually removed every marker it claims to have removed, from
    every value it claims to have removed it from."""
    contract = json.loads(CONTRACT_PATH.read_text())
    manifest = _manifest()
    unstripped_paths = {path for path, entry in manifest.items() if entry.get("unstripped")}
    assert unstripped_paths, "manifest must name at least 1 unstripped path"

    raw_hit_paths = {path for path, value in _walk(contract, "") if _find_matches(value)}
    assert raw_hit_paths, "the marker scanner found 0 hits in the RAW (un-restored) contract JSON"

    unexpected = sorted(raw_hit_paths - unstripped_paths)
    assert not unexpected, (
        f"the RAW contract JSON still has scanner hit(s) outside the manifest's `unstripped: true` "
        f"paths -- R-10 (B) left provenance-marker text behind at: {unexpected}"
    )
    assert raw_hit_paths == unstripped_paths, (
        f"expected the raw contract's hit-path set to equal exactly the manifest's unstripped-path "
        f"set; raw={sorted(raw_hit_paths)} unstripped={sorted(unstripped_paths)}"
    )
