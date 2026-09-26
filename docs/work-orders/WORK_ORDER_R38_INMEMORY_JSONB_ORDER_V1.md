# 作業指示書 — R-38 r2db in-memory の ORDER BY と PostgreSQL jsonb 順序の一致

## 0. 版数・位置づけ

- **v1.0 (2026-09-26)。** 基点 local main `a1c1ee3` (契約 1.11.0。契約は変えない)。Change Set Manifest 形式 (`docs/design/ROADMAP_POST_PHASE7_V1.md` (以下 `RM`) §9 の 9)。
- 台帳: `RM` §8 の R-38。**規模 M** (`docs/work-orders/OPERATING_CONDITIONS.md` (以下 `OC`) §1.13 の 73・74)。**変更クラス B** (`tools/change_class.py` の実測: `r2db-api/src/r2db_api/inmemory_sort.py`・`r2db-api/tests/test_foundation.py`・`r2db-api/tests/test_postgres.py`・`tools/tests/test_leaf_import_direction.py` はいずれも B。`RM` §9 の 8)。`spec/`・`conformance-tests/`・`security/`・`_ISOMORPHIC_TARGETS` に触れない。
- 設計文書は持たない (規模 M は作業指示書 1 節。`OC` §1.13 の 74)。枠は本書 §1 (監督確定。出所は監督の scratchpad の `$SP/frame-r38.md`)。PostgreSQL の実測は同じ scratchpad の `$SP/pg-jsonb-order-measured.md` (監督 2026-09-26、PostgreSQL 16.14) で、テストに使う値集合と期待順序は本書 付録 A に写す。
- 手本: `docs/work-orders/WORK_ORDER_R111_CONTROL_ACTOR_REPAIR_V1.md` の節構成 (§0〜§5)。写さず節番号で指す。
- 役割: 実装担当 (テンプレ 2) 1 回、コードレビュー (テンプレ 5、Class B) 1 回 (`docs/work-orders/ROLE_PROMPT_TEMPLATES.md`)。**監査担当は起動しない** (規模 M かつ Class B。`OC` §1.13 の 74)。commit・完了ゲート・merge は監督。
- 1 WP、1 worktree (`.claude/worktrees/r38`、branch `r38`)、1 commit、main へ 1 merge。
- 並行チャット (worktree r101) は `tools/perf_baseline.py` と `docs/design/PERF_*` を触る。本件はそれらに触れない。

## 1. 監督確定事項

行番号は起草時 (`a1c1ee3`) の実測。以下 `IS` = `r2db-api/src/r2db_api/inmemory_sort.py`、`PS` = `r2db-api/src/r2db_api/postgres_sql.py`。

### 1.1 問題設定 (事実)

1. `IS`:47-50 の `_sort_key` は list / dict を `json.dumps(value, sort_keys=True, default=str)` のテキストで比較する。`_sort_rows` (ORDER BY、`r2db-api/src/r2db_api/structured.py`:917) と `_after_page_cursor` (keyset cursor、同:929) が共用する。
2. r2db の PostgreSQL backend は列を直接 `ORDER BY` し (`PS`:41-68 `_select_statement`、`_order_by_sql` :117-122)、cursor 述語も同じ列比較 (`_keyset_predicate_sql` :71-114)。untyped 列と `object` / `array` 型列は物理 jsonb (`_bind_value` :125-134、`Jsonb(value)`)。順序は PostgreSQL 自身の jsonb 比較 (`jsonb_util.c` の compareJsonbContainers)。
3. order_by に型の制限は無い (`r2db-api/src/r2db_api/paging.py`:56-91 `_resolve_order_by`、`structured.py`:890)。FIELD_TYPES = string / integer / number / boolean / object / array / json (`r2db-api/src/r2db_api/schema_binding.py`:34。json は untyped = None に変換、`structured.py`:326、:443)。
4. PostgreSQL 16.14 の実測 (付録 A の出所): 配列は要素数が先、その後に要素ごと。オブジェクトはペア数が先、その後に格納順 (キー長が短い順、同長は byte 順) のペアごとに key → value。要素・値の型順は Null < String < Number < Boolean < Array < Object (入れ子の JSON null は最小)。数値は numeric 比較 (`1 = 1.0`、`0 = -0.0`)。最上位の空配列 `[]` だけは scalar より小さい。現行 in-memory は `[1,2] < [3]`、`[10] < [9]` を真にする (PostgreSQL は両方偽)。
5. 既存テストは型間順位しか固定していない (`r2db-api/tests/test_foundation.py`:2252-2277、`r2db-api/tests/test_postgres.py`:2465-2486)。parity テスト `test_postgres.py`:3307-3325 は integer 列のみ。conformance (C-28 / C-30) は scalar 列のみ。in-memory と PostgreSQL の array / object の同型内順序を照合するテストは無い。
6. 本番プロセスは常に `PostgresCell` (`r2db-api/src/r2db_api/main.py`:519-529)。in-memory `ApplicationCell` は conformance の in-process plug `r2db-api` (`r2db-api/src/r2db_api/service.py`:105-115 の既定 cell_factory) と単体テストで使われる。
7. `IS` の docstring (:29、:35-37) は「PostgreSQL 自身の既定と一致する」と主張しており、array / object の同型内順序については誤り。
8. MitateDB-api には同種の食い違いは無い (着手条件の確認済み): json / object / array 型は SQLite・PostgreSQL 両 backend とも物理 TEXT (`MitateDB-api/src/mitatedb_api/postgres_types.py`:24)、書込み時に canonical JSON (`MitateDB-api/src/mitatedb_api/request_binding.py`:83-85)、ORDER BY は素の列 (`MitateDB-api/src/mitatedb_api/backend_sqlite.py`:661-664、`MitateDB-api/src/mitatedb_api/backend_postgres.py`:1460-1463)。両 backend が同じテキスト順で一致する。
9. 契約 `spec/data-service-api.v1.json` の `structured_operations.paging.ordering` は、string・number・boolean 以外の値 (型の違う untyped の値を含む) の比較を実装依存とし、2 実装が同じ位置に置くことを要求しない。peer 間 (r2db の jsonb 順 vs MitateDB の canonical text 順) の不一致は契約が明示的に許容している。conformance 条件は足さない (足すには契約の意味の決定 = Class C / D と依頼者裁定が要る。本件の範囲外。§1.5 の U-2)。
10. r2db の PostgreSQL backend は JSON null を SQL NULL として束縛する (`PS`:125-134)。したがって最上位の JSON null はどちらの backend にも格納されず、`_sort_key(None)` は SQL NULL を表す。付録 A の値集合は最上位の `null` を含まない。

### 1.2 守るべき条件

1. r2db の 1 実装の中で、in-memory backend と PostgreSQL backend が同じ入力に同じ順序 (ORDER BY と keyset cursor の両方) を返す。基準は実 PostgreSQL の jsonb 比較そのもの (代理指標ではなく実サーバーの出力と照合する。`OC` §1.7 の 52)。
2. 型間順位 (`_JSON_TYPE_RANK`: String < Number < Boolean < Array < Object) と SQL NULL の配置 (最大 = ASC で NULLS LAST) は現行どおり (`test_foundation.py`:2266-2273、`test_postgres.py`:2439-2486 の pin を壊さない)。
3. `_sort_key` / `_sort_rows` / `_after_page_cursor` の facade (`structured.py`:38 の再 export、`test_foundation.py`:2252 の identity pin) と leaf の import 制約 (`tools/tests/test_leaf_import_direction.py`:100 = `json`, `typing` のみ) を保つ。新しい import を足さない。`json` の import の扱いは §1.3 の D-1 の監督裁定による。
4. 契約・conformance・security・spec に触れない。`_ISOMORPHIC_TARGETS` に触れない (r2db 固有の leaf)。
5. src の新しい comment に経緯語 (WP / R-38 / phase / 日付 / 裁定名) を書かない。docstring の「PostgreSQL と一致する」主張は実測 (完了条件の test 名・件数) を得た後に書く (`OC` §1.5 の 34)。

### 1.3 決定と根拠

- **D-1.** `_sort_key` の list / dict の枝を、PostgreSQL の compareJsonbContainers と同じ構造的な総順序キーに置き換える (テキスト比較を廃止)。入れ子の値のキー関数 (仮称 `_jsonb_value_key`) を leaf に足す:
  - JSON null (入れ子) → 最小ランク。str → (rank, 文字列)。int / float (bool を除く) → (rank, 値) (Python の数値比較。`1 == 1.0` は PostgreSQL と同じ)。bool → (rank, int(値))。list → (rank, len, 要素キーの tuple)。dict → (rank, len, ペアの tuple。ペアは (キー文字列, 値キー)、並びは (len(キーの UTF-8 bytes), キーの UTF-8 bytes) の昇順 = jsonb の格納順)。ランクは Null < String < Number < Boolean < Array < Object。
  - 最上位: SQL NULL は現行どおり最大 (`(1, 0, "")`)。最上位の空配列 `[]` は非 NULL の scalar より小さい (実測 `[] < null < "x" < 0 < false < true < [0] < {}`) ので、`_sort_key([])` は string ランクより小さい位置にする (実装は `_JSON_TYPE_RANK` を変えずに `_sort_key` の中で扱う)。他の最上位値は現行の `(0, _JSON_TYPE_RANK[...], ...)` の形を保ち、list / dict の第 3 要素だけを新しい構造キーにする。
  - `json` の import (監督裁定): 残してよい。未使用なら消し、tools/tests の pin を合わせる。どちらも可。実装担当が実測して報告する。
  - 根拠: 基準は PostgreSQL の実挙動そのもの (§1.1 の 4)。cursor 比較 (`_after_page_cursor`) は同じ `_sort_key` を使うので同時に直る。
- **D-2.** 文字列の比較は現行どおり Python の codepoint 順 (入れ子のキー・値も同じ)。PostgreSQL は DB 既定照合 (使い捨てクラスタは en_US.UTF-8、`tools/testpg/dsa_testpg.py`:820) で比較するので、大文字小文字・非 ASCII を混ぜた文字列は本件の後も食い違う。本件では直さない (in-memory で locale 照合を再現する手段が無く、正しい直し方は PostgreSQL 側で順序を照合非依存にする = 製品挙動の変更で依頼者裁定が要る。§1.5 の U-1)。テストの文字列値は小文字 ASCII 英字と数字だけを使い、照合差を踏まない。
- **D-3.** テストは `r2db-api/tests` に 3 種: (T1) leaf 単体: 付録 A の値集合を `sorted(..., key=_sort_key)` して PostgreSQL の順序と一致すること。(T2) 実 PostgreSQL との差分テスト (`test_postgres.py`:3307 の `test_parity_order_by_null_placement_and_cross_type` と同じ形): untyped 列と `array` 型列・`object` 型列に同じ値集合を入れ、asc / desc の `order_by` の items が `PostgresCell` と in-memory `ApplicationCell` で一致し、かつ PostgreSQL 側の items が付録 A の順序そのものであること (non-vacuous: 行数 ≥ 値集合の件数を assert)。(T3) keyset cursor の parity: 同じ値集合を page_size 1〜2 で cursor を辿り、両 backend の連結列が一致し全行に届くこと (`_after_page_cursor` の検査)。
- **D-4.** `IS` の docstring の誤った主張を実測後に正す (module docstring は可。`_sort_key` の docstring の「matching PostgreSQL's own defaults」の範囲を「同型内の array / object も compareJsonbContainers の規則で」と書く)。`tools/check_comment_provenance.py --register` と `--base a1c1ee3 r2db-api/src/r2db_api/inmemory_sort.py` を実装担当が回し、出力の分類 ((1)〜(5)) を報告する。`docs/code-history/r2db-api/` に `inmemory_sort.md` は無い (登録済み block なし) ので correction は不要の見込み。実測で赤が出たら監督へ上げる。
- **D-5.** 変異は `tools/dev/mutate.py` の entry 1 件 = 単一 node、`-n` なし。M1 list を json テキスト比較に戻す (T1・T2 が赤)、M2 list の len を外す (要素ごとの比較だけ)、M3 dict のペア並びを codepoint 順 (len を外す)、M4 入れ子 null を最大ランクに、M5 最上位の空配列の特例を外す、M6 `_after_page_cursor` だけ json テキスト比較に戻す (T3 が赤、T1 は緑)。完了条件番号 → 変異 の表に監査照合の行を含め、対応の無い行を残さない。
- **D-6.** 台帳 R-39 の (1c) (降順の同値行、`false < true` の pin) は本件の範囲外のまま台帳 R-39 に残す。

### 1.4 却下した代替案と理由

- (a) 新しい conformance 条件 (次の C 番号) で全 plug の JSON 値の順序を固定する: 契約 (§1.1 の 9) が peer 間の一致を要求しておらず、条件を足すには契約の意味を決める依頼者裁定 (Class C / D) が要る。本件は 1 実装内の backend 一致に限る。
- (b) PostgreSQL backend 側を canonical JSON テキスト順 (`ORDER BY col::text` 等) に変える: 本番の順序を変え、jsonb の index 順と一致しなくなる。in-memory は本番ではないので、基準は PostgreSQL。
- (c) order_by に object / array / json 型列を禁止して回避する: 「制約で回避しない」(依頼者原則)。
- (d) `sort_keys=True` を保ったまま部分修正 (要素数だけ先に比べる等): 要素の数値をテキスト比較する誤りが残る。

### 1.5 未確定で依頼者判断待ちの選択肢

本件では決めない。

- **U-1. 文字列の照合順序 (D-2)。** r2db の PostgreSQL backend は DB 既定照合 (en_US.UTF-8)、in-memory は codepoint 順。
  - (i) PostgreSQL 側の ORDER BY / cursor 述語を `COLLATE "C"` 相当にして照合非依存にする (本番の text 順序が変わる。契約は照合を実装依存としているので契約文は不変)。
  - (ii) 現状維持し、in-memory は codepoint 順のままとする (差は文書化のみ)。
  - 監督が台帳に新規起票し、選択は依頼者。
- **U-2. peer 間 (r2db の jsonb 順 vs MitateDB の canonical text 順) の JSON 値の順序不一致。** 契約が許容している (§1.1 の 9)。監督裁定により起票せず、観察として引き継ぎ書に残す。依頼者が契約で揃えたければ別途。

### 1.6 記録の置き場

変異を持たない完了条件 (10〜14) の逐語記録は、設計文書が無いので本書 §5 に残す (`OC` §1.5 の 40)。log のパス・log のファイル名は本書に書かない (公開値スキャンの誤検知を避ける。パスは実装担当の報告と scratchpad にだけ置く)。traceback を貼らない (`OC` §1.9 の 63)。

## 2. WP-1 — in-memory の jsonb 構造順序キーと parity テスト

### 2.1 目的

`IS` の `_sort_key` の list / dict の枝を PostgreSQL の jsonb 比較と同じ構造キーに改め (D-1)、in-memory `ApplicationCell` と `PostgresCell` の ORDER BY と keyset cursor の順序を、実 PostgreSQL の出力との差分テストで一致させる (D-3)。

### 2.2 読むべき正本

- 本書 §1 と 付録 A
- `IS` 全文 (80 行)
- `PS`:41-134 (`ORDER BY`・keyset 述語・`_bind_value`)
- `structured.py`:38 (facade の再 export)、:917、:929 (呼び出し元)
- `test_foundation.py`:2252-2297 (facade identity と型間順位の pin。T1 の置き場の目安)
- `test_postgres.py`:2439-2486 (NULL 配置と型間順位の pin)、:2575-2600 (cursor を辿る形)、:3115-3116 (`_memory_cell()`)、:3307-3325 (T2・T3 の雛形の parity テスト。`make_cell(app_a)` と `_memory_cell()`)
- `tools/tests/test_leaf_import_direction.py`:100 (`inmemory_sort.py` の許容集合) と :243-268 (検査は「実 import ⊆ 許容集合」)
- `tools/tests/test_src_import_readers.py`:799 `test_reader_zero_imports_match_allow_table` (src の import で読み手が無いものは allow 表と集合で一致しなければ赤)
- `OC` §1.4・§1.5

### 2.3 現状と目標 (起草時の実測。着手時に再実測する)

| 箇所 | 現状 | 目標 |
|---|---|---|
| `_sort_key` の list 枝 (`IS`:47-48) | canonical JSON テキスト | (rank, len, 要素キーの tuple) (D-1) |
| `_sort_key` の dict 枝 (`IS`:49-50) | canonical JSON テキスト | (rank, len, 格納順のペアの tuple) (D-1) |
| 入れ子の値 | テキストの一部として比較 | `_jsonb_value_key` (仮称)。JSON null 最小、型順 Null < String < Number < Boolean < Array < Object (D-1) |
| 最上位の `[]` | array ランク (boolean より大) | 非 NULL の scalar より小さい (D-1) |
| SQL NULL (`None`)・`_JSON_TYPE_RANK`・scalar の枝 | 現行 | 変えない (§1.2 の 2) |
| `_after_page_cursor` (`IS`:61-80) | `_sort_key` を使う | 変えない (`_sort_key` の修正で同時に直る) |
| docstring (`IS`:1-14、:29-37) | 「PostgreSQL と一致」(array / object では誤り) | 実測後に正す (D-4) |
| `json` の import (`IS`:17) | 使用中 | D-1 の監督裁定どおり (2.4 のタスク 4) |
| in-memory と PostgreSQL の array / object の順序照合 | テスト無し | T1〜T3 (新規 8 node) |

### 2.4 タスク

実装担当が順に行う。

0. **基点の再実測。** 2.11 の `r2db-api/tests`・`-k "not MitateDB"`・`tools/tests`・2 つの `-k` 絞り込みを未変更の worktree で 1 回ずつ回し、集計行を §5 の完了条件 13 の欄に写す。
1. **テストを先に書く (D-3)。** 名前は 2.14 の表のとおり。T1 は node 名の接頭辞 `test_inmemory_sort_jsonb_`、T2・T3 は `test_parity_order_by_jsonb_` とする。既存ファイル (T1 は `test_foundation.py`:2277 の直後、T2・T3 は `test_postgres.py`:3325 の直後) に足すか新規ファイルにするかは実装担当の裁量。新規ファイルにしたときは 2.11 の `-k` 絞り込みの対象ファイルをそのファイルに読み替え、報告に書く。
   - **T1** (`_sort_key` を直接使う leaf 単体、PostgreSQL 不要): 4 node。
     - T1a 配列: 付録 A の A-3 と A-8 の列を `sorted(..., key=_sort_key)` した結果が付録 A の順序と一致。加えて `_sort_key([3]) < _sort_key([1, 2])`、`_sort_key([9]) < _sort_key([10])`、`_sort_key(1) == _sort_key(1.0)`、`_sort_key(0) == _sort_key(-0.0)` を個別に assert。
     - T1b オブジェクト: A-4・A-5・A-6 の列が一致。加えて `_sort_key({"a": 1, "b": 2}) == _sort_key({"b": 2, "a": 1})`。
     - T1c 入れ子の型順と入れ子の null: A-2・A-7 の列が一致。
     - T1d 最上位: A-1 の列が一致し、`_sort_key(None)` が A-1 のどの値のキーより大きい。
   - **T2** (`make_cell(app_a)` と `_memory_cell()` の差分、実 PostgreSQL): 3 node。付録 A の列 1 本ごとに entity を 1 つ作るか、列ごとに行を入れ直す。どちらも各列を `asc` と `desc` で `query(..., order_by=[{"field": <列>, "direction": d}])` し、(1) PostgreSQL の items と in-memory の items が等しい、(2) PostgreSQL の `asc` の items が付録 A の順序と等しい (`desc` はその逆順)、(3) items の件数が列の値の件数以上、を assert する。page_size は列の件数より大きくとる。
     - T2a untyped 列 (`create_entity` の `fields` に置く): A-1〜A-8 の全列。
     - T2b `array` 型列 (`add_field` の `field_type: "array"`): A-2・A-3・A-4。
     - T2c `object` 型列 (`field_type: "object"`): A-5・A-6・A-7。
   - **T3** (keyset cursor の parity、実 PostgreSQL): 1 node。T2a と同じ列・同じ列の置き方で、`page_size` 1 と 2、`asc` と `desc` のそれぞれについて `next_cursor` が `None` になるまで辿り (`test_postgres.py`:2586-2595 の形。上限回数を置く)、(1) 両 backend の連結列が等しい、(2) 各 backend の連結列が同じ backend の page 無し (`page_size` を列の件数より大きく) の items と等しい、(3) 連結列の件数が列の値の件数と等しい (全行に届く)、を assert する。
   - 値集合は付録 A にあるものだけを使う。r2db がいずれかの値の格納または cursor を拒否したときは、値を落とさず実装前に監督へ上げる (`OC` §1.5 の 37)。
2. **未変更の `IS` でテストが赤になることを確かめる。** タスク 1 のテストを、`IS` を変えずに 2.11 の 2 つの `-k` 絞り込みで回し、集計行と `FAILED` の要約行を §5 の完了条件 1 の欄に写す (T1a・T1b・T1c・T1d・T2a・T2b・T2c・T3 のうち赤になったもの。M1 は未変更の list 枝と同じ形なので、2.14 の M1 の実測もこれと整合するはず)。
3. **D-1 の実装。** `IS` に入れ子の値のキー関数を足し、`_sort_key` の list / dict の枝と最上位の `[]` の扱いを D-1 のとおりにする。`_JSON_TYPE_RANK`・SQL NULL の枝・scalar の枝・`_sort_rows`・`_after_page_cursor` の本体は変えない。
4. **`json` の import。** D-1 の監督裁定に従う。実測の事実: `json` が未使用になったまま import を残すと `tools/tests/test_src_import_readers.py`:799 が赤になる (読み手の無い import は allow 表と集合で一致しなければならない)。`test_leaf_import_direction.py`:100 の許容集合は部分集合検査 (:261) なので、`json` を外しても外さなくても緑。どちらを採ったかと `tools/tests` の集計行を報告する。
5. **docstring (D-4)。** 2.11 の変異と suite の実測を得た後に、`IS` の module docstring と `_sort_key` の docstring を正す。「PostgreSQL と一致する」と書く範囲に、完了条件の test 名と件数を引く (`OC` §1.5 の 34)。文字列の照合は一致の範囲外であること (D-2) も書く。新しい comment に経緯語を書かない (§1.2 の 5)。既存の docstring にある経緯語 (review 名等) の扱いは `check_comment_provenance.py` の分類に従い、赤になったら監督へ上げる。
6. **変異。** 2.14 の M1〜M6 を `$SP/r38-mutations.json` に書き、2.11 の `mutate.py` で回す。
7. **provenance。** 2.11 の `check_comment_provenance.py` 2 本を回し、出力の分類 ((1)〜(5)) を §5 に写す。
8. **suite。** 2.11 の `r2db-api/tests`・`-k "not MitateDB"`・`tools/tests` を回す。
9. **報告。** `pt.py` / `mutate.py` の出力行 (集計行・変異表) をそのまま貼る (`OC` §1.10 の 65)。§5 の欄を埋める。

### 2.5 触ってよいパス

- `r2db-api/src/r2db_api/inmemory_sort.py`
- `r2db-api/tests/test_foundation.py`、`r2db-api/tests/test_postgres.py` (新規テストの追記のみ。既存テストの本体は変えない)
- `r2db-api/tests/` 配下の新規ファイル (タスク 1 で新規ファイルを選んだときだけ)
- `tools/tests/test_leaf_import_direction.py` の `inmemory_sort.py` の許容集合 (:100) の 1 行 (タスク 4 で `json` を外したときだけ。D-1 の監督裁定の範囲)
- 本書 §5

### 2.6 触らないパス

`spec/`、`security/`、`conformance-tests/`、`MitateDB-api/`、`r2db-api/src/` の `inmemory_sort.py` 以外 (`postgres_sql.py`・`structured.py` を含む)、`r2db-api/conformance/`、`tools/` (2.5 の 1 行を除く。`tools/tests/test_src_import_readers.py` の allow 表を含む)、`docs/code-history/`、`RM`、`OC`、`CLAUDE.md`、`tools/perf_baseline.py`・`docs/design/PERF_*` (並行チャット)。これらに変更が要ると分かったら、実装前に監督へ上げる (`OC` §1.5 の 37)。

### 2.7 期待結果表 (commit の時点)

| 対象 | 期待 |
|---|---|
| 新規 T1 (4 node) | すべて ok |
| 新規 T2・T3 (4 node) | すべて ok |
| 既存の pin (`test_foundation.py`:2252、`test_postgres.py`:2439・:2465・:3307) | ok のまま、本体の差分なし |
| `r2db-api/tests` | 基点の件数 + 8、failed 0 |
| `conformance-tests -k "not MitateDB"` | 基点と同件数、failed 0 |
| `tools/tests` | 基点と同件数、failed 0 |
| `mutate.py` | 2.14 の全 entry が `as expected` |
| `check_comment_provenance.py` | `--register` OK、`--base` の分類を §5 に記録 |

### 2.8 完了条件 (assert 水準)

1. 同型の配列の比較は要素ごとの数値比較で行われ、テキスト比較ではない: T1a で A-3・A-8 の列の `sorted` が付録 A と一致し、`_sort_key([9]) < _sort_key([10])`、`_sort_key(1) == _sort_key(1.0)`、`_sort_key(0) == _sort_key(-0.0)`。未変更の `IS` で赤になったことを §5 に記録する (タスク 2)。
2. 配列は要素数が先: T1a で `_sort_key([3]) < _sort_key([1, 2])` と、A-3 の `[1,2] < [1,2,3]` を含む列の一致。
3. オブジェクトはペア数が先、その後に格納順 (キー長 → byte 順) のペアごとに key → value、キーの並べ方の違う同じオブジェクトは同値: T1b で A-4・A-5・A-6 の列が一致し、`_sort_key({"a": 1, "b": 2}) == _sort_key({"b": 2, "a": 1})`。
4. 入れ子の型順は Null < String < Number < Boolean < Array < Object で入れ子の JSON null が最小: T1c で A-2・A-7 の列が一致。
5. 最上位の `[]` は非 NULL の scalar より小さく、SQL NULL は最大のまま: T1d で A-1 の列が一致し、`_sort_key(None)` が A-1 の全値のキーより大きい。
6. untyped 列の ORDER BY が両 backend で一致し、PostgreSQL の出力が付録 A そのもの: T2a で A-1〜A-8 の各列について `asc` / `desc` の items が PostgreSQL と in-memory で等しく、PostgreSQL の `asc` の items が付録 A の順序 (`desc` は逆順) と等しく、件数 ≥ 列の値の件数。
7. `array` 型列で同じ: T2b で A-2・A-3・A-4 について 6 と同じ 3 点。
8. `object` 型列で同じ: T2c で A-5・A-6・A-7 について 6 と同じ 3 点。
9. keyset cursor の辿りが両 backend で一致し全行に届く: T3 で `page_size` 1・2 × `asc`・`desc` の各組について、両 backend の連結列が等しく、各 backend の連結列がその backend の page 無しの items と等しく、連結列の件数が列の値の件数と等しい。M6 のもとで T3 は赤、T1a は緑 (T3 だけが cursor の経路を守っていることの確認)。
10. 型間順位・SQL NULL の配置・facade・scalar の枝を壊していない: 既存の `test_foundation.py`:2252、`test_postgres.py`:2439・:2465・:3307 が ok で本体の差分が無く、`git diff a1c1ee3 -- r2db-api/src/r2db_api/inmemory_sort.py` に `_JSON_TYPE_RANK` の定義行・`value is None` の枝・bool / 数値 / str の枝・`_sort_rows`・`_after_page_cursor` の本体の変更が無い (監査照合: 集計行と diff の該当範囲の file:line を §5 に記録)。
11. docstring の主張は実測の後: `IS` の docstring の「PostgreSQL と一致する」主張の範囲が、完了条件 1〜9 の test 名と件数を引いて書かれ、文字列の照合が範囲外であることを書いている。新しい comment・docstring に経緯語が無い。`check_comment_provenance.py --register` が OK で、`--base a1c1ee3` の分類 ((1)〜(5)) を §5 に記録している (監査照合: 2 コマンドの出力行と docstring の file:line)。
12. import の制約: `IS` の import が `json`・`typing` (と `__future__`) の部分集合で、読み手の無い import が無い。`tools/tests` が基点と同件数で failed 0 (監査照合: タスク 4 の選択、`IS` の import 行の file:line、`tools/tests` の集計行を §5 に記録)。
13. suite: `r2db-api/tests -q` の件数が基点 + 8 で failed 0、`conformance-tests -k "not MitateDB" -q -n 5 --dist loadgroup` の件数が基点と同じで failed 0 (in-process plug `r2db-api` が新しい `_sort_key` で緑) (監査照合: タスク 0 と タスク 8 の集計行を §5 に記録)。
14. 2.14 の表に、変異も監査照合も持たない行が無い (監査照合: 本表)。

### 2.9 非空振り要件

- T1 の各列の assert は `sorted` の結果と付録 A の列の等号で比べ、入力は付録 A の列を並べ替えたもの (例: 逆順と固定の置換の 2 通り) とする (入力が既に期待順だと、キーが恒等でも緑になる)。
- 同値の組 (`1` と `1.0`、`0` と `-0.0`、`0.0` と `0`、`{"a":1,"b":2}` と `{"b":2,"a":1}`) は Python の `==` で比べ、同値行の並び (台帳 R-39 の (1c)、D-6) は固定しない。
- T2・T3 は各列の件数を assert する (T2 は ≥、T3 は ==)。PostgreSQL 側の items を付録 A と比べる assert を省かない (両 backend が同じように誤っても緑になる形にしない)。
- T3 は辿った page の数が 1 より大きいことを assert する (`page_size` が列の件数以上だと cursor を 1 度も使わない)。

### 2.10 同型性テストの対象

なし。`_ISOMORPHIC_TARGETS` を増減しない。`IS` は r2db 固有の leaf で、MitateDB に同名の helper を置かない。

### 2.11 道具の引数と集計行の期待形

リポジトリ root から root の `.venv` で起動する。`SP` は監督が発注時に渡す scratchpad。

```
./.venv/bin/python tools/dev/pt.py -C .claude/worktrees/r38 --wait 300 -- r2db-api/tests/test_foundation.py -q -k inmemory_sort
./.venv/bin/python tools/dev/pt.py -C .claude/worktrees/r38 --wait 300 -- r2db-api/tests/test_postgres.py -q -k "order_by or parity_order"
./.venv/bin/python tools/dev/pt.py -C .claude/worktrees/r38 --wait 300 -- r2db-api/tests -q
./.venv/bin/python tools/dev/pt.py -C .claude/worktrees/r38 --wait 300 -- conformance-tests -k "not MitateDB" -q -n 5 --dist loadgroup
./.venv/bin/python tools/dev/pt.py -C .claude/worktrees/r38 --wait 300 -- tools/tests -q
./.venv/bin/python tools/dev/mutate.py "$SP/r38-mutations.json" -C .claude/worktrees/r38
./.venv/bin/python .claude/worktrees/r38/tools/check_comment_provenance.py --register
./.venv/bin/python .claude/worktrees/r38/tools/check_comment_provenance.py --base a1c1ee3 r2db-api/src/r2db_api/inmemory_sort.py
```

- すべて前景で `timeout` 600000 を明示する (`OC` §1.5 の 39)。`tools/tests` は完了ゲートに含まれないので、ここで必ず回す。
- 集計行の期待形 (`<...>` は着手時に基点で実測して埋める):

| コマンド | 期待形 |
|---|---|
| `test_foundation.py -k inmemory_sort` | `pt: <基点 + 4> passed` (起草時の grep で該当 def は 1 件) |
| `test_postgres.py -k "order_by or parity_order"` | `pt: <基点 + 4> passed` (起草時の grep で名前に `order_by` / `parity_order` を含む def は 7 件) |
| `r2db-api/tests` | `pt: <基点 + 8> passed` (基点の参考値: R-110 の記録 `1470 passed`) |
| `-k "not MitateDB"` | `pt: <基点と同じ> passed` (基点の参考値: R-110 の記録 `776 passed`) |
| `tools/tests` | `pt: <基点と同じ> passed` (基点の参考値: R-110 の記録 `591 passed`) |

- 変異ファイルの entry は **単一の node id、`-n` なし**とする (`mutate.py` は最初の赤で止まる)。1 つの変異を複数の node で赤にしたいときは、同じ `old` / `new` の entry を node ごとに分ける (2.14 の M1a / M1b 等)。conformance 全体・`tools/dev/gate.py`・`tools/dev/finalize.py` は監督だけが回す。

### 2.12 使用テンプレート

実装 = テンプレ 2、コードレビュー = テンプレ 5 (Class B)。受け入れ監査は起動しない (§0)。監査照合の行 (完了条件 10〜14) は、監督が §5 の逐語記録を道具の出力 (`pt.py`・`mutate.py`・`check_comment_provenance.py`・`git diff`) と突合する (`OC` §1.13 の 74)。

### 2.13 禁止事項

- suite 全体 (`conformance-tests` 全体、root suite) を回さない (`OC` §1.6 の 42)。`tools/dev/gate.py` と `tools/dev/finalize.py` を実行しない (`OC` §1.11 の 70)。
- commit・push・merge をしない。下請けの Agent を使わない (`OC` §1.7 の 47)。
- `spec/`・`conformance-tests/`・`security/`・`tools/`・`MitateDB-api/` に触れない。例外は `tools/tests/test_leaf_import_direction.py` の `inmemory_sort.py` の許容集合の 1 行だけで、D-1 の監督裁定の範囲に限る (2.5)。
- 本書 §1 に無い機構 (照合の再現、PostgreSQL 側の SQL の変更、order_by の型制限等) を足さない。必要と判断したら実装前に上げる (`OC` §1.5 の 37)。
- src の comment・docstring に経緯語 (WP / R-38 / phase / 日付 / 裁定名) を書かない。
- テストの文字列値に付録 A 以外の値、大文字・非 ASCII・記号を使わない (D-2)。
- 変異による一時変更を残さない (復元は `mutate.py` に任せ、`git checkout --` を使わない)。
- log のパス・log 名・traceback・作業機の絶対パスを本書に書かない (§1.6、`OC` §1.9)。

### 2.14 完了条件番号 → 変異

変異は `IS` の 1 箇所を壊す。`old` / `new` の文字列は実装後のコードから実装担当が書く (`old` は元ファイルで一意)。node の置き場は 2.4 のタスク 1 の裁量に従い、報告に node id を書く。

| 完了条件 | 変異 (`IS`:操作) | 赤になる test (期待) |
|---|---|---|
| 1 | M1a: list の枝を `json.dumps(value, sort_keys=True, default=str)` のテキスト比較に戻す | T1a `test_inmemory_sort_jsonb_array_order_matches_postgres` (red) |
| 2 | M2: list のキーから len を外す (要素キーの tuple だけで比べる) | T1a (red) |
| 3 | M3a: dict のペアの並びを codepoint 順にする (キーの UTF-8 bytes の len を外す) | T1b `test_inmemory_sort_jsonb_object_order_matches_postgres` (red) |
| 4 | M4: 入れ子の JSON null を最大ランクにする | T1c `test_inmemory_sort_jsonb_nested_type_order_and_null_minimum` (red) |
| 5 | M5: 最上位の `[]` の特例を外す (array ランクに戻す) | T1d `test_inmemory_sort_jsonb_top_level_empty_array_below_scalars` (red) |
| 6 | M1b: M1a と同じ変異 | T2a `test_parity_order_by_jsonb_untyped_column` (red) |
| 7 | M2b: M2 と同じ変異 | T2b `test_parity_order_by_jsonb_array_column` (red) |
| 8 | M3b: M3a と同じ変異 | T2c `test_parity_order_by_jsonb_object_column` (red) |
| 9 | M6: `_after_page_cursor` の中の比較だけを json テキスト比較に戻す (`_sort_key` 自体は変えない) | T3 `test_parity_order_by_jsonb_keyset_cursor_walk` (red) |
| 9 | M6c: M6 と同じ変異 | T1a (green。M6 が `_sort_key` を壊していないことの対照) |
| 10 | 監査照合: 既存の pin 4 node の集計行と、`git diff a1c1ee3 -- r2db-api/src/r2db_api/inmemory_sort.py` の該当範囲 (§5) | — |
| 11 | 監査照合: `check_comment_provenance.py` 2 本の出力行と docstring の file:line (§5) | — |
| 12 | 監査照合: タスク 4 の選択、import 行の file:line、`tools/tests` の集計行 (§5) | — |
| 13 | 監査照合: `r2db-api/tests` と `-k "not MitateDB"` の基点と実装後の集計行 (§5) | — |
| 14 | 監査照合: 本表 | — |

## 3. merge (監督)

1. 実装担当の報告 → コードレビュー (テンプレ 5、Class B) → 差し戻しはファイルで (`OC` §1.7 の 49)。
2. 完了ゲート `./.venv/bin/python tools/dev/gate.py -C .claude/worktrees/r38 --label r38` を 1 回。集計行を本書 §5 に足す。`tools/tests` は完了ゲートに含まれないので `finalize.py` に `--tools-tests` を付ける。
3. `RM` v1.124 (見込み。他チャットと衝突したら merge 時に renumber): §8 の R-38 行に【追記】(閉止。完了条件・変異の結果・`pt.py` の集計行・完了ゲートの集計行) する。§1.5 の U-1 (文字列の照合順序) を新規行として起票する (番号は merge 時に採番、選択肢 (i)(ii) を両論のまま)。版数ログを 5 行に保ち、6 版目の行を `docs/archive/docs/design/ROADMAP_POST_PHASE7_V1__VERSION_LOG.md` へ移す (`OC` §1.16 の 78)。`security/CONTROL_MAPPING.md` は触らない (制御は変わらない)。
4. 引き継ぎ書 `docs/work-orders/HANDOVER_20260926_FABLE2.md` に本件の節を書き、§1.5 の U-2 を観察として残す。同じ変更セットで `docs/work-orders/HANDOVER_20260925_FABLE2.md` を `docs/archive/docs/work-orders/` へ `git mv` する (最新 2 通は `HANDOVER_20260926_FABLE.md` と `HANDOVER_20260926_FABLE2.md`。`OC` §1.16 の 78)。
5. `./.venv/bin/python tools/dev/finalize.py -C .claude/worktrees/r38 --branch r38 --tools-tests -m <message file> --allow <触ったパス>` で commit と merge (1 commit)。`--allow` は 2.5 のうち実際に触ったパスと、`RM`・版数ログの記録ファイル・引き継ぎ書 2 通 (新規と回転)・本書。

## 4. 訂正註

(実施中に本書の誤り・発注後の監督裁定が生じたらここへ追記する。本文は書き換えない。`OC` §1.8 の 57。)

**訂正註 1 (コードレビュー F2、監督裁定「直す」)**: §1.3 の D-1 の数値の枝の記述(「int / float (bool を除く) → (rank, 値) (Python の数値比較。`1 == 1.0` は PostgreSQL と同じ)」) は 2**53 を超える値では誤り。実測 (PostgreSQL 16.14、psycopg `Jsonb` 束縛 = r2db `_bind_value` と同じ経路): `[2.0**60] < [1152921504606846990]` は PG で偽 (PG 側の値は `1152921504606847000`。`json.dumps` の最短表現 `1.152921504606847e+18` を numeric として読むため)。Python の生の値比較では真。最上位の数値の枝でも同じ (`2.0**60 < 1152921504606846990` は PG で偽)。修正: `_sort_key` (最上位) と `_jsonb_value_key` (入れ子) の数値の枝を、PostgreSQL が実際に受け取る JSON テキストの数値そのもの (`decimal.Decimal(repr(value))` -- float、`decimal.Decimal(value)` -- int) で比べるように変える。`Decimal(1) == Decimal("1.0")`、`Decimal("-0.0") == Decimal(0)` は真なので、既存の数値の同値は保たれる。T2 (実 PostgreSQL との差分テスト) にはこの 2**53 超の値を足さない: PostgreSQL は float を numeric `1152921504606847000` として格納し、読み戻す値そのものが in-memory の float と等しくならないため (順序ではなく格納時の丸めの話で、本件 (backend 間の順序の一致) の範囲外)。

**訂正註 2 (コードレビュー F3、監督裁定)**: §2.13 の禁止事項「テストの文字列値に付録 A 以外の値、大文字・非 ASCII・記号を使わない (D-2)」は、**キーが比較の各位置で等しく、値の比較だけで大小が決まる場合に限り**、非 ASCII のキーを許す例外を持つ (理由: 文字列の照合順序 (D-2) は key どうしの比較にだけ掛かり、この例外に当たる比較は 1 番目に並ぶペアの key が一致し value で決まるため照合非依存)。付録 A に次を A-9 として追記する (出所: 監督実測、PostgreSQL 16.14、review 裁定ファイル F3): `{"a": 1, "é": 2} < {"a": 2, "é": 1} < {"ab": 1, "é": 2} < {"ab": 2, "é": 1}` (`é` は UTF-8 で 2 byte。`a` (1 byte) が `é` より先、`ab` (2 byte) と `é` (2 byte) は byte 順で `ab` が先。各比較は 1 番目のペアの key が等しく value で決まるので照合非依存)。codepoint 数で並べると `é` が先になり順序が逆転する (キー長の規則が UTF-8 byte 長であることを固定する、変異 M3c)。

**訂正註 3 (2026-09-26、監督)**: §3 の 3・4 は起草後に main が動いた (別チャットの R-41 が main `90b9d93` で台帳 v1.124、`HANDOVER_20260926_FABLE2.md`、`HANDOVER_20260925_FABLE2.md` の回転、`COLLECTION_FLOOR` 4198 → 4233 を取った) ため次のとおり読み替える: 台帳は **v1.125** (回転する版数ログの行は v1.120)、新規行は **R-112**、引き継ぎ書は **`HANDOVER_20260926_FABLE3.md`**、回転するのは **`HANDOVER_20260926_FABLE.md`** (最新 2 通は FABLE2 と FABLE3)。main を r38 に取り込んだ最終ツリーで完了ゲートを再実行する。

## 5. 実施記録

(監査照合の逐語記録 — 実行したコマンドと集計行、または file:line — を完了条件番号ごとに記す。log のパス・log 名・traceback は書かない (§1.6)。完了ゲートの集計行は監督が記す。)

**完了条件 1** (未変更の `IS` での赤、タスク 2):

- `r2db-api/tests/test_inmemory_sort_jsonb_order.py -q` (新規 4 node、`IS` 未変更): `pt: 4 failed in 0.04s`。FAILED: `test_inmemory_sort_jsonb_array_order_matches_postgres`、`test_inmemory_sort_jsonb_object_order_matches_postgres`、`test_inmemory_sort_jsonb_nested_type_order_and_null_minimum`、`test_inmemory_sort_jsonb_top_level_empty_array_below_scalars`。
- `r2db-api/tests/test_postgres.py -q -k "order_by or parity_order"` (`IS` 未変更): `pt: 4 failed, 7 passed, 206 deselected in 2.05s`。FAILED: `test_parity_order_by_jsonb_untyped_column`、`test_parity_order_by_jsonb_array_column`、`test_parity_order_by_jsonb_object_column`、`test_parity_order_by_jsonb_keyset_cursor_walk`。7 passed は起草時の grep 件数 (7 件) と一致。
- コードレビュー差し戻し (F2/F3) で T1a/T1b/T1d に足した assert (訂正註 1・2) は、この赤測定より後に追加したため個別の赤測定は取っていない。非空振りは変異 M7 (T1a)・M3c (T1b) で確認する (下)。

**完了条件 1〜9** (変異表、`mutate.py` の出力行。コードレビュー差し戻しで M3c・M7 を追加、全 12 entry を再実行):

```
M1a      expect=red   got=red       OK  | 1 failed in 0.03s | restore=ok
M2       expect=red   got=red       OK  | 1 failed in 0.03s | restore=ok
M3a      expect=red   got=red       OK  | 1 failed in 0.03s | restore=ok
M4       expect=red   got=red       OK  | 1 failed in 0.03s | restore=ok
M5       expect=red   got=red       OK  | 1 failed in 0.02s | restore=ok
M1b      expect=red   got=red       OK  | 1 failed in 0.42s | restore=ok
M2b      expect=red   got=red       OK  | 1 failed in 0.35s | restore=ok
M3b      expect=red   got=red       OK  | 1 failed in 1.20s | restore=ok
M6       expect=red   got=red       OK  | 1 failed in 0.35s | restore=ok
M6c      expect=green got=green     OK  | 1 passed in 0.01s | restore=ok
M3c      expect=red   got=red       OK  | 1 failed in 0.03s | restore=ok
M7       expect=red   got=red       OK  | 1 failed in 0.03s | restore=ok
mutate: 12 mutations, 12 as expected, restores verified 1/1 files (sha256 x2), grep counts unchanged (n/a for 1 edits whose lines all exist in the pristine file)
```

対応: M1a/M1b→1・6、M2/M2b→2・7、M3a/M3b/M3c→3・8、M4→4、M5→5、M6/M6c→9、M7→1 (訂正註 1 の数値の枝)。

コードレビュー側の変異 (`review-r38.md` 観点3、F3 裁定 §5 記録): RV1 (最上位 dict の len を外す)・RV2 (入れ子 dict の len を外す)・RV3 (keys-first) はいずれも T1b で red (テストは非空振り)。RV4 (キー長を UTF-8 bytes から codepoint 数に変える、`M3c` と同じ変更) は A-9 追加前は green (ASCII のみの列では byte 長と codepoint 数が一致するため区別できない既知の穴) だったが、A-9 (非 ASCII キー) を追加した後の `M3c` では red になり、キー長規則が UTF-8 byte 長であることを固定した。

**完了条件 10** (既存の pin と diff の範囲):

`test_foundation.py:2252`(`test_inmemory_sort_leaf_preserves_structured_facade_and_null_rank`)、`test_postgres.py:2439`(`test_order_by_null_placement_matches_application_cell_defaults`)・`:2465`(`test_order_by_untyped_column_uses_jsonb_cross_type_order`)・`:3307`(`test_parity_order_by_null_placement_and_cross_type`) は実装後も同じ行番号で存在し、`r2db-api/tests -q` の集計 (完了条件 13) に含まれ全件 passed。`git diff a1c1ee3 -- r2db-api/src/r2db_api/inmemory_sort.py` (F2 反映後、再実測): `_JSON_TYPE_RANK` の定義行 (`IS`:25)・`value is None:` の枝 (`_sort_key` 内、`return (1, 0, "")`、`IS`:94)・bool/str の枝・`_sort_rows`(`IS`:150)・`_after_page_cursor`(`IS`:157) の本体は diff のハンク外 (無変更、コンテキスト行としてのみ現れる箇所を確認した)。diff が触れるのは `import json`→`from decimal import Decimal` の置換、新規関数 `_numeric_key`(`IS`:28)、`_sort_key` の docstring と数値・list/dict の枝、新規関数 `_dict_pair_key`(`IS`:114)・`_jsonb_value_key`(`IS`:126) の数値の枝のみ。

**完了条件 11** (provenance 2 本の出力と docstring の file:line。F1 の分類訂正を反映し再実行):

- `--register`: `comment provenance register OK: 92 files scanned, 433 CH-IDs`(分類: 問題なし)。
- `--base a1c1ee3 r2db-api/src/r2db_api/inmemory_sort.py` (F2 反映後、再実測):
  ```
  FAIL (§4.1 (1)) r2db-api/src/r2db_api/inmemory_sort.py:17 code changed (AST differs, docstrings excluded)
  FAIL (§4.1 (2)) r2db-api/src/r2db_api/inmemory_sort.py:46 scope/anchor ('_sort_key', 'stmt#1'): the sequence of CH-ID-less blocks changed (old 1, new 1) -- a block was added, removed, or moved to a different statement without a CH-ID reference
  ```
  分類 (コードレビュー F1 裁定、訂正): :17 の (1) は `import json` → `from decimal import Decimal` の置換によるコード変化 (期待どおり、コード自体の変更であって経緯コメントの問題ではない)。:46 の (2) は既存の CH-ID 無し docstring の内容変更 (`old 1, new 1`)。設計 `docs/design/CODE_COMMENT_PROVENANCE_V1.md` §4.1 (2) の D-2 により赤 (旧版に在る対象への追加は今までどおり赤)。R-110 の読み替え (`docs/work-orders/WORK_ORDER_R110_UNDECLARED_FIELD_REFUSAL_V1.md` §4 訂正註 2 の末尾: コード変更を伴う WP では完了条件 30 を「(5) 経緯語 0 と `--register` OK」と読み替える監督裁定) に従う。`docs/code-history/r2db-api/inmemory_sort.md` は無く、経緯語の削除を伴わないので登録も correction も不要 (前回の記録が引いた Known gap 3「a first docstring on an existing function」は "old 0, new 1" の場合に当たり、本件 "old 1, new 1" には当たらない誤りだったので訂正した)。
  docstring の file:line: `_sort_key` の docstring (`IS`:45-92)。完了条件 1〜9 の test 名と件数への言及は `IS`:73-78 (`test_inmemory_sort_jsonb_order.py` の 4 test、`test_postgres.py` の `test_parity_order_by_jsonb_*` 4 test、計 8 test)。数値は `Decimal` で比べる旨は `IS`:80-85。文字列照合が範囲外である旨は `IS`:87-91。

**完了条件 12** (`json`/`decimal` の import の選択と `tools/tests`):

選択: `json` は list/dict の枝から `json.dumps` 呼び出しが消え未使用になったため、import を外した (D-1 監督裁定の「消す」側)。コードレビュー差し戻し (F2、訂正註 1) で数値の枝を `decimal.Decimal` に変えたため `from decimal import Decimal` を追加 (読み手のある import)。`IS`:17-18 は `from decimal import Decimal` / `from typing import Any` のみ (`import json` 無し)。`tools/tests/test_leaf_import_direction.py:100` の許容集合を `frozenset({"json", "typing"})` → `frozenset({"decimal", "typing"})` に更新 (1 行)。`tools/tests/test_src_import_readers.py` の allow 表には触れていない (`decimal` は `_numeric_key` に読み手があるため対象外、実測どおり)。`tools/tests -q`: 基点 `pt: 591 passed in 58.58s`、F2 前の実装 `pt: 591 passed in 54.00s`、F2/F3 反映後の再実行 `pt: 591 passed in 303.35s` (基点と同数、failed 0。実行時間の増加は並行チャットとの共有 PostgreSQL クラスタの混雑によるもので、collection 件数・failed 数への影響なし)。

**完了条件 13** (基点と実装後の集計行。F2/F3 反映後に再実行):

| コマンド | 基点 | F2 前の実装後 | F2/F3 反映後 (最終) |
|---|---|---|---|
| `r2db-api/tests -q` | `1470 passed in 115.54s (0:01:55)`(監督実測、未変更 worktree) | `pt: 1478 passed in 111.39s` | `pt: 1478 passed in 421.28s (0:07:01)` (基点 + 8、failed 0。時間増は並行負荷) |
| `-k "not MitateDB" -q -n 5 --dist loadgroup` | `pt: 776 passed in 124.98s (0:02:04)` | `pt: 776 passed in 140.19s` | 1 回目 `pt: 1 failed, 775 passed in 227.76s` (`test_testpg_cluster.py::test_peer_root_starts_and_cleans_up_its_own_cluster` が `psycopg.OperationalError: connection is bad … No such file or directory` で失敗。throwaway PostgreSQL の socket が並行チャットの負荷で消えた基盤側の flake、`inmemory_sort.py` に無関係)。再実行 `pt: 776 passed in 214.55s` (基点と同数、failed 0)。 |
| `tools/tests -q` | `pt: 591 passed in 57.03s` | `pt: 591 passed in 54.00s` | `pt: 591 passed in 303.35s` (基点と同じ、failed 0) |

**完了ゲート** (監督):

## 付録 A. 値集合と PostgreSQL の期待順序

出所: `$SP/pg-jsonb-order-measured.md` (監督 2026-09-26、PostgreSQL 16.14、DB 既定照合 en_US.UTF-8)。各列は PostgreSQL の jsonb の昇順 (`<` は厳密に小さい、`=` は PostgreSQL が等しいと判定)。値は実測表にあるものだけで、文字列は小文字 ASCII 英字と数字だけのものに絞った (実測表のうち最上位の `null` は §1.1 の 10 により、`[""]` は文字列の制約により除いた)。

| 列 | 昇順 | 実測表の節 |
|---|---|---|
| A-1 最上位の型間 | `[] < "x" < 0 < false < true < [0] < {} < {"a": 0}` | 型順 (最上位) |
| A-2 入れ子の型順 | `[null] < ["a"] < [-1] < [0] < [1.5] < [false] < [true] < [[]] < [{}]` | 型順 (要素の中) |
| A-3 配列 | `[] < [null] < ["b"] < [3] < [9] < [10] < [true] < [[1]] < [{"a": 1}] < ["a", "b"] < ["a", 1] < [1, "a"] < [1, 2] < [1, 2, 3]` | 配列 |
| A-4 配列の中のオブジェクト | `[{"a": 1}] < [{"a": 2}] < [{"b": 0}] < [{"a": 1, "b": 1}]` | 配列 |
| A-5 オブジェクト | `{} < {"a": 1} < {"a": 2} < {"b": 0} < {"b": 1} < {"a": 1, "b": 2}` | オブジェクト |
| A-6 オブジェクトの格納順 | `{"a": 1, "b": 2} < {"a": 1, "bb": 0} < {"a": 1, "c": 0} < {"a": 9, "c": 0} < {"b": 0, "c": 0} < {"b": 1, "aa": 2} < {"b": 2, "aa": 1} < {"c": 0, "ab": 1}` | オブジェクト |
| A-7 オブジェクトの値の型 | `{"a": null} < {"a": "s"} < {"a": 0} < {"a": true} < {"a": [3]} < {"a": [1, 2]} < {"a": {"x": 1}}` | オブジェクト |
| A-8 数値 | `-0.00001 < 0.0 = 0 < 1 = 1.0 < 1.5 < 9 < 10 < 12345678901234567890 < 100000000000000000000` | 数値 |

- 同値: `{"a": 1, "b": 2} = {"b": 2, "a": 1}`、`1 = 1.0`、`0 = -0.0`。
- 偽であること: `[1, 2] < [3]`、`[10] < [9]` (どちらも `=` も偽)。
- A-6 の格納順: `{"b": 1, "aa": 2}` は `b`, `aa` の順、`{"c": 0, "ab": 1}` は `c`, `ab` の順 (短いキーが先)。
