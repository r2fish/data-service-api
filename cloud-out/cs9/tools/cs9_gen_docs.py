"""cs9_gen_docs.py -- renders judgement-<module>.md and measure.md for change set 9 from the measurement JSON,
the specs, the rejected lists, the removed-token rows and the per-block decisions written below.
usage: python3 cs9_gen_docs.py -C REPO --sp SP_DIR --out OUT_DIR
"""
import argparse, json, re, subprocess, sys
from pathlib import Path
ap = argparse.ArgumentParser(); ap.add_argument("-C", dest="root", required=True); ap.add_argument("--sp", required=True); ap.add_argument("--out", required=True)
ns = ap.parse_args(); root = Path(ns.root).resolve(); SP = Path(ns.sp); OUT = Path(ns.out); BASE = "092e1a1"
sys.path.insert(0, str(root / "tools")); import check_comment_provenance as cp
M = json.load(open(SP / "cs9/measure.json"))
R2 = "r2db-api/src/r2db_api/structured.py"; MT = "MitateDB-api/src/mitatedb_api/platform_declarations.py"
SHORT = {R2: "structured", MT: "platform_declarations"}
CHECK_WORDS = re.compile(r"\b(such|this|that|instead|exactly as|again|still|also|otherwise|then)\b|その|これ|再び|なお", re.IGNORECASE)

def show(rel): return subprocess.run(["git", "-C", str(root), "show", f"{BASE}:{rel}"], capture_output=True, text=True, check=True).stdout

# ---------------------------------------------------------------------------------------------
# per-block decisions (key = base start line). kind: "move" (in spec), "keep", "rejected", "iv"
# ---------------------------------------------------------------------------------------------
VERS = "版数付き文書名 `Contract 1.7.0` と同じ括弧から経緯トークン {tok} 1 語とその区切りを (4) で除く。{ids} は版数付き文書名と同じ括弧に残り保護される。残る文は `this WP` でも名指しでも {tok} を指さない"
DEC = {R2: {
 81: ("keep", "ラベル `CCR-13 WP-5b: ` は保護参照 CCR-13 を含み除外 2。`WP-2〜WP-5` は文中 (括弧でもラベルでもない) で許容操作に当たらない。同じ文に実在パス `R2DB_CCR13_STORAGE_V1.md` (保護参照) と現在の挙動 (`DataService` が境界と cell の決定だけを晒す) が同居", "除去なし (基準のまま)", None),
 187: ("keep", "ラベル `WP-2(b) fix round 2 (coordinator item C): ` は内容語 fix / coordinator / item / C の 4 語で §8.1 条件 3 を満たさない。識別子検査の安全上の理由 (reserved by EXACT match at this ONE choke point) と同居", "除去なし (基準のまま)", "(iii)"),
 195: ("move", "文頭ラベル `WP-2 review minor (e): ` (経緯トークン WP-2・review、内容語 minor 1) を (6) で除く。残る文は `previously` の経緯と現在の規則 (`revision` を黙って無視しない) の同居文なので文は残す。残る文はラベルの WP・review を名指しも指示語でも指さない。minor は module 内の他所で現行の区分名として使われない (L891 の同形ラベルだけ)", "`revision` was previously an accepted-but-unused key … -- 読める", None),
 202: ("keep", "第 1 段落のラベル `R-2 (corrigendum m-1): ` は経緯トークン 0 の裸 ID だけで、R-2 / m-1 の決定 (`field_type` は `add_field` だけ) を指す唯一の手掛かり。第 2 段落の版数付き括弧 `(D-2 (5), work order §2 WP-2a \"実装の指示\")` の WP-2a は、残る文の `this WP's own \"実装の指示\"` が指す位置指定 (Y7-3 (b))", "除去なし (基準のまま)", "ID-only / this WP"),
 221: ("move", "文頭ラベル `Phase 6 WP-2 (design D-3(iv)): ` (経緯トークン Phase 6・WP-2、裸 ID D-3(iv) は設計名を持たない) を (6) で除く。残る文は `field_types` の受理規則で、design・D-3・Phase 6 を名指しも指示語でも指さない (`immediately above` は L202-212 の規則を指す位置語)", "`field_types` (the per-field map) is accepted only by `create_entity` … -- 読める", None),
 226: ("move", VERS.format(tok="WP-2a", ids="D-2 (1)"), "`Contract 1.7.0 (D-2 (1)): `field_constraints` …` -- 読める", None),
 231: ("move", VERS.format(tok="WP-2a", ids="D-2 (1)"), "同上", None),
 236: ("move", "文頭ラベル `WP-2 review M-3: ` (経緯トークン WP-2・review、裸 ID M-3) を (6) で除く。残る文 (`index`/`unique` は `create_index` だけに意味を持つ) は M-3 を名指さず、`field_type` above で L202-212 を指す", "`index`/`unique` are meaningful only to `create_index` … -- 読める", None),
 246: ("move", "文頭ラベル `Review blocker B-1: ` (blocker は設計 §4.1 (5) の語、裸 ID B-1) を (6) で除く。残る文は契約参照 (`SchemaOperationRequest.destructive`、`evaluation_order`) と現在の規則を述べ、B-1 を名指さない", "symmetric with `bind_mutation`'s identical check above … -- 読める (小文字始まりは逐語)", None),
 272: ("keep", "ラベル `Ruling N-1: ` は経緯トークン 0 の裸 ID。残る文が `N-1's own example`・`(N-1: \"有効な識別子…\")` で N-1 を 2 回名指す (Y7-3 (b))", "除去なし (基準のまま)", "ID-only (名指し)"),
 284: ("keep", "ラベル `Phase 6 WP-2 (design D-3(iv)): ` は検査器が許す候補だが、残る文の `decision (ii)'s default` と `design's own enumeration` が設計名の無いまま design D-3(iv) に寄りかかる", "除去なし (基準のまま)", "(i)"),
 309: ("move", "括弧 `(coordinator F2, 2026-09-04 review)` から日付と review (ともに §4.1 (5) の語) を区切りごと除く (検査器が受け付けた)。残る `(coordinator F2)` は指摘の番号で、文は `isinstance` を先に検査する現在の理由を述べる", "checked FIRST (coordinator F2): `in` against `FIELD_TYPES` … -- 読める", None),
 322: ("keep", "ラベル `Decision (v1.3 G11): ` は版数付き文書名 (除外 2)。経緯トークン 0", "除去なし (基準のまま)", None),
 328: ("move", VERS.format(tok="WP-2a", ids="D-2 (1)") + "。残る文の `D-2 (2)'s own default` は D-2 を名指すが D-2 は残る", "`Contract 1.7.0 (D-2 (1)): `field_constraints` is an OPTIONAL … -- 読める", None),
 338: ("move", "第 2 文の文頭ラベル `Monitor ruling N-2 (rulings-r2-closure.md, WP-2a closure): ` (経緯トークン monitor ruling・WP-2a、非実在ファイル名 rulings-r2-closure.md はトークン、裸 ID N-2、内容語 closure 1) を (6) で除く。2 行にまたがるので除去に接する 2 行を手で切り直した。文頭でない位置: 直前の文 `Mirrors `field_types`'s identical \"sent without fields\" check above.` にラベル・見出しは無い ((ii) に当たらない)。残る文は N-2 を名指さない", "check above. `field` names the request-internal key this whole clause hangs off … -- 読める", None),
 350: ("move", "文頭ラベル `Monitor ruling N-2 (rulings-r2-closure.md): ` を (6) で除く。残る文 `same key, same reason as the \"requires fields\" branch above.` は L338-342 の規則を位置で指し、N-2 を名指さない (小文字始まりは逐語)", "same key, same reason as the \"requires fields\" branch above. -- 省略形だが基準でも同じ省略形", None),
 359: ("rejected", "ラベル `Ruling O-3 (`{scratchpad}/rulings-r3-r7-flip.md` 追補4, 版フリップ監査差し戻し): ` は日本語を含むため検査器が文字数で数え、ラベル全体 (scratchpad パスを含む) で 53 文字 > 24 (§8.1 条件 2) となり (6) に当たらない。文は SI-10 (保護参照) を含み丸ごとは消せない。作業ノートの参照 (L359) はこのため残る", "除去なし (基準のまま)", "検査器が拒んだ"),
 378: ("keep", "ラベル `Monitor ruling m-1 (rulings-wp2a-review.md, contract corrigendum, verbatim list of `constraint_declaration` cases): ` は内容語 (contract / corrigendum / verbatim / list / cases) が 3 語を超え (6) に当たらない。後続の引用はこのラベルの出所に寄りかかる", "除去なし (基準のまま)", "(iii)"),
 397: ("keep", "ラベル `Monitor ruling E (rulings-wp3a-review.md, applied to r2db by M-3/rulings-wp2a-review.md): ` は内容語 (applied / to / r2db / by、E は ID 文法に当たらない) が 3 語を超える。残る文は MitateDB `cell.py` の同形を指す参照", "除去なし (基準のまま)", "(iii)"),
 433: ("keep", "`Coordinator F2: ` は経緯トークンも ID 文法に当たる語も含まず (6) のラベルではない。括弧 `(not a WP-2 regression)` は否定語 (除外 1) と内容語を含む。`this scalar sibling`・`the same fix` は L309-319 の F2 を指す", "除去なし (基準のまま)", None),
 441: ("keep", "ラベル `Decision (v1.3 G11): ` は版数付き文書名 (除外 2)", "除去なし (基準のまま)", None),
 444: ("move", VERS.format(tok="WP-2a", ids="D-2 (1)"), "`Contract 1.7.0 (D-2 (1)): `add_field`'s own single-field … -- 読める", None),
 458: ("keep", "ラベル `Monitor ruling A (rulings-wp3a-review.md, applied to r2db by rulings-wp2a-review.md B-2): ` は内容語が 3 語を超える (applied / to / r2db / by)。引用 \"add_field で enum: null = enum 無し\" はこのラベルの出所に寄りかかる", "除去なし (基準のまま)", "(iii)"),
 470: ("move", "版数付き括弧 `(D-2 (5), WP-2a; monitor ruling A/B-2)` から WP-2a と区切り `, ` を (4) で除く。`monitor ruling` も経緯トークンだが、除くと `A/B-2` の断片だけが残るので残す (Y7-3 (b) 「種類語や断片だけが残る」)。残る 2 段落は現在の PATCH 規則と bind 時に検査しない理由", "`Contract 1.7.0 (D-2 (5); monitor ruling A/B-2): `alter_field` redeclares … -- 読める", None),
 488: ("keep", "ラベル `Monitor ruling N-1 (rulings-r2-closure.md, contract corrigendum 3, verbatim): ` は内容語 contract / corrigendum / verbatim を含み、直後の引用文の出所 (訂正 3 の逐語) を担う。除くと引用の出所が落ちる", "除去なし (基準のまま)", "(iii)"),
 514: ("move", "文頭ラベル `Monitor ruling A: ` (経緯トークン monitor ruling。A は ID 文法に当たらず内容語 1) を (6) で除く。残る文 `enum: null` clears the field's enum. は現在の規則で A を名指さない (L458・L470 の `monitor ruling A/B-2` は別の塊)", "`enum: null` clears the field's enum. -- 読める", None),
 532: ("keep", "ラベル `R-5: ` は経緯トークン 0 の裸 ID で、index 名の合成規則の決定を指す唯一の手掛かり。括弧 `(corrigendum m-2)` の corrigendum は §9 規則 3 の種類語ではない", "除去なし (基準のまま)", "ID-only"),
 549: ("keep", "ラベル `Ruling N-1: ` は経緯トークン 0 の裸 ID で、残る文 `same reasoning as create_entity's fields loop above` が L272-277 (N-1 を名指す塊) を指す。唯一の手掛かり", "除去なし (基準のまま)", "ID-only"),
 554: ("keep", "ラベル `WP-2 review M-5: ` は検査器が許す候補だが、残る文の `(§2)` が設計名を持たず、ラベルの WP-2 がその節の出所の唯一の手掛かり。C-17 (保護参照) と `R-3` を含む文は残す", "除去なし (基準のまま)", "(i)"),
 579: ("move", "見出し行の括弧 `(D-4, WP-2b)` から WP-2b を (4) で除く (`contract 1.7.0` と同じ行だが括弧の外。D-4 は裸のまま残る)。ラベル `Peer symmetry (work order §2 WP-2b \"同型性テストの対象\")` は内容語 (Peer symmetry) と WP の位置指定を持ち残す。括弧 `(依頼者裁定 2026-09-03 案(a))` の日付だけの除去は検査器が拒んだ (CJK 連結の正規化で `依頼者裁定 案(a)` が `依頼者裁定案(a)` になり、基準から導けない)", "`# --- contract 1.7.0 dry_run/plan (D-4) ---` -- 読める。日付は基準のまま", "日付: 検査器が拒んだ"),
 636: ("rejected", "括弧 `(依頼者裁定 2026-09-03 案(a))` の日付だけの除去を検査器が拒んだ (CJK 連結の正規化、L579 と同じ)。見出しの `(D-5, WP-2c)` の WP-2c は、残る文 `not by this WP` が指す位置指定なので除かない (Y7-3 (b))。内容の除去が 0 なので基準のバイト列のまま、CH-1005 は欠番", "除去なし (基準のまま)", "検査器が拒んだ / this WP"),
 667: ("keep", "ラベル `Ruling I-12/adapter port v1.11 compatibility: ` は版数付き文書名 (port v1.11) を含み除外 2。経緯トークン 0。実在パス `conformance/conformance_adapter_r2db.py` を含む", "除去なし (基準のまま)", None),
 708: ("keep", "括弧 `(ruling I-1: \"in-memory 参照 cell はプロセス内 dict\"; …)`・`(ruling I-8: \"記録した応答 object 全体…\")` は引用の内容語を含み (4) で括弧ごとは消えない。経緯トークン 0", "除去なし (基準のまま)", None),
 728: ("rejected", "ラベル `Ruling L-6/M-6 (`{scratchpad}/rulings-r3-r7-flip.md` addendum 2, WP-2e closure audit R-1): ` は検査器の数え方で内容語 6 (Ruling / L-6/M-6 / addendum / 2 / closure / audit) となり条件 3 を満たさない。文は `contract `versioning.version_binding`` の現在の条件と同居。作業ノートの参照 (L728) はこのため残る", "除去なし (基準のまま)", "検査器が拒んだ"),
 750: ("keep", "括弧 `(R-3/R-4: never a known/selectable field)` は否定語と内容語を含む。経緯トークン 0", "除去なし (基準のまま)", None),
 754: ("keep", "括弧 `(R-5)` は経緯トークン 0 の裸 ID だけで、uniqueness key の決定を指す唯一の手掛かり", "除去なし (基準のまま)", "ID-only"),
 757: ("move", VERS.format(tok="WP-2a", ids="D-2 (4)"), "`Contract 1.7.0 (D-2 (4)): entity -> field_name -> FieldConstraints …` -- 読める", None),
 768: ("keep", "括弧 `(R-1: address_reuse is \"never\" -- …)`・`(R-1: reuse is scoped …)` は内容語を含む。経緯トークン 0。ROLLBACK の理由と同居", "除去なし (基準のまま)", None),
 779: ("rejected", "版数付き括弧 `(D-5 (6), U-3 = (A), ruling I-1, WP-2c)` から WP-2c を除く編集を検査器が拒んだ (`U-3 = (A)` の `=` を含む括弧。FAIL (§4.1 (3)) cannot delete a whole sentence carrying a protected reference)。内容の除去が 0 なので基準のまま、CH-1008 は欠番", "除去なし (基準のまま)", "検査器が拒んだ"),
 788: ("keep", "ラベル `Ruling U-7 (`{scratchpad}/review2/frame.md` F-①, WP-6d): ` は検査器が許す候補だが、残る文が `ruling U-7 explicitly allows \"per cell\"` と `nothing before this ruling prevented` で U-7 を名指す (Y7-3 (b))。L1010・L1461 が `_idempotency_lock`'s own field comment で指す参照先。lock の安全上の理由。作業ノートの参照 (L788) はこのため残る", "除去なし (基準のまま)", "名指し (Y7-3 (b))"),
 821: ("keep", "ラベル `m-9: ` は経緯トークン 0 の裸 ID で、seed row の経路の決定を指す唯一の手掛かり", "除去なし (基準のまま)", "ID-only"),
 827: ("move", "見出し `# ---- idempotency (contract 1.7.0 D-5, WP-2c) ----` の版数付き括弧から WP-2c を (4) で除く", "`# ---- idempotency (contract 1.7.0 D-5) ----` -- 読める", None),
 830: ("keep", "ラベル `Ruling I-6: ` は経緯トークン 0 の裸 ID で、lazy reclaim の決定を指す唯一の手掛かり。禁止事項 5 の引用と同居", "除去なし (基準のまま)", "ID-only"),
 844: ("keep", "ラベル `Ruling I-6/D-5 (5): ` は経緯トークン 0 の裸 ID。残る文は `this is called from … before target existence` の順序 (安全上の理由) を述べる", "除去なし (基準のまま)", "ID-only"),
 876: ("keep", "ラベル `WP-2(b) fix round 2 (coordinator item C): ` は内容語 4 語で (6) に当たらない (L187-192 と同形)。identifier 位置の予約名拒否 (安全) と同居", "除去なし (基準のまま)", "(iii)"),
 891: ("move", "文頭ラベル `WP-2 review minor (c): ` を (6) で除く (L195 と同形)。残る文は order_by の複雑度の現在の数え方で、WP・review を名指さない", "order_by clauses count toward query complexity like select/where terms already do … -- 読める", None),
 898: ("keep", "ラベル `R-7, corrigendum M-9: ` は経緯トークン 0 の裸 ID で、型検査を先に行う決定を指す唯一の手掛かり", "除去なし (基準のまま)", "ID-only"),
 906: ("keep", "ラベル `M-2 (`{scratchpad}/audit-wp2e-2.md` R-3): ` は検査器が許す候補だが、残る文 `this catch's pre-M-2 `violated_declaration`` が M-2 を名指す (Y7-3 (b))。作業ノートの参照 (L906) はこのため残る。`module docstring's own documented divergence` の指す先は module docstring (L1、1 行) に無い (移動前からの穴)", "除去なし (基準のまま)", "名指し (Y7-3 (b))"),
 918: ("keep", "ラベル `keyset paging (design D-3 (3), D-6): ` の `keyset paging` は L925・L930 の見出しにも使う現行の区分名 ((iii))。経緯トークン 0", "除去なし (基準のまま)", "(iii)"),
 962: ("keep", "ラベル `Phase 6 WP-2 (design D-3(iii)): ` は検査器が許す候補だが、残る文の `decision (ii)'s own default` が設計名の無いまま寄りかかる", "除去なし (基準のまま)", "(i)"),
 967: ("move", VERS.format(tok="WP-2a", ids="D-2 (1)") + "。残る文の `(D-2 (4): \"catalog は…\")` は残る", "`Contract 1.7.0 (D-2 (1)): total over `fields` …` -- 読める", None),
 1010: ("move", "文頭ラベル `Ruling U-7 (WP-6d): ` (経緯トークン WP-6d、裸 ID U-7、Ruling は内容語 1) を (6) で除く。残る文は U-7 を名指さず、`see `_idempotency_lock`'s own field comment above` で L788-798 (U-7 を名指す塊、基準のまま) を指す。docstring 先頭は小文字 `thin lock wrapper` になる (変形しない)", "thin lock wrapper -- `self._idempotency_lock` is held for this call's entire duration … -- 読める", None),
 1039: ("move", "第 1 段落の版数付き括弧 `(contract 1.7.0, D-4, WP-2b)` から WP-2b を (4) で除く。見送り 2 件: (a) 第 2 段落の文頭ラベル `Review round F-5 (`{scratchpad}/rulings-r4.md`): ` は検査器が許す候補だが、直前の段落のラベル `(contract 1.7.0, D-4):` が残るので、F-5 の段落が D-4 の記述の続きに読める ((ii)。18.5 の裁定点)。(b) 括弧内の `H-1, `{scratchpad}/rulings-r4.md` addendum 2:` は内容を持つ括弧の中で、パスだけ除くと `addendum 2` の指す先が無くなる。`A plain apply pays no …` は r2db `tests/test_dry_run_and_plan.py:332` が指す参照先で残る", "`dry_run`/`plan`/`plan_request` (contract 1.7.0, D-4): `dry_run` walks every gate … -- 読める", "(ii) 見送り 1 件"),
 1077: ("move", VERS.format(tok="WP-2c", ids="D-5 (8)・S-b・I-3"), "`Contract 1.7.0 (D-5 (8), addendum 2 S-b, ruling I-3): the idempotency lookup sits HERE …` -- 読める", None),
 1093: ("keep", "ラベル `L-6/M-6: ` は経緯トークン 0 の裸 ID。pre-1.7.0 record の扱いの決定を指す唯一の手掛かり", "除去なし (基準のまま)", "ID-only"),
 1102: ("keep", "ラベル `Ruling I-3/I-8: ` は経緯トークン 0 の裸 ID。replay で実行しない決定の唯一の手掛かり", "除去なし (基準のまま)", "ID-only"),
 1109: ("move", VERS.format(tok="WP-2e", ids="D-7 (3)"), "`Contract 1.7.0 (D-7 (3)): the ORIGINAL execution's own `request_id` …` -- 読める", None),
 1115: ("keep", "ラベル `Ruling I-6/D-5 (5): ` は経緯トークン 0 の裸 ID。capacity を先に検査する順序 (安全) の唯一の手掛かり", "除去なし (基準のまま)", "ID-only"),
 1129: ("move", "文頭ラベル `Phase 4 (design D-2): ` を (6) で除く。残る文は `DESTRUCTIVE_CONFIRMATION_V1` (設計名) を自ら名指し、D-2・Phase 4 を名指さない。r2db `postgres.py:1765` が `ApplicationCell.transact`'s identical comment で指す参照先で、文は残る", "whether this batch passed through the DESTRUCTIVE_CONFIRMATION_V1 choke -- what `MutationOutcome.destructive` reports. … -- 読める", None),
 1139: ("move", "文頭ラベル `WP-2 review M-2: ` を (6) で除く。残る文は per-operation deadline check の現在の理由で M-2 を名指さない", "per-operation deadline check, not only before/after the whole batch … -- 読める", None),
 1146: ("move", "文頭ラベル `Monitor ruling M-3/D (rulings-wp2a-review.md, rulings-wp3a-review.md D): ` (折返しで 2 行に割れる。2 行を切り直した) を (6) で除く。残る文の `D-3 (2)` は括弧に残り、M-3/D を名指さない", "`operation_index` is this operation's own position in the request's `operations` list … -- 読める", None),
 1159: ("rejected", "版数付き括弧 `(D-4 (2)/(4), WP-2b)` から WP-2b を除く編集を検査器が拒んだ (`(2)/(4)` の `/` を含む括弧)。後から試したので番号は最初の割当の次 (CH-1035) を欠番にする (Y7-16)。文は commit vs rollback の順序 (安全) と同居し残す", "除去なし (基準のまま)", "検査器が拒んだ"),
 1172: ("keep", "ラベル `D-4 (4)/(6): ` は経緯トークン 0 の裸 ID。dry_run の rollback 経路の決定の唯一の手掛かり (18.5 の裁定点: `D-n (m): ` 形のラベルの扱い)", "除去なし (基準のまま)", "ID-only"),
 1183: ("move", "文頭ラベル `Phase 4 (design D-2/D-10): ` を (6) で除く。残る文は pre-commit hook の順序と fail-closed の理由 (安全) を述べる同居文なので文は残す。D-2/D-10 を名指さない", "the pre-commit hook is called for every real batch, not only a destructive one, … -- 読める", None),
 1195: ("rejected", "版数付き括弧 `(D-5 (1)(i)/(3), ruling I-1, WP-2c)` から WP-2c を除く編集を検査器が拒んだ (`/` を含む括弧)。commit と record の不可分性 (安全) の文は残す。CH-1021 は欠番", "除去なし (基準のまま)", "検査器が拒んだ"),
 1209: ("move", VERS.format(tok="WP-2e", ids="D-7 (3)"), "`Contract 1.7.0 (D-7 (3)): `request_id` rides in the same payload …` -- 読める", None),
 1225: ("move", VERS.format(tok="WP-2a", ids="D-2 (4)") + "。残る文の `addendum 2 S-k`・`D-2 (2)` は残る", "`Contract 1.7.0 (D-2 (4)): the registry's own entry for this entity …` -- 読める", None),
 1232: ("move", "文頭ラベル `Monitor ruling M-3/D (rulings-wp2a-review.md, D-3 (2)): ` を (6) で除く。残る文は contract text の例 (\"operations/0/values/label\") を自ら名指し、M-3・D-3 を名指さない。D-3 (2) は L1146-1152 の括弧に残る", "every `details.field` this method raises for a VALUE-position defect … -- 読める", None),
 1241: ("keep", "ラベル `Contract 1.7.0 (D-2 (3)(ii), addendum R-c): ` は版数付き文書名 (除外 2)。経緯トークン 0", "除去なし (基準のまま)", None),
 1265: ("keep", "ラベル `update / delete: ` は内容語。`R-7, corrigendum M-9` は文中。経緯トークン 0", "除去なし (基準のまま)", None),
 1277: ("keep", "L906-915 と同文: `this catch's pre-M-2` が M-2 を名指す (Y7-3 (b))。作業ノートの参照 (L1277) はこのため残る", "除去なし (基準のまま)", "名指し (Y7-3 (b))"),
 1290: ("keep", "ラベル `m-5: ` は経緯トークン 0 の裸 ID。confirmation を precondition より先に検査する決定 (安全) の唯一の手掛かり", "除去なし (基準のまま)", "ID-only"),
 1301: ("move", "文頭ラベル `Phase 4 (design D-2): ` を (6) で除く。残る文は fail-closed dispatch signal (安全) の説明で、D-2 を名指さない。r2db `postgres.py:2010` が `same signal `ApplicationCell._apply` returns` で指すのはコード", "reaching this point means `require_destructive_confirmation` above did not raise … -- 読める", None),
 1336: ("keep", "ラベル `R-5 / §0.5 Q-1 (adjudicated 案B): ` は内容語 (adjudicated 案B) を含む。経緯トークン 0", "除去なし (基準のまま)", None),
 1340: ("keep", "ラベル `Q-1 案B: ` は内容語 (案B) を含む。経緯トークン 0", "除去なし (基準のまま)", None),
 1357: ("keep", "ラベル `R-7, corrigendum M-9: ` は経緯トークン 0 の裸 ID (L898 と同形)。唯一の手掛かり", "除去なし (基準のまま)", "ID-only"),
 1364: ("keep", "ラベル `R-5: ` は経緯トークン 0 の裸 ID。upsert を insert に解決しない決定の唯一の手掛かり", "除去なし (基準のまま)", "ID-only"),
 1381: ("keep", "ラベル `Contract 1.7.0 (D-2 (3)(ii), (contract text): …` は版数付き文書名と契約の引用。経緯トークン 0", "除去なし (基準のまま)", None),
 1403: ("keep", "ラベル `R-4, corrigendum M-2: ` は経緯トークン 0 の裸 ID。PRECONDITION_FAILED / NOT_FOUND の区別の決定の唯一の手掛かり", "除去なし (基準のまま)", "ID-only"),
 1461: ("move", "文頭ラベル `Ruling U-7 (WP-6d): ` を (6) で除く (L1010 と同形)。残る文は `transact`'s identical wrapper above (L1010) と `_idempotency_lock`'s own field comment (L788) を指し、U-7 を名指さない", "thin lock wrapper -- see `transact`'s identical wrapper above … -- 読める", None),
 1488: ("move", "2 編集: (1) 第 1 文の版数付き括弧 `(contract 1.7.0, D-4, WP-2b)` から WP-2b を (4) で除く。(2) 文中の `review round F-8 (`{scratchpad}/rulings-r4.md`)` の括弧 (非実在パスだけ) を括弧ごと (4) で除く。折返しで割れた 2 行を切り直した。`review round F-8` は文中 (ラベルではない) なので残る。残る文は `DataService.schema` の現在の返り値の形を述べる", "Always returns `SchemaOutcome` -- review round F-8: a bare `int` for one request … -- 読める", None),
 1505: ("rejected", "版数付き括弧 `(D-5 (8)/(9), addendum 2 S-b, ruling I-3, WP-2c)` から WP-2c を除く編集を検査器が拒んだ (`(8)/(9)` の `/`)。L1077-1085 の同形 (`(8)` のみ) は受け付けられた。r2db `postgres.py:2273` が `ApplicationCell.apply_schema`'s identical comment で指す参照先。CH-1028 は欠番", "除去なし (基準のまま)", "検査器が拒んだ"),
 1522: ("keep", "ラベル `L-6/M-6: ` は経緯トークン 0 の裸 ID (L1093 と同形)", "除去なし (基準のまま)", "ID-only"),
 1531: ("keep", "ラベル `Ruling I-3/I-8/I-9: ` は経緯トークン 0 の裸 ID。schema 操作の replay の決定の唯一の手掛かり", "除去なし (基準のまま)", "ID-only"),
 1538: ("keep", "ラベル `M-6: ` は経緯トークン 0 の裸 ID", "除去なし (基準のまま)", "ID-only"),
 1543: ("move", "文頭ラベル `WP-2 review M-2: ` を (6) で除く。残る文は SI-08 (保護参照、安全) を含む現在の理由で M-2 を名指さない", "indexes count toward `schema_objects` too, like entities/fields already did (SI-08: …) -- 読める", None),
 1557: ("rejected", "版数付き括弧 `(D-2 (7), U-1 = (β), WP-2a)` から WP-2a を除く編集を検査器が拒んだ (`U-1 = (β)` の `=`)。CH-1030 は欠番", "除去なし (基準のまま)", "検査器が拒んだ"),
 1573: ("rejected", "版数付き括弧 `(D-4 (7)/(3), addendum 2 S-a/S-j, WP-2b)` から WP-2b を除く編集を検査器が拒んだ (`/` を含む括弧)。第 2 文の文頭ラベル `Review round F-5: ` は検査器が許す候補だが、同じ段落の直前の文のラベル `Contract 1.7.0 (…): ` が残るので F-5 の文が契約の記述の続きに読める ((ii)。見送り)。CH-1031 は欠番", "除去なし (基準のまま)", "検査器が拒んだ / (ii)"),
 1595: ("keep", "経緯トークン 0、裸 ID 0 (R-42 で書き直された現在の理由)", "除去なし (基準のまま)", None),
 1803: ("iv", "`security/CONTROL_MAPPING.md:1246` が `structured.py:1807` (この塊の中の行) を指す。(iv) により塊を基準のまま残す (`repull.py` の `unresolved` を出さない)。版数付き括弧 `(D-4 (2)/(4), WP-2b)` は `/` を含むので検査器も拒む形", "除去なし (基準のまま)", "(iv)"),
 1820: ("keep", "ラベル `D-4 (3)/(4): ` は経緯トークン 0 の裸 ID。dry-run の descriptor の決定の唯一の手掛かり (18.5 の裁定点)。`conformance-tests` の `structured.py:1821` ×2 がこの塊の行を指す (触らない対象)", "除去なし (基準のまま)", "ID-only"),
 1848: ("rejected", "版数付き括弧 `(D-5 (1)(i)/(3), ruling I-1, WP-2c)` から WP-2c を除く編集を検査器が拒んだ (`/`)。`transact`'s identical comment (L1195-1205、同じく拒まれた) を指す。CH-1032 は欠番", "除去なし (基準のまま)", "検査器が拒んだ"),
 1856: ("move", VERS.format(tok="WP-2e", ids="D-7 (3)") + "。残る文は `transact`'s identical comment (L1209-1212、同じ編集) を指す", "`Contract 1.7.0 (D-7 (3)): see `transact`'s identical comment …` -- 読める", None),
 1862: ("move", "文頭ラベル `Review round F-8: ` (経緯トークン review round F-8 の 1 語) を (6) で除く。残る文は現在の返り値の形で F-8 を名指さない。実在パス `test_constraints_declaration.py` (折返しで割れる) は本文中にあり残る", "always `SchemaOutcome`, plan or no plan -- every pre-1.7.0 direct caller … -- 読める", None),
}, MT: {
 1: ("move", "第 4 段落の括弧 `(no cross-peer sharing, requester ruling 2026-09-03)` から裁定の日付句 `requester ruling 2026-09-03` と区切りを除く (検査器が受け付けた。Y7-3 (a))。第 1 文のラベル `Q4 phase D-1/D-2 (docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md v1.3): ` は実在パス + 版数で保護。第 3 段落の括弧 `(supervisor ruling 2026-09-05, `{scratchpad}/rulings-q4-wp12-rework.md` §1)` は検査器が許す候補だが、残る文 `not specified verbatim by the ruling, which only fixes … listed in §1` と `this WP's own completion report` が寄りかかる ((i)) ので残す。作業ノートの参照 (L24) はこのため残る。L60-65・L887-920・L941-945 が `this module's own docstring/header` で指す参照先", "Peer-local, independently maintained (no cross-peer sharing) -- this module's read/validate/derive/check helpers are pinned isomorphic … -- 読める", "(i) 見送り 1 件"),
 69: ("rejected", "括弧 `(design §8 migration allocation, requester ruling 2026-09-05: MitateDB `0007`; …)` から裁定の日付句 `, requester ruling 2026-09-05` を除く編集を検査器が拒んだ (括弧の中で `: ` が続く形。FAIL (§4.1 (3)) retained text has no order-preserving match)。CH-1061 は欠番", "除去なし (基準のまま)", "検査器が拒んだ"),
 77: ("move", "`#: ` の後の文頭ラベル `Phase 10 WP-6b (design D-5 (ii)): ` (経緯トークン Phase 10・WP-6b、裸 ID D-5 (ii)) を (6) で除く。`#:` の行頭記号は保つ (0g 6)。残る文は F-15 (保護) と migration の現在の役割を述べ、D-5・WP-6b を名指さない", "#: the platform single-shot migration that widens `platform_declarations.key`'s own CHECK constraint … -- 読める", None),
 108: ("keep", "括弧 `(Agent C isomorphism convergence, rulings-q4-wp12-rework.md sec.1: the literal env var name was previously baked …)` は内容語を含み (4) で括弧ごとは消えない。`previously` の経緯と現在の理由 (定数で normalize-diff を通す) が同じ文に同居", "除去なし (基準のまま)", None),
 121: ("keep", "括弧 `(… Agent C isomorphism convergence, rulings-q4-wp12-rework.md sec.1)` は内容語を含む。経緯トークン 0", "除去なし (基準のまま)", None),
 132: ("keep", "括弧 `(ruling §1: \"peer 名を含む定数は対応表に載せない\")` は引用の内容語を含む", "除去なし (基準のまま)", None),
 361: ("keep", "第 2 文のラベル `Agent C isomorphism convergence (rulings-q4-wp12-rework.md sec.1, §12 LQ4-23): ` は内容語 4 語 (Agent / C / isomorphism / convergence)。括弧の中の `sec.1`・`LQ4-23` (ID 文法に当たらない) は内容語で括弧ごとは消えない。残る文は現在の置き場所 (design §3.10) を述べる", "除去なし (基準のまま)", "(iii)"),
 525: ("rejected", "見出し行の文末 `-- design D-2(f), monitor ruling 2026-09-05.` の裁定の日付句は括弧でもラベルでもなく、許容操作に当たらない (検査器が拒んだ。FAIL (§4.1 (3)) cannot delete a whole sentence carrying a protected reference)。CH-1063 は欠番", "除去なし (基準のまま)", "検査器が拒んだ"),
 656: ("move", "括弧 `(design D-1(c) amendment 2026-09-05)` から日付 1 語を除く (検査器が受け付けた。Y7-3 (a))。残る `(design D-1(c) amendment)` は条項と訂正を名指し、文は catalog query の範囲 (安全: cluster 全体を読まない) を述べる", "(`setdatabase = <this db's oid>`, F-11's own per-database override) -- the catalog query itself is restricted to `setdatabase IN (0, own db oid)` (design D-1(c) amendment), never every database … -- 読める", None),
 758: ("keep", "ラベルの括弧は実在パス `docs/design/PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md` (折返しで割れる) と `Contract 1.7.0` を持ち保護。括弧内の `{scratchpad}/rulings-r3-r7-flip.md` ×2 だけを除くと `F-3, F-3;`・`L-2/M-7` が出所の無い断片として残る。残る文は `T3 rework`・`the PRE-rework version` に寄りかかる ((i))。作業ノートの参照 (L760・L761) はこのため残る", "除去なし (基準のまま)", "(i) / 断片"),
 862: ("move", "文中の括弧 `(ruling `{scratchpad}/rulings-r3-r7-flip.md` L-2/M-7)` (種類語 ruling、非実在パス、裸 ID) を括弧ごと (4) で除く (§9 規則 3)。`#:` の 3 行を 2 行に切り直した (`#:` は保つ)。`WP-3e rework T3 removed …` は文中の主語で残る (`used to` の経緯と現在の理由の同居文)。残る文は L-2/M-7 を名指さない", "#: … -- never here. WP-3e rework T3 removed this module's former `_CONTRACT_170_LIMIT_ATTRIBUTES` (…) for exactly that reason: … -- 読める", None),
 887: ("move", "第 1 文の括弧 `(Phase 10 WP-4f, supervisor ruling 2026-09-09; peer-symmetric with …)` から経緯トークン 3 語 (Phase 10・WP-4f・supervisor ruling 2026-09-09) と区切り `; ` を除く (検査器が受け付けた)。ラベル `F-16 (…)` の F-16 は保護参照で残る。残る文の `the full WP-4e finding this responds to` は WP-4e (残る) を指す。第 3 段落の `(measured 2026-09-10, WP-4 integration review M-1, …)` は日付を除くと `measured,` が何時の計測か失うので残す (Y7-3 (b))。role の安全上の理由 (CONNECTION LIMIT) を含む文は残す", "# F-16 (peer-symmetric with r2db-api's own same-numbered check -- see that peer's own module for the full WP-4e finding this responds to): every PostgreSQL role … -- 読める", "一部残し (measured 2026-09-10)"),
 1068: ("move", "文頭ラベル `M-1 (WP-4 integration review 2026-09-10): ` (裸 ID M-1、経緯トークン WP-4・review・日付、内容語 integration 1) を (6) で除く。残る文は `max(...)` と `_table_owner` の現在の理由で M-1 を名指さない (L887-920 第 3 段落の `WP-4 integration review M-1` は別の塊)。integration は module 内で現行の区分名として使われない", "# a role can legitimately match MORE than one platform-plane class below … -- 読める", None),
 1201: ("keep", "ラベル `F-18 (R-91, work order docs/work-orders/WORK_ORDER_R91_MAX_CONNECTIONS_HEADROOM_CHECK_V1.md §1.2 D-1, …): ` は F-18 と実在パス (折返しで割れる) で保護。経緯トークン 0。残る文の `(§1.1 (c))` は同じ括弧の work order を出所に持つ", "除去なし (基準のまま)", None),
}}
AUTO_KEEP = ("keep", "経緯トークン 0。除去の対象になる語が無く、経緯だけの文も無い (全文を読んだ。§3 残す)。内容の除去が 0 なので CH-ID を付けない (Y7-3 (d))", "除去なし (基準のまま)", None)
JUDGE = {"move": "移す (文頭ラベル・括弧内トークン・日付の機械除去)。残りは残す", "keep": "残す (§3)", "rejected": "残す (§3。除去を試したが検査器が受け付けない (`--base` で赤を実測)。基準のまま)", "iv": "残す (§3。(iv) `security/CONTROL_MAPPING.md` が指す行)"}

# ---------------------------------------------------------------------------------------------
def spec_for(module): return json.load(open(SP / f"cs9/cs9-spec-{SHORT[module]}.json"))
def rejected_for(module): return json.load(open(SP / f"cs9/cs9-rejected-{SHORT[module]}.json"))
def removed_rows(module):
    rows = []
    for l in (SP / "cs9/checks-raw.txt").read_text().splitlines():
        if l.startswith("REMOVED\t") and module in l: rows.append(l.split("\t"))
    return rows
def esc(s): return s.replace("|", "\\|").replace("\n", " ")
def head(s, n=70): s = " ".join(s.split()); return esc(s[:n] + ("…" if len(s) > n else ""))

def render(module):
    info = M["modules"][module]; short = SHORT[module]; peer = module.split("/")[0]
    src = show(module); blocks = {b.start_line: b for b in cp.extract_all_blocks(src)}
    spec = spec_for(module); by_line = {b["line"]: b for b in spec["blocks"]}; rej = {r["line"]: r for r in rejected_for(module)}
    dec = DEC[module]
    out = [f"# 変更セット 9 判定表 — `{module}` (草案)", "",
           f"基点 `{BASE}` (このセッションの checkout の origin/main、fetch 後。作業機の local main はこれより先に進んでいる可能性がある)。行番号はすべて基点の値。HEAD の状態の行番号は書かない (作業機で取り直す)。この表は草案の記録であり受け入れの証拠ではない。数え方は作業指示書 §16.2・§16.4 と同じ (塊 = `extract_all_blocks`、文 = `split_sentences(_flatten(...))`、目印 = 設計 §3、安全 / 保護参照 / 位置 = §14.2 の正規表現)。", "",
           f"対象の塊 {info['summary']['target_blocks']} (docstring {info['summary']['target_docstring']} / comment {info['summary']['target_comment']})、spec に入れた塊 {len(spec['blocks'])} (編集 {sum(len(b['edits']) for b in spec['blocks'])})、検査器が拒んだ塊 {len(rej)} (番号は欠番のまま)、削除した文 0。", ""]
    # A
    out += ["## A. 判定表 (全塊。対象の塊 1 つにつき 1 行。spec の `blocks` の各項目が 1 行に対応し、spec に無い行は「基準のまま」)", "",
            "| # | 塊 (基点の行) | qualname | 種別 | 拾った理由 (目印 / 安全 / 保護参照 / 位置 / 参照先) | spec の CH-ID | 除いた語句 (spec の `old` → `new`) | HEAD の状態 | 判定 (§3) | 根拠 | 削除前の確認 (指示語・副詞・直後の 2 文。設計 §3) | 除去後の文を読んだ判定 | 点検語 |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    rows_b, rows_c, nonhead_labels, label_words, skipped, idonly = [], [], [], [], [], []
    for i, e in enumerate(info["target_blocks"], 1):
        L = e["start"]; blk = blocks[L]
        kind, reason, after, typ = dec.get(L, AUTO_KEEP)
        reasons = []
        if e["marker_sentences"]: reasons.append(f"目印 {len(e['marker_sentences'])} 文")
        if e["safety"]: reasons.append("安全")
        if e["protected"]: reasons.append("保護参照")
        if e["position"]: reasons.append("位置")
        if e["xref"]: reasons.append("参照先/参照元")
        picked = "、".join(reasons) or "全塊走査 (拾った理由なし)"
        flat = cp._flatten(blk.kind, blk.dedented)
        words = sorted({m.group(0).lower() for m in CHECK_WORDS.finditer(flat)})
        if kind == "move":
            b = by_line[L]; ch = b["ch"]
            removed = "; ".join(f"`{esc(x['old'])}` → `{esc(x['new']) or '(空)'}`" for x in b["edits"])
            headst = f"`# history: {ch}`" if blk.kind == "comment" else f"`History: {ch}`"
        elif kind == "rejected":
            r = rej[L]; ch = f"{r['ch_reserved_unused']} (欠番)"; removed = "(試した除去: " + "; ".join(f"`{esc(x['old'])}` → `{esc(x['new']) or '(空)'}`" for x in r["edits"]) + ") → 検査器が拒んだ"; headst = "基準のバイト列 (CH なし)"
        else:
            ch = "なし"; removed = "(除去なし)"; headst = "基準のバイト列 (CH なし)"
        out.append(f"| {i} | L{e['start']}-{e['end']} | `{e['qualname']}` | {e['kind']} | {picked} | {ch} | {removed} | {headst} | {JUDGE[kind]} | {esc(reason)} | 文の削除 0 | {esc(after)} | {('、'.join('`'+w+'`' for w in words)) or 'なし'} |")
        for ms in e["marker_sentences"]:
            rows_b.append((i, L, e["end"], ch if kind == "move" else "なし", "、".join(f"`{m}`" for m in ms["markers"]), ms["sentence"], headst, kind, words))
        if e["safety"] or e["protected"] or e["position"]:
            kinds = []
            if e["safety"]: kinds.append("安全 (" + "、".join(sorted({w for s in e["safety"] for w in s["words"]})) + ")")
            if e["protected"]: kinds.append("保護参照")
            if e["position"]: kinds.append("位置")
            rows_c.append((i, L, e["end"], ch if kind == "move" else "なし", "、".join(kinds), headst, kind, len(e["safety"]), len(e["protected"]), len(e["position"]), words))
        if typ: skipped.append((i, L, e["end"], typ, reason))
        if typ and typ.startswith("ID-only"): idonly.append((L, e["end"]))
    out += ["", f"## B. 目印一覧に当たる文 ({info['summary']['marker_sentences']} 文 / {info['summary']['marker_blocks']} 塊。完了条件 27)", "",
            "| # | 塊 (基点の行) | CH-ID | 目印 | 文 (先頭の数語) | HEAD の状態 | 判定 (§3) | 根拠 | 点検語 | A の行 |", "|---|---|---|---|---|---|---|---|---|---|"]
    for n, (ai, L, E, ch, mk, sent, hs, kind, words) in enumerate(rows_b, 1):
        basis = {"move": "ラベル・括弧・日付だけを除き、文は残す (経緯と現在の理由の同居文)", "keep": "同居文は残す (A の行の根拠)", "rejected": "検査器が除去を受け付けず、基準のまま", "iv": "(iv) 基準のまま"}[kind]
        out.append(f"| {n} | L{L}-{E} | {ch} | {mk} | `{head(sent)}` | {hs} | 残す (文は削除しない) | {basis} | {('、'.join('`'+w+'`' for w in words)) or 'なし'} | {ai} |")
    out += ["", f"## C. 経緯と同じ文にある安全上の理由・保護参照・位置 (安全 {info['summary']['safety_blocks']} 塊と、保護参照・位置だけの塊)", "",
            "| # | 塊 | CH-ID | 種別 | HEAD の状態 | 判定 (§3) | 根拠 (その塊の安全上の理由・保護参照が残ること) | 点検語 | A の行 |", "|---|---|---|---|---|---|---|---|---|"]
    for n, (ai, L, E, ch, kinds, hs, kind, ns_, np_, npos, words) in enumerate(rows_c, 1):
        out.append(f"| {n} | L{L}-{E} | {ch} | {kinds} | {hs} | 残す (文は削除しない。除去は経緯トークンの機械除去だけ) | 経緯トークンを含む文のうち 安全 {ns_} / 保護参照 {np_} / 位置 {npos} 文。文は消していない。{'除去はラベル・括弧内トークン・日付だけ' if kind == 'move' else '除去なし'} | {('、'.join('`'+w+'`' for w in words)) or 'なし'} | {ai} |")
    # removed words (condition 30)
    rows = removed_rows(module)
    out += ["", f"## 除いた語の一覧 (完了条件 30。`cs9_removed_tokens.py` の `REMOVED` 行 {len(rows)} 行と同じ順で 1 行ずつ対応。実行は checks.md)", "",
            "| # | 塊 (基点の行) | CH-ID | 種類 | 除いた語 | 回数 | 意味と出所が残る根拠 |", "|---|---|---|---|---|---|---|"]
    for n, r in enumerate(rows, 1):
        _, path, where, ch, cls, tok, cnt = r
        if tok.startswith("WP-"): why = f"WP の位置指定 `{tok}` はラベル又は括弧の中だけにあった。残る文は `this WP`・`pre-WP`・`WP-` でこの WP を指さない (A の根拠欄で点検済み)"
        elif cls == "path": why = f"作業ノートの参照 `{tok}` (基点の tree に無い非実在パス = 経緯トークン、設計 §9 規則 2)。残る文はそれを指さない"
        elif tok.startswith("review"): why = f"`{tok}` は指摘番号を含む 1 つの経緯トークン (設計 §9.2 規則 1 の除外)。実行時検査の F-ID ではない"
        else: why = f"設計名 (ファイル名・版数) の付かない裸の局所 ID `{tok}`。出所を持たず、残る文は名指しも指示語でも指さない。保護参照 (SI-・F-ID・実在パス・版数付き文書名) は変わらない (`--base` exit 0)"
        out.append(f"| {n} | {where} | {ch} | {cls} | `{tok}` | {cnt[1:]} | {why} |")
    # references
    out += ["", "## 塊をまたぐ参照先一覧 (行番号は基点。参照先の文は「残す」と固定)", "", "| # | 参照元 (`file:line`) | 参照の語 | 参照先 (`file:line`) | 参照先の文 (先頭の数語) | 残っているか (spec を当てた作業ツリー) |", "|---|---|---|---|---|---|"]
    for n, row in enumerate(XREFS[module], 1): out.append(f"| {n} | {row[0]} | {esc(row[1])} | {row[2]} | `{esc(row[3])}` | {row[4]} |")
    out += ["", "## 文頭でない位置のラベル除去の全件 (直前に残る段落・文のラベル・見出しと並べる)", "", "| # | 塊 (CH-ID、基点の行) | 除去したラベル | 除去の位置 | 直前に残る段落・文のラベル・見出し | 判定 |", "|---|---|---|---|---|---|"]
    for n, row in enumerate(NONHEAD[module], 1): out.append(f"| {n} | {row[0]} | `{esc(row[1])}` | {row[2]} | {esc(row[3])} | {esc(row[4])} |")
    out += ["", "## ラベルを除いた全編集の内容語の走査 ((iii)。ラベルの中の、経緯トークン・ID・括弧・接続語・種類語 (design / ruling / review) 以外の語)", "", "| # | 塊 (CH-ID、基点の行) | 除いたラベル | 内容語 | module 内の他の出現 (現行の区分名・規則名か) | 判定 |", "|---|---|---|---|---|---|"]
    for n, row in enumerate(LABELWORDS[module], 1): out.append(f"| {n} | {row[0]} | `{esc(row[1])}` | {row[2]} | {esc(row[3])} | {row[4]} |")
    out += ["", "## 見送った除去の一覧 (候補が在ったが基準のまま残した塊。型は依頼の (i)〜(iv) と Y7-3 (b)、検査器が拒んだもの)", "", "| # | 塊 (基点の行) | 型 | 根拠 (A の行と同じ) |", "|---|---|---|---|"]
    for n, (ai, L, E, typ, reason) in enumerate(skipped, 1): out.append(f"| {n} | L{L}-{E} (A の行 {ai}) | {typ} | {esc(reason)} |")
    out += ["", "## 作業ノートの参照の残し (`{scratchpad}/…`・`scratchpad/…`)", "", "| 行 (基点) | 置き場 | 残した理由 |", "|---|---|---|"]
    for row in SCRATCH[module]: out.append(f"| {row[0]} | {row[1]} | {esc(row[2])} |")
    out += ["", "## 指示語チェックの候補一覧 (削除した文 1 つにつき 1 行)", "", "削除した文は 0 文 (spec の `new` が空の編集はすべて文頭ラベルの除去で、文の削除ではない)。候補一覧は該当なし。", "",
            "## HTTP の status・error code を含む削除文の監査一覧", "", "削除した文が 0 文のため該当なし。", "",
            "## 0d の保護参照があるために残った、経緯だけの文", "", "| # | 塊 (行) | 文 (先頭の数語) | 保護参照 | 状態 |", "|---|---|---|---|---|"]
    for n, row in enumerate(PROTECTED_HISTORY[module], 1): out.append(f"| {n} | {row[0]} | `{esc(row[1])}` | {row[2]} | {esc(row[3])} |")
    out += ["", "## 訂正の記録 (0g)", "", TRAIL[module]]
    (OUT / f"judgement-{short}.md").write_text("\n".join(out) + "\n")
    print(f"judgement-{short}.md: A {len(info['target_blocks'])} rows, B {len(rows_b)}, C {len(rows_c)}, removed {len(rows)}, skipped {len(skipped)}")

XREFS = {R2: [
 ("`structured.py` L195-199", "`field_type`'s own precedent below", "L202-212 (CH なし)", "R-2 (corrigendum m-1): `field_type` is accepted only by `add_field`", "はい"),
 ("`structured.py` L221-223 / L231-233 / L236-240", "immediately above / `field_type`'s own `add_field`-only rule above / `field_type` above", "L202-212", "同上", "はい"),
 ("`structured.py` L226-228", "symmetric with `field_types` immediately above", "L221-223 (CH-0991)", "`field_types` (the per-field map) is accepted only by `create_entity`", "はい (ラベルだけ除いた)"),
 ("`structured.py` L338-342 / L350-351", "Mirrors `field_types`'s identical \"sent without fields\" check above / the \"requires fields\" branch above", "L293-298 / L338-342 (CH-0998)", "(c) `field_types` sent without `fields` at all / `field` names the request-internal key", "はい"),
 ("`structured.py` L433-437 / L441-442", "same isinstance-first guard as create_entity's field_types values above / same json->None translation", "L309-319 (CH-0996) / L322-325", "`isinstance` checked FIRST (coordinator F2) / Decision (v1.3 G11)", "はい"),
 ("`structured.py` L444-448", "unlike `alter_field` below", "L470-484 (CH-1002)", "`alter_field` redeclares one EXISTING field's `enum`/`nullable` as a PATCH", "はい"),
 ("`structured.py` L549-551", "same reasoning as create_entity's fields loop above", "L272-277", "Ruling N-1: identifier_syntax stops at the container position", "はい"),
 ("`structured.py` L906-915 / L1277-1286", "module docstring's own documented divergence", "L1 (module docstring、1 行)", "A small structured-operation reference engine (no database-native command path).", "**無い** (divergence の記述は module docstring に無い。移動前からの穴。`inmemory_predicate.py:106` の \"documented, accepted cross-backend divergence (see `postgres.py`'s …\" が別の所在を示す)"),
 ("`structured.py` L1010-1016 / L1461-1465", "see `_idempotency_lock`'s own field comment above", "L788-798 (CH なし)", "Ruling U-7 (`{scratchpad}/review2/frame.md` F-①, WP-6d): this in-memory backend has no database transaction", "はい (基準のまま)"),
 ("`structured.py` L1461-1465", "see `transact`'s identical wrapper above", "L1010-1016 (CH-1013)", "thin lock wrapper -- `self._idempotency_lock` is held", "はい"),
 ("`structured.py` L1488-1501", "identical single tx-exit-point discipline to `transact` above", "L1039-1069 (CH-1014)", "`dry_run`/`plan`/`plan_request` (contract 1.7.0, D-4): `dry_run` walks every gate", "はい"),
 ("`structured.py` L1848-1852 / L1856-1858", "mirroring `transact`'s identical comment / see `transact`'s identical comment", "L1195-1205 (CH-1021 欠番、基準のまま) / L1209-1212 (CH-1023)", "Contract 1.7.0 (D-5 (1)(i)/(3), ruling I-1, WP-2c): recorded in the SAME critical section / Contract 1.7.0 (D-7 (3)): `request_id` rides", "はい"),
 ("r2db `src/r2db_api/postgres.py:1765`", "see `ApplicationCell.transact`'s identical comment (parity)", "L1129-1135 (CH-1017)", "whether this batch passed through the DESTRUCTIVE_CONFIRMATION_V1 choke", "はい (ラベルだけ除いた)"),
 ("r2db `src/r2db_api/postgres.py:1783`", "see `ApplicationCell.transact`'s identical comment for the ordering rationale", "L1077-1085 (CH-1015)", "Contract 1.7.0 (D-5 (8), addendum 2 S-b, ruling I-3): the idempotency lookup sits HERE", "はい"),
 ("r2db `src/r2db_api/postgres.py:2273`", "see `ApplicationCell.apply_schema`'s identical comment", "L1505-1514 (CH-1028 欠番、基準のまま)", "Contract 1.7.0 (D-5 (8)/(9), addendum 2 S-b, ruling I-3, WP-2c): the idempotency lookup sits HERE", "はい"),
 ("r2db `src/r2db_api/postgres.py:1991` / `:2010` / `:2346`", "symmetric with the `insert` branch above and with `ApplicationCell._apply` / same signal `ApplicationCell._apply` returns / structured.py's own `_reject_reserved_entity_name`", "コード (L1265-1268 の規則、L1301-1304 CH-1024 の signal、`identifier_rules.py` へ出た関数)", "update / delete: R-7, corrigendum M-9 / reaching this point means `require_destructive_confirmation` above did not raise", "はい (コードへの参照。文は残る)"),
 ("r2db `src/r2db_api/backend.py:154`", "identical single-tx-exit-point discipline to `transact` above", "`StorageBackend` protocol の自身の docstring (ApplicationCell を指さない)", "—", "対象外 (別 module の自身への参照)"),
 ("r2db `src/r2db_api/schema_binding.py:28/29/40/72/142/148/164/192`、`value_types.py:115`", "`bind_schema_operation` below (in `structured.py`) / `validate_enum_declaration` below (in `structured.py`) / monitor ruling m-1, rulings-wp2a-review.md", "コード (`bind_schema_operation`、登録 helper `validate_enum_declaration`) と L378-383 の m-1 の裁定", "Monitor ruling m-1 (rulings-wp2a-review.md, contract corrigendum, …)", "はい (L378-383 は基準のまま)"),
 ("r2db `src/r2db_api/storage_outcomes.py:89`", "nothing below `transact`'s own idempotency lookup … ran", "コード (`_transact_locked` の lookup、L1077-1085 CH-1015 の説明)", "the idempotency lookup sits HERE", "はい"),
 ("r2db `tests/test_dry_run_and_plan.py:332`", "review round F-5's own docstring claim on `transact` above (\"A plain apply pays no `json.dumps`/`sha256` cost it never uses\")", "L1039-1069 (CH-1014) 第 2 段落", "Review round F-5 (`{scratchpad}/rulings-r4.md`): `service.py` builds `plan_request` unconditionally … A plain apply pays no `json.dumps`/`sha256` cost it never uses.", "はい (F-5 のラベルは見送り、文は逐語で残る)"),
 ("r2db `tests/test_audit_query.py:1515-1518`", "Ruling U-7 …: `apply_schema` above is now a thin `with self._idempotency_lock:` wrapper", "L1461-1465 (CH-1026) の docstring とコード", "thin lock wrapper -- see `transact`'s identical wrapper above", "はい (test 側のコメントは U-7 を自ら名指す)"),
 ("MitateDB `tests/test_denial_details_and_request_id.py:206`", "r2db-api's own `structured.py::_apply` names this same position (`values_path = f\"operations/{operation_index}/values/\"`)", "コード (`_apply` の `values_path`)。周辺の塊 L1232-1237 (CH-1022)", "every `details.field` this method raises for a VALUE-position defect … names the request-internal PATH", "はい (コードへの参照。文は残る)"),
 ("`conformance-tests/test_c20_constraint_declaration_agreement.py:154`、`test_c22_dry_run_and_plan.py:186`", "`r2db-api/src/r2db_api/structured.py:1821`", "L1820-1827 (CH なし) の行 (位置参照)", "D-4 (3)/(4): `descriptor` is the target entity's own descriptor", "はい (塊は基準のまま。行番号は移動するが `conformance-tests/` は触らない。範囲内に留まる: 1821 ≤ 1906)"),
 ("`conformance-tests/test_c05_limit_declaration_agreement.py:555` (折返し `structured.py:` + `923`)", "`postgres.py:1224`/`structured.py:923`", "L923 (コード。`test_conformance_docstring_position_refs.py::test_pin_the_one_remaining_line_wrapped_position_reference_in_the_real_corpus` が解決と範囲を固定)", "—", "はい (コード行。行番号は移動するが触らない)"),
 ("登録 helper の中から対象の塊へ: `structured.py` L114-123 (`enum_member_matches_type`)", "`validate_enum_declaration` below rejects the declaration itself first", "登録 helper 同士 (L136-163)", "—", "対象外 (helper → helper)"),
 ("登録 helper の中から対象の塊へ: `structured.py` L136-163 (`validate_enum_declaration`)", "see `FIELD_TYPES`'s own comment / see that class' own docstring", "`schema_binding.py` (module の外) / `_ConstraintDeclarationError` の docstring (`schema_binding.py`)", "—", "対象外 (module の外)"),
 ("登録 helper の中から対象の塊へ: `structured.py` L647-661 (`normalize_request_for_idempotency`)", "IDENTICAL recipe to `normalize_request_for_plan` above", "登録 helper 同士 (L589-604)", "—", "対象外 (helper → helper)"),
 ("登録 helper の中から対象の塊へ: 対象の塊を指す文", "—", "—", "—", "**0 件** (6 helper docstring の参照はすべて helper 同士か module の外を指す)"),
], MT: [
 ("`platform_declarations.py` L60-65", "this module's own docstring above explains why that is safe", "L1-47 (CH-1060) 第 3 段落", "Reference-implementation module (supervisor ruling 2026-09-05, `{scratchpad}/rulings-q4-wp12-rework.md` §1): every name, signature and return type below is shared verbatim", "はい (第 3 段落は基準のまま。除いたのは第 4 段落の裁定の日付句)"),
 ("`platform_declarations.py` L887-920 (`this module's own header already avoids that technique`)、L941-945 (`this module's own header`)", "this module's own header", "L1-47 (CH-1060) 第 1 段落 (D-2(h))", "`pg_db_role_setting` … is now the single source of both the two writer timeouts AND which roles are declared audit writers (D-2(h))", "はい"),
 ("`platform_declarations.py` L1068-1074", "see the module header above", "L887-920 (CH-1066) 第 3 段落", "Deliberately excludes `mitatedbsvc_provision` … This is an EXPLICIT exclusion (`_table_owner`, below)", "はい (除いたのは第 1 文の括弧の経緯トークンだけ)"),
 ("`platform_declarations.py` L379-384 / L1095-1098 / L1525-1528", "`surfaces.data.base_url`'s own `suffix` check / `0012_role_connection_limits.sql`'s own migration-time loop / `check_denial_window_function` compares", "コード・migration", "—", "はい (コードへの参照)"),
 ("`platform_declarations.py` L77-82 (CH-1062)", "referenced by `_f15_missing_message` only", "コード", "—", "はい"),
 ("`platform_declarations.py` L1201-1236", "F-16 above never asks / UNLIKE F-16's own narrowed startup calls", "L887-920 (CH-1066) と `check_role_connection_limits` のコード", "every PostgreSQL role this deployment's own processes pool connections against must have a `CONNECTION LIMIT`", "はい"),
 ("登録 helper の中から対象の塊へ: L964-980 (`_table_owner`)", "Used below to keep that owner … (M-1, WP-4 integration review 2026-09-10, …)", "L1068-1074 (CH-1067) のコードと、同じ M-1 の裁定", "M-1 (WP-4 integration review 2026-09-10): a role can legitimately match MORE than one platform-plane class", "はい (helper 側は M-1 と日付を自ら持つ。対象の塊のラベルを除いても helper の文は指す先 (コード) を失わない)"),
 ("登録 helper の中から対象の塊へ: L1352-1369 (`check_max_connections_headroom`)、L1314-1317 (`HeadroomReport`)、L1268-1273", "`headroom_lower_bound`, above / `_f18_message` below / unlike `check_role_connection_limits`'s own read", "コード (登録 helper 同士)", "—", "対象外 (helper → helper / コード)"),
 ("登録 helper の中から対象の塊へ: L803-823 (`check_contract_170_declarations`)", "the signature above is bare … (版フリップ監査, ruling `{scratchpad}/rulings-r3-r7-flip.md` 追補4)", "コード (自身の signature)。周辺の塊 L758-797 (基準のまま)", "Contract 1.7.0 (design docs/design/PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md D-1/D-6/D-5, …)", "はい"),
 ("登録 helper の中から対象の塊へ: L557-561 (`check_control_surface_consistency`)", "it has its own unconditional F-3c check below, monitor ruling 2026-09-05", "コード (`require_control_surface_declared`)。見出し L525-530 (基準のまま、CH-1063 欠番)", "F-6 / F-3c: `surfaces.control`'s presence must agree with the calling process' own role", "はい"),
 ("MitateDB `conformance/real_server_mitatedb.py:460`、r2db `conformance/real_server_r2db.py:528`", "left below `check_role_connection_limits`'s own floor", "数値の比較 (コメントへの参照ではない)", "—", "対象外"),
 ("MitateDB `tests/test_audit_query.py:2722`", "Unlike `check_role_connection_limits` (excluded above: …)", "同じテストファイルの同型性の表のコメント", "—", "対象外"),
 ("r2db `tests/test_application_audit.py:2848`", "the central claim `check_writer_role_timeouts`'s own docstring makes (design D-1(c))", "r2db 側の同名 docstring (と MitateDB の登録 helper L732-745)", "—", "対象外 (登録 helper の docstring。触らない)"),
 ("`security/CONTROL_MAPPING.md` (15 件) / `conformance-tests/` (0 件) / README・`docs/` (0 件)", "位置参照 `MitateDB-api/src/mitatedb_api/platform_declarations.py:N` (すべてパス付き。basename だけの形は 0)", "コードの行 (コメント・docstring の行を指すものは 0)", "—", "`repull.py --dry-run` が 15 件とも引き直す (unresolved 0)"),
]}
NONHEAD = {R2: [
 ("CH-0998 (L338-342)", "Monitor ruling N-2 (rulings-r2-closure.md, WP-2a closure): ", "第 2 文の先頭 (塊の 2 行目〜3 行目)", "第 1 文 `Mirrors `field_types`'s identical \"sent without fields\" check above.` にラベル・見出しは無い", "前に残るラベル・見出しが無い。(ii) に当たらない"),
 ("(見送り) CH-1014 (L1039-1069)", "Review round F-5 (`{scratchpad}/rulings-r4.md`): ", "第 2 段落の先頭", "第 1 段落のラベル `` `dry_run`/`plan`/`plan_request` (contract 1.7.0, D-4): `` が残る", "(ii) に当たる恐れ (F-5 の段落が D-4 の記述の続きに読める) → 除かない。18.5 の裁定点"),
 ("(見送り) L1573-1580 (CH-1031 欠番)", "Review round F-5: ", "同じ段落の第 2 文の先頭", "第 1 文のラベル `Contract 1.7.0 (D-4 (7)/(3), addendum 2 S-a/S-j, WP-2b): ` が残る (WP-2b の除去も検査器が拒んだ)", "(ii) に当たる恐れ → 除かない"),
], MT: [("—", "—", "—", "文頭でない位置のラベル除去は 0 件 (CH-1062・CH-1067 のラベルは塊の先頭。CH-1060・CH-1064・CH-1065・CH-1066 の編集は括弧・日付で、ラベルは基準のまま)", "該当なし")]}
LABELWORDS = {R2: [
 ("CH-0990 (L195)", "WP-2 review minor (e): ", "minor", "L891 の同形ラベル (CH-1011) だけ。現行の区分名・規則名ではない (review の指摘の重さ)", "除いてよい"),
 ("CH-0991 (L221)", "Phase 6 WP-2 (design D-3(iv)): ", "(design は種類語) なし", "—", "除いてよい"),
 ("CH-0994 (L236)", "WP-2 review M-3: ", "なし", "—", "除いてよい"),
 ("CH-0995 (L246)", "Review blocker B-1: ", "(Review・blocker は §4.1 (5) の語) なし", "—", "除いてよい"),
 ("CH-0998 (L338)", "Monitor ruling N-2 (rulings-r2-closure.md, WP-2a closure): ", "closure", "L359・L488・L729 の経緯ラベルの中だけ。現行の区分名・規則名ではない (WP の閉じ)", "除いてよい"),
 ("CH-0999 (L350)", "Monitor ruling N-2 (rulings-r2-closure.md): ", "なし", "—", "除いてよい"),
 ("CH-1003 (L514)", "Monitor ruling A: ", "A (裁定の名。ID 文法に当たらない)", "L458・L470 の `monitor ruling A/B-2` (ラベルの中。基準のまま)", "除いてよい (裁定の名は L458・L470 に残る)"),
 ("CH-1011 (L891)", "WP-2 review minor (c): ", "minor", "L195 と同じ", "除いてよい"),
 ("CH-1013 (L1010)、CH-1026 (L1461)", "Ruling U-7 (WP-6d): ", "Ruling (種類語。検査器は内容語 1 と数える)", "—", "除いてよい"),
 ("CH-1017 (L1129)、CH-1024 (L1301)", "Phase 4 (design D-2): ", "なし", "—", "除いてよい"),
 ("CH-1018 (L1139)、CH-1027 (L1543)", "WP-2 review M-2: ", "なし", "—", "除いてよい"),
 ("CH-1019 (L1146)", "Monitor ruling M-3/D (rulings-wp2a-review.md, rulings-wp3a-review.md D): ", "D (裁定の名)", "—", "除いてよい"),
 ("CH-1020 (L1183)", "Phase 4 (design D-2/D-10): ", "なし", "—", "除いてよい"),
 ("CH-1022 (L1232)", "Monitor ruling M-3/D (rulings-wp2a-review.md, D-3 (2)): ", "なし (D-3 (2) は裸 ID)", "D-3 (2) は L1146-1152 の括弧と L378・L488 の本文に残る", "除いてよい"),
 ("CH-1034 (L1862)", "Review round F-8: ", "なし", "—", "除いてよい"),
], MT: [
 ("CH-1062 (L77)", "Phase 10 WP-6b (design D-5 (ii)): ", "なし", "—", "除いてよい"),
 ("CH-1067 (L1068)", "M-1 (WP-4 integration review 2026-09-10): ", "integration", "L918 (経緯ラベル) と登録 helper L971 の docstring の中だけ。現行の区分名・規則名ではない", "除いてよい"),
]}
SCRATCH = {R2: [
 ("L359", "対象の塊 (L359-375、CH-1000 欠番)", "ラベルを検査器が拒んだ (日本語を含むラベルの文字数 53 > 24)"),
 ("L728", "対象の塊 (L728-742、CH-1006 欠番)", "ラベルを検査器が拒んだ (内容語 6)"),
 ("L788", "対象の塊 (L788-798、基準のまま)", "残る文が U-7 を名指す (Y7-3 (b))"),
 ("L906・L1277", "対象の塊 (L906-915・L1277-1286、基準のまま)", "残る文が `pre-M-2` で M-2 を名指す (Y7-3 (b))"),
 ("L1048", "対象の塊 (L1039-1069、CH-1014) の第 1 段落の括弧の中", "内容を持つ括弧の中で、パスだけ除くと `addendum 2` の指す先が無くなる"),
 ("L1063", "対象の塊 (L1039-1069、CH-1014) の第 2 段落のラベル", "(ii) 見送り (18.5 の裁定点)"),
 ("L1492 (除いた)", "対象の塊 (L1488-1501、CH-1025)", "括弧ごと除いた (REMOVED path 行)"),
 ("L610-631", "登録 helper `compute_plan_token` の docstring", "対象外 (Y7-5 と同じ)"),
], MT: [
 ("L24", "対象の塊 (L1-47、CH-1060) の第 3 段落", "残る文が `the ruling`・`listed in §1`・`this WP's own completion report` で寄りかかる ((i))"),
 ("L760・L761", "対象の塊 (L758-797、基準のまま)", "実在パス + 版数付きの括弧の中。除くと `F-3, F-3;`・`L-2/M-7` が断片として残り、残る文が `T3 rework` に寄りかかる ((i))"),
 ("L871 (除いた)", "対象の塊 (L862-883、CH-1065)", "括弧ごと除いた (REMOVED path 行)"),
 ("L266-271、L441-460、L803-823", "登録 helper (`_f3c_message`・`validate_process_ceilings_value`・`check_contract_170_declarations`) の docstring", "対象外 (Y7-5 と同じ)"),
]}
PROTECTED_HISTORY = {R2: [
 ("L81-110 (第 3 段落)", "CCR-13 WP-5b: this shared boundary structurally *accepts* the full vocabulary … `DataService` (service.py) carried a provisional gate through WP-2〜WP-5 … that gate is removed in the same commit that updates the declaration (design R2DB_CCR13_STORAGE_V1.md §3)", "CCR-13、実在パス `R2DB_CCR13_STORAGE_V1.md`", "基準のまま。経緯 (WP-2〜WP-5 の暫定 gate) と現在の事実 (`DataService` は境界と cell の決定だけを晒す) が同じ文に同居。`WP-2〜WP-5` は文中で許容操作に当たらない"),
 ("L202-212 (第 1 段落)", "R-2 (corrigendum m-1): `field_type` is accepted only by `add_field`; every other operation rejects it exactly as before this contract version did …", "(保護参照は無いが) 現在の規則と同居", "基準のまま。ラベルは経緯トークン 0 の唯一の手掛かり"),
 ("L728-742 (第 1 文)", "Ruling L-6/M-6 (`{scratchpad}/rulings-r3-r7-flip.md` addendum 2, WP-2e closure audit R-1): a record written before the 1.7.0 flip carries no `request_id` …", "契約 `versioning.version_binding` の条件 (出所付き)", "基準のまま (CH-1006 欠番)。ラベルの除去を検査器が拒んだ (内容語 6)"),
], MT: [
 ("L1-47 (第 3 段落)", "Reference-implementation module (supervisor ruling 2026-09-05, `{scratchpad}/rulings-q4-wp12-rework.md` §1): every name, signature and return type below is shared verbatim with r2db-api's own same-named realization …", "(ラベルの内容語 Reference-implementation module) と残る文の寄りかかり", "基準のまま ((i))。CH-1060 は第 4 段落の日付句だけ除いた"),
 ("L758-797 (第 1 文)", "Contract 1.7.0 (design docs/design/PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md D-1/D-6/D-5, work order §2 WP-3e F-3, `{scratchpad}/rulings-r3-r7-flip.md` F-3; WP-3e rework T3, …): pinned isomorphic to r2db-api's own `check_contract_170_declarations` …", "実在パス (折返しで割れる)、版数付き文書名", "基準のまま。経緯 (T3 rework の前後) と現在の構造 (`capabilities_document` を caller から受ける) が同居"),
 ("L887-920 (第 3 段落末)", "… (measured 2026-09-10, WP-4 integration review M-1, peer-symmetric with r2db-api's own `r2dbsvc_control`).", "(保護参照は無い) 計測の事実", "基準のまま。日付を除くと `measured,` が何時の計測か失う (Y7-3 (b))"),
]}
TRAIL = {R2: "`docs/code-history/r2db-api/structured.md` の `### correction:` は基点で 4 件 (CH-0552 に 3、CH-0564 に 1。台帳 R-42 の既存の記録)。本草案は訂正の記録を足さない (今のコードと食い違う文は見つけていない)。完了条件 19 の変異は既存の記録 (CH-0552) の `old` を変えると `FAIL (§9.3 (2))` になる (checks.md)。手本の wrapper の接頭辞 `FAIL (§9f)` は作業ツリーにだけ在る pending の記録の形式の赤であり、基点の記録を変える変異には当たらない (報告の「手本のとおりにできなかった点」)。",
         MT: "`docs/code-history/MitateDB-api/platform_declarations.md` の `### correction:` は基点で 1 件 (CH-0550、2026-10-01 の既存の記録)。本草案は訂正の記録を足さない。"}

for module in (R2, MT): render(module)

# ---------------------------------------------------------------------------------------------
# measure.md
# ---------------------------------------------------------------------------------------------
r, m = M["modules"][R2], M["modules"][MT]
def tenplus(info): return "、".join(f"L{a}-{b}" for a, b in info["summary"]["ten_plus_blocks"])
def marker_blocks(info): return "、".join(f"L{e['start']}-{e['end']}" for e in info["target_blocks"] if e["marker_sentences"])
def safety_blocks(info): return "、".join(f"L{e['start']}-{e['end']} ({'、'.join(sorted({w for s in e['safety'] for w in s['words']}))})" for e in info["target_blocks"] if e["safety"])
def helper_table(info):
    rows = []
    for h in info["helper_nodes"]:
        rows.append(f"| `{h['symbol']}` | {h['node']} | L{h['lines'][0]}-{h['lines'][1]} | {len(h['blocks_inside'])} {('(' + '、'.join(f'L{a}-{b} {k}' for a, b, k in h['blocks_inside']) + ')') if h['blocks_inside'] else ''} |")
    return "\n".join(rows)
posrefs = (SP / "cs9/posrefs.txt").read_text()
xref_ext = (SP / "cs9/xref-external.txt").read_text()
measure = f"""# 変更セット 9 実測 (A) — r2db `structured.py`、MitateDB `platform_declarations.py`

- 基点: `{BASE}` (このセッションの checkout で `git fetch origin main` の後の `origin/main`。着手時の stale な `origin/main` は `4241b55` だったが fetch で `{BASE}` に進み、HEAD と同一。作業機の local main はこれより先に進んでいる可能性がある)。
- 数え方: 作業指示書 §16.2 (= §13.2・§14.2) と同じ。塊 = `tools/check_comment_provenance.py` の `extract_all_blocks`、経緯トークン = `_HISTORY_TOKEN_PATTERNS` の `findall` の合計 (§2.3 末尾)、文 = `split_sentences(_flatten(kind, dedented))`、目印 = 設計 §3 の叙述の目印 (英語は語境界付き・大文字小文字を区別しない、日本語は語境界なし)、安全の語 / 保護参照 / 位置の語 = §14.2 の正規表現と母集団 (経緯トークンを含む文)、塊をまたぐ参照の語 = §13.2 の正規表現に `'s identical comment`・`<名前> below|above`・`own (comment|docstring|paragraph)`・`identical-purpose comment` を足した。10 行以上の塊 = 行数 ≥ 10 で CH-ID の無い塊 (設計 §10.3 の数え方)。
- 登録 helper の表は **ast で読んだ** (両 peer の `tests/test_audit_query.py` の `_ISOMORPHIC_TARGETS`、`ast.AnnAssign` の値を `ast.literal_eval`)。対象外にするのは symbol の node (def / class / 代入文) の中に開始行を持つ塊だけ。代入だけの symbol も数に入れ、「中に塊を持つ node」と分けて書いた。
- 計測 script: `cloud-out/cs9/tools/cs9_measure.py` (→ `measure.json`)、`cs9_xref_grep.py` (外部からの参照)、`cs9_posrefs.py` (位置参照)。すべて基点の blob (`git show`) に当てた。

## 1. 塊

| 項目 | r2db `structured.py` | MitateDB `platform_declarations.py` | 計 |
|---|---|---|---|
| 行数 | {r['lines']} | {m['lines']} | {r['lines'] + m['lines']} |
| 塊 (`extract_all_blocks`) | {r['blocks_total']} (docstring {r['blocks_docstring']} / comment {r['blocks_comment']}) | {m['blocks_total']} (docstring {m['blocks_docstring']} / comment {m['blocks_comment']}) | {r['blocks_total'] + m['blocks_total']} (`--base` の `189 blocks checked` と一致) |
| 対象外: 既存の CH-ID の塊 | {len(r['existing_ch'])} ({'、'.join(f"{e['history_id']} L{e['start']}-{e['end']}" for e in r['existing_ch'])}) | {len(m['existing_ch'])} ({'、'.join(f"{e['history_id']} L{e['start']}-{e['end']}" for e in m['existing_ch'])}) | {len(r['existing_ch']) + len(m['existing_ch'])} |
| 登録 helper の symbol (`_ISOMORPHIC_TARGETS` のこの module の行) | {len(r['helpers'])} (両 peer の表で同数) | {len(m['helpers'])} (両 peer の表で同数) | — |
| うち中に塊を持つ node / 対象外の塊 | {sum(bool(h['blocks_inside']) for h in r['helper_nodes'])} node / {len(r['helper_blocks'])} 塊 (すべて docstring) | {sum(bool(h['blocks_inside']) for h in m['helper_nodes'])} node / {len(m['helper_blocks'])} 塊 (docstring 34、comment 1 = L503-509 `read_platform_declarations` の中) | {len(r['helper_blocks']) + len(m['helper_blocks'])} |
| **対象の塊** | **{r['summary']['target_blocks']}** (docstring {r['summary']['target_docstring']} / comment {r['summary']['target_comment']}、{r['summary']['target_lines']} 行) | **{m['summary']['target_blocks']}** (docstring {m['summary']['target_docstring']} / comment {m['summary']['target_comment']}、{m['summary']['target_lines']} 行) | **{r['summary']['target_blocks'] + m['summary']['target_blocks']}** |
| 経緯トークン (module 全文) / うち対象の塊の中 | {r['history_tokens_file']} / {r['history_tokens_in_targets']} | {m['history_tokens_file']} / {m['history_tokens_in_targets']} | {r['history_tokens_file'] + m['history_tokens_file']} / {r['history_tokens_in_targets'] + m['history_tokens_in_targets']} |
| 経緯トークンを含む対象の塊 (行数) | {r['summary']['blocks_with_tokens']} ({r['summary']['lines_in_blocks_with_tokens']} 行) | {m['summary']['blocks_with_tokens']} ({m['summary']['lines_in_blocks_with_tokens']} 行) | {r['summary']['blocks_with_tokens'] + m['summary']['blocks_with_tokens']} |
| 日付を含む行 (module 全文 / 対象の塊) | {len(r['date_lines_file'])} / {len(r['summary']['date_lines_in_targets'])} (L{'、L'.join(map(str, r['summary']['date_lines_in_targets']))}) | {len(m['date_lines_file'])} / {len(m['summary']['date_lines_in_targets'])} (L{'、L'.join(map(str, m['summary']['date_lines_in_targets']))}。登録 helper の中に L241・L266・L559・L570・L680・L971・L1043、既存 CH-0550 に L1043) | — |
| `#:` の行 | 0 | {len(m['colon_hash_lines'])} (対象の塊: L60-65、L69-73、L77-82、L86-88、L91-94、L97-98、L101-104、L108-114、L121-125、L128-129、L132-136、L856-859、L862-883、L922-928、L931-938、L941-945、L998-1001、L1525-1528) | — |
| 目印一覧に当たる文 / 塊 (対象の塊だけ) | {r['summary']['marker_sentences']} / {r['summary']['marker_blocks']} | {m['summary']['marker_sentences']} / {m['summary']['marker_blocks']} | {r['summary']['marker_sentences'] + m['summary']['marker_sentences']} / {r['summary']['marker_blocks'] + m['summary']['marker_blocks']} |
| 塊をまたぐ参照の語を含む文 (対象の塊) | {r['summary']['xref_sentences']} | {m['summary']['xref_sentences']} | — |
| 経緯トークンを含む文のうち 安全 / 保護参照 / 位置 | {r['summary']['safety_sentences']} / {r['summary']['protected_sentences']} / {r['summary']['position_sentences']} 文 (安全の塊 {r['summary']['safety_blocks']}) | {m['summary']['safety_sentences']} / {m['summary']['protected_sentences']} / {m['summary']['position_sentences']} 文 (安全の塊 {m['summary']['safety_blocks']}) | — |
| 10 行以上の塊 (CH なし、対象の塊) | {len(r['summary']['ten_plus_blocks'])} 塊 / {r['summary']['ten_plus_lines']} 行 (登録 helper を含む全塊で {r['summary']['ten_plus_all_blocks']}) | {len(m['summary']['ten_plus_blocks'])} 塊 / {m['summary']['ten_plus_lines']} 行 (登録 helper を含む全塊で {m['summary']['ten_plus_all_blocks']}) | — |
| 作業ノートの参照 (`{{scratchpad}}/…`・`scratchpad/…`) の行: 対象の塊の中 / 登録 helper の中 | L{'、L'.join(map(str, r['summary']['scratchpad_target_lines']))} / L610-631 (`compute_plan_token`) | L{'、L'.join(map(str, m['summary']['scratchpad_target_lines']))} / L266-271 (`_f3c_message`)、L441-460 (`validate_process_ceilings_value`、`scratchpad/phase10/wp6-rulings.md`)、L803-823 (`check_contract_170_declarations`) | — |

- `--register` (基点、無変更): `comment provenance register OK: 95 files scanned, 515 CH-IDs`。`--base {BASE}` (無変更、2 module): `comment provenance OK: 189 blocks checked` (exit 0)。`check_doc_refs.py`: `check_doc_refs OK: 0 dangling references`。
- 受け皿は既存の `docs/code-history/r2db-api/structured.md` (基点で 13 節 + 訂正 4 件) と `docs/code-history/MitateDB-api/platform_declarations.md` (1 節 + 訂正 1 件) に追記する。
- CH-ID の範囲 `CH-0990`〜`CH-1059` / `CH-1060`〜`CH-1129` は `src/`・`docs/code-history/` に 0 件 (最大は CH-0775)。作業指示書の本文に変異の番号として `CH-0997`・`CH-0999` が書かれているが、受け皿・`src/` には無い (註: 手本の変異 c6b の孤児の節 `CH-0997` は r2db の範囲の中なので、変更セット 9 では範囲外の番号 (例 `CH-1997`) を使う)。

**登録 helper (ast で読んだ)**

r2db `structured.py` (`_ISOMORPHIC_TARGETS` の r2db 側パスが `src/r2db_api/structured.py` の行。相手は MitateDB `field_types.py` 2 と `cell.py` 4):

| symbol | node | 行 | 中の塊 |
|---|---|---|---|
{helper_table(r)}

MitateDB `platform_declarations.py` (両 peer の `platform_declarations.py` が相手の行、{len(m['helpers'])} symbol。代入だけの symbol 5 (`VISIBILITY_LAG_CLOCK_SKEW_MARGIN_MS`、`_API_ROLE_STORE_COUNT`、`_CONTROLPLANE_ROLE_POOL_FLOOR`、`_AUDITREADER_ROLE_POOL_FLOOR`、`_ROLE_CLASSES`) は中に塊を持たない。各代入の直前の `#:` 塊は node の外なので対象):

| symbol | node | 行 | 中の塊 |
|---|---|---|---|
{helper_table(m)}

**10 行以上の塊 (対象の塊、CH なし)**

- `structured.py`: {tenplus(r)}
- `platform_declarations.py`: {tenplus(m)}

**目印一覧に当たる文を持つ塊** (文ごとの目印は判定表 B)

- `structured.py` ({r['summary']['marker_sentences']} 文 / {r['summary']['marker_blocks']} 塊): {marker_blocks(r)}
- `platform_declarations.py` ({m['summary']['marker_sentences']} 文 / {m['summary']['marker_blocks']} 塊): {marker_blocks(m)}

**経緯トークンと安全上の語が同じ文にある塊** (文は消さない。判定表 C に展開)

- `structured.py` ({r['summary']['safety_blocks']} 塊): {safety_blocks(r)}
- `platform_declarations.py` ({m['summary']['safety_blocks']} 塊): {safety_blocks(m)}

## 2. 塊をまたぐ参照先

判定表の「塊をまたぐ参照先一覧」に全件を置いた (module の中、両 peer の `src/`・`tests/`・`conformance/`、`conformance-tests/`、`security/`)。要点:

- `structured.py` の中: `field_type`'s own precedent / rule above (L195→L202、L221・L231・L236→L202)、`_idempotency_lock`'s own field comment (L1010・L1461→L788)、`transact`'s identical wrapper / comment (L1461→L1010、L1848→L1195、L1856→L1209)、`transact` above (L1488→L1039)、module docstring's own documented divergence (L906・L1277→L1: **無い**。module docstring は 1 行で divergence の記述を持たない。移動前からの穴)。
- 外から: r2db `postgres.py:1765` (→ L1129-1135)、`:1783` (→ L1077-1085)、`:2273` (→ L1505-1514)、`tests/test_dry_run_and_plan.py:332` (→ L1039-1069 第 2 段落の \"A plain apply pays no …\")、`tests/test_audit_query.py:1515-1518` (→ L1461-1465)、MitateDB `tests/test_denial_details_and_request_id.py:206` (→ `_apply` のコード)、`conformance-tests/test_c20…:154`・`test_c22…:186` (位置参照 `structured.py:1821` → L1820-1827 のコメント行)。
- `platform_declarations.py` の中: this module's own docstring / header (L60-65・L887-920・L941-945→L1-47)、see the module header above (L1068-1074→L887-920)、F-16 above (L1201-1236→L887-920)。
- 登録 helper の中から対象の塊を指す文: `structured.py` 0 件 (6 helper の参照は helper 同士か module の外)。`platform_declarations.py`: `_table_owner` (L964-980) が M-1 の裁定 (L1068-1074 のラベルが名指す) を自ら持つ、`check_contract_170_declarations` (L803-823) が L758-797 の周辺を指す、`check_control_surface_consistency` (L557-561) が L525-530 の見出し (F-3c) を指す。helper 側の文は対象の塊の除去で指す先を失わない。
- `cs9_xref_grep.py` の生の出力 (両 module、フィルタ前): `cloud-out/cs9/tools/xref-external.txt`。

## 3. 位置参照 (`ファイル名:行`。続きの形 `` `:N` `` を含む)

`cs9_posrefs.py` の出力 (基点。全件、パス付き / basename だけ / 続きの形、指す行がコメント・docstring の行か):

```text
{posrefs.strip()}
```

- `security/CONTROL_MAPPING.md` → `structured.py`: 12 件 (パス付き 11 + 続きの形 `` `:1599` `` 1、行 371・372・686・1244〜1248・1604)。**指す行がコメント・docstring の行であるもの**: 1 件 — `:1246` の `structured.py:1807` (L1803-1812 の comment 塊。(iv) によりこの塊は基準のまま)。ほかは code の行。`repull.py --dry-run` は 10 件を引き直し (`unresolved 0`、checks.md)。
- `security/CONTROL_MAPPING.md` → MitateDB `platform_declarations.py`: 15 件 (パス付き 13 + 続きの形 `` `:1348` ``・`` `:1325` `` 2、行 902・903・1074・1079・1090〜1092・1095・1096・1101・1103・2004・2016)。コメント・docstring の行を指すものは 0。r2db の同名ファイルへの参照 22 件 (行 700・701・766・773・781〜790・1872・1874・1960〜1964) はすべてパス付きで、`repull.py` は 1 件も書き換えない (checks.md の guard 0)。basename だけの形は 0。
- `conformance-tests/` → `structured.py`: `test_c20_constraint_declaration_agreement.py:154`、`test_c22_dry_run_and_plan.py:186` (パス付き `:1821`、comment L1820-1827 の行、行数の範囲内) と、`test_c05_limit_declaration_agreement.py:555` の折返し `structured.py:` + `923` (`test_conformance_docstring_position_refs.py::test_pin_the_one_remaining_line_wrapped_position_reference_in_the_real_corpus` が解決と範囲を固定)。触らない。→ `platform_declarations.py`: 0。
- README (root・両 peer)、両 peer の `docs/`: 0。r2db `tests/`: 4 (basename だけ: `test_foundation.py:617` `:229`、`:886` `:212`、`:1280` `:702`、`test_l1_details_vocabulary_ast_scan.py:738` `:1508`)。MitateDB `tests/`: 1 (basename だけ、`test_l1_details_vocabulary_ast_scan.py:809` `structured.py:1508`)。r2db `conformance/`: 3 行 (basename だけ: `conformance_adapter_r2db.py:319`・`:1031` の `structured.py:2269` + 続き `:2294`・`:2697`・`:2718` (行数 1867 を超え、移動前から古い)、`:1286` の `:1183`)。すべて触らない。
- `docs/` (設計・作業指示書・archive の記録): 187 出現、`security/CONTROL_MAPPING_HISTORY.md`: 0。触らない。

## 4. 行番号 pin と、module を文字列として読む検査

- 行番号 pin: r2db `tests/test_l1_details_vocabulary_ast_scan.py` の `_BACKEND_LAYER_ALLOWLIST` (L140-299) は実体 1 行 `("postgres.py", 1948)` で、`test_backend_layer_allowlist_is_confined_to_postgres_py` (L702) が全要素の module を `postgres.py` に固定する。`structured.py` の `(module, lineno)` pin は **0 件**。`SCANNED_MODULES` (L107) に `structured.py` は在るが名前だけ。件数 pin `"structured.py": 48` (L574、`test_ast_full_count_matches_the_audit_site_count`) は `_fail_call_sites` (ast) の数でコメントに依らない。MitateDB `tests/test_l1_details_vocabulary_ast_scan.py` の `_BACKEND_LAYER_ALLOWLIST` (L306-376) は 17 行すべて `backend_postgres.py`、`_CONTROL_PLANE_NO_VOCABULARY_ALLOWLIST` は空。`platform_declarations.py` の pin は **0 件**。→ 完了条件 9 は両 module とも非該当 (監査照合)。pins.md 参照。
- module を文字列として読む検査 (設計 §5 (b) の grep `read_text|\\.count\\(|getsource|__doc__` を両 peer の `tests/`・`conformance/`、`conformance-tests/`、`tools/tests/` に掛け、module 名・symbol 名の近傍を見た): 2 module を対象にするものは **0 件**。除いたもの (名指し): `MitateDB-api/tests/test_ops_startup_checks.py` の `_load_module` (L304。`<ref>:platform_declarations.py` を `compile` + `exec` する。`_f16_agrees_on_row` L568、`_f18_agrees_on_row` L616 が呼ぶ。compile はコメントに鈍感)、`r2db-api/tests/test_process_ceilings_declaration.py:839` (`inspect.getsource` を **r2db の** `platform_declarations.py` の 2 関数に `not in` で掛ける、`test_declaration_table_is_the_only_source_no_env_fallback`。本変更セットの module ではない)、`MitateDB-api/tests/test_r113_multi_process_wiring.py:435` (`getsource(ApplicationCell._limit_gate)`、cell.py)、`tools/tests/test_sql_statement_safety_scan.py` (module 名の一覧は走査対象の集合の pin で、本文を読まない)、`tools/tests/test_leaf_import_direction.py` (名前と説明だけ)。→ 完了条件 10 は非該当。

## 5. WP の分け方の案 (対象の塊の合計 134 > 130)

| 案 | 境界 | 塊の数 | 評価 |
|---|---|---|---|
| (a) module で分ける: WP-9a = r2db `structured.py`、WP-9b = MitateDB `platform_declarations.py` | ファイル境界 | 103 / 31 | spec・受け皿・`repull.py` の対象が 1 ファイルずつで衝突しない。WP-9b は小さく、`#:` 塊と `security/CONTROL_MAPPING.md` の版上げを 2 回に分ける手間だけが残る。手本 (CS7、ファイル内で 102 / 103) と同じ順の手順 |
| (b) 1 WP (CS5・CS6 の前例 113〜123 塊) | — | 134 | 編集した塊は 42 (36 + 6) で CS7 の WP 1 つ (36〜42) と同じ規模。レビューの戻しが 2 ファイルに及ぶ |
| (c) `structured.py` を `ApplicationCell` の `def` 行 (L746) で割る + MitateDB | L1-745 / L746-1867 / MitateDB | 58 / 45 / 31 | 3 WP。版上げ 3 回。塊 134 で 3 WP は過分 |

裁定は 18.5 に置く (決めない)。
"""
(OUT / "measure.md").write_text(measure)
print("measure.md written")
