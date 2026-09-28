# 引き継ぎ — 2026-09-28 (R-113 multi-process worker に着手: 設計 v0.5 と依頼者裁定、台帳 v1.130、作業指示書 v1.0、WP-1 (conformance) 完了、WP-2 (r2db) 実装中。Class D、契約 1.11.0 不変、規模 L)

本書は前書の全項を写さない。生きている事項だけを載せる。恒久の運用規律は `docs/work-orders/OPERATING_CONDITIONS.md` (以下 `OC`)。前書は `HANDOVER_20260928_FABLE.md` (R-101 是正 WP-3 / WP-4)。本書は `docs/work-orders/HANDOVER_20260928_FABLE2.md`。以下 `RM` = `docs/design/ROADMAP_POST_PHASE7_V1.md`、設計 = `docs/design/MULTI_PROCESS_WORKER_V0_1.md`、`WO` = `docs/work-orders/WORK_ORDER_R113_MULTI_PROCESS_WORKER_V1.md` (worktree `r113` の WIP にだけ在る。main には未統合)、`CM` = `security/CONTROL_MAPPING.md`。本書で D-N / Q-N と書くときは設計のもの、WP-N / M-N / 完了条件と書くときは `WO` のものを指す (`OC` §1.8 の 59)。裁定の番号は「設計 裁定 N」(設計 §10、1〜42) と「`WO` 裁定 N」(`WO` §6.1、1〜21) で書き分ける。

記録: `docs/archive/docs/work-orders/HANDOVER_20260926_FABLE5.md` (R-101 WP-1 / WP-2 の後の引き継ぎ) (本変更セットで回転、`OC` §1.16 の 78)

## 1. 現在地

- **main は `e3b0f5a`** (設計 v0.5 + `RM` v1.130 + R-114 の起票。docs-only)。
- **worktree `r113`** (branch `r113`) は WIP `74d90f3` = `WO` v1.0 (§6.1 `WO` 裁定 1〜21、§6.2 WP-1 の記録) + WP-1 の merge (`060a5d8`、worktree `r113-wp1` の `8a0327d`)。
- **WP-1 (conformance) は完了、レビュー全件閉止。** 中身: 新条件 (`conformance-tests/test_c32_shared_limits.py`。番号は `r113` の木の `conformance-tests/CONDITIONS.md` で採番済み)、C-26 (4) の 3 通り・(5) の workers ≥ 2、launcher の workers / pgid / mkdtemp の slot directory / preflight / pid 付き access log / `LOCK TABLE` の保持、宣言分岐 + launcher の配線 accessor 2 本。
- **WP-2 (r2db 実装) は実装中。** worktree `r113-wp2` (branch `r113-wp2`、基点 `74d90f3`) で実装担当 (sonnet) が作業中。本書起草時点で src 10 ファイル・tests 7 ファイル・migration 0015・`r2db-api/src/r2db_api/concurrency_slots.py` の差分が未 commit。変異 run は進行中 (M62 付近 / 54 件)。
- **WP-2 の実装報告は未着。** 報告書の予定の置き場は本チャットの scratchpad (`r113-wp2-report-1.md`)。新チャットは旧 scratchpad を読めないので、監督が差分と報告を `.claude/worktrees/r113/.r113-handoff/` に写す (未追跡、commit しない)。
- **WP-2 の途中経過 (監督の観察)**: 変異 M52 (`LOCK_NB` を外す) の下で `test_full_slots_refuse_immediately_never_blocking` が時間の上限無しに 1 時間 42 分 hang した。監督が pytest の子だけを SIGTERM し、実装担当に「取得を別 thread + `join(timeout)` で上限付きにして M52 を回し直す」と指示済み (未完)。
- **Class D**、契約 **1.11.0 不変**、規模 **L**。
- push は停止中 (GitHub 課金上限)。ローカル commit のみ。
- 役割とモデル: drafter = opus (`claude-opus-5-5`)、reviewer = opus、implementer = sonnet、explorer = sonnet ×3。

## 2. 本チャットで閉じたもの

| 件 | 結果 | 記録 |
|---|---|---|
| 設計 v0.1 → v0.5 | 設計レビュー 1 回 + 再確認 3 回 (旧 13 / 新 8 / 新 A〜F)、設計 裁定 1〜42 | 設計 §0・§10 |
| 設計の芯 | 静的分割案を撤回 → `concurrency` は host 内共有の `fcntl.flock` slot、`requests_per_minute` は PG の 1 credential 1 行 int[61] 秒 ring (基点秒は単調)、写像は「配線 かつ ceiling ≤ workers」で `enforced`、preflight は one-shot、契約 1.12.0 は不要 | 設計 裁定 10・15・26・27・30・34・37 |
| 依頼者裁定 | 逐語「Q-1 は (A')、Q-3 は 1、Q-4 は (B)、Q-5 は行う で進めます。」 | 設計 §5 |
| `RM` v1.130 | R-113 行に追記、R-52 行に追記、R-114 の起票 (契約 :925 の audit 窓 "fixed" と実装の sliding の食い違い、規模 S、監督案 (i)) | `RM` §8 |
| `WO` v1.0 | Change Set Manifest、`WO` 裁定 1〜21 | `WO` §6.1 |
| WP-1 | 上の §1。コードレビュー 1 回 + 再確認 2 回、全件閉止 | `WO` §6.2 |

## 3. 次の一手

1. **WP-2 の完了。** 新チャットは実装担当を新規起動し、`r113-wp2` の未 commit 差分と `.claude/worktrees/r113/.r113-handoff/` の報告から続ける。残り: M52 のテストに時間の上限、変異 54 件、同型性テストの赤は完了条件 78 の監査照合、provenance は `--base 74d90f3`。→ コードレビュー (opus、`docs/work-orders/ROLE_PROMPT_TEMPLATES.md` の 5) → `r113` に merge。
2. **WP-3 (MitateDB)。** 同型移植。`_ISOMORPHIC_TARGETS` の登録と件数 pin は WP-3 だけが触る。control の preflight entry。
3. **WP-4 (計測)。** `tools/perf_baseline.py --real-server <peer> --workers N`。rate 文の小実験 (0.2 ms/文)、N=1 / N=4、K=1 / K=32 × 2 run、pid 付き access log、D-16 の逐語 = 設計 §7.1、既定 concurrency 32。R-101 の閉止の判定は Q-5 のとおり本変更セットの結果で行う。
4. **WP-5 (配備)。** systemd の `ExecStartPre` の preflight・`RuntimeDirectory` 0700・env 必須・`--workers ${R2DB_WORKERS}` の静的 pin、Dockerfile CMD の `set -e`、runbook (1 host・max-instances=1・`--cpu ≥ workers`・SIGHUP 禁止・int[61] の開示)。
5. **WP-6 (記録)。** `RM` の R-113 / R-101 / R-18 行、`CM` 3.7 (Class D)、`conformance-tests/COLLECTION_FLOOR`、`tools/PERF_BASELINE_README.md`、引き継ぎ書。
6. 受け入れ監査 1 回 (evidence-auditor、`docs/work-orders/ROLE_PROMPT_TEMPLATES.md` の 6) → 完了ゲート (監督。`gate.py -C` を必ず渡す、`tools/tests` は別に回す) → finalize (Class D、契約ファイル不変)。
7. **WP-1 だけを main に統合しない。** C-05 の int[61] の文は WP-2 / WP-3 の後に現物と一致する。

## 4. 依頼者判断待ち・未決

- **R-114 の直し方。** (i) 契約の文言を「窓の形は定めない」に改める (版上げ)、(ii) 実装を fixed window に改める。監督案 (i)。
- **R-101 の閉止は WP-4 の D-16 次第。**
- R-52 (rollout の重なり) は R-113 の範囲外。

## 5. 本チャットで足した運用上の教訓

1. 変異で「blocking になる」ことを検出するテストは時間の上限を持たせる (M52 の hang)。hang したときは監督が pytest の子だけを SIGTERM すれば、`mutate.py` は赤として続行する。
2. 発注プロンプトに `export SP` を必ず書く (pt の log が `$SP` の外に出た)。
3. レビューの「再確認」は同じ reviewer を SendMessage で続ける (context を保てて安い)。本チャットは設計 3 回・コード 2 回。
4. 静的分割のように宣言値に届かない案は、AI client の前提 (宣言を読んで計画する) に反する製品欠陥として設計レビューで落ちた。利用率を落とす案は最初から候補に入れない。
5. uvicorn の `--workers` の supervisor は子の起動失敗を置き換え続け、親は exit 0 で終わる。fail-fast は親側の preflight one-shot で担う。
6. 契約の文言 (`spec/data-service-api.v1.json`:303・:905) は「per-process memory」を名指ししている。状態の置き場の設計は契約の文言と突き合わせてから決める。
7. Sonnet の session limit で implementer が止まっても、SendMessage で再開すれば続けられる (差分は無傷)。
8. 発注プロンプトの完了条件の列挙が `WO` と食い違うと実装担当が迷う (`WO` 裁定 17)。番号は `WO` を正とし、プロンプトには写さない。

## 6. 裁定

全件を載せる (`OC` §1.15 の 77)。

| 指摘 | 裁定 | 理由 |
|---|---|---|
| 設計レビュー 1 の 1 (高): `--workers N` の下で F-15 の fail-fast が起動失敗にならない | 直した (設計 裁定 11、手段は裁定 26 で改めた) | supervisor は子を置き換え続け親は 0 で終わる。親側の preflight one-shot で止める |
| 設計レビュー 1 の 2 (高): 静的分割では N=4 の計測が既定 32 で完走しない | 直した (設計 裁定 10・16・17) | 静的分割を撤回し host 共有の flock slot に。接続予算は thread limit で数える |
| 設計レビュー 1 の 3 (高): C-26 (4) と新条件が peer の設計選択を共通 conformance の要求にする | 直した (設計 裁定 12) | 宣言で分岐し、`enforced` を宣言した peer にだけ新条件を課す |
| 設計レビュー 1 の 4 (a)(b) (高): 1.12.0 の文言案の穴 | 直した (設計 裁定 13) | 分割の撤回で消えた。契約 1.11.0 不変 |
| 設計レビュー 1 の 4 (c): 契約 :925 の audit 窓 "fixed" と実装の sliding | 起票 R-114 | 本件より前からの食い違い。本件では直さない |
| 設計レビュー 1 の 5 (中高): 新条件 (a) の保持の手段 | 直した (設計 裁定 14・23) | launcher の特権接続の `LOCK TABLE`。本番に stall フックを足さない |
| 設計レビュー 1 の 6 (中): fixed window は分の境目で「ちょうど L」を赤にする | 直した (設計 裁定 15) | 現行の sliding を PG の行に保つ (Q-2 は監督裁定で閉じた) |
| 設計レビュー 1 の 7 (中): rate 行の形・接続・時計が未決 | 直した (設計 裁定 15) | 既存 api role pool の autocommit 1 文、DB の時計、fail-closed |
| 設計レビュー 1 の 8 (中): PG を持たない in-process plug の扱い | 直した (設計 裁定 18) | 共有の仕組みが配線されたときだけ `enforced` |
| 設計レビュー 1 の 9 (中): launcher が supervisor の子を追跡しない | 直した (設計 裁定 19) | process group で起動し killpg、孤児掃除の対象に |
| 設計レビュー 1 の 10 (低中): Q-4 (C) と autoscaling で宣言値が平常時に届かない | 直した (設計 裁定 20) | 監督案を (B) に改めた |
| 設計レビュー 1 の 11 (低): 実 process 数と宣言がずれる入口 | 直した (設計 裁定 11) | `--workers` は常に明示し env に必須 |
| 設計レビュー 1 の 12 (不確実・低): supervisor の SIGKILL で audit buffer が失われる | 直した (設計 裁定 21) | D-2 の表に開示 |
| 設計レビュー 1 の 13 (低): 出所のずれと却下理由の不足 | 直した (設計 裁定 21) | 行番号の訂正と §4 の却下理由 |
| 設計レビュー 1 クラスの引き上げ | 直した (設計 裁定 22) | Class D |
| 設計再確認 1b 新 1 (高): preflight に `verify-declarations` を使うと provision の DSN が data plane に入る | 直した (設計 裁定 26) | service 自身の env と DSN で `build_app()` を 1 回走らせる one-shot |
| 設計再確認 1b 新 2 (高): `enforced` は 1 host に依るが宣言に情報が無い | 直した (設計 裁定 27) | 「配線 かつ ceiling ≤ workers」のときだけ `enforced` |
| 設計再確認 1b 新 3 (中高): slot directory の同一性・権限・errno | 直した (設計 裁定 28・36) | `O_NOFOLLOW`・0600、塞がりの errno を限定し他は fail-closed、専用 `selfcheck` |
| 設計再確認 1b 新 4 (中): thread 間の排他と拒否経路の syscall 数 | 直した (設計 裁定 29) | fd は要求ごとに open・close、process 内で共有しない |
| 設計再確認 1b 新 5 (不確実・中): rate 行の 1 文が全 process をまたぐ直列区間 | 直した (設計 裁定 30・34) | 固定長の int[61]。費用は WP-4 の小実験で確かめる |
| 設計再確認 1b 新 6 (低中): 計測時 64 の理由が現物と違う | 直した (設計 裁定 31) | 計測は本番既定の 32 |
| 設計再確認 1b 新 7 (低): 新条件 (b) の分散の観測 | 直した (設計 裁定 32) | 200 がちょうど L、rpm の拒否 L、pid 2 種以上 |
| 設計再確認 1b 新 8 (低): 細部 | 直した (設計 裁定 33) | 孤児掃除は pgid で記録ほか |
| 設計再確認 1b 新 8 のうち Cloud Run の一時的な max-instances 超過 | 観察 | 推測 (現物未確認)。runbook に「推測」と明記して開示 |
| 設計再確認 1c 新 A (高): 基点の秒が戻り L を超えて通す | 直した (設計 裁定 37) | 基点の秒を単調に進める |
| 設計再確認 1c 新 B (中): 本文に「60」が残る | 直した (設計 裁定 38) | 61 に揃えた |
| 設計再確認 1c 新 C (低中): workers の env と `--workers` の引数がずれる入口 | 直した (設計 裁定 39) | env の同じ変数からだけ渡し、静的テストで pin (WP-5) |
| 設計再確認 1c 新 D (低中): SIGHUP の N+1 で接続予算が破れる | 直した (設計 裁定 40) | runbook で SIGHUP を禁じる |
| 設計再確認 1c 新 E (低): preflight entry の細部 | 直した (設計 裁定 41) | module の `app` を使い回す、CMD は `set -e` |
| 設計再確認 1c 新 F (低): int[61] は境目で最大 1 秒分多めに数える | 観察 (設計 裁定 42 で開示) | L を超えて通すことは無い。C-05 と両 runbook に開示 |
| WP-1 レビュー 1 F1 (高): 新条件 (b) の窓が (a) の要求で汚れる | 直した | (a)(b) それぞれ専用の runtime credential |
| WP-1 レビュー 1 F2 (高): MitateDB は LIMIT_EXCEEDED を 413 で返す | 直した (`WO` 裁定 18) | envelope の `code` と `details.limit_class` で数える |
| WP-1 レビュー 1 F3 (高): 完了条件 4 のテストが ceiling 1 / workers 2 | 直した | ceiling 2 / workers 2 で起動 |
| WP-1 レビュー 1 F4 (中): r2db control の preflight が空振り | 直した (`WO` 裁定 19 (i)) | 観測テストを足し、構築は WP-2 の完了条件に |
| WP-1 レビュー 1 F5 (中): C-26 の文が偽、C-05 に int[61] の開示が無い | 直した (差し戻し 4 で完了) | 旧文を history へ、C-05 に 1 host と int[61] の文 |
| WP-1 レビュー 1 F6 (中): 新条件の行に偽の記述と一時的な実測値 | 直した | 誤帰属と一時値を除いた |
| WP-1 レビュー 1 F7 (中): 完了条件 18 の pid が (b) の送信に限られない | 直した | 送信前の log 位置で区切る |
| WP-1 レビュー 1 F8 (中低): `application_name` の文字列の種類を数える | 直した (regex は 1b N1 で再修正) | pid を parse して distinct を数える |
| WP-1 レビュー 1 F9 (不確実・中): F-15 / F-16 の起動経路に workers と slot の env が無い | 直した (`WO` 裁定 19 (iii)) | WP-2 の必須化で赤にしない |
| WP-1 レビュー 1 F10 (中低): preflight が走ったことを見ていない、M5 | 直した | preflight の argv と returncode を見る |
| WP-1 レビュー 1 F11 (中低): 「子 2 本」を確かめていない | 直した | uvicorn の worker をちょうど 2 本 |
| WP-1 レビュー 1 F12 (低): 経緯語と時限付きの断言 | 直した | — |
| WP-1 レビュー 1 F13 (低): `PermissionError` の理由のコメントが実測と違う | 直した (1c で閉止) | 実際の呼び出しに合わせた |
| WP-1 レビュー 1 F14 (不確実・低): leader が死んだ group を `sweep_orphans` が掃除しない | 既知の穴 (§1.12 の 71、`WO` 裁定 21) | worker の cmdline に識別子が無い。docstring の `Known gaps` に置き、効かない枝を削除 |
| WP-1 レビュー 1 F15 (低): reap 済み pgid への SIGKILL、macOS の EPERM | 直した | 3 箇所で握る |
| WP-1 レビュー 1 F16 (低): `LOCK TABLE` の失敗が捨てられる | 直した | 例外を `error` に積む |
| WP-1 レビュー 1 F17 (不確実・低): restart で slot directory を作り直さない | 直した | restart でも mkdtemp |
| WP-1 レビュー 1 F18 (不確実): ceiling 2 で `enforced` を全 peer に課す | 直した (`WO` 裁定 20) | 宣言分岐と launcher の配線 accessor の cross-check |
| WP-1 再確認 1b N1 (高): 完了条件 15 の regex が `WO` の `application_name` を拒む | 直した (`WO` 裁定 21) | launcher の既存 `.name` を peer token に |
| WP-1 再確認 1b N2 (中): C-26 (1) の起動順序の記述が偽 | 直した | 現物の順序に合わせた |
| WP-1 再確認 1b N3 (中低): C-26 (6) の「nor any of its own workers」が未観測 | 直した (`WO` 裁定 21) | 残骸テストを ceiling 2 / workers 2 に広げた |
| WP-1 再確認 1b N4 (低): pt の log が `$SP` の外 | 観察 (`WO` 裁定 21) | 発注プロンプトに `export SP` を必ず書く (§5 の 2) |
| WP-1 再確認 1c 観察: C-05 の int[61] の文は WP-2 / WP-3 の後に現物と一致 | 観察 | WP-1 だけを main に統合しない (§3 の 7) |
| WP-1 再確認 1c 観察: C-26 の行は control の preflight fail-fast に触れない | 観察 | 偽ではない |
| WP-1 再確認 1c 観察: C-26 の cell の残り 21 字 | 観察 | 次の訂正は参照を history へ送る |
| WP-1 実装 逸脱 1: preflight を両 plane で常時実行 | 受理 (`WO` 裁定 9) | `WO` 裁定 4 の帰結 |
| WP-1 実装 逸脱 2: pid 付き access log を `UVICORN_LOG_CONFIG` で注入 | 受理 (`WO` 裁定 10) | 起動関数の引数を増やさない |
| WP-1 実装 逸脱 3: developer credential の発行を `_ensure_provisioned` に | 受理 (`WO` 裁定 11) | 触ってよいパスの範囲内 |
| WP-1 実装 逸脱 4: preflight は現行の module-level `app` に依存 | 受理 (`WO` 裁定 12) | WP-2 / WP-3 の完了条件に entry の使い回しを足した |
| WP-1 実装 逸脱 5: lock 保持の接続の `application_name` | 受理 (`WO` 裁定 13) | data plane の名前と衝突させない |
| WP-1 実装 逸脱 6: `CONDITIONS.md` の追記方式 | 受理 (`WO` 裁定 14) | 既存の文が偽にならない限り |
| WP-1 実装 逸脱 7: 両 peer の新 method を同名同引数に | 受理 (`WO` 裁定 15) | 対称性 |
| WP-1 実装 逸脱 8: `sweep_orphans` の `PermissionError` の許容 | 受理 (`WO` 裁定 16) | `os.getpgid(pid) == pid` の場合に限る |
| WP-1 発注プロンプトの赤リスト「5・13」 | 直した (`WO` 裁定 17) | `WO` §3.2 の本文が正 (§5 の 8) |
| WP-1 レビュー 1 の観察 (指摘外) 6 点: 公開値 0 / launcher の対称性 (developer credential の発行経路だけ peer 固有) / 保持の上限は `SET LOCAL statement_timeout` の残り予算に依る / data の preflight は module-level の `build_app()` で本物 / 完了条件 19 は部分実行では示せず完了ゲートで示す / M3 は `pid + 1` を代用 | 観察 (起票しない) | いずれも欠陥ではない。完了条件 19 と保持の上限は完了ゲートと WP-2 の完了条件で確かめる |
| WP-1 レビュー 1b の F9 の残り (uvicorn の argv に `--workers` が無い経路 = F-15 / F-16 の単独起動) | 観察 (起票しない) | 配備の起動形は WP-5 の静的 pin (`WO` 裁定 39 相当) が担う。launcher の単独起動は 1 process |
| WP-1 レビュー 1b §5: `CONDITIONS.md` の cell 長 (C-26 2979 / C-05 2966 / 新条件の行 992 の 3000 に対する余裕) | 観察 (起票しない) | 次の訂正 (WP-6) で Design の参照を `CONDITIONS_HISTORY.md` へ送る。検査器の穴ではない |
| WP-1 レビュー 1c の観察: C-26 の行が control の preflight fail-fast テストに触れない / `(history).**Disclosed` の空白 / 新規コメントの「review finding N」参照 (既存慣行と同形) | 観察 (起票しない) | 偽ではない。WP-6 で C-26 の行を直すときに control の preflight を 1 句足す (残り 21 字なので参照の移動と同時に) |
