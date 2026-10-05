"""cs9_build_spec.py -- builds the two change-set-9 specs (cs9_apply.py format) from an edit table.

usage: python3 cs9_build_spec.py -C REPO --base REV OUT_DIR
Each edit is (block start line at REV, old, new). The builder checks, against
`git show REV:MODULE`, that `old` occurs exactly once inside the block's own
lines (as left by the earlier edits of the same block), that the block has no
CH-ID at REV and is not inside an excluded symbol (the apply tool re-checks).
CH-IDs are assigned in ascending block order from the reserved range.
"""
import argparse, json, subprocess, sys
from pathlib import Path

R2DB = "r2db-api/src/r2db_api/structured.py"
MIT = "MitateDB-api/src/mitatedb_api/platform_declarations.py"

EDITS = {
 R2DB: {
  "companion": "docs/code-history/r2db-api/structured.md",
  "excluded_symbols": ["validate_enum_declaration", "enum_member_matches_type", "normalize_request_for_plan", "compute_plan_token", "normalize_request_for_idempotency", "idempotency_digest"],
  "ch_range": ["CH-0990", "CH-1059"],
  "blocks": [
   (195, [("WP-2 review minor (e): ", "")]),
   (221, [("Phase 6 WP-2 (design D-3(iv)): ", "")]),
   (226, [("Contract 1.7.0 (D-2 (1), WP-2a): ", "Contract 1.7.0 (D-2 (1)): ")]),
   (231, [("Contract 1.7.0 (D-2 (1), WP-2a): ", "Contract 1.7.0 (D-2 (1)): ")]),
   (236, [("WP-2 review M-3: ", "")]),
   (246, [("Review blocker B-1: ", "")]),
   (309, [("(coordinator F2, 2026-09-04 review)", "(coordinator F2)")]),   # trial: date + review inside a content paren
   (328, [("Contract 1.7.0 (D-2 (1), WP-2a): ", "Contract 1.7.0 (D-2 (1)): ")]),
   (338, [("check above. Monitor ruling N-2 (rulings-r2-closure.md,\n                # WP-2a closure): `field` names the request-internal key", "check above. `field` names the request-internal key")]),
   (350, [("Monitor ruling N-2 (rulings-r2-closure.md): same key,", "same key,")]),
   (359, "REJECTED: label has Japanese; the checker counts 53 characters (> 24) over the whole label, scratchpad path included -- FAIL (§4.1 (3)) cannot delete a whole sentence carrying a protected reference", [("Ruling O-3 (`{scratchpad}/rulings-r3-r7-flip.md` 追補4,\n                # 版フリップ監査差し戻し): a `field_constraints` KEY that is", "a `field_constraints` KEY that is")]),
   (444, [("Contract 1.7.0 (D-2 (1), WP-2a): ", "Contract 1.7.0 (D-2 (1)): ")]),
   (470, [("Contract 1.7.0 (D-2 (5), WP-2a; monitor ruling A/B-2): ", "Contract 1.7.0 (D-2 (5); monitor ruling A/B-2): ")]),
   (514, [("Monitor ruling A: `enum: null`", "`enum: null`")]),
   (579, [("dry_run/plan (D-4, WP-2b) ", "dry_run/plan (D-4) ")]),   # a 2nd edit (依頼者裁定 2026-09-03 案(a) -> 依頼者裁定 案(a)) was REJECTED: FAIL (§4.1 (3)) cannot delete a whole sentence carrying a protected reference (CJK join normalisation)
   (636, "REJECTED: date-only removal; the CJK join normalisation turns the retained `依頼者裁定 案(a)` into `依頼者裁定案(a)` -- FAIL (§4.1 (3)) retained text has no order-preserving match", [("(依頼者裁定 2026-09-03 案(a))", "(依頼者裁定 案(a))")]),   # trial: date only (WP-2c stays: "not by this WP")
   (728, "REJECTED: label has 6 content words (Ruling, L-6/M-6, addendum, 2, closure, audit) -- FAIL (§4.1 (3)) retained text has no order-preserving match", [("Ruling L-6/M-6 (`{scratchpad}/rulings-r3-r7-flip.md` addendum 2,\n    WP-2e closure audit R-1): a record written", "a record written")]),
   (757, [("Contract 1.7.0 (D-2 (4), WP-2a): ", "Contract 1.7.0 (D-2 (4)): ")]),
   (779, "REJECTED: paren with `=` (U-3 = (A)) -- FAIL (§4.1 (3)) cannot delete a whole sentence carrying a protected reference", [("ruling I-1, WP-2c): ", "ruling I-1): ")]),
   (827, [("(contract 1.7.0 D-5, WP-2c)", "(contract 1.7.0 D-5)")]),
   (891, [("WP-2 review minor (c): ", "")]),
   (950, [("`catalog()` below (WP-2b) so", "`catalog()` below so")]),
   (967, [("Contract 1.7.0 (D-2 (1), WP-2a): ", "Contract 1.7.0 (D-2 (1)): ")]),
   (1010, [("Ruling U-7 (WP-6d): thin lock wrapper", "thin lock wrapper")]),
   (1039, [("(contract 1.7.0, D-4, WP-2b):", "(contract 1.7.0, D-4):")]),
   (1077, [("ruling I-3, WP-2c): ", "ruling I-3): ")]),
   (1109, [("(D-7 (3), WP-2e): ", "(D-7 (3)): ")]),
   (1129, [("Phase 4 (design D-2): whether", "whether")]),
   (1139, [("WP-2 review M-2: per-operation", "per-operation")]),
   (1146, [("Monitor ruling M-3/D (rulings-wp2a-review.md, rulings-\n                # wp3a-review.md D): `operation_index`", "`operation_index`")]),
   (1183, [("Phase 4 (design D-2/D-10): the pre-commit", "the pre-commit")]),
   (1195, "REJECTED: paren with `/` ((1)(i)/(3)) -- FAIL (§4.1 (3)) cannot delete a whole sentence carrying a protected reference", [("ruling I-1, WP-2c): ", "ruling I-1): ")]),
   (1209, [("(D-7 (3), WP-2e): ", "(D-7 (3)): ")]),
   (1225, [("(D-2 (4), WP-2a): ", "(D-2 (4)): ")]),
   (1232, [("Monitor ruling M-3/D (rulings-wp2a-review.md, D-3 (2)): every", "every")]),
   (1301, [("Phase 4 (design D-2): reaching", "reaching")]),
   (1461, [("Ruling U-7 (WP-6d): thin lock wrapper", "thin lock wrapper")]),
   (1488, [("(contract 1.7.0, D-4, WP-2b):", "(contract 1.7.0, D-4):"), ("review round F-8 (`{scratchpad}/\n        rulings-r4.md`): a bare `int`", "review round F-8: a bare `int`")]),
   (1505, "REJECTED: paren with `/` ((8)/(9)) -- FAIL (§4.1 (3)) cannot delete a whole sentence carrying a protected reference", [("ruling I-3, WP-2c):", "ruling I-3):")]),
   (1543, [("WP-2 review M-2: indexes", "indexes")]),
   (1557, "REJECTED: paren with `=` (U-1 = (β)) -- FAIL (§4.1 (3)) cannot delete a whole sentence carrying a protected reference", [("U-1 = (β), WP-2a): ", "U-1 = (β)): ")]),
   (1573, "REJECTED: paren with `/` ((7)/(3), S-a/S-j) -- FAIL (§4.1 (3)) cannot delete a whole sentence carrying a protected reference", [("addendum 2 S-a/S-j, WP-2b): ", "addendum 2 S-a/S-j): ")]),
   (1848, "REJECTED: paren with `/` ((1)(i)/(3)) -- FAIL (§4.1 (3)) cannot delete a whole sentence carrying a protected reference", [("ruling I-1, WP-2c): ", "ruling I-1): ")]),
   (1856, [("(D-7 (3), WP-2e): ", "(D-7 (3)): ")]),
   (1862, [("Review round F-8: always", "always")]),
   (1159, "REJECTED (tried after the first run, so it takes the last number of the first assignment + 1 rather than shifting the others -- Y7-16): paren with `/` ((2)/(4)) -- FAIL (§4.1 (3)) cannot delete a whole sentence carrying a protected reference", [("Contract 1.7.0 (D-4 (2)/(4), WP-2b): ", "Contract 1.7.0 (D-4 (2)/(4)): ")]),
  ]},
 MIT: {
  "companion": "docs/code-history/MitateDB-api/platform_declarations.md",
  "excluded_symbols": None,  # filled from the isomorphic table below
  "ch_range": ["CH-1060", "CH-1129"],
  "blocks": [
   (1, [("(no cross-peer sharing, requester\nruling 2026-09-03)", "(no cross-peer sharing)")]),   # trial: ruling-date phrase inside a content paren
   (69, "REJECTED: ruling-date phrase inside a content paren whose `: ` follows -- FAIL (§4.1 (3)) retained text has no order-preserving match", [("allocation, requester ruling\n#: 2026-09-05: MitateDB", "allocation: MitateDB")]),   # trial: ruling-date phrase inside a content paren
   (77, [("#: Phase 10 WP-6b (design D-5 (ii)): the platform", "#: the platform")]),
   (525, "REJECTED: ruling-date phrase at a sentence end, outside any paren (no allowed operation) -- FAIL (§4.1 (3)) cannot delete a whole sentence carrying a protected reference", [("design\n# D-2(f), monitor ruling 2026-09-05.", "design\n# D-2(f).")]),   # trial: ruling-date phrase at a sentence end (not a paren)
   (656, [("(design D-1(c) amendment 2026-09-05)", "(design D-1(c) amendment)")]),   # trial: date only inside a content paren
   (862, [("WP-3e rework T3 (ruling\n#: `{scratchpad}/rulings-r3-r7-flip.md` L-2/M-7) removed this module's\n#: former", "WP-3e rework T3 removed this\n#: module's former")]),
   (887, [("(Phase 10 WP-4f, supervisor ruling 2026-09-09; peer-symmetric", "(peer-symmetric")]),   # trial: tokens + ruling date inside a content paren
   (1068, [("# M-1 (WP-4 integration review 2026-09-10): a role", "# a role")]),
  ]},
}


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("-C", dest="root", required=True); ap.add_argument("--base", required=True); ap.add_argument("out_dir")
    ns = ap.parse_args(); root = Path(ns.root).resolve(); sys.path.insert(0, str(root / "tools"))
    import check_comment_provenance as cp
    import ast
    def show(rel): return subprocess.run(["git", "-C", str(root), "show", f"{ns.base}:{rel}"], capture_output=True, text=True, check=True).stdout
    def helpers(peer, module_rel):
        col = 0 if peer == "r2db-api" else 1; out = set()
        for p in ("r2db-api/tests/test_audit_query.py", "MitateDB-api/tests/test_audit_query.py"):
            for node in ast.walk(ast.parse(show(p))):
                tgt = node.target if isinstance(node, ast.AnnAssign) else (node.targets[0] if isinstance(node, ast.Assign) else None)
                if isinstance(tgt, ast.Name) and tgt.id == "_ISOMORPHIC_TARGETS":
                    for e in node.value.elts:
                        row = ast.literal_eval(e)
                        if row[col] == module_rel: out.add(row[2])
        return sorted(out)
    ok = True
    for module, cfg in EDITS.items():
        src = show(module); lines = src.splitlines(keepends=True)
        by_line = {b.start_line: b for b in cp.extract_all_blocks(src)}
        peer = module.split("/", 1)[0]
        excluded = cfg["excluded_symbols"] or helpers(peer, module.split("/", 1)[1])
        assert sorted(excluded) == helpers(peer, module.split("/", 1)[1]), module
        lo = int(cfg["ch_range"][0][3:])
        blocks = []
        rejected = []
        for n, entry in enumerate(cfg["blocks"]):
            if len(entry) == 3:
                line, reason, edits = entry
                rejected.append((f"CH-{lo + n:04d}", line, reason, edits)); continue
            line, edits = entry
            blk = by_line.get(line)
            if blk is None: print(f"{module}: no block at L{line}"); ok = False; continue
            if blk.history_id: print(f"{module}: L{line} carries {blk.history_id}"); ok = False
            region = "".join(lines[blk.start_line - 1: blk.end_line])
            for old, new in edits:
                c = region.count(old)
                if c != 1: print(f"{module}: L{line}: old occurs {c} times: {old[:60]!r}"); ok = False
                region = region.replace(old, new)
            blocks.append({"ch": f"CH-{lo + n:04d}", "line": line, "edits": [{"old": o, "new": nw} for o, nw in edits]})
        spec = {"base": ns.base, "parent": ns.base, "module": module, "companion": cfg["companion"], "excluded_symbols": excluded,
                "line_range": [1, len(lines)], "ch_range": cfg["ch_range"], "blocks": blocks}
        name = "structured" if "structured" in module else "platform_declarations"
        Path(ns.out_dir, f"cs9-rejected-{name}.json").write_text(json.dumps([{"ch_reserved_unused": c, "line": l, "reason": r, "edits": [{"old": o, "new": nw} for o, nw in e]} for c, l, r, e in rejected], ensure_ascii=False, indent=1) + "\n")
        print(f"{module}: rejected (numbers kept vacant): {[(c, l) for c, l, _, _ in rejected]}")
        Path(ns.out_dir, f"cs9-spec-{name}.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1) + "\n")
        print(f"{module}: {len(blocks)} blocks, {sum(len(b['edits']) for b in blocks)} edits, CH {blocks[0]['ch']}..{blocks[-1]['ch']}, excluded {len(excluded)} -> cs9-spec-{name}.json")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
