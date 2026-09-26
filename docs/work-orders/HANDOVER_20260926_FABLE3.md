# 引き継ぎ — 2026-09-26 (R-38: r2db in-memory の ORDER BY と PostgreSQL jsonb 順序の一致。Class B、規模 M、1 WP。追記: R-112 (i) 文字列の照合順序の着手、Class D、規模 M、main 未 merge)

本書は前書の全項を写さない。生きている事項だけを載せる。恒久の運用規律は `docs/work-orders/OPERATING_CONDITIONS.md` (以下 `OC`)。前書は `HANDOVER_20260926_FABLE2.md` (R-41 チャット。同日の別チャット)。本書は `docs/work-orders/HANDOVER_20260926_FABLE3.md`。以下 `RM` = `docs/design/ROADMAP_POST_PHASE7_V1.md`、作業指示書 = `docs/work-orders/WORK_ORDER_R38_INMEMORY_JSONB_ORDER_V1.md`。本書で D-N / U-N / M-N / T-N / 完了条件 / 付録 A と書くときは作業指示書のものを指す (`OC` §1.8 の 59)。 ただし「追記 — R-112 (i) の着手」節と「裁定」節の R-112 の行では、作業指示書は `docs/work-orders/WORK_ORDER_R112_STRING_COLLATION_V1.md` を指す。

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

## 追記 — R-112 (i) の着手 (2026-09-26、同チャット)

本節と「裁定」節の R-112 の行では、作業指示書 = `docs/work-orders/WORK_ORDER_R112_STRING_COLLATION_V1.md` で、D-N / 完了条件 / 訂正註 / 付録 A / 変異名 (M1a 等) / P1・P2・T1〜T4・V1・V2 (test の略号) はその作業指示書のもの (`OC` §1.8 の 59)。「裁定」節の表の R-112 の行 (「探索担当 r2db (sonnet)」の行から末尾まで 17 行) の出所は、監督チャットの scratchpad の `rulings-r112.md` (監督、2026-09-26) の逐語である。scratchpad は次のチャットから読めないので、次のチャットが要る材料は本節に写した。

### 現在地

- 台帳 `RM` §8 の R-112 (文字列の照合順序) は、依頼者裁定 (i) (逐語「(i)で。2は後で。」、`RM` v1.126、main `0d7065c`) で着手した。worktree r38、branch r38、基点 main `0d7065c`。
- 済み: 枠 (監督。D-1〜D-7)、作業指示書 v1.0 + 訂正註 1〜3 (作業指示書 §4)、実装担当 (sonnet) の WP-1 完了報告。変更クラスは **Class D** に引き上げた (訂正註 1: 登録済み同型 helper 2 つ (`_VERIFY_DECLARATIONS_EXIT_CODES`・`_verify_declarations_checks`) の本体変更 + 新 helper の `_ISOMORPHIC_TARGETS` 登録)。**規模 M のまま、受け入れ監査を 1 回入れる**。
- **実装は worktree r38 の branch r38 に WIP commit として置く (main 未 merge。監督がチャット終了時に commit)。**
- 未実施: コードレビュー、受け入れ監査、完了ゲート、台帳 v1.127 の【追記】、merge。作業指示書 §5 (実施記録) の欄は空のまま (実装担当の集計行・変異表・provenance の分類は下の「閉じたもの」に写した)。
- 役割とモデル: explorer (sonnet ×2)、drafter (opus、transcript の `"model"` 欄は `claude-opus-5-5`)、implementer (sonnet)。commit・完了ゲート・merge は監督。
- 並行チャット R-101 (worktree r101) は継続中で、`tools/perf_baseline.py`・`docs/design/PERF_*` を触る (本件は触れない)。push は停止中。

### 閉じたもの

**実測** (監督、PostgreSQL 16.14。共有ローカル PostgreSQL に一時 DB を 2 つ作り、計測後に drop)。値集合は `_` `1` `a` `A` `ä` `aa` `b` `B` `z` `Z`。Python の codepoint 順 (= in-memory `_sort_key` / SQLite BINARY = UTF-8 byte 順) は `1 < A < B < Z < _ < a < aa < b < z < ä`。

| DB (`TEMPLATE template0 ENCODING 'UTF8'`) | datcollate / datctype | jsonb の文字列順 = text 列の順 | `upper('ä')` | `'Ä' ilike 'ä'` | `'ä' ~* 'Ä'` | `'straße' ~ '^\w+$'` |
|---|---|---|---|---|---|---|
| 既定 (現行) | en_US.UTF-8 / en_US.UTF-8 | `_ < 1 < a < A < ä < aa < b < B < z < Z` (codepoint 順と不一致) | `Ä` | true | true | true |
| `LC_COLLATE 'C' LC_CTYPE 'C'` | C / C | `1 < A < B < Z < _ < a < aa < b < z < ä` (codepoint 順と一致) | `ä` (折り返しなし) | false | false | false |
| `LC_COLLATE 'C' LC_CTYPE 'en_US.UTF-8'` | C / en_US.UTF-8 | `1 < A < B < Z < _ < a < aa < b < z < ä` (codepoint 順と一致) | `Ä` | true | true | true |

- jsonb には式レベルの COLLATE を付けられない: `ORDER BY jsonb COLLATE "C"` は `collations are not supported by type jsonb` で拒否 (監督実測)。r2db の untyped / object / array 列 (物理 jsonb) は DB 単位の `LC_COLLATE` が唯一の経路。既存 DB の照合は変えられない (再作成のみ)。
- 決定 D-1〜D-7 (作業指示書 §1.3)、却下 (a)〜(d) (同 §1.4)、訂正註 1〜3 (同 §4)。

**実装** (実装担当の報告。脚 A = r2db-api、脚 B = MitateDB-api。全変異 as expected、suite は基点 + 期待 node 数で failed 0)。

- 変更ファイル 16 件 (作業指示書を除く): 両 peer の `migrations/0003_provision_application.sql` (`CREATE DATABASE` + comment)、両 peer の `platform_declarations.py` (`_f19_message` / `check_application_collations`、`__all__`。本体は両 peer で byte-identical)、両 peer の `ops.py` (`_VERIFY_DECLARATIONS_EXIT_CODES["F-19"] = 18`、`_verify_declarations_checks` に F-19 の呼び出し)、`r2db-api/src/r2db_api/inmemory_sort.py` (`_sort_key` の docstring の照合の段落、D-5)、両 peer の `tests/test_postgres.py`・`tests/test_ops_verify_declarations.py`・`tests/test_audit_query.py`、`docs/ops/BACKUP_RESTORE_R2DB.md` (復元先の `CREATE DATABASE`、訂正註 2 (a))、`r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md`・`MitateDB-api/docs/cloud-run-cloud-sql.md` (F-19 の段落、訂正註 2 (a))。
- 新規 node: 脚 A 8 = `test_application_database_collation_is_c` (P1)、`test_application_database_collation_keeps_the_cluster_ctype` (P2)、`test_parity_string_collation_order_by_string_column` (T1)、`test_parity_string_collation_order_by_untyped_column` (T2)、`test_parity_string_collation_keyset_cursor_walk` (T3)、`test_parity_string_collation_where_gt_lt` (T4)、`test_verify_declarations_f19_fails_when_an_application_database_collation_is_not_c` (V1)、`test_verify_declarations_f19_passes_after_provisioning_with_0003` (V2)。脚 B 7 = 同名 (T2 なし)。V1 は D-4 の 2 通りのうち「`0003` を読み `LC_COLLATE 'C'` だけを除いた本文で provision する」方 (`_provision_app_for_verify_without_collation_c`)。
- 集計行 (実装担当、逐語。基点は供与値: `r2db-api/tests` `1478 passed`、`MitateDB-api/tests` `1480 passed, 2 subtests passed`、`tools/tests` `591 passed`。他の 4 コマンド (postgres の絞り込み 2 本と verify のファイル 2 本) は未変更ツリーで再実測していない = 裁定の逸脱 (e)):

```
r2db test_postgres.py -k "collation or parity_order": pt: 11 passed, 212 deselected in 2.92s
MitateDB test_postgres.py -k "collation or parity_order": pt: 5 passed, 93 deselected in 0.92s
r2db test_ops_verify_declarations.py: pt: 49 passed in 12.28s
MitateDB test_ops_verify_declarations.py: pt: 51 passed in 11.49s
r2db-api/tests: pt: 1486 passed in 112.14s
MitateDB-api/tests: pt: 1487 passed, 2 subtests passed in 246.62s
conformance -k "c30 or c28 or c06" -n 5 --dist loadgroup: pt: 202 passed in 40.44s
tools/tests: pt: 591 passed in 54.24s
r2db test_audit_query.py -k isomorphic: pt: 4 passed, 72 deselected in 1.71s
MitateDB test_audit_query.py -k isomorphic: pt: 4 passed, 59 deselected in 1.71s
```

- 変異 (実装担当、逐語。3 回に分けて実行、計 20/20 as expected):

```
M1a expect=red got=red OK | M1b red/red OK | M1c red/red OK | M1d red/red OK
M1e red/red OK | M1f red/red OK | M5a red/red OK | M5b red/red OK
M5c expect=green got=green OK | M3 red/red OK
mutate: 10 mutations, 10 as expected, restores verified 2/2 files (sha256 x2), grep counts unchanged
---
M2a red/red OK | M2b red/red OK | M2c red/red OK | M2d red/red OK | M2e red/red OK
M6a red/red OK | M6b red/red OK | M6c expect=green got=green OK | M4 red/red OK
mutate: 9 mutations, 9 as expected, restores verified 2/2 files (sha256 x2), grep counts unchanged
---
M7 expect=red got=red OK | mutate: 1 mutations, 1 as expected, restores verified 1/1 files (sha256 x2), grep counts unchanged
```

  完了条件との対応 (実装担当の報告): 1→M1a、3→M1b、4→M1c、5→M1d、6→M1e、8→M1f / M5b、2→M5a / M5c (緑の対照)、7→M3、9→M2a、11→M2b、12→M2c、13→M2d、15→M2e / M6b、10→M6a / M6c (緑の対照)、14→M4、16→M7 (+監査照合)、17〜21→監査照合のみ。
- provenance: `--register` は `comment provenance register OK: 92 files scanned, 433 CH-IDs`。`--base 0d7065c` の赤 5 本はすべて `docs/design/CODE_COMMENT_PROVENANCE_V1.md` §4.1 の分類で想定内 (登録済み block への赤は無し): r2db `platform_declarations.py`:1398・`ops.py`:1021、MitateDB `platform_declarations.py`:1373・`ops.py`:1289 → (1) 新規関数 / 新規呼び出し; r2db `inmemory_sort.py`:46 → (2) CH-ID なし docstring 段落の内容変更 (D-5、R-38 と同じ扱い)。
- `_ISOMORPHIC_TARGETS`: 両 peer 159 → 161 行 (`check_application_collations` / `_f19_message`)。件数 pin の test 名 `test_isomorphic_target_table_is_pinned_to_its_current_159_rows` → `..._161_rows` (関数名・自己参照行・重複 literal・`len()` の 4 箇所 × 2 peer)。
- D-7 の grep は README・deploy に限る読み方で 0 件 (`MitateDB-api/deploy/` は存在しない。訂正註 3 (2))。既存テストが F-19 で赤になった事例は無し。
- `inmemory_sort.py` の D-5 の docstring は `test_postgres.py` の `-k "collation or parity_order"` の「11 passed」を引く (既存の jsonb parity と新規の合算。訂正註 3 (3) でレビュー対象)。

### 次の一手

0. (監督、チャット終了時に追加) 作業指示書 §5 は空欄のまま。コードレビューの前に本節の実測を §5 に転記し、完了条件 16・18・19 の監査照合を実測して記す (作業指示書 §4 訂正註 4)。WIP commit は `738ca3a`。

順に行う。

1. 新しいチャットで worktree r38 を開き、`git log --oneline -3` と `git diff 0d7065c --stat` で WIP commit を確かめる。
2. コードレビュー (テンプレ 5、Class D、対象 = `git diff 0d7065c`)。特に訂正註 3 の (1) (未変更実装での赤を変異の実測で代替したこと)・(3) (docstring の「11 passed」)・(5) (`database_name` だけでの登録済み application の列挙)。
3. 差し戻し → 修正。
4. 完了ゲート `tools/dev/gate.py -C .claude/worktrees/r38 --label r112` (main が動いていれば先に取り込み、最終ツリーで回す)。
5. 受け入れ監査 (テンプレ 6、evidence-auditor、全 WP)。
6. 台帳 `RM` v1.127: R-112 行に下の閉止注の草案を【追記】し、placeholders を埋める。版数ログの v1.122 の行を `docs/archive/docs/design/ROADMAP_POST_PHASE7_V1__VERSION_LOG.md` へ回転する (`OC` §1.16 の 78)。`security/CONTROL_MAPPING.md` は触らない。本書に完了の追記をする。
7. `tools/dev/finalize.py --tools-tests` で commit と main への `--no-ff` merge (WIP commit と修正 commit の 2 commit を 1 merge)。

台帳 R-112 行の閉止注の草案 (監督、逐語。`<MEASURED>` / `<REVIEW>` / `<AUDIT>` / `<GATE>` は次のチャットが埋める):

```
**閉止 2026-09-26 (v1.127)**。依頼者裁定 (i) を作業指示書 `docs/work-orders/WORK_ORDER_R112_STRING_COLLATION_V1.md` WP-1 (Class D、規模 M。訂正註 1・2) で実施。**訂正**: 本行の「`migrations/0001` の `TEMPLATE template0 ENCODING 'UTF8'`」は application DB については `migrations/0003_provision_application.sql` の誤り (0001 は platform DB)。**直した**: 両 peer の `migrations/0003_provision_application.sql` の `CREATE DATABASE` に `LC_COLLATE 'C'` を足した (`LC_CTYPE` は書かず template0 = クラスタ既定の UTF-8 locale を引き継ぐ。実測: `LC_COLLATE 'C' LC_CTYPE 'en_US.UTF-8'` で jsonb の中の文字列も text 列も codepoint 順になり、`upper('ä') = 'Ä'` / `ILIKE` / `~*` / `\w` は保たれる。`LC_CTYPE 'C'` にすると非 ASCII の折り返しが壊れる。jsonb には式レベルの COLLATE を付けられないので DB 単位が r2db の唯一の経路。platform DB (0001) は変えない)。両 peer の `ops verify-declarations` に **F-19** (登録済み application の DB の `datcollate = 'C'`、`datctype <> 'C'`、PostgreSQL 15 以上では `datlocprovider = 'c'`、DB が無ければ FAIL。終了コード 18) を足し、helper `check_application_collations` と message helper を両 peer で同名・同本体にして `_ISOMORPHIC_TARGETS` に登録 (集合の増加 = Class D)。既存 DB の retrofit 経路は作らない (`LC_COLLATE` は変更不能。運用前なので再 provision)。`docs/ops/BACKUP_RESTORE_R2DB.md` の復元先の `CREATE DATABASE` を同じ形に、両 peer の runbook に F-19 の段落を足した。r2db `inmemory_sort.py` の docstring の「照合差は扱わない」を実測後に改めた。**実測**: <MEASURED>。コードレビュー (opus、Class D): <REVIEW>。受け入れ監査 (opus): <AUDIT>。完了ゲート (監督、solo、使い捨てクラスタ): <GATE>。`security/CONTROL_MAPPING.md` は 3.4 のまま (制御は変わらない。照合は順序の性質であって Security Invariant の制御ではない)。契約 1.11.0 のまま (`paging.ordering` は照合を実装依存とし、本件は実装内の選択)。「2」(peer 間の JSON 値の順序差) は依頼者裁定どおり保留。
```

### 依頼者判断待ち

- 「2」(peer 間の JSON 値の順序差。本書 §4 の「peer 間の JSON 値の順序」の行) は保留のまま。他に無し。

### 教訓

1. **`LC_COLLATE` と `LC_CTYPE` は別に決める。** ctype を `C` にすると非 ASCII の折り返し (`upper` / `ILIKE` / `~*` / `\w`) が壊れる (実測)。
2. **jsonb には式レベルの COLLATE が付かない。** jsonb の中の文字列の順序は DB 単位の照合が唯一の経路。
3. **実装担当が「テストを先に赤にする」順を守らなかったときは、同じ編集の変異が同じ node を赤にした実測で代替できるかを見てから差し戻しを決める** (訂正註 3)。

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
| 探索担当 r2db (sonnet): 両 migration の `CREATE DATABASE` に照合指定なし、SQL に COLLATE なし、index は素の btree、parity テストは照合差を検出しない | 採用 (監督が 0001:106 / 0003:102 を直読み) | 枠 §1〜2 |
| 探索担当 r2db 疑義: 「jsonb の中の文字列は COLLATE を付けられない」は未検証 | 採用 → 監督実測: `ORDER BY jsonb COLLATE "C"` は `collations are not supported by type jsonb` で拒否 | DB 単位の `LC_COLLATE` が r2db の唯一の経路 |
| 探索担当 r2db 観察: `postgres.py` module docstring の「許容差 2 件」に照合差が無い | **観察** (変更しない) | 本件で照合差は消えるので追記不要 |
| 探索担当 MitateDB (sonnet): TEXT 列のみ、パターン演算子なし、`create_index` なし、SQLite は BINARY; 列単位 COLLATE も可、0015 型の upgrade script も可 | 採用 (方法は r2db と同じ DB 単位に統一、retrofit は作らない = 却下案 (a)(d)) | peer 間で方法を割らない。`LC_COLLATE` は retrofit 不能 |
| 起草担当 疑義 1: 登録済み同型 helper 2 つの本体を変えるので Class C、新 helper を登録すると D | 裁定: **Class D** (新 helper を F-17 の前例どおり登録。訂正註 1) | 長期に正しい形 (両 peer の verify 検査を同型に保つ)。規模 M のまま、受け入れ監査を 1 回入れる |
| 起草担当 疑義 2: MitateDB の最後の検査は F-18 (F-17 ではない) → 両 peer とも F-19 | 採用 | 枠 §7 の実測誤り (監督) |
| 起草担当 疑義 3: `docs/ops/BACKUP_RESTORE_R2DB.md:28` の復元先 `CREATE DATABASE … OWNER` は F-19 で FAIL する; runbook の F-18 段落に F-19 が無い | 直す (訂正註 2 (a): 復元先に `TEMPLATE template0 ENCODING 'UTF8' LC_COLLATE 'C'`、両 runbook に F-19 段落) | 運用手順が検査と矛盾したまま残る |
| 起草担当 疑義 4: C / POSIX で initdb したクラスタでは `datctype = 'C'` で FAIL; ICU provider では `LC_COLLATE` が順序を決めない | 採用 (訂正註 2 (b): C ctype の FAIL は意図どおり (runbook に明記)、F-19 は PostgreSQL 15 以上で `datlocprovider = 'c'` も要求、`0003` に `LOCALE_PROVIDER` は書かない) | 折り返しが壊れた配備と ICU の DB を検出する。PostgreSQL の下限は上げない |
| 起草担当 疑義 5: verify テストは実 PG fixture、MitateDB に SQLite/PG parity の前例なし | 採用 (SQLite cell の作り方は `test_row_order_column.py:93`) | — |
| 起草担当 疑義 6: 枠に無い V2・M5b・M6b を足した; `database_name` が `pg_database` に無い場合が枠に無い | 採用 (V2 等は残す。訂正註 2 (c): 見つからない DB は FAIL) | 非空振り |
| 起草担当 疑義 7: 台帳 R-112 行が application DB の出所を `migrations/0001` と誤記 | 直す (閉止の【追記】で訂正。訂正註 2 (d)) | — |
| 起草担当 観察: check_doc_refs は追跡済みファイルしか走査しない (新規ファイルは手で確認) | **観察** (既知。`git add -N` 後に finalize が走査する) | — |
| 実装担当 逸脱 (a): テストより先に実装し、未変更実装での赤を確認していない | 採用しないが差し戻さない (訂正註 3 (1): M1/M2 系の変異が同じ node を赤にした実測で完了条件 1 を代替。次のチャットのレビューが独立に確かめる) | 同じ編集 (`LC_COLLATE 'C'` を外す) で同じ node が赤になる |
| 実装担当 判断 (b): `applications` の列名が peer で違うため `database_name` だけで問い合わせ両 peer byte-identical に | 採用 (訂正註 3 (5)。レビューで全件列挙を確認) | 同型性を保つ |
| 実装担当 訂正 (c): 0003 comment の `LC_CTYPE` の語を除去 | 採用 | 完了条件 18 |
| 実装担当 判断 (d): D-7 の grep は README / deploy に限る | 採用 (訂正註 3 (2)) | `docs/` の既存言及は写しではない |
| 実装担当 逸脱 (e): 絞り込み 4 コマンドの基点を未変更 tree で未実測 | 採用 (期待形と一致。監査照合の欄にその旨を書く) | (a) と同根 |
