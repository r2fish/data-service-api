# 作業指示書 — R-110 未宣言 field 名の拒否の統一 (契約 1.10.0 → 1.11.0、C-31)

## 0. 版数・位置づけ

- **v1.0 (2026-09-25)。** 基点 local main `b9a41ef` (契約 1.10.0)。Change Set Manifest 形式 (`docs/design/ROADMAP_POST_PHASE7_V1.md` (以下 `RM`) §9 の 9)。
- 台帳: `RM` §8 の R-110。**規模 M** (起票時 S。依頼者裁定 2026-09-25 (逐語)「A で 1.11.0、規模 M で進めてください」により引き上げ — 契約版 1.11.0 と新条件 C-31 を伴うため。`docs/work-orders/OPERATING_CONDITIONS.md` (以下 `OC`) §1.13 の 73・74)。**変更クラス D** (`security/CONTROL_MAPPING.md` の Evidence 追加。`RM` §9 の 8)。下限は `tools/change_class.py` で確かめる。
- 設計文書は持たない (規模 M は作業指示書 1 節。`OC` §1.13 の 74)。枠は本書 §1、確定文は **`$SP/verbatim-1110.md`** (§1〜§5。監督の scratchpad)。
- 手本: `docs/work-orders/WORK_ORDER_PHASE11_KEYSET_PAGING_V1.md` §2 (WP-1 契約) と §7 (WP-6 版フリップと記録)、commit `3af11b3` / `5d988c6` のファイル列。**本書はそれらを写さず節番号で指す。**
- 役割: 実装担当 (テンプレ 2) 1 回、コードレビュー (テンプレ 5、Class D) 1 回、受け入れ監査 (テンプレ 6。Class D なので起動) 1 回 (`docs/work-orders/ROLE_PROMPT_TEMPLATES.md`)。commit・完了ゲート・merge は監督。
- 本書は C-31 を引く。C-31 は同じ変更セットで `conformance-tests/CONDITIONS.md` に行が入るまで `check_doc_refs` で解決しない。

## 1. 監督確定事項

1. **A (依頼者裁定 2026-09-25)**: 未宣言 field 名の拒否を両 peer で `VALIDATION_FAILED` / `violated_declaration: request_schema` / `field` = 位置 path に揃える。位置は 4 つ — `select/<i>`、`where/<i>/field`、`order_by/<i>/field`、`operations/<i>/values/<name>`。`declared_type`・`observed_type` は載せない。`NOT_FOUND` は未知の entity / row に限る。文言は確定文 §1。
2. 契約 1.11.0 = 従属判断 16。置くもの: `errors.details_vocabulary.undeclared_field` (確定文 §1)、`versioning.version_binding` の段落 (§2。1.10.0 の段落の直後、version-flip 文の直前)、`versioning.obligations` の entry (§3。1.10.0 の entry の直後 = index 9)。
3. **旧い遡及拒否の行と 1.9.0 / 1.10.0 の段落は触らない** (`spec/CONTRACT_HISTORY.md` `## versioning.version_binding` の Revision note 3 の方針)。
4. 1 WP、1 worktree、1 commit、main へ 1 merge。版フリップ (両 peer の data 側と control 側) は実挙動と同じ commit (C-19)。
5. C-31 の版ゲートは C-30 と同じ形の **non-strict** xfail (`parse_semver(contract_version) < (1, 11, 0)`、`request.node.add_marker`)。commit 時点では 24 node すべて ok。
6. 確定文は `$SP/verbatim-1110.md` から逐語で複製する (`OC` §1.5 の 35・36)。
7. 変異を持たない完了条件の逐語記録 (コマンドと集計行、または file:line) は、設計文書が無いので本書 §5 に残す (`OC` §1.5 の 40)。

## 2. WP-1 — 契約 1.11.0、C-31、両 peer の拒否と宣言、記録

### 2.1 目的

契約 1.11.0 を置き、4 位置の未宣言 field 名の拒否を両 peer で同じ形にし、C-31 を 6 plug で緑にする。両 peer の宣言を同じ commit で 1.11.0 にし、記録を揃える。

### 2.2 読むべき正本

- `$SP/verbatim-1110.md` §1〜§5
- `spec/data-service-api.v1.json` の `errors.details_vocabulary`・`versioning.version_binding`・`versioning.obligations`
- `spec/CCR_DISPOSITION.md` の従属判断 15 (形の手本)、`spec/CONTRACT_HISTORY.md` の `## versioning.version_binding` (Revision note 3〜6)、`spec/README.md`:27 (1.10.0 の段落)
- `conformance-tests/test_c30_keyset_paging.py` (版ゲートと `observed_branch` の作法)、`conformance-tests/test_contract.py` の 1.10.0 のピン (`test_contract_pins_the_1_10_0_*`)
- `conformance-tests/CONDITIONS.md` の C-30 行、`conformance-tests/CONDITIONS_HISTORY.md` の `## C-30`
- `security/CONTROL_MAPPING.md` 3.3 の SI-10 `### Common` の `#### Evidence` (形式 3.0)
- 手本の作業指示書 §2・§7

### 2.3 現状と目標 (起草時の実測。着手時に再実測する)

| 位置 | r2db-api 現状 | MitateDB-api 現状 | 目標 (両 peer) |
|---|---|---|---|
| select | `NOT_FOUND`、details なし (`r2db-api/src/r2db_api/mutation_binding.py`:69-70 `validate_projection`) | `VALIDATION_FAILED` / `request_schema` / `select/<field 名>` (`MitateDB-api/src/mitatedb_api/cell.py`:3268-3274 `_select_fields`) | `select/<i>` |
| where | `NOT_FOUND`、details なし (`mutation_binding.py`:83-84 `validate_predicates`) | `where/<i>/field` (`cell.py` の `_bind_filters`、:3561 以下) | `where/<i>/field` |
| order_by | `NOT_FOUND`、details なし (`r2db-api/src/r2db_api/paging.py`:70-71 `_resolve_order_by`) | `order_by/<i>/field` (`cell.py`:3355-3359 `_bind_order_by`) | `order_by/<i>/field` |
| values | `NOT_FOUND`、details なし (`mutation_binding.py`:190-191 `bind_mutation`) | `operations/<i>/values/<name>` (`cell.py`:3513-3516 `_prepare_values`。`MitateDB-api/tests/test_denial_details_and_request_id.py` の `test_single_unknown_field_names_it_as_field` が固定) | `operations/<i>/values/<name>` |

r2db の新しい拒否は既存の `violation(...)` helper と同じ 2 キー (`violated_declaration`・`field`) で出す。`validate_predicates` は mutation の `where` とも共有であり、`path_prefix` どおりの path になる。

### 2.4 タスク

1. **契約 JSON 3 複製** (`spec/`、両 peer の `contract/`): 確定文 §1〜§3 を逐語で置き、`contract_version` を 1.11.0 にする。3 複製を同一バイトにする。`spec/OPERATION_CATALOG.json` を再生成し (`./.venv/bin/python $WT/tools/contract_catalog.py`。出力先が `$WT/spec/` であることを確かめる)、`--check` で照合する。
2. **`spec/CCR_DISPOSITION.md`**: 従属判断 15 の後に 16 を置く (依頼者裁定の逐語と A の内容。版数の扱い)。
3. **`spec/CONTRACT_HISTORY.md`**: 既存の `## versioning.version_binding` 節に Revision note を 1 本足す (確定文 §5 の要旨)。register test が求める追随 (Value の引用・従属判断の列・`Introduced in`) は `3af11b3` の形に倣う。新しい `## <json_path>` 見出しを作らない。marker 走査の実測 (件数と見出しの増減) を Revision note に書く。
4. **`spec/README.md`**: 1.10.0 の段落 (:27) の形で 1.11.0 の段落を足す。
5. **`conformance-tests/test_contract.py`**: `test_contract_declares_1_10_0` を 1.11.0 に追随させる。1.11.0 のピンを足す — (a) `obligations[9]` の等号、(b) version_binding 段落の逐語と位置 (1.10.0 段落末尾の遡及文と `A peer's version-flip` の間が段落だけであることの等号)、(c) `errors.details_vocabulary.undeclared_field` の逐語の等号。既存の 1.10.0 の version_binding ピンの右端の追随以外で既存ピンを変えない。
6. **`conformance-tests/test_c31_undeclared_field_refusal.py`** (新規、`pytestmark = pytest.mark.condition("C-31")`): 6 plug × 4 位置 = 24 node。既存の port (`query_page`、`attempt_mutation`) で駆動する。各位置で次を assert する。
   - (a) 未宣言名を含む要求 → `ConformanceDenial` の code が `VALIDATION_FAILED`、`details.violated_declaration == "request_schema"`、`details.field` が期待 path と等号、`declared_type`・`observed_type` がキーとして無い。
   - (b) 同じ要求の未宣言名だけを宣言 field に替えると成功する。替える先は同じ要求の他の entry と重ならない field にする (r2db は `order_by` の同一 field の重複を拒否する。`r2db-api/tests/test_postgres.py` の `test_order_by_unknown_field_is_not_found_and_rejects_a_repeated_field`)。
   - (c) `conftest.assert_details_vocabulary_values_safe`。
   - 版ゲートと `observed_branch` の突合は `test_c30_keyset_paging.py` の形 (`>= 1.11.0` の枝だけで突合)。
7. **`conformance-tests/CONDITIONS.md`** に C-31 行 (Condition = 確定文 §4 逐語、Status = `executable (six adapters)` とテスト名・駆動・非空振りの根拠、Evidence = テスト名)。**`conformance-tests/CONDITIONS_HISTORY.md`** に空でない `## C-31`。
8. **r2db-api**: 2.3 の表の 4 箇所を目標の形にする。
9. **MitateDB-api**: `_select_fields` の path を `select/<i>` にする。where / order_by / values は 2.3 の表の現状を再実測し、目標と違えば合わせる。
10. **宣言**: 両 peer の `capabilities_document.py` と `control_plane.py` の `contract_version` を 1.11.0 に (同一 commit)。1.10.0 の宣言を固定する peer の test を追随させる (`grep -rn '1\.10\.0' r2db-api/tests MitateDB-api/tests` で列挙。起草時は r2db 4 ファイル・MitateDB 5 ファイル。宣言値の等号でない行 (経緯の docstring) は触らない)。
11. **既存の unit test**: 4 位置の未宣言 field 名について `NOT_FOUND` を固定する r2db の test を新しい形に更新する — 起草時の実測は `r2db-api/tests/test_foundation.py` の `test_developer_schema_catalog_controls_fields` (:141 の assert のみ) と `test_order_by_unknown_field_is_not_found`、`r2db-api/tests/test_postgres.py` の `test_order_by_unknown_field_is_not_found_and_rejects_a_repeated_field`、`r2db-api/tests/test_http.py` の `test_query_order_by_unknown_field_is_not_found`。旧い挙動を名乗る test 名は改名してよい。未知の entity / row / index の `NOT_FOUND` を固定する test は触らない。MitateDB で select の未宣言名の path を固定する unit test は起草時の grep で見つかっていない — 再実測し、有れば追随させ、無ければ報告する (新設は監督裁定)。
12. **L1 details 語彙の走査**: 両 peer の `tests/test_l1_details_vocabulary_ast_scan.py` の件数 pin・行番号 allowlist を実測で追随させる (`OC` §1.5 の 40b の趣旨。pin を実測値へ合わせるだけで済ませず、新しい拒否が走査対象に入ったことを確かめる)。
13. **コメントの出所**: 登録済みの block を書き換えるときは `docs/code-history/<peer>/<module>.md` に `### correction` を足す。新しい src コメントに経緯語 (フェーズ・WP・R 番号・裁定名) を書かない。`docs/design/R2DB_CCR13_STORAGE_V1.md` は本文 (§1 の `order_by` の行、§8 の m-6) を書き換えず、文書末尾に訂正註を足す (1.11.0 で覆したこと、根拠 = 従属判断 16、日付)。
14. **記録** (2.5 の表)。

### 2.5 触ってよいパス

- `spec/data-service-api.v1.json`、`spec/OPERATION_CATALOG.json`、`spec/CCR_DISPOSITION.md`、`spec/CONTRACT_HISTORY.md`、`spec/README.md` (`spec/CONTRACT_HISTORY_MANIFEST.json` は変更が要るときだけ)
- `r2db-api/src/r2db_api/contract/data-service-api.v1.json`、`MitateDB-api/src/mitatedb_api/contract/data-service-api.v1.json`
- `r2db-api/src/r2db_api/mutation_binding.py`、`r2db-api/src/r2db_api/paging.py`、`MitateDB-api/src/mitatedb_api/cell.py` (2.3 の拒否の箇所のみ)
- `r2db-api/src/r2db_api/capabilities_document.py`、`r2db-api/src/r2db_api/control_plane.py`、`MitateDB-api/src/mitatedb_api/capabilities_document.py`、`MitateDB-api/src/mitatedb_api/control_plane.py` (宣言値とその註のみ)
- 両 peer の `tests/` のうち、タスク 10〜12 で列挙した file
- `conformance-tests/test_c31_undeclared_field_refusal.py` (新規)、`conformance-tests/test_contract.py`、`conformance-tests/CONDITIONS.md`、`conformance-tests/CONDITIONS_HISTORY.md`
- `security/CONTROL_MAPPING.md`
- `docs/code-history/` 配下 (タスク 13 の `### correction` のみ)、`docs/design/R2DB_CCR13_STORAGE_V1.md` (末尾の訂正註のみ)
- `RM`、`docs/archive/docs/design/ROADMAP_POST_PHASE7_V1__VERSION_LOG.md` (回転する 1 行の追加のみ)、本書 §5

| 記録 | 内容 | 書く人 |
|---|---|---|
| `security/CONTROL_MAPPING.md` 3.3 → 3.4 | SI-10 の `### Common` `#### Evidence` に C-31 の Evidence 1 行 (形式 3.0、テスト名で指す)。Control claim は足さない。版の行 | 実装担当 |
| `RM` v1.122 | R-110 行に【追記】(規模 S → M と依頼者裁定の逐語、完了条件・変異の結果、`pt.py` の集計行)。§0.1.1 G-2 / G-3 行を 1.11.0 / C-00〜C-31 の 32 件。§0.1.2 の「判定を受ける」段に C-31。版数ログを 5 行に保ち、6 行目 (v1.117) を記録へ移す (`OC` §1.16 の 78) | 実装担当 (完了ゲートの集計行は監督が merge 前に足す) |
| `docs/work-orders/HANDOVER_20260925_FABLE2.md` | R-110 の節と「裁定」節への追記 (新しい引き継ぎ書は作らない。`OC` §1.13 の 75) | 監督 |

### 2.6 触らないパス

`conformance-tests/adapter.py` と plug、C-31 以外の `conformance-tests/test_*.py` (register 系を含む)、両 peer のその他の `src/`、`tools/` (`tools/tests` を含む)、`security/` の `CONTROL_MAPPING.md` 以外、`OC`、`CLAUDE.md`。port や register test、`tools/tests` の pin に変更が要ると分かったら、実装前に監督へ上げる (`OC` §1.5 の 37)。

### 2.7 期待結果表 (commit の時点)

C-31 の 4 位置 × 6 plug (r / rh / rs / m / mh / ms。略記は手本の作業指示書 §1.5) = 24 node がすべて **ok**。xfailed = 0、xpassed = 0。C-30 の 9 node × 6 plug は ok のまま。

### 2.8 完了条件 (assert 水準)

1. 3 複製の `versioning.obligations[9]` が確定文 §3 と等号 (新しい obligations ピンが緑)。
2. `versioning.version_binding` の 1.11.0 段落が確定文 §2 と逐語で一致し、位置が §1 の 2 のとおり (新しい version_binding ピンが緑)。
3. `errors.details_vocabulary.undeclared_field` が確定文 §1 と等号 (新しい語彙ピンが緑)。
4. 3 複製の `contract_version` が 1.11.0 (`test_contract_declares_1_11_0` が緑)。
5. `test_contract.py` の既存ピンの変更が 1.11.0 の追随 (宣言版のテストと 1.10.0 の version_binding ピンの右端) に限られる。
6. 3 複製が同一バイト (`test_contract_packaged_copies_are_byte_identical` が緑)。
7. `CCR_DISPOSITION.md` に従属判断 16 がある (`test_versioning_obligations_subordinate_rulings_exist_in_ccr_disposition` が緑)。
8. `CONTRACT_HISTORY.md` の Revision note が `## versioning.version_binding` 節にあり、新しい `## ` 見出しが無く、`conformance-tests/test_contract_history_register.py` が緑。
9. `spec/OPERATION_CATALOG.json` が再生成と一致 (`--check` の終了コード 0、`conformance-tests/test_operation_catalog_register.py` が緑)。
10. `spec/README.md` に 1.11.0 の段落がある。
11. r2db の select の拒否が目標の形で、C-31 の select node が r / rh / rs で緑。
12. r2db の where の拒否が目標の形で、C-31 の where node が r2db の 3 plug で緑。
13. r2db の order_by の拒否が目標の形で、C-31 の order_by node が r2db の 3 plug で緑。
14. r2db の values の未知 key の拒否が目標の形で、C-31 の values node が r2db の 3 plug で緑。
15. MitateDB の select の path が `select/<i>` で、C-31 の select node が m / mh / ms で緑。
16. MitateDB の where の path が `where/<i>/field` で、C-31 の where node が MitateDB の 3 plug で緑。
17. MitateDB の order_by の path が `order_by/<i>/field` で、C-31 の order_by node が MitateDB の 3 plug で緑。
18. MitateDB の values の path が `operations/<i>/values/<name>` で、C-31 の values node が MitateDB の 3 plug で緑。
19. 4 位置の拒否の details に `declared_type`・`observed_type` が無い (C-31 の (a) が assert)。
20. C-31 の (b) の成功脚が 24 node すべてで実際に成功を観測する。
21. C-31 の details が語彙の外のキーや要求に無い値を運ばない (C-31 の (c))。
22. C-31 の版ゲートが non-strict xfail である (`< 1.11.0` の宣言では xfail になり、失敗しない)。
23. 両 peer の data 側と control 側の宣言が 1.11.0 で、`conformance-tests/test_c19_client_self_sufficiency.py` が緑。
24. 両 peer の `src/` に宣言 1.10.0 が残っていない (data 側と control 側)。
25. 4 位置の未宣言名に `NOT_FOUND` を固定していた r2db の unit test が新しい形を固定する。
26. 両 peer の `tests/test_l1_details_vocabulary_ast_scan.py` が緑で、pin の変化が実測に基づく。
27. `CONDITIONS.md` の C-31 行の Condition 欄が確定文 §4 と逐語で一致し、`## C-31` があり、`conformance-tests/test_conditions_register.py` が緑。
28. `CONTROL_MAPPING.md` が 3.4 で、C-31 の Evidence のテスト名が解決する (`conformance-tests/test_control_mapping_register.py` が緑)。
29. `RM` の記録 (2.5 の表) があり、版数ログの回転が済み、`check_doc_refs` が dangling 0。
30. コメントの出所の検査が緑 (`--register` と、触った src に対する `--base b9a41ef`)。`R2DB_CCR13_STORAGE_V1.md` の本文が変わっていない (差分は末尾の訂正註だけ)。
31. conformance の部分集合 2 本、C-31 単独、両 peer の suite、`tools/tests` が緑 (failed / xfailed / xpassed = 0)。
32. 触ったファイルの `public_value_scan` が `total_flagged=0`。
33. 2.14 の表に、変異も監査照合も持たない行が無い。

### 2.9 非空振り要件

- 未宣言名は各位置で **index 1 以上** に置き、index 0 には宣言 field を置く (期待 path の index が定数 0 や容器の位置と区別できるように)。期待 path は要求の実位置から計算する。
- C-31 の 24 node が `>= 1.11.0` の枝で走ったことを、`observed_branch` の突合と node 数 (6 plug × 4 位置) で報告する。
- (b) の成功は返った items / 影響件数を assert する (例外が出なかったことだけで済ませない)。
- 新しい契約ピンは確定文を定数に持ち、等号で比べる (部分一致にしない)。

### 2.10 同型性テストの対象

なし。`_ISOMORPHIC_TARGETS` を増減しない。両 peer に同名の helper を新設する必要が出たら実装前に上げる。

### 2.11 道具の引数と集計行の期待形

リポジトリ root から root の `.venv` で起動する。`WT=.claude/worktrees/r110`。

```
./.venv/bin/python tools/dev/pt.py -C $WT --wait 300 -- conformance-tests/test_contract.py conformance-tests/test_contract_history_register.py conformance-tests/test_operation_catalog_register.py conformance-tests/test_conditions_register.py conformance-tests/test_control_mapping_register.py -q
./.venv/bin/python tools/dev/pt.py -C $WT --wait 300 -- conformance-tests/test_c31_undeclared_field_refusal.py -q -rxX -n 2
./.venv/bin/python tools/dev/pt.py -C $WT --wait 300 -- conformance-tests/test_c19_client_self_sufficiency.py conformance-tests/test_c30_keyset_paging.py -q -rxX -n 2
./.venv/bin/python tools/dev/pt.py -C $WT --wait 300 -- conformance-tests -k "not MitateDB" -q -rxX -n 5 --dist loadgroup
./.venv/bin/python tools/dev/pt.py -C $WT --wait 300 -- conformance-tests -k "not r2db" -q -rxX -n 5 --dist loadgroup
./.venv/bin/python tools/dev/pt.py -C $WT --wait 300 -- r2db-api/tests -q
./.venv/bin/python tools/dev/pt.py -C $WT --wait 300 -- MitateDB-api/tests -q
./.venv/bin/python tools/dev/pt.py -C $WT --wait 300 -- tools/tests -q
./.venv/bin/python $WT/tools/contract_catalog.py --check
./.venv/bin/python $WT/tools/check_doc_refs.py
./.venv/bin/python $WT/tools/check_comment_provenance.py --register
./.venv/bin/python $WT/tools/check_comment_provenance.py --base b9a41ef <触った src のパス>
./.venv/bin/python $WT/tools/public_value_scan.py <触ったファイル (worktree からの相対)>
./.venv/bin/python tools/dev/mutate.py "$SP/r110-mutations.json" -C $WT --wait 300
```

- 集計行の期待形: C-31 単独 `pt: 24 passed`、部分集合 2 本と各 suite は failed / xfailed / xpassed が 0。conformance 全体・`tools/dev/gate.py`・`tools/dev/finalize.py` は監督だけが回す。
- 変異ファイルの entry は **単一の node id、`-n` なし**とする (`mutate.py` は最初の赤で止まる)。「全 plug で赤」を言う変異は plug ごとに entry を分ける。報告には `pt.py` / `mutate.py` の出力行 (集計行・変異表・`log=`) をそのまま貼る (`OC` §1.10 の 65)。

### 2.12 使用テンプレート

実装 = テンプレ 2 (Sonnet)、コードレビュー = テンプレ 5 (Class D)、受け入れ監査 = テンプレ 6。

### 2.13 禁止事項

手本の作業指示書 §1.6 の 1〜3・6・7 に加えて:

- 確定文を言い換えない。spec の他の文を変えない。遡及拒否の旧い行と 1.9.0 / 1.10.0 の段落を触らない。`required` 配列・既存キー・既存 enum を変えない。
- 新しい src コメントに経緯語を書かない。登録済みの block を `### correction` なしに書き換えない。
- 片 peer だけ、または data 側だけフリップした状態を残さない。変異による一時フリップを残さない (復元は `mutate.py` に任せ、`git checkout --` を使わない)。
- 未知の entity / row / index の `NOT_FOUND` を変えない。schema 操作の拒否を変えない。
- `COLLECTION_FLOOR` を触らない。`skip` を使わない。

### 2.14 完了条件番号 → 変異

| 完了条件 | 変異 (`file:操作`) | 赤になる test |
|---|---|---|
| 1 | M1: 3 複製の 1.11.0 entry の `unconditional` を空にする | 新しい obligations ピン |
| 2 | M2: 3 複製の 1.11.0 段落の 1 語を変える | 新しい version_binding ピン |
| 3 | M3: 3 複製から `errors.details_vocabulary.undeclared_field` を消す | 新しい語彙ピン |
| 4 | M4: 3 複製の `contract_version` を 1.10.0 に戻す | `test_contract_declares_1_11_0` |
| 5 | 監査照合: `git diff b9a41ef -- conformance-tests/test_contract.py` の既存ピンの変更行の列挙 (§5) | — |
| 6 | M6: `r2db-api/src/r2db_api/contract/data-service-api.v1.json` だけ 1 語変える | `test_contract_packaged_copies_are_byte_identical` |
| 7 | M7: `CCR_DISPOSITION.md` の従属判断 16 の番号を変える | `test_versioning_obligations_subordinate_rulings_exist_in_ccr_disposition` |
| 8 | M8: `CONTRACT_HISTORY.md` の Value の引用から 1.11.0 段落の 1 語を変える。加えて監査照合: marker 走査の実測 (§5) | `conformance-tests/test_contract_history_register.py` の引用照合 |
| 9 | M9: `spec/OPERATION_CATALOG.json` の `contract_version` を 1.10.0 に戻す | `conformance-tests/test_operation_catalog_register.py` |
| 10 | 監査照合: `spec/README.md` の差分 (§5) | — |
| 11 | M11-r / M11-rh / M11-rs: `mutation_binding.py` の `validate_projection` を `NOT_FOUND` に戻す | C-31 の select node (r / rh / rs) |
| 12 | M12: `validate_predicates` を `NOT_FOUND` に戻す | C-31 の where node (r) |
| 13 | M13: `paging.py` の `_resolve_order_by` を `NOT_FOUND` に戻す | C-31 の order_by node (r) |
| 14 | M14: `bind_mutation` の未知 key を `NOT_FOUND` に戻す | C-31 の values node (r) |
| 15 | M15-m / M15-mh / M15-ms: `cell.py` の `_select_fields` の path を `f"select/{field}"` に戻す | C-31 の select node (m / mh / ms) |
| 16 | M16: `_bind_filters` の path から `/field` を外す | C-31 の where node (m) |
| 17 | M17: `_bind_order_by` の path から `/field` を外す | C-31 の order_by node (m) |
| 18 | M18: `_prepare_values` の path を `values/<name>` にする (`operations/<i>/` を外す) | C-31 の values node (m) |
| 19 | M19: `_select_fields` の拒否の details に `"declared_type": "string"` を足す | C-31 の select node (m) |
| 20 | M20: `validate_projection` が index 1 以上の entry を宣言 field でも拒否する (判定に `or i >= 1` を足す) | C-31 の select node (r)。(a) は緑のまま (b) で赤 |
| 21 | M21: `_select_fields` の拒否の details に語彙外のキー (値 = 宣言 field 名) を足す | C-31 の select node (m) |
| 22 | M22 (**expect: green**): r2db の `capabilities_document.py` と `control_plane.py` を 1.10.0 に戻し、同時に M11 の本体変異を入れる。加えて監査照合: 同じ状態の `pt.py -rxX` の short test summary に XFAIL が出ること (§5) | C-31 の select node (r) が xfail で緑 |
| 23 | M23-r: r2db の `capabilities_document.py` だけ 1.10.0 に戻す / M23-m: MitateDB の `capabilities_document.py` だけ 1.10.0 に戻す (entry を分ける) | `test_c19_surfaces_present_and_consistent_across_both_documents` (その peer の plug) |
| 24 | 監査照合: 両 peer の `src/` で `"contract_version": "1.10.0"` の grep 0 件 (§5) | — |
| 25 | M25: `paging.py` の `_resolve_order_by` を `NOT_FOUND` に戻す | タスク 11 で更新した r2db の order_by の unit test (`r2db-api/tests/test_foundation.py`) |
| 26 | 監査照合: 両 peer の `test_l1_details_vocabulary_ast_scan.py` の差分と集計行 (§5) | — |
| 27 | M27: `CONDITIONS_HISTORY.md` の `## C-31` 節を削る。加えて監査照合: C-31 行の Condition 欄と確定文 §4 の diff 0 行 (§5) | `test_conditions_history_has_exactly_the_main_tables_ids` |
| 28 | M28: `CONTROL_MAPPING.md` の C-31 の Evidence の node 名を存在しない名前にする | `conformance-tests/test_control_mapping_register.py` の名前解決テスト |
| 29 | 監査照合: `RM` の差分と `check_doc_refs` の出力行 (§5) | — |
| 30 | 監査照合: `check_comment_provenance.py` の出力行と `R2DB_CCR13_STORAGE_V1.md` の差分 (§5) | — |
| 31 | 監査照合: `pt.py` の集計行 (§5) | — |
| 32 | 監査照合: `public_value_scan` の出力行 (§5) | — |
| 33 | 監査照合: 本表 | — |

## 3. merge (監督)

1. 実装担当の報告 → コードレビュー (テンプレ 5) → 差し戻しはファイルで (`OC` §1.7 の 49) → 受け入れ監査 (テンプレ 6)。
2. 完了ゲート `./.venv/bin/python tools/dev/gate.py -C $WT --label r110` を 1 回。集計行を `RM` の R-110 の【追記】と本書 §5 に足す。
3. **依頼者確認 (Q-4 の形)**: 契約版に触れる merge の前に、完了ゲートの集計行と main に対する `git diff --stat` を添えて確認を取る。確認が得られるまで merge しない。
4. `tools/dev/finalize.py` で commit と merge (1 commit)。引き継ぎ書 `docs/work-orders/HANDOVER_20260925_FABLE2.md` に R-110 の節と裁定を追記する。

## 4. 訂正註

(実施中に本書の誤り・発注後の監督裁定が生じたらここへ追記する。本文は書き換えない。`OC` §1.8 の 57。)

**訂正註 1 (2026-09-25、コードレビュー F1〜F8 への監督裁定による差し戻し)**: 確定文 §1 の末尾文を「NOT_FOUND is not a conforming refusal of an undeclared field name at these positions.」に狭めた (F1。upsert の unique_key と schema 操作の NOT_FOUND との衝突を避けるため)。C-31 の values 脚の entity を `{a, b}` にし成功脚を 2 key にした (F2)。両 peer に mutation の where (5 番目の位置、`operations/<i>/where/<j>/field`) を固定する unit test を 1 本ずつ追加した (F3。§2.4 のタスクが明示していなかった観測を、契約が同じ共有関数で義務化しているために補った)。CONTRACT_HISTORY の Revision note 7 に §5 の要旨 3 点を追記した (F5)。RM の R-110 行の形式を修正した (F6)。新しい src コメントから経緯語・裁定名を除いた (F7)。test_c31 の docstring と CONTROL_MAPPING の C-31 行を直した (F8)。F9 (複数欠陥時の判定順の相違) は観察として記録し、契約・実装は変更しない。

**訂正註 2 (2026-09-25、受け入れ監査への監督裁定)**: 確定文 §4 の「at each of the four positions」を「at four of the five positions … -- the fifth, a mutation's where predicate field (`operations/<i>/where/<j>/field`), is pinned by each peer's own unit test;」に改めた (疑義 3。契約は 5 位置を名指すが、C-31 自体は 4 位置しか駆動しない — 5 つ目は F3 の unit test が固定する)。`CONDITIONS.md` C-31 行の Condition 欄と `test_c31_undeclared_field_refusal.py` の docstring をこの新しい確定文に揃えた。C-31 の values 脚を 2 operation の batch にし、2 つ目の operation に未宣言名を置いて `operations/1/values/<name>` を確認する形に改めた (O2。全 6 plug で batch が使えることを確認済み)。r2db の `mutation_binding.py`/`paging.py` の comment から「NOT_FOUND stays reserved for a missing entity or row」を除いた (O1)。MitateDB `capabilities_document.py` の宣言 comment の 3 点 (values の path は index 形ではない、契約は 5 位置、経緯語「now」) を直し、`docs/code-history/MitateDB-api/capabilities_document.md` に同じ correction を足した (O4)。RM の R-110 行の版数行の「完了ゲート未反映」文と、RM・作業指示書 §5 のバッククォート崩れ、§5 の完了条件 26 の suite 件数 (1470/1475) を直した (O3)。`test_conditions_register.py` の module docstring に Known gaps 1 行を足した (O5、CONDITIONS.md の Invariants 欄はどの register も読まないという既知の穴。§1.12 の 71)。完了条件 30 は、コード変更を伴う WP では「(5) 履歴語 0 と `--register` OK」と読み替える (下記、未充足 30 への裁定)。完了条件 31 (`test_c27_same_digest_executes_once[MitateDB-api-http]` の既知 flake、R-111) は頻度を RM の R-111 行に追記のうえ、抱えたまま merge する (Q-4 で明示。完了ゲート全体は緑)。

## 5. 実施記録

(監査照合の逐語記録 — 実行したコマンドと集計行、または file:line — を完了条件番号ごとに記す。完了ゲートの集計行と Q-4 の確認の逐語は監督が記す。)

**完了条件 5** (`git diff b9a41ef -- conformance-tests/test_contract.py` の既存ピンの変更行の列挙): 既存の test 定義で名前・本体が変わったのは 2 件のみ -- `test_contract_declares_1_10_0` → `test_contract_declares_1_11_0` (アサート値の追随) と `test_contract_pins_the_1_10_0_version_binding_paragraph_verbatim` (右端のアンカーを `"A peer's version-flip"` の索引から `"Only an implementation declaring 1.11.0"` の索引へ変更 -- `PIN_1_10_0_VERSION_BINDING_PARAGRAPH` 自体の文字列は無変更)。他の既存ピン (`PIN_1_10_0_*`、`test_contract_pins_the_1_10_0_obligations_entry_verbatim` 等) は無変更。新規追加は `FIXED_1_11_0_OBLIGATIONS_ENTRY`・`PIN_1_11_0_*`・`test_contract_pins_the_1_11_0_*` の 3 test。

**完了条件 10** (`spec/README.md` の差分): 1.10.0 の段落 (Contract **1.10.0** ...) の直後に 1.11.0 の段落を追加した以外、既存文への変更は無い (`git diff b9a41ef -- spec/README.md` は追加行のみの diff)。

**完了条件 24** (両 peer の `src/` で `"contract_version": "1.10.0"` の grep 0 件): `grep -rn '"contract_version": "1.10.0"' r2db-api/src MitateDB-api/src` → 0 件 (両 peer とも `capabilities_document.py`/`control_plane.py`/`contract/data-service-api.v1.json` が 1.11.0 を宣言)。

**完了条件 26** (両 peer の `test_l1_details_vocabulary_ast_scan.py` の差分と集計行): r2db 側は `mutation_binding.py: 18 → 21`(+3: `validate_projection`/`validate_predicates`/`bind_mutation` の未宣言 field 判定が `NOT_FOUND` から vocabulary コードへ移った分)・`paging.py: 6 → 7`(+1: `_resolve_order_by`)を pin 更新し、`pt: 1470 passed in 106.71s` (r2db-api/tests 全体、本ファイルと F3 の新 unit test を含む最終実測) で緑。MitateDB 側は該当ファイルの pin・件数に変更なし (`_select_fields` の変更は `field` 値の文字列内容のみで、vocabulary コード自体は変わっていないため) -- `pt: 1475 passed, 2 subtests passed in 135.23s` (F3 の新 unit test を含む最終実測) で緑。

**完了条件 8** (marker 走査の件数と見出しの増減): `errors.details_vocabulary.undeclared_field` と `versioning.obligations` の 1.11.0 entry のいずれも marker scanner の hit 0 (`_find_matches` で実測)。RAW contract JSON 全体の scanner hit 総数は **3** のまま (`versioning.compatibility`・`versioning.version_binding`・`destructive_confirmation.phrase_construction.rules[3]` の既存 3 件のみ、`unstripped: true` の 3 path と一致)。`## <json_path>` 見出しの増減は 0 件 (新しい anchor を追加していない)。

**完了条件 22** (XFAIL 行の逐語): M22 (r2db の宣言 1.10.0 + select body の M11 相当変異を同時適用) を単独 `-rxX` で再現し、以下を得た:
```
XFAIL conformance-tests/test_c31_undeclared_field_refusal.py::test_c31_select_names_the_undeclared_entrys_index[r2db-api] - r2db-api declares contract_version '1.10.0' (< 1.11.0) -- the undeclared-field refusal alignment is a 1.11.0 obligation (CCR_DISPOSITION.md subordinate ruling 16); this branch is expected to fail (not merely skip) until this peer's own version-flip commit lands, per the contract's own 1.11.0-only retroactivity rule.
1 xfailed in 0.19s
```

**完了条件 27** (Condition 欄と確定文 §4 の diff 0): `conformance-tests/CONDITIONS.md` の C-31 行の Condition 欄は、生の文字列比較では確定文 §4 と不一致 (Condition 欄はバッククォートで用語を囲むため) だが、バッククォートを除去すると完全一致 (`.replace("`", "")` の上で `==`、Python で実測 `True`) -- C-30 行と同じ扱い。差分はバッククォートの有無のみで、語・句読点は 1 字も違わない。

**完了条件 29** (`RM` の差分と `check_doc_refs` の出力行): `docs/design/ROADMAP_POST_PHASE7_V1.md` に v1.122 の版数ログ行を追加し、R-110 行の状態欄 (第 3 列) を「**閉止 2026-09-25 (v1.122)**」の形にして規模引き上げ・実施内容・実測・`gate: 4198 passed, 2 subtests passed in 330.17s (0:05:30)、judge=PASS、pg_database/pg_roles diff 0、label r110b (最終ツリー。監査追記前の r110 は 349.99s、judge=PASS)` を記した (説明欄は原文のまま、F6 の指摘どおり)、§0.1.1 の G-2/G-3 行 (契約 1.11.0、C-00〜C-31 の 32 件)、§0.1.2 の「判定を受ける」段に C-31 を追加、v1.117 の行を `docs/archive/docs/design/ROADMAP_POST_PHASE7_V1__VERSION_LOG.md` へ回転 (版数ログを 5 行に保持)。`check_doc_refs OK: 0 dangling references` (`tracked markdown files scanned: 213`)。

**完了条件 30** (コメントの出所の検査、`R2DB_CCR13_STORAGE_V1.md` の本文不変): `check_comment_provenance.py --register` → `comment provenance register OK: 92 files scanned, 433 CH-IDs`。`--base b9a41ef` (触った 7 src ファイル: 両 peer の `capabilities_document.py`/`control_plane.py`、r2db の `mutation_binding.py`/`paging.py`、MitateDB の `cell.py`) → §4.1 (1) 「code changed (AST differs, docstrings excluded)」7 件 (実コード・宣言値の変更そのものであり想定どおり)、§4.1 (2) 「CH-ID-less blocks changed」**6 件** (実測。コードレビュー差し戻し F4 により 4 件から訂正): `MitateDB cell.py::_select_fields` stmt#6 (1件)、`r2db mutation_binding.py` の `bind_mutation` stmt#11 (1件)・`validate_predicates` stmt#2 (1件)・`validate_projection` stmt#3 と stmt#4 (2件)、`r2db paging.py` の `_resolve_order_by` stmt#2 (1件) -- いずれも新しい説明コメントを既存の CH-ID を持たない comment block の直前に足したことで anchor 対応がずれた構造的副作用であり (`docs/work-orders/WORK_ORDER_PHASE11_KEYSET_PAGING_V1.md` 実施記録に同種の先例あり)、登録済み (`history: CH-NNNN` を持つ) block の内容変更は 0 件、§4.1 (5) (経緯語の新規追加) は 0 件 (F7 対応後も 0 件のまま実測)。`docs/design/R2DB_CCR13_STORAGE_V1.md` は末尾に「## 13. 訂正註」を追加しただけで、本文 (§1・§8 を含む上位の全節) は無変更 (`git diff b9a41ef -- docs/design/R2DB_CCR13_STORAGE_V1.md` は追加行のみ)。

**完了条件 33** (2.14 の表に、変異も監査照合も持たない行が無いこと): §2.14 の 1〜33 の全行を本節および `tools/dev/mutate.py` の変異表 (verbatim) と対応づけ、いずれの行にも実測記録があることを確認した (対応表は実装担当の最終報告に記載)。

**完了条件 31** (conformance 部分集合 2 本・C-31 単独・両 peer suite・`tools/tests`): 本書の報告 (実装担当の最終報告) に `pt.py` の集計行を verbatim で記載。`-k "not r2db"` は `test_c27_same_digest_executes_once[MitateDB-api-http]` の既知 flake (R-111, AUTH_INVALID) で 2 回とも 1 failed -- 本 WP の変更とは無関係 (触っていないファイル、無関係なコード経路)。他はすべて failed/xfailed/xpassed = 0。

**完了条件 32** (`public_value_scan` の `total_flagged=0`): 触った 42 ファイル (worktree 内の絶対パスで実行) → `# mode=tree files_scanned=42 total_flagged=0`。
