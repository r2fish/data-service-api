#!/usr/bin/env python3
"""ledger.py -- list the open rows of the ledger and check its fixed fields.

Everything about this tool -- the two tables and their columns, the closed
vocabularies, the archive file, the arguments, the output and the exit codes
-- is decided in docs/design/LEDGER_FIXED_FIELDS_V1.md (D-1 to D-3, D-7,
D-8) and is not restated here.

Known gaps (recorded per docs/work-orders/OPERATING_CONDITIONS.md 1.12-71:
a gap that cannot let a contract violation or a Security Invariant breach
through the completion gate is recorded here and not filed in the ledger):
    1. not detected: an extra cell inserted after the mark cell of a
       table-1 row whose shifted values all stay inside their length
       limits (before the start condition, before the title or after the
       title; a repeat of the mark cell is one such case), a spaced
       separator (space, pipe, space) typed inside a
       fixed field, and a ninth column -- the content and destination
       cells are one opaque remainder.
       why: the fixed cells are read by position and the remainder is
       taken whole, because content cells legitimately contain that
       separator.
       measured: on the repository's ledger, deleting or repeating each of
       the five fixed cells of each of the 35 table-1 rows (350 variants)
       left 105 green -- all of them the repeat of the mark, the start
       condition or the title cell; the other 245 (any deletion, and the
       repeat of the state or size cell) were red; inserting one short
       free-text cell into each of the 35 rows was red before the state,
       size and mark cells (0 of 35 green each) and green before the
       start condition, before the title and after the title (35 of 35).
       caught by: reading the diff before the commit, and the --open table
       (the shifted cells show in its columns).
    2. not detected: a row whose content text contradicts its fixed fields
       (a state of "not started" on a row whose content says it closed).
       why: the fixed fields are the current value by rule and the
       content is history; the tool never reads the content.
       caught by: the supervisor's classification at the change set that
       moves a row. --verify-move covered the first move only: it needs a
       base whose section 8 is still the single three-column table
       (bf429d0 or earlier) and is red against any later base.
    3. not detected: a table heading or row inside a code fence in section
       8 (a fenced heading is counted like any other; a fenced row is read
       like any other), and the text of an archive row beyond its closing
       ` |` and the file's final newline, and any text placed before the
       archive's first section (--verify-move compared the rows once, at
       the first move, against the single-table base).
       why: the tool finds tables by their heading line and never parses
       Markdown, and the archive rows are history that is not re-judged.
       caught by: the ledger having no fenced blocks in section 8
       (accepted), and reading the diff of the archive file before the
       commit that closes a row (it must only add lines at the end).
"""
from __future__ import annotations

import argparse
import datetime
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFAULT_LEDGER = REPO / "docs/design/ROADMAP_POST_PHASE7_V1.md"
DEFAULT_ARCHIVE = (
    REPO / "docs/archive/docs/design/ROADMAP_POST_PHASE7_V1__LEDGER_CLOSED.md"
)

EXIT_RED = 1
EXIT_PREREQ = 78

STATES = ("未着手", "進行中", "常設", "閉止", "却下")
OPEN_STATES = ("未着手", "進行中")
STATES_81 = ("未着手", "進行中", "常設")
STATES_82 = ("閉止", "却下")
SIZES = ("S", "M", "L", "-")
MARKS = ("あり", "なし")
MAX_TITLE = 40
MAX_COND = 60

HEADER_81 = "| ID | 状態 | 規模 | 印 | 着手条件 | 件名 | 内容 | 行き先 |"
HEADER_82 = "| ID | 状態 | 閉止日 | 件名 |"

_ROW_ID_RE = re.compile(r"^\| \*\*R-(\d+)\*\* \| ")
_SEPARATOR_RE = re.compile(r"^\|[\s:|-]+\|\s*$")
_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_ARCHIVE_HEADING_RE = re.compile(r"^## R-(\d+)\s*$")
_ID_ARG_RE = re.compile(r"^R-(\d+)$")


class PrereqError(Exception):
    """A precondition failed: unreadable file, no section 8, git unusable."""


class Row:
    """One ledger row; `ok` is true once every fixed field has been read."""

    def __init__(self, id: int, table: str, lineno: int, raw: str) -> None:
        self.id = id
        self.table = table
        self.lineno = lineno
        self.raw = raw
        self.state = ""
        self.size = ""
        self.mark = ""
        self.cond = ""
        self.title = ""
        self.date = ""
        self.rest = ""
        self.ok = False

    def fixed(self) -> list[str]:
        if self.table == "8.1":
            return [self.state, self.size, self.mark, self.cond, self.title]
        return [self.state, self.date, self.title]


class Ledger:
    def __init__(self, path: Path, rows81: list[Row], rows82: list[Row], findings: list[tuple[str, str]]) -> None:
        self.path = path
        self.rows81 = rows81
        self.rows82 = rows82
        self.findings = findings


# --------------------------------------------------------------------------
# reading
# --------------------------------------------------------------------------

def _disp(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO))
    except ValueError:
        return path.name


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise PrereqError(f"cannot read {path.name}: {exc}") from exc


def _table_lines(lines: list[str], heading: str, path: Path) -> list[tuple[int, str]]:
    """The `|` lines of the first table after the line starting with `heading`."""
    start = None
    for i, line in enumerate(lines):
        if line.startswith(heading):
            start = i
            break
    if start is None:
        raise PrereqError(f"{path.name}: no heading starting with {heading!r}")
    out: list[tuple[int, str]] = []
    for j in range(start + 1, len(lines)):
        line = lines[j]
        if line.startswith("|"):
            out.append((j + 1, line))
        elif out or line.startswith("#"):
            break
    return out


def _parse_81(lineno: int, raw: str, rid: int) -> tuple[Row, str | None]:
    row = Row(rid, "8.1", lineno, raw)
    parts = raw.split(" | ", 6)
    if len(parts) < 7 or " | " not in parts[6] or not parts[6].rstrip().endswith("|"):
        return row, "expected five fixed cells then a remainder (content, destination)"
    row.state, row.size, row.mark, row.cond, row.title = parts[1:6]
    row.rest = parts[6]
    if any(not cell.strip() for cell in row.fixed()):
        return row, "an empty fixed cell"
    row.ok = True
    return row, None


def _parse_82(lineno: int, raw: str, rid: int) -> tuple[Row, str | None]:
    row = Row(rid, "8.2", lineno, raw)
    body = raw.rstrip()
    if not (body.startswith("| ") and body.endswith(" |")):
        return row, "row is not delimited by pipes"
    cells = body[2:-2].split(" | ")
    if len(cells) != 4:
        return row, f"expected 4 cells, found {len(cells)}"
    row.state, row.date, row.title = cells[1:4]
    if any(not cell.strip() for cell in row.fixed()):
        return row, "an empty fixed cell"
    row.ok = True
    return row, None


def _parse_table(lines: list[str], heading: str, table: str, path: Path):
    rows: list[Row] = []
    findings: list[tuple[str, str]] = []
    data = _table_lines(lines, heading, path)
    expected = HEADER_81 if table == "8.1" else HEADER_82
    if data and data[0][1] != expected:
        findings.append(("columns", f"{_disp(path)}:{data[0][0]}: table {table} header line is not {expected!r}"))
    if len(data) < 2 or not _SEPARATOR_RE.match(data[1][1]):
        findings.append(("fields", f"{_disp(path)}: table {table} has no header and separator lines"))
        data = data[1:]
    else:
        data = data[2:]
    for lineno, raw in data:
        m = _ROW_ID_RE.match(raw)
        if m is None:
            findings.append(("fields", f"{_disp(path)}:{lineno}: table {table} line has no `**R-N**` ID cell"))
            continue
        rid = int(m.group(1))
        parser = _parse_81 if table == "8.1" else _parse_82
        row, err = parser(lineno, raw, rid)
        if err is not None:
            findings.append(("fields", f"{_disp(path)}:{lineno}: R-{rid}: {err}"))
        rows.append(row)
    return rows, findings


def parse_ledger(path: Path) -> Ledger:
    lines = _read(path).split("\n")
    rows81, f1 = _parse_table(lines, "### 8.1 ", "8.1", path)
    rows82, f2 = _parse_table(lines, "### 8.2 ", "8.2", path)
    findings = f1 + f2
    for heading in ("### 8.1 ", "### 8.2 "):
        n = sum(1 for line in lines if line.startswith(heading))
        if n != 1:
            findings.append(("heading", f"{_disp(path)}: {n} lines start with {heading!r} (exactly one)"))
    start = next((i for i, line in enumerate(lines) if line.startswith("## 8. ")), None)
    if start is None:
        raise PrereqError(f"{path.name}: no heading starting with '## 8. '")
    read = {r.lineno for r in rows81 + rows82}
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("## "):
            break
        if _ROW_ID_RE.match(lines[j]) and j + 1 not in read:
            findings.append(("stray", f"{_disp(path)}:{j + 1}: a `| **R-N** | ` line in section 8 that neither table reads"))
    return Ledger(path, rows81, rows82, findings)


def parse_archive(path: Path):
    """Returns (lines, sections); a section is [id, heading line no., body lines]."""
    lines = _read(path).split("\n")
    sections: list[list] = []
    cur = None
    for i, line in enumerate(lines):
        m = _ARCHIVE_HEADING_RE.match(line)
        if m:
            cur = [int(m.group(1)), i + 1, []]
            sections.append(cur)
        elif line.startswith("## "):
            cur = None
        elif cur is not None:
            cur[2].append(line)
    return lines, sections


# --------------------------------------------------------------------------
# --check
# --------------------------------------------------------------------------

def _in_vocab(value: str, allowed: tuple[str, ...]) -> bool:
    return value in allowed


def _valid_date(value: str) -> bool:
    m = _DATE_RE.match(value)
    if m is None:
        return False
    try:
        datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return False
    return True


def _header_ok(lines: list[str]) -> bool:
    if len(lines) < 3:
        return False
    return all(l.startswith("<!--") and l.rstrip().endswith("-->") for l in lines[:3])


def run_check(ledger: Ledger, archive_lines: list[str], sections: list[list]) -> list[tuple[str, str]]:
    findings = list(ledger.findings)
    where = _disp(ledger.path)
    rows = ledger.rows81 + ledger.rows82
    ok_rows = [r for r in rows if r.ok]

    for r in ledger.rows81:
        if not r.ok:
            continue
        loc = f"{where}:{r.lineno}: R-{r.id}"
        if not _in_vocab(r.state, STATES):
            findings.append(("vocab", f"{loc}: state {r.state!r} is outside the vocabulary"))
        if not _in_vocab(r.size, SIZES):
            findings.append(("vocab", f"{loc}: size {r.size!r} is outside the vocabulary"))
        if not _in_vocab(r.mark, MARKS):
            findings.append(("vocab", f"{loc}: mark {r.mark!r} is outside the vocabulary"))
        if r.size == "-" and r.state != "常設":
            findings.append(("dash", f"{loc}: size '-' is only for a row whose state is 常設"))
    for r in ledger.rows82:
        if r.ok and not _in_vocab(r.state, STATES):
            findings.append(("vocab", f"{where}:{r.lineno}: R-{r.id}: state {r.state!r} is outside the vocabulary"))

    for r in ok_rows:
        allowed = STATES_81 if r.table == "8.1" else STATES_82
        if r.state in STATES and r.state not in allowed:
            findings.append(("table", f"{where}:{r.lineno}: R-{r.id}: state {r.state!r} does not belong in table {r.table}"))

    for r in ledger.rows82:
        if r.ok and not _valid_date(r.date):
            findings.append(("date", f"{where}:{r.lineno}: R-{r.id}: {r.date!r} is not a calendar date YYYY-MM-DD"))

    for r in ok_rows:
        loc = f"{where}:{r.lineno}: R-{r.id}"
        if len(r.title) > MAX_TITLE:
            findings.append(("length", f"{loc}: title is {len(r.title)} characters (max {MAX_TITLE})"))
        if r.table == "8.1" and len(r.cond) > MAX_COND:
            findings.append(("length", f"{loc}: start condition is {len(r.cond)} characters (max {MAX_COND})"))
        if any("|" in cell for cell in r.fixed()):
            findings.append(("pipe", f"{loc}: a fixed field contains a pipe"))

    ids = [r.id for r in rows]
    for rid, n in sorted(Counter(ids).items()):
        if n > 1:
            findings.append(("dup", f"R-{rid} appears {n} times across the two tables"))
    if ids:
        present = set(ids)
        missing = [n for n in range(1, max(ids) + 1) if n not in present]
        if missing:
            findings.append(("gap", "missing IDs: " + ", ".join(f"R-{n}" for n in missing)))
    for table_rows in (ledger.rows81, ledger.rows82):
        for a, b in zip(table_rows, table_rows[1:]):
            if a.id > b.id:
                findings.append(("order", f"{where}:{b.lineno}: R-{b.id} follows R-{a.id} (not ascending)"))

    index_ids = {r.id for r in ledger.rows82}
    arch_ids = [s[0] for s in sections]
    arch_set = set(arch_ids)
    if index_ids != arch_set:
        only_index = sorted(index_ids - arch_set)
        only_arch = sorted(arch_set - index_ids)
        findings.append((
            "index",
            "index and archive differ: only in the index "
            + (", ".join(f"R-{n}" for n in only_index) or "-")
            + "; only in the archive "
            + (", ".join(f"R-{n}" for n in only_arch) or "-"),
        ))
    for rid, n in sorted(Counter(arch_ids).items()):
        if n > 1:
            findings.append(("index", f"the archive has {n} sections for R-{rid}"))

    for sid, hline, body in sections:
        row_lines = [l for l in body if _ROW_ID_RE.match(l)]
        row_ids = [int(_ROW_ID_RE.match(l).group(1)) for l in row_lines]
        if row_ids != [sid]:
            found = ", ".join(f"R-{n}" for n in row_ids) or "none"
            findings.append(("section", f"archive:{hline}: section R-{sid} must hold exactly one `| **R-{sid}** | ` row (found: {found})"))
        for l in row_lines:
            if not l.endswith(" |"):
                findings.append(("row-end", f"archive:{hline}: the R-{sid} row does not end with ` |` (a cut row)"))
    if archive_lines and archive_lines[-1] != "":
        findings.append(("eof", "the archive does not end with a newline (a cut file)"))

    if not _header_ok(archive_lines):
        findings.append(("header", "the archive does not start with three HTML comment header lines"))

    if not rows:
        findings.append(("empty", "no ledger rows were read (a check that observes nothing is red)"))
    return findings


# --------------------------------------------------------------------------
# listing
# --------------------------------------------------------------------------

def _emit(fmt: str, header: list[str], table: list[list[str]]) -> None:
    if fmt == "tsv":
        print("\t".join(header))
        for cells in table:
            print("\t".join(cells))
        return
    print("| " + " | ".join(header) + " |")
    print("|" + "---|" * len(header))
    for cells in table:
        print("| " + " | ".join(cells) + " |")


def _structural(ledger: Ledger) -> bool:
    """Report rows that cannot be read; True when there are any."""
    if not ledger.findings:
        return False
    for tag, msg in ledger.findings:
        print(f"RED [{tag}] {msg}", file=sys.stderr)
    print("ledger: rows cannot be read; run --check", file=sys.stderr)
    return True


def cmd_open(ledger: Ledger, fmt: str) -> int:
    if _structural(ledger):
        return EXIT_RED
    rows = [r for r in ledger.rows81 if r.state in OPEN_STATES]
    rows.sort(key=lambda r: (0 if r.mark == "なし" else 1, r.id))
    header = ["ID", "件名", "規模", "印", "着手条件", "状態"]
    _emit(fmt, header, [[f"R-{r.id}", r.title, r.size, r.mark, r.cond, r.state] for r in rows])
    n_none = sum(1 for r in rows if r.mark == "なし")
    n_mark = sum(1 for r in rows if r.mark == "あり")
    n_todo = sum(1 for r in rows if r.state == "未着手")
    n_doing = sum(1 for r in rows if r.state == "進行中")
    print()
    print(f"open={len(rows)} (印なし={n_none} 印あり={n_mark}; 未着手={n_todo} 進行中={n_doing})")
    return 0


def cmd_all(ledger: Ledger, fmt: str) -> int:
    if _structural(ledger):
        return EXIT_RED
    rows = ledger.rows81 + ledger.rows82
    rows = sorted(rows, key=lambda r: r.id)
    header = ["ID", "状態", "規模", "印", "閉止日", "着手条件", "件名"]
    table = []
    for r in rows:
        if r.table == "8.1":
            table.append([f"R-{r.id}", r.state, r.size, r.mark, "-", r.cond, r.title])
        else:
            table.append([f"R-{r.id}", r.state, "-", "-", r.date, "-", r.title])
    _emit(fmt, header, table)
    counts = Counter(r.state for r in rows)
    print()
    print("all=%d (%s)" % (len(rows), " ".join(f"{s}={counts.get(s, 0)}" for s in STATES)))
    return 0


def cmd_show(ledger: Ledger, archive: Path, rid_text: str) -> int:
    m = _ID_ARG_RE.match(rid_text)
    if m is None:
        print(f"ledger: {rid_text!r} is not of the form R-N", file=sys.stderr)
        return EXIT_RED
    rid = int(m.group(1))
    for r in ledger.rows81:
        if r.id == rid:
            print(r.raw)
            return 0
    _, sections = parse_archive(archive)
    hits = [s for s in sections if s[0] == rid]
    if not hits:
        print(f"ledger: R-{rid} is in neither table 8.1 nor the archive", file=sys.stderr)
        return EXIT_RED
    for _, _, body in hits:
        for line in [ln for ln in body if ln.strip()]:
            print(line)
    return 0


# --------------------------------------------------------------------------
# --verify-move
# --------------------------------------------------------------------------

def _git(args: list[str]) -> str:
    try:
        proc = subprocess.run(["git", *args], capture_output=True, check=False)
    except OSError as exc:
        raise PrereqError(f"git cannot be run: {exc}") from exc
    if proc.returncode != 0:
        raise PrereqError("git " + " ".join(args[:3]) + " failed: " + proc.stderr.decode("utf-8", "replace").strip())
    return proc.stdout.decode("utf-8")


def _base_rows(ledger_path: Path, rev: str) -> dict[int, str]:
    if rev.startswith("-"):
        raise PrereqError(f"{rev!r} is not a revision")
    top = Path(_git(["-C", str(ledger_path.parent), "rev-parse", "--show-toplevel"]).strip())
    try:
        rel = ledger_path.resolve().relative_to(top.resolve())
    except ValueError as exc:
        raise PrereqError("the ledger is not inside the git work tree") from exc
    text = _git(["-C", str(top), "show", f"{rev}:{rel.as_posix()}"])
    lines = text.split("\n")
    start = next((i for i, l in enumerate(lines) if l.startswith("## 8. ")), None)
    if start is None:
        raise PrereqError(f"no `## 8. ` section in {rev}")
    rows: dict[int, str] = {}
    for line in lines[start + 1:]:
        if line.startswith("## "):
            break
        m = _ROW_ID_RE.match(line)
        if m and int(m.group(1)) not in rows:
            rows[int(m.group(1))] = line
    return rows


def cmd_verify_move(ledger: Ledger, archive: Path, rev: str) -> int:
    base = _base_rows(ledger.path, rev)
    if not base:
        raise PrereqError(f"no ledger rows found in section 8 of {rev}")
    arch_lines, sections = parse_archive(archive)
    arch_rows: dict[int, str] = {}
    for line in arch_lines:
        m = _ROW_ID_RE.match(line)
        if m:
            arch_rows.setdefault(int(m.group(1)), line)
    findings: list[tuple[str, str]] = run_check(ledger, arch_lines, sections)
    for rid, line in sorted(arch_rows.items()):
        if rid in base and line != base[rid]:
            findings.append(("moved-row", f"archive row R-{rid} differs from the base row"))
    for r in ledger.rows81:
        if r.ok and r.id in base:
            base_rest = base[r.id][len(f"| **R-{r.id}** | "):]
            if r.rest != base_rest:
                findings.append(("kept-rest", f"table 8.1 row R-{r.id}: content/destination differ from the base row"))
    current = set(arch_rows) | {r.id for r in ledger.rows81}
    lost = sorted(set(base) - current)
    if lost:
        findings.append(("lost-id", "in the base but in neither the archive nor table 8.1: " + ", ".join(f"R-{n}" for n in lost)))
    new = len(current - set(base))
    for tag, msg in findings:
        print(f"RED [{tag}] {msg}")
    if findings:
        print(f"ledger --verify-move {rev}: RED findings={len(findings)} new_ids={new}")
        return EXIT_RED
    print(f"ledger --verify-move {rev}: GREEN base_ids={len(base)} archive_rows={len(arch_rows)} new_ids={new}")
    return 0


# --------------------------------------------------------------------------
# entry
# --------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="ledger.py", description="see docs/design/LEDGER_FIXED_FIELDS_V1.md")
    ap.add_argument("ledger", nargs="?", type=Path, default=DEFAULT_LEDGER)
    ap.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    ap.add_argument("--format", choices=("md", "tsv"), default="md")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--open", action="store_true")
    mode.add_argument("--all", action="store_true")
    mode.add_argument("--show", metavar="R-N")
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--verify-move", metavar="BASE_REV")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        ledger = parse_ledger(args.ledger)
        if args.open:
            return cmd_open(ledger, args.format)
        if args.all:
            return cmd_all(ledger, args.format)
        if args.show is not None:
            return cmd_show(ledger, args.archive, args.show)
        if args.verify_move is not None:
            return cmd_verify_move(ledger, args.archive, args.verify_move)
        lines, sections = parse_archive(args.archive)
        findings = run_check(ledger, lines, sections)
    except PrereqError as exc:
        print(f"ledger: precondition error: {exc}", file=sys.stderr)
        return EXIT_PREREQ
    for tag, msg in findings:
        print(f"RED [{tag}] {msg}")
    counts = f"rows(8.1)={len(ledger.rows81)} rows(8.2)={len(ledger.rows82)} archive_sections={len(sections)}"
    if findings:
        print(f"ledger --check: RED findings={len(findings)} {counts}")
        return EXIT_RED
    print(f"ledger --check: GREEN {counts}")
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    sys.exit(main())
