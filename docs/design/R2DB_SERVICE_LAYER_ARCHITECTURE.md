# r2db-api 実サービス層 (HTTP + PostgreSQL) アーキテクチャ決定 v1

## 文書情報

- 版数: 1.2 (§3 の手順1〜5を実装済みとして記録し、§7 に残作業を新設)
- 発行日: 2026-08-27
- 設計担当: Opus
- 前提: `docs/design/CONFORMANCE_ADAPTER_V1.md` の完了。共通suiteが実体を検証できる状態を先に作る。

## 1. 位置づけ

現在の `r2db-api/src/r2db_api` は in-memory reference foundation であり、production deploymentではない。本設計は、その authority shape を保存したまま HTTP境界と PostgreSQL永続化を与える。

CLAUDE.md の development order に従い、**共通契約 → conformance証拠 → 実装** の順序を守る。HTTP endpoint名・request形状は `spec/data-service-api.v1.json` が既に定義しており、実装がこれを発明することはない。

既存VPS `project/r2-vps/apps/r2db-api` は明示的移行が行われるまで現行正本であり、本作業はこれを変更しない。

## 2. 確定する主要決定

### D-1 レイヤ分割

```text
HTTP adapter (ASGI)
  ↓  検証済みAuthContext / 構造化request
DataService                      ← 既存。authority・limit・auditの中核。変更を最小化する
  ↓  bound plan (identifier allowlist済 + 値はbind parameter)
StorageBackend (protocol)
  ├─ InMemoryCell   ← 既存 structured.py。test doubleとして残す
  └─ PostgresCell   ← 新規
```

`structured.py` は **検証・計画層** に位置づけを移す。identifier検証、operator allowlist、mutation形状検査、destructive確認、limit適用はここに留め、実行だけをbackendに委ねる。この分割により、in-memory backendとPostgreSQL backendが**同一の検証境界**を通る。検証をbackend側へ複製すると、片方だけが緩むという最悪の分岐が起きる。

### D-2 HTTP層

- **Starlette** を採用する (FastAPIではなく)。理由: request/response schemaは `spec/` のJSON Schemaが正本であり、pydanticによる第二の型定義を導入すると正本が二重化する。security-criticalな検証は既に `structured.py` にある。
- **request byte boundは本文parse前に適用する。** `Content-Length` 検査だけでは不足で、chunked/欺瞞ヘッダに対しては ASGI receive loop で累積バイト数を打ち切る。framework の body parser に到達してからでは SI-08 を満たさない。これは実装上の最重要注意点である。
- 認証は `Authorization: Bearer` のみ。credentialからの `AuthContext` 解決はserver側で行い、path・query・body・その他headerは scope/role に一切影響しない (SI-06)。
- error responseは `application/problem+json`、`FoundationError.problem()` の形状。未捕捉例外は汎用 `SERVICE_UNAVAILABLE` に潰し、trace/内部文言を外へ出さない (SI-10)。
- `request_id` を各requestで生成し、responseとauditの双方に載せる。現状 `DataService._event` はrequest毎に新しいUUIDを作っており、**同一requestの複数eventが相関しない**。HTTP層導入時にrequest_idを引き回すよう修正する。

### D-3 PostgreSQL isolation model

**schema-per-application + application毎の2つのDB role + RLSを多層防御として併用する。**

| 層 | 内容 |
|---|---|
| 名前空間 | application毎に1 schema。物理schema名はcontrol planeが採番し、client入力から導出しない |
| 権限 | application毎に `runtime` role と `developer` role。runtimeはDML のみ、developerは自schemaへのDDLのみ。いずれも `CREATEDB` / `CREATEROLE` / superuserを持たない |
| RLS | 単一schema化した場合に備えた第二の壁。application_id列 + policyを敷き、role権限が誤設定でも越境しない |
| 接続 | control planeは別role・別接続。application requestの経路から到達しない (SI-02) |

database-per-applicationは接続数と運用コストで現実的でない。RLS単独はSI-00の「単一実装欠陥が他applicationへ波及しない」に対して層が薄い。schema + role + RLS の三層が、コストと封じ込めの妥当点である。

**注意点 (実装時に必ず扱う):** connection poolで `SET ROLE` / `search_path` を使う場合、返却時の `RESET ROLE` / `DISCARD ALL` を怠ると、次の借り手が前applicationの権限で動く。これはSI-01を直接破る典型的欠陥である。pool返却hookでの明示的リセットと、リセット漏れを検出するtestを必須とする。可能ならrole毎に独立poolを持ち、借り手を跨いだrole切替自体を発生させない方式を優先する。

### D-4 SQL構築境界

- driver は **psycopg 3**。
- 値は**例外なく**server-side bind parameterで渡す。文字列連結は禁止する。
- identifier は `psycopg.sql.Identifier` のみで合成し、その前に (a) 構文allowlist、(b) **catalogとの照合**の二段を通す。構文検査だけでは、攻撃者が有効な構文の未知identifierを注入できる。
- 動的SQL断片 (operator、ORDER方向) は固定literalへの写像のみとし、外部文字列を通さない。
- `PostgresCell` に「任意SQL文字列を受け取る公開method」を作らない。内部helperも `sql.Composed` を受け取る形にし、`str` を実行する経路を型で塞ぐ。

### D-5 transaction / atomicity

- 1 HTTP request = 1 transaction。`transaction: "atomic"` はDB transactionへ直接写像する。
- `best_effort` は現状 `unavailable` のまま。partial-result意味論を契約が定義するまで advertise しない。
- statement timeout と lock timeout をsession単位で設定し、`execution_ms` limitと整合させる。現在の `reference_wall_clock` enforcementは、PostgreSQL側の `statement_timeout` へ格上げできる。capability documentの `limit_enforcement` を `enforced` に変える根拠になる。

### D-6 audit

- 現行の in-memory `AuditSink` は production では不十分。append-only性を application からも service processからも保証できない。
- 方向: audit書き込み専用role (INSERTのみ、UPDATE/DELETE権限なし) + 別schema、加えて外部sinkへの転送。**sink書き込み失敗時のポリシー**を明示的に決める必要がある (fail-closed / degrade)。現在 `r2db-api/README.md` は「claimしない」と記している。実サービス層ではこれを決定しなければならない。SI-14が要求するのは証拠の存在であり、SI-15はauthorizationのfail-closedを要求するがaudit sink障害までは要求していない。**推奨: security-relevant denial と control plane変更については fail-closed、通常のdata operation eventについては bounded buffer + 明示的alert。** これは要判断事項として依頼者へ上げる。

### D-7 secret管理

- credential pepper、DB接続情報は環境変数名 / secret manager参照のみ。repository には合成値しか置かない。
- `R2DB_CREDENTIAL_PEPPER` は既に環境変数必須。DB credentialも同方式とし、`.env.example` に名前だけを追加する。

## 3. 作業順序 (確定後に細分する)

1. **[done]** `spec/` 側の不足確認 -- `catalog` 応答 (`GET /v1/catalog`) と `CapabilityDocument.authorization_propagation_bound_ms` (`docs/design/CONFORMANCE_ADAPTER_V1.md` §7 の契約追加、`required` 化込み) を実装。pagination cursor (`Page.cursor`) は契約schema上は既存のまま残し、実装は `CAPABILITY_UNSUPPORTED` で明示的に未対応と回答する形で決着した (advertiseしない)。
2. **[done]** `StorageBackend` protocol抽出、`InMemoryCell` をその実装へ整理 (振る舞い不変、既存test緑を維持) -- `r2db-api/src/r2db_api/backend.py`。`ApplicationCell` が protocol に適合することを import時の `issubclass` assertionで検査している。
3. **[done]** `PostgresCell` 実装 + schema/role provisioning (control plane側) -- `r2db-api/src/r2db_api/postgres.py`、`r2db-api/migrations/0001_bootstrap_control_plane.sql`・`0002_provisioning_functions.sql`、runbook (`r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md`)。D-3の三層 (schema / runtime・developer role / RLS) を実装し、`r2db-api/tests/test_postgres.py` で実PostgreSQL 16に対して検証している。
4. **[done]** ASGI層 (byte bound → 認証 → routing → 構造化検証 → 実行 → problem+json) -- `r2db-api/src/r2db_api/http.py`。request byte boundはASGI receive loopで本文parse前に適用し (`RequestByteBoundMiddleware`)、認証は `Authorization: Bearer` のみを見る。
5. **[done]** conformance adapter を HTTP経路へ差し替え、C-01/C-03/C-08 を **HTTP越しに** 再実行 -- `r2db-api/conformance/conformance_adapter_r2db_http.py` (`r2db-api-http`)。既存の in-process adapter (`conformance_adapter_r2db.py`) を置き換えるのではなく、同一peerの第二adapterとして追加し、両方を `registry.json` に `required: true` で登録した。3件の実装欠陥がこの過程で表面化し、修正済み (`docs/design/CONFORMANCE_ADAPTER_V1.md` §10.6, §10.8)。
6. `CONTROL_MAPPING.md` を deployment証拠で更新 -- 本ドキュメント更新の一部として、ローカル/testクラスタ証拠を追記済み (`security/CONTROL_MAPPING.md`)。ただしこれは手順6が要求する「deployment証拠」そのものではない -- VPS上でのprovisioning実行、および実運用environmentでの評価が残っている限り未完了として扱う (§7 参照)。

手順5が本phaseの意義である。in-process adapterで確立した条件を、HTTP + PostgreSQL の実体に対してそのまま再実行できることが、conformance層を先に作る理由である。

## 4. 解決済み判断事項

以下は依頼者裁定により確定した (2026-08-27)。詳細は §5。

- D-6 audit sink 障害時ポリシー: **推奨案を採用**。
- `CapabilityDocument.authorization_propagation_bound_ms` の required 化: **採用**。
- PostgreSQL の配置: **既存VPS**。

## 5. 依頼者裁定と、そこから導かれる制約

### 5.1 audit sink 障害時ポリシー (D-6 確定)

採用:

- **fail-closed** — authentication/authorization denial、credential/application lifecycle 変更、destructive/privilege-sensitive 操作、security-control failure。これらを永続的に記録できない場合、操作を実行しない。
- **bounded buffer + 明示的alert** — 通常の data operation event。有限バッファで吸収してよいが、**alertなしに黙って捨ててはならない**。

共通契約の `audit.sink_failure_policy` として記述する。両peerに共通する安全性質であり、platform詳細ではない。CCR-06 が既に canonical audit 意味論を採用しているため新規CCRは不要で、採用済み意味論の機械可読化にあたる。

### 5.2 伝播bound公開 (確定)

`CapabilityDocument` に `authorization_propagation_bound_ms` を追加し `required` とする。CCR-10 が既に採用した意味論の機械可読化。`MitateDB-api` は capability discovery 自体を持たないため、契約が要求する最小の discovery を実装する必要がある。これは本決定の直接の帰結である。

### 5.3 配置: 既存VPS (確定)

Cloud SQL や managed identity は前提にできない。ローカルPostgreSQL上で D-3 の三層 (schema / role / RLS) を実現する。ここから次の制約が確定する。

**C-1 既存実装との共存。** 既存VPS上では `project/r2-vps/apps/r2db-api` が現行正本として稼働している (CLAUDE.md)。新実装はこれを一切変更せず、**database名・role名・待受port・schema名の全てを分離**して共存しなければならない。移行は明示的な作業であり、本設計は暗黙に開始しない。既存DBへの接続情報を新実装が持たないこと自体が分離の証拠になる。

**C-2 provisioning権限の分離。** schema/role の作成には privileged role が要る。API process の role は `CREATEDB` / `CREATEROLE` / superuser を**持たない**。provisioning は migration/SQL として版管理し、運用者が別credentialで実行する。API process から provisioning 権限へ到達しないことが SI-02 の実体である。

**C-3 接続境界。** PostgreSQL は外部ネットワークへ公開しない。localhost socket / loopback のみで待ち受け、`pg_hba.conf` は該当roleに限定する。これは deployment 証拠として `security/CONTROL_MAPPING.md` に記録する対象であり、application code で証明できる性質ではない。

**C-4 secret管理。** DB credential は systemd EnvironmentFile 等のOS権限で保護した外部供給とし、repositoryには変数名のみを置く。`.env.example` に名前だけを追加する。

**C-5 検証環境。** 本作業機にはPostgreSQL 16が稼働しているため、`PostgresCell` と provisioning SQL は**実PostgreSQLに対して**検証する。skipで回避しない。VPS本体へのprovisioningは本作業の範囲外であり、成果物は migration SQL と runbook である。テスト用のdatabase/roleは専用namespaceを用い、テスト終了時に破棄する。

## 6. 旧 §4 要判断事項 (解決済み、記録として保持)

## 7. 未解決のまま残る作業

手順1〜5 (§3) が実装した範囲は、いずれもローカル/testクラスタでの検証にとどまる。以下は本phaseの範囲外として明示的に残す:

- **VPS provisioning が未実施。** `migrations/` はrepositoryに存在するが、既存VPS上では一度も実行されていない。`r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` §5 が要求する `pg_hba.conf`・`listen_addresses` の実機確認も未実施。
- **production証拠が無い。** `security/CONTROL_MAPPING.md` の該当行はすべて「ローカル/testクラスタ evidence」であることを明記しており、production identity/network/database-grant evidenceには昇格していない。
- **audit sinkの耐久実装が無い。** D-6/§5.1で確定したfail-closed / bounded-buffer+alertの方針は契約に記述されたが、`AuditSink` (`r2db-api/src/r2db_api/audit.py`) は引き続き単一プロセス内のin-memory append-onlyリストのままであり、外部sinkへの転送・失敗検知・alertingのいずれも未実装。
- **`psycopg_pool` への置き換えが未実施。** `postgres.py` の `_RolePool` は手作りのqueueベースpoolであり、`psycopg_pool` (公式pool実装) への置き換えは行っていない。D-3が指摘するrole/schema漏れのhazardは `_RolePool` の設計 (role毎に別pool、`SET ROLE`を使わない) で構造的に回避しているが、再接続・health check等のpool運用機能は自前実装の範囲にとどまる。
