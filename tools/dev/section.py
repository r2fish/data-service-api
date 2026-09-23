#!/usr/bin/env python3
"""section.py -- print only the Markdown sections you need.

Replaces paging through long design documents and work orders with
`sed -n` / repeated reads.

Usage:
    tools/dev/section.py FILE --list [--depth N]   # outline with line numbers
    tools/dev/section.py FILE PATTERN [PATTERN ...] [-n]

A PATTERN is a regular expression searched in heading text (without the
leading #). Each matching section is printed from its heading up to the next
heading of the same or a higher level. Headings inside ``` fences are
ignored. -n prefixes line numbers.
Exit: 0; 1 when a PATTERN matches no heading.

Known gaps (recorded per docs/work-orders/OPERATING_CONDITIONS.md 1.12-71:
a gap that cannot let a contract violation or a Security Invariant breach
through the completion gate is recorded here and not filed in the ledger):
    1. not detected: a setext heading (a title underlined with `===` or
       `---`) -- it is neither listed nor printed as a section.
       why: `_HEADING_RE` matches ATX headings (`#` to `######`) only.
       caught by: accepted -- the documents here use ATX headings, and a
       heading missing from `--list` is the visible symptom.
    2. not detected: a fence opened with MORE than three markers -- it
       is treated as a 3-marker fence, so a nested ``` inside it toggles
       the state again.
       why: the fence marker compared is `stripped[:3]`.
       caught by: reading the printed section (accepted).
    3. not detected: a `#` line inside an indented (4-space) code block
       -- it is reported as a heading.
       why: only fenced blocks are skipped.
       caught by: reading the printed outline (accepted).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")


def headings(lines: list[str]) -> list[tuple[int, int, str]]:
    """(index, level, text) for every heading outside code fences."""
    found, fence = [], None
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            marker = stripped[:3]
            fence = None if fence == marker else (fence or marker)
            continue
        if fence is None:
            m = _HEADING_RE.match(line)
            if m:
                found.append((i, len(m.group(1)), m.group(2)))
    return found


def sections(lines: list[str], pattern: str) -> list[tuple[int, int]]:
    hs = headings(lines)
    rx = re.compile(pattern)
    spans = []
    for k, (i, level, text) in enumerate(hs):
        if rx.search(text):
            end = next((j for j, lv, _ in hs[k + 1:] if lv <= level), len(lines))
            spans.append((i, end))
    return spans


def main(argv: list[str] | None = None, out=sys.stdout) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("file")
    parser.add_argument("patterns", nargs="*")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--depth", type=int, default=6)
    parser.add_argument("-n", dest="numbers", action="store_true")
    ns = parser.parse_args(argv)
    lines = Path(ns.file).read_text(encoding="utf-8").splitlines()
    if ns.list or not ns.patterns:
        for i, level, text in headings(lines):
            if level <= ns.depth:
                print(f"{i + 1:>6}  {'#' * level} {text}", file=out)
        return 0
    status = 0
    for pattern in ns.patterns:
        spans = sections(lines, pattern)
        if not spans:
            print(f"section: no heading matches {pattern!r}", file=sys.stderr)
            status = 1
        for start, end in spans:
            for i in range(start, end):
                print(f"{i + 1:>6}  {lines[i]}" if ns.numbers else lines[i], file=out)
    return status


if __name__ == "__main__":
    sys.exit(main())
