# フェーズ7 以降の計画 (Roadmap) v1

- 版数: **v1.183 (2026-10-06)**。v1.182 からの変更: **R-123 を閉止した** (変更セット `r123`、Class B、規模 S)。r2db in-memory plug の `pg_text_format.py` を実 PostgreSQL 16.14 に合わせた: `_float8out_text` は PG の float8out (Ryu 最短桁列、区間の両端を除外、plain は指数 -4 以上 15 未満) を再現、`_jsonb_numeric_text` は -0.0 を `0.0` に、`_predicate_text` は typed number 列の int も float8out に通す。棚卸しとレビューで台帳の 2 点の外に 2 点 (≥ 1e16 の境界値、typed number 列の int) が出て同じ変更セットで直した。完了条件 C-1〜C-4 と変異 M-1〜M-4 (+M-3b) は parity テスト 4 本、実 PG との corpus 比較 12268 値は不一致 0、docstring 3 本は CH-1130〜CH-1132 で登録 + 訂正記録。完了ゲート gate: 5280 passed, 2 subtests passed in 473.50s (0:07:53), judge=PASS, label r123, pg_database/pg_roles diff 0 (log `gate 20261006-064721`; 収集数 5276 → 5280 で `conformance-tests/COLLECTION_FLOOR` を 5280 に上げた)。監督裁定 6 件 (契約は number 列の text 形を定めない、ほか) は事後確認待ち。記録: `docs/archive/docs/design/ROADMAP_POST_PHASE7_V1__LEDGER_CLOSED.md` の R-123 の節。
- 版数: **v1.182 (2026-10-06)**。v1.181 からの変更: **R-39 の監督裁定 Y-1〜Y-20 の依頼者による事後確認 (2026-10-06) を記録した。** 依頼者 (逐語): 「事後確認は了承します」 — 対象は引き継ぎ書 `docs/work-orders/HANDOVER_20261005_R39_FABLE.md` §4.1・§4.2 の Y-1〜Y-20 (Y-3a を含む 21 行: 印の除去、`src/` 側コメントの R-22 への引き渡し、位置参照の symbol 形とガード、C-xx 昇格の不採用、R-123 / R-124 の起票、R-95 の床、mutate.py の既知の穴ほか)。閉止行 R-39 の記録ファイルの節末尾に【追記】した (設計 `docs/design/LEDGER_FIXED_FIELDS_V1.md` D-4)。R-123 / R-124 の判断は未着手のまま。v1.177 の版数行を版数ログへ回転した。
- 版数: **v1.181 (2026-10-05)**。v1.180 からの変更: **R-39 を閉止した** (変更セット 2 を統合)。tests / conformance / conformance-tests / README の行番号形の位置参照 91 件を `file.py::symbol` 形へ置き換え、時点の記録 16 件は新ガード `tools/tests/test_no_line_number_position_refs.py` の allowlist に固定、不正確な文 3 種と MitateDB README の 2 文を現物に合わせ、R-95 の床を実測へ下げた (監督裁定 Y-3〜Y-19、事後確認待ち。Y-19 は tools/tests 対象の mutate.py が suite lock を取らない既知の穴)。完了ゲート `gate: 5276 passed, 2 subtests passed in 753.62s (0:12:33), judge=PASS, label r39-cs2`。置換 138 件、allowlist 45 entry・48 件、ガードの変異 10 件と R-95 の変異 29 件が期待どおり、`tools/dev/mutate.py` に Known gaps 3 (Y-19)。 R-39 行を §8.2 の索引と記録ファイルへ移した。v1.176 の版数行を版数ログへ回転した。
- 版数: **v1.180 (2026-10-05)**。v1.179 からの変更: **R-39 に着手し、変更セット 1 (テストの穴) を統合した。** 依頼者指示 2026-10-05 (逐語:「R-39を着手するチップを出して」) で着手し、印「あり」(着手条件: 運用開始後) を監督裁定 Y-1 で「なし」に改めた (事後確認待ち)。棚卸し: (1b)(1g)(3a) は閉止済み、(1m) は既存の literal pin が固定済み、(1h) の「bool の offset」は前提消滅。変更セット 1 = 両 peer の新規テスト 10 本 (r2db 6、MitateDB 4) で 28 性質を固定、既存テストと `src/` の変更 0、変異 28 件が赤、完了ゲート `5276 passed, 2 subtests passed`、`COLLECTION_FLOOR` 5248 → 5276。作業指示書 `docs/work-orders/WORK_ORDER_R39_TEST_GAPS_V1.md` (変更セット 1・2)。R-123 (r2db `pg_text_format` の実 PG との不一致) と R-124 (order_by 項目の details.field の peer 差) を起票した。`src/` 側の古いコメントは R-22 へ渡した (Y-2)。R-39 行は開いたまま (変更セット 2 = 位置参照、Class C、進行中)。v1.175 の版数行を版数ログへ回転した。
- 版数: **v1.179 (2026-10-05)**。v1.178 からの変更: **R-22 問い 3 の依頼者による事後確認 (2026-10-05) を記録した。** 依頼者 (逐語): 「事後確認は了承します」 — 対象は、R6-4 の残りの日付の除去と変更セット 7・8・9 の監督裁定 18 件 (引き継ぎ書 `docs/work-orders/HANDOVER_20261005_R22_CS7_FABLE.md` の §4 の 1〜8、§6 の 9〜14、§6b の 15〜18)。R-22 行に【追記】した。行は開いたままである。未決 (fingerprint に入る MitateDB の 4 module の扱い、検査器が受け付けない形の許可、origin のクラウドの branch 2 本、GitHub への送信) は確認の対象ではなく、残る。v1.174 の版数行を版数ログへ回転した。
- 記録: `docs/archive/docs/design/ROADMAP_POST_PHASE7_V1__VERSION_LOG.md` (v1.107 以前の版数ログ。逐語。書き換えない)
- 起草: Fable (監督)。依頼者の目標 (§0) は逐語。判定 (§3, §6) は本会話での監督評価であり、各フェーズの設計文書で再審議してよい。
- 位置づけ: 本書は **計画文書**であり、`CLAUDE.md` の source-of-truth 順位には入らない。各フェーズの正本は、そのフェーズの設計文書 (`docs/design/PHASE*_V1.md`) と作業指示書である。本書はそれらの**着手順・範囲・着手条件・守るべき条件**を先に固定し、次フェーズの設計起草者が「何を、なぜ、どの順で」を再導出せずに済むようにする。
- 前提となる main: `e26f704` (フェーズ7 WP-8 マージ後。WP-7 の gate 2265 passed / 9 xfailed)。

---

## 0. 依頼者の目標 (2026-09-06、逐語)

> 私が望むのは、このリポジトリ成果物が、AI(エージェント)にとってのベストなDBプラットフォームになることです(人を拒絶するわけではない)。それは、人からみて、比類なきセキュリテイ・信頼性を備えていることです(パフォーマンスが高いことは大前提)。

本書はこれを 4 つの要求に分解して扱う。

| 記号 | 要求 | 本書での扱い |
|---|---|---|
| **G-1** | AI エージェントにとって最良の DB プラットフォーム | エージェントの 1 周 (§4 P-2) を閉じることを最優先にする。人間の利用を排除しない (機械可読と人間可読を両立する) |
| **G-2** | 人から見て比類なきセキュリティ | Security Invariants と conformance による**証明可能性**を維持し、宣言した bound が全 peer で実効であること (§5 フェーズ8) |
| **G-3** | 比類なき信頼性 | 1 要求 = 1 原子単位、再送安全性 (idempotency)、宣言が真であること (§4 P-1〜P-3) |
| **G-4** | 高性能は大前提 | **現時点で計測が存在しない** (§7)。フェーズ8 で基準値を取り、以後は各フェーズが差分を記録する **【訂正註 2026-10-04 (R-28)】** 同じ欄の前の文は 2026-09-06 の起票時の原文である。基準値は 2026-09-07 に取得済みで、閾値は §0.1.4 にある |

既存の設計原則 (2026-09-02: 先送りしない・シンプル・制約で回避しない・誇れる成果物) と、契約の前提 (利用設計者は AI エージェントであり、宣言は読まれる) は本書全体に適用する。

## 0.1 終わりの定義 (2026-09-23)

§0 の G-1〜G-4 は方向であって終了条件ではない (G-4 の欄は「現時点で計測が存在しない」と書かれたままであり、基準値は 2026-09-07 に取得済みである — §7 の 1 の訂正註)。台帳は 2026-09-15〜23 の 9 日で起票 54 件・閉止 40 件であり、閉じるたびに文書・テスト・道具が増える (17 日で `.md` の行数 25,089 → 66,571、`tools` の `.py` 6 → 38) ので、自然には閉塞しない。既知の穴の運用 (`docs/work-orders/OPERATING_CONDITIONS.md` §1.12) と規模三段 (同 §1.13) で増分は減るが、閉塞したときに「終わった」のか「止まった」のかを見分ける基準が無いと起票が再開するので、本節にその基準を置く (数字と趣旨は依頼者指示 2026-09-23)。

### 0.1.1 終了条件

| G | 終了条件 | 検証法 |
|---|---|---|
| **G-1** | エージェントの 1 周 (§4 P-2: catalog を読む → 要求を作る → 判定を受ける → 安全に再送する) の 4 段それぞれに、両 peer で executable な共通条件 (`conformance-tests/CONDITIONS.md`) が少なくとも 1 件あり、緑である | 下の 0.1.2 の対応づけと `conformance-tests/registry.json` の adapter 構成、および完了ゲート (`tools/dev/gate.py`) の集計行 |
| **G-2 / G-3** | 契約の現行版 (現在 1.16.0 (R-42、2026-10-03。1.15.0 は R-118、2026-10-03)。`spec/data-service-api.v1.json`:6、両 peer の `capabilities_document`。契約版を上げる変更セットは同じ変更セットで本行の版を更新する) の性質が両 peer で conformance に固定されている — `conformance-tests/CONDITIONS.md` の全条件 (現在 C-00〜C-36 の 37 件。C-32 は 2026-09-29 の R-113、C-33 は 2026-10-01 の R-115、C-34 は 2026-10-01 の R-102、C-35 は 2026-10-01 の R-108、C-36 は 2026-10-03 の R-42 で足した) が両 peer で executable かつ緑 (C-26 は plug ではなく composition root 単位) (完了ゲートの集計行で failed / skipped / xfailed = 0) — かつ、`security/SECURITY_INVARIANTS_V1.md` の各 SI (SI-00〜SI-15 の 16 件) について `security/CONTROL_MAPPING.md` の r2db-api 節と MitateDB-api 節の両方に、テスト名で指せる証拠がある | `CONDITIONS.md` の `executable` 欄と完了ゲートの集計行、`CONTROL_MAPPING.md` の各 SI の peer 節のテスト名 |
| **G-4** | 性能の大前提が計測で満たされている — R-101 (1 process 内の直列化の主体の切り分け) と R-102 (MitateDB のデータ面の application 単位の直列化) が閉じ、`docs/design/PERF_*` の基準値が閾値付きで記録され、直近の計測がその閾値の内側にある | §8 の R-101・R-102 行の閉止と、`tools/perf_baseline.py` の PERF 行 (p50 / p95 / `backend_calls`) の記録 (閾値は 0.1.4 のとおり。依頼者裁定 2026-09-24) |

### 0.1.2 G-1 の 4 段と共通条件の対応づけ (実物の Condition 文から)

| 周回の段 | 共通条件 |
|---|---|
| catalog を読む | C-11・C-12・C-17・C-19・C-20・C-28・C-29 |
| 要求を作る | C-03・C-21・C-22・C-28・C-30 |
| 判定を受ける | C-04・C-05・C-18・C-21・C-24・C-28・C-30・C-31 |
| 安全に再送する | C-07・C-23・C-25・C-27・C-28 |

### 0.1.3 現時点の充足状況 (2026-09-23 の実測)

| G | 状況 | 実測 | 欠けるもの / 対応する R |
|---|---|---|---|
| **G-1** | **充足** (2026-09-25 再実測、WP-6) | 4 段すべてに両 peer で executable な条件がある (0.1.2 の対応づけ。「要求を作る」「判定を受ける」の 2 段に C-30 を追加。全件 four adapters / six adapters)。C-30 の 9 node (T は 7 変種) が 6 plug で `pt: 90 passed` (`conformance-tests/test_c30_keyset_paging.py -q -rxX -n 2`、実装担当実測 2026-09-25)。**完了ゲートは本 WP では未実施** (merge 前の 1 回に委ねる。§9 WP 分割の骨子) — 前回の完了ゲート (`gate: 4056 passed, 2 subtests passed in 330.43s (0:05:30)`、judge=PASS、pg_database/pg_roles diff 0、label p11、2026-09-25) は本 WP-6 の変更を含まない。**【追記 2026-09-25 (受け入れ監査)】** 受け入れ監査の実施中に監督が単独実行した完了ゲートの集計行は `gate: 4167 passed, 2 subtests passed in 327.83s (0:05:27)`、`judge=PASS`、pg_database/pg_roles diff 0 (`$SP/acceptance-packet.md` §3)。本追記 (観察 1 の新テスト・記述訂正) を含めた最終ゲートの集計行: `gate: `gate: 4168 passed, 2 subtests passed in 327.60s (0:05:27)`、judge=PASS、pg_database/pg_roles diff 0、label p11b (最終ツリー。SQLite の改変 cursor テスト追加前の ff6ad67 では label p11 `4167 passed in 327.83s`、judge=PASS)`(監督が最終ゲート後に埋める) | 無し (前回の実測 = 完了ゲート `3987 passed, 2 subtests passed`、judge=PASS、pg_database/pg_roles 差分 0、2026-09-23、label s01-end) |
| **G-2 / G-3** (conformance) | **充足** (2026-09-25 再実測、WP-6) | 31 件全件が `executable` (表記の内訳: `four adapters` 20 / `six adapters` 9 (C-28・C-29・C-30 を含む) / `two composition roots` 1 = C-26 / adapter 数の表記なし 1 = C-27。`CONDITIONS.md`:60 の凡例により `four adapters` の語は `registry.json` の全 registered adapter (現在 6) を指す)。片 peer のみの条件は 0 件。C-19 (版一致 assert) は `pt: 67 passed`、C-29 の版一致 node を含む `test_c29_operation_catalog_url.py` は `pt: 20 passed` (実装担当実測 2026-09-25)。**完了ゲートは本 WP では未実施** (前回のゲート `gate: 4056 passed, 2 subtests passed in 330.43s (0:05:30)`、judge=PASS、pg_database/pg_roles diff 0、label p11、2026-09-25、は本 WP-6 の変更を含まない) **【再実測 2026-10-01】** 36 件 (C-00〜C-35) 全件が `executable` (`conformance-tests/CONDITIONS.md` の Status の表記の内訳: `four adapters` 19 / `six adapters` 12 / `two composition roots` 3 = C-26・C-32・C-33 / `four wire adapters` 1 = C-35 (凡例 `conformance-tests/CONDITIONS.md`:90、R-108) / adapter 数の表記なし 1 = C-27)。完了ゲート `gate: 5014 passed, 2 subtests passed in 558.50s (0:09:18)`、judge=PASS、pg_database/pg_roles diff 0 (label r108、2026-10-01 21:18、merge 候補 `2e51997` = local main `9be46b7` を取り込んだ branch `r108`)。 | 無し (前回の実測 = 28 件、`six adapters` 6、凡例 `CONDITIONS.md`:58、完了ゲート `3987 passed, 2 subtests passed`、2026-09-23) |
| **G-2 / G-3** (`CONTROL_MAPPING`) | **充足** (2026-09-25 再実測、WP-6) | 版 **3.3** (R-109。C-30 の Control/Evidence を SI-01・SI-08・SI-10 の Common 節に、Status を SI-03・SI-08・SI-10 に追加。新しい invariant は足していない)。16 SI の全 Evidence 主張 357 件 (3.2 の 352 件 + 5 件)、全 Control 主張 580 件 (3.2 の 577 件 + 3 件。数え方は 3.0 時点と同じ) が `conformance-tests/test_control_mapping_register.py` で解決する (実装担当実測 2026-09-25: `pt: 58 passed`)。SI-07 の r2db-api 節の証拠欠落 (0.1.5 の (c) 裁定どおり起票しない) は不変。**完了ゲートは本 WP では未実施** (前回のゲート `gate: 4056 passed, 2 subtests passed in 330.43s (0:05:30)`、judge=PASS、pg_database/pg_roles diff 0、label p11、2026-09-25、は本 WP-6 の変更を含まない) | 無し (前回の実測 = 版 3.2、Evidence 352 件、Control 577 件、2026-09-25、label p11) |
| **G-4** | **未充足** | R-101・R-102 は 2026-09-23 起票のみ (規模 M / L、R-102 は設計レビューが着手条件、R-79〜R-82 の結果待ち)。基準値は存在する (フェーズ8 設計 §11.2 = 2026-09-07 の 14 行、フェーズ9 設計 §11.2 = 2026-09-08 の前 / 後 / Δ 表、フェーズ10 設計 §11.10 = K=1 / K=3 の PERF 行、`docs/design/PERF_CONCURRENCY_MEASUREMENT_V0_1.md` v0.2 = K sweep) が、**閾値はどこにも無い** (`tools/PERF_BASELINE_README.md`:9-13、:265-266「places no threshold on anything (P-8)」、フェーズ8 設計 §11.2 の注記「閾値は無い (P-8)」) **【2026-09-25 再実測】** R-101・R-102 は起票のみのまま (§8)。閾値は §0.1.4 に置かれた (依頼者裁定 2026-09-24)。 **【2026-09-27 再実測】** R-101 は WP-1 (計測器) / WP-2 (実測と判定) 実施済みだが未閉止 (§0.1.4 の 2: K=32 / K=1 が 29.5〜33.3 倍。§8 の R-101 行)。R-102 は起票のみ。 **【2026-09-28 再実測】** R-101 は是正 WP-3 / WP-4 を実施したが閉止せず (§0.1.4 の 2 の改訂形 = real-server plug で 15.7 / 18.7 倍。1 回目の 4.6 / 4.3 倍は計測器の欠陥で無効。§8 の R-101 行と設計メモ v0.3 §6)。8 倍に届く候補は R-113 (multi-process)。R-102 は起票のみ。§0.1.4 の 3 (MitateDB の lock 待ち 10% 以下) は未計測。 **【2026-09-29 再実測】** R-113 (multi-process worker) を実施したが R-101 は開いたまま (依頼者裁定「R-101は閉じない」、§8 の R-101 行)。real-server plug の 4 worker で `query` p50 の K=32 / K=1 は約 7〜10 倍 (正式の run は r2db 6.78 / 7.24 倍、MitateDB 7.60 / 7.40 倍で 8 倍以内。同じ手順の繰り返し 2 回では最大 10.30 倍、12 個の比のうち 8 超が 5 個。設計 `docs/design/MULTI_PROCESS_WORKER_V0_1.md` §7.4 の表 7-1)。§0.1.4 の 1 (K=1 の非退行) は同 表 7-2 の 21 行とも閾値の内側。R-102 は起票のみ。§0.1.4 の 3 は未計測。 **【2026-10-01 再実測】** R-102 を閉止した (§8.2、記録ファイルの R-102 の節)。§0.1.4 の 3 (R-102 設計の Q-2 の読み替え: pool の取得と schema lock の waits / acquire の合算、K=4) の判定値は 2 run とも 0 / 4856 = 0.0% (基準値 1319 / 3537 = 37.3%。作業指示書 `docs/work-orders/WORK_ORDER_R102_APPLICATION_SERIALIZATION_V1.md` §5.3 表 A) で充足。K=1 の非退行 (§0.1.4 の 1) は全 plug で閾値の内側 (同 表 B)。R-101 は開いたまま。 | R-101・R-102 の閉止と、閾値の裁定 (0.1.4)。§7 の 3 と P-8 は「基準値が 2 フェーズ安定した後にゲート化を審議する」とし、フェーズ9 設計 :139 が「本フェーズは 2 フェーズ目」と記録しているが、審議は行われていない |

### 0.1.4 G-4 の閾値 (依頼者裁定 2026-09-24。案 1 の p50 のみ +30% → +40% に改めて採用、案 2〜4 は提示どおり採用)

数字の出所: フェーズ10 設計 §11.10 (K=1 と K=3 の 2 run の p50 差はすべて 30% 未満 = run 間の雑音の上限として観測された値)、`docs/design/PERF_CONCURRENCY_MEASUREMENT_V0_1.md` §3 の 3 (query の p50 は K に比例。r2db-http K=1 2.67 → K=32 62.7 = 23 倍、socket 26 倍、MitateDB-http 34 倍、socket 31 倍) と同 §3 の 4 (MitateDB の cell lock は K=4 で acquire の 28〜29% が待ち (985/3530 = §2.1、1019/3530 = §2.2 の :50)、K=32 で 45%。同 §4 の (3) は同じ事実を「K ≥ 4 で acquire の 30〜45%」と書く)、直近の K=1 基準値 = フェーズ9 設計 §11.2 の「後」列 14 行 (`--warmup 20 --n 200`)。

1. **退行閾値** (P-8 の「ゲート化」の具体形): 変更セットの完了ゲートで取る K=1 の `perf_baseline.py --warmup 20 --n 200` の p50 が、同一 plug・同一 op の直近基準値の **+40% 以内** (起草時の案は +30%。run 間の雑音の上限と同水準では誤検出が出るため、依頼者裁定 2026-09-24 で +40% に改めた)、p95 が **+50% 以内**。30% は run 間の雑音として観測済みの上限である。両論 — +30% は雑音と同水準なので誤検出しうる / これより緩めると退行を見逃す。
2. **並行スケール閾値** (R-101・R-102 が「閉じた」と言える計測上の形): K=32 の `query` の p50 が K=1 の **8 倍以内** (実並行 4 相当。現状 23〜34 倍 = ほぼ直列) を両 peer の http / socket plug で満たす。 **【改訂 2026-09-28 (v1.129、依頼者裁定 2026-09-27「1〜4 すべて監督案どおりで進める」の 1)】計測器を `tools/perf_baseline.py --real-server <peer>` (composition root を別 process で起動し、K 並列の client process で測る real-server plug) に改める。理由: 従来の http / socket plug は client と server が同 process・同 GIL で、K=1 の CPU 行から出る床が 8 倍を超える (client だけで 20.7 / 10.1 倍 (socket)、HTTP も DB も無い in-process plug で 13〜15 倍。作業指示書 `docs/work-orders/WORK_ORDER_R101_SERIALIZATION_ATTRIBUTION_V1.md` §7.1)。8 倍の数字と「両 peer」は変えない。判定規則は同書 §10.1 D-16 (K=32 の 2 run とも 8 倍以内)。従来 plug の値は記録として残す (2026-09-28 時点 20.8 / 28.4 / 29.2 / 30.8 倍、設計メモ v0.3 §5)。**
3. **MitateDB の lock 待ち**: K=4 で cell lock の waits/acquire が **10% 以下** (現状 28〜29%)。
4. **`backend_calls`**: 同一 plug の版間差分が +0 を超えるときに理由が記録されていること (現行の慣行の明文化であり、閾値ではない)。

本案の閾値は完了ゲートの退行検査であって、契約が宣言する bound (limit class) ではない — §7 の 3 が「閾値を先に置かない」と述べるのは後者 (閾値が bound として機能を縛る形 (P-5) になること) についてであり、本節はその区別のもとに案を置く。

### 0.1.5 依頼者裁定 (2026-09-24。起草時は裁定待ちだった 5 件。各項の末尾に【裁定】を付す)

- **(a)** 0.1.1 の終了条件の文言 (G-2 / G-3 は依頼者の骨子どおり 1 文に束ねた。分けるかを含む)。【裁定】現行のまま (分けても検証法が同じものを 2 行に書くだけになる)。
- **(b)** 0.1.4 の閾値案 1〜3 の数値。【裁定】案 1 の p50 を +40% に改め、p95 +50%、案 2 (8 倍以内)、案 3 (10% 以下) は提示どおり採用。0.1.4 に反映済み。
- **(c)** SI-07 の r2db-api 節の証拠欠落 (0.1.3) を §8 に起票するか。対応する R は現在無い。【裁定】起票しない。CONTROL_MAPPING 形式 3.0 (`docs/design/CONTROL_MAPPING_FORM_V3_V0_1.md`。台帳行は R-103 (v1.114 で起票)) の実施で参照を引けない Evidence 主張は全件が実テスト名を引くか Status へ落ちるので、同じ変更セットで解消する。その受け入れで 0.1.3 の当該行を再実測する。
- **(d)** §7 の 3 (「閾値を先に置かない」) と 0.1.4 の関係の整理。§7 の 3 の審議が「ゲート化しない」と結論した場合の G-4 の充足形 (閾値なしで基準値が 2 フェーズ安定していること 等) も裁定対象に含む。§7 は本節では書き換えず、訂正註も足さない (裁定後に足す)。【裁定】両立。§7 の 3 が禁じるのは閾値を契約の bound として機能を縛ることであり、0.1.4 は完了ゲートの退行検査である。§7 の 3 に訂正註を足した (同日)。「ゲート化しない」案は採らない (基準値が 2 フェーズ安定しているだけでは退行を見逃す)。
- **(e)** 本節を満たした時点で残る未閉止行 (現在 35 件、うち 17 件は「着手条件: 運用開始後」。v1.105) の扱い (残置か閉止か、運用開始後の着手の可否) と、`docs/work-orders/OPERATING_CONDITIONS.md` §1.12 の 71 で「はい」と判定した検査器の穴が但し書きの「終了条件を破る欠陥」に含まれるか。【裁定】残置。閉じずに「着手条件: 運用開始後」の印のまま台帳に残し、実需の記録 (§5 フェーズ11 の実需の定義) が付いた行だけ着手可とする。§1.12 の 71 で「はい」と判定した検査器の穴 (現在 R-46 の 1 件) は但し書きの「終了条件を破る欠陥」に含める (公開化の直前に秘密が通り得る穴は G-2 の破れである)。

**但し書き (終わりに達した後の運用)**: 本節の判定対象は台帳全体 (終わったか止まったか) であり、個別行の閉止は各行の完了条件による。本節を満たした時点で台帳は完成であり、以後の台帳への起票は「実需の記録 (§3.2・§5 フェーズ11 の着手条件に当たる需要の記録)」か「本節の終了条件のいずれかを破る欠陥」に限る。

---

## 1. 現状

以下の各層は日付付きの記録であり、後の変更で書き換えない。現在地の値は `docs/work-orders/OPERATING_CONDITIONS.md` §1.8 の 55a の表の出所から読む。

### 1.0l 更新 (2026-10-03、R-42 の閉止。`docs/work-orders/OPERATING_CONDITIONS.md` §1.8 の 55)

- **期限を使い切った要求の意味論を契約 1.16.0 (従属判断 21) に定め、両 peer で決定的に拒否する形にして R-42 を閉じた。** `limits.execution_ms` は受理点から commit の開始までの待ちと文を数え、使い切った要求は次の文を発行する前に `LIMIT_EXCEEDED` / `execution_ms` で拒否され (残り 1 ms 未満は使い切り)、文ごとの bound は算出時の残りを超えず、拒否・打ち切られた要求は何も残さない (無条件義務 4 件。設計 `docs/design/EXPIRED_REQUEST_SEMANTICS_V0_1.md` §9 の依頼者確定文を逐語)。
- 共通条件 C-36 (3 vector + positive control、6 plug、port v1.22 の `hold_after_admission` と「放した後の文の数」の handle)。両 peer の検査は「次に文を発行する点」(r2db `_run` / `_transaction`、MitateDB `_execute`) に統合し、pool 待ち・接続確立の写像は時計の判定 1 本、MitateDB の schema 3 経路は store → pre_commit → COMMIT、SQLite backend に文の bound。`security/CONTROL_MAPPING.md` 3.19。
- 完了ゲート gate: 5231 passed, 2 subtests passed in 509.14s (0:08:29), judge=PASS, label r42, pg_database/pg_roles diff 0。性能差分は閾値の内側 (K=1 の p50 の最大 +11.7%・p95 の最大 +8.4%、K=32 の p50 の最大 +4.1%・p95 の最大 +3.2% (閾値 p50 +40% / p95 +50%)、backend_calls 不変)。監督裁定は依頼者指示 2026-10-03「裁定事項が出た場合は、監督推奨で進めて、後から確認」により監督推奨で進め、一覧は `docs/work-orders/HANDOVER_20261003_R42_CLOSE_FABLE.md` の「裁定」節 (依頼者の事後確認待ち)。

### 1.0k 更新 (2026-10-01、R-108 の閉止。`docs/work-orders/OPERATING_CONDITIONS.md` §1.8 の 55)

- **契約文書 (`spec/`)・base URL・key 1 本だけから要求を組めることを wire で示し、R-108 を閉じた。** 契約 1.14.0 は 12 文を足した (URL の組み立て規則 `versioning.url_composition` と credential を付けた要求の redirect を追わない規則、path の placeholder とその percent-encode、要求と成功応答の media type、応答の分類 `errors.response_classification`、capability document の `role`、前提にする外部標準、派生 catalog の項が属する surface、`operation_catalog_url` に credential を出す範囲、`version_binding` の義務 (a)(b)(c))。参照クライアント `conformance-tests/reference_client.py` が C-28 の 1 周を wire の 4 plug で port v1.21 の `wire_entry` を通して回す (共通条件 **C-35**)。`security/CONTROL_MAPPING.md` は 3.16 (§8 の R-108 行、記録ファイル)。
- 両 peer の runbook に、`operation_catalog_url` を上書きした配備に掛かる義務 (c) の 1 文を足した。`tools/deploy_smoke.py` は credential を付けた要求の redirect を追わない。socket 経路の redirect の `Location` が宣言の port を持たない件は R-121 に起票した。
- **CI は `main` への push と `workflow_dispatch` でだけ走る** (依頼者裁定 2026-10-01 (逐語): 「CI は main だけに絞ってください」。main `9be46b7` に R-108 とは別の変更セットとして入った。`docs/work-orders/OPERATING_CONDITIONS.md` §3 の 7)。

### 1.0j 更新 (2026-10-01、R-102 の閉止。`docs/work-orders/OPERATING_CONDITIONS.md` §1.8 の 55)

- **MitateDB のデータ面は application ごとに直列化されなくなり、R-102 を閉じた。** cell lock を廃止し、要求は application × role の pool から接続を借り、1 要求 = 主接続の 1 transaction とし、同じ application の要求の調停は transaction scope の advisory lock (schema 操作の直列化 lock と実体単位の共有 / 排他 lock、idempotency の per-key / 件数 lock) が process をまたいで担う。r2db は `apply_schema` が schema lock を取る。plan の前提条件の共通条件 **C-34** が両 peer でこれを固定する。契約 1.13.0 は不変、`security/CONTROL_MAPPING.md` は 3.14 (§8 の R-102 行、記録ファイル)。
- **r2db の DML の検証と `alter_field` の間の窓は開いたまま** (R-120 に起票)。MitateDB の runbook §10.10 は版 12 で not accepted (依頼者の再受理待ち)。

### 1.0i 更新 (2026-10-01、R-115 の閉止。`docs/work-orders/OPERATING_CONDITIONS.md` §1.8 の 55)

- **契約 1.13.0 (`audit.process_loss_policy`) を両 peer が宣言し、R-115 を閉じた。** 応答を返した操作の audit event と拒否の件数は、service process の突然死でも失われない (共通条件 C-33、§8 の R-115 行)。

### 1.0h 更新 (2026-09-29、R-113 の完了。`docs/work-orders/OPERATING_CONDITIONS.md` §1.8 の 55)

**§1.0g は下に残す。以下は R-113 の完了だけを足す。**

- **R-113 (multi-process worker) は閉止した。** 両 peer の data plane は `--workers N` の複数 process で動く。`requests_per_minute` は credential ごとの PostgreSQL の行 (r2db `0015` / MitateDB `0016`) で全 worker をまたいで数え、`concurrency` は host 内の全 worker で共有する slot で数える。`limit_enforcement` は、共有の仕組みが配線され、かつ `process_ceilings.data` ≤ workers のときだけ `enforced` を返す。新しい共通条件 **C-32** が両 peer でこれを固定する。契約 1.11.0 は不変、`security/CONTROL_MAPPING.md` は 3.7 (§8 の R-113 行)。
- **R-101 は開いたまま** (依頼者裁定「R-101は閉じない」)。4 worker で K=32 の `query` p50 は 1 process の約 39 ms から約 25 ms に下がったが、worker の外に直列の区間が残る (§8 の R-101 行)。
- **本番への適用は運用者の作業である。** r2db の `0015`、MitateDB の `0016` と新しい env (worker 数、slot directory、control の worker 数、MitateDB の thread limit) の配備、MitateDB の runbook §10 の再受理 (依頼者) は、この更新の時点で行っていない。 **【追記 2026-09-30 (v1.132)】** runbook §10 の再受理は同日に行った: §10.6 と §10.7 は版 6 で受理、§10.10 は版 9 で not accepted (受理は R-116 の後)。R-113 行の【追記 2026-09-30】と `docs/work-orders/WORK_ORDER_R113_MULTI_PROCESS_WORKER_V1.md` §6.3。

### 1.0g 更新 (2026-09-16、R-45 / R-46 の起票)

**§1.0f は下に残す。以下は将来残件の起票だけを足す。**

- **R-45** は MitateDB-api を `operation_depth` を宣言・強制できる platform へ更新する残件である (Mitate F9 の阻害要因)。**DSN・credential・token を出力せずに** declarations、migration、アプリケーションごとの upgrade 状態、isolated / production の組、rollback、DDL のロックと停止条件を読める運用経路が先行条件であり、状態が不明なら blocked とする。
- **R-46** は公開値スキャナの既存の弱点である。許可ホストの URL の中に deny suffix のホストを含む URL を入れ子にすると、外側の URL として 1 件に読まれ deny が効かない。

### 1.0f 更新 (2026-09-13、ファイル／バイナリ API の起票)

**§1.0e は下に残す。以下は将来残件の分類だけを足す。**

- **R-36（画像を含むファイル／バイナリの保存・取得）は未着手の候補機能である。** 現行の共通 API は `application/json` の構造化データを対象とし、任意 bytes の upload / download / metadata / delete は提供しない。JSON/Base64 は本機能の実現方法にしない。
- **候補設計は `docs/design/OBJECT_STORAGE_BINARY_API_V0_1.md` である。** application ごとの private bucket・provider identity・object-capable 実行単位による隔離、raw-byte streaming、`Content-Digest`、idempotency、削除確認、再認可、監査、object 専用の resource limit を提案している。
- **予定と順序**: まず設計レビューで公開契約・capability・error / limit vocabulary・Security Invariants の適用結果・conformance 条件を確定し、その後に両 peer の実装と provider 側の最小権限配備を行う。確定までは、この候補文書を契約、conformance tests、実装、または配備の根拠にしてはならない。

### 1.0e 更新 (2026-09-10、フェーズ10 の完了ゲートと記録。§9 の 6)

**§1.0d は下に残す。以下は §1.0d に足す分だけである。**

- **フェーズ10 (配備面の証拠、契約 1.8.0「資源制限の適用単位」) は WP-9 (記録・閉止・ハンドオーバー) の段に入った。** **正本はフェーズ10 設計 `docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md` (v1.6) と作業指示書 (v1.4) であり、本節は再導出しない。**
- **到達した状態**: **(1) 実 socket・reverse proxy 込みの plug が 2 本増え、conformance の plug は 4 → 6 になった** (`registry.json` の `adapters` 6 件、すべて `required: true`)。**(2) 新条件 C-26 が両 peer の本番 composition root を実起動し、宣言表由来の `surfaces` を serve された文書と突合して実ダイヤルし、`process_ceilings` → `limit_enforcement` の写像と F-16 の fail-fast を観測する** (`composition_roots` 2 件)。**(3) 契約は 1.8.0 (3 複製の sha256 = `ff97ddce2a209a69e819c3d36ae7870f85238afe1181cfc7db688616f54faa35`)、両 peer が 1.8.0 を宣言した。** **(4) 両 peer の HTTP handler が同期区間を threadpool へ委譲し、認証前に concurrency slot を取り、pool と PostgreSQL role の `CONNECTION LIMIT` が宣言 concurrency から導出されるようになった。**
- **開いたまま残るもの (2 件)**: **(a) C-27 (同一キー同時送信の共通条件) は `CONDITIONS.md` に declared のままである** — **WP-6d-ii (port hook `hold_after_idempotency_lookup` と `test_c27_concurrent_same_key.py`) は未実施であり、契約 1.8.0 の条件付き義務を共通 suite が観測していない。** **実装 (WP-6d-i) と両 peer の同時テストは在る。** **(b) CI の集計行が未取得である** — **GitHub の課金上限で push を停止しているためであり (台帳 L10-15)、復旧後に main の先頭で 1 回取る。** **性能計測 (WP-7) は main `ff8d232` に入り、PERF 行の記入だけが監督に残っている。**
- **本フェーズが露出させた実欠陥は 6 件で、いずれもレビューが見つけ、変異で赤を実測して閉じた** — **件数 bound の lock が deadlock する形だったこと、cell 共有接続が lock の外で他要求に奪われること、role pool が固定 4 だったこと、role の `CONNECTION LIMIT` が pool 構成に足りなかったこと、readiness probe が認証前 rate window を消費していたこと、role 名が NULL の application 行で migration 全体が rollback すること** (設計 §11.9)。**3 件は「宣言した bound が実配備で到達不能」であり、実 socket と実並行が入って初めて見えた。**
- **監督裁定は U-14〜U-22 の 9 件である** (設計 §5)。**依頼者への報告事項は U-1〜U-6 と併せてフェーズ完了報告に置く。** **R-22 (`CONTROL_MAPPING.md` の再編) は依頼者判断待ちのままである。**
- **push は停止中である** (GitHub の課金上限。依頼者確認済み)。**本フェーズのコミットとマージはすべてローカルであり、remote には出ていない。**
- **【追記 2026-09-10 (v1.11)。上の各項は書き換えていない】** **「開いたまま残るもの (2 件)」の (a) は解消した。** **WP-6d-ii を実施し (branch `phase10-wp6dii`、`d97de35` + レビュー是正 `8425ef4` + main 取り込み `05bc548`、main へのマージ `2455f96`)、C-27 は `CONDITIONS.md` で `executable` になった。** **駆動は 6 plug 全数であり (socket 2 plug は port v1.15 の hook `hold_after_idempotency_lookup` を継承する)、どの plug でも skip / xfail されない。** **したがって契約 1.8.0 の条件付き義務 `idempotency_concurrent_same_key_sends_serialized` は、両 peer について共通 suite が観測している。** **変異で赤を実測した** — key advisory lock で (i) (ii)、件数 advisory lock で (iii)、MitateDB の外側 cell lock で (i) (ii) (iii)、hook の no-op 化で保持待ちの時間切れ。**開示 1 件**: **MitateDB の PG session advisory lock は共通 suite (1 plug = 1 cell) では load-bearing にならず、非 vacuity は peer-local テスト (2 cell 構成) が担う** — C-27 行に書いた。**開いたまま残るのは (b) の CI 集計行だけである** (台帳 L10-15)。**正本はフェーズ10 設計 (v1.7) §3 D-13 の実施註 (6d-ii) / §9.1 の「8 (f) / 14 (再)」/ §11.11 である。**

### 1.0d 更新 (2026-09-08、外部レビュー 2 検証。§9 の 6)

**§1.0c は下に残す。以下は §1.0c に足す分だけである (フェーズの完了状態は §1.0b のまま)。**

- **依頼者が 2 本目の外部レビュー (2026-09-08、基準 main `b16afdd`) を提示し、監督が現物で検証した。** **依頼者裁定 (2026-09-08、逐語)**: 「フェーズ 10 に組み込めるのであれば組み込んでください。」
- **指摘 5 件はいずれも事実として裏付けられた。**
  - **(1) 同一 idempotency key の同時要求で二重実行できる。** 両 peer とも照会が lock を持たず、`INSERT ... ON CONFLICT (idempotency_key) DO UPDATE` の後追いに委ねている (r2db `r2db-api/src/r2db_api/postgres.py:1188` の素の SELECT と `:1223` の store、MitateDB `MitateDB-api/src/mitatedb_api/backend_postgres.py:1697` の store と自己 commit の別トランザクションで走る照会)。**監督は使い捨ての PostgreSQL 16 で再現した** — read committed で同一キーの 2 要求が両方とも照会結果 `None` を読み、**効果行が 2 件 commit され、digest が異なっても `CONFLICT` にならず後着の digest が上書きした**。異キー 2 件の `idempotency_entries` 件数検査 (`SELECT count(*)` の check-then-write) も両方が同じ値を読んで両方 insert した。**再現手順とスクリプトは監督保管であり、一時 DB は drop 済み、リポジトリは無変更である。** **契約 1.7.0 の穴ではなく、実装と検証の穴である** (`spec/data-service-api.v1.json` の `idempotency.record` は「二度実行しない」と定めており、同時送信もその射程にある)。**起票先は R-24。**
  - **(2) MitateDB が `budget: {}` を digest から落とす** (`MitateDB-api/src/mitatedb_api/cell.py:2702` の `if budget:`。r2db は `r2db-api/src/r2db_api/service.py:1237` で `if budget is not None:`)。契約 1.7.0 は budget も再送一致の対象と定めているので MitateDB 側の不具合であり、plan digest にも同じ影響が及ぶ。**同型性 pin は helper 名が違う (`plan_request` / `digest_request`) ため拾えなかった。** **起票先は R-25。**
  - **(3) CI が `skipped` / `xfailed` = 0 を強制していない。** `.github/workflows/ci.yml` の集計 step は 4 数を記録するだけで、比較 job は 3.11 と 3.12 の一致だけを見る。**`docs/work-orders/OPERATING_CONDITIONS.md` §1.3 の 22 が合格条件として定めている値が、CI では検査されていない。** **起票先は R-26。**
  - **(4) `sweep_orphans` の pid 検査。** レビュアーが見た版は未対策だが、**現在の WP-3 作業ツリーでは pidfile の pid の cmdline に harness の prefix marker が含まれるときだけ signal する形になっており、所有者検査は既に在る** (監督裁定 2026-09-08)。**残る穴は `pid <= 0` の明示 guard が無いことだけである** (`os.kill(0, …)` はプロセスグループ、`os.kill(-1, …)` は全プロセスを指す。marker 検査が先行するので実害経路は無い)。**起票先は R-27。** **【状態 2026-09-08】WP-3 は main `6055c69` にマージされ、本項は main に対する follow-up として実施した (branch `phase10-wp3f` の `ea237e5`)。**
  - **(5) 正本文書の矛盾が 2 件残っている。** `r2db-api/README.md:158` の「VPS に PostgreSQL 未導入」は WP-0 (R-21) の書き直しの取りこぼしであり、`docs/work-orders/DEPLOY_PHASE6_20260904.md` の項 9〜12 は 2026-09-05 に r2db Stage 1 を VPS へ初回導入し外部到達を確認したと記録する。`docs/work-orders/HANDOVER_20260908_FABLE.md` §1 の「フェーズ7 の残は WP-9 だけ」は、同日後刻の `docs/work-orders/PUBLICATION_GATE_20260906.md` §3.2 (手順 0〜6.5 実施済み、visibility 切替のみ依頼者判断で保留) と食い違う。**レビュアーの構造的な指摘 (現在地を入口となる文書から正確に判断できない) を含めて、起票先は R-28。**
- **設計課題として妥当と評価したものは 4 件であり、いずれもフェーズ11 送りである** — **R-29** (両 peer の最低共通機能プロファイルと単一シナリオ検査)、**R-30** (SI-00 の境界と 1 プロセス複数 Application DSN)、**R-31** (配備全体の資源保護)、**R-32** (検証 seam と同型性の分離)。**「無状態 plan と単一要求の原子性を基本方針として保つのは良いが、長時間処理や bulk を一律排除する根拠にはしない」というレビュアーの締めには同意する** — `CLAUDE.md` の「Security Invariants are not a feature gate」と同旨である。
- **フェーズ9 は完了のままである。** **フェーズ9 が示したのは「逐次経路の再送安全性」であり、「同時送信の再送安全性」はフェーズ10 WP-6d が示す。** **これは完了の取り消しではなく、完了が覆う範囲の明示である** (監督裁定 2026-09-08。フェーズ10 設計 §5 U-7 / U-8)。 **【追記 2026-09-08 (v1.9)】** **同時送信の再送安全性は WP-6d-i で実装済みである** (両 peer の backend lock + in-memory lock + peer-local の同時テスト。下記の実施行)。**契約で検証可能になる — すなわち共通 suite が新条件 C-27 として 4 plug で駆動する — のは WP-6d-ii であり、C-27 は契約 1.8.0 の条件付き義務 `idempotency_concurrent_same_key_sends_serialized` の実行可能な条件である** (フェーズ10 設計 §3 D-13、§5 U-8 / U-9)。**フェーズ9 の完了状態はこの追記でも変わらない。**
- **履行状況の補正**: **WP-5a は未コミットの変更ではなく branch `phase10-wp5` に commit 済みである** (`654e23e`、ツリー clean。root suite の単独ゲート待ち)。**【状態 2026-09-08】その後、別セッションが WP-3 を main `6055c69` に (branch の実装コミットは `8d39260`。adapter port は `CONFORMANCE_ADAPTER_V1.md` v1.14、`ci.yml` に nginx 導入と socket 残骸検査)、WP-5a を `654e23e` の時点で main `3d7f823` にマージした** — **U-9 の追補 `73adbda` はそこに含まれないので、次のゲート束でマージする。**
- **次の一手**: **小修正の束 WP-1c (R-25 / R-26 / R-28) を即時に入れ、同一キー直列化 WP-6d-i を並行で着手する** (フェーズ10 設計 §5 U-7〜U-13、同 §3 D-13、作業指示書 §2)。
- **【ゲート 2026-09-08】** ゲート 1 (main `ec15c74`) は `1 failed, 2852 passed` — 赤は負荷依存の timing テスト 1 件 (§8 **R-34**)。単独で緑を 3 回確認したうえで、他の pytest が 0 件の条件を機械的に待ってからゲートを再実行する。 **【実施 2026-09-08 (v1.9)】R-34 は実施済みである** — **branch `phase10-r34` の `12a7bd7`** (両 peer の `tests/test_audit_query.py` の `_run_delayed_tx_vector` を Event 同期に改めた。writer が INSERT の後に signal し、probe は INSERT 時刻から `lag_s + 0.2` 待って走り、tx が open であることを assert し、`finally` で writer を解放する。**即時 commit の変異で両 peer `2 failed`**、**ファイルごとに 3 回連続緑で r2db `75 passed` / MitateDB `62 passed`**) と **`5a59002`** (**`12a7bd7` が巻き込んだ変異検査用の scratch 複製 `r2db-api/tests/test_zzr34mutationscratch_audit_query.py` の削除**)。**巻き込みは監督が実装担当の作業中の worktree で `git add -A` を使ったために起きた過程誤りであり、再発防止として `docs/work-orders/OPERATING_CONDITIONS.md` §1.1 に条項 12a を足した** (フェーズ10 設計 §11.5)。**R-34 は WP-6d-i のゲート束で main へ入る** (`685ebfa` が `phase10-wp6d` と統合済み)。
- **【新起票 2026-09-08 (v1.9)】WP-6d-i のコードレビューが、両 peer に在る既存の欠陥を 1 件見つけた** — **フェーズ9 R-2 の nullable 違反走査が `LOCK TABLE ... IN SHARE MODE` の後に同一トランザクションで `ALTER TABLE` を打つので、同じ表へのキー無しスキーマ変更 2 件が相互に待ち、PostgreSQL の deadlock detector が一方を中断するまで解けない。** **起票先は §8 の R-35、行き先はフェーズ10 内の小さな Class B の WP「WP-R35」(`SHARE ROW EXCLUSIVE` への変更と 2 スレッドテスト。worktree `phase10-r35`、実施済み、コミット `46b081a` + レビュー是正 `7ead163` (Opus レビュー accept)) である** (フェーズ10 設計 §3 **D-15**、同作業指示書 WP-R35)。**フェーズ9 R-2 の完了は取り消さない** — **走査が依拠する性質 (行の書き手を排除する) は `SHARE ROW EXCLUSIVE` でも保たれ、直すのは lock mode 1 行である。**
- **【状態 2026-09-08】本レビューの取り込みは同一セッション内で実施中である。** **現時点で在るコミットは `73adbda` (WP-5a 追補、U-9。branch `phase10-wp5`)、`ea237e5` (WP-3 follow-up、U-12。branch `phase10-wp3f`)、`5944013` (WP-1c、U-11。branch `phase10-wp1c`。Opus のコードレビューは「accept with fixes」で、確定コミットは `2431e93`) である。** **WP-6d-i の確定コミットは `968884f` (R-35 統合後の AST pin 更新まで含む branch 末尾。再レビュー accept、replay 経路の reap テストを追加) である。** **いずれも次のゲート束で main へマージする。** **【更新 2026-09-08 (v1.9)】WP-6d-i は実装済みである** — **branch `phase10-wp6d` の実装 `21cc8fb`、Opus のコードレビュー 1 巡目「accept with fixes」(指摘 F1〜F8) の是正 `6a3453d`、R-34 の branch `phase10-r34` との統合 `685ebfa` (再レビュー accept)。main へのマージは `4e1020a` (WP-6d-i + R-34 + R-35 の束) + 直後の pin 修正 `ee80c97` (`test_limit_class_vocabulary.py` の `ResourceLimitError` 呼び出し数 33 → 35。F2 の 2 箇所分。ゲート 3 が検出し、ゲート 4 で再確認) である。** **実現の形は peer で分かれた** — **r2db は裁定どおり transaction-scoped の `pg_advisory_xact_lock` (key 単位 / 表単位)、MitateDB は catalog 読みが同じ接続の途中で自己 commit する構造のため SESSION advisory lock を書く側の接続で取り `finally` で解放する形である** (**同じ必須の安全結果を platform ごとの統制で満たす形。`CLAUDE.md`**)。**変異 5 種で赤を実測し、監督の raw-SQL 競合スクリプトは新しい SQL で 25 反復とも二重実行 0 件である。** 詳細はフェーズ10 設計 §3 D-13 の実施註と §11.4。 **WP-1c のコードレビューは本レビューとは別の指摘を 1 件出した** — **MitateDB `ApplicationCell.create_collection` が受け取るだけで読まない `destructive` 引数と、HTTP 層が同じ値を `digest_extra` に畳み込む非対称である** (**現時点で渡す経路が無いので実害は無い**)。**起票先は R-33、行き先はフェーズ11 である。**

### 1.0c 更新 (2026-09-08、外部レビュー検証。§9 の 6)

**§1.0b は下に残す。以下は §1.0b に足す分だけである (フェーズの完了状態は §1.0b のまま)。**

- **依頼者が提示した外部レビュー (2026-09-08) を監督が現物で検証した。** 検証は root suite の単独実行 (`2807 passed` / 0 failed、収集 2807)、契約複製 3 本の sha256 一致、catalog 鮮度、`check_doc_refs` 0 件、現行ツリーの value scan 0 件、`pip check` 0 件、test DB / role 残骸 0 件で、レビューの数値と一致した (警告は 1 種 × xdist worker 5 件)。
- **指摘は事実として裏付けられた。** 是正の起票先は **§8 の R-17〜R-23** である。**訂正 2 点**: `CONTROL_MAPPING.md` で最長の行は SI-08 ではなく **SI-14 (26,012 文字)** である (SI-08 は 5,797 文字)。警告の出現数は 1 件ではなく **5 件** (同一 1 種)。
- **追加で見つかったもの 2 点**: r2db の配備 runbook も素の `pip install` である (R-19 に含めた)。開発機 `.venv` の psycopg は 3.3.4 で `constraints.txt` の 3.3.5 と一致しない (`OPERATING_CONDITIONS.md` §2 の 16)。
- **閉じた**: **R-17** (公開ゲート実施記録 `docs/work-orders/PUBLICATION_GATE_20260906.md` を `966e0af` から復元。再発防止の機械検査は開いたまま)。
- **次の一手**: **フェーズ10 着手前に R-21 (正本文書の陳腐化) を是正し、フェーズ10 設計で R-18 の裁定を仰ぐ。** R-19 / R-20 はフェーズ10 の範囲、R-22 / R-23 は依頼者判断待ち。

### 1.0b 更新 (2026-09-08、フェーズ9 完了。§9 の 6)

**§1.0 (2026-09-07 時点) と §1.1 は下に残す。以下が現在形である。**

- **フェーズ9 は完了した (2026-09-08)。** main の最新 merge は **`85e99fa`** (版フリップの pair-closing)。**その直前 2 つが `3efa79f` (r2db の版フリップ) と `ab89f64` (MitateDB の版フリップ) であり、3 つの merge の間に他のコミットは 1 つも挟まっていない。** 完了ゲート (root suite 単独実行) は ****`2807 passed, 5 warnings in 323.70s (0:05:23)`** (failed 0 / xfailed 0 / skipped 0 / error 0 — 集計行にいずれの語も無い。終了コード変数は zsh の `pipestatus` 差で取得漏れ、判定は集計行による。`pg_database` 22 → 22、`ps` で他の pytest 0 件、2026-09-08 05:26〜05:32 JST、main `85e99fa` と同一 tree)** (failed 0 / xfailed 0 / skipped 0)。
- **契約は 1.6.0 から 1.7.0 になった。** 契約 JSON と両 peer の packaged 複製 2 本の sha256 は 3 本とも **`1651795480511be5476c554ea95dda67152fe2512beedee352049d17c19afcc4`** である (フェーズ8 の `968d3c72…45e6` から動いた)。**両 peer が 1.7.0 を宣言する** — `r2db-api/src/r2db_api/service.py:942` / `control_plane.py:731`、`MitateDB-api/src/mitatedb_api/cell.py:3852` / `control_plane.py:1424`。
- **能力は 11 種 → 14 種**(`constraint_declarations` / `dry_run` / `request_budget` を新設し、既存の `idempotency` を両 peer で `enabled` にした)、**limit class は 16 種 → 17 種**(`enum_members`)、**error code は 17 種のまま**、**共通条件は C-00〜C-19 の 20 件 → C-00〜C-25 の 26 件**であり、**新 6 条件 (C-20〜C-25) はすべて four adapters で実行可能**である。
- **エージェントの 1 周 (P-2) が宣言だけで閉じた。** **R-2** 制約宣言 (`field_constraints` の enum / nullable、新設 `alter_field`、同じ版で catalog が報告)、**R-3** 検証エラーの固定 details 語彙 (`violated_declaration` は 11 語の閉じた語彙、`field` は要求内パス)、**R-4** `dry_run` と無状態 plan (token = `"<sha256hex>.<application schema revision>"`)、**R-5** idempotency の両 peer 実装、**R-6** request budget (配備値を下回る方向にのみ効く)、**R-7** 成功応答の `request_id`、**R-8** 派生の操作カタログ (`tools/contract_catalog.py` + `spec/OPERATION_CATALOG.json`、19 行、再生成一致テスト) と `versioning.obligations`。
- **R-10 (B) も同梱で閉じた。** `spec/CONTRACT_HISTORY_MANIFEST.json` は 29 エントリ (剥離 26 / `unstripped` 3) で、剥離量は 1,812 バイト (#18 の語改訂 +2 を差し引いて正味 -1,810)。**逆適用の deep-equal は 26 値中 24 値が byte 一致し、残り 2 値の差は意図した規範文改訂 (U-8 #28) だけである。** **契約 JSON 全体は 1.7.0 の新設分により 77,119 → 126,516 バイトに増えた** — 剥離で短くなったわけではない。
- **閉じた台帳項目**: **L9-2b** (MitateDB が `PRECONDITION_FAILED` を発行するようになった)、**L9-5** (剥離量の実測を記録)、**L9-7 (= L7-8)** (`idempotency` の肯定枝が 4 plug で load-bearing になった)、**L9-8 (= L8-4)** (R-10 (B) の 5 段手順)、**L9-9 (= L8-9)** (`versioning.obligations` + register 2 本。ただし実施形は「散文を残して機械可読な索引を並置する」であり、起票時の想定とは違う)。
- **開いている台帳項目**: フェーズ9 側は **L9-1** (`schema_objects` の数え方の不一致)、**L9-2a** (MitateDB は `IDENTIFIER_INVALID` を発行しない)、**L9-3** (r2db に limits の env override が無い)、**L9-4** (`operation_catalog_url` を両 peer が宣言しない)、**L9-10** (無条件義務が累計 4 件になった)、**L9-11** (`result_items` の意味が peer で揃わず C-24 で駆動しない)、**L9-12** (`example_profile` が全 class を網羅しない)、**L9-13** (idempotency の replay と `evaluation_order` の関係)、**L9-14** (記録する応答の内部表現が peer で異なる)、**L9-15** (C-25 (3) の監査行照合が共通 suite で駆動されない)。**フェーズ7 / 8 側は §1.0 のまま** — **L7-2** (実 socket HTTP plug、フェーズ10)、**L7-19 / L8-2** (上流待ち)、**L6-5a** (フェーズ10)、**L8-5 / L8-6 / L8-10 / L8-11 / L8-12 / L8-13**。
- **フェーズ7 の残は依然として WP-9 (公開ゲート) だけであり、着手条件は依頼者の実行合図のみである。** **フェーズ9 は `tools/rewrite_hash_refs.py` を触っていない** (触るファイルの重なり 0)。
- **次の一手**: **WP-9 (依頼者の合図待ち)** と **フェーズ10 (L7-2 / L6-5a)**。**性能基準値は本フェーズで 2 フェーズ目の差分が付いた** (フェーズ9 設計 §11.2) ので、**フェーズ10 の完了ゲートの後に §7 の 3 が言う「退行のゲート化」を審議できる。**

### 1.0 更新 (2026-09-07、フェーズ8 完了。§9 の 6)

**§1.1 (2026-09-06 時点) は下に残す。以下が現在形である。**

- **フェーズ8 は完了した (2026-09-07)。** main の最新 merge は **`f4635ed`** (WP-1 = L7-1 + port v1.12 + L7-21)。完了ゲート (root suite 単独実行) は **`2340 passed, 5 warnings in 349.31s (0:05:49)`**、**failed 0 / xfailed 0 / skipped 0**。
- **契約は 1.6.0 のまま 1 バイトも動いていない。** 契約 JSON と両 peer の packaged 複製 2 本の sha256 は 3 本とも `968d3c72…45e6` である (フェーズ8 設計 §11.1)。**能力 11 種、error code 17 種、limit class 16 種、共通条件 C-00〜C-19 の 20 件が全件 four adapters で実行可能**という状態も変わらない (新しい共通条件は足していない)。
- **宣言した bound が全 peer で実効になった (G-2 の土台)。** **L7-1 が閉じた** — MitateDB の application plane が `execution_ms` (`reference_wall_clock`) / `concurrency` / `requests_per_minute` / `operation_depth` と in-process の `request_bytes` を実際に強制し、**C-05 V3 の `xfail(strict=True)` は 9 → 0 になった**。**`operation_depth` は in-process / HTTP の両面で `enforced` であり、非対称は残っていない。**
- **`concurrency` が共通 suite で初めて駆動されるようになった。** **port は v1.12** — `hold_in_flight` (in-flight 保持 primitive、4 plug すべてが実装、待ち上限 30 秒) と、要求側の optional フィールド (`limit` / `extra_predicates`) が入った。**L7-21 が閉じた** — V2 の除外判定は peer 名固定から能力判定になり、**`test_c05` の `adapter.name` 読みは allowlist 3 行だけである** (AST 走査で固定)。
- **CI にテスト総数の下限が入った (R-9)。** `conformance-tests/COLLECTION_FLOOR` = **2340** (フェーズ8 のゲート時実測)。検査は `tools/check_collection_floor.py` で、CI の 3.11 / 3.12 の両 job が pytest の前に走らせる。**減少は明示の更新コミット無しに赤である。** **L7-23 (register テストの収集 0 件ガード) も閉じた。** **CI の `conformance` job には `timeout-minutes: 30` が入った。**
- **`spec/` に provenance companion が入った (R-10 (A))。** `spec/CONTRACT_HISTORY.md` が **29 個の JSON パス anchor** を持ち、各 anchor が値の全文の逐語複製・該当する subordinate ruling・導入版を記録する。**契約 JSON は 0 バイト動いていない。** 常設スキャナと companion の anchor 集合の一致、引用の byte 一致、導入版の照合 (17 件) を register テスト 7 本が固定する。
- **運用項目が揃った (R-11)。** 両 peer に **`ops verify-declarations`** (F 番号ごとの固定終了コード、同型) が入り、`tools/deploy_smoke.py`、`docs/ops/BACKUP_RESTORE_R2DB.md` (実証記録付き)、argv secret の常設静的検査が入った。**provision script の psql argv から secret が消えた** (6 件 → 0 件、`\getenv` + `ON_ERROR_STOP`)。**L7-18 は閉じた。L7-19 は撤去条件未達のまま据え置き** (上流の Starlette 待ち)。**L7-22 は起票時点で既に充足していたことが判明し、記述訂正で閉じた。**
- **性能基準値がある (R-12、G-4 の土台)。** `tools/perf_baseline.py` と、**4 plug × 3 op (`query` / `mutate` / `batch`) = 12 行 + MitateDB 2 plug × `cross_entity` = 2 行、計 14 行**の基準値がフェーズ8 設計 §11.2 に記録された (`--warmup 20 --n 200`、`commit=3c85e96-dirty`)。**閾値は置いていない** (P-8)。**この基準値が §7 の 3 が言う「2 フェーズ安定」の起点である** — フェーズ9 と フェーズ10 の完了ゲートが同じ形で差分を添えた後に、ゲート化を審議する。
- **フェーズ7 の残は WP-9 (公開ゲート) だけであり、着手条件は依然として依頼者の実行合図のみである。** フェーズ8 とは触るファイルが重ならなかった。
- **開いている台帳項目**: **L7-2** (実 socket HTTP plug、フェーズ10)、**L7-19** (上流待ち)、**L6-5a** (`surfaces` の DB 側単一真実、フェーズ10)、および フェーズ8 が起票した **L8-2 / L8-3 (閉) / L8-5 / L8-6 / L8-10 / L8-11 / L8-12 / L8-13** — 詳細はフェーズ8 設計 §10。

### 1.1 現状 (2026-09-06 時点。§1.0 が上書きする)

- **契約**: 1.6.0。能力 11 種、error code 17 種、limit class 16 種、共通条件 C-00〜C-19 の 20 件は**全件が共通 suite で実行可能** (four adapters)。
- **フェーズ7**: 7-A (WP-1〜3) と 7-B の WP-4〜8 は main マージ済み (第 14 次引き継ぎ = `docs/work-orders/HANDOVER_20260906_FABLE.md`)。**残るのは WP-9 (公開ゲート) だけで、着手条件は依頼者の実行合図のみ**。
- **台帳の最優先候補**: **L7-1** (MitateDB application plane の `execution_ms` / `concurrency` / `requests_per_minute` / `operation_depth` の 4 class の実 enforcement + concurrency probe の port primitive。`operation_depth` は WP-4 の実測で `unavailable` と確定)。C-05 V3 の `xfail(strict=True)` 9 件が撤去の合図。
- **第 14 次引き継ぎ §4-2 で開いている項目**: L7-2 (実 socket HTTP plug)、L7-18 (`ops verify-declarations` が両 peer に無い)、L7-19 (上流 DeprecationWarning の狭い ignore、撤去条件未達)、L7-21 (C-05 V2 の除外判定が peer 名固定。port v1.12 で能力判定へ)、L7-22 (現行行から落ちた台帳 ID 2 件)、L7-23 (register テストは単独実行で緑にならない。収集 0 件ガードが未設置)。
- **契約済みだが両 peer 未実装の能力**: `idempotency` (両 peer `unavailable`、L7-8)、`best_effort_transactions`。
- **既知の構造課題**: `surfaces` の 2 プロセス間ドリフト (L6-5a、手当ては Q4 と同じ DB 側単一真実)、実 socket HTTP plug の不在 (L7-2)、r2db に宣言検証の終了コード付き ops が無い (L7-18)。
- **性能**: 計測ハーネス・基準値ともに無い。
- **契約 JSON の可読性**: `versioning` だけで約 11.6k 字、各所に「Since 1.x.0 (subordinate ruling …)」の経緯文が同居する。WP-7 が行った現行/履歴の分離は `CONTROL_MAPPING.md` と `CONDITIONS.md` のみで、**契約 JSON は未分離**。
- **CI**: 3.11 / 3.12 の集計 4 数の一致は検査するが、**テスト総数の下限や前回比の減少は検査しない**。

---

## 2. 評価した外部提案

2026-09-06 に依頼者から 2 本の提案が示された。本節は要旨のみ。判定と理由は §3、却下は §6。

- **提案 I** (5 項目): A サンドボックス/dry-run、B バッチ照会と出力形式切替、C LLM 向け構造化エラー、D フィールドのセマンティクス、E topology 健全性と監査ストリーミング。
- **提案 II** (15 項目 + 基盤 9 項目): 操作カタログ/wire schema、plan/dry_run/apply、全 mutation idempotency、request budget、非同期 job、migration planner、change feed、snapshot/clone、query explain、aggregation、bulk ingest/export、関係モデル、制約付き credential 委任、policy simulation、応答横断の相関 ID。基盤 9 項目は §3.3。

提案 II は本リポジトリを読んで書かれており、基盤 9 項目のうち 6 件はフェーズ7 と台帳の内容と独立に一致した。提案 I は契約の記法 (`code` / path 様式) や SI の番号 (SI-04 の引用) が原典と合わず、採用する項目は契約本文から設計し直す。

---

## 3. 判定の総括

### 3.1 採用 (行き先はフェーズ番号と台帳 ID)

| 提案 | 判定の形 | 行き先 |
|---|---|---|
| I-C / II-15 構造化エラー | VALIDATION_FAILED 等に**固定 details 語彙** (field / declared_type / observed_type / violated_declaration)。`suggested_fix_action` と `valid_sample` は外す (§6) | フェーズ9 **R-3** |
| I-D フィールドのセマンティクス | 説明文ではなく**サーバが強制する制約** (enum・nullable) を schema 操作に足し、**同じ版で** catalog に返す (L6-6) | フェーズ9 **R-2** |
| I-A dry_run / II-2 plan | 新 endpoint ではなく既存 request の `dry_run` フィールド。plan は **request digest + schema revision の無状態トークン**。両 peer とも「実行して rollback」で同型実装 | フェーズ9 **R-4** |
| II-3 idempotency | **契約済み能力の実装** + 契約追記 (body digest 結合、同一 key 異 body の拒否、結果再取得、cross-entity/schema への適用、監査相関) | フェーズ9 **R-5** |
| II-4 request budget | 配備上限を**下回る方向にだけ**効く要求単位の予算。既存 limit class の部分集合から始める | フェーズ9 **R-6** |
| II-15 相関 ID | 成功応答への `request_id` 追加 (閉じた schema への optional 追加、minor 版) | フェーズ9 **R-7** |
| II-1 操作カタログ / wire schema | 契約 JSON から**派生**する機械可読の操作カタログ + 再生成一致テスト。OpenAPI は非正本のまま | フェーズ9 **R-8** |
| II-14 policy simulation | dry_run の認可判定として R-4 に統合 | フェーズ9 **R-4** |
| II 基盤: テスト総数の消失検知 | CI に下限 (前回 main の集計) を置く | フェーズ8 **R-9** |
| II 基盤: 現行仕様と履歴の分離 (契約 JSON) | WP-7 と同じ companion 方式を契約 JSON に適用 | フェーズ8 **R-10** |
| II 基盤: resource limit の全 peer 実効化 | = L7-1 | フェーズ8 **L7-1** |
| II 基盤: 実 socket HTTP adapter | = L7-2 | フェーズ10 **L7-2** |
| I-E topology 健全性 | 相互ダイヤルではなく **L6-5a の手当て** (`surfaces` を DB 側単一真実へ) | フェーズ10 **L6-5a** |
| II 基盤: smoke test / backup-restore 実証 / argv 検査 | r2db 実装内の運用項目 | フェーズ8 **R-11** |

### 3.2 保留 (実需の実証を着手条件とする)

| 提案 | 契約上の入口 | 主な設計制約 |
|---|---|---|
| II-5 非同期 job | CCR-09 (「long-running job 実装時に状態遷移・cancel・expiry を追加」) | credential revoke 後の継続規則は SI-13 の新しい面 |
| II-7 change feed (pull 型) | 1.4.0 の audit cursor と同じ語彙 (opaque cursor、全順序、retention) | 第 2 の耐久ログを両 peer に持つ。retention は安全上必要な bound |
| II-10 aggregation | `allowed_query_operators` の拡張 | 有限演算子集合。group 数の limit class 追加 |
| II-13 credential 委任 | CCR-11 / `lifecycle.user_session` | entity/operation allowlist と有効期限まで。row scope は述語の永続化になり別格 |
| II-11 bulk ingest/export | `best_effort_transactions` (契約済み未実装) | resumable upload は往復をまたぐ状態 (P-1) に当たるので不可。chunk 単位の原子性のみ **【追記 2026-09-21】高速化案 9 (一括挿入の `COPY` / `executemany`) は本行に含める** (依頼者指示 2026-09-21 の高速化案の検討)。新しい機能なので高速化としては起票しない。 |
| II-6 migration planner | R-2 の制約宣言と R-4 の dry_run の後 | desired-state 差分。breaking 分類は契約に無い概念 |
| I-B / II-12 entity 横断照会・関係モデル | CCR-15 と同型の `ScopedQueryRequest` は小さい。**関係モデルは 2.0 級** | subgraph fetch は関係モデルが先 |
| II-8 snapshot/clone | data plane の sandbox は却下 (§6)。**control plane の application lifecycle (snapshot から新 Application)** なら SI-01 に乗る | 優先度低 |
| II-9 query explain | CCR-01 の「表現力不足の実証」 | SQLite / PostgreSQL / in-memory で planner が異なり、共通の意味を持たせられない |
| (高速化案 7) keyset ページング (依頼者指示 2026-09-21 の高速化案の検討) | entity query の paging の意味 (現行の方式は着手時に確認する) | 深いページの速度のための変更でも、cursor の意味と順序の保証は共通契約の変更になる (版数の更新) |
| (高速化案 8) 宣言に基づく索引の自動作成 (依頼者指示 2026-09-21 の高速化案の検討) | collection / field の宣言 | 索引の作成は schema 操作であり、lock・所要時間・容量の bound (SI-08) と両 peer の同じ結果が要る |

保留項目は**再提案を歓迎する**。着手条件は「公開後の実利用で、現行契約では表現できない要求が記録されたこと」(CCR-01 の再検討条件) とし、記録の置き場は本書 §8 の台帳とする。

**【追記 2026-09-23 (v1.108)】実需の定義 (依頼者 2026-09-23)。** 上の段落の着手条件「公開後の実利用で、現行契約では表現できない要求が記録されたこと」は、リポジトリが private でクライアント通知も送らない現状では、外から実需が届く経路が無い。そこで本項と §5 フェーズ11 の着手条件にいう**実需**とは、次のいずれかとする。**(a)** MitateDB-api の消費者である **Mitate リポジトリ** (Mitate 本体) の正本文書 — 設計 (`docs/design/`)、作業指示書・引き継ぎ書 (`docs/work-orders/`)、残件索引 (`docs/remaining-work-index.md`)、決定 (`decisions/`)、Primitive 候補 (`primitives/CANDIDATES.md`) — に記録された、data-service-api の現行契約では満たせない要件。**(b)** 依頼者が本書 §8 の台帳に記録した要件。Mitate の文書は事実として引用するだけであり、本書の変更で Mitate 側の文書は編集しない。r2db-api 側の消費者が現れたときは、その消費者の正本文書を同じ規則で (a) に加える。

**突合表 (2026-09-23 時点。explorer の探索結果を監督が引用箇所を再読して確定した。判定の語: 充足 = (a) の要件が記録され、現行契約または現行 peer で満たせない / 部分的 = 近い記録はあるが機能そのものの要件ではない、または Mitate 側で解決済み・要求しないと明記 / なし = 記録なし。ファイルはすべて Mitate リポジトリ内の相対パス。)**

| 保留項目 | 判定 | Mitate の記録 (file:§ と要旨) |
|---|---|---|
| II-5 非同期 job (CCR-09) | なし | 該当なし (「非同期」の言及は Agent 層の LLM 呼び出しの話のみ。`docs/design/agent-pull-context.md` の「捨てた案 (i) 非同期化」等) |
| II-11 bulk ingest/export | 部分的 | `docs/work-orders/mitate-application-data-service-client-phase-b-requirements.md` §12 (i): `cross_entity_mutation` の batch 上限 100 (`batch_items`) に対象 N ≥ 50 の発火が当たる実測 (2026-09-03)。`docs/design/contract-v0.22.0-scheduled-action-target-ceiling.md` §1・§10 D8・§19 の trigger 5 / 13 / 15: 上限 40 を Mitate 側で pin し、「規模の実需で上限を上げるとき」を将来の trigger として記録 (まだ来ていない)。一括投入・export そのものの要件は無い |
| II-10 aggregation | 部分的 | `decisions/DM-0021-declarative-aggregation.json` の review_triggers 末尾「Aggregation must push down to the Data Service once Phase B lands」。一方 Phase B 後の `docs/work-orders/mitate-application-data-service-client-phase-b-requirements.md` §7 の 3「集計 (v0.8.0) は client 側計算: Data Service 契約に集計はなく、要求もしない」、`docs/work-orders/mitate-application-data-service-client-phase-b.md` §1 D4 (scoping 委譲のみ、集計は Application 層)。同 `docs/work-orders/mitate-application-data-service-client-phase-b-requirements.md` §12 (e) 業務 field への filter/sort 委譲は「未着手」の将来最適化 |
| II-7 change feed | 部分的 | `docs/design/contract-v0.21.0-audit-deepening.md` §7 の 7-3-a: 監査の keyset paging は共通 spec の `lt` / `desc` で足り「`data-service-api` は 1 バイトも変わらない」。同 §12 に「`data-service-api` 側の cursor 語彙との整合」が採否未定の trigger として残る。変更フィードそのものの要件は無い |
| II-13 credential 委任 (CCR-11) | なし | 該当なし。`architecture/DATA_SERVICE_BOUNDARY.md` (Mitate side must not depend on: direct database credentials) と `docs/design/governance-wrapper-hosting.md` §4 の 1 は逆に DB credential を渡さない境界を明記 |
| II-6 migration planner | なし | 該当なし (`dry-run` の言及は R-45 の platform upgrade 手順のみ) |
| I-B / II-12 関係モデル | なし | `primitives/reference-expansion.md` §Extension limits「No filter or sort over expanded values … is a join」、`docs/design/contract-v0.24.0-concurrence.md` §1-3・§Out of Boundary (汎用 join は non-goal)。Mitate 自身の設計判断であり、data-service-api への要件ではない |
| II-8 snapshot/clone | なし | 該当なし |
| II-9 query explain | なし | 該当なし |
| (高速化案 7) keyset ページング | **充足** | `docs/work-orders/mitate-application-data-service-client-phase-b-requirements.md` §3「offset の扱い」の 2「将来要求として登録済み: cursor pagination のサーバ側実装 (サーバ側台帳へ)」、同 §12 (f)「cursor 走査 … 未着手 — サーバ側 cursor 実装待ち」、`docs/work-orders/mitate-application-data-service-client-phase-b.md` §1 D4 (MitateDB は `next_page` を常に null で返し、上限到達時は正直拒否)。現物 (2026-09-23): MitateDB-api は `next_page` を常に `null` で返す (`MitateDB-api/src/mitatedb_api/http.py`:675)。Mitate の要件は cursor 走査であり、keyset との対応は着手時に確認する |
| (高速化案 8) 索引の自動作成 | なし | 該当なし |
| R-36 ファイル/バイナリ | 部分的 | `docs/remaining-work-index.md` §将来設計・保留「添付ファイル・画像 — F2 とは別工程として保留」、`docs/design/agent-entry-record.md` §6.1 (アップロード・原本の保存方式は添付機能側で設計)。data-service-api への具体的な要件は未確定 |
| R-43 行・列セキュリティ | 部分的 | `primitives/CANDIDATES.md` の Primitive 候補 24 (field 単位の読取投影) と 25 (集団所属を認可属性に)。いずれも採否未定で、Application / 契約層での判定を前提に書かれている。`decisions/DM-0021-declarative-aggregation.json` の review_triggers「Read authorization gains per-field or row-level rules」。(b) としては R-43 行自体に依頼者の要求 (2026-09-15) が記録済み |
| R-29 最低共通機能プロファイル | **充足** | `docs/design/contract-v0.26.0-attributed-append-log.md` §7「両 peer に実装が無い … 本番 peer の MitateDB は `row_addressability: unavailable` を宣言しており、spec の規則 … そのものが成り立たない」、同 §17 (honest scope)「Data Service が update / delete を拒否する形は本版に存在しない」。`docs/work-orders/mitate-application-data-service-client-phase-b-requirements.md` §3 (solutionName の一意性は `row_addressability` unavailable のため Data Service では守れない)・§12 (g) (`revision_preconditions` は未着手、複数 instance 化の前提)。Mitate が直接指すのは **R-49** (`append_only`) |

**その他 (保留項目に当たらないが、Mitate が data-service-api に対して記録している要件)**: (1) **R-45** (operation depth / platform upgrade。進行中。`docs/remaining-work-index.md` §検証待ち・運用前確認 1)。(2) `in` 演算子 (`docs/work-orders/mitate-application-data-service-client-phase-b-requirements.md` §2 C.8・§12 (b)。spec の演算子集合には `in` がある (`spec/data-service-api.v1.json`:625)。両 peer の実装状況は本表の対象外)。(3) `listSolutions` の読取費用 (`docs/remaining-work-index.md` §実装待ち・進行中 4。Mitate 側の設計作業)。(4) directory の全件読取が `result_items` cap に当たる懸念 (`docs/design/contract-v0.22.0-scheduled-action-target-ceiling.md` §19 の trigger 11)。(5) TEXT 比較の型意味論を pin する conformance が無い (`docs/design/contract-v0.17.0-value-guard-and-datetime.md` §8-2)。

### 3.3 提案 II の基盤 9 項目の突合

| 項目 | 現状 |
|---|---|
| 20 条件を共通 suite で実行可能に | 済 (フェーズ7 WP-4/5) |
| 実 socket・reverse proxy 込み HTTP adapter | L7-2 (フェーズ10) |
| resource limit の全 peer 実効化 | L7-1 (フェーズ8) |
| conformance test 総数の消失検知 | 未対応 → R-9 |
| machine-readable な現行仕様と履歴の分離 | WP-7 で `CONTROL_MAPPING.md` / `CONDITIONS.md` は済。契約 JSON は未 → R-10 |
| schema/wire artifact の自動生成と hash 照合 | 未対応 → R-8 |
| deployment smoke test | 未対応 → R-11 |
| credential を argv へ出さない配備 | r2db の provision script と systemd は環境変数 / 0600 EnvironmentFile 経由で既に満たす。ops CLI の引数経路は R-11 で検査 |
| backup/restore の定期実証 | 未対応 (runbook に項が無い) → R-11 |

---

## 4. 横断の守るべき条件 (以後の全フェーズに適用)

| 記号 | 条件 | 根拠 |
|---|---|---|
| **P-1** | **1 要求 = 1 原子単位。往復をまたぐサーバ保持状態を持ち込まない。** plan・sandbox・resumable upload・保持 lock はすべてこれに当たる。無状態化 (決定的トークン、実行して rollback) で同じ目的を満たす | 契約 `transactions.interactive`、SI-08、両 peer の同型性 (状態は同型性を「持ち方」と「失効」の 2 回壊す) |
| **P-2** | **エージェントの 1 周を閉じることを優先する**: catalog を読む → 要求を作る → 判定を受ける → 安全に再送する。この周回に欠けているものが最優先で、周回の外の機能は実需の実証を待つ | G-1、ai-agent 前提 |
| **P-3** | **宣言は真であり、検査される。** 新しい宣言 (制約・能力・limit) は、宣言と実挙動の一致を共通条件として同時に追加する。advisory な宣言 (強制されない説明文) を catalog に載せない | C-05 / C-17、L6-6 |
| **P-4** | **catalog と schema 操作は同じ版で動く。** 片方だけ先行させない | L6-6 |
| **P-5** | **bound は安全上必要なものだけ。** 機能の問題を TTL・件数上限・除外リストで消さない。要求単位 budget は配備上限を下回る方向にのみ効く | 設計原則 3、SI-08 |
| **P-6** | **peer 同型性を維持する。** 同名 helper は正規化 diff で固定し、コードは共有しない。platform 固有の実現 (PostgreSQL / SQLite / in-memory) が異なっても、契約上の意味は一致させる | peer-symmetry 規約 (2026-09-03) |
| **P-7** | **契約はエージェントが読める長さと形を保つ。** 経緯文は companion へ、現行の意味だけを契約本体に置く。派生の機械可読 artifact は再生成一致テストで正本に縛る | G-1、R-8 / R-10 |
| **P-8** | **各フェーズは性能の差分を記録する。** 基準値 (R-12) 確定後、完了ゲートに p50 / p95 の記録を添える。退行は初期は記録のみ、基準値が 2 フェーズ安定した後にゲート化を審議する | G-4 |
| **P-9** | **クラウド製品・任意 SQL・自然言語クエリ・管理画面・ORM 互換は共通契約に入れない** | CLAUDE.md 境界、CCR-01、提案 II の同趣旨 |

---

## 5. フェーズ計画

### フェーズ7 残 (変更なし)

- **WP-8** は完了した (main `e26f704`)。本書への参照は第 14 次引き継ぎ §4-2 の末尾に 1 行で置いた。
- **WP-9** 公開ゲート。着手条件は依頼者の実行合図のみ (L7-12 状態注記)。**公開は G-2 の「人から見て」を成立させる前提**であり、フェーズ8 以降のどの機能よりも先に価値を生む。フェーズ8 の着手を WP-9 の完了に**依存させない** (触るファイルが重ならない) が、順序としては WP-9 を先に置くことを推奨する。

### フェーズ8 — 実効 bound と基盤衛生 (契約変更なし) 【完了 (2026-09-07)】

**【状態注記 2026-09-07】本節は完了した。** 正本は `docs/design/PHASE8_EFFECTIVE_BOUNDS_AND_HYGIENE_V1.md` (**v1.3**、§11 が実施記録) と `docs/work-orders/WORK_ORDER_PHASE8_EFFECTIVE_BOUNDS_V1.md` (訂正註は §5) である。**main の最新 merge は `f4635ed`、完了ゲートは `2340 passed, 5 warnings in 349.31s (0:05:49)` (failed 0 / xfailed 0 / skipped 0)。** 下記「完了条件」の 4 項目の充足は次のとおりである (R-14 に従い、元の行は消さずに残す)。

- **完了条件 1「C-05 V3 の xfail が 0 (または実測で残る class とその理由が台帳に載る)」= 充足。** **xfail は 0 である。** `operation_depth` が in-process / HTTP の両面で `enforced` になったため、残った class は無い (設計 §5 U-1 状態注記、§10 L8-3)。
- **完了条件 2「CI に総数下限 job」= 充足。** `tools/check_collection_floor.py` を CI の 3.11 / 3.12 の両 job が pytest の前に走らせる。`conformance-tests/COLLECTION_FLOOR` = **2340**。
- **完了条件 3「`spec/` に companion」= 充足。** `spec/CONTRACT_HISTORY.md` (**29 anchor**)。**契約 JSON は 0 バイト不変** (3 複製の sha256 が付録 A §A.0 と一致)。
- **完了条件 4「R-12 の基準値が設計に記録される」= 充足。** **フェーズ8 設計 §11.2 に PERFRUN 行 + PERF 14 行**を記録した (本書 §5 が言う「設計 §13」はフェーズ7 の節番号の慣行であり、フェーズ8 では §11.2 である)。
- **「再検討事項」の 2 件も決着した。** **`operation_depth` の枝** = 依頼者裁定 (A)、実装して両面 `enforced` (逃げ枝は条件不成立)。**性能ハーネスの plug 選択** = **4 plug 全部を測り、HTTP 2 plug は `transport=asgi-inprocess` とラベルして L7-2 前であることを記録した。**

- **目的**: G-2 と G-4 の土台。宣言した bound が全 peer で実効であること、以後の契約改版に耐える計測と検知を置くこと。
- **着手条件**: 依頼者の着手裁定。WP-9 との並行可 (触るファイルが重ならない)。
- **範囲**:
  - **L7-1** MitateDB application plane の `execution_ms` / `concurrency` / `requests_per_minute` / `operation_depth` の実 enforcement (in-process `request_bytes` は副項目) + port への in-flight 保持 primitive + C-05 V3 xfail の class ごとの撤去。**L7-21** (V2 の除外判定を peer 名固定から能力判定へ、port v1.12) を同梱する。同じ C-05 を触るためである。
  - **R-9** CI のテスト総数下限 (前回 main の `--collect-only` 件数を下限とし、減少は明示の更新なしに赤)。**L7-23** (register テストの収集 0 件ガード) と **L7-22** (現行行へ台帳 ID 2 件を戻す) を同梱する。
  - **R-10** 契約 JSON の現行/履歴分離。WP-7 の companion 方式 (`*_HISTORY.md`、ID ごとの anchor、register テスト) を `spec/` に適用。**契約の意味は 1 文字も変えない** (1.6.0 のまま)。分離の検査は「現行 JSON から経緯マーカーが消えたこと」と「companion に逐語で残ること」。 **【改版 2026-09-07 (R-14)。上の文は起票時の原文であり、消さずに残す】** **本フェーズの R-10 は「provenance companion (契約 JSON は 0 バイト不変) + register テストによる網羅性の固定」である。** **検査文「現行 JSON から経緯マーカーが消えたこと」は不成立であり、採らなかった** — 根拠は**逐語インベントリ (フェーズ8 設計 付録 A、2026-09-06)** であり、**マーカーを含む 29 値のうち「値全体が経緯叙述」であるものは 0 件、29 値すべてにマーカーと現行の規範文が同居し、18 件は `test_contract.py` の PIN = 依頼者確定文言として逐語固定されている**。したがって**規範文を書き換えずに消せるマーカーは 0 件**である。**採った検査は (i) 常設スキャナが列挙する JSON パス集合 = companion の anchor 集合 (過不足なし)、(ii) 各 anchor の引用が契約値と byte 一致、(iii) 導入版が `Since X.Y.Z` と一致 (対象 17 件)、(iv) ruling 参照が `CCR_DISPOSITION.md` の見出しに実在、(v) 見出しの重複なし・配下が非空**である。**(B) (29 値の接頭辞 / 挿入句の剥離) はフェーズ9 (契約 1.7.0) へ送った** — 18 件の PIN = 依頼者確定文言の再確定が要るため、版が上がるフェーズで扱えば再確定が 1 回で済むからである (依頼者裁定 2026-09-06 = 監督推奨どおり、フェーズ8 設計 §5 U-2 / §10 L8-4 / L8-8)。
  - **R-11** 運用項目: deployment smoke test (provision 後に capabilities / catalog / 1 query を実打ちして終了コードで返す)、**L7-18** の `ops verify-declarations` を**両 peer に同型で**追加、backup/restore の手順と実証記録 (r2db)、ops CLI の引数に secret を取る経路の検査 (両 peer)。**L7-19** は constraints の Starlette 更新と同一コミットで ignore を外す (撤去条件が満たせる版があれば本フェーズで行う)。
  - **R-12** 性能基準値: 両 peer × 4 plug に対する query / mutate / cross-entity の p50 / p95 を測る使い捨てでないハーネス (`tools/`) と、完了ゲートに添える集計行の形式。**閾値は置かない** (P-8)。 **【改版 2026-09-07 (R-14)。上の文は起票時の原文であり、消さずに残す】** **op 名は「query / mutate / batch (+ `cross_entity` は `cross_entity_mutation` が `unavailable` でない plug のみ)」である。** **根拠: r2db は `cross_entity_mutation: unavailable` を宣言しており、拒否経路の費用は性能基準値の対象ではない** (拒否の費用を測っても意味のある比較にならない)。**3 列目は両 peer で比較可能な唯一の複数操作単位である `batch` (単一 entity の atomic mutation batch、操作数 5) を採った。** **監督裁定 2026-09-06、フェーズ8 設計 D-6。出力は 4 plug × 3 op = 12 行 + MitateDB 2 plug × `cross_entity` = 2 行、計 14 行である。**
- **守るべき条件**: 契約変更ゼロ。L7-1 は C-05 の既存の駆動集合規則に従う。R-10 は WP-7 の規約を再利用し新方式を作らない。
- **完了条件**: C-05 V3 の xfail が 0 (または実測で残る class とその理由が台帳に載る)、CI に総数下限 job、`spec/` に companion、R-12 の基準値が設計 §13 に記録される。
- **再検討事項**: `operation_depth` の枝 (L7-1)。性能ハーネスの plug 選択 (HTTP plug を含めるか。L7-2 前なので in-process TestClient 経路になる点を記録する)。

### フェーズ9 — 契約 1.7.0「宣言と検証」【完了 (2026-09-08)】

**【状態注記 2026-09-08】本節は完了した。** 正本は `docs/design/PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md` (**v1.8**、§11 が実施記録) と `docs/work-orders/WORK_ORDER_PHASE9_CONTRACT_170_V1.md` (訂正註は §6、19 件) である。**main の最新 merge は `85e99fa`、完了ゲートは **`2807 passed, 5 warnings in 323.70s (0:05:23)`** (failed 0 / xfailed 0 / skipped 0 / error 0 — 集計行にいずれの語も無い。終了コード変数は zsh の `pipestatus` 差で取得漏れ、判定は集計行による。`pg_database` 22 → 22、`ps` で他の pytest 0 件、2026-09-08 05:26〜05:32 JST、main `85e99fa` と同一 tree) である。** 下記「完了条件」の 4 項目の充足は次のとおりである (R-14 に従い、元の行は消さずに残す)。

- **完了条件 1「契約 1.7.0」= 充足。** 3 複製の sha256 は `1651795480511be5476c554ea95dda67152fe2512beedee352049d17c19afcc4` で一致する (フェーズ8 の値から動いた)。**従属判断 12 を `spec/CCR_DISPOSITION.md` に新設した。**
- **完了条件 2「両 peer の `contract_version` 1.7.0」= 充足。** 4 箇所すべてを実測した (§1.0b)。**版フリップは peer ごとに 1 コミットで、完了ゲート内で連続して main にマージし、間に他のコミットを挟んでいない** (設計 §5 U-7 = (A))。
- **完了条件 3「新条件 (C-20 以降) が four adapters で executable」= 充足。** **C-20〜C-25 の 6 行がいずれも `executable (four adapters)` である。** **版ゲートの `xfail(strict=True)` は 8 → 4 → 0 と遷移し、`conformance-tests/` を 1 行も編集せずに 0 になった。**
- **完了条件 4「R-12 の性能差分が記録される」= 充足。** フェーズ9 設計 **§11.2** にフェーズ8 §11.2 と同形式で記録した (PERFRUN 行 + 14 行の PERF 表 + 同一 plug の版間差分)。**閾値は置いていない** (P-8)。**これで基準値は 2 フェーズ安定した。**
- **「再検討事項」の 3 件も決着した。** **enum の上限** = 設計 §5 U-1 = (β)、独立の limit class `enum_members` を新設 (`schema_objects` には含めない)。**dry_run の監査イベント** = 設計 §5 U-2、dry_run は監査行を書かない (実行前拒否は従来どおり監査される)。**idempotency の保持** = 設計 §5 U-3 = (A)、application DB の side table に data tx と同一 tx で書く (DB 側単一真実 (Q4) には載せない)。


- **目的**: G-1 と G-3。エージェントの 1 周 (P-2) を閉じる。
- **着手条件**: フェーズ8 完了 (実効 bound の無い peer に新しい要求形を足さない)。契約フェーズなので**設計レビュー 2 回**。
- **範囲** (一括出荷。分けると P-4 に反する):
  - **R-2** 制約宣言: `create_entity` / `add_field` / `alter_field` に enum と nullable。サーバが値検証の choke point で強制し、`EntityDescriptor` が同じ版で報告する。既存行が反する `alter_field` は実行前検証で全件拒否。`pattern` は正規表現の計算量が SI-08 の面になるので**初版に含めない**。両 peer の宣言永続化は per-application upgrade (フェーズ6 / Q4 の機構) で行う。
  - **R-3** 検証エラー語彙: VALIDATION_FAILED / IDENTIFIER_INVALID / CAPABILITY_UNSUPPORTED に固定 key (`field` / `declared_type` / `observed_type` / `violated_declaration`)。事実のみ。行値・推奨値・修正動作は載せない (SI-10)。両 peer でどの層が `violated_declaration` を決めるかを揃える (L6-9 の二重検証を整理する)。
  - **R-4** dry_run と無状態 plan: `MutationRequest` / `ScopedMutationRequest` / `SchemaOperationRequest` に `dry_run`。応答は実呼びと同じ判定 + affected 件数 + (schema なら) 変更後の `EntityDescriptor`。副作用の規則 (監査イベント・idempotency 記録・server-assigned address の消費) を契約に明記。plan トークン = request digest + 対象 entity の schema revision の決定的値で、apply 時に不一致なら PRECONDITION_FAILED。認可判定 (policy simulation) も dry_run の判定に含める。conformance 条件: 「dry_run の判定 = 実呼びの判定、外部可視の状態変化 0」。 **【改版 2026-09-07 (R-14)。上の文は起票時の原文であり、消さずに残す】** **plan の schema 状態成分は「対象 entity の schema revision」ではなく「対象 Application の schema revision」である。** **根拠: 両 peer とも entity 単位の revision を持たず、`SchemaOperationResult.revision` は per-application の単調カウンタである** (r2db `r2db-api/src/r2db_api/postgres.py:1900-1935`、MitateDB `MitateDB-api/src/mitatedb_api/backend_postgres.py:646-661`。フェーズ9 設計 F-16)。**帰結として、対象 entity に無関係な entity への schema 操作も plan を失効させる** — **これは fail-closed 側の誤差であり (失効しすぎることはあっても、変わった schema を見落とすことはない)、安全側である。** **契約 `structured_operations.dry_run.plan` がこの広さを 1 文で開示する。** **監督裁定 2026-09-07 (依頼者裁定「判断しなければならないものが出たらあなたの推奨で進めてください。後で報告してください。」の委任に基づく)、フェーズ9 設計 §5 U-4 = (A) と §3 D-4 (7)。**
  - **R-5** idempotency の実装と契約追記: 両 peer で `idempotency` を `enabled` へ。契約に追記するのは (i) key と body digest の結合、(ii) 同一 key 異 body は CONFLICT、(iii) 保持期間内の再送は元の結果を返す、(iv) cross-entity と schema 操作にも適用、(v) 監査イベントとの相関 (key は secret ではないが、**client が secret 的な値を key に入れることを契約で禁じる文**を置き、`forbidden_fields` との境界を明記)。L7-8 の肯定側がここで初めて load-bearing になる。
  - **R-6** request budget: 要求単位の `budget` (初版は `result_items` / `execution_ms` / `batch_items` の 3 class)。配備上限を超える値は VALIDATION_FAILED、超過は LIMIT_EXCEEDED + `limit_class`。`rows_scanned` は limit class に無く backend 間で意味が揃わないので**含めない**。
  - **R-7** 成功応答の `request_id` (QueryResult / MutationResult / SchemaOperationResult に optional 追加)。
  - **R-8** 派生の操作カタログ: 契約 JSON から生成する機械可読 artifact (endpoint ごとの role / destructive / atomicity 境界 / 返し得る code / 能力依存 / request・response schema)。`tools/` で生成し、テストが再生成して一致を assert する。`/v1/capabilities` からの参照は optional 1 項目。「resource cost の概算方法」は両 peer で同型に計算できないので**含めない**。
- **守るべき条件**: P-1 (plan は無状態)、P-3 (新宣言ごとに一致条件)、P-4、P-5 (budget は下回る方向のみ)、P-7 (経緯文を契約本体に足さない。R-10 の companion に書く)、`versioning.version_binding` の規律 (1.7.0 義務の網羅列挙)。
- **完了条件**: 契約 1.7.0、両 peer の `contract_version` 1.7.0、新条件 (C-20 以降) が four adapters で executable、R-12 の性能差分が記録される。
- **再検討事項**: enum の上限 (要素数・長さ) を `schema_objects` に含めるか別 class か。dry_run の監査イベントの扱い (attributable であるべきか、破壊操作の dry_run を security-relevant とみなすか)。idempotency の保持を DB 側単一真実 (Q4) に載せるか。

### フェーズ10 — 配備面の証拠 (契約変更なし、フェーズ9 と並行可)

- **L7-2** 実 socket を持つ HTTP plug (5・6 番目の plug)。reverse proxy 込み。ここで初めて `surfaces` の「宣言 URL の実在」が load-bearing になる (L6-5 / L6-12)。
- **L6-5a** `surfaces` を DB 側単一真実へ載せる (Q4 と同じ機構)。相互ダイヤルによる健全性検査は採らない (§6)。 **【訂正註 2026-09-08 (R-14)。上の文は起票時の原文であり、消さずに残す】** **`surfaces` を DB 側単一真実へ載せる機構は、Q4 フェーズで既に閉じている** (`docs/design/PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md:796` の【閉止 2026-09-05】、設計 `docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md` D-2、migration r2db `0008` / MitateDB `0007`)。**フェーズ10 の残余は「本番経路での実証」である** — Q4 設計 §12 の **LQ4-11** (r2db HTTP plug は `surfaces` を明示注入して宣言表を通らないので、本機構は共通 conformance では検証されない) を、**本番 composition root を実起動する新条件 C-26 で閉じる** (フェーズ10 設計 §1.3 (1)、§3 D-1 (B)、§3 D-4)。
- **着手条件**: CI が実サーバ起動の場を持つこと (フェーズ7 D-3 で成立済み)。フェーズ9 と触るファイルが重ならないことを設計で確認する。
- **【追記 2026-09-08 (v1.6)】着手前・同フェーズ内の是正 (§8 の R-17〜R-23)。** **着手前**: **R-21** (`CONTROL_MAPPING.md` SI-08 行と両 README の陳腐化を現物から書き直す)。**本フェーズの範囲に足す**: **R-17** の再発防止検査 (追跡中の `.md` が 0 バイトなら赤)、**R-19** (本番 image / 配備手順を `constraints.txt` の exact-pin に揃える)、**R-18** の裁定 (資源制限 `enforced` の適用単位。配備面の証拠を扱う本フェーズが最も近い)、**R-20** の実測 (L7-2 の実 socket adapter で同時要求下の tail latency を測ってから方式を決める)。**設計文書 §1〜§2 に転記する (§9 の 1)。** 変更クラスは各行の記載による (§9 の 8)。
- **【訂正註 2026-09-08 (R-14)。上の見出しと本文は起票時の原文であり、消さずに残す】** **本フェーズは契約を触る。** 見出しの「契約変更なし」は起票時の見込みであり、**§8 の R-18 の裁定 (資源制限 `enforced` の適用単位) が契約文を要すると判明したことで成立しなくなった** — **契約 1.7.0 → 1.8.0** である (フェーズ10 設計 `docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md` §3 D-5 (i)、§5 U-6)。**帰結として設計レビューは 2 回である** (本書 §9 の 3)。**「フェーズ9 と並行可」も現況では成立しない** — フェーズ9 は 2026-09-08 に完了したので、並行の余地そのものが無い。

- **【追記 2026-09-08 (v1.8)】外部レビュー 2 の検証 (§1.0d) が本フェーズに足した作業項目は 5 つである。** **依頼者裁定 (2026-09-08、逐語)**「フェーズ 10 に組み込めるのであれば組み込んでください。」に基づく。**確定形はフェーズ10 設計 `docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md` §5 の U-7〜U-13 と §3 D-13、発注は同作業指示書である。**
  - **WP-1c** (**R-25** / **R-26** / **R-28**、Class B): MitateDB の digest から `budget: {}` が落ちる不具合の是正と両 peer のテスト、CI の `skipped == 0` / `xfailed == 0` (**および `xpassed == 0` / `deselected == 0`。監督裁定 2026-09-08 の拡張**) の強制、`r2db-api/README.md:158` の書き直しと第 16 次引き継ぎ §1 への日付付き訂正註 (追記であって書き換えではない)。**実施は branch `phase10-wp1c` の `5944013` (確定は `2431e93`) であり、範囲は `cell.py` のスキーマ操作 3 箇所の digest と `security/CONTROL_MAPPING.md` の SI-00〜SI-03 の受入境界にも及んだ。** **WP-3 が先に main へ入ったので、WP-1c は main の WP-3 の上に載る形になった** (`ci.yml` は領域が異なるので競合しない)。
  - **WP-6d** (**R-24**、Class C): 同一 idempotency key の同時要求を直列化する。**6d-i** = 両 peer の backend lock + in-memory lock + peer-local テスト (WP-3 に依存しない)、**6d-ii** = 新条件 **C-27** と adapter hook (WP-3 の hook 抽出の後)。
  - **WP-5a 追補** (契約 1.8.0 の `idempotency.record` に同時送信の直列化義務を 1 文足す。**1.8.0 は未公開なので版は動かさない**。監督が実施する)。**実施済み — branch `phase10-wp5` の `73adbda`。WP-5a 本体は `654e23e` の時点で main `3d7f823` に入っており、この追補は次のゲート束でマージする。**
  - **WP-8 の前提条件**: threadpool 委譲は「1 要求 1 接続 (または pool からの貸出) で cell が接続を跨いで共有しない」ことを先に満たす。
  - **WP-3 の追跡是正 (follow-up) 項目**: `sweep_orphans` の `pid <= 0` の明示 guard とテスト 1 本 (**R-27**)。**WP-3 は main `6055c69` へ先にマージされていたので、rework ではなく main に対する follow-up として実施した (branch `phase10-wp3f` の `ea237e5`。次のゲート束でマージする)。**

- **【追記 2026-09-08 (v1.9)】本フェーズに 2 件が加わった。** **(1) WP-R35** (**R-35**、Class B): **フェーズ9 R-2 の走査 lock mode を `SHARE ROW EXCLUSIVE` に改める** (両 peer の `add_field` / `alter_field` の 1 行ずつ + 決定的な 2 スレッドテスト。**worktree `phase10-r35`、実施済み、コミット `46b081a` + レビュー是正 `7ead163` (Opus レビュー accept)**)。**出所は WP-6d-i のコードレビューであり、本フェーズの新規変更が作った欠陥ではない** (フェーズ10 設計 §3 **D-15**)。**取り込み順は WP-6d-i → WP-R35 である** (同じ 2 ファイルを触る)。 **(2) R-34 の実施** (Class B、`<peer>/tests` のみ): **完了ゲートの timing テストを Event 同期に改めた** (branch `phase10-r34` の `12a7bd7` / `5a59002`。§1.0d)。**どちらも契約・宣言・共通条件に触らない。**

- **【追記 2026-09-10 (v1.10)。フェーズ10 の完了】** **本節の起票文と上の追記はすべて残す。** **本フェーズが閉じたのは L7-2 / L6-5a の残余 (実 socket plug 2 本と本番 composition root の証拠 C-26)、R-17 の残 / R-18 / R-19 / R-20 / R-21、および外部レビュー 2 由来の R-24〜R-28 (1) (2)、R-34 / R-35 である。** **契約は 1.7.0 → 1.8.0 になり (訂正註のとおり見出しの「契約変更なし」は成立しなかった)、共通条件は C-26 を 1 件足して実行可能になった。** **開いたまま残るのは 2 件である** — **(a) 新条件 C-27 (WP-6d-ii) は `CONDITIONS.md` に declared のままで、共通 suite ではまだ駆動していない (実装 WP-6d-i と peer-local テストは在る)、(b) CI の集計行が課金上限で未取得であり (台帳 L10-15)、WP-7 (main `ff8d232`) の PERF 行の記入が監督に残っている。** **完了ゲートの実測と未達の扱いはフェーズ10 設計 `docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md` (v1.6) §9.1 が正本であり、本書は再導出しない。** **本フェーズの起票は同書 §10.4 の L10-8〜L10-19 であり、フェーズ11 へ送るのは R-22 (依頼者判断待ち) / R-23 / R-28 (3) / R-29 / R-30 / R-31 の残余 / R-32 / R-33 である。**

- **【追記 2026-09-10 (v1.11)。WP-6d-ii の実施。上の追記は書き換えていない】** **上の (a) は解消した** — **WP-6d-ii (新条件 **C-27** と port v1.15 の hook `hold_after_idempotency_lookup`) を実施し、main `2455f96` に入った** (branch `phase10-wp6dii` の `d97de35` + `8425ef4` + `05bc548`)。**共通条件は C-26 と C-27 の 2 件が実行可能になり、C-27 は 6 plug 全数で駆動する。** **これで外部レビュー 2 由来の起票のうち本フェーズ担当分 (R-24〜R-28 (1) (2)、R-34 / R-35) はすべて閉じた。** **開いたまま残るのは (b) の CI 集計行 (課金上限、台帳 L10-15) だけであり、フェーズ11 へ送る一覧は上の追記のままで変わらない。** **正本はフェーズ10 設計 (v1.7) §3 D-13 の実施註 (6d-ii) / §9.1 / §11.11 である。**

### フェーズ11 以降 — 実需駆動 (§3.2 の保留項目)

着手順は実需の記録順とし、本書では固定しない。ただし依存関係は次のとおり。

- 非同期 job (CCR-09) → bulk ingest/export の chunk 原子性 → aggregation。
- change feed は idempotency (R-5) と audit cursor の語彙を前提とする。
- credential 委任 (CCR-11) は R-4 の認可 dry_run を前提とする。
- 関係モデルは 2.0 級として独立審議。関係に依存する機能 (subgraph fetch、relationship-aware plan) はその後。
- snapshot は control plane の application lifecycle としてのみ再考する。
- **【追記 2026-09-23 (v1.108)】実需の突合 (§3.2 の実需の定義と突合表による。2026-09-23 時点)。** 上の依存関係は書き換えていない。どれから着手するかは依頼者の裁定事項であり、本追記は判断しない。
  - 非同期 job (CCR-09): 実需なし (2026-09-23 時点)。
  - bulk ingest/export の chunk 原子性: 部分的 (§3.2 突合表。batch 上限の実測はあるが、一括投入・export の要件は無い)。着手条件の充足は依頼者裁定。
  - aggregation: 部分的 (同表。pushdown の trigger はあるが、Phase B 後の要求棚卸しは「要求もしない」と明記)。着手条件の充足は依頼者裁定。
  - change feed: 部分的 (同表。既存語彙で自己完結し、cursor 語彙の整合が trigger として残るのみ)。着手条件の充足は依頼者裁定。
  - credential 委任 (CCR-11): 実需なし (2026-09-23 時点)。
  - 関係モデル: 実需なし (2026-09-23 時点。Mitate は汎用 join を non-goal と明記)。
  - snapshot: 実需なし (2026-09-23 時点)。
  - migration planner (II-6)・query explain (II-9)・索引の自動作成 (高速化案 8): 実需なし (2026-09-23 時点)。
  - keyset ページング (高速化案 7): **着手条件充足** (Mitate `docs/work-orders/mitate-application-data-service-client-phase-b-requirements.md` §3 の 2・§12 (f)、2026-09-23)。
  - R-36 ファイル/バイナリ: 部分的 (同表)。着手条件の充足は依頼者裁定。
  - R-43 行・列セキュリティ: 部分的 (同表。(b) は R-43 行に記録済み)。着手条件の充足は依頼者裁定。
  - R-29 最低共通機能プロファイル: **着手条件充足** (Mitate `docs/design/contract-v0.26.0-attributed-append-log.md` §7・§17、2026-09-23)。

---

## 6. 却下した案 (再提案には新しい論拠が要る)

| 案 | 理由 |
|---|---|
| data plane の sandbox セッション / TTL 付き clone / copy-on-write セッション | P-1。契約 `transactions.interactive` は「有限 bound を構造的に証明する設計」を再検討条件にしており、TTL・容量で縛る形はその証明ではない (P-5)。dry_run が同じ目的を無状態で満たす |
| サーバ保持の `plan_id` (expires_at 付き) | P-1。無状態トークンで同じ保証が得られる |
| 出力形式の切替 (CSV / TSV / JSON Lines) | 型付き catalog と矛盾 (json / object / array が落ちる)。`media_type` は契約で固定。conformance 面が倍になり安全上の利得が無い。`select` 射影と page で足りる |
| webhook / WebSocket / Pub/Sub による監査ストリーミング | P-9 (クラウド製品は契約外)。監査 sink からの外向き送信路は SI-10 / SI-14 の新しい漏洩面であり、受信先 URL の登録は永続設定の新しい面。1.4.0 の opaque cursor + `audit_requests_per_minute` がこの用途の設計。push が要るなら契約外の poller が担う |
| surfaces の相互ダイヤルによる topology 健全性検査 | data plane に外向き依存と新しい故障面を作る。L6-5a が既に手当て (DB 側単一真実) を決めている |
| エラー応答の `suggested_fix_action` / `valid_sample` | サーバが client の意図を推測する形で、値の黙示的変換を誘導する。行値は SI-10 違反、合成値は無意味。宣言を指し戻す形 (R-3) で足りる |
| catalog の advisory な説明文 (強制されない description) | P-3 / L6-6。強制される制約 (R-2) に置き換える |
| 操作カタログの「resource cost の概算方法」 | 両 peer で同型に計算できない。宣言だけ先行する形は P-3 に反する |
| `rows_scanned` の budget class | 既存 limit class に無く、SQLite / PostgreSQL / in-memory で観測の意味が揃わない |
| 任意 SQL・自然言語クエリ・管理画面・ORM 互換 | P-9。提案 II も同趣旨 |

---

## 7. 性能の扱い (G-4)

依頼者は高性能を大前提と述べたが、**現時点でリポジトリに計測は存在しない**。**【訂正註 2026-10-04 (R-28)】この文は 2026-09-06 の起票時の原文である。基準値は 2026-09-07 に取得済み (下の 1 の訂正註)、閾値は §0.1.4。】**既知の観測は L6-15 (MitateDB の宣言型 registry 参照が insert 2 回・query 3 回の往復を増やす) のみで、数値は無い。したがって、

1. フェーズ8 の R-12 で基準値を取る。対象は両 peer × 4 plug の query / mutate / cross-entity、指標は p50 / p95 と 1 要求あたりの DB 往復数。 **【訂正註 2026-09-07 (R-14)。上の文は起票時の原文であり、消さずに残す】** **実際の op 名は「query / mutate / batch (+ `cross_entity` は `cross_entity_mutation` が `unavailable` でない plug = MitateDB 2 plug のみ)」である** (§5 の R-12 行の改版と同じ。根拠: r2db は `cross_entity_mutation: unavailable` であり、拒否経路の費用は対象外。監督裁定 2026-09-06、フェーズ8 設計 D-6)。**指標名も「DB 往復数」ではなく `backend_calls` (backend 呼び出し回数) である** — **ラップ点の粒度が 4 plug で揃わないので plug 間で比較してはならず、比較の意味を持つのは同一 plug の版間の差分だけである** (フェーズ8 設計 §10 L8-11 / §11.2 の注記)。**基準値は 2026-09-07 に取得済みであり (フェーズ8 設計 §11.2)、下記 3 の「2 フェーズ安定」の起点は本基準値である。**
2. 以後の各フェーズは完了ゲートに差分を添える (P-8)。
3. 退行の扱いは初期は記録のみとし、基準値が 2 フェーズ安定した後にゲート化を審議する。**閾値を先に置かない**のは、閾値が bound として機能を縛る形 (P-5) になるのを避けるためである。 **【訂正註 2026-09-24 (v1.113)。上の文は書き換えていない】** §0.1.4 の閾値は完了ゲートの退行検査であって契約の bound ではなく、本項が避ける形 (P-5) に当たらない (依頼者裁定 2026-09-24、§0.1.5 の (d))。ゲート化の審議は §0.1.4 の採用をもって終える。
4. 性能のために同型性 (P-6) や宣言の真実性 (P-3) を崩す案は採らない。L6-15 のキャッシュは、宣言の変更が cell open 時に見えること (Q4 の visibility 規律) を守る形でのみ入れる。

---

## 8. 台帳 (本書の起票項目)

- 記録: `docs/archive/docs/design/ROADMAP_POST_PHASE7_V1__LEDGER_CLOSED.md` (閉止・却下した行の全文と、その行への後からの追記。逐語。書き換えない)
- 固定欄 (状態 / 規模 / 印 / 着手条件 / 件名 / 閉止日) の語彙と書式は設計 `docs/design/LEDGER_FIXED_FIELDS_V1.md` D-2、規律は `docs/work-orders/OPERATING_CONDITIONS.md` §1.16 の 79。**固定欄が現在の値であり、「内容」の欄の規模・印の前置きは経緯である。** 未閉止行の一覧は `python3 tools/dev/ledger.py --open`、検査は `python3 tools/dev/ledger.py --check`。

### 8.1 未閉止と常設の行

| ID | 状態 | 規模 | 印 | 着手条件 | 件名 | 内容 | 行き先 |
|---|---|---|---|---|---|---|---|
| **R-1** | 常設 | - | なし | - | 依頼者の目標を 4 要求 G-1〜G-4 に分解 | 依頼者の目標 (§0) を 4 要求 G-1〜G-4 に分解した。以後のフェーズ設計は §2「守るべき条件」でどの G に応えるかを明記する | 全フェーズ |
| **R-11** | 進行中 | S | あり | 上流 Starlette の修正版 | 運用項目 (smoke test、L7-19 撤去ほか) | **【追記 2026-09-23 (v1.105)】規模 S — 残りは L7-19 の pin 撤去 1 件で、上流 Starlette の修正版待ち。着手条件: 運用開始後 (運用が始まって data と client が存在しても直す費用は上がらない)。** 運用項目: smoke test、L7-18 `ops verify-declarations` (両 peer)、backup/restore 実証 (r2db)、ops CLI 引数の secret 経路検査、L7-19 の撤去 | **フェーズ8 完了 (2026-09-07)**。`tools/deploy_smoke.py`、両 peer の `ops verify-declarations` (**L7-18 は閉じた**)、`docs/ops/BACKUP_RESTORE_R2DB.md` と実証記録、argv secret の常設検査 (**修正前 6 件 → 修正後 0 件**) が入った。**L7-19 だけは撤去条件未達のまま据え置きである** — 上流の Starlette に当該参照を直した版が無い (フェーズ8 設計 §10 L8-2) |
| **R-13** | 常設 | S | あり | - | 保留項目 (§3.2) の実需記録の置き場 | **【追記 2026-09-23 (v1.105)】規模 S — 作業項目ではなく実需の記録の置き場で、1 件 1 行を本表に足すだけ。着手条件: 運用開始後 (運用が始まって data と client が存在しても直す費用は上がらない)。** 保留項目 (§3.2) の実需記録の置き場。公開後の実利用で現行契約では表現できない要求が出たとき、本表に日付・要求・不足する契約要素を 1 行で記す。これが CCR-01 の「表現力不足の実証」になる | フェーズ11 以降 |
| **R-14** | 常設 | - | なし | - | 本書の改版規約 | 本書の改版規約: 判定 (§3, §6) を覆すときは、覆した根拠と日付を該当行に残し版数を上げる。行を消さない | 本書 |
| **R-22** | 進行中 | L | なし | - | 保守性 (module 分割・履歴コメント移動・CM 再編) | **【追記 2026-09-23 (v1.105)】規模 L — 進行中の多段の変更セット (module 分割・履歴コメント移動・CONTROL_MAPPING 再編)。手順は来歴設計 v0.24 に従う。** 保守性。`MitateDB-api/src/mitatedb_api/cell.py` 4,244 行、`r2db-api/src/r2db_api/structured.py` 3,182 行、`postgres.py` 2,799 行。最長関数は `transact` 447 行 (cell.py)、`apply_schema` 443 行 (postgres.py)、`bind_schema_operation` 399 行 (structured.py)。長大な履歴コメントが認知負荷を上げる。`security/CONTROL_MAPPING.md` は 1 invariant 1 行で、SI-14 行 26,012 文字、SI-08 行 5,797 文字 — 差分レビューと更新漏れ検出に不向き (R-21 の陳腐化はこの形の帰結でもある) | **依頼者判断待ち** (行き先候補: 開発プロセス衛生 v2、またはフェーズ11 以降の実需前)。分割は挙動不変の **Class B** (同型 helper `_ISOMORPHIC_TARGETS` に触れれば **C**、集合を増減すれば **D**)。CONTROL_MAPPING は invariant ごとの節 + 「統制 / 証拠 / 状態」の表への再編 (**Class D**、内容不変)。**P-1〜P-9 と「先送りしない」原則に照らし、R-21 の是正時に再編を同時に行うかを依頼者に問う** | **裁定済み・実施中 (状態の更新 2026-09-22)**: 依頼者裁定 2026-09-14「全て推奨で進めてください」で 4 問とも決着しており、依頼者判断待ちではない。問い 1 (R-37 が巨大モジュール分割の答え) は R-37 の閉止 (2026-09-16) で完了、問い 2 (`security/CONTROL_MAPPING.md` の再編) は v2.0 で完了、問い 4 (R-32 の先行) は R-32 行の実施 2026-09-14 で完了。**残るのは問い 3 (長大な履歴コメントの記録への移動) だけで、次は R6-4 で残した日付の除去と変更セット 7 の選定である** (記録の正本は `docs/design/CODE_COMMENT_PROVENANCE_V1.md` §10)。以下の「依頼者判断待ち」の語は当時の状態として残す。 ~~依頼者判断待ち~~ **【フェーズ10 の報告 2026-09-10】** **依頼者判断待ちのまま持ち越す。** **問いは「`CONTROL_MAPPING.md` の再編を R-21 の是正と同時に行うか」であり、R-21 の是正は 2026-09-08 に完了したので、同時実施の機会は過ぎた。** **フェーズ10 完了報告で改めて問う** (フェーズ10 設計 §9 の 13)。**行き先候補は開発プロセス衛生 v2 (R-32 / R-33 と一緒) である。** **【依頼者裁定 2026-09-14】** 「全て推奨で進めてください」 — 監督が同日提示した 4 問 (文面は監督提示の要約) のすべてに推奨案を採る。**R-22 は裁定済み・実施中である。** (問い 1) **R-37 を R-22 の巨大モジュール分割の答えとして採る。次は R-37 WP-0。** (問い 2) **`security/CONTROL_MAPPING.md` の再編は開発プロセス衛生 v2 を待たず、単独の Class D 変更として早めに行い、再編前後で文が欠けないことを機械照合する** (R-21 との同時実施の機会は過ぎ、SI-08 行は 5,797 → 20,315 字、SI-14 行は 26,012 → 27,950 字。監督実測 2026-09-14)。(問い 3) **長大な履歴コメントは経緯を設計書などの記録へ移し、コードには現在の理由と記録への参照 ID だけを残す。移動は別の変更で行う** (§4 P-7 と一貫。要件は R-37 設計 §9.2)。(問い 4) **R-32 は R-37 WP-3 が `cell.py` の `_gate` 又はその呼出し経路を移動・変更する前に片付ける。** **【実施 2026-09-14 (問い 2)】** `security/CONTROL_MAPPING.md` を v2.0 へ再編した (SI ごとの節、peer ごとの Control / Evidence / Status、主張 1 行)。内容不変は照合ツールと独立監査で確認 (主張 418、欠落・追加 0)。軸は割当表 `tools/control_mapping_axes.tsv` が正本 (Control 261 / Evidence 93 / Status 64)。 WP-3 監査は 3 回目で合格。root suite `3340 passed`。設計 `docs/design/CONTROL_MAPPING_RESTRUCTURE_V1.md` §9。 契約版数は据え置き (依頼者裁定「(i)で進めてください」)。 **【実施 2026-09-14 (問い 3)】** コメント整理の変更セット 0 / 0b / 1 / 0c / 2 を完了した (r2db `postgres.py` と `service.py`、登録簿 179 CH-ID、root gate 3356)。残る対象は設計 `docs/design/CODE_COMMENT_PROVENANCE_V1.md` §6 の優先順で進める (記録は同設計 v0.7 §10)。 **【追記 2026-09-15 (問い 3)】** 変更セット 3 (MitateDB `http.py`、r2db `control_plane.py`、登録 285 ID)、0e・0f (改行の壊れ 190 件超を修正)、事実訂正 (CH-0239 / CH-0139) を完了した (同設計 v0.11 §10.2)。次の変更セットは、§6 の優先 1 のうち R-37 の抽出が残る MitateDB `cell.py`・`backend_postgres.py` と r2db `structured.py` を除くと対象が無いため、優先 2 (10 行以上の塊の行数順) の先頭である r2db `ops.py` とする。 **【追記 2026-09-15 (問い 3)】** 変更セット 0g (訂正の記録、merge `1a921e0`)、行番号 pin の修正 (`9297dd9`)、変更セット 4 (r2db `ops.py`・MitateDB `backend_sqlite.py`、登録 378 ID、`0e969e1`) と記録 (同設計 v0.13 §10.3、`3adba35`) を完了した。 **【追記 2026-09-15 (問い 3)】** 変更セット 0h (文の分割の隠蔽の順序、述語 B の条件 9、`2d47e52`) と変更セット 5 (r2db `credential_store.py`・MitateDB `ops.py`、登録 418 ID、`708ee4c`、merge `db82663`) を完了した (同設計 v0.15 §10.4)。 **【追記 2026-09-15 (問い 3)】** 変更セット 6 (r2db `control_main.py`・MitateDB `backend_postgres.py`、`CH-0504`〜`CH-0616` を予約) の作業指示書を起草した (`docs/work-orders/WORK_ORDER_CODE_COMMENT_PROVENANCE_CS1.md` §14、監督確認待ち)。`backend_postgres.py` は R-37 の裁定 Y-5 により WP-1n の後・WP-4 の前に行い、WP-4 と並行しない。 **【追記 2026-09-15 (問い 3)】** 変更セット 6 (r2db `control_main.py`・MitateDB `backend_postgres.py`、日付だけの除去に縮小 (R6-1)、登録 427 ID、`1f9342f`、merge `42842de`) を完了した。赤いゲートを pipe の終了コードで見落として統合し、main 上の再ゲートで `3390 passed` を確かめた (同設計 v0.16 §10.5)。 **【追記 2026-09-16 (変更セット 0i)】** 変更セット 0i (チェッカーの保護参照の拡張と、変更セット 1〜4 の 52 塊の戻し、登録 427 ID、`d9191fe`、merge `ffd6493`、未 push) を完了した。root gate `3399 passed`、統合後の `tools/tests` `420 passed` (同設計 v0.19 §10.6、作業指示書 `docs/work-orders/WORK_ORDER_CODE_COMMENT_PROVENANCE_CS1.md` §15)。次は R6-4 で残した日付の除去と、変更セット 7 の選定である。 **【追記 2026-09-23 (v1.106)】依頼者裁定 2026-09-23: 「着手条件: 運用開始後」の印は付けない — 進行中の項目であり、仕分けの対象にしない。** **【追記 2026-10-04 (問い 3、v1.170)】** 依頼者指示 2026-10-04 (逐語): 「この内容で着手チップを出してください」 — 対象は、R6-4 の残りを先に単独で片付け、変更セット 7 を MitateDB `cell.py` 単独とする推奨。(1) R6-4 で残した日付の除去を完了した (`c498db2`、merge `e09472b`。対象 4 塊中 3 塊に CH-0580〜CH-0582、登録 434 ID、変異 6 件が赤、完了ゲート `5232 passed, 2 subtests passed`、`security/CONTROL_MAPPING.md` 3.21。記録は来歴設計 v0.28 §10.8)。(2) 変更セット 7 の作業指示書を確定した (`docs/work-orders/WORK_ORDER_CODE_COMMENT_PROVENANCE_CS1.md` §16、監督裁定 Y7-1〜Y7-15)。監督裁定 (依頼者の方針 2026-10-03 により推奨で進めた。事後確認待ち): (a) (1) の範囲は CH-ID の無い 4 塊に限り、CH-ID 付きで日付が残る 5 塊と他 module の日付は後の変更セットで扱う、(b) 検査器が日付だけの除去を拒む 1 塊は基準のまま残す、(c) 変更セットが自分で動かした `security/CONTROL_MAPPING.md` の位置参照は同じ変更セットで引き直し (経路により Class D、版を 1 つ上げる、主張の文は変えない)、conformance・README など既にずれている位置参照は触らない、(d) `cell.py` の対象 205 塊は `ApplicationCell.insert` の前後で WP-7a (102) と WP-7b (103) に分け、順に統合する、(e) 除去は除いた後の文が読める場合に限る (作業指示書 §16.5 Y7-3)、(f) 並行する台帳 R-82 の worktree と `cell.py`・CH-ID・`security/CONTROL_MAPPING.md` の版が重なるが止めずに進め、後から main に入る側が基点を取り直す (Y7-13)。次は WP-7a の実装である。 **【追記 2026-10-04 (問い 3、v1.175)】** 変更セット 7 の WP-7a を完了した (`6714bc7`、merge `79ea879`。MitateDB `cell.py` の `ApplicationCell.insert` より前の対象 102 塊中 36 塊に CH-ID、登録 473 ID、文の削除 0、変異 30 件が赤、完了ゲート `5248 passed, 2 subtests passed`、`security/CONTROL_MAPPING.md` 3.23。記録は来歴設計 v0.29 §10.9 と作業指示書 §16.4)。監督裁定 (事後確認待ち): (g) レビューが、ラベルの除去で同じ塊に残る設計参照の拠り所が消えると指摘した 3 塊は基準の文へ戻す、(h) 実装中に台帳 R-82 が main に入ったので基点を取り直した (Y7-13)、(i) 変異 c22b は検査器が引用する文まで固定した 2 件を足して確かめた。次は WP-7b である。 **【追記 2026-10-05 (問い 3、v1.176)】** 変更セット 7 の WP-7b を完了し (`6dbe3e6`、merge `092e1a1`。`ApplicationCell.insert` 以降の対象 102 塊中 42 塊に CH-ID、登録 515 ID、文の削除 0、変異 29 件が赤、完了ゲート `5248 passed, 2 subtests passed`、`security/CONTROL_MAPPING.md` 3.24)、変更セット 7 (MitateDB `cell.py`、204 塊中 78 塊) を受け入れた (受け入れ監査は未充足 0・証拠不足 0。記録は来歴設計 v0.30 §10.10、作業指示書 §16.4、引き継ぎ書 `docs/work-orders/HANDOVER_20261005_R22_CS7_FABLE.md`)。監督裁定 (事後確認待ち): (j) WP-7b のレビューが挙げた 7 編集 (拠り所の消える除去 1、前に残るラベルの段落の続きに読める除去 5、内容語が消える除去 1) は基準の文へ戻す (両論の件も「迷えば基準のまま」で戻す)、(k) 検査器が日付だけの除去を受け付けない 4 行は基準のまま残す、(l) `cell.py` に基準からある作業ノート名のプレースホルダ参照 (運用条件 §1.9 の 62。全 peer で約 60 ファイル) は本変更セットでは触らず、後続の変更セットがファイルごとに除く (起票しない)、(m) 受け入れ監査の観察 2 件 (WP-7a の記録の数値 2 か所、検査器の FAIL の行番号の案内) は訂正註と観察に留める。次の変更セットの候補は来歴設計 §10.10 の「次の候補」。 **【追記 2026-10-05 (問い 3、v1.177)】** 変更セット 8 を完了し、受け入れた (`4ffd5b1`、merge `47dabd1`。r2db `platform_declarations.py` の対象 32 塊中 8 塊、MitateDB `control_plane.py` の対象 83 塊中 18 塊に CH-ID、登録 541 ID、文の削除 0、変異 29 件が赤、完了ゲート `5248 passed, 2 subtests passed`、`security/CONTROL_MAPPING.md` 3.25。受け入れ監査は未充足 0・証拠不足 0。記録は来歴設計 v0.31 §10.11、作業指示書 §17、引き継ぎ書 `docs/work-orders/HANDOVER_20261005_R22_CS7_FABLE.md` の追記)。監督裁定 (事後確認待ち。作業指示書 §17.5 の Y8-1〜Y8-17): (n) 判定と spec の草案をクラウドセッションに作らせ、作業機で取り込んで再現する。クラウドの照合の値は受け入れの証拠にしない、(o) 2 module を 1 WP で行う、(p) `security/CONTROL_MAPPING.md` が指すコメント行を変える塊 (CH-0943)、残る文がラベルの設計に寄りかかる疑いのある塊 (CH-0941)、ラベルと一緒に現行の区分名が消える塊 (CH-0930) は基準の文のまま残す、(q) 裸の ID だけのラベルは、残る文が寄りかかるか唯一の手掛かりなら残し、そうでない文頭ラベルは除く、(r) 対象の塊に残る作業ノートのプレースホルダ参照は、検査器が許し文が読める場合に除く (2 件を除き、3 行は残した)、(s) 「前」の集計行を取らず、同じ基点の直前の変更セットの後の値で代える。次の変更セットの候補は来歴設計 §10.11 の「次の候補」。 **【追記 2026-10-05 (問い 3、v1.178)】** 変更セット 9 を完了し、受け入れた (`27c0ea9`、merge `5a41b97`。r2db `structured.py` の対象 103 塊中 36 塊に CH-ID、登録 577 ID、文の削除 0、変異 25 件が赤、完了ゲート `5248 passed, 2 subtests passed`、`security/CONTROL_MAPPING.md` 3.26。受け入れ監査は未充足 0・証拠不足 0。記録は来歴設計 v0.32 §10.12、作業指示書 §18、引き継ぎ書 `docs/work-orders/HANDOVER_20261005_R22_CS7_FABLE.md` の追記)。監督裁定 (事後確認待ち。作業指示書 §18.5 の Y9-1〜Y9-15): (t) MitateDB `platform_declarations.py` を外す — blob id が起動検査の fingerprint (`KNOWN_FINGERPRINTS`) に入り、コメントだけの編集でも行の追加と test の更新が要るので、コメント整理の変更セットに混ぜない。fingerprint に blob id で入る 4 module の整理をどう行うかは未決、(u) 裸の ID だけのラベル約 20 塊と、検査器が拒む形 (`/`・`=` を含む版数付き括弧、日付だけ) は基準のまま残す、(v) 作業ノートの参照は、除いた後に残る位置指定や裸の ID が同じ module の別の文書・別の裁定の同じ語と重ならない場合だけ除く (2 件を除き、7 行は残した)、(w) 完了条件 19 は訂正の記録を足さない変更セットでは非該当とする。次の変更セットの候補は来歴設計 §10.12 の「次の候補」。 **【追記 2026-10-05 (問い 3、v1.179)】** 依頼者の事後確認 (2026-10-05、逐語): 「事後確認は了承します」 — v1.170・v1.175・v1.176・v1.177・v1.178 の追記に「事後確認待ち」と記した監督裁定 (a)〜(w) (引き継ぎ書の番号では 1〜18) を了承。未決の 4 点は残る。 **【追記 2026-10-05 (R-39 からの引き渡し)】** R-39 の棚卸しで見つかった `src/` 側の古い位置参照・不正確なコメントは、来歴検査器が CH-ID の無い塊の変更をすべて赤にする (来歴設計 §4.1 (2) v0.22) ため R-39 では直さず、本行の次の変更セットの候補として渡す (R-39 監督裁定 Y-2、事後確認待ち): r2db `structured.py` の「`_ENUM_ELIGIBLE_TYPES` above」「this module's own internal vocabulary」(定義は `schema_binding.py`)、`limits.py` の「`_fail_constraint_declaration` precedent above in this same module」(`limits.py` では成り立たず、定義は `schema_binding.py`)、MitateDB `cell.py` の「flip to `enabled` below」と `service.py:996-1000`・`:1072-1074`・`:1133-1144`・`:1156-1163`・`:1079`・`:877`、`cell.py:1034-1046`、`capabilities_document.py` の `service.py:936-937`・`:770`・`:832`、`config.py` の `limits.py:16-20`、`provisional_gate.py` の docstring (呼出し元の文: `cell.py` に gate も空 tuple も無く、空 tuple は `http.py` にある)。直し方は CH-ID 登録 + 訂正記録 (§9.3) で、同じ変更セットで `security/CONTROL_MAPPING.md` の位置参照を引き直す。 |
| **R-31** | 進行中 | L | あり | 実需の記録 (R-13) | 配備全体の資源保護が揃っていない | **【追記 2026-09-23 (v1.105)】規模 L — 残り (プロセス数・rate・応答サイズ・DB 容量・監査保存量) は配備全体の bound の設計で複数 WP。着手条件は本行のとおり実需の記録 (R-13)。着手条件: 運用開始後 (運用が始まって data と client が存在しても直す費用は上がらない)。** **配備全体の資源保護 (プロセス数・rate・connection・応答サイズ・DB 容量・監査保存量) が揃っていない。** **フェーズ10 が扱うのは「宣言の正直さ」(適用単位の定義と `process_ceilings`) であり、配備全体の bound そのものはその先である** | **フェーズ11 以降**。**着手条件は実需の記録** (**R-13**) と、フェーズ10 の実測 (**R-20**) である **【フェーズ10 の分割 2026-09-10】** **connection の部分は本フェーズで閉じた** — **role の `CONNECTION LIMIT` を実 pool 構成 + 4 に揃える migration (r2db `0013` / MitateDB `0012`) と、`ops verify-declarations` + 4 つの composition root の起動時 fail-fast (**F-16**) が入り、C-26 が fail-fast を観測する** (フェーズ10 設計 §5 **U-19**、台帳 **L10-11**、main `9361f1b`)。**残り (プロセス数・rate・応答サイズ・DB 容量・監査保存量) はフェーズ11 のままである。** |
| **R-36** | 進行中 | L | あり | - | 画像を含む任意ファイル／バイナリの扱いが無い | **【追記 2026-09-23 (v1.105)】規模 L — 新しい共通 capability と HTTP 契約の設計 (設計レビュー起点)。着手条件: 運用開始後 (運用が始まって data と client が存在しても直す費用は上がらない)。** **画像を含む任意ファイル／バイナリの扱いが現行共通 API に無い。** 現行は JSON の構造化データ API であり、raw bytes の upload / download、永続 object ID、内容種別、完全性、アプリケーション単位の object storage 隔離を定義していない。 | **フェーズ11 以降（設計レビュー起点）**。候補は `docs/design/OBJECT_STORAGE_BINARY_API_V0_1.md`。先に、共通 capability・HTTP 契約・object 専用 limit / error vocabulary・監査・削除確認・idempotency・ストリーミング中の再認可と、既存 Security Invariants の適用結果を確定する。次に transport 非依存 port と conformance 条件を作り、最後に r2db の R2 互換 backend と MitateDB の GCS backend を、それぞれ application 専用 bucket / identity / 実行単位の最小権限で実装・配備する。**候補段階では未実装・未宣言・非正本である。** **【追記 2026-09-23 (v1.108)】実需は部分的 (Mitate `docs/remaining-work-index.md` §将来設計・保留「添付ファイル・画像」、`docs/design/agent-entry-record.md` §6.1。2026-09-23。§3.2 突合表)。着手条件の充足は依頼者裁定。** **【追記 2026-10-02 (v1.152)】状態を「進行中」、着手条件の欄を `-` にした (着手条件「設計レビュー。充足は依頼者裁定」は下の裁定と確認で充足)。設計レビュー 1 回目・2 回目を 2026-10-02 に実施した (cloud session。各回 reviewer の観点 A / B の並列 2 起動と再確認 1 起動。`docs/work-orders/OPERATING_CONDITIONS.md` §1.7 の 50・50a)。設計 `docs/design/OBJECT_STORAGE_BINARY_API_V0_1.md` は候補 v0.3 → v0.5 (候補のまま。未実装・未宣言・非正本)。依頼者裁定 2026-10-02 (逐語): 「全て監督推奨で進めてください」(設計 §11 の Q-0〜Q-5 への裁定)。採った案 (ID は設計 §11 のもの): Q-0 (a) 着手条件を充足とみなす / Q-1 (甲)+(乙) download 操作だけの分類の例外と、errors.content_type に一致する media type の upload の拒否 / Q-2 (ii) 1 base URL のまま前段 router が application 専用の実行単位へ振り分ける / Q-3 (甲) (転送時間の bound は Q-6 で改めた) / Q-4 (a) object_storage を提供する deployment は正の `authorization_propagation_bound_ms` を宣言する / Q-5 (a) class を足さず provider 側の quota で縛る / Q-6 (c) 転送専用の class `object_transfer_ms` を 1 つ足す / Q-7 (a)+(b) router を前段と同格の基盤部品とし、SI-00 の残余として記録し要件を条件にする / Q-8 (a) object-capable な配備では `concurrency` を `deployment_required` と宣言する / Q-9 (a) `X-Request-Id` は常にその要求自身の request_id。Q-0 と Q-6〜Q-9 は裁定文に書かれていない件で、監督の読みで進めたうえ、依頼者が 2026-10-02 に作業機の session で確認した (選択肢の選択: Q-0 は「(a) 充足」、Q-6〜Q-9 は「4 件とも推奨どおり」)。実需は 2026-10-02 時点も部分的のまま (Mitate `docs/remaining-work-index.md` の「添付ファイル・画像」は保留。作業機で確認)。完了ゲート `gate: 5019 passed, 2 subtests passed in 470.09s (0:07:50)` (judge=PASS、label r36-design-v05。main との差分は `.md` のみ)。次の段 = 契約改版の作業指示書 (Class C/D。別の変更セット): 共通契約 (media_type の操作別例外、version_binding 1.14.0 (a)、OperationCatalogEntry の request / response media type と headers、field 定義、violated_declaration 14 語、limits.classes +5、destructive applies_to、Idempotency-Key header、X-Request-Id、{object_id}、`authorization_propagation_bound_ms` の正の宣言) → conformance (port v1.22 以降、設計 §7.1 の O-n を C-n に) → 両 peer の実装 → `security/CONTROL_MAPPING.md` (SI-00 の router 残余、SI-08 の総量残余) → 配備値。provider / RFC / nginx の挙動は設計内では未確認であり (設計 §12.1)、作業機での確認結果は引き継ぎ書 `docs/work-orders/HANDOVER_20261002_R36_FABLE.md` の作業機の追記に置く。** |
| **R-40** | 未着手 | L | なし | 依頼者裁定 (フェーズ11) | NaN / ±Infinity の受入 | **【追記 2026-09-23 (v1.105)】規模 L — NaN / ±Infinity の受入は契約の決定で依頼者裁定と両 peer の実装 (Class C / D)。** **`number` の field が NaN / ±Infinity を受け入れる。** 両 peer は request body を starlette の `request.json()` で読み (`r2db-api/src/r2db_api/http.py:359`、`MitateDB-api/src/mitatedb_api/http.py:543`)、Python の `json.loads` は `NaN` / `Infinity` リテラルを受け入れる。型検査 (r2db `_check_type` の `r2db-api/src/r2db_api/value_types.py:122`、MitateDB `check_declared_value` の `MitateDB-api/src/mitatedb_api/field_types.py:134`) は isinstance だけを見る。`number` は DOUBLE PRECISION に対応し (`r2db-api/src/r2db_api/postgres_types.py:27`、MitateDB は `real` 経由で `MitateDB-api/src/mitatedb_api/backend_postgres.py:157`)、NaN / Infinity を格納する。spec、Security Invariants、conformance tests、両 peer の tests のいずれも有限性に触れていない。**未検証**: 型なし field の jsonb 経路で PostgreSQL がエラーを返すか、格納済みの NaN を応答へ直列化するとき失敗するか (JSON の allow_nan)。R-37 WP-1i のレビューで見つかった (設計 `docs/design/MODULE_REFACT_ARCHITECTURE_V1.md` §10.5 の 12)。 | **フェーズ11**。有限数を要求するかは共通契約の決定であり (spec + conformance、Class C / D)、**依頼者裁定が要る**。SI-05 (外部から来た値は明示の検証境界を通る) の適用として扱う。決定の前に上の未検証 2 点を実測する。 **【追記 2026-09-21】JSON の解析・出力を `orjson` に替える高速化案は、単独では起票せず本件に含める** (依頼者指示 2026-09-21 の高速化案の検討)。NaN / ±Infinity の扱いが標準の `json` と異なるので (差の実測は着手時)、有限数の決定と同時に扱う。 |
| **R-43** | 未着手 | L | なし | 保留 (依頼者 2026-09-15)。充足は依頼者裁定 | 行・列単位アクセス制御 (Row/Column Security) | **【追記 2026-09-23 (v1.105)】規模 L — 行・列単位アクセス制御は新機能で設計レビュー起点 (保留中)。** **行・列単位のアクセス制御 (Row/Column Security) が無い。** 現行はロール 4 つの操作単位の許可だけで、主体 (端末・社員)、行・列の権限、権限データの管理 API を定義していない。依頼者の要求は、システムテーブルの権限データ (列 × 役職 → 読 / 読書、行の規則) を control だけが扱い、許されない列・行は存在も推測できないこと (2026-09-15)。依頼者裁定 (逐語): 「A テーブルの役職の値は、システムテーブル側に持つ（推奨）で良いです。」「行単位の制御も範囲に入れます。」 | **保留 (依頼者、2026-09-15)**。先行項目の完了後に着手する。構想メモは `docs/design/ROW_COLUMN_SECURITY_IDEA_V0_1.md` (§6 に着手前に決めること 7 点)。着手時は共通の要求 → Security Invariants → 共通契約 → conformance → 両 peer の実装の順で、契約フェーズとして設計レビュー 2 回。**構想段階では未設計・未宣言・非正本である。** 【追記 2026-09-15】構想メモ v0.2 §8 に起草者の評価 (良い点 4・懸念 3・コスト) を追加した。再開時の最初の一歩は、具体的な利用先 (どのアプリか、利用者の認証方式、役職以外に要る属性) を固めること (同メモ §6 冒頭)。 **【追記 2026-09-23 (v1.108)】実需は部分的 (Mitate `primitives/CANDIDATES.md` の Primitive 候補 24・25。2026-09-23。§3.2 突合表。(b) は本行の依頼者要求 2026-09-15 が該当)。着手条件の充足は依頼者裁定。** |
| **R-47** | 未着手 | M | あり | 本番 inventory の読み取りの後 | 古い 0003 の application で upgrade 台帳の読みが失敗 | **【追記 2026-09-23 (v1.105)】規模 M — 本番の inventory 読み取りの後、該当 application の数に応じて upgrade 経路を直す (migration に触れうる)。着手条件: 運用開始後 (運用が始まって data と client が存在しても直す費用は上がらない)。** **`b87d1c85` (2026-09-05) より前の版の `0003_provision_application.sql` で provision され、0008 が未適用の application は、現行の `ops upgrade-applications` / `upgrade-status` が台帳を読む段階で `permission denied for schema public` (`InsufficientPrivilege`) により失敗する。** `platform_upgrades.read_applied_upgrade_numbers` は台帳の表が無い場合 (`UndefinedTable`) だけを扱い、台帳を後付けする 0008 は流れる機会が無い。fail-closed でデータは壊さない。R-45 WP-C の過去の版を起点にしたテストが発見 (設計メモ `docs/design/MITATEDB_PLATFORM_READONLY_INVENTORY_V0_1.md` §12.2)。本番にこの状態の application があるかは未確認。 | **起票 2026-09-17、起票のみ** (依頼者裁定 (逐語)「台帳に 1 行起票するだけにする」。監督の推奨は R-45 の中で直すことだった)。本番にこの状態の application があれば R-45 の本番更新は blocked になる。 **【追記 2026-09-17】** 依頼者の回答 2 (2026-09-17、逐語は作業指示書 `docs/work-orders/WORK_ORDER_MITATEDB_OPERATION_DEPTH_PLATFORM_UPGRADE_V1.md` §6A.12) により起票のまま。R-45 の WP-E・WP-D (・WP-F) の受け入れ後に `inventory` で本番を読み、(3) が blocked なら R-47 を 1 本の WP として開く。該当の数と状態を見てから直し方を決める。 |
| **R-49** | 未着手 | L | なし | 依頼者の指示 (R-45 は閉止済み) | mutation class (append_only 等) の実装 | **【追記 2026-09-23 (v1.105)】規模 L — mutation class (append_only 等) は契約語彙の実装で、両 peer + conformance (Class C / D)。** **mutation class `append_only` (および `read_only`・`append_delete`) が spec の語彙にあるだけで、両 peer に実装が無い。** 実測 (監督、2026-09-17): `spec/data-service-api.v1.json` の `structured_operations.mutation_classes` は 4 クラスと、「`row_addressability` が enabled のとき entity ごとに 1 クラスを catalog に宣言し、宣言したクラスは支持しない mutation を `CAPABILITY_UNSUPPORTED` で拒否する」規則を持つ。r2db-api は `mutation_class` を `"mutable"` に固定して返す (`r2db-api/src/r2db_api/postgres.py`、`r2db-api/src/r2db_api/structured.py`)。MitateDB-api は src に `mutation_class` の実装を持たない (`MitateDB-api/src/mitatedb_api/cell.py` の docstring に語があるだけ)。MitateDB が `row_addressability: unavailable` を宣言している点は Mitate 側の監督の実測であり、本リポジトリでは未照合 — 着手時に確かめる。**発端**: Mitate の F2 (Agent 入口の記録と対話継承) の契約設計が、会話記録の collection を `append_only` に対応付けて update / delete を Data Service に拒否させる前提を置いていた。依頼者裁定 (Mitate の監督セッションの中継による逐語)「案aで、data-service-api側は後日実装にします。」により、F2 は追記のみを Application の構造で保証する形に書き直し、Data Service 側の強制は後日の強化とする。**論点**: 本番 peer の MitateDB では `row_addressability` が unavailable なので、spec の規則のままでは宣言が成り立たない。実装するなら spec の規則の見直しを含む見込みで、Class D・契約版の改版になりうる。R-29 (両 peer の最低共通機能プロファイル) と関係する。 | **起票 2026-09-17、起票のみ** (依頼者指示 `docs/work-orders/REQUESTER_DIRECTIVE_20260916_R37_CLOSURE_R45_PRIORITY.md` §3.3)。設計メモ・作業指示書・worktree は起こさない。着手は R-45 の後、依頼者の指示を待つ。 **【追記 2026-09-25 (v1.120)】依頼者裁定 U-2 (フェーズ11 設計 `docs/design/PHASE11_MIN_COMMON_PROFILE_V1.md` §5、2026-09-24): Mitate の実需のうち `append_only` (mutation class) は本行に付け替える (baseline では満たされない。R-106 / R-107 と対)。** |
| **R-52** | 進行中 | S | なし | 本番の読み取りの後。Mitate への報告を含む | role の CONNECTION LIMIT が rollout 中に不足 | **【追記 2026-09-23 (v1.105)】規模 S — 残りは (i) r2db 配備の process 数の確認と (ii) 裁定 Q-4 の記録 (文書と裁定のみ)。本番の読み取りが先。** **MitateDB の role の `CONNECTION LIMIT` が rollout 中の process 数に足りない。** `0012_role_connection_limits.sql` の 68 / 20 / 36 と `0005_application_audit.sql` の auditreader 5 は、いずれも **1 plane 1 process・concurrency 32 の前提**の値である。一方 `ops inventory` の項目 (8) の需要は process 数の合計に比例する (controlplane = 合計 × 16、auditreader = 合計 × 4、api = 合計 × 2 × concurrency、application role = 合計 × concurrency)。したがって rollout 中に candidate と traffic を持つ revision が並ぶ (process 数の合計が 2 以上になる) と需要が上限を超え、**Control を配備した本番の Gate-0 では (8) が blocked になる見込みである。** 対処の候補: 上限を上げる新しい platform migration / 数え方の見直し / 旧 revision を先に止める手順。runbook `MitateDB-api/docs/cloud-run-cloud-sql.md` §10.10 は、本番の状態を 1 つも変える前に紙の上で検算し、収まらなければ直しの段を始めず `blocked—platform remediation required` で止まる手順として閉じている (この runbook に直し方は無い)。 | **起票 2026-09-18、起票のみ** (R-45 WP-D の設計レビュー 2 回目の高 1 件と監督の現物確認)。**着手は依頼者の指示を待つ。** 本件では何も直さない。**Mitate への報告に含める。** **【追記 2026-09-18 (v1.63)】着手した。** 依頼者の回答 (2026-09-18):「本番の読み取りより前に着手」。設計メモ `docs/design/MITATEDB_ROLLOUT_CONNECTION_LIMITS_V0_1.md` v0.3 (設計レビュー 1 回、8 件を反映)。依頼者裁定 (2026-09-18、逐語は同メモ §10.1): 新しい platform migration `0014` で上限を 132 / 36 / 68 / 12 に上げる、並走は 2 に固定、F-16 の床は 1 process 分のまま、`max_connections` が足りない場合の方針は本番の読み取りの後に裁定する。**`security/CONTROL_MAPPING.md` の WP は R-50 の統合後に着手する** (SI-08 の MitateDB ブロックの残りが 6 字のため。監督裁定)。これに伴い小さい項目の着手順を R-51 → R-50 → R-54 とする。次は作業指示書。 **【追記 2026-09-18 (v1.65)】WP-1 を統合した。** 作業指示書 `docs/work-orders/WORK_ORDER_R52_ROLLOUT_CONNECTION_LIMITS_V1.md` (4 本の直列)。WP-1 = migration `MitateDB-api/migrations/0014_role_connection_limits_rollout.sql` と `apply-platform-migration` の受け付け・追随テスト: main `11c98a2` (作業 `e16be5f`)。第 1 段 (実測) → 一括裁定 → 実装 → コードレビュー 2 回 (差し戻し 1: `0013` と同じ「存在しない role を飛ばす」防御を足した)。新規テスト 12 件、変異 22 件は全部赤。完了ゲートは worktree で `3704 passed`、統合後の main (R-51 と合わさった木) で `3710 passed, 2 subtests passed`、`judge=PASS`、実行クラスタ差分 0。検知の限界 (`0013` 単独再適用の後、application を provision するまでどの検査も捕らえない) は WP-2 の runbook が持ち、構造的な直しは R-57。次は WP-2 (runbook)。WP-3 は R-50 の統合後。 **【追記 2026-09-18 (v1.66)】WP-2 と WP-4 の runbook 部分を統合した。WP-3 の前提 (R-50) が解除された。** WP-2 = runbook `MitateDB-api/docs/cloud-run-cloud-sql.md` の §3・§10 を migration `0014` に合わせた: main `da75ee2` (作業 `3c1194c`)。範囲の追加 (W2-9〜W2-11) と desk-walk レビューの記録、および WP-4 の runbook 部分を前倒しする裁定は main `1ebadf0` (作業 `f00cdd4`)。WP-4 の runbook 部分 = `0014` の改訂を受けた §10 の受理記録の取り直し (表 version 3、手順 version 6): main `96fda8c` (作業 `762c800`)。**WP-3 の前提**: 「`security/CONTROL_MAPPING.md` の WP は R-50 の統合後」という監督裁定の条件は、R-50 の WP-3 が main `d2e7333` に入って満たされた。SI-08 / MitateDB-api の既定の小ブロックは 10,190 字 (残り 5,010) で、WP-3 が追記する `0014` の算式の行は既定の小ブロックに入る。行番号は分割と WP-3 で動いており、`docs/design/MITATEDB_ROLLOUT_CONNECTION_LIMITS_V0_1.md:77` の一覧が挙げる `:548` `:641` `:647` `:650` `:659` は `:578` `:684` `:690` `:693` `:701` になった (`:5` は不変。実測は R-50 の作業指示書 §12 と設計メモ §13.5)。同一覧の更新は WP-3 の完了条件のまま。次は WP-3。 **【追記 2026-09-19 (v1.68)】実装 WP を受け入れた。行は閉じない。** WP-3 = `security/CONTROL_MAPPING.md` 版 2.9 (main `dccceeb`。追加 8・書き換え 7、完了ゲート `3733 passed, 2 subtests passed`、`judge=PASS`)。受け入れ監査 (`evidence-auditor` 1 回): 未充足 0、証拠不足 2、要訂正 3 → 監督裁定 A-1〜A-5 (作業指示書 §11) で **WP-1〜WP-4 を受け入れた**。本番には何も適用していない。**残り (本行を開けておく理由)**: (i) r2db-api の配備が 2 つの process を並走させうるかは未確認 (設計メモ §9。`security/CONTROL_MAPPING.md` の SI-08 / MitateDB-api が「ledger item R-52, still open」として開示している)。(ii) 依頼者裁定 Q-4 (`max_connections` が条件 2 に足りない場合の方針) は本番の読み取りの後。条件 2 の合計 (rollout 時 234 + reserved) は application の件数と runtime / developer の別に比例する物理的な worst case を数えない。 **【追記 2026-09-23 (v1.106)】依頼者裁定 2026-09-23: 「着手条件: 運用開始後」の印は付けない — 残り (i)(ii) は本番の読み取りの後に裁定して記録する。運用前に扱う。** **【追記 2026-09-28 (v1.130)】R-113 の設計 (`docs/design/MULTI_PROCESS_WORKER_V0_1.md` §9 (p)、監督裁定 25・33): `concurrency` の slot 共有は 1 host に閉じるので、Cloud Run の revision 切り替えで旧と新の instance が同時に serve する間は slot が共有されず上限が 2L になる。1.8.0 の in-memory 窓でも同じ 2L の破れであり、本件で解かず本行の射程 (rollout の重なりの process 数を `process_ceilings` に宣言するか) に含める。** **【追記 2026-09-30 (v1.134)】R-45 を閉じ、R-45 の行が残りとして書いていた「Mitate への報告 (R-52 を含める)」を本行の残りに移した** (依頼者裁定 2026-09-30 (逐語):「その推奨どおりに進めてください」)。送信の記録は 2026-09-30 の時点で無く、最後の記述は `docs/archive/docs/work-orders/HANDOVER_20260919_FABLE2.md`:35 の「依頼者に確認してから送る」である。 |
| **R-80** | 進行中 | L | なし | 設計レビュー (往復の時間を変えて測る手段を先に決める) | 1 要求の中の DB 往復がまとめられていない | **【追記 2026-09-23 (v1.105)】規模 M — pipeline mode の導入は両 peer のコード変更と性能計測 (Class B)。着手条件: 運用開始後 (運用が始まって data と client が存在しても直す費用は上がらない)。** **1 要求の中の DB 往復がまとめられていない (高速化案 3)。** 両 peer の src に psycopg の `pipeline()` は 0 件。本体の処理・監査の書き込み・idempotency の記録を pipeline mode でまとめ、往復を減らす。SI-11 (原子性) と SI-14 (監査) の結果を変えないことを条件にする。**Class B**。 | **起票 2026-09-21、起票のみ** (依頼者指示 2026-09-21 の高速化案の検討)。着手順は R-75〜R-77 の後に R-78 → R-79 → R-80 → R-81 → R-82 → R-85 → R-86。 R-20・P-8 の「実測前に直さない」に従い、`tools/perf_baseline.py` の基準値 (K=1 / K=3) を前後で取る。 **【追記 2026-09-24 (WP-1・WP-2 統合)】** 計測器 (Class B、harness のみ、作業指示書 `docs/work-orders/WORK_ORDER_R80_ROUNDTRIP_MEASUREMENT_V1.md` §6): `tools/perf_baseline.py --roundtrip` が op ごとに pre/post の probe と `pg_stat_database` (最短 12 秒待ち、3 回不動で確定) から `ROUNDTRIP` 行 (接続ごとの文/要求、DB ごとの transaction/要求と session/要求) を出す。実測 K=1 (`docs/design/PERF_ROUNDTRIP_MEASUREMENT_V0_1.md` v0.2 §2〜§4): r2db = runtime 6 / 7 / 11 文/要求 (query / mutate / batch)、app DB 2 tx、**platform DB 8 tx** (pool 経由、session 0); MitateDB = runtime 3 / 3 / 7 文、developer **16 / 8 / 40 文** (catalog 読み 5 / 2 / 10 transaction)、app DB 5 / 3 / 11 tx、platform 4 tx + **session 2 本/要求** (harness の `pool=None` 配線で production の値ではない)。独立で続けて送れる区間は r2db 5〜8 往復、MitateDB 25 往復 (catalog) だが、後者と r2db の catalog 2 文は **R-82 が読みごと消す**対象。**判断 (同メモ §4): pipeline 化は R-82 の後に残る独立区間 (`BEGIN` + `SET LOCAL` ×2 + savepoint 系、2〜5 往復) に対して行う方が無駄が無い — 着手順を R-82 先行に変えるかは依頼者裁定 (引き継ぎ書 §4)。** R-81 は本計測の経路に無い (harness が idempotency key を送らない)。platform DB の 8 tx (r2db) / 4 tx (MitateDB) /要求は R-83 の判断材料。完了ゲート `4018 passed`。**open のまま** (修正の WP-2 は裁定待ち)。 **【追記 2026-10-04 (v1.171)】着手条件「R-82 を先にするかの依頼者裁定」は、依頼者指示 2026-10-04 (逐語): 「R-82をチップで出してください」により「R-82 を先にする」で決着した。R-82 は同日に閉止した (記録ファイルの R-82 の節)。R-82 の後に残る独立区間は `BEGIN` + `SET LOCAL` ×2 (+ token の読み 1 文、savepoint 系) である。R-80 自体には着手していない (印「運用開始後」は残る)。** **【追記 2026-10-04 (v1.173)】「運用開始後」の印を外して修正に着手した。根拠は依頼者指示 2026-10-04 (逐語): 「R-80開始チップを出してください。」。** main `6635064` での取り直し: 文/要求は r2db runtime 5 / 6 / 10、MitateDB runtime 3 / 4 / 8 / 5・developer 3 / 3 / 3 / 3、platform DB は 12 / 4 transaction (R-83 の材料)。依存表と候補ごとの実測は `docs/design/PERF_ROUNDTRIP_MEASUREMENT_V0_1.md` v0.3 §5。**監督裁定 (依頼者の事後確認待ち)**: (1) psycopg が transaction を管理する形のままの pipeline は実装しない — psycopg 3.3.5 は pipeline mode の暗黙の `BEGIN` の直後・`commit()`・pipeline の出口で sync するので、6 往復の transaction が 5 往復になるだけで (B) と変わらず、直結では遅くなる (p50 0.080 → 0.105 ms)。(2) (B) `set_config` の 1 文化は実装しない — 1 transaction あたり −0.013 ms、要求の p50 の 0.6%〜2.5%、往復数の比の上限でも 5.3% (r2db) / 14.3% (MitateDB) で雑音の範囲 (§0.1.4)。(3) autocommit の接続に `BEGIN` / `COMMIT` を文として流し要求ごとに pipeline に入る形 (レビュー担当の実測: query の transaction 6 → 2 往復、data 操作 7 → 2〜3 往復) は、直結では時間の差が無く (0.076〜0.083 対 0.079〜0.080 ms)、効果は DB が別ホストの配備でだけ現れる (往復数の比の上限は r2db query 21%、MitateDB query 57%。その配備の往復 1 回の時間は未実測で、`tools/perf_baseline.py` は往復の時間を変えて測れない)。両 peer の transaction の境界 (SI-11 の制御、idempotency の savepoint、R-79・R-42 の機構、error code への対応) を psycopg の管理から外して作り直す Class D の変更であり、**規模を M から L に上げ (運用条件 §1.13 の 73)、着手条件を設計レビューにする。** 設計は先に、往復の時間を変えて測る手段と判定の閾値を決める。**本変更セットではコードを変えていない** (完了条件と変異の対応は無い)。open のまま。 **【追記 2026-10-04 (v1.174)】依頼者の事後確認 (逐語): 「確認事項は了承します」 — v1.173 の追記の監督裁定 (1)〜(3) と、引き継ぎ書 `docs/work-orders/HANDOVER_20261004_R80_FABLE.md` §4 の 5 件の全件。** |
| **R-81** | 未着手 | M | あり | - | idempotency の記録の往復数を減らす | **【追記 2026-09-23 (v1.105)】規模 M — idempotency 記録の往復削減は両 peer のコード変更 (Class B、記録形式に触れれば C)。着手条件: 運用開始後 (運用が始まって data と client が存在しても直す費用は上がらない)。** **idempotency の記録の往復数を減らす (高速化案 4)。** 「探してから入れる」を `INSERT … ON CONFLICT … RETURNING` の 1 文に寄せる。現行の文と往復数は着手時に実測する (両 backend は既に `ON CONFLICT` を使う箇所を持つ)。同じ key の同時要求の直列化 (R-24、条件 C-27) を崩さないことを条件にする。**Class B** (conformance を触るなら C)。 | **起票 2026-09-21、起票のみ** (依頼者指示 2026-09-21 の高速化案の検討)。着手順は R-75〜R-77 の後に R-78 → R-79 → R-80 → R-81 → R-82 → R-85 → R-86。 R-20・P-8 の「実測前に直さない」に従い、`tools/perf_baseline.py` の基準値 (K=1 / K=3) を前後で取る。 |
| **R-83** | 未着手 | L | あり | 設計レビュー | API キーの検証結果のキャッシュ | **【追記 2026-09-23 (v1.105)】規模 L — API キー検証結果のキャッシュは認証経路 (Class C / D 見込み、設計レビュー)。着手条件: 運用開始後 (運用が始まって data と client が存在しても直す費用は上がらない)。** **API キーの検証結果のキャッシュ (高速化案 6)。** 短い有効期限でキャッシュし、要求ごとの認証の DB 往復を減らす。SI-13 (失効と無効化の実効性) は宣言した伝播の上限の内で失効が効くことを求めるので、上限の宣言と「失効したキーがキャッシュから通らない」ことを確かめるテストの形を先に決める。**設計レビューを着手条件にする。** 変更クラスは設計で決める (宣言を足すなら C / D)。 | **起票 2026-09-21、起票のみ** (依頼者指示 2026-09-21 の高速化案の検討)。R-78〜R-82 の結果を見てから、設計レビューを経て着手するかを決める。 |
| **R-101** | 進行中 | M | なし | 依頼者の着手判断 | 1 process 内の直列化の主体が切り分けられていない | **【追記 2026-09-23 (v1.105)】規模 M — 直列化主体の切り分けは計測 (tools) と判断で、コード変更は結果次第。** **1 process 内の直列化の主体 (uvicorn の threadpool / GIL / PostgreSQL 往復) が切り分けられていない。** R-78 の sweep (`docs/design/PERF_CONCURRENCY_MEASUREMENT_V0_1.md` §3 の 3) で両 peer の p50 が K にほぼ比例して伸び、r2db は pool 待ち 0 (size 32) でも同じ形だった。asgi-inprocess と socket の両転送で同じ形なので、client と server が同 process・同 GIL にいる計測の限界でもある。候補: threadpool の寸法の sweep (uvicorn / anyio の limiter)、server を別 process にした socket 計測、`py-spy` 等でのプロファイル。R-84 (async psycopg) の着手条件の判定材料。**Class B** (tools)。 | **起票 2026-09-23、起票のみ** (R-78 WP-2 の判断 (2)、監督裁定)。着手・直し方は未定で、本件では何も直さない。 **【追記 2026-09-27 (v1.128)】WP-1 (計測器) と WP-2 (実測と判定) を実施した。閉じない (閉止形は §0.1.4 の 2)。** 作業指示書 `docs/work-orders/WORK_ORDER_R101_SERIALIZATION_ATTRIBUTION_V1.md` (v1.0 + §6.1 の訂正註 1〜9・監督裁定 1〜8、**Class D** = 依頼者裁定「D で進める」の逐語は同 §6.1、規模 M)。**WP-1**: 両 peer の `psycopg_counting.py` に接続単位の `db_wall_ms` / `txn_count` (execute / executemany / commit / rollback / `transaction()` の enter・exit で加算、byte 一致の sha256 pin 維持)、r2db `_RolePool` と MitateDB credential store / audit sink の「閉じる前の畳み込み」+ 統計専用 lock (AST 静的 pin 3 箇所)、`tools/perf_baseline.py` の `CPU` 行 (getrusage + thread_time、measured 窓のみ) と `DBTIME` 行 (scope=app / platform、PRE/POST 差分)、両 http adapter の `DSA_PERF_THREAD_LIMIT` (loop ごとに anyio 既定 limiter を設定する ASGI wrapper、`perf_thread_limit()` / `platform_db_time_stats()` accessor)。同名 helper 6 つ (env 読み取り・wrapper・accessor + AST pin の helper 3 つ) を `_ISOMORPHIC_TARGETS` に登録 (件数 pin 159 → 167、R-112 の 2 行と合算)。`security/CONTROL_MAPPING.md` は SI-08 Evidence の参照追随のみで 3.5 (Control 主張の追加・変更なし)。契約 1.11.0・`spec/`・`conformance-tests/` 不変。完了条件 77 件、変異 M1〜M64c・M100〜M112 + レビュー / 監査の自作分、コードレビュー 2 回 (opus)、受け入れ監査 1 回 (充足 77 / 未充足 0 / 証拠不足 0)。完了ゲート (監督、solo、使い捨てクラスタ、最終 tree `3d10d7d`): `label r101b gate: 4314 passed, 2 subtests passed in 334.79s (0:05:34)`、judge=PASS、pg_database/pg_roles diff 0 (main `31f981d` の 4262 + 52); `tools/tests` `pt: 613 passed`。**WP-2** (設計メモ `docs/design/PERF_SERIALIZATION_MEASUREMENT_V0_1.md` v0.2 §2〜§4、判定規則は計測前に固定した D-5 の逐語): 非退行 ±10% 内 (K=1 3 組・K=3 1 組。1 組目の r2db-http batch +11.7% は同条件 2 組で +3.5% / +0.3% と再現せず)、sweep 10 run (thread limit {既定 40, 4, 1} × K {1, 4, 32} + 既定 × K=32 の 2 回目、ε ≤ 2.9%、δ = 10%)。**判定 (§4)**: 4 plug (r2db / MitateDB × http / socket) すべてで **J-2 成立 = 直列化の主体は Python の CPU (GIL)** (r = cpu_total / wall = 2.2 / 1.4 / 6.5 / 4.5、うち server 側の CPU が主なのは r2db-socket 以外の 3 plug)、MitateDB の 2 plug は **J-5 も成立 (cell lock の待ち = R-102。K=32 で acquire の 47% が待ち)**、J-3 (DB 往復の待ち) はどの plug でも不成立、判定不能の plug は無し。**threadpool は不足の意味では律速でない** (limit 1 でも p50 は ±δ 内) が、**thread 数を減らすと速くなる** (limit 4 は既定 40 より p50 で 30〜49%、p95 で 28〜44% 速い。r2db-socket を除く 3 plug。J-1 (i) の場合分けの外として事実で記録)。**§0.1.4 の 2 に対する現状**: `query` p50 の K=32 / K=1 = **33.3 / 31.8 / 29.9 / 29.5 倍** (limit 4 でも 15.2〜32.9 倍) で、8 倍以内はどの plug も満たさない。是正の候補 (composition root の limiter 縮小、multi-process worker、R-102、R-84) は設計メモ §4 の 5 に列挙し、**是正 WP は作業指示書 v1.1 で足す (是正の形は依頼者確認)**。R-84 の再検討条件は R-84 行に追記。 **【追記 2026-09-28 (v1.129)】是正 WP-3 / WP-4 を実施した (作業指示書 v1.1 §7〜§12、Class D、規模 M × 2、依頼者裁定の逐語は §6.1)。** 前提の発見: 計測器の床 (client が同 GIL) のため §0.1.4 の 2 は現行 plug では出ない (同書 §7.1) → 計測器を real-server plug に改めた (§0.1.4 の 2 の改訂)。WP-3: 両 peer の `create_app` に thread limiter middleware (既定 4、`R2DB_THREAD_LIMIT` / `MITATEDB_THREAD_LIMIT`、`None` か正整数以外は `ValueError`)、adapter は `DSA_PERF_THREAD_LIMIT` の実効値を渡す、MitateDB http adapter の credential store に production と同じ platform pool + `BoundedConnectionPool` の閉じる前の畳み込み、`_ISOMORPHIC_TARGETS` 167 → 169、CM 3.6 (参照追随のみ)。WP-4: `tools/perf_baseline.py --real-server <peer>` / `--client-processes N` (registry の `composition_roots` の launcher、control credential の自己 rotate → developer credential 発行 → entity、`query` を runtime bearer で、`REALPERF` / `REALCPU` 行)。コードレビュー各 2 回 (opus)、完了ゲート (最終 tree) `label r101c gate: 4342 passed, 2 subtests passed in 323.21s (0:05:23)`、judge=PASS、pg_database/pg_roles diff 0 (main `2e746cc` の 4314 + 28。中間 tree d7a7500 の r101b も 4342 / PASS)。**D-12 成立** (設計メモ v0.3 §5: K=32 の `query` p50 が基準比 −41.4 / −10.7 / −80.4 / −51.1% (r2db-http / r2db-socket / MitateDB-http / MitateDB-socket)、K=1 は −6.1 / +0.1 / −79.9 / −53.1%、`thread_limit=4`、MitateDB platform の per-call connect 0)。現行 plug の K=32 / K=1 は 20.8 / 28.4 / 29.2 / 30.8 倍 (床のとおり)。**【訂正 2026-09-28 (v1.129、監督裁定 20)】下の「D-16 成立 → 閉止」は計測器の欠陥 (client の子 process が group ごとに生成され K=1 の分母に初回コストが入る。受け入れ監査の観察 1、作業指示書 §6.1 裁定 17) による見かけで無効。欠陥を直した計測器 (D-15a) での 2 回目は不成立 (r2db 15.72 / 15.76 倍、MitateDB 18.67 / 18.83 倍。設計メモ v0.3 §6) で、R-101 は閉じない。行は R-14 のとおり残す。** **D-16 (real-server plug) 1 回目 成立 → R-101 を閉止する (無効、上の訂正)** (設計メモ v0.3 §6: `--real-server`、server 1 process、client 8 process、`--warmup 3 --n 15`。`query` p50 K=1 / K=32 (2 run) = r2db 10.425 / 48.265・47.712 ms = **4.63 / 4.58 倍**、MitateDB 10.905 / 46.761・46.571 ms = **4.29 / 4.27 倍**、ε 1.1% / 0.4%)。観察 (依頼者へ、引き継ぎ書 §4): この計測器の K=1 の分母は client 自身の CPU (8.0 / 8.3 ms/req、`REALCPU`) が 74〜77% で、server の直列化に対して甘い。socket plug の K=1 を分母にすると 10.0 / 10.1 倍。閉止をこの形で受理するか分母を再改訂するかは依頼者判断。 **【追記 2026-09-29 (v1.131)】R-113 (multi-process worker) の実施後に D-16 を 4 worker で測った。閉じない。** 設計 `docs/design/MULTI_PROCESS_WORKER_V0_1.md` §7.4 の表 7-1 (`--real-server <peer> --workers 4 --warmup 3 --n 15`、宣言値の `concurrency` 32、thread limit 4、client process は min(8, K)、木 `17cc7fa`): 正式の run (手順どおりの 1 回目) では `query` p50 の K=32 / K=1 が r2db 6.78 / 7.24 倍、MitateDB 7.60 / 7.40 倍で、規則 (R-113 作業指示書 `docs/work-orders/WORK_ORDER_R113_MULTI_PROCESS_WORKER_V1.md` §10.1 = R-101 作業指示書 §10.1 の D-16、逐語) の文字どおりには 8 以下。同じ手順の繰り返し 2 回では最大 10.30 倍 (12 個の比のうち 8 超が 5 個)。N = 1 の対照は r2db 10.92 / 10.76 倍、MitateDB 18.18 / 18.22 倍。**依頼者裁定 (2026-09-29、逐語): 「R-101は閉じない」** (R-113 作業指示書 §6.1 の監督裁定 55)。却下した案: 規則の文字どおりに閉じる (依頼者裁定で閉じない)。読み: multi-process の効果は在る (K=32 の p50 が N = 1 の約 39 ms から N = 4 の約 25 ms) が、worker の外に直列の区間が残る。切り分けの候補 (未計測): 同じ credential の rate の行の取り合い、slot の走査を直列にする `scan` の lock (host の全 worker で 1 本)、client 側の床、nginx。K=32 の p50 は 23.5〜27.7 ms で安定し、揺れているのは分母の K=1 で、n = 15 では 2.5〜3.8 ms の幅で揺れ、比の判定を不安定にしている。D-16 の規則と手順 (K=1 の標本数を含む) は依頼者裁定 (2026-09-27) で固定したもので、変えるなら依頼者裁定が要る。同日の 1 回目の 12 run は load average 12〜15 の下で取ったので無効として捨てた (設計 §7.4)。 | ~~閉止 2026-09-28~~ → **開いたまま (訂正 2026-09-28、監督裁定 20)**: 欠陥を直した計測器での D-16 は不成立 (15.7 / 18.7 倍)。次は R-113 (multi-process worker、規模 L) の着手 = 依頼者判断。 **【追記 2026-09-29 (v1.131)】開いたまま** (依頼者裁定「R-101は閉じない」)。R-113 は閉止した。次は worker の外に残る直列の区間の切り分けで、着手は依頼者判断。 |
| **R-106** | 未着手 | L | なし | Mitate の実需 | MitateDB-api に row_addressability を実装する | **規模 L — 宣言値と保存形の両方に触れ (P-3 により最低 Class C)、契約 `structured_operations.mutation_classes` の規則 (`row_addressability` が enabled のとき entity ごとに 1 クラス) と `upsert` の規則が同時に効くので、設計レビューを要する。計画文書 **R-49** (mutation class の実装) と論点を共有する。** **MitateDB-api に `row_addressability` (mutation class と住所指定) を実装する** — 宣言を `unavailable` から動かし、entity ごとの mutation class と行の住所を契約の語彙どおり持たせる。 出所: 設計 `docs/design/PHASE11_MIN_COMMON_PROFILE_V1.md` §16 (v1.0、2026-09-24、規模は監督が決めた)。 | **起票 2026-09-25** (依頼者裁定 2026-09-24 U-2「MitateDB に row_addressability / revision_preconditions を足す新規起票 2 件 + 既存 R-49 に付け替える」、フェーズ11 R-29 の閉止に伴う)。着手条件: **Mitate の実需** (設計 §1.6 の逐語 (1)(2): `append_only` への対応付けが「両 peer に実装が無い」「本番 peer は `row_addressability: unavailable` で宣言自体が成り立たない」)。 |
| **R-107** | 未着手 | L | なし | Mitate の実需 | MitateDB に revision_preconditions を実装 | **規模 L — 宣言値 + 保存形 + 契約の意味論に触れる (R-106 と同じ)。複数 instance 化の前提であり、計画文書 **R-102** (application ごとの直列化) と干渉しうる。** **MitateDB-api に `revision_preconditions` (`expected_revision`) を実装する** — 宣言を `unavailable` から動かし、revision の保持と precondition の判定を持たせる。 出所: 設計 `docs/design/PHASE11_MIN_COMMON_PROFILE_V1.md` §16 (v1.0、2026-09-24、規模は監督が決めた)。 | **起票 2026-09-25** (依頼者裁定 2026-09-24 U-2、R-106 と同じ)。着手条件: **Mitate の実需** (設計 §1.6 の逐語 (3)(4): solutionName の一意性は「`row_addressability`/unique 制約が unavailable のため Data Service では守れない」、§12 の (g) 行「`revision_preconditions`(§2.C.7。複数 instance 化の前提。DM-0025)」は「**未着手**」)。 |
| **R-124** | 未着手 | S | なし | 契約の path 規則の確認 | order_by 項目の details.field path の peer 差 | **規模 S — 不正な direction と order_by 項目の形の違反で返す `details.field` が peer で違う (R-39 の棚卸し、reader 2026-10-05): r2db は `order_by/direction`・`order_by` (`paging.py` の非 index 形)、MitateDB の cell 層は `order_by/<i>/direction`・`order_by/<i>` (`cell.py`)、MitateDB の backend は r2db と同じ非 index 形。共通契約 `spec/` が項目位置を要求するか (undeclared field の position path との整合) を確認し、片方に揃える。R-39 CS-1 の C1-5b は r2db の現行値 `order_by/direction` を pin しているので、揃えるときはそのテストを同じ変更セットで動かす。** | 契約の確認 → 揃える peer の tests + src (Class B)。契約文の変更が要れば Class C |

### 8.2 閉止・却下の索引

| ID | 状態 | 閉止日 | 件名 |
|---|---|---|---|
| **R-2** | 閉止 | 2026-09-08 | 制約宣言 (enum・nullable) と同版 catalog 報告 |
| **R-3** | 閉止 | 2026-09-08 | 検証エラーの固定 details 語彙 |
| **R-4** | 閉止 | 2026-09-08 | dry_run と無状態 plan トークン、認可 dry_run |
| **R-5** | 閉止 | 2026-09-08 | idempotency の両 peer 実装と契約追記 |
| **R-6** | 閉止 | 2026-09-08 | request budget (3 class から) |
| **R-7** | 閉止 | 2026-09-08 | 成功応答の request_id |
| **R-8** | 閉止 | 2026-09-08 | 契約 JSON 派生の操作カタログと再生成一致テスト |
| **R-9** | 閉止 | 2026-09-07 | CI のテスト総数下限 |
| **R-10** | 閉止 | 2026-09-07 | 契約 JSON の現行/履歴分離 (WP-7 方式) |
| **R-12** | 閉止 | 2026-09-07 | 性能基準値ハーネスと集計行形式 |
| **R-15** | 閉止 | 2026-09-07 | 開発プロセス衛生 v1 |
| **R-16** | 閉止 | 2026-09-25 | scenario 級 conformance の新設 |
| **R-17** | 閉止 | 2026-10-04 | 公開ゲート実施記録の空ファイル化 |
| **R-18** | 閉止 | 2026-09-09 | 資源制限 enforced の適用単位が契約で未定義 |
| **R-19** | 閉止 | 2026-09-08 | 本番 image の依存解決が CI と一致しない |
| **R-20** | 閉止 | 2026-09-10 | HTTP handler が同期 service / psycopg を直接呼ぶ |
| **R-21** | 閉止 | 2026-09-08 | 正本文書の陳腐化 |
| **R-23** | 閉止 | 2026-09-25 | AI エージェント向けの機械可読派生物の不足 |
| **R-24** | 閉止 | 2026-09-10 | 同一 idempotency key の同時要求が直列化されない |
| **R-25** | 閉止 | 2026-09-10 | MitateDB が budget: {} を digest から落とす |
| **R-26** | 閉止 | 2026-09-10 | CI が skipped / xfailed = 0 を強制していない |
| **R-27** | 閉止 | 2026-09-10 | sweep_orphans に pid <= 0 の明示 guard が無い |
| **R-28** | 閉止 | 2026-10-04 | 正本文書の陳腐化 (R-21 の残余) と構造的原因 |
| **R-29** | 閉止 | 2026-09-25 | 最低共通機能プロファイルが無い |
| **R-30** | 閉止 | 2026-10-03 | SI-00 の境界と複数 Application DSN 保持の関係 |
| **R-32** | 閉止 | 2026-09-14 | 検証 seam と同型性の分離 |
| **R-33** | 閉止 | 2026-10-03 | cell 経路と HTTP 経路で digest の材料が食い違い得る |
| **R-34** | 閉止 | 2026-09-08 | 完了ゲートの root suite に負荷依存の timing テストがある |
| **R-35** | 閉止 | 2026-09-10 | nullable 違反走査の LOCK TABLE が deadlock する |
| **R-37** | 閉止 | 2026-09-16 | 巨大モジュールの段階的リファクタリング |
| **R-38** | 閉止 | 2026-09-26 | r2db in-memory ORDER BY と jsonb 順序の食い違い |
| **R-39** | 閉止 | 2026-10-05 | 複数のテストの穴の一括追跡 |
| **R-41** | 閉止 | 2026-09-26 | 削除確認 phrase の契約規則を conformance で固定 |
| **R-42** | 閉止 | 2026-10-03 | 期限切れ要求の意味論 |
| **R-44** | 閉止 | 2026-10-04 | テストが共有 PostgreSQL を使う問題 (使い捨てクラスタ化) |
| **R-45** | 閉止 | 2026-09-18 | MitateDB-api の operation_depth の upgrade |
| **R-46** | 閉止 | 2026-09-30 | 公開値スキャナで入れ子 URL の deny suffix が効かない |
| **R-48** | 閉止 | 2026-09-18 | role の statement_timeout を設定する経路が無い |
| **R-50** | 閉止 | 2026-09-19 | CONTROL_MAPPING SI-08 ブロックが上限に張り付く |
| **R-51** | 閉止 | 2026-09-18 | audit_query が psycopg.Error を個別に扱わない |
| **R-53** | 閉止 | 2026-09-18 | ops.py の help 文が現物と食い違う 3 箇所 |
| **R-54** | 閉止 | 2026-09-19 | runbook §9 が provision role の自己 GRANT 形 |
| **R-55** | 閉止 | 2026-09-19 | ops.py のコメントと docstring に作業期の文言が残る |
| **R-56** | 閉止 | 2026-09-20 | auditreader に statement_timeout が無い |
| **R-57** | 閉止 | 2026-09-20 | 単独再適用を apply-platform-migration が扱わない |
| **R-58** | 閉止 | 2026-09-20 | dsa_testpg.py が PGPASSWORD を消す |
| **R-59** | 閉止 | 2026-09-19 | SI-09 / MitateDB-api の既定の小ブロックが上限近い |
| **R-60** | 閉止 | 2026-09-20 | SI-08's own MitateDB-api block の指し方が非一意 |
| **R-61** | 閉止 | 2026-09-20 | CONTROL_MAPPING に失効した作業期の本番制限が残る |
| **R-62** | 閉止 | 2026-09-21 | PostgresCell.catalog が timeout を通らない |
| **R-63** | 閉止 | 2026-09-20 | §4.1 が新しい関数の docstring を書けなくする |
| **R-64** | 閉止 | 2026-09-21 | Evidence の ::test_ 名を解決する検査が無い |
| **R-65** | 閉止 | 2026-09-21 | CONTROL_MAPPING SI-08 の既定の小ブロックの残りが少ない |
| **R-66** | 閉止 | 2026-09-22 | r2db-api 配備 script が 0013 を流していない |
| **R-67** | 閉止 | 2026-09-22 | 両 peer の auditreader 検査に docstring が無い |
| **R-68** | 閉止 | 2026-09-20 | --base が登録済みコメントの言い換えを通さない |
| **R-69** | 閉止 | 2026-09-22 | 部分的に縮約済みの文は R-68 の経路でも言い換えられない |
| **R-70** | 閉止 | 2026-09-21 | Platform-upgrade の Control が弱く読める |
| **R-71** | 閉止 | 2026-09-21 | catalog の打ち切りを VALIDATION_FAILED に写す |
| **R-72** | 閉止 | 2026-09-23 | production-restriction の states が網羅と読める |
| **R-73** | 閉止 | 2026-09-22 | MAX_BLOCK_LENGTH の上のコメントが古い |
| **R-74** | 閉止 | 2026-09-23 | CONDITIONS.md が引くテスト名を解決する機械検査が無い |
| **R-75** | 閉止 | 2026-09-22 | 両 peer の src/ で SQL の構築形を見る静的走査が無い |
| **R-76** | 閉止 | 2026-09-22 | src の循環 import を検査するテストが無い |
| **R-77** | 閉止 | 2026-09-22 | 文字列注釈だけが読む名前を読み手 0 と誤判定し得る |
| **R-78** | 閉止 | 2026-09-23 | 接続プールの寸法と待ちが計測されていない |
| **R-79** | 閉止 | 2026-09-23 | prepared statement が効いているかが分からない |
| **R-82** | 閉止 | 2026-10-04 | スキーマ情報を要求ごとに読み直している可能性 |
| **R-84** | 却下 | 2026-09-28 | async psycopg への移行 |
| **R-85** | 閉止 | 2026-09-24 | テスト DB の template 複製 |
| **R-86** | 閉止 | 2026-09-24 | 遅いテスト一覧が常設されていない |
| **R-87** | 閉止 | 2026-09-23 | catalog 読み 8 本の上限が execution_ms に追随しない |
| **R-88** | 閉止 | 2026-09-23 | CONTROL_MAPPING の位置参照を検査する機械検査が無い |
| **R-89** | 閉止 | 2026-09-23 | 来歴検査 §4.1 (2) が直後の文の変更で赤になる |
| **R-90** | 閉止 | 2026-09-23 | r2db-api に apply-platform-migration が無い |
| **R-91** | 閉止 | 2026-09-23 | max_connections を検査する箇所が無い |
| **R-92** | 閉止 | 2026-09-22 | F-12 の案内文が --lock-timeout を含まない |
| **R-93** | 閉止 | 2026-09-22 | 0005 ヘッダの R2DB_PLATFORM_POOL_SIZE 記述が陳腐化 |
| **R-94** | 閉止 | 2026-09-22 | 読み手 0 で記録も無い import が 2 件ある |
| **R-95** | 閉止 | 2026-09-23 | conformance docstring の位置参照の陳腐化 |
| **R-96** | 閉止 | 2026-09-23 | src・tests の docstring の位置参照に機械検査が無い |
| **R-97** | 閉止 | 2026-09-30 | script が psql -f の path を検査しない |
| **R-98** | 閉止 | 2026-09-23 | superseded-by の静的導出が綴り違いを別 target と見なす |
| **R-99** | 閉止 | 2026-09-30 | MitateDB の test が tempdir を 5 個残す |
| **R-100** | 閉止 | 2026-09-23 | change_class.py が分類行を出さない path がある |
| **R-102** | 閉止 | 2026-10-01 | MitateDB のデータ面は application ごとに直列化される |
| **R-103** | 閉止 | 2026-09-24 | CONTROL_MAPPING を形式 2.25 から 3.0 へ移行する |
| **R-104** | 閉止 | 2026-09-24 | CONTROL_MAPPING 3.0 の Evidence が増えた |
| **R-105** | 閉止 | 2026-09-24 | conformance テスト 20 件の作り替え |
| **R-108** | 閉止 | 2026-10-01 | 契約文書だけで要求を組む参照クライアント |
| **R-109** | 閉止 | 2026-09-25 | 契約 1.9.0 → 1.10.0 (keyset ページング) |
| **R-110** | 閉止 | 2026-09-25 | order_by の未知 field の拒否コードが両 peer で違う |
| **R-111** | 閉止 | 2026-09-26 | MitateDB http の credential repair 経路 |
| **R-112** | 閉止 | 2026-09-26 | order_by の文字列の比較順序が backend 間で違う |
| **R-113** | 閉止 | 2026-09-29 | multi-process worker の limit 状態の置き場 |
| **R-114** | 閉止 | 2026-09-30 | audit_requests_per_minute の窓の形の契約と実装の差 |
| **R-115** | 閉止 | 2026-10-01 | SIGKILL された worker の audit buffer 欠落 |
| **R-116** | 閉止 | 2026-09-30 | Gate-0 の起動時の検査の紙の検算を道具に移す |
| **R-117** | 閉止 | 2026-09-30 | 台帳の固定欄と閉止行の回転 |
| **R-118** | 閉止 | 2026-10-03 | audit_query の alias の保持期限の文言が現物と食い違う |
| **R-119** | 閉止 | 2026-10-01 | MitateDB の read_page の decode が lock の外 |
| **R-120** | 閉止 | 2026-10-03 | r2db の DML 検証と書き込みの間の alter の窓 |
| **R-121** | 閉止 | 2026-10-02 | socket 経路の redirect 先に宣言の port が無い |
| **R-122** | 閉止 | 2026-10-04 | MitateDB socket 隔離面の control URL が無応答 |
| **R-123** | 閉止 | 2026-10-06 | r2db `pg_text_format` の実 PG との不一致 |

### R-23 着手前調査資料（非正本）

[`R23_AGENT_DERIVED_ARTIFACT_READINESS_20260913.md`](R23_AGENT_DERIVED_ARTIFACT_READINESS_20260913.md) は、現行の契約・catalog・capability discovery・関連 conformance を調べた**着手前調査資料**である。**未承認の提案であり、R-23 / R-29 の設計判断、優先度、契約、conformance、実装または配備を拘束しない。** 他のAIを含む読者は、これを実装指示や採用済み設計として扱ってはならない。R-23 または R-29 を実際に着手する前に、当時の正本・実装・capability・Security Invariants・実需を再照合し、採用する範囲を設計レビューで明示的に確定する。再照合後も有効な事実調査は再利用してよいが、提案・順序・具体例を無批判に継承してはならない。

---

## 9. 各フェーズの着手手順

1. 本書の該当フェーズ節を読み、範囲・着手条件・守るべき条件を設計文書 v1.0 の §1〜§2 に転記する (再導出しない)。
2. 設計文書は `docs/design/PHASE<n>_<name>_V1.md`、作業指示書は `docs/work-orders/WORK_ORDER_PHASE<n>_<name>_V1.md`。
3. 契約を触るフェーズは設計レビュー 2 回、触らないフェーズは 1 回。
4. 依頼者裁定は設計文書に逐語で記録し、再審議しない。
5. 完了ゲートは root suite の単独実行 (`pytest -q -n 5 --dist loadgroup`) と CI 3.11 job の集計行、および R-12 確定後は性能差分。
6. フェーズ完了時に本書 §1「現状」と §8 の行き先を更新する (R-14)。

7. 着手前に `docs/work-orders/OPERATING_CONDITIONS.md` を読む。**運用条件 (役割分担・コミット規約・ゲートの実行法・開発機の環境条件・CI の条件) の正本は同ファイルであり、引き継ぎ書はフェーズ固有の差分のみを持つ。** 既存の引き継ぎ書は履歴として書き換えない。

8. **変更クラス。** **触れるファイルの集合だけで機械的に決まり** (肯定列挙)、**クラスは必要な証拠の量を決める** (証拠を省略するための仕組みではない)。

   | Class | 触れる対象 (肯定列挙) | 必要な証拠 |
   |---|---|---|
   | **A** | **`.md` のみ** (ただし `spec/`・`security/`・`conformance-tests/` 配下の `.md` を除く)、**および `docs/archive/` 配下の全ファイル** (拡張子を問わない。v1.111、設計 `docs/design/DOC_ARCHIVE_SPLIT_V1.md` D-3 (iii)) | pre-commit (`public_value_scan` + `check_doc_refs`) + 監督確認。commit + push + main merge |
   | **B** | **A でも C でも D でもない全ファイル** — 両 peer のコード、`tools/`、CI 定義、pre-commit 定義、fixture | 触った peer の suite + Opus コードレビュー (報告に無い変異 1〜2 種) + マージ時に監督の root suite 単独実行 |
   | **C** | 契約 JSON、`spec/` 配下、`conformance-tests/` 配下、catalog 宣言値、**`_ISOMORPHIC_TARGETS` に登録された helper の本体** | フェーズ設計文書 + 契約版数の更新 + 設計レビュー 2 回 + 完了ゲート全部 (§9 の 5) |
   | **D** | `security/` 配下、`CLAUDE.md` の境界節、**`_ISOMORPHIC_TARGETS` 集合の増減** (登録 helper の追加・削除)、公開ゲート (`docs/security/public-repository-policy.md` と `tools/public_value_scan.py` の規則) | C の全部 + 依頼者裁定の逐語記録 + 版付きの security-contract 決定 |

   **1 つのコミットが複数のクラスに触れるときは、最も重いクラスを採る。**

   **P-6 により、片 peer だけの「内部変更」は B にならない** — 登録済み同型 helper の本体に触れれば C である。**P-3 により、宣言値に触れる変更は最低 C である。** **`docs/work-orders/OPERATING_CONDITIONS.md` の変更は A である** — ただし §1 (恒久の運用規律) の行を変えるときは依頼者確認を添える。

9. **作業指示書はフェーズ10 から、WP ごとの Change Set Manifest とする。** 必須項目は以下である。

   - 目的 (1〜3 行)
   - 読むべき正本 (ファイル + 節番号)
   - 触るファイル
   - 触らないファイル
   - **完了条件 ↔ 変異の 1 対 1 表** (`file:操作` → 赤になる test id)
   - 検証コマンドと集計行の期待形
   - 使用テンプレート番号
   - 変更クラス (§9 の 8)

   **設計の逐語表・裁定文・却下案・背景は manifest に写さず、設計文書の節番号で指す。** 訂正註の慣行 (本文を書き換えず註で直す) は維持する。**目安は WP あたり 5〜10 KB** である (実測: フェーズ9 作業指示書の WP-1 節 44.7 KB のうち、発注に必要な情報は 6.4 KB = 14.3%)。

10. **テストは三段である。** 新しい仕組みは無く、現行運用の明文化である。

    | 段 | いつ | 何を回すか |
    |---|---|---|
    | 開発中 | 実装担当が随時 | 触った peer の suite + 該当する conformance ファイル |
    | 統合前 | WP を branch へ取り込むとき | **監督**の root suite 単独実行 |
    | 完了ゲート | フェーズ完了時 | §9 の 5 (root suite + CI 3.11 の集計行 + 性能差分) |

11. **完了ゲートに `tools/check_doc_refs.py` を加える** (CI の 3.11 / 3.12 両 job、pytest の前段)。**ID 族と正本ファイルの対応表は script 内の定数であり、更新は明示コミットのみで行う** (`COLLECTION_FLOOR` と同じ規約)。
    **【訂正注 2026-09-07 (v1.4)】CI 上の位置は「3.11 / 3.12 両 job の pytest 前段」ではなく、常時実行の独立 job `doc-refs` である (Class A の push では conformance job が回らないため。§9 の 8 の CI 実装は設計 D-4)。上の本文は原文として残す。**

12. **規模と着手順。** 各項目の規模 (S / M / L) は起票時に監督が内容から決めて行の冒頭に記し (v1.133 から §8.1 の規模の欄。`docs/work-orders/OPERATING_CONDITIONS.md` §1.16 の 79)、手順の重さは `docs/work-orders/OPERATING_CONDITIONS.md` §1.13 の表が決める (変更クラス (8) は証拠の量を決め、規模は役割の数と記録の回数を決める。証拠は減らさない)。**着手順は、印なし > 「着手条件: 運用開始後」** — 印の問いは「運用が始まって data と client が存在すると、直す費用が上がるか」であり、上がる項目 (契約と保存形に触れるもの) を運用前に済ませ、上がらない項目は運用開始後に着手する。印なしの行に別の着手条件 (依頼者裁定待ち、公開化の前、push 再開後、本番の読み取りの後 等) が書かれていればそれに従う。(依頼者指示 2026-09-23、v1.105) 規模・印・着手条件は §8.1 の固定欄に記し (語彙は設計 `docs/design/LEDGER_FIXED_FIELDS_V1.md` D-2)、未閉止行を着手順に並べた一覧は `tools/dev/ledger.py --open` が出す。(v1.133)

13. 台帳の閉止判断は §0.1 (終わりの定義) に対して行う。§0.1 を満たした時点で台帳は完成であり、以後の起票は §0.1 の但し書きに従う。(依頼者 2026-09-23、v1.107)

14. レビュー担当・監査担当の指摘のうち同じ変更セットで直さなかったものは、監督が 1 件ごとに 起票 / 既知の穴 / 観察 に裁定し、引き継ぎ書の「裁定」節に全件残す。起票前の 2 問と観察の扱いは `docs/work-orders/OPERATING_CONDITIONS.md` §1.15 の 77。(依頼者 2026-09-23、v1.109)
