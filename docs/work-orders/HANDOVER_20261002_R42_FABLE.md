# 引き継ぎ書 — 2026-10-02 R-42 (期限切れ要求の意味論) 設計起草

本書は台帳 (`docs/design/ROADMAP_POST_PHASE7_V1.md` §8) R-42 の設計起草の cloud session の記録である。規律の正本は `docs/work-orders/OPERATING_CONDITIONS.md` (以下 `OC`)、R-42 の正本は設計 `docs/design/EXPIRED_REQUEST_SEMANTICS_V0_1.md` v0.3 (以下「設計」) である。

## 1. 現在地

- 環境: cloud session (PostgreSQL 無し。新しい実測はしていない)。branch `claude/happy-einstein-f2oyqf` (origin に push 済み)。基点 local main `4241b55` (= branch の起点。main には merge も送信もしていない)。
- 成果物: 設計 v0.3 (commit `98e2f00`)、本書 (本書の commit)。
- 規律: 台帳 R-42 (規模 L、Class D として発注)。契約を触るので設計レビューは 2 回 (`OC` §1.7 の 50)。1 回目は本 session で行った (A / B の 2 起動を並列 + 再確認 1 起動、§1.7 の 50a)。2 回目は依頼者裁定の反映後に行う。
- 触っていないもの: `spec/`、`security/`、`conformance-tests/`、両 peer、台帳、版数ログ、既存の引き継ぎ書の archive への移動。
- cloud の作業条件: `.venv` (Python 3.11) を作り、pre-commit を入れた (`pre-commit install` 済み)。identity は r2fish の noreply に設定した。commit は `tools/dev/finalize.py -C . --branch claude/happy-einstein-f2oyqf --no-merge` で行った (doc 参照・公開値スキャン・空 `.md` の検査は finalize が実行)。`tools/dev/handover_ready.py` は main checkout が main 上にあることを前提にするので、cloud では使っていない。

## 2. 本チャットで閉じたもの

- 探索: explorer 4 起動 (r2db / MitateDB の期限と待ちの経路、契約・conformance・SI の所在、既存の設計文書と台帳行) と reader 3 起動 (r2db、MitateDB、契約・conformance・CONTROL_MAPPING)。台帳 R-42 行と現物の差を確かめた。MitateDB の `ApplicationCell._lock` は台帳 R-102 で廃止済み。r2db は backend の入口に `check_deadline` を持つが、pool と apply_schema に穴がある。MitateDB は pool と lock の後に検査を持つが、scope の入口と文の間に穴がある。
- 枠決め (監督): 決定 設計 D-1〜D-9、却下 X-1〜X-8、未確定 U-1〜U-7、作業機で測る M-1〜M-8。
- 起草: drafter が v0.1 を書いた。起草の疑義 8 件は監督が裁定した (疑義 2: 1 ms の budget では stall 点に届かない → vector (i) と (ii)(iii) で予算の決め方を分けた)。
- 設計レビュー 1 回目: A 9 件・B 15 件を 19 件 (設計 §11.1 の RV-1〜RV-19) に統合した。採否は「裁定」節。v0.2 に反映し、設計 U-8・U-9 を新設した。
- 再確認: reviewer 1 起動 (担当観点: 指定なし) が 12 件 (F1〜F12) と観察 1 件を返した。全件「直す」と裁定し、v0.3 に反映した (設計 §11.2 の RC-1〜RC-13)。再々確認は行っていない (RC-1・RC-2・RC-7 の反映は監督が直読みで確かめた)。
- 静的検査: `check_doc_refs OK: 0 dangling references`、`public_value_scan` `total_flagged=0`、pre-commit の 3 hook (public-value-scan / check-doc-refs / ledger-check) は Passed。

## 3. 次の一手 (作業機)

1. branch `claude/happy-einstein-f2oyqf` を取り込む。fetch し、設計と本書の 2 commit を確かめる。worktree `.claude/worktrees/r42` を作り、main へ `--no-ff` で merge するのは監督。本書を commit する変更セットで最新 2 通から外れる `docs/work-orders/HANDOVER_20261001_R102_FABLE.md` を `docs/archive/docs/work-orders/` へ `git mv` する (`OC` §1.16 の 78。cloud では行っていない)。
2. 台帳の版上げ: R-42 行に【追記 2026-10-02】(設計 v0.3 の所在、設計 U-1〜U-9 が裁定待ち、起票候補 1 件) を書く。6 版目の版数ログ行を archive へ移す (§1.16 の 78)。起票候補「MitateDB の schema 操作の cancel 分岐に `commit_failed` が無い (allow 行だけが残る)」を §8 に起票して R-N を採番し、設計 D-9 の該当行に番号を入れる。
3. 作業機で測る項目 設計 M-1〜M-8 (設計 §8) を測り、設計 §1.5・§8 に実測を【追記】する。特に M-1 (1 ms 経路の再現。両 peer、MitateDB の 503 を含む) と M-4 (COMMIT が cancel されたときの成否) は、設計 U-6 と §9 の【保留】文に効く。
4. 依頼者裁定 設計 U-1〜U-9 を得て、設計 §10 に逐語で記録する (`OC` §1.7 の 51、§1.5 の 35: 確定文言はファイル経由)。契約文 (設計 §9) は依頼者が確定する。
5. 設計レビュー 2 回目 (裁定の反映後。A / B の 2 起動を並列 → 再確認)。
6. 作業指示書 (Change Set Manifest) を書く。順は 契約 1.15.0 → conformance (新条件、port v1.22、C-05 / C-24 / CONTROL_MAPPING の開示の書き換え) → 両 peer の実装 (設計 D-9) → 完了ゲート (`tools/dev/gate.py`。契約ファイルを触るので root suite の完走と性能差分) → 受け入れ監査 (evidence-auditor 1 回) → 台帳の閉止。
7. 完了ゲートはすべて作業機で走らせる。cloud では走らせていない。

## 4. 依頼者判断待ち・未決

設計 §5 の要旨 (両論と推奨。逐語は設計):

- U-1 計測の始点と待ちの算入: (a) 受理点から、pool・lock の待ちをすべて数える (**推奨**) / (b) 受信時から (認証・body 解析も数える) / (c) 最初の文から (待ちを数えない) / (d) 待ちを別 class に分ける。
- U-2 文の途中の期限切れの上限 (文の実行区間): (a) 現行の形 + 文の間の時計検査 (上限 < 残りの 2 倍、往復を足さない。**推奨**) / (b) 文ごとに `SET LOCAL` を再設定 (文ごとに 1 往復、費用は M-3) / (c) PostgreSQL 17 の `transaction_timeout`。
- U-3 再送可否の伝達: (a) 何も残らない保証だけ (**推奨**。v0.2 で (b) から移した) / (b) 加えて `details.futility` を MAY (実装は「再送しても同じ」を知り得ない) / (c) 必須の新 key (却下)。
- U-4 契約の版: (a) minor 1.15.0 + subordinate ruling 20 + obligations entry (**推奨**) / (b) major (既存の義務 1.7.0 (3) を execution_ms について狭めること、今 200 になり得る要求を拒否に変えること) / (c) 版を上げず註だけ。
- U-5 conformance の範囲と観測の形: (a) 新条件の (i)〜(iii) を port v1.22 の新 primitive 込みで全部 (**推奨**) / (b) (ii)(iii) を先に、(i) は後続。観測は handle が「放した後に発行された文の数」を返す形 (**推奨**) / 応答 code だけ。
- U-6 pool 待ち超過・接続確立・commit 段の code: pool 待ちは (a) 両 peer とも `LIMIT_EXCEEDED` execution_ms (**推奨**) / (b) r2db の 503 を許す。接続確立は (a) 予算由来の超過は 413 / (b) 503 のまま。commit 段は (a) `LIMIT_EXCEEDED` execution_ms (**推奨**) / (b) `SERVICE_UNAVAILABLE`。
- U-7 閾値: (a) 残り < 1 ms で拒否 (**推奨**) / (b) 残り ≤ 0 で拒否 (現行の `_retime`) / (c) 残り < 安全余裕 (例 5 ms)。
- U-8 最後の文が完了した後の時計検査: (a) 検査しない。設計 D-2 (d) を置かず、COMMIT は最後に設定した文の bound だけで打ち切る (**推奨**) / (b) 検査する。(d) を置き、read は SELECT の後にも検査する。
- U-9 `limits.execution_ms` の置き場: (a) `limits` の新 key (`_PRE_1_8_0_LIMITS_KEYS` の pin の切り直しに依頼者確認が要る。**推奨**) / (b) `limits.profile` の文字列の中 (1.8.0 の文より前に挿入すれば endswith の pin はそのまま) / (c) `limits.request_budget` の末尾 (包含の pin はそのまま)。

未決 (依頼者判断ではなく作業機の実測に依る): 設計 §9 の commit 段の【保留】文 (M-4)、vector (ii)(iii) の予算 B の値 (M-8)、MitateDB の `SET` が 1 ms で cancel され得るか (M-1)。

## 5. 運用上の教訓

- 台帳行の file:line と機構の記述は、起票から 2 週間で陳腐化していた (台帳 R-102 が cell lock を廃止した)。設計の前に現物で取り直す手順 (explorer → 監督の直読み → reader) が効いた。
- 「予算を最小 (1 ms) に狭め、stall で期限切れを作る」は、stall 点より前に文や検査がある経路では空振りする。vector ごとに「stall 点に届く予算」と「stall 点に入った合図からの保持」を分けて設計する。
- 単調性の論法 (拒否の方向は負荷で揺れない) は、放した後にしか効かない。stall への到達・dry run・再送は成功の方向なので、positive control と B の余裕が要る。
- cloud session では PostgreSQL が無い。PostgreSQL の挙動に依る主張を【既存実測 / PG 文書 / 未確認 → M-N】で分けて書く形は、レビューでも「実測できない」観点を切り分けやすかった。
- `max(1, …)` を単に外すと `statement_timeout = 0` (無効) になり fail-open する (レビュー B の F1)。閾値は「残り < 1 ms で拒否し、0 を返さない」。

## 6. 裁定

`OC` §1.15 の 77。材料は起草の疑義 8 件、設計レビュー 1 回目 (A 9 件・B 15 件 → RV-1〜RV-19)、再確認 (F1〜F12 と観察 1 → RC-1〜RC-13)。レビュー報告は持ち越せないので全件を載せる。表の順は時系列。

| 指摘 | 裁定 | 理由 |
|---|---|---|
| 起草の疑義 1 (新条件に C-35 の次の番号を書くと、`tools/check_doc_refs.py` が未定義の C 族番号として止める) | 直した | 「新条件」と呼び、番号は conformance の WP で採番 (先例 `docs/design/MULTI_PROCESS_WORKER_V0_1.md:766`) |
| 起草の疑義 2 (`budget.execution_ms = 1` では vector (ii)(iii) の stall 点に届く前に拒否され、空振りする) | 直した | (i) は 1 ms・保持 100 ms。(ii)(iii) は stall 点に届く予算 B と、合図から B + 余裕の保持 (設計 D-7) |
| 起草の疑義 3 (lock 待ちの後・commit の前・pool 待ちの写像の検査点に、§1.5 の 40 の対応 vector が無い) | 直した | peer の単体テストで固定する (設計 D-9) |
| 起草の疑義 4 (契約文の置き場「`limits.request_budget` か `LIMIT_EXCEEDED`」が未決) | 直した | 監督が `limits.execution_ms` と決めたが、RV-14 で pin の制約がわかり、設計 U-9 として両論で設計 §5 に残した (裁定は依頼者) |
| 起草の疑義 5 (「never driven」の書き換え対象に test_c24 と `security/CONTROL_MAPPING.md:1141` が漏れていた) | 直した | 設計 §6.5 に足した |
| 起草の疑義 6 (決定軸に出所が無い) | 直した | 依頼者指示 2026-10-02 (本 session の起動指示) と添えた |
| 起草の疑義 7 (U-1 の利点・欠点を drafter が枠から起こした) | 観察 | 監督が読み、そのままでよいとした |
| 起草の疑義 8 (ファイル名が `OC` §1.8 の 54 の形でない) | 直した | 依頼者指示によるファイル名で、§1.8 の 53 の転記はしない旨を設計 §0 に 1 行 |
| レビュー A-1・B-F2 (RV-1。検査点 (d) と pre_commit の前後が未規定。MitateDB の schema 操作は allow 行の後の cancel で error 行を書かない) | 直した | (d) を pre_commit の前と定め、error 行の追記の記述を transact と r2db に限った (設計 D-2・D-3・§1.4 #7) |
| レビュー A-1・B-F2 (RV-1 の派生: MitateDB の schema 操作の cancel 分岐に `commit_failed` が無い) | 起票 (R-N は作業機で採番) | audit_query の利用者が allow 行を見て commit 済みと誤読する。`OC` §1.15 の 77 の (b) に当たる。台帳は本 session で触れない |
| レビュー A-2・B-F3 (RV-2。§9.1 の「externally visible state change」が audit event と commit 段まで覆う) | 直した | 残さないものを列挙した。commit 段の文は M-4 まで【保留】、義務 (c) は commit 前に限った |
| レビュー B-F1 (RV-3。`max(1, …)` を外すと `statement_timeout = 0` で fail-open。閾値 `>` が揃わない) | 直した | `_timeout_ms` は残り < 1 ms で拒否し 0 を返さない。`check_deadline`・SQLite・in-memory の閾値を揃える |
| レビュー A-3・B-F7 (RV-4。単調性は放した後だけ。stall 到達・dry run・再送は成功の方向。C-24 を引いた句が誤り) | 直した | 設計 D-7 に限界を明記した。positive control、budget を外した再送 (CONFLICT か新規) で観測、費用の見積もり |
| レビュー A-4・B-F13 (RV-5。最後の文の後の検査が peer で分かれる: r2db は SELECT 後に 413、MitateDB は 200) | 直した | 設計 U-8 として両論で設計 §5 に残した (裁定は依頼者)。どちらも決定的、推奨 (a) 検査しない |
| レビュー A-5・B-F11 (RV-6。接続確立の経路が設計 D-5 の上限と U-6 から漏れる。MitateDB の connect は下限 2 s・失敗は 503) | 直した | D-5 を文の実行区間に限り、区間外を列挙した。U-6 に接続確立の行 |
| レビュー A-6 (RV-7。「文」が未定義: pool の維持の `SELECT 1`・`SET LOCAL`・COMMIT・別接続の audit) | 直した | 設計 D-2 と §9.1 に定義を置いた |
| レビュー A-7・B-F5 (RV-8。in-process 2 plug では文の数を観測できない。r2db の入口検査と (a) が冗長で変異が生き残る) | 直した | plug ごとの表。r2db の入口検査を pool 取得の後へ移し、検査点を 1 つにする |
| レビュー A-8・B-F14 (RV-9。§9 に [U-N] の差し替え印が無い。`limit_enforcement.execution_ms` が unavailable のときの扱い) | 直した | 差し替え印を足した。分岐しない根拠は `limits.finite_required` でなく C-05 V3 |
| レビュー A-9 (RV-10。残り 1 ms 以上・文の所要時間未満の帯は、設計 D-2 の後も負荷で 200 / 413) | 直した | D-2 の範囲を明記し、U-7 (c) と X-2 に結んだ |
| レビュー B-F4 (RV-11。dry run の execution_ms の拒否は real を予言しない。1.7.0 (3) と衝突) | 直した | 設計 D-1・§9.1 に 1 文 |
| レビュー B-F6 (RV-12。新 primitive の止める点が実装の点で定義されている。義務 (a) の証拠が無い) | 直した | 契約の点で定義した。(a) の証拠は CONTROL_MAPPING の claim と peer の単体テスト |
| レビュー B-F8 (RV-13。既存 2 primitive の docstring が「放した後に commit まで進む」と約束している) | 直した | port v1.22 で docstring を改訂する (確定文の経路) |
| レビュー B-F9 (RV-14。`limits` の新 key は `_PRE_1_8_0_LIMITS_KEYS` の pin が禁じる。idempotency.record への挿入は pin を壊す) | 直した | 置き場は設計 U-9 として両論で設計 §5 に残した (裁定は依頼者)。挿入案を削った。記録 (CONTRACT_HISTORY・CCR_DISPOSITION) を列挙した |
| レビュー B-F10 (RV-15。MitateDB の `SET LOCAL` と `_retime` の cancel が 503 に写る) | 直した | 設計 §1.4・§1.5・M-1・D-9 |
| レビュー B-F12 (RV-16。実装は「再送しても同じ」を知り得ず、`futility` を真に書けない) | 直した | 設計 U-3 の推奨を (a) に移した |
| レビュー B-F14 の残り (RV-17) | 直した | RV-9 に含めた |
| レビュー B-F15 (RV-18。`CONFORMANCE_ADAPTER_V1.md:36-44` の引き方、§6.6 の見出し、CONDITIONS_HISTORY への移送の規約が無い) | 直した | §2 の原則と §25 (:3461-3472) に直し、移送の規約を設計 §6.5 に足した |
| レビュー B の照合 (RV-19。照合済みの行の印と行番号のずれ) | 直した | 印を外し、行番号を直した (:1766、:1803-1804、:2656-2672、test_c24 :40-41) |
| 再確認 F1 (RC-1。MitateDB の schema 3 経路は pre_commit の後に idempotency を書き、設計 D-2 と両立しない) | 直した | 設計 D-9 に並べ替え (store → pre_commit → COMMIT)、§6.6 に順序を戻す変異 |
| 再確認 F2 (RC-2。U-8 (a) と D-2 (d) が衝突する) | 直した | U-8 (a) では (d) を置かない。(d) の行に [U-8 (b)] |
| 再確認 F3 (RC-3。(a) と `_timeout_ms` の拒否が二重で、単独の変異が生き残る) | 直した | (a) を `_timeout_ms` の拒否が兼ねる 1 点にした。in-process の脚注を直した |
| 再確認 F4 (RC-4。「文」が単一の transaction に限られ developer 接続が落ちる。`execute_count` が pool 維持の文を数える) | 直した | 定義をすべての接続にした。pool 維持の文を除く手段は port の設計で決める |
| 再確認 F5 (RC-5。dry run の例外が 1.7.0 (3) と `dry_run.decision` に届かない) | 直した | 設計 §9.2 に 1 文、§9.4 に相互参照の候補、U-4 (b) に 1 行 |
| 再確認 F6 (RC-6。「is not state in this sense」の先行詞が無く、`dry_run.external_effects` と衝突する) | 直した | 「audit evidence を律しない」の文に替えた |
| 再確認 F7 (RC-7。U-9 (b)(c) の pin の記述が現物と逆) | 直した | 監督の採否表 RV-14 の事実誤認を正した (`test_contract.py:111-115`・`:177`、`:2267-2268`) |
| 再確認 F8 (RC-8。§9.2 の義務文が U-9 (a) を前提にしている) | 直した | [U-9 (b)/(c)] の差し替え文を足した |
| 再確認 F9 (RC-9。M-4 の構成では COMMIT が cancel されない) | 直した | COMMIT 自体を遅くする構成 (deferred constraint trigger に `pg_sleep` 等) にした |
| 再確認 F10 (RC-10。COMMIT の bound を「scope 入口で設定」としていたが、lock 待ちの後に再設定される) | 直した | 「最後に設定した文の bound」にした (設計 D-2・D-5) |
| 再確認 F11 (RC-11。CONTROL_MAPPING の :659・:852・:870・:1023 の書き換えが漏れる。:1023 は現物と不一致) | 直した | 設計 §6.5 に足し、§6.1 に現物との差を添えた |
| 再確認 F12 (RC-12。THREAT_MODEL との関係が無い) | 直した | 設計 §7 に T-07・T-08・T-09・T-14 の段落 |
| 再確認 観察 (RC-13。B が照合した範囲の印が残っている) | 直した | 設計 §1.4 #4、§6.1・§6.5 の印を外した |

## 7. 作業機の追記 (2026-10-02)

- 取り込み: branch `claude/happy-einstein-f2oyqf` を worktree `.claude/worktrees/r42` (branch `r42`) に取り、main へ `--no-ff` で merge した (main `9674ab9`)。§3 の 1 が名指す `docs/work-orders/HANDOVER_20261001_R102_FABLE.md` は R-121 のチャットが移動済みだったので、最新 2 通から外れる `docs/work-orders/HANDOVER_20261001_R108_FABLE.md` を archive へ移した。
- 台帳 v1.151: R-42 を進行中にし、【追記 2026-10-02】を足した。新しい行は起票していない。
- §6 の「レビュー A-1・B-F2 (RV-1 の派生)」の裁定「起票 (R-N は作業機で採番)」を次の行で上書きする (`OC` §1.8 の 56。元の行は消さない)。

| 指摘 | 裁定 | 理由 |
|---|---|---|
| レビュー A-1・B-F2 (RV-1 の派生: MitateDB の schema 操作の cancel 分岐に `commit_failed` が無い) | 観察 (起票しない)。監督裁定 2026-10-02 | 作業機の照合で前提が現物と合わなかった。`MitateDB-api/src/mitatedb_api/cell.py:770-789` の `_error_row_once_fired` (R-115 WP-4b) が backend の 4 経路の呼び出しを包み、pre_commit の後の失敗で error 行を書く。`MitateDB-api/tests/test_application_audit.py` の 2 テストが `["allow", "error"]` を固定している。指摘は backend の分岐だけを読んでいた。設計 §1.4 #7・D-3・D-9・§7 の該当記述は次の版で訂正する |

### 7.1 照合と実測 (設計 v0.4)

- 設計を v0.4 にした (作業機の照合と実測 M-1〜M-8 の反映。一覧は設計 §11.3 の W-1〜W-24、実測の逐語は設計 §12)。§3 の 3 は済み。§3 の 2 のうち起票は行っていない (上の表)。
- 体制: 読解担当 1 起動 (設計が引く file:line の照合)、実装担当 2 起動 (計測専用の worktree に一時の未追跡テストを置き、計測後に削除。M-1・M-7 と M-8)、監督 (throwaway cluster での PostgreSQL 単体の計測 = M-2・M-4・M-6、`tools/perf_baseline.py` = M-3・M-5)、起草担当 1 起動 (v0.4)。製品コード・テスト・`spec/`・`conformance-tests/` は変えていない。完了ゲートは回していない (文書のみの変更セット)。
- 設計を変えた実測: `statement_timeout` は COMMIT を打ち切らない (M-4)。「COMMIT は文の bound で打ち切られる」を取り下げ、§4 の U-6 の「commit 段」の選択肢と未決の「commit 段の【保留】文」は無くなった。U-8 (a) の文も変わった (設計 §5 が正)。
- 修正前の挙動 (M-8): MitateDB の PostgreSQL 2 plug は、予算 50 ms を 60 ms 以上過ぎた要求を最後まで実行して commit する (20/20)。r2db の 3 plug と MitateDB の SQLite plug は、応答の code だけなら修正前から期待どおりになる。
- 測れなかったもの: M-8 の 100/100・vector (i)・完了ゲートの負荷の下の B (新 primitive と実装が要る。conformance の WP の完了条件にする)、配備の PostgreSQL の版 (M-2)、r2db の pool 待ち超過と MitateDB の新規接続・`PoolExhausted` の経路。
- 次の一手は §3 の 4 から (依頼者裁定 設計 U-1〜U-9 → 設計 §10 に逐語 → 設計レビュー 2 回目 → 作業指示書)。
- `tools/perf_baseline.py --concurrency 32` は既定の標本数では r2db の rate の bound に当たって止まる。`--n 15 --warmup 3` (`tools/PERF_BASELINE_README.md` の D-16 の形) を使う。

裁定 (`OC` §1.15 の 77。材料は読解担当の照合、実装担当 2 起動の報告、起草担当の疑義):

| 指摘 | 裁定 | 理由 |
|---|---|---|
| 読解: 設計の内容の食い違い 6 件・行番号ずれ 5 件 | 直した | 設計 v0.4 (§11.3 の W-6〜W-14)。一次資料 4 か所は監督が直読みで確かめた |
| 読解: `security/CONTROL_MAPPING.md:1023` の読み方が 2 通りある | 直した | 「pool・lock の待ちの超過」と「到達不能」の 2 句は現物と合うと読む。新規接続の確立が予算を超えた場合がどちらに入るかは設計 U-6 の材料にした |
| 計測 (M-8): 既存 primitive の stall 点が plug で違い、r2db の実装は port の docstring (「予約を取り終え」) と合わない | 直す (R-42 の port v1.22 の WP) | 新条件は「放した後に発行された文の数」を見るので、stall 点の定義と 4 実装を揃える必要がある。設計 D-7・§6.4。既存の C-27 と plan 検証のテストへの影響は port の設計で確かめる |
| 計測 (M-8): 応答の code だけでは 4 plug で新条件が修正前から緑になる | 直した | 設計 U-5 (c) と §6.6 に書いた (文の数の観測と peer の単体テストで固定する) |
| 計測 (M-8): budget なしの dry run の plan は budget 付きの実要求で `PRECONDITION_FAILED` になる | 直した | 設計 D-7・§6.3 ((iii) の dry run は実要求と同じ budget を付ける) |
| 計測 (M-8): B = 5 ms で r2db の PostgreSQL 2 plug の (ii) が 5/20 だけ拒否される (冷えた pool と推測) | 観察 | 原因は未検証。B は conformance の WP で完了ゲートの中の到達時間から決めるので、そこで現れる |
| 計測 (M-1): MitateDB の 503 と `SET LOCAL` 自体の cancel は再現しない (0 / 1695) | 直した | 設計 §1.5 を「経路は存在するが再現しなかった」に改めた。写像の修正 (設計 D-9) は残す |
| 計測 (M-1): 50 ms 待った後の文が 2〜3 倍遅い | 観察 | 計測の副作用で、設計の主張に効かない。原因は未検証 |
| 計測 (M-7): MitateDB の body の解析の終了から受理点までに約 2.5 ms ある | 観察 | 内訳は未調査。DB の利用者には所要時間としてしか見えず、台帳 R-80 (要求の中の往復) の範囲 |
| 起草の疑義 1 (残り 0.6 ms の実測は「残り 1 ms 以上」の帯の例にならない) | 直した | 「修正前の揺れの実測」として引いた |
| 起草の疑義 2 (`audit_dispatch.py` のコメントの開始行) | 直した | `:32` に直した |
| 起草の疑義 3〜5 (実測の置き場、枠に無い行番号の更新、`perf_baseline.py` の 1 回目の失敗) | 観察 | 置き場は設計 §12、行番号は現物どおり、失敗は標本数によるもので上に書いた |

