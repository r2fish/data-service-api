# MitateDB-api 次期正式実装 作業指示書

## 文書情報

- 版数: 1.1
- 発行日: 2026-08-27
- 発行者: 依頼者
- 改訂履歴:
  - 1.0 (2026-08-27) 初版
  - 1.1 (2026-08-27) 位置づけ・作業順序の明記、参照資産の事実整合(稼働実装なし・Mitate先行ドキュメント参照)、共通契約整備の主導権明確化、報告先・裁定ルール追加

## 位置づけ・作業順序

- 本作業はr2db-api次期正式実装([R2DB_API_WORK_INSTRUCTION.md](R2DB_API_WORK_INSTRUCTION.md))と同時進行とする。優先はr2db-api側にある。
- 共通契約(`data-service-api/spec/`)の整備はr2db-api作業が主導する。MitateDB-api作業は独自にspec/を書き起こさず、Mitate由来の要求を共通契約への変更要求として提起し、取り込みはr2db-api側へのpeer影響を確認して行う。
- 共通契約が未整備の領域でMitateDB-api実装を先行させず、実装固有契約を暗黙に発生させない。
- data-service-api(r2db-api、MitateDB-api)の成立後に、Mitate本体の本格着手を行う。
- 期限・マイルストーンは本指示書では定めない。

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
data-service-api/MitateDB-api
```

MitateDB-apiの稼働実装はまだ存在せず、本作業が初回実装である。

参照すべき既存資産は、Mitate Repositoryの先行ドキュメント群(architecture、contracts、primitives、governance等)である。Mitate Repositoryは本Repositoryとは別のRepositoryであり、ローカル参照先は依頼者が作業開始時に提示する。場所や構造を推測で固定しない。

先行ドキュメント群はCapability、要求、テスト観点を確認するために参照してよいが、その構造・API・内部設計を維持する義務はない。

Mitate Repository側は今回の作業では変更しない。

稼働中の旧APIは存在しないため、旧API互換の考慮は不要である。Mitate本体は新MitateDB-apiの正式契約に対して実装する。

また、`MitateDB-api/architecture/DATA_SERVICE_FOUNDATION.md` をMitateDB-apiの責務境界(owns / does not own)の先行定義として参照する。

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

`data-service-api/MitateDB-api` を、次期本番として使用できる正式なData Service APIとして新規構築する。

MitateDB-apiは`r2db-api`のコピーや従属実装ではなく、`data-service-api/spec/`と共通Security Invariants／conformance contractを満たすpeer implementationとする。共通契約は共有するが、Mitate固有のplatform control、deployment、authority isolation、storage/runtime方式は目的に最適なものを採用してよい。

中心目的は次のとおり。

1. Application単位の強いデータ・authority分離を成立させる。
2. 1つのApplication Credential侵害、または1つのapplication-facing implementation defectだけで、他ApplicationまたはControl Planeへ到達できない構造を成立させる。
3. Application向けAPIから任意SQLやDB-native commandを公開せず、十分に拡張可能なstructured operationを提供する。
4. Data、Development、Application User、Control、Provisioning、Auditの責務とauthorityを明確にする。
5. resource consumption、revocation、destructive operation、atomicity、error disclosure、auditability、fail-closedを正式なサービス契約として成立させる。
6. 将来のCapability追加を阻害しないAPI/内部構造にする。


### 4.1 r2db-apiとの関係

- Public contractと共通semanticsは`data-service-api/spec/`を正本とし、MitateDB-api固有仕様を暗黙に追加しない。
- 共通conformance suiteはr2db-api／MitateDB-apiの双方に適用できる状態を維持する。
- 同じSecurity Invariantを満たすcontrol implementationは両者で異なってよい。
- r2db-apiの内部構造、PostgreSQL固有control、deployment方式をMitateDB-apiへ機械的に移植しない。
- MitateDB-apiで必要になった共通Capabilityは、実装固有endpointとして閉じず、共通contractへ上げるべきかを判断する。

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

r2db-api現行実装で成立している次の原則を、明確な改善理由がない限り共通原則として維持する。

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

一方で、r2db-api(現行・次期)の実装形式 — credential形式、endpoint、JSON contract、認証方式、Control DB構造、Credential保存・配布方式、framework構成等 — には拘束されない。共通契約とSecurity Invariantsを満たす範囲で、Mitateの目的に最適な方式を採用してよい。

---

## 7. 最初の実装範囲

最初の作業では、Public APIの個別機能を大量実装することより、次期MitateDB-apiのfoundationを成立させることを優先する。

少なくとも以下を一体として構築する。

### 7.1 Machine-readable contract

共通契約(`spec/`)の整備はr2db-api作業が主導する。MitateDB-api作業ではspec/を独自に書き起こさず、次を行う。

- Mitateの先行ドキュメント群から導かれる要求を、共通契約への変更要求として整理・提起する
- 共通契約がMitateDB-apiのpeer implementationとして成立するか(r2db-api固有の暗黙前提がないか)を確認する
- 共通契約への取り込みは、r2db-api側へのpeer影響を確認して行う

共通契約に最低限含まれるべき対象は次のとおり(r2db-api側指示書と共通)。

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

MitateDB-apiの既存テストは存在しない。r2db-api側で確立されている以下の観点を、共通conformance観点として適用する。

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

- Mitate Repositoryおよび稼働中の本番資産は、明示的に作業対象へ含めない限り変更しない。
- Mitate Repositoryの非公開情報(ローカルパス、内部運用情報、公開判断が済んでいない設計内容等)を本公開Repositoryへ記載しない。
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

1. MitateDB-apiが従う正式なAPI/security契約がmachine-readableな形でRepositoryに存在する。
2. Security Invariants由来のconformance条件と実行可能な初期suiteが存在する。
3. authority topologyとruntime/deployment skeletonがコード・設定として存在する。
4. SI-00をどの境界で成立させるかが実装とevidence planに結び付いている。
5. Data Planeの次の実装へそのまま進める構造になっている。
6. `CONTROL_MAPPING.md`に実在するcontrol/evidenceのみ反映されている。
7. test / lint / compile等、Repositoryで妥当なquality gateを実行し結果を報告する。
8. 旧正本を変更していない。
9. 未解決事項がある場合は、実装を止めるblocking issueと将来改善を分けて報告する。

Lunaは完了時に、変更概要、主要設計判断、Security Invariant対応、テスト結果、残課題を簡潔に報告する。
完了報告は依頼者へ提出する。Terraのレビュー結果とSolの判定は最終報告に含め、報告経路を一本化する。

---

## 12. Terraのレビュー条件

Lunaの成果に対し、最低限以下を独立確認する。

- Capabilityを不必要に狭めていないか
- API contractと実装が乖離していないか
- 共通contractをMitateDB-api固有都合で分岐させていないか
- 共通conformance suiteがpeer implementationとして成立しているか
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
11. Luna/Terraで判断が割れた場合はSolが裁定する。Solが決せない事項は依頼者へエスカレーションする。

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
