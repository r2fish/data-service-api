# MitateDB-api フェーズ3 — HTTP 面と PostgreSQL 永続化 (Cloud Run / Cloud SQL 対応) 設計 v1.0

- 版数: v1.2 (2026-08-30。WP-0 は独立レビューが**二重に**実施された: 本セッション側 (blocker 2 / major 11 / minor 11) を v1.1 で、並行セッション mitate-30 側 (blocker 3 / major 11 / minor 16 / nit 3、対象 v1.0) を第2ラウンドとして v1.2 で、いずれも全数裁定・反映。§8 参照)
- 設計: Fable (監督)。レビュー: 独立レビュー (WP-0、Opus)。実装: WP-1 以降
- 位置づけ: `docs/work-orders/HANDOVER_20260830_FABLE.md` §3 項目2「フェーズ3: MitateDB-api の HTTP 層と永続化 (C-14/C-15 の provided 化を含む)」の実施設計。Mitate repository 側 DM-0018 (Cloud Run 二段階配備) の **Phase B サーバ側** — 「mitate-application の永続化は共通 Data Service API (Cloud SQL 上の MitateDB-api) 経由のみ」— の前提を成立させる
- 依拠する正本: `spec/data-service-api.v1.json` (contract 1.2.0)、`security/SECURITY_INVARIANTS_V1.md`、`security/THREAT_MODEL_V1.md`、`conformance-tests/` (port v1.6、C-01〜C-18)、`MitateDB-api/architecture/DATA_SERVICE_FOUNDATION.md`、`docs/work-orders/MITATEDB_API_WORK_INSTRUCTION.md`
- **契約変更なし**。本フェーズは contract 1.2.0 の実装であり、契約文言・スキーマ・語彙に一切触れない。実装中に契約の欠落・曖昧が見つかった場合は独断で埋めず、両解釈と影響を記録して依頼者へ CCR として提起する (Q-1 の §8.1(b) の前例)

## 0. スコープ

### 目的

MitateDB-api を「ローカル foundation」から「配備可能な peer」にする。完了時の状態:

1. 共通契約 1.2.0 の application-plane endpoint (`/v1/*`) が実 HTTP 境界 + 実 PostgreSQL 永続化で動く
2. control plane (`/control/v1` の 11 endpoint + bootstrap/reset 儀式 CLI) が実装され、`control_plane: enabled` を宣言し、C-14/C-15 が **PROVIDED 分岐**で走る (現在の surface-absent 分岐からの昇格)
3. 第4の conformance adapter **`MitateDB-api-http`** (実 HTTP + 実 PostgreSQL) が `registry.json` に required 登録され、C-01〜C-18 の全 executable 条件が 4 adapter で緑
4. Cloud Run / Cloud SQL への配備資産 (Dockerfile、runbook) が揃う。**配備の実行は運用者作業であり本フェーズに含まない**

### スコープ外 (意図的凍結)

- **capability envelope の拡張**: `upsert` / `contains` / `matches` / `is_null` / `row_addressability` / `revision_preconditions` / `idempotency` / `cross_entity_mutation` / `application_catalog` / `audit_query` / `best_effort_transactions` は現宣言 (unavailable / unsupported / partial) のまま。拡張の要否は Mitate 側 Phase B クライアント設計 (mitate-application の実要求) が確定してから別フェーズで判断する — 実需要なしに宣言面を広げると「初実行まで実証されないコード」を無目的に増やす
  - **【訂正注記 2026-09-04】`application_catalog` はフェーズ6 WP-3 (契約 1.6.0、設計 `docs/design/PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md` §3 D-3) で `enabled` へ flip した** — 「実需要が確定してから別フェーズで判断」という本節の凍結は、依頼者裁定 (2026-09-04、利用者が AI エージェントである前提では catalog の自己記述性は製品の核) により上書きされた。`GET /v1/catalog` は `entity` / `fields` / `field_types` の 3 キーを返し (`mutation_class` 等は `row_addressability: unavailable` のため省略)、宣言型は per-application registry (`_mdb_field_types`、migration 0006 + 0003 テンプレート改訂) が唯一の情報源である。同フェーズで型未宣言 field の既定型は `text` → `json` へ、`json`/`object`/`array` の読み出しは JSON 値へ、宣言 `boolean` の wire は 0/1 → JSON boolean へ変わった (挙動変更 α β γ、cutover 規則は同設計 §8)。上記の凍結文は当時の記述として残す。
  - **例外 (P3-D1、WP-0 B-1 裁定)**: `schema_operations` の `add_field` を本フェーズで解禁する。**帰結 (第2ラウンド B-1)**: 「他の schema 変更が存在しないため delete 確認句に state fingerprint 不要」という既存論証 (cell.py、`DESTRUCTIVE_CONFIRMATION_V1.md` §7 記録) が崩れるため、delete の declare-and-echo 確認句へ schema fingerprint (`@schema_revision`、r2db Q1-D10 と同型) を add_field と同一コミット (WP-1) で追加する。句の綴りは契約非固定 (Q1-D2) のため互換問題なし。また `create_entity` は契約どおり fields 省略を受理 (address 基本列のみの entity)、foundation 面 `create_collection` の空 fields 拒否は不変。契約 `SchemaOperationRequest` は per-field 型スロットを持たない (`field_type` 単一) ため、共通 fixture の混合型 entity は `create_entity` + field ごとの `add_field` でしか契約形状の HTTP 要求として構築できない (r2db-http 既確立の形)。これは投機的な宣言拡張ではなく第4 adapter 成立の実需要であり、上の凍結列挙にも元々含まれていない。宣言 flip と実装・テストは単一コミット (WP-1)。契約側 per-field 型追加の CCR 起票、および共通 suite を MitateDB の不足に合わせて緩める案は、それぞれ「契約変更なし」「peer の不足を埋めない」の原則により不採用
- application-plane の耐久 audit sink (フェーズ4。`audit_query` unavailable 継続の理由でもある)
- 実 GCP プロジェクトへの配備実行・Cloud SQL 実機検証 (運用者作業。runbook 化まで)
- Mitate 実装 repository (mitate-application) 側のクライアント実装 — DM-0018 の review trigger「MitateDB-api exposes the common Data Service API over HTTP」の成立が本フェーズの出口であり、クライアント着手はその後に Mitate repository 側の作業指示書で発注する
- r2db-api 側の変更 (L4 = `request_bytes` の control discovery 宣言は r2db の台帳項目のまま。本フェーズでは触らない)

## 1. 設計判断 (R-x。実装ポリシーであり契約変更ではない)

### R-1: 永続化トポロジ — database-per-application (Cloud SQL 互換で成立させる)

1つの PostgreSQL インスタンス (本番: Cloud SQL for PostgreSQL) 内に:

- **platform registry database** (`mitatedb_platform`): applications / credentials / control_credentials / control_audit の4テーブル
- **application database** (application ごとに1つ、名前は control plane が採番しクライアント入力から導出しない): その application のデータテーブルのみ

application ごとに専用 DB role を **runtime / developer の2つ**発行し、`REVOKE CONNECT ON DATABASE ... FROM PUBLIC` + 当該 application の 2 role のみ `GRANT CONNECT`。越境は grant 規律ではなく **DB 境界で構造的に不可能** (SI-00/SI-01)。runtime role は自 DB 内 DML のみ、developer role は加えて DDL (`create_entity` の実行主体)。

**Cloud SQL 適合条件** (superuser なし、`cloudsqlsuperuser` 付与モデル、**PostgreSQL 16 に固定**) を設計段階で固定する: 使用する管理 SQL は次の allowlist に限る (WP-0 M-7 で r2db の実測済み provisioning 所要語彙まで拡張):

- `CREATE/DROP DATABASE`、`CREATE/DROP ROLE`、`GRANT`/`REVOKE` (`GRANT <role> TO CURRENT_USER WITH SET TRUE` を含む — PG16+ 構文のため版固定の根拠)、`CONNECTION LIMIT`
- `REVOKE ALL ON SCHEMA public FROM PUBLIC`、`ALTER SCHEMA public OWNER TO <role>`、`SET LOCAL ROLE <role>`、`ALTER DEFAULT PRIVILEGES FOR ROLE <role> IN SCHEMA public`
- `pg_terminate_backend` (Cloud SQL では実行 role が `pg_signal_backend` member であることが前提 — runbook の実機検証手順に含める。`DROP DATABASE` 前の接続残存対策。terminate と DROP の間の再接続 race に備え retry を設けるか、PG13+ の `DROP DATABASE ... WITH (FORCE)` を代替として実測選択する — 第2ラウンド M-10)

superuser 専用機能 (untrusted PL、ALTER SYSTEM 等) を一切使わない。

**cloudsqlsuperuser 迂回の禁止 (第2ラウンド M-8)**: Cloud SQL の Users API / gcloud / Console で作成したユーザは `cloudsqlsuperuser` member となり `REVOKE CONNECT ... FROM PUBLIC` を迂回して任意 DB へ接続できる。application role は**必ず provisioning SQL の `CREATE ROLE` で作成し、Users API/Console での作成を runbook で明示的に禁止**する。provisioning 時に `pg_auth_members` を検査し、application role が `cloudsqlsuperuser` 非メンバーであることを fail-closed 検証する。`CONTROL_MAPPING.md` の SI-00/SI-01 行に配備前提として記録する。migrations ファイル冒頭に「Cloud SQL 適合語彙」の注記を置き、逸脱をレビュー対象にする。**証拠区分は正直に**: 本フェーズの実測はローカル PostgreSQL 16 クラスタ (Homebrew、`host=/tmp port=5432`、r2db テストと同一規約) のみで、Cloud SQL 実機 evidence は配備時まで absent と `security/CONTROL_MAPPING.md` に明記する。

代替案 (不採用): 単一 database + schema-per-application + RLS。共有 CONNECT 面が残り、単一実装欠陥での越境がやや可能になる (containment が grant/RLS 規律依存)。r2db が database-per-application で実測確立した安全結果と同型を、Cloud SQL 制約下で MitateDB 自身が検証して採る。RLS の defence-in-depth 併用は本フェーズでは見送り、台帳へ (§7)。

### R-2: 実行 choke point — 値は常に bind、識別子は二段検証、raw string は型で拒否

- psycopg 3。値は常に server-side bind パラメータ。文字列補間で SQL に値を入れる経路を作らない
- 識別子は (1) 既存 `identifiers.validate_identifier` の構文 allowlist、(2) 対象 database の生きた catalog (`information_schema`) との照合、の二段を通ってから `psycopg.sql.Identifier` でのみ合成。既存 `identifiers._RESERVED` は SQLite 固有 (`sqlite_sequence`) を含むため、予約名集合は backend 依存として backend 層に置く (構文 allowlist 本体は共有のまま。WP-0 m-7)
- 実行は単一 choke point 関数に集約し、型注釈と実行時型検査で `psycopg.sql.Composed`/`SQL` 以外 (特に `str`) を `TypeError` で拒否する — 「どのメソッドからも raw string を実行できない」ことをファイル構造で成立させる

これは r2db 内部構造の移植ではなく SI-04/SI-05 の要求結果の成立形。**実装コードの peer 間共有はしない** — 二重独立実装が conformance の検出力の源泉である実績 (peer 不適合3件はすべて差分から発見) を保つ。

### R-3: MitateDB 内部の backend seam — 検証・宣言は一箇所、実行は backend ごと

既存 `cell.py` (SQLite) の要求検証・capability 宣言・エラー分類・declare-and-echo 句構成のロジックを **backend 非依存の層**に抽出し、実行のみを backend (既存 SQLite / 新設 PostgreSQL) が担う構造にする。

- 目的: in-process adapter (`MitateDB-api`) と HTTP adapter (`MitateDB-api-http`) が**同一の公開意味論**を持つことを、注意力でなく構造で成立させる (宣言と実挙動の一致が二系統に分裂しない)。既知の許容差は3点のみで、いずれも台帳記録する: (1) C-17 unavailable 分岐の evidence 形態 (in-process = `SurfaceAbsent`、http = present denial。R-8 の共通側変更参照 — WP-0 B-2)、(2) catalog の absence 形態 (in-process = `CATALOG_SURFACE_ABSENT`、http = 実 `CAPABILITY_UNSUPPORTED` 拒否。C-11/C-12 は両形態を受理 — 第2ラウンド確認事項)、(3) NUL バイト等の backend 値ドメイン差 (SQLite = round-trip、PostgreSQL = 実行前の決定的 `VALIDATION_FAILED`。C-03 は両形態を受理 — 第2ラウンド M-11)
- 用語注記: 本書で「capability 宣言 (capability_document)」と呼ぶものの実体は `ApplicationRuntime.capabilities()` (第2ラウンド n-1)
- 既存 foundation テスト (`tests/test_foundation.py`) は SQLite backend に対して**公開 API の外部挙動不変**で通り続けること (回帰網)。ただし内部構造依存テスト (private シンボル `_canonical_where_json` の import 位置、`hasattr` によるクラス構造 assert、`test_limit_class_vocabulary.py` の AST 走査対象パス) は seam 移動に追従して更新してよく、その更新自体を独立レビュー対象にする (WP-0 m-3)。加えて同じ意味論テストを PostgreSQL backend にも課す
- seam の正確な切り方 (プラン生成方式か Strategy 方式か等) は実装裁量。ただし capability 宣言 (`capability_document`) の正本が単一箇所であることは要求
- SQLite backend は「ローカル決定的テスト用」の位置づけを維持し、配備対象にしない (`DATA_SERVICE_FOUNDATION.md` の宣言どおり)

### R-4: platform registry と面別ストア分離

`mitatedb_platform` 内:

| テーブル | 内容 | 書き手 |
|---|---|---|
| `applications` | application_id、状態 (enabled/disabled)、割当 DB 名 (**nullable — 二状態 registry**) | control plane |
| `credentials` | application credential の pepper-HMAC digest、role、状態 | control plane (発行/失効)、application 面は**読取のみ** (authenticate) |
| `control_credentials` | control credential の digest (専用 pepper)、must_rotate、状態 | control plane のみ |
| `control_audit` | 契約 `audit.fields` の 12 列 + recorded_at + **単調採番列 (bigserial)** — C-15 vector 2 の prefix 厳密比較は recorded_at だけでは同時刻で順序が揺れるため、採番列 + ORDER BY で安定順序を保証する (第2ラウンド m-2)。**INSERT-only** | control plane role (INSERT のみ。SELECT/UPDATE/DELETE 不可) |

- **プロセス role の分離**: application-plane プロセスは専用 role (例 `mitatedbsvc_api`) で registry へ接続し、`control_credentials`/`control_audit` への grant を一切持たない。control-plane プロセスは専用 role (例 `mitatedbsvc_controlplane`)。provisioning 権限 (CREATEDB/CREATEROLE を持つ例 `mitatedbsvc_provision`) は儀式/provisioning CLI のみが保持し、どちらの API プロセスにも渡さない
- **pepper 2本**: `MITATEDB_CREDENTIAL_PEPPER` / `MITATEDB_CONTROL_CREDENTIAL_PEPPER`。起動時に相違を検証 (同値なら起動拒否)。secret は Secret Manager 参照のみ、repo/イメージ/テストに実値を書かない (テストは synthetic 値)
- **credential store の二重実装**: 既存 in-memory `CredentialStore` (foundation/in-process adapter 用) と新設 Postgres 版が同一 call surface を持ち、parity テストで両者に同一挙動を課す。**parity の基準は「現行 in-memory の挙動」ではなく「契約の挙動」** (第2ラウンド M-2): 現行 `auth.py` の `revoke()` は `enabled=False` へ畳んでおり (conflate)、契約 `CredentialsResult`/`CredentialStateResult` が required とする `enabled` (可逆) / `revoked` (終局) の独立2値と不一致。両実装とも独立2値へ是正し、「`enable` は disable のみを戻し、revoked を決して復活させない」(契約 `enable_credential.semantics` / `lifecycle.credential`) を不変条件テストで固定する。DB 不達時は `AUTH_STATE_UNAVAILABLE` 系 fail-closed (資格情報の推測可能な劣化経路を作らない)
- **application_id の契約規則** (第2ラウンド M-9): control plane は application_id を契約 `control_plane.identifiers` の狭い規則 `^[a-z][a-z0-9_]{0,32}$` で検証する (既存 `identifiers.validate_identifier` の 63 文字規則は data-plane 識別子用であり流用しない)。database 名・role 名は application_id からの装飾導出でなく control plane が採番し、全長 63 バイト検証を課す (PostgreSQL NAMEDATALEN の黙った切り詰めで 2 application が role を共有する事故の予防)
- 越境不能の実測: 「application A の role では B の DB へ raw 接続もできない」「application 面 role では control テーブルへ SELECT もできない」を、facade 経由でなく**素の接続**で確認するテストを置く (r2db の `test_cross_database_connect_is_refused_at_the_database_level` と同型の検証を MitateDB 自身のテストとして)
- **二状態 registry** (WP-0 M-11): `register_application` は「登録済み (unprovisioned、`database_name` NULL)」状態を作り、provisioning 完了時に `database_name` を確定する。unprovisioned な application の data-plane `authenticate()` は fail-closed。crash-safety は r2db 実測の訂正 (`R2DB_CCR14_CONTROL_PLANE_V1.md` — provisioning の begin 側は registry に書かず、確定は finish 側) を設計時点で採る。deprovisioning は「登録のみで DB を持たない行」も撤去できること (C-14 vector 5 の後始末が要求)
- **prefix 置換方式** (WP-0 M-8): PostgreSQL の role は cluster-global のため、固定名 `mitatedb_platform` / `mitatedbsvc_*` は本番既定値であり、migrations 内では固定語幹 (`mitatedbsvc` / `mitatedb`) を1トークンとして書く。conformance/テストは r2db 同様の文字列置換で throwaway prefix (`mitatedbhttp{hex8}` 等 — r2db の `r2dbhttp`/`r2dbtest` と衝突しない語幹) に差し替え、残留物 sweep は prefix-anchored 正規表現 + advisory lock で行う
- **既存 `service.py::ControlPlane` との関係** (WP-0 m-8): 既存クラスは privileged provisioning facade であり、新設の in-band control plane とは責務が異なる。混同を避ける改名 (例 `ProvisioningFacade`) を WP-1 の seam リファクタに含める。既存 `provision_application` の `ValueError` (FoundationError 階層外) は安全分類へ載せ替える (正当な重複登録が「未捕捉例外 = SERVICE_UNAVAILABLE」に落ちる経路を残さない)

### R-5: application-plane HTTP 面 (`/v1`)

- Starlette ASGI 独立 app。応答は契約 `errors.shape` の problem+json。エラー本文に SQL・接続情報・例外原文・秘密を載せない (既存 `errors.py` の安全分類をそのまま HTTP へ写像)
- `request_bytes` (SI-08) は **ASGI receive ループで実受信バイト数を計測して** enforce し、パーサへ渡す前に `LIMIT_EXCEEDED`(`limit_class: request_bytes`) で拒否
- 契約 endpoint 7本を全て mount する。宣言 unavailable の capability に対応する endpoint (`/v1/data/mutations` = cross_entity、`/v1/audit/query`、`/v1/catalog` の `application_catalog`) は、**宣言どおり一様に `CAPABILITY_UNSUPPORTED`** を返す (宣言と実挙動の一致。逆向き C-12/C-11 が機械検出する)
- 認証: `Authorization` ヘッダの credential。欠落は `AUTH_REQUIRED`、無効は `AUTH_INVALID`、状態不達は `AUTH_STATE_UNAVAILABLE` (いずれも契約 `errors.codes` 内。fail-closed)。application/role はサーバ側の credential 状態からのみ導出 (C-01)
- body の `entity` フィールド密輸 (URL path の entity と別名を body に持ち込む) は unknown field として拒否 (契約 `endpoints.mutate.semantics`)
- **mutate バッチ意味論の収束 (P3-D2、第2ラウンド B-2 裁定)**: 現行 `transact` は insert のみ実行し update/delete を `CapabilityError` で拒否するが、宣言 `atomic_mutation.operations: [insert, update, delete]` + 契約「A batch is atomic unless explicitly declared best_effort」+ 当 peer `best_effort_transactions: unavailable` の下で、HTTP の mutate endpoint 1 本にはこの分裂を隠す場所がない (C-12 positive control は宣言 operations の実行を要求する)。**WP-1.5 で `transact` を update/delete まで atomic 拡張し、実挙動を既存宣言へ追いつかせる** (宣言の拡張ではなく収束)。バッチ内 delete は専用経路と同一の declare-and-echo 確認 (fingerprint 込み) を単一 choke で通す。これにより `DESTRUCTIVE_CONFIRMATION_V1.md` §8.1(b) の解釈論点 (「バッチ限定か一般語彙か」) は MitateDB では両解釈とも真になり実害が消滅する — 契約文言の明確化 CCR 自体は台帳残置のまま依頼者へ申し送る。C-06 V2b-wire は両 composition とも実分岐へ入る (destructive キーを wire から省略しつつ有効 confirmation を載せた形の拒否仕様を含む)。これは既存 in-process adapter の C-06 分岐が変わる公開面変更であり、「外部挙動不変」の明示の例外として単一 WP (WP-1.5) に隔離する
- **値ドメインの backend 差** (第2ラウンド M-11): PostgreSQL が実行時拒否する値 (NUL バイト等) は backend 実行前の**決定的 `VALIDATION_FAILED`** として拒否する (psycopg 例外の UNCLASSIFIED 化は C-03 の明示失敗)。SQLite backend の round-trip 挙動は不変 (R-3 の既知許容差 (3))
- **HTTP status の peer 間一致** (第2ラウンド m-12): 契約 `errors.http_status_note` は cross-peer での status 一致を conformance evidence として追跡すると定める。error code → HTTP status の写像は r2db の実マッピングと突合し、一致させるか、相違に理由を付して記録する (WP-3 完了条件)

### R-6: control plane (`/control/v1` + 儀式 CLI)

- **独立 ASGI app** (application-plane と別 app、別 Cloud Run service が既定。同居可能な構造にはするが既定は分離)
- 11 endpoint (`control_capabilities` / `register_application` / `list_applications` / `disable_application` / `enable_application` / `issue_credential` / `list_credentials` / `rotate_credential` / `revoke_credential` / `disable_credential` / `enable_credential`) を契約どおり実装
- **評価順序を固定する** (WP-0 M-6): `rate-limit 前段 → 認証 → 認可 → capability 判定 → 対象解決 → shape 検証 → (該当時) confirmation → precondition → 実行`。C-14 vector 1 は「不在対象 + 無権限」で `NOT_FOUND`/`CAPABILITY_UNSUPPORTED` が漏れないこと (= 対象解決より認証・認可が先) を、vector 3 は `role=control` の in-band 発行が対象の実在/不在/disabled/飽和のいずれでも一様に `CAPABILITY_UNSUPPORTED` であること (= capability 判定が対象解決より先) を機械検証する。契約 `evaluation_order` (shape→認証/認可→対象→confirmation→precondition→実行) と C-14 の要求を1つの順序表として実装の choke point に固定する
- **must_rotate credential の拒否コードは `FORBIDDEN`** (C-15 が完全一致を要求。WP-0 m-4)
- **`credentials_per_application` は revoked 行を数えない** (C-14 vector 3(iv)/5 は revoke 後にヘッドルームが戻る前提。r2db が `CONTROL_MAPPING.md` SI-08 行に明記した規則と同一。第2ラウンド M-3)
- **`list_credentials` は application + control credential の混載一覧** (C-15 vector 1 / C-06 V7 が role==control 行の列挙を要求。契約 role enum は [runtime, developer, control, audit]、`application_id` は optional。第2ラウンド m-6)
- **制御面応答は契約 schema の完全一致** (全結果型 `additionalProperties: false` — 余剰キー 1 つで C-11 赤。第2ラウンド m-7)
- **control discovery (`control_capabilities`) は `request_bytes` を最初から宣言する** (r2db の既知ギャップ L4 を再生産しない。実 enforce と同一コミット。第2ラウンド m-10)
- **in-process composition の control 監査 shape も契約 `audit.fields` の 12 フィールド** (foundation の 6 フィールド `AuditSink` とは別物として実装。第2ラウンド m-3)
- **rate limit window とスケールの整合** (第2ラウンド M-7 裁定): window はプロセス内実装とし、**control service の `max-instances=1` を runbook 不変条件に固定**する (DM-0018 の application 側 in-memory pin と同型の正直な固定)。共有 window 化・`deployment_required` 宣言への切替は将来課題台帳へ (§7)。conformance build は単一 ASGI プロセスなので宣言 `enforced` は真
- **儀式意味論の正本は再利用可能な product code** に置き、CLI (`ops`) と in-process adapter の双方が同一コアを呼ぶ (C-15 は in-process adapter にも実の儀式実行を要求し、adapter が credential 行を捏造することを禁じる — r2db が `ops.py` から `control_plane.py` へコアを抽出したのと同型。WP-0 m-6)
- **状態変更は監査行と同一トランザクション**で書く — 耐久書込失敗は状態変更ごと abort (fail-closed by construction)。認証・認可の**拒否イベントも耐久記録**する。例外は2系統のみ: (i) rate-limit 前段拒否 (認証前・audit 増幅 DoS 防止)、(ii) `AUTH_STATE_UNAVAILABLE` (store 自体が不達で監査書込も不能)。この2例外は r2db が条件付き承認で確立した形と同じ理由で採用し、コード注記と CONTROL_MAPPING に明記する
- **bootstrap / reset は out-of-band CLI** (`python -m mitatedb_api.ops`)。in-band に置かない。**CLI entry point (`ops` module) の新設は WP-5 の flip コミットに置く** (第2ラウンド M-5 裁定): WP-4 で CLI を作ると、adapter の bootstrap/reset `SurfaceAbsent` 主張が「実 CLI が存在するのに absent を申告する」実態虚偽の期間を作る (port の SurfaceAbsent 定義は source inspection で確認された全面不在のみを許す)。WP-4 は儀式**コア** (再利用可能な product 関数、直接テスト) までを実装し、operator が起動できる entry point は宣言 flip と同時に現れる。契約 `control_plane.bootstrap` の全条項を満たす: bootstrap は control credential 行が (revoked 含め) 1行でも存在すれば `CONFLICT`、reset は全 control credential を atomic に revoke し新規1本だけ mint、初回 credential は **must_rotate 方式**で非恒久 (capabilities と self-rotate 以外を拒否、実 rotation 完了で解除)
- **declare-and-echo** (契約 1.2.0): CLI の不可逆 subcommand (reset / credential 削除系 / **deprovision** — WP-1 レビュー m-12: deprovision は credential 行を含む application 名前空間の終局撤去であり、旧 guard 廃止後の唯一のインターロックとして CLI gate に載せる) と、in-band の「最後の有効 control credential の revoke」gate に適用。句はサーバが宣言しクライアントが復唱する方式のみ (Q1-D2)。判定は完全一致、truthy 受理なし
- **資源境界 3 クラス** (`applications` / `credentials_per_application` / `control_requests_per_minute`) を実 enforce し discovery (`control_capabilities`) で `enforced` 公開。C-14 vector 5 は「宣言した bound の正確な位置で拒否が起きる」ことを位置算術で検証するため、bound は composition root で設定可能にし、conformance adapter が自身の consumption を織り込める値を選べること。**設定値の数値制約** (WP-0 M-5、C-14 実装からの逆算): 3クラスとも `≤ 200` (`_MAX_EXERCISABLE_LIMIT`) **【訂正注記 2026-09-04】製品側の受理レンジ上限はフェーズ5 WP-4 (依頼者裁定 Q3 = 案 A) で撤廃された** — `ControlPlaneLimits.__post_init__` は 4 クラスとも「正の整数であること」しか検査しない。`_MAX_EXERCISABLE_LIMIT` は**製品の上限ではなく conformance 構成側の上限**として残る: C-14 vector 5 は宣言 bound の正確な位置で拒否が起きることを位置算術で検証するため、**駆動コストが構成値に比例して伸びる** (現行値でも `conformance-tests/test_c14_authority_boundary.py` の 4 件で約 249 秒)。この 2 つを混同しないこと (設計 `docs/design/PHASE5_CONTRACT_150_AND_LIMIT_RANGE_V1.md` §3 D-3 / §6.4 / §11 L5-7)。以下の不等式・実測値は当時の記述である、`control_requests_per_minute > applications + 2 × credentials_per_application + 67` (headroom+margin 不等式)、`applications` は suite 実行1回の累積登録数を上回ること (r2db-http 実測: vector 5 到達時 80、session 終了時 89 に対し `applications=100, credentials_per_application=5, control_requests_per_minute=200`)。WP-5 の完了条件に in-process / http 両 adapter での n_existing 実測記録を含める
- **un-revoke はどこにも作らない** (revoke の終局性、C-13/SI-13)。disable からの復旧は CLI break-glass (enable/rotate)、revoke からの正準復旧は reset 儀式のみ。拒否応答には r2db R-11 で確立した「真実の宣言」(徒労・帰属・監査済みの事実) を、MitateDB の実態に対して真実である範囲で載せる (虚偽の宣言は禁止 — 例: 耐久監査が実在しない面に `audited: true` を言わない。Q1-D6)

### R-7: capability 宣言は composition root 注入、環境ごとの実挙動と一致させる

- `request_bytes` は現在 `limits.request_bytes` の数値は公開済みで、`limit_enforcement.request_bytes` のみ `unavailable` (in-process にはワイヤが存在せず実挙動が無いため真実。WP-0 N-4 の精緻化)。HTTP composition では**実 enforce と同一コミットで enforcement 側を `enforced` 宣言**へ。in-process composition は `unavailable` のまま (実挙動どおり)
- `control_plane` は WP-5 の flip まで両 composition とも `unavailable` のまま。**flip は「/control/v1 の mount + 宣言変更 + C-14/C-15 PROVIDED 緑」を単一コミット**で行う (「申告と実挙動は単一コミットでしか同時に動かさない」規律)。それまで control 面コードは公開 composition に mount しない — declared-unavailable form (b) の状態を一瞬も経由しない (form (b) の authenticity 限界を踏まないため)
- 限度値・宣言値は環境変数 (`MITATEDB_*`) で composition root から注入し、宣言値と enforce 値が同一ソースから出ることを構造で保証する (宣言数値と実閾値の乖離 = Q1-D11 で不採用にした形を作らない)

### R-8: conformance — 第4 adapter `MitateDB-api-http`

- plug: `MitateDB-api/conformance/conformance_adapter_mitatedb_http.py` (module `conformance_adapter_mitatedb_http`)。`registry.json` に **required** で登録。登録位置は既存 `MitateDB-api` エントリより**後** (conftest は registry の `name` から conformance ディレクトリを sys.path に積むため、`MitateDB-api-http` という name 単独ではディレクトリが解決されず、先行エントリへの順序依存がある — r2db-api-http と同じ構造。WP-0 m-1)
- plug オブジェクトの `name` **属性**は `"MitateDB-api (http+postgres)"` とし、in-process plug の `"MitateDB-api"` と別値にする (C-06 の Fixture / capability document キャッシュは `.name` キーであり、同値だと in-process の Fixture が http 側テストへ静かに流用される。r2db-http の `"r2db-api (http+postgres)"` と同じ回避。WP-0 M-3)
- 実 HTTP (httpx / ASGITransport) + 実 PostgreSQL (throwaway-prefix database、R-4 の prefix 置換方式)。admin DSN knob は `MITATEDB_TEST_ADMIN_DSN`、既定 `host=/tmp port=5432 dbname=postgres` (r2db 規約と同一)。**DSN 不達時は skip でなく fail** (r2db `test_postgres.py` の「skip 禁止」条項と同じ。WP-0 m-9)。儀式は実 CLI subprocess (`python -m mitatedb_api.ops bootstrap`/`reset`) — MitateDB-api は未インストールのため subprocess env に `PYTHONPATH=MitateDB-api/src` を明示注入する (WP-0 m-11)
- C-14/C-15 の PROVIDED 化は **in-process / http 両 adapter** に対して行う (in-process は in-memory control store + 儀式コア直結、http は Postgres store + CLI subprocess — r2db WP-5 と同じ二形態)
- **共通側変更 (2件、WP-2.5 として独立レビュー・単独コミット。WP-0 B-2 / M-4 裁定)**:
  1. **C-17 unavailable 分岐への present-denial 形態追加**: 現行は `SurfaceAbsent` を強制するが、`/v1/schema/operations` を mount した MitateDB-http では `create_index` を受け取る実 entry point が存在するため、正直な evidence は `ConformanceDenial(CAPABILITY_UNSUPPORTED)` である (port 自身が「実 entry point があるのに SurfaceAbsent を使うことを禁止」している)。C-18 が既に持つ「real, present denial」受理と同型の分岐を C-17 に追加する。既存 3 adapter の分岐は不変
  2. **C-11 の `_find_adapter_with` を全 adapter 反復へ**: 現行は最初に見つけた 1 adapter しか raw response 検証しないため、「2 adapter 目の実文書を得る」という本設計の主張は suite 変更なしには成立しない。raw accessor を持つ**全** adapter の実文書を検証する形に変更する (既存挙動の緩和ではなく検証範囲の拡大のみ)
- adapter 追加に伴う既存 guard の同一コミット更新 (WP-3): `test_c06_destructive_confirmation.py` の `_EXPECTED_STRICT_ADAPTER_NAMES` に `MitateDB-api-http` を追加 (guard は集合完全一致 assert であり、更新なしでは登録コミットで無条件赤化。失敗メッセージ自身が同一コミット更新を要求。WP-0 M-2)
- WP-3 時点 (control flip 前) の port op 形態: `deprovision_application` を含む control 系 16 call は **`SurfaceAbsent` のまま**とする (C-14 の絶対性主張は形態の一様性を要求。WP-1 で実 deprovisioning コードが存在しても、port op として公開するのは WP-5 の flip 時。WP-0 m-2)
- `control_audit_events()` の観測用に owner/admin role 接続の**別 reader** を adapter 側に用意する (R-4 で control-plane role から SELECT を剥奪するため。r2db-http と同型。WP-0 m-5)
- **C-13 `credential_reactivation_vectors` の書き換えは flip と同一コミット** (第2ラウンド M-4): 現宣言 structurally_absent の根拠「CredentialStore に un-revoke / enable 呼出が一切ない」は `enable_credential` 実装の瞬間に偽になる。WP-5 で「revoked への enable(True)」の実ベクタ (must_deny) へ書き換え、R-4 の enabled/revoked 独立2値と同時に成立させる
- **adapter の control credential handle はキャッシュし毎回 probe しない** (第2ラウンド m-16): r2db-http の実測教訓 (setup traffic だけで rate window を使い切った)。handle が死んでいたら実 reset で修復 (port の規定形)。同様に、in-process adapter の `capability_document()` が呼び出しごとに probe application を provisioning する現挙動 (実測: MitateDB 抽出 66 テストの session で 155 application 中 39 が probe 由来) は WP-3/WP-5 で probe 再利用へ是正する — C-14 bound 不等式のヘッドルームと HTTP composition の実 DB/role 生成数 (155 app = 155 DB + 310 role) を直接圧迫するため (第2ラウンド M-1)
- 実行コストの増分 (WP-0 m-10 / 第2ラウンド n-3): C-14 provided 分岐は rate-limit window 回復の `sleep(61)` を含むため、MitateDB 2 adapter の provided 化で root suite は**約 +122 秒**、テスト増分は約 +66〜70 件 (第2ラウンド実測)、http adapter は session 中に実 database を r2db-http 同規模 (~90個以上) 作成・破棄する。§3 の「root suite 完走」条件はこのコストを織り込んで維持する
- 上記 2 件以外の port (`conformance-tests/adapter.py`) の変更は原則なし。実装中に追加の port 変更が必要になった場合は「peer の不足を埋めない」原則の下で設計論点として明示し、共通側の変更として単独レビューを通す

### R-9: 配備資産 (Cloud Run / Cloud SQL)

- `MitateDB-api/docker/Dockerfile`: multi-stage、非 root、実行は uvicorn。data-plane / control-plane を同一イメージ・別 entrypoint で起動できる形
- runbook `MitateDB-api/docs/cloud-run-cloud-sql.md`: Cloud SQL インスタンス作成、registry/role の bootstrap 手順 (provisioning 権限は運用者/儀式のみ)、Secret Manager への pepper/DSN 登録、2 Cloud Run service (data: mitate-application の SA のみ invoker / control: 運用者のみ、`--no-allow-unauthenticated`)、Cloud SQL 接続 (unix socket DSN)、Cloud SQL 実機での適合検証手順 (R-1 の語彙が実機で通ることの確認コマンド列)。**runbook 不変条件 4 本** (第2ラウンド M-7/M-8/m-13、WP-1 レビュー m-4): (1) control service は `max-instances=1` (rate limit window のプロセス内実装が `enforced` 宣言の真実性条件)、(2) application role の Users API/Console 作成禁止 (R-1 の cloudsqlsuperuser 迂回)、(3) control service を停止/未配備にする場合は data 面の `control_plane` 宣言 env を同時に変更する (2サービス分離下では宣言が operator 申告になるため、宣言と実態の結合を手順で保証する)、(4) provisioning 実行セッションでは `log_statement` 等の文ログを無効化する (provisioning password は plpgsql `%L` リテラルとして流れるため、文ログ有効時に平文が載る)
- コードは Cloud を知らない: 接続は DSN 注入のみ。IAM DB 認証・Cloud SQL Connector の採否は将来強化として台帳へ (§7)
- 配備の実行・GCP project 作成・secret 実値投入は運用者作業 (Mitate repo CLAUDE.md の絶対事項と同じ規律)

## 2. endpoint → 実装対応 (application plane)

| 契約 endpoint | 実装 |
|---|---|
| `GET /v1/capabilities` | composition root 注入の capability 宣言を返す (**application 認証のみ**。契約 `versioning.control_discovery` の control 認証受理は co-hosting convenience であって要求ではなく、R-4 の面別 store 分離の帰結として採らない — application-plane プロセスは control credential を検証する手段を構造的に持たない。WP-0 M-9) |
| `POST /v1/data/{entity}/query` | backend seam 経由 structured query (宣言 envelope: eq 系 `_OPS`、`contains`/`matches`/`is_null` は `CAPABILITY_UNSUPPORTED`)。契約 core shape の写像 (クライアント実要求の確認結果): `order_by` 配列は **multi-field sort として実装** (現 cell の単一 dict から seam で拡張)、`page.size` → limit、`page.cursor` は未実装 (受理時は契約語彙内で決定的に拒否し分類を記録 — conformance 非被覆領域、cursor 対応は台帳へ)。field_type `object`/`array` → cell native `json` の写像を定義 |
| `POST /v1/data/{entity}/mutations` | insert / update / delete (delete は declare-and-echo)。`upsert`・`expected_revision` は `CAPABILITY_UNSUPPORTED`。body 内 `entity` は unknown field 拒否 |
| `POST /v1/data/mutations` | `CAPABILITY_UNSUPPORTED` (cross_entity_mutation: unavailable) |
| `GET /v1/catalog` | `CAPABILITY_UNSUPPORTED` (application_catalog: unavailable — 現宣言のまま) |
| `POST /v1/schema/operations` | `create_entity` + `add_field` (developer。P3-D1 — 混合型 entity は契約形状では create + field ごとの add_field でしか構築できない)。他 op は宣言どおり `CAPABILITY_UNSUPPORTED` (present denial — C-17 の evidence 形態は R-8 の共通側変更参照) |
| `POST /v1/audit/query` | `CAPABILITY_UNSUPPORTED` (audit_query: unavailable、フェーズ4) |

control plane は契約 `control_endpoints` の 11 本を R-6 のとおり。

## 3. WP 分割

| WP | 内容 | 公開面への影響 |
|---|---|---|
| **WP-0** | 本設計の独立レビュー。blocker/major 全消化で v1.1 確定 | なし |
| **WP-1** | PostgreSQL 基盤: `MitateDB-api/pyproject.toml` 新設 (依存宣言: starlette / psycopg[binary] / uvicorn / httpx。WP-0 M-10)、migrations (platform registry 二状態 / provisioning SQL、Cloud SQL 適合語彙注記、prefix 1トークン規律)、R-3 backend seam (cell.py の公開挙動不変リファクタ、既存 `ControlPlane` facade の改名と `ValueError` 再分類)、**`add_field` 解禁 (P3-D1、宣言+実装+テスト単一コミット、SQLite/PG 両 backend)**、**delete 確認句への schema fingerprint 追加 (add_field 解禁の帰結、同一コミット)**、Postgres data backend (query/insert/update/delete/create_entity/add_field)、database-per-application provisioning/deprovisioning (application_id 契約規則 + 採番 + 63バイト検証)、値ドメイン検証 (NUL 等の決定的 VALIDATION_FAILED)、実 PG テスト (越境拒否の素接続検証含む) | あり (in-process adapter の `schema_operations` 宣言に `add_field` が加わり、delete 確認句が fingerprint 化。他は不変) |
| **WP-1.5** | **mutate バッチ意味論の収束 (P3-D2)**: `transact` の update/delete atomic 拡張 + バッチ内 delete の declare-and-echo 単一 choke + C-06 V2b 実分岐対応。外部挙動変更を本 WP に隔離 | あり (in-process adapter の C-06 分岐が absence → 実分岐へ。宣言は不変 — 実挙動が既存宣言へ収束) |
| **WP-2** | credential 永続化: Postgres 版 application credential store、**enabled/revoked 独立2値化 (in-memory 側も契約挙動へ是正)**、契約挙動基準の parity テスト、pepper 検証、DB 不達 fail-closed | あり (in-memory store の revoke/enable 意味論が契約へ是正される — 現 conformance は非依存だが公開面変更として記録) |
| **WP-2.5** | **共通側変更 (単独コミット・独立レビュー)**: C-17 unavailable 分岐への present-denial 形態追加 + C-11 `_find_adapter_with` の全 adapter 反復化 (R-8)。加えて WP-1.5 レビュー繰延べ2件: test_c06 の docstring (「MitateDB の transact は insert のみ」) の陳腐化訂正、`_batch_delete_capability_absent` の absence 分岐が全 adapter で到達不能になった事実の CONDITIONS.md 記録 (baseline 分岐の残置宣言と同じ前例)。既存 3 adapter は全数緑のまま | なし (共通 suite の検証範囲拡大のみ) |
| **WP-3** | application-plane HTTP 面 + composition root (serve) + `MitateDB-api-http` adapter 登録 (`_EXPECTED_STRICT_ADAPTER_NAMES` 同一コミット更新、control 系 port op は SurfaceAbsent 維持)。`request_bytes` enforcement 宣言は本 WP (実挙動と同一コミット)。→ 既存 executable 全条件が 4 adapter で緑 (C-14/C-15 は http 側も surface-absent) | あり (新 adapter 追加。既存 adapter の挙動不変) |
| **WP-4** | control plane 本体: control credential store 二重実装 + parity (enabled/revoked 独立2値)、ControlPlaneService (同一 tx 監査・rate limit・bounds・評価順序)、**儀式コア (product 関数、declare-and-echo。CLI entry point は作らない — R-6)**、control HTTP app (**未 mount**)、**topology 実行可能証拠** (r2db の AuthorityTopology/test_topology.py 相当 — CONTROL_MAPPING の TBD を文書だけで閉じない。第2ラウンド m-14)。全て直接テスト | なし (公開 composition に mount せず、CLI entry point も不在) |
| **WP-5** | **宣言 flip 単一コミット**: /control/v1 mount + `control_plane: enabled` (両 adapter) + **儀式 CLI entry point (`ops`) 新設** + **C-13 reactivation 実ベクタ化** + capability_document probe 再利用化 + C-14/C-15 PROVIDED 初実行 (両 adapter で n_existing 実測記録)。**WP-4 申し送り**: (i) 2ストア表現の突合 — WP-4 が control 用に新設した applications/credentials 書込 registry と、WP-2 の application 面 `auth.CredentialStore`/`credential_store_postgres` (読取) が同一 `credentials` テーブルを別 Python 表現で扱う。in-band 発行した credential を application 面 `authenticate` が読む突合テストを完了条件に含める。(ii) `ControlPlaneLimits` の実測較正 (n_existing)。(iii) reset の out-of-band confirmation-mismatch 拒否の監査方針 (N-1: in-band は拒否監査するが out-of-band 儀式は成功時のみ audit_append — CLI 実装時に方針確認)。厳格分岐の初実行 WP として「発見一覧」を成果物に含める | あり (C-14/C-15 が PROVIDED 分岐へ、C-13 が実ベクタへ) |
| **WP-6** | 記録整理: Dockerfile / runbook、`security/CONTROL_MAPPING.md` の MitateDB 列 TBD 解消 (実在テスト名の引用、Cloud SQL 実機 evidence absent の明記)、`CONDITIONS.md` 更新、README、将来課題台帳、引き継ぎ | なし (ドキュメント) |

各 WP の完了条件 (共通):

1. テスト追加 + **変異注入** (テストが守る性質を壊す変異で赤化を実測 → scratchpad 経由復元・diff 一致確認。`git checkout` 不使用)
2. **root suite 完走** (契約ファイル・共通文書を触らない WP でも完走。現基準 814 passed + 本フェーズの増分)
2b. **宣言語彙を持つ call site の全数固定の維持** (第2ラウンド m-8): `ResourceLimitError` の emission 箇所を増やす WP は `test_limit_class_vocabulary.py` の期待件数を同一コミットで更新する (WP-1 PG backend / WP-3 request_bytes / WP-4 control bounds が該当)
3. 独立レビュー往復 (実装者報告は実測で裏取り)
4. commit / push / main merge (`--no-ff`) を1セット。push 前に identity 確認 (r2fish noreply のみ)

## 4. リスクとレビュー重点

- **provided 分岐の初実行が WP-5 に集中する**: 静的レビューのみで確定したコードは初回実行まで実証されていない (CCR-14 WP-5・Q-1 WP-3/5 で毎回実証)。WP-5 は「初回実行デバッグの発見一覧」自体を成果物にし、conformance suite 側の想定漏れと製品欠陥を切り分けて記録する
- **Cloud SQL 適合が実機未検証のまま進む**: R-1 の語彙 allowlist と runbook の実機検証手順で「何が未検証か」を機械的に列挙可能にする。実機で語彙が拒否された場合は設計改版 (このリスクは正直に CONTROL_MAPPING に残す)
- **cell.py リファクタ (R-3) の外部挙動**: foundation テスト・in-process conformance の全数が回帰網。リファクタ WP では「外部挙動不変」を明示の完了条件にする (WP-2 B-1 の教訓: 検証層の位置を動かすと公開面が動く)
- **接続数の有限性**: Cloud SQL の max_connections は小さい。application ごとの接続は bounded pool (上限は設定注入)、role には `CONNECTION LIMIT` を掛け、テスト/adapter は接続を確実に閉じる (r2db-http adapter が `CONNECTION LIMIT 10` を使い切った実例の予防)
- **SQLite / PostgreSQL の意味論差** (型・照合順序・エラー分類): 同一 conformance fixture が両 adapter に走ること自体が検出網。差分が出たら「どちらが契約に適合か」を契約文言から判定し、契約が定めない領域なら独断で閉じず記録・提起 (Q-1 §8.1(b) の前例)
- **C-14 vector 5 の位置算術**: bound 設定値は adapter 自身の累積 consumption を織り込む必要がある (r2db の `n_existing=80` 実測)。MitateDB 側も同じ計測を完了条件に含める

## 5. 申し送り (依頼者への報告事項 — いずれも覆せる)

1. **D-A**: 永続化トポロジは database-per-application (R-1)。代替 (schema + RLS) は不採用、RLS 併用は台帳送り
2. **D-B**: スタックは Starlette + psycopg 3 + uvicorn — r2db と同一の実行環境部品だが、**実装コードの共有はしない** (二重独立実装の検出力維持)
3. **D-C**: C-14/C-15 の PROVIDED 化は in-process / http の両 adapter に対して行う (r2db WP-5 と同じ二形態)
4. **D-D**: capability envelope は本フェーズで凍結 (スコープ外節)。拡張は mitate-application の実要求確定後に別フェーズで判断
5. **D-E**: IAM DB 認証・RLS defence-in-depth・application-plane 耐久 audit sink (フェーズ4)・Cloud SQL 実機検証は台帳へ (§7)
6. **D-F**: 配備既定は data-plane / control-plane を別 Cloud Run service (同一イメージ・別 entrypoint)
7. **D-G (= P3-D1)**: `add_field` を本フェーズで解禁 (§0 例外節。凍結の趣旨に対する最小の例外であり、第4 adapter 成立の実需要による)
8. **D-H**: 共通 conformance suite への変更 2 件 (C-17 present-denial 形態、C-11 全 adapter 反復) を WP-2.5 として実施 (R-8。単独コミット・独立レビュー)
9. **D-I**: L4 (r2db `request_bytes` の control discovery 宣言) は引き継ぎ書 §3 で「次のコード WP へ繰延べ」とされていたが、本フェーズでは扱わない (r2db 側を触らない原則優先の意図的逸脱。r2db の台帳項目として残置 — WP-0 N-3)。なお MitateDB 側は最初から宣言する (R-6) ため同ギャップは再生産しない
10. **D-J (= P3-D2)**: mutate バッチの update/delete atomic 拡張 (R-5)。実挙動を既存宣言 `atomic_mutation.operations: [insert, update, delete]` へ収束させる。`DESTRUCTIVE_CONFIRMATION_V1.md` §8.1(b) の解釈論点は MitateDB では実害消滅、契約明確化 CCR は台帳残置のまま
11. **D-K**: control service `max-instances=1` を runbook 不変条件とする (rate limit のプロセス内 window の真実性条件。共有 window / deployment_required 化は台帳へ)
12. **D-L (依頼者判断待ち → クライアント側正式回答受領、最終確認待ち)**: mitate-application の実要求棚卸し (Mitate repo `docs/work-orders/mitate-application-data-service-client-phase-b-requirements.md`) が **`cross_entity_mutation` の凍結解除検討**を要求。**2026-08-30 クライアント側セッション (mitate-cd) から「採用 — フェーズ3.5 として実装依頼」の正式回答を受領** (同文書 v1.2 §6 が正本): (i) 監査保証 (成功した状態変更 = ちょうど1 audit event) は原子性の問題であり max-instances=1 (直列化) では crash 窓を消せない、(ii) 代替3案は全て不採用、**保証を毀損する縮退でのカットオーバーは行わず cross_entity_mutation 成立まで Phase B カットオーバーを待つ** (現行 in-memory 継続)、(iii) スコープ下限: 1 atomic unit = 複数 entity にまたがる insert/update/delete の列 (全成功 or 全無効)、batch 上限 10 で十分、upsert / read-your-writes / preconditions / 実行順序観測は不要、新エラー語彙不要。C-16 executable 化と共通 suite 作業の発生は了解済み。**本フェーズ (3) は現行スコープのまま完了させる。フェーズ3.5 の着手は、他セッション経由の伝聞を依頼者承認とは扱わない規律により、本セッションの依頼者の直接確認を待つ** (完了報告で提起)

## 6. 本フェーズが閉じる既存台帳項目 / 閉じない項目

- 閉じる: `CONTROL_MAPPING.md` MitateDB 列の「TBD during implementation」のうち、control plane 分離・credential 永続化・propagation bound・HTTP 面 SI-10 系、および SI-08 の**部分** (`request_bytes` と control 面 rate のみ。application-plane の request rate / concurrency / execution time は本フェーズでも未実装のまま — §7 台帳へ。WP-0 M-1) (いずれもローカル実測 evidence として)
- 閉じない (明示継続): Cloud SQL/Cloud Run の production platform evidence (`foundation.json` の platform_evidence_required_before_production 3項目は配備時)、application-plane 耐久 audit sink (フェーズ4)、`audit_query` の C-11 zero-coverage (フェーズ4)、**C-16 (cross_entity_mutation 両 peer unavailable のため本フェーズ後も非 executable — 第2ラウンド n-2。D-L の依頼者判断で変わりうる)**、契約 additive 候補束 (`DESTRUCTIVE_CONFIRMATION_V1.md` §8.1(e)、1.3.0 検討時一括)

> **RESOLVED 追記 (2026-09-03、フェーズ4 WP-4 記録整理。上記「閉じない」列挙の原文は記録として保存)**: 上の 3 項目のうち 2 項目が閉じた。**application-plane 耐久 audit sink** は `mitatedb_registry.application_audit` (migration `0005`) として出荷され、**`audit_query` の C-11 zero-coverage** も解消した (`AuditResult` の逆向き検証が登録済み 4 adapter すべてで実文書に対して走る)。あわせて本書 §0 スコープ外節・§4 の endpoint 表 (`POST /v1/audit/query` の行)・§5 D-E が述べる「`audit_query` unavailable 継続」は、**data-plane ホストについては現在も真** (このホストは当該 capability を提供しないので `CAPABILITY_UNSUPPORTED` を返す) だが、**control ホストでは `enabled` であり `contract_version` は 1.4.0** である。**C-16** はフェーズ3.5 で executable 化済み。正本は `docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md` (v1.5) と `security/CONTROL_MAPPING.md` の SI-14 行。

## 7. 将来課題台帳 (本フェーズ新設分)

- **cross_entity_mutation の採否 (D-L)**: mitate-application の実要求 (本体 + audit の 2 entity atomic 書込)。依頼者判断待ち — 採用ならフェーズ3.5 として設計し C-16 を executable 化
  > **SHIPPED — 追記 (2026-08-31、フェーズ3.5、house style — 原文は上記のまま保持)**: 依頼者直接承認 (2026-08-31)。フェーズ3.5として設計・実施し (`docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md`)、WP-2 (MitateDB 実装: 二段パス transact + batch_entities + HTTP 実体化 + 宣言 flip)・WP-3 (共通 suite: port v1.7 + C-16 新設・executable 化 + C-11/C-12 拡張) で出荷完了した。契約は 1.3.0 (WP-1、意味論明確化のみ、wire 形状新設なし)。C-16 は4 adapter で executable — MitateDB 2 adapter は PROVIDED 分岐 (V1〜V4)、r2db 2 adapter は ABSENT 分岐 (V5、P35-D1 により r2db 側は採用せず継続 unavailable)。
- **control rate limit の共有 window / deployment_required 化** (D-K の将来強化。max-instances>1 スケールが必要になったとき)
- **revision_preconditions** (mitate-application が複数 instance 化したとき必須 — クライアント要求棚卸し C 節)
- **application-plane の request rate / concurrency / execution time 境界** (SI-08 の残クラス。WP-0 M-1): Cloud Run の concurrency / max-instances / timeout を配備層 enforce として使う場合は `limit_enforcement: deployment_required` の宣言まで含めて別フェーズで設計する (契約 `capability_status.rules` — deployment_required is not an application-code proof)
- **positive-existence check の設計 (WP-3 レビュー M-1 の帰結)**: CONDITIONS.md の C-14/C-17 が「form-(b) peer が登録されるまで DEFERRED」としていた positive-existence check のトリガーが、MitateDB-api-http の登録 (schema ops を mount しつつ create_index/drop_entity を present denial) で発火した。加えて対称的な限界が判明: HTTP peer の公開面は JSON operation enum であり、form-(a) SurfaceAbsent の独立検証 (`signature_forbids_parameters` = Python callable シグネチャ検査) は wire 語彙を検証できないため、「実際は mount しているのに SurfaceAbsent を偽装する」HTTP peer を機械検出できない (実測: drop_entity を偽 SurfaceAbsent に戻す変異が C-06 V3/V6 を赤化させない)。**安全性の本質 (index/entity が実際には作られ/消されていないこと) は present-denial 側の (d) probe が既に押さえており**、残る gap は「peer がどの evidence 形態を主張するかの自己整合性」= gaming vector のみ。port op としての positive-existence check (entry point の実在を wire レベルで実証させる仕組み) を将来設計する。本フェーズでは CONDITIONS.md に限界を正直に開示するに留める (C-14 の既存 DEFERRED 開示と同じ流儀)
- RLS defence-in-depth の併用 (R-1 不採用分。database-per-application が主境界として実測確立した後の追加層として)
- IAM DB 認証 / Cloud SQL Connector の採否 (現行: 標準 DSN + Secret Manager 参照)
- application database の `CONNECTION LIMIT` / pool 上限の運用チューニング (初版は保守的な固定値)
- **platform registry 接続の bounded pool** (WP-2 レビュー N-1): `PostgresCredentialStore` は呼出ごと新規接続 (WP-2 の意図的判断 — fail-closed の一様観測)。HTTP 面では assert_active が操作ごとに走るため `mitatedbsvc_api` の `CONNECTION LIMIT 20` と衝突する — **WP-3 の composition で bounded pool 化または接続再利用が必須** (WP-3 完了条件に含める)
- MitateDB の `drop_entity` / `drop_index` (schema 削除系) — 現宣言 unsupported のまま。C-06 V6 は共有 absence 機構継続

## 8. 訂正記録 (WP-0 独立レビュー)

WP-0 独立レビュー (Opus、2026-08-30) の結果: **blocker 2 / major 11 / minor 11 / note 5**。全指摘を監督裁定のうえ v1.1 へ反映した。

- **B-1** (契約 `SchemaOperationRequest` の単一 `field_type` と混合型 fixture の不整合): `add_field` 解禁 (P3-D1、§0 例外節・§2・WP-1) で解決。契約 CCR / 共通 suite 緩和は不採用 (理由は §0 例外節)
- **B-2** (C-17 unavailable 分岐の `SurfaceAbsent` 強制と mount 済み entry point の矛盾): 共通側変更 WP-2.5 を新設 (D-H)。R-8 の「port 変更なし」「WP-3 で全条件緑」の当初主張を訂正
- **M-1** SI-08「閉じる」の過大主張を §6 で部分化し、残クラスを §7 台帳へ / **M-2** `_EXPECTED_STRICT_ADAPTER_NAMES` 同一コミット更新を WP-3 完了条件へ / **M-3** plug `name` 属性の別値化を R-8 へ / **M-4** C-11 主張は WP-2.5 の全 adapter 反復化で成立させる / **M-5** C-14 vector 5 の数値制約 3 本を R-6 へ / **M-6** 評価順序表を R-6 へ / **M-7** Cloud SQL 語彙 allowlist の拡張 + PostgreSQL 16 固定を R-1 へ / **M-8** prefix 置換方式を R-4 へ / **M-9** `/v1/capabilities` を application 認証のみに訂正 (§2) / **M-10** `MitateDB-api/pyproject.toml` を WP-1 成果物へ / **M-11** 二状態 registry を R-4 へ
- **m-1〜m-11** (registry 順序 / deprovision SurfaceAbsent 維持 / 回帰網主張の精緻化 / `FORBIDDEN` / 監査 reader / 儀式コア抽出 / 予約名の backend 依存 / 既存 `ControlPlane` の改名と `ValueError` 再分類 / DSN 規約と skip 禁止 / 実行時間・DB 生成数の増分 / subprocess PYTHONPATH) は各節へ追記
- **N-3** L4 の意図的逸脱を D-I として記録 / **N-4** R-7 の `request_bytes` 記述を enforcement 側限定へ精緻化
- レビューが「検証済み・問題なし」と確認した事実主張 (endpoint 7+11 本、errors.codes、凍結 capability 11 件の現宣言、C-14/C-15 surface-absent、814 passed 基準、bootstrap/reset/must_rotate/declare-and-echo の契約文言整合、SI 参照の正確性、form (b) 回避) は v1.0 から不変

### 第2ラウンド (並行セッション mitate-30 の独立 WP-0 レビュー、対象 v1.0、blocker 3 / major 11 / minor 16 / nit 3) の裁定 — v1.2

経緯: 本設計 v1.0 は並行セッション mitate-30 が執筆し、本セッションが自ドラフトと誤認したまま独立レビュー・v1.1 化・コミットした (二重発注)。両セッションの WP-0 レビューは独立に走り、相補的だった。実装所有は本セッションに固定、mitate-30 はクライアント側 (mitate-application) を所有。

- **重複 (v1.1 で解決済み)**: B-1 (= 当方 B-1/P3-D1)、B-3 (= M-2)、M-6 (= M-4/WP-2.5)、M-10 の大半 (= M-11/pg_terminate_backend)、m-4/m-5/m-11 (= m-4/M-6/M-9)
- **B-1 追加分**: delete 確認句の fingerprint 前提崩れ → §0 例外節へ追記、WP-1 で add_field と同一コミット。create_entity の fields 省略受理も確定
- **B-2 (裁定 = P3-D2/D-J)**: transact の update/delete atomic 拡張で実挙動を既存宣言へ収束させる (WP-1.5 新設)。レビュア推奨案を採用。§8.1(b) は MitateDB では実害消滅、契約 CCR は台帳残置
- **M-1**: 数値制約は v1.1 反映済み。追加分 (capability_document の per-call provisioning 是正、155 application 実測、HTTP での実 DB/role 総数) を R-8 へ
- **M-2** → R-4 (enabled/revoked 独立2値、parity 基準 = 契約挙動、WP-2) / **M-3** → R-6 (revoked は bound に数えない) / **M-4** → R-8 (C-13 実ベクタ化は flip と同一コミット、WP-5) / **M-5 (裁定 = 案(ii))** → R-6 (CLI entry point は WP-5、WP-4 は儀式コアまで) / **M-7 (裁定 = 案(i))** → R-6/R-9 (max-instances=1 runbook 不変条件、D-K) / **M-8** → R-1/R-9 (cloudsqlsuperuser 迂回禁止 + pg_auth_members fail-closed 検査) / **M-9** → R-4 (application_id 契約規則 + 採番 + 63バイト検証) / **M-11** → R-5 (実行前の決定的 VALIDATION_FAILED、backend 差は R-3 既知許容差 (3))
- **m-1** (v1.1 反映済み) / **m-2** → R-4 (単調採番列) / **m-3** → R-6 (in-process control 監査も 12 フィールド) / **m-6** → R-6 (混載一覧) / **m-7** → R-6 (schema 完全一致) / **m-8** → §3 完了条件 2b (AST 件数の同一コミット更新) / **m-9** → R-2 (SQLite 側外部挙動不変 + PG 側予約名を明記) / **m-10** → R-6 (request_bytes を最初から宣言) / **m-12** → R-5 (HTTP status の r2db 突合) / **m-13** → R-9 (宣言結合の runbook 不変条件) / **m-14** → §3 WP-4 (topology 実行可能証拠) / **m-15** → R-1 allowlist (FOR ROLE 形) / **m-16** → R-8 (credential handle キャッシュ)
- **n-1** → R-3 用語注記 / **n-2** → §6 / **n-3** → R-8 実行コスト
- **クライアント実要求** (mitate-30 送付の棚卸し): cross_entity_mutation の凍結解除検討 = D-L として依頼者判断へ。JSON 文書型 (`object`) と order_by/page の要確認 2 件は §8 末尾の確認結果参照

### WP-1 実装記録 (2026-08-30)

成果物: `MitateDB-api/pyproject.toml`、migrations 0001〜0004 (platform bootstrap / registry 4テーブル + begin/finish provision/deprovision 関数 / application DB 実体 / 撤去)、backend seam (`backend.py` / `backend_sqlite.py` / `backend_postgres.py`、cell.py は sqlite3/psycopg 非依存化)、add_field 解禁 + delete 句 `@schema_revision` fingerprint (P3-D1)、`ProvisioningFacade` 改名 (後方互換 alias 維持)、実 PG テスト。root suite **814 → 858 passed** (+44。foundation +7、test_postgres 37 件)。

独立レビュー2往復 (Opus): 第1回 blocker 1 / major 4 / minor 8 → 全修正。第2回 (確認往復) 新規 major 3 / minor 7 → 全修正。主な発見と修正:

- **B-1**: PG backend の型不一致値が psycopg 例外のまま分類階層を脱出し、rollback 漏れで connection が恒久汚染 → 2層修正: (i) 宣言 field_type への実行前決定的 `ValidationError` (`_validate_value_domain`、接続不要の純粋関数として単体テスト化)、(ii) 全 DML/DDL の包括 `except psycopg.Error: rollback → 分類`。NULL は全 domain で受理 (M-5 回帰の修正)
- **M-6**: `ALTER ROLE` crash-retry フォールバックが先取り role を属性・メンバーシップごと採用しうる穴 → `assert_role_has_no_memberships` (rolsuper/rolcreatedb/rolcreaterole/rolinherit 全 false + rolcanlogin true + membership 0件、違反時 RAISE の fail-closed 検証。cloudsqlsuperuser 個別検査 (R-1) はこれに包含、直接 membership 0件は推移的 membership 不能を含意)
- **M-7**: SQLite backend にも同欠陥クラス (10**30 の OverflowError 脱出 + 暗黙 tx 残留で transact 恒久失敗) → int64 範囲チェック + `begin()` の tx 耐性。**SQLite 外部挙動の意図的変更** (脱出例外 → 分類済みエラー) として記録
- **m-11**: begin 時に role 名を registry 行へ記録し (database_name NULL = 未 provisioned マーカー維持)、0004 が中断残骸の ghost role を DROP 可能に
- **M-1/m-2 (audit_seq)**: control_audit に bigserial 単調採番列。`INSERT ... RETURNING` が INSERT-only 権限で拒否されることを実測 (append-only grant の正しさの副次確認)
- **M-4 裁定**: deprovision の credential guard を廃止し、finish 側が同一 tx で credentials → applications を削除 (提供 role の下。control_audit は不可触・残存を実測)。インターロックは WP-5 で CLI deprovision の declare-and-echo gate へ (R-6)
- 変異注入: 実装者 5+3 本、レビュアー 5+4 本 (第2回で生存した 3 本は検出力補強後に全て赤化を再実測)。生存変異ゼロ
- 記録済みの軽微な挙動差 (m-14): transact のエラーメッセージ文言変化、`NotFoundError` 経路が rollback されるようになった改善
- WP-3 への申し送り: in-process adapter `provision_application` は `_call` を通らず `ConflictError` 再分類が port 境界で未観測 (m-13)。`create_entity` fields 省略時の合成 `id` 列を C-11/C-17 が観測しないことの確認 (N-2)。boolean 列は両 backend とも INTEGER 表現 (bool↔int cast 不在のため)。PG の insert 返り値は ctid (安定性なし、`row_addressability: unavailable` は不変)

### WP-5 実装記録 (2026-08-30。宣言 flip 単一コミット・control plane PROVIDED 初実行)

/control/v1 mount (control_main.py、data 面と別 entrypoint = 同一イメージ・別 uvicorn app)、control_plane 宣言を config 単一ソース (config.py `control_plane_status`) へ flip (cell.py はこれを読むのみ)、儀式 CLI `ops.py` (bootstrap/reset のみ — 監督裁定。WP-4 儀式コア直呼び・reset は declare-and-echo)、両 conformance adapter の 14 control op を PROVIDED 化 (in-process は `auth.CredentialStore` 上の `_ReconciledControlBackend` シム、http は実 /control/v1 ASGI + 実 CLI subprocess)、**2ストア突合成立** (in-band 発行 credential を application 面 authenticate が読む — WP-4 申し送り (i) を実現)、C-13 を structurally_absent → 実 must_deny ベクタ (revoke→enable(True)→再認証拒否)、probe 再利用化。root suite **1122 → 1145 passed** (+23、config __post_init__ 検証含む)。**C-13/C-14/C-15 が4 adapter 全緑** (PROVIDED 分岐初実行)。n_existing 実測: in-process 73 / http 75 (bound 100 に対しマージン25、r2db 80 と同水準)。

**初回実行デバッグ発見3件 — すべて harness 側、製品コード欠陥ゼロ** (厳格分岐初実行の主成果物): (1) HTTP adapter の authenticate が ControlCredentialHandle の application_id/role を無条件参照 → AttributeError (getattr 化。製品の HTTP authenticate は control credential を渡されても credentials テーブルに行が無く AUTH_INVALID で構造的に拒否 = C-14 の要求。レビューが製品コードで直接反証)、(2) probe 再利用と WP-3 の LRU cell cache の初交差 → cell 不在時の再 provision で自己修復、(3) control handle キャッシュの liveness を返却前に実 GET で検証。3件とも `control_plane.py`/`control_http.py`/`ops.py` への修正不要。

独立レビュー1往復 (blocker 0 / major 0 / minor 1): m-1 (`control_plane_status` のコンストラクタ層無検証 → `FoundationConfig.__post_init__` で語彙検証、`from_env` の境界検証は維持) を修正。変異は実装者5 + レビュアー4 = 生存ゼロ (config 単一ソース破壊・C-13 resurrection・2ストア突合破壊・must_deny vacuous 化を各々赤化)。**監督受入の注意事項**: 初回の受入 suite が 62 failed/320 errors になったが、原因は並行 pytest 2本 (実装者の待機中バックグラウンド run と監督 run) による PG クラスタ競合 (leftover role 622/DB 307) で、コード回帰ではない。クラスタ掃除 + 単独再実行で 1145 passed を確認。N-1 (2サービス分離下の宣言は operator assertion — runbook 不変条件3が担保)、N-2 (in-process 突合は同一 Python オブジェクト、http/本番は同一 Postgres テーブル2表現) は設計どおり。

### WP-4 実装記録 (2026-08-30)

control plane 本体を実装 (公開 composition に mount せず、全て直接テスト): control credential store 二重実装 (control_auth.py / control_credential_store_postgres.py、専用 pepper・must_rotate・enabled/revoked 2値・fail-closed で `InsufficientPrivilege` を独立分類 = application 面 WP-2 より精密)、control_audit.py (12フィールド + audit_seq、別 reader)、control_plane.py (ControlPlaneService・ControlPlaneLimits・儀式コア bootstrap/reset)、control_http.py (/control/v1 11 route、**どこからも import されない**)。R-6 全規律 (同一 tx 監査・例外2系統・評価順序 rate→認証→認可→capability→対象解決→shape→confirmation→precondition・rate 前段・bounds 数値制約・revoked 非計上・must_rotate FORBIDDEN・un-revoke ゼロ・list_credentials 混載・bootstrap CONFLICT が revoked 含む・reset atomic revoke+mint) をレビューが実測 (同一 tx atomicity・評価順序を独立 import で裏取り)。CLI entry point・mount・宣言 flip は WP-5。root suite **1014 → 1108+ passed** (+94、全 MitateDB-api/tests、公開面影響ゼロ)。

独立レビュー1往復 (blocker 0 / major 0 / minor 4、全て「正しい実装だがテスト未固定」): m-1 (rate window の時間回復) / m-2 (CONTROL_AUDIT_FIELDS の12列完全性) / m-3 (control store の pepper 長検証) を検出力テストで追加 (WP-5 の PROVIDED 初実行前に閉じる)。**裁量 (3) の記録**: migrations 0002 の `control_credentials` テーブルに `revoked` 列が無かった (WP-1 のスキーマ欠落 — WP-2 は sibling `credentials` に revoked を足したが control 側には足さなかった) を WP-4 で発見・in-place 修正。既存 Cloud SQL デプロイ皆無 + 全テストが 0001-0004 を毎回再実行のため in-place で安全 — **WP-6 で CONTROL_MAPPING に「WP-1 スキーマ欠落を WP-4 で発見・修正」を記録**。申し送り: control の count-bound の check-then-act は非トランザクション (max-instances=1 + rate lock + 逐次 conformance 下で C-14 に現れないが真の並行では racy。m-4)。

### WP-3 実装記録 (2026-08-30)

application-plane HTTP 面 (http.py: 契約7 endpoint、ASGI receive ループでの request_bytes 実測、multi-field order_by、page.cursor→CAPABILITY_UNSUPPORTED、problem+json、Bearer `credential_id.secret`、error→HTTP status は r2db 実マッピングと全 grep 突合一致)、composition root (main.py: env 注入・pepper 分離検証・request_bytes enforcement 宣言を HTTP composition のみ)、bounded pool (pool.py、composition で実配線 / adapter は逐次のため pool=None)、第4 adapter `MitateDB-api-http` (httpx ASGITransport + 実 PostgreSQL、prefix mitatedbhttp{hex8} + advisory lock sweep、name="MitateDB-api (http+postgres)")。registry.json required 登録 + `_EXPECTED_STRICT_ADAPTER_NAMES` 更新。root suite **892 → 1013 passed** (+121。既存 executable 全条件が 4 adapter で緑)。

独立レビュー2往復 (初回 blocker 0 / major 4 / minor 6 → 全解消、統合確認で major 0)。主な発見と対応: **M-1** — adapter の drop_entity が wire で受理するのに偽 SurfaceAbsent を主張 → present-denial 化。真因の早期 close 問題 (M-2) は共通側 conftest fixture が param ローテーションで close していたことと判明し、**WP-2.5c で conftest を真の session teardown close へ修正** → `_ensure_alive`/registry 順序依存を撤去。**M-3** — create_entity の field_type 黙殺 (honor できない要求を成功受理し生成 entity が以後 integer を拒否) → CapabilityError。**M-4** — SQLite backend の order_by direction が唯一の防御なのに文字列連結で、allowlist 除去時に ORDER BY 内 subquery が実行される (SI-04/05 潜在違反) → 両 backend 定数マップ化 (レビューが injection の閉塞を直接実測)。**受理境界 (CONDITIONS.md 開示)**: HTTP peer の公開面は JSON operation enum であり form-(a) SurfaceAbsent の signature 検証は wire 語彙を見られないため、mount 済み peer の偽 SurfaceAbsent を機械検出できない (form-(b) fabrication と同クラス)。安全性の本質は present-denial 側の (d) probe が押さえ、残る gap は形態主張の自己整合性のみ → positive-existence check を §7 将来課題へ。変異注入は各往復で実施、生存はいずれも受理境界。

### WP-2.5 実装記録 (2026-08-30)

共通側変更 (R-8 の裁定2件 + WP-1.5 繰延べ2件): C-17 unavailable 分岐が present-denial 形態を受理 (`absence.py` の共有ヘルパー `assert_control_operation_absent_or_uniformly_refused` へ**寄せる**形で実装 — インライン再実装の解消と同時に `declared_surface >= public_surface` 検査等のハードニングを獲得。`CAPABILITY_UNSUPPORTED` 限定 + 受理時は重複挿入プローブで index 不作成を検証)。C-11 は `_find_all_adapters_with` + parametrize で raw accessor を持つ全 adapter を検証。test_c06 docstring の歴史的経緯化、CONDITIONS.md へ absence shortcut 到達不能の残置記録と C-17 form-(b) 捏造不可判別限界の開示 (C-14 と同じ DEFERRED 宣言)。**新設分岐は stub adapter による永続 regression テストで固定** (レビュー M-2: 「誰も通らない新規コード」を残さない)。root suite **887 → 892 passed** (+5)。

peer 側の同時修正 (別コミット、レビュー M-1): `public_operation_callables()` の陳腐化 — WP-1 追加の `create_entity`/`add_field` に加え実測で `capabilities` も欠落しており計3件追加 (C-17/C-15/C-11/absence.py の独立検証の証拠面が公開面全体を被覆していなかった)。introspection による全数被覆の機械固定テストを新設 (将来の面追加で自動赤化)。独立レビュー1往復 (blocker 0 / major 2 / minor 4、既存 3 adapter への検証緩和ゼロをレビュアーが入力クラス全数突合で確認)。

### WP-2 実装記録 (2026-08-30)

R-4 の credential 永続化: in-memory 側の enabled/revoked 独立2値化 (revoke=terminal、un-revoke 経路ゼロをレビューが grep 全数で確認)、`PostgresCredentialStore` 新規 (同一 call surface、pepper-HMAC digest のみ保存、`hmac.compare_digest` + 未知 id でもダミー digest 計算、DB 不達は全9メソッドで `AuthorizationStateUnavailable` fail-closed — レビューが9メソッド全数実測)。parity 基準 = 契約挙動 (核心: revoke → enable → 再認証 must_deny を両ストアで固定)。`assert_pepper_separation` 新設 (呼出は composition root、WP-3/4)。0002 credentials に revoked 列。root suite **873 → 887 passed** (+14)。

独立レビュー1往復 (blocker 0 / major 1 / minor 6): **M-1 裁定** — `InsufficientPrivilege` (恒久的権限誤設定) を `AuthorizationStateUnavailable` から分離し新設 `StorageConfigurationError` へ (R-6 監査免除 (ii) の「store 不達」意味論を汚染しないため。HTTP 写像は `SERVICE_UNAVAILABLE` 提案 — WP-3 で確定)。m-1: disable/enable_application が影響有無 bool を返却 (無言 no-op の情報化)。m-5: DB の role 値が語彙外なら状態整合性喪失として `AuthorizationStateUnavailable`。m-6: adapter の C-13 根拠コメント3箇所へ補記 (実ベクタ化は WP-5 と同一コミット — **WP-2 が作った revoke→enable→再認証こそ C-13 の最強ベクタであり WP-5 投入必須**)。変異: 実装者4+1本、レビュアー5本 — **受理境界1件を記録**: `hmac.compare_digest` → `==` の変異は行動テストで構造的に検出不能 (タイミングのみの差)。定数時間比較はレビューとコード規律だけが守る性質。N-2: control credential store は WP-4 で同型の第2クラス (`control_credentials` テーブル、専用 pepper)。

### WP-1.5 実装記録 (2026-08-30)

P3-D2 実施: `transact` が update / delete を atomic 実行 (両 backend、途中失敗は shape/capability/not-found/値ドメインの全クラスで全体 rollback を実測)。バッチ内 delete は専用経路と同一の単一 choke `_validate_delete_confirmation` (宣言・echo・fingerprint・details 四キー)、update も同様に `_validate_update` へ一本化。バッチ内 delete の監査は commit 成功後に遅延発火 (rollback された delete は監査に残らない)。宣言 (`capabilities()`) は不変 — 実挙動が既存宣言 `atomic_mutation.operations` へ収束。upsert は CapabilityError 継続。C-06 V2b-wire は in-process adapter で実分岐へ (probe が `DESTRUCTIVE_CONFIRMATION_REQUIRED` を返す)。root suite **858 → 873 passed** (+15)。

独立レビュー1往復 (blocker 0 / major 1 / minor 5): M-1 (バッチ経路の mass-operation ガード 6 形状のテスト空白) / m-1 (update 検証の choke 一本化) / m-4 (delete の `values` キー受理のローカル固定 — adapter が全 item に values を設定するため C-06 成立の必要条件、変異で実証) / m-5 (`DESTRUCTIVE_CONFIRMATION_V1.md` §7.4・§8.1(b) へ原文不変の補記) を修正。m-2/m-3 (共通側: test_c06 docstring 陳腐化、absence 分岐の全 adapter 到達不能化の記録) は WP-2.5 へ繰延べ。変異注入は実装者 5 本 + レビュアー 4 本、生存ゼロ。裁量判断「delete の operation-dict の `values` 受理 (未使用)」はレビューで契約 `definitions.Mutation` (operation 別 narrowing なし) との整合を確認し採用。フェーズ4 への申し送り: 耐久 audit sink 導入時、バッチ監査の遅延発火に伴う commit 後クラッシュ窓の扱いを R-6 の同一 tx 規律とどう整合させるか (N-1)。
