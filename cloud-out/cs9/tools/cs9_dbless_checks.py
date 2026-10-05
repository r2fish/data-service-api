"""cs9_dbless_checks.py -- change set 9 (D): the DB-less collation, output verbatim.

usage: python3 cs9_dbless_checks.py -C REPO --sp SP_DIR --base REV
Applies both specs with cs9_apply.py, runs the checker (--base, --register),
check_doc_refs, cs9_removed_tokens, repull --dry-run, the AST-invariance and
untouched-block checks, the CLI red checks for conditions 17 / 21 / 29 / 22(b),
the after-state counts, then restores every touched file from the backup copies
(cp, sha256 twice). Prints every tool's output lines verbatim between markers.
"""
import argparse, ast, hashlib, json, re, subprocess, sys, time
from pathlib import Path

ap = argparse.ArgumentParser(); ap.add_argument("-C", dest="root", required=True); ap.add_argument("--sp", required=True); ap.add_argument("--base", required=True)
ns = ap.parse_args(); root = Path(ns.root).resolve(); SP = Path(ns.sp); TOOLS = SP / "cs9/tools"; BASE = ns.base
sys.path.insert(0, str(root / "tools")); import check_comment_provenance as cp
MODS = ["r2db-api/src/r2db_api/structured.py", "MitateDB-api/src/mitatedb_api/platform_declarations.py"]
COMPS = ["docs/code-history/r2db-api/structured.md", "docs/code-history/MitateDB-api/platform_declarations.md"]
CM = "security/CONTROL_MAPPING.md"
PY = sys.executable

def run(cmd, label, cwd=root):
    p = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    out = (p.stdout + p.stderr).rstrip("\n")
    print(f"### {label}\n$ {' '.join(str(c) for c in cmd)}\n{out}\n(exit {p.returncode})\n")
    return p.returncode, out

def sha(rel): return hashlib.sha256((root / rel).read_bytes()).hexdigest()
def show(rel): return subprocess.run(["git", "-C", str(root), "show", f"{BASE}:{rel}"], capture_output=True, text=True, check=True).stdout

# 1. apply
for name in ("structured", "platform_declarations"):
    run([PY, TOOLS / "cs9_apply.py", "-C", str(root), "--spec", str(SP / f"cs9/cs9-spec-{name}.json")], f"apply {name}")
# 2. checker / register / doc refs
rc_base, _ = run([PY, "tools/check_comment_provenance.py", "--base", BASE, *MODS], "check_comment_provenance --base")
run([PY, "tools/check_comment_provenance.py", "--register"], "check_comment_provenance --register")
run([PY, "tools/check_doc_refs.py"], "check_doc_refs")
rc_rt, rt_out = run([PY, TOOLS / "cs9_removed_tokens.py", "-C", str(root)], "cs9_removed_tokens (worktree)")
rc_rp, rp_out = run([PY, TOOLS / "repull.py", "--dry-run", BASE, CM, "--", *MODS], "repull --dry-run")
# the other peer's same-named module must not be touched by repull: every rewritten line names one of MODS' basenames and resolves to MODS
other = [l for l in rp_out.splitlines() if l.startswith(CM) and "r2db-api/src/r2db_api/platform_declarations.py" in l]
print(f"### repull guard: lines rewriting a reference into r2db-api's platform_declarations.py: {len(other)}\n")
# 3. AST invariance + untouched blocks
for m in MODS:
    old, new = show(m), (root / m).read_text()
    print(f"### AST {m}: {'identical' if cp.ast_signature(old) == cp.ast_signature(new) else 'DIFFERENT'} (docstrings excluded, design §4.1 (1)); lines {len(old.splitlines())} -> {len(new.splitlines())}")
    ob, nb = cp.extract_all_blocks(old), cp.extract_all_blocks(new)
    spec = json.loads((SP / f"cs9/cs9-spec-{'structured' if 'structured' in m else 'platform_declarations'}.json").read_text())
    edited = {b["line"] for b in spec["blocks"]}
    new_texts = [b.dedented for b in nb]
    missing = [(b.start_line, b.end_line, b.history_id) for b in ob if b.start_line not in edited and b.dedented not in new_texts]
    print(f"    base blocks {len(ob)}, new blocks {len(nb)}; base blocks not in the spec whose text is absent verbatim from the new module: {missing}")
    tok_old = sum(len(p.findall(old)) for p in cp._HISTORY_TOKEN_PATTERNS); tok_new = sum(len(p.findall(new)) for p in cp._HISTORY_TOKEN_PATTERNS)
    d_old = [i + 1 for i, l in enumerate(old.splitlines()) if re.search(r"\b20\d\d-\d\d-\d\d\b", l)]; d_new = [i + 1 for i, l in enumerate(new.splitlines()) if re.search(r"\b20\d\d-\d\d-\d\d\b", l)]
    ch_old = sum(b.history_id is not None for b in ob); ch_new = sum(b.history_id is not None for b in nb)
    colon_old = sum(l.lstrip().startswith("#:") for l in old.splitlines()); colon_new = sum(l.lstrip().startswith("#:") for l in new.splitlines())
    scr_old = sum(1 for l in old.splitlines() if re.search(r"\{scratchpad\}/|(?<![\w/])scratchpad/", l)); scr_new = sum(1 for l in new.splitlines() if re.search(r"\{scratchpad\}/|(?<![\w/])scratchpad/", l))
    bs = sum("\\" in b.dedented for b in nb if b.kind == "docstring" and b.history_id in {x["ch"] for x in spec["blocks"]})
    print(f"    history tokens {tok_old} -> {tok_new}; date lines {len(d_old)} -> {len(d_new)} (new: {d_new}); CH blocks {ch_old} -> {ch_new}; `#:` lines {colon_old} -> {colon_new}; scratchpad lines {scr_old} -> {scr_new}; changed docstrings with a backslash: {bs}\n")
    # 22(b) measurement: a CH block (this spec) whose label holds a real path split by a line wrap
    rp = cp._tree_paths(root, BASE); hits = []
    for b in nb:
        if b.history_id in {x["ch"] for x in spec["blocks"]}:
            lines = b.dedented.splitlines()
            for i in range(len(lines) - 1):
                joined = (lines[i].rstrip().rstrip("#").rstrip() + lines[i + 1].lstrip().lstrip("#:").lstrip())
                for cand in cp._filename_candidates(joined):
                    if cp._is_real_filename_candidate(cand, rp) and cand not in lines[i] and cand not in lines[i + 1]:
                        hits.append((b.history_id, cand))
    print(f"    22(b): CH blocks of this spec with a real path split by a line wrap: {sorted(set(hits))}\n")
# 4. CLI red checks (mutations on the applied tree, restored from a copy after each)
def mutate(label, rel, old, new, cmd, expect_prefix=None):
    text = (root / rel).read_text(); n = text.count(old)
    if n != 1:
        print(f"### mutation {label}: old occurs {n} times (not applied)\n"); return
    keep = text; (root / rel).write_text(text.replace(old, new))
    try:
        rc, out = run(cmd, f"mutation {label}: {old[:50]!r} -> {new[:50]!r}")
        if expect_prefix is not None:
            hits = [l for l in out.splitlines() if l.startswith(expect_prefix)]
            others = [l for l in out.splitlines() if l.startswith("FAIL") and not l.startswith(expect_prefix)]
            print(f"    expected {expect_prefix!r}: {'RED as expected' if rc == 1 and hits else 'NOT as expected'}; matching lines {len(hits)}, other FAIL lines {len(others)}\n")
    finally:
        (root / rel).write_text(keep)
        assert (root / rel).read_text() == keep
R = MODS[0]; P = [PY, "tools/check_comment_provenance.py", "--base", BASE, *MODS]
mutate("c17 (condition 17: capitalise after the removed label, CH block base L246)", R, "# symmetric with `bind_mutation`'s identical", "# Symmetric with `bind_mutation`'s identical", P, "FAIL (§4.1 (3))")
mutate("c21a (condition 21 (a): join two words that need a space, CH block base L246)", R, "This is a shape check (contract", "This is a shapecheck (contract", P, "FAIL (§4.1 (3))")
mutate("c21c (condition 21 (c): join a backtick-span line wrap with a space, CH block base L470)", R, "`alter_\n        # field` redeclares", "`alter_ field` redeclares", P, "FAIL (§9e)")
# 21 (b): find a `/`-ending wrapped line inside a CH block of this spec
new_r = (root / R).read_text(); spec_r = json.loads((SP / "cs9/cs9-spec-structured.json").read_text()); chs = {x["ch"] for x in spec_r["blocks"]}
cands = []
for b in cp.extract_all_blocks(new_r):
    if b.history_id in chs:
        ls = b.dedented.splitlines()
        for i in range(len(ls) - 1):
            if ls[i].rstrip().endswith("/") and not ls[i].rstrip().endswith(" /") and ls[i + 1].lstrip("# ").strip():
                cands.append((b.history_id, b.start_line + i, ls[i].rstrip()[-30:], ls[i + 1].lstrip("# ")[:20]))
print(f"### 21 (b) candidates (`/` at a line end inside a CH block of this spec): {cands}\n")
if cands:
    ch, line, tail, nxt = cands[0]
    src_lines = new_r.splitlines(keepends=True)
    # locate the physical lines in the new source
    for i in range(len(src_lines) - 1):
        if src_lines[i].rstrip().endswith(tail) and src_lines[i + 1].lstrip().lstrip("#").lstrip().startswith(nxt):
            old = src_lines[i] + src_lines[i + 1]
            indent = src_lines[i + 1][: len(src_lines[i + 1]) - len(src_lines[i + 1].lstrip())]
            new = src_lines[i].rstrip("\n") + " " + src_lines[i + 1].lstrip().lstrip("#").lstrip()
            mutate(f"c21b (condition 21 (b): `/` line wrap joined with a space, {ch})", R, old, new, P, "FAIL (§9e)")
            break
# 29: a removal of a kind we left in place, added in another CH block -> REMOVED rows grow (checker stays green)
mutate("c29 (condition 29: one more allowed removal in CH block base L1077 -> REMOVED rows must grow)", R, "at all (ruling I-7 /\n            # D-4): the guard below", "at all: the guard below", [PY, TOOLS / "cs9_removed_tokens.py", "-C", str(root)])
mutate("c29 (same mutation, checker still green?)", R, "at all (ruling I-7 /\n            # D-4): the guard below", "at all: the guard below", P)
# 5. pins: none expected; print the evidence lines
run(["grep", "-nE", r'\("structured\.py", *[0-9]+|\("platform_declarations\.py", *[0-9]+', "r2db-api/tests/test_l1_details_vocabulary_ast_scan.py", "MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py"], "line-number pins into the two modules (grep; exit 1 = none)")
# 6. restore from backup (cp), sha256 twice
for rel in MODS + COMPS + [CM]:
    subprocess.run(["cp", str(SP / "cs9/backup" / rel), str(root / rel)], check=True)
time.sleep(3)
exp = {l.split()[1]: l.split()[0] for l in (SP / "cs9/backup/sha256.txt").read_text().splitlines()}
for rnd in (1, 2):
    ok = all(sha(rel) == exp[rel] for rel in exp)
    print(f"### restore check {rnd}: {'all 5 files match the base sha256' if ok else 'MISMATCH'}")
run(["git", "status", "--short", "--", *MODS, *COMPS, CM], "git status of the touched paths after restore")
