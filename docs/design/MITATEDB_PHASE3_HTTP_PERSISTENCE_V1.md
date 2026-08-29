# MitateDB-api フェーズ3 — HTTP 面と PostgreSQL 永続化 (Cloud Run / Cloud SQL 対応) 設計 v1.0

- 版数: v1.1 (2026-08-30。WP-0 独立レビュー (blocker 2 / major 11 / minor 11) の全指摘を裁定・反映して確定。§8 参照)
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
  - **例外 (P3-D1、WP-0 B-1 裁定)**: `schema_operations` の `add_field` のみ本フェーズで解禁する。契約 `SchemaOperationRequest` は per-field 型スロットを持たない (`field_type` 単一) ため、共通 fixture の混合型 entity は `create_entity` + field ごとの `add_field` でしか契約形状の HTTP 要求として構築できない (r2db-http 既確立の形)。これは投機的な宣言拡張ではなく第4 adapter 成立の実需要であり、上の凍結列挙にも元々含まれていない。宣言 flip と実装・テストは単一コミット (WP-1)。契約側 per-field 型追加の CCR 起票、および共通 suite を MitateDB の不足に合わせて緩める案は、それぞれ「契約変更なし」「peer の不足を埋めない」の原則により不採用
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
- `pg_terminate_backend` (Cloud SQL では実行 role が `pg_signal_backend` member であることが前提 — runbook の実機検証手順に含める。`DROP DATABASE` 前の接続残存対策)

superuser 専用機能 (untrusted PL、ALTER SYSTEM 等) を一切使わない。migrations ファイル冒頭に「Cloud SQL 適合語彙」の注記を置き、逸脱をレビュー対象にする。**証拠区分は正直に**: 本フェーズの実測はローカル PostgreSQL 16 クラスタ (Homebrew、`host=/tmp port=5432`、r2db テストと同一規約) のみで、Cloud SQL 実機 evidence は配備時まで absent と `security/CONTROL_MAPPING.md` に明記する。

代替案 (不採用): 単一 database + schema-per-application + RLS。共有 CONNECT 面が残り、単一実装欠陥での越境がやや可能になる (containment が grant/RLS 規律依存)。r2db が database-per-application で実測確立した安全結果と同型を、Cloud SQL 制約下で MitateDB 自身が検証して採る。RLS の defence-in-depth 併用は本フェーズでは見送り、台帳へ (§7)。

### R-2: 実行 choke point — 値は常に bind、識別子は二段検証、raw string は型で拒否

- psycopg 3。値は常に server-side bind パラメータ。文字列補間で SQL に値を入れる経路を作らない
- 識別子は (1) 既存 `identifiers.validate_identifier` の構文 allowlist、(2) 対象 database の生きた catalog (`information_schema`) との照合、の二段を通ってから `psycopg.sql.Identifier` でのみ合成。既存 `identifiers._RESERVED` は SQLite 固有 (`sqlite_sequence`) を含むため、予約名集合は backend 依存として backend 層に置く (構文 allowlist 本体は共有のまま。WP-0 m-7)
- 実行は単一 choke point 関数に集約し、型注釈と実行時型検査で `psycopg.sql.Composed`/`SQL` 以外 (特に `str`) を `TypeError` で拒否する — 「どのメソッドからも raw string を実行できない」ことをファイル構造で成立させる

これは r2db 内部構造の移植ではなく SI-04/SI-05 の要求結果の成立形。**実装コードの peer 間共有はしない** — 二重独立実装が conformance の検出力の源泉である実績 (peer 不適合3件はすべて差分から発見) を保つ。

### R-3: MitateDB 内部の backend seam — 検証・宣言は一箇所、実行は backend ごと

既存 `cell.py` (SQLite) の要求検証・capability 宣言・エラー分類・declare-and-echo 句構成のロジックを **backend 非依存の層**に抽出し、実行のみを backend (既存 SQLite / 新設 PostgreSQL) が担う構造にする。

- 目的: in-process adapter (`MitateDB-api`) と HTTP adapter (`MitateDB-api-http`) が**同一の公開意味論**を持つことを、注意力でなく構造で成立させる (宣言と実挙動の一致が二系統に分裂しない)。既知の例外は1点のみ: C-17 unavailable 分岐の evidence 形態 (in-process = `SurfaceAbsent`、http = present denial。R-8 の共通側変更参照 — WP-0 B-2)
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
| `control_audit` | 契約 `audit.fields` の 12 列 + recorded_at。**INSERT-only** | control plane role (INSERT のみ。SELECT/UPDATE/DELETE 不可) |

- **プロセス role の分離**: application-plane プロセスは専用 role (例 `mitatedbsvc_api`) で registry へ接続し、`control_credentials`/`control_audit` への grant を一切持たない。control-plane プロセスは専用 role (例 `mitatedbsvc_controlplane`)。provisioning 権限 (CREATEDB/CREATEROLE を持つ例 `mitatedbsvc_provision`) は儀式/provisioning CLI のみが保持し、どちらの API プロセスにも渡さない
- **pepper 2本**: `MITATEDB_CREDENTIAL_PEPPER` / `MITATEDB_CONTROL_CREDENTIAL_PEPPER`。起動時に相違を検証 (同値なら起動拒否)。secret は Secret Manager 参照のみ、repo/イメージ/テストに実値を書かない (テストは synthetic 値)
- **credential store の二重実装**: 既存 in-memory `CredentialStore` (foundation/in-process adapter 用) と新設 Postgres 版が同一 call surface を持ち、parity テストで両者に同一挙動を課す。DB 不達時は `AUTH_STATE_UNAVAILABLE` 系 fail-closed (資格情報の推測可能な劣化経路を作らない)
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

### R-6: control plane (`/control/v1` + 儀式 CLI)

- **独立 ASGI app** (application-plane と別 app、別 Cloud Run service が既定。同居可能な構造にはするが既定は分離)
- 11 endpoint (`control_capabilities` / `register_application` / `list_applications` / `disable_application` / `enable_application` / `issue_credential` / `list_credentials` / `rotate_credential` / `revoke_credential` / `disable_credential` / `enable_credential`) を契約どおり実装
- **評価順序を固定する** (WP-0 M-6): `rate-limit 前段 → 認証 → 認可 → capability 判定 → 対象解決 → shape 検証 → (該当時) confirmation → precondition → 実行`。C-14 vector 1 は「不在対象 + 無権限」で `NOT_FOUND`/`CAPABILITY_UNSUPPORTED` が漏れないこと (= 対象解決より認証・認可が先) を、vector 3 は `role=control` の in-band 発行が対象の実在/不在/disabled/飽和のいずれでも一様に `CAPABILITY_UNSUPPORTED` であること (= capability 判定が対象解決より先) を機械検証する。契約 `evaluation_order` (shape→認証/認可→対象→confirmation→precondition→実行) と C-14 の要求を1つの順序表として実装の choke point に固定する
- **must_rotate credential の拒否コードは `FORBIDDEN`** (C-15 が完全一致を要求。WP-0 m-4)
- **儀式意味論の正本は再利用可能な product code** に置き、CLI (`ops`) と in-process adapter の双方が同一コアを呼ぶ (C-15 は in-process adapter にも実の儀式実行を要求し、adapter が credential 行を捏造することを禁じる — r2db が `ops.py` から `control_plane.py` へコアを抽出したのと同型。WP-0 m-6)
- **状態変更は監査行と同一トランザクション**で書く — 耐久書込失敗は状態変更ごと abort (fail-closed by construction)。認証・認可の**拒否イベントも耐久記録**する。例外は2系統のみ: (i) rate-limit 前段拒否 (認証前・audit 増幅 DoS 防止)、(ii) `AUTH_STATE_UNAVAILABLE` (store 自体が不達で監査書込も不能)。この2例外は r2db が条件付き承認で確立した形と同じ理由で採用し、コード注記と CONTROL_MAPPING に明記する
- **bootstrap / reset は out-of-band CLI** (`python -m mitatedb_api.ops`)。in-band に置かない。契約 `control_plane.bootstrap` の全条項を満たす: bootstrap は control credential 行が (revoked 含め) 1行でも存在すれば `CONFLICT`、reset は全 control credential を atomic に revoke し新規1本だけ mint、初回 credential は **must_rotate 方式**で非恒久 (capabilities と self-rotate 以外を拒否、実 rotation 完了で解除)
- **declare-and-echo** (契約 1.2.0): CLI の不可逆 subcommand (reset / credential 削除系) と、in-band の「最後の有効 control credential の revoke」gate に適用。句はサーバが宣言しクライアントが復唱する方式のみ (Q1-D2)。判定は完全一致、truthy 受理なし
- **資源境界 3 クラス** (`applications` / `credentials_per_application` / `control_requests_per_minute`) を実 enforce し discovery (`control_capabilities`) で `enforced` 公開。C-14 vector 5 は「宣言した bound の正確な位置で拒否が起きる」ことを位置算術で検証するため、bound は composition root で設定可能にし、conformance adapter が自身の consumption を織り込める値を選べること。**設定値の数値制約** (WP-0 M-5、C-14 実装からの逆算): 3クラスとも `≤ 200` (`_MAX_EXERCISABLE_LIMIT`)、`control_requests_per_minute > applications + 2 × credentials_per_application + 67` (headroom+margin 不等式)、`applications` は suite 実行1回の累積登録数を上回ること (r2db-http 実測: vector 5 到達時 80、session 終了時 89 に対し `applications=100, credentials_per_application=5, control_requests_per_minute=200`)。WP-5 の完了条件に in-process / http 両 adapter での n_existing 実測記録を含める
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
- 実行コストの増分 (WP-0 m-10): C-14 provided 分岐は rate-limit window 回復の `sleep(61)` を含むため、MitateDB 2 adapter の provided 化で root suite は**約 +122 秒**、http adapter は session 中に実 database を r2db-http 同規模 (~90個) 作成・破棄する。§3 の「root suite 完走」条件はこのコストを織り込んで維持する
- 上記 2 件以外の port (`conformance-tests/adapter.py`) の変更は原則なし。実装中に追加の port 変更が必要になった場合は「peer の不足を埋めない」原則の下で設計論点として明示し、共通側の変更として単独レビューを通す

### R-9: 配備資産 (Cloud Run / Cloud SQL)

- `MitateDB-api/docker/Dockerfile`: multi-stage、非 root、実行は uvicorn。data-plane / control-plane を同一イメージ・別 entrypoint で起動できる形
- runbook `MitateDB-api/docs/cloud-run-cloud-sql.md`: Cloud SQL インスタンス作成、registry/role の bootstrap 手順 (provisioning 権限は運用者/儀式のみ)、Secret Manager への pepper/DSN 登録、2 Cloud Run service (data: mitate-application の SA のみ invoker / control: 運用者のみ、`--no-allow-unauthenticated`)、Cloud SQL 接続 (unix socket DSN)、Cloud SQL 実機での適合検証手順 (R-1 の語彙が実機で通ることの確認コマンド列)
- コードは Cloud を知らない: 接続は DSN 注入のみ。IAM DB 認証・Cloud SQL Connector の採否は将来強化として台帳へ (§7)
- 配備の実行・GCP project 作成・secret 実値投入は運用者作業 (Mitate repo CLAUDE.md の絶対事項と同じ規律)

## 2. endpoint → 実装対応 (application plane)

| 契約 endpoint | 実装 |
|---|---|
| `GET /v1/capabilities` | composition root 注入の capability 宣言を返す (**application 認証のみ**。契約 `versioning.control_discovery` の control 認証受理は co-hosting convenience であって要求ではなく、R-4 の面別 store 分離の帰結として採らない — application-plane プロセスは control credential を検証する手段を構造的に持たない。WP-0 M-9) |
| `POST /v1/data/{entity}/query` | backend seam 経由 structured query (宣言 envelope: eq 系 `_OPS`、`contains`/`matches`/`is_null` は `CAPABILITY_UNSUPPORTED`) |
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
| **WP-1** | PostgreSQL 基盤: `MitateDB-api/pyproject.toml` 新設 (依存宣言: starlette / psycopg[binary] / uvicorn / httpx。WP-0 M-10)、migrations (platform registry 二状態 / provisioning SQL、Cloud SQL 適合語彙注記、prefix 1トークン規律)、R-3 backend seam (cell.py の公開挙動不変リファクタ、既存 `ControlPlane` facade の改名と `ValueError` 再分類)、**`add_field` 解禁 (P3-D1、宣言+実装+テスト単一コミット、SQLite/PG 両 backend)**、Postgres data backend (query/insert/update/delete/create_entity/add_field)、database-per-application provisioning/deprovisioning、実 PG テスト (越境拒否の素接続検証含む) | あり (in-process adapter の `schema_operations` 宣言に `add_field` が加わる。他は不変) |
| **WP-2** | credential 永続化: Postgres 版 application credential store、in-memory 版との parity テスト、pepper 検証、DB 不達 fail-closed | なし |
| **WP-2.5** | **共通側変更 (単独コミット・独立レビュー)**: C-17 unavailable 分岐への present-denial 形態追加 + C-11 `_find_adapter_with` の全 adapter 反復化 (R-8)。既存 3 adapter は全数緑のまま | なし (共通 suite の検証範囲拡大のみ) |
| **WP-3** | application-plane HTTP 面 + composition root (serve) + `MitateDB-api-http` adapter 登録 (`_EXPECTED_STRICT_ADAPTER_NAMES` 同一コミット更新、control 系 port op は SurfaceAbsent 維持)。`request_bytes` enforcement 宣言は本 WP (実挙動と同一コミット)。→ 既存 executable 全条件が 4 adapter で緑 (C-14/C-15 は http 側も surface-absent) | あり (新 adapter 追加。既存 adapter の挙動不変) |
| **WP-4** | control plane 本体: control credential store 二重実装 + parity、ControlPlaneService (同一 tx 監査・rate limit・bounds)、儀式 CLI (`ops`、declare-and-echo)、control HTTP app (**未 mount**)。全て直接テスト | なし (公開 composition に mount しない) |
| **WP-5** | **宣言 flip 単一コミット**: /control/v1 mount + `control_plane: enabled` (両 adapter) + C-14/C-15 PROVIDED 初実行。厳格分岐の初実行 WP として「発見一覧」を成果物に含める | あり (C-14/C-15 が PROVIDED 分岐へ) |
| **WP-6** | 記録整理: Dockerfile / runbook、`security/CONTROL_MAPPING.md` の MitateDB 列 TBD 解消 (実在テスト名の引用、Cloud SQL 実機 evidence absent の明記)、`CONDITIONS.md` 更新、README、将来課題台帳、引き継ぎ | なし (ドキュメント) |

各 WP の完了条件 (共通):

1. テスト追加 + **変異注入** (テストが守る性質を壊す変異で赤化を実測 → scratchpad 経由復元・diff 一致確認。`git checkout` 不使用)
2. **root suite 完走** (契約ファイル・共通文書を触らない WP でも完走。現基準 814 passed + 本フェーズの増分)
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
9. **D-I**: L4 (r2db `request_bytes` の control discovery 宣言) は引き継ぎ書 §3 で「次のコード WP へ繰延べ」とされていたが、本フェーズでは扱わない (r2db 側を触らない原則優先の意図的逸脱。r2db の台帳項目として残置 — WP-0 N-3)

## 6. 本フェーズが閉じる既存台帳項目 / 閉じない項目

- 閉じる: `CONTROL_MAPPING.md` MitateDB 列の「TBD during implementation」のうち、control plane 分離・credential 永続化・propagation bound・HTTP 面 SI-10 系、および SI-08 の**部分** (`request_bytes` と control 面 rate のみ。application-plane の request rate / concurrency / execution time は本フェーズでも未実装のまま — §7 台帳へ。WP-0 M-1) (いずれもローカル実測 evidence として)
- 閉じない (明示継続): Cloud SQL/Cloud Run の production platform evidence (`foundation.json` の platform_evidence_required_before_production 3項目は配備時)、application-plane 耐久 audit sink (フェーズ4)、`audit_query` の C-11 zero-coverage (フェーズ4)、契約 additive 候補束 (`DESTRUCTIVE_CONFIRMATION_V1.md` §8.1(e)、1.3.0 検討時一括)

## 7. 将来課題台帳 (本フェーズ新設分)

- **application-plane の request rate / concurrency / execution time 境界** (SI-08 の残クラス。WP-0 M-1): Cloud Run の concurrency / max-instances / timeout を配備層 enforce として使う場合は `limit_enforcement: deployment_required` の宣言まで含めて別フェーズで設計する (契約 `capability_status.rules` — deployment_required is not an application-code proof)
- RLS defence-in-depth の併用 (R-1 不採用分。database-per-application が主境界として実測確立した後の追加層として)
- IAM DB 認証 / Cloud SQL Connector の採否 (現行: 標準 DSN + Secret Manager 参照)
- application database の `CONNECTION LIMIT` / pool 上限の運用チューニング (初版は保守的な固定値)
- MitateDB の `drop_entity` / `drop_index` (schema 削除系) — 現宣言 unsupported のまま。C-06 V6 は共有 absence 機構継続

## 8. 訂正記録 (WP-0 独立レビュー)

WP-0 独立レビュー (Opus、2026-08-30) の結果: **blocker 2 / major 11 / minor 11 / note 5**。全指摘を監督裁定のうえ v1.1 へ反映した。

- **B-1** (契約 `SchemaOperationRequest` の単一 `field_type` と混合型 fixture の不整合): `add_field` 解禁 (P3-D1、§0 例外節・§2・WP-1) で解決。契約 CCR / 共通 suite 緩和は不採用 (理由は §0 例外節)
- **B-2** (C-17 unavailable 分岐の `SurfaceAbsent` 強制と mount 済み entry point の矛盾): 共通側変更 WP-2.5 を新設 (D-H)。R-8 の「port 変更なし」「WP-3 で全条件緑」の当初主張を訂正
- **M-1** SI-08「閉じる」の過大主張を §6 で部分化し、残クラスを §7 台帳へ / **M-2** `_EXPECTED_STRICT_ADAPTER_NAMES` 同一コミット更新を WP-3 完了条件へ / **M-3** plug `name` 属性の別値化を R-8 へ / **M-4** C-11 主張は WP-2.5 の全 adapter 反復化で成立させる / **M-5** C-14 vector 5 の数値制約 3 本を R-6 へ / **M-6** 評価順序表を R-6 へ / **M-7** Cloud SQL 語彙 allowlist の拡張 + PostgreSQL 16 固定を R-1 へ / **M-8** prefix 置換方式を R-4 へ / **M-9** `/v1/capabilities` を application 認証のみに訂正 (§2) / **M-10** `MitateDB-api/pyproject.toml` を WP-1 成果物へ / **M-11** 二状態 registry を R-4 へ
- **m-1〜m-11** (registry 順序 / deprovision SurfaceAbsent 維持 / 回帰網主張の精緻化 / `FORBIDDEN` / 監査 reader / 儀式コア抽出 / 予約名の backend 依存 / 既存 `ControlPlane` の改名と `ValueError` 再分類 / DSN 規約と skip 禁止 / 実行時間・DB 生成数の増分 / subprocess PYTHONPATH) は各節へ追記
- **N-3** L4 の意図的逸脱を D-I として記録 / **N-4** R-7 の `request_bytes` 記述を enforcement 側限定へ精緻化
- レビューが「検証済み・問題なし」と確認した事実主張 (endpoint 7+11 本、errors.codes、凍結 capability 11 件の現宣言、C-14/C-15 surface-absent、814 passed 基準、bootstrap/reset/must_rotate/declare-and-echo の契約文言整合、SI 参照の正確性、form (b) 回避) は v1.0 から不変
