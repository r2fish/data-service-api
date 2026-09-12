# data-service-api 完成度向上アプローチ

## 前提

本書は確認済みの現状から導く提案であり、未承認の設計・機能を実装済み又は現行ロードマップに確定済みとは扱わない。現在の成熟度は `PRODUCTION_CANDIDATE` であり、`PRODUCTION_READY` の判定には実環境での切替、運用観測、復旧の証拠が必要である。

## 優先順位

| 優先度 | 取り組み | 現状 | 完了の判断基準 |
|---|---|---|---|
| P0 | 旧 VPS からの切替・データ移行 | 未実装 | snapshot と増分同期、整合性照合、切替、撤回を自動化し、SI-00〜SI-14・監査・credential・idempotency の保存を隔離環境で実証する。 |
| P0 | 運用観測性と障害復旧 | 一部実装 | `request_id` と audit を相関キーに、最小権限の構造化ログ／メトリクスを定義する。network/DB/disk/process 障害後に fail-closed と復旧整合性を実証する。 |
| P1 | online schema / application upgrade 規律 | 一部実装 | 既存の upgrade ledger を基礎に、後方互換、旧新プロセス併存、段階展開、停止基準、rollback 可否を操作ごとに明文化・検証する。 |
| P1 | agent 向け派生契約成果物 | R-23 は将来項目 | operation catalog を正本にせず、生成・再生成一致可能な bundle / manifest を追加する。`operation_catalog_url` の採用も同時に判断する。 |
| P2 | SDK と E2E サンプル | 未実装 | capability/catalog discovery、`dry_run`、`plan`、`request_id`、安全な再試行を扱う薄い SDK を提供する。 |
| P2 | 大量処理・replica topology | 未実装／部分実装 | chunk 再開・原子性・budget・部分成功の意味論を契約化してから実装する。replica は freshness/read-your-writes/schema propagation を定義してから扱う。 |
| P2 | 構造・文書の保守性 | 改善候補 | 挙動不変のモジュール抽出と、現行仕様・履歴・将来作業を案内する短い入口文書を導入する。 |

## P0-1: 旧 VPS 切替・移行

現行 r2db は旧 VPS 配備と別の名前空間を使い、旧実装の migration を暗黙に行わない。この分離は安全だが、切替機構ではない。

設計を開始する前に、旧実装の実データモデル、credential 形式、監査の保持要件、書込み停止の許容時間、DNS/LB の制御者を確認する必要がある。これらは本リポジトリ内にないため、推測で adapter や移行 script を作成しない。

採用すべき段階は次のとおりである。

1. source/target の論理スキーマとデータ分類を機械比較する。
2. 読取り一貫性を持つ snapshot と、書込み差分を表現する方式を決める。
3. 移行データ、credential、audit、idempotency record それぞれの保存／再発行／非移行を明文化する。
4. 本番相当の隔離環境で、同期、検算、切替、旧系への撤回を反復する。
5. 実行ログと整合性結果を、秘密を含めずに evidence として残す。

「無停止」は要件として測定可能に定義する必要がある。旧新双方が書込みを受ける期間を許すのか、一時的な書込み停止を許すのかで、正しい設計は異なる。

## P0-2: 可観測性と障害復旧

SI-10 の非開示はクライアント応答の境界であり、SRE に観測手段を与えない理由にはならない。ただし telemetry も credential、SQL、行値、個人情報を出力してはならない。

最初に固定するべき telemetry schema は、少なくとも `request_id`、plane、operation、outcome/code、duration、DB connection acquisition、lock wait、retry/replay、pool 使用量、audit write outcome を含む。クライアント由来の生payload、SQL、secret、row value、内部DB名は含めない。出力先へのアクセスは control/audit の権限設計と同じく最小権限にする。

障害試験は通常CIから分離した専用環境で行う。最低限、DB接続断、DB再起動／failover、書込み失敗、容量圧迫、process kill を対象とし、各ケースで以下を確認する。

- 要求が安全に拒否又は失敗し、成功を偽装しないこと。
- 復旧後に idempotency record と実効果が二重化・乖離しないこと。
- durable audit の許容された遅延・失敗の意味論を守ること。
- 再試行可能な状態と、運用者の介入が必要な状態を区別できること。

## P1: SDK と agent 向け成果物

サーバ側には capability discovery、field type/constraint catalog、`dry_run`、`plan`、`request_id`、構造化 denial がある。SDK はそれらを忠実に消費するべきであり、任意にデータを書き換えたり「プロンプト修復」を隠れて実行するべきではない。

SDK が自動化してよいのは、capability の再読込み、同一 idempotency key の安全な再送、`dry_run` と実行の明示的な二段階、契約上 retryable と定義された失敗の限定的な再試行である。破壊的操作、権限不足、schema 意味の変更、`violated_declaration` の修復は、呼出し側へ構造化された判断材料として返す。

Python と TypeScript の両方を同時に始める必要はない。派生 contract bundle と一つの参照SDKを先に作り、wire contract / conformance との一致を自動テストする。

## P2: 処理能力・トポロジー

C-16 の cross-entity mutation は、有効な peer で原子性と `batch_entities` を検証している。しかし全 peer で提供される汎用 bulk API ではない。大量処理には cursor、chunk 上限、再開トークン、idempotency、dry-run、timeout/budget、部分成功を明示的に契約化する必要がある。

read replica は単なる DSN 追加ではない。read-after-write、replica lag、schema変更反映、障害時の primary fallback、監査・認可の一貫性を先に決め、capability/declaration/conformance に落とす。

## 保守性の改善

巨大モジュールの分割は価値があるが、P0の運用安全性を遅らせない。まず純粋な parser/validator/formatter を抽出し、public signature、契約、両 peer の安全結果を変えないことを既存の同型性・適合性試験で固定する。

文書については既存履歴を移動・削除せず、短い入口から `spec/`、`security/`、現行runbook、ロードマップ、履歴文書を案内する形が安全である。新しい `CURRENT_SPEC.md` の作成は提案であり、現時点の確定タスクではない。
