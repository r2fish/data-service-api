# 作業指示書 — R-39 移動前から存在するテストの穴と古い位置参照

## 0. 版数・位置づけ

- **v1.0 (2026-10-05)。** 起草。変更セット 1 (§3〜§7) と変更セット 2 (§9) の 2 本立て。枠は監督確定 (2026-10-05)、裁定は §8 (事後確認待ち)。
- 規律は `docs/work-orders/OPERATING_CONDITIONS.md` に従う (commit は監督のみ、道具は `tools/dev/`、下請け Agent を使わない。§1.1、§1.7 の 46・47)。本書の訂正は本文を書き換えず訂正註として追記する (§1.8 の 57)。

## 1. 目的と基点

- **目的**: 台帳 `RM` (= `docs/design/ROADMAP_POST_PHASE7_V1.md`) §8 の R-39 (`RM`:464) が追跡する穴のうち、変更セット 1 (CS-1) では今も開いているテストの穴 10 件を新規テストで塞ぎ、変更セット 2 (CS-2) では tests / conformance / conformance-tests / README に残る行番号形の位置参照と不正確な文を直して再発防止のガードを置く。
- **基点**: main `fef2cc5`、台帳 v1.179、`security/CONTROL_MAPPING.md` 3.26 (いずれも 2026-10-05 の記録。§1.8 の 55a)。
- **穴の原記述**: `MRA` (= `docs/design/MODULE_REFACT_ARCHITECTURE_V1.md`) §10.2 (`MRA`:317、:319)、§10.4 (`MRA`:342、:344)、§10.5 (`MRA`:367、:368)、§10.6 (`MRA`:385、:386、:388、:389)、§10.7 (`MRA`:407、:408、:409)、§10.9 (`MRA`:443)。
- **判定の出所**: `$SP/r39-gap-judgement-AB.md` (reader。実 PostgreSQL 16.14 照合済み) と `$SP/r39-lineref-classification.md` (reader。位置参照の分類と文の案)。file:line は基点 `fef2cc5` での実測で、判定ファイルの行番号と食い違う箇所は本書の実測を採った。
- **worktree**: CS-1 = `.claude/worktrees/r39`、CS-2 = `.claude/worktrees/r39-refs` (main から新設)。

| 変更セット | 変更クラス | 規模 | 役割 |
|---|---|---|---|
| CS-1 (テストの穴) | Class B (両 peer の tests のみ) | M | 実装担当 1、コードレビュー 1 起動、監査担当なし |
| CS-2 (位置参照とガード) | Class C (`conformance-tests/` を触る) | M | 実装担当 1、コードレビュー 1 起動 (共通契約の観点: conformance-tests の docstring の文が契約の主張を変えていないこと)、受け入れ監査 1 起動 |

### 1.1 並行する 2 変更セットの触るファイル (重なり 0。§1.2 の 16・17)

| 変更セット | 触るファイル |
|---|---|
| CS-1 | §3.2 の新規 10 ファイルのみ (いずれも基点に存在しないことを確認済み) |
| CS-2 | §9.2 の既存ファイルの文 (C2-1 の分類で増える分を含む。いずれも既存ファイル) と、新規 `tools/tests/test_no_line_number_position_refs.py` 1 本 |

CS-1 の新規ファイル名は CS-2 の一覧のどれとも一致しない。CS-1 は既存ファイルを編集しない。

## 2. 枠 (監督確定、CS-1)

### 2.1 守る条件

- 台帳 R-39 のテストの穴 (A/B 群) のうち、現在も開いているものを両 peer の tests に新規テストで塞ぐ。
- 既存の挙動を変えない。製品コード (`src/`) を変更しない。変異の注入と復元は `tools/dev/mutate.py` の管理下に限る (§1.4)。
- **新規ファイルのみ**: 既存のテストファイルを編集しない (CS-2 が既存 tests を触るため。§1.1)。新規ファイル名は leaf 単位。
- 空振り禁止 (§1.5 の 32): 各テストは観測対象 ≥ 1 を assert する。実 PG を使うテストは既存の `test_postgres.py` のフィクスチャ経路 (`DSA_TEST_PG`、`tools/testpg`) に乗る。
- 完了条件 1 項目 = 新テスト関数 1 本 = 変異 1 entry (§1.5 の 33。分割の仕方は監督裁定 2026-10-05)。変異は製品コードの該当行を壊し、新テストが赤になることを `mutate.py` で実測する (1 テストにつき 1 entry)。実 PG parity テストの変異は in-memory 側 (`pg_text_format.py` / `inmemory_predicate.py`) に掛ける。
- 製品コードの変更が要ると分かった性質はテストにせず、§5 に残す (監督が台帳へ起票)。

### 2.2 却下した代替案

- 既存の parity テスト (`test_postgres.py` / `test_foundation.py`) に値を足す — CS-2 と同じファイルを触るので却下。
- C-xx 条件への昇格 — `pg_text_format` の parity は r2db の plug 内の一致であり共通契約の文言ではない。契約が number 列の text 形を定めるかは起票先で決める (§8 の Y-4)。

## 3. CS-1 — WP-1: テストの穴 10 件を新規テストで塞ぐ

WP は 1 本 (実装担当 1)。製品コードの file:line は基点 `fef2cc5` の実測。

### 3.1 対象 → 完了条件 → 変異

完了条件 1 項目 = 新テスト関数 1 本 = 変異 1 entry (§2.1)。

| # | 穴 (原記述) | 対象 module と file:line | 完了条件 (入力と期待値) | 変異 (製品コードの file:line と壊し方) |
|---|---|---|---|---|
| C1-1a | 1a float8 の負の指数 (`MRA`:317) | r2db `r2db-api/src/r2db_api/pg_text_format.py`:17-31 `_float8out_text` | `_float8out_text(1e-5) == "1e-05"`、`(1.5e-7) == "1.5e-07"`、`(-1e-7) == "-1e-07"`。実 PG parity: 同じ値を typed number 列に入れ、contains / matches の needle が in-memory と PG の両 plug で同じ行を当てる | **M1-1a**: `pg_text_format.py`:30-31 の符号または指数の 1 箇所を壊す (どちらにするかは実装担当が決め、変異表に 1 つだけ書く。例: 返す前に `text.replace("e-0", "e-")` を挟む。0 詰めは `repr` 由来で明示の行は無い) |
| C1-1b | 1a jsonb 数値の text (`MRA`:317) | 同 :34-60 `_jsonb_numeric_text` | `_jsonb_numeric_text(1e-07) == "0.0000001"`、`(1.234e-05) == "0.00001234"`。実 PG parity: 同じ値を untyped 列に入れ、needle が両 plug で同じ行を当てる | **M1-1b**: `pg_text_format.py`:58-59 の指数の展開を外す (`text` をそのまま返す) |
| C1-1c | 1a 非 ASCII キー順 (`MRA`:317) | 同 :83 `_jsonb_text` (:99 キーの並べ方) | `_jsonb_text({"é":1,"z":2,"ab":3,"日本":4}) == '{"z": 2, "ab": 3, "é": 1, "日本": 4}'` (順 `z, ab, é, 日本`)。実 PG parity: 同じ object 値で needle が両 plug で同じ行を当てる | **M1-1c**: `pg_text_format.py`:99 の鍵を `lambda k: k.encode("utf-8")` にする (長さの項を外す) |
| C1-2a | 1c 降順の同値行 (`MRA`:319) | r2db `r2db-api/src/r2db_api/inmemory_sort.py`:169-173 `_sort_rows` | bucket 列に x,x,x,y,y (id 1-5)、order_by bucket desc の id 列 == `[4, 5, 1, 2, 3]` (同値は id 昇順。値は判定の読解による。実装担当が現行実装で確かめ、報告に実測値を書く)。実 PG (`order by bucket desc, id asc`) との parity でも同じ | **M1-2a**: `inmemory_sort.py`:171 の `reversed(spec)` を `spec` にする |
| C1-2b | 1c typed boolean (`MRA`:319) | 同 :45 `_sort_key` (:114-115 bool の鍵) | typed boolean 列に True,False,True,False (id 1-4): 昇順 id == `[2, 4, 1, 3]`、降順 id == `[1, 3, 2, 4]`。実 PG との parity でも同じ | **M1-2b**: `inmemory_sort.py`:115 の `int(value)` を `-int(value)` にする |
| C1-2c | 1c `_after_page_cursor` の bool (`MRA`:319) | 同 :176-195 `_after_page_cursor` | typed boolean 列の order_by で cursor ページングを行い、bool の cursor 値の後ろに来る行が正しいこと。入力と期待値は実装担当が現行実装を読んで確定し、報告に実測値を書く | **M1-2c**: `inmemory_sort.py`:192-193 の asc の比較を反転する (`>` → `<`)。最終形は実装担当が期待値と併せて確定する |
| C1-3a | 1d スカラーのコスト (`MRA`:342) | MitateDB `MitateDB-api/src/mitatedb_api/request_limits.py`:18 `_measure_request_bytes` (:73-76) | `_measure_request_bytes` を直接呼ぶ。スカラー 1 個 (`None`、`True`、`1`、`1.5`) と未知型 `object()` は bound=7 拒否 / 8 通る。拒否は `ResourceLimitError` (`limit_class="request_bytes"`。以下 C1-3 共通) | **M1-3a**: `request_limits.py`:74 の `total += 8` を `total += 9` にする |
| C1-3b | 1d bytes のコスト (`MRA`:342) | 同 :71-72 | `b"x"*10` は bound=9 拒否 / 10 通る。`bytearray(b"x"*10)` も同じ | **M1-3b**: `request_limits.py`:72 の `len(item)` を `len(item) + 1` にする |
| C1-3c | 1d container の固定 2 (`MRA`:342) | 同 :64-68 | 空 list は bound=1 拒否 / 2 通る | **M1-3c**: `request_limits.py`:65 の `total += 2` を `total += 3` にする |
| C1-3d | 1d tuple・set の枝 (`MRA`:342) | 同 :64 | 空 tuple・空 set は bound=1 拒否 / 2 通る (未知型の 8 にならない) | **M1-3d**: `request_limits.py`:64 の `(list, tuple, set)` を `(list,)` にする |
| C1-3e | 1d dict の key のコスト (`MRA`:342) | 同 :58-63 | `{"a": 1}` は 2+4+8=14 (bound=13 拒否 / 14 通る)。`{1: 1}` は 2+8+8=18 (17 拒否 / 18 通る) | **M1-3e**: `request_limits.py`:62 (key を子として積む行) を削る |
| C1-3f | 1d 兄弟の共有は循環でない (`MRA`:342) | 同 :39-57 (祖先経路の `frozenset`) | 同一 list を `[shared, shared]` の兄弟に置いて例外なし。対照: 自己参照は `ValidationError` | **M1-3f**: `request_limits.py`:39-57 の循環判定を、祖先経路ではなく全体の訪問集合で行う形に変える (r2db `r2db-api/src/r2db_api/limits.py`:63 `check_request` の `seen` と同じ形。最終形は実装担当が変異表に書く) |
| C1-4a | 1e matches の `(?s)` (`MRA`:344) | r2db `r2db-api/src/r2db_api/inmemory_predicate.py`:61 | label `"a\nb"` に matches `"a_b"` と `"a%b"` が当たる。in-memory と実 PG の parity で同じ (実 PG の値は §3.3) | **M1-4a**: `inmemory_predicate.py`:61 から `(?s)` を外す |
| C1-4b | 1e matches の `\Z` (`MRA`:344) | 同 :61 | label `"a\n"` に matches `"a"` が当たらず、`"a%"` は当たる。parity で同じ | **M1-4b**: `inmemory_predicate.py`:61 の `\\Z` を `$` にする |
| C1-5a | 1h order_by 項目の余分なキー (`MRA`:367) | r2db `r2db-api/src/r2db_api/paging.py`:56 `_resolve_order_by` (:63) | `_resolve_order_by` を直接呼ぶ。`[{"field":"f0","x":1}]` → VALIDATION_FAILED、details.violated_declaration `request_schema`、details.field `"order_by"` | **M1-5a**: `paging.py`:63 から `or set(item) - {"field", "direction"}` を削る |
| C1-5b | 1h 不正な direction (`MRA`:367) | 同 :84-85 | `[{"field":"f0","direction":"sideways"}]` → VALIDATION_FAILED、details == `{"violated_declaration": "enum", "field": "order_by/direction", "declared_type": "string"}` (現行値の pin。peer 差は §5) | **M1-5b**: `paging.py`:84-85 の direction 検査を削る |
| C1-5c | 1h id を補うのは不在時だけ (`MRA`:367) | 同 :87-91 | `[{"field":"id","direction":"desc"}]` の結果 == `[("id", "desc")]`、`[{"field":"f0"},{"field":"id"}]` の結果で `id` が 1 個 (順序・件数が変わらない) | **M1-5c**: `paging.py`:87 の `not any(...)` を `any(...)` にする |
| C1-5d | 1h cursor 値の bool (旧「bool の offset」の現行の対応物) (`MRA`:367) | 同 :146-172 `decode_and_check_page_cursor`、`r2db-api/src/r2db_api/value_types.py`:123 | 期待値は実装担当が現行実装を読んで確定し、報告に実測値を書く。判定の読解では、integer の id 列で `encode_page_cursor([True, 1], binding)` → VALIDATION_FAILED / request_schema / details.field `page/cursor` | **M1-5d**: `value_types.py`:123 から `and not isinstance(value, bool)` を削る |
| C1-6a | 1i enum field の型違い (`MRA`:368) | r2db `r2db-api/src/r2db_api/value_types.py`:69 `_check_type` (:122-172 型検査、:182-187 enum 検査) | string + enum `["a","b"]` の field に insert `{"status": 5}` → details == `{"field": "operations/0/values/status", "violated_declaration": "field_type", "declared_type": "string", "observed_type": "integer"}` (enum ではない) | **M1-6a**: `value_types.py`:182-187 の enum 検査を :122 の型検査の前へ移す |
| C1-6b | 1i `in` の要素の path (`MRA`:368) | 同 :255-256 | query where `[{"field":"status","operator":"in","value":["a",5]}]` → details.field `"where/0/value/1"`、violated_declaration `"field_type"`、declared_type `"string"`、observed_type `"integer"` | **M1-6b**: `value_types.py`:256 の `f"{base_path}/{j}"` を `base_path` にする |
| C1-7a | 1j 複数の未知キー (`MRA`:385) | MitateDB `MitateDB-api/src/mitatedb_api/constraint_resolution.py`:63 `_resolve_field_constraints` (:89-98) | `field_constraints={"status": {"zz":1,"aa":2}}` → details.field == `"field_constraints/status/aa"` (辞書順最小) | **M1-7a**: `constraint_resolution.py`:91 の `sorted(unknown_keys)[0]` を `[-1]` にする |
| C1-7b | 1j 整数の nullable (`MRA`:386) | 同 :99-114 | `{"nullable": 1}` → details == `{"violated_declaration": "request_schema", "field": "field_constraints/status/nullable", "declared_type": "boolean", "observed_type": "integer"}`。対照: `{"nullable": True}` は通る | **M1-7b**: `constraint_resolution.py`:100 の `isinstance(nullable, bool)` を `isinstance(nullable, (bool, int))` にする |
| C1-8a | 1l 拒否メッセージの文言 (`MRA`:388) | MitateDB `MitateDB-api/src/mitatedb_api/postgres_reserved_names.py`:18-23 `_check_reserved_name` | label `"collection"` で `str(exc) == "reserved collection"`、label `"entity"` で `"reserved entity"` | **M1-8a**: `postgres_reserved_names.py`:21 の `"reserved " + label` を変える (例 `"reserved: " + label`) |
| C1-8b | 1l `pg_` の大文字小文字 (`MRA`:389) | 同 :19 | `"PG_x"`・`"Pg_x"` は検査を通る (`startswith` は大小を区別する) | **M1-8b**: `postgres_reserved_names.py`:19 の `value.startswith(...)` を `value.lower().startswith(...)` にする |
| C1-9 | 1n 孤立 surrogate の範囲 (`MRA`:408) | MitateDB `MitateDB-api/src/mitatedb_api/postgres_value_domain.py`:13 `_validate_value_domain` (:110-114) | `"\udc00"`、`"\udfff"` (low 単独) と `"\ud800"`、`"\udbff"` (high 単独) がいずれも `ValidationError` (details.violated_declaration `field_type`、observed_type `string`) | **M1-9**: `postgres_value_domain.py`:110 の上限 `0xDFFF` を `0xDBFF` にする |
| C1-10a | 3c-24 形の検査と request_bytes の順 (`MRA`:443) | r2db `r2db-api/src/r2db_api/service.py`:295-297 (`_query_outcome`)。形の検査は `r2db-api/src/r2db_api/request_shape.py`:14 | request_bytes=100 の limits で `service.query(ctx, "items", select="x"*1000)` → VALIDATION_FAILED / request_schema (LIMIT_EXCEEDED ではない)。対照: 形が正しく超過だけのとき LIMIT_EXCEEDED | **M1-10a**: `service.py`:296-297 (request の組立てと `self.limits.check_request(request)`) を :295 の形の検査の前へ移す |
| C1-10b | 3c-24 形の検査と depth の順 (`MRA`:443) | 同 :295・:298 | `page_size=True` と深さ 1200 の where 値の組 → VALIDATION_FAILED (LIMIT_EXCEEDED ではない)。対照: 形が正しく depth 超過だけのとき LIMIT_EXCEEDED | **M1-10b**: `service.py`:298 の `self.limits.check_depth(request)` を、request の組立て (:296) と併せて :295 の形の検査の前へ移す |
| C1-10c | 3c-24 形の検査と request_bytes の順、mutate 経路 (`MRA`:443) | `service.py` の mutate 経路 (:357-370 付近。実装担当が現行の行を読んで確定) | 形の不正 (例 `best_effort` の型違い) と request_bytes 超過の組 → VALIDATION_FAILED (LIMIT_EXCEEDED ではない)。対照: 形が正しく超過だけのとき LIMIT_EXCEEDED | **M1-10c**: mutate 経路の `check_request` 呼出しを形の検査の前へ (監督追加 2026-10-05: 起草報告の指摘「mutate 経路がどの完了条件にも入っていない」を受けて足した) |
| C1-11 | 対応表 | — | §6 の表で C1-1a〜C1-10c の全行に変異が対応し、全 entry が赤 → 復元 sha256 一致 | — (監査照合: `mutate.py` の変異表と集計行を §10 に逐語で残す) |

### 3.2 触ってよいパス (新規テストファイル案)

| # | 新規ファイル案 |
|---|---|
| C1-1a〜1c | `r2db-api/tests/test_pg_text_format_parity.py` |
| C1-2a〜2c | `r2db-api/tests/test_inmemory_sort_desc_ties_parity.py` |
| C1-3a〜3f | `MitateDB-api/tests/test_request_limits_measurement.py` |
| C1-4a・4b | `r2db-api/tests/test_matches_newline_parity.py` |
| C1-5a〜5d | `r2db-api/tests/test_paging_order_by_shape.py` |
| C1-6a・6b | `r2db-api/tests/test_value_types_enum_type_order.py` |
| C1-7a・7b | `MitateDB-api/tests/test_constraint_resolution_keys.py` |
| C1-8a・8b | `MitateDB-api/tests/test_postgres_reserved_names_leaf.py` |
| C1-9 | `MitateDB-api/tests/test_postgres_value_domain_surrogates.py` |
| C1-10a・10b | `r2db-api/tests/test_request_shape_before_limits.py` |

- 上記の新規ファイルと `$SP/r39-cs1-mutations.json` のみ。ファイル名は変えてよいが leaf 単位で、基点に存在しない名前に限る (変えたら報告に書く)。
- `src/`、既存の tests、`conformance/`、`conformance-tests/`、`docs/`、`security/` には触らない (台帳への起票 §5 は監督が行う)。

### 3.3 実 PostgreSQL の実測 (PostgreSQL 16.14、LC_ALL=C 相当の initdb、2026-10-05、reader。期待値の出所)

| 種別 | 入力 → PG の text |
|---|---|
| float8 (`select (<lit>::float8)::text`) | -0.0→`-0`、1e-5→`1e-05`、0.0001→`0.0001`、1e15→`1e+15`、1e16→`1e+16`、123456789012345.0→`123456789012345`、1234567890123456.0→`1.234567890123456e+15`、9999999999999998.0→`9.999999999999998e+15`、1.5e-7→`1.5e-07`、-1e-7→`-1e-07`、5e-324→`5e-324`、1e14→`100000000000000` |
| jsonb 数値 (`select '<json text>'::jsonb #>> '{}'`) | `-0.0`→`0.0`、`1e-07`→`0.0000001`、`1.5e-07`→`0.00000015`、`-1e-07`→`-0.0000001`、`1e+16`→`10000000000000000`、`1.234e-05`→`0.00001234` |
| jsonb object text (`select '<json>'::jsonb::text`) | `{"é":1,"z":2,"ab":3,"日本":4}` → `{"z": 2, "ab": 3, "é": 1, "日本": 4}` |
| LIKE | `'a\nb' like 'a_b'`=t、`like 'a%b'`=t、`'a\n' like 'a'`=f、`'a\n' like 'a%'`=t |

### 3.4 道具の引数 (main checkout を cwd にし、`SP` を export する)

- テスト: `tools/dev/pt.py -C .claude/worktrees/r39 --wait 300 -- r2db-api/tests/<新規ファイル> MitateDB-api/tests/<新規ファイル> -q`
- 変異: `tools/dev/mutate.py "$SP/r39-cs1-mutations.json" -C .claude/worktrees/r39 --wait 300` (1 テスト関数につき 1 entry、expect=red。`mutate.py` は最初の失敗で止まるので entry ごとに対象テストを 1 件だけ書く)
- 実行は §1.5 の 39 のとおり。

**訂正註 (2026-10-05、CS-1 実装報告、本文は書き換えない)**: C1-10c の「形の不正 (例 `best_effort` の型違い) → VALIDATION_FAILED」は現行と合わない。`best_effort` の型違いは現行 CAPABILITY_UNSUPPORTED (details.field `transaction`) であり、既存の `test_foundation.py` も同じ値を pin している。実装は `operations` の形の不正 (→ VALIDATION_FAILED、field `operations`) を主とし、`best_effort` + 過大 operations → CAPABILITY_UNSUPPORTED、対照の過大のみ → LIMIT_EXCEEDED を同じ関数で assert した。C1-5d の spec は judgement の「id 列で `[True,1]`」では件数不一致で bool と無関係に拒否されるため 2 項 (n, id) にした。C1-10c は `test_request_shape_before_limits.py` に置いた (§3.2 は 10a・10b だけ記載)。

## 4. 閉じたと記録するだけの件 (テストを足さない)

- **1e の NULL 行除外と untyped float** (`MRA`:344): 固定済み。NULL 行除外は `r2db-api/tests/test_foundation.py`:1985-2013 と実 PG parity `r2db-api/tests/test_postgres.py`:3119-3171、untyped float と nested float の jsonb text は `r2db-api/tests/test_postgres.py`:3203-3248。
- **1m** (`MRA`:407): 既存の literal pin (`MitateDB-api/tests/test_postgres.py`:1603-1632) が固定済み。
- **1h の「bool の offset」** (`MRA`:367): offset codec は フェーズ11 で消え、前提が消滅した。現行の対応物 (cursor 値の bool) は C1-5d で固定する。
- **1k** (`MRA`:409): 「到達不能な gate を固定するのは直接のテストだけ」は現状の記述であり穴ではない。docstring の古い文は `src/` なので CS-1 では触らない (§8 の Y-2: R-22 へ渡す)。

**参考** (テストにも起票にもしない。判定の記録):

- 1d の peer 差: r2db `ResourceLimits.check_request` (`r2db-api/src/r2db_api/limits.py`:63) は訪問集合 `seen` が全体で、兄弟の共有も循環として扱い、未知型は VALIDATION_FAILED。MitateDB `_measure_request_bytes` (`MitateDB-api/src/mitatedb_api/request_limits.py`:30-37、:75-76) は祖先経路だけを見て、未知型は 8。
- 1j: 未知キーは `sorted(unknown_keys)[0]` の 1 件だけを、構文検査なしで message と details.field にそのまま入れる (`MitateDB-api/src/mitatedb_api/constraint_resolution.py`:89-98)。

## 5. 起票へ回す件 (製品コードの変更が要る疑い。直さない。§8 の Y-5)

起票は CS-1 と同じ変更セット (worktree `.claude/worktrees/r39`) で台帳 (`RM` §8) に入れる。

- **R-123** r2db `pg_text_format._float8out_text` (`r2db-api/src/r2db_api/pg_text_format.py`:17-31): 1e15 以上 1e16 未満で実 PG は指数表記 (`1e+15`、`1.234567890123456e+15`、`9.999999999999998e+15`)、現行は plain (`1000000000000000`、`1234567890123456`、`9999999999999998`)。`_jsonb_numeric_text(-0.0)` (同 :34-60): 実 PG は `0.0`、現行は `-0.0`。
- **R-124** order_by 項目の details.field の peer 差: r2db は `order_by/direction` (`r2db-api/src/r2db_api/paging.py`:85)・`order_by` (:64)、MitateDB の cell 層は `order_by/<i>/direction`・`order_by/<i>`。契約の path 規則の確認。

## 6. CS-1 完了条件 → 変異 (1 項目 1 テスト関数 1 entry、expect=red。§1.5 の 40)

| 完了条件 | 変異 | 赤になるべきテスト関数 (test id は実装担当が変異表に書く) |
|---|---|---|
| C1-1a | M1-1a | float8 の負の指数 |
| C1-1b | M1-1b | jsonb 数値の text |
| C1-1c | M1-1c | 非 ASCII キー順 |
| C1-2a | M1-2a | 降順の同値行 |
| C1-2b | M1-2b | typed boolean の昇順・降順 |
| C1-2c | M1-2c | `_after_page_cursor` の bool |
| C1-3a | M1-3a | スカラーのコスト 8 |
| C1-3b | M1-3b | bytes のコスト len |
| C1-3c | M1-3c | container の固定 2 |
| C1-3d | M1-3d | tuple・set の枝 |
| C1-3e | M1-3e | dict の key のコスト |
| C1-3f | M1-3f | 兄弟の共有は循環でない |
| C1-4a | M1-4a | `(?s)` (改行に `_`・`%` が当たる) |
| C1-4b | M1-4b | `\Z` (末尾の改行を許さない) |
| C1-5a | M1-5a | order_by 項目の余分なキー |
| C1-5b | M1-5b | 不正な direction |
| C1-5c | M1-5c | id が既にあるとき補わない |
| C1-5d | M1-5d | cursor 値の bool |
| C1-6a | M1-6a | enum field の型違い |
| C1-6b | M1-6b | `in` の要素の path |
| C1-7a | M1-7a | 複数の未知キー |
| C1-7b | M1-7b | 整数の nullable |
| C1-8a | M1-8a | 拒否メッセージの文言 |
| C1-8b | M1-8b | `PG_x`・`Pg_x` が通る |
| C1-9 | M1-9 | low surrogate 単独の拒否 |
| C1-10a | M1-10a | 形の不正と request_bytes 超過の組 |
| C1-10b | M1-10b | 形の不正と depth 超過の組 |
| C1-10c | M1-10c | 形の不正と request_bytes 超過の組 (mutate 経路) |
| C1-11 | 監査照合 (本表と `mutate.py` の変異表・集計行を §10 に逐語で残す) | — |

対応の無い行が無いことを最後の完了条件とする (C1-11)。

## 7. CS-1 受入条件

1. `tools/dev/pt.py` (§3.4) の集計行が failed 0。集計行を §10 に逐語で残す。
2. `tools/dev/mutate.py` の変異表の全 entry (M1-1a〜M1-10c の 28 件) が `expect=red got=red`。
3. 各変異の復元後の sha256 一致 (`mutate.py` の出力。§1.4 の 29〜31)。
4. 完了ゲート (`tools/dev/gate.py`、監督のみ。§1.6 の 41) が `judge=PASS`。
5. 既存テストファイル無変更: `git -C .claude/worktrees/r39 diff --stat main` に既存の tests が出ず、`git status --short` の tests 配下が §3.2 の新規ファイル (`??`) だけである。`src/` の差分 0。
6. コードレビュー 1 起動 (規模 M。監査担当なし)。

## 8. 監督裁定の引用 (推奨で進め、事後確認待ち。依頼者方針 2026-10-03)

以下は監督裁定の逐語である (§1.5 の 35・36)。いずれも **事後確認待ち**。

| # | 裁定 | 推奨の理由 |
|---|---|---|
| Y-1 | 台帳 R-39 の印「あり」(着手条件: 運用開始後) を「なし」に改め、着手条件の欄に「依頼者指示 2026-10-05 で前倒し」と記す | 固定欄が正 (LEDGER_FIXED_FIELDS D-2)。条件が消えた行に印を残すと `ledger.py --open` の並び (印なし先) が実態と食い違う。経緯は【追記】に残す (R-14、行を消さない) |
| Y-2 | 両 peer の `src/` にある古い位置参照・不正確なコメント (structured.py L146-148、cell.py L1910/1916/1981/2546/3869/3934、limits.py L315-316、capabilities_document.py L335/374/376、config.py L56) は R-39 で直さず、台帳 R-22 の次の変更セットの候補として R-22 行へ【追記】で渡す | 来歴検査器は CH-ID の無い塊の変更をすべて赤にし (設計 §4.1 (2) v0.22、reader 実測)、正規の経路は CH-ID 登録 + 訂正記録 (§9.3) = R-22 の作業そのもの。R-39 で同じ塊を触ると受け皿と衝突する。R-22 側は CM の位置参照の引き直しも手順に持つ |
| Y-3 | tests/・conformance/・conformance-tests/・README の `file.py:NNNN` 形の参照は、「現在の所在の主張」なら行番号に依らない形 (`file.py::symbol`) に直し、「時点の記録」は触らない。再発防止に tools/tests へ静的ガード (行番号形の位置参照 0 件、時点の記録は逐語 allowlist) を置く | 行番号は設計上腐る (R-37 以降 4 回引き直している)。symbol 形は移動に追随しないが grep で検証できる。ガードが無いと同じ穴が再び開く |
| Y-3a | Y-3 のガードの対象は `(structured\|cell\|service).py` に限らず、tests/・conformance/・conformance-tests/・両 peer README にある全ての `<module>.py:NNNN` 形 (reader が同じ hunk に見つけた 25 件を含む)。時点の記録 8 件は逐語の allowlist (file、トークン、記録である理由) に置く | 行番号参照が腐る性質は module を選ばない。同じファイルの同じ種類の欠陥を残すと、ガードを allowlist で広げるしかなくなる |
| Y-4 | `pg_text_format` の実 PG parity を C-xx 条件へ昇格しない | r2db の plug 内 (in-memory と PG) の一致であり共通契約の文言ではない。契約が number 列の text 形を定めるかは起票先 (pg_text_format の不一致の行) で決める |
| Y-5 | 製品コードの変更が要る疑い 2 件を台帳に起票する: (R-123) r2db `pg_text_format` の実 PG との不一致 (1e15〜1e16 の指数表記、jsonb `-0.0` → `0.0`)、(R-124) order_by 項目の details.field path の peer 差 (r2db `order_by/direction`、MitateDB cell 層 `order_by/<i>/direction`) と契約の path 規則の確認 | R-39 の枠 (挙動を変えない) の外。R-39 で直すと Class B の製品変更が混ざる |
| Y-6 | MitateDB README L267-269 の「`deployment_required` はどの peer の宣言コードにも無い」は `capabilities_document.py:57` が返す現状と食い違うので、CS-2 で実装担当が確認して文を直す (位置参照ではなく内容の古さ) | 同じ README の同じ節を触る変更セットで直すのが最小 |

## 9. 変更セット 2 — 古い位置参照・不正確なコメントの修正と再発防止ガード

worktree `.claude/worktrees/r39-refs` (main から)。WP は 1 本 (実装担当 1)。

### 9.1 枠 (監督確定、CS-2)

- 台帳 R-39 の (3b)、(3c) の行番号参照、(3d〜3i) の manifest の tests / conformance 側、(3g) の tests 側、(3h)、(1d) の V-4 と「共通: conformance と tests に残る行番号参照」を直す (`RM`:464)。
- `src/` は触らない (§8 の Y-2)。製品コードの変更なし。テストの assert・期待値を変えない (文字列・コメント・docstring・README の文だけ)。
- CS-1 と重なり 0 (§1.1)。

### 9.2 触ってよいパス

- r2db: `r2db-api/tests/test_idempotency_records.py`、`r2db-api/tests/test_control_plane_service.py`、`r2db-api/tests/test_foundation.py`、`r2db-api/tests/test_audit_query.py`、`r2db-api/conformance/conformance_adapter_r2db.py`、`r2db-api/conformance/conformance_adapter_r2db_http.py`、`r2db-api/conformance/conformance_adapter_r2db_socket.py`
- MitateDB: `MitateDB-api/tests/test_control_main.py`、`MitateDB-api/tests/test_audit_query.py`、`MitateDB-api/tests/test_idempotency_records.py`、`MitateDB-api/tests/test_main.py`、`MitateDB-api/tests/test_control_plane_service.py`、`MitateDB-api/tests/test_foundation.py`、`MitateDB-api/tests/test_limit_class_vocabulary.py`、`MitateDB-api/tests/test_threadpool_offload.py`、`MitateDB-api/conformance/conformance_adapter_mitatedb.py`、`MitateDB-api/conformance/conformance_adapter_mitatedb_http.py`、`MitateDB-api/README.md`
- 共通: `conformance-tests/test_c05_limit_declaration_agreement.py`、`conformance-tests/test_c14_authority_boundary.py`、`conformance-tests/test_c20_constraint_declaration_agreement.py`、`conformance-tests/test_c22_dry_run_and_plan.py`、`conformance-tests/test_c24_request_budget.py`
- 新規: `tools/tests/test_no_line_number_position_refs.py`、`$SP/r39-cs2-mutations.json`
- 一覧は `$SP/r39-lineref-classification.md` の表と「list 外」の行から取った。C2-1 の未分類の行を主張と分類して直すファイル (例 `conformance-tests/test_c04_unsupported_and_safe_errors.py`) は、分類表を報告に添えたうえで触ってよい。

### 9.3 対象 → 完了条件 → 変異

| # | 対象 | 完了条件 | 変異 |
|---|---|---|---|
| C2-1 | 「現在の所在の主張」の行番号参照 55 件 (分類表の「主張」)、同じ hunk の `<module>.py:NNNN` 25 件 (分類表の「list 外」)、および C2-5 の走査対象に残る未分類の行 (`synthetic_*.py` の 12 行、`conformance-tests/test_c04_unsupported_and_safe_errors.py`:147-159、`test_c27_concurrent_same_key.py`・`test_c28_baseline_turn.py`・`test_c30_keyset_paging.py` ほか約 40 行) | 分類表の行は分類表を正とする。未分類の行は実装担当が分類表と同じ規則 (主張 → `file.py::symbol`、時点の記録 → allowlist、位置参照でないもの → 理由を付けて報告) で分類し、その分類表を報告に添える。主張は `file.py::symbol` 形 (または「`symbol` in `file.py`」) に置換する。置換案は分類表の「置換案」の列。symbol が grep で現存することを 1 件ずつ確認し、確認結果を報告に書く。conformance-tests は R-95 の `conformance-tests/test_conformance_docstring_position_refs.py` の抽出規則 (bare `:NNN` が直前の path を継承) に合わせ、comment unit ごとに直す (例: `test_c05_limit_declaration_agreement.py` の 1195〜1203 行、930〜932 行、`test_c14_authority_boundary.py` の 746〜747 行は unit ごとまとめる) | ガードの変異で代表 (C2-5 の M2-5) |
| C2-2 | 「時点の記録」と分類したもの全件。reader の 8 件: `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py`:117、:738、`r2db-api/tests/test_idempotency_records.py`:369、`MitateDB-api/tests/test_threadpool_offload.py`:642、`MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py`:809、`MitateDB-api/tests/test_dry_run_and_plan.py`:370、`r2db-api/conformance/conformance_adapter_r2db.py`:1479、`conformance-tests/test_c05_limit_declaration_agreement.py`:890 、と C2-1 で実装担当が時点の記録と分類したもの | 触らない。ガードの allowlist に (file、逐語トークン、記録である理由) で載せる。理由は分類表の「触らない理由」の列 (実装担当の分類分は報告の分類表) から取る。件数は固定しない | **M2-2**: allowlist から 1 件を外す → ガード赤 |
| C2-3 | 不正確な文 3 種: (a) `r2db-api/tests/test_audit_query.py`:2753-2757 と `MitateDB-api/tests/test_audit_query.py`:2533-2537 の「never surfaced past its own module」(捕捉は呼出し側: r2db は `structured.py` ×3・`postgres.py` が `schema_binding.py::_fail_constraint_declaration` で翻訳、MitateDB は `constraint_resolution.py::_validate_enum_declaration_with_path`)。(b) `r2db-api/tests/test_foundation.py`:504-506 (存在しない `service.py` の capabilities() comment を引く → comment を引かずに同じ事実を言う。出典は設計 `docs/design/R2DB_CCR13_STORAGE_V1.md`:156)。(c) `MitateDB-api/tests/test_limit_class_vocabulary.py`:148-168 全体の件数説明 (:165-166 の `cell.py x3` の列挙を含む。足し算本体は触らず現在地を足す: `_measure_request_bytes` ×3 と `_check_operation_depth` は `request_limits.py`、`_resolve_field_constraints` は `constraint_resolution.py`) | 分類表の (iv) の文の案を基に直す。assert の数値・期待値は変えない | 監査照合: `git diff` に assert 行の変更が無いこと (§9.4 の 3) と、直した文を §10 に逐語で残す |
| C2-4 | `MitateDB-api/README.md`:267-269 の `deployment_required` の文 (§8 の Y-6) | `MitateDB-api/src/mitatedb_api/capabilities_document.py` の現物を読んで事実に合わせる。読んだ file:line と新文を報告に書く | 監査照合: 新文と参照した file:line を §10 に逐語で残す |
| C2-5 | 再発防止ガード `tools/tests/test_no_line_number_position_refs.py` | 走査対象は `r2db-api/tests`、`r2db-api/conformance`、`MitateDB-api/tests`、`MitateDB-api/conformance`、`conformance-tests` の `*.py` と、両 peer の `README.md` (`r2db-api/README.md`、`MitateDB-api/README.md`)。除外: `conformance-tests/CONDITIONS.md`・`conformance-tests/README.md`・`conformance-tests/CONDITIONS_HISTORY.md` (Class C の条件表・履歴。`*.py` でないので走査に入らないが、除外の理由を Known gaps に書く)、`conformance-tests/test_conformance_docstring_position_refs.py` 自身 (fixture 文字列。ファイル単位で除外し Known gaps に書く)。走査対象の `\b[A-Za-z_][A-Za-z0-9_]*\.py:[0-9]+` を全件列挙し、allowlist (C2-2 の全件、逐語) 以外が 0 件であることを assert する。allowlist の各項目が現存することも assert する (陳腐化防止)。空振り禁止は §1.5 の 32 による。module docstring 末尾の `Known gaps` 3 行 (§1.12 の 71): 1 行目 = `file.py::symbol` の symbol の現存は見ない (と上記の除外)、2 行目 = その理由、3 行目 = 代わりに受け止めるもの (レビューの grep)。行をまたぐ bare `:NNN` と `.json:NNN` 形を検出しないことも 3 行目に書く | **M2-5**: 走査対象のテストファイルに `# see cell.py:12` を 1 行足す → 赤 |
| C2-6 | 対応表 | §9.6 の表で C2-1〜C2-5 に変異または監査照合が対応する | — (監査照合: 本表) |

### 9.4 受入条件

1. `tools/dev/pt.py -C .claude/worktrees/r39-refs --wait 300 -- tools/tests/test_no_line_number_position_refs.py conformance-tests/test_conformance_docstring_position_refs.py -q` が緑 (`tools/tests` は完了ゲートの testpaths 外なので `pt.py` で直接回す)。触ったテストファイルを `pt.py` で回して緑 (suite 全体は回さない。§1.6 の 42)。集計行を §10 に逐語で残す。
2. `tools/dev/mutate.py "$SP/r39-cs2-mutations.json" -C .claude/worktrees/r39-refs --wait 300`: M2-2・M2-5 が `expect=red got=red`、復元 sha256 一致。
3. `git diff` に `src/` のファイルが無い。assert 行 (`assert ` を含む行) の変更が無い (監査照合: `git diff -U0 | grep '^[-+].*assert '` が空。ただし assert のメッセージ文字列 (`test_limit_class_vocabulary.py` の f-string) は assert 行ではなく継続行であることを確認する)。
4. 完了ゲート (監督のみ)。
5. コードレビュー 1 起動 (共通契約の観点) と受け入れ監査 1 起動 (Class C)。

### 9.5 却下した代替案

- 行番号を現在値に引き直す — 次の編集で再び腐る。R-37 以降 4 回引き直している。
- `src/` のコメントも同じ変更セットで直す — 来歴検査器 (CH-ID の無い塊は変更が全て赤) と R-22 の受け皿に衝突する (§8 の Y-2)。
- ガードを conformance-tests 内に置く — 走査対象が両 peer の tests と README を含み、リポジトリ衛生の検査器は `tools/tests` が置き場 (前例 `tools/tests/test_leaf_import_direction.py`、`tools/tests/test_src_import_cycles.py`)。

### 9.6 CS-2 完了条件 → 変異 (§1.5 の 40)

| 完了条件 | 変異 / 監査照合 |
|---|---|
| C2-1 | M2-5 で代表 (ガードが行番号形を赤にすること)。置換後の symbol の現存は監査照合 (報告の grep 結果) |
| C2-2 | M2-2 |
| C2-3 | 監査照合 (§9.4 の 3 の `git diff` の出力と新文を §10 に逐語で残す) |
| C2-4 | 監査照合 (新文と参照した file:line を §10 に逐語で残す) |
| C2-5 | M2-5 |
| C2-6 | 監査照合 (本表) |

対応の無い行が無いことを最後の完了条件とする (C2-6)。

## 10. 記録 (統合時に監督が埋める)

- CS-1: (未実施)
- CS-2: (未実施)
