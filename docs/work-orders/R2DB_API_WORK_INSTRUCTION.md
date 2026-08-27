# r2db-api 次期正式実装 作業指示書

## 1. 作業体制

- 実装担当: Luna
- レビュー担当: Terra
- 監督: Sol
- 依頼者: 依頼者

役割は分離する。

### Luna

事実確認、設計判断、実装、テスト、必要な文書更新までを一貫して行う。
目的とSecurity Invariantsを満たす範囲で実装方法はLunaの判断に委ねる。
既存実装の形を機械的に移植しない。

### Terra

Lunaの成果を独立にレビューする。
Security Invariants、責務境界、API契約、authority topology、テスト、回帰、運用可能性を確認し、問題を重要度付きで報告する。
レビューのために設計を別物へ作り替えない。修正が必要な場合は、問題・根拠・期待する成立条件を明示する。

### Sol

全体を監督し、目的・Capability・Security Invariants・Luna/Terraの判断がずれていないかを確認する。
実装詳細を過剰に固定せず、必要な場合のみ方向修正を行う。
Terraの指摘は機械的に採用せず、Security Invariantsと製品価値に照らして採否を判断する。

---

## 2. 正式対象

新しい正本は以下とする。

```text
data-service-api/r2db-api
```

現在本番で利用中の以下は、移行元・参考実装であり、新しい正本ではない。

```text
project/r2-vps/apps/r2db-api
```

旧実装はCapability、実運用知識、テスト観点を確認するために参照してよいが、構造・API・内部実装を維持する義務はない。

旧実装側は今回の作業では変更しない。

既存ApplicationとのAPI互換性も要求しない。
新r2db-apiを本番へ反映する前に、利用Application側を新仕様へ対応させる。
旧API互換adapterは原則作らない。

---

## 3. Securityの正本

以下を必ず基準とする。

```text
data-service-api/security/SECURITY_INVARIANTS_V1.md
data-service-api/security/THREAT_MODEL_V1.md
data-service-api/security/CONTROL_MAPPING.md
data-service-api/conformance-tests/
```

`SECURITY_INVARIANTS_V1.md` がSecurity上の最上位契約である。

Security InvariantsはCapabilityを制限するためのfeature allowlistではない。
実装方法を固定するテンプレートでもない。
求められる安全上の結果を成立させるための不変条件として扱う。

---

## 4. 実装目的

`data-service-api/r2db-api` を、次期本番として使用できる正式なData Service APIとして新規構築する。

中心目的は次のとおり。

1. Application単位の強いデータ・authority分離を成立させる。
2. 1つのApplication Credential侵害、または1つのapplication-facing implementation defectだけで、他ApplicationまたはControl Planeへ到達できない構造を成立させる。
3. Application向けAPIから任意SQLやDB-native commandを公開せず、十分に拡張可能なstructured operationを提供する。
4. Data、Development、Application User、Control、Provisioning、Auditの責務とauthorityを明確にする。
5. resource consumption、revocation、destructive operation、atomicity、error disclosure、auditability、fail-closedを正式なサービス契約として成立させる。
6. 将来のCapability追加を阻害しないAPI/内部構造にする。

---

## 5. 承認済み設計方針

先行設計では、次のPlane分離を基本方向とする。

```text
Application Data Plane
Application Development Plane
Application User / Identity Plane
Control Plane
Provisioning Plane
Audit Plane
```

特にPublic Application-facing pathとControl/Provisioning authorityを分離する。

ただし、以下を固定実装として扱わないこと。

### 5.1 Application Security Cellの実装方式

Application単位のSecurity Cellというcontainment境界は必要だが、

```text
1 Application = 1 container
1 Application = 1 process
```

そのものを不変条件とはしない。

SI-00を実証可能な形で満たし、Application数増加時にも現実的に運用できるなら、より軽量または効率的なauthority isolation方式を採用してよい。

単なるPython module分割だけでSI-00を満たしたことにはしない。

### 5.2 API設計

先行設計のendpoint、operation名、JSON形式は有力案だが、完成仕様として固定しない。

Capability、責務、Security Invariantsから見てより良いAPI契約がある場合は改善してよい。

ただし、変更理由を説明できること。

### 5.3 Resource limit

request body、batch、result、query complexity、execution time、concurrency、rate、schema/object proliferation等は必ず有限にする。

先行設計にある具体的な数値は初期候補でありSecurity Invariantではない。
deployment/profileによって適切に設定可能な構造とする。
「無制限」は許可しない。

---

## 6. 維持する原則

現行実装から、明確な改善理由がない限り次の原則を維持する。

- 1 Applicationのデータが他Applicationから読めないこと
- Application scopeをrequest側で任意に切り替えられないこと
- Runtime/Data authorityとDevelopment/Schema authorityの分離
- Application向け任意SQL endpointを持たないこと
- structured operation
- identifier validation / quoting
- value binding
- fail-closed authentication / authorization
- secret非開示
- transaction atomicity
- Application disable / Credential revoke
- Credential secret平文を恒久保存・再表示しないこと

一方で、次は固定しない。

- 現在のRuntime Key / Developer Key形式
- 現在のendpoint
- 現在のJSON contract
- 現在のMeta login方式
- 現在のControl DB構造
- 現在のCredential保存・配布方式
- 現在のFastAPI module構成

---

## 7. 最初の実装範囲

最初の作業では、Public APIの個別機能を大量実装することより、次期r2db-apiのfoundationを成立させることを優先する。

少なくとも以下を一体として構築する。

### 7.1 Machine-readable contract

`spec/` 等に、実装と独立した正式契約を置く。

対象には最低限、次を含める。

- API contract
- authentication / credential semantics
- Application scope semantics
- structured query model
- transaction semantics
- error contract
- resource-limit semantics
- revocation / disable semantics
- audit event contract
- versioning / capability discovery rules

OpenAPI / JSON Schema等を利用してよい。
形式は目的に最適なものを選択する。

### 7.2 Conformance conditions / tests

Security Invariantsから実装非依存のconformance conditionを導出し、可能なものから自動テスト化する。

旧r2db-apiの既存テストは正本ではない。
ただし以下の観点は再利用する。

- cross-Application isolation
- authentication fail-closed
- RuntimeからDDL拒否
- injection耐性
- identifier validation
- parameter binding
- transaction rollback
- Application / Credential disable

SI-00のようにHTTP testだけでは証明できない項目は、platform evidenceを別途定義する。

### 7.3 Authority topology / runtime skeleton

Data Serviceの実行authority境界を、コードだけでなくruntime/deploymentとして成立させる骨格を構築する。

最低限、次を証明可能にする方向で設計・実装する。

- Application Aのapplication-facing authorityからApplication B DBへ到達できない
- Application-facing authorityからControl DB / Provisioning authorityへ到達できない
- Data authorityがDevelopment secret/authorityを必要なく取得できない
- Public requestからprivileged provisioningへ直接到達できない
- Audit eventをApplication側から改変・削除できない

### 7.4 CONTROL_MAPPING

実装・test・platform evidenceが実際に存在するものだけを`CONTROL_MAPPING.md`へ反映する。
予定を証拠として記載しない。

---

## 8. API Capabilityの方向

最終APIはLunaが現状を確認して決定してよいが、最低限以下のCapabilityを失わないこと。

### Data

- schema/catalog参照
- create/read/update/delete
- structured filtering
- projection
- ordering
- bounded pagination
- bounded bulk operation
- atomic multi-operation transaction
- composite/unique keyを扱える将来性
- precondition / idempotency / revision等、retry/raceを安全に扱う仕組み

### Development

- schema introspection
- structured schema change
- table / column
- index / constraint
- destructive schema operationの明示的制御
- schema revision
- 長時間DDLが必要な場合の安全なjob semantics

SQL文字列を逃げ道として公開しない。
Capability不足はstructured APIの拡張で解決する。

### Application User / Identity

- Applicationにboundされたlogin/session
- user / role / scope / policy
- user/session disable・revocation
- Data Planeでのpolicy enforcement

UI Skin等を認可の正本にしない。
Console/Embed UIそのものはData Service coreに含めなくてよい。

### Control / Provisioning

- Application lifecycle
- Credential lifecycle
- quota / status
- disable / revoke
- provisioning operations
- audit query

Application CredentialをControl Plane認証として使用しない。

---

## 9. Security上の重点

特に以下を実装・レビュー・監督で重点確認する。

### SI-00

1 Credentialまたは1 application-facing defectだけで、他Application / Control Planeへ横展開できないこと。
認証コード上のscope checkだけでなく、実行authorityそのものを制限する。

### SI-08

body、batch、result、query complexity、execution time、concurrency、rate、schema/object proliferation等に有限なboundを設ける。
通常Capabilityを不必要に狭めない。

### SI-10

Public errorへSQL、stack trace、DB名、role名、connection情報、raw PostgreSQL error、secret存在差を出さない。
一方、正当なClientが入力を修正できるsafe diagnosticsは維持する。

### SI-11

atomic operationとbest-effort operationを曖昧に混ぜない。
transaction semanticsをcontractとして定義する。

### SI-13

Credential revoke、Application disable、User/session revokeの反映上限を明示し、必要なauthorization stateが期限内に確立できない場合はfail closedとする。

### SI-14

security eventを正式に記録する。
secret、token、password、row value、SQLをaudit logへ記録しない。

---

## 10. 変更禁止・作業境界

- `project/r2-vps/apps/r2db-api` は変更しない。
- Security Invariantsの意味を実装都合で弱めない。
- Security対策を理由にCapabilityを不必要に削らない。
- 任意SQL endpointを追加しない。
- Public APIとprivileged provisioningを同一authorityへ戻さない。
- 旧API互換adapterを作らない。必要性が判明した場合は実装せず理由を報告する。
- 不要な管理UIを作らない。
- 設計書だけ作って実装価値ループを止めない。
- 実装方法を細かなPhaseへ過剰分割しない。
- pushは依頼されない限り行わない。

既存の無関係な変更が存在する場合は保持し、stash/reset/clean等で消さない。

---

## 11. Lunaの完了条件

最初の実装作業は、少なくとも以下を満たした時点で完了候補とする。

1. 次期r2db-apiの正式なAPI/security契約がmachine-readableな形でRepositoryに存在する。
2. Security Invariants由来のconformance条件と実行可能な初期suiteが存在する。
3. authority topologyとruntime/deployment skeletonがコード・設定として存在する。
4. SI-00をどの境界で成立させるかが実装とevidence planに結び付いている。
5. Data Planeの次の実装へそのまま進める構造になっている。
6. `CONTROL_MAPPING.md`に実在するcontrol/evidenceのみ反映されている。
7. test / lint / compile等、Repositoryで妥当なquality gateを実行し結果を報告する。
8. 旧正本を変更していない。
9. 未解決事項がある場合は、実装を止めるblocking issueと将来改善を分けて報告する。

Lunaは完了時に、変更概要、主要設計判断、Security Invariant対応、テスト結果、残課題を簡潔に報告する。

---

## 12. Terraのレビュー条件

Lunaの成果に対し、最低限以下を独立確認する。

- Capabilityを不必要に狭めていないか
- API contractと実装が乖離していないか
- SI-00が単なるapplication_id checkになっていないか
- Application間 lateral movementがruntime authorityで遮断されているか
- Control / Provisioningへの到達可能性がPublic Planeに残っていないか
- Runtime / Development separationがsecret/DB role/runtime authorityまで成立しているか
- resource boundsに抜け道がないか
- destructive operation / transaction / retry semanticsが明確か
- error / auditにsecretや内部topologyが漏れないか
- revoke / disableが契約したbound内でfail-closedになるか
- conformance testsが実装追認ではなくInvariant由来になっているか
- 旧正本や無関係資産を変更していないか

指摘は `Critical / High / Medium / Low` で分類する。

Critical / Highは、根拠と修正後に成立すべき条件を明示する。
Medium / Lowは、実装価値を止める理由がなければ将来改善として扱ってよい。

---

## 13. Solの監督基準

Solは次を基準にLuna/Terraの作業を監督する。

1. Security Invariantsを守る。
2. Capabilityを先に見る。
3. 実装方法は目的を満たす範囲でLunaに任せる。
4. Terraの指摘はriskと根拠で評価し、形式的完全性だけで作業を止めない。
5. Critical / Highが実在する場合は解消させる。
6. Medium / Lowだけを理由に価値提供を先送りしない。
7. SI-00、SI-08、SI-14を特に見落とさない。
8. 現行実装の模倣ではなく、次期正式サービスとしての一貫性を維持する。
9. 設計・テスト・レビューを反復すること自体を目的化しない。
10. Foundation成立後はData Plane等の実Capability実装へ速やかに進める。

---

## 14. 最終ゴール

この作業の最終目的はSecurity文書への形式適合ではない。

```text
安全にApplicationを分離し、
Application開発から使いやすく、
AIエージェントからも扱いやすく、
Structured APIとして十分なDB Capabilityを提供し、
長期的に拡張できるData Service APIを成立させる。
```

Security InvariantsはこのCapabilityを安全に使い続けるための基盤とする。
