# フェーズ7 以降の計画 (Roadmap) v1

- 版数: **v1.0 (2026-09-06)**。外部提案 2 本の評価と依頼者の目標宣言を受けて起草。
- 起草: Fable (監督)。依頼者の目標 (§0) は逐語。判定 (§3, §6) は本会話での監督評価であり、各フェーズの設計文書で再審議してよい。
- 位置づけ: 本書は **計画文書**であり、`CLAUDE.md` の source-of-truth 順位には入らない。各フェーズの正本は、そのフェーズの設計文書 (`docs/design/PHASE*_V1.md`) と作業指示書である。本書はそれらの**着手順・範囲・着手条件・守るべき条件**を先に固定し、次フェーズの設計起草者が「何を、なぜ、どの順で」を再導出せずに済むようにする。
- 前提となる main: `a8353fe` (フェーズ7 WP-7 マージ後。gate 2265 passed / 9 xfailed)。

---

## 0. 依頼者の目標 (2026-09-06、逐語)

> 私が望むのは、このリポジトリ成果物が、AI(エージェント)にとってのベストなDBプラットフォームになることです(人を拒絶するわけではない)。それは、人からみて、比類なきセキュリテイ・信頼性を備えていることです(パフォーマンスが高いことは大前提)。

本書はこれを 4 つの要求に分解して扱う。

| 記号 | 要求 | 本書での扱い |
|---|---|---|
| **G-1** | AI エージェントにとって最良の DB プラットフォーム | エージェントの 1 周 (§4 P-2) を閉じることを最優先にする。人間の利用を排除しない (機械可読と人間可読を両立する) |
| **G-2** | 人から見て比類なきセキュリティ | Security Invariants と conformance による**証明可能性**を維持し、宣言した bound が全 peer で実効であること (§5 フェーズ8) |
| **G-3** | 比類なき信頼性 | 1 要求 = 1 原子単位、再送安全性 (idempotency)、宣言が真であること (§4 P-1〜P-3) |
| **G-4** | 高性能は大前提 | **現時点で計測が存在しない** (§7)。フェーズ8 で基準値を取り、以後は各フェーズが差分を記録する |

既存の設計原則 (2026-09-02: 先送りしない・シンプル・制約で回避しない・誇れる成果物) と、契約の前提 (利用設計者は AI エージェントであり、宣言は読まれる) は本書全体に適用する。

---

## 1. 現状 (2026-09-06)

- **契約**: 1.6.0。能力 11 種、error code 17 種、limit class 16 種、共通条件 C-00〜C-19 の 20 件は**全件が共通 suite で実行可能** (four adapters)。
- **フェーズ7**: 7-A (WP-1〜3) と 7-B の WP-4〜7 は main マージ済み。**残るのは WP-8 (記録・第 14 次引き継ぎ) と WP-9 (公開ゲート。着手条件は依頼者の実行合図のみ)**。
- **台帳の最優先候補**: **L7-1** (MitateDB application plane の `execution_ms` / `concurrency` / `requests_per_minute` の実 enforcement + concurrency probe の port primitive)。C-05 V3 の `xfail(strict=True)` 9 件が撤去の合図。
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
| II-11 bulk ingest/export | `best_effort_transactions` (契約済み未実装) | resumable upload は往復をまたぐ状態 (P-1) に当たるので不可。chunk 単位の原子性のみ |
| II-6 migration planner | R-2 の制約宣言と R-4 の dry_run の後 | desired-state 差分。breaking 分類は契約に無い概念 |
| I-B / II-12 entity 横断照会・関係モデル | CCR-15 と同型の `ScopedQueryRequest` は小さい。**関係モデルは 2.0 級** | subgraph fetch は関係モデルが先 |
| II-8 snapshot/clone | data plane の sandbox は却下 (§6)。**control plane の application lifecycle (snapshot から新 Application)** なら SI-01 に乗る | 優先度低 |
| II-9 query explain | CCR-01 の「表現力不足の実証」 | SQLite / PostgreSQL / in-memory で planner が異なり、共通の意味を持たせられない |

保留項目は**再提案を歓迎する**。着手条件は「公開後の実利用で、現行契約では表現できない要求が記録されたこと」(CCR-01 の再検討条件) とし、記録の置き場は本書 §8 の台帳とする。

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

- **WP-8** 記録・第 14 次引き継ぎ。**本書への参照を引き継ぎに載せる。**
- **WP-9** 公開ゲート。着手条件は依頼者の実行合図のみ (L7-12 状態注記)。**公開は G-2 の「人から見て」を成立させる前提**であり、フェーズ8 以降のどの機能よりも先に価値を生む。フェーズ8 の着手を WP-9 の完了に**依存させない** (触るファイルが重ならない) が、順序としては WP-9 を先に置くことを推奨する。

### フェーズ8 — 実効 bound と基盤衛生 (契約変更なし)

- **目的**: G-2 と G-4 の土台。宣言した bound が全 peer で実効であること、以後の契約改版に耐える計測と検知を置くこと。
- **着手条件**: WP-8 完了 (7-B の記録が閉じていること)。WP-9 との並行可。
- **範囲**:
  - **L7-1** MitateDB application plane の `execution_ms` / `concurrency` / `requests_per_minute` の実 enforcement (`operation_depth` と in-process `request_bytes` は WP-4 の実測に従い副項目) + port への in-flight 保持 primitive + C-05 V3 xfail の class ごとの撤去。
  - **R-9** CI のテスト総数下限 (前回 main の `--collect-only` 件数を下限とし、減少は明示の更新なしに赤)。
  - **R-10** 契約 JSON の現行/履歴分離。WP-7 の companion 方式 (`*_HISTORY.md`、ID ごとの anchor、register テスト) を `spec/` に適用。**契約の意味は 1 文字も変えない** (1.6.0 のまま)。分離の検査は「現行 JSON から経緯マーカーが消えたこと」と「companion に逐語で残ること」。
  - **R-11** r2db 運用項目: deployment smoke test (provision 後に capabilities / catalog / 1 query を実打ちして終了コードで返す。L7-18 の `ops verify-declarations` を同梱)、backup/restore の手順と実証記録、ops CLI の引数に secret を取る経路の検査。
  - **R-12** 性能基準値: 両 peer × 4 plug に対する query / mutate / cross-entity の p50 / p95 を測る使い捨てでないハーネス (`tools/`) と、完了ゲートに添える集計行の形式。**閾値は置かない** (P-8)。
- **守るべき条件**: 契約変更ゼロ。L7-1 は C-05 の既存の駆動集合規則に従う。R-10 は WP-7 の規約を再利用し新方式を作らない。
- **完了条件**: C-05 V3 の xfail が 0 (または実測で残る class とその理由が台帳に載る)、CI に総数下限 job、`spec/` に companion、R-12 の基準値が設計 §13 に記録される。
- **再検討事項**: `operation_depth` の枝 (L7-1)。性能ハーネスの plug 選択 (HTTP plug を含めるか。L7-2 前なので in-process TestClient 経路になる点を記録する)。

### フェーズ9 — 契約 1.7.0「宣言と検証」

- **目的**: G-1 と G-3。エージェントの 1 周 (P-2) を閉じる。
- **着手条件**: フェーズ8 完了 (実効 bound の無い peer に新しい要求形を足さない)。契約フェーズなので**設計レビュー 2 回**。
- **範囲** (一括出荷。分けると P-4 に反する):
  - **R-2** 制約宣言: `create_entity` / `add_field` / `alter_field` に enum と nullable。サーバが値検証の choke point で強制し、`EntityDescriptor` が同じ版で報告する。既存行が反する `alter_field` は実行前検証で全件拒否。`pattern` は正規表現の計算量が SI-08 の面になるので**初版に含めない**。両 peer の宣言永続化は per-application upgrade (フェーズ6 / Q4 の機構) で行う。
  - **R-3** 検証エラー語彙: VALIDATION_FAILED / IDENTIFIER_INVALID / CAPABILITY_UNSUPPORTED に固定 key (`field` / `declared_type` / `observed_type` / `violated_declaration`)。事実のみ。行値・推奨値・修正動作は載せない (SI-10)。両 peer でどの層が `violated_declaration` を決めるかを揃える (L6-9 の二重検証を整理する)。
  - **R-4** dry_run と無状態 plan: `MutationRequest` / `ScopedMutationRequest` / `SchemaOperationRequest` に `dry_run`。応答は実呼びと同じ判定 + affected 件数 + (schema なら) 変更後の `EntityDescriptor`。副作用の規則 (監査イベント・idempotency 記録・server-assigned address の消費) を契約に明記。plan トークン = request digest + 対象 entity の schema revision の決定的値で、apply 時に不一致なら PRECONDITION_FAILED。認可判定 (policy simulation) も dry_run の判定に含める。conformance 条件: 「dry_run の判定 = 実呼びの判定、外部可視の状態変化 0」。
  - **R-5** idempotency の実装と契約追記: 両 peer で `idempotency` を `enabled` へ。契約に追記するのは (i) key と body digest の結合、(ii) 同一 key 異 body は CONFLICT、(iii) 保持期間内の再送は元の結果を返す、(iv) cross-entity と schema 操作にも適用、(v) 監査イベントとの相関 (key は secret ではないが、**client が secret 的な値を key に入れることを契約で禁じる文**を置き、`forbidden_fields` との境界を明記)。L7-8 の肯定側がここで初めて load-bearing になる。
  - **R-6** request budget: 要求単位の `budget` (初版は `result_items` / `execution_ms` / `batch_items` の 3 class)。配備上限を超える値は VALIDATION_FAILED、超過は LIMIT_EXCEEDED + `limit_class`。`rows_scanned` は limit class に無く backend 間で意味が揃わないので**含めない**。
  - **R-7** 成功応答の `request_id` (QueryResult / MutationResult / SchemaOperationResult に optional 追加)。
  - **R-8** 派生の操作カタログ: 契約 JSON から生成する機械可読 artifact (endpoint ごとの role / destructive / atomicity 境界 / 返し得る code / 能力依存 / request・response schema)。`tools/` で生成し、テストが再生成して一致を assert する。`/v1/capabilities` からの参照は optional 1 項目。「resource cost の概算方法」は両 peer で同型に計算できないので**含めない**。
- **守るべき条件**: P-1 (plan は無状態)、P-3 (新宣言ごとに一致条件)、P-4、P-5 (budget は下回る方向のみ)、P-7 (経緯文を契約本体に足さない。R-10 の companion に書く)、`versioning.version_binding` の規律 (1.7.0 義務の網羅列挙)。
- **完了条件**: 契約 1.7.0、両 peer の `contract_version` 1.7.0、新条件 (C-20 以降) が four adapters で executable、R-12 の性能差分が記録される。
- **再検討事項**: enum の上限 (要素数・長さ) を `schema_objects` に含めるか別 class か。dry_run の監査イベントの扱い (attributable であるべきか、破壊操作の dry_run を security-relevant とみなすか)。idempotency の保持を DB 側単一真実 (Q4) に載せるか。

### フェーズ10 — 配備面の証拠 (契約変更なし、フェーズ9 と並行可)

- **L7-2** 実 socket を持つ HTTP plug (5・6 番目の plug)。reverse proxy 込み。ここで初めて `surfaces` の「宣言 URL の実在」が load-bearing になる (L6-5 / L6-12)。
- **L6-5a** `surfaces` を DB 側単一真実へ載せる (Q4 と同じ機構)。相互ダイヤルによる健全性検査は採らない (§6)。
- **着手条件**: CI が実サーバ起動の場を持つこと (フェーズ7 D-3 で成立済み)。フェーズ9 と触るファイルが重ならないことを設計で確認する。

### フェーズ11 以降 — 実需駆動 (§3.2 の保留項目)

着手順は実需の記録順とし、本書では固定しない。ただし依存関係は次のとおり。

- 非同期 job (CCR-09) → bulk ingest/export の chunk 原子性 → aggregation。
- change feed は idempotency (R-5) と audit cursor の語彙を前提とする。
- credential 委任 (CCR-11) は R-4 の認可 dry_run を前提とする。
- 関係モデルは 2.0 級として独立審議。関係に依存する機能 (subgraph fetch、relationship-aware plan) はその後。
- snapshot は control plane の application lifecycle としてのみ再考する。

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

依頼者は高性能を大前提と述べたが、**現時点でリポジトリに計測は存在しない**。既知の観測は L6-15 (MitateDB の宣言型 registry 参照が insert 2 回・query 3 回の往復を増やす) のみで、数値は無い。したがって、

1. フェーズ8 の R-12 で基準値を取る。対象は両 peer × 4 plug の query / mutate / cross-entity、指標は p50 / p95 と 1 要求あたりの DB 往復数。
2. 以後の各フェーズは完了ゲートに差分を添える (P-8)。
3. 退行の扱いは初期は記録のみとし、基準値が 2 フェーズ安定した後にゲート化を審議する。**閾値を先に置かない**のは、閾値が bound として機能を縛る形 (P-5) になるのを避けるためである。
4. 性能のために同型性 (P-6) や宣言の真実性 (P-3) を崩す案は採らない。L6-15 のキャッシュは、宣言の変更が cell open 時に見えること (Q4 の visibility 規律) を守る形でのみ入れる。

---

## 8. 台帳 (本書の起票項目)

| ID | 内容 | 行き先 |
|---|---|---|
| **R-1** | 依頼者の目標 (§0) を 4 要求 G-1〜G-4 に分解した。以後のフェーズ設計は §2「守るべき条件」でどの G に応えるかを明記する | 全フェーズ |
| **R-2** | 制約宣言 (enum・nullable) と同版 catalog 報告 | フェーズ9 |
| **R-3** | 検証エラーの固定 details 語彙 | フェーズ9 |
| **R-4** | `dry_run` と無状態 plan トークン、認可 dry_run | フェーズ9 |
| **R-5** | idempotency の両 peer 実装と契約追記 | フェーズ9 |
| **R-6** | request budget (3 class から) | フェーズ9 |
| **R-7** | 成功応答の `request_id` | フェーズ9 |
| **R-8** | 契約 JSON から派生する機械可読の操作カタログ + 再生成一致テスト | フェーズ9 |
| **R-9** | CI のテスト総数下限 | フェーズ8 |
| **R-10** | 契約 JSON の現行/履歴分離 (WP-7 方式) | フェーズ8 |
| **R-11** | r2db 運用項目: smoke test (L7-18 同梱)、backup/restore 実証、ops CLI 引数の secret 経路検査 | フェーズ8 |
| **R-12** | 性能基準値ハーネスと集計行形式 | フェーズ8 |
| **R-13** | 保留項目 (§3.2) の実需記録の置き場。公開後の実利用で現行契約では表現できない要求が出たとき、本表に日付・要求・不足する契約要素を 1 行で記す。これが CCR-01 の「表現力不足の実証」になる | フェーズ11 以降 |
| **R-14** | 本書の改版規約: 判定 (§3, §6) を覆すときは、覆した根拠と日付を該当行に残し版数を上げる。行を消さない | 本書 |

---

## 9. 各フェーズの着手手順

1. 本書の該当フェーズ節を読み、範囲・着手条件・守るべき条件を設計文書 v1.0 の §1〜§2 に転記する (再導出しない)。
2. 設計文書は `docs/design/PHASE<n>_<name>_V1.md`、作業指示書は `docs/work-orders/WORK_ORDER_PHASE<n>_<name>_V1.md`。
3. 契約を触るフェーズは設計レビュー 2 回、触らないフェーズは 1 回。
4. 依頼者裁定は設計文書に逐語で記録し、再審議しない。
5. 完了ゲートは root suite の単独実行 (`pytest -q -n 5 --dist loadgroup`) と CI 3.11 job の集計行、および R-12 確定後は性能差分。
6. フェーズ完了時に本書 §1「現状」と §8 の行き先を更新する (R-14)。
