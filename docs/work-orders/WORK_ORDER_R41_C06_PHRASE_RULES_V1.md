# 作業指示書 — R-41 削除確認 phrase の契約規則を C-06 で固定する

## 0. 版数・位置づけ

- **v1.1 (2026-09-26)。** v1.0 → v1.1: 設計レビュー (opus、Class C) の指摘 F1〜F8 を反映 (V13 の名前、V10 の entity の作り方、V12 の同一 entity と affected、M5 の差し替えと開示 (6)、タスク 0 (iv)、§2.7 の cwd、Status セルの予算、V9 の文字列と M1-m の箇所)。裁定は引き継ぎ書の「裁定」節。基点 local main `a1c1ee3` (契約 1.11.0)。Change Set Manifest 形式 (`docs/design/ROADMAP_POST_PHASE7_V1.md` (以下 `RM`) §9 の 9)。
- 台帳: `RM` §8 の R-41。**規模 M** (起票時の判定のまま。`docs/work-orders/OPERATING_CONDITIONS.md` (以下 `OC`) §1.13 の 73・74)。**変更クラス C** (`conformance-tests/` のみ。契約・`security/`・両 peer の `src/` に触れない。`RM` §9 の 8)。下限は `tools/change_class.py` で確かめる。
- 設計文書は持たない (規模 M は作業指示書 1 節)。枠は本書 §1。設計レビューは 1 回 (契約に触れない。`OC` §1.7 の 50)。
- 役割: 設計レビュー (テンプレ 4) 1 回、実装担当 (テンプレ 2) 1 回、コードレビュー (テンプレ 5、Class C) 1 回、受け入れ監査 (テンプレ 6。Class C なので起動) 1 回。commit・完了ゲート・merge・`COLLECTION_FLOOR`・台帳・引き継ぎ書は監督。
- 並行: R-101 (worktree `r101`) が `tools/perf_baseline.py` と `docs/design/PERF_*` を触る。本書はそれらに触れない (重なり 0)。

## 1. 監督確定事項

1. **規則の出所**: 契約 `spec/data-service-api.v1.json` の `destructive_confirmation` — `phrase_construction.rules` の 6 則 (以下 規則 1〜6: 導出入力の限定 / 決定性 / scope 込み / 再作成可能な対象の state fingerprint / identifier 検証済みの名前だけ / `confirmation.maxLength` 以内)、`valid_confirmation`、`evaluation_order`。文言は写さず、docstring は契約の節名で指す。
2. **足すベクトル** (`conformance-tests/test_c06_destructive_confirmation.py`、strict 分岐。`< 1.2.0` の基線分岐は V1〜V8 と同じく `_assert_baseline_delete_invariant` に落とす):
   - **V9** `test_c06_v9_phrase_is_independent_of_destructive_and_confirmation_values` (規則 1): 共有 entity への probe (destructive=True, confirmation=None) の phrase P に対し、(True, 短い ASCII 文字列 `"c06-v9-not-the-phrase"`)、(True, 別 entity の正しい phrase)、(False, P)、(False, None) の 4 要求の拒否がすべて `DESTRUCTIVE_CONFIRMATION_REQUIRED` で `required_confirmation == P`、行数不変。
   - **V10** `test_c06_v10_where_value_type_is_part_of_the_scope` (規則 3): 使い捨て entity (port の `create_entity_with_declared_types(session, entity, ["item_key", "tag"], {"item_key": "integer", "tag": "json"})` で作る。`create_entity` の型語彙は text / integer だけで `json` を受けない) に `tag` = `1` の行と `"1"` の行を入れ、`tag eq 1` と `tag eq "1"` の probe が両方 `DESTRUCTIVE_CONFIRMATION_REQUIRED` を得て phrase が異なる。互いの phrase を取り違えた要求は拒否、行数不変。
   - **V11** `test_c06_v11_phrase_fits_confirmation_max_length` (規則 6): 上限は `ROOT / "spec" / "data-service-api.v1.json"` の `definitions.Mutation.properties.confirmation.maxLength` から読む (`test_contract.py` と同じ読み方。`definitions.ScopedMutation`・`schemas.SchemaOperationRequest`・`schemas.CredentialRevokeRequest` の `properties.confirmation.maxLength` と一致することも assert する。literal 256 を書かない)。両 peer が受ける最長の entity 名 (63 文字。契約は identifier 長を束縛せず、63 は両 peer の方針の共通部分 — docstring に開示する) の使い捨て entity `{"item_key": "integer", "label": "text"}` への、`label eq <2,000 文字の文字列>` の delete probe、および `drop_entity` の probe (form が `"present"` のとき) の phrase 長が上限以内。
   - **V12** `test_c06_v12_delete_phrase_invalidated_by_add_field` (規則 4): 使い捨て entity に行を 1 件入れ、その行への delete の probe P1、再 probe == P1 (決定性の前提を先に置く。V6 の M-1 と同じ理由)、**同じ entity** への port の `add_field_with_declared_type` の後に P1 は拒否・行数不変、再 probe P2 != P1、P2 の echo で実行され `affected == 1`。別 entity への add_field は使わない (Application 全体の `schema_revision` は実装の選択であり、契約規則 4 の要求は同じ対象の schema 変更まで)。
   - **V13** `test_c06_v13_unvalidated_entity_name_is_refused_without_a_phrase` (規則 5): 契約 `structured_operations.identifier` の文法に違反する entity 名 (`"1c06_bad"` = 先頭が数字、`"c06-bad!name"` = 記号。大文字は契約上は正しいので使わない。URL 経路を壊す `/` は使わない) への delete (destructive=True, confirmation=None) が `VALIDATION_FAILED` か `IDENTIFIER_INVALID` で、`details.violated_declaration == "identifier_syntax"`、`required_confirmation` を持たず、`NOT_FOUND` でもなく、`assert_no_payload_echo_in_details` を通る。V13 が観測するのは「delete の entity 位置で identifier 構文の拒否が存在確認 (`NOT_FOUND`) より先に来ること」であり、規則 5 そのもの (未検証の名前の phrase への反射) は存在確認が confirmation より先に来るため構造的に破れない — docstring と開示範囲 (6) に書く。
3. **request_id からの独立 (台帳 (a))**: 契約は client が `request_id` を与える手段を定めず (`QueryResult.request_id` の記述)、port の `ConformanceDenial` は拒否の `request_id` を運ばない。独立性は「別々に発行した要求が同じ phrase を得る」形 (V4 と V9) でのみ観測でき、`request_id` の値そのものは比較しない。V9 の docstring と `CONDITIONS.md` の開示範囲 (5) に書く。port は改版しない。
4. **台帳 (b) の文言の裁定**: 台帳は「`VALIDATION_FAILED` になること」と書くが、契約は identifier 構文違反の拒否 code を `VALIDATION_FAILED` と `IDENTIFIER_INVALID` の 2 つ持ち (`errors.details_vocabulary.IDENTIFIER_INVALID`)、C-21 の D-3(6) が「MitateDB は `IDENTIFIER_INVALID` を出さない」と開示済みで、r2db は `identifier_syntax` を `IDENTIFIER_INVALID` で返す (`r2db-api/src/r2db_api/identifier_rules.py` の `validate_identifier`)。規則 5 の実体は「未検証の文字列を phrase に反射しない」なので、V13 は 2 code のどちらかと `identifier_syntax` を assert する。契約変更ではない。台帳の【追記】に記す。
5. **V10 の乗り物**: `json` は契約の field 型語彙の非型付け語 (r2db は `json` を宣言型なしとして扱う `r2db-api/src/r2db_api/structured.py` の `declared_types` 構築、MitateDB は canonical JSON text で格納)。着手時の実測 (タスク 0) で 6 plug が `tag eq 1` / `tag eq "1"` の両 probe に `DESTRUCTIVE_CONFIRMATION_REQUIRED` を返さない plug があれば、書く前に止めて監督に上げる (設計外の拡張 `OC` §1.5 の 37)。
6. **期待**: 30 node すべて緑。両 peer の delete phrase は既に `@schema_revision` と型付きの where digest を持つ (両 peer の `tests/test_foundation.py` の R-37 WP-2a のテスト)。赤になる plug があれば、是正は同一変更セットで行う (台帳行) が、その前に監督に上げる。
7. **記録**: `conformance-tests/CONDITIONS.md` の C-06 行 Status に V9〜V13 (test 名) と開示範囲 (5) (request_id の観測形)・(6) (V13 の観測形) を足す。Status セルは 3,000 文字以内 (`test_conditions_register.py` の `MAX_CELL_LENGTH`。上限は上げない。超える分は `CONDITIONS_HISTORY.md` の R-41 段落へ移す)。同じセルの古い記述「four adapters」「All 4 registered adapters」は 6 plug の現状に直す (監督裁定: 同じセルを編集するので同時に直す)。`CONDITIONS_HISTORY.md` の `## C-06` 末尾に R-41 の段落を足す (既存段落は触らない)。module docstring のベクトル一覧に V9〜V13 を足す。`security/CONTROL_MAPPING.md` は触らない (制御は変わらない。触れば Class D)。`COLLECTION_FLOOR` は監督が完了ゲートで上げる (4203 + 30 = 4233 の見込み)。
8. 1 WP、1 worktree (`.claude/worktrees/goofy-easley-1e390c`、branch `r41`)、1 commit、main へ 1 merge。

## 2. WP-1 — C-06 の V9〜V13 と記録

### 2.1 読むべき正本

- `spec/data-service-api.v1.json` の `destructive_confirmation` (規則の出所。`python -c` で該当 key を出す)。
- `conformance-tests/test_c06_destructive_confirmation.py` の module docstring、`fx`、`_probe_delete`、`_probe_drop_entity`、`_drop_entity_form_and_probe`、`_assert_delete_denied`、V3・V4・V6 (書き方の手本)。
- `conformance-tests/adapter.py` の `delete` / `drop_entity` / `create_entity` / `add_field_with_declared_type` / `insert` / `count` / `fresh_identifier` / `assert_no_payload_echo_in_details`。
- `conformance-tests/CONDITIONS.md` の C-06 行、`CONDITIONS_HISTORY.md` の `## C-06`、`conformance-tests/test_conditions_register.py`・`test_conformance_docstring_position_refs.py` (記録の検査器。docstring の `file:line` 参照は書かない。名前で指す)。

### 2.2 タスク

0. 着手時の実測 (書く前): 6 plug で (i) `json` field への `eq` probe が `DESTRUCTIVE_CONFIRMATION_REQUIRED` を返すか、(ii) 2,000 文字の where 値が受理されるか (拒否なら値長を下げ、実測値を報告に書く)、(iii) 構文違反 entity 名 2 つの拒否 code と `violated_declaration`、(iv) 63 文字の entity 名 (`fresh_identifier` の prefix を伸ばす) を作成できるか。`$SP/r41-task0.md` に plug × 結果の表で残す。§1 の 5・6 に当たる結果なら止めて報告する。
1. V9〜V13 を §1 の 2 のとおり足す。使い捨て entity は `fresh_identifier` で作り、共有 fixture の行は消さない (V5 が消す行に触れない)。各 test の docstring に規則番号と観測の形 (V9 は §1 の 3 の開示) を書く。
2. module docstring のベクトル一覧に V9〜V13 を足す。
3. `CONDITIONS.md` C-06 行と `CONDITIONS_HISTORY.md` `## C-06` を §1 の 7 のとおり更新する。
4. 変異 M1〜M5 (§2.6) を `tools/dev/mutate.py` で回す。すべて両 peer の `src/` への一時変異で、道具が復元する。
5. 報告: `pt.py` の集計行と `log=`、変異表、タスク 0 の表、`--collect-only -q` の前後の node 数。

### 2.3 触ってよいパス

`conformance-tests/test_c06_destructive_confirmation.py`、`conformance-tests/CONDITIONS.md`、`conformance-tests/CONDITIONS_HISTORY.md`。(`conformance-tests/COLLECTION_FLOOR` は監督。)

### 2.4 触らないパス

`spec/`、`security/`、両 peer の `src/`・`conformance/`・`tests/` (変異は道具の一時編集のみ)、`conformance-tests/adapter.py`、`tools/perf_baseline.py`、`docs/design/PERF_*`、`docs/design/ROADMAP_POST_PHASE7_V1.md`。

### 2.5 完了条件 (assert 水準)

1. V9 が 6 plug で緑、M1-r / M1-m で赤。
2. V10 が 6 plug で緑 (両 probe が phrase を得る = 空振りでない)、M2-r / M2-m で赤。
3. V11 が 6 plug で緑 (上限は契約から読み 4 箇所一致)、M3-r / M3-m で赤。
4. V12 が 6 plug で緑、M4-r / M4-m で赤。
5. V13 が 6 plug で緑 (2 つの名前とも)、M5-r / M5-m で赤。
6. C-06 file の node 数が着手前 + 30 (`--collect-only -q` の実測)。
7. `CONDITIONS.md` C-06 行が 5 つの test 名を backtick で挙げ、`test_conditions_register.py`・`test_conformance_docstring_position_refs.py`・`test_control_mapping_register.py` が緑。
8. `tools/tests -q` が緑 (基点 591)、`tools/check_doc_refs.py` が 0 dangling。
9. 本表 §2.6 に対応の無い行が無い。

### 2.6 完了条件番号 → 変異

各行 1 entry (`mutate.py` は最初の失敗で止まるので、1 変異 = 1 test = 1 entry)。test の引数は `conformance-tests/test_c06_destructive_confirmation.py -k "<test 名> and <peer>" -q`。

| 完了条件 | 変異 (`file:操作`) | 赤になる test |
|---|---|---|
| 1 | M1-r: `r2db-api/src/r2db_api/delete_confirmation.py` の `require_destructive_confirmation` が組む details の `required_confirmation` に提示された `confirmation` (None なら `"-"`) を連結する / M1-m: `MitateDB-api/src/mitatedb_api/cell.py` の `_validate_delete_confirmation` が組む `details["required_confirmation"]` に同様 | V9 (r2db 3 plug / MitateDB 3 plug) |
| 2 | M2-r: `r2db-api/src/r2db_api/delete_confirmation.py` の `_canonical_where_json` で value を `str(value)` にする / M2-m: `MitateDB-api/src/mitatedb_api/delete_confirmation.py` の同関数 | V10 |
| 3 | M3-r: r2db `delete_confirmation_phrase` の digest を `_canonical_where_json(where)` の生文字列に置き換え、長さ assert を外す / M3-m: MitateDB `_delete_confirmation_phrase` 同様 / RV1-r (コードレビューで追加): r2db `drop_entity_confirmation_phrase` で entity を 5 回連結し長さ assert を外す (drop_entity 側。form が `"present"` なのは r2db の 3 plug だけ) | V11 (delete 側 / drop_entity 側) |
| 4 | M4-r: r2db `delete_confirmation_phrase` の `schema_revision` を定数 0 にする / M4-m: MitateDB 同様 | V12 |
| 5 | M5-r: `r2db-api/src/r2db_api/structured.py` の transact 冒頭の `validate_identifier(entity, field="entity")` (と `postgres.py` に同じ検査があればそれも) を外す → 構文違反の名前が存在確認の `NOT_FOUND` に落ちる / M5-m: `MitateDB-api/src/mitatedb_api/cell.py` の `_validate_delete_confirmation` (delete 経路) の `self._identifier(collection, …)` を素通しにする | V13 (`identifier_syntax` の assert / `NOT_FOUND` でない assert) |
| 6 | 監査照合: `--collect-only -q` の前後の実測 (§5) | — |
| 7 | M7: `CONDITIONS.md` C-06 行の V9 の test 名を存在しない名前にする | `test_conditions_register.py` |
| 8 | 監査照合: `tools/tests` と `check_doc_refs` の出力行 (§5) | — |
| 9 | 監査照合: 本表 | — |

### 2.7 道具の引数

cwd は担当 worktree (`<repo>/.claude/worktrees/goofy-easley-1e390c`)。`-C` は省略 (既定はカレント)。interpreter は main checkout の `.venv` (`PY=<main checkout>/.venv/bin/python`)。検査器は worktree 側の copy を実行する。

```
export SP=<scratchpad>; PY=<main checkout>/.venv/bin/python
$PY tools/dev/pt.py -- conformance-tests/test_c06_destructive_confirmation.py -q -rxX -n 2
$PY tools/dev/pt.py -- conformance-tests/test_c06_destructive_confirmation.py --collect-only -q
$PY tools/dev/pt.py -- conformance-tests/test_conditions_register.py conformance-tests/test_conformance_docstring_position_refs.py conformance-tests/test_control_mapping_register.py -q
$PY tools/dev/pt.py -- tools/tests -q
$PY tools/dev/mutate.py "$SP/r41-mutations.json"
$PY tools/check_doc_refs.py
```

集計行の期待形: C-06 file `pt: N passed` (N = 着手前 + 30、failed 0、xfail 0)、変異表 10 件 (M1〜M5 × r/m) + M7 + RV1-r すべて `as expected`。

### 2.8 禁止事項

suite 全体を回さない。`gate.py` / `finalize.py` / commit / merge を実行しない。下請け Agent を使わない。port (`adapter.py`) と両 peer を編集しない (変異は道具経由の一時編集のみ)。docstring に `file:line` を書かない。skip / xfail を足さない。

## 3. merge (監督)

コードレビュー (テンプレ 5) → 完了ゲート `tools/dev/gate.py -C .claude/worktrees/goofy-easley-1e390c --label r41` → `COLLECTION_FLOOR` を実測値に → 受け入れ監査 (テンプレ 6) → `RM` R-41 行【追記】と版上げ (merge 時に他チャットと衝突すれば renumber) → 引き継ぎ書 → `tools/dev/finalize.py -C .claude/worktrees/goofy-easley-1e390c --branch r41 --allow 'conformance-tests/*' --allow 'docs/*' --tools-tests`。push はしない。

## 4. 訂正註

1. **M5-m の変異箇所 (実装担当の報告、2026-09-26)**: §2.6 の指定 (`cell.py` の `_validate_delete_confirmation` の `self._identifier(collection, …)` を素通し) では V13 が赤にならない (実測 3 passed のまま)。MitateDB の delete 経路は `backend_sqlite.py` / `backend_postgres.py` の field_domains が同じ `identifiers.validate_identifier` を独立に呼ぶ多重防御で、単一の choke point ではない。M5-m は `MitateDB-api/src/mitatedb_api/identifiers.py` の `validate_identifier` 本体を素通しにする変異に差し替えた (delete 経路の 3 箇所が共通に呼ぶ 1 関数。呼び出し元は全体では約 24 箇所あり、この変異が見るのは検証の欠落であって検証と存在確認の順序ではない — コードレビュー観察 O1)。監督受理。
2. **完了条件 7 の register 3 file 単独実行**: `test_conditions_register.py` は conformance-tests 全体の marker を集めて照合するため、3 file 単独では HEAD (無変更) でも同一 3 件が赤になる (L7-23 の設計)。C-06 を含む拡張実行で C-06 起因の欠陥は無いことを確認。緑の判定は監督の完了ゲート (root suite) で行う。

## 5. 実施記録

- タスク 0 (着手時の実測、6 plug): (i) `json` field への `tag eq 1` / `tag eq "1"` の probe は両方 `DESTRUCTIVE_CONFIRMATION_REQUIRED`、(ii) 2,000 文字の where 値は受理、(iii) `"1c06_bad"` / `"c06-bad!name"` は r2db 3 plug が `IDENTIFIER_INVALID`、MitateDB 3 plug が `VALIDATION_FAILED`、いずれも `identifier_syntax`、(iv) 63 文字の entity は 6 plug で作成できる (実装担当の表、scratchpad `r41-task0.md`)。§1 の 5・6 の停止条件に該当なし。
- C-06 file: `pt: 99 passed` (`-n 2`。着手前 `--collect-only -q` 69 node → 99 node、+30 = 完了条件 6)。差し戻し後も `pt: 99 passed`、監査観察 O-1 の追記後も `pt: 99 passed in 74.77s`。
- register 3 file + docstring refs: 単独実行は `1 failed, 148 passed` (`test_every_executable_condition_has_a_marked_test` — conformance-tests 全体を集めないと marker 0 件で赤になる既知の性質。§4 の 2)。完了ゲート (root suite) で緑。
- `tools/tests -q`: `pt: 591 passed in 57.53s` (基点と同数)。`tools/check_doc_refs.py`: `OK: 0 dangling references`。`public_value_scan` (conformance-tests 3 file): `total_flagged=0`。
- 変異: `mutate: 11 mutations, 11 as expected, restores verified 7/7` (M1-r/M1-m … M5-r/M5-m、M7)。コードレビュー RV1-r (drop_entity 側): `1 failed, 96 deselected`、`1 as expected`。受け入れ監査 AU-1-r / AU-1-m (両 peer の identifier 正規表現に `!` と `-` を足す): `2 as expected` (赤の理由は `NOT_FOUND` への転落)。両 peer の `src` は各実行後 clean。
- 変更クラス: `tools/change_class.py` → C (conformance-tests + docs)。性能差分 (`OC` §1.3 の 27) は付けない (両 peer の src に触れない Class C)。
- 完了ゲート (監督、solo、使い捨てクラスタ): 1 回目 label r41 (監査前の tree): `gate: 4233 passed, 2 subtests passed in 996.30s (0:16:36)`、judge=PASS、pg_database/pg_roles diff 0 (4203 + 30)。2 回目 label r41b (監査観察 O-1 反映後の最終 tree): `gate: 4233 passed, 2 subtests passed in 492.02s (0:08:12)、judge=PASS、pg_database/pg_roles diff 0`。`COLLECTION_FLOOR` 4198 → 4233。
- 受け入れ監査 (opus): 完了条件 20 項目中 充足 19 / 未充足 1 (本 §5 が空だったこと。本記入で解消) / 証拠不足 0 / 該当なし 1 (§1.5 の 35・36。依頼者確定文言なし)。観察 O-1 は同一変更セットで直した (V10 の取り違え 2 脚が code と 4 宣言を assert)、O-2 (1 回目のゲート 996 s と stderr の `KeyboardInterrupt` warning 1 件。件数・判定は一致) は観察。設計疑義 (契約規則 4 の "any other schema change" の範囲) は観察。
