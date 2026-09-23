# 引き継ぎ — 2026-09-23 (R-95・R-87・R-90・R-91 を閉じ、R-78 の計測器を入れた。契約は 1.8.0 のまま)

本書は前書の全項を写さない。生きている事項だけを載せる。恒久の運用規律は `docs/work-orders/OPERATING_CONDITIONS.md`。前書は `docs/work-orders/HANDOVER_20260923_FABLE.md` で、**同書の §4・§5 と、そこが引く前々書までの §4・§5 は引き続き有効**である (本書の §4・§5 は追加だけを書く)。前のチャットの scratchpad は読めない。監督のモデルは Fable。push は GitHub の請求上限のため停止中 (`OPERATING_CONDITIONS.md` §2 の 20)。**依頼者が言うまで push しない。** origin/main は `8bf21a2` のまま。

## 1. 現在地

- ローカルの main は **`900b2e9`**。
- 最後の root gate は R-78 の木 (`--label r78`) で `3987 passed, 2 subtests passed`、`judge=PASS`、実行クラスタ差分 0。`tools/tests` は **601 本**。
- `security/CONTROL_MAPPING.md` は版 **2.25**、台帳 `docs/design/ROADMAP_POST_PHASE7_V1.md` は **v1.102** (R-78 の閉止で `v1.103`)。
- **進行中: 無し。** R-78 の WP-2 (K を振った sweep と `docs/design/PERF_CONCURRENCY_MEASUREMENT_V0_1.md` §2〜§4 の記入) は本チャットで監督が自ら行って閉じる — 結果は §2 の R-78 行に書き足す。
- 統合済みの worktree は全て fold 済み。残る `r45-wpd` は他チャットの dirty な残骸、`claude/*` は他チャットの session worktree。

## 2. 本チャットで閉じたもの

| 項目 | 要点 |
|---|---|
| R-95 (C) conformance の docstring の位置参照 | main `2f56763`。新規 `conformance-tests/test_conformance_docstring_position_refs.py` (node id 25) が docstring・コメント塊・行末コメントを単位に連結し、4 形の `file:line` を 2 経路で解決して行番号の範囲を検査する (許可表 0 行、床 files 49 / units 1452、現物依存の正の pin 1 件、D-9 の限界 5 点を docstring に開示)。訂正は 7 ファイル 30 件 (`structured.py:1583`→`:1821` ほか path・peer・引用内容の事実訂正を含む)。変異 29 件、設計レビュー 1・コードレビュー 1 (差し戻し 1)・受け入れ監査 1。ゲート `3899`。台帳 v1.98、**R-96 を起票** |
| R-87 (D) MitateDB の catalog 読みが宣言 `execution_ms` に従わない | main `43c408c`。`PostgresBackend.__init__` が `max_execution_ms` (既定 5000) を持ち、developer 接続の catalog 読み **8 本**すべてが取引の最初の実文の前で無条件に `SET LOCAL` する (role 水準の 5000ms に勝つことを構築値 200 / role 5000 の実測 `elapsed` 0.20s で固定)。新規 `MitateDB-api/tests/test_r87_catalog_read_execution_ms.py` (node id 11)、R-71 の実 QueryCanceled テストを新ファイルへ移動。`security/CONTROL_MAPPING.md` **版 2.23** (3 主張行を in place、2 主張行を追記)。往復は catalog 読み 1 本につき +2 文だが p50 の差は **±6% 以内** (往復数の増分は R-80 の対象)。変異 14 + 5 件、設計レビュー 1・コードレビュー 1 (差し戻し 1)・受け入れ監査 1 (差し戻し 2)。ゲート `3909`。台帳 v1.99 |
| R-90 (D) r2db に platform migration / deprovision のサブコマンドが無い | main `088be85`。`r2db-api` の `ops apply-platform-migration` (対象 `0008`/`0012`/`0013`/`0014`、`_PLATFORM_MIGRATION_SUPERSEDED_BY = {0008: (0012,)}`、psql 変数表は 0008 のみ、symlink を追って migrations dir 内であることを確かめる解決) と `ops deprovision` (slug 書式 → 必須 `--lock-timeout` → control DSN → `provisioned_at` 指紋の確認句 → `0004`、不一致は JSON denial exit 2 で書き込み 0)。新規 `r2db-api/tests/test_ops_apply_platform_migration.py` (43 テスト、AST 検査 2 本、drift-then-restore 4 本)。同型 pin **143 → 150**、runbook の手動 `psql -f` 7 箇所をサブコマンドに、`security/CONTROL_MAPPING.md` **版 2.24** (4 行を in place、SI-09 r2db に 6 本追記)。変異 21 + 12 + 3 件、設計レビュー 1・コードレビュー 2 巡・受け入れ監査 1。ゲート `3952`。台帳 v1.100、**R-97〜R-99 を起票** |
| R-91 (D) `max_connections` の余裕を誰も検査していない | main `da8d807`。**F-18** = 宣言された `process_ceilings` だけから配備全体の接続需要の**下界**を出し、`max_connections` から予約枠を引いた値と比べて足りなければ落とす (上界は報告のみ。**設計レビュー 1 が起草時の上界モデルを覆した**)。`ops verify-declarations` で **exit 17**、起動時は両 peer の composition root **4 箇所**。`{5,5}` → `{2,2}` で下界 720 → 288。同型 pin **150 → 156**、`security/CONTROL_MAPPING.md` **版 2.25** (主張 3 本を追記、2 行を in place)。変異 25 + 6 + 1 件、設計レビュー 1・コードレビュー 1 (差し戻し 1)・受け入れ監査 1 (差し戻し 2)。ゲート `3976`。台帳 v1.101、**R-100 を起票** |
| hotfix `ADMIN_DSN_ENV` の件数 pin | main `8195672`。`tools/tests/test_no_shared_cluster_defaults.py` の件数 pin 27 → 28。R-90 が新規テストファイルを足したのに pin を更新せず、root ゲートが `tools/tests` を含まないため見落とされた (§5 の (1)) |
| R-78 WP-1 (B) プールの取得待ちの計測器 | main `900b2e9`。両 peer に取得待ちの統計 (`acquire_count`・`wait_count`・`wait_total_ms`・`wait_max_ms`・`in_use_peak`・`size`、統計専用 lock)、MitateDB の data 面は `_CountingRLock` (再入を含む `lock_acquire_count`、素の `RLock` との残る 2 点の差を docstring に開示)。`tools/perf_baseline.py` が plug 単位・plug 累積の **`POOL` 行**を `PERF` 行の前に出し、r2db http plug に `DSA_PERF_POOL_SIZE` (既定 2 不変)。`tools/tests` 件数 pin 28 → 29、`_BACKEND_LAYER_ALLOWLIST` の行ずれを 40b で実測更新。変異 12 件、コードレビュー 1 (差し戻し 2)、受け入れ監査は Class B のため省略。性能の非退行は p50 差 -8.0%〜+7.3% (±10% 以内)。ゲート `3987`。**WP-2 (監督の sweep と設計メモ §2〜§4)**: `WP-2 (監督) 完了: sweep 12 run を `docs/design/PERF_CONCURRENCY_MEASUREMENT_V0_1.md` v0.2 §2 に逐語、§4 の判断 = プールは律速でない (寸法不変)、1 process 内の直列化が支配的 (R-101 起票)、MitateDB は cell の `RLock` が直列化点 (R-102 起票)。R-78 閉止 (v1.103)、同じ統合で閉じた` |

- 作業指示書: `docs/work-orders/WORK_ORDER_R95_CONFORMANCE_DOCSTRING_POSITION_REFS_V1.md` §6、`docs/work-orders/WORK_ORDER_R87_MITATEDB_CATALOG_READ_EXECUTION_MS_V1.md` §6、`docs/work-orders/WORK_ORDER_R90_R2DB_PLATFORM_MIGRATION_AND_DEPROVISION_OPS_V1.md` §8、`docs/work-orders/WORK_ORDER_R91_MAX_CONNECTIONS_HEADROOM_CHECK_V1.md` §7、`docs/work-orders/WORK_ORDER_R78_POOL_WAIT_MEASUREMENT_V1.md` §6。訂正註と監督裁定はすべて各 §x.1 に在る。
- `COLLECTION_FLOOR` (3326) は未更新 — 下限であり、更新はフェーズ完了時の監督の仕事。

## 3. 次の一手

1. **R-79** (prepared statement が効いているかの実測)。**着手前に、本チャットの探索ノート `$SP/explore-r78-r79.md` の事実 (現物の観測値) を台帳の R-79 行に書き足すこと** — 次のチャットからは scratchpad が読めない。
2. 続いて **R-80**、**R-81**、**R-82**、**R-85**、**R-86**。その後 **R-96**〜**R-100**。**R-83**・**R-84** は R-78〜R-82 の結果次第 (台帳の各行の保留条件を読む)。
3. fold は `tools/dev/fold.py --min-age-hours 0 --apply`。その前に他チャットの worktree を `git worktree lock` で保護する (前書 §3 の 3 と同じ)。

## 4. 依頼者判断待ち・未決 (前書 §4 に足すもの)

- **(r) 本チャットの Class D の決定 3 件の事後確認。** R-87 (catalog 読み 8 本の上限を構築時の `max_execution_ms` に + `CONTROL_MAPPING` 2.23)、R-90 (`CONTROL_MAPPING` 2.24 の訂正 4 行・追記 6 本と同型 pin +7)、R-91 (F-18 の追加 = `CONTROL_MAPPING` 2.25 の追記 3 本・訂正 2 行と同型 pin +6)。いずれも **2026-09-19 の委任**の下で監督が下した。
- **(s) R-52 (open) の形が変わった。** R-91 の F-18 により「並走する process の分を `process_ceilings` に宣言すれば下界の判定に反映される」形になったが、**宣言そのものは運用者の判断**であり、配備実態との一致を機械は見ない。

## 5. 本チャットで足した運用上の教訓 (前書 §5 に足すもの)

1. **root ゲートは `tools/tests` を含まない。** テストファイルを足す WP は、新規ファイルを `git add -N` してから `tools/tests` を回し、`finalize.py` に `--tools-tests` を付ける (R-90 の見落とし → hotfix `8195672`)。
2. **`security/` の主張が引く `file:line` は、統合直前に現物の def 行で確定文を更新する。** R-88 の検査には D-9 の限界 (範囲内の指し先違いは機械で捕まらない) があり、そこに甘えない (R-91)。
3. **版数行に裸の `:N` を書かない** — R-88 の位置参照検査が preamble の裸 `:N` を「path なし」として赤にする (R-91 の訂正註 3)。
4. **確定文の件数は peer ごとに数える** (R-91 の「all four composition roots」が両 peer 合算で誤り、`both` に訂正)。
5. **`security/` の WP の変異も必ず実行する** — R-87 では WP-2 の 5 件 (M14〜M18) が未実行のまま報告され、受け入れ監査が捕まえた。
6. **fixture に `0013` が無い木では role の `statement_timeout` は 0。** 「role 5000ms vs 構築値」を確かめるテストは、前提をテスト内で作って `finally` で復元する (R-87)。
7. **`public_value_scan` は `mutate.py` のログ dir 名 (道具名 + 日付 + 時刻をハイフンで繋いだ綴り) を R3 (project id) として拾う。** 追跡文書にはログの**時刻**だけを書き、dir 名をそのまま写さない (本書の初稿がこれで赤になった)。
8. **`tools/perf_baseline.py` は gate intent があると待たずに 75 で拒む。** sweep は完了ゲートの後に回す。
9. **Bash ツールは zsh。** `for spec in "1 10 100"; do set -- $spec` は分割されない — `read -r a b c <<< "$spec"` を使う。
10. **`CONTROL_MAPPING_HISTORY.md` の題には新版の版数を書く** (R-90 の実装が直前の 2.23 を書いていた)。
11. **追記する主張の断言ごとに証拠テスト名を付ける** (R-90 の WP-4 コードレビュー)。
12. **R-78 の計測で分かった前提**: 計測対象の r2db plug は `pool_size=2` で production と違う、rate window が 600/分なので K ≥ 8 では n を下げる必要がある、MitateDB のデータ面はプールではなく `RLock` の直列化である。これらは R-79〜R-82 の計測の前提になる。

- 監督チャットはモデル呼び出し 300 回を超えているので、**次は新しいチャットで本書から始める** (`OPERATING_CONDITIONS.md` §1.10 の 67)。
