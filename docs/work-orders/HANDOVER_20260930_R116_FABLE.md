# 引き継ぎ — 2026-09-30 (R-116 Gate-0 の起動時の検査 F-16 / F-18 の検算を道具 `ops startup-checks` に移す。Class D、規模 M、契約 1.12.0 不変)

本書は前書の全項を写さない。前書は `docs/work-orders/HANDOVER_20260930_R114_FABLE.md`。恒久の運用規律は `docs/work-orders/OPERATING_CONDITIONS.md` (以下 `OC`)。`RM` = `docs/design/ROADMAP_POST_PHASE7_V1.md`、設計 = `docs/design/MITATEDB_STARTUP_CHECK_TOOL_V0_1.md` (v0.3)、`WO` = `docs/work-orders/WORK_ORDER_R116_STARTUP_CHECK_TOOL_V1.md` (v1.1)、`CR` = `MitateDB-api/docs/cloud-run-cloud-sql.md`、`CM` = `security/CONTROL_MAPPING.md`。全裁定の正本は `WO` §6.1・§7.1〜§7.8 と設計 §12.4。

## 1. 現在地

- 依頼者裁定 (逐語。設計 §0 から複製):
  - 2026-09-29「本番の値は分からないので、確かめる手順の形で進めてください」
  - 2026-09-30「推奨の (1) と (3) の組み合わせで進めてください」
  - 2026-09-30「1は含めない、2はDで進めてください」
- worktree は branch `r116` のもの (名は公開値スキャンの R3 に当たるので書かない)、基点 local main `ab20f4e` (契約 1.12.0)。本チャットは再開 (2026-09-30)。変更セットは `tools/dev/finalize.py` で commit し local main へ `--no-ff` merge した (STOP 1 回: `tools/tests` の `ADMIN_DSN_ENV` の件数 pin 32 → 33、`WO` §7.9。SHA は `git log`)。
- 設計 v0.2 → v0.3、`WO` v1.0 → v1.1。WP-1・WP-2・§10.10 版 10 の受理レビュー・WP-3 まで済んだ。
- WP-1: 道具 `MitateDB-api/src/mitatedb_api/startup_checks.py`、`MitateDB-api/src/mitatedb_api/ops.py` の配線、`MitateDB-api/tests/test_ops_startup_checks.py` (76 id)、`tools/tests` の pin 4 file。最新の集計は `pt: 216 passed` (`TINV` を含む)、`pt: 12 passed` (`tools/tests` 4 file)、`mutate: 48 mutations, 48 as expected`。
- WP-2: `CR` §10.10 版 9 → 10、§10.4.3・§10.4.4 step 7・§6.5 の追随。`### 10.6`〜`### 10.9` 直前は byte 不変 (sha256 `b44422ec…`、`WO` §7.7)。
- §10.10 版 10 の独立の受理レビュー: **受理** (必須 0 件。`WO` §6.1)。
- WP-3 (監督): `CM` 3.8 → 3.9、行参照の追随 `ops.py` 93 件 + `CR` 15 件。既存コメントの書き換えは `docs/code-history/MitateDB-api/ops.md` の CH-0545。
- 完了ゲート 1 回目 (受理レビューの任意を直す前): `gate: 4687 passed, 2 subtests passed in 411.36s (0:06:51)`、`judge=PASS`、pg diff 0 (label `r116`)。
- 完了ゲート 2 回目: `gate: 2 failed, 4685 passed, 2 subtests passed in 410.49s (0:06:50)`、`judge=FAIL` — 赤は `CM` 3.9 の版の行と主張 2 行 (`WO` §6.2)。直して登録簿の検査 `pt: 58 passed`。
- 完了ゲート 3 回目 (最終形): `gate: 4687 passed, 2 subtests passed in 400.48s (0:06:40)`、`judge=PASS`、pg diff 0 (label r116-3、2026-09-30 13:39)
- 受け入れ監査: 充足 (42〜46・46b・58 は記録を足して充足、43 は push 再開後)。観察 4 件は直した (§6)。
- 台帳 R-116 は v1.136 で閉止 (§8.2 の索引と記録ファイル、版数ログの回転)。本番には何も適用していない。push は停止中 (`OC` §2 の 20)。

## 2. 本チャットで閉じたもの

| 件 | 結果 | 記録 |
|---|---|---|
| 設計の再確認レビュー (v0.2) | 12 件を裁定し v0.3 に織り込んだ | 設計 §12.4 |
| WP-1 (道具とテスト) | コードレビュー 1 (6 件) と再確認 (1 件)、全件直した | `WO` §7.3・§7.4 |
| WP-2 (runbook) | コードレビュー 1 (6 件) と再確認 (観察 2 件)、全件直した | `WO` §7.5〜§7.7 |
| §10.10 版 10 の受理 | 受理。任意 9 件と道具側 1 件を直した | `WO` §6.1・§7.8 |
| WP-3 (記録) | `CM` 3.9、CH-0545 | `WO` §5 |

R-116 そのものは未閉止 (§3)。

## 3. 次の一手

1. 完了ゲート 2 回目の集計行を確かめる。
2. 受け入れ監査のパケットを 1 件ずつ裁定する (`OC` §1.15 の 77)。本書 §6 の監査の行を埋める。
3. 台帳 v1.136: R-116 を閉止し、行を記録ファイルの末尾へ逐語で移して §8.2 に索引行を残す。版数ログを回転する (`OC` §1.16 の 78・79)。`tools/dev/ledger.py --check`。
4. 本書の placeholder を埋める。
5. 同じ変更セットで `docs/work-orders/HANDOVER_20260930_FABLE.md` を `docs/archive/docs/work-orders/` へ `git mv` する (最新 2 通 = 本書と `HANDOVER_20260930_R114_FABLE.md`。`OC` §1.16 の 78)。
6. `tools/dev/finalize.py --tools-tests` (identity は r2fish noreply。`git add -A` を使わない。push は停止中)。
7. 依頼者に §4 の (i) / (ii) を挙げる。
8. #43 (CI 3.12 の leg) は push 再開後に main の run で照合する (設計 §12.3 の 3)。

## 4. 依頼者判断待ち・未決

- runbook §10.8 の表の §10.10 の行 (「Current version 9 / not accepted」) は byte 不変の範囲として変えていない — (i) 受理の記録は作業指示書 §6.1 に置く (本作業はこれ) / (ii) その 1 行だけ変える (§10.6・§10.7 の受理を無効にしない、と依頼者が裁定する)。設計 §11。

## 5. 本チャットで足した運用上の教訓

- (i) 回数に数えない再確認レビュー (1 起動) が、v0.2 の新しい穴を 12 件見つけた。設計を書き直した後の再確認は省かない。
- (ii) 新しい src module を足すと `tools/tests` の pin 4 file (`sql_statement_safety`・`leaf_import_direction`・`src_import_readers`・`src_import_cycles`) が、`ADMIN_DSN_ENV` を定義する新しいテスト file は `test_no_shared_cluster_defaults` の件数 pin が赤になる。作業指示書の触ってよいパスに最初から入れ、`CM` を触るなら登録簿の検査 (`test_control_mapping_register.py`) をゲートの前に単独で回す。
- (iii) 変異が別の検査で「たまたま赤」になるとき (M33 の rule 語、M26 の文字列定数) は、試験が assert する性質を rule 語まで下ろして註記する。
- (iv) 既存コメントを書き換えると provenance の (2) が出る。旧塊を CH-ID で登録し correction を書く形 (CH-0545) で、同じ変更セットに収める。
- (v) runbook のコマンドを書く前に合成 cluster で実行する規律によって、出力 key の順 (sort_keys) と `declaration.current` の実物 (全 row を読むと必ず失敗する) が早く見つかった。
- (vi) `CM` の行参照の追随は difflib の等価区間で写像し、写像先の行の本文が一致することを機械で確かめる (scratchpad の小 script。93 + 15 件)。

## 6. 裁定

今回の起票は 0 件、既知の穴の新規登録も 0 件。受理レビューの必須は 0 件。

| 指摘 | 裁定 | 理由 |
|---|---|---|
| 設計の再確認レビュー 1: G3 の行の世代が式の同一性で固定されない | 直した | 式が変われば G4 を足す。#46a、設計 D-4 |
| 同 2: 新 module で赤になる `tools/tests` の固定が WP-1 のパスに無い | 直した | #46b、設計 §8 |
| 同 3: G0 が関数名の参照 0 だけで決まり、改名・文字列参照で偽の G0 | 直した | 文字列定数の検査と表を先に引く順。#46c |
| 同 4: #1〜#5 の比べ方が未定 | 直した | 試験が p を独立に計算して `current_judgment` で比べる。#46d |
| 同 5: §6 の例と文の食い違い、`reason`・`coverage` の語彙が無い | 直した | 閉じた語彙を D-8 に置いた |
| 同 6: §12.3 の 1・2 が本文に無い | 直した | 設計 D-4・§10 (9) |
| 同 7: WP-3 に `CM` の主張と版の行の完了条件が無い | 直した | 61a |
| 同 8: `_inventory_role_classes` の所在と import の向き | 直した | 設計 D-1・D-6 |
| 同 9: #16〜#19 の fixture の現在値が無い | 直した | 設計 §9 |
| 同 10: 入力の型の拒否、#28 の合成 repo、読み手の取り出し方 | 直した | 設計 D-5・§5・§9 #28 |
| 同 11: §3.2 の「src の変更は無い」が基点で偽 | 直した | 設計 §0・§2・§3.2 |
| 同 12 (不確実): step 7 の後の再実行で controlplane が窓のせいで `blocked` のまま | 直した | (甲) を採り、step 7 以降は step 6 の出力を指して再実行しない (D-7・D-9、`CR` step 7・11・13・Rollback)。(乙) は却下 (0012 / 0014 は自身の適用を記録しない) |
| WP-1 レビュー 1: G1 / G2 の application role の床が試験で固定されていない | 直した | 試験を足し、変異 M6b を足した |
| 同 2: M33・M34 の赤が rule 語の assert による | 直した | M33 は註記、M34 は入力の順を替えた |
| 同 3: docstring 2 箇所が実物と合わない | 直した | 実物に合わせた |
| 同 4: `main()` の既存コメントが偽になった | 直した | 最小の語を足し、CH-0545 に登録した |
| 同 5: Control の revision 0 件で `coverage["control"]` が `listed` | 直した | `control-revisions-missing` で拒否 (#42) |
| 同 6 (不確実): partial clone の lazy fetch | 直した | `GIT_NO_LAZY_FETCH=1`、変異 M46e |
| WP-1 再確認 1: `WO` §7.4 の rule 語が実物と違う | 直した | 訂正註で `empty-revisions` と読み替えた |
| WP-2 レビュー 1: §6.5 が step 6 の手計算を指す | 直した | 範囲を広げて道具の判定を指す形にした |
| 同 2: 2 段の rollout の入口が `reason` 付きの `blocked` を除かない | 直した | `reason` が `null` で F-16 に `blocked` が無いときに限った |
| 同 3: 終了コード 1 の stderr に usage error の例外が無い | 直した | 例外を書いた |
| 同 4: 「Report and stop」と step 6 の「直して再実行」が食い違う | 直した | 入力を訂正してもなお `confirmed` でないときに限った |
| 同 5: 出力 file 名が固定で上書きされる | 直した | run ごとの file 名にして合成 cluster で再実行した |
| 同 6 (不確実): step 13 の「step 6 に戻る」の範囲 | 直した | (乙) の 1 文を足した |
| WP-2 再確認 観察 A: 2 段の rollout の入口の条件が §6.5 で揃っていない | 直した | 監督が「where step 6 allows it」とした |
| 同 観察 B: step 13 の env-only revision が `rollback_target` も持ちうる | 直した | 監督が括弧書きを足した |
| 受理レビュー 必須 | 指摘なし | 必須 0 件で受理 |
| 同 任意 1: Control の env-only revision が入力から漏れうる | 直した | step 6 に 1 文を足した |
| 同 任意 2: 宣言 3 点と `known_gaps` の対応が実物と合わない | 直した | runbook の括弧と docstring の gap 9 を直した |
| 同 任意 3: 最初の実行が step 5 の後になっている | 直した | step 1 の前にも 1 回実行する |
| 同 任意 4: `audit_dsn_configured` の secret 参照の扱い | 直した | 名があれば `true` (厳しい側) |
| 同 任意 5: Dockerfile 検索の hit を step 6 でどう読むか | 直した | 2 つの名を設定する hit に限った |
| 同 任意 6: Rollback の kind が step 10 の後に合わない | 直した | `env_only_revision` を括弧に足した |
| 同 任意 7: 2 段の rollout の入口が `unknown` を除かない | 直した | 「and every other judgment is `confirmed`」を足した |
| 同 任意 8: 「nothing is fetched」が git 2.44 以上を前提にしている | 直した | 前提と full clone を足した |
| 同 任意 9: `CM`:1072 の主張が古い | 直した | WP-3 で文ごと直した (61a) |
| 同 道具側 10 (不確実): `refs/replace` による差し替え | 直した | `GIT_NO_REPLACE_OBJECTS=1`、変異 M46g |
| 実装担当 (WP-1) の疑義 1: 代表 ref の無い行は 46a で照合されない | 観察 | 設計 §12.3 の 1 が受け入れている |
| 同 2: G1 / G2 で 0・負の `concurrency` は床 ≤ 0 で `confirmed` | 観察 | 古い検査と同じ挙動 |
| 同 3: 全 G0 の入力は検査 0 件で `confirmed` | 観察 | 設計 §6 のとおり。`generation` と `checks_evaluated` で見える |
| 監査: 完了ゲート 2 回目 FAIL (`CM` の版の行の裸の `ops.py`、主張 2 行が 300 字超) | 直した | 参照型の 1 文に縮め、パスを全部書いた。登録簿の検査 58 passed、ゲート 3 回目 (§1) |
| 監査 未充足 42・44・45・46・46b (逐語の記録) | 直した | 設計 §13 |
| 監査 未充足 58 (台帳の閉止) | 直した | v1.136 |
| 監査 証拠不足 43 (CI 3.12 の leg) | 観察 | push 再開後に main の run で照合 (設計 §12.3 の 3) |
| 監査 観察 1: WP-3 に `CM` 登録簿の検査が無い | 直した | `WO` §5.2 #60a |
| 監査 観察 2: 版の説明の 2 段の rollout の入口 | 直した | `CR`:3087-3088 |
| 監査 観察 3: 未追跡の WO・引き継ぎ書を `check_doc_refs` が見ない | 直した | `git add -N` の後に緑 |
| 監査 観察 4: 46g の行と設計の版数行 | 直した | 設計 v0.4 |
