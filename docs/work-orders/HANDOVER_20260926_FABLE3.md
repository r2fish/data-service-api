# 引き継ぎ — 2026-09-26 (R-38: r2db in-memory の ORDER BY と PostgreSQL jsonb 順序の一致。Class B、規模 M、1 WP)

本書は前書の全項を写さない。生きている事項だけを載せる。恒久の運用規律は `docs/work-orders/OPERATING_CONDITIONS.md` (以下 `OC`)。前書は `HANDOVER_20260926_FABLE2.md` (R-41 チャット。同日の別チャット)。本書は `docs/work-orders/HANDOVER_20260926_FABLE3.md`。以下 `RM` = `docs/design/ROADMAP_POST_PHASE7_V1.md`、作業指示書 = `docs/work-orders/WORK_ORDER_R38_INMEMORY_JSONB_ORDER_V1.md`。本書で D-N / U-N / M-N / T-N / 完了条件 / 付録 A と書くときは作業指示書のものを指す (`OC` §1.8 の 59)。

記録: `docs/archive/docs/work-orders/HANDOVER_20260926_FABLE.md` (R-111 チャット。本変更セットで回転)

## 1. 現在地

- 本チャット (2026-09-26) は `RM` の R-38 だけを扱った。worktree r38、branch r38、基点 local main `a1c1ee3`。main はその後 R-41 の merge (`90b9d93`) で動いた。本変更セットは main を取り込み、完了ゲートは取り込み後の最終ツリーで回す。作業指示書 v1.0 + 訂正註 2 件 (作業指示書 §4)、1 WP、**Class B・規模 M** (監査担当は起動しない。`OC` §1.13 の 74)。
- 役割とモデル: explorer (sonnet、2 体)、drafter / reviewer (opus、transcript の `"model"` 欄は `claude-opus-5-5`)、implementer (sonnet)。commit・完了ゲート・merge は監督。
- 直したもの: `r2db-api/src/r2db_api/inmemory_sort.py` の `_sort_key` (list / dict の枝を jsonb 構造順序に、数値の枝を `Decimal(repr)` に、`json` → `decimal` の import)、新規 `_numeric_key` / `_dict_pair_key` / `_jsonb_value_key`。新規テスト 8 node (T1a〜T1d leaf 単体 `r2db-api/tests/test_inmemory_sort_jsonb_order.py`、T2a〜T2c・T3 実 PostgreSQL parity `r2db-api/tests/test_postgres.py` 末尾)。`tools/tests/test_leaf_import_direction.py` の許容集合 `{"decimal","typing"}`。
- 集計行 (実装担当、差し戻し反映後の最終):
  - T1 `test_inmemory_sort_jsonb_order.py`: `pt: 4 passed in 0.14s`
  - `test_postgres.py -k "order_by or parity_order"`: `pt: 11 passed, 206 deselected in 5.03s`
  - `r2db-api/tests`: `pt: 1478 passed in 421.28s (0:07:01)` (基点 1470 + 8)
  - `-k "not MitateDB" -n 5 --dist loadgroup`: 1 回目 `pt: 1 failed, 775 passed in 227.76s` (`test_testpg_cluster.py::test_peer_root_starts_and_cleans_up_its_own_cluster` の基盤 flake。throwaway PostgreSQL の socket 消失で、`inmemory_sort.py` に無関係)、再実行 `pt: 776 passed in 214.55s` (基点と同数)
  - `tools/tests`: `pt: 591 passed in 303.35s` (基点と同数)
  - 変異: `mutate: 12 mutations, 12 as expected, restores verified 1/1 files (sha256 x2), grep counts unchanged` (M1a/M1b/M2/M2b/M3a/M3b/M3c/M4/M5/M6/M6c/M7)。レビュー側変異 RV1〜RV4 (作業指示書 §5)。
  - 完了ゲート (監督、solo、使い捨てクラスタ): `label r38 (基点 a1c1ee3 のツリー): gate: 4211 passed, 2 subtests passed in 392.77s (0:06:32), judge=PASS, pg_database/pg_roles diff 0 (4203 + 8); label r38b (main 90b9d93 (R-41) を取り込んだツリー、記録の編集前): gate: 4241 passed, 2 subtests passed in 483.21s (0:08:03), judge=PASS, pg_database/pg_roles diff 0 (main 90b9d93 の 4233 + 新規 8)`
- 台帳 `RM` **v1.125** (v1.124 は R-41。R-38 閉止 + 新規行 **R-112** (merge 時に main の台帳 (v1.124) に R-112 が無いことを監督が確認して確定))。`security/CONTROL_MAPPING.md` は **3.4 のまま** (制御は変わらない)。契約 **1.11.0 のまま**。
- 本書は merge 前に起草した。main への merge は §4 の報告の後 (作業指示書 §3)。
- push は停止中 (GitHub 課金上限)。ローカル commit と main への merge のみ。
- 並行チャット R-101 (worktree r101、`tools/perf_baseline.py`・`docs/design/PERF_*`) と触るファイルの重なりなし。
- 本チャットの裁定の材料は監督チャットの scratchpad の `rulings-r38.md` (「裁定」節に逐語で転記済み)。

## 2. 本チャットで閉じたもの

| 件 | 結果 | 記録 |
|---|---|---|
| 着手条件の確認 | MitateDB-api には同種の食い違い無し: json 型は両 backend とも TEXT 列 + canonical JSON、素の列を ORDER BY | 作業指示書 §1.1 の 8 |
| conformance 条件の要否 | 契約 `paging.ordering` が peer 間の一致を要求しないので足さない (Class B 据え置き) | 作業指示書 §1.1 の 9、§1.4 (a) |
| PostgreSQL 16.14 の jsonb 順序の実測 | 配列は要素数 → 要素ごと、オブジェクトはペア数 → 格納順 (キー長 → byte 順) のペアごとに key → value、入れ子の型順 Null < String < Number < Boolean < Array < Object、最上位の `[]` は scalar より小さい、数値は numeric | 作業指示書 §1.1 の 4、付録 A |
| 決定 D-1〜D-6 | 構造順序キー、文字列は codepoint 順のまま、テスト 3 種、docstring の訂正、変異、R-39 の (1c) は R-39 に残す | 作業指示書 §1.3 |
| 却下 (a)〜(d) | conformance 条件で固定、PostgreSQL 側を text 順に、型の禁止で回避、`sort_keys=True` のまま部分修正 | 作業指示書 §1.4 |
| コードレビュー F1〜F4 | F1〜F3 直した (F2・F3 は訂正註 1・2)、F4 観察 | 作業指示書 §4・§5、本書「裁定」節 |

## 3. 次の一手

R-38 閉止までの残り手順は作業指示書 §3 (main の取り込み → 完了ゲート → `RM` v1.125 の【追記】と R-112 の起票 → `tools/dev/finalize.py --tools-tests` で main へ merge)。版数ログから回転する行は v1.120。前々書 `HANDOVER_20260926_FABLE.md` の `docs/archive/docs/work-orders/` への回転は本変更セットで監督が行う (`OC` §1.16 の 78。最新 2 通は `HANDOVER_20260926_FABLE2.md` と本書)。

R-38 閉止後の残件 (前書 `HANDOVER_20260926_FABLE2.md` §3 と `docs/archive/docs/work-orders/HANDOVER_20260926_FABLE.md` §3 の両方から、生きているものを引き継ぐ):

- **CI の sqlite 版の実測**: push 再開後。pin テストは `MitateDB-api/tests/test_sqlite_version_floor.py` (>= 3.30)。
- **レビュー観察 2 件** (起票しない。`docs/archive/docs/work-orders/HANDOVER_20260925_FABLE2.md` の「裁定」節): cursor 付き要求 1 回ごとに catalog を 2 回余分に読む / `tools/contract_catalog.py --help` が書き込む。
- **push は停止中** (GitHub 課金上限)。再開後、main 先頭で CI を 1 回 (前書 §3)。
- **R-110 由来の観察 2 件** (起票しない。`docs/archive/docs/work-orders/HANDOVER_20260925_FABLE2.md` の「裁定」節): F9 = 欠陥が 2 つある要求で拒否コードの判定順が両 peer で違う / schema 操作 (`alter_field` / `create_index`) の未知 field / index の拒否コードが両 peer で不一致。
- **R-111 の観察 2 件** (起票しない。`docs/archive/docs/work-orders/HANDOVER_20260926_FABLE.md` の「裁定」節): r2db の制御 stack 作り直し、enable の path 文字列の複製。

台帳 `RM` §8 の未着手項目の着手順は依頼者裁定。

## 4. 依頼者判断待ち・未決

- **【追記 2026-09-26、merge 後】依頼者裁定 (逐語)「(i)で。2は後で。」** -- R-112 は (i) で着手 (台帳 v1.126)。下の (2) peer 間の JSON 値の順序差は保留。
- **R-112 文字列の照合順序** (作業指示書 §1.5 の U-1)。order_by の文字列の比較順序が 1 実装の backend 間で違う (r2db: PostgreSQL は DB 既定照合、in-memory は codepoint 順。MitateDB: PostgreSQL は DB 既定照合、SQLite は BINARY)。両論のまま:
  - (i) PostgreSQL 側を `COLLATE "C"` 相当にして in-memory / SQLite と揃える (jsonb の中の文字列は DB の照合を C にしないと揃わない = provisioning の変更、既存 client の見る順序が変わる)。
  - (ii) 現状維持し文書化する。
- **peer 間の JSON 値の順序** (作業指示書 §1.5 の U-2): r2db は jsonb 構造順、MitateDB は canonical text 順。契約が許容するので**観察** (起票しない)。契約で揃えるなら別途依頼者裁定。
- **R-38 の merge 前の報告**: 契約に触れないので Q-4 の形は不要。監督が完了ゲートの集計行と diff stat を添えて報告する。**本書起草時点では報告前。**

## 5. 本チャットで足した運用上の教訓

1. **PostgreSQL の実測は `select v::text as t ... order by v` のように出力列に別名を付ける。** 別名なしの `v::text` は出力列名が `v` になり `ORDER BY v` が text 順で走る (1 回目の計測がこれで狂った)。
2. **jsonb の順序は文書の型順だけでは足りない。** 最上位の空配列が scalar より小さい特例と、数値が JSON テキストの numeric として比べられること (2^53 超の float) は実測で初めて出た。基準は必ず実サーバの出力。
3. **「同型の値の順序」を pin するテストは入力を並べ替えて渡す。** 期待順のままだとキーが恒等でも緑。
4. **provenance の (2) 赤の分類は `old N, new M` の値で読む。** Known gap 3 は `old 0, new 1` にしか当たらない (レビュー F1)。
5. **並行チャットの性能計測 (排他 suite lock) の下では `--wait 300` でも REFUSED が出る。** 迂回せず待って再実行する (実装担当が 3 回経験)。加えて throwaway PostgreSQL の socket 消失 (`test_testpg_cluster.py` の基盤 flake) を 1 回観測、再実行で緑。

## 裁定

全件を載せる (`OC` §1.15 の 77)。出所は監督チャットの scratchpad の `rulings-r38.md` (監督、2026-09-26) の逐語である。表中の D-N / U-N / § 番号 / タスク / 付録 A は作業指示書のもの。

| 指摘 | 裁定 | 理由 |
|---|---|---|
| 探索担当 1 (sonnet): MitateDB は json 型を両 backend とも TEXT 列に canonical JSON で格納し素の列を ORDER BY、同種の食い違い無し | 採用 (監督が `postgres_types.py:24`・`request_binding.py:83-85`・`backend_sqlite.py:661-664`・`backend_postgres.py:1460-1463` を直読みで確認) | 着手条件の確認。R-38 は r2db のみ |
| 探索担当 1 観察: SQLite の BINARY 比較と PostgreSQL 列の照合 (既定 locale) の一致は保証されない | **起票** (U-1 の文字列照合の行に MitateDB 側も併記) | 利用者が気づく (大文字小文字・非 ASCII の順序が backend で違う)。r2db と同じ論点 |
| 探索担当 2 (sonnet): 契約 `paging.ordering` は実装間の一致を要求しない、conformance に array/object の order_by 無し、本番は常に PostgresCell | 採用 (監督が spec の文を直読みで確認) | 枠 §9 |
| 起草担当 疑義 1: 枠の `postgres_sql.py` の行番号ずれ | 直した (起草者が実測値で記載) | — |
| 起草担当 疑義 2: 未使用の `json` import を残すと `test_src_import_readers.py:799` が赤 | 採用 (タスク 4 の記述どおり。残せるのは使っている場合だけ) | 実測の事実 |
| 起草担当 疑義 3: 枠 (a) の C 番号の直書き (C-31 の次の番号) は check_doc_refs が赤にする | 直した (「次の C 番号」) | — |
| 起草担当 疑義 4: 最上位の JSON null は r2db に格納できない (SQL NULL に束縛)、`[""]` は文字列の制約 | 採用 (付録 A から除外) | `_bind_value` :125-134 |
| 起草担当 疑義 5: 枠に無い手順 3 つ (未変更コードで先に赤を確かめる、T1 の入力を並べ替える、T3 の page 数 > 1) | 採用 (残す) | いずれも非空振り要件 (`OC` §1.5 の 32) を強める |
| 起草担当 疑義 6: 新規ファイルにすると `-k` 行が対象を外す | 採用 + 監督裁定: T1 は新規ファイル `r2db-api/tests/test_inmemory_sort_jsonb_order.py`、T2/T3 は `test_postgres.py` の末尾に追記 | 下の観察 (行番号の引用ずれ) を増やさない |
| 起草担当 観察: `tools/tests/test_src_import_readers.py` の allow 表の理由文が `test_foundation.py` の古い行番号 (:2234 等、実物 :2252) を引く | **観察** (起票しない) | 2 問: (a) 検査器の穴ではない (理由文の位置参照は検査に使われない)、(b) 利用者は気づかず §0.1 も破らない。本件では T1 を別ファイルにして更にずらさない |
| 起草担当 観察: 作業指示書 38 KB (目安 5〜10 KB 超) | **観察** | 付録 A の値集合が大半。分割の実益なし |
| 実装担当 報告: provenance `--base` の (2) 赤を Known gap 3 に当てた | 直した (レビュー F1) | 分類の誤り。設計 §4.1 (2) D-2 の正当な赤として記録 |
| 実装担当 判断: `json` の import を消し `test_leaf_import_direction.py` の許容集合を `{"typing"}` に (F2 の対応で `{"decimal", "typing"}` に) | 採用 | D-1 の裁定の範囲 (未使用 import は `test_src_import_readers.py:799` が赤にする) |
| コードレビュー F1 (中): §5 完了条件 11 の provenance 赤の分類が誤り (`old 1, new 1` は既存 docstring の内容変更、Known gap 3 は `old 0, new 1`) | 直した | 登録・correction は不要 (受け皿なし、経緯語の削除なし)。R-110 訂正註 2 の読み替えに従う |
| コードレビュー F2 (低): 2^53 超の float と近い int の順序が backend 間で食い違う (最上位も基点から) | 直した (監督実測で PG 偽 / Python 真を確認 → 数値の枝を `Decimal(repr(float))` / `Decimal(int)` に。D-1 の訂正註) | PG が受け取る JSON テキストの数値そのものと比べれば一致する。格納の丸め (PG が読み戻す値が float と等しくない) は順序の話ではなく範囲外 |
| コードレビュー F3 (低): 完了条件 3 の「ペア数が先」「key → value」に変異が無い (RV1〜RV3 は赤で固定済み)、キー長の UTF-8 規則が未固定 (RV4 緑) | 直した (T1b に PG 実測の A-9 列 `{"a":1,"é":2} < {"a":2,"é":1} < {"ab":1,"é":2} < {"ab":2,"é":1}` と変異 M3c を追加、RV1〜RV4 を §5 に記録) | §2.13 の非 ASCII 禁止は「キーが各位置で等しく value で決まる比較」に限り緩めた (訂正註) |
| コードレビュー F4 (観察): T2/T3 の `==` は bool と数値を同一視 (`True == 1`) | **観察** (変更しない) | 最上位は `test_foundation.py:2271`、入れ子は A-2 の `[1.5]` が固定し、現時点で抜ける回帰は無い。利用者は気づかない |
| コードレビュー 権限: レビュー側の checker 再実行が拒否された | 採用 (再実行は実装担当が差し戻しの中で行う) | 役割の書き込み制約どおり |
