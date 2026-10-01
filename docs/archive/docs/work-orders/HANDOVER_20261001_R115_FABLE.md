# 引き継ぎ書 — 2026-10-01 R-115 (worker の突然死による audit の欠落) 閉止

本書は R-115 の 2 つ目のチャットの記録である。規律の正本は `docs/work-orders/OPERATING_CONDITIONS.md`、R-115 の正本は設計 `docs/design/AUDIT_PROCESS_LOSS_V0_1.md` v0.5 と作業指示書 `docs/work-orders/WORK_ORDER_R115_AUDIT_PROCESS_LOSS_V1.md` (§10 の記録、§11 の訂正註 1〜15) である。前のチャットの記録: `docs/archive/docs/work-orders/HANDOVER_20260930_R115_FABLE.md`。

## 1. 現在地

- R-115 は閉止 (台帳 v1.143、`CM` 3.12、契約 1.13.0 `audit.process_loss_policy`、新条件 C-33)。main への merge は branch `r115-cont` を main `b346af2` に `--no-ff` で merge した候補 `r115-merge` を経て 1 回。完了ゲートは候補の上で PASS (作業指示書 §10.2)。
- 閉止の後に残るもの (製品の挙動と契約には掛からない): (1) MitateDB runbook `MitateDB-api/docs/cloud-run-cloud-sql.md` §10.6 / §10.7 / §10.10 の 7 / 7 / 11 版の依頼者による再受理 (§10.8 は not accepted、Gate-0 は未準備。独立レビュー済み、訂正註 14)。(2) 依頼者の一括確認 (§4)。
- 台帳の R-102・R-108 は着手条件「R-115 の merge」が満たされた。

## 2. 本チャットで閉じたもの

| 段 | commit | 内容 | レビュー |
|---|---|---|---|
| WP-4b レビュー | — | `9ae742d` の独立レビュー。指摘 8 件 (§6) | 済み。差し戻しは WP-5b に統合 |
| 性能 (WP-4b 時点) | — | head `9ae742d` vs main、閾値内 (§10.3) | — |
| WP-5a | `4584457` | r2db: migration 0016 (counter table + SECURITY DEFINER の加算関数)、coalescer 削除、`audit_query` の UNION の枝、F-21、r2db の 1.13.0 宣言 | 済み、指摘 10 件 (§6)、7 件を WP-5b で両 peer に適用 |
| WP-5b | `cca7286` | MitateDB: migration 0017、同上、FORBIDDEN の audit、MitateDB の 1.13.0 宣言、WP-4b の差し戻し、WP-5a の差し戻し R1〜R7、port v1.19 (`flush_audit_buffer` 削除) | 済み、指摘 6 件 (§6) |
| WP-5 後続 | `c196bd9` | S1〜S4 (F-21 が全権限を見る、owner の除外、接続 role の EXECUTE、説明文)、C-09 の頁たどり、backend の単発 insert / update の削除 | — |
| main 取り込み | `d0a8864` | main `b346af2` (R-46、R-102 設計、reader 役割) | 衝突なし |
| WP-6 | `0cb591a`・`38a197e` | `CM` 3.12、台帳 v1.143、設計文書への註 (R-113 設計 v0.7、フェーズ4 設計 v1.7、provenance v0.27、adapter 設計 v1.19)、両 peer の runbook (MitateDB §10 の新しい版)、runbook §10 の独立レビュー 7 件の反映 | runbook §10 は独立レビュー済み |
| 完了ゲート | 候補 `b799a5a` | `4854 passed`、PASS。`COLLECTION_FLOOR` 4697 → 4854 (`d419f23`) | 受け入れ監査 済み (§10.5) |
| 性能 (最終) | — | すべて閾値内 (§10.3)。in-process の MitateDB plug の sink に pool を足した (§10.4) | — |

## 3. 次の一手

1. 依頼者の一括確認 (§4) と runbook §10 の再受理。再受理されたら §10.8 を accepted に書き換え、`CM`:1294 付近と `RM` を追随させる (Class A / D、規模 S)。
2. R-102 (MitateDB の application 単位の直列化) と R-108 (参照クライアント) は着手可能。R-102 は本件で cell lock の内側に入った platform DB 往復 (§6 の観察) を解く設計でもある。

## 4. 依頼者判断待ち・未決

依頼者指示 2026-09-30「裁定は推奨で進めてください、最後に確認」の下で、監督の推奨で進めた裁定の一覧 (再審議ではなく確認):

1. SECURITY DEFINER 関数と counter table の owner は schema の owner role のまま (両 peer で provision role と同じ。訂正註 13 (1))。代替の専用 NOLOGIN owner role は採らなかった。
2. conformance の port `flush_audit_buffer` を削除 (port v1.19。訂正註 13 (3))。
3. F-21 に runtime role の直接権限の不在 (全権限)、auditreader の SELECT、接続 role の EXECUTE の検査を足した (訂正註 13 (2)、WP-5b レビュー S1〜S3)。
4. counter の主 key に窓の長さを入れた (訂正註 13 (2))。
5. `outcome_note` の 1 文目を「service が commit を見なかった (commit しなかった、または接続断で成否が不明)」に改めた (訂正註 11 (3))。
6. MitateDB の catalog は audit event を出さない非対称を本件の範囲外とした (訂正註 11 (2))。
7. runbook §10.10 の step 15 の語を実挙動に直した (訂正註 14。裁定 6 の「足すだけ」を超える。旧文と新文は `$SP/r115-wp6b-report.md` §7)。確認が得られなければ旧文に戻し 7c だけ残す。
8. MitateDB runbook §10.8 を 7 / 7 / 11 not accepted に書いた (runbook 自身の規則)。
9. in-process の MitateDB conformance plug の audit sink に pool を足した (作業指示書 §10.4)。

## 5. 運用上の教訓

- branch の途中の commit の `KNOWN_FINGERPRINTS` の行を最後に整理すると、branch の先頭では指紋の試験が赤になる。完了ゲートは main に branch を `--no-ff` で merge した候補の上で回す (first-parent の履歴に branch の commit が入らない)。
- 性能計測は他チャットの pytest と他プロジェクトの vitest で簡単に壊れる。load average を計測ごとに記録し、4 を超えた巡は捨てる。「静かになるまで待つ」script が有効。
- conformance の in-process plug の構成 (pool の有無) は composition root と揃える。揃っていないと plug の閾値検査が製品に無い費用を測る。
- `audit_query` を 1 頁だけ読む試験は、event が全部同期で残るようになると頁からあふれる (C-09)。
- 実装担当が同じ worktree で編集中にレビューを並行させるときは、レビュー担当に「commit の版を読む (`git show <sha>:<path>`)」と明記する。
- 台帳の版は他チャットと衝突する (v1.142 → v1.143)。CM の行参照は runbook の最終の行番号で最後に追随させる。
- `verify-declarations` は provision / control の DSN では F-13 で止まる。F-21 (と F-17) は writer role の DSN で読む。

## 6. 裁定

`OC` §1.15 の 77。起票 0 件。

| 指摘 | 裁定 | 理由 |
|---|---|---|
| レビュー WP-4b・F1 (MitateDB の catalog が event を出さない) | 観察 | 基点からの非対称、出さない event は失われない (訂正註 11 (2)) |
| レビュー WP-4b・F2 (接続断で error 行の有無が経路で逆) | 直した | WP-5b で全経路 error 行 + `outcome_note` |
| レビュー WP-4b・F3 (完了条件 40・46 の訂正註なし) | 直した | 訂正註 11 (1) |
| レビュー WP-4b・F4 (cell lock 内の platform DB 往復) | 観察 | K=4 keyed mutate +4.4% / +7.2%。R-102 が解く |
| レビュー WP-4b・F5・F6 (`audit_hook.py` docstring) | 直した | WP-5b |
| レビュー WP-4b・F7 (port docstring) | 直した | port ごと削除 |
| レビュー WP-4b・F8 (backend の単発 insert / update) | 直した | `c196bd9` で削除 |
| レビュー WP-5a・1 (関数の owner) | 観察 | 訂正註 13 (1)、依頼者確認 §4 の 1 |
| レビュー WP-5a・2・3・4・6・7・8・9 | 直した | WP-5b R1〜R7 (両 peer) |
| レビュー WP-5a・5 (未認証 flood の直列化) | 観察 | 実測 §10.3: 正規 tenant +7〜10%、429 / 503 は 0 |
| レビュー WP-5a・10 (memory の窓の表が刈り込まれない) | 観察 | in-process の plug の構成、製品の経路ではない |
| レビュー WP-5b・1・4・5 | 直した | `c196bd9` S1〜S4 |
| レビュー WP-5b・2 (port v1.19 の設計文書) | 直した | WP-6 |
| レビュー WP-5b・3 (cell lock 内の加算 2 箇所) | 観察 | F4 と同じ |
| レビュー WP-5b・6 (名前だけを見る試験 2 件) | 観察 | 性質は C-33 の変異が固定 |
| runbook §10 レビュー・1〜7 | 直した | `38a197e` (訂正註 14) |
| 監査・未充足 68・72・74 | 直した | 訂正註 15、本書 |
| 監査・証拠不足 31 件 | 観察 | 前チャットの変異の逐語 27 件は前の引き継ぎ書 §2・§6 の記録、性能 4 件は §10.3 |
| 監査・観察 1 (台帳の閉止が残件に触れない) | 直した | 記録ファイルに追記 |
| 監査・観察 2 (C-33 行の実測の出所) | 直した | 候補のゲートに書き直し |
| 監査・観察 3 (`tools/tests` 未実行) | 直した | 候補の上で 781 passed |
| 実装 WP-5a・§9 の 4 (起動時に runtime role の table 権限を見ない) | 直した | F-21 に足した |
| 実装 WP-5a・§9 の 10 (b) (`completeness_note` に窓の遅れが無い) | 観察 | `coalescing_window_ms` の宣言と summary の意味は変わらない |
| 実装 WP-5b・§0 の 2 (F-21 の role 同定を ACL で) | 観察 | S2・S3 で端を直した上で採用 |
| 起草 WP-6a・2 (provenance の註の節数) / WP-6b・1〜10 | 直した | WP-6 の後続 |

## 追記 — 2026-10-01 依頼者の確認と再受理

依頼者 (逐語): 「9件すべて確認、§10 も再受理します」。§4 の 9 件は確定、runbook §10.8 は 7 / 7 / 11 accepted (`CM` 3.13、変更セット `r115-accept`、規模 S、記録のみ)。§1 の「閉止の後に残るもの」は無くなった。step 15 の新文は確定 (旧文へ戻さない)。
