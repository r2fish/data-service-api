"""cs9_apply.py -- change set 9: apply a block-edit spec to one module, from the base revision.

Every run rebuilds the module and its companion from the base revision, so a
run is repeatable and the spec is the single record of what was removed.
Edits are exact-string replacements inside one block's own source lines;
nothing is re-wrapped.

usage: cs9_apply.py -C WORKTREE --spec SPEC.json [--dry-run]

SPEC.json:
  {"base": "<rev>", "parent": "<7-hex sha written into the companion>",
   "module": "r2db-api/src/r2db_api/structured.py",
   "companion": "docs/code-history/r2db-api/structured.md",
   "excluded_symbols": ["validate_enum_declaration", ...],
   "line_range": [first, last],          # base line numbers this spec may touch (inclusive)
   "ch_range": ["CH-0990", "CH-1059"],   # the CH-IDs reserved for this work package (inclusive)
   "blocks": [
     {"ch": "CH-0990", "line": <base start line of the block>,
      "edits": [{"old": "...", "new": "..."}, ...]}
   ]}

Rules enforced here (exit 1 with a message naming the block):
  * `line` is the start line of a block `extract_all_blocks` finds in the base source;
  * the block has no CH-ID in the base, lies inside `line_range`, and is not
    inside an excluded symbol;
  * every `old` occurs exactly once in the block's own lines (as left by the
    earlier edits of the same block) and differs from `new`;
  * at least one edit per block; CH-IDs are unique, inside `ch_range`, and
    absent from the base module and the base companion (their order is free).
The comment-provenance checker (`--base`) is still the judge of whether an
edit is an allowed removal; this tool only applies edits and writes sections.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from pathlib import Path


def _git_show(wt: Path, rev: str, rel: str) -> str:
    return subprocess.run(["git", "-C", str(wt), "show", f"{rev}:{rel}"], capture_output=True, text=True, check=True).stdout


def _qualname(tree: ast.Module, line: int) -> str:
    best = "<module>"

    def walk(node: ast.AST, prefix: str) -> None:
        nonlocal best
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                name = f"{prefix}.{child.name}" if prefix else child.name
                first = min([child.lineno] + [d.lineno for d in child.decorator_list])
                if first <= line <= child.end_lineno:
                    best = name
                    walk(child, name)

    walk(tree, "")
    return best


def _die(msg: str) -> None:
    print(f"cs9_apply: {msg}", file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-C", dest="wt", required=True)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    wt = Path(args.wt).resolve()
    sys.path.insert(0, str(wt / "tools"))
    import check_comment_provenance as ccp  # noqa: E402  (the worktree's own checker)

    spec = json.loads(Path(args.spec).read_text())
    base, parent, module, companion = spec["base"], spec["parent"], spec["module"], spec["companion"]
    first, last = spec["line_range"]
    excluded = set(spec.get("excluded_symbols", []))
    ch_lo, ch_hi = spec["ch_range"]
    base_src = _git_show(wt, base, module)
    try:
        base_comp = _git_show(wt, base, companion)
    except subprocess.CalledProcessError:
        base_comp = ""
    if base_comp and not base_comp.endswith("\n"):
        _die("base companion does not end with a newline")
    tree = ast.parse(base_src)
    by_line = {b.start_line: b for b in ccp.extract_all_blocks(base_src)}
    lines = base_src.splitlines(keepends=True)
    rel = module.split("/", 1)[1]

    seen: set[str] = set()
    prev_line = 0
    sections: list[str] = []
    # apply from the bottom up so earlier base line numbers stay valid
    plan = []
    for entry in spec["blocks"]:
        ch, line, edits = entry["ch"], entry["line"], entry["edits"]
        if not re.fullmatch(r"CH-\d{4}", ch):
            _die(f"{ch}: not a CH-NNNN id")
        if ch in seen:
            _die(f"{ch}: listed twice")
        if not (ch_lo <= ch <= ch_hi):
            _die(f"{ch}: outside ch_range {ch_lo}..{ch_hi}")
        if ch in base_src or f"## {ch}\n" in base_comp:
            _die(f"{ch}: already present at the base")
        seen.add(ch)
        if line <= prev_line:
            _die(f"{ch}: blocks must be listed in ascending base line order")
        prev_line = line
        blk = by_line.get(line)
        if blk is None:
            _die(f"{ch}: no block starts at base line {line}")
        if blk.history_id is not None:
            _die(f"{ch}: base block at line {line} already carries {blk.history_id}")
        if not (first <= blk.start_line and blk.end_line <= last):
            _die(f"{ch}: block {blk.start_line}-{blk.end_line} is outside line_range {first}-{last}")
        qual = _qualname(tree, blk.start_line)
        if any(part in excluded for part in qual.split(".")):
            _die(f"{ch}: block at line {line} is inside the excluded symbol {qual}")
        if not edits:
            _die(f"{ch}: no edits (a block with nothing removed keeps its base bytes and gets no CH-ID)")
        plan.append((ch, blk, edits, qual))

    for ch, blk, edits, qual in sorted(plan, key=lambda item: -item[1].start_line):
        region = "".join(lines[blk.start_line - 1 : blk.end_line])
        for n, edit in enumerate(edits, 1):
            old, new = edit["old"], edit["new"]
            if old == new:
                _die(f"{ch}: edit {n} changes nothing")
            if region.count(old) != 1:
                _die(f"{ch}: edit {n}: `old` occurs {region.count(old)} times in the block (need exactly 1)")
            region = region.replace(old, new)
        if not region.endswith("\n"):
            _die(f"{ch}: the block no longer ends with a newline")
        region_lines = region.splitlines(keepends=True)
        tail = region_lines[-1]
        indent = tail[: len(tail) - len(tail.lstrip())]
        if blk.kind == "comment":
            if not all(l.strip().startswith("#") for l in region_lines):
                _die(f"{ch}: a comment block line no longer starts with '#'")
            region = region + f"{indent}# history: {ch}\n"
        else:
            m = re.search(r'("""|\'\'\')[ \t]*\n\Z', region)
            if m is None:
                _die(f"{ch}: the docstring's closing quotes are not at the end of its last line")
            quote = m.group(1)
            body = region[: m.start()]
            pre = body.rstrip(" \t")
            if pre.endswith("\n") and pre.strip():
                # closing quotes on their own line: that line keeps its base bytes
                region = pre + f"\n{indent}History: {ch}\n" + region[len(pre):]
            else:
                # text."""  -> text.\n\n<indent>History: CH\n<indent>"""
                first_line = lines[blk.start_line - 1]
                doc_indent = first_line[: len(first_line) - len(first_line.lstrip())]
                region = body.rstrip(" \t") + f"\n\n{doc_indent}History: {ch}\n{doc_indent}{quote}\n"
        lines[blk.start_line - 1 : blk.end_line] = [region]
        fence = "```"
        while fence in blk.dedented:
            fence += "`"
        sections.append((blk.start_line, (
            f"\n## {ch}\n\n- moved from: `{rel}` (`{qual}`)\n- parent commit: `{parent}`\n- kind: {blk.kind}\n\n"
            f"{fence}\n{blk.dedented}\n{fence}\n"
        )))
        print(f"{ch} {blk.kind} base L{blk.start_line}-{blk.end_line} {qual} edits={len(edits)}")

    new_src = "".join(lines)
    try:
        ast.parse(new_src)
    except (SyntaxError, ValueError) as exc:  # ValueError: e.g. a lone surrogate written unescaped in the spec
        _die(f"the edited module does not parse: {exc!r}")
    new_comp = base_comp + "".join(text for _, text in sorted(sections))
    if not base_comp:
        new_comp = new_comp.lstrip("\n")
    print(f"blocks={len(plan)} module_lines {len(base_src.splitlines())} -> {len(new_src.splitlines())}")
    if args.dry_run:
        return 0
    (wt / module).write_text(new_src)
    (wt / companion).parent.mkdir(parents=True, exist_ok=True)
    (wt / companion).write_text(new_comp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
