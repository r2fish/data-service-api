# 作業指示書 — R-37 WP-0 inventory と WP-1 の Change Set Manifest

## 0. 版数・位置づけ

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
| U-3 | ST1 は `pg_text_format.py` (float8out を含むため)。削除確認 phrase の helper は両 peer とも `delete_confirmation.py` (CE1 と後の ST5)。他は提案名で進め、独立レビューで確認する | §2、§5 |
| U-4 | `fold_operation_idempotency_keys` と `check_plan_precondition` は設計 §3.2 (idempotency、plan) の副作用境界なので除外する。結果型 (dataclass) は純粋なので WP-3 の候補にする | §2、§3、§4 |
| U-5 / m5 | import 方向はテストで機械化する。`tools/tests/test_leaf_import_direction.py` の 1 file に leaf 一覧 (peer・パス・許可リスト) を持たせ、両 peer に同名 helper を置かない。独立した変更セット WP-1-0 (1a の前) とし、既存 6 leaf の登録と全 module の分類を含める。WP-1-0 以降の全 WP の検証とゲートに `pytest -q tools/tests` を入れる。以後 module を足す WP は同じ変更で一覧を更新する | §4、§5.1〜§5.4 |
| U-6 | 責務ごとに別 module にする (ST3 は 1a と共有しない) | §2.1 |
| M1 | WP-1b の key 順の変異は、キー順の崩れた dict を値に持つ Filter の新規テストを赤の根拠にする | §5.3 |
| M2 | 両 peer `src/` の全 module を leaf 又は理由付き非 leaf に分類させ、未分類は赤 (変異: 分類の無い新 module を足す) | §5.1 |
| m1〜m4、m6〜m8 | m1 ST2 の範囲を L1592-1597 とし説明コメントを照合対象へ / m2 `_float8out_text` の位置参照を 40c の対象へ / m3 `__future__` は常に許可、AST の module 名で照合 / m4 import 違反の変異は循環しないもの / m6 sib 集合の更新 / m7 venv の python と `tools/tests` baseline 107 / m8 §1 の件数表を削除 | §1、§2、§4、§5 |
