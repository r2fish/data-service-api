# 作業指示書 — R-37 WP-0 inventory と WP-1 の Change Set Manifest

## 0. 版数・位置づけ

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
