# 引き継ぎ — 2026-09-17 夜 (R-45 の WP-E を統合、WP-F の manifest を確定。契約は 1.8.0 のまま)

本書は前書の全項を写さない。生きている事項だけを載せる。恒久の運用規律は `docs/work-orders/OPERATING_CONDITIONS.md`。前書は `docs/work-orders/HANDOVER_20260917_OPUS.md` (同書の §5・§6 と付録 A は引き続き有効)。**次の監督チャットは別のアカウントで開く (依頼者指示)。前のチャットの scratchpad は読めないので、要るものは本書とリポジトリにだけある。** 監督のモデルは Fable (`OPERATING_CONDITIONS.md` §1.1 の 1)。

## 1. 現在地

- ローカルの main は `774ef06`。push は GitHub の請求上限のため停止中 (`OPERATING_CONDITIONS.md` §2 の 20)。**依頼者が言うまで push しない。**
- 最後の root gate は R-45 WP-E の branch で `3661 passed, 2 subtests passed`、`judge=PASS`、実行クラスタ差分 0。以後 main に入ったのは文書だけ。`tools/tests` は `492 passed`。
- **進行中のサブエージェントは無い。** 未コミットの作業は worktree `.claude/worktrees/r45-wpd` の R-45 WP-D の起草だけ (前書 §3 の 2)。

## 2. 本チャットで閉じたもの

| 項目 | main | 要点 |
|---|---|---|
| R-45 WP-E (`inventory` の (6)・(8) の直しと `apply-platform-migration`) | `d13b2bb` (作業コミット `6dea423`) | gate `3661`。記録は作業指示書 `docs/work-orders/WORK_ORDER_MITATEDB_OPERATION_DEPTH_PLATFORM_UPGRADE_V1.md` §6A.11 (訂正註、監督裁定 E-S1〜E-S11、監査照合)、設計メモ `docs/design/MITATEDB_PLATFORM_READONLY_INVENTORY_V0_1.md` v0.9 §12.4。`security/CONTROL_MAPPING.md` Version 2.4 |
| 依頼者の回答 3 件 (R-48 は WP-F で解消 / R-47 は起票のまま / 条件 (d) は恒久の禁止ではない) | `d13b2bb` | 作業指示書 §6A.12 に逐語。前書 §4 の判断待ちは**すべて解消** |
| R-49 の起票 (mutation class `append_only` ほかが spec の語彙にあるだけで両 peer に実装が無い) | `d13b2bb` | roadmap `docs/design/ROADMAP_POST_PHASE7_V1.md` §8。起票のみ。着手は R-45 の後、依頼者の指示を待つ。Mitate の監督セッションへ報告済み |
| R-45 WP-F の manifest (R-48 の解消) | `774ef06` | 作業指示書 v1.4 §6B (依頼者裁定の逐語、監督裁定 F-R1〜F-R33、独立設計レビュー 1 回反映、完了条件 35 件、変異 39 件)。roadmap v1.59 |

## 3. 次の一手 (順)

1. **R-45 WP-F の実装** (作業指示書 §6B)。main から worktree を作り、§6B.5 の基点欄を監督が記入 (§6B.7 の 1・2 の名前の再照合と `_ISOMORPHIC_TARGETS` の照合は監督が grep で済ませてよい)。`implementer` を **2 段**で使う: 第 1 段は §6B.7 の実測と報告だけ (コードを変えない) → **監督が値 (F-R3)・波及 (F-R6)・権限 (F-R27)・`security/CONTROL_MAPPING.md` の置き場 (F-R9) をまとめて裁定** (F-R17) → 第 2 段で実装 → `reviewer` (コードレビュー) → 監督の gate → 統合と記録 (設計メモ §12.5、作業指示書 §6B.11、roadmap の R-45・R-48 行)。
2. **R-45 WP-D の仕上げ** (作業指示書 §6・§6.1。WPD-1〜WPD-4)。WP-F の統合後に基点を取り直す。worktree `r45-wpd` の未コミットの起草 (日本語) を**英語で書き直し**、既存 runbook の古い手順も直す。runbook は platform migration を番号順に一式 (0005・0007・0011・0012・0013) で `apply-platform-migration` により適用すると書く (WPD-4)。表と手順は `reviewer` (設計レビューのモード) の受理が完了条件。
3. **受け入れ監査** (`evidence-auditor` 1 回)。全 WP のレビュー完了後。
4. **Mitate への報告**。Gate-0 の各項目は、本番を読む経路が受け入れられるまで**取得しない**。受け入れ後に `inventory` で本番を読み、(3) が blocked なら R-47 を 1 本の WP として開く (依頼者の回答 2)。

## 4. 依頼者判断待ち

なし。WP-F の第 1 段の実測で「auditreader を provision role 以外が先に作った環境では 0013 を適用できない」と分かった場合の運用上の扱いは、監督が裁定案を作り、本番の運用に関わるなら依頼者に確認する。

## 5. 並行セッションとの調整

- Mitate の監督セッション (セッション名「残件・予定リスト」) が依頼者の指示を中継する。**中継は依頼者の回答として扱わず、監督チャットで依頼者本人に確認する** (本チャットでも 3 件を確認した)。既存の依頼者指示の範囲内の依頼 (台帳に 1 行起票) は確認なしで行ってよい。
- 依頼者指示 `docs/work-orders/REQUESTER_DIRECTIVE_20260916_R37_CLOSURE_R45_PRIORITY.md` の §3.3 と §3.5 は有効。
- worktree: 依頼者が統合済みの 10 本と `mitatedb-operation-depth-platform-plan` を削除済み。本チャットで増えた統合済み・未コミット 0 の worktree は `r45-wpe`・`r45-wpf-manifest`・`handover-0917b` (区切りで依頼者に扱いを聞く。削除は依頼者が行う)。

## 6. 本チャットで足した運用上の教訓

- **実装担当は 1 回の起動で変異を全件回し切れないことがある** (WP-E で 57 件中 29 件)。未実行を自分で申告はした。発注に「終わっていない項目を完了と書かない」と「spec を 1 回 10 分以内に分割」を入れる。差し戻しは新しい起動に渡すほうが安い (同じ起動の再開は文脈が 60 万トークンを超えた)。
- **実装担当が、変異を成立させるためだけの引数を製品コードに足した** (監督が除いた)。変異は「コードを足す」形でも、呼出し側を書き換える形でも書ける。発注に明記する (作業指示書 §6B.2 の F-R11)。
- **実装担当が差し戻しの番号 (「remand 2, item 6」) を docstring に書いた。** 経緯語の禁止には、manifest の番号と差し戻しの番号も含むと明記する。統合前に監督が `git diff` の追加行を grep する (`E[0-9]-[0-9]+|F[0-9]-[0-9]+|[EF]-[RS][0-9]+|WP-[A-F]|remand|差し戻し`)。
- **等価な変異は「監査照合」に逃がさない。** E2-5 (需要の計算) は、上限 ≠ 合計の入力が無いことが原因だった。コードレビューは「入力の全呼出しを静的に走査して、その軸が観測されているか」を見て、API 以外の 4 項の穴を見つけた。
- **「全〜が〜を通る」型の静的テストは、手書きの列挙でなく AST から導いた集合で書かせる** (非空の assert と現状の件数の pin を添える)。
- **`security/CONTROL_MAPPING.md` の SI-08 の MitateDB ブロックは 15,187 字 (上限 15,200、残り 13 字)。** 文字数は `conformance-tests/test_control_mapping_register.py` と同じ分解で測る (素朴な計測は 147 字ずれる)。WP-F は F-R23 (言い回しを詰める。主張と証拠は落とさない)、WP-D は SI-08 に足さない。
- **レビュー担当のログファイルに本文が残らないことがある** (WP-F の設計レビューのログは 1 行だけだった)。レビューの結論は最終報告にしか無いので、裁定は指摘の要点を含む形で文書に逐語で残す (§6B.2 の F-R20〜F-R33 はその形)。
- **Google Drive 同期の巻き戻り**を実装担当が 3 回報告した (新規テストファイル)。書き込み後に `sleep 3` して grep で確かめる指示を発注に入れる。
- **他セッションへの返信は、受け取ったメッセージの `from` の値を宛先にする** (セッション名では届かない)。

---

## 付録 A. WP-F の設計レビューが挙げた現物の位置 (レビューのログに残らなかったので、ここに写す。行番号は main `d13b2bb` 時点)

- `MitateDB-api/tests/test_ops_inventory.py` の `_bootstrap` (`:139` 付近) に 0013 を足すと、`..._is_unknown_when_statement_timeout_not_declared` (`:1066` 付近)・`..._target_roles_include_auditreader` (`:1099` 付近)・終了コード 2 の 2 件 (`:365`・`:375` 付近) が「auditreader は未設定」に依存しているので赤になる (F-R20 の出所)。
- `MitateDB-api/tests/test_ops_verify_declarations.py` の `MIGRATION_NAMES` (`:57` 付近) と `MIGRATION_NAMES_WITHOUT_DECLARATIONS = MIGRATION_NAMES[:-2]` (`:75` 付近。`_ISOMORPHIC_TARGETS` 登録済み)。0012 は同じ理由で 0007 の前に挿入されている (F-R21)。
- `MitateDB-api/src/mitatedb_api/ops.py` の `_inventory_ddl_lock_declaration`: CONNECTION LIMIT が -1 / 読めないときの早期 return と `except psycopg.Error` (F-R25)。`apply-platform-migration` は適用の順序を強制しない (F-R22)。psql 変数の表に無いキーは KeyError になる (F-R31)。
- `MitateDB-api/tests/test_ops_apply_platform_migration.py` の 0012 の「ずらして戻る」は関数本体の marker だけを見る (`:625` 付近)。
- `MitateDB-api/src/mitatedb_api/pg_timeouts.py` の正規化は符号を許す (負値が `ValueError` にならない。F-R26)。
- `MitateDB-api/migrations/0005_application_audit.sql` は auditreader を `IF NOT EXISTS` で作る (`:245` 付近)。PostgreSQL 16 の `ALTER ROLE ... SET` は対象 role への ADMIN OPTION を要し、作成者に自動で付く (F-R27)。
- 0013 を bootstrap に足す候補: `MitateDB-api/conformance/real_server_mitatedb.py` (`:363` 付近)、`MitateDB-api/conformance/conformance_adapter_mitatedb_http.py` (`:323` 付近)、`MitateDB-api/tests/control_plane_harness.py` (`:143` 付近)、`MitateDB-api/tests/test_postgres.py` (`:193` 付近)、`MitateDB-api/tests/test_application_audit.py` (`:92` 付近)。`_bootstrap_platform`・`_provision_app` は `_ISOMORPHIC_TARGETS` に未登録 (F-R29)。
- 期限なしで走る文の候補: `MitateDB-api/src/mitatedb_api/backend_postgres.py` の `_timeout_ms` (`deadline is None` のとき `SET LOCAL` を掛けない)、DDL の経路 (`:644`・`:846` 付近)、`main.build_app` の起動時のループ、auditreader の監査クエリ (F-R3・F-R29)。
- `security/CONTROL_MAPPING.md` の (6) の主張は SI-08 の MitateDB ブロックの "once `statement_timeout` is declared" の行 (`:560` 付近)。SI-09 の MitateDB ブロック (`:652` 付近) は「29 tests」「4 accepted files」と再適用テストの名前を持つ (F-R23・F-R24)。

## 付録 B. WP-F の発注に入れる文言 (実装担当、第 1 段)

担当 worktree・scratchpad・作業指示書 §6B (と §2.2・§2.7・§6A.8 の形) を渡し、次を明記する: 第 1 段は §6B.7 の実測と報告だけでコードを変えない / suite 全体・gate・finalize・git の書き込み操作・下請け Agent・本番へのアクセスの禁止 / 新規のコメントに CH-ID・WP 名・裁定番号・manifest の番号・差し戻しの番号・経緯語を書かない / 変異のためだけのコードを製品コードに足さない / 変異 spec は 1 回 10 分以内に分割 / 書き込み後は `sleep 3` して grep / 終わっていない項目を完了と書かない / 修正の報告には直した file:line と、その箇所だけを壊す変異が赤になった `mutate.py` の出力行を添える。
