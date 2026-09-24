# フェーズ11 実施設計: 最低共通機能プロファイル (R-29 / R-23 / R-16)

- 版数: **v1.1 (2026-09-24)**。**改版履歴**:
  - **v0.1 (2026-09-24)** — 起草初稿。監督が確定した枠 (2026-09-24) を展開した版であり、**設計レビュー 1 回目の対象となる版**である。契約を触るので設計レビューは 2 回である (計画文書 §9 の 3)。
  - **v0.2 (2026-09-24)** — **設計レビュー 1 の反映。既存の決定・裁定・却下は撤回していない。** 設計レビュー 1 の 11 件の指摘に対する**監督裁定を §13 に逐語で置き**、裁定が本文の反映を命じた箇所 (D-1 / D-2 / D-5 / D-6 / X-1 / 新設 X-6 / §6.1 / §6.2 / §6.3 / §6.4 / §6.5 / §7 / §8.1 / §8.2 / §9 / §11 / §12 の裁定 3) を書き換えた。**書き換えた行には v0.2 の註と日付と根拠を残し、v0.1 の判定を消していない** (`docs/work-orders/OPERATING_CONDITIONS.md` §1.8 の 56)。**§12 (v0.1 の起草時疑義と監督裁定) はそのまま残す。** **§5 の U-1〜U-5 は両論のままであり、【裁定】欄は空である。** 本版が**設計レビュー 2 回目の対象**である。
  - **v0.3 (2026-09-24)** — **設計レビュー 2 の反映。既存の決定・裁定・却下は撤回していない。** 設計レビュー 2 の 12 件 + 回答項の指摘に対する**監督裁定を §14 に逐語で置き**、裁定が本文の反映を命じた箇所 (D-2 / 新設 X-7 / §5 U-4 / §6.1 / §6.2 / §6.4 / §6.5 / 新設 §6.6 / §7 / §7.1 / §8.3 / §10 / §11 / §13.1 の裁定 3・6) を書き換えた。**書き換えた行には v0.3 の註と日付と根拠を残し、v0.1 / v0.2 の判定を消していない** (`docs/work-orders/OPERATING_CONDITIONS.md` §1.8 の 56)。**§12・§13 (v0.1 / v0.2 の裁定) はそのまま残す。** **§5 の U-1〜U-5 は両論のままであり、【裁定】欄は空である。** 設計レビューは 2 回で終わりである (計画文書 §9 の 3)。
  - **v1.0 (2026-09-24)** — **確定版。** **依頼者裁定 (2026-09-24) を §5 の【裁定】欄に逐語で写した** (`docs/work-orders/OPERATING_CONDITIONS.md` §1.5 の 35。言い換えていない)。**§6 の (α)/(β) の書き分けを (α) に確定した** (U-1 / U-4 = (α))。**(β) の文案と分岐文は §5 U-1 / U-4 の表と §6.3 の記録として残し、1 行も消していない** (同 §1.8 の 56)。**§15「v0.3 の疑義と監督裁定」・§16「起票する項目」・§17「実施記録」を新設した。** **§12・§13・§13.1・§14 (v0.1〜v0.3 の裁定) はそのまま残す。** **決定 (D-1〜D-8) と却下 (X-1〜X-7) は 1 件も撤回していない。**
  - **v1.1 (2026-09-24)** — **WP-1 コードレビューの差し戻し反映 (訂正註のみ、決定は 1 件も撤回していない)。** WP-1 実測により §6.4 (:708) と §6.6 (:791)、§15 表の 3・4 (:998、:999) に**【v1.1 訂正】** の 1 文をそれぞれ追記した (`docs/work-orders/OPERATING_CONDITIONS.md` §1.8 の 56。行は消していない)。内容は作業指示書 §7.1 訂正註 2・3 と同一: (1) `conformance-tests/test_conditions_register.py` の参照解決検査は backtick 付きの未作成ファイル名を `file not found`、backtick 無しを naked token で赤にするため、declared 期の Evidence 欄にはファイル名を書かない。(2) 従属判断 7(A) の closed 列挙を読む機械検査は存在せず、完了条件 8 は監査照合に読み替える。
- 位置づけ: 計画文書 `docs/design/ROADMAP_POST_PHASE7_V1.md` (以下 **計画文書**) の **§5 フェーズ11 節**・**§4** (P-1〜P-9)・**§8 の R-29 / R-23 / R-16 行**が**正本**であり、本書 §1.1 / §1.2 / §2.1 はそれを**逐語で転記する** (再導出しない。計画文書 §9 の 1)。**§3 の D-1〜D-8 と §4 の X-1〜X-7 は監督確定である** (**v0.3 改訂**: v0.1 は X-1〜X-5、v0.2 が X-6、v0.3 が X-7 を足した。**却下した案は 1 件も撤回していない**)**。** **§5 の U-1〜U-5 は依頼者裁定待ちであり、両論のまま置く** — 各項の【裁定】欄は空で、裁定は逐語で記入して再審議しない (計画文書 §9 の 4)。WP 分割は §10 に見込みのみを置き、作業指示書 (`docs/work-orders/WORK_ORDER_PHASE11_MIN_COMMON_PROFILE_V1.md`) で確定する。 **v1.0 改訂 (2026-09-24)**: 本書は**監督が確定した枠の実施設計であり、§5 は依頼者裁定済みである** — 【裁定】欄は逐語で埋めてあり、再審議しない (計画文書 §9 の 4)。**WP 分割は作業指示書 `docs/work-orders/WORK_ORDER_PHASE11_MIN_COMMON_PROFILE_V1.md` で確定した** (§10 は見込みとして残す)。
- 対象台帳行: 計画文書 §8 の **R-29** (両 peer の最低共通機能プロファイル)、**R-23** (機械可読な派生物)、**R-16** (scenario 級 conformance) の 3 行を 1 つの設計文書で扱う。3 行を対で扱うことは計画文書 R-29 行・R-23 行・フェーズ10 設計 `docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md` §5 **U-13** の (1) が定めている。
- テーマ: **「どの peer でも、宣言を読んで分岐しなくても必ず完遂できる作業列」を固定し、その作業列を 1 本の scenario として通すこと。**
- 契約版と条件番号の書き方: 本書では **1.9.0 (仮。merge 時に確定)**、**C-28 (仮)** / **C-29 (仮)** と書く。並走中の項目 (keyset ページング) と版・番号が衝突しうるため、確定は merge 直前に main を読んで行う (§9)。
- 規模: **L** (計画文書 R-29 行・R-23 行・R-16 行の既存の規模宣言)。**変更クラス: C** (契約 JSON・`spec/`・`conformance-tests/`・両 peer の宣言値)、`security/CONTROL_MAPPING.md` に証拠行を足せば **D** (§3 D-8、計画文書 §9 の 8)。
- 応える G (計画文書 §0.1.1): **G-1** (周回の 4 段に両 peer で executable な共通条件があり緑であること) に C-28 (仮) で応え、**G-2 / G-3** (契約の現行版の性質が両 peer で conformance に固定されていること) に契約 1.9.0 (仮) と C-28 / C-29 (仮) で応える。G-2 / G-3 行の契約版と条件数は同じ変更セットで更新する (§3 D-7)。
- 設計原則 (依頼者、2026-09-02): 先送りしない / シンプル / 制約・制限で回避しない / 誇れる成果物。既定の重み付けは「最小変更」ではなく「長期に正しい形」。**決定軸は、堅牢で安全が第一、次に最大限の自由 (ガードレールでありゲートではない)** である (枠 §2)。
- 公開規律: 本書には実 credential・実ホスト名・実ドメイン・実 DSN・作業機の絶対パス・traceback を書かない。**file:line はすべて repo ルートからの相対パス**である。Mitate 側の正本は**別リポジトリ**の相対パスとして引く。

---

## 1. 問題設定と実需

### 1.1 計画文書 §5「フェーズ11 以降」節の転記

計画文書 §5 の当該節を以下に**転記する** (再導出しない)。

> ### フェーズ11 以降 — 実需駆動 (§3.2 の保留項目)
>
> 着手順は実需の記録順とし、本書では固定しない。ただし依存関係は次のとおり。
>
> - 非同期 job (CCR-09) → bulk ingest/export の chunk 原子性 → aggregation。
> - change feed は idempotency (R-5) と audit cursor の語彙を前提とする。
> - credential 委任 (CCR-11) は R-4 の認可 dry_run を前提とする。
> - 関係モデルは 2.0 級として独立審議。関係に依存する機能 (subgraph fetch、relationship-aware plan) はその後。
> - snapshot は control plane の application lifecycle としてのみ再考する。
> - **【追記 2026-09-23 (v1.108)】実需の突合 (§3.2 の実需の定義と突合表による。2026-09-23 時点)。** 上の依存関係は書き換えていない。どれから着手するかは依頼者の裁定事項であり、本追記は判断しない。
>   - 非同期 job (CCR-09): 実需なし (2026-09-23 時点)。
>   - bulk ingest/export の chunk 原子性: 部分的 (§3.2 突合表。batch 上限の実測はあるが、一括投入・export の要件は無い)。着手条件の充足は依頼者裁定。
>   - aggregation: 部分的 (同表。pushdown の trigger はあるが、Phase B 後の要求棚卸しは「要求もしない」と明記)。着手条件の充足は依頼者裁定。
>   - change feed: 部分的 (同表。既存語彙で自己完結し、cursor 語彙の整合が trigger として残るのみ)。着手条件の充足は依頼者裁定。
>   - credential 委任 (CCR-11): 実需なし (2026-09-23 時点)。
>   - 関係モデル: 実需なし (2026-09-23 時点。Mitate は汎用 join を non-goal と明記)。
>   - snapshot: 実需なし (2026-09-23 時点)。
>   - migration planner (II-6)・query explain (II-9)・索引の自動作成 (高速化案 8): 実需なし (2026-09-23 時点)。
>   - keyset ページング (高速化案 7): **着手条件充足** (Mitate `docs/work-orders/mitate-application-data-service-client-phase-b-requirements.md` §3 の 2・§12 (f)、2026-09-23)。
>   - R-36 ファイル/バイナリ: 部分的 (同表)。着手条件の充足は依頼者裁定。
>   - R-43 行・列セキュリティ: 部分的 (同表。(b) は R-43 行に記録済み)。着手条件の充足は依頼者裁定。
>   - R-29 最低共通機能プロファイル: **着手条件充足** (Mitate `docs/design/contract-v0.26.0-attributed-append-log.md` §7・§17、2026-09-23)。

### 1.2 計画文書 §8 の R-29 / R-23 / R-16 行の転記

**R-29 行** (計画文書 §8) を**逐語で転記する**。

> | **R-29** | **【追記 2026-09-23 (v1.105)】規模 L — 最低共通機能プロファイルは契約の決定 (Class C / D、設計レビュー 2 回)。** **両 peer の最低共通機能プロファイルが無い。** 宣言は現物どおり非対称である (r2db は `cross_entity_mutation` が `unavailable`、MitateDB は `row_addressability` と `revision_preconditions` が `unavailable`、`structured_query` と `atomic_mutation` は `partial`)。**契約義務としてではなく、conformance 条件「両 peer が必ず完遂できる作業列」として固定する形である** | **フェーズ11 の先頭**。**R-23** (機械可読な派生物) と対にし、「discovery → catalog → 要求作成 → 拒否の修正 → dry_run → 実行 → 再送」を 1 本のシナリオとして通す検査 (**R-16** の scenario 級 conformance と同じ周回) と同時に扱う。フェーズ10 設計 §5 **U-13** **【追記 2026-09-23 (v1.108)】着手条件充足 (Mitate `docs/design/contract-v0.26.0-attributed-append-log.md` §7・§17、2026-09-23。§3.2 突合表)。着手順は依頼者裁定。** |

**R-23 行** (計画文書 §8) を**逐語で転記する**。

> | **R-23** | **【追記 2026-09-23 (v1.105)】規模 L — 派生物の生成器と契約の対応の設計が要り、R-29 と対で扱う。** AI エージェント向けの不足。`spec/README.md` の目標「仕様・base URL・API key だけで利用」に対し、`OPERATION_CATALOG.json` は method / path / role / schema 名の索引であり、schema 本体・認証例・完全な要求例・server binding・標準 discovery URL を一体提供しない。`operation_catalog_url` は契約に optional として存在するが両 peer が宣言しない (L9-4) | **フェーズ11 以降 (実需駆動、§3.2)**。非正本の派生物 (OpenAPI / JSON Schema bundle / agent manifest / 具体例) を `tools/contract_catalog.py` と同じ「生成 + 再生成 byte 一致」方式で出す案。**OpenAPI を正本にしない判断 (`spec/README.md`) は変えない。** **L9-4 の解消は先行して可 (Class C)** | フェーズ11 以降 **【フェーズ10 の判断 2026-09-10】** **フェーズ11 のまま。** **フェーズ10 は触っていない。** **R-29 (最低共通機能プロファイル) と対で扱う。** **【追記 2026-09-23 (v1.106)】依頼者裁定 2026-09-23: 「着手条件: 運用開始後」の印は付けない — R-29 (印なし) と対で運用前に扱う。** |

**R-16 行** (計画文書 §8) を**逐語で転記する**。

> | **R-16** | **【追記 2026-09-23 (v1.105)】規模 L — scenario 級 conformance の新設は契約側 (Class C) で設計レビューを要する。** **起票候補**: P-2 の周回 (catalog を読む → 要求を作る → 判定を受ける → 安全に再送する) を両 peer で通す scenario 級 conformance。**フェーズ9 設計文書との重複確認を着手条件とする** — フェーズ9 が同じ周回の一部を既に条件化している可能性があり、着手前に突合する。本作業では設計しない **【追記 2026-09-08 (v1.5)。着手条件である「フェーズ9 設計文書との重複確認」の材料】** **フェーズ9 は P-2 の周回のうち「判定を受ける」と「安全に再送する」の 2 段を共通条件として条件化した** — **C-20 (宣言と挙動の一致) / C-21 (拒否が構造化診断を持つ) / C-22 (dry_run の判定が実呼びと一致し副作用 0) / C-23 (再送の意味) / C-24 (要求単位 budget) / C-25 (`request_id` による相関) の 6 条件である。** **R-16 が足すべきものは、この 6 条件が個別に見ている性質ではなく、「catalog を読む → 要求を作る → 判定を受ける → 安全に再送する」を 1 本の scenario として通したときに初めて見える不整合 (段と段の間の受け渡し) である。** | フェーズ10 以降 **【追記 2026-09-23 (v1.106)】依頼者裁定 2026-09-23: 「着手条件: 運用開始後」の印は付けない — scenario 級 conformance は契約側の証拠であり、運用開始後は両 peer の是正費用が上がる。運用前に扱う。** |

**着手条件の充足** (R-16): 上の R-16 行が求める「フェーズ9 設計文書との重複確認」は、同行の 2026-09-08 の追記 (C-20〜C-25 の 6 条件) と、本書 §1.4 の既存条件の対応 (探索で再実測) で満たしている。**C-28 (仮) はこの 6 条件を置き換えない** (§3 D-2)。

### 1.3 探索で確定した事実 (1) — 両 peer の宣言値 14 キー

契約 `capability_status.defined` が定義する capability は **14 キー**である (`spec/data-service-api.v1.json`:216-230 の範囲。実測: 同ファイルの `capability_status.defined` の要素数 14)。両 peer の現物の宣言は次のとおりで、**非対称である**。

| capability | r2db-api (`r2db-api/src/r2db_api/capabilities_document.py`) | MitateDB-api (`MitateDB-api/src/mitatedb_api/capabilities_document.py`) |
|---|---|---|
| `structured_query` | `enabled` (:50。operators 10 種) | **`partial`** (:80。`unsupported`: `contains` / `matches` / `is_null`) |
| `atomic_mutation` | `enabled` (:60。insert / update / upsert / delete) | **`partial`** (:81。operations は insert / update / delete、`unsupported`: `upsert`) |
| `application_catalog` | `enabled` (:61) | `enabled` (:86) |
| `schema_operations` | `partial` (:62。`unsupported`: `jobs`、operations は role 依存) | `partial` (:99。operations は developer のとき create_entity / add_field / alter_field、`unsupported`: create_index / drop_index / drop_entity / jobs) |
| `audit_query` | `unavailable` (:63。データ面の host) | `unavailable` (:100。同左) |
| `best_effort_transactions` | `unavailable` (:64) | `unavailable` (:101) |
| `idempotency` | `enabled` (:76) | `enabled` (:113) |
| `revision_preconditions` | `enabled` (:77) | **`unavailable`** (:114) |
| `row_addressability` | `enabled` (:78) | **`unavailable`** (:115) |
| `cross_entity_mutation` | **`unavailable`** (:81) | **`partial`** (:146。operations は insert / update / delete、`unsupported`: `upsert`) |
| `control_plane` | 配備側の注入値 (:84) | 配備側の注入値 (:156) |
| `constraint_declarations` | `enabled` (:89) | `enabled` (:174) |
| `dry_run` | `enabled` (:94) | `enabled` (:182) |
| `request_budget` | `enabled` (:101) | `enabled` (:190) |

**契約は「何が optional でないか」を定めていない。** `capability_status.rules` は「A capability must not be advertised as enabled unless its operations are executable.」「Optional target operations may be unavailable and must fail with CAPABILITY_UNSUPPORTED.」と述べるが (`spec/data-service-api.v1.json`:232-238)、**どの操作が optional でないか (= どの peer でも必ず実行される作業列) を定める節が無い。** したがってエージェントは、宣言を読んで分岐する以外に「どの peer でも通る手順」を持てない。これが R-29 の問題である。

**`partial` の読み方 (事実)**: 契約は `partial` を横断的に定義しておらず、`status_enum` の一員として現れるだけである (`spec/data-service-api.v1.json`:203-208、:1196 付近の `CapabilityDocument.capabilities` の `status.enum`)。`partial` のとき何が使えるかは、各 capability entry 自身の `operations` / `unsupported` サブキーが個別に開示する (entry は開いた形であり、`atomic_mutation` の定義文自身が「`operations` is a peer-published key within that open shape, not a fixed property of the closed envelope」と述べる)。**読解不能なのではなく、「契約は `partial` を一般定義せず、宣言側が個別に開示する」が正しい読みである。**

### 1.4 探索で確定した事実 (2) — 現物の交差、および既存条件の対応

**両 peer が今日「実行できる」と宣言している集合の交差** (上の表からの導出。§3 D-1 がこれを baseline として採る)。

| # | 操作 | r2db-api | MitateDB-api | 交差 |
|---|---|---|---|---|
| (a) | discovery (`GET /v1/capabilities`) | 無条件 | 無条件 | **入る** |
| (b) | catalog (`GET /v1/catalog`、`application_catalog`) | `enabled` | `enabled` | **入る** |
| (c) | schema (developer): `create_entity` / `add_field` (`field_constraints` の enum / nullable を含む) | `schema_operations` partial (両操作は `unsupported` でない)、`constraint_declarations` enabled | 同左 (developer のとき operations に両操作あり)、`constraint_declarations` enabled | **入る** |
| (d) | `insert` | `atomic_mutation` enabled | `atomic_mutation` partial (insert は `unsupported` でない) | **入る** |
| (e) | 述語 query: {eq, ne, lt, lte, gt, gte, in} + `order_by` + `page` | `structured_query` enabled (10 演算子) | `structured_query` partial (`contains` / `matches` / `is_null` のみ欠落) | **入る** (7 演算子。**v0.2 註 (2026-09-24、設計レビュー 1 指摘 1 の裁定)**: `page` のうち交差に入るのは **`size` のみ**である — `page.cursor` は MitateDB が `CAPABILITY_UNSUPPORTED` で拒否し (`MitateDB-api/src/mitatedb_api/http.py`:638-657)、`next_page` は常に `None` を返す (`MitateDB-api/src/mitatedb_api/cell.py`:3682-3689)。§3 D-1 (e) を参照) |
| (f) | 述語指定の `update` / `delete` (`delete` は declare-and-echo を含む) | enabled | partial (両操作は `unsupported` でない) | **入る** |
| (g) | `dry_run` と `plan` | `enabled` | `enabled` | **入る** |
| (h) | `idempotency_key` の記録と再送 | `enabled` | `enabled` | **入る** |
| (i) | `request_budget` | `enabled` | `enabled` | **入る** |
| (j) | `constraint_declarations` | `enabled` | `enabled` | **入る** |
| (k) | 成功結果の `request_id` | 1.8.0 宣言の無条件義務 | 同左 | **入る** |
| (l) | 拒否の構造化診断 (`field` / `violated_declaration`) | 1.8.0 宣言の無条件義務 | 同左 | **入る** |
| — | `contains` / `matches` / `is_null` | enabled | **不可** | 入らない |
| — | `upsert` | enabled (一意キー宣言 entity のみ) | **不可** | 入らない |
| — | `cross_entity_mutation` (`POST /v1/data/mutations`) | **`unavailable`** | partial | 入らない |
| — | `row_addressability` (mutation class・住所指定) | enabled | **`unavailable`** | 入らない |
| — | `revision_preconditions` (`expected_revision`) | enabled | **`unavailable`** | 入らない |
| — | データ面の `audit_query` | `unavailable` | `unavailable` | 入らない |
| — | `best_effort_transactions` | `unavailable` | `unavailable` | 入らない |
| — | `create_index` / `drop_index` / `drop_entity` / `jobs` | `jobs` のみ不可 | 4 種とも不可 | 入らない |

**既存条件の対応 (R-16 の重複確認の材料。`conformance-tests/CONDITIONS.md` の実測)**: 計画文書 §0.1.2 が周回の 4 段に条件を対応づけており (catalog を読む = C-11・C-12・C-17・C-19・C-20 / 要求を作る = C-03・C-21・C-22 / 判定を受ける = C-04・C-05・C-18・C-21・C-24 / 安全に再送する = C-07・C-23・C-25・C-27)、**4 段すべてに両 peer で executable な条件がある** (計画文書 §0.1.3 の G-1 行「充足」)。ただし **4 段を 1 本で通す scenario は無い** — C-22 (`conformance-tests/test_c22_dry_run_and_plan.py`) と C-23 (`conformance-tests/test_c23_idempotency_semantics.py`) は 1 テスト関数の中で 2 段を連鎖させるが、**拒否の診断を読んで同じ要求を直し、dry_run し、実行し、再送する**という受け渡しを 1 本で繋ぐものは、調査した範囲に存在しない。これが R-16 の問題である。

**拒否の診断が持つもの (事実)**: `VALIDATION_FAILED` の `details` は `violated_declaration` (必須) と `field` (必須。`/` 区切りの要求本体内の位置) を持ち (`spec/data-service-api.v1.json`:769-773)、`violated_declaration_vocabulary` は 11 語の閉じた語彙で、「**Every value a details key carries under this vocabulary is a statement of declared fact: never a row value, never a suggested value, never a corrective action, never SQL, and never an internal name**」と明記する (同 :783)。**したがって「どの位置が悪いか」は診断から機械的に読めるが、「何に直せばよいか」は診断に無く、catalog から採るほかない。**

### 1.5 探索で確定した事実 (3) — R-23 の現物

- 生成器 `tools/contract_catalog.py`: `build_catalog()` (:75-96) が `spec/data-service-api.v1.json` の `endpoints` / `control_endpoints` から 1 operation につき 9 フィールド (name / method / path / roles / requires_capability / atomicity / destructive / request_schema / response_schema) を投影し、`render()` (:99-100) が `indent=2` / `ensure_ascii=False` / `sort_keys=False` / 末尾改行で書き出す。`main()` (:103-119) は `--check` で再生成差分を判定する。
- 派生物 `spec/OPERATION_CATALOG.json`: 298 行、19 operation の索引。**schema 本体・要求例は持たない** (schema は名前で指すだけである)。
- 再生成一致テスト: `conformance-tests/test_operation_catalog_register.py`:120-128 (`build_catalog()` + `render()` の結果と on-disk の文字列一致)。
- `operation_catalog_url` の現行定義 (`spec/data-service-api.v1.json`:1270-1274、`CapabilityDocument` 内): 「Optional. The absolute URL at which this deployment publishes its own spec/OPERATION_CATALOG.json-shaped derived operation catalog, where it chooses to. Not required by any obligation this version introduces (D-8).」 — **両 peer とも宣言しない** (L9-4。`docs/design/PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md`:847、:1507)。
- `spec/README.md`:5-9 の目標 (逐語): 「The target is that an AI agent can use either implementation from: 1. this API specification, 2. a base URL, and 3. an authorized API key.」 これに対し **C-19 が実際に検査するのは、credential の逐語性・`surfaces` の宣言・型付き catalog の 3 点である** (`conformance-tests/CONDITIONS.md`:48)。

### 1.6 実需 (Mitate 正本からの逐語)

**逐語である。言い換えない。** 出所は別リポジトリ (Mitate) の正本であり、相対パスで指す。以下に引くのは R-29 に直接かかる 4 か所で、**残りは相対パスと行範囲で指す**。

**(1) `docs/design/contract-v0.26.0-attributed-append-log.md` §7-3 (§7 は行 137〜158)** の当該段落 (逐語):

> - **「Data Service が update / delete を拒否する形にする」は将来の強化であり、本版の保証ではない。** v1.1 は項目の collection を共通 API の mutation class **`append_only`** に対応付け、保存側の宣言として同じ形を持たせると書いた。**事実（実測、2026-09-17）**: `spec/data-service-api.v1.json` の `structured_operations.mutation_classes` は 4 クラス（`read_only` / `append_only` / `append_delete` / `mutable`）を語彙として持つが、**両 peer に実装が無い** —— `r2db-api` は `mutation_class` を `"mutable"` に固定して返し、`MitateDB-api` は `src` に `mutation_class` の実装を持たない。さらに本番 peer の MitateDB は `row_addressability: unavailable` を宣言しており、**spec の規則（row addressability が有効なとき entity ごとに 1 クラスを宣言する）そのものが成り立たない**。**ユーザー裁定（逐語）**: 「案aで、data-service-api側は後日実装にします。」 —— したがって本版は `append_only` への対応付けを保証として書かず、上記の構造保証で閉じる。`data-service-api` 側の実装は同 repository の台帳に **R-49** として起票済みであり（起票のみ）、**着手は同台帳 R-45 の後、依頼者の指示待ち**である。

**(2) 同文書 §17 (honest scope、行 1008〜1039) の当該項** (逐語):

> - **保存側は追記のみを強制しない（v1.2）。** 本版の「追記のみ」を守るのは、**契約に項目を変える操作が無いこと**と、**保存部の構造テスト**の 2 つだけである。共通 Data Service API の mutation class `append_only` は spec の語彙にあるだけで両 peer に実装が無く（本番 peer は `row_addressability: unavailable` で宣言自体が成り立たない）、**Data Service が update / delete を拒否する形は本版に存在しない**（将来の強化。data-service-api 台帳 R-49）。**「保存側が拒否するので安全である」とは書かない。** 構造テストが観測するのは本版の実装が発行する mutation であって、将来の実装や別経路からの書込ではない。

**(3) `docs/work-orders/mitate-application-data-service-client-phase-b-requirements.md` §3 (行 53〜68) の `solutionName` の行** (逐語):

> - solutionName の一意性は `row_addressability`/unique 制約が unavailable のため Data Service では守れない — read-before-write + 単一 instance 直列化で維持し、複数 instance 化の際に再判断 (C.7 と同じ条件)

**(4) 同文書 §12 の表 (行 156〜195) の (f)(g) 行** (逐語):

> | f | cursor 走査（MitateDB の `next_page` は常に null。成立時に指示書 §1 D4 の「ちょうど B 件も拒否」縮退を撤廃） | **未着手** — サーバ側 cursor 実装待ち |
> | g | `revision_preconditions`（§2.C.7。複数 instance 化の前提。DM-0025） | **未着手** — max-instances=1 の単一 instance 不変条件で運用中。複数 instance 化は別指示書 |

**残りの出所** (逐語は引かず、位置で指す): `docs/design/contract-v0.26.0-attributed-append-log.md` §7 全体 (行 137〜158) と §17 全体 (行 1008〜1039)、`docs/work-orders/mitate-application-data-service-client-phase-b-requirements.md` §3 全体 (行 53〜68) と §12 全体 (行 156〜195)。

**この実需の読み (枠 §1 の 4)**: 上の 4 点はいずれも **MitateDB の機能の床が低いこと**に由来する — `row_addressability` が `unavailable` なので mutation class の規則が成り立たず、一意性を Data Service では守れず、`revision_preconditions` が無い。**これらは「最低共通機能プロファイルを現物の交差で固定する」だけでは満たされない。** 満たすには MitateDB の機能の床を上げる別項目 (計画文書の **R-49** と、`row_addressability` / `revision_preconditions` の MitateDB 実装の新規起票) が要る。**床を上げるか否かは依頼者判断である** (§5 U-2)。本書の honest scope は §11 に置く。

### 1.7 非正本資料の但し書き

`docs/design/R23_AGENT_DERIVED_ARTIFACT_READINESS_20260913.md` は**着手前調査資料 (非正本) であり、未承認の提案である** — 本書は同資料 §2 の事実調査のみを (再照合のうえ) 引き、**§3〜§8 の提案・順序・具体例を継承しない** (計画文書 §8 の当該但し書き)。

---

## 2. 守るべき条件

### 2.1 計画文書 §4 の横断条件 (P-1〜P-9) の転記

計画文書 §4「横断の守るべき条件 (以後の全フェーズに適用)」を**逐語で転記する** (再導出しない)。

> | 記号 | 条件 | 根拠 |
> |---|---|---|
> | **P-1** | **1 要求 = 1 原子単位。往復をまたぐサーバ保持状態を持ち込まない。** plan・sandbox・resumable upload・保持 lock はすべてこれに当たる。無状態化 (決定的トークン、実行して rollback) で同じ目的を満たす | 契約 `transactions.interactive`、SI-08、両 peer の同型性 (状態は同型性を「持ち方」と「失効」の 2 回壊す) |
> | **P-2** | **エージェントの 1 周を閉じることを優先する**: catalog を読む → 要求を作る → 判定を受ける → 安全に再送する。この周回に欠けているものが最優先で、周回の外の機能は実需の実証を待つ | G-1、ai-agent 前提 |
> | **P-3** | **宣言は真であり、検査される。** 新しい宣言 (制約・能力・limit) は、宣言と実挙動の一致を共通条件として同時に追加する。advisory な宣言 (強制されない説明文) を catalog に載せない | C-05 / C-17、L6-6 |
> | **P-4** | **catalog と schema 操作は同じ版で動く。** 片方だけ先行させない | L6-6 |
> | **P-5** | **bound は安全上必要なものだけ。** 機能の問題を TTL・件数上限・除外リストで消さない。要求単位 budget は配備上限を下回る方向にのみ効く | 設計原則 3、SI-08 |
> | **P-6** | **peer 同型性を維持する。** 同名 helper は正規化 diff で固定し、コードは共有しない。platform 固有の実現 (PostgreSQL / SQLite / in-memory) が異なっても、契約上の意味は一致させる | peer-symmetry 規約 (2026-09-03) |
> | **P-7** | **契約はエージェントが読める長さと形を保つ。** 経緯文は companion へ、現行の意味だけを契約本体に置く。派生の機械可読 artifact は再生成一致テストで正本に縛る | G-1、R-8 / R-10 |
> | **P-8** | **各フェーズは性能の差分を記録する。** 基準値 (R-12) 確定後、完了ゲートに p50 / p95 の記録を添える。退行は初期は記録のみ、基準値が 2 フェーズ安定した後にゲート化を審議する | G-4 |
> | **P-9** | **クラウド製品・任意 SQL・自然言語クエリ・管理画面・ORM 互換は共通契約に入れない** | CLAUDE.md 境界、CCR-01、提案 II の同趣旨 |

### 2.2 本項目で効く条件 (枠 §2)

1. **P-2** (周回を閉じることが最優先)、**P-3** (宣言は真で検査される。**advisory な宣言を catalog に載せない**)、**P-6** (peer 同型性)、**P-7** (契約はエージェントが読める長さ。**派生物は再生成一致テストで正本に縛る**)、**P-9**。
2. **計画文書 §0.1.1 の G-2 / G-3 行を同じ変更セットで更新する** (契約版・条件数)。
3. **新条件は両 peer で executable かつ緑**である — `skip` / `xfail` を使わない (`docs/work-orders/OPERATING_CONDITIONS.md` §1.3 の 22・26)。
4. **新しい Security Invariant を足さない** (`CLAUDE.md`「Security Invariants are not a feature gate」)。新条件の SI 列は**既存 SI への対応**で書く (§8)。
5. **決定軸**: 堅牢で安全が第一、次に最大限の自由 (ガードレールでありゲートではない)。**最小変更ではなく長期に正しい形を採る。**
6. **並走 (keyset ページング、別チャット) と衝突させない**: scenario の paging は**現行方式** (`page.size` と `next_page`。MitateDB は `next_page` を常に `null` で返す) で書き、**結果集合を `page.size` 未満に保って** keyset 側の変更に依存させない。**契約版と C 番号は merge 直前に main を読んで振る** (先に merge した側が 1.9.0)。詳細は §9。

---

## 3. 決定と根拠

**本節の D-1〜D-8 は監督確定である** (枠 §3)。各 D は「決定 / 根拠 / 契約への影響 / conformance への影響 / Security Invariants との関係」の順に書く。**枠にない決定は足していない** — 未確定の選択肢は §5 に両論のまま置く。

### D-1 プロファイルの内容 = 現物の交差

#### 決定

**両 peer が今日「実行できる」と宣言している集合の交差を、最低共通機能プロファイル (以下 baseline) とする。** baseline は次の (a)〜(l) である。

| # | baseline に入るもの |
|---|---|
| (a) | discovery: `GET /v1/capabilities` (data plane) |
| (b) | catalog: `GET /v1/catalog` |
| (c) | schema (developer credential): `create_entity` と `add_field` (`field_constraints` の enum / nullable を含む) |
| (d) | `insert` |
| (e) | 述語 query: 演算子 {`eq`, `ne`, `lt`, `lte`, `gt`, `gte`, `in`} と `order_by`・**`page` の `size` のみ** — **v0.2 改訂 (2026-09-24、設計レビュー 1 指摘 1 の裁定 = 採用)**。v0.1 は「`order_by`・`page` (現行方式)」と書いていた。`page.cursor` は MitateDB が `CAPABILITY_UNSUPPORTED` で拒否するので (`MitateDB-api/src/mitatedb_api/http.py`:638-657)、`page` を丸ごと床に入れると **1.9.0 を宣言した当日から契約文が偽になる** (しかも C-28 の段は cursor を送らないのでテストは緑のまま = P-3 違反)。**床に入るのは `page.size` だけである** |
| (f) | 述語指定の `update` と `delete` (住所指定ではない。`delete` は C-06 の declare-and-echo を含む) |
| (g) | `dry_run` と `plan` |
| (h) | `idempotency_key` の記録と再送 (同 key 同 body → 原結果と同じ `request_id`、実行なし) |
| (i) | `request_budget` |
| (j) | `constraint_declarations` |
| (k) | 成功結果の `request_id` |
| (l) | 拒否の構造化診断 (C-21 の `field` / `violated_declaration`) |

**baseline に入れないもの** (いずれかの peer で `unavailable` / 不可): `contains` / `matches` / `is_null`、`upsert`、`cross_entity_mutation`、`row_addressability` (mutation class・住所)、`revision_preconditions`、データ面の `audit_query`、`best_effort_transactions`、`create_index` / `drop_index` / `drop_entity` / `jobs`、**`page.cursor` と、非 null の `next_page` が与える継続** (**v0.2 追加 (2026-09-24、設計レビュー 1 指摘 1 の裁定)**: peer は `next_page` に常に null を答えてよい)。**これらは従来どおり capability の宣言で分岐する** — baseline は「分岐しなくてよい下限」であって、分岐の禁止ではない。

**(k)(l) の契約文上の扱い (v0.2 註、2026-09-24、設計レビュー 1 指摘 5 の裁定 = 採用)**: **(k)(l) は baseline の構成要素のままである** (床の内容は 1 項目も変えていない)。ただし**契約本文 (§6.1) の `operations` 配列からは外し、`rule` の 1 文で受ける** — 契約 1.7.0 がすでに `request_id_on_every_successful_result` と `details_vocabulary_on_validation_identifier_and_capability_denials` を**無条件義務**として持っており (`spec/data-service-api.v1.json` の `versioning.obligations` の 1.7.0 entry)、同じ義務を契約の 2 か所に別の語で載せることは **P-7** に反する。

#### 根拠

- §1.3 / §1.4 の実測 (両 peer の `capabilities_document.py` の宣言値と、そこからの交差の導出)。
- **P-2**: 周回を閉じるために必要な操作はすべて交差の中にある (§1.4 の (a)〜(l) が周回の 4 段を覆う)。
- **決定軸「ガードレールでありゲートではない」** (`CLAUDE.md`「Security Invariants are not a feature gate」と同じ趣旨): baseline は**床**であり、天井ではない。baseline の外の capability を peer が持つことを妨げない。
- **床を上げる案 (交差そのものを広げる案) は本 D で採らない** — 依頼者判断である (§5 U-2)。

#### 契約への影響

baseline の一覧を契約本文に **1 節**として置く (§3 D-4、§6.1)。**capability document / catalog に新しい宣言キーは足さない** (§4 X-1)。

#### conformance への影響

baseline を 1 本で通す scenario 条件 **C-28 (仮)** を新設する (D-2)。既存条件は 1 件も置き換えない。

#### Security Invariants との関係

**新 SI を足さない。** baseline は「必ず実行できる操作の集合」であって新しい安全性質ではなく、各操作の安全性質は既存 SI (SI-05 / SI-08 / SI-09 / SI-10 / SI-11 / SI-14 / SI-15) がすでに持つ。§8 を参照。

### D-2 scenario 条件 (C-28 仮) = baseline を 1 本で通す作業列

#### 決定

**1 テスト関数が 1 adapter に対して次の 12 段を順に実行し、どの段も宣言分岐を持たない** — **どこかで `CAPABILITY_UNSUPPORTED` が返れば赤**とする。

1. capabilities を読み、契約版を読む。
2. developer で entity を作る (enum と `nullable: false` の field を含む)。
3. runtime で catalog を読む。
4. **catalog だけから要求を組み立てる。まず enum 外の値を持つ `insert` を送り**、`VALIDATION_FAILED` の `details.field` と `violated_declaration: enum` を受ける。
5. **診断だけを使って要求を直す** — `field` の位置の値を catalog の enum の要素に置き換える。**修正値は診断に無い** (`spec/data-service-api.v1.json`:783) ので **catalog から採る**。
6. 直した要求に、**段 (7) で使うのと同じ `idempotency_key` を付けて** `dry_run: true` で送り、`committed: false` と `affected` と `plan` を受ける。**v0.2 改訂 (2026-09-24、設計レビュー 1 指摘 7 の裁定 = 採用)**: v0.1 は key を付けずに dry_run していた。`plan` token は `plan` 自身と `dry_run` 以外の**全フィールド** (`idempotency_key` を明示的に含む) を digest するので (`spec/data-service-api.v1.json`:711)、key 無しの dry_run が返した `plan` を key 付きの実送信に提示すると**必ず不一致になる**。**dry run 上の `idempotency_key` は記録も照合もされない**と契約が明示しているので (同:710)、この順序は安全であり、契約が想定した使い方である。
7. **段 (6) が返した `plan` をそのまま提示して**、同じ要求に同じ `idempotency_key` を付けて実送信し、`committed: true` と `request_id` を受ける。**期待に「`plan` 不一致による `PRECONDITION_FAILED` / `violated_declaration: plan` が起きないこと」を含める。** **v0.2 改訂 (2026-09-24、同指摘 7 の裁定)**: v0.1 は `plan` を実送信に提示するかを書いていなかった — 提示しなければ dry_run → 実送信の継ぎ目が「`plan` を受け取って捨てるだけ」になり、**R-16 が見たい受け渡しがそこで空になる**。**`plan` の受け渡しが R-16 の継ぎ目である。** (**v0.3 註、設計レビュー 2 指摘 8 の裁定**: この句は本段の下の改訂で「鎖の 1 本」に弱めた。**段 (6) → 段 (7) で `plan` を提示するという決定自体は動かない。**)
8. 同 key 同 body で再送し、**同じ `request_id` が返り、行数が増えない**。
9. baseline の各演算子で query する (`order_by`・**`page.size`** 付き)。**要求に `budget` を付ける** — **受理されて行が返ることを床 (i) (`request_budget`) の観測とする。** **v0.3 改訂 (2026-09-24、設計レビュー 2 指摘 4 の裁定 = 採用)**: v0.2 は `result_items` を「**返る行数以上**の値で」とだけ書いていたが、**それでは MitateDB だけが `LIMIT_EXCEEDED` になる** — MitateDB は `result_items` を**要求された `limit` (= `page.size`) で判定し**、返った行数では判定しない (`MitateDB-api/src/mitatedb_api/cell.py`:2125-2129 のコメントと :2137)。r2db は `min(len(rows), page_size)` で判定する (`r2db-api/src/r2db_api/structured.py`:923、`r2db-api/src/r2db_api/postgres.py`:1377)。**したがって段 (9) は次の 1 つの不等式を満たす組み方に固定する**: **返る行数 R ≤ `page.size` S ≤ `budget.result_items` B ≤ この配備が宣言する `limits.result_items`**。**右端は capability document から読む — 固定リテラルを書かない** (C-24 が「配備の宣言値を超える `budget` は `VALIDATION_FAILED` で拒否し、決して黙って clamp しない」を固定しているため)。 **v0.2 改訂 (2026-09-24、設計レビュー 1 指摘 1・6 の裁定 = 採用)**: v0.1 は `page` を無限定に書き、かつ **`request_budget` を使う段を 1 つも持たなかった** (床の 1 項目が観測対象 0 件 = §1.5 の 32・40 の空振りと同じ形)。**budget を狭める意味 (narrowed bound での `LIMIT_EXCEEDED` / `limit_class`) は C-24 が単独で持つので、C-28 は C-24 と重複しない。**
10. 述語 `update`。
11. 述語 `delete` (declare-and-echo)。
12. 最終 query で状態を確認する。

**段間の受け渡し (R-16 が見たいもの) は「(4) の拒否 → (5) の修正 → (6) dry_run → (7) 実送信 → (8) 再送」が同一の要求体で繋がることである。** **そのうち (6) → (7) の継ぎ目は `plan` token そのものである** (v0.2 追加、設計レビュー 1 指摘 7 の裁定) — dry_run が返した token を実送信が提示して初めて、「同じ要求である」ことが段をまたいで load-bearing になる。

**v0.3 改訂 (2026-09-24、設計レビュー 2 指摘 8 の裁定 = 採用)**: v0.2 は「**`plan` の受け渡しが R-16 の継ぎ目である**」と書いたが、**その主張は実測より強い** — **C-22 が既に plan の有効性 (同じ plan を不変の schema に対して提示した実要求が通ること) を 4 plug で固定している** (`conformance-tests/CONDITIONS.md` の C-22 行)。**C-28 が足すのは、(4) の拒否 → (5) の診断による修正 → (6) dry_run → (7) 実送信 → (8) 再送を、(5) 以降 (8) まで同一の要求体が通り抜けることであり、`plan` はその鎖の 1 本である。** v0.2 の文は「`plan` が継ぎ目の全部である」と読めるので、本版でこの形に弱めた (**v0.2 の文は上に残している**)。 既存条件 (C-20 / C-21 / C-22 / C-23 / C-25) は各段を個別に見ており、**C-28 (仮) はそれらを置き換えない。**

**実現は既存の port で行う** — `conformance-tests/adapter.py` の `capability_document` (:1200)、`catalog_document` (:2229)、`create_entity_with_declared_types` (:2287) / `schema_operation_with_result` (:2333。`field_constraints` / `enum` / `nullable` を運ぶのはこちらである)、`attempt_mutation_with_result` (:2563。`dry_run` / `plan` / `budget` / `idempotency_key` / `destructive` / `confirmation` を 1 呼び出しの keyword に持つ)、`select_eq` (:2094。`limit` = `page.size`)、`attempt_filter` (:2113)。**port の追加が要るなら実装前に監督へ上げる** (`docs/work-orders/OPERATING_CONDITIONS.md` §1.5 の 37)。**起草時点で判明している port の不足は §7 の末尾に列挙する** (`order_by` を運ぶ port method が現状 1 つも無い、ほか)。

#### 根拠

- R-16 行の 2026-09-08 の追記: 「R-16 が足すべきものは … 1 本の scenario として通したときに初めて見える不整合 (段と段の間の受け渡し) である」(§1.2)。
- §1.4 の実測: 4 段を 1 本で通す scenario は現存しない。
- §1.4 の診断の事実: 修正値は診断に無く catalog から採るほかない — **段 (5) が「診断 + catalog だけで直せる」ことの検査そのものになる。**

#### 契約への影響

無し (条件は契約文を要求しない)。ただし **C-28 (仮) が固定するのは D-4 の契約義務の観測形**である。

#### conformance への影響

`conformance-tests/CONDITIONS.md` に C-28 行を足し (条件文・SI 列・検証方法・`executable` 欄は §6.4)、テストファイル (慣行どおり `conformance-tests/test_c28_*.py`、`@pytest.mark.condition("C-28")`) を足す。**registry.json の全 adapter (現在 6) で駆動する** — `conftest.py` の `adapter` fixture が全 adapter に parametrize する既存機構をそのまま使う。

#### Security Invariants との関係

**新 SI を足さない。** C-28 の SI 列は §8 のとおり既存 SI への対応で書く。

### D-3 R-16 は C-28 (仮) で閉じる

#### 決定

**R-16 のために別条件を起こさない。** 計画文書 §8 の **R-16 行は、R-29 の閉止と同じ変更セットで閉じる。**

#### 根拠

同じ周回を 2 本走らせても段間の受け渡しの証拠は増えない (§4 X-3)。R-16 行自身が「1 本の scenario として通したときに初めて見える不整合」を求めており、C-28 (仮) がそれである。

#### 契約への影響

無し。

#### conformance への影響

条件は 1 件 (C-28 仮) の追加に留まる。

#### Security Invariants との関係

無し (条件数の話である)。

### D-4 契約版 1.9.0 (仮) の obligation は baseline の実行義務

#### 決定

**「契約 1.9.0 を宣言する peer は、baseline の各操作を宣言するだけでなく実行する」**を 1.9.0 の義務とする。**これは §5 U-1 の (α) を採る形であり、U-1 は依頼者が確定する** — 本 D は (α) を前提に書いた実施形である。

- **契約本文には baseline の一覧を 1 節で置く** (**P-7**: 短く、経緯は companion へ)。
- **`version_binding` の 1.9.0 entry に unconditional obligation として結ぶ。**
- **catalog / capability document に新しい宣言キーは足さない** (**P-3**: baseline は宣言ではなく版の義務である)。

#### 根拠

- **P-7**: エージェントが読むのは契約であって `conformance-tests/` ではない。契約から baseline を読めなければ、エージェントは結局すべての宣言を読んで分岐するしかない。
- `capability_status.rules` の「Optional target operations may be unavailable」の **optional を初めて定義できる** — 現行の契約には「何が optional でないか」が無い (§1.3)。
- **P-3**: baseline を宣言キーにすると「宣言していない peer」という無意味な状態を作る (§4 X-1)。

#### 契約への影響

`spec/data-service-api.v1.json` に (1) baseline 節 1 つ、(2) `versioning.version_binding` の散文への 1.9.0 段落、(3) `versioning.obligations` への 1.9.0 entry を足す。**契約 JSON の 3 複製は同一コミットで同一バイトにする** (既存規律。`spec/data-service-api.v1.json`、`r2db-api/src/r2db_api/contract/data-service-api.v1.json`、`MitateDB-api/src/mitatedb_api/contract/data-service-api.v1.json`)。文案は §6.1 / §6.2。

#### conformance への影響

C-28 (仮) が 1.9.0 の無条件義務の観測形である。**版フリップの規律** (契約自身が持つ「A peer's version-flip … must land in the same commit as the real behavior change it claims」) により、**宣言と挙動は同一コミットである** (`docs/work-orders/OPERATING_CONDITIONS.md` §1.1 の 11)。`conformance-tests/test_contract.py`:95 の契約版の固定比較と、`MitateDB-api/tests/test_denial_details_and_request_id.py`:522 の宣言版の assert を同じ変更セットで更新する。

#### Security Invariants との関係

**新 SI を足さない。** 義務は「できると宣言したことを実際に実行する」であり、SI-05 / SI-15 の既存の性質 (検証された構造化操作、fail-closed な認可) を弱めない。

### D-5 R-23 の最小形 = `operation_catalog_url` の宣言と byte 一致の配布

#### 決定

**両 peer が `operation_catalog_url` を宣言し、その URL が、宣言する契約版の `spec/OPERATION_CATALOG.json` を byte 一致で返す。** これを新条件 **C-29 (仮)** とする。

- 形は **declare-first** とする — 宣言する peer に対して byte 一致を検査し、宣言しない peer は `unavailable` 相当の枝を通る。**ただし両 peer が同じ変更セットで宣言するので、分岐は空にならない** (両 peer とも肯定側を通る)。
- **配るバイト列の出所 (v0.2 改訂、2026-09-24、設計レビュー 1 指摘 3 の裁定 = (i) 採用)**: v0.1 は「**生成器 `tools/contract_catalog.py` と再生成一致テストは既存のまま**である (変更しない)」と書いていたが、**どちらの peer の package も派生カタログを同梱しておらず** (`r2db-api/src/r2db_api/contract/` と `MitateDB-api/src/mitatedb_api/contract/` にあるのは契約 JSON のみ)、**生成器は repo ルート決め打ちで、配備された package から使えない** (`tools/contract_catalog.py`:44 の `CATALOG_PATH`)。この決定のままでは WP-3 が着手できないので、次のとおり改める — **生成器の正本は `tools/contract_catalog.py` のままとし、配布物を 3 複製にする**: `spec/OPERATION_CATALOG.json` と、両 peer の `contract/OPERATION_CATALOG.json` を、**契約 JSON の 3 複製と同じ「同一コミットで同一バイト」規律**に載せる (`conformance-tests/test_contract.py`:361 の `test_contract_packaged_copies_are_byte_identical` が契約 JSON に対して持つ形)。あわせて **`conformance-tests/test_operation_catalog_register.py` の再生成一致テスト (:120) を 3 複製比較に拡張する** — これは **P-7「派生物は再生成一致テストで正本に縛る」**の形を、配布物まで延長したものである。**peer ごとに派生器を持たせる案は却下である** (§4 X-6)。
- **配る path の契約上の位置 (v0.2 追加、2026-09-24、設計レビュー 1 指摘 8 の裁定 = 一部採用)**: 派生カタログを配る path を、**契約 `endpoints` に operation `operation_catalog` として載せる** — **`method`: `GET`、`roles`: data surface の credential (`runtime` / `developer`)、`requires_capability`: なし**。**認証は `GET /v1/capabilities` と同じであり、無認証の面は作らない** (したがって SI-15 の面は立たず、SI-08 の既存の request-rate bound がそのまま掛かる。§8.2)。**これにより派生カタログは自己言及の 20 件目の operation を持つ** — その機械的帰結 (`conformance-tests/test_operation_catalog_register.py`:117 の「19 件 (7 + 12)」の assert と、`spec/OPERATION_CATALOG.json` の再生成) は **§6.5 で同じ変更セットに落とす**。**`operation_catalog_url` は「この配備でその operation に到達する絶対 URL」である** — **`surfaces.data.base_url` 配下であることは条件にしない** (契約に無い性質を条件に入れない。**CDN 等に置く配備はそこを宣言してよい**)。**v0.1 §12 の裁定 3 の (i) はこの制約を求めていたが、本裁定で外した。**
- **これが R-23 の WP の下限 (a) である** — 派生物の拡張 (b) と参照クライアント (c) は §5 U-3 の依頼者判断である。
- **`operation_catalog_url` を 1.9.0 の義務にするかは §5 U-4** であり、本 D はどちらでも成立する形 (宣言 + byte 一致) を定める。

#### 根拠

- **L9-4** (両 peer が `operation_catalog_url` を宣言しない) は計画文書 R-23 行が「解消は先行して可 (Class C)」と述べる。
- **P-7**: 派生物は再生成一致テストで正本に縛る — 既存の `test_operation_catalog_register.py`:120-128 がその形であり、**配る URL の byte 一致はその形を配備まで延長したものである。**
- **P-3**: 宣言 (`operation_catalog_url`) は真であり検査される。宣言だけ足して配らない形は advisory な宣言になる。

#### 契約への影響

`operation_catalog_url` の記述 (`spec/data-service-api.v1.json`:1270-1274) の改訂。文案は §6.3 に **U-4 の両案**を置く。

#### conformance への影響

`CONDITIONS.md` に C-29 行を足す (§6.4)。**開示事項 (v0.2 改訂、2026-09-24、設計レビュー 1 指摘 8 の裁定)**: 現在の port には「宣言された URL を取得する」method が無く、in-process plug には HTTP 面が無い。**形は裁定済みであり、二段である** — (i) **6 plug すべて**で、peer 自身がその operation に対して返す本文を **port method `operation_catalog_document()` (新設)** で取り、`tools/contract_catalog.py` の生成物と **byte 一致**することを見る。(ii) **`transport_kind == "socket"` の plug では、宣言された `operation_catalog_url` を実際に dial して同じ本文を得る** (非空: socket plug ≥ 1 を要求)。**in-process の 4 plug は URL 文字列が非 dial の合成 placeholder のままでよく、その旨を C-29 行の honest limits に開示する** (§6.4)。§7.1 に port の形を列挙する。

#### Security Invariants との関係

**新 SI を足さない。** 配る文書は契約の派生物であり、**配備固有の秘密を含まない** (`spec/OPERATION_CATALOG.json` は operation 索引のみである) — SI-10 (情報非開示) に対しては「新たに開示するものが無い」ことが根拠である (§8)。

### D-6 paging は現行方式

#### 決定

**scenario の paging は現行方式** (`page.size` と `next_page`) で書き、**結果集合を `page.size` 未満に保つ。**

**床に入るのは `page.size` だけである** (**v0.2 追加、2026-09-24、設計レビュー 1 指摘 1 の裁定 = 採用**) — `page.cursor` と、非 null の `next_page` が与える継続は **baseline の外**であり、契約文の `outside` に明記する (§6.1、D-1)。これにより keyset ページング並走との境界が、**scenario の側だけでなく契約文の側でも閉じる** (§9 の (iii))。

#### 根拠

並走 (keyset ページング) の変更に C-28 (仮) を依存させないため (枠 §2、§9)。MitateDB は `next_page` を常に `None` で返す (`MitateDB-api/src/mitatedb_api/cell.py`:3682-3689) ので、**`next_page` の値そのものを C-28 の判定材料にしない。**

#### 契約への影響

無し。

#### conformance への影響

段 (9) と段 (12) の期待は「返る件数と順序」であり、**頁送りの有無に依存しない。**

#### Security Invariants との関係

無し。

### D-7 番号と版は merge 直前に振る

#### 決定

**契約版 (1.9.0 仮) と条件番号 (C-28 / C-29 仮) は merge 直前に main を読んで振る** — **先に merge した側が 1.9.0 である。** 同じ変更セットで**計画文書 §0.1.1 の G-2 / G-3 行の契約版と条件数を更新する** (現在「1.8.0」「C-00〜C-27 の 28 件」→ 新版と 30 件)。

#### 根拠

並走する項目と版・番号が衝突する (枠 §2、§9)。G-2 / G-3 行は「契約版を上げる変更セットは同じ変更セットで本行の版を更新する」と自ら定めている (計画文書 §0.1.1)。

#### 契約への影響

版ラベルの確定タイミングのみ。

#### conformance への影響

`CONDITIONS.md` の行 ID と、条件数を数える記録 (計画文書 §0.1.1 / §0.1.3) の更新。

#### Security Invariants との関係

無し。

### D-8 変更クラス

#### 決定

**Class C** — 契約 JSON・`conformance-tests/`・両 peer の `capabilities_document` (宣言値) に触れる。**`security/CONTROL_MAPPING.md` に C-28 / C-29 の証拠行を足せば Class D** である (計画文書 §9 の 8。形式 3.0 の更新規約)。**本設計は D を前提に書き、依頼者裁定を逐語で残す欄を §5 U-5 に用意する。**

#### 根拠

計画文書 §9 の 8 の肯定列挙: 契約 JSON / `spec/` 配下 / `conformance-tests/` 配下 / catalog 宣言値 = C、`security/` 配下 = D、**1 つのコミットが複数クラスに触れるときは最も重いクラスを採る。** 宣言値に触れる変更は P-3 により最低 C である。

#### 契約への影響

無し (手続きの決定である)。

#### conformance への影響

Class D は「C の全部 + 依頼者裁定の逐語記録 + 版付きの security-contract 決定」を要求する。**着手前に `tools/change_class.py` を実行して実測の分類行を得る** (慣行)。

#### Security Invariants との関係

**新 SI を足さない。** `CONTROL_MAPPING.md` への追記は既存 SI の証拠欄への追加であり、SI の集合を変えない (§8)。

---

## 4. 却下した代替案

**本節の X-1〜X-7 は監督確定である** (枠 §4)。**X-6 は v0.2、X-7 は v0.3 の追加であり、X-1〜X-5 は v0.1 のまま撤回していない。**

### X-1 baseline を capability document の新キー (例 `baseline_profile`) として宣言させる — **却下**

**理由**: **P-3** (advisory な宣言を catalog に載せない)。**baseline は版の義務であって peer ごとの宣言ではない。** 宣言にすると「baseline を宣言していない peer」という**無意味な状態**を作る — その状態の peer が baseline を実行できるかどうかは、宣言からは何も言えない。宣言キーを足さない代わりに、版の義務として結ぶ (D-4)。

**v0.2 註 (2026-09-24、設計レビュー 1 指摘 5 の裁定)**: **契約本文に置く一覧は X-1 に当たらない。** X-1 が却下したのは **capability document への新しい宣言キー**であって、**契約側の一覧ではない** — したがって §6.1 の `common_baseline.capabilities` 配列 (床が触れる capability 8 名の列挙) は本却下の対象外である。

### X-2 scenario を宣言分岐つき (declare-first) で書く — **却下**

**理由**: **baseline の存在意義は「分岐なしに通る」ことである。** 分岐を許すと C-22 / C-23 の再掲になり (両者はすでに declare-first で書かれている。`conformance-tests/CONDITIONS.md`:51-52)、R-29 も R-16 も 1 ミリも進まない。C-28 (仮) は**どの段も宣言分岐を持たない** (D-2)。

### X-3 R-16 を独立条件 (別の C 番号) にする — **却下**

**理由**: **同じ周回を 2 本走らせるだけで、段間の受け渡しの証拠は増えない。** R-16 行が求めるのは「1 本の scenario として通したときに初めて見える不整合」であり、本数ではない (D-3)。

### X-4 baseline に `cross_entity_mutation` を入れる (r2db にエンドポイント実装を要求)

**却下ではなく、§5 U-2 の一部 (床を上げる案) として依頼者判断とする。** r2db-api は `cross_entity_mutation` を `unavailable` と宣言しており (`r2db-api/src/r2db_api/capabilities_document.py`:81)、baseline に入れるには r2db 側の実装が要る。**本書は交差 (D-1) を採り、床を上げるかどうかを U-2 に置く。**

### X-5 OpenAPI を正本にする — **却下**

**理由**: 計画文書 R-23 行の「**OpenAPI を正本にしない判断 (`spec/README.md`) は変えない**」のとおりである。`spec/README.md` は `data-service-api.v1.json` を「intentionally **not** an OpenAPI document」と述べる。**派生物として OpenAPI を出す案は U-3 (b) の範囲**であり、正本の置き換えではない。

### X-6 各 peer が自分の packaged 契約から派生カタログを毎回導出する (peer ごとの派生器) — **却下** (v0.2 追加、2026-09-24)

**理由** (設計レビュー 1 指摘 3 の裁定): **同名 helper が両 peer に増える** — コード共有は不可なので (依頼者決定 2026-09-03)、**P-6 の同型性テストの対象 (`_ISOMORPHIC_TARGETS`) が動く**。これに対し **P-7 の「派生物は再生成一致テストで正本に縛る」の方が単純である**: 配布物を 3 複製にして「同一コミットで同一バイト」規律に載せれば、**生成器の正本は 1 本 (`tools/contract_catalog.py`) のまま**でよい (D-5)。**本案は却下であり、D-5 の (i) を採る。**

### X-7 1.9.0 の段落に無条件義務の件数文を書き、`test_operation_catalog_register.py` の版集合 pin を広げる — **却下** (v0.3 追加、2026-09-24)

**理由** (設計レビュー 2 指摘 2 の裁定 = (a) 採用、(b) を本却下案に落としたもの): `conformance-tests/test_operation_catalog_register.py` の固定事項 (vi) は、「`N of those obligations are unconditional`」文を持つ版の集合が**ちょうど 3 件 {1.4.0, 1.6.0, 1.7.0}** であることを直接 assert する (:343-355)。**1.9.0 の段落に複数形の件数文を書けばこの assert は赤になり、pin を 4 版に広げる変更が同じ変更セットに要る。** さらに U-4 が (β) なら件数文は単数形になり、`_UNCONDITIONAL_COUNT_RE` (:278) は**複数形にしか当たらない**ので、正規表現を `is` / `are` 両形に広げる変更も要る。**これだけの変更を足して得られるのは「散文の件数と `obligations` 索引の件数の機械照合」を 1 版分広げることだけであり、広げる理由が無い** — **1.9.0 の義務は §6.2 (1) の (a)(b) の列挙そのものが述べ、`versioning.obligations` の entry がその索引である。** **本案は却下であり、§6.2 (1) は件数文を持たない** (裁定 2 の (a))。**pin (`len(prose_counts) == 3`) は触らない。**

---

## 5. 依頼者判断待ち (U-1〜U-5)

**本節の 5 項目は両論のまま置く。** **監督の推奨は「監督の推奨」として明示するが、本文をどちらかに寄せていない。** 裁定は【裁定】欄に**逐語で**記入し、再審議しない (計画文書 §9 の 4)。**裁定前は空欄である。** **v1.0 (2026-09-24)**: **5 項目とも依頼者裁定済みであり、【裁定】欄は逐語で埋めた** (監督保管の確定文ファイル `{scratchpad}/requester-rulings-20260924.md` から複製。`docs/work-orders/OPERATING_CONDITIONS.md` §1.5 の 35)。**両論の表は記録として 1 行も消していない** (同 §1.8 の 56)。

### U-1 baseline を置く場所

| | **(α) 契約 1.9.0 の obligation として契約本文に 1 節** | **(β) 契約は変えず conformance 条件 C-28 (仮) だけで固定** |
|---|---|---|
| **内容** | D-4 のとおり。baseline の一覧を契約本文に 1 節で置き、`version_binding` の 1.9.0 entry に unconditional obligation として結ぶ | 契約本文に baseline を置かず、C-28 (仮) が「両 peer が必ず完遂できる作業列」を固定する。契約版は R-23 の `operation_catalog_url` の義務化で上がるか、上がらない |
| **エージェントから見た形** | **契約版から baseline を知れる** — 契約を読めば「分岐せずに何が呼べるか」が分かる | **契約を読んでも baseline を知れない** — `conformance-tests/` を読まない限り分からない |
| **計画文書 R-29 行との関係** | 同行の「**契約義務としてではなく**、conformance 条件 … として固定する形である」という **2026-09-08 の監督提案の形からは外れる** | **台帳行の逐語の形そのもの**である |
| **P-7 との関係** | 契約に 1 節増える (短い一覧 1 つ。経緯は本書へ) | 契約は 1 バイトも増えない |
| **P-3 との関係** | baseline は宣言ではなく版の義務なので、advisory な宣言は増えない | 同左 (そもそも契約に書かない) |
| **`capability_status.rules` の「optional」** | **初めて定義できる** — 「optional でないもの = baseline」 | 未定義のまま残る |
| **影響範囲** | 契約 JSON (3 複製)・`version_binding`・`obligations`・`CCR_DISPOSITION.md` の従属判断 1 件・両 peer の版フリップ・契約版を固定するテスト | `conformance-tests/` のみ (+ U-4 が (α) なら契約は別理由で上がる) |

**監督の推奨: (α)。** **理由**: **P-7** (エージェントが読むのは契約であって `conformance-tests/` ではない) と、`capability_status.rules` の「optional」を**初めて定義できる**こと。

**【裁定】** **依頼者裁定 (2026-09-24)。逐語**: 「U-1 / U-4 (連動): 「(α) 契約の義務にする」 — baseline と operation_catalog_url を契約 1.9.0 (仮) の無条件義務にする。」 **本項と U-4 は 1 件の裁定である。** 反映先: §6 本文を (α) に確定 (§6.1 の `capability_status.rules` 6 番目を置く、§6.2 (1) の (b)、§6.3 (α) 案、§6.4 の C-29 `Status`)。

### U-2 床を上げるか

| | **(i) baseline = 現物の交差 (D-1) のまま** | **(ii) baseline に `row_addressability`・`unique_keys`・`revision_preconditions` を入れる** |
|---|---|---|
| **内容** | baseline は交差とし、Mitate の実需 (一意性 / `revision_preconditions` / append-only) は **MitateDB の機能を足す別項目**に付け替える (計画文書 R-49 + 新規起票 2 件) | baseline に `row_addressability`・`unique_keys` (`create_index` の unique)・`revision_preconditions` を入れ、**MitateDB-api の実装を本項目の WP に含める** |
| **Mitate の実需 (§1.6)** | **本項目では満たされない** (honest scope として §11 に明記する)。満たすのは別項目 | **本項目で満たされる** (一意性・`revision_preconditions`。append-only は R-49 の mutation class が別途要る) |
| **規模** | **L** (本書の前提) | **L を超える** — フェーズ11 の複数項目分。MitateDB のデータ面 (住所・一意索引・revision) の実装は、計画文書 R-102 (application ごとの直列化) と干渉しうる |
| **契約への影響** | 無し (交差は現行契約の語彙で書ける) | **spec の規則の見直しを含みうる** — `mutation_classes.rule` は「`row_addressability` が enabled のとき entity ごとに 1 クラス」を要求し、`upsert` の規則も住所の宣言に依存する (計画文書 R-49 行の「論点」) |
| **P-2 との関係** | 周回は交差だけで閉じる (§1.4) | 周回は閉じるが、周回の外の機能 (住所・一意性) を同時に足すことになる |
| **リスク** | 実需が「満たされないまま」残る期間が延びる | 範囲が閉じない (フェーズ10 設計 §5 U-13 が「入れると範囲が閉じない」として送った形の再来) |

**監督の推奨: (i) を本項目で行い、(ii) の起票の可否を同時に裁定してもらう。** (起票する場合は、`row_addressability` / `revision_preconditions` の MitateDB 実装の新規起票 2 件 + 既存の R-49。)

**【裁定】** **依頼者裁定 (2026-09-24)。逐語**: 「U-2: 「(i) 現物の交差 + 床上げは別起票」 — baseline は両 peer が今日実行できる操作の交差。Mitate の実需 (solutionName の一意性、revision_preconditions、append_only) は 本項目では満たされず、MitateDB に row_addressability / revision_preconditions を足す新規起票 2 件 + 既存 R-49 に付け替える。」 反映先: D-1 のまま (床は交差)、§11 の honest scope、§16 の起票 (1)(2)。

### U-3 R-23 の範囲

| | **(a) D-5 の最小形のみ** | **(b) (a) + 派生物の拡張** | **(c) (a) + 参照クライアント** |
|---|---|---|---|
| **内容** | 両 peer が `operation_catalog_url` を宣言し、byte 一致で配る (C-29 仮) | (a) に加え、**JSON Schema bundle** と **operation ごとの完全な要求例**を `tools/contract_catalog.py` と同じ「生成 + 再生成一致」で出し、同じ URL 群で配る | (a) に加え、**spec と base URL と key だけから要求を組み立てる共通コード** (`conformance-tests/` 内、peer 側 adapter を通らない) で、C-28 (仮) の作業列を wire plug (http ×2、socket ×2) に対して回す |
| **`spec/README.md`:5-9 の目標** | 索引の在り処が配備から分かるところまで | schema 本体と要求例まで機械可読になる | **実行可能な形で証明する唯一の案** — 「spec + base URL + key だけで使える」を実際に走らせる |
| **規模** | 小 (宣言 + 配布 + 条件 1 件) | 中 (生成器の拡張と再生成一致テスト) | **大** (参照クライアント 1 本 + 4 plug 駆動) |
| **P-7 との関係** | 派生物は既存 1 種のまま | 派生物が増えるが、すべて再生成一致で正本に縛る | 派生物は増えない。**クライアント側が契約だけを読む**ことを検査する |
| **C-19 との関係** | C-19 は宣言の 3 点を見る (§1.5) — 変わらない | 同左 | **C-19 が見ていない「契約だけで組み立てられるか」を実測で埋める** |

**監督の推奨: (a) を本項目、(c) を次の項目として起票。** (**依頼者が (c) を本項目に含めると裁定すれば、参照クライアントを WP-4 にする** — §10。)

**【裁定】** **依頼者裁定 (2026-09-24)。逐語**: 「U-3: 「(a) 最小形 + (c) を別起票」 — 本項目は両 peer が operation_catalog_url を宣言し byte 一致で配る (C-29) まで。参照クライアント (spec + base URL + key だけから要求を組み立てる共通コードで C-28 を wire plug に回す) は次の項目として起票。」 反映先: D-5 のまま (最小形)、§11 の honest scope、§16 の起票 (3)。**参照クライアントの WP は置かない** (§10 の但し書きは発動しない)。

### U-4 `operation_catalog_url` を 1.9.0 (仮) で義務化するか

| | **(α) 義務化** | **(β) optional のまま両 peer が宣言** |
|---|---|---|
| **内容** | 1.9.0 の unconditional obligation にする — 「1.9.0 を宣言する peer は `operation_catalog_url` を宣言し、その URL で byte 一致の派生カタログを配る」 | 契約の記述は optional のまま (現行 :1270-1274 の性格を維持)。両 peer が宣言し、**C-29 (仮) は declare-first** で書く |
| **契約文** | §6.3 (α) 案 | §6.3 (β) 案 |
| **`endpoints.operation_catalog` との関係** (**v0.3 追加**、§13.1 裁定 6 + 設計レビュー 2 指摘 6 の裁定) | endpoint と宣言の両方が 1.9.0 の義務である | **endpoint は 1.9.0 を宣言する peer に無条件で掛かり、optional なのは `operation_catalog_url` の宣言だけである。** endpoint entry の `semantics` が**版ゲートを逐語で持つ**ので (§6.6)、**1.8.0 を宣言する既存配備に遡及しない** — v0.2 §13.1 裁定 6 の「endpoint は無条件」はこの版ゲート付きの意味である |
| **P-3 との関係** | 宣言する peer にも宣言しない peer にも意味が定まる | **宣言しない peer が現れたときに C-29 の分岐が空を通る** (今は両 peer が宣言するので実害は無いが、将来の peer で vacuity が生じうる) |
| **他の配備への影響** | 1.9.0 を名乗る**すべての**配備が派生カタログを配る義務を負う (配る先が無い配備 — 例えば socket 面しか持たない配備 — の扱いを契約で決める必要がある) | 配れない配備は宣言しなければよい |
| **U-1 との整合** | U-1 (α) と同じ論理 (版の義務として結ぶ) | U-1 (β) と同じ論理 (宣言と conformance で閉じる) |

**監督の推奨: (α)。** 理由は **P-3** と、U-1 (α) と同じ論理である。

**【裁定】** **依頼者裁定 (2026-09-24)。逐語**: 「U-1 / U-4 (連動): 「(α) 契約の義務にする」 — baseline と operation_catalog_url を契約 1.9.0 (仮) の無条件義務にする。」 **U-1 と同一の裁定である。** 反映先: §6.2 (1) の (b) を角括弧なしで置く、§6.2 (2) の `unconditional` 2 件、§6.3 は (α) 案で確定、§6.4 の C-29 `Status` は version-gated、§6.5 の `conformance-tests/test_contract.py`:1189 / :1301 の pin を 1.9.0 の文言へ差し替える。**(β) の文案と分岐文は記録として残す。**

### U-5 Class D の裁定文

**本項目は `security/CONTROL_MAPPING.md` への証拠追記を含むため Class D である** (D-8)。**Class D は「依頼者裁定の逐語記録 + 版付きの security-contract 決定」を要求する** (計画文書 §9 の 8)。**依頼者の裁定文をここに逐語で置く。**

- 裁定の対象: (1) C-28 / C-29 (仮) の証拠を `security/CONTROL_MAPPING.md` (形式 3.0) の既存 SI の節に足すこと、(2) 本項目を Class D として扱うこと。
- **新しい Security Invariant は足さない** (§2.2 の 4、§8)。

**【裁定】** **依頼者裁定 (2026-09-24)。逐語**: 「U-5: 「この文で裁定する」 — 裁定文 (逐語): 「C-28 / C-29 の証拠を security/CONTROL_MAPPING.md (形式 3.0) の既存 SI の Common 節に足し、版を 3.1 → 3.2 に上げる。新しい Security Invariant は足さない。本項目は Class D として扱う。」」 反映先: §8.3、§10 WP-4、作業指示書 §5 (WP-4)。

---

## 6. 契約 1.9.0 (仮) の変更案

**契約文は英語である** (`spec/` は英語)。**本節の英文は案であり、確定は設計レビューと §5 の裁定の後である。** **v1.0 (2026-09-24)**: **§5 の裁定は済んだ (U-1 / U-4 = (α))。本節の英文は (α) の形で確定であり、確定した文は作業指示書が scratchpad の確定文ファイル経由で実装担当へ渡す** (§1.5 の 35)。**(β) の文案は採らないが、記録として本節に残す。** 契約 JSON の 3 複製は同一コミットで同一バイトにする。

### 6.1 baseline 節の契約文案 (`spec/data-service-api.v1.json`、`capability_status` の隣に新設)

```json
"common_baseline": {
  "purpose": "The operations a client may compose without reading capability_status first. Anything not named here stays optional in the sense capability_status.rules already gives that word.",
  "operations": [
    "capability discovery on the data surface (GET /v1/capabilities)",
    "catalog discovery (GET /v1/catalog)",
    "create_entity and add_field under a developer credential, including the enum and nullable members of field_constraints",
    "insert",
    "predicate query with the operators eq, ne, lt, lte, gt, gte and in, together with order_by and the size member of page",
    "predicate-addressed update and delete -- never row-addressed; a delete follows the declare-and-echo protocol destructive_confirmation defines",
    "request-level dry_run and the plan it returns",
    "idempotency_key: the key recorded with its request digest, and a resend of the same key with the same body answered from that record, carrying the original request_id, without executing again",
    "a request's own budget",
    "declared enum and nullable constraints enforced on every value written"
  ],
  "capabilities": [
    "application_catalog",
    "schema_operations",
    "structured_query",
    "atomic_mutation",
    "constraint_declarations",
    "dry_run",
    "idempotency",
    "request_budget"
  ],
  "rule": "An implementation declaring this contract version or higher executes every operation named here: it answers none of them with CAPABILITY_UNSUPPORTED, and it declares none of the capabilities common_baseline.capabilities names as unavailable. This is a floor, not a ceiling -- it neither requires nor forbids anything outside the list. A capability declared partial stays conformant as long as its own unsupported list names nothing this list names, and as long as the operations list it publishes to a credential of the role an operation names here carries that operation: schema_operations, for instance, is read under a developer credential, which is the credential this list names for create_entity and add_field. The request_id and details obligations 1.7.0 already binds unconditionally continue to apply to every operation named here. The floor is about what a deployment provides, not about what one entity's own catalog declaration admits: where row_addressability is provided, mutation_classes.rule continues to decide each entity, and an entity declaring a class that does not support update or delete still refuses them with CAPABILITY_UNSUPPORTED -- a refusal the client reads from the catalog before sending, not one it must discover by trying.",
  "outside": "Named here to remove doubt, these are NOT in the floor and remain governed by each implementation's own declaration: the contains, matches and is_null operators; upsert; cross-entity mutation; row_addressability (mutation classes and row addresses); revision_preconditions; audit_query on the data surface; best_effort_transactions; create_index, drop_index, drop_entity and jobs; and page.cursor and the continuation a non-null next_page would offer -- a peer may always answer next_page: null."
}
```

**P-7 の根拠**: 上の節は一覧 2 つ (`operations` と `capabilities`) と規則であり、**経緯 (なぜこの交差なのか) は本書 §1.3 / §1.4 と §3 D-1 に置く。**

**v0.2 の変更 (2026-09-24、設計レビュー 1 指摘 1・2・5 の裁定 = 採用)**:

1. **`operations` の 5 番目**を `"... together with order_by and page"` から **`"... together with order_by and the size member of page"`** に改めた (指摘 1)。
2. **`outside` の列挙に `page.cursor` と、非 null の `next_page` が与える継続を足した** (同上。「a peer may always answer next_page: null」の 1 文を含む)。
3. **`rule` に 2 文足した** (指摘 2 と指摘 5)。第 1 文は **(k)(l) の受け** — 1.7.0 が無条件で結んでいる `request_id` と `details` の義務がここに挙げた全 operation に掛かり続けることを述べ、`operations` 配列からは (k)(l) を外した (同じ義務を契約の 2 か所に別の語で載せない。P-7)。第 2 文は**レビューの文案を逐語で採ったもの**で、**床を「配備が提供する操作の床」に限定し、entity 単位の宣言を除外する** — これが無いと、`row_addressability` を provide する peer が `append_only` / `append_delete` / `read_only` の entity を 1 つ宣言した瞬間、契約は同じ要求に相反する二つの答え (`mutation_classes.rule` の `CAPABILITY_UNSUPPORTED` と、床の「`CAPABILITY_UNSUPPORTED` を返さない」) を命じる (`spec/data-service-api.v1.json`:680 の `mutation_classes.rule`、同:695 の `upsert`)。**今日露見しないのは r2db が `mutation_class` を `"mutable"` に固定しているからにすぎない** (`r2db-api/src/r2db_api/structured.py`:971、`r2db-api/src/r2db_api/postgres.py`:950)。**この但し書きにより、計画文書 R-49 (mutation class の実装) は契約上実装可能なままである** (§11)。
4. **`capabilities` 配列 (8 名) を置いた** (指摘 5)。これは `rule` が指す集合の**列挙**であり、**peer 側の宣言キーではない** — したがって §4 X-1 の却下理由には当たらない (X-1 は capability document への新キーを却下したのであって、契約本文の一覧ではない)。

**v0.3 の変更 (2026-09-24、設計レビュー 2 指摘 12・9 の裁定 = 採用)**:

5. **`rule` の第 1 文の「and it declares no capability one of them needs as unavailable」を「and it declares none of the capabilities common_baseline.capabilities names as unavailable」に書き換えた** (指摘 12 = §13.1 裁定 1 の本文反映)。**これで `capabilities` 配列が `rule` の主語になり、無拘束の配列でなくなる** (P-3)。**v0.2 の旧句は本行に逐語で残している。**
6. **`rule` の partial 節に credential 句を足した** (指摘 9。**レビューの文案を逐語で採った**)。理由: 両 peer とも `schema_operations` は **runtime credential のときに `operations: []` の `partial`** を返す (`r2db-api/src/r2db_api/capabilities_document.py`:62、`MitateDB-api/src/mitatedb_api/capabilities_document.py`:99 の `if is_developer else []`)。v0.2 の `rule` は `unsupported` 列しか見ていなかったので、**runtime の文書を読んだエージェントには「床は `create_entity` を約束するのに `operations` は空」という矛盾が見える**。足した句は、**床が名指す credential (developer) で読んだ `operations` に当該 operation が載っていることまでを規則にする。** あわせて **§7 段 (1) の期待欄に「`operations` の非空を assert しない」を註記した。**

**`capability_status.rules` の 6 番目の要素 (v0.3 追加、2026-09-24、設計レビュー 2 回答項の裁定 = 採用)**:

```text
Optional, in the sense the second rule above gives that word, means outside common_baseline: every operation common_baseline.operations names is required of an implementation declaring the contract version common_baseline.rule binds, and every other target operation stays optional and may be unavailable.
```

- **理由**: §5 **U-1 (α)** は「`capability_status.rules` の `optional` を**初めて定義できる**」ことを推奨の根拠に挙げているのに、v0.2 の §6 には**その語が現れる節 (`capability_status.rules`) に床を指す文を足す案が無かった** — 定義は `common_baseline.purpose` の側にしか無い形になっていた。
- **機械的帰結**: `conformance-tests/test_contract.py`:164-166 の **`len(rules) == 5`** の pin を **6** に更新する (**同じ変更セットで**。§6.5 の表)。**5 番目の要素 (1.8.0 が監督確定文として置いたもの) は 1 文字も動かさない** — 同テストの `rules[-1] == FIXED_1_8_0_CAPABILITY_STATUS_RULE` の assert は**末尾**を見るので、**6 番目を末尾に足すとこの assert が赤になる**。**新要素を 1.8.0 の文の前に置いて末尾を保つか、pin 側を末尾比較から index 比較に改めるかは、本書の裁定に含まれていない** — **起草時の開示として監督に上げる** (§1.5 の 37)。**どちらを採っても `len(rules) == 6` への更新は要る。**
- **U-1 が (β) と裁定された場合、この要素は置かない** (契約を触らないため)。
- **v1.0 の確定 (2026-09-24、依頼者裁定 U-1 = (α))**: **本要素は置く。** 上の中黒の条件 ((β) なら置かない) は (α) の確定で解消した — **行は残す** (§1.8 の 56)。
- **v1.0 の確定 (2026-09-24、監督裁定 §15 の 2)**: **6 番目の規則は `capability_status.rules` の末尾に追加する** (時系列順を保つ)。**`conformance-tests/test_contract.py`:168 の `rules[-1] == FIXED_1_8_0_CAPABILITY_STATUS_RULE` を `rules[4]` の index 固定に改め、1.8.0 の確定文そのものは 1 文字も変えない。** 同:165 の `len(rules) == 5` は **6** にする (同一変更セット。§6.5 の行)。**上の中黒が監督へ上げた開示 (末尾に置くか pin を改めるか) は、本裁定で決着した — 開示の行は判定の履歴として残す。**

### 6.2 `versioning.version_binding` の 1.9.0 (仮) entry 案

**(1) 散文への追記** (`version_binding` 文字列の末尾、1.8.0 の段落の後、版フリップの規律の文の前):

```text
Only an implementation declaring 1.9.0 or higher additionally claims conformance to the obligations 1.9.0 introduces (subordinate ruling 14). Those obligations are unconditional in the same sense as every obligation enumerated above -- they bind simply by declaring 1.9.0, independent of any capability's own status: (a) every operation common_baseline.operations names is executable -- it is not answered with CAPABILITY_UNSUPPORTED, and no capability it needs is declared unavailable[; and (b) its capability document carries operation_catalog_url, and the document served at that URL is byte-identical to this contract version's own derived operation catalog]. Because common_baseline names operations these capabilities govern, an implementation declaring 1.9.0 declares none of application_catalog, schema_operations, structured_query, atomic_mutation, constraint_declarations, dry_run, idempotency or request_budget as unavailable; every obligation an earlier version made conditional on exactly those capabilities therefore binds unconditionally at 1.9.0, and is not restated here. 1.9.0 introduces no obligation on what a client must send: a request valid under 1.8.0 stays valid. An implementation still declaring 1.8.0 is not held to any 1.9.0-only obligation retroactively.
```

- **`[; and (b) ...]` は §5 U-4 が (α) のときだけ置く。**
- **v1.0 の確定 (2026-09-24、依頼者裁定 U-4 = (α))**: **(b) を置く。角括弧は裁定待ちの標であり、契約に入る文には残さない** — `... independent of any capability's own status: (a) ...; and (b) its capability document carries operation_catalog_url, and the document served at that URL is byte-identical to this contract version's own derived operation catalog.` の形にする。**(b) を置かない (β) の形は §5 U-4 の表の記録として残る。**
- **v0.3 改訂 (2026-09-24、設計レビュー 2 指摘 2 の裁定 = (a) 採用)**: **この段落は無条件義務の件数文 (`<COUNT> of those obligations is/are unconditional ...`) を持たない。** v0.2 は `<COUNT>` を「(α) なら `Two ... are`、(β) なら `One ... is`」と書き、直後の中黒で「散文が述べる無条件義務の件数と `obligations` 索引の件数は機械的に一致させる」と述べていたが、**それは実測と合わない** — **実測**: `conformance-tests/test_operation_catalog_register.py` の固定事項 (vi) は、**複数形の**「`N of those obligations are unconditional`」文 (`_UNCONDITIONAL_COUNT_RE`、:278) を持つ版の集合が**ちょうど {1.4.0, 1.6.0, 1.7.0} の 3 件**であることを直接 assert する (:343-355)。(α) の複数形はこの assert を**赤にし**、(β) の単数形はこの正規表現に**当たらない** (= 件数照合が 1 件も走らない)。**契約側の規約もこれを許している** — `obligations_note` (`spec/data-service-api.v1.json`:200) は件数の一致を「**where the prose states one**」と条件付きで述べており、**件数文を置かないことは契約に適合する。** **したがって 1.9.0 の義務は (a)(b) の列挙だけで述べ、機械索引は `versioning.obligations` の entry (下の (2)) が担う。** **pin (`len(prose_counts) == 3`) は触らない。** **件数文を書いて pin を広げる案は却下である** (§4 **X-7**)。
- **WP-1 への註 (実装上の注意)**: 1.9.0 の段落に **`All of those obligations are unconditional`** のような語を置くと `_UNCONDITIONAL_COUNT_RE` に**当たってしまう** (`(\w+) of those obligations are unconditional`)。**上の文案は `Those obligations are unconditional` であり、当たらない。**
- **v0.2 追加 (2026-09-24、設計レビュー 1 指摘 5 の裁定 = 採用)**: 上の**「Because common_baseline names operations these capabilities govern, ...」の 1 文はレビューの文案を逐語で採ったもの**である。理由: 床は `application_catalog` / `schema_operations` / `structured_query` / `atomic_mutation` / `constraint_declarations` / `dry_run` / `idempotency` / `request_budget` を「`unavailable` にできない」状態にするので、**1.6.0〜1.8.0 が `conditional` として置いた義務は 1.9.0 では条件が決して偽にならない**。これを契約が述べないと、**機械索引だけを読むエージェントは、床があるのに依然として capability を読んで分岐する** — 本書のテーマが機械可読面で達成されない。
- **無条件化する `conditional` 行 (`spec/data-service-api.v1.json` の `versioning.obligations` から逐語で写した 8 件)**: 1.6.0 = `field_types_total_in_entity_descriptor` (`application_catalog`)、`create_entity_and_add_field_accept_field_types_vocabulary` (`schema_operations`)。1.7.0 = `constraint_declarations_accepted_and_enforced_on_schema_operations` (`constraint_declarations`, `schema_operations`)、`field_constraints_total_in_entity_descriptor` (`constraint_declarations`, `application_catalog`)、`dry_run_decides_as_the_real_request_and_leaves_no_external_effect` (`dry_run`)、`idempotency_key_recorded_with_request_digest_and_replayed_within_retention` (`idempotency`)、`request_budget_narrows_only_downward` (`request_budget`)。1.8.0 = `idempotency_concurrent_same_key_sends_serialized` (`idempotency`)。**実測の註**: この 8 行が条件に置く capability は上の 8 名のうち **6 名**であり、**`structured_query` と `atomic_mutation` を条件に持つ `conditional` 行は現存しない** (床はこの 2 つも `unavailable` にできなくするが、無条件化する既存義務はその 2 つには無い)。**これらの行を 1.9.0 で `conditional` から動かすかどうかは本書の決定に含まれていない** — 上の 1 文は「条件が偽にならない」ことを述べるだけであり、`obligations` 索引の既存 entry は動かさない。

**(2) `versioning.obligations` への entry 案** (U-4 (α) のとき):

```json
{
  "version": "1.9.0",
  "subordinate_ruling": 14,
  "unconditional": [
    "common_baseline_operations_executable",
    "operation_catalog_url_published_byte_identical"
  ],
  "conditional": []
}
```

U-4 (β) のときは `unconditional` を `["common_baseline_operations_executable"]` の 1 件にする。

**v1.0 の確定 (2026-09-24、依頼者裁定 U-4 = (α))**: **entry は上の 2 件で確定である。** 直前の 1 文 ((β) の 1 件案) は両論の記録として残す (§1.8 の 56)。

**(3) `spec/CCR_DISPOSITION.md` に従属判断 14 を 1 節新設する** (直前は従属判断 13 = 契約 1.8.0)。**本書 §3 の D-1 / D-4 / D-5 を指し、経緯を写さない。**

### 6.3 `operation_catalog_url` の扱いの案 (U-4 の両案)

**現行** (`spec/data-service-api.v1.json`:1270-1274 の `description`):

```text
Optional. The absolute URL at which this deployment publishes its own spec/OPERATION_CATALOG.json-shaped derived operation catalog, where it chooses to. Not required by any obligation this version introduces (D-8).
```

**(α) 義務化案** (v0.2 改訂):

```text
Required of an implementation declaring 1.9.0 or higher: the absolute URL at which a client reaches this deployment's own operation_catalog operation. The document served there is byte-identical to the derived operation catalog of the contract version this capability document declares. The URL is not required to sit under this deployment's surfaces.data.base_url: a deployment serving the document from elsewhere -- a content delivery network, for instance -- names that URL here. An implementation declaring a lower version may publish it or not, as before.
```

**(β) optional 維持案** (v0.2 改訂):

```text
Optional. The absolute URL at which this deployment publishes its own spec/OPERATION_CATALOG.json-shaped derived operation catalog, where it chooses to. Where it does publish one, the document served there is byte-identical to the declared contract version's own spec/OPERATION_CATALOG.json, and the URL is not required to sit under this deployment's surfaces.data.base_url. Not required by any obligation this version introduces.
```

**v0.2 の変更 (2026-09-24、設計レビュー 1 指摘 8 の裁定 = 一部採用)**: レビューは両案に「The URL is under this deployment's own surfaces.data.base_url.」を足すよう求めたが、**裁定は逆であり、その制約を置かない** — **契約に無い性質を条件に入れないため**であり (条件 > 契約になる)、**CDN 等に置く conformant な配備を落とさない**ためである。あわせて (α) は**配る path が契約 `endpoints` の operation `operation_catalog` であること**を指す形にした (D-5)。

**注 (起草時の開示)**: 現行文末の `(D-8)` はフェーズ9 設計文書のローカル ID を指しており、**他文書から参照するときは文書名を添える規律** (`docs/work-orders/OPERATING_CONDITIONS.md` §1.8 の 59) に照らすと、契約本文に裸で置かれたままである。**(α) は当該文ごと置き換わるので問題は消える。(β) を採る場合は `(D-8)` を `(phase 9 design D-8)` の形に直すか、削るかを設計レビューで決める** — **本書はどちらにも寄せていない。**

**v0.2 註 (2026-09-24、設計レビュー 1 指摘 4 の裁定 = 採用)**: **(α)(β) のどちらを採っても、この `description` は `conformance-tests/test_contract.py` の 1.7.0 逐語 pin に当たる** (:1189 の `PIN_1_7_0_CAPABILITY_DOCUMENT_OPERATION_CATALOG_URL`、:1301 以下の assert)。裁定は次のとおりである。

- **(α) を採る場合**: **当該文ごとの置換であるから、pin を 1.9.0 の文言へ差し替える。** **版の文言を pin するテストは、版を上げる同一変更セットで新しい文言へ移す** — `docs/work-orders/OPERATING_CONDITIONS.md` §1.5 の 35 が禁じるのは**依頼者が確定した文の言い換え**であり、**版の改訂そのものは §5 U-4 の依頼者裁定である**。
- **(β) を採る場合**: **現行文を含んだまま追記する形になるので、pin は緑のままである。** このとき文末の **`(D-8)` の裸参照は履歴として残る** (**v0.1 §12 の裁定と同じく、本書はこれを直す決定をしていない**)。
- どちらの場合も **§6.5 の表に `conformance-tests/test_contract.py`:1189 / :1301 の行を置く** (実装担当が想定外の赤に当たらないようにする)。

**v1.0 の確定 (2026-09-24、依頼者裁定 U-4 = (α))**: **契約に入るのは (α) 義務化案である。** **(β) optional 維持案は採らない — 行は消さず、両論の記録として本節に残す** (§1.8 の 56)。帰結: (i) 上の「注 (起草時の開示)」の `(D-8)` の裸参照は、**(α) が当該文ごと置き換えるので消える**。(ii) 上の v0.2 註の (α) 側が確定形である — **`conformance-tests/test_contract.py`:1189 / :1301 の 1.7.0 逐語 pin を 1.9.0 の文言へ差し替える** (§6.5)。

### 6.4 `conformance-tests/CONDITIONS.md` の C-28 / C-29 (仮) 行の案

**行の言語は同ファイルの既存行 (C-27 行) に合わせて英語とする。** 列は `| ID | Condition | Invariants | Evidence | Status |` である。**SI 列の根拠は §8。**

**C-28 (仮) 行の案**:

```text
| C-28 | A client that composes only the operations `common_baseline` names, reading no capability status at all, completes one whole agent turn against every conformant peer: it discovers capabilities and the catalog, creates an entity carrying an `enum` and a `nullable: false` field under a developer credential, builds a request from the catalog alone, is refused with `VALIDATION_FAILED` carrying `violated_declaration: enum` and the `field` position, repairs THAT SAME request from the diagnosis and the catalog, reaches the same decision under `dry_run: true` -- carrying the same `idempotency_key` it will send for real, which a dry run neither records nor looks up -- with `committed: false` and a `plan`, sends the repaired request for real under that key while presenting THAT SAME `plan`, receives `committed: true` with a `request_id` and no plan-mismatch refusal, resends the same key with the same body and receives the FIRST execution's own `request_id` with no second row, queries with each baseline operator under `order_by`, a `page` `size` at least as large as the rows that come back, and a `budget` whose `result_items` is at least that `size` and no larger than the `limits.result_items` this deployment's own capability document declares, updates and deletes by predicate (the delete under declare-and-echo), and reads the resulting state back. No step branches on a declaration: a `CAPABILITY_UNSUPPORTED` anywhere in the turn is a failure of this row. | SI-05, SI-09, SI-10, SI-11, SI-14 | one scenario test per adapter carrying the same request body from the refusal through the repair, the dry run, the real send and the resend -- `conformance-tests/test_c28_baseline_turn.py` | executable (six adapters) -- `conformance-tests/test_c28_baseline_turn.py`, `@pytest.mark.condition("C-28")`, port v1.16; unconditional 1.9.0 obligation, version-gated rather than capability-gated. Relationship to C-20/C-21/C-22/C-23/C-25: those rows fix each step's own meaning and stay as they are; this row fixes that the steps hand one request to each other. [history](CONDITIONS_HISTORY.md#c-28) |
```

**C-29 (仮) 行の案**:

```text
| C-29 | The derived operation catalog a peer names in `operation_catalog_url` is the contract's own: the document served at that URL is byte-identical to the derived operation catalog this repository's spec generates, whose own `contract_version` equals the version the same capability document declares, so a client that read the URL and a client that read the specification hold the same index. | SI-10 | a fetch of the declared URL compared byte-for-byte against the packaged catalog for the declared version, alongside the existing regeneration-identity test (`conformance-tests/test_operation_catalog_register.py`) | executable (six adapters) -- `conformance-tests/test_c29_operation_catalog_url.py`, `@pytest.mark.condition("C-29")`, port v1.17. Two stages: (i) on all six plugs, the body the peer itself returns for its own `operation_catalog` operation (port `operation_catalog_document()`) is compared byte-for-byte against the packaged derived catalog, and the parsed body is validated against `schemas.OperationCatalogDocument` with `conformance-tests/schema_check.py`; (ii) on plugs whose `transport_kind` is `socket`, the declared `operation_catalog_url` is dialled for real and yields the same body (non-vacuity: at least one socket plug). **Honest limit**: on the four in-process plugs the declared URL is a synthetic, non-dialled placeholder; the URL is NOT required to sit under `surfaces.data.base_url`; and this row's own byte comparison, not C-11's response-schema reverse-validation, is what holds the served document to the contract. [history](CONDITIONS_HISTORY.md#c-29) |
```

- **U-4 (α)** のとき: C-29 の `Status` 欄は「unconditional 1.9.0 obligation, version-gated」と書く。
- **U-4 (β)** のとき: 「declare-first on `capabilities().operation_catalog_url`。**Declaration branch**: 未宣言 — 何も配らないことを確認する枝。Otherwise — byte 一致」と書く。**両 peer が同じ変更セットで宣言するので、肯定側は両 peer で load-bearing である。**
- **v1.0 の確定 (2026-09-24、依頼者裁定 U-4 = (α))**: **C-29 行の `Status` は (α) の形 (「unconditional 1.9.0 obligation, version-gated」) で書く。** 直前の (β) の中黒は両論の記録として残す。
- **`executable (six adapters)` と書けるかは port の形に依る** (§7 末尾の開示事項)。
- **v0.2 の変更 (2026-09-24、設計レビュー 1 指摘 1・6・7・8 の裁定)**: C-28 行の条件文を **D-2 / §7 と同じ語に揃えた** — (i) `under order_by and page` を **`order_by`・`page` の `size`** に (指摘 1)、(ii) query に **`budget`** を足し (指摘 6)、(iii) dry_run が**実送信と同じ `idempotency_key`** を運び、実送信が**その `plan` を提示する**形にした (指摘 7)。C-29 行の `Status` 欄を**二段形**に書き改めた (指摘 8。`surfaces.data.base_url` 配下という制約は置かない)。
- **v0.2 註 (設計レビュー 1 指摘 11 = 観察、本項目では直さない)**: 既存の `conformance-tests/CONDITIONS.md` は C-06 / C-12 / C-20 / C-22 / C-23 行を `executable (four adapters)` と書くが、**実測では 6 件収集される** (`conformance-tests/conftest.py`:260 の `adapter` fixture が `registry.json` の 6 件に parametrize する)。**裁定により C-28 / C-29 行は `six adapters` と書く** (凡例は `four adapters` を registry の全 adapter の意味で用いている)。**既存行の陳腐化は本設計が作った欠陥ではなく、本項目では直さない** — **直すか別起票かは引き継ぎ書の裁定表に載せる。**

- **v0.3 の変更 (2026-09-24、設計レビュー 2 指摘 3・4・5・10 と回答項の裁定)**:
  1. **C-28 行の `budget` を 1 つの不等式に固定した** (指摘 4) — 「返る行数 R ≤ `page.size` S ≤ `budget.result_items` B ≤ 宣言 `limits.result_items`」。**右端は capability document から読み、固定リテラルを書かない** (D-2 段 (9)、§7 段 (9) と同じ語である)。
  2. **C-29 行の条件文を言い換えた** (**回答項の裁定 = 採用**) — v0.2 は「the `spec/OPERATION_CATALOG.json` of the contract version the same capability document declares」と書いていたが、**`spec/OPERATION_CATALOG.json` は版別保管を持たない単一の生成物である** (`spec/OPERATION_CATALOG.json`:1-3 の `$comment` と `contract_version`)。旧文は**存在しない対象 (過去版の生成物) を指しうる**ので、「**this repository's spec generates, whose own `contract_version` equals the version the same capability document declares**」の形にした。
  3. **C-29 行の末尾に `[history](CONDITIONS_HISTORY.md#c-29)` を足した** (指摘 3) — `conformance-tests/test_conditions_register.py`:345-386 が、全行に `[history]` リンクがあることと、companion (`CONDITIONS_HISTORY.md`) の見出し集合が主表の ID 集合と**過不足なく一致する**ことを要求する。**`## C-28` / `## C-29` の節を同じ変更セットで新設する** (§6.5 の表)。
  4. **C-29 の port 版数を v1.16 から v1.17 に分けた** (指摘 10) — **段 (9) の query method (WP-2) が v1.16、`operation_catalog_document()` (WP-3) が v1.17** である。v0.2 は別 WP の別追加に同じ版数を書いていた。
  5. **C-29 の (i) に `schemas.OperationCatalogDocument` に対する schema 検証を足した** (指摘 5) — 配られた本文を `conformance-tests/schema_check.py` の `assert_valid` で検証する。**あわせて honest limits に「C-11 の応答 schema 逆検証の対象ではない」ことを開示した** — C-11 は対象 schema を**手で列挙**しており (`conformance-tests/test_c11_response_schema_conformance.py`:339-433)、新 schema は自動では対象にならない (§11)。

- **WP-1 が置く暫定 `Status` 欄 (v0.3 追加、2026-09-24、設計レビュー 2 指摘 3 の裁定 = 採用)**: **上の 2 行案は WP-2 / WP-3 が着地した後の最終形である。** **WP-1 が置く時点ではテストファイルが存在しないので、`Status` 欄を `executable` で始めてはならず、テスト名を 1 つも書いてはならない** — `conformance-tests/test_conditions_register.py` は (i) `Status` が `executable` で**始まる**行に `@pytest.mark.condition(<ID>)` のテストが収集されることを要求し (:236-247)、(ii) `CONDITIONS.md` の**テスト名参照とファイルパス参照が実在の def / file に解決する**ことを要求する (:702-717 の `bare_file` を含む 5 形、:745-751)。**暫定文の案** (C-27 の declared 期の先例と同じ形である):

```text
declared; not yet executable -- this item's later work package lands the scenario, and the row is declared here so the design document's own C-28 references resolve, the same sequence C-20..C-27 followed (design first, condition row second). Unconditional 1.9.0 obligation, version-gated rather than capability-gated. Relationship to C-20/C-21/C-22/C-23/C-25: those rows fix each step's own meaning and stay as they are; this row fixes that the steps hand one request to each other. [history](CONDITIONS_HISTORY.md#c-28)
```

  - **C-29 も同じ形の暫定 `Status` にする** (`C-28` を `C-29` に、関係節を「the regeneration-identity test fixes that the derived catalog agrees with the contract; this row fixes that the document a deployment serves is that same catalog」に置き換える)。
  - **Evidence 欄にもテストファイル名を書かない** (**起草時の開示**: 上の (ii) の参照抽出には `bare_file` 形があり、**未作成のファイルパスも未解決になる**。C-27 の declared 期は Evidence 欄に `(not yet created)` を付けてファイル名を書いていたので、**許容形かどうかは WP-1 で実測する**。**実測して許容されるなら書いてよい** — 本書はどちらにも寄せていない)。
  - **v1.0 の確定 (2026-09-24、監督裁定 §15 の 3)**: **C-27 の declared 期の先例に合わせ、Evidence 欄には テストファイル名を `(not yet created)` 付きで書く。** 直前の中黒 (書かない) は本裁定で覆した — **行は消していない** (§1.8 の 56)。**WP-1 は `conformance-tests/test_conditions_register.py` の参照解決の検査 (:702-717) が緑であることを 完了条件とする** (作業指示書 §2)。**【v1.1 訂正 2026-09-24 (WP-1 実測、作業指示書 §7.1 訂正註 2)】** 現行の `test_conditions_register.py` は backtick 付きの未作成ファイル名を `file not found`、backtick 無しを naked token で赤にするため、declared 期の Evidence 欄にはファイル名を書かない (散文で証拠の形を書く)。C-26 / C-27 の先例は参照解決の検査 (main 2365955) 以前のものである。
  - **WP-2 が C-28 行の、WP-3 が C-29 行の `Status` 欄を、上の最終形 (`executable (six adapters) -- ...`) に書き換える。** **この書き換えは `CONDITIONS_HISTORY.md` の該当節に旧文を逐語で残して行う** (`docs/work-orders/OPERATING_CONDITIONS.md` §1.8 の 56、C-27 の先例)。
  - **§12 の裁定 4 (本書は WP-1 と同一変更セット) はこの暫定文でも成立する** — `tools/check_doc_refs.py` が見るのは ID 族であって、テスト名やファイルパスではない。

### 6.5 両 peer の宣言の変更点

| 対象 | 変更 |
|---|---|
| `r2db-api/src/r2db_api/capabilities_document.py` / `MitateDB-api/src/mitatedb_api/capabilities_document.py` | `contract_version` を 1.9.0 (仮) にする。**baseline のための新しい status 変更は無い** — 現物の交差なので、どちらの peer も status を 1 つも動かさずに義務を満たす (§1.3 の実測)。 |
| 同上 | `operation_catalog_url` を宣言に足す (D-5)。**値は配備側が与える** — 本書に実ホスト名・実ドメインは書かない。**宣言と、その URL が byte 一致の文書を返すことは同一コミットである** (`docs/work-orders/OPERATING_CONDITIONS.md` §1.1 の 11)。 |
| 契約 JSON の 3 複製 | 同一コミットで同一バイトに更新する。 |
| 契約版を固定するテスト | `conformance-tests/test_contract.py`:95、`MitateDB-api/tests/test_denial_details_and_request_id.py`:522 を同じ変更セットで更新する。**r2db 側に 1.8.0 の直接固定があるかは着手時に再実測する** (探索では見つからなかった)。 |
| 計画文書 §0.1.1 の G-2 / G-3 行 | 契約版と条件数 (28 → 30) を同じ変更セットで更新する (D-7)。 |
| **`conformance-tests/test_contract.py`:1189 / :1301** (**v0.2 追加、設計レビュー 1 指摘 4 の裁定**) | `operation_catalog_url` の **1.7.0 逐語 pin** (`PIN_1_7_0_CAPABILITY_DOCUMENT_OPERATION_CATALOG_URL` と、その assert)。**§5 U-4 が (α) なら当該文ごとの置換なので pin を 1.9.0 の文言へ差し替える** (版の文言を pin するテストは、版を上げる同一変更セットで新文言へ移す)。**(β) なら現行文を含んだまま追記するので pin は緑のままである** (§6.3 の註)。 **v1.0 の確定 (2026-09-24、依頼者裁定 U-4 = (α))**: **(α) であるから pin を 1.9.0 の文言へ差し替える。** |
| **派生カタログ `OPERATION_CATALOG.json` の 3 複製** (**v0.2 追加、設計レビュー 1 指摘 3 の裁定**) | `spec/OPERATION_CATALOG.json` に加えて `r2db-api/src/r2db_api/contract/OPERATION_CATALOG.json` と `MitateDB-api/src/mitatedb_api/contract/OPERATION_CATALOG.json` を置き、**同一コミットで同一バイト**にする。`conformance-tests/test_operation_catalog_register.py` の**再生成一致テスト (:120) を 3 複製比較に拡張する** (D-5)。 |
| **`conformance-tests/test_operation_catalog_register.py`:117** (**v0.2 追加、設計レビュー 1 指摘 8 の裁定の機械的帰結**) | `assert len(entries) == 19` (「7 + 12」) を、**`operation_catalog` endpoint を足した後の件数 (8 + 12 = 20)** に更新し、`spec/OPERATION_CATALOG.json` を**再生成して 3 複製に反映する** (D-5)。 |
| **`conformance-tests/test_contract.py`:1414** (**v1.0 追加、2026-09-24、起草時の実測**) | `test_contract_1_7_0_structure_and_additive_only` は `endpoints` + `control_endpoints` の entry 数を **`assert n == 19`** で固定する (同:1405-1414 の走査)。**`endpoints.operation_catalog` を足すと 20 になるので、同一変更セットで 20 に更新する。** 本行は §6.6 の決定の機械的帰結であり、新しい決定ではない (v0.3 は `test_operation_catalog_register.py`:117 の件数だけを挙げていた)。 |
| **`spec/CONTRACT_HISTORY.md` の `## versioning.version_binding` 節** (**v0.3 追加、設計レビュー 2 指摘 1 の裁定 = 採用**) | **同一変更セットで**: (1) **Value** の逐語 quote を**追記後の値に置き換える**、(2) **Subordinate ruling(s):** に `- 従属判断 14` を足す、(3) **Introduced in:** を `contract 1.2.0 through 1.9.0 (cumulative)` にする、(4) **1.8.0 の Revision note の直後に 1.9.0 の Revision note を同じ形で書く** (1.9.0 が足す **provenance-marker 無しの契約値**を列挙する)。**理由**: この entry は `spec/CONTRACT_HISTORY_MANIFEST.json` で **`unstripped: true`** であり、`conformance-tests/test_contract_history_register.py` の固定事項 (5) (:40-43) は **live 値との完全一致**を要求する — **§6.2 (1) を `version_binding` に追記した瞬間に赤になる。** 固定事項 (4) (:37-39) は節が名指す従属判断が `spec/CCR_DISPOSITION.md` に実在することを要求するので、**従属判断 14 の新設 (§6.2 (3)) と同じ変更セットである。** |
| **`spec/CONTRACT_HISTORY.md` に新しい `## <json_path>` 見出しは足さない** (**v0.3 追加、実測**) | **実測 (v0.3 で再実測)**: §6.1 の `rule` に足した 2 句・`capabilities` 配列・`capability_status.rules` の 6 番目・§6.3 (α)(β) の文案・§6.6 の `semantics` の版ゲート文は、いずれも `test_contract_history_register.py` の `_PATTERNS` (`Since 1.x.y` / `subordinate ruling N` / `superseded` / `supersedes` / `ruling` / `Phase N` / `WP-N` / 日付 / `CCR-N` / `historical` / `previously` / `formerly` / 先頭 `was `) に **0 ヒット**である — したがって**固定事項 (1)(6) は緑のままであり、新しい見出しは不要である。** **`(subordinate ruling 14)` を書く §6.2 (1) だけがヒットするが、そのパスは `unstripped: true` であり既に `## versioning.version_binding` 見出しを持つ**ので問題にならない。**WP-1 は文案を変えたら再実測する。** |
| **`conformance-tests/CONDITIONS_HISTORY.md`** (**v0.3 追加、設計レビュー 2 指摘 3 の裁定 = 採用**) | **`## C-28` / `## C-29` の節を、主表の行と同じコミットで新設する** — `conformance-tests/test_conditions_register.py`:345-386 が、全行に `[history](CONDITIONS_HISTORY.md#<slug>)` があることと、**companion の見出し集合が主表の ID 集合と過不足なく一致する (両方向)** ことを要求する。**WP-2 / WP-3 が `Status` 欄を最終形に書き換えるときは、旧文をこの節に逐語で残す** (§1.8 の 56、C-27 の先例)。 |
| **`conformance-tests/test_contract.py`:164-166** (**v0.3 追加、設計レビュー 2 回答項の裁定 = 採用**) | `capability_status.rules` に 6 番目の要素を足すので (§6.1)、**`assert len(rules) == 5` を 6 に更新する** (同一変更セット)。**同テストが 1.8.0 の監督確定文を `rules[-1]` で見ていることに注意する** (§6.1 の開示)。**§5 U-1 が (β) と裁定されれば、この行は不要である。** **v1.0 の確定 (2026-09-24、U-1 = (α)、監督裁定 §15 の 2)**: **本行は要る。6 番目は末尾に追加し、同:168 の `rules[-1]` を `rules[4]` の index 固定に改める** (1.8.0 の確定文 `FIXED_1_8_0_CAPABILITY_STATUS_RULE` は 1 文字も変えない)。`len(rules) == 6`。 |
| **`conformance-tests/test_operation_catalog_register.py`:343-355** (**v0.3 追加、設計レビュー 2 指摘 2 の裁定**) | **触らない。** 固定事項 (vi) の版集合 pin (`len(prose_counts) == 3`、`{1.4.0, 1.6.0, 1.7.0}`) は、**§6.2 (1) が無条件義務の件数文を持たないので緑のままである。** **件数文を書いて pin を広げる案は却下である** (§4 X-7)。 |

### 6.6 `endpoints.operation_catalog` entry と応答 schema の案 (v0.3 新設、2026-09-24)

**設計レビュー 2 指摘 5・6・7 の裁定 = 採用。** v0.2 は D-5 / §13.1 裁定 3 で `method` / `roles` / `requires_capability` / `response` の 4 つしか決めておらず、**残りの必須キーを実装担当が自分で決めることになっていた** (= 設計外の決定)。**entry の全文案を置く。**

```json
"operation_catalog": {
  "method": "GET",
  "path": "/v1/operation-catalog",
  "auth": "runtime or developer",
  "response": "OperationCatalogDocument",
  "semantics": "Served by an implementation declaring 1.9.0 or higher; an implementation declaring a lower version is not held to it.",
  "roles": ["runtime", "developer"],
  "requires_capability": [],
  "atomicity": "none"
}
```

- **必須キーの根拠 (実測)**: `tools/contract_catalog.py`:61-72 の `_endpoint_record` は `method` / `path` / `roles` / `requires_capability` / `atomicity` を**必須**で読む (欠ければ生成器が KeyError で落ちる)。`conformance-tests/test_operation_catalog_register.py` の固定事項 (i) は **`roles` が同じ entry の `auth` 散文と一致する**ことを `_roles_expected_from_auth` (:88-99) で検査し、(iii) は `atomicity` が `{atomic, none, atomic_unless_best_effort}` のいずれかであることを検査する。**`auth` の `"runtime or developer"` は `{runtime, developer}` に解決する** (:80 の `_ROLE_GROUPS`。`endpoints.query` / `endpoints.mutate` と同じ形であり、**data surface の bearer application credential** を意味する)。
- **`destructive` は entry のキーではない** — 生成器が `destructive_confirmation.applies_to_structured` から**構造的に導く** (`tools/contract_catalog.py`:51-58)。この operation はそこに現れないので、**派生カタログ上は `destructive: false` になる** (裁定 7 の「destructive false」はこの導出値のことである)。**`request` キーは置かない** (GET であり要求体が無い。派生カタログ上は `request_schema: null` になる)。
- **`path` は案である** (`endpoints` の既存 7 件が `/v1/...` であることに揃えた)。**確定は WP-1。**
- **版ゲートの 1 文 (`semantics`) の理由** (指摘 6 の裁定): 新 endpoint は `requires_capability` が空なので **capability による逃げ道が無く**、U-4 (β) では版による逃げ道も無い。**この 1 文が無いと、契約 `endpoints` は 1.8.0 を宣言する既存配備 (今日の両 peer を含む) を即座に「serve していない endpoint がある」状態に置き、§6.2 (1) 自身の「An implementation still declaring 1.8.0 is not held to any 1.9.0-only obligation retroactively」と正面から反する。** **`requires_capability` に既存 capability を 1 つ置いて門にする案は採らない** — 床に無い capability を門にすることになり、X-1 の趣旨に反する。
- **自己言及は循環しない (実測、レビュー 2 で確認)**: 生成器は `endpoints` からの純投影であり、生成物自身を読まない (`tools/contract_catalog.py::build_catalog`)。再生成一致テストは生成物と on-disk を比べるだけなので、**20 件目の operation が自分自身を指しても循環しない。** 件数は **8 + 12 = 20** で §6.5 の記述どおりである。

**応答 schema (指摘 5 の裁定 = 採用)**: **`schemas.OperationCatalogDocument` を新設し、`definitions.OperationCatalogEntry` (entry の 9 フィールド) をその `operations` の要素にする。** v0.2 の §13.1 裁定 3 は「`definitions` に `OperationCatalog` (entry の 9 フィールド) を新設し `response` がそれを指す」としていたが、**実測でその形は採れない** — (1) `endpoints.*.response` が指す名前は**すべて top-level `schemas` の member** であり (`schemas` 20 件に対し `definitions` は 6 件の共有部品)、`definitions` を指す entry は 1 件も無い。(2) 配る文書の top-level は `{$comment, contract_version, operations}` であり (`spec/OPERATION_CATALOG.json`:1-4)、**entry の 9 フィールドを記述した schema では応答を記述できない。**

```json
"schemas": {
  "OperationCatalogDocument": {
    "type": "object",
    "additionalProperties": false,
    "required": ["$comment", "contract_version", "operations"],
    "properties": {
      "$comment": { "type": "string" },
      "contract_version": { "type": "string" },
      "operations": { "type": "array", "items": { "$ref": "#/definitions/OperationCatalogEntry" } }
    }
  }
},
"definitions": {
  "OperationCatalogEntry": {
    "type": "object",
    "additionalProperties": false,
    "required": ["name", "method", "path", "roles", "requires_capability", "atomicity", "destructive", "request_schema", "response_schema"],
    "properties": {
      "name": { "type": "string" },
      "method": { "type": "string" },
      "path": { "type": "string" },
      "roles": { "type": "array", "items": { "type": "string" } },
      "requires_capability": { "type": "array", "items": { "type": "string" } },
      "atomicity": { "enum": ["atomic", "none", "atomic_unless_best_effort"] },
      "destructive": { "type": "boolean" },
      "request_schema": { "type": ["string", "null"] },
      "response_schema": { "type": ["string", "null"] }
    }
  }
}
```

- **9 フィールドの出所 (実測)**: `tools/contract_catalog.py`:61-72 の `_endpoint_record` が返す 9 キーそのものである。**schema は生成器の投影に後から付ける記述であり、生成器の正本性を動かさない** (P-7)。
- **閉じた schema にする** — 1.2.0 の obligation (3) が「this version lists as closed」な schema / definition に `additionalProperties: false` を要求する形に揃えた。**新設 2 件がその「closed」の列挙に名指しで載る必要があるかは WP-1 で実測する。**
- **v1.0 の確定 (2026-09-24、監督裁定 §15 の 4)**: **2 つの新 schema は閉じた形 (`additionalProperties: false`) で書き、1.2.0 の closed 列挙に載せる** — 載せなければ列挙が「全 schema」でなくなるためである。**直前の中黒の保留は本裁定で決着した (行は残す)。** **起草時の実測 (列挙の所在)**: 1.2.0 の obligation (3) が言う「this version lists as closed」の列挙は **契約 JSON の中の配列ではなく**、`spec/CCR_DISPOSITION.md` の**従属判断 7(A)** の散文である (応答 schema 11 種 + `definitions.EntityDescriptor` + request `AuditQueryRequest` + ネスト 4 箇所を名指し、意図的に開けた 4 箇所を除外として挙げる)。**WP-1 は、その列挙を検査するテストが緑であることを完了条件とする** (作業指示書 §2。**検査テストの所在と、そもそも機械検査が存在するかは WP-1 が実測して報告する** — 起草時の実測では `conformance-tests/test_c11_response_schema_conformance.py` の手書き列挙と `conformance-tests/test_contract.py` の個別 assert しか見つかっていない)。**【v1.1 訂正 2026-09-24 (WP-1 実測、作業指示書 §7.1 訂正註 3)】** 7(A) の列挙を読む機械検査は存在しない (実測)。完了条件 8 は監査照合 (`spec/CCR_DISPOSITION.md` の 7(A) 行と契約 JSON の `additionalProperties: false` の行を報告と §17 に記す)。動的な効力は WP-3 の O6 が持つ。
- **`schema_check.py` で検証できる形にしてある (実測)**: 上で使ったキーワード (`type` / `required` / `properties` / `additionalProperties` / `enum` / `items` / `$ref`) はすべて `conformance-tests/schema_check.py`:59-76 の `IMPLEMENTED_KEYWORDS` の中である (同モジュールのキーワード集合は**閉じており**、未実装のキーワードを使うと `ValueError` になる)。**C-29 の (i) が配られた本文をこの schema に対して `assert_valid` する** (§6.4)。
- **C-11 の手書き列挙には載せない** (裁定 5): `conformance-tests/test_c11_response_schema_conformance.py` は対象 schema を**手で列挙している** (:339-433) ので、新 schema は自動では C-11 の逆検証の対象にならない。**本設計は C-11 の列挙に載せない** — **配る文書を契約に縛るのは C-29 の byte 一致と上の `schema_check` である。** **この限界は §6.4 の C-29 行の honest limit と §11 に開示する。**

---

## 7. C-28 (仮) の段の表

**「その段だけを壊す変異」は候補である** — **実測前であり、実際に赤になる test id は作業指示書の「完了条件 ↔ 変異」表で実測して確定する** (`docs/work-orders/OPERATING_CONDITIONS.md` §1.5 の 34)。

| 段 | 使う port method (`conformance-tests/adapter.py`) | 期待する応答 | 対応する既存条件 | その段だけを壊す変異の候補 | **この段だけが赤か** (起草時点の見込み。**実測は作業指示書の「完了条件 ↔ 変異」表で行う**) |
|---|---|---|---|---|---|
| (1) capabilities を読み契約版を読む | `capability_document()` (:1200) | `contract_version` が 1.9.0 (仮) 以上。baseline が要る capability が 1 つも `unavailable` でない。**`operations` の非空を assert しない** (**v0.3 追加、設計レビュー 2 指摘 9 の裁定**: 両 peer とも `schema_operations` は **runtime credential では `operations: []` の `partial`** を返す。床が名指す credential は **developer** である。§6.1 の `rule` の credential 句と同じ語である) | C-11・C-12・C-19 | peer の `capabilities_document.py` の `contract_version` を 1.8.0 に戻す (宣言だけ下げる) | **同時に赤** — `contract_version` を下げれば C-12 / C-19 も赤になる |
| (2) developer で entity を作る (enum と `nullable: false`) | `schema_operation_with_result(..., operation="create_entity", field_constraints=...)` (:2333) | 成功。`request_id` を持つ | C-20 | developer credential でも `create_entity` を `CAPABILITY_UNSUPPORTED` にする | **同時に赤** (C-20) |
| (3) runtime で catalog を読む | `catalog_document(session)` (:2229) | `EntityDescriptor` が (2) で宣言した `field_constraints` を同じ版で報告する | C-11・C-17・C-20 | catalog の `EntityDescriptor` から `field_constraints` を落とす | **同時に赤** (C-11 / C-17 / C-20) |
| (4) catalog だけから要求を組み立て、enum 外の値で `insert` を送る | `attempt_mutation_with_result(..., operation="insert", values=...)` (:2563) | `VALIDATION_FAILED`、`details.violated_declaration == "enum"`、`details.field` が要求本体内の位置を指す | C-20・C-21 | 値検証の choke point を外し、enum 外の値を受理して書き込む | **同時に赤** (C-20 / C-21) |
| (5) 診断だけを使って同じ要求を直す (値は catalog の enum から採る) | (port 呼び出しなし。テスト側の組み立て) | `details.field` の位置が、テストが組み立てた要求の実在の位置と一致する | (対応する既存条件なし = **本条件が足すもの**) | 拒否の `details.field` が指す位置を 1 段ずらす (例: `operations/0/values/x` を `values/x` にする) | **この段だけが赤** — C-21 は `details.field` の**形**しか見ておらず、位置の正しさを見ていない |
| (6) 直した要求に**段 (7) と同じ `idempotency_key` を付けて** `dry_run: true` で送る (**v0.2 改訂、設計レビュー 1 指摘 7 の裁定**) | `attempt_mutation_with_result(..., dry_run=True, idempotency_key=...)` (:2563) | `committed: false`、`affected`、`plan` が返り、**行が増えない**。**dry run 上の key は記録も照合もされないので、段 (7) の実送信が「最初の実送信」であり続ける** (`spec/data-service-api.v1.json`:710) | C-22 | `dry_run` 分岐を外して実行してしまう (`committed: true` を返す) | **同時に赤** (C-22) |
| (7) **段 (6) が返した `plan` をそのまま提示して**、同じ要求に同じ `idempotency_key` を付けて実送信 (**v0.2 改訂、設計レビュー 1 指摘 7 の裁定**) | `attempt_mutation_with_result(..., idempotency_key=..., plan=...)` (:2563) | `committed: true`、`request_id` を持つ。**`plan` 不一致による `PRECONDITION_FAILED` / `violated_declaration: plan` が起きない** (段 (6) と段 (7) の要求は `dry_run` 以外のすべてのフィールドで同一である。同:711) | C-22・C-23・C-25 | **`plan` の digest に `dry_run` を含める** (段 (6) の token が段 (7) で必ず不一致になる)。**v0.3 改訂 (2026-09-24、設計レビュー 2 指摘 8 の裁定 = 採用)**: v0.2 の「成功結果から `request_id` を落とす」は **C-25 が既に持つ変異**であり、この段が足したものを隔離しない | **同時に赤** (C-22)。**この段の期待は「plan 不一致が起きない」という否定形なので、peer を緩める変異では赤にならない** — **厳しくする変異でしか赤にできない** |
| (8) 同 key 同 body で再送 | 同上 (同じ引数) | **同じ `request_id`** が返り、**行数が増えない** | C-23・C-27 | 再送時に idempotency の記録を無視して再実行する | **同時に赤** (C-23) |
| (9) baseline の各演算子で query (`order_by`・**`page.size`**・**`budget`** 付き) (**v0.2 改訂、設計レビュー 1 指摘 1・6・10 の裁定**) | `attempt_filter(...)` (:2113) / `select_eq(..., limit=...)` (:2094) + **`order_by` と `budget` を運ぶ port (不足。下の開示事項)** | 各演算子が期待どおりの部分集合を返し、`order_by` の順序で並ぶ。**`budget` を付けても受理されて行が返る** (床 (i) の観測。狭める側は C-24 が持つ)。**v0.3 改訂 (設計レビュー 2 指摘 4 の裁定)**: **返る行数 R ≤ `page.size` S ≤ `budget.result_items` B ≤ 宣言 `limits.result_items` (capability document から読む。固定リテラルを書かない)** を満たす組み方にする — **MitateDB は `result_items` を要求された `limit` (= `page.size`) で判定する** (`MitateDB-api/src/mitatedb_api/cell.py`:2125-2129・:2137) ので、v0.2 の「返る行数以上」だけでは**片 peer だけが `LIMIT_EXCEEDED` になる**。**sort key は entity 内で一意な値にし、tie を作らない** — r2db は `order_by` に `id` の tie-break を自動で足すが (`r2db-api/src/r2db_api/paging.py`:83-90)、MitateDB にはその概念が無く (`MitateDB-api/src/mitatedb_api/cell.py`:3147 の `_bind_order_by`)、**tie があると順序が peer 間で割れる** | C-03・C-05・C-12・C-24 | `in` 演算子を `CAPABILITY_UNSUPPORTED` で拒否する (あるいは `order_by` を無視する) / **`budget` を `CAPABILITY_UNSUPPORTED` で拒否する** (v0.2 追加、指摘 6 の裁定) | **`order_by` を無視する変異はこの段だけが赤** — `order_by` を運ぶ port が現存せず、既存条件が 1 つも見ていない。**`budget` 拒否は C-24 と、`in` 拒否は C-12 と同時に赤** |
| (10) 述語 `update` | `attempt_mutation_with_result(..., operation="update", where_field=..., where_value=...)` (:2563) | `affected` が述語に一致した件数と等しく、他の行が変わらない | C-12・C-17 | `where` を無視して全件を更新する | **同時に赤** (C-12 / C-17) |
| (11) 述語 `delete` (declare-and-echo) | `attempt_mutation_with_result(..., operation="delete", destructive=True, confirmation=...)` (:2563) | 確認なしは `DESTRUCTIVE_CONFIRMATION_REQUIRED` + 宣言、句の全文復唱で実行 | C-06 | 確認句の全文一致を存在チェックに緩める | **同時に赤** (C-06) |
| (12) 最終 query で状態を確認 | `select_eq(...)` (:2094) | 残る行が (7)(10)(11) の帰結と一致する | C-12 | `delete` が `affected` を返すのに行を消さない | **同時に赤** (C-12) |

### 7.1 起草時点で判明している port の不足 (実装前に監督へ上げる。§1.5 の 37)

1. **`order_by` を運ぶ port method が 1 つも無い** (実測: `conformance-tests/adapter.py` に `order_by` の keyword 引数は存在せず、:2155 のコメントに語が現れるのみ)。**段 (9) には port 追加 (v1.16 相当) が要る見込みである。** `select_eq` は `limit` (= `page.size`) を持つ (:2094、port v1.12)。**§12 の裁定 2 (v0.2 で本文に反映)**: **`order_by` は baseline に残す** (両 peer が実装している: `r2db-api/src/r2db_api/backend.py`:62・`r2db-api/src/r2db_api/http.py`:468、`MitateDB-api/src/mitatedb_api/backend.py`:338・`MitateDB-api/src/mitatedb_api/backend_postgres.py`:1397)。**WP-2 で port v1.16 として `order_by` を運ぶ query method を 1 つ足す** (**v0.3 註、設計レビュー 2 指摘 10 の裁定**: **C-29 の `operation_catalog_document()` は WP-3 の port v1.17 であり、版数を分ける**) — **既存 `select_eq` の拡張ではなく新 method**であり、**同名 helper を両 peer の adapter に置くなら同型性テストの対象**である。**これは設計外の port 追加ではなく、本裁定により設計内である。** **v0.2 註**: 下の 4 も参照 — 段 (9) は `page.size` と `budget` も同じ要求で運ぶ (設計レビュー 1 指摘 6 の裁定)。
2. **宣言された `operation_catalog_url` を取得する port method が無い。** さらに **in-process plug には HTTP 面が無い。** **v0.2 改訂 (2026-09-24、設計レビュー 1 指摘 8 の裁定)**: **形は裁定済みである** — (i) **6 plug 全部**で、peer 自身が `operation_catalog` operation に対して返す本文を **新設 port method `operation_catalog_document()`** (**v0.3 改訂、設計レビュー 2 指摘 10 の裁定 = 採用: port v1.16 ではなく v1.17。WP-3 で足す**) で取り、`tools/contract_catalog.py` の生成物と **byte 一致**することを見る。(ii) **`transport_kind == "socket"` の plug では、宣言 URL を実 TCP で dial して同じ本文を得る** (非空: socket plug ≥ 1)。**in-process の 4 plug では宣言 URL が非 dial の placeholder のままでよく、その旨を C-29 行に開示する** (§6.4)。**宣言 URL が `surfaces.data.base_url` 配下であることは検査しない** (契約に無い性質を条件に入れない)。
3. 1 本の scenario 関数で **developer credential と runtime credential を使い分ける**形が既存の port (`authenticate` / `scope_of`) で足りるかを、実装前に確認する。
4. **段 (9) は `order_by`・`page.size`・`budget` を 1 つの query 要求で運ぶ port を要する** (**v0.2 追加、設計レビュー 1 指摘 6 の裁定**)。**実測**: `query_with_budget` (:2874、port v1.13) は `budget` を運ぶが **`order_by` も `page` も持たず、述語は eq 固定**である。`select_eq` (:2094) は `limit` (= `page.size`) を持つが `budget` を持たない。`attempt_filter` (:2113) は任意の演算子を運ぶが `limit` も `budget` も持たない。**したがって段 (9) の port 追加 (v1.16 相当) は、`order_by` と `page.size` と `budget` を同時に運ぶ 1 method として設計する見込みである** — **既存 3 method の置き換えではなく追加**とし、**形は実装前に監督へ上げる** (§1.5 の 37)。

---

## 8. Security Invariants との関係

**SI 列の具体値 (C-28 = SI-05 / SI-09 / SI-10 / SI-11 / SI-14、C-29 = SI-10) は起草担当の案であり、確定は依頼者裁定 §5 U-5 (`security/CONTROL_MAPPING.md` への追記) と同時である** (§12 の裁定 6。v0.2 で本文に反映)。

**新しい Security Invariant を足さない** (§2.2 の 4)。`CLAUDE.md`「Security Invariants are not a feature gate」のとおり、**SI は舗装とガードレールであって能力の許可リストではない** — baseline は「必ず実行できる操作の床」であり、新しい共通の安全性質ではないので、**新設の根拠が無い。**

### 8.1 C-28 (仮) の SI 列の根拠

| SI | 本条件が観測する性質 | 観測する段 |
|---|---|---|
| **SI-05** Validated Structured Operations | 宣言された `enum` / `nullable` が値検証の choke point で強制され、要求は述語と宣言された型を通してのみ組み立てられる (native command text を一度も通らない) | (2)(4)(9)(10) |
| **SI-09** Controlled Destructive Operations | 述語 `delete` が declare-and-echo を経なければ実行されない | (11) |
| **SI-10** Error and Information Non-Disclosure | 拒否の `details` が**位置と宣言された事実だけ**を返し、行値・推奨値・修正動作・内部名を返さない — **だからこそ段 (5) は catalog から修正値を採るしかない** | (4)(5) |
| **SI-11** Atomic Integrity | `dry_run` が外部可視の状態を変えず、同 key 同 body の再送が二度実行されない | (6)(7)(8) |
| **SI-14** Security-Relevant Auditability | **成功結果が `request_id` を持ち、再送が元の実行の `request_id` を返し、別の実行は別の値を持つ** (**監査証跡との突合は本条件の対象外であり、`audit_query` が使える場合に C-25 が持つ**) | (7)(8) |

**v0.2 改訂 (2026-09-24、設計レビュー 1 指摘 9 の裁定 = 採用)**: v0.1 の SI-14 行は「成功結果の `request_id` が同じ要求の**監査証跡と同じ識別子**であり」と書いていたが、**両 peer ともデータ面の `audit_query` は `unavailable`** であり (§1.3)、**C-28 は監査証跡を 1 度も見ない** — §8.1 自身が SI-15 を「観測しないものを列に書かない」として落としているのと同じ基準に反していた。**根拠を `conformance-tests/CONDITIONS.md` の C-25 行と同じ限定文言 (`request_id` の存在と相関まで。監査証跡との突合は「where `audit_query` is available」の条件付き) に揃えた。**

**SI-15 (Fail-Closed Authorization) は列に入れない** — C-28 (仮) の作業列には**認可拒否の脚が無い**ので、この条件は SI-15 の性質を観測しない。**観測しないものを列に書かない** (P-3 の趣旨: 宣言は真である)。**最終的な SI 列は、実装後にどの assert が実在するかを実測して確定する** (作業指示書の受入条件)。

### 8.2 C-29 (仮) の SI 列の根拠

**SI-10 のみ**を列に置く。配る派生カタログは**契約の派生物そのもの** (byte 一致) であり、**配備固有の情報を 1 バイトも含まない** — `spec/OPERATION_CATALOG.json` は 19 operation の 9 フィールドの索引である (§1.5)。**「配ることで新たに開示されるものが無い」ことが、この条件が守る安全上の性質である。** 逆向きに言えば、**byte 一致が破れた瞬間に「配備が独自の何かを混ぜた」可能性が立つ**ので、byte 一致の検査自体が SI-10 の証拠になる。

**v0.2 追加 (2026-09-24、設計レビュー 1 指摘 8 の裁定 = 一部採用)**: 配る path は **`GET /v1/capabilities` と同じ認証**を要求する operation (`operation_catalog`、`roles` = `runtime` / `developer`) であり、**無認証の面を新たに作らない** (D-5)。したがって —

- **SI-15 (Fail-Closed Authorization) は列に足さない。** 新しい pre-auth の面が立たないからである (無認証で配る案を採っていれば SI-15 の面が立った)。
- **SI-08 (Bounded Resource Consumption) も列に足さない。** 新しい operation は data surface の**既存の request-rate bound をそのまま受ける**が (`requests_per_minute` と `request_budget` の適用は既存の面と同じである)、**C-29 はその bound を観測しない** — §8.1 と同じ基準 (観測しないものを列に書かない) による。**bound そのものは C-05 / C-24 が持つ。**
- したがって **C-29 の SI 列は SI-10 のみのままである。**

### 8.3 `security/CONTROL_MAPPING.md` への証拠追記 (形式 3.0) と変更クラス

- **追記する形 (v0.3 改訂、2026-09-24、設計レビュー 2 指摘 11 の裁定 = 採用)**: 上の表の各 SI の **Common 節の Evidence** に、**テスト名を citation とする 1 行 (300 文字以内)** を足す。**`security/CONTROL_MAPPING.md` 冒頭の Version 行を 3.1 → 3.2 に上げ**、**`conformance-tests/test_control_mapping_register.py` が緑であることを WP-4 の完了条件にする。** **Control 主張は足さない** — 本項目は新しい施行箇所を作らない (baseline は既存の施行の上に立つ)。
  - **v0.2 の記述 (「各 SI の **peer 節**の Evidence 主張に足す」) を本版で改めた** (行は消していない。§1.8 の 56)。**理由**: (1) conformance 条件由来の証拠は **Common 節**に置かれている先例がある (SI-14 の Common 節の C-25 / C-26 の行: `security/CONTROL_MAPPING.md`:1746・:1750)。**C-28 / C-29 は両 peer を同じテストで見る**ので、peer 節と決め打つと先例と割れる。(2) v0.2 は **Version 行の更新規約**と、**citation を失った Evidence は Status 軸へ落ちる**という形式 3.0 の規約に触れていなかった (同:1-14 の Claim form)。
- **これにより変更クラスは D になる** (D-8)。**依頼者裁定の逐語は §5 U-5 に置く。**
- **SI の集合 (SI-00〜SI-15 の 16 件) は変わらない** — 計画文書 §0.1.1 の G-2 / G-3 行の SI 件数は更新しない。

---

## 9. 並走 (keyset ページング) との衝突回避

**別チャットで keyset ページングの項目が並走している** (計画文書 §5 フェーズ11 節の「keyset ページング (高速化案 7): **着手条件充足**」)。衝突しうるのは **(i) 契約版のラベル**、**(ii) 条件番号**、**(iii) 頁送りの意味**の 3 点である。

| # | 衝突の面 | 本項目の回避 |
|---|---|---|
| (i) | 契約版 1.9.0 のラベル | **merge 直前に main を読んで振る。先に merge した側が 1.9.0 である** (D-7)。本書は「1.9.0 (仮。merge 時に確定)」と書き、契約 JSON・`CCR_DISPOSITION.md` の従属判断番号・`version_binding` / `obligations` の entry・両 peer の宣言・契約版を固定するテスト・計画文書 G-2 / G-3 行を**同じ変更セットで**振り直す |
| (ii) | 条件番号 C-28 / C-29 | 同上。**`CONDITIONS.md` の行 ID・`@pytest.mark.condition(...)`・テストファイル名・`CONDITIONS_HISTORY.md` の anchor を同じ変更セットで振り直す** |
| (iii) | 頁送りの意味 | **現行方式で書く** (D-6)。`page.size` と `next_page` を使い、**結果集合を `page.size` 未満に保つ** — C-28 (仮) は頁をまたがないので、keyset 側が `next_page` の意味を変えても本条件の期待は動かない。**MitateDB は `next_page` を常に `None` で返す** (`MitateDB-api/src/mitatedb_api/cell.py`:3682-3689) ので、`next_page` の値そのものを判定材料にしない。**v0.2 追加 (2026-09-24、設計レビュー 1 指摘 1 の裁定 = 採用)**: **契約文の側でも閉じた** — **床に入るのは `page.size` だけ**であり、`page.cursor` と非 null の `next_page` が与える継続は `common_baseline.outside` に明記する (D-1 (e)、D-6、§6.1)。v0.1 は scenario の側 (結果集合を `page.size` 未満に保つ) だけで閉じており、**契約文が `page` を無限定に床へ入れていた** |

**触るファイルの重なり**: 本項目と keyset 側は、**契約 JSON・`conformance-tests/CONDITIONS.md`・両 peer の `capabilities_document.py`** で重なる見込みである。**したがって両者を並行 WP として同時に走らせない** — **どちらかが merge された後にもう一方が main を読み直して振り直す**、という直列化で扱う (`docs/work-orders/OPERATING_CONDITIONS.md` §1.2 の 16・17 が求める「重なり 0」を、本項目の内部 WP については §10 の表で示す)。

---

## 10. WP 分割の見込み

**本節は見込みであり、確定は作業指示書 (`docs/work-orders/WORK_ORDER_PHASE11_MIN_COMMON_PROFILE_V1.md`) で行う** (計画文書 §9 の 9: WP ごとの Change Set Manifest、完了条件 ↔ 変異の 1 対 1 表、触ってよい / 触らないパス、検証コマンド、変更クラス)。 **v1.0 (2026-09-24)**: **確定した** — 作業指示書 v1.0 が WP-1〜WP-4 を直列の Change Set Manifest として持つ。**本節の表は見込みとして残す** (§1.8 の 56)。

| WP | 内容 | 主に触るファイル (見込み) |
|---|---|---|
| **WP-1** | 契約 1.9.0 (仮): baseline 節 + `version_binding` / `obligations` + `operation_catalog_url` の扱い + `CCR_DISPOSITION.md` 従属判断 14 + `CONDITIONS.md` の C-28 / C-29 行 (declared)。**v0.2 追加 (設計レビュー 1 指摘 4・8 の裁定)**: **`endpoints` に operation `operation_catalog` を足し** (D-5)、その機械的帰結 — `spec/OPERATION_CATALOG.json` の**再生成** (19 → 20 operation) と `conformance-tests/test_operation_catalog_register.py`:117 の件数 assert の更新 — を同じ変更セットに含める。**`conformance-tests/test_contract.py`:1189 / :1301 の 1.7.0 逐語 pin の扱いは §5 U-4 の裁定で決まる** (§6.3 の註、§6.5)。**v0.3 追加 (設計レビュー 2 指摘 1・3・5・6・7 と回答項の裁定)**: (i) **`spec/CONTRACT_HISTORY.md` の `## versioning.version_binding` 節** (逐語 quote・従属判断 14・Introduced in・1.9.0 の Revision note) を**同じ変更セットで**更新する (§6.5)。(ii) **`conformance-tests/CONDITIONS_HISTORY.md` に `## C-28` / `## C-29` の節を新設**し、C-29 行に `[history]` リンクを置く。(iii) **C-28 / C-29 行の `Status` 欄は `declared` で置き、`executable` で始めず、テスト名を書かない** (§6.4 の暫定文案)。(iv) **`endpoints.operation_catalog` entry (全文案 §6.6) と `schemas.OperationCatalogDocument` / `definitions.OperationCatalogEntry` を足す。** (v) **`capability_status.rules` の 6 番目の要素**と `conformance-tests/test_contract.py`:164-166 の `len(rules)` 更新 (§6.1、§6.5) | 契約 JSON 3 複製、`spec/`、`spec/OPERATION_CATALOG.json`、**`spec/CONTRACT_HISTORY.md`**、`spec/CCR_DISPOSITION.md`、`conformance-tests/CONDITIONS.md`、**`conformance-tests/CONDITIONS_HISTORY.md`**、`conformance-tests/test_operation_catalog_register.py`、`conformance-tests/test_contract.py` |
| **WP-2** | C-28 (仮) の scenario 実装 (両 peer で緑)。**port v1.16 として `order_by`・`page.size`・`budget` を運ぶ query method を 1 つ新設する** (既存 method の拡張ではない。§12 の裁定 2、§7.1 の 1・4)。**同名 helper を両 peer の adapter に置くなら同型性テストの対象である**。**v0.3 追加 (設計レビュー 2 指摘 3 の裁定)**: **C-28 行の `Status` 欄を最終形に書き換え**、旧文を `CONDITIONS_HISTORY.md` の `## C-28` 節に逐語で残す | `conformance-tests/test_c28_*.py`、`conformance-tests/adapter.py` (port **v1.16**)、各 peer の `conformance/` adapter、`conformance-tests/CONDITIONS.md`、`conformance-tests/CONDITIONS_HISTORY.md` |
| **WP-3** | 両 peer の 1.9.0 宣言 + `operation_catalog_url` の宣言と配布 + C-29 (仮) を executable に (**宣言と挙動は同一コミット**、§1.1 の 11)。**v0.2 追加 (設計レビュー 1 指摘 3・8 の裁定)**: **派生カタログ `OPERATION_CATALOG.json` を両 peer の `contract/` に同梱して 3 複製にし**、`conformance-tests/test_operation_catalog_register.py` の**再生成一致テストを 3 複製比較に拡張する**。**`operation_catalog` endpoint を足した帰結 (同ファイル :117 の「19 件」の assert と `spec/OPERATION_CATALOG.json` の再生成) は WP-1 と同じ変更セットに属する** (§6.5)。**v0.3 追加 (設計レビュー 2 指摘 10・3 の裁定)**: **新設 port method `operation_catalog_document()` は port v1.17 である** (WP-2 の query method は v1.16。**版数を分ける**)。**C-29 行の `Status` 欄を最終形に書き換え**、旧文を `CONDITIONS_HISTORY.md` の `## C-29` 節に逐語で残す | 両 peer の `capabilities_document.py` / `http.py` / `contract/OPERATION_CATALOG.json`、**`conformance-tests/adapter.py` (port v1.17)**、**両 peer の `conformance/` adapter**、`conformance-tests/test_c29_*.py`、`conformance-tests/test_operation_catalog_register.py`、`conformance-tests/CONDITIONS.md`、`conformance-tests/CONDITIONS_HISTORY.md` |
| **WP-4** | 記録: 計画文書の R-29 / R-16 / R-23 行、G-2 / G-3 行、`security/CONTROL_MAPPING.md`、引き継ぎ書。**v0.3 追加 (設計レビュー 2 指摘 11 の裁定)**: **Common 節の Evidence に 1 行 (テスト名 citation、300 文字以内) を足し、Version 行を 3.1 → 3.2 に上げ、`conformance-tests/test_control_mapping_register.py` が緑であることを完了条件にする** (§8.3) | `docs/design/ROADMAP_POST_PHASE7_V1.md`、`security/CONTROL_MAPPING.md`、`docs/work-orders/HANDOVER_*.md` |

- **§5 U-3 が (c) と裁定されれば、WP-3 と WP-4 の間に参照クライアントの WP を挟む。** **v1.0 (2026-09-24、依頼者裁定 U-3 = 「(a) 最小形 + (c) を別起票」)**: **挟まない。** 参照クライアントは §16 の起票 (3) である。
- **WP-1〜WP-4 は直列である** (WP-1 が契約と条件行を置き、WP-2 / WP-3 がそれを load-bearing にする)。**並行 WP を置く場合は、触るファイルの重なりが 0 であることを作業指示書の表と実ファイル名で示す** (§1.2 の 16・17)。**現時点では WP-2 と WP-3 が `conformance-tests/adapter.py` と両 peer の `conformance/` adapter で重なるので、並行にしない。** (**v0.3 改訂、2026-09-24、設計レビュー 2 指摘 10 の裁定**: v0.2 は重なりを本文でだけ述べ、**表の「主に触るファイル」列が示していなかった** — §1.2 の 16・17 が求める重なりの明示になっていなかった。**上の表に両 WP の adapter を書き、port 版数を v1.16 / v1.17 に分けた。**)
- **本書は WP-1 と同一変更セットでコミットする** (§12 の裁定 4。v0.2 で本文に反映) — `tools/check_doc_refs.py` は C-28 / C-29 (仮) への参照を**行が存在しないうちは dangling と判定する**ので、**本書単独ではコミットできない**。**設計レビューと依頼者裁定は未コミットの worktree 上で行い、番号と版は merge 直前に main を読んで振り直す** (D-7、§9)。
- **機械的に随伴するもの** (作業指示書で完了条件に落とす): `conformance-tests/README.md` の `COLLECTION_FLOOR` の更新 (新規テストの収集件数。**完了ゲートで監督が更新する**、同 README:164-187)、`tools/dev/gate.py` の集計行、`tools/change_class.py` の実測分類行。

---

## 11. honest scope — 本設計が満たさないもの

- **Mitate の実需 (§1.6) は、本設計だけでは満たされない。** `solutionName` の一意性、`revision_preconditions`、append-only の保存側強制は、いずれも **MitateDB の機能の床**に依るものであり、**現物の交差 (D-1) を固定しても 1 つも解決しない。** 満たすには **§5 U-2 の (ii)**、または計画文書 **R-49** と `row_addressability` / `revision_preconditions` の MitateDB 実装の新規起票が要る。**「baseline を固定したので実需に応えた」とは書かない。** **v1.0 (2026-09-24、依頼者裁定 U-2 = 「(i) 現物の交差 + 床上げは別起票」)**: **本項目では満たされないことが確定した。** 足りない分は **§16 の起票 (1)(2)** と計画文書 **R-49** が持つ。
- **`append_only` (mutation class の実装) は本設計の範囲外である。** 計画文書 R-49 のままであり、本設計はその着手条件を変えない。**v0.2 追加 (2026-09-24、設計レビュー 1 指摘 2 の裁定 = 採用)**: v0.1 の §6.1 の `rule` には但し書きが無く、**そのままでは R-49 を契約上実装不能にしていた** — `row_addressability` を provide する peer が `append_only` / `append_delete` / `read_only` の entity を 1 つ宣言した瞬間、`mutation_classes.rule` (`spec/data-service-api.v1.json`:680) と `upsert` の規則 (同:695) が命じる `CAPABILITY_UNSUPPORTED` と、床の「`CAPABILITY_UNSUPPORTED` を返さない」が正面から衝突するためである。**§6.1 の `rule` に加えた但し書き (床は配備が提供する操作の床であり、entity ごとの宣言は `mutation_classes.rule` が決める) により、R-49 は契約上実装可能なままである。** なお R-49 は **§1.6 の Mitate の実需そのもの** (append-only の保存側強制) に直結する。
- **参照クライアントは本設計に含まれない** (§5 U-3 の (c) が採られない限り。**v1.0 (2026-09-24)**: **依頼者裁定 U-3 により (c) は別起票であり、本設計には含まれないことが確定した** — §16 の起票 (3))。したがって **`spec/README.md`:5-9 の目標 (spec + base URL + key だけで使える) を実行可能な形で証明してはいない** — C-29 (仮) が示すのは「配る索引が契約の派生物と byte 一致であること」までである。
- **C-28 (仮) は port を経由する。** conformance の adapter は peer ごとの薄い層であり、**wire を直接叩くクライアントではない** — したがって **C-28 は「契約文書だけで要求を組み立てられること」の証明ではない。** その証明は U-3 (c) の参照クライアントだけが与える。**「scenario が緑だから文書は十分である」とは書かない。**
- **C-28 (仮) の 12 段のうち、既存条件から隔離されて赤になる段は多くない** (**v0.3 追加、2026-09-24、設計レビュー 2 指摘 8 の裁定 = 採用**)。**起草時点の見込み**: **段 (5) の `details.field` の位置** (C-21 は `field` の**形**しか見ない) と、**段 (9) の `order_by` の無視** (`order_by` を運ぶ port が現存せず、既存条件が 1 つも見ていない) の**2 つだけがこの条件単独で赤になり**、他の段の変異は既存条件 (C-06 / C-12 / C-20 / C-21 / C-22 / C-23 / C-24 / C-25) と**同時に赤になる** (§7 の「この段だけが赤か」列)。**したがって「R-16 の継ぎ目は `plan` である」とは書かない** — **C-22 が既に plan の有効性を 4 plug で固定している。** **C-28 が足すのは、(4) の拒否 → (5) の診断による修正 → (6) dry_run → (7) 実送信 → (8) 再送を、同一の要求体が通り抜けることである** (D-2)。**実測は作業指示書の「完了条件 ↔ 変異」表で行う** (§1.5 の 34、40)。
- **配る派生カタログは C-11 の応答 schema 逆検証の対象ではない** (**v0.3 追加、2026-09-24、設計レビュー 2 指摘 5 の裁定の開示**)。C-11 は対象 schema を**手で列挙**しており (`conformance-tests/test_c11_response_schema_conformance.py`:339-433)、**本設計は新設 `schemas.OperationCatalogDocument` をその列挙に足さない。** **配る文書を契約に縛るのは、C-29 の byte 一致と、同条件が `conformance-tests/schema_check.py` で行う schema 検証だけである** (§6.4、§6.6)。**C-11 に足す案は本設計の範囲外であり、必要なら別 WP である。**
- **baseline は現時点の交差である。** どちらかの peer が capability を落とせば、baseline は義務違反になる (それが D-4 の狙いである) が、**逆に「baseline があるから両 peer は永久に同じことができる」わけではない** — 交差の外の非対称 (§1.3 の 6 項目) は残り、エージェントはそこでは従来どおり宣言を読んで分岐する。
- **性能について本設計は何も主張しない。** C-28 (仮) は 12 段の往復を 1 テストで行うので**完了ゲートの壁時計を延ばす** — 延びた量は実測して記録する (P-8、計画文書 R-105 の教訓)。**目標値は先に置かない。**
- **本設計は実行検証されていない。** §7 の変異はすべて**候補**であり、port の不足 (§7.1) は実装前に監督へ上げる未解決事項である。

## 12. 起草時の疑義と監督裁定 (v0.1、2026-09-24)

起草担当が枠 (`frame-r29.md`、監督保管) に対して返した疑義 8 件と、設計レビュー前の監督裁定。裁定は本文を書き換えず、本節で上書きする (該当節には設計レビュー反映時に反映する)。

| # | 疑義 | 監督裁定 |
|---|---|---|
| 1 | capability キーは 13 ではなく 14 (`control_plane` を含む) | 14 が正。枠の 13 は誤記。本文どおり |
| 2 | `order_by` を運ぶ port method が無い (段 (9) は port 追加が前提) | baseline に `order_by` を残す (両 peer が実装: `r2db-api/src/r2db_api/backend.py:62`・`r2db-api/src/r2db_api/http.py:468`、`MitateDB-api/src/mitatedb_api/backend.py:338`・`backend_postgres.py:1397`)。WP-2 で port v1.16 として `order_by` を運ぶ query method を 1 つ足す (既存 `select_eq` の拡張ではなく新 method。同名 helper を両 peer の adapter に置くなら同型性テストの対象)。設計外の port 追加ではなく、本裁定で設計内とする |
| 3 | in-process plug に HTTP 面が無く、C-29 の「配る」が定まらない | C-19 の D-4 と同じ二段形: (i) 6 plug 全部で、宣言 `operation_catalog_url` が `surfaces.data.base_url` 配下の絶対 URL であること、および peer 自身がその path に対して返す本文 (port method `operation_catalog_document()`、新設) が `tools/contract_catalog.py` の生成物と byte 一致すること、(ii) `transport_kind == "socket"` の plug では宣言 URL を実 TCP で dial して同じ本文を得ること (非空: socket plug ≥ 1 を要求)。in-process の 4 plug は URL 文字列が非 dial の合成 placeholder のままでよく、その旨を C-29 行の honest limits に開示する。**v0.2 註 (2026-09-24)**: **本裁定の (i) は、設計レビュー 1 指摘 8 の裁定により書き換えた** — 「宣言 URL が `surfaces.data.base_url` 配下の絶対 URL であること」の検査は**外した** (契約に無い性質を条件に入れない)。**書き換え後の本文は §3 D-5 / §6.3 / §6.4 / §7.1 の 2 / §8.2 にある。行は消していない** (`docs/work-orders/OPERATING_CONDITIONS.md` §1.8 の 56) |
| 4 | `check_doc_refs.py` が C-28 / C-29 (仮) の参照を dangling と判定し、本書単独ではコミットできない | 本書は WP-1 (CONDITIONS.md に C-28 / C-29 の行を declared で足す) と同一変更セットでコミットする。設計レビューと依頼者裁定は未コミットの worktree 上で行う。番号は merge 直前に main を読んで振り直す (§0 の仮番号規約) |
| 5 | C-29 の declare-first と U-4 (α) 義務化は両立しない | U-4 の裁定で決まる。両案の書き分け (§6) のままレビューに出す。(α) なら C-29 は分岐なし (1.9.0 宣言 peer は必ず宣言する)、(β) なら declare-first |
| 6 | SI 列の具体値 (C-28 = SI-05/09/10/11/14、C-29 = SI-10) は起草担当の案 | 案のまま設計レビューの対象にする。確定は依頼者裁定 U-5 (CONTROL_MAPPING への追記) と同時 |
| 7 | X-4 は却下ではなく U-2 送り | 註のとおり。X-4 は「却下案の節に置いた U-2 の参照」として残す |
| 8 | `CCR_DISPOSITION.md` の従属判断 14 の新設 | 1.8.0 = 13 の慣行どおり新設する (機械的帰結)。文言は WP-1 |

---

## 13. 設計レビュー 1 の反映 (v0.2、2026-09-24)

**設計レビュー 1 回目 (重い順に 11 件の指摘) に対する監督裁定を、以下に逐語で置く。** **裁定は再審議しない。** 「反映先」の列が、本文のどこを書き換えたかの索引である — **書き換えた各箇所には `v0.2` の註と日付と裁定番号を残してあり、v0.1 の判定は消していない** (`docs/work-orders/OPERATING_CONDITIONS.md` §1.8 の 56)。**§12 (v0.1 の起草時疑義と監督裁定) は残し、裁定 3 の行には書き換えの註を足した。**

| # | 裁定 | 反映先 |
|---|---|---|
| 1 | 採用。床の paging は `page.size` のみ。`outside` に `page.cursor` と `next_page` による継続を明記 (keyset 並走の契約面の切り分けにもなる) | D-1 (e)、§6.1 operations/outside、§7 段 (9)、§9 |
| 2 | 採用。§6.1 rule の末尾にレビューの文案 (floor は配備が提供する操作の床、row_addressability を提供する peer では `mutation_classes.rule` が entity ごとに決め、update/delete を支持しないクラスの entity は catalog から読める拒否として CAPABILITY_UNSUPPORTED のまま) を逐語で足す。§11 の R-49 行に「この但し書きにより R-49 は契約上実装可能なまま」と書く | §6.1、D-1、§11 |
| 3 | 採用 (i): 派生カタログ `OPERATION_CATALOG.json` を契約 JSON と同じ 3 複製 (spec + 両 peer の `contract/`) にし、「同一コミットで同一バイト」規律に載せ、`conformance-tests/test_operation_catalog_register.py` の再生成一致テストを 3 複製比較に拡張する。(ii) の peer ごと派生器は採らない (同型 helper が増え、P-7 の「再生成一致で正本に縛る」の方が単純)。D-5 の中黒は「生成器の正本は `tools/contract_catalog.py` のまま。配布物は 3 複製」に書き換える | D-5、§6.5、§10 WP-3 |
| 4 | 採用。§6.5 に `conformance-tests/test_contract.py`:1189 / :1301 の行を足す。(α) は当該文ごと置換なので pin を 1.9.0 の文言へ差し替える (版の文言を pin するテストは版上げの同一変更セットで新文言に移す — §1.5 の 35 は依頼者確定文の言い換え禁止であり、版の改訂は U-4 の依頼者裁定そのもの)。(β) は現行文を含んだまま追記し pin は緑のまま、`(D-8)` の裸参照は履歴として残す | §6.3 註、§6.5 |
| 5 | 採用 (3 点とも): §6.2 (1) にレビューの 1 文を逐語で足す / §6.1 に `capabilities` 配列 (8 名) を置く (契約側の一覧であり X-1 に当たらない旨を X-1 に註記) / (k)(l) を operations から外し rule 側の 1 文 (レビュー文案) で受ける | §6.1、§6.2、§4 X-1 |
| 6 | 採用 (前者): 段 (9) の query に `budget` (`result_items` を行数以上の値で) を付け、受理されて行が返ることを床 (i) の観測とする。狭める意味は C-24 に委ねる (C-28 は重複しない)。段 (9) だけを壊す変異候補に「budget を CAPABILITY_UNSUPPORTED で拒否する」を足す | D-2、§7 |
| 7 | 採用。段 (6) の dry_run にも段 (7) と同じ `idempotency_key` を付ける (契約 :710 が「記録も照合もしない」と明示) と、段 (7) で段 (6) の `plan` を提示することを D-2 と §7 に書く。plan の受け渡しが R-16 の継ぎ目であることを明記 | D-2、§7 段 (6)(7) |
| 8 | 一部採用。C-29 (i) から「`surfaces.data.base_url` 配下」の制約を外す (契約に無い性質を条件に入れない)。配る path は契約 `endpoints` に operation `operation_catalog` (GET、roles = data surface の credential (runtime / developer)、requires_capability なし) として載せる (派生カタログが自己言及の 20 件目を持つことを開示)。認証は `GET /v1/capabilities` と同じ (無認証面は作らない → SI-15 は不要、SI-08 は既存の request-rate bound がそのまま掛かる)。`operation_catalog_url` は「この配備でその operation に到達する絶対 URL」であり、CDN 等に置く配備はそこを宣言してよい。C-29 は宣言 URL を socket plug で実 dial、in-process plug は port method で同じ本文を得る (§12 裁定 3 の (i) を書き換え) | D-5、§6.3、§6.4 C-29 行、§8.2、§12 裁定 3 |
| 9 | 採用。§8.1 の SI-14 の根拠を C-25 行と同じ限定文言 (request_id の存在と相関、監査証跡は対象外) にする | §8.1 |
| 10 | 採用。§7 段 (9) に「sort key は一意 (一意でない列の tie は両 peer で順序が割れる: r2db は id tie-break、MitateDB は無し)」を足す | §7 |
| 11 | 観察 (本項目では直さない)。C-28 / C-29 行は `six adapters` と書く (凡例が `four adapters` = registry の全 adapter と定めている)。引き継ぎ書の裁定表に載せる | §6.4 (変更なし) |

加えて v0.2 で: §12 の監督裁定 1〜8 を本文に反映し (§12 は残す)、§13「設計レビュー 1 の反映」に上の表を逐語で置く。版数 v0.2 (2026-09-24)、改版履歴に「設計レビュー 1 の反映。既存の決定・裁定・却下は撤回していない」を書く。U-1〜U-5 は両論のまま (裁定欄は空のまま)。

**反映していない指摘 (開示)**: 上の 11 件に含まれない提案は反映していない — 具体的には、(1) レビュー「特に見てほしい点への回答」4 が提案した **C-29 の条件文の言い換え** (「the derived catalog this repository's spec generates, whose own `contract_version` equals the version the capability document declares」)、(2) 同 6 が提案した **`rule` への 3 文目** (「The floor names which operations exist; it does not promise any particular request succeeds ...」) である。**いずれも裁定表に無いため、本版では本文に入れていない** — 要否は設計レビュー 2 または監督裁定による。

**v0.3 での決着 (2026-09-24、設計レビュー 2 回答項の裁定)**: **(1) の C-29 条件文の言い換えは採用した** (§6.4。理由: `spec/OPERATION_CATALOG.json` は版別保管を持たない単一生成物であり、旧文は存在しない対象を指しうる)。**(2) の `rule` の 3 文目は足さない** (裁定どおり)。**あわせて `capability_status.rules` に 6 番目の規則を足す** (§6.1、§6.5)。

### 13.1 v0.2 起草時の疑義と監督裁定 (2026-09-24。設計レビュー 2 の対象)

| # | 疑義 | 監督裁定 |
|---|---|---|
| 1 | §6.1 の `capabilities` 配列に意味を結ぶ文が無い (無拘束の配列は P-3 に触れうる) | 3 文目は足さない。`rule` の既存句「and it declares no capability one of them needs as unavailable」を「and it declares none of the capabilities common_baseline.capabilities names as unavailable」に書き換える (配列が rule の主語になる)。**v0.3 註 (2026-09-24、設計レビュー 2 指摘 12 の裁定)**: **本裁定を §6.1 本文に反映した** (v0.2 は裁定だけがここにあり、本文は旧句のままだった) |
| 2 | 裁定 5 の逐語文は 8 capability を名指すが、既存 conditional 行が条件に置くのは 6 名 (`structured_query` / `atomic_mutation` を条件に持つ行は無い) | 8 名のまま (床が unavailable を禁じる capability の一覧であり、既存行の条件の一覧ではない)。§6.2 の実測註はそのまま残す |
| 3 | `operation_catalog` endpoint の `response` 欄に指すスキーマが無い | 契約 `definitions` に `OperationCatalog` (entry の 9 フィールド = `tools/contract_catalog.py` の投影と同じ) を新設し、`response` はそれを指す。派生物の形が契約に縛られ、C-11 の応答 schema 検査の対象にもなる (P-7)。WP-1 の項目。**v0.3 註 (2026-09-24、設計レビュー 2 指摘 5 の裁定 = 採用。裁定文は消していない)**: **本裁定の「`definitions` に `OperationCatalog` を新設し `response` がそれを指す」と「C-11 の対象にもなる」の 2 点は書き換えた** — 実測により、(1) `endpoints.*.response` が指す名前は**すべて top-level `schemas` の member** であり、(2) 配る文書の top-level は `{$comment, contract_version, operations}` なので entry の 9 フィールドでは応答を記述できず、(3) C-11 は対象 schema を**手で列挙**している。**書き換え後の本文は §6.6 (`schemas.OperationCatalogDocument` + `definitions.OperationCatalogEntry`) と §6.4 の C-29 行・§11 の開示にある** |
| 4 | 裁定 11 の「凡例が `four adapters` = 全 adapter」の出所 | 計画文書 §0.1.3 の G-2/G-3 行 (「`CONDITIONS.md`:58 の凡例により `four adapters` の語は `registry.json` の全 registered adapter (現在 6) を指す」) と `CONDITIONS.md` の C-27 行直後の凡例段落。結論は裁定どおり |
| 5 | 3 複製の新ファイルが package data / 配布設定に触れる要否 | WP-3 で実測する (契約 JSON の複製が既に package に載る設定を流用できるかを見る)。設計はこれ以上決めない |
| 6 | U-4 (β) のとき endpoint として契約に載ることと宣言 optional の併存 | 併存する: endpoint は「この path で配る」の定義、`operation_catalog_url` は「どの絶対 URL で到達するか」の宣言。(β) では宣言しない peer が endpoint を持たないことを許さない (endpoint は無条件)。U-4 の表にこの 1 行を足す。**v0.3 註 (2026-09-24、設計レビュー 2 指摘 6 の裁定 = 採用。裁定文は消していない)**: **「endpoint は無条件」は版ゲート付きの意味である** — endpoint entry の `semantics` に「`Served by an implementation declaring 1.9.0 or higher; an implementation declaring a lower version is not held to it.`」を置く (§6.6)。**これが無いと、契約 `endpoints` は 1.8.0 を宣言する既存配備を即座に非準拠にし、§6.2 (1) 自身の遡及禁止文と反する。** **U-4 の表の 1 行は v0.3 で足した** |

---

## 14. 設計レビュー 2 の反映 (v0.3、2026-09-24)

**設計レビュー 2 回目 (重い順に 12 件の指摘 + 回答項) に対する監督裁定を、以下に逐語で置く。** **裁定は再審議しない。** 「反映先」の列が、本文のどこを書き換えたかの索引である — **書き換えた各箇所には `v0.3` の註と日付と裁定番号を残してあり、v0.1 / v0.2 の判定は消していない** (`docs/work-orders/OPERATING_CONDITIONS.md` §1.8 の 56)。**§12 (v0.1 の起草時疑義と監督裁定)・§13 (設計レビュー 1 の反映)・§13.1 (v0.2 起草時の疑義と監督裁定) は残し、§13.1 の裁定 1・3・6 の行には書き換えの註を足した。**

| # | 裁定 | 反映先 |
|---|---|---|
| 1 | 採用。`spec/CONTRACT_HISTORY.md` の `## versioning.version_binding` 節の全文引用 (unstripped) と従属判断 14 行・`Introduced in:` 行を WP-1 の同一変更セットで更新する。§6.5 に 2 行、§10 WP-1 の触るファイルに追加 | §6.5、§10 |
| 2 | 採用 (a): 1.8.0 の先例どおり count 文 (`Two/One of those obligations ...`) を書かない。§6.2 (1) の散文から count 文を外し、義務は (a)(b) の列挙だけで述べる。pin (`len(prose_counts) == 3`) は触らない。(b) は却下案 X-7 として記す (regex 拡張と pin 更新の分だけ変更が増え、機械照合の対象版を広げる理由が無い) | §6.2、§4 |
| 3 | 採用。WP-1 は C-28 / C-29 行を `declared` の Status (`executable` で始めず、テスト名を書かない) で置き、`[history](CONDITIONS_HISTORY.md#c-28)` / `#c-29` リンクと `CONDITIONS_HISTORY.md` の `## C-28` / `## C-29` 節を同時に足す。WP-2 (C-28) / WP-3 (C-29) が Status を `executable` に書き換える | §6.4、§6.5、§10 |
| 4 | 採用。段 (9) の不等式 R ≤ `page.size` ≤ `budget.result_items` ≤ 宣言 `limits.result_items` (capability document から読む) を D-2・§7・§6.4 の C-28 行に固定する | D-2、§7、§6.4 |
| 5 | 採用。`schemas.OperationCatalogDocument` (top-level `{$comment, contract_version, operations}`) と `definitions.OperationCatalogEntry` (9 フィールド) に分ける。C-11 の手書き列挙には載せず、C-29 のテストが配られた文書を `schemas.OperationCatalogDocument` に対して `schema_check.py` で検証する。§11 に「C-11 の列挙に載せない」を開示 | §6、§6.4 C-29 行、§11 |
| 6 | 採用。endpoint entry の `semantics` に版ゲート 1 文 (`Served by an implementation declaring 1.9.0 or higher; an implementation declaring a lower version is not held to it.`) を置く。U-4 (β) でも endpoint は 1.9.0 宣言 peer に無条件、`operation_catalog_url` の宣言だけが optional | §6 entry、§5 U-4 |
| 7 | 採用。レビュー全文 §7 の entry JSON 案を §6 に置く (method GET、roles runtime/developer、auth = data surface の bearer application credential、requires_capability []、atomicity none、request なし、response OperationCatalogDocument、destructive false) | §6 |
| 8 | 採用。段 (7) の変異候補を「plan の digest に `dry_run` を含める」に差し替え、§7 に「この段だけが赤か」列を足し、他条件と同時に赤になる段はその旨を書く。D-2 / §11 の継ぎ目主張を「C-22 が plan の有効性を 4 plug で固定済み。C-28 が足すのは (4)→(5) の診断による修正と (5)→(8) が同一要求体であること」に弱める | §7、D-2、§11 |
| 9 | 採用。rule の partial 節に credential 句 (レビュー全文 §9 の文案) を足す。§7 段 (1) に「`operations` の非空を assert しない」註 | §6.1、§7 |
| 10 | 採用。WP-3 の触るファイルに `conformance-tests/adapter.py` と両 peer の conformance adapter を足し、port 版数を WP-2 = v1.16、WP-3 = v1.17 に分ける | §10、§7.1 |
| 11 | 採用。CONTROL_MAPPING への追記は先例どおり Common 節、Version 3.1 → 3.2、`test_control_mapping_register.py` 緑を完了条件に | §8.3、§10 WP-4 |
| 12 | 採用。§13.1 裁定 1 の句を §6.1 本文に反映 | §6.1 |
| 回答 | C-29 条件文の言い換え (版別保管が無い) を採用。rule の 3 文目は足さない。`capability_status.rules` に 6 番目の規則 (「optional とは common_baseline の外を指す」の 1 文、英文はレビュー全文の案か起草担当の案) を足し、`test_contract.py`:164-166 の `len(rules) == 5` を 6 に更新する行を §6.5 に足す | §6.1、§6.4、§6.5 |

v0.3 (2026-09-24): 改版履歴に「設計レビュー 2 の反映。既存の決定・裁定・却下は撤回していない」。§14「設計レビュー 2 の反映」に上の表を逐語で置く。U-1〜U-5 は両論のまま、裁定欄は空のまま。

**本版で新設した節・行**: §4 **X-7** (却下案。裁定 2 の (b))、§6.6 (endpoint entry と応答 schema)、§6.1 の `capability_status.rules` 6 番目、§6.4 の暫定 `Status` 欄、§6.5 の 5 行、§7 の「この段だけが赤か」列、§11 の 2 中黒、§5 U-4 の 1 行。**却下した案は 1 件も撤回していない。**

**起草時の開示 (§1.5 の 37、本版で監督へ上げるもの)**: (1) `capability_status.rules` に 6 番目を足すと、`conformance-tests/test_contract.py` の `rules[-1] == FIXED_1_8_0_CAPABILITY_STATUS_RULE` (1.8.0 の監督確定文を**末尾**で見る assert) に当たる — **新要素を 1.8.0 の文の前に置くか、pin を index 比較に改めるかは本書の裁定に含まれていない。** (2) `CONDITIONS.md` の **Evidence 欄**に未作成のテストファイル名を書けるか (C-27 の declared 期の `(not yet created)` が許容形か) は **WP-1 で実測する。** (3) §6.6 の 2 つの新 schema が 1.2.0 の「closed」列挙に名指しで載る必要があるかは **WP-1 で実測する。**

---

## 15. v0.3 の疑義と監督裁定 (v1.0、2026-09-24)

**v0.3 の起草時に監督へ上げた疑義 5 件と、その監督裁定を以下に逐語で置く** (`docs/work-orders/OPERATING_CONDITIONS.md` §1.5 の 37)。**裁定は再審議しない。** **疑義の本文は起草報告 (監督保管) にあり、本書には写さない** — 下の「疑義」列は裁定が指している対象を同定できる範囲で書いた索引である。

| # | 疑義 (対象の同定) | 監督裁定 (逐語) | 反映先 |
|---|---|---|---|
| 1 | v0.3 の起草報告で上げた**根拠の訂正** (本書の操作面には影響しない) | 採用 (起草担当の根拠の訂正のとおり。操作面は変わらない) | 本文の操作は不変 (反映箇所なし) |
| 2 | §14 末尾の開示 (1) — `capability_status.rules` に 6 番目を足すと `conformance-tests/test_contract.py` の `rules[-1] == FIXED_1_8_0_CAPABILITY_STATUS_RULE` (末尾比較) に当たる | 6 番目の規則は末尾に追加する (時系列順を保つ)。`conformance-tests/test_contract.py`:167 の pin は `rules[-1]` から `rules[4]` (index 固定) に改め、1.8.0 の確定文そのものは 1 文字も変えない。`len(rules) == 6`。§6.5 の行に書く | §6.1、§6.5 |
| 3 | §14 末尾の開示 (2) — `CONDITIONS.md` の Evidence 欄に未作成のテストファイル名を書けるか (`conformance-tests/test_conditions_register.py` の参照解決) | C-27 の declared 期の先例に合わせる: Evidence 欄にファイル名を `(not yet created)` 付きで書く。WP-1 で参照解決の検査 (:702-717) が緑であることを完了条件にする。**【v1.1 訂正 2026-09-24 (WP-1 実測、作業指示書 §7.1 訂正註 2)】** 現行の `test_conditions_register.py` は backtick 付きの未作成ファイル名を `file not found`、backtick 無しを naked token で赤にするため、declared 期の Evidence 欄にはファイル名を書かない (散文で証拠の形を書く)。C-26 / C-27 の先例は参照解決の検査 (main 2365955) 以前のもの | §6.4、作業指示書 §2 |
| 4 | §14 末尾の開示 (3) — §6.6 の新設 2 schema が 1.2.0 の「closed」の列挙に載る必要があるか | 2 schema は閉じた形 (`additionalProperties: false`) で書き、1.2.0 の closed 列挙に載せる (載せないと列挙が「全 schema」でなくなる)。WP-1 で列挙の検査テストの緑を完了条件にする。**【v1.1 訂正 2026-09-24 (WP-1 実測、作業指示書 §7.1 訂正註 3)】** 7(A) の列挙を読む機械検査は存在しない (実測)。完了条件 8 は監査照合 (`spec/CCR_DISPOSITION.md` の 7(A) 行と契約 JSON の `additionalProperties: false` の行を報告と §17 に記す)。動的な効力は WP-3 の O6 が持つ | §6.6、作業指示書 §2 |
| 5 | §6 の条件付き註 (U-1 が (β) なら `capability_status.rules` の 6 番目を置かない 等) の扱い | U-1 = (α) で裁定された (依頼者裁定 2026-09-24)。条件付き註は「(α) で確定」に書き換え、(β) の分岐文は §5 の表にだけ残す | §6.1、§6.2、§6.3、§6.4、§5 |

**註 (裁定 2 の位置)**: 裁定文は `conformance-tests/test_contract.py`:167 と書く。**起草時の実測では、末尾比較の assert は同ファイル :168、`len(rules) == 5` は :165 である** — 行番号は着手時に再実測する (作業指示書 §2)。**裁定の内容 (index 固定に改める、1.8.0 の確定文は変えない、`len(rules) == 6`) は動かさない。**

---

## 16. 起票する項目 (v1.0、2026-09-24)

**依頼者裁定 U-2 / U-3 の帰結として、3 件を新規起票する。** **番号は merge 直前に main の計画文書 `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 を読んで振る** (D-7 と同じ規律)。**規模は監督が決めた (3 件とも L)。** **本設計はこの 3 件を実装しない。**

| # | 内容 (1 行) | 規模 | 規模の理由 | 着手条件 |
|---|---|---|---|---|
| (1) | **MitateDB-api に `row_addressability` (mutation class と住所指定) を実装する** — 宣言を `unavailable` から動かし、entity ごとの mutation class と行の住所を契約の語彙どおり持たせる | **L** | 宣言値と保存形の両方に触れ (P-3 により最低 Class C)、契約 `structured_operations.mutation_classes` の規則 (`row_addressability` が enabled のとき entity ごとに 1 クラス) と `upsert` の規則が同時に効くので、設計レビューを要する。計画文書 **R-49** (mutation class の実装) と論点を共有する | **Mitate の実需** (§1.6 の逐語 (1)(2): `append_only` への対応付けが「両 peer に実装が無い」「本番 peer は `row_addressability: unavailable` で宣言自体が成り立たない」)。依頼者裁定 U-2 の「MitateDB に row_addressability / revision_preconditions を足す新規起票 2 件 + 既存 R-49 に付け替える」 |
| (2) | **MitateDB-api に `revision_preconditions` (`expected_revision`) を実装する** — 宣言を `unavailable` から動かし、revision の保持と precondition の判定を持たせる | **L** | 同上 (宣言値 + 保存形 + 契約の意味論)。複数 instance 化の前提であり、計画文書 **R-102** (application ごとの直列化) と干渉しうる | **Mitate の実需** (§1.6 の逐語 (3)(4): solutionName の一意性は「`row_addressability`/unique 制約が unavailable のため Data Service では守れない」、§12 の (g) 行「`revision_preconditions`(§2.C.7。複数 instance 化の前提。DM-0025)」は「**未着手**」)。依頼者裁定 U-2 (同上) |
| (3) | **参照クライアント** — spec と base URL と API key だけから要求を組み立てる共通コードを `conformance-tests/` に 1 本置き、C-28 の作業列を wire plug (http ×2、socket ×2) に対して回す | **L** | peer 側 adapter を通らない新しい層を作り、契約文書だけで要求が組めることを実行可能な形で固定する。既存 port の外に出るので設計レビューを要する | **R-23 の目標** (`spec/README.md`:5-9 の逐語目標「The target is that an AI agent can use either implementation from: 1. this API specification, 2. a base URL, and 3. an authorized API key.」) の**実行可能な証明**。依頼者裁定 U-3 の「参照クライアント … は次の項目として起票」 |

- **(1)(2) は本設計の honest scope (§11) が「満たさない」と書いたものを引き取る項目である。** 本設計の C-28 / C-29 はこの 3 件の着手を前提にしない。
- **(3) が着地するまで、`spec/README.md`:5-9 の目標は実行可能な形で証明されていない** (§11)。

---

## 17. 実施記録 (統合時に監督が埋める)

**本節は空欄で作る。** 作業指示書 `docs/work-orders/WORK_ORDER_PHASE11_MIN_COMMON_PROFILE_V1.md` の WP-4 が、以下を本節に写すことを完了条件に持つ (§1.5 の 40 の「監査照合」の照合対象の逐語記録)。

| 項目 | 記録 |
|---|---|
| 確定した契約版 | (merge 直前に main を読んで確定。1.9.0 (仮)) |
| 確定した条件番号 | (同上。C-28 / C-29 (仮)) |
| WP-1 の commit と pt の集計行 | |
| WP-2 の commit と pt の集計行、変異表 (完了条件 ↔ 変異の実測) | |
| WP-3 の commit と pt の集計行、変異表 | |
| 完了ゲートの集計行 (監督単独、`tools/dev/gate.py`) | (前 = `4022 passed, 2 subtests passed in 486.51s`、label r105b) |
| 性能差分 (P-8) | (C-28 / C-29 が加わった分の壁時計の増分。目標値は置かない。§11) |
| `tools/change_class.py` の実測分類行 | |
| 起票した 3 件の番号 (§16) | |
