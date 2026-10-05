# 変更セット 9 実測 (A) — r2db `structured.py`、MitateDB `platform_declarations.py`

- 基点: `092e1a1` (このセッションの checkout で `git fetch origin main` の後の `origin/main`。着手時の stale な `origin/main` は `4241b55` だったが fetch で `092e1a1` に進み、HEAD と同一。作業機の local main はこれより先に進んでいる可能性がある)。
- 数え方: 作業指示書 §16.2 (= §13.2・§14.2) と同じ。塊 = `tools/check_comment_provenance.py` の `extract_all_blocks`、経緯トークン = `_HISTORY_TOKEN_PATTERNS` の `findall` の合計 (§2.3 末尾)、文 = `split_sentences(_flatten(kind, dedented))`、目印 = 設計 §3 の叙述の目印 (英語は語境界付き・大文字小文字を区別しない、日本語は語境界なし)、安全の語 / 保護参照 / 位置の語 = §14.2 の正規表現と母集団 (経緯トークンを含む文)、塊をまたぐ参照の語 = §13.2 の正規表現に `'s identical comment`・`<名前> below|above`・`own (comment|docstring|paragraph)`・`identical-purpose comment` を足した。10 行以上の塊 = 行数 ≥ 10 で CH-ID の無い塊 (設計 §10.3 の数え方)。
- 登録 helper の表は **ast で読んだ** (両 peer の `tests/test_audit_query.py` の `_ISOMORPHIC_TARGETS`、`ast.AnnAssign` の値を `ast.literal_eval`)。対象外にするのは symbol の node (def / class / 代入文) の中に開始行を持つ塊だけ。代入だけの symbol も数に入れ、「中に塊を持つ node」と分けて書いた。
- 計測 script: `cloud-out/cs9/tools/cs9_measure.py` (→ `measure.json`)、`cs9_xref_grep.py` (外部からの参照)、`cs9_posrefs.py` (位置参照)。すべて基点の blob (`git show`) に当てた。

## 1. 塊

| 項目 | r2db `structured.py` | MitateDB `platform_declarations.py` | 計 |
|---|---|---|---|
| 行数 | 1867 | 1713 | 3580 |
| 塊 (`extract_all_blocks`) | 122 (docstring 17 / comment 105) | 67 (docstring 38 / comment 29) | 189 (`--base` の `189 blocks checked` と一致) |
| 対象外: 既存の CH-ID の塊 | 13 (CH-0552 L1603-1613、CH-0553 L1618-1622、CH-0554 L1626-1628、CH-0555 L1646-1649、CH-0556 L1651-1655、CH-0557 L1662-1667、CH-0558 L1670-1678、CH-0559 L1690-1694、CH-0560 L1702-1708、CH-0561 L1722-1744、CH-0562 L1778-1781、CH-0563 L1789-1793、CH-0564 L1831-1840) | 1 (CH-0550 L1011-1064) | 14 |
| 登録 helper の symbol (`_ISOMORPHIC_TARGETS` のこの module の行) | 6 (両 peer の表で同数) | 60 (両 peer の表で同数) | — |
| うち中に塊を持つ node / 対象外の塊 | 6 node / 6 塊 (すべて docstring) | 34 node / 35 塊 (docstring 34、comment 1 = L503-509 `read_platform_declarations` の中) | 41 |
| **対象の塊** | **103** (docstring 11 / comment 92、653 行) | **31** (docstring 3 / comment 28、319 行) | **134** |
| 経緯トークン (module 全文) / うち対象の塊の中 | 112 / 94 | 42 / 24 | 154 / 118 |
| 経緯トークンを含む対象の塊 (行数) | 60 (457 行) | 9 (175 行) | 69 |
| 日付を含む行 (module 全文 / 対象の塊) | 3 / 3 (L310、L584、L641) | 15 / 8 (L23、L44、L72、L529、L661、L888、L917、L1068。登録 helper の中に L241・L266・L559・L570・L680・L971・L1043、既存 CH-0550 に L1043) | — |
| `#:` の行 | 0 | 103 (対象の塊: L60-65、L69-73、L77-82、L86-88、L91-94、L97-98、L101-104、L108-114、L121-125、L128-129、L132-136、L856-859、L862-883、L922-928、L931-938、L941-945、L998-1001、L1525-1528) | — |
| 目印一覧に当たる文 / 塊 (対象の塊だけ) | 17 / 17 | 8 / 6 | 25 / 23 |
| 塊をまたぐ参照の語を含む文 (対象の塊) | 63 | 12 | — |
| 経緯トークンを含む文のうち 安全 / 保護参照 / 位置 | 17 / 37 / 34 文 (安全の塊 17) | 5 / 6 / 3 文 (安全の塊 4) | — |
| 10 行以上の塊 (CH なし、対象の塊) | 18 塊 / 253 行 (登録 helper を含む全塊で 23) | 6 塊 / 189 行 (登録 helper を含む全塊で 19) | — |
| 作業ノートの参照 (`{scratchpad}/…`・`scratchpad/…`) の行: 対象の塊の中 / 登録 helper の中 | L359、L728、L788、L906、L1048、L1063、L1277、L1492 / L610-631 (`compute_plan_token`) | L24、L760、L761、L871 / L266-271 (`_f3c_message`)、L441-460 (`validate_process_ceilings_value`、`scratchpad/phase10/wp6-rulings.md`)、L803-823 (`check_contract_170_declarations`) | — |

- `--register` (基点、無変更): `comment provenance register OK: 95 files scanned, 515 CH-IDs`。`--base 092e1a1` (無変更、2 module): `comment provenance OK: 189 blocks checked` (exit 0)。`check_doc_refs.py`: `check_doc_refs OK: 0 dangling references`。
- 受け皿は既存の `docs/code-history/r2db-api/structured.md` (基点で 13 節 + 訂正 4 件) と `docs/code-history/MitateDB-api/platform_declarations.md` (1 節 + 訂正 1 件) に追記する。
- CH-ID の範囲 `CH-0990`〜`CH-1059` / `CH-1060`〜`CH-1129` は `src/`・`docs/code-history/` に 0 件 (最大は CH-0775)。作業指示書の本文に変異の番号として `CH-0997`・`CH-0999` が書かれているが、受け皿・`src/` には無い (註: 手本の変異 c6b の孤児の節 `CH-0997` は r2db の範囲の中なので、変更セット 9 では範囲外の番号 (例 `CH-1997`) を使う)。

**登録 helper (ast で読んだ)**

r2db `structured.py` (`_ISOMORPHIC_TARGETS` の r2db 側パスが `src/r2db_api/structured.py` の行。相手は MitateDB `field_types.py` 2 と `cell.py` 4):

| symbol | node | 行 | 中の塊 |
|---|---|---|---|
| `enum_member_matches_type` | FunctionDef | L113-132 | 1 (L114-123 docstring) |
| `validate_enum_declaration` | FunctionDef | L135-175 | 1 (L136-163 docstring) |
| `normalize_request_for_plan` | FunctionDef | L588-606 | 1 (L589-604 docstring) |
| `compute_plan_token` | FunctionDef | L609-633 | 1 (L610-631 docstring) |
| `normalize_request_for_idempotency` | FunctionDef | L646-663 | 1 (L647-661 docstring) |
| `idempotency_digest` | FunctionDef | L694-703 | 1 (L695-702 docstring) |

MitateDB `platform_declarations.py` (両 peer の `platform_declarations.py` が相手の行、60 symbol。代入だけの symbol 5 (`VISIBILITY_LAG_CLOCK_SKEW_MARGIN_MS`、`_API_ROLE_STORE_COUNT`、`_CONTROLPLANE_ROLE_POOL_FLOOR`、`_AUDITREADER_ROLE_POOL_FLOOR`、`_ROLE_CLASSES`) は中に塊を持たない。各代入の直前の `#:` 塊は node の外なので対象):

| symbol | node | 行 | 中の塊 |
|---|---|---|---|
| `VISIBILITY_LAG_CLOCK_SKEW_MARGIN_MS` | Assign | L130-130 | 0  |
| `PlatformDeclarationError` | ClassDef | L140-156 | 1 (L141-152 docstring) |
| `Surfaces` | ClassDef | L159-163 | 1 (L161-161 docstring) |
| `ProcessCeilings` | ClassDef | L166-176 | 1 (L168-174 docstring) |
| `PlatformDeclarations` | ClassDef | L179-186 | 1 (L181-182 docstring) |
| `RoleTimeoutCatalog` | ClassDef | L189-196 | 1 (L191-193 docstring) |
| `_f1_message` | FunctionDef | L205-214 | 0  |
| `_f2_message` | FunctionDef | L217-224 | 0  |
| `reject_removed_timeout_env` | FunctionDef | L227-235 | 1 (L228-232 docstring) |
| `reject_removed_surface_env` | FunctionDef | L238-246 | 1 (L239-243 docstring) |
| `_f3_message` | FunctionDef | L257-262 | 0  |
| `_f3c_message` | FunctionDef | L265-277 | 1 (L266-271 docstring) |
| `_f4_message` | FunctionDef | L280-285 | 0  |
| `_f4b_window_message` | FunctionDef | L288-295 | 0  |
| `_f4b_writer_roles_message` | FunctionDef | L298-305 | 0  |
| `_f5_message` | FunctionDef | L308-313 | 0  |
| `_f8_message` | FunctionDef | L316-321 | 0  |
| `validate_coalescing_window_value` | FunctionDef | L324-330 | 1 (L325-327 docstring) |
| `validate_audit_writer_roles_value` | FunctionDef | L333-357 | 1 (L334-347 docstring) |
| `validate_surfaces_value` | FunctionDef | L392-407 | 1 (L393-395 docstring) |
| `_f15_shape_message` | FunctionDef | L419-427 | 0  |
| `_f15_value_message` | FunctionDef | L430-437 | 0  |
| `validate_process_ceilings_value` | FunctionDef | L440-471 | 1 (L441-460 docstring) |
| `read_platform_declarations` | FunctionDef | L474-522 | 2 (L475-487 docstring、L503-509 comment) |
| `_f6_forward_message` | FunctionDef | L533-542 | 0  |
| `_f6_reverse_message` | FunctionDef | L545-553 | 0  |
| `check_control_surface_consistency` | FunctionDef | L556-566 | 1 (L557-561 docstring) |
| `require_control_surface_declared` | FunctionDef | L569-576 | 1 (L570-574 docstring) |
| `_f7_message` | FunctionDef | L589-597 | 0  |
| `_f9_message` | FunctionDef | L600-610 | 0  |
| `_f10_message` | FunctionDef | L613-620 | 0  |
| `_f11_message` | FunctionDef | L623-630 | 0  |
| `_f13_message` | FunctionDef | L633-646 | 0  |
| `read_declared_role_timeouts` | FunctionDef | L674-705 | 1 (L675-681 docstring) |
| `read_effective_timeouts_ms` | FunctionDef | L708-716 | 1 (L709-712 docstring) |
| `derive_visibility_lag_ms` | FunctionDef | L719-726 | 1 (L720-725 docstring) |
| `check_writer_role_timeouts` | FunctionDef | L729-755 | 1 (L732-745 docstring) |
| `check_contract_170_declarations` | FunctionDef | L798-853 | 1 (L803-823 docstring) |
| `_API_ROLE_STORE_COUNT` | Assign | L929-929 | 0  |
| `_CONTROLPLANE_ROLE_POOL_FLOOR` | Assign | L939-939 | 0  |
| `_AUDITREADER_ROLE_POOL_FLOOR` | Assign | L946-946 | 0  |
| `_roles_with_table_privilege` | FunctionDef | L949-960 | 1 (L950-953 docstring) |
| `_table_owner` | FunctionDef | L963-984 | 1 (L964-980 docstring) |
| `_f16_message` | FunctionDef | L987-995 | 0  |
| `_ROLE_CLASSES` | Assign | L1002-1002 | 0  |
| `_f17_message` | FunctionDef | L1129-1142 | 0  |
| `check_auditreader_statement_timeout` | FunctionDef | L1145-1198 | 1 (L1146-1171 docstring) |
| `headroom_lower_bound` | FunctionDef | L1239-1264 | 1 (L1248-1262 docstring) |
| `_count_registered_applications` | FunctionDef | L1267-1277 | 1 (L1268-1273 docstring) |
| `_read_connection_headroom_settings` | FunctionDef | L1283-1309 | 1 (L1284-1291 docstring) |
| `HeadroomReport` | ClassDef | L1312-1322 | 1 (L1314-1317 docstring) |
| `_f18_message` | FunctionDef | L1325-1345 | 1 (L1334-1338 docstring) |
| `check_max_connections_headroom` | FunctionDef | L1348-1406 | 1 (L1352-1369 docstring) |
| `_f19_message` | FunctionDef | L1409-1434 | 0  |
| `check_application_collations` | FunctionDef | L1437-1490 | 1 (L1438-1461 docstring) |
| `check_request_rate_function` | FunctionDef | L1493-1522 | 1 (L1494-1503 docstring) |
| `_f21_message` | FunctionDef | L1536-1542 | 0  |
| `_f21_acl_holders` | FunctionDef | L1545-1559 | 1 (L1546-1550 docstring) |
| `check_denial_window_function` | FunctionDef | L1562-1662 | 1 (L1563-1584 docstring) |
| `ops_module_hint` | FunctionDef | L1665-1671 | 1 (L1666-1670 docstring) |

**10 行以上の塊 (対象の塊、CH なし)**

- `structured.py`: L81-110、L202-212、L309-319、L359-375、L470-484、L667-681、L708-719、L728-742、L768-777、L788-798、L906-915、L1039-1069、L1183-1192、L1195-1205、L1277-1286、L1488-1501、L1505-1514、L1803-1812
- `platform_declarations.py`: L1-47、L361-370、L758-797、L862-883、L887-920、L1201-1236

**目印一覧に当たる文を持つ塊** (文ごとの目印は判定表 B)

- `structured.py` (17 文 / 17 塊): L195-199、L202-212、L338-342、L350-351、L359-375、L378-383、L397-402、L458-462、L470-484、L488-496、L514-514、L636-643、L788-798、L1039-1069、L1146-1152、L1232-1237、L1820-1827
- `platform_declarations.py` (8 文 / 6 塊): L1-47、L69-73、L108-114、L525-530、L862-883、L887-920

**経緯トークンと安全上の語が同じ文にある塊** (文は消さない。判定表 C に展開)

- `structured.py` (17 塊): L81-110 (commit)、L187-192 (identifier)、L195-199 (locking)、L359-375 (SI-10、identifier)、L636-643 (commit)、L788-798 (Lock、transaction)、L876-881 (identifier)、L1010-1016 (lock)、L1039-1069 (commit、rollback)、L1159-1165 (commit、rollback)、L1183-1192 (commit、commit_failed)、L1195-1205 (commit、transaction)、L1301-1304 (fail-closed)、L1461-1465 (lock)、L1543-1546 (SI-08)、L1803-1812 (commit、rollback)、L1848-1852 (commit、committed)
- `platform_declarations.py` (4 塊): L69-73 (role、timeout)、L525-530 (role)、L887-920 (role)、L1068-1074 (role)

## 2. 塊をまたぐ参照先

判定表の「塊をまたぐ参照先一覧」に全件を置いた (module の中、両 peer の `src/`・`tests/`・`conformance/`、`conformance-tests/`、`security/`)。要点:

- `structured.py` の中: `field_type`'s own precedent / rule above (L195→L202、L221・L231・L236→L202)、`_idempotency_lock`'s own field comment (L1010・L1461→L788)、`transact`'s identical wrapper / comment (L1461→L1010、L1848→L1195、L1856→L1209)、`transact` above (L1488→L1039)、module docstring's own documented divergence (L906・L1277→L1: **無い**。module docstring は 1 行で divergence の記述を持たない。移動前からの穴)。
- 外から: r2db `postgres.py:1765` (→ L1129-1135)、`:1783` (→ L1077-1085)、`:2273` (→ L1505-1514)、`tests/test_dry_run_and_plan.py:332` (→ L1039-1069 第 2 段落の "A plain apply pays no …")、`tests/test_audit_query.py:1515-1518` (→ L1461-1465)、MitateDB `tests/test_denial_details_and_request_id.py:206` (→ `_apply` のコード)、`conformance-tests/test_c20…:154`・`test_c22…:186` (位置参照 `structured.py:1821` → L1820-1827 のコメント行)。
- `platform_declarations.py` の中: this module's own docstring / header (L60-65・L887-920・L941-945→L1-47)、see the module header above (L1068-1074→L887-920)、F-16 above (L1201-1236→L887-920)。
- 登録 helper の中から対象の塊を指す文: `structured.py` 0 件 (6 helper の参照は helper 同士か module の外)。`platform_declarations.py`: `_table_owner` (L964-980) が M-1 の裁定 (L1068-1074 のラベルが名指す) を自ら持つ、`check_contract_170_declarations` (L803-823) が L758-797 の周辺を指す、`check_control_surface_consistency` (L557-561) が L525-530 の見出し (F-3c) を指す。helper 側の文は対象の塊の除去で指す先を失わない。
- `cs9_xref_grep.py` の生の出力 (両 module、フィルタ前): `cloud-out/cs9/tools/xref-external.txt`。

## 3. 位置参照 (`ファイル名:行`。続きの形 `` `:N` `` を含む)

`cs9_posrefs.py` の出力 (基点。全件、パス付き / basename だけ / 続きの形、指す行がコメント・docstring の行か):

```text
== r2db-api/src/r2db_api/structured.py (1867 lines)
MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py:809: 'structured.py:1508' form=basename peer=ambiguous this_module=False cited_line_in_block=None in_range=True
conformance-tests/test_c20_constraint_declaration_agreement.py:154: 'r2db-api/src/r2db_api/structured.py:1821' form=path peer=r2db-api this_module=True cited_line_in_block=comment L1820-1827 in_range=True
conformance-tests/test_c22_dry_run_and_plan.py:186: 'r2db-api/src/r2db_api/structured.py:1821' form=path peer=r2db-api this_module=True cited_line_in_block=comment L1820-1827 in_range=True
r2db-api/conformance/conformance_adapter_r2db.py:319: 'structured.py:2269' form=basename peer=ambiguous this_module=False cited_line_in_block=None in_range=False
r2db-api/conformance/conformance_adapter_r2db.py:319: '`:2294' form=continuation peer=ambiguous this_module=False cited_line_in_block=None in_range=False
r2db-api/conformance/conformance_adapter_r2db.py:319: '`:2697' form=continuation peer=ambiguous this_module=False cited_line_in_block=None in_range=False
r2db-api/conformance/conformance_adapter_r2db.py:319: '`:2718' form=continuation peer=ambiguous this_module=False cited_line_in_block=None in_range=False
r2db-api/conformance/conformance_adapter_r2db.py:1031: 'structured.py:2269' form=basename peer=ambiguous this_module=False cited_line_in_block=None in_range=False
r2db-api/conformance/conformance_adapter_r2db.py:1031: '`:2294' form=continuation peer=ambiguous this_module=False cited_line_in_block=None in_range=False
r2db-api/conformance/conformance_adapter_r2db.py:1031: '`:2697' form=continuation peer=ambiguous this_module=False cited_line_in_block=None in_range=False
r2db-api/conformance/conformance_adapter_r2db.py:1031: '`:2718' form=continuation peer=ambiguous this_module=False cited_line_in_block=None in_range=False
r2db-api/conformance/conformance_adapter_r2db.py:1286: 'structured.py:1183' form=basename peer=ambiguous this_module=False cited_line_in_block=None in_range=True
r2db-api/tests/test_foundation.py:617: 'structured.py:229' form=basename peer=ambiguous this_module=False cited_line_in_block=None in_range=True
r2db-api/tests/test_foundation.py:886: 'structured.py:212' form=basename peer=ambiguous this_module=False cited_line_in_block=None in_range=True
r2db-api/tests/test_foundation.py:1280: 'structured.py:702' form=basename peer=ambiguous this_module=False cited_line_in_block=None in_range=True
r2db-api/tests/test_l1_details_vocabulary_ast_scan.py:738: 'structured.py:1508' form=basename peer=ambiguous this_module=False cited_line_in_block=None in_range=True
security/CONTROL_MAPPING.md:371: 'r2db-api/src/r2db_api/structured.py:178-179' form=path peer=r2db-api this_module=True cited_line_in_block=None in_range=True
security/CONTROL_MAPPING.md:372: 'r2db-api/src/r2db_api/structured.py:884' form=path peer=r2db-api this_module=True cited_line_in_block=None in_range=True
security/CONTROL_MAPPING.md:686: 'r2db-api/src/r2db_api/structured.py:1145' form=path peer=r2db-api this_module=True cited_line_in_block=None in_range=True
security/CONTROL_MAPPING.md:686: '`:1599' form=continuation peer=r2db-api this_module=True cited_line_in_block=None in_range=True
security/CONTROL_MAPPING.md:1244: 'r2db-api/src/r2db_api/structured.py:1796' form=path peer=r2db-api this_module=True cited_line_in_block=None in_range=True
security/CONTROL_MAPPING.md:1245: 'r2db-api/src/r2db_api/structured.py:568' form=path peer=r2db-api this_module=True cited_line_in_block=None in_range=True
security/CONTROL_MAPPING.md:1246: 'r2db-api/src/r2db_api/structured.py:1807' form=path peer=r2db-api this_module=True cited_line_in_block=comment L1803-1812 in_range=True
security/CONTROL_MAPPING.md:1247: 'r2db-api/src/r2db_api/structured.py:22' form=path peer=r2db-api this_module=True cited_line_in_block=None in_range=True
security/CONTROL_MAPPING.md:1248: 'r2db-api/src/r2db_api/structured.py:1784' form=path peer=r2db-api this_module=True cited_line_in_block=None in_range=True
security/CONTROL_MAPPING.md:1604: 'r2db-api/src/r2db_api/structured.py:995' form=path peer=r2db-api this_module=True cited_line_in_block=None in_range=True
-- total 26; this module 12; into comment/docstring lines 3; basename-only 8; continuation 7
== MitateDB-api/src/mitatedb_api/platform_declarations.py (1713 lines)
security/CONTROL_MAPPING.md:700: 'r2db-api/src/r2db_api/platform_declarations.py:1168' form=path peer=r2db-api this_module=False cited_line_in_block=None in_range=True
security/CONTROL_MAPPING.md:701: 'r2db-api/src/r2db_api/platform_declarations.py:1152' form=path peer=r2db-api this_module=False cited_line_in_block=None in_range=True
security/CONTROL_MAPPING.md:766: 'r2db-api/src/r2db_api/platform_declarations.py:499' form=path peer=r2db-api this_module=False cited_line_in_block=None in_range=True
security/CONTROL_MAPPING.md:773: 'r2db-api/src/r2db_api/platform_declarations.py:465' form=path peer=r2db-api this_module=False cited_line_in_block=None in_range=True
security/CONTROL_MAPPING.md:781: 'r2db-api/src/r2db_api/platform_declarations.py:1031' form=path peer=r2db-api this_module=False cited_line_in_block=None in_range=True
security/CONTROL_MAPPING.md:782: 'r2db-api/src/r2db_api/platform_declarations.py:1031' form=path peer=r2db-api this_module=False cited_line_in_block=None in_range=True
security/CONTROL_MAPPING.md:783: 'r2db-api/src/r2db_api/platform_declarations.py:1031' form=path peer=r2db-api this_module=False cited_line_in_block=None in_range=True
security/CONTROL_MAPPING.md:784: 'r2db-api/src/r2db_api/platform_declarations.py:1108' form=path peer=r2db-api this_module=False cited_line_in_block=None in_range=True
security/CONTROL_MAPPING.md:785: 'r2db-api/src/r2db_api/platform_declarations.py:1260' form=path peer=r2db-api this_module=False cited_line_in_block=None in_range=True
security/CONTROL_MAPPING.md:785: '`:1369' form=continuation peer=r2db-api this_module=False cited_line_in_block=None in_range=True
security/CONTROL_MAPPING.md:785: '`:1346' form=continuation peer=r2db-api this_module=False cited_line_in_block=None in_range=True
security/CONTROL_MAPPING.md:786: 'r2db-api/src/r2db_api/platform_declarations.py:1260' form=path peer=r2db-api this_module=False cited_line_in_block=None in_range=True
security/CONTROL_MAPPING.md:787: 'r2db-api/src/r2db_api/platform_declarations.py:1260' form=path peer=r2db-api this_module=False cited_line_in_block=None in_range=True
security/CONTROL_MAPPING.md:788: 'r2db-api/src/r2db_api/platform_declarations.py:1260' form=path peer=r2db-api this_module=False cited_line_in_block=None in_range=True
security/CONTROL_MAPPING.md:790: 'r2db-api/src/r2db_api/platform_declarations.py:1515' form=path peer=r2db-api this_module=False cited_line_in_block=None in_range=True
security/CONTROL_MAPPING.md:902: 'MitateDB-api/src/mitatedb_api/platform_declarations.py:1145' form=path peer=MitateDB-api this_module=True cited_line_in_block=None in_range=True
security/CONTROL_MAPPING.md:903: 'MitateDB-api/src/mitatedb_api/platform_declarations.py:1145' form=path peer=MitateDB-api this_module=True cited_line_in_block=None in_range=True
security/CONTROL_MAPPING.md:1074: 'MitateDB-api/src/mitatedb_api/platform_declarations.py:474' form=path peer=MitateDB-api this_module=True cited_line_in_block=None in_range=True
security/CONTROL_MAPPING.md:1079: 'MitateDB-api/src/mitatedb_api/platform_declarations.py:440' form=path peer=MitateDB-api this_module=True cited_line_in_block=None in_range=True
security/CONTROL_MAPPING.md:1090: 'MitateDB-api/src/mitatedb_api/platform_declarations.py:1005' form=path peer=MitateDB-api this_module=True cited_line_in_block=None in_range=True
security/CONTROL_MAPPING.md:1091: 'MitateDB-api/src/mitatedb_api/platform_declarations.py:1239' form=path peer=MitateDB-api this_module=True cited_line_in_block=None in_range=True
security/CONTROL_MAPPING.md:1091: '`:1348' form=continuation peer=MitateDB-api this_module=True cited_line_in_block=None in_range=True
security/CONTROL_MAPPING.md:1091: '`:1325' form=continuation peer=MitateDB-api this_module=True cited_line_in_block=None in_range=True
security/CONTROL_MAPPING.md:1092: 'MitateDB-api/src/mitatedb_api/platform_declarations.py:1239' form=path peer=MitateDB-api this_module=True cited_line_in_block=None in_range=True
security/CONTROL_MAPPING.md:1095: 'MitateDB-api/src/mitatedb_api/platform_declarations.py:1239' form=path peer=MitateDB-api this_module=True cited_line_in_block=None in_range=True
security/CONTROL_MAPPING.md:1096: 'MitateDB-api/src/mitatedb_api/platform_declarations.py:1493' form=path peer=MitateDB-api this_module=True cited_line_in_block=None in_range=True
security/CONTROL_MAPPING.md:1101: 'MitateDB-api/src/mitatedb_api/platform_declarations.py:1005' form=path peer=MitateDB-api this_module=True cited_line_in_block=None in_range=True
security/CONTROL_MAPPING.md:1103: 'MitateDB-api/src/mitatedb_api/platform_declarations.py:1239' form=path peer=MitateDB-api this_module=True cited_line_in_block=None in_range=True
security/CONTROL_MAPPING.md:1872: 'r2db-api/src/r2db_api/platform_declarations.py:1584' form=path peer=r2db-api this_module=False cited_line_in_block=None in_range=True
security/CONTROL_MAPPING.md:1874: 'r2db-api/src/r2db_api/platform_declarations.py:1584' form=path peer=r2db-api this_module=False cited_line_in_block=None in_range=True
security/CONTROL_MAPPING.md:1960: 'r2db-api/src/r2db_api/platform_declarations.py:748' form=path peer=r2db-api this_module=False cited_line_in_block=None in_range=True
security/CONTROL_MAPPING.md:1961: 'r2db-api/src/r2db_api/platform_declarations.py:748' form=path peer=r2db-api this_module=False cited_line_in_block=None in_range=True
security/CONTROL_MAPPING.md:1962: 'r2db-api/src/r2db_api/platform_declarations.py:748' form=path peer=r2db-api this_module=False cited_line_in_block=None in_range=True
security/CONTROL_MAPPING.md:1963: 'r2db-api/src/r2db_api/platform_declarations.py:748' form=path peer=r2db-api this_module=False cited_line_in_block=None in_range=True
security/CONTROL_MAPPING.md:1964: 'r2db-api/src/r2db_api/platform_declarations.py:748' form=path peer=r2db-api this_module=False cited_line_in_block=None in_range=True
security/CONTROL_MAPPING.md:2004: 'MitateDB-api/src/mitatedb_api/platform_declarations.py:1562' form=path peer=MitateDB-api this_module=True cited_line_in_block=None in_range=True
security/CONTROL_MAPPING.md:2016: 'MitateDB-api/src/mitatedb_api/platform_declarations.py:719' form=path peer=MitateDB-api this_module=True cited_line_in_block=None in_range=True
-- total 37; this module 15; into comment/docstring lines 0; basename-only 0; continuation 4
```

- `security/CONTROL_MAPPING.md` → `structured.py`: 12 件 (パス付き 11 + 続きの形 `` `:1599` `` 1、行 371・372・686・1244〜1248・1604)。**指す行がコメント・docstring の行であるもの**: 1 件 — `:1246` の `structured.py:1807` (L1803-1812 の comment 塊。(iv) によりこの塊は基準のまま)。ほかは code の行。`repull.py --dry-run` は 10 件を引き直し (`unresolved 0`、checks.md)。
- `security/CONTROL_MAPPING.md` → MitateDB `platform_declarations.py`: 15 件 (パス付き 13 + 続きの形 `` `:1348` ``・`` `:1325` `` 2、行 902・903・1074・1079・1090〜1092・1095・1096・1101・1103・2004・2016)。コメント・docstring の行を指すものは 0。r2db の同名ファイルへの参照 22 件 (行 700・701・766・773・781〜790・1872・1874・1960〜1964) はすべてパス付きで、`repull.py` は 1 件も書き換えない (checks.md の guard 0)。basename だけの形は 0。
- `conformance-tests/` → `structured.py`: `test_c20_constraint_declaration_agreement.py:154`、`test_c22_dry_run_and_plan.py:186` (パス付き `:1821`、comment L1820-1827 の行、行数の範囲内) と、`test_c05_limit_declaration_agreement.py:555` の折返し `structured.py:` + `923` (`test_conformance_docstring_position_refs.py::test_pin_the_one_remaining_line_wrapped_position_reference_in_the_real_corpus` が解決と範囲を固定)。触らない。→ `platform_declarations.py`: 0。
- README (root・両 peer)、両 peer の `docs/`: 0。r2db `tests/`: 4 (basename だけ: `test_foundation.py:617` `:229`、`:886` `:212`、`:1280` `:702`、`test_l1_details_vocabulary_ast_scan.py:738` `:1508`)。MitateDB `tests/`: 1 (basename だけ、`test_l1_details_vocabulary_ast_scan.py:809` `structured.py:1508`)。r2db `conformance/`: 3 行 (basename だけ: `conformance_adapter_r2db.py:319`・`:1031` の `structured.py:2269` + 続き `:2294`・`:2697`・`:2718` (行数 1867 を超え、移動前から古い)、`:1286` の `:1183`)。すべて触らない。
- `docs/` (設計・作業指示書・archive の記録): 187 出現、`security/CONTROL_MAPPING_HISTORY.md`: 0。触らない。

## 4. 行番号 pin と、module を文字列として読む検査

- 行番号 pin: r2db `tests/test_l1_details_vocabulary_ast_scan.py` の `_BACKEND_LAYER_ALLOWLIST` (L140-299) は実体 1 行 `("postgres.py", 1948)` で、`test_backend_layer_allowlist_is_confined_to_postgres_py` (L702) が全要素の module を `postgres.py` に固定する。`structured.py` の `(module, lineno)` pin は **0 件**。`SCANNED_MODULES` (L107) に `structured.py` は在るが名前だけ。件数 pin `"structured.py": 48` (L574、`test_ast_full_count_matches_the_audit_site_count`) は `_fail_call_sites` (ast) の数でコメントに依らない。MitateDB `tests/test_l1_details_vocabulary_ast_scan.py` の `_BACKEND_LAYER_ALLOWLIST` (L306-376) は 17 行すべて `backend_postgres.py`、`_CONTROL_PLANE_NO_VOCABULARY_ALLOWLIST` は空。`platform_declarations.py` の pin は **0 件**。→ 完了条件 9 は両 module とも非該当 (監査照合)。pins.md 参照。
- module を文字列として読む検査 (設計 §5 (b) の grep `read_text|\.count\(|getsource|__doc__` を両 peer の `tests/`・`conformance/`、`conformance-tests/`、`tools/tests/` に掛け、module 名・symbol 名の近傍を見た): 2 module を対象にするものは **0 件**。除いたもの (名指し): `MitateDB-api/tests/test_ops_startup_checks.py` の `_load_module` (L304。`<ref>:platform_declarations.py` を `compile` + `exec` する。`_f16_agrees_on_row` L568、`_f18_agrees_on_row` L616 が呼ぶ。compile はコメントに鈍感)、`r2db-api/tests/test_process_ceilings_declaration.py:839` (`inspect.getsource` を **r2db の** `platform_declarations.py` の 2 関数に `not in` で掛ける、`test_declaration_table_is_the_only_source_no_env_fallback`。本変更セットの module ではない)、`MitateDB-api/tests/test_r113_multi_process_wiring.py:435` (`getsource(ApplicationCell._limit_gate)`、cell.py)、`tools/tests/test_sql_statement_safety_scan.py` (module 名の一覧は走査対象の集合の pin で、本文を読まない)、`tools/tests/test_leaf_import_direction.py` (名前と説明だけ)。→ 完了条件 10 は非該当。

## 5. WP の分け方の案 (対象の塊の合計 134 > 130)

| 案 | 境界 | 塊の数 | 評価 |
|---|---|---|---|
| (a) module で分ける: WP-9a = r2db `structured.py`、WP-9b = MitateDB `platform_declarations.py` | ファイル境界 | 103 / 31 | spec・受け皿・`repull.py` の対象が 1 ファイルずつで衝突しない。WP-9b は小さく、`#:` 塊と `security/CONTROL_MAPPING.md` の版上げを 2 回に分ける手間だけが残る。手本 (CS7、ファイル内で 102 / 103) と同じ順の手順 |
| (b) 1 WP (CS5・CS6 の前例 113〜123 塊) | — | 134 | 編集した塊は 42 (36 + 6) で CS7 の WP 1 つ (36〜42) と同じ規模。レビューの戻しが 2 ファイルに及ぶ |
| (c) `structured.py` を `ApplicationCell` の `def` 行 (L746) で割る + MitateDB | L1-745 / L746-1867 / MitateDB | 58 / 45 / 31 | 3 WP。版上げ 3 回。塊 134 で 3 WP は過分 |

裁定は 18.5 に置く (決めない)。
