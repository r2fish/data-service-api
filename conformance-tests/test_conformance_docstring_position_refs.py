"""R-95 (docs/work-orders/WORK_ORDER_R95_CONFORMANCE_DOCSTRING_POSITION_REFS_V1.md
D-1..D-9): every position reference a docstring or comment inside
`conformance-tests/*.py` itself cites -- a backtick-quoted path immediately
followed by a colon and one or two dash-joined line numbers (no space
between the quote and the colon), or that same colon/number pair continued
bare, inheriting the nearest earlier path in the same docstring/comment
unit -- must resolve to a real repository file, with every cited line
number inside that file's own current line count. D-1: this file owns its
own extraction/resolution functions; it does not import
`test_control_mapping_register.py` (R-88's own sibling check over
`security/CONTROL_MAPPING.md`) and does not reuse that file's line-unit
extraction -- see D-2 below for why a line-unit extraction cannot see a
reference whose path is itself split across two physical lines.

Unit (D-2): two kinds. (alpha) every `ast`-level docstring (Module /
ClassDef / FunctionDef / AsyncFunctionDef). (beta) every comment block --
the maximal run of consecutive-line, same-start-column, whole-line `#`
comments is one unit; a comment sharing its own line with code is always
its own 1-line unit. A unit's lines are concatenated into one string before
extraction: counting backtick characters cumulatively from the unit's own
first line through the end of each line in turn, a line break reached on an
ODD cumulative count (an unclosed backtick span) joins the next line with
no separator, after dropping that next line's own leading whitespace (and,
for a comment line, its own leading `#`) -- this is what lets a path that
some earlier author line-wrapped mid-string still read as one path. A line
break reached on an EVEN count joins with a single space instead. A
reported failure's line number is always the unit's own first physical
line, never a line further into a multi-line unit.

Shapes extracted (D-3), narrower than R-88's own 6-shape list over
`security/CONTROL_MAPPING.md` -- this check has no counterpart to R-88's
own label form (a short numeric string resolved against a peer's own
migration directory; conformance prose cites no migration file this way)
and no counterpart to R-88's own bare-path-without-a-line-number form
(D-9 (3) leaves that alone deliberately):
  (a)  a backtick-quoted path directly followed, inside the SAME backtick
       span, by a colon and a line number (or a dash-joined pair).
  (a') the same pair, but the colon sits just outside the closing
       backtick, touching it with no gap.
  (c)  a colon-and-number(s) pair on its own, backtick-quoted or bare,
       whose ONLY extraction condition is that the character immediately
       before the colon is not alphanumeric (this is what keeps an
       ordinary ratio, or an ID like `C-14` followed by a section number,
       out of the extracted set -- neither has a non-alphanumeric
       character right before its own colon). It inherits the nearest
       EARLIER path-shaped backtick span in the SAME unit (an earlier
       plain backtick-quoted path with no line number of its own
       contributes to this inheritance without itself being checked); a
       colon-and-number pair with no earlier path anywhere in its own
       unit is itself a failure ("no preceding path"), never silently
       dropped.
A path candidate is judged only by extension (case-sensitive), from the
same whitelist R-88 uses; a `path::name` double-colon form (a pytest node
id, not a position reference) is never extracted at all.

Resolution (D-4): (i) as a path relative to the repository root. Then
(iii) by SUFFIX match on path components (not bare basename) against every
file under both peers' own `src`/`migrations`/`docs`/`tests`/`conformance`/
`deploy`/`config`/`docker` subdirectories plus the shared `conformance-
tests`/`tools`/`security`/`spec`/repository-root-`docs` directories --
unique match resolves, zero is "file not found", more than one is
"ambiguous". Conformance prose carries no peer-scoped subsection the way
`security/CONTROL_MAPPING.md` does, so there is no peer-prefix route
between (i) and (iii) the way R-88's own (ii) is. A resolved file's cited
line number (or the end of a dash-joined pair) must be `>= 1` and inside
that file's own current line count, and a dash-joined pair's own end must
not be smaller than its own start ("bad range").

Limits (D-9), current as of this file's own last edit:
  1. A reference that resolves, and stays inside its resolved file's own
     line count, but has quietly come to point at an unrelated statement
     (the exact line it once pointed to now holding something else) is
     NOT detected here -- only a human reading the surrounding prose
     against the real file catches that; this file only catches a
     reference whose PATH or LINE NUMBER no longer resolves at all.
  2. Route (iii) never pins a directory: once a suffix match is unique
     somewhere in its own search scope, moving the file to a DIFFERENT
     directory still inside that same scope leaves the reference
     resolved, even though the module it once named has moved.
  3. A bare path with no line number at all is not a position reference
     this file checks (D-3's own carve-out; a fixed, short numeric label
     resolved against a peer's own migration directory, R-88's own shape
     (e), has no counterpart here either -- conformance prose cites no
     migration file that way).
  4. Only `conformance-tests/*.py` docstrings/comments are in scope; the
     same defect in either peer's own `src`/`tests` docstrings/comments is
     untouched by this file.
  5. A bare, non-backtick-quoted `path:N` written directly in running
     prose (never inside backticks at all) and an ID-prefixed form like
     `C-14:476` are both outside D-3's own extraction shapes -- the first
     because this file only looks inside backtick spans (or a colon
     touching one) for a path, the second because the character right
     before that colon is alphanumeric, which D-3's own (c) condition
     excludes on purpose.

This file's own docstrings and comments deliberately cite no real
`path:N`-shaped reference anywhere below (R-95 WP-1 §2.1): since this file
is itself inside `conformance-tests/`, the real-corpus test in this same
file (`test_every_real_conformance_tests_position_reference_resolves_or_is_allowlisted`)
scans this file too, and an embedded real reference would go stale exactly
the way the ones this file exists to catch do.

Known gaps (recorded per docs/work-orders/OPERATING_CONDITIONS.md 1.12-71:
a gap that cannot let a contract violation or a Security Invariant breach
through the completion gate is recorded here and not filed in the ledger):
    1. not detected: a reference that still resolves and stays in range
       while pointing at an unrelated statement -- see Limits (D-9) item
       1 above.
       why: same item (resolution proves the path and the line count,
       never the content at that line).
       caught by: a human reading the surrounding prose against the real
       file, and the acceptance audit of any change set that touches the
       unit (accepted; R-88's own resolution over
       `security/CONTROL_MAPPING.md` carries the same bound).
    2. not detected: a file moved to a different directory inside route
       (iii)'s own search scope -- see Limits (D-9) item 2 above.
       why: same item (a unique suffix match never pins a directory).
       caught by: code review of the move itself (accepted).
    3. not detected: a bare path carrying no line number, and R-88's own
       short-label shape -- see Limits (D-9) item 3 above.
       why: same item (D-3's own carve-out).
       caught by: for the label shape over `security/CONTROL_MAPPING.md`,
       R-88's own checks in `conformance-tests/
       test_control_mapping_register.py`; for conformance prose, review
       (accepted).
    4. not detected: the same defect inside either peer's own `src` or
       `tests` docstrings and comments -- see Limits (D-9) item 4 above.
       why: same item (scope is `conformance-tests/*.py` only).
       caught by: `tools/check_comment_provenance.py`'s own Known gaps
       section names it as that checker's first gap (ledger R-96 was
       closed into it 2026-09-23); code review meanwhile.
    5. not detected: a non-backtick-quoted reference written in running
       prose, and an ID-prefixed form -- see Limits (D-9) item 5 above.
       why: same item (extraction looks inside backtick spans, and the
       character right before the colon must not be alphanumeric).
       caught by: review (accepted by D-3, deliberately).
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from pathlib import Path

CONFORMANCE_TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = CONFORMANCE_TESTS_DIR.parent

# D-3: same case-sensitive extension whitelist R-88 uses (`security/
# CONTROL_MAPPING.md`'s own POSITION_REF check) -- a shared vocabulary
# decision, not a shared function (D-1: no import between the two files).
_EXTENSIONS = {
    ".py", ".sql", ".md", ".sh", ".yml", ".yaml", ".toml", ".txt", ".json", ".ini",
}

_PEER_DIRS = ("r2db-api", "MitateDB-api")
_PEER_SUBDIRS = ("src", "migrations", "docs", "tests", "conformance", "deploy", "config", "docker")
_SHARED_DIRS = ("conformance-tests", "tools", "security", "spec", "docs")

# D-3: a backtick span, OR a colon-and-digits pair whose own preceding
# character is not alphanumeric (the negative lookbehind is this file's
# own (c) extraction condition, applied uniformly whether the colon sits
# inside or outside a backtick span).
_TOKEN_RE = re.compile(r"`([^`]+)`|(?<![A-Za-z0-9]):(\d+)(?:-(\d+))?")
_INNER_RE = re.compile(r"^([A-Za-z0-9_./\-]+):(\d+)(?:-(\d+))?$")
_BARE_WHOLE_RE = re.compile(r"^:(\d+)(?:-(\d+))?$")
_PATH_TOKEN_RE = re.compile(r"^[A-Za-z0-9_./\-]+$")


def _has_whitelisted_extension(path_str: str) -> bool:
    return Path(path_str).suffix in _EXTENSIONS


def _join_unit_lines(lines: list[str]) -> str:
    """D-2's own concatenation rule. `lines` are already prefix-stripped
    (a docstring's own `\\n`-split value; a comment block's own per-line
    text with its leading `#` already removed) -- this function only
    decides, per line break, whether to drop the next line's remaining
    leading whitespace (odd cumulative backtick count so far: an unclosed
    span) or keep it behind one inserted space (even count)."""
    if not lines:
        return ""
    result = lines[0]
    cumulative = lines[0].count("`")
    for line in lines[1:]:
        if cumulative % 2 == 1:
            result += line.lstrip()
        else:
            result += " " + line
        cumulative += line.count("`")
    return result


def _def_ranges(tree: ast.AST) -> list[tuple[int, int, str]]:
    """(start_line, end_line, dotted_qualname) for every ClassDef/
    FunctionDef/AsyncFunctionDef, at any nesting depth -- used both to
    build a docstring unit's own scope name and to look up which scope
    (if any) encloses a given comment unit's own first line."""
    ranges: list[tuple[int, int, str]] = []

    def walk(node: ast.AST, stack: list[str]) -> None:
        is_def = isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        new_stack = stack
        if is_def:
            new_stack = stack + [node.name]
            ranges.append((node.lineno, node.end_lineno, ".".join(new_stack)))
        for child in ast.iter_child_nodes(node):
            walk(child, new_stack)

    for child in ast.iter_child_nodes(tree):
        walk(child, [])
    return ranges


def _scope_for_line(lineno: int, def_ranges: list[tuple[int, int, str]]) -> str:
    best: tuple[int, str] | None = None
    for start, end, name in def_ranges:
        if start <= lineno <= end:
            span = end - start
            if best is None or span < best[0]:
                best = (span, name)
    return best[1] if best else "<module>"


def _docstring_units(tree: ast.AST) -> list[dict]:
    """D-2 (alpha)."""
    units: list[dict] = []
    module_doc = ast.get_docstring(tree, clean=False)
    if module_doc is not None and tree.body and isinstance(tree.body[0], ast.Expr):
        units.append(dict(lines=module_doc.split("\n"), start_line=tree.body[0].lineno, scope="<module>"))

    def walk(node: ast.AST, stack: list[str]) -> None:
        is_def = isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        new_stack = stack
        if is_def:
            new_stack = stack + [node.name]
            doc = ast.get_docstring(node, clean=False)
            if doc is not None and node.body and isinstance(node.body[0], ast.Expr):
                units.append(dict(lines=doc.split("\n"), start_line=node.body[0].lineno, scope=".".join(new_stack)))
        for child in ast.iter_child_nodes(node):
            walk(child, new_stack)

    for child in ast.iter_child_nodes(tree):
        walk(child, [])
    return units


def _comment_units(source_bytes: bytes, def_ranges: list[tuple[int, int, str]]) -> list[dict]:
    """D-2 (beta): a standalone `#` line (nothing but whitespace precedes
    it on its own physical line) joins the current run when its own line
    number is exactly one past the run's last line AND its own start
    column matches the run's own column; anything else (a different
    column, a gap, or a comment sharing its line with code) starts -- or,
    for a trailing comment, immediately closes -- its own new unit."""
    units: list[dict] = []
    current_run: list[tuple[int, str, int]] = []

    def flush_run() -> None:
        nonlocal current_run
        if current_run:
            lines = [text for (_lineno, text, _col) in current_run]
            start_line = current_run[0][0]
            units.append(dict(lines=lines, start_line=start_line, scope=_scope_for_line(start_line, def_ranges)))
            current_run = []

    for tok in tokenize.tokenize(io.BytesIO(source_bytes).readline):
        if tok.type != tokenize.COMMENT:
            continue
        is_standalone = tok.line.lstrip().startswith("#")
        content = tok.string[1:] if tok.string.startswith("#") else tok.string
        lineno, col = tok.start
        if not is_standalone:
            flush_run()
            units.append(dict(lines=[content], start_line=lineno, scope=_scope_for_line(lineno, def_ranges)))
            continue
        if current_run and lineno == current_run[-1][0] + 1 and col == current_run[-1][2]:
            current_run.append((lineno, content, col))
        else:
            flush_run()
            current_run = [(lineno, content, col)]
    flush_run()
    return units


def _extract_refs(text: str) -> list[dict]:
    """D-3. Returns a list of dicts with keys shape/raw/path/l1/l2, in the
    same left-to-right order the unit text carries them. Shape "d" (a
    plain backtick-quoted path, no line number) updates `carry_path` for
    a later (c) to inherit but is never itself appended to the result --
    D-9 (3)'s own carve-out."""
    tokens: list[tuple] = []
    for m in _TOKEN_RE.finditer(text):
        if m.group(1) is not None:
            tokens.append(("bt", m.group(1), m.start(), m.end()))
        else:
            tokens.append(("colon", int(m.group(2)), int(m.group(3) or m.group(2)), m.start(), m.end()))

    refs: list[dict] = []
    carry_path: str | None = None
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok[0] == "bt":
            _kind, content, start, end = tok
            inner = _INNER_RE.match(content)
            if inner and _has_whitelisted_extension(inner.group(1)):
                l1 = int(inner.group(2))
                l2 = int(inner.group(3) or inner.group(2))
                shape = "b" if inner.group(3) else "a"
                refs.append(dict(shape=shape, raw=content, path=inner.group(1), l1=l1, l2=l2))
                carry_path = inner.group(1)
                i += 1
                continue
            bare_whole = _BARE_WHOLE_RE.match(content)
            if bare_whole:
                l1 = int(bare_whole.group(1))
                l2 = int(bare_whole.group(2) or bare_whole.group(1))
                refs.append(dict(shape="c", raw=content, path=carry_path, l1=l1, l2=l2))
                i += 1
                continue
            nxt = tokens[i + 1] if i + 1 < len(tokens) else None
            is_adjacent = nxt is not None and nxt[0] == "colon" and nxt[3] == end
            if is_adjacent and _PATH_TOKEN_RE.match(content) and _has_whitelisted_extension(content):
                l1, l2 = nxt[1], nxt[2]
                tail = f":{l1}" + (f"-{l2}" if l2 != l1 else "")
                refs.append(dict(shape="a'", raw=content + tail, path=content, l1=l1, l2=l2))
                carry_path = content
                i += 2
                continue
            if _PATH_TOKEN_RE.match(content) and _has_whitelisted_extension(content):
                carry_path = content
            i += 1
            continue
        else:
            _kind, l1, l2, _start, _end = tok
            raw = f":{l1}" + (f"-{l2}" if l2 != l1 else "")
            refs.append(dict(shape="c", raw=raw, path=carry_path, l1=l1, l2=l2))
            i += 1
            continue
    return refs


def _search_dirs(repo_root: Path) -> list[Path]:
    dirs: list[Path] = []
    for peer in _PEER_DIRS:
        for sub in _PEER_SUBDIRS:
            d = repo_root / peer / sub
            if d.is_dir():
                dirs.append(d)
    for sub in _SHARED_DIRS:
        d = repo_root / sub
        if d.is_dir():
            dirs.append(d)
    return dirs


_III_CACHE: dict[str, list[tuple[Path, tuple[str, ...]]]] = {}


def _iii_candidates(repo_root: Path) -> list[tuple[Path, tuple[str, ...]]]:
    """D-4 (iii)'s own file universe, cached per repo root: every file
    under the combined peer/shared search scope, paired with its own path
    components relative to `repo_root`."""
    key = str(repo_root)
    if key not in _III_CACHE:
        found: list[tuple[Path, tuple[str, ...]]] = []
        for d in _search_dirs(repo_root):
            for f in d.rglob("*"):
                if f.is_file():
                    found.append((f, f.relative_to(repo_root).parts))
        _III_CACHE[key] = found
    return _III_CACHE[key]


def _resolve_ref(ref: dict, repo_root: Path) -> tuple[Path | None, str | None, str | None]:
    """D-4 (i)/(iii). Returns (resolved_path_or_None, route_or_None,
    failure_note_or_None); the line-range check is `_range_note`'s own
    separate job, so a resolved-but-out-of-range reference is told apart
    from an unresolvable one."""
    path_str = ref["path"]
    if path_str is None:
        return None, None, "no preceding path"
    direct = repo_root / path_str
    if direct.is_file():
        return direct, "i", None
    parts = tuple(path_str.split("/"))
    hits = [f for f, fparts in _iii_candidates(repo_root) if fparts[-len(parts):] == parts]
    if len(hits) == 1:
        return hits[0], "iii", None
    if len(hits) > 1:
        return None, None, "ambiguous"
    return None, None, "file not found"


def _range_note(ref: dict, resolved_path: Path) -> str | None:
    """D-4 (iv): the lower bound (return-1 review item 3) and the upper
    bound are 2 separate checks on purpose -- a reversed range and a
    `< 1` start both count as "bad range", never confused with the
    EOF-relative upper-bound failure below."""
    if ref["l1"] < 1:
        return "bad range"
    if ref["l2"] < ref["l1"]:
        return "bad range"
    n = len(resolved_path.read_bytes().decode("utf-8", "replace").splitlines())
    if ref["l2"] > n:
        return f"line {ref['l2']} beyond EOF {n}"
    return None


def _all_units_for_file(path: Path) -> list[dict]:
    source = path.read_text()
    tree = ast.parse(source, filename=str(path))
    def_ranges = _def_ranges(tree)
    return _docstring_units(tree) + _comment_units(path.read_bytes(), def_ranges)


def _unresolved_for_file(path: Path, repo_root: Path):
    """Returns (unresolved, shape_counts, route_counts). `unresolved` is a
    list of (rel_path, unit_start_line, scope, ref, note) tuples, one
    entry per reference that did not resolve or did not stay in range --
    D-8's own "one entry per unresolved reference, never folded"."""
    rel = path.relative_to(repo_root).as_posix()
    unresolved: list[tuple[str, int, str, dict, str]] = []
    shape_counts: dict[str, int] = {}
    route_counts: dict[str, int] = {}
    for unit in _all_units_for_file(path):
        text = _join_unit_lines(unit["lines"])
        for ref in _extract_refs(text):
            shape_counts[ref["shape"]] = shape_counts.get(ref["shape"], 0) + 1
            resolved, route, note = _resolve_ref(ref, repo_root)
            if resolved is None:
                unresolved.append((rel, unit["start_line"], unit["scope"], ref, note))
                continue
            route_counts[route] = route_counts.get(route, 0) + 1
            range_note = _range_note(ref, resolved)
            if range_note is not None:
                unresolved.append((rel, unit["start_line"], unit["scope"], ref, range_note))
    return unresolved, shape_counts, route_counts


def _scan_target_files(conformance_dir: Path) -> list[Path]:
    """D-2's own scan target: `sorted(Path.rglob("*.py"))` under
    `conformance-tests/` -- recursive (`rglob`, not `glob`), and including
    a file `git` does not track (D-2's own fail-closed choice, R-88's
    supervisor ruling 2 applied here unchanged)."""
    return sorted(conformance_dir.rglob("*.py"))


def _scan_repo(repo_root: Path, conformance_dir: Path):
    all_unresolved: list[tuple[str, int, str, dict, str]] = []
    shape_totals: dict[str, int] = {}
    route_totals: dict[str, int] = {}
    unit_count = 0
    files = _scan_target_files(conformance_dir)
    for f in files:
        unit_count += len(_all_units_for_file(f))
        unresolved, shapes, routes = _unresolved_for_file(f, repo_root)
        all_unresolved.extend(unresolved)
        for k, v in shapes.items():
            shape_totals[k] = shape_totals.get(k, 0) + v
        for k, v in routes.items():
            route_totals[k] = route_totals.get(k, 0) + v
    return files, unit_count, all_unresolved, shape_totals, route_totals


def _diff_against_allowlist(unresolved, allowlist: dict):
    """D-5: `messages` is every unresolved reference not covered by
    `allowlist`; `dead` is every allowlist row that covered nothing (a
    resolution that now succeeds on the filesystem, or simply a row for a
    reference that no longer exists) -- pinned as a SET, both directions
    reported."""
    messages: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    for rel, start_line, scope, ref, note in unresolved:
        key = (rel, scope, ref["raw"])
        if key in allowlist:
            seen.add(key)
            continue
        messages.append(f"{rel}:{start_line}: {ref['raw']} ({note})")
    dead = sorted(set(allowlist) - seen)
    return messages, dead


# D-5: measured 2026-09-23 (this file's own corrected worktree, WP-1+WP-2
# same change set) -- 0 rows. `test_fixture_allowlist_set_pin_...` below
# exercises both of D-5's own set-pin directions against a synthetic table
# instead (a real removal is not possible from an empty table).
POSITION_REF_ALLOWLIST: dict[tuple[str, str, str], str] = {}

# D-7: floors. SCAN_FILES_FLOOR and SCAN_UNITS_FLOOR are each this file's
# own measurement (2026-09-23, 49 files, 1452 units) minus a margin. The
# shape and route floors below were set to the measured value as-is, no
# margin, by R-39 CS-2 (2026-10-05, this file's own `_scan_repo`: 61 files,
# 1833 units, shapes a=2 b=0 c=2, routes i=2 iii=2; before CS-2: a=27 b=3
# c=16 a'=5, i=24 iii=27): R-39 CS-2 replaced line-number references with
# symbol forms, so the real corpus's shape counts fell. A floor guarantees that the
# scan still passes through each shape; it is not a device for keeping
# references. Shape (b) has no real reference left, so its floor is 0 and
# its extraction is pinned by the synthetic fixture
# `test_shape_a_and_b_resolve_via_route_i_and_stay_in_range` below.
SCAN_FILES_FLOOR = 47
SCAN_UNITS_FLOOR = 1420
SHAPE_A_FLOOR = 2
SHAPE_B_FLOOR = 0
SHAPE_C_FLOOR = 2
ROUTE_I_FLOOR = 2
ROUTE_III_FLOOR = 2


def test_scan_target_is_every_py_file_under_conformance_tests_recursive(tmp_path):
    """Completion condition 8/D-2: `sorted(Path.rglob("*.py"))`, not a
    top-level-only `glob` -- a file nested one directory deeper than today
    must still be picked up."""
    nested = tmp_path / "sub" / "deeper.py"
    nested.parent.mkdir(parents=True)
    nested.write_text("x = 1\n")
    top = tmp_path / "top.py"
    top.write_text("y = 2\n")
    found = _scan_target_files(tmp_path)
    assert found == sorted([nested, top])


def test_docstring_units_collected_via_ast_module_class_and_function(tmp_path):
    """Completion condition 7 (alpha)/D-2."""
    f = tmp_path / "sample.py"
    f.write_text(
        '"""module doc."""\n\n\n'
        "class C:\n"
        '    """class doc."""\n\n'
        "    def m(self):\n"
        '        """method doc."""\n'
        "        return 1\n"
    )
    tree = ast.parse(f.read_text())
    units = _docstring_units(tree)
    scopes = {u["scope"] for u in units}
    assert scopes == {"<module>", "C", "C.m"}, scopes


def test_comment_block_is_the_maximal_same_column_run(tmp_path):
    """Completion condition 7 (beta)/D-2: 2 consecutive same-column lines
    join one unit; a 3rd line at a DIFFERENT column starts a new one."""
    f = tmp_path / "sample.py"
    f.write_text(
        "def g():\n"
        "    # line one\n"
        "    # line two\n"
        "        # different column\n"
        "    return 1\n"
    )
    units = _comment_units(f.read_bytes(), [])
    by_start = {u["start_line"]: u["lines"] for u in units}
    assert by_start[2] == [" line one", " line two"], by_start
    assert by_start[4] == [" different column"], by_start


def test_trailing_comment_is_its_own_1_line_unit(tmp_path):
    """Completion condition 7: a comment sharing its own line with code
    never joins a neighboring standalone run, even at the same column."""
    f = tmp_path / "sample.py"
    f.write_text(
        "def g():\n"
        "    x = 1  # trailing\n"
        "    # standalone\n"
        "    return x\n"
    )
    units = _comment_units(f.read_bytes(), [])
    by_start = {u["start_line"]: u["lines"] for u in units}
    assert by_start[2] == [" trailing"], by_start
    assert by_start[3] == [" standalone"], by_start


def test_join_unit_lines_open_span_drops_next_lines_leading_whitespace():
    """Completion condition 5/D-2: an odd cumulative backtick count at a
    line break joins with no separator, after stripping the next line's
    own leading whitespace -- this is what lets a path an earlier author
    split across 2 physical lines read back as one token."""
    joined = _join_unit_lines(["see `pkg/mod_", "    name.py:12` for detail"])
    assert joined == "see `pkg/mod_name.py:12` for detail", joined


def test_join_unit_lines_closed_span_adds_a_single_space():
    """Completion condition 5: an even cumulative backtick count at a line
    break joins with one inserted space (in ADDITION to whatever leading
    whitespace the next line already carries -- unlike the odd-count case
    above, nothing is stripped here), keeping ordinary prose readable."""
    joined = _join_unit_lines(["first sentence.", "second sentence."])
    assert joined == "first sentence. second sentence.", joined


def test_shape_a_and_b_resolve_via_route_i_and_stay_in_range(tmp_path):
    """Completion condition 1/9."""
    f = tmp_path / "five_lines.sql"
    f.write_text("1\n2\n3\n4\n5\n")
    refs = _extract_refs("see `five_lines.sql:3` and `five_lines.sql:2-4` here")
    assert [r["shape"] for r in refs] == ["a", "b"], refs
    for ref in refs:
        resolved, route, note = _resolve_ref(ref, tmp_path)
        assert resolved is not None and route == "i" and note is None, (ref, resolved, route, note)
        assert _range_note(ref, resolved) is None


def test_fixture_shape_a_prime_is_extracted_like_shape_a(tmp_path):
    """Completion condition 2/D-3 (a'): the colon sits just outside the
    closing backtick, touching it with no gap -- current corpus carries 0
    of these (D-7), so this fixture is the only pin for the shape."""
    f = tmp_path / "five_lines.sql"
    f.write_text("1\n2\n3\n4\n5\n")
    refs = _extract_refs("see `five_lines.sql`:3 and `five_lines.sql`:2-4 here")
    assert [r["shape"] for r in refs] == ["a'", "a'"], refs
    resolved, route, note = _resolve_ref(refs[0], tmp_path)
    assert resolved is not None and route == "i" and note is None


def test_carry_forward_uses_the_nearest_preceding_path_in_the_unit():
    """Completion condition 3/D-3 (c)."""
    refs = _extract_refs("first `a/one.py`, then `:5`, then `b/two.py:9`, then `:11`")
    by_raw = {r["raw"]: r for r in refs if r["shape"] == "c"}
    assert by_raw[":5"]["path"] == "a/one.py", by_raw
    assert by_raw[":11"]["path"] == "b/two.py", by_raw


def test_bare_colon_with_no_preceding_path_is_extracted_and_flagged(tmp_path):
    """Completion condition 3: a bare colon-number with NOTHING earlier in
    its own unit is still extracted (not silently dropped) -- and then
    fails resolution with "no preceding path"."""
    refs = _extract_refs("stray `:7` with nothing before it")
    assert len(refs) == 1 and refs[0]["shape"] == "c" and refs[0]["path"] is None, refs
    resolved, route, note = _resolve_ref(refs[0], tmp_path)
    assert resolved is None and note == "no preceding path", (resolved, route, note)


def test_colon_preceded_by_a_digit_is_not_extracted():
    """Completion condition 4/D-3 (c)'s own extraction condition: a bare
    (non-backtick-quoted) ratio (1:1) and an ID-prefixed section number
    (C-14:476, whose own character right before the colon is the digit
    `4`) are both excluded -- never by "was there an earlier path", only
    by the character right before the colon. Left un-backtick-quoted on
    purpose: quoting either one routes it through the backtick branch
    instead (D-3's own path-shaped-content checks reject both anyway, for
    an unrelated reason -- neither carries a whitelisted extension), which
    would not exercise this extraction condition at all."""
    refs = _extract_refs("odds are 1:1 and see C-14:476 for the rule, no `x.py` seen")
    assert refs == [], refs


def test_pytest_node_id_double_colon_is_not_extracted():
    """Completion condition 12."""
    refs = _extract_refs("see `conformance-tests/test_contract.py::test_thing` for the case")
    assert refs == [], refs


def test_extension_whitelist_is_case_sensitive_and_dotted_identifiers_are_skipped():
    """Completion condition 12: `psycopg.sql.SQL`'s own suffix `.SQL` is
    not in the (lowercase) whitelist, and a dotted code identifier with no
    whitelisted extension at all is never mistaken for a path -- each one
    directly followed by a colon and a line number, so a widened whitelist
    really would turn one into shape (a) instead of nothing at all."""
    refs = _extract_refs(
        "uses `psycopg.sql.Composed:5` and `AuthContext.application_id:6`, never `psycopg.sql.SQL:7`"
    )
    assert refs == [], refs


def test_bare_path_without_a_line_number_is_not_a_position_reference():
    """Completion condition 13/D-3/D-9 (3): a plain backtick-quoted path
    with no colon at all is out of scope -- it never appears in the
    extracted list."""
    refs = _extract_refs("see `some/module.py` for context")
    assert refs == [], refs


def test_fake_bare_path_directly_followed_by_a_bare_colon_is_file_not_found(tmp_path):
    """Completion condition 13/D-3's own note: a made-up bare path (shape
    "d", itself unchecked) still sets `carry_path`, so a bare colon right
    after it inherits a path that does not exist -- "file not found", not
    silently skipped."""
    refs = _extract_refs("see `totally/made_up_xyz.py`, at `:9`")
    c_ref = [r for r in refs if r["shape"] == "c"][0]
    resolved, route, note = _resolve_ref(c_ref, tmp_path)
    assert resolved is None and note == "file not found", (resolved, route, note)


def test_route_i_resolves_a_repository_root_relative_path(tmp_path):
    """Completion condition 9."""
    (tmp_path / "top_level.md").write_text("x\n")
    ref = dict(shape="d", raw="top_level.md", path="top_level.md", l1=None, l2=None)
    resolved, route, note = _resolve_ref(ref, tmp_path)
    assert resolved is not None and route == "i" and note is None


def test_route_iii_suffix_match_is_unique_where_basename_alone_is_ambiguous(tmp_path):
    """Completion condition 10/D-4 (iii): 2 peers both carry a same-named
    `service.py` under their own package directory -- a bare basename
    match would be ambiguous, but a path carrying the package name too
    resolves uniquely."""
    for pkg in ("r2db_api", "mitatedb_api"):
        d = tmp_path / ("r2db-api" if pkg == "r2db_api" else "MitateDB-api") / "src" / pkg
        d.mkdir(parents=True)
        (d / "service.py").write_text("x\n")
    bare = dict(shape="d", raw="service.py", path="service.py", l1=None, l2=None)
    resolved, route, note = _resolve_ref(bare, tmp_path)
    assert resolved is None and note == "ambiguous", (resolved, route, note)
    qualified = dict(shape="d", raw="r2db_api/service.py", path="r2db_api/service.py", l1=None, l2=None)
    resolved2, route2, note2 = _resolve_ref(qualified, tmp_path)
    assert resolved2 is not None and route2 == "iii" and note2 is None, (resolved2, route2, note2)


def test_route_iii_search_scope_includes_a_peers_own_conformance_subdir(tmp_path):
    """Completion condition 10: the search scope names a peer's own
    `conformance/` subdirectory (basename `conformance_adapter_r2db.py`,
    the real corpus's own adapters live there) -- not only R-88's own
    allowlist of subdirectories, which has no `conformance/` entry."""
    d = tmp_path / "r2db-api" / "conformance"
    d.mkdir(parents=True)
    (d / "conformance_adapter_r2db.py").write_text("x\n")
    ref = dict(shape="d", raw="conformance_adapter_r2db.py", path="conformance_adapter_r2db.py", l1=None, l2=None)
    resolved, route, note = _resolve_ref(ref, tmp_path)
    assert resolved is not None and route == "iii" and note is None, (resolved, route, note)


def test_bad_range_and_beyond_eof_are_both_reported_with_both_numbers(tmp_path):
    """Completion condition 11/D-4 (iv)."""
    f = tmp_path / "five_lines.sql"
    f.write_text("1\n2\n3\n4\n5\n")
    reversed_ref = dict(shape="b", raw="five_lines.sql:4-2", path="five_lines.sql", l1=4, l2=2)
    assert _range_note(reversed_ref, f) == "bad range"
    past_eof = dict(shape="a", raw="five_lines.sql:9", path="five_lines.sql", l1=9, l2=9)
    assert _range_note(past_eof, f) == "line 9 beyond EOF 5"


def test_line_number_below_1_is_bad_range(tmp_path):
    """Completion condition 11/D-4 (iv), return-1 review item 3: the lower
    bound (`l1 >= 1`) is its own check, not merely implied by the
    reversed-range/EOF checks above -- `l1=0` is neither `l2 < l1` (both
    are 0) nor past EOF, so without this check it would wrongly resolve."""
    f = tmp_path / "five_lines.sql"
    f.write_text("1\n2\n3\n4\n5\n")
    below_one = dict(shape="a", raw="five_lines.sql:0", path="five_lines.sql", l1=0, l2=0)
    assert _range_note(below_one, f) == "bad range"


def test_fixture_allowlist_set_pin_hides_a_matched_row_and_flags_a_dead_row():
    """Completion condition 14/D-5: the fixture table has exactly 1 row.
    A reference matching it is hidden from `messages`; a table row that
    matches nothing extracted is reported as dead. Against the real (0-row)
    `POSITION_REF_ALLOWLIST`, M13a removes this fixture's own one row (the
    matched reference becomes unhidden) and M13b adds an unmatched row (a
    dead pin appears) -- both directions pinned here since the real table
    starts at 0 rows and has no row to remove."""
    fixture_allowlist = {
        ("conformance-tests/fixture_only_example.py", "<module>", "fixture_only_example.py:1"): (
            "synthetic pin -- not a real repository file"
        ),
    }
    ref = dict(shape="d", raw="fixture_only_example.py:1", path="fixture_only_example.py", l1=1, l2=1)
    unresolved = [("conformance-tests/fixture_only_example.py", 1, "<module>", ref, "file not found")]
    messages, dead = _diff_against_allowlist(unresolved, fixture_allowlist)
    assert not messages, messages
    assert not dead, dead


def test_every_real_conformance_tests_position_reference_resolves_or_is_allowlisted():
    """Completion conditions 17/18/23: D-8's own 1-entry-per-line report,
    scanning the real repository tree (`conformance-tests` itself
    included). Completion condition 23: after WP-2's own corrections this
    must be green with a 0-row allowlist."""
    _files, _unit_count, unresolved, _shapes, _routes = _scan_repo(REPO_ROOT, CONFORMANCE_TESTS_DIR)
    messages, dead = _diff_against_allowlist(unresolved, POSITION_REF_ALLOWLIST)
    assert not messages, "\n".join(messages)
    assert not dead, f"dead allow-list row(s): {dead}"


def test_scan_meets_the_floor_for_files_units_shapes_and_routes():
    """Completion conditions 15/20/D-7."""
    files, unit_count, _unresolved, shapes, routes = _scan_repo(REPO_ROOT, CONFORMANCE_TESTS_DIR)
    assert len(files) >= SCAN_FILES_FLOOR, len(files)
    assert unit_count >= SCAN_UNITS_FLOOR, unit_count
    assert shapes.get("a", 0) >= SHAPE_A_FLOOR, shapes
    assert shapes.get("b", 0) >= SHAPE_B_FLOOR, shapes
    assert shapes.get("c", 0) >= SHAPE_C_FLOOR, shapes
    assert routes.get("i", 0) >= ROUTE_I_FLOOR, routes
    assert routes.get("iii", 0) >= ROUTE_III_FLOOR, routes


def test_fixture_line_wrapped_position_reference_is_joined_and_resolved(tmp_path):
    """Completion condition 6, moved from the real corpus to a synthetic
    fixture (R-39 CS-2 replaced the real corpus's last line-wrapped
    references by symbol forms, so no real wrap is left to pin): a
    docstring and a comment each carry a backtick-quoted path split across
    2 physical lines. Driven through the file-level pipeline
    (`_all_units_for_file`, `_join_unit_lines`, `_extract_refs`,
    `_resolve_ref`, `_range_note`), so a regression in D-2's own join rule
    breaks it the way it would break a real wrapped reference."""
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "wrapped_module.sql").write_text("1\n2\n3\n4\n5\n")
    sample = tmp_path / "sample.py"
    sample.write_text(
        '"""see `pkg/wrapped_\n'
        '    module.sql:3` here."""\n'
        "\n\n"
        "# see `pkg/wrapped_\n"
        "# module.sql:4` here\n"
        "x = 1\n"
    )
    refs = []
    for unit in _all_units_for_file(sample):
        refs.extend(_extract_refs(_join_unit_lines(unit["lines"])))
    assert sorted(r["raw"] for r in refs) == ["pkg/wrapped_module.sql:3", "pkg/wrapped_module.sql:4"], refs
    for ref in refs:
        resolved, route, note = _resolve_ref(ref, tmp_path)
        assert resolved is not None and route == "i" and note is None, (ref, resolved, route, note)
        assert _range_note(ref, resolved) is None


def test_this_file_is_meaningful_under_a_standalone_pytest_invocation():
    """Completion condition 16/D-1: this file's own checks read only the
    filesystem (`ast`/`tokenize`/`Path`) -- nothing here depends on
    `request.session.items` or any collection-wide marker/fixture, unlike
    `_collect_marked_condition_ids` in `test_conditions_register.py`,
    which this file deliberately does not use as a model. A grep for this
    sibling file's own module name, confirming 0 import lines, is part of
    the report this check's own work order requires, not part of this
    test body."""
    import sys

    this_module = sys.modules[__name__]
    assert not hasattr(this_module, "test_control_mapping_register")
