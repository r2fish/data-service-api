# 引き継ぎ書 — 2026-10-03 R-42 (期限切れ要求の意味論) 実施・閉止

本書は台帳 (`docs/design/ROADMAP_POST_PHASE7_V1.md` §8、以下 `RM`) R-42 の作業機の監督チャット (Fable) の記録で、`docs/archive/docs/work-orders/HANDOVER_20261003_R42_FABLE.md` (設計完了まで) の続きである。規律の正本は `docs/work-orders/OPERATING_CONDITIONS.md` (以下 `OC`)。本書の略記: 設計 = `docs/design/EXPIRED_REQUEST_SEMANTICS_V0_1.md`、`WO` = `docs/work-orders/WORK_ORDER_R42_EXPIRED_REQUEST_SEMANTICS_V1.md`、`CM` = `security/CONTROL_MAPPING.md`、`CA` = `docs/design/CONFORMANCE_ADAPTER_V1.md`。D-N・U-N・V-N・M-N・N-N は設計の番号、WP-N・完了条件・変異の V 番号は `WO` の番号である。

## 1. 現在地

- local main は `662d58a` (台帳 v1.160)。未送信で、送信は Mitate 経由 (`OC` §2 の 20)。
- 統合 branch `r42` の commit 列: `662d58a` → `a0b5d1d` (WP-2 port) → `c14faea` → `e332c34` → `5ef1fe1` (WP-3) → `7b6aced` → `62136cd` → `d510122` (WP-4) → `b2658e6` → `2910a5c` → `9d68964` (flip: WP-1 の契約 1.16.0、新条件 C-36、WP-3 の訂正、`CM` 3.19)。全 commit は `git log --oneline 662d58a..9d68964` で取れる。
- 完了ゲート (監督が `9d68964` の上で実行): gate: 5231 passed, 2 subtests passed in 509.14s (0:08:29), judge=PASS, label r42, pg_database/pg_roles diff 0
- 性能差分 (`$SP/perf-r42-compare.txt`。基準は local main `662d58a`、同日・同引数): K=1 の p50 の最大は +11.7% (MitateDB in-process query、0.128 → 0.143 ms)、K=32 の p50 の最大は +4.1%。`backend_calls` は不変。閾値 +40% / +50% の内側である。
- 閉止の commit は gate の後に監督が `tools/dev/finalize.py` で作り、main へ merge する。中身は 台帳 v1.161、設計 v0.11、`WO` §5・§6、本書、`COLLECTION_FLOOR` の更新、`tools/check_comment_provenance.py` の Known gaps 9。`CM` は 3.19 のまま。受け入れ監査 (`evidence-auditor` 1 回) も gate の後に行う。
- worktree の実体: `WO` の `.claude/worktrees/r42-wp1` / `.claude/worktrees/r42` は記号名である。実体は本チャットの session worktree (`.claude/worktrees/` 配下) で branch を切り替えた (subagent の他 worktree への書き込みが拒否されるため。`WO` §6 訂正註 1)。`r42-wp1` branch (WIP 4 commit) は main の履歴に入れず、内容として flip の commit に取り込んだ (同 訂正註 3)。`.claude/worktrees/r42-perfbase` (detached `662d58a`、性能の基準用) は閉止の後に畳む。

## 2. 本チャットで閉じたもの

各 WP は 実装 → コードレビュー A / B 並列 → 監督が変異を実行 → 差し戻し → 再確認 の順で閉じた。

- **WP-1 (契約 1.16.0・従属判断 21)。** `limits.execution_ms`、`versioning.version_binding` の 1.16.0 の段落、`versioning.obligations[12]`、`structured_operations.dry_run.decision` の末尾 1 文。設計 §9 の依頼者確定文を逐語で入れ、版の番号だけ読み替えた。変異は 14 件、レビュー B の 3 件、V3 / V14。
- **WP-2 (port v1.22、`CA` §32)。** `hold_after_admission`、放した後の文の数を返す handle、両 peer の `psycopg_counting.py` の `txn_open_count`。変異は 26 件、レビューの 4 件 (flip 後に実行)、差し戻しの分。
- **WP-3 (r2db)。** 期限検査を `_run` / `_transaction` に統合し、単独の検査点を 0 件にした。in-memory backend は operation ごとに検査し、apply_schema は入口と operation の直前の 2 点で検査する。変異 42 件。
- **WP-4 (MitateDB)。** 期限検査を `_execute` に統合した。schema 3 経路の順序を store → pre_commit → COMMIT に揃えた。SQLite backend には文の bound (progress handler) を入れた。変異 61 件。
- **WP-5 (flip と新条件 C-36)。** 3 vector に positive control を加え、6 plug で測った。版 gate は 1.16.0 で、全 plug を束縛する guard を付けた。M-8 は 6 plug で 100/100、B = 500 ms。測定の過程で見つかった WP-3 の訂正 (in-memory apply_schema の operation 直前の検査) も flip の commit に入れた。
- 記録 (閉止の変更セット): 設計 v0.11 の註 (1)〜(7) (`$SP/r42-design-v011-note.md`)、`WO` §6 の訂正註 1〜9 (`$SP/r42-wo-section6.md`)、台帳の文面 (`$SP/r42-ledger-texts.md`)。

## 3. 次の一手

1. 依頼者の事後確認。対象は §4 と「裁定」節の全件。
2. main の送信は Mitate 経由で行う。
3. worktree を `tools/dev/fold.py` で畳む (`r42-perfbase` を含む)。
4. `conformance-tests/test_c20_*.py`:154 と `test_c22_*.py`:186 が引く `structured.py:1821` が古い (観察、基点から)。

## 4. 依頼者判断待ち・未決

依頼者指示 (2026-10-03「裁定事項が出た場合は、監督推奨で進めて、後から確認」) により、裁定は全件を監督推奨で進めた。事後確認の対象は「裁定」節の全件である。とくに次の件:

- `reference_wall_clock` の定義文を契約に足さない (WP-1 レビュー A-3 / B-7)。
- in-memory apply_schema を 2 点で検査する (入口 + operation の直前。WP-3 実装報告、実測の起動)。
- schema 経路の store の例外を batch 側と同じ写像にする (WP-4 レビュー A-3)。
- `hold_after_plan_verification` の docstring に `LIMIT_EXCEEDED` の場合を足す (WP-2 実装報告)。
- `txn_open_count` を製品の `psycopg_counting.py` に置く (WP-2 実装報告)。
- SQLite の progress handler の粒度は 1000 命令 (WP-4 実装報告)。
- idempotency 表が無いときの `UndefinedTable` が、schema 経路で 404 から 503 に変わる (WP-4 差し戻し 1 の後)。
- 運用手順書の `contract_version == "1.6.0"` (`r2db-api/deploy/DEPLOYMENT_RUNBOOK.md`:847、`MitateDB-api/docs/cloud-run-cloud-sql.md`:1542)。観察。規模 S で直すかを依頼者に問う。
- C-09 が人工高負荷の下で一過性に赤になった (観察)。

## 5. 運用上の教訓

- **(a) 検査点の文を 1 つ消すと provenance checker の §4.1 (2) が全部赤になる。** 直前にある CH-ID 無しの塊の鍵が次の文へ移るためである。CH-ID 化で解く (`tools/check_comment_provenance.py` の Known gaps 9)。
- **(b) `tools/check_comment_provenance.py --base` は作業ツリーを書き換えずに回す。** §4.1 (1) の赤は想定内として報告する。
- **(c) `tools/dev/pt.py` の `--wait` は `--` の前に置く。** 後ろに置くと pytest に渡り、exit 4 になる。
- **(d) 並行チャットで main が進む。** 本チャット中にも R-30、R-120 (2 回) で進んだ。統合 branch は WP の前に main を取り込み、`CM` と台帳の版は現物から取る。
- **(e) 中間 commit で未定義の条件番号を文書が名指すと `check_doc_refs` が赤になる。** 番号は flip の commit で付ける。
- **(f) 新条件の positive control は、版 gate のため flip まで空振りになる。** port の事実は、版に依らない配線テストで固定する。
- **(g) B は人工負荷 (burner) で代用して決めた。** gate 相当の負荷での到達時間の最大の 2 倍以上を取った。

## 6. 裁定

`OC` §1.15 の 77。材料は監督の裁定記録 (`$SP/r42-rulings.md`) の全表である。番号は各報告の番号で、R-N (差し戻しの項) は各差し戻し指示の番号を指す。「依頼者確認待ち (監督推奨で進めた)」は §4 の依頼者指示による。

| 指摘 | 裁定 | 理由 |
|---|---|---|
| WP-1 レビュー A-1: WIP commit を merge で取り込むと flip が「最後の 1 commit」に入らない (不確実) | 直した (内容として flip の commit に取り込んだ。`WO` §6 訂正註 3) | D-6 (B) の字義を守る。`7f23864` は main から到達しない |
| WP-1 レビュー A-2 / B-3: 宣言コメント・Revision note 12・README・CH companion が義務を言い換え、「same commit」が偽 | 直した (差し戻し 1 R1) | 確定文言の規律 (`OC` §1.5 の 36)。4 識別子と契約の指し先だけにした |
| WP-1 レビュー A-3 / B-7: `reference_wall_clock` の定義文が契約に無い (完了条件 16) | 観察 (足さない。依頼者へ上げる) | 確定文の外の契約追記には依頼者確認が要る。義務は status に依らず無条件で、DB の利用者が気づく差は無い |
| WP-1 レビュー A-4: 運用手順書の期待値 `contract_version == "1.6.0"` | 観察 | DB の利用者は読まず、§0.1 を破らない。配備側の記述で WP-1 の経路外。規模 S で直すかを依頼者に提示する |
| WP-1 レビュー B-1: 完了条件 3 の U-9 の裁定が docstring でなくコメントにあり、docstring が旧文 | 直した (R2) | `WO` の字義 |
| WP-1 レビュー B-2: CCR_DISPOSITION 21 が先例の形 (逐語引用) と違う | 直した (R3) | 先例 19・20 に揃えた |
| WP-1 レビュー B-4: provenance 検査のために追跡中の src を一時的に書き換えた | 直した (R4。素のまま再実行し、逐語で報告) | §4.1 (1) の赤は想定内 (先例 R-120)。作業ツリーは書き換えない |
| WP-1 レビュー B-5: 報告の件数 29 → 30 | 直した (R5) | 報告の数え違い |
| WP-1 レビュー B-6: `_PRE_1_8_0_LIMITS_KEYS` → `_LIMITS_KEYS_1_16_0` の改名で、設計・`WO` の記号名が古くなった (不確実) | 直した (設計 v0.11 の註 (5)) | 行は消さない (`OC` §1.8 の 56) |
| WP-1 レビュー B 変異 RB-V5b / RB-V12b / RB-V12c | 実行 3/3 red | 監督が実行 |
| WP-1 実装担当の疑義: 1.7.0 の義務 (3) の narrowing が 1.7.0 の文の側から見えない | 観察 (足さない) | 確定文の範囲。dry_run.decision 末尾の 1 文が相互参照を担う |
| WP-1 実装担当の疑義: `tools/contract_catalog.py` は spec の 1 部しか書かず、peer の 2 部は cp | 観察 | `--check` が 3 部を照合する (完了条件 11) |
| WP-1 実装担当の疑義: `docs/design/OBJECT_STORAGE_BINARY_API_V0_1.md`:754「改版 (1.15.0 以降)」 | 観察 | 将来の版への言及で、計画文書である。1.16.0 以降と読める |
| WP-1 再確認-1: CCR 21 の注記が自己矛盾 | 直した (監督、WIP commit 3) | 文言 1 語 |
| WP-1 再確認-2: 報告 §8 の 3・6・9 が差し戻し前の記述 | 直した (報告 §11 に注記) | scratchpad の報告 |
| WP-1 再確認 観察: `--base 7f23864` で §9.3 (2) が 2 件赤 (CH-0142・CH-0542) | 観察 | base は `2fdc894` (`7f23864` は main に到達しない) |
| WP-2 実装報告: `hold_after_idempotency_lookup` の docstring 改訂文 (完了条件 24) | 確定 (提案の 2 文に、直前の文へ予算切れの先着を足した 3 文)。依頼者確認待ち (監督推奨で進めた) | 予算切れの先着では「commit した後」が偽になる |
| WP-2 実装報告: `hold_after_plan_verification` に `LIMIT_EXCEEDED` の場合を足すか | 足した (`CA` に【追記】。`WO` R102 は記録なので触らない)。依頼者確認待ち (監督推奨で進めた) | 6 plug の現物で真 |
| WP-2 実装報告: C-36 の Condition 文 | 確定 (test の具体値を外し、PostgreSQL の限定を 1 文に集めた)。依頼者確認待ち (監督推奨で進めた) | Condition は性質を述べ、test の値は述べない |
| WP-2 実装報告: `txn_open_count` を製品の `psycopg_counting.py` に足す | 採用。依頼者確認待ち (監督推奨で進めた) | 設計 D-7 が置き場の候補として明示している。R-79 の計数と同じ性質で、test 用 hook ではない |
| WP-2 実装報告: `txn_open_count` を単独で殺す単体テスト (両 peer の `test_r79_prepared_stats.py`) | 足した (触ってよいパスを拡張。`WO` §6 訂正註 4)。依頼者確認待ち (監督推奨で進めた) | `OC` §1.5 の 33 (変異先行) |
| WP-2 実装報告: `hold_after_admission` の docstring が MitateDB の単一行書き込みまで含めて言う | 直した (事実だけに。plug ごとの到達形は `CA` §32.2 に開示)。依頼者確認待ち (監督推奨で進めた) | 言い過ぎ |
| WP-2 実装報告: MitateDB の stall が concurrency slot を保持する | 観察。依頼者確認待ち (監督推奨で進めた) | 契約の点の定義どおり |
| WP-2 実装報告: 配線テスト 3 本・primitive test 1 本・`_reserve` の arming の消費・handle の default field | 認める。依頼者確認待ち (監督推奨で進めた) | 設計の意図の範囲 |
| WP-2 実装報告: 完了条件 25 を B = 0 で実測 | 認める (WP-4 の後に再測)。依頼者確認待ち (監督推奨で進めた) | 現 tree では検査が stall 点の前に無い |
| WP-2 実装報告: `CA` §32 が C-36 を名指すと、中間 commit で `check_doc_refs` が赤 | 直した (port の commit では「C-35 の次」と書き、flip の commit で C-36 に戻した。`WO` §6 訂正註 2)。依頼者確認待ち (監督推奨で進めた) | 設計 D-7 も同じ理由で番号を書かない |
| WP-2 レビュー A-F1 / B-1: primitive test が版で束縛されている (RA-1 green) | 直した (差し戻し 2 R1。修正後の RA-1 は red) | port の事実は版に依らない |
| WP-2 レビュー A-F2: V28a / V28b / V31a が生き残る見込み (不確実) | 直した (WP-3・WP-4 で検査点を helper に統合し、V28 / V31 は経路上の最初の文の前の検査すべてを外す。`WO` §6 訂正註 6) | D-9 の推奨 |
| WP-2 レビュー A-F3: meter の重点 2 点を固定する永続 test が無い | RA-2a〜c を WP-4 の後に実行し、3/3 red (`CA` §32.3 に記録) | 観測できない分は開示する方針。3 件とも観測できた |
| WP-2 レビュー A-F4: 文の数が負になり得る | 直した (R5、開示) | 製品の fold は変えない |
| WP-2 レビュー A-F5 / B-4: 算式の文が executemany を落としている | 直した (R3) | 文面のみ |
| WP-2 レビュー A-F6: 「request-shape checks」が言い過ぎ | 直した (R4) | 事実に合わせた |
| WP-2 レビュー B-2: guard が束縛集合の空を見ない | 直した (R2。RB-V33-guard-set-empty は flip の後に実行) | V33 の字義 |
| WP-2 レビュー B-3: `CA` §32.2 に実測が無い | 直した (R6。実測は実測の起動で記入) | 主張は実測の後に置く |
| WP-2 レビュー B-5: `CA` §30.1 の【追記】漏れ | 直した (R7) | 追記漏れ |
| WP-2 レビュー B-6: port の test が中間 commit に無い | 観察 | WP-4 直後の実測が受け止める |
| WP-2 レビュー B-7: 完了条件 27・38 が root suite でしか緑にならない | 直した (`WO` §6 訂正註 7) | 読み替え |
| WP-2 レビュー B-8: Status / CH の文言 | 直した (R8) | 文面 |
| WP-2 レビュー B 観察: 同型性の行は sha256 test が代替する / socket の item は未観測 / C-05 の Status は 2995/3000 字 | 観察 | 担当の観察。socket の item は監督が 6/6 red で観測した |
| WP-2 差し戻し 2 の後: 「request-shape checks」が plug の 3 file に残っていた | 直した (監督、`c14faea`) | 同じ stall 点の主張 |
| WP-2 差し戻し 2 の後: RA-1 (修正後) | red (1/1) | F1 / B-1 は閉じた |
| WP-2 再確認-1: `CA` §32.3 (2)「偽の緑にはならない」は言い過ぎ (MitateDB release の例外) | 直した (監督、`e332c34`) | 文言 |
| WP-2 再確認-2: C-36 の Status の「liveness statement」が r2db の `SET search_path` を落としている | 直した (監督、flip の commit) | 文言 |
| WP-2 再確認-3: catalog 読みが hold に捕まったときの失敗文言が汎用 | 観察 | 赤になり、ハングしない。影響は診断性だけ |
| WP-3 実装報告: in-memory apply_schema の operation 後の検査が残っている (完了条件 51 の列挙漏れ) | 直した (差し戻し 1 R1。`WO` §6 訂正註 5)。依頼者確認待ち (監督推奨で進めた) | D-9 の「同じ意味論」。単独の点を残さない |
| WP-3 実装報告: 期限切れの要求も pool checkout を 1 回使う | 観察。依頼者確認待ち (監督推奨で進めた) | D-9 / U-1 の帰結 |
| WP-3 実装報告: `_run` の 1 点が単一故障点になる | 観察。依頼者確認待ち (監督推奨で進めた) | D-9 の選択 |
| WP-3 実装報告: 実時計で execution_ms = 1 の要求は常に拒否される | 観察 (依頼者へ報告)。依頼者確認待ち (監督推奨で進めた) | 設計 §9.1 (契約文) の帰結 |
| WP-3 実装報告: 接続に `request_budget` 属性を付けて `_run` へ渡す | 認める。依頼者確認待ち (監督推奨で進めた) | 設計は渡し方を定めない |
| WP-3 実装報告: 文を消すと、CH-ID 無しの塊の鍵が次の文へ移り §4.1 (2) が赤 | 直した (道 (a): CH-ID 化し、companion `docs/code-history/r2db-api/structured.md` を新設 (CH-0552〜CH-0564)。事実とずれた 2 件は受け皿に原文を残す)。依頼者確認待ち (監督推奨で進めた) | 既存の規律 (D-1 の受け皿) で解ける。checker の規則変更は R-42 の範囲外 |
| WP-3 実装報告: 上の checker の挙動 (塊の直後の文を消すと鍵が移る) | 既知の穴 (`OC` §1.12 の 71。Known gaps 9)。依頼者確認待ち (監督推奨で進めた) | 偽の赤であり、製品の欠陥は通らない |
| WP-3 実装報告: 変異 V51h (入口検査を外す) を追加した | 認める。依頼者確認待ち (監督推奨で進めた) | 「単独では外せない」の文を実測に置き換えた |
| WP-3 レビュー A-1: connect_timeout の docstring の下限 (psycopg は 2 s に引き上げる) | 直した (差し戻し 3 R1) | 文面 |
| WP-3 レビュー B-1: 追随した test の名前「rolls back」が偽 | 直した (R2) | `OC` §1.5 の 40b |
| WP-3 レビュー B-2: in-memory apply_schema が期限検査より前に idempotency を照会する (不確実・両論) | 直した ((b) 揃える。R3: 検査を照会の前へ移し、test と V51i を足した) | D-9 の「同じ意味論」。storage 操作 = 文 |
| WP-3 レビュー B-3: 完了条件 45 の「再設定しない」に変異が無い | 直した (RB-V45b を監督が実行して red。spec に取り込んだ) | `OC` §1.5 の 33 |
| WP-3 レビュー B-4 (a)(c)(d): docstring・報告の件数・差し戻し 1 の変異の記録 | 直した (R4) | 文面・報告 |
| WP-3 レビュー B-4 (b): pool 待ちの test が待ちを確かめない | 観察 | V52 は待ちに依らず赤になる |
| WP-3 レビュー B-5: 触ってよいパスの外 (test_foundation、ast allowlist)、CH-ID の manifest 予約 | 直した (`WO` §6 訂正註 4) | 追随と 40b の範囲 |
| WP-3 差し戻し 3 の後: 旧 test 名が `security/CONTROL_MAPPING_HISTORY.md`:175 に残る | 観察 | 履歴の記録は書き換えない |
| WP-3 差し戻し 3 の後: 実装担当が `--collect-only -q` を venv の pytest で直接実行した | 観察 (DB に触れない collect だけ) | `OC` §1.10 の 66 の趣旨は守られている |
| WP-3 差し戻し 3 の後: 差し戻し 1 の変異 8 件の集計行の file が無い | 認める | 同じ 8 entry を含む 10 件の再実測の集計行で代えた |
| WP-3 再確認-1: module docstring の限定が 1 test について字義どおりでない | 直した (監督、`62136cd`) | 文面 |
| WP-3 再確認-2: `test_c20`:154 / `test_c22`:186 の `structured.py:1821` が古い (基点から) | 観察 | R-95 の検査は範囲内だけを見る。WP-3 の範囲外 |
| WP-4 実装報告: SQLite の idempotency の dict 操作を文と見なさない | 認める (観察)。依頼者確認待ち (監督推奨で進めた) | 設計 §9.1 の「文を取らない storage」は in-memory backend の話。SQLite backend の storage は SQLite である |
| WP-4 実装報告: progress handler は 1000 命令ごとに時計を見る (粒度) | 認める (`CM` と docstring に開示)。依頼者確認待ち (監督推奨で進めた) | 字義 (算出時の残りを超えない bound) は満たす |
| WP-4 実装報告: pool 取得の途中で新規接続を開いてから拒否する経路がある | 観察。依頼者確認待ち (監督推奨で進めた) | 設計 §9.1「接続確立は残りを超え得る」と D-9「pool 取得の後」の帰結。r2db と同じ |
| WP-4 実装報告: `_retime` の `<= 0` を削除し、V58 を読み替える | 認める。依頼者確認待ち (監督推奨で進めた) | 単独の点を減らす方向 |
| WP-4 実装報告: `record_idempotency` のその他の psycopg 例外 → StorageTransientError (503) | 認める。依頼者確認待ち (監督推奨で進めた) | 「翻訳」の範囲。到達不能は 503 のまま (V-3) |
| WP-4 実装報告: `test_application_audit` の旧 test を書き換えた | 認める (設計 §1.4 #7 と台帳 R-42 行の旧 test 名は、設計 v0.11 の註 (4) と閉止の【追記】で引き直す)。依頼者確認待ち (監督推奨で進めた) | 事実が設計どおり変わった |
| WP-4 実装報告: 触ってよいパスの外の pin の追随 3 file、companion 3 file | 直した (`WO` §6 訂正註 4)。依頼者確認待ち (監督推奨で進めた) | 40b の範囲 |
| WP-4 レビュー B-1: `CM` の行参照 21 件が別の行を指す (CH-0566 で +3) | 直した (差し戻し 1 R1。高) | 主張と現物が違う |
| WP-4 レビュー A-1 / B-3: SQLite で打ち切った文の rollback が handler の下で走る | 直した (R2。test と V68c を足した) | N-4 の字義 |
| WP-4 レビュー A-2 / B-4: `test_sqlite_stops_…` が空振り (RA4-1 / RB4-1 が green) | 直した (R3) | `OC` §1.5 の 32 |
| WP-4 レビュー A-3: schema 3 経路の store で、予算以外の psycopg 例外が VALIDATION_FAILED になる | 直した (batch 側と同じ写像に。R4。test と V65e を足した) | 分類の誤り。到達不能は 503 (V-3) |
| WP-4 レビュー B-2: `audit_hook.py` の module docstring が旧順序 | 直した (R5。パスを拡張、CH-0567) | 事実と違う記述を残さない |
| WP-4 レビュー B-7: deadlock 分岐が区別できない (RB4-2 green) | 直した (分岐を統合し、文を落とした。R6) | 同じ型・同じ写像 |
| WP-4 レビュー B-5 / B-6: 文面・件数 | 直した (R7) | 文面・報告 |
| WP-4 レビュー B 観察: `CM`:883・:967 は WP-2 の新条件の部の対象 | 直した (実測の起動で扱った) | `WO` の割当どおり |
| WP-4 差し戻し 1 の後: idempotency 表が無いときの `UndefinedTable` が、schema 経路で 404 → 503 (transient) に変わる | 観察 | batch 側の既存の写像と同じ。元の 404「collection not found」は誤り。恒久的な構成不備を別 code にするかは設計判断で、R-42 の外 |
| WP-4 差し戻し 1 の後: RA4-1 を実装担当が実行した (監督が実行すると指示していた) | 認める (red。spec は不変) | 実測は得られた |
| WP-4 差し戻し 1 の後: `audit_hook.py`:22 の例外文も落とした (指示の 2 点の外) | 認める | 事実に合わせた |
| WP-4 再確認-1: `CM`:1094 の `cell.py:2749` が 22 件目のずれ | 直した (監督、`2910a5c`) | 主張と現物が違う |
| 実測の起動: r2db in-memory の (iii) negative が 0/100 (apply_schema の検査が入口の 1 回だけ) | 直した (WP-3 の訂正: operation の直前に検査を足し、入口の検査は残す。単体テストと V51j を足し、flip の commit に入れた) | 完了条件 51「各 operation の前で検査」、D-2 (c)。入口と operation は別の点 |
| 実測の起動: B = 500 ms (保持 600 ms) | 確定 | 到達の最大は 239.4 ms (人工高負荷)、gate 相当では 84.5 ms。2 倍以上の余裕がある |
| 実測の起動: V28a2 / V28b2 (bound を残し、文の数で赤) を追加し、http / socket を別 entry にした | 認める | 観測するのが code ではなく文の数であることの確認 |
| 実測の起動: C-09 が人工高負荷 (scratch 3000 要求) の 1 回だけ、wire plug 4 つで赤 | 観察 (原因は未確認。gate で再現したら起票を検討する) | 本 file の要求数では再現していない |
| 実測の起動: `CM`:967「unlike r2db-api's own data plane」が現物と合わない | 認める (「Neither peer …」に訂正) | 設計 §11.5 RW-16 (現物と照合してから直す) |
| flip 候補の再確認-1: CH-0552 のコメント「checked once at entry」が偽 | 直した (`9d68964`。CH-0552 に訂正記録) | 事実に合わせた |
| flip 候補の再確認-2: `CM` の SI-11 r2db Evidence で claim と引用 test が合わない | 直した (`9d68964`) | 主張と実測が違う |
| flip 候補の再確認-3: 「after the plan check」は実際には compute_plan_token の後 | 直した (`9d68964`) | 文面 |
| flip 候補の再確認-4: dry run の最大 138.1 ms は positive control の母集団の値 (B の下では 27.6 ms) | 直した (`9d68964`) | 定義と母集団を揃えた。B = 500 の結論は変わらない |
| flip 候補の再確認-5: CH:485 の file 数 | 直した (`9d68964`) | 文面 |
| flip 候補の再確認 変異 RR-1 (新しい検査を stall 点の前へ移す) | red (レビュー担当が実行) | C-36 (iii)[r2db-api] が位置を固定している |
| flip 候補の再確認: (i)(ii) を検査追加後に再測していない | 観察 | apply_schema を通らない。gate で 1 回走る |
| レビュー B (WP-4) 観察: `_timeout_ms` は元からある名前 | 観察 | — |
| レビュー B (WP-4) 観察: mutate の log の test source 53 行が現物と一致 (変異の実行後に test が変わっていない) | 観察 | — |
| レビュー B (WP-4) 観察: V56・V58a の 2 点同時除去は妥当 (単独は V56a・V58a3・V59・V58b が殺す) | 観察 | — |
| 監査 75: flip の commit に WP-3 の訂正 (in-memory apply_schema の operation 前の検査) が入る (未充足・字義) | 訂正註 10 で読み替え (分けない) | D-6 (B) の目的は保たれ、実測で見つかった訂正を同じ commit で直した |
| 監査 81: `ledger.py --check` の出力が記録に無い (証拠不足) | 直した (WO §5.4 に逐語) | — |
| 監査 84: 3 つの検査器の出力が記録に無い (証拠不足) | 直した (WO §5.4 に逐語) | — |
| 監査 A1: 設計 v0.11 の註 (2) の dry run 138.1 ms が母集団違い | 直した (27.6 ms と positive control の 138.1 ms に分けた) | 再確認-4 と同じ |
| 監査 A2: WO §5.3 の「9d68964 の内容」と `commit=2910a5c-dirty`、他の pytest 無しの記録 | 直した (WO §5.3) | 差はコメント・文書のみ |
| 監査 A3: 性能の全表が scratchpad にしか無い | 直した (WO §5.3 に全表) | 記録は repo に置く |
| 監査 A4: WP-3 報告の `grep -c` の件数が 5ef1fe1 の現物 (9・9) と合わない | 観察 | scratchpad の報告。CM の現物は register が照合 |
| 監査 観察 1: 本書の裁定表で 2 行が連結、監査の placeholder 行の体裁 | 直した | — |
| 監査 73: 差し戻し後の集計行が報告に無く log だけ (`1929 passed`・`248 passed`) | 観察 (gate で充足) | — |
