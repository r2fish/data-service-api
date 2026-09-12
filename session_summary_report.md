# data-service-api 継続評価・完成度向上 セッションサマリー

**実施日**: 2026-09-13
**対象**: `data-service-api`、HEAD `8c8b770`、契約 `1.8.0`

## 結論

本リポジトリは、共通契約を正本として二つの peer 実装を適合性条件で検証する、強固な API 基盤である。今回の評価は **8.0 / 10**、成熟度は **`PRODUCTION_CANDIDATE`** とした。これは実運用済み又は本番投入済みを意味しない。特に旧 VPS からの切替、SRE 向け観測性、障害復旧の実証は未完了である。

## 確認済みの成果

- `spec/`、`security/`、`conformance-tests/` を実装より上位の正本として扱い、r2db と MitateDB を peer に保つ構造がある。
- 配布用の三つの契約 JSON は SHA-256 が一致する。
- `StorageBackend` protocol とサービス境界があり、構造化操作・識別子検証・値の bind parameter 化・権限分離・監査・冪等性を実装している。
- 登録済み adapter は in-process、HTTP+PostgreSQL、socket を含む六つである。C-26 は実プロセスの起動・停止、C-27 は同一 idempotency key の決定的な並行送信を扱う。
- CI は PostgreSQL 16、変更クラス判定、収集件数下限、socket/nginx 残留検査を定義する。

## 今回の検証結果

| 対象 | 判定 | 根拠・限定 |
|---|---|---|
| 巨大モジュール | 妥当な改善候補 | `cell.py` 4,711 行、`structured.py` 3,254 行、`postgres.py` 2,975 行。責務を変えない抽出を優先する。 |
| wire-level positive-existence | 既知の検証限界 | `CONDITIONS.md` が HTTP adapter の present-denial / surface-absent の真正性を完全には立証できない範囲を明示する。 |
| 旧 VPS からの移行 | 未実装 | `r2db-api/README.md` は旧実装の移行を implicit にせず、production cutover を明示的な将来タスクとしている。 |
| per-application upgrade | 一部実装 | upgrade ledger と `ops upgrade-applications` はあるが、無停止互換展開・旧新併存・schema rollback の運用プロトコルではない。 |
| SRE 向け observability | 一部実装 | durable audit、`request_id`、起動時の宣言・role timeout・connection limit 検査はある。OTel/Prometheus、span、lock wait・SQL latency・pool 使用率の標準テレメトリはない。 |
| 障害復旧・chaos 実証 | 未実装 | 局所的な失敗注入はあるが、network partition、DB failover、Disk Full、OOM と復旧後の監査／冪等性照合を行う実機プロトコルはない。 |
| Agent SDK | 未実装 | C-19 はクライアントがサーバ宣言から必要情報を発見できることの条件であり、Python / TypeScript SDK は存在しない。 |
| Cross-entity / bulk | 部分実装 | C-16 で MitateDB の cross-entity `insert`/`update`/`delete` は原子的に検証される。r2db は unavailable、`upsert` と再開可能な大量 chunk protocol は未提供。 |
| Read replica | 未実装 | role ごとの DSN/pool は権限分離であり、reader/writer routing、replica lag、read-your-writes の設計ではない。 |

## 検証実行の記録

- `tools/tests` はこのセッションで **65 passed**。
- root pytest と collection-floor はローカル PostgreSQL が sandbox から到達できず、必須 adapter の構築時に安全に失敗した。skip にはならない。
- Git 履歴 `88f9c65` には、HEAD 直前の根拠として **3,326 collected/passed の記録、DB 差分 0、nginx 残留 0** がある。本セッションではこの全体実行を独立再現していない。

## 継続評価ベースライン

| 軸 | 点 / 10 |
|---|---:|
| 新規性・独自性 | 8 |
| 技術品質 | 8 |
| アーキテクチャ・設計一貫性 | 8 |
| 拡張性 | 8 |
| 保守性・理解可能性 | 7 |
| テスト・検証可能性 | 9 |
| 完成度 | 7 |
| 実用価値・問題解決力 | 7 |
| 信頼性・堅牢性 | 9 |
| セキュリティ・境界管理 | 9 |
| 技術的負債の少なさ | 7 |
| 成長性・将来性 | 8 |

**Architecture Health**: `IMPROVING`

**Technical Debt Trend**: `DECREASING`

**Development Direction**: `CLEAR`

## 現在の残件・予定

以下は「実装済み」と扱わない。

- 現行ロードマップの R-23: agent 向け派生物（OpenAPI / JSON Schema bundle / agent manifest 等）の検討。SDK はこの範囲にも未着手。
- 現行ロードマップの R-31: プロセス数、rate、応答サイズ、DB 容量、監査保存量を含む配備全体の資源保護。connection limit の一部だけは完了。
- 現行ロードマップの R-36: object/binary API。候補設計はあるが、未実装・未宣言・非正本。
- 旧 VPS から新 r2db への、データ整合性を証明できる切替・撤回手順。
- 最小権限の運用テレメトリ、障害注入と復旧照合の標準プロトコル。

詳細な提案と優先順位は [completion_approach_report.md](completion_approach_report.md) を参照する。
