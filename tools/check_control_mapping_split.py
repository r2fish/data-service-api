#!/usr/bin/env python3
"""tools/check_control_mapping_split.py -- independent verification that a
`security/CONTROL_MAPPING.md` sub-block split (design
docs/design/CONTROL_MAPPING_MULTI_BLOCK_V0_1.md v0.4, section 6, condition
(ii)) moved bullets around WITHOUT losing, inventing, or silently
relocating any of them across (SI, peer, axis) -- i.e. that nothing
"escaped" to a different Security Invariant, peer, or axis than it started
in. Deliberately does NOT reuse `tools/check_control_mapping_restructure.py`
(design section 6): that tool's own `missing`/`added` folding into `moved`
is a body-text GLOBAL pairing across the whole file, which would make a
bullet moved to the WRONG Security Invariant look identical to one moved
within the SAME (SI, peer, axis) -- both would show up as one `missing`
and one `added` with matching text, and the old algorithm folds any such
pair into `moved` regardless of which SI/peer/axis it came from or landed
in. This script instead builds the (SI, peer, axis, body) 4-tuple multiset
STRICTLY -- a move to a different SI, peer, or axis always shows up as
both a `missing` and an `added`, never silently paired away.

Usage:
    ./.venv/bin/python tools/check_control_mapping_split.py --base <rev> [--new PATH] [--expect "<line>"]

`--base <rev>` reads the OLD file via `git show <rev>:security/CONTROL_MAPPING.md`.
`--new PATH` is the NEW (split) file to check (default:
`security/CONTROL_MAPPING.md` in the working tree). Both the old and new
texts are read with the SAME heading/bullet-form parser (design section 5)
-- the "old" form for this tool is simply a heading/bullet file whose every
peer has exactly one (default, unnamed) sub-block; nothing peer-specific
distinguishes "old" from "new" beyond that.

Prints one aggregate line in the design section 6 form:

    missing=<N> added=<N> moved=<N> empty_axis_added=<N> empty_axis_removed=<N>
    subsequence=ok|violation preamble=identical|differs ccr14=identical|differs
    rule=identical|differs

`missing`/`added`/`moved`/`empty_axis_added`/`empty_axis_removed` are
legitimately non-zero for an intentional split (design section 6's own
"期待する集計行"), so this script does not gate its exit code on them by
itself -- pass `--expect "<line>"` (the exact line the caller expects) to
turn that by-hand comparison into a machine gate: exit 1 if the computed
line does not match `--expect` verbatim (訂正註 1 S-2). `preamble` stays a
2-value identical/differs label (a legitimate split rewrites the
preamble); when it `differs`, a unified diff of just the two preambles is
printed to stdout so a reviewer does not have to open both files by hand.
Exit 0 requires `subsequence=ok` AND `ccr14=identical` AND `rule=identical`
AND (if `--expect` was given) a matching aggregate line -- the first three
are never expected to differ for any legitimate split (design section 6,
condition (ii) and section 3(ii)). Exit 2 if the input cannot be parsed
(`CheckError`).
"""
from __future__ import annotations

import argparse
import collections
import difflib
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTROL_MAPPING_REL = "security/CONTROL_MAPPING.md"

PEERS = ("r2db-api", "MitateDB-api", "Common")
AXES = ("Control", "Evidence", "Status")

_SI_SECTION_RE = re.compile(r"^## (SI-\d+)\s+(.+?)\s*$", re.MULTILINE)
_ANY_H2_RE = re.compile(r"^## (.+?)\s*$", re.MULTILINE)
_H3_LINE_RE = re.compile(r"^### (.*)$", re.MULTILINE)
_AXIS_H4_RE = re.compile(r"^#### (.+?)\s*$", re.MULTILINE)
_BULLET_RE = re.compile(r"^- (.*)$")
_SUBBLOCK_HEADING_RE = re.compile(r"^### (r2db-api|MitateDB-api|Common)(?: -- (\S(?:.*\S)?))?$")
_SUBJECT_TOKEN_RE = re.compile(r"^[\x21-\x7E]+(?: [\x21-\x7E]+)*$")


class CheckError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# heading/bullet-form parsing (design section 5), duplicated from
# `conformance-tests/test_control_mapping_register.py` deliberately, not
# imported -- this tool is standard-library only and must not depend on a
# pytest-carrying module (design section 12, Q-4).
# ---------------------------------------------------------------------------


class Bullet:
    __slots__ = ("sid", "peer", "axis", "subblock", "body", "order")

    def __init__(self, sid: str, peer: str, axis: str, subblock: str | None, body: str, order: int):
        self.sid = sid
        self.peer = peer
        self.axis = axis
        self.subblock = subblock
        self.body = body
        self.order = order  # position within its own (sid, peer, axis), file order


def _parse_subblock_heading(line: str) -> tuple[str, str | None] | None:
    m = _SUBBLOCK_HEADING_RE.match(line)
    if not m:
        return None
    peer, subject = m.group(1), m.group(2)
    if subject is not None:
        if " -- " in subject or not _SUBJECT_TOKEN_RE.match(subject):
            return None
    return peer, subject


class ParsedFile:
    def __init__(self, text: str):
        self.text = text
        si_matches = list(_SI_SECTION_RE.finditer(text))
        if not si_matches:
            raise CheckError("no '## SI-NN' section found")
        all_h2 = list(_ANY_H2_RE.finditer(text))
        all_h2_starts = [m.start() for m in all_h2]

        self.preamble = text[: si_matches[0].start()]

        ccr_match = re.search(r"^## CCR-14.*$", text, re.MULTILINE)
        rule_match = re.search(r"^## Rule\s*$", text, re.MULTILINE)
        if not ccr_match or not rule_match:
            raise CheckError("missing '## CCR-14 ...' or '## Rule' heading")
        self.ccr14_text = text[ccr_match.start() : rule_match.start()].rstrip("\n")
        self.rule_text = text[rule_match.start() :].rstrip("\n")

        # bullets: (sid, peer, axis) -> ordered list of Bullet
        self.bullets: dict[tuple[str, str, str], list[Bullet]] = collections.defaultdict(list)
        # empty-axis counts: (sid, peer, axis) -> count of subblocks whose
        # axis is the '- —' placeholder
        self.empty_axis_counts: collections.Counter = collections.Counter()

        for m in si_matches:
            sid = m.group(1)
            start = m.end()
            later = [s for s in all_h2_starts if s > m.start()]
            end = min(later) if later else len(text)
            body = text[start:end]

            h3_matches = list(_H3_LINE_RE.finditer(body))
            for i, hm in enumerate(h3_matches):
                raw_line = hm.group(0)
                hstart = hm.end()
                hend = h3_matches[i + 1].start() if i + 1 < len(h3_matches) else len(body)
                parsed = _parse_subblock_heading(raw_line)
                if parsed is None:
                    raise CheckError(f"{sid}: unrecognized sub-block heading: {raw_line!r}")
                peer, subject = parsed
                subblock_body = body[hstart:hend]

                axis_matches = list(_AXIS_H4_RE.finditer(subblock_body))
                axis_names = [am.group(1).strip() for am in axis_matches]
                if axis_names != list(AXES):
                    raise CheckError(f"{sid}/{peer}/{subject!r}: axes are {axis_names}, expected {list(AXES)}")
                for j, am in enumerate(axis_matches):
                    axis = axis_names[j]
                    astart = am.end()
                    aend = axis_matches[j + 1].start() if j + 1 < len(axis_matches) else len(subblock_body)
                    axis_body = subblock_body[astart:aend]
                    lines = [l.strip() for l in axis_body.splitlines() if l.strip()]
                    bullet_texts = []
                    for line in lines:
                        bm = _BULLET_RE.match(line)
                        if bm:
                            bullet_texts.append(bm.group(1))
                    if bullet_texts == ["—"]:
                        self.empty_axis_counts[(sid, peer, axis)] += 1
                        continue
                    key = (sid, peer, axis)
                    for text_val in bullet_texts:
                        order = len(self.bullets[key])
                        self.bullets[key].append(Bullet(sid, peer, axis, subject, text_val, order))


# ---------------------------------------------------------------------------
# design section 6's comparison algorithm
# ---------------------------------------------------------------------------


def _multiset4(parsed: ParsedFile) -> collections.Counter:
    """(sid, peer, axis, body) 4-tuple multiset -- design section 6, step
    2. No global pairing: this is the ONLY multiset used to compute
    missing/added."""
    counter: collections.Counter = collections.Counter()
    for key, bullets in parsed.bullets.items():
        sid, peer, axis = key
        for b in bullets:
            counter[(sid, peer, axis, b.body)] += 1
    return counter


def check_missing_added(old: ParsedFile, new: ParsedFile) -> tuple[int, int, collections.Counter, collections.Counter]:
    old_c = _multiset4(old)
    new_c = _multiset4(new)
    missing_c = old_c - new_c
    added_c = new_c - old_c
    return sum(missing_c.values()), sum(added_c.values()), missing_c, added_c


def check_moved(old: ParsedFile, new: ParsedFile) -> int:
    """Design section 6, step 3 (as corrected by 訂正註 1 S-3): `moved`
    counts ONLY a sub-block reassignment of a bullet whose (sid, peer,
    axis, body) 4-tuple is otherwise unchanged -- pairing each such bullet
    between the OLD file and the NEW file, FIFO, per 4-tuple (mirrors
    `check_subsequence`'s own per-4-tuple FIFO queue below), and counting
    the pairs whose OLD sub-block name differs from the NEW one. Comparing
    only the new side's sub-block name (whether it landed on a NAMED
    block) is wrong: it cannot tell a same-named-to-same-named bullet
    (unmoved) from a bullet moved BACK from a named block to the default
    one (both would compare a named-vs-something value against `None` the
    same way), and it double-charges an already-split file compared to
    itself. 訂正註 1's own measured fixtures: an already-split file
    compared to itself must be `moved=0`, and a bullet moved from a named
    block back to the default one must be `moved=1`."""
    old_by4: dict[tuple[str, str, str, str], collections.deque] = collections.defaultdict(collections.deque)
    for key, bullets in old.bullets.items():
        sid, peer, axis = key
        for b in bullets:
            old_by4[(sid, peer, axis, b.body)].append(b.subblock)

    moved = 0
    for key, bullets in new.bullets.items():
        sid, peer, axis = key
        for b in bullets:
            queue = old_by4.get((sid, peer, axis, b.body))
            if not queue:
                continue
            old_subblock = queue.popleft()
            if old_subblock != b.subblock:
                moved += 1
    return moved


def check_empty_axis(old: ParsedFile, new: ParsedFile) -> tuple[int, int]:
    """Design section 6, step 4: '- —' is excluded from the main
    multiset; net new/removed placeholders are counted separately, per
    (sid, peer, axis)."""
    keys = set(old.empty_axis_counts) | set(new.empty_axis_counts)
    added = removed = 0
    for key in keys:
        o = old.empty_axis_counts.get(key, 0)
        n = new.empty_axis_counts.get(key, 0)
        if n > o:
            added += n - o
        elif o > n:
            removed += o - n
    return added, removed


def check_subsequence(old: ParsedFile, new: ParsedFile) -> bool:
    """Design section 6, step 5: for each (sid, peer, axis, subblock) in
    the new file, its bullets' matched original indices (in `old`, per
    (sid, peer, axis)) must form a strictly increasing sequence, in the
    order those bullets appear in the new file. A first-available FIFO
    queue per (sid, peer, axis, body) assigns each new bullet occurrence
    to the earliest not-yet-consumed old occurrence with the same text;
    bullets with no old counterpart (new/rewritten) are excluded (already
    counted by `added`)."""
    queues: dict[tuple[str, str, str, str], collections.deque] = collections.defaultdict(collections.deque)
    for key, bullets in old.bullets.items():
        sid, peer, axis = key
        for b in bullets:
            queues[(sid, peer, axis, b.body)].append(b.order)

    per_subblock_indices: dict[tuple[str, str, str, str | None], list[int]] = collections.defaultdict(list)
    for key, bullets in new.bullets.items():
        sid, peer, axis = key
        for b in bullets:
            q = queues.get((sid, peer, axis, b.body))
            if q:
                old_idx = q.popleft()
                per_subblock_indices[(sid, peer, axis, b.subblock)].append(old_idx)

    for indices in per_subblock_indices.values():
        for a, c in zip(indices, indices[1:]):
            if c <= a:
                return False
    return True


def check_preamble(old: ParsedFile, new: ParsedFile) -> bool:
    return old.preamble.strip("\n") == new.preamble.strip("\n")


def preamble_diff(old: ParsedFile, new: ParsedFile) -> str:
    """訂正註 1 S-2: `preamble` stays a 2-value identical/differs label
    (a legitimate split rewrites the preamble, design section 6 point 6),
    but when it differs the caller needs to see WHAT differs without
    opening both files by hand -- a unified diff of just the two
    preambles. Empty string when the preambles are identical."""
    old_lines = old.preamble.strip("\n").splitlines(keepends=True)
    new_lines = new.preamble.strip("\n").splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(old_lines, new_lines, fromfile="old preamble", tofile="new preamble", lineterm="\n")
    )


def check_ccr14_rule(old: ParsedFile, new: ParsedFile) -> tuple[bool, bool]:
    return old.ccr14_text == new.ccr14_text, old.rule_text == new.rule_text


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def _evaluate(old: ParsedFile, new: ParsedFile) -> tuple[int, str]:
    """Pure core shared by `check_from_texts` and `main()`: two already-
    parsed files in, (exit code, aggregate line) out."""
    missing, added, _missing_c, _added_c = check_missing_added(old, new)
    moved = check_moved(old, new)
    empty_axis_added, empty_axis_removed = check_empty_axis(old, new)
    subsequence_ok = check_subsequence(old, new)
    preamble_ok = check_preamble(old, new)
    ccr14_ok, rule_ok = check_ccr14_rule(old, new)

    line = (
        f"missing={missing} added={added} moved={moved} "
        f"empty_axis_added={empty_axis_added} empty_axis_removed={empty_axis_removed} "
        f"subsequence={'ok' if subsequence_ok else 'violation'} "
        f"preamble={'identical' if preamble_ok else 'differs'} "
        f"ccr14={'identical' if ccr14_ok else 'differs'} "
        f"rule={'identical' if rule_ok else 'differs'}"
    )
    all_clear = subsequence_ok and ccr14_ok and rule_ok
    return (0 if all_clear else 1), line


def check_from_texts(old_text: str, new_text: str) -> tuple[int, str]:
    """Pure core: old-file text + new-file text in, (exit code, aggregate
    line) out. Split out from `run()` so tests can exercise it directly on
    in-memory fixtures without a git revision or a file on disk."""
    old = ParsedFile(old_text)
    new = ParsedFile(new_text)
    return _evaluate(old, new)


def apply_expect(code: int, line: str, expect: str | None) -> int:
    """訂正註 1 S-2: `--expect "<aggregate line>"` makes the summary-line
    comparison (previously left to the caller reading `missing`/`added`
    by hand) machine-gated -- if `expect` is given and does not match the
    computed `line` verbatim, the exit code becomes 1 regardless of what
    `code` already was. `expect=None` (flag omitted) leaves `code`
    untouched."""
    if expect is not None and line != expect:
        return 1
    return code


def read_old_file(base_rev: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{base_rev}:{CONTROL_MAPPING_REL}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def run(base_rev: str, new_path: Path) -> tuple[int, str]:
    old_text = read_old_file(base_rev)
    new_text = new_path.read_text()
    return check_from_texts(old_text, new_text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="git revision to read the old CONTROL_MAPPING.md from")
    parser.add_argument("--new", default=str(REPO_ROOT / CONTROL_MAPPING_REL), help="path to the new (split) file")
    parser.add_argument(
        "--expect",
        default=None,
        help="expected aggregate line (verbatim); exit 1 if the computed line does not match",
    )
    args = parser.parse_args(argv)
    try:
        old_text = read_old_file(args.base)
        new_text = Path(args.new).read_text()
        old = ParsedFile(old_text)
        new = ParsedFile(new_text)
    except CheckError as exc:
        print(f"check_control_mapping_split: CHECK STOPPED: {exc}", file=sys.stderr)
        return 2
    code, line = _evaluate(old, new)
    print(line)
    if not check_preamble(old, new):
        diff = preamble_diff(old, new)
        if diff:
            print(diff)
    code = apply_expect(code, line, args.expect)
    if args.expect is not None and line != args.expect:
        print(
            f"check_control_mapping_split: --expect MISMATCH\n  got:      {line}\n  expected: {args.expect}",
            file=sys.stderr,
        )
    return code


if __name__ == "__main__":
    sys.exit(main())
