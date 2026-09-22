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

R-50 (docs/design/CONTROL_MAPPING_MULTI_BLOCK_V0_1.md v0.4, section 5): a
`### <peer>` subsection may itself hold one or more `### <peer> -- <topic>`
sub-blocks, each with its own full Control/Evidence/Status triple. Every
peer carries a mandatory, unnamed default sub-block (`### <peer>`, no ` --
`) first, followed by up to `MAX_NAMED_SUBBLOCKS` named sub-blocks in file
order; the length cap (below) applies per sub-block, not per peer.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

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
# The longest block moves as content changes, so its current length is
# not recorded here -- measure it by running this file's own
# `_split_sections` against the current `security/CONTROL_MAPPING.md`,
# then `_iter_section_subblocks` on each returned section, then
# `_subblock_block_text` on each of those sub-blocks, and taking the
# longest result (the same measurement CONTROL_MAPPING.md's own
# preamble "Length cap measurement" paragraph records for that file).
# MAX_BLOCK_LENGTH is the 2026-09-06 measurement above plus its
# margin; it does not track the longest block's current length.
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

# R-50 (design docs/design/CONTROL_MAPPING_MULTI_BLOCK_V0_1.md v0.4,
# section 4, Q-1, 監督裁定 2026-09-18): each (SI, peer) may hold at most
# this many NAMED sub-blocks in addition to its mandatory default one
# (ceiling = 4 * MAX_BLOCK_LENGTH per (SI, peer)). Raising this value
# requires a supervisor ruling recorded here, the same as MAX_BLOCK_LENGTH
# above -- it is not a value a generator/editor may bump on its own.
MAX_NAMED_SUBBLOCKS = 3

# Required test (a) (design section 10 / work order
# docs/work-orders/WORK_ORDER_R50_CONTROL_MAPPING_MULTI_BLOCK_V1.md W1-10),
# per 訂正註 1 S-1 (2026-09-18 監督裁定): no per-file absolute pin on the
# dash/bullet/em-dash totals -- a change that adds a claim, or WP-2's own
# two new `- —` placeholders, would move all three numbers and force this
# file to be touched by every unrelated registry edit. The dropped-bullet
# property is instead held by a per-section identity (raw == collected +
# em, asserted below) plus two anchors that only guard against a silently
# vacuous check: the SI section count (16, SI-00..SI-15) and a non-zero
# collected-bullet total.
EXPECTED_SI_SECTION_COUNT = 16

_SI_SECTION_RE = re.compile(r"^## (SI-\d+)\s+(.+?)\s*$", re.MULTILINE)
_ANY_H2_RE = re.compile(r"^## (.+?)\s*$", re.MULTILINE)
_PEER_H3_RE = re.compile(r"^### (.*)$", re.MULTILINE)
_AXIS_H4_RE = re.compile(r"^#### (.+?)\s*$", re.MULTILINE)
_BULLET_RE = re.compile(r"^- (.*)$")
_HISTORY_LINK_RE = re.compile(r"\[history\]\(CONTROL_MAPPING_HISTORY\.md#([a-z0-9\-]+)\)")
_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_SI_INVARIANT_HEADING_RE = re.compile(r"^### (SI-\d+)\b", re.MULTILINE)

EXPECTED_PEER_ORDER = ("r2db-api", "MitateDB-api", "Common")
EXPECTED_AXIS_ORDER = ("Control", "Evidence", "Status")

# R-50 design section 5's 2-stage sub-block heading allowlist. Stage 1:
# the peer name is one of the 3 known peers, and -- if a topic is present
# -- it is introduced by the literal separator ` -- ` and starts/ends on a
# non-space character (a trailing-whitespace heading fails stage 1
# outright: `\S` cannot match the space just before end-of-line). Stage 2
# (applied separately, below) further restricts what a captured topic may
# contain; an allowlist, not an exclusion filter -- a `### ` line that
# fails EITHER stage is a violation, never silently skipped.
_SUBBLOCK_HEADING_RE = re.compile(r"^### (r2db-api|MitateDB-api|Common)(?: -- (\S(?:.*\S)?))?$")
# Stage 2: a topic is ASCII visible characters (0x21-0x7E) grouped into
# words joined by exactly one regular space each -- this alone would still
# accept a topic containing a second literal ` -- ` (each `-` is itself in
# 0x21-0x7E, so "a -- b" tokenizes as 3 valid words); the explicit
# substring check below closes that gap.
_SUBJECT_TOKEN_RE = re.compile(r"^[\x21-\x7E]+(?: [\x21-\x7E]+)*$")


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


# ---------------------------------------------------------------------------
# R-50: sub-block parsing and shape analysis (design section 5), as pure
# functions of `text` -- called by both the on-the-real-file tests below
# and the synthetic-fixture parametrized tests further down (work order
# W1-1: "検査の本体は `text` を引数に取る純関数へ切り出し … 同じ純関数を
# 呼ぶ").
# ---------------------------------------------------------------------------


class SubBlock:
    def __init__(self, peer: str, subject: str | None, body: str, heading_line: str):
        self.peer = peer
        self.subject = subject  # None marks the mandatory default sub-block
        self.body = body  # text between this '### ' heading and the next one (or end)
        self.heading_line = heading_line
        self.sid: str | None = None  # filled in by callers that know it, for messages only


def _parse_subblock_heading(line: str) -> tuple[str, str | None] | None:
    """Design section 5's 2-stage allowlist, applied to one raw '### '
    line (no leading/trailing normalization: a caller must pass the exact
    line text). Returns (peer, subject_or_None) if well-formed, else None."""
    m = _SUBBLOCK_HEADING_RE.match(line)
    if not m:
        return None
    peer, subject = m.group(1), m.group(2)
    if subject is not None:
        if " -- " in subject:
            return None
        if not _SUBJECT_TOKEN_RE.match(subject):
            return None
    return peer, subject


def _parse_body_subblocks(body: str) -> tuple[list[SubBlock], list[str]]:
    """Splits one SI section's body into its `### ` sub-blocks. Every raw
    `### ` line is checked against the section-5 allowlist and, if it
    fails, is recorded in the returned `bad_headings` list -- never
    silently skipped (an exclusion filter would let an unrecognized
    `### ` line escape every shape/cap check that follows)."""
    h3_matches = list(_PEER_H3_RE.finditer(body))
    subblocks: list[SubBlock] = []
    bad_headings: list[str] = []
    for i, m in enumerate(h3_matches):
        raw_line = m.group(0)
        start = m.end()
        end = h3_matches[i + 1].start() if i + 1 < len(h3_matches) else len(body)
        parsed = _parse_subblock_heading(raw_line)
        if parsed is None:
            bad_headings.append(raw_line)
            continue
        peer, subject = parsed
        subblocks.append(SubBlock(peer, subject, body[start:end], raw_line))
    return subblocks, bad_headings


def _iter_section_subblocks(section: ParsedSection) -> tuple[list[SubBlock], list[str]]:
    subblocks, bad_headings = _parse_body_subblocks(section.body)
    for sb in subblocks:
        sb.sid = section.sid
    return subblocks, bad_headings


def _subblock_axis_bullets(sb: SubBlock) -> dict[str, list[str]]:
    axis_matches = list(_AXIS_H4_RE.finditer(sb.body))
    result: dict[str, list[str]] = {}
    for j, am in enumerate(axis_matches):
        axis = am.group(1).strip()
        astart = am.end()
        aend = axis_matches[j + 1].start() if j + 1 < len(axis_matches) else len(sb.body)
        axis_body = sb.body[astart:aend]
        bullets = []
        for line in axis_body.splitlines():
            line = line.strip()
            m = _BULLET_RE.match(line)
            if m:
                bullets.append(m.group(1))
        result[axis] = bullets
    return result


def _subblock_block_text(sb: SubBlock) -> str:
    """Design section 5's "主" cap join, at sub-block granularity: the 3
    axes' claims, joined by a single space each; `- —` (no claim for that
    axis) contributes nothing."""
    axis_bullets = _subblock_axis_bullets(sb)
    claims: list[str] = []
    for axis in EXPECTED_AXIS_ORDER:
        bullets = axis_bullets.get(axis, [])
        if bullets == ["—"]:
            continue
        claims.extend(bullets)
    return " ".join(claims)


def _check_subblock_axes(sid: str, sb: SubBlock) -> list[str]:
    """Design section 5's condition (iii), at sub-block granularity: each
    sub-block holds exactly `#### Control` / `#### Evidence` / `#### Status`
    in that order, nothing but blank lines before the first one, every
    content line is a `- ` bullet, and `- —` may appear only as an axis's
    sole line."""
    violations: list[str] = []
    label = f"{sid}/{sb.peer}/{sb.subject!r}"
    axis_matches = list(_AXIS_H4_RE.finditer(sb.body))
    axis_names = [m.group(1).strip() for m in axis_matches]
    if axis_names != list(EXPECTED_AXIS_ORDER):
        violations.append(f"{label}: axes are {axis_names}, expected {list(EXPECTED_AXIS_ORDER)}")
        return violations

    axis_preface = sb.body[: axis_matches[0].start()]
    if axis_preface.strip():
        violations.append(f"{label}: stray content before first '#### ' heading: {axis_preface!r}")

    for j, am in enumerate(axis_matches):
        axis = axis_names[j]
        astart = am.end()
        aend = axis_matches[j + 1].start() if j + 1 < len(axis_matches) else len(sb.body)
        axis_body = sb.body[astart:aend]
        nonblank = [l for l in axis_body.splitlines() if l.strip()]
        if not nonblank:
            violations.append(f"{label}/{axis}: no content lines at all")
            continue
        bad_lines = [l for l in nonblank if not _BULLET_RE.match(l)]
        if bad_lines:
            violations.append(f"{label}/{axis}: non-'- ' line(s) found: {bad_lines}")
        if nonblank == ["- —"]:
            continue
        if "- —" in nonblank:
            violations.append(f"{label}/{axis}: '- —' placeholder mixed with real claim bullets: {nonblank}")
    return violations


def _run_length_peers(peer_sequence: list[str]) -> list[str]:
    """Collapses consecutive repeats -- design section 5's "同じ peer の
    小ブロックは連続して並べ" (grouping) check: comparing this against
    `EXPECTED_PEER_ORDER` catches BOTH a peer appearing out of order and a
    peer's sub-blocks being split into two non-adjacent runs (the peer
    would then appear twice in this list, never equal to the 3-tuple)."""
    groups: list[str] = []
    for p in peer_sequence:
        if not groups or groups[-1] != p:
            groups.append(p)
    return groups


class ShapeAnalysis:
    def __init__(self):
        self.section_preface: list[str] = []
        self.bad_headings: list[str] = []
        self.missing_default: list[tuple[str, str]] = []
        self.multiple_default: list[tuple[str, str]] = []
        self.default_not_first: list[tuple[str, str]] = []
        self.duplicate_subjects: list[tuple[str, str, str]] = []
        self.too_many_named: list[tuple[str, str, int]] = []
        self.peer_order: list[str] = []
        self.axis_shape: list[str] = []
        self.block_length: list[tuple[str, str, str | None, int]] = []


def _analyze_shape(text: str) -> ShapeAnalysis:
    """R-50 design sections 4/5, single pure entry point: both the
    on-the-real-file tests and the synthetic-fixture parametrized tests
    below call this same function (work order W1-1)."""
    sections, _tail = _split_sections(text)
    report = ShapeAnalysis()
    for section in sections:
        h3_matches = list(_PEER_H3_RE.finditer(section.body))
        if h3_matches:
            preface = section.body[: h3_matches[0].start()]
            preface_lines = [l for l in preface.splitlines() if l.strip()]
            if not (len(preface_lines) == 1 and _HISTORY_LINK_RE.search(preface_lines[0])):
                report.section_preface.append(section.sid)
        else:
            report.section_preface.append(section.sid)

        subblocks, bad_headings = _iter_section_subblocks(section)
        report.bad_headings.extend(bad_headings)

        peer_sequence = [sb.peer for sb in subblocks]
        if _run_length_peers(peer_sequence) != list(EXPECTED_PEER_ORDER):
            report.peer_order.append(section.sid)

        for peer in EXPECTED_PEER_ORDER:
            peer_subblocks = [sb for sb in subblocks if sb.peer == peer]
            defaults = [sb for sb in peer_subblocks if sb.subject is None]
            named = [sb for sb in peer_subblocks if sb.subject is not None]
            if not defaults:
                report.missing_default.append((section.sid, peer))
            if len(defaults) > 1:
                report.multiple_default.append((section.sid, peer))
            if peer_subblocks and peer_subblocks[0].subject is not None:
                report.default_not_first.append((section.sid, peer))
            if len(named) > MAX_NAMED_SUBBLOCKS:
                report.too_many_named.append((section.sid, peer, len(named)))
            seen: dict[str, int] = {}
            for sb in named:
                seen[sb.subject] = seen.get(sb.subject, 0) + 1
            for subject, count in seen.items():
                if count > 1:
                    report.duplicate_subjects.append((section.sid, peer, subject))

        for sb in subblocks:
            report.axis_shape.extend(_check_subblock_axes(section.sid, sb))
            block_text = _subblock_block_text(sb)
            if len(block_text) > MAX_BLOCK_LENGTH:
                report.block_length.append((sb.sid, sb.peer, sb.subject, len(block_text)))
    return report


def _iter_bullets(body: str, peer: str, axis: str) -> list[str]:
    """(peer, axis) -> claim bullet texts, across EVERY one of that peer's
    sub-blocks within `body` (the mandatory default one, plus every named
    one) -- design section 9's pitfall: an implementation that returns at
    the FIRST matching sub-block silently drops every later, named
    sub-block's bullets. Used by the required test (a) accounting below;
    the length-cap check walks sub-blocks directly instead (a cap applies
    to one sub-block at a time, not to a peer's bullets pooled together)."""
    bullets: list[str] = []
    subblocks, _bad = _parse_body_subblocks(body)
    for sb in subblocks:
        if sb.peer != peer:
            continue
        axis_bullets = _subblock_axis_bullets(sb).get(axis, [])
        if axis_bullets == ["—"]:
            continue
        bullets.extend(axis_bullets)
    return bullets


def _count_raw_dash_lines(section_body: str) -> int:
    return len(re.findall(r"^- ", section_body, re.MULTILINE))


def _count_em_dash_lines(section_body: str) -> int:
    return len(re.findall(r"^- —$", section_body, re.MULTILINE))


def _bullet_accounting(section: ParsedSection) -> tuple[int, int, int]:
    """Required test (a) (design section 10): (raw_dash_lines,
    collected_bullets, em_dash_lines). `raw_dash_lines` counts every '- '
    line in the section body directly from the text, independent of any
    sub-block walking; a mismatch against `collected_bullets +
    em_dash_lines` means `_iter_bullets` silently dropped bullets."""
    raw = _count_raw_dash_lines(section.body)
    em = _count_em_dash_lines(section.body)
    collected = 0
    for peer in EXPECTED_PEER_ORDER:
        for axis in EXPECTED_AXIS_ORDER:
            collected += len(_iter_bullets(section.body, peer, axis))
    return raw, collected, em


# ---------------------------------------------------------------------------
# on-the-real-file tests (system 2 of W1-1's "両系統": current
# `security/CONTROL_MAPPING.md` carries zero named sub-blocks at WP-1
# integration time -- every check below must still be green against it,
# design section 1.3's "後方互換のためではなく…既定の小ブロックだけの形
# が§5の規則の部分集合であるため")
# ---------------------------------------------------------------------------


def test_control_mapping_md_every_section_has_the_history_link_preface_only():
    text = _read()
    report = _analyze_shape(text)
    assert report.section_preface == [], (
        f"section(s) with other than exactly one history-link preface line: {report.section_preface}"
    )


def test_control_mapping_md_subblock_headings_use_the_allowlisted_form():
    """W1-2 / W1-3: every `### ` line inside an SI section must satisfy
    both stages of design section 5's allowlist."""
    text = _read()
    report = _analyze_shape(text)
    assert report.bad_headings == [], f"'### ' heading(s) failing the section-5 allowlist: {report.bad_headings}"


def test_control_mapping_md_default_subblock_is_required_exactly_once_and_first():
    """W1-4 (i)(ii)(iii)."""
    text = _read()
    report = _analyze_shape(text)
    assert report.missing_default == [], f"(SI, peer) missing a default sub-block: {report.missing_default}"
    assert report.multiple_default == [], f"(SI, peer) with more than one default sub-block: {report.multiple_default}"
    assert report.default_not_first == [], f"(SI, peer) whose first sub-block is not the default one: {report.default_not_first}"


def test_control_mapping_md_subject_names_are_unique_per_si_peer():
    """W1-5."""
    text = _read()
    report = _analyze_shape(text)
    assert report.duplicate_subjects == [], f"duplicate sub-block subject(s): {report.duplicate_subjects}"


def test_control_mapping_md_subblocks_are_grouped_and_peer_ordered():
    """W1-6."""
    text = _read()
    report = _analyze_shape(text)
    assert report.peer_order == [], f"SI section(s) with out-of-order/interleaved sub-blocks: {report.peer_order}"


def test_control_mapping_md_every_subblock_has_the_fixed_axis_shape():
    """W1-7, at sub-block granularity."""
    text = _read()
    report = _analyze_shape(text)
    assert report.axis_shape == [], f"sub-block(s) with malformed axis shape: {report.axis_shape}"


def test_control_mapping_md_named_subblocks_do_not_exceed_max_named_subblocks():
    """W1-9 (R-c)."""
    text = _read()
    report = _analyze_shape(text)
    assert report.too_many_named == [], f"(SI, peer) with more than {MAX_NAMED_SUBBLOCKS} named sub-block(s): {report.too_many_named}"


def test_control_mapping_md_blocks_do_not_exceed_the_length_cap():
    """W1-8 (R-a): the cap applies per (SI, peer, sub-block)."""
    text = _read()
    report = _analyze_shape(text)
    assert report.block_length == [], (
        f"sub-block(s) in {CONTROL_MAPPING_PATH} exceed the {MAX_BLOCK_LENGTH}-character cap "
        f"(sid, peer, subject, length): {report.block_length}"
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


def test_control_mapping_md_every_dash_line_is_a_bullet_or_an_em_dash_placeholder():
    """Required test (a) (design section 10, work order W1-10), on the
    real file: no `- ` line is silently dropped by the sub-block walk.
    Per 訂正註 1 S-1, the per-section identity below carries the property
    (no absolute total pin); `EXPECTED_SI_SECTION_COUNT` and the non-zero
    check only guard against a vacuously-empty pass."""
    text = _read()
    sections, _tail = _split_sections(text)
    assert len(sections) == EXPECTED_SI_SECTION_COUNT, (
        f"expected {EXPECTED_SI_SECTION_COUNT} '## SI-NN' sections, found {len(sections)}"
    )
    per_section_mismatches = []
    total_raw = total_collected = total_em = 0
    for section in sections:
        raw, collected, em = _bullet_accounting(section)
        total_raw += raw
        total_collected += collected
        total_em += em
        if raw != collected + em:
            per_section_mismatches.append((section.sid, raw, collected, em))
    assert not per_section_mismatches, (
        f"section(s) where raw '- ' line count != collected bullets + '- —' lines "
        f"(sid, raw, collected, em_dash): {per_section_mismatches}"
    )
    assert total_collected > 0, "collected bullets total is 0 -- the sub-block walk observed nothing"


# ---------------------------------------------------------------------------
# synthetic-fixture parametrized tests (system 1 of W1-1's "両系統") --
# self-contained minimal "## SI-NN" text fragments, never touching
# `security/CONTROL_MAPPING.md`. Each fixture is deliberately minimal: it
# supplies only the sub-block(s) needed to exercise the ONE condition its
# test checks and ignores unrelated fields on the returned ShapeAnalysis.
# ---------------------------------------------------------------------------


def _axis_lines(bullets: tuple[str, ...]) -> str:
    lines = bullets if bullets else ("—",)
    return "\n".join(f"- {b}" for b in lines)


def _subblock(heading: str, control=("control claim",), evidence=("evidence claim",), status=("—",)) -> str:
    return (
        f"{heading}\n\n"
        f"#### Control\n\n{_axis_lines(control)}\n\n"
        f"#### Evidence\n\n{_axis_lines(evidence)}\n\n"
        f"#### Status\n\n{_axis_lines(status)}\n\n"
    )


def _section(body: str, sid: str = "SI-01", name: str = "Example Invariant") -> str:
    return f"## {sid} {name}\n\n[history](CONTROL_MAPPING_HISTORY.md#{sid.lower()})\n\n{body}"


VALID_SECTION_TEXT = _section(
    _subblock("### r2db-api", control=("r2 claim",), evidence=("r2 evidence",))
    + _subblock("### MitateDB-api", control=("mitate claim",), evidence=("mitate evidence",))
    + _subblock("### Common", control=("common claim",), evidence=("common evidence",))
)


def test_fixture_baseline_default_only_section_has_no_violations():
    """Sanity check for the fixtures below, and design section 1.3's own
    requirement: a document with zero named sub-blocks (today's real
    file's own shape) must be fully compliant."""
    report = _analyze_shape(VALID_SECTION_TEXT)
    assert report.bad_headings == report.missing_default == report.multiple_default == []
    assert report.default_not_first == report.duplicate_subjects == report.too_many_named == []
    assert report.peer_order == report.axis_shape == report.block_length == report.section_preface == []


def test_fixture_unknown_subblock_heading_is_rejected_not_skipped():
    """W1-2."""
    text = _section(_subblock("### r2db-api") + "### Unknown\n\n")
    report = _analyze_shape(text)
    assert report.bad_headings == ["### Unknown"], report.bad_headings


@pytest.mark.parametrize(
    "topic",
    [
        pytest.param("ops   ", id="trailing_space"),
        pytest.param("ops　inventory", id="full_width_space"),
        pytest.param("a -- b", id="double_separator"),
    ],
)
def test_fixture_subblock_subject_with_bad_form_is_rejected(topic):
    """W1-3 (design section 5's own fixture examples: trailing whitespace,
    full-width space, a second ` -- `)."""
    text = _section(
        _subblock("### r2db-api")
        + _subblock(f"### r2db-api -- {topic}")
    )
    report = _analyze_shape(text)
    assert report.bad_headings, f"expected the malformed subject heading to be rejected: topic={topic!r}"


def test_fixture_default_subblock_missing_is_rejected():
    """W1-4 (i): a peer with only named sub-blocks, no default."""
    text = _section(_subblock("### r2db-api -- ops inventory"))
    report = _analyze_shape(text)
    assert ("SI-01", "r2db-api") in report.missing_default, report.missing_default


def test_fixture_default_subblock_duplicated_is_rejected():
    """W1-4 (ii): two unnamed sub-blocks for the same peer."""
    text = _section(_subblock("### r2db-api") + _subblock("### r2db-api"))
    report = _analyze_shape(text)
    assert ("SI-01", "r2db-api") in report.multiple_default, report.multiple_default


def test_fixture_default_subblock_not_first_is_rejected():
    """W1-4 (iii): the default sub-block exists but is not first."""
    text = _section(_subblock("### r2db-api -- ops inventory") + _subblock("### r2db-api"))
    report = _analyze_shape(text)
    assert ("SI-01", "r2db-api") in report.default_not_first, report.default_not_first


def test_fixture_duplicate_subject_within_peer_is_rejected():
    """W1-5."""
    text = _section(
        _subblock("### r2db-api")
        + _subblock("### r2db-api -- ops inventory")
        + _subblock("### r2db-api -- ops inventory")
    )
    report = _analyze_shape(text)
    assert ("SI-01", "r2db-api", "ops inventory") in report.duplicate_subjects, report.duplicate_subjects


def test_fixture_subblocks_interleaved_across_peers_is_rejected():
    """W1-6: a peer's sub-blocks split into two non-adjacent runs."""
    text = _section(
        _subblock("### r2db-api")
        + _subblock("### MitateDB-api")
        + _subblock("### r2db-api -- ops inventory")
    )
    report = _analyze_shape(text)
    assert "SI-01" in report.peer_order, report.peer_order


def test_fixture_named_subblock_missing_an_axis_is_rejected():
    """W1-7: a named sub-block with only 2 of the 3 required axes."""
    text = _section(
        _subblock("### r2db-api")
        + "### r2db-api -- ops inventory\n\n#### Control\n\n- claim\n\n#### Evidence\n\n- claim\n\n"
    )
    report = _analyze_shape(text)
    assert report.axis_shape, "expected the malformed (2-axis) named sub-block to be flagged"


def test_fixture_named_subblock_axis_with_a_prose_continuation_line_is_rejected():
    """W1-7 (差し戻し 1, item 4): a named sub-block's axis holds a real
    bullet AND a bare prose continuation line (no `- ` prefix) directly
    under it -- module docstring's own "散文行や継続行が...抜けないよう
    に": the continuation line must not silently vanish from the
    axis-shape check."""
    text = _section(
        _subblock("### r2db-api")
        + "### r2db-api -- ops inventory\n\n"
        "#### Control\n\n- claim\ncontinuation prose line\n\n"
        "#### Evidence\n\n- claim\n\n"
        "#### Status\n\n- —\n\n"
    )
    report = _analyze_shape(text)
    assert report.axis_shape, "expected a bare prose continuation line under a bullet to be flagged"


def test_fixture_named_subblock_axis_mixes_em_dash_placeholder_with_a_real_bullet_is_rejected():
    """W1-7 (差し戻し 1, item 4): a named sub-block's axis mixes `- —`
    with a real claim bullet -- `- —` may appear ONLY as an axis's sole
    line."""
    text = _section(
        _subblock("### r2db-api")
        + "### r2db-api -- ops inventory\n\n"
        "#### Control\n\n- —\n- claim\n\n"
        "#### Evidence\n\n- claim\n\n"
        "#### Status\n\n- —\n\n"
    )
    report = _analyze_shape(text)
    assert report.axis_shape, "expected '- —' mixed with a real claim bullet to be flagged"


def test_fixture_named_subblock_alone_exceeds_the_length_cap():
    """Required test (b) (W1-8): a single named sub-block whose own
    content, alone, exceeds MAX_BLOCK_LENGTH."""
    long_claim = "x" * (MAX_BLOCK_LENGTH + 100)
    text = _section(
        _subblock("### r2db-api")
        + _subblock("### r2db-api -- ops inventory", control=(long_claim,), evidence=("—",), status=("—",))
    )
    report = _analyze_shape(text)
    offenders = [o for o in report.block_length if o[1] == "r2db-api" and o[2] == "ops inventory"]
    assert offenders, report.block_length


def test_fixture_four_named_subblocks_exceeds_max_named_subblocks():
    """W1-9 (R-c): MAX_NAMED_SUBBLOCKS = 3, a 4th named sub-block is red."""
    text = _section(
        _subblock("### r2db-api")
        + _subblock("### r2db-api -- topic one")
        + _subblock("### r2db-api -- topic two")
        + _subblock("### r2db-api -- topic three")
        + _subblock("### r2db-api -- topic four")
    )
    report = _analyze_shape(text)
    assert ("SI-01", "r2db-api", 4) in report.too_many_named, report.too_many_named


def test_fixture_bullet_accounting_catches_dropped_named_subblock_bullets():
    """Required test (a), fixture side (W1-10): a peer with a default
    sub-block AND a named one, each with distinct claim text -- a
    first-match-only `_iter_bullets` would silently drop the named
    sub-block's bullets from the accounting total."""
    text = _section(
        _subblock("### r2db-api", control=("default claim",), evidence=("default evidence",))
        + _subblock("### r2db-api -- ops inventory", control=("named claim",), evidence=("named evidence",))
    )
    sections, _tail = _split_sections(text)
    assert len(sections) == 1
    raw, collected, em = _bullet_accounting(sections[0])
    assert raw >= 1, "fixture must contain at least one '- ' line to be a meaningful test"
    assert raw == collected + em, (
        f"required test (a) mismatch on a fixture WITH a named sub-block: raw={raw} collected={collected} em={em}"
    )
    assert collected == 4, f"expected all 4 real bullets (2 default + 2 named) collected, got {collected}"


# ---------------------------------------------------------------------------
# R-64 (docs/work-orders/WORK_ORDER_R64_CONTROL_MAPPING_TEST_NAME_RESOLUTION_V1.md
# section 1, D-1..D-4): every test-name reference a Control/Evidence claim
# cites must resolve to a real `def`, so a rename or removal on the test
# side cannot leave a claim pointing at nothing while this suite stays
# green (the gap R-56's mutation M11 and R-57's mutation found). Two
# reference forms:
#   (i) full form `<path>.py::<name>` (or, if `<path>` omits its
#       directory, a basename that is unique within the claiming
#       subsection's peer-scoped test directories); the file must be
#       repository-relative and real, and it must hold `def <name>`
#       (module-level, or one level under a class -- a method).
#   (ii) bare form `::<name>` / `` `<name>` `` (the whole backtick span is
#       the `test_`-prefixed identifier): `<name>` must be a `def`
#       SOMEWHERE in the claim's peer-scoped test directories. This does
#       NOT distinguish which file, and does not catch the same name
#       existing in both peers (D-1's own stated limit).
# Resolution is peer-scoped only -- the rejected alternative (tracking the
# nearest preceding path across bullets) is not implemented: 31% of bare
# `::name` references share no bullet with a preceding path, and that
# heuristic misattributes an SI-14 reference (work order section 1's own
# measurement).
# ---------------------------------------------------------------------------

import ast

REPO_ROOT = CONTROL_MAPPING_PATH.parent.parent

# D-3: the ONE file this check reads -- never a `security/*.md` glob, and
# never `CONTROL_MAPPING_HISTORY_PATH` (the verbatim archive of superseded
# claims, where a since-renamed test name is CORRECT to find, e.g. the
# `..._all_11_endpoints` bullet R-64 WP-2 moves there).
TEST_NAME_RESOLUTION_TARGET_PATH = CONTROL_MAPPING_PATH

# D-2: the 4 test directories a `def`/`async def` index is built over
# (`ast`, not pytest collection -- collection needs PostgreSQL/a DSN,
# OPERATING_CONDITIONS.md section 2 item 12). Keys match the peer-scoping
# table below.
_TEST_DIR_KEYS = ("r2db-api", "MitateDB-api", "conformance-tests", "tools/tests")
_TEST_DIRS = {
    "r2db-api": REPO_ROOT / "r2db-api" / "tests",
    "MitateDB-api": REPO_ROOT / "MitateDB-api" / "tests",
    "conformance-tests": REPO_ROOT / "conformance-tests",
    "tools/tests": REPO_ROOT / "tools" / "tests",
}

# D-1 (ii): which of the 4 directories a bare reference may resolve in,
# keyed by the CLAIMING subsection's own peer name. A `Common` subsection,
# or any claim outside every SI section, gets all 4 (`tools/tests` is
# never reachable from a named-peer subsection -- current file: 0 such
# bare references, D-1 (ii)'s own note; a claim wanting `tools/tests`
# writes the full form instead).
_PEER_SCOPED_DIR_KEYS = {
    "r2db-api": ("r2db-api", "conformance-tests"),
    "MitateDB-api": ("MitateDB-api", "conformance-tests"),
    "Common": ("r2db-api", "MitateDB-api", "conformance-tests", "tools/tests"),
}
_OUTSIDE_SI_DIR_KEYS = ("r2db-api", "MitateDB-api", "conformance-tests", "tools/tests")

_FULL_FORM_REF_RE = re.compile(r"^(\S+\.py)::([A-Za-z_]\w*)$")
_BARE_COLON_REF_RE = re.compile(r"^::(test_\w+)$")
_BARE_NAME_REF_RE = re.compile(r"^(test_\w+)$")

# D-4: floor per reference form -- measured 2026-09-21 (基点 3711a34) at
# 112 / 320 / 109; each floor below is that count minus a margin, so a
# regression in the extraction regex (or a future edit that trims claims
# well past the margin) is caught rather than a floor that only guards
# against zero (OPERATING_CONDITIONS.md section 1.5 item 32, D-4).
FULL_FORM_FLOOR = 90
BARE_COLON_FORM_FLOOR = 280
BARE_NAME_FORM_FLOOR = 90


def _iter_defs_in_file(path: Path) -> set[str]:
    """D-2: `def`/`async def` names directly under the module, or
    directly under a class body (one level of nesting, a method) -- never
    a nested function inside another function, which is not itself a
    collectible pytest item."""
    try:
        tree = ast.parse(path.read_text())
    except (SyntaxError, UnicodeDecodeError):
        return set()
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    names.add(child.name)
    return names


def _build_def_index() -> dict[str, dict[str, set[str]]]:
    """D-2: dir_key -> {repository-relative posix path: def names}, one
    entry per `*.py` file anywhere under each of the 4 test directories
    (`rglob`, 差し戻し 1 item 3, 監督裁定: a nested test file must still be
    indexed). A full-form reference to a path OUTSIDE all 4 of these
    directories stays unresolved regardless -- D-1 (i)'s own evidence is
    scoped to these 4 directories, by design, not to the whole
    repository."""
    index: dict[str, dict[str, set[str]]] = {}
    for dir_key in _TEST_DIR_KEYS:
        entries: dict[str, set[str]] = {}
        dir_path = _TEST_DIRS[dir_key]
        if dir_path.is_dir():
            for f in sorted(dir_path.rglob("*.py")):
                if "__pycache__" in f.parts:
                    continue
                rel = f.relative_to(REPO_ROOT).as_posix()
                entries[rel] = _iter_defs_in_file(f)
        index[dir_key] = entries
    return index


def _resolve_full_form(index, allowed_dir_keys, path_str: str, name: str) -> bool:
    """D-1 (i). A directory-carrying `path_str` resolves against any
    indexed directory (full form resolves "subsection を問わず"); a
    directory-OMITTED `path_str` (a bare basename) resolves only within
    `allowed_dir_keys`, and only if the basename is unique there."""
    if "/" in path_str:
        for entries in index.values():
            if path_str in entries:
                return name in entries[path_str]
        return False
    matches = [
        (rel, names)
        for dir_key in allowed_dir_keys
        for rel, names in index.get(dir_key, {}).items()
        if rel.rsplit("/", 1)[-1] == path_str
    ]
    if len(matches) != 1:
        return False
    _rel, names = matches[0]
    return name in names


def _resolve_bare_form(index, allowed_dir_keys, name: str) -> bool:
    """D-1 (ii): `name` is a `def` somewhere in the claim's peer-scoped
    directories -- which file, or a same-name collision with the OTHER
    peer, is outside what (ii) checks (D-1's own stated limit)."""
    return any(name in names for dir_key in allowed_dir_keys for names in index.get(dir_key, {}).values())


class _Claim:
    def __init__(self, sid, peer, subject, axis, line, bullet):
        self.sid = sid
        self.peer = peer
        self.subject = subject
        self.axis = axis
        self.line = line
        self.bullet = bullet


def _iter_document_claims(text: str):
    """Walks the SI/peer(/subject)/axis/bullet structure directly on
    absolute text offsets (parallel to `_analyze_shape`'s relative-offset
    walk over `ParsedSection`/`SubBlock`, which callers outside this
    section rely on staying relative-only) so each yielded `_Claim`
    carries a real line number for failure messages. Text outside every
    SI section (preamble, `## CCR-14`, `## Rule`) is walked too (D-3:
    "対象は全文"), and NOT restricted to `- ` bullet lines there -- every
    non-blank line outside an SI section is a candidate (差し戻し 1 item 1,
    監督裁定: a plain paragraph line such as `security/CONTROL_MAPPING.md`'s
    own `Version:` line can carry a test-name reference; measured
    2026-09-21, the current file has none outside its SI sections, so this
    path is pinned by a fixture). Each such reference resolves
    with `peer=None` (the D-1 (ii) "SI 節の外" case, resolved against
    `_OUTSIDE_SI_DIR_KEYS`, all 4 directories)."""
    h2_starts = [m.start() for m in _ANY_H2_RE.finditer(text)]
    si_matches = list(_SI_SECTION_RE.finditer(text))
    si_spans = []
    for m in si_matches:
        later = [s for s in h2_starts if s > m.start()]
        end = min(later) if later else len(text)
        si_spans.append((m.group(1), m.start(), end))

    def in_any_si(pos: int) -> bool:
        return any(start <= pos < end for _sid, start, end in si_spans)

    for sid, sec_start, sec_end in si_spans:
        h3_matches = [m for m in _PEER_H3_RE.finditer(text) if sec_start <= m.start() < sec_end]
        for i, h3 in enumerate(h3_matches):
            parsed = _parse_subblock_heading(h3.group(0))
            if parsed is None:
                continue
            peer, subject = parsed
            sub_start = h3.end()
            sub_end = h3_matches[i + 1].start() if i + 1 < len(h3_matches) else sec_end
            axis_matches = [m for m in _AXIS_H4_RE.finditer(text) if sub_start <= m.start() < sub_end]
            for j, am in enumerate(axis_matches):
                axis = am.group(1).strip()
                a_start = am.end()
                a_end = axis_matches[j + 1].start() if j + 1 < len(axis_matches) else sub_end
                for bm in re.finditer(r"^- (.*)$", text[a_start:a_end], re.MULTILINE):
                    bullet = bm.group(1)
                    if bullet == "—":
                        continue
                    line = text.count("\n", 0, a_start + bm.start()) + 1
                    yield _Claim(sid, peer, subject, axis, line, bullet)
    # D-3 (差し戻し 1 item 1): preamble + tail (CCR-14, Rule) -- every
    # non-blank line outside any SI section, not only `- ` bullet lines.
    pos = 0
    for raw_line in text.splitlines(keepends=True):
        start = pos
        pos += len(raw_line)
        line_content = raw_line.rstrip("\n")
        if not line_content.strip():
            continue
        if in_any_si(start):
            continue
        line = text.count("\n", 0, start) + 1
        yield _Claim(None, None, None, None, line, line_content)


def _extract_bullet_references(bullet: str):
    """The 3 reference forms inside one claim bullet's backtick spans:
    `("full", path, name)`, `("bare_colon", name)`, `("bare_name", name)`.
    A backtick span matching none of the 3 (e.g. `` `CredentialStore.
    authenticate` ``, a code reference with no `test_` prefix) is not a
    test-name reference at all and is silently not yielded -- only the 3
    shapes D-1 defines are references this check resolves."""
    refs = []
    for span in re.findall(r"`([^`]+)`", bullet):
        m = _FULL_FORM_REF_RE.match(span)
        if m:
            refs.append(("full", m.group(1), m.group(2)))
            continue
        m = _BARE_COLON_REF_RE.match(span)
        if m:
            refs.append(("bare_colon", m.group(1)))
            continue
        m = _BARE_NAME_REF_RE.match(span)
        if m:
            refs.append(("bare_name", m.group(1)))
            continue
    return refs


def _find_unresolved_test_name_references(text: str, index) -> list[str]:
    """D-1: one message per unresolved reference, `file:line`, the name,
    (SI, peer, subblock, axis) and which rule ((i)/(ii)) applied -- never
    folded/summarized, so every offender is visible from one failed
    assertion (work order section 2.1)."""
    violations: list[str] = []
    for claim in _iter_document_claims(text):
        allowed = _PEER_SCOPED_DIR_KEYS.get(claim.peer, _OUTSIDE_SI_DIR_KEYS)
        for ref in _extract_bullet_references(claim.bullet):
            if ref[0] == "full":
                _kind, path_str, name = ref
                ok = _resolve_full_form(index, allowed, path_str, name)
                rule = "(i)"
            else:
                _kind, name = ref
                ok = _resolve_bare_form(index, allowed, name)
                rule = "(ii)"
            if not ok:
                violations.append(
                    f"{TEST_NAME_RESOLUTION_TARGET_PATH}:{claim.line}: {name!r} "
                    f"(SI={claim.sid}, peer={claim.peer}, subblock={claim.subject!r}, axis={claim.axis}) "
                    f"rule {rule} does not resolve to a real def"
                )
    return violations


def test_control_mapping_md_test_name_reference_extraction_meets_the_floor():
    """D-4: the reference extraction must not go silently empty on the
    real file -- three floors, one per form (work order section 2.4, M4)."""
    text = TEST_NAME_RESOLUTION_TARGET_PATH.read_text()
    full = bare_colon = bare_name = 0
    for claim in _iter_document_claims(text):
        for ref in _extract_bullet_references(claim.bullet):
            if ref[0] == "full":
                full += 1
            elif ref[0] == "bare_colon":
                bare_colon += 1
            else:
                bare_name += 1
    assert full >= FULL_FORM_FLOOR, f"full-form reference count {full} below floor {FULL_FORM_FLOOR}"
    assert bare_colon >= BARE_COLON_FORM_FLOOR, f"bare '::' reference count {bare_colon} below floor {BARE_COLON_FORM_FLOOR}"
    assert bare_name >= BARE_NAME_FORM_FLOOR, f"bare-name reference count {bare_name} below floor {BARE_NAME_FORM_FLOOR}"


def test_control_mapping_test_name_def_index_has_at_least_one_entry_per_directory():
    """D-4: the `ast` index itself must not be silently empty in any of
    the 4 directories."""
    index = _build_def_index()
    empty_dirs = [dir_key for dir_key in _TEST_DIR_KEYS if not any(index.get(dir_key, {}).values())]
    assert not empty_dirs, f"directory key(s) with zero indexed test defs: {empty_dirs}"


def test_test_name_resolution_target_path_is_pinned_to_control_mapping_only():
    """D-3: the object of this check is ONE constant, never a
    `security/*.md` glob and never `CONTROL_MAPPING_HISTORY_PATH` (M8:
    broadening this constant to also cover the history file would pull in
    that file's own verbatim, intentionally-unresolvable superseded test
    names)."""
    assert TEST_NAME_RESOLUTION_TARGET_PATH == CONTROL_MAPPING_PATH
    assert TEST_NAME_RESOLUTION_TARGET_PATH != CONTROL_MAPPING_HISTORY_PATH


def test_control_mapping_md_every_test_name_reference_resolves():
    """D-1: the real file's every Control/Evidence test-name reference
    resolves. WP-1 measurement (work order section 2.1): exactly one
    unresolved reference, `security/CONTROL_MAPPING.md:477`'s
    `test_audit_role_http_authorization_matrix_all_11_endpoints` (renamed
    to `..._all_13_endpoints`, D-5 (a)) -- WP-2 corrects it in the same
    commit (D-6), so this test is green only from that commit onward."""
    text = TEST_NAME_RESOLUTION_TARGET_PATH.read_text()
    index = _build_def_index()
    violations = _find_unresolved_test_name_references(text, index)
    assert violations == [], "\n".join(violations)


def test_control_mapping_md_async_def_test_is_indexed_and_resolves():
    """D-2 (M7): an `async def` test must be indexed -- this uses a real
    one (`r2db-api/tests/test_preauth_concurrency_bound.py::
    test_unauthenticated_flood_is_bounded_by_concurrency`, an `async def`)
    rather than a synthetic fixture, since the fixture path never touches
    the real `ast` index this property is about."""
    index = _build_def_index()
    rel = "r2db-api/tests/test_preauth_concurrency_bound.py"
    assert rel in index["r2db-api"], f"{rel} missing from the r2db-api index"
    assert "test_unauthenticated_flood_is_bounded_by_concurrency" in index["r2db-api"][rel]


def _fake_index(**dir_entries):
    """{dir_key: {rel_path: {names}}}, the same shape `_build_def_index`
    returns, built by hand so the fixture tests below never touch the
    real filesystem."""
    return dir_entries


def test_fixture_full_form_unknown_name_in_a_real_path_does_not_resolve():
    """D-1 (i) (M1): mutating `_resolve_full_form` to check only that
    `path_str` is indexed (never that `name` is one of its own defs)
    would let this resolve."""
    index = _fake_index(**{"r2db-api": {"r2db-api/tests/test_x.py": {"test_real"}}})
    assert not _resolve_full_form(index, ("r2db-api", "conformance-tests"), "r2db-api/tests/test_x.py", "test_fake")


def test_fixture_bare_form_name_only_in_the_other_peer_does_not_resolve():
    """D-1 (ii) peer scope (M2): mutating `_resolve_bare_form` to search
    all 4 directories (never just `allowed_dir_keys`) would let this
    resolve."""
    index = _fake_index(**{"MitateDB-api": {"MitateDB-api/tests/test_y.py": {"test_only_in_mitatedb"}}})
    assert not _resolve_bare_form(index, ("r2db-api", "conformance-tests"), "test_only_in_mitatedb")


def test_fixture_directory_omitted_basename_ambiguous_does_not_resolve():
    """D-1 (i) directory omission (M3): mutating `_resolve_full_form` to
    take the first basename match (instead of requiring exactly one)
    would let this resolve even though `test_dup.py` exists twice within
    the allowed directories."""
    index = _fake_index(**{
        "r2db-api": {"r2db-api/tests/test_dup.py": {"test_shared"}},
        "conformance-tests": {"conformance-tests/test_dup.py": {"test_other"}},
    })
    assert not _resolve_full_form(index, ("r2db-api", "conformance-tests"), "test_dup.py", "test_shared")


def test_fixture_outside_si_section_line_with_unresolved_reference_is_detected():
    """D-3 (差し戻し 1 item 1, 監督裁定, M9): a plain paragraph line OUTSIDE
    every SI section (preamble, `## CCR-14`, `## Rule`) must be scanned
    for test-name references too, not only `- ` bullet lines -- the
    property that let the real file's own version line (a paragraph line
    citing a since-renamed test name) escape detection before this fix."""
    text = "A preamble paragraph line citing `test_totally_fake_outside_si_reference` as evidence.\n"
    violations = _find_unresolved_test_name_references(text, _fake_index())
    assert violations, "expected the outside-SI paragraph line's fake reference to be flagged"
