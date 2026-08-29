# r2db-api 実サービス層 (HTTP + PostgreSQL) アーキテクチャ決定 v1

## 文書情報

- 版数: 1.4 (§8.7 に接続プール管理の決定を追加) (§3 の手順1〜5を実装済みとして記録し、§7 に残作業を新設)
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

## 8. D-3 改訂 — database-per-application (v1.3)

### 8.1 決定

`r2db-api` の application 分離を **schema-per-application から database-per-application へ変更する。**

各 Application は専用の PostgreSQL データベースを持ち、その中の `public` schema に entity を置く。runtime / developer の2 role は従来どおり Application ごとに分ける。

### 8.2 変更する理由

**スキーマは名前空間であり、データベースは壁である。** PostgreSQL では FDW/dblink 無しにデータベースを跨げない。一方 schema 境界は `search_path` の設定ミス、grant の漏れ、RLS ポリシーの当て忘れのいずれか一つで越えられる。SI-00 が要求するのは「単一の実装欠陥が他 Application へ波及しないこと」であり、越境が原理的に不可能な境界のほうが、規律で維持する境界より強い。

さらに現行実装には**構造的な弱点**がある。`PostgresCell._create_entity` は実行時に作成する全テーブルへ RLS を有効化しているが、将来テーブルを作る経路が増えたときに RLS 付与を書き忘れれば、壁は黙って消える。これは §10.1 で `SET ROLE` のリセット漏れについて「規律ではなく構造で消すべき」と判断したのと同じ性質の問題であり、同じ基準を topology 選択にも適用する。

### 8.3 当初 schema を選んだ理由と、その再評価

理由は接続数だった。データベースごとにプールが要るため、消費接続は `application数 × role数 × pool_size` で増え、PostgreSQL の `max_connections` (既定100前後) が天井になる。

しかし本配備では当該制約が効かない。単一 VPS、Application 数は十数個規模である。**起きていない将来のスケール問題のために、いま効いている封じ込めの強度を下げる判断は筋が悪い。** 接続数は運用パラメータとして上限を明示し、天井が見えた時点で再検討する (pgbouncer 等の接続集約、あるいは topology 再評価)。

副次的効果として、既存 VPS 実装が database-per-application であるため **topology が一致し、移行が大幅に容易になる。** 運用知識も流用できる。

### 8.4 共通契約への影響

**無い。** SI-00 の Implementation freedom が明示している。

> Implementations may use separate databases, roles, schemas, tenants, IAM boundaries, network boundaries, policy engines, or equivalent layered controls. The invariant requires containment, not one particular topology.

共通契約は topology を規定しない。本変更は `r2db-api` ローカルの実装判断であり、CCR は不要、`MitateDB-api` への影響も無い (CLAUDE.md: プラットフォーム固有の PostgreSQL provisioning は各実装の内側)。

### 8.5 必須の実装条件

1. **データベース単位の接続許可を閉じる。** 新規データベースは既定で `PUBLIC` に `CONNECT` が付く。provisioning は必ず `REVOKE CONNECT ON DATABASE ... FROM PUBLIC` を行い、当該 Application の runtime/developer 2 role にのみ `CONNECT` を付与する。これが主たる壁であり、**テストで直接検証する** — Application A の role が Application B のデータベースへ接続できないことを、`PostgresCell` 経由ではなく生の接続で確認する。
2. **`public` schema の既定権限を閉じる。** `REVOKE ALL ON SCHEMA public FROM PUBLIC`。developer が所有し、runtime は DML のみ。
3. **RLS は補助の壁として維持するが、実行時コードの記憶に依存させない。** データベース境界が主たる壁になったため RLS の必然性は下がるが、多層防御として残す価値はある。ただし「テーブル作成時に有効化し忘れたら消える」構造は避ける。実現手段の優先順位は次のとおり。
   - (a) bootstrap (クラスタ管理者が実行) でテンプレートデータベースに event trigger を作り、Application データベースを `CREATE DATABASE ... TEMPLATE` で作る。`CREATE EVENT TRIGGER` は superuser 権限を要するため、制御 role では実行できない点に注意。
   - (b) (a) が不可なら、実行時の有効化は残したうえで、**当該データベース内に RLS 未適用のテーブルが1つでも存在すれば fail する検証**を provisioning とテストの双方に置く。希望ではなく検査にする。
4. **接続数の上限を明示する。** `application数 × 2 role × pool_size` の実効値を runbook に記載し、`max_connections` に対する余裕を運用者が計算できるようにする。
5. **既存 VPS 実装との共存 (§5.3 C-1) は維持する。** データベース名・role 名は `r2dbsvc_` 系の名前空間を保ち、既存の `app_<slug>_<hex>` 系と衝突しない。

### 8.6 変更規模

`PostgresCell` は既に Application ごとに独立した DSN を2本受け取る設計であり (`runtime_dsn` / `developer_dsn`)、`_RolePool` も「1つの固定 role として認証済みの DSN」単位でプールを持つ。したがって**接続先をデータベース単位に変えるのに構造変更は要らない。** SQL 合成部 (identifier 検証、catalog 照合、bind parameter、単一 choke point) は一切変更しない。

### 8.7 接続プール管理 — 上限をアプリ数から切り離す

#### 判断の誤りとその訂正

§8.3 で「接続数の制約は本配備では効かない」と記した。**この判断は誤りだった。**

アプリ数を十数個と見積もった点は正しかったが、`pool_size` との積を計算していなかった。既定 `pool_size=4` では `アプリ数 × 2 role × 4` となり、13アプリで104接続、`max_connections=100` を超える。既存本番には既に11個の application database がある。移行した時点で天井だった。

より重要な誤りは、**稼働中の既存実装が同じ問題を既に解いていたのに、それを参照しなかったこと**である。`project/r2-vps/apps/r2db-api/src/r2db_api/pools.py` の `AppPoolManager` は次を備えている。

- `pool_idle_seconds` (既定300) — 未使用エンジンの破棄
- `pool_cache_max` (既定32) — 保持エンジン数の LRU 上限
- `pool_pre_ping` / `pool_recycle`

移行元の実装が本番で解決済みの問題を、新実装で解き直していなかった。

#### 決定

同等の設計を採用する。実装は SQLAlchemy ではなく psycopg 手製プールのため、コードではなく設計を移植する。

- `SharedPoolManager` をプロセス全体で共有し、`(application_id, role)` をキーにプールを保持する。
- **上限はグローバルに置く。** `PostgresCell` ごとに上限を置いても何も縛れない (セルはアプリごとに存在するため)。セルはプール実体を持たず、マネージャから毎回解決する。
- アイドル退避と LRU 上限の双方を持つ。**本質は上限をアプリ数から切り離すことであり、`pool_size` を下げるだけの対症療法では構造が残る。**
- checkout 時に `SELECT 1` で死活を確認する。`conn.closed` はサーバ側で切断された接続を検出できない。
- 設定値は既存実装に揃える (`R2DB_POOL_IDLE_SECONDS=300`、`R2DB_POOL_CACHE_MAX=32`、`R2DB_POOL_SIZE=2`、`R2DB_POOL_MAX_OVERFLOW=2`)。運用者が既存の経験値を流用できる。
- `SET ROLE` は導入しない。プールは固定 role の DSN 専用という §10.1 の性質を保ったまま上限を追加する。

#### 退避が貸出中接続を閉じないことの担保

プール退避は `_retired` を立て、キュー内のアイドル接続のみを閉じる。貸出中の接続はキューに存在しないため、**退避処理からは到達できない**。返却時に `_retired` を見て再投入せず閉じる。

これはテストによる担保ではなく構造による担保である。実行中のトランザクション途中で接続が切れる障害は、負荷時にのみ散発的に現れ本番で最も追いにくい部類であり、規律ではなく構造で消すべき対象にあたる (§10.1 と同じ基準)。

#### 上限の算術

`cache_max` が数えるのは `(application_id, role)` のペア、すなわちプールそのものである。role 係数は既に `cache_max` に含まれるため掛け直してはならない。

```
live_pools        = min(applications × 2, cache_max)
ceiling           = cache_max × (pool_size + pool_max_overflow) = 32 × 4 = 128
```

既存本番実装の上限と一致する。128 は `max_connections=100` を超えるが、これは満杯時の理論値であり、アイドル退避により実効値は大きく下回る。既存実装も同条件で稼働している。運用時は `max_connections` の引き上げか `R2DB_POOL_CACHE_MAX` の低減で調整する。
