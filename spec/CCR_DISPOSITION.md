# CCR-01〜12 共通契約採否記録

入力は `MitateDB-api/contracts/COMMON_CONTRACT_CHANGE_REQUEST.md`。判断は実装固有の都合ではなく、共通Capability、Security Invariants v1、両peer適用可能性で行った。

| CCR | 判定 | 理由 | 再検討条件 |
|---|---|---|---|
| CCR-01 | 採用 | versioned structured API、raw SQL/物理名/DB credential非依存は SI-04/05/12 と両peerに共通 | structured APIが表現力不足となる実証があれば、SQL公開以外の拡張を提案する |
| CCR-02 | 採用 | domain-neutralな永続化境界は共通責務を明確化し、business workflow混入を防ぐ | 上位層との責務衝突を示す新Capabilityがあれば境界を再評価 |
| CCR-03 | 採用 | logical catalog、generic entity、CRUD/query、bounded bulkは共通Capabilityとして有用 | peerの表現力不足が確認された場合は構造化拡張を追加 |
| CCR-04 | 採用 | validation、authorization、binding、failure-before-executionを必須化し SI-05/06/15 を満たす | 新操作で不足する検証クラスが発見された場合に契約を拡張 |
| CCR-05 | 採用 | atomicity、rollback、retry/race preconditionは SI-11 の共通意味論 | 分散操作を導入する際、追加の整合性証拠が必要になれば改訂 |
| CCR-06 | 採用 | canonical service-observed auditとsecret/SQL/row-value非開示は SI-10/14 に共通 | 法令やpeer差で保持項目が不足する実証があれば最小項目を再評価 |
| CCR-07 | 採用 | requestからschema proliferationまで有限boundを要求し SI-08 を直接反映 | 実測で不足する資源クラスがあれば追加 |
| CCR-08 | 採用 | scope/roleをserver-boundにし、control-plane証拠とは分離することで SI-00/01/02/03/06 を共通化 | 新しい認証方式が導入される際に同じ非昇格性が証明できるか再検討 |
| CCR-09 | 採用 | structured schema/destructive/job意味論は将来Capabilityとして必要。権限・bound・atomicityを明示する | long-running jobを実装する時点で状態遷移とcancel/expiry条件を追加 |
| CCR-10 | 採用 | revoke/disable伝播boundとfail-closedは SI-13/15 に不可欠 | セッションキャッシュを導入する際、bound証拠が不足なら方式を再検討 |
| CCR-11 | 採用 | Application-bound user/session、role/scope/policyを共通意味論とし、business PersonやUI authorityは除外 | user/identity capability実装時にpeer同等の policy/revoke 証拠を確認 |
| CCR-12 | 採用 | audit emission/query分離とcontrol/audit-only queryは SI-02/10/14 に整合 | business auditを上位層から取り込む場合、security evidenceとの混同がない契約を別途審査 |

却下・保留となるCCRはない。Google Cloud、SQLite、PostgreSQL、Cloud Run、secret manager等の実装制御は共通契約へ昇格せず、各peerの証拠として扱う。

## 追加契約変更 (2026-08-27, 依頼者承認済み)

以下の2件は新規CCRではなく、既採用の意味論を機械可読化する additive 変更 (`versioning.compatibility` の範囲内)。判断は `docs/design/R2DB_SERVICE_LAYER_ARCHITECTURE.md` D-6 の要判断事項として依頼者へ提示され、承認された。

| 変更 | 実現するCCR | 内容 | 再検討条件 |
|---|---|---|---|
| `audit.sink_failure_policy` の追加 | CCR-06 | security-relevant denial・control-plane変更はaudit sink障害時にfail-closed、通常のdata-operation eventはbounded buffer + 明示的alertとする方針を契約文言化 | 実sinkの運用実績でbounded bufferの許容遅延・alert経路の要件が不足すると判明した場合 |
| `CapabilityDocument.authorization_propagation_bound_ms` の追加 (`required`化含む) | CCR-10 | `lifecycle.propagation_bound` が要求する「有限boundをprofileで公開する」を検証可能にする機械可読フィールドを追加 | 将来sessionキャッシュ等でbound値が0固定でなくなる場合、より詳細な粒度 (credential種別別など) が必要か再評価 |

いずれも新しい共通Capabilityや安全outcomeを追加するものではなく、既存の CCR-06 (canonical audit) / CCR-10 (revoke/disable伝播bound) が既に要求していた意味論を、`spec/data-service-api.v1.json` 上で検証・実装可能な形にしたものである。
