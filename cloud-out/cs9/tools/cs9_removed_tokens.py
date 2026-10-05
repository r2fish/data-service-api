"""cs9_removed_tokens.py -- change set 9 audit for conditions 28-30 (work order §18.3).

For every block carrying a CH-ID, pairs it with its basis block at --base (same
scope, byte-equal to the companion's fenced block -- the checker's own first-move
rule) and compares basis and new text with whitespace ignored. Prints:
  WS-ONLY  file  Ls-e  CH-ID                      (condition 28: must be 0 rows)
  REMOVED  file  Ls-e  CH-ID  class  token  xN    (condition 30: one §16.4 row each)
  UNPAIRED file  Ln    CH-ID                      (no basis block; must be 0 rows)
classes: path (a real path/directory or file basename in the --base tree),
         id (a bare clause/decision ID: M-1, D-4, R-6, m-7, L4-10, WP-n, §n),
         wp-locator ("work order WP-n" / "作業指示書 WP-n" / "work order §n").
Line numbers are the basis's. Exit 0 only when WS-ONLY and UNPAIRED are 0.
Usage: python3 "$SP/cs9_removed_tokens.py" -C "$WT" [--base REV] [--head REV] [PATH ...]
  --head omitted = working tree (before the commit); --head HEAD after it.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

DEFAULT_PATHS = [
    "r2db-api/src/r2db_api/structured.py",
    "MitateDB-api/src/mitatedb_api/platform_declarations.py",
]
_STRIP = "`'\"()[]{}<>,;:!?*"
_EXT = re.compile(r"\w\.[A-Za-z0-9]+$")
_ID_OR_LOCATOR = re.compile(
    r"(?P<loc>(?:work order|作業指示書)\s*(?:WP-[0-9A-Za-z]+(?:-[0-9A-Za-z]+)*|§\s?[0-9]+(?:\.[0-9]+)*))"
    r"|(?P<id>(?<![\w\-])(?:WP-[0-9A-Za-z]+(?:-[0-9A-Za-z]+)*|(?:[A-Z]{1,6}[0-9]*|[a-z])-[0-9]+[a-z]?"
    r"|§\s?[0-9]+(?:\.[0-9]+)*)(?![\w]))"
)


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True).stdout


def tokens(text: str, names: frozenset[str]) -> Counter:
    flat = " ".join(text.split())
    found: Counter = Counter()
    kept = []
    for raw in flat.split(" "):
        word = raw.strip(_STRIP).rstrip(".")
        if word.endswith("'s"):
            word = word[:-2]
        word = word.split(":", 1)[0].removeprefix("./").rstrip("/")
        if word in names and ("/" in word or _EXT.search(word)):
            found[("path", word)] += 1
            kept.append(" ")
        else:
            kept.append(raw)
    for m in _ID_OR_LOCATOR.finditer(" ".join(kept)):
        cls = "wp-locator" if m.group("loc") else "id"
        found[(cls, " ".join(m.group(0).split()))] += 1
    return found


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-C", dest="wt", required=True)
    ap.add_argument("--base", default="092e1a1")
    ap.add_argument("--head", default=None)
    ap.add_argument("paths", nargs="*")
    ns = ap.parse_args()
    wt = Path(ns.wt).resolve()
    sys.path.insert(0, str(wt / "tools"))
    import check_comment_provenance as cp  # noqa: E402

    tree = cp._tree_paths(wt, ns.base)
    names = set(tree)
    for p in tree:
        parts = p.split("/")
        names.add(parts[-1])
        names.update("/".join(parts[:i]) for i in range(1, len(parts)))
    names = frozenset(names)
    idset = cp._tracked_identifier_set(wt, ns.base)
    ws_only = removed = unpaired = ch_blocks = 0
    print(f"BASE {ns.base} HEAD {ns.head or 'worktree'}")
    for rel in ns.paths or DEFAULT_PATHS:
        old_src = git(wt, "show", f"{ns.base}:{rel}")
        new_src = git(wt, "show", f"{ns.head}:{rel}") if ns.head else (wt / rel).read_text(encoding="utf-8")
        old_blocks, new_blocks = cp.extract_all_blocks(old_src), cp.extract_all_blocks(new_src)
        old_pos, new_pos = cp._block_positions(old_src, old_blocks), cp._block_positions(new_src, new_blocks)
        companions = cp._load_companion_lookup(wt, Path(rel).parts[0])
        used = [False] * len(old_blocks)
        base_ids = {ob.history_id for ob in old_blocks if ob.history_id is not None}
        for j, nb in enumerate(new_blocks):
            if nb.history_id is None or nb.history_id in base_ids:
                continue  # a CH-ID the base already carries is another change set's block (Y7-12)
            ch_blocks += 1
            comp = companions.get(nb.history_id)
            idx = next((i for i, ob in enumerate(old_blocks) if not used[i] and comp is not None
                        and ob.dedented == comp and old_pos[i][0] == new_pos[j][0]), None)
            if idx is None:
                unpaired += 1
                print(f"UNPAIRED\t{rel}\tL{nb.start_line}\t{nb.history_id}")
                continue
            used[idx] = True
            ob = old_blocks[idx]
            where = f"{rel}\tL{ob.start_line}-{ob.end_line}\t{nb.history_id}"
            old_flat = " ".join(cp._flatten(ob.kind, ob.dedented, idset).split())
            new_flat = " ".join(cp._flatten(nb.kind, nb.retained_text, idset).split()) if nb.retained_text else ""
            if old_flat == new_flat:
                ws_only += 1
                print(f"WS-ONLY\t{where}")
                continue
            gone = tokens(old_flat, names) - tokens(new_flat, names)
            for (cls, tok), n in sorted(gone.items(), key=lambda kv: (kv[0][0], kv[0][1])):
                removed += 1
                print(f"REMOVED\t{where}\t{cls}\t{tok}\tx{n}")
    print(f"SUMMARY ch_blocks={ch_blocks} ws_only={ws_only} unpaired={unpaired} removed_rows={removed}")
    return 0 if ws_only == 0 and unpaired == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
