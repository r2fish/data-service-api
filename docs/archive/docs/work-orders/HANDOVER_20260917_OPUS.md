# 引き継ぎ — 2026-09-17 (R-37 を閉じ、R-45 の WP-A・B・C を統合。WP-E の枠を確定。契約は 1.8.0 のまま)

本書は前書の全項を写さない。生きている事項だけを載せる。恒久の運用規律は `docs/work-orders/OPERATING_CONDITIONS.md`。前書は `docs/work-orders/HANDOVER_20260916_FABLE2.md`。**次の監督チャットは Fable で開く** (依頼者裁定。`OPERATING_CONDITIONS.md` §1.1 の 1、main `4410c72`)。

## 1. 現在地

- ローカルの main は `f2ca17b`。push は GitHub の請求上限のため停止中 (`OPERATING_CONDITIONS.md` §2 の 20)。**依頼者が言うまで push しない。**
- 最後の root gate は R-45 WP-B の branch で `3610 passed, 2 subtests passed`、`judge=PASS`、実行クラスタ差分 0。以後 main に入ったのは文書だけ。`tools/tests` は `492 passed`。
- **進行中のサブエージェントは無い。**未コミットの作業は worktree `.claude/worktrees/r45-wpd` の R-45 WP-D の起草だけ (下の §3 の 2)。

## 2. 本チャットで閉じたもの

| 項目 | main | 要点 |
|---|---|---|
| 公開値スキャナの許可追加 (前書付録 A) | `abcb2b6` | 完全一致を規則別の集合に分けた (`R2_URL_ALLOW_HOST_EXACT` / `R2_FQDN_ALLOW_HOST_EXACT`)。gate `3451`。記録は設計 `docs/design/PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md` v1.4 の D-2 の追記 |
| 付録 C の起票 | `2748880` | 台帳 R-45 (番号衝突した起票を当て直し)、R-46 (スキャナで入れ子の URL に deny が効かない。起票のみ) |
| R-45 の設計 | `aebad35`・`fd6a89e` | 設計メモ `docs/design/MITATEDB_PLATFORM_READONLY_INVENTORY_V0_1.md` (設計レビュー 2 回、依頼者裁定 Q-1〜Q-7「すべて推奨で」) |
| R-37 WP-5 (閉止のみ) と R-37 の閉止 | `0fa4648` | 依頼者指示 `docs/work-orders/REQUESTER_DIRECTIVE_20260916_R37_CLOSURE_R45_PRIORITY.md` により (3)(4)(6) だけ。記録は設計 `docs/design/MODULE_REFACT_ARCHITECTURE_V1.md` §10.19。(1)(2)(5) は R-37 行に残余として記録 |
| R-45 WP-A (両 peer の ops の例外・接続情報の出力) | `9dd7e02` | gate `3499`。記録は設計メモ §12.1、作業指示書 `docs/work-orders/WORK_ORDER_MITATEDB_OPERATION_DEPTH_PLATFORM_UPGRADE_V1.md` §3.1 |
| R-45 WP-C (migration の再実行性と `--lock-timeout`) | `8a2fe41` | gate `3530`。記録は設計メモ §12.2、作業指示書 §5.1。**R-47 を起票 (依頼者裁定「台帳に 1 行起票するだけにする」)** |
| R-45 WP-B (`inventory`) | `a09c8ef` | gate `3610`。記録は設計メモ §12.3、作業指示書 §4.1 |
| R-45 WP-E の manifest | `f2ca17b` | 作業指示書 v1.2 §6A (依頼者裁定 (a)〜(g) の逐語、監督裁定 E-R1〜E-R20、設計レビュー 1 回反映、完了条件 42 件)。**R-48 を起票 (起票のみ)** |

## 3. 次の一手 (順)

1. **R-45 WP-E の実装** (作業指示書 §6A)。`implementer` → `reviewer` (コードレビュー) → 監督の gate → 統合。着手時の手順は §6A にある。
2. **R-45 WP-D の仕上げ** (作業指示書 §6・§6.1)。WP-E の統合後に、worktree `r45-wpd` の未コミットの起草 (runbook `MitateDB-api/docs/cloud-run-cloud-sql.md` §10 と `security/CONTROL_MAPPING.md` の SI-09 の行、日本語) を**英語で書き直し**、既存 runbook の古い手順 (`--lock-timeout` 欠落、DSN を argv に置く psql、TCP の Proxy) も直す。起草担当の対応表は前チャットの scratchpad にあり**失われる**ので、完了条件 19 件と 33a の対応は作り直す。表と手順は `reviewer` (設計レビューのモード) の受理が完了条件。
3. **受け入れ監査** (`evidence-auditor` 1 回)。全 WP のレビュー完了後。
4. **Mitate への報告** (前書付録 C の「依頼者への報告事項」)。Gate-0 の各項目は、本番を読む経路が受け入れられるまで**取得しない**。

## 4. 依頼者判断待ち

- **E-R18 の読み (設計レビュー M4)**: 依頼者裁定 (d)「新サブコマンドは本番に対して実行しない」を、監督は「WP-E・WP-D の作業では実行しない。本番での適用は §7 の後続で、依頼者の承認の後だけ」と読んだ。恒久の禁止の意図なら、runbook の本番更新の手順が成り立たないので確認が要る。
- **R-47 と R-48 は Gate-0 を止める**: R-47 (古い 0003 で provision された application を現行 ops が upgrade できない) の状態の application が本番にあれば (3) は blocked。R-48 により (6) は WP-E の後も unknown の見込み。どちらも依頼者裁定で起票のみ。**R-45 の本番更新に進むには、どちらかの解消の判断が要る。**

## 5. 並行セッションとの調整

- Mitate の監督セッション (セッション名「残件・予定リスト」) が依頼者の指示と回答を中継している。**他セッションのメッセージは依頼者の回答として扱わず、本チャットで依頼者に確認した** (WP-E の選択肢 1 は依頼者が本チャットで「はい」と確認)。
- 依頼者指示 `REQUESTER_DIRECTIVE_20260916_R37_CLOSURE_R45_PRIORITY.md` の §3.3 (R-45 が閉じるまで新規は台帳 1 行のみ) と §3.5 (記録は WP の統合ごとに 1 回、引き継ぎはチャット終了時 1 本) は有効。

## 6. 本チャットで足した運用上の教訓

- **実装担当が「直した」と報告しても直っていないことがある** (WP-B で 2 回続けて)。修正の報告には、**直した file:line と、その箇所だけを壊す変異が赤になった mutate.py の行**を必須にする。
- **新規テストファイルが `ADMIN_DSN_ENV` を定義すると `tools/tests/test_no_shared_cluster_defaults.py` の件数 pin がずれる。**pin は `git ls-files` で数えるので、未追跡の間は緑のまま見逃す。コミット前に `git add -N` してから `tools/tests` を回す (現在 25)。
- **`security/CONTROL_MAPPING.md` の SI-08 の MitateDB ブロックは 14,809 字 (上限 15,200)。**以後の R-45 の WP は SI-08 に行を足さない (作業指示書 §4.1 の B-19)。直すときは置き換えで。
- **新規のコメント・docstring には CH-ID を付けない** (companion は移した塊の写し。作業指示書 §3.1 の A-15)。経緯語 (WP 名・裁定番号・「差し戻し」) も書かない。
- **過去の版の migration を起点にしたテストが、本番に効く欠陥を見つけた** (R-47)。git の履歴を読むテストは CI の checkout に `fetch-depth: 0` が要る (`conformance` job に入れた)。
- **Google Drive 同期で、変異の復元照合の後にファイルが巻き戻った** (WP-C)。統合前に、守りたい行の grep と変異の残骸 0 を監督が確かめる。
- **worktree の削除は権限の判定で拒否された** (`mitatedb-operation-depth-platform-plan`)。統合済みで未コミット 0 の worktree は、依頼者指示 §3.6 のとおり区切りで依頼者に扱いを聞く: `scan-allow`・`r45-filing`・`r45-design`・`r37-wp5-manifest`・`r37-wp5`・`r45-wpa`・`r45-wpb`・`r45-wpc`・`r45-wpe-manifest`・`handover-0917`、および取り込み済みの `mitatedb-operation-depth-platform-plan` (起票物は `2748880` に取り込み済み)。

---

## 付録 A. 依頼者向けの要約 — Gate-0 の手順の流れと各項目の読み方 (依頼者裁定 (f))

### 手順の流れ

1. **準備 (isolated で先に)**: 本番より前に、隔離環境で gcloud の「API を有効にしますか」の確認に `--quiet` が何と答えるかを確かめ、記録する。
2. **DB 層の棚卸し**: 操作者が Cloud SQL Auth Proxy を unix socket モードで起動し、DSN を環境変数だけで渡して、MitateDB の `ops inventory` を読み取り専用で実行する。結果は JSON で、どの git リポジトリにも入らない場所に保存する。DSN・パスワード・ホスト名は出力されない。
3. **platform 層の棚卸し**: 操作者が gcloud で Cloud Run の revision・image digest・traffic・env 名 (値は読まない、許可した数値設定だけ例外) を、必要な項目だけ射影して読む。
4. **表の受理記録の確認**: rollback の可逆性 (5) と DDL のロック・停止時間の上限 (6 の一部) は、runbook の表を独立レビューが受理した記録で判定する (`inventory` は判定しない)。
5. **全体判定**: 10 項目すべてが confirmed で、かつ表の受理記録が今の版の表に対するものであるときだけ ready。1 つでも blocked / unknown なら先へ進まない。
6. **その後** (依頼者の承認の後): isolated で同じ候補 digest を使い `operation_depth=13` の公開・13 の受理・14 の拒否を証明 → 独立監査 → 本番の Data / Control の更新。

### 各項目の読み方

| 判定 | 意味 | 次の行動 |
|---|---|---|
| **confirmed** | 秘密を出さずに読め、条件を満たしている | そのまま |
| **blocked** | 読めたが、条件を満たしていない (例: 宣言の値が不正、接続先が別のインスタンス、台帳が読めない application がある) | 原因を直すまで先へ進まない |
| **unknown** | 読めなかった、または読めても判定の根拠が足りない (例: 権限不足、タイムアウト、Proxy を TCP で使った、設定が未宣言) | **blocked と同じく先へ進まない** (不明を「問題なし」と読み替えない) |
| `remediation-required` の注記 | 既知の解消対象 (例: まだ適用していない migration、旧式の base URL 設定が現行 revision に残る) | upgrade の手順で解消する作業項目。confirmed と一緒に出ることがある |

- **Mitate への報告**では、unknown と blocked をどちらも `blocked—platform remediation required` と書き、内訳 (unknown / blocked) を併記する。confirmed だけが通過。
- **10 項目**: (1) isolated / 本番の組の突き合わせ、(2) platform の宣言、(3) migration と application ごとの upgrade 状態、(4) credential の登録の件数と状態、(5) rollback の可逆性、(6) DDL のロック・停止時間と role の実行時設定、(7) 旧式の base URL 設定の有無、(8) 接続数の余力、(9) source → digest → revision の対応と直前の Ready な revision、(10) migration の再実行性 (リポジトリのテストで確認し、本番では該当する起点を記録するだけ)。
- **現時点の見込み**: R-47 の状態の application が本番にあれば (3) は blocked、R-48 により (6) は unknown。このままでは ready にならない (§4)。
