# 引き継ぎ — 2026-09-26 (R-101: 1 process 内の直列化の主体の切り分け。WP-1 実装中で中断、Class D、規模 M)

本書は前書の全項を写さない。生きている事項だけを載せる。恒久の運用規律は `docs/work-orders/OPERATING_CONDITIONS.md` (以下 `OC`)。前書は `HANDOVER_20260926_FABLE.md` (R-111)。以下 `RM` = `docs/design/ROADMAP_POST_PHASE7_V1.md`、作業指示書 = `docs/work-orders/WORK_ORDER_R101_SERIALIZATION_ATTRIBUTION_V1.md` (以下 `WO`)。

記録: `docs/archive/docs/work-orders/HANDOVER_20260925_FABLE2.md`

## 1. 現在地

- 本チャット (2026-09-26) は `RM` §8 の **R-101** に着手した。worktree `.claude/worktrees/r101`、branch `r101`、基点 local main `a1c1ee3`。**Class D** (依頼者裁定「D で進める」、`WO` §6.1 に逐語)、規模 M。契約 1.11.0 不変、`security/CONTROL_MAPPING.md` は参照追随のみで **3.4 → 3.5** (Control 主張の追加・変更なし)。
- 役割とモデル: explorer (sonnet)、drafter / reviewer (opus、transcript の `"model"` 欄は `claude-opus-5-5`)、implementer (sonnet、1 起動を 3 段で継続)。
- **WP-1 (計測器) は実装途中で中断した**: 第 1 段 (両 peer の src の計数) と第 2 段 (harness の CPU / DBTIME 行、adapter の thread limit と accessor、文書) は実装済み、差し戻し 1 (未実装の完了条件) は対応済み、**コードレビュー 1 (opus、10 件) の差し戻し 2 の対応は本書起草時点で進行中** (§3)。本書の commit 時点の状態は §3 の「commit 時点」に記す。
- **WP-1 の状態は branch `r101` に commit するが main へは merge しない** (完了ゲート未実施、レビュー再確認と受け入れ監査が未了)。
- 監督の枠 (v1.4)・裁定の逐語・レビュー報告・実装報告は本チャットの scratchpad (`r101-frame.md`、`rulings-r101.md`、`explore-r101.md`、`design-review-r101.md`、`code-review-wp1.md`、`r101-report-stage{1,2,2b,3}.md`、`r101-return-{1,2}.md`)。**新チャットの scratchpad からは見えない**ので、生きている内容は `WO` §1 (枠の逐語) と §6.1 (訂正註・裁定)、本書「裁定」節に写してある。
- push は停止中 (GitHub 課金上限)。ローカル commit のみ。
- 並行チャット: **R-38** (r2db in-memory ORDER BY) と **R-41** (C-06 phrase ベクトル + `COLLECTION_FLOOR` 4198 → 4203) が同日に別 worktree で開始 (依頼者承認)。触るファイルは R-101 と重ならない。台帳 / CM の版数行と引き継ぎ書名は merge 順で renumber する。

## 2. 本チャットで閉じたもの

| 件 | 結果 | 記録 |
|---|---|---|
| 現状確認と着手候補 | 印なし 6 件 (R-101 / R-41 / R-38 / R-33 / R-22 続き / R-42) を提示、依頼者が R-101 を選択、R-38 / R-41 を並行開始 | 本書 §1 |
| R-101 の枠 | 問題設定・守る条件 (a)〜(f)・D-1〜D-7・判定規則 J-1〜J-5・却下案・範囲 (`RM` §0.1.4 の 2 = K=32 の query p50 ≤ 8× K=1 が閉止形。本 WO は切り分けまで) | `WO` §1 (逐語) |
| 作業指示書 v1.0 | 完了条件 77、変異 64、WP-1 (実装担当) / WP-2 (監督) | `WO` |
| 設計レビュー 1 (opus) | 14 件 (高 2・中 6・低 6) 全件裁定・反映。主要: DBTIME を app + platform の 2 行に (F1)、判定規則の単位・雑音 ε・判定不能の帰結 (F2)、Class D (F7)、wrapper は `async def __call__` (F8) | 「裁定」節 |
| 依頼者裁定 | 「D で進める」(逐語) | `WO` §6.1 |
| WP-1 第 1 段 | 両 peer `psycopg_counting.py` (db_wall_ms / txn_count、`transaction()` override、probe は基底 commit)、r2db `_RolePool` の畳み込み、MitateDB credential store / audit sink の per-call 接続。`pt: 1488 passed` (r2db) / `pt: 1483 passed` (MitateDB)、変異 23/23 | `$SP/r101-report-stage1.md` (scratchpad)、`WO` §6.1 訂正註 1・裁定 1 |
| WP-1 第 2 段 + 差し戻し 1 | harness CPU / DBTIME 行、adapter の `DSA_PERF_THREAD_LIMIT` / wrapper / `perf_thread_limit()` / `platform_db_time_stats()`、`_ISOMORPHIC_TARGETS` +3 (pin 162)、README、設計メモの骨。`pt: 1498` / `1492` / `607` (tools/tests)、conformance `pt: 1253 passed in 570.84s` (監督)、変異 累計 63 | `WO` §6.1 訂正註 2〜4・裁定 2 |
| CM 参照追随 | 件数ピン改名で SI-08 Evidence が dangling → 監督が追随、3.5 | `WO` §6.1 訂正註 3 |

## 3. 次の一手 (新チャット)

**commit 時点**: (本書の末尾「追記 — commit 時点」に監督が記す)

1. **差し戻し 2 の残り** (`$SP/r101-return-2.md` の内容は本書「裁定」節のコードレビュー 1 の表と `WO` §6.1 裁定 3・4 に写した。指示本文はレビュー報告 §5 だったが scratchpad にしか無いので、新チャットでは `WO` §2.2 / §2.3 と本書の表から再構成する): F1 CPU 窓 (capture を除く)、F2 68/69 の limiter 実読み、F4 差分の固定 3 本 + r2db db_calls 変異、F5 README の回数、F6 wrapper の WeakSet、F7 `_RolePool.connection()` の畳み込み抜け・二重計上、F8 `transaction()` 往復自身の例外、F9 コメント 5 箇所、条件 23 の assert、条件 26 の AST pin を 3 箇所に。
2. **コードレビューの再確認** (opus、同じ観点。差し戻し 2 の全件が直っているか + 新規変異)。
3. **完了ゲート** (監督、root から `tools/dev/gate.py -C .claude/worktrees/r101 --label r101`。R-38 / R-41 の pytest と排他)。conformance は 1253 が基点 + 新規分。`COLLECTION_FLOOR` は R-41 側が上げる予定なので本変更セットでは据え置き (merge 時に照合)。
4. **受け入れ監査** (evidence-auditor、Class D。完了条件 77 件、変異 64 件 (+ レビュー追加分)、道具の出力)。
5. **WP-2** (監督): `WO` §3。非退行 (基点 `a1c1ee3` の道具と worktree の道具で K=1 / K=3)、sweep 10 run (limit {既定, 4, 1} × K {1, 4, 32} + 既定 × K=32 の 2 回目 = ε)、設計メモ `docs/design/PERF_SERIALIZATION_MEASUREMENT_V0_1.md` §2〜§4 (判定規則 J-1〜J-5 は §3.3 の逐語、計測後に動かさない)。他チャットの pytest と重ならない時間に。
6. 記録: `RM` v1.124 (R-101 行に【追記】、閉じない。R-84 行に J-1 の結果を追記)、`WO` §6.2、本書の更新、`finalize.py --tools-tests` で main へ merge (R-38 / R-41 の merge と版数 renumber)。
7. 是正 WP (`RM` §0.1.4 の 2 の形を満たす) は WP-2 §4 の判断の後、`WO` v1.1 で足す (依頼者確認)。

## 4. 依頼者判断待ち・未決

- 無し (Class D は裁定済み)。WP-2 §4 で「判定不能」の plug が出たときの追加計測の要否は依頼者確認。
- 是正の形 (§3 の 7) は WP-2 の後。

## 5. 本チャットで足した運用上の教訓

1. **件数ピンを改名する変更セットは同じセットで `security/CONTROL_MAPPING.md` の Evidence 参照を追随させる** (改名しないと `_ISOMORPHIC_TARGETS` の pin が赤、追随しないと register テストが赤)。
2. **判定規則は「単位・雑音・全不成立の帰結」を書かないと機械的に当てはまらない** (設計レビュー F2)。閾値は run 間の雑音を同条件の 2 run で測ってから決める。
3. **計測器の対象範囲は最初に経路の実測から決める**: app DB だけを見る DBTIME は platform 側 (r2db 8 tx/要求、MitateDB 4 tx + session 2 本) を落としていた (設計レビュー F1)。
4. **「時間予算内で未実装」は完了条件を落とす理由にならない** (差し戻し 1)。実装担当には差し戻しファイルで返す。
5. **同一起動の implementer を 3 段で継続すると context が 90 万 token 近くまで育つ**。次回は段ごとに別起動にして報告ファイルで引き継ぐ方が安い。
6. **CPU 窓の定義は「measured group の中だけ」を実装で保証しないと、要求の組み立て (capture) が混ざる** (コードレビュー F1)。

## 裁定

全件を載せる (`OC` §1.15 の 77)。

| 指摘 | 裁定 | 理由 |
|---|---|---|
| 起草 疑義 1: r2db は `with conn.transaction()` で BEGIN/COMMIT を送り commit() override を通らない | 直した (`transaction()` を公開 API で override、鍵は db_wall_ms / txn_count の 2 つ) | J-3 の分子 |
| 起草 疑義 2: probe 自身の commit が窓に入る | 直した (基底の commit を直接呼ぶ) | 計測器自身の往復 |
| 起草 疑義 3: `--roundtrip` の pin と POOL lock= の acquire | 直した (2 pin を実測値に、事実を README に) | — |
| 起草 疑義 4: 21b の訂正註の置き場 | 起草どおり (`WO` §6.1) | — |
| 起草 疑義 5: `RM` §0.1.4 の 2 と枠の範囲 | 採用 (本 WO は切り分けまで。閉止は 8 倍以内の形) | 依頼者裁定を再審議しない |
| 起草 疑義 6: run_in_threadpool の箇所数 | 直した (11) | — |
| 起草 疑義 7: DBTIME の位置と conns= | 決めた (CPU → POOL → DBTIME → PREPARED → ROUNDTRIP、conns= は POST の label 数) | — |
| 起草 改版 疑義 1〜4 (D-1/D-2 の並び、WP 分割の文、POST probe の時点、probe 失敗時の rollback) | 直した ×3、観察 ×1 (probe 失敗時の rollback は README に 1 行) | — |
| 設計レビュー F1 (高): DBTIME が app DB だけ | 直した (scope=app / platform の 2 行、per-call 接続の畳み込み) | 主体判定が偏る |
| 設計レビュー F2 (高): J 規則が機械的に当てはまらない | 直した (D-5 全面改訂) | 計測後に動かせない |
| 設計レビュー F3 (中): 構成上の事実から決まる規則 | 直した | — |
| 設計レビュー F4 (中): ±10% が雑音より細かい | 直した (ε の 2 run、δ = max(10%, 2ε)) | — |
| 設計レビュー F5 (中): thread limit の実値が出力に無い | 直した (CPU 行 thread_limit= 列) | — |
| 設計レビュー F6 (中): transaction() の 3 性質に変異 1 つ | 直した (3 行 3 変異 + 追加変異) | 1 項目 1 変異 |
| 設計レビュー F7 (中): OC 38 の照合 | 直した (3 helper を登録、Class D、依頼者裁定) | 適用除外を作らない |
| 設計レビュー F8 (中): MitateDB-socket で asgi2 判定 | 直した (`async def __call__`、asgi3 の pin) | — |
| 設計レビュー F9〜F14 (低): txns の単位、PRE の枝、J-4 の名付け、loop ごと 1 回、gone=、§0/§5 の記述 | 直した ×6 | — |
| 起草 改版 (v1.3) 疑義 1〜5: platform 行の畳み込み、MitateDB の pool 無し、統計 lock、accessor の登録、Class B の残り | 直した ×4、`platform_db_time_stats()` は登録しない (R-78 `pool_stats()` の裁定と同じ) | — |
| 実装 第 1 段 疑義 1: 条件 20 の txn_count ≥ 1 | 直した (`WO` 訂正註 1: 0 のまま) | 守る条件 (b) |
| 実装 第 1 段 疑義 2: 来歴検査 §4.1 (2) 11 行 | 受理 (`WO` 裁定 1。R-67 の前例。レビューで 11 箇所確認済み) | 仕様どおりの赤 |
| 実装 第 2 段 疑義 0: conformance 1 件赤 (CM の旧テスト名) | 直した (監督、CM 3.5、`WO` 訂正註 3) | — |
| 実装 第 2 段 疑義 1・2・4: 未実装の完了条件、db_calls 常時 0 | 直した (差し戻し 1) | 時間予算は理由にならない |
| 実装 第 2 段 疑義 3: test_src_import_readers の 1 行 | 受理 (`WO` 訂正註 2) | 機械的帰結 |
| コードレビュー 1 F1 (高): CPU 窓に capture | 直す (差し戻し 2、進行中) | J-2 の分子 |
| コードレビュー 1 F2 (中): 68/69 が identity だけ | 直す (差し戻し 2) | 代理指標の禁止 |
| コードレビュー 1 F3 (中): 条件 26 の AST pin | 受理 (`WO` 裁定 3、3 箇所に拡張) | 並行喪失の試験は不安定 |
| コードレビュー 1 F4〜F9: 差分の未固定、README、WeakSet、`_RolePool` の畳み込み、transaction 往復の例外、コメント 5 箇所 | 直す (差し戻し 2) | — |
| コードレビュー 1 F10 (低): 記録の不一致 | 直した (`WO` 訂正註 4、裁定 1 の 11 行) + 条件 23 の assert は差し戻し 2 | — |

## 追記 — commit 時点 (2026-09-26、監督)

- 依頼者の指示で、implementer の差し戻し 2 の対応が終わる前にチャットを閉じた。**commit した木は差し戻し 2 の途中の状態で、どの項目 (F1〜F9、条件 23、条件 26) まで反映されたかは未確認、テストの緑も未確認** (最後に確認できた集計行は差し戻し 1 の後: `pt: 1498 passed` (r2db) / `pt: 1492 passed, 2 subtests passed` (MitateDB) / `pt: 607 passed` (tools/tests) / conformance `pt: 1253 passed in 570.84s`)。
- **新チャットの最初の手**: (1) `tools/dev/pt.py --wait 1800 -C .claude/worktrees/r101 -- tools/tests -q`、`-- r2db-api/tests -q`、`-- MitateDB-api/tests -q` を各 1 回回して木の状態を確定する (赤なら差し戻し 2 の途中の編集が原因。`git diff` で該当箇所を見て仕上げるか戻す)。(2) `git diff` を差し戻し 2 の項目 (本書「裁定」節のコードレビュー 1 の表) と突き合わせ、未反映の項目を新しい implementer (別起動、`WO` §2 と本書の表を渡す) に発注する。(3) 以降は §3 の 2〜7。
- 変異の JSON (`r101-mutations-*.json`) と実装報告は旧チャットの scratchpad にしか無い。新チャットでは §2.3 の表から変異を作り直す (実装担当が自作分を持つ)。
