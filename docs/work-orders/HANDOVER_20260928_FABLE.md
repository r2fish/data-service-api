# 引き継ぎ — 2026-09-28 (R-101 是正: WP-3 (thread limiter を `create_app` に、既定 4) と WP-4 (real-server plug) を実装、完了ゲート PASS。Class D、規模 M × 2 WP)

本書は前書の全項を写さない。生きている事項だけを載せる。恒久の運用規律は `docs/work-orders/OPERATING_CONDITIONS.md` (以下 `OC`)。前書は `HANDOVER_20260926_FABLE5.md` (R-101 WP-1 / WP-2)。本書は `docs/work-orders/HANDOVER_20260928_FABLE.md` (チャットは 2026-09-27 開始・2026-09-28 終了)。以下 `RM` = `docs/design/ROADMAP_POST_PHASE7_V1.md`、作業指示書 = `docs/work-orders/WORK_ORDER_R101_SERIALIZATION_ATTRIBUTION_V1.md` (以下 `WO`)、設計メモ = `docs/design/PERF_SERIALIZATION_MEASUREMENT_V0_1.md`、`CM` = `security/CONTROL_MAPPING.md`。本書で D-N / M-N / 完了条件と書くときは `WO` のものを指す (`OC` §1.8 の 59)。

記録: `docs/archive/docs/work-orders/HANDOVER_20260926_FABLE4.md` (R-101 WP-1 の前チャット) (本変更セットで回転、`OC` §1.16 の 78)

## 1. 現在地

- **R-101 の是正 WP-3 と WP-4 を実装し、コードレビューを各 2 回 (opus) 経て全件閉じ、統合した木で完了ゲート PASS。** 受け入れ監査 (Class D) と再計測 (D-12 / D-16) は本書起草時点で未実施。
- worktree `.claude/worktrees/r101b` (branch `r101b`、WP-4) と `.claude/worktrees/r101b-wp3` (branch `r101b-wp3`、WP-3)。両方とも基点 `01d38c5` (`WO` v1.1 の WIP。その下は local main `2e746cc`) から切り、並行させた (`WO` §6.1 監督裁定 9)。`r101b-wp3` を `r101b` に merge した tree が `d7a7500`。main は本書起草時点で `2e746cc` のまま (本チャットで main を取り込んでいない)。
- 変更は WIP commit のみ (`01d38c5`〜`d7a7500` の 12 commit)。記録 (`RM` の版上げ・`WO` §6.2・設計メモ v0.3・本書) は未 commit。
- **Class D** (依頼者裁定 2026-09-28「D で進める」、`WO` §6.1 に逐語)。契約 1.11.0 不変。`_ISOMORPHIC_TARGETS` の件数 pin 167 → 169 (追加 `ThreadLimitMiddleware`・`DEFAULT_THREAD_LIMIT`・`_thread_limit_from_env`、削除 `_PerfThreadLimitWrapper`)。`CM` 3.5 → 3.6 (参照追随のみ。`WO` §6.1 監督裁定 11)。
- **完了ゲート** (監督、solo、使い捨てクラスタ、label `r101b`、tree `d7a7500`): `gate: 4342 passed, 2 subtests passed in 330.44s (0:05:30)`、judge=PASS、pg_database/pg_roles diff 0。`conformance-tests/COLLECTION_FLOOR` は木の中で 4314 のまま (4342 = 4314 + 28)。
- R-113 (multi-process worker、規模 L) は `RM` §8 に起票済み (WIP `01d38c5`)。`RM` の版は v1.128 のまま (版上げは記録の段)。
- push は停止中 (GitHub 課金上限)。ローカル commit のみ。
- 役割とモデル: implementer = sonnet (段ごとに別起動: WP-3 第 1 段・第 2 段・差し戻し 1〜2、WP-4 第 1 段・差し戻し 1〜4)、reviewer = opus (`claude-opus-5-5`、WP-3 / WP-4 で各 1 起動を再確認まで継続)、drafter = opus (`claude-opus-5-5`)、evidence-auditor = opus、explorer = sonnet ×4。

## 2. 本チャットで閉じたもの

| 件 | 結果 | 記録 |
|---|---|---|
| 是正の形 | 依頼者裁定 (2026-09-27、逐語「1〜4 すべて監督案どおりで進める」) | `WO` §6.1 |
| `WO` v1.1 | §7〜§12 (枠 v1.1、D-8〜D-16、WP-3・WP-4、再計測と閉止の判定)。起草の疑義 (1)〜(10) は監督裁定で本文に組み込み | `WO` §0・§7.3 |
| Class D の宣言 | 依頼者裁定 (2026-09-28、逐語「D で進める」) | `WO` §6.1 |
| R-113 の起票 | `RM` §8 (出発点は設計メモ v0.3 §6) | `RM` §8 R-113 |
| WP-3 第 1 段 | D-8 / D-9 / D-10 / D-13 (middleware、既定 4、env `R2DB_THREAD_LIMIT` / `MITATEDB_THREAD_LIMIT`、adapter は実効値を渡す)。limiter 40 を述べた既存コメントは CH-0544 / CH-0202 で書き換え | `WO` §6.1 訂正註 12、監督裁定 10・11 |
| WP-3 第 2 段 | D-11 (MitateDB http adapter の credential store に platform pool、`BoundedConnectionPool` の閉じる前の畳み込み)。接続ピーク: MitateDB-api/tests 13/300、conformance-tests 59/300 (枯渇は再現せず) | 完了条件 162 |
| WP-3 コードレビュー 1・2 | F1〜F11 + 観察 3 → 差し戻し 1。レビュー 2 は残り無し、新規 N1・N2 → 差し戻し 2 (M207 / M208) | `WO` §6.1 監督裁定 13、「裁定」節 |
| WP-3 の変異 (最終) | `mutate: 26 mutations, 26 as expected` (r2db) / `22 ... 22 as expected` (MitateDB) / `11 ... 11 as expected` (MitateDB 第 2 段)。各 restores verified | 実装報告 |
| WP-4 | `tools/perf_baseline.py --real-server <peer>`、`--client-processes` (既定 8)、`REALPERF` / `REALCPU` 行 | `WO` §9 |
| WP-4 コードレビュー 1・2 | F1〜F9 + P1 → 差し戻し 1。レビュー 2 は F4 の残り + 新規 N1〜N3 + 観察 2 → 差し戻し 2 (M211) | `WO` §6.1 監督裁定 12、「裁定」節 |
| WP-4 の変異・テスト (最終) | 32 件すべて `expect=red got=red`。`tools/tests` `pt: 642 passed in 78.39s (0:01:18)` (`r101b` 側、統合前) | 実装報告 |
| CI `tools-tests` job | install に httpx を追加 (検証は push 再開後) | `WO` §6.1 訂正註 13 |
| `CM` の行番号参照 | 両 `http.py` / `main.py` への 23 件を統合後に追随 (`412f906`) | `CM` 3.6 |
| 完了ゲート | §1 のとおり | 本書 §1 |

## 3. 次の一手

1. **受け入れ監査** (`ROLE_PROMPT_TEMPLATES.md` の 6、Class D、`WO` §11)。[監督: 監査結果]
2. **D-12 の再計測** (`WO` §10.2 の 2) → 設計メモ v0.3 §5。**成立** (設計メモ v0.3 §5: K=32 の `query` p50 が基準比 −41.4 / −10.7 / −80.4 / −51.1%、悪化 0、K=1 は r2db ±10% 内・MitateDB 悪化なし、`thread_limit=4`、MitateDB platform の per-call connect 0)
3. **D-16 の実測** (`WO` §10.2 の 3・4) → 設計メモ v0.3 §6。**成立** (設計メモ v0.3 §6。R-101 閉止。§4 の観察あり)
4. **記録** (`WO` §10.4・§10.5): `RM` §0.1.4 の 2 に【改訂】(R-14 の形)、R-101 行に【追記】、R-84 行に却下の理由 (`WO` §7.4 の (d))、R-113 行に【追記】(設計メモ v0.3 §6 の実測)、`RM` の版上げと版数ログの回転 (`OC` §1.16 の 78)、`WO` §6.2 に WP-3 / WP-4 の実施と受け入れ、`conformance-tests/COLLECTION_FLOOR` 4314 → 4342 (最終ゲート r101c の実測)、本書の commit と `HANDOVER_20260926_FABLE4.md` の回転。
5. 統合: main を取り込んだ木で完了ゲート (`WO` §11)、`tools/tests` を別に回す (`finalize.py --tools-tests`)。push 再開後に CI を 1 回 (訂正註 13 の httpx の検証を含む)。
6. worktree `r101b-wp3` の fold。
7. 前書から持ち越し: 監査 O-3 (`MitateDB-api/src/mitatedb_api/cell.py` の `prepared_stats` docstring) は R-102 の変更セットで直す。判定規則の次版への申し送り (`WO` §12 の (12-4))。

## 4. 依頼者判断待ち・未決

- **R-113 (multi-process worker、規模 L、設計レビューが着手条件) の着手時期。**
- **R-101 の閉止は D-16 の実測次第。** server は 1 process なので 8 倍は満たさない見込み (`WO` §10.1 の D-16)。**結果: D-16 成立、R-101 閉止** (real-server plug、server 1 process: r2db 4.63 / 4.58 倍、MitateDB 4.29 / 4.27 倍。設計メモ v0.3 §6)。ただし K=1 の分母は client の CPU (8.0 / 8.3 ms/req) が 74〜77% で server の直列化に対して甘い (socket plug の K=1 を分母にすると 10.0 / 10.1 倍) — 閉止をこの形で受理するか、分母を再改訂するかは依頼者判断 (§4)。

## 5. 本チャットで足した運用上の教訓

1. 裁定表の「採る」を implementer が「範囲外」と読んだ (WP-4 F5) — 裁定表は「直す / 採る」を同じ列で「実装する」と明示する。
2. stub だけのテストは実 API の認可 (must_rotate) を写せなかった — real-server 経路は監督の実 launcher での 1 run を監査照合に含める (今回は 403 で発覚し、差し戻し 3 で launcher に `control_credential_id` を足した)。
3. 2 worktree 並行 (WP-3 / WP-4) の重なりは README が auto-merge、WO §6.1 の両側追記だけが conflict (両側の追記を順に残して解いた)。
4. `security/CONTROL_MAPPING.md` の `file:line` 参照 (両 http.py 27 件ずつ、両 main.py 6 件ずつ) は content-anchored の script (`$SP/cm_repoint.py`) で追随した (23 件、消えた 2 件は再 anchor)。次の変更セットでも同じ script が使える (scratchpad なので repo には無い)。
5. `ps … | grep -c` は自分の grep や直前の python を拾う — 0 でなければ `ps -eo pid=,etime=,args=` で正体を見る。
6. `multiprocessing` の子は macOS で `fork` だと urllib の後に無応答になった — `forkserver` + 事前 warm で回避 (WP-4)。
7. API の session 上限で auditor が途中終了した — 再起動でよい (編集も journal も残らない)。

1. 裁定表の「採る」を implementer が「範囲外」と読んだ (WP-4 コードレビュー 1 の F5) → 裁定表は「直す / 採る (= 実装)」を同じ列で明示する。
2. 2 worktree の並行で、`tools/PERF_BASELINE_README.md` の重なりは auto-merge で解けた。conflict は `WO` §6.1 の両側の追記だけだった。
3. 完了ゲートの前に `tools/tests` を別に回す (root gate の対象外)。
4. `CM` の行番号参照は content-anchored の script (`cm_repoint.py`) で 23 件を追随させた。
5. process の残りを `ps` で数えると、数える側の grep 自身が 1 件に入る。
6. real-server plug の子 process は、開発機 (macOS) で forkserver が要った (fork では、先に urllib で HTTP を通した後の子が import 中に無応答になった)。

## 6. 裁定

全件を載せる (`OC` §1.15 の 77)。

| 指摘 | 裁定 | 理由 |
|---|---|---|
| WP-3 レビュー 1 F1 (中): r2db D-9 の AST pin が env と既定値を固定しない | 直した (M201 / M202) | pin に引数 3 個・`args[0]` = `env`・`args[2]` = `DEFAULT_THREAD_LIMIT` |
| WP-3 レビュー 1 F2 (中): `r2db-api/src/r2db_api/http.py` の CH-0544 の縮約で文意が壊れた | 直した | 同じ変更セットの訂正記録で既定 4 と env を述べる文に |
| WP-3 レビュー 1 F3 (中〜低): `MitateDB-api/src/mitatedb_api/http.py` の CH-0202 の文が D-13 と矛盾 | 直した | 受理は宣言 concurrency まで、limiter は同期区間の同時数だけ |
| WP-3 レビュー 1 F4 (低): 新 docstring の断言 (a)〜(d) | 直した | (a) 413、(b) 位置と「still」、(c) Starlette の文、(d) GC の主張を削除 |
| WP-3 レビュー 1 F5 (低): `pool.py` の来歴検査 2 行と「No other line changes.」 | 直した (`WO` 監督裁定 13) | 2 行は裁定 10 と同じ読みで受理、経緯の文を削除 |
| WP-3 レビュー 1 F6 (低): `acquire()` の死接続の畳み込みにテスト無し | 直した (M203 / M204) | 第 2 段の逸脱 (a) を採り、fake の単体テスト 2 本 |
| WP-3 レビュー 1 F7 (低): 8+1 が slot の保持を直接観測しない | 直した | limiter 4 と in-flight 8 を assert してから 9 本目、body の code と class |
| WP-3 レビュー 1 F8 (低): 報告と記録の不一致 (a)〜(d) | 直した | (a)(b) 実装担当、(c) 訂正註 12 の文言、(d) `CM` 3.6 の版行 |
| WP-3 レビュー 1 F9 (低): 古い記述・経緯語 | 直した | — |
| WP-3 レビュー 1 F10 (低): README の偽の理由 | 直した | 結論 (補正 0) は真、理由を「probe は `_read_pool` を回らない」に |
| WP-3 レビュー 1 F11 (不確実・低): `create_app(thread_limit=0)` で全要求 500 | 直した (M205 / M206) | 起動時の `ValueError` の方が要求ごとの 500 より良い |
| WP-3 レビュー 1 観察: 同じ loop で別 app が最初の要求を受けると limiter を上書き | 観察 | perf_baseline は isolated surface を使わず、env を残した pytest は README が禁じる。現行の経路で到達しない |
| WP-3 レビュー 1 観察: 既定 4 の下の `hold_in_flight` の bound | 観察 | C-05 の isolated surface は concurrency 3 (≤ 4)。conformance の意味の変化は無い |
| WP-3 レビュー 1 観察: socket plug での limiter の効果 | 観察 | WP-1 の wrapper と同じ効果 |
| WP-3 レビュー 2 N1 (低): F6 の 2 本目が稀に分岐 (3) を通らず緑 | 直した | `assert pool._idle.empty()` で M204 が決定的に赤 |
| WP-3 レビュー 2 N2 (低): F11 のテストが非 int を試さない | 直した (M207 / M208) | 非 int と bool を拒否 |
| WP-4 レビュー 1 F1 (中〜高): `client_processes=` が算術値 | 直した | 観測した子の pid の数。RV1 を 132・133・168 に |
| WP-4 レビュー 1 F2 (中): 141 の既知 CPU の stub が未実装、warmup の除外が未観測 | 直した (M209) | busy loop の stub、±20% |
| WP-4 レビュー 1 F3 (低〜中): 144 の assert が空振り | 直した | `_load_composition_root_class` を spy |
| WP-4 レビュー 1 F4 (低): 出所の誤り・文書名の無い ID・経緯語 | 直した | 差し戻し 1 で一部、残りは差し戻し 2 |
| WP-4 レビュー 1 F5 (不確実): group の開始時刻 | 直した (M210) | 採る = 各子が barrier から戻った直後の `time_ns` の最小 |
| WP-4 レビュー 1 F6 (低): `requests=` が算術値 | 直した | 応答数。n×K に満たない run は失敗 |
| WP-4 レビュー 1 F7 (低): 例外が包まれない | 直した | URLError / OSError / JSONDecodeError と registry の未解決 |
| WP-4 レビュー 1 F8 (低): 要求数の上限の注意 | 直した | README に `requests_per_minute` との関係 |
| WP-4 レビュー 1 F9 (不確実): `_warm_forkserver` の順序の主張 | 直した | 事実だけの文に |
| WP-4 レビュー 1 P1: 指示書外 (a)〜(d) を実装後に報告 | 受理 (`WO` 監督裁定 12) | 中身は妥当。以後は実装前に報告 (`OC` §1.5 の 37) |
| WP-4 レビュー 1 範囲外の観察: CI `tools-tests` job に httpx が無い | 直した (`WO` 訂正註 13) | push 再開後の collection の赤を防ぐ |
| WP-4 レビュー 2 F4 の残り: 文書名の無い `D-15:`・「completion condition N」 | 直した | 見出しの文書名を受けて「The work order's D-15」 |
| WP-4 レビュー 2 N1 (低): 道具の docstring に経緯語 | 直した | — |
| WP-4 レビュー 2 N2 (低): 144 のテストが `main()` の例外を飲む | 直した | assert を無条件に |
| WP-4 レビュー 2 N3 (低): README の「well under the budget」 | 直した | 580 / 600、`--n 16` で超える、と事実で |
| WP-4 レビュー 2 観察: `--n 0` で `client_processes` が `None` | 直した (M211) | `--real-server` は `--n` ≥ 1 |
| WP-4 レビュー 2 観察: 141 のテストは子の worker を差し替え、本物の worker の CPU の窓はコードの読みだけ | 観察 | F2 の実現法 (監督裁定 12) の帰結 |
| WP-4 レビュー 2 観察: F7 の残る経路 (存在しない module の ImportError、`LauncherStartupError`) は traceback | 観察 | start の失敗は launcher 自身が stop 済みで残骸は無い (レビュー 2 の所見) |
| 起草の疑義 (1): D-11 の対象 (audit sink は production でも pool 無し) | 直した (`WO` §7 冒頭、D-11) | 枠の誤りの訂正 |
| 起草の疑義 (2): `BoundedConnectionPool` の閉じる前の畳み込み | 直した (D-11) | r2db `_RolePool` と同じ形 |
| 起草の疑義 (3): 最外側 wrapper か middleware か | 直した (D-8) | pure-ASGI middleware、返り値の形は不変 |
| 起草の疑義 (4): 宣言 concurrency の同時到達を試す既存テスト | 直した (D-13) | `thread_limit=None` を明示 |
| 起草の疑義 (5): limiter 40 を述べる既存コメント | 直した (D-13) | 事実に合わせ、来歴を登録 |
| 起草の疑義 (6): real-server の credential の使い分け | 直した (D-15) | control → developer で用意、`query` は runtime、先頭で 200 と行数 > 0 |
| 起草の疑義 (7): env の parse | 直した (D-9) | 未設定・空 → 4、他は正整数のみ |
| 起草の疑義 (8): `DSA_PERF_THREAD_LIMIT` と accessor | 直した (D-10) | 無効 → 既定 4、accessor は実効値 |
| 起草の疑義 (9): 子の数・余り・行の位置・8 倍の成立 | 直した (D-15・D-16) | — |
| 起草の疑義 (10): R-113 の起票の時期 | 直した (`RM` §8) | 本変更セットで起票、版上げは記録の段 |
| 起草の訂正: limit 4 の MitateDB-http の比 15.4 | 直した (`WO` §7 冒頭) | 設計メモ §3 の 4 の 15.2 |
| WP-3 第 1 段 疑義 (1) / 逸脱 (a): r2db D-9 を AST pin + 単体テストの合成で | 直した (`WO` 訂正註 12) | 既存ファイルの方針 (実 platform DB を要する `build_app` を実行しない) |
| WP-3 第 1 段 疑義 (2) / 逸脱 (b): MitateDB の `LIMIT_EXCEEDED` (concurrency) は 413、r2db は 429 | 観察 (`WO` §6.1 の観察) | 契約は HTTP status を束縛しない (429 / 413 の出現 0 件) |
| WP-3 第 1 段 逸脱 (c): r2db `http.py` の limiter 40 の塊は :383-453 の 1 塊 | 受理 (`WO` 監督裁定 10) | 塊全体を CH-0544 として登録し旧 40 の 2 文だけ削除 |
| WP-3 第 1 段 逸脱 (d): 両 adapter の不要になった import の削除 | 受理 (`WO` 裁定 14) | wrapper の削除の直接の帰結 (§8.1 に名指し無し) |
| WP-3 第 1 段 逸脱 (e): `tools/tests` を未実行 | 受理 (`WO` 裁定 14) | 差し戻し 1 の報告で `pt: 613 passed` |
| WP-3 第 2 段 逸脱 (a) / 疑義 (2): `acquire()` の死接続にも畳み込み | 直した (F6 で採った) | §8.1 の「ほかに pool が接続を閉じる経路」 |
| WP-3 第 2 段 疑義 (1) / 逸脱 (d): README の Probe 節の MitateDB の記述 | 直した (F10) | — |
| WP-3 第 2 段 逸脱 (b): 完了条件 115・162 は監査照合 | 受理 (`WO` 裁定 14) | §8.3 の対応表どおり変異を持たない |
| WP-3 第 2 段 逸脱 (c): `test_r78_pool_wait_stats.py` の見出しコメントの書き換え | 受理 (`WO` 裁定 14) | D-11 の実施に合わせた追随 |
| WP-3 第 2 段 逸脱 (e): 完了条件 115 の観測は一回限りの script | 受理 (`WO` 裁定 14) | 指示書は「1 行で観測し、出力を報告に残す」 |
| WP-4 第 1 報告 逸脱 1〜4: `application_id` を capabilities から、forkserver、timeout、下限検証 | 受理 (`WO` 監督裁定 12 の P1) | — |
| WP-4 第 1 報告 逸脱 5: 裸の「R-101 WP-4」を新規コメントから除いた | 受理 (`WO` 裁定 14) | §9.1 の書き方より起動プロンプトの逐語を優先 |
| WP-4 第 1 報告 疑義 1: 先頭の確認 (200・行数 > 0) は K に依らず 1 本 | 受理 (`WO` 裁定 14) | レビュー 1 (vi) は runtime bearer で 200 かつ items 非空を確認 |
| WP-4 第 1 報告 疑義 2: WP-3 未実装の木で WP-4 を完了 | 受理 (`WO` 裁定 14) | `d7a7500` で統合済み |
| WP-4 差し戻し 1 指示書外 1〜4・疑義 1・2 | 受理 (`WO` 監督裁定 12) | — |
| WP-4 差し戻し 2 逸脱 1: 置換は新規区間の 18 箇所、既存行の「completion condition」は対象外 | 受理 (`WO` 裁定 14) | 既存行は WP-4 の追加ではない |
| D-16 の 1 回目 (tree d7a7500): `POST /control/v1/credentials -> 403` (bootstrap の control credential が `must_rotate`) | 直した (差し戻し 3: launcher の `control_credential_id` + perf tool の自己 rotate、`WO` 訂正註 14 / 裁定 15) | stub は実 API の認可を写せなかった |
| WP-4 差し戻し 3 の疑義 1〜3 (launcher に触る必要、bearer 分割は契約の MUST NOT、実装せず報告) | 裁定 15 = (a) launcher を触ってよいパスに足す | OC §1.5 の 37 のとおりの停止 |
| WP-4 レビュー 3 N1 (M212 の docstring の赤の理由)・N2 (完了条件の対応付け) | 直した (差し戻し 4、`WO` 裁定 16) | docstring のみ |
| WP-4 レビュー 3 観察: run 後の launcher の `control_bearer` は無効な旧 secret のまま / launcher は C-26 と共有 | 観察 (`WO` 裁定 16) | perf tool は launcher を 1 run で捨てる。C-26 は完了ゲートで緑 |
| D-16 の分母 (K=1) が client の CPU に支配される (設計メモ v0.3 §6.3) | 観察 → §4 で依頼者判断 | 規則は計測前に固定したので判定は動かさない |
