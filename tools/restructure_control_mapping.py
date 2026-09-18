#!/usr/bin/env python3
"""tools/restructure_control_mapping.py -- regenerate `security/CONTROL_MAPPING.md`
from its old (pre-restructure) 4-column table form into the new heading/bullet
form, deterministically, per design
docs/design/CONTROL_MAPPING_RESTRUCTURE_V1.md v0.3 (R-22 question 2, WP-2).

This script is the GENERATION half of a generate/check pair
(`tools/check_control_mapping_restructure.py` is the independent CHECK half
-- it does not import this module; it implements section 3.1's decomposition
on its own, so the two implementations must independently agree). This file
implements design sections 2-4:

- section 3.1: split each of the 3 old table cells (r2db-api,
  MitateDB-api, Common) per row into an ordered list of "claims" -- the old
  Common cell's `[history](...)` link is stripped first (section 2's
  "参照側の影響" -- the link moves to its own line, verbatim, under the new
  heading instead).
- axis assignment (design v0.4, WP-3 audit corrective, monitor ruling
  2026-09-14): rule-based inference (the former R0-R6 ladder) is RETIRED --
  it misassigned 38 of 418 claims by the WP-3 audit's own count, all
  traceable to structural flaws in the rules themselves (a peer-column
  default that swallowed test-evidence prose, an anaphora rule that
  inherited the wrong axis across a label boundary, a label regex that
  missed a mid-sentence "-- disclosed", a backtick-only rule that caught a
  non-test identifier). The axis of record is now
  `tools/control_mapping_axes.tsv` (columns `si peer index head axis`,
  one row per claim, `head` the claim's own leading 60 characters) --
  this script only decomposes and looks the result up. Every claim must
  match exactly one table row by (si, peer, index) with an identical
  `head`; any claim with no matching row, any table row past a peer's own
  claim count (or naming an (si, peer) absent from the document), or any
  `head` mismatch stops generation red (`load_axes_table` /
  `assign_axes_from_table` below). The old rule ladder is not reachable
  from this module at all -- see `docs/design/CONTROL_MAPPING_RESTRUCTURE_V1.md`
  §9 for the corrected axis counts and the audit's own per-claim record.
- section 2: emit the new heading/subsection/bullet form, one `## SI-NN
  <name>` section per row in the old table's own order, each with `###
  r2db-api` / `### MitateDB-api` / `### Common` subsections (old column
  order) and `#### Control` / `#### Evidence` / `#### Status`
  sub-subsections (fixed order) each holding one `- <claim>` bullet per
  line (`- —` when the axis has no claim for that subsection).
- the preamble's P1-P4 changes (section 2's "preamble の変更" table) and the
  `## CCR-14 ...` / `## Rule` tail sections carried through byte-for-byte,
  unchanged, after all 16 SI sections.

`MAX_LINE_LENGTH` (referenced by P2's appended sentence, and by the
registered conformance test's own line-length guard) is computed from the
generated file itself: the longest physical line, rounded up to the next
multiple of 100 -- never a hand-picked constant.

Usage:
    ./.venv/bin/python tools/restructure_control_mapping.py --base <rev> [--out PATH] [--log PATH] [--axes-table PATH]

`--base <rev>` reads the OLD file via `git show <rev>:security/CONTROL_MAPPING.md`
(never the working tree, so the input is always the exact historical
content named on the command line). `--out` writes the new file there
(default: print to stdout). `--log PATH` additionally writes a TSV of every
claim's (SI, peer, claim index, axis) assignment, in emission order.
`--axes-table PATH` overrides the default `tools/control_mapping_axes.tsv`.

R-50 (docs/design/CONTROL_MAPPING_MULTI_BLOCK_V0_1.md v0.4, section 9): 本表は 2026-09-14 の一度限りの生成の入力であり、小ブロックの割当は含まない。
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTROL_MAPPING_REL = "security/CONTROL_MAPPING.md"

PEERS = ("r2db-api", "MitateDB-api", "Common")
AXES = ("Control", "Evidence", "Status")

# ---------------------------------------------------------------------------
# section 3.1: decomposition (old cell -> ordered list of claims)
# ---------------------------------------------------------------------------

_LINK_RE = re.compile(r"\s*\[history\]\(CONTROL_MAPPING_HISTORY\.md#si-\d{2}\)")
_LABEL_RE = re.compile(r"\*\*[^*]+?(\*\*:|:\*\*)")
_ABBR_ENDINGS = ("vs.", "e.g.", "i.e.", "...")


def extract_history_link(common_cell: str) -> str:
    """Return the verbatim `[history](CONTROL_MAPPING_HISTORY.md#si-NN)` link
    found in a row's old Common cell (section 2: "旧 Common セルから移す")."""
    m = re.search(r"\[history\]\(CONTROL_MAPPING_HISTORY\.md#si-\d{2}\)", common_cell)
    if not m:
        raise ValueError(f"no history link found in Common cell: {common_cell[:120]!r}")
    return m.group(0)


def strip_history_link(common_cell: str) -> str:
    return _LINK_RE.sub("", common_cell)


def check_no_forbidden_markup(raw_file_text: str) -> None:
    """Section 3.1 step 0: if the base file contains an escaped `\\|` or a
    `<br` anywhere, generation stops red (GFM only un-escapes a code-span
    `\\|` inside a table; moving that text into a bullet would silently
    change how it renders)."""
    problems = []
    if "\\|" in raw_file_text:
        problems.append("escaped `\\|` found in base file")
    if "<br" in raw_file_text:
        problems.append("`<br` found in base file")
    if problems:
        raise GenerationError("; ".join(problems))


def decompose(cell: str) -> list[str]:
    """Split one old table cell into an ordered list of claims (design
    section 3.1, steps 2-4). Step 1 (stripping the history link from the
    Common cell) is the caller's job -- this function only decomposes.

    Scans left to right tracking backtick open/close state and, outside
    backticks, parenthesis depth. A cut point can only occur outside a
    backtick span at paren-depth 0. Two cut kinds:
      (a) immediately after a '.' or ';' that is followed by a space,
          unless the segment ending there ends with 'vs.'/'e.g.'/'i.e.'/'...'
          (that exception never applies to ';', which cannot end such a
          segment).
      (b) immediately before a bold label `**...**:`/`**...:**`.
    Each resulting claim is stripped of surrounding whitespace; empty
    claims are discarded. Claim content itself is never altered.
    """
    cuts = [0]
    tick = False
    depth = 0
    i = 0
    n = len(cell)
    while i < n:
        ch = cell[i]
        if ch == "`":
            tick = not tick
            i += 1
            continue
        if not tick:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth = max(0, depth - 1)
            if depth == 0:
                m = _LABEL_RE.match(cell, i)
                if m and i > cuts[-1]:
                    cuts.append(i)
                    i += 1
                    continue
                if ch in ".;" and i + 1 < n and cell[i + 1] == " ":
                    seg = cell[cuts[-1] : i + 1]
                    if ch == ";" or not seg.endswith(_ABBR_ENDINGS):
                        cuts.append(i + 1)
        i += 1
    cuts.append(n)
    claims = []
    for a, b in zip(cuts, cuts[1:]):
        c = cell[a:b].strip()
        if c:
            claims.append(c)
    return claims


# ---------------------------------------------------------------------------
# axis assignment: table lookup (design v0.4 -- R0-R6 rule inference retired)
# ---------------------------------------------------------------------------


class GenerationError(RuntimeError):
    """Raised when generation must stop red (design section 3.1 step 0; the
    axis table's own 1:1-with-decomposition requirement below)."""


AXES_TABLE_REL = "tools/control_mapping_axes.tsv"
_AXES_TABLE_HEADER = ["si", "peer", "index", "head", "axis"]


def load_axes_table(path: Path) -> tuple[dict[tuple[str, str, int], str], dict[tuple[str, str, int], str]]:
    """Load the axis-assignment table of record: one row per claim, keyed
    by (si, peer, index) -- the same 0-based per-(SI, peer) decomposition
    index `decompose()` produces -- carrying that claim's own leading 60
    characters (`head`, for 1:1 verification against a fresh decomposition)
    and its assigned axis. Returns (heads, axes), both keyed the same way.
    A duplicate (si, peer, index) key anywhere in the file is a hard error:
    every row is meant to answer for exactly one claim, so two rows naming
    the same claim can never be silently collapsed into one by dict
    overwrite. A duplicate `head` WITHIN the same (si, peer) across two
    different indices is also a hard error (monitor ruling 2026-09-14,
    code review item 2): two distinct claims in one cell sharing the same
    leading 60 characters is exactly the shape a copy-paste authoring
    mistake (the wrong row's head pasted onto a different index) would
    take, and nothing else downstream would ever catch it -- the 1:1
    head-match check in `assign_axes_from_table` compares each index
    independently and would happily accept two rows that both happen to
    match SOME claim's head, even the wrong one, as long as the multiset
    of heads present matches ambiguously."""
    heads: dict[tuple[str, str, int], str] = {}
    axes: dict[tuple[str, str, int], str] = {}
    seen: set[tuple[str, str, int]] = set()
    heads_seen_per_peer: dict[tuple[str, str], dict[str, int]] = {}
    with open(path, encoding="utf-8") as f:
        header_line = f.readline().rstrip("\n")
        if header_line.split("\t") != _AXES_TABLE_HEADER:
            raise GenerationError(f"axis table {path} has unexpected header: {header_line!r}")
        for lineno, raw_line in enumerate(f, start=2):
            line = raw_line.rstrip("\n")
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) != 5:
                raise GenerationError(
                    f"axis table {path}:{lineno}: expected 5 tab-separated fields, got {len(parts)}: {line!r}"
                )
            si, peer, index_s, head, axis = parts
            try:
                index = int(index_s)
            except ValueError:
                raise GenerationError(f"axis table {path}:{lineno}: index {index_s!r} is not an integer")
            if axis not in AXES:
                raise GenerationError(f"axis table {path}:{lineno}: axis {axis!r} is not one of {AXES}")
            key = (si, peer, index)
            if key in seen:
                raise GenerationError(f"axis table {path}:{lineno}: duplicate row for (si, peer, index)={key}")
            seen.add(key)
            peer_key = (si, peer)
            per_peer_heads = heads_seen_per_peer.setdefault(peer_key, {})
            if head in per_peer_heads:
                raise GenerationError(
                    f"axis table {path}:{lineno}: duplicate head within ({si}, {peer}) -- "
                    f"index {index} repeats the same head already used by index {per_peer_heads[head]}: {head!r}"
                )
            per_peer_heads[head] = index
            heads[key] = head
            axes[key] = axis
    return heads, axes


def assign_axes_from_table(
    claims_by_key: dict[tuple[str, str], list[str]],
    heads: dict[tuple[str, str, int], str],
    axes: dict[tuple[str, str, int], str],
) -> dict[tuple[str, str, int], str]:
    """Cross-check the table against a fresh decomposition and return
    {(si, peer, index): axis} for every claim. `claims_by_key` is
    {(si, peer): [claim, ...]} in decomposition order. Any of the three
    failure modes design v0.4 names -- a claim with no matching table row
    ("missing"), a table row past the end of its (si, peer)'s own claim
    list or naming an (si, peer) absent from the document entirely
    ("surplus"), or a table row whose `head` does not match the freshly
    decomposed claim's own leading 60 characters ("head mismatch") -- is
    collected and reported together, then raised as one GenerationError."""
    remaining = set(heads.keys())
    missing: list[tuple[str, str, int]] = []
    mismatched: list[tuple[tuple[str, str, int], str, str]] = []
    result: dict[tuple[str, str, int], str] = {}

    for (si, peer), claims in claims_by_key.items():
        for k, claim in enumerate(claims):
            key = (si, peer, k)
            if key not in heads:
                missing.append(key)
                continue
            remaining.discard(key)
            expected_head = claim[:60]
            if heads[key] != expected_head:
                mismatched.append((key, heads[key], expected_head))
                continue
            result[key] = axes[key]

    surplus = sorted(remaining)

    if missing or mismatched or surplus:
        parts = []
        if missing:
            parts.append(f"missing table row(s) for {len(missing)} claim(s), e.g. {missing[:5]}")
        if mismatched:
            parts.append(
                f"head mismatch for {len(mismatched)} row(s), e.g. "
                f"{[(k, table_head, real_head) for k, table_head, real_head in mismatched[:3]]}"
            )
        if surplus:
            parts.append(f"surplus table row(s) not consumed by any claim: {len(surplus)}, e.g. {surplus[:5]}")
        raise GenerationError("axis table is not 1:1 with the decomposed claims: " + "; ".join(parts))

    return result


# ---------------------------------------------------------------------------
# preamble transform (P1-P4)
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
            raise GenerationError(f"P1 phrase not found exactly once in preamble: {old!r}")
        text = text.replace(old, new, 1)
    for old, new in P2_REPLACEMENTS:
        if text.count(old) != 1:
            raise GenerationError(f"P2 phrase not found exactly once in preamble: {old!r}")
        text = text.replace(old, new, 1)
    if text.count(P2_PARAGRAPH_END_MARKER) != 1:
        raise GenerationError("P2 paragraph end marker not found exactly once in preamble")
    idx = text.index(P2_PARAGRAPH_END_MARKER) + len(P2_PARAGRAPH_END_MARKER)
    text = text[:idx] + P2_APPEND_TEMPLATE.format(n=max_line_length) + text[idx:]

    lines = text.split("\n")
    if not lines[2].startswith("Status: **Implementation mapping template**"):
        raise GenerationError("preamble line 3 is not the expected Status line; cannot place P3")
    lines = lines[:3] + ["", P3_LINE] + lines[3:]
    orig_line5_idx = 4 + 2  # original 0-based index 4 (line 5), shifted +2 by the P3 insertion
    if not lines[orig_line5_idx].startswith("This document maps common Security Invariants"):
        raise GenerationError("preamble line 5 is not the expected intro line; cannot place P4")
    lines = lines[: orig_line5_idx + 1] + ["", P4_LINE] + lines[orig_line5_idx + 1 :]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# table parsing (old file)
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
            raise GenerationError("old file has no '|'-started table")
        span = pipe_idx[-1] - pipe_idx[0] + 1
        if span != len(pipe_idx):
            raise GenerationError("old file appears to have more than one '|'-started table")
        self.preamble = "\n".join(lines[: pipe_idx[0]])
        table_lines = [lines[i] for i in pipe_idx]
        self.header = _split_table_row(table_lines[0])
        self.rows: list[list[str]] = []
        for line in table_lines[2:]:
            cells = _split_table_row(line)
            if len(cells) != len(self.header):
                raise GenerationError(f"malformed table row (column count mismatch): {line[:80]!r}")
            self.rows.append(cells)
        self.tail = "\n".join(lines[pipe_idx[-1] + 1 :])


# ---------------------------------------------------------------------------
# generation
# ---------------------------------------------------------------------------


class SiSection:
    __slots__ = ("sid", "name", "history_link", "claims_by_peer_axis", "claims_log")

    def __init__(self, sid: str, name: str, history_link: str):
        self.sid = sid
        self.name = name
        self.history_link = history_link
        self.claims_by_peer_axis: dict[tuple[str, str], list[str]] = {
            (peer, axis): [] for peer in PEERS for axis in AXES
        }
        self.claims_log: list[tuple[str, str, int, str]] = []  # sid, peer, k, axis


def build_sections(
    old: OldFile, heads: dict[tuple[str, str, int], str], axes_table: dict[tuple[str, str, int], str]
) -> list[SiSection]:
    # Decompose every (sid, peer) cell first, so the table cross-check
    # (assign_axes_from_table) sees the WHOLE document's claims at once --
    # a "surplus" table row can name an (sid, peer) that would otherwise
    # never be visited at all.
    claims_by_key: dict[tuple[str, str], list[str]] = {}
    row_meta: list[tuple[str, str, str]] = []  # sid, invariant_cell, history_link
    for cells in old.rows:
        invariant_cell = cells[0]
        m = re.match(r"^(SI-\d+)", invariant_cell)
        if not m:
            raise GenerationError(f"row Invariant cell has no leading SI-NN id: {invariant_cell!r}")
        sid = m.group(1)
        history_link = extract_history_link(cells[3])
        row_meta.append((sid, invariant_cell, history_link))
        for col_idx, peer in ((1, "r2db-api"), (2, "MitateDB-api"), (3, "Common")):
            cell = cells[col_idx]
            if peer == "Common":
                cell = strip_history_link(cell)
            claims_by_key[(sid, peer)] = decompose(cell)

    axis_by_key = assign_axes_from_table(claims_by_key, heads, axes_table)

    sections: list[SiSection] = []
    for sid, invariant_cell, history_link in row_meta:
        section = SiSection(sid, invariant_cell, history_link)
        for peer in PEERS:
            claims = claims_by_key[(sid, peer)]
            for k, claim in enumerate(claims):
                axis = axis_by_key[(sid, peer, k)]
                section.claims_by_peer_axis[(peer, axis)].append(claim)
                section.claims_log.append((sid, peer, k, axis))
        sections.append(section)
    return sections


def render_section(section: SiSection) -> str:
    """Render one `## SI-NN <name>` section. Every logical block (the
    heading+link pair, each `### <peer>` heading, each `#### <axis>` bullet
    group) is separated from the next by exactly one blank line; no blank
    line is left dangling at the very end (the caller joins sections with
    `\\n\\n`, which supplies that separator between sections)."""
    lines = [f"## {section.name}", "", section.history_link, ""]
    for peer in PEERS:
        lines.append(f"### {peer}")
        lines.append("")
        for axis in AXES:
            lines.append(f"#### {axis}")
            lines.append("")
            claims = section.claims_by_peer_axis[(peer, axis)]
            if claims:
                lines.extend(f"- {c}" for c in claims)
            else:
                lines.append("- —")
            lines.append("")
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def compute_max_line_length(text: str) -> int:
    """The longest physical line in `text`, rounded UP to the next multiple
    of 100 (design section 2: "最長の物理行は約1,400字になる...100字単位で
    切り上げる")."""
    longest = max((len(l) for l in text.splitlines()), default=0)
    return ((longest + 99) // 100) * 100


def generate_from_text(
    raw: str, axes_table: tuple[dict[tuple[str, str, int], str], dict[tuple[str, str, int], str]] | None = None
) -> tuple[str, list[tuple[str, str, int, str]]]:
    """Pure core of generation: old-file text in, (new-file text, per-claim
    assignment log) out. Split out from `generate()` so tests can exercise
    it directly on in-memory fixtures without needing a git revision or a
    real `tools/control_mapping_axes.tsv` on disk -- pass `axes_table` as
    `(heads, axes)` (the same shape `load_axes_table` returns) to supply a
    fixture's own small table; omit it to load the real one from
    `tools/control_mapping_axes.tsv`."""
    check_no_forbidden_markup(raw)
    old = OldFile(raw)

    if axes_table is None:
        heads, axes = load_axes_table(REPO_ROOT / AXES_TABLE_REL)
    else:
        heads, axes = axes_table

    sections = build_sections(old, heads, axes)

    body = "\n\n".join(render_section(s) for s in sections)

    # First pass with a placeholder N to size the file, then recompute and
    # verify the fixed point (the P2 sentence's own line length never ends
    # up the longest line in practice, but this is measured, not assumed).
    placeholder_preamble = transform_preamble(old.preamble, 0).rstrip("\n")
    draft = placeholder_preamble + "\n\n" + body + "\n" + old.tail
    n = compute_max_line_length(draft)
    for _ in range(4):
        preamble = transform_preamble(old.preamble, n).rstrip("\n")
        full = preamble + "\n\n" + body + "\n" + old.tail
        n2 = compute_max_line_length(full)
        if n2 == n:
            break
        n = n2
    else:
        raise GenerationError("MAX_LINE_LENGTH computation did not reach a fixed point")

    full = full.rstrip("\n") + "\n"

    log: list[tuple[str, str, int, str]] = []
    for s in sections:
        log.extend(s.claims_log)
    return full, log


def generate(base_rev: str, axes_table_path: Path | None = None) -> tuple[str, list[tuple[str, str, int, str]]]:
    raw = read_old_file(base_rev)
    axes_table = load_axes_table(axes_table_path or (REPO_ROOT / AXES_TABLE_REL))
    return generate_from_text(raw, axes_table)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="git revision to read the old CONTROL_MAPPING.md from")
    parser.add_argument("--out", help="write the generated file here (default: stdout)")
    parser.add_argument("--log", help="write the per-claim assignment TSV log here")
    parser.add_argument("--axes-table", help="override the default tools/control_mapping_axes.tsv path")
    args = parser.parse_args(argv)

    try:
        axes_table_path = Path(args.axes_table) if args.axes_table else None
        full, log = generate(args.base, axes_table_path)
    except GenerationError as exc:
        print(f"restructure_control_mapping: GENERATION STOPPED: {exc}", file=sys.stderr)
        return 1

    if args.out:
        Path(args.out).write_text(full)
    else:
        sys.stdout.write(full)

    if args.log:
        with open(args.log, "w") as f:
            f.write("sid\tpeer\tclaim_index\taxis\n")
            for sid, peer, k, axis in log:
                f.write(f"{sid}\t{peer}\t{k}\t{axis}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
