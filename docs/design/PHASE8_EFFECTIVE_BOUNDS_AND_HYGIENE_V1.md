# フェーズ8 実施設計: 実効 bound と基盤衛生 (契約 1.6.0 不変)

- 版数: **v1.3 (2026-09-07)** — **実施記録 (§11) の記入と訂正註の追加のみ**である。§3 の各 D に「**訂正註 (実装で確定した差)**」を足し、§5 U-1 に状態注記を、§9 の各項に結果を、§10 の台帳に状態注記と新規起票を足した。**§3〜§5 の決定文言は 1 文字も変えていない** — 訂正註は原文を消さずに追記する形である (フェーズ6 §11 L6-18 の流儀)。
- 旧 **v1.2 (2026-09-06)** — §5 U-1 / U-2 に依頼者裁定 (逐語「推奨で進めてください」) を記録。U-1 = (A)、U-2 = (A) (B はフェーズ9)。**§5 は確定であり再審議しない。** 本文の他節は v1.1 のまま。
- 旧 **v1.1 (2026-09-06)** — 設計レビュー 1 回目の指摘 **18 件を全件反映**した改稿である (監督採否 2026-09-06)。**§3 D-1〜D-6 は監督確定のまま**であり、**§5 U-1 / U-2 は依頼者判断待ちのまま**である。改稿は根拠 (file:line) の追記・検査形の限定・開示事項の追加に限り、決定そのものは動かしていない
- 旧版: **v1.0 (2026-09-06)** — 起草初稿。設計レビュー 1 回目の対象となった版である
- 位置づけ: **監督が確定した枠 (2026-09-06) の実施設計**である。計画文書 `docs/design/ROADMAP_POST_PHASE7_V1.md` (v1.1) の §5「フェーズ8」節・§4 (P-1〜P-9)・§7・§8 (R-9〜R-12)・§9 が**正本**であり、本書 §1〜§2 はそれを**転記**する (再導出しない)。§3 の D-1〜D-6 は監督確定であり、**§5 の U-1 / U-2 だけが依頼者判断待ち**である。WP 分割は §8 に素案のみを置き、作業指示書 (`docs/work-orders/WORK_ORDER_PHASE8_EFFECTIVE_BOUNDS_V1.md`) は別途起こす。構成・粒度・文体はフェーズ7 設計文書 (`docs/design/PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md`) を踏襲する
- テーマ: **「宣言した bound が全 peer で実効であり、それが機械的に証明され、以後の改版に耐える計測と検知が置かれている」状態にすること**
- 前提となる main: **`9389fd5`** (計画文書 v1.1 マージ後)。作業 branch **`phase8-effective-bounds`**、worktree `.claude/worktrees/phase8`。**root `--collect-only -q` = 2274 tests collected** (実測 2026-09-06)
- **契約は不変である**。本フェーズは契約の**意味**を 1 文字も変えない (1.6.0 のまま)。`limit_enforcement` の値語彙 (`enforced` / `reference_wall_clock` / `deployment_required` / `unavailable`) と `limits.classes` の 16 語は既存のまま使う。**契約 JSON のテキストは、R-10 が U-2 (A) なら 0 バイト不変、(B) なら接頭辞の剥離分だけ動く**。動く場合も計画文書 §5 が「契約の意味は 1 文字も変えない」と既に固定した範囲内である (§3 D-4、§5 U-2)
- 応える G (計画文書 §0): **G-2** (人から見て比類なきセキュリティ = 宣言 bound の実効性とその証明可能性)、**G-4** (高性能は大前提 = 基準値の取得)。**G-3** (信頼性) には副次的に応える — 宣言が真であること (P-3) は信頼性の一部である
- 体制・規律: 既存フェーズと同一である。Fable 監督/設計/コミット、Opus 起草/独立レビュー/受け入れ監査、Sonnet 実装 (コミットしない)。**設計レビューは 1 回** (契約を触らないフェーズ。計画文書 §9 の 3)
- 設計原則 (依頼者、2026-09-02): 先送りしない / シンプル / 制約・制限で回避しない / 誇れる成果物。既定の重み付けは「最小変更」ではなく「長期に正しい形」。利用者は AI エージェントである (宣言は確実に読まれる)
- **公開規律**: 本書には実値を一切書かない — 実ホスト名・cloud project 識別子・実 e-mail・実 credential_id・作業機の絶対パス・IAM principal を含まない。合成値は `<UPPER_SNAKE>` 形の placeholder と `*.example.invalid` のみを使う
- **WP-9 (フェーズ7 の公開ゲート) と並行できる**。WP-9 が触るのは `tools/rewrite_hash_refs.py` (新設) と docs/ の hash 参照の一括更新のみであり、本フェーズはそのファイルを作らない。本書および本フェーズの新設文書に commit hash を書いた場合、WP-9 の commit-map 適用対象になるだけで衝突しない

---

## 1. 問題設定

### 1.1 計画文書 §5「フェーズ8」節の転記

計画文書 `docs/design/ROADMAP_POST_PHASE7_V1.md` §5 のフェーズ8 節を以下に**転記する** (再導出しない)。

> **フェーズ8 — 実効 bound と基盤衛生 (契約変更なし)**
>
> - **目的**: G-2 と G-4 の土台。宣言した bound が全 peer で実効であること、以後の契約改版に耐える計測と検知を置くこと。
> - **着手条件**: 依頼者の着手裁定。WP-9 との並行可 (触るファイルが重ならない)。
> - **範囲**:
>   - **L7-1** MitateDB application plane の `execution_ms` / `concurrency` / `requests_per_minute` / `operation_depth` の実 enforcement (in-process `request_bytes` は副項目) + port への in-flight 保持 primitive + C-05 V3 xfail の class ごとの撤去。**L7-21** (V2 の除外判定を peer 名固定から能力判定へ、port v1.12) を同梱する。同じ C-05 を触るためである。
>   - **R-9** CI のテスト総数下限 (前回 main の `--collect-only` 件数を下限とし、減少は明示の更新なしに赤)。**L7-23** (register テストの収集 0 件ガード) と **L7-22** (現行行へ台帳 ID 2 件を戻す) を同梱する。
>   - **R-10** 契約 JSON の現行/履歴分離。WP-7 の companion 方式 (`*_HISTORY.md`、ID ごとの anchor、register テスト) を `spec/` に適用。**契約の意味は 1 文字も変えない** (1.6.0 のまま)。分離の検査は「現行 JSON から経緯マーカーが消えたこと」と「companion に逐語で残ること」。
>   - **R-11** 運用項目: deployment smoke test (provision 後に capabilities / catalog / 1 query を実打ちして終了コードで返す)、**L7-18** の `ops verify-declarations` を**両 peer に同型で**追加、backup/restore の手順と実証記録 (r2db)、ops CLI の引数に secret を取る経路の検査 (両 peer)。**L7-19** は constraints の Starlette 更新と同一コミットで ignore を外す (撤去条件が満たせる版があれば本フェーズで行う)。
>   - **R-12** 性能基準値: 両 peer × 4 plug に対する query / mutate / cross-entity の p50 / p95 を測る使い捨てでないハーネス (`tools/`) と、完了ゲートに添える集計行の形式。**閾値は置かない** (P-8)。
> - **守るべき条件**: 契約変更ゼロ。L7-1 は C-05 の既存の駆動集合規則に従う。R-10 は WP-7 の規約を再利用し新方式を作らない。
> - **完了条件**: C-05 V3 の xfail が 0 (または実測で残る class とその理由が台帳に載る)、CI に総数下限 job、`spec/` に companion、R-12 の基準値が設計 §13 に記録される。
> - **再検討事項**: `operation_depth` の枝 (L7-1)。性能ハーネスの plug 選択 (HTTP plug を含めるか。L7-2 前なので in-process TestClient 経路になる点を記録する)。

**本書での §番号の対応**: 計画文書が「設計 §13」と書くのはフェーズ7 設計文書の節番号 (実施記録) を指す慣行の踏襲である。**本書では実施記録は §11 であり、R-12 の基準値は §11.2 に記録する。**

### 1.2 探索で確定した事実 (根拠)

以下はすべて worktree `.claude/worktrees/phase8` (main `9389fd5`) の現物を読んで確認した事実である。**テストは実行していない** (§1.3 の実測 2 件を除く)。

**(1) MitateDB application plane の 4 class は実装が無く、宣言が正直にそう言っている。**

- `MitateDB-api/src/mitatedb_api/cell.py:1494-1534` の `limit_enforcement` ブロックが `execution_ms` / `concurrency` / `requests_per_minute` / `operation_depth` を **`unavailable`** と自己申告する。フェーズ7 WP-4 が置いたコメント (`:1504-1533`) は、その判定が grep による実測であること (「wall-clock 実行時間を測る経路も、in-flight 数を追う経路も、application-plane 要求に rate 窓を当てる経路も無い」) と、`operation_depth` について「`Filter`/mutation の形はフラット (単層の述語 list) で、入れ子の概念自体が無い」ことを記録している。
- `request_bytes` は **HTTP 面だけが実測強制**である。`MitateDB-api/src/mitatedb_api/http.py:208` の `RequestByteBoundMiddleware` が ASGI 受信ループで実バイトを積算し、`http.py:591` が capability 文書の `limit_enforcement.request_bytes` を `enforced` へ上書きする。**in-process 面は `unavailable`** (`cell.py:1502`) であり、`FoundationConfig.validate_request_size` (`MitateDB-api/src/mitatedb_api/config.py:172-178`) は定義されているが**呼び出し元が無い** (`cell.py` のコメント `:1499-1501` が自認している)。
- **r2db の `_slot` に相当する一元 choke point が MitateDB に無い。** application plane の入口は `ApplicationRuntime` (`cell.py:1335`) の 8 メソッド (`schema_revision` / `insert` / `read` / `catalog` / `update` / `delete` / `transact` / `capabilities`、`:1352-1394`) と、`ApplicationDeveloper` が足す schema 操作 (`cell.py:1543-1560`) であり、**そのすべてが `__authorize` (`cell.py:1348-1350`) を最初に呼ぶ**。したがって「入口が 1 つ無い」のではなく、**共通の入口ヘルパは既に 1 つある**。

**(2) r2db の参照実装と、その実際の検査順序。**

- `ResourceLimits` (`r2db-api/src/r2db_api/limits.py:11-20`) が 9 class を持つ。`check_request` (`:37-70`、構造推定)、`check_deadline` (`:73-75`)、`check_depth` (`:77-89`、要求 dict 全体への汎用再帰深さ、循環検出付き) がその実体である。
- **要求入口の実順序** (in-process、`r2db-api/src/r2db_api/service.py`):
  1. `_slot` (`:1133-1144`) が最初に `_check` (`:1146-1154`、認証・application 有効性・cell 存在) を呼ぶ。
  2. 次に **`_acquire_rate`** (`:1156-1163`) — **credential_id 毎の 60 秒 sliding window**。超過は `LIMIT_EXCEEDED` + `details.limit_class = "requests_per_minute"`。
  3. 次に **concurrency** — `self._active_lock` の下で `self._active >= self.limits.concurrency` を見て `LIMIT_EXCEEDED` + `limit_class = "concurrency"`、通れば `self._active += 1`。`finally` で必ず減算する (`:1141-1144`)。
  4. `_slot` の内側で形式検証を行った後、**`check_request` (request_bytes)** → **`check_depth` (operation_depth)** の順に呼ぶ (`query`: `:996` / `:997`、`mutate`: `:1037` / `:1038`、`schema`: `:1072` / `:1073`)。
  5. その直後に `deadline = self._clock() + self.limits.execution_ms / 1000` を作り (`:999` / `:1039` / `:1074`)、cell へ渡す (`:1000` / `:1048` / `:1079`)。PostgreSQL backend は残余から逆算した値で `SET LOCAL statement_timeout` / `lock_timeout` を張り (`r2db-api/src/r2db_api/postgres.py:1936-1959`)、`QueryCanceled` / `LockNotAvailable` を `LIMIT_EXCEEDED`(`execution_ms`) へ写す。宣言は **`reference_wall_clock`** (`service.py:936-937`)。
  6. **HTTP 面では、その手前にもう 1 段ある** — `create_app` が返すのは `RequestByteBoundMiddleware(app, service.limits)` (`r2db-api/src/r2db_api/http.py:475`) であり、**実バイト計測が認証よりも前に走る**。同じ `ResourceLimits` を見るので、宣言と 2 つの enforcement 層は同じ 1 個所から出る。

**(3) MitateDB backend は二重である。** SQLite (`backend_sqlite.py`、`:memory:`、ローカル決定論用) と PostgreSQL (`backend_postgres.py`、本番) があり、**PG 経路に `statement_timeout` の使用は無い**。control plane の `_check_rate` (`MitateDB-api/src/mitatedb_api/control_plane.py:1162-1172`) は**グローバル**の sliding window であり、application plane の credential 単位の窓とは別の概念である。

**(4) C-05 の現行構造。**

- V2 の駆動集合は `_V2_DRIVERS` (`conformance-tests/test_c05_limit_declaration_agreement.py:529-538`) の 8 driver が、各自の冒頭で「その plug の宣言が `enforced` か」を見て `return False` する形で決まる (例 `:232` / `:272` / `:302` / `:362` / `:407` / `:432` / `:477` / `:511`)。V2 本体 (`:666-683`) は真を返した driver が 1 つ以上あることだけを assert する。
- **peer 名固定の除外は 2 箇所である** — `_drive_result_items` (`:473-474`) と `_drive_query_complexity` (`:507-508`) の `adapter.name.startswith("r2db-api")`。**`request_bytes` に peer 名分岐は無い** (`_drive_request_bytes` `:432` の宣言判定だけで MitateDB in-process が自然に落ちる)。**`CONDITIONS.md:34` の C-05 行が L7-21 を「the MitateDB exclusion for `request_bytes`/`query_complexity` is keyed on peer name」と書いているのは実装と食い違っており、訂正が要る** (正しくは `result_items` / `query_complexity`)。
- V3 は固定 9 class × 4 plug = 36 ケースの静的 parametrize (`:713-728`) であり、`_V3_KNOWN_UNAVAILABLE` (`:700-710`) の **9 組**に `xfail(strict=True)` を付ける。内訳は `MitateDB-api` が 5 組 (`execution_ms` / `concurrency` / `requests_per_minute` / `operation_depth` / `request_bytes`)、`MitateDB-api-http` が 4 組 (`request_bytes` を除く)。**撤去とは「frozenset から組を削除すること」であり、削除と同時に実装で宣言が上がっていなければ赤になる。**
- 既存の `_drive_operation_depth` (`:299-356`) は、**フラットな insert が実測で深さ 4 に座る**ことを利用した N / N+1 レシピを持ち、隔離 profile の `operation_depth` が **4 であること自体を assert する** (`:330-334`)。N+1 は「同じ insert に `where` を足す」形であり、**`check_depth` が内容検証より前に走ること**に依存している (`:509-517` 相当のコメント)。r2db 2 plug の隔離 profile はこのために `operation_depth=4` を宣言している (`r2db-api/conformance/conformance_adapter_r2db.py:142-151`、`r2db-api/conformance/conformance_adapter_r2db_http.py:752-761`)。

**(5) port v1.11 の形。**

- 要求を出す primitive はすべて「1 呼び出し = 1 完結」の**同期 signature** である — `insert` (`conformance-tests/adapter.py:1717`)、`select_eq` (`:1720-1722`、述語は `field`/`value` の 1 個、page/limit の概念なし)、`attempt_filter` (`:1725-1727`、常に述語ちょうど 1 個)、`attempt_mutation` (`:1907-1918`)、`attempt_cross_entity_batch` (`:2063-2065`)。**部分実行や pending 状態を表す型は無い。**
- `isolated_application_surface()` (`:1407-1518`) は out-of-band で新しい service/cell を直接構築し、**port 準拠の adapter instance を yield する**。in-process の実装は「小さな profile を与えて同型の adapter を新規構築する」だけである (`conformance_adapter_r2db.py:649-654`、`conformance_adapter_mitatedb.py:836-855`)。**MitateDB in-process の teardown は既に `cell._backend.close()` に手を伸ばしている** (`conformance_adapter_mitatedb.py:853-855`) — adapter が cell / backend オブジェクトへ到達する前例がある。
- HTTP plug 2 本は**実ソケットではない** — `httpx.AsyncClient(transport=httpx.ASGITransport(app=app))` (`conformance_adapter_r2db_http.py:947` / `conformance_adapter_mitatedb_http.py:736`) を、呼び出しごとの `self._loop.run_until_complete(coro)` (`conformance_adapter_r2db_http.py:1156-1157` / `conformance_adapter_mitatedb_http.py:838-839`) で駆動する。**1 本の loop を 1 呼び出しずつ回す構造なので、このままでは複数要求を in-flight のまま保持できない。** 隔離 instance は自前の loop と client を作る (`conformance_adapter_r2db_http.py:1966-1967` / `conformance_adapter_mitatedb_http.py:1480-1481`)。

**(6) `concurrency` は共通 suite のどこでも駆動されていない。** C-14 は control plane の 3 class (`applications` / `credentials_per_application` / `control_requests_per_minute`) を位置演算で駆動する (`conformance-tests/test_c14_authority_boundary.py:503-545`) が、**`control_concurrency` という class は契約にもコードにも存在しない**。`_MAX_EXERCISABLE_LIMIT = 200` は `test_c14_authority_boundary.py:141` と `test_c05_limit_declaration_agreement.py:70` に同値で置かれている。

**(7) CI は 1 本、総数の下限は見ていない。** `.github/workflows/ci.yml` (267 行) の `conformance` job (`:63`、matrix 3.11 / 3.12) が `python -m pytest -q -n 5 --dist loadgroup` を回し (`:103-106`)、`:108-182` の heredoc が tally 行から 4 数を抽出、artifact 経由で `tally-consistency` job (`:207-242`) が 3.11 と 3.12 を突合する。**trigger は push のみで、`concurrency` の cancel-in-progress がある。** `scanner` job (`:245-253`) は `tools/public_value_scan.py` を素の `python3` で呼ぶ (**標準ライブラリのみ**という tools/ の規約)。

**(8) L7-23 の原因。** `conformance-tests/test_conditions_register.py:166-176` の `_collect_marked_condition_ids` が `request.session.items` からライブの collection を読む。register ファイルだけを収集すると集合が空になり、`:184` のテストは「全 20 条件にマーカーが無い」と判定して赤、`:198` 以降のテストは**空集合同士で vacuous に緑**になる。**赤が 1 本出るために「全体 run でだけ評価する」運用になっており、静かに緑になる側は誰も見ていない。**

**(9) L7-22 は実態としては充足している。** `security/CONTROL_MAPPING.md:33` の SI-00 行は「ledger item L4-13, still open」を**現行行に持っており**、`conformance-tests/CONDITIONS.md:38` の C-09 行は「P4-D18 (L4-8, still open) DEFERS …」を**現行行に持っている**。**フェーズ7 設計 §11 の L7-22 と第 14 次引き継ぎ §4-2 の「開いている」という記述が実態と食い違っている。**

**(10) R-10 の対象と、それを固定しているもの。** `spec/data-service-api.v1.json` (77,117 バイト) と両 peer の packaged 複製 2 本は**バイト一致テスト**で固定されている (`r2db-api/tests/test_http.py:286`、`MitateDB-api/tests/test_http.py:155`)。経緯マーカーを含む値は **29 個**、うち **18 個が `conformance-tests/test_contract.py` の PIN またはパス式 assert で固定されている** (付録 A)。`versioning.version_binding` 1 キーで **10,269 字 = 契約全体の 13.32%** を占める。**マーカーが現行規範文と同一文に同居する複合文が多数ある** — 例: `audit.query_operation_vocabulary` の "Since 1.5.0 (subordinate ruling 10, item 1, conditional): …" は、その 1 文がそのまま `operations` / `target_kinds` 語彙の現行定義であり、`PIN_1_5_0_SENTENCE_1..4` (`test_contract.py:447-467`) が**依頼者確定文言として逐語 assert している**。**契約の意味部分に対する正規化 hash テストは存在しない。**

**(11) R-11 の現況。** 両 peer の `ops` CLI (`r2db-api/src/r2db_api/ops.py` / `MitateDB-api/src/mitatedb_api/ops.py`) は argparse サブコマンド方式で、**引数に secret を取る経路は 1 つも無い** (DSN・pepper はすべて環境変数)。`verify-declarations` は**両 peer に無い**。Q4 の宣言検査は両 peer の `platform_declarations.py` に純関数として分離されており、`read_platform_declarations` は **F-8 (表が無い) → F-3 (surfaces 行が無い) → F-4 (coalescing 行が無い) → F-4b / F-5 (値の検証)** の順で `PlatformDeclarationError` を上げる (`r2db-api/src/r2db_api/platform_declarations.py:370-403`)。**`PlatformDeclarationError` (`:132-136`) はメッセージ文字列しか持たず、F 番号を構造化属性として持たない。**
- **隣接経路に実在の穴が 1 つある** — `r2db-api/deploy/scripts/part1_provision_host_and_db.sh` が **6 箇所**で password を psql の argv に渡している (`:270` `control_password`、`:279` `api_password`、`:284` `controlplane_password`、`:289` `auditreader_password`、`:334` `runtime_password`、`:335` `developer_password`)。`ps` から一時的に見える形である。
- **L7-19 の撤去条件は本フェーズでは満たせない** — `constraints.txt:42` は `starlette==1.6.0` であり、`pip index versions starlette` の最新も 1.6.0 である (探索 (e) が実行して確認)。**こちら側の遅れではなく上流待ちである。**

**(12) R-12 の材料。** 4 adapter の `build_adapter()` はモジュール関数であり **pytest の外から import して呼べる** (`conformance_adapter_r2db.py:1639`、`conformance_adapter_r2db_http.py:3219`、`conformance_adapter_mitatedb.py:1942`、`conformance_adapter_mitatedb_http.py:2271`)。**DB 往復数を数える既存フックは無い。** 最も近い前例は `MitateDB-api/tests/test_postgres.py:595-607` の「backend のメソッドをテスト側で差し替えて呼び出し回数を数える」形である。既知の性能観測は L6-15 (MitateDB の宣言型 registry 参照が insert 2 回・query 3 回の往復を増やす) の**記述のみ**で、数値は無い。

### 1.3 起草時に実行した 2 件 (実測)

1. **`--collect-only -q` の件数** = **2274 tests collected** (worktree phase8、main `9389fd5`)。R-9 の下限の初期値の根拠である。
2. **argv secret 静的規則のプロトタイプ** (常設規律 5) = **現行ツリーで 6 件 flagged**。逐語の規則と出力は §3 D-5 に置く。

---

## 2. 守るべき条件

### 2.1 計画文書 §4 の横断条件 (P-1〜P-9) の転記

| 記号 | 条件 | 根拠 |
|---|---|---|
| **P-1** | **1 要求 = 1 原子単位。往復をまたぐサーバ保持状態を持ち込まない。** plan・sandbox・resumable upload・保持 lock はすべてこれに当たる。無状態化 (決定的トークン、実行して rollback) で同じ目的を満たす | 契約 `transactions.interactive`、SI-08、両 peer の同型性 |
| **P-2** | **エージェントの 1 周を閉じることを優先する**: catalog を読む → 要求を作る → 判定を受ける → 安全に再送する | G-1、ai-agent 前提 |
| **P-3** | **宣言は真であり、検査される。** 新しい宣言 (制約・能力・limit) は、宣言と実挙動の一致を共通条件として同時に追加する。advisory な宣言を catalog に載せない | C-05 / C-17、L6-6 |
| **P-4** | **catalog と schema 操作は同じ版で動く。** 片方だけ先行させない | L6-6 |
| **P-5** | **bound は安全上必要なものだけ。** 機能の問題を TTL・件数上限・除外リストで消さない | 設計原則 3、SI-08 |
| **P-6** | **peer 同型性を維持する。** 同名 helper は正規化 diff で固定し、コードは共有しない。platform 固有の実現が異なっても、契約上の意味は一致させる | peer-symmetry 規約 (2026-09-03) |
| **P-7** | **契約はエージェントが読める長さと形を保つ。** 経緯文は companion へ、現行の意味だけを契約本体に置く。派生の機械可読 artifact は再生成一致テストで正本に縛る | G-1、R-8 / R-10 |
| **P-8** | **各フェーズは性能の差分を記録する。** 基準値 (R-12) 確定後、完了ゲートに p50 / p95 の記録を添える。退行は初期は記録のみ、基準値が 2 フェーズ安定した後にゲート化を審議する | G-4 |
| **P-9** | **クラウド製品・任意 SQL・自然言語クエリ・管理画面・ORM 互換は共通契約に入れない** | CLAUDE.md 境界、CCR-01 |

### 2.2 本フェーズでの適用 (効く 5 条件)

- **P-3 の本フェーズでの適用**: MitateDB の 4 class は**宣言を上げるコミットと enforcement を入れるコミットを同一にする** — 先に宣言だけ `enforced` にすることを禁じる (D-1)。逆に、駆動できない class を「駆動しているように見せる」除外も禁じる (D-2 の L7-21)。
- **P-5 の本フェーズでの適用**: 新しい bound を**発明しない**。実装するのは契約 `limits.classes` に既にある 4 class だけであり、値は既存 `FoundationConfig` と同じ「配備が宣言する既定値」の形で置く (D-1)。`operation_depth` を実装するか否かは「安全上必要か」で判断する (U-1)。
- **P-6 の本フェーズでの適用**: 4 class の実現は r2db と「契約上の意味」を一致させる — **拒否の順序・error code・`details.limit_class`・宣言語 (`execution_ms` は両 peer とも `reference_wall_clock`) を揃える**。**コードは共有しない**。両 peer に同名で置くヘルパが生じたら同型性テストの対応表に載せる (D-1 / D-5)。
- **P-7 の本フェーズでの適用**: R-10 は**契約本体から経緯を減らす**方向にのみ働き、**契約に新しいキー (companion への参照) を足さない** (D-4)。
- **P-8 の本フェーズでの適用**: 本フェーズが**基準値そのもの**を作る。**閾値は置かない** — 置けば bound として機能を縛る形 (P-5) になる (D-6)。

### 2.3 本フェーズ固有の制約

1. **C1 契約 1.6.0 の意味は変えない。** `spec/data-service-api.v1.json` のテキストは U-2 (A) なら 0 バイト不変 (3 複製の sha256 で示す)、(B) なら接頭辞の剥離分だけ動き、**その場合の意味の同一性は機械検査 (deep-equal) で示す** (D-4)。版数は 1.6.0 のままである。
2. **C2 新しい共通 Security Invariant は不要である** (§7 で根拠を示す)。
3. **C3 開発順序**を守る: 共通要件 → 該当 SI → 共通契約への影響判断 → conformance → 実装 → 実装別テスト・統制。
4. **C4 完了ゲート**の集計行は `pytest -q -n 5 --dist loadgroup` の**単独実行**で取る。**設計段階では suite を回さない。**
5. **C5 常設規律 7 項目**を継承する (`docs/work-orders/WORK_ORDER_PHASE7_EVIDENCE_AND_PUBLICATION_V1.md` §0.1、フェーズ6 §0.1 の逐語継承)。特に**規律 2 (完了条件 1 項目 = 変異 1 つ)** と**規律 5 (静的規則は逐語プロトタイプの後に設計へ)** — 後者に従い、D-5 の argv 規則はプロトタイプ済みであり結果を D-5 に、R-10 のマーカー逐語インベントリを**付録 A** に添付する。
6. **C6 速度規律 5 項目**を継承する (`docs/work-orders/HANDOVER_20260904_FABLE2.md:67`、フェーズ6 設計 §641、第 14 次引き継ぎ §4-3)。完了ゲートは監督が単独実行し、subagent には担当ファイルの範囲だけを回させる。**ローカル PostgreSQL の `max_connections = 300` が前提である。**
7. **C7 公開規律**: 設計文書・作業指示書に実値を書かない。
8. **C8 並行作業**: WP-9 (公開ゲート) と本フェーズは触るファイルが重ならない (§8)。並行 worktree を使う WP は、着手前に「触るファイルの重なり 0」を確認する (第 14 次 §4-3)。

---

## 3. 決定と根拠

### D-1 L7-1 の実装形 (MitateDB application plane の 4 class + `request_bytes` 副項目)

#### 決定

**MitateDB の application plane に、r2db と契約上の意味が一致する enforcement を置く。** 実現方式は platform に従って異なってよいが (P-6)、**拒否の位置・error code・`details.limit_class`・宣言語は一致させる**。対象は次表のとおりである。

| class | 実現方式 (MitateDB) | 宣言値 | V2 駆動の有無 | 撤去対象の xfail 組 |
|---|---|---|---|---|
| `requests_per_minute` | **credential_id 毎の 60 秒 sliding window** (r2db `_acquire_rate` (`service.py:1156-1163`) と同型。control plane の**グローバル**窓 `control_plane.py:1162-1172` とは別物として置き、control plane は変えない) | **`enforced`** | **駆動する** (既存 `_drive_requests_per_minute` `test_c05:359-401` を使う。**ただし「そのまま効く」かは条件つきである** — `already_consumed` (`:383`) の再測定要否を WP-1 が確認して記録する。D-2「検査の形」) | `(MitateDB-api, requests_per_minute)` / `(MitateDB-api-http, requests_per_minute)` |
| `concurrency` | **in-flight カウンタ + `threading.Lock`** (r2db `_slot` (`service.py:1133-1144`) と同型。取得後は例外経路を含めて `finally` で必ず解放する) | **`enforced`** | **駆動する** (D-2 の in-flight 保持 primitive を前提に、新設 `_drive_concurrency` が駆動。**r2db 2 plug の差集合も同時に閉じる**) | `(MitateDB-api, concurrency)` / `(MitateDB-api-http, concurrency)` |
| `execution_ms` | **二重構え** — (i) app 側の deadline 検査 (要求受理時刻 + `execution_ms` を wall-clock で判定、r2db `limits.check_deadline` (`limits.py:73-75`) と同型)、(ii) **PostgreSQL backend では残余から逆算した `SET LOCAL statement_timeout` / `lock_timeout`** を張り、`QueryCanceled` / `LockNotAvailable` を `LIMIT_EXCEEDED`(`execution_ms`) へ写す (r2db `postgres.py:1936-1959` と同型)。**SQLite backend は app 側 wall-clock のみ** (sqlite3 に query timeout API が無い) | **`reference_wall_clock`** (r2db `service.py:936-937` と同じ。**`enforced` にしない** — 理由は §4) | **駆動しない** (V1 の整合検査と V3 のみ。D-6.2 の「構成不能」分類は変わらない) | `(MitateDB-api, execution_ms)` / `(MitateDB-api-http, execution_ms)` |
| `operation_depth` | **両論 (§5 U-1)。依頼者判断待ち** | (A) `enforced` / (B) `unavailable` 据え置き | (A) 駆動する (既存 `_drive_operation_depth` `test_c05:299-356`) / (B) 駆動しない | (A) 2 組を撤去 / (B) 2 組を**残す** (理由を C-05 行と台帳へ) |
| **`request_bytes` (in-process、副項目)** | **r2db `limits.check_request` (`limits.py:37-70`) と同型の構造推定**を cell 層に置く — str は `len × 4`、bytes は `len`、scalar / None / bool は 8、container は 2 として積算し、**container の要素数が `bound // 8` を超えた時点で拒否**、総和が bound を超えた時点で拒否。in-process 面でも実効になる | **`enforced`** (in-process 面も) | **駆動する** (既存 `_drive_request_bytes` `test_c05:429-460`、**片側検査**。in-process plug が新たに駆動対象に入る) | `(MitateDB-api, request_bytes)` |

**HTTP 面の二重化について**: MitateDB HTTP は既存の実バイト middleware (`http.py:208`) を**維持する**。in-process の構造推定と HTTP の実バイト計測は**別の層で別の量を測る**が、**意味は「どちらか先に超えた方で拒否する」**であり矛盾しない。これは **r2db が既に採っている形と同じである** — r2db も HTTP 面では `RequestByteBoundMiddleware` (`http.py:475`) が実バイトで先に拒否し、通過した要求を `limits.check_request` (`service.py:996`) が構造推定で再度測る。**両層とも `LIMIT_EXCEEDED` + `details.limit_class = "request_bytes"` を返す**ので、client から見た応答は同一である。**この同一性を検査で固定する** (下記「検査の形」)。

**`http.py:576-592` の上書きを外す**: in-process が `enforced` になれば、HTTP 面が `limit_enforcement.request_bytes` を `unavailable` → `enforced` へ差し替える必要が無くなる。**上書き行 (`http.py:591`) を削除する** — 残すと「cell.py が capability 内容の単一の真実である」(R-3) という既決の分担に対して、意味のない冗長な上書きが残る。

**要求入口の一元化と、状態の置き場 (レビュー H-1 / H-2 反映)**: `ApplicationRuntime` (`cell.py:1335`) の全メソッドが既に `__authorize` (`:1348-1350`) を通る。**gate の「判定」はこの `__authorize` の直後**に置く。ただし **gate の「状態」(rate 窓・in-flight カウンタ・それらの Lock・deadline の起点) は `ApplicationRuntime` に持たせない** — 次の 2 つの実測がその形を禁じる。

- **`ApplicationRuntime` は要求ごとに新規構築される。** HTTP 面は `HttpService.authenticate` (`MitateDB-api/src/mitatedb_api/http.py:447`) が要求ごとに `ApplicationRuntime(cell, principal, guard, request_id=…)` を返し (`:480`、developer は `:479`)、各 endpoint はその都度 `_authenticate` (`:513-524`) を呼ぶ。in-process 面も `MitateDataService.open_session` (`MitateDB-api/src/mitatedb_api/service.py:78-96`) が呼ばれるたびに新しい session を返す。**したがって session オブジェクトに窓やカウンタを持たせると、要求ごとに初期化され、宣言だけが `enforced` に上がって実挙動は無制限になる (P-3 違反)。**
- **`ApplicationRuntime.__slots__` は `("__cell", "__principal", "__guard")` である** (`cell.py:1338`) ので、そもそも属性を足せない。**本設計は `__slots__` を変更しない。**

**カウンタのスコープ (決定)**: **`concurrency` の in-flight カウンタは r2db と同じ「プロセス (配備) 全体」**とし、**`requests_per_minute` は r2db と同じ credential_id 単位の窓**とする。r2db の現行スコープがそれである — `self._active` / `self._rate_windows` は `DataService` の属性であり (`r2db-api/src/r2db_api/service.py:1133-1144` / `:1156-1163`)、その 1 service が複数 application の cell を持つ (`:844`)。**契約上の意味を一致させる** (P-6) とは、同じ `limits.concurrency = N` の宣言が両 peer で「この配備全体で同時 N 本」を意味することである。

**置き場は実装 WP が新設する (1 プロセス 1 個)**: **MitateDB には現状、両 surface に共通する「プロセス単位の長寿命オブジェクト」が service.py に存在しない。** 実測は次のとおりである。

- in-process 面の cell 所有者は `ProvisioningFacade` (別名 `ControlPlane`、`service.py:11`) であり、`self.cells` (`:41`) に `provision_application` (`:43-58`) が `ApplicationCell` を 1 度だけ入れる。`MitateDataService` (`:72`) はそれを参照するだけである。**conformance in-process plug では、この 2 つを adapter が構築時に 1 度だけ作り (`MitateDB-api/conformance/conformance_adapter_mitatedb.py:358` / `:374`)、以後の全 port 呼び出しが同じ instance の `open_session` (`:957` / `:999`) を通る** — **要求をまたいで生きている。**
- HTTP 面は `ProvisioningFacade` を通らない。長寿命なのは合成根が持つ `cells` dict と、それを閉じ込めた `_cell_factory`、そして `HttpService` (`http.py:417`) である — 実配備は `main.build_app` が起動時に `cells` (`MitateDB-api/src/mitatedb_api/main.py:391` / `:420`) を作って `HttpService` を 1 個構築し (`:446`)、`app.state.service` (`http.py:968`) に置く。conformance HTTP plug も同型で、`self._cells` (`conformance_adapter_mitatedb_http.py:651`) から既存 cell を返すだけの `_cell_factory` (`:723-727`) と 1 個の `HttpService` (`:730`、隔離 instance は `:1477`) を持つ。**`ApplicationCell` 自体も、両面とも要求ごとに作り直されてはいない。**
- したがって **`ApplicationCell` に状態を置けば「application 単位」にしかならず、上記の決定 (配備単位) を満たさない。** **実装 WP は「1 プロセス 1 個」の限度状態ホルダを新設し、合成根が 1 個だけ構築して全 `ApplicationCell` に注入する。** **この形には既存の前例がある** — `audit_dispatch.AuditRouter` がまさに「`main.build_app` がプロセスに 1 個だけ作り、全 `ApplicationCell` と credential store に渡す」形で配線されており (`cell.py:308-318` のコメントと `main.py:368` / `:420`)、**同じ注入経路をそのまま再利用できる**。gate の判定は `ApplicationRuntime` が `self.__cell` 経由でそのホルダに触るだけであり、**`__slots__` も session の構築コストも変わらない。**

**順序は r2db の実順序に一致させる** (§1.2 (2))。

```
認証・認可 (__authorize / _require_data)
  → requests_per_minute        (credential 単位の窓)
  → concurrency 取得           (カウンタ + Lock、finally で解放)
  → request_bytes              (要求 dict の構造推定)
  → operation_depth            (U-1 (A) の場合のみ)
  → deadline = 受理時刻 + execution_ms を作って backend へ渡す
```

**この順序は本設計が新たに決めたものではなく、r2db の現物の順序である** — `_slot` が `_acquire_rate` → concurrency の順に置かれ (`service.py:1135-1140`)、`_slot` の内側で `check_request` → `check_depth` → deadline 生成が並ぶ (`:996-999` / `:1037-1039` / `:1072-1074`)。**枠の初稿は順序を誤っており (request_bytes → operation_depth → requests_per_minute → concurrency と書かれていた)、上記の実順序で置き換えた** (監督裁定 2026-09-06)。枠自身が「順序は r2db の順序と一致させる (設計が r2db の実順序を file:line で確認して書く)」と指示しており、**確認した実順序を採る**。

**宣言と実装は同一コミットで動かす** (P-3): `cell.py` の `limit_enforcement` の値の変更と、その class の enforcement の実装と、C-05 V3 の当該組の撤去は、**class ごとに 1 コミットに収める**。

#### 根拠 (file:line)

- 4 class が未実装であること: `MitateDB-api/src/mitatedb_api/cell.py:1494-1534` (宣言と、WP-4 が grep 実測で書いたコメント)。
- in-process `request_bytes` が未配線であること: `MitateDB-api/src/mitatedb_api/config.py:172-178` (`validate_request_size` の定義) と `cell.py:1499-1501` (呼び出し元が無いという自認)。
- 共通入口が既にあること: `MitateDB-api/src/mitatedb_api/cell.py:1348-1350` (`__authorize`)、`:1352-1394` (8 メソッドすべてが最初に呼ぶ)、`:1543-1560` (`ApplicationDeveloper` の schema 操作も同じ)。
- r2db の参照実装と順序: `r2db-api/src/r2db_api/service.py:1133-1144` / `:1146-1154` / `:1156-1163`、`:996-1000` / `:1037-1048` / `:1072-1079`、`r2db-api/src/r2db_api/limits.py:37-70` / `:73-75` / `:77-89`、`r2db-api/src/r2db_api/postgres.py:1936-1959`、`r2db-api/src/r2db_api/http.py:475`。
- 宣言語の一致 (`execution_ms` = `reference_wall_clock`): `r2db-api/src/r2db_api/service.py:936-937`。
- MitateDB の限度値の置き場: `MitateDB-api/src/mitatedb_api/config.py:20-35` (`FoundationConfig` の既定値群)、`:106-109` (env 名の対応表)。

#### 実装の形

1. **`MitateDB-api/src/mitatedb_api/config.py`** — `FoundationConfig` に 3〜4 フィールドを足す: `max_requests_per_minute` / `max_concurrency` / `max_execution_ms` (+ U-1 (A) なら `max_operation_depth`)。既存フィールドと同じく**既定値を持つ配備宣言**であり、env 名の対応表 (`:106-109`) にも同型で足す。既存の `validate_request_size` (`:172-178`) は**残す**が、in-process の構造推定は cell 層に置く (バイト長ではなく構造推定であり、意味が違う)。
2. **`MitateDB-api/src/mitatedb_api/cell.py`** — **判定**は `ApplicationRuntime` の `__authorize` (`:1348-1350`) の直後に置く。**状態は「1 プロセス 1 個」の限度状態ホルダ (新設) に置き**、`ApplicationCell` の構築引数として注入する (`audit_router` と同じ配線、`:300-318`)。ホルダが持つのは (i) rate 窓 (`principal.credential_id` をキーにした `dict[str, list[float]]` + `Lock`。**credential 単位**)、(ii) in-flight カウンタ + `Lock` の contextmanager (**プロセス = 配備単位**)。要求ごとに評価するのは (iii) 構造推定 (`request_bytes`)、(iv) U-1 (A) なら深さ検査、(v) deadline の生成である。**`ApplicationRuntime.__slots__` (`:1338`) は変更しない** — session はホルダに `self.__cell` 経由で到達する。**`ApplicationDeveloper` の schema 操作も同じ gate を通る** (継承関係上、同じヘルパを呼ぶ)。`limit_enforcement` ブロック (`:1494-1534`) と `limits` ブロック (`:1481-1493`) を同一コミットで更新する。
   - **合成根の配線 (同一コミット)**: `main.build_app` (`main.py:391` / `:420` / `:446`) と conformance 2 plug (`conformance_adapter_mitatedb.py:358` / `:374`、`conformance_adapter_mitatedb_http.py:651` / `:723-730`、隔離は `:1477`) が**ホルダを 1 個だけ**構築し、そのプロセスの全 `ApplicationCell` に同じ instance を渡す。**隔離 instance は自分専用のホルダを 1 個持つ** (共有 adapter のホルダに触れない)。
3. **`MitateDB-api/src/mitatedb_api/backend_postgres.py`** — 実行前に `SET LOCAL statement_timeout` / `lock_timeout` を残余から逆算して張り、`psycopg` の `QueryCanceled` / `LockNotAvailable` を `LIMIT_EXCEEDED`(`execution_ms`) へ写す。**r2db `postgres.py:1943-1959` と同型だがコードは共有しない** (P-6)。
4. **`MitateDB-api/src/mitatedb_api/backend_sqlite.py`** — 変更は app 側 deadline 検査の呼び出しのみ (DB 側 timeout は無い)。
5. **`MitateDB-api/src/mitatedb_api/http.py`** — `:591` の `request_bytes` 上書きを削除する。middleware (`:208-293`) は残す。
6. **`MitateDB-api/tests/`** — 4 class それぞれの peer-local テスト (拒否位置・error code・`limit_class`・解放)。**両 peer に同名ヘルパを置く場合のみ**同型性テストの対応表に行を足す (常設規律 6)。
7. **`MitateDB-api/conformance/conformance_adapter_mitatedb.py:837-847`** と **`conformance_adapter_mitatedb_http.py:1477-1478` 近傍** — 隔離 profile (`small_config`) に新フィールドの小さな値を与える。**すべての count 値は `_MAX_EXERCISABLE_LIMIT`(200) 以下**にする。**`concurrency` は駆動で実際に N 本の要求を保持するので、スレッド数として現実的な小さい値 (例 3) を置く。**
8. **r2db 側**: 4 class は既に実装済みであり **`src` は無変更**である。変更は D-2 の port 実装 (`conformance/` の 2 ファイル) と、隔離 profile の `concurrency` 値を駆動可能な小さい値へ下げること (現行 `concurrency=32` は `conformance_adapter_r2db.py:148` / `conformance_adapter_r2db_http.py:758`。32 本のスレッドを保持する形は避ける) に限る。

#### 検査の形

- **C-05 V2**: `requests_per_minute` / `request_bytes` の既存 driver が MitateDB でも真を返すようになる (宣言が `enforced` になるため、driver 冒頭の宣言判定を通る)。`concurrency` は D-2 の新 driver が駆動する。**変異**: MitateDB の gate から rate 窓の判定を外す → `_drive_requests_per_minute` が MitateDB 2 plug で赤。in-flight カウンタの上限判定を外す → `_drive_concurrency` が 4 plug で赤。構造推定の `bound // 8` の早期拒否を外す → `_drive_request_bytes` が MitateDB in-process で赤。
- **C-05 V3**: `_V3_KNOWN_UNAVAILABLE` (`test_c05:700-710`) から該当組を削除する。**削除と実装は同一コミット**であり、`strict=True` により順序を間違えれば必ず赤になる (実装が先なら XPASS で赤、削除が先なら通常の assert が赤)。
- **C-05 V1**: 宣言の自己整合 ((a)〜(e)) は既存のまま効く。`enforced` へ上げた class は **`limits` に有限値 (integer ≥ 1) を持つ**ことが V1 (c) で要求される — 値の追加漏れはここで赤になる。
- **既存の V1 統制 assert を同一コミットで撤去する (レビュー H-3 反映)**: `test_c05_limit_declaration_agreement.py:646-659` は「`unavailable` / `deployment_required` かつ `limits` に値を持つ class が存在すること」を計算し、`if adapter.name == "MitateDB-api":` (`:653`) でその存在を assert する。**現在その唯一の実例は in-process の `request_bytes` である** (値の公開と `unavailable` 宣言、`cell.py:1494-1534`。テスト自身の docstring が「the ONE currently-registered case」と書いている)。**D-1 後はこの組み合わせが 0 件になるので、撤去しなければ MitateDB-api plug で赤になる。** したがって **`request_bytes` を `enforced` へ上げるコミットと同一コミットで `:646-659` を撤去する** (§8 WP-1)。
  - **撤去して残る側の確認 (実装 WP が確認し §11.3 に記録する)**: この assert が守っていた命題 (**V1 (d) = `unavailable` でも `limits` 値を公開してよい、という非制約**) は、**同じテスト `test_c05_v1_d_unavailable_class_may_still_publish_a_limits_value` (`:615`) の前半**が全 plug に対して `_assert_v1_self_consistency` を実際に呼ぶ形で保持している (`:645`) — 撤去対象は同テストの**後半 (非空振り確認)** だけである。**失われるのは「その組み合わせが現に観測されている」という非空振りの担保であり、命題そのものの検査ではない。** 実装 WP はこの点を確認したうえで、**非空振りの担保が 0 件になったこと**を C-05 行の開示に反映する (§6.2)。
- **peer-local**: `execution_ms` の PG 側 timeout は MitateDB の PG テストで固定する (`MITATEDB_TEST_ADMIN_DSN` が要る)。**変異**: `SET LOCAL` を張らない → 長時間クエリが `LIMIT_EXCEEDED` にならず赤。
- **応答の同一性 (request_bytes の二重層)**: MitateDB HTTP で「middleware が先に拒否する要求」と「middleware を通過して構造推定が拒否する要求」の**両方**が `LIMIT_EXCEEDED` + `details.limit_class = "request_bytes"` を返すことを peer-local テストで固定する。**変異**: 構造推定側の `limit_class` を別の値にする → 赤。

#### 開示事項

- `execution_ms` は **`reference_wall_clock`** のままであり、**共通 suite は拒否位置を測らない** (V1 の整合検査と V3 のみ)。この状態は C-05 行の開示 (1) に既にあり、**本フェーズでも変わらない** (r2db も同じである)。
- U-1 が (B) になった場合、**`operation_depth` は 2 plug で `unavailable` のまま**であり、xfail 2 組が残る。その理由 (この peer の要求構造に有限の入れ子が無いこと) を C-05 行と台帳 (§10) に載せる。
- **カウンタのスコープ差は共通 suite では観測できない (レビュー H-2 反映)。** C-05 の隔離 surface が張るのは **application 1 個**であり、「配備単位」と「application 単位」の違いが表に出る場面が無い。**共通 suite が示せるのは「宣言値 N の位置で決定的に拒否される」ことまでであり、N が何を数えているかは示せない。** したがって本設計はスコープを**決定として固定し** (配備単位の in-flight、credential 単位の rate 窓)、その一致は**両 peer の peer-local テストと実装の形 (ホルダが 1 プロセス 1 個であること) で担保する**。**この限界を C-05 行の開示と台帳 (§10 L8-6) に書く。**
- **MitateDB は 1 cell あたり同時 1 操作である (レビュー H-4 反映)。** `ApplicationCell._lock` (`cell.py:329`、`RLock`) が application plane の全操作を包むので、**同一 application の要求は cell の内側で直列化される**。したがって MitateDB が宣言する **`concurrency` は「同時に受け付けて実行する本数」ではなく「拒否の閾値」である** — 閾値までは受け付け、超えた分を `LIMIT_EXCEEDED` で決定的に拒否する、という意味である。**この点を port docstring・C-05 行・台帳 (§10 L8-6) に開示する。** (r2db 側にこの直列化は無い — `PostgresCell._lock` (`r2db-api/src/r2db_api/postgres.py:328`) は接続プールの短い critical section であり、操作を直列化しない。)

#### 訂正註 (実装で確定した差、2026-09-07 = v1.3)

**本節の決定は変えていない。以下は WP-1a / WP-1b の実測で確定した、本文と実装の差である。**

1. **gate は `catalog()` / `schema_revision()` / `capabilities()` も通す (監督裁定、WP-1a 差し戻し 1 の 3)。** 本文「実装の形」2 は判定を `__authorize` の直後に置くとだけ書いたが、**r2db は 3 つとも `_slot` を通す**ので、P-6 (契約上の意味の一致) と SI-08 (request rate / concurrency) に合わせて MitateDB も同じにした。**通すのは rate / concurrency のみである** (`_limit_gate(principal, None, …)`)。**`post_schema` の revision 読み戻しは client 要求ではないので非 gate の内部経路に分離した** (`ApplicationCell._schema_revision_uncounted()` + `ApplicationRuntime._post_schema_revision()`) — 通したままだと schema 操作 1 回の窓消費が 2 倍になり、`schema_objects` driver が rpm=50 で早期に涸渇する (実測)。
2. **限度状態ホルダは「1 プロセス 1 個」の新設オブジェクトとして実装された** (本文「実装の形」2 の予告どおり)。合成根 (`main.py` / `service.py`) と conformance 2 plug が 1 個だけ構築して全 `ApplicationCell` に注入する。**変異「holder 構築を `ApplicationCell.__init__` へ移す」→ `test_limit_holder_is_shared_across_applications_in_one_process` が赤**で load-bearing を実測した。
3. **`operation_depth` は in-process 面でも `enforced` になった (両面 enforced、xfail 0)。** §5 U-1 裁定の「in-process 経路に要求 dict が無い形であれば in-process 側の 1 組だけ `unavailable` を残す」という逃げ枝は、**条件が成立しない** — レビューの実測により、**既定 `max_operation_depth=8` の下で 7 段ネストの json 値を持つ素の `session.insert()` が `LIMIT_EXCEEDED(operation_depth)` になる** (in-process の `values` 自体が要求構造である) ことが分かった。したがって `_V3_KNOWN_UNAVAILABLE` は `frozenset()` であり、**C-05 V3 の xfail は 0 である**。起草時に想定した「HTTP だけ `enforced`」という `request_bytes` 同型の非対称は生じない。**その帰結として、初稿実装が `http.py` に置いた `operation_depth` 上書きと `_operation_depth_limit` は削除され、`http.py` の差分は本文どおり「`request_bytes` 上書きの削除」(+ 上記 1 の `_post_schema_revision` 分離) に戻った。**
4. **`execution_ms` の写像は `transact` 経路にも要る。** 本文「実装の形」3 は `backend_postgres.py` とだけ書いたが、実装は **`insert_in_transaction` / `update_in_transaction` / `delete_in_transaction` の 3 経路**にも `QueryCanceled` / `LockNotAvailable` → `LIMIT_EXCEEDED`(`execution_ms`) を置いた (rollback は置かない — 外側の `transact()` が単一の rollback 点である)。peer-local テスト `test_execution_ms_pg_lock_timeout_maps_to_limit_exceeded_via_transact` を足し、**`SET LOCAL` を張る行を消す変異が赤 (無限待機 → タイムアウト)** であることを実測した。
5. **`already_consumed` (`test_c05:383`) の再測定結果**: MitateDB in-process = **0**、MitateDB HTTP = **1**、r2db in-process = **0**、r2db HTTP = **1**。**式は `1 if "http" in adapter.name else 0` に統一した** (transport 固有であり peer 非依存)。MitateDB HTTP が 1 になるのは上記 1 で `capabilities()` を gate 対象にしたためである。
6. **`request_bytes` の `bound // 8` 早期拒否は、既存 V2 driver では赤にならない。** 既存レシピは長い文字列を使うため総和側で先に拒否される (実測、4 plug 全緑のまま)。**この行を真に load-bearing にする peer-local テストを新設した** (`test_measure_request_bytes_rejects_a_container_with_too_many_elements_before_the_running_total_would`)。
7. **MitateDB の `_measure_request_bytes` は r2db の `check_request` と 2 点で異なる** (契約上の意味 = 片側検査には影響しないが、同型性の差として記録する): **循環検出が祖先パス限定である** (r2db は走査済み全体)、**未知型を `+8` で受ける** (r2db は `VALIDATION_FAILED`)。台帳 **L8-10**。
8. **gate の実順序は `cell.py:536-541` で `rate → concurrency → request_bytes → operation_depth → deadline`** であり、本文の順序表どおりである。順序を固定する peer-local テストを 2 本足した (`test_gate_denies_requests_per_minute_before_concurrency` / `..._before_request_bytes`)。**監査の自作変異 A (rate 窓のキーを credential から全体共通へ) が peer-local 2 本と C-05 V2 の MitateDB 2 plug を赤にした** — **credential スコープは load-bearing である**。

---

### D-2 port v1.12 (in-flight 保持 primitive と L7-21 の能力判定化)

#### 決定

1. **in-flight 保持 primitive を port へ足す。** `isolated_application_surface()` が yield する adapter に、`hold_in_flight(n)` 相当の context manager を足す。**意味は次の 1 文である** — 「**n 個の application plane 要求を、service の in-flight 窓の内側で停止させたまま保持する。保持中に n+1 個目を出すと `LIMIT_EXCEEDED`(`concurrency`) で拒否される。解放後、保持していた n 個はすべて正常に完了する**」。
2. **製品コードにテスト用フックを足さない。** 停止点は **adapter が out-of-band で構築した cell オブジェクト (peer によっては backend) を adapter 側でラップして作る**。**in-flight カウンタの内側で止まること**が要件である (カウンタ取得後、DB 実行前)。**MitateDB ではラップ対象を cell の操作メソッド入口に取る** (下記 (b) の理由)。
3. **4 plug すべてが実装する。** r2db 2 plug も実装することで、C-05 行の開示 (3) が指す差集合 (「`enforced` と宣言されているが検査形が無い `concurrency`」) が閉じる。
4. **L7-21**: port v1.12 に**要求側の optional フィールド**を足す — `select_eq` / `attempt_filter` 系に **page size (`limit`)** と**複数述語 filter** を運ぶ手段。**除外判定を peer 名から「この adapter がこのフィールドを port 経由で運べるか」の能力判定へ置き換える。** 4 plug とも運べるようにするので、**除外は消える**。
5. **`CONFORMANCE_ADAPTER_V1.md` を v1.12 へ改版する** (§22 を新設、文書情報の版数行も更新)。

#### 根拠 (file:line)

- 現行 port に in-flight を保持する手段が無いこと: `conformance-tests/adapter.py:1717` / `:1720-1722` / `:1725-1727` / `:1907-1918` / `:2063-2065` (すべて 1 呼び出し = 1 完結の同期 signature)。
- HTTP plug が単一 loop の `run_until_complete` であること: `r2db-api/conformance/conformance_adapter_r2db_http.py:1156-1157`、`MitateDB-api/conformance/conformance_adapter_mitatedb_http.py:838-839`。**ASGITransport は in-process なので** (`:947` / `:736`)、in-process plug と同じラップが効く。
- 隔離 surface が out-of-band 構築であること、adapter が既に cell / backend へ手を伸ばしていること: `conformance_adapter_r2db.py:649-654`、`conformance_adapter_mitatedb.py:836-855` (**teardown が `cell._backend.close()` を呼んでいる**)。
- 停止点が「カウンタの内側・DB 実行前」に置けること: r2db は `_slot` の内側で `self._cells[...]` へ dispatch する (`service.py:1000` / `:1048` / `:1079` / `:1095`) ので、**cell オブジェクトを差し替えれば停止点はカウンタ取得後になる**。MitateDB も同型で、gate (D-1) の内側で backend を呼ぶ。
- L7-21 の除外が peer 名固定であること: `test_c05_limit_declaration_agreement.py:473-474` / `:507-508`。除外理由 (port が page/limit を持たない、述語が常に 1 個) は同ファイル `:465-472` / `:498-506` のコメントにある。

#### 実装の形

**(a) `hold_in_flight` の signature と意味 (port v1.12 の追加 1)**

```python
@abstractmethod
def hold_in_flight(self, session, n: int) -> AbstractContextManager[None]:
    """n 個の application plane 要求を、この instance の in-flight 窓の
    内側 (concurrency カウンタ取得後、DB 実行前) で停止させたまま保持する。

    - `with` の内側では、n 個が in-flight のまま保持されている。
    - その状態で通常の port 操作を 1 つ出すと `ConformanceDenial`
      (`LIMIT_EXCEEDED` / `details.limit_class == "concurrency"`) になる。
    - `with` を抜けると保持していた n 個はすべて解放され、正常に完了する
      (例外を上げない)。抜ける時点で n 個の完了を待ち合わせる。
    - `n` は、この instance が宣言する `limits.concurrency` 以下でなければ
      ならない (呼び出し側が assert する)。
    """
```

**(b) 停止点の作り方 (plug ごと)**

| plug | ラップ対象 | 停止点が「カウンタの内側」である根拠 | 並行性の作り方 |
|---|---|---|---|
| `r2db-api` (in-process) | 隔離 instance の `DataService` が持つ cell オブジェクト (`conformance_adapter_r2db.py:649-650` が作る fresh adapter の service。dispatch は `service.py:1000` / `:1048` / `:1079`) | dispatch は `_slot` の `with` の内側にある (`service.py:986-1000` 等) ので、cell の `query` / `transact` / `apply_schema` に入った時点で `self._active` は既に +1 されている | port 呼び出しは素の同期呼び出しなので、**n 本の `threading.Thread`** から出せばよい |
| `r2db-api-http` | `cell_factory=iso._make_cell` (`conformance_adapter_r2db_http.py:1959-1961`) が返す `PostgresCell` をラップ | 同上 (service は同じ `service.py` の `_slot` を通る) | **n 本のスレッドが各自の event loop と `httpx.AsyncClient(ASGITransport(app))` を持ち、同一の ASGI app (= 同一 service) を叩く。** service の `_active_lock` は `threading.Lock` (`service.py:847`) なので、複数 OS スレッドからの本物の並行アクセスに対して安全である |
| `MitateDB-api` (in-process) | **`ApplicationCell` の操作メソッド入口** — adapter が out-of-band で構築した cell オブジェクト (`conformance_adapter_mitatedb.py:358` の `ControlPlane.cells` 配下、teardown で `cell._backend.close()` に既に到達している `:853-855`) の当該メソッドを、gate 付きの proxy に差し替える。**`_backend` はラップしない** | D-1 の gate が in-flight を取った**後**、`ApplicationCell._lock` (`cell.py:329`) を取る**前**に入る。したがって停止した時点でカウンタは +1 済みであり、**`_lock` はまだ握っていない** | 同 in-process、n 本のスレッド |
| `MitateDB-api-http` | 同上 — plug が自分で組む `ApplicationCell(..., backend=PostgresBackend(...))` (`conformance_adapter_mitatedb_http.py:926` 近傍、`self._cells` `:651` が保持) の**操作メソッド入口** | 同上 | 同 HTTP、n 本のスレッド + 各自の loop と client (`:1477-1481` の隔離構成の延長) |

**ラップの中身**は「最初の n 回の呼び出しだけ `threading.Event().wait()` で止め、`with` の終了時に `set()` する」小さな proxy である。**adapter 内部の実装詳細であり、port の意味には現れない。**

**MitateDB 側でラップ対象を `_backend` にしてはならない (レビュー H-4 反映)**: `ApplicationCell._lock = RLock()` (`cell.py:329`) は application plane の**全操作**を包み (`:430` `:498` `:517` `:532` `:542` `:561` `:601` `:706` `:920`)、**`_backend` の呼び出しはその `with self._lock:` の内側にある** (例 `:561`)。`_backend` で止めると 1 本目が `_lock` を掴んだまま停止し、**2 本目以降は `_lock` の獲得で止まって停止点に到達しない** — `hold_in_flight` が n 本の到達を待ち合わせる実装なら **n ≥ 2 で恒久ハングする**。**cell の操作メソッド入口 (lock 取得前) に置けばこの問題は生じない。** **r2db 側にこの制約は無い** — `PostgresCell._lock` (`r2db-api/src/r2db_api/postgres.py:328`) は接続プールの短い critical section であって操作を直列化せず、in-memory cell に lock は無い。**r2db は service の `_slot` の内側 = backend 呼び出し前であればどこでもよい。**

**停止点を「DB 実行前」に置くことには 2 つ目の効き目がある** — 保持中の n 本は**接続を掴まない**ので、HTTP + PostgreSQL plug の接続プールを枯渇させない。

**HTTP plug の単一 loop 構造との折り合い**: 現行の `self._loop.run_until_complete` (`conformance_adapter_r2db_http.py:1156-1157`) は「1 コルーチンを投げて呼び出しスレッドがブロックする」形であり、**1 本の loop では複数要求を同時に in-flight にできない**。したがって `hold_in_flight` の HTTP 実装は、**保持用のスレッドごとに新しい event loop と `AsyncClient` を作る** (共有 loop を跨いで使わない)。**共有 adapter の `self._loop` / `self._client` には触れない** — 隔離 instance の中だけで完結する。

**(c) L7-21 の能力判定化 (port v1.12 の追加 2)**

- `select_eq` / `attempt_filter` に **optional の要求側フィールド**を足す: (i) **page size** (client が「これだけ返してほしい」と申告する値)、(ii) **複数述語 filter** (1 呼び出しで 2 個以上の述語を提示する手段)。**既存 signature は壊さない** (optional 追加のみ)。
- 除外判定は **adapter の能力判定**にする — 「その adapter がこのフィールドを port 経由で運べるか」。**4 plug とも運べるように実装するので、実際には除外が消える。**
- **`result_items` は両側化する (実測で確認する)**: 宣言値 N に対して「page size = N を要求して N 行 → 成功」「page size = N+1 を要求して N+1 行 → 拒否」。**両 peer の検査位置は一致し得る** — r2db は `limits.check("result_items", min(len(rows), page_size))` (`r2db-api/src/r2db_api/postgres.py:1069`、`structured.py:1198`)、MitateDB は `limit > self.config.max_result_rows` で拒否する (`MitateDB-api/src/mitatedb_api/cell.py:557-560`) ので、**行が N+1 本以上あれば両者とも page_size = N+1 で拒否する**。**実装 WP がこの一致を実測して確認し、§11.3 に記録する** (一致しなければ片側のままとし、理由を C-05 行に書き直す)。
- **`query_complexity` は片側のままとする (結論。レビュー M-7 反映)**: **実測待ちではなく、metric の定義から算術的に既に決まっている。** r2db の metric は `len(where) + len(select) + order_by_count` であり (`test_c05:498-506` のコメント、`r2db-api/src/r2db_api/structured.py`)、**port の `select_eq` / `attempt_filter` は select を必ず 1 個以上運ぶ** (`conformance-tests/adapter.py:1720-1727`)。MitateDB の metric は `len(filters)` のみである。したがって述語を N 個運ぶ同一の要求は、MitateDB では metric = N (成功) だが r2db では metric ≥ N+1 (拒否) になり、**「N 成功 / N+1 拒否」の位置は構造的に一致しない**。**両側化は行わず、片側 (宣言を確実に超える構成の拒否 + 安全側の最小要求の成功) のままとし、この理由を C-05 行に書く** (§6.2 (2))。**能力判定化 (除外の撤去) は `query_complexity` にも適用する** — 片側であることと、peer 名で除外することは別である。
- **peer 名分岐の固定は「命題を限定した静的 assert + allowlist」で行う (レビュー H-5 反映)。** 固定する命題は **「V2 driver が『駆動するか否か』を peer 名で決めない」** の 1 つに限定する。**「`test_c05` から `adapter.name.startswith(` を 0 件にする」という形は採らない** — 撤去対象でない正当な名前使用を巻き込むためである。検査は次の形に置く。
  - **(i) 駆動可否の命題**: `_V2_DRIVERS` (`test_c05:529-538`) の各 driver 本体に、`adapter.name` を読んで early `return False` する分岐が無いこと。**変異**: `_drive_result_items` に `if not adapter.name.startswith("r2db-api"): return False` を 1 行戻す → 赤。
  - **(ii) allowlist と理由表**: `test_c05` 内で `adapter.name` を読む箇所を **allowlist 以外 0 件**に固定する (`adapter.name.startswith(` / `adapter.name ==` の逐語走査)。allowlist は次の 3 行であり、**本フェーズ後に残るのはこの 3 行だけである**。

| 行 | 何のための名前使用か | なぜ除外ではないか |
|---|---|---|
| `test_c05:266` (`_schema_objects_unit_cost`) | **peer ごとの実測計数規則** (r2db は entity + field 数で 3、MitateDB は table 1 個で 1) | 駆動可否ではなく**期待値の計算**である。`:251-265` のコメントが実測の根拠と「adapter-branching for its own sake ではない」ことを明記している |
| `test_c05:383` (`_drive_requests_per_minute`) | **HTTP plug の `authenticate()` が同じ rate 窓を 1 単位消費する**ことの補正 (`already_consumed`) | 駆動可否ではなく**観測位置の補正**である。実測 (`:375-382` のコメント) に基づく。**本フェーズで再測定する** (下記「検査の形」) |
| `test_c05:835` (`test_c05_e_isolated_application_surface_releases_resources`) | **MitateDB in-process (SQLite) 固有の資源解放観測経路** (`iso._control.cells` と `cell._backend._db` の生存確認) | 駆動可否ではなく**観測手段の違い**である。PG を使う plug は同テスト冒頭 (`:765`) で `_live_pg_backend_count` の**能力判定**により別経路を取る |

  - **`test_c05:653` は allowlist に載せない** — D-1「検査の形」で**同一コミットで撤去する**行だからである (H-3)。**撤去後、`:473-474` / `:507-508` と併せて peer 名分岐は 3 行になる。**

#### 検査の形

- **`_drive_concurrency` (新設、`_V2_DRIVERS` に 1 行追加)**: 宣言 `enforced` を確認 → `bound <= _MAX_EXERCISABLE_LIMIT` を assert → **rate headroom を assert する** → `hold_in_flight(bound)` で N 本保持 → **N+1 本目が `LIMIT_EXCEEDED` / `limit_class == "concurrency"`** → 解放後、**保持していた N 本がすべて成功して完了**。**4 plug 全数で駆動する。**
- **rate headroom の前提を明示する (レビュー M-2 反映)**: r2db の `_slot` は **`requests_per_minute` を `concurrency` より先に見る** (`r2db-api/src/r2db_api/service.py:1134-1136`) ので、N+1 本目が rate 側で拒否されると `_assert_limit_exceeded(..., "concurrency")` が**別の理由で赤になり、原因が読み取りにくい**。したがって `hold_in_flight` の前に **「この隔離 instance の `requests_per_minute` の残りが n+1 以上である」ことを assert する** (driver ごとに新しい隔離 instance を張る規約により窓は空から始まるが、**前提を書かずに依存しない**)。**同型の前提は `isolated_application_surface` の docstring が rpm driver について既に持っている。** 隔離 profile の現行値は r2db 2 plug が 50 (`r2db-api/conformance/conformance_adapter_r2db.py:150`、`conformance_adapter_r2db_http.py:757`) であり、**MitateDB の新 profile 値もこの assert が通る値にする** (D-1 実装の形 7)。
- **`already_consumed` の再測定 (レビュー M-1 反映)**: `_drive_requests_per_minute` の `already_consumed` (`test_c05:383`) は「in-process の `authenticate()` は gate を通らない」という**実測**に依存する (`:375-382` のコメント)。D-1 が gate を `__authorize` の直後に置くと、この前提は **MitateDB 2 plug について測り直しが要る**。**判定条件**: 隔離 surface の `capability_document()` / `authenticate()` が**専用の probe application/credential**を使い回すなら (MitateDB in-process は `conformance_adapter_mitatedb.py:497-516` がその形 — probe application/session を 1 度だけ作って使い回す)、drive が測る runtime credential の窓を消費しないので **0 のままでよい**。**WP-1 が MitateDB 2 plug について実測し、必要なら `:383` の式を能力/実測ベースへ直し、いずれの場合も測定結果を §11.3 に記録する。**
- **変異**: (i) 製品側の concurrency 上限判定を外す → 4 plug で赤。(ii) `hold_in_flight` のラップを「カウンタの外側」(gate に入る前) で止める形に変える → N+1 本目が拒否されず赤 (= 停止点の位置が load-bearing であることの実測)。(iii) 解放後の完了を待たない実装にする → 「N 本すべて成功」の assert が赤。
- **L7-21 の静的 assert (命題を限定、上記 (c))**: (i) `_V2_DRIVERS` の各 driver 本体に peer 名による early `return False` が無いこと、(ii) `test_c05` 内の `adapter.name` 使用が **allowlist の 3 行以外 0 件**であること。**変異**: `_drive_result_items` に `if not adapter.name.startswith("r2db-api"): return False` を 1 行戻す → (i) が赤。allowlist 外に `adapter.name == "…"` を 1 行足す → (ii) が赤。
- **`result_items` / `query_complexity`**: **`result_items` は両側**で N / N+1 の位置を、**`query_complexity` は片側** (「宣言を確実に超える構成の拒否 + 安全側の最小要求の成功」) を、**いずれも 4 plug で駆動する** (上記 (c) の結論)。**変異**: 宣言値だけを 1 大きく偽る → 該当 plug で赤。

#### 開示事項

- **C-05 行の開示 (1)(2)(3) と L7-21 記述を実測後に書き直す** (§6.2)。とくに **(3) は本フェーズで解消する** (`concurrency` が駆動対象に入る) ので、**「差集合が空である」ことを新たに書く**。
- `hold_in_flight` が作る並行性は **in-process の並行性である** (4 plug とも ASGITransport / 直接構築。L7-2 前)。**実ソケット・reverse proxy 越しの concurrency は本フェーズの射程外である** — port docstring と C-05 行にこの限界を書く。
- **MitateDB では 1 cell あたり同時 1 操作である** (`ApplicationCell._lock`、`cell.py:329`)。`hold_in_flight` の停止点は**その lock を取る前**にあるので保持自体は成立するが、**宣言する `concurrency` は「同時実行本数」ではなく「拒否の閾値」である**。**この意味を port docstring にも 1 文で書く** (D-1 開示事項と同文)。

#### 訂正註 (実装で確定した差、2026-09-07 = v1.3)

**本節の決定は変えていない。以下は WP-1b の実測で確定した、本文と実装の差である。**

1. **MitateDB 2 plug の停止点は「操作メソッド入口」ではなく `_limit_gate` 自体のラップである (監督追認、WP-1 差し戻し 2 の 6)。** 本文「実装の形」(b) の表と作業指示書 §2 WP-1b の逐語表は「`ApplicationCell` の操作メソッド入口」と書いたが、**操作メソッド全体をラップすると `_limit_gate` を実行する前に止まり、カウンタが増える前の停止になる** — 停止点要件 (カウンタ取得後・DB 実行前) を満たさない。実装は `_StalledGateContextManager` を新設し、**`_limit_gate` の `__enter__()` を実行した後**に停止する形にした (`cell.py:536-537` の counter 増分後、`cell.py:329` の `_lock` 取得前)。**変異 2 (ラップを gate の外側 = カウンタの外側に移す) → `_drive_concurrency` が `DID NOT RAISE` で赤**であり、停止点の位置が load-bearing であることを実測した。**r2db 2 plug は本文どおり cell オブジェクト (`catalog`) のラップである** (`service.py:1095` の dispatch = `_slot` の内側)。
2. **隔離 profile の `operation_depth` を 4 → 5 にし、V2 のレシピを `update` + `where` に改めた (監督裁定 R-A、2026-09-06)。** 本文 §1.2 (4) が前提にしていた「フラット insert が深さ 4 に座る」レシピは、**depth=4 のままだと隔離面で `where` 付き mutation が全て拒否される** — MitateDB の唯一の破壊的操作である `delete` を含むので、C-04 の MitateDB-http が赤になる (WP-1a rework 3 の実測)。**新しいレシピは「`update` + `where` (深さ 5) が成功 / `where` の value を dict にして深さ 6 で `LIMIT_EXCEEDED`」であり、4 plug とも隔離 profile は `operation_depth=5` を宣言する** (driver は `bound == 5` を assert する)。**変異 R-A (MitateDB in-process の profile を 4 に戻す) → C-05 V2 [MitateDB-api] が赤。** **フェーズ7 設計 D-6.2 の `operation_depth` 行 (旧レシピ) にも訂正註を置いた。**
3. **`result_items` のレシピは「表に bound+1 行を 1 度だけ入れ、成功側 `limit=bound` / 拒否側 `limit=bound+1`」である (監督裁定、WP-1 差し戻し 3 の 4)。** 本文「実装の形」(c) が書いた「N 行 / N+1 行を返してもらう」形では、**r2db の実検査 (`min(len(rows), page_size)`) は実行数側だけで位置が決まり、port の `limit` を adapter が捨てても suite が全緑になる** (監査の自作変異 B / B2 で実測)。改めたレシピでは **`limit` だけで N / N+1 が決まる**ので、**4 plug すべてで `limit` が load-bearing** になる (変異「r2db in-process の `limit` を無視」→ C-05 V2 [r2db-api] が赤)。**N / N+1 の位置は 4 plug とも `bound=5`、5 成功 / 6 拒否で一致した** (r2db = `min(rows, page_size)`、MitateDB = 要求 `limit` 値そのもの)。
4. **`query_complexity` は本文どおり片側のままである** (metric 定義の算術から決まる、実測待ちではない)。ただし片側検査の**安全側 / 拒否側を固定小定数ではなく `bound-1` / `bound+1` に締め直した** — 固定小定数では宣言値の膨張を検出できないためである。**MitateDB 自身の宣言偽装は検出できない** (r2db 型の "+1 tax" が metric に無い) ので、**変異は r2db 側の宣言値 +1 偽装で実証した**。
5. **`hold_in_flight` の待ち合わせには 30 秒の上限を置いた (監督裁定、WP-1 差し戻し 2 の 3)。** 停止点に到達しない回帰が**ハングではなく理由文付きの `AssertionError`** として赤になる形である (4 adapter とも)。保持スレッドは `daemon=True`、`join()` にも同 timeout を置いた。**あわせて CI の `conformance` job に `timeout-minutes: 30` を足した** (main `f4c2590`) — 壊れた前提は runner の上限まで待つのではなく赤として出るべきだからである。
6. **`hold_in_flight` の意味 1 文は port ABC (`conformance-tests/adapter.py`) の docstring に逐語で複製し、逐語一致を assert する文字列ピンのテストを test_c05 に置いた** (監督裁定、WP-1 差し戻し 3 の 1)。監査が「逐語 3 文がツリー内に 0 件、port docstring は言い換え」を検出したことへの是正である (常設規律 4)。
7. **`_drive_concurrency` の非空振り assert は、`hold_in_flight` が yield する実測保持本数 (semaphore の実測値) に対して取る** (監督裁定、WP-1 差し戻し 3 の 5)。初稿の `held = bound` 直後の `held >= 1` はトートロジーだった (監査 (E))。
8. **L7-21 の静的 assert は (i)(ii) とも AST 走査に統一した。** (ii) は `ast.Compare` (`==` / `in`) と `ast.Call` (`.startswith`) の全ノード (関数定義・非同期関数定義・モジュール直下) を歩き、**allowlist 3 行が実コードとして一致すること**も assert する (初稿はコメント行にマッチしていた)。(i) は `ast.If` + 同じ visitor に揃えた。
9. **`CONDITIONS.md` C-05 Status セルの書き換え後の文字数は 2,960 字である** (上限 3,000、余裕 40 字)。推移は 2,524 (書き換え前) → 2,926 → 2,886 (`[history]` リンクの重複 1 つを削除) → **2,960** (「V3: `xfail` は 0 件」の 1 文を追加)。
10. **MitateDB in-process adapter の `_attempt_mutation_outcome` を 2 点直した** (port 意味は不変、adapter 内部の修正): (a) `insert` / `update` に `filters` があれば `transact()` へ回す (旧実装は `insert` 分岐が `where` を握り潰しており、R-A のレシピが in-process で成立しなかった)、(b) `transact` 経由の影響行数を `len(results)` ではなく `results[0]` の実カウントから取る (旧実装は 2 行一致の update に 1 を報告していた)。(b) の固定として `test_c12_capability_agreement.py::test_update_reports_the_real_number_of_rows_affected` を新設し、4 plug で 2 行一致 → 2 / 0 行一致 → 0 を assert する。

---

### D-3 R-9 (テスト総数の下限) + L7-23 + L7-22

#### 決定

1. **下限はリポジトリ内のファイルに置く。** `conformance-tests/COLLECTION_FLOOR` (1 行、10 進整数のみ)。値は**前回 main の root `--collect-only -q` の件数**である。
2. **検査は `tools/check_collection_floor.py` (標準ライブラリのみ) に置き、CI はそれを呼ぶ。** ローカルでも同じコマンドで走る。CI の `conformance` job に **pytest の前** の step として足す。**3.11 / 3.12 の両 job で走らせる。**
3. **更新は明示コミットのみ。** 下限を下げるには当該ファイルを編集するコミットが要る (= 減少は明示の更新なしに赤)。**各フェーズの完了ゲートで、その時点の実測値へ更新する。**
4. **L7-23**: `_collect_marked_condition_ids` (`test_conditions_register.py:166-176`) に **「観測 0 件なら fail-loud」ガード**を置く。**skip にはしない** (空振り禁止、常設規律 1)。メッセージに理由 (「このテストは conformance 全体 run の内側でのみ評価できる」) を書く。
5. **L7-22**: 実態は充足済みである (§1.2 (9))。**ファイル変更は行わず、台帳側の状態注記を訂正する** (§10)。

#### 根拠 (file:line)

- CI の現況: `.github/workflows/ci.yml:63` (conformance job)、`:103-106` (pytest)、`:108-182` (tally 抽出)、`:207-242` (tally-consistency)、`:245-253` (scanner job が素の `python3` で tools/ を呼ぶ前例)。
- 現在の収集件数: **2274** (実測 2026-09-06、§1.3)。
- L7-23 の原因: `conformance-tests/test_conditions_register.py:166-176` / `:184` / `:198`。
- L7-22 の実態: `security/CONTROL_MAPPING.md:33` (L4-13 が現行行にある)、`conformance-tests/CONDITIONS.md:38` (L4-8 が現行行にある)。

#### 実装の形

- **`conformance-tests/COLLECTION_FLOOR`** — 1 行。前文もコメントも置かない (parser を単純に保つ)。運用規約は `conformance-tests/README.md` に散文で書く。
- **`tools/check_collection_floor.py`** — 標準ライブラリのみ。`python -m pytest --collect-only -q` を repo root で実行し、末尾の `<N> tests collected` を正規表現で読み、`COLLECTION_FLOOR` の値と比較する。**下回れば非 0 終了**し、実測値・下限・差分を 1 行で出す。**上回るのは正常** (増加は自由)。引数で floor ファイルのパスを上書きできる。
- **`.github/workflows/ci.yml`** — `conformance` job の pip install の後、pytest の前に 1 step を足す (`python3 tools/check_collection_floor.py`)。**3.11 / 3.12 の各 job で、その job 自身の collect 件数を `COLLECTION_FLOOR` と比較するだけにする。**
  - **collect 件数を tally artifact に載せて `tally-consistency` で突合することはしない (レビュー L-2 反映)** — 現状 `sys.version_info` による収集分岐はリポジトリに 1 件も無いので突合は成立するが、**将来 version 分岐を 1 つ入れた瞬間に `tally-consistency` が赤になる新しい義務を作る**ことになる。**新しい義務を作らない**方を採り、tally artifact の 4 数は現行のままとする。
  - **前提と費用 (レビュー L-1 反映)**: `--collect-only` は**収集時に 4 adapter を実構築する** — `conformance-tests/conftest.py:107-145` (`_discover_and_build`) が `registry.json` の各 entry を import して `build_adapter()` を呼び、それが module 読み込み時 (`:173`) に走る。したがって**この step にも PostgreSQL と全 DSN 環境変数が要り、HTTP plug の使い捨て DB provisioning が 1 job あたり 2 回 (collect step + pytest 本体) 走る**。**CI では PG 起動 step の後ろに置く** (`.github/workflows/ci.yml:77-82` の service 起動より後)。**この provisioning 費用の倍化は既知の代償として受け入れる** — 下限検査を pytest の外側から測る (§4 の却下理由) 以上、収集を 1 回余分に走らせること自体は避けられない。
- **`conformance-tests/test_conditions_register.py`** — `_collect_marked_condition_ids` の末尾に `assert ids, "<理由>"` を置く。

#### 検査の形

- **R-9**: `COLLECTION_FLOOR` の値を実測値より大きく書き換える → **CI の step が赤**、ローカルでも同じコマンドが赤。**変異**: floor を `2274` → `2275` にする (下限超過側)、および `check_collection_floor.py` の比較を `>=` から常に真へ変える (検査が効いていることの確認)。**pytest テストとしては置かない** — 部分実行で常に赤になる形 (L7-23 と同じ罠) を増やさない (§4)。
- **L7-23 のガードが完了ゲートで誤爆しない前提 (レビュー L-3 反映)**: `assert ids` が `-n 5 --dist loadgroup` の下で緑であるのは、**xdist の各 worker が session 全体を収集する** (収集は worker ごとに全件行われ、実行だけが分配される) からである。**この前提が崩れるとゲート全体が赤になる**ので、**WP-2 は完了ゲート形式 (`-n 5 --dist loadgroup`) でこのガードが緑であることを実測し、§11.3 に記録する。**
- **L7-23**: register ファイル単独で `pytest conformance-tests/test_conditions_register.py` を回すと、**ガードが「収集 0 件」を明示して赤にする** (今までは「全 20 条件にマーカーが無い」という誤誘導的な赤だった)。**同時に、`:198` 以降の vacuous pass が消える。** **変異**: ガードを外す → 単独実行で `:198` 以降が緑に戻る (= ガードが load-bearing であることの実測)。**この変異の観測は「単独実行のコマンド」自体で行う** (全体 run では両方とも緑なので差が出ない)。
- **L7-22**: 変異は無い (ファイル変更なし)。**監査照合** — 監査が `security/CONTROL_MAPPING.md:33` と `conformance-tests/CONDITIONS.md:38` を読み、L4-13 / L4-8 が現行行にあることと、§10 の状態注記がそれと一致することを突き合わせる。

#### 開示事項

- **COLLECTION_FLOOR の運用規約** (§6.4 に再掲): (i) 値は**前回 main の実測値**であり、フェーズ完了ゲートで監督が更新する。(ii) **下げるコミットは、下げる理由を commit message に書く**。(iii) **上げるのは自由だが、上げるのも完了ゲートの一部として監督が行う** (WP 途中で上げると他の WP のマージが赤になる)。

#### 訂正註 (実装で確定した差、2026-09-07 = v1.3)

**本節の決定は変えていない。以下は WP-2 の実測で確定した、本文と実装の差である。**

1. **「`--collect-only` は使い捨て DB provisioning を 1 job あたり 2 回走らせる」という本文「実装の形」の費用開示は、実測と合わない。** 実測 (WP-2 レビュー R-4): **`pg_database` / `pg_roles` の差分は 0** である。**正しくは「`--collect-only` は 4 adapter を実構築し PostgreSQL への接続検証を行うので、PG と全 DSN 環境変数が要る。使い捨て DB の provisioning は行わない」**である。**CI ではこの step を PG 起動 step の後ろに置く**という結論そのものは変わらない (接続検証があるため)。`conformance-tests/README.md` の運用規約は訂正後の文言で書かれている。
2. **`tools/check_collection_floor.py` は「読めなかったので緑にしない」側を明示的に持つ。** `<N> tests collected` 行が読めない場合に加え、**`returncode != 0` または summary 行に `error` を含む場合 (部分収集)** も非 0 終了する — `measured >= floor` でも緑にしない。監査の自作変異 D (DSN を死んだポートへ → 収集自体が RuntimeError) と B (`collect_ignore_glob` で 238 件を静かに落とす → `measured=2036 floor=2274 diff=-238` で EXIT=1) がこの 2 枝を独立に実証した。
3. **`COLLECTION_FLOOR` の値は完了ゲートで 2274 → 2340 へ更新した** (§11.1)。WP-1〜5 が足したテスト分である。
4. **`public_value_scan.py` は `git ls-files` ベースであり、未追跡の新設ファイルを走査しない** (既知の契約、L7-14)。**未追跡ファイルは明示引数で走査するか、`add` 後に再走査する** — pre-commit hook は staged なファイルを見るので commit 経路は塞がっている。本フェーズの各 WP はこの形で `total_flagged=0` を実測した。

---

### D-4 R-10 (契約 JSON の現行/履歴分離)

#### 決定

**逐語インベントリ (付録 A) の実測を受けて、本フェーズの R-10 は「provenance companion を置き、契約 JSON は 0 バイト動かさない」形 ((A)) を基本形とする。** インベントリが示したのは次の 3 点である。

- **マーカーを含む値は 29 件であり、値全体が経緯叙述であるものは 0 件である** — 29 件すべてに現行の規範文が同居する (付録 A §A.1 の `trailing_chars_after_last_marker` 列)。
- **`versioning.version_binding` (10,269 字) は単一の文字列であり、その全文が規範である** — 内容は版ごとの義務の網羅列挙 (「Only an implementation declaring 1.x.0 or higher additionally claims conformance to …」「(a) … (b) …」「Where it declares application_catalog …」の形) であり、**独立した経緯段落は存在しない** (監督が 36 文に分けて直読み、2026-09-06)。
- **29 値のうち 18 件が `test_contract.py` の PIN またはパス式 assert で逐語固定されている** (依頼者確定文言、常設規律 4)。

**したがって「値全体が経緯叙述のものを移す」「`version_binding` の経緯段落を移す」という起草時の形には実体が無い。** 決定は次のとおりである。

1. **companion は `spec/CONTRACT_HISTORY.md`** とし、**WP-7 の規約を再利用する** (新方式を作らない): **見出しは ID のみ** (タイトルを付けない)、**本文は逐語**、**register テストで機械固定する**、**更新規約は表の外の前文に散文で書く**。**見出しを ID のみに保つ規約は (A) でも維持する** — 理由は「リンクが壊れるから」ではなく (**(A) では contract JSON 側からのリンクが存在しないので壊れるリンクも無い**)、**anchor (見出し) の slug が ID から機械的に決まることが register テストの anchor 解決検査を成立させるから**であり、**WP-7 の規約 (`conformance-tests/test_conditions_register.py:58` の `_HISTORY_LINK_RE`、`:62-73` の `_github_slug`) をそのまま再利用するためである**。
2. **anchor の ID は「JSON パス」とする** (例: `## versioning.version_binding`)。`CONDITIONS.md` の C-XX に相当する識別子が契約 JSON には無いので、**記録の対象を一意に指せるのは JSON パスである**。
3. **anchor の中身は 3 点である** — (i) **マーカーの逐語**、(ii) 該当する **subordinate ruling の `spec/CCR_DISPOSITION.md` 上の見出し / 行**、(iii) **導入版**。ruling の所在は付録 A §A.3a の対応表 (`### 従属判断 — すべて裁定済み` 配下の番号付き項目) がそのまま使える。
4. **契約 JSON は 0 バイト動かさない。** 値の移動も接頭辞の剥離も行わない。その帰結として、
   - **PIN は 1 つも触らない** (`conformance-tests/test_contract.py` は無変更)。
   - **マニフェスト (`spec/CONTRACT_HISTORY_MANIFEST.json`) は要らない** — 移動が無いので「何をどこへ移したか」の正本が要らず、**companion の anchor 集合そのものが記録の正本**になる。
   - **deep-equal の意味不変検証も要らない** — 意味が動かないことは**既存の 3 複製バイト一致テストと sha256 の記録**で足りる (付録 A §A.0)。
   - **契約 JSON 側に companion への参照キーも置かない** (§4 の却下理由のまま)。
5. **register テストは常設スキャナを持つ。** 付録 A のプロトタイプ (`{scratchpad}/r10_marker_inventory.py`) の**正規表現をそのまま**常設テストへ移し (常設規律 5)、契約 JSON を走査して「**マーカーを 1 つ以上含む JSON パスの集合**」を機械的に列挙する。**この集合と companion の anchor 集合の一致が本方式の核である** — 契約に新しいマーカー付きの値が入れば、companion に anchor を足すまで赤になる。
6. **計画文書 §5 / §8 の R-10 行を改版する。** 計画文書が置いた検査文「現行 JSON から経緯マーカーが消えたこと」は、(A) では**満たせない** — 規範文を書き換えずに消せるマーカーが **0 件**だからである。**R-14 に従い、根拠 (付録 A の逐語インベントリ) と日付を添えて、当該行を「provenance companion (契約 JSON 不変) + register テストによる網羅性の固定」へ改版する。** 実施は **WP-6**、起票は §10 (**L8-8**)。
7. **版数は 1.6.0 のままである。** (A) では契約 JSON が 1 バイトも動かないので、版を刻むかどうかの論点自体が生じない。
8. **(B) (接頭辞の剥離) を採る場合の条件付き追加。** 依頼者裁定が (B) になった場合にのみ、次の 4 点を足す。
   - (i) **`spec/CONTRACT_HISTORY_MANIFEST.json`** — 1 エントリ = `{ "json_path": …, "kind": "prefix", "anchor": … }`。**マニフェストは「何を剥がしたか」だけを言い、契約の意味を持たない。**
   - (ii) **意味不変の機械検査** — 分離前 (main `9389fd5` の JSON) と分離後の JSON を、マニフェストの操作を逆適用したうえで **deep-equal 比較**する使い捨ての検証。**`tools/` に常設しない**。結果は §11.1 に記録する。
   - (iii) **PIN 定数の書き換え** (18 件) と、その前段としての**対象文の before/after 一覧の依頼者提示と再確定** (常設規律 4)。
   - (iv) **契約 JSON と両 peer の packaged 複製 2 本を同一コミットで同一バイトに更新すること** (既存のバイト一致テストが漏れを即座に検出する)。
   - **`versioning.version_binding` は接頭辞ではなく本文に版の言及が織り込まれているので、(B) でも動かない** (別枝 (C)、§5 U-2)。
   - **この場合、版数 1.6.0 のままでよいかの判断が改めて要る** — 依頼者確定文言そのものが変わるためである (§5 U-2、監督の推奨はフェーズ9 の契約 1.7.0 に載せること)。
9. **どちらを採るかは両論である** (§5 U-2)。**依頼者判断待ち。監督の推奨は「(A) を本フェーズ、(B) はフェーズ9 (契約 1.7.0)」である。**

#### 根拠 (file:line)

- WP-7 の companion 方式: `docs/design/PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md:480-518` (D-7)、`conformance-tests/test_conditions_register.py:58` (`_HISTORY_LINK_RE`)、`:62-73` (`_github_slug`)、`:246-350` (単一表 / ID 重複 / セル長 / anchor 解決 / 見出し集合一致 / 見出し配下非空の 6 テスト)、`conformance-tests/test_control_mapping_register.py:121-222` (同型 7 テスト)。
- 3 複製のバイト一致: `r2db-api/tests/test_http.py:286`、`MitateDB-api/tests/test_http.py:155`。**3 本の sha256 が一致することを起草時に確認した** (付録 A §A.0)。
- 経緯マーカーの分布と PIN: **付録 A** (逐語インベントリ)。集計は「マーカーを含む値 **29 個**、うち **18 個が test-pinned**、うち **2 個は製品コードがそのキーを読む**、`versioning.version_binding` が **10,269 字 = 13.32%**」である (§A.2c)。
- **値全体が経緯叙述の値が 0 件であること**: 付録 A §A.1 の全 29 行が `trailing_chars_after_last_marker` に非 0 の後続 (最小 4 字、最大 2,177 字) を持つこと。
- **`version_binding` が単一文字列で独立した経緯段落を持たないこと**: 付録 A §A.1 の当該行 (`(i) starts_with_marker=False, trailing_chars_after_last_marker=2631`) と、監督の直読み (36 文、2026-09-06)。
- 複合文の実例: `audit.query_operation_vocabulary` / `audit.query_target_kind_vocabulary` は "Since 1.5.0 (subordinate ruling 10, item 1, conditional): …" で始まる同一の 4 文を持ち、`versioning.version_binding` にも同じ 4 文がある。**`PIN_1_5_0_SENTENCE_1..4` (`conformance-tests/test_contract.py:447-467`) が 3 箇所すべてに対して逐語 assert している** (`:510-512` / `:519-522`)。
- subordinate ruling の所在: 付録 A §A.3 (`spec/CCR_DISPOSITION.md:93` の `### 従属判断 — すべて裁定済み`) と §A.3a の番号 → 行の対応表。
- 契約の意味部分に対する正規化 hash テストは**存在しない** (探索 (d) の grep 実測)。近い前例は `test_contract.py` の `_normalize_prose_for_pin()` (`:469-478`) のみである。

#### 実装の形 ((A) を基本形とする)

1. **`spec/CONTRACT_HISTORY.md`** — 見出しは `## <json_path>`、配下に上記 3 点 (マーカー逐語 / ruling の所在 / 導入版)。**割当の無い見出しは作らない。** 冒頭 (見出しの外) に前文を置き、**更新規約**(「契約 JSON に新しくマーカー付きの値が入ったら、同一コミットで本ファイルに anchor を足す」) と、**本方式の限界**(下記「開示事項」) を散文で書く。
2. **`spec/README.md`** — companion への到達経路を 1 段落足す (上記「開示事項」)。**契約 JSON は触らない。**
3. **`conformance-tests/test_contract_history_register.py` (新設、ファイル名は素案)** — 4 項目を固定する。
   - (i) **常設スキャナが列挙する JSON パス集合 = companion の見出し集合** (過不足なし)。
   - (ii) **見出しの重複が無い。**
   - (iii) **各見出し配下が空でない。**
   - (iv) **各 anchor が参照する subordinate ruling が `spec/CCR_DISPOSITION.md` の見出し (番号付き項目) に実在する。**
   - **`@pytest.mark.condition` は付けない** (新しい共通条件を作らないため。§6.5)。
4. **`spec/data-service-api.v1.json` と両 peer の packaged 複製 2 本 — 無変更である。** 既存のバイト一致テスト 2 本が、うっかりの変更を即座に赤にする。**ゲート時に 3 本の sha256 を §11.1 に記録する** (付録 A §A.0 の値と一致すること)。
5. **`conformance-tests/test_contract.py` — 無変更である。** PIN の参照先も定数も動かさない。
6. **計画文書 `docs/design/ROADMAP_POST_PHASE7_V1.md` の §5 / §8 R-10 行** — 上記「決定」6 の改版 (WP-6、R-14 に従い根拠と日付を添える)。
7. **(B) を採る場合にのみ**: マニフェスト、使い捨ての deep-equal 検証 (scratchpad。`git show 9389fd5:spec/data-service-api.v1.json` と現行を比較)、PIN 18 件の書き換え、契約 JSON と複製 2 本の同一コミット更新。

#### 検査の形

- **常設**: 新設 register テスト 4 項目 + 既存のバイト一致テスト 2 本 + 既存の `test_contract.py` の PIN 群 (無変更のまま効く)。
- **変異** ((A) の場合):
  - (i) **companion の見出しを 1 つ削除する** → 集合一致が赤。
  - (ii) **契約 JSON にマーカー付きの値を 1 つ足す** (scratchpad の使い捨て複製に対して行う) → 集合一致が赤。
  - (iii) **anchor 配下を空にする** → 非空検査が赤。
  - (iv) **ruling 番号を存在しない番号に書き換える** → 実在検査が赤。
  - (v) **packaged 複製 1 本だけを書き換える** → 既存のバイト一致テストが赤。
- **人手の突合 (機械化できない部分)**: WP-7 の L7-10 と同じ限界がここにもある — **機械検査は anchor の在否と空でないことしか見ない。** ただし **(A) では契約 JSON が 1 バイトも動かないので、「現行から規範文が落ちた」という危険そのものが生じない** — 人手の突合が担うのは「**companion に写した逐語が正しいか、ruling の対応付けが妥当か**」に縮む。レビューはこれを独立項目として持つ。**(B) を採る場合は、これに加えて「剥がした接頭辞以外が動いていないか」を deep-equal 検証と人手の突合の両方で見る。**

#### 開示事項

- **(A) では契約 JSON の長さは 1 文字も減らない。** P-7 への効きは「**`spec/` ディレクトリから 1 hop で経緯の一次資料 (subordinate ruling) へ辿れる**」ことに限られる。**「経緯を分離した」という主張が実際より強く読まれないよう**、この限界を **companion の前文**と台帳 (§10) に明記する。
- **(A) では契約 JSON の中から companion への in-band の参照は 1 つも無い (レビュー M-6 反映)。** 決定 4 が「契約 JSON に companion への参照キーを置かない」と決めている以上、**`spec/data-service-api.v1.json` を単体で読む経路には companion は現れない** — 到達性は「先に companion の存在を知っている読み手」にしか成立しない。**利用者は AI エージェントであり、契約 JSON だけを読む経路が実在する**ので、この非対称を放置せず、**到達経路を次の 2 箇所に置く**。
  - **`spec/README.md`** (`spec/` ディレクトリの目次であり、契約 JSON と `CCR_DISPOSITION.md` を既に紹介している) に **1 段落**を足す — companion (`spec/CONTRACT_HISTORY.md`) が存在すること、**anchor が JSON パスであること**、契約 JSON 側には参照キーを置かない方針であることを書く。
  - **companion の前文** — 何を記録するファイルか、契約 JSON は 1 バイトも動いていないこと、上記の限界。
  - **これは「契約 JSON から 1 hop」ではなく「`spec/` ディレクトリから 1 hop」である。** 本書および companion 前文でこの表現を使い分ける。
- **契約本体に残る経緯マーカーの件数 (29 値) を companion 前文に記録する。** 本フェーズ後もこの件数は変わらない。
- **計画文書 R-10 の検査文を改版する** (決定 6)。改版の事実・根拠・日付は計画文書自身と §10 (L8-8) に残す。

#### 訂正註 (実装で確定した差、2026-09-07 = v1.3)

**本節の決定は変えていない。以下は WP-3 の実測で確定した、本文と実装の差である。**

1. **各 anchor が複製するのは「マーカー句」ではなく「値の全文」である** (WP-3 の実装判断、監督承認)。本文「決定」3 (i) は「マーカーの逐語」と書いたが、**29 値はすべてマーカーと現行規範文が同居する複合文であり、マーカー句だけを切り出すと「その ruling が何を義務づけたか」が読めず、companion の効き (1 hop で一次資料へ) が消える**。**節のラベルは `Value (verbatim, full value copied from the contract JSON …; the history marker is embedded in it)` であり、`spec/README.md` の記述も同じ形に直した。**
2. **逐語一致の常設テストを足した** (監督裁定、WP-3 差し戻し 1 の 1)。本文「実装の形」3 の 4 項目に加え、**各 anchor の引用が現行 `spec/data-service-api.v1.json` の当該 JSON パスの値と byte 一致すること**を assert する (`_walk` を再利用)。**引用 1 文字の改変でこのテストだけが赤**である。あわせて「引用中に `Since X.Y.Z` があれば導入版フィールドがそれと一致すること」(対象 **17 件**、`checked == 17` を assert) も足した。**register テストは 5 → 7 本になった。**
3. **設計「決定」1 が ID のみ見出しの根拠に挙げた「slug の機械解決による anchor 解決検査」は実装に無い。** 実装は **companion の見出し文字列と JSON パスの生文字列比較**で代替している ((A) では契約 JSON 側からのリンクが 1 つも無いので、解決すべき slug が存在しない)。**「見出しを ID のみに保つ」規約そのものは維持する** (フェーズ9 で (B) を採るときに解決検査が要る)。
4. **ruling 参照は行番号を持たず、見出し番号のみで参照する** (監督裁定、WP-3 差し戻し 1 の 2)。行番号は 1 行の挿入で全部ずれるためである。実在検査 (`CCR_DISPOSITION.md` の従属判断節に当該番号が実在すること) はそのまま効く。
5. **29 値のうち 2 値は経緯マーカーを持たない。** `versioning.compatibility` と `destructive_confirmation.phrase_construction.rules[3]` は、**規範文中の `previously` に走査規則が一致した誤ヒット**である。**この 2 節には「history marker は無く、ruling の帰属は内容から付した」旨の 1 行注記を置いた** (開示済み)。**件数 29 そのものは付録 A と変わらない** — 走査規則を変えていないためである。
6. **機械検査の限界 (監査が変異で実測した 2 点、開示)**: (i) **`Since` を持たない 12 節の導入版は機械検査の外である** (裁定 3 が「該当しない 12 件は非空のみ」と明言した範囲どおり)。監査の変異 MUT-X (`control_plane.authority` の導入版を `9.9.9` へ) は緑のままだった。(ii) **ruling 帰属の「正しさ」は無検査であり、在否のみを見る** (本文「検査の形」の「人手の突合」が担う部分)。監査の変異 MUT-Y (`従属判断 6` → 実在するが誤った `従属判断 11`) は緑のままだった。**どちらも本文 D-4 の設計どおりであり、欠陥ではない。**

---

### D-5 R-11 (運用項目)

#### 決定

1. **`ops verify-declarations` を両 peer に同型で追加する。** `platform_declarations.py` の検査関数を順に呼び、**F 番号ごとに固定の終了コード**を返す。出力は **1 行 1 検査**。
2. **`PlatformDeclarationError` に F 番号の構造化属性 (`code`) を足す。** 現状はメッセージ文字列しか持たず、ops 側が prefix 判定に頼るしかない (`r2db-api/src/r2db_api/platform_declarations.py:132-136`)。**メッセージ文言は変えない。**
3. **deployment smoke test を `tools/deploy_smoke.py` に置く** (標準ライブラリ `urllib` のみ)。**入力は base URL と API key の「環境変数名」であり、引数で secret を取らない。** capabilities → catalog → 1 query を実打ちし、各段の結果を 1 行ずつ出して終了コードで返す。**両 peer 共通のツールでよい** — 契約が同じであり、**製品コードではない**。
4. **backup / restore の手順書を `docs/ops/` に置き、実証記録を残す** (r2db)。pg_dump カスタム形式 → 新 DB へ pg_restore → `ops verify-declarations` + smoke test で復元確認。**実証は Sonnet がローカル PG で実行し、対象 DB の catalog と 1 query の結果が復元前後で一致することを §11.1 に残す。**
5. **ops CLI 引数の secret 経路検査**: 現に見つかった `part1_provision_host_and_db.sh` の 6 箇所を**環境変数経由へ直し**、**静的規則を常設のテストとして置く。**
6. **L7-19 は撤去条件未達**である。状態注記のみ (§10)。

#### 根拠 (file:line)

- `ops` に secret 引数が無いこと・`verify-declarations` が無いこと: 両 peer `ops.py` の `_build_parser()` (r2db `:1620-1824`、MitateDB `:1366-1585`) と探索 (e) の grep 実測 (`add_argument(...dsn|password|api_key|pepper|secret|token)` = 0 件)。
- 検査関数が純関数として分離されていること: `r2db-api/src/r2db_api/platform_declarations.py:370-403` (`read_platform_declarations`、F-8 → F-3 → F-4 → F-4b/F-5 の順)、`:406-425` (`require_control_surface_declared`、F-3c)、`:451-` (`check_control_surface_consistency`、F-6)、`:613-` (`check_writer_role_timeouts`、F-7 / F-9 / F-10 / F-11 / F-13)。MitateDB は同型 (`MitateDB-api/src/mitatedb_api/platform_declarations.py:362-`)。
- 起動時にしか確かめられないこと: 呼び出し元は composition root だけである (r2db `main.py:360` / `:366` / `:400`、`control_main.py:465` / `:473` / `:486`)。
- argv に password を渡している 6 箇所: `r2db-api/deploy/scripts/part1_provision_host_and_db.sh:270` / `:279` / `:284` / `:289` / `:334` / `:335`。
- 移行先の手段: 各 migration は psql 変数 `:'control_password'` 等を使う (`r2db-api/migrations/0001_bootstrap_control_plane.sql:88`)。**psql は 14 以降 `\getenv` を持ち、作業機・CI とも PostgreSQL 16 である** (`psql (PostgreSQL) 16.14`、CI は `postgres:16`、`.github/workflows/ci.yml:77-82`)。
- L7-19: `constraints.txt:42` (`starlette==1.6.0`)、`filterwarnings` の 3 箇所 (`pyproject.toml:5`、`r2db-api/pyproject.toml:94`、`MitateDB-api/pyproject.toml:70`) と、それを固定する `conformance-tests/test_pytest_config_symmetry.py`。

#### 実装の形

**(a) `ops verify-declarations` の終了コード表 (両 peer 同一)**

| 終了コード | 条件 | 何を意味するか |
|---|---|---|
| **0** | 全検査 pass | 宣言はこのプロセスが起動できる状態である |
| **1** | 引数エラー | 使い方の誤り (検査結果ではない) |
| **2** | platform DB へ接続できない | 検査以前の失敗 |
| **3** | **F-3** | `surfaces` 行が無い |
| **4** | **F-3c** | `surfaces.control` が無い (`--control` を指定したときのみ検査) |
| **5** | **F-4** | `audit_coalescing_window_ms` 行が無い |
| **6** | **F-4b** | `audit_writer_roles` の値が不正 |
| **7** | **F-5** | `surfaces` の値が不正 |
| **8** | **F-8** | 宣言表そのものが無い (migration 未適用) |
| **9** | **F-6** | `surfaces.control` の有無と `<PEER>_CONTROL_PLANE_STATUS` が食い違う (env が与えられたときのみ検査) |
| **10** | **F-7 / F-10 / F-11** | 書き手 role の timeout 設定が無い/不正/per-database override |
| **11** | **F-13** | 接続中の role が宣言された書き手 role に含まれない |
| **12** | **F-9** | **接続中の role の実効 timeout 値が、宣言された値と一致しない** (この接続自身の effective setting を読む検査) |

**表の固定点は 0 = 全 pass、F-3 → 3、F-3c → 4、F-4 → 5、F-8 → 8 である** (枠の指定)。残りはその間を埋める形で本設計が確定した。

**F-9 に専用コード 12 を与える (レビュー M-4 反映)**: 起草初稿の表は F-9 の行を欠いていたが、**F-9 は両 peer に実在する検査条件**である — `check_writer_role_timeouts` の docstring が「(1) `current_user` が `declared_roles` に含まれるか (F-13) → (2) 宣言側の存在/妥当性 (F-7 / F-10 / F-11) → (3) **この接続自身の effective 値** (F-9)」の 3 段を明記している (`r2db-api/src/r2db_api/platform_declarations.py:628-633`、`MitateDB-api/src/mitatedb_api/platform_declarations.py:617-621`)。**10 に畳まず専用コードにする** — F-9 は「宣言が無い/不正」ではなく「宣言と実効値の食い違い」であり、運用上の手当てが別物 (role 設定の再適用) だからである。

**対象外の 3 条件 (F-1 / F-2 / F-12) を、理由付きで並べて書く**:

| 条件 | 定義位置 (両 peer) | 対象外の理由 |
|---|---|---|
| **F-1** | r2db `platform_declarations.py:193`、MitateDB `:181` | **廃止 env 変数が「定義されているか」はプロセス env の話**であり、provision DSN からは判定できない |
| **F-2** | r2db `:204`、MitateDB `:192` | 同上 (surfaces 側の廃止 env) |
| **F-12** | r2db `:43`、MitateDB `:20` (**cell-open-time, API-facing** と明記) | **cell を開く時点でしか判定できない**条件であり、宣言表の読み取りでは判定できない (実体は `backend_postgres` の pending platform upgrade guard) |

**この 3 条件が対象外であることを、出力の末尾に 1 行で書く。**

**出力形式** (1 行 1 検査、先頭に判定):

```
OK   F-8  declaration table present
OK   F-3  surfaces row present
FAIL F-4  audit_coalescing_window_ms row missing -- run `<peer> ops declare-coalescing-window --ms <N>`
```

**(b) `tools/deploy_smoke.py`**

- 引数: `--base-url-env <NAME>` `--api-key-env <NAME>` (**値ではなく環境変数名**)、`--entity <NAME>` (query 対象、既定は catalog の先頭)。
- 段: (1) `GET /v1/capabilities` → 200 かつ `contract_version` が読めること、(2) `GET`(catalog 相当の公開経路) → entity 一覧が読めること、(3) query 1 本 → 200。**各段の結果を 1 行ずつ出す。** 終了コードは 0 / 段ごとの非 0。
- **ローカルでの実証**: conformance HTTP plug が組む ASGI app を `uvicorn` で起動して叩く。**これは実ソケットを通す最初の機会になるが、L7-2 の plug ではない** — conformance の plug は増やさない (§6.6)。
- **secret の扱い**: 値は環境から読み、**引数にも出力にも出さない** (SI-10)。

**(c) argv secret 静的規則 (常設規律 5: 逐語プロトタイプ済み)**

**規則が主張する命題 (1 文、レビュー M-5 反映)**: **「配備スクリプトと両 peer の `ops.py` が、secret を子プロセスの argv に載せない」** — `ps` から見える形で secret が渡っていないこと、である。**環境変数経由で渡すことは違反ではない** (むしろ本設計が推奨する形である)。

規則 (Python `re`、逐語。**初稿の規則をレビュー M-5 に従って改めた版である**):

```python
SECRET_WORD = r"(?:password|passwd|pepper|secret|token|api_key|key)"

RULE = re.compile(
    r"(?:^|[\s;|&])-v[\s=][A-Za-z0-9_]*" + SECRET_WORD + r"\s*="   # (a) psql -v <...secret...>=
    r"|--password(?:=\S|[ \t]+[^-\s])"                              # (b) 値を伴う --password のみ
    r"|://[^/\s]*:[^@/\s]+@",                                       # (c) URL の userinfo
    re.IGNORECASE,
)
COMMENT = re.compile(r"^\s*#")
ENV_ASSIGN = re.compile(r"^\s*(?:export\s+)?[A-Za-z_][A-Za-z0-9_]*=")
```

**初稿からの変更点は 3 つである**。

- **(a) 対象語を `password` だけから `password|passwd|pepper|secret|token|api_key|key` へ広げた** — CLAUDE.md の公開ゲートは pepper / token / API key を明示的に守る対象に挙げており、初稿の規則は `-v pepper=…` / `-v api_key=…` を**取りこぼしていた** (レビューの実測)。
- **(b) `--password` は値を伴う形だけを対象にした** — 初稿の `--password(?:[=\s]|$)` は `psql --password -U <role>` のような**値を取らないプロンプト強制フラグ**を偽陽性で拾っていた (秘密は argv に出ない)。
- **(c) URL の userinfo を足し、(初稿の) `PGPASSWORD\s*=` の枝を外した** — 後者は `export PGPASSWORD="$X"` という**本設計が推奨する env 代入そのもの**と、`# never put PGPASSWORD= in argv` のような**コメント**を偽陽性で拾っていた。**行頭の env 代入 (`export X=` / `X=`) とコメント行は走査対象から除外する** (上記 2 つの正規表現)。

対象: `r2db-api/deploy/scripts/` 配下の全ファイルと、両 peer の `ops.py`。**現行ツリーに対するプロトタイプ出力 (改版した規則で 2026-09-06 に再実行、7 ファイル走査)**:

```
r2db-api/deploy/scripts/part1_provision_host_and_db.sh:270: -v control_password="${R2DBSVC_CONTROL_PASSWORD}" \
r2db-api/deploy/scripts/part1_provision_host_and_db.sh:279: -v api_password="${R2DBSVC_API_PASSWORD}" \
r2db-api/deploy/scripts/part1_provision_host_and_db.sh:284: -v controlplane_password="${R2DBSVC_CONTROLPLANE_PASSWORD}" \
r2db-api/deploy/scripts/part1_provision_host_and_db.sh:289: -v auditreader_password="${R2DBSVC_AUDITREADER_PASSWORD}" \
r2db-api/deploy/scripts/part1_provision_host_and_db.sh:334: -v runtime_password="${R2DB_APP_RUNTIME_PASSWORD}" \
r2db-api/deploy/scripts/part1_provision_host_and_db.sh:335: -v developer_password="${R2DB_APP_DEVELOPER_PASSWORD}" \
files scanned: 7 hits: 6
```

**現行は 6 件である** (枠が挙げた `control_password` 1 件ではない)。**改版した規則でも同じ 6 行であり、増減は無い。**

**WP-4 の完了条件 (常設規律 5 の形)**: **同一の逐語プロトタイプを「修正前」「修正後」の両方で走らせ、出力を §11.1 に記録する** — **修正前 = 6 件 (上記の 6 行)、修正後 = 0 件**。**片方だけの記録では完了としない** (規則が現に何かを捕まえていたことと、修正がそれを消したことの両方を残すため)。

**射程外 (開示)**:

- **偽陽性の残余**: (b) は `--password` の直後に**位置引数**が続く形 (例: `createuser --password <role>`) を区別できず、**flag に値が続いていると読んで拾う**。この形が将来必要になったら、**該当行を書き換えるか、規則の allowlist として理由付きで記録する** — 規則を緩めない。
- **取りこぼし**: **コマンド置換や変数展開で組み立てた文字列** (例: `psql "$(build_dsn)"`)、**配列展開**、**複数行にまたがる引数**は検出できない。**本規則は「行の見た目」に対する静的検査であり、実行時の argv を観測するものではない。**
- したがって**本規則の緑は「この 3 パターンが現行ツリーに無い」ことしか言わない** — secret を argv に載せないという命題そのものの全証明ではない。**この限界を常設テストの docstring に 1 文で書く。**

**修正の形**: psql の `-v` を止め、**`\getenv` で環境から読む prelude を psql の標準入力へ渡す**:

```sh
printf '%s\n' \
    "\\getenv control_password R2DBSVC_CONTROL_PASSWORD" \
    "\\i ${R2DBSVC_MIGRATIONS_DIR}/0001_bootstrap_control_plane.sql" \
  | psql "${R2DBSVC_BOOTSTRAP_ADMIN_DSN}"
```

**migration ファイル自身は変えない** — `:'control_password'` の参照はそのまま効く。**migration 冒頭のコメントにある `-v control_password=…` の使用例は、同一コミットで `\getenv` 形へ書き直す** (規則の対象外だが、読み手が古い形を写す事故を防ぐ)。

**常設のテスト** (`conformance-tests/test_deploy_secret_argv_scan.py`、ファイル名は素案): 上記の規則を対象ファイル群へ適用し、**flagged 0 件**を assert する。`@pytest.mark.condition` は付けない (§6.5)。

**(d) backup / restore**

- **`docs/ops/BACKUP_RESTORE_R2DB.md`** — pg_dump (カスタム形式) → 新 DB へ pg_restore → `ops verify-declarations` → `tools/deploy_smoke.py` の順の手順書。**実値は書かない** (`<UPPER_SNAKE>` placeholder と `*.example.invalid` のみ)。
- **実証記録**: 対象 DB の catalog と 1 query の結果が復元前後で一致したことを、§11.1 に集計行として残す。

#### 検査の形

- **`ops verify-declarations`**: 両 peer の ops テストで、**F 番号ごとに 1 本ずつ**「その条件を作って当該終了コードが返る」ことを固定する。**両 peer に同名で置くヘルパは同型性テストの対応表に載せる** (常設規律 6)。**変異**: 終了コード表の 1 行を別の値にする → 該当テストが赤。`code` 属性の付与を 1 箇所落とす → 該当 F の終了コードが既定値になり赤。
- **argv 規則**: 上記 (c) のテスト。**変異**: `part1_provision_host_and_db.sh` に `-v x_password="$FOO"` を 1 行足す → 赤。
- **smoke test**: **変異**: 段 2 の判定を常に真にする → ローカル実証で catalog を空にしたときに 0 を返してしまう…この形は「実配備に対して走らせる道具」であり、**pytest の完了条件としては扱わない**。**監査照合** — 監査は §11.1 の実証記録 (段ごとの出力と終了コード) を手順書と突き合わせる。
- **backup / restore**: 同上、**監査照合**である (実行環境に依存するため変異を作らない)。

#### 開示事項

- **`verify-declarations` は「provision DSN から見える宣言」だけを検査する。** プロセス env に依存する **F-1 / F-2** と、**cell を開く時点でしか判定できない F-12** は射程外であり、**出力の末尾にその限界を 1 行で書く** (上記 (a) の対象外表)。
- **`tools/deploy_smoke.py` は製品コードではない** (両 peer 共通の運用道具)。**契約に新しい面を作らない。**

#### 訂正註 (実装で確定した差、2026-09-07 = v1.3)

**本節の決定は変えていない。以下は WP-4 の実測で確定した、本文と実装の差である。**

1. **終了コード表への注記: argparse ネイティブの誤引数は 2 である。** 本文 (a) の表は「1 = 引数エラー」だが、**`verify-declarations` 自身の usage エラー (env 未設定) が 1 に揃う一方、argparse が自分で出す誤引数エラーは Python 標準機構の既定で 2 になる** — 共有パーサの `error()` を上書きすれば全サブコマンドに波及するので、**本フェーズでは上書きせず、表側に注記を置く形で決着した** (監督裁定、WP-4 差し戻し 2 の 4)。**表の固定点 (0 / 3 / 4 / 5 / 8) と F 番号側の割り当ては実装と逐語一致である。**
2. **`tools/deploy_smoke.py` の終了コードは段ごとに分けた** (監督裁定、WP-4 差し戻し 1 の 5 と差し戻し 2 の 3)。**1 = 段 1 失敗、2 = 段 2 失敗、3 = 段 3 失敗、4 = 段 3 未実施 (空 catalog / query 可能な field 無し)、5 = usage error**。**`--allow-empty-catalog` を明示したときだけ空 catalog が 0 になる。** 本文 (b) の「終了コードは 0 / 段ごとの非 0」を具体化したものであり、**空 catalog を黙って 0 で返す初稿実装 (「空の application は壊れた配備ではない」) は採らなかった** — 復元検証がそれで緑になるためである。
3. **provision script の psql prelude には `\set ON_ERROR_STOP on` が要る** (監督裁定、WP-4 差し戻し 1 の 1)。`\getenv` へ移しただけでは、**不在ファイルの `\i` も未定義 env の `\getenv` も psql が exit 0 で終わる** (実測: PostgreSQL 16.14 で 0 → 3 に変わることを確認)。**`-f` で流す 0002 / 0008 経路には `-v ON_ERROR_STOP=1` を渡した。** migration 冒頭コメントの使用例も同じ形に直した。
4. **argv secret 静的規則の実測は「修正前 7 ファイル走査 / 6 件、修正後 7 ファイル走査 / 0 件」である** (§11.1 に逐語)。**常設テストは規則の逐語 pin + 合成フィクスチャの 1 行ずつの検出 / 非検出 assert + 走査対象ディレクトリの実在と `.sh` が 1 件以上ある assert を持つ** — 「走査対象が消えても緑」になる形をレビューの変異が実証したためである。
5. **`verify-declarations` の書き手 role 検査 (F-7 / F-9 / F-10 / F-11 / F-13) は writer role の DSN で実行しないと意味を持たない。** provision / control role は `audit_writer_roles` に含まれない (migration が `[api_role, controlplane_role]` のみを seed する) ので、**素の provision DSN で実行するとこの段は常に F-13 = exit 11 になる**。**`docs/ops/BACKUP_RESTORE_R2DB.md` の手順 4 に、writer role の DSN で実行することと owner role で実行した場合に F-13 / exit 11 になる理由を明記した** (実測: writer role → exit 0、owner role → exit 11)。
6. **対象外 3 条件 (F-1 / F-2 / F-12) の 1 行は、PASS 経路だけでなく FAIL 経路 (exit 0〜12 の全経路) でも必ず出す。** 出力形式を固定するテストを両 peer に同名で置き、同型性テストの対象に加えた。**同型性表 (`_ISOMORPHIC_TARGETS`) は 67 → 86 行になった** (WP-4 で 4 行 → 8 行 → 5 行 + `_verify_declarations_checks` / `cmd_verify_declarations` を追加。pin テスト名も `..._86_rows` へ)。**監査の自作変異 B (`_verify_declarations_checks` のループ変数名だけ改名) が最初は全緑だったこと**が、この追加の直接の根拠である。
7. **`PlatformDeclarationError.code` はキーワード専用の必須引数にした。** 本文 (「検査の形」) の変異は「`code` 属性の付与を 1 箇所落とす → 該当 F の終了コードが既定値になり赤」と書いたが、実装では **`code=` を落とすと構築時点で `TypeError`** になる。**「付け忘れても動いてしまう」抜け道を作らない形であり、変異が該当テストを赤にするという実質は満たしている** (監督が受理)。

---

### D-6 R-12 (性能基準値ハーネス)

#### 決定

1. **`tools/perf_baseline.py`** を置く。4 adapter の `build_adapter()` を import し、各 plug で **3 op** を warmup + N 回実行して **p50 / p95 (ms)** と **1 要求あたりの backend 呼び出し回数 (`backend_calls`)** を出す。**3 op は次のとおりである** (監督裁定 2026-09-06)。
   - **`query`** = `select_eq` (述語 1 個)。
   - **`mutate`** = `insert` (1 操作)。
   - **`batch`** = **単一 entity の atomic mutation batch** (`attempt_batch_with_addresses`、**操作数 5**)。**両 peer で比較可能な唯一の複数操作単位であるため、3 列目はこれにする。**
   - **`cross_entity`** (`attempt_cross_entity_batch`) は **MitateDB 2 plug でのみ測る 4 列目**である。**`r2db-api` は `cross_entity_mutation: unavailable` を宣言しているので測らない** — **拒否の費用は性能の対象外である** (拒否経路を測っても意味のある比較にならない)。したがって出力は **4 plug × 3 op = 12 行 + MitateDB 2 plug × `cross_entity` = 2 行、計 14 行**である。
2. **`backend_calls` は、adapter が構築する backend / 接続オブジェクトをハーネス側でラップして数える。** **製品コードにカウンタを足さない** (D-2 と同じ原則)。
3. **閾値を置かない** (P-8)。**出力は固定形式の 1 行 / (peer, plug, op) であり、判定はしない。**
4. **4 plug 全部を測る。** HTTP plug は **ASGITransport の in-process 経路**であることをラベルに出し、**L7-2 後に実 socket 列が加わる前提**を書く。
5. **基準値は完了ゲート時 (全 WP マージ後の branch) に監督が単独実行し、§11.2 に表で記録する。** 以後の完了ゲートはこの行を添える (P-8)。

#### 根拠 (file:line)

- `build_adapter()` が pytest の外から呼べること: `r2db-api/conformance/conformance_adapter_r2db.py:1639`、`r2db-api/conformance/conformance_adapter_r2db_http.py:3219`、`MitateDB-api/conformance/conformance_adapter_mitatedb.py:1942`、`MitateDB-api/conformance/conformance_adapter_mitatedb_http.py:2271`。
- backend 呼び出し回数を数える既存フックが無いこと・近い前例: `MitateDB-api/tests/test_postgres.py:595-607` (backend メソッドの差し替えで呼び出し回数を数える)。
- HTTP plug が in-process であること: `conformance_adapter_r2db_http.py:947`、`conformance_adapter_mitatedb_http.py:736` (ASGITransport)。
- tools/ の規約 (標準ライブラリのみ): `tools/public_value_scan.py:1-23`。**ただし本ハーネスは conformance adapter を import する**ので、テスト依存 (`httpx` 等) は adapter 経由で入る — **ハーネス自身が新しい外部依存を足さない**、という形で規約を守る。
- 既知の性能観測が記述のみであること: `docs/design/PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md:763` / `:834` (L6-15)、計画文書 §7。

#### 実装の形

- **出力形式 (逐語)**:

```
PERF peer=<peer> plug=<plug> transport=<in-process|asgi-inprocess> op=<query|mutate|batch|cross_entity> n=<N> p50_ms=<x.xxx> p95_ms=<x.xxx> backend_calls=<n.nn>
```

- **`op=batch` は操作数 5 で固定する** (`ops=5` を README に明記し、後から変えたら §11.2 の脚注に書く)。**`op=cross_entity` の行が出るのは MitateDB 2 plug だけである** — r2db 2 plug ではハーネスが宣言 (`cross_entity_mutation`) を読んで**行を出さない** (拒否の費用を測らない、決定 1)。

- **plug 一覧は `conformance-tests/registry.json` を正本として読む (レビュー L-6 反映)。** **ハーネスに plug 名や module 名を手書きしない** — conftest が読んでいる正本と同じファイルを読む (`conformance-tests/conftest.py:32` の `REGISTRY_PATH`、`:100-105` の `_load_registry`)。**`build_adapter()` を呼ぶ前に conftest と同じ準備が要る**: registry の各 entry について **`<peer>/conformance` を `sys.path` に足してから import する** (`conftest.py:107-145` の `_discover_and_build` と同じ手順。各 adapter 自身も `conformance-tests` を `sys.path` に足す — 例 `conformance_adapter_mitatedb.py:44`)。**registry に plug が増えたら、ハーネスは黙って新しい行を出す** — これが「plug 選択を手書きしない」ことの効き目である。
- **先頭に実行環境の 1 行を出す**: `PERFRUN host=<uname -s/-m> python=<version> commit=<short sha> date=<YYYY-MM-DD>`。**実ホスト名は出さない** (公開規律 — OS 名とアーキテクチャのみ)。
- **`transport`**: in-process plug は `in-process`、HTTP plug は **`asgi-inprocess`**。実ソケット plug (L7-2) が入ったら `socket` の列が加わる。
- **反復回数と warmup (U-3、設計の裁量)**: **warmup 20、計測 N = 200** を既定とし、`--n` / `--warmup` で上書きできる。**`batch` (操作数 5) と `cross_entity` は 1 要求が重いので同じ N でよいか**を実行時に見て、必要なら `--n` で下げた値を §11.2 に記録する (**回数は出力行に必ず出る**ので、後から読み手が比較できる)。
- **`backend_calls` (指標名、レビュー L-5 反映)**: 各 plug が構築する backend / cell / 接続オブジェクトを、ハーネス側の proxy で包み、**backend の `execute` 相当の呼び出し回数** (in-memory / SQLite plug は backend メソッド、PG plug は cursor の実行) を数える。**1 要求あたりの平均**を小数 2 桁で出す。**指標名を `db_roundtrips` から `backend_calls` へ改めたのは、in-process 2 plug (r2db は in-memory cell、MitateDB は SQLite `:memory:`) で数えているものが DB プロセスへの往復ではなく、単なる呼び出し回数だからである** — 名前が測っていないものを主張しない形にする。**`transport` ラベルと README に「`backend_calls` は往復ではなく呼び出し回数であり、DB プロセスを跨ぐのは PG を通る plug だけである」と書く。**
- **`tools/PERF_BASELINE_README.md`** (または `tools/README.md` の 1 節) — 実行方法、必要な環境変数 (HTTP plug は実 PG が要る)、**数値の意味の限界** (in-process であること、往復の意味が plug 間で異なること、閾値が無いこと)。

#### 検査の形

- **本ハーネスはテストではない。** 完了条件は「**§11.2 に 14 行 (4 plug × 3 op = 12 行 + MitateDB 2 plug × `cross_entity` = 2 行) が記録されていること**」であり、**常設規律 2 の対応表では「文書・記録」条件として扱い、変異を作らない**。**監査照合** — 監査は §11.2 の行が出力形式どおりであること、`transport` ラベルが plug と整合すること、`commit` がゲート時の branch head と一致することを突き合わせる。
- **例外 (自己検査は非空性に限定する、レビュー L-5 反映)**: ラップが「数えていない」形になっていないことだけを、**ハーネス自身の自己検査**で示す — **`query` 1 回に対して `backend_calls >= 1` であること**を実行時に assert し、満たさなければ非 0 終了する。**これ以上の主張 (特定の回数であること) は自己検査に持たせない** — 回数は測定対象であって前提ではない。

#### 開示事項

- **HTTP plug の数値は ASGI in-process の値であり、実ネットワーク・reverse proxy・TLS を含まない。** §11.2 の表と台帳 (§10) にこの注記を置く。
- **閾値は無い。** 退行の扱いは計画文書 §7 の 3 のとおり、**基準値が 2 フェーズ安定した後にゲート化を審議する。**

#### 訂正註 (実装で確定した差、2026-09-07 = v1.3)

**本節の決定は変えていない。以下は WP-5 の実測で確定した、本文と実装の差である。**

1. **op 名は `query` / `mutate` / `batch` (+ `cross_entity`) である。** 計画文書 §5 / §7 / §8 の R-12 行が書いていた「query / mutate / cross-entity」は**本設計「決定」1 の監督裁定 (2026-09-06) で置き換わっている** — **`cross_entity` は `cross_entity_mutation` が `unavailable` でない plug (= MitateDB 2 plug) でのみ出る 4 列目**であり、3 列目は両 peer で比較可能な `batch` (単一 entity の atomic mutation batch、操作数 5) である。**計画文書側の R-12 行は WP-6 で R-14 に従い改版した** (§10 L8-8)。
2. **`cross_entity` の操作数は 2 entity × 1 insert である** (設計は op 数を固定していなかった。WP-5 の実装判断、README に開示)。
3. **`backend_calls` のラップ点は 4 plug で粒度が揃わない** (実測。**plug 間で比較しない指標である**): **PG を通る 2 plug** = `psycopg` の cursor 実行回数 (真の「1 SQL 実行 = 1 call」)、**r2db in-process** = `ApplicationCell` (in-memory) 自身の公開 4 メソッド (`query` / `transact` / `apply_schema` / `catalog`) なので**常に 1.00**、**MitateDB in-process** = `SQLiteBackend` の公開 20 メソッド (`begin` / `insert_in_transaction` / `commit` 等) を数えるので **11〜37** になる。**本文「開示事項」は in-memory / SQLite と PG の差までは書いていたが、in-process 2 plug 同士の粒度差は想定していなかった** — §11.2 の注記と `tools/PERF_BASELINE_README.md` に明記した。台帳 **L8-11**。
4. **ハーネスは `isolated_application_surface()` ではなく `build_adapter()` の結果を直接使い、op ごとに新しい runtime credential を発行して rate 窓を分離する** (本文「実装の形」は `build_adapter()` としか書いていない)。
5. **`--warmup` の値は出力に残らない。** 裁定 1 で `n=` を「集計標本数 (`len(durations_ms)`)」にした結果、warmup は PERF 行からも §11.2 の表からも復元できない。**PERF / PERFRUN は確定文言なのでフィールドを増やさず、ゲート時のコマンド行 (warmup と n) を §11.2 の注記に添える形で決着した** (監督裁定)。
6. **`_classify_plug` は名前接尾辞と属性形状が食い違う adapter に対して非 0 終了する** — 実 socket plug (L7-2) が入ったときに黙って `asgi-inprocess` とラベルしないためである。**L7-2 導入時にはラベルを明示的に足す必要がある** (README に 1 行)。
7. **計測窓に `BatchOperation` / `ScopedBatchOperation` の生成が残る** (監査 (1)、部分充足)。実測の窓内コストは **batch 0.00252 ms/回 (in-process p50 の 2.4〜4.7%)、cross_entity 0.00109 ms (3.6%)、mutate 0.00004 ms (≒0%)** である。**旧欠陥 (約 10%) からは下がったが「計測区間は adapter 呼び出しだけ」には未到達であり、この残余を §11.2 の注記に開示する。** **`BatchOperation` の事前生成は監督が最終修正した** (main `02afb01`)。

---

## 4. 却下した代替案

| 案 | 却下の理由 |
|---|---|
| **製品コードにテスト用フック** (`before_execute` callable、人工遅延 endpoint 等) を足して in-flight を作る | **製品面にテスト専用経路が乗る** — SI 上の面積が増え、しかも両 peer に同じ穴を開けることになる。adapter 側のラップで足りる (D-2) |
| **「実際に遅い要求」(大量行の集計等) で in-flight を作る** | **決定的でない。** 処理時間は実行環境依存であり、「ちょうど N 個が in-flight である瞬間」を保証できない。C-05 の他の driver が持つ「宣言位置ちょうどで拒否される」厳密さを満たせない (D-6.2 が `execution_ms` を「構成不能」に落としたのと同じ理由) |
| **R-9 を「CI で main を checkout して 2 回 collect」で実装する** | (i) main への push では「前回の main」が自分自身になる。(ii) `concurrency` の cancel-in-progress で直前 run が消えていることがある。(iii) **「明示の更新」という概念がどこにも現れない** — 減少を承認する行為が記録に残らない |
| **R-9 を pytest テスト (`len(session.items) >= floor`) で実装する** | **部分実行で常に赤になる** (L7-23 とまったく同じ罠を 1 つ増やす)。下限はテスト集合の外側から測るべき量である |
| **R-10 で契約 JSON に companion への参照キーを足す** | 契約本文に非規範キーを増やすのは**意味不変の範囲を越えかねない**。**companion の anchor (JSON パス) + register テストの常設スキャナ**で同じ追跡性が得られる (D-4)。**(A) では契約 JSON を 0 バイト動かさないので、参照キーを足せばそれ自体が唯一の契約変更になってしまう** |
| **`execution_ms` を `enforced` で宣言する** | **wall-clock は決定的に N+1 を構成できない。** r2db も `reference_wall_clock` であり (`service.py:936-937`)、P-3 (宣言は真である) を優先する。**実装が二重構え (app + DB 側 timeout) であることは、宣言語の選択を変えない** — 語が意味するのは「参照 wall-clock に対する best-effort である」ことである |
| **`requests_per_minute` をグローバル窓にする** (control plane と同型) | application plane の窓は **credential 単位**が r2db と同型であり (`service.py:1156-1163`)、**1 credential が他を締め出せない**。グローバルにすると同型性 (P-6) が崩れ、隔離 surface での駆動も他テストの traffic に汚染される |
| **性能ハーネスに閾値を置く** | **P-8**。閾値は bound として機能を縛る形 (P-5) になり得る。基準値が 2 フェーズ安定した後に審議する |
| **R-10 の意味不変検証を `tools/` に常設する** | 1 回きりの移行の検証である。**常設すべきは「現行 JSON から経緯が消えている」ことと「companion に逐語で残っている」こと**であり、それは register テストが持つ |

---

## 5. 未確定の選択肢 (依頼者判断待ち)

**本節の 2 項目は両論のまま置く。監督の推奨は明示するが、裁定は依頼者が行う。**

### U-1 `operation_depth` の枝

| | **(A) 実装して `enforced` を宣言する** | **(B) `unavailable` のまま据え置く** |
|---|---|---|
| **内容** | r2db `limits.check_depth` (`limits.py:77-89`) と同型の**汎用再帰深さ検査**を、MitateDB の要求入口 (HTTP の JSON body と in-process の要求構造の両方) に置き、`enforced` + `limits.operation_depth` の有限値を宣言する | 実装せず、`unavailable` の宣言と理由 (この peer の要求構造はフラットで、有限の入れ子が無い) を維持する |
| **根拠** | (i) SI-08 が bound すべき class に「**expensive or recursive operation depth**」を挙げている (`security/SECURITY_INVARIANTS_V1.md:226-240`)。(ii) **peer 同型** (P-6) — r2db は同じ検査を持つ。(iii) **JSON の入れ子は parser 資源の実 hazard** であり、P-5 の「安全上必要」に当たる。(iv) **駆動レシピが既に在る** — `_drive_operation_depth` (`test_c05:299-356`) はフラット insert が深さ 4 に座ることを利用しており、隔離 profile に `operation_depth=4` を置けばそのまま効く | (i) **P-5** — bound は安全上必要なものだけであり、有限の入れ子が構造的に存在しない peer に bound を足すのは「無いものを数える」形になる。(ii) 値の allowlist 検証が既に入れ子を拒否しており (`cell.py:1521-1533` のコメント)、深さの hazard は別の層で閉じている |
| **懸念** | **in-process 経路に「要求 dict」が存在しない形なら、in-process 側は `unavailable` のままになり得る** — MitateDB の in-process port 呼び出しは `insert(collection, values)` のように**引数で渡る**ので、r2db のような「要求 dict 全体」が無い。この場合 `request_bytes` と同じ非対称 (HTTP だけ `enforced`) が生じる。**実装 WP が実測して確定する。** また既存 driver は **N+1 を「insert に `where` を足す」形で作る**ので、MitateDB 側でも**深さ検査が内容検証より前に走る**ことが要る | **SI-08 の class が 1 つ peer 非対称のまま残る。** V3 の xfail が **0 にならず 2 組残る** (完了ゲートの `xfailed` が 0 ではなく 2 になる)。C-05 行と台帳にその理由を書き続けることになる |
| **影響範囲** | xfail **9 → 0**。触るのは `cell.py` の gate + `config.py` の 1 フィールド + 隔離 profile 2 箇所 (`conformance_adapter_mitatedb.py:837-847` / `conformance_adapter_mitatedb_http.py:1477-1478` 近傍)。PIN は無い | xfail **9 → 2**。触るファイルは無い (宣言も現行のまま)。C-05 行の開示 1 文と台帳 1 項目が増える |

**監督の推奨: (A)。** ただし **(A) を採っても、in-process 面が構造上 `unavailable` にとどまる可能性が残る** — その場合は「HTTP のみ `enforced`」という `request_bytes` と同型の正直な宣言になり、xfail は 1 組だけ残る。**実装 WP の実測結果を §11.3 に記録する。**

**依頼者裁定 (逐語、2026-09-06):** 「推奨で進めてください」 — 監督の推奨どおり **(A) を採る**: MitateDB に r2db `limits.check_depth` 同型の汎用再帰深さ検査を置き `operation_depth` を `enforced` にする。xfail は 9 → 0 を目標とし、in-process 経路に要求 dict が無い形であれば in-process 側の 1 組だけ `unavailable` を残して理由を C-05 行と §10 に開示する (実装 WP が実測)。**再審議しない** (計画文書 §9 手順 4)。

**【状態注記 2026-09-07 (フェーズ8 完了)】裁定 (A) は実装され、逃げ枝は使われなかった。** **裁定文が許した「in-process 経路に要求 dict が無い形であれば in-process 側の 1 組だけ `unavailable` を残す」枝は、条件が成立しない** — 実測により、**既定 `max_operation_depth=8` の下で 7 段ネストの json 値を持つ素の `session.insert()` が in-process でも `LIMIT_EXCEEDED(operation_depth)` になる** (in-process の `values` 自体が要求構造である) ことが分かった。したがって **`operation_depth` は両面 (in-process / HTTP) とも `enforced` であり、`_V3_KNOWN_UNAVAILABLE` は `frozenset()`、C-05 V3 の xfail は 0 である**。**C-05 行にも台帳にも「残った組」の開示は無い** (残った組が無いため)。詳細は §3 D-1 訂正註 3 と §11.3 WP-1a。

### U-2 R-10 の形 (逐語インベントリ後に改稿、2026-09-06)

**前提となる実測 (付録 A)**: マーカーを含む値は **29 件**、**うち値全体が経緯叙述のものは 0 件** (29 件すべてに現行の規範文が同居する)、**18 件は `test_contract.py` の PIN またはパス式 assert で逐語固定**され (依頼者確定文言)、**2 キーは製品コードがそのキーを読む**。`versioning.version_binding` は **10,269 字の単一文字列**で、内容は版ごとの義務の条件性 (unconditional / conditional) を定める**規範文**であり、`test_contract.py` は「N of those obligations are unconditional」の**件数まで** assert している。**したがって「経緯段落だけを移す」という枝は存在しない。** 計画文書 §5 の検査文「現行 JSON から経緯マーカーが消えたこと」は、**規範文を書き換えずには満たせない。**

| | **(A) provenance companion (契約 JSON は 0 バイト不変)** | **(B) 接頭辞の剥離** |
|---|---|---|
| **内容** | `spec/CONTRACT_HISTORY.md` を **JSON パスごとの anchor** で置き、各 anchor に「**マーカー逐語 → 該当 subordinate ruling の `spec/CCR_DISPOSITION.md` の見出し / 行 → 導入版**」を書く。**契約 JSON は 1 バイトも動かさない** | 29 値の "Since 1.x.0 (subordinate ruling N, …): " 等の**接頭辞 / 挿入句を剥がして** (A) の companion へ移し、契約本体には**規範文だけ**を残す |
| **契約 JSON の変化** | **0 バイト** (3 複製とも無変更。既存のバイト一致テストがそのまま担保する) | **29 値が動く。** マーカーが契約本体から **0 件**になる。**`versioning.version_binding` は接頭辞ではなく本文に版の言及が織り込まれているので (B) でも残る** (下記 (C)) |
| **機械検査** | **register テスト 4 項目** — 常設スキャナ (付録 A の正規表現をそのまま) が列挙する JSON パス集合 = companion の anchor 集合 / anchor 配下が非空 / 見出し重複無し / ruling 参照が `CCR_DISPOSITION.md` の見出しに実在。**マニフェストも deep-equal 検証も要らない** (JSON が動かないので、3 複製のバイト一致 + sha256 の記録で足りる) | (A) の 4 項目に加えて、**マニフェスト (`spec/CONTRACT_HISTORY_MANIFEST.json`)** と、**分離前後の JSON をマニフェストの逆適用後に deep-equal 比較する使い捨て検証**が要る |
| **PIN への影響** | **1 つも触らない。** 定数も参照先も動かない | **PIN 定数の文言そのものを書き換える** (18 件)。少なくとも `PIN_1_5_0_SENTENCE_1..4` (`test_contract.py:447-467`)、`PIN_1_6_0_ITEM_1_SECRET_IS_BEARER` (`:548`)、`PIN_1_6_0_ITEM_2_SURFACES` (`:551`)、`PIN_1_6_0_ITEM_3_FIELD_TYPES` (`:554`) が対象になる |
| **常設規律 4 との関係** | **抵触しない** (確定文言に触れない) | **抵触する** — **対象文の before/after 一覧を依頼者に提示し、再確定を得てから実装する**手順が要る |
| **計画文書 R-10 の検査文** | **満たせない。** R-14 に従い、**根拠 (付録 A) と日付を添えて計画文書 §5 / §8 の R-10 行を「provenance companion (JSON 不変)」へ改版する** (WP-6、§10 L8-8) | **満たせる** (契約本体からマーカーが 0 件になる) |
| **版数** | **1.6.0 のまま** (JSON が動かないので論点が生じない) | 意味は不変だが**依頼者確定文言が変わる**ので、版を刻むかの判断が改めて要る。**監督の推奨はフェーズ9 の契約 1.7.0 に載せること** |
| **P-7 への効き** | **「経緯の一次資料に 1 hop で辿れる」ことに留まる。JSON の長さは減らない** — この限界を companion 前文と §10 で開示する | **最も効く。** 契約本体が現行の意味だけになる |
| **手戻り** | 小。1 WP で閉じる | 大。対象文の一覧提示 → 依頼者再確定 → 実装 → PIN 書き換え |

**(C) `versioning.version_binding` の機械可読化** — 版ごとの unconditional / conditional な義務を**配列**に組み替える案。これは **R-8 (機械可読 artifact + 再生成一致テスト) と同じ問題**であり、**契約 1.7.0 (フェーズ9) の範囲**である。**本フェーズの両論には入れず、台帳 (§10 L8-9) へ送る。**

**監督の推奨: (A) を本フェーズで行い、(B) はフェーズ9 (契約 1.7.0) で版とともに行う。** 1.7.0 であれば確定文言の改版が自然に版に乗り、`versioning.version_binding` の 1.7.0 義務の列挙と同じコミットで扱えるため、**再確定を 1 回で済ませられる**。**(B) をフェーズ9 へ送る場合、その決定を台帳 (§10 L8-4) に日付付きで記録する** (R-14)。

**依頼者裁定 (逐語、2026-09-06):** 「推奨で進めてください」 — 監督の推奨どおり **(A) を本フェーズで採り、(B) はフェーズ9 (契約 1.7.0) で版とともに行う**。契約 JSON は 0 バイト不変、`spec/CONTRACT_HISTORY.md` を provenance companion として置き、register テストで固定する。計画文書 §5 / §8 の R-10 行は R-14 に従い改版する (§10 L8-8)。(B) の送り先はフェーズ9 として §10 に日付付きで記録する。**再審議しない** (計画文書 §9 手順 4)。

### U-3 (軽微、設計の裁量で確定済み)

性能ハーネスの反復回数と warmup の既定値は **warmup 20 / N = 200** とした (D-6)。**出力行に必ず `n=` が出る**ので、後から変えても比較可能性は失われない。

---

## 6. conformance への影響

### 6.1 port v1.12

`conformance-tests/adapter.py` を **v1.12** へ上げる。**追加は 2 項目、削除は無い。**

1. **`hold_in_flight(session, n)`** (D-2) — in-flight 保持の context manager。**4 plug すべてが実装する。** 意味論・停止点の位置・解放後の完了保証を docstring に書く。**「in-process の並行性である」という限界と、「宣言される `concurrency` は拒否の閾値であって並列実行能力ではない」(MitateDB は 1 cell あたり同時 1 操作) も docstring に書く。**
2. **要求側の optional フィールド** (D-2、L7-21) — `select_eq` / `attempt_filter` 系に **page size** と**複数述語 filter**。**既存の呼び出し形は壊さない。**

`docs/design/CONFORMANCE_ADAPTER_V1.md` に **§22 (v1.12)** を新設する (§21 = v1.11 と同じ構成: 追加メソッドの意味論 / 既存機構との関係 / 互換性影響)。**文書情報の版数行 (現行 1.11) も更新する。**

### 6.2 `CONDITIONS.md` C-05 行の書き換え箇所

**Status は変えない** (`executable (four adapters) -- …` のまま)。書き換えるのは**開示部分**である。

**セル長の余裕 (実測、レビュー M-3 反映)**: `conformance-tests/test_conditions_register.py:56` の `MAX_CELL_LENGTH = 3000` に対し、**C-05 の Status セルは現在 2,524 文字** (最長は C-09 の 2,948、C-19 の 2,942)。**余裕は 476 文字である。** 本フェーズの書き換えは削除 (L7-21 の 1 文) と追加 (下記の新しい 1 文と実測結果) の両方を含むので、**WP-1 は書き換え後のセル長を測って §11.3 に記録する**。**3,000 を超える場合は、開示の一部を `CONDITIONS_HISTORY.md#c-05` へ逐語で移して現行行を縮める** (現行/履歴分離の規約どおり。**開示を削って辻褄を合わせない**)。

| 現行の開示 | 本フェーズ後 |
|---|---|
| **(1)** 「駆動しない 3 class = `execution_ms` / `concurrency` / `idempotency_retention_ms`」 | **`concurrency` を外す** (D-2 の primitive で駆動されるようになる)。残りは `execution_ms` / `idempotency_retention_ms` の **2 class** |
| **(2)** 「片側のみ = `request_bytes` / `query_complexity`。`result_items` は両側だが r2db のみ」 | **次の形に書き直す** — `request_bytes` は**全 plug で片側** (MitateDB in-process も駆動対象に入る)、**`query_complexity` は 4 plug とも片側のままである**。理由は実測待ちではなく metric 定義の差から決まっている (r2db は `len(where) + len(select) + order_by_count`、MitateDB は `len(filters)` のみで、port の要求は select を必ず 1 個以上運ぶ — §3 D-2 (c))。**`result_items` は両側化し**、その位置一致は WP-1 の実測で確認する。**「r2db のみ」という限定は消える** (能力判定化により 4 plug が駆動対象になる) |
| **(3)** 「`concurrency` は両 r2db plug が `enforced` と宣言しているが検査形が無い」 | **逐語で限定して書く** — 「**`enforced` と宣言された class で、V2 の検査形を持たないものが 0 件である**」。**「差集合が空」とだけ書かない** (レビュー L-7 反映) — `execution_ms` は本フェーズ後も `reference_wall_clock` のままで V2 では駆動されず (開示 (1) に残る)、緩い言い方だとその 2 文が矛盾して読める |
| **L7-21 の既知ギャップ 1 文** | **削除する** (穴が閉じるため)。**なお現行の文は「the MitateDB exclusion for `request_bytes`/`query_complexity`」と書いているが、実装上 peer 名で除外されていたのは `result_items` / `query_complexity` である** (§1.2 (4))。**訂正の事実そのものは `CONDITIONS_HISTORY.md#c-05` へ逐語で移す** (現行/履歴分離の規約どおり) |
| **(4)(5)** および Acceptance boundary | **変えない** |

**あわせて足す文 (セル長の余裕 476 文字の内訳。WP-1 が実測で確定する)**:

- 「V2 の `concurrency` 駆動は **in-process の並行性**に対するものであり、実ソケット・reverse proxy 越しの並行性は L7-2 まで射程外である」。
- 「**MitateDB は 1 cell あたり同時 1 操作である** (`ApplicationCell._lock`)。宣言する `concurrency` は**拒否の閾値**であって並列実行能力ではない」(§3 D-1 開示事項、レビュー H-4)。
- 「**カウンタのスコープ (配備単位の in-flight、credential 単位の rate 窓) の一致は共通 suite では観測できない** — 隔離 surface の application が 1 個だからである」(§3 D-1 開示事項、レビュー H-2)。
- 「**V1 (d) の非空振り担保 (`unavailable` かつ `limits` 値を持つ実例) は 0 件になった**」(§3 D-1「検査の形」、レビュー H-3) — 命題自体は同テスト前半が保持する。

### 6.3 xfail 件数の遷移

| | 現在 | 本フェーズ後 |
|---|---|---|
| C-05 V3 `xfail(strict=True)` | **9** (`MitateDB-api` 5 + `MitateDB-api-http` 4) | **U-1 (A) なら 0** / **U-1 (B) なら 2** (`operation_depth` × 2 plug) |
| その他の xfail | 0 | 0 |

**撤去は class ごとに、実装と同一コミットで行う** (`_V3_KNOWN_UNAVAILABLE` から組を削除)。**V3 の parametrize 基底 (固定 9 × 4 plug = 36 ケース) は変わらない** — 収集件数はこの操作では動かない。

### 6.4 COLLECTION_FLOOR の運用規約

- 値 = **前回 main の root `--collect-only -q` の件数**。本フェーズ着手時点の実測は **2274** である。
- **更新は監督が完了ゲートで行う。** WP の途中で上げない (他 WP のマージが赤くなる)。
- **下げるコミットには理由を書く。** 「テストを消した」ことが記録に残る形にするための機構であり、下げること自体は禁止しない。
- 検査は `tools/check_collection_floor.py` (ローカルと CI で同一)。**CI は 3.11 / 3.12 の両 job で走らせ、各 job が自分の collect 件数を `COLLECTION_FLOOR` と比較するだけである** — **collect 件数を tally artifact に載せて `tally-consistency` で突合することはしない** (§3 D-3、レビュー L-2: 将来の version 分岐で赤になる新しい義務を作らないため)。
- **残余リスク (開示、レビュー L-4)**: **`COLLECTION_FLOOR` を実測値へ締める経路は完全に人手である** (完了ゲート項目 4)。したがって**ゲートとゲートの間は「(その時点の実測 − 下限) 本まで」のテスト削除が検知されない**。**下限が守るのは「大きく減ったこと」であって「1 本も減っていないこと」ではない。** この限界は機構の設計上のものであり、**ゲート間隔を短くする以外に機械的な手当ては無い**。

### 6.5 新規テストファイル一覧 (ファイル名は素案。作業指示書で確定する)

| ファイル | 何を固定するか | 条件マーカー | WP |
|---|---|---|---|
| `conformance-tests/test_contract_history_register.py` | R-10 の companion register 4 項目 (D-4) — 常設スキャナの JSON パス集合 = anchor 集合 / 非空 / 重複無し / ruling 実在。**(B) を採る場合はマニフェスト検査 2 項目を足す** | **付けない** | WP-3 |
| `conformance-tests/test_deploy_secret_argv_scan.py` | argv secret 静的規則が 0 件であること (D-5) | **付けない** | WP-4 |
| `tools/check_collection_floor.py` | (テストではない) CI とローカルの下限検査 (D-3) | — | WP-2 |
| `tools/deploy_smoke.py` | (テストではない) 配備後の実打ち (D-5) | — | WP-4 |
| `tools/perf_baseline.py` | (テストではない) 性能基準値 (D-6) | — | WP-5 |
| `conformance-tests/COLLECTION_FLOOR` | (データ) 下限値 | — | WP-2 |

**既存ファイルの変更**: `conformance-tests/adapter.py` (port v1.12)、4 adapter (`hold_in_flight` と要求側フィールド)、`conformance-tests/test_c05_limit_declaration_agreement.py` (`_drive_concurrency` 追加 / peer 名分岐の撤去 / 静的 assert / `_V3_KNOWN_UNAVAILABLE` の削減)、`conformance-tests/test_conditions_register.py` (収集 0 件ガード)、`conformance-tests/CONDITIONS.md` (C-05 行のみ)、両 peer の `tests/` と `ops.py` / `platform_declarations.py`、`.github/workflows/ci.yml`。**U-2 が (A) なら `conformance-tests/test_contract.py` と `spec/data-service-api.v1.json` (および packaged 複製 2 本) は無変更である** — (B) を採る場合にのみ、PIN 定数の書き換えと契約 JSON / 複製 3 本の更新が入る。

### 6.6 `CONDITIONS.md` の Status 変更と、新条件を足さない理由

- **Status 変更は無い。** C-00〜C-19 の 20 行はすべて既に `executable (four adapters)` であり、本フェーズはその状態を変えない。
- **新しい共通条件 (C-20 以降) を足さない。** 理由は次の 3 点である。
  1. **本フェーズは新しい命題を導入しない。** C-05 の命題 (「適用されるすべての resource class が有限で発見可能な bound を持ち、bound を超えた要求が決定的に終わる」) は既に存在し、本フェーズが行うのは**その命題の被覆を広げること** (駆動されない class を駆動されるようにし、peer 名固定の除外を消すこと) である。**被覆が広がることは条件の追加ではない。**
  2. **契約が変わらない。** 新しい条件は「契約または SI の新しい面を固定する」ときに足す。本フェーズは契約 1.6.0 の意味を変えず、SI も足さない (§7)。
  3. **R-9 / R-10 / R-11 / R-12 が固定するのはリポジトリの衛生と運用であり、peer 実装に対する implementation-independent な要求ではない。** `CONDITIONS.md` は後者の置き場である (CLAUDE.md)。したがってこれらのテストには `@pytest.mark.condition` を付けない — **既存の `test_control_mapping_register.py` / `test_pytest_config_symmetry.py` と同じ扱いである。**
- **plug は増えない** (4 plug のまま)。`tools/deploy_smoke.py` のローカル実証で uvicorn を起動するのは**運用道具の実証**であり、**conformance の plug ではない** (L7-2 は依然としてフェーズ10 の項目である)。

---

## 7. Security Invariants との関係

**新しい共通 Security Invariant は足さない** (制約 C2)。本フェーズが導入する要素はいずれも既存の invariant に載る。**Security Invariants は capability の許可リストではなく、守るべき安全成果の集合である** (CLAUDE.md「Security Invariants are not a feature gate」) — 本フェーズは**新しい安全成果を導入せず、既存の安全成果を実効化し、証明可能にする**ものである。

| 決定 | 載る invariant | 根拠 |
|---|---|---|
| **D-1** MitateDB の 4 class + `request_bytes` の実 enforcement | **SI-08** | SI-08 は「request body size / batch size / result size / query complexity / **execution time** / **concurrency** / **request rate** / schema object 数 / **expensive or recursive operation depth**」を bound すべき class として挙げ (`security/SECURITY_INVARIANTS_V1.md:230-240`)、**実装の自由度**を明記する (`:242-243`)。**したがって「未実装であること自体」は SI-08 違反ではなく、違反になるのは宣言が正直でないときである** (フェーズ7 §8 の判断)。本フェーズは**その隙間を実装側から閉じる** — 宣言を上げ、同時に実挙動をそれに合わせる。**新しい安全成果ではなく、既存の成果の実現である** |
| **D-2** port v1.12 (in-flight 保持、能力判定化) | **SI-08** | SI-08 の Verification は「境界・濫用テストが、上限を超えたところで決定的な拒否または終了を確認する」である (`:250-251`)。**`concurrency` はこれまで 1 度も確認されていなかった** — port に手段が無かったためである。本項はその**検証手段**を作る。**L7-21 の能力判定化も同じ** — 「peer 名で除外する」形は、宣言が偽であっても緑になり得るので、**SI-08 の Verification が空振りしていた**ことになる |
| **D-3** R-9 / L7-23 / L7-22 | **なし (SI 中立)** | 証拠の消失検知と、register テストの空振り防止である。**どの invariant の内容も変えない。** 測っているのは既存の SI に紐づく既存の条件が「実際に実行されているか」である |
| **D-4** R-10 現行/履歴分離 | **なし (形式のみ)** | **契約の意味を変えない** (D-4 の機械検査がそれを示す)。SI に対する契約の対応関係は不変である |
| **D-5** `ops verify-declarations` / smoke test / backup-restore / argv 規則 | **SI-02**、**SI-10**、(間接的に) **SI-14** | (i) **`ops verify-declarations` が検査する宣言は control plane の分離を成立させる前提である** — `surfaces.control` の有無と `<PEER>_CONTROL_PLANE_STATUS` の整合 (F-6 / F-3c) は、**control plane が別プロセス・別 listen で立つ**という SI-02 の担保が配備で崩れていないことを、起動前に確かめる手段である。(ii) **書き手 role の timeout 設定 (F-7 / F-10 / F-11 / F-13) は監査 sink の書き手側の設定**であり、SI-14 (security-relevant auditability) の実現条件に触れる。(iii) **argv の secret 経路は SI-10 である** — SI-10 は「database passwords/connection URLs」を「守るべきもの」に挙げており (`security/SECURITY_INVARIANTS_V1.md:287-292`)、`ps` から見える argv は公開面ではないが**同じ資産の露出経路**である。**新しい境界は作らない** — 既存の担保が配備で崩れていないことを機械的に確かめるだけである |
| **D-6** 性能基準値 | **なし (SI 中立)** | 計測のみ。**閾値を置かないので、bound として何かを縛ることもない** (P-5) |

**SI-08 について 1 点明記する**: フェーズ7 §8 は「MitateDB が 4 class を実装していないこと自体は SI-08 違反ではない — 違反になるのは、その状態を宣言が正直に表していないときである」と書き、宣言側で隙間を閉じた。**本フェーズは反対側 (実装側) から閉じる** — 実装が入れば宣言は `enforced` へ上がり、**共通 suite が拒否位置を実際に測る**。**SI-08 の Statement (「認証されているというだけで、1 client・1 credential・1 要求・1 操作がサービス資源へ無制限にアクセスできてはならない」) は変わらない** — 変わるのは、その成果が**両 peer で実際に成り立っていること**が示せるようになる、という点である。

**U-1 (B) を採る場合について 1 点明記する**: `operation_depth` が `unavailable` のままであることは、**SI-08 の "where applicable" の範囲内である** — この peer の要求構造に有限の入れ子が無いなら、bound すべき対象そのものが無い。**ただしその主張は宣言と台帳に明示され、C-05 V3 の xfail 2 組がその状態を可視のまま保持する** (静かに閉じない)。

---

## 8. WP 分割の素案 (作業指示書で確定する)

| WP | 内容 | 触るファイル (概略) | 並行 |
|---|---|---|---|
| **WP-1** | L7-1 + port v1.12 + L7-21 + V3 撤去 + C-05 行更新 | `MitateDB-api/src/mitatedb_api/` (`cell.py` / `http.py` / `config.py` / `backend_postgres.py` / `backend_sqlite.py`、**および限度状態ホルダを 1 個構築する合成根 `main.py` / `service.py`**)、`MitateDB-api/tests/`、`conformance-tests/adapter.py`、4 adapter (`*/conformance/conformance_adapter_*.py`)、`conformance-tests/test_c05_limit_declaration_agreement.py`、`conformance-tests/CONDITIONS.md` (**C-05 行のみ**)、`docs/design/CONFORMANCE_ADAPTER_V1.md`、`r2db-api/conformance/` (隔離 profile の `concurrency` 値のみ。`r2db-api/src` は無変更) | **単独 worktree。1a (MitateDB enforcement + xfail 撤去) → 1b (port v1.12: in-flight + L7-21) の順に同 worktree で直列** |
| **WP-2** | R-9 + L7-23 + L7-22 注記 | `.github/workflows/ci.yml`、`tools/check_collection_floor.py`、`conformance-tests/COLLECTION_FLOOR`、`conformance-tests/test_conditions_register.py`、`conformance-tests/README.md` | 並行可 |
| **WP-3** | R-10 | **(A) の場合**: `spec/CONTRACT_HISTORY.md` (新設)、`conformance-tests/test_contract_history_register.py` (新設)、`spec/README.md` (companion への到達経路 1 段落、D-4 開示事項) の **3 ファイルのみ**。契約 JSON・packaged 複製 2 本・`test_contract.py` は**無変更**。計画文書 R-10 行の改版は WP-6。**(B) の場合のみ追加**: `spec/data-service-api.v1.json`、両 peer の packaged 複製 2 本、`spec/CONTRACT_HISTORY_MANIFEST.json`、`conformance-tests/test_contract.py` (PIN 定数) | 並行可 (**U-2 確定後**) |
| **WP-4** | R-11 | 両 peer の `ops.py` / `platform_declarations.py` / `tests/`、`tools/deploy_smoke.py`、`r2db-api/deploy/scripts/`、`r2db-api/migrations/` (コメントの使用例のみ)、`docs/ops/`、`conformance-tests/test_deploy_secret_argv_scan.py` (新設) | 並行可 |
| **WP-5** | R-12 | `tools/perf_baseline.py` (+ README) | 並行可。**基準値の実測は完了ゲート** |
| **WP-6** | 記録・第 15 次引き継ぎ・計画文書 §1 / **§5 (R-10 の検査文の改版、D-4 決定 6)** / §8 の更新 (R-14) | `docs/` | **最後** |

### 8.1 触るファイルの重なり (ファイル名レベルの確認)

| 組 | 重なり | 根拠 |
|---|---|---|
| WP-1 × WP-2 | **0** | ともに `conformance-tests/` を触るが**別ファイル**である — WP-1 は `adapter.py` / `test_c05_*.py` / `CONDITIONS.md`、WP-2 は `test_conditions_register.py` / `COLLECTION_FLOOR` / `README.md`。**`CONDITIONS.md` を触るのは WP-1 だけであり、しかも C-05 行のみ**である |
| WP-1 × WP-3 | **0** | WP-3 は `spec/` と新設 register テストのみ ((B) を採る場合に `test_contract.py` が加わる)。**`CONDITIONS.md` を触らない** (新テストに条件マーカーを付けないので Status 行の追加も無い、§6.5) |
| WP-1 × WP-4 | **0** | WP-4 は両 peer の `ops.py` / `platform_declarations.py` / `deploy/` / `docs/ops/` と新設テスト。**WP-1 が触る `cell.py` / `http.py` / `config.py` / `backend_*.py` とは別ファイル**である。**両者とも `MitateDB-api/tests/` に足す**ので、**ファイル名を分ける** (WP-1 は limit 系、WP-4 は ops 系) ことを作業指示書で明示する |
| WP-1 × WP-5 | **0** | WP-5 は `tools/perf_baseline.py` のみ。**adapter を import するが変更しない** |
| WP-2 × WP-3 / WP-4 / WP-5 | **0** | WP-2 は CI workflow と `tools/check_collection_floor.py`。**WP-4 / WP-5 が足すのは `tools/` の別ファイル**であり、**CI workflow を触るのは WP-2 だけ**である |
| WP-3 × WP-4 / WP-5 | **0** | 対象領域が `spec/` と `deploy/` / `tools/` で分かれる |
| WP-4 × WP-5 | **0** | `tools/` の別ファイル |
| 全 WP × **WP-9 (フェーズ7 公開ゲート)** | **0** | WP-9 が触るのは `tools/rewrite_hash_refs.py` (新設) と docs/ の hash 参照の一括更新のみである。**本フェーズはそのファイルを作らない。** 本フェーズが新設する docs に commit hash を書いた場合、WP-9 の commit-map 適用対象になるだけで衝突しない |

**`COLLECTION_FLOOR` の値は、全 WP のマージ後に監督が最終更新する** — WP-2 が置く初期値は着手時点の実測 (2274) であり、WP-1 / WP-3 / WP-4 がテストを足せば実測は増える。**下限なので途中で赤にはならない。**

---

## 9. 完了ゲート

1. **root suite の単独実行** `./.venv/bin/python -m pytest -q -n 5 --dist loadgroup` (監督が単独で実行。`ps` で他の pytest が 0 件であることを確認してから。ローカル PG の `max_connections = 300` が前提):
   - **`xfailed` = 0** (U-1 裁定 (A)。**実測で in-process の `operation_depth` 1 組が残る場合のみ 1**、§5 U-1 裁定のとおり理由を C-05 行と §10 に開示する) **【v1.2 訂正: 旧「または 2 (U-1 (B))」は裁定前の枝であり無効】**
   - **`skipped` = 0**
   - **`failed` = 0**
2. **CI の 3.11 job の集計行が 1 の集計行と一致すること。** `tally-consistency` job が緑 (**3.11 / 3.12 の 4 数の一致。collect 件数は突合対象に足さない** — §6.4)。**collection floor step が 3.11 / 3.12 の両 job で緑であること。**
3. **`tools/perf_baseline.py` の PERF 行を §11.2 に記録すること** — **4 plug × 3 op (`query` / `mutate` / `batch`) = 12 行 + MitateDB 2 plug × `cross_entity` = 2 行、計 14 行**。実行は全 WP マージ後の branch に対して監督が単独で行う。
4. **`COLLECTION_FLOOR` をゲート時の実測値へ更新すること。**
5. **R-10 の記録**: **U-2 が (A) の場合**は、契約 JSON と両 peer の packaged 複製 2 本の **sha256 が付録 A §A.0 の値と一致すること** (= 契約 JSON が 0 バイト不変であること) を §11.1 に記録すること。**(B) の場合**は、deep-equal 検証の結果 (差分 0 と走査キー数) を §11.1 に記録すること。
6. **全 WP が常設規律 1〜7 と速度規律 1〜5 を満たすこと。** 各 WP の「完了条件番号 → 変異」対応表に、対応の無い行が無いこと。
   - **変異を持たない完了条件は 4 つある** — D-3 の **L7-22** (監査照合)、D-5 の **smoke test** と **backup / restore** (いずれも監査照合)、D-6 の **性能基準値** (記録)。**この 4 項目については、「照合対象の逐語記録 (実行したコマンドと集計行、または file:line) を §11 に残すこと」自体を完了条件とする** (レビュー L-8)。**受け入れ監査は §11 のその記録を逐語で報告に引く** — 変異が無い項目ほど「何を見て緑と言ったか」を残さないと空振り禁止 (常設規律 1) 側が担保できないためである。
7. **設計レビュー 1 回** (契約を触らないフェーズ。計画文書 §9 の 3)。
8. **U-1 / U-2 の依頼者裁定が §5 に逐語で記録されていること** (計画文書 §9 の 4)。

#### 結果 (2026-09-07、v1.3)

| 項 | 結果 | 根拠 |
|---|---|---|
| **1** root suite | **充足** | `2340 passed, 5 warnings in 349.31s (0:05:49)`、EXIT=0。**`xfailed` = 0 / `skipped` = 0 / `failed` = 0**。**逃げ枝は使われず、`operation_depth` は両面 `enforced` である** (§5 U-1 状態注記)。§11.1 |
| **2** CI | **充足** (監督追記: run 34047745958、3.11 / 3.12 とも `2340 passed`、floor step 緑、tally-consistency success) | **WP-1 マージ前の記録は §11.1 に逐語で残した** (main `f21d763` = WP-2/3/4/5 の run 34038494519 で 3.11 / 3.12 とも緑、**collection floor step が両 job で緑**、`tally-consistency` success)。**WP-1 入りの main `f4635ed` の run 34047745958 は監督が確認し §11.1 に追記した** (3.11 / 3.12 とも `2340 passed`、4 数一致) |
| **3** PERF 14 行 | **充足** | §11.2 に PERFRUN 行 + PERF **14 行** (4 plug × 3 op = 12 + MitateDB 2 plug × `cross_entity` = 2) を記録した |
| **4** `COLLECTION_FLOOR` | **充足** | **2274 → 2340** (ゲート時実測 `measured=2340 floor=2340 diff=0`)。§11.1 |
| **5** R-10 の記録 | **充足** | 3 複製とも sha256 `968d3c72…45e6` = 付録 A §A.0 と一致 (0 バイト不変)、常設スキャナの列挙 = companion anchor = **29 件**。§11.1 |
| **6** 常設規律 / 速度規律 | **充足** | 全 WP の対応表に対応の無い行は無い。**変異を持たない 4 項目 (L7-22 / smoke / backup-restore / 性能基準値) は §11.1 / §11.2 に逐語記録を置いた。** 受け入れ監査はいずれもその記録を逐語で報告に引いている (§11.3) |
| **7** 設計レビュー 1 回 | **充足** | 設計 v1.1 に 18 件を反映済み。**追加の設計レビューは行っていない。** 各 WP のコードレビューと受け入れ監査は別枠であり、回数の制限は掛からない |
| **8** 裁定の逐語記録 | **充足** | §5 U-1 / U-2 に逐語で記録済み (2026-09-06)。**再審議していない** |

---

## 10. 台帳 (本フェーズの起票項目)

- **L8-1 L7-22 は起票時点で既に充足していた (実態訂正)**。`security/CONTROL_MAPPING.md:33` の SI-00 行は「ledger item L4-13, still open」を、`conformance-tests/CONDITIONS.md:38` の C-09 行は「P4-D18 (L4-8, still open)」を**現行行に持っている** (2026-09-06 に現物で確認)。**フェーズ7 設計 §11 の L7-22 と第 14 次引き継ぎ §4-2 の「開いている」という記述が実態と食い違っていた。** 手当てはファイル変更ではなく、**両文書の状態注記の訂正**である (WP-6)。**L7-22 は閉じる。** **【状態注記 2026-09-07 (WP-6 完了)】閉じた。** 訂正はフェーズ7 設計 §11 の L7-22 と第 14 次引き継ぎ §4-2 の両方に入れた。監査照合の逐語は §11.1 にある。**ファイルは 1 バイトも変えていない** (実態は起票時点で充足していたため)。
- **L8-2 L7-19 は本フェーズでも撤去条件未達 (据え置きの理由)**。`constraints.txt:42` は `starlette==1.6.0` であり、`pip index versions starlette` の最新も **1.6.0** である (2026-09-06 実測)。**上流に `anyio.abc.BlockingPortal` 参照を直した版が存在しない**ので、「constraints の更新と同一コミットで ignore を外す」という撤去条件は満たせない。**こちら側の遅れではない。** 次に Starlette が上がったときに再評価する。**開いたまま据え置く。** **【状態注記 2026-09-07 (WP-4 完了)】据え置きのまま。** WP-4 は `constraints.txt` と 3 つの `filterwarnings` を 1 バイトも触っていない (監査が `git diff` で確認)。**撤去条件は依然として上流待ちである。**
- **L8-3 `operation_depth` の枝 (U-1 の結果を記録する)**。**U-1 が (A) の場合**: MitateDB の in-process 面に「要求 dict 全体」が存在しないため、**HTTP だけ `enforced`・in-process は `unavailable`** という `request_bytes` 同型の非対称が残る可能性がある。実装 WP の実測結果 (どちらの面で `enforced` になったか、xfail が何組残ったか) を §11.3 に記録し、残った組の理由を C-05 行に開示する。**U-1 が (B) の場合**: 「この peer の要求構造に有限の入れ子が無い」という判断の根拠 (`cell.py:1521-1533` のコメントと WP-4 の grep 実測) を本項に残し、**xfail 2 組をその状態の可視化として保持する**。**将来、MitateDB の要求形が入れ子を持つようになった時点で再評価する。** **【状態注記 2026-09-07 (WP-1 完了)】閉じた。非対称は生じなかった。** **`operation_depth` は in-process / HTTP の両面で `enforced`** であり、**xfail は 0 組**である。「in-process 面に要求 dict 全体が存在しない」という懸念は成立しなかった — **既定 `max_operation_depth=8` の下で 7 段ネストの json 値を持つ素の `session.insert()` が in-process でも `LIMIT_EXCEEDED(operation_depth)` になる** (in-process の `values` 自体が要求構造である、レビューの実測)。**残った組が無いので C-05 行への開示も無い。** 深さの数え方は両 peer で同じ要求構造 (entity → operations[] → op → values / filters) に対して定義されている。§3 D-1 訂正註 3、§11.3 WP-1a。
- **L8-4 R-10 (B) をフェーズ9 へ送る場合の記録 (U-2 の結果次第)**。U-2 が (A) で確定した場合、**(B) (29 値の "Since 1.x.0 (subordinate ruling N, …): " 接頭辞 / 挿入句を剥がして provenance を companion へ移す) はフェーズ9 (契約 1.7.0) の対象として送る**。**送った日付と理由 (18 件の PIN = 依頼者確定文言の再確定が要るため、版が上がるフェーズで扱えば再確定が 1 回で済む) を本項に残す** (R-14)。**あわせて、本フェーズ後も契約本体に経緯マーカーが残る件数 (29 値、付録 A §A.2c) を記録する** — (A) では JSON が動かないので、この件数は本フェーズ前後で変わらない。 **【状態注記 2026-09-07 (WP-3 / WP-6 完了)】(B) をフェーズ9 (契約 1.7.0) へ送った (送付日 2026-09-07)。** 理由は上記のとおり — **18 件の PIN = 依頼者確定文言の再確定が要るため、版が上がるフェーズで扱えば再確定が 1 回で済む**。**契約 JSON は本フェーズで 0 バイト動いていない** (3 複製とも sha256 `968d3c72…45e6`、§11.1)。**契約本体に残る経緯マーカー付きの値は 29 件のままである** (companion 前文に記録済み)。**計画文書 §5 / §8 の R-10 行は L8-8 の改版で「(B) はフェーズ9」を明示した。** 本項は**フェーズ9 の着手材料として開いたまま保持する。**
- **L8-5 HTTP plug の性能値は ASGI in-process の値である**。`tools/perf_baseline.py` が測る `r2db-api-http` / `MitateDB-api-http` の数値は、`httpx.ASGITransport` を通した**同一プロセス内**の値であり (`conformance_adapter_r2db_http.py:947`、`conformance_adapter_mitatedb_http.py:736`)、**実ネットワーク・reverse proxy・TLS・接続確立の費用を含まない**。**L7-2 (実 socket plug、フェーズ10) が入った時点で、実 socket 列が加わる**。§11.2 の表と `tools/` の README にこの注記を置く。**また、`backend_calls` は「往復」ではなく backend 呼び出し回数であり、DB プロセスを跨ぐのは PG を通る plug (§11.2 の 4-6 / 10-12 行) だけである** — in-memory / SQLite plug の値は同一プロセス内の呼び出し回数である。 **【状態注記 2026-09-07 (WP-5 / WP-6 完了)】記録した。開いたまま (L7-2 待ち)。** **本項が引く行番号「4-6 / 10-12 行」は起票時の表 (plug 順) に対するものであり、§11.2 の表はハーネスの出力順 (registry 順) へ差し替えたので、PG を通る plug は現行表の 8〜14 行に当たる。** **あわせて `backend_calls` の粒度差が in-process 2 plug 同士でも大きいことが実測で分かったので、新規に L8-11 として起票する。**
- **L8-6 `concurrency` の駆動は in-process の並行性に対するものであり、宣言値は拒否の閾値である**。D-2 の `hold_in_flight` が作るのは同一プロセス内の並行性であり、**実ソケット越しの concurrency (接続数の bound を含む) は射程外**である。L7-2 の後に再評価する。**あわせて 2 点を本項に記録する** (設計レビュー 1 回目、2026-09-06): (i) **MitateDB は `ApplicationCell._lock` (`cell.py:329`) により 1 cell あたり同時 1 操作である**ため、宣言する `concurrency` は**拒否の閾値**であって並列実行能力ではない (r2db 側に同じ直列化は無い — `postgres.py:328` は接続プールの短い critical section である)。(ii) **カウンタのスコープ (in-flight = 配備単位、rate 窓 = credential 単位) の両 peer 一致は共通 suite では観測できない** — C-05 の隔離 surface が張る application が 1 個だからである。担保は実装の形 (状態ホルダが 1 プロセス 1 個であること) と peer-local テストにある。 **【状態注記 2026-09-07 (WP-1 完了)】記録した。開いたまま (L7-2 待ち)。** 3 点とも `CONDITIONS.md` C-05 行と port docstring に開示済みである。**(i)(ii) は実装で確認した** — ホルダは合成根が 1 個だけ構築して全 `ApplicationCell` に注入する形になり、**変異「holder を `ApplicationCell.__init__` で構築する」→ `test_limit_holder_is_shared_across_applications_in_one_process` が赤**である。**`hold_in_flight` が作る並行性は 4 plug とも同一プロセス内である** (ASGITransport / 直接構築)。
- **L8-7 `CONDITIONS.md` C-05 行の L7-21 記述に誤記があった (訂正の記録)**。現行行は「the MitateDB exclusion for `request_bytes`/`query_complexity` is keyed on peer name」と書いているが、**実装上 peer 名で除外されていたのは `result_items` / `query_complexity` の 2 つ**であり (`test_c05_limit_declaration_agreement.py:473-474` / `:507-508`)、`request_bytes` の非該当は **MitateDB in-process の `unavailable` 宣言による自然な結果**である (`:432` の宣言判定)。**WP-1 で C-05 行を書き直す際に訂正し、訂正の事実は `CONDITIONS_HISTORY.md#c-05` へ逐語で残す。** **【状態注記 2026-09-07 (WP-1b 完了)】閉じた。** C-05 行の旧 known-gap 文は削除され、訂正の事実は `CONDITIONS_HISTORY.md#c-05` へ逐語で移した。**監査が HEAD の実装と照合して一致を確認した** (`:473-474` = `_drive_result_items`、`:507-508` = `_drive_query_complexity` が `startswith("r2db-api")` で早期 return しており、`_drive_request_bytes` には `adapter.name` 分岐が皆無であったこと)。**現行の C-05 行に peer 名固定の記述は残っていない** (穴自体が閉じたため)。
- **L8-8 計画文書 §5 / §8 の R-10 行を改版する (R-14 の適用)**。計画文書が置いた検査文「現行 JSON から経緯マーカーが消えたこと」は、**逐語インベントリ (付録 A、2026-09-06) が「値全体が経緯叙述の値は 0 件」「29 値すべてにマーカーと現行規範文が同居」「18 件は依頼者確定文言として PIN されている」ことを実測したため、規範文を書き換えずには満たせない**。**R-14 に従い、根拠 (付録 A) と日付を添えて、当該行を「provenance companion (契約 JSON 不変) + register テストによる網羅性の固定」へ改版する** (実施は WP-6)。**U-2 が (B) で確定した場合は本項は不要になる** — その場合は元の検査文がそのまま満たせるので、本項を「改版せず」と閉じる。 **同じ改版で計画文書 §5 / §7 / §8 の R-12 行の op 名も改める** — 「query / mutate / cross-entity」を「query / mutate / batch (+ cross_entity は `cross_entity_mutation` が `unavailable` でない plug のみ)」へ。根拠: r2db は `cross_entity_mutation: unavailable` であり、拒否経路の費用は性能基準値の対象ではない (監督裁定 2026-09-06、D-6)。 **【状態注記 2026-09-07 (WP-6 完了)】改版を実施した。閉じる。** 計画文書 `docs/design/ROADMAP_POST_PHASE7_V1.md` は **v1.2** になり、**§5 / §8 の R-10 行**は旧文を残したうえで「provenance companion (JSON 不変)。検査文『現行 JSON から経緯マーカーが消えたこと』は逐語インベントリ (設計 付録 A、2026-09-06) で 0 件が純粋経緯と判明したため不成立。(B) 接頭辞剥離はフェーズ9 1.7.0 へ」を根拠・日付付きで足した。**§5 / §7 / §8 の R-12 行**の op 名も同じ形で改版した。**R-14 に従い、行は 1 つも消していない。**
- **L8-9 `versioning.version_binding` の機械可読化 ((C)) をフェーズ9 へ送る**。**10,269 字の単一文字列**である `versioning.version_binding` を、版ごとの unconditional / conditional な義務の**配列**に組み替える案は、**R-8 (機械可読 artifact + 再生成一致テスト) と同じ問題**であり、**契約 1.7.0 (フェーズ9) の範囲**である。**本フェーズの両論 (§5 U-2) には入れず、本項で保持する。** `test_contract.py` が「N of those obligations are unconditional」の件数まで assert している (`test_contract.py:343-360`) ため、組み替えは**再生成一致テストと同時にしか行えない**ことを併記する。 **【状態注記 2026-09-07 (WP-6 完了)】フェーズ9 へ保持。開いたまま。** 本フェーズは `versioning.version_binding` を 1 バイトも動かしていない (契約 JSON 0 バイト不変)。**companion には当該 JSON パスの anchor が 1 件あり、値全文 (10,269 字) の逐語複製と 従属判断 7 / 8 / 9 / 10 / 11 への参照、導入版 `contract 1.2.0 through 1.6.0 (cumulative)` を持つ** (WP-3、監査が byte 一致を確認)。

**以下は本フェーズの実施中に新規起票した項目である (2026-09-07)。**

- **L8-10 MitateDB の `_measure_request_bytes` は r2db の `check_request` と 2 点で異なる (peer 差の記録)**。**(i) 循環検出が祖先パス限定である** (r2db は走査済み全体を持つ)、**(ii) 未知型を `+8` として受ける** (r2db は `VALIDATION_FAILED` を上げる)。**契約上の意味 (`request_bytes` の片側検査 = 宣言を確実に超える構成が決定的に拒否されること) には影響しない**ので本フェーズでは手当てしないが、**同型性 (P-6) の差として記録する**。**将来 `request_bytes` を両側化する、あるいは構造推定の値そのものを契約が語るようになった時点で再評価する。** **開いたまま (記録)。**
- **L8-11 `backend_calls` の粒度は 4 plug で揃わない (指標の限界)**。ラップ点は **PG を通る 2 plug = cursor 実行回数**、**r2db in-process = `ApplicationCell` の公開 4 メソッド (常に 1.00)**、**MitateDB in-process = `SQLiteBackend` の公開 20 メソッド (11〜37)** である。**したがって `backend_calls` は plug 間で比較してはならない指標であり、比較の意味を持つのは同一 plug の版間の差分だけである。** §11.2 の注記と `tools/PERF_BASELINE_README.md` に明記した。**手当ての候補は「4 plug で同じ意味を持つ点 (例: 実 SQL 実行) までラップを潜らせる」ことだが、in-memory plug には SQL の概念自体が無いので、共通の意味を作れるかどうかから検討が要る。** **開いたまま (記録)。**
- **L8-12 隔離 profile の bound は、駆動レシピだけでなく「他の条件が隔離面を使う」ことを許す値にする**。**R-A (2026-09-06) の教訓である** — 隔離 profile の `operation_depth` を駆動レシピに合わせて 4 に置いたところ、**隔離面で `where` 付き mutation が全て拒否され、MitateDB の唯一の破壊的操作である `delete` を使う C-04 が MitateDB-http で赤になった**。**bound を選ぶときは「この bound の下で、隔離面を使う (あるいは将来使う) 他の条件の要求構造が通るか」を確認する。** 現行値は 4 plug とも `operation_depth=5`、`concurrency=3`、`requests_per_minute=50`、`execution_ms=5000` である。**開いたまま (規律)。**
- **L8-13 隔離 profile の `operation_depth` の下で `expected_revision` / `unique_key` 付き mutation は深さを 1 段消費する (記録)**。`operation_depth=4` の下では `LIMIT_EXCEEDED(operation_depth)` になることを WP-1a が実測した (両 peer とも同じ要求構造)。**R-A で 5 に上げたことで現行は通る**が、**将来この profile 値を下げるときは `expected_revision` / `unique_key` / `where` を使う条件 (C-12 / C-17 / C-18 など) が隔離面を使っていないかを先に確認する。** L8-12 の具体例である。**開いたまま (記録)。**
- **L8-14 代理指標の禁止 (教訓、監督裁定 2026-09-06)**。`conformance-tests/test_c04_unsupported_and_safe_errors.py` の `_operation_depth_enforced()` は、**「`operation_depth` が `enforced` である」ことを「r2db 同等の `drop_entity` 対応 peer である」ことの代理指標**として使っていた — 起票時点では両者が偶然一致していた (r2db のみ) ためである。**本フェーズで MitateDB も `operation_depth: enforced` になった瞬間にこの代理は壊れ、2 件が赤になった。** **是正は `_peer_declares_drop_entity_supported()` — 宣言された能力 (`capabilities.schema_operations.unsupported` に `drop_entity` が無いこと) を直接読む形である** (`unsupported` キー自体が無ければ assert で明示的に落とす。空データを黙って許さない)。**規律**: **分岐の条件は、その分岐が実際に依存している性質そのものを読む。** 別の性質で代用すると、代用元が動いた瞬間に静かに壊れる (この場合は赤になったので気付けたが、逆向き = 静かに緑になる形もあり得る)。**閉じた (教訓として保持)。**
- **L8-15 port の新フィールドが「配線されているだけ」で load-bearing でない形があり得る (教訓)**。`result_items` の初稿レシピ (表に N / N+1 行を用意して返してもらう形) では、**r2db の実検査が `min(len(rows), page_size)` で実行数側から位置を決めるため、adapter が port の `limit` を完全に捨てても suite が全緑だった** (監査の自作変異 B / B2)。**「4 plug すべてで両側で駆動されている」ことと「4 plug すべてで新フィールドが load-bearing である」ことは別の命題である。** 是正後のレシピ (表に bound+1 行を 1 度だけ入れ、`limit=bound` / `limit=bound+1` で分ける) は後者も満たす。**規律**: **port に optional フィールドを足したら、そのフィールドを adapter が捨てる変異が赤になることまでを実測する。** **閉じた (教訓として保持)。**
- **L8-16 作業指示書の誤記 2 件 (記録)**。**(a)** §2 WP-2 のテストコマンド 3 本目 `conformance-tests/test_c00_contract_discovery.py` は**実在しない** (実在は `test_c00_application_escape.py`)。**しかもファイル名を直しても目的を果たさない** — L7-23 のガードは「観測 0 件」だけを閉じる設計であり、1 件でも収集される部分実行 (register + 1 ファイル) には効かないためである (実測: `1 failed, 17 passed`)。**設計どおりであり、実装の逸脱ではない。** **(b)** §2 WP-1b の逐語表が MitateDB の `hold_in_flight` のラップ対象を「`ApplicationCell` の操作メソッド入口」としているが、**その形では `_limit_gate` を実行する前 (カウンタ増分前) に止まり停止点要件を満たさない**。**実装は `_limit_gate` 自体のラップであり、監督が追認した。** **両件とも作業指示書 §5 の訂正註に置いた。閉じた。**

---

## 11. 実施記録

**本節は 2026-09-07 (WP-6) に記入した。**

### 11.1 集計行

**取得条件 (全項共通)**: worktree `.claude/worktrees/phase8` = branch `phase8-effective-bounds` **`3c85e96`** (main への merge は **`f4635ed`**)。**監督が単独で実行し、`ps` で他の pytest が 0 件であることを確認してから取った。** ローカル PostgreSQL の `max_connections = 300`、`statement_timeout = 0`。**`pg_database` の件数は前後とも 21 → 21 で残留は無い。**

| 項目 | 値 | 取得条件 |
|---|---|---|
| **完了ゲート (root suite 単独実行)** | **`2340 passed, 5 warnings in 349.31s (0:05:49)`** / **EXIT=0**。**failed 0 / xfailed 0 / skipped 0**。日付 2026-09-07、branch head `3c85e96` | `./.venv/bin/python -m pytest -q -n 5 --dist loadgroup`、監督単独実行。**`5 warnings` は共有 `.venv` に `httpx2` を入れていないことによる `StarletteDeprecationWarning` (第 14 次 §4-3 記載) であり、CI 側は `httpx2` が入るので 0 である。warnings の数は一致判定に用いない** |
| **CI 3.11 job の集計行** | **【監督追記 2026-09-07】run 34047745958 (main `f4635ed` = WP-1 入り): 3.11 (正本) `2340 passed in 433.13s (0:07:13)`、3.12 `2340 passed in 456.24s (0:07:36)`、両 job `COLLECTION_FLOOR check OK: measured=2340 floor=2274 diff=66`、`tally-consistency` / scanner / deploy-assets-lint すべて success。failed 0 / xfailed 0 / skipped 0 — ローカル root suite `2340 passed` と 4 数一致 (L7-6 の突合済み)。** 旧記述: **WP-1 入りの main `f4635ed` に対する run は本書執筆時点で未確認である。** 参考として WP-1 マージ前の 2 run を逐語で残す: **run 34038494519** (main `f21d763` = WP-2/3/4/5) 3.11 `2312 passed, 9 xfailed in 464.96s (0:07:44)`、3.12 `2312 passed, 9 xfailed in 443.99s (0:07:23)`、両 job `COLLECTION_FLOOR check OK: measured=2321 floor=2274 diff=47`、**全 job success** (`tally-consistency` を含む)。**run 34034469614** (main `56ff04c` = WP-2/3) 3.11 `2272 passed, 9 xfailed in 427.86s (0:07:07)`、3.12 `2272 passed, 9 xfailed in 369.68s (0:06:09)`、floor step OK (measured 2281 / floor 2274)、`tally-consistency` success。**この 2 run の `9 xfailed` は WP-1 が未マージだったためであり、WP-1 マージ後は 0 になる** (完了ゲートの実測) | run id、`tally-consistency` の結果、両 job の floor step ログ行。**main の run は docs-only push のたびに `concurrency` の cancel-in-progress で消えるので、ゲートは最終 push の run で読む** |
| **`--collect-only -q` の件数 (ゲート時)** | **2340**。逐語: `collected=2340` / `COLLECTION_FLOOR check OK: measured=2340 floor=2340 diff=0` / `EXIT=0` | `COLLECTION_FLOOR` を **2274 → 2340** へ更新した後の値。**以後この件数を下回れば、明示の更新コミットが無いかぎり CI が赤になる** |
| **C-05 V3 の `xfailed` 件数と内訳** | **0**。内訳は無い (残った組が無い) | U-1 裁定 (A)。**逃げ枝 (in-process 1 組を `unavailable` で残す) は条件不成立であり使われなかった** (§5 U-1 状態注記、§3 D-1 訂正註 3)。`_V3_KNOWN_UNAVAILABLE = frozenset()`。**V3 の parametrize 基底は固定 9 class × 4 plug = 36 ケースのまま変わらない** |
| **R-10 の記録** | **契約 JSON と両 peer の packaged 複製 2 本の sha256 = `968d3c72415d4536c0393ce451497324c182cbc2ae9d9213e0ec6ed4444f45e6` (3 本一致)** — 付録 A §A.0 の値と一致する = **契約 JSON は 0 バイト不変**である。**常設スキャナが列挙した JSON パス件数 = companion の anchor 件数 = 29 (過不足なし)** | U-2 = (A)。対象は `spec/data-service-api.v1.json` / `MitateDB-api/src/mitatedb_api/contract/data-service-api.v1.json` / `r2db-api/src/r2db_api/contract/data-service-api.v1.json`。**WP-3 の着手時・変異の復元後・完了時のいずれでも同一であり、監査も独立に 3 回照合した** |
| **argv secret 静的規則の出力** | **修正前 = 6 件 / 修正後 = 0 件** (下記に逐語) | 常設規律 5、§3 D-5。**両方を残す** (規則が現に何かを捕まえていたことと、修正がそれを消したことの両方を示すため) |
| **backup / restore 実証** | **PART A (platform DB) / PART B (application DB) とも exit 0**、**復元前後で catalog と 1 query の結果が完全一致** (下記に逐語) | §9 の 6 (変異を持たない完了条件)。**実行コマンドを逐語で残す。dump パスは作業機の絶対パスを含むので `<DUMP_PATH>` へ置換した** |
| **L7-22 の監査照合記録** | **`security/CONTROL_MAPPING.md:33`** (SI-00 行) に逐語 **「a separate, still-open asymmetry (ledger item L4-13, still open)」**、**`conformance-tests/CONDITIONS.md:38`** (C-09 行) に逐語 **「Supervisor ruling P4-D18 (L4-8, still open) DEFERS rebuilding V4」**。**どちらも現行行に在る。両ファイルは本フェーズで 1 バイトも変えていない** | §9 の 6。**L4-13 / L4-8 が現行行として在ることを、実装担当と受け入れ監査が別々に読んで確認した** (§10 L8-1) |

**argv secret 静的規則の逐語 (走査対象 = `r2db-api/deploy/scripts/` 配下の全ファイルと両 peer の `ops.py`)**

修正前:

```
r2db-api/deploy/scripts/part1_provision_host_and_db.sh:270: -v control_password="${R2DBSVC_CONTROL_PASSWORD}" \
r2db-api/deploy/scripts/part1_provision_host_and_db.sh:279: -v api_password="${R2DBSVC_API_PASSWORD}" \
r2db-api/deploy/scripts/part1_provision_host_and_db.sh:284: -v controlplane_password="${R2DBSVC_CONTROLPLANE_PASSWORD}" \
r2db-api/deploy/scripts/part1_provision_host_and_db.sh:289: -v auditreader_password="${R2DBSVC_AUDITREADER_PASSWORD}" \
r2db-api/deploy/scripts/part1_provision_host_and_db.sh:334: -v runtime_password="${R2DB_APP_RUNTIME_PASSWORD}" \
r2db-api/deploy/scripts/part1_provision_host_and_db.sh:335: -v developer_password="${R2DB_APP_DEVELOPER_PASSWORD}" \
files scanned: 7 hits: 6
```

修正後:

```
files scanned: 7 hits: 0
```

**この 2 つの出力は `{scratchpad}/argv_scan_before.txt` / `argv_scan_after.txt` に残した** (受け入れ監査が両ファイルを独立に照合した)。**常設テストは `conformance-tests/test_deploy_secret_argv_scan.py` であり、`4 passed` である。**

**backup / restore 実証の逐語 (r2db-api、ローカル PostgreSQL 16.14。作成した DB / role は実証後にすべて削除し、`p8wp4%` 検索で 0 件を確認した)**

- **PART A (platform DB)**: `pg_dump --format=custom` → `<DUMP_PATH>` → `createdb <NEW_DB> OWNER <OWNER_ROLE>` → `pg_restore` → **`ops verify-declarations`** を**復元先を指す writer role の DSN** で実行 → **exit 0** (宣言一致)。
- **PART B (application DB)**: 同一手順で復元し、**`PostgresCell.catalog()` と実データ行を復元前後で比較して完全一致**を確認 → 復元済み DB を裏に持つ ASGI app を uvicorn で起動 → **`tools/deploy_smoke.py` を実行して exit 0**。
- **smoke の逐語出力** (実ソケット、両 peer で同型に成功):

```
stage1 capabilities  200 contract_version=1.6.0
stage2 catalog       200 entities=1
stage3 query         200 rows=1
                                            -> exit 0
```

- **失敗経路も実測した**: 空 catalog で `--allow-empty-catalog` 無し → **exit 4** (`stage3 skipped: empty catalog` を stderr へ)、`--allow-empty-catalog` あり → **exit 0**、段 3 が 500 を返す fake サーバ → **exit 3**、接続不能 → **exit 2**、env 未設定 → **exit 1**。
- **`ops verify-declarations` の role 依存も実測した**: **writer (api) role の DSN → 6 OK 行 + 対象外 1 行、exit 0**。**同じ platform を owner (control) role の DSN で実行 → F-13 で exit 11** (対象外行は FAIL 経路でも出る)。**この運用要件は `docs/ops/BACKUP_RESTORE_R2DB.md` の手順 4 に明記した** (§3 D-5 訂正註 5)。
- **監査が独立に起こした F-8 (空 DB の DSN) の出力** (両 peer とも FAIL 経路で対象外行が末尾に出ること、形式が同型で差が peer 名のみであることの確認):

```
FAIL F-8  relation <PEER>_registry.platform_declarations does not exist: ...
--   F-1/F-2/F-12  out of scope for this command: ...  -> exit 8
```

### 11.2 性能基準値 (R-12)

**実行環境行 (逐語)**:

```
PERFRUN host=Darwin/arm64 python=3.11.15 commit=3c85e96-dirty date=2026-09-07
```

**実行コマンド (逐語)**: `./.venv/bin/python tools/perf_baseline.py --warmup 20 --n 200` / **EXIT=0**。**監督が完了ゲート (root suite 終了後) に単独で実行した。他の pytest は 0 件、`pg_database` は前後とも 21 → 21 で残留無し。**

**`commit=3c85e96-dirty` の `-dirty` は `conformance-tests/COLLECTION_FLOOR` の未コミット更新 (2274 → 2340) だけによるものである** — ゲート作業の順序上、floor の更新コミットは PERF 取得の後に置いた。`3c85e96` は本フェーズの branch head であり、main への merge は `f4635ed` である。

**行順はハーネスの出力順 (`conformance-tests/registry.json` の順 = r2db in-process → MitateDB in-process → r2db-http → MitateDB-http) に合わせて転記した** — 起票時の表 (plug 順) とは順序が異なる。転記時の取り違えを避けるためである。

| # | peer | plug | transport | op | n | p50_ms | p95_ms | backend_calls |
|---|---|---|---|---|---|---|---|---|
| 1 | r2db-api | `r2db-api` | in-process | query | 200 | 0.042 | 0.045 | 1.00 |
| 2 | r2db-api | `r2db-api` | in-process | mutate | 200 | 0.147 | 0.221 | 1.00 |
| 3 | r2db-api | `r2db-api` | in-process | batch | 200 | 0.746 | 1.109 | 1.00 |
| 4 | MitateDB-api | `MitateDB-api` | in-process | query | 200 | 0.037 | 0.040 | 11.00 |
| 5 | MitateDB-api | `MitateDB-api` | in-process | mutate | 200 | 0.022 | 0.024 | 7.00 |
| 6 | MitateDB-api | `MitateDB-api` | in-process | batch | 200 | 0.073 | 0.080 | 37.00 |
| 7 | MitateDB-api | `MitateDB-api` | in-process | cross_entity | 200 | 0.039 | 0.043 | 16.00 |
| 8 | r2db-api | `r2db-api-http` | asgi-inprocess | query | 200 | 4.840 | 5.347 | 14.00 |
| 9 | r2db-api | `r2db-api-http` | asgi-inprocess | mutate | 200 | 4.771 | 5.186 | 14.00 |
| 10 | r2db-api | `r2db-api-http` | asgi-inprocess | batch | 200 | 4.250 | 5.262 | 18.00 |
| 11 | MitateDB-api | `MitateDB-api-http` | asgi-inprocess | query | 200 | 4.750 | 6.469 | 13.00 |
| 12 | MitateDB-api | `MitateDB-api-http` | asgi-inprocess | mutate | 200 | 4.499 | 6.101 | 9.00 |
| 13 | MitateDB-api | `MitateDB-api-http` | asgi-inprocess | batch | 200 | 4.263 | 6.095 | 29.00 |
| 14 | MitateDB-api | `MitateDB-api-http` | asgi-inprocess | cross_entity | 200 | 4.594 | 6.212 | 14.01 |

**注記**:

- **`op=batch` は単一 entity の atomic mutation batch (`attempt_batch_with_addresses`、操作数 5)** である。**両 peer で比較可能な複数操作単位であるため 3 列目に採った** (監督裁定 2026-09-06)。操作数を既定から変えた場合はここに書く。
- **`op=cross_entity` は MitateDB 2 plug のみである** (7 / 14 行)。**`r2db-api` は `cross_entity_mutation: unavailable` を宣言しており、拒否の費用は性能の対象外なので測らない。** したがって r2db と MitateDB の比較は残る 12 行で行い、7 / 14 行は MitateDB 内部の参照値である。**`cross_entity` の操作数は 2 entity × 1 insert である** (§3 D-6 訂正註 2)。
- HTTP plug の値は **ASGI in-process** の値であり、実ネットワーク・reverse proxy・TLS を含まない (L8-5)。**L7-2 (実 socket plug、フェーズ10) が入った時点で実 socket 列が加わる。**
- **`backend_calls` は backend 呼び出し回数であり、DB プロセスへの往復ではない。しかも 4 plug で粒度が揃わないので、plug 間で比較してはならない** (L8-11、§3 D-6 訂正註 3): **PG を通る 2 plug (8〜14 行) = cursor 実行回数**、**r2db in-process (1〜3 行) = `ApplicationCell` の公開 4 メソッドなので常に 1.00**、**MitateDB in-process (4〜7 行) = `SQLiteBackend` の公開 20 メソッドを数えるので 11〜37** である。**比較の意味を持つのは同一 plug の版間の差分だけである。**
- **`--warmup` の値は PERF 行から復元できない** — `n=` は集計標本数である。**したがって上の「実行コマンド (逐語)」が warmup と n の記録であり、以後の基準値は同じ `--warmup` / `--n` で取る** (op 順で同一 entity の状態が育つので、`--n` が異なる実行同士は比較できない)。
- **計測窓には `BatchOperation` / `ScopedBatchOperation` の生成が残っている** (§3 D-6 訂正註 7)。実測の窓内コストは **batch 0.00252 ms/回 (in-process p50 の 2.4〜4.7%)、cross_entity 0.00109 ms (3.6%)、mutate 0.00004 ms (≒0%)** である。**p50 / p95 は線形補間であり、port と ASGI の変換コストを含む。**
- **閾値は無い** (P-8)。**退行の扱いは計画文書 §7 の 3 のとおり、本基準値が 2 フェーズ安定した後にゲート化を審議する** — **本表がその起点である。**
- **異常時の traceback には作業機の絶対パスが出るので本節には貼らない** (公開規律)。

### 11.3 WP ごとの記録

- **WP-1a** (L7-1 = MitateDB application plane の 4 class + `request_bytes` 副項目 + V3 撤去 + `test_c05:646-659` 撤去)
  - **触ったファイル**: `MitateDB-api/src/mitatedb_api/` の `config.py` / `cell.py` / `http.py` / `backend_postgres.py` / `backend_sqlite.py` / `main.py` / `service.py`、`MitateDB-api/tests/test_application_plane_limits.py` (新設) と `test_limit_class_vocabulary.py` / `test_postgres.py`、`MitateDB-api/conformance/` の 2 adapter (隔離 profile と限度状態ホルダの配線)、`conformance-tests/test_c05_limit_declaration_agreement.py` (V1 統制の撤去・`_V3_KNOWN_UNAVAILABLE` の削減・`already_consumed` 式)、`conformance-tests/test_c04_unsupported_and_safe_errors.py` (代理指標の是正、下記「設計外の発見」)。
  - **集計行 (最終)**: `MitateDB-api/tests` → **768 passed**、`conformance-tests/test_c05_limit_declaration_agreement.py` → **58 passed** (旧 49 passed / 9 xfailed)、`conformance-tests` 全体 (`-n 5 --dist loadgroup`) → **`1 failed, 583 passed in 71.52s (0:01:11)`** (この 1 failed が下記「設計外の発見」であり、WP-1b で解消した)、`tools/public_value_scan.py` → `# mode=tree files_scanned=267 total_flagged=0`。
  - **変異**: 初回 **11 件** + 差し戻し 1 で **3 件** + 差し戻し 3 で **1 件**。**差し戻し 3 回** (レビュー 1 回 8 件 → 差し戻し 1、追加裁定 → 差し戻し 3)。
  - **記録が要る実測項目 (設計 §11.3 の (i)〜(v))**:
    - **(i) `already_consumed` の再測定**: MitateDB in-process = **0**、MitateDB HTTP = **1**、r2db in-process = **0**、r2db HTTP = **1**。**式は `1 if "http" in adapter.name else 0` に統一した** (transport 固有・peer 非依存)。初稿が入れた peer 名固定 (`adapter.name == "r2db-api (http+postgres)"`) は撤去した。MitateDB HTTP が 1 になるのは、監督裁定で `capabilities()` を gate 対象にしたためである。
    - **(ii) `result_items` 両側化の位置一致**: **4 plug とも `bound=5`、5 成功 / 6 拒否で一致した** (r2db = `min(len(rows), page_size)`、MitateDB = 要求 `limit` 値そのもの)。**実装は WP-1b。**
    - **(iii) C-05 Status セルの文字数**: **2,960 字** (上限 3,000)。推移は 2,524 → 2,926 → 2,886 → **2,960**。**実装は WP-1b。**
    - **(iv) `operation_depth` の面**: **in-process / HTTP の両面で `enforced`**。**残った xfail 組は 0 である。** 逃げ枝は条件不成立 (§5 U-1 状態注記)。
    - **(v) V1 (d) の命題の保持**: `test_c05:646-659` 相当を削除し説明コメントに置換した後、**「`unavailable` かつ `limits` に値を持つ class」は実測で 0 件**である。**命題そのものは同テスト前半 (`_assert_v1_self_consistency` を全 plug に対して実際に呼ぶ部分) が保持している** — 失われたのは非空振りの担保だけであり、その事実は C-05 行に開示した。
  - **設計外の発見 (監督裁定で是正)**: **`test_c04_unsupported_and_safe_errors.py` の `_operation_depth_enforced()` が代理指標だった** — 「`operation_depth` が `enforced`」を「`drop_entity` 対応 peer」の代用にしており、MitateDB も `enforced` になった瞬間に 2 件が赤になった。**是正は宣言された能力 (`capabilities.schema_operations.unsupported` に `drop_entity` が無いこと) を直接読む `_peer_declares_drop_entity_supported()` である** (`unsupported` キー自体が無ければ assert で落とす)。**観測件数は True 側 2 plug / False 側 2 plug で空振り無し、判定を反転する変異は 4 plug すべてで赤 (`4 failed, 4 passed`)。台帳 L8-14。** **同じ是正の副産物として、隔離 profile `operation_depth=4` の下では MitateDB-http の `delete` probe (深さ 5) が拒否されることが判明し、R-A (depth 4 → 5) につながった。**
  - **もう 1 件の設計外の発見**: **MitateDB in-process adapter の `insert` 分岐が `where` を握り潰していた** — V2 の `operation_depth` レシピが in-process で成立しない原因である。**`expected_revision` / `unique_key` と同じく `transact()` へ回す形に直した** (adapter の変更であり port の意味は不変)。

- **WP-1b** (port v1.12 = `hold_in_flight` + 要求側 optional フィールド + `_drive_concurrency` + `result_items` 両側化 + L7-21 + `CONFORMANCE_ADAPTER_V1.md` §22 + C-05 行)
  - **触ったファイル**: `conformance-tests/adapter.py` (port v1.12)、4 adapter、`conformance-tests/test_c05_limit_declaration_agreement.py`、`conformance-tests/CONDITIONS.md` (C-05 行のみ)、`conformance-tests/CONDITIONS_HISTORY.md` (`#c-05` へ L8-7 の訂正を逐語)、`docs/design/CONFORMANCE_ADAPTER_V1.md` (§22 新設、版数 1.11 → 1.12)、`conformance-tests/test_c12_capability_agreement.py` (差し戻し 2 の裁定 1 で新設した 1 本)。
  - **集計行 (最終)**: `conformance-tests/test_c05_limit_declaration_agreement.py` → **`61 passed in 6.36s`**、`conformance-tests` 全体 (`-n 5 --dist loadgroup`) → **`591 passed in 74.59s (0:01:14)`** (failed 0 / xfailed 0)、`MitateDB-api/tests` → **768 passed**、`r2db-api/tests` → **934 passed, 1 warning**、`tools/public_value_scan.py` → `# mode=tree files_scanned=267 total_flagged=0`。
  - **変異**: 初回 **11 件** (完了条件 10 件 + R-A 1 件) + 差し戻し 2 で **1 件** + 差し戻し 3 で **1 件**。**差し戻し 2 回** (レビュー 2 回目 6 件 → 差し戻し 2、受け入れ監査 → 差し戻し 3)。
  - **4 plug の停止点 (実測、file:line)**: **r2db 2 plug** = `service.py:1139` の `_active += 1` の後、`service.py:1095` の cell dispatch (`catalog`) をラップ。**MitateDB 2 plug** = `_limit_gate` 自体をラップし、`cell.py:536-537` の counter 増分を実行した後、`cell.py:329` の `_lock` を取る前に停止する (`_StalledGateContextManager`)。**待ち上限は 4 helper とも 30.0 秒で、超過は理由文付きの `AssertionError` である。**
  - **監査が独立に取った変異と、その帰結**: **`limit` が r2db 2 plug で load-bearing でなかった** (変異 B / B2 が赤にならない)。**監督裁定 (差し戻し 3 の 4) でレシピを改め、`limit` が 4 plug すべてで load-bearing になった** (改修後の変異「r2db in-process の `limit` を無視」→ C-05 V2 [r2db-api] が赤、`1 failed, 60 passed`)。**台帳 L8-15。**
  - **監査の未充足 3 件とその処置**: **(A) `hold_in_flight` の意味 1 文が port docstring に逐語で入っていなかった** (言い換えがあった) → **差し戻し 3 の 1 で確定文ファイルから逐語複製し、逐語一致を assert する文字列ピンのテストを新設した** (常設規律 4)。**(B) C-05 行に「V3 の xfail が 0 件」の記載が無かった** → **差し戻し 3 の 2 で 1 文追加** (セル長 2,886 → 2,960)。**(C) 実測と食い違うコメント 2 箇所** (`test_c05:777-779` / `:673` 付近が `operation_depth` を「in-process では `unavailable`」と書いたまま) と r2db helper docstring の停止点行番号 → **差し戻し 3 の 3 で訂正。** **3 件とも是正済みである。**
  - **監査の残余 (処置済み・記録)**: **(E) `_drive_concurrency` の非空振り assert がトートロジーだった** → **差し戻し 3 の 5 で、`hold_in_flight` が yield する実測保持本数に対して取る形に改めた。** **L7-21 (i) のテキスト走査を (ii) と同じ AST 走査に統一した。**
  - **設計への疑義 (報告どおり記録)**: `query_complexity` の片側検査は安全側 / 拒否側を `bound-1` / `bound+1` に締め直した。**MitateDB 自身の宣言偽装は metric に r2db 型の "+1 tax" が無いため検出できず、変異は r2db 側で実証した** (作業指示書の「いずれかの plug」を満たす)。**この非対称は C-05 行に開示済みの事実と同根である。**
  - **報告の事実誤認 1 件 (訂正済み)**: 「`update` + `filters` を `transact` 経路へ回す変更の影響は grep で確認して 0 箇所」という報告は誤りだった — **単一行 regex が複数行の呼び出し (本リポジトリの主流の書式) を検出できていなかった**。**AST 全数走査による実測は 4 ファイル 12 箇所である** (`test_c05:371,379` / `test_c12:95` / `test_c17:283` / `test_c18:81,124,145,190,209,294,326,337`)。**「他の呼び出し箇所への影響ゼロ」という結論自体は変わらないが、根拠の手順が誤っていたので訂正した** (差し戻し 2 の裁定 2)。

- **WP-2** (R-9 + L7-23 + L7-22 注記)
  - **触ったファイル**: `conformance-tests/COLLECTION_FLOOR` (新設、1 行 `2274`)、`tools/check_collection_floor.py` (新設、標準ライブラリのみ)、`.github/workflows/ci.yml` (+3 行、pip install の後・pytest の前に 1 step)、`conformance-tests/test_conditions_register.py` (収集 0 件ガード)、`conformance-tests/README.md` (運用規約の節)。**`security/CONTROL_MAPPING.md` と `conformance-tests/CONDITIONS.md` は 1 バイトも触っていない** (L7-22 は実態充足のため注記のみ)。
  - **集計行**: floor 検査 → `COLLECTION_FLOOR check OK: measured=2274 floor=2274 diff=0` / EXIT=0。register ファイル単独 → **`3 failed, 7 passed`** (ガード由来の fail-loud、設計どおり)。`conformance-tests` 全体 (`-n 5 --dist loadgroup`) → **`575 passed, 9 xfailed in 72.41s (0:01:12)`** / EXIT=0。`tools/public_value_scan.py` → `# mode=tree files_scanned=267 total_flagged=0`。
  - **変異**: 実装 **3 件** + 差し戻し **4 件の異常系** + 監査の自作 **4 件 (A / B / D / E)**。**差し戻し 1 回** (レビュー 7 件)。
  - **記録が要る実測項目 (設計 §11.3 の指定)**: **L7-23 のガード (`assert ids`) は完了ゲート形式 (`-n 5 --dist loadgroup`) で緑である。** 監査が計測プラグイン (scratchpad、リポジトリ無改変) で観測件数を独立に取った — **conformance 全体で `AUDIT_MARKED_IDS n=20 items=584`、register 単独で `n=0 items=10`**。**xdist の各 worker が session 全体を収集するという前提は実測で成立している。**
  - **監査の指摘とその処置**: **収集エラーが「緑」として報告される穴** (レビュー R-1) → **`returncode != 0` / summary 行の `error` を見る枝を足した** (差し戻し)。監査の自作変異 B (`collect_ignore_glob` で 238 件を静かに落とす、終了コード 0・エラー無し) が **`measured=2036 floor=2274 diff=-238` / EXIT=1** で捕まったことが、この機構が本来守るべき形 (静かな証拠消失) に効くことの実証である。
  - **監査の未充足とその処置**: **(1) 設計 §11.3 の WP-2 行が「(未記入)」だった** → **本項で記入した** (記録の帰属は WP-6 である)。**(2) CI run id と両 job の floor step ログ行が未取得だった** (未 push のため原理的に不可) → **§11.1 に main `56ff04c` / `f21d763` の 2 run を逐語で記録した。** **(3) 完了ゲート形式の実測が root suite ではなく `conformance-tests` 限定だった** → **監督の完了ゲート (root suite `2340 passed`) で解消した。** **(4) `public_value_scan.py` が未追跡の新設 2 ファイルを走査していなかった** → **明示引数での走査で `total_flagged=0` を確認した** (§3 D-3 訂正註 4)。
  - **作業指示書の誤記 (訂正註へ)**: テストコマンド 3 本目 `test_c00_contract_discovery.py` は実在しない (実在は `test_c00_application_escape.py`)。**ファイル名を直しても目的を果たさない** — 実測 `1 failed, 17 passed`。**ガードは「観測 0 件」だけを閉じる設計であり、部分実行では救えない** (D-3 どおり、実装の逸脱ではない)。**台帳 L8-16 (a)。**
  - **費用開示の訂正**: `--collect-only` の provisioning 倍化は実測と合わなかった (`pg_database` / `pg_roles` の差分 0)。**`README.md` は訂正後の文言 (接続検証のみ) で書かれている** (§3 D-3 訂正註 1)。

- **WP-3** (R-10 (A) = provenance companion、契約 JSON 0 バイト不変)
  - **触ったファイル**: **3 つのみ** — `spec/CONTRACT_HISTORY.md` (新設、**29 見出し**)、`conformance-tests/test_contract_history_register.py` (新設、**7 テスト**、`@pytest.mark.condition` 無し)、`spec/README.md` (到達経路 1 段落)。**契約 JSON・packaged 複製 2 本・`conformance-tests/test_contract.py`・`CONDITIONS.md` は無変更である** (`git diff` で 0 行を確認)。
  - **集計行 (最終)**: `test_contract_history_register.py` + `test_contract.py` + 両 peer の `tests/test_http.py` → **`128 passed in 4.75s`**。register ファイル単独 → **7 passed** (初稿 5 + 差し戻しの 2)。`tools/public_value_scan.py` → `# mode=tree files_scanned=267 total_flagged=0`。
  - **契約 JSON の sha256**: 3 複製とも **`968d3c72415d4536c0393ce451497324c182cbc2ae9d9213e0ec6ed4444f45e6`** (着手時・変異の復元後・完了時・監査の 3 回照合とも同一)。
  - **スキャナ列挙件数 = companion anchor 件数 = 29 (過不足なし)。** 付録 A §A.2c の 29 と一致する。
  - **変異**: 実装 **6 件** + 差し戻しで **2 件** + 監査の自作 **2 件 (MUT-X / MUT-Y)**。**差し戻し 1 回** (レビュー 6 件)。
  - **監査の判定**: **未充足・証拠不足は無し** (完了条件 10 項目 + 差し戻し裁定 1〜4 のすべてで監査が独立に証拠を取った)。
  - **監査が実測した機械検査の限界 (開示、設計どおり)**: **MUT-X** (`Since` を持たない節の導入版を `9.9.9` へ) → **緑のまま** = 29 節中 12 節の導入版は機械検査の外である。**MUT-Y** (`従属判断 6` → 実在するが誤った `従属判断 11`) → **緑のまま** = ruling 帰属の正しさは無検査で在否のみを見る。**どちらも設計 D-4 が明言した範囲であり、だからこそ完了条件 8 の人手突合が要る。**
  - **人手の突合 (完了条件 8)**: **全 29 anchor について引用が契約値と byte 一致することをプログラムで突合** (`OK sections: 29 / 29`)、うち指定 3 件 + 監査の追加 2 件について ruling 帰属の妥当性を目視確認した。`versioning.version_binding` は **10,269 字**が byte 一致し、本文が名指しする 従属判断 7 / 8 / 9 / 10 / 11 と companion の記載が一致する。
  - **実装判断 (設計との差、監督承認)**: **引用は値の全文である** (マーカー句だけでは ruling の義務が読めない)。**逐語一致の常設テストと導入版の機械照合 (`checked == 17`) を差し戻しで足した。** **ruling 参照から行番号を外した。** **`previously` の誤ヒット 2 値には注記を置いた。** 詳細は §3 D-4 訂正註。

- **WP-4** (R-11 = `ops verify-declarations` 両 peer 同型 + smoke test + backup/restore + argv secret 検査)
  - **触ったファイル**: 両 peer の `platform_declarations.py` (`PlatformDeclarationError.code`、raise site **各 23 箇所**) と `ops.py` (`verify-declarations` サブコマンド)、両 peer の `tests/test_ops_verify_declarations.py` (新設、**各 18 テスト**) と `tests/test_audit_query.py` (同型性表 **67 → 86 行**)、`tools/deploy_smoke.py` (新設、標準ライブラリ `urllib` のみ)、`conformance-tests/test_deploy_secret_argv_scan.py` (新設)、`r2db-api/deploy/scripts/part1_provision_host_and_db.sh`、`r2db-api/migrations/` の 0001 / 0002 / 0008 (**冒頭コメントの使用例のみ**)、`docs/ops/BACKUP_RESTORE_R2DB.md` (新設)。
  - **集計行 (最終)**: `conformance-tests/test_deploy_secret_argv_scan.py` → **4 passed**、両 peer の `test_ops_verify_declarations.py` → **各 18 passed**、`r2db-api/tests` → **952 passed, 1 warning in 77.57s**、`MitateDB-api/tests` → **774 passed in 60.10s**、`bash -n` OK / `shellcheck` exit 0、`tools/public_value_scan.py` → `# mode=tree files_scanned=267 total_flagged=0` (未追跡 14 件を明示 → `files_scanned=14 total_flagged=0`)。
  - **変異**: 実装 **4 件** + 差し戻し 1 で **2 件** + 差し戻し 2 で **2 件** + 監査の自作 **2 件 (A / B)**。**差し戻し 2 回** (レビュー 8 件 → 差し戻し 1、受け入れ監査 → 差し戻し 2)。
  - **監査の未充足とその処置**: **完了条件 9 (同型性対応表) が未充足だった** — 両 peer の `ops.py` 冒頭コメントが `_verify_declarations_checks` を「pinned」と名指ししているのに表に行が無く、**監査の自作変異 B (MitateDB 側のループ変数名だけ改名) が全緑だった**。**差し戻し 2 の裁定 1 で `_verify_declarations_checks` / `cmd_verify_declarations` + 正規化後一致の定数 5 個を表に足し (79 → 86 行)、変異 B と変異 A (対象外行の理由文だけ書き換え) の両方が赤になることを実測した。** **報告の切り分け説明も実測 (共有 36 記号、収録 13、残 23 は実差あり) に合わせて訂正した** — 旧報告の「残り 19 個は実差あり」は誤りだった。
  - **監査の残余 (設計側へ送った 2 件)**: **(1) argparse ネイティブ誤引数の exit 2** → **設計 D-5 の表への注記として処置した** (§3 D-5 訂正註 1)。**(2) `deploy_smoke.py` の exit 4 の二義性 (段 3 失敗と段 3 未実施が同じ 4)** → **差し戻し 2 の裁定 3 で終了コードを分けた** (1/2/3 = 段ごとの失敗、4 = 段 3 未実施、5 = usage)。
  - **WP-6 への申し送り (監査)**: `{scratchpad}/backup_restore_r2db_final.txt` の dump パスに作業機の絶対パスが含まれる → **§11.1 へ転記する際に `<DUMP_PATH>` へ置換した** (公開規律)。
  - **L7-19**: **本 WP でも撤去条件未達である。`constraints.txt` と 3 つの `filterwarnings` は無変更**であることを監査が `git diff` で確認した (L8-2)。

- **WP-5** (R-12 = 性能基準値ハーネス)
  - **触ったファイル**: `tools/perf_baseline.py` (新設) と `tools/PERF_BASELINE_README.md` (新設) の **2 つのみ**。**製品コードと `conformance-tests/` は無変更である** (`git status` は未追跡 2 件のみ)。
  - **集計行 (試走、基準値ではない)**: `--warmup 2 --n 5` で **PERFRUN + PERF 14 行 / EXIT=0**。`tools/public_value_scan.py` → `# mode=tree files_scanned=2 total_flagged=0`。**基準値そのものは監督が完了ゲートで単独実行し、§11.2 に記録した。**
  - **変異**: 実装 **1 件** (自己検査の非空性) + registry 増加の実測 **1 件** + 監査の自作 **3 件 (A / B / C)**。**差し戻し 1 回** (レビュー 8 件)。
  - **非空振りの実測**: **カウンタを無効化する変異 → EXIT=1**、in-process 2 plug が `min=0 < 1 over N samples` で赤 (HTTP 2 plug は別コードパスなので無傷)。**registry を +1 した複製で走らせると PERF 行が 14 → 17 行になる** (plug 名・module 名をハーネスに手書きしていないことの実証。`conformance-tests/registry.json` 本体は無変更)。**閾値の grep は自己検査の 1 件のみ。**
  - **監査の残余とその処置**: **(1) 裁定 2 (値生成を計測窓の外へ) が部分充足** — `BatchOperation` / `ScopedBatchOperation` の生成が窓内に残る (窓内コストの実測は §11.2 の注記に開示)。**`BatchOperation` の事前生成は監督が最終修正した (main `02afb01`)。** **(2) `README:33` の誤記** (「warmup も PERF 行の `n=` に echo される」) → 訂正。**(3) `--warmup` が出力に残らない** → **§11.2 にゲート時のコマンド行 (warmup と n) を注記として添える形で決着した** (PERF / PERFRUN は確定文言なのでフィールドを増やさない)。**(4) §11.2 の表の行順がハーネスの出力順と異なる** → **本記録では表を出力順 (registry 順) に差し替えた** (転記時の取り違え防止)。
  - **設計への疑義 (記録)**: **`cross_entity` の操作数 (2 entity × 1 insert)**、**in-process 2 plug の `backend_calls` 粒度差 (台帳 L8-11)**、**`build_adapter()` 直使い + op ごとの credential 発行**の 3 点。**いずれも設計が固定していない範囲であり逸脱ではない** — 前 2 者は §11.2 の注記と台帳へ、3 点目はハーネスの docstring / README へ落とした。
  - **衛生**: 出力に hostname・ユーザー名・絶対パスは 0 件。`pg_database` の残留 0 (`datname ilike '%perf%'` が空)。**レビュー中に `mtdbctl…_platform` DB が出現したが、他 WP の並行実行由来であり帰属不能である** — **以後、完了ゲートでは `pg_database` の前後差分を取る** (ゲート時は 21 → 21)。

- **WP-6** (記録・第 15 次引き継ぎ・計画文書の改版)
  - **触ったファイル**: 本書 (§3 の各 D に訂正註、§5 U-1 に状態注記、§9 に結果、§10 に状態注記と新規起票 L8-10〜L8-16、§11 の全記入、版数行)、`docs/design/ROADMAP_POST_PHASE7_V1.md` (**v1.2** — §1 現状、§5 フェーズ8 節、§5 / §8 の R-10 行と §5 / §7 / §8 の R-12 行の改版、§8 の R-9〜R-12 の行き先)、`docs/design/PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md` (§11 の L7-1 / L7-18 / L7-19 / L7-21 / L7-22 / L7-23 に状態注記、D-6.2 の `operation_depth` 行に訂正註、版数行 1 行)、`docs/work-orders/WORK_ORDER_PHASE8_EFFECTIVE_BOUNDS_V1.md` (**§5 訂正註のみ。本文は書き換えていない**)、`docs/work-orders/HANDOVER_20260907_FABLE.md` (**第 15 次、新設**)、`docs/work-orders/HANDOVER_20260906_FABLE.md` (§4-2 末尾に第 15 次へのポインタ 1 行)、`conformance-tests/COLLECTION_FLOOR` (**2274 → 2340。監督のゲート作業**)。
  - **集計行**: `./.venv/bin/python tools/public_value_scan.py` → **`# mode=tree files_scanned=267 total_flagged=0`** (未追跡の新設 1 ファイルは明示引数で走査し `total_flagged=0`)。**本 WP の成果物はすべて文書・記録であり、変異は作らない** (全項目が監査照合である)。
  - **計画文書の改版 (R-14)**: **行を 1 つも消していない。** R-10 行と R-12 行は**旧文を残したうえで、根拠と日付を添えた改版文を足す**形にした (L8-8)。
  - **記録の限界 (開示)**: **CI の WP-1 入り run (main `f4635ed`) は起草時点で未確認だったが、監督が 2026-09-07 に run 34047745958 を確認し §11.1 に追記した** (3.11 / 3.12 とも `2340 passed`、4 数一致)。 台帳 L7-6 (CI とローカルの集計行が食い違ったときの正本) と同じ扱いである。

---

## 付録 A. R-10 の経緯マーカー逐語インベントリ (常設規律 5)

**本付録は `spec/data-service-api.v1.json` (main `9389fd5`) に対する機械走査の結果であり、判断を含まない事実の記録である。** §3 D-4 と §5 U-2 はこの表を根拠にしている。走査は逐語プロトタイプ (`{scratchpad}/r10_marker_inventory.py`) が出力したものを、見出しの階層だけ 1 段下げて**そのまま転記**した (内容は 1 文字も変えていない)。

**読み方**:
- **`chars`** = その値の全長。**`matched patterns`** = その値に現れた経緯マーカーの種別。
- **`(i) starts_with_marker` / `trailing_chars_after_last_marker`** = マーカーが値の先頭にあるか、最後のマーカーの後ろに何文字続くか。**後続が長い値ほど「マーカーと現行規範文が同居する複合文」である** (U-2 (A) が触らない側)。
- **`(ii) test-pinned`** = `conformance-tests/test_contract.py` の PIN 定数またはパス式 assert が固定しているか。**U-2 (A) では参照先の付け替えだけ、(B) では定数の文言そのものの書き換えになる。**
- **`(iii) product code reads key`** = 製品コードがそのキーを読むか (読むキーの移動は挙動に影響し得るので、マニフェストの分類で特に注意する)。

**なお、探索ノート (b)(d) が「マーカー 51 件・35 キー」と数えたのは値の中の出現回数を数えたものであり、本表の「29 値」は「マーカーを 1 つ以上含む値の個数」である** — 数え方が違うだけで、対象は同じである。

**逐語転記 (ここから)** — R10 verbatim marker inventory (design-doc appendix material, no judgment)

Contract file: `spec/data-service-api.v1.json` (77117 bytes/chars)

contract_version at scan time: `1.6.0`


### A.0. Triple sha256 check

| copy | sha256 |
|---|---|
| `spec/data-service-api.v1.json` | `968d3c72415d4536c0393ce451497324c182cbc2ae9d9213e0ec6ed4444f45e6` |
| `MitateDB-api/src/mitatedb_api/contract/data-service-api.v1.json` | `968d3c72415d4536c0393ce451497324c182cbc2ae9d9213e0ec6ed4444f45e6` |
| `r2db-api/src/r2db_api/contract/data-service-api.v1.json` | `968d3c72415d4536c0393ce451497324c182cbc2ae9d9213e0ec6ed4444f45e6` |

All three byte-identical: **True**


### A.1. Marker inventory table

| JSON path | chars | matched patterns | value head (verbatim, first 160 chars) | classification material |
|---|---|---|---|---|
| `audit.query_cursor` | 562 | Since 1.x.y, subordinate ruling N, ruling | Since 1.4.0 (subordinate ruling 9, item 1, conditional): AuditQueryRequest.after is an opaque cursor, not an event_id or a numeric offset -- a client never cons | (i) starts_with_marker=True, trailing_chars_after_last_marker=531<br>(ii) test-pinned: test_contract.py:212 (test_audit_query_after_is_an_opaque_cursor @L209) via path expr<br>(iii) product code reads key: none found |
| `audit.query_event_class_vocabulary` | 462 | Since 1.x.y, subordinate ruling N, ruling | Since 1.4.0 (subordinate ruling 9, item 4, conditional): event_class is a vocabulary each implementation declares for itself, at capabilities().audit_query.even | (i) starts_with_marker=True, trailing_chars_after_last_marker=431<br>(ii) test-pinned: test_contract.py:248 (test_event_class_is_a_declared_vocabulary @L244) via path expr<br>(iii) product code reads key: none found |
| `audit.query_event_fields_note` | 736 | Since 1.x.y, subordinate ruling N, ruling | Since 1.4.0 (subordinate ruling 9, items 1 and 3, conditional): each event AuditResult.events[] returns from audit_query MAY carry fields beyond audit.fields -- | (i) starts_with_marker=True, trailing_chars_after_last_marker=56<br>(ii) test-pinned: test_contract.py:233 (test_audit_result_event_carries_plane_and_cursor @L223) via path expr<br>(iii) product code reads key: none found |
| `audit.query_operation_vocabulary` | 876 | Since 1.x.y, subordinate ruling N, ruling | Since 1.5.0 (subordinate ruling 10, item 1, conditional): operations and target_kinds are vocabularies each implementation declares for itself at capabilities() | (i) starts_with_marker=True, trailing_chars_after_last_marker=845<br>(ii) test-pinned: test_contract.py:494 (test_contract_pins_the_requester_finalized_1_4_0_and_1_5_0_prose @L484) via path expr; PIN_1_5_0_SENTENCE_1 (pinned constant; used at lines ['447', '510', '519']); PIN_1_5_0_SENTENCE_2 (pinned constant; used at lines ['454', '511', '520']); PIN_1_5_0_SENTENCE_3 (pinned constant; used at lines ['459', '512', '521']); PIN_1_5_0_SENTENCE_4 (pinned constant; used at lines ['465', '522']); test_contract.py:448 (test_version_binding_1_4_0_unconditional_and_conditional_counts_agree @L343) via substring-of-value grep<br>(iii) product code reads key: none found |
| `audit.query_ordering` | 537 | Since 1.x.y, subordinate ruling N, ruling | Since 1.4.0 (subordinate ruling 9, item 2, conditional on audit_query being provided -- versioning.version_binding): AuditResult.events[] returned by audit_quer | (i) starts_with_marker=True, trailing_chars_after_last_marker=506<br>(ii) test-pinned: test_contract.py:231 (test_audit_result_event_carries_plane_and_cursor @L223) via path expr<br>(iii) product code reads key: none found |
| `audit.query_target_kind_vocabulary` | 876 | Since 1.x.y, subordinate ruling N, ruling | Since 1.5.0 (subordinate ruling 10, item 1, conditional): operations and target_kinds are vocabularies each implementation declares for itself at capabilities() | (i) starts_with_marker=True, trailing_chars_after_last_marker=845<br>(ii) test-pinned: test_contract.py:495 (test_contract_pins_the_requester_finalized_1_4_0_and_1_5_0_prose @L484) via path expr; PIN_1_5_0_SENTENCE_1 (pinned constant; used at lines ['447', '510', '519']); PIN_1_5_0_SENTENCE_2 (pinned constant; used at lines ['454', '511', '520']); PIN_1_5_0_SENTENCE_3 (pinned constant; used at lines ['459', '512', '521']); PIN_1_5_0_SENTENCE_4 (pinned constant; used at lines ['465', '522']); test_contract.py:448 (test_version_binding_1_4_0_unconditional_and_conditional_counts_agree @L343) via substring-of-value grep<br>(iii) product code reads key: none found |
| `capability_status.defined.atomic_mutation` | 658 | subordinate ruling N, ruling | Single-entity atomic mutation batches. A capability entry's own operations list names the mutation vocabulary the batch execution surface executes -- not a batc | (i) starts_with_marker=False, trailing_chars_after_last_marker=377<br>(ii) test-pinned: test_contract.py:188 (test_contract_1_3_0_prose_pins @L171) via path expr<br>(iii) product code reads key: r2db-api/src/r2db_api/service.py:912; MitateDB-api/src/mitatedb_api/cell.py:1421 |
| `control_endpoints.audit_query.semantics` | 969 | subordinate ruling N, ruling | Added in 1.4.0 (subordinate ruling 9, item 7): this is audit_query's canonical location, moved here from endpoints.audit_query because its only real authority ( | (i) starts_with_marker=False, trailing_chars_after_last_marker=935<br>(ii) test-pinned: none found<br>(iii) product code reads key: none found |
| `control_endpoints.revoke_credential.semantics` | 496 | previously | Terminal. A revoked credential can never be made valid again; enable does not apply. Revoking the last remaining active control credential is permitted but requ | (i) starts_with_marker=False, trailing_chars_after_last_marker=79<br>(ii) test-pinned: none found<br>(iii) product code reads key: none found |
| `control_plane.authority` | 358 | subordinate ruling N, ruling | Application credentials fail closed on every control endpoint; control credentials are rejected on data/schema endpoints. An audit credential is accepted only o | (i) starts_with_marker=False, trailing_chars_after_last_marker=87<br>(ii) test-pinned: test_contract.py:193 (test_contract_1_3_0_prose_pins @L171) via path expr; test_contract.py:264 (test_audit_role_is_accepted_on_audit_query @L258) via path expr<br>(iii) product code reads key: r2db-api/src/r2db_api/service.py:915; r2db-api/src/r2db_api/control_plane.py:760; MitateDB-api/src/mitatedb_api/cell.py:1433; MitateDB-api/src/mitatedb_api/control_plane.py:1430 |
| `definitions.EntityDescriptor.properties.field_types.description` | 2208 | Since 1.x.y, subordinate ruling N, ruling | Since 1.6.0 (subordinate ruling 11, item 3, conditional on application_catalog being provided -- versioning.version_binding): The field-type vocabulary gains a  | (i) starts_with_marker=True, trailing_chars_after_last_marker=2177<br>(ii) test-pinned: PIN_1_6_0_ITEM_3_FIELD_TYPES (pinned constant; used at lines ['554', '674'])<br>(iii) product code reads key: none found |
| `definitions.Mutation.properties.values.description` | 237 | subordinate ruling N, ruling | Deliberately left open (subordinate ruling 7(A)): the field-name vocabulary is entity-defined, not fixed by this contract, so an additionalProperties: false clo | (i) starts_with_marker=False, trailing_chars_after_last_marker=195<br>(ii) test-pinned: none found<br>(iii) product code reads key: none found |
| `definitions.ScopedMutation.properties.values.description` | 237 | subordinate ruling N, ruling | Deliberately left open (subordinate ruling 7(A)): the field-name vocabulary is entity-defined, not fixed by this contract, so an additionalProperties: false clo | (i) starts_with_marker=False, trailing_chars_after_last_marker=195<br>(ii) test-pinned: none found<br>(iii) product code reads key: none found |
| `destructive_confirmation.phrase_construction.rules[3]` | 448 | previously | State-fingerprinted for re-creatable targets: a target identifiable by a name that can be destroyed and later recreated (e.g. an entity or index) includes a sta | (i) starts_with_marker=False, trailing_chars_after_last_marker=143<br>(ii) test-pinned: none found<br>(iii) product code reads key: none found |
| `destructive_confirmation.resolved_in` | 206 | subordinate ruling N, ruling | 1.2.0. Defines the declare-and-echo confirmation semantics for every destructive operation in this contract, common across data, schema, and control-plane surfa | (i) starts_with_marker=False, trailing_chars_after_last_marker=4<br>(ii) test-pinned: none found<br>(iii) product code reads key: none found |
| `endpoints.audit_query.deprecation_note` | 639 | Since 1.x.y, subordinate ruling N, ruling | Since 1.4.0 (subordinate ruling 9, item 7): this entry's path is retained as an alias of control_endpoints.audit_query for one further minor version after 1.4.0 | (i) starts_with_marker=True, trailing_chars_after_last_marker=608<br>(ii) test-pinned: none found<br>(iii) product code reads key: none found |
| `limits.audit_requests_per_minute_note` | 662 | Since 1.x.y, subordinate ruling N, ruling | Since 1.4.0 (subordinate ruling 9, item 8, conditional on audit_query being provided -- versioning.version_binding). A pre-authentication fixed window governing | (i) starts_with_marker=True, trailing_chars_after_last_marker=631<br>(ii) test-pinned: test_contract.py:314 (test_audit_requests_per_minute_is_a_declared_limit_class @L306) via path expr<br>(iii) product code reads key: none found |
| `schemas.AuditResult.properties.events.items.description` | 210 | subordinate ruling N, ruling | Deliberately left open (subordinate ruling 7(A)): audit.fields is itself an open-ended, additive vocabulary, and a per-event shape is not one of the 11 response | (i) starts_with_marker=False, trailing_chars_after_last_marker=8<br>(ii) test-pinned: none found<br>(iii) product code reads key: none found |
| `schemas.CapabilityDocument.description` | 442 | subordinate ruling N, ruling | The envelope itself is closed (additionalProperties: false at this level), but capabilities/limits/limit_enforcement below and each capability entry's own value | (i) starts_with_marker=False, trailing_chars_after_last_marker=7<br>(ii) test-pinned: none found<br>(iii) product code reads key: none found |
| `schemas.CapabilityDocument.properties.surfaces.description` | 1503 | Since 1.x.y, subordinate ruling N, ruling | Since 1.6.0 (subordinate ruling 11, item 2; unconditional -- versioning.version_binding): surfaces names the absolute base URLs at which this deployment's own s | (i) starts_with_marker=True, trailing_chars_after_last_marker=1472<br>(ii) test-pinned: PIN_1_6_0_ITEM_2_SURFACES (pinned constant; used at lines ['551', '631'])<br>(iii) product code reads key: none found |
| `schemas.CredentialIssued.properties.secret.description` | 1045 | Since 1.x.y, subordinate ruling N, ruling | Since 1.6.0 (subordinate ruling 11, item 1; unconditional -- versioning.version_binding): CredentialIssued.secret -- and the secret a rotate response returns, w | (i) starts_with_marker=True, trailing_chars_after_last_marker=1014<br>(ii) test-pinned: test_contract.py:609 (test_contract_pins_the_requester_finalized_1_6_0_prose @L596) via path expr; PIN_1_6_0_ITEM_1_SECRET_IS_BEARER (pinned constant; used at lines ['548', '606'])<br>(iii) product code reads key: none found |
| `schemas.CredentialRotated.properties.secret.description` | 1045 | Since 1.x.y, subordinate ruling N, ruling | Since 1.6.0 (subordinate ruling 11, item 1; unconditional -- versioning.version_binding): CredentialIssued.secret -- and the secret a rotate response returns, w | (i) starts_with_marker=True, trailing_chars_after_last_marker=1014<br>(ii) test-pinned: test_contract.py:610 (test_contract_pins_the_requester_finalized_1_6_0_prose @L596) via path expr; PIN_1_6_0_ITEM_1_SECRET_IS_BEARER (pinned constant; used at lines ['548', '606'])<br>(iii) product code reads key: none found |
| `schemas.MutationResult.properties.assigned_addresses.items.properties.address.description` | 164 | subordinate ruling N, ruling | Deliberately left open (subordinate ruling 7(A)): the address field-name vocabulary is entity-defined (EntityDescriptor.address_fields), not fixed by this contr | (i) starts_with_marker=False, trailing_chars_after_last_marker=122<br>(ii) test-pinned: none found<br>(iii) product code reads key: none found |
| `schemas.SchemaOperationRequest.properties.field_types.description` | 2206 | Since 1.x.y, subordinate ruling N, ruling | Since 1.6.0 (subordinate ruling 11, item 3, conditional on schema_operations being provided -- versioning.version_binding): The field-type vocabulary gains a se | (i) starts_with_marker=True, trailing_chars_after_last_marker=2175<br>(ii) test-pinned: PIN_1_6_0_ITEM_3_FIELD_TYPES (pinned constant; used at lines ['554', '674'])<br>(iii) product code reads key: none found |
| `security.schemes.application_credential.description` | 1155 | Since 1.x.y, subordinate ruling N, ruling | Opaque credential presented over TLS. The service stores only a verifier/digest and never returns the secret. Since 1.6.0 (subordinate ruling 11, item 1; uncond | (i) starts_with_marker=False, trailing_chars_after_last_marker=1014<br>(ii) test-pinned: test_contract.py:607 (test_contract_pins_the_requester_finalized_1_6_0_prose @L596) via path expr; PIN_1_6_0_ITEM_1_SECRET_IS_BEARER (pinned constant; used at lines ['548', '606'])<br>(iii) product code reads key: none found |
| `security.schemes.control_credential.description` | 1333 | Since 1.x.y, subordinate ruling N, ruling | A separately authenticated Control/Audit authority; application credentials are not accepted. The service stores only a verifier/digest; the secret is returned  | (i) starts_with_marker=False, trailing_chars_after_last_marker=1014<br>(ii) test-pinned: test_contract.py:608 (test_contract_pins_the_requester_finalized_1_6_0_prose @L596) via path expr; PIN_1_6_0_ITEM_1_SECRET_IS_BEARER (pinned constant; used at lines ['548', '606'])<br>(iii) product code reads key: none found |
| `structured_operations.reserved_entity_names_note` | 752 | Since 1.x.y, subordinate ruling N, ruling | Since 1.4.0 (subordinate ruling 9, item 6; unconditional -- versioning.version_binding). audit_events is reserved across implementations as an entity/collection | (i) starts_with_marker=True, trailing_chars_after_last_marker=721<br>(ii) test-pinned: test_contract.py:277 (test_audit_events_is_a_documented_reserved_name @L271) via path expr<br>(iii) product code reads key: none found |
| `versioning.compatibility` | 726 | previously | Additive fields and capabilities are allowed; removal or semantic change requires a new major version. The control surface follows the same compatibility rules. | (i) starts_with_marker=False, trailing_chars_after_last_marker=52<br>(ii) test-pinned: none found<br>(iii) product code reads key: none found |
| `versioning.version_binding` | 10269 | Since 1.x.y, subordinate ruling N, ruling | An implementation's own declared contract_version is the general rule for which version's definitions it is claiming conformance to: only an implementation decl | (i) starts_with_marker=False, trailing_chars_after_last_marker=2631<br>(ii) test-pinned: test_contract.py:330 (test_version_binding_1_4_0_obligations_are_conditional_on_providing_audit_query @L319) via path expr; test_contract.py:360 (test_version_binding_1_4_0_unconditional_and_conditional_counts_agree @L343) via path expr; test_contract.py:493 (test_contract_pins_the_requester_finalized_1_4_0_and_1_5_0_prose @L484) via path expr; test_contract.py:689 (test_contract_pins_the_requester_finalized_1_6_0_prose @L596) via path expr; PIN_1_4_0_OBLIGATION_B_ADDENDUM (pinned constant; used at lines ['433', '497']); PIN_1_5_0_SENTENCE_1 (pinned constant; used at lines ['447', '510', '519']); PIN_1_5_0_SENTENCE_2 (pinned constant; used at lines ['454', '511', '520']); PIN_1_5_0_SENTENCE_3 (pinned constant; used at lines ['459', '512', '521']); PIN_1_6_0_VERSION_BINDING_PARAGRAPH (pinned constant; used at lines ['563', '580', '690']); PIN_1_6_0_RETROACTIVE_DENIAL_ROW_1_1_0 (pinned constant; used at lines ['582', '696']); PIN_1_6_0_RETROACTIVE_DENIAL_ROW_1_2_0 (pinned constant; used at lines ['585', '697']); PIN_1_6_0_RETROACTIVE_DENIAL_ROW_1_3_0 (pinned constant; used at lines ['588', '698']); PIN_1_6_0_RETROACTIVE_DENIAL_ROW_1_4_0 (pinned constant; used at lines ['591', '699'])<br>(iii) product code reads key: none found |

### A.2. Aggregates

#### A.2a. By pattern

| pattern | count (value matches, not occurrence count within value) |
|---|---|
| Since 1.x.y | 17 |
| subordinate ruling N | 26 |
| superseded | 0 |
| supersedes | 0 |
| ruling | 26 |
| Phase N | 0 |
| WP-N | 0 |
| date YYYY-MM-DD | 0 |
| CCR-N | 0 |
| historical | 0 |
| previously | 3 |
| formerly | 0 |
| was (leading) | 0 |

#### A.2b. By key (last path segment)

| key | count |
|---|---|
| `description` | 12 |
| `semantics` | 2 |
| `compatibility` | 1 |
| `version_binding` | 1 |
| `atomic_mutation` | 1 |
| `deprecation_note` | 1 |
| `authority` | 1 |
| `resolved_in` | 1 |
| `rules` | 1 |
| `reserved_entity_names_note` | 1 |
| `audit_requests_per_minute_note` | 1 |
| `query_ordering` | 1 |
| `query_cursor` | 1 |
| `query_event_fields_note` | 1 |
| `query_event_class_vocabulary` | 1 |
| `query_operation_vocabulary` | 1 |
| `query_target_kind_vocabulary` | 1 |

#### A.2c. Totals

- Total matched string values: 29
- Of which test-pinned (some grep hit found): 18
- Of which product code reads the key (some grep hit found): 2
- `versioning.version_binding` length: 10269 chars
- `versioning.version_binding` as % of whole contract file: 13.32%

### A.3. CCR_DISPOSITION.md heading structure (subordinate rulings) summary

- `spec/CCR_DISPOSITION.md` L1: `# CCR-01〜12 共通契約採否記録` (table of CCR-01..12 dispositions, all 採用)
- L22: `## 追加契約変更 (2026-08-27...)` (2 additive changes realizing CCR-06/CCR-10)
- L33: `## CCR-13〜15 採否記録 (r2db-api 起票)` (CCR-13/14/15, all 採用 2026-08-28)
- L45: `### 判断の軸` / L54: `### 各版の誤りの記録` (draft-history notes, versions 1-4 corrections)
- L87: `### 裁定の記録 (依頼者)` (requester rulings on CCR-13/14/15 itself)
- L93: `### 従属判断 — すべて裁定済み` (numbered subordinate rulings 1-11, each = one contract-version bundle: 1-6 are pre-1.1.0 items; 7=1.2.0-adjacent; 8=1.3.0 bundle A-F; 9=1.4.0 bundle (8 items); 10=1.5.0 bundle (2 items); 11=1.6.0 bundle (4 items D-1..D-3(vii)))
- L199: `### 実装順序 (採用後)` (implementation ordering note, closing)

#### A.3a. subordinate ruling N -> CCR_DISPOSITION.md line table (numbered-item start lines found by scanning `^N. **`)

| N (subordinate ruling) | CCR_DISPOSITION.md line (item start) | referenced in contract JSON? |
|---|---|---|
| 1 | spec/CCR_DISPOSITION.md:95 | no |
| 2 | spec/CCR_DISPOSITION.md:96 | no |
| 3 | spec/CCR_DISPOSITION.md:97 | no |
| 4 | spec/CCR_DISPOSITION.md:99 | no |
| 5 | spec/CCR_DISPOSITION.md:101 | no |
| 6 | spec/CCR_DISPOSITION.md:103 | yes |
| 7 | spec/CCR_DISPOSITION.md:105 | yes |
| 8 | spec/CCR_DISPOSITION.md:112 | yes |
| 9 | spec/CCR_DISPOSITION.md:127 | yes |
| 10 | spec/CCR_DISPOSITION.md:150 | yes |
| 11 | spec/CCR_DISPOSITION.md:171 | yes |
