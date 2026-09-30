# 引き継ぎ書 — 2026-09-30 R-115 (worker の突然死による audit の欠落) 実装の途中

本書は R-115 のチャットの区切りの記録である。規律の正本は `docs/work-orders/OPERATING_CONDITIONS.md`、R-115 の正本は設計 `docs/design/AUDIT_PROCESS_LOSS_V0_1.md` v0.5 と作業指示書 `docs/work-orders/WORK_ORDER_R115_AUDIT_PROCESS_LOSS_V1.md` (§11 の訂正註 1〜10 が裁定の全件) である。

## 1. 現在地

- worktree `.claude/worktrees/mystifying-hellman-56a270`、branch `claude/mystifying-hellman-56a270`、先頭 `9ae742d`、clean。**main へは未 merge** (契約の宣言と実挙動を同時に動かすため、全 WP の後に 1 回だけ merge する)。main `3b8699d` を `7ff8b69` で branch に取り込み済み (その後 main は進んでいる)。
- main に入っているのは設計と作業指示書 (`c729ab0`) と本書だけである。branch 上の作業指示書は訂正註 7〜10 まで進んでおり、main の写しより新しい。
- 台帳 R-115 行は未閉止のまま (状態の欄は WP-6 で直す)。

## 2. 本チャットで終えたもの (すべて branch 上)

| WP | commit | 内容 | レビュー |
|---|---|---|---|
| WP-1 | `95f6906`、`8f8e849` | 契約 1.13.0 `audit.process_loss_policy`、`version_binding` の段、`obligations` の項目、逐語ピン。peer の宣言は 1.12.0 のまま | 済み、差し戻し適用済み |
| WP-2 | `6f49408`、`a9c59af` | 新条件 (branch 上の `conformance-tests/test_c33_process_loss.py`。real-server、workers=2、全 worker を SIGKILL して `audit_query` を読む) と両 launcher の helper。同型性の表は 203 行 | 済み、差し戻し適用済み |
| WP-3 | `e1d021a`、`d8bcf6c` | MitateDB の durable audit sink を pool に。pool は 1.0 s を超えて idle だった接続を貸す前に 1 往復で確かめる。F-16 の式は不変 | 済み、差し戻し適用済み |
| WP-4a | `0359c51`、`d8bcf6c` | r2db: data 操作の event を応答の前に同期で書く。bounded buffer を削除。pre_commit を transaction の最後の文へ。schema の replay を durable に | 済み、指摘は `9ae742d` で適用 |
| WP-4b | `9ae742d` | MitateDB: 同上。両 peer の `outcome_note` を同一の文に。conformance の port `flush_audit_buffer` は残し、拒否の窓の sweep だけを担う | **未実施** |

実測 (実装担当の報告、`9ae742d` 時点): `MitateDB-api/tests` 1753 passed、`r2db-api/tests` 1657 passed、`tools/tests` 748 passed。新条件の「成功の event」は両 peer で緑。

branch 上で意図どおり赤のもの: 新条件の拒否の合計 2 件 (WP-5 で緑になる)、C-29 の版一致 6 件 (peer の版上げは WP-5)、`conformance-tests/test_control_mapping_register.py` の 3 件 (行番号参照と test 名のずれ。WP-6)。

## 3. 次の一手 (この順)

1. **WP-4b のコードレビュー** (`git show 9ae742d`)。観点は WP-4a のレビューと同じ (event を書かずに成功を返す経路、pre_commit の順序と error 行、fail-closed、cell lock を握る区間) に加え、MitateDB の `cell.py` の `_error_row_once_fired` (backend の 4 メソッドが hook の発火後に error 行を書かない穴を cell 側で包んだ判断)、単発の insert / update を pre_commit の経路に載せた判断、削除した test 13 件が守っていた性質。
2. **性能の計測 (監督)**: 設計 §8。`tools/perf_baseline.py --real-server <peer> --warmup 20 --n 200` を、branch の先頭と基点 (main) で交互に 3 巡、load average を記録する。道具に口の無いもの (real-server の mutate、r2db の K > 1 の keyed mutate、MitateDB の K=4 の cell lock の waits/acquire、未認証 flood 下の正規 tenant) は scratch の driver で測り、作業指示書 §10 に数値と手順を残す。real-server の launcher は ambient の `R2DB_*` / `MITATEDB_*` を取り除くので、値を渡すときは launcher の `_data_env` を差し替え、壊す値で起動が落ちることで注入を確かめる。閾値 (`docs/design/ROADMAP_POST_PHASE7_V1.md` §0.1.4) を超えたら依頼者へ上げる (1-A' には切り替えない)。
3. **WP-5** (作業指示書 §7、設計 §5 の 2-A): 両 peer の migration (counter table と加算だけの SECURITY DEFINER 関数)、process 内の coalescer の削除、`audit_query` の UNION の枝、memory backend の同じ意味、MitateDB の FORBIDDEN の audit 欠落の修正 (訂正註 9)、peer の版上げ (訂正註 7。戻した差分は `git diff c729ab0 95f6906 -- <16 file>`)、`KNOWN_FINGERPRINTS` の途中の行の整理。2 段 (peer ごと) に分けるとよい。
4. **WP-6** (作業指示書 §8): `security/CONTROL_MAPPING.md` の SI-14 と行番号参照・pin 名、両 peer の runbook (MitateDB は §10.6 → 7 版、§10.7 → 7 版、§10.10 → 11 版。訂正註 6)、R-113 設計 D-2 の表とフェーズ4 設計への覆しの註、`docs/design/CODE_COMMENT_PROVENANCE_V1.md` への註 (訂正註 9 の (2))、`docs/design/MITATEDB_STARTUP_CHECK_TOOL_V0_1.md` の行数の記述、台帳。取り込み後の main の実物に合わせて `COLLECTION_FLOOR`、台帳の版、`CM` の版を振る。
5. main を branch に取り込み → 完了ゲート (`tools/dev/gate.py -C <worktree> --label r115`) → 受け入れ監査 → runbook §10 の独立レビューと依頼者の受理 → main へ 1 回 merge → 引き継ぎ書と memory。

## 4. 依頼者判断待ち・未決

- 依頼者判断待ちは無い。
- 未決 (監督): port `flush_audit_buffer` を呼ぶ conformance の test が 0 件になった。WP-5 で拒否の窓が DB に移ると port の役割が無くなる。WP-5 の後に port を残すか消すかを決める (消すなら port の版の改訂で、依頼者裁定が要りうる)。
- 先で依頼者に求めるもの: runbook §10 の再受理 (確定)、性能が閾値を超えた場合の判断 (条件つき)。

## 5. 運用上の教訓

- real-server の launcher は ambient の peer 用 env を取り除く。env で渡した knob は黙って効かず、「差なし」の計測が出る。
- MitateDB に platform migration を足すと、runbook §10.6・§10.7・§10.10 の改版と再受理が必ず要る。着手の枠を決めるときに先に確かめる。
- `credential_request_rate_admit` は SECURITY INVOKER である。両 peer に SECURITY DEFINER の前例は無い。
- 2 peer にまたがる実装 WP は peer ごとに分ける (1 つの worktree で変異を回せるのは同時に 1 人)。レビューは commit を指して読み取りだけにすれば、次の実装と並行できる。
- 実装担当が利用枠の上限で途中終了したら、`SendMessage` で同じ担当を再開する (文脈が残る)。
- 契約の版上げは、peer の宣言を実挙動と同じ commit に置く。branch の途中の commit も bisect で当たる。

## 6. 裁定

本チャットのレビュー担当の指摘の全件 (`OC` §1.15 の 77)。設計レビュー 2 回と再確認 (F1〜F11、G1〜G11、H1〜H11) の反映は設計 §12 の表が正本である。以下はコードレビューの分。起票 0 件、既知の穴 0 件。

| 指摘 | 裁定 | 理由 |
|---|---|---|
| レビュー WP-1・1 (peer の版上げが実挙動より先) | 直した | 訂正註 7。WP-5 へ移した |
| レビュー WP-1・2 (`sink_failure_policy` の不変が未固定) | 直した | 全文の逐語ピン |
| レビュー WP-1・3 (確定文の要約の表記) | 直した | 要約と明記 |
| レビュー WP-2・F1 (件数 pin の取りこぼし) | 直した | `test_r78_pool_wait_stats.py` |
| レビュー WP-2・F2 (SIGKILL が未固定) | 直した | AST の試験。SIGTERM では空振りで緑になることを変異で実証 |
| レビュー WP-2・F3 (MitateDB の FORBIDDEN が audit に残らない) | WP-5 で直す | 訂正註 9 (依頼者裁定) |
| レビュー WP-2・F4、F5、F8、F9 | 直した | 文言、poll の上限の出所、成功を処理した pid の確認 |
| レビュー WP-2・F6 (版の分岐なし) | 観察 | skip は禁止。merge 時に両 peer が 1.13.0 を宣言する |
| レビュー WP-2・F7 (新条件の行が既に executable) | 観察 | main には緑の状態でしか入らない |
| レビュー WP-3・1 (F-9 の接続が書き込みと別の経路) | 直した | audit の pool から借りる |
| レビュー WP-3・2 (死んだ接続 1 本ごとに 503) | 直した | pool の idle ping (訂正註 8)。1.0 s 以内の切断の 1 件は残る |
| レビュー WP-3・3 (pool の大きさが env の上書きに従う) | 直した | F-16 が数える値で作る |
| レビュー WP-3・4 (fresh 接続を前提にした文言) | 直した | runbook の 1 箇所は WP-6 |
| レビュー WP-3・5 (途中の tree の指紋の行が増える) | WP-5 で直す | 最後の実装 WP の末尾で整理する |
| レビュー WP-3・6 (防御的な rollback が未固定、in-process adapter は pool 無し) | 直した / 観察 | 前者は test を足した。後者は in-process の plug の構成で、製品の経路ではない |
| レビュー WP-4a・1 (一意制約・値の違反の分岐で error 行なし) | 直した | `9ae742d` |
| レビュー WP-4a・2 (`outcome_note` の「1 例だけ」) | 直した | 両 peer 同一の文 |
| レビュー WP-4a・3、4、6 | 直した | hook の発火を見る、古い記述、data 未 commit の assert |
| レビュー WP-4a・5 (keyed mutate が lock を握ったまま往復) | 観察 | 性能の計測に足して判断する (§3 の 2) |
| 実装 WP-3 (b) (`MITATEDB_PLATFORM_POOL_SIZE` の上書きで床を超える既存の穴) | 観察 | credential 側の既存の性質で、本件で広がっていない |
| 実装 WP-4a (旧 knob を設定しても黙って無視される) | 観察 | 機能は消えており、害は無い |
