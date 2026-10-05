"""cs9_dbless_checks2.py -- follow-up CLI red checks (conditions 29 and 20), applied tree, restored after."""
import hashlib, subprocess, sys, time
from pathlib import Path
root = Path(sys.argv[1]).resolve(); SP = Path(sys.argv[2]); BASE = sys.argv[3]; TOOLS = SP / "cs9/tools"; PY = sys.executable
MODS = ["r2db-api/src/r2db_api/structured.py", "MitateDB-api/src/mitatedb_api/platform_declarations.py"]
COMPS = ["docs/code-history/r2db-api/structured.md", "docs/code-history/MitateDB-api/platform_declarations.md"]
def run(cmd, label):
    p = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True); out = (p.stdout + p.stderr).rstrip("\n")
    print(f"### {label}\n$ {' '.join(str(c) for c in cmd)}\n{out}\n(exit {p.returncode})\n"); return p.returncode, out
for name in ("structured", "platform_declarations"):
    run([PY, TOOLS / "cs9_apply.py", "-C", str(root), "--spec", str(SP / f"cs9/cs9-spec-{name}.json")], f"apply {name}")
P = [PY, "tools/check_comment_provenance.py", "--base", BASE, *MODS]; RT = [PY, TOOLS / "cs9_removed_tokens.py", "-C", str(root)]
def mutate(label, rel, old, new, cmds):
    text = (root / rel).read_text(); n = text.count(old)
    if n != 1: print(f"### mutation {label}: old occurs {n} times (not applied)\n"); return
    (root / rel).write_text(text.replace(old, new))
    try:
        for cmd, tag in cmds: run(cmd, f"mutation {label} -> {tag}")
    finally:
        (root / rel).write_text(text)
R, M = MODS
_, base_rt = run(RT, "cs9_removed_tokens before the c29 mutation (SUMMARY line is the reference)")
mutate("c29 (condition 29: one more allowed removal, CH-1016 base L1077-1085: drop `(ruling I-7 / D-4)` -> REMOVED rows must grow by 2)", R,
       "at all (ruling I-7 /\n        # D-4): the guard below", "at all: the guard below", [(RT, "cs9_removed_tokens"), (P, "check_comment_provenance --base (must stay green: the removal is allowed)")])
mutate("c20 (condition 20: a `#:` line of the CH `#:` block base L77-82 becomes `#`)", M, "#: the platform single-shot migration that widens", "# the platform single-shot migration that widens", [(P, "check_comment_provenance --base")])
mutate("c15-style sanity (CH-less block loses a sentence: base L306 `(a)` line removed) -- expected FAIL (§4.1 (2))", R, "                # (a) a name field_types declares that `fields` never named.\n", "", [(P, "check_comment_provenance --base")])
for rel in MODS + COMPS: subprocess.run(["cp", str(SP / "cs9/backup" / rel), str(root / rel)], check=True)
time.sleep(3)
exp = {l.split()[1]: l.split()[0] for l in (SP / "cs9/backup/sha256.txt").read_text().splitlines()}
for rnd in (1, 2): print(f"### restore check {rnd}: {'all match the base sha256' if all(hashlib.sha256((root / r).read_bytes()).hexdigest() == exp[r] for r in MODS + COMPS) else 'MISMATCH'}")
run(["git", "status", "--short", "--", *MODS, *COMPS, "security/CONTROL_MAPPING.md"], "git status after restore")
