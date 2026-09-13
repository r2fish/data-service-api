# 引き継ぎ — 2026-09-10 (第17次。フェーズ10 — 配備面の証拠。契約は 1.7.0 → **1.8.0**)

- 引き継ぎ元: Fable (監督)。実装: Sonnet subagent、レビュー/起草/監査: Opus subagent (各 WP で独立レビュー + 変異注入を継続)
- 引き継ぎ先: 次セッションの Fable (同体制継続)
- 前提: **第16次 `HANDOVER_20260908_FABLE.md` (フェーズ9) と、そのさらに前の引き継ぎの約束事は全て継続**する。**現在地のみ本書が上書きする**
- **運用条件 (役割分担・コミット規約・ゲートの実行法・開発機の環境条件・CI の条件) の正本は `docs/work-orders/OPERATING_CONDITIONS.md` である。本書はフェーズ固有の差分だけを持つ。**
- 本書は**フェーズ10 (配備面の証拠。契約 1.8.0「資源制限の適用単位」) の WP-0〜WP-9 を実施したセッションの記録**である。**契約は 1.6.0 → 1.7.0 (フェーズ9) に続いて 1.7.0 → 1.8.0 へ上がった** (3 複製の sha256 で示す)。**新しい Security Invariant は足していない。** **実機適用は未実施であり、クライアント一報も送っていない** (方針不変)
- **前書全項の複製はしない** — 継承を明示し、**本フェーズが足したものだけを書く**

## 1. 現在地 (main)

**フェーズ10 は WP-9 (記録・閉止・ハンドオーバー) の段に入った。** **完了ゲートの実測と未達の扱いは フェーズ10 設計 `docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md` (v1.6) §9.1 が正本であり、本書は再導出しない。** **フェーズ7 の残は依然として WP-9 (公開ゲート) の手順 7 (visibility の切替) だけであり、着手条件は依頼者の実行合図である** (`docs/work-orders/PUBLICATION_GATE_20260906.md` §3.2)。

**束ごとの main へのマージと root suite の集計行 (逐語)。** **詳細 (branch の実装コミット・変異・レビュー巡数) は設計 §11.7〜§11.9 が正本である。**

| 束 | main | 含む WP | 集計行 |
|---|---|---|---|
| 1 | `bce2598` | WP-0 (R-21 の着手前是正) | 文書と README のみ |
| 2 | `7d8bb0f` / `c9a937a` | WP-1a (R-17)、WP-2 (R-19) | `2807 passed in 184.77s (0:03:04)` |
| 3 | `1cd2c39` / `91b3f0f` / `7c53652` / `b16afdd` | WP-1b、CI `tools-tests`、設計 v1.2、作業指示書 v1.0 | `2807 passed in 197.72s (0:03:17)` |
| 4 | `6055c69` / `3d7f823` | WP-3 (実 socket harness、port v1.14)、**WP-5a (契約 1.8.0 公開)** | `2842 passed in 231.02s (0:03:51)` |
| 5 | `0cec2b3` / `25312f4` / `ec15c74` / `4f2fb56` | WP-5a 追補 (U-9)、WP-3 follow-up、WP-1c、外部レビュー 2 の記録 | ゲート 1 は `1 failed, 2852 passed` (赤は R-34 の timing テスト 1 件) |
| 6 | `4e1020a` + `ee80c97` / `c1ce2b4` | WP-6d-i (同一キー直列化)、R-34、R-35 | 設計 §11.4〜§11.6 |
| 7 | `8bf21a2` (+ `318fd3e`) | WP-8a (r2db threadpool 委譲) | `2887 passed in 355.87s (0:05:55)` |
| 8 | `a3a35af` | WP-6a / WP-6b (`process_ceilings`)、**pair-closing (両 peer 1.8.0 宣言、同型性表 97 → 105 行)** | `2964 passed in 250.73s (0:04:10)` |
| 9 | `b1d9001` / `453e711` | 設計 v1.5 + 作業指示書 v1.3、WP-8b (MitateDB threadpool 委譲 + 案 A) | `2975 passed in 376.68s (0:06:16)` |
| 10 | `c387b32` | WP-6c (**新条件 C-26** と両 peer の launcher) | `2990 passed in 237.57s (0:03:57)` |
| 11 | `9361f1b` | WP-4a〜4g (socket 2 plug、6 plug conformance、pool 導出、`CONNECTION LIMIT` migration、F-16)、WP-8c (認証前 slot) | `3294 passed in 266.04s (0:04:26)` |
| 12 | `4a90cf4` | WP-5b (`CONDITIONS.md` の C-03 / C-05 / C-09 / C-15 / C-19 / C-25 を 6 plug の現実に改訂) | `conformance-tests` `959 passed in 146.91s (0:02:26)` |
| 13 | `ff8d232` | WP-7 (`perf_baseline.py` の `--concurrency K`、socket transport 列、K=1 / K=3 の実測) | PERF 行は設計 §9.1 の 6 / 15 に監督が記入する |
| 14 | (本記録の merge。ハッシュは次回引き継ぎ §1) | WP-9 (記録・閉止・ハンドオーバー) | 監督が完了ゲートで記入する |

**集計行の出所**: **完了ゲートは監督がリポジトリルートで単独実行したものが正本である** (`OPERATING_CONDITIONS.md` §1.3 の 19〜21)。**`failed` / `skipped` / `xfailed` / `error` はいずれの束ゲートでも集計行に現れていない。**

**CI について**: **本フェーズの CI 集計行は存在しない。** **GitHub の課金上限に達したことを依頼者が 2026-09-09 に確認し、以後 push を停止したためである** (設計 §5 **U-21**、台帳 **L10-15**)。**コミットとマージはすべてローカルであり、remote には出ていない。** **復旧後に main の先頭で 1 回 run を取り、集計行と `conformance` job の所要を記録すること** (これが L10-1 / L10-15 / 完了ゲート 3・16 の閉止条件である)。

**正本の所在 (第 16 次から更新された箇所のみ)**:

- **本フェーズの実施設計** = `docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md` (**v1.6**)。**§3 の D-1〜D-15 が確定事項**、**§5 が U-1〜U-22 の確定 (依頼者裁定の委任に基づく監督確定) の逐語**、**§6.2 が C-26 / C-27**、**§9 が完了ゲート 17 項目・§9.1 がその実測**、**§10 が台帳 (L10-1〜L10-19、状態注記つき)**、**§11 が実施記録**
- **発注と WP 分割** = `docs/work-orders/WORK_ORDER_PHASE10_DEPLOYMENT_EVIDENCE_V1.md` (**v1.4**)。**§5 に訂正註 6 件** (本文の manifest は書き換えていない)。**訂正註 6 が WP ごとの commit hash の索引である**
- **計画文書** = `docs/design/ROADMAP_POST_PHASE7_V1.md` (**v1.10**)。**§1.0e が現在形の「現状」**、§5 のフェーズ10 節に完了の追記、**§8 の R-17〜R-21 の行き先が「フェーズ10 完了」、R-31 が connection 部分とそれ以外に分かれた**
- **契約** = **1.8.0**。3 複製の sha256 = **`ff97ddce2a209a69e819c3d36ae7870f85238afe1181cfc7db688616f54faa35`**。**従属判断 13** (`spec/CCR_DISPOSITION.md`)。**無条件義務 `limit_enforcement_scoped_to_deployment_behind_base_url` 1 件と、条件付き義務 `idempotency_concurrent_same_key_sends_serialized` 1 件が加わった**
- **conformance の plug は 6 件** (`conformance-tests/registry.json` の `adapters`。`r2db-api` / `MitateDB-api` / `r2db-api-http` / `MitateDB-api-http` / **`r2db-api-socket`** / **`MitateDB-api-socket`**)、**新節 `composition_roots` が 2 件**。**新条件は C-26 (実行可能) と C-27 (declared のまま)**
- **同型性表 `_ISOMORPHIC_TARGETS` は両 peer 105 行** (両 peer の `tests/test_audit_query.py`)
- **`conformance-tests/COLLECTION_FLOOR`** = 着手時 2807。**更新は完了ゲートの実測値で監督が単独コミットする**

## 2. 到達した状態

### 2.1 「宣言した URL が実在する」が実 TCP で検査されるようになった (L7-2 / L6-5 / L6-12 / LQ4-9)

- **5・6 番目の plug は既存 HTTP adapter の composition を継承し、同一プロセス内の uvicorn thread に bind して、その前に nginx subprocess を置く。** **client は実 TCP で叩く** — **変わるのは transport (実 HTTP/1.1 framing、実 proxy、実 connection 並行性) だけである。**
- **C-19 の実ダイヤル枝が `transport_kind == "socket"` で分岐し、data 面 / control 面の両方で認証付き GET が `200` と同一文書を返すことを確かめる。** **in-process / ASGI plug が自己整合のままである射程は `CONDITIONS.md` の C-19 行に開示した。**

### 2.2 「本番の組み立て方そのもの」が共通 suite で 1 度だけ起動されるようになった (LQ4-11、新条件 C-26)

- **両 peer が `conformance/real_server_<peer>.py` に launcher を持ち、文書化された composition root を文書化された env だけで実起動する。** **C-26 は 6 項目を観測する** — 宣言 CLI → uvicorn → nginx → readiness の順序、**serve された `capabilities.surfaces` へのダイヤルと宣言表からの読み戻しの一致**、`deploy_smoke` の緑、**`process_ceilings` を 1 / 2 で宣言した 2 回の起動による `limit_enforcement` 写像の観測**、行が無ければ fail-fast すること、終了時の残骸 0。
- **F-16 (role の `CONNECTION LIMIT` が pool 構成の floor を下回れば起動を止める) も C-26 が観測する。**

### 2.3 「資源制限の適用単位」が契約で定義された (R-18、契約 1.8.0)

- **契約 1.8.0 は「`enforced` の適用単位は宣言 base URL の背後の配備である」と定め、配備者宣言 `process_ceilings = {"data": <int>, "control": <int>}` から `limit_enforcement` を導く。** **写像は 3 区分である** — 要求単位で完結する class は ceiling に依らず不変、in-memory per process の class は ceiling ≥ 2 で `deployment_required`、**DB 側で bound する class は同一 tx 内の lock 付き check-then-write なので ceiling に依らず `enforced`**。
- **3 区分目の lock は両 peer とも表単位の定数 key の `pg_advisory_xact_lock` (同名 helper `_take_bound_advisory_lock`) である。**

### 2.4 「宣言した bound が実配備で本当に到達できる」ようになった (R-20、L10-8〜L10-12)

- **両 peer の HTTP handler が同期区間を `run_in_threadpool` へ委譲した。** **委譲前は単一 event loop の上で in-flight が 1 に留まり、宣言 `concurrency` は到達不能だった。**
- **委譲して初めて実並行になり、3 つの実欠陥が露出した** — **role pool が固定 4 だったこと、PostgreSQL role の `CONNECTION LIMIT` が実 pool 構成に足りなかったこと、MitateDB の cell が共有する単一接続が lock の外で他要求に奪われること。** **いずれも本フェーズ内で閉じた。**
- **併せて、data 面は認証の前に concurrency slot を取るようになった** (両 peer。裁定 4 (2026-09-06) の HTTP 面の更新)。

## 3. クライアント連携状態

**一報は送らない** (依頼者判断 2026-09-03 以降不変)。**ただし契約が 1.7.0 から 1.8.0 へ上がり、3 複製の sha256 が動いた。**

- **後方互換の追加のみである。** **1.8.0 を宣言する実装には無条件義務が 1 件 (適用単位)、条件付き義務が 1 件 (同一キー同時送信の直列化) 加わる。** **1.7.0 を宣言する第三者実装は 1.7.0 のまま conformant である。**
- **既存 client から見た挙動の変化は無い** — **`limit_enforcement` の値が配備者宣言に応じて `enforced` / `deployment_required` を取り得るようになったが、これは「宣言が正直になった」ことであって拒否の形は変わらない。**
- **実配備は未実施なので、現に影響を受けるクライアントは存在しない。** **公開 (フェーズ7 WP-9 の手順 7) を実行した場合の影響は第 14 次 §3 のままである。**

## 4. 次の一手 (優先順)

### 4-1. フェーズ10 の残 2 件 (フェーズを閉じる前に依頼者へ報告して決める)

- **(a) WP-6d-ii (新条件 C-27)。** **C-27 は `CONDITIONS.md` に declared のままで、共通 suite ではまだ駆動していない。** **必要なのは port hook `hold_after_idempotency_lookup` (保持点は受理区間の末尾) と `conformance-tests/test_c27_concurrent_same_key.py` であり、実装の形は設計 v1.5 §3 D-13 の「実装の形 (6d-ii) の確定」と作業指示書 v1.3 の WP-6d-ii manifest が確定済みである。** **着手条件だった「両 peer の 1.8.0 フリップ」は `a3a35af` で満たされた。** **worktree は `phase10-wp6dii`。**
- **(b) PERF 行の記入。** **WP-7 (`perf_baseline.py` の `--concurrency K`、socket transport 列、K=1 / K=3) は main `ff8d232` に入った。** **残るのは監督が単独実行した値を設計 §9.1 の 6 / 15 に、フェーズ9 §11.2 と同形式で記入することである** (閾値は置かず plug 間の比較もしない。**WP-6d の lock 導入前後のどちらであるかを明記する**)。**この値が台帳 L10-9 (要求スコープ接続をフェーズ11 へ送るか閉じるか) の判断材料である。**

### 4-2. 台帳の開いている項目

**フェーズ10 側 (設計 §10.3 / §10.4 が正本。全 19 項に状態注記がある)**

- **閉じた**: **L10-7** (socket plug と C-26 の分割)、**L10-8** (in-flight 1)、**L10-10** (認証前 in-flight bound)、**L10-11** (`CONNECTION LIMIT`。R-31 の connection 部分)、**L10-12** (readiness probe の window 消費)、および **L10-1** (CI 所要をローカル値で記録)。
- **開いている (記録)**: **L10-2** (宣言 `process_ceilings` と Cloud Run 側 `--max-instances` の一致は app も共通 suite も検証できない)、**L10-3 / L10-4 / L10-5**、**L10-6** (`image-pins` の証拠は CI にしか無い)、**L10-13** (`.pth` が main checkout を指す)、**L10-14** (待機ループ)、**L10-17** (WP-6c の軽微 4 件)、**L10-18** (slot 持ち回りの実現差)、**L10-19** (`_SURFACES` 定数化)。
- **開いている (作業待ち)**: **L10-9** (要求スコープ接続。WP-7 の結果で裁定)、**L10-15** (CI 集計行)、**L10-16** (`_ISOMORPHIC_TARGETS` に未登録の同名 helper — launcher 群、F-16 の `check_role_connection_limits` 系、WP-8c の `_parse_handler` / `_authenticate_call_nodes` 系。**登録は Class D の pair-closing commit**)。

**フェーズ7 / 8 / 9 側**: **L7-2 / L8-5 (PERF の記入待ち) / L8-6 / L9-15 / LQ4-11 は本フェーズで閉じた (L8-5 のみ記入待ち)。** **それ以外は第 16 次 §4-2 のままである。**

### 4-3. 依頼者判断待ち (フェーズ完了報告で問う)

- **R-22**: **`security/CONTROL_MAPPING.md` の再編 (invariant ごとの節 + 「統制 / 証拠 / 状態」の表。Class D、内容不変) を行うか。** **同時実施の相手だった R-21 の是正は 2026-09-08 に完了したので、その機会は過ぎた。** **行き先候補は開発プロセス衛生 v2 (R-32 / R-33 と一緒) である。**
- **報告事項**: **U-1〜U-6 (設計時) と U-14〜U-22 (実施時) の計 15 件の監督裁定を列挙する。** **併せて push 保留の事実と、上記 4-1 の残 2 件を報告する。**

### 4-4. フェーズ11 (実需駆動)

**送るのは R-23 / R-28 (3) / R-29 (両 peer の最低共通機能プロファイル) / R-30 (SI-00 の境界) / R-31 の残余 (connection 以外の配備全体の資源保護) / R-32 (検証 seam と同型性の分離) / R-33 である。** **着手順は計画文書 §5 のとおり実需の記録順であり、本書では固定しない。**

### 4-5. GitHub 復旧後にすること

1. **`git log --format='%an <%ae>' -N` で `r2fish` / noreply のみを確認してから push する** (`OPERATING_CONDITIONS.md` §1.1 の 5〜7)。**本フェーズは 30 件超のコミットがローカルにあるので、確認は全件に掛ける。**
2. **main の先頭で 1 回 run を取り、`conformance` (3.11 / 3.12) の集計行、`tally-consistency`、`image-pins`、`doc-refs`、`tools-tests`、`change-class` の状態と、`conformance` job の所要時間を記録する** (L10-15 / L10-1)。
3. **`COLLECTION_FLOOR` の値が CI の collect 件数と一致することを確認する。**

## 4-6. 運用規律 (第 16 次 §4-5 と `OPERATING_CONDITIONS.md` を継承。本フェーズが足したもの)

**`OPERATING_CONDITIONS.md` §2 の 17〜20 と §3 の 11〜12 が正本である。本書は要点だけを指す。**

- **worktree から起動する subprocess には `PYTHONPATH` を明示する** (§2 の 17)。
- **待機ループは python プロセスだけを数える形で書き、`comm=` が効かない場合は `ps -eo args= | grep -q '[-]m pytest'` に落として逸脱として報告する** (§2 の 18)。
- **性能計測中は pytest と nginx を走らせない** (§2 の 19)。
- **課金上限中は push しない。文書だけのコミットには `[skip ci]` を付ける** (§2 の 20)。
- **`tools-tests` は常時実行、`image-pins` の証拠の場は CI だけである** (§3 の 11〜12)。
- **並行 worktree は同一ローカル PostgreSQL を共有する。** **本フェーズでは他 worktree の suite と重なって `AUTH_STATE_UNAVAILABLE` / `LIMIT_EXCEEDED` の偽赤が繰り返し出た。** **「単独実行」は worker 数ではなく他 pytest が 0 件であることを指す** (§1.3 の 21) — **この条件を満たさないまま取った赤は原因の特定に使わない。**

## 5. 教訓の追加 (前書全項継承に追加)

- **「宣言した bound が実配備で到達可能か」は、実 socket と実並行を通すまで分からない。** **本フェーズが見つけた実欠陥 6 件のうち 3 件 (固定 4 の role pool、role の `CONNECTION LIMIT` 不足、readiness probe の window 消費) は、in-process / ASGI の場では原理的に見えなかった。** **「宣言が真であること」を条件化するだけでは足りず、宣言を真にする経路が実配備で通ることまで測る必要がある。**
- **発注文で前例を引くときは、その前例を現物で確認してから引く。** **本フェーズの最大の欠陥 (件数 bound の lock が deadlock する形) は、監督がフェーズ9 R-2 の `LOCK TABLE ... IN SHARE MODE` を「件数 bound の前例」として誤って引いたことが直接の原因である。** **実装担当は指示どおりに書き、レビューが実 PG で `{1: 'DeadlockDetected', 2: 'OK'}` を実測して初めて分かった。** **前例の確認を実装担当に課す条項 (WP-6d-i の完了条件 8) は正しく働き、フェーズ9 R-2 自身の欠陥 (R-35) まで露出させた。**
- **「テストが空振りしている」は、実装の欠陥と同じ頻度で出る。** **本フェーズのレビューは、deadlock を踏まない順序で書かれた lock テスト、明示注入で composition root を通らない写像テスト、委譲を外しても緑のままの委譲テスト、lock オブジェクトの入場回数だけを数える thread-safety テストを見つけた。** **いずれも「緑である」ことが性質の証拠になっていなかった。** **変異は「テストが赤くなるか」ではなく「本来守るべき性質を壊す変異で赤くなるか」で設計する。**
- **待機ループのデッドロックは 1 日単位で時間を溶かす。** **本フェーズでも `ps ... | grep pytest` 形の待機ループが丸 1 日超残った。** **加えて、第 16 次が定めた `ps -eo comm=,args=` 形はこの開発機では `comm` がパス切り詰めのため一致せず、待たずに即抜けする** — **「待った」と思って走らせた suite が他 worktree と重なる。** **待機形は必ず 1 度、意図どおり待つことを確かめてから使う。**
- **共有 `.venv` の `.pth` は main checkout を指す。** **worktree の中で subprocess を起こす仕組み (C-26 の composition root、`ops` CLI) は、`PYTHONPATH` を明示しない限り worktree の変更を見ない。** **「直したのに変異が赤にならない」の原因になる。**
- **課金上限のような外部要因は、隠さず未達として残す。** **本フェーズは CI を 1 度も回せなかった。** **ローカルの単独ゲートは正本として有効だが、3.12 matrix の再現と `image-pins` の証拠はローカルには無い。** **「合格」と書けるのは測った項目だけであり、測れなかった項目は台帳 (L10-15) と完了ゲートの実測表に未達として残す。**
- **実装担当が「壊れた状態」を報告してきたときは、それを設計判断として扱う。** **WP-8c の fail-closed 化は conformance adapter の構築を壊し、conformance 全件が収集不能になった。** **報告は隠さず出され、統合 branch の WP-4g で配線して解いた。** **「壊れているので緩める」の側に倒さなかったことが、`HttpService` の必須引数を守った。**
- **同型性登録のために片側を寄せる判断は、記録に残す。** **`_surfaces_value` を登録するために MitateDB 側の inline dict を r2db と同じ module 定数に揃えた (値は不変)。** **逆に `cmd_declare_process_ceilings` は、正規化後も本物の差 (statement 順・例外処理の形) が残ったので登録しなかった。** **「同型性表に載せられるか」を実装の形の判断基準にしないこと** — **計画文書 §8 の R-32 が扱うのはこの境界である。**

## 6. 追記 2026-09-10 (本書の記述後に WP-6d-ii が入った)

**本節より上は 1 文字も書き換えていない** — **上の §1 / §4-1 (a) / §4-2 は本書を書いた時点 (WP-6d-ii の着手前) の記録である。以下がその現在形である。**

- **WP-6d-ii は実施済みである。** **branch `phase10-wp6dii` の実装 `d97de35` → Opus のコードレビュー是正 `8425ef4` (判定「accept with fixes」、指摘 F1〜F7) → main 取り込み `05bc548`。main へのマージは `2455f96` (`[skip ci]`) であり、これが本フェーズの束 15 である** (設計 §11.7)。
- **したがって §4-1 の残 2 件は 0 件である。** **(a) C-27 は `CONDITIONS.md` で `executable` になり、6 plug 全数で駆動する** (in-process 2 + ASGI 2 + socket 2。**socket 2 plug は hook を 1 行も書かずに継承する**)。**(b) PERF 行は設計 §11.10 に入った。**
- **新しい正本の所在**: **conformance adapter port は v1.14 → **v1.15** (`docs/design/CONFORMANCE_ADAPTER_V1.md` §25)。** **新 hook は `hold_after_idempotency_lookup(session, idempotency_key)`** (`conformance-tests/adapter.py` の abstract method 1 個 + 非 normative handle `IdempotencyHold`)。**新しい共通テストは `conformance-tests/test_c27_concurrent_same_key.py`** (plug ごと 5 本 + registry guard 2 本 = **`32 passed`**)。
- **契約 1.8.0 の条件付き義務 `idempotency_concurrent_same_key_sends_serialized` は、両 peer について共通 suite が観測している。** **本フェーズの新条件は C-26 と C-27 の 2 件で確定した。**
- **`conformance-tests/COLLECTION_FLOOR` は本書 §1 の 3294 から `3326` へ監督が再更新する** (単独コミット。C-27 の 32 件ぶん増える)。**§1 の「着手時 2807」の記述はそのままである。**
- **開示 1 件 (弱点ではなく観測限界)**: **`MitateDB-api-http` では PG session advisory lock を外しても C-27 は赤にならない** — **共通 suite は 1 application につき cell を 1 つしか張らず、その `RLock` が先に直列化するからである。** **非 vacuity は peer-local テスト (2 cell 構成、`MitateDB-api/tests/test_idempotency_concurrency.py`) が担う。C-27 行に開示済みである。**
- **開示 1 件 (完了条件)**: **作業指示書 WP-6d-ii の完了条件 12 のうち「`wait_until_held` の戻り値を定数 1 にする」変異は反証不能である** (保持件数は常に 1)。**監督裁定 2026-09-10 は受理であり、測っている性質は「hook を no-op にすると保持待ちが全件で時間切れになる」変異が pin する** (設計 §9.1 の「未達の扱い」の追記)。
- **残る未達は 1 種だけである** — **CI の集計行が課金上限で未取得であること** (台帳 **L10-15**、設計 §9.1 の項目 3 / 16)。**push は依然として停止中である** (§4-5 の手順は不変)。
- **畳む worktree** (実数は `git worktree list` で確認する。`OPERATING_CONDITIONS.md` §1.2 の 18): **`phase10-wp1c` / `phase10-review2` / `phase10-wp3f` / `phase10-wp6d` / `phase10-r34` / `phase10-r35` / `phase10-wp6dii`。**
- **更新した記録**: フェーズ10 設計 **v1.7** (§3 D-13 の実施註 (6d-ii)、§5 U-8 の実施註、§9.1 の項目 1 / 5 / 8 (f) / 14 への追記、§11.7 の束 15、§11.11)、作業指示書 **v1.5** (WP-6d-ii manifest の状態・実施の記録、§5 訂正註 7)、計画文書 **v1.11** (§1.0e / §5 / §8 の **R-24** 閉止)。**R-24 は 6d-i + 6d-ii の両方が入って完全に閉じた。**

## 7. 追記 2026-09-13（L10-16 の記録照合・閉止）

**本節より上の当時の記録は書き換えていない。** §4-2 が「作業待ち」とした **L10-16 は閉止した。** その後の Class D pair-closing `2152c94`（実装 `fe2b105`）で、両 peer の `_ISOMORPHIC_TARGETS` は **105 → 137 行**になった。C-26 launcher の同名 helper 23 件、F-16 の同型な純粋 Python 部分 7 件、WP-8c の `_parse_handler` / `_authenticate_call_nodes` 2 件を登録し、同型に見えても実在する peer 差を持つ `check_role_connection_limits` 本体などは対象外として根拠を table のコメントへ残した。table 全内容を pin するテストは 137 行を assert し、行削除・片側1文字差分の変異は赤であることを実測した。証跡はフェーズ10 設計 v1.8 §10.4 の L10-16 行が正本である。**フェーズ10の未達は、引き続き CI 集計行 L10-15 のみである。**
