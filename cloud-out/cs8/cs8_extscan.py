"""cs8_extscan.py -- change set 8: scans outside the two modules (base tree via `git ls-tree`/`git show`).

usage: python3 cs8_extscan.py -C REPO --base REV

Prints, per module:
  A. sentences outside the module that point at its comments/docstrings
     (§13.2 regex + `'s identical comment` + `<name> below/above` + `own (comment|docstring|paragraph)`),
     restricted to lines that also name the module (file name or a symbol it defines);
  B. position references `file:N` into the module (full path, peer-relative, bare basename),
     and the continuation form `:N` on the same line after such a path, grouped by location;
  C. `(module, lineno)` pins in both peers' tests/test_l1_details_vocabulary_ast_scan.py;
  D. design §5 (b) grep (`read_text|\\.count\\(|getsource|__doc__`) over both peers' tests/ and conformance/,
     conformance-tests/ and tools/tests/, keeping hits whose line or file names the module.
Everything is read from the base revision, nothing is written.
"""
from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

MODULES = {
    "r2db-api/src/r2db_api/platform_declarations.py": ("r2db-api", "platform_declarations"),
    "MitateDB-api/src/mitatedb_api/control_plane.py": ("MitateDB-api", "control_plane"),
}
REF_RE = re.compile(
    r"(\b(above|below|see [^.]{0,60}own (comment|docstring)|the comment on)\b|'s identical comment|own (comment|docstring|paragraph|header|note|tail|module docstring)|identical(-purpose)? comment)",
    re.IGNORECASE,
)
EXT = r"(?:py|md|sql|json|toml|yaml|yml|sh|txt|conf|tsv|cfg|ini)"
TOKEN = re.compile(
    rf"(?P<path>(?<![A-Za-z0-9_./-])(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.{EXT})(?![A-Za-z0-9_/])(?P<q>`?)(?::(?P<a>\d+)(?:-(?P<b>\d+))?)?"
    rf"|(?<![A-Za-z0-9])(?P<bq>`?):(?P<ca>\d+)(?:-(?P<cb>\d+))?(?![A-Za-z0-9])"
)
STRING_CHECK_RE = re.compile(r"read_text|\.count\(|getsource|__doc__")


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-C", dest="repo", required=True)
    ap.add_argument("--base", required=True)
    ns = ap.parse_args()
    repo = Path(ns.repo).resolve()
    rev = ns.base
    tree = [p for p in git(repo, "ls-tree", "-r", "--name-only", rev).splitlines()]
    texts: dict[str, str] = {}

    def text(p: str) -> str:
        if p not in texts:
            try:
                texts[p] = git(repo, "show", f"{rev}:{p}")
            except subprocess.CalledProcessError:
                texts[p] = ""
        return texts[p]

    for module, (peer, stem) in MODULES.items():
        print(f"\n# {module} @ {rev}")
        src = text(module)
        tree_mod = ast.parse(src)
        symbols = {n.name for n in tree_mod.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
        for c in tree_mod.body:
            if isinstance(c, ast.ClassDef):
                symbols |= {m.name for m in c.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))}
        sym_re = re.compile(r"\b(" + "|".join(sorted(map(re.escape, symbols), key=len, reverse=True)) + r")\b")
        name_re = re.compile(re.escape(stem) + r"(\.py)?\b")
        # A: external references
        print("\n## A. 塊をまたぐ参照先 (module の外から)")
        scope_dirs = [d for p in ("r2db-api", "MitateDB-api") for d in (f"{p}/src/", f"{p}/tests/", f"{p}/conformance/")] + ["conformance-tests/", "security/"]
        readmes = [p for p in tree if p.endswith("README.md") and (p.count("/") == 0 or p.startswith(("r2db-api/", "MitateDB-api/")))]
        files = [p for p in tree if any(p.startswith(d) for d in scope_dirs) and p.endswith((".py", ".md"))] + readmes
        hits = 0
        for p in sorted(set(files)):
            if p == module:
                continue
            same_peer = p.startswith(peer + "/")
            for i, line in enumerate(text(p).splitlines(), 1):
                if not REF_RE.search(line):
                    continue
                named = bool(name_re.search(line))
                # a peer's own file may name the module only by one of its symbols
                sym_named = same_peer and bool(sym_re.search(line))
                if named or sym_named:
                    hits += 1
                    print(f"- `{p}:{i}` {'[name]' if named else '[symbol]'} {line.strip()[:200]}")
        print(f"- A hits: {hits}")
        # B: position references
        print("\n## B. 位置参照 (`file:N`、続きの `:N`)")
        groups: dict[str, list[str]] = defaultdict(list)
        counts: Counter = Counter()
        for p in tree:
            if not p.endswith((".md", ".py", ".txt")):
                continue
            if p == module:
                loc = "self"
            elif p == "security/CONTROL_MAPPING.md":
                loc = "security/CONTROL_MAPPING.md"
            elif p.startswith("security/"):
                loc = "security/ (other)"
            elif p.startswith("conformance-tests/"):
                loc = "conformance-tests/"
            elif p in ("README.md", f"{peer}/README.md"):
                loc = "README"
            elif p.startswith(f"{peer}/docs/"):
                loc = f"{peer}/docs/"
            elif p.startswith(f"{peer}/tests/"):
                loc = f"{peer}/tests/"
            elif p.startswith(f"{peer}/conformance/"):
                loc = f"{peer}/conformance/"
            elif p.startswith(f"{peer}/src/"):
                loc = f"{peer}/src/ (other modules)"
            elif p.startswith("docs/"):
                loc = "docs/ (記録)"
            elif p.startswith(("r2db-api/", "MitateDB-api/")):
                loc = "other peer"
            else:
                loc = "elsewhere"
            for i, line in enumerate(text(p).splitlines(), 1):
                cur = None
                for m in TOKEN.finditer(line):
                    if m.group("path"):
                        path = m.group("path")
                        base = path.rsplit("/", 1)[-1]
                        if base != f"{stem}.py":
                            cur = None
                        elif path == module:
                            cur = "exact"
                        elif module.endswith("/" + path):
                            cur = "peer-rel"
                        elif "/" not in path:
                            cur = "bare"
                        else:
                            cur = None  # the other peer's same-named module
                        if cur and m.group("a"):
                            counts[(loc, cur)] += 1
                            groups[loc].append(f"`{p}:{i}` {m.group(0)}")
                    elif cur and m.group("ca"):
                        counts[(loc, cur + " (続き)")] += 1
                        groups[loc].append(f"`{p}:{i}` {m.group(0)} (続き)")
        for (loc, kind), n in sorted(counts.items()):
            print(f"- {loc} [{kind}]: {n}")
        for loc in ("security/CONTROL_MAPPING.md", "conformance-tests/", "README", f"{peer}/docs/", f"{peer}/tests/", f"{peer}/conformance/", "self", f"{peer}/src/ (other modules)"):
            for g in groups.get(loc, []):
                print(f"  - {loc}: {g}")
        # C: line pins
        print("\n## C. 行番号 pin")
        for p in ("r2db-api/tests/test_l1_details_vocabulary_ast_scan.py", "MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py"):
            t = text(p)
            pins = re.findall(rf'\(\s*"{stem}\.py"\s*,\s*(\d+)\s*\)', t)
            counts_pin = re.findall(rf'"{stem}\.py"\s*:\s*(\d+)', t)
            print(f"- `{p}`: (module, lineno) pins = {len(pins)} {pins}; count pins = {counts_pin}")
        # D: string checks
        print("\n## D. 設計 §5 (b) の grep")
        dirs = [d for pp in ("r2db-api", "MitateDB-api") for d in (f"{pp}/tests/", f"{pp}/conformance/")] + ["conformance-tests/", "tools/tests/"]
        for p in sorted(p for p in tree if any(p.startswith(d) for d in dirs) and p.endswith(".py")):
            t = text(p)
            file_named = stem in Path(p).stem
            for i, line in enumerate(t.splitlines(), 1):
                if STRING_CHECK_RE.search(line) and (name_re.search(line) or (file_named and not line.lstrip().startswith("#"))):
                    print(f"- `{p}:{i}` {line.strip()[:180]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
