"""cs8_measure.py -- change set 8 measurement (work order §16.2's counting, applied to the base blob).

usage: python3 cs8_measure.py -C REPO --base REV MODULE [MODULE ...] [--json OUT]

For each module (repo-relative path) the base blob is read with `git show`,
blocks are taken with the checker's own `extract_all_blocks`, and the counts of
work order §13.2 / §14.2 / §16.2 are printed as Markdown. Nothing is written
into the repository.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

PEERS = {"r2db-api": "r2db_api", "MitateDB-api": "mitatedb_api"}

# design §3 叙述の目印 (English: word boundary, case-insensitive; Japanese: no boundary)
MARKERS_EN = [
    r"before (this|the) (fix|change|ruling|rework|review)",
    r"previously", r"originally", r"used to", r"no longer",
    r"was (added|changed|removed|introduced|flipped|replaced|moved|extracted)", r"first implementation",
    r"this (WP|commit|change set|round)", r"in this same commit", r"unchanged from before",
    r"the review('s)? .* (found|showed)",
    r"flipped (again )?to", r"(supervisor|supervisory|monitor|requester) ruling",
    r"it claimed", r"this same commit", r"was (considered|rejected)", r"the original (fix|implementation)",
    r"existed before", r"before (WP|Phase)[- ]\w+", r"pre-(WP|Phase)",
]
MARKERS_JA = ["以前は", "当初", "差し戻し", "監督裁定"]
MARKER_RES = [(m, re.compile(r"\b" + m + r"\b", re.IGNORECASE)) for m in MARKERS_EN] + [(m, re.compile(m)) for m in MARKERS_JA]

# §13.2 の正規表現 + §16.2 設計レビューで足した 2 形 + 本件で足した形
REF_RE = re.compile(r"\b(above|below|see [^.]{0,60}own (comment|docstring)|the comment on)\b", re.IGNORECASE)
REF_EXTRA_RE = re.compile(r"('s identical comment|own (comment|docstring|paragraph)|identical(-purpose)? comment)", re.IGNORECASE)

# §14.2 の正規表現
SAFETY_RE = re.compile(
    r"\b(lock\w*|FOR UPDATE|advisory|transaction\w*|commit\w*|rollback|ROLLBACK|timeout\w*|statement_timeout|lock_timeout|"
    r"fail[- ]closed|TOCTOU|race|deadlock|secret\w*|password|credential\w*|revoke\w*|compare_digest|injection|sql\.Identifier|"
    r"sql\.SQL|Identifier|quote\w*|isolation|SERIALIZABLE|atomic\w*|SI-\d+|privilege\w*|least privilege|role|search_path|pepper|"
    r"leak\w*|opaque)\b",
    re.IGNORECASE,
)
POSITION_RE = re.compile(r"\b(above|below|here)\b|\.py:\d+|\bin `[\w/]+\.py`|`[\w/]+\.py`'s")
DATE_RE = re.compile(r"\b20\d\d-\d\d-\d\d\b", re.ASCII)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout


def registered_symbols(repo: Path, rev: str, module: str) -> set[str]:
    """Symbols of `module` that appear in either peer's `_ISOMORPHIC_TARGETS` rows."""
    peer_rel = module.split("/", 1)[1]
    out: set[str] = set()
    for peer in PEERS:
        text = git(repo, "show", f"{rev}:{peer}/tests/test_audit_query.py")
        m = re.search(r"_ISOMORPHIC_TARGETS\s*(?::[^=]*)?=\s*\((.*?)\n\)", text, re.S)
        body = m.group(1)
        for row in re.finditer(r'\(\s*"([^"]+)",\s*"([^"]+)",\s*"([^"]+)"\s*\)', body):
            a, b, sym = row.groups()
            if peer_rel in (a, b):
                out.add(sym)
    return out


def symbol_ranges(tree: ast.Module, symbols: set[str]) -> dict[str, tuple[int, int]]:
    """(lineno, end_lineno) of each registered symbol, located the way the isomorphism test does."""
    found: dict[str, tuple[int, int]] = {}
    for n in tree.body:
        name = None
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = n.name
        elif isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name) and t.id in symbols:
                    name = t.id
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
            name = n.target.id
        if name in symbols and name not in found:
            found[name] = (n.lineno, n.end_lineno)
    for c in tree.body:
        if isinstance(c, ast.ClassDef):
            for m in c.body:
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and m.name in symbols and m.name not in found:
                    found[m.name] = (m.lineno, m.end_lineno)
    return found


def qualname(tree: ast.Module, line: int) -> str:
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


def count_tokens(ccp, text: str) -> int:
    return sum(len(p.findall(text)) for p in ccp._HISTORY_TOKEN_PATTERNS)


def has_token(ccp, text: str) -> bool:
    return any(p.search(text) for p in ccp._HISTORY_TOKEN_PATTERNS)


def measure(repo: Path, rev: str, module: str, ccp, real_paths) -> dict:
    src = git(repo, "show", f"{rev}:{module}")
    lines = src.splitlines()
    tree = ast.parse(src)
    blocks = ccp.extract_all_blocks(src)
    syms = registered_symbols(repo, rev, module)
    ranges = symbol_ranges(tree, syms)
    res: dict = {"module": module, "base": rev, "lines": len(lines), "blocks": len(blocks)}
    res["kinds"] = dict(Counter(b.kind for b in blocks))
    res["block_lines"] = sum(b.end_line - b.start_line + 1 for b in blocks)
    res["registered_symbols"] = sorted(syms)
    res["registered_symbols_found"] = {k: list(v) for k, v in sorted(ranges.items())}
    res["registered_symbols_missing"] = sorted(syms - set(ranges))
    existing = [(b.start_line, b.end_line, b.history_id) for b in blocks if b.history_id]
    res["existing_ch"] = existing

    def in_helper(b) -> str | None:
        for name, (lo, hi) in ranges.items():
            if lo <= b.start_line and b.end_line <= hi:
                return name
        return None

    helper_blocks = [(b.start_line, b.end_line, b.kind, in_helper(b)) for b in blocks if in_helper(b)]
    res["helper_blocks"] = helper_blocks
    res["helper_block_lines"] = sum(e - s + 1 for s, e, _, _ in helper_blocks)
    targets = [b for b in blocks if b.history_id is None and in_helper(b) is None]
    res["target_blocks"] = len(targets)
    res["target_kinds"] = dict(Counter(b.kind for b in targets))
    res["target_lines"] = sum(b.end_line - b.start_line + 1 for b in targets)

    res["tokens_file"] = count_tokens(ccp, src)
    tok_in_targets = 0
    blocks_with_tok = []
    for b in targets:
        n = count_tokens(ccp, b.dedented)
        if n:
            tok_in_targets += n
            blocks_with_tok.append((b.start_line, b.end_line, n))
    res["tokens_in_targets"] = tok_in_targets
    res["target_blocks_with_tokens"] = len(blocks_with_tok)
    res["target_blocks_with_tokens_lines"] = sum(e - s + 1 for s, e, _ in blocks_with_tok)
    res["tokens_all_blocks"] = sum(count_tokens(ccp, b.dedented) for b in blocks)
    res["date_lines"] = [i + 1 for i, l in enumerate(lines) if DATE_RE.search(l)]
    res["colon_hash_lines"] = [i + 1 for i, l in enumerate(lines) if l.lstrip().startswith("#:")]
    res["long_blocks_no_ch"] = [(b.start_line, b.end_line) for b in blocks if b.history_id is None and b.end_line - b.start_line + 1 >= 10]
    res["long_blocks_targets"] = [(b.start_line, b.end_line) for b in targets if b.end_line - b.start_line + 1 >= 10]
    res["long_blocks_targets_lines"] = sum(e - s + 1 for s, e in res["long_blocks_targets"])
    if res["long_blocks_targets"]:
        res["longest_target_block"] = max(e - s + 1 for s, e in res["long_blocks_targets"])

    # sentence-level: markers, refs, safety/protected/position among token sentences
    marker_rows = []
    ref_sentences = 0
    ref_rows = []
    safety_rows, protected_rows, position_rows = [], [], []
    tok_sent_total = 0
    per_block = []
    for b in targets:
        flat = ccp._flatten(b.kind, b.dedented)
        sents = [" ".join(s.split()) for s in ccp.split_sentences(flat)]
        hits = []
        for s in sents:
            ms = [rx.search(s).group(0) for name, rx in MARKER_RES if rx.search(s)]
            if ms:
                hits.append((s[:140], ms))
            if REF_RE.search(s) or REF_EXTRA_RE.search(s):
                ref_sentences += 1
                words = sorted(set(m.group(0) for m in REF_RE.finditer(s)) | set(m.group(0) for m in REF_EXTRA_RE.finditer(s)))
                ref_rows.append((b.start_line, b.end_line, words, s[:160]))
            if has_token(ccp, s):
                tok_sent_total += 1
                sw = sorted(set(m.group(0) for m in SAFETY_RE.finditer(s)))
                if sw:
                    safety_rows.append((b.start_line, b.end_line, sw, s[:160]))
                if ccp._sentence_has_protected_reference(s, real_paths):
                    protected_rows.append((b.start_line, b.end_line, s[:160]))
                pw = sorted(set(m.group(0) for m in POSITION_RE.finditer(s)))
                if pw:
                    position_rows.append((b.start_line, b.end_line, pw, s[:160]))
        if hits:
            marker_rows.append((b.start_line, b.end_line, hits))
        per_block.append({
            "start": b.start_line, "end": b.end_line, "kind": b.kind, "qualname": qualname(tree, b.start_line),
            "lines": b.end_line - b.start_line + 1, "tokens": count_tokens(ccp, b.dedented),
            "sentences": len(sents), "markers": sum(len(h[1]) for h in hits),
            "dates": len(DATE_RE.findall(b.dedented)),
        })
    res["marker_sentences"] = sum(len(r[2]) for r in marker_rows)
    res["marker_blocks"] = len(marker_rows)
    res["marker_rows"] = marker_rows
    res["ref_sentences"] = ref_sentences
    res["ref_rows"] = ref_rows
    res["token_sentences"] = tok_sent_total
    res["safety_rows"] = safety_rows
    res["protected_rows"] = protected_rows
    res["position_rows"] = position_rows
    res["safety_blocks"] = sorted(set((r[0], r[1]) for r in safety_rows))
    res["protected_blocks"] = sorted(set((r[0], r[1]) for r in protected_rows))
    res["position_blocks"] = sorted(set((r[0], r[1]) for r in position_rows))
    res["per_block"] = per_block
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-C", dest="repo", required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("modules", nargs="+")
    ap.add_argument("--json")
    ns = ap.parse_args()
    repo = Path(ns.repo).resolve()
    sys.path.insert(0, str(repo / "tools"))
    import check_comment_provenance as ccp  # noqa: E402

    real_paths = ccp._tree_paths(repo, ns.base)
    out = {m: measure(repo, ns.base, m, ccp, real_paths) for m in ns.modules}
    if ns.json:
        Path(ns.json).write_text(json.dumps(out, ensure_ascii=False, indent=1))
    for m, r in out.items():
        print(f"## {m} @ {r['base']}")
        for k in ("lines", "blocks", "kinds", "block_lines", "existing_ch", "helper_blocks", "helper_block_lines",
                  "registered_symbols_missing", "target_blocks", "target_kinds", "target_lines", "tokens_file",
                  "tokens_all_blocks", "tokens_in_targets", "target_blocks_with_tokens", "target_blocks_with_tokens_lines",
                  "date_lines", "colon_hash_lines", "long_blocks_no_ch", "long_blocks_targets", "long_blocks_targets_lines",
                  "marker_sentences", "marker_blocks", "ref_sentences", "token_sentences"):
            print(f"- {k}: {r[k]}")
        print(f"- registered symbols: {len(r['registered_symbols'])} (found {len(r['registered_symbols_found'])})")
        print(f"- safety/protected/position sentences: {len(r['safety_rows'])} / {len(r['protected_rows'])} / {len(r['position_rows'])}; blocks {len(r['safety_blocks'])} / {len(r['protected_blocks'])} / {len(r['position_blocks'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
