#!/usr/bin/env python3
"""tools/check_control_mapping_restructure.py -- independent verification
half of the `security/CONTROL_MAPPING.md` restructure (design
docs/design/CONTROL_MAPPING_RESTRUCTURE_V1.md v0.3, section 4, checks
V1-V8). Deliberately does NOT import `tools/restructure_control_mapping.py`:
it implements section 3.1's cell decomposition on its own, using a
different code shape (backtick-span MASKING over the raw cell text, then a
single depth-tracking pass over the masked text to find cut points -- the
generator instead does one linear scan that flips a `tick` boolean
character by character). If the two implementations of the same written
spec disagree, that disagreement itself is a red signal (V2/V3/V8 below),
independent of whether either implementation happens to be the one with
the bug.

Usage:
    ./.venv/bin/python tools/check_control_mapping_restructure.py --base <rev> [--new PATH]

`--base <rev>` reads the OLD file via `git show <rev>:security/CONTROL_MAPPING.md`.
`--new PATH` is the NEW (restructured) file to check (default:
`security/CONTROL_MAPPING.md` in the working tree). Prints one aggregate
line in the form design section 4 specifies:

    sections=16 blocks=48 claims_old=<N> claims_new=<N> missing=0 added=0
    moved=0 reordered=0 unbalanced=0 history=16/16 ccr14=identical
    rule=identical preamble=identical chars=identical

and exits 0 only when every count is at its expected all-clear value (the
missing/added/moved/reordered/unbalanced counters at 0, `history` at
N/N, and the four equality fields all `identical`).

R-50 (design docs/design/CONTROL_MAPPING_MULTI_BLOCK_V0_1.md v0.4 section 9): this tool has no table of its own -- it assumes the OLD table form and is a one-time-only correspondence check against it (design section 6); its `blocks_count = len(sections) * len(PEERS)` (below) counts SI sections times peers, not sub-blocks.
"""
from __future__ import annotations

import argparse
import collections
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTROL_MAPPING_REL = "security/CONTROL_MAPPING.md"

PEERS = ("r2db-api", "MitateDB-api", "Common")
AXES = ("Control", "Evidence", "Status")

_LABEL_RE = re.compile(r"\*\*[^*]+?(\*\*:|:\*\*)")
_LINK_RE = re.compile(r"\s*\[history\]\(CONTROL_MAPPING_HISTORY\.md#si-\d{2}\)")
_ABBR_ENDINGS = ("vs.", "e.g.", "i.e.", "...")
_TICK_SPAN_RE = re.compile(r"`[^`]*`")


class CheckError(RuntimeError):
    pass


def check_no_forbidden_markup(raw_file_text: str) -> None:
    """Design section 3.1 step 0, independently re-checked on the check
    side too (code review item (d), 2026-09-14): if the OLD file contains
    an escaped `\\|` or a `<br` anywhere, the check must stop red rather
    than silently decompose text whose GFM rendering a bullet-list move
    would change. Mirrors `restructure_control_mapping.py`'s own
    `check_no_forbidden_markup` in effect, not by import."""
    problems = []
    if "\\|" in raw_file_text:
        problems.append("escaped `\\|` found in old file")
    if "<br" in raw_file_text:
        problems.append("`<br` found in old file")
    if problems:
        raise CheckError("; ".join(problems))


# ---------------------------------------------------------------------------
# independent decomposition of an OLD cell (masking approach)
# ---------------------------------------------------------------------------


def _mask_backtick_spans(cell: str) -> str:
    """Replace every backtick-delimited span (including the backticks
    themselves) with a run of `\\x00` of the SAME length, so indices are
    unaffected and no masked character can ever match a cut-point pattern
    ('.', ';', '(', ')', or the bold-label opener '**'). A dangling,
    unmatched trailing backtick (odd count) is left unmasked past that
    point -- callers rely on V7 to flag odd-backtick claims separately."""
    return _TICK_SPAN_RE.sub(lambda m: "\x00" * len(m.group(0)), cell)


def decompose(cell: str) -> list[str]:
    """Independent re-implementation of design section 3.1. Masks backtick
    spans first, then walks the masked text tracking paren depth (parens
    inside a masked span never contribute, matching "outside backticks");
    a cut point may fall only where depth == 0. Cut kinds:
      (a) right after a '.' or ';' immediately followed by a space, unless
          the un-masked original segment ending there ends with one of
          'vs.'/'e.g.'/'i.e.'/'...' (never checked for ';').
      (b) right before a bold label `**...**:`/`**...:**` matched against
          the ORIGINAL text (a masked span can never start with '**' since
          masking begins at the opening backtick, not before it, so
          matching against the original text at a depth-0, unmasked
          position is equivalent and avoids re-deriving the label pattern
          against masked text).
    """
    masked = _mask_backtick_spans(cell)
    n = len(cell)
    depth = 0
    cuts = [0]
    for i in range(n):
        mch = masked[i]
        if mch == "\x00":
            continue  # inside a backtick span; never contributes to depth or cuts
        if mch == "(":
            depth += 1
            continue
        if mch == ")":
            depth = max(0, depth - 1)
            continue
        if depth != 0:
            continue
        if _LABEL_RE.match(cell, i) and i > cuts[-1]:
            cuts.append(i)
            continue
        if mch in ".;" and i + 1 < n and cell[i + 1] == " ":
            seg = cell[cuts[-1] : i + 1]
            if mch == ";" or not seg.endswith(_ABBR_ENDINGS):
                cuts.append(i + 1)
    cuts.append(n)
    claims = []
    for a, b in zip(cuts, cuts[1:]):
        c = cell[a:b].strip()
        if c:
            claims.append(c)
    return claims


def strip_history_link(common_cell: str) -> str:
    return _LINK_RE.sub("", common_cell)


def extract_history_link_fragment(common_cell: str) -> str:
    m = re.search(r"\[history\]\(CONTROL_MAPPING_HISTORY\.md#(si-\d{2})\)", common_cell)
    if not m:
        raise CheckError(f"no history link in old Common cell: {common_cell[:120]!r}")
    return m.group(1)


# ---------------------------------------------------------------------------
# old file parsing (table form)
# ---------------------------------------------------------------------------


def _split_table_row(line: str) -> list[str]:
    s = line.strip()
    inner = s[1:-1] if s.startswith("|") and s.endswith("|") else s.strip("|")
    return [c.strip() for c in inner.split("|")]


def read_old_file(base_rev: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{base_rev}:{CONTROL_MAPPING_REL}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


class OldFile:
    def __init__(self, raw_text: str):
        self.raw_text = raw_text
        lines = raw_text.splitlines()
        pipe_idx = [i for i, l in enumerate(lines) if l.strip().startswith("|")]
        if not pipe_idx:
            raise CheckError("old file has no '|'-started table")
        self.preamble = "\n".join(lines[: pipe_idx[0]])
        table_lines = [lines[i] for i in pipe_idx]
        self.header = _split_table_row(table_lines[0])
        self.rows: list[list[str]] = [_split_table_row(l) for l in table_lines[2:]]
        self.tail = "\n".join(lines[pipe_idx[-1] + 1 :])

    def row_by_sid(self) -> dict[str, list[str]]:
        out = {}
        for cells in self.rows:
            m = re.match(r"^(SI-\d+)", cells[0])
            if m:
                out[m.group(1)] = cells
        return out


# ---------------------------------------------------------------------------
# new file parsing (heading/bullet form)
# ---------------------------------------------------------------------------

_SI_HEADING_RE = re.compile(r"^## (SI-\d+.*)$", re.MULTILINE)
_PEER_HEADING_RE = re.compile(r"^### (.+)$", re.MULTILINE)
_AXIS_HEADING_RE = re.compile(r"^#### (.+)$", re.MULTILINE)
_BULLET_RE = re.compile(r"^- (.*)$")


class NewSection:
    def __init__(self, sid: str, name: str):
        self.sid = sid
        self.name = name
        self.history_fragment: str | None = None
        self.claims: dict[tuple[str, str], list[str]] = {}
        self.raw_body: str = ""


def parse_new_file(text: str) -> tuple[str, list[NewSection], str, str]:
    """Returns (preamble, sections, ccr14_section_text, rule_section_text)."""
    si_matches = list(_SI_HEADING_RE.finditer(text))
    if not si_matches:
        raise CheckError("new file has no '## SI-NN' heading")
    preamble = text[: si_matches[0].start()]

    ccr_match = re.search(r"^## CCR-14.*$", text, re.MULTILINE)
    rule_match = re.search(r"^## Rule\s*$", text, re.MULTILINE)
    if not ccr_match or not rule_match:
        raise CheckError("new file missing '## CCR-14 ...' or '## Rule' heading")
    ccr14_text = text[ccr_match.start() : rule_match.start()].rstrip("\n")
    rule_text = text[rule_match.start() :].rstrip("\n")

    sections: list[NewSection] = []
    body_end = ccr_match.start()
    for i, m in enumerate(si_matches):
        end = si_matches[i + 1].start() if i + 1 < len(si_matches) else body_end
        heading_text = m.group(1).strip()
        sid_m = re.match(r"^(SI-\d+)\s+(.*)$", heading_text)
        if not sid_m:
            raise CheckError(f"malformed SI heading: {heading_text!r}")
        sid = sid_m.group(1)
        section_body = text[m.end() : end]
        sec = NewSection(sid, heading_text)
        sec.raw_body = section_body

        link_matches = re.findall(r"\[history\]\(CONTROL_MAPPING_HISTORY\.md#(si-\d{2})\)", section_body)
        sec.history_fragment = link_matches[0] if len(link_matches) == 1 else None
        sec._link_count = len(link_matches)  # type: ignore[attr-defined]

        peer_matches = list(_PEER_HEADING_RE.finditer(section_body))
        for j, pm in enumerate(peer_matches):
            peer_name = pm.group(1).strip()
            pstart = pm.end()
            pend = peer_matches[j + 1].start() if j + 1 < len(peer_matches) else len(section_body)
            peer_body = section_body[pstart:pend]
            axis_matches = list(_AXIS_HEADING_RE.finditer(peer_body))
            for k, am in enumerate(axis_matches):
                axis_name = am.group(1).strip()
                astart = am.end()
                aend = axis_matches[k + 1].start() if k + 1 < len(axis_matches) else len(peer_body)
                axis_body = peer_body[astart:aend]
                bullets = []
                for line in axis_body.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    bm = _BULLET_RE.match(line)
                    if bm:
                        bullets.append(bm.group(1))
                if bullets == ["—"]:
                    bullets = []
                sec.claims[(peer_name, axis_name)] = bullets
        sections.append(sec)
    return preamble, sections, ccr14_text, rule_text


# ---------------------------------------------------------------------------
# preamble transform (duplicated literally from the generator's own written
# spec -- NOT imported, per this file's own module docstring)
# ---------------------------------------------------------------------------

P1_REPLACEMENTS = [
    ("current row below", "current claim below"),
    ("so a row's own", "so a section's own"),
    ("Each row keeps", "Each section keeps"),
    ("holds exactly one", "holds no"),
    (
        "do not add a second one, and keep every cell as one continuous",
        "do not add one, and keep every claim as one bullet on one",
    ),
    (
        "no raw `|` or embedded newline inside a cell",
        "no embedded newline inside a claim",
    ),
]

P2_REPLACEMENTS = [
    ("Cell-length cap", "Length cap"),
    ("longest cell is still", "longest (SI, subsection) block is still"),
    ("control/evidence cell, now", "block, now"),
    ("MAX_CELL_LENGTH", "MAX_BLOCK_LENGTH"),
]

P2_APPEND_TEMPLATE = (
    " A block is one subsection's claims (r2db-api, MitateDB-api or Common) "
    "joined by single spaces. Each physical line is also capped at "
    "`MAX_LINE_LENGTH = {n}`."
)

P2_PARAGRAPH_END_MARKER = "keeps its own copy)."

P3_LINE = (
    "Version: **2.0** (2026-09-14; structure only, content unchanged -- "
    "docs/design/CONTROL_MAPPING_RESTRUCTURE_V1.md)"
)

P4_LINE = (
    "Each claim is one bullet under its invariant, subsection (r2db-api / "
    "MitateDB-api / Common) and axis (Control / Evidence / Status); `- —` "
    "marks an axis with no claim."
)


def transform_preamble(old_preamble: str, max_line_length: int) -> str:
    text = old_preamble
    for old, new in P1_REPLACEMENTS:
        if text.count(old) != 1:
            raise CheckError(f"P1 phrase not found exactly once in preamble: {old!r}")
        text = text.replace(old, new, 1)
    for old, new in P2_REPLACEMENTS:
        if text.count(old) != 1:
            raise CheckError(f"P2 phrase not found exactly once in preamble: {old!r}")
        text = text.replace(old, new, 1)
    if text.count(P2_PARAGRAPH_END_MARKER) != 1:
        raise CheckError("P2 paragraph end marker not found exactly once in preamble")
    idx = text.index(P2_PARAGRAPH_END_MARKER) + len(P2_PARAGRAPH_END_MARKER)
    text = text[:idx] + P2_APPEND_TEMPLATE.format(n=max_line_length) + text[idx:]

    lines = text.split("\n")
    if not lines[2].startswith("Status: **Implementation mapping template**"):
        raise CheckError("preamble line 3 is not the expected Status line; cannot place P3")
    lines = lines[:3] + ["", P3_LINE] + lines[3:]
    orig_line5_idx = 4 + 2
    if not lines[orig_line5_idx].startswith("This document maps common Security Invariants"):
        raise CheckError("preamble line 5 is not the expected intro line; cannot place P4")
    lines = lines[: orig_line5_idx + 1] + ["", P4_LINE] + lines[orig_line5_idx + 1 :]
    return "\n".join(lines)


def _extract_declared_max_line_length(new_preamble: str) -> int:
    m = re.search(r"MAX_LINE_LENGTH = (\d+)", new_preamble)
    if not m:
        raise CheckError("new preamble does not declare MAX_LINE_LENGTH")
    return int(m.group(1))


# ---------------------------------------------------------------------------
# V1-V8
# ---------------------------------------------------------------------------


def check_v1_si_identity(old: OldFile, sections: list[NewSection]) -> tuple[bool, str]:
    old_names = [cells[0] for cells in old.rows]
    new_names = [s.name for s in sections]
    ok = old_names == new_names
    return ok, ("identical" if ok else "differs")


def check_v2_v3_v8(
    old: OldFile, sections: list[NewSection]
) -> tuple[int, int, int, int, dict]:
    """Returns (missing, added, moved, reordered, extra) where extra carries
    chars-preserved (V8) and any diagnostic detail.

    V3 and V8 share one piece of machinery: matching each NEW bullet back
    to the ORIGINAL (pre-decomposition) claim index it came from, within
    its (sid, peer). Axes are walked in the file's own fixed order
    (Control, Evidence, Status) and duplicate claim texts are matched
    first-available-index-first, SHARED across axes (not reset per axis) --
    two axes can never both claim the same original occurrence of a
    repeated claim text. V3 then checks each axis's own matched indices are
    increasing (a subsequence of the original order); V8 pools every
    matched (index, text) pair across all three axes, sorts by original
    index to recover the claim order the design calls "ログ順", rejoins
    with single spaces, and compares (whitespace-stripped) against the old
    cell -- this is what actually detects character loss in decompose()
    itself, independent of which axis a claim was bucketed into."""
    old_by_sid = old.row_by_sid()
    new_by_sid = {s.sid: s for s in sections}
    col_for_peer = {"r2db-api": 1, "MitateDB-api": 2, "Common": 3}

    per_key_old: dict[tuple[str, str], list[str]] = {}
    per_key_new_by_axis: dict[tuple[str, str, str], list[str]] = {}

    for sid, cells in old_by_sid.items():
        section = new_by_sid.get(sid)
        for peer in PEERS:
            cell = cells[col_for_peer[peer]]
            if peer == "Common":
                cell = strip_history_link(cell)
            per_key_old[(sid, peer)] = decompose(cell)
            for axis in AXES:
                per_key_new_by_axis[(sid, peer, axis)] = (
                    section.claims.get((peer, axis), []) if section is not None else []
                )

    # missing/added per (sid, peer), then pair up "moved" globally
    missing_multisets: dict[tuple[str, str], collections.Counter] = {}
    added_multisets: dict[tuple[str, str], collections.Counter] = {}
    for key in per_key_old:
        sid, peer = key
        oc = collections.Counter(per_key_old[key])
        nc = collections.Counter()
        for axis in AXES:
            nc.update(per_key_new_by_axis[(sid, peer, axis)])
        missing_multisets[key] = oc - nc
        added_multisets[key] = nc - oc

    moved = 0
    all_missing_texts: collections.Counter = collections.Counter()
    for c in missing_multisets.values():
        all_missing_texts.update(c)
    all_added_texts: collections.Counter = collections.Counter()
    for c in added_multisets.values():
        all_added_texts.update(c)
    for text in list(all_missing_texts):
        pair_n = min(all_missing_texts[text], all_added_texts.get(text, 0))
        if pair_n:
            moved += pair_n
            all_missing_texts[text] -= pair_n
            all_added_texts[text] -= pair_n
    missing = sum(all_missing_texts.values())
    added = sum(all_added_texts.values())

    # V3 (order) + V8 (character preservation), via shared index matching
    reordered = 0
    chars_ok = True
    chars_offenders: list[tuple[str, str]] = []
    for (sid, peer), old_claims in per_key_old.items():
        index_queue: dict[str, collections.deque] = collections.defaultdict(collections.deque)
        for idx, c in enumerate(old_claims):
            index_queue[c].append(idx)
        used: dict[str, int] = collections.defaultdict(int)
        reconstruction: list[tuple[int, str]] = []
        for axis in AXES:
            bullets = per_key_new_by_axis[(sid, peer, axis)]
            positions = []
            for c in bullets:
                q = index_queue.get(c)
                n_used = used[c]
                if q is not None and n_used < len(q):
                    idx = q[n_used]
                    used[c] += 1
                    positions.append(idx)
                    reconstruction.append((idx, c))
            for a, b in zip(positions, positions[1:]):
                if b <= a:
                    reordered += 1
                    break

        cell = old_by_sid[sid][col_for_peer[peer]]
        if peer == "Common":
            cell = strip_history_link(cell)
        reconstruction.sort(key=lambda pair: pair[0])
        rebuilt = " ".join(text for _, text in reconstruction)
        old_chars = re.sub(r"\s+", "", cell)
        new_chars = re.sub(r"\s+", "", rebuilt)
        if old_chars != new_chars:
            chars_ok = False
            chars_offenders.append((sid, peer))

    extra = {"chars_ok": chars_ok, "chars_offenders": chars_offenders}
    return missing, added, moved, reordered, extra


def check_v4_history(old: OldFile, sections: list[NewSection]) -> tuple[int, int]:
    old_by_sid = old.row_by_sid()
    total = 0
    ok = 0
    for sid, cells in old_by_sid.items():
        total += 1
        try:
            old_fragment = extract_history_link_fragment(cells[3])
        except CheckError:
            continue
        matches = [s for s in sections if s.sid == sid]
        if len(matches) != 1:
            continue
        section = matches[0]
        if getattr(section, "_link_count", 0) == 1 and section.history_fragment == old_fragment:
            ok += 1
    return ok, total


def check_v5_ccr14_rule(old: OldFile, ccr14_text: str, rule_text: str) -> tuple[bool, bool]:
    old_ccr_match = re.search(r"^## CCR-14.*$", old.tail, re.MULTILINE)
    old_rule_match = re.search(r"^## Rule\s*$", old.tail, re.MULTILINE)
    if not old_ccr_match or not old_rule_match:
        raise CheckError("old file missing '## CCR-14 ...' or '## Rule' heading")
    old_ccr14_text = old.tail[old_ccr_match.start() : old_rule_match.start()].rstrip("\n")
    old_rule_text = old.tail[old_rule_match.start() :].rstrip("\n")
    return (old_ccr14_text == ccr14_text, old_rule_text == rule_text)


def check_v6_preamble(old: OldFile, new_preamble: str) -> bool:
    n = _extract_declared_max_line_length(new_preamble)
    expected = transform_preamble(old.preamble, n).strip("\n")
    return expected == new_preamble.strip("\n")


def check_v7_balance(sections: list[NewSection]) -> int:
    unbalanced = 0
    for s in sections:
        for claims in s.claims.values():
            for c in claims:
                if c.count("`") % 2 == 1:
                    unbalanced += 1
                    continue
                masked = _mask_backtick_spans(c)
                depth = 0
                bad = False
                for ch in masked:
                    if ch == "(":
                        depth += 1
                    elif ch == ")":
                        depth -= 1
                        if depth < 0:
                            bad = True
                            break
                if bad or depth != 0:
                    unbalanced += 1
    return unbalanced


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def check_from_texts(old_raw: str, new_text: str) -> tuple[int, str]:
    """Pure core of the check: old-file text + new-file text in, (exit
    code, aggregate line) out. Split out from `run()` so tests can exercise
    it directly on in-memory fixtures without needing a git revision or a
    file on disk."""
    check_no_forbidden_markup(old_raw)
    old = OldFile(old_raw)
    preamble, sections, ccr14_text, rule_text = parse_new_file(new_text)

    v1_ok, v1_status = check_v1_si_identity(old, sections)
    missing, added, moved, reordered, extra = check_v2_v3_v8(old, sections)
    history_ok, history_total = check_v4_history(old, sections)
    ccr14_ok, rule_ok = check_v5_ccr14_rule(old, ccr14_text, rule_text)
    preamble_ok = check_v6_preamble(old, preamble)
    unbalanced = check_v7_balance(sections)

    col_for_peer = {"r2db-api": 1, "MitateDB-api": 2, "Common": 3}
    old_by_sid = old.row_by_sid()
    claims_old = 0
    for sid, cells in old_by_sid.items():
        for peer in PEERS:
            cell = cells[col_for_peer[peer]]
            if peer == "Common":
                cell = strip_history_link(cell)
            claims_old += len(decompose(cell))
    claims_new = 0
    for s in sections:
        for claims in s.claims.values():
            claims_new += len(claims)

    sections_count = len(sections)
    blocks_count = len(sections) * len(PEERS)

    line = (
        f"sections={sections_count} blocks={blocks_count} claims_old={claims_old} "
        f"claims_new={claims_new} missing={missing} added={added} moved={moved} "
        f"reordered={reordered} unbalanced={unbalanced} "
        f"history={history_ok}/{history_total} "
        f"ccr14={'identical' if ccr14_ok else 'differs'} "
        f"rule={'identical' if rule_ok else 'differs'} "
        f"preamble={'identical' if preamble_ok else 'differs'} "
        f"chars={'identical' if extra['chars_ok'] else 'differs'}"
    )

    all_clear = (
        v1_ok
        and missing == 0
        and added == 0
        and moved == 0
        and reordered == 0
        and unbalanced == 0
        and history_ok == history_total
        and ccr14_ok
        and rule_ok
        and preamble_ok
        and extra["chars_ok"]
    )
    if not v1_ok:
        line = f"sections={v1_status} " + line

    return (0 if all_clear else 1), line


def run(base_rev: str, new_path: Path) -> tuple[int, str]:
    old_raw = read_old_file(base_rev)
    new_text = new_path.read_text()
    return check_from_texts(old_raw, new_text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="git revision to read the old CONTROL_MAPPING.md from")
    parser.add_argument("--new", default=str(REPO_ROOT / CONTROL_MAPPING_REL), help="path to the new (restructured) file")
    args = parser.parse_args(argv)
    try:
        code, line = run(args.base, Path(args.new))
    except CheckError as exc:
        print(f"check_control_mapping_restructure: CHECK STOPPED: {exc}", file=sys.stderr)
        return 1
    print(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
