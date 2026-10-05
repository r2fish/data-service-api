"""cs9_dbless_checks4.py -- final spec: checker/register/removed_tokens, then c29 (A/B), c19a, c23 on the applied tree; restored after."""
import hashlib, re, subprocess, sys, time
from pathlib import Path
root = Path(sys.argv[1]).resolve(); SP = Path(sys.argv[2]); BASE = sys.argv[3]; TOOLS = SP / "cs9/tools"; PY = sys.executable
MODS = ["r2db-api/src/r2db_api/structured.py", "MitateDB-api/src/mitatedb_api/platform_declarations.py"]
COMPS = ["docs/code-history/r2db-api/structured.md", "docs/code-history/MitateDB-api/platform_declarations.md"]
def run(cmd, label, redact=None):
    p = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True); out = (p.stdout + p.stderr).rstrip("\n")
    if redact: out = out.replace(redact, "R-<3 桁、本書には書かない>")
    print(f"### {label}\n$ {' '.join(str(c) for c in cmd)}\n{out}\n(exit {p.returncode})\n"); return p.returncode, out
for name in ("structured", "platform_declarations"):
    run([PY, TOOLS / "cs9_apply.py", "-C", str(root), "--spec", str(SP / f"cs9/cs9-spec-{name}.json")], f"apply {name}")
P = [PY, "tools/check_comment_provenance.py", "--base", BASE, *MODS]; RT = [PY, TOOLS / "cs9_removed_tokens.py", "-C", str(root)]; D = [PY, "tools/check_doc_refs.py"]
run(P, "check_comment_provenance --base (final spec)"); run([PY, "tools/check_comment_provenance.py", "--register"], "check_comment_provenance --register (final spec)")
run(RT, "cs9_removed_tokens (final spec, worktree)")
def mutate(label, rel, old, new, cmds, redact=None):
    text = (root / rel).read_text(); n = text.count(old)
    if n != 1: print(f"### mutation {label}: old occurs {n} times (not applied)\n"); return
    (root / rel).write_text(text.replace(old, new))
    try:
        for cmd, tag in cmds: run(cmd, f"mutation {label} -> {tag}", redact)
    finally:
        (root / rel).write_text(text)
R, M = MODS
mutate("c29 candidate A (CH-1004, base L579: drop the bare-ID paren `(D-4)` of the section header; expected: checker green, REMOVED rows 50 -> 51)", R,
       "# --- contract 1.7.0 dry_run/plan (D-4) ---", "# --- contract 1.7.0 dry_run/plan ---", [(P, "check_comment_provenance --base"), (RT, "cs9_removed_tokens")])
mutate("c29 candidate B (CH-1019, base L1146: drop `, D-3 (2)` from a content paren; expected: checker green, REMOVED rows 50 -> 51)", R,
       "(`operations/<i>/values/<field>`,\n                # D-3 (2)) for any", "(`operations/<i>/values/<field>`) for any", [(P, "check_comment_provenance --base"), (RT, "cs9_removed_tokens")])
mutate("c19a (condition 19 (a): an existing correction record's `old` text (CH-0552, structured.md) is changed to a sentence the basis does not hold)", COMPS[0],
       "(only the LATER deadline-check/audit-hook points below restore `before_*`)", "(only the LATER deadline-check/audit-hook points below restore `after_*`)", [(P, "check_comment_provenance --base")])
num = "R-987"
mutate("c23 (condition 23: a ledger-less 3-digit R number appended inside a fenced block of structured.md)", COMPS[0],
       "# must run first, not merely \"before `schema_revision`\n# advances\".\n```", f"# must run first, not merely \"before `schema_revision`\n# advances\" ({num}).\n```", [(D, "check_doc_refs")], redact=num)
for rel in MODS + COMPS: subprocess.run(["cp", str(SP / "cs9/backup" / rel), str(root / rel)], check=True)
time.sleep(3)
exp = {l.split()[1]: l.split()[0] for l in (SP / "cs9/backup/sha256.txt").read_text().splitlines()}
for rnd in (1, 2): print(f"### restore check {rnd}: {'all match the base sha256' if all(hashlib.sha256((root / r).read_bytes()).hexdigest() == exp[r] for r in MODS + COMPS) else 'MISMATCH'}")
run(["git", "status", "--short", "--", *MODS, *COMPS, "security/CONTROL_MAPPING.md"], "git status after restore")
