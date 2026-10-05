"""repull.py -- re-pull `file:line` references that moved with comment-only edits.

usage: repull.py [--dry-run] BASE DOC -- SRC [SRC ...]      (cwd = the worktree root)

BASE must be the commit the working tree is based on: DOC at HEAD and DOC at
BASE must be the same text (exit 2 otherwise), so every difference between
BASE's DOC and the working tree's DOC is this change set's own.

For every line of DOC as it is at BASE, walks the position references in order:
a path-shaped token (optionally followed by `:N` / `:N-M`, the colon inside or
just outside the closing backtick) names the current file; a bare `:N` / `:N-M`
whose preceding character is not alphanumeric inherits the nearest earlier path
on the same line. A reference into one of SRC is rewritten to the line that
holds the same text now (difflib over BASE's SRC and the working tree's SRC).
A cited line that no longer exists unchanged is reported as `unresolved` and
left alone (exit 1). References into other files are never rewritten.

Writing: a working-tree line is replaced by its rewritten BASE line where the
two are equal once every line number of a reference into SRC is masked -- so
the BASE line itself, the rewritten line, and a line an earlier run re-pulled
against an earlier edit of SRC are all brought to the rewritten line, and a
second run changes nothing. A BASE line whose reference moved but which has no
such working-tree line is reported as `not applied` (exit 1) and left alone.
Lines the working tree added (a new version line) and every other edit of a
line are kept.
"""
import difflib
import re
import subprocess
import sys
from pathlib import Path

args = sys.argv[1:]
dry = bool(args) and args[0] == "--dry-run"
if dry:
    args = args[1:]
base, doc = args[0], args[1]
srcs = args[args.index("--") + 1:]


def show(rev, path):
    return subprocess.run(["git", "show", f"{rev}:{path}"], capture_output=True, text=True, check=True).stdout


if show("HEAD", doc) != show(base, doc):
    print(f"repull: {doc} differs between HEAD and {base}; pass the commit this working tree is based on")
    sys.exit(2)
maps = {}
for p in srcs:
    o = show(base, p).splitlines()
    n = Path(p).read_text().splitlines()
    m = {}
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, o, n, autojunk=False).get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                m[i1 + k + 1] = j1 + k + 1
    maps[p] = m
EXT = r"(?:py|md|sql|json|toml|yaml|yml|sh|txt|conf|tsv|cfg|ini)"
TOKEN = re.compile(
    rf"(?P<path>(?<![A-Za-z0-9_./-])(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.{EXT})(?![A-Za-z0-9_/])(?P<q>`?)(?::(?P<a>\d+)(?:-(?P<b>\d+))?)?"
    rf"|(?<![A-Za-z0-9])(?P<bq>`?):(?P<ca>\d+)(?:-(?P<cb>\d+))?(?![A-Za-z0-9])"
)


def owner(path):
    hits = [s for s in srcs if s == path or s.endswith("/" + path)]
    return hits[0] if len(hits) == 1 else None


changed = 0
unresolved = []


def fix_line(line, lineno, mask=False):
    cur = None

    def rep(mm):
        global changed
        nonlocal cur
        if mm.group("path"):
            cur = owner(mm.group("path"))
            a, b, head = mm.group("a"), mm.group("b"), mm.group("path") + mm.group("q")
        else:
            a, b, head = mm.group("ca"), mm.group("cb"), mm.group("bq")
        if cur is None or a is None:
            return mm.group(0)
        if mask:
            return f"{head}:#"
        m = maps[cur]
        ia = int(a)
        ib = int(b) if b else None
        if ia not in m or (ib is not None and ib not in m):
            unresolved.append(f"{doc}:{lineno}: {mm.group(0)}")
            return mm.group(0)
        na, nb = m[ia], (m[ib] if ib is not None else None)
        if (na, nb) == (ia, ib):
            return mm.group(0)
        changed += 1
        print(f"{doc}:{lineno}: {Path(cur).name} :{a}{'-' + b if b else ''} -> :{na}{'-' + str(nb) if nb else ''}")
        return f"{head}:{na}" + (f"-{nb}" if nb is not None else "")

    return TOKEN.sub(rep, line)


base_doc = show(base, doc).splitlines(keepends=True)
out = [fix_line(line, i + 1) for i, line in enumerate(base_doc)]
cur_lines = Path(doc).read_text().splitlines(keepends=True)
res = list(cur_lines)
moved = {i for i in range(len(base_doc)) if out[i] != base_doc[i]}
done = set()
masked_base = [fix_line(line, 0, mask=True) for line in base_doc]
masked_cur = [fix_line(line, 0, mask=True) for line in cur_lines]
sm = difflib.SequenceMatcher(None, masked_base, masked_cur, autojunk=False)
for tag, i1, i2, j1, j2 in sm.get_opcodes():
    if tag == "equal":
        for k in range(i2 - i1):
            if masked_base[i1 + k] != base_doc[i1 + k]:  # the line cites SRC by line number
                done.add(i1 + k)
                res[j1 + k] = out[i1 + k]  # also brings back a line an earlier run moved further
not_applied = [f"{doc}:{i + 1}" for i in sorted(moved - done)]
print(f"{doc}: changed {changed}, unresolved {len(unresolved)}, not applied {len(not_applied)}")
for u in unresolved:
    print("unresolved", u)
for u in not_applied:
    print("not applied (no working-tree line equals this base line with its SRC line numbers masked)", u)
if not dry:
    Path(doc).write_text("".join(res))
sys.exit(1 if unresolved or not_applied else 0)
