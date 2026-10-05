# 変更セット 9 — (D) DB を使わない照合の記録 (checks.md)

- 基点 `092e1a1`。作業ツリーに spec を当てて確かめ、当てた結果は commit せず、module・受け皿・`security/CONTROL_MAPPING.md` を基点の内容に戻した (cp で復元、`sleep 3` の後 sha256 を 2 回照合。各実行の末尾)。
- **これは草案の記録であり、受け入れの証拠ではない** (作業機が全部取り直す)。PostgreSQL を使うテスト、`tools/dev/gate.py`・`mutate.py`・`finalize.py`、両 peer の suite・`conformance-tests/`、`pytest` は実行していない。変異は `tools/dev/mutate.py` ではなく、道具 `cs9_dbless_checks*.py` が文字列を置き換えて CLI を直接呼び、元に戻した。
- 道具の出力行は逐語。作業用ディレクトリは `$SP`、worktree の根は `$WT` と伏せた (公開リポジトリ規律)。c23 で足した 3 桁の R 番号は本書に書かない (`check_doc_refs` が本書も走査する)。
- 道具: `cloud-out/cs9/tools/` の `cs9_apply.py`・`repull.py`・`cs9_cli_red.py`・`cs9_removed_tokens.py` (作業指示書 §16.3 の本文から基点・module・CH-ID の範囲だけ置き換えた。置き換え表は wo-section18.md)、`cs9_build_spec.py` (spec の生成)、`cs9_dbless_checks.py`〜`cs9_dbless_checks4.py` (本書の実行)。

## 要約 (最終の spec)

| 照合 | 出力行 (逐語) |
|---|---|
| `cs9_apply.py` (r2db) | `blocks=36 module_lines 1867 -> 1906` |
| `cs9_apply.py` (MitateDB) | `blocks=6 module_lines 1713 -> 1720` |
| `check_comment_provenance.py --base 092e1a1 <2 module>` | `comment provenance OK: 189 blocks checked` (exit 0) |
| `check_comment_provenance.py --register` | `comment provenance register OK: 95 files scanned, 557 CH-IDs` (exit 0。基点 515 + 42) |
| `check_doc_refs.py` | `check_doc_refs OK: 0 dangling references` (exit 0) |
| `cs9_removed_tokens.py -C $WT` | `SUMMARY ch_blocks=42 ws_only=0 unpaired=0 removed_rows=50` (exit 0。`REMOVED` 行 50 は下の実行 1 に逐語) |
| `repull.py --dry-run 092e1a1 security/CONTROL_MAPPING.md -- <2 module>` | `security/CONTROL_MAPPING.md: changed 23, unresolved 0, not applied 0` (exit 0。`structured.py` 10 件、`platform_declarations.py` 13 件。r2db の同名ファイルへの参照を書き換えた行 0) |
| AST (`ast_signature`、docstring を除く) | 両 module とも identical |
| 対象外の塊 (登録 helper の中、既存の CH-ID) | spec に無い基点の塊で新しい module に逐語で無いもの: `[]` (両 module) |
| 経緯トークン (module 全文) 前 → 後 | `structured.py` 112 → 65、`platform_declarations.py` 42 → 31 |
| 日付を含む行 前 → 後 | `structured.py` 3 → 2 (残るのは L584・L641 の `依頼者裁定 2026-09-03`、検査器が日付だけの除去を拒む)、`platform_declarations.py` 15 → 11 (対象の塊で残るのは L23 (i)、L72 (検査器が拒んだ)、L529 (同)、L888 の `measured 2026-09-10`、L917 相当; 登録 helper の中 6 と既存 CH-0550 の 1 は対象外) |
| `#:` の行 前 → 後 | `platform_declarations.py` 103 → 102 (CH-1065 の 3 行を 2 行に切り直した。行頭記号は保つ。`#:` の塊に `# history:` 行を足すのは `cs9_apply.py` の形) |
| 作業ノートの参照の行 前 → 後 | `structured.py` 9 → 8、`platform_declarations.py` 7 → 6 |
| 変えた docstring の `\` | 0 (両 module) |
| 22(b) の実測 | spec で CH-ID の付く塊の**ラベル**に折り返しで割れた実在パス: 0 (両 module)。本文中には CH-1034 (L1862-1866) の `` `test_constraints_declaration.py` `` が折り返しで割れて在る (ラベルではない) → 完了条件 22(b) は非該当 |
| 行番号 pin | grep 0 件 (exit 1) |

## 変異の CLI 確認 (指定の赤になること。空振りと別の理由の赤が無いことを見た)

| 完了条件 | 変異 (塊、当てた文字列) | 期待 | 結果 (逐語の FAIL 行は下の実行) |
|---|---|---|---|
| 17 | CH-0995 (L246-253): ラベル除去後の先頭 `symmetric` → `Symmetric` | `FAIL (§4.1 (3))` | 赤。FAIL 行 1 本、別の FAIL 0 (実行 1) |
| 21 (a) | CH-0995: `shape check` → `shapecheck` (空白が要る語の境界を空白なしでつなぐ) | `FAIL (§4.1 (3))` | 赤。FAIL 行 1 本、別の FAIL 0 (実行 1) |
| 21 (b) | CH-1014 (L1039-1069): `` `transaction`/ `` の直後の改行を空白 1 つでつなぐ | `FAIL (§9e)` | 赤。`'(`entity`/`operations`/`transaction`/ `budget`,' should be ... (zero space)` (実行 1) |
| 21 (c) | CH-1002 (L470-484): `` `alter_ `` + 改行 + `` field` `` を空白 1 つでつなぐ | `FAIL (§9e)` | 赤。`'`alter_ field`' should be '`alter_field`' (zero space)` (実行 1) |
| 29 | A: CH-1004 (L579-585) の見出しの裸 ID の括弧 `(D-4)` を除く / B: CH-1019 (L1146-1152) の括弧から `, D-3 (2)` を除く — 残した除去と同じ種類 (裸 ID だけの括弧) を別の塊に 1 つ残す向き | 検査器は緑のまま、`REMOVED` 行が増える | A・B とも `comment provenance OK` のまま `removed_rows=50` → `51` (実行 4) |
| 20 | CH-1062 (L77-82、`#:` 塊) の 1 行目の `#:` を `#` にする | `FAIL (§9f)` | 赤。`CH-1062: '#:' Sphinx-style comment marker lost` (実行 3。同じ出力に T69 の試行の FAIL 行が 1 本重なる) |
| 19 (a) | 既存の訂正記録 (CH-0552、`structured.md`) の `old` を基準に無い文にする | `FAIL (§9f)` (手本) | 赤だが接頭辞は `FAIL (§9.3 (2))` (`basis correction #1 ... does not match the working-tree entry at the same position verbatim`)。基点の記録を変える変異は §9.3 規則 2 の赤で、手本の wrapper の `§9f` とは別 (実行 4。wo-section18.md の報告) |
| 23 | `structured.md` の fenced block に台帳に無い 3 桁の R 番号を足す | `check_doc_refs FAILED:` | 赤。`check_doc_refs FAILED: 1 dangling reference(s)` (実行 4。番号は伏せた) |
| 15 (確認) | CH の無い塊 L306 の 1 行を消す | `FAIL (§4.1 (2))` | 赤。`the sequence of CH-ID-less blocks changed (old 15, new 14)` (実行 2) |
| 22 (b) | 非該当 (上の実測) | — | — |
| (Y9-3 の実測) | CH-1014 (L1039-1069) 第 2 段落のラベル `Review round F-5 (`{scratchpad}/rulings-r4.md`): ` を除く (草案では (ii) で見送った編集) | 検査器が許すか | 許す: `comment provenance OK: 189 blocks checked` (実行 5)。見送りは (ii) の読みの問題で、検査器の制約ではない |

## 検査器が拒んだ編集 (最初の試行、実行の前に別に取った `--base` の出力。逐語)

```text
FAIL (§4.1 (3)) r2db-api/src/r2db_api/structured.py:368 cannot delete a whole sentence carrying a protected reference: 'Ruling O-3 (`{scratchpad}/rulings-r3-r7-flip.md` 追補4, 版フリップ監査差し戻し): a `field_constraints` KEY that is itself an identifier-syntax violation must not be echoed into `field` (SI-10 -- ...'
FAIL (§4.1 (3)) r2db-api/src/r2db_api/structured.py:591 cannot delete a whole sentence carrying a protected reference: 'Peer symmetry (work order §2 WP-2b "同型性テストの対象"): MitateDB-api places its own same-named, same-signature pair in `field_types.py` (...) -- no code is shared between the two peers (依頼者裁定 2026-09-03 案(a)); ...'
FAIL (§4.1 (3)) r2db-api/src/r2db_api/structured.py:649 retained text has no order-preserving match in the original block for: 'Peer symmetry (work order §2 WP-2c "同型性テストの対象"): ... (依頼者裁定案(a)); ...'
FAIL (§4.1 (3)) r2db-api/src/r2db_api/structured.py:742 retained text has no order-preserving match in the original block for: 'a record written before the 1.7.0 flip carries no `request_id` in its payload -- ...'
FAIL (§4.1 (3)) r2db-api/src/r2db_api/structured.py:796 cannot delete a whole sentence carrying a protected reference: 'Contract 1.7.0 (D-5 (6), U-3 = (A), ruling I-1, WP-2c): ...'
FAIL (§4.1 (3)) r2db-api/src/r2db_api/structured.py:1228 cannot delete a whole sentence carrying a protected reference: 'Contract 1.7.0 (D-5 (1)(i)/(3), ruling I-1, WP-2c): ...'
FAIL (§4.1 (3)) r2db-api/src/r2db_api/structured.py:1546 cannot delete a whole sentence carrying a protected reference: "Contract 1.7.0 (D-5 (8)/(9), addendum 2 S-b, ruling I-3, WP-2c): ..."
FAIL (§4.1 (3)) r2db-api/src/r2db_api/structured.py:1600 cannot delete a whole sentence carrying a protected reference: "Contract 1.7.0 (D-2 (7), U-1 = (β), WP-2a): ..."
FAIL (§4.1 (3)) r2db-api/src/r2db_api/structured.py:1617 cannot delete a whole sentence carrying a protected reference: 'Contract 1.7.0 (D-4 (7)/(3), addendum 2 S-a/S-j, WP-2b): ...'
FAIL (§4.1 (3)) r2db-api/src/r2db_api/structured.py:1893 cannot delete a whole sentence carrying a protected reference: "Contract 1.7.0 (D-5 (1)(i)/(3), ruling I-1, WP-2c): ..."
FAIL (§4.1 (3)) MitateDB-api/src/mitatedb_api/platform_declarations.py:70 retained text has no order-preserving match in the original block for: "The platform single-shot migration that creates the table and seeds ... (design §8 migration allocation: MitateDB `0007`; ...)"
FAIL (§4.1 (3)) MitateDB-api/src/mitatedb_api/platform_declarations.py:527 cannot delete a whole sentence carrying a protected reference: "--- F-6 / F-3c: ... -- design D-2(f), monitor ruling 2026-09-05."
FAIL (§4.1 (3)) r2db-api/src/r2db_api/structured.py:1187 cannot delete a whole sentence carrying a protected reference: 'Contract 1.7.0 (D-4 (2)/(4), WP-2b): the single tx-exit point -- plan validity, then commit vs rollback.'   (実行 3、T69 の試行)
```
(文は長いので `...` で省いた。全文は各塊の基準の本文。T20・T37 のラベルが (6) に当たらない理由は検査器の内部関数で確かめた: `_label_qualifies` False、T20 は `_label_japanese_char_count` = 53、T37 は内容語 6 (`Ruling`, `L-6/M-6`, `addendum`, `2`, `closure`, `audit`)。)

## 実行 1 (最初の spec。T69 の試行を含まない。この実行の spec は最終の spec と同じ内容)

```text
### apply structured
$ python3 $SP/cs9/tools/cs9_apply.py -C $WT --spec $SP/cs9/cs9-spec-structured.json
CH-1034 comment base L1862-1866 ApplicationCell._apply_schema_locked edits=1
CH-1033 comment base L1856-1858 ApplicationCell._apply_schema_locked edits=1
CH-1029 comment base L1543-1546 ApplicationCell._apply_schema_locked edits=1
CH-1027 docstring base L1488-1501 ApplicationCell._apply_schema_locked edits=2
CH-1026 docstring base L1461-1465 ApplicationCell.apply_schema edits=1
CH-1025 comment base L1301-1304 ApplicationCell._apply edits=1
CH-1024 comment base L1232-1237 ApplicationCell._apply edits=1
CH-1023 comment base L1225-1230 ApplicationCell._apply edits=1
CH-1022 comment base L1209-1212 ApplicationCell._transact_locked edits=1
CH-1020 comment base L1183-1192 ApplicationCell._transact_locked edits=1
CH-1019 comment base L1146-1152 ApplicationCell._transact_locked edits=1
CH-1018 comment base L1139-1144 ApplicationCell._transact_locked edits=1
CH-1017 comment base L1129-1135 ApplicationCell._transact_locked edits=1
CH-1016 comment base L1109-1112 ApplicationCell._transact_locked edits=1
CH-1015 comment base L1077-1085 ApplicationCell._transact_locked edits=1
CH-1014 docstring base L1039-1069 ApplicationCell._transact_locked edits=1
CH-1013 docstring base L1010-1016 ApplicationCell.transact edits=1
CH-1012 comment base L967-972 ApplicationCell._describe_entity edits=1
CH-1011 docstring base L950-955 ApplicationCell._describe_entity edits=1
CH-1010 comment base L891-895 ApplicationCell.query edits=1
CH-1009 comment base L827-827 ApplicationCell edits=1
CH-1007 comment base L757-765 ApplicationCell edits=1
CH-1004 comment base L579-585 <module> edits=1
CH-1003 comment base L514-514 bind_schema_operation edits=1
CH-1002 comment base L470-484 bind_schema_operation edits=1
CH-1001 comment base L444-448 bind_schema_operation edits=1
CH-0999 comment base L350-351 bind_schema_operation edits=1
CH-0998 comment base L338-342 bind_schema_operation edits=1
CH-0997 comment base L328-335 bind_schema_operation edits=1
CH-0996 comment base L309-319 bind_schema_operation edits=1
CH-0995 comment base L246-253 bind_schema_operation edits=1
CH-0994 comment base L236-240 bind_schema_operation edits=1
CH-0993 comment base L231-233 bind_schema_operation edits=1
CH-0992 comment base L226-228 bind_schema_operation edits=1
CH-0991 comment base L221-223 bind_schema_operation edits=1
CH-0990 comment base L195-199 bind_schema_operation edits=1
blocks=36 module_lines 1867 -> 1906
(exit 0)

### apply platform_declarations
$ python3 $SP/cs9/tools/cs9_apply.py -C $WT --spec $SP/cs9/cs9-spec-platform_declarations.json
CH-1067 comment base L1068-1074 check_role_connection_limits edits=1
CH-1066 comment base L887-920 <module> edits=1
CH-1065 comment base L862-883 <module> edits=1
CH-1064 docstring base L656-663 _role_setting_rows edits=1
CH-1062 comment base L77-82 <module> edits=1
CH-1060 docstring base L1-47 <module> edits=1
blocks=6 module_lines 1713 -> 1720
(exit 0)

### check_comment_provenance --base
$ python3 tools/check_comment_provenance.py --base 092e1a1 r2db-api/src/r2db_api/structured.py MitateDB-api/src/mitatedb_api/platform_declarations.py
comment provenance OK: 189 blocks checked
(exit 0)

### check_comment_provenance --register
$ python3 tools/check_comment_provenance.py --register
comment provenance register OK: 95 files scanned, 557 CH-IDs
(exit 0)

### check_doc_refs
$ python3 tools/check_doc_refs.py
SI: definitions=16 references=2282
C: definitions=37 references=4200
CCR: definitions=15 references=255
G: definitions=4 references=221
P: definitions=9 references=464
R: definitions=122 references=5126
L: definitions=145 references=1700
external references (reported only, no definition required):
  DM-0018: docs/design/DEVELOPMENT_PROCESS_HYGIENE_V1.md:80, docs/design/DEVELOPMENT_PROCESS_HYGIENE_V1.md:235, docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md:5, docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md:27, docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md:114, docs/work-orders/WORK_ORDER_DEVELOPMENT_PROCESS_HYGIENE_V1.md:120
  DM-0021: docs/design/ROADMAP_POST_PHASE7_V1.md:273, docs/design/ROADMAP_POST_PHASE7_V1.md:283
  DM-0025: docs/design/PHASE11_MIN_COMMON_PROFILE_V1.md:149, docs/design/PHASE11_MIN_COMMON_PROFILE_V1.md:1014, docs/design/ROADMAP_POST_PHASE7_V1.md:475
  DM-0052: docs/design/MITATEDB_PLATFORM_READONLY_INVENTORY_V0_1.md:6, docs/work-orders/WORK_ORDER_MITATEDB_OPERATION_DEPTH_PLATFORM_UPGRADE_V1.md:6
tracked markdown files scanned: 281
empty markdown files: 0
check_doc_refs OK: 0 dangling references
(exit 0)

### cs9_removed_tokens (worktree)
$ python3 $SP/cs9/tools/cs9_removed_tokens.py -C $WT
BASE 092e1a1 HEAD worktree
REMOVED	r2db-api/src/r2db_api/structured.py	L195-199	CH-0990	id	WP-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L221-223	CH-0991	id	D-3	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L221-223	CH-0991	id	WP-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L226-228	CH-0992	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L231-233	CH-0993	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L236-240	CH-0994	id	M-3	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L236-240	CH-0994	id	WP-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L246-253	CH-0995	id	B-1	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L328-335	CH-0997	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L338-342	CH-0998	id	N-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L338-342	CH-0998	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L350-351	CH-0999	id	N-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L444-448	CH-1001	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L470-484	CH-1002	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L579-585	CH-1004	id	WP-2b	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L757-765	CH-1007	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L827-827	CH-1009	id	WP-2c	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L891-895	CH-1010	id	WP-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L950-955	CH-1011	id	WP-2b	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L967-972	CH-1012	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1010-1016	CH-1013	id	U-7	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1010-1016	CH-1013	id	WP-6d	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1039-1069	CH-1014	id	WP-2b	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1077-1085	CH-1015	id	WP-2c	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1109-1112	CH-1016	id	WP-2e	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1129-1135	CH-1017	id	D-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1139-1144	CH-1018	id	M-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1139-1144	CH-1018	id	WP-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1146-1152	CH-1019	id	M-3	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1183-1192	CH-1020	id	D-10	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1183-1192	CH-1020	id	D-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1209-1212	CH-1022	id	WP-2e	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1225-1230	CH-1023	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1232-1237	CH-1024	id	D-3	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1232-1237	CH-1024	id	M-3	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1301-1304	CH-1025	id	D-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1461-1465	CH-1026	id	U-7	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1461-1465	CH-1026	id	WP-6d	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1488-1501	CH-1027	id	WP-2b	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1543-1546	CH-1029	id	M-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1543-1546	CH-1029	id	WP-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1856-1858	CH-1033	id	WP-2e	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1862-1866	CH-1034	id	F-8	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L77-82	CH-1062	id	D-5	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L77-82	CH-1062	id	WP-6b	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L862-883	CH-1065	id	L-2	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L862-883	CH-1065	id	M-7	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L887-920	CH-1066	id	WP-4f	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L1068-1074	CH-1067	id	M-1	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L1068-1074	CH-1067	id	WP-4	x1
SUMMARY ch_blocks=42 ws_only=0 unpaired=0 removed_rows=50
(exit 0)

### repull --dry-run
$ python3 $SP/cs9/tools/repull.py --dry-run 092e1a1 security/CONTROL_MAPPING.md -- r2db-api/src/r2db_api/structured.py MitateDB-api/src/mitatedb_api/platform_declarations.py
security/CONTROL_MAPPING.md:372: structured.py :884 -> :899
security/CONTROL_MAPPING.md:686: structured.py :1145 -> :1173
security/CONTROL_MAPPING.md:686: structured.py :1599 -> :1636
security/CONTROL_MAPPING.md:902: platform_declarations.py :1145 -> :1152
security/CONTROL_MAPPING.md:903: platform_declarations.py :1145 -> :1152
security/CONTROL_MAPPING.md:1074: platform_declarations.py :474 -> :476
security/CONTROL_MAPPING.md:1079: platform_declarations.py :440 -> :442
security/CONTROL_MAPPING.md:1090: platform_declarations.py :1005 -> :1011
security/CONTROL_MAPPING.md:1091: platform_declarations.py :1239 -> :1246
security/CONTROL_MAPPING.md:1091: platform_declarations.py :1348 -> :1355
security/CONTROL_MAPPING.md:1091: platform_declarations.py :1325 -> :1332
security/CONTROL_MAPPING.md:1092: platform_declarations.py :1239 -> :1246
security/CONTROL_MAPPING.md:1095: platform_declarations.py :1239 -> :1246
security/CONTROL_MAPPING.md:1096: platform_declarations.py :1493 -> :1500
security/CONTROL_MAPPING.md:1101: platform_declarations.py :1005 -> :1011
security/CONTROL_MAPPING.md:1103: platform_declarations.py :1239 -> :1246
security/CONTROL_MAPPING.md:1244: structured.py :1796 -> :1833
security/CONTROL_MAPPING.md:1245: structured.py :568 -> :580
security/CONTROL_MAPPING.md:1246: structured.py :1807 -> :1844
security/CONTROL_MAPPING.md:1248: structured.py :1784 -> :1821
security/CONTROL_MAPPING.md:1604: structured.py :995 -> :1015
security/CONTROL_MAPPING.md:2004: platform_declarations.py :1562 -> :1569
security/CONTROL_MAPPING.md:2016: platform_declarations.py :719 -> :724
security/CONTROL_MAPPING.md: changed 23, unresolved 0, not applied 0
(exit 0)

### repull guard: lines rewriting a reference into r2db-api's platform_declarations.py: 0

### AST r2db-api/src/r2db_api/structured.py: identical (docstrings excluded, design §4.1 (1)); lines 1867 -> 1906
    base blocks 122, new blocks 122; base blocks not in the spec whose text is absent verbatim from the new module: []
    history tokens 112 -> 65; date lines 3 -> 2 (new: [596, 654]); CH blocks 13 -> 49; `#:` lines 0 -> 0; scratchpad lines 9 -> 8; changed docstrings with a backslash: 0

    22(b): CH blocks of this spec with a real path split by a line wrap: [('CH-1034', '`test_constraints_declaration.py`')]

### AST MitateDB-api/src/mitatedb_api/platform_declarations.py: identical (docstrings excluded, design §4.1 (1)); lines 1713 -> 1720
    base blocks 67, new blocks 67; base blocks not in the spec whose text is absent verbatim from the new module: []
    history tokens 42 -> 31; date lines 15 -> 11 (new: [23, 73, 243, 268, 531, 561, 572, 685, 922, 977, 1049]); CH blocks 1 -> 7; `#:` lines 103 -> 102; scratchpad lines 7 -> 6; changed docstrings with a backslash: 0

    22(b): CH blocks of this spec with a real path split by a line wrap: []

### mutation c17 (condition 17: capitalise after the removed label, CH block base L246): "# symmetric with `bind_mutation`'s identical" -> "# Symmetric with `bind_mutation`'s identical"
$ python3 tools/check_comment_provenance.py --base 092e1a1 r2db-api/src/r2db_api/structured.py MitateDB-api/src/mitatedb_api/platform_declarations.py
FAIL (§4.1 (3)) r2db-api/src/r2db_api/structured.py:251 cannot delete a whole sentence carrying a protected reference: "Review blocker B-1: symmetric with `bind_mutation`'s identical check above (now in `mutation_binding.py`) -- a non-boolean truthy `destructive` (a string, an int, an object) must never be silently coerced into `True` by a loose `bool(...)` cast downstream."
(exit 1)

    expected 'FAIL (§4.1 (3))': RED as expected; matching lines 1, other FAIL lines 0

### mutation c21a (condition 21 (a): join two words that need a space, CH block base L246): 'This is a shape check (contract' -> 'This is a shapecheck (contract'
$ python3 tools/check_comment_provenance.py --base 092e1a1 r2db-api/src/r2db_api/structured.py MitateDB-api/src/mitatedb_api/platform_declarations.py
FAIL (§4.1 (3)) r2db-api/src/r2db_api/structured.py:251 retained text has no order-preserving match in the original block for: 'This is a shapecheck (contract `SchemaOperationRequest.destructive: {"type": "boolean"}`), so it runs here, before the destructive-confirmation gate itself, per contract `evaluation_order` (shape validation precedes confirmation evaluation).'
(exit 1)

    expected 'FAIL (§4.1 (3))': RED as expected; matching lines 1, other FAIL lines 0

### mutation c21c (condition 21 (c): join a backtick-span line wrap with a space, CH block base L470): '`alter_\n        # field` redeclares' -> '`alter_ field` redeclares'
$ python3 tools/check_comment_provenance.py --base 092e1a1 r2db-api/src/r2db_api/structured.py MitateDB-api/src/mitatedb_api/platform_declarations.py
FAIL (§9e) r2db-api/src/r2db_api/structured.py:480 broken line-wrap join for CH-1002: '`alter_ field`' should be '`alter_field`' (zero space)
(exit 1)

    expected 'FAIL (§9e)': RED as expected; matching lines 1, other FAIL lines 0

### 21 (b) candidates (`/` at a line end inside a CH block of this spec): [('CH-1014', 1069, 'y`/`operations`/`transaction`/', '`budget`, never `pla'), ('CH-1014', 1070, 'mselves -- H-1, `{scratchpad}/', 'rulings-r4.md` adden')]

### mutation c21b (condition 21 (b): `/` line wrap joined with a space, CH-1014): '        `service.py` assembled (`entity`/`operatio' -> '        `service.py` assembled (`entity`/`operatio'
$ python3 tools/check_comment_provenance.py --base 092e1a1 r2db-api/src/r2db_api/structured.py MitateDB-api/src/mitatedb_api/platform_declarations.py
FAIL (§9e) r2db-api/src/r2db_api/structured.py:1061 broken line-wrap join for CH-1014: '(`entity`/`operations`/`transaction`/ `budget`,' should be '(`entity`/`operations`/`transaction`/`budget`,' (zero space)
(exit 1)

    expected 'FAIL (§9e)': RED as expected; matching lines 1, other FAIL lines 0

### mutation c29 (condition 29: one more allowed removal in CH block base L1077 -> REMOVED rows must grow): old occurs 0 times (not applied)

### mutation c29 (same mutation, checker still green?): old occurs 0 times (not applied)

### line-number pins into the two modules (grep; exit 1 = none)
$ grep -nE \("structured\.py", *[0-9]+|\("platform_declarations\.py", *[0-9]+ r2db-api/tests/test_l1_details_vocabulary_ast_scan.py MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py

(exit 1)

### restore check 1: all 5 files match the base sha256
### restore check 2: all 5 files match the base sha256
### git status of the touched paths after restore
$ git status --short -- r2db-api/src/r2db_api/structured.py MitateDB-api/src/mitatedb_api/platform_declarations.py docs/code-history/r2db-api/structured.md docs/code-history/MitateDB-api/platform_declarations.md security/CONTROL_MAPPING.md

(exit 0)
```

## 実行 2 (c29 の最初の試み (当たらず)・c20 (当たらず)・c15 の確認)

```text
### apply structured
$ python3 $SP/cs9/tools/cs9_apply.py -C $WT --spec $SP/cs9/cs9-spec-structured.json
CH-1034 comment base L1862-1866 ApplicationCell._apply_schema_locked edits=1
CH-1033 comment base L1856-1858 ApplicationCell._apply_schema_locked edits=1
CH-1029 comment base L1543-1546 ApplicationCell._apply_schema_locked edits=1
CH-1027 docstring base L1488-1501 ApplicationCell._apply_schema_locked edits=2
CH-1026 docstring base L1461-1465 ApplicationCell.apply_schema edits=1
CH-1025 comment base L1301-1304 ApplicationCell._apply edits=1
CH-1024 comment base L1232-1237 ApplicationCell._apply edits=1
CH-1023 comment base L1225-1230 ApplicationCell._apply edits=1
CH-1022 comment base L1209-1212 ApplicationCell._transact_locked edits=1
CH-1020 comment base L1183-1192 ApplicationCell._transact_locked edits=1
CH-1019 comment base L1146-1152 ApplicationCell._transact_locked edits=1
CH-1018 comment base L1139-1144 ApplicationCell._transact_locked edits=1
CH-1017 comment base L1129-1135 ApplicationCell._transact_locked edits=1
CH-1016 comment base L1109-1112 ApplicationCell._transact_locked edits=1
CH-1015 comment base L1077-1085 ApplicationCell._transact_locked edits=1
CH-1014 docstring base L1039-1069 ApplicationCell._transact_locked edits=1
CH-1013 docstring base L1010-1016 ApplicationCell.transact edits=1
CH-1012 comment base L967-972 ApplicationCell._describe_entity edits=1
CH-1011 docstring base L950-955 ApplicationCell._describe_entity edits=1
CH-1010 comment base L891-895 ApplicationCell.query edits=1
CH-1009 comment base L827-827 ApplicationCell edits=1
CH-1007 comment base L757-765 ApplicationCell edits=1
CH-1004 comment base L579-585 <module> edits=1
CH-1003 comment base L514-514 bind_schema_operation edits=1
CH-1002 comment base L470-484 bind_schema_operation edits=1
CH-1001 comment base L444-448 bind_schema_operation edits=1
CH-0999 comment base L350-351 bind_schema_operation edits=1
CH-0998 comment base L338-342 bind_schema_operation edits=1
CH-0997 comment base L328-335 bind_schema_operation edits=1
CH-0996 comment base L309-319 bind_schema_operation edits=1
CH-0995 comment base L246-253 bind_schema_operation edits=1
CH-0994 comment base L236-240 bind_schema_operation edits=1
CH-0993 comment base L231-233 bind_schema_operation edits=1
CH-0992 comment base L226-228 bind_schema_operation edits=1
CH-0991 comment base L221-223 bind_schema_operation edits=1
CH-0990 comment base L195-199 bind_schema_operation edits=1
blocks=36 module_lines 1867 -> 1906
(exit 0)

### apply platform_declarations
$ python3 $SP/cs9/tools/cs9_apply.py -C $WT --spec $SP/cs9/cs9-spec-platform_declarations.json
CH-1067 comment base L1068-1074 check_role_connection_limits edits=1
CH-1066 comment base L887-920 <module> edits=1
CH-1065 comment base L862-883 <module> edits=1
CH-1064 docstring base L656-663 _role_setting_rows edits=1
CH-1062 comment base L77-82 <module> edits=1
CH-1060 docstring base L1-47 <module> edits=1
blocks=6 module_lines 1713 -> 1720
(exit 0)

### cs9_removed_tokens before the c29 mutation (SUMMARY line is the reference)
$ python3 $SP/cs9/tools/cs9_removed_tokens.py -C $WT
BASE 092e1a1 HEAD worktree
REMOVED	r2db-api/src/r2db_api/structured.py	L195-199	CH-0990	id	WP-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L221-223	CH-0991	id	D-3	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L221-223	CH-0991	id	WP-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L226-228	CH-0992	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L231-233	CH-0993	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L236-240	CH-0994	id	M-3	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L236-240	CH-0994	id	WP-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L246-253	CH-0995	id	B-1	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L328-335	CH-0997	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L338-342	CH-0998	id	N-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L338-342	CH-0998	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L350-351	CH-0999	id	N-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L444-448	CH-1001	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L470-484	CH-1002	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L579-585	CH-1004	id	WP-2b	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L757-765	CH-1007	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L827-827	CH-1009	id	WP-2c	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L891-895	CH-1010	id	WP-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L950-955	CH-1011	id	WP-2b	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L967-972	CH-1012	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1010-1016	CH-1013	id	U-7	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1010-1016	CH-1013	id	WP-6d	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1039-1069	CH-1014	id	WP-2b	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1077-1085	CH-1015	id	WP-2c	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1109-1112	CH-1016	id	WP-2e	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1129-1135	CH-1017	id	D-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1139-1144	CH-1018	id	M-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1139-1144	CH-1018	id	WP-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1146-1152	CH-1019	id	M-3	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1183-1192	CH-1020	id	D-10	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1183-1192	CH-1020	id	D-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1209-1212	CH-1022	id	WP-2e	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1225-1230	CH-1023	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1232-1237	CH-1024	id	D-3	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1232-1237	CH-1024	id	M-3	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1301-1304	CH-1025	id	D-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1461-1465	CH-1026	id	U-7	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1461-1465	CH-1026	id	WP-6d	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1488-1501	CH-1027	id	WP-2b	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1543-1546	CH-1029	id	M-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1543-1546	CH-1029	id	WP-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1856-1858	CH-1033	id	WP-2e	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1862-1866	CH-1034	id	F-8	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L77-82	CH-1062	id	D-5	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L77-82	CH-1062	id	WP-6b	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L862-883	CH-1065	id	L-2	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L862-883	CH-1065	id	M-7	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L887-920	CH-1066	id	WP-4f	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L1068-1074	CH-1067	id	M-1	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L1068-1074	CH-1067	id	WP-4	x1
SUMMARY ch_blocks=42 ws_only=0 unpaired=0 removed_rows=50
(exit 0)

### mutation c29 (condition 29: one more allowed removal, CH-1016 base L1077-1085: drop `(ruling I-7 / D-4)` -> REMOVED rows must grow by 2) -> cs9_removed_tokens
$ python3 $SP/cs9/tools/cs9_removed_tokens.py -C $WT
BASE 092e1a1 HEAD worktree
REMOVED	r2db-api/src/r2db_api/structured.py	L195-199	CH-0990	id	WP-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L221-223	CH-0991	id	D-3	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L221-223	CH-0991	id	WP-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L226-228	CH-0992	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L231-233	CH-0993	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L236-240	CH-0994	id	M-3	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L236-240	CH-0994	id	WP-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L246-253	CH-0995	id	B-1	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L328-335	CH-0997	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L338-342	CH-0998	id	N-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L338-342	CH-0998	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L350-351	CH-0999	id	N-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L444-448	CH-1001	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L470-484	CH-1002	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L579-585	CH-1004	id	WP-2b	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L757-765	CH-1007	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L827-827	CH-1009	id	WP-2c	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L891-895	CH-1010	id	WP-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L950-955	CH-1011	id	WP-2b	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L967-972	CH-1012	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1010-1016	CH-1013	id	U-7	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1010-1016	CH-1013	id	WP-6d	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1039-1069	CH-1014	id	WP-2b	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1077-1085	CH-1015	id	D-4	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1077-1085	CH-1015	id	I-7	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1077-1085	CH-1015	id	WP-2c	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1109-1112	CH-1016	id	WP-2e	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1129-1135	CH-1017	id	D-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1139-1144	CH-1018	id	M-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1139-1144	CH-1018	id	WP-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1146-1152	CH-1019	id	M-3	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1183-1192	CH-1020	id	D-10	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1183-1192	CH-1020	id	D-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1209-1212	CH-1022	id	WP-2e	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1225-1230	CH-1023	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1232-1237	CH-1024	id	D-3	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1232-1237	CH-1024	id	M-3	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1301-1304	CH-1025	id	D-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1461-1465	CH-1026	id	U-7	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1461-1465	CH-1026	id	WP-6d	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1488-1501	CH-1027	id	WP-2b	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1543-1546	CH-1029	id	M-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1543-1546	CH-1029	id	WP-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1856-1858	CH-1033	id	WP-2e	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1862-1866	CH-1034	id	F-8	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L77-82	CH-1062	id	D-5	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L77-82	CH-1062	id	WP-6b	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L862-883	CH-1065	id	L-2	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L862-883	CH-1065	id	M-7	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L887-920	CH-1066	id	WP-4f	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L1068-1074	CH-1067	id	M-1	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L1068-1074	CH-1067	id	WP-4	x1
SUMMARY ch_blocks=42 ws_only=0 unpaired=0 removed_rows=52
(exit 0)

### mutation c29 (condition 29: one more allowed removal, CH-1016 base L1077-1085: drop `(ruling I-7 / D-4)` -> REMOVED rows must grow by 2) -> check_comment_provenance --base (must stay green: the removal is allowed)
$ python3 tools/check_comment_provenance.py --base 092e1a1 r2db-api/src/r2db_api/structured.py MitateDB-api/src/mitatedb_api/platform_declarations.py
FAIL (§4.1 (3)) r2db-api/src/r2db_api/structured.py:1101 retained text has no order-preserving match in the original block for: 'A `dry_run` never consults or writes a record at all: the guard below is `idempotency_key is not None and not dry_run`, never merely `idempotency_key is not None`.'
(exit 1)

### mutation c20 (condition 20: a `#:` line of the CH `#:` block base L77-82 becomes `#`): old occurs 0 times (not applied)

### mutation c15-style sanity (CH-less block loses a sentence: base L306 `(a)` line removed) -- expected FAIL (§4.1 (2)) -> check_comment_provenance --base
$ python3 tools/check_comment_provenance.py --base 092e1a1 r2db-api/src/r2db_api/structured.py MitateDB-api/src/mitatedb_api/platform_declarations.py
FAIL (§4.1 (2)) r2db-api/src/r2db_api/structured.py:278 scope/anchor ('bind_schema_operation', 'stmt#24'): the sequence of CH-ID-less blocks changed (old 15, new 14) -- a block was added, removed, or moved to a different statement without a CH-ID reference
(exit 1)

### restore check 1: all match the base sha256
### restore check 2: all match the base sha256
### git status after restore
$ git status --short -- r2db-api/src/r2db_api/structured.py MitateDB-api/src/mitatedb_api/platform_declarations.py docs/code-history/r2db-api/structured.md docs/code-history/MitateDB-api/platform_declarations.md security/CONTROL_MAPPING.md

(exit 0)
```

## 実行 3 (T69 の試行を spec に含めた状態。検査器の FAIL 行 1 本は T69 の赤で、各変異の出力に重なって出る — 「別の理由の赤」として読み分けること。c20 の `FAIL (§9f)` 行はこの実行で取った)

```text
### apply structured
$ python3 $SP/cs9/tools/cs9_apply.py -C $WT --spec $SP/cs9/cs9-spec-structured.json
CH-1035 comment base L1862-1866 ApplicationCell._apply_schema_locked edits=1
CH-1034 comment base L1856-1858 ApplicationCell._apply_schema_locked edits=1
CH-1030 comment base L1543-1546 ApplicationCell._apply_schema_locked edits=1
CH-1028 docstring base L1488-1501 ApplicationCell._apply_schema_locked edits=2
CH-1027 docstring base L1461-1465 ApplicationCell.apply_schema edits=1
CH-1026 comment base L1301-1304 ApplicationCell._apply edits=1
CH-1025 comment base L1232-1237 ApplicationCell._apply edits=1
CH-1024 comment base L1225-1230 ApplicationCell._apply edits=1
CH-1023 comment base L1209-1212 ApplicationCell._transact_locked edits=1
CH-1021 comment base L1183-1192 ApplicationCell._transact_locked edits=1
CH-1020 comment base L1159-1165 ApplicationCell._transact_locked edits=1
CH-1019 comment base L1146-1152 ApplicationCell._transact_locked edits=1
CH-1018 comment base L1139-1144 ApplicationCell._transact_locked edits=1
CH-1017 comment base L1129-1135 ApplicationCell._transact_locked edits=1
CH-1016 comment base L1109-1112 ApplicationCell._transact_locked edits=1
CH-1015 comment base L1077-1085 ApplicationCell._transact_locked edits=1
CH-1014 docstring base L1039-1069 ApplicationCell._transact_locked edits=1
CH-1013 docstring base L1010-1016 ApplicationCell.transact edits=1
CH-1012 comment base L967-972 ApplicationCell._describe_entity edits=1
CH-1011 docstring base L950-955 ApplicationCell._describe_entity edits=1
CH-1010 comment base L891-895 ApplicationCell.query edits=1
CH-1009 comment base L827-827 ApplicationCell edits=1
CH-1007 comment base L757-765 ApplicationCell edits=1
CH-1004 comment base L579-585 <module> edits=1
CH-1003 comment base L514-514 bind_schema_operation edits=1
CH-1002 comment base L470-484 bind_schema_operation edits=1
CH-1001 comment base L444-448 bind_schema_operation edits=1
CH-0999 comment base L350-351 bind_schema_operation edits=1
CH-0998 comment base L338-342 bind_schema_operation edits=1
CH-0997 comment base L328-335 bind_schema_operation edits=1
CH-0996 comment base L309-319 bind_schema_operation edits=1
CH-0995 comment base L246-253 bind_schema_operation edits=1
CH-0994 comment base L236-240 bind_schema_operation edits=1
CH-0993 comment base L231-233 bind_schema_operation edits=1
CH-0992 comment base L226-228 bind_schema_operation edits=1
CH-0991 comment base L221-223 bind_schema_operation edits=1
CH-0990 comment base L195-199 bind_schema_operation edits=1
blocks=37 module_lines 1867 -> 1907
(exit 0)

### apply platform_declarations
$ python3 $SP/cs9/tools/cs9_apply.py -C $WT --spec $SP/cs9/cs9-spec-platform_declarations.json
CH-1067 comment base L1068-1074 check_role_connection_limits edits=1
CH-1066 comment base L887-920 <module> edits=1
CH-1065 comment base L862-883 <module> edits=1
CH-1064 docstring base L656-663 _role_setting_rows edits=1
CH-1062 comment base L77-82 <module> edits=1
CH-1060 docstring base L1-47 <module> edits=1
blocks=6 module_lines 1713 -> 1720
(exit 0)

### check_comment_provenance --base (with the T69 trial)
$ python3 tools/check_comment_provenance.py --base 092e1a1 r2db-api/src/r2db_api/structured.py MitateDB-api/src/mitatedb_api/platform_declarations.py
FAIL (§4.1 (3)) r2db-api/src/r2db_api/structured.py:1187 cannot delete a whole sentence carrying a protected reference: 'Contract 1.7.0 (D-4 (2)/(4), WP-2b): the single tx-exit point -- plan validity, then commit vs rollback.'
(exit 1)

### mutation c29 candidate A (CH block base L579: drop the bare-ID paren `(D-4)` of the section header -> REMOVED rows must grow by 1, checker must stay green) -> check_comment_provenance --base
$ python3 tools/check_comment_provenance.py --base 092e1a1 r2db-api/src/r2db_api/structured.py MitateDB-api/src/mitatedb_api/platform_declarations.py
FAIL (§4.1 (3)) r2db-api/src/r2db_api/structured.py:1187 cannot delete a whole sentence carrying a protected reference: 'Contract 1.7.0 (D-4 (2)/(4), WP-2b): the single tx-exit point -- plan validity, then commit vs rollback.'
(exit 1)

### mutation c29 candidate A (CH block base L579: drop the bare-ID paren `(D-4)` of the section header -> REMOVED rows must grow by 1, checker must stay green) -> cs9_removed_tokens
$ python3 $SP/cs9/tools/cs9_removed_tokens.py -C $WT
BASE 092e1a1 HEAD worktree
REMOVED	r2db-api/src/r2db_api/structured.py	L195-199	CH-0990	id	WP-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L221-223	CH-0991	id	D-3	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L221-223	CH-0991	id	WP-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L226-228	CH-0992	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L231-233	CH-0993	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L236-240	CH-0994	id	M-3	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L236-240	CH-0994	id	WP-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L246-253	CH-0995	id	B-1	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L328-335	CH-0997	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L338-342	CH-0998	id	N-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L338-342	CH-0998	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L350-351	CH-0999	id	N-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L444-448	CH-1001	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L470-484	CH-1002	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L579-585	CH-1004	id	D-4	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L579-585	CH-1004	id	WP-2b	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L757-765	CH-1007	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L827-827	CH-1009	id	WP-2c	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L891-895	CH-1010	id	WP-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L950-955	CH-1011	id	WP-2b	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L967-972	CH-1012	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1010-1016	CH-1013	id	U-7	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1010-1016	CH-1013	id	WP-6d	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1039-1069	CH-1014	id	WP-2b	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1077-1085	CH-1015	id	WP-2c	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1109-1112	CH-1016	id	WP-2e	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1129-1135	CH-1017	id	D-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1139-1144	CH-1018	id	M-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1139-1144	CH-1018	id	WP-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1146-1152	CH-1019	id	M-3	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1159-1165	CH-1020	id	WP-2b	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1183-1192	CH-1021	id	D-10	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1183-1192	CH-1021	id	D-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1209-1212	CH-1023	id	WP-2e	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1225-1230	CH-1024	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1232-1237	CH-1025	id	D-3	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1232-1237	CH-1025	id	M-3	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1301-1304	CH-1026	id	D-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1461-1465	CH-1027	id	U-7	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1461-1465	CH-1027	id	WP-6d	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1488-1501	CH-1028	id	WP-2b	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1543-1546	CH-1030	id	M-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1543-1546	CH-1030	id	WP-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1856-1858	CH-1034	id	WP-2e	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1862-1866	CH-1035	id	F-8	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L77-82	CH-1062	id	D-5	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L77-82	CH-1062	id	WP-6b	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L862-883	CH-1065	id	L-2	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L862-883	CH-1065	id	M-7	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L887-920	CH-1066	id	WP-4f	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L1068-1074	CH-1067	id	M-1	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L1068-1074	CH-1067	id	WP-4	x1
SUMMARY ch_blocks=43 ws_only=0 unpaired=0 removed_rows=52
(exit 0)

### mutation c29 candidate B (CH block base L1146: drop `, D-3 (2)` from a content paren -> REMOVED rows must grow by 1, checker must stay green) -> check_comment_provenance --base
$ python3 tools/check_comment_provenance.py --base 092e1a1 r2db-api/src/r2db_api/structured.py MitateDB-api/src/mitatedb_api/platform_declarations.py
FAIL (§4.1 (3)) r2db-api/src/r2db_api/structured.py:1186 cannot delete a whole sentence carrying a protected reference: 'Contract 1.7.0 (D-4 (2)/(4), WP-2b): the single tx-exit point -- plan validity, then commit vs rollback.'
(exit 1)

### mutation c29 candidate B (CH block base L1146: drop `, D-3 (2)` from a content paren -> REMOVED rows must grow by 1, checker must stay green) -> cs9_removed_tokens
$ python3 $SP/cs9/tools/cs9_removed_tokens.py -C $WT
BASE 092e1a1 HEAD worktree
REMOVED	r2db-api/src/r2db_api/structured.py	L195-199	CH-0990	id	WP-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L221-223	CH-0991	id	D-3	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L221-223	CH-0991	id	WP-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L226-228	CH-0992	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L231-233	CH-0993	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L236-240	CH-0994	id	M-3	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L236-240	CH-0994	id	WP-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L246-253	CH-0995	id	B-1	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L328-335	CH-0997	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L338-342	CH-0998	id	N-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L338-342	CH-0998	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L350-351	CH-0999	id	N-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L444-448	CH-1001	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L470-484	CH-1002	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L579-585	CH-1004	id	WP-2b	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L757-765	CH-1007	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L827-827	CH-1009	id	WP-2c	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L891-895	CH-1010	id	WP-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L950-955	CH-1011	id	WP-2b	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L967-972	CH-1012	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1010-1016	CH-1013	id	U-7	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1010-1016	CH-1013	id	WP-6d	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1039-1069	CH-1014	id	WP-2b	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1077-1085	CH-1015	id	WP-2c	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1109-1112	CH-1016	id	WP-2e	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1129-1135	CH-1017	id	D-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1139-1144	CH-1018	id	M-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1139-1144	CH-1018	id	WP-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1146-1152	CH-1019	id	D-3	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1146-1152	CH-1019	id	M-3	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1159-1165	CH-1020	id	WP-2b	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1183-1192	CH-1021	id	D-10	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1183-1192	CH-1021	id	D-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1209-1212	CH-1023	id	WP-2e	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1225-1230	CH-1024	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1232-1237	CH-1025	id	D-3	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1232-1237	CH-1025	id	M-3	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1301-1304	CH-1026	id	D-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1461-1465	CH-1027	id	U-7	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1461-1465	CH-1027	id	WP-6d	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1488-1501	CH-1028	id	WP-2b	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1543-1546	CH-1030	id	M-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1543-1546	CH-1030	id	WP-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1856-1858	CH-1034	id	WP-2e	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1862-1866	CH-1035	id	F-8	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L77-82	CH-1062	id	D-5	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L77-82	CH-1062	id	WP-6b	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L862-883	CH-1065	id	L-2	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L862-883	CH-1065	id	M-7	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L887-920	CH-1066	id	WP-4f	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L1068-1074	CH-1067	id	M-1	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L1068-1074	CH-1067	id	WP-4	x1
SUMMARY ch_blocks=43 ws_only=0 unpaired=0 removed_rows=52
(exit 0)

### mutation c20 (condition 20: the first `#:` line of the CH `#:` block base L77-82 becomes `#`) -> check_comment_provenance --base
$ python3 tools/check_comment_provenance.py --base 092e1a1 r2db-api/src/r2db_api/structured.py MitateDB-api/src/mitatedb_api/platform_declarations.py
FAIL (§4.1 (3)) r2db-api/src/r2db_api/structured.py:1187 cannot delete a whole sentence carrying a protected reference: 'Contract 1.7.0 (D-4 (2)/(4), WP-2b): the single tx-exit point -- plan validity, then commit vs rollback.'
FAIL (§9f) MitateDB-api/src/mitatedb_api/platform_declarations.py:78 CH-1062: '#:' Sphinx-style comment marker lost (basis used '#:' lines, new block does not)
(exit 1)

### restore check 1: all match the base sha256
### restore check 2: all match the base sha256
### git status after restore
$ git status --short -- r2db-api/src/r2db_api/structured.py MitateDB-api/src/mitatedb_api/platform_declarations.py docs/code-history/r2db-api/structured.md docs/code-history/MitateDB-api/platform_declarations.md security/CONTROL_MAPPING.md

(exit 0)
```

## 実行 4 (最終の spec。検査器・`--register`・監査スクリプトの最終値、c29 (A / B)・c19a・c23)

```text
### apply structured
$ python3 $SP/cs9/tools/cs9_apply.py -C $WT --spec $SP/cs9/cs9-spec-structured.json
CH-1034 comment base L1862-1866 ApplicationCell._apply_schema_locked edits=1
CH-1033 comment base L1856-1858 ApplicationCell._apply_schema_locked edits=1
CH-1029 comment base L1543-1546 ApplicationCell._apply_schema_locked edits=1
CH-1027 docstring base L1488-1501 ApplicationCell._apply_schema_locked edits=2
CH-1026 docstring base L1461-1465 ApplicationCell.apply_schema edits=1
CH-1025 comment base L1301-1304 ApplicationCell._apply edits=1
CH-1024 comment base L1232-1237 ApplicationCell._apply edits=1
CH-1023 comment base L1225-1230 ApplicationCell._apply edits=1
CH-1022 comment base L1209-1212 ApplicationCell._transact_locked edits=1
CH-1020 comment base L1183-1192 ApplicationCell._transact_locked edits=1
CH-1019 comment base L1146-1152 ApplicationCell._transact_locked edits=1
CH-1018 comment base L1139-1144 ApplicationCell._transact_locked edits=1
CH-1017 comment base L1129-1135 ApplicationCell._transact_locked edits=1
CH-1016 comment base L1109-1112 ApplicationCell._transact_locked edits=1
CH-1015 comment base L1077-1085 ApplicationCell._transact_locked edits=1
CH-1014 docstring base L1039-1069 ApplicationCell._transact_locked edits=1
CH-1013 docstring base L1010-1016 ApplicationCell.transact edits=1
CH-1012 comment base L967-972 ApplicationCell._describe_entity edits=1
CH-1011 docstring base L950-955 ApplicationCell._describe_entity edits=1
CH-1010 comment base L891-895 ApplicationCell.query edits=1
CH-1009 comment base L827-827 ApplicationCell edits=1
CH-1007 comment base L757-765 ApplicationCell edits=1
CH-1004 comment base L579-585 <module> edits=1
CH-1003 comment base L514-514 bind_schema_operation edits=1
CH-1002 comment base L470-484 bind_schema_operation edits=1
CH-1001 comment base L444-448 bind_schema_operation edits=1
CH-0999 comment base L350-351 bind_schema_operation edits=1
CH-0998 comment base L338-342 bind_schema_operation edits=1
CH-0997 comment base L328-335 bind_schema_operation edits=1
CH-0996 comment base L309-319 bind_schema_operation edits=1
CH-0995 comment base L246-253 bind_schema_operation edits=1
CH-0994 comment base L236-240 bind_schema_operation edits=1
CH-0993 comment base L231-233 bind_schema_operation edits=1
CH-0992 comment base L226-228 bind_schema_operation edits=1
CH-0991 comment base L221-223 bind_schema_operation edits=1
CH-0990 comment base L195-199 bind_schema_operation edits=1
blocks=36 module_lines 1867 -> 1906
(exit 0)

### apply platform_declarations
$ python3 $SP/cs9/tools/cs9_apply.py -C $WT --spec $SP/cs9/cs9-spec-platform_declarations.json
CH-1067 comment base L1068-1074 check_role_connection_limits edits=1
CH-1066 comment base L887-920 <module> edits=1
CH-1065 comment base L862-883 <module> edits=1
CH-1064 docstring base L656-663 _role_setting_rows edits=1
CH-1062 comment base L77-82 <module> edits=1
CH-1060 docstring base L1-47 <module> edits=1
blocks=6 module_lines 1713 -> 1720
(exit 0)

### check_comment_provenance --base (final spec)
$ python3 tools/check_comment_provenance.py --base 092e1a1 r2db-api/src/r2db_api/structured.py MitateDB-api/src/mitatedb_api/platform_declarations.py
comment provenance OK: 189 blocks checked
(exit 0)

### check_comment_provenance --register (final spec)
$ python3 tools/check_comment_provenance.py --register
comment provenance register OK: 95 files scanned, 557 CH-IDs
(exit 0)

### cs9_removed_tokens (final spec, worktree)
$ python3 $SP/cs9/tools/cs9_removed_tokens.py -C $WT
BASE 092e1a1 HEAD worktree
REMOVED	r2db-api/src/r2db_api/structured.py	L195-199	CH-0990	id	WP-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L221-223	CH-0991	id	D-3	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L221-223	CH-0991	id	WP-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L226-228	CH-0992	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L231-233	CH-0993	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L236-240	CH-0994	id	M-3	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L236-240	CH-0994	id	WP-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L246-253	CH-0995	id	B-1	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L328-335	CH-0997	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L338-342	CH-0998	id	N-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L338-342	CH-0998	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L350-351	CH-0999	id	N-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L444-448	CH-1001	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L470-484	CH-1002	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L579-585	CH-1004	id	WP-2b	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L757-765	CH-1007	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L827-827	CH-1009	id	WP-2c	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L891-895	CH-1010	id	WP-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L950-955	CH-1011	id	WP-2b	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L967-972	CH-1012	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1010-1016	CH-1013	id	U-7	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1010-1016	CH-1013	id	WP-6d	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1039-1069	CH-1014	id	WP-2b	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1077-1085	CH-1015	id	WP-2c	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1109-1112	CH-1016	id	WP-2e	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1129-1135	CH-1017	id	D-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1139-1144	CH-1018	id	M-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1139-1144	CH-1018	id	WP-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1146-1152	CH-1019	id	M-3	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1183-1192	CH-1020	id	D-10	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1183-1192	CH-1020	id	D-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1209-1212	CH-1022	id	WP-2e	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1225-1230	CH-1023	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1232-1237	CH-1024	id	D-3	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1232-1237	CH-1024	id	M-3	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1301-1304	CH-1025	id	D-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1461-1465	CH-1026	id	U-7	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1461-1465	CH-1026	id	WP-6d	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1488-1501	CH-1027	id	WP-2b	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1543-1546	CH-1029	id	M-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1543-1546	CH-1029	id	WP-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1856-1858	CH-1033	id	WP-2e	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1862-1866	CH-1034	id	F-8	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L77-82	CH-1062	id	D-5	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L77-82	CH-1062	id	WP-6b	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L862-883	CH-1065	id	L-2	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L862-883	CH-1065	id	M-7	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L887-920	CH-1066	id	WP-4f	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L1068-1074	CH-1067	id	M-1	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L1068-1074	CH-1067	id	WP-4	x1
SUMMARY ch_blocks=42 ws_only=0 unpaired=0 removed_rows=50
(exit 0)

### mutation c29 candidate A (CH-1004, base L579: drop the bare-ID paren `(D-4)` of the section header; expected: checker green, REMOVED rows 50 -> 51) -> check_comment_provenance --base
$ python3 tools/check_comment_provenance.py --base 092e1a1 r2db-api/src/r2db_api/structured.py MitateDB-api/src/mitatedb_api/platform_declarations.py
comment provenance OK: 189 blocks checked
(exit 0)

### mutation c29 candidate A (CH-1004, base L579: drop the bare-ID paren `(D-4)` of the section header; expected: checker green, REMOVED rows 50 -> 51) -> cs9_removed_tokens
$ python3 $SP/cs9/tools/cs9_removed_tokens.py -C $WT
BASE 092e1a1 HEAD worktree
REMOVED	r2db-api/src/r2db_api/structured.py	L195-199	CH-0990	id	WP-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L221-223	CH-0991	id	D-3	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L221-223	CH-0991	id	WP-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L226-228	CH-0992	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L231-233	CH-0993	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L236-240	CH-0994	id	M-3	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L236-240	CH-0994	id	WP-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L246-253	CH-0995	id	B-1	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L328-335	CH-0997	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L338-342	CH-0998	id	N-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L338-342	CH-0998	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L350-351	CH-0999	id	N-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L444-448	CH-1001	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L470-484	CH-1002	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L579-585	CH-1004	id	D-4	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L579-585	CH-1004	id	WP-2b	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L757-765	CH-1007	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L827-827	CH-1009	id	WP-2c	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L891-895	CH-1010	id	WP-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L950-955	CH-1011	id	WP-2b	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L967-972	CH-1012	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1010-1016	CH-1013	id	U-7	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1010-1016	CH-1013	id	WP-6d	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1039-1069	CH-1014	id	WP-2b	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1077-1085	CH-1015	id	WP-2c	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1109-1112	CH-1016	id	WP-2e	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1129-1135	CH-1017	id	D-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1139-1144	CH-1018	id	M-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1139-1144	CH-1018	id	WP-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1146-1152	CH-1019	id	M-3	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1183-1192	CH-1020	id	D-10	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1183-1192	CH-1020	id	D-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1209-1212	CH-1022	id	WP-2e	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1225-1230	CH-1023	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1232-1237	CH-1024	id	D-3	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1232-1237	CH-1024	id	M-3	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1301-1304	CH-1025	id	D-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1461-1465	CH-1026	id	U-7	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1461-1465	CH-1026	id	WP-6d	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1488-1501	CH-1027	id	WP-2b	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1543-1546	CH-1029	id	M-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1543-1546	CH-1029	id	WP-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1856-1858	CH-1033	id	WP-2e	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1862-1866	CH-1034	id	F-8	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L77-82	CH-1062	id	D-5	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L77-82	CH-1062	id	WP-6b	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L862-883	CH-1065	id	L-2	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L862-883	CH-1065	id	M-7	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L887-920	CH-1066	id	WP-4f	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L1068-1074	CH-1067	id	M-1	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L1068-1074	CH-1067	id	WP-4	x1
SUMMARY ch_blocks=42 ws_only=0 unpaired=0 removed_rows=51
(exit 0)

### mutation c29 candidate B (CH-1019, base L1146: drop `, D-3 (2)` from a content paren; expected: checker green, REMOVED rows 50 -> 51) -> check_comment_provenance --base
$ python3 tools/check_comment_provenance.py --base 092e1a1 r2db-api/src/r2db_api/structured.py MitateDB-api/src/mitatedb_api/platform_declarations.py
comment provenance OK: 189 blocks checked
(exit 0)

### mutation c29 candidate B (CH-1019, base L1146: drop `, D-3 (2)` from a content paren; expected: checker green, REMOVED rows 50 -> 51) -> cs9_removed_tokens
$ python3 $SP/cs9/tools/cs9_removed_tokens.py -C $WT
BASE 092e1a1 HEAD worktree
REMOVED	r2db-api/src/r2db_api/structured.py	L195-199	CH-0990	id	WP-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L221-223	CH-0991	id	D-3	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L221-223	CH-0991	id	WP-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L226-228	CH-0992	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L231-233	CH-0993	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L236-240	CH-0994	id	M-3	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L236-240	CH-0994	id	WP-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L246-253	CH-0995	id	B-1	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L328-335	CH-0997	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L338-342	CH-0998	id	N-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L338-342	CH-0998	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L350-351	CH-0999	id	N-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L444-448	CH-1001	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L470-484	CH-1002	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L579-585	CH-1004	id	WP-2b	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L757-765	CH-1007	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L827-827	CH-1009	id	WP-2c	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L891-895	CH-1010	id	WP-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L950-955	CH-1011	id	WP-2b	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L967-972	CH-1012	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1010-1016	CH-1013	id	U-7	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1010-1016	CH-1013	id	WP-6d	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1039-1069	CH-1014	id	WP-2b	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1077-1085	CH-1015	id	WP-2c	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1109-1112	CH-1016	id	WP-2e	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1129-1135	CH-1017	id	D-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1139-1144	CH-1018	id	M-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1139-1144	CH-1018	id	WP-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1146-1152	CH-1019	id	D-3	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1146-1152	CH-1019	id	M-3	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1183-1192	CH-1020	id	D-10	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1183-1192	CH-1020	id	D-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1209-1212	CH-1022	id	WP-2e	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1225-1230	CH-1023	id	WP-2a	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1232-1237	CH-1024	id	D-3	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1232-1237	CH-1024	id	M-3	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1301-1304	CH-1025	id	D-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1461-1465	CH-1026	id	U-7	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1461-1465	CH-1026	id	WP-6d	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1488-1501	CH-1027	id	WP-2b	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1543-1546	CH-1029	id	M-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1543-1546	CH-1029	id	WP-2	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1856-1858	CH-1033	id	WP-2e	x1
REMOVED	r2db-api/src/r2db_api/structured.py	L1862-1866	CH-1034	id	F-8	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L77-82	CH-1062	id	D-5	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L77-82	CH-1062	id	WP-6b	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L862-883	CH-1065	id	L-2	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L862-883	CH-1065	id	M-7	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L887-920	CH-1066	id	WP-4f	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L1068-1074	CH-1067	id	M-1	x1
REMOVED	MitateDB-api/src/mitatedb_api/platform_declarations.py	L1068-1074	CH-1067	id	WP-4	x1
SUMMARY ch_blocks=42 ws_only=0 unpaired=0 removed_rows=51
(exit 0)

### mutation c19a (condition 19 (a): an existing correction record's `old` text (CH-0552, structured.md) is changed to a sentence the basis does not hold) -> check_comment_provenance --base
$ python3 tools/check_comment_provenance.py --base 092e1a1 r2db-api/src/r2db_api/structured.py MitateDB-api/src/mitatedb_api/platform_declarations.py
FAIL (§9.3 (2)) r2db-api/src/r2db_api/structured.py:1640 CH-0552: basis correction #1 (2026-10-03) does not match the working-tree entry at the same position verbatim (edited, deleted, or reordered)
(exit 1)

### mutation c23 (condition 23: a ledger-less 3-digit R number appended inside a fenced block of structured.md) -> check_doc_refs
$ python3 tools/check_doc_refs.py
SI: definitions=16 references=2282
C: definitions=37 references=4200
CCR: definitions=15 references=255
G: definitions=4 references=221
P: definitions=9 references=464
R: definitions=122 references=5127
L: definitions=145 references=1700
external references (reported only, no definition required):
  DM-0018: docs/design/DEVELOPMENT_PROCESS_HYGIENE_V1.md:80, docs/design/DEVELOPMENT_PROCESS_HYGIENE_V1.md:235, docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md:5, docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md:27, docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md:114, docs/work-orders/WORK_ORDER_DEVELOPMENT_PROCESS_HYGIENE_V1.md:120
  DM-0021: docs/design/ROADMAP_POST_PHASE7_V1.md:273, docs/design/ROADMAP_POST_PHASE7_V1.md:283
  DM-0025: docs/design/PHASE11_MIN_COMMON_PROFILE_V1.md:149, docs/design/PHASE11_MIN_COMMON_PROFILE_V1.md:1014, docs/design/ROADMAP_POST_PHASE7_V1.md:475
  DM-0052: docs/design/MITATEDB_PLATFORM_READONLY_INVENTORY_V0_1.md:6, docs/work-orders/WORK_ORDER_MITATEDB_OPERATION_DEPTH_PLATFORM_UPGRADE_V1.md:6
docs/code-history/r2db-api/structured.md:19: R-<3 桁、本書には書かない> has no definition in docs/design/ROADMAP_POST_PHASE7_V1.md
tracked markdown files scanned: 281
empty markdown files: 0
check_doc_refs FAILED: 1 dangling reference(s)
(exit 1)

### restore check 1: all match the base sha256
### restore check 2: all match the base sha256
### git status after restore
$ git status --short -- r2db-api/src/r2db_api/structured.py MitateDB-api/src/mitatedb_api/platform_declarations.py docs/code-history/r2db-api/structured.md docs/code-history/MitateDB-api/platform_declarations.md security/CONTROL_MAPPING.md

(exit 0)
```

## 実行 5 (Y9-3 の実測。最終の spec を当てた上で、見送った F-5 のラベル除去を 1 件足して検査器に当てた。元に戻した)

```text
### apply structured
$ python3 $SP/cs9/tools/cs9_apply.py -C $WT --spec $SP/cs9/cs9-spec-structured.json
CH-1034 comment base L1862-1866 ApplicationCell._apply_schema_locked edits=1
CH-1033 comment base L1856-1858 ApplicationCell._apply_schema_locked edits=1
CH-1029 comment base L1543-1546 ApplicationCell._apply_schema_locked edits=1
CH-1027 docstring base L1488-1501 ApplicationCell._apply_schema_locked edits=2
CH-1026 docstring base L1461-1465 ApplicationCell.apply_schema edits=1
CH-1025 comment base L1301-1304 ApplicationCell._apply edits=1
CH-1024 comment base L1232-1237 ApplicationCell._apply edits=1
CH-1023 comment base L1225-1230 ApplicationCell._apply edits=1
CH-1022 comment base L1209-1212 ApplicationCell._transact_locked edits=1
CH-1020 comment base L1183-1192 ApplicationCell._transact_locked edits=1
CH-1019 comment base L1146-1152 ApplicationCell._transact_locked edits=1
CH-1018 comment base L1139-1144 ApplicationCell._transact_locked edits=1
CH-1017 comment base L1129-1135 ApplicationCell._transact_locked edits=1
CH-1016 comment base L1109-1112 ApplicationCell._transact_locked edits=1
CH-1015 comment base L1077-1085 ApplicationCell._transact_locked edits=1
CH-1014 docstring base L1039-1069 ApplicationCell._transact_locked edits=1
CH-1013 docstring base L1010-1016 ApplicationCell.transact edits=1
CH-1012 comment base L967-972 ApplicationCell._describe_entity edits=1
CH-1011 docstring base L950-955 ApplicationCell._describe_entity edits=1
CH-1010 comment base L891-895 ApplicationCell.query edits=1
CH-1009 comment base L827-827 ApplicationCell edits=1
CH-1007 comment base L757-765 ApplicationCell edits=1
CH-1004 comment base L579-585 <module> edits=1
CH-1003 comment base L514-514 bind_schema_operation edits=1
CH-1002 comment base L470-484 bind_schema_operation edits=1
CH-1001 comment base L444-448 bind_schema_operation edits=1
CH-0999 comment base L350-351 bind_schema_operation edits=1
CH-0998 comment base L338-342 bind_schema_operation edits=1
CH-0997 comment base L328-335 bind_schema_operation edits=1
CH-0996 comment base L309-319 bind_schema_operation edits=1
CH-0995 comment base L246-253 bind_schema_operation edits=1
CH-0994 comment base L236-240 bind_schema_operation edits=1
CH-0993 comment base L231-233 bind_schema_operation edits=1
CH-0992 comment base L226-228 bind_schema_operation edits=1
CH-0991 comment base L221-223 bind_schema_operation edits=1
CH-0990 comment base L195-199 bind_schema_operation edits=1
blocks=36 module_lines 1867 -> 1906
(exit 0)

### apply platform_declarations
$ python3 $SP/cs9/tools/cs9_apply.py -C $WT --spec $SP/cs9/cs9-spec-platform_declarations.json
CH-1067 comment base L1068-1074 check_role_connection_limits edits=1
CH-1066 comment base L887-920 <module> edits=1
CH-1065 comment base L862-883 <module> edits=1
CH-1064 docstring base L656-663 _role_setting_rows edits=1
CH-1062 comment base L77-82 <module> edits=1
CH-1060 docstring base L1-47 <module> edits=1
blocks=6 module_lines 1713 -> 1720
(exit 0)

### Y9-3 trial: old occurs 1 time(s)
### Y9-3 trial: 2nd-paragraph label `Review round F-5 (`{scratchpad}/rulings-r4.md`): ` removed (CH-1014) -> does the checker accept it?
$ python3 tools/check_comment_provenance.py --base 092e1a1 r2db-api/src/r2db_api/structured.py MitateDB-api/src/mitatedb_api/platform_declarations.py
comment provenance OK: 189 blocks checked
(exit 0)

### Y9-3 trial 2 (L1573-1580, CH-less): old occurs 1 time(s) -- a CH-less block cannot be edited without a CH-ID, so only the label form is noted; not applied
### restore check 1: all match the base sha256
### restore check 2: all match the base sha256
### git status after restore (whole tree)
$ git status --short
?? cloud-out/
(exit 0)
```
