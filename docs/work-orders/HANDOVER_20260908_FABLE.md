# 引き継ぎ — 2026-09-08 (第16次。フェーズ9 — 契約 1.7.0「宣言と検証」。契約は 1.6.0 → **1.7.0**)

- 引き継ぎ元: Fable (監督)。実装: Sonnet subagent、レビュー/起草/受け入れ監査: Opus subagent (各 WP で独立レビュー + 変異注入を継続)
- 引き継ぎ先: 次セッションの Fable (同体制継続)
- 前提: **第15次 `HANDOVER_20260907_FABLE.md` (フェーズ8) と、そのさらに前の引き継ぎの約束事は全て継続**する。**現在地のみ本書が上書きする**
- **運用条件 (役割分担・コミット規約・ゲートの実行法・開発機の環境条件・CI の条件) の正本は `docs/work-orders/OPERATING_CONDITIONS.md` である** (計画文書 §9 の 7。並行セッションの「開発プロセス衛生 v1」が本フェーズ中に main へ入った)。**本書はフェーズ固有の差分だけを持つ。**
- 本書は**フェーズ9 (契約 1.7.0「宣言と検証」) の WP-0〜WP-4 を完了したセッションの記録**である。**契約は 1.6.0 から 1.7.0 へ上がった** (3 複製の sha256 で示す)。**新しい Security Invariant は足していない** (設計 §2 の C2、§7)。**実機適用は未実施であり、クライアント一報も送っていない** (方針不変)
- **前書全項の複製はしない** — 継承を明示し、**本フェーズが足したものだけを書く** (作業指示書 §2 WP-4 禁止事項 6)

## 1. 現在地 (main)

**フェーズ9 は WP-4 (完了ゲートと記録) をもって閉じた。フェーズ7 の残は依然として WP-9 (公開ゲート) だけであり、着手条件は依頼者の実行合図である。**

| コミット (実装 → merge) | WP | 内容 | 集計行 |
|---|---|---|---|
| `95b57bf` → `dd635b0` | WP-0 | 設計 v1.3 + 作業指示書 v1.0 (完了条件 130 件 / 変異 130 件の 1 対 1) | 文書のみ |
| `ca8920c` → `0fb3d14` | WP-1 | **契約 1.7.0 公開 (従属判断 12)** — R-2〜R-8 + R-10 (B) + port v1.13 + C-20〜C-25。**両 peer は 1.6.0 のまま、新 3 capability を `unavailable` と宣言** | `conformance-tests` `638 passed, 8 xfailed` |
| 訂正 1〜12 (`55e1f5b` / `07ebd5d` / `6b2f14c` / `2e565fe` / `6328602` / `83c705b` / `4ec8177` / `8888b8f` / `8740cf0` / `eb77398` / `64fc3e0` / `a0e1c71` / `b37099d` / `7904098` / `bf7478e`) | WP-1 訂正 | 契約補正 3 回 (`96854a6b…` → `afd6bb4f…0052` → `16517954…fcc4`)、port v1.13 の追補、C-20〜C-25 の leg 追加、隔離 profile、`CONDITIONS.md` 行 | 各コミット本文 |
| `fdef94e` + `8a82f39` → `b6c5917` | WP-2a | **r2db R-2** (`constraint_declarations: enabled`) | `r2db-api/tests` **1020 passed** |
| `7c41c9d` + `04b69c0` → `bc87590` | WP-3a | **MitateDB R-2** | `MitateDB-api/tests` **839 passed** |
| `da64edf` → `3846886` | pair-closing | R-2 の同型性表 2 行 (86 → 88) | — |
| `71e97b1` … `b361d8c` → `ab52ce6` | WP-2b | **r2db R-4** (`dry_run: enabled`) | `r2db-api/tests` **1061 passed** |
| `bcf69f5` … `a9f172d` → `c9ea605` | WP-3b | **MitateDB R-4** | `MitateDB-api/tests` **877 passed** |
| `896a1dc` → `ad3d11d` | pair-closing | R-4 の同型性表 2 行 (88 → 90) | CI 3.11 `2593 passed` |
| `66a23a9` + `c661a06` → `71ff97b` | WP-2cd | **r2db R-5 + R-6** (`idempotency` / `request_budget` = `enabled`) | `r2db-api/tests` **1108 passed** |
| `712648a` … `aa6f737` → `96cf930` | WP-3cd | **MitateDB R-5 + R-6** | `MitateDB-api/tests` **917 passed** |
| `b734d56` → `b3936b5` | pair-closing | R-5 / R-6 の同型性表 3 行 (90 → 93) | CI 3.11 / 3.12 **`2681 passed / 0 failed / 8 xfailed`** |
| `fd3d4ab` … `5eeef33` → **`3efa79f`** | WP-2e | **r2db R-3 + R-7 + 版フリップ (1.7.0)** | `r2db-api/tests` `1 failed, 1167 passed` (赤は同型性 pin のみ) |
| `4f4fb2e` … `30f1086` → **`ab89f64`** | WP-3e | **MitateDB R-3 + R-7 + 版フリップ (1.7.0)** | `MitateDB-api/tests` `2 failed, 983 passed` (赤は同型性 pin と adapter coverage) |
| `12f825e` (+ `0de6ed1`) → **`85e99fa`** | pair-closing | **版フリップの pair-closing** (同型性表 93/95 → **97 行 (両 peer 一致)**、O-8 の CONFLICT、C-21 / C-25 行の更新) | `r2db-api/tests` **1169 passed**、`MitateDB-api/tests` **992 passed**、`conformance-tests` **646 passed (failed 0 / xfailed 0)** |
| `(本記録の merge。ハッシュは次回引き継ぎ §1 に記載)` | WP-4 | 記録 (設計 v1.8 §10 / §11)、計画文書 v1.5、作業指示書 §6 訂正註 19、本書、`COLLECTION_FLOOR` | **`2807 passed, 5 warnings in 323.70s (0:05:23)`** (failed 0 / xfailed 0 / skipped 0 / error 0 — 集計行にいずれの語も無い。終了コード変数は zsh の `pipestatus` 差で取得漏れ、判定は集計行による。`pg_database` 22 → 22、`ps` で他の pytest 0 件、2026-09-08 05:26〜05:32 JST、main `85e99fa` と同一 tree) / `2807 tests collected in 0.24s`、`conformance-tests/COLLECTION_FLOOR` 2340 → **2807** (コミット `670dd8a`、`tools/check_collection_floor.py`: `COLLECTION_FLOOR check OK: measured=2807 floor=2807 diff=0`。floor 更新コミットは PERF 取得の後に置いた) / `PERFRUN host=Darwin/arm64 python=3.11.15 commit=85e99fa date=2026-09-08`、EXIT 0、`pg_database` 22 → 22。同一 plug の版間差は `backend_calls` が r2db-api-http の mutate 14.00 → 15.00 / batch 18.00 → 19.00 の +1.00 のみ (書き込み経路の `_load_field_constraints` の SELECT 1 文。SAVEPOINT / RELEASE は `conn.transaction()` 経由で `Cursor.execute` に載らない)、他 12 行は ±0.00。p50 の最大増は r2db in-process batch 0.746 → 0.883 ms、p95 の最大増は MitateDB-http mutate 6.101 → 8.099 ms、HTTP 4 plug の p50 は r2db 側 3 op と MitateDB query / mutate で減少 (§11.2 の表) / run **34159431523** (main `85e99fa`): 7 job すべて success。3.11 `2807 passed in 501.82s (0:08:21)`、3.12 `2807 passed in 487.82s (0:08:07)` (ローカルの 2807 と一致)、`tally-consistency` 緑、collection floor step は両 job で `COLLECTION_FLOOR check OK: measured=2807 floor=2340` (floor 更新コミット前の run。差は正の方向) |

**集計行の出所**: **完了ゲートは監督がローカルで単独実行したものが正本である。** **`3efa79f` / `ab89f64` / `85e99fa` の 3 つの merge は、間に他のコミットを 1 つも挟まずに連続している** (設計 §5 U-7 = (A)、作業指示書 §4 の 7)。

**並行セッションが本フェーズ中に main を進めた** — 「開発プロセス衛生 v1」(`31b4a16` / `ca72b81` / `5ff1b39` / `18367dd` とその merge) が `OPERATING_CONDITIONS.md`、`tools/check_doc_refs.py` の常時実行 job、`tools/change_class.py` と変更クラス job、計画文書 v1.3 / v1.4 を入れた。**フェーズ9 の各 merge は `git pull --ff-only origin main` の後に行った。**

**CI について**: **課金停止 (GitHub の「recent account payments have failed」) で一時 job が走らなくなり、依頼者が 2026-09-07 に解消して再実行で緑になった。** **フリップ前の直近の緑は main `3c1e1c1` / `b3936b5` の `2681 passed / 0 failed / 8 xfailed` である。** **`85e99fa` 以降の run は run **34159431523** (main `85e99fa`): 7 job すべて success。3.11 `2807 passed in 501.82s (0:08:21)`、3.12 `2807 passed in 487.82s (0:08:07)` (ローカルの 2807 と一致)、`tally-consistency` 緑、collection floor step は両 job で `COLLECTION_FLOOR check OK: measured=2807 floor=2340` (floor 更新コミット前の run。差は正の方向)。**

正本の所在 (第 15 次から更新された箇所のみ):

- **本フェーズの実施設計** = `docs/design/PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md` (**v1.8**)。**§3 の D-1〜D-9 が確定事項**、**§5 が U-1〜U-8 の確定 (依頼者裁定の委任に基づく監督確定) の逐語**、**§6.2 が C-20〜C-25**、**§9 が完了ゲート 16 項目**、**§10 が台帳 (L9-1〜L9-15、状態注記つき)**、**§11 が実施記録**、**付録 A / B が R-8 プロトタイプと R-10 (B) の before/after**
- **発注と WP 分割** = `docs/work-orders/WORK_ORDER_PHASE9_CONTRACT_170_V1.md` (v1.0)。**§6 に訂正註 19 件**を置いた (本文の発注内容は書き換えていない)
- **計画文書** = `docs/design/ROADMAP_POST_PHASE7_V1.md` (**v1.5**)。**§1.0b が現在形の「現状」**、§5 のフェーズ9 節に完了と完了条件の充足、**§5 の R-4 行と §8 の R-8 行が R-14 に従って改版済み**、**§8 の R-2〜R-8 の行き先が「フェーズ9 完了」**
- **契約** = **1.7.0**。3 複製の sha256 = **`1651795480511be5476c554ea95dda67152fe2512beedee352049d17c19afcc4`**。**従属判断 12** (`spec/CCR_DISPOSITION.md`)、**provenance マニフェスト** = `spec/CONTRACT_HISTORY_MANIFEST.json` (29 エントリ)、**派生カタログ** = `spec/OPERATION_CATALOG.json` (生成は `tools/contract_catalog.py`)
- **conformance の port は v1.13** (`docs/design/CONFORMANCE_ADAPTER_V1.md` §23)。**新条件は C-20〜C-25 の 6 本** (`conformance-tests/test_c2[0-5]_*.py`)
- **同型性表 `_ISOMORPHIC_TARGETS` は両 peer 97 行** (両 peer の `tests/test_audit_query.py`)
- **テスト総数の下限** = `conformance-tests/COLLECTION_FLOOR` (**`2807 tests collected in 0.24s`、`conformance-tests/COLLECTION_FLOOR` 2340 → **2807** (コミット `670dd8a`、`tools/check_collection_floor.py`: `COLLECTION_FLOOR check OK: measured=2807 floor=2807 diff=0`。floor 更新コミットは PERF 取得の後に置いた)**。着手時は 2340)

## 2. 到達した状態

### 2.1 エージェントが「宣言だけを読んで 1 周できる」ようになった (R-2 / R-3 / R-4 / R-5 / R-6 / R-7)

- **catalog を読む → 要求を作る**: **`field_constraints` (enum / nullable) を schema 操作で宣言でき、サーバが値検証の choke point で強制し、`EntityDescriptor` が同じ版で総計として報告する** (R-2)。**`alter_field` は本フェーズの新設である** — 既存行が反する `alter_field` と `add_field(nullable: false)` は、同一 tx 内で `LOCK TABLE ... IN SHARE MODE` を取ってから走査し、1 行でも反すれば `CONFLICT` で全体を拒否して行も catalog も revision も動かさない。**「制約は書き込みだけを縛る」** — 集合外の値を使った query predicate は拒否されず、単に 0 行に一致する。
- **判定を受ける**: **`VALIDATION_FAILED` / `IDENTIFIER_INVALID` / `CAPABILITY_UNSUPPORTED` が 4 key (`field` / `declared_type` / `observed_type` / `violated_declaration`) を持ち、`violated_declaration` は 11 語の閉じた語彙である** (R-3)。**`field` は要求内パス**であり (`operations/1/values/status`、`field_constraints/status/enum`、`budget/result_items`)、**batch の index を反映する**。**行値・SQL・内部名・修正動作は載せない** (SI-10)。**「宣言を読む層が先に走ったこと」を機械が固定する** — 両 peer に AST 全数走査のテストがあり、choke point / request-shape 層に details 無しの発行箇所が 0 件であることと、型対規則 (`field_type` / `nullable` なら型の対、`enum` / `constraint_declaration` なら宣言型のみ) を静的に検査する。**control 面にも同じ規則を適用した** (裁定 O-1)。
- **安全に再送する**: **`idempotency` が両 peer で `enabled` になった** (R-5)。**記録は application DB の side table に data tx と同一 tx で書く** — 記録が存在するのは要求が commit したときだけであり、失敗した試行は記録を残さない。**照会は認証・認可・bound の後、target-existence / 破壊確認 / precondition の前**なので、**確認つきで実行した破壊 `delete` の再送は、対象がもう無くても確認 phrase が無くても元の結果を返す**。**同 key 異 body は `CONFLICT`。replay は監査行を 1 行 (`outcome: replayed`) 残す** — 破壊操作の再送が「成功応答を返しつつ証拠ゼロ」にならないためである (SI-14)。
- **試してから実行する**: **`dry_run` が実呼びとまったく同じ判定 (認可・破壊確認・precondition・bound) を返し、外部から見える状態変化を 0 にする** (R-4)。**plan は無状態トークン `"<sha256hex>.<application schema revision>"`** であり、要求 body が変わっても schema が変わっても `PRECONDITION_FAILED` になる。**サーバは往復をまたぐ状態を 1 バイトも持たない** (P-1)。**schema の dry_run は変更後の `descriptor` と変更前の `revision` を返す** — 確定していない値は返さない。
- **自分で自分を絞る**: **要求単位の `budget` が配備値を下回る方向にのみ効く** (R-6)。**適用外の class・非整数・配備値超過は `VALIDATION_FAILED` + `violated_declaration: budget`** で、黙って丸めない。**超過は `LIMIT_EXCEEDED` + `limit_class`** であり、budget 由来か配備由来かを区別しない。
- **応答を相関できる**: **すべての成功応答が `request_id` を持ち、要求ごとに相異なり、replay は元実行の値を返す** (R-7)。
- **これらは全部検査されている** — **新条件 C-20〜C-25 の 6 本が four adapters で実行可能であり、C-21 / C-25 は 1.7.0 の無条件義務として版ゲートで、他の 4 本は capability 宣言で分岐する。** **どちらの枝も「実際に観測した枝が、その plug 自身の宣言が含意する枝と一致すること」を per-plug で assert する** — 空振りが構造的に赤になる。

### 2.2 契約が「機械が読める形」を持つようになった (R-8 / L8-9)

- **`tools/contract_catalog.py` が契約 JSON から `spec/OPERATION_CATALOG.json` を生成し、テストが再生成して byte 一致を assert する。** **19 行 (endpoints 7 + control_endpoints 12) が、endpoint ごとに roles / destructive / atomicity 境界 / 能力依存 / request・response schema を持つ。** **atomicity の実値は `atomic` / `atomic_unless_best_effort` / `none` の 3 語ちょうどである。**
- **`versioning.obligations` (版 1.2.0〜1.7.0 の 6 entry) を新設した。** **散文 `versioning.version_binding` は残した** — **L8-9 が想定した「単一文字列を配列に組み替える」形ではなく、「散文を残し、機械可読な索引を並置し、両者を register で縛る」形である** (この差は設計 §10 L9-9 に明記した)。**register は「版集合が一致すること」と「無条件件数が散文の件数語と一致すること (件数語を持つのは 1.4.0 / 1.6.0 / 1.7.0 の厳密に 3 版)」まで assert する。**
- **`endpoint_fields_note` を新設した** — `roles` / `requires_capability` / `atomicity` の 3 語の意味を契約自身が定義する。**とくに `requires_capability` は「その endpoint が提供されるために `unavailable` 以外で宣言されていなければならない capability」(必須前提) である** (訂正註 5)。
- **`CapabilityDocument.operation_catalog_url` は optional 1 項目として契約に載せたが、両 peer は宣言しない** (台帳 L9-4)。

### 2.3 契約の経緯が本体から剥がれた (R-10 (B) — フェーズ8 からの送りが閉じた)

- **`spec/CONTRACT_HISTORY_MANIFEST.json` が 29 エントリを持ち、内訳は剥離 26 / `unstripped` 3 である。** **剥離した接頭辞・挿入句の合計は 1,812 バイト、#18 の語改訂 (`this ruling closes` → `this contract closes`) が +2 バイトなので、正味 -1,810 バイトである。**
- **逆適用の deep-equal 検証は 26 値中 24 値が byte 一致し、残り 2 値の差は意図した規範文改訂 (U-8 #28) だけである** — **「差分 0」ではないことを設計 §11.1 に開示した。変換そのものは 26/26 で可逆である。**
- **`unstripped` は 3 件** (`versioning.version_binding` / `versioning.compatibility` / `destructive_confirmation.phrase_construction.rules[3]`)。**剥離後の契約全体にスキャナを当てたヒットもこの 3 件だけであり、`unstripped` 集合と完全に一致する。**
- **依頼者確定文言の PIN 18 件のうち、動いたのは 7 件だけである** (`PIN_1_5_0_SENTENCE_1` の 2 分割 + retroactive 4 件の改名 + 段落 2 件の改訂)。**残り 8 定数は 1 バイトも動いていない。**
- **効きの限界も前と同じである** — **契約 JSON は短くならなかった。** 1.7.0 の新設分により全体は **77,119 → 126,516 バイト**に増えた。**効きは「経緯の在処が 1 か所に集まり、機械が網羅性を固定できるようになった」ことに留まる。**

### 2.4 「宣言が真であること」を配備の実体に対して確かめられるようになった

- **両 peer の `ops verify-declarations` に F-14 が入った** (裁定 L-2 / M-7)。**検査するのは (a) served capability document が 4 capability を `enabled` と宣言し limits に 3 class を持つこと、(b) 全 application DB に R-2 / R-5 の per-application upgrade が適用済みであること**であり、**未適用の application が 1 つでもあれば「enabled の宣言が偽」として非 0 終了する。** **実 PostgreSQL で rc = 13 (未適用あり) と rc = 0 (全適用済み) を実測した。**
- **`ResourceLimits()` / `FoundationConfig()` のその場構築ではなく、実際に配る capability document を読む** — **その場構築を検査する形は、構築時の `__post_init__` が先に例外を投げるので F-14 経由では原理的に赤くならない、という監査の指摘で置き換えた。**
- **per-application upgrade の台帳は r2db `{9, 10, 11}`、MitateDB `{6, 8, 9, 10}` に増えた。** **未適用の application で 1.7.0 の新機能を使う要求は、実行前に `SERVICE_UNAVAILABLE` で拒否される** (裁定 J-5、fail-closed)。

## 3. クライアント連携状態

**一報は送らない** (依頼者判断 2026-09-03 以降不変)。**ただし第 15 次から性質が変わった** — **本フェーズは契約を 1.6.0 から 1.7.0 へ上げ、3 複製の sha256 が動いた。**

- **後方互換の追加のみである。** **`required` 配列は 33 ブロック全部が 1.6.0 と完全一致であり、新フィールドはすべて optional である** (WP-1 監査が旧新の全 `required` を機械比較して identical を実測)。**1.6.0 を宣言する第三者実装は 1.6.0 のまま conformant である** (retroactive-denial 規定)。
- **1.7.0 を宣言する実装には無条件義務が 2 件加わる** — **(a) 3 code の denial が details 4 key を持つこと、(b) すべての成功応答が `request_id` を持つこと。** **累計 4 件になった** (台帳 L9-10)。**これは意図した設計 (宣言の価値を上げる) であり、版を上げる費用として記録した。**
- **既存 client から見た「挙動の変化」は 1 点だけある** — **拒否応答の `details` が増える。** **`details` は 1.4.0 以降 open な map であり、追加は契約違反ではない。**
- **公開 (WP-9) を実行した場合にクライアント側へ影響し得る唯一の項目は第 14 次 §3 のまま** — **有効 credential 2 件 (r2db control / runtime) の revoke + 再発行**である (**rotate は id を保持するため不可**)。**依頼者の実行合図の後にしか起きない。**
- **実配備は未実施なので、現に影響を受けるクライアントは存在しない。**

## 4. 次の一手 (優先順)

### 4-1. WP-9 公開ゲート (フェーズ7 で唯一残っている WP。着手条件 = 依頼者の実行合図)

**第 14 次 §4-1 の手順 (0〜7) と担当がそのまま有効である。** 正本は フェーズ7 設計 §9 の手順表と作業指示書 §2 WP-9 のチェックリストであり、**本書は複製しない。**

**フェーズ9 が足した前提は 3 つである。**

- **`tools/rewrite_hash_refs.py` は本フェーズで 1 バイトも触っていない** (作業指示書 §5、全 WP に掛かる禁止事項)。**WP-9 のリハーサル成果 (main `59403e0` までの `rewrite_hash_refs` 改良) はそのまま有効である。**
- **畳む worktree がさらに増えた。** フェーズ9 側だけで **`goofy-taussig-e21ba0` (session)、`phase9-r2db`、`phase9-mitatedb`** と、並行セッションの **`process-hygiene` 系**がある。**手順 0.5 (filter-repo の前に全 linked worktree を畳む) の実行時は `git worktree list` で実数を確認すること** — この列挙は 2026-09-08 時点の記録であって網羅リストではない。
- **本フェーズが新設・改訂した文書には commit hash が入っている** (本書 §1、設計 §11、計画文書 §1.0b)。**手順 2 (commit-map による hash 参照の一括更新) の対象になるだけであり、衝突はしない。**

### 4-2. 台帳の開いている項目

**フェーズ9 側 (フェーズ9 設計 §10 が正本。全 16 項に状態注記がある)**

- **閉じた**: **L9-2b** (MitateDB の `PRECONDITION_FAILED`)、**L9-5** (剥離量の実測を記録して閉じた)、**L9-7 (= L7-8)**、**L9-8 (= L8-4)**、**L9-9 (= L8-9)**。**L9-6 は v1.1 で撤回済み (記録として残す)。**
- **開いている (記録)**: **L9-1** (`schema_objects` の数え方が peer で一致しない。r2db は entity + field + index の 1,000、MitateDB は table 数の 128)、**L9-2a** (MitateDB は `IDENTIFIER_INVALID` を発行しない)、**L9-3** (r2db に limits の env override が無い。本フェーズで差が 3 class ぶん広がった)、**L9-4** (`operation_catalog_url` を両 peer が宣言しない)、**L9-10** (無条件義務が累計 4 件)、**L9-11** (`result_items` の意味が peer で揃わず C-24 で駆動しない)、**L9-12** (`example_profile` が全 class を網羅しない)、**L9-13** (idempotency の replay と `evaluation_order` の関係)。
- **開いている (本フェーズで新設)**: **L9-14** — **idempotency 記録の内部表現が peer で異なる** (r2db は契約形、MitateDB は peer 内部形を記録して HTTP 境界で変換。監督が追認した)。**契約上の replay の意味は同じで C-23 が 4 plug で駆動するが、「記録される object そのものの形」は共通条件では観測できない** — **記録の中身に依存する将来の条件を書くときはこの差が先に効く。** **L9-15** — **C-25 (3) の監査行照合が共通 suite で 1 plug も駆動されない** (隔離 profile の 4 plug がすべて `audit_query: unavailable` を宣言する)。**担うのは両 peer のローカル pin である。閉じる条件は C-09 の駆動設計そのものに触る。**

**フェーズ7 / 8 側 (第 15 次 §4-2 のまま。差分なし)**

- **L7-2 (実 socket HTTP plug) — 開いている。フェーズ10。** **本フェーズで重みがさらに増した** — dry_run / idempotency / budget の HTTP 経路もすべて ASGI in-process の値である。
- **L7-19 / L8-2 — 開いている (上流待ち)。L6-5a — フェーズ10。L8-5 / L8-6 / L8-10 / L8-11 / L8-12 / L8-13 — 第 15 次のまま。**

**依頼者判断待ちの新規項目は本フェーズでは増えていない** (§5 U-1〜U-8 と本フェーズ中の全裁定は、依頼者の逐語委任「判断しなければならないものが出たらあなたの推奨で進めてください。後で報告してください。」に基づいて監督が確定した。**報告事項は設計 §5 と作業指示書 §6 訂正註 1〜19 に集約してある**)。

### 4-3. フェーズ10 (配備面の証拠。契約変更なし)

**L7-2 (実 socket HTTP plug) と L6-5a (`surfaces` の DB 側単一真実)。** **着手条件だった CI はフェーズ7 で成立済みである。** **フェーズ9 が L7-2 の価値をさらに増やした** — (i) dry_run の判定一致と idempotency の再送安全性が実ソケット越しにも成立するか、(ii) 性能基準値に実 socket 列が加わるか、(iii) **L9-15 (C-25 (3) の監査行照合) は `audit_query` を宣言する plug が現れて初めて共通側で駆動できる。**

**あわせて計画文書 §8 の R-16 (P-2 の周回を 1 本の scenario として通す conformance) の着手条件「フェーズ9 設計文書との重複確認」は済んでいる** — **フェーズ9 は周回の各段を C-20〜C-25 として個別に条件化したので、R-16 が足すべきものは段と段の間の受け渡しである** (計画文書 §8 R-16 行の追記)。

### 4-4. 性能のゲート化の審議

**本フェーズで性能基準値は 2 フェーズ安定した** (計画文書 §7 の 3 が言う「2 フェーズ」の 2 つ目)。**フェーズ10 の完了ゲートの後に、退行のゲート化を審議できる。** **本フェーズの版間差分は フェーズ9 設計 §11.2 にある。**

## 4-5. 運用規律 (第 15 次 §4-5 と `OPERATING_CONDITIONS.md` を継承。本フェーズが足したもの)

**第 15 次 §4-5 の全項はそのまま有効である。** 以下は本フェーズが足した分だけである。

- **変異の実測は `PYTHONPYCACHEPREFIX` を scratchpad 配下に設定して行う** (裁定 H-5)。**これを設定しないと、`cp` 復元後に `git status` clean・sha256 一致でも `__pycache__` の古い bytecode が走って偽の赤 (および偽の緑) が出る** — source と pyc の記録 mtime が同一秒になるためである。**この規律より前に取った変異結果は、「緑だった」側が特に信用できない。**
- **待機ループは自己一致しない形で書く**: `while ps -eo comm=,args= | awk '$1 ~ /python/ && $0 ~ /-m pytest/' | grep -q .; do sleep 5; done`。**`ps aux | grep '[p]ytest'` 形は待機シェル自身に一致して永久待機になる** — 本フェーズで実際に 5 本のデッドロックした待機ループが残った。
- **レビュアの差し戻し文はファイルに残す。** **報告だけで返すと、次の実装プロンプトを組む段で原文が失われ、再作業が止まる。** 本フェーズは `{scratchpad}/review-*.md` / `audit-*.md` / `rulings-*.md` を常設し、**実装プロンプトには裁定ファイルを最初から全部渡した** (訂正註 14 (ii))。
- **納品前に main をマージした状態で全 suite を再実行する** (裁定 M-8)。**本フェーズで 1 度、per-module 件数 pin が main のマージで赤になったまま納品された。**
- **subagent には peer 側 worktree への `cd` を明示で許可する。** 監査は 2 つの worktree を横断して比較する必要があり、許可が無いと片側だけを読んで「相手側は未確認」と書いて終わる。
- **並行セッションが main を進めることを前提にする。** **merge 前に必ず `git pull --ff-only origin main` を行う。** 本フェーズ中に「開発プロセス衛生 v1」が 4 回 main に入った。
- **契約の補正はフリップ前にまとめて 1 コミットにする** (訂正註 14 (i))。**peer が版を宣言した後の補正は、宣言の意味を後から動かすことになる。**
- **過大な WIP コミットメッセージは `git reset --soft` で正直に書き直す。** 「pre-review WIP」と題したコミットに差し戻し後の再作業 11 項目が入っている状態を監査が指摘した。

## 5. 教訓の追加 (前書全項継承に追加)

- **「実装は正しいが、それを守るテストが無い」は、実装の欠陥と同じ重さで扱う。** 本フェーズの差し戻しの過半はこれだった — **plan digest への `idempotency_key` の配線 (両 peer)、idempotency 記録が data tx と同一 tx であること、期限切れ回収の順序、遅延 digest の性能条項、HTTP が `request_id` を再生成しないこと。** **いずれも実装は正しく、変異を当てても全緑だった。** **とくに遅延 digest は効き幅が大きい** (HTTP + 実 PG plug の 126 テストで `_read_schema_revision` が 62 回 / 2,494 回) **のに、「消えても誰も気づかない」形で入っていた。** **常設規律 1 (空振り禁止) と 2 (変異先行) は、実装の正しさとは独立に効く。**
- **レビュアの差し戻し文は報告ではなくファイルに残す。** 報告だけで返すと、次の実装プロンプトを組む段で原文が失われ、再作業が止まる。**確定文言をファイル経由で複製する規律 (常設規律 4) は、裁定文にも同じように掛かる。**
- **待機ループは自己一致しない形で書く。** `ps aux | grep '[p]ytest'` は待機シェル自身に一致する。本フェーズでは 5 本のデッドロックが実際に残り、監査の 1 パスが丸ごと止まりかけた。
- **`PYTHONPYCACHEPREFIX` で変異実測の pyc を隔離する。** `cp` 復元 + 1 秒粒度の mtime は、`git status` clean・sha256 一致でも古い bytecode を走らせる。**Drive 同期ツリー特有の事故ではなく一般的な罠である。**
- **テスト結果を pipe の後ろに置いたまま commit chain に入れない。** 訂正 9 が赤のまま出荷され、次の訂正 9b で「隔離 profile が実際には `idempotency_entries=20` を設定していなかった (sed の取りこぼしで 5 のままだった)」ことが分かった。**BSD sed には `\b` が無い** — GNU sed 前提の置換スクリプトはこの環境では黙って外れる。
- **Sonnet は 6 項目を超える再作業を断ることがある。** WP-3e の再作業がこれに当たり、**T1 / T2 / T3 の 3 プロンプトに分割して発注した** (訂正註 18)。**差し戻しが 6 項目を超えたら、最初から分割して出す。**
- **subagent には peer 側 worktree への `cd` を明示で許可する。** 許可が無いと監査は片側だけを読み、「相手側は未確認」で終わる — pair-closing の判断材料が揃わない。
- **並行セッションが main を進める前提で運用する。** **merge 前に `git pull --ff-only origin main` を必ず行う。** 本フェーズは「開発プロセス衛生 v1」と 4 回交差した。
- **契約補正はフリップ前にまとめて 1 コミットにし、裁定は実装前に全部渡し、レビューと監査を 1 pass に統合する** (依頼者承認の短縮 3 点、訂正註 14)。**この 3 つで WP あたりの往復が 1 回減った。** **ただし「レビュー 2 回目を省く」ことの代償は実測できていない** — 統合パスが見つけた指摘の数は 2 回に分けたときと同等だったが、それが偶然かどうかは 1 フェーズでは分からない。
- **過大な WIP コミットメッセージは `git reset --soft` で正直に書き直す。** コミットメッセージは監査が「何が入っているか」を判断する一次資料であり、実態と食い違うと監査が誤った前提で走る。**本フェーズはこれを 1 件、記録として残した** — **pair-closing コミット `12f825e` のメッセージは `_served_capabilities_document` を同型表に登録したと書いているが、実際には登録していない** (裁定 O-7 の対象外であり、両 peer の本文が本質的に非同型だった)。**メッセージは書き換えず、設計 §11.3 に訂正を書いた。**
- **「宣言より先に挙動を入れることを禁じる機構」は、`xfail(strict=True)` だけでは成立しないことがある。** **本フェーズの C-21 / C-25 は当初、pre-1.7.0 枝の末尾に `observed_branch` の突合を置いていたため、その枝は構造上どうやっても pass できず、strict XPASS が原理的に起こり得なかった** (監査が adapter に `request_id` を注入しても xfail のままであることで実証した)。**訂正註 7 で「pre-1.7.0 枝では突合を本体に含めない」と形を確定した。** **「strict xfail を置いた」ことと「早期実装が赤になる」ことは別の命題である。**
