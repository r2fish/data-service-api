"""Mechanical fixation for `security/CONTROL_MAPPING.md`'s new (2.0)
heading/bullet form (design docs/design/CONTROL_MAPPING_RESTRUCTURE_V1.md
v0.3, section 5). Superseded phase 7 WP-7 (i)'s table-based checks below
this docstring's predecessor guarded (`security/CONTROL_MAPPING.md`'s old
4-column `|`-table form no longer exists at all -- this file checks the
new form ONLY, per design section 5's "新しい登録テストは新形だけを検査
する"). The current/history split contract itself (every SI id's
`[history](CONTROL_MAPPING_HISTORY.md#...)` link resolving to a real,
non-empty `CONTROL_MAPPING_HISTORY.md` heading, with the two files' ID sets
in exact 1:1 correspondence) is unchanged from the table-form predecessor;
only how a row's own content is laid out inside the file changed.

`CONTROL_MAPPING.md` carries no `@pytest.mark.condition(...)` of its own --
these tests check the DOCUMENT's shape, not a behavioral condition.

New-form shape (design section 2), enumerated by design section 5's own
table:
    ## SI-NN <name>

    [history](CONTROL_MAPPING_HISTORY.md#si-nn)

    ### r2db-api

    #### Control

    - <claim>
    - <claim>

    #### Evidence

    - <claim>

    #### Status

    - —

    ### MitateDB-api
    (same form)

    ### Common
    (same form)

one `## SI-NN` section per Security Invariant, SI-00..SI-15 in ascending
order, followed by `## CCR-14 ...` and `## Rule` (no other `## ` headings
anywhere in the file); each SI section holds exactly the 3 `### ` peer
subsections in that order, each holding exactly the 3 `#### ` axis
sub-subsections in that order; every axis holds one or more `- ` bullet
lines, EXCEPT that `- —` may appear only as an axis's sole line (marking
"no claim for this axis"). No other non-blank line may appear inside an SI
section (design section 5's own "散文行や継続行が cap と主張集合を抜け
ないように") -- a stray prose/continuation line would silently escape both
the block-length cap and the claim-multiset check
`tools/check_control_mapping_restructure.py` performs, so this file itself
also fixes the SHAPE those two properties depend on.
"""
from __future__ import annotations

import re
from pathlib import Path

CONTROL_MAPPING_PATH = Path(__file__).parent.parent / "security" / "CONTROL_MAPPING.md"
CONTROL_MAPPING_HISTORY_PATH = Path(__file__).parent.parent / "security" / "CONTROL_MAPPING_HISTORY.md"
SECURITY_INVARIANTS_PATH = Path(__file__).parent.parent / "security" / "SECURITY_INVARIANTS_V1.md"

# Design section 5, "肥大化の抑止": a block is one (SI, subsection)'s
# claims (across all 3 axes) joined by a single space each; content is
# unchanged by the restructure, so this ratchet carries the OLD table
# form's own MAX_CELL_LENGTH value forward unchanged, verbatim record of
# this file's own predecessor comment (差し戻し rework round 3, 監督裁定
# 2026-09-06, item C-1/B-2) kept below rather than paraphrased:
#
# Measured 2026-09-06 (after restoring the dropped SI-14 r2db-api items
# A-3/A-4 -- the exclusion-list rationale/asymmetry note and the
# process-local deployment-ceiling note -- that this same rework round put
# back onto the current row): this file's own longest cell is SI-14's
# r2db-api control/evidence cell at 15,065 characters. MAX_CELL_LENGTH =
# 15,200 is that measurement plus a 135-character margin.
#
# Re-measured 2026-09-14 (WP-2, after the restructure): SI-14's r2db-api
# block is now 15,122 characters (`tools/check_control_mapping_restructure.py`
# against the restructured file, and CONTROL_MAPPING.md's own preamble
# "Length cap measurement" paragraph). MAX_BLOCK_LENGTH is carried forward
# unchanged at 15200 -- 78 left against 15,122, not the same 135-char
# margin the 2026-09-06 measurement had (content is unchanged by the
# restructure; the margin shrank because the block itself grew from
# 15,065 to 15,122 characters between those two measurements, both prior
# to this restructure's own WP-2 pass).
MAX_BLOCK_LENGTH = 15200

# Secondary cap (design section 5's own "補助"): no single physical line
# may exceed this length. Computed by
# tools/restructure_control_mapping.py as the restructured file's own
# longest physical line rounded up to the next 100 -- 1,400 (the longest
# line is `- ` plus SI-08's r2db-api longest claim, 1,382 characters,
# measured 2026-09-14) -- and recorded verbatim in CONTROL_MAPPING.md's own
# preamble as `` `MAX_LINE_LENGTH = 1400` ``. Kept in sync with that value,
# not derived from it at test time, so a generator regression that changes
# the preamble's own declared number without regenerating a consistent
# file is still caught (this constant and the preamble's own text must
# both be updated together, by hand, whenever the file is regenerated).
MAX_LINE_LENGTH = 1400

_SI_SECTION_RE = re.compile(r"^## (SI-\d+)\s+(.+?)\s*$", re.MULTILINE)
_ANY_H2_RE = re.compile(r"^## (.+?)\s*$", re.MULTILINE)
_PEER_H3_RE = re.compile(r"^### (.+?)\s*$", re.MULTILINE)
_AXIS_H4_RE = re.compile(r"^#### (.+?)\s*$", re.MULTILINE)
_BULLET_RE = re.compile(r"^- (.*)$")
_HISTORY_LINK_RE = re.compile(r"\[history\]\(CONTROL_MAPPING_HISTORY\.md#([a-z0-9\-]+)\)")
_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_SI_INVARIANT_HEADING_RE = re.compile(r"^### (SI-\d+)\b", re.MULTILINE)

EXPECTED_PEER_ORDER = ("r2db-api", "MitateDB-api", "Common")
EXPECTED_AXIS_ORDER = ("Control", "Evidence", "Status")


def _github_slug(text: str) -> str:
    """Same approximation of GitHub's heading-anchor slug algorithm as
    `test_conditions_register.py::_github_slug` -- lowercase, drop
    anything that is not a word character/space/hyphen, spaces to
    hyphens. Duplicated rather than imported: each register test is meant
    to stand alone."""
    text = text.strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    text = re.sub(r"\s+", "-", text)
    return text


class ParsedSection:
    def __init__(self, sid: str, name: str, body: str):
        self.sid = sid
        self.name = name
        self.body = body


def _read() -> str:
    return CONTROL_MAPPING_PATH.read_text()


def _split_sections(text: str) -> tuple[list[ParsedSection], str]:
    """Returns (SI sections, tail_after_last_SI_section) -- the tail holds
    `## CCR-14 ...` and `## Rule` plus anything else, unparsed, for the
    section-order check to inspect on its own. An SI section's own body
    ends at the next '## ' heading of ANY kind (not only the next SI
    section) -- the last SI section's body must stop at the first non-SI
    heading (CCR-14), never run to end-of-file, or a stray non-'- ' line
    inside CCR-14/Rule would be silently swallowed into that SI section's
    own last axis instead of being caught (or not) as what it is."""
    all_h2 = list(_ANY_H2_RE.finditer(text))
    matches = list(_SI_SECTION_RE.finditer(text))
    all_h2_starts = [m.start() for m in all_h2]
    sections = []
    for m in matches:
        start = m.end()
        later_starts = [s for s in all_h2_starts if s > m.start()]
        end = min(later_starts) if later_starts else len(text)
        sections.append(ParsedSection(m.group(1), m.group(2), text[start:end]))
    # tail is everything from the first non-SI '## ' heading onward (CCR-14, Rule)
    tail = ""
    for m in all_h2:
        if not re.match(r"^SI-\d+\b", m.group(1)):
            tail = text[m.start() :]
            break
    return sections, tail


def _no_pipe_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip().startswith("|")]


def test_control_mapping_md_has_no_pipe_table_lines():
    """Design section 5: the new form has no `|`-started table anywhere."""
    text = _read()
    offenders = _no_pipe_lines(text)
    assert not offenders, f"{CONTROL_MAPPING_PATH} has '|'-started line(s), old table form not fully removed: {offenders[:5]}"


def test_control_mapping_md_section_order_is_si_ascending_then_ccr14_then_rule():
    text = _read()
    all_h2 = [m.group(1).strip() for m in _ANY_H2_RE.finditer(text)]
    si_headings = [h for h in all_h2 if re.match(r"^SI-\d+\b", h)]
    non_si_headings = [h for h in all_h2 if not re.match(r"^SI-\d+\b", h)]

    si_ids = [re.match(r"^(SI-\d+)", h).group(1) for h in si_headings]
    expected_order = sorted(si_ids, key=lambda s: int(s.split("-")[1]))
    assert si_ids == expected_order, f"SI sections are not in ascending order: {si_ids}"

    assert len(non_si_headings) == 2, (
        f"expected exactly 2 non-SI '## ' headings (CCR-14, Rule), found {len(non_si_headings)}: {non_si_headings}"
    )
    assert non_si_headings[0].startswith("CCR-14"), f"first non-SI heading is not CCR-14: {non_si_headings[0]!r}"
    assert non_si_headings[1] == "Rule", f"second non-SI heading is not 'Rule': {non_si_headings[1]!r}"

    # the non-SI headings must come after every SI heading
    all_positions = [(m.start(), m.group(1).strip()) for m in _ANY_H2_RE.finditer(text)]
    last_si_pos = max(pos for pos, h in all_positions if re.match(r"^SI-\d+\b", h))
    ccr_pos = min(pos for pos, h in all_positions if h.startswith("CCR-14"))
    assert ccr_pos > last_si_pos, "CCR-14 section is not positioned after all SI sections"


def test_control_mapping_md_has_no_duplicate_si_ids():
    text = _read()
    ids = [m.group(1) for m in _SI_SECTION_RE.finditer(text)]
    duplicates = sorted({sid for sid in ids if ids.count(sid) > 1})
    assert not duplicates, f"duplicate SI section id(s) in {CONTROL_MAPPING_PATH}: {duplicates}"


def test_control_mapping_md_si_ids_match_security_invariants_1to1():
    """Design section 5: SI ids must be a 1:1 set match against
    `security/SECURITY_INVARIANTS_V1.md`'s own `### SI-NN` headings. Names
    are NOT compared (SI-03/SI-04 differ in wording between the two
    documents by design)."""
    text = _read()
    mapping_ids = {m.group(1) for m in _SI_SECTION_RE.finditer(text)}
    invariants_text = SECURITY_INVARIANTS_PATH.read_text()
    invariants_ids = {m.group(1) for m in _SI_INVARIANT_HEADING_RE.finditer(invariants_text)}
    missing = sorted(invariants_ids - mapping_ids)
    extra = sorted(mapping_ids - invariants_ids)
    assert not missing and not extra, (
        f"SI id mismatch between {CONTROL_MAPPING_PATH} and {SECURITY_INVARIANTS_PATH}: "
        f"missing_from_control_mapping={missing} extra_in_control_mapping={extra}"
    )


def test_control_mapping_md_every_section_has_the_fixed_peer_and_axis_shape():
    """Design section 5's own "形" property, checked in full: each SI
    section has EXACTLY the 3 `### <peer>` subsections in the fixed order,
    each with EXACTLY the 3 `#### <axis>` sub-subsections in the fixed
    order, each with at least one `- ` bullet line; `- —` is allowed only
    as an axis's sole line. Every non-blank line inside an SI section must
    be one of: the history link line, a fixed `### `/`#### ` heading, or a
    `- ` bullet -- no prose or continuation line may slip through."""
    text = _read()
    sections, _tail = _split_sections(text)
    assert sections, f"no '## SI-NN' sections found in {CONTROL_MAPPING_PATH}"

    for section in sections:
        body = section.body
        peer_matches = list(_PEER_H3_RE.finditer(body))
        peer_names = [m.group(1).strip() for m in peer_matches]
        assert peer_names == list(EXPECTED_PEER_ORDER), (
            f"{section.sid}: '### ' subsections are {peer_names}, expected {list(EXPECTED_PEER_ORDER)}"
        )

        # everything before the first '### ' heading: blank lines and
        # exactly one history-link line
        preface = body[: peer_matches[0].start()] if peer_matches else body
        preface_lines = [l for l in preface.splitlines() if l.strip()]
        assert len(preface_lines) == 1 and _HISTORY_LINK_RE.search(preface_lines[0]), (
            f"{section.sid}: expected exactly one non-blank line before '### r2db-api' "
            f"(the history link), found: {preface_lines}"
        )

        for i, pm in enumerate(peer_matches):
            peer = peer_names[i]
            pstart = pm.end()
            pend = peer_matches[i + 1].start() if i + 1 < len(peer_matches) else len(body)
            peer_body = body[pstart:pend]

            axis_matches = list(_AXIS_H4_RE.finditer(peer_body))
            axis_names = [m.group(1).strip() for m in axis_matches]
            assert axis_names == list(EXPECTED_AXIS_ORDER), (
                f"{section.sid}/{peer}: '#### ' sub-subsections are {axis_names}, expected {list(EXPECTED_AXIS_ORDER)}"
            )

            # nothing but blank lines may precede the first '#### ' heading
            axis_preface = peer_body[: axis_matches[0].start()] if axis_matches else peer_body
            assert not axis_preface.strip(), (
                f"{section.sid}/{peer}: stray non-blank content before the first '#### ' heading: {axis_preface!r}"
            )

            for j, am in enumerate(axis_matches):
                axis = axis_names[j]
                astart = am.end()
                aend = axis_matches[j + 1].start() if j + 1 < len(axis_matches) else len(peer_body)
                axis_body = peer_body[astart:aend]
                # NOT `l.strip()` here: a nested bullet ("  - foo", review
                # item 7) must be rejected, and stripping leading
                # whitespace before matching would silently accept it as
                # an ordinary top-level "- " line. Only lines that are
                # blank once trailing whitespace is removed are dropped;
                # every remaining line is checked in its RAW (unindented)
                # form.
                nonblank = [l for l in axis_body.splitlines() if l.strip()]
                assert nonblank, f"{section.sid}/{peer}/{axis}: no content lines at all"
                bad_lines = [l for l in nonblank if not _BULLET_RE.match(l)]
                assert not bad_lines, (
                    f"{section.sid}/{peer}/{axis}: non-'- ' line(s) found (prose/continuation/nested-bullet leak): {bad_lines}"
                )
                if nonblank == ["- —"]:
                    continue
                assert "- —" not in nonblank, (
                    f"{section.sid}/{peer}/{axis}: '- —' placeholder mixed with real claim bullets: {nonblank}"
                )


def _iter_bullets(body: str, peer: str, axis: str) -> list[str]:
    peer_matches = list(_PEER_H3_RE.finditer(body))
    for i, pm in enumerate(peer_matches):
        if pm.group(1).strip() != peer:
            continue
        pstart = pm.end()
        pend = peer_matches[i + 1].start() if i + 1 < len(peer_matches) else len(body)
        peer_body = body[pstart:pend]
        axis_matches = list(_AXIS_H4_RE.finditer(peer_body))
        for j, am in enumerate(axis_matches):
            if am.group(1).strip() != axis:
                continue
            astart = am.end()
            aend = axis_matches[j + 1].start() if j + 1 < len(axis_matches) else len(peer_body)
            axis_body = peer_body[astart:aend]
            bullets = []
            for line in axis_body.splitlines():
                line = line.strip()
                m = _BULLET_RE.match(line)
                if m:
                    bullets.append(m.group(1))
            if bullets == ["—"]:
                return []
            return bullets
    return []


def test_control_mapping_md_blocks_do_not_exceed_the_length_cap():
    """Design section 5's own "主" cap: per (SI, subsection), all 3 axes'
    claims joined by a single space each must not exceed MAX_BLOCK_LENGTH."""
    text = _read()
    sections, _tail = _split_sections(text)
    offenders = []
    for section in sections:
        for peer in EXPECTED_PEER_ORDER:
            claims: list[str] = []
            for axis in EXPECTED_AXIS_ORDER:
                claims.extend(_iter_bullets(section.body, peer, axis))
            block = " ".join(claims)
            if len(block) > MAX_BLOCK_LENGTH:
                offenders.append((section.sid, peer, len(block)))
    assert not offenders, (
        f"block(s) in {CONTROL_MAPPING_PATH} exceed the {MAX_BLOCK_LENGTH}-character cap "
        f"(id, peer, length): {offenders}"
    )


def test_control_mapping_md_lines_do_not_exceed_the_line_length_cap():
    """Design section 5's own "補助" cap: no physical line may exceed
    MAX_LINE_LENGTH."""
    text = _read()
    offenders = [(i + 1, len(line)) for i, line in enumerate(text.splitlines()) if len(line) > MAX_LINE_LENGTH]
    assert not offenders, (
        f"line(s) in {CONTROL_MAPPING_PATH} exceed the {MAX_LINE_LENGTH}-character cap "
        f"(line number, length): {offenders[:10]}"
    )


_DECLARED_MAX_LINE_LENGTH_RE = re.compile(r"MAX_LINE_LENGTH = (\d+)")


def test_control_mapping_md_declares_the_same_max_line_length_as_this_file():
    """Code review item (e): the preamble's own P2 sentence
    ('` `` `MAX_LINE_LENGTH = <N>` `` `') is generated content, not derived
    from this test's own MAX_LINE_LENGTH constant at test time (module
    docstring: "Kept in sync with that value, not derived from it"). A
    regenerate that changes the file's own longest line without this
    constant being updated to match must be caught here, not silently
    accepted because both numbers happen to independently satisfy the cap
    check above."""
    text = _read()
    m = _DECLARED_MAX_LINE_LENGTH_RE.search(text)
    assert m, f"{CONTROL_MAPPING_PATH}'s preamble does not declare a MAX_LINE_LENGTH value"
    declared = int(m.group(1))
    assert declared == MAX_LINE_LENGTH, (
        f"{CONTROL_MAPPING_PATH} declares MAX_LINE_LENGTH = {declared} but this test's own "
        f"constant is {MAX_LINE_LENGTH} -- update MAX_LINE_LENGTH above to match a regeneration"
    )


def test_every_control_mapping_section_has_a_resolving_history_link():
    text = _read()
    sections, _tail = _split_sections(text)
    companion_slugs = _companion_heading_slugs(CONTROL_MAPPING_HISTORY_PATH)
    missing_link: list[str] = []
    duplicate_link: list[str] = []
    unresolved: list[tuple[str, str]] = []
    for section in sections:
        matches = _HISTORY_LINK_RE.findall(section.body)
        if not matches:
            missing_link.append(section.sid)
            continue
        if len(matches) > 1:
            duplicate_link.append(section.sid)
            continue
        if matches[0] not in companion_slugs:
            unresolved.append((section.sid, matches[0]))
    assert not missing_link, f"section(s) in {CONTROL_MAPPING_PATH} have no [history](...) link: {missing_link}"
    assert not duplicate_link, f"section(s) in {CONTROL_MAPPING_PATH} have more than one [history](...) link: {duplicate_link}"
    assert not unresolved, (
        f"section(s) in {CONTROL_MAPPING_PATH} whose history link fragment does not resolve to a heading "
        f"in {CONTROL_MAPPING_HISTORY_PATH} (id, fragment): {unresolved}"
    )


def _companion_heading_slugs(path: Path) -> set[str]:
    text = path.read_text()
    return {_github_slug(m.group(1)) for m in _HEADING_RE.finditer(text)}


def _companion_sections(path: Path) -> dict[str, str]:
    """{heading_slug: section_body} for every '## <heading>' section in a
    companion file -- mirrors `test_conditions_register.py::
    _companion_sections` (duplicated, not imported)."""
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


def test_control_mapping_history_has_exactly_the_main_sections_ids():
    text = _read()
    sections, _tail = _split_sections(text)
    main_slugs = {_github_slug(section.sid) for section in sections}
    companion_slugs = _companion_heading_slugs(CONTROL_MAPPING_HISTORY_PATH)
    missing = sorted(main_slugs - companion_slugs)
    extra = sorted(companion_slugs - main_slugs)
    assert not missing and not extra, (
        f"mismatch between {CONTROL_MAPPING_PATH} IDs and {CONTROL_MAPPING_HISTORY_PATH} headings: "
        f"missing_from_companion={missing} extra_in_companion={extra}"
    )


def test_control_mapping_history_every_heading_section_is_non_empty():
    sections = _companion_sections(CONTROL_MAPPING_HISTORY_PATH)
    empty = sorted(slug for slug, body in sections.items() if not body)
    assert not empty, (
        f"{CONTROL_MAPPING_HISTORY_PATH} has heading(s) with an empty section body: {empty}"
    )
