# フェーズ9 実施設計: 契約 1.7.0「宣言と検証」

- 版数: **v1.3 (2026-09-07)**。**改版履歴**:
  - **v1.0 (2026-09-07)** — 起草初稿。設計レビュー 1 回目の対象となる版である。
  - **v1.1 (2026-09-07)** — 設計レビュー 1 回目 (Blocker 4 / Major 9 / Minor 10) を全件反映、§5 U-1〜U-8 を依頼者裁定の委任に基づき監督が確定。**設計レビュー 2 回目の対象となる版**である。
  - **v1.2 (2026-09-07)** — 設計レビュー 2 回目 (Blocker 4 / Major 9 / Minor 13) を全件反映 (監督裁定 S-a〜S-n)。U-3 / U-4 の確定文を訂正後の本文に差し替え。
  - **v1.3 (2026-09-07)** — 作業指示書起草者の疑義 4 件に対する監督裁定 T-1〜T-4 を反映、§6.1 表の整形。
- 位置づけ: **監督が確定した枠 (2026-09-07) の実施設計**であり、**2 回の設計レビューを経て確定した設計 (v1.3) であって、作業指示書の正本である。** 計画文書 `docs/design/ROADMAP_POST_PHASE7_V1.md` (v1.2) の §5「フェーズ9」節・§4 (P-1〜P-9)・§7・§8 (R-2〜R-8 / R-10)・§9 が**正本**であり、本書 §1.1 / §2.1 はそれを**逐語で転記**する (再導出しない)。§3 の D-1〜D-9 と §4 の A-1〜A-10 は**監督確定**である。**§5 の U-1〜U-8 は、依頼者裁定 (2026-09-07) が判断を監督に委任したことに基づき、設計レビュー 1 回目の反映時に監督が確定した (v1.1)。U-3 / U-4 の確定文は v1.2 で監督の訂正後の本文に差し替えた (枝の確定は不変)。** **作業指示書の起草中に生じた疑義 4 件は監督裁定 T-1〜T-4 として v1.3 に反映した** (§3 D-4 の実装の形 / §5 U-8 #29 / §6.2 / §6.3 / §6.4 / §6.6 / §8 / §8.1 / §9)。 **§3 D-10 は v1.1 で撤回した** (レビュー 1 B1。前提事実の誤り)。WP 分割は §8 に素案のみを置き、作業指示書 (`docs/work-orders/WORK_ORDER_PHASE9_CONTRACT_170_V1.md`) は別途起こす。構成・粒度・文体はフェーズ8 設計文書 (`docs/design/PHASE8_EFFECTIVE_BOUNDS_AND_HYGIENE_V1.md` v1.3) を踏襲する。
- テーマ: **「エージェントの 1 周 (catalog を読む → 要求を作る → 判定を受ける → 安全に再送する) が、宣言だけで閉じており、その宣言がすべて検査されている」状態にすること。**
- 前提となる main: **`523753c`** (= フェーズ8 完了の `ef7bd57` に WP-9 リハーサルのコミット群を重ねたもの)。作業 branch **`phase9-contract-170`**、worktree はフェーズ8 と同じ運用 (`.claude/worktrees/` 配下、WP ごとに分ける。§8)。
- **契約は変わる**。本フェーズは **契約 1.6.0 → 1.7.0** の改版であり、`spec/CCR_DISPOSITION.md` に**従属判断 12** を新設する。契約 JSON の 3 複製 (`spec/data-service-api.v1.json`、`r2db-api/src/r2db_api/contract/data-service-api.v1.json`、`MitateDB-api/src/mitatedb_api/contract/data-service-api.v1.json`) は**同一コミットで同一バイトに**更新する。**現行 3 複製の sha256 は `968d3c72415d4536c0393ce451497324c182cbc2ae9d9213e0ec6ed4444f45e6`** (2026-09-07 実測、フェーズ8 設計 付録 A §A.0 と一致)。本フェーズ後は当然この値から動く — **動いた後の値を §11.1 に記録する**のが完了ゲートの一部である。
- 応える G (計画文書 §0、R-1 の要求): **G-1** (AI エージェントにとって最良の DB プラットフォーム = エージェントの 1 周を閉じること) と **G-3** (比類なき信頼性 = 1 要求 = 1 原子単位、再送安全性、宣言が真であること) が**本フェーズの主対象**である。**G-2** (人から見て比類なきセキュリティ) には**新条件 C-20〜C-25 の証明可能性**で応える — 本フェーズが足す宣言は 1 つ残らず共通条件で検査される。**G-4** (高性能は大前提) には **P-8 の差分記録**で応える — フェーズ8 §11.2 の基準値に対する差分を完了ゲートに添える (§9)。
- 体制・規律: 既存フェーズと同一である。Fable 監督/設計/コミット、Opus 起草/独立レビュー/受け入れ監査、Sonnet 実装 (コミットしない)。**設計レビューは 2 回** (契約を触るフェーズ。計画文書 §9 の 3。**フェーズ8 は 1 回だった — 回数を取り違えない**、第 15 次引き継ぎ §4-3 の 3)。
- 設計原則 (依頼者、2026-09-02): 先送りしない / シンプル / 制約・制限で回避しない / 誇れる成果物。既定の重み付けは「最小変更」ではなく「長期に正しい形」。**利用設計者は AI エージェントであり、宣言は確実に読まれる** — 本フェーズはこの前提を最大限に使う (宣言できるものは宣言し、宣言したものは強制する)。
- **公開規律**: 本書には実値を一切書かない — 実ホスト名・cloud project 識別子・実 e-mail・実 credential_id・作業機の絶対パス・IAM principal を含まない。合成値は `<UPPER_SNAKE>` 形の placeholder と `*.example.invalid` のみを使う。**file:line はすべて worktree 相対パス**である。
- **WP-9 (フェーズ7 の公開ゲート) と並行できる**。WP-9 が触るのは `tools/rewrite_hash_refs.py` と docs/ の hash 参照の一括更新のみであり、**本フェーズはそのツールを触らない** (§8.1)。本書に commit hash を書いた場合、WP-9 の commit-map 適用対象になるだけで衝突しない。

---

## 1. 問題設定

### 1.1 計画文書 §5「フェーズ9」節の転記

計画文書 `docs/design/ROADMAP_POST_PHASE7_V1.md` §5 のフェーズ9 節を以下に**転記する** (再導出しない)。

> **フェーズ9 — 契約 1.7.0「宣言と検証」**
>
> - **目的**: G-1 と G-3。エージェントの 1 周 (P-2) を閉じる。
> - **着手条件**: フェーズ8 完了 (実効 bound の無い peer に新しい要求形を足さない)。契約フェーズなので**設計レビュー 2 回**。
> - **範囲** (一括出荷。分けると P-4 に反する):
>   - **R-2** 制約宣言: `create_entity` / `add_field` / `alter_field` に enum と nullable。サーバが値検証の choke point で強制し、`EntityDescriptor` が同じ版で報告する。既存行が反する `alter_field` は実行前検証で全件拒否。`pattern` は正規表現の計算量が SI-08 の面になるので**初版に含めない**。両 peer の宣言永続化は per-application upgrade (フェーズ6 / Q4 の機構) で行う。
>   - **R-3** 検証エラー語彙: VALIDATION_FAILED / IDENTIFIER_INVALID / CAPABILITY_UNSUPPORTED に固定 key (`field` / `declared_type` / `observed_type` / `violated_declaration`)。事実のみ。行値・推奨値・修正動作は載せない (SI-10)。両 peer でどの層が `violated_declaration` を決めるかを揃える (L6-9 の二重検証を整理する)。
>   - **R-4** dry_run と無状態 plan: `MutationRequest` / `ScopedMutationRequest` / `SchemaOperationRequest` に `dry_run`。応答は実呼びと同じ判定 + affected 件数 + (schema なら) 変更後の `EntityDescriptor`。副作用の規則 (監査イベント・idempotency 記録・server-assigned address の消費) を契約に明記。plan トークン = request digest + 対象 entity の schema revision の決定的値で、apply 時に不一致なら PRECONDITION_FAILED。認可判定 (policy simulation) も dry_run の判定に含める。conformance 条件: 「dry_run の判定 = 実呼びの判定、外部可視の状態変化 0」。
>   - **R-5** idempotency の実装と契約追記: 両 peer で `idempotency` を `enabled` へ。契約に追記するのは (i) key と body digest の結合、(ii) 同一 key 異 body は CONFLICT、(iii) 保持期間内の再送は元の結果を返す、(iv) cross-entity と schema 操作にも適用、(v) 監査イベントとの相関 (key は secret ではないが、**client が secret 的な値を key に入れることを契約で禁じる文**を置き、`forbidden_fields` との境界を明記)。L7-8 の肯定側がここで初めて load-bearing になる。
>   - **R-6** request budget: 要求単位の `budget` (初版は `result_items` / `execution_ms` / `batch_items` の 3 class)。配備上限を超える値は VALIDATION_FAILED、超過は LIMIT_EXCEEDED + `limit_class`。`rows_scanned` は limit class に無く backend 間で意味が揃わないので**含めない**。
>   - **R-7** 成功応答の `request_id` (QueryResult / MutationResult / SchemaOperationResult に optional 追加)。
>   - **R-8** 派生の操作カタログ: 契約 JSON から生成する機械可読 artifact (endpoint ごとの role / destructive / atomicity 境界 / 返し得る code / 能力依存 / request・response schema)。`tools/` で生成し、テストが再生成して一致を assert する。`/v1/capabilities` からの参照は optional 1 項目。「resource cost の概算方法」は両 peer で同型に計算できないので**含めない**。
> - **守るべき条件**: P-1 (plan は無状態)、P-3 (新宣言ごとに一致条件)、P-4、P-5 (budget は下回る方向のみ)、P-7 (経緯文を契約本体に足さない。R-10 の companion に書く)、`versioning.version_binding` の規律 (1.7.0 義務の網羅列挙)。
> - **完了条件**: 契約 1.7.0、両 peer の `contract_version` 1.7.0、新条件 (C-20 以降) が four adapters で executable、R-12 の性能差分が記録される。
> - **再検討事項**: enum の上限 (要素数・長さ) を `schema_objects` に含めるか別 class か。dry_run の監査イベントの扱い (attributable であるべきか、破壊操作の dry_run を security-relevant とみなすか)。idempotency の保持を DB 側単一真実 (Q4) に載せるか。

**あわせて、フェーズ8 からの送り 2 件が本フェーズの範囲に入る** (フェーズ8 設計 §10 L8-4 / L8-9、第 15 次引き継ぎ §4-3「フェーズ9 で先に片付くもの」)。

> - **R-10 (B) — 29 値の "Since 1.x.0 (subordinate ruling N, …): " 接頭辞 / 挿入句を剥がして companion へ移す** (フェーズ8 設計 §10 L8-4)。**手順が決まっている**: **(i) 対象文の before/after 一覧を依頼者に提示して再確定を得る** (常設規律 4。**18 件の PIN が依頼者確定文言である**)、(ii) `spec/CONTRACT_HISTORY_MANIFEST.json` を置く、(iii) 分離前後の JSON をマニフェストの逆適用後に deep-equal 比較する使い捨て検証 (`tools/` に常設しない)、(iv) 契約 JSON と両 peer の packaged 複製 2 本を同一コミットで同一バイトに更新する、(v) PIN 定数 18 件の書き換え。**1.7.0 に載せれば再確定が 1 回で済む** — これが送りの理由である。
> - **R-8 と L8-9 (`versioning.version_binding` の機械可読化) は同じ問題である** (フェーズ8 設計 §10 L8-9)。**10,269 字の単一文字列を版ごとの義務の配列に組み替える案は、`test_contract.py` が「N of those obligations are unconditional」の件数まで assert しているので、再生成一致テストと同時にしか行えない。**

**本書での §番号の対応**: 計画文書が「設計 §13」と書くのはフェーズ7 設計文書の節番号を指す慣行の踏襲である。**本書では実施記録は §11 であり、R-12 の性能差分は §11.2 に記録する** (フェーズ8 §11.2 と同形式)。

### 1.2 探索で確定した事実 (根拠)

以下はすべて本 worktree (main `523753c`) の現物を読んで確認した事実である。**テストは実行していない** (§1.3 を除く)。**F 番号は監督が確定した枠の番号であり、本節はそれを展開したものである。**

#### (a) 制約宣言 (R-2) の材料

- **F-1 `alter_field` は両 peer とも未実装である (present-denial)。** r2db は `bind_schema_operation` (`r2db-api/src/r2db_api/structured.py:589-761`) の if/elif 連鎖が末尾 `structured.py:761` で `CAPABILITY_UNSUPPORTED` を返し、`r2db-api/src/r2db_api/service.py:885` の `schema_ops` リテラル (`["create_entity", "add_field", "create_index", "drop_index", "drop_entity"]`) と `service.py:914` の capability 文書 (`"unsupported": ["alter_field", "jobs"]`) がそれを宣言する。**`r2db-api/src/r2db_api/structured.py:563` の `SCHEMA_OPERATIONS` 定数はリポジトリ全体で参照が 0 件の死んだ定数であり (2026-09-07 実測、レビュー 2 m5)、拒否点ではない** — **作業指示書に「`SCHEMA_OPERATIONS` を更新する」と書かない** (観測可能な変化が 0 の作業になる)。MitateDB は `MitateDB-api/src/mitatedb_api/http.py:941-946` が同じ形で拒否する。**なお `alter_field` に `field_type` を載せた要求は現行でも既に `VALIDATION_FAILED` になる** (`structured.py:617`、条件は `name != "add_field" and "field_type" in operation`) — **D-2 (5) が望む結果と同じだが `violated_declaration` が無いので、WP-2a はこの既存分岐を `unsupported_field` に載せ替えることになる。** **一方、契約 `spec/data-service-api.v1.json` の `SchemaOperationRequest.operation` enum には `alter_field` が既に載っている。** → **R-2 の `alter_field` は「既存機能への追加」ではなく「新設」である。**
- **F-2 値検証の choke point は各 peer に 1 関数ずつある。** r2db は `_check_type` (`r2db-api/src/r2db_api/structured.py:858-900`) — in-memory cell と `PostgresCell` が**同一関数を共有**し、insert / update / upsert の値と predicate 値がすべてここを通る。MitateDB は `check_declared_value` (`MitateDB-api/src/mitatedb_api/field_types.py:70-112`) — 呼び出しは **3 箇所**、`_prepare_values` (`MitateDB-api/src/mitatedb_api/cell.py:1416-1452`) の **`cell.py:1442`** と `_bind_filters` (`cell.py:1454-1514`) の **`cell.py:1502` / `:1510`** である (**v1.2 で実測に訂正。レビュー 2 M7 / m4** — v1.1 は `_bind_filters` を 1 呼び出しと数えていた)。**null が宣言型に関わらず常に受理されることは、r2db は `_check_type` の docstring が、MitateDB は `field_types.py:89-96` の本文コメントと実装が示す** (**v1.2 で訂正。レビュー 2 m2** — MitateDB 側の docstring (`field_types.py:71-86`) は null に触れておらず、「NOT NULL は本契約版の範囲外である」という文言も存在しない。実体は「SQL NULL is valid for any column regardless of its declared type -- this foundation defines no NOT NULL constraint anywhere」というコメントと `:95-96` の実装である)。**したがって `nullable` は現行挙動 (常に true) を宣言化するものであり、宣言の追加が既定の意味を変えない。**
- **F-3 フィールド宣言の正本は peer で形が違う。** r2db は **PostgreSQL の物理カラム型そのもの**が正本であり、side table を持たない — `_load_catalog` (`r2db-api/src/r2db_api/postgres.py:885-`) が `information_schema` から毎回再構築し、`_FIELD_TYPE_SQL` (`postgres.py:175-190`) が契約語彙と SQL 型を対応させる。MitateDB は**宣言型レジストリ `_mdb_field_types`** (`MitateDB-api/src/mitatedb_api/backend_postgres.py:363-370`) が正本であり、書き込みは `create_collection` (`backend_postgres.py:667-720`) と `add_field` (`:744-794`) である。**per-application upgrade の機構は両 peer に既にある** — r2db は `_r2db_platform_upgrades` (`r2db-api/migrations/0009_platform_upgrades_ledger_upgrade.sql`、`python -m r2db_api.ops upgrade-applications`)、MitateDB は `_mdb_platform_upgrades` (`MitateDB-api/migrations/0008_platform_upgrades_upgrade.sql`、`platform_upgrades.require_application_upgrades_applied` `backend_postgres.py:456-480`)。**命名規範は「platform は一回限りの migration、per-app は `_upgrade.sql` 接尾辞の script」である。**
- **F-4 `EntityDescriptor` の生成点は各 peer 1 箇所である。** r2db は `PostgresCell.catalog()` (`r2db-api/src/r2db_api/postgres.py:851-883`)、MitateDB は `ApplicationRuntime.catalog()` (`MitateDB-api/src/mitatedb_api/cell.py:785-811`、`_backend.all_field_types()` を引く)。**`FieldDescriptor` という独立型は無く、`field_types: {name: type}` の map である。** 1.6.0 の `EntityDescriptor.field_types.description` は「catalog は nullability・default・required を宣言しない。**後の版が schema 操作にその概念を与えるなら、同じ版で catalog にも与える**」と明記している (契約 `definitions.EntityDescriptor`)。→ **1.7.0 がこの約束を履行する版である。**
- **F-5 `schema_objects` の数え方が peer で違う。** r2db は **entity 1 + field 数 + index 数**を数え (`r2db-api/src/r2db_api/postgres.py:1620-1627`、`structured.py:1467` / `:1478`、既定値 1000 は `r2db-api/src/r2db_api/limits.py:12-20` の `schema_objects` 行。**v1.2 で実測に訂正。レビュー 2 m4**)、MitateDB は **`information_schema` のテーブル数のみ**を数える (`MitateDB-api/src/mitatedb_api/backend_postgres.py:494-507`、既定 128 は `MitateDB-api/src/mitatedb_api/config.py:35`)。MitateDB は field 数を**別軸 `max_fields`** として `ValidationError` で扱う (`cell.py:617` / `:708`)。**したがって契約 `limits.classes` の `schema_objects` の意味が peer で一致していない** — P-6 (peer 同型性) の既存の差である。**enum 要素数をこの class に載せるか否かが §5 U-1 の分岐点である。**

#### (b) エラー details (R-3) の材料

- **F-6 既存行走査の置き場所は peer で違う (v1.2 で実測に訂正。レビュー 2 M3、監督裁定 S-g)。** r2db は `apply_schema` (`r2db-api/src/r2db_api/postgres.py:1617-1729`) が `with conn.transaction():` (`:1617`) で DDL 全体を包むので、**既存行走査を同一トランザクションに置ける位置が既にある。** **MitateDB は pre-flight のカタログ読み取りが DDL とは別トランザクションであり、その間に commit する** — `cell.py:707` の `self._backend.field_domains(collection)` は `MitateDB-api/src/mitatedb_api/backend_postgres.py:563` で `self._developer.commit()` し、`cell.py:624` の `self._backend.schema_count()` も `backend_postgres.py:506` で commit する。DDL はその後に**別のトランザクション**として `backend_postgres.py:705-720` / `:762-774` で開かれ、末尾 (`:720` / `:774`) で commit する。**唯一の直列化はプロセス内の `self._lock` (`cell.py:716` ほか) であり、pre-flight 読み取りを跨がない。** → **`alter_field` の既存行走査を同一トランザクションに入れるには、MitateDB は schema 経路のトランザクション境界そのものを変える必要がある** (D-2 実装の形 3)。**なお MitateDB の developer 接続の SELECT 権限は解決済みである** — developer role は `public` schema の所有者であり (`MitateDB-api/migrations/0003_provision_application.sql:112` の `ALTER SCHEMA public OWNER TO :"developer_role";`)、application table はすべてその接続で作られるので**所有者として SELECT を持つ。明示 GRANT は存在しないが不要である。**
- **F-7 エラー details の現行形は peer で大きく違う (`alter_field` の present-denial は `MitateDB-api/src/mitatedb_api/http.py:941-946`。v1.2 で実測に訂正、レビュー 2 m4)。** r2db は `fail()` (`r2db-api/src/r2db_api/errors.py:22`) が details を受け取り、実際に載るのは `field` (多数)、`LIMIT_EXCEEDED` の `resource` / `limit_class` / `limit` の 3 key、`IDENTIFIER_INVALID` の `field` のみ、`PRECONDITION_FAILED` は details 無しである。**MitateDB は `ValidationError` / `CapabilityError` が details 属性そのものを持たない** (`MitateDB-api/src/mitatedb_api/errors.py:43-44` / `:188-205`。**105 箇所の `ValidationError` 呼び出しに details 引数は 0 件**)。details を持つのは `ResourceLimitError` (`limit_class`) と `DestructiveConfirmationRequired` (4 key) だけである。**さらに MitateDB は `IDENTIFIER_INVALID` を発行しない** (`MitateDB-api/src/mitatedb_api/identifiers.py:30` が `ValidationError` に畳み込み、`http.py:88-96` がその判断を明記している) **し、`PRECONDITION_FAILED` も発行しない** (`revision_preconditions` が `unavailable`、`cell.py:1755`)。**`declared_type` / `observed_type` という名前は両 peer のどこにも存在しない。**
- **F-8 契約に details の固定 key を置く前例は 2 つある。** (i) `errors.details_vocabulary` — `LIMIT_EXCEEDED.limit_class` を必須と定め、`common_optional` に `audited` / `attribution` / `futility` を置き、`open` 節で「details は閉じた語彙ではない。**SI-10 の非開示要求は key 名に関わらず details の内容を制約する**」と述べる。(ii) `destructive_confirmation.denial.details_keys` + `details_rules` — **4 key すべてが全 denial に present であること**を規則として書く方式である。**`ErrorResponse` の JSON Schema は契約に無い** (`errors.shape` は型名の羅列にすぎない)。
- **F-9 L6-9 の二重検証の現況。** 主検証は choke point 層 (F-2) であり、defence-in-depth は backend 層である — r2db は `r2db-api/src/r2db_api/postgres.py:1249` の汎用 `VALIDATION_FAILED` (details 無し)、MitateDB は `_check_domain` (`MitateDB-api/src/mitatedb_api/backend_postgres.py:299-329`、details 無し。**v1.2 で実測に訂正。レビュー 2 m4**)。**層の区別は現在 message 文字列だけで付いている** (`docs/design/PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md:805-806`、L6-14 は `:832`)。
- **F-10 HTTP 整形の形。** r2db は `.problem()` (`r2db-api/src/r2db_api/errors.py:18-19`) が in-process / HTTP 共通で details をそのまま出す。MitateDB は details については in-process (`MitateDB-api/conformance/conformance_adapter_mitatedb.py:2260-2263`) と HTTP (`MitateDB-api/src/mitatedb_api/http.py:188-189`) が同一機構だが、**message は HTTP 層の `_problem_for_exception` (`http.py:152-189`) が code 別の固定文言に置換する。**
- **F-11 conformance の SI-10 走査は現在 `DESTRUCTIVE_CONFIRMATION_REQUIRED` の details しか見ていない** (`conformance-tests/test_c04_unsupported_and_safe_errors.py:29-45`、`conformance-tests/conftest.py:517-546` の `assert_no_unsafe_diagnostic_content`)。**`conformance-tests/schema_check.py` は discovery / catalog 文書専用であり、error 応答は対象外である。**

#### (c) 要求経路と原子性 (R-4 / R-5) の材料

- **F-12 mutation / schema の経路 (r2db)**: `r2db-api/src/r2db_api/http.py:324-341` の `post_mutate` / `:352-359` の `post_schema` → `r2db-api/src/r2db_api/service.py:1028-1058` の `_mutate_outcome` (`limits.check_request` は `:1037`、`check_depth` は `:1038`) / `:1060-1084` の schema (developer 判定 `:1070` が先) → in-memory の `ApplicationCell.transact` (`structured.py:1236-1289`。**deepcopy が BEGIN、except での restore が ROLLBACK に当たる**) / `PostgresCell.transact` (`postgres.py:1122-1206`、`with conn.transaction():` は `:1147`) / `apply_schema` (`postgres.py:1606-1729`、tx は `:1617`)。rate / concurrency は `DataService._slot` (`service.py:1132-1144`)。**監査 emit は `DataService._event` (`service.py:1165-1236`) の単一 dispatch であり、durable な pre-commit hook は `_make_audit_hook` (`service.py:1256-1269`) が作る。**
- **F-13 mutation / schema の経路 (MitateDB)**: `MitateDB-api/src/mitatedb_api/http.py:672-708` の `post_mutate` / `:741-783` の `post_cross_entity_mutate` (**実装済み**) / `:803-946` の `post_schema` → `ApplicationCell._limit_gate` (`cell.py:507-542`。順序は rate → concurrency → request_bytes → operation_depth → deadline) → `transact` (`cell.py:1110-1333`。`batch_items` は `:1162`、`batch_entities` は `:1164`、**pass1 の `_plan_operation` (`:993-1072`) は DML の副作用を持たない — ただしカタログ読み取り (`field_domains` / `schema_revision`) は別の developer 接続で走り、そこで commit する** (`cell.py:1003-1017` の docstring が明記。**v1.2 で訂正。レビュー 2 m3** — dry_run の「外部可視の状態変化 0」には影響しないが、根拠文としては不正確だった)、BEGIN は `:1204`、COMMIT は `:1240`、ROLLBACK の実行は `:1295` (`except` 節の範囲は `:1241-1311`。**v1.2 で実測に訂正。レビュー 2 m4**))。**schema 操作は `transact` を経由せず、`create_entity` (`cell.py:599-649`) / `add_field` (`cell.py:674-722`) が個別に limit gate → backend DDL を行う。** backend の begin/commit/rollback は `backend_sqlite.py:475-497` と `backend_postgres.py:1142-1162`。監査 hook は `_make_audit_hook` (`cell.py:544-555`) → `AuditRouter`。
- **F-14 監査 pre_commit hook は両 peer とも「データ tx とは別コネクションで即 commit する」形である** (`r2db-api/src/r2db_api/audit_hook.py:1-53` の call contract、`r2db-api/src/r2db_api/postgres.py:1173-1175` / `:1710-1712`、`MitateDB-api/src/mitatedb_api/backend_postgres.py:717-720` / `:771-774`)。**データ tx を rollback しても監査行は残る。** → **`dry_run` は「rollback するから監査も消える」形にはならない。`pre_commit()` の呼び出し自体を分岐で抑止する必要がある。**
- **F-15 PostgreSQL の id 採番 (`GENERATED ALWAYS AS IDENTITY`) は rollback で巻き戻らない。** `r2db-api/src/r2db_api/structured.py:1105-1116` のコメントが、**in-memory 側も同じ非トランザクショナル挙動を鏡写しにしている**ことと `address_reuse` が `"never"` であることを明記している。→ **dry_run は採番を消費し得る。**
- **F-16 schema revision の持ち方 (v1.1 で訂正。レビュー 1 B1)。** r2db は in-memory が `schema_revision` (`r2db-api/src/r2db_api/structured.py:1105`、プロセス内)、Postgres が `_read_schema_revision` / `_bump_revision` (`r2db-api/src/r2db_api/postgres.py:1900-1935`。**DDL と同一 tx、永続**)。MitateDB Postgres は `_mdb_schema_revision` (`MitateDB-api/src/mitatedb_api/backend_postgres.py:361` / `:646-661`、**永続**)。**MitateDB の SQLite backend は `sqlite3.connect(":memory:", check_same_thread=False)` (`MitateDB-api/src/mitatedb_api/backend_sqlite.py:87`) の 1 形しか持たず、リポジトリ全体で `sqlite3.connect` はこの 1 箇所だけである** — したがって**この backend はファイル永続 backend ではなくプロセス内 backend であり**、`_schema_revision` (`backend_sqlite.py:95` / `:207` / `:250`) も宣言型レジストリ `_declared_types` (`backend_sqlite.py:107` / `:218` / `:253`) も**プロセス内の Python 構造である**。**接続断で DB 全体が消えるので「永続する backend で revision だけが揮発する」という食い違いは存在せず、r2db の in-memory `ApplicationCell` と同列である。** **v1.0 はこれを「ファイルに永続する backend」と誤読しており、その誤読の上に立っていた D-10 は撤回した** (§3 D-10、台帳 L9-6)。`SchemaOperationResult.revision` (string) は契約に既にある。
- **F-17 `request_id` の現況。** 両 peer とも **HTTP 層でサーバが生成する** (`r2db-api/src/r2db_api/http.py:133` の uuid4、`MitateDB-api/src/mitatedb_api/http.py:231`)。r2db の監査 `_event` には `request_id` が載る (`service.py:1165-1198`)。**client 提供値を監査イベントに載せた前例は無い。** **成功応答 (`QueryResult` / `MutationResult` / `SchemaOperationResult`) に `request_id` は無い。** **全 request / response schema は `additionalProperties: false` であり、両 peer の `_check_object_shape` (`r2db-api/src/r2db_api/http.py:76-97`、`MitateDB-api/src/mitatedb_api/http.py:319`) が未知フィールドを拒否する。** → **新フィールドは契約 JSON (3 複製) の変更が先行必須である。**

#### (d) bound (R-6) の材料

- **F-18 limits の現況。** r2db は `r2db-api/src/r2db_api/limits.py:12-20` が既定値を持ち、**配備時の env override は無い** (`main.py` が参照しない。control-plane 側だけは `R2DB_CONTROL_LIMIT_*` で上書きできる)。MitateDB は `MitateDB-api/src/mitatedb_api/config.py:20-220` が `MITATEDB_MAX_*` env で上書きできる。**3 class の検査位置**は次のとおりである。`batch_items`: r2db `structured.py:1243` / `postgres.py:1129`、MitateDB `cell.py:1162`。`result_items`: r2db は query が `structured.py:1198`、mutate の affected が逐次 `structured.py:1272` / `postgres.py:1163`、MitateDB は read が `cell.py:834-837`。`execution_ms`: r2db は deadline 行 `service.py:999` (query) / `:1039` (mutate) / `:1074` (schema) の 3 箇所と `postgres._set_timeouts` (`:1943-1959`)、MitateDB は `_limit_gate` の deadline (`cell.py:541`) と `backend_sqlite.py:24-35` / `backend_postgres.py:1123-1157` (**行番号は v1.2 で実測に訂正。レビュー 2 m4**)。

#### (e) idempotency (R-5) の材料

- **F-19 idempotency の現況。** 契約は `capability_status.defined.idempotency` を「Request-level idempotency_key deduplication with finite retention bounds.」と定義し、`limits.classes` に `idempotency_entries` / `idempotency_retention_ms` (example_profile は 10000 / 86400000) を持ち、`MutationRequest` / `ScopedMutationRequest` に `idempotency_key` (string、maxLength 128) を**既に持つ**。**`SchemaOperationRequest` には無い。** `transactions.retry` が `idempotency_key` に言及し、`audit.forbidden_fields` は `["credential","token","password","secret","private_key","sql","row_value"]` である (**契約テキストのみ。コード側でこの名前を引く経路は両 peer とも無い**)。**両 peer とも `unavailable`** (`r2db-api/src/r2db_api/service.py:917`、`MitateDB-api/src/mitatedb_api/cell.py:1754`) であり、key 付き要求を `CAPABILITY_UNSUPPORTED` で拒否する (r2db は `http.py:331` と `structured.py:205-206`、MitateDB は `http.py:684-685` と `:768-769`)。**C-07 (ii) (`conformance-tests/test_c07_atomicity_and_retry.py:106-158`) は `unavailable` 枝 (4/4 plug) と `retry_same_result` 枝 (0/4 plug) の exhaustive な if/else であり、肯定側は一度も実行されていない** (L7-8、フェーズ7 設計 `:781`)。port の `BatchOperation` が `idempotency_key` を運ぶ (裁定 S-4、port v1.11、`conformance-tests/adapter.py:757`)。

#### (f) 契約と改版 (R-8 / R-10 / 版フリップ) の材料

- **F-20 契約 JSON の構造 (`control_endpoints` の件数を v1.1 で 10 → 12 に訂正。レビュー 1 m1。付録 A (i) の実測 19 行 = 7 + 12 と一致させた)。** `endpoints` 7 要素 / `control_endpoints` **12 要素**はいずれも `{method, path, auth, request, response, semantics}` のみを持ち、**`auth` は自然文である** (`"runtime or developer"` 等)。**role 配列も、destructive 印も、atomicity 印も、返し得る error code も持たない。** destructive は `destructive_confirmation.applies_to` の**擬似式の文字列配列**、atomicity は `transactions` 節、error code は `errors.codes` の全域 1 本、能力依存は `capability_status.defined` と `versioning.version_binding` の自然文に分散している。`schemas` は 20 件、`definitions` は 6 件。**`tools/` に契約から派生物を生成するものは無い** (現在の `tools/` は `check_collection_floor.py` / `deploy_smoke.py` / `perf_baseline.py` / `public_value_scan.py` / `rewrite_hash_refs.py`)。**`CapabilityDocument` への optional 追加の前例は `surfaces` (1.6.0) であり、`required` 配列は不変だった。**
- **F-21 `versioning.version_binding` は 10,269 字 (契約全体の 13.32%) の単一散文である。** 版ごとに "Only an implementation declaring 1.X.0 or higher additionally claims conformance to the obligations 1.X.0 introduced (subordinate ruling N)." で区切られ、無条件 (a)(b)(c) と条件付き (1)(2)(3) の列挙、"N of those obligations are unconditional" の定型文、末尾に retroactive-denial の 4 文が並ぶ。**`conformance-tests/test_contract.py:343-360` が件数を assert する。**
- **F-22 PIN の実数。** `conformance-tests/test_contract.py` の `^PIN_` 定数は **15 件** (行 433〜591。1.4.0 obligation B addendum、1.5.0 sentence 1-4、1.6.0 item 1/2/3、1.6.0 version_binding paragraph、upsert sentence before/after、retroactive denial row 1.1.0/1.2.0/1.3.0/1.4.0)。**フェーズ8 付録 A §A.2c の「test-pinned: 18」は 29 マーカー値のうち何らかのテスト照合がある値の個数であり、`PIN_` 定数の個数 (15) とは集計軸が違う。** **R-10 (B) の再確定対象は「依頼者確定文言として PIN されている値」= 付録 A の 18 値 (`PIN_` 定数 15 件を含む) とする。** **ただし剥離によって実際に不一致になる `PIN_` 定数は 1 件だけである (v1.2 で追記。レビュー 2 M1 の実測、監督裁定 S-e)** — **`PIN_1_5_0_SENTENCE_1` (`conformance-tests/test_contract.py:447-452`) のみ**であり、この定数は**依頼者確定文言そのものの内側に provenance 接頭辞 (`Since 1.5.0 (subordinate ruling 10, item 1, conditional): `) を含み**、**3 つの json_path に対して照合される** (`test_contract.py:510` が `versioning.version_binding` = unstripped、`:519` が `audit.query_operation_vocabulary` / `audit.query_target_kind_vocabulary` = 剥離対象)。**残り 14 定数は剥離後も一致し続ける** — 照合先が `versioning.version_binding` (unstripped)、`structured_operations.upsert` (剥離対象外)、または接頭辞を含まない本文だからである。**帰結は D-9 手順 5 と §6.3 に書く。**
- **F-23 `spec/CONTRACT_HISTORY.md` は 29 anchor を持つ。** 形式は `## <json_path>` + Value (契約値の全文逐語 quote) + Subordinate ruling (`従属判断 N`) + Introduced in。register は `conformance-tests/test_contract_history_register.py` の 7 本 (scanner が 1 件以上 `:186`、heading 集合一致 `:198`、重複なし `:214`、非空 `:221`、ruling 実在 `:228`、quote の byte 一致 `:305`、Since 照合 `:352` の関数内 `:388` の `assert checked == 17`)。**スキャナの正規表現表 `_PATTERNS` は `conformance-tests/test_contract_history_register.py:64-79` である (v1.2 で実測に訂正。レビュー 2 m4。v1.1 は `:68-81` と書いていた)。****接頭辞を剥がすと確実に赤になるのは、heading 集合一致・byte 一致・Since 照合 (checked 件数)・`test_contract.py` の PIN 群 (in-substring) である。** 両 peer の packaged copy byte 一致テスト (`r2db-api/tests/test_http.py:286-289`、`MitateDB-api/tests/test_http.py:155-158`。**assert 行は `:289` / `:158` である。v1.2 で実測に訂正、レビュー 2 m4**) は 3 複製を同時更新すれば緑のままである。**前文の limitation 3 が「29 値はすべて現行規範文と同居しており、規範文を書き換えずにはマーカーを外せない」と明記している。**
- **F-24 契約改版の前例 (1.5.0 → 1.6.0)。** `bb86a37` が契約 JSON 1.6.0 + CCR 従属判断 11 + 両 packaged copy + port v1.10 + C-19 + PIN を 1 コミットで入れ (**peer は 1.5.0 宣言のまま、新フィールドは provisional gate で拒否**)、その後 `36e6d35`「r2db declares 1.6.0」、`1b87b38`「MitateDB declares 1.6.0 … vacuity guard and port self-report removed」と **peer ごとに版フリップのコミットを分けている** (`version_binding` 末尾の「A peer's version-flip … must land in the same commit as the real behavior change it claims」に整合)。**従属判断の番号は 8→1.3.0、9→1.4.0、10→1.5.0、11→1.6.0 であり、1.7.0 は従属判断 12 である。**
- **F-25 3 複製の sha256 (2026-09-07 実測、フェーズ8 §A.0 と同一)** = `968d3c72415d4536c0393ce451497324c182cbc2ae9d9213e0ec6ed4444f45e6`。peer の `contract_version` 宣言箇所は r2db が `service.py:900` / `control_plane.py:725`、MitateDB が `cell.py:1737` / `control_plane.py:1403`。**C-19 が data 面と control 面の一致を assert し** (`conformance-tests/test_c19_client_self_sufficiency.py:257-259`)、**版分岐は `_semver_tuple(...) < (1,6,0)` で return する形である** (`test_c19:170` ほか)。
- **F-26 性能基準値の形式。** `tools/perf_baseline.py` と基準値はフェーズ8 設計 §11.2 (PERFRUN 行 + PERF 14 行、`--warmup 20 --n 200`)。ローカル PostgreSQL は `max_connections = 300` / `statement_timeout = 0`、`pg_db_role_setting` に残る 4 行は `wp2e2e*` / `mtdbtest*` の svc role のみ (admin role 無し)。

### 1.3 起草時に実行した件

1. **契約 JSON 3 複製の sha256 の再測** = `968d3c72415d4536c0393ce451497324c182cbc2ae9d9213e0ec6ed4444f45e6` (3 本一致)。**フェーズ8 付録 A §A.0 と同一であり、フェーズ8 完了後に契約は 1 バイトも動いていない**ことを確認した (F-25)。
2. **R-8 プロトタイプ (常設規律 5)** — 契約 JSON から操作カタログを射影する規則の逐語プロトタイプ。**出力は付録 A に転記する。** **結論: 純粋な射影で得られるのは 19 行 (endpoints 7 + control_endpoints 12) の `{method, path, auth (生文字列), request/response schema とその required/properties}` までであり、(a) role は PARTIAL (`"application"` が `security.roles` に無く、散文でしか定義されていない)、(b) destructive は PARTIAL (5 節中 3 節しか機械解決できず、しかも第 2 段の `$ref` 展開が要る。どの enum 値が destructive かは schema に印が無い)、(c) atomicity は MOSTLY NO (`transactions` に endpoint / operation のキーが無い)、(d) 返し得る code は NO (`errors.codes` は全域 1 本、endpoint ごとのキーが存在しない)、(e) 能力依存は NO (`capability_status` と `endpoints` の間に共有キー・id・`$ref` が 1 つも無い)** である。**この 5 判定が D-8 の決定の根拠そのものである。**
3. **R-10 (B) の before/after 一覧のプロトタイプ (常設規律 5 + 常設規律 4)** — 29 値それぞれについて「剥がす接頭辞 / 挿入句」と「剥がした後の値」を機械生成したもの。**出力は付録 B に転記する。依頼者への提示物そのものである** (§5 U-6)。**結論 (草案時点): 29 値の分類は `strip-prefix` 13 / `strip-insert` 12 / 両方 1 / `unstripped` 3 であり、test-pinned は 18 件** (F-22 と一致)。**確定後 (監督裁定 S-d を織り込んだ分類) は `strip-prefix` 14 / `strip-insert` 11 / 両方 1 / `unstripped` 3 である** — **#18 `schemas.AuditResult.properties.events.items.description` が `strip-insert` から「接頭辞全体の除去 + 1 語の改訂」へ変わったからである (D-9、付録 B #18 の注記)。`unstripped` の 3 件は変わらない。**

---

## 2. 守るべき条件

### 2.1 計画文書 §4 の横断条件 (P-1〜P-9) の転記

計画文書 `docs/design/ROADMAP_POST_PHASE7_V1.md` §4 の表を以下に**転記する** (再導出しない)。

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

### 2.2 本フェーズでの適用 (効く 7 条件)

**計画文書 §5 のフェーズ9 節が「守るべき条件」として名指すのは P-1 / P-3 / P-4 / P-5 / P-7 と `version_binding` の規律である。本フェーズはこれに P-6 と P-8 を加えて 7 条件を効かせる。**

- **P-1 の本フェーズでの適用**: **`plan` はサーバに何も保持させない** — 決定的トークン (request digest + schema 状態の決定的値) の再計算だけで検証する (D-4)。**`dry_run` は「実行して rollback する」形で無状態を保つ**。**`idempotency` の記録は往復をまたぐ状態だが、これは契約が既に `capability_status.defined.idempotency` と `limits.classes` の 2 class で定義済みの、有限 bound を持つ記録である** — P-1 が禁じる「保持 lock / 保持接続 / 保持トランザクション」ではない (D-5)。
- **P-2 の本フェーズでの適用**: **本フェーズの 7 項目はすべて 1 周のどこかを閉じる** — catalog を読む (R-2 の `field_constraints` 報告、R-8 の操作カタログ)、要求を作る (R-2 の制約宣言、R-6 の budget)、判定を受ける (R-3 の details 語彙、R-4 の dry_run)、安全に再送する (R-5 の idempotency、R-7 の `request_id` 相関)。**周回の外の機能は 1 つも足さない。**
- **P-3 の本フェーズでの適用**: **本フェーズが足す宣言はすべて共通条件を同時に持つ** — `field_constraints` は C-20、details 語彙は C-21、`dry_run` は C-22、`idempotency` は C-23、`budget` は C-24、`request_id` は C-25。**advisory な宣言を 1 つも足さない** — これが A-7 (自然文の正規表現解釈) と U-5 (B) (返し得る code を初版に含めない) の判断根拠である。**さらに「宣言が挙動より先に出る」ことを機構が禁じる** — 版フリップは無条件義務を入れる最後の WP と同一コミット、新 capability の gate 外しは挙動と同一コミット、無条件義務の条件テストは `xfail(strict=True)` を版宣言に条件付ける (D-1)。
- **P-4 の本フェーズでの適用**: **R-2 は「schema 操作が制約を受け取る」と「catalog が制約を報告する」を同じ版で出す。** 1.6.0 の `EntityDescriptor` 文言が「後の版が schema 操作にその概念を与えるなら同じ版で catalog にも与える」と明記しており (F-4)、**1.7.0 がその約束の履行である。** 片方だけ先行させない。
- **P-5 の本フェーズでの適用**: **新しい limit class は 1 つだけ足す** (§5 U-1 = (β) の確定により `enum_members` のみ)。**`budget` は配備値を下回る方向にのみ効き、上回る値は VALIDATION_FAILED である** (D-6)。**`rows_scanned` は含めない** (計画文書 §6 の却下済み案)。**`pattern` は含めない** (計画文書 §5 が「正規表現の計算量が SI-08 の面になる」として初版から除外している)。
- **P-6 の本フェーズでの適用**: **契約上の意味を一致させ、実現方式は platform に従わせる。** 宣言の正本は r2db が side table、MitateDB が既存 registry の列追加という**別の形**になるが (D-2)、**catalog が報告する `field_constraints` の意味・強制点 (choke point)・違反時の code と details は一致させる。** **コードは共有しない。** 同名ヘルパを置く場合のみ同型性テストの対応表に行を足す (常設規律 6)。**その行追加は監督の pair-closing commit である** (§8。v1.3、監督裁定 T-2)。
- **P-7 の本フェーズでの適用**: **契約本体に足すのは現行の意味だけであり、経緯文は companion (`spec/CONTRACT_HISTORY.md`) に置く** (D-8 の P-7 条項)。**R-10 (B) は契約本体から経緯の接頭辞を実際に減らす** — フェーズ8 の (A) が「1 hop で辿れる」に留まったのに対し、(B) が初めて契約本体を短くする (D-9)。**R-8 の派生 artifact は再生成一致テストで正本に縛る。**
- **P-8 の本フェーズでの適用**: **完了ゲートにフェーズ8 §11.2 と同形式の性能差分を添える** (§9 の 3)。**閾値は置かない。** 本フェーズは「2 フェーズ安定」の 2 フェーズ目である (計画文書 §7 の 3)。
- **`version_binding` の規律の本フェーズでの適用**: **1.7.0 の義務を網羅列挙する。** 無条件 / 条件付きの区別と件数を明記し、retroactive-denial の行を更新し、新しい 1.6.0 の行を足す (D-1 / §3 D-8 の契約文案)。

### 2.3 本フェーズ固有の制約

1. **C1 契約は 1.7.0 になる。** `spec/data-service-api.v1.json` と両 peer の packaged 複製 2 本を**同一コミットで同一バイトに**更新する。**変更はすべて additive である** — 既存キーの削除・型変更・enum 縮小・`required` 追加を行わない。**1.6.0 で有効な要求は 1.7.0 実装でもそのまま有効である** (`versioning.compatibility` の "removal or semantic change requires a new major version" に抵触しないこと)。**R-10 (B) による接頭辞剥離は「値の文字列が動く」が「意味は不変」であり、その同一性はマニフェスト逆適用後の deep-equal で機械的に示す** (D-9)。
2. **C2 新しい共通 Security Invariant は足さない** (§7 で invariant ごとに根拠を示す)。
3. **C3 開発順序**を守る: 共通要件 → 該当 SI → 共通契約 → conformance 証拠 → 実装 → 実装別テスト・統制 (CLAUDE.md)。**本フェーズでは「契約 1.7.0 の公開 (WP-1) が peer 実装 (WP-2 / WP-3) に先行する」という形でこれが現れる** (F-24 の前例と同型)。
4. **C4 完了ゲート**の集計行は `pytest -q -n 5 --dist loadgroup` の**単独実行**で取る。**設計段階では suite を回さない。**
5. **C5 常設規律 7 項目**を継承する (`docs/work-orders/WORK_ORDER_PHASE7_EVIDENCE_AND_PUBLICATION_V1.md` §0.1、フェーズ6 §0.1 の逐語継承)。特に**規律 2 (完了条件 1 項目 = 変異 1 つ)**、**規律 4 (依頼者確定文言はファイル経由で逐語複製する。docstring や文書に写すときにも掛かる** — フェーズ8 で違反 1 件が検出された、第 15 次 §4-3 の 4)、**規律 5 (静的規則・派生生成は逐語プロトタイプの後に設計へ)** — 後者に従い R-8 の射影プロトタイプを**付録 A**に、R-10 (B) の before/after 一覧を**付録 B**に添付する。
6. **C6 速度規律 5 項目**を継承する。完了ゲートは監督が単独実行し、subagent には担当ファイルの範囲だけを回させる。**ローカル PostgreSQL の `max_connections = 300` が前提である。**
7. **C7 公開規律**: 設計文書・作業指示書に実値を書かない。
8. **C8 並行作業**: WP-9 (公開ゲート) と本フェーズは触るファイルが重ならない (§8.1)。**並行 worktree を使う WP は着手前に「触るファイルの重なり 0」を実ファイル名で確認する。** **WP-1 と WP-4 のように順序で分ける WP は「重なり 0」の対象ではない** — 直列であることが担保である。
9. **C9 依頼者確定文言の再確定は 1 回にまとめる。** R-10 (B) の 18 値 (§5 U-6) と 1.7.0 の新規契約文案 (§5 U-8) は**同じ確定でまとめる** — これが R-10 (B) をフェーズ9 へ送った理由そのものである (フェーズ8 §10 L8-4)。**v1.1 でこの確定を行った** (依頼者裁定 2026-09-07 の委任に基づく監督確定。§5)。**`PIN_1_6_0_ITEM_3_FIELD_TYPES` の意味改訂 (§5 U-8 #28) も同じ確定に含まれる** — 剥離と同じ 2 json_path を触るからである。

---

## 3. 決定と根拠

**本節の D-1〜D-9 は監督確定である。** **D-10 は v1.1 で撤回した** (前提事実の誤り、レビュー 1 B1)。各 D は「決定 / 根拠 (file:line) / 実装の形 / 検査の形 / 却下した代替 (§4 への参照) / 開示事項」の順に書く。**契約に載せる候補文 (英語) は「契約文案」のブロックに明示する** — これらは**依頼者確定文言の再確定対象**であり、§5 U-8 に json_path ごとの一覧と確定を置く。

### D-1 出荷の形と版フリップの規律

#### 決定

**(1) 契約 1.7.0 は従属判断 12 として出荷する。** `spec/CCR_DISPOSITION.md` に 1 節を新設し (見出し番号 12。F-24 の番号列に続く)、契約 JSON の 3 複製を**同一コミットで同一バイトに**更新する。**F-24 の `bb86a37` 型である** — この WP は**どちらの peer の `contract_version` も動かさない**。

**(2) 1.7.0 の義務を 2 種に分ける。**

| 種別 | 内容 | 結び先 |
|---|---|---|
| **無条件義務** | **R-3 の details 語彙** (VALIDATION_FAILED / IDENTIFIER_INVALID / CAPABILITY_UNSUPPORTED を**発行するときの**形)、**R-7 の成功応答 `request_id`** | 1.7.0 を宣言すること自体 |
| **条件付き義務** | **R-2 制約宣言** (新設 capability `constraint_declarations` + 既存 `schema_operations` / `application_catalog`)、**R-4 dry_run** (新設 capability `dry_run`)、**R-5 idempotency** (既存 capability `idempotency`)、**R-6 request budget** (新設 capability `request_budget`) | "conditional on X being provided" で当該 capability に結ぶ |
| **(契約文書のみの変更。実装に義務を課さない)** | **R-10 (B) の接頭辞剥離**、**`versioning.obligations` 配列の追加**、**R-8 の構造化フィールドと派生カタログ** | — |

**3 種目は `version_binding` の義務列挙には載らない** — `version_binding` が列挙するのは「実装を縛る義務」であり、契約文書自身の整形や機械可読化は実装に何も要求しないからである。**ただし R-8 の `operation_catalog_url` を `CapabilityDocument` に足す件だけは実装が触れ得るので、`required` に入れない optional 1 項目とし、義務にもしない** (D-8)。

**(3) peer 側は WP-1 (契約公開) と同一コミットで provisional gate を置く。** 新フィールド (`dry_run` / `plan` / `budget` / `enum` / `nullable` / `field_constraints` / `SchemaOperationRequest.idempotency_key`) を **`CAPABILITY_UNSUPPORTED` として実行前に拒否する**。**理由**: packaged copy が 1.7.0 schema になると `_check_object_shape` (F-17) が新フィールドを**通してしまい**、通したうえで無視して実行すれば **P-3 違反 (宣言が真でない)** になる。**新設 capability (`constraint_declarations` / `dry_run` / `request_budget`) は同じコミットで `unavailable` として宣言に載せる** — 「宣言が正直に『無い』と言う」形である (フェーズ7 §8 の判断と同型)。**この「正直に `unavailable` と宣言する」ことを検査するのは、C-11 に WP-1 が足す逆方向 (defined ⊆ declared) の assert である (v1.3。監督裁定 T-4。§6.2 / §6.4 / §9 の 16)** — **載せなくても全条件が緑になる状態を残さない** (分岐ヘルパは capability 不在時に `"unavailable"` を既定値にするため)。

**(4) 各 peer の capability WP がその capability の gate を外す。** gate を外すコミットで、同時に **capability document の status を `enabled` にし、挙動を入れる** — **宣言と挙動は同一コミットである** (P-3)。

**(5) 各 peer の版フリップ (`contract_version` 1.6.0 → 1.7.0) は、その peer の無条件義務 (R-3 / R-7) を入れる最後の WP と同一コミットで行う。** F-24 の `36e6d35` / `1b87b38` 型である。**両 peer のフリップは完了ゲート内で連続して main にマージし、フリップ間に他のコミットを挟まない。** (「同時」の形は §5 U-7 = (A) で確定した。)

**(6) 新条件 C-20〜C-25 は「宣言分岐」型で書く。** C-07 (ii) (`conformance-tests/test_c07_atomicity_and_retry.py:106-158`) の型である — **capability が `unavailable` なら「実行前拒否 + 副作用 0」を assert し、それ以外 (`enabled` / `partial` / `planned`) なら肯定側を assert し、`observed_branch` を宣言から導いた期待と突合する** (**分岐は `status_enum` の 4 値に対して網羅である。v1.2、レビュー 2 m6**)。

**(7) 無条件義務の条件 (C-21 / C-25) は `xfail(strict=True)` を「宣言 `contract_version` < 1.7.0」に条件付けて置く。** **挙動が宣言より先に入れば XPASS で赤、宣言が先なら通常の assert が赤になる。** フェーズ8 の教訓「**機構が順序を強制する形は、規律を文章で書くより強い**」(第 15 次 §5 の最終項) をそのまま適用する。

#### 根拠 (file:line)

- 前例の 3 コミット構成: F-24 (`bb86a37` / `36e6d35` / `1b87b38`)。契約自身の規律は `versioning.version_binding` 末尾の "A peer's version-flip -- the commit that changes its own declared contract_version -- must land in the same commit as the real behavior change it claims"。
- 新フィールドが shape 検査を通ってしまうこと: `r2db-api/src/r2db_api/http.py:76-97` (`_check_object_shape`) と `:330` (`MutationRequest` に対する適用)、`MitateDB-api/src/mitatedb_api/http.py:319` と `:613` / `:652`。契約 schema はすべて `additionalProperties: false` (F-17)。
- 現行の実行前拒否の形 (provisional gate の雛形がすでにある): `r2db-api/src/r2db_api/http.py:331-332` (`idempotency_key` を `CAPABILITY_UNSUPPORTED`)、`r2db-api/src/r2db_api/structured.py:205-206`、`MitateDB-api/src/mitatedb_api/http.py:684-685` / `:768-769`。
- 宣言分岐型テストの前例: `conformance-tests/test_c07_atomicity_and_retry.py:106-158` (`_idempotency_status` による分岐と `observed_branch` の突合 `:154-158`)。
- 版分岐の書き方の前例: `conformance-tests/test_c19_client_self_sufficiency.py:170` ほかの `_semver_tuple(...) < (1,6,0)` (**文字列比較を使わない**)。

#### 実装の形

1. **WP-1 (直列、契約 JSON を触る唯一の WP)** が契約 3 複製・CCR 従属判断 12・`CONTRACT_HISTORY` + MANIFEST・PIN 書き換え + 1.7.0 PIN・`versioning.obligations`・R-8 構造化フィールド・`tools/contract_catalog.py` + `spec/OPERATION_CATALOG.json` + register・port v1.13・C-20〜C-25・`CONDITIONS.md`・**両 peer の provisional gate と新 capability の `unavailable` 宣言**を 1 つの WP で入れる (§8)。
2. **WP-2 (r2db) / WP-3 (MitateDB)** が capability ごとのサブ WP で gate を外し、挙動と宣言を同一コミットに落とす。**最後のサブ WP (2e / 3e) が R-3 + R-7 + 版フリップを持つ。**
3. **WP-4** が完了ゲートと記録を行う。

#### 検査の形

- **順序の強制**: C-21 / C-25 の `xfail(strict=True)` は `parse_semver(adapter.capability_document()["contract_version"]) < (1,7,0)` を条件にする。**変異「r2db の版フリップを R-3 実装より前のコミットに置く」→ C-21 が XPASS で赤。** **変異「R-7 を実装しないまま版フリップする」→ C-25 の assert が赤。**
- **provisional gate の load-bearing**: **変異「WP-1 の gate 行を消す」→ C-20 / C-22 / C-24 の `unavailable` 枝が「実行前拒否」を観測できず赤。**
- **3 複製の同一性**: 既存の byte 一致テスト (`r2db-api/tests/test_http.py:286-289`、`MitateDB-api/tests/test_http.py:155-158`) がそのまま担保する。**変異「1 複製だけ更新する」→ 2 本が赤。**

#### 開示事項

- **WP-1 の時点では、両 peer は 1.6.0 を宣言したまま 1.7.0 schema の契約を同梱している。** これは 1.6.0 の前例と同じ状態であり、`version_binding` の retroactive-denial 規定 (「1.6.0 を宣言する実装は 1.7.0-only の義務を遡って課されない」) がその正当性を与える。**その規定文そのものを 1.7.0 が足す**ので、WP-1 は自分を正当化する文を自分で置くことになる — **これは 1.6.0 が 1.5.0 に対して行ったことと同型であり、新しい形ではない。**
- **`constraint_declarations` を新設 capability にする以上、`capability_status.defined` に 3 語 (`constraint_declarations` / `dry_run` / `request_budget`) が増える。** 現行 11 語 → **14 語**である。**C-12 (capability agreement) の駆動集合が自動的に広がる。**

---

### D-2 R-2 制約宣言 (enum / nullable) と `alter_field` の新設

#### 決定

**(1) 宣言の形は `field_type` / `field_types` の前例を鏡写しにする。**

- **`create_entity`**: `field_constraints: {name: {enum?: [...], nullable?: bool}}`。**部分可** (`fields` の一部だけを名指してよい)。**省略 = 制約なし。**
- **`add_field` / `alter_field`**: top-level の `enum` / `nullable`。
- **`EntityDescriptor`**: `field_constraints` を **fields 全体に対して総計 (total)** で報告する — `{name: {nullable: bool, enum?: [...]}}`。**`nullable` は全 field に必ず載り、`enum` は宣言された field にだけ載る。**

**この「要求は部分・catalog は総計」という非対称は 1.6.0 の `field_types` がすでに採った形である** (契約 `SchemaOperationRequest.field_types.description`: "the request's object may be partial … while the catalog's object is always total over that entity's own fields")。**1.7.0 は同じ規則を `field_constraints` に適用する。**

**(2) 意味を次のとおり固定する。**

- **`nullable` の既定は `true`** (= 現行挙動。F-2 の「null は宣言型に関わらず常に受理」を宣言化する)。
- **`nullable: false` の field は insert で非 null 値が必須である。** 欠落は違反であり、そのとき `observed_type` は **`absent`** である。**update / upsert で null を書けない。**
- **`enum` は非 null 値に対する許容値の閉集合である。** 要素は **field の宣言型 (`string` / `integer` / `number` / `boolean` のいずれか) の値のみ**であり、**`object` / `array` / `json` の field には宣言できない** (VALIDATION_FAILED)。**重複なし・空でない。**
- **null の可否は `nullable` が決め、`enum` は関与しない。** `nullable: true` かつ `enum` を持つ field は、null か enum の要素かのいずれかを取る。
- **query の predicate 値は `enum` を検査しない。** 読み取りは制約の対象外であり、**値が集合外なら単に一致しない**だけである。

**(3) 強制点は 2 つであり、いずれも書き込み経路にのみ効く (v1.1 で明確化。レビュー 1 B2 / B3、監督裁定 R-b / R-c)。**

- **(i) 値ごとの検査 (型 / `enum` / null 書き込み) は choke point である。** F-2 の 2 関数に **`constraints=None` の明示引数**を足す。**新シグネチャを逐語で固定する (v1.2。レビュー 2 m11 — 現行はどちらも `*` を持たないので、キーワード専用化も本フェーズの変更に含まれる)**:
  - r2db: 現行 `def _check_type(value: Any, field_type: str | None, field_name: str) -> None:` (`r2db-api/src/r2db_api/structured.py:858`) → **`def _check_type(value: Any, field_type: str | None, field_name: str, *, constraints: FieldConstraints | None = None) -> None:`**
  - MitateDB: 現行 `def check_declared_value(value: Any, declared_type: "str | None") -> None:` (`MitateDB-api/src/mitatedb_api/field_types.py:70`) → **`def check_declared_value(value: Any, declared_type: "str | None", *, constraints: "FieldConstraints | None" = None) -> None:`**
  - **`enum` / `nullable` を検査するのは `constraints` を渡された呼び出しだけである。**
- **呼び出し 8 箇所を全列挙し、どれが `constraints` を渡すかを設計で固定する (v1.2 で追加。レビュー 2 M7、監督裁定 S-k)。** **分岐の位置と引数名を設計で固定して実装者裁量にしない** (P-6)。

| peer | file:line | 経路 | `constraints` |
|---|---|---|---|
| r2db | `r2db-api/src/r2db_api/structured.py:949` | predicate (`in` の要素) | **渡さない** |
| r2db | `r2db-api/src/r2db_api/structured.py:951` | predicate (スカラ) | **渡さない** |
| r2db | `r2db-api/src/r2db_api/structured.py:1298` | in-memory **insert** | **渡す** |
| r2db | `r2db-api/src/r2db_api/structured.py:1314` | in-memory **update** | **渡す** |
| r2db | `r2db-api/src/r2db_api/structured.py:1392` | in-memory **upsert** | **渡す** |
| r2db | `r2db-api/src/r2db_api/postgres.py:1281` | Postgres **insert** | **渡す** |
| r2db | `r2db-api/src/r2db_api/postgres.py:1296` | Postgres **update** | **渡す** |
| r2db | `r2db-api/src/r2db_api/postgres.py:1471` | Postgres **upsert** | **渡す** |
| MitateDB | `MitateDB-api/src/mitatedb_api/cell.py:1442` (`_prepare_values`) | 書き込み値の全経路 (insert / update / upsert / batch) | **渡す** |
| MitateDB | `MitateDB-api/src/mitatedb_api/cell.py:1502` (`_bind_filters`、`in` の要素) | predicate | **渡さない** |
| MitateDB | `MitateDB-api/src/mitatedb_api/cell.py:1510` (`_bind_filters`、スカラ) | predicate | **渡さない** |

**r2db の書き込み側は 6 箇所すべてが `constraints` を渡す — 渡さないのは `structured.py:949` / `:951` の 2 箇所だけである。** **MitateDB は書き込み側が `_prepare_values` の 1 箇所に集約されており (insert / update / upsert / batch のすべてがそこを通る)、predicate 側の 2 箇所には渡さない。** **`_apply_upsert` 経由の 2 呼び出し (`structured.py:1392` / `postgres.py:1471`) を落とすと、upsert 経由で `enum` 制約を回避できる状態が生まれる** — **C-20 の `enum` leg / `nullable` leg を insert / update / upsert の 3 経路すべてで観測することでこれを赤にする** (§6.2)。**型検査は従来どおり全経路で効く。** **これは D-2 (2) の「query の predicate 値は `enum` を検査しない」を実装位置で担保する形である。**
- **(ii) `nullable: false` の欠落検査は operation 単位で、`insert` にのみ掛ける。** choke point は値を 1 個ずつ受け取る関数であり、**欠落した field についてはそもそも呼ばれない**ので、この検査は choke point では書けない。位置を設計で固定する — **r2db は in-memory の insert 分岐 (`r2db-api/src/r2db_api/structured.py:1296`、値検査は `:1298`) と Postgres の insert 分岐 (`r2db-api/src/r2db_api/postgres.py:1277`、値検査は `:1281`) の値検査の直前** (**行番号は v1.2 で実測に訂正。レビュー 2 m4**)、**MitateDB は `_plan_operation` の insert 分岐 (`MitateDB-api/src/mitatedb_api/cell.py:1034-1046`、`_prepare_values` 呼び出しの直前)** である。評価するのは `declared_non_nullable - set(values)` であり、**両 peer とも検査順序を「欠落検査 → 値検査」に揃える。** 違反時の `observed_type` は **`absent`** である。
- **`update` / `upsert` の欠落は違反ではない** — 値を書かないことは既存値を変えないことであり、`nullable: false` が禁じるのは「null を書くこと」と「insert で値を持たない行を作ること」である。**ただし insert に解決した `upsert` は insert と同じ規則で拒否される。**
- **backend 層の物理制約 (NOT NULL / CHECK) は足さない** (§4 A-1)。

**(4) 宣言の正本は peer ごと・backend ごとに置く (P-6: 意味は一致、実現は platform に従う。v1.1 で MitateDB 側を backend ごとに書き分けた。レビュー 1 B1、監督裁定 R-a)。**

- **r2db (Postgres)**: application DB に side table **`_r2db_field_constraints`** を新設する。per-application upgrade script (`r2db-api/migrations/00xx_field_constraints_upgrade.sql`) を置き、`python -m r2db_api.ops upgrade-applications` の経路で適用する (F-3 の命名規範)。**型は引き続き `information_schema` から読み、制約だけを side table から読む。**
- **r2db (in-memory 参照 cell)**: `ApplicationCell` のプロセス内構造に制約を持つ (`structured.py` の既存 schema 保持と同じ場所)。**upgrade script は要らない** — プロセス内に永続化する対象が無い。
- **MitateDB (Postgres backend)**: 既存の宣言型レジストリ **`_mdb_field_types` に列を足す** (`MitateDB-api/src/mitatedb_api/backend_postgres.py:363-370`)。同じく per-application upgrade script で適用する。
- **MitateDB (SQLite backend)**: **この backend は `:memory:` のプロセス内 backend であり、宣言型レジストリ自体が Python の dict `_declared_types` (`MitateDB-api/src/mitatedb_api/backend_sqlite.py:107`) である** (F-16)。**制約も `_declared_types` と同じプロセス内構造に持つ。** **upgrade script は要らない。**
- **catalog はどの backend でも「宣言 registry」から報告する** — 物理制約を読み戻して報告する形は採らない (A-1 と同じ理由)。

**(5) `alter_field` の 1.7.0 の意味を「1 field の enum / nullable の再宣言」と定める。** enum の設定・置換・解除、`nullable` の切替である。**`field_type` の再宣言は 1.7.0 では定義しない** — `alter_field` に `field_type` を載せた要求は `VALIDATION_FAILED`、`violated_declaration = unsupported_field` である (§4 A-2)。

**(6) 既存行が新宣言に反するなら実行前検証で全件拒否する。** **同一トランザクション内で、DDL / registry 更新の前に違反行の存在を検査し、1 行でもあれば `CONFLICT` で rollback する。** details は `field` と `violated_declaration ∈ {enum, nullable}` であり、**行値も件数も載せない** (SI-10)。**成功した `alter_field` は schema_revision を進め、拒否された `alter_field` は進めない** — **C-20 (6) は「行も catalog も 1 つも変わっていない」に加えて「拒否時に revision が進んでいない」を assert する (v1.2 で追加。レビュー 2 M3、監督裁定 S-g)。**

**(7) enum の上限は §5 U-1 = (β) で確定した** — `limits.classes` に新 class **`enum_members`** (field あたりの enum 要素数の上限) を足し、`example_profile` は **64** とする。**要素長は `request_bytes` に委ねる。** 契約文案は下記 (#4) である。

#### 契約文案 (英語)

**`schemas.SchemaOperationRequest.properties.field_constraints.description`**:

> `field_constraints` declares, per field, the two constraints this version defines: `nullable` (whether that field accepts a null value) and `enum` (the closed set of non-null values that field accepts). On `create_entity` it is an object keyed by field name and may be partial -- any name in `fields` it omits is created with no `enum` and `nullable: true`. On `add_field` and `alter_field` the same two constraints are carried as the request's own top-level `enum` and `nullable`, for the single field the operation names. `nullable` defaults to true, which is what a field created before this version, or created without the key, already is: this names an existing default rather than introducing a new one. A field declared `nullable: false` requires a non-null value on `insert` -- an operation that omits it is refused -- and cannot be set to null by `update` or `upsert`. An `upsert` that resolves to an insert is refused on the same rule; an `upsert` that resolves to an update is not, because it writes no value to that field. `enum` constrains non-null values only; whether null is accepted is decided by `nullable` alone, and a field may declare both. An `enum` is a non-empty list of distinct values, each of the field's own declared type, and is declarable only on a field whose type is `string`, `integer`, `number` or `boolean`: an `enum` on an `object`, `array` or `json` field, an empty or duplicated `enum`, an `enum` member outside the field's declared type, a `field_constraints` naming a field the request's own `fields` does not name, or a `field_constraints` sent without `fields`, each fails `VALIDATION_FAILED`; none of them is silently ignored. Constraints bind writes only: a query predicate is never refused for carrying a value outside a field's `enum` -- such a value simply matches no row.

**`schemas.SchemaOperationRequest.properties.operation` (`alter_field` の意味づけ、`structured_operations` 側に置く場合も同文)**:

> `alter_field` redeclares the constraints of one existing field: it sets, replaces or clears that field's `enum`, and switches its `nullable`. It does not redeclare that field's type -- an `alter_field` carrying `field_type` fails `VALIDATION_FAILED` -- because converting values already stored under one type into another is not defined by this version. Before it changes anything, an `alter_field` verifies every existing row of the entity against the constraints it would establish, within the same transaction as the change itself; where even one row would violate them, the whole operation is refused with `CONFLICT` and nothing is changed. The denial names the field and which declaration it would violate, and never the offending values, nor how many rows there are. A committed `alter_field` advances the entity's schema revision.

**`definitions.EntityDescriptor.properties.field_constraints.description`**:

> `field_constraints` reports, for every one of this entity's own `fields`, the constraints currently in force on it: `nullable`, always present, and `enum`, present only on a field that declares one. Like `field_types`, and unlike the request-side object of the same name, this object is always total over that entity's own `fields`. What a client declared -- through `SchemaOperationRequest.field_constraints` on `create_entity`, or `enum`/`nullable` on `add_field` or `alter_field` -- is what the catalog reports back, and a field for which nothing was declared reports `nullable: true` and no `enum`. This is the same-version catalog reporting the 1.6.0 `field_types` description reserves for whichever later version gives schema operations a notion of nullability: this is that version, and the notion it gives is exactly these two constraints -- not default values, and no notion of a required field beyond what `nullable: false` itself requires on `insert`.

**`limits.classes` への `enum_members` 追加と `limits.example_profile` への値追加 (§5 U-1 = (β) の確定。v1.1)**:

- `limits.classes` に **`enum_members`** の 1 語を足す (現行 16 語 → 17 語)。
- `limits.example_profile` に **`enum_members: 64`** を足す。**`example_profile` は現在 15 値であり `audit_requests_per_minute` を欠いている** — この既存の欠落は本フェーズでは埋めず、**「`example_profile` は `classes` の全 class を網羅しない例示である」ことを台帳 (L9-12) に記録する** (レビュー 1 m10)。
- 意味記述 (`limits.enum_members`):

> `enum_members` bounds how many members one field's declared `enum` may carry. It counts members, not bytes: the length of any single member is bounded by `request_bytes` on the schema operation that declares it, as every other request-carried string is. A `create_entity`, `add_field` or `alter_field` declaring an `enum` with more members than this deployment's own declared value is refused with `LIMIT_EXCEEDED` and `details.limit_class: enum_members`, before anything is created or altered. The bound is per field: an entity may declare an `enum` on every one of its fields, each within this bound, subject to `schema_objects` as before.

**`definitions.EntityDescriptor.properties.field_types.description` / `schemas.SchemaOperationRequest.properties.field_types.description` の当該 1 文の同ラベル改訂 (v1.1 で追加。レビュー 1 B4、監督裁定 R-d。§5 U-8 #28)**:

現行の PIN 文言 (`PIN_1_6_0_ITEM_3_FIELD_TYPES`、`conformance-tests/test_contract.py:554`、2 json_path に逐語で同居) は「the catalog … declares neither nullability, nor default values, nor whether a field is required」と述べており、**`field_constraints.nullable` を全 field に載せる 1.7.0 では偽になる。** **確定した改訂文は次のとおりである** (2 json_path とも同一文。**剥離後の PIN 定数はこの文を含む形に書き換える**):

> The catalog reports only facts this contract's own schema operations can establish: nullability and enum membership through field_constraints, and neither default values nor a notion of required distinct from nullable: false, because no schema operation defined here establishes either; a later version that gives schema operations such a notion gives it to the catalog in that same version.

#### 根拠 (file:line)

- `alter_field` が enum に在り実装に無いこと: `r2db-api/src/r2db_api/structured.py:761`、`r2db-api/src/r2db_api/service.py:885` / `:914`、`MitateDB-api/src/mitatedb_api/http.py:941-946` (F-1)。
- choke point が 1 関数ずつであること: `r2db-api/src/r2db_api/structured.py:858-900`、`MitateDB-api/src/mitatedb_api/field_types.py:70-112` と呼び出し 3 箇所 `MitateDB-api/src/mitatedb_api/cell.py:1442` / `:1502` / `:1510` (F-2)。**null が宣言型に関わらず常に受理されること** (r2db は `_check_type` の docstring、MitateDB は `MitateDB-api/src/mitatedb_api/field_types.py:89-96` の本文コメントと実装) **が `nullable` 既定 true の根拠である。**
- 宣言正本の場所: `r2db-api/src/r2db_api/postgres.py:885-` / `:175-190`、`MitateDB-api/src/mitatedb_api/backend_postgres.py:363-370` / `:667-720` / `:744-794` (F-3)。
- per-application upgrade 機構: `r2db-api/migrations/0009_platform_upgrades_ledger_upgrade.sql`、`MitateDB-api/migrations/0008_platform_upgrades_upgrade.sql`、`MitateDB-api/src/mitatedb_api/backend_postgres.py:456-480` (F-3)。
- catalog 生成点: `r2db-api/src/r2db_api/postgres.py:851-883`、`MitateDB-api/src/mitatedb_api/cell.py:785-811` (F-4)。
- 1.6.0 の約束文: 契約 `definitions.EntityDescriptor.properties.field_types.description` の「a later version that gives schema operations such a notion gives it to the catalog in that same version」(F-4)。
- 既存行走査の置き場所: r2db は `r2db-api/src/r2db_api/postgres.py:1617-1729` の単一 tx に置ける。**MitateDB は pre-flight (`cell.py:707` → `MitateDB-api/src/mitatedb_api/backend_postgres.py:563` で commit、`cell.py:624` → `:506` で commit) と DDL tx (`backend_postgres.py:705-720` / `:762-774`) が別なので、backend に単一 tx のメソッドを新設する** (F-6)。

#### 実装の形

1. **契約 (WP-1)**: `SchemaOperationRequest` に `field_constraints` (object) / `enum` (array) / `nullable` (boolean) を optional で足し、`definitions.EntityDescriptor` に `field_constraints` を optional で足す。**`required` は変えない。** `capability_status.defined` に `constraint_declarations` を足す。
2. **r2db (WP-2a)**: side table `_r2db_field_constraints` + per-application upgrade script + `ops upgrade-applications` 経路 + in-memory 参照 cell のプロセス内制約保持 + `apply_schema` への `alter_field` 追加 + **`_check_type` への `constraints` 引数追加と enum / nullable 検査 (上表の書き込み 6 箇所に渡す)** + **insert 分岐 2 箇所への欠落検査** (`structured.py:1296` / `postgres.py:1277`) + `catalog()` への `field_constraints` 追加 + **`bind_schema_operation` の分岐 (`structured.py:589-761`) と `service.py:885` の `schema_ops` リテラルの更新** (**`SCHEMA_OPERATIONS` 定数は死んでいるので触らない。v1.2、レビュー 2 m5**) + **`structured.py:617` の既存 `field_type` 拒否を `violated_declaration: unsupported_field` に載せ替える** + capability の `unsupported` から `alter_field` を外す。
3. **MitateDB (WP-3a)**: **Postgres backend は `_mdb_field_types` への列追加 + per-application upgrade script**、**SQLite backend は `_declared_types` と同じプロセス内構造への制約追加 (upgrade script 無し)** + `add_field` / `create_collection` の書き込み + **`alter_field` の新設** + **`check_declared_value` への `constraints` 引数追加と enum / nullable 検査 (`_prepare_values` の `cell.py:1442` にのみ渡し、`_bind_filters` の `:1502` / `:1510` には渡さない)** + **`_plan_operation` の insert 分岐 (`cell.py:1034-1046`) への欠落検査** + `catalog()` への `field_constraints` 追加 + `http.py:941-946` の present-denial 解除。
4. **既存行走査 (v1.2 で改訂。レビュー 2 M3、監督裁定 S-g)**: **r2db は `apply_schema` が既に `with conn.transaction():` (`postgres.py:1617`) で DDL 全体を包むので、その中に走査を置く。** **MitateDB は `alter_field` を backend の新設メソッド 1 本 (`alter_field_constraints` 等。名は作業指示書で確定) として実装し、その 1 つのトランザクションの中で「違反行の SELECT → registry 更新 → revision bump → commit」を行う** — **既存の `create_collection` / `add_field` の「cell 層で読んでから別 tx で DDL」の型に倣わない。** **cell 層の pre-flight 位置 (`cell.py:707` / `:624`) に走査を置いてはならない** — その位置は別トランザクションであり commit する (F-6)。**この競合は共通条件では観測できないので (C-20 (6) は「1 行も変わっていない」しか見ない)、「走査と DDL の間に他 session の書き込みが入れる隙間が無いこと」を示す peer-local テストを WP-3a の完了条件とし、C-20 行にその限界を開示する。** **MitateDB の developer 接続の SELECT 権限は F-6 のとおり解決済みである** (所有者権限。明示 GRANT は不要)。**実測の記録は §11.3 に残す。**

#### 検査の形

- **C-20 (§6.2)** が両方向を固定する — 宣言した制約が**強制される**こと、catalog が**同版で報告する**こと、`alter_field` の既存行違反が **`CONFLICT` で全件拒否**されること。
- **変異**: choke point から enum 検査を外す → C-20 の「集合外の値が拒否される」が 4 plug で赤。**predicate 経路に `constraints` を渡す** → C-20 (5) の「集合外の値で検索しても拒否されない」が赤。**`_apply_upsert` の `_check_type` に `constraints` を渡さない** (`structured.py:1392` / `postgres.py:1471`) → **C-20 (1) の upsert 枝が赤** (v1.2 で追加。レビュー 2 M7)。`nullable: false` の欠落検査を insert 分岐から外す → C-20 の `absent` 枝が赤。catalog の `field_constraints` を宣言でなく既定値から作る → C-20 の round-trip が赤。`alter_field` の既存行走査を DDL の**後**に移す → C-20 の「1 行も変わっていない」assert が赤。**拒否時に revision を進める** → C-20 (6) の revision 不変 assert が赤 (v1.2 で追加。S-g)。**MitateDB の既存行走査を cell 層の pre-flight 位置 (別トランザクション) に置く** → **共通条件では捕まらない**ので、WP-3a の peer-local テストが赤にする (上記 実装の形 4。この限界を C-20 行に開示する)。
- **peer-local**: side table / registry 列が per-application upgrade で作られること、`ops upgrade-applications` 未適用の application で `alter_field` が安全に失敗すること。

#### 開示事項

- **`enum` は書き込み側のみの制約である。** query predicate は検査しないので、**「集合外の値で検索しても VALIDATION_FAILED にならない」**。これは意図した設計であり (読み取りは制約の対象外)、**C-20 の負側 assert として明示的に固定する** — 黙って通るのではなく、「通ることが検査されている」形にする。
- **既存行の走査費用は entity の行数に比例する。** `alter_field` は schema 操作であり `execution_ms` の下にある — **大きな entity では deadline に当たり得る**。これは bound が正しく効いている姿であり、`LIMIT_EXCEEDED(execution_ms)` として返る。**この点を契約文案の外 (C-20 行の開示) に書く。**
- **物理制約を置かないので、契約の外から直接 DB に書けば制約は破れる。** これは A-1 の判断そのものであり、**「契約の外から書く経路は契約の保証範囲外である」**という既存の姿勢 (SI-12 の No Data-Service Bypass が別途担保する) を変えない。
- **`SchemaOperationRequest.properties.enum` は JSON Schema の予約語と同名だが、リポジトリ内の 2 検証器はいずれも安全である (v1.2 で結論を本文に確定。レビュー 2 m12 の実読確認)。** **`properties` 配下のキーは名前でありキーワードではない。** `r2db-api/src/r2db_api/http.py:76-97` と `MitateDB-api/src/mitatedb_api/http.py:319-329` の `_check_object_shape` は**どちらも `schema.get("properties")` のキー集合と `schema.get("required")` しか読まない** (値も型も `enum` キーワードも見ない)。`conformance-tests/schema_check.py:165` の `if "enum" in schema` は**サブスキーマ側**を見るので `properties.enum` とは当たらない。**加えて MitateDB には JSON Schema を解釈するコードが一切無く、契約の enum は Python リテラルに手写しされている** (`MitateDB-api/src/mitatedb_api/field_types.py:33` ほか)。**第三者の汎用 validator では衝突し得る**ことは変わらないので、**WP-1 はこの結論を実測で再確認して §11.3 に記録する** (結論は既に出ている)。 **宣言の形そのもの (`add_field` / `alter_field` が top-level の `enum` / `nullable` を運ぶこと) は D-2 (1) の監督確定であり、本項はその形の予約語上の含意を開示するものである。**
- **`upsert` の扱いを契約文案が明示する (v1.1。レビュー 1 B3)** — **insert に解決した `upsert` は `nullable: false` の欠落規則の対象であり、update に解決した `upsert` は対象外である** (その field に値を書かないから)。**黙って片方に寄せない。**

---

### D-3 R-3 検証エラーの固定 details 語彙

#### 決定

**(1) `errors.details_vocabulary` に 3 code のブロックを足す** — `VALIDATION_FAILED` / `IDENTIFIER_INVALID` / `CAPABILITY_UNSUPPORTED`。**`LIMIT_EXCEEDED.limit_class` の前例と同形である** (F-8)。

**(2) key は 4 つのみである。**

| key | 型と意味 |
|---|---|
| **`field`** | string。**要求内の位置**を、要求 body の根からの `/` 区切りパスで名指す (先頭に `/` を置かない)。例: `operations/0/values/label`、`budget/result_items`、`entity`、`field_constraints/label/enum`。 |
| **`declared_type`** | string。**宣言側の型** — field 型語彙の 7 語 (`string` / `integer` / `number` / `boolean` / `object` / `array` / `json`) のいずれか、または request schema が定める JSON 型 (`string` / `integer` / `number` / `boolean` / `object` / `array`)。 |
| **`observed_type`** | string。**受け取った値の JSON 型** — `string` / `integer` / `number` / `boolean` / `object` / `array` / `null` のいずれか、**または値が存在しないことを表す `absent`**。 |
| **`violated_declaration`** | string。**固定語彙**。下記 (3)。 |

**`field` の形式を「要求 body 根からのパス」1 形式に固定する理由**: D-6 が `budget` 違反の `field` を `budget/<class>` と定めており、entity field 名では表せない位置がすでに要求されている。**batch の何番目かを名指せるのもこの形だけである** (`operations/3/values/x`)。したがって**要求内の位置を指す 1 形式**に統一し、entity field 名を裸で置く形は採らない。

**(3) `violated_declaration` の固定語彙 (10 語)。**

| 値 | 意味 | 主な発行元 |
|---|---|---|
| `request_schema` | 要求が契約の request schema に適合しない (未知フィールド、型違い、必須欠落) | request-shape 層 |
| `identifier_syntax` | 識別子が契約の identifier 構文に適合しない | identifier 検証 |
| `field_type` | 値が field の宣言型に適合しない | choke point |
| `enum` | 非 null 値が field の宣言 `enum` の要素でない | choke point |
| `nullable` | `nullable: false` の field に null を書いた、または insert で欠落した | choke point |
| `capability` | 要求された操作 / フィールドをこの配備が提供していない | capability gate |
| `budget` | 要求単位 `budget` の宣言そのものが不正 (適用外 class、配備値超過、非整数) | limit gate |
| `unsupported_field` | この版が意味を定義していないフィールドを、schema 上は受け取れる位置に載せた (例: `alter_field` の `field_type`) | choke point |
| `plan` | `plan` トークンが現在の要求 / schema 状態と一致しない | plan 検証 |
| `idempotency_key` | 同一 `idempotency_key` が異なる要求 digest で再送された | idempotency 記録 |

**このうち `plan` は `PRECONDITION_FAILED` に、`idempotency_key` と (`alter_field` の既存行違反である) `enum` / `nullable` は `CONFLICT` に載る。** つまり **`violated_declaration` は 1 本の閉じた語彙であり、必須規則が掛かるのは 3 code だけで、他の code は同じ語彙から任意に載せてよい**、という形である。

**(4) 必須規則。**

**v1.1 で 3 分岐に書き分けた** (レビュー 1 M2、監督裁定 R-f)。**理由**: `request_schema` の未知フィールド denial には `declared_type` が**存在しない** (契約 schema がその名前を知らないから) ため、載せれば語彙外の値を捏造することになる。`enum` 違反では `declared_type == observed_type` になり (どちらも例えば `string`)、2 key が載っていて違反の内容を 1 ビットも説明しない — **AI エージェントが型不一致と誤読する。**

- **`VALIDATION_FAILED`**: `violated_declaration` **必須**。`field` は**違反が 1 field に帰属できるとき必須**。`declared_type` / `observed_type` は次の 3 分岐である。
  - **`violated_declaration` が `field_type` / `nullable`**: **両方必須**。
  - **`violated_declaration` が `enum`**: **`declared_type` 必須** (その field の宣言型)、**`observed_type` は載せない** (値の型は違反の内容ではなく、載せれば型不一致と誤読される)。
  - **`violated_declaration` が `request_schema`**: **`field` 必須**。`declared_type` / `observed_type` は**「値の型に関する違反」(型不一致・必須欠落) のときのみ**載せ、**「未知フィールド」のときは載せない**。
- **`IDENTIFIER_INVALID`**: `field` + `violated_declaration: identifier_syntax` が**必須**。
- **`CAPABILITY_UNSUPPORTED`**: `violated_declaration: capability` が**必須**。`field` は**要求内の位置が定まるとき必須**。
- **値は事実のみである** — 行値・推奨値・修正動作・SQL・内部名を載せない (SI-10)。

**(5) 層の整理 (L6-9)。** **`violated_declaration` を決めるのは choke point 層 (F-2) と request-shape 層 (`_check_object_shape`) である。** backend 層の defence-in-depth (F-9) は**残す**が **4 key を持たない**。**conformance が 4 key の存在を assert することで、「backend 層が先に発火する経路」は赤になる** — 層の順序が message 文字列ではなく details の有無で機械的に検査可能になる。**MitateDB は `ValidationError` / `CapabilityError` に details 属性を新設する** (F-7)。

**(6) 適用範囲。** 4 key は 3 code が**発行されるときの**形を固定する。**MitateDB が `IDENTIFIER_INVALID` を発行しない現行 (F-7) は本フェーズで変えない** — 発行しない実装は「その code の形」に縛られないからである。**この非対称は台帳 (L9-2a) に記録する。**

**ただし `PRECONDITION_FAILED` は D-4 により MitateDB でも発行されるようになる (v1.2 で追加。レビュー 2 M4、監督裁定 S-h)。** **plan の失効判定が MitateDB にこの code を初めて発行させるので、WP-3b が `PRECONDITION_FAILED` の例外クラスを新設する** (§8)。**本節の 4 key 必須規則は 3 code にしか掛からないので、`PRECONDITION_FAILED` は `violated_declaration: plan` を「載せてよい側」であって「必須の側」ではない** — (3) の表が定める閉じた語彙から任意に載せる形である。**L9-2 はこの差に合わせて 2 項に分ける** (§10)。

#### 契約文案 (英語)

**`errors.details_vocabulary.VALIDATION_FAILED`**:

> {"violated_declaration": "string, required. Which declaration this request violated, drawn from errors.details_vocabulary.violated_declaration_vocabulary.", "field": "string, required whenever the violation is attributable to one position in the request: that position, named as a '/'-separated path from the request body root, with no leading separator (for example operations/0/values/label, budget/result_items, or entity). It names a position in the request, never a storage location.", "declared_type": "string, required where violated_declaration is field_type or nullable, and where it is request_schema and the violation is about a value's type -- the type the declaration names, a member of the field-type vocabulary for a field-level violation or the JSON type this contract's own request schema names for a request-shape one. Where violated_declaration is enum, it names the field's own declared type; where the violation is an unrecognized field, no type is declared for it and this key is absent.", "observed_type": "string, required alongside declared_type wherever declared_type is required, except under enum, where the value's own type is not what was violated and this key is omitted so that an enum violation is not read as a type mismatch: the JSON type of the value actually received (string, integer, number, boolean, object, array or null), or absent where the request omitted a value the declaration requires."}

**`errors.details_vocabulary.IDENTIFIER_INVALID`**:

> {"violated_declaration": "string, required. Always identifier_syntax.", "field": "string, required. The position in the request carrying the identifier, named as for VALIDATION_FAILED.field."}

**`errors.details_vocabulary.CAPABILITY_UNSUPPORTED`**:

> {"violated_declaration": "string, required. Always capability.", "field": "string, required whenever the unsupported operation or field occupies a determinate position in the request, named as for VALIDATION_FAILED.field; omitted where the request as a whole is what is unsupported."}

**`errors.details_vocabulary.violated_declaration_vocabulary`**:

> A closed vocabulary of ten values naming which declaration a denial reports as violated: request_schema (the request does not match this contract's own request schema for that endpoint), identifier_syntax (an identifier does not match the identifier syntax this contract declares), field_type (a value does not match the field's declared type), enum (a non-null value is not a member of the field's declared enum), nullable (a null was written to, or a required value omitted from, a field declared nullable: false), capability (this deployment does not provide the operation or field the request names), budget (the request's own budget declaration is itself invalid -- a class that does not apply to this endpoint, a value above the deployed bound, or a non-integer), unsupported_field (a field this version gives no meaning to, carried where the request schema can still receive it), plan (a plan token does not match the request and schema state it is presented against), and idempotency_key (the same key was resent with a different request digest). The required-key rules above bind VALIDATION_FAILED, IDENTIFIER_INVALID and CAPABILITY_UNSUPPORTED only; any other code's denial may carry violated_declaration drawn from this same vocabulary without being required to -- PRECONDITION_FAILED carries plan, and CONFLICT carries idempotency_key, or enum/nullable where an alter_field is refused because existing rows would violate the constraints it declares. Every value a details key carries under this vocabulary is a statement of declared fact: never a row value, never a suggested value, never a corrective action, never SQL, and never an internal name (SI-10 constrains the content of every details value regardless of key name, as errors.details_vocabulary.open already states).

**`errors.details_vocabulary.layer_rule`**:

> The four keys above are decided by the layer that reads the declaration -- the request-shape check and the value-validation choke point. An implementation may keep additional defence-in-depth validation behind those layers; such a layer is not required to produce these keys, and a denial reaching a client without them is evidence that the declaration-reading layer did not run first.

#### 根拠 (file:line)

- 現行 details の実態: `r2db-api/src/r2db_api/errors.py:22` (`fail`)、`MitateDB-api/src/mitatedb_api/errors.py:43-44` / `:188-205` (**105 箇所の `ValidationError` 呼び出しに details 引数 0 件**)、`MitateDB-api/src/mitatedb_api/identifiers.py:30`、`MitateDB-api/src/mitatedb_api/http.py:88-96`、`MitateDB-api/src/mitatedb_api/cell.py:1755` (F-7)。
- 契約の前例: `errors.details_vocabulary` (`LIMIT_EXCEEDED.limit_class` と `open` 節)、`destructive_confirmation.denial.details_keys` / `details_rules` (F-8)。
- 二重検証の層: `r2db-api/src/r2db_api/postgres.py:1249`、`MitateDB-api/src/mitatedb_api/backend_postgres.py:299-329` (F-9)。層の区別が message 文字列だけであること: `docs/design/PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md:805-806` / `:832` (L6-14)。
- HTTP 整形: `r2db-api/src/r2db_api/errors.py:18-19`、`MitateDB-api/src/mitatedb_api/http.py:152-189` / `:188-189`、`MitateDB-api/conformance/conformance_adapter_mitatedb.py:2260-2263` (F-10)。**message は MitateDB HTTP で code 別固定文言に置換されるので、details に載せる以外に構造化情報を運ぶ経路が無い。**
- SI-10 走査の現況: `conformance-tests/test_c04_unsupported_and_safe_errors.py:29-45`、`conformance-tests/conftest.py:517-546` (F-11)。

#### 実装の形

1. **契約 (WP-1)**: `errors.details_vocabulary` に 3 ブロック + `violated_declaration_vocabulary` + `layer_rule` を足す。**既存の `LIMIT_EXCEEDED` / `common_optional` / `open` / `cross_reference` は 1 文字も変えない。**
2. **r2db (WP-2e)**: `fail()` の呼び出し側で 4 key を組み立てる。**`field` の値を「entity field 名」から「要求内パス」へ改める箇所が多数出る** — 実装 WP が全数を AST 走査で列挙して §11.3 に記録する (grep では取り逃す。第 15 次 §5 の教訓)。**`_check_object_shape` (`r2db-api/src/r2db_api/http.py:76-97`) の現行 `details={"fields": sorted(extra)}` (複数形・リスト) は `violated_declaration: request_schema` の形へ改める** — **未知フィールドが 1 個なら `field` にその位置を単数で載せ、複数あるときは `field` を省く** (上記 (4) の「違反が 1 field に帰属できるとき必須」の帰結であり、実装裁量ではない)。
3. **MitateDB (WP-3e)**: `ValidationError` / `CapabilityError` に `details` 属性を新設し、`http.py` の整形と in-process の整形の**両方**が同じ details を出すことを確認する (F-10 の 2 経路)。
4. **backend 層は触らない** — details 無しのまま残す。

#### 検査の形

- **C-21 (§6.2)** が「3 code の denial が必須 key を持つ」「値が固定語彙に属する」「行値・SQL・内部名が含まれない」を固定する。**無条件義務なので `xfail(strict=True)` を版宣言に条件付ける** (D-1 (7))。
- **変異**: choke point が `violated_declaration` を落とす → C-21 が赤。backend 層が先に発火する順序へ変える → **backend 層は 4 key を持たないので C-21 が赤** (これが「層の順序を機械で固定する」形である)。`field` を entity field 名に戻す → C-21 のパス形式 assert が赤。
- **SI-10 側**: 既存の `assert_no_unsafe_diagnostic_content` (`conformance-tests/conftest.py:517-546`) の**走査対象を 3 code の details にも広げる** (F-11 で現在は `DESTRUCTIVE_CONFIRMATION_REQUIRED` のみ)。**ただし対象は本節の 4 key の値に限定する (v1.1。レビュー 1 m7、監督裁定の Minor 一括採択)** — `details.field` は **client 自身が選んだ field 名**を要求内パスとして含むので、敵対的な identifier を送る probe を走査対象にすると**テストが自分のエコーで赤になる。** **C-21 が使う identifier は `fresh_identifier` の良性の値に限り、敵対的 identifier の probe は C-03 の territory であって C-21 の走査対象にしない。** **変異**: details に行値を入れる → C-21 が赤。

#### 開示事項

- **`field` の位置は「要求内」であって「storage 内」ではない。** 契約文案がそう明記する。**これは SI-10 の要請でもある** — storage 内の位置を返せば内部構造の開示になる。
- **MitateDB は `IDENTIFIER_INVALID` を発行しないので、C-21 の `IDENTIFIER_INVALID` 枝は MitateDB 2 plug で観測されない。** **これは空振りではなく「その code を発行しない実装は縛られない」という適用範囲の帰結である** — C-21 の非 vacuity 要件は「**3 code のうち少なくとも 1 つが、その plug で実際に観測される**」であり、MitateDB では `VALIDATION_FAILED` と `CAPABILITY_UNSUPPORTED` が観測される (§6.2)。**この非対称を台帳 L9-2a と C-21 行に開示する。**
- **backend 層の denial が details 無しで client に届く経路は残る** (defence-in-depth が先に発火する構成ミスが起きた場合)。**C-21 はそれを赤にするが、「赤になる」ことと「起き得ない」ことは別である** — 契約文案の `layer_rule` はこの状況を「宣言を読む層が先に走らなかった証拠である」と明示的に名付ける。

---

### D-4 R-4 dry_run と無状態 plan

#### 決定

**(1) 要求側のフィールド。** `MutationRequest` / `ScopedMutationRequest` / `SchemaOperationRequest` に **`dry_run`** (boolean、既定 `false`) と **`plan`** (string、`maxLength: 256`) を足す。**`QueryRequest` には足さない** — 読み取りに dry_run の意味が無い。

`maxLength` を 256 に固定する理由: `plan` は**不透明だが決定的なトークン**であり、実装が選ぶ digest 表現 (16 進 sha256 = 64 字、base64url = 43 字) に十分な余裕を持ちつつ、`confirmation` (256) / `idempotency_key` (128) と同じ桁の既存上限に揃える。**要求の byte 費用は `request_bytes` が別途 bound する。**

**(2) 判定は実呼びと同一の経路を通る — dry_run 固有の早回りをしない (v1.1 で改訂。レビュー 1 M1、監督裁定 R-e)。**

**dry_run は実呼びが通るすべての gate を通る** — 認証、role、rate / concurrency、request_bytes、operation_depth、request shape、capability、検証である。**認可判定 (FORBIDDEN / SCOPE_MISMATCH)、破壊確認 (DESTRUCTIVE_CONFIRMATION_REQUIRED)、precondition、limit は、実呼びと同一の code と details で返す。** これが計画文書の「認可判定 (policy simulation) も dry_run の判定に含める」の実現形である。

**gate の順序は契約に載せない。** **v1.0 は順序を列挙し契約文案がそれを英語で断言していたが、その順序は両 peer のどちらの実装とも一致しない** — r2db は HTTP 層の `_check_object_shape` (`r2db-api/src/r2db_api/http.py:330`) が `service.mutate_result` (`:335`) より前にあり、rate / concurrency (`service.py:1030` の `_slot`) と `request_bytes` (`service.py:1037`) は **shape の後**である。MitateDB も `http.py:319` の shape 検査が `_limit_gate` より前である。**さらに in-process plug には shape 検査層が存在しない** (adapter が service / cell を直接呼ぶ)。**順序は実装事実であり、契約が固定するのは「どの gate が掛かるか」と「返る code / details」である。**

**ただし例外が 2 つある (v1.2 で追加。レビュー 2 M8、監督裁定 S-l)。** **これは新しい順序規定ではなく、契約 `destructive_confirmation.evaluation_order` (「Confirmation validity is evaluated after shape validation, authentication/authorization, and target-existence checks, and before precondition evaluation and execution.」) という既存の 1 文への当てはめである。**

- **`plan` の照合は precondition である** — したがって `evaluation_order` の precondition 段 (`expected_revision` と同じ段。confirmation の**後**、execution の**前**) で行う。**帰結: 失効した `plan` を持つ未確認の `drop_entity` は `DESTRUCTIVE_CONFIRMATION_REQUIRED` を返す** (`PRECONDITION_FAILED` ではない)。
- **`budget` の妥当性検査 (適用外 class / 配備値超過 / 非整数のいずれも) は要求の検証段である** — shape / capability と同じ段であり、target-existence の**前**である (D-6 (3))。**帰結: 配備値超過の `budget` を持つ未確認の `delete` は `VALIDATION_FAILED` を返す。**

**この 2 点は「順序は外から観測できない」の例外でもある** — **2 つの違反を同時に含む 1 要求が返す code として観測できる**ので、C-22 / C-24 がそれぞれ 1 本ずつ assert する (§6.2)。**それ以外の gate の順序は依然として契約に載せない。**

**(3) dry_run が返す成功応答。**

- **実呼びと同じ schema** である (新しい response schema を作らない)。
- **`committed: false`。**
- **`affected` は実行したときの件数**である。
- **mutation の `assigned_addresses` は載せない** — 採番は確定しないので、載せれば偽の宣言になる (§4 A-9)。
- **schema なら変更後の `EntityDescriptor` を `descriptor` に載せる** (`SchemaOperationResult` に optional `descriptor` を足す)。
- **schema の `revision` は「判定時点の現在 revision」である (v1.2 で追加。レビュー 2 M6、監督裁定 S-j)。** `SchemaOperationResult.revision` は `required` の string なので dry_run でも必ず載る。**載せるのは plan を計算した値と同じ「今の revision」であり、その操作が確立するはずの revision ではない** — **確立していない値を返さないという点で `assigned_addresses` を載せない理由と同じである** (§4 A-9)。**`descriptor` は変更後の姿を載せ、`revision` は現在値を載せる**という非対称は意図したものであり、契約文案がそう明記する。
- **加えて `plan` を返す。** **そのために `MutationResult` と `SchemaOperationResult` に `plan` (string) を optional で足す (v1.3 で明記。監督裁定 T-1)** — 3 result schema はいずれも `additionalProperties: false` であり、足さなければ dry_run 応答が C-11 (response schema conformance) で赤になる。**`required` 配列は変えない。** **§5 U-8 #29 である。**

**(4) 実現はトランザクション内で実行し commit の代わりに rollback する** (§4 A-3 が静的検証案を却下している)。r2db in-memory は restore、r2db Postgres は tx rollback、MitateDB は明示 rollback である。**加えて次の 3 点を分岐で抑止する。**

- **監査 pre_commit hook を呼ばない** (F-14。rollback しても監査行は残るので、呼んだ時点で外部可視の状態が変わる)。**§5 U-2 = (A) の確定により、この規則は最終である** — dry_run が実行段階に達した場合、監査行を一切書かない。**実行前の拒否 (AUTH / FORBIDDEN / LIMIT / SCOPE_MISMATCH 等) は現行どおり監査される。**
- **idempotency 記録を書かない・参照しない。** **`dry_run` に `idempotency_key` があっても「無視する」のではなく「記録しない」と契約に書く** — 無視は黙って挙動が変わる形であり、明示された規則の方がエージェントに読める。
- **revision を進めない。**

**(5) id 採番の消費は起き得る** (F-15)。**契約に明記する** — 「dry_run は server-assigned address の採番を消費し得るが、消費した address は返さず、`address_reuse` の規律 (`never`) に従い再利用されない」。**これは正直な宣言であって欠陥ではない** — 隠せば「外部可視の状態変化 0」が偽になる。

**(6) 「外部可視の状態変化 0」の定義。** 行・catalog・revision・idempotency 記録・**監査行** (§5 U-2 = (A) の確定により含む) が変わらないこと。**rate / concurrency の消費は「状態変化」に含めない** — 要求である以上 bound を消費するのが正しく、消費しない形は「dry_run で bound を回避できる」という穴になる。

**(7) `plan` トークンは「要求の正規化 digest + 対象 Application の schema revision」である** (P-1: 無状態。**§5 U-4 = (A) で確定した**)。**revision は `SchemaOperationResult.revision` が報告するのと同じ値**であり、**per-application の単調カウンタ**である。**`cross_entity_mutate` も同じ per-application revision を使う** — entity ごとの revision は両 peer とも持たない。**revision を進める操作 (index 作成を含む) はすべて plan を無効にする。** **revision が Application 単位である帰結として、対象 entity に無関係な entity への schema 操作も plan を失効させる** — **これは fail-closed 側の誤差であり安全だが、正本 (計画文書 §5 R-4) が「対象 entity の schema revision」と書いているので、R-14 の規約で改版註を足す** (§10.1。v1.2 で追加。レビュー 2 M5、監督裁定 S-i)。

**digest の対象と正規化規則を設計で固定する (v1.2 で追加。レビュー 2 B1、監督裁定 S-a)。** **作業指示書送りにしない** — P-6 (peer 同型性) の最も割れやすい 1 点だからである。

- **digest の対象は「契約レベルの要求オブジェクト」である** — 当該 endpoint の request schema の `properties` として受理された object であり、**raw HTTP body ではない。** **HTTP 層から来ても in-process port から来ても同じ object になる** (in-process 経路には body が存在しない。r2db は `http.py:329` が body を parse して `:336` で `operations` だけを渡し、MitateDB は `http.py:651-669` の `_mutation_item` がキー名を改名した dict を組み立て直すので、**raw body を digest の材料にすると 4 plug で規則が一致しない**)。
- **除く key は `plan` と `dry_run` の 2 つだけである。** `plan` は自分自身の digest を含められず、`dry_run` は dry_run 要求と apply 要求で必ず値が異なるからである。**`idempotency_key` / `budget` / `transaction` / `confirmation` は含める。**
- **正規化 = JSON の key を辞書順に並べ、区切りに空白を入れず、非 ASCII を escape せず UTF-8 で直列化したバイト列の sha256 (hex)。**
- **計算位置は両 peer とも service / cell 層の入口 (要求 object が揃う最初の点) である。**
- **idempotency の digest (D-5 (1)(i)) は同じ object から `plan` / `dry_run` / `idempotency_key` の 3 key を除いたものである** — **2 つの digest は同じ規則の上に立ち、除外集合だけが違う。**

**apply (= `dry_run: false` で `plan` を伴う実呼び) の規則**: サーバが**同じ規則で再計算し、不一致なら `PRECONDITION_FAILED`** (details: `violated_declaration = plan`)。**トークンは opaque だが決定的である** — **同一要求の dry_run を 2 回行えば同一の `plan` が返る。**

**(8) 能力**: `dry_run` を `capability_status.defined` に新設する (条件付き義務の結び先)。

#### 契約文案 (英語)

**`schemas.MutationRequest.properties.dry_run.description` (3 request schema 共通の文言。正本は `structured_operations.dry_run` に置き、各 schema からはその節を指す)**:

> `dry_run` asks the service to reach the same decision it would reach for the identical request without it, and then to leave nothing behind. A dry-run request is subject to the same gates a real one is -- authentication, role, request rate and concurrency, request size, operation depth, request shape, capability availability, and validation -- and any refusal it receives is the refusal the real request would receive, with the same code and the same details: authorization refusals, destructive-confirmation refusals, precondition refusals and limit refusals are all part of what a dry run decides, not steps it skips. Where it is not refused, it answers with the same response schema the real request answers with, carrying `committed: false`, the `affected` count the real request would have produced, and a `plan`. A dry-run mutation does not carry `assigned_addresses`: the addresses a real execution would assign are not settled, and reporting them would be a false statement rather than a preview. A dry-run schema operation carries `descriptor`, the `EntityDescriptor` the entity would have afterwards. Its `revision` is the Application's schema revision as it stands now -- the revision the `plan` was taken against -- and not the revision the operation would establish, which for the same reason `assigned_addresses` is withheld is not settled until it commits.

**`structured_operations.dry_run.external_effects`**:

> A dry run leaves no externally visible state change: no row, no catalog entry, no schema revision, no idempotency record, and no audit event is created, changed or removed by it. Two consumptions are deliberately outside that statement. First, a dry run is a request, and consumes this deployment's own request-rate and concurrency bounds exactly as a real request does -- a bound a client could avoid by asking for a dry run would not be a bound. Second, where an implementation assigns addresses from a non-transactional sequence, a dry run may consume a value from that sequence; it never returns the value it consumed, and the consumed value is not reused, which is what `EntityDescriptor.address_reuse: never` already declares. An `idempotency_key` presented on a dry-run request is neither recorded nor looked up: the dry run is not deduplicated against earlier requests, and does not make a later resend of the same key a duplicate. This is stated rather than left to the reader as "ignored", because a client that resends after a dry run must be able to know that its first real send is genuinely the first.

**`structured_operations.dry_run.plan`**:

> `plan` is an opaque but deterministic token: it is computed from the request itself together with the Application's own schema revision -- the same value `SchemaOperationResult.revision` reports -- as it stood when the request was decided, and holds no server-side state -- there is nothing on the service that expires, is evicted, or must be cleaned up, and two dry runs of the identical request against unchanged schema return the identical token. The token is computed over this request as this contract defines it -- the request object this endpoint's own request schema names, not the bytes a particular transport delivered it in -- taking every field of that object except `plan` itself, which cannot contain its own digest, and `dry_run`, whose value necessarily differs between the dry run and the real request it plans. Every other field, including `budget`, `transaction`, `confirmation` and `idempotency_key`, is part of what the token commits to: a real request differing from the dry run in any of them is a different request, and the token no longer agrees. The digest is taken over that object serialized with its keys in lexicographic order, without insignificant whitespace, and without escaping non-ASCII characters, as UTF-8; the token an implementation returns is its own representation of that digest together with the revision. A client may present the token it received back on the real request. Where it does, the service recomputes the token by the same rule and executes only if the two agree; where they disagree -- because the request differs, or because any schema operation on that Application advanced its revision in between -- the request is refused with `PRECONDITION_FAILED` and `details.violated_declaration: plan`, and nothing is executed. Because that revision is the Application's own, a schema operation on any entity of the same Application invalidates a plan taken against any other: the token names the Application's schema state, not one entity's. A `plan` is a precondition, and is evaluated where `destructive_confirmation.evaluation_order` places precondition evaluation -- after confirmation validity and before execution -- so a request that is both unconfirmed and carrying a stale `plan` is refused for the missing confirmation first. A `plan` is never required: a real request that omits it executes on the service's own current state, exactly as it did before this version.

#### 根拠 (file:line)

- 経路と tx 境界: r2db `r2db-api/src/r2db_api/service.py:1028-1058` / `:1060-1084`、`r2db-api/src/r2db_api/structured.py:1236-1289` (deepcopy = BEGIN / restore = ROLLBACK)、`r2db-api/src/r2db_api/postgres.py:1122-1206` (`:1147`) / `:1606-1729` (`:1617`)。MitateDB `MitateDB-api/src/mitatedb_api/cell.py:1110-1333` (BEGIN `:1204` / COMMIT `:1240` / ROLLBACK の実行は `:1295`)、**pass1 の `_plan_operation` (`cell.py:993-1072`) が DML の副作用を持たない**こと (カタログ読み取りは別接続で commit する。`cell.py:1003-1017`)、schema は `cell.py:599-649` / `:674-722` が個別に行うこと (F-12 / F-13)。
- 監査 hook が別コネクション即 commit であること: `r2db-api/src/r2db_api/audit_hook.py:1-53`、`r2db-api/src/r2db_api/postgres.py:1173-1175` / `:1710-1712`、`MitateDB-api/src/mitatedb_api/backend_postgres.py:717-720` / `:771-774` (F-14)。
- 採番が rollback で戻らないこと: `r2db-api/src/r2db_api/structured.py:1105-1116` のコメント (F-15)。
- schema revision の持ち方: `r2db-api/src/r2db_api/postgres.py:1900-1935` (Postgres、DDL と同一 tx で永続)、`MitateDB-api/src/mitatedb_api/backend_postgres.py:361` / `:646-661` (同左)、`r2db-api/src/r2db_api/structured.py:1105` と `MitateDB-api/src/mitatedb_api/backend_sqlite.py:87` / `:95` / `:207` / `:250` (**両 peer の in-memory backend はプロセス内。SQLite backend も `:memory:` である**、F-16) — **§5 U-4 = (A) の前提である。**
- 新フィールドが shape 検査で拒否されること (= 契約先行が必須であること): F-17。

#### 実装の形

1. **契約 (WP-1)**: 3 request schema に `dry_run` / `plan` を optional で足し、`SchemaOperationResult` に `descriptor` を optional で足し、**`MutationResult` と `SchemaOperationResult` に `plan` (string) を optional で足し (v1.3 で追加。監督裁定 T-1。§5 U-8 #29。`required` は変えない)**、`structured_operations` に `dry_run` 節 (3 段落) を足し、`capability_status.defined` に `dry_run` を足す。
2. **r2db (WP-2b)**: `_mutate_outcome` / schema 経路に dry_run 分岐を置く。**commit 直前で分岐するのではなく、「commit するか rollback するか」を tx の出口 1 点で決める形にする** — 途中で分岐すると「実呼びと同じ判定」が崩れる。`_make_audit_hook` を dry_run では組み立てない。
3. **MitateDB (WP-3b)**: `transact` の COMMIT / ROLLBACK 点 (`cell.py:1240-1241`) で分岐する。schema 操作は `create_entity` / `add_field` / `alter_field` が個別に tx を持つので、それぞれに同じ出口分岐を置く。
4. **plan の計算は両 peer で同一規則にする** (P-6)。**材料・除外 key・正規化規則は D-4 (7) が設計で固定した** (v1.2。作業指示書送りにしない)。**計算位置は service / cell 層の入口である** — r2db は `r2db-api/src/r2db_api/service.py:1036` の `request = {"entity": entity, "operations": operations}` を組む位置、MitateDB は `MitateDB-api/src/mitatedb_api/cell.py:1158` の `request = {"operations": operations}` を組む位置が現行の対応点であり、**契約レベルの要求オブジェクトが揃うように両 peer とも受け渡しを補う** (現在は `transaction` / `idempotency_key` が service / cell 層に届かない、`filters` が `Filter` dataclass になっている等の差がある)。**コードは共有しない。**
5. **WP-3b は `PRECONDITION_FAILED` の例外クラスを新設する (v1.2。レビュー 2 M4、監督裁定 S-h)** — MitateDB は現在この code をコード上どこにも持たない (`MitateDB-api/src/mitatedb_api/http.py:89` のコメントが「この peer はいくつかの契約 code をそもそも発行しない」と明記している)。**`MitateDB-api/src/mitatedb_api/errors.py` に例外を足し、`_problem_for_exception` の code 別固定文言表 (`http.py:152-189`) に 1 行足し、in-process 経路 (`MitateDB-api/conformance/conformance_adapter_mitatedb.py:2260-2263`) でも同じ details が出ることを確認する** (F-10 の 2 経路)。

#### 検査の形

- **C-22 (§6.2)** が「判定 = 実呼び」「外部可視状態変化 0」「plan の決定性と `PRECONDITION_FAILED`」を固定する。**conformance は 5 つの命題を assert する**: (i) 同一要求 + schema 不変 → apply 成功、(ii) schema 変更後 → `PRECONDITION_FAILED`、(iii) 別 body + 同 plan → `PRECONDITION_FAILED`、(iv) dry_run 2 回で plan 一致、**(v) `budget` だけを変えた apply → `PRECONDITION_FAILED`** (v1.2 で追加。レビュー 2 B1 — digest の対象領域が load-bearing であることの assert)。
- **変異**: dry_run で `pre_commit` を呼ぶ → C-22 の「監査行不変」が赤 (§5 U-2 = (A))。dry_run を「検証だけして実行しない」形に変える → C-22 の `affected` 一致が赤。plan を乱数にする → (iv) が赤。plan の schema 状態成分を落とす → (ii) が赤。plan の request 成分を落とす → (iii) が赤。**digest の対象を `operations` だけに狭める** → (v) が赤。**`dry_run` / `plan` を digest から除かない** → (i) が 4 plug で赤 (apply が必ず `PRECONDITION_FAILED` になる)。**dry_run の schema 応答に「適用後の revision」を載せる** → C-22 (5) の revision assert が赤 (S-j)。
- **`assigned_addresses` を dry_run で返す変異** → C-22 の「dry_run 応答に `assigned_addresses` が無い」assert が赤。

#### 開示事項

- **採番の消費は共通 suite で観測できる** (dry_run の後に実 insert して address が飛ぶかを見れば分かる) **が、条件としては固定しない** — **「消費し得る」は許容であって義務ではない**ので、消費する実装も消費しない実装も conformant である。**C-22 はこの点を assert しない。この限界を C-22 行に開示する。** **なおこれは data mutation 側の話である (v1.2 で明確化。レビュー 2 の確認事項)** — r2db の `apply_schema` は `_next_id` を snapshot / restore する (`r2db-api/src/r2db_api/structured.py:1481`) ので、**schema の dry_run では採番は消費されない。**
- **`plan` は Application 全体の schema 状態に結び付いている (v1.2 で追加。レビュー 2 M5)** — **対象 entity に無関係な entity への schema 操作でも失効する。** これは per-application の単調カウンタしか両 peer が持たないことの帰結であり (F-16)、**fail-closed 側の誤差である** (失効しすぎることはあっても、変わった schema を見落とすことはない)。**契約文案がこれを 1 文で開示し、C-22 行にも開示する。**
- **`plan` は認可状態を含まない。** dry_run と apply の間に credential が revoke されれば apply は AUTH で落ちる — **plan がそれを検出するのではなく、apply 自身の認証段が落とす。** これは正しい形であり、**「plan は認可のスナップショットではない」と C-22 行に開示する。**
- **dry_run が rate / concurrency を消費することは、エージェントにとって費用である。** 「安全に試す」ことに費用が掛かるのは意図した設計 (P-5) であり、**budget (D-6) で自分の取り分を絞れる**ようにしてある。

---

### D-5 R-5 idempotency の実装と契約追記

#### 決定

**(1) 契約追記は計画文書の (i)〜(v) を逐語で守る。**

- **(i)** key は**要求の正規化 digest と結合して記録する**。**digest の対象・正規化規則は D-4 (7) と同一であり、除く key だけが違う (v1.2 で明記。レビュー 2 B1、監督裁定 S-a)** — **契約レベルの要求オブジェクトから `plan` / `dry_run` / `idempotency_key` の 3 key を除いたもの**の、**key を辞書順に並べ、区切りに空白を入れず、非 ASCII を escape せず UTF-8 で直列化したバイト列の sha256 (hex)** である。**`budget` / `transaction` / `confirmation` は含める。** **計算位置は両 peer とも service / cell 層の入口である。**
- **(ii)** **同一 key・異なる digest は `CONFLICT`** (details: `violated_declaration = idempotency_key`)。
- **(iii)** **保持期間 (`idempotency_retention_ms`) 内の同一 key・同一 digest の再送は、元の結果を再実行せずに返す。** 返すのは `MutationResult` / `SchemaOperationResult` の**全体**であり、**`request_id` を含む** (R-7)。
- **(iv)** **`MutationRequest` / `ScopedMutationRequest` / `SchemaOperationRequest` の 3 つに適用する。** `SchemaOperationRequest` には `idempotency_key` を**新規に追加する** (F-19: 現在は無い)。
- **(v)** **監査との相関は「再送応答が元実行の `request_id` を返す」ことで成り立つ。** **key を監査行に載せない。**

**(2) 契約に client 側の禁止文を置く。** 「client は secret 的な値 (credential、token、password、private key、その他の secret) を key に入れてはならない。**key は `forbidden_fields` の対象ではなく、監査行にも応答にも載らないが、それは key が secret でよいことを意味しない**」。**`audit.forbidden_fields` との境界を明記する** — forbidden_fields は「監査行に載せてはならない field 名」の一覧であり、`idempotency_key` はそもそも監査行に載らないので一覧の対象外だが、**対象外であることが安全の根拠にはならない。**

**(3) 記録されるのは commit された結果だけである。** **記録は data トランザクションと同一 tx で書く。** **失敗した試行は記録を残さず、再送は新規実行になる。** **dry_run は記録も参照もしない** (D-4)。

**(4) key のスコープは Application である。** 同一 Application 内で一意であり、**credential をまたいでも同一 key は同一要求とみなす** (§4 A-5)。**atomic unit の scope (Application storage) に合わせる** — 契約 `transactions.cross_entity` が「one atomic unit across entities within a single Application's storage scope」と定める境界と同じである。

**(5) bound は既存の 2 class を使う。** `idempotency_entries` (Application あたりの保持件数) と `idempotency_retention_ms`。**満杯時は、期限切れを掃除してもなお満杯なら `LIMIT_EXCEEDED` (`limit_class = idempotency_entries`)。** **期限切れ entry は「無い」ものとして扱い、削除は遅延でよい。** **満杯の判定は (8) の照会段で行い、要求を実行してから rollback する形にはしない (v1.2 で明記。レビュー 2 m13、監督裁定の Minor 一括採択)** — **記録の書き込み自体は data tx と同一 tx だが、「入るかどうか」の判定は実行前である。** これを分けないと、拒否される要求が実行費用を払うことになり SI-08 の趣旨に反する。

**(6) 保持場所は §5 U-3 = (A) で確定した** — **application DB の side table** である。per-application upgrade で置き、**data tx と同一 tx で書く**。**r2db の in-memory 参照 cell と MitateDB の in-memory (SQLite `:memory:`) backend はプロセス内構造、両 peer の Postgres backend は application DB の side table である** (F-16、§5 U-3 の確定文)。

**(7) capability `idempotency` を両 peer で `enabled` にする。** **C-07 (ii) の `retry_same_result` 枝が 4 plug で load-bearing になり、L7-8 が閉じる。**

**(8) 記録済み key の照会位置を固定する (v1.2 で新設。レビュー 2 B2、監督裁定 S-b)。** **照会は、認証・認可・bound (rate / concurrency / request_bytes / operation_depth / shape / capability / `budget` の妥当性) の後、`destructive_confirmation.evaluation_order` が定める target-existence / confirmation / precondition / execution の前である。** **記録済み key の再送は target-existence 以降の段を一切実行せずに元の結果を返す** — **`drop_entity` の再送は、entity がもう無くても、確認 phrase が無くても、元の結果を返す。**

**理由**: これを固定しないと、**最も再送安全性が要る操作でだけ両 peer が割れる。** `drop_entity` / `delete` を有効な confirmation phrase + `idempotency_key` で送って commit し、応答が失われて同一 key・同一 body で再送する場合、照会を confirmation より**前**に置く peer は元の結果を返し、**後**に置く peer は「entity がもう無い」ので `NOT_FOUND`、あるいは `destructive_confirmation.phrase_construction.rules[3]` の state fingerprint が変わっているので `DESTRUCTIVE_CONFIRMATION_REQUIRED` を返す。**これは `evaluation_order` の文言そのものを変えるものではなく、既に固定されている順序への 1 点の挿入である** — 契約側には `structured_operations.idempotency.record` に書く。

#### 契約文案 (英語)

**`structured_operations.idempotency.record`**:

> An `idempotency_key` is recorded together with a deterministic digest of the request it was sent with, and the record is written in the same transaction as the effects it records: a key is present exactly when the request it names committed. A request that fails leaves no record, so resending it is a new attempt, not a duplicate. Within `idempotency_retention_ms` of the recorded request, resending the same key with the same request digest returns that original request's own recorded result -- the whole `MutationResult` or `SchemaOperationResult`, including its `request_id` -- without executing anything a second time. Resending the same key with a different request digest is refused with `CONFLICT` and `details.violated_declaration: idempotency_key`; the denial does not disclose the earlier request. A key whose retention has elapsed is treated as absent: the resend is a new request, and an implementation may delete elapsed records lazily. A key is scoped to one Application: the same key presented under a different credential of the same Application is the same key, because the atomic unit this contract defines is scoped to one Application's storage. Where recording a new key would exceed `idempotency_entries` after elapsed records are reclaimed, the request is refused with `LIMIT_EXCEEDED` and `details.limit_class: idempotency_entries`, before it executes rather than after. A replayed `SchemaOperationResult` carries the `revision` the original execution produced, which is the revision that execution established, not necessarily the entity's revision now. The digest is taken over the request object this endpoint's own request schema names, excluding `idempotency_key` itself, `plan` and `dry_run`, and is otherwise computed exactly as `structured_operations.dry_run.plan` describes: every other field, including `budget`, `transaction` and `confirmation`, is part of what a resend must match. A resend that matches a retained record is answered from that record before target existence, destructive confirmation and any precondition are evaluated -- after this request's own authentication, authorization and bounds, which it consumes like any other request. Without that placement a resent destructive operation could not be answered from its record at all: its target no longer exists, and `destructive_confirmation.phrase_construction` recomputes a phrase against state the first execution already changed.

**`structured_operations.idempotency.correlation`**:

> Idempotency and audit evidence are correlated through `request_id`, not through the key: a resend answers with the original execution's own `request_id`, which is the identifier that execution's audit events carry, so a client holding only its own responses can tell which single execution its repeated sends resolved to. The key itself is not written to audit events.

**`structured_operations.idempotency.key_secrecy`**:

> A client MUST NOT place a credential, token, password, private key, or any other secret in an `idempotency_key`. The key is not a member of `audit.forbidden_fields`, and this version writes it neither to audit events nor to any response -- but neither of those facts makes a secret safe to use as a key. A key is a client-chosen name for one request, is compared for equality against other clients' keys within the same Application, and may be retained for as long as `idempotency_retention_ms` declares; a value that must not be guessable, resent, or retained does not belong in it.

**`schemas.SchemaOperationRequest.properties.idempotency_key`**: `{"type": "string", "maxLength": 128}` — **`MutationRequest` / `ScopedMutationRequest` の既存定義と同一形である。**

#### 根拠 (file:line)

- 既存の契約側の材料: `capability_status.defined.idempotency`、`limits.classes` の `idempotency_entries` / `idempotency_retention_ms` (example_profile 10000 / 86400000)、`MutationRequest` / `ScopedMutationRequest` の `idempotency_key`、`transactions.retry`、`audit.forbidden_fields` (F-19)。
- 現行の present-denial: `r2db-api/src/r2db_api/service.py:917`、`r2db-api/src/r2db_api/http.py:331`、`r2db-api/src/r2db_api/structured.py:205-206`、`MitateDB-api/src/mitatedb_api/cell.py:1754`、`MitateDB-api/src/mitatedb_api/http.py:684-685` / `:768-769` (F-19)。
- 肯定側が一度も実行されていないこと: `conformance-tests/test_c07_atomicity_and_retry.py:106-158` (L7-8、フェーズ7 設計 `:781`)。
- port が key を運べること: `conformance-tests/adapter.py:757` (`BatchOperation.idempotency_key`、port v1.11、裁定 S-4)。
- data tx の境界 (記録を同一 tx に置ける位置): `r2db-api/src/r2db_api/postgres.py:1147`、`MitateDB-api/src/mitatedb_api/cell.py:1204-1240` (F-12 / F-13)。
- `forbidden_fields` がコードから引かれていないこと: F-19 (**契約テキストのみ。両 peer に名前引きの経路が無い**)。

#### 実装の形

1. **契約 (WP-1)**: `structured_operations` に `idempotency` 節 (3 段落) を足し、`SchemaOperationRequest` に `idempotency_key` を足す。**`capability_status.defined.idempotency` の既存文は変えない。**
2. **r2db (WP-2c) / MitateDB (WP-3c)**: 記録の読み書きを data tx と同一 tx に置き、照会を (8) の位置に置く。**present-denial の行を削除するのと、記録を入れるのと、capability を `enabled` にするのは同一コミットである** (P-3)。**同じコミットで、その peer の capability document に `limits.idempotency_entries` / `limits.idempotency_retention_ms` と対応する `limit_enforcement` エントリを足す (v1.2 で追加。レビュー 2 M2、監督裁定 S-f)** — **C-05 V1 (e) の `_CAPABILITY_CONDITIONED` (`conformance-tests/test_c05_limit_declaration_agreement.py:84-88`) がこの 2 class を `idempotency` に条件付けており、`idempotency` を `unavailable` 以外にした瞬間に明示の宣言が必須になる。** 宣言を欠くと **C-05 V1 がその peer の 2 plug で赤になる。**
3. **正規化 digest の規則は D-5 (1)(i) と D-4 (7) が設計で固定した** (v1.2。作業指示書送りにしない)。**コードは共有しない** (P-6)。
4. **掃除**: 期限切れ entry の削除は、`idempotency_entries` に当たったときの遅延回収で行う。**背景スレッドや定期ジョブは置かない** (P-1 の趣旨 = 往復をまたぐ機構を増やさない)。

#### 検査の形

- **C-23 (§6.2)** が (i)〜(v) を固定する。**あわせて C-07 (ii) の肯定枝が 4 plug で load-bearing になる** — **既存テストは 1 文字も変えずに、宣言が変わることで枝が入れ替わる** (これが宣言分岐型の利点である)。
- **変異**: 記録を data tx の外 (別コネクション) に移す → C-23 の「失敗した試行は記録を残さない」が赤。digest を key だけにする → (ii) の `CONFLICT` が出ず赤。再送で再実行する → (iii) の `affected` / `assigned_addresses` 一致が赤。再送応答の `request_id` を新規生成する → (v) と C-25 の相関 assert が赤。key スコープを credential 単位にする → C-23 の「別 credential・同 key = 同一要求」が赤。**照会を confirmation / target-existence の後に置く** → **C-23 (vii) の破壊操作 replay が赤** (v1.2 で追加。S-b)。**digest から `budget` / `transaction` / `confirmation` を除く** → 同一 key・別 `budget` が `CONFLICT` にならず C-23 (ii) が赤。
- **`CONDITIONS.md` の C-07 行の Status を更新する** — 「肯定枝は現在どの adapter からも到達されない」という開示を削り、「4 plug で load-bearing である」に書き換える (§6.4)。

#### 開示事項

- **`idempotency` は往復をまたぐサーバ側の記録である。** P-1 が禁じるのは「保持 lock / 保持接続 / 保持トランザクション」であり、**有限 bound を持ち、契約が既に 2 class で bound を定義済みの記録**はこれに当たらない。**この判断を明示的に書く** — 書かないと P-1 との関係が読み手に不明になる。
- **同一 Application 内で key 空間を共有するので、ある credential が別 credential の key と衝突させることができる。** これは**意図した設計** (A-5) であり、衝突は `CONFLICT` として決定的に返る。**「他 credential の結果が読める」ことにはならない** — 一致した場合に返るのは同一 Application 内の同一要求の結果であり、Application が権限境界である (SI-01)。**この点を C-23 行に開示する。**
- **保持場所は (A) application DB で確定したので、application を deprovision すると記録も消える。** これは正しい (Application が消えれば要求も無い)。
- **(8) の照会位置は「再送が破壊確認をすり抜ける」形ではない (v1.2 で追加。レビュー 2 B2)。** **記録に一致するのは「一度確認を通って commit した要求とバイト等価の要求」だけ**であり、確認は最初の実行時に既に行われている。**確認を通っていない要求は記録に一致しないので、通常どおり confirmation 段で拒否される。** **この点を C-23 行に開示する。**
- **再送で返す `SchemaOperationResult.revision` は元実行時点の値である (v1.1 で明記。レビュー 1 m9)** — `revision` は `required` の string であり、再送時点の現在 revision とは一致し得ない。**契約文案がこれを明記する** — 明記しないと、client が replay 応答の `revision` を「現在の revision」として precondition に使う。

---

### D-6 R-6 request budget

#### 決定

**(1) 要求側のフィールド。** `QueryRequest` / `MutationRequest` / `ScopedMutationRequest` / `SchemaOperationRequest` に **`budget`** (object、`additionalProperties: false`) を足す。プロパティは **`result_items` / `execution_ms` / `batch_items`** の 3 つで、**すべて optional、整数 ≥ 1** である。

**(2) 適用表 (endpoint ごとに意味を持つ class)。**

**v1.1 で `mutate` / `cross_entity_mutate` から `result_items` を外した** (レビュー 1 M3、監督裁定 R-g)。

| endpoint | `result_items` | `execution_ms` | `batch_items` |
|---|---|---|---|
| `query` (`POST /v1/data/{entity}/query`) | **適用** (返す行数) | **適用** | 適用外 |
| `mutate` (`POST /v1/data/{entity}/mutations`) | 適用外 | **適用** | **適用** |
| `cross_entity_mutate` (`POST /v1/data/mutations`) | 適用外 | **適用** | **適用** |
| `schema` (`POST /v1/schema/operations`) | 適用外 | **適用** | 適用外 |

**適用外の class を載せた要求は `VALIDATION_FAILED`** (`violated_declaration = budget`、`field = budget/<class>`)。**黙って無視しない。**

**`result_items` を mutation から外した理由**: **`result_items` の駆動点が peer で一致していない。** r2db は mutation の `affected` に**逐次** `limits.check("result_items", affected)` を掛ける (`r2db-api/src/r2db_api/structured.py:1272`、`r2db-api/src/r2db_api/postgres.py:1163`) が、**MitateDB は mutation の `affected` に対する検査を持たず** (`MitateDB-api/src/mitatedb_api/cell.py` の `result_items` 参照は `:837` / `:1808` / `:1836` のみ)、read 経路の**要求 `limit` の事前検査**としてのみ持つ (`cell.py:834-837`)。**mutation に `budget.result_items` を受け付けさせると、MitateDB に新しい強制点を実装させることになり、それは「budget が既存 bound を下回る方向に効く」ではなく配備 bound の意味の変更である** — P-5 (bound は安全上必要なものだけ) に反する。**この非対称そのものは本フェーズで変えず、台帳 L9-11 に起票する。**

**(3) 規則 (P-5)。**

- **実効 bound = min(配備値, budget)。**
- **`budget` が配備値を上回る値なら `VALIDATION_FAILED`** (`violated_declaration = budget`)。**budget は配備値を上回る方向には一切効かない。**
- **超過は既存どおり `LIMIT_EXCEEDED` + `details.limit_class`** — **budget 由来か配備値由来かを区別しない** (区別すれば配備値の露出になり、また client にとって意味が同じである)。
- **`budget` の妥当性検査 (適用外 class・配備値超過・非整数のいずれも) は要求の検証段で行う (v1.2 で追加。レビュー 2 M8、監督裁定 S-l)** — shape validation と同じ段であり、`destructive_confirmation.evaluation_order` が言う target-existence / confirmation / precondition の**前**である。**帰結: 配備値超過の `budget` を持つ未確認の `delete` は `VALIDATION_FAILED` を返す** (`DESTRUCTIVE_CONFIRMATION_REQUIRED` ではない)。**これを契約文案に 1 文で書く。**
- **`rows_scanned` は含めない** (計画文書 §6 の却下済み案)。

**(4) 能力**: `request_budget` を `capability_status.defined` に新設する。

**(5) 注入点は F-18 の各行である** — r2db は deadline 生成 3 箇所 (`service.py:999` / `:1039` / `:1074`) と `limits.check_*` の実効値、MitateDB は `_limit_gate` の deadline (`cell.py:541`) と `transact` / read の参照行 (`cell.py:1162` / `:835-836`)。

#### 契約文案 (英語)

**`limits.request_budget`**:

> `budget` lets one request ask for a smaller bound than the deployment's own, and only a smaller one. Where a request carries `budget.<class>`, the bound in force for that request is the smaller of the deployment's declared value for that class and the requested value; a request whose `budget.<class>` exceeds the deployment's own declared value is refused with `VALIDATION_FAILED` and `details.violated_declaration: budget`, rather than being silently reduced -- a client that asked for more than the deployment allows has misread the deployment's own declaration, and telling it so is more useful than granting it less than it asked for. Exceeding a bound that is in force because a `budget` narrowed it is refused exactly as exceeding the deployed bound is: `LIMIT_EXCEEDED` with `details.limit_class` naming that class, without distinguishing which of the two values was the smaller. Three classes are budgetable in this version: `result_items`, `execution_ms` and `batch_items`. Each applies only where it has meaning: `result_items` and `execution_ms` on a query; `execution_ms` and `batch_items` on a single-entity or cross-entity mutation; `execution_ms` alone on a schema operation. `result_items` is not budgetable on a mutation: it bounds the rows a query returns, and this version does not give one request a way to narrow how many rows its own mutation may affect. A `budget` naming a class that does not apply to the endpoint it was sent to, or carrying a value that is not an integer of at least 1, is refused with `VALIDATION_FAILED`, `details.violated_declaration: budget` and `details.field` naming that class within `budget`; it is not ignored. Every one of those refusals belongs to validating the request itself: a `budget` is checked where this contract's own request shape is checked, before target existence, destructive confirmation and precondition evaluation, so a request that is both unconfirmed and carrying an invalid `budget` is refused for the `budget` first. `budget` never raises a bound, never introduces a class outside `limits.classes`, and never changes what this deployment declares at capability discovery -- the declared values remain the deployment's own, and a `budget` is one request's own narrowing of them.

#### 根拠 (file:line)

- 3 class の実際の検査位置: `r2db-api/src/r2db_api/structured.py:1243` / `postgres.py:1129` (batch_items)、`structured.py:1198` / `:1272` / `postgres.py:1163` (result_items)、`service.py:999` / `:1039` / `:1074` と `postgres.py:1943-1959` (execution_ms)。MitateDB は `cell.py:1162` (batch_items)、`cell.py:834-837` (result_rows)、`cell.py:541` + `backend_sqlite.py:24-35` + `backend_postgres.py:1123-1157` (execution_ms) (F-18)。
- 配備値の出所: `r2db-api/src/r2db_api/limits.py:12-20` (**env override 無し**)、`MitateDB-api/src/mitatedb_api/config.py:20-220` (`MITATEDB_MAX_*` で上書き可) (F-18)。**この非対称は本フェーズでは変えない** (台帳 L9-3)。
- `LIMIT_EXCEEDED` の details 規則の前例: 契約 `errors.details_vocabulary.LIMIT_EXCEEDED.limit_class` (F-8)。
- `rows_scanned` を含めない根拠: 計画文書 §6 の却下表 (「既存 limit class に無く、SQLite / PostgreSQL / in-memory で観測の意味が揃わない」)。

#### 実装の形

1. **契約 (WP-1)**: 4 request schema に `budget` を optional で足し、`limits` に `request_budget` 節を足し、`capability_status.defined` に `request_budget` を足す。
2. **r2db (WP-2d) / MitateDB (WP-3d)**: **配備値を読む 1 点で「実効値」を作る形にする** — 検査点を個別に書き換えるのではなく、要求ごとに `effective_limits = deployed.narrowed_by(budget)` を作り、既存の検査点はそれを見る。**これにより「budget が効かない検査点が 1 つ残る」形を構造的に排除する。**
3. **`budget` の妥当性検査 3 種 (適用外 class・配備値超過・非整数) をまとめて request-shape の直後に置く** — 実行前拒否であることと、`evaluation_order` に対する位置 (target-existence / confirmation より前) を C-24 が assert する (v1.2。S-l)。

#### 検査の形

- **C-24 (§6.2)** が「下回る方向のみ」「適用外 class の拒否」「超過の `LIMIT_EXCEEDED`」を固定する。
- **変異**: `min` を `max` にする → C-24 の「budget で narrow した bound が効く」が赤。配備値超過を黙って clamp する → C-24 の `VALIDATION_FAILED` assert が赤。適用外 class を無視する → C-24 の拒否 assert が赤。`limit_class` を budget 専用の値にする → C-24 の code / details assert が赤。**`budget` の妥当性検査を confirmation の後に移す** → C-24 の順序 assert (2 違反同時要求) が赤 (v1.2。S-l)。
- **非 vacuity**: C-24 は**実際に budget で narrow した位置で拒否されること**を観測する — 「宣言どおりの位置」を N / N+1 で挟む形は C-05 V2 の driver と同型である。**フェーズ8 の教訓 L8-15 (「配線されているだけ」を排除する) に従い、adapter が `budget` を捨てる変異が赤になることまでを実測する** (§6.2)。

#### 開示事項

- **`execution_ms` の budget は `reference_wall_clock` の下にある** — 両 peer とも `execution_ms` の宣言語は `reference_wall_clock` であり (フェーズ8 D-1)、**budget もその精度を超えない**。**C-24 は `execution_ms` の位置を測らない** (C-05 V2 が `execution_ms` を駆動しないのと同じ理由: 決定的な N+1 を構成できない)。
- **C-24 の非 vacuity を確実に駆動する class は `batch_items` である (v1.1 で確定。レビュー 1 M3)** — **両 peer とも要求内の operation 件数で N / N+1 を決定的に構成できる** (`r2db-api/src/r2db_api/structured.py:1243`、`MitateDB-api/src/mitatedb_api/cell.py:1162`)。**`result_items` は query 経路にのみ適用されるが、MitateDB の拒否は返した行数ではなく「要求された `limit` の値」で決まる** (`MitateDB-api/src/mitatedb_api/cell.py:834-837`) **ので、行を入れて N / N+1 を挟むレシピが両 peer で同型にならない。** **WP-1 が「両 peer で `result_items` を budget だけで駆動できる query の形」を実測して選び、選べなければ `batch_items` のみを非 vacuity の対象とし、`result_items` を C-24 行に「駆動せず」として開示する** — **駆動できない class を「駆動する」と設計に書かない** (L8-15 の教訓)。
- **r2db は配備時の limits env override を持たない** (F-18)。**budget は「配備値より小さくする」機構なので、配備値を動かせないことは budget の有効性に影響しない**が、**同型性の差として台帳 L9-3 に記録する。**

---

### D-7 R-7 成功応答の `request_id`

#### 決定

**(1) `QueryResult` / `MutationResult` / `SchemaOperationResult` に `request_id` (string) を足す。** **schema 上は optional であり、`required` 配列は不変である** (1.6.0 の `surfaces` と同じ形。F-20)。

**(2) ただし 1.7.0 を宣言する peer は必ず載せる (無条件義務)。** **schema optional と義務必須の組み合わせは意図したものである** — schema を `required` にすると 1.6.0 実装の応答が 1.7.0 schema に適合しなくなり、`versioning.compatibility` が言う semantic change になる。**義務側で必須にすることで、追加の additive 性を保ったまま「載せても載せなくてもよい」空振りを避ける** (§4 A-8)。

**(3) 値は監査行の `request_id` と同一である** (F-17)。**in-process 経路でも生成する** — r2db は `_event` が既に `request_id` を持つのでそれを応答へ回し、MitateDB も同型にする。**現在はどちらも HTTP 層でのみ生成しているので、生成点を service / cell 層へ下げる。**

**(4) client 提供値は受け取らない。** 要求側に `request_id` を足さない。**サーバ生成のみである** — client が指定できる形にすると、監査行の識別子を client が制御できることになり、SI-14 (相関可能な証拠) の意味が弱まる。**これは現行の実装形 (F-17: 両 peer ともサーバ生成、client 提供値を監査に載せた前例なし) をそのまま契約に固定するものである。**

#### 契約文案 (英語)

**`schemas.QueryResult.properties.request_id.description` (3 result schema 共通。正本は下記 `version_binding` の無条件義務 (b) と、`errors.shape.request_id` の既存記述との対応)**:

> `request_id` is the service's own identifier for the request this result answers -- the same identifier its audit evidence for that request carries, and the same shape `errors.shape.request_id` already names on a denial. It is generated by the service; this contract defines no way for a client to supply or influence it. It is declared as an optional property so that a response written under an earlier version remains valid against this schema; an implementation declaring 1.7.0 carries it on every successful `QueryResult`, `MutationResult` and `SchemaOperationResult` it returns (`versioning.version_binding`). Where a request is answered from an idempotency record rather than executed, the `request_id` returned is the original execution's own, not a new one (`structured_operations.idempotency.correlation`).

#### 根拠 (file:line)

- 現行の生成点と監査への搭載: `r2db-api/src/r2db_api/http.py:133`、`r2db-api/src/r2db_api/service.py:1165-1198`、`MitateDB-api/src/mitatedb_api/http.py:231` (F-17)。
- 成功応答に無いこと・schema が閉じていること: 契約 `schemas.QueryResult` / `MutationResult` / `SchemaOperationResult` (いずれも `additionalProperties: false`)、両 peer の `_check_object_shape` (F-17)。
- optional 追加の前例 (`required` 不変): 契約 `schemas.CapabilityDocument.properties.surfaces` (1.6.0、F-20)。
- 既存の `request_id` の位置づけ: 契約 `errors.shape` が denial 側に `request_id` を既に持つ。**本項は成功側に同じ識別子を出す**ものであり、新しい概念ではない。

#### 実装の形

1. **契約 (WP-1)**: 3 result schema に `request_id` を optional で足す。**`required` は変えない。**
2. **r2db (WP-2e) / MitateDB (WP-3e)**: 生成点を service / cell 層へ下げ、in-process の戻り値にも載せる。**HTTP 層は下位が返した値をそのまま出す** (HTTP 層で再生成しない — すれば監査行と食い違う)。
3. **idempotency の再送応答は記録済みの `request_id` を返す** (D-5 (v))。

#### 検査の形

- **C-25 (§6.2)** が「成功応答に `request_id` があること」「要求ごとに異なること」「`audit_query` が利用可能な plug では当該 mutation の監査行の `request_id` と一致すること」を固定する。**無条件義務なので `xfail(strict=True)` を版宣言に条件付ける** (D-1 (7))。
- **変異**: HTTP 層で `request_id` を再生成する → C-25 の監査行一致が赤。同一値を返し続ける → 一意性 assert が赤。in-process 経路で載せない → in-process 2 plug が赤。idempotency 再送で新規生成する → C-23 / C-25 の相関 assert が赤。

#### 開示事項

- **監査行との一致は `audit_query` が利用可能な plug でのみ観測できる。** **利用不能な plug では「存在・一意」までである。** **どの plug で監査照合まで届いたかを C-25 行に開示する** — 「4 plug で緑」が「4 plug で監査照合した」を意味しないことを明示する。
- **`request_id` は不透明である。** 形式 (uuid4 等) を契約が定めない。**client は等値比較だけを行う。**

---

### D-8 R-8 派生の操作カタログ + L8-9

#### 決定

**(1) 生成元は契約 JSON のみである。** 生成器は**純粋な射影**であり、自然文を解釈しない (§4 A-7)。**そのために 1.7.0 が機械可読の構造化フィールドを契約 JSON に足す** — F-20 のとおり、現行 JSON からは role / destructive / atomicity / 能力依存が機械的に導けないからである。

**(2) 契約に足す構造化フィールド。**

| json_path | 形 | 既存の自然文との関係 |
|---|---|---|
| `endpoints.*.roles` / `control_endpoints.*.roles` | 配列。値は `runtime` / `developer` / `control` / `audit` (`CapabilityDocument.role` の enum と同じ 4 語) | 既存 `auth` 文と**両立**し、**両者の一致を register テストで固定**する。写像は `application → {runtime, developer}`、`control → {control}`、`audit → {audit}`、`"X or Y"` は和集合。 |
| `endpoints.*.requires_capability` / `control_endpoints.*.requires_capability` | 配列。`capability_status.defined` のキー | 現行は `capability_status.defined` の説明文と `version_binding` に分散。**register が「値が `capability_status.defined` に実在する」ことを固定する。** |
| `endpoints.*.atomicity` / `control_endpoints.*.atomicity` | **固定語彙 3 語**: `atomic` / `none` / **`atomic_unless_best_effort`** (**v1.2 で `per_item_when_declared` から改名。監督裁定 S-n** — 既定が atomic であることを語そのものに含める) | `transactions` 節の意味を endpoint に割り付ける。`query` / `catalog` / `capabilities` / `audit_query` = `none`、`mutate` = **`atomic_unless_best_effort`** (契約 `endpoints.mutate.semantics` の「atomic unless explicitly declared best_effort」)、`cross_entity_mutate` = `atomic`、`schema` = `atomic`。 |
| `destructive_confirmation.applies_to_structured` | 配列。要素は `{endpoint, operation}` 等の構造化値 | 既存 `applies_to` の擬似式配列と **1:1 対応**することを register が固定する。**既存 `applies_to` は残す** (§4 A-6 と同じ理由)。 |
| `versioning.obligations` | 版ごとの配列 (下記 (3)) | 既存 `version_binding` 散文と、**版集合の一致**および**「N of those obligations are unconditional」の件数一致**を register が固定する。**散文は残す** (§4 A-6)。 |

**(3) `versioning.obligations` の形。**

```json
{
  "versioning": {
    "obligations": [
      {
        "version": "1.7.0",
        "subordinate_ruling": 12,
        "unconditional": [
          "details_vocabulary_on_validation_identifier_and_capability_denials",
          "request_id_on_every_successful_result"
        ],
        "conditional": [
          {"obligation": "constraint_declarations_accepted_and_enforced_on_schema_operations",
           "capability": ["constraint_declarations", "schema_operations"]},
          {"obligation": "field_constraints_total_in_entity_descriptor",
           "capability": ["constraint_declarations", "application_catalog"]},
          {"obligation": "dry_run_decides_as_the_real_request_and_leaves_no_external_effect",
           "capability": ["dry_run"]},
          {"obligation": "idempotency_key_recorded_with_request_digest_and_replayed_within_retention",
           "capability": ["idempotency"]},
          {"obligation": "request_budget_narrows_only_downward",
           "capability": ["request_budget"]}
        ]
      }
    ]
  }
}
```

**`capability` を配列にする理由**: 1.7.0 の 2 件は「`constraint_declarations` が提供されており、かつ `schema_operations` (または `application_catalog`) が提供されている」という**連言**である。1.6.0 の条件付き義務は単一 capability だったので、**配列にすることで 1.6.0 の既存 2 件も 1 要素配列として同じ形に載る。** **要素間は AND である**ことを `versioning.obligations_note` に明記する。

**過去版 (1.2.0〜1.6.0) も載せるが、載せるのは `version` / `subordinate_ruling` と、散文から機械的に写せる義務だけである (v1.1 で改訂。レビュー 1 M5、監督裁定 R-i)。** **散文が持つ限定句・例外・補筆はすべて散文側に残す。** `obligations` は**索引であって代替ではない**。

**`unconditional` / `conditional` の件数照合は、散文が件数語を持つ版にのみ掛ける。** **付録 A (iii) の実測が示すとおり、「N of those obligations are unconditional」の文を持つのは 1.4.0 と 1.6.0 の 2 段落だけであり**、1.3.0 と 1.5.0 のブロックは (a)/(b)/… も (1)/(2)/… もマーカーを 1 つも持たず (extraction status = failed)、1.2.0 は無条件 / 条件付きに分かれていない (partial)。**したがって照合対象は 1.4.0 / 1.6.0 / 新設の 1.7.0 の 3 版であり、register はその「対象版数 = 3」も assert する** (空振り防止)。**件数語を持たない版の段落に件数語を足す形は採らない** — **1.5.0 段落は `PIN_1_5_0_SENTENCE_1..3` (`conformance-tests/test_contract.py:447-464`) が掛かる依頼者確定文言であり、件数照合のために確定文言を書き換えることはしない。**

**(4) 「返し得る code」は §5 U-5 = (B) で確定した** — **`endpoints.*.error_codes` は初版のカタログに含めない。** **「resource cost の概算」は含めない** (計画文書 §6 の却下済み案)。**計画文書 §5 R-8 が列挙していた項目を外すので、計画文書 §8 の R-8 行に R-14 の規約で根拠と日付を残す** (§10、改版そのものは WP-4 で行う)。

**(5) 生成器と artifact。** **`tools/contract_catalog.py`** (標準ライブラリのみ — `tools/` の既存規約) が **`spec/OPERATION_CATALOG.json`** を書き、**`conformance-tests/test_operation_catalog_register.py`** が再生成して **byte 一致**を assert する。**`/v1/capabilities` からの参照は `CapabilityDocument` に optional 1 項目 `operation_catalog_url` を足す** (`surfaces` の前例)。**義務にはしない** (D-1 (2) の 3 種目)。

**(6) P-7**: 契約 JSON に足す構造化フィールドは**現行の意味だけ**である。**経緯文は書かない** (書けば R-10 (B) が減らした分を足し戻すことになる)。

#### 契約文案 (英語)

**`versioning.obligations_note`**:

> `obligations` is a machine-readable index of what `version_binding` states in prose: for each version label, the numbered contract decision that introduced it, the obligations that bind unconditionally, and the obligations that bind only where the named capabilities are declared as something other than `unavailable`. Where an entry names more than one capability, all of them must be so declared for that obligation to bind. This index is derived from `version_binding` and does not replace it: every limiting clause, exception, same-label addendum and scoping sentence lives in the prose, and where the two could be read as disagreeing, the prose is the contract. The two are held in agreement mechanically -- the set of version labels must match between them, and so must each version's own count of unconditional obligations, where the prose states one.

**`ruling` の語を避けているのは意図である (v1.1 で明記。レビュー 1 M7、監督裁定 R-k)** — `conformance-tests/test_contract_history_register.py:64-79` の `_PATTERNS` は裸の `ruling` を provenance マーカーとして拾うので、この語を含む新規契約値は **companion に `## <json_path>` セクションを要求し、heading 集合一致 (`:198`) を赤にする。** **v1.0 の文案は "the subordinate ruling that introduced it" と書いており、この地雷を実際に踏んでいた** — v1.1 で "the numbered contract decision that introduced it" に改めた。

**`versioning.version_binding` に足す 1.7.0 段落 (既存 1.6.0 段落の直後、retroactive-denial の総括文の前に置く)**:

> Only an implementation declaring 1.7.0 or higher additionally claims conformance to the obligations 1.7.0 introduces (subordinate ruling 12). Two of those obligations are unconditional in the same sense as every obligation enumerated above -- they bind simply by declaring 1.7.0, independent of any capability's own status: (a) every denial it answers with VALIDATION_FAILED, IDENTIFIER_INVALID or CAPABILITY_UNSUPPORTED carries the details keys errors.details_vocabulary requires for that code, with violated_declaration drawn from the closed vocabulary named there, and carries no row value, no suggested value, no corrective action and no internal name; and (b) every successful QueryResult, MutationResult and SchemaOperationResult it returns carries request_id, the same identifier its own audit evidence for that request carries. The remaining 1.7.0 obligations are conditional, in the same sense 1.4.0's and 1.6.0's own conditional lists are: they bind only insofar as the implementation's own capabilities() declares the named capability -- or, where two are named, both of them -- as something other than unavailable. Where it declares constraint_declarations and schema_operations both as something other than unavailable: (1) a create_entity it executes accepts field_constraints, an add_field and an alter_field it executes accept enum and nullable, each field is created or altered with the constraints declared there, those constraints are enforced on every value written to that field, and an alter_field whose declared constraints existing rows would violate is refused in full with CONFLICT, changing nothing. Where it declares constraint_declarations and application_catalog both as something other than unavailable: (2) every EntityDescriptor it returns carries field_constraints, total over that entity's own fields, reporting nullable: true and no enum for a field that declares neither. Where it declares dry_run as something other than unavailable: (3) a request carrying dry_run receives the decision the identical request without it would receive -- the same code and the same details on a refusal, the same affected count on a success -- and leaves no externally visible state change, subject to the two consumptions structured_operations.dry_run.external_effects names; and a plan it returns is deterministic, and is verified by recomputation on the real request, refusing with PRECONDITION_FAILED where it no longer agrees. Where it declares idempotency as something other than unavailable: (4) an idempotency_key is recorded with a digest of the request it accompanied, in the same transaction as that request's own effects; the same key with the same digest, resent within idempotency_retention_ms, returns the original result without re-executing, including the original request_id; and the same key with a different digest is refused with CONFLICT. Where it declares request_budget as something other than unavailable: (5) a budget narrows a bound downward only, a budget above the deployed value or naming a class that does not apply to that endpoint is refused with VALIDATION_FAILED, and exceeding a narrowed bound is refused with LIMIT_EXCEEDED naming that limit class. 1.7.0 introduces no obligation on what a client must send: dry_run, plan, budget, field_constraints, enum, nullable, and SchemaOperationRequest.idempotency_key are optional wherever they appear, and a request valid under 1.6.0 stays valid. An implementation still declaring 1.6.0 is not held to any 1.7.0-only obligation retroactively.

**retroactive-denial の 4 文への追記案 (既存文の末尾側の列挙に `1.7.0-only` を足す。PIN 定数 4 件が対応する)**:

| 対象 | 1.6.0 での現行文 (PIN) | 1.7.0 での案 |
|---|---|---|
| 1.1.0 行 | `is not held to any 1.2.0-only, 1.3.0-only, 1.4.0-only, 1.5.0-only, or 1.6.0-only obligation retroactively` | `is not held to any 1.2.0-only, 1.3.0-only, 1.4.0-only, 1.5.0-only, 1.6.0-only, or 1.7.0-only obligation retroactively` |
| 1.2.0 行 | `is not held to any 1.3.0-only, 1.4.0-only, 1.5.0-only, or 1.6.0-only obligation retroactively` | `is not held to any 1.3.0-only, 1.4.0-only, 1.5.0-only, 1.6.0-only, or 1.7.0-only obligation retroactively` |
| 1.3.0 行 | `is not held to any 1.4.0-only, 1.5.0-only, or 1.6.0-only obligation retroactively` | `is not held to any 1.4.0-only, 1.5.0-only, 1.6.0-only, or 1.7.0-only obligation retroactively` |
| 1.4.0 行 | `is not held to any 1.5.0-only or 1.6.0-only obligation retroactively` | `is not held to any 1.5.0-only, 1.6.0-only, or 1.7.0-only obligation retroactively` |

**新しい行 (1.6.0 に対する retroactive denial)**: **上の 1.7.0 段落の最終文がそれである** — `An implementation still declaring 1.6.0 is not held to any 1.7.0-only obligation retroactively.` **これは 1.6.0 が 1.5.0 に対して採った形とまったく同じである** (`conformance-tests/test_contract.py:576-581` のコメントが「the 5th row (1.5.0 vs 1.6.0-only) is supplied by confirmed-prose block (4) itself (its own last sentence)」と明記している)。

**1.5.0 行の扱い (§5 U-8 #24 = (a) で確定した)**: 現行の 1.5.0 に対する retroactive denial は **1.6.0 段落の最終文** `An implementation still declaring 1.5.0 is not held to any 1.6.0-only obligation retroactively.` であり、**`PIN_1_6_0_VERSION_BINDING_PARAGRAPH` (`conformance-tests/test_contract.py:563`) に含まれる依頼者確定文言である。** **確定した改訂文は次のとおりである** — 既存文を広げる:

> An implementation still declaring 1.5.0 is not held to any 1.6.0-only or 1.7.0-only obligation retroactively.

**確定の理由**: #23 で retroactive-denial 4 文の PIN が同時に動くので、**同じ主題 (どの版がどの版の義務を遡って課されないか) を 1 箇所に保つ**方を採る。**帰結として `PIN_1_6_0_VERSION_BINDING_PARAGRAPH` は「R-10 (B) の剥離後の文字列」と「この 1 文の改訂」の両方を反映した形に書き換える** (§6.3)。

**件数**: **1.7.0 の義務は無条件 2 件・条件付き 5 件、計 7 件である。** `versioning.obligations` の 1.7.0 エントリもこの件数と一致する。

#### 根拠 (file:line)

- 現行 JSON から機械的に導けないこと: 契約 `endpoints` / `control_endpoints` の要素が `{method, path, auth, request, response, semantics}` のみであること、`auth` が自然文であること、`destructive_confirmation.applies_to` が擬似式の文字列配列であること、`errors.codes` が全域 1 本であること (F-20)。
- `version_binding` の構造と件数 assert: F-21、`conformance-tests/test_contract.py:319-360` (`(\w+) of those obligations are unconditional` の正規表現照合と `CCR_DISPOSITION.md` との突合)。
- retroactive-denial の PIN と「5 行目は段落最終文が供給する」規約: `conformance-tests/test_contract.py:576-593`。
- optional 追加の前例: `schemas.CapabilityDocument.properties.surfaces` (F-20)。
- L8-9 の起票内容: フェーズ8 設計 §10 L8-9 (「10,269 字の単一文字列を配列に組み替える案は R-8 と同じ問題であり、再生成一致テストと同時にしか行えない」)。

#### 実装の形

1. **契約 (WP-1)**: 上記 5 種の構造化フィールド + `versioning.obligations` + `obligations_note` + 1.7.0 段落 + retroactive-denial の更新。
2. **`tools/contract_catalog.py`** (標準ライブラリのみ): 契約 JSON を読み、endpoint ごとに `{name, method, path, roles, requires_capability, atomicity, destructive, request_schema, response_schema}` を射影して `spec/OPERATION_CATALOG.json` を書く。**決定的な出力である** (キー順固定、インデント固定、末尾改行あり)。
3. **`conformance-tests/test_operation_catalog_register.py`**: 再生成して byte 一致、および (i) `roles` ↔ `auth` の一致、(ii) `requires_capability` の値が `capability_status.defined` に実在、(iii) `atomicity` の値が固定 3 語、(iv) `applies_to_structured` ↔ `applies_to` の 1:1、(v) `obligations` の版集合 ↔ 散文の版集合、**(vi) 件数語を持つ版についてのみ無条件件数 ↔ 散文の件数語**。**(vi) の実装規則を設計で固定する (v1.1。レビュー 1 M5、監督裁定 R-i)**: **散文から「`N of those obligations are unconditional` の文を持つ版」の集合を抽出し、その集合についてのみ件数一致を assert する。集合の要素数が 3 (1.4.0 / 1.6.0 / 1.7.0) であることも assert する** — **集合が空なら赤にする** (空振り防止)。
4. **既存テストの非破壊を WP-1 の完了条件にする (v1.1。レビュー 1 M5 の 4)**: `conformance-tests/test_contract.py:343-360` の `re.search(r"(\w+) of those obligations are unconditional")` は**最初の 1 件 (1.4.0) しか拾っていない**。**1.6.0 段落の直後に 1.7.0 段落を挿入しても、この既存 assert が 1.4.0 を拾い続けること (= 壊れないこと) を WP-1 が実測して §11.1 に記録する。** **新設 2 本を足すだけでなく、既存 1 本の挙動を検証する。**
5. **`CapabilityDocument.operation_catalog_url`**: optional。**両 peer は本フェーズでは宣言しない** (義務でないため)。**宣言しない選択を台帳 L9-4 に記録する。**
6. **provenance スキャナへの 0 ヒットを WP-1 の完了条件にする (v1.1。レビュー 1 M7、監督裁定 R-k)**: **1.7.0 が新設 / 改訂したすべての契約 JSON 値** (`obligations_note`、`dry_run` 3 段落、`idempotency` 3 段落、`request_budget`、`enum_members`、`roles` / `requires_capability` / `atomicity` の description、`details_vocabulary` の各ブロック等) **に対して `conformance-tests/test_contract_history_register.py:64-79` の `_PATTERNS` を走らせ、ヒットが 0 件であることを実測して §11.1 に記録する。** **ヒットがあれば、その値の文言から経緯語を落とすのが既定であり (P-7)、落とせない場合にのみ companion に anchor を足す。**

#### 検査の形

- **register テストが 6 項目 (上記 3 の (i)〜(vi)) を固定する。** **変異**: `roles` の 1 要素を消す → (i) が赤。`atomicity` に 4 語目を入れる → (iii) が赤。`obligations` の 1.7.0 の `unconditional` を 3 件にする → (vi) が赤。`spec/OPERATION_CATALOG.json` を手で編集する → 再生成一致が赤。
- **`@pytest.mark.condition` は付けない** — これはリポジトリ衛生の固定であり、peer 実装に対する implementation-independent な要求ではない (フェーズ8 §6.6 の 3 と同じ扱い)。

#### 開示事項

- **`obligations` は索引であって契約の代替ではない。** 契約文案の `obligations_note` がそう明記する。**「散文が正本である」ことを契約自身が言う**形にしないと、機械可読側を読んだエージェントが限定句を見落とす。
- **`roles` は「その endpoint が受け付ける role」であって「その role が必ず成功する」ではない** — capability や authority の判定が別に掛かる。**この点を `roles` の description に書く。**
- **1.2.0〜1.6.0 分の `obligations` は「散文から機械的に写せる範囲だけ」である。** **写せなかった限定句が存在すること自体を `obligations_note` が開示する。** 完全性は主張しない。

---

### D-9 R-10 (B) 接頭辞剥離 (1.7.0 同梱)

#### 決定

**手順は第 15 次引き継ぎ §4-3 のとおり 5 段である。**

1. **対象 29 値の before/after 一覧を依頼者に提示して再確定を得る** (**付録 B**。**18 値が依頼者確定文言**である。常設規律 4)。→ §5 U-6。
2. **`spec/CONTRACT_HISTORY_MANIFEST.json` を置く** — json_path → 剥がした接頭辞 / 挿入句の**逐語**。
3. **分離前後の JSON をマニフェストの逆適用後に deep-equal 比較する使い捨て検証**を行う。**`tools/` に常設しない** (フェーズ8 §4 の却下表: 「1 回きりの移行の検証である」)。scratchpad で実行し、**結果 (差分 0 と走査キー数) を §11.1 に記録する。**
4. **契約 JSON と両 peer の packaged 複製 2 本を同一コミットで同一バイトに更新する。**
5. **PIN 定数を書き換える — 剥離によって実際に不一致になるのは `PIN_1_5_0_SENTENCE_1` の 1 件だけである (v1.2 で実測に訂正。レビュー 2 M1、監督裁定 S-e)。** **動かない 14 定数には手を入れない** (常設規律 4 の趣旨)。**`PIN_1_5_0_SENTENCE_1` は依頼者確定文の内側に provenance 接頭辞を含み、3 つの json_path に照合される** — `versioning.version_binding` (unstripped なので接頭辞は残る) と `audit.query_operation_vocabulary` / `audit.query_target_kind_vocabulary` (剥離対象なので接頭辞が消える)。**確定: 定数を 2 つに分ける** — **`PIN_1_5_0_SENTENCE_1` (接頭辞付き。`version_binding` の照合に使う) と `PIN_1_5_0_SENTENCE_1_STRIPPED` (接頭辞なし。audit の 2 path の照合に使う)。規範文は同一であり、違いは接頭辞の有無だけである。**

**1.7.0 で動く PIN の全一覧は 7 件である (v1.2。S-e)**: `PIN_1_5_0_SENTENCE_1` の 2 定数分割 (1 件) + retroactive-denial 4 定数 (§5 U-8 #23) + `PIN_1_6_0_VERSION_BINDING_PARAGRAPH` (#24) + `PIN_1_6_0_ITEM_3_FIELD_TYPES` (#28)。**後の 6 件は剥離ではなく 1.7.0 の文言改訂で動くものである。**

**register テストの改版 (v1.1 で明確化。レビュー 1 M6、監督裁定 R-j)**: `conformance-tests/test_contract_history_register.py` の**スキャナとすべての照合を、「契約 JSON にマニフェストを逆適用した値」に対して行う**。

- **companion の quote は従来どおり「マーカーを含む値の全文」である** — すなわち**剥離前の原文**であり、**逆適用後の値と byte 一致する。** 照合対象を「契約 JSON の値」から「契約 JSON の値にマニフェストの `stripped_prefix` / `stripped_insert` を逆適用した値」へ変えるだけであり、**`spec/CONTRACT_HISTORY.md` の 29 セクションの Value 本文は動かさない。**
- **`Since` 照合は逆適用後の値から読む** — quote 内に `Since X.Y.Z` が残るので **`assert checked == 17` (`conformance-tests/test_contract_history_register.py:352`、実行位置 `:388`) は無改訂で通る。** **通ることを WP-1 が実測して §11.1 に記録する。**
- **v1.0 は「quote は逆適用後の値と byte 一致し、`Since` 照合はマニフェスト側の接頭辞から読む」と書いており、この 2 つは両立しない** (逆適用後なら `Since` は quote 内に残るので、マニフェストから読む必要が無い)。**v1.1 は前者に寄せて確定した** — どちらを quote に置くかを実装裁量にしない。
- **新規 assert を 1 本足す**: **「剥離後の契約 JSON にはスキャナがヒットする値が 0 件である」** (`unstripped: true` の 3 値を除く)。**これが「剥がしたつもりで剥がし残した」を赤にする。**

**`schemas.AuditResult.properties.events.items.description` の扱い (v1.2 で新設。レビュー 2 B4、監督裁定 S-d)**: **この値は挿入句 ` (subordinate ruling 7(A))` を剥がしても規範文の中に裸の `ruling` が残り、上の新規 assert が赤になる** (レビュー 2 の実測)。**確定は (b) である** — **接頭辞 `Deliberately left open (subordinate ruling 7(A)): ` を挿入句として剥がしたうえで、末尾の `this ruling closes` を `this contract closes` に改める。** **剥離後の値**:

> audit.fields is itself an open-ended, additive vocabulary, and a per-event shape is not one of the 11 response schemas or nested row schemas this contract closes.

**先頭の `audit.fields` は小文字の識別子なので大文字化しない。** **この値は PIN 定数を持たない** (付録 B #18「none found」) **ので、依頼者確定文言の破棄には当たらない。** **改訂の理由は「剥がした挿入句への後方参照が宙に浮くため」である** — `this ruling` が指していた `(subordinate ruling 7(A))` が値から消えるので、参照先を契約自身に付け替える。**マニフェストにはこの語改訂を `rewrite: {"from": "this ruling closes", "to": "this contract closes"}` として記録し、逆適用は「接頭辞の復元 + 語の復元」で元値と byte 一致させる。** **`unstripped` は 3 件のままである。**

**「剥がせない値」の扱い**: 規範文と不可分でマーカーを外せない値は、**マニフェストに `unstripped: true` で残し、その件数を台帳 (L9-5) に記録する。** **黙って対象から外さない。** **`unstripped` = 3 件** (`versioning.version_binding` / `versioning.compatibility` / `destructive_confirmation.phrase_construction.rules[3]`) **であり、残り 26 件は、S-d を織り込んだ確定後の分類で `strip-prefix` 14 / `strip-insert` 11 / 両方 1 である** (草案時点は `strip-prefix` 13 / `strip-insert` 12 / 両方 1 だった。**#18 が `strip-insert` から「接頭辞全体の除去 + 1 語の改訂」へ移ったことによる 1 件の移動である**。付録 B #18 の注記)。

**意味の保存**: 「conditional on X being provided -- versioning.version_binding」という挿入句が運んでいた情報は、**`versioning.obligations` (D-8) が機械可読に持つ**ので、剥がしても失われない。**これが (B) を 1.7.0 と同時に行う技術的な理由である** (再確定が 1 回で済むという運用上の理由に加えて)。

**確定した剥離範囲 (§5 U-6。v1.1)**: **付録 B の 29 値のうち機械的に分離できた 26 値をマニフェスト草案どおり剥がし、加えて次の 2 件を草案に追加して剥がす。**

- **(a) `security.schemes.application_credential.description` と `security.schemes.control_credential.description`** (付録 B #25 / #26): 値中の `Since 1.6.0 (subordinate ruling 11, item 1; unconditional -- versioning.version_binding): ` を**挿入句全体 (「Since 1.6.0」を含む) として剥がし、`Since 1.6.0: ` を残さない。**
- **(b) `control_endpoints.revoke_credential.semantics`** (付録 B #9): 末尾文 `Resolved in contract 1.2.0 (previously a pending contract decision, the destructive-confirmation semantics question).` を**文全体として剥がす** (草案は括弧内のみを剥がし `Resolved in contract 1.2.0.` を残していた)。
- **(c) `schemas.AuditResult.properties.events.items.description`** (付録 B #18。**v1.2 で追加。監督裁定 S-d**): 接頭辞 `Deliberately left open (subordinate ruling 7(A)): ` を**全体として剥がし**、あわせて末尾の `this ruling closes` を **`this contract closes`** に改める (上記「`schemas.AuditResult...` の扱い」)。**マニフェストに `rewrite` として記録する。**

**残す 3 値は付録 B の `unstripped` と同じ** — `versioning.version_binding` (累積の規範叙述そのもの)、`versioning.compatibility` と `destructive_confirmation.phrase_construction.rules[3]` (スキャナの `previously` が通常語の一致であり provenance マーカーではない)。**剥離後の 26 値 (+ 追加 2 件) の規範文は 1 語も変えない** — 除去するのは接頭辞 / 挿入句だけである。**18 件の依頼者確定文言についても同じ扱いであり、確定された規範文は不変で、除去されるのは provenance 表記のみである。** **PIN 定数は剥離後の文字列に書き換える。**

**計画文書 §5 (2026-09-07 改版註) との関係 (v1.1 で追加。レビュー 1 m8)**: 計画文書の「**規範文を書き換えずに消せるマーカーは 0 件である**」(`docs/design/ROADMAP_POST_PHASE7_V1.md:162`) は、**値の byte を 1 文字も動かさずに消せるマーカーが 0 件**という意味であり、**(B) は byte を動かすことを前提に、意味の不変をマニフェスト逆適用の deep-equal で機械的に示す**方式である。**両者は矛盾しない。** **付録 B を §5 U-6 の提示物として読む側が「0 件のはずでは」と読まないよう、この 1 文を添える。**

#### 根拠 (file:line)

- companion の現行構造と register 7 本: `spec/CONTRACT_HISTORY.md` (29 anchor、前文の limitation 1〜3)、`conformance-tests/test_contract_history_register.py:186` / `:198` / `:214` / `:221` / `:228` / `:305` / `:352` (F-23)。
- 接頭辞剥離で確実に赤になるもの: heading 集合一致 (`:198`)、quote byte 一致 (`:305`)、`Since` 照合の `assert checked == 17` (`:352`)、`test_contract.py` の PIN 群 (in-substring 比較)。
- packaged copy の byte 一致テスト: `r2db-api/tests/test_http.py:286-289`、`MitateDB-api/tests/test_http.py:155-158` (F-23)。**3 複製を同時更新すれば緑のままである。**
- PIN の実数と集計軸の違い: `conformance-tests/test_contract.py` の `^PIN_` 15 件 (行 433〜591) と、フェーズ8 付録 A §A.2c の「test-pinned: 18」(F-22)。**再確定対象は 18 値である。**
- 「29 値すべてが現行規範文と同居する」: `spec/CONTRACT_HISTORY.md` 前文 limitation 3、フェーズ8 設計 §5 U-2 の前提となる実測。

#### 実装の形

1. **WP-1 内の 1 単位として行う** — R-10 (B) は契約 JSON を触るので、**契約 JSON を触る唯一の WP (WP-1) の中でしか行えない。**
2. **マニフェストの形** (素案。作業指示書で確定):

```json
{
  "audit.query_cursor": {
    "stripped_prefix": "Since 1.4.0 (subordinate ruling 9, item 1, conditional): ",
    "unstripped": false
  },
  "schemas.AuditResult.properties.events.items.description": {
    "stripped_prefix": "Deliberately left open (subordinate ruling 7(A)): ",
    "rewrite": {"from": "this ruling closes", "to": "this contract closes"},
    "unstripped": false
  },
  "versioning.version_binding": {
    "stripped_prefix": null,
    "unstripped": true,
    "reason": "version labels are woven through the normative sentences themselves; no prefix or clause can be removed without rewriting them"
  }
}
```

3. **逆適用検証**: `stripped_prefix` を各 json_path の値の先頭へ戻し、**`rewrite` を持つ entry は `to` を `from` に戻し**、`unstripped: true` の値はそのまま、で得た JSON と**剥離前の JSON を deep-equal 比較する。** 差分 0 を確認したうえで、走査した key 数を記録する。

#### 検査の形

- **改版後の register 7 本がそのまま効く** — 対象が「JSON」から「JSON + 逆適用」に変わるだけである。**変異**: マニフェストから 1 エントリを消す → heading 集合一致が赤。逆適用後の quote を 1 文字変える → byte 一致が赤。`unstripped: true` を勝手に足す → `Since` 照合の件数が合わず赤。
- **3 複製の byte 一致**は既存テストが担保する。
- **剥離漏れを赤にするのは新規 assert (剥離後スキャナ 0 ヒット) と heading 集合一致であり、PIN ではない (v1.2 で訂正。レビュー 2 M1、監督裁定 S-e)。** **v1.1 は「PIN の書き換えが漏れれば該当 PIN が赤になる — これが剥離と PIN 書き換えを同一コミットに強制する機構である」と書いていたが、実測ではこの強制は 15 定数中 1 件 (`PIN_1_5_0_SENTENCE_1`) でしか成立しない** — 残り 14 定数は剥離後も一致し続けるので、剥離だけを行って PIN を一切触らなくても緑のままである。**したがって強制力を持つのは、マニフェスト逆適用後の quote byte 一致 (`:305`)、heading 集合一致 (`:198`)、および新規の「剥離後スキャナ 0 ヒット」assert である。**

#### 開示事項

- **本項は契約の意味を 1 文字も変えない。** それを示すのは**マニフェスト逆適用後の deep-equal** であり、**目視ではない。**
- **本項が触る値は 26 値だが、依頼者確定文言のうち PIN 定数として実際に書き換えが要るのは `PIN_1_5_0_SENTENCE_1` の 2 定数分割 1 件だけである (v1.2 で訂正。S-e)。** **他の 17 値の確定文は、剥離後も PIN の照合が通り続ける** — 照合先が `unstripped` の値か、接頭辞を含まない本文だからである。**再確定 (§5 U-6) の対象が 18 値であることと、PIN の書き換えが 1 件であることは別の集計軸である。** **常設規律 4 の再確定は §5 U-6 で完了した** (依頼者裁定 2026-09-07 の委任に基づく監督確定、v1.1)。**確定内容は §5 U-6 に逐語で記録されており、WP-1 はそこから複製する** — **設計文書と作業指示書と契約 JSON へは確定文ファイル経由で複製し、書き写しの言い換えを行わない。**
- **剥離後も契約 JSON の長さは「剥がした接頭辞・挿入句の分」しか減らない。** フェーズ8 の (A) が「1 文字も減らない」だったのに対し (B) は実際に減るが、**`versioning.version_binding` の 10,269 字 (契約全体の 13.32%) は `unstripped` として残る** — **付録 B の実測でそう分類された** (値が累積叙述であり、後続文が同一値内の先行文を参照するため、機械的分離ではなく再著述になる)。**期待値を過大に書かない** — **削減量は 26 値分の接頭辞・挿入句の合計であって、契約の 13.32% を占める最大の値は動かない。**
- **削減量は設計時点で見積れる (v1.2 で追加。レビュー 2 m10)。** **確定した剥離リスト (付録 B の 26 値 + 監督裁定の追加剥離 2 件) を適用したレビュー 2 の実測は 1,787 バイト / 契約 JSON 全体 77,119 バイト = 2.3% である。** **これに S-d の扱い (#18 で剥がす範囲が挿入句 26 字から接頭辞 50 字へ広がるので **+24 バイト**、`ruling` → `contract` の語改訂で **-2 バイト**) を織り込むと、見積りは約 **1,809 バイト / 2.3%** である。**確定値は WP-1 が実測して §11.1 と L9-5 に記録する。**

---

### D-10 MitateDB の schema revision 永続化 (**撤回 (前提事実の誤り、レビュー 1 B1)**)

#### 決定

**本項は v1.1 で撤回した。** **v1.0 の D-10 は「MitateDB SQLite backend はファイルに永続する backend であり、そこだけ schema revision が Python のプロセス内カウンタであるため、永続する DB と揮発する revision の食い違いを持つ」という前提の上に立っていたが、その前提は事実に反する。**

- **MitateDB の SQLite backend は `sqlite3.connect(":memory:", check_same_thread=False)` (`MitateDB-api/src/mitatedb_api/backend_sqlite.py:87`) の 1 形しか持たず、リポジトリ全体で `sqlite3.connect` はこの 1 箇所だけである。** **接続断で DB 全体が消えるプロセス内 backend であり、r2db の in-memory `ApplicationCell` と同列である** (F-16 を v1.1 で訂正した)。
- **したがって D-10 の理由 1・2 はいずれも成立しない。** **「永続するのに revision だけ揮発する」食い違いはそもそも存在せず**、この backend では**「再起動をまたいだ真実性」という概念自体が無い** — 状態全体がプロセスとともに消えるからである。
- **宣言型レジストリ `_declared_types` も同じくプロセス内である** (`backend_sqlite.py:107` / `:218` / `:253`)。**この事実は D-2 (4) にも効き、v1.1 は MitateDB 側の宣言正本を「Postgres backend = `_mdb_field_types` に列追加」「in-memory (SQLite) backend = `_declared_types` と同じプロセス内構造」に書き分けた。**

**撤回の帰結。**

1. **§5 U-4 = (A) は変更しない。** plan の材料は per-application の schema revision であり、**Postgres backend は両 peer とも DDL と同一 tx で永続、in-memory backend は両 peer ともプロセス内である** — 4 plug で同じ規則が成り立ち、D-10 は U-4 = (A) の前提ではない。
2. **§6.5 の新規ファイル一覧から `MitateDB-api/migrations/00xx_schema_revision_upgrade.sql` を削除した。** **書こうとしても対象となる application ファイルが存在しない。**
3. **WP-3b の先頭要件を削除した** (§8)。**WP-3b は R-4 dry_run のみである。**
4. **台帳 L9-6 は「撤回 (前提事実の誤り、レビュー 1 B1)」の記録として残す** — 削除しない (起票と撤回の経緯を残す規律)。

---

## 4. 却下した代替案

**本節の A-1〜A-10 は監督確定である。再提案には新しい論拠が要る。**

| ID | 案 | 却下の理由 |
|---|---|---|
| **A-1** | **`enum` / `nullable` を PostgreSQL の物理制約 (CHECK / NOT NULL) でも強制する** | **二重検証 (L6-9) を増やし、違反が backend 層の汎用 `VALIDATION_FAILED` として details 無しで漏れる経路を作る** (F-9: 両 peer の backend 層は details を持たない)。**D-3 が「4 key を持つのは宣言を読む層だけ」と定めた層の整理と正面から衝突する。** choke point 1 点 + registry 正本で十分であり、**直接 DB 書き込みは契約の外である** (SI-12 が別途担保する)。 |
| **A-2** | **`alter_field` で `field_type` の再宣言も 1.7.0 に含める** | **既存値の変換規則 (string→integer 等) が peer 同型に定義できない** — r2db は物理カラム型そのものが正本 (`ALTER TABLE ... TYPE ... USING ...` の変換式が要る)、MitateDB は宣言 registry と実体が別 (F-3) であり、「変換」の意味が一致しない。**実需も未実証である** (R-13 の記録が 0 件)。**定義しないことを契約に書く** (D-2 の契約文案が `alter_field` に `field_type` を載せた要求を `VALIDATION_FAILED` と定める) — 黙って無視する形にはしない。 |
| **A-3** | **`dry_run` を「実行せず静的検証のみ」で実装する** | **`affected` 件数・precondition・unique 制約の判定が実行と一致しない。** 計画文書が課した条件「**dry_run の判定 = 実呼びの判定**」に真正面から反する。**「試したときは通ったのに本番で落ちる」形はエージェントにとって最悪の宣言**であり、P-3 (宣言は真である) の違反そのものである。 |
| **A-4** | **`plan` を server 保持 (`plan_id` + expires_at) にする** | **P-1 違反。** 計画文書 §6 が既に却下している (「無状態トークンで同じ保証が得られる」)。**保持すれば失効・容量・掃除という 3 つの新しい面が増え、両 peer の同型性を「持ち方」と「失効」の 2 回壊す。** |
| **A-5** | **idempotency key のスコープを credential 単位にする** | **同一 Application の別 credential からの再送を「別要求」として二重実行する。** atomic unit の scope は契約が `transactions.cross_entity` で「within a single Application's storage scope」と定めており、**再送安全性の scope をそれより狭くすると、credential rotate をまたいだ再送が安全でなくなる** — rotate は運用上ふつうに起きる。 |
| **A-6** | **`version_binding` の散文を配列に置換する** | **string → array は `versioning.compatibility` が言う "removal or semantic change" であり major 版事項である。** かつ **PIN された依頼者確定文言の破棄**になる (F-22: `PIN_1_6_0_VERSION_BINDING_PARAGRAPH` ほか)。**散文は残し、`obligations` 配列を追加して両者を register で縛る** (D-8)。 |
| **A-7** | **R-8 の生成器が既存の自然文 (`auth`、`applies_to` の擬似式) を正規表現で解釈する** | **脆く、解釈結果が advisory になる (P-3)。** `auth` は `"runtime or developer"` / `"application or control"` のような自然文であり (F-20)、語が 1 つ増えた瞬間に静かに間違った射影を出す。**フェーズ8 の教訓 L8-14 (代理指標の禁止: 分岐の条件はその分岐が依存する性質そのものを読む) と同じ罠である。** **構造化フィールドを契約に足す**方が長期に正しい。 |
| **A-8** | **`request_id` を optional のまま「載せても載せなくてもよい」にする** | **空振り条件になる。** どちらでも conformant なら C-25 は何も固定しない。**1.7.0 を宣言する peer には無条件義務とし、schema 上の optional は「過去版の応答が新 schema に適合し続けるため」だけの理由にする** (D-7 (2))。 |
| **A-9** | **`dry_run` で `assigned_addresses` を返す** | **採番は確定しないので偽の宣言になる** (F-15: rollback しても sequence は戻らないが、返した address が実 apply で割り当てられる保証は無い)。**返さないことを契約に明記し、なぜ返さないかも書く** — 書かないと「実装の手抜き」と読まれる。 |
| **A-10** | **idempotency 記録を platform DB (cross-app) に置く** | **data tx と別コネクションになり、「記録あり = commit 済み」が原子的に成り立たない** (F-14 の監査 hook がまさにその形であり、rollback しても残る)。補償 (先に記録し失敗時に消す) が要り、その補償自体が失敗し得る。**ただし cross-app の単一真実という別の利点があるので、§5 U-3 の (B) として両論に残す。** |

**あわせて、計画文書 §6 が既に却下している案は再提案しない** — data plane の sandbox セッション、サーバ保持 `plan_id`、出力形式の切替、webhook / WebSocket による監査ストリーミング、surfaces の相互ダイヤル、`suggested_fix_action` / `valid_sample`、catalog の advisory な説明文、操作カタログの resource cost 概算、`rows_scanned` budget class、任意 SQL / 自然言語クエリ / 管理画面 / ORM 互換。**本フェーズの決定はいずれもこの表に触れていない。**

---

## 5. 未確定だった選択肢と、その確定

**本節の 8 項目は v1.0 では両論のまま置き、監督の見立てを明示していた。裁定は逐語で本節に記録し、再審議しない** (計画文書 §9 の 4)。**逐語は確定文ファイル経由で複製する** (常設規律 4。フェーズ8 で言い換えによる違反が 1 件検出されている、第 15 次 §4-3 の 4)。

**依頼者裁定 (2026-09-07、逐語)**:

> 判断しなければならないものが出たらあなたの推奨で進めてください。後で報告してください。

**適用範囲 (監督の解釈、2026-09-07)**: **本節の未確定選択肢 U-1〜U-8 (R-10 (B) の before/after 再確定と契約文案の確定を含む) は監督の推奨で確定し、確定内容と根拠を本設計文書に記録して、フェーズ完了報告で依頼者に報告する。**

**確定は 1 回目のレビュー反映時に確定した (v1.1)。2 回目のレビューは確定後の設計を独立に検証する。** **各項の「依頼者裁定 (逐語)」欄には、上記の依頼者逐語を引いたうえで、監督の確定内容 (どの枝を採ったか) と根拠を記入してある。** **各項の表と「監督の見立て」は v1.0 のまま残す** — 確定に至った両論そのものが判断の根拠だからである。

### U-1 `enum` の上限 (要素数・要素長) の class

| | **(α) `schema_objects` に enum 要素を数える** | **(β) 新 class `enum_members` を足す** |
|---|---|---|
| **内容** | enum の要素を `schema_objects` の数え上げに含める。**前提として MitateDB の `schema_objects` の数え方を r2db と同じ「entity + field + index」に揃える** (= F-5 の非対称を同時に解消する)。要素長は `request_bytes` に委ねる | `limits.classes` に **`enum_members`** (field あたりの要素数上限、`example_profile` は 64 程度) を足す。要素長は `request_bytes` に委ねる |
| **新 limit class** | **0 個** (既存 class の意味を広げる) | **1 個** |
| **P-5 との関係** | class は増えないが、**`schema_objects` が「schema の物理オブジェクト数」から「schema 宣言の総量」へ意味が広がる**。既存配備の宣言値 (r2db 1000 / MitateDB 128) の意味も変わる | **安全上必要な bound を、それが何を数えているか分かる名前で足す。** 既存 class の意味を動かさない |
| **P-6 との関係** | **F-5 の非対称を本フェーズで解消する** — MitateDB の数え方を変えるのは application plane の挙動変更であり、`max_fields` (`cell.py:617` / `:708`) との関係整理も要る。**範囲が広がる** | **F-5 の非対称は残る** (台帳に載せ、別途扱う) |
| **宣言の読みやすさ** | エージェントは `schema_objects` の 1 値から enum 要素数の余地を逆算できない | **`enum_members` を読めば「1 field に何個まで書けるか」が直接分かる** |
| **影響範囲** | 契約 (`limits.schema_objects` の意味記述)、MitateDB の数え方の変更、C-05 の `schema_objects` driver の再確認 | 契約 (`limits.classes` に 1 語 + `example_profile` に 1 値)、両 peer の宣言と検査、C-05 V1 (e) の固定 9 class 集合の再確認 |

**監督の見立て: (β)。** **P-5 (安全上必要な bound だけ) と宣言の読みやすさ (G-1) に合う。** **F-5 の非対称はどちらでも台帳 (L9-1) に載せ、(α) なら本フェーズで解消し、(β) なら別途扱う。**

**依頼者裁定 (逐語)**:

> 判断しなければならないものが出たらあなたの推奨で進めてください。後で報告してください。

**確定 (監督、2026-09-07。上記の委任に基づく)**:

**確定: (β) 新 class `enum_members` を `limits.classes` に足す (field あたりの enum 要素数の上限、`example_profile` は 64)。要素長は `request_bytes` に委ねる。F-5 の非対称 (schema_objects の数え方) は本フェーズで変えず L9-1 に残す。**

**根拠: P-5 (安全上必要な bound を、それが何を数えているか分かる名前で足す)、G-1 (1 field に何個まで書けるかを 1 値で読める)、既存 class の意味を動かさない。**

**契約文案は §3 D-2 の「`limits.classes` への `enum_members` 追加と `limits.example_profile` への値追加」ブロック (U-8 #4) である。**

### U-2 `dry_run` の監査イベント

| | **(A) 監査行を一切書かない** | **(B) 破壊操作・schema 操作の dry_run は監査行を書く** |
|---|---|---|
| **内容** | dry_run が実行段階に達した場合、**監査行を一切書かない。** **実行前の拒否 (AUTH / FORBIDDEN / LIMIT) は現行どおり監査される** — それらは dry_run 固有の経路ではないからである | 破壊操作・schema 操作の dry_run は **`outcome: dry_run` の attributable な監査行**を書く (security-relevant とみなす) |
| **「外部可視の状態変化 0」** | **監査行にも適用される** — C-22 が「dry_run 前後で監査行が増えていない」を assert できる | **適用されない。** C-22 の「監査行不変」assert を**書けない**か、**書けても弱くなる** (「dry_run 行以外は増えていない」) |
| **SI-14 との関係** | 「誰が何を試したか」の証拠が残らない。**ただし dry_run は状態を変えないので、SI-14 の "minimum event classes" のどれにも該当しない** — destructive schema/data operation も privilege-sensitive operation も、実際には起きていない | **「破壊操作を試した」ことが証拠として残る。** 偵察行為の検知に効く |
| **費用** | 無し | 監査 sink への書き込みが dry_run のたびに発生する。**dry_run は「安全に試す」ための機能なので、試行回数は実呼びより多くなり得る** |

**監督の見立て: (A)。** **(B) は「dry_run の判定 = 実呼びの判定」を保ったまま採れる**ので排除はできないが、**C-22 の最も強い assert (「監査行を含めて何も増えない」) を弱める。** **(B) を採るなら、C-22 は「dry_run 行がちょうど 1 行増え、それ以外は増えない」という形に置き換える** — 弱くはなるが空振りにはしない。

**依頼者裁定 (逐語)**:

> 判断しなければならないものが出たらあなたの推奨で進めてください。後で報告してください。

**確定 (監督、2026-09-07。上記の委任に基づく)**:

**確定: (A) dry_run が実行段階に達した場合、監査行を一切書かない。実行前の拒否 (AUTH / FORBIDDEN / LIMIT / SCOPE_MISMATCH 等) は現行どおり監査される。C-22 は「dry_run の前後で監査行が 1 行も増えていない」を assert する。**

**根拠: 「外部可視の状態変化 0」を監査行にも適用でき、C-22 の最も強い assert が書ける。dry_run は状態を変えないので SI-14 の最小イベント class のどれにも該当しない。**

### U-3 idempotency 記録の保持場所

**下表は v1.0 のまま残す。** **表中の「MitateDB SQLite は application ファイル内のテーブル」は v1.0 時点の誤った前提であり (レビュー 1 B1。この backend は `:memory:` のプロセス内 backend である。F-16)、下記の確定文はその訂正を反映した本文である。**

| | **(A) application DB の side table** | **(B) platform DB の共通テーブル** |
|---|---|---|
| **内容** | per-application upgrade で application DB に表を置き、**data tx と同一 tx で書く。** r2db の in-memory 参照 cell はプロセス内 dict、MitateDB SQLite は application ファイル内のテーブル | Q4 の `platform_declarations` と同居する **cross-app 1 表**に置く |
| **原子性** | **「記録あり = commit 済み」が同一 tx で成り立つ** | **別コネクションになるので成り立たない。** 「先に記録し失敗時に消す」補償が要り、**その補償自体が失敗し得る** (A-10) |
| **単一真実 (Q4)** | application ごとに分散する | **cross-app の単一真実になる。** 運用者が 1 箇所で件数と保持期間を見られる |
| **deprovision** | application を消せば記録も消える (正しい) | 記録が残る。**孤児行の掃除規約が要る** |
| **in-memory / SQLite peer** | プロセス内 dict / application ファイルで自然に閉じる | platform DB が要るので、**PostgreSQL を持たない plug (in-memory / SQLite) で成立しない** |

**監督の見立て: (A)。** **原子性が構造で成り立つことと、4 plug すべてで同じ形が取れることが決め手である。** (B) の利点 (cross-app の単一真実) は、**運用側から見たいなら `ops` サブコマンドで集約できる**ので、記録そのものを移す理由にはならない。

**依頼者裁定 (逐語)**:

> 判断しなければならないものが出たらあなたの推奨で進めてください。後で報告してください。

**確定 (監督、2026-09-07。上記の委任に基づく)**:

**確定: (A) application DB の side table。per-application upgrade で置き、data tx と同一 tx で書く。r2db の in-memory 参照 cell と MitateDB の in-memory (SQLite `:memory:`) backend はプロセス内構造、両 peer の Postgres backend は application DB の side table。**

**根拠: 「記録あり = commit 済み」が構造で成り立つ (SI-11)、4 plug すべてで同じ形が取れる (P-6)、deprovision で記録が消える。**

**(v1.2 で、監督裁定の訂正 (2026-09-07) に従い確定文を訂正後の本文に差し替えた。v1.1 が付けていた事実注記は不要になったので削除した。)**

### U-4 `plan` トークンの「schema 状態の決定的値」

**下表は v1.0 のまま残す。** **表中の「D-10 の永続化が前提」「MitateDB SQLite は D-10 で永続化する」は v1.0 時点の前提であり、D-10 は v1.1 で撤回された** (レビュー 1 B1。下記の確定と事実注記を参照)。

| | **(A) `schema_revision` 番号** | **(B) 対象 entity の `EntityDescriptor` の正規化 digest** |
|---|---|---|
| **内容** | `SchemaOperationResult.revision` と同じ値を plan の材料にする。**D-10 の永続化が前提である** | 対象 entity の `EntityDescriptor` を正規化して digest を取る。**両 peer で同一の正規化規則を定める** |
| **既存機構との整合** | **明快である** — 契約が既に持つ `revision` と 1 対 1 である。エージェントが「revision が変わったから plan が無効になった」と理解できる | `revision` とは独立の値になる。**エージェントには不透明のまま** (契約上 plan は opaque なので問題にはならない) |
| **P-1 / P-6 との関係** | revision の意味と持ち方が peer で違う (F-16: r2db in-memory はプロセス内、MitateDB SQLite は D-10 で永続化する) | **「catalog が報告する内容」から作るので、持ち方に依らず両 peer で同一構成規則にできる。** P-6 に素直である |
| **検出できる変化** | **revision を進める操作すべて** (index 作成なども含む) | **`EntityDescriptor` に現れる変化のみ** — descriptor に現れない schema 変更 (例えば index) を検出しない |
| **再起動・移行** | 永続化すれば耐える (D-10) | **依らない。** 復元した DB でも同じ digest になる |
| **実装費用** | 小 (既存値を使う) | 中 (正規化規則を定義し、両 peer で同型に実装する) |

**監督の見立て: (B) が P-1 / P-6 に素直である。** ただし **(A) は既存 `revision` との整合が明快**であり、**「plan が無効になった理由」をエージェントが自分で診断できる** (catalog の revision を見ればよい) という G-1 上の利点がある。**(B) を採る場合、「descriptor に現れない schema 変更は plan を無効にしない」ことを契約と C-22 行に開示する必要がある。**

**計画文書 (正本) の文言との関係 (v1.1 で追加。レビュー 1 M8)**: 計画文書 `docs/design/ROADMAP_POST_PHASE7_V1.md` §5 のフェーズ9 節 R-4 は「plan トークン = **request digest + 対象 entity の schema revision の決定的値**」と書いており、**本書 §1.1 はこれを逐語で転記している。** **確定は (A) であり「schema revision」を採る点では正本どおりだが、その revision は「対象 entity の」ではなく「対象 Application の」である (v1.2 で改訂。レビュー 2 M5、監督裁定 S-i)。** **両 peer とも entity 単位の revision を持たず、`SchemaOperationResult.revision` は per-application の単調カウンタである** (F-16。r2db `r2db-api/src/r2db_api/postgres.py:1900-1935`、MitateDB `MitateDB-api/src/mitatedb_api/backend_postgres.py:646-661`)。**帰結として、対象 entity に無関係な entity への schema 操作も plan を失効させる** — **これは fail-closed 側の誤差であり安全だが、正本の文言とは意味が違う。** **したがって計画文書 §5 フェーズ9 節の R-4 行を R-14 の流儀 (起票時の原文を消さず、改版註を日付・根拠つきで足す) で改版する。改版文案は §10.1 に置き、改版そのものは WP-4 で行う。** (**v1.1 は「正本の指定どおりであるから改版は不要である」と書いていたが、それは誤りであった。**) (なお、**(A) を「D-10 が前提だから採りにくい」とする v1.0 の見立ては、レビュー 1 B1 で D-10 の前提が崩れたことにより解消した** — 4 plug のいずれでも per-application revision は一貫して定義でき、in-memory backend では状態全体がプロセス内なので revision だけが揮発するという食い違いが無い。)

**依頼者裁定 (逐語)**:

> 判断しなければならないものが出たらあなたの推奨で進めてください。後で報告してください。

**確定 (監督、2026-09-07。上記の委任に基づく)**:

**確定: (A) schema revision 番号。plan の材料は「要求 body の正規化 digest」と「対象 Application の schema revision (SchemaOperationResult.revision と同じ値、per-application の単調カウンタ)」である (両 peer の Postgres backend は DDL と同一 tx で永続する revision、in-memory backend はプロセス内の revision)。契約文案 #12 は「a deterministic value for the schema state」を「the Application's own schema revision -- the same value SchemaOperationResult.revision reports」と具体化する。cross_entity_mutate も同じ per-application revision を使う (entity ごとの revision は両 peer とも持たない)。**

**根拠: 契約が既に持つ revision と 1 対 1 で、エージェントが「revision が変わったから plan が無効になった」と自分で診断できる (G-1)。revision を進める操作すべて (index を含む) を検出する。両 peer とも per-application の単調カウンタを schema 操作ごとに進める形で揃っているので P-6 を満たす。(B) の正規化規則を両 peer に同型で実装する費用と「descriptor に現れない変更を検出しない」開示を避ける (シンプル)。**

**(v1.2 で、監督裁定の訂正 (2026-09-07) に従い確定文を訂正後の本文に差し替えた。v1.1 が付けていた事実注記は不要になったので削除した。)** **なお「要求 body の正規化 digest」の対象・除外 key・正規化規則は §3 D-4 (7) が設計で固定した (v1.2、監督裁定 S-a)** — 確定の枝そのものは変わらない。

### U-5 R-8 の「返し得る code」

| | **(A) `endpoints.*.error_codes` を契約に足す** | **(B) 初版のカタログに含めない** |
|---|---|---|
| **内容** | endpoint ごとに返し得る code を宣言し、**conformance が「suite 中にその endpoint で観測した code ⊆ 宣言」を assert する。** 逆方向 (宣言した code がすべて観測される) は検査不能であることを開示する | 宣言しない。**エージェントは `errors.codes` の全域と各節の記述から判断する** (現行どおり) |
| **P-3 との関係** | **片方向だけ検査可能である。** 「宣言に無い code が出たら赤」は真に検査できる。**「宣言にあるが出ない code」は空振りとして残る** | **advisory な宣言を足さない** (P-3 の最も素直な適用) |
| **G-1 との関係** | **エージェントが「この endpoint は何で落ち得るか」を 1 箇所で読める** — 1 周を閉じるうえで実利がある | エージェントは全域 17 code から自分で絞る |
| **計画文書との関係** | 計画文書 §5 の R-8 が「返し得る code」を**列挙項目として名指している** | **名指された項目を初版から外すので、依頼者の再確定が要る** |

**監督の見立て: (B)。** **「宣言にあるが観測されない code」は空振りであり、片方向しか検査できない宣言を契約に置くのは P-3 の趣旨から遠い。** **ただし計画文書 §5 が明示的に列挙した項目なので、外すには依頼者の再確定が要る。**

**依頼者裁定 (逐語)**:

> 判断しなければならないものが出たらあなたの推奨で進めてください。後で報告してください。

**確定 (監督、2026-09-07。上記の委任に基づく)**:

**確定: (B) `endpoints.*.error_codes` は初版のカタログに含めない。計画文書 §5 R-8 の「返し得る code」は、片方向 (観測 ⊆ 宣言) しか検査できず「宣言にあるが観測されない code」が advisory として残るため、P-3 を優先して外す。計画文書 §8 の R-8 行に R-14 の規約で根拠と日付を残す。**

**根拠: P-3 (advisory な宣言を catalog に載せない)。エージェントは `errors.codes` の全域 17 code と各節の記述から判断する (現行どおり)。**

**計画文書 §8 R-8 行への改版文案は §10 に置く** (計画文書そのものの更新は WP-4 で行う)。

### U-6 R-10 (B) の再確定

**付録 B の before/after 一覧 (29 値、うち 18 値が依頼者確定文言) を提示し、値ごとに「剥がす / 残す」の確定を得る。** **これが D-9 の着手条件である** (常設規律 4)。**確定前に契約 JSON の当該値に手を付けない。**

**依頼者裁定 (逐語)**:

> 判断しなければならないものが出たらあなたの推奨で進めてください。後で報告してください。

**確定 (監督、2026-09-07。上記の委任に基づく)**:

**確定: 付録 B の 29 値のうち、機械的に分離できた 26 値はマニフェスト草案どおり剥がす。ただし次の 2 件は草案に追加して剥がす: (a) `security.schemes.application_credential.description` と `security.schemes.control_credential.description` の値中の "Since 1.6.0 (subordinate ruling 11, item 1; unconditional -- versioning.version_binding): " は挿入句全体 (「Since 1.6.0」を含む) を剥がし、"Since 1.6.0: " を残さない。(b) `control_endpoints.revoke_credential.semantics` の末尾文 "Resolved in contract 1.2.0 (previously a pending contract decision, the destructive-confirmation semantics question)." は文全体を挿入句として剥がす。残す 3 値 = `versioning.version_binding` (累積の規範叙述そのもの)、`versioning.compatibility` と `destructive_confirmation.phrase_construction.rules[3]` (scanner の "previously" が通常語の一致であり provenance マーカーではない)。剥離後の 26 値の規範文は 1 語も変えない (接頭辞 / 挿入句の除去のみ)。18 件の依頼者確定文言についても同じ扱い — 確定された規範文は不変であり、除去されるのは provenance 表記のみである。PIN 定数は剥離後の文字列に書き換える。**

**根拠: R-10 (B) の趣旨 (経緯文は companion へ、契約本体は現行の意味だけ。P-7)。付録 B の逆適用 byte 一致 29/29 が機械的可逆性を示している。**

**付録 B への反映**: **追加剥離 2 件は付録 B の #9 / #25 / #26 の行に「監督裁定で追加剥離」として注記し、剥離後の文を更新した (v1.1)。** **v1.2 では監督裁定 S-d により #18 の行にも同形の注記を足した。** **これらは逐語転記のプロトタイプ出力に対する追記であり、いずれも注記としてその旨を明示してある。**

**確定文への 2 点の補足 (v1.2。監督裁定 追補 2)** — **確定そのものは変えない**:

1. **S-d (レビュー 2 B4)**: **`schemas.AuditResult.properties.events.items.description` は、接頭辞を剥がしたうえで末尾の `this ruling closes` を `this contract closes` に改める。** 剥がした挿入句への後方参照が宙に浮くためであり、**この値は PIN 定数を持たないので依頼者確定文言の破棄には当たらない** (D-9)。**`unstripped` は 3 件のままである。**
2. **S-e (レビュー 2 M1)**: **確定文の「確定された規範文は不変であり、除去されるのは provenance 表記のみである」は、`PIN_1_5_0_SENTENCE_1` については別の形で成り立つ** — **この確定文は provenance 接頭辞を確定文の内側に含んでおり**、`versioning.version_binding` (unstripped) では接頭辞付きのまま、`audit.query_operation_vocabulary` / `audit.query_target_kind_vocabulary` (剥離対象) では接頭辞なしになる。**したがって同じ確定文の 2 変種が必要であり、PIN 定数を 2 つに分ける** (D-9 手順 5)。**規範文そのものは 2 変種で同一であり、違いは接頭辞の有無だけである。**

### U-7 版フリップの「同時」

| | **(A) peer ごとに独立した version-flip コミット** | **(B) 両 peer のフリップを 1 コミットにまとめる** |
|---|---|---|
| **内容** | 1.6.0 の前例 (`36e6d35` / `1b87b38`) どおり peer ごとに 1 コミットを作り、**完了ゲート内で連続して main にマージする** | 最後の 1 コミットで両 peer を同時にフリップする |
| **`version_binding` の規律** | **満たす** — 各フリップが「それが主張する実挙動変更」と同一コミットに落ちる | **満たす**が、1 コミットが 2 peer 分の挙動変更を持つ |
| **並行 worktree** | **WP-2 と WP-3 を最後まで並行で回せる** | **最後の 1 コミットだけ直列にする必要がある** (両 peer の src を 1 コミットで触るため) |
| **切り分け** | どちらの peer のフリップが問題を起こしたかが commit 単位で分かる | 分からない |

**監督の見立て: (A)。** 前例があり、並行運用を最後まで保て、切り分けができる。

**依頼者裁定 (逐語)**:

> 判断しなければならないものが出たらあなたの推奨で進めてください。後で報告してください。

**確定 (監督、2026-09-07。上記の委任に基づく)**:

**確定: (A) peer ごとに独立した version-flip コミット (1.6.0 の前例 36e6d35 / 1b87b38 の型) を作り、完了ゲート内で連続して main にマージする。フリップ間に他のコミットを挟まない。**

**根拠: version_binding の規律 (フリップは主張する実挙動変更と同一コミット) を満たし、WP-2 / WP-3 の並行を最後まで保て、commit 単位で切り分けられる。**

### U-8 契約文案の確定 (json_path ごと)

**本フェーズが契約に置く新規 / 改訂の文言はすべて依頼者確定文言の再確定対象である** (常設規律 4)。**U-6 (R-10 (B) の 18 値) と同じ確定で 1 回にまとめた** (C9)。**下表は §3 の各 D が示した契約文案の一覧であり、v1.0 で両論だった項 (#4 / #11 / #12 / #13 / #24 / #26) は確定した枝を示す。** **#28 は v1.1 で追加した項である** (レビュー 1 B4)。

| # | json_path | 出所 | 状態 |
|---|---|---|---|
| 1 | `schemas.SchemaOperationRequest.properties.field_constraints.description` | D-2 | 新規。単一案 |
| 2 | `structured_operations.alter_field` (または `SchemaOperationRequest.operation` の説明に併記) | D-2 | 新規。単一案。**置き場所 (独立節か既存節への併記か) は設計の裁量として作業指示書で確定する** |
| 3 | `definitions.EntityDescriptor.properties.field_constraints.description` | D-2 | 新規。単一案 |
| 4 | `limits.enum_members` + `limits.classes` への 1 語追加 + `limits.example_profile` への `enum_members: 64` | D-2 / U-1 | **確定 (U-1 = (β))。** 文案は §3 D-2 の当該ブロック |
| 5 | `errors.details_vocabulary.VALIDATION_FAILED` | D-3 | 新規。単一案 |
| 6 | `errors.details_vocabulary.IDENTIFIER_INVALID` | D-3 | 新規。単一案 |
| 7 | `errors.details_vocabulary.CAPABILITY_UNSUPPORTED` | D-3 | 新規。単一案 |
| 8 | `errors.details_vocabulary.violated_declaration_vocabulary` | D-3 | 新規。単一案 (10 語) |
| 9 | `errors.details_vocabulary.layer_rule` | D-3 | 新規。単一案 |
| 10 | `structured_operations.dry_run.decision` (3 request schema から参照) | D-4 | 新規。単一案 |
| 11 | `structured_operations.dry_run.external_effects` | D-4 | **確定 (U-2 = (A))。掲載案どおり「no audit event」。** |
| 12 | `structured_operations.dry_run.plan` | D-4 | **確定 (U-4 = (A))。** 「a deterministic value for the schema state」を `the Application's own schema revision -- the same value SchemaOperationResult.revision reports` へ具体化した文案を §3 D-4 に掲載 |
| 13 | `structured_operations.idempotency.record` | D-5 | **確定 (U-3 = (A))。掲載案どおり** (「same transaction as the effects it records」が成立する)。**replay 応答の `SchemaOperationResult.revision` が元実行時点の値である 1 文を v1.1 で追加した** (レビュー 1 m9) |
| 14 | `structured_operations.idempotency.correlation` | D-5 | 新規。単一案 |
| 15 | `structured_operations.idempotency.key_secrecy` | D-5 | 新規。単一案 |
| 16 | `schemas.SchemaOperationRequest.properties.idempotency_key` | D-5 | 新規。単一案 (既存 2 schema と同一形) |
| 17 | `limits.request_budget` | D-6 | 新規。単一案 |
| 18 | `schemas.QueryResult.properties.request_id.description` (および `MutationResult` / `SchemaOperationResult` の同名) | D-7 | 新規。単一案 |
| 19 | `endpoints.*.roles` / `.requires_capability` / `.atomicity` (および `control_endpoints.*` の同名) | D-8 | 新規。単一案 |
| 20 | `destructive_confirmation.applies_to_structured` | D-8 | 新規。単一案 |
| 21 | `versioning.obligations` + `versioning.obligations_note` | D-8 | 新規。単一案 |
| 22 | **`versioning.version_binding` の 1.7.0 段落** | D-8 | 新規。単一案。**無条件 2 件 / 条件付き 5 件** |
| 23 | **`versioning.version_binding` の retroactive-denial 4 文への `1.7.0-only` 追記** | D-8 | 改訂。単一案。**PIN 定数 4 件が同時に動く** |
| 24 | **`versioning.version_binding` の 1.6.0 段落最終文 (1.5.0 に対する retroactive denial)** | D-8 | **確定 (a)。** 既存文を `1.6.0-only or 1.7.0-only` へ広げる。**`PIN_1_6_0_VERSION_BINDING_PARAGRAPH` を「剥離後の文字列 + この改訂」で書き換える** — #23 で retroactive-denial 4 文の PIN も同時に動くので、同じ主題を 1 箇所に保つ方を採る。確定文は §3 D-8 に掲載 |
| 25 | `schemas.CapabilityDocument.properties.operation_catalog_url` | D-8 | 新規。単一案。**optional、義務にしない** |
| 26 | `endpoints.*.error_codes` | D-8 / U-5 | **置かない (確定、U-5 = (B))。** 計画文書 §8 R-8 行への R-14 改版文案は §10 に置く |
| 27 | **R-10 (B) で剥離する 29 値** | D-9 | **確定 (U-6)。付録 B の一覧に監督裁定の追加剥離 2 件 (#9 / #25 / #26) を反映済み。18 値が依頼者確定文言。** |
| **28** | **`definitions.EntityDescriptor.properties.field_types.description` / `schemas.SchemaOperationRequest.properties.field_types.description` の当該 1 文 (`PIN_1_6_0_ITEM_3_FIELD_TYPES`)** | D-2 / レビュー 1 B4 | **v1.1 で追加。改訂。確定。** 現行文の「the catalog … declares neither nullability …」は 1.7.0 で偽になる。**確定文は §3 D-2 の当該ブロックに逐語で掲載** (2 json_path とも同一文)。**剥離後の PIN 定数はこの文を含む形に書き換える** (§6.3) |
| **29** | **`schemas.MutationResult.properties.plan` / `schemas.SchemaOperationResult.properties.plan`** (string、**optional**。**`required` 不変**) | D-4 (3) / 裁定 T-1 | **v1.3 で追加。確定。** dry_run 応答が `plan` を運ぶため。**3 result schema は `additionalProperties: false`** なので、足さなければ dry_run 応答が C-11 で赤になる |

**依頼者裁定 (逐語)**:

> 判断しなければならないものが出たらあなたの推奨で進めてください。後で報告してください。

**確定 (監督、2026-09-07。上記の委任に基づく)**:

**確定: #1〜#3、#5〜#10、#14〜#22、#25 は掲載案 (単一案) を採る。#4 は U-1 = (β) の形。#11 は U-2 = (A) の掲載案どおり。#12 は U-4 = (A) の具体化。#13 は U-3 = (A) の掲載案どおり。#24 は (a) — 1.6.0 段落最終文を「1.6.0-only or 1.7.0-only」へ広げる (PIN_1_6_0_VERSION_BINDING_PARAGRAPH を剥離後の文字列 + この改訂で書き換える。#23 で retroactive-denial 4 文の PIN も同時に動くので、同じ主題を 1 箇所に保つ方を採る)。#26 は U-5 = (B) により置かない。#27 は U-6 のとおり。**

**起草者の指摘 2〜5 (「契約文書のみの変更」の第 3 種、条件付き義務の capability 配列 (AND)、violated_declaration の閉じた 10 語彙、field の `/` 区切りパス) はいずれも採る。**

**根拠: 各 D の根拠のとおり。**

**#28 (v1.1 で追加。レビュー 1 B4、監督裁定 R-d)**: **`PIN_1_6_0_ITEM_3_FIELD_TYPES` の文を改訂する。** 現行文「it declares neither nullability, nor default values, nor whether a field is required, because no schema operation defined here establishes any of them; a later version that gives schema operations such a notion gives it to the catalog in that same version」は **1.7.0 で偽になる**ので書き換える。**確定文**:

> The catalog reports only facts this contract's own schema operations can establish: nullability and enum membership through field_constraints, and neither default values nor a notion of required distinct from nullable: false, because no schema operation defined here establishes either; a later version that gives schema operations such a notion gives it to the catalog in that same version.

**(2 json_path とも同一文。剥離後の PIN 定数はこの文を含む形に書き換える。)**

**v1.2 での契約文案の改訂 (監督裁定 追補 2。枝の確定は変えず、確定した枝の文言を精緻化したものである)**:

| # | json_path | v1.2 での改訂 | 裁定 |
|---|---|---|---|
| 10 | `structured_operations.dry_run.decision` | dry_run の schema 応答の `revision` が「判定時点の現在 revision」であることを 1 文追加 | **S-j** |
| 12 | `structured_operations.dry_run.plan` | digest の対象 (契約レベルの要求オブジェクト)・除外 key (`plan` / `dry_run`)・正規化規則を英文で明記。plan が Application 全体の schema 状態に結び付くことの開示 1 文。plan の照合位置 (`evaluation_order` の precondition 段) 1 文 | **S-a / S-i / S-l** |
| 13 | `structured_operations.idempotency.record` | digest の除外 key (`plan` / `dry_run` / `idempotency_key`) と D-4 との同一規則を 1 文。照会位置 (target-existence / confirmation / precondition の前) を 2 文。満杯拒否が実行前であることを 1 語 | **S-a / S-b / m13** |
| 17 | `limits.request_budget` | `budget` の妥当性検査が要求の検証段 (target-existence / confirmation / precondition の前) であることを 1 文追加 | **S-l** |
| 19 | `endpoints.*.atomicity` | 固定語彙を `atomic` / `none` / **`atomic_unless_best_effort`** に改名 (v1.1 の `per_item_when_declared` から) | **S-n** |
| 27 | R-10 (B) の剥離 | `schemas.AuditResult.properties.events.items.description` を「接頭辞全体の除去 + `this ruling closes` → `this contract closes`」とし、マニフェストに `rewrite` を記録 | **S-d** |

**#29 (v1.3 で追加。作業指示書起草者の疑義 1、監督裁定 T-1)**: **`schemas.MutationResult.properties.plan` と `schemas.SchemaOperationResult.properties.plan` (string, optional) を契約に足す** (dry_run 応答が plan を運ぶため。3 result schema は `additionalProperties:false`)。**設計 D-4「実装の形 1」と本表に追加した。** **`required` 配列は変えない** — #18 (`request_id`) と同じ形である。

**複製の規律**: **確定文は確定文ファイルに逐語で置き、契約 JSON・設計文書・作業指示書・port docstring へはそのファイルから複製する** (常設規律 4)。

---

## 6. conformance への影響

### 6.1 port v1.13

`conformance-tests/adapter.py` を **v1.13** へ上げる。**追加のみ、削除は無い。** `docs/design/CONFORMANCE_ADAPTER_V1.md` に **§23 (v1.13)** を新設する (§22 = v1.12 と同じ構成: 追加メソッドの意味論 / 既存機構との関係 / 互換性影響)。**文書情報の版数行 (現行 1.12) も更新する。**

| # | 追加 | 何のため | 既定値と互換性 |
|---|---|---|---|
| 1 | mutation 系 / schema 系 primitive の **`dry_run: bool = False`** キーワード (**request 単位。`BatchOperation` / `ScopedBatchOperation` には置かない**。v1.1 で改訂、レビュー 1 M9 / 監督裁定 R-l) | C-22 | **既定 `False` = pre-v1.13 とバイト等価の挙動。** |
| 2 | mutation / schema primitive の **`plan: str or None = None`** キーワード (**request 単位のみ**) と、結果側の **`plan`** (**#29。dry_run 応答が運ぶ**) | C-22 | 既定 `None` = 送らない。 |
| 3 | 4 endpoint 系 primitive の **`budget: Mapping[str, int] or None = None`** キーワード (**request 単位のみ**) | C-24 | 既定 `None` = 送らない。 |
| 4 | schema primitive の **`idempotency_key: str or None = None`** | C-23 (iv) | 既定 `None` = 送らない。**`BatchOperation.idempotency_key` は v1.11 から在る。** |
| 5 | schema primitive の **`enum` / `nullable` / `field_constraints`** キーワード | C-20 | 既定 `None` = 送らない。**`field_types` (port v1.10) と同じ位置・同じ扱い。** |
| 6 | 結果側の **`request_id`** の露出 (成功応答から取り出す) | C-25 | **`ConformanceDenial` は既に `request_id` を持たないので、成功側だけの追加である。** |
| 7 | schema 結果側の **`descriptor`** の露出 | C-22 (dry_run の schema 応答) | 既定 `None`。 |
| 8 | **`alter_field`** primitive | C-20 | **新設。** 現在の port に `alter_field` は無い (両 peer 未実装のため)。 |

**表記について (v1.3)**: **上表の `str or None` / `Mapping[str, int] or None` は、実装するシグネチャとしては `str | None` / `Mapping[str, int] | None` である。** **Markdown の表では型注記の裸の `|` が列区切りとして解釈されて表が崩れるため、表の中でだけ表記を改めた** — **意味は変えていない。**

**port docstring に書く限界 (逐語規律の対象)**: (i) **`dry_run` の「外部可視の状態変化 0」は adapter が観測できる範囲 (行・catalog・revision・監査 query) に限られる** — 採番の消費は観測できるが assert しない (D-4 開示事項)、(ii) **`plan` は opaque であり、adapter は等値比較だけを行う** (構造を解釈しない)、(iii) **`dry_run` / `budget` / `plan` は 1 要求に 1 個であり、operation ごとに異なる値を持てない** (v1.1 で追加、レビュー 1 M9)、(iv) **`budget` は「配備値を下回る方向にのみ効く」ものであり、adapter が bound を上げる用途に使ってはならない。** (v) **`BatchOperation.idempotency_key` は per-item のフィールドだが、契約の `idempotency_key` は request 単位である (v1.2 で追加。レビュー 2 M9、監督裁定 S-m)** — **1 attempt 内の operations が運ぶ `idempotency_key` は「全 operation が同じ値を持つ」か「全 operation が持たない」かのどちらかでなければならず、adapter はその値を request 単位の key として送る。** **混在は port の誤用として adapter 自身が `AssertionError` (理由文付き) で落とす。peer には送らない。** **混在した key を adapter が黙って 1 つに畳み込まない。**

**`dry_run` / `plan` / `budget` を per-item に置かない理由 (v1.1。レビュー 1 M9、監督裁定 R-l)**: **契約はこの 3 つを `MutationRequest` / `ScopedMutationRequest` / `SchemaOperationRequest` の request-level フィールドとして定めており** (D-4 (1)、D-6 (1))、`Mutation` / `ScopedMutation` (per-item) には置かない。**per-item に置くと「1 batch 内で `dry_run` が混在したときの意味」が契約に無いまま adapter が折り畳み規則を決めることになり、C-22 の「判定 = 実呼び」が adapter 側の勝手な意味付けに依存する。** **`idempotency_key` が `BatchOperation` に per-item で在る既存の非対称はフィールドの位置としてはそのまま残す** — port v1.11 の既存形であり、裁定 S-4 がその位置を定めているからである (`conformance-tests/adapter.py:757`)。**ただし畳み込み規則を放置しない (v1.2。レビュー 2 M9、監督裁定 S-m)** — **C-23 (v) は複数 item の batch を使うので、「2 item のうち 1 つだけに key」「2 つに別々の key」の意味が契約にも port にも無いまま 4 adapter が別々に畳み込むと、C-23 と C-07 (ii) が plug ごとに別の命題を検査することになる** (しかも L7-8 を閉じる当の枝である)。**上記 (v) の規則を port の docstring に逐語で固定し、混在は adapter が拒否する。**

**フェーズ8 の教訓 L8-15 を適用する**: **port に optional フィールドを足したら、「配線されている」ではなく「adapter がそのフィールドを捨てる変異が赤になる」ところまで実測する。** **本フェーズは #1〜#5 の 5 フィールドすべてについてこれを行い、結果を §11.3 に記録する。**

### 6.2 新条件 C-20〜C-25

**6 条件すべてが (i) four adapters で executable、(ii) 宣言分岐型、(iii) 非 vacuity 要件つき、である。**

**非 vacuity 要件は宣言ベースの per-plug 形に統一する (v1.2 で改訂。レビュー 2 B3、監督裁定 S-c)。** **各 plug は自分の宣言 (`capabilities()` の当該 capability の status、または `contract_version`) から期待枝を導き、`observed_branch` と突合する** — **C-07 (ii) (`conformance-tests/test_c07_atomicity_and_retry.py:106-158`、突合は `:154-158`) と同じ型である。** **suite 横断の集約 guard は置かない。**

**理由 (実測の教訓)**: `conformance-tests/test_c07_atomicity_and_retry.py:36-39` が「per-plug non-vacuity … **a session-crossing aggregate guard does not work under `-n 5 --dist loadgroup`** (each plug is its own xdist group)」と明記している。**完了ゲート (§9 の 1) はまさに `-n 5 --dist loadgroup` である。** 観測を worker 間で集約する状態が存在しないので、「suite 全体で肯定側を 1 plug が通ったこと」を assert しようとすると、**常に空集合を見て赤になるか、worker ごとに別の集約を見て偽陽性の緑になるか**のどちらかにしかならない。**v1.1 の §6.2 冒頭はこの形を要求しており、§6.6 (R-h) の宣言ベースの記述と食い違っていた** — **v1.2 は §6.6 の側に統一した。**

**「両 peer がフリップした後は 4 plug すべてが肯定枝である」ことは、テストではなく完了ゲートで監督が確認する** — xfail の残数と各条件の `observed_branch` の集計行で見る (§9 の 14)。**L7-8 (肯定側が 4/4 plug で未到達だった) を二度と作らないための担保はここに置く。**

**既存条件 C-11 に逆方向の assert を足す (v1.3 で追加。作業指示書起草者の疑義 4、監督裁定 T-4)**: **「両 peer が `capability_status.defined` の全語 (1.7.0 で 14 語) を `capabilities` に宣言する」assert は、C-11 (`conformance-tests/test_c11_document_conformance.py`) に逆方向 (defined ⊆ declared) の assert として WP-1 で足す。版ゲートは置かない** (両 peer は現行 11 語をすべて宣言していることを WP-1 が実測し、新 3 語は provisional gate と同一コミットで `unavailable` を宣言するので緑のまま)。**これが「新 capability を正直に `unavailable` と宣言する」ことの検査になる** (D-1 (3))。**現行の `conformance-tests/test_c11_document_conformance.py:55-56` は「宣言した名前が `defined` に含まれる」という片方向しか見ていない** (§9 の 16)。

**status の 4 値に対して分岐を網羅にする (v1.2 で明記。レビュー 2 m6)**: 契約 `capability_status.status_enum` は `enabled` / `partial` / `unavailable` / **`planned`** の 4 値である。**分岐は「`unavailable` なら拒否枝、それ以外 (`enabled` / `partial` / `planned`) は肯定枝」で書く** — **C-07 (ii) (`test_c07:81` の `"unavailable" if status == "unavailable" else "retry_same_result"`) と同じ形である。** 本フェーズの新 capability を `planned` で宣言する計画は無いが、**分岐は 4 値に対して網羅である。**

#### C-20 制約宣言の一致

- **Condition**: 「A peer's published field constraints agree with observed behavior: a value outside a field's declared `enum`, and a null (or an omitted value) on a field declared `nullable: false`, are refused at the value-validation boundary; the catalog reports the constraints the schema operation declared, total over the entity's own fields, in the same version; and an `alter_field` whose declared constraints existing rows would violate is refused in full with `CONFLICT`, changing nothing.」
- **Invariants**: `SI-05, SI-15`
- **Evidence**: `declaration-agreement test (constraint round-trip, positive and negative sides), pre-flight rejection test`
- **Status (骨子)**: `executable (four adapters) -- conformance-tests/test_c20_constraint_declaration_agreement.py, @pytest.mark.condition("C-20"), port v1.13; declare-first on capabilities().constraint_declarations.` 以下に**宣言分岐**と**開示**を書く。
- **宣言分岐**:
  - **`unavailable` 枝**: `field_constraints` / `enum` / `nullable` を載せた schema 要求が **`CAPABILITY_UNSUPPORTED` で実行前に拒否**され、**catalog に `field_constraints` が現れず**、**entity が作られていない** (副作用 0) ことを assert する。`observed_branch = "unavailable"`。
  - **`enabled` / `partial` / `planned` 枝**: (1) `enum` を宣言した field に集合外の値を書くと `VALIDATION_FAILED` + `violated_declaration = enum` — **これを `insert` / `update` / `upsert` の 3 経路すべてで観測する (v1.2 で拡張。レビュー 2 M7、監督裁定 S-k)**、(2) 集合内の値は書ける (**正の対照**)、(3) `nullable: false` の field に null を書くと `VALIDATION_FAILED` + `violated_declaration = nullable` (+ `observed_type = null`) — **これも `insert` / `update` / `upsert` の 3 経路すべてで観測する (S-k)**。insert で省略すると同 code + `observed_type = absent`、**insert に解決する `upsert` の省略も同じ拒否になり、update に解決する `upsert` は拒否されない** (v1.1、レビュー 1 B3)、(4) catalog の `field_constraints` が宣言と一致し、**`fields` 全体に対して総計である**、(5) query の predicate に集合外の値を置いても**拒否されず 0 行が返る** (D-2 開示事項の負側)、(6) 既存行が違反する `alter_field` が `CONFLICT` + `violated_declaration ∈ {enum, nullable}` で拒否され、**catalog も行も 1 つも変わっておらず、revision も進んでいない** (v1.2 で revision 不変を追加。監督裁定 S-g)、(7) 違反しない `alter_field` は成功し **revision が進む**。`observed_branch = "enforced"`。
  - **突合**: `observed_branch` を `capabilities().constraint_declarations.status` から導いた期待値と assert する (C-07 (ii) `test_c07:154-158` と同形)。
- **非 vacuity**: **各 plug が 2 枝のどちらかを実際に観測し、それが自分の宣言から導いた期待枝と一致すること** (per-plug、宣言ベース。§6.2 冒頭、監督裁定 S-c)。**WP-1 の時点では 4 plug すべてが `unavailable` 枝を通り、WP-2a / WP-3a の後は順に `enforced` 枝へ移る** — **`conformance-tests/` を 1 行も編集せずに移る。** **「4 plug すべてが `enforced` 枝である」ことは完了ゲートで確認する** (§9 の 14)。
- **開示 (v1.2)**: **MitateDB の既存行走査が DDL と同一トランザクションにあるかは共通条件では観測できない** — C-20 (6) は「1 行も変わっていない」しか見ないので、走査と DDL の間に他 session の書き込みが入る競合は緑のまま通る。**WP-3a の peer-local テストがこれを担保する** (D-2 実装の形 4)。**この限界を C-20 行に開示する。** **あわせて「Overlaps C-17 (同じ declaration-agreement の姿勢、異なる宣言)」の 1 文を C-20 行に置く** (§6.4)。

#### C-21 検証エラー語彙

- **Condition**: 「Denials this contract requires structured diagnostics for carry them: every `VALIDATION_FAILED`, `IDENTIFIER_INVALID` and `CAPABILITY_UNSUPPORTED` a peer declaring contract 1.7.0 returns carries the details keys `errors.details_vocabulary` requires for that code, with `violated_declaration` drawn from the closed vocabulary, `field` naming a position in the request, and no row value, SQL, internal name, or corrective action anywhere in `details`.」
- **Invariants**: `SI-05, SI-10`
- **Evidence**: `error-probe test over each required code, plus the shared unsafe-content scan`
- **Status (骨子)**: `executable (four adapters) -- conformance-tests/test_c21_denial_details_vocabulary.py, @pytest.mark.condition("C-21"), port v1.13; unconditional 1.7.0 obligation, version-gated.`
- **宣言分岐 (版分岐)**: **本条件は capability ではなく `contract_version` で分岐する** (無条件義務であるため)。
  - **`contract_version < 1.7.0` 枝**: **`xfail(strict=True)`。** 挙動が宣言より先に入れば XPASS で赤になる (D-1 (7))。`observed_branch = "pre_1_7_0"`。
  - **`>= 1.7.0` 枝**: 3 code それぞれについて、その plug で**実際に発行される code だけ**を対象に、必須 key の存在・語彙適合・`field` のパス形式・`declared_type` / `observed_type` の値域を assert する。**加えて `assert_no_unsafe_diagnostic_content` を details 全体に掛ける。** `observed_branch = "vocabulary_enforced"`。
  - **突合**: `observed_branch` を `parse_semver(contract_version) >= (1,7,0)` から導いた期待値と assert する。**文字列比較を使わない** (C-19 の `_semver_tuple` 前例)。
- **非 vacuity**: **各 plug について「2 枝のどちらかを実際に観測し、それが自分の宣言 `contract_version` から導いた期待枝と一致すること」と「`>= 1.7.0` 枝では 3 code のうち少なくとも 1 つを実際に観測したこと」を assert する** (per-plug、宣言ベース。§6.2 冒頭、監督裁定 S-c。**v1.2 で suite 全体の集約 assert を削除した**)。**MitateDB は `IDENTIFIER_INVALID` を発行しない** (F-7) ので 3 code 全部は観測されない — **その非対称を C-21 行に開示する** (§3 D-3 開示事項、台帳 L9-2a)。

#### C-22 dry_run

- **Condition**: 「A dry-run request reaches the decision the identical real request reaches -- the same refusal code and details, or the same `affected` count with `committed: false` -- and leaves no externally visible state change; the `plan` it returns is deterministic, is honored on a real request against unchanged schema, and is refused with `PRECONDITION_FAILED` where the request body or the entity's schema has changed.」
- **Invariants**: `SI-11, SI-15, SI-08`
- **Evidence**: `decision-equivalence test, external-effect absence test, plan determinism and staleness test`
- **Status (骨子)**: `executable (four adapters) -- conformance-tests/test_c22_dry_run_and_plan.py, @pytest.mark.condition("C-22"), port v1.13; declare-first on capabilities().dry_run.`
- **宣言分岐**:
  - **`unavailable` 枝**: `dry_run: true` を載せた要求が **`CAPABILITY_UNSUPPORTED` で実行前に拒否**され、**行が 1 つも変わっていない**ことを assert する。`plan` を載せた要求も同様。`observed_branch = "unavailable"`。
  - **`enabled` / `partial` / `planned` 枝**: (1) **判定一致 (拒否側)** — 認可・破壊確認・precondition・limit のそれぞれについて、dry_run と実呼びが**同一 code**を返す、(2) **判定一致 (成功側)** — dry_run の `affected` が実呼びの `affected` と一致し、dry_run の応答が `committed: false` である、(3) **外部可視の状態変化 0** — dry_run の前後で行数・catalog・revision が不変であり、**`audit_query` が利用可能な plug では監査行も不変である** (§5 U-2 = (A) の確定)、(4) **`assigned_addresses` が dry_run 応答に無い**、(5) **schema の dry_run が `descriptor` を返し、それが実 apply 後の catalog と一致する。あわせて dry_run の `revision` が実 apply の前の catalog revision と一致し、apply 後の値とは異なる** (v1.2 で追加。レビュー 2 M6、監督裁定 S-j)、(6) **plan 決定性** — 同一要求の dry_run 2 回で `plan` が一致、(7) **plan 有効** — 同一要求 + schema 不変で apply が成功、(8) **plan 失効 (schema)** — 間に schema を変えると `PRECONDITION_FAILED` + `violated_declaration = plan`、(9) **plan 不一致 (body)** — 別 body に同 plan を付けると同じ拒否、**(10) digest 領域** — **`budget` だけを変えた apply が `PRECONDITION_FAILED` になる** (v1.2 で追加。レビュー 2 B1、監督裁定 S-a — digest が `operations` だけでないことの load-bearing な観測)、**(11) 順序** — **失効した `plan` を持つ未確認の `drop_entity` が `DESTRUCTIVE_CONFIRMATION_REQUIRED` を返す** (`PRECONDITION_FAILED` ではない。v1.2 で追加。レビュー 2 M8、監督裁定 S-l — 「順序を外から観測する」唯一の形である)。`observed_branch = "dry_run_enabled"`。
- **非 vacuity**: **各 plug が 2 枝のどちらかを実際に観測し、それが自分の宣言 `capabilities().dry_run.status` から導いた期待枝と一致すること** (per-plug、宣言ベース。§6.2 冒頭、監督裁定 S-c)。**WP-1 の時点では 4 plug すべてが `unavailable` 枝である。**
- **開示 (v1.2)**: **`plan` は Application 全体の schema 状態に結び付いており、対象 entity に無関係な entity への schema 操作でも失効する** (レビュー 2 M5)。**採番の消費は assert しない** (D-4 開示事項)。**`plan` は認可のスナップショットではない** (同)。

#### C-23 idempotency

- **Condition**: 「A peer declaring `idempotency` records each key with a digest of the request it accompanied and in the same transaction as that request's effects: a resend of the same key with the same body within the declared retention returns the original result -- including its `request_id` -- without re-executing; a resend with a different body is refused with `CONFLICT`; a failed attempt leaves no record; the key is scoped to the Application, not to the credential; and it applies to single-entity, cross-entity and schema requests alike.」
- **Invariants**: `SI-11, SI-08, SI-14`
- **Evidence**: `retry-equivalence test, digest-conflict test, failed-attempt absence test, cross-credential scope test`
- **Status (骨子)**: `executable (four adapters) -- conformance-tests/test_c23_idempotency_semantics.py, @pytest.mark.condition("C-23"), port v1.13; declare-first on capabilities().idempotency. Overlaps C-07 (ii): that row's own positive branch becomes load-bearing on all four plugs in the same version.`
- **宣言分岐**:
  - **`unavailable` 枝**: **C-07 (ii) の現行と同じ** — key 付き要求が `CAPABILITY_UNSUPPORTED` で実行前に拒否され、副作用 0。`observed_branch = "unavailable"`。
  - **`enabled` / `partial` / `planned` 枝**: (i) 同一 key + 同一 body の再送が `affected` / `assigned_addresses` / `request_id` すべて一致し、**行が 1 つしか増えていない**、(ii) 同一 key + 異なる body が `CONFLICT` + `violated_declaration = idempotency_key`、(iii) 保持期間内であること (retention の値は宣言から読む。**期限切れの検査は行わない** — 待ち時間を要するため。**この限界を C-23 行に開示する**)、(iv) `SchemaOperationRequest` と cross-entity でも同じ 3 性質が成り立つ (**cross-entity は `cross_entity_mutation` が `unavailable` でない plug のみ**)、(v) 失敗した試行 (無効な item を含む batch) の後、同じ key の再送が**新規実行になる**、(vi) 同一 Application の**別 credential**から同じ key を送ると**同一要求とみなされる**、**(vii) 破壊操作の replay** — **`delete` または `drop_entity` を有効な confirmation + key で実行し、同一 key・同一 body を再送すると、`DESTRUCTIVE_CONFIRMATION_REQUIRED` でも `NOT_FOUND` でもなく元の結果が返る** (v1.2 で追加。レビュー 2 B2、監督裁定 S-b。**変異「照会を confirmation / target-existence の後に置く」→ 赤**)。`observed_branch = "retry_same_result"`。
- **非 vacuity**: **各 plug が 2 枝のどちらかを実際に観測し、それが自分の宣言 `capabilities().idempotency.status` から導いた期待枝と一致すること** (per-plug、宣言ベース。§6.2 冒頭、監督裁定 S-c)。**C-07 (ii) の per-plug 非 vacuity は現行のまま効き続ける** (テストを 1 文字も変えずに枝が入れ替わる)。
- **開示 (v1.2)**: **(vii) は「再送が破壊確認をすり抜ける」形ではない** — 記録に一致するのは一度確認を通って commit した要求とバイト等価の要求だけである (D-5 開示事項)。**`BatchOperation.idempotency_key` は per-item だが、port は「全 item 同一 key か全 item 無し」しか受け付けない** (§6.1 (v))。

#### C-24 request budget

- **Condition**: 「A request-scoped `budget` narrows a declared bound downward only: a bound narrowed by `budget` refuses at the narrowed position with `LIMIT_EXCEEDED` naming that limit class, a `budget` above the deployment's own declared value is refused with `VALIDATION_FAILED` and `violated_declaration: budget`, and a `budget` naming a class that does not apply to that endpoint is refused the same way rather than ignored.」
- **Invariants**: `SI-08, SI-15`
- **Evidence**: `narrowed-bound boundary test (N/N+1 at the requested position), over-deployment rejection test, inapplicable-class rejection test`
- **Status (骨子)**: `executable (four adapters) -- conformance-tests/test_c24_request_budget.py, @pytest.mark.condition("C-24"), port v1.13; declare-first on capabilities().request_budget. Overlaps C-05: the same limit classes, a different proposition (C-05 fixes the deployment's own declared bound; C-24 fixes one request's narrowing of it).`
- **宣言分岐**:
  - **`unavailable` 枝**: `budget` を載せた要求が `CAPABILITY_UNSUPPORTED` で実行前に拒否され、副作用 0。`observed_branch = "unavailable"`。
  - **`enabled` / `partial` / `planned` 枝**: (1) **`batch_items`** — **`budget.batch_items = 2` を置き、2 件の operation を含む要求は成功、3 件の要求は `LIMIT_EXCEEDED(batch_items)`** (v1.2 でレシピを確定。レビュー 2 m9、監督裁定の Minor 一括採択 — **契約 `schemas.MutationRequest.properties.operations` の `maxItems: 100` にも配備 `batch_items` (既定 100) にも当たらない位置で N / N+1 を挟む**。in-process plug には shape 検査層が無いので、schema 側の件数制約が先に効く経路を避ける必要がある)、**両 peer で決定的に構成できる駆動 class である**、(2) **`result_items`** — **query 経路でのみ適用され、両 peer で同型に駆動できる形を WP-1 が実測して選ぶ。選べなければ非 vacuity の対象から外し、C-24 行に「駆動せず」として開示する** (v1.1 で改訂。レビュー 1 M3。MitateDB の `result_items` は返した行数ではなく要求された `limit` の値で拒否する、`MitateDB-api/src/mitatedb_api/cell.py:834-837`)、(3) 配備値を上回る budget → `VALIDATION_FAILED` + `violated_declaration = budget`、(4) 適用外 class (例: query に `batch_items`、**mutation に `result_items`**) → `VALIDATION_FAILED` + `field = budget/<class>`、(5) `budget` を省略した同じ要求は配備値まで通る (**正の対照**)、**(6) 順序** — **配備値超過の `budget` を持つ未確認の `delete` が `VALIDATION_FAILED` を返す** (`DESTRUCTIVE_CONFIRMATION_REQUIRED` ではない。v1.2 で追加。レビュー 2 M8、監督裁定 S-l)。`observed_branch = "budget_enforced"`。**`execution_ms` は駆動しない** (D-6 開示事項: 決定的な N+1 を構成できない。C-05 V2 が `execution_ms` を駆動しないのと同じ理由)。
- **非 vacuity**: **各 plug が 2 枝のどちらかを実際に観測し、それが自分の宣言 `capabilities().request_budget.status` から導いた期待枝と一致すること** (per-plug、宣言ベース。§6.2 冒頭、監督裁定 S-c)、かつ **L8-15 に従い「adapter が `budget` を捨てる変異が赤になる」ことを実測すること** — **(1) `batch_items` のレシピは、要求内の operation 件数を budget だけで N / N+1 に分ける**形にする (実行数側に位置決定の余地を残さない)。**(2) `result_items` を駆動対象に含めるか否かは WP-1 の実測で決め、含めない場合はその旨を C-24 行に開示する。**
- **開示 (v1.2)**: **C-05 との overlap は本行が持つ** — **C-05 行の Status セルは実測 2,960 字であり、上限 3,000 (`conformance-tests/test_conditions_register.py:56` の `MAX_CELL_LENGTH`) に対して約 150 字の overlap 文を足す余地が無い** (§6.4。レビュー 2 m1)。

#### C-25 成功応答の `request_id`

- **Condition**: 「Every successful result a peer declaring contract 1.7.0 returns carries `request_id`; distinct executions carry distinct values (a request answered from an idempotency record is not a new execution and carries the original execution's own value); and where `audit_query` is available, the value a mutation returned is the value that mutation's own audit events carry.」 (**`distinct requests` → `distinct executions` は v1.1 の訂正。レビュー 1 m4** — 再送も 1 つの request なので、v1.0 の文面は同節 (4) の「再送は元実行の値を返す」と正面から矛盾していた。)
- **Invariants**: `SI-14`
- **Evidence**: `presence and uniqueness test, audit correlation test where audit_query is available`
- **Status (骨子)**: `executable (four adapters) -- conformance-tests/test_c25_result_request_id.py, @pytest.mark.condition("C-25"), port v1.13; unconditional 1.7.0 obligation, version-gated.`
- **宣言分岐 (版分岐)**:
  - **`contract_version < 1.7.0` 枝**: **`xfail(strict=True)`**。`observed_branch = "pre_1_7_0"`。
  - **`>= 1.7.0` 枝**: (1) `QueryResult` / `MutationResult` / `SchemaOperationResult` の 3 つすべてに `request_id` がある、(2) 連続する 2 要求の値が異なる、(3) **`audit_query` が `unavailable` でない plug** では、mutation が返した値が当該監査行の `request_id` と一致する、(4) **idempotency が `enabled` の plug** では、再送応答が**元実行の値**を返す (C-23 (i) と重なるが、こちらは相関側の命題である)。`observed_branch = "request_id_present"`。
- **非 vacuity**: **各 plug が 2 枝のどちらかを実際に観測し、それが自分の宣言 `contract_version` から導いた期待枝と一致すること** (per-plug、宣言ベース。§6.2 冒頭、監督裁定 S-c。**v1.2 で suite 全体の集約 assert を削除した**)、かつ **(3) の監査照合まで届いた plug がどれかを C-25 行に明記すること** (「4 plug で緑」が「4 plug で監査照合した」を意味しないことを開示する)。

### 6.3 register テストと既存テストの改版

| 対象 | 変更 | WP |
|---|---|---|
| `conformance-tests/test_contract.py` | **1.7.0 の PIN を足す** (依頼者確定文言を**ファイル経由で**複製する。常設規律 4)。**retroactive-denial 4 定数を `1.7.0-only` 入りへ書き換える** (#23)。**`PIN_1_6_0_VERSION_BINDING_PARAGRAPH` を「剥離後の文字列 + 1.6.0 段落最終文の `1.6.0-only or 1.7.0-only` 改訂」の形へ書き換える** (#24 = (a))。**`PIN_1_6_0_ITEM_3_FIELD_TYPES` を §5 U-8 #28 の確定文へ書き換える** (2 json_path とも同一文。**R-10 (B) の剥離とは別事項の意味改訂である**。v1.1 で追加、レビュー 1 B4)。**剥離で動く PIN は `PIN_1_5_0_SENTENCE_1` の 1 件のみであり、これを `PIN_1_5_0_SENTENCE_1` (接頭辞付き、`version_binding` の照合用) と `PIN_1_5_0_SENTENCE_1_STRIPPED` (接頭辞なし、audit の 2 path の照合用) の 2 定数に分割する** (**v1.2 で実測に訂正。レビュー 2 M1、監督裁定 S-e。v1.1 の「剥離した 18 値の PIN を書き換える」は事実に反していた** — 動かない 14 定数には手を入れない)。**1.7.0 で動く PIN は計 7 件である** (この 1 件 + #23 の 4 件 + #24 + #28)。`versioning.obligations` ↔ 散文の**版集合一致**と、**件数語を持つ 3 版 (1.4.0 / 1.6.0 / 1.7.0) の無条件件数一致**の 2 本を新設する (R-i)。**既存の `test_contract.py:343-360` が 1.4.0 を拾い続けることを実測する** | WP-1 |
| `conformance-tests/test_contract_history_register.py` | **スキャナとすべての照合の対象を「契約 JSON にマニフェストを逆適用した値」へ改める** (D-9、R-j)。**companion の quote は従来どおり剥離前の原文であり、逆適用後の値と byte 一致する。** **`Since` 照合は逆適用後の値から読み、`assert checked == 17` は無改訂で通る (通ることを実測して §11.1 に記録する)。** **`unstripped: true` のエントリの扱いを明記する。** **「剥離後の契約 JSON にスキャナがヒットする値が 0 件である (`unstripped` の 3 値を除く)」の新規 assert を足す。** **1.7.0 が新設 / 改訂した全契約値に対しスキャナが 0 ヒットであることを WP-1 の完了条件にする** (R-k) | WP-1 |
| `spec/CONTRACT_HISTORY.md` (**v1.1 で追加。レビュー 1 m2 / m3**) | **前文の limitation 1 (「契約 JSON の長さは 1 文字も縮まない」) と limitation 3 (「29 値は現行規範文と同居しておりマーカーを外せない」) を (B) 実施後の事実へ書き換える。** **29 セクションの Value 見出し定型文 (「the history marker is embedded in it」) も同様に書き換える。** **旧文は履歴分離の規約に従うか、前文に改版註として残す** — 黙って消さない。**`versioning.version_binding` セクションの `Introduced in` を `contract 1.2.0 through 1.7.0 (cumulative)` へ更新する** (`_VERSION_RANGE_RE` が parse する形。1.7.0 段落には `Since 1.x.y` 形の語が無いので `checked` は増えず赤にはならないが、範囲表記が実態から遅れる) | WP-1 |
| `conformance-tests/test_operation_catalog_register.py` (**新設**) | 再生成 byte 一致 + `roles` ↔ `auth` + `requires_capability` の実在 + `atomicity` の固定 3 語 + `applies_to_structured` ↔ `applies_to` の 1:1 + `obligations` の 2 項目 (D-8) | WP-1 |
| `conformance-tests/test_c07_atomicity_and_retry.py` | **1 文字も変えない。** 宣言が変わることで `retry_same_result` 枝に入れ替わる (D-5) | — |
| `conformance-tests/test_c05_limit_declaration_agreement.py` (**v1.2 で追加。レビュー 2 M2、監督裁定 S-f**) | **変更しない。ただし `idempotency` のフリップにより V1 (e) の必須集合が 2 class 増える** — `_CAPABILITY_CONDITIONED` (`:84-88`) が `idempotency_entries` / `idempotency_retention_ms` を `idempotency` に条件付けているため。**両 class の `limits` 値と `limit_enforcement` エントリを capability document に足すことが WP-2c / WP-3c の完了条件である** | WP-2c / WP-3c |
| `conformance-tests/adapter.py` の `BatchOperation.idempotency_key` docstring (**v1.2 で追加。レビュー 2 M9、監督裁定 S-m**) | **per-item の key を「全 item 同一か全 item 無し」に限り、混在を adapter が `AssertionError` で落とす規則を docstring に逐語で足す** (§6.1 (v)) | WP-1 |
| `conformance-tests/test_c11_document_conformance.py` (**v1.3 で追加。監督裁定 T-4**) | **逆方向 (defined ⊆ declared) の assert を 1 本足す** — 「両 peer の capability document が `capability_status.defined` の全語 (1.7.0 で 14 語) を名指している」。**版ゲートは置かない。** **現行 `:55-56` は片方向 (declared ⊆ defined) しか見ていない** | WP-1 |
| `conformance-tests/test_c12_capability_agreement.py` | **`capability_status.defined` が 11 語 → 14 語になるので、駆動集合が自動的に広がる。** ハードコードした語彙一覧があれば契約から読む形へ直す (実装 WP が確認する) | WP-1 |
| `conformance-tests/test_c19_client_self_sufficiency.py` | **版分岐 `< (1,6,0)` はそのまま効く。** 1.7.0 宣言後も 1.6.0 の義務は満たされているので変更不要である。**「全 adapter が 1.6.0 以上を宣言する」形の assert があれば 1.7.0 でも真である** (実装 WP が確認する) | WP-2e / WP-3e |
| `conformance-tests/conftest.py` | `assert_no_unsafe_diagnostic_content` (`:517-546`) の**走査対象を C-21 の 3 code の details にも広げる。ただし対象は D-3 の 4 key の値に限定する** (v1.1。レビュー 1 m7) — `details.field` は client 自身が選んだ識別子を含むので、敵対的 identifier の probe を対象にするとテストが自分のエコーで赤になる | WP-1 |
| `conformance-tests/CONDITIONS.md` | **C-20〜C-25 の 6 行を追加。** **C-07 行の Status を更新** (§6.4)。**C-05 行には足さない — overlap は C-24 行の側から参照する** (v1.2 で確定。レビュー 2 m1) | WP-1 |
| `conformance-tests/COLLECTION_FLOOR` | **完了ゲートで実測値へ** (§9 の 4)。**WP の途中で上げない** | WP-4 |
| 両 peer の `tests/test_http.py` | packaged copy の byte 一致テストは**そのまま効く** (3 複製を同時更新するため) | — |

### 6.4 `CONDITIONS.md` の既存行の変更

- **C-07 行**: 「both currently-registered peers declare `idempotency: unavailable`, so the common suite's own executable evidence today is entirely on the `unavailable` branch … the `unavailable`-other branch … is currently unreached by any registered adapter and is disclosed here as genuinely untested」という開示を**書き換える** — 「both registered peers declare `idempotency: enabled` from contract 1.7.0; the positive branch (a same-key resend returns the same result) is load-bearing on all four plugs. Its own fuller semantics are C-23's territory」。**旧文は `CONDITIONS_HISTORY.md#c-07` へ逐語で移す** (現行/履歴分離の規約)。**L7-8 はここで閉じる。**
- **C-05 行**: **足さない (v1.2 で断定形に改訂。レビュー 2 m1)。** **C-05 の最長セルは実測 2,960 字であり (2026-09-07)、上限は `MAX_CELL_LENGTH = 3000` (`conformance-tests/test_conditions_register.py:56`) である。** overlap 文はおよそ 150 字なので**必ず超える。** **したがって overlap は C-24 行の側から C-05 を参照する形で置く** — 「Overlaps **C-05**: the same limit classes, a different proposition (C-05 fixes the deployment's own declared bound; this row fixes one request's downward narrowing of it)」を **C-24 行に置く。** **C-05 行の開示を削って辻褄を合わせることはしない。** (参考: C-09 は 2,948、C-19 は 2,942 であり、いずれも本フェーズでは触らない。**セル長の実測値は WP-1 が §11.3 に記録する。**)
- **C-17 / C-18 行**: **変更しない。** C-20 は「宣言した制約と実挙動の一致」であり、C-17 の「mutation class / addressability / uniqueness の宣言と実挙動の一致」とは**命題が異なる** (対象とする宣言が違う)。**ただし C-20 行に「Overlaps C-17 (同じ declaration-agreement の姿勢、異なる宣言)」を 1 文置く。**
- **C-11 (response schema conformance) 行**: **v1.3 で「変更しない」から改めた (監督裁定 T-4)。** **schema 照合そのものは変わらない** — 新しい optional フィールド (`request_id` / `descriptor` / **`plan`** (#29) / `field_constraints`) は `additionalProperties: false` の下で schema に足されるので、既存の照合がそのまま新フィールドを検査する。**変えるのは 1 点である**: **WP-1 が `conformance-tests/test_c11_document_conformance.py` に逆方向 (defined ⊆ declared) の assert を足す**ので、**C-11 行の Status にその 1 文を足す** (**版ゲートは置かない**。§6.2 / §6.3 / §9 の 16)。**セル長が `MAX_CELL_LENGTH = 3000` を下回ることを WP-1 が実測して §11.3 に記録する** (C-05 行で起きた問題を繰り返さないため)。

### 6.5 新規ファイル一覧 (ファイル名は素案。作業指示書で確定する)

| ファイル | 何を固定するか | 条件マーカー | WP |
|---|---|---|---|
| `conformance-tests/test_c20_constraint_declaration_agreement.py` | C-20 | `@pytest.mark.condition("C-20")` | WP-1 |
| `conformance-tests/test_c21_denial_details_vocabulary.py` | C-21 | `("C-21")` | WP-1 |
| `conformance-tests/test_c22_dry_run_and_plan.py` | C-22 | `("C-22")` | WP-1 |
| `conformance-tests/test_c23_idempotency_semantics.py` | C-23 | `("C-23")` | WP-1 |
| `conformance-tests/test_c24_request_budget.py` | C-24 | `("C-24")` | WP-1 |
| `conformance-tests/test_c25_result_request_id.py` | C-25 | `("C-25")` | WP-1 |
| `conformance-tests/test_operation_catalog_register.py` | R-8 の再生成一致と 6 項目 (D-8) | **付けない** (リポジトリ衛生。フェーズ8 §6.6 の 3 と同じ扱い) | WP-1 |
| `tools/contract_catalog.py` | (テストではない) 契約 → カタログの射影。**標準ライブラリのみ** | — | WP-1 |
| `spec/OPERATION_CATALOG.json` | (データ) 派生 artifact | — | WP-1 |
| `spec/CONTRACT_HISTORY_MANIFEST.json` | (データ) R-10 (B) の剥離マニフェスト | — | WP-1 |
| `r2db-api/migrations/00xx_field_constraints_upgrade.sql` | r2db の side table の per-application upgrade | — | WP-2a |
| `MitateDB-api/migrations/00xx_field_constraints_upgrade.sql` | MitateDB **Postgres backend** の registry 列追加の per-application upgrade (**SQLite backend はプロセス内なので upgrade script を持たない**、D-2 (4)) | — | WP-3a |
| (idempotency 記録の表) | §5 U-3 = (A) の確定により、per-application upgrade が両 peer の Postgres backend に 1 本ずつ | — | WP-2c / WP-3c |

### 6.6 xfail 件数の遷移

**v1.2 で表を改めた (レビュー 2 B3 / m8、監督裁定 S-c)。** **suite 横断の非 vacuity guard 4 本は置かないことになったので、xfail は版ゲートの 8 本だけである。**

| | 現在 (main `523753c`) | WP-1 後 | 先に済んだ peer のフリップ後 | 完了ゲート |
|---|---|---|---|---|
| C-21 / C-25 の版ゲート `xfail(strict=True)` (**per-plug**) | 0 | **8** (2 条件 × 4 plug) | **4** (未フリップ peer の 2 plug × 2 条件) | **0** (両 peer が 1.7.0 を宣言する) |
| C-20 / C-22 / C-23 / C-24 (**capability 宣言分岐。xfail を持たない**) | 0 | 0 | 0 | 0 |
| その他 | 0 | 0 | 0 | 0 |
| **合計** | **0** | **8** | **4** | **0** |

**完了ゲートの `xfailed` は 0 である** (§9 の 1)。**WP-1 のマージ時点では 8 本が xfail であり、これは「宣言より先に挙動を入れることを機構が禁じている」状態そのものである** (D-1 (7))。**`strict=True` を落として回避しない** — フェーズ8 の教訓 (第 15 次 §5 の最終項)。

**遷移はファイル編集なしに起こる (v1.1 の R-h をそのまま維持する)。** **版ゲート 8 本の条件は「その plug の宣言 `contract_version` < 1.7.0」であり、実行時に plug の宣言を読む。** **したがって件数は `conformance-tests/` を 1 行も編集せずに 8 → 4 → 0 と動く** — **WP-1 完了時点は 8 本 (C-21 / C-25 × 4 plug)**、**先に済んだ peer のフリップ後は 4 本 (未フリップ peer の 2 plug × 2 条件)**、**両 peer が済めば 0** になる。**中間の 4 を含むこの 3 段の遷移は監督裁定 T-3 の確定である (v1.3 で明記)** — **8 → 0 と書かない** (片 peer だけがフリップした状態は必ず通るので、そこでの期待値を書いていないと「4 本残っている」を異常と読み違える)。

**C-20 / C-22 / C-23 / C-24 は xfail を持たない (v1.2)。** これらは capability の宣言で分岐するので、**WP-1 の時点では 4 plug すべてが `unavailable` 枝を通って緑であり、実装 WP が capability を宣言した瞬間に肯定枝へ移る** — **どちらの枝も「観測されたこと」が per-plug で assert される**ので、xfail で押さえるべき「宣言より先の挙動」は存在しない。**「両 peer がフリップした後は 4 plug すべてが肯定枝である」ことは、完了ゲートで監督が各条件の `observed_branch` の集計行で確認する** (§9 の 14)。**v1.1 が置いていた suite 横断の集約 guard は、`-n 5 --dist loadgroup` の下では成立しない** (`conformance-tests/test_c07_atomicity_and_retry.py:36-39` の実測) **ので撤回した。** **guard の条件を「suite 自身の観測結果」から導く形 (自己参照) も採らない。**

### 6.7 `COLLECTION_FLOOR` の運用

- **値は前回 main の root `--collect-only -q` の件数である。** 本フェーズ着手時点の実測は**フェーズ8 完了時の 2340** である。
- **更新は監督が完了ゲートで行う。WP の途中で上げない** (他 WP のマージが赤くなる)。
- **本フェーズは 6 条件 × 4 plug + register 群を足すので、件数は相当に増える。** 完了ゲートの実測値へ締める (§9 の 4)。
- **残余リスクはフェーズ8 §6.4 の開示のまま** — 下限が守るのは「大きく減ったこと」であって「1 本も減っていないこと」ではない。

---

## 7. Security Invariants との関係

**新しい共通 Security Invariant は足さない** (制約 C2)。**Security Invariants は capability の許可リストではなく、守るべき安全成果の集合である** (CLAUDE.md「Security Invariants are not a feature gate」)。**本フェーズは新しい安全成果を導入せず、既存の安全成果を、新しい capability の上でも成り立たせ、証明可能にする。** 以下は **invariant ごと**に「既存で担保されるか」「新たに検証可能にすべき性質があるか」を書いたものである。

| invariant | 本フェーズの要素 | 既存で担保されるか / 新たに検証可能にする性質 |
|---|---|---|
| **SI-08 (Bounded Resource Consumption)** | **R-6 budget**、**R-2 enum の上限** (U-1)、**R-5 `idempotency_entries` / `idempotency_retention_ms`**、**R-4 dry_run が rate / concurrency を消費すること** | **既存で担保される。** SI-08 は bound すべき class を列挙し (`security/SECURITY_INVARIANTS_V1.md:230-240`)、**実装の自由度を明記する** (`:242-243`)。**budget は bound を下回る方向にのみ効くので、SI-08 の Statement (「認証されているというだけで無制限にアクセスできてはならない」) を弱めない** — 弱め得るのは「上回る方向」だけであり、それを A-6 相当の判断 (D-6) で構造的に禁じている。**新たに検証可能にする性質は「1 要求が自ら課した bound も決定的に効く」ことであり、C-24 がこれを固定する。** **`idempotency` は往復をまたぐ記録だが、契約が既に 2 class で bound を定義済みであり、無制限の保持にはならない** (D-5)。**dry_run が bound を消費することは、「dry_run で bound を回避できる」という新しい穴を作らないための決定である** (D-4 (6))。 |
| **SI-10 (Error and Information Non-Disclosure)** | **R-3 の details 語彙**、**R-2 の `CONFLICT` が行値も件数も載せないこと**、**idempotency key を監査行にも応答にも載せないこと** | **既存で担保される。** SI-10 は「Must still provide: Errors useful enough for legitimate clients and **AI agents** to correct requests. **Security does not justify opaque failure when structured safe diagnostics can be provided.**」(`security/SECURITY_INVARIANTS_V1.md:296-297`) と明記しており、**R-3 はこの後段の要求を初めて機械検査可能にする**ものである。**新たに検証可能にする性質は 2 つある**: (i) **details の中身が事実のみであること** — 現行の共通 suite は `DESTRUCTIVE_CONFIRMATION_REQUIRED` の details しか走査していない (F-11)。C-21 が 3 code へ広げる。(ii) **`field` が要求内の位置であって storage 内の位置でないこと** — 内部構造の開示を構造的に防ぐ。**`idempotency_key` の secrecy 文 (D-5) は SI-10 の「Must protect: credential material」を client 側の作法へ延長したものであり、新しい保護対象を作らない。** |
| **SI-11 (Atomic Integrity)** | **R-5 の記録が data tx と同一 tx であること**、**R-4 dry_run が rollback であること**、**R-2 の `alter_field` が全件拒否であること** | **既存で担保される。** SI-11 は「Operations declared atomic by the public contract MUST either complete according to contract or leave no partial externally visible state.」であり、**本フェーズは atomic unit の定義を変えない** (1 要求 = 1 原子単位のまま)。**新たに検証可能にする性質は「記録あり = commit 済み」が原子的に成り立つこと**であり、C-23 (v) (失敗した試行が記録を残さない) がこれを固定する。**§5 U-3 = (A) の確定により、この性質は補償に依らず構造で成り立つ** — 記録は data tx と同一 tx に書かれる。**`alter_field` の「1 行でも違反すれば全件拒否」は、schema 操作を原子単位として扱う既存の姿勢そのものである。** |
| **SI-14 (Security-Relevant Auditability)** | **R-7 の `request_id` 相関**、**R-4 dry_run の監査規則** (§5 U-2)、**idempotency key を監査に載せないこと** | **既存で担保される。** SI-14 の Verification は「Representative events yield correlated evidence; secrets are absent from logs.」であり、**R-7 は "correlated" 側を client から検証可能にする** — 現在は成功応答に相関子が無いので、client は自分の要求を監査行に突き合わせられない。**新たに検証可能にする性質は「client が受け取った識別子で監査行に到達できること」であり、C-25 (3) がこれを固定する** (`audit_query` が利用可能な plug で)。**dry_run の監査規則は §5 U-2 = (A) で確定した** — 「状態を変えない操作は SI-14 の minimum event classes のどれにも該当しない」という判断である。**却下した (B) (破壊操作の試行を security-relevant とみなす) を含め、**どちらも SI-14 の "Does not require: Logging every successful read at unlimited granularity. Audit detail should be proportional to security value and operational cost." の範囲内である。** |
| **SI-15 (Fail-Closed Authorization)** | **provisional gate**、**dry_run の認可判定**、**新 capability の `unavailable` 宣言** | **既存で担保される。** SI-15 は「When the service cannot establish the required identity, scope, role, policy, or security-critical state for an operation, it MUST NOT execute that operation.」である。**provisional gate (D-1 (3)) はまさにこの形である** — 契約 schema が新フィールドを通すようになっても、実装がその意味を確立できない間は実行しない。**新たに検証可能にする性質は「dry_run が認可を迂回しない」ことであり、C-22 の判定一致 (拒否側) がこれを固定する** — 「試すだけなら通る」形は SI-15 の最も分かりやすい違反であり、それが起きていないことを機械で示す。 |
| **SI-05 (Validated Structured Operations)** | **R-2 の choke point 強制**、**R-3 の `violated_declaration`** | **既存で担保される。** SI-05 の下で「宣言された制約が値検証境界で強制される」ことは新しい成果ではなく、**既存の型検証と同じ層の拡張である。** **新たに検証可能にする性質は「宣言と強制が一致すること」であり C-20 が固定する。** |
| **SI-01 / SI-02 / SI-12** | **idempotency key の Application スコープ** | **既存で担保される。** key 空間は Application 内であり、**Application が権限境界である** (SI-01)。**cross-Application の key 共有は生じない。** **物理制約を置かない判断 (A-1) は SI-12 (No Data-Service Bypass) が別途担保する範囲であり、本フェーズはその境界を動かさない。** |

**新しい invariant を足さない根拠を 1 点明記する**: **本フェーズが導入する 3 つの新 capability (`constraint_declarations` / `dry_run` / `request_budget`) は、いずれも「既存の安全成果を、より多くの場面で成り立たせる」ものである** — 制約宣言は SI-05 の検証境界を宣言駆動にし、dry_run は SI-15 の認可判定を実行前に見せ、budget は SI-08 の bound を client 側から狭める。**どれも新しい安全成果 (既存 15 invariant のどれにも属さない性質) を要求しない。** **CLAUDE.md が禁じる「新機能ごとに invariant を足す」形にも、「既存 invariant に合致しないから拒否する」形にもしていない。**

---

## 8. WP 分割の素案 (作業指示書で確定する)

| WP | 内容 | 触るファイル (実ファイル名) | 並行 |
|---|---|---|---|
| **WP-0** | **文書** — 本設計 v1.0 → **設計レビュー 1 回目 → v1.1 (全件反映 + §5 U-1〜U-8 の確定) → 設計レビュー 2 回目 → v1.2 (全件反映。監督裁定 S-a〜S-n) → 作業指示書の起草 → 起草者の疑義 4 件に対する監督裁定 T-1〜T-4 → v1.3** → 作業指示書の整合 (**正本は本設計 v1.3**) | `docs/design/PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md`、`docs/work-orders/WORK_ORDER_PHASE9_CONTRACT_170_V1.md` | **最初。単独** |
| **WP-1** | **契約 1.7.0** (**契約 JSON を触る唯一の WP**) — 契約 3 複製、CCR 従属判断 12、`CONTRACT_HISTORY` + MANIFEST、PIN 書き換え + 1.7.0 PIN、`versioning.obligations`、R-8 構造化フィールド、`tools/contract_catalog.py` + `spec/OPERATION_CATALOG.json` + register、port v1.13、C-20〜C-25、`CONDITIONS.md`、**両 peer の provisional gate と新 capability の `unavailable` 宣言** | `spec/data-service-api.v1.json`、`spec/CCR_DISPOSITION.md`、`spec/CONTRACT_HISTORY.md`、`spec/CONTRACT_HISTORY_MANIFEST.json` (新設)、`spec/OPERATION_CATALOG.json` (新設)、`spec/README.md`、`tools/contract_catalog.py` (新設)、`conformance-tests/adapter.py`、`conformance-tests/conftest.py`、`conformance-tests/CONDITIONS.md`、`conformance-tests/CONDITIONS_HISTORY.md`、`conformance-tests/test_contract.py`、`conformance-tests/test_contract_history_register.py`、`conformance-tests/test_operation_catalog_register.py` (新設)、`conformance-tests/test_c2{0,1,2,3,4,5}_*.py` (新設 6 本)、`conformance-tests/test_c11_document_conformance.py` (**逆方向 assert 1 本。v1.3、監督裁定 T-4**)、`conformance-tests/test_c12_capability_agreement.py`、4 adapter (`r2db-api/conformance/conformance_adapter_r2db.py`、`r2db-api/conformance/conformance_adapter_r2db_http.py`、`MitateDB-api/conformance/conformance_adapter_mitatedb.py`、`MitateDB-api/conformance/conformance_adapter_mitatedb_http.py`)、`docs/design/CONFORMANCE_ADAPTER_V1.md`、**両 peer の packaged 複製** (`r2db-api/src/r2db_api/contract/data-service-api.v1.json`、`MitateDB-api/src/mitatedb_api/contract/data-service-api.v1.json`)、**両 peer の provisional gate** (`r2db-api/src/r2db_api/http.py`、`r2db-api/src/r2db_api/structured.py`、`r2db-api/src/r2db_api/service.py`、`MitateDB-api/src/mitatedb_api/http.py`、`MitateDB-api/src/mitatedb_api/cell.py`) | **単独 worktree。WP-0 の後、WP-2 / WP-3 の前。直列** |
| **WP-2** | **r2db** (worktree `phase9-r2db`、**直列サブ WP**) — **2a** R-2 (side table + upgrade + `alter_field` + choke point 6 箇所への `constraints`) / **2b** R-4 dry_run / **2c** R-5 idempotency (**同一コミットで capability document に `idempotency_entries` / `idempotency_retention_ms` の `limits` 値と `limit_enforcement` を足す**。v1.2、監督裁定 S-f) / **2d** R-6 budget / **2e** R-3 + R-7 + **版フリップ** + `ops verify-declarations` 更新 | `r2db-api/src/r2db_api/` (`structured.py` / `postgres.py` / `service.py` / `http.py` / `errors.py` / `limits.py` / `ops.py` / `platform_declarations.py`)、`r2db-api/migrations/`、`r2db-api/tests/`、`r2db-api/conformance/` (隔離 profile の値のみ) | **WP-3 と並行** |
| **WP-3** | **MitateDB** (worktree `phase9-mitatedb`、**直列サブ WP**) — **3a** R-2 (**`alter_field` は backend に単一 tx のメソッドを新設する**、v1.2 / S-g) / **3b** R-4 dry_run (**D-10 は撤回したので先頭要件は無い**、v1.1。**`PRECONDITION_FAILED` の例外クラスを `MitateDB-api/src/mitatedb_api/errors.py` に新設し、`_problem_for_exception` (`http.py:152-189`) の code 別固定文言に 1 行足し、in-process 経路 (`MitateDB-api/conformance/conformance_adapter_mitatedb.py:2260-2263`) でも同じ details が出ることを確認する**。v1.2 / S-h) / **3c** R-5 (**同一コミットで capability document に `idempotency_entries` / `idempotency_retention_ms` の `limits` 値と `limit_enforcement` を足す**。v1.2 / S-f) / **3d** R-6 / **3e** R-3 + R-7 + **版フリップ** | `MitateDB-api/src/mitatedb_api/` (`cell.py` / `field_types.py` / `backend_postgres.py` / `backend_sqlite.py` / `http.py` / `errors.py` / `config.py` / `identifiers.py` / `ops.py`)、`MitateDB-api/migrations/`、`MitateDB-api/tests/`、`MitateDB-api/conformance/` (隔離 profile の値のみ) | **WP-2 と並行** |
| **WP-4** | **完了ゲート + 記録** — root suite 単独、CI、perf 差分、`COLLECTION_FLOOR`、設計 §9〜§11、計画文書 §1 / §5 / §8、**第 16 次ハンドオーバー** | `conformance-tests/COLLECTION_FLOOR`、`docs/design/PHASE9_*.md`、`docs/design/ROADMAP_POST_PHASE7_V1.md`、`docs/work-orders/HANDOVER_202609xx_FABLE.md` (新設)、`docs/work-orders/WORK_ORDER_PHASE9_*.md` (訂正註) | **最後。単独** |

**`conformance-tests/` を触るのは WP-1 だけである。** **peer WP が conformance を直す必要が出たら監督裁定を仰ぐ** — 直接触らない。

**同型性表への行追加は監督の pair-closing commit である (v1.3 で追加。作業指示書起草者の疑義 2、監督裁定 T-2)**: **同型性表 `_ISOMORPHIC_TARGETS` (両 peer の `tests/test_audit_query.py`) への行追加は、capability ごとの pair (WP-2x と WP-3x) が両方 main にマージされた後に、監督が 1 コミット (pair-closing commit) で両 peer 分を足す。** **各 peer の実装担当は、自 peer 側の helper 名と対応する相手側の helper 名 (作業指示書の同型性表のとおり) を報告に書く。** **監督の pair-closing commit は両 peer の isomorphism テストを実行して緑を確認してからマージする。** **WP-2 × WP-3 の重なり 0 はこれで保たれる** (§8.1)。**実装担当が自分の判断で行を足さない** — 足せば両 peer の `tests/test_audit_query.py` を同時に触ることになり、並行する 2 WP の唯一の重なりを作る。

### 8.1 触るファイルの重なり (実ファイル名レベルの確認)

| 組 | 重なり | 根拠 |
|---|---|---|
| **WP-2 × WP-3** | **0** | **WP-2 が触るのは `r2db-api/` 配下のみ、WP-3 が触るのは `MitateDB-api/` 配下のみ**である。共有ディレクトリ (`conformance-tests/` / `spec/` / `tools/` / `docs/`) はどちらも触らない。**両者が並行する唯一の組であり、この行が「重なり 0」の要件が掛かる唯一の行である。** **唯一の例外候補である同型性表 `_ISOMORPHIC_TARGETS` (両 peer の `tests/test_audit_query.py`) への行追加は、どちらの実装 WP も行わない — pair (WP-2x と WP-3x) が両方 main にマージされた後に監督が 1 コミット (pair-closing commit) で両 peer 分を足す (v1.3。監督裁定 T-2)。** **したがって重なりは 0 のままである。** |
| **WP-1 × WP-2** | **重なる (直列で解消する)** | **WP-1 は provisional gate のために `r2db-api/src/r2db_api/http.py` / `structured.py` / `service.py` と packaged 複製 `r2db-api/src/r2db_api/contract/data-service-api.v1.json`、および `r2db-api/conformance/` の 2 adapter を触る。** WP-2 は同じ 3 ファイルの gate を外す。**したがって並行させない** — **WP-1 → WP-2 の直列である。** これは重なりの見落としではなく**順序による解消**であり、C8 の「重なり 0」要件は並行する組にのみ掛かる。 |
| **WP-1 × WP-3** | **重なる (直列で解消する)** | 同上。**WP-1 が `MitateDB-api/src/mitatedb_api/http.py` / `cell.py`、packaged 複製、`MitateDB-api/conformance/` の 2 adapter を触る。** |
| **WP-1 × WP-4** | **0** | WP-4 は `conformance-tests/COLLECTION_FLOOR` と `docs/` のみ。**WP-1 は `COLLECTION_FLOOR` を触らない** (更新は完了ゲートのみ、§6.7)。 |
| **WP-2 × WP-4 / WP-3 × WP-4** | **0** | WP-4 は peer の `src` を触らない。 |
| **全 WP × WP-9 (フェーズ7 公開ゲート)** | **0** | **WP-9 が触るのは `tools/rewrite_hash_refs.py` と `docs/` 配下の hash 参照の一括更新のみである。** **本フェーズが `tools/` に足すのは `tools/contract_catalog.py` (新設) だけであり、`tools/rewrite_hash_refs.py` を作りも直しもしない。** 本フェーズが新設・改訂する docs (`docs/design/PHASE9_*.md`、`docs/work-orders/WORK_ORDER_PHASE9_*.md`、第 16 次ハンドオーバー) に commit hash を書いた場合、**WP-9 の commit-map 適用対象になるだけで衝突しない** (フェーズ8 §8.1 最終行と同じ判断)。 |

**WP-2 と WP-3 のサブ WP 内の直列性**: **同じ peer の `src` を複数のサブ WP が触るので、2a → 2b → 2c → 2d → 2e / 3a → 3b → 3c → 3d → 3e は同一 worktree で直列に進める。** **peer 間だけが並行である。**

**フェーズ8 の運用教訓の適用** (第 15 次 §4-5): **WP-2 と WP-3 はそれぞれ自分の peer の `tests/` にファイルを足すので、ファイル名の衝突は起き得ない** (別ディレクトリ)。**ただし同一 peer 内のサブ WP 同士は同じ `tests/` に足すので、サブ WP ごとにファイル名の接頭辞を分ける** (例: `test_constraints_*.py` / `test_dry_run_*.py` / `test_idempotency_*.py` / `test_budget_*.py` / `test_denial_details_*.py`) — 作業指示書で明示する。

---

## 9. 完了ゲート

1. **root suite の単独実行** `./.venv/bin/python -m pytest -q -n 5 --dist loadgroup` (監督が単独で実行。`ps` で他の pytest が 0 件であることを確認してから。ローカル PG の `max_connections = 300` が前提):
   - **`failed` = 0**
   - **`xfailed` = 0** (§6.6: WP-1 が置く 8 本はすべて、実行時に plug の宣言を読む条件が偽になることで外れる。**残るなら、その組と理由を台帳と当該条件行に開示する**)
   - **`skipped` = 0**
2. **CI の 3.11 job の集計行が 1 の集計行と一致すること。** `tally-consistency` job が緑 (3.11 / 3.12 の 4 数の一致)。**collection floor step が 3.11 / 3.12 の両 job で緑であること。**
3. **性能差分を §11.2 に記録すること** — `./.venv/bin/python tools/perf_baseline.py --warmup 20 --n 200` を**単独実行**し、**フェーズ8 §11.2 と同形式** (PERFRUN 行 + PERF 表) で記録し、**同一 plug の版間差分 (p50 / p95 / `backend_calls`)** を並記する。**plug 間の比較はしない** (L8-11)。**閾値は無い** (P-8)。**本フェーズは「2 フェーズ安定」の 2 フェーズ目である** (計画文書 §7 の 3)。
4. **`COLLECTION_FLOOR` をゲート時の実測値へ更新すること** (着手時点は 2340)。
5. **契約 1.7.0 の記録**: **契約 JSON と両 peer の packaged 複製 2 本の sha256 が 3 本一致すること**を §11.1 に記録する (**値はフェーズ8 の `968d3c72…45e6` から必ず動く**)。**R-10 (B) のマニフェスト逆適用 deep-equal 検証の結果 (差分 0 と走査キー数) も §11.1 に記録する。**
6. **両 peer の `contract_version` が 1.7.0 であること** — 4 箇所 (`r2db-api/src/r2db_api/service.py` / `control_plane.py`、`MitateDB-api/src/mitatedb_api/cell.py` / `control_plane.py`) と、**C-19 の data 面 / control 面一致 assert が緑であること。**
7. **新条件 C-20〜C-25 が four adapters で executable であること** — `CONDITIONS.md` の 6 行が `executable (four adapters)` であり、`conformance-tests/test_conditions_register.py` の照合が緑であること。**各条件の非 vacuity assert (§6.2) が緑であること。**
8. **全 WP が常設規律 1〜7 と速度規律 1〜5 を満たすこと。** 各 WP の「完了条件番号 → 変異」対応表に、対応の無い行が無いこと。**変異を持たない完了条件については、照合対象の逐語記録 (実行したコマンドと集計行、または file:line) を §11 に残すこと自体を完了条件とする** (フェーズ8 §9 の 6 と同じ規律)。
9. **設計レビュー 2 回** (契約を触るフェーズ。計画文書 §9 の 3)。**1 回目は v1.0 に対して実施済み (Blocker 4 / Major 9 / Minor 10 を全件反映して v1.1)。2 回目は v1.1 に対して実施済み (Blocker 4 / Major 9 / Minor 13 を全件反映して v1.2、監督裁定 S-a〜S-n)。以後の設計レビューは行わない — 作業指示書の正本は本設計 v1.3 である。** **v1.3 はレビューではなく、作業指示書起草者の疑義 4 件に対する監督裁定 T-1〜T-4 の反映である (レビュー回数は 2 回のままである)。**
10. **§5 U-1〜U-8 の確定が §5 に逐語で記録されていること** (計画文書 §9 の 4)。**確定文言は確定文ファイル経由で複製されていること** (常設規律 4)。
11. **`pg_database` の前後差分が 0 であること。他の pytest が 0 件であること。**
12. **provenance スキャナへの 0 ヒット (v1.1 で追加。レビュー 1 M7、監督裁定 R-k)**: **1.7.0 が新設 / 改訂したすべての契約 JSON 値に対して `conformance-tests/test_contract_history_register.py:64-79` の `_PATTERNS` を走らせ、ヒット 0 件を実測して §11.1 に記録すること。**
13. **既存 assert の非破壊の実測 (v1.1 で追加。レビュー 1 M5 / M6。v1.2 で 1 項追加、レビュー 2 M1)**: **`conformance-tests/test_contract.py:343-360` の件数正規表現が 1.7.0 段落追加後も 1.4.0 を拾い続けること**、**`conformance-tests/test_contract_history_register.py` の `assert checked == 17` (`:388`) がマニフェスト逆適用後の値に対して無改訂で通ること**、および **`PIN_1_5_0_SENTENCE_1` を 2 変種に分割した後、`versioning.version_binding` 側の照合 (`conformance-tests/test_contract.py:510`) が無改訂で通ること**を、それぞれ実測して §11.1 に記録すること。
14. **各条件の肯定枝が 4 plug で通っていることの確認 (v1.2 で追加。レビュー 2 B3、監督裁定 S-c)**: **C-20 / C-22 / C-23 / C-24 について、両 peer のフリップ後に 4 plug すべてが肯定枝 (`enforced` / `dry_run_enabled` / `retry_same_result` / `budget_enforced`) を観測していることを、xfail の残数と各条件の `observed_branch` の集計行で**監督が確認し、§11.1 に記録すること。**これは suite 内の集約 assert では成立しない** (`-n 5 --dist loadgroup` では plug ごとに worker が分かれる)。
15. **`idempotency` に条件付く 2 limit class の宣言 (v1.2 で追加。レビュー 2 M2、監督裁定 S-f)**: **両 peer の capability document が `idempotency_entries` / `idempotency_retention_ms` の `limits` 値と `limit_enforcement` エントリを持つこと** (C-05 V1 (e) の `_CAPABILITY_CONDITIONED`)。
16. **`capability_status.defined` の全 14 語を両 peer が名指していること (v1.2 で追加。レビュー 2 m7)**: **現行の `conformance-tests/test_c11_document_conformance.py:55-56` は「宣言した名前が `defined` に含まれる」という片方向しか見ておらず、逆方向 (defined の全語を peer が宣言する) の assert はリポジトリに無い。** **分岐ヘルパは capability 不在時に `"unavailable"` を既定値にするので、D-1 (3) の「新設 capability を同じコミットで `unavailable` として宣言に載せる」は、載せなくても全条件が緑になる。** **確定 (v1.3。監督裁定 T-4)**: **この assert は C-11 (`conformance-tests/test_c11_document_conformance.py`) に逆方向 (defined ⊆ declared) の assert として WP-1 で足す。版ゲートは置かない。** **どこに置くかを WP-1 の裁量にしない** (v1.2 は `test_operation_catalog_register.py` との二択を WP-1 に委ねていた)。**WP-1 の完了条件として、両 peer の capability document が `capability_status.defined` の 14 語すべてを名指していることを実測して §11.1 に記録する。**

---

## 10. 台帳 (本フェーズの起票項目)

**本節は起票時 (設計 v1.0) の内容である。実施結果は §11 と各項の状態注記に書く。**

- **L9-1 `schema_objects` の数え方が両 peer で一致していない (F-5)**。r2db は **entity 1 + field 数 + index 数** (`r2db-api/src/r2db_api/postgres.py:1620-1627`、`structured.py:1467` / `:1478`、既定 1000 は `limits.py:12-20`)、MitateDB は **`information_schema` のテーブル数のみ** (`MitateDB-api/src/mitatedb_api/backend_postgres.py:494-507`、既定 128 は `config.py:35`) であり、MitateDB は field 数を**別軸 `max_fields`** で `ValidationError` として扱う (`cell.py:617` / `:708`)。**契約 `limits.classes` の `schema_objects` の意味が peer で一致していない** — **P-6 の既存の差である。** **§5 U-1 = (β) の確定により、本項は本フェーズでは解消せず、開いたまま残して別途扱う。** **本項に実測値を記録する。** **開いたまま (記録)。**
- **L9-2a MitateDB は `IDENTIFIER_INVALID` を発行しない (F-7)**。`MitateDB-api/src/mitatedb_api/identifiers.py:30` が `ValidationError` へ畳み込み、その判断を `http.py:88-96` が明記している。**D-3 の適用範囲は「発行されるときの形」なので、発行しない実装は縛られない** — **本フェーズでこの非対称を変えない。** **帰結として C-21 の `IDENTIFIER_INVALID` 枝は MitateDB 2 plug で観測されない。** **この事実を C-21 行に開示し、本項に記録する。** **将来 identifier 検証を分離するときに再評価する。** **開いたまま (記録)。** (**v1.2 で L9-2 を 2 項に分割した。レビュー 2 M4、監督裁定 S-h。**)
- **L9-2b MitateDB の `PRECONDITION_FAILED` は本フェーズで閉じる (v1.2 で新設。レビュー 2 M4、監督裁定 S-h)**。**現行の MitateDB は `PRECONDITION_FAILED` をリポジトリ全体でコード文字列として持たない** — 出現するのは `MitateDB-api/src/mitatedb_api/http.py:89` のコメント、`audit_dispatch.py:48` のコメント、および同梱契約 JSON だけである。**D-4 の plan 失効判定がこの code を初めて必要にするので、WP-3b が例外クラスを新設する** (§8、D-4 実装の形 5)。**`revision_preconditions` (行単位の precondition) が `unavailable` である事実は変わらない**が、**「`PRECONDITION_FAILED` を発行しない実装」ではなくなる。** **v1.1 の L9-2 は「本フェーズでこの非対称を変えない」と書いており、D-4 (7) / C-22 (8)(9) と両立しなかった。** **閉止は WP-3b の完了時である。** **開いたまま (閉止予定)。**
- **L9-3 r2db は limits の配備時 env override を持たない (F-18)**。`r2db-api/src/r2db_api/limits.py:12-20` の既定値を `main.py` が参照せず、上書き経路が無い (control-plane 側だけは `R2DB_CONTROL_LIMIT_*` で上書きできる)。MitateDB は `MitateDB-api/src/mitatedb_api/config.py:20-220` が `MITATEDB_MAX_*` で上書きできる。**budget (D-6) は「配備値より小さくする」機構なので本フェーズの機能には影響しないが、同型性 (P-6) の差として記録する。** **配備者が bound を配備ごとに動かせないことは、`limits.profile` (「Limits are deployment-profile values」) の趣旨からは弱い。** **開いたまま (記録)。**
- **L9-4 `CapabilityDocument.operation_catalog_url` を両 peer は本フェーズで宣言しない (D-8)**。optional であり義務でもないので、宣言しない実装も conformant である。**帰結として、この項目が load-bearing になる条件は本フェーズには無い** — 契約に置くだけである。**宣言する実装が現れた時点で「宣言した URL が実在するか」が問題になり、それは L7-2 / L6-5 の `surfaces` とまったく同じ問題である。** **開いたまま (記録)。**
- **L9-5 R-10 (B) の `unstripped` 件数 (D-9)**。**マニフェストに `unstripped: true` で残る値の件数と、その各々の理由を本項に記録する。** **`versioning.version_binding` (10,269 字、契約全体の 13.32%) は `unstripped` になる見込みが高い** — 版の言及が規範文そのものに織り込まれており、接頭辞として剥がせる形をしていない (F-21、`spec/CONTRACT_HISTORY.md` 前文 limitation 3)。**あわせて、剥離によって契約 JSON が実際に何バイト短くなったかを記録する** — フェーズ8 の (A) が「1 文字も減らない」だった限界に対する、本フェーズの実測の答えである。**確定後の `unstripped` は 3 件である** — `versioning.version_binding` (10,269 字の累積叙述であり、後続文が同一値内の先行文を参照するため、機械的な分離ではなく再著述になる)、`versioning.compatibility`、`destructive_confirmation.phrase_construction.rules[3]` (後 2 者はマーカーが括弧・接頭辞の形を取らず、規範文中の裸の語として現れる)。**残り 26 件の内訳は、監督裁定 S-d を織り込んだ確定後の分類で `strip-prefix` 14 / `strip-insert` 11 / 両方 1 である** (草案時点は 13 / 12 / 1。**#18 `schemas.AuditResult.properties.events.items.description` が `strip-insert` から「接頭辞全体の除去 + `this ruling closes` → `this contract closes` の語改訂」へ移った**。**この 1 件は、挿入句を剥がしただけでは規範文の中に裸の `ruling` が残り、D-9 の新規 assert (剥離後スキャナ 0 ヒット) が赤になるからである** — レビュー 2 B4 の実測、監督裁定 S-d。**この値は PIN 定数を持たないので確定文言の破棄には当たらない。**)。**削減量の設計時点の見積り (v1.2 で追記。レビュー 2 m10)**: **レビュー 2 の実測 (26 値 + 追加剥離 2 件) が 1,787 バイト / 契約 JSON 全体 77,119 バイト = 2.3% であり、S-d の扱い (#18 で剥がす範囲が 26 字から 50 字へ広がって +24 バイト、語改訂で -2 バイト) を織り込むと約 1,809 バイト / 2.3% である。** **完了時に、実際にマニフェストへ入った件数と契約 JSON のバイト減少量の実測へ改める。** **開いたまま (WP-1 の実測待ち)。**
- **L9-6 (撤回) §5 U-4 が (B) の場合、D-10 (MitateDB SQLite の revision 永続化) は共通 suite から観測されない**。**本項は v1.1 で撤回した (前提事実の誤り、レビュー 1 B1)。** 起票時の内容は「plan トークンが descriptor digest 由来なら revision の永続性を共通条件が検査する経路が無く、担保が peer-local テストだけになる」というものであり、**D-10 (MitateDB SQLite backend の revision 永続化) が行われることを前提にしていた。** **D-10 は撤回された** — MitateDB の SQLite backend は `sqlite3.connect(":memory:")` のみ (`MitateDB-api/src/mitatedb_api/backend_sqlite.py:87`) のプロセス内 backend であり、永続化すべき対象が存在しないからである (§3 D-10、F-16)。**あわせて §5 U-4 = (A) が確定したので、(B) を前提とする本項の想定そのものが成立しない。** **撤回の記録として残す (削除しない)。**
- **L9-7 L7-8 (C-07 (ii) の肯定側が未到達) は本フェーズで閉じる予定である**。`conformance-tests/test_c07_atomicity_and_retry.py:106-158` の `retry_same_result` 枝は、両 peer が `idempotency: enabled` を宣言した時点で **4 plug で load-bearing になる** (D-5 (7))。**テストは 1 文字も変えない** — 宣言が変わることで枝が入れ替わる。**閉止は WP-2c / WP-3c の完了時である。** **C-07 行の開示文の書き換えは WP-1 で行う** (§6.4) が、**実際に肯定枝が通るのは実装 WP の後である。** **開いたまま (閉止予定)。**
- **L9-8 L8-4 (R-10 (B) をフェーズ9 へ送る) は本フェーズで閉じる予定である**。フェーズ8 設計 §10 L8-4 が「フェーズ9 の着手材料として開いたまま保持する」と書いた項目であり、**D-9 の 5 段手順の完了をもって閉じる。** **閉止条件は (i) 依頼者の再確定 (§5 U-6)、(ii) マニフェストの設置、(iii) deep-equal 検証の差分 0、(iv) 3 複製の同一バイト更新、(v) PIN 書き換えの 5 つすべてである。** **1 つでも欠ければ閉じない。** **開いたまま (閉止予定)。**
- **L9-9 L8-9 (`versioning.version_binding` の機械可読化) は本フェーズで閉じる予定である**。フェーズ8 設計 §10 L8-9 が「フェーズ9 へ保持」と書いた項目であり、**D-8 の `versioning.obligations` 配列 + register 2 本 (版集合一致 / 無条件件数一致) の設置をもって閉じる。** **散文は残す** (A-6) ので、L8-9 が想定した「配列に組み替える」形そのものではない — **「散文を残し、機械可読な索引を並置し、両者を register で縛る」形である。** **この差を閉止時に明記する** (R-14 の流儀: 起票時の想定と実施形が違うときは、根拠と日付を添えて書く)。**開いたまま (閉止予定)。**
- **L9-10 契約 1.7.0 は無条件義務を 2 件持つので、1.6.0 のみを宣言する第三者実装との差が広がる**。1.6.0 の無条件義務は 2 件 (`surfaces` と bearer secret)、1.7.0 で 2 件 (details 語彙と `request_id`) が加わり、累計 4 件になる。**retroactive-denial 規定によりこれらは 1.6.0 実装に遡及しない**が、**「1.7.0 を宣言するには 2 件を無条件で満たす必要がある」という参入障壁が上がる。** **これは意図した設計 (宣言の価値を上げる) であり欠陥ではないが、版を上げる費用として記録する。** **開いたまま (記録)。**
- **L9-11 `result_items` の意味と駆動点が両 peer で一致していない (v1.1 で起票。レビュー 1 M3、監督裁定 R-g)**。r2db は mutation の `affected` 件数に**逐次** `limits.check("result_items", affected)` を掛ける (`r2db-api/src/r2db_api/structured.py:1272`、`r2db-api/src/r2db_api/postgres.py:1163`) が、**MitateDB は mutation の `affected` に対する検査を持たず**、read 経路の**要求 `limit` の事前検査**としてのみ持つ (`MitateDB-api/src/mitatedb_api/cell.py:834-837`)。**つまり `result_items` が数えているものが「返した行数」「要求した上限」「影響した行数」の間で peer 一致していない** — **L9-1 の `schema_objects` と同型の P-6 の既存差である。** **本フェーズでは変えない** — D-6 の適用表から mutation の `result_items` を外すことで、**新しい強制点を MitateDB に実装させないことを選んだ** (P-5)。**C-24 が `result_items` を駆動するか否かは WP-1 の実測で決め、駆動しないなら C-24 行に開示する。** **開いたまま (記録)。**
- **L9-12 `limits.example_profile` は `limits.classes` の全 class を網羅しない (v1.1 で起票。レビュー 1 m10)**。`limits.classes` は 16 語だが `example_profile` は 15 値であり、**`audit_requests_per_minute` を持たない** (2026-09-07 実測)。**本フェーズは `enum_members` を `classes` (17 語へ) と `example_profile` (16 値へ) の両方に足す**が、**既存の欠落は埋めない** — 埋めるかどうかは `example_profile` が「例示」なのか「網羅」なのかという契約上の位置づけの判断であり、本フェーズの範囲ではない。**「`example_profile` は全 class を網羅しない例示である」ことを本項に記録し、将来 `example_profile` に依存する条件を書くときの前提とする。** **開いたまま (記録)。**
- **L9-13 idempotency の replay と `destructive_confirmation.evaluation_order` の関係を 1.7.0 が初めて定めた (v1.2 で起票。レビュー 2 B2、監督裁定 S-b)**。**契約 `destructive_confirmation.evaluation_order` は「confirmation は shape / 認証・認可 / target-existence の後、precondition と execution の前」と定めているが、記録済み `idempotency_key` の照会がその列のどこに入るかは 1.6.0 まで定義されていなかった。** **1.7.0 は「認証・認可・bound の後、target-existence の前」と定める** (D-5 (8))。**これを定めないと、破壊操作 (`drop_entity` / `delete`) の再送だけが両 peer で割れる** — 照会が confirmation より後なら、target が既に無いので `NOT_FOUND`、あるいは state fingerprint が変わっているので `DESTRUCTIVE_CONFIRMATION_REQUIRED` になる。**`evaluation_order` の文言そのものは変えず、`structured_operations.idempotency.record` の側に置いた。** **将来 `evaluation_order` を機械可読化するときに、この挿入位置も同じ表に載せるかを再評価する。** **開いたまま (記録)。**

### 10.1 計画文書への改版文案 (§5 U-5 = (B) と U-4 = (A) の帰結。v1.1 で追加、v1.2 で R-4 行を追加)

**§5 U-5 = (B) の確定により、計画文書 §5 R-8 が列挙していた「返し得る code」を初版のカタログから外す。** **計画文書は正本であるから、R-14 の規約 (起票時の原文を消さず、改版註を日付・根拠つきで足す) に従って改版する。** **下記はその文案であり、計画文書 `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の R-8 行の内容セル末尾に足す。改版そのものは WP-4 で行う** (本フェーズの設計文書は計画文書を書き換えない)。

> **【改版 2026-09-07 (R-14)。上の文は起票時の原文であり、消さずに残す】** **フェーズ9 が出す初版の操作カタログは、`endpoints` / `control_endpoints` ごとの role・destructive・atomicity 境界・能力依存・request / response schema を持つが、§5 R-8 が列挙していた「返し得る code」(`endpoints.*.error_codes`) は含めない。** **根拠: この宣言は片方向 (「観測した code ⊆ 宣言」) しか検査できず、「宣言にあるが観測されない code」が advisory として残る。P-3 (advisory な宣言を catalog に載せない) を優先した。** **エージェントは `errors.codes` の全域 17 code と各節の記述から判断する (現行どおり)。** **監督裁定 2026-09-07 (依頼者裁定「判断しなければならないものが出たらあなたの推奨で進めてください。後で報告してください。」の委任に基づく)、フェーズ9 設計 §5 U-5 = (B)。**

**あわせて計画文書 §5 フェーズ9 節の R-4 行も改版する (v1.2 で追加。レビュー 2 M5、監督裁定 S-i)。** **§5 U-4 = (A) は「schema revision」を採る点では正本どおりだが、その revision は「対象 entity の」ではなく「対象 Application の」であり、意味が違う。** **下記はその文案であり、計画文書 `docs/design/ROADMAP_POST_PHASE7_V1.md` §5 のフェーズ9 節 R-4 行の末尾に足す。改版そのものは WP-4 で行う。** (**v1.1 は「改版は要らない」と書いていたが、それは誤りであった。**)

> **【改版 2026-09-07 (R-14)。上の文は起票時の原文であり、消さずに残す】** **plan の schema 状態成分は「対象 entity の schema revision」ではなく「対象 Application の schema revision」である。** **根拠: 両 peer とも entity 単位の revision を持たず、`SchemaOperationResult.revision` は per-application の単調カウンタである** (r2db `r2db-api/src/r2db_api/postgres.py:1900-1935`、MitateDB `MitateDB-api/src/mitatedb_api/backend_postgres.py:646-661`。フェーズ9 設計 F-16)。**帰結として、対象 entity に無関係な entity への schema 操作も plan を失効させる** — **これは fail-closed 側の誤差であり (失効しすぎることはあっても、変わった schema を見落とすことはない)、安全側である。** **契約 `structured_operations.dry_run.plan` がこの広さを 1 文で開示する。** **監督裁定 2026-09-07 (依頼者裁定「判断しなければならないものが出たらあなたの推奨で進めてください。後で報告してください。」の委任に基づく)、フェーズ9 設計 §5 U-4 = (A) と §3 D-4 (7)。**

---

## 11. 実施記録

**本節は完了ゲート (WP-4) で記入する。設計 v1.0 の時点では空欄である。**

### 11.1 集計行

***(未記入。完了ゲートで記入する。記入する項目: 取得条件 (worktree / branch head / main merge / `ps` 確認 / PG 設定 / `pg_database` 前後差分)、root suite の集計行と EXIT、CI の 3.11 / 3.12 の集計行と run id、`--collect-only -q` の件数と `COLLECTION_FLOOR` 更新、xfail の残数と内訳、契約 3 複製の新 sha256、R-10 (B) の deep-equal 検証結果 (差分 0 と走査キー数)、剥離による契約 JSON のバイト減少量、`unstripped` 件数、両 peer の `contract_version` の 4 箇所、**1.7.0 が新設 / 改訂した契約値に対する provenance スキャナのヒット数 (0 であること、§9 の 12)**、**`test_contract.py:343-360` が 1.7.0 段落追加後も 1.4.0 を拾い続けること**、**`test_contract_history_register.py` の `assert checked == 17` が逆適用後の値に対して無改訂で通ること** (§9 の 13)。)***

### 11.2 性能差分 (P-8)

***(未記入。完了ゲートで記入する。形式はフェーズ8 設計 §11.2 と同一 — PERFRUN 行 (逐語) + 実行コマンド (逐語) + PERF 表 (plug × op)。あわせて、フェーズ8 §11.2 の基準値に対する**同一 plug の版間差分** (p50 / p95 / `backend_calls`) を並記する。plug 間の比較はしない (L8-11)。閾値は置かない (P-8)。)***

### 11.3 WP ごとの記録

***(未記入。各 WP の完了時に記入する。少なくとも次を含める: WP-1 の C-05 行のセル長実測と `MAX_CELL_LENGTH` に対する余裕、port v1.13 の 5 フィールドについて「adapter が捨てる変異が赤になる」ことの実測 (L8-15)、WP-2a / WP-3a の既存行走査における MitateDB developer 接続の SELECT 権限の実測 (F-6 の未確認点)、WP-2e の `field` 値を要求内パスへ改めた箇所の AST 全数走査の結果 (grep を根拠にしない。第 15 次 §5 の教訓)、**WP-1 の `SchemaOperationRequest.properties.enum` が `_check_object_shape` / `schema_check.py` の 2 検証器と衝突しないことの実測** (§3 D-2 開示事項、レビュー 1 m6)、**C-24 が `result_items` を駆動するか否かの WP-1 の実測結果** (§3 D-6 開示事項、レビュー 1 M3)、**WP-3a の「既存行走査と DDL の間に他 session の書き込みが入る隙間が無い」ことを示す peer-local テストの結果** (§3 D-2 実装の形 4、レビュー 2 M3)、**WP-1 の `BatchOperation.idempotency_key` 混在拒否 (§6.1 (v)) の実測**、各サブ WP の「完了条件番号 → 変異」対応表。)***

---

## 付録 A. R-8 プロトタイプ出力 (常設規律 5)

**本付録は `spec/data-service-api.v1.json` (1.6.0) に対する機械走査の結果であり、判断を含まない事実の記録である。** §3 D-8 と §4 A-7 はこの出力を根拠にしている。**逐語プロトタイプの出力を、見出しの階層だけ 2 段下げてそのまま転記した (内容は 1 文字も変えていない。ただし冒頭 2 文だけは、作業機のパスを含む記述を「コミットしない」旨の記述へ置き換えた)。**

**読み方**: **(i) が純粋な射影で得られる行**、**(ii) が「(a) role / (b) destructive / (c) atomicity / (d) 返し得る code / (e) 能力依存の 5 項目を、現行 JSON から純粋な射影で導けるか」の判定**である。**判定はすべて PARTIAL / MOSTLY NO / NO であり、これが D-8 の決定「1.7.0 が機械可読の構造化フィールドを契約 JSON に足し、生成器は純粋な射影にする」の根拠そのものである。** **(iii) は `versioning.version_binding` の版ごとブロック抽出**であり、**1.3.0 / 1.5.0 のブロックがマーカーを 1 つも持たず抽出に失敗すること**と、**1.4.0 の生の marker 数 8 に対し distinct が 6 であること (素朴な marker 計数は信用できず dedup が要る)** を記録している — **D-8 の register テスト (obligations ↔ 散文の件数一致) を「件数語」との照合として設計した根拠である。** **(iv) は候補キーの列挙のみであり、設計判断を含まない** (D-8 が採ったのはこの候補の一部である)。

**逐語転記 (ここから)**

Throwaway prototype (常設規律 5). Read-only against the repo; the script and its raw output are not committed.

#### (i) Pure projection: endpoints + control_endpoints

Total rows: 19 (7 endpoints + 12 control_endpoints)

| group | name | method | path | auth (raw) | request schema | response schema | request required | request properties | response required | response properties |
|---|---|---|---|---|---|---|---|---|---|---|
| endpoints | capabilities | GET | /v1/capabilities | application or control |  | CapabilityDocument |  |  | contract_version, capabilities, limits, limit_enforcement, authorization_propagation_bound_ms | contract_version, capabilities, limits, limit_enforcement, authorization_propagation_bound_ms, application_scope, role, surfaces |
| endpoints | query | POST | /v1/data/{entity}/query | runtime or developer | QueryRequest | QueryResult | select | select, where, order_by, page | items, next_page | items, next_page, revisions |
| endpoints | mutate | POST | /v1/data/{entity}/mutations | runtime or developer | MutationRequest | MutationResult | operations | operations, transaction, idempotency_key | committed, affected | committed, affected, assigned_addresses |
| endpoints | cross_entity_mutate | POST | /v1/data/mutations | runtime or developer | ScopedMutationRequest | MutationResult | operations | operations, idempotency_key | committed, affected | committed, affected, assigned_addresses |
| endpoints | catalog | GET | /v1/catalog | runtime or developer |  | CatalogDocument |  |  | application_scope, entities | application_scope, entities |
| endpoints | schema | POST | /v1/schema/operations | developer | SchemaOperationRequest | SchemaOperationResult | operation, entity | operation, entity, field, fields, index, unique, field_type, field_types, destructive, confirmation, revision | committed, revision | committed, revision |
| endpoints | audit_query | POST | /v1/audit/query | control or audit | AuditQueryRequest | AuditResult |  | event_classes, after, limit | events | events |
| control_endpoints | control_capabilities | GET | /control/v1/capabilities | control or audit |  | CapabilityDocument |  |  | contract_version, capabilities, limits, limit_enforcement, authorization_propagation_bound_ms | contract_version, capabilities, limits, limit_enforcement, authorization_propagation_bound_ms, application_scope, role, surfaces |
| control_endpoints | register_application | POST | /control/v1/applications | control | ApplicationRegistrationRequest | ApplicationStateResult | application_id | application_id | application_id, enabled | application_id, enabled |
| control_endpoints | list_applications | GET | /control/v1/applications | control or audit |  | ApplicationsResult |  |  | applications | applications |
| control_endpoints | disable_application | POST | /control/v1/applications/{application_id}/disable | control |  | ApplicationStateResult |  |  | application_id, enabled | application_id, enabled |
| control_endpoints | enable_application | POST | /control/v1/applications/{application_id}/enable | control |  | ApplicationStateResult |  |  | application_id, enabled | application_id, enabled |
| control_endpoints | issue_credential | POST | /control/v1/credentials | control | CredentialIssueRequest | CredentialIssued | application_id, role | application_id, role | credential_id, application_id, role, secret | credential_id, application_id, role, secret |
| control_endpoints | list_credentials | GET | /control/v1/credentials | control or audit |  | CredentialsResult |  |  | credentials | credentials |
| control_endpoints | rotate_credential | POST | /control/v1/credentials/{credential_id}/rotate | control |  | CredentialRotated |  |  | credential_id, secret | credential_id, secret |
| control_endpoints | revoke_credential | POST | /control/v1/credentials/{credential_id}/revoke | control | CredentialRevokeRequest | CredentialStateResult |  | destructive, confirmation | credential_id, enabled, revoked | credential_id, enabled, revoked |
| control_endpoints | disable_credential | POST | /control/v1/credentials/{credential_id}/disable | control |  | CredentialStateResult |  |  | credential_id, enabled, revoked | credential_id, enabled, revoked |
| control_endpoints | enable_credential | POST | /control/v1/credentials/{credential_id}/enable | control |  | CredentialStateResult |  |  | credential_id, enabled, revoked | credential_id, enabled, revoked |
| control_endpoints | audit_query | POST | /control/v1/audit/query | control or audit | AuditQueryRequest | AuditResult |  | event_classes, after, limit | events | events |

#### (ii) Can (a)-(e) be derived by pure projection?

| item | verdict | summary |
|---|---|---|
| (a) role | PARTIAL | PARTIAL: mechanical tokenization + set-membership against security.roles recovers the union-of-roles for every endpoint EXCEPT the literal token 'application' (used in endpoints.capabilities.auth == 'application or control'), which does not appear in security.roles at all. 'application' is only defined in prose (security.schemes / security.scope) as an umbrella over runtime+developer credentials -- recovering that requires interpreting that prose, not just projecting security.roles. |
| (b) destructive | PARTIAL | PARTIAL: 3 of 5 clauses key off a CamelCase identifier that can be resolved to endpoint(s) mechanically, but only by expanding a SECOND $ref level (request schema -> array items -> #/definitions/Mutation or ScopedMutation), beyond the one-level expansion in step 1. Even once resolved to an endpoint, the actual gating condition ('.operation == "delete"', or '.operation in ("drop_entity","drop_index")', or 'revoking the LAST REMAINING ACTIVE control credential') is an enum-value and cross-request-state predicate expressed only in prose -- the JSON schema for Mutation.operation is an enum list, but WHICH enum member is 'destructive' is not tagged in the schema; that mapping is read off the applies_to prose string, not projected from a machine flag. The CredentialRevokeRequest clause and the trailing 'future destructive operations...' clause cannot be resolved mechanically at all (see per-clause notes). |
| (c) atomicity | MOSTLY NO | MOSTLY NOT PROJECTABLE: transactions has no endpoint/operation key at all -- it is 6 free-standing prose keys (default/atomic/best_effort/cross_entity/interactive/retry). The only mechanical hit is transactions.cross_entity, whose prose happens to contain the literal path 'POST /v1/data/mutations' and the literal capability id 'cross_entity_mutation' as substrings -- a verbatim string match, not a structural key. Which endpoints are 'atomic by default' (i.e. all of them, per transactions.default) vs. which may declare best_effort (mutate/cross_entity_mutate, per MutationRequest.transaction enum existing on those two request schemas) requires reading the request schema's 'transaction' enum property AND cross-referencing it against transactions.* prose by name -- an interpretation step, not a projection. |
| (d) error codes | NO (per-endpoint) | NOT PROJECTABLE per-endpoint: errors.codes is exactly one flat array (17 codes) shared by the whole contract; no endpoint or control_endpoint object carries an error-code list of its own. A catalog wanting 'which codes can THIS endpoint return' cannot get it from any key -- it would have to read each endpoint's 'semantics'/'auth' prose plus general sections (security.failure, destructive_confirmation.denial, structured_operations, limits) and infer applicability per endpoint. That is interpretation, not projection; the current JSON has no per-endpoint error-code key to project at all. |
| (e) capability dependency | NO (no shared key) | NOT STRUCTURALLY PROJECTABLE: capability_status.defined has no capability-id -> endpoint-name key anywhere. Exactly one entry (cross_entity_mutation) happens to embed a verbatim path string 'POST /v1/data/mutations' inside its free-text description; every other capability<->endpoint association (structured_query<->query, atomic_mutation<->mutate, application_catalog<->catalog, schema_operations<->schema, audit_query<->audit_query/control_audit_query, control_plane<->control_endpoints as a group) is inferable only by a human reading capability_status.defined's prose names/descriptions side by side with endpoint names/paths -- there is no shared key, id, or $ref between capability_status and endpoints/control_endpoints. capability_status.rules is pure prose (0 of 4 rules reference an endpoint or capability id in a structured way). versioning.version_binding does name capability ids (audit_query, application_catalog, schema_operations, control_plane, cross_entity_mutation) inline in prose when stating which obligations are conditional on them, but again as free text, not as a table/mapping key. |

##### (a) role detail

security.roles = ['runtime', 'developer', 'control', 'audit']

| endpoint | auth (raw) | matched role tokens | unmatched tokens |
|---|---|---|---|
| capabilities | application or control | control | application |
| query | runtime or developer | runtime, developer | - |
| mutate | runtime or developer | runtime, developer | - |
| cross_entity_mutate | runtime or developer | runtime, developer | - |
| catalog | runtime or developer | runtime, developer | - |
| schema | developer | developer | - |
| audit_query | control or audit | control, audit | - |
| control_capabilities | control or audit | control, audit | - |
| register_application | control | control | - |
| list_applications | control or audit | control, audit | - |
| disable_application | control | control | - |
| enable_application | control | control | - |
| issue_credential | control | control | - |
| list_credentials | control or audit | control, audit | - |
| rotate_credential | control | control | - |
| revoke_credential | control | control | - |
| disable_credential | control | control | - |
| enable_credential | control | control | - |
| audit_query | control or audit | control, audit | - |

##### (b) destructive detail

| applies_to clause | leading schema token | mapped endpoints (mechanical) | note |
|---|---|---|---|
| Mutation.operation == "delete" | Mutation | mutate | 'Mutation' is a #/definitions/ entry, not an endpoint request schema directly; it is only reachable by expanding a second $ref level (request schema's array property -> definitions.Mutation). |
| ScopedMutation.operation == "delete" | ScopedMutation | cross_entity_mutate | 'ScopedMutation' is a #/definitions/ entry, not an endpoint request schema directly; it is only reachable by expanding a second $ref level (request schema's array property -> definitions.ScopedMutation). |
| SchemaOperationRequest.operation in ("drop_entity", "drop_index") | SchemaOperationRequest | schema | - |
| CredentialRevokeRequest revoking the last remaining active control credential | - | - | Clause has no leading 'Identifier.' token to key off of (e.g. 'future destructive operations inherit this same definition') -- pure prose, nothing to project. |
| future destructive operations inherit this same definition | - | - | Clause has no leading 'Identifier.' token to key off of (e.g. 'future destructive operations inherit this same definition') -- pure prose, nothing to project. |

##### (c) atomicity detail

| transactions key | mentions endpoint path verbatim | mentions capability id verbatim |
|---|---|---|
| default | - | - |
| atomic | - | - |
| best_effort | - | - |
| cross_entity | - | cross_entity_mutation |
| interactive | - | - |
| retry | - | idempotency |

##### (d) error codes detail

errors.codes is a single flat array of 17 codes, scoped to the whole contract (no per-endpoint field found): AUTH_REQUIRED, AUTH_INVALID, AUTH_REVOKED, APPLICATION_DISABLED, AUTH_STATE_UNAVAILABLE, FORBIDDEN, SCOPE_MISMATCH, VALIDATION_FAILED, IDENTIFIER_INVALID, CAPABILITY_UNSUPPORTED, NOT_FOUND, CONFLICT, PRECONDITION_FAILED, LIMIT_EXCEEDED, DESTRUCTIVE_CONFIRMATION_REQUIRED, ATOMICITY_FAILED, SERVICE_UNAVAILABLE

##### (e) capability dependency detail

| capability id | mentions endpoint path verbatim in its prose |
|---|---|
| structured_query | - |
| atomic_mutation | - |
| application_catalog | - |
| schema_operations | - |
| audit_query | - |
| best_effort_transactions | - |
| idempotency | - |
| revision_preconditions | - |
| row_addressability | - |
| cross_entity_mutation | /v1/data/mutations |
| control_plane | - |

#### (iii) versioning.version_binding block extraction

version_binding is 10269 chars of prose; split into 5 blocks on the 'Only an implementation declaring X.Y.Z or higher' marker.

| version | unconditional markers (a)(b).. | conditional markers (1)(2).. raw | conditional markers distinct | 'N of those obligations are unconditional' sentence | declared N | extraction status | note |
|---|---|---|---|---|---|---|---|
| 1.2.0 | 0 [] | 4 ['1', '2', '3', '4'] | 4 ['1', '2', '3', '4'] | - | - | partial | Block enumerates obligations but does not split them into an unconditional/conditional sub-list (e.g. 1.2.0's (1)-(4) are all exhaustive, not divided). |
| 1.3.0 | 0 [] | 0 [] | 0 [] | - | - | failed | No (a)/(b)/... or (1)/(2)/... markers found in this block at all. |
| 1.4.0 | 3 ['a', 'b', 'c'] | 8 ['5', '1', '2', '2', '3', '4', '5', '6'] | 6 ['1', '2', '3', '4', '5', '6'] | Three of those obligations are unconditional | 3 | ok | (raw regex hit 8 occurrences of (N) tokens, e.g. duplicates/forward-references like a later '(this document's own ... obligation (N) below)' re-mentioning a number already used as a list marker -- 6 distinct numbers ['1', '2', '3', '4', '5', '6'] after dedup; naive marker counting alone is NOT reliable, dedup is required). |
| 1.5.0 | 0 [] | 0 [] | 0 [] | - | - | failed | No (a)/(b)/... or (1)/(2)/... markers found in this block at all. |
| 1.6.0 | 2 ['a', 'b'] | 2 ['1', '2'] | 2 ['1', '2'] | Two of those obligations are unconditional | 2 | ok | - |

#### (iv) Candidate structured keys for 1.7.0 (enumeration only -- no design judgment made here)

- endpoints.*.role_required / control_endpoints.*.role_required: an explicit array drawn from security.roles, replacing the free-text 'auth' string (would remove the need to tokenize 'X or Y or application-as-umbrella').
- A top-level 'application' role alias entry (or security.roles including 'application' explicitly with its runtime+developer expansion) so auth strings tokenize against a complete vocabulary.
- destructive_confirmation.applies_to entries restructured as objects, e.g. {schema, field, values, endpoints: [...]} instead of one prose string per clause, so 'which endpoints/operations are destructive' is a direct lookup.
- A machine flag on the relevant enum member itself, e.g. Mutation.operation enum entries carrying {value: 'delete', destructive: true} instead of a separate prose cross-reference.
- transactions.* entries carrying an explicit 'applies_to_endpoints': [...] or 'applies_to_capabilities': [...] array per key.
- A per-endpoint (or per-capability) 'error_codes': [...] array subsetting errors.codes, instead of one global flat list with no scoping.
- capability_status.defined entries carrying an explicit 'endpoints': [...] array (or the reverse: endpoints/control_endpoints entries carrying a 'capability': '<id>' field) to close the capability<->endpoint gap.
- versioning.version_binding restructured as data: a list of {version, unconditional: [...], conditional: [...], subordinate_ruling} objects instead of one 10K-character prose field -- would make the table in this prototype's step 3 unnecessary.
- capability_status.rules items carrying a structured 'applies_to' field (capability id or vocabulary name) instead of being pure prose.

**逐語転記 (ここまで)**

---

## 付録 B. R-10 (B) の before/after 一覧 (常設規律 5 + 常設規律 4)

**本付録は §5 U-6 の提示物そのものである。** §3 D-9 の手順 (i) がこの一覧の提示と再確定を着手条件としている。**逐語プロトタイプの出力を、見出しの階層だけ 2 段下げてそのまま転記した (内容は 1 文字も変えていない。ただし冒頭の生成元を述べる 1 文だけは、作業機のパスを含む記述を置き換え、逐語 JSON の所在の説明に改めた)。**

**v1.1 での追記**: **§5 U-6 の確定で草案より剥離範囲を広げた 2 件 (#9 / #25 / #26 の 3 行) に、「監督裁定で追加剥離」の注記と確定後の値を書き加えた。** **この 2 件はいずれも `strip-insert` のまま範囲だけが広がったので、分類の内訳と件数は動かない。**

**v1.2 での追記**: **監督裁定 S-d により #18 の行にも「監督裁定で追加剥離 + 語改訂」の注記と確定後の値を書き加えた。** **この 1 件は `strip-insert` から「接頭辞全体の除去 + 1 語の改訂」へ移るので、末尾の Overall classification totals の内訳が 1 件動く** — **草案時点の `strip-prefix` 13 / `strip-insert` 12 に対し、確定後は `strip-prefix` 14 / `strip-insert` 11 である。** **`両方` 1 と `unstripped` 3 は変わらない。** **totals の数表そのものは逐語転記なので書き換えず、この注記で差を示す。**

**それ以外の行・分類・件数は逐語転記のままである。**

**読み方**: **`分類`** は `strip-prefix` (値の先頭の "Since 1.x.0 (…): " 等を剥がす) / `strip-insert` (値の途中の "(subordinate ruling N)" 等の挿入句を剥がす) / `strip-prefix+strip-insert` (両方) / **`unstripped`** (規範文と不可分で剥がせない) の 4 種である。**`unstripped` は 3 件**であり、そのうち **`versioning.version_binding` は「値が 10,269 字の累積的な 1 本の叙述であり、後続文が同一値内の先行文を参照している」ため、機械的な prefix / insert 分離ではなく段落の再著述になる**ことが理由である (**L9-5 の見込みどおりである**)。**`PIN 状態` の列が「依頼者確定文言かどうか」を示し、test-pinned は 18 件である** (F-22 と一致)。

**逐語転記 (ここから)**

Generated mechanically from `spec/data-service-api.v1.json` by a throwaway prototype (常設規律 5), using the SAME scanner regex family as `conformance-tests/test_contract_history_register.py`. The full verbatim before/after text of every one of the 29 values is held as per-value JSON alongside this table and is attached in full when the list is put to the requester (§5 U-6); the table below truncates long values for readability only.

Total matched values: 29. Test-pinned (per Appendix A.2c): 18.

---

| # | json_path | PIN 状態 | before (truncated, full in .json) | 剥がす接頭辞・挿入句 (逐語) | after (truncated, full in .json) | 分類 |
|---|---|---|---|---|---|---|
| 1 | `audit.query_cursor` | test_contract.py:212 (test_audit_query_after_is_an_opaque_cursor @L209) via path expr | Since 1.4.0 (subordinate ruling 9, item 1, conditional): AuditQueryRequest.after is an opaque cursor, not an event_id or a numeric offset -- a client never constructs one itself, only echoes back the  …[snip]… ed with that same set of filters; reusing it under different filters is not defined by this version. | prefix: `Since 1.4.0 (subordinate ruling 9, item 1, conditional): ` | AuditQueryRequest.after is an opaque cursor, not an event_id or a numeric offset -- a client never constructs one itself, only echoes back the cursor field of the last event it received (query_event_f …[snip]… ed with that same set of filters; reusing it under different filters is not defined by this version. | strip-prefix |
| 2 | `audit.query_event_class_vocabulary` | test_contract.py:248 (test_event_class_is_a_declared_vocabulary @L244) via path expr | Since 1.4.0 (subordinate ruling 9, item 4, conditional): event_class is a vocabulary each implementation declares for itself, at capabilities().audit_query.event_classes -- this contract does not enum …[snip]… fields' own additive-vocabulary posture rather than capability_status.defined's closed status_enum). | prefix: `Since 1.4.0 (subordinate ruling 9, item 4, conditional): ` | event_class is a vocabulary each implementation declares for itself, at capabilities().audit_query.event_classes -- this contract does not enumerate a fixed event_class enum, and does not require an i …[snip]… fields' own additive-vocabulary posture rather than capability_status.defined's closed status_enum). | strip-prefix |
| 3 | `audit.query_event_fields_note` | test_contract.py:233 (test_audit_result_event_carries_plane_and_cursor @L223) via path expr | Since 1.4.0 (subordinate ruling 9, items 1 and 3, conditional): each event AuditResult.events[] returns from audit_query MAY carry fields beyond audit.fields -- plane (control or application: the dura …[snip]…  an open per-event shape (subordinate ruling 7(A)), so none of these are a schema-breaking addition. | prefix: `Since 1.4.0 (subordinate ruling 9, items 1 and 3, conditional): `<br>insert: ` (subordinate ruling 7(A))` | each event AuditResult.events[] returns from audit_query MAY carry fields beyond audit.fields -- plane (control or application: the durable source the event was read from, never a value the original e …[snip]… ditResult.events[] remains an open per-event shape, so none of these are a schema-breaking addition. | strip-prefix+strip-insert |
| 4 | `audit.query_operation_vocabulary` | test_contract.py:494 (test_contract_pins_the_requester_finalized_1_4_0_and_1_5_0_prose @L484) via path expr; PIN_1_5_0_SENTENCE_1/2/3/4 (pinned constants); test_contract.py:448 (test_version_binding_1_4_0_unconditional_and_conditional_counts_agree @L343) via substring-of-value grep | Since 1.5.0 (subordinate ruling 10, item 1, conditional): operations and target_kinds are vocabularies each implementation declares for itself at capabilities().audit_query.operations / .target_kinds  …[snip]… apability_status.defined.atomic_mutation.operations, which enumerates the executable mutation verbs. | prefix: `Since 1.5.0 (subordinate ruling 10, item 1, conditional): ` | operations and target_kinds are vocabularies each implementation declares for itself at capabilities().audit_query.operations / .target_kinds -- the sets of values the operation and target_kind fields …[snip]… apability_status.defined.atomic_mutation.operations, which enumerates the executable mutation verbs. | strip-prefix |
| 5 | `audit.query_ordering` | test_contract.py:231 (test_audit_result_event_carries_plane_and_cursor @L223) via path expr | Since 1.4.0 (subordinate ruling 9, item 2, conditional on audit_query being provided -- versioning.version_binding): AuditResult.events[] returned by audit_query is totally ordered by (recorded_at, pl …[snip]… ique, so recorded_at and plane together, not event_id alone, are what make the combined order total. | prefix: `Since 1.4.0 (subordinate ruling 9, item 2, conditional on audit_query being provided -- versioning.version_binding): ` | AuditResult.events[] returned by audit_query is totally ordered by (recorded_at, plane, event_id). plane is included in the ordering key because an implementation may hold more than one durable event  …[snip]… ique, so recorded_at and plane together, not event_id alone, are what make the combined order total. | strip-prefix |
| 6 | `audit.query_target_kind_vocabulary` | test_contract.py:495 (test_contract_pins_the_requester_finalized_1_4_0_and_1_5_0_prose @L484) via path expr; PIN_1_5_0_SENTENCE_1/2/3/4 (pinned constants); test_contract.py:448 via substring-of-value grep | Since 1.5.0 (subordinate ruling 10, item 1, conditional): operations and target_kinds are vocabularies each implementation declares for itself at capabilities().audit_query.operations / .target_kinds  …[snip]… apability_status.defined.atomic_mutation.operations, which enumerates the executable mutation verbs. | prefix: `Since 1.5.0 (subordinate ruling 10, item 1, conditional): ` | operations and target_kinds are vocabularies each implementation declares for itself at capabilities().audit_query.operations / .target_kinds -- the sets of values the operation and target_kind fields …[snip]… apability_status.defined.atomic_mutation.operations, which enumerates the executable mutation verbs. | strip-prefix |
| 7 | `capability_status.defined.atomic_mutation` | test_contract.py:188 (test_contract_1_3_0_prose_pins @L171) via path expr | Single-entity atomic mutation batches. A capability entry's own operations list names the mutation vocabulary the batch execution surface executes -- not a batch-specific subset distinct from single-o …[snip]… will not find operations declared there; it discovers the key by reading a real capability document. | insert: ` (CCR_DISPOSITION.md subordinate ruling 8-F)` | Single-entity atomic mutation batches. A capability entry's own operations list names the mutation vocabulary the batch execution surface executes -- not a batch-specific subset distinct from single-o …[snip]… will not find operations declared there; it discovers the key by reading a real capability document. | strip-insert |
| 8 | `control_endpoints.audit_query.semantics` | none found | Added in 1.4.0 (subordinate ruling 9, item 7): this is audit_query's canonical location, moved here from endpoints.audit_query because its only real authority (control or audit) and its only real host …[snip]… ) -- see control_plane.provision and versioning.version_binding's 1.4.0 conditional-obligation list. | insert: ` (subordinate ruling 9, item 7)` | Added in 1.4.0: this is audit_query's canonical location, moved here from endpoints.audit_query because its only real authority (control or audit) and its only real host (the control surface, per cont …[snip]… ) -- see control_plane.provision and versioning.version_binding's 1.4.0 conditional-obligation list. | strip-insert |
| 9 | `control_endpoints.revoke_credential.semantics` | none found | Terminal. A revoked credential can never be made valid again; enable does not apply. Revoking the last remaining active control credential is permitted but requires a valid confirmation per the destru …[snip]… act 1.2.0 (previously a pending contract decision, the destructive-confirmation semantics question). | **【監督裁定で追加剥離 (§5 U-6 (b)、v1.1)】** 草案 = insert: ` (previously a pending contract decision, the destructive-confirmation semantics question)` → **確定 = 末尾文全体を挿入句として剥がす**: `Resolved in contract 1.2.0 (previously a pending contract decision, the destructive-confirmation semantics question).` | **確定後**: Terminal. A revoked credential can never be made valid again; enable does not apply. Revoking the last remaining active control credential is permitted but requires a valid confirmation per the destru …[snip]…  credential that is not the last active one -- requires no confirmation. (末尾の `Resolved in contract 1.2.0.` を残さない) | strip-insert (**監督裁定で範囲を拡大**) |
| 10 | `control_plane.authority` | test_contract.py:193 (test_contract_1_3_0_prose_pins @L171) via path expr; test_contract.py:264 (test_audit_role_is_accepted_on_audit_query @L258) via path expr | Application credentials fail closed on every control endpoint; control credentials are rejected on data/schema endpoints. An audit credential is accepted only on the read-only control_capabilities, li …[snip]… dinate ruling 9) audit_query endpoints; every other control endpoint fails it closed with FORBIDDEN. | insert: ` (since 1.4.0, subordinate ruling 9)` | Application credentials fail closed on every control endpoint; control credentials are rejected on data/schema endpoints. An audit credential is accepted only on the read-only control_capabilities, li …[snip]… credentials, and audit_query endpoints; every other control endpoint fails it closed with FORBIDDEN. | strip-insert |
| 11 | `definitions.EntityDescriptor.properties.field_types.description` | PIN_1_6_0_ITEM_3_FIELD_TYPES (pinned constant; used at lines 554, 674) | Since 1.6.0 (subordinate ruling 11, item 3, conditional on application_catalog being provided -- versioning.version_binding): The field-type vocabulary gains a seventh member, json, meaning any JSON v …[snip]…  is silently ignored. add_field continues to carry a single field_type for the single field it adds. | prefix: `Since 1.6.0 (subordinate ruling 11, item 3, conditional on application_catalog being provided -- versioning.version_binding): ` | The field-type vocabulary gains a seventh member, json, meaning any JSON value. A field created without a declared type has type json -- this names an existing default rather than introducing a new on …[snip]…  is silently ignored. add_field continues to carry a single field_type for the single field it adds. | strip-prefix |
| 12 | `definitions.Mutation.properties.values.description` | none found | Deliberately left open (subordinate ruling 7(A)): the field-name vocabulary is entity-defined, not fixed by this contract, so an additionalProperties: false closure here would be meaningless -- there is no fixed key set to close against. | insert: ` (subordinate ruling 7(A))` | Deliberately left open: the field-name vocabulary is entity-defined, not fixed by this contract, so an additionalProperties: false closure here would be meaningless -- there is no fixed key set to close against. | strip-insert |
| 13 | `definitions.ScopedMutation.properties.values.description` | none found | Deliberately left open (subordinate ruling 7(A)): the field-name vocabulary is entity-defined, not fixed by this contract, so an additionalProperties: false closure here would be meaningless -- there is no fixed key set to close against. | insert: ` (subordinate ruling 7(A))` | Deliberately left open: the field-name vocabulary is entity-defined, not fixed by this contract, so an additionalProperties: false closure here would be meaningless -- there is no fixed key set to close against. | strip-insert |
| 14 | `destructive_confirmation.phrase_construction.rules[3]` | none found | State-fingerprinted for re-creatable targets: a target identifiable by a name that can be destroyed and later recreated (e.g. an entity or index) includes a state fingerprint in its phrase, so that ei …[snip]… he identical structure under the same name after a drop does not resurrect an old phrase's validity. | (none — unstripped) | State-fingerprinted for re-creatable targets: a target identifiable by a name that can be destroyed and later recreated (e.g. an entity or index) includes a state fingerprint in its phrase, so that ei …[snip]… he identical structure under the same name after a drop does not resurrect an old phrase's validity. | unstripped (no 'Since 1.x.0 (...)' clause at the value's start, and no balanced (...) group anywhere in the value contains a provenance-marker trigger substring -- the scan…) |
| 15 | `destructive_confirmation.resolved_in` | none found | 1.2.0. Defines the declare-and-echo confirmation semantics for every destructive operation in this contract, common across data, schema, and control-plane surfaces (CCR_DISPOSITION.md subordinate ruling 6). | insert: ` (CCR_DISPOSITION.md subordinate ruling 6)` | 1.2.0. Defines the declare-and-echo confirmation semantics for every destructive operation in this contract, common across data, schema, and control-plane surfaces. | strip-insert |
| 16 | `endpoints.audit_query.deprecation_note` | none found | Since 1.4.0 (subordinate ruling 9, item 7): this entry's path is retained as an alias of control_endpoints.audit_query for one further minor version after 1.4.0, resolving to the identical operation o …[snip]… est/response shape, specifically so a pre-1.4.0-shaped client is not broken by the reclassification. | prefix: `Since 1.4.0 (subordinate ruling 9, item 7): ` | this entry's path is retained as an alias of control_endpoints.audit_query for one further minor version after 1.4.0, resolving to the identical operation on the control surface's own host, not this s …[snip]… est/response shape, specifically so a pre-1.4.0-shaped client is not broken by the reclassification. | strip-prefix |
| 17 | `limits.audit_requests_per_minute_note` | test_contract.py:314 (test_audit_requests_per_minute_is_a_declared_limit_class @L306) via path expr | Since 1.4.0 (subordinate ruling 9, item 8, conditional on audit_query being provided -- versioning.version_binding). A pre-authentication fixed window governing the audit_query endpoint specifically ( …[snip]… t exhaust the same window a break-glass control-plane operation (e.g. revoke_credential) depends on. | prefix: `Since 1.4.0 (subordinate ruling 9, item 8, conditional on audit_query being provided -- versioning.version_binding). ` | A pre-authentication fixed window governing the audit_query endpoint specifically (both its canonical and alias paths, control_endpoints.audit_query/endpoints.audit_query.deprecation_note), separate f …[snip]… t exhaust the same window a break-glass control-plane operation (e.g. revoke_credential) depends on. | strip-prefix |
| 18 | `schemas.AuditResult.properties.events.items.description` | none found | Deliberately left open (subordinate ruling 7(A)): audit.fields is itself an open-ended, additive vocabulary, and a per-event shape is not one of the 11 response schemas or nested row schemas this ruling closes. | **監督裁定 S-d で追加剥離 + 語改訂 (v1.2)**: prefix: `Deliberately left open (subordinate ruling 7(A)): ` / rewrite: `this ruling closes` → `this contract closes` (草案は insert: ` (subordinate ruling 7(A))` のみ) | **確定後**: audit.fields is itself an open-ended, additive vocabulary, and a per-event shape is not one of the 11 response schemas or nested row schemas this contract closes. | **strip-prefix + rewrite** (草案は strip-insert)。**理由: 挿入句だけを剥がすと規範文の中に裸の `ruling` が残り、D-9 の新規 assert (剥離後スキャナ 0 ヒット) が赤になる。剥がした挿入句への後方参照 `this ruling` が宙に浮くので、参照先を契約自身に付け替える。この値は PIN を持たないので確定文言の破棄には当たらない。先頭の `audit.fields` は小文字の識別子なので大文字化しない。** |
| 19 | `schemas.CapabilityDocument.description` | none found | The envelope itself is closed (additionalProperties: false at this level), but capabilities/limits/limit_enforcement below and each capability entry's own value schema deliberately keep additionalProp …[snip]… ht comparable to the closed response envelopes elsewhere in this contract (subordinate ruling 7(A)). | insert: ` (subordinate ruling 7(A))` | The envelope itself is closed (additionalProperties: false at this level), but capabilities/limits/limit_enforcement below and each capability entry's own value schema deliberately keep additionalProp …[snip]…  mechanism, not an oversight comparable to the closed response envelopes elsewhere in this contract. | strip-insert |
| 20 | `schemas.CapabilityDocument.properties.surfaces.description` | PIN_1_6_0_ITEM_2_SURFACES (pinned constant; used at lines 551, 631) | Since 1.6.0 (subordinate ruling 11, item 2; unconditional -- versioning.version_binding): surfaces names the absolute base URLs at which this deployment's own surfaces are reached, as declared by the  …[snip]… cuments disagree is non-conformant, and a client is given no rule for preferring one over the other. | prefix: `Since 1.6.0 (subordinate ruling 11, item 2; unconditional -- versioning.version_binding): ` | surfaces names the absolute base URLs at which this deployment's own surfaces are reached, as declared by the deployer -- never derived, and never to be inferred by a client from the URL it happened t …[snip]… cuments disagree is non-conformant, and a client is given no rule for preferring one over the other. | strip-prefix |
| 21 | `schemas.CredentialIssued.properties.secret.description` | test_contract.py:609 (test_contract_pins_the_requester_finalized_1_6_0_prose @L596) via path expr; PIN_1_6_0_ITEM_1_SECRET_IS_BEARER (pinned constant; used at lines 548, 606) | Since 1.6.0 (subordinate ruling 11, item 1; unconditional -- versioning.version_binding): CredentialIssued.secret -- and the secret a rotate response returns, wherever this contract defines one -- is  …[snip]… ay depend on it. The service still stores only a verifier/digest and never returns the secret again. | prefix: `Since 1.6.0 (subordinate ruling 11, item 1; unconditional -- versioning.version_binding): ` | CredentialIssued.secret -- and the secret a rotate response returns, wherever this contract defines one -- is the complete bearer token for the surface that credential is for: a client presents that e …[snip]… ay depend on it. The service still stores only a verifier/digest and never returns the secret again. | strip-prefix |
| 22 | `schemas.CredentialRotated.properties.secret.description` | test_contract.py:610 (test_contract_pins_the_requester_finalized_1_6_0_prose @L596) via path expr; PIN_1_6_0_ITEM_1_SECRET_IS_BEARER (pinned constant; used at lines 548, 606) | Since 1.6.0 (subordinate ruling 11, item 1; unconditional -- versioning.version_binding): CredentialIssued.secret -- and the secret a rotate response returns, wherever this contract defines one -- is  …[snip]… ay depend on it. The service still stores only a verifier/digest and never returns the secret again. | prefix: `Since 1.6.0 (subordinate ruling 11, item 1; unconditional -- versioning.version_binding): ` | CredentialIssued.secret -- and the secret a rotate response returns, wherever this contract defines one -- is the complete bearer token for the surface that credential is for: a client presents that e …[snip]… ay depend on it. The service still stores only a verifier/digest and never returns the secret again. | strip-prefix |
| 23 | `schemas.MutationResult.properties.assigned_addresses.items.properties.address.description` | none found | Deliberately left open (subordinate ruling 7(A)): the address field-name vocabulary is entity-defined (EntityDescriptor.address_fields), not fixed by this contract. | insert: ` (subordinate ruling 7(A))` | Deliberately left open: the address field-name vocabulary is entity-defined (EntityDescriptor.address_fields), not fixed by this contract. | strip-insert |
| 24 | `schemas.SchemaOperationRequest.properties.field_types.description` | PIN_1_6_0_ITEM_3_FIELD_TYPES (pinned constant; used at lines 554, 674) | Since 1.6.0 (subordinate ruling 11, item 3, conditional on schema_operations being provided -- versioning.version_binding): The field-type vocabulary gains a seventh member, json, meaning any JSON val …[snip]…  is silently ignored. add_field continues to carry a single field_type for the single field it adds. | prefix: `Since 1.6.0 (subordinate ruling 11, item 3, conditional on schema_operations being provided -- versioning.version_binding): ` | The field-type vocabulary gains a seventh member, json, meaning any JSON value. A field created without a declared type has type json -- this names an existing default rather than introducing a new on …[snip]…  is silently ignored. add_field continues to carry a single field_type for the single field it adds. | strip-prefix |
| 25 | `security.schemes.application_credential.description` | test_contract.py:607 (test_contract_pins_the_requester_finalized_1_6_0_prose @L596) via path expr; PIN_1_6_0_ITEM_1_SECRET_IS_BEARER (pinned constant; used at lines 548, 606) | Opaque credential presented over TLS. The service stores only a verifier/digest and never returns the secret. Since 1.6.0 (subordinate ruling 11, item 1; unconditional -- versioning.version_binding):  …[snip]… ay depend on it. The service still stores only a verifier/digest and never returns the secret again. | **【監督裁定で追加剥離 (§5 U-6 (a)、v1.1)】** 草案 = insert: ` (subordinate ruling 11, item 1; unconditional -- versioning.version_binding)` → **確定 = 挿入句全体 (「Since 1.6.0」を含む) を剥がす**: `Since 1.6.0 (subordinate ruling 11, item 1; unconditional -- versioning.version_binding): ` | **確定後**: Opaque credential presented over TLS. The service stores only a verifier/digest and never returns the secret. CredentialIssued.secret -- and the secret a rotate response returns, wherever …[snip]… ay depend on it. The service still stores only a verifier/digest and never returns the secret again. (`Since 1.6.0: ` を残さない) | strip-insert (**監督裁定で範囲を拡大**) |
| 26 | `security.schemes.control_credential.description` | test_contract.py:608 (test_contract_pins_the_requester_finalized_1_6_0_prose @L596) via path expr; PIN_1_6_0_ITEM_1_SECRET_IS_BEARER (pinned constant; used at lines 548, 606) | A separately authenticated Control/Audit authority; application credentials are not accepted. The service stores only a verifier/digest; the secret is returned exactly once, at issue or rotate time. A …[snip]… ay depend on it. The service still stores only a verifier/digest and never returns the secret again. | **【監督裁定で追加剥離 (§5 U-6 (a)、v1.1)】** 草案 = insert: ` (subordinate ruling 11, item 1; unconditional -- versioning.version_binding)` → **確定 = 挿入句全体 (「Since 1.6.0」を含む) を剥がす**: `Since 1.6.0 (subordinate ruling 11, item 1; unconditional -- versioning.version_binding): ` | **確定後**: A separately authenticated Control/Audit authority; application credentials are not accepted. The service stores only a verifier/digest; the secret is returned exactly once, at issue or rotate time. A …[snip]… ay depend on it. The service still stores only a verifier/digest and never returns the secret again. (`Since 1.6.0: ` を残さない) | strip-insert (**監督裁定で範囲を拡大**) |
| 27 | `structured_operations.reserved_entity_names_note` | test_contract.py:277 (test_audit_events_is_a_documented_reserved_name @L271) via path expr | Since 1.4.0 (subordinate ruling 9, item 6; unconditional -- versioning.version_binding). audit_events is reserved across implementations as an entity/collection name, for platform-managed audit storag …[snip]… is additive: a future implementation-shared reserved name may be appended without removing this one. | prefix: `Since 1.4.0 (subordinate ruling 9, item 6; unconditional -- versioning.version_binding). ` | audit_events is reserved across implementations as an entity/collection name, for platform-managed audit storage an implementation may keep alongside application-declared entities in the same underlyi …[snip]… is additive: a future implementation-shared reserved name may be appended without removing this one. | strip-prefix |
| 28 | `versioning.compatibility` | none found | Additive fields and capabilities are allowed; removal or semantic change requires a new major version. The control surface follows the same compatibility rules. A response or request schema closure (a …[snip]… ation of shape rather than removing a previously-required capability or altering accepted semantics. | (none — unstripped) | Additive fields and capabilities are allowed; removal or semantic change requires a new major version. The control surface follows the same compatibility rules. A response or request schema closure (a …[snip]… ation of shape rather than removing a previously-required capability or altering accepted semantics. | unstripped (no 'Since 1.x.0 (...)' clause at the value's start, and no balanced (...) group anywhere in the value contains a provenance-marker trigger substring -- the scan…) |
| 29 | `versioning.version_binding` | test_contract.py:330, :360, :493, :689 via path expr; PIN_1_4_0_OBLIGATION_B_ADDENDUM; PIN_1_5_0_SENTENCE_1/2/3; PIN_1_6_0_VERSION_BINDING_PARAGRAPH; PIN_1_6_0_RETROACTIVE_DENIAL_ROW_1_1_0/1_2_0/1_3_0/1_4_0 (pinned constants) | An implementation's own declared contract_version is the general rule for which version's definitions it is claiming conformance to: only an implementation declaring 1.2.0 or higher claims conformance …[snip]… nding behavior exists, or shipping the behavior while the declaration lags, are both non-conformant. | (none — unstripped) | An implementation's own declared contract_version is the general rule for which version's definitions it is claiming conformance to: only an implementation declaring 1.2.0 or higher claims conformance …[snip]… nding behavior exists, or shipping the behavior while the declaration lags, are both non-conformant. | unstripped (value is 10269 chars and is a single cumulative narrative: it restates obligations version-by-version, and later sentences depend on earlier ones IN THE SAME VA…) |

---

#### Full reasons for `unstripped` and combo classifications

##### `audit.query_event_fields_note` — strip-prefix+strip-insert

(no additional reason recorded)

##### `destructive_confirmation.phrase_construction.rules[3]` — unstripped

no 'Since 1.x.0 (...)' clause at the value's start, and no balanced (...) group anywhere in the value contains a provenance-marker trigger substring -- the scanner's match here is a bare keyword (see matched-patterns) sitting inside ordinary normative prose with no bracketed/prefixed marker clause to separate out. spec/CONTRACT_HISTORY.md's own note for this path (where present) says the same thing.

##### `versioning.compatibility` — unstripped

no 'Since 1.x.0 (...)' clause at the value's start, and no balanced (...) group anywhere in the value contains a provenance-marker trigger substring -- the scanner's match here is a bare keyword (see matched-patterns) sitting inside ordinary normative prose with no bracketed/prefixed marker clause to separate out. spec/CONTRACT_HISTORY.md's own note for this path (where present) says the same thing.

##### `versioning.version_binding` — unstripped

value is 10269 chars and is a single cumulative narrative: it restates obligations version-by-version, and later sentences depend on earlier ones IN THE SAME VALUE (e.g. the 1.5.0 paragraph's sentence 4 says 'the same superset relation holds for event_classes, stated here explicitly', referring back across the value; the 1.6.0 paragraph's retroactive-denial rows extend four EARLIER sentences already inside this same value). The generic Rule A/B algorithm used on the other 28 values would find 8 separate bracketed provenance-marker parentheticals scattered through it plus at least one embedded 'Since 1.5.0 (...): ' clause reused verbatim from audit.query_operation_vocabulary -- fragmenting it into that many discrete extraction points is not a single mechanical prefix/insert split, it is a re-authoring of the paragraph's own cross-references, which is out of scope for a before/after inventory. Named explicitly in the task as the unstrippable example.


---

#### Test-pinned (18) breakdown by classification

- strip-insert: 4
- strip-prefix: 12
- strip-prefix+strip-insert: 1
- unstripped: 1
- total test-pinned: 18 (Appendix A.2c states 18)

---

#### Overall classification totals

- strip-insert: 12
- strip-prefix: 13
- strip-prefix+strip-insert: 1
- unstripped: 3
- total: 29

**逐語転記 (ここまで)**
