# 作業指示書 — R-37 WP-0 inventory と WP-1 の Change Set Manifest

## 0. 版数・位置づけ

- **v1.23 (2026-09-16)。** §5.46 の冒頭に依頼者指示 `docs/work-orders/REQUESTER_DIRECTIVE_20260916_R37_CLOSURE_R45_PRIORITY.md` への参照を 1 行足した (本文は書き換えていない)。WP-5 は (3)(4)(6) だけを行い、R-37 を閉じた (設計 §10.19)。
- **v1.22 (2026-09-16)。** 基点 `abcb2b6` (実測 A〜F の基点は `2ed3a3d`。間の変更は文書・`MitateDB-api/docs/f9-execution-assets-v1/`・`tools/public_value_scan.py` だけ)。R-37 の最後の WP である WP-5 (facade 縮小と閉止) の manifest を **§5.46** として足した。枠は引き継ぎ書 `docs/work-orders/HANDOVER_20260916_FABLE2.md` 付録 B (裁定 Z5-1〜Z5-8)。起草時の疑義への監督裁定 **Z5-9〜Z5-14** (第 2 次) を §5.46 に逐語で置き、完了条件と変異の表をそれに合わせた。続いて設計レビューへの監督裁定 **Z5-15〜Z5-21** (第 3 次) を同じく逐語で置き (Z5-9 の例の訂正、Z5-10 の許可規則と絞り込みを覆す)、本文と表を振り直した。既存の版数行・§5.45 までの本文・訂正註 1〜8 はいずれも書き換えていない (§1.8 の 56・57)。**独立設計レビュー待ち。**
- **v1.21 (2026-09-16)。** 基点 `fdaf9e8` (WP-4c を統合済み)。WP-4c の実施と独立コードレビューで判明した 7 件を **訂正註 8 (8-1〜8-7)** として §5.45 の末尾に足した。**7 件はいずれも WP-5 (facade 縮小と閉止) に掛かる。**§5.43・§5.44・統合後の manifest の本文・表・完了条件と、既存の版数行・訂正註 1〜7 はいずれも書き換えていない (§1.8 の 56・57)。設計側の記録は `docs/design/MODULE_REFACT_ARCHITECTURE_V1.md` (v1.21) §10.18。
- **v1.20 (2026-09-16)。** 基点 `2e94bbf` (WP-4b を統合済み)。WP-4b の実施で判明した 2 件を **訂正註 6・7** として §5.45 の末尾に足した (閉語彙外・例外経路の条件の強化、0f の読み方の非対称)。どちらも **WP-4c に掛かる**。§5.42 の本文・表・完了条件と既存の版数行・訂正註はいずれも書き換えていない (§1.8 の 56・57)。設計側の記録は `docs/design/MODULE_REFACT_ARCHITECTURE_V1.md` (v1.20) §10.17。
- **v1.19 (2026-09-16)。** 基点 `bec2eeb` (WP-4a とその記録を統合済み)。依頼者裁定により §5.43 (WP-4c) と §5.44 (WP-4d) を 1 つの WP (呼称 **WP-4c**) として実施する訂正註を §5.45 の末尾に足した。§5.43・§5.44 の本文、Z4-2 の行、既存の版数行はいずれも書き換えていない (§1.8 の 56・57)。
- **v1.18 (2026-09-16)。** 基点 `acb257e` (WP-4a を統合済み)。WP-4a の実装中の監督裁定 W4-4 (第 4 次) と、独立コードレビュー由来の訂正註 4 件、WP-5 候補 1 件を §5.45 に足した。既存の行は書き換えていない。設計側の記録は `docs/design/MODULE_REFACT_ARCHITECTURE_V1.md` (v1.19) §10.16。
- **v1.17 (2026-09-16)。** 基点 `ba98255` (R-37 WP-3 完了、R-44 WP-1 統合済み)。§5.40〜§5.45 を追記した。内容は、WP-4 (PG1・PG3・PG2 と BP3) の実測、監督裁定 Z4-1〜Z4-8、4 件の manifest (WP-4a〜4d)、第 2 次・第 3 次の監督裁定、PG4 を範囲外とした根拠の記録である。既存の行は書き換えていない。独立レビュー反映: A-1〜A-3、B-1〜B-3、C-1〜C-10 (全 16 件を採用)。**独立レビュー反映済み。**
- **v1.16 (2026-09-16)。** 基点 `a48cfa1` (WP-3h を統合済み)。WP-3i の実装中の監督裁定 W3-23 を §5.39 の裁定表に足し、§5.38 に訂正註を足した。既存の行は書き換えていない。
- **v1.15 (2026-09-16)。** 基点 `ffd6493` (WP-3g と R-22 変更セット 0i を統合済み)。WP-3h の実装中の監督裁定 W3-21・W3-22 を §5.39 の裁定表に足し、§5.37 に訂正註を足した。既存の行は書き換えていない。
- **v1.14 (2026-09-16)。** 基点 `bdea9ee` (WP-3f を統合済み)。WP-3g の実装中の監督裁定 W3-19・W3-20 を §5.39 の裁定表に足し、§5.36 に訂正註を足した。既存の行は書き換えていない。
- **v1.13 (2026-09-15)。** 基点 `b4aac70` (WP-3e を統合済み)。WP-3f の実装中の監督裁定 W3-17・W3-18 を §5.39 の裁定表に足し、§5.35 に訂正註を足した。既存の行は書き換えていない。
- **v1.12 (2026-09-15)。** 基点 main `b65e97d` (WP-3d を統合済み)。WP-3e の実装中の監督裁定 W3-15・W3-16 を §5.39 の裁定表に足し、§5.34 に訂正註を足した。既存の行は書き換えていない。
- **v1.11 (2026-09-15)。** 基点 main `9994d7c` (WP-3a〜3c を統合済み)。§5.32〜§5.39 を追記した。内容は、WP-3d〜3i (ST10 → CE5 → ST8 → ST9 → CE7 → CE6) の実測、監督の枠 WF-1〜WF-7、manifest、未確定 W3-6〜W3-13 である。既存の行は書き換えていない。独立レビュー反映: M1〜M5、minor、監督裁定 U1〜U5 (§5.32〜§5.39)。**独立レビュー反映済み。**
- **v1.10 (2026-09-15)。** 基点 main `b45312d` (WP-2a を統合済み)。§5.27〜§5.31 に WP-3 (SV1〜SV3) の実測、WP-3a / 3b / 3c の manifest、未確定 W3-1〜W3-5 を追記した。既存の行は書き換えていない。独立レビュー (差し戻し) 反映: facade テスト、訂正の記録の赤テスト、評価順の変異、W3-4、範囲外の位置参照、CH-0126 の扱い。**独立レビュー待ち。**
- **v1.9 (2026-09-15)。** 基点 main `13241c2` (WP-1m・1n・1k を統合済み)。§5.25・§5.26 に WP-2a (Y-6・Y-8、削除確認 phrase の契約規則のテスト) の manifest と未確定 Z-1〜Z-3 を追記した。既存の行は書き換えていない。独立レビュー (差し戻し) 反映: Z-2・Z-3 の裁定、型区別の assert、規則 5 と R-41 の注記。**独立レビュー待ち。**
- **v1.8 (2026-09-15)。** 基点 main `f70afb0` (WP-1j・1l と記録を統合済み)。§5.20〜§5.24 に WP-1m / 1n (BP1、BP2) の manifest、WP-2 (CE1) の判断材料、未確定 Y-1〜Y-6 を追記した。既存の行は書き換えていない。独立レビュー (軽微な差し戻し) 反映: 監督裁定 Y-7〜Y-9、1n の変異 6、S_M の監査照合の範囲、§5.23 の事実。**独立レビュー待ち。**
- **v1.7 (2026-09-14)。** 基点 main `2fde59a` (WP-1g / 1h / 1i 統合済み。worktree `r37-wp0` の `dad3c35` と同一 tree)。§5.15〜§5.19 に WP-1j / 1k / 1l (CE3 → CE4 → BP4) の manifest と未確定 X-1〜X-4 を追記した。既存の行は書き換えていない。独立レビュー反映: 監督裁定 X-1〜X-5 (§5.19)、1k の括弧書きと順序、1l の allowlist 実測値。**独立レビュー済み。**
- **v1.6 (2026-09-14)。** W-1〜W-3 と既知の穴の追跡先への監督裁定を反映した (§5.11 の 14、§5.13 の追加行・23・24、§5.14 の裁定表)。独立レビューの指摘 (監督裁定) も反映した。v1.5 以降の未コミット分だけを直し、それ以前の行は書き換えていない。
- **v1.5 (2026-09-14)。** 基点 main `4fc5517` (WP-1d / 1e / 1f 統合済み)。§6 に U-2 の追記行 (r2db `service.py` は変更セット 2 が先)、§5.10〜§5.14 に WP-1g / 1h / 1i の manifest を追記した。既存の行は書き換えていない。**独立レビュー待ち。**
- **v1.4 (2026-09-14)。** 独立レビューの minor 5 件 (監督裁定、全件採用) を §5.5〜§5.9 に反映した: 共通の完了条件 C-1〜C-3 を §5.5 へ集約、§5.6 の変異 3b・5b と位置参照、§5.7 の `__future__` 必須と既知の穴、§5.9 の未確定表を削除して裁定表だけ残した。
- **v1.3 (2026-09-14)。** 基点 `fbf45cb` (対象ファイルは main `944e86b` と同一)。v1.2 からの変更: WP-1 後続 3 件 (CE2、ST3、ST4) の manifest、重なり、未確定点を §5.5〜§5.9 に追記した。既存の行は書き換えていない (§5 見出しの「4 件」と §5 共通表の「順序」は v1.2 時点の記述)。**独立レビュー待ち。**
- **v1.2 (2026-09-14)。** 基点 main `a0e2a82`。v1.1 からの変更: 独立レビューの指摘 (M1、M2、m1〜m8) と U-3・m5 への監督裁定 (同日) を反映した (§6)。
- v1.1 (2026-09-14): §6 の未確定 U-1〜U-6 に監督裁定を反映し、§1〜§5 を追随させた。
- v1.0 (2026-09-14): 起草。
- 正本設計: `docs/design/MODULE_REFACT_ARCHITECTURE_V1.md` (**v1.4**、以下「設計」)。本書は設計 §4 WP-0 の inventory と、§7 の着手条件のうち「対象 test baseline」「変更 path manifest」「roadmap §9 の 9 の Change Set Manifest」を満たすための文書である。独立レビュー (v1.1 に対して) の指摘は本版で反映した。
- 設計の表・裁定・背景は写さず節番号で指す。**設計と食い違ったら設計が正。** 訂正は本文を書き換えず註で足す。
- WP-0 はコードを動かさない (設計 §4)。本書の実測はすべて `--collect-only` と静的走査による。
- R-32 は閉じた (`_gate` の検証用分岐は除去済み) ので、設計 §9.3 の WP-3 前提条件は満たされている。`_gate` 又はその呼出し経路を触る候補は WP-3 に置く。

## 1. baseline (実測 2026-09-14、`a0e2a82`)

| 項目 | 値 |
|---|---|
| root collection | **3,341** (`COLLECTION_FLOOR` 3,326。設計 §5.3 により WP 中は据え置き) |
| 内訳 | `r2db-api/tests` 1,257 / `MitateDB-api/tests` 1,089 / `conformance-tests` 995 |
| `tools/tests` (root の testpaths の外) | **107** (`$PY -m pytest --collect-only -q -p no:cacheprovider tools/tests`) |
| `$PY` | main checkout の venv の python (`<main checkout>/.venv/bin/python`)。実パスは公開ゲート `public_value_scan` の R6 と設計 §6 により書かない |
| node id 一覧の sha256 (先頭 16 桁) | `9c139c3df7eca740` |
| 取得コマンド | `$PY -m pytest --collect-only -q -p no:cacheprovider \| grep '::' \| sort \| shasum -a 256` |

完了ゲートでは同じコマンドで一覧を取り (`tools/tests` も)、差分が「その WP の新規テストだけ」であることを確認する。

**対象 module の固定値テスト** (実測):

| module | 行 | L1 scan | 件数 pin | 行番号 allowlist | 文字列・getsource 検査 | 登録 helper | 経緯塊 ※ | コメント整理 |
|---|---|---|---|---|---|---|---|---|
| MitateDB `cell.py` | 4,660 | 対象 | 49 | 0 | `test_application_audit.py:1101-1103` (`read_text` の `count ==`) | 4 | 102 / 2,393 行 | 抽出の後 (ファイル単位) |
| r2db `structured.py` | 3,238 | 対象 | 93 | 0 | なし | 6 | 54 / 856 行 | 抽出の後 (ファイル単位) |
| r2db `postgres.py` | 2,929 | 対象 | module 別 pin なし | 1 (`1706`) | `test_threadpool_offload.py:487` (`_RolePool._acquire` の getsource→AST) | 0 | 41 / 812 行 | **変更セット 1 (抽出より先)** |
| r2db `service.py` | 1,876 | 対象 | 10 | 0 | `test_threadpool_offload.py:450`、`:469` (`DataService._slot` / `_acquire_rate` の getsource→AST) | 0 | 33 / 757 行 | 未定 |
| MitateDB `backend_postgres.py` | 2,046 | 対象 | 24 | 20 (`563`〜`1986`) | なし | 0 | 35 / 811 行 | 抽出の後 (ファイル単位) |

※ 10 行以上の連続 `#` 塊又は docstring で、`WP-` / `Phase N` / `R-N` / `review` / `round` / 日付 / `M-N` / `m-N` / 追補 のいずれかを含むもの。`docs/work-orders/WORK_ORDER_CODE_COMMENT_PROVENANCE_CS1.md` (branch `ccp-cs0`) §2.1 の実測とは方法が違い件数は一致しない。本書では「要否」の判定にだけ使う。

## 2. module ごとの inventory

**凡例**: 分類 = 設計 §3 (P 純粋 / E 明示の依存を渡せば純粋 / S 副作用境界 → §3)。副作用 = 読取・書込 (「raise」は例外送出だけ)。pin = 固定値テストへの影響 (count ±n = L1 件数 pin、scan = 移動先を `SCANNED_MODULES` に追加、allow n = 行番号 allowlist の行送り n 件、text = 文字列検査)。同型 = `_ISOMORPHIC_TARGETS` 登録の要否。整理 = 範囲内の経緯塊 (件 / 行)。変更クラスは登録 helper 以外すべて **B** (roadmap §9 の 8)。sib = `test_backend_layer_allowlist_entries_have_no_in_memory_sibling_denial` の固定 module 集合 (r2db `structured.py`、MitateDB `cell.py`・`field_types.py`・`http.py`・`identifiers.py`) を同じ変更で更新する。移動先パスと module 名は本書のとおり (U-3)。

### 2.1 r2db `r2db-api/src/r2db_api/structured.py`

| ID | 候補 | 行範囲 (行数) | 直近の呼出し元 | 副作用 | leaf の import | 既存テスト | SI | 分類 | 抽出後 | facade に残す | 同型 | pin | 整理 | WP |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ST1 | `_float8out_text` `_jsonb_numeric_text` `_jsonb_scalar_text` `_jsonb_text` | L3061-3150 (90) | `_predicate_text` (同 module) | なし | `json` `decimal` `typing` | 間接: `test_foundation.py` の contains/matches 群 | SI-05 | P | `r2db_api/pg_text_format.py` | 4 名 | 不要 (MitateDB に同名 def 無し) | なし | 要 3 / 48 | **1a** |
| ST2 | `_JSON_TYPE_RANK` `_sort_key` `_sort_rows` | L1592-1597、L1634-1664 (37) | `ApplicationCell.query` (L2094) | なし | `json` `typing` | `test_foundation.py` の order_by 群 | SI-05 | P | `r2db_api/inmemory_sort.py` | 3 名 | 不要 (同上) | なし | 要 1 / 10 | **1c** |
| ST3 | `_wildcard_pattern` `_predicate_text` `_matches` | L3027-3058、L3153-3238 (118) | `ApplicationCell.query` / `_transact_locked` | raise | `re` `errors` ST1 | `test_foundation.py` contains/matches | SI-05 | P | `r2db_api/inmemory_predicate.py` (ST1 と共有しない。U-6) | 3 名 | 不要 | count −1、scan、sib | 要 3 / 52 | 1 後続 |
| ST4 | `IDENTIFIER` `MAX_IDENTIFIER_LENGTH` `_RESERVED_PREFIX` `_RESERVED_ENTITY_NAMES` `validate_identifier` `_reject_reserved_*` (3) | L20-97 (78) | postgres / service / control_plane / credential_store / ops / platform_declarations ほか | raise | `re` `errors` | `test_l5_si10_details_leak_scan.py`、`test_postgres.py` | SI-04、SI-05 | P | `r2db_api/identifier_rules.py` | 7 名 | 不要 | count −4、scan、sib | 要 2 / 22 | 1 後続 (ST5・ST7 の前提) |
| ST5 | `_PHRASE_MAX_LENGTH` `_MAX_REVISION_DIGITS` `_canonical_where_json` `_where_digest16` `*_confirmation_phrase` (5) `RESET_CONTROL_CREDENTIALS` `require_destructive_confirmation` | L363-604 (242) | postgres / control_plane / ops / auth | raise (語彙外 code) | `hashlib` `json` `errors` + `MAX_IDENTIFIER_LENGTH` | `test_foundation.py`、`test_dry_run_and_plan.py`、`test_control_plane_store.py`、`test_credential_persistence.py` | SI-09 | P | `r2db_api/delete_confirmation.py` | 11 名 | 不要 (WP-2 で MitateDB `_canonical_where_json` と比較) | sib | 要 6 / 123 | 1 後続 (ST4 の後 — §4) |
| ST6 | `_INT64_MIN/MAX` `_declared_type_label` `_check_type` `_validate_wildcard_pattern` `_validate_predicate_types` | L1380-1566 (187) | postgres (7 参照) / `_fail_constraint_declaration` | raise | `errors` `value_nul` + `_TEXT_ONLY_OPERATORS` | `test_foundation.py`、`test_postgres.py` | SI-05、SI-10 | P | `r2db_api/value_types.py` | 6 名 | 不要 | count −11、scan、sib | 要 3 / 56 | 1 後続 |
| ST7 | `MAX_PAGE_SIZE` `validate_page_size` `MAX_ORDER_BY_FIELDS` `MAX_CURSOR_OFFSET` `_resolve_order_by` `_shape_hash` `_encode_cursor` `_decode_cursor` | L1578-1631、L1667-1710 (98) | postgres / http / ApplicationCell | raise | `base64` `hashlib` `json` `errors` + ST4 | `test_foundation.py` order_by、`test_http.py` | SI-05、SI-08 | E (`ResourceLimits` を引数で受ける) | `r2db_api/paging.py` | 8 名 | 不要 | count −10、scan、sib | 不要 | 1 後続 (ST4 の後) |
| ST8 | `_mapping` `parse_predicate` `Predicate` `validate_projection` `validate_predicates` `MUTATION_OPERATIONS` `_MUTATION_KEYS` `MAX_EXPECTED_REVISION_LENGTH` `BoundMutation` `bind_mutation` | L100-340 (241) | service / control_plane / postgres / adapter | raise | `errors` + ST4 | `test_foundation.py`、`test_denial_details_and_request_id.py` | SI-05 | P | `r2db_api/mutation_binding.py` | 10 名 | 不要 | count −18、scan、sib | 要 5 / 80 | 3 |
| ST9 | `FIELD_TYPES` `MAX_INDEX_FIELDS` `SCHEMA_OPERATIONS` `_SCHEMA_KEYS` `FieldConstraints` `ConstraintPatch` `_ENUM_ELIGIBLE_TYPES` `_ConstraintDeclarationError` `_fail_constraint_declaration` `BoundSchemaOperation` `bind_schema_operation` | L619-729、L754-766、L812-1273 (約 590) | postgres (7 参照) / adapter | raise (L879 の `FORBIDDEN` を含む) | `errors` + ST4、ST6 | `test_foundation.py`、`test_postgres.py`、`test_http.py` | SI-03、SI-05 | E — **binding の境界であり DDL builder ではない** (設計 §4 WP-0)。developer gate は facade に残す | `r2db_api/schema_binding.py` | 11 名 | 不要 (登録 enum helper は動かさない) | count −37、scan、sib | 要 8 / 126 | 3 |
| ST10 | `QueryOutcome` `MutationOutcome` `SchemaOutcome` | L1292-1370、L1880-1920 | service / backend / http / postgres | なし | `dataclasses` | 間接 | SI-10 | P (型) | WP-3 の binding leaf | 3 名 | 不要 | なし | 要 5 / 67 | 3 (U-4) |
| — | `validate_enum_declaration` `enum_member_matches_type` `normalize_request_for_plan` `compute_plan_token` `normalize_request_for_idempotency` `idempotency_digest` | L732-751、L769-809、L1722-1837 | — | — | — | `test_audit_query.py` 同型性 | — | — | **候補外**: 登録済み (Class C)。移動は登録行の差替えになり設計 §6 が禁じる | — | 登録済み | — | — | — |

### 2.2 MitateDB `MitateDB-api/src/mitatedb_api/cell.py`

| ID | 候補 | 行範囲 (行数) | 直近の呼出し元 | 副作用 | leaf の import | 既存テスト | SI | 分類 | 抽出後 | facade に残す | 同型 | pin | 整理 | WP |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| CE1 | `_canonical_where_json` `_delete_confirmation_phrase` | L351-375、L574-613 (65) | `ApplicationCell._validate_delete_confirmation` (L2674) | なし | `hashlib` `json` | `test_foundation.py` 直接 2 件、`test_idempotency_records.py` / `test_idempotency_concurrency.py` / `test_application_audit.py` (phrase 生成) | SI-09 | P | `mitatedb_api/delete_confirmation.py` | 2 名 | 不要 (r2db `structured._canonical_where_json` は同名。登録の判断は WP-2) | text: 検査対象の 2 文字列を含まない (影響 0) | 要 2 / 57 | **1b** |
| CE2 | `_measure_request_bytes` `_check_operation_depth` | L623-724 (100) | `_limit_gate` (L1048-1049)、`http.py`、adapter | raise | `errors` `request_traversal` | `test_application_plane_limits.py`、`test_limit_class_vocabulary.py`、conformance C05 (コメント参照) | SI-08 | P | `mitatedb_api/request_limits.py` | 2 名 | 不要 | count −2、scan、sib | 不要 | 1 後続 (次点) |
| CE3 | `_validate_enum_declaration_with_path` `_resolve_field_constraints` | L162-268 (105) | create_collection / add_field / alter_field | raise | `errors` `field_types` | `test_limit_class_vocabulary.py`、`test_constraints_declaration.py` | SI-05、SI-08 | E (`max_enum_members` を引数) | `mitatedb_api/constraint_resolution.py` | 2 名 | 不要 | count −3、scan、sib | 要 2 / 44 | 1 後続 |
| CE4 | `_deny_provisional_field` | L3999-4026 (28) | `http.py` | raise | `errors` | 間接 | SI-05 | P | CE3 と同じ leaf か別か (実装前に確定) | 1 名 | 不要 | count −1、scan、sib | 要 1 / 23 | 1 後続 |
| CE5 | 定数群 `_CONTRACT_MUTATION_VOCABULARY` `_TRANSACT_*_KEYS` (3) `_FIELD_TYPE_VOCABULARY` `_UNSUPPORTED_CONTRACT_OPERATORS` `_DELETE_CONSEQUENCE` | L97-331 (散在) | ApplicationCell / `http.py` / `backend.py` / adapter | なし | — | `test_http.py`、`test_denial_details_and_request_id.py` | SI-05 | P | WP-3 の binding leaf | 7 名 | 不要 | なし | 要 5 / 約 150 | 3 |
| CE6 | binding method 群 `_bind_order_by` `_bind_filters` `_prepare_values` `_check_missing_required_fields` `_check_predicate_value` `_normalize_value` `_normalize_value_for_storage` `_select_fields` `_decode_rows` `_validate_update` | L2485-2541、L3402-3932 (約 590) | 各操作 (`_gate` 通過後) | raise + self 読取 | 未確定 | `test_foundation.py`、`test_denial_details_and_request_id.py` | SI-05 | E (self の状態を引数化) | `mitatedb_api/request_binding.py` | method は委譲で残す | 不要 | count 多数 (WP-3 manifest で実測)、scan | 要 | 3 |
| CE7 | `_surfaces_document_fragment`、`ApplicationRuntime.__build_capabilities_document` | L339-348、L4193-4555 (373) | `ApplicationRuntime.capabilities` | self 読取 (config / limits) | `surfaces` | 間接 (capabilities) | — | E | 未定 | 1 名 + method | 不要 | なし | 要 | 3 |
| — | `normalize_request_for_plan` `compute_plan_token` `normalize_request_for_idempotency` `idempotency_digest` | L378-473 | — | — | — | 同型性 | — | — | **候補外** (登録済み、設計 §6) | — | 登録済み | — | — | — |

### 2.3 r2db `r2db-api/src/r2db_api/postgres.py` (コメント整理の変更セット 1 を先に行う。U-2)

| ID | 候補 | 行範囲 (行数) | 直近の呼出し元 | 副作用 | leaf の import | 既存テスト | SI | 分類 | 抽出後 | facade に残す | 同型 | pin | 整理 | WP |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| PG1 | `_DOMAIN_TO_DECLARED` `_SQL_TYPE_TO_DECLARED` `_TableInfo` | L229-306 (78) | `_describe_table` / `_load_catalog` | なし | `dataclasses` | `test_postgres.py` (PG) | SI-05 | P | 既存 `r2db_api/postgres_types.py` へ追加 | 3 名 | 不要 | allow 1 (`1706` の行送り) | 要 1 / 20 | 4 (変更セット 1 の後。U-2) |
| PG2 | `_COMPARISON_OPERATORS` + `_where_clause` `_text_expression` `_predicate_sql` | L262-269、L2051-2140 (98) | query / `_apply` / `_update` / `_delete` | なし | `psycopg.sql` `postgres_like` | `test_postgres.py`、静的安全性テスト | SI-04、SI-05 | E (method → 関数。D-4) | `r2db_api/postgres_predicates.py` | method は委譲で残す | 不要 | scan 対象の denial 2 件 (`2101`、`2139`) が移る | 要 1 / 20 | 4 (変更セット 1 の後。U-2) |
| PG3 | `_select_statement` `_order_by_sql` `_append_revision_predicate` | L1413-1447、L1800-1825 (61) | query / `_update` / `_delete` | なし | `psycopg.sql` | `test_postgres.py` | SI-04 | E (D-4) | PG2 と同じ leaf | 同上 | 不要 | allow 1 (L1413-1447 は `1706` より前) | 要 2 / 32 | 4 (変更セット 1 の後。U-2) |
| PG4 | `apply_schema` 内の DDL 組立 | L2144-2631 (488) の一部 | `apply_schema` | 実行と混在 | — | `test_postgres.py` | SI-04、SI-11 | 未確定 (lock・transaction と同じ本体) | 未定 | — | 不要 | 未測定 | 要 | 4 (範囲は WP-4 manifest で実測) |

### 2.4 r2db `r2db-api/src/r2db_api/service.py`

| ID | 候補 | 行範囲 (行数) | 直近の呼出し元 | 副作用 | leaf の import | 既存テスト | SI | 分類 | 抽出後 | facade に残す | 同型 | pin | 整理 | WP |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SV1 | `QueryPage` `MutationResult` | L147-207 (61) | `http.py`、adapter | なし | `dataclasses` | `test_http.py`、conformance C11 / C25 (型名) | SI-10 | P (型) | `r2db_api/service_results.py` | 2 名 | 不要 | なし | 要 1 / 29 | 3 (U-4) |
| SV2 | `DataService.capabilities` | L926-1099 (174) | `http.py` | self 読取 (limits / topology) | 未確定 | `test_foundation.py` capability 群 | — | E | 未定 | method は委譲で残す | 不要 | なし | 要 6 / 100 | 3 |
| SV3 | `_query_outcome` / `_mutate_outcome` の binding 部分 | L1142-1350 の一部 | `query_page` / `mutate_result` | idempotency・audit と混在 | — | `test_application_audit.py` ほか | SI-05 | 未確定 | 未定 | — | 不要 | count −n (L1147〜1245 の 6 件のうち該当分) | 要 | 3 (範囲は WP-3 manifest で実測) |

### 2.5 MitateDB `MitateDB-api/src/mitatedb_api/backend_postgres.py` (抽出を先に行い、コメント整理は後。U-2)

| ID | 候補 | 行範囲 (行数) | 直近の呼出し元 | 副作用 | leaf の import | 既存テスト | SI | 分類 | 抽出後 | facade に残す | 同型 | pin | 整理 | WP |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BP1 | `_TYPES` `_TYPE_SQL` `_DOMAIN_BY_DATA_TYPE` `_TEXT_DOMAIN_BY_DECLARED_TYPE` | L157-202 (46) | create_collection / add_field / `_validate_value_domain` (`cell.py`・`postgres_value_domain.py` はコメントでの参照) | なし | `psycopg.sql` `field_types` | `test_postgres.py` | SI-04、SI-05 | P | `mitatedb_api/postgres_types.py` | 4 名 | 不要 | allow 20 | 要 2 / 30 | 1 後続 又は 4 |
| BP2 | `_validate_value_domain` | L205-319 (115) | `encode_value` | raise | `errors` `postgres_value_domain` | `test_postgres.py` (17 参照)、`test_http.py`、`test_denial_details_and_request_id.py` | SI-05、SI-10 | P | 既存 `mitatedb_api/postgres_value_domain.py` へ追加 | 1 名 | 不要 | count −2 (+2 移動先)、allow 20 | 要 4 / 89 | 1 後続 |
| BP3 | `_OPERATOR_SQL` `_DIRECTION_SQL` + `_where_sql` | L325-326、L1339-1353 | insert / update / delete / read | なし | `psycopg.sql` | `test_postgres.py`、`test_order_by_direction_hardening.py` | SI-04 | E (method → 関数。D-4) | `mitatedb_api/postgres_sql.py` | 2 名 + 委譲 method | 不要 | allow 20 (定数 L325-326 の移動で全件) | 要 1 / 23 | 4 |
| BP4 | `_RESERVED_EXACT` `_RESERVED_PREFIX` + `check_reserved` | L137-138、L532-547 | `cell.py` の identifier choke point | raise | `errors` | `test_postgres.py` | SI-04 | E (self 使用は着手時に確認) | 未定 | 2 名 + method | 不要 | count −1、allow 20 | 要 | 1 後続 |

## 3. 除外した副作用境界 (設計 §3.2。候補にしない)

| module | symbol (行) | 境界の種類 |
|---|---|---|
| MitateDB `cell.py` | `_LimitStateHolder` (L762-863) | lock、時計 |
| 同 | `ApplicationCell._gate` (L1054-1064)、`_limit_gate` (L974-1052) | 認証・scope・limit。**呼出し経路を触る抽出は WP-3** (R-32 閉止済み) |
| 同 | `_idempotency_check` `_idempotency_pg_scope` (L1150-1366)、`_reconstruct_digest_operation` (L496-571) | idempotency reservation / replay |
| 同 | `_make_audit_hook` `_push_*_event` `_write_replayed_schema_event` `_route_delete_confirmation_denial` (L1066-1148) | audit emit |
| 同 | `_validate_delete_confirmation` (L2561-2685) | audit への denial 経路。`test_application_audit.py:1102-1103` の件数検査の対象 |
| 同 | `transact` (L2908-3400)、`_plan_operation` (L2723-2870)、`check_plan_precondition` (L476-493) | transaction、plan (`check_plan_precondition` は U-4) |
| 同 | `_require_data` `_require_developer` (L3934-3996)、`ApplicationRuntime` / `ApplicationDeveloper` の認可 facade | 認可 |
| r2db `structured.py` | `ApplicationCell` (L1923-3017)、`_IdempotencyRecord` `_idempotency_record_has_request_id` (L1840-1877)、`fold_operation_idempotency_keys` (L1800-1825) | in-memory cell の lock、idempotency (`fold_operation_idempotency_keys` は U-4) |
| r2db `postgres.py` | `_run` (L309-317) | execute choke point |
| 同 | `_RolePool` `SharedPoolManager` `_PoolHandle` `default_pool_manager` `_env_int` (L320-729) | connection ownership、環境変数。`_RolePool._acquire` は getsource→AST 検査の対象 |
| 同 | 表名・lock 定数 (L155-223)、`_idempotency_*` (L1175-1320) | advisory lock、idempotency |
| 同 | `transact` `apply_schema` `_apply_upsert` `_set_timeouts` `_timeout_ms` | transaction、`SET LOCAL` timeout |
| 同 | `_fail_client_value` `_fail_unique_conflict` (L1665-1706) | driver exception mapping (allowlist `1706`) |
| 同 | `verify_platform_upgrades_applied`、`_apply_row_level_security` `verify_row_level_security`、`_RefusingPlatformUpgradeCell` | fail-closed |
| r2db `service.py` | `_now_iso`、`_PreCommitHook` `_AuditBuffer` `_DenialCoalescer`、audit 定数 (`_DURABLE_DENIAL_CODES` ほか) | 時計、audit |
| 同 | `authenticate`、`_slot` `acquire_concurrency_slot` `_check` `_acquire_rate`、`_event` `_denial_event` `flush_audit_buffer`、`ControlAuthority` | 認証、lock (getsource→AST 検査の対象)、audit、control plane |
| MitateDB `backend_postgres.py` | `_guard_pending_platform_upgrades`、`_execute`、表名・lock 定数 (L351-436) | fail-closed、execute、lock |
| 同 | `begin` `commit` `rollback` `_set_timeouts` `_timeout_ms`、`idempotency_*` `_write_idempotency_row` `record_idempotency`、`alter_field_constraints` `create_collection` `add_field` | transaction、timeout、idempotency、DDL 実行と lock |

## 4. 優先順と WP 割当

**WP-1 の最初の 3 件の選定基準**: 移動する denial が 0 件 (件数 pin・`SCANNED_MODULES` を変えない)、行番号 allowlist が無い file、文字列・getsource 検査に掛からない、登録 helper を含まない、コメント整理の変更セット 1 (r2db `postgres.py`) と同じファイルでない。

| 順 | WP | ID | 理由 |
|---|---|---|---|
| 0 | 1-0 | leaf import 方向テスト | 既存 6 leaf の登録と、両 peer `src/` の全 module の分類 (M2)。以後の WP の前提 (m5) |
| 1 | 1a | ST1 | pin 影響 0。呼出し元は同 module の 1 関数だけ |
| 2 | 1b | CE1 | pin 影響 0 (件数検査の文字列を含まない) |
| 3 | 1c | ST2 | pin 影響 0 |
| 4〜 | 1 後続 | CE2 → ST3 → ST4 → ST5 → ST7 → ST6 → CE3 → CE4 → BP4 | pin 影響の小さい順 (count / scan / sib の変更を伴う) |
| — | 1 後続 又は 4 | BP1、BP2 | allow 20 件の行送りを伴う。`backend_postgres.py` は抽出が先 (U-2) |
| — | 2 | CE1 ↔ r2db `_canonical_where_json` | 同名だけが根拠にならない (設計 §3.1 末尾)。本文比較のうえ登録するかを決める (登録すれば Class D) |
| — | 3 | ST8、ST9、ST10、CE5、CE6、CE7、SV1、SV2、SV3 | request binding と結果型 (ST10、SV1。U-4)。`_gate` 経路は WP-3 |
| — | 4 | PG1〜PG4、BP3 | SQL assembly。PG1〜PG4 は変更セット 1 の統合後 (U-2) |

- **ST5 は ST4 の後にしか動かせない。** ST5 は `MAX_IDENTIFIER_LENGTH` (L27) を読む。leaf が `structured` を import すると循環 import になり、設計 D-1 が禁じる late import でしか解けない。ST7 も `validate_identifier` を読むので同じである。
- `bind_schema_operation` (ST9) は developer gate、request shape、identifier / constraint validation を行って `BoundSchemaOperation` を返す binding の境界である。gate (L879) は facade に残し、leaf へ移さない (設計 §4 WP-0)。
- **同じファイルで抽出とコメント整理の変更セットを同時に行わない (U-1 / U-2)。** r2db `postgres.py` は変更セット 1 → 抽出。`structured.py`・`cell.py`・MitateDB `backend_postgres.py` は抽出 → ファイル単位のコメント整理。抽出で移す docstring・コメントは 40c のとおり逐語で移し、経緯の整理は後の変更セットで行う。
- **module を足す WP は、同じ変更で `tools/tests/test_leaf_import_direction.py` の分類 (leaf なら許可リストも) を更新する (U-5、M2)。**
- **ST3〜ST9、CE2〜CE4 で denial を移す WP は、同じ変更で sib の固定 module 集合を更新する (m6)。**
- **WP-1-0 以降のすべての WP の検証とゲートに `pytest -q tools/tests` を入れる (m5)。** root ゲートは `tools/tests` を収集しない。

## 5. Change Set Manifest (4 件)

**共通**:

| 項目 | 内容 |
|---|---|
| 変更クラス | **B** (roadmap §9 の 8)。`_ISOMORPHIC_TARGETS` の増減が起きたら停止 |
| テンプレート | **2** Sonnet 実装 (コミットしない、git 操作禁止) → **5** Opus コードレビュー (報告に無い変異 1〜2 種) → **6** Opus 証拠監査 |
| 読む正本 | 設計 §1.1、§2 D-1 / D-2 / D-3、§3、§4 WP-1、§5.1、§5.2、§8.3 (先例)、§8.4。`docs/work-orders/OPERATING_CONDITIONS.md` §1.5 (32〜40c)、§1.6。本書 §2 の該当行と §6 の裁定 |
| 変異の規律 | 一時コピー又は専用 worktree。復元、変異文字列 0 件、sha256 二重照合 (運用条件 §1.4) |
| 「赤になる test id」 | **予想である。** 実装担当が実測で確定し、同じ行を書き換えず報告に記す (§1.5 の 34)。`tools/tests` の test 関数の分け方は実装に任せる |
| 順序 | **WP-1-0 → 1a → 1b → 1c の直列** (§6) |

- **監督裁定 (独立レビュー再確認の minor 1)**: import 方向テストは module ごとに parametrize しない (全 module を 1 関数で走査する)。leaf を足しても `tools/tests` の node id は増えない。
- **監督裁定 (同 minor 2)**: 空 module を足す変異 (WP-1-0 の変異 3・4) は `pytest -q tools/tests` だけで実行する。

**検証コマンドと期待形** (worktree の root で実行。40a: 抽出コミットの前、前景直列、`timeout` 600000):

```
$PY -m pytest -q tools/tests          → failed 0 (root ゲートの外。全 WP で実行)
$PY -m pytest -q r2db-api/tests       → failed/skipped/xfailed 0
$PY -m pytest -q MitateDB-api/tests   → 同上
$PY -m pytest -q conformance-tests    → 同上
$PY -m pytest --collect-only -q -p no:cacheprovider | grep '::' | sort
                                      → §1 の一覧との差 = 新規テストだけ
$PY -m pytest --collect-only -q -p no:cacheprovider tools/tests
                                      → §1 の 107 + 新規テスト
python3 tools/check_doc_refs.py       → exit 0
python3 tools/public_value_scan.py <触ったファイル> → total_flagged=0
監督: root suite 単独 `$PY -m pytest -q -n 5 --dist loadgroup` と `$PY -m pytest -q tools/tests` (§1.3 の 19〜23)
```

### 5.1 WP-1-0 — leaf の import 方向テスト

**目的**: `tools/tests/test_leaf_import_direction.py` を新設する。既存 6 leaf を登録し、両 peer `src/` の全 module を分類させる。`src/` は触らない。

| 触るファイル | 触らないファイル |
|---|---|
| 新規 `tools/tests/test_leaf_import_direction.py` | 両 peer の `src/` と `tests/`、`conformance-tests/`、`tools/` の他ファイル、`.github/`、`_ISOMORPHIC_TARGETS` |

| 項目 | 規則 |
|---|---|
| 対象 | 両 peer の `src/<package>/` 配下の全 `.py` (再帰。`__init__.py` と `contract/__init__.py` を含む)。実測 r2db 27、MitateDB 36 |
| 分類 (M2) | 各 module は「leaf 一覧 (peer・パス・許可リスト)」か「理由付きの非 leaf 集合」のどちらか 1 つだけに入る。未分類・重複・理由の空欄は赤 |
| 照合 (m3) | AST の `import` / `from` を読み、import を実行しない。名前は AST 上の module 名 (`from psycopg import sql` → `psycopg`、`from .errors import …` → `.errors`)。`__future__` は常に許可する |
| 置き場所 | `tools/tests` の 1 file だけ。両 peer に同名 helper を置かない (§1.5 の 38) |

| peer | 既存 leaf | 許可リスト (実測 2026-09-14) |
|---|---|---|
| r2db | `r2db-api/src/r2db_api/postgres_types.py` | `psycopg` |
| r2db | `r2db-api/src/r2db_api/postgres_like.py` | なし |
| r2db | `r2db-api/src/r2db_api/audit_counts.py` | なし |
| r2db | `r2db-api/src/r2db_api/value_nul.py` | `typing` |
| MitateDB | `MitateDB-api/src/mitatedb_api/postgres_value_domain.py` | `.errors` |
| MitateDB | `MitateDB-api/src/mitatedb_api/request_traversal.py` | `dataclasses`、`typing` |

非 leaf の理由は 1 行 (例: 上位層を import する、I/O・lock を持つ)。分類は実装担当が実測し、監督がコミット前に確定する。

| # | 完了条件 | 変異 (`file:操作`、src は専用 worktree) | 赤になる test id (予想) |
|---|---|---|---|
| 1 | leaf の import が許可リストの内だけ (r2db) | `postgres_like.py`: `import os` を 1 行足す | `tools/tests/test_leaf_import_direction.py::test_leaf_modules_import_only_their_allowlisted_modules` |
| 2 | 同 (MitateDB) | `request_traversal.py`: 許可リスト外の `import json` を 1 行足す | 同上 |
| 3 | 全 module が分類される (M2) | `r2db-api/src/r2db_api/` に分類の無い空 module を足す | `tools/tests/test_leaf_import_direction.py::test_every_src_module_is_classified` |
| 4 | subpackage も対象 | `MitateDB-api/src/mitatedb_api/contract/` に分類の無い空 module を足す | 同上 |
| 5 | leaf と非 leaf が重ならない | 一覧: `postgres_like.py` を非 leaf 集合にも足す | 同上 |
| 6 | 非 leaf に理由がある | 一覧: 非 leaf 1 件の理由を空文字にする | 同上 |
| 7 | 一覧のパスが実在する (§1.5 の 32) | 一覧: leaf 1 件のパスを存在しない名前にする | 同上 |
| 8 | 触ったのは新規 1 file だけ | **監査照合**: 差分のパス一覧、`_ISOMORPHIC_TARGETS` の差分 0 | — |
| 9 | 集計行 | **監査照合**: `tools/tests` は 107 + 新規、両 peer suite と conformance は前後で一致 (src の移動は無く 40a の対象外) | — |
| 10 | 対応の無い行が無い | **監査照合** (§1.5 の 40) | — |

### 5.2 WP-1a — r2db PostgreSQL テキスト表現 (ST1)

**目的**: `structured.py` の 4 関数を leaf `r2db-api/src/r2db_api/pg_text_format.py` へ移す。facade と挙動は変えない。

| 触るファイル | 触らないファイル |
|---|---|
| `r2db-api/src/r2db_api/structured.py` (L3061-3150 を除き import 1 行)、新規 `r2db-api/src/r2db_api/pg_text_format.py`、`r2db-api/tests/test_foundation.py` (新規テスト 1 本)、`tools/tests/test_leaf_import_direction.py` (leaf 1 行、許可 `json`・`decimal`・`typing`) | `r2db-api/src/r2db_api/postgres.py` (L81 の `structured._jsonb_text` 参照は facade で成立する。変更セット 1 の対象)、`r2db-api/tests/test_l1_details_vocabulary_ast_scan.py`、両 peer の `tests/test_audit_query.py`、MitateDB-api 全部、`conformance-tests/`、`spec/`、`security/` |

| # | 完了条件 | 変異 (`file:操作`) | 赤になる test id (予想) |
|---|---|---|---|
| 1 | facade 互換 | `structured.py`: import から `_jsonb_scalar_text` を外す | `r2db-api/tests/test_foundation.py::test_pg_text_format_leaf_preserves_structured_facade_and_postgres_text_forms` (新規) |
| 2 | 整数値 float の `.0` を落とす (float8out) | `pg_text_format.py`: `_float8out_text` の `endswith(".0")` を `endswith(".00")` | 同上 |
| 3 | jsonb 数値は指数表記を展開する | `pg_text_format.py`: `_jsonb_numeric_text` の `Decimal` 分岐を削除 | 同上 |
| 4 | bool は小文字 literal | `pg_text_format.py`: `"true"` を `"True"` | 同上、`r2db-api/tests/test_foundation.py::test_contains_and_matches_apply_to_typed_non_string_columns_via_text_form` |
| 5 | object の key 順は (byte 長, byte 値) | `pg_text_format.py`: sort key から `len(...)` を外す | 新規テスト |
| 6 | 移動先が L1 走査で扱われる (40b) | `pg_text_format.py`: `details=` の無い `fail("VALIDATION_FAILED", "x")` を 1 行足す | `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py::test_every_module_with_a_vocabulary_denial_is_accounted_for` |
| 7 | leaf の import が許可リストの内だけ (m4) | `pg_text_format.py`: `import os` を 1 行足す | `tools/tests/test_leaf_import_direction.py::test_leaf_modules_import_only_their_allowlisted_modules` |
| 8 | 新 leaf が分類される | 一覧から `pg_text_format.py` の行を消す | `tools/tests/test_leaf_import_direction.py::test_every_src_module_is_classified` |
| 9 | docstring の逐語移動 (40c) | **監査照合**: 差分は位置参照の括弧書きだけ。対象は `_jsonb_text` の「`_predicate_text`, below」と `_float8out_text` の「nothing else in this file does」(m2)。経緯の整理はしない (U-1) | — |
| 10 | 同型性を登録しない | **監査照合**: `_ISOMORPHIC_TARGETS` の差分 0、MitateDB `src/` の同名 def 0 件 | — |
| 11 | 集計行 (40a) | **監査照合**: コミット前の 4 集計行 (両 peer、conformance、`tools/tests`) | — |
| 12 | node id の差分 | **監査照合**: root は WP-1-0 統合後との差が新規 1 件、`tools/tests` は差 0 | — |
| 13 | 対応の無い行が無い | **監査照合** (§1.5 の 40) | — |

### 5.3 WP-1b — MitateDB 削除確認 phrase (CE1)

**目的**: `cell.py` の `_canonical_where_json` と `_delete_confirmation_phrase` を leaf `MitateDB-api/src/mitatedb_api/delete_confirmation.py` へ移す (r2db の ST5 も後で同名にする。U-3)。

| 触るファイル | 触らないファイル |
|---|---|
| `MitateDB-api/src/mitatedb_api/cell.py` (L351-375、L574-613 を除き import 1 行)、新規 `MitateDB-api/src/mitatedb_api/delete_confirmation.py`、`MitateDB-api/tests/test_foundation.py` (新規テスト 1 本)、`tools/tests/test_leaf_import_direction.py` (leaf 1 行、許可 `hashlib`・`json`) | `MitateDB-api/tests/test_application_audit.py`、`MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py`、両 peer の `tests/test_audit_query.py`、r2db-api 全部 (`structured._canonical_where_json` は WP-2)、`conformance-tests/` |

| # | 完了条件 | 変異 (`file:操作`) | 赤になる test id (予想) |
|---|---|---|---|
| 1 | facade 互換 | `cell.py`: import から `_delete_confirmation_phrase` を外す | `MitateDB-api/tests/test_foundation.py::FoundationTests::test_delete_confirmation_leaf_preserves_cell_facade_and_phrase_shape` (新規) |
| 2 | 値の dict も key 順に並べる (M1) | `delete_confirmation.py`: `sort_keys=True` を `False` | 同上 (値に `{"z": 1, "a": 2}` を持つ Filter の canonical JSON を literal で pin する。既存の `::test_canonical_where_json_key_sorts_each_filter_preserves_list_order_never_stringifies` は現行データでは緑のまま) |
| 3 | phrase の形 (digest 16 桁 + schema_revision) | `delete_confirmation.py`: `[:16]` を `[:15]` | 同上 (固定入力の phrase を literal で pin する。既存テストは同じ関数で phrase を作るので緑のまま) |
| 4 | 移動先が L1 走査で扱われる (40b) | `delete_confirmation.py`: `details` の無い `raise ValidationError("x")` を 1 行足す | `MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py::test_every_module_with_a_vocabulary_denial_is_accounted_for` |
| 5 | 件数検査が効いたまま | **監査照合**: `test_application_audit.py:1102-1103` の 2 文字列の `cell.py` 内件数が前後とも 1 / 2 | — |
| 6 | leaf の import が許可リストの内だけ (m4) | `delete_confirmation.py`: `import os` を 1 行足す | `tools/tests/test_leaf_import_direction.py::test_leaf_modules_import_only_their_allowlisted_modules` |
| 7 | 新 leaf が分類される | 一覧から `delete_confirmation.py` の行を消す | `tools/tests/test_leaf_import_direction.py::test_every_src_module_is_classified` |
| 8 | docstring の逐語移動 (40c) | **監査照合**: 差分は位置参照の括弧書きだけ (「`delete` below」「`ApplicationCell.delete` below」「comment above `_DELETE_CONSEQUENCE`」)。経緯の整理はしない (U-1) | — |
| 9 | 同型性を登録しない (WP-1 は片側) | **監査照合**: `_ISOMORPHIC_TARGETS` の差分 0 | — |
| 10 | 集計行 (40a) | **監査照合**: コミット前の 4 集計行 | — |
| 11 | node id の差分 | **監査照合**: root は直前の統合後との差が新規 1 件、`tools/tests` は差 0 | — |
| 12 | 対応の無い行が無い | **監査照合** (§1.5 の 40) | — |

### 5.4 WP-1c — r2db in-memory の並べ替え key (ST2)

**目的**: `structured.py` の `_JSON_TYPE_RANK` (説明コメントを含む) / `_sort_key` / `_sort_rows` を leaf `r2db-api/src/r2db_api/inmemory_sort.py` へ移す。

| 触るファイル | 触らないファイル |
|---|---|
| `r2db-api/src/r2db_api/structured.py` (L1592-1597、L1634-1664 を除き import 1 行)、新規 `r2db-api/src/r2db_api/inmemory_sort.py`、`r2db-api/tests/test_foundation.py` (新規テスト 1 本)、`tools/tests/test_leaf_import_direction.py` (leaf 1 行、許可 `json`・`typing`) | `r2db-api/src/r2db_api/postgres.py` (L1430 のコメント参照。変更セット 1 の対象)、`r2db-api/tests/test_l1_details_vocabulary_ast_scan.py`、両 peer の `tests/test_audit_query.py`、MitateDB-api 全部、`conformance-tests/` |

| # | 完了条件 | 変異 (`file:操作`) | 赤になる test id (予想) |
|---|---|---|---|
| 1 | facade 互換 | `structured.py`: import から `_sort_rows` を外す | `r2db-api/tests/test_foundation.py::test_inmemory_sort_leaf_preserves_structured_facade_and_null_rank` (新規)、`::test_order_by_sorts_and_appends_id_when_absent` |
| 2 | NULL は昇順で最後 | `inmemory_sort.py`: `(1, 0, "")` を `(-1, 0, "")` | `r2db-api/tests/test_foundation.py::test_order_by_null_placement_matches_postgresql_defaults` |
| 3 | 型の違う値は jsonb の型順 | `inmemory_sort.py`: `_JSON_TYPE_RANK` の `string` と `number` を入れ替え | `r2db-api/tests/test_foundation.py::test_order_by_untyped_column_uses_jsonb_cross_type_order` |
| 4 | 複数 field は後ろの field から安定ソート | `inmemory_sort.py`: `reversed(spec)` を `spec` | 新規テスト |
| 5 | 移動先が L1 走査で扱われる (40b) | `inmemory_sort.py`: `details=` の無い `fail("VALIDATION_FAILED", "x")` を 1 行足す | `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py::test_every_module_with_a_vocabulary_denial_is_accounted_for` |
| 6 | leaf の import が許可リストの内だけ (m4) | `inmemory_sort.py`: `import os` を 1 行足す | `tools/tests/test_leaf_import_direction.py::test_leaf_modules_import_only_their_allowlisted_modules` |
| 7 | 新 leaf が分類される | 一覧から `inmemory_sort.py` の行を消す | `tools/tests/test_leaf_import_direction.py::test_every_src_module_is_classified` |
| 8 | docstring・コメントの逐語移動 (40c) | **監査照合**: `_sort_key` の docstring と L1592-1596 の説明コメント (m1)。「`_sort_key` below」「`_sort_rows`'s existing」は同じ leaf に残る。経緯の整理はしない (U-1) | — |
| 9 | 同型性を登録しない | **監査照合**: `_ISOMORPHIC_TARGETS` の差分 0、MitateDB `src/` の同名 def 0 件 | — |
| 10 | 集計行 (40a) | **監査照合**: コミット前の 4 集計行 | — |
| 11 | node id の差分 | **監査照合**: root は直前の統合後との差が新規 1 件、`tools/tests` は差 0 | — |
| 12 | 対応の無い行が無い | **監査照合** (§1.5 の 40) | — |

### 5.5 WP-1 後続 3 件の共通 (v1.3 追記、v1.4 でレビュー反映)

| 項目 | 内容 |
|---|---|
| 対象 | §4 の「4〜」行の先頭 3 件 (CE2 → ST3 → ST4)。飛ばした候補は無い |
| 行番号 | `fbf45cb` の実測。§2 の行範囲は `a0e2a82` 時点のもので、1a〜1c の移動によりずれている。対象ファイルは main `944e86b` と同一 |
| 変更クラス、テンプレート、変異の規律、検証コマンド | §5 の共通表と検証コマンドのとおり。root collection は各 WP で +1 (新規テスト 1 本)、`tools/tests` は着手時の基点との差 0 |
| 読む正本 | §5 の共通表に加え、設計 §10 (WP-1 の実施記録と既知の穴)、運用条件 §1.5 の 40a〜40c |
| 「赤になる test id」 | 予想である。既存の id は `fbf45cb` の collect-only で存在を確認済み。(新規) の id はまだ存在しない |

**1a〜1c の先例とレビュー指摘から足す規律**:

| # | 規律 | 出所 |
|---|---|---|
| 1 | 位置参照の括弧書きは指示語の直後に置く (例: 「above (in `request_limits.py`)」)。移動範囲の外に残る指示語も、指す先が変われば対象にする | 40c、1a〜1c |
| 2 | 定義の直前にある説明コメントを移動範囲に含める | m1 (1c) |
| 3 | 変異は性質を直接壊すものにする。赤を確かめられる literal 入力を新規テストに置く | M1 (1b) |
| 4 | 新 leaf を `tools/tests/test_leaf_import_direction.py` の leaf 一覧に 1 行足す | U-5 |
| 5 | denial を移す WP は、同じ変更で L1 details AST scan を更新する: `SCANNED_MODULES`、件数 pin、行番号 allowlist (実測。不変なら差分 0 を記録する)、sib の固定 module 集合 | 40b、m6 |

**各 WP の表の末尾に付く共通の完了条件** (いずれも監査照合):

| # | 完了条件 | 照合対象 |
|---|---|---|
| C-1 | 集計行 (40a) | コミット前の 4 集計行 |
| C-2 | node id の差分 | root は直前の統合後との差が新規 1 件、`tools/tests` は着手時の基点との差 0 |
| C-3 | 対応の無い行が無い | §1.5 の 40 |

**監督裁定 (WP-1d コードレビュー)**: WP-1d は dict 分岐・循環検出を直接呼ぶテストに価値があるとして新規テスト 6 本を残した (facade 1、変異 2・3b・4・5a・5b の各 1)。C-2 の「新規 1 件」は WP-1d には適用されず、root の差は新規 6 件である。§5.6 の完了条件表・実測はこの前提で読む。

**監督裁定 (WP-1e コードレビュー)**: §5.7 の完了条件 7 の予想 test id は float を経由せず赤にならないため、実装担当が新規テスト `test_matches_applies_float8out_formatting_to_a_typed_number_column` を足した。新規テストは合計 2 本 (facade 1、上記 1)。C-2 の「新規 1 件」は WP-1e には適用されず、root の差は新規 2 件である。§5.7 の完了条件表・実測はこの前提で読む。

**監督裁定 (WP-1f コードレビュー)**: 新規テストは合計 4 本 (facade と長さの境界を兼ねる 1、先頭の数字 1、末尾の改行 1、str でない値 1)。C-2 の「新規 1 件」は WP-1f には適用されず、root の差は新規 4 件である。§5.8 の完了条件表・実測はこの前提で読む。

### 5.6 WP-1d — MitateDB 要求の大きさと深さの検査 (CE2)

**目的**: `cell.py` の `_measure_request_bytes` と `_check_operation_depth` を leaf `MitateDB-api/src/mitatedb_api/request_limits.py` へ移す。`_limit_gate` の呼出し順と facade は変えない。

| 項目 | 実測 (`fbf45cb`) |
|---|---|
| 移動範囲 | `cell.py` L555-656 (2 関数。直前に説明コメントは無い) |
| 呼出し元 | `ApplicationCell._limit_gate` (L980-981) |
| leaf の import | `.errors` (`ValidationError`・`ResourceLimitError`・`violation`)、`.request_traversal` (`_as_traversable`) |
| facade | `cell.py` が 2 名を import する。`_as_traversable` の import は `test_application_plane_limits.py` が `cell` から読むので残す |
| denial | `ValidationError` 2 件 (L590、L647。4-key)、`ResourceLimitError` 4 件 |
| 件数 pin | `cell.py` 49 → 47、`request_limits.py` 2 (キーを新設) |
| 行番号 allowlist | 対象は `backend_postgres.py` だけなので差分 0 |
| sib 集合 | (`cell.py`, `field_types.py`, `http.py`, `identifiers.py`) に `request_limits.py` を足す |
| `test_limit_class_vocabulary.py` | 走査はパッケージ直下の `*.py` (非再帰) なので、件数 36 は変わらない |
| 移動範囲外の位置参照 (40c) | 直す: `cell.py` L698-699 の「`_check_operation_depth` above」、L4394 の「(module-level, above)」、`request_traversal.py` L9-10 の「below (in `cell.py`)」、`MitateDB-api/tests/test_application_plane_limits.py` L553 の「`cell.py::_measure_request_bytes`」。直さない: V-4 の一覧 |

| 触るファイル | 触らないファイル |
|---|---|
| `MitateDB-api/src/mitatedb_api/cell.py` (L555-656 を除き、import 1 行と括弧書き 2 箇所)、新規 `MitateDB-api/src/mitatedb_api/request_limits.py`、`MitateDB-api/tests/test_application_plane_limits.py` (新規テスト 1 本と L553 の参照)、`MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py` (`SCANNED_MODULES`、件数 pin、sib 集合)、`tools/tests/test_leaf_import_direction.py` (leaf 1 行、許可 `.errors`・`.request_traversal`)、`MitateDB-api/src/mitatedb_api/request_traversal.py` (L9-10 の括弧書きだけ) | `MitateDB-api/src/mitatedb_api/http.py` (L931 は名前だけの参照)、`MitateDB-api/tests/test_limit_class_vocabulary.py`、`MitateDB-api/tests/test_application_audit.py`、`conformance-tests/` (V-4)、両 peer の `tests/test_audit_query.py`、r2db-api 全部 |

| # | 完了条件 | 変異 (`file:操作`) | 赤になる test id (予想) |
|---|---|---|---|
| 1 | facade 互換 | `cell.py`: import から `_check_operation_depth` を外す | `MitateDB-api/tests/test_application_plane_limits.py::test_request_limits_leaf_preserves_cell_facade_and_bounds` (新規)、`::test_gate_denies_operation_depth_before_budget_validation` |
| 2 | str は 1 文字を 4 byte と数える | `request_limits.py`: `len(item) * 4` を `len(item) * 3` にする | 新規テスト (`"x" * 25` が bound 99 で拒否され、bound 100 で通ることを literal で固定する) |
| 3a | 容器の要素数で先に拒否する (list) | `request_limits.py`: list 分岐の `bound // 8` を `bound // 4` にする | `MitateDB-api/tests/test_application_plane_limits.py::test_measure_request_bytes_rejects_a_container_with_too_many_elements_before_the_running_total_would` |
| 3b | 同 (dict) | `request_limits.py`: dict 分岐の `bound // 8` を `bound // 4` にする | 新規テスト (1 文字の key 13,000 個と空 list の値を持つ dict を bound 100,000 で渡す。合計 78,002 は bound 未満、要素数は 12,500 を超える) |
| 4 | 深さは bound を超えたときだけ拒否する | `request_limits.py`: `next_depth > bound` を `>=` にする | 新規テスト (`{"a": {"b": 1}}` が bound 2 で通り、bound 1 で `limit_class` `operation_depth` になる) |
| 5a | 循環は `request_schema` の `ValidationError` になる (`_check_operation_depth`) | `request_limits.py`: `_check_operation_depth` の条件を `False and marker in ancestors` にする (呼出し箇所の数は変えない) | 新規テスト (自己参照の list で `_check_operation_depth` を直接呼び、`details == {"violated_declaration": "request_schema"}` を確かめる) |
| 5b | 同 (`_measure_request_bytes`) | `request_limits.py`: `_measure_request_bytes` の条件を同じく `False and marker in ancestors` にする | 新規テスト (同じ list で `_measure_request_bytes` を直接呼ぶ) |
| 6 | 移動先が `SCANNED_MODULES` に入る (40b) | `test_l1_details_vocabulary_ast_scan.py`: `SCANNED_MODULES` から `request_limits.py` を外す | `MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py::test_every_module_with_a_vocabulary_denial_is_accounted_for`、`::test_ast_full_count_matches_a_non_trivial_floor` |
| 7 | 件数 pin (`cell.py` 47、`request_limits.py` 2) | `request_limits.py`: 4-key の `ValidationError("x", details=violation("request_schema"))` を返す関数を 1 つ足す | `MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py::test_ast_full_count_matches_a_non_trivial_floor` |
| 8 | 移した denial が 4-key のまま | `request_limits.py`: `_measure_request_bytes` の `ValidationError` から `details=` を外す | `MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py::test_every_choke_point_denial_carries_details_ast_full_count`、`::test_allowlist_entries_match_real_bare_call_sites` |
| 9 | 行番号 allowlist が実測と一致 | **監査照合**: `_BACKEND_LAYER_ALLOWLIST` の差分 0、`::test_allowlist_entries_match_real_bare_call_sites` が緑 | — |
| 10 | sib 集合に移動先が入る (m6) | `request_limits.py`: `_check_operation_depth` の `ResourceLimitError` の文言を allowlist の文言 `"storage backend rejected the request"` にする | `MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py::test_backend_layer_allowlist_entries_have_no_in_memory_sibling_denial` (集合を更新しないと緑のまま) |
| 11 | limit_class の走査が移動先に及ぶ | `request_limits.py`: `request_bytes` の `ResourceLimitError` 1 件から `limit_class=` を外す | `MitateDB-api/tests/test_limit_class_vocabulary.py::test_every_resource_limit_error_call_site_declares_a_contract_limit_class` |
| 12 | leaf の import が許可リストの内だけ | `request_limits.py`: `import os` を 1 行足す | `tools/tests/test_leaf_import_direction.py::test_leaf_modules_import_only_their_allowlisted_modules` |
| 13 | 新 leaf が分類される | 一覧から `request_limits.py` の行を消す | `tools/tests/test_leaf_import_direction.py::test_every_src_module_is_classified` |
| 14 | docstring とコメントの逐語移動と、位置参照の括弧書き (40c) | **監査照合**: 2 つの docstring と L646 のコメントが逐語であること。範囲内の「above」「immediately above」は同じ leaf の中で成り立つので括弧を付けない。範囲外の差分は `cell.py` L699、L4394 と `request_traversal.py` L9-10 の括弧書きだけであること | — |
| 15 | テストの位置参照を移動先に直す (40c) | **監査照合**: `test_application_plane_limits.py` L553 の「`cell.py::_measure_request_bytes`」が移動先を指し、新規テスト以外の差分はそこだけであること | — |
| 16 | 同型性を登録しない | **監査照合**: `_ISOMORPHIC_TARGETS` の差分 0。r2db 側の対応物は `limits.py::ResourceLimits.check_request` / `check_depth` で、同名ではない | — |
| 17 | 既知の穴を記録する (V-4) | **監査照合**: V-4 の一覧が差分 0 のままで、完了時の実施記録 (設計の追記) に既知の穴として載っていること | — |

**監督裁定 (WP-1d コードレビュー)**: 完了条件 1 の facade テストは facade のみを検査する内容に合わせ `test_request_limits_leaf_preserves_cell_facade` (新規) に改名した。行 1 の test id はこの名前で読む。新規テストは合計 6 本 (facade 1、変異 2・3b・4・5a・5b の各 1)。

- 5a / 5b の新規テストは関数を直接呼ぶ。gate を通すと、先に走る検査が同じ例外を出して変異を隠すためである。
- 共通の C-1〜C-3 (§5.5) を末尾に付ける。

### 5.7 WP-1e — r2db in-memory の述語評価 (ST3)

**目的**: `structured.py` の `_wildcard_pattern` (説明コメントを含む)、`_predicate_text`、`_matches` を leaf `r2db-api/src/r2db_api/inmemory_predicate.py` へ移す。**変更セット 1 の統合後に着手する** (§5.9)。

| 項目 | 実測 (`fbf45cb`) |
|---|---|
| 移動範囲 | `structured.py` L2983-3109 (ファイル末尾。L2983-2989 の説明コメントを含む。§2.1 で 2 区間だった範囲は、ST1 の移動で連続した) |
| 呼出し元 | `_matches` を `ApplicationCell.query` (L2044) と `_transact_locked` (L2400) が呼ぶ |
| leaf の import | `__future__` (`from __future__ import annotations` は**必須**)、`re`、`typing`、`.errors` (`fail`・`violation`)、`.pg_text_format` (`_float8out_text`・`_jsonb_scalar_text`・`_jsonb_text`) |
| 型注釈 `Predicate` | `_matches` の注釈は裸の名前の注釈 (文字列ではない) で、逐語のまま残し import しない (V-2)。`from __future__ import annotations` が無いと、定義時に評価されて NameError になる |
| facade | `structured.py` が 3 名を import する。`pg_text_format` の import 行は、1a の facade テストが `structured` から読むので残す |
| denial | `fail("VALIDATION_FAILED", …)` 1 件 (L3012。4-key) |
| 件数 pin | `structured.py` 93 → 92、`inmemory_predicate.py` 1 (`test_ast_full_count_matches_the_audit_site_count` の module tuple と dict の両方に足す) |
| 行番号 allowlist | 対象は `postgres.py` だけなので差分 0 |
| sib 集合 | `_all_fail_messages(SRC / "structured.py")` の 1 module を (`structured.py`, `inmemory_predicate.py`) にする |
| 移動範囲外の位置参照 (40c) | `pg_text_format.py` L85 の「`_predicate_text`, below (in `structured.py`)」、同 L7 の「`structured._predicate_text` … remain in their own modules」 |

| 触るファイル | 触らないファイル |
|---|---|
| `r2db-api/src/r2db_api/structured.py` (L2983-3109 を除き import 1 行)、新規 `r2db-api/src/r2db_api/inmemory_predicate.py`、`r2db-api/tests/test_foundation.py` (新規テスト 1 本)、`r2db-api/tests/test_l1_details_vocabulary_ast_scan.py` (`SCANNED_MODULES`、件数 pin、sib 集合)、`tools/tests/test_leaf_import_direction.py` (leaf 1 行、許可 `re`・`typing`・`.errors`・`.pg_text_format`)、`r2db-api/src/r2db_api/pg_text_format.py` (L7、L85 の括弧書きだけ) | `r2db-api/src/r2db_api/postgres.py` (変更セット 1)、`r2db-api/tests/test_l1_details_vocabulary_ast_scan.py` の `_BACKEND_LAYER_ALLOWLIST` (変更セット 1 が書く)、`r2db-api/tests/test_postgres.py`、MitateDB-api 全部、`conformance-tests/`、両 peer の `tests/test_audit_query.py` |

| # | 完了条件 | 変異 (`file:操作`) | 赤になる test id (予想) |
|---|---|---|---|
| 1 | facade 互換 | `structured.py`: import から `_matches` を外す | `r2db-api/tests/test_foundation.py::test_inmemory_predicate_leaf_preserves_structured_facade_and_wildcard_escape` (新規)、`::test_contains_is_a_literal_substring_and_never_interprets_wildcards` |
| 2 | `_` はちょうど 1 文字 | `inmemory_predicate.py`: `_` 分岐の `"."` を `re.escape(ch)` にする | `r2db-api/tests/test_foundation.py::test_matches_wildcard_semantics_and_case_sensitivity` |
| 3 | `\` は次の 1 文字を literal にする | `inmemory_predicate.py`: `\` 分岐の `re.escape(pattern[i + 1])` を `"."` にする | 新規テスト (`r"a\_b"` が `"a_b"` に一致し、`"axb"` に一致しない。既存の `"100\\% sure"` は緑のまま) |
| 4 | 大文字と小文字を区別する | `inmemory_predicate.py`: `"(?s)\\A"` を `"(?si)\\A"` にする | `r2db-api/tests/test_foundation.py::test_matches_wildcard_semantics_and_case_sensitivity` |
| 5 | `contains` は wildcard を解釈しない | `inmemory_predicate.py`: `contains` 分岐を `_wildcard_pattern("%" + expected + "%").match(…) is not None` にする | `r2db-api/tests/test_foundation.py::test_contains_is_a_literal_substring_and_never_interprets_wildcards` |
| 6 | `in` は NULL の行を除く | `inmemory_predicate.py`: `in` 分岐の `if actual is None: return False` を削除する | `r2db-api/tests/test_foundation.py::test_in_excludes_null_rows_even_when_the_list_itself_contains_null` |
| 7 | 型付き `number` 列の float だけ float8out にする | `inmemory_predicate.py`: `field_type == "number"` を `!=` にする | `r2db-api/tests/test_foundation.py::test_contains_and_matches_apply_to_typed_non_string_columns_via_text_form` |
| 8 | 移動先が `SCANNED_MODULES` に入る (40b) | `test_l1_details_vocabulary_ast_scan.py`: `SCANNED_MODULES` から `inmemory_predicate.py` を外す | `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py::test_every_module_with_a_vocabulary_denial_is_accounted_for` |
| 9 | 件数 pin (`structured.py` 92、`inmemory_predicate.py` 1) | `inmemory_predicate.py`: 4-key の `fail("VALIDATION_FAILED", "x", details=violation("request_schema"))` を呼ぶ関数を 1 つ足す | `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py::test_ast_full_count_matches_the_audit_site_count` |
| 10 | 移した denial が 4-key のまま | `inmemory_predicate.py`: `_wildcard_pattern` の `fail` から `details=` を外す | `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py::test_every_choke_point_denial_carries_details_ast_full_count`、`::test_allowlist_entries_match_real_bare_call_sites` |
| 11 | 行番号 allowlist が実測と一致 | **監査照合**: 本 WP による `_BACKEND_LAYER_ALLOWLIST` の差分 0 (変更セット 1 統合後の値との比較) | — |
| 12 | sib 集合に移動先が入る (m6) | `inmemory_predicate.py`: `_wildcard_pattern` の `fail` の文言を allowlist の文言 `"A value in this request is not acceptable to the underlying storage."` にする | `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py::test_backend_layer_allowlist_entries_have_no_in_memory_sibling_denial` (集合を更新しないと緑のまま) |
| 13 | leaf の import が許可リストの内だけ | `inmemory_predicate.py`: `import os` を 1 行足す | `tools/tests/test_leaf_import_direction.py::test_leaf_modules_import_only_their_allowlisted_modules` |
| 14 | 新 leaf が分類される | 一覧から `inmemory_predicate.py` の行を消す | `tools/tests/test_leaf_import_direction.py::test_every_src_module_is_classified` |
| 15 | docstring とコメントの逐語移動と、位置参照の括弧書き (40c) | **監査照合**: L2983-2989 の説明コメント、関数内のコメント、2 つの docstring が逐語であること。範囲外の差分は `pg_text_format.py` L7、L85 の 2 箇所だけで、移動先 `inmemory_predicate.py` を指すこと | — |
| 16 | `_matches` は AST 同一 (注釈の名前 `Predicate` も同一) で、leaf は `Predicate` を import しない (V-2) | `inmemory_predicate.py`: `if TYPE_CHECKING: from .structured import Predicate` を足す | `tools/tests/test_leaf_import_direction.py::test_leaf_modules_import_only_their_allowlisted_modules` (AST 同一は監査照合で確かめる) |
| 17 | leaf に `from __future__ import annotations` がある (V-2) | `inmemory_predicate.py`: その行を消す | `r2db-api/tests/test_foundation.py` の収集エラー (`structured` の import 時に `_matches` の定義が NameError。Python 3.11) |
| 18 | 同型性を登録しない | **監査照合**: `_ISOMORPHIC_TARGETS` の差分 0、MitateDB `src/` の同名 def 0 件 | — |
| 19 | 既知の穴を記録する (V-2) | **監査照合**: 型検査 (pyflakes / ruff 等) を導入すると `Predicate` が未定義名 F821 になることが、完了時の実施記録に載っていること | — |

**監督裁定 (WP-1e コードレビュー)**: 完了条件 7 の予想 test id `test_contains_and_matches_apply_to_typed_non_string_columns_via_text_form` は float を経由しないため赤にならない。実装担当が新規テスト `test_matches_applies_float8out_formatting_to_a_typed_number_column` を足し、これを赤の根拠とした。新規テストは合計 2 本 (facade 1、上記 1)。C-2 の「新規 1 件」は WP-1e には適用されず、root の差は新規 2 件である。本節の完了条件 1・7 の実測はこの前提で読む。

- 共通の C-1〜C-3 (§5.5) を末尾に付ける。

### 5.8 WP-1f — r2db identifier 規則 (ST4)

**目的**: `structured.py` の identifier 構文と予約名の定数・検査 (8 名、説明コメントを含む) を leaf `r2db-api/src/r2db_api/identifier_rules.py` へ移す。ST5・ST7 の前提 (§4)。**変更セット 1 と WP-1e の統合後に着手する** (§5.9)。

| 項目 | 実測 (`fbf45cb`) |
|---|---|
| 移動範囲 | `structured.py` L22-29 (`IDENTIFIER`、L23-28 の説明コメント、`MAX_IDENTIFIER_LENGTH`) と L41-99 (`_RESERVED_PREFIX` から `_reject_reserved_entity_name` まで。L41-48、L52-61、L82-93 の説明コメントを含む) |
| 残すもの | L30 `OPERATORS`、L31-39 `_TEXT_ONLY_OPERATORS` とその説明コメント。§2.1 の L20-97 にはこれらが含まれていたが、ST4 の symbol ではない |
| 呼出し元 | `structured.py` 内 (`Predicate.validate`、`bind_mutation`、`bind_schema_operation` ほか)、`postgres.py` (`validate_identifier`・`_reject_reserved_entity_name`)、`credential_store.py` (`validate_identifier`)、`platform_declarations.py` (`IDENTIFIER`・`MAX_IDENTIFIER_LENGTH`) |
| leaf の import | `re`、`.errors` (`fail`・`violation`) |
| facade | `structured.py` が 8 名を import する。他 module の import は facade 経由のまま成り立つ |
| denial | `fail("IDENTIFIER_INVALID", …)` 4 件 (L64、L70、L79、L99。4-key) |
| 件数 pin | `structured.py` 92 → 88 (WP-1e 統合後の値から)、`identifier_rules.py` 4 |
| 行番号 allowlist | 対象は `postgres.py` だけなので差分 0 |
| sib 集合 | WP-1e で作る module 集合に `identifier_rules.py` を足す |
| 移動範囲外の位置参照 (40c) | `structured.py` L363 の「`MAX_IDENTIFIER_LENGTH` above」(ST5 のコメント) に括弧書きを付ける。範囲内の「every identifier-syntax helper below」「`_reject_reserved_prefix` above」は同じ leaf の中で成り立つ |

| 触るファイル | 触らないファイル |
|---|---|
| `r2db-api/src/r2db_api/structured.py` (移動範囲を除き、import 1 行と L363 の括弧書き)、新規 `r2db-api/src/r2db_api/identifier_rules.py`、`r2db-api/tests/test_foundation.py` (新規テスト 1 本)、`r2db-api/tests/test_l1_details_vocabulary_ast_scan.py` (`SCANNED_MODULES`、件数 pin、sib 集合)、`tools/tests/test_leaf_import_direction.py` (leaf 1 行、許可 `re`・`.errors`) | `r2db-api/src/r2db_api/postgres.py` (L141-149 の import は facade で成り立つ。変更セット 1)、`credential_store.py`、`platform_declarations.py`、`r2db-api/tests/test_postgres.py` (L627、L822 のコメント参照)、`r2db-api/tests/test_l5_si10_details_leak_scan.py`、MitateDB-api 全部 (`identifiers.py` は WP-2)、`conformance-tests/`、両 peer の `tests/test_audit_query.py` |

| # | 完了条件 | 変異 (`file:操作`) | 赤になる test id (予想) |
|---|---|---|---|
| 1 | facade 互換 | `structured.py`: import から `_reject_reserved_prefix` を外す (他 module は import していない) | `r2db-api/tests/test_foundation.py::test_identifier_rules_leaf_preserves_structured_facade_and_length_bound` (新規)、`::test_create_index_rejects_reserved_prefix_double_underscore_oversized_name_id_field_and_bad_field_counts` |
| 2 | 長さは 63 まで許す | `identifier_rules.py`: `len(value) > MAX_IDENTIFIER_LENGTH` を `>=` にする | 新規テスト (`"a" * 63` が通り、`"a" * 64` が `IDENTIFIER_INVALID` になる) |
| 3 | 先頭は英字か `_` | `identifier_rules.py`: `IDENTIFIER` の先頭の文字類を `[A-Za-z0-9_]` にする | 新規テスト (`"1a"` が拒否される)、`r2db-api/tests/test_postgres.py::test_injection_payloads_in_identifier_positions_are_rejected[starts_with_digit]` (**後者は実測で確定する**) |
| 4 | `id` は field 名にだけ予約する | `identifier_rules.py`: `_reject_reserved_field` の `name == "id" or ` を削除する | `r2db-api/tests/test_foundation.py::test_reserved_identifier_names_are_rejected_for_entities_and_fields` |
| 5 | `audit_events` は完全一致だけを拒否する | `identifier_rules.py`: `name in _RESERVED_ENTITY_NAMES` を `name.startswith("audit_events")` にする | `r2db-api/tests/test_foundation.py::test_audit_events_entity_name_is_reserved_by_exact_match_only` |
| 6 | details の `field` は要求内の path | `identifier_rules.py`: `validate_identifier` の `field=field` を `field="identifier"` にする | `r2db-api/tests/test_denial_details_and_request_id.py::test_identifier_invalid_field_is_a_request_path_not_the_literal_identifier` |
| 7 | 移動先が `SCANNED_MODULES` に入る (40b) | `test_l1_details_vocabulary_ast_scan.py`: `SCANNED_MODULES` から `identifier_rules.py` を外す | `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py::test_every_module_with_a_vocabulary_denial_is_accounted_for` |
| 8 | 件数 pin (`structured.py` 88、`identifier_rules.py` 4) | `identifier_rules.py`: 4-key の `fail("IDENTIFIER_INVALID", "x", details=violation("identifier_syntax", field="x"))` を呼ぶ関数を 1 つ足す | `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py::test_ast_full_count_matches_the_audit_site_count` |
| 9 | 移した denial が 4-key のまま | `identifier_rules.py`: `_reject_reserved_entity_name` の `fail` から `details=` を外す | `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py::test_every_choke_point_denial_carries_details_ast_full_count`、`::test_allowlist_entries_match_real_bare_call_sites` |
| 10 | 行番号 allowlist が実測と一致 | **監査照合**: 本 WP による `_BACKEND_LAYER_ALLOWLIST` の差分 0 | — |
| 11 | sib 集合に移動先が入る (m6) | `identifier_rules.py`: `_reject_reserved_entity_name` の文言を allowlist の文言 `"A value in this request is not acceptable to the underlying storage."` にする | `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py::test_backend_layer_allowlist_entries_have_no_in_memory_sibling_denial` (集合を更新しないと緑のまま) |
| 12 | leaf の import が許可リストの内だけ | `identifier_rules.py`: `import os` を 1 行足す | `tools/tests/test_leaf_import_direction.py::test_leaf_modules_import_only_their_allowlisted_modules` |
| 13 | 新 leaf が分類される | 一覧から `identifier_rules.py` の行を消す | `tools/tests/test_leaf_import_direction.py::test_every_src_module_is_classified` |
| 14 | docstring とコメントの逐語移動と、位置参照の括弧書き (40c) | **監査照合**: L23-28、L41-48、L52-61、L82-93 の説明コメントと `_reject_reserved_prefix` の docstring が逐語であること。範囲外の括弧書きは L363 の 1 箇所 | — |
| 15 | 同型性を登録しない | **監査照合**: `_ISOMORPHIC_TARGETS` の差分 0。MitateDB `identifiers.py:22` に同名の `validate_identifier` があるが署名が違う (`label` 位置引数と、keyword 必須の `field`)。登録するかは WP-2 で決める | — |

**監督裁定 (WP-1f コードレビュー)**: 新規テストは合計 4 本 (facade と長さの境界を兼ねる 1 [完了条件 1・2]、先頭の数字 1 [完了条件 3]、末尾の改行 1、str でない値 1)。root の差は新規 4 件である (§5.5 の C-2 はこの WP には適用されない)。追加の 2 本は SI-05 の既知の穴を塞ぐ:
- `validate_identifier` は末尾に改行の付いた識別子 (`"name\n"`) を拒否する。`IDENTIFIER.fullmatch` を `.match` にする変異で赤になることを実測で確認した。
- `validate_identifier` は str でない値 (`123`、`None`) を拒否する。`isinstance(value, str)` の検査を外す変異 (`TypeError` が `FoundationError` を隠す) で赤になることを実測で確認した。

`structured.py` の `import re` は、識別子規則の移動により参照が 0 件になったため、同じ WP で削除した (先例 `2a20d33`)。完了条件 3 の「赤になる test id」は `r2db-api/tests/test_postgres.py::test_injection_payloads_in_identifier_positions_are_rejected[starts_with_digit]` と、新規の先頭数字テスト (`test_identifier_rejects_a_name_starting_with_a_digit`) の 2 件である。

- 共通の C-1〜C-3 (§5.5) を末尾に付ける。

### 5.9 重なり・順序・監督裁定 (v1.3 追記)

**触るパスの重なり** (○ = 重なりなし。× = 重なりあり、直列。L = `tools/tests/test_leaf_import_direction.py`、S = `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py`):

| | WP-1d (CE2) | WP-1e (ST3) | WP-1f (ST4) | 変更セット 1 |
|---|---|---|---|---|
| WP-1d | — | × L | × L | ○ |
| WP-1e | × | — | × L、S、`structured.py`、`r2db-api/tests/test_foundation.py` | × S |
| WP-1f | × | × | — | × S |

- **順序**: WP-1d → WP-1e → WP-1f の直列 (3 件とも L を触る)。WP-1d は変更セット 1 と重ならないので、その統合を待たずに着手できる。
- **WP-1e と WP-1f は S を触るので、変更セット 1 の統合後に直列で行う。** 変更セット 1 は S の `_BACKEND_LAYER_ALLOWLIST` の数値を書き、WP-1e / 1f は同じファイルの `SCANNED_MODULES`、件数 pin、sib 集合を書く。変更セット 1 はほかに r2db `postgres.py`、`docs/code-history/r2db-api/`、`tools/check_comment_provenance.py` を触るが、3 件はそれらに触れない。
- `structured.py` と `cell.py` のコメント整理は抽出の後に行う (U-2)。3 件とも経緯の整理はせず、40c のとおり逐語で移す。

**監督裁定 (2026-09-14、V-1〜V-4)**:

| # | 裁定 | 反映先 |
|---|---|---|
| V-1 | 移動範囲外の括弧書き (`request_traversal.py` L9-10、`pg_text_format.py` L7/L85) は同じ WP で直す | §5.6 の 14、§5.7 の 15 |
| V-2 | `_matches` の `Predicate` は裸の名前の注釈 (文字列ではない) のまま逐語で残し、import しない。leaf に `from __future__ import annotations` が必須 (実行時に評価させない)。完了条件は AST 同一 (注釈の名前も同一) と、leaf に `Predicate` の import が無いこと。型検査を導入すると F821 になる点は既知の穴 | §5.7 の 16・17・19 |
| V-3 | WP 名は 1d / 1e / 1f で確定 | §5.6〜§5.8 |
| V-4 | 移動前から古い、又は移動で古くなるが直すと Class C になる参照は、本範囲で直さない。一覧: `cell.py` L4395 の「(`:531`)」、`conformance-tests/test_c05_limit_declaration_agreement.py` L1184-1185 の「`cell.py`'s own `_LimitStateHolder`/`_measure_request_bytes`」と L1197 の `cell.py:531`、`MitateDB-api/tests/test_limit_class_vocabulary.py` L143 の件数説明の文字列 (「cell.py x6」)。WP-1d の既知の穴として完了時の実施記録に書く | §5.6 の 17 |

### 5.10 WP-1f の次の 3 件の共通 (v1.5 追記、**独立レビュー待ち**)

| 項目 | 内容 |
|---|---|
| 対象 | §4 の「4〜」行で WP-1f に続く 3 件 (ST5 → ST7 → ST6)。飛ばした候補は無い (3 件とも `service.py` を触らない) |
| 行番号 | `4fc5517` の実測。WP-1h / 1i の行番号は先行 WP の統合でずれるので、着手時に取り直す |
| 変更クラス、テンプレート、検証コマンド | §5 の共通表と §5.5 のとおり。各表の末尾に §5.5 の C-1〜C-3 を付ける。C-2 の「新規 1 件」は各 WP の新規テスト本数と読み替える |
| 読む正本 | §5.5 に加え、設計 §10.4 |
| 「赤になる test id」 | 予想である。既存の id は `4fc5517` の collect-only で存在を確認済み。予想に挙げた既存テストは本体を読み、変異で壊す性質を通ることを確かめた |

**WP-1d〜1f のレビューから足す規律** (§5.5 の 1〜5 の続き):

| # | 規律 |
|---|---|
| 6 | 新規テストの本数と名前は中身に合わせる (1 本に詰めない。名前が検査内容を表す) |
| 7 | 予想の赤テストは、変異で壊す性質を実際に通るものを選ぶ |
| 8 | sib 集合は固定 tuple に module を足す |
| 9 | 移動で未使用になった import は同じ WP で削除する。facade テストが移動元から読む名前は残す |
| 10 | 位置参照の括弧書きは指示語の直後に置く。`structured.X` のような qualified name は facade で成り立つので直さない |
| 11 | 裸の名前の注釈を持つ関数を移すときは、leaf に `from __future__ import annotations` を置き、注釈の型を import しない (V-2) |

### 5.11 WP-1g — r2db 破壊的操作の確認 phrase (ST5、**独立レビュー待ち**)

**目的**: `structured.py` の確認 phrase の構成と SI-09 gate (11 名と節見出しコメント) を leaf `r2db-api/src/r2db_api/delete_confirmation.py` へ移す (U-3)。

| 項目 | 実測 (`4fc5517`) |
|---|---|
| 移動範囲 | `structured.py` L287-549 (L287-303 の節見出しコメント、L305-307・L309-313・L443-450 の説明コメント、`RESET_CONTROL_CREDENTIALS` の docstring L453-470 を含む。L279-284 は `bind_mutation` の末尾なので含めず、件数 pin は 88 のまま) |
| 呼出し元 | `ApplicationCell` の delete / drop_entity / drop_index、`postgres.py`、`control_plane.py`、`ops.py` (いずれも facade 経由) |
| leaf の import | `hashlib`、`json`、`typing`、`.errors` (`fail`)、`.identifier_rules` (`MAX_IDENTIFIER_LENGTH`)。注釈 `"list[Predicate]"` は文字列なので import しない |
| facade | 11 名を import する。`structured.py` 側で未使用になる import は無い |
| denial | `fail("DESTRUCTIVE_CONFIRMATION_REQUIRED", message, …)` 1 件。語彙 code ではなく文言も引数なので、L1 scan (件数 pin、`SCANNED_MODULES`、sib、allowlist) は変わらない |
| 移動範囲外の位置参照 (40c) | `ops.py` L138 の「`structured.py`'s own header comment」、`r2db-api/tests/test_control_plane_store.py` L1292 の「the exact same module (`structured.py`)」 |
| 範囲内で指す先が残る参照 | L309 の「`_INT64_MAX` below in this same module」(`_INT64_MAX` は `structured.py` に残る。W-2)、L292 の「(data/schema plane here, …)」の here (data/schema plane は `structured.py` に残る) |

| 触るファイル | 触らないファイル |
|---|---|
| `r2db-api/src/r2db_api/structured.py` (移動範囲を除き import 1 行)、新規 `r2db-api/src/r2db_api/delete_confirmation.py`、`r2db-api/tests/test_foundation.py` (新規テスト 4 本)、`tools/tests/test_leaf_import_direction.py` (leaf 1 行、許可 `hashlib`・`json`・`typing`・`.errors`・`.identifier_rules`)、`r2db-api/src/r2db_api/ops.py` (L138 の括弧書きだけ)、`r2db-api/tests/test_control_plane_store.py` (L1292 の括弧書きだけ) | `r2db-api/src/r2db_api/postgres.py`・`service.py` (変更セット 2)、`r2db-api/tests/test_l1_details_vocabulary_ast_scan.py`、`control_plane.py`、MitateDB-api 全部 (同名 `_canonical_where_json` は WP-2)、`conformance-tests/`、両 peer の `tests/test_audit_query.py` |

| # | 完了条件 | 変異 (`file:操作`) | 赤になる test id (予想) |
|---|---|---|---|
| 1 | facade 互換 | `structured.py`: import から `_canonical_where_json` を外す (他 module は import していない) | `r2db-api/tests/test_foundation.py::test_delete_confirmation_leaf_preserves_structured_facade` (新規。11 名の同一性だけを確かめる) |
| 2 | canonical JSON は入れ子の key も並べる | `delete_confirmation.py`: `sort_keys=True` を `False` にする | `r2db-api/tests/test_foundation.py::test_canonical_where_json_sorts_nested_keys_and_escapes_non_ascii` (新規。値に `{"z": 1, "a": 2}` を持つ `Predicate` の canonical JSON を literal で固定する) |
| 3 | canonical JSON は非 ASCII を escape する | `delete_confirmation.py`: `ensure_ascii=True` を `False` にする | 同上 (値 `"é"` の canonical JSON を literal で固定する) |
| 4 | delete phrase は digest 16 桁を持つ | `delete_confirmation.py`: `_where_digest16` の `[:16]` を `[:15]` にする | `r2db-api/tests/test_foundation.py::test_delete_confirmation_phrases_have_fixed_literal_shapes` (新規。固定入力の phrase を literal で固定する) |
| 5 | delete phrase は schema_revision で無効になる | `delete_confirmation.py`: `delete_confirmation_phrase` の f-string から ` @schema_revision={schema_revision}` を削る | `r2db-api/tests/test_foundation.py::test_delete_phrase_invalidated_by_drop_recreate_of_the_same_entity_under_the_same_name` |
| 6 | drop / revoke / CLI の phrase の綴り | `delete_confirmation.py`: `drop_entity_confirmation_phrase` の `DROP_ENTITY` を `DROP_TABLE` にする | `r2db-api/tests/test_foundation.py::test_delete_confirmation_phrases_have_fixed_literal_shapes` (4 関数と `RESET_CONTROL_CREDENTIALS` の出力を literal で固定する) |
| 7 | gate は destructive が真で確認文が完全一致のときだけ通す | `delete_confirmation.py`: `require_destructive_confirmation` の `not destructive or ` を削る | `r2db-api/tests/test_foundation.py::test_require_destructive_confirmation_needs_destructive_true_and_the_exact_phrase` (新規。`destructive=False` と正しい phrase で拒否される) |
| 8 | denial の details は 4 key | `delete_confirmation.py`: `"recovery": recovery,` の行を削る | 同上 (details を literal で固定する) |
| 9 | L1 scan は変わらない | **監査照合**: `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py` の差分 0 で緑 | — |
| 10 | leaf の import が許可リストの内だけ | `delete_confirmation.py`: `import os` を 1 行足す | `tools/tests/test_leaf_import_direction.py::test_leaf_modules_import_only_their_allowlisted_modules` |
| 11 | 新 leaf が分類される | 一覧から `delete_confirmation.py` の行を消す | `tools/tests/test_leaf_import_direction.py::test_every_src_module_is_classified` |
| 12 | 逐語移動と位置参照の括弧書き (40c) | **監査照合**: 節見出しと説明コメント、docstring が逐語。範囲内の「this module's header comment」「the other three」「`*_confirmation_phrase` functions above」は同じ leaf の中で成り立つ。括弧書きは `ops.py` L138、`test_control_plane_store.py` L1292、L292 の here の直後 (「(in `structured.py`)」)、L309 (W-2) の 4 箇所だけ | — |
| 13 | 同型性を登録しない | **監査照合**: `_ISOMORPHIC_TARGETS` の差分 0。MitateDB `delete_confirmation._canonical_where_json(filters)` は署名が違う (WP-2) | — |
| 14 | マージ時点で `_INT64_MAX` の参照が正しい (W-2 裁定) | **監査照合**: 移した文の「`_INT64_MAX` below in this same module」の直後に `(in \`structured.py\`)` があり、`_INT64_MAX` が `structured.py` に在ること | — |

**監督裁定 (WP-1gコードレビュー)**: `test_control_plane_store.py` L1292 の入れ子括弧を 1 層 (`` `structured.py` (now in `delete_confirmation.py`) ``) に直して原文の改行を保ち、`ops.py` L138-140 も原文の改行を保ったまま括弧書きだけを足す形に戻し、完了条件 7・8 のテストに `destructive=True` かつ正確な phrase で通る場合と、空白付き・swapcase の phrase が `.strip()`/`.casefold()` 緩和の変異でそれぞれ赤になることを実測して足した。

### 5.12 WP-1h — r2db page size・order_by・cursor (ST7、**独立レビュー待ち**)

**目的**: `structured.py` の page size・order_by・cursor の検査と組立 (8 名と節見出し 2 行) を leaf `r2db-api/src/r2db_api/paging.py` へ移す。**変更セット 2 と WP-1g の統合後に着手する** (§5.14)。

| 項目 | 実測 (`4fc5517`) |
|---|---|
| 移動範囲 | `structured.py` L1514-1616 (L1514・L1533 の節見出し、L1516-1522 の説明コメント、関数内のコメントを含む) |
| 呼出し元 | `ApplicationCell.query`、`postgres.py` (`validate_page_size`・`_resolve_order_by`・`_shape_hash`・`_encode_cursor`・`_decode_cursor`。facade 経由) |
| leaf の import | `__future__` (**必須**)、`base64`、`hashlib`、`json`、`typing`、`.errors` (`fail`・`violation`)、`.identifier_rules` (`validate_identifier`)、`.limits` (`ResourceLimits`。`limits.py` は `.errors` だけを import するので循環しない) |
| 型注釈 `Predicate` | `_shape_hash` の `list[Predicate]` は裸の名前の注釈。逐語で残し import しない (V-2 と同じ) |
| facade | 8 名を import する。`import base64` は `structured.py` で未使用になるので削除する |
| denial | 語彙 code の `fail` 10 件 (4-key)、ほかに `LIMIT_EXCEEDED` 1 件と `NOT_FOUND` 1 件 |
| 件数 pin | `structured.py` 88 → 78、`paging.py` 10 (module tuple と dict の両方に足す) |
| 行番号 allowlist | 対象は `postgres.py` だけなので、本 WP による差分 0 |
| sib 集合 | 固定 tuple (`structured.py`, `inmemory_predicate.py`, `identifier_rules.py`) に `paging.py` を足す |
| 移動範囲外の位置参照 (40c) | `http.py` L466 の「`structured.py`'s shared `_resolve_order_by`/`_decode_cursor`」。`test_http.py` L498 の `r2db_api.structured._shape_hash` は facade で成り立つので直さない |

| 触るファイル | 触らないファイル |
|---|---|
| `r2db-api/src/r2db_api/structured.py` (移動範囲を除き、import 1 行と `import base64` の削除)、新規 `r2db-api/src/r2db_api/paging.py`、`r2db-api/tests/test_foundation.py` (新規テスト 3 本)、`r2db-api/tests/test_l1_details_vocabulary_ast_scan.py` (`SCANNED_MODULES`、件数 pin、sib tuple)、`tools/tests/test_leaf_import_direction.py` (leaf 1 行、許可 `base64`・`hashlib`・`json`・`typing`・`.errors`・`.identifier_rules`・`.limits`)、`r2db-api/src/r2db_api/http.py` (L466 の括弧書きだけ) | `r2db-api/src/r2db_api/postgres.py`・`service.py` (変更セット 2)、`r2db-api/tests/test_l1_details_vocabulary_ast_scan.py` の `_BACKEND_LAYER_ALLOWLIST`、`r2db-api/tests/test_http.py`、MitateDB-api 全部、`conformance-tests/`、両 peer の `tests/test_audit_query.py` |

| # | 完了条件 | 変異 (`file:操作`) | 赤になる test id (予想) |
|---|---|---|---|
| 1 | facade 互換 | `structured.py`: import から `MAX_CURSOR_OFFSET` を外す (他 module は import していない) | `r2db-api/tests/test_foundation.py::test_paging_leaf_preserves_structured_facade` (新規) |
| 2 | page size は 1000 を含み、1001 を拒否する | `paging.py`: `page_size > MAX_PAGE_SIZE` を `>=` にする | `r2db-api/tests/test_foundation.py::test_page_size_over_the_contract_maximum_is_validation_failed` |
| 3 | page size 0 は `LIMIT_EXCEEDED` | `paging.py`: `page_size <= 0` を `page_size < 0` にする | `r2db-api/tests/test_foundation.py::test_validate_page_size_refuses_zero_as_limit_exceeded` (新規。既存の `r2db-api/tests/test_foundation.py::test_finite_limits_are_enforced_and_discoverable` も赤になるかは実測で確定する) |
| 4 | order_by は 10 個まで | `paging.py`: `len(order_by) > MAX_ORDER_BY_FIELDS` を `>=` にする | `r2db-api/tests/test_foundation.py::test_resolve_order_by_bounds_fields_and_appends_id_last` (新規。10 個を通し 11 個を拒否する) |
| 5 | `id` が無ければ末尾に昇順で足す | `paging.py`: `spec.append(("id", "asc"))` を `pass` にする | 同上 (`_resolve_order_by(None, set())` が `[("id", "asc")]`。既存の `::test_order_by_sorts_and_appends_id_when_absent` は挿入順と一致するので緑のまま) |
| 6 | 同じ field を 2 度指定できない | `paging.py`: `field_name in seen_fields` の条件を `False and field_name in seen_fields` にする | `r2db-api/tests/test_foundation.py::test_order_by_rejects_a_repeated_field` |
| 7 | cursor の offset は 10^9 まで | `paging.py`: `or offset > MAX_CURSOR_OFFSET` を削る | `r2db-api/tests/test_foundation.py::test_cursor_rejects_negative_offset_overflow_and_non_dict_payload` |
| 8 | cursor は同じ形の問い合わせにだけ使える | `paging.py`: `shape != expected_shape` を `False` にする | `r2db-api/tests/test_foundation.py::test_cursor_shape_mismatch_and_malformed_cursor_are_rejected` |
| 9 | shape hash は application に結び付く | `paging.py`: `"application": application_id,` の行を削る | `r2db-api/tests/test_foundation.py::test_cursor_shape_hash_is_bound_to_application_and_entity` |
| 10 | 移動先が `SCANNED_MODULES` に入る (40b) | `test_l1_details_vocabulary_ast_scan.py`: `SCANNED_MODULES` から `paging.py` を外す | `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py::test_every_module_with_a_vocabulary_denial_is_accounted_for` |
| 11 | 件数 pin (`structured.py` 78、`paging.py` 10) | `paging.py`: 4-key の `fail("VALIDATION_FAILED", "x", details=violation("request_schema"))` を呼ぶ関数を 1 つ足す | `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py::test_ast_full_count_matches_the_audit_site_count` |
| 12 | 移した denial が 4-key のまま | `paging.py`: `_decode_cursor` の最初の `fail` から `details=` を外す | `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py::test_every_choke_point_denial_carries_details_ast_full_count`、`::test_allowlist_entries_match_real_bare_call_sites` |
| 13 | 行番号 allowlist が実測と一致 | **監査照合**: 本 WP による `_BACKEND_LAYER_ALLOWLIST` の差分 0 | — |
| 14 | sib tuple に移動先が入る | `paging.py`: `"Cursor is not valid."` を allowlist の文言 `"A value in this request is not acceptable to the underlying storage."` にする | `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py::test_backend_layer_allowlist_entries_have_no_in_memory_sibling_denial` (tuple を更新しないと緑のまま) |
| 15 | leaf の import が許可リストの内だけ | `paging.py`: `import os` を 1 行足す | `tools/tests/test_leaf_import_direction.py::test_leaf_modules_import_only_their_allowlisted_modules` |
| 16 | 新 leaf が分類される | 一覧から `paging.py` の行を消す | `tools/tests/test_leaf_import_direction.py::test_every_src_module_is_classified` |
| 17 | `_shape_hash` は AST 同一 (注釈の名前も同一) で、leaf は `Predicate` を import しない | `paging.py`: `if TYPE_CHECKING: from .structured import Predicate` を足す | `tools/tests/test_leaf_import_direction.py::test_leaf_modules_import_only_their_allowlisted_modules` (AST 同一は監査照合) |
| 18 | leaf に `from __future__ import annotations` がある | `paging.py`: その行を消す | `r2db-api/tests/test_foundation.py` の収集エラー (`_shape_hash` の定義時に NameError。Python 3.11) |
| 19 | 未使用になった import を削除した | **監査照合**: `structured.py` に `import base64` が無く、`base64` の参照も 0 件 | — |
| 20 | 逐語移動と位置参照の括弧書き (40c) | **監査照合**: 節見出し、説明コメント、関数内のコメントが逐語。範囲外の差分は `http.py` L466 の括弧書きだけ | — |
| 21 | 同型性を登録しない | **監査照合**: `_ISOMORPHIC_TARGETS` の差分 0、MitateDB `src/` の同名 def 0 件 | — |
| 22 | 既知の穴を記録する | **監査照合**: `Predicate` の裸の注釈が型検査器で F821 になることが、完了時の実施記録に載る | — |

**監督裁定 (WP-1h 実装時): 範囲外の位置参照 1 件を W-2 に従い修正**

対象は `structured.py:1294` (`normalize_request_for_plan` の docstring 内、`_shape_hash` への位置参照に `(in \`paging.py\`)` を補った)。完了条件 20 の「範囲外の差分」はこの 1 件を含む。

**監督裁定 (WP-1h コードレビュー): cursor hash の束縛テスト 2 件を追加**

### 5.13 WP-1i — r2db 値の型検査 (ST6、**独立レビュー待ち**)

**目的**: `structured.py` の値の型・domain 検査と述語値の検査 (6 名) を、それだけが読む `_TEXT_ONLY_OPERATORS` と一緒に leaf `r2db-api/src/r2db_api/value_types.py` へ移す (W-1)。**変更セット 2 と WP-1h の統合後に着手する** (§5.14)。

| 項目 | 実測 (`4fc5517`) |
|---|---|
| 移動範囲 | `structured.py` L33-41 (`_TEXT_ONLY_OPERATORS` と説明コメント) と L1318-1511 (L1318 の節見出し、L1320-1324 の説明コメント、関数内のコメントを含む) |
| `_TEXT_ONLY_OPERATORS` | 読み手は `_validate_predicate_types` だけ (他 module とテストの参照 0 件)。`structured.py` に残すと、leaf が `.structured` を import する循環になる |
| 呼出し元 | `structured.py` 内 (write 経路、`query`、`_fail_constraint_declaration`)、`postgres.py` (`_check_type`・`_declared_type_label`・`_validate_predicate_types`。facade 経由) |
| leaf の import | `typing`、`.errors` (`fail`・`observed_type_of`・`violation`)、`.value_nul` (`_contains_nul`)。注釈 `"FieldConstraints \| None"`・`list["Predicate"]` は文字列なので import しない |
| facade | 6 名と `_TEXT_ONLY_OPERATORS` を import する。`_contains_nul` は `structured.py` で未使用になるが、`test_contains_nul_leaf_preserves_structured_facade_and_nested_detection` が `structured` から読むので残す |
| denial | 語彙 code の `fail` 11 件 (4-key) |
| 件数 pin | `structured.py` 78 → 67、`value_types.py` 11 |
| 行番号 allowlist | 本 WP による差分 0 |
| sib 集合 | 固定 tuple に `value_types.py` を足す |
| 移動範囲外の位置参照 (40c) | `structured.py` L555「`_check_type` below」、L561「this file's own `_check_type`」、L596「(`_check_type` below)」、L763「`_declared_type_label` below」、WP-1g の leaf の「`_INT64_MAX` below in this same module」(W-2)。範囲内の L1383「`_ENUM_ELIGIBLE_TYPES` gate above」は指す先が `structured.py` に残るので、leaf 側で「above」の直後に「(in `structured.py`)」を付ける。`postgres.py` L1559 の `r2db_api.structured._check_type` は facade で成り立つので直さない。L2296「(`_validate_predicate_types`, below and in `query`)」と L2312「`_check_type` below」は `_apply` の中で下にある呼出しを指し、呼出しは `structured.py` に残るので直さない (コードレビューの訂正) |

| 触るファイル | 触らないファイル |
|---|---|
| `r2db-api/src/r2db_api/structured.py` (移動範囲を除き、import 1 行と括弧書き 6 箇所)、新規 `r2db-api/src/r2db_api/value_types.py`、`r2db-api/tests/test_foundation.py` (新規テスト 1 本)、`r2db-api/tests/test_l1_details_vocabulary_ast_scan.py` (`SCANNED_MODULES`、件数 pin、sib tuple)、`tools/tests/test_leaf_import_direction.py` (leaf 1 行、許可 `typing`・`.errors`・`.value_nul`)、`r2db-api/src/r2db_api/delete_confirmation.py` (括弧書き 1 箇所。W-2) | `r2db-api/src/r2db_api/postgres.py`・`service.py` (変更セット 2)、`r2db-api/tests/test_l1_details_vocabulary_ast_scan.py` の `_BACKEND_LAYER_ALLOWLIST`、`r2db-api/tests/test_constraints_declaration.py`、`r2db-api/tests/test_denial_details_and_request_id.py`、MitateDB-api 全部、`conformance-tests/`、両 peer の `tests/test_audit_query.py` |
| (W-1 裁定) `structured.py` の L33-41 (`_TEXT_ONLY_OPERATORS` と説明コメント) を移し、facade import に `_TEXT_ONLY_OPERATORS` を足す | — |

| # | 完了条件 | 変異 (`file:操作`) | 赤になる test id (予想) |
|---|---|---|---|
| 1 | facade 互換 | `structured.py`: import から `_INT64_MAX` を外す (他 module は import していない) | `r2db-api/tests/test_foundation.py::test_value_types_leaf_preserves_structured_facade` (新規) |
| 2 | int64 の両端を受け入れる | `value_types.py`: `_INT64_MIN <= value <= _INT64_MAX` を `_INT64_MIN < value < _INT64_MAX` にする | `r2db-api/tests/test_foundation.py::test_integer_field_value_out_of_bigint_range_is_validation_failed` (`test_foundation.py:1566`。赤になるかは実測で確定する) |
| 3 | int64 の外は `field_type` 違反 | `value_types.py`: 範囲検査の条件を `False and not (…)` にする | `r2db-api/tests/test_foundation.py::test_integer_field_value_out_of_bigint_range_is_validation_failed` |
| 4 | bool は integer にならない | `value_types.py`: integer 分岐の `and not isinstance(value, bool)` を削る | `r2db-api/tests/test_foundation.py::test_typed_integer_and_number_columns_reject_boolean_values` |
| 5 | 型なし値の NUL を拒否する | `value_types.py`: 型なし分岐の `_contains_nul(value)` の条件を `False and _contains_nul(value)` にする | `r2db-api/tests/test_foundation.py::test_nul_byte_is_rejected_in_string_object_array_and_untyped_values` |
| 6 | `nullable: false` は null を拒否する | `value_types.py`: `not constraints.nullable` を `constraints.nullable` にする | `r2db-api/tests/test_constraints_declaration.py::test_memory_nullable_false_refuses_explicit_null[insert]` |
| 7 | enum 違反は `observed_type` を持たない | `value_types.py`: enum 分岐の details に `"observed_type": observed_type_of(value)` を足す | `r2db-api/tests/test_denial_details_and_request_id.py::test_enum_violation_carries_declared_type_never_observed_type`、`r2db-api/tests/test_l1_details_vocabulary_ast_scan.py::test_type_pair_rule_is_respected_at_every_violated_declaration_site` |
| 8 | 型の不一致は `declared_type` と `observed_type` を持つ | `value_types.py`: 型不一致の `fail` の `observed_type=observed_type_of(value)` を `observed_type=None` にする | `r2db-api/tests/test_denial_details_and_request_id.py::test_field_type_violation_carries_both_declared_and_observed_type`、`r2db-api/tests/test_l1_details_vocabulary_ast_scan.py::test_type_pair_rule_is_respected_at_every_violated_declaration_site` |
| 9 | contains / matches の値は str だけ | `value_types.py`: `not isinstance(predicate.value, str)` の条件を `False and …` にする | `r2db-api/tests/test_foundation.py::test_contains_and_matches_reject_non_string_values` |
| 10 | eq / ne は null を拒否する | `value_types.py`: `predicate.value is None` の条件を `False and …` にする | `r2db-api/tests/test_foundation.py::test_eq_and_ne_reject_a_null_predicate_value` |
| 11 | `in` は空 list を拒否する | `value_types.py`: `or not predicate.value` を削る | `r2db-api/tests/test_foundation.py::test_in_operator_rejects_an_empty_list` |
| 12 | 末尾の backslash は奇数個のときだけ拒否する | `value_types.py`: `% 2 == 1` を `> 0` にする | `r2db-api/tests/test_foundation.py::test_matches_pattern_ending_in_an_unescaped_backslash_is_validation_failed` (偶数個を通す部分) |
| 13 | 移動先が `SCANNED_MODULES` に入る (40b) | `test_l1_details_vocabulary_ast_scan.py`: `SCANNED_MODULES` から `value_types.py` を外す | `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py::test_every_module_with_a_vocabulary_denial_is_accounted_for` |
| 14 | 件数 pin (`structured.py` 67、`value_types.py` 11) | `value_types.py`: 4-key の `fail("VALIDATION_FAILED", "x", details=violation("request_schema"))` を呼ぶ関数を 1 つ足す | `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py::test_ast_full_count_matches_the_audit_site_count` |
| 15 | 移した denial が 4-key のまま | `value_types.py`: `_validate_wildcard_pattern` の `fail` から `details=` を外す | `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py::test_every_choke_point_denial_carries_details_ast_full_count`、`::test_allowlist_entries_match_real_bare_call_sites` |
| 16 | 行番号 allowlist が実測と一致 | **監査照合**: 本 WP による `_BACKEND_LAYER_ALLOWLIST` の差分 0 | — |
| 17 | sib tuple に移動先が入る | `value_types.py`: `_validate_wildcard_pattern` の文言を allowlist の文言 `"A value in this request is not acceptable to the underlying storage."` にする | `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py::test_backend_layer_allowlist_entries_have_no_in_memory_sibling_denial` (tuple を更新しないと緑のまま) |
| 18 | leaf の import が許可リストの内だけ | `value_types.py`: `import os` を 1 行足す | `tools/tests/test_leaf_import_direction.py::test_leaf_modules_import_only_their_allowlisted_modules` |
| 19 | 新 leaf が分類される | 一覧から `value_types.py` の行を消す | `tools/tests/test_leaf_import_direction.py::test_every_src_module_is_classified` |
| 20 | 未使用になった import の扱い | **監査照合**: `structured.py` で未使用になる名前は `_contains_nul` だけで、facade テストのために残したこと | — |
| 21 | 逐語移動と位置参照の括弧書き (40c) | **監査照合**: 説明コメント、節見出し、docstring が逐語。括弧書きは `structured.py` の 4 箇所 (L555、L561、L596、L763)、`delete_confirmation.py` の 1 箇所 (W-2)、leaf 内の L1383 の 1 箇所の計 6 箇所だけ | — |
| 22 | 同型性を登録しない | **監査照合**: `_ISOMORPHIC_TARGETS` の差分 0、MitateDB `src/` の同名 def 0 件 | — |
| 23 | `_TEXT_ONLY_OPERATORS` は facade 経由で同じ object (W-1 裁定) | `structured.py`: import から `_TEXT_ONLY_OPERATORS` を外す | `r2db-api/tests/test_foundation.py::test_value_types_leaf_preserves_structured_facade` (新規。`structured._TEXT_ONLY_OPERATORS is value_types._TEXT_ONLY_OPERATORS` を確かめる) |
| 24 | マージ時点で `_INT64_MAX` の参照が正しい (W-2 裁定) | **監査照合**: `delete_confirmation.py` の括弧書きが `(in \`value_types.py\`)` に直り、`_INT64_MAX` が `value_types.py` に在ること | — |

### 5.14 重なり・順序・未確定 (v1.5 追記)

**触るパスの重なり** (L = `tools/tests/test_leaf_import_direction.py`、S = `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py`、T = `r2db-api/src/r2db_api/structured.py`、F = `r2db-api/tests/test_foundation.py`):

| | WP-1g (ST5) | WP-1h (ST7) | WP-1i (ST6) | 変更セット 2 |
|---|---|---|---|---|
| WP-1g | — | × L、T、F | × L、T、F、`delete_confirmation.py` | ○ |
| WP-1h | × | — | × L、S、T、F | × S |
| WP-1i | × | × | — | × S |

- **順序**: WP-1g → WP-1h → WP-1i の直列。WP-1g は変更セット 2 と重ならないので、その統合を待たずに着手できる。1g が触る `ops.py`・`r2db-api/tests/test_control_plane_store.py`・`r2db-api/tests/test_foundation.py` は、変更セット 2 が触る r2db `service.py`・`postgres.py`・`r2db-api/tests/test_l1_details_vocabulary_ast_scan.py`・`docs/code-history/r2db-api/` と重ならない (監督確認済み)。
- **WP-1h と WP-1i は S を触るので、変更セット 2 の統合後に直列で行う。** 変更セット 2 はほかに r2db `service.py`・`postgres.py`・`docs/code-history/r2db-api/` を触るが、3 件はそれらに触れない。
- `service.py` を触る候補 (SV1〜SV3) は変更セット 2 の後に回す (§6 の U-2 追記)。

**未確定 (監督判断待ち)**:

| # | 点 |
|---|---|
| W-1 | WP-1i で `_TEXT_ONLY_OPERATORS` と説明コメントを一緒に移すか。§2.1 は leaf の import を「+ `_TEXT_ONLY_OPERATORS`」と書いたが、`structured.py` から import すると循環になる |
| W-2 | `structured.py` L309 の「`_INT64_MAX` below in this same module」は WP-1g で leaf へ移り、指す先は `structured.py` に残り、WP-1i で `value_types.py` に変わる。括弧書きを WP-1g で付けて WP-1i で差し替えるか、WP-1i で 1 回だけ付けるか |
| W-3 | 変更セット 2 の作業指示書は `4fc5517` の worktree に無い。重なり表は監督の示した触るファイルによる |

**監督裁定 (2026-09-14、W-1〜W-3)**:

| # | 裁定 | 反映先 |
|---|---|---|
| W-1 | `_TEXT_ONLY_OPERATORS` は WP-1i で `value_types.py` へ一緒に移し、`structured.py` には facade として残す (残すと循環 import) | §5.13 の触るファイル (追加行)、23 |
| W-2 | WP-1g で移す文の「`_INT64_MAX` below in this same module」に `(in \`structured.py\`)` を補い、WP-1i で `(in \`value_types.py\`)` に直す。各 WP のマージ時点で参照が正しいこと | §5.11 の 14、§5.13 の 24 |
| W-3 | 変更セット 2 との重なり表は、監督の示したファイル一覧のままでよい | §5.14 |
| 既知の穴 | 設計 §10.4 の #5・#7・#8 と §10.2 の 1〜3 は roadmap §8 R-39 で追跡する。#6 (F821) は型検査器の既知事項として設計 §10.4 に残す | 設計 §10.4、roadmap R-38・R-39 |
| 独立レビュー | 1g の移動範囲を L287-549 に訂正、40c の一覧 (1g の L292、1i の L561・L1383)、1g の新規テストを性質ごとに分割 (計 4 本)、1i の新規テストを 1 本に、1h の変異 3 の注記、1g と変更セット 2 の非重複 | §5.11〜§5.14 |

### 5.15 WP-1i の次の 3 件の共通 (v1.7 追記、**独立レビュー済み**)

| 項目 | 内容 |
|---|---|
| 対象 | §4 の「4〜」行の残り 3 件 (CE3 → CE4 → BP4)。飛ばした候補は無い。3 件とも MitateDB 側で、r2db-api と `conformance-tests/` は触らない |
| 行番号 | `2fde59a` の実測。WP-1k の `cell.py` の行は WP-1j の統合でずれるので着手時に取り直す。WP-1l の `backend_postgres.py` は 1j / 1k が触らない |
| 変更クラス、テンプレート、検証コマンド | §5 の共通表、§5.5、§5.10 のとおり。各表の末尾に §5.5 の C-1〜C-3 を付ける (C-2 の「新規 1 件」は各 WP の新規テスト本数と読み替える) |
| 読む正本 | §5.10 に加え、設計 §10.5 |
| baseline (導出) | root 3,366 (`r2db-api/tests` 1,275 / `MitateDB-api/tests` 1,096 / `conformance-tests` 995)、`tools/tests` 109。§1 の件数に設計 §10.1・§10.4・§10.5 の新規テスト本数を足した値で、WP-1i の root ゲート `3366 passed` と一致する。着手時に collect-only で確かめる |
| S_M | `MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py`。現在は `SCANNED_MODULES` 11 件、件数 pin `cell.py` 47・`backend_postgres.py` 24、行番号 allowlist 20 件 (`backend_postgres.py` L563〜L1986)、sib tuple (`cell.py`, `field_types.py`, `http.py`, `identifiers.py`, `request_limits.py`) |
| 新規テスト | facade は先例どおり、移した名前の組ごとに `is` の検査を 1 本。性質のテストは各節に書く (1j 2 本、1k 2 本、1l 2 本。すべて `MitateDB-api/tests`) |
| `_gate` (設計 §9.3) | 3 件とも `_gate` (L883)・`_limit_gate` (L803) の本体とその呼出し経路を動かさない。両関数は移す名前を呼ばない (実測)。移すものはゲート通過後の操作から呼ばれ、呼出し箇所は `cell.py` に残る |

### 5.16 WP-1j — MitateDB field_constraints の解決 (CE3、**独立レビュー済み**)

**目的**: `cell.py` の `_validate_enum_declaration_with_path` と `_resolve_field_constraints` を leaf `MitateDB-api/src/mitatedb_api/constraint_resolution.py` (§2.2 の名前) へ移す。

| 項目 | 実測 (`2fde59a`) |
|---|---|
| 移動範囲 | `cell.py` L164-270 (2 関数。直前の L161 は `_FIELD_TYPE_VOCABULARY`、直後の L272 からは次の定数の説明コメントなので含めない) |
| 呼出し元 | `ApplicationCell.create_collection` (L1381、`_resolve_field_constraints`)、`add_field` (L1778)・`alter_field` (L2039) (`_validate_enum_declaration_with_path`) |
| leaf の import | `.errors` (`ResourceLimitError`・`ValidationError`)、`.field_types` (`_ConstraintDeclarationError`・`json_type_name`・`validate_enum_declaration`)。`field_types.py` は `typing` と `.errors` だけを import するので循環しない。注釈が無いので `__future__` は不要 |
| facade | `cell.py` が 2 名を import する。移動で未使用になる `validate_enum_declaration`・`_ConstraintDeclarationError` を `cell.py` の import から削除する (他 module とテストは `cell` から読まない)。`json_type_name` は L2032 が使うので残す |
| denial | `ValidationError` 3 件 (L199、L238、L252。4-key)、`ResourceLimitError` 1 件 (L267、`enum_members`) |
| 件数 pin | `cell.py` 47 → 44、`constraint_resolution.py` 3 |
| 行番号 allowlist | 対象は `backend_postgres.py` だけなので差分 0 |
| sib tuple | `constraint_resolution.py` を足す |
| `test_limit_class_vocabulary.py` | パッケージ直下の `*.py` を走査するので件数 36 は変わらない |
| 範囲内の位置参照 | L176「(`_resolve_field_constraints` below)」は 2 関数を同じ順で移すので leaf の中で成り立つ。L180・L192・L229 の「here」は同じ関数・同じ宣言を指す |
| 範囲外の位置参照 (40c) | 直す: `field_types.py` L256 と L288 の「`cell.py`'s own `_validate_enum_declaration_with_path`」、`cell.py` L4229-4230 と L4342-4343 の「`_resolve_field_constraints`/`add_field`/`alter_field` above」(3 名のうち移るのは `_resolve_field_constraints` だけ。X-4)。直さない: 両 peer の `tests/test_audit_query.py` (MitateDB L2473-2474、r2db L2688-2689) の `cell._validate_enum_declaration_with_path` (qualified name は facade で成り立つ。§5.10 の 10)、`MitateDB-api/tests/test_limit_class_vocabulary.py` L154 の件数説明の文字列「cell.py x3 … in `_resolve_field_constraints`」(V-4 と同じ扱い) |

| 触るファイル | 触らないファイル |
|---|---|
| `MitateDB-api/src/mitatedb_api/cell.py` (移動範囲を除き、import 1 行の追加と 2 名の削除、括弧書き 2 箇所)、新規 `MitateDB-api/src/mitatedb_api/constraint_resolution.py`、`MitateDB-api/src/mitatedb_api/field_types.py` (L256・L288 の括弧書きだけ)、`MitateDB-api/tests/test_constraints_declaration.py` (新規テスト 2 本)、S_M (`SCANNED_MODULES`、件数 pin、sib tuple)、`tools/tests/test_leaf_import_direction.py` (leaf 1 行、許可 `.errors`・`.field_types`) | `MitateDB-api/src/mitatedb_api/http.py` (変更セット 3)、`backend_postgres.py`、S_M の `_BACKEND_LAYER_ALLOWLIST`、`MitateDB-api/tests/test_limit_class_vocabulary.py`、両 peer の `tests/test_audit_query.py` (登録は `field_types.validate_enum_declaration` のまま)、r2db-api 全部、`conformance-tests/` |

| # | 完了条件 | 変異 (`file:操作`) | 赤になる test id (予想) |
|---|---|---|---|
| 1 | facade 互換 | `cell.py`: import から `_resolve_field_constraints` を外す | `MitateDB-api/tests/test_constraints_declaration.py::test_constraint_resolution_leaf_preserves_cell_facade` (新規。2 名の `is`)、`::test_field_constraints_unknown_key_is_rejected` (L1381 の NameError) |
| 2 | field_constraints の未知キーを拒否する | `constraint_resolution.py`: `if unknown_keys:` を `if False and unknown_keys:` にする | `MitateDB-api/tests/test_constraints_declaration.py::test_field_constraints_unknown_key_is_rejected` |
| 3 | nullable は bool だけ | `constraint_resolution.py`: `not isinstance(nullable, bool)` を `False and not isinstance(nullable, bool)` にする | `MitateDB-api/tests/test_constraints_declaration.py::test_field_constraints_nullable_not_a_boolean_is_refused` |
| 4 | 解決結果は total で、nullable の既定は true | `constraint_resolution.py`: `declared.get("nullable", True)` の `True` を `False` にする | `MitateDB-api/tests/test_constraints_declaration.py::test_catalog_field_constraints_round_trips_and_is_total` |
| 5 | enum の path は `field_constraints/<field>/enum` | `constraint_resolution.py`: `f"field_constraints/{field}/enum"` を `"enum"` にする | `MitateDB-api/tests/test_constraints_declaration.py::test_enum_on_json_typed_field_is_constraint_declaration` |
| 6 | enum 宣言の違反は `declared_type` を持つ | `constraint_resolution.py`: wrapper の `"declared_type": declared_type,` の行を削る | `MitateDB-api/tests/test_constraints_declaration.py::test_empty_enum_is_constraint_declaration`、`::test_enum_on_untyped_field_is_constraint_declaration_via_add_field` |
| 7 | enum の要素数は上限ちょうどまで許す | `constraint_resolution.py`: `len(validated_enum) > max_enum_members` を `>=` にする | `MitateDB-api/tests/test_constraints_declaration.py::test_create_entity_enum_at_exactly_max_enum_members_is_accepted` (新規。`max_enum_members=3` で 3 要素の `create_entity` が通る。既存の `::test_enum_members_limit_exceeded_refuses_before_anything_is_created` は 4 要素なので緑のまま) |
| 8 | 上限超過は `enum_members` の LIMIT_EXCEEDED | `constraint_resolution.py`: `limit_class="enum_members"` を外す | `MitateDB-api/tests/test_limit_class_vocabulary.py::test_every_resource_limit_error_call_site_declares_a_contract_limit_class`、`MitateDB-api/tests/test_constraints_declaration.py::test_enum_members_limit_exceeded_refuses_before_anything_is_created` |
| 9 | 移動先が `SCANNED_MODULES` に入る (40b) | S_M: `SCANNED_MODULES` から `constraint_resolution.py` を外す | `MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py::test_every_module_with_a_vocabulary_denial_is_accounted_for`、`::test_ast_full_count_matches_a_non_trivial_floor` |
| 10 | 件数 pin (`cell.py` 44、`constraint_resolution.py` 3) | `constraint_resolution.py`: `ValidationError("x", details={"violated_declaration": "request_schema"})` を raise する関数を 1 つ足す | `MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py::test_ast_full_count_matches_a_non_trivial_floor` |
| 11 | 移した denial が 4-key のまま | `constraint_resolution.py`: 未知キーの `ValidationError` から `details=` を外す | `MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py::test_every_choke_point_denial_carries_details_ast_full_count`、`::test_allowlist_entries_match_real_bare_call_sites` |
| 12 | 行番号 allowlist が実測と一致 | **監査照合**: 本 WP による `_BACKEND_LAYER_ALLOWLIST` の差分 0 | — |
| 13 | sib tuple に移動先が入る | `constraint_resolution.py`: `"field_constraints.nullable must be a boolean"` を allowlist の文言 `"storage backend rejected the request"` にする | `MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py::test_backend_layer_allowlist_entries_have_no_in_memory_sibling_denial` (tuple を更新しないと緑のまま) |
| 14 | leaf の import が許可リストの内だけ | `constraint_resolution.py`: `import os` を 1 行足す | `tools/tests/test_leaf_import_direction.py::test_leaf_modules_import_only_their_allowlisted_modules` |
| 15 | 新 leaf が分類される | 一覧から `constraint_resolution.py` の行を消す | `tools/tests/test_leaf_import_direction.py::test_every_src_module_is_classified` |
| 16 | 未使用になった import を削除した | **監査照合**: `cell.py` の import に `validate_enum_declaration`・`_ConstraintDeclarationError` が無く、コード上の参照も 0 件 (docstring の言及は残る) | — |
| 17 | 逐語移動と位置参照の括弧書き (40c) | **監査照合**: 2 つの docstring と関数内のコメントが逐語。括弧書きは `field_types.py` L256・L288、`cell.py` L4230・L4343 の 4 箇所だけ | — |
| 18 | 同型性を登録しない | **監査照合**: `_ISOMORPHIC_TARGETS` の差分 0 (登録は `field_types.validate_enum_declaration` で、移す 2 関数は登録外)、r2db `src/` の同名 def 0 件 | — |
| 19 | 既知の穴を記録する | **監査照合**: `test_limit_class_vocabulary.py` L154 の件数説明が古くなることが、完了時の実施記録に載る | — |

### 5.17 WP-1k — MitateDB provisional gate (CE4、**独立レビュー済み**)

**目的**: `cell.py` の `_deny_provisional_field` を leaf `MitateDB-api/src/mitatedb_api/provisional_gate.py` へ移す (CE3 と責務が違うので別 leaf。U-6。名前は X-2)。**変更セット 3 の統合後に着手する** (X-1)。

| 項目 | 実測 (`2fde59a`。WP-1j の統合後に取り直す) |
|---|---|
| 移動範囲 | `cell.py` L3828-3856 (1 関数。直前は `ApplicationCell._require_developer` の末尾、直後は L3858 の `class ApplicationRuntime`) |
| 呼出し元 | 無い (docstring のとおり到達不能)。`http.py` L474 の同名関数は別物で、`http.py` L534 はそちらを呼ぶ。§2.2 の CE4 行の「`http.py`」は誤りで、本行を正とする |
| leaf の import | `.errors` (`CapabilityError`) |
| facade | `cell.py` が 1 名を import する。`CapabilityError` は `cell.py` に残る 5 箇所が使う。未使用になる import は無い |
| denial | `CapabilityError` 1 件 (L3852。`details` あり) |
| 件数 pin | `cell.py` 44 → 43 (WP-1j 統合後の値から)、`provisional_gate.py` 1 |
| 行番号 allowlist | 差分 0 |
| sib tuple | `provisional_gate.py` を足す (§4 の m6) |
| 既存テスト | 直接のテストは無い (到達不能のため) |
| 範囲内の位置参照 (40c) | L3836-3837「`ApplicationRuntime`/`ApplicationDeveloper`'s own keyword-only-field gates below」: 2 class は `cell.py` に残る (L3858、L4387) ので、「below」の直後に「(in `cell.py`)」を付ける。2 class には gate の呼出しがもう無く、この記述は移動前から古いが、V-4 と同じく本文は直さない。「`http.py::_deny_provisional_field`」(2 箇所) と、r2db の「`structured.py`'s own `SCHEMA_OPERATIONS`」(r2db `structured.py` L332 に在る) は成り立つ |
| 範囲外の位置参照 (40c) | `errors.py` L284「(`cell.py`/`http.py`'s own `_deny_provisional_field`)」の `cell.py` の直後に「(in `provisional_gate.py`)」。`http.py` L500「(mirrors `cell.py`'s identical in-process counterpart)」も指す先が変わるので、変更セット 3 の統合後に L500 の文を取り直して付ける (X-1) |

| 触るファイル | 触らないファイル |
|---|---|
| `MitateDB-api/src/mitatedb_api/cell.py` (移動範囲を除き import 1 行)、新規 `MitateDB-api/src/mitatedb_api/provisional_gate.py`、`MitateDB-api/src/mitatedb_api/errors.py` (L284 の括弧書きだけ)、`MitateDB-api/src/mitatedb_api/http.py` (L500 の括弧書きだけ。X-1 の裁定と変更セット 3 統合後の実測による)、`MitateDB-api/tests/test_denial_details_and_request_id.py` (新規テスト 2 本)、S_M (`SCANNED_MODULES`、件数 pin、sib tuple)、`tools/tests/test_leaf_import_direction.py` (leaf 1 行、許可 `.errors`) | `http.py` の `_deny_provisional_field` の本体と呼出し、`backend_postgres.py`、S_M の `_BACKEND_LAYER_ALLOWLIST`、両 peer の `tests/test_audit_query.py`、r2db-api 全部、`conformance-tests/` |

| # | 完了条件 | 変異 (`file:操作`) | 赤になる test id (予想) |
|---|---|---|---|
| 1 | facade 互換 | `cell.py`: import から `_deny_provisional_field` を外す | `MitateDB-api/tests/test_denial_details_and_request_id.py::test_provisional_gate_leaf_preserves_cell_facade` (新規) |
| 2 | details の `violated_declaration` は `capability` | `provisional_gate.py`: `"capability"` を `"request_schema"` にする | `MitateDB-api/tests/test_denial_details_and_request_id.py::test_deny_provisional_field_raises_capability_unsupported_naming_the_field` (新規。`_deny_provisional_field("budget")` の例外型、文言、details を literal で固定する) |
| 3 | details の `field` は field 名 | `provisional_gate.py`: `"field": field_name` を削る | 同上 |
| 4 | 移動先が `SCANNED_MODULES` に入る (40b) | S_M: `SCANNED_MODULES` から `provisional_gate.py` を外す | `MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py::test_every_module_with_a_vocabulary_denial_is_accounted_for`、`::test_ast_full_count_matches_a_non_trivial_floor` |
| 5 | 件数 pin (`cell.py` 43、`provisional_gate.py` 1) | `provisional_gate.py`: `CapabilityError("x", details={"violated_declaration": "capability"})` を raise する関数を 1 つ足す | `MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py::test_ast_full_count_matches_a_non_trivial_floor` |
| 6 | 移した denial が 4-key のまま | `provisional_gate.py`: `details=` を外す | `MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py::test_every_choke_point_denial_carries_details_ast_full_count`、`::test_allowlist_entries_match_real_bare_call_sites` |
| 7 | 行番号 allowlist が実測と一致 | **監査照合**: 本 WP による `_BACKEND_LAYER_ALLOWLIST` の差分 0 | — |
| 8 | sib tuple に移動先が入る | `provisional_gate.py`: 文言を allowlist の文言 `"storage backend rejected the request"` にする | `MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py::test_backend_layer_allowlist_entries_have_no_in_memory_sibling_denial` (tuple を更新しないと緑のまま) |
| 9 | leaf の import が許可リストの内だけ | `provisional_gate.py`: `import os` を 1 行足す | `tools/tests/test_leaf_import_direction.py::test_leaf_modules_import_only_their_allowlisted_modules` |
| 10 | 新 leaf が分類される | 一覧から `provisional_gate.py` の行を消す | `tools/tests/test_leaf_import_direction.py::test_every_src_module_is_classified` |
| 11 | 逐語移動と位置参照の括弧書き (40c) | **監査照合**: docstring が逐語。括弧書きは leaf 内の L3837、`errors.py` L284、`http.py` L500 の 3 箇所だけ | — |
| 12 | 同型性を登録しない | **監査照合**: `_ISOMORPHIC_TARGETS` の差分 0。同じ peer の `http.py::_deny_provisional_field` とは登録が無く、本 WP でも足さない | — |
| 13 | 既知の穴を記録する | **監査照合**: L3833-3838 の caller list の記述が移動前から古いことが、完了時の実施記録に載る | — |

### 5.18 WP-1l — MitateDB PostgreSQL 予約名 (BP4、**独立レビュー済み**)

**目的**: `backend_postgres.py` の予約名の定数 2 つ (説明コメントを含む) と `PostgresBackend.check_reserved` の検査本体を、leaf `MitateDB-api/src/mitatedb_api/postgres_reserved_names.py` の関数 `_check_reserved_name(value, label)` へ移す。method は委譲で残す (§2.5 の「2 名 + method」。名前と形は X-2・X-3)。

| 項目 | 実測 (`2fde59a`) |
|---|---|
| 移動範囲 | `backend_postgres.py` L129-138 (L129-136 の説明コメント、`_RESERVED_EXACT`、`_RESERVED_PREFIX`) と、`check_reserved` の本体 L543-547 (`if` と `raise`) |
| 残すもの | `check_reserved` の `def` と L533-542 のコメント (identifier choke point の後半である理由で、method に属する)。本体は `_check_reserved_name(value, label)` の 1 行にする |
| self | `check_reserved` は `self` を読まない (実測)。`cell.py` L1107 が `self._backend.check_reserved(value, label)` で呼ぶので、method は残す (`backend.StorageBackend` の duck-typed 契約) |
| leaf の import | `.errors` (`ValidationError`・`violation`) |
| facade | `backend_postgres.py` が 3 名を import する。`ValidationError`・`violation` は残る denial が使う。未使用になる import は無い |
| denial | `ValidationError` 1 件 (L544。4-key、`identifier_syntax`) |
| 件数 pin | `backend_postgres.py` 24 → 23、`postgres_reserved_names.py` 1 |
| 行番号 allowlist | **20 件すべてが 14 行上へずれる** (実測): 549, 606, 655, 682, 739, 791, 816, 994, 1011, 1142, 1300, 1387, 1439, 1472, 1498, 1565, 1593, 1634, 1903, 1972。前提は import 1 行 (facade の説明コメントなし) と委譲 1 行。コメントを足すとずれ幅が変わるので、そのときは実測で書き直す |
| sib tuple | 足さない。backend 層の leaf で、§4 の m6 の対象 (ST3〜ST9、CE2〜CE4) の外。先例 `postgres_value_domain.py` も tuple に無い (X-3) |
| 既存テスト | PostgreSQL backend の `pg_` 接頭辞と `audit_events` の完全一致を固定するテストは無い (`MitateDB-api/tests` の grep 0 件)。SI-04 の穴として新規テストで塞ぐ |
| 位置参照 (40c) | L129-136 のコメントは leaf へ逐語で移り、「`check_reserved` is a method」は method が残るので成り立つ。method に残る L536「that module's own docstring」は `identifiers` を、L538「this backend」は `PostgresBackend` を指し、変わらない。範囲外の `identifiers.py` L11-12・`backend_sqlite.py` L138-139 の `backend_postgres.PostgresBackend.check_reserved`、`spec/CCR_DISPOSITION.md` L135・r2db `identifier_rules.py` L75・`docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md` L112 の `backend_postgres` の `_RESERVED_EXACT` は facade で成り立つので直さない。`docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md` L79 の「L98」は移動前から古い記録で直さない。**括弧書きは 0 箇所** |

| 触るファイル | 触らないファイル |
|---|---|
| `MitateDB-api/src/mitatedb_api/backend_postgres.py` (移動範囲を除き、import 1 行と `check_reserved` の本体)、新規 `MitateDB-api/src/mitatedb_api/postgres_reserved_names.py`、`MitateDB-api/tests/test_postgres.py` (新規テスト 2 本。PostgreSQL に接続しない)、S_M (`SCANNED_MODULES`、件数 pin、行番号 allowlist 20 件)、`tools/tests/test_leaf_import_direction.py` (leaf 1 行、許可 `.errors`) | `cell.py`、`backend_sqlite.py` (`_RESERVED` と `check_reserved` は対象外)、`backend.py`、`identifiers.py`、S_M の sib tuple、`spec/`、`docs/design/`、両 peer の `tests/test_audit_query.py`、r2db-api 全部、`conformance-tests/` |

| # | 完了条件 | 変異 (`file:操作`) | 赤になる test id (予想) |
|---|---|---|---|
| 1 | facade 互換 | `backend_postgres.py`: import から `_RESERVED_PREFIX` を外す (module 内の参照は無い) | `MitateDB-api/tests/test_postgres.py::test_postgres_reserved_names_leaf_preserves_backend_postgres_facade` (新規。3 名の `is`) |
| 2 | `pg_` で始まる名前を拒否する | `postgres_reserved_names.py`: `value.startswith(_RESERVED_PREFIX)` を `value == _RESERVED_PREFIX` にする | `MitateDB-api/tests/test_postgres.py::test_postgres_backend_check_reserved_refuses_pg_prefix_and_audit_events_exactly` (新規。`PostgresBackend.check_reserved(None, …)` で呼び、`"pg_x"` と `"audit_events"` の例外と details `{"violated_declaration": "identifier_syntax", "field": <label>}`、`"audit_events2"` と `"xpg_"` が通ることを literal で固定する) |
| 3 | `audit_events` は完全一致だけを拒否する | `postgres_reserved_names.py`: `value in _RESERVED_EXACT` を `value.startswith("audit_events")` にする | 同上 |
| 4 | `audit_events` を拒否する | `postgres_reserved_names.py`: `value in _RESERVED_EXACT or ` を削る | 同上 |
| 5 | details の `field` は label | `postgres_reserved_names.py`: `field=label` を `field="identifier"` にする | 同上 |
| 6 | method が leaf に委譲する | `backend_postgres.py`: `check_reserved` の委譲の行を `return None` にする | 同上 |
| 7 | 移動先が `SCANNED_MODULES` に入る (40b) | S_M: `SCANNED_MODULES` から `postgres_reserved_names.py` を外す | `MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py::test_every_module_with_a_vocabulary_denial_is_accounted_for`、`::test_ast_full_count_matches_a_non_trivial_floor` |
| 8 | 件数 pin (`backend_postgres.py` 23、`postgres_reserved_names.py` 1) | `postgres_reserved_names.py`: `ValidationError("x", details=violation("request_schema"))` を raise する関数を 1 つ足す | `MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py::test_ast_full_count_matches_a_non_trivial_floor` |
| 9 | 移した denial が 4-key のまま | `postgres_reserved_names.py`: `details=` を外す | `MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py::test_every_choke_point_denial_carries_details_ast_full_count`、`::test_allowlist_entries_match_real_bare_call_sites` |
| 10 | 行番号 allowlist 20 件が実測と一致 (40b) | S_M: 1 件を移動前の行番号に戻す | `MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py::test_allowlist_entries_match_real_bare_call_sites` |
| 11 | leaf の import が許可リストの内だけ | `postgres_reserved_names.py`: `import os` を 1 行足す | `tools/tests/test_leaf_import_direction.py::test_leaf_modules_import_only_their_allowlisted_modules` |
| 12 | 新 leaf が分類される | 一覧から `postgres_reserved_names.py` の行を消す | `tools/tests/test_leaf_import_direction.py::test_every_src_module_is_classified` |
| 13 | sib tuple を変えない (X-3) | **監査照合**: sib tuple の差分 0 | — |
| 14 | 逐語移動 (40c) | **監査照合**: L129-136 のコメントが leaf に逐語、L533-542 のコメントが method に逐語で残る。leaf の `if` 文は移動前の method 本体と AST 同一。括弧書き 0 箇所 | — |
| 15 | 同型性を登録しない | **監査照合**: `_ISOMORPHIC_TARGETS` の差分 0、r2db `src/` の同名 def 0 件。`backend_sqlite.SQLiteBackend.check_reserved` は変えない | — |
| 16 | 既知の穴を記録する | **監査照合**: 移動前は PostgreSQL の予約名 (SI-04) を固定するテストが無かったこと (本 WP で塞いだ) が、完了時の実施記録に載る | — |

### 5.19 重なり・順序・未確定 (v1.7 追記)

**触るパスの重なり** (L = `tools/tests/test_leaf_import_direction.py`、S_M = §5.15、C = `MitateDB-api/src/mitatedb_api/cell.py`、H = `MitateDB-api/src/mitatedb_api/http.py`):

| | WP-1j (CE3) | WP-1k (CE4) | WP-1l (BP4) | 変更セット 3 |
|---|---|---|---|---|
| WP-1j | — | × L、S_M、C | × L、S_M | ○ |
| WP-1k | × | — | × L、S_M | × H (L500 の括弧書き。X-1) |
| WP-1l | × | × | — | ○ |

- **順序**: 1 branch で WP-1j → WP-1l → WP-1k の直列 (3 件とも L と S_M を触り、1j と 1k は C も触る。X-1)。1l は 1j / 1k のコードに依存せず、件数 pin と allowlist も別 module の値なので、1l を先にしても値は変わらない。1k は変更セット 3 の統合後に行う。
- **U-1 / U-2**: 変更セット 3 が触る MitateDB `http.py`・r2db `control_plane.py`・r2db `service.py`・`docs/code-history/` を、1j と 1l は触らない。変更セット 3 は両 peer の `tests/` を触らないので、共有する静的テストも無い。1k だけが `http.py` L500 に括弧書きを要するので、1k は変更セット 3 の統合後に行い、L500 の文を取り直す (X-1)。
- `cell.py`・`backend_postgres.py` のコメント整理は抽出の後 (U-2)。`backend_postgres.py` は BP1〜BP3 も残るので、整理は BP 系の抽出がすべて済んでから行う。
- 設計 §9.3: 3 件とも `_gate` とその呼出し経路を動かさない (§5.15)。
- 並行 branch `codex/mitatedb-operation-depth-platform-plan` は、main との差に MitateDB の `src/`・`tests/` と `tools/tests` を含まない (実測)。

**未確定 (監督判断待ち)**:

| # | 点 |
|---|---|
| X-1 | WP-1k の `http.py` L500「(mirrors `cell.py`'s identical in-process counterpart)」の括弧書き。案 (a) 変更セット 3 の統合後に 1k を行い、残った文に付ける。案 (b) 1k では付けず、V-4 と同じく既知の穴にする |
| X-2 | leaf 名。CE4 は `provisional_gate.py`、BP4 は `postgres_reserved_names.py` と関数 `_check_reserved_name` (§2.2・§2.5 は未定)。CE3 は §2.2 の `constraint_resolution.py` |
| X-3 | BP4 の形。検査本体を leaf の関数へ移し、method は委譲で残す (method 内のコメントも method に残す)。sib tuple には足さない |
| X-4 | `cell.py` L4230・L4343 の「above」は 3 名を指し、移るのは `_resolve_field_constraints` だけ。括弧書きを「(`_resolve_field_constraints` now in `constraint_resolution.py`)」とするか |

**監督裁定 (2026-09-14)**:

| # | 裁定 |
|---|---|
| X-1 | 案 (a)。W-2 により位置参照は各 WP の統合時点で正しくする。順序は WP-1j → WP-1l → WP-1k とし、1k は変更セット 3 の統合後に L500 の文を取り直して括弧書きを付ける |
| X-2 | 提案名で進める (`constraint_resolution.py`、`provisional_gate.py`、`postgres_reserved_names.py` の `_check_reserved_name`) |
| X-3 | 提案どおり。検査本体を leaf に移し、method は委譲で残す。sib tuple に足さない理由は独立レビューで確かめる |
| X-4 | 「above」の直後に「(`_resolve_field_constraints` in `constraint_resolution.py`)」を付ける。残る 2 名には付けない。「now」などの経緯語は使わない |
| X-5 | CE4 (`_deny_provisional_field`) は到達不能だが、docstring の記録どおり次の provisional capability 用の仕組みとして残す。削除せずに抽出する |

### 5.20 BP1・BP2 と WP-2 判断材料の共通 (v1.8 追記、**独立レビュー待ち**)

| 項目 | 内容 |
|---|---|
| 対象 | §4 の順番の付かない行から BP1 → BP2 (WP-1m / 1n、MitateDB `backend_postgres.py`) と、WP-2 の CE1 ↔ r2db `_canonical_where_json` の判断材料 (§5.23) |
| 行番号 | `f70afb0` の実測。1n の行は 1m の統合でずれる。allowlist の値は、各節の前提どおりの移動を写しに当て、S_M と同じ AST 走査で数えた値 |
| baseline (導出) | root 3,370 (`r2db-api/tests` 1,275 / `MitateDB-api/tests` 1,100 / `conformance-tests` 995)、`tools/tests` 109。設計 §10.6 の WP-1l の root ゲート 3370 と一致する。着手時に collect-only で確かめる |
| 変更クラス、テンプレート、検証コマンド | §5.15 と同じ。C-1〜C-3 を各表の末尾に付ける |
| 設計 §3 の禁止境界 | BP1 は固定の `sql.SQL` 定数と dict だけで execute しない (設計 §3.1 の「SQL object の組立」。先例 r2db `postgres_types.py`、設計 §8.1 の 1)。BP2 は値の検査だけ。connection / cursor、transaction、lock、`SET LOCAL` timeout、driver exception mapping (layer (ii) の `except psycopg.Error`)、`_execute`、DDL 文の組立 (`create_collection` L1030・`add_field` L1164)、`field_domains` の catalog 読取は `backend_postgres.py` に残す。WP-4 へ回すものは、既に WP-4 の BP3 以外に無い |
| sib tuple | 2 件とも足さない (backend 層。X-3 と `postgres_value_domain.py` の先例) |

### 5.21 WP-1m — MitateDB PostgreSQL の型写像 (BP1、**独立レビュー待ち**)

**目的**: `backend_postgres.py` の型写像の定数 4 つ (説明コメントを含む) を leaf `MitateDB-api/src/mitatedb_api/postgres_types.py` (§2.5 の名前。r2db に同名 file があるが中身は別) へ移す。

| 項目 | 実測 (`f70afb0`) |
|---|---|
| 移動範囲 | `backend_postgres.py` L130-192 (`_TYPES`・`_TYPE_SQL`・`_DOMAIN_BY_DATA_TYPE`・`_TEXT_DOMAIN_BY_DECLARED_TYPE` と、L130-146・L151-167・L174-186 の説明コメント)。直後の空行 L193-194 も除く |
| 呼出し元 | `_TYPE_SQL`: `create_collection` (L1030)・`add_field` (L1164)。domain 表: `field_domains` (L613-616)。`_TYPES` は `_TYPE_SQL` の組立にだけ使う |
| leaf の import | `psycopg` (`from psycopg import sql`)。§2.5 の `field_types` は使わない |
| facade | コードから読む 3 名 (`_TYPE_SQL`・`_DOMAIN_BY_DATA_TYPE`・`_TEXT_DOMAIN_BY_DECLARED_TYPE`) を import 1 行で読む。`_TYPES` はコードからの参照が 0 なので facade に残さず、import にも入れない (Y-7)。未使用になる import は無い |
| denial | 無い。件数 pin・`SCANNED_MODULES`・sib は差分 0 |
| 行番号 allowlist | 20 件すべてが 64 行上へ: 485, 542, 591, 618, 675, 727, 752, 930, 947, 1078, 1236, 1323, 1375, 1408, 1434, 1501, 1529, 1570, 1839, 1908。前提は import 1 行 (facade の説明コメントなし) と、括弧書きで行が増えないこと。行が増えればずれ幅が変わる |
| 範囲内の位置参照 (40c) | 付ける: L134「this module's own `encode_value` below」の below、L145「no method in this module」の this module、L161「see `field_domains` below」の below の直後に「(in `backend_postgres.py`)」。付けない: L175「this backend's own `_check_domain` category」(this backend は PostgreSQL backend 層を指す。WP-1l の先例) |
| 範囲外の位置参照 (40c) | 付ける: `backend_postgres.py` L297「See this module's own `_TYPES` comment」と L566「(`_DOMAIN_BY_DATA_TYPE`'s own corrected comment above)」の直後と、`cell.py` L157・`MitateDB-api/tests/test_postgres.py` L1227 のコメントが名指す `_TYPES` の直後に「(in `postgres_types.py`)」(Y-7)。書き換える (W-2): `postgres_value_domain.py` L29-30 の「(in `backend_postgres.py`)」を「(in `postgres_types.py`)」。直さない: L41「this backend's own `_TYPES`」(this backend)、`docs/design/` の記録 |

| 触るファイル | 触らないファイル |
|---|---|
| `MitateDB-api/src/mitatedb_api/backend_postgres.py` (移動範囲を除き、import 1 行と括弧書き 2 箇所)、新規 `MitateDB-api/src/mitatedb_api/postgres_types.py`、`MitateDB-api/src/mitatedb_api/postgres_value_domain.py` (L29-30 の括弧書きの書換えだけ)、`MitateDB-api/src/mitatedb_api/cell.py` (L157 の括弧書きだけ。WP-1k と重なるが 1m → 1n → 1k の直列なので問題ない)、`MitateDB-api/tests/test_postgres.py` (新規テスト 1 本と L1227 の括弧書き。接続しない)、S_M (allowlist 20 件と移動記録のコメント)、`tools/tests/test_leaf_import_direction.py` (leaf 1 行、許可 `psycopg`) | `backend_sqlite.py` (`_TYPES` は別物)、`http.py`、S_M の件数 pin・`SCANNED_MODULES`・sib、両 peer の `tests/test_audit_query.py`、r2db-api 全部、`conformance-tests/`、`docs/design/` |

| # | 完了条件 | 変異 (`file:操作`) | 赤になる test id (予想) |
|---|---|---|---|
| 1 | (欠番。`_TYPES` を facade に残さないので facade テストと変異を置かない。Y-7) | — | — |
| 2 | `boolean` は物理 `INTEGER` | `postgres_types.py`: `"boolean": "INTEGER"` を `"BOOLEAN"` にする | `MitateDB-api/tests/test_postgres.py::test_postgres_types_pin_native_column_types_and_domains` (新規。4 表を literal で固定する)、`::test_declared_type_registry_round_trips_every_contract_type` (**後者は実測で確定する**) |
| 3 | `_TYPE_SQL` は `sql.SQL` の定数 (m-7) | `postgres_types.py`: `sql.SQL(native)` を `sql.Identifier(native)` にする | `MitateDB-api/tests/test_postgres.py::test_postgres_types_pin_native_column_types_and_domains` |
| 4 | 物理型から domain への逆写像 | `postgres_types.py`: `"bigint": "int64"` を `"int32"` にする | 同上 |
| 5 | text 系の宣言型は 4 つの別 domain | `postgres_types.py`: `"object": "object"` を `"string"` にする | 同上 (挙動は変わらないので既存テストは緑のまま) |
| 6 | 行番号 allowlist 20 件が実測と一致 (40b) | S_M: 1 件を移動前の値に戻す | `MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py::test_allowlist_entries_match_real_bare_call_sites` |
| 7 | S_M の他の値は不変 | **監査照合**: S_M の差分が allowlist 20 件と、その移動記録のコメント (WP-1l の先例 S_M L193-200) だけ | — |
| 8 | leaf の import が許可リストの内だけ | `postgres_types.py`: `import os` を 1 行足す | `tools/tests/test_leaf_import_direction.py::test_leaf_modules_import_only_their_allowlisted_modules` |
| 9 | 新 leaf が分類される | 一覧から `postgres_types.py` の行を消す | `tools/tests/test_leaf_import_direction.py::test_every_src_module_is_classified` |
| 10 | 逐語移動と位置参照 (40c) | **監査照合**: 説明コメントが逐語。括弧書きは leaf の L134・L145・L161、`backend_postgres.py` の L297・L566、`cell.py` L157、`test_postgres.py` L1227 の 7 箇所、書換えは `postgres_value_domain.py` L29-30 の 1 箇所だけ | — |
| 11 | 同型性を登録しない | **監査照合**: `_ISOMORPHIC_TARGETS` の差分 0、r2db `src/` の同名定義 0 件。`backend_sqlite._TYPES` は変えない | — |

### 5.22 WP-1n — MitateDB PostgreSQL の値 domain gate (BP2、**独立レビュー待ち**)

**目的**: `backend_postgres.py` の `_validate_value_domain` を既存 leaf `MitateDB-api/src/mitatedb_api/postgres_value_domain.py` の `_check_domain` の直前へ移す (§2.5)。`PostgresBackend.encode_value` は呼出しのまま残す。**WP-1m の統合後に着手する。**

| 項目 | 実測 (`f70afb0`。1m の統合後に取り直す) |
|---|---|
| 移動範囲 | `backend_postgres.py` L195-309 (docstring と関数内コメントを含む) と直後の空行 L310-311 |
| 呼出し元 | `PostgresBackend.encode_value` (L1320)。テストは `backend_postgres` から読む (`MitateDB-api/tests/test_postgres.py` L1444、L1463) |
| leaf の import | 変わらない (`.errors` の `ValidationError`・`observed_type_of`・`violation`)。`_check_domain` は同じ module |
| facade | L100 の import に `_validate_value_domain` を足す。移動で未使用になる `observed_type_of` を L91-94 の import から削除する (1 行減る)。`_check_domain` もコードからは参照されなくなる (残るのはコメント L1308 だけ) が、`MitateDB-api/tests/test_postgres.py` L1497・L1529 が `_check_domain`・`_INT_DOMAIN_RANGES` を `backend_postgres` から import するので facade に残す (Y-3)。L98-99 のコメントは facade で成り立つので直さない。import の行数は変わらないので allowlist の値は下記のまま |
| denial | `ValidationError` 2 件 (L267 NUL、L293 lone surrogate。4-key) |
| 件数 pin | `backend_postgres.py` 23 → 21、`postgres_value_domain.py` 4 → 6 |
| `SCANNED_MODULES`・sib・L | 差分 0 (移動先は走査済みの backend 層 leaf、許可リストも不変) |
| 行番号 allowlist | 1m の値からさらに 118 行上へ: 367, 424, 473, 500, 557, 609, 634, 812, 829, 960, 1118, 1205, 1257, 1290, 1316, 1383, 1411, 1452, 1721, 1790。前提は 1m の前提に加え、import の変更が上記 2 つだけで、括弧書きで行が増えないこと |
| 範囲内の位置参照 (40c) | 付ける: L280「this module's own layer (ii) backstop」と L281「this module's per-DML-method final clause」の直後に「(in `backend_postgres.py`)」。L297 の括弧書きは 1m で付けたまま移る。付けない: L272「immediately above」、L285「above」、L301「below」(同じ関数の中)、L198 の `PostgresBackend.encode_value`、L217 の `cell.py::_prepare_values` (指す先は動かない) |
| 範囲外の位置参照 (40c) | 書き換える (W-2): `backend_postgres.py` L1308-1309「functions below (`_check_domain` now in `postgres_value_domain.py`)」は 2 関数とも移るので 2 名を覆う形に (Y-4)。`postgres_value_domain.py` L25-27「above (in `backend_postgres.py`; this is …)」から「in `backend_postgres.py`; 」を除く (Y-2)。付ける: `backend_sqlite.py` L688「`backend_postgres.py::_validate_value_domain`」の直後に「(in `postgres_value_domain.py`)」(§5.6 の `cell.py::_measure_request_bytes` の先例)。`field_types.py` L12「Backend domain checks (`backend_postgres.py`)」の既存の括弧の直後に、入れ子にせず「 (in `postgres_value_domain.py`)」(Y-9)。直さない: `MitateDB-api/tests/test_http.py` L815・`field_types.py` L188 の `backend_postgres._validate_value_domain` (facade)、`test_postgres.py` の名前だけの言及、`docs/design/` の記録 |

| 触るファイル | 触らないファイル |
|---|---|
| `MitateDB-api/src/mitatedb_api/backend_postgres.py` (移動範囲を除き、import 2 箇所と L1309 の書換え)、`MitateDB-api/src/mitatedb_api/postgres_value_domain.py` (関数の追加、括弧書き 2 箇所、L26 の書換え)、`MitateDB-api/src/mitatedb_api/backend_sqlite.py` (L688 の括弧書きだけ)、`MitateDB-api/src/mitatedb_api/field_types.py` (L12 の括弧書きだけ)、`MitateDB-api/tests/test_postgres.py` (新規テスト 2 本)、S_M (件数 pin、allowlist 20 件、移動記録のコメント、L75 の「carries 4」を 6 に) | `cell.py`、`http.py`、`MitateDB-api/tests/test_http.py`、S_M の `SCANNED_MODULES`・sib、`tools/tests/test_leaf_import_direction.py`、両 peer の `tests/test_audit_query.py`、r2db-api 全部、`conformance-tests/` |

| # | 完了条件 | 変異 (`file:操作`) | 赤になる test id (予想) |
|---|---|---|---|
| 1 | facade 互換 | `backend_postgres.py`: L100 の import から `_validate_value_domain` を外す | `MitateDB-api/tests/test_postgres.py::test_postgres_value_domain_leaf_preserves_backend_postgres_facade` (新規。`_validate_value_domain` の `is`。`_check_domain`・`_INT_DOMAIN_RANGES` は L1497・L1529 の既存テストが `backend_postgres` から読む)、`::test_validate_value_domain_accepts_none_for_every_domain` |
| 2 | NULL は全 domain で通す (M-5) | `postgres_value_domain.py`: `if value is None: return None` を削る | `MitateDB-api/tests/test_postgres.py::test_validate_value_domain_accepts_none_for_every_domain` |
| 3 | NUL を 4-key で拒否する | `postgres_value_domain.py`: NUL の条件を `False and …` にする | `MitateDB-api/tests/test_postgres.py::test_postgres_only_value_domain_denials_reachable_from_a_normal_client_request_carry_the_4_key_form` (layer (ii) の denial は details を持たない) |
| 4 | lone surrogate を拒否する | `postgres_value_domain.py`: surrogate の条件を `False and …` にする | 同上、`::test_transact_lone_surrogate_value_is_deterministic_validation_failure_and_earlier_entity_unchanged` |
| 5 | bool は domain 検査の前に int にする | `postgres_value_domain.py`: `value = int(value)` を `pass` にする | `MitateDB-api/tests/test_postgres.py::test_validate_value_domain_converts_bool_to_int_before_the_domain_check` (新規。`_validate_value_domain(True, domain="int32")` が `1` で型が `int`) |
| 6 | domain 検査を呼ぶ | `postgres_value_domain.py`: `_check_domain` を呼ぶ代入行を `pass` に置き換える (削ると `if` の中身が空になり SyntaxError) | `MitateDB-api/tests/test_postgres.py::test_validate_value_domain_actually_invokes_the_domain_check` |
| 7 | details の `field` は呼出し側の path | `postgres_value_domain.py`: NUL の `field=field` を `field=None` にする | `MitateDB-api/tests/test_postgres.py::test_postgres_only_value_domain_denials_reachable_from_a_normal_client_request_carry_the_4_key_form` |
| 8 | 件数 pin (`backend_postgres.py` 21、`postgres_value_domain.py` 6) | `postgres_value_domain.py`: `ValidationError("x", details=violation("request_schema"))` を raise する関数を 1 つ足す | `MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py::test_ast_full_count_matches_a_non_trivial_floor` |
| 9 | 移した denial が 4-key のまま | `postgres_value_domain.py`: surrogate の `details=` を外す | `MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py::test_every_choke_point_denial_carries_details_ast_full_count`、`::test_allowlist_entries_match_real_bare_call_sites` |
| 10 | 行番号 allowlist 20 件が実測と一致 (40b) | S_M: 1 件を 1m の値に戻す | `MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py::test_allowlist_entries_match_real_bare_call_sites` |
| 11 | leaf の import が許可リストの内だけ | `postgres_value_domain.py`: `import os` を 1 行足す | `tools/tests/test_leaf_import_direction.py::test_leaf_modules_import_only_their_allowlisted_modules` |
| 12 | 未使用になった import を削除した | **監査照合**: `backend_postgres.py` の import と本文に `observed_type_of` が無い | — |
| 13 | `SCANNED_MODULES`・sib・L は不変 | **監査照合**: 3 つの差分 0。S_M の差分は件数 pin、allowlist 20 件、移動記録のコメント (WP-1l の先例 S_M L193-200)、L75 の「carries 4」→ 6 だけ | — |
| 14 | 逐語移動と位置参照 (40c) | **監査照合**: docstring と関数内コメントが逐語。括弧書きは leaf の L280・L281、`backend_sqlite.py` L688、`field_types.py` L12 の 4 箇所、書換えは `backend_postgres.py` L1309 と `postgres_value_domain.py` L26 の 2 箇所だけ | — |
| 15 | 同型性を登録しない | **監査照合**: `_ISOMORPHIC_TARGETS` の差分 0、r2db `src/` の同名 def 0 件 | — |

### 5.23 WP-2 判断材料 — CE1 ↔ r2db `_canonical_where_json` (v1.8 追記)

| 事実 | 内容 |
|---|---|
| 同型性テスト | 両 peer の `tests/test_audit_query.py` の `_ISOMORPHIC_TARGETS` (137 行、行数 pin あり) と `test_peer_local_helpers_are_isomorphic_to_the_sibling_peer`。normalizer (`_normalize`) が吸収するのは docstring、package 名、型名 `ResourceLimits`/`FoundationConfig`、env 接頭辞 `R2DB_`/`MITATEDB_`、行末空白、空行だけ。`tools/tests` に同型性テストは無い |
| 本文 | MitateDB `delete_confirmation.py:18` は `def _canonical_where_json(filters)` で `json.dumps(payload, sort_keys=True, separators=(",", ":"))`。r2db `delete_confirmation.py:58` は `def _canonical_where_json(where: "list[Predicate]") -> str` で `json.dumps(payload, sort_keys=True, ensure_ascii=True)` (区切りは既定)。引数名・注釈・区切り文字が違い、正規化後も一致しない。出力の byte 列も違う |
| 契約 | `destructive_confirmation.phrase_construction.spelling` は綴りを実装定義とし、peer 間の互換面ではないとする。規範は `spec/data-service-api.v1.json` L578-583 の規則 (per-request の値を入れない、決定性、scope を含み衝突しない、再作成可能な対象の state fingerprint、identifier 検証済みの名前だけ、有界) |
| 変更クラス | 登録は `_ISOMORPHIC_TARGETS` の増加で Class D (設計 §6)。本文を揃えると片側の digest が変わり、配備時に発行済みの phrase が一度無効になる |

| 案 | 内容 | 評価 |
|---|---|---|
| A | 登録しない。差の理由を WP-2 の記録に残す (設計 §4 WP-2 の「片側固有」) | 変更なし。未固定の性質は穴のまま |
| B | 片側の本文を他方へ揃えて登録し、両表・full-content pin・行数 pin を同時に更新する | Class D。契約は綴りの一致を求めず、本文同型を保つ合理的な理由が無い (設計 §3.1 末尾、D-3) |
| C | A に加え、契約の規則に揃えた性質を各 peer のテストで literal に固定する。コードは共有しない。性質: 入れ子の key 順、list 順の保持、非 ASCII の escape、scope が違えば phrase が違う、値の型の区別 (`1`・`"1"`・`true` で digest が別)、schema_revision が変われば phrase が変わる (state fingerprint)、per-request の値 (request_id など) が入らない、256 文字以内 (Bounded) | Class B。MitateDB の非 ASCII の穴 (設計 §10.2 の 2) を塞ぐ。WP-2a の完了条件に「R-39 の (1b) と (1g) を閉じ、R-39 行を更新する」を入れる (Y-8) |

**推奨: C。** 共通なのは契約 `phrase_construction` の規則であって本文ではなく、綴りは契約上実装定義である。性質は peer ごとのテストで固定し、同型性表は増やさない。

### 5.24 重なり・順序・未確定 (v1.8 追記)

**触るパスの重なり** (L・S_M は §5.15、P = `MitateDB-api/src/mitatedb_api/backend_postgres.py`、V = `MitateDB-api/src/mitatedb_api/postgres_value_domain.py`、T = `MitateDB-api/tests/test_postgres.py`、C = `MitateDB-api/src/mitatedb_api/cell.py`):

| | WP-1m (BP1) | WP-1n (BP2) | WP-1k (CE4) | 変更セット 3 |
|---|---|---|---|---|
| WP-1m | — | × S_M、P、V、T | × L、S_M、C (L157 のコメント) | ○ |
| WP-1n | × | — | × S_M | ○ |

- **順序**: WP-1m → WP-1n の直列。WP-1k とは S_M (1m は L と C も) を共有するので直列にする。1k は変更セット 3 を待つので **1m → 1n → 1k** を推奨する。1k が先に着手できても値は衝突しない (1k は `cell.py` の件数 pin・`SCANNED_MODULES`・sib を、BP 系は `backend_postgres.py`・`postgres_value_domain.py` の件数 pin と allowlist を書く)。
- **U-1 / U-2**: 2 件とも変更セット 3 のファイル (MitateDB `http.py`、r2db `control_plane.py`・`service.py`) を触らない。§5.19 の「`backend_postgres.py` の整理は BP 系の抽出がすべて済んでから」は、BP3 が WP-4 (manifest 未作成) なので整理を WP-4 まで延ばす。1n の後・WP-4 の前に置き、WP-4 と並行しなければ U-1 は守れる (Y-5)。整理の変更セットは allowlist の行を動かすので S_M の数値を触る (変更セット 2 の先例)。
- **設計 §3**: §5.20。**設計 §9.3**: 1m が触る `cell.py` は L157 のコメントだけで、`_gate` とその呼出し経路を動かさない。1n は `cell.py` を触らない。

**未確定 (監督判断待ち)**:

| # | 点 |
|---|---|
| Y-1 | BP1 を WP-1 で行う (§2.5 は「1 後続 又は 4」)。execute しない定数だけの leaf で、r2db の先例 `postgres_types.py` も WP-1 相当 (設計 §8.1 の 1) |
| Y-2 | BP2 の置き場所を `_check_domain` の直前にし、`postgres_value_domain.py` L26 の括弧書きから「in `backend_postgres.py`; 」を除く (W-2 の書換え) |
| Y-3 | `_check_domain` は 1n の後に `backend_postgres.py` のコードから参照されなくなるが、facade に残す。L98-99 のコメントは直さない |
| Y-4 | `backend_postgres.py` L1309 の既存の括弧書き「(`_check_domain` now in `postgres_value_domain.py`)」を「(both in `postgres_value_domain.py`)」に書き換える (X-4 により「now」は使わない) |
| Y-5 | `backend_postgres.py` のコメント整理を 1n の後、WP-4 の前に置く (§2.5・§4・§5.19 の U-2 の読替え) |
| Y-6 | WP-2 の CE1 は §5.23 の案 C |
| Y-7 | (監督裁定) Y-3 を `_TYPES` にも当てる。コードからの参照が 0 なので facade に残さず import にも入れない。facade テストと §5.21 の変異 1 は置かず、`cell.py` L157・`test_postgres.py` L1227 の `_TYPES` に「(in `postgres_types.py`)」を付ける |
| Y-8 | (監督裁定) §5.23 案 C の性質を契約 L578-583 の規則に揃え、WP-2a の完了条件に「R-39 の (1b) と (1g) を閉じ、R-39 行を更新する」を入れる |
| Y-9 | (監督裁定) 1n で `field_types.py` L12 の「Backend domain checks (`backend_postgres.py`)」の括弧の直後に、入れ子にせず「 (in `postgres_value_domain.py`)」を付ける |

**監督裁定 (2026-09-15)**:

| # | 裁定 |
|---|---|
| Y-1 | BP1 は WP-1 で行う (WP-1m) |
| Y-2 | 提案どおり。BP2 は `_check_domain` の直前に置き、L26 の括弧書きは W-2 で書き換える |
| Y-3 | `_check_domain` の facade 名は、1n の後も tests 又は他 module が `backend_postgres` から読むときだけ残す。読む箇所が無ければ、未使用 import として同じ WP で削除する (L98-99 のコメントも合わせて判断する) |
| Y-4 | 提案どおり「(both in `postgres_value_domain.py`)」に書き換える |
| Y-5 | `backend_postgres.py` のコメント整理は WP-1n の後、WP-4 の前に置く。WP-4 と並行しない |
| Y-6 | 案 C。性質のテストは WP-1n と WP-1k の後に、Class B の小さな WP (WP-2a) として両 peer に足す。同型性表は増やさない |

### 5.25 WP-2a — 削除確認 phrase の契約規則をテストで固定 (Y-6・Y-8、v1.9 追記、**独立レビュー待ち**)

**目的**: コードは変えず、両 peer の `delete_confirmation.py` (`_canonical_where_json` と delete phrase の組立) について、契約 `spec/data-service-api.v1.json` L578-583 の規則のうち未固定の性質をテストで固定する。綴りは契約上実装定義 (`phrase_construction.spelling`) なので、テストは綴りを比べず、等しい・違う・長さ・部分文字列の関係で固定する。両 peer に同名の helper を足さず、`_ISOMORPHIC_TARGETS` も増やさない。

| 項目 | 内容 |
|---|---|
| 変更クラス | **B** (両 peer の `tests/` だけ。`src/`・`conformance-tests/` は変えない) |
| 着手条件 | WP-1n・WP-1k が main に統合済み (`13241c2`。Y-6 の条件)。R-39 行の更新は、同じ worktree で設計書とロードマップを編集している別担当の統合後に、監督の記録コミットで行う |
| baseline (導出) | root 3,375 (`r2db-api/tests` 1,275 / `MitateDB-api/tests` 1,105 / `conformance-tests` 995)、`tools/tests` 109。設計 §10.7 の WP-1k の root ゲート 3375 と一致する。着手時に collect-only で確かめる |
| 変異の規律 | 変異は helper の本体に一時的に当て、復元を sha256 で照合する (§5 共通表)。既存テストでも赤になる変異は新規テストの証拠にならない (偽の緑を隠す) ので、**既存テストが緑のまま新規テストだけが赤になる変異**を選ぶ |
| 綴りの差 | 両 peer の phrase は同じ形 (`DELETE <対象> @where=<16 桁> @schema_revision=<n>`) だが、canonical JSON の区切りが違う (MitateDB `","`・`":"`、r2db は既定の `", "`・`": "`) ので、同じ where でも digest は違う。契約上の実装定義なので、テストはこの差を固定しない |

**既存テストが固定している性質** (`13241c2` の実測):

| 性質 (契約の規則) | MitateDB | r2db | 本 WP |
|---|---|---|---|
| 入れ子の key 順 (決定性) | `MitateDB-api/tests/test_foundation.py::FoundationTests::test_delete_confirmation_leaf_preserves_cell_facade_and_phrase_shape` | `r2db-api/tests/test_foundation.py::test_canonical_where_json_sorts_nested_keys_and_escapes_non_ascii` | 足さない |
| list 順の保持 | `MitateDB-api/tests/test_foundation.py::FoundationTests::test_canonical_where_json_key_sorts_each_filter_preserves_list_order_never_stringifies` | 上記 r2db テストの literal が付随的に固定するだけ | r2db に足す (Z-2 裁定) |
| 非 ASCII の escape | **無い** (R-39 (1b)) | 上記 r2db テスト | MitateDB に足す |
| scope が違えば phrase が違う (規則 3) | `conformance-tests/test_c06_destructive_confirmation.py::test_c06_v3_confirmation_exact_match_required` (entity 違いと where 違い。両 peer の adapter で走る) | 同左 | 足さない |
| schema_revision が変われば phrase が変わる (規則 4) | `MitateDB-api/tests/test_foundation.py::FoundationTests::test_delete_confirmation_phrase_is_invalidated_by_a_subsequent_add_field` | `r2db-api/tests/test_foundation.py::test_delete_phrase_invalidated_by_drop_recreate_of_the_same_entity_under_the_same_name` | 足さない |
| 256 以内 (規則 6) | 本体 L83 の `assert` だけで、境界を固定するテストは無い | `_PHRASE_MAX_LENGTH` は guard としてだけ使われる (R-39 (1g)) | 両 peer に足す |
| per-request の値が入らない (規則 1) | `conformance-tests/test_c06_destructive_confirmation.py::test_c06_v4_phrase_is_deterministic_and_requester_independent` (同じ要求の 2 回、別 role の credential)。helper の引数に request 由来の値は無い | 同左 | 足さない (request_id と `confirmation` の値の違いは Z-1) |
| 値の型の区別 (`1`・`"1"`・`true`) | **無い** | **無い** | 両 peer に足す |

**足すテスト** (6 本。名前は検査内容に合わせる。`bound` は 同梱の契約 (`resources.files("<pkg>.contract").joinpath("data-service-api.v1.json")`。既存の `r2db-api/tests/test_http.py` L287・`MitateDB-api/tests/test_http.py` L229 と同じ読み方で、`mitatedb_api.http` は import しない) の `definitions.Mutation.properties.confirmation.maxLength`。同じテストで `definitions.ScopedMutation`・`schemas.SchemaOperationRequest`・`schemas.CredentialRevokeRequest` の値と等しいことも検査する。Z-3 裁定):

| peer | 配置 | 名前 | 内容 |
|---|---|---|---|
| MitateDB | `MitateDB-api/tests/test_foundation.py` の `FoundationTests` | `test_canonical_where_json_escapes_non_ascii_filter_values` | 値 `"é"` の canonical JSON が escape 形 `\u00e9` を含み、`é` そのものを含まない |
| MitateDB | 同上 | `test_delete_confirmation_phrase_distinguishes_value_types` | 値 `1`・`"1"`・`True` の phrase が互いに違う (対象・field・revision は同じ)。assert は `len({phrase(v) for v in (1, "1", True)}) == 3` とする (`1 == True` で hash も等しいので、値を dict・set のキーにしない) |
| MitateDB | 同上 | `test_delete_confirmation_phrase_is_bounded_by_the_confirmation_max_length` | `bound` を読み、対象 `"w"` で revision の桁数を `bound - 50` にした phrase が長さ `bound` で返り、1 桁増やすと `AssertionError` (桁数は literal にしない) |
| r2db | `r2db-api/tests/test_foundation.py` (module 関数) | `test_delete_confirmation_phrase_distinguishes_value_types` | MitateDB と同じ性質と assert |
| r2db | 同上 | `test_canonical_where_json_preserves_predicate_order` | operator を非昇順 (`lt` → `eq`) に並べた 2 述語の canonical JSON で、`lt` の述語が `eq` の述語より前に出る (部分文字列の位置で比べる。Z-2 裁定) |
| r2db | 同上 | `test_delete_confirmation_phrase_is_bounded_by_the_phrase_max_length` | `bound` を読み、`_PHRASE_MAX_LENGTH == bound` と、上と同じ `bound` / `bound + 1` の境界 |

| 触るファイル | 触らないファイル |
|---|---|
| `MitateDB-api/tests/test_foundation.py` (新規テスト 3 本)、`r2db-api/tests/test_foundation.py` (新規テスト 3 本)。記録 (監督、別担当の編集の統合後): `docs/design/ROADMAP_POST_PHASE7_V1.md` の R-39 行への【追記】と設計 §10 の実施記録 | 両 peer の `src/` (`delete_confirmation.py` を含む。変異は一時コピーだけ)、`conformance-tests/` (Z-1)、両 peer の `tests/test_audit_query.py` と L1 scan、`tools/`、`spec/` |

| # | 完了条件 | 変異 (`file:操作`) | 赤になる test id (予想) |
|---|---|---|---|
| 1 | MitateDB の canonical JSON は非 ASCII を escape する (R-39 (1b)) | `MitateDB-api/src/mitatedb_api/delete_confirmation.py`: L42 の `json.dumps` に `ensure_ascii=False` を足す | `MitateDB-api/tests/test_foundation.py::FoundationTests::test_canonical_where_json_escapes_non_ascii_filter_values` (新規) |
| 2 | MitateDB は `true` と `1` を区別する | 同 L41: `"value": f.value` を `"value": int(f.value) if isinstance(f.value, bool) else f.value` にする | `MitateDB-api/tests/test_foundation.py::FoundationTests::test_delete_confirmation_phrase_distinguishes_value_types` (新規) |
| 3 | MitateDB は `"1"` と `1` を区別する | 同 L41: `"value": f.value` を `"value": int(f.value) if isinstance(f.value, str) and f.value.isdigit() else f.value` にする | 同上 |
| 4 | MitateDB の phrase は契約の `confirmation.maxLength` 以内で、境界ちょうどは通る | 同 L83: `<= 256` を `<= 257` にする | `MitateDB-api/tests/test_foundation.py::FoundationTests::test_delete_confirmation_phrase_is_bounded_by_the_confirmation_max_length` (新規) |
| 5 | r2db は `true` と `1` を区別する | `r2db-api/src/r2db_api/delete_confirmation.py`: L79 の `"value": p.value` を `"value": int(p.value) if isinstance(p.value, bool) else p.value` にする | `r2db-api/tests/test_foundation.py::test_delete_confirmation_phrase_distinguishes_value_types` (新規) |
| 6 | r2db は `"1"` と `1` を区別する | 同 L79: `"value": p.value` を `"value": int(p.value) if isinstance(p.value, str) and p.value.isdigit() else p.value` にする | 同上 |
| 7 | r2db の上限値は同梱の契約の `confirmation.maxLength` (R-39 (1g)) | 同 L49: `_PHRASE_MAX_LENGTH = 256` を `257` にする | `r2db-api/tests/test_foundation.py::test_delete_confirmation_phrase_is_bounded_by_the_phrase_max_length` (新規) |
| 8 | r2db は実際の phrase の長さを検査する | 同 L128: `assert len(phrase) <= _PHRASE_MAX_LENGTH, …` の行を削る | 同上 |
| 9 | 変異 1〜8・13 で赤になるのは新規テストだけ (偽の緑の排除と重複の回避) | **監査照合**: 各変異の実行ログで、上表の既存テスト (key 順・list 順・scope・schema_revision・per-request) と両 peer の既存 phrase テストが緑のままであること | — |
| 10 | 綴りを固定しない | **監査照合**: 新規テストに phrase 全体・canonical JSON 全体の literal が無い (等値・不等・長さ・部分文字列だけ) | — |
| 11 | コードと同型性表を変えない | **監査照合**: 両 peer の `src/` の差分 0、`_ISOMORPHIC_TARGETS` の差分 0 | — |
| 12 | R-39 の (1b) と (1g) を閉じ、R-39 行を更新する (Y-8) | **監査照合**: 完了時の記録コミットで R-39 行に (1b)・(1g) を閉じた旨の【追記】があり、設計 §10 の実施記録に載ること | — |

| 13 | r2db は述語の list 順を保つ (Z-2 裁定) | `r2db-api/src/r2db_api/delete_confirmation.py`: L79 の `for p in where` を `for p in sorted(where, key=lambda p: p.operator)` にする (field 順のソートや逆順は既存の `r2db-api/tests/test_foundation.py::test_canonical_where_json_sorts_nested_keys_and_escapes_non_ascii` (L650) も赤にし、9 に反する) | `r2db-api/tests/test_foundation.py::test_canonical_where_json_preserves_predicate_order` (新規) |
| 14 | 上限は契約から読み、4 か所の値が等しい (Z-3 裁定) | **監査照合**: 新規の境界テスト 2 本が `bound` を同梱の契約から読み、4 か所の等値を assert し、256 と revision の桁数を literal で持たないこと | — |

- 共通の C-1〜C-3 (§5.5) を末尾に付ける。C-2 の新規は 6 件 (MitateDB 3、r2db 3)。

### 5.26 WP-2a の重なり・別案・未確定 (v1.9 追記)

- **重なり**: 触るのは両 peer の `tests/test_foundation.py` だけ。コメント変更セット (変更セット 3 以降、`backend_postgres.py` の整理 Y-5) とは重ならない。同じ 2 file を触る R-37 の WP (WP-3 以降) とは直列にする。
- **範囲外**: 規則 5 (identifier 検証済みの名前だけ) と、規則 1 の `destructive` 値からの独立は本 WP で固定せず、R-41 に追記する予定 (ロードマップは別担当が直す)。
- **Class C の別案 (本 WP に入れない)**: C-06 に次の vector を足せば、adapter 経由で両 peer に同じ規則を掛けられる。(a) request_id と `confirmation` の値だけが違う 2 つの probe が同じ `required_confirmation` を得る (規則 1。adapter が request_id を渡せるかは着手時に確かめる)、(b) where の値が `1` と `"1"` の probe で phrase が違う、(c) `required_confirmation` が 256 以内 (規則 6)、(d) delete phrase が add_field の後に変わる (規則 4。V6 は drop_entity だけ)。

**未確定 (監督判断待ち)**:

| # | 点 |
|---|---|
| Z-1 | 上の Class C の別案を起票するか。起票先は R-39 か新しい R 行か |
| Z-2 | r2db の list 順は既存テストの literal が付随的に固定しているだけ。明示のテストを足すか (本案は足さない) |
| Z-3 | 256 を literal で固定するか、同梱の契約 JSON の `confirmation.maxLength` から読むか (本案は literal) |

**監督裁定 (2026-09-15、独立レビュー)**: Z-2 は r2db に明示のテストを足す (§5.25 の 13)。Z-3 は同梱の契約から読む (§5.25 の足すテストと 14)。Z-1 は未確定のまま。

**監督裁定 (2026-09-15)**:

| # | 裁定 |
|---|---|
| Z-1 | Class C の案 (C-06 に request_id / `confirmation` 値からの独立、1 と "1"、256 以内、add_field 後に phrase が変わる、のベクトルを足す) は本 WP に入れず、ロードマップに R-41 として起票する (フェーズ11、Class C) |
| Z-2 | r2db にも list 順を明示的に固定するテストを足す (既存の literal に偶然含まれることに頼らない) |
| Z-3 | 256 は literal ではなく、同梱の契約から上限を読み、`_PHRASE_MAX_LENGTH` がそれと一致すること、及び境界 256/257 を固定する (契約が正) |

### 5.27 WP-3 の実測と分け方 (v1.10 追記、**独立レビュー待ち**)

**対象**: §2.4 の SV1〜SV3 (r2db `service.py`)。§4 の WP-3 行の ST8〜ST10 (`structured.py`) と CE5〜CE7 (MitateDB `cell.py`) は本書では実測せず、後の WP-3d 以降に回す (W3-1)。

| ID | 実測 (`b45312d`) | 読む module レベルの名前・状態 | 呼出し元 | 例外・`details` | MitateDB の対応 |
|---|---|---|---|---|---|
| SV1 | `service.py` L120-165 (`QueryPage`・`MutationResult`、frozen dataclass) | `dataclass`、`Any` だけ | `DataService.query_page` (L907)・`mutate_result` (L956)。`http.py` L462・L501 は文字列注釈、conformance-tests は契約の schema 名としての言及だけ | なし | 無い (MitateDB は dict を返し、`http.py` が応答を組む) |
| SV2 | `DataService.capabilities` L758-881 の文書組立 (L760-880) と `_IN_MEMORY_PROCESS_WIDE_LIMIT_CLASSES` (L68-70) | 暗黙に読む: `canonical.role`・`canonical.application_id` (principal)、`self.limits`、`self._control_plane_status`、`self._process_ceiling`、`self._surfaces`。**6 つとも値又は `limits` object を引数で渡せる** | `http.py` の capabilities、両 conformance adapter | なし (`_slot` の中) | `cell.py` L3883 `ApplicationRuntime.__build_capabilities_document(principal)`。本体の構造が違うので対にしない (CE7 として別 WP) |
| SV3 | `_query_outcome` L913-920 (型検査 4 件)、`_mutate_outcome` L980-984 (`transaction` の解決と検査 2 件) | 引数だけ (`select`・`where`・`page_size`・`order_by`・`cursor`・`transaction`・`operations`)。limits・capability・schema revision は読まない | `query`・`query_page`・`mutate`・`mutate_result` | 語彙 code の `fail` 6 件 (L914・L916・L918・L920 `VALIDATION_FAILED`、L982 `CAPABILITY_UNSUPPORTED`、L984 `VALIDATION_FAILED`)。いずれも `violation(...)` の 4-key | `http.py` の shape 検査と `cell.py` の `_gate` 後の検査 (CE6)。単位が違う |

- **片側か両 peer か**: 3 件とも **r2db だけ** (WP-1 と同じ片側抽出)。MitateDB に同じ公開意味で本文を揃える合理的な単位が無く (§5.23 と同じ判断)、WP-2 の対応抽出は起こさない。
- **禁止境界として WP-3 から外すもの (設計 §3.2)**: `_slot`・`_check`・`_acquire_rate` (認証・認可・rate・concurrency)、`_event`・`_denial_event`・`_make_audit_hook` と `except FoundationError` の deny 監査 (audit)、`fold_operation_idempotency_keys`・`effective_idempotency_key` (idempotency、U-4)、`plan_request` の組立と `dry_run` による `hook`・`assigned_addresses`・`plan` の分岐 (plan / dry-run)、`uuid` による request_id の生成、`self._clock` の deadline、`self.limits.check_request`・`check_depth`・`narrow_limits_by_budget` (limits を読むので facade に残す)、`self._cells[...]` の実行、`schema`・`catalog`・`deny_unsupported`。評価順 (`_slot` → 形の検査 → limits → budget → 実行) と例外型は facade が持つ。
- **分け方**: 3 単位の直列 (§5.28〜§5.30)。3 件とも `service.py`・`r2db-api/tests/test_foundation.py`・`tools/tests/test_leaf_import_direction.py`・`docs/code-history/r2db-api/service.md` を触る。
- **baseline (導出)**: root 3,382 (`r2db-api/tests` 1,278 / `MitateDB-api/tests` 1,109 / `conformance-tests` 995)、`tools/tests` 109。設計 §10.8 の WP-2a の root ゲート 3382 と一致する。着手時に collect-only で確かめる。
- **静的な pin**: `service.py` に行番号 allowlist は無い (r2db の `_BACKEND_LAYER_ALLOWLIST` は `postgres.py` だけ)。`r2db-api/tests/test_threadpool_offload.py` の getsource は `DataService._slot`・`_acquire_rate` だけで、3 件とも動かさない。L1 scan の件数 pin (`service.py` 10) が変わるのは 3c だけ。
- **CH-ID の付いた塊 (変更セット 2)**: 3a で 4 塊を移し (CH-0167〜0170)、3b で 9 塊を移す (CH-0136〜0143、CH-0174)。3c は CH-0126 を leaf へ移す (3c の後、facade に `resolved_transaction` の読み手が無いため。W3-5)。計 14 塊。括弧書きを足す塊は、同じ変更で `docs/code-history/r2db-api/service.md` の該当節に訂正の記録 (旧文 → 新文) を追記する (コメント出所の設計 v0.13 §9 0g の 4)。訂正は 3a 1 件 (CH-0168)、3b 5 件 (CH-0143・CH-0140・CH-0139・CH-0136・CH-0174)、3c 1 件 (CH-0126) の計 7 件。節は動かさない (受け皿 README「後の抽出で symbol が移っても節は動かさない」)。`--register` は CH-ID を peer 単位で引くので、別ファイルへの移動はそのまま解決する。
- **統合の手順**: src の行数が変わるので、各単位は root ゲートを通してから統合する。コミットした後の HEAD で `pytest -q tools/tests` を流す (`tools/tests/test_comment_provenance.py::test_0f_both_peers_all_src_rev_vs_itself_is_green` が HEAD のコードと受け皿を照合するため。`test_repository_register_passes` は形式しか見ない)。
- **重なり**: コメント変更セット 5 (`ccp-cs0`、r2db `credential_store.py`・MitateDB `ops.py` と各受け皿) と触るファイルは重ならない。変更セット 5 が `tools/` や `docs/code-history/r2db-api/service.md` を触らないことを着手時に確かめる。設計書・ロードマップは触らない (記録は監督)。

### 5.28 WP-3a — r2db 応答の結果型 (SV1、**独立レビュー待ち**)

**目的**: `service.py` の `QueryPage`・`MutationResult` を leaf `r2db-api/src/r2db_api/service_results.py` (§2.4 の名前) へ移す。

| 項目 | 実測 (`b45312d`) |
|---|---|
| 移動範囲 | `service.py` L120-165 (2 つの dataclass と docstring・コメント) と直後の空行 |
| leaf の import | `__future__` (移動元と同じく注釈を文字列のままにする)、`dataclasses`、`typing` |
| facade | `service.py` が 2 名を import 1 行で読む (L907・L956 が組み立てる)。移動で未使用になる `from dataclasses import dataclass` (L5) を削除する |
| denial・件数 pin・`SCANNED_MODULES`・allowlist | 無い。L1 scan は差分 0 |
| 範囲内の位置参照 (40c) | 付ける: CH-0168 (`MutationResult` の docstring) の「`mutate` below」の直後に「(in `service.py`)」(訂正の記録 1 件)。付けない: CH-0169 の `_query_outcome`・`query_page`、CH-0167 の `MutationOutcome.request_id`、`http.post_mutate`・`DataService.mutate_result` (名前だけで位置語が無い) |
| 範囲外の位置参照 (40c) | CH-0133 (L903)「reaches `QueryPage.request_id` below」は L907 の呼出しを指し、動かないので付けない。`http.py` L554 の `MutationResult.request_id`'s own comment は名前だけ |

| 触るファイル | 触らないファイル |
|---|---|
| `r2db-api/src/r2db_api/service.py` (移動範囲、import 1 行、L5 の削除)、新規 `r2db-api/src/r2db_api/service_results.py`、`docs/code-history/r2db-api/service.md` (CH-0168 の訂正の記録だけ)、`r2db-api/tests/test_foundation.py` (新規テスト 2 本)、`tools/tests/test_leaf_import_direction.py` (leaf 1 行、許可 `dataclasses`・`typing`) | `r2db-api/src/r2db_api/http.py`、`r2db-api/tests/test_l1_details_vocabulary_ast_scan.py`、`conformance-tests/`、`r2db-api/src/r2db_api/credential_store.py` (変更セット 5)、MitateDB-api 全部、`docs/design/`、roadmap |

| # | 完了条件 | 変異 (`file:操作`) | 赤になる test id (予想) |
|---|---|---|---|
| 1 | facade 互換 | `service.py`: import から `MutationResult` を外す | `r2db-api/tests/test_foundation.py::test_service_results_leaf_preserves_service_facade` (新規。2 名の `is`) |
| 2 | 結果型は frozen | `service_results.py`: `MutationResult` の `frozen=True` を外す | `r2db-api/tests/test_foundation.py::test_service_results_are_frozen_with_contract_defaults` (新規。代入で `FrozenInstanceError`、`dataclasses.fields` の名前と既定値を固定する) |
| 3 | 既定値は変わらない | `service_results.py`: `committed: bool = True` を `False` にする | 同上 |
| 4 | leaf の import が許可リストの内だけ | `service_results.py`: `import os` を 1 行足す | `tools/tests/test_leaf_import_direction.py::test_leaf_modules_import_only_their_allowlisted_modules` |
| 5 | 新 leaf が分類される | 一覧から `service_results.py` の行を消す | `tools/tests/test_leaf_import_direction.py::test_every_src_module_is_classified` |
| 6 | 括弧書きを足した CH-ID 塊に訂正の記録がある (0g の 4) | `service.md`: CH-0168 の訂正の記録を書かない | `tools/tests/test_comment_provenance.py::test_0f_both_peers_all_src_rev_vs_itself_is_green` (HEAD を読むので、変異を使い捨ての clone にコミットして実行する。`--register` の `test_repository_register_passes` は形式しか見ず赤にならない) |
| 7 | 未使用になった import を削除した | **監査照合**: `service.py` に `dataclass` の import と参照が無い | — |
| 8 | 逐語移動と位置参照 (40c) | **監査照合**: docstring とコメントが逐語。括弧書きは CH-0168 の 1 箇所だけ。CH-0167〜0170 の 4 塊が leaf にある | — |
| 9 | 同型性を登録しない | **監査照合**: `_ISOMORPHIC_TARGETS` の差分 0、MitateDB `src/` の同名定義 0 件 | — |
| 10 | 統合の手順 | **監査照合**: 統合前の root ゲートの集計行と、コミット後の HEAD の `tools/tests` の集計行 | — |

### 5.29 WP-3b — r2db capabilities 文書の組立 (SV2、**独立レビュー待ち**)

**目的**: `DataService.capabilities` の文書組立を leaf `r2db-api/src/r2db_api/capabilities_document.py` の関数 `build_capabilities_document(*, role, application_id, limits, control_plane_status, process_ceiling, surfaces)` へ移し、暗黙に読んでいた principal と deployment の値を引数で渡す (設計 §4 WP-3)。`_slot` (認可・rate・concurrency) は method に残す。**WP-3a の統合後に着手する。**

| 項目 | 実測 (`b45312d`。3a の統合後に取り直す) |
|---|---|
| 移動範囲 | `service.py` L760-881 (`schema_ops` から `return document` まで。コメントを含む) と、L68-70 (`_IN_MEMORY_PROCESS_WIDE_LIMIT_CLASSES` と CH-0174 の説明コメント。読み手は L860 だけ) |
| method に残すもの | L758-759 (`def` と `with self._slot(...) as canonical:`) と、関数を呼んで返す 1 行 |
| 本体の変更 | 6 つの名前の置換だけ: `canonical.role` → `role`、`canonical.application_id` → `application_id`、`self.limits` → `limits` (L839・L863)、`self._control_plane_status` → `control_plane_status`、`self._process_ceiling` → `process_ceiling`、`self._surfaces` → `surfaces` (W3-3) |
| leaf の import | `__future__`、`typing`。`limits` は `as_dict()` を呼ぶだけで `.limits` を import しない |
| facade | `service.py` が `build_capabilities_document` を読む。`_IN_MEMORY_PROCESS_WIDE_LIMIT_CLASSES` は `service.py` から読む箇所が 0 (tests も読まない) なので facade に残さない (Y-3・Y-7 と同じ) |
| denial・件数 pin・allowlist | 無い。L1 scan は差分 0 |
| 範囲内の位置参照 (40c) | 付ける (「(in `service.py`)」): L762「(see `query`/`mutate`/`schema`/`catalog` below)」の below (CH-0143)、L818「(see __init__'s comment on this field)」の __init__'s (CH-0140)、L821「(`schema`/`mutate_result`/`_query_outcome` below」の below (CH-0139)、L865「`_slot()` above」の above (CH なし)、L876「`__init__`'s own comment」の `__init__`'s (CH-0136)、L68「(`self._rate_windows`/`self._active`, both below)」の below (CH-0174)。付けない: L765・L776・L790・L809・L815・L821 前半・L842 の below と L815・L840 の here (指す先も leaf に移る) |
| 範囲外の位置参照 (40c) | 付けない: `http.py` L613「(service.py's `capabilities()`)」と `ops.py` L1149 (CH-0323)「what `service.py` is expected to declare」。どちらも宣言を返す `DataService.capabilities()` を指し、その method は `service.py` に残るので指す先は変わらない (`ops.py` は CH-ID の塊で、付ければ受け皿の訂正も要る) |

| 触るファイル | 触らないファイル |
|---|---|
| `r2db-api/src/r2db_api/service.py` (移動範囲、method の 1 行、import 1 行)、新規 `r2db-api/src/r2db_api/capabilities_document.py`、`docs/code-history/r2db-api/service.md` (CH-0143・CH-0140・CH-0139・CH-0136・CH-0174 の訂正の記録だけ)、`r2db-api/tests/test_foundation.py` (新規テスト 2 本)、`tools/tests/test_leaf_import_direction.py` (leaf 1 行、許可 `typing`) | `r2db-api/src/r2db_api/http.py`、`limits.py`、`main.py`、`r2db-api/tests/test_l1_details_vocabulary_ast_scan.py`、`conformance-tests/`、MitateDB-api 全部 (CE7 は別 WP)、`credential_store.py`、`docs/design/`、roadmap |

| # | 完了条件 | 変異 (`file:操作`) | 赤になる test id (予想) |
|---|---|---|---|
| 1 | 文書は引数だけから組み立てる | `capabilities_document.py`: `role == "developer"` を `role != "developer"` にする | `r2db-api/tests/test_foundation.py::test_capabilities_document_is_built_only_from_explicit_arguments` (新規。leaf を直接呼び、developer は 6 つの schema 操作・runtime は空 list、`process_ceiling` 2 で `requests_per_minute`・`concurrency` が `deployment_required`、`control_plane_status`・`surfaces` の反映を literal で固定する。`DataService.capabilities` との比較は同じ leaf を通るので赤にならず、使わない) |
| 2 | method は deployment の値を渡す | `service.py`: 呼出しの `process_ceiling=self._process_ceiling` を `process_ceiling=1` にする | `r2db-api/tests/test_foundation.py::test_data_service_capabilities_passes_deployment_values_to_the_document` (新規。既定でない limits、`control_plane_status="enabled"`、surfaces、`process_ceiling=2` で `DataService.capabilities` を呼び literal と比べる)、`r2db-api/tests/test_process_ceilings_declaration.py::test_ceiling_two_maps_in_memory_classes_to_deployment_required` |
| 3 | 同上 (surfaces) | `service.py`: `surfaces=self._surfaces` を `surfaces=None` にする | `r2db-api/tests/test_foundation.py::test_data_service_capabilities_passes_deployment_values_to_the_document`、`r2db-api/tests/test_surfaces_env.py::test_build_app_control_plane_enabled_publishes_both_surfaces` |
| 4 | 同上 (limits) | `service.py`: `limits=self.limits` を `limits=ResourceLimits()` にする | `r2db-api/tests/test_foundation.py::test_data_service_capabilities_passes_deployment_values_to_the_document` (`r2db-api/tests/test_control_plane_service.py` L1781 は `ControlPlaneService` のテストで、leaf を直接呼ぶテストと同じく赤にならない) |
| 5 | 同上 (control_plane) | `service.py`: `control_plane_status=self._control_plane_status` を `"unavailable"` にする | `r2db-api/tests/test_foundation.py::test_data_service_capabilities_passes_deployment_values_to_the_document`、`r2db-api/tests/test_credential_persistence.py::test_build_app_control_plane_status_enabled_is_declared` |
| 6 | 認可と slot を通る | **監査照合**: `with self._slot(...)` が method に残り、leaf は `_slot`・`AuthContext` を参照しない (設計 §3.2)。呼出しが `with` の本体の中にある。leaf の 6 つの引数は keyword-only で既定値を持たない | — |
| 7 | leaf の import が許可リストの内だけ | `capabilities_document.py`: `import os` を 1 行足す | `tools/tests/test_leaf_import_direction.py::test_leaf_modules_import_only_their_allowlisted_modules` |
| 8 | 新 leaf が分類される | 一覧から `capabilities_document.py` の行を消す | `tools/tests/test_leaf_import_direction.py::test_every_src_module_is_classified` |
| 9 | 訂正の記録 5 件 (0g の 4) | `service.md`: CH-0139 の訂正の記録を書かない | `tools/tests/test_comment_provenance.py::test_0f_both_peers_all_src_rev_vs_itself_is_green` (HEAD を読むので、変異を使い捨ての clone にコミットして実行する。`--register` の `test_repository_register_passes` は形式しか見ず赤にならない) |
| 10 | 本体は 6 つの置換を除き同一 | **監査照合**: 置換を戻した leaf の本体と移動前の L760-881 が AST で一致する | — |
| 11 | 逐語移動と位置参照 (40c) | **監査照合**: コメントが逐語 (置換は識別子だけ)。括弧書きは上表の 6 箇所だけ。9 塊が leaf にある | — |
| 12 | 公開の宣言は変わらない | **監査照合**: 既存の capabilities テストと conformance (C-05・C-17 など) の集計行が前後で一致 | — |
| 13 | 同型性を登録しない | **監査照合**: `_ISOMORPHIC_TARGETS` の差分 0。MitateDB CE7 とは対にしない | — |
| 14 | 統合の手順 | **監査照合**: 3a の 10 と同じ | — |

### 5.30 WP-3c — r2db query / mutate の形の検査 (SV3、**独立レビュー待ち**)

**目的**: `_query_outcome` と `_mutate_outcome` の型・capability の検査を leaf `r2db-api/src/r2db_api/request_shape.py` の `_check_query_request_shape(select, where, page_size, order_by, cursor)` と `_check_mutation_request_shape(transaction, operations)` (値を返さない。facade は解決済みの transaction を読まない) へ移す。呼出しは同じ位置 (`_slot` の中、limits 検査の前) に置き、評価順と例外型を変えない。**WP-3b の統合後に着手する。**

| 項目 | 実測 (`b45312d`。3b の統合後に取り直す) |
|---|---|
| 移動範囲 | `service.py` L913-920 (4 検査) と L972-984 (CH-0126 の塊、`resolved_transaction` の解決、capability 検査、operations 検査) |
| 残すもの | L985 以降 (idempotency key の折畳み、`request`、limits、budget、`plan_request`)。`resolved_transaction` の読み手は L981 だけなので、3c の後 facade に読み手が無くなる。代入が leaf へ移るので、その説明の CH-0126 の塊も leaf へ移す (W3-5) |
| leaf の import | `__future__`、`typing`、`.errors` (`fail`・`observed_type_of`・`violation`) |
| facade | 2 関数を import 1 行で読む。`fail`・`observed_type_of`・`violation` は `service.py` の他の箇所が使うので残す |
| denial | 語彙 code の `fail` 6 件 (4-key) |
| 件数 pin | `service.py` 10 → 4、`request_shape.py` 6 (`test_ast_full_count_matches_the_audit_site_count` の module tuple と dict の両方に足す) |
| 行番号 allowlist | 対象は `postgres.py` だけなので差分 0 |
| sib tuple | 固定 tuple (`structured.py`, `inmemory_predicate.py`, `identifier_rules.py`, `paging.py`, `value_types.py`) に `request_shape.py` を足し、テストの docstring の module 一覧も合わせる (W3-4 裁定) |
| 既存テスト | `select` が list でない: `r2db-api/tests/test_foundation.py::test_malformed_inputs_fail_with_safe_foundation_errors`、`r2db-api/tests/test_application_audit.py::test_validation_failed_denials_add_no_durable_row_and_no_buffer_entry`。`best_effort`: `r2db-api/tests/test_denial_details_and_request_id.py::test_capability_unsupported_carries_violated_declaration`。`cursor`・`order_by` が dict: `r2db-api/tests/test_l5_si10_details_leak_scan.py::test_si10_scan_finds_no_leaked_value_sql_dsn_internal_name_or_stack_trace` (文言の漏洩だけ)。`where` が list でない、`page_size` が bool、6 件の details の literal は固定されていない |
| 位置参照 (40c) | 付ける: leaf へ移る CH-0126 の「what `plan_request` below reflects」の below の直後に「(in `service.py`)」(訂正の記録 1 件)。同じ塊の「(the capability gate below)」は leaf の中で成り立つので付けない |

| 触るファイル | 触らないファイル |
|---|---|
| `r2db-api/src/r2db_api/service.py` (移動範囲、呼出し 2 行、import 1 行)、新規 `r2db-api/src/r2db_api/request_shape.py`、`docs/code-history/r2db-api/service.md` (CH-0126 の訂正の記録だけ)、`r2db-api/tests/test_foundation.py` (新規テスト 2 本)、`r2db-api/tests/test_l1_details_vocabulary_ast_scan.py` (`SCANNED_MODULES`、件数 pin、sib tuple とその docstring)、`tools/tests/test_leaf_import_direction.py` (leaf 1 行、許可 `typing`・`.errors`) | `r2db-api/src/r2db_api/http.py` (HTTP の shape 検査は別)、`structured.py`、`limits.py`、同 L1 scan の `_BACKEND_LAYER_ALLOWLIST`、`conformance-tests/`、MitateDB-api 全部、`credential_store.py`、`docs/design/`、roadmap |

| # | 完了条件 | 変異 (`file:操作`) | 赤になる test id (予想) |
|---|---|---|---|
| 1 | `page_size` は bool を拒否する | `request_shape.py`: `or isinstance(page_size, bool)` を削る | `r2db-api/tests/test_foundation.py::test_request_shape_denials_carry_code_details_and_order` (新規。6 つの不正入力の code と details を literal で固定する) |
| 2 | `where` は list | `request_shape.py`: `where` の条件を `False and …` にする | 同上 |
| 3 | `cursor` は str | `request_shape.py`: `cursor` の条件を `False and …` にする | 同上 |
| 4 | capability の検査が operations の検査より先 | `request_shape.py`: 2 つの検査の順を入れ替える | 同上 (`transaction="best_effort"` と `operations="x"` で `CAPABILITY_UNSUPPORTED`) |
| 5 | `atomic` 以外を拒否する | `request_shape.py`: `!= "atomic"` を `not in ("atomic", "best_effort")` にする | `r2db-api/tests/test_denial_details_and_request_id.py::test_capability_unsupported_carries_violated_declaration` |
| 6 | 形の検査は認可の後に走り、deny が監査される (評価順) | `service.py`: `_check_query_request_shape(...)` の呼出しを `with self._slot(...)` の外 (前) へ出す | `r2db-api/tests/test_foundation.py::test_request_shape_checks_run_after_authorization_and_are_audited` (新規。無効な context と不正な `select` の組で `AUTH_INVALID`、不正な `select` だけのときはメモリ内の監査 (`ControlAuthority.audit_events()`) に `VALIDATION_FAILED` の deny が残る) |
| 6b | facade の差分は呼出しだけ | **監査照合**: 2 つの呼出しが `with` の本体の中、`self.limits.check_request` の前にあり、facade の差分は呼出し 2 行・import・移動範囲の削除だけ | — |
| 7 | 移動先が `SCANNED_MODULES` に入る (40b) | L1 scan: `SCANNED_MODULES` から `request_shape.py` を外す | `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py::test_every_module_with_a_vocabulary_denial_is_accounted_for` |
| 8 | 件数 pin (`service.py` 4、`request_shape.py` 6) | `request_shape.py`: 4-key の `fail("VALIDATION_FAILED", "x", details=violation("request_schema"))` を呼ぶ関数を 1 つ足す | `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py::test_ast_full_count_matches_the_audit_site_count` |
| 9 | 移した denial が 4-key のまま | `request_shape.py`: `cursor` の `fail` から `details=` を外す | `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py::test_every_choke_point_denial_carries_details_ast_full_count`、`::test_allowlist_entries_match_real_bare_call_sites` |
| 9b | sib tuple に移動先が入る (W3-4) | `request_shape.py`: `"Cursor must be a string."` を allowlist の文言 `"A value in this request is not acceptable to the underlying storage."` にする | `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py::test_backend_layer_allowlist_entries_have_no_in_memory_sibling_denial` (tuple を更新しないと緑のまま) |
| 10 | leaf の import が許可リストの内だけ | `request_shape.py`: `import os` を 1 行足す | `tools/tests/test_leaf_import_direction.py::test_leaf_modules_import_only_their_allowlisted_modules` |
| 11 | 新 leaf が分類される | 一覧から `request_shape.py` の行を消す | `tools/tests/test_leaf_import_direction.py::test_every_src_module_is_classified` |
| 12 | 訂正の記録 (0g の 4) | `service.md`: CH-0126 の訂正の記録を書かない | `tools/tests/test_comment_provenance.py::test_0f_both_peers_all_src_rev_vs_itself_is_green` (HEAD を読むので、変異を使い捨ての clone にコミットして実行する。`--register` の `test_repository_register_passes` は形式しか見ず赤にならない) |
| 13 | 移した文は同一 | **監査照合**: leaf の検査文が移動前の L913-920・L980-984 と AST で一致し、CH-0126 のコメントが逐語 (関数の引数名は移動前の変数名のまま) | — |
| 14 | 同型性を登録しない・統合の手順 | **監査照合**: `_ISOMORPHIC_TARGETS` の差分 0。3a の 10 と同じ手順 | — |

### 5.31 WP-3 の順序と未確定 (v1.10 追記)

- **順序**: WP-3a → 3b → 3c の直列 (共通に `service.py`・`r2db-api/tests/test_foundation.py`・L・`service.md` を触る)。3c だけが r2db の L1 scan を触る。
- 各単位の新規テストは 3a 2 本、3b 2 本、3c 2 本。§5.5 の C-1〜C-3 を末尾に付ける。
- 設計 §9.3: 3 件とも MitateDB `cell.py` の `_gate` とその呼出し経路を触らない。U-2: r2db `service.py` のコメント整理 (変更セット 2、変更セット 3 の 0d の戻し) は統合済み。

**未確定 (監督判断待ち)**:

| # | 点 |
|---|---|
| W3-1 | WP-3 の範囲。本書は SV1〜SV3 (3a〜3c) だけを起草した。ST8〜ST10 (r2db `structured.py`) と CE5〜CE7 (MitateDB `cell.py`) を WP-3d 以降として実測するか、別の段階にするか |
| W3-2 | leaf 名。`service_results.py` (§2.4)、`capabilities_document.py` の `build_capabilities_document`、`request_shape.py` の `_check_query_request_shape`・`_check_mutation_request_shape` |
| W3-3 | 3b は本体の AST が 6 つの名前の置換だけ変わる (これまでの「AST 同一」の例外)。設計 §4 WP-3 の「暗黙に読ませない」に従う形として認めるか |
| W3-4 | 3c の leaf を r2db の L1 scan の sib tuple に足すか (本案は足さない) |
| W3-5 | CH-0126 は `resolved_transaction` の説明で、3c の後 facade にその読み手が無い (代入も leaf へ移る)。塊を leaf へ移し「`plan_request` below」に括弧書きを付ける (本案) か、facade に残すか |

**監督裁定 (2026-09-15、独立レビュー)**: 指摘をすべて採用した。W3-4 は足す (§5.30)。3b・3c の facade テスト、訂正の記録の赤テスト、評価順の変異、3b の範囲 (L760-881) と範囲外の位置参照は §5.27・§5.29・§5.30 に反映した。

**監督裁定 (2026-09-15)**:

| # | 裁定 |
|---|---|
| W3-1 | ST8〜ST10 と CE5〜CE7 は、WP-3a〜3c の統合後に WP-3d 以降として実測・起草する (本 manifest には入れない) |
| W3-2 | 提案の leaf 名 (`service_results.py`、`capabilities_document.py`、`request_shape.py`) で進める |
| W3-3 | 認める。ただし 3b の実装の検証で、移した本体と元の本体の AST の差が、その 6 つの名前を引数の名前に置き換えた箇所だけであることを機械的に示す (差分の列挙をログに残す)。能力文書は literal の期待値のテストで固定する |
| W3-4 | 先例 (m6、`request_limits.py`・`constraint_resolution.py`) に揃えて sib tuple に足す。足すと検査が空振りになる、又は偽の赤になる根拠が独立レビューで示された場合だけ、足さない案に戻す |
| W3-5 | 独立レビュー後の本案に改める: 3c で `resolved_transaction` の代入も leaf へ移り facade に読み手が残らないので、CH-0126 の塊は leaf へ移し、「`plan_request` below」に括弧書きを付けて受け皿に訂正の記録を足す |

### 5.32 WP-3d〜3i の実測と共通 (v1.11 追記、**独立レビュー反映済み**)

**対象と順序**: §4 の WP-3 行の残り 6 件を、1 抽出 = 1 WP の直列で行う。ST10 → CE5 → ST8 → ST9 → CE7 → CE6 を WP-3d → 3e → 3f → 3g → 3h → 3i とする (W3-1)。

**実測**: main `9994d7c`。`structured.py` は 2379 行、`cell.py` は 4350 行。行範囲は top-level の定義と class member の `lineno`/`end_lineno` (デコレータを含む) で測った。denial は、各 peer の L1 scan の `_fail_call_sites` をそのまま import し、範囲ごとに数えた。どちらも読み取りだけである。

```bash
python3 -c 'import ast,sys; t=ast.parse(open(sys.argv[1]).read()); [print(min([n.lineno]+[d.lineno for d in getattr(n,"decorator_list",[])]), n.end_lineno, getattr(n,"name",type(n).__name__)) for n in t.body]' r2db-api/src/r2db_api/structured.py
python3 -c 'import importlib.util as u,sys; from pathlib import Path; s=u.spec_from_file_location("m",sys.argv[1]); m=u.module_from_spec(s); s.loader.exec_module(m); print(sorted(x if isinstance(x,int) else x[0] for x in m._fail_call_sites(Path(sys.argv[2]))))' MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py MitateDB-api/src/mitatedb_api/cell.py
grep -c 'CH-[0-9]' r2db-api/src/r2db_api/structured.py MitateDB-api/src/mitatedb_api/cell.py   # 0 と 0
```

**監督の枠 (WF-1〜WF-7。各 WP はこれを前提に読む)**:

| # | 規則 |
|---|---|
| WF-1 | `_ISOMORPHIC_TARGETS` に登録された helper は動かさない。対象は r2db `structured.py` の `validate_enum_declaration`・`enum_member_matches_type`・`normalize_request_for_plan`・`compute_plan_token`・`normalize_request_for_idempotency`・`idempotency_digest` と、MitateDB `cell.py` の後ろ 4 件である。本文も 1 文字も変えず、位置参照も補わない。`_IdempotencyRecord`・`_idempotency_record_has_request_id`・`fold_operation_idempotency_keys`・`check_plan_precondition` (§3) も動かさない。抽出はこれらをまたぐ飛び石で行い、各 WP の完了条件に「`_ISOMORPHIC_TARGETS` の差分 0」を置く |
| WF-2 | 認可・rate・slot・audit・評価順序 (設計 §3.2) は facade に残す。facade の呼出しの位置は変えない |
| WF-3 | 各 WP の変異表に、認可 → 検査 → 実行 → 監査 の順序を壊す変異を 1 つ以上置く (WP-3c のレビューで見つかった穴への対処) |
| WF-4 | 片側の抽出とし、同型登録はしない。ST8〜ST10 は r2db、CE5〜CE7 は MitateDB である。CE7 は SV2 と対にしない (§5.29) |
| WF-5 | CH-ID の付いた塊は両 module とも 0 件である。docstring とコメントは 40c のとおり逐語で移す。括弧書きの判定は次のとおり。(i) below / above / here / 「THIS function」 / 「`X.py`'s」 / 「in `X.py`」 / `file:line` のように位置を指し、移動で指す先が変わるものには付ける。移動範囲の外に残る文も対象である (§5.5 の 1)。(ii) facade から同じ修飾名で読める参照 (例: `cell._FIELD_TYPE_VOCABULARY`) には付けない。(iii) 移動前から指す先を誤っている参照には付けず、既知の穴に回す。(iv) 範囲外の参照が CH-ID の塊の中にあるときは、受け皿に訂正の記録を足す (§5.27) |
| WF-6 | 統合の手順は §5.28 の 10 と同じ。src の行数が変わるので、root ゲートを通してから統合し、コミット後の HEAD で `tools/tests` を流す |
| WF-7 | 設計にない検査や機構は足さない。枠の中で行えない部分は範囲から外し、§5.39 の未確定に置く |

- **共通の規律**: §5.5 の規律 1〜5 に従い、各表の末尾に C-1〜C-3 を付ける。C-2 の新規件数は §5.39 の数である。
- **baseline (導出)**: root 3388、`tools/tests` 392 (設計 §10.9 の WP-3c の統合後)。着手時に collect-only で確かめる。
- **静的な pin の実測**:

| pin | r2db | MitateDB |
|---|---|---|
| L1 件数 pin | `structured.py` 67。ST8 範囲 18、ST9 のうち `bind_schema_operation` の外 1 (L522)、ST10 0 | `cell.py` 43。CE5 0、CE7 0、CE6 20 (3i の範囲は 1) |
| 行番号 allowlist | `postgres.py` だけ。差分 0 | `backend_postgres.py`・`backend_sqlite.py` だけ。差分 0 |
| sib tuple | 6 module (`structured.py` と leaf 5 件) | 7 module (`cell.py`・`field_types.py`・`http.py`・`identifiers.py` と leaf 3 件) |
| 修飾名の固定 | `r2db-api/tests/test_audit_query.py` L1488 の `_NON_AUDIT_OPERATION_PARAMETERS` が `structured.bind_mutation` を含む (3f) | 同表の `cell.` の 2 件は範囲外 |
| getsource | `test_threadpool_offload.py` は `DataService._slot`・`_acquire_rate` だけ | 範囲内に無い |
| 本文の文字列の数え上げ | 無い | `MitateDB-api/tests/test_application_audit.py` L1101 が `cell.py` の本文で `def _validate_delete_confirmation(` を 1、`self._validate_delete_confirmation(` を 2 と数える。どちらも移動範囲に無く、差分 0 |
| L (`tools/tests/test_leaf_import_direction.py`) | 各 WP で leaf 1 行を足す | 同じ |

- **重なり**: コメント変更セット 5 (`ccp-cs0`、R-22、未統合 `bcd07c1`) は r2db `postgres.py`・`control_plane.py`・`ops.py`・`service.py` と MitateDB `backend_sqlite.py`・`http.py`・`ops.py` を触る (他に `credential_store.py`、受け皿、`tools/check_comment_provenance.py`・`tools/tests/test_comment_provenance.py`)。3f の `postgres.py` (別の hunk) と、3d〜3i の変異の読み先 (`service.py`、訂正の記録の赤テスト) が重なる。3d〜3i は `ccp-cs0` の統合後に着手し、そのとき本節と各 WP の行番号を取り直す。
- **行番号**: 3e〜3i の行番号は、前の WP の統合後に取り直す (3b・3c と同じ)。変異の spec が引く行番号も同じである。
- **実行するコマンド** (`WT` は監督が割り当てる worktree。変異の spec は完了条件表の変異 1 行につき 1 件、`expect: red`。HEAD を読む訂正の記録の変異だけは §5.28 の 6 のとおり使い捨ての clone で行う):

```bash
tools/dev/pt.py -C "$WT" -- r2db-api/tests -q
tools/dev/pt.py -C "$WT" -- MitateDB-api/tests -q
tools/dev/pt.py -C "$WT" -- conformance-tests -q
tools/dev/pt.py -C "$WT" -- tools/tests -q
tools/dev/mutate.py "$SP/wp3d-mutations.json" -C "$WT"   # WP ごとに wp3e … wp3i
tools/dev/gate.py --label wp3d                             # 監督。run_in_background
```

### 5.33 WP-3d — r2db の storage の結果型 (ST10、**独立レビュー反映済み**)

**目的**: `QueryOutcome`・`MutationOutcome`・`SchemaOutcome` を leaf `r2db-api/src/r2db_api/storage_outcomes.py` へ移す (名前は W3-6)。

| 項目 | 実測 (`9994d7c`) |
|---|---|
| 移動範囲 (3 名、計 136 行) | 2 塊。L978-1072 は CCR-13 の見出しコメント、`QueryOutcome`、`MutationOutcome` の 95 行。L1242-1282 は `SchemaOutcome` の 41 行 |
| 飛び石 | 間の L1074-1239 は動かさない (dry_run/plan の見出し、登録 helper 4 件、`fold_operation_idempotency_keys`、`_IdempotencyRecord`、`_idempotency_record_has_request_id`)。leaf の中は Query → Mutation → Schema の順に置く |
| leaf の import | `__future__`、`dataclasses`、`typing` |
| facade | 3 名を import 1 行で読む。組み立てるのは `ApplicationCell` の L1470 (`QueryOutcome`)、L1629・L1704・L1740 (`MutationOutcome`)、L2058・L2343・L2379 (`SchemaOutcome`) である。`backend.py` L27、`postgres.py` L111-143、`r2db-api/tests/test_foundation.py` L15、`r2db-api/tests/test_threadpool_offload.py` L50 も `structured` から読む |
| denial・件数 pin・sib・allowlist | 無い (L1014 は `ValueError` で、語彙 code ではない) |
| 位置参照 (WF-5) | 付けない。L1055 の「below `transact`'s own idempotency lookup」は処理の順を言っており、位置ではない。L1245 の「`MutationOutcome` above」は leaf の中でも成り立つ。範囲外は `backend.py` L31「are defined in `structured.py`」の直後に「(now in `storage_outcomes.py`)」を付ける (CH は無い)。同じコメントの L35-37 (import 循環の仮定の文) は移動後も成り立つので付けない |
| 評価順 (WF-3) | 3 型を呼ぶ箇所は無い。結果型が監査の分岐を決める箇所 (`service.py` L862・L924 の `outcome.replayed`) で変異を行う (W3-13) |

| 触るファイル | 触らないファイル |
|---|---|
| `r2db-api/src/r2db_api/structured.py` (移動範囲と import 1 行)、新規 `r2db-api/src/r2db_api/storage_outcomes.py`、`r2db-api/src/r2db_api/backend.py` (L31 の括弧書きだけ)、`r2db-api/tests/test_foundation.py` (新規テスト 2 本)、`tools/tests/test_leaf_import_direction.py` (leaf 1 行、許可 `dataclasses`・`typing`) | `postgres.py`、`service.py`、`r2db-api/tests/test_l1_details_vocabulary_ast_scan.py`、`r2db-api/tests/test_audit_query.py`、`conformance-tests/`、MitateDB-api 全部、`docs/code-history/`、`docs/design/`、roadmap |

| # | 完了条件 | 変異 (`file:操作`) | 赤になる test id (予想) |
|---|---|---|---|
| 1 | facade 互換 | `structured.py`: import から `SchemaOutcome` を外す | `r2db-api/tests/test_foundation.py::test_storage_outcomes_leaf_preserves_structured_facade` (新規。`structured` と `backend` の 3 名が leaf と `is`) |
| 2 | frozen、fields、既定値 | `storage_outcomes.py`: `MutationOutcome` の `frozen=True` を外す | `r2db-api/tests/test_foundation.py::test_storage_outcomes_are_frozen_with_contract_defaults` (新規。代入で `FrozenInstanceError`。3 型の `dataclasses.fields` の名前と既定値を literal で固定し、`revisions` の長さ違いで `ValueError` を確かめる) |
| 3 | `QueryOutcome` は長さ違いの `revisions` を拒否する | `storage_outcomes.py`: `raise ValueError` の条件を `False and …` にする | 同上 |
| 4 | 実行 → 監査: 本当に実行した mutation は `allow` として監査される (WF-3) | `storage_outcomes.py`: `MutationOutcome` の `replayed: bool = False` を `True` にする | `r2db-api/tests/test_application_audit.py::test_delete_bearing_mutate_never_enters_the_buffer_path` (L3010 の `outcome == "allow"`)、2 の新規テスト |
| 5 | leaf の import が許可リストの内だけ | `storage_outcomes.py`: `import os` を 1 行足す | `tools/tests/test_leaf_import_direction.py::test_leaf_modules_import_only_their_allowlisted_modules` |
| 6 | 新 leaf が分類される | 一覧から `storage_outcomes.py` の行を消す | `tools/tests/test_leaf_import_direction.py::test_every_src_module_is_classified` |
| 7 | 飛び石で間を動かさない (WF-1) | **監査照合**: L1074-1239 の差分 0。`_ISOMORPHIC_TARGETS` の差分 0 | — |
| 8 | 逐語移動 (40c) | **監査照合**: 3 型と見出しコメントが AST とコメントで逐語。括弧書きは `backend.py` L31 の 1 箇所だけ | — |
| 9 | 同型登録しない・統合の手順 | **監査照合**: WF-4 と WF-6 | — |

### 5.34 WP-3e — MitateDB の要求の語彙の定数 (CE5、**独立レビュー反映済み**)

**目的**: 7 つの定数を leaf `MitateDB-api/src/mitatedb_api/request_vocabulary.py` へ移す (名前は W3-6)。**WP-3d の統合後に着手する。**

| 項目 | 実測 (`9994d7c`。3d の統合後に取り直す) |
|---|---|
| 移動範囲 (7 名、174 行) | `cell.py` L56-229。7 定数とその前後の説明コメントを含む。**連続した範囲で、飛び石は要らない。** CE7 の `_surfaces_document_fragment` (L232-241) と登録 helper (L244-339) は、範囲の後ろにある |
| leaf の import | 無い (literal だけ)。許可は空集合 |
| facade | 7 名を import で読む。読み手は `_CONTRACT_MUTATION_VOCABULARY` が L2477・L2569、`_TRANSACT_*_KEYS` が L2475〜L2697、`_FIELD_TYPE_VOCABULARY` が L1198・L1548、`_UNSUPPORTED_CONTRACT_OPERATORS` が L3527・L3552、`_DELETE_CONSEQUENCE` が L2400〜L2465。他の module と tests はコメントで名前を引くだけ |
| denial・件数 pin・sib・allowlist | 無い |
| 範囲内の位置参照 (WF-5) | 付ける (「(in `cell.py`)」): L58「`transact()` below」、L68「refused unconditionally here」、L84「`_plan_operation` below」、L101「"insert" branch below」、L121「the excess-key checks below」、L167「capability entry below」(3h で改める)、L171「branch below」、L177「`_bind_filters` below」。付けない: L127・L149 の above、L144・L148・L201 の here、L189 の「paragraph immediately below」(いずれも範囲内を指す)、L113 の「this method's own」(同じ文の `ApplicationCell.transact` を指し、移動後も成り立つ)。既知の穴: L195「The phrase construction below」(WP-1b 以降、指す先は `delete_confirmation.py` にある) |
| 範囲外の位置参照 (WF-5) | 付ける (「(now in `request_vocabulary.py`)」、いずれも CH は無い): `MitateDB-api/tests/test_http.py` L1491「(`_TRANSACT_INSERT_KEYS` in `cell.py`)」の `cell.py` の直後。`cell.py` L2409-2410「the module-level comment above `_DELETE_CONSEQUENCE`」の above の直後。L2475-2477「the module's own `_TRANSACT_INSERT_KEYS`/…/`_CONTRACT_MUTATION_VOCABULARY` constants」の constants の直後。L2697-2698「`_TRANSACT_INSERT_KEYS`/`_UPDATE_KEYS`/`_DELETE_KEYS` above」の above の直後。`MitateDB-api/src/mitatedb_api/delete_confirmation.py` L50 の既存の「(in `cell.py`)」の直後 (移動で誤りになる)。`MitateDB-api/conformance/conformance_adapter_mitatedb.py` L1467「`cell.py`'s own pre-1.6.0 `_FIELD_TYPE_VOCABULARY`」の `_FIELD_TYPE_VOCABULARY` の直後。付けない: `cell._FIELD_TYPE_VOCABULARY` (`backend.py` L131、`http.py` L541、`backend_sqlite.py` L37、`conformance_adapter_mitatedb.py` L1480・L1645、`test_constraints_declaration.py` L65)、`test_denial_details_and_request_id.py` L145 (検査は `_plan_operation` に残る) |
| 評価順 | 読み手の `_plan_operation` は、`transact` の `_require_data` (L2684) と `_gate` (L2708) より後で走る |

| 触るファイル | 触らないファイル |
|---|---|
| `MitateDB-api/src/mitatedb_api/cell.py` (移動範囲と import 1 行)、新規 `MitateDB-api/src/mitatedb_api/request_vocabulary.py`、`MitateDB-api/tests/test_foundation.py` (新規テスト 3 本)、`MitateDB-api/tests/test_http.py` (L1491 の括弧書きだけ)、`MitateDB-api/src/mitatedb_api/delete_confirmation.py` (L50 の括弧書きだけ)、`MitateDB-api/conformance/conformance_adapter_mitatedb.py` (L1467 の括弧書きだけ)、`tools/tests/test_leaf_import_direction.py` (leaf 1 行、許可は空) | `http.py`、`backend*.py`、`MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py`、`MitateDB-api/tests/test_audit_query.py`、`conformance-tests/`、r2db-api 全部、`docs/code-history/`、`docs/design/`、roadmap |

| # | 完了条件 | 変異 (`file:操作`) | 赤になる test id (予想) |
|---|---|---|---|
| 1 | facade 互換 | `cell.py`: import から `_TRANSACT_DELETE_KEYS` を外す | `MitateDB-api/tests/test_foundation.py::test_request_vocabulary_leaf_preserves_cell_facade` (新規。7 名が leaf と `is`) |
| 2 | 定数の値は変わらない | `request_vocabulary.py`: `_TRANSACT_INSERT_KEYS` から `"idempotency_key"` を外す | `MitateDB-api/tests/test_foundation.py::test_request_vocabulary_constants_are_literal` (新規。7 定数を literal で固定する) |
| 3 | 認可 → 検査: 鍵集合の検査は認可の後に走る (WF-3) | `cell.py` `transact`: `self._require_data(principal, request_id=request_id)` (L2684) の行を `with self._gate(...)` のブロックの後ろへ移す | `MitateDB-api/tests/test_foundation.py::test_transact_key_set_check_runs_after_authorization` (新規。別の Application の principal と、`expected_revision` を持つ insert の組では `AuthorizationError`。同じ Application では `CapabilityError`) |
| 4 | leaf の import が許可リストの内だけ | `request_vocabulary.py`: `import os` を 1 行足す | `tools/tests/test_leaf_import_direction.py::test_leaf_modules_import_only_their_allowlisted_modules` |
| 5 | 新 leaf が分類される | 一覧から `request_vocabulary.py` の行を消す | `tools/tests/test_leaf_import_direction.py::test_every_src_module_is_classified` |
| 6 | 逐語移動と位置参照 (40c) | **監査照合**: コメントが逐語。括弧書きは上表の範囲内 8 箇所と範囲外 6 箇所だけ | — |
| 7 | 登録 helper を動かさない・同型登録しない・統合の手順 | **監査照合**: `_ISOMORPHIC_TARGETS` の差分 0 と L232-339 の差分 0、WF-4、WF-6 | — |

【訂正註 2026-09-15 (WP-3e の実装、監督裁定 W3-15・W3-16)。上の表は起草時の原文であり、消さずに残す (`OPERATING_CONDITIONS.md` §1.8 の 57)】

- 範囲外の位置参照の括弧書きは 6 箇所ではなく 9 箇所である。括弧書きは計 17 箇所 (範囲内 8、範囲外 9)。完了条件 6 の「範囲外 6 箇所」も 9 箇所と読む。足した 3 箇所は、`cell.py` の `add_field` の docstring (W3-15) と `MitateDB-api/src/mitatedb_api/http.py` L821・L993 (W3-16) である。
- 「範囲外の位置参照は、いずれも CH は無い」は誤りである。`http.py` の 2 箇所に CH-0221・CH-0228 が付く。訂正の記録は 2 件 (CH-0221、CH-0228) である。
- 触るファイルに `http.py` (括弧書き 2 箇所) と `docs/code-history/MitateDB-api/http.md` (訂正の記録 2 件) を足す (W3-16)。「触らないファイル」の `http.py` と `docs/code-history/` は、この 2 件を除いて読む。
- 新規テストはレビュー後に締めた: `test_request_vocabulary_constants_are_literal` に 7 定数すべての型の完全一致の pin (変異 C2b)、`test_transact_key_set_check_runs_after_authorization` の同じ Application の枝に `details["field"]` の assert (変異 C3b)。

### 5.35 WP-3f — r2db の mutation の束縛 (ST8、**独立レビュー反映済み**)

**目的**: ST8 を leaf `r2db-api/src/r2db_api/mutation_binding.py` (§2.1) へ移す。**WP-3e の統合後に着手する。**

| 項目 | 実測 (`9994d7c`。3e の統合後に取り直す) |
|---|---|
| 移動範囲 (11 名、飛び石 2 塊、計 212 行) | `structured.py` L63-103 (41 行) と L136-306 (171 行)。§2.1 の 10 名に `OPERATORS` (L63) を足す。`OPERATORS` を読むのは `Predicate.validate` (L100) だけで、facade に残すと leaf が `structured` を import する循環になる。間の D-1 境界の見出しコメント (L104-133) は W3-7 (b) により facade に残す |
| leaf の import | `__future__`、`dataclasses`、`typing`、`.errors` (`fail`・`observed_type_of`・`violation`)、`.identifier_rules` (`validate_identifier`) |
| facade (6 名) | `BoundMutation`・`Predicate`・`bind_mutation`・`validate_predicates`・`validate_projection` (`ApplicationCell` の L1427-1428・L1748・L1857 と `postgres.py` L111-143 が読む) と、`parse_predicate` (`service.py` L22)。`Predicate` は `backend.py` L27 と tests も読む。facade に残さないもの: `OPERATORS`・`_mapping`・`MUTATION_OPERATIONS`・`_MUTATION_KEYS`・`MAX_EXPECTED_REVISION_LENGTH`。src・tests・conformance のコードでの読み手は 0 で、コメントか docstring に名前が出るだけである |
| denial | 18 (4-key 又は `NOT_FOUND`) |
| 件数 pin | `structured.py` 67 → 49、`mutation_binding.py` 18。module tuple と dict の両方に足す |
| `SCANNED_MODULES`・sib tuple | どちらにも `mutation_binding.py` を足し、sib テストの docstring の module 一覧も合わせる (W3-4)。allowlist の差分は 0 |
| 修飾名の固定 | `r2db-api/tests/test_audit_query.py` L1496 の `"structured.bind_mutation"` を `"mutation_binding.bind_mutation"` に改める。定義が移るだけで、要素の数は変わらない (W3-8) |
| 範囲内の位置参照 (WF-5) | 付けない: L89・L156・L293 の below、L193 の above、L212・L218・L240・L285 の here (いずれも範囲内を指す)。既知の穴: L224「`_mutate_outcome` below」(指す先は `service.py`) |
| facade に残る見出しの位置参照 (W3-7 (b)) | 付ける: L106「Everything below this point」の直後に、`validate_projection` 以下が `mutation_binding.py` に移ったことを示す括弧書き 1 つ。この 1 つが見出し全体を覆う。付けない: L109「`ApplicationCell` (below)」(facade に残り、成り立つ)、L115「decided exactly once, here」と L120「pure-shape-checked here」(L106 の括弧書きが覆う) |
| 範囲外の位置参照 (WF-5) | 付ける: `r2db-api/src/r2db_api/postgres.py` L1897「`structured.OPERATORS`」の直後に「(now in `mutation_binding.py`)」。これは CH-0057 の塊 (L1893-1901、marker L1901) の中なので、`docs/code-history/r2db-api/postgres.md` の CH-0057 節 (L1114) に訂正の記録を足す。もう 1 件は `r2db-api/conformance/conformance_adapter_r2db_http.py` L3576「`structured.py`'s `bind_mutation`」の直後に「(now in `mutation_binding.py`)」(CH は無い)。付けない: `control_plane.py` L1013・L1030、`postgres.py` L1608・L1673・L1896、`test_denial_details_and_request_id.py` L255 (いずれも名前だけ) |
| 評価順 | 呼出しは `ApplicationCell._apply` (L1748) と `PostgresCell._apply` (`postgres.py` L1539)。どちらも `DataService._mutate_outcome` の `_slot` (L800) の中から届く。facade の呼出しは変えない |

| 触るファイル | 触らないファイル |
|---|---|
| `r2db-api/src/r2db_api/structured.py` (移動範囲と import 1 行)、新規 `r2db-api/src/r2db_api/mutation_binding.py`、`r2db-api/src/r2db_api/postgres.py` (L1897 の括弧書きだけ)、`r2db-api/conformance/conformance_adapter_r2db_http.py` (L3576 の括弧書きだけ)、`docs/code-history/r2db-api/postgres.md` (CH-0057 の訂正の記録だけ)、`r2db-api/tests/test_foundation.py` (新規テスト 4 本)、`r2db-api/tests/test_l1_details_vocabulary_ast_scan.py` (`SCANNED_MODULES`、件数 pin、sib tuple とその docstring)、`r2db-api/tests/test_audit_query.py` (L1496 の 1 要素)、`tools/tests/test_leaf_import_direction.py` (leaf 1 行、許可 `dataclasses`・`typing`・`.errors`・`.identifier_rules`) | `service.py`、`backend.py`、`control_plane.py`、同 L1 scan の `_BACKEND_LAYER_ALLOWLIST`、`_ISOMORPHIC_TARGETS`、`conformance-tests/`、MitateDB-api 全部、`docs/design/`、roadmap |

| # | 完了条件 | 変異 (`file:操作`) | 赤になる test id (予想) |
|---|---|---|---|
| 1 | facade 互換 | `structured.py`: import から `parse_predicate` を外す | `r2db-api/tests/test_foundation.py::test_mutation_binding_leaf_preserves_structured_facade` (新規。6 名が leaf と `is`) |
| 2 | insert は filter を拒否する | `mutation_binding.py`: `if name == "insert" and "where" in operation:` を `if False and …` にする | `r2db-api/tests/test_foundation.py::test_mutation_binding_denials_carry_code_and_details` (新規。insert に `where`、未知の演算子 `like`、str でない `expected_revision` の code と details を literal で固定する) |
| 3 | 未知の operation は batch の位置を持つ `CAPABILITY_UNSUPPORTED` | `mutation_binding.py`: `field=f"operations/{operation_index}/operation"` を `field="operation"` にする | `r2db-api/tests/test_denial_details_and_request_id.py::test_capability_unsupported_field_reflects_batch_index_for_an_unsupported_mutation_operation` |
| 4 | `Predicate` は `OPERATORS` の外の演算子を拒否する | `mutation_binding.py`: `OPERATORS` に `"like"` を足す | 2 の新規テスト |
| 5 | 認可 → 検査: 束縛は認可の後に走り、deny が監査される (WF-3) | `structured.py` `ApplicationCell._apply` の既存の `bind_mutation(...)` 呼出し (L1748) を、`service.py` `_mutate_outcome` の `with self._slot(...)` (L800) の前へ移す (WP-3c の 6 と同じく既存の呼出しの位置を変える。新しい呼出しは足さない) | `r2db-api/tests/test_foundation.py::test_mutation_binding_runs_after_authorization_and_is_audited` (新規。無効な context と、`where` を持つ insert の組では `AUTH_INVALID`。有効な runtime では `VALIDATION_FAILED` の deny が `ControlAuthority.audit_events()` に残り、行が増えない) |
| 5b | 検査 → 実行 | **監査照合**: `ApplicationCell._apply` と `PostgresCell._apply` の `bind_mutation` 呼出しの位置と引数の差分 0 | — |
| 6 | 移動先が `SCANNED_MODULES` に入る (40b) | L1 scan: `SCANNED_MODULES` から `mutation_binding.py` を外す | `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py::test_every_module_with_a_vocabulary_denial_is_accounted_for` |
| 7 | 件数 pin (`structured.py` 49、`mutation_binding.py` 18) | `mutation_binding.py`: 4-key の `fail("VALIDATION_FAILED", "x", details=violation("request_schema"))` を呼ぶ関数を 1 つ足す | `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py::test_ast_full_count_matches_the_audit_site_count` |
| 8 | 移した denial が 4-key のまま | `mutation_binding.py`: `"Mutation values must be an object."` の `fail` から `details=` を外す | `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py::test_every_choke_point_denial_carries_details_ast_full_count`、`::test_allowlist_entries_match_real_bare_call_sites` |
| 9 | sib tuple に移動先が入る (W3-4) | `mutation_binding.py`: `"Mutation contains too many fields."` を `"A value in this request is not acceptable to the underlying storage."` にする | `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py::test_backend_layer_allowlist_entries_have_no_in_memory_sibling_denial` |
| 10 | 修飾名の固定を移動に合わせる | `test_audit_query.py`: `"structured.bind_mutation"` を改めずに残す | `r2db-api/tests/test_audit_query.py::test_non_audit_operation_parameters_exclusion_list_entries_exist`、`::test_every_definition_taking_the_field_declares_it_keyword_only` |
| 11 | leaf の import が許可リストの内だけ | `mutation_binding.py`: `import os` を 1 行足す | `tools/tests/test_leaf_import_direction.py::test_leaf_modules_import_only_their_allowlisted_modules` |
| 12 | 新 leaf が分類される | 一覧から `mutation_binding.py` の行を消す | `tools/tests/test_leaf_import_direction.py::test_every_src_module_is_classified` |
| 13 | 訂正の記録 (§5.27 の 0g の 4) | `postgres.md`: CH-0057 の訂正の記録を書かない | `tools/tests/test_comment_provenance.py::test_0f_both_peers_all_src_rev_vs_itself_is_green` (使い捨ての clone で実行) |
| 14 | 逐語移動と位置参照 (40c) | **監査照合**: AST とコメントが逐語。括弧書きは L106 (W3-7 (b))、`postgres.py` L1897、adapter L3576 だけ。見出し L104-133 はそれ以外の差分 0 | — |
| 15 | 登録 helper・同型・統合 | **監査照合**: `_ISOMORPHIC_TARGETS` の差分 0、WF-4、WF-6 | — |

【訂正註 2026-09-15 (WP-3f の実装、監督裁定 W3-17・W3-18)。上の表は起草時の原文であり、消さずに残す (`OPERATING_CONDITIONS.md` §1.8 の 57)】

- 範囲外の位置参照の括弧書きは 2 箇所ではなく 10 箇所である。manifest の `postgres.py` L1897 と adapter L3576 に、W3-17 の 8 箇所を足す。括弧書きは計 11 箇所 (見出し L106 と範囲外 10)。完了条件 14 の「括弧書きは L106、`postgres.py` L1897、adapter L3576 だけ」は W3-17 と合わせて読む。
- 範囲外の位置参照の「付けない」に挙げた `control_plane.py` L1013・L1030 は、W3-17 で付ける側に分類し直した。
- 訂正の記録は 3 件である: CH-0057 (manifest)、CH-0266・CH-0272 (W3-17)。
- 触るファイルに `r2db-api/src/r2db_api/capabilities_document.py`・`r2db-api/src/r2db_api/control_plane.py`・`r2db-api/conformance/conformance_adapter_r2db.py` (括弧書きだけ) と `docs/code-history/r2db-api/control_plane.md` (訂正の記録だけ) (W3-17)、`tools/tests/test_comment_provenance.py` (W3-18。q4 の削除だけ) を足す。`structured.py` は L442 の括弧書き (W3-17) も触る。「触らないファイル」の `control_plane.py` は、この括弧書きを除いて読む。
- 触るファイルの行の「新規テスト 4 本」は 3 本である。完了条件の表が名指す新規テストは 3 つで、条件 4 は条件 2 のテストを使う。§5.39 の新規テストの数の「3f 4」も 3 と読む。
- 見出しの括弧書きの名前は backtick で囲む (レビュー N1)。

### 5.36 WP-3g — r2db の schema の束縛の型と定数 (ST9 の一部、**独立レビュー反映済み**)

**目的**: ST9 の 11 名のうち `bind_schema_operation` を除く 10 名を、leaf `r2db-api/src/r2db_api/schema_binding.py` (§2.1) へ移す。`bind_schema_operation` は developer gate (L578-579) も本体 (L580-975) も `structured.py` に残す。**WP-3f の統合後に着手する。**

**範囲を限る理由 (実測)**: gate は関数の先頭 2 行なので、本体から分けること自体はできる。しかし本体は、登録 helper の `validate_enum_declaration` を L822 と L864 で呼んでいる。本体だけを leaf へ移すと、leaf が `structured` を import する循環 (設計 D-1 が禁じる) になる。helper を一緒に移すと、登録行の差替え (Class D) になる。枠の中では本体を移せないので、範囲を gate を含む関数の外に限る (W3-9)。

| 項目 | 実測 (`9994d7c`。3f の統合後に取り直す) |
|---|---|
| 移動範囲 (10 名、飛び石 3 塊、計 197 行) | L309-431 の 123 行 (`FIELD_TYPES` の説明コメントから `_ENUM_ELIGIBLE_TYPES` まで)、L456-468 の 13 行 (`_ConstraintDeclarationError`)、L514-574 の 61 行 (`_fail_constraint_declaration`・`BoundSchemaOperation`) |
| 残すもの | L434-453 の `enum_member_matches_type` と L471-511 の `validate_enum_declaration` (どちらも登録 helper で、本文の差分 0)、L577-975 の `bind_schema_operation` |
| leaf の import | `__future__`、`dataclasses`、`typing`、`.errors` (`fail`)、`.value_types` (`_declared_type_label`) |
| facade (9 名) | `bind_schema_operation` が読む 8 名 (`BoundSchemaOperation`・`ConstraintPatch`・`FIELD_TYPES`・`FieldConstraints`・`MAX_INDEX_FIELDS`・`_ConstraintDeclarationError`・`_SCHEMA_KEYS`・`_fail_constraint_declaration`) と、`validate_enum_declaration` が読む `_ENUM_ELIGIBLE_TYPES`。`postgres.py` と `ApplicationCell` も 4 名を読む。facade に残さないもの: `SCHEMA_OPERATIONS` (読み手は 0。L324 のコメント自体が dead constant だと書いている。Y-3・Y-7 と同じ扱い) |
| denial・件数 pin | denial は 1 (L522、4-key)。件数 pin は `structured.py` 49 → 48、`schema_binding.py` 1。module tuple と dict の両方に足す。`FORBIDDEN` (L579) は L1 の数に入らず、動かさない |
| `SCANNED_MODULES`・sib tuple・修飾名 | `SCANNED_MODULES` と sib tuple に `schema_binding.py` を足す。allowlist の差分は 0。`_NON_AUDIT_OPERATION_PARAMETERS` の差分も 0 (`bind_schema_operation` は残り、移す関数に `operation` 引数は無い) |
| 範囲内の位置参照 (WF-5) | 付ける (「(in `structured.py`)」): L315「`field_types`, below」、L316「`bind_schema_operation` below」、L327「chain below」、L337「here」、L340「this function」と L342「THIS function」(どちらも `bind_schema_operation` を指し、leaf には指す先が無い)、L359「`validate_enum_declaration` below」、L429「the two functions below」、L457「`validate_enum_declaration` below」、L516「call site below」、L544「`bind_schema_operation` below」。付けない: L324 の below、L386 の above、L563 の below (いずれも範囲内を指す)、L459「never surfaced outside this module」(移動前から `postgres.py` L2134 も捕まえており、指す先が誤っている。WF-5 (iii)、既知の穴)。L312・L318・L353・L520 は既に括弧書きがある |
| 範囲外の位置参照 (WF-5) | 付ける: `structured.py` L723 (`bind_schema_operation` の中)「`FIELD_TYPES`'s own module-level comment above」の above の直後に「(in `schema_binding.py`)」。もう 1 件は `r2db-api/src/r2db_api/value_types.py` L13「in `structured.py`」の直後に「(now in `schema_binding.py`)」(CH は無い)。付けない: `test_audit_query.py` L2688 (`structured._fail_constraint_declaration` は facade から読める)、`test_http.py` L1100 (指す文は `bind_schema_operation` に残る)。既知の穴: 登録 helper の中の L482「`_ENUM_ELIGIBLE_TYPES` above」と L484「this module's own internal vocabulary」は WF-1 により補わない。L328「`service.py`'s `schema_ops`/`unsupported` literals」は WP-3b 以降古い |
| 評価順 (WF-2) | gate は `bind_schema_operation` の先頭に残る。移す名前を読む検査 (L582 の `_SCHEMA_KEYS`) より前にある |

| 触るファイル | 触らないファイル |
|---|---|
| `r2db-api/src/r2db_api/structured.py` (移動範囲、import 1 行、L723 の括弧書き)、新規 `r2db-api/src/r2db_api/schema_binding.py`、`r2db-api/src/r2db_api/value_types.py` (L13 の括弧書きだけ)、`r2db-api/tests/test_foundation.py` (新規テスト 3 本)、`r2db-api/tests/test_l1_details_vocabulary_ast_scan.py` (`SCANNED_MODULES`、件数 pin、sib tuple とその docstring)、`tools/tests/test_leaf_import_direction.py` (leaf 1 行、許可 `dataclasses`・`typing`・`.errors`・`.value_types`) | `postgres.py`、`service.py`、`r2db-api/tests/test_audit_query.py`、`_BACKEND_LAYER_ALLOWLIST`、`conformance-tests/`、MitateDB-api 全部、`docs/code-history/`、`docs/design/`、roadmap |

| # | 完了条件 | 変異 (`file:操作`) | 赤になる test id (予想) |
|---|---|---|---|
| 1 | facade 互換 | `structured.py`: import から `ConstraintPatch` を外す | `r2db-api/tests/test_foundation.py::test_schema_binding_leaf_preserves_structured_facade` (新規。9 名が leaf と `is`) |
| 2 | 定数と型は変わらない | `schema_binding.py`: `MAX_INDEX_FIELDS = 16` を `17` にする | `r2db-api/tests/test_foundation.py::test_schema_binding_constants_and_types_are_literal` (新規。`FIELD_TYPES`・`MAX_INDEX_FIELDS`・`_SCHEMA_KEYS`・`_ENUM_ELIGIBLE_TYPES` の値と、3 つの dataclass の fields と既定値を literal で固定する) |
| 3 | 宣言の拒否は field path と型の label を持つ | `schema_binding.py`: `"violated_declaration": "constraint_declaration"` を `"request_schema"` にする | 2 の新規テスト (`_fail_constraint_declaration("enum", None, _ConstraintDeclarationError("m"))` の details を literal で固定する) |
| 4 | 認可 → 検査: developer gate は形の検査より先に走る (WF-3) | `structured.py` `bind_schema_operation`: `if not developer:` とその `fail("FORBIDDEN", …)` の 2 行を、`_SCHEMA_KEYS` の検査の後ろへ移す | `r2db-api/tests/test_foundation.py::test_schema_binding_developer_gate_precedes_shape_checks` (新規。`developer=False` と未知の key の組で `FORBIDDEN`) |
| 5 | 移動先が `SCANNED_MODULES` に入る (40b) | L1 scan: `SCANNED_MODULES` から `schema_binding.py` を外す | `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py::test_every_module_with_a_vocabulary_denial_is_accounted_for` |
| 6 | 件数 pin (`structured.py` 48、`schema_binding.py` 1) | `schema_binding.py`: 4-key の `fail` を呼ぶ関数を 1 つ足す | `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py::test_ast_full_count_matches_the_audit_site_count` |
| 7 | 移した denial が details を持つ | `schema_binding.py`: `_fail_constraint_declaration` の `details={…}` を外す | `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py::test_every_choke_point_denial_carries_details_ast_full_count`、`::test_allowlist_entries_match_real_bare_call_sites` |
| 8 | sib tuple に移動先が入る (W3-4) | `schema_binding.py`: `str(exc)` を `"A value in this request is not acceptable to the underlying storage."` にする | `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py::test_backend_layer_allowlist_entries_have_no_in_memory_sibling_denial` |
| 9 | leaf の import が許可リストの内だけ | `schema_binding.py`: `import os` を 1 行足す | `tools/tests/test_leaf_import_direction.py::test_leaf_modules_import_only_their_allowlisted_modules` |
| 10 | 新 leaf が分類される | 一覧から `schema_binding.py` の行を消す | `tools/tests/test_leaf_import_direction.py::test_every_src_module_is_classified` |
| 11 | 登録 helper を動かさない (WF-1) | **監査照合**: L434-453 と L471-511 の本文の差分 0、`_ISOMORPHIC_TARGETS` の差分 0 | — |
| 12 | gate は facade に残る (WF-2) | **監査照合**: `bind_schema_operation` の差分は L723 の括弧書きだけ。leaf に `developer` と `FORBIDDEN` が無い | — |
| 13 | 逐語移動と位置参照 (40c) | **監査照合**: 3 塊が逐語。括弧書きは上表の範囲内 11 箇所と範囲外 2 箇所だけ | — |
| 14 | 同型・統合 | **監査照合**: WF-4、WF-6 | — |

【訂正註 2026-09-16 (WP-3g の実装、監督裁定 W3-19・W3-20)。上の表は起草時の原文であり、消さずに残す (`OPERATING_CONDITIONS.md` §1.8 の 57)】

- 括弧書きは計 15 箇所である。範囲内は 11 箇所のまま、範囲外は 2 箇所ではなく 4 箇所である: manifest の `structured.py` L723 と `value_types.py` L13 に、`provisional_gate.py` L29 (W3-19) と `conformance_adapter_r2db.py` L1215 (W3-20) を足す。完了条件 13 の「範囲内 11 箇所と範囲外 2 箇所だけ」は W3-19・W3-20 と合わせて読む。
- 移動後の行番号 (`bdea9ee` で実測): 範囲内は `schema_binding.py` L28・L29・L40・L50・L53・L55・L72・L142・L148・L164・L192、範囲外は `structured.py` L326 (manifest の L723)・`value_types.py` L13・`provisional_gate.py` L29・`conformance_adapter_r2db.py` L1215。manifest の行番号は `9994d7c` の実測で、`bdea9ee` で取り直したずれは一様な -203 だけだった (例: 移動範囲 L309-431 → L106-228)。
- 触るファイルに `MitateDB-api/src/mitatedb_api/provisional_gate.py` (W3-19) と `r2db-api/conformance/conformance_adapter_r2db.py` (W3-20) を足す (どちらも括弧書き 1 つだけ)。「触らないファイル」の MitateDB-api 全部は、`provisional_gate.py` の括弧書きを除いて読む。
- 完了条件 1 と 6 の変異は W3-20 で改めた形で読む: 1 は W3-14 の上書き (`ConstraintPatch = type("ConstraintPatch", (), {})`)、6 は移した site 自身の 4-key の `details` で `fail` を呼ぶ孤立した probe である。

### 5.37 WP-3h — MitateDB capabilities 文書の組立 (CE7、**独立レビュー反映済み**)

**目的**: `ApplicationRuntime.__build_capabilities_document` の本体と `_surfaces_document_fragment` を、leaf `MitateDB-api/src/mitatedb_api/capabilities_document.py` の `build_capabilities_document(*, is_developer, role, application_id, cell_config, process_ceiling)` (いずれも既定値なし) へ移す (名前は W3-6)。`capabilities()` の中の `__authorize` → `_limit_gate` → 組立 の順 (L3877-3881) は変えない。**WP-3g の統合後に着手する。**

| 項目 | 実測 (`9994d7c`。3g の統合後に取り直す) |
|---|---|
| 移動範囲 (計 371 行) | `cell.py` L232-241 (`_surfaces_document_fragment`、10 行) と L3885-4245 (本体、361 行)。L3884 の `is_developer = principal.role == Role.DEVELOPER` は method に残す (W3-10) |
| 本体の変更 | W3-3・W3-10 と同じく、差分を列挙する。L3884 の代入は method に残り、`is_developer` (L3960 が読む) は引数になる。置換は `principal.role.value` → `role` (L4244)、`principal.application_id` → `application_id` (L4243)、`self.__cell.config` → `cell_config` (L3885)、`self.__cell.process_ceiling` → `process_ceiling` (L3895)。これ以外に `self`・`principal`・`Role` を読む箇所は無い |
| method に残すもの | L3883 の `def __build_capabilities_document(self, principal):`、L3884 の代入、leaf を 5 つの keyword (`role=principal.role.value` ほか) で呼んで返す 1 文。`MitateDB-api/tests/test_denial_details_and_request_id.py` L562 と `platform_declarations.py` L858 がこの名前を引く |
| leaf の import | `.backend` (`SQL_OPERATOR_TOKENS`。`backend.py` は何も import しない)、`.surfaces` (`build_surfaces`。stdlib だけを import する) |
| facade | `build_capabilities_document` を import する。`_surfaces_document_fragment` の読み手は L4053 だけで、本体と一緒に移るので残さない。`build_surfaces` の import (L54) は読み手が 0 になるので削る。`SQL_OPERATOR_TOKENS` (L3548) と `Role` (L3690・L3701・L3884) は残す |
| denial・件数 pin・`SCANNED_MODULES`・sib・allowlist | 無い (範囲内の denial は 0) |
| 範囲内の位置参照 (WF-5) | 付ける (「(in `cell.py`)」): L4022「`.add_field` above」、L4027「the corresponding gate above」、L4039「`.alter_field` above」、L4109「every method below」、L4152「(`:531`)」、L4154「every method below」、L4200「this module's own」、L4239「`__authorize` above」。あわせて、3e で L167 (`request_vocabulary.py`) に付けた括弧書きを「(in `capabilities_document.py`)」に改める。付けない: L3887・L3893・L3902・L3913・L3959・L3987・L3998・L4070・L4082・L4096・L4141・L4148・L4215・L4222 (文書の中を指す)、L3906・L3984・L4001・L4012 の here。L4091・L4204 は既に括弧書きがある。既知の穴: L4128 の `r2db_api/service.py:936-937` (WP-3b 以降は `capabilities_document.py`)、L4152 の `:531` の値 (`_limit_gate` は L693)、`_surfaces_document_fragment` の「`control_plane_status` immediately above」 |
| 範囲外の位置参照 (WF-5) | 付ける (「(body now in `capabilities_document.py`)」): `platform_declarations.py` L858 の「`cell.py`'s own `__build_capabilities_document`」と L870 の「`cell.py`'s document-builder」、`test_denial_details_and_request_id.py` L562 の「`__build_capabilities_document`'s (`cell.py`)」、`cell.py` L3769・L3827 の「(`__build_capabilities_document` below)」の直後、`MitateDB-api/README.md` L198 の「`cell.py`'s `__build_capabilities_document`」。いずれも本体の literal を指し、CH は無い |

| 触るファイル | 触らないファイル |
|---|---|
| `MitateDB-api/src/mitatedb_api/cell.py` (移動範囲、method の 1 文、import)、新規 `MitateDB-api/src/mitatedb_api/capabilities_document.py`、`MitateDB-api/src/mitatedb_api/request_vocabulary.py` (L167 相当の括弧書きだけ)、`MitateDB-api/src/mitatedb_api/platform_declarations.py` (L858・L870 の括弧書きだけ)、`MitateDB-api/README.md` (L198 の括弧書きだけ)、`MitateDB-api/tests/test_denial_details_and_request_id.py` (L562 の括弧書きだけ)、`MitateDB-api/tests/test_foundation.py` (新規テスト 3 本)、`tools/tests/test_leaf_import_direction.py` (leaf 1 行、許可 `.backend`・`.surfaces`) | `http.py`、`config.py`、`surfaces.py`、`MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py`、`conformance-tests/`、r2db-api 全部 (SV2 と対にしない)、`docs/code-history/`、`docs/design/`、roadmap |

| # | 完了条件 | 変異 (`file:操作`) | 赤になる test id (予想) |
|---|---|---|---|
| 1 | 文書は引数だけから組み立てる | `capabilities_document.py`: `schema_operations` の `if is_developer` を `if not is_developer` にする | `MitateDB-api/tests/test_foundation.py::test_capabilities_document_is_built_only_from_explicit_arguments` (新規。leaf を直接呼ぶ。developer と runtime の `schema_operations`、`process_ceiling` 2 のときの `deployment_required`、surfaces の有無、`application_scope`・`role` を literal で固定する) |
| 2 | method は cell の値を渡す (`process_ceiling`) | `cell.py`: `process_ceiling=self.__cell.process_ceiling` を `process_ceiling=1` にする | `MitateDB-api/tests/test_foundation.py::test_runtime_capabilities_passes_cell_values_to_the_document` (新規。既定でない config、`process_ceiling=2`、runtime で `ApplicationRuntime.capabilities()` を呼び、literal と比べる)、`MitateDB-api/tests/test_process_ceilings_declaration.py::test_ceiling_two_maps_data_plane_in_memory_classes_to_deployment_required` |
| 3 | 同上 (`cell_config`) | `cell.py`: `cell_config=self.__cell.config` を `cell_config=FoundationConfig()` にする | 2 の新規テスト |
| 4 | 同上 (`is_developer`) | `cell.py`: L3884 の `==` を `!=` にする | `MitateDB-api/tests/test_foundation.py::FoundationTests::test_add_field_is_declared_and_usable_by_developer_only` |
| 4b | 同上 (`role`) | `cell.py`: `role=principal.role.value` を `role="developer"` にする | 2 の新規テスト |
| 4c | 同上 (`application_id`) | `cell.py`: `application_id=principal.application_id` を `application_id="other"` にする | 2 の新規テスト |
| 5 | 認可と limit gate の内側で組み立てる (WF-3) | `cell.py` `capabilities()`: `self.__authorize(request_id=request_id)` の前に `return self.__build_capabilities_document(self.__principal)` を足す | `MitateDB-api/tests/test_foundation.py::test_capabilities_document_is_built_after_authorization_inside_the_limit_gate` (新規。revoke した credential の runtime では認証のエラー、`max_requests_per_minute=1` の 2 回目では `ResourceLimitError`) |
| 6 | leaf の import が許可リストの内だけ | `capabilities_document.py`: `import os` を 1 行足す | `tools/tests/test_leaf_import_direction.py::test_leaf_modules_import_only_their_allowlisted_modules` |
| 7 | 新 leaf が分類される | 一覧から `capabilities_document.py` の mitatedb の行を消す | `tools/tests/test_leaf_import_direction.py::test_every_src_module_is_classified` |
| 8 | 本体は 4 つの置換を除き同一 | **監査照合**: 置換を戻した leaf の本体と、移動前の L3885-4245 が AST で一致し、L3884 は method で差分 0。差の列挙をログに残す (W3-3・W3-10) | — |
| 9 | 逐語移動と位置参照 (40c) | **監査照合**: コメントが逐語 (置換は識別子だけ)。括弧書きは上表の箇所だけ | — |
| 10 | 公開の宣言は変わらない | **監査照合**: 既存の capabilities テストと conformance (C-05・C-12・C-17 ほか) の集計行が前後で一致 | — |
| 11 | 登録 helper・同型・統合 | **監査照合**: `_ISOMORPHIC_TARGETS` の差分 0、WF-4 (SV2 と対にしない)、WF-6 | — |

【訂正註 2026-09-16 (WP-3h の実装、監督裁定 W3-21・W3-22)。上の表は起草時の原文であり、消さずに残す (`OPERATING_CONDITIONS.md` §1.8 の 57)】

- 括弧書きの数。上の表が挙げるのは、範囲内 8 箇所、範囲外 6 箇所 (`platform_declarations.py` L858・L870、`test_denial_details_and_request_id.py` L562、`cell.py` L3769・L3827、`README.md` L198)、`request_vocabulary.py` の括弧書き 1 つの書換えである。実装では、範囲内は R5 の 2 箇所を足して 10 箇所、範囲外は W3-21 の 1 箇所 (`platform_declarations.py` L772) と W3-22 の 4 箇所 (R1〜R4) を足して 11 箇所になった。括弧書きは計 21 箇所、書換えは 1 つである。完了条件 9 の「括弧書きは上表の箇所だけ」は W3-21・W3-22 と合わせて読む。
- 移動後の行番号 (`ffd6493` に移動を適用して実測): 範囲内は `capabilities_document.py` L161・L166・L177・L248・L292・L293・L340・L378 と R5 の L301・L303。範囲外は `cell.py` L3591 (manifest の L3769)・L3649 (L3827)・L3652 (R1)、`platform_declarations.py` L773 (W3-21。L772 から折り返す文)・L858・L870、`test_denial_details_and_request_id.py` L562、`README.md` L198-199、`http.py` L601 (R2)、`test_c05_limit_declaration_agreement.py` L932・L1203 (R3・R4)。書換えは `request_vocabulary.py` L119 (manifest の L167。`cell.py` とは別のずれ)。manifest の行番号は `9994d7c` の実測である。`ffd6493` で取り直すと、`cell.py` のずれは一様な -166 だけだった (例: 本体 L3885-4245 → L3719-4079、`_surfaces_document_fragment` L232-241 → L66-75)。
- 触るファイルに次の 3 つを足す (W3-22): `MitateDB-api/src/mitatedb_api/http.py` (R2 の括弧書き 1 つ)、`docs/code-history/MitateDB-api/http.md` (CH-0208 の訂正の記録)、`conformance-tests/test_c05_limit_declaration_agreement.py` (R3・R4 のコメントだけ)。`MitateDB-api/tests/test_foundation.py` は、新規テスト 3 本に加えてテスト 3 の強化 (n2) を含む。新規の test method は増えない。
- 変異は計 11 である。表の 1〜7・4b・4c の変異 (C1〜C7・C4b・C4c) に次の 2 つを足す。n2 は `capabilities()` の `__authorize` と `_limit_gate` の入替えで、強化したテスト 3 が赤になる。n3 は C2 と同じ変異で、`MitateDB-api/tests/test_process_ceilings_declaration.py::test_ceiling_two_maps_data_plane_in_memory_classes_to_deployment_required` だけを走らせて赤になる。

### 5.38 WP-3i — MitateDB の値の正規化 (CE6 の一部、**独立レビュー反映済み**)

**目的**: CE6 のうち、`self._backend`・`self.config`・`self._identifier` を読まない 3 method (`_check_predicate_value`・`_normalize_value`・`_normalize_value_for_storage`) を、leaf `MitateDB-api/src/mitatedb_api/request_binding.py` (§2.2) の関数へ移す。class には委譲の属性を残す。**WP-3h の統合後に着手する。**

**CE6 の実測 (10 method、計 564 行、denial 20)**:

| method | 行 (行数) | denial | self 経由で読むもの |
|---|---|---|---|
| `_validate_update` | L2205-2261 (57) | 2 | `_bind_filters`・`_prepare_values` |
| `_select_fields` | L3122-3162 (41) | 3 | `_backend.field_domains`、`config.max_fields`、`_identifier` |
| `_decode_rows` | L3164-3185 (22) | 0 | `_backend.field_types` |
| `_bind_order_by` | L3203-3253 (51) | 5 | `_backend.field_domains`、`_identifier`、`_MAX_ORDER_BY_TERMS` |
| `_check_missing_required_fields` | L3255-3305 (51) | 1 | `_backend.field_types_and_constraints` |
| `_prepare_values` | L3307-3442 (136) | 3 | `_backend.field_domains`・`field_types_and_constraints`・`encode_value`、`config.max_fields`、`_identifier` |
| `_check_predicate_value` | L3444-3462 (19) | 0 | なし |
| `_bind_filters` | L3464-3605 (142) | 5 | `_backend.field_domains`・`field_types`・`encode_value`、`config.max_filter_terms`、`_identifier` |
| `_normalize_value` | L3607-3630 (24) | 1 | なし |
| `_normalize_value_for_storage` | L3632-3652 (21) | 0 | `cls._normalize_value` |

- `backend.py` L98-102 によると、`field_domains` は live catalog を読み、存在の検査も兼ねる。`_decode_rows` から `_prepare_values` までと `_bind_filters` の 6 method は DB の catalog を読むので、設計 §3.1 の「DB を読まない」と §7 の停止条件に当たる。`_validate_update` はそのうち 2 つを呼び、`update` (L2273) と `_plan_operation` (L2550、§3.2 の plan) の両方から呼ばれる。この 7 method は 3i に含めない (W3-11)。
- 3 method の呼出し元は変えない。`_check_predicate_value` は `_bind_filters` の L3586・L3600 から、`_normalize_value_for_storage` は `_prepare_values` の L3440 と `_bind_filters` の L3593・L3602 から、`_normalize_value` は L3652 から呼ばれる。経路は `read` (L2171 の `_gate` の中)、`insert` (L2116)、`update` (L2266)、`_plan_operation`、`_validate_delete_confirmation` の 5 つである。

| 項目 | 実測 (`9994d7c`。3h の統合後に取り直す) |
|---|---|
| 移動範囲 (3 名、飛び石 2 塊、計 65 行) | L3444-3462 (19 行) と L3607-3652 (46 行、空行 L3631 を含む)。間の `_bind_filters` (L3464-3605) は残す |
| 本体の変更 | デコレータ 2 つと `cls` 引数を除き、`cls._normalize_value` → `_normalize_value` (L3652) の置換 1 つ (W3-12) |
| class に残すもの | `_check_predicate_value = staticmethod(_check_predicate_value)` と、`_normalize_value`・`_normalize_value_for_storage` の同じ形の 3 行。呼出し元の `self.`/`cls.` はそのまま使える。`backend.py` L309、`backend_postgres.py` L27、`backend_sqlite.py` L41、`postgres_types.py` L55、`postgres_value_domain.py` L78、`delete_confirmation.py` L30 は `ApplicationCell._normalize_value*` の名前で引く |
| leaf の import | `json`、`.errors` (`ValidationError`・`violation`)、`.field_types` (`check_declared_value`)。`cell.py` の `json`・`check_declared_value` は他の読み手があるので残す |
| denial・件数 pin | denial は 1 (L3627、4-key)。件数 pin は `cell.py` 43 → 42、`request_binding.py` 1 |
| `SCANNED_MODULES`・sib tuple | どちらにも `request_binding.py` を足す (sib は 7 → 8 module)。allowlist の差分は 0 |
| 位置参照 (WF-5) | 付ける: L3628「this class's own defensive style」の直後に「(`ApplicationCell`, in `cell.py`)」。付けない: L3622「the accepted set above」(関数の中)、2 つの docstring (名前だけ)。範囲外の `ApplicationCell._normalize_value*` は委譲の属性で読めるので付けない |

| 触るファイル | 触らないファイル |
|---|---|
| `MitateDB-api/src/mitatedb_api/cell.py` (移動範囲、委譲 3 行、import 1 行)、新規 `MitateDB-api/src/mitatedb_api/request_binding.py`、`MitateDB-api/tests/test_foundation.py` (新規テスト 4 本)、`MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py` (`SCANNED_MODULES`、件数 pin、sib tuple とその docstring)、`tools/tests/test_leaf_import_direction.py` (leaf 1 行、許可 `json`・`.errors`・`.field_types`) | 他の 7 method、`backend*.py`、`http.py`、`_BACKEND_LAYER_ALLOWLIST`、`MitateDB-api/tests/test_audit_query.py`、`conformance-tests/`、r2db-api 全部、`docs/code-history/`、`docs/design/`、roadmap |

| # | 完了条件 | 変異 (`file:操作`) | 赤になる test id (予想) |
|---|---|---|---|
| 1 | 委譲の属性が leaf を指す | `cell.py`: `_normalize_value = staticmethod(_normalize_value)` の行を消す | `MitateDB-api/tests/test_foundation.py::test_request_binding_leaf_preserves_cell_delegates` (新規。3 属性が leaf の関数と `is`) |
| 2 | `object`/`array`/`json` の値は正規 JSON で保存する | `request_binding.py`: `("object", "array", "json")` を `("object", "array")` にする | `MitateDB-api/tests/test_foundation.py::test_request_binding_normalizes_values_literally` (新規。キー順の崩れた dict、`json` 宣言の str、`None`、未対応の型の details を literal で固定する) |
| 3 | 未対応の型は `request_schema` で拒否する | `request_binding.py`: `violation("request_schema")` を `violation("capability")` にする | 2 の新規テスト |
| 4 | 述語の値の拒否は値の path を持つ | `request_binding.py`: `details["field"] = value_path` を `details["field"] = "value"` にする | `MitateDB-api/tests/test_foundation.py::test_request_binding_predicate_value_denial_carries_value_path` (新規。integer 宣言に文字列の値で `where/0/value`) |
| 5 | 認可 → 検査: 値の検査は認可の後に走る (WF-3) | `cell.py` `read`: `self._require_data(principal, request_id=request_id)` (L2169) を `bound_filters = self._bind_filters(...)` の直後へ移す | `MitateDB-api/tests/test_foundation.py::test_predicate_value_check_runs_after_authorization` (新規。別の Application の principal と、integer 宣言の field に文字列の値の filter の組で `AuthorizationError`。同じ Application では `ValidationError`) |
| 6 | 移動先が `SCANNED_MODULES` に入る (40b) | L1 scan: `SCANNED_MODULES` から `request_binding.py` を外す | `MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py::test_every_module_with_a_vocabulary_denial_is_accounted_for` |
| 7 | 件数 pin (`cell.py` 42、`request_binding.py` 1) | `request_binding.py`: 4-key の `ValidationError` を raise する関数を 1 つ足す | `MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py::test_ast_full_count_matches_a_non_trivial_floor` |
| 8 | 移した denial が 4-key のまま | `request_binding.py`: `details=violation("request_schema"),` の行を消す | `MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py::test_every_choke_point_denial_carries_details_ast_full_count`、`::test_allowlist_entries_match_real_bare_call_sites` |
| 9 | sib tuple に移動先が入る | `request_binding.py`: `"unsupported value"` を `"storage backend rejected the request"` にする | `MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py::test_backend_layer_allowlist_entries_have_no_in_memory_sibling_denial` |
| 10 | leaf の import が許可リストの内だけ | `request_binding.py`: `import os` を 1 行足す | `tools/tests/test_leaf_import_direction.py::test_leaf_modules_import_only_their_allowlisted_modules` |
| 11 | 新 leaf が分類される | 一覧から `request_binding.py` の行を消す | `tools/tests/test_leaf_import_direction.py::test_every_src_module_is_classified` |
| 12 | 本体は列挙した差を除き同一 | **監査照合**: デコレータ・`cls` 引数・`cls._normalize_value` の 3 種を戻した leaf の本体が、移動前と AST で一致する。差の列挙をログに残す | — |
| 13 | 逐語移動と位置参照 (40c) | **監査照合**: docstring とコメントが逐語。括弧書きは L3628 の 1 箇所だけ | — |
| 14 | 登録 helper・同型・統合 | **監査照合**: `_ISOMORPHIC_TARGETS` の差分 0、WF-4、WF-6 | — |

【訂正註 2026-09-16 (WP-3i の実装、監督裁定 W3-23)。上の表は起草時の原文であり、消さずに残す (`OPERATING_CONDITIONS.md` §1.8 の 57)】

- 括弧書きの数。上の表が挙げるのは範囲内の 1 箇所 (L3628「this class's own defensive style」) で、範囲外は 0 である。実装では範囲外に W3-23 の 2 箇所 ((1) `MitateDB-api/tests/test_http.py`、(3) `MitateDB-api/tests/test_foundation.py`) を足した。括弧書きは計 3 箇所である。ほかに、leaf の module docstring (本 WP の新しい文) の事実の誤りを 3 つ直した (W3-23 (4))。完了条件 13 の「括弧書きは L3628 の 1 箇所だけ」は W3-23 と合わせて読む。
- 移動後の行番号 (`a48cfa1` に移動を適用して実測。leaf は手直し 1 の後): 範囲内の括弧書きは `request_binding.py` L61。範囲外は `test_http.py` L811 (L810 から折り返す文)・`test_foundation.py` L1458。変えない参照 (W3-23 (2)) は `cell.py` L3392-3393。manifest の行番号は `9994d7c` の実測である。`a48cfa1` で取り直すと、ずれは一様な -178 だけだった (例: 移動範囲 L3444-3462 → L3266-3284、L3607-3652 → L3429-3474、denial L3627 → L3449)。位置参照の行の「L3628」は、`9994d7c` では L3626 にある (引用の誤り)。文字列の一致で特定したので、編集には影響しない。
- 触るファイルに `MitateDB-api/tests/test_http.py` (W3-23 (1) の括弧書き 1 つだけ) を足す。`MitateDB-api/tests/test_foundation.py` は、新規テスト 4 本に加えて W3-23 (3) の括弧書き 1 つを含む。`test_l1_details_vocabulary_ast_scan.py` の sib tuple の docstring は変えていない (W3-23 (5))。
- 変異は計 12 である。表の 1〜11 の変異 (C1〜C11) に C8b を足す。C8b は C8 と同じ変異で、2 本目の予想 test `MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py::test_allowlist_entries_match_real_bare_call_sites` を単独で走らせる。

### 5.39 WP-3d〜3i の順序と未確定 (v1.11 追記)

- **順序**: 3d → 3e → 3f → 3g → 3h → 3i の直列。3d・3f・3g は `structured.py`・r2db の `test_foundation.py`・r2db の L1 scan を共有し、3e・3h・3i は `cell.py`・MitateDB の `test_foundation.py` を共有する。6 件とも L を触るので並行しない。3h は 3e の L167 の括弧書きを改めるので、3e の後に行う。
- **新規テストの数 (C-2)**: 3d 2、3e 3、3f 4、3g 3、3h 3、3i 4。
- **設計 §9.3**: 3e・3h・3i は `_gate`・`_limit_gate` とその呼出し経路を変えない。動かすのは変異の中だけである。
- **既知の穴** (移動前から存在し、範囲外。R-39 候補): r2db `structured.py` L224 の「`_mutate_outcome` below」と、L482 (登録 helper の中) の「`_ENUM_ELIGIBLE_TYPES` above」。MitateDB `cell.py` L195 の「The phrase construction below」、L4128 の `service.py:936-937`、L4152 の `:531`、`_surfaces_document_fragment` の「immediately above」、L2465 の「module-level "PG 留意" note above `_DELETE_CONSEQUENCE`」(その note は無い)。r2db `structured.py` L328 の「`service.py`'s `schema_ops`/`unsupported` literals」(WP-3b 以降古い)、L459 の「never surfaced outside this module」(`postgres.py` も捕まえる)、L484 (登録 helper の中) の「this module's own internal vocabulary」。conformance と tests に残る `structured.py:NNNN`・`cell.py:NNNN` の古い行番号 (#25 と同種)。

**未確定 (監督判断待ち)**:

| # | 点 |
|---|---|
| W3-6 | leaf 名。`storage_outcomes.py` (3d)、`request_vocabulary.py` (3e)、`capabilities_document.py` の `build_capabilities_document` (3h)。3h は r2db と同じ名前になるが、同名であることは同型登録の根拠にしない (設計 §3.1)。`mutation_binding.py`・`schema_binding.py`・`request_binding.py` は §2.1・§2.2 のとおり |
| W3-7 | 3f の D-1 見出しコメント (L104-133)。「Everything below this point is the boundary」は、ST8・ST9 の全体と両 cell を覆う文である。(a) leaf へ移し、below の直後に `schema_binding.py` と `structured.py` の `bind_schema_operation` を指す括弧書きを補う。(b) facade に残し、`validate_projection` 以下が移ったことを括弧書きで補う。どちらにするか |
| W3-8 | 3f で `_NON_AUDIT_OPERATION_PARAMETERS` の 1 要素を改名する。40b の固定表と同じく同じ変更セットで行うか、除外集合の変更として監督の裁定を要するか |
| W3-9 | ST9 の `bind_schema_operation` の本体。登録 helper を呼ぶので、枠の中では循環を避けて移せない。移すには、validator を引数で渡す (設計にない) か、helper を移す (Class D) かが要る。3g の範囲に限る (本案) か、ST9 全体を保留するか |
| W3-10 | 3h の leaf は、`Role` のために `.auth` (設計 §3.2 の認証境界の module) を import する。許可リストに入れるか。入れない場合は比較式を変えることになり、名前の置換を超える |
| W3-11 | CE6 の 7 method は backend の catalog を読む (設計 §3.1・§7)。3i を 3 method に限る (本案) か、backend を引数で渡す案を設計変更として扱うか |
| W3-12 | 3i の本体の差 (デコレータと `cls` 引数を削り、`cls._normalize_value` を置換する) を、W3-3 の例外と同じく認めるか |
| W3-13 | ST10 には動かせる呼出しが無い。WF-3 の変異を、`replayed` の既定値の変異 (実行 → 監査、3d の 4) で代えてよいか |

**監督裁定 (2026-09-15)**:

| # | 裁定 |
|---|---|
| W3-6 | 本案の名前で行う。3h が r2db と同名になることは、同型登録の根拠にしない |
| W3-7 | (b)。見出しコメントは facade に残し、`validate_projection` 以下が `mutation_binding.py` に移ったことを括弧書きで補う。コメントが覆う cell は facade に残るため |
| W3-8 | 3f と同じ変更セットで改名する。移動に伴う改名であり、除外集合の意味は変えない |
| W3-9 | 本案。3g は 10 名に限る。`bind_schema_operation` の本体は facade に残す (validator の引数化も helper の移動もしない) |
| W3-10 | leaf は `.auth` を import しない。WP-3b (`capabilities_document.py` の import は `typing` だけ) と同じく、facade が `Role` に依存する値を計算し、既定値の無い引数で渡す。本体の差は W3-3 と同じく差分の列挙で示す |
| W3-11 | 本案。3i は 3 method に限る。backend を引数で渡す案は採らない |
| W3-12 | 認める。W3-3 と同じく、差分を列挙してログに残す |
| W3-13 | 認める |
| W3-14 | 3d の完了条件 1 の変異 (`structured.py` の import から `SchemaOutcome` を外す) は、`backend.py` も同じ名前を import するので収集時の ImportError (exit 2) になり、条件 1 だけを壊さない。`storage_outcomes` の import の直後で `SchemaOutcome` を別の class で上書きする変異に置き換える (実装時の監督裁定、2026-09-15)。以後の WP でも、facade の名前を消す変異が他 module の import を壊す場合は、同じく上書きの変異を使う |
| W3-15 | `cell.py` の `add_field` の docstring (L1326 付近) の「see the module-level comment above `_DELETE_CONSEQUENCE`」(名前が行をまたいで折り返す) は、manifest (§5.34) が漏らした範囲外の位置参照である。L2409-2410 の項と同じ括弧書き「(now in `request_vocabulary.py`)」を付ける。この塊に CH-ID は無い。実装者が見つけた (実装時の監督裁定、2026-09-15) |
| W3-16 | manifest (§5.34) が漏らした範囲外の位置参照が `MitateDB-api/src/mitatedb_api/http.py` にさらに 2 つあり、どちらも CH-ID が付く: L821 (CH-0221)「(`_TRANSACT_INSERT_KEYS`/`_TRANSACT_UPDATE_KEYS`/`_TRANSACT_DELETE_KEYS` in `cell.py`)」と L993 (CH-0228)「`cell.py`'s own `_TRANSACT_INSERT_KEYS` already applies to `transact()`」。それぞれに括弧書き「(now in `request_vocabulary.py`)」を付け、`docs/code-history/MitateDB-api/http.md` に §5.27 の形式の訂正の記録を書く (WF-5 (iv))。このため `http.py` と `docs/code-history/MitateDB-api/http.md` は §5.34 の「触らないファイル」から外れる。独立 Opus レビューが見つけた (実装時の監督裁定、2026-09-15) |
| W3-17 | manifest (§5.35) が漏らした範囲外の位置参照が 8 つある。独立 Opus レビューが見つけた。いずれも `mutation_binding.py` へ移った名前を指すことを確かめ、括弧書き「(now in `mutation_binding.py`)」を付ける: `r2db-api/src/r2db_api/structured.py` L442「`bind_mutation`'s identical check above」、`r2db-api/src/r2db_api/capabilities_document.py` L56「bind_mutation/_apply_upsert」、`r2db-api/src/r2db_api/control_plane.py` L760「(structured.py)」(CH-0266)・L910「(structured.py)」(CH-0272)・L1012「e.g. `bind_mutation`'s」・L1029「`validate_projection`'s」(L1012・L1029 は §5.35 が名前だけとしたものを分類し直す)、`r2db-api/conformance/conformance_adapter_r2db.py` L1395-1396・L1409-1410 (`_MUTATION_KEYS` / `bind_mutation`)。CH-0266・CH-0272 には `docs/code-history/r2db-api/control_plane.md` に §5.27 の形式の訂正の記録を書く。`r2db-api/tests/test_foundation.py` L549-550 の「structured.py:229」は `b4aac70` の時点ですでに古く、既知の穴のまま残す (R-39 と同種) (実装時の監督裁定、2026-09-15) |
| W3-18 | `tools/tests/test_comment_provenance.py::test_q4_real_repo_postgres_unchanged_is_green` を退役させる。このテストは固定の基点 `5d12799` で `run_base` を走らせ、作業ツリーの `r2db-api/src/r2db_api/postgres.py` と比べていた。基点ですでに CH-ID を持つ塊に正当な位置の括弧書きを足すと、チェッカーの再編集の枝 (`tools/check_comment_provenance.py` の L2246〜L2275 付近) を通る。この枝は古い基点からは決して導けないので、CH-0057 に括弧書きが付くとテストは赤になる (再現: `FAIL (§4.1 (2)) r2db-api/src/r2db_api/postgres.py:1895 basis block for CH-0057 is not derivable ...`)。覆いは `test_0f_both_peers_all_src_rev_vs_itself_is_green` (HEAD の全 CH の塊) と CH-0028 の pin が保つ。採らない案: 基点の貼り直し (それより前の SHA はすべて赤で、コミットは自分の SHA を名指せない)、チェッカーの変更 (同じチェッカーを書き換える R-22 変更セット 0i と衝突する)、括弧書きの移動・省略 (赤になるか、WF-5 (i) に反する)。あわせて: CH-0057 の訂正の記録は、当初 `M-1: ` のラベルの除去を記録の無い除去として織り込んでいた。その除去は変更セット 1 自身の操作 (6) で、すでに導ける。記録は括弧書きだけを足す形に書き直した (レビュー M2) (実装時の監督裁定、2026-09-15) |
| W3-19 | manifest (§5.36) が漏らした範囲外の位置参照である。実装者の手順 0 の走査が、分類の無いこの参照で止まった: `MitateDB-api/src/mitatedb_api/provisional_gate.py` L29「`structured.py`'s own `SCHEMA_OPERATIONS` constant」。`SCHEMA_OPERATIONS` は `schema_binding.py` へ移り、facade から再 export しないので、`SCHEMA_OPERATIONS` の直後に括弧書き「(now in `schema_binding.py`)」を付ける。この塊に CH-ID は無く、訂正の記録は書かない。このため `provisional_gate.py` は、この括弧書き 1 つに限り §5.36 の「触らないファイル」(MitateDB-api 全部) から外れる (実装時の監督裁定、2026-09-15) |
| W3-20 | manifest (§5.36) が漏らした範囲外の位置参照がもう 1 つある。独立 Opus レビューが見つけた: `r2db-api/conformance/conformance_adapter_r2db.py` L1214-1215「`structured.py`'s own pre-1.6.0 `_SCHEMA_KEYS`/`bind_schema_operation`」。括弧書き「(now in `schema_binding.py`)」は `_SCHEMA_KEYS` の直後に付ける。`bind_schema_operation` は facade に残る (W3-9) ので、その直後には付けない。前例: WP-3e は MitateDB 側の同じ文「`cell.py`'s own pre-1.6.0 `_FIELD_TYPE_VOCABULARY`」に括弧書きを付けた。WF-5 (ii) が除くのは修飾名 `module.NAME` の形だけで、「`X.py`'s」の形は除かない。CH-ID は無く、訂正の記録は書かない。adapter を触るファイルに足す。あわせて変異を改める (レビュー m1・m2): C1 は W3-14 の上書きの形 (`.schema_binding` の import の塊の後で `ConstraintPatch = type("ConstraintPatch", (), {})`) にする。`r2db-api/src/r2db_api/postgres.py` L113 が `.structured` から `ConstraintPatch` を import するので、外す形は使えない。C6 は、移した site 自身の 4-key の `details` で `fail` を呼ぶ孤立した probe にする。当初の `details={"field": "x"}` の probe は、隣の L1 のテスト 2 本も赤にしていた。改めた後に赤になるのは `test_ast_full_count_matches_the_audit_site_count` だけである (`{'schema_binding.py': 2} != {'schema_binding.py': 1}`) (実装時の監督裁定、2026-09-16) |
| W3-21 | manifest (§5.37) が分類していない範囲外の参照が 2 つある。実装者の手順 0 の走査が、この 2 つで止まった。(1) `MitateDB-api/src/mitatedb_api/cell.py` L521「`ApplicationRuntime.__build_capabilities_document` (this same module, a different class) reads it via `self.__cell.process_ceiling`」は変えない。`cell.py` に残る facade の method は、なお `self.__cell.process_ceiling` を読んで leaf へ渡す (W3-10)。文は字義どおり成り立つので、確かめたものとして記録する。(2) `MitateDB-api/src/mitatedb_api/platform_declarations.py` L772「this peer's own `__build_capabilities_document` (`cell.py`) already normalizes」には、manifest の L858・L870 と同じ括弧書き「(body now in `capabilities_document.py`)」を付ける。L772・L858・L870 の塊に CH-ID は無く、訂正の記録は書かない (実装時の監督裁定、2026-09-16) |
| W3-22 | manifest (§5.37) と W3-21 が漏らした参照がある。独立 Opus レビューが見つけた。R1: `cell.py` L3652「flip to `enabled` below」を「below (now in `capabilities_document.py`)」にする。R2: `MitateDB-api/src/mitatedb_api/http.py` L601 (CH-0208) の「`limit_enforcement.operation_depth` comment」の直後に「(now in `capabilities_document.py`)」を付ける。あわせて `docs/code-history/MitateDB-api/http.md` §CH-0208 に訂正の記録を書く。WP-3h で CH-ID の塊の中を編集するのはこれが初めてである。R3・R4: `conformance-tests/test_c05_limit_declaration_agreement.py` L932・L1203 の `cell.py:1875-1926` の直後に「(now in `capabilities_document.py`)」を付ける。行番号はすでに古い (既知の穴) ので、そのまま残す。R5: leaf `capabilities_document.py` L301 の `(:770)` と L303 の `(:832)` に、L292 の `(:531)` と同じく「(in `cell.py`)」を付ける。値は古い (既知の穴)。n2: `capabilities()` の `__authorize` と `_limit_gate` を入れ替える変異が緑のままだった。テスト 3 (`test_capabilities_document_is_built_after_authorization_inside_the_limit_gate`) に場面を足す。同じ credential で `rpm=1` を使い切り、revoke して、もう一度呼ぶ。認可が先なら `AuthenticationError`、入れ替えると `ResourceLimitError` になる。これで入替えの変異は赤になる。n3: C2 の 2 本目の予想 test `test_ceiling_two_maps_data_plane_in_memory_classes_to_deployment_required` を C2 の下で単独で走らせ、赤を観測した。このため `http.py`、`docs/code-history/MitateDB-api/http.md`、`test_c05` (コメントだけ) は §5.37 の「触らないファイル」から外れる。n1: 「`cell.py`'s own declaration」の形の残りの参照は、`cell.py` に残る `capabilities()` を指す。確かめたものとして記録し、括弧書きは付けない (WP-3b の前例、§5.29)。該当は `http.py` L599・L759・L900・L1199、`MitateDB-api/src/mitatedb_api/ops.py` L13・L1256、`MitateDB-api/src/mitatedb_api/control_main.py` L76、`conformance-tests/test_c14_authority_boundary.py` L182、`conformance-tests/test_c25_result_request_id.py` L61-62、`cell.py` L11・L3317 (実装時の監督裁定、2026-09-16) |
| W3-23 | manifest (§5.38) が分類していない参照が 2 つある。実装者の手順 0 の走査はこの 2 つを見つけたが、止まらずに自分で判定して進めた。独立 Opus レビューは、2 つの判定のうち 1 つを誤りとした。分類の無い参照では必ず止まる。この逸脱は前例にしない。(1) `MitateDB-api/tests/test_http.py` L810-811「`cell.py::_normalize_value_for_storage`」は、本体が行う NUL の escape を述べる。名前の直後に括弧書き「(body now in `request_binding.py`)」を付ける (W3-21 (2) の形)。CH-ID は無い。(2) `MitateDB-api/src/mitatedb_api/cell.py` L3392-3393「`_check_predicate_value`'s own path immediately above」は変えない。指す先は `_bind_filters` の中の呼出し箇所で、`cell.py` に残る。確かめたものとして記録する。(3) `MitateDB-api/tests/test_foundation.py` L1458 の `cell.py:587` は、`a48cfa1` では正しかった。`cell.py` に足した import の行で、指す先が L588 にずれる。書き換えず、括弧書き「(now `:588`)」を足す (40c)。(4) `request_binding.py` の module docstring は本 WP の新しい文なので、事実の誤りを直す。「total」(`_normalize_value` は raise する)、「`cls.` の呼出し箇所」(もう残っていない)、「its own module」(→ `cell.py`)。(5) `MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py` の sib tuple の docstring は例を挙げるだけなので、変えない。あわせて: C2 の巻き添え (既存の json の往復テスト 5 本が赤) は canonicalization の性質から避けられないので認める。条件 2 は、専用の新規テストが単独で固定する。C1 の巻き添えも認める。実装者は、C2 ほかの変異を `mutate.py` の外で当てて full suite を補助的に走らせた。レビューは、変異が残っていないことを静的に確かめた。13 の spec のすべてで `old` はちょうど 1 回あり、`new` は無い。canonicalization の tuple は `a48cfa1` と同じで、sha256 は変異前の backup と一致する。この補助実行の巻き添えの件数には、保存したログが無い (実装時の監督裁定、2026-09-16) |


### 5.40 WP-4 の実測と共通 (v1.17 追記、**独立レビュー反映済み**)

**対象と順序**: §4 の WP-4 行のうち、PG1・PG2・PG3 と BP3 を、1 抽出 = 1 WP の直列で行う。BP3 → PG1 → PG3 → PG2 (+ `_bind_value`) を WP-4a → 4b → 4c → 4d とする (Z4-2)。PG4 は範囲外である (Z4-1。根拠は §5.45)。

**実測**: 基準コミット `ba98255`。行番号は `ed265f4` での実測であり、`git diff --name-only ed265f4..ba98255` が両 peer の `src/` と `tests/` に 1 件も触れていないことを監督が照合済みである。`r2db-api/src/r2db_api/postgres.py` は 2545 行、`MitateDB-api/src/mitatedb_api/backend_postgres.py` は 1860 行。行範囲は top-level の定義と class member の `lineno`/`end_lineno` (デコレータを含む) で測った。denial は各 peer の L1 scan の `_fail_call_sites` をそのまま import して範囲ごとに数えた。どれも読み取りだけである。**各 WP の行番号は、前の WP の統合後に取り直す** (§5.32 と同じ)。

**監督裁定 (Z4-1〜Z4-8。各 WP はこれを前提に読む。逐語)**:

| # | 裁定 |
|---|---|
| Z4-1 | **PG4 は WP-4 の範囲外とし、`apply_schema` には触らない。** 設計 §2.3 の「未確定」はこの実測で閉じる |
| Z4-2 | **4 件の直列 WP に分ける。** 4a = BP3 (MitateDB)、4b = PG1、4c = PG3、4d = PG2 + `_bind_value` |
| Z4-3 | **PG2 は `_bind_value` (L1525-1535) を同じ変更セットで leaf へ移し、class には WP-3i と同じ委譲属性を残す。** 代案 (validator を引数で渡す) は採らない |
| Z4-4 | **CH-ID を持つ塊のファイルまたぎ移動: 登録簿の節は動かさない。`--base <親>` は来歴の証拠に使わない。証拠は使い捨て clone の、コミットした HEAD での `tools/tests` 0f とする** |
| Z4-5 | **`_BACKEND_LAYER_ALLOWLIST` の `("postgres.py", 1523)` は移動範囲外だが行番号が動く。同じ変更セットで実測値へ更新し、既存の前例と同じ形の行送りコメントを足す** |
| Z4-6 | **件数 pin は非対称である。移動元 `postgres.py` には減算コメントを書かない。移動先の新 leaf は前例どおり件数 pin の辞書に足す** |
| Z4-7 | **4 件は直列。並行しない** |
| Z4-8 | **leaf 名**: 4a = `MitateDB-api/src/mitatedb_api/postgres_sql.py` (新規)、4b = 既存 `r2db-api/src/r2db_api/postgres_types.py` へ追加、4c・4d = `r2db-api/src/r2db_api/postgres_sql.py` (新規) |

- Z4-8 の根拠のうち、**同名であることを同型登録の根拠にしない** (設計 §3.1 末尾、W3-6 の前例)。`postgres_predicates.py` (§2.3 の提案名) は PG3 の `_select_statement`/`_order_by_sql` を覆わないので採らない。
- Z4-1 の根拠は `r2db-api/src/r2db_api/postgres.py` L1907-2275 の通読である。`sql.SQL(...).format(...)` はいずれも 1〜2 行後に同じ `with conn.cursor()` の中で `_run()` され、`LOCK TABLE {table} IN SHARE ROW EXCLUSIVE MODE` (L2094・L2159) と同じ分岐に地続きで、組立だけのまとまりは無い。設計 §3.2 と §3 は `apply_schema` を副作用境界として既に除外している。
- Z4-3 の根拠は `_predicate_sql` の L1878・L1903 が `self._bind_value` を呼び、`_bind_value` 自身は `self` を使わない純粋 method である実測と、他の 6 呼出し箇所 (L1655・L1681・L1752・L1783・L1806・L2177) が委譲属性のまま動く実測である。

**§5.32 の枠 (WF-1〜WF-7) の掛かり方**:

| # | WP-4 での扱い |
|---|---|
| WF-1 | そのまま掛かる。`_ISOMORPHIC_TARGETS` に PG1〜PG4・BP3 のいずれの名前も無い (grep 実測)。各 WP の完了条件に「差分 0」を置く |
| WF-2 | そのまま掛かる。connection / cursor 所有権、transaction、advisory / table lock、`SET LOCAL` timeout、driver exception mapping、`_run` は facade に残す (設計 §3.2、§3) |
| WF-3 | WP-4 の移動範囲には認可・rate・slot・audit の呼出しが 1 件も無く、順序を壊す変異を置けない。代わりに**設計 §5.2 の「SQL 安全性」の変異 (identifier object / placeholder を raw text に置換する) を各 WP に 1 つ以上置く** (D-4)。**W3-13 と同じ扱いである** (「ST10 には動かせる呼出しが無い。WF-3 の変異を、`replayed` の既定値の変異で代えてよいか」→「認める」)。第 2 次裁定 7 |
| WF-4 | そのまま掛かる。4a は MitateDB 片側、4b〜4d は r2db 片側。同型登録はしない |
| WF-5 | 位置参照の分類は (i)〜(iv) をそのまま使う。各 WP の実測表の「位置参照」欄はこの分類の結果である |
| WF-6 | そのまま掛かる。src の行数が変わるので、root ゲートを通してから統合し、コミット後の HEAD で `tools/tests` を流す |
| WF-7 | そのまま掛かる。設計にない検査や機構は足さない。枠の中で行えない部分は §5.45 の未確定に置く |

- **共通の規律**: §5.5 の規律 1〜5 に従い、各表の末尾に C-1〜C-3 を付ける。C-2 の新規件数は §5.45 の数である。
- **第 2 次の監督裁定 (W4-1〜W4-3 と項目 4〜8、2026-09-16)** は §5.45 にある。各 WP はこれも前提に読む。

**位置参照の走査 (手順 0。全 WP の完了条件)**:

WP-3e〜3i の manifest はいずれも範囲外の位置参照を取りこぼし、独立レビューだけが順に 3・8・1・5・2 件を見つけた (引き継ぎ書 `docs/work-orders/HANDOVER_20260916_FABLE.md` §6)。各 WP の実装担当は、**手順 0 として、移動する名前を repo 全体 (両 peer の `src/`・`tests/`、`conformance-tests/`、`tools/`、`docs/code-history/`) で走査し、各 manifest の「位置参照」欄の分類と突き合わせる。分類の無い参照が 1 件でもあれば、そこで止まって監督へ上げる。** W3-23 の逸脱 (実装担当が 2 件を見つけたが止まらず自分で判定し、独立レビューが 1 件を誤りとした) は前例にしない。走査の実行コマンドと出力 (件数と `file:line` の一覧) を報告に貼り、設計 §10 の実施記録に残す。

**CH-ID のファイルまたぎ移動 (Z4-4)**:

- 移動範囲に CH-ID を持つ塊が含まれる WP (4b・4c・4d。件数は各 manifest) では、`# history: CH-NNNN` / `History: CH-NNNN` の行も逐語で一緒に移す。
- 受け皿 `docs/code-history/<peer>/<module>.md` の**節は動かさない** (`docs/design/CODE_COMMENT_PROVENANCE_V1.md`:53 が「`<module>` は移動時点のファイル名である。後の R-37 抽出で symbol が移っても節は動かさない」と定める)。移動先の新 module 名の受け皿ファイルは作らない。
- **来歴の証拠に `--base <親>` を使わない。** 移動元では「basis block の CH-ID がどの新しい塊とも対応しない」の無条件 FAIL、移動先では `git show` 不能の判定不能になる。証拠は、使い捨て clone で変更をコミットし、その HEAD で `tools/tests` の 0f (`test_0f_both_peers_all_src_rev_vs_itself_is_green`) を流したものとする (引き継ぎ書 `docs/work-orders/HANDOVER_20260916_FABLE.md`:50、設計 §10.11 の訂正と同じ取り方)。0f の走査は両 peer の `src/<pkg>/*.py` を glob するので、新しい module は自動で対象に入る。
- WF-5 (iv) に当たる箇所 (CH-ID の塊の中の位置参照に括弧書きを足す場合) は、同じ変更で受け皿の該当 CH-ID 節に §5.27 の形式の訂正の記録を書く。

**件数 pin の非対称 (Z4-6)**: r2db の `test_ast_full_count_matches_the_audit_site_count` の `counts` 辞書 (`r2db-api/tests/test_l1_details_vocabulary_ast_scan.py` L366 付近) は 11 module で、`postgres.py` を含まない。一方 `SCANNED_MODULES` (同 L84) は `postgres.py` を含む。したがって WP-4d が移す 2 件の 4-key denial は、**移動元では pin が動かず (減算コメントも書かない)、移動先の新 leaf でだけ pin が増える**。WP-3 までの「−N / +N の対」にならない。MitateDB 側の `test_ast_full_count_matches_a_non_trivial_floor` は `SCANNED_MODULES` 全件を辞書で pin するが、WP-4a は denial を 1 件も動かさないので差分 0 である。

**allowlist の行送り (Z4-5)**: `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py` L125 の `("postgres.py", 1523)` (`_fail_client_value`) は移動範囲外だが、4b (L205-226・L250-276)、4c (L1280-1312)、4d (L240-247) はいずれも L1523 より上を削るので行番号が動く。**3 WP のそれぞれで実測値へ更新し、同ファイルの既存コメント (「R-37 WP-1 leaf extraction (2026-09-14): line shift only (1752 -> 1706)」、同 L121-124) と同じ形の行送りコメントを足す。** 4a は MitateDB 側の `_BACKEND_LAYER_ALLOWLIST` 20 件すべてが動くので、同じく実測で取り直し、同ファイルの既存コメント (「R-37 WP-1n (2026-09-15): … every entry below shifted UP by 118 lines (485 -> 367, …)」) と同じ形の行送りコメントを足す。**いずれも 40b のとおり、件数 pin・行番号を実測値へ合わせるだけで済ませず、移動先が走査対象に入ったことを確認する。**

**leaf の分類 (U-5 / M2)**: 4 件とも同じ変更セットで `tools/tests/test_leaf_import_direction.py` を更新する。4a・4c は `LEAF_MODULE_ENTRIES` に新 leaf 1 行を足す。4b は既存 `("postgres_types.py", frozenset({"psycopg"}))` の許可集合を実測で広げる。4d は 4c が足した行の許可集合を広げる。leaf を足しても `tools/tests` の node id は増えない (§5 の監督裁定 minor 1)。

**`pytest -q tools/tests` (m5)**: root ゲートは `tools/tests` を収集しない。4 件とも検証とゲートに `tools/tests` を入れる。

**R-44 (別セッション) との関係**:

- ファイル単位の重なりは 0 の見込みである。`tools/tests/` は同じディレクトリだが別ファイル (`test_leaf_import_direction.py`・`test_comment_provenance.py` ⇔ `test_testpg.py`・`test_dev_tools.py`) で、§1.2 の 17 の「ファイル名の系統を分ける」を満たす。
- **確定した重なり**: R-44 WP-3 が両 peer の `tests/test_postgres.py` を触る。WP-4a は同ファイルの位置参照 1 件 (後述) で触る見込みがあるので**重なる**。相手は WP-3 の着手前にこちらの状況を確認しに来ると確約済みである。R-44 WP-2 (道具だけ) の間は重ならない。新規テストは `tests/test_foundation.py` に置き、`tests/test_postgres.py` への書き込みを位置参照の括弧書き 1 件だけに抑える。
- **集計行**: 双方が新規テストを足すので、`COLLECTION_FLOOR` とゲートの集計行は統合順に依存する。「直前の main + 自分の新規テスト数」で照合できないので、**統合の直前に main を取り込んでから期待値を出す**。
- **道具の引数**: R-44 WP-2 が `tools/dev/_devlib.py` の `ps` 検出と `--hold` / `GATE_HOLD_FLAG` を廃止する (互換は残さない)。**道具の引数は統合時点の仕様に従い、固定の手順を焼き込まない。** 発注中の subagent が古い引数を持っていたら、統合の連絡を受けた時点で直す。

**baseline (導出)**: root `3417 passed, 2 subtests passed`、`tools/tests` 453 (R-44 WP-1 の統合後、`ba98255`)。R-44 WP-2 でさらに増える。着手時に collect-only で確かめる。

**静的な pin の実測**:

| pin | r2db (4b・4c・4d) | MitateDB (4a) |
|---|---|---|
| `SCANNED_MODULES` | `postgres.py` を含む 15 module (L84)。4b・4c の新 leaf は denial 0 なので足さない。4d で `postgres_sql.py` を足す | `backend_postgres.py` を含む 15 module (L109-112)。4a の新 leaf は denial 0 なので足さない |
| 件数 pin | `counts` 辞書は 11 module で `postgres.py` を含まない (Z4-6)。4d で `postgres_sql.py`: 2 を足す | `counts` は `SCANNED_MODULES` 全件。`backend_postgres.py` は 21 のまま (差分 0) |
| 行番号 allowlist | `("postgres.py", 1523)` の 1 件。4b・4c・4d で行送り (Z4-5)。`test_backend_layer_allowlist_is_confined_to_postgres_py` の前提は変わらない | `backend_postgres.py` の 20 件。4a で全件が行送り。`test_backend_layer_allowlist_is_confined_to_backend_modules` の前提は変わらない |
| sib の固定 module 集合 | in-memory 側 (`structured.py` と抽出 leaf 7 件) の集合であり、backend 層の `postgres_sql.py` は入れない。4b〜4d とも差分 0 | `_BACKEND_LAYER_ALLOWLIST` の module 集合 (`backend_postgres.py`・`backend_sqlite.py`) だけを見る。4a は差分 0 |
| `_ISOMORPHIC_TARGETS` | PG1〜PG4 のいずれの名前も無し (grep 実測)。差分 0 | BP3 の 3 名とも無し (grep 実測)。差分 0 |
| getsource / 文字列の数え上げ | `test_threadpool_offload.py` は `DataService._slot`・`_acquire_rate` だけ。移動範囲に無い | 移動範囲に無い |
| L (`tools/tests/test_leaf_import_direction.py`) | 4b は既存 1 行の許可集合、4c は新 leaf 1 行、4d はその許可集合 | 4a は新 leaf 1 行 |

**実行するコマンド** (`WT` は監督が割り当てる worktree、`SP` は scratchpad。変異の spec は完了条件表の変異 1 行につき 1 件、`expect: red`。HEAD を読む来歴の変異だけは使い捨ての clone で行う):

```bash
tools/dev/pt.py -C "$WT" -- r2db-api/tests -q
tools/dev/pt.py -C "$WT" -- MitateDB-api/tests -q
tools/dev/pt.py -C "$WT" -- conformance-tests -q
tools/dev/pt.py -C "$WT" -- tools/tests -q
tools/dev/mutate.py "$SP/wp4a-mutations.json" -C "$WT"   # WP ごとに wp4b … wp4d
tools/dev/gate.py --label wp4a                            # 監督。run_in_background
```

R-44 WP-2 の統合後は同じ道具の `--wait` の形になる (`tools/dev/pt.py --wait 1800 -C "$WT" -- <pytest args>`、`tools/dev/mutate.py "$SP/wp4a-mutations.json" -C "$WT" --wait 1800`)。**引数は統合時点の仕様に従う。**

### 5.41 WP-4a — MitateDB の SQL 述語の組立 (BP3、**独立レビュー反映済み**)

**目的**: `_OPERATOR_SQL`・`_DIRECTION_SQL` と `PostgresBackend._where_sql` を leaf `MitateDB-api/src/mitatedb_api/postgres_sql.py` (新規、Z4-8) の module 定数と関数へ移す (D-4。method → 関数)。class には WP-3i と同じ委譲属性を残し、5 箇所の呼出しの形 (`self._where_sql(filters)`。`update_in_transaction`・`delete_in_transaction`・`read`・`update`・`delete`。`insert` は `_where_sql` を呼ばない — C-5) と、`read()` の中の ORDER BY / LIMIT の組立・`_execute`・timeout・driver 例外の変換はいずれも `backend_postgres.py` に残す。**WP-4 の最初の WP であり、着手条件は R-44 との調整 (§5.40) だけである。**

| 項目 | 実測 (`ed265f4`。着手時に取り直す) |
|---|---|
| 移動範囲 (3 名、2 塊、計 20 行) | L130-134 (m-7 の説明コメント 3 行と `_OPERATOR_SQL`・`_DIRECTION_SQL` の 2 行。規律 2 のとおり直前の説明コメントを含む)、L1152-1166 (`_where_sql`、15 行) |
| 飛び石 | 間の L135-1151 は動かさない。L1149-1151 の区切りコメント (`# ---- / # DML (runtime connection only -- R-1) / # ----`) は、後続の `insert`/`update`/`delete`/`read` を覆うので facade に残し、その直後に委譲属性を置く |
| 本体の変更 | `def _where_sql(self, filters):` → `def _where_sql(filters):` の 1 種だけ。本体は `self.` を 1 度も参照しない (実測)。定数は 1 文字も変えない |
| class (facade) に残すもの | `_where_sql = staticmethod(_where_sql)` の 1 行 (WP-3i の形)。呼出し元 L1281 (`update_in_transaction`)・L1311 (`delete_in_transaction`)・L1333 (`read`)・L1404 (`update`)・L1429 (`delete`) はそのまま `self._where_sql(...)` で動く。module 先頭では `_OPERATOR_SQL`・`_DIRECTION_SQL` を leaf から import する (§2.5 の「2 名 + 委譲 method」)。`_DIRECTION_SQL` は `read()` の L1354 が読み続ける。**`_OPERATOR_SQL` は条件付きである (第 2 次裁定 6)**: 実装担当が移動後の読み手 0 を実測で示したら import を削り (WP-3h の読み手 0 の import 削除が前例)、根拠 (読み手 0 の実測) と回帰証拠 (suite の集計行) を WP 記録に添える。読み手が 1 件でもあれば §2.5 の「2 名 + 委譲 method」のとおり再 export として残す。どちらの道筋でも完了条件 1 の facade テストは `_DIRECTION_SQL` と委譲属性を固定し、削った場合は `_OPERATOR_SQL` を leaf 側だけで固定する |
| leaf の import | `psycopg` (`from psycopg import sql`)、`.backend` (`SQL_OPERATOR_TOKENS`)。`MitateDB-api/src/mitatedb_api/backend.py` は module-level の import を 1 つも持たない (実測) ので循環 import にならない。許可集合は `{"psycopg", ".backend"}` |
| denial・件数 pin | 移動範囲の denial は 0 件。`backend_postgres.py` の件数 pin は 21 のまま差分 0。新 leaf は denial 0 なので件数 pin の辞書に足さない。`read()` の中の「invalid order direction」の 4-key denial (L1370、`raise ValidationError(` の行。C-5〜C-6) は移動しない |
| `SCANNED_MODULES`・sib tuple | どちらも差分 0 (新 leaf は denial 0)。40b の確認は `test_every_module_with_a_vocabulary_denial_is_accounted_for` が新 leaf を拾うこと (完了条件 9 の変異で示す) |
| 行番号 allowlist (Z4-5) | `MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py` L243-262 の `backend_postgres.py` 20 件がすべて行送りする (L133-134 の削除は全件に、L1152-1166 の削除は L1214 以降の 9 件にさらに掛かる)。実測で取り直し、行送りコメントを足す。件数と site の同一性 (20 件) は変わらない |
| CH-ID (Z4-4) | 移動範囲に CH-ID は 0 件 (`backend_postgres.py` の 6 件 CH-0525/0526/0528/0529/0530/0537 はいずれも範囲外)。**ただし範囲外の CH-0340 に括弧書きを足すので、0f の証拠は他の WP と同じく使い捨て clone の HEAD で取る** |
| 位置参照 (WF-5) | **付ける**: `MitateDB-api/src/mitatedb_api/backend_sqlite.py` L45 の「mirroring `backend_postgres.py`'s own `_DIRECTION_SQL` constant dict」の `_DIRECTION_SQL` の直後に「(now in `postgres_sql.py`)」(WF-5 (i)。「`X.py`'s」の形は (ii) の除外に当たらない — W3-20 の前例)。**この塊は CH-0340 を持つ**ので、同じ変更で `docs/code-history/MitateDB-api/backend_sqlite.md` §CH-0340 に §5.27 の形式の訂正の記録を書く (WF-5 (iv)、W3-22 の R2 と W3-16 の前例。第 2 次裁定 5)。`MitateDB-api/tests/test_postgres.py` L1418 の「`PostgresBackend.read()`'s own `_DIRECTION_SQL` closed dict」の `_DIRECTION_SQL` の直後にも同じ括弧書きを足す (CH-ID は無い)。**付けない**: `MitateDB-api/tests/test_order_by_direction_hardening.py` L5 の `_DIRECTION_SQL` (名前だけ。§5.38 の前例)。`backend_sqlite.py` の同名 method `_where_sql` (L541、別 class の別実装で、この WP では触らない) と、それを呼ぶ L520・L533・L557・L586・L599。`docs/code-history/MitateDB-api/backend_postgres.md` の登録簿の節 (Z4-4)。`docs/work-orders/WORK_ORDER_CODE_COMMENT_PROVENANCE_CS1.md` L1953・L2033・L2469 の表と註 (過去の作業指示書。§1.8 の 57 により本文を書き換えない。A-2 (1)(2)(3))。`docs/code-history/MitateDB-api/backend_sqlite.md` §CH-0340 の**逐語写しの本文** (設計 `CODE_COMMENT_PROVENANCE_V1.md` D-1 の「各節は移動変更セットの親コミット時点の写しである。後のコード変更に合わせて書き換えない」。4a が同ファイルに足すのは訂正の記録だけで、写しは 1 文字も変えない。A-2 (4))。`security/CONTROL_MAPPING.md` L538 と `MitateDB-api/README.md` L223 の `backend_postgres.py:1658-1661` (移動前から既に古い。**WP-4 では触らない** — §5.45 の既知の穴。A-2 (5))。手順 0 の走査はこの一覧と突き合わせる |

| 触るファイル | 触らないファイル |
|---|---|
| `MitateDB-api/src/mitatedb_api/backend_postgres.py` (移動範囲、import 1 行、委譲 1 行)、新規 `MitateDB-api/src/mitatedb_api/postgres_sql.py`、`MitateDB-api/tests/test_foundation.py` (新規テスト 4 本)、`MitateDB-api/src/mitatedb_api/backend_sqlite.py` (L45 の括弧書きだけ)、`docs/code-history/MitateDB-api/backend_sqlite.md` (§CH-0340 の訂正の記録だけ)、`MitateDB-api/tests/test_postgres.py` (L1418 の括弧書きだけ。R-44 WP-3 と重なるので §5.40 の調整に従う)、`MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py` (allowlist 20 件の行送りと行送りコメントだけ)、`tools/tests/test_leaf_import_direction.py` (leaf 1 行、許可 `psycopg`・`.backend`) | `cell.py`、`http.py`、`backend.py`、`postgres_types.py`、`postgres_value_domain.py`、`MitateDB-api/tests/test_audit_query.py`、`MitateDB-api/tests/test_order_by_direction_hardening.py`、`docs/code-history/MitateDB-api/backend_postgres.md`、`conformance-tests/`、r2db-api 全部、`docs/design/`、roadmap |

| # | 完了条件 | 変異 (`file:操作`) | 赤になる test id (予想) |
|---|---|---|---|
| 1 | facade 互換 (委譲属性と 2 定数が leaf を指す) | `backend_postgres.py`: `_where_sql = staticmethod(_where_sql)` の行を消す | `MitateDB-api/tests/test_foundation.py::test_postgres_sql_leaf_preserves_backend_facade` (新規。3 名が leaf と `is`) |
| 2 | WHERE 片の組立が逐語 (空 filters、`AND` 連結、`IN` の placeholder 個数、params の順) | `postgres_sql.py`: `sql.SQL(" AND ")` を `sql.SQL(" OR ")` にする | `MitateDB-api/tests/test_foundation.py::test_postgres_sql_where_fragment_is_composed_literally` (新規。空・単項・2 項・`in` を literal で固定する) |
| 3 | 空の filters は空片と空 params を返す | `postgres_sql.py`: `if not filters:` を `if False:` にする | 2 の新規テスト |
| 4 | 値は placeholder 経由でしか SQL に入らない (D-4、設計 §5.2 の「SQL 安全性」) | `postgres_sql.py`: `sql.SQL("{} {} %s").format(column, _OPERATOR_SQL[item.operator])` を、値を f-string で埋める形に置換する | `MitateDB-api/tests/test_foundation.py::test_postgres_sql_never_inlines_a_value_into_the_fragment` (新規。`'` を含む値で、組立た `Composed` の断片に `sql.Placeholder` があり、値は `params` にだけ現れることを固定する) |
| 5 | operator token は閉じた表から引く | `postgres_sql.py`: `{name: sql.SQL(token) for name, token in SQL_OPERATOR_TOKENS.items()}` を `{name: sql.SQL("=") for name in SQL_OPERATOR_TOKENS}` にする | `MitateDB-api/tests/test_foundation.py::test_postgres_sql_operator_and_direction_tokens_are_closed` (新規。`_OPERATOR_SQL`・`_DIRECTION_SQL` を literal で固定する) |
| 6 | sort direction は閉じた表から引く | `postgres_sql.py`: `_DIRECTION_SQL` の `"desc"` を `sql.SQL("ASC")` にする | 5 の新規テスト。`MitateDB-api/tests/test_postgres.py` の降順 `order_by` を通す既存テスト |
| 7 | 行番号 allowlist の行送り (40b、Z4-5) | `MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py`: 更新した 20 件のうち 1 件を旧値に戻す | `MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py::test_allowlist_entries_match_real_bare_call_sites` |
| 8 | `backend_postgres.py` の件数 pin が動かない (21) | `backend_postgres.py`: 4-key の `ValidationError` を raise する private 関数を 1 つ足す | `MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py::test_ast_full_count_matches_a_non_trivial_floor` |
| 9 | 移動先が走査の対象に入る (40b) | `postgres_sql.py`: 4-key の `ValidationError` を raise する関数を 1 つ足す (**import は足さない**。走査は AST だけを読むので未定義名でも数える。B-2) | `MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py::test_every_module_with_a_vocabulary_denial_is_accounted_for` |
| 10 | leaf の import が許可リストの内だけ | `postgres_sql.py`: `import os` を 1 行足す | `tools/tests/test_leaf_import_direction.py::test_leaf_modules_import_only_their_allowlisted_modules` |
| 11 | 新 leaf が分類される | 一覧から `postgres_sql.py` の行を消す | `tools/tests/test_leaf_import_direction.py::test_every_src_module_is_classified` |
| 12 | CH-0340 の訂正の記録 (WF-5 (iv)) | `docs/code-history/MitateDB-api/backend_sqlite.md`: §CH-0340 に足した訂正の記録を消す | 使い捨て clone のコミット後の HEAD で `tools/tests/test_comment_provenance.py::test_0f_both_peers_all_src_rev_vs_itself_is_green` |
| 13 | 手順 0 の走査 (§5.40) | **監査照合**: 3 名を repo 全体で走査した実行コマンドと出力 (件数と `file:line` の一覧) を報告に貼り、設計 §10 に残す。分類の無い参照が 0 件であること | — |
| 14 | 逐語移動と位置参照 (40c) | **監査照合**: 説明コメントと本体が AST とコメントで逐語。本体の差は `self` 引数の除去 1 種だけ。括弧書きは上表の 2 箇所だけ | — |
| 15 | 同型・統合・来歴の証拠 | **監査照合**: `_ISOMORPHIC_TARGETS` の差分 0 (WF-1)、WF-4、WF-6。来歴は使い捨て clone の HEAD での `tools/tests` 0f の集計行 (Z4-4) | — |

### 5.42 WP-4b — r2db の catalog の型写像 (PG1、**独立レビュー反映済み**)

**目的**: `_DOMAIN_TO_DECLARED`・`_SQL_TYPE_TO_DECLARED`・`_TableInfo` を、既存 leaf `r2db-api/src/r2db_api/postgres_types.py` へ追加する (Z4-8。新しい module は作らない)。`_load_catalog`・`_describe_table` の catalog 読み取りと `information_schema` 照会はいずれも `postgres.py` に残る。**WP-4a の統合後に着手する。**

| 項目 | 実測 (`ed265f4`。4a の統合後に取り直す) |
|---|---|
| 移動範囲 (3 名、2 塊、計 48 行) | L205-226 (`_DOMAIN_TO_DECLARED` の説明コメントと CH-0005 の行、dict 本体 L207-210、`_SQL_TYPE_TO_DECLARED` の説明コメント L212-220 (L211 は空行。C-4) と dict 本体 L221-226。規律 2)、L250-275 (`@dataclass` デコレータ L250 を含む `_TableInfo`。docstring と CH-0006・CH-0101 を含む。`end_lineno` は 275 で L276 は空行 — C-1 が第 2 次裁定 8 の「L250-276」を訂正する) |
| 飛び石 | 間の L227-249 は動かさない (`_RolePool` の bounded-wait 既定値の説明コメントと `_DEFAULT_CONNECT_TIMEOUT_S`・`_DEFAULT_ACQUIRE_TIMEOUT_S`、および `_COMPARISON_OPERATORS` L240-247 — 後者は WP-4d が移す)。leaf の中は `_DOMAIN_TO_DECLARED` → `_SQL_TYPE_TO_DECLARED` → `_TableInfo` の順に、既存の `_column_type_sql` の後ろへ置く |
| 本体の変更 | 無し (定数と dataclass をそのまま移す)。`_TableInfo` は method を 1 つも持たない |
| facade に残すもの | `postgres.py` は既存の `from .postgres_types import ...` (L110) に 3 名を足して読む。組み立てる・読む箇所は L940 (`_DOMAIN_TO_DECLARED.get`)、L942 (`_SQL_TYPE_TO_DECLARED.get`)、L976 (`_TableInfo(...)` の構築)、型ヒント L819・L862・L1536・L1715 で、いずれも `postgres.py` に残る |
| leaf の import | 現在の `psycopg` (`sql`) に加えて `dataclasses` (`dataclass`・`field`)、`typing` (`Any`)。許可集合は `{"psycopg", "dataclasses", "typing"}`。**`constraints: dict[str, "FieldConstraints"]` の `FieldConstraints` は import しない** (W4-2。`from __future__ import annotations` の下で注釈は評価されない。`TYPE_CHECKING` も使わない。前例は `r2db-api/src/r2db_api/inmemory_predicate.py` L14 (`from __future__ import annotations`) / L95 (`predicate: Predicate`)。C-7)。移す注釈は裸の名前のまま書く |
| denial・件数 pin | 移動範囲の denial は 0 件 (`ValueError` も無い)。`postgres.py` は `counts` 辞書に含まれないので差分 0 (Z4-6)。`postgres_types.py` は denial 0 のままなので辞書に足さない |
| `SCANNED_MODULES`・sib tuple | どちらも差分 0。`postgres_types.py` は既に leaf として登録済みで、denial を持たない。40b の確認は完了条件 9 の変異で示す |
| 行番号 allowlist (Z4-5) | `("postgres.py", 1523)` が 2 塊 (計 49 行) の削除と import 1 行の追加のぶん上へ動く。実測で取り直し、L121-124 と同じ形の行送りコメントを足す |
| CH-ID (Z4-4) | 3 件が移動範囲にある。CH-0005 (L206、`_DOMAIN_TO_DECLARED` の説明コメント)、CH-0006 (L266、`_TableInfo` の docstring)、CH-0101 (L274、`constraints` field のコメント)。3 件とも `docs/code-history/r2db-api/postgres.md` に節がある (L169・L182・L1969)。**節は動かさず、`postgres_types.md` は作らない。** `# history:` / `History:` の行も逐語で一緒に移す |
| 位置参照 (WF-5) | **付ける**: CH-0101 のコメント L271 の「read from the side-table registry (`_load_field_constraints` below)」の `below` の直後に「(in `postgres.py`)」(WF-5 (i)。`_load_field_constraints` は L980 に残る)。**この塊は CH-0101 を持つ**ので、同じ変更で `docs/code-history/r2db-api/postgres.md` §CH-0101 に §5.27 の形式の訂正の記録を書く (WF-5 (iv))。**付けない**: `_SQL_TYPE_TO_DECLARED` のコメント L216 の「one of the two DOMAINs above (`_DOMAIN_TO_DECLARED` …)」(above の指す先も一緒に移る)、CH-0101 の「`columns`/`indexes` above」(同上)、`_TableInfo` docstring の `PostgresCell._load_catalog`・`PostgresCell.apply_schema` (修飾名。WF-5 (ii))、`_load_catalog` の名前だけの参照 (L206・L217)、`postgres.py` L108-109 の CH-0002 のコメント (名指しの `_FIELD_TYPE_SQL`/`_JSONB_SQL` の 2 名だけを述べており、移動で真偽が変わらない。W3-21 (1) と同じく確かめたものとして記録する)、`postgres.py` の型ヒント 4 箇所 (import で読める)、`docs/code-history/r2db-api/postgres.md` の登録簿の節 (Z4-4)、`docs/work-orders/WORK_ORDER_CODE_COMMENT_PROVENANCE_CS1.md` の表 (過去の作業指示書。§1.8 の 57 により本文を書き換えない)。**既知の穴** (WF-5 (iii)、§5.45): `docs/design/PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md` の **L49 と L111 の 2 件** (A-3)。L49 の `postgres.py:249` と L111 の `:232-236`/`:249`/`:173-176` はいずれも移動前からすでに古い |

| 触るファイル | 触らないファイル |
|---|---|
| `r2db-api/src/r2db_api/postgres.py` (移動範囲、import 1 行の名前追加)、`r2db-api/src/r2db_api/postgres_types.py` (3 名の追加と import)、`r2db-api/tests/test_foundation.py` (新規テスト 3 本)、`docs/code-history/r2db-api/postgres.md` (§CH-0101 の訂正の記録だけ)、`r2db-api/tests/test_l1_details_vocabulary_ast_scan.py` (allowlist 1 件の行送りと行送りコメントだけ)、`tools/tests/test_leaf_import_direction.py` (`postgres_types.py` の許可集合 1 行) | `structured.py`、`schema_binding.py`、`service.py`、`backend.py`、`postgres_like.py`、`r2db-api/tests/test_postgres.py`、`r2db-api/tests/test_audit_query.py`、`conformance-tests/`、MitateDB-api 全部、`docs/design/`、roadmap |

| # | 完了条件 | 変異 (`file:操作`) | 赤になる test id (予想) |
|---|---|---|---|
| 1 | facade 互換 (3 名が leaf と同一) | `postgres.py`: `.postgres_types` の import の直後で `_TableInfo = type("_TableInfo", (), {})` と上書きする (W3-14 の形。import から名前を外す形は `_load_catalog` の実行時 NameError になり、条件 1 だけを壊さない) | `r2db-api/tests/test_foundation.py::test_postgres_types_leaf_preserves_postgres_facade` (新規。3 名が leaf と `is`) |
| 2 | DOMAIN 名 → 宣言型の写像が逐語 | `postgres_types.py`: `_DOMAIN_TO_DECLARED` の `"_r2db_json_array": "array"` を `"object"` にする | `r2db-api/tests/test_foundation.py::test_postgres_types_catalog_maps_are_literal` (新規。2 辞書を literal で固定する) |
| 3 | `information_schema.data_type` → 宣言型の写像が逐語 | `postgres_types.py`: `_SQL_TYPE_TO_DECLARED` から `"double precision": "number"` を外す | 2 の新規テスト |
| 4 | `_TableInfo` の field と既定値 (`constraints` は呼び出しごとに新しい `{}`) | `postgres_types.py`: `constraints: dict[str, "FieldConstraints"] = field(default_factory=dict)` を `= field(default_factory=list)` にする | `r2db-api/tests/test_foundation.py::test_table_info_fields_and_defaults` (新規。`dataclasses.fields` の名前・順序と、2 つの実体で `constraints` が共有されないことを固定する) |
| 5 | 行番号 allowlist の行送り (40b、Z4-5) | `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py`: 更新した `("postgres.py", <実測値>)` を旧値 `1523` に戻す | `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py::test_allowlist_entries_match_real_bare_call_sites` |
| 6 | leaf の import が許可リストの内だけ | `postgres_types.py`: `import os` を 1 行足す | `tools/tests/test_leaf_import_direction.py::test_leaf_modules_import_only_their_allowlisted_modules` |
| 7 | **leaf は注釈対象の型を import しない** (W4-2) | `postgres_types.py`: `from .structured import FieldConstraints` を 1 行足す | `tools/tests/test_leaf_import_direction.py::test_leaf_modules_import_only_their_allowlisted_modules` |
| 8 | 移動先が走査の対象に入る (40b) | `postgres_types.py`: 4-key の `fail("VALIDATION_FAILED", …, details=violation(…))` を持つ関数を 1 つ足す (**import は足さない**。B-2) | `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py::test_every_module_with_a_vocabulary_denial_is_accounted_for` |
| 9 | CH-ID が塊と一緒に移る (Z4-4) | `postgres_types.py`: `_TableInfo` docstring の `History: CH-0006` を `History: CH-0005` に差し替える | 使い捨て clone のコミット後の HEAD で `tools/tests/test_comment_provenance.py::test_0f_both_peers_all_src_rev_vs_itself_is_green` |
| 10 | CH-0101 の訂正の記録 (WF-5 (iv)) | `docs/code-history/r2db-api/postgres.md`: §CH-0101 に足した訂正の記録を消す | 同上 (使い捨て clone の HEAD) |
| 11 | 手順 0 の走査 (§5.40) | **監査照合**: 3 名を repo 全体で走査した実行コマンドと出力を報告に貼り、設計 §10 に残す。分類の無い参照が 0 件であること | — |
| 12 | 逐語移動と位置参照 (40c) | **監査照合**: 説明コメント・docstring・`# history:` 行が逐語。本体の変更は無い。括弧書きは CH-0101 の 1 箇所だけ | — |
| 13 | 同型・統合・来歴の証拠 | **監査照合**: `_ISOMORPHIC_TARGETS` の差分 0 (WF-1)、WF-4、WF-6。来歴は使い捨て clone の HEAD での `tools/tests` 0f の集計行 (Z4-4) | — |

### 5.43 WP-4c — r2db の SQL 文の組立 (PG3、**独立レビュー反映済み**)

**目的**: `_select_statement`・`_order_by_sql`・`_append_revision_predicate` を leaf `r2db-api/src/r2db_api/postgres_sql.py` (新規、Z4-8) の関数へ移す (D-4。method → 関数)。列名の定数は動かさず、既定値の無い引数で facade から渡す (W4-1)。class には委譲属性を残し、`query`/`_update`/`_delete`/`_apply_upsert` の呼出しの形と、`_run` による実行・transaction・lock・例外分類はいずれも `postgres.py` に残る。**WP-4b の統合後に着手する。**

| 項目 | 実測 (`ed265f4`。4b の統合後に取り直す) |
|---|---|
| 移動範囲 (3 名、2 塊、計 57 行) | L1280-1312 (`_select_statement` 26 行と `_order_by_sql` 6 行。間の空行を含む 33 行)、L1602-1625 (`_append_revision_predicate`、docstring と CH-0045 を含む 24 行) |
| 飛び石 | 間の L1313-1601 は動かさない (L1314 の区切りコメント `# ---- mutations ----` 以下の mutation 系 method 群)。leaf の中は `_select_statement` → `_order_by_sql` → `_append_revision_predicate` の順に置く |
| 本体の変更 | (a) 3 つとも `self` 引数を除く、(b) `_select_statement` L1294 の `self._order_by_sql(order_spec)` を `_order_by_sql(order_spec)` にする、(c) **`_select_statement` と `_append_revision_predicate` に既定値の無い引数 `revision_column` を足し、本体の `_REVISION_COLUMN` (L1290・L1623) をその引数に置き換える** (W4-1。W3-10 と同じ形)、の 3 種だけ。`_order_by_sql`・`_append_revision_predicate` は `self` を 1 度も参照しない (実測)。差は W3-3・W3-12 と同じく列挙してログに残す |
| 列名定数の扱い (W4-1) | `_REVISION_COLUMN` (`postgres.py` L202) は**動かさない**。移動範囲の外に **4 箇所**の読み手 (L926・L1677・L1779・L2294) があり、移すと 4c が PG3 を大きく超えるためである (**B-3 の訂正**: 第 2 次裁定 W4-1 の根拠は「6 箇所」と書いたが、総使用数 6 のうち L1290・L1623 の 2 箇所は移動範囲の中である。裁定の結論は変わらない)。facade の呼出し箇所 L1253 (`query`)・L1676 (`_update`)・L1695 (`_delete`)・L1791 (`_apply_upsert`) が `_REVISION_COLUMN` を渡す。`_ID_COLUMN` (L201) は PG3 の 3 関数のいずれも読まない (実測) ので引数にも入れない。**着手時の実測で読んでいたら、同じく既定値の無い引数で渡す** |
| class (facade) に残すもの | `_select_statement`・`_order_by_sql`・`_append_revision_predicate` の 3 つの委譲属性 (`_select_statement = staticmethod(_select_statement)` の形、WP-3i と同じ)。呼出し元 4 箇所はそのまま `self.` で動き、引数が 1 つ増える。L1294 の sibling 呼出しは leaf の中の直接呼出しになる |
| leaf の import | `psycopg` (`from psycopg import sql`)、`typing` (`Any`)。`.errors` は要らない (範囲内に denial が無い)。`postgres.py` は import しない (循環)。許可集合は `{"psycopg", "typing"}` |
| denial・件数 pin | 移動範囲の denial は 0 件 (実測)。`postgres.py` は `counts` 辞書に含まれない (Z4-6) ので差分 0。新 leaf は denial 0 なので辞書に足さない (WP-4d で足す) |
| `SCANNED_MODULES`・sib tuple | どちらも差分 0 (新 leaf は denial 0。`SCANNED_MODULES` への追加は WP-4d で行う)。40b の確認は完了条件 11 の変異で示す |
| 行番号 allowlist (Z4-5) | `("postgres.py", 1523)` が L1280-1312 の削除と import 1 行・委譲 3 行の増減ぶん動く (L1602-1625 は L1523 より下なので効かない)。実測で取り直し、行送りコメントを足す |
| CH-ID (Z4-4) | 2 件が移動範囲にある。CH-0026 (L1304、`_select_statement` の `OFFSET`/`LIMIT` のコメント)、CH-0045 (L1619、`_append_revision_predicate` の docstring)。どちらも `docs/code-history/r2db-api/postgres.md` に節がある (L599・L907)。節は動かさず、`# history:` / `History:` の行を逐語で一緒に移す。**範囲外の CH-0001 にも括弧書きを足す** (下の位置参照の欄) |
| 位置参照 (WF-5) | **付ける (2 箇所)**: (1) `postgres.py` L1271 の「Every row was selected as `select ++ [_r2db_revision::text]` (`_select_statement`, below)」の `below` の直後に「(now in `postgres_sql.py`)」(範囲外に残る文だが指す先が移る。§5.5 の規律 1)。この塊に CH-ID は無い (直前の CH-0025 は L1264 の別の塊) ので訂正の記録は書かない。(2) `postgres.py` の module docstring L22-23 の「Every SQL fragment built anywhere below that carries a client-supplied identifier/operator/value is constructed via …」の `below` の直後に「(and in `postgres_sql.py`)」。WF-5 (i) の機械適用である (SELECT 文の組立が別 module へ出るので、`below` だけでは覆わなくなる)。**この塊は CH-0001 を持つ**ので、同じ変更で `docs/code-history/r2db-api/postgres.md` §CH-0001 に §5.27 の形式の訂正の記録を書く (WF-5 (iv)、W3-22 の R2 の前例)。**付けない**: CH-0026 の「the same pattern `_set_timeouts` already uses」(名前だけ。§5.38 の前例)、同じ塊の「`sql.Literal` here」(指す先も一緒に移る)、`ApplicationCell._sort_key`・`bind_mutation`・`ApplicationCell` の名前 / 修飾名の参照 (WF-5 (ii))、module docstring L16 の `_COMPARISON_OPERATORS` (名前だけ。WP-4d で移るが文は真のまま)、`docs/code-history/r2db-api/postgres.md` の登録簿の節 (Z4-4)、`docs/work-orders/WORK_ORDER_CODE_COMMENT_PROVENANCE_CS1.md` の表 |

| 触るファイル | 触らないファイル |
|---|---|
| `r2db-api/src/r2db_api/postgres.py` (移動範囲、import 1 行、委譲 3 行、呼出し 4 箇所の引数、L1271 と module docstring の括弧書き)、新規 `r2db-api/src/r2db_api/postgres_sql.py`、`r2db-api/tests/test_foundation.py` (新規テスト 5 本)、`docs/code-history/r2db-api/postgres.md` (§CH-0001 の訂正の記録だけ)、`r2db-api/tests/test_l1_details_vocabulary_ast_scan.py` (allowlist 1 件の行送りと行送りコメントだけ)、`tools/tests/test_leaf_import_direction.py` (leaf 1 行) | `structured.py`、`postgres_types.py`、`postgres_like.py`、`service.py`、`r2db-api/tests/test_postgres.py`、`r2db-api/tests/test_audit_query.py`、`conformance-tests/`、MitateDB-api 全部、`docs/design/`、roadmap |

| # | 完了条件 | 変異 (`file:操作`) | 赤になる test id (予想) |
|---|---|---|---|
| 1 | facade 互換 (3 つの委譲属性が leaf を指す) | `postgres.py`: `_select_statement = staticmethod(_select_statement)` の行を消す | `r2db-api/tests/test_foundation.py::test_postgres_sql_leaf_preserves_postgres_delegates` (新規。3 属性が leaf の関数と `is`) |
| 2 | SELECT 文の並び (列 + revision、FROM、WHERE、ORDER BY、OFFSET、LIMIT) が逐語 | `postgres_sql.py`: `"{base} OFFSET {offset} LIMIT {limit}"` の `OFFSET`/`LIMIT` の順を入れ替える | `r2db-api/tests/test_foundation.py::test_select_statement_is_composed_literally` (新規。`as_string` を使わず、`Composed` の断片の列を literal で固定する) |
| 3 | 先読み 1 行 (`page_size + 1`) を取る | `postgres_sql.py`: `limit=sql.Literal(int(page_size) + 1)` を `int(page_size)` にする | 2 の新規テスト。`r2db-api/tests/test_postgres.py` の `has_more` を確かめる既存テスト |
| 4 | ORDER BY の direction は固定リテラルの 2 値だけ | `postgres_sql.py`: `sql.SQL("ASC" if direction == "asc" else "DESC")` を `sql.SQL("ASC")` にする | `r2db-api/tests/test_foundation.py::test_order_by_sql_uses_only_fixed_direction_literals` (新規。asc / desc の両方と複数項を固定する) |
| 5 | revision 述語は `::text` の比較を placeholder で束縛する (D-4、設計 §5.2 の「SQL 安全性」を builder unit test で取る。W4-3) | `postgres_sql.py`: `ph=sql.Placeholder()` を `ph=sql.SQL(expected_revision)` にする | `r2db-api/tests/test_foundation.py::test_append_revision_predicate_binds_the_expected_revision` (新規。`Composed` の断片に `sql.Placeholder` があり、値は params の末尾にだけ現れることを固定する) |
| 6 | `expected_revision` が `None` のときは述語も params も変えない | `postgres_sql.py`: `if expected_revision is None:` を `if False:` にする | 5 の新規テスト |
| 7 | **leaf は列名を既定値の無い引数で受け、module 定数を読まない** (W4-1) | `postgres_sql.py`: `revision_column` の引数に既定値 `= "_r2db_revision"` を足す | `r2db-api/tests/test_foundation.py::test_postgres_sql_takes_column_names_as_required_arguments` (新規。`inspect.signature` で 2 関数の該当引数に既定値が無いこと、および leaf の namespace に `_REVISION_COLUMN`/`_ID_COLUMN` が無いことを固定する) |
| 8 | 行番号 allowlist の行送り (40b、Z4-5) | `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py`: 更新した `("postgres.py", <実測値>)` を前の WP の値に戻す | `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py::test_allowlist_entries_match_real_bare_call_sites` |
| 9 | leaf の import が許可リストの内だけ | `postgres_sql.py`: `import os` を 1 行足す | `tools/tests/test_leaf_import_direction.py::test_leaf_modules_import_only_their_allowlisted_modules` |
| 10 | 新 leaf が分類される | 一覧から `postgres_sql.py` の行を消す | `tools/tests/test_leaf_import_direction.py::test_every_src_module_is_classified` |
| 11 | 新 leaf が走査の対象に入る (40b) | `postgres_sql.py`: 4-key の `fail("VALIDATION_FAILED", …, details=violation(…))` を持つ関数を 1 つ足す (**import は足さない**。B-2) | `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py::test_every_module_with_a_vocabulary_denial_is_accounted_for` |
| 12 | CH-ID が塊と一緒に移る (Z4-4) | `postgres_sql.py`: `_append_revision_predicate` の `History: CH-0045` を `History: CH-0026` に差し替える | 使い捨て clone のコミット後の HEAD で `tools/tests/test_comment_provenance.py::test_0f_both_peers_all_src_rev_vs_itself_is_green` |
| 13 | CH-0001 の訂正の記録 (WF-5 (iv)) | `docs/code-history/r2db-api/postgres.md`: §CH-0001 に足した訂正の記録を消す | 同上 (使い捨て clone の HEAD) |
| 14 | 手順 0 の走査 (§5.40) | **監査照合**: 3 名と `_REVISION_COLUMN`・`_ID_COLUMN` を repo 全体で走査した実行コマンドと出力を報告に貼り、設計 §10 に残す。分類の無い参照が 0 件であること | — |
| 15 | 本体は列挙した差を除き同一 | **監査照合**: `self` 引数・sibling 呼出し・列名引数の 3 種を戻した leaf の本体が、移動前と AST で一致する。差の列挙をログに残す | — |
| 16 | 逐語移動と位置参照 (40c) | **監査照合**: docstring・コメント・`# history:` 行が逐語。括弧書きは L1271 と module docstring の 2 箇所だけ | — |
| 17 | 同型・統合・来歴の証拠 | **監査照合**: `_ISOMORPHIC_TARGETS` の差分 0 (WF-1)、WF-4、WF-6。来歴は使い捨て clone の HEAD での `tools/tests` 0f の集計行 (Z4-4) | — |

### 5.44 WP-4d — r2db の SQL 述語の組立と値の束縛 (PG2、**独立レビュー反映済み**)

**目的**: `_COMPARISON_OPERATORS` と `_where_clause`・`_text_expression`・`_predicate_sql`、および `_bind_value` (Z4-3) を、WP-4c が作った leaf `r2db-api/src/r2db_api/postgres_sql.py` へ移す (D-4。method → 関数)。class には WP-3i と同じ委譲属性を残し、`_bind_value` の他の 6 呼出し箇所 (L1655・L1681・L1752・L1783・L1806・L2177) は `self._bind_value` のまま動かす。移す 2 件の 4-key denial は語彙・`details` とも 1 文字も変えない。**WP-4c の統合後に着手する。**

| 項目 | 実測 (`ed265f4`。4c の統合後に取り直す) |
|---|---|
| 移動範囲 (5 名、3 塊、計 97 行) | L240-247 (`_COMPARISON_OPERATORS`、8 行。直前に説明コメントは無い — 実測)、L1525-1534 (`_bind_value`、docstring と CH-0041 を含む 10 行。`end_lineno` は 1534 で L1535 は空行 — C-2 が Z4-3 と第 2 次裁定 8 の「L1525-1535」を訂正する)、L1825-1903 (`_where_clause` 10 行・`_text_expression` 23 行・`_predicate_sql` 44 行、間の空行を含む 79 行) |
| 飛び石 | 3 塊の間は動かさない。L1823 の区切りコメント (`# ---- predicate/WHERE composition ----`) は facade に残し、その直後に 3 つの委譲属性を置く。`_bind_value` の直前の `_fail_client_value` (`def` は L1507。L1508-1523 は docstring 以降。§3 の除外。C-3) には触らない |
| 本体の変更 | (a) 4 つとも `self` 引数を除く、(b) `self._predicate_sql` (L1831) → `_predicate_sql`、(c) `self._text_expression` (L1880) → `_text_expression`、(d) `self._bind_value` (L1878・L1903) → `_bind_value` の 4 種だけ。`_text_expression`・`_bind_value` は `self` を 1 度も参照しない (実測)。差は W3-3・W3-12 と同じく列挙してログに残す |
| class (facade) に残すもの | `_where_clause`・`_text_expression`・`_predicate_sql`・`_bind_value` の 4 つの委譲属性 (`_bind_value = staticmethod(_bind_value)` の形、WP-3i と同じ。Z4-3)。呼出し元 L1252 (`query`)・L1581 (`_apply`) の `self._where_clause`、L1655・L1681・L1752・L1783・L1806・L2177 の `self._bind_value` はそのまま動く。`_COMPARISON_OPERATORS` は移動後 `postgres.py` に読み手が残らない (module docstring L16 が名前で言及するだけ) ので、4a と同じく第 2 次裁定 6 に従う (読み手 0 を実測で示して削るか、再 export として残すか。削る場合は根拠と回帰証拠を WP 記録に添える) |
| leaf の import | WP-4c までの `psycopg` (`sql`)・`typing` に加えて `psycopg.types.json` の `Jsonb` (`psycopg` に正規化される)、`.postgres_like` (`_escape_like_literal`)、`.errors` (`fail`・`violation`)。`.postgres_like` は import を持たない 12 行の leaf で、循環にならない (実測)。許可集合は `{"psycopg", "typing", ".postgres_like", ".errors"}`。**`_predicate_sql(predicate: Predicate, …)` と `_where_clause(where: list[Predicate], …)` (移動前は L1825) の `Predicate` は import しない** (W4-2。`from __future__ import annotations` の下で注釈は評価されない。`TYPE_CHECKING` も使わない。前例は `inmemory_predicate.py` L14 / L95。C-7) |
| denial・件数 pin (Z4-6) | 移動範囲の 4-key denial は 2 件。L1874 (`"Filter value is incompatible with the selected operator."`、`violation("request_schema", field="where")`) と L1902 (`"Unsupported filter operator."`、`violation("capability", field="where")`)、いずれも `_predicate_sql` の中。**移動元 `postgres.py` は `counts` 辞書に含まれないので減算コメントを書かない。移動先は `counts` 辞書に `"postgres_sql.py": 2` を足し、前例と同じ形の由来コメント (どの method が移す前に持っていた何件か) を添える** |
| `SCANNED_MODULES`・sib tuple | `SCANNED_MODULES` (L84) に `postgres_sql.py` を足す (40b)。sib の固定 module 集合は in-memory 側 (`structured.py` と抽出 leaf 7 件) の集合なので、backend 層の `postgres_sql.py` は足さない (差分 0)。`test_backend_layer_allowlist_is_confined_to_postgres_py` の前提 (allowlist は `postgres.py` だけ) も変わらない |
| 行番号 allowlist (Z4-5) | `("postgres.py", 1523)` は L240-247 の削除ぶんだけ上へ動く (`_bind_value` L1525-1535 と 3 method は L1523 より下なので効かない)。実測で取り直し、行送りコメントを足す |
| CH-ID (Z4-4) | **6 件**が移動範囲にある (第 2 次裁定 4)。CH-0041 (L1528、`_bind_value` の docstring)、CH-0053 (L1854、`_text_expression` の docstring)、CH-0054 (L1877)、CH-0055 (L1885)、CH-0056 (L1890)、CH-0057 (L1901)。6 件とも `docs/code-history/r2db-api/postgres.md` に節がある (L850・L1046・L1074・L1087・L1102・L1114)。節は動かさず、`# history:` / `History:` の行も逐語で一緒に移す。`_COMPARISON_OPERATORS` (L240-247) に CH-ID は無い |
| 位置参照 (WF-5) | **付ける**: CH-0054 のコメント L1866 の「both call sites of `_where_clause` (`query`/`_apply` above)」の `above` の直後に「(in `postgres.py`)」。**この塊は CH-0054 を持つ**ので、同じ変更で `docs/code-history/r2db-api/postgres.md` §CH-0054 に §5.27 の形式の訂正の記録を書く (WF-5 (iv)、W3-22 の R2 の前例。第 2 次裁定 5)。**付けない**: 同じ塊の「mirroring `_predicate_sql`'s … fallback below」(指す先も一緒に移る)、CH-0057 の「`structured.OPERATORS` (now in `mutation_binding.py`)」(WP-3f で正しく直っており、この移動で指す先は変わらない。確かめたものとして記録する)、CH-0055 の `_validate_predicate_types`・CH-0041 の `ApplicationCell`・CH-0053 の `add_field` (名前 / 修飾名。WF-5 (ii))、`r2db-api/src/r2db_api/pg_text_format.py` L7 と `r2db-api/src/r2db_api/inmemory_predicate.py` L67・L79 の `PostgresCell._text_expression` (委譲属性で同じ修飾名から読める。WF-5 (ii))、`r2db-api/tests/test_postgres.py` L1483 の「fallback in `_predicate_sql`」(名前だけ)、`postgres.py` L2166 の「`_bind_value` (never a bare member)」(名前だけで、委譲属性のまま真)、`postgres.py` module docstring L16 の `_COMPARISON_OPERATORS` (名前だけ)、同 docstring L22-23 の `below` (**WP-4c が既に「(and in `postgres_sql.py`)」を足しており、4d の移動先も同じ module なので変えない。確かめたものとして記録する**)、`docs/code-history/` の登録簿の節 (Z4-4) |

| 触るファイル | 触らないファイル |
|---|---|
| `r2db-api/src/r2db_api/postgres.py` (移動範囲、import 1 行、委譲 4 行)、`r2db-api/src/r2db_api/postgres_sql.py` (5 名の追加と import)、`r2db-api/tests/test_foundation.py` (新規テスト 5 本)、`r2db-api/tests/test_l1_details_vocabulary_ast_scan.py` (`SCANNED_MODULES`、`counts` 辞書、allowlist 1 件の行送りと行送りコメント)、`docs/code-history/r2db-api/postgres.md` (§CH-0054 の訂正の記録だけ)、`tools/tests/test_leaf_import_direction.py` (`postgres_sql.py` の許可集合 1 行) | `structured.py`、`mutation_binding.py`、`postgres_types.py`、`postgres_like.py`、`pg_text_format.py`、`inmemory_predicate.py`、`service.py`、`r2db-api/tests/test_postgres.py`、`r2db-api/tests/test_audit_query.py`、`conformance-tests/`、MitateDB-api 全部、`docs/design/`、roadmap |

| # | 完了条件 | 変異 (`file:操作`) | 赤になる test id (予想) |
|---|---|---|---|
| 1 | facade 互換 (4 つの委譲属性が leaf を指す) | `postgres.py`: `_bind_value = staticmethod(_bind_value)` の行を消す | `r2db-api/tests/test_foundation.py::test_postgres_sql_leaf_preserves_predicate_delegates` (新規。4 属性が leaf の関数と `is`) |
| 2 | 比較演算子は閉じた表の固定リテラルだけ | `postgres_sql.py`: `_COMPARISON_OPERATORS` の `"ne": sql.SQL("<>")` を `sql.SQL("=")` にする | `r2db-api/tests/test_foundation.py::test_comparison_operators_are_literal` (新規。6 演算子を literal で固定する) |
| 3 | 述語の値は placeholder 経由でしか SQL に入らない (D-4、設計 §5.2 の「SQL 安全性」を builder unit test で取る。W4-3) | `postgres_sql.py`: `sql.SQL("{col} {op} {ph}")` の `ph=sql.Placeholder()` を、値を埋めた `sql.SQL(...)` に置換する | `r2db-api/tests/test_foundation.py::test_predicate_sql_never_inlines_a_value` (新規。`'` を含む値で、`Composed` の断片に `sql.Placeholder` があり、値は params にだけ現れることを固定する) |
| 4 | `contains` は LIKE のワイルドカードを escape し、`matches` はしない | `postgres_sql.py`: `escaped = _escape_like_literal(predicate.value)` を `escaped = predicate.value` にする | `r2db-api/tests/test_foundation.py::test_predicate_sql_escapes_only_contains_patterns` (新規。`%`・`_`・`\` を含む値の params を literal で固定する) |
| 5 | 型なし列の text 表現は `#>> '{}'`、型つきは `::text` | `postgres_sql.py`: `_text_expression` の `if field_type is None:` を `if False:` にする | `r2db-api/tests/test_foundation.py::test_text_expression_unwraps_only_untyped_columns` (新規) |
| 6 | 値の束縛 (`None` → SQL NULL、型なし / `object` / `array` → `Jsonb`、それ以外は素の値) | `postgres_sql.py`: `if field_type is None or field_type in ("object", "array"):` から `"array"` を外す | `r2db-api/tests/test_foundation.py::test_bind_value_wraps_only_json_shaped_columns` (新規。4 通りを literal で固定する) |
| 7 | 移した 2 件の denial が 4-key のまま | `postgres_sql.py`: L1902 相当の `fail("VALIDATION_FAILED", "Unsupported filter operator.", details=violation("capability", field="where"))` から、部分文字列 `, details=violation("capability", field="where")` だけを取り除く (行は残す。現物は 1 行で末尾カンマも無い — B-1) | `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py::test_every_choke_point_denial_carries_details_ast_full_count`、`::test_allowlist_entries_match_real_bare_call_sites` |
| 8 | 移動先が `SCANNED_MODULES` に入る (40b) | `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py`: `SCANNED_MODULES` から `postgres_sql.py` を外す | `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py::test_every_module_with_a_vocabulary_denial_is_accounted_for` |
| 9 | 件数 pin (`postgres_sql.py` 2。移動元は pin されない。Z4-6) | `postgres_sql.py`: 4-key の `fail("VALIDATION_FAILED", …, details=violation(…))` を持つ孤立した関数を 1 つ足す (**import は足さない**。B-2) | `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py::test_ast_full_count_matches_the_audit_site_count` (`{'postgres_sql.py': 3} != {'postgres_sql.py': 2}`) |
| 10 | 行番号 allowlist の行送り (40b、Z4-5) | `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py`: 更新した `("postgres.py", <実測値>)` を前の WP の値に戻す | `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py::test_allowlist_entries_match_real_bare_call_sites` |
| 11 | leaf の import が許可リストの内だけ | `postgres_sql.py`: `import os` を 1 行足す | `tools/tests/test_leaf_import_direction.py::test_leaf_modules_import_only_their_allowlisted_modules` |
| 12 | **leaf は注釈対象の型を import しない** (W4-2。注釈対象は `_predicate_sql(predicate: Predicate, …)` と `_where_clause(where: list[Predicate], …)` の 2 箇所。C-8) | `postgres_sql.py`: `from .structured import Predicate` を 1 行足す | `tools/tests/test_leaf_import_direction.py::test_leaf_modules_import_only_their_allowlisted_modules` |
| 13 | leaf の分類が保たれる | 一覧から `postgres_sql.py` の行を消す | `tools/tests/test_leaf_import_direction.py::test_every_src_module_is_classified` |
| 14 | CH-ID が塊と一緒に移る (Z4-4) | `postgres_sql.py`: `_predicate_sql` の `# history: CH-0057` を `# history: CH-0056` に差し替える | 使い捨て clone のコミット後の HEAD で `tools/tests/test_comment_provenance.py::test_0f_both_peers_all_src_rev_vs_itself_is_green` |
| 15 | CH-0054 の訂正の記録 (WF-5 (iv)) | `docs/code-history/r2db-api/postgres.md`: §CH-0054 に足した訂正の記録を消す | 同上 (使い捨て clone の HEAD) |
| 16 | 手順 0 の走査 (§5.40) | **監査照合**: 5 名を repo 全体で走査した実行コマンドと出力を報告に貼り、設計 §10 に残す。分類の無い参照が 0 件であること | — |
| 17 | 本体は列挙した差を除き同一 | **監査照合**: `self` 引数と 3 種の sibling 呼出しを戻した leaf の本体が、移動前と AST で一致する。差の列挙をログに残す | — |
| 18 | 逐語移動と位置参照 (40c) | **監査照合**: docstring・コメント・`# history:` 行が逐語。括弧書きは CH-0054 の 1 箇所だけ | — |
| 19 | 同型・統合・来歴の証拠 | **監査照合**: `_ISOMORPHIC_TARGETS` の差分 0 (WF-1)、WF-4、WF-6。来歴は使い捨て clone の HEAD での `tools/tests` 0f の集計行 (Z4-4) | — |

### 5.45 WP-4 の順序と未確定 (v1.17 追記)

- **順序**: 4a → 4b → 4c → 4d の直列 (Z4-2、Z4-7)。4 件とも `tools/tests/test_leaf_import_direction.py` を触り (U-5 / M2)、4b〜4d は `r2db-api/src/r2db_api/postgres.py`・`r2db-api/tests/test_foundation.py`・`r2db-api/tests/test_l1_details_vocabulary_ast_scan.py` を共有するので、並行しない。4d は 4c が作る leaf `postgres_sql.py` に足すので 4c の後に行う。4a は MitateDB 側だけを触るが、`tools/tests` を共有するので直列に含める。
- **新規テストの数 (C-2)**: 4a 4、4b 3、4c 5、4d 6、**計 18** (A-1。§5.44 の完了条件 1〜6 は 6 本とも新規テストである)。root の collection はこの数だけ増える。`tools/tests` は着手時の基点との差 0 (leaf を足しても node id は増えない)。R-44 側の新規テストと同時に動くので、期待値は統合の直前に main を取り込んでから出す (§5.40)。
- **完了条件「leaf の分類が保たれる」の扱い (C-9)**: §5.43 (4c) と §5.44 (4d) の同名の条件は、**その WP が作る新 leaf の登録**を固定するので残す。§5.42 (4b) は `postgres_types.py` が 4b 以前から leaf 一覧 (`tools/tests/test_leaf_import_direction.py` L94) にあり、同じ変異が 4b の主張する性質を壊さないので、§1.5 の 32 (空振り禁止) に照らして条件から外した (4b の完了条件は 14 → 13)。4b の分類まわりは W4-2 由来の「leaf は注釈対象の型を import しない」の条件が引き続き持つ。
- **設計 §9.3**: 4 件とも `_gate`・`_limit_gate`・認可・rate・slot・audit の呼出し経路を 1 行も変えない。移動範囲にこれらの呼出しは 1 件も無い。
- **PG4 を範囲外とした根拠の記録 (Z4-1)**: `r2db-api/src/r2db_api/postgres.py` L1907-2275 (`apply_schema` 全体、369 行) を通読した実測による。(1) method 全体が `with self._developer.connection() as conn: … with conn.transaction():` (L1941-1944) の単一の transaction / lock ブロックの中にある。(2) `sql.SQL(...)`/`sql.Identifier(...)` の組立は L2092、L2145-2146、L2175-2176 の 3 箇所だけで、いずれも 1〜2 行の単発であり、直後に同じ分岐の中で `_run()` され、`LOCK TABLE {table} IN SHARE ROW EXCLUSIVE MODE` (L2094・L2159) と地続きである。(3) method 全体で `self.` 経由の呼出しが 20 種以上あり (`_developer.connection`・`_timeout_ms`・`_set_timeouts`・`_load_catalog`・`_idempotency_*`・`_read_schema_revision`・`_create_entity`/`_drop_entity`/`_add_field`/`_create_index`/`_drop_index`・`_write_field_constraints`/`_clear_field_constraints`・`_describe_table`・`_bump_revision`・`_bind_value`・`_fail_unique_conflict`/`_fail_client_value`)、設計 §3.1 の「明示引数だけで決まる」を満たす連続した部分が無い。(4) `fail(...)` は 18 件あるが code はいずれも `CONFLICT`/`NOT_FOUND`/`LIMIT_EXCEEDED`/`SERVICE_UNAVAILABLE` で、L1 scan の対象語彙に 1 件も当たらない (抽出しても件数 pin・allowlist は動かない)。設計 §7 の停止条件「pure leaf が connection、transaction を必要とし、dependency を明示しても境界が細くならない」に当たるので、範囲を広げずに閉じる。設計 §3.2 と §3 が `apply_schema` を副作用境界として既に除外していることと整合する。§2.3 の PG4 行の「未確定」「範囲は WP-4 manifest で実測」はこの記録で閉じる (§1.8 の 57 のとおり §2.3 の本文は書き換えない)。
- **既知の穴** (移動前から存在し、範囲外。R-39 候補): `docs/design/PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md` の **L49 と L111 の 2 件** (A-3)。L49 の `postgres.py:249` と、L111 の「`_TableInfo.columns` は docstring (`:232-236`)」・`:249`・`:173-176` は、いずれも現在の行 (`_TableInfo` は L250-275) と合わない。`docs/work-orders/WORK_ORDER_CODE_COMMENT_PROVENANCE_CS1.md` の表が引く `postgres.py` の行番号 (L176-177・L230・L251・L259・L270-275 ほか) はすべて変更セット 1 当時のもので、既に古い。`docs/work-orders/WORK_ORDER_R37_WP0_INVENTORY_V1.md` §2.3・§2.5 の行範囲 (PG1 `L229-306`、PG2 `L262-269`・`L2051-2140`、PG3 `L1413-1447`・`L1800-1825`、PG4 `L2144-2631`、BP3 `L325-326`・`L1339-1353`) は 2026-09-14 の実測で、以後の抽出でずれている (本節と §5.40〜§5.44 の実測が現行値である。§1.8 の 57 のとおり §2 の本文は書き換えない)。`MitateDB-api/tests/test_order_by_direction_hardening.py` L5 の docstring は SQLite backend のテストの中で `_DIRECTION_SQL` に触れる (名前だけ)。**SQL 安全性の repo 全体の静的走査が両 peer とも無い** (設計 D-4 の「client-influenced statement が plain `str` で到達できない性質を新 module を含む走査で確認する」に当たる機構が実在しない)。W4-3 の裁定により WP-4 では作らず、WP-5 (facade 縮小と閉止) へ回す。R-39 候補として記録する。**`security/CONTROL_MAPPING.md` L538 と `MitateDB-api/README.md` L223 の `backend_postgres.py:1658-1661`** は移動前から既に古い (現在の L1658-1661 は advisory lock key の docstring であって `SET LOCAL statement_timeout` の箇所ではない)。**WP-4 では両方とも触らない。** `security/` は `tools/change_class.py` の `_D_DIR_PREFIXES` により **Class D** であり、宣言した Class B を超える。README 側だけを直すと同じ主張が 2 箇所で食い違うので、両方まとめて R-39 候補に送る (A-2 (5)、E)。**`postgres_sql.py` が `SCANNED_MODULES` に入った後の構造的な穴** (C-10): 同 module に将来 bare denial (`details` 無しの `fail`) が生じると、`test_allowlist_entries_match_real_bare_call_sites` が allowlist への追加を要求する一方、`test_backend_layer_allowlist_is_confined_to_postgres_py` (`r2db-api/tests/test_l1_details_vocabulary_ast_scan.py` L488-493 の `assert all(module == "postgres.py" …)`) がそれを禁じ、両立しない。WP-4 が移す 2 件は 4-key なので今回は赤にならない。R-39 候補として記録する。

**訂正註 2026-09-16 (WP-4 起草時の実測。§1.8 の 57 のとおり §2 の本文は書き換えない)**

- §2.3 の PG2 行の「既存テスト」欄が挙げる「静的安全性テスト」は、**実在するファイルを指していない** (2026-09-16 の実測: r2db の `tests/` に該当する静的走査のテストファイルは 0 件。MitateDB の `test_order_by_direction_hardening.py` は SQLiteBackend だけを見る)。PG2 の既存テストは `test_postgres.py` 経由の間接検証だけである。設計 §5.2 の「SQL 安全性」の赤の根拠は、同表が併記する builder unit test で取る (W4-3)。
- §2.3 の PG1〜PG4 行と §2.5 の BP3 行の行範囲・行数は 2026-09-14 の実測であり、以後の抽出でずれている。現行値は §5.40〜§5.44 の実測表である。

**未確定 (監督判断待ちとして起草時に挙げた点。裁定は下表。§1.8 の 56 のとおり行を消さない)**:

| # | 点 |
|---|---|
| W4-1 | 4c の `_REVISION_COLUMN` (`postgres.py` L202)。`_select_statement` (L1290) と `_append_revision_predicate` (L1623) の両方が読む。leaf が `postgres.py` を import することはできない (循環)。(a) 既定値の無い引数で facade から渡す (W3-10 の前例)。(b) 定数を leaf へ移し、`postgres.py` は facade 再 export で読む (§3 の除外一覧との関係で監督裁定が要る)。どちらにするか |
| W4-2 | leaf の型注釈のための import。4b の `_TableInfo.constraints: dict[str, "FieldConstraints"]` と、4d の `_predicate_sql(predicate: Predicate, …)`。(a) import しない (leaf の許可集合を増やさない)。(b) `TYPE_CHECKING` の下で import し、許可集合に `.schema_binding` / `.structured` を足す。どちらにするか。4b と 4d で同じ裁定にするか |
| W4-3 | 設計 D-4 は「client-influenced statement が plain `str` で到達できない性質を新 module を含む走査で確認する」と定めるが、その走査に当たる静的テストは現在 repo に存在しない。(a) WP-4c・4d の範囲で新 leaf を含む走査テストを足す。(b) 各 WP の builder unit test で代え、走査は WP-5 へ回す |

**監督裁定 (第 2 次、2026-09-16。逐語)**:

| # | 裁定 |
|---|---|
| W4-1 | **`_REVISION_COLUMN` は動かさない。4c の 2 関数へ、既定値の無い引数で渡す** (W3-10 の形)。`postgres.py` 側の呼出し箇所が `_REVISION_COLUMN` を渡す |
| W4-2 | **型注釈は `from __future__ import annotations` の下で裸の名前のまま書き、型を import しない。`TYPE_CHECKING` も使わない**。検証項目を足すこと: leaf が注釈対象の型を import していないことを完了条件に含める |
| W4-3 | **WP-4 で新しい静的走査は作らない。** 設計 §5.2 の「SQL 安全性」の赤の根拠は、同表が併記する **builder unit test** で取る。repo 全体の静的走査を足すかどうかは **WP-5 へ回し**、§5.45 に既知の穴 (R-39 候補) として記録する |
| 4 | **受け入れる。** `_bind_value` の CH-0041 を 4d の CH 一覧に足し、**4d の CH は 6 件**とする |
| 5 | **受け入れる。** 範囲外の位置参照のうち CH-ID を持つ 2 件 (MitateDB `backend_sqlite.py` L45 = CH-0340、r2db `postgres.py` L1866 = CH-0054) には、**W3-22 と同じく受け皿へ訂正の記録を書く**。「触らないファイル」から `backend_sqlite.py` と `docs/code-history/MitateDB-api/backend_sqlite.md` を外す |
| 6 | **条件付き。** `_OPERATOR_SQL` は、実装担当が **移動後の読み手 0 を実測で示したら削る**。1 件でもあれば §2.5 のとおり再 export として残す。削る場合は根拠 (読み手 0 の実測) と回帰証拠 (suite の集計行) を WP 記録に添える (設計 §4 WP-5 の「export を消す場合」の規律を前倒しで満たす)。前例は WP-3h の読み手 0 の import 削除 |
| 7 | **受け入れる。** WF-3 (認可 → 検査の順序) は WP-4 に置けない。移動範囲に認可・rate・audit の呼出しが無く、順序を壊す変異を作れない。設計 §5.2 の「SQL 安全性」の変異で代える。**W3-13 と同じ扱い**であり、§5.40 にその旨を明記する |
| 8 | **受け入れる。** 実測の細部を草稿の値へ直す: `_bind_value` は L1525-1535、`_TableInfo` はデコレータを含めて L250-276 |

- W4-1 の根拠 (監督の実測): `postgres.py` L201-202 の `_ID_COLUMN`/`_REVISION_COLUMN` は列名の文字列定数であり、§3 の除外行「表名・lock 定数 (L155-223)」が指す境界 (同範囲の `_IDEMPOTENCY_KEY_LOCK_NAMESPACE` L192・`_IDEMPOTENCY_COUNT_ADVISORY_LOCK_KEY` L194 の advisory lock) ではない。動かさない決め手は、**`_REVISION_COLUMN` に移動範囲の外の読み手が 6 箇所 (L926・L1677・L1779・L2294 ほか)、`_ID_COLUMN` に 7 箇所ある**ことである。**【訂正 2026-09-16 (第 3 次裁定 B-3)。上の行は §1.8 の 56 のとおり消さずに残す】** `_REVISION_COLUMN` の 6 は定義を除く総使用数であり、**移動範囲の外の読み手は 4 箇所 (L926・L1677・L1779・L2294)、範囲内が 2 箇所 (L1290・L1623)** である。`_ID_COLUMN` の 7 箇所 (L851・L923・L925・L1649・L1654・L1804・L1813) は実測どおりである。**裁定の結論 (`_REVISION_COLUMN` を動かさず、既定値の無い引数で渡す) は変えない。** 4 箇所でも成り立ち、除外範囲に触れないという主たる根拠も変わらない。引数で渡せば leaf は設計 §3.1 の「明示引数だけで決まる」を字義どおり満たし、除外範囲に一切触れない。
- W4-2 の根拠 (監督の実測): `r2db-api/src/r2db_api/inmemory_predicate.py` は L15 (**訂正: 正しくは L14。第 3 次裁定 C-7。前例そのものは成立する**) で `from __future__ import annotations` を宣言し、L95 で `predicate: Predicate` と注釈しながら `Predicate` を import していない。同ファイルは独立レビューと完了ゲートを通っている。`TYPE_CHECKING` を使う src module は `control_plane.py` の 1 件だけで、leaf には無い。
- **第 2 次裁定 8 の数値の訂正 (第 3 次裁定 C-1・C-2。§1.8 の 56 のとおり裁定の行は消さない)**: `_TableInfo` は **L250-275** (`end_lineno` は 275、L276 は空行) で 4b の移動範囲は 2 塊 計 **48** 行。`_bind_value` は **L1525-1534** (L1535 は空行) の **10** 行で、4d の移動範囲は 3 塊 計 **97** 行。Z4-3 の「L1525-1535」も同じ訂正で読む。あわせて第 3 次裁定 C-3 (`_fail_client_value` の `def` は L1507)、C-4 (`_SQL_TYPE_TO_DECLARED` の説明コメントは L212-220)、C-5 (`_where_sql` の呼出しは 5 箇所。`insert` は呼ばない)、C-6 (「invalid order direction」の denial は L1370) を各 manifest に反映した。
- W4-3 の適用範囲についての起草側の分類: 裁定は repo 全体の静的走査についてであり、`postgres.py` の module docstring (CH-0001) L22-23 の `below` の扱いは覆っていない。**WF-5 (i) の機械適用として「付ける」に分類し、WP-4c で括弧書きと §CH-0001 の訂正の記録を足す** (§5.43)。この分類を覆す場合は監督裁定を要する。

**依頼者判断待ち**: 無し。WP-4 は Class B (実装のみ。契約・不変条件・`_ISOMORPHIC_TARGETS` に触れない) であり、上記はいずれも監督裁定の範囲である。

**訂正註・裁定 2026-09-16 (WP-4a の実装と独立コードレビュー)。上の本文・表・裁定は起草時および第 2 次・第 3 次裁定時の原文であり、消さずに残す (`OPERATING_CONDITIONS.md` §1.8 の 57)。下の 1〜5 は WP-4a だけでなく §5.42 (4b)・§5.43 (4c)・§5.44 (4d) にも掛かる。**

**1. 監督裁定 (第 4 次。W4-4。逐語)**

発見 (WP-4a の実装担当、実装時): §5.41 の完了条件 **12** (CH-0340 の訂正の記録を消す変異 → 0f が赤) と **15** (来歴の証拠 = 記録後の HEAD での `tools/tests` 0f) は、**どちらも記録 (`git` への反映) を要する**。しかしそれは監督のみが行う (`OPERATING_CONDITIONS.md` §1.1 の 2)。本セッションの hook は、worktree の場所によらず subagent からのそれを一律に拒む。**したがって manifest は、実装担当に実行不能な完了条件を割り当てていた。** §5.40 の「CH-ID のファイルまたぎ移動」の証拠の段も同じ形で、**4b・4c・4d にも同じく掛かる** (3 件とも CH-ID を移す)。独立レビューはこれを検出しなかった (test id と実測値は照合したが、役割ごとの権限までは見ていない)。

| # | 裁定 |
|---|---|
| W4-4 (a) | **来歴の証拠 (完了条件 15) と、訂正の記録の変異 (完了条件 12) は監督が行う。** 実装担当の完了条件から外し、**「監督が実施する」と明記した監査照合**に変える。実装担当は変異の spec (`old` / `new` の文字列) を用意して報告するところまでを担当する |
| W4-4 (b) | **使い捨て clone は使わない。** 監督は `tools/dev/finalize.py --no-merge` で WP branch に記録し、**その HEAD で `tools/tests` を流して 0f の集計行を取る**。これが来歴の証拠である。証拠が緑であることを確かめてから main へ統合する。clone を作る理由は「実装担当が記録できないこと」だったが、監督は記録できるので、その回り道は要らない |
| W4-4 (c) | 完了条件 12 の変異は、(b) の記録の後に**監督が**作業ツリー側で当て、`tools/tests` の 0f が赤になることを確かめ、§1.4 の 29〜31 の規律 (scratchpad backup からの `cp` で復元、`sleep 3` の後に sha256 を 2 回照合、変異文字列の全文 grep 0 件) で戻す。0f が作業ツリーの companion を読まず git から読む形であれば、その場で判明するので、**その場合は捨て branch 上の記録で取り直し、結果を記録する** |
| W4-4 (d) | **4b・4c・4d の manifest にも同じ読み替えを掛ける。** 3 件とも CH-ID を移すので、来歴の証拠と訂正の記録の変異は同じく監督が行う |
| W4-4 (e) | 本件は §1.8 の 57 に従い、作業指示書の本文を書き換えず、**§5.45 に訂正註として記録する**。4a の統合時に他の記録とまとめて 1 つにする |

WP-4a での実施結果: 完了条件 15 は `dd59cd4` の HEAD で `tools/tests` `486 passed` (0f 緑)。完了条件 12 の変異 (M12) は監督が当て、予想どおり赤になり、復元を確かめた (`mutate: 1 mutations, 1 as expected, restores verified 1/1 files (sha256 x2)`)。0f が作業ツリーの companion を読む形であることは実測で確かめたので、W4-4 (c) の「捨て branch で取り直す」枝には入らなかった。

**2. 訂正の記録の `old:` / `new:` の書き方 (独立コードレビュー 高-1。4b〜4d にも掛かる)**

`docs/code-history/` の節に書く訂正の記録の `old:` / `new:` は、**コメント記号 `# ` を落とし、行の折り返しを連結した 1 行**で書く。`tools/check_comment_provenance.py` の `_apply_corrections` は、companion を `_flatten` した本文 (コメント記号を落とし行を連結したもの) に対して `old` の **1 件一致**を要求する。したがって `# ` 接頭や折り返しを含む断片を写すと 0 件一致になり、`FAIL (§9f) … old sentence occurs 0 time(s) in the basis (expected exactly 1)` になる。前例は `docs/code-history/MitateDB-api/http.md`:699 (CH-0208) と `docs/code-history/r2db-api/service.md`:409 である。

**WP-4a の初稿はこれを誤り、独立レビューだけが検出した。** HEAD の blob 同士でも同じ赤が出るので、記録に入れても 0f は赤のままであり、W4-4 (b) の来歴の証拠も W4-4 (c) の変異も成立しなかった。初稿時点の実装担当の報告「`tools/tests` の 1 赤は未コミットの新 leaf だけが理由」は実測に反していた (§1.5 の 34「主張は実測の後」)。**4b・4c・4d の 3 件とも CH-ID の塊に括弧書きを足すので、同じ落とし穴に掛かる** — 4b は §5.42 のとおり移動範囲に CH-0005・CH-0006・CH-0101 の 3 件があり、L271 の `below` へ括弧書きを付けるので **§CH-0101 に訂正の記録を書く**。4c は §5.43 の CH-0001 ほか、4d は §5.44 の CH-0054 ほかである。各 WP は、訂正の記録を書いた後に `python3 tools/check_comment_provenance.py --base <基点> <対象 src>` を走らせ、§9f が出ないことを確かめてから報告する。なお逐語写しの本文 (fence の中) は 1 文字も変えない (A-2 (4))。

**3. 完了条件と変異の追加 (独立コードレビュー 中-1。4b〜4d にも掛かる)**

§5.41 の完了条件に **16「operator は閉じた表から引き、閉語彙外は黙って既定値に落ちない」** を足し、変異 **M13** (`postgres_sql.py` の `_OPERATOR_SQL[item.operator]` を `_OPERATOR_SQL.get(item.operator, sql.SQL("="))` にする) を実測した。理由は、この変異が manifest の新規 4 本すべてを緑のまま通過したからである (完了条件 5 のテストは辞書の中身を pin するだけで、参照の閉じ方を pin しない)。設計 §5.1 の 2 が「正常値だけでなく、境界値、型違い、**閉語彙外、例外経路**を含める」を必須の証拠に挙げているので、これは設計外の拡張ではなく **manifest の取りこぼしの補充**である。あわせて、空の `in` 値 (`Filter("f","in",[])`) を leaf 単体は `IN ()` に組み、防いでいるのは `cell.py`:3370 の「in filter requires values」で **leaf の外である**という分担の事実を、足した新規テストの docstring に 1 文書き留めた (40b の意図。挙動は変えない)。

**4b・4c・4d の新規テストにも、閉語彙外・例外経路の場面を 1 つ以上置く。**

これに伴う件数の更新: 4a の**完了条件は 15 → 16、変異は 12 → 13、新規テストは 4 → 5** である。**変異 13 の内訳は、実装担当 12 (M1〜M11 と M13)、監督 1 (M12、完了条件 12) である。**上の「新規テストの数 (C-2)」の行は 4a 4 / 計 18 であるが、**§1.8 の 56 のとおり消さず、本註で上書きする**: 実績は **4a 5 / 計 19** (4b 3・4c 5・4d 6 は未着手のまま) として読む。完了ゲートの期待値も `3421` → **`3422 passed, 2 subtests passed`** に変わり、実測はこの値である。

**4. 読み手を失ったものの検査 (差し戻し S-1。4b〜4d の完了条件に監査照合として足す)**

抽出 WP では、**移動によって読み手を失った import・定数・再 export が移動元に残っていないか**を、**移動前の HEAD と AST の参照件数を比較して**確かめる。手順は、`ast.Name` の参照件数を import 名ごとに数え、`git show HEAD` の同じ集計と比べて「移動が原因で 0 になったもの」だけを取り出す形である。

WP-4a では `MitateDB-api/src/mitatedb_api/backend_postgres.py`:90 の `from .backend import SQL_OPERATOR_TOKENS, UNCHANGED` のうち `SQL_OPERATOR_TOKENS` の 1 件が見つかり、第 2 次裁定 6 と同じ基準で削った (`UNCHANGED` は読み手 5 なので残した)。**suite でも変異でも検出されない種類の欠陥である** — 壊れるのは実行時の挙動ではなく、設計 D-1 の「依存グラフを細くする」という主張と、同じ変更セット内での裁定 6 の適用の一貫性、および後続 WP・WP-5 が引く前例である。**4b・4c・4d の完了条件に監査照合として足す。**

**5. `--base` の §4.1 の赤の読み方 (独立コードレビュー 低-2。4b〜4d にも掛かる)**

CH-ID を持たない塊が別ファイルへ移ると、`tools/check_comment_provenance.py --base <親>` は移動元で §4.1 の赤を出す。WP-4a では `backend_postgres.py`:130・:131 ほか 8 件で出た。これは m-7 の説明コメント (CH-ID 無し) の移動による**位置ずれ**によるものであり、**40c を満たしていても出る** (移動先 `postgres_sql.py` L20-24 と旧 L130-134 の逐語一致、本体の差が `self` 引数の除去 1 種だけであることは diff で確認済み)。**Z4-4 のとおり `--base` は来歴の証拠に使わない**ので、この赤は判定に使わない。完了条件 14 (逐語移動と位置参照) の監査照合の材料として記録する。

**既知の穴への追加 (WP-5 候補。移動前から存在。WP-4 の範囲外。R-39 候補)**

`MitateDB-api/src/mitatedb_api/backend_postgres.py` には WP-4a 以前から読み手 0 の import が **5 件**ある — `CONTRACT_TYPES`、`_INT_DOMAIN_RANGES`、`_check_domain`、`_RESERVED_EXACT`、`_RESERVED_PREFIX` (WP-4a の AST 参照件数の全件比較で確認。いずれも移動前から 0 件で、本 WP が読み手を失わせたものではない)。うち `_INT_DOMAIN_RANGES` と `_check_domain` の 2 件は、既存コメントが「re-exported for facade compatibility; not referenced elsewhere」と明記しており、意図的な facade 再 export である。残る `CONTRACT_TYPES`・`_RESERVED_EXACT`・`_RESERVED_PREFIX` の 3 件に同じ明記があるかは **WP-5 (facade 縮小と閉止) で確かめる**。設計 §4 の WP-5 は「export を消す場合は個別に根拠と回帰証拠を添え、通常の変更クラス判定を再実施する」と定めるので、**WP-4 では触らない。**

---

**訂正註 2026-09-16 (依頼者裁定。WP-4c と WP-4d を 1 つの WP にまとめる)**

**1. 依頼者裁定 (逐語。§1.7 の 51 のとおり再審議しない)**

> 4c・4dをまとめてください。

経緯: 監督が 1 WP あたりのコード変更の小ささと証拠作業の比率を報告し、「1 WP あたりの重さを軽くするか、残りの 4c・4d をまとめるかはご判断の余地がある」と示したことへの回答である。

**本裁定は Z4-2 の一部を覆す。** Z4-2 は「4 件の直列 WP に分ける。4a = BP3、4b = PG1、4c = PG3、4d = PG2 + `_bind_value`」と定め、§5.40 の却下した代替案は「PG2 と PG3 を 1 つの WP にまとめる」を「移動名が 8 になり、Z4-2 の理由に反する」として退けていた。**§1.8 の 56 のとおり Z4-2 とその根拠・却下理由の行は消さず、本註で上書きする。**Z4-1・Z4-3〜Z4-6・Z4-8 は変わらない。Z4-7 (直列。並行しない) も変わらない (件数だけが 4 件から 3 件になる)。

**2. 統合後の WP-4c の定義**

- **呼称は WP-4c** とし、§5.44 の「WP-4d」という呼称は以後使わない (統合後の WP-4c に含まれる)。
- **移動する 8 名**: PG3 の `_select_statement`・`_order_by_sql`・`_append_revision_predicate` (§5.43)、PG2 の `_COMPARISON_OPERATORS`・`_where_clause`・`_text_expression`・`_predicate_sql` と `_bind_value` (§5.44、Z4-3)。
- **移動先**: 新規 `r2db-api/src/r2db_api/postgres_sql.py` (Z4-8)。1 つの変更セットで新規作成し、8 名をまとめて置く。
- **着手条件**: **WP-4b の統合後**に着手する (`postgres.py`・`r2db-api/tests/test_foundation.py`・`r2db-api/tests/test_l1_details_vocabulary_ast_scan.py`・`tools/tests/test_leaf_import_direction.py` を共有するため。Z4-7)。行番号は 4b の統合後に取り直す (§5.40 と同じ)。
- **WP-4 は 4a → 4b → 4c の 3 件の直列**になる (Z4-2 の 4 件を 3 件に改める)。PG4 は Z4-1 のとおり範囲外である。
- **§5.45 の既存の訂正註 1〜5 (W4-4、訂正の記録の `old:`/`new:` の書式、閉語彙外・例外経路、読み手を失ったものの検査、`--base` の §4.1 の赤の読み方) は、統合後の WP-4c にもそのまま掛かる。**

**3. 実測 (§5.43 と §5.44 の実測欄を統合した 1 つの表)**

「統合の型」欄は、**1 回**=まとめたことで作業が 1 度で済む欄、**和**=2 つの manifest の値の和を取る欄、**据置**=どちらか一方にしか無く、そのまま持ち越す欄である。値はすべて §5.43・§5.44 の実測 (`ed265f4`) をそのまま引いたものであり、**着手時に 4b の統合後で取り直す。**

| 項目 | 統合後 (出所) | 統合の型 |
|---|---|---|
| 移動範囲 | **8 名、5 塊、計 154 行**。PG3 = L1280-1312 (`_select_statement` 26 行・`_order_by_sql` 6 行、間の空行を含む 33 行)、L1602-1625 (`_append_revision_predicate` 24 行) の 2 塊 57 行 (§5.43)。PG2 + `_bind_value` = L240-247 (`_COMPARISON_OPERATORS` 8 行)、L1525-1534 (`_bind_value` 10 行。C-2 の訂正後の値)、L1825-1903 (`_where_clause` 10 行・`_text_expression` 23 行・`_predicate_sql` 44 行、間の空行を含む 79 行) の 3 塊 97 行 (§5.44) | 和 |
| 飛び石 | §5.43・§5.44 の飛び石の指定をそのまま両方守る。L1313-1601 は動かさない (L1314 の `# ---- mutations ----` 以下)。L1823 の `# ---- predicate/WHERE composition ----` は facade に残し、その直後に PG2 側の委譲属性を置く。`_fail_client_value` (`def` は L1507。§3 の除外。C-3) には触らない | 和 |
| leaf の中の並び (監督裁定 2026-09-16) | **移動前の `postgres.py` での出現順をそのまま保つ。** 着手時の裁量を無くし、逐語移動 (40c) の照合を「出現順も含めて機械的に確かめられる」形にするためである。§5.43 の「leaf の中は `_select_statement` → `_order_by_sql` → `_append_revision_predicate` の順」はこの順に含まれる。**移動前後で出現順が一致することを完了条件 29 の監査照合に含める。** 移動前の実測の行番号は `_COMPARISON_OPERATORS` L240 / `_select_statement` L1280 / `_order_by_sql` L1306 / `_bind_value` L1525 / `_append_revision_predicate` L1602 / `_where_clause` L1825 / `_text_expression` / `_predicate_sql` (L1825-1903 の塊の中) である。**着手時に 4b の統合後で取り直した行番号の昇順で並べ、その一覧を報告に貼る** | 監督裁定 (1 回) |
| 本体の変更 | §5.43 の 3 種と §5.44 の 4 種の和。(a) 関数 7 つ (定数 `_COMPARISON_OPERATORS` を除く 7 名) から `self` 引数を除く、(b) `self._order_by_sql` (L1294) → `_order_by_sql`、(c) `_select_statement`・`_append_revision_predicate` に既定値の無い引数 `revision_column` を足し `_REVISION_COLUMN` (L1290・L1623) を置き換える (W4-1)、(d) `self._predicate_sql` (L1831) → `_predicate_sql`、(e) `self._text_expression` (L1880) → `_text_expression`、(f) `self._bind_value` (L1878・L1903) → `_bind_value`。`_order_by_sql`・`_append_revision_predicate`・`_text_expression`・`_bind_value` は `self` を 1 度も参照しない (実測)。差は W3-3・W3-12 と同じく列挙してログに残す | 和 |
| 列名定数の扱い (W4-1) | §5.43 のまま。`_REVISION_COLUMN` (L202) は動かさず、移動範囲の外の読み手 4 箇所 (L926・L1677・L1779・L2294。B-3 の訂正後の値) を保つ。facade の呼出し箇所 L1253 (`query`)・L1676 (`_update`)・L1695 (`_delete`)・L1791 (`_apply_upsert`) が `_REVISION_COLUMN` を渡す。`_ID_COLUMN` (L201) は 3 関数のいずれも読まない (実測)。着手時の実測で読んでいたら同じく既定値の無い引数で渡す | 据置 |
| facade に残すもの | **委譲属性 7 つ**。PG3 側 3 つ (`_select_statement`・`_order_by_sql`・`_append_revision_predicate`) と PG2 側 4 つ (`_where_clause`・`_text_expression`・`_predicate_sql`・`_bind_value`)。いずれも `= staticmethod(...)` の形 (WP-3i と同じ。Z4-3)。呼出し元は §5.43 の 4 箇所 (L1253・L1676・L1695・L1791) と §5.44 の L1252 (`query`)・L1581 (`_apply`)・`self._bind_value` の 6 箇所 (L1655・L1681・L1752・L1783・L1806・L2177) がそのまま動く (PG3 側は引数が 1 つ増える)。`_COMPARISON_OPERATORS` は移動後 `postgres.py` に読み手が残らない (module docstring L16 が名前で言及するだけ) ので、第 2 次裁定 6 に従う (読み手 0 を実測で示して削るか、再 export として残すか。削る場合は根拠と回帰証拠を WP 記録に添える) | 和 |
| leaf の新規作成 | 1 つの変更セットで 1 回だけ作る (§5.43 で作り §5.44 で足す 2 段階を 1 回にする) | 1 回 |
| `postgres.py` の import 行 | leaf からの import 行の編集は **1 回**(§5.43 の 1 行と §5.44 の 1 行を 1 回にまとめる) | 1 回 |
| leaf の import | §5.44 の集合をそのまま採る: `psycopg` (`from psycopg import sql`)、`typing` (`Any`)、`psycopg.types.json` の `Jsonb` (`psycopg` に正規化)、`.postgres_like` (`_escape_like_literal`)、`.errors` (`fail`・`violation`)。**許可集合は `{"psycopg", "typing", ".postgres_like", ".errors"}`** (§5.43 の `{"psycopg", "typing"}` との和)。`postgres.py` は import しない (循環)。`.postgres_like` は import を持たない 12 行の leaf で循環にならない (実測)。**`Predicate` は import しない** (W4-2。`from __future__ import annotations` の下で注釈は評価されない。`TYPE_CHECKING` も使わない。前例は `inmemory_predicate.py` L14 / L95。C-7) | 和 (1 行) |
| denial・件数 pin (Z4-6) | 移動範囲の 4-key denial は **2 件**。PG3 側は 0 件 (§5.43 の実測)、PG2 側が L1874 (`"Filter value is incompatible with the selected operator."`、`violation("request_schema", field="where")`) と L1902 (`"Unsupported filter operator."`、`violation("capability", field="where")`)、いずれも `_predicate_sql` の中 (§5.44)。**移動元 `postgres.py` は `counts` 辞書に含まれないので減算コメントを書かない。移動先は `counts` 辞書に `"postgres_sql.py": 2` を 1 回だけ足し、前例と同じ形の由来コメント (どの method が移す前に持っていた何件か) を添える** | 和 (追加は 1 回) |
| `SCANNED_MODULES`・sib tuple | `SCANNED_MODULES` (L84) に `postgres_sql.py` を **1 回**足す (40b)。§5.43 の「差分 0、追加は WP-4d で行う」は、統合により本 WP の中で行う。sib の固定 module 集合は in-memory 側の集合なので backend 層の `postgres_sql.py` は足さない (差分 0)。`test_backend_layer_allowlist_is_confined_to_postgres_py` の前提 (allowlist は `postgres.py` だけ) も変わらない | 1 回 |
| 行番号 allowlist (Z4-5) | `("postgres.py", 1523)` の更新は **1 回**。行送りの要因は §5.43 (L1280-1312 の削除、import 1 行と委譲属性の増減) と §5.44 (L240-247 の削除) の**両方**であり、**実測は合算後の値を取る**。L1525-1534 と L1602-1625・L1825-1903 は L1523 より下なので効かない。既存の前例と同じ形の行送りコメントを 1 件足す | 1 回 (実測は合算値) |
| CH-ID (Z4-4) | **8 件**が移動範囲にある。PG3 側 2 件 = CH-0026 (L1304、`_select_statement` の `OFFSET`/`LIMIT` のコメント)、CH-0045 (L1619、`_append_revision_predicate` の docstring)。PG2 側 6 件 = CH-0041 (L1528、`_bind_value` の docstring)、CH-0053 (L1854、`_text_expression` の docstring)、CH-0054 (L1877)、CH-0055 (L1885)、CH-0056 (L1890)、CH-0057 (L1901)。8 件とも `docs/code-history/r2db-api/postgres.md` に節がある (L599・L907・L850・L1046・L1074・L1087・L1102・L1114)。**節は動かさず**、`# history:` / `History:` の行を逐語で一緒に移す。`_COMPARISON_OPERATORS` (L240-247) に CH-ID は無い | 和 |
| 位置参照 (WF-5) — 付ける | **3 箇所**。(1) `postgres.py` L1271 の「… (`_select_statement`, below)」の `below` の直後に「(now in `postgres_sql.py`)」(この塊に CH-ID は無いので訂正の記録は書かない。直前の CH-0025 は L1264 の別の塊)。(2) module docstring L22-23 の `below` の直後に「(and in `postgres_sql.py`)」(**この塊は CH-0001 を持つ**ので §CH-0001 に §5.27 の形式の訂正の記録を書く。WF-5 (iv)、W3-22 の R2 の前例)。(3) CH-0054 のコメント L1866 の「both call sites of `_where_clause` (`query`/`_apply` above)」の `above` の直後に「(in `postgres.py`)」(**この塊は CH-0054 を持つ**ので §CH-0054 にも訂正の記録を書く。第 2 次裁定 5)。**訂正の記録は §CH-0001 と §CH-0054 の 2 件**である。§5.44 の「(2) は WP-4c が既に足しているので 4d では変えない」は、統合により**同じ変更セットで 1 回足す**と読む | 和 (2・3 は 1 回ずつ) |
| 位置参照 (WF-5) — 付けない | §5.43 と §5.44 の「付けない」一覧の和をそのまま守る。CH-0026 の「the same pattern `_set_timeouts` already uses」と同じ塊の「`sql.Literal` here」、`ApplicationCell._sort_key`・`bind_mutation`・`ApplicationCell` の名前 / 修飾名 (WF-5 (ii))、module docstring L16 の `_COMPARISON_OPERATORS` (名前だけ。**本 WP で移るが文は真のまま**)、CH-0057 の「`structured.OPERATORS` (now in `mutation_binding.py`)」(WP-3f で正しく直っており指す先は変わらない)、CH-0055 の `_validate_predicate_types`・CH-0041 の `ApplicationCell`・CH-0053 の `add_field`、`pg_text_format.py` L7 と `inmemory_predicate.py` L67・L79 の `PostgresCell._text_expression` (委譲属性で同じ修飾名から読める)、`r2db-api/tests/test_postgres.py` L1483 の「fallback in `_predicate_sql`」、`postgres.py` L2166 の「`_bind_value` (never a bare member)」、`docs/code-history/` の登録簿の節 (Z4-4)、`docs/work-orders/WORK_ORDER_CODE_COMMENT_PROVENANCE_CS1.md` の表。**「確かめたものとして記録する」扱いの件もそのまま引き継ぐ** | 和 |
| 新規テスト | **11 本** (§5.43 の 5 本 + §5.44 の 6 本)。いずれも `r2db-api/tests/test_foundation.py`。**§5.44 の「触るファイル」欄の「新規テスト 5 本」は §5.44 内部の誤記である** — 独立レビュー A-1 の 5 → 6 の訂正が §5.45 の「新規テストの数 (C-2)」の行だけに入り、同欄に及ばなかったもので、§5.44 の完了条件 1〜6 は 6 本とも新規テストである。**6 が正**とし、§1.8 の 57 のとおり §5.44 の本文は書き換えない | 和 |

**4. 触るファイル / 触らないファイル (§5.43 と §5.44 の和集合。互いに触るものは 触らない 側から除く)**

| 触るファイル (6) | 触らないファイル |
|---|---|
| `r2db-api/src/r2db_api/postgres.py` (移動範囲 5 塊、import 1 行、委譲属性 7 行、PG3 側の呼出し 4 箇所の引数、L1271 と module docstring の括弧書き)、新規 `r2db-api/src/r2db_api/postgres_sql.py` (8 名と import)、`r2db-api/tests/test_foundation.py` (新規テスト 11 本)、`r2db-api/tests/test_l1_details_vocabulary_ast_scan.py` (`SCANNED_MODULES`、`counts` 辞書、allowlist 1 件の行送りと行送りコメント)、`docs/code-history/r2db-api/postgres.md` (§CH-0001 と §CH-0054 の訂正の記録だけ)、`tools/tests/test_leaf_import_direction.py` (leaf 1 行と許可集合 1 行) | `structured.py`、`mutation_binding.py`、`postgres_types.py`、`postgres_like.py` (import するだけで編集しない)、`pg_text_format.py`、`inmemory_predicate.py`、`service.py`、`r2db-api/tests/test_postgres.py`、`r2db-api/tests/test_audit_query.py`、`conformance-tests/`、MitateDB-api 全部、`docs/design/`、roadmap |

**5. 完了条件 → 変異 → 赤になる test id (§5.43 と §5.44 の表の和から重複を除き、1 から振り直した)**

「出所」欄の `43-n` は §5.43 の完了条件 n、`44-n` は §5.44 の完了条件 n、`註-n` は §5.45 の訂正註 n、`枠-n` は本註の 6 の項目 n を指す。**「監督」と記した行は W4-4 (a)(d) により監督が実施する監査照合であり、実装担当は変異の `old` / `new` の spec を用意して報告するところまでを担当する。**

| # | 出所 | 完了条件 | 変異 (`file:操作`) | 赤になる test id (予想) | 実施 |
|---|---|---|---|---|---|
| 1 | 43-1 | facade 互換 (PG3 側の 3 委譲属性が leaf を指す) | `postgres.py`: `_select_statement = staticmethod(_select_statement)` の行を消す | `r2db-api/tests/test_foundation.py::test_postgres_sql_leaf_preserves_postgres_delegates` (新規) | 実装担当 |
| 2 | 44-1 | facade 互換 (PG2 側の 4 委譲属性が leaf を指す) | `postgres.py`: `_bind_value = staticmethod(_bind_value)` の行を消す | `r2db-api/tests/test_foundation.py::test_postgres_sql_leaf_preserves_predicate_delegates` (新規) | 実装担当 |
| 3 | 43-2 | SELECT 文の並び (列 + revision、FROM、WHERE、ORDER BY、OFFSET、LIMIT) が逐語 | `postgres_sql.py`: `"{base} OFFSET {offset} LIMIT {limit}"` の `OFFSET`/`LIMIT` の順を入れ替える | `::test_select_statement_is_composed_literally` (新規) | 実装担当 |
| 4 | 43-3 | 先読み 1 行 (`page_size + 1`) を取る | `postgres_sql.py`: `limit=sql.Literal(int(page_size) + 1)` を `int(page_size)` にする | 3 の新規テスト。`r2db-api/tests/test_postgres.py` の `has_more` を確かめる既存テスト | 実装担当 |
| 5 | 43-4 | ORDER BY の direction は固定リテラルの 2 値だけ | `postgres_sql.py`: `sql.SQL("ASC" if direction == "asc" else "DESC")` を `sql.SQL("ASC")` にする | `::test_order_by_sql_uses_only_fixed_direction_literals` (新規) | 実装担当 |
| 6 | 43-5 | revision 述語は `::text` の比較を placeholder で束縛する (W4-3) | `postgres_sql.py`: `ph=sql.Placeholder()` を `ph=sql.SQL(expected_revision)` にする | `::test_append_revision_predicate_binds_the_expected_revision` (新規) | 実装担当 |
| 7 | 43-6 | `expected_revision` が `None` のときは述語も params も変えない | `postgres_sql.py`: `if expected_revision is None:` を `if False:` にする | 6 の新規テスト | 実装担当 |
| 8 | 43-7 | leaf は列名を既定値の無い引数で受け、module 定数を読まない (W4-1) | `postgres_sql.py`: `revision_column` の引数に既定値 `= "_r2db_revision"` を足す | `::test_postgres_sql_takes_column_names_as_required_arguments` (新規) | 実装担当 |
| 9 | 44-2 | 比較演算子は閉じた表の固定リテラルだけ | `postgres_sql.py`: `_COMPARISON_OPERATORS` の `"ne": sql.SQL("<>")` を `sql.SQL("=")` にする | `::test_comparison_operators_are_literal` (新規) | 実装担当 |
| 10 | 44-3 | 述語の値は placeholder 経由でしか SQL に入らない (W4-3) | `postgres_sql.py`: `sql.SQL("{col} {op} {ph}")` の `ph=sql.Placeholder()` を、値を埋めた `sql.SQL(...)` に置換する | `::test_predicate_sql_never_inlines_a_value` (新規) | 実装担当 |
| 11 | 44-4 | `contains` は LIKE のワイルドカードを escape し、`matches` はしない | `postgres_sql.py`: `escaped = _escape_like_literal(predicate.value)` を `escaped = predicate.value` にする | `::test_predicate_sql_escapes_only_contains_patterns` (新規) | 実装担当 |
| 12 | 44-5 | 型なし列の text 表現は `#>> '{}'`、型つきは `::text` | `postgres_sql.py`: `_text_expression` の `if field_type is None:` を `if False:` にする | `::test_text_expression_unwraps_only_untyped_columns` (新規) | 実装担当 |
| 13 | 44-6 | 値の束縛 (`None` → SQL NULL、型なし / `object` / `array` → `Jsonb`、それ以外は素の値) | `postgres_sql.py`: `if field_type is None or field_type in ("object", "array"):` から `"array"` を外す | `::test_bind_value_wraps_only_json_shaped_columns` (新規) | 実装担当 |
| 14 | 44-7 | 移した 2 件の denial が 4-key のまま | `postgres_sql.py`: L1902 相当の `fail("VALIDATION_FAILED", "Unsupported filter operator.", details=violation("capability", field="where"))` から、部分文字列 `, details=violation("capability", field="where")` だけを取り除く (行は残す。現物は 1 行で末尾カンマも無い — B-1) | `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py::test_every_choke_point_denial_carries_details_ast_full_count`、`::test_allowlist_entries_match_real_bare_call_sites` | 実装担当 |
| 15 | 44-8 (43-11 を吸収) | 移動先が `SCANNED_MODULES` に入る (40b) | `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py`: `SCANNED_MODULES` から `postgres_sql.py` を外す | `::test_every_module_with_a_vocabulary_denial_is_accounted_for` | 実装担当 |
| 16 | 44-9 | 件数 pin (`postgres_sql.py` 2。移動元は pin されない。Z4-6) | `postgres_sql.py`: 4-key の `fail("VALIDATION_FAILED", …, details=violation(…))` を持つ孤立した関数を 1 つ足す (**import は足さない**。B-2) | `::test_ast_full_count_matches_the_audit_site_count` (`{'postgres_sql.py': 3} != {'postgres_sql.py': 2}`) | 実装担当 |
| 17 | 43-8 = 44-10 | 行番号 allowlist の行送り (40b、Z4-5) | `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py`: 更新した `("postgres.py", <実測値>)` を WP-4b の値に戻す | `::test_allowlist_entries_match_real_bare_call_sites` | 実装担当 |
| 18 | 43-9 = 44-11 | leaf の import が許可リストの内だけ | `postgres_sql.py`: `import os` を 1 行足す | `tools/tests/test_leaf_import_direction.py::test_leaf_modules_import_only_their_allowlisted_modules` | 実装担当 |
| 19 | 44-12 | leaf は注釈対象の型を import しない (W4-2。注釈対象は `_predicate_sql(predicate: Predicate, …)` と `_where_clause(where: list[Predicate], …)` の 2 箇所。C-8) | `postgres_sql.py`: `from .structured import Predicate` を 1 行足す | `tools/tests/test_leaf_import_direction.py::test_leaf_modules_import_only_their_allowlisted_modules` | 実装担当 |
| 20 | 43-10 = 44-13 | 新 leaf が分類される | `tools/tests/test_leaf_import_direction.py`: 一覧から `postgres_sql.py` の行を消す | `::test_every_src_module_is_classified` | 実装担当 |
| 21 | 43-12 | CH-ID が塊と一緒に移る (PG3 側の 2 件) | `postgres_sql.py`: `_append_revision_predicate` の `History: CH-0045` を `History: CH-0026` に差し替える | 記録した HEAD で `tools/tests/test_comment_provenance.py::test_0f_both_peers_all_src_rev_vs_itself_is_green` | **監督** |
| 22 | 44-14 | CH-ID が塊と一緒に移る (PG2 側の 6 件) | `postgres_sql.py`: `_predicate_sql` の `# history: CH-0057` を `# history: CH-0056` に差し替える | 同上 | **監督** |
| 23 | 43-13 | §CH-0001 の訂正の記録 (WF-5 (iv)) | `docs/code-history/r2db-api/postgres.md`: §CH-0001 に足した訂正の記録を消す | 同上 | **監督** |
| 24 | 44-15 | §CH-0054 の訂正の記録 (WF-5 (iv)) | `docs/code-history/r2db-api/postgres.md`: §CH-0054 に足した訂正の記録を消す | 同上 | **監督** |
| 25 | 43-14 + 44-16 + 枠-1・枠-2 | 手順 0 の走査 (§5.40)。**8 名を一括ではなく名前ごとに走査し、名前ごとの件数と `file:line` を報告に分けて貼る**。あわせて `_REVISION_COLUMN`・`_ID_COLUMN` も走査する。**分類 (「付ける」「付けない」) の無い参照が 1 件でもあれば止まる** (W3-23 の逸脱を前例にしない) | **監査照合**: 名前ごとの実行コマンドと出力を報告に貼り、設計 §10 に残す。分類の無い参照が 0 件であること | — | 実装担当 |
| 26 | 枠-3 | 独立コードレビューが、手順 0 の走査を実装担当とは別に自分でやり直す (WP-4a で実際に機能した) | **監査照合**: 独立レビューが自分で流した走査の実行コマンドと出力を、実装担当の報告と突き合わせた結果を差し戻し文書に残すこと | — | 独立レビュー |
| 27 | 43-15 + 44-17 | 本体は列挙した差を除き同一 | **監査照合**: 上の「本体の変更」欄の (a)〜(f) の 6 種を戻した leaf の本体が、移動前と AST で一致する。差の列挙をログに残す | — | 実装担当 |
| 28 | 註-4 | 移動によって読み手を失った import・定数・再 export が移動元に残っていない | **監査照合**: `ast.Name` の参照件数を import 名ごとに数え、移動前の HEAD (`git show HEAD`) の同じ集計と比べ、「移動が原因で 0 になったもの」だけを取り出す。見つかったものは第 2 次裁定 6 と同じ基準で扱い、根拠と回帰証拠を記録に添える | — | 実装担当 |
| 29 | 43-16 + 44-18 + 監督裁定 (leaf の中の並び) | 逐語移動と位置参照 (40c)、**および出現順の保存** | **監査照合**: docstring・コメント・`# history:` 行が逐語。括弧書きは上の「付ける」3 箇所 (L1271、module docstring、CH-0054 の L1866) だけであること。**あわせて、leaf の 8 名の出現順が移動前の `postgres.py` での出現順と一致することを、移動前の HEAD の行番号順の一覧と leaf の定義順の一覧を並べて示す** | — | 実装担当 |
| 30 | 43-17 + 44-19 (前半) | 同型・統合 | **監査照合**: `_ISOMORPHIC_TARGETS` の差分 0 (WF-1)、WF-4、WF-6 | — | 実装担当 |
| 31 | 43-17 + 44-19 (後半)、W4-4 (a)(b)(d) | 来歴の証拠 | **監査照合 (監督が実施)**: 監督が `tools/dev/finalize.py --no-merge` で WP branch に記録し、**その HEAD で `tools/tests` を流して 0f の集計行を取る**。使い捨て clone は使わない。緑を確かめてから統合する。`--base <親>` の §4.1 の赤は判定に使わない (Z4-4、訂正註 5) | — | **監督** |
| 32 | §1.5 の 40 (**両 manifest の欠落の補充**) | 上の表に、対応する変異も監査照合も無い完了条件の行が 1 つも無い | **監査照合**: 1〜31 の各行に「変異」または「監査照合」が入っていることを照合し、結果を報告に貼る | — | 実装担当 |

**件数 (下限)**: **完了条件 32 件** = 変異 24 件 (実装担当 20 = 1〜20、監督 4 = 21〜24) + 監査照合 8 件 (25〜32。うち 31 は監督、26 は独立レビュー)。**新規テスト 11 本。**

完了条件 32 は §5.43・§5.44 のどちらにも無く、両 manifest の和を 1 件超える。これは規律 §1.5 の 40 がすべての WP に必須とする行の**欠落の補充**であり、統合によって増やしたものではない。**32 / 24 / 11 はいずれも着手時の下限である** (下の 7 を見よ)。

**6. まとめたことによる危険と、その打ち消し (完了条件として明記した項目)**

Z4-2 の理由 (1 WP あたりの移動名が増えると範囲外の位置参照を取りこぼす。WP-3e〜3i では独立レビューだけが順に 3・8・1・5・2 件を見つけた) は本裁定でも消えていない。したがって次の 4 つを完了条件に置いた。

1. **手順 0 の走査は、8 名を一括ではなく名前ごとに行い、名前ごとの件数と `file:line` を報告に分けて貼る** (完了条件 25)。一括の走査は、名前ごとの取りこぼしを集計の中に隠す。
2. **分類の無い参照が 1 件でもあれば止まる** (完了条件 25 の後段)。W3-23 の逸脱を前例にしない。
3. **独立コードレビューは、手順 0 の走査を実装担当とは別に自分でやり直す** (完了条件 26)。WP-4a で実際に機能した。
4. **CH-ID は PG3 側 (CH-0026・CH-0045 と範囲外の CH-0001) と PG2 側 (CH-0041・CH-0053〜CH-0057) の両方が入るので、訂正の記録も両方書く** (完了条件 23・24)。§5.45 の訂正註 2 (`_flatten` 後の 1 行で書く) がそのまま掛かる。

**7. 件数の更新 (§1.8 の 56 のとおり、既存の行を消さずに本註で上書きする)**

- §5.45 の「**新規テストの数 (C-2)**」の行 (「4a 4、4b 3、4c 5、4d 6、**計 18**」) と、訂正註 3 の上書き (「実績は **4a 5 / 計 19**」) は、**いずれも消さずに残す**。本註で次のとおり読む: **4a 5 (実績) / 4b 3 (未着手) / 統合後の 4c 11 (未着手、下限) の 3 件、計 19 (下限)。**総数の下限 19 は変わらず、内訳が 4 件から 3 件になる。
- **完了ゲートの期待値**: **WP-4b の統合後の集計行 + 11 (下限)**。**監督は完了ゲートの直前に、実装担当が実際に足した新規テストの数を確かめてから期待値を出す。**絶対値は 4b が未統合のため本註では書かない (訂正註 3 が記した WP-4a 統合時点の実測は `3422 passed, 2 subtests passed` である)。R-44 側の新規テストと同時に動くので、期待値は統合の直前に main を取り込んでから出す (§5.40)。
- **完了条件・変異の実績の記録**: 統合後の WP-4c の実績 (下限である完了条件 32・変異 24・新規テスト 11 に対する実測) は、設計 `docs/design/MODULE_REFACT_ARCHITECTURE_V1.md` §10 の WP-4c 実施記録に書く (§10.16 の WP-4a 実施記録と同じ形)。
- **件数は固定値ではなく下限である (監督裁定 2026-09-16)。**訂正註 3 の「閉語彙外・例外経路の場面を新規テストに 1 つ以上置く」は統合後の WP-4c にも掛かり、**PG2 の経路と PG3 の経路それぞれに新しい場面を要求しうる**。WP-4a では同じ指摘 (独立コードレビュー 中-1) で完了条件が 15 → 16、変異が 12 → 13、新規テストが 4 → 5 に増えた。したがって **完了条件 32・変異 24・新規テスト 11 は着手時の下限**であり、**実装担当は訂正註 3 を満たすために必要なら足す。監督は完了ゲートの直前に実際の新規テスト数を確かめてから期待値を出す。**

**8. §5.45 の既存の訂正註との関係**

§5.45 の訂正註 **1〜5** (W4-4 の 4 裁定、訂正の記録の `old:`/`new:` の書式、閉語彙外・例外経路の完了条件と変異、読み手を失ったものの検査、`--base` の §4.1 の赤の読み方) は、**統合後の WP-4c にもそのまま掛かる** (それぞれ完了条件 21〜24・31、7 の項、25〜32 の表、28、31 に織り込んである)。

---

---

**訂正註 2026-09-16 (WP-4b の実装と独立コードレビュー)。上の本文・表・裁定・訂正註はいずれも当時の原文であり、消さずに残す (`OPERATING_CONDITIONS.md` §1.8 の 57)。下の 6・7 は上の訂正註 1〜5 の番号を継ぐものであり、**統合後の WP-4c (§5.43 + §5.44) に掛かる**。**

**6. 閉語彙外・例外経路の完了条件の強化 (訂正註 3 の上書き。独立コードレビュー 中-1。WP-4c に掛かる)**

訂正註 3 は「**4b・4c・4d の新規テストにも、閉語彙外・例外経路の場面を 1 つ以上置く**」と書いた。**この書き方では足りない。assertion を足すだけでは満たせない**ことが、WP-4a と WP-4b の **2 回続けて**明らかになった。原因は 2 回とも同じで、**既存の等値 assertion に論理的に含意される assertion を足していた**ことである (§1.5 の 32 の空振り)。

- WP-4a: 完了条件 5 のテストは `_OPERATOR_SQL` の中身を pin するだけで、参照の閉じ方を pin しなかった。`_OPERATOR_SQL[item.operator]` → `.get(item.operator, sql.SQL("="))` の変異が新規 4 本すべてを緑のまま通過した (完了条件 16 と変異 M13 を足して補充)。
- WP-4b: 足した 2 行 (`assert "_r2db_json_unknown" not in _DOMAIN_TO_DECLARED`・`assert "smallint" not in _SQL_TYPE_TO_DECLARED`) は、直前の `==` による辞書全体の固定に含意される。呼出し側 `r2db-api/src/r2db_api/postgres.py`:891 の `_SQL_TYPE_TO_DECLARED.get(data_type)` → `.get(data_type, "string")` の変異が**新規 3 本とも緑で素通り**した。**独立レビューが自作変異で実証して初めて分かった。**

**以後、閉語彙外・例外経路の完了条件は次を満たす。**

1. **番号付きの変異を 1 つ持つ。**完了条件の表に `file:操作` と赤になる test id を書き、他の完了条件と同じ形で番号を振る。監査照合にしない。
2. **実装担当がその変異を当てて赤になった実測を報告に添える** (`tools/dev/mutate.py` の `expect=red got=red OK` の行)。§1.5 の 32 (「X を壊す変異を赤にした実測を添える」) を**この条件に明示的に掛ける**。assertion を足しただけで満たしたことにしない。
3. **テストは、断言が及ぶ経路 (呼出し側を含む) を実際に実行する。**それが難しい場合は、AST で**呼出しサイトの形**を固定する (WP-4b は `postgres.py` を `ast` で読み、2 つの `.get` 呼出しの引数が 1 個であること = 既定値を取らないことを固定した)。**表・定数・辞書の中身を pin するだけのテストでは足りない。**
4. **テストの docstring は、テストが実際に固定する範囲までしか断言しない** (§1.5 の 34)。WP-4b の初稿は呼出し側の fallback まで断言しながら、呼出し側を 1 行も実行していなかった。

これに伴う件数の更新: **4b の完了条件は 13 → 14、変異は 8 → 9 である** (内訳は実装担当 9 = M1〜M9、監督 2 = S1・S2 の計 11 変異 + 監査照合 3)。新規テストは 3 本のまま (差し替えで対応した)。上の「新規テストの数 (C-2)」の行と訂正註 3 の上書き行は、§1.8 の 56 のとおり消さず、本註で次のとおり読む: **4a 5 (実績) / 4b 3 (実績) / 統合後の 4c 11 (未着手、下限)。** WP-4b の完了ゲートの期待値は 4a 統合後の `3422` + 3 = **`3425 passed, 2 subtests passed`** であり、実測はこの値である。**統合後の WP-4c の期待値は `3425` + 実際の新規テスト数 (下限 11) であり、監督は完了ゲートの直前に実数を確かめてから出す** (依頼者裁定の訂正註 7 の項のとおり、件数は下限である)。

**7. 0f の読み方の非対称 (W4-4 (c) の枝の実測。WP-4c に掛かる)**

`tools/tests/test_comment_provenance.py::test_0f_both_peers_all_src_rev_vs_itself_is_green` は、**src を記録済みのツリーから読み、companion (`docs/code-history/` の登録簿) を作業ツリーから読む。**この非対称の帰結は次の 2 つである。

- **companion 側の変異は、作業ツリーのままで赤になる。**WP-4a の M12 (CH-0340 の訂正の記録を消す) と WP-4b の S1 (§CH-0101 に足した訂正の記録を消す) はいずれも作業ツリーで赤になった (S1: `expect=red got=red OK | 1 failed in 3.27s | restore=ok`)。
- **src 側の来歴の変異 (`# history:` / `History:` の ID 差し替え等) は、記録しない限り 0f に見えない。**作業ツリーで当てても**緑のまま通る**。WP-4b の S2 (`r2db-api/src/r2db_api/postgres_types.py`:61 のコメント側の `# history: CH-0005` → `# history: CH-0006`) は `expect=red got=green NG | 1 passed` であった。**なお実際に回した S2 は、§5.42 の完了条件 9 が書いた spec (docstring 側の `History: CH-0006` → `History: CH-0005`) とは当てた場所も向きも異なる。守る性質は同じ**であり、**記録には実際に回したほうを書く** (§1.5 の 34)。

**W4-4 (c) はこの枝を想定している** (「0f が作業ツリーの companion を読まず git から読む形であれば、その場で判明するので、その場合は捨て branch 上の記録で取り直し、結果を記録する」)。**src 側の来歴を固定する完了条件は、次の手順で赤を確認する。**

1. W4-4 (b) のとおり `tools/dev/finalize.py --no-merge` で WP branch に記録し、その HEAD で `tools/tests` の 0f が緑であることを確かめる (来歴の証拠)。
2. その HEAD の上に**捨てコミット**を作り、変異を当てた状態で `tools/tests` を回して 0f が赤になることを確かめる。WP-4b では捨てコミット (当日は `c6bbe30`) で `1 failed, 11 passed, 234 deselected` を得た。**この SHA は 3 の `reset --hard` で到達不能になるので、当日の実施の記録としてのみ残す。再現は SHA ではなく変異の内容で書く** — WP-4b の場合は「`postgres_types.py`:61 の `# history: CH-0005` を `# history: CH-0006` に差し替えたものを記録した HEAD の上の捨てコミットに載せ、0f を回す」である。
3. `git reset --hard <記録した HEAD>` で戻し、**§1.4 の 30 のとおり `sleep` の後に sha256 を 2 回照合して一致、変異文字列の全文 grep 0 件、作業ツリーがクリーンであることを確かめる。**
4. 作業ツリーで緑だったことと、捨てコミット上で赤だったことの**両方**を記録に残す。**「作業ツリーで緑だった」を「変異が効かない」と読み違えない。**

**統合前の `tools/tests` の 1 赤の読み方も同じ機構である。** 変更した src がまだ記録されていない間は、記録済みのツリーから読む src 側と作業ツリーの companion 側が食い違うので、**新 leaf を作らない WP でも 0f の 1 件が赤になる** (WP-4b の統合前は `1 failed, 485 passed`、記録後の HEAD では `486 passed`)。この 1 赤を §9f 起因と読み違えない (訂正註 2 の落とし穴)。§9f が出ていないことは `python3 tools/check_comment_provenance.py --base <基点> <対象 src>` で別に確かめる (WP-4b は `--base bec2eeb` で **§9f 0 件**。残る 9 件はすべて §4.1 の位置ずれで、訂正註 5 のとおり判定に使わない)。

**あわせて: 移動先 module 自身の docstring の扱い (独立コードレビュー 中-2。WP-4c に掛かる)。** §5.4x の「本体の変更は無し」は**移動する塊についての条件**であり移動先 module の header docstring は対象外なので、**移動によってその docstring が偽になったら、その WP で直す** (§1.5 の 34。WP-4b は `postgres_types.py`:1-6 の「it only maps … to a psycopg SQL composition object」が逆写像 2 本と `_TableInfo` の流入で偽になったため直した。CH-ID を持たない塊なので `--register` と 0f には影響しない)。

**訂正註 8 (2026-09-16。WP-4c の実施と独立コードレビュー)。上の本文・表・裁定・訂正註はいずれも当時の原文であり、消さずに残す (`OPERATING_CONDITIONS.md` §1.8 の 57)。番号は訂正註 1〜7 を継ぐ。本註は 7 項目 (8-1〜8-7) から成り、次の訂正註は 9 から始める。**

**本註の 7 項目はいずれも WP-5 (facade 縮小と閉止) に掛かる。**WP-4 は本 WP で完了したので、WP-4a〜4c に掛かる項目としての効力は終わっている。実施の記録は設計 `docs/design/MODULE_REFACT_ARCHITECTURE_V1.md` (v1.21) §10.18 である。

**8-1. §4.1 (5) は R-37 の抽出 WP にも掛かる。例外を作らない (独立コードレビュー 中-2)**

抽出 WP が src へ足す**新しいコメントに `WP-` / `R-` の経緯トークンを入れない**。WP-4c では `postgres.py`:109-110 の新規コメントが `-- R-37` / `# WP-4c)` を含み、`python3 tools/check_comment_provenance.py --base <基点>` が `FAIL (§4.1 (5)) … added line carries a history token` を出した。根拠は (i) 設計 `docs/design/CODE_COMMENT_PROVENANCE_V1.md` §4.1 (5) が**追加行の経緯トークンを名指しで禁じている**こと、(ii) すぐ下の CH-0002 の同趣旨コメント (`postgres.py`:116) が経緯トークンを持たない**前例**であること、(iii) WP-4a・WP-4b はどちらも src に経緯トークンを足していないこと、(iv) R-22 のコメント整理は経緯トークンを消していく作業であり、その最中に src へ新しい `WP-` を入れると後続の変更セットに手間を生むことである。

**0f は rev-vs-itself なので追加行を持たず、この赤を構造的に捕まえない。`--base` でしか出ない。****訂正註 5 の「`--base` の §4.1 の赤は判定に使わない」を、§4.1 の赤すべてに広げて読んではならない。**§4.1 の赤は**類型ごとに分けて読む** (8-2 を見よ)。

**8-2. `--base` の §4.1 には構造的に必ず出る類型がある (独立コードレビュー 低-5)**

WP-4c の `--base` の §4.1 は 21 件で、内訳は **19 件が訂正註 5 の類型** (位置ずれ・CH-ID 塊の移動・新ファイルの `git show` 不能)、**1 件が 8-1 の真の赤**、**1 件が `postgres.py`:1 の `CH-0001 basis block … not derivable`** であった。最後のものは、**`--base` が旧 blob を basis に取る一方で、訂正の記録は新しい本文に合わせて書かれる**ために必ず出る構造的なもので、0f (src を記録済み HEAD から読む) では出ない。

**完了条件の証拠は 0f である** (統合後の manifest の完了条件 31、W4-4 (b))。`--base` は判定に使わないが、**§9f が 0 件であることの確認**と、**8-1 の (5) の検出**には使う。

**8-3. `_order_by_sql` の閉語彙外の direction が黙って `DESC` になる (独立コードレビュー 低-4。R-39 候補)**

`r2db-api/src/r2db_api/postgres_sql.py` の `_order_by_sql` は `sql.SQL("ASC" if direction == "asc" else "DESC")` であり、**閉語彙外の direction を拒否せず `DESC` に落とす**。**移動前から同じ挙動**であり、変えれば挙動の変更になる (設計 §1.1 の不変の公開意味に触れる) ので **WP-4 の範囲外**とした。**既知の穴として記録し、行き先は R-39 の候補**である。WP-5 でも挙動は変えない。

**8-4. 訂正註 4 (読み手を失ったものの検査) の適用範囲 (監督裁定 1)**

訂正註 4 の検査を**移動元 module の中だけで行うのでは足りない**。**その module を facade として読む外部のファイル (テストを含む) も確認対象に含める。**WP-4c では `_escape_like_literal` の import を消して `r2db-api/tests/test_postgres.py`:1175 の facade テストが赤になった (`1 failed, 1306 passed` → 復元後 `1307 passed`)。`postgres.py` 内の `ast.Name` の参照件数だけでは 0 に見えたためである。復元し、import は **facade 再 export として残した**。

**WP-5 (facade 縮小と閉止) に最も強く掛かる** — WP-5 は export の削除そのものを扱うので、同じ穴が最も効く WP である。

**8-5. 完了条件 24 (§CH-0054 の訂正の記録) は無効である (監督裁定 2)**

**WF-5 (iv) の適用は「括弧書きを足す塊が CH-ID を持つか」で決まり、近くの塊が CH-ID を持つかでは決まらない。**§CH-0054 に登録されている塊は「`# R-7, corrigendum m-7: each element gets the same per-column type-aware bind …`」であり、括弧書きを足した文「both call sites of `_where_clause` (`query`/`_apply` above)」を**含まない**。後者は `_predicate_sql` の中の別の塊で `ch_id=None` である (実装担当と独立レビューの双方が `extract_all_blocks` で実測)。統合後の manifest の完了条件 24 は**起草時に塊の単位を取り違えていた**ので、**前提が成り立たず無効**とした。WP-4c の訂正の記録は §CH-0001 の 1 件だけである。

**WP-5 の manifest は、位置参照の行を書くときに「括弧書きが入る塊自身の CH-ID」を `extract_all_blocks` の実測で確かめてから書く。**

**8-6. docstring のインデントの差を「本体の変更」の 4 種目として認める (監督裁定 3)**

class の method (8 スペース) から module の関数 (4 スペース) へ移すと、**docstring のインデントが移動に内在して変わる**。これは 40c の「本文を言い換えない」に反しない。**「本体の変更」の列挙に 4 種目として加え、`inspect.cleandoc` 正規化後に AST で完全一致することを監査照合の材料にする** (W3-3・W3-12 の「差分の列挙で示す」と同じ扱い)。WP-4c では独立レビューが 7/7 完全一致、5 種目の差なしを実測した。

**8-7. 新規ファイルを足す WP では、その走査がどう列挙するかを実測する**

「新規ファイルも走査に見えているはず」は**検査の目的についての推測**であって、**列挙の行を読むまでは事実ではない**。

- **`rglob` / `glob` 系** (ファイルシステム列挙) は**未追跡の新規ファイルも見る**。WP-4c が関わる 3 つはすべてこれである (監督実測): `tools/tests/test_leaf_import_direction.py`:301 の `src_root.rglob("*.py")`、`r2db-api/tests/test_l1_details_vocabulary_ast_scan.py`:601 の `SRC.rglob("*.py")`、`tools/tests/test_comment_provenance.py`:2834 (0f) の `base.glob("*.py")`。
- **`git ls-files` 系**は**追跡されるまで見ない**。`tools/public_value_scan.py` のツリーモード (§2 の 7) と、R-44 が新設した `tools/tests/test_no_shared_cluster_defaults.py` がこれである。
- **この違いは不統一ではなく、検査の目的の反映である**: 「公開されるものに何が入っているか」を見る検査は `git ls-files` が筋であり (未追跡はまだ公開の対象ではない)、「コードが実際にどう依存しているか」を見る検査は `rglob` が正しい。
- **`tools/tests` は root suite の外なので `gate.py` では 1 本も走らない** (`tools/tests/pytest.ini` が根であり `testpaths` の外)。走るのは `finalize.py --tools-tests` の段である。**したがって、この層の赤はゲートが緑で通った後に出る。**手前で確かめるには `tools/dev/pt.py -C <worktree> --wait 1800 -- tools/tests -q` を回す。
- **W4-4 (b) の手順がこの穴を塞いでいる**: `finalize.py --no-merge` で**記録してから** `tools/tests` を回すので、その時点で新規ファイルは必ず追跡済みであり、`git ls-files` 系の検査も正しく見える。**穴が残るのは「記録する前に手で `tools/tests` を回し、その集計行を正本にする」経路だけである** (別セッションが実際に踏み、レビューに指摘された)。

### 5.46 WP-5 — facade 縮小と閉止 (R-37 の最後の WP。v1.22 追記、**独立設計レビュー反映済み**)

**【依頼者指示 2026-09-16 により範囲を縮小】** `docs/work-orders/REQUESTER_DIRECTIVE_20260916_R37_CLOSURE_R45_PRIORITY.md` §3.1・§5: 行うのは Z5-1 の (3)(4)(6) だけで、完了条件は (3)(4)(6) に掛かる行だけが有効。(1)(2)(5) と Z5-9〜Z5-13・Z5-15〜Z5-23 の対象は行わない。(3) の再照合は全追跡ファイルへの文字列 grep に置き換えた。実施記録は設計 `docs/design/MODULE_REFACT_ARCHITECTURE_V1.md` §10.19。

**枠**: 引き継ぎ書 `docs/work-orders/HANDOVER_20260916_FABLE2.md` 付録 B (監督が確定。問題設定・守るべき条件・実測 A〜F・裁定 Z5-1〜Z5-8・却下した代替案) を前提に読む。本節は枠を言い換えず、実測 A〜F は同付録の記号で指す。正本設計は `docs/design/MODULE_REFACT_ARCHITECTURE_V1.md` §1.1・§1.2・§3.2・§4 の WP-5 節・§5・§6・§7。§5.45 の訂正註 1〜8 はすべて掛かる (訂正註 8 は 8-1〜8-7 とも WP-5 に掛かると明記している)。

**監督裁定 (Z5-1〜Z5-8。同付録からの逐語)**:

| # | 裁定 | 根拠 |
|---|---|---|
| Z5-1 | **WP-5 の範囲は次の 6 つ。**(1) **SQL 安全性の静的走査の新設** (設計 D-4 が要求し、W4-3 が WP-5 へ送ったもの)、(2) **循環 import の静的検査の新設**、(3) **真に読み手 0 の import 2 件の削除**、(4) **残る再 export を「意図的な facade 互換」として記録**、(5) **読み手検査の偽陰性 (文字列注釈) の手当て**、(6) **R-37 の閉止記録** | (1) は設計 D-4 の「client-influenced statement が plain `str` で到達できない性質を新 module を含む走査で確認する」に対応する機構が 0 件。(2) は設計 §4 WP-5 の「import graph を確認する」の機械化された形で、現在は静的テストが無い |
| Z5-2 | **テストの削除は行わない。**重複候補 1 件は **R-39 候補として記録** | 設計 §5.3 は `COLLECTION_FLOOR` が「大幅な収集減の検知器であって、テストを削除していない証明ではない」と述べ、実測では削除を検出する道具が無い。**削除の根拠より、削除を検出する手段が無いことのほうが重い** |
| Z5-3 | **SQL 安全性の走査は SQL キーワードの文字列一致で作らない。**AST で「execute の choke point に到達する値がどう構築されたか」を見る形にする | 監督実測: キーワード一致だと `r2db-api/src/r2db_api/delete_confirmation.py`:127・138・163・243 の削除確認の句 (利用者が打ち込む文字列で SQL ではない) と `MitateDB-api/src/mitatedb_api/ops.py`:798 のエラーメッセージが偽陽性になる |
| Z5-4 | **削除する読み手 0 の import は 2 件だけ** (`CONTRACT_TYPES`、`config.py` の `build_surfaces`)。**他の候補は削らない** | 上の A の再照合。facade identity test が読むもの・facade 明記があるものは削れない |
| Z5-5 | **読み手検査 (訂正註 4) の偽陰性を手当てする。**文字列注釈を扱うか、扱えないことを明記して手作業の照合を完了条件にする | WP-4 が確立した検査手法そのものの穴であり、WP-5 の削除判断がこの手法に依存する |
| Z5-6 | **Class B。**`_ISOMORPHIC_TARGETS` に触れない (差分 0 を完了条件にする)。`spec/`・`security/`・`conformance-tests/` に触れない | 削除は peer の private な import 2 件、新設は `tools/tests/` のテスト |
| Z5-7 | **1 つの WP として行う** (依頼者の統合の方針に沿う)。**完了条件は (1)〜(6) ごとに分ける** | 依頼者裁定「4c・4dをまとめてください。」の方針。規模は WP-4c より小さい |
| Z5-8 | **新設する 2 つの走査は走査対象を両 peer の `src/` に明示的に限る。**peer のディレクトリ全体を `rglob` しない | `7cd1d80` が `MitateDB-api/docs/f9-execution-assets-v1/` に `.py` 3 件を置いた。レビューされていない参照用コードで、`MitateDB-api/` を `rglob` すると判定に混ざる |

**監督裁定 (第 2 次、2026-09-16、Z5-9〜Z5-14。起草時の疑義への裁定。`wp5-rulings-1.md` からの逐語)**:

| # | 裁定 |
|---|---|
| Z5-9 | (choke point の名前の重複) choke point は **module の修飾名 + クラス名 + メソッド名**で引く (例: `r2db_api.postgres` の backend クラスの `_run`)。裸の関数名で引かない。 |
| Z5-10 | (走査範囲) Z5-3 の「choke point に到達する値」を、D-4 の性質 (client-influenced statement が plain str で到達できない) に合わせて**psycopg を import する両 peer `src/` module の全 `.execute(` / `.executemany(` 呼び出し**へ広げる。第 1 引数が次のいずれかなら許可: (a) 文字列リテラル (静的 SQL)、(b) `sql.SQL(<文字列リテラル>)`・`sql.Identifier` / `sql.Literal` / `sql.Placeholder` と、それらの `.format()` / `.join()` / `+` による合成、(c) 上の (a)(b) だけから作られた module 定数、(d) choke point の引数 (呼び出し元で同じ規則が掛かる)。それ以外 (f-string、`%`、`str +`、`sql.SQL(<非リテラル>)`) は赤。判定できない既存箇所は**理由付きの明示許可表 + 件数 pin** に置き、実装担当は件数と理由を報告する (監督が採否を裁定)。`backend_sqlite.py` は PostgreSQL ではないので走査外とし、理由を書く。 |
| Z5-11 | (変異) (1) の変異に次を足す: `sql.SQL(<f-string>)` を choke point に渡す一時呼び出し → 赤、直接 `.execute(` へ f-string を渡す一時呼び出し → 赤。plain str だけの変異は実行時ガードと重なるので単独では足りない。 |
| Z5-12 | (循環 import) graph は**関数内 import と `TYPE_CHECKING` 下の import を含む全辺**で循環 0 を assert する (閉止条件の「依存方向」を最も強く固定する。現状は含めても 0)。将来の意図的な例外は監督裁定を要すると書く。 |
| Z5-13 | ((5) 文字列注釈) **第一案を採る。**ただし恒久テストにはせず、WP-5 の読み手検査スクリプト (scratchpad) が文字列注釈を parse して読み手に数える。空振り防止として、既知の文字列注釈の読み手 (`MitateDB-api/src/mitatedb_api/http.py`、`audit_query.py` — 関数名で引く) がスクリプトで読み手として数えられることを実装担当が実測して報告する。この確認を完了条件 14 の「監査照合」とする。 |
| Z5-14 | (削除と 40a) §1.5 の 40a を削除にも準用する: (3) のコミット前に両 peer の suite の集計行を記録する。 |
| (番号なし) | 新規テスト 2 件のファイル名は起草案のとおりでよい。 |

- **Z5-13 の「完了条件 14」は起草時の番号である。**裁定の反映で表を振り直したので、第 2 次の表では**完了条件 18** に当たった (裁定の文言は逐語のまま残す。第 3 次の番号は下の第 3 次裁定の註を見よ)。

**監督裁定 (第 3 次、2026-09-16、Z5-15〜Z5-21。設計レビューの指摘 高 2・中 5・低 2 への対応。`wp5-rulings-2.md` からの逐語)**:

| # | 裁定 |
|---|---|
| Z5-15 | (Z5-9 の訂正註) Z5-9 の例「backend クラスの `_run`」は誤り。両 choke point は module 直下の関数であり、修飾名は **module + 関数名** (`r2db_api.postgres._run`、`mitatedb_api.backend_postgres._execute`) で引く。Z5-9 の本文は残し、本項を訂正註として置く。 |
| Z5-16 | (高 1) Z5-10 の規則 (a)〜(d) を**データの流れを追わない 2 本立て**に置き換える (Z5-10 の本文は残し、本項で覆す)。規則 1: 走査 module 内のすべての `sql.SQL(...)` の引数は、**静的に文字列リテラルへ畳める式**に限る — 文字列リテラル、リテラル同士の `+`、同じ関数内または module 内の全代入がそれ自体静的に畳める名前。呼出し位置を問わない。規則 2: すべての実行呼出し (下の Z5-17) の第 1 引数に、f-string・`%` 書式・`str` の `+` 連結・`.format()` を**直接**置かない (`sql.SQL` / `sql.Composed` の `.format()` / `.join()` は除く)。規則で畳めない既存箇所は理由付きの明示許可表 + 件数 pin。実装担当は件数と理由を報告し、採否は監督が裁定する。レビュー実測で問題になった `sql.SQL(base_statement + "…")` 4 件と `sql.SQL(<module 定数>)` 3 件は、規則 1 で畳めるかを実装担当が実測する。 |
| Z5-17 | (高 2) 「実行呼出し」は `.execute(` / `.executemany(` と、次の名前付き関数の呼出しを指す: 両 choke point (Z5-15) と、同名の wrapper 4 つ (MitateDB `mitatedb_api.control_plane`・`mitatedb_api.credential_store_postgres`・`mitatedb_api.control_credential_store_postgres` の `_execute`、r2db `r2db_api.credential_store` の `_execute`)。いずれも修飾名で列挙し、規則 2 を呼出し側に掛ける。 |
| Z5-18 | (中 1) 走査対象は両 peer の `src/` 配下の**全 module を AST で発見**し、`backend_sqlite.py` だけを理由付きで名指し除外する (psycopg を import するかで絞らない)。発見した集合を pin する。変異 8 は「発見の結果から 1 module を落とす」、変異 10 は「psycopg を import しない新規 module に、引数の cursor へ f-string を渡す実行呼出しを置く」にする。 |
| Z5-19 | (中 2・中 3・低 2) 変異 10 の tests は構築形テストの node id 1 本に絞る。変異 6 は psycopg を import する module (例 `r2db-api/src/r2db_api/ops.py`) に、実行呼出しに渡らない f-string の SQL 風文字列を足す形 (緑の期待) にする。`.format()` の引数の中の `sql.SQL(<f-string>)` を赤にする変異を 1 件足す。 |
| Z5-20 | (中 4) import graph の作り方を明記する: `from . import X` は submodule X に解決する。親 package の暗黙の import は辺に数えない。関数内・`TYPE_CHECKING` 下の import も辺に数える (Z5-12)。根拠欄に設計 §5.1 の 1 (全 WP に「循環 import がない静的照合」) を足す。 |
| Z5-21 | (中 5・低 1) Z5-4 の再照合の範囲を「`git ls-files` の全 `.py` (`MitateDB-api/docs/f9-execution-assets-v1/` の 3 件を除く) と `docs/code-history/`」にする (両 peer の `conformance/` と各 `conftest.py` を含む)。「完了条件 15」の残りを 19 に直す。 |

- **覆した項**: Z5-9 の例は Z5-15 が訂正する。Z5-10 の許可規則 (a)〜(d) は Z5-16 が覆し、Z5-10 の「psycopg を import する … module」の絞り込みは Z5-18 が覆す (Z5-10 の `backend_sqlite.py` の走査外と、明示許可表 + 件数 pin は Z5-16・Z5-18 で引き継がれる)。第 2 次の行はいずれも消さずに残す (§1.8 の 56)。
- **裁定の中の番号**: Z5-18・Z5-19 の「変異 6・8・10」は第 2 次の表の番号であり、下の表ではそれぞれ**完了条件 8・10・12** に当たる。Z5-21 の「19 に直す」は第 2 次の表の番号であり、下の表では**完了条件 22** に当たる。Z5-13 の「完了条件 14」は下の表の**完了条件 21** に当たる (裁定の文言は逐語のまま残す)。

**基点**:

- 実測 A〜F の基点は main `2ed3a3d` (付録 B)。本 manifest の基点は main `abcb2b6` である。`2ed3a3d..abcb2b6` で main へ入ったのは文書、`MitateDB-api/docs/f9-execution-assets-v1/` の参照用ファイル、`tools/public_value_scan.py` の許可追加だけであり (起草時に `git diff --name-only 2ed3a3d..abcb2b6` で照合)、両 peer の `src/`・`tests/` に触れていない。**したがって A〜F の実測は src について有効である。**
- **完了条件 (3) の前提**: 実装担当は着手時に、A の 2 件 (`MitateDB-api/src/mitatedb_api/backend_postgres.py`:95 の `CONTRACT_TYPES`、`MitateDB-api/src/mitatedb_api/config.py`:8 の `build_surfaces`) を再照合する。照合は訂正註 4 の検査を訂正註 8-4 の範囲 (その module を facade として読む外部のファイル。テストを含む) で行い、あわせて 2 名を `git ls-files` の全 `.py` (`MitateDB-api/docs/f9-execution-assets-v1/` の 3 件を除く。両 peer の `conformance/` と各 `conftest.py` を含む) と `docs/code-history/` で名前ごとに走査して (Z5-21)、件数と `file:line` を報告に貼る (§5.40 の手順 0 の形)。**付録 B の A と食い違う参照が 1 件でもあれば、そこで止まって監督へ上げる。**文字列注釈の扱いは (5) に従うので、**(5) は (3) より先に行う** (Z5-5 の根拠「WP-5 の削除判断がこの手法に依存する」)。

**変更クラスと範囲**: Class B (Z5-6)。`_ISOMORPHIC_TARGETS` の差分 0。`spec/`・`security/`・`conformance-tests/` に触れない。**テストは削除しない** (Z5-2)。`tools/tests` は root suite の `testpaths` の外であり、**`gate.py` では 1 本も走らない** (訂正註 8-7)。新設の 2 テストは `tools/dev/pt.py … -- tools/tests` と `finalize.py --tools-tests` の段でだけ走る。

| 触るファイル | 触らないファイル |
|---|---|
| `MitateDB-api/src/mitatedb_api/backend_postgres.py` (L95 の import から `CONTRACT_TYPES` の 1 名を外すだけ)、`MitateDB-api/src/mitatedb_api/config.py` (L8 の import から `build_surfaces` の 1 名を外すだけ)、新規 `tools/tests/test_sql_statement_safety_scan.py` ((1)。ファイル名は起草案のとおり。第 2 次裁定)、新規 `tools/tests/test_src_import_cycles.py` ((2)。ファイル名は起草案のとおり。第 2 次裁定) | `spec/`、`security/`、`conformance-tests/`、両 peer の `tests/test_audit_query.py` (`_ISOMORPHIC_TARGETS`)、`r2db-api/src/` 全部 (変異の一時編集を除く)、`r2db-api/tests/`、`MitateDB-api/tests/`、`MitateDB-api/docs/f9-execution-assets-v1/`、`tools/tests/test_leaf_import_direction.py`、`docs/code-history/`、`docs/design/`、roadmap (記録は監督) |

- src の変更は import 行の名前の削除 2 件だけであり、コメント・docstring を変えない。したがって位置参照の括弧書きと `docs/code-history/` の訂正の記録は生じない。src に経緯トークンを足さない (訂正註 8-1)。
- **新規ファイルの列挙方法の実測 (訂正註 8-7)**: 新設する 2 テストが `src/` の module をどう列挙するか (`rglob` / `glob` 系か `git ls-files` 系か) を、実装したコードの該当行 (`file:line`) で報告に書く。完了条件 12 の変異の赤が作業ツリーで見えるかどうかはこの実測で決まる。

**新規テストの数**: root collection の増分は **0** (新設は `tools/tests` だけ。削除 0)。完了ゲートの期待値は**直前の main の root 集計行と同数**である。`tools/tests` の増分は実装担当が実際に足した node id の数であり、監督は統合の直前に collect-only で確かめる。

**実行するコマンド** (`WT` は監督が割り当てる worktree、`SP` は scratchpad。**実装担当は suite 全体・`conformance-tests`・`gate.py` を回さない** — 引き継ぎ書 `docs/work-orders/HANDOVER_20260916_FABLE2.md` §6 の最後の項。変異の spec は完了条件表の変異 1 行につき 1 件):

```bash
tools/dev/pt.py --wait 1800 -C "$WT" -- tools/tests/test_sql_statement_safety_scan.py tools/tests/test_src_import_cycles.py -q
tools/dev/pt.py --wait 1800 -C "$WT" -- tools/tests -q
tools/dev/pt.py --wait 1800 -C "$WT" -- MitateDB-api/tests -q     # (3) の削除の前と後
tools/dev/pt.py --wait 1800 -C "$WT" -- r2db-api/tests -q         # (3) の削除の前と後
tools/dev/mutate.py "$SP/wp5-mutations.json" -C "$WT" --wait 1800
tools/dev/gate.py -C "$WT" --label wp5                            # 監督のみ。run_in_background
```

spec の形の例 (完了条件 3。`old` は着手時に対象ファイルで 1 件一致する行を選ぶ):

```json
{"pytest": ["-q", "tools/tests/test_sql_statement_safety_scan.py"],
 "mutations": [
  {"id": "M3", "expect": "red",
   "file": "MitateDB-api/src/mitatedb_api/backend_postgres.py",
   "old": "<1 件一致する既存行>",
   "new": "<既存行>\ndef _wp5_mutant(cursor, table):\n    _execute(cursor, f\"SELECT * FROM {table}\")\n",
   "tests": ["tools/tests/test_sql_statement_safety_scan.py"]}]}
```

#### (1) SQL 安全性の静的走査 (Z5-1 (1)、Z5-3、Z5-8〜Z5-11、Z5-15〜Z5-19)

- 形: AST で、SQL の構築形を見る (Z5-3)。SQL キーワードの文字列一致で作らない。**データの流れは追わない** (Z5-16)。
- 走査対象 (Z5-18): 両 peer の `src/` 配下の**全 module を AST で発見**し、発見した集合を pin する。psycopg を import するかで絞らない。`MitateDB-api/src/mitatedb_api/backend_sqlite.py` だけを、理由 (PostgreSQL ではない) を書いて名指しで除外する。走査の根は両 peer の `src/` に明示的に限る (Z5-8)。
- 規則 1 (Z5-16): 走査 module 内のすべての `sql.SQL(...)` の引数は、静的に文字列リテラルへ畳める式に限る。呼出し位置を問わない。
- 規則 2 (Z5-16): すべての実行呼出しの第 1 引数に、f-string・`%` 書式・`str` の `+` 連結・`.format()` を直接置かない (`sql.SQL` / `sql.Composed` の `.format()` / `.join()` は除く)。
- 実行呼出し (Z5-17): `.execute(` / `.executemany(` と、修飾名で列挙した 6 関数 — choke point `r2db_api.postgres._run`・`mitatedb_api.backend_postgres._execute` (Z5-15。裸の関数名で引かない) と wrapper `mitatedb_api.control_plane._execute`・`mitatedb_api.credential_store_postgres._execute`・`mitatedb_api.control_credential_store_postgres._execute`・`r2db_api.credential_store._execute` — の呼出し。
- 規則で畳めない既存箇所は、理由付きの明示許可表と件数 pin に置く。**実装担当は許可表の件数と各行の理由を報告し、採否は監督が裁定する** (Z5-16)。レビュー実測の `sql.SQL(base_statement + "…")` 4 件と `sql.SQL(<module 定数>)` 3 件は、規則 1 で畳めるかを実装担当が実測して報告する。
- 空振り禁止 (§1.5 の 32): 各 peer について、`sql.SQL(...)` と各実行呼出し (6 関数と `.execute(` / `.executemany(`) を 1 件以上観測したことを assert する。
- 実測 B のとおり、両 choke point は `isinstance(statement, (sql.SQL, sql.Composed))` の実行時ガードを持つ。plain `str` の変異だけではこのガードと重なるので、`sql.SQL(<f-string>)`・`.format()` の引数の中の `sql.SQL(<f-string>)`・直接 `.execute(` の変異を併せて置く (Z5-11、Z5-19)。
- 触ってよいパス: `tools/tests/test_sql_statement_safety_scan.py` (新規)。変異の一時編集は下表のとおり。

#### (2) 循環 import の静的検査 (Z5-1 (2)、Z5-8、Z5-12、Z5-20)

- 形: 両 peer の `src/` の import graph を AST で組み、**関数内 import と `TYPE_CHECKING` 下の import を含む全辺**で循環が 0 であることを assert する (Z5-12)。観測した module 数と edge 数が 1 以上であることも assert する (§1.5 の 32)。走査対象は両 peer の `src/` に明示的に限る (Z5-8)。
- graph の作り方 (Z5-20): `from . import X` は submodule X に解決する。親 package の暗黙の import は辺に数えない (両 peer の `__init__.py` は submodule を import するので、数えると現状の src で循環が出る — 起草時の実測)。
- 根拠 (Z5-20): 設計 §5.1 の 1 (全 WP に「循環 import がない静的照合」) と、付録 B の Z5-1 の根拠。
- **将来の意図的な例外 (循環を許す辺) は監督裁定を要する** (Z5-12)。テストの docstring にもその旨を書く。
- **設計の範囲についての監督の見立て (付録 B の「独立設計レビューで見てもらう点」から逐語)**: 「**(2) の循環 import 検査が、設計 §4 の「import graph を確認する」の範囲に収まるか** (§1.5 の 37 の設計外の拡張に当たらないか)。監督の見立ては「範囲内」 — 一度きりの手作業の確認は変異を対応付けられず (§1.5 の 33)、閉止条件の「依存方向」を持続的に保てるのはテストの形だけであるため。」**独立設計レビューはこの点を見る。**
- 触ってよいパス: `tools/tests/test_src_import_cycles.py` (新規)。変異の一時編集は下表のとおり。

#### (3) 読み手 0 の import 2 件の削除 (Z5-1 (3)、Z5-4)

- 削除は `CONTRACT_TYPES` (`backend_postgres.py`:95) と `build_surfaces` (`config.py`:8) の **2 件だけ**。他の候補 (facade identity test が読むもの、facade 明記があるもの) は削らない (Z5-4)。
- 前提: 上の「基点」の再照合と (5) の完了。
- **§1.5 の 40a を削除にも準用する** (Z5-14): (3) のコミット前に両 peer の suite の集計行を記録する。
- **回帰証拠**: 削除の前と後で、両 peer の suite と `tools/tests` を `tools/dev/pt.py` で回し、4 本の集計行 (前後 × 2 peer と `tools/tests`) を報告に貼る (設計 §4 WP-5 の「export を消す … 場合は個別に根拠と回帰証拠を添え」)。根拠は再照合の出力である。
- 触ってよいパス: `MitateDB-api/src/mitatedb_api/backend_postgres.py`・`MitateDB-api/src/mitatedb_api/config.py` (各 import 行の 1 名だけ)。

#### (4) 残る再 export の記録 (Z5-1 (4))

- 削らずに残す再 export を、module・名前・残す根拠 (facade identity test の `file:line`、または facade 明記コメントの `file:line`) の一覧にして報告に貼る。実測 A が挙げた `_RESERVED_EXACT`/`_RESERVED_PREFIX` (`MitateDB-api/tests/test_postgres.py`:1666-1670 が読む) と `_INT_DOMAIN_RANGES`/`_check_domain` (facade 明記) を含める。実測 C の委譲属性 (`staticmethod` 委譲。r2db `postgres.py` 7・MitateDB `backend_postgres.py` 1・`cell.py` 3) も同じ一覧に置く。
- 変異を持たない。**監査照合** (完了条件 20)。記録先は設計 `docs/design/MODULE_REFACT_ARCHITECTURE_V1.md` §10 の WP-5 実施記録 (監督が書く)。

#### (5) 読み手検査の偽陰性 (文字列注釈) の手当て (Z5-1 (5)、Z5-5、Z5-13)

実測 A の既知の限界 (文字列注釈は `ast.Name` に現れない。該当: `MitateDB-api/src/mitatedb_api/http.py`:17・486、`MitateDB-api/src/mitatedb_api/audit_query.py`:32・228・280・391) に対し、**第一案を採る** (Z5-13)。

- WP-5 の読み手検査スクリプト (scratchpad に置く。恒久テストにしない) が、注釈位置 (引数・戻り値・`AnnAssign` の annotation) にある `ast.Constant` の `str` を式として parse し、現れる名前を読み手として数える。
- 空振り防止: 既知の文字列注釈の読み手 (`http.py`・`audit_query.py`。**関数名で引く**) がスクリプトで読み手として数えられることを実装担当が実測し、関数名・名前・件数を報告に貼る。**監査照合** (完了条件 21)。
- 触ってよいパス: scratchpad のスクリプトだけ (repo には置かない)。
- (起草時に両論で置いた第二案 (扱えないことを明記して手作業で照合する) は Z5-13 により採らない。)

#### (6) R-37 の閉止記録 (Z5-1 (6))

- 設計 §4 WP-5 の閉止条件 (「line count は成果指標ではなく、責務・依存方向・回帰証拠が閉止条件である」) に対する記録を残す。変異を持たない。**監査照合** (完了条件 22)。記録は監督が行う (設計 §10 と roadmap R-37)。照合対象は完了条件 22 の行に列挙する (Z5-21)。

**完了条件 → 変異 → 赤になる test id** (第 3 次裁定で振り直した。以下「構築形テスト」は `tools/tests/test_sql_statement_safety_scan.py` の規則 1・2 を assert する新規テストの node id 1 本、「pin テスト」は同ファイルの発見集合・許可表の件数を assert する新規テストを指す)

| # | 枠 | 完了条件 | 変異 (`file:操作`) | 赤になる test id (予想) | 実施 |
|---|---|---|---|---|---|
| 1 | (1) | 実行呼出しを修飾名で引き (Z5-15、Z5-17)、各 peer で `sql.SQL(...)` と実行呼出しを 1 件以上観測する (空振り禁止) | `tools/tests/test_sql_statement_safety_scan.py`: 修飾名 `r2db_api.postgres._run` を存在しない名前に差し替える | 同ファイルの観測件数の assert (新規) | 実装担当 |
| 2 | (1) | 規則 2: r2db の choke point に f-string を直接渡したら赤 | `r2db-api/src/r2db_api/postgres.py`: `_run(cursor, f"SELECT … {x}")` を行う一時関数を 1 つ足す | 構築形テスト | 実装担当 |
| 3 | (1) | 規則 2: MitateDB の choke point に f-string を直接渡したら赤 | `MitateDB-api/src/mitatedb_api/backend_postgres.py`: `_execute(cursor, f"SELECT … {x}")` を行う一時関数を 1 つ足す (spec の例は上) | 構築形テスト | 実装担当 |
| 4 | (1) | 規則 1: `sql.SQL(...)` の引数は静的に畳める式に限る (Z5-16) | 3 件。`r2db-api/src/r2db_api/postgres.py`・`MitateDB-api/src/mitatedb_api/backend_postgres.py`: それぞれ `sql.SQL(f"SELECT … {x}")` を choke point に渡す一時関数を足す。`r2db-api/src/r2db_api/postgres.py`: 一時関数の中で `q = "SELECT 1"` の後に `q = f"SELECT {x}"` と再代入し、`sql.SQL(q)` を作る (全代入が静的でない名前) | 構築形テスト | 実装担当 |
| 5 | (1) | 規則 1 は呼出し位置を問わない: `.format()` の引数の中の `sql.SQL(<f-string>)` も赤 (Z5-19) | `MitateDB-api/src/mitatedb_api/backend_postgres.py`: `sql.SQL("SELECT {} FROM t").format(sql.SQL(f"{x}"))` を choke point に渡す一時関数を足す | 構築形テスト | 実装担当 |
| 6 | (1) | 規則 2: choke point を通らない直接の `.execute(` に f-string が渡ったら赤 (Z5-17) | 2 件。`r2db-api/src/r2db_api/ops.py`・`MitateDB-api/src/mitatedb_api/ops.py`: それぞれ `cursor.execute(f"SELECT … {x}")` を行う一時関数を足す | 構築形テスト | 実装担当 |
| 7 | (1) | 規則 2 は同名の wrapper 4 つの呼出しにも掛かる (Z5-17) | `r2db-api/src/r2db_api/credential_store.py`: `_execute(cursor, f"SELECT … {x}")` を行う一時関数を足す | 構築形テスト | 実装担当 |
| 8 | (1) | SQL キーワードの文字列一致で作らない (Z5-3。実行呼出しに渡らない SQL 風の f-string は赤にしない) | `r2db-api/src/r2db_api/ops.py` (psycopg を import する module): どの実行呼出しにも渡らない f-string の SQL 風文字列 (`f"SELECT … FROM {x}"`) を 1 つ足す。**`expect: green`** (Z5-19。2〜7 の赤と対にして、判定が構築形で決まることを示す) | 構築形テストが緑のまま | 実装担当 |
| 9 | (1) | 走査の根は両 peer の `src/` に限る (Z5-8) | `tools/tests/test_sql_statement_safety_scan.py`: MitateDB の走査の根を `MitateDB-api/src` から `MitateDB-api` に広げる (`MitateDB-api/docs/f9-execution-assets-v1/` の `.py` 3 件が混ざる) | pin テスト | 実装担当 |
| 10 | (1) | `src/` の全 module を AST で発見し、`backend_sqlite.py` だけを理由付きで除外した集合が pin されている (Z5-18) | 2 件。`tools/tests/test_sql_statement_safety_scan.py`: 発見の結果から 1 module を落とす。名指し除外から `backend_sqlite.py` を外す | pin テスト | 実装担当 |
| 11 | (1) | 規則で畳めない既存箇所の明示許可表が理由付きで件数 pin されている (Z5-16) | `tools/tests/test_sql_statement_safety_scan.py`: 許可表から 1 行を外す (許可表が 0 件なら、存在しない箇所を指す行を 1 つ足す) | pin テストまたは構築形テスト | 実装担当 |
| 12 | (1) | 新しい module を、psycopg を import しなくても走査する (設計 D-4「新 module を含む走査」、Z5-18、訂正註 8-7) | 両 peer のいずれかの `src/` に **psycopg を import しない**新規 module を 1 つ足し、引数の cursor へ f-string を渡す実行呼出し (`cursor.execute(f"SELECT … {x}")`) を置く | **構築形テストの node id 1 本だけを tests に指定する** (Z5-19)。列挙が `git ls-files` 系なら作業ツリーでは見えないので、実測した列挙方法を報告に書き、監督が §5.45 の訂正註 7 の手順 (記録した HEAD の上の捨てコミット) で赤を確かめる | 実装担当 (列挙が `git ls-files` 系なら監督) |
| 13 | (2) | r2db の `src/` に循環 import が無い (module 先頭の import) | `r2db-api/src/r2db_api/postgres_sql.py`: 先頭に `from .postgres import _run` を 1 行足す | `tools/tests/test_src_import_cycles.py` の循環 0 の assert (新規) | 実装担当 |
| 14 | (2) | MitateDB の `src/` に循環 import が無い (module 先頭の import) | `MitateDB-api/src/mitatedb_api/postgres_sql.py`: 先頭に `from .backend_postgres import _execute` を 1 行足す | 13 と同じ | 実装担当 |
| 15 | (2) | 関数内 import と `TYPE_CHECKING` 下の import も辺に数える (Z5-12) | 2 件。`r2db-api/src/r2db_api/postgres_sql.py`: 既存の関数の本体の先頭に `from .postgres import _run` を足す。`MitateDB-api/src/mitatedb_api/postgres_sql.py`: `if TYPE_CHECKING:` の下に `from .backend_postgres import _execute` を足す (`TYPE_CHECKING` の import を含む) | 13 と同じ | 実装担当 |
| 16 | (2) | `from . import X` は submodule X に解決し、親 package の暗黙の import は辺に数えない (Z5-20) | 2 件。`r2db-api/src/r2db_api/platform_upgrades.py`: `from . import ops` を 1 行足す (`ops.py` は `from . import platform_upgrades` を持つ) → 赤。`tools/tests/test_src_import_cycles.py`: 各 module から親 package (`__init__`) への辺を足す形に変える → 現状の src で赤 | 13 と同じ | 実装担当 |
| 17 | (2) | 走査対象は両 peer の `src/` に限り、module 数・edge 数を 1 以上観測する (Z5-8、空振り禁止) | 2 件。`tools/tests/test_src_import_cycles.py`: 列挙から 1 module を外す。MitateDB の根を `MitateDB-api` に広げる | `tools/tests/test_src_import_cycles.py` の集合または件数の pin (新規) | 実装担当 |
| 18 | (3) | `backend_postgres.py` から削るのは `CONTRACT_TYPES` だけで、読み手のある再 export は残す (Z5-4) | `MitateDB-api/src/mitatedb_api/backend_postgres.py`: 対照として `_RESERVED_EXACT` を import から外す | `MitateDB-api/tests/test_postgres.py::test_postgres_reserved_names_leaf_preserves_backend_postgres_facade` | 実装担当 |
| 19 | (3) | `config.py` から削るのは `build_surfaces` だけで、読み手のある名前は残す (Z5-4) | `MitateDB-api/src/mitatedb_api/config.py`: 対照として `validate_data_base_url` を import から外す | `MitateDB-api/tests/test_config.py::test_from_env_accepts_a_well_formed_data_base_url` (着手時に赤の実測で確かめる) | 実装担当 |
| 20 | (4) | 残る再 export と委譲属性を「意図的な facade 互換」として記録する | **監査照合**: (4) の一覧 (module・名前・根拠の `file:line`) を報告に貼り、設計 §10 に残す | — | 実装担当 (記録は監督) |
| 21 | (5) | 読み手検査が文字列注釈で偽陰性にならない (Z5-13) | **監査照合**: scratchpad の読み手検査スクリプトが、既知の文字列注釈の読み手 (`http.py`・`audit_query.py`。関数名で引く) を読み手として数えた実測 (実行コマンド、関数名・名前・件数) を報告に貼り、設計 §10 に残す | — | 実装担当 |
| 22 | (6) | R-37 の閉止記録 | **監査照合**: 次をすべて設計 §10 の WP-5 実施記録と roadmap R-37 に残す。(a) 完了条件 1〜19 の `mutate.py` の出力行、(b) (3) の削除前後の集計行 (Z5-14 のとおり、コミット前の両 peer の suite の集計行を含む)、(c) `_ISOMORPHIC_TARGETS` の差分 0 (Z5-6)、(d) `spec/`・`security/`・`conformance-tests/` の差分 0 と `tools/change_class.py` の判定 (Class B)、(e) §1 の取得コマンドによる node id 一覧の前後 diff が `tools/tests` の新規テストだけで、削除 0 であること (Z5-2、設計 §5.3)、(f) 実測 D の重複候補 1 件 (`_escape_like_literal`) を R-39 候補として記録したこと (Z5-2)、(g) root gate の集計行が直前の main と同数であること、(h) 記録した HEAD での `tools/tests` の集計行 (W4-4 (b))、(i) (1) の明示許可表の件数・理由と監督の採否 (Z5-16)、(j) (3) の再照合の実行コマンドと出力 (Z5-21) | — | **監督** |
| 23 | §1.5 の 40 | 上の表に、変異も監査照合も無い完了条件の行が 1 つも無い | **監査照合**: 1〜22 の各行に「変異」または「監査照合」が入っていることを照合し、結果を報告に貼る | — | 実装担当 |

**件数 (下限)**: 完了条件 23 件 = 変異を持つ行 19 件 (1〜19。変異は 25 件 — 4 は 3 件、6・10・15・16・17 は各 2 件、8 は `expect: green`) + 監査照合 4 件 (20〜23。22 は監督)。§5.45 の訂正註 6 のとおり、実装担当は変異が素通りする場面を見つけたら足す。

---

## 6. 重なり表と監督裁定

**触るパスの重なり** (○ = 重なりなし。× = 重なりあり、直列。L = `tools/tests/test_leaf_import_direction.py`):

| | WP-1-0 | WP-1a | WP-1b | WP-1c | 変更セット 0 (`ccp-cs0`) | 変更セット 1 |
|---|---|---|---|---|---|---|
| WP-1-0 | — | × L | × L | × L | ○ | ○ |
| WP-1a | × | — | × L | × L、`structured.py`、`r2db-api/tests/test_foundation.py` | ○ | ○ (別 module。L81 のコメントは触らない) |
| WP-1b | × | × | — | × L | ○ | ○ |
| WP-1c | × | × | × | — | ○ | ○ (L1430 のコメントは触らない) |

- 変更セット 1 は `r2db-api/src/r2db_api/postgres.py`、`r2db-api/tests/test_l1_details_vocabulary_ast_scan.py`、`tools/check_comment_provenance.py`、`docs/code-history/r2db-api/postgres.md` を触る。変更セット 0 の `tools/tests` のファイルは `test_comment_provenance.py` で、L と別である。
- 並行 worktree `mitatedb-operation-depth-platform-plan` の作業指示書は運用手順だけで、`src/` に触れない (起草時点)。着手時に再確認する。

**監督裁定 (2026-09-14)**:

| # | 裁定 | 反映先 |
|---|---|---|
| U-1 / U-2 | 同じファイルで抽出とコメント整理の変更セットを同時に行わない。r2db `postgres.py` はコメント整理 (変更セット 1) が先。`structured.py`・`cell.py`・MitateDB `backend_postgres.py` は抽出が先で、コメント整理は後にファイル単位で行う。抽出で移す docstring・コメントは 40c で逐語に移し、経緯の整理は後の変更セットで行う | §1、§2.3、§2.5、§4、§5 |
| U-2 (追記 2026-09-14) | r2db `service.py` はコメント整理 (変更セット 2) を先に行い、R-37 WP-3 (SV1〜SV3) は後にする。並行しない (監督裁定、変更セット 2 の作業指示書 §5.1 と対) | §2.4、§4、§5.14 |
| U-3 | ST1 は `pg_text_format.py` (float8out を含むため)。削除確認 phrase の helper は両 peer とも `delete_confirmation.py` (CE1 と後の ST5)。他は提案名で進め、独立レビューで確認する | §2、§5 |
| U-4 | `fold_operation_idempotency_keys` と `check_plan_precondition` は設計 §3.2 (idempotency、plan) の副作用境界なので除外する。結果型 (dataclass) は純粋なので WP-3 の候補にする | §2、§3、§4 |
| U-5 / m5 | import 方向はテストで機械化する。`tools/tests/test_leaf_import_direction.py` の 1 file に leaf 一覧 (peer・パス・許可リスト) を持たせ、両 peer に同名 helper を置かない。独立した変更セット WP-1-0 (1a の前) とし、既存 6 leaf の登録と全 module の分類を含める。WP-1-0 以降の全 WP の検証とゲートに `pytest -q tools/tests` を入れる。以後 module を足す WP は同じ変更で一覧を更新する | §4、§5.1〜§5.4 |
| U-6 | 責務ごとに別 module にする (ST3 は 1a と共有しない) | §2.1 |
| M1 | WP-1b の key 順の変異は、キー順の崩れた dict を値に持つ Filter の新規テストを赤の根拠にする | §5.3 |
| M2 | 両 peer `src/` の全 module を leaf 又は理由付き非 leaf に分類させ、未分類は赤 (変異: 分類の無い新 module を足す) | §5.1 |
| m1〜m4、m6〜m8 | m1 ST2 の範囲を L1592-1597 とし説明コメントを照合対象へ / m2 `_float8out_text` の位置参照を 40c の対象へ / m3 `__future__` は常に許可、AST の module 名で照合 / m4 import 違反の変異は循環しないもの / m6 sib 集合の更新 / m7 venv の python と `tools/tests` baseline 107 / m8 §1 の件数表を削除 | §1、§2、§4、§5 |
