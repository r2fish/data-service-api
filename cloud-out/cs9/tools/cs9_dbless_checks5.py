"""cs9_dbless_checks5.py -- Y9-3 measurement: does the checker accept removing the 2nd-paragraph label `Review round F-5 (...)` of base L1039-1069 (CH-1014)? Applied tree, restored after."""
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
P = [PY, "tools/check_comment_provenance.py", "--base", BASE, *MODS]
R = MODS[0]; text = (root / R).read_text()
old = "Review round F-5 (`{scratchpad}/rulings-r4.md`): `service.py`"; new = "`service.py`"
n = text.count(old); print(f"### Y9-3 trial: old occurs {n} time(s)")
if n == 1:
    (root / R).write_text(text.replace(old, new))
    try: run(P, "Y9-3 trial: 2nd-paragraph label `Review round F-5 (`{scratchpad}/rulings-r4.md`): ` removed (CH-1014) -> does the checker accept it?")
    finally: (root / R).write_text(text)
old2 = "Review round F-5: only computed when"; new2 = "only computed when"
n2 = text.count(old2); print(f"### Y9-3 trial 2 (L1573-1580, CH-less): old occurs {n2} time(s) -- a CH-less block cannot be edited without a CH-ID, so only the label form is noted; not applied")
for rel in MODS + COMPS: subprocess.run(["cp", str(SP / "cs9/backup" / rel), str(root / rel)], check=True)
time.sleep(3)
exp = {l.split()[1]: l.split()[0] for l in (SP / "cs9/backup/sha256.txt").read_text().splitlines()}
for rnd in (1, 2): print(f"### restore check {rnd}: {'all match the base sha256' if all(hashlib.sha256((root / r).read_bytes()).hexdigest() == exp[r] for r in MODS + COMPS) else 'MISMATCH'}")
run(["git", "status", "--short"], "git status after restore (whole tree)")
