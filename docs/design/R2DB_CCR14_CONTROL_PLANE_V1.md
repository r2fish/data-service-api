# r2db-api CCR-14 control plane HTTP 面 (`/control/v1`) 設計 v1.1

- 日付: 2026-08-29。設計: Fable (監督)。実装: Sonnet subagents、レビュー: Opus subagents
- 改訂: v1.1 — WP-0 独立レビュー (Opus、blocker 3 / major 10 / minor 10 / nit 2、全指摘を実測で裏取り済み・誤指摘 0) を反映。§8 訂正記録
- 規範 (この設計はこれらを変更しない):
  - `spec/data-service-api.v1.json` 契約 1.1.0 — CCR-14 の文言化は**完了済み** (`control_endpoints` の 11 endpoint、`control_plane` 節、`capability_status.defined.control_plane`、schema 定義、`limits.classes` の制御面3クラス、`audit.sink_failure_policy`)
  - `spec/CCR_DISPOSITION.md` — 裁定: 全体採用 / **in-band 発行は案B** (`role=control` 発行は `CAPABILITY_UNSUPPORTED`、control credential は bootstrap/reset の帯域外儀式のみ) / base path `/control/v1` 確定
  - `conformance-tests/CONDITIONS.md` — C-14 (authority boundary)、C-15 (bootstrap/reset lifecycle)。いずれも登録済み・not yet executable
  - `security/SECURITY_INVARIANTS_V1.md` — 特に SI-00/02/03/06/08/09/13/14/15、および契約 `audit.sink_failure_policy` (認証認可の拒否・credential/Application lifecycle 変更・破壊的/特権操作・security-control failure の耐久記録失敗は fail-closed)
- 先行設計: `docs/design/R2DB_CREDENTIAL_PERSISTENCE_AND_COMPOSITION_ROOT_V1.md` (P2-D1〜D7)。同設計の §0「HTTP 制御面を作らない・control credential 型を作らない」は CCR-14 採否待ちの自制であり、本設計がそれを正式に解除する

## 0. スコープ

**含む**: r2db-api への `/control/v1` 11 endpoint の実装 (独立 ASGI アプリ)、control credential 型の導入 (ストア・migration・pepper)、**registry の「登録済み/provisioning 済み」二状態化 (0002 provisioning 関数の改訂を含む — §8 B-1)**、bootstrap/reset の帯域外儀式 (CLI)、制御面の SI-08 資源境界、control-plane 監査の耐久化 (状態変更 + 拒否イベント、unit-of-work 導入を含む)、conformance port の control 面拡張と C-14/C-15 の executable 化 (3 adapter)、`ops.py` の位置づけ再定義、CONTROL_MAPPING / runbook / capabilities.json の追随。

**含まない**: MitateDB-api の HTTP 層 (次フェーズ。本フェーズでは port の surface-absent 分岐で C-14/C-15 に応答する)、application-plane の耐久 audit sink (フェーズ3。ただし R-6 が control-plane 分だけ先行耐久化する)、Application の PostgreSQL 実 provisioning の HTTP 化 (R-4)、Application 削除 (契約が v1 対象外と明記)、`/v1/audit/query` の実装 (audit_query capability は unavailable のまま)。

## 0.5 依頼者裁定待ちの契約論点 (実装は条項休止のまま先行する)

**Q-1: 破壊的確認の有効性定義 (C-06 共通化の前提)。** 契約 1.1.0 の `revoke_credential` 意味論は「最後の有効な control credential の失効は許可され、明示的確認を要する — ただし有効な確認の定義は未解決の契約判断であり、**解決まで本条項は実効化しない**」と自ら定める。よって本実装は revoke を確認検査なしで提供することが契約適合であり、独自の確認規則を発明して契約の空白を埋めることは (CCR-13 の Q-1 で是正した欠陥の形の再発になるため) しない。`CredentialRevokeRequest` の `destructive`/`confirmation` フィールドは schema どおり受理し、内容は検査しない。**この状態は MitateDB の既知欠落 (確認トークン不検証) と同型である**ことを明記して裁定を仰ぐ。裁定のたたき台: 「`destructive: true` を必須とし、`confirmation` は対象 credential_id の完全一致」等の定義を C-06 共通条項として起こし、確定後に additive に実効化 (拒否コードは `DESTRUCTIVE_CONFIRMATION_REQUIRED` が既に契約語彙にある)。**本設計はこの裁定を実装のブロッカーにしない** — 確定後の実効化は語彙追加なしの意味論追加で済む。

## 1. 設計判断 (実装ポリシー。契約変更ではない)

### R-1: 制御面は独立 ASGI アプリ。同居は可、既定は分離

契約の separability 条項 (「分離配備可能でなければならない。同居する場合 SI-00 適合証拠が境界維持を説明する」) に対し:

- 新モジュール `control_http.py` が `create_control_app(control_service, *, lifespan=None)` を提供する。`http.py` (application 面) とルータ・ハンドラ・認証経路を一切共有しない
- 新 composition root `control_main.py` が独立プロセス/リスナとして起動できる。**runbook の既定は別プロセス・別 listen アドレス** (application 面と同一ホスト同居は許すが、bind は運用者判断)。module-level の `app` 即時構築は WP-5 まで置かない (§8 m-10 — 「配備できるが申告されない制御面」の窓を作らない)
- 同居配備 (単一サーバプロセスに両アプリを載せる) を選ぶ場合の SI-00 境界証拠: (a) 認証ストアが面ごとに別物で secret 名前空間が交わらない (R-8)、(b) DB 接続 role が面ごとに別で application 面 role は control 面の保存物を読めない (R-2/R-3)、(c) `AuthorityTopology` が public_plane→control_plane 到達を構造検証する既存機構を control アプリ登録にも適用する。この3点を CONTROL_MAPPING の SI-00/SI-02 行に review evidence として記載する (契約も「分離配備可能は振る舞いテストでなく設計証拠で審査」と定める)

### R-2: control credential は専用テーブル・専用 pepper。application 面からは不可読

CCR-14 の教訓3 (制御プレーンの保存物を application 面と同居させない) を保存レイアウトで満たす:

- migration `0006_control_plane_http.sql` が `r2dbsvc_registry.control_credentials` を新設する。列: `credential_id` (PK, `ctl_` + 16hex)、`verifier` (UNIQUE)、`enabled`、`revoked`、`must_rotate` (R-5)、`created_at`、`updated_at`。**application FK を持たない** (control credential はどの Application にも属さない)
- 既存 `credentials` テーブルの CHECK (`role IN ('runtime','developer')`) は**変更しない**。role=control は別テーブルに住むので、application credential ストアに control 行が混入する状態が構造的に作れない
- verifier は `HMAC-SHA256(control_pepper, secret)`。pepper は専用環境変数 `R2DB_CONTROL_CREDENTIAL_PEPPER` (application 面の `R2DB_CREDENTIAL_PEPPER` と別値を要求し、起動時に同値なら起動失敗)。秘密は発行/rotate 応答に一度だけ現れ、どこにも保存しない (`control_credential` scheme の契約条項どおり)
- `r2dbsvc_api` (application 面 API プロセスの読取専用 role) には `control_credentials` への **GRANT を一切与えない**。application 面プロセスの侵害は control credential の verifier すら読めない (0006 レビュー時確認済み: platform DB に `ALTER DEFAULT PRIVILEGES` は存在せず、自動開放経路は無い — §8 m-6)

### R-3: 制御面プロセスの DB role は新設 `r2dbsvc_controlplane` (least privilege)

`r2dbsvc_control` (運用者/CLI の provisioning authority) を長時間稼働の HTTP プロセスに渡さない。0006 が新設する login role `r2dbsvc_controlplane` の権限は:

- `applications`: SELECT / INSERT / UPDATE (`enabled` の反転と登録。R-4 のとおり登録は registry 行のみで、provisioning 列は書かない)。DELETE なし
- `credentials`: SELECT / INSERT / UPDATE (issue/rotate/revoke/disable/enable)。DELETE なし (`delete-credential` は CLI 専用の帯域外操作のまま)
- `control_credentials`: SELECT / UPDATE (rotate/revoke/disable/enable)。**INSERT なし** — control credential の行を作れるのは bootstrap/reset (CLI、`r2dbsvc_control`) だけ。案Bの「発行経路は帯域外のみ」が DB 権限のレベルで二重化される
- `control_audit` (R-6): INSERT のみ。UPDATE/DELETE なし。**この append-only 強制の範囲は「制御面プロセス role から」である** — スキーマ owner の `r2dbsvc_control` (運用者) は所有者権限で削除できる。CONTROL_MAPPING の SI-14 行はこの範囲で書き、契約 `audit.immutability` の "externally governed where required" に接続する (§8 m-4)
- `r2dbsvc_control` (儀式・CLI 側) にも `control_audit` への INSERT を **0006 で明示 GRANT する** (owner 権限で通る事実に暗黙依存しない — §8 m-3)
- provisioning 関数 (0002) への EXECUTE なし、CREATEDB/CREATEROLE なし。SEQUENCE / FUNCTION への GRANT が 0006 に**存在しないこと**もレビュー確認項目とする (§8 m-5)

接続 DSN は `R2DB_CONTROLPLANE_DSN`。制御面プロセスが侵害されても、Application の実データベースへの到達経路 (DSN も権限も) を持たない。

### R-4: `register_application` は「登録済み」状態を作る。provisioning は運用者 runbook のまま — registry を二状態化する

`POST /control/v1/applications` は Application を「登録済み・未 provisioning」として `applications` に記録する。0002 の実 provisioning (Application 専用 DB・role 作成) は従来どおり運用者の帯域外 runbook とし、データプレーンの serving set (`R2DB_SERVE_APPS` と DSN 群) も静的構成のまま。理由:

1. 実 provisioning の HTTP 化は、生成した DB role パスワードを API プロセスが読める場所に置くことを強い (教訓3の再発形)。秘密は外部 secret 管理に置くという現行原則 (P2-D5) と両立しない
2. 契約の register の意味論は「Application が制御面に存在し credential を発行できる」ことであり、データプレーンでの serving は配備の問題。契約は provisioning 方式を定めない
3. onboarding のうち「登録 + application credential 発行」はサーバログインなしで完結する (CCR-14 の目的の当該部分は満たす)。DB provisioning の自動化は将来の配備改善として独立に追求できる (additive)

**二状態化の実体 (§8 B-1 — v1 の「行を作るだけ」は既存列構造では実装不能だった)**。既存 `applications` は `database_name`/`runtime_role`/`developer_role` が NOT NULL UNIQUE で「登録だけの行」を表現できず、ダミー値を入れると 0002 の `already provisioned` ガードにより**その slug は二度と実 provisioning できなくなる**。よって 0006 は:

- 上記3列と `provisioned_at` の NOT NULL を落とし、**CHECK「3列は全て NULL (登録済み) か全て NOT NULL (provisioning 済み) か」**を追加する (UNIQUE は NULL を複数許すので維持できる)。「provisioning 済み」の判定は `database_name IS NOT NULL` であり、新しい状態列は増やさない
- `begin_provision_application` (0002) を **CREATE OR REPLACE で改訂**する: 登録済み行があれば provisioning 列を埋める UPDATE、無ければ従来どおり INSERT (運用者先行の従来フローも生き続ける)。既に provisioning 済みなら従来どおり例外
- `main.py` の起動時突合に「serving 対象は provisioning 済みであること」を追加する (登録済みのみの行は突合を通らず、実在しない DSN で cell を組む事故を防ぐ)

登録済みだが未 provisioning の Application への credential 発行は許す (credential は authenticate できるが、データ面操作は serving されるまで到達しない)。誤登録された slug の後始末は disable (契約どおり終端状態) であり、行の削除経路は設けない (契約 `application_deletion` v1 対象外)。

### R-5: bootstrap / reset は CLI の新サブコマンド。初回 credential の非恒久化は must-rotate 方式

`python -m r2db_api.ops` に `bootstrap` / `reset` を追加する (接続は従来どおり `R2DB_CONTROL_DSN` = `r2dbsvc_control`。公開 HTTP 面から実行経路が無いことは R-3 の INSERT 権限欠如が構造的に保証)。

- **bootstrap**: `control_credentials` に**行が1件でも存在すれば** (失効済みを含む) `CONFLICT` で拒否する。契約の文言は "While a control credential exists" であり、全件失効済みの状態を「存在しない」と読むと reset 以外の第二の発行経路が開く (§8 M-6)。**bootstrap は生涯1回、復旧は常に reset**。空なら control credential を1本発行し、秘密を一度だけ標準出力し、`control_audit` に正準イベントを書く (同一トランザクション)
- **reset**: 既存の**全** control credential を revoked=true にした上で新しい1本を発行する (同一トランザクション — 部分適用で「失効を生き延びる旧 credential + 新 credential」が併存する瞬間を作らない)。Application データと `credentials` と監査には触れない。正準イベントを書く
- **非恒久化は must-rotate 方式を採る** (契約は「期限またはローテート強制。機構は自由」): bootstrap/reset が発行する credential は `must_rotate=true`。この状態の credential が認可されるのは `GET /control/v1/capabilities` と自分自身への `rotate` のみで、他の全操作は `FORBIDDEN`。rotate 成功で `must_rotate=false` になる。時計に依存せず (TTL のテストは時刻注入を要する)、運用者に儀式の完遂を強制し、C-15 の「first-issued credential is non-permanent」を決定的に検証できる
- **契約条項の読みの明示 (§8 m-1、覆せる監督決定)**: 契約 bootstrap[5] "it expires or requires rotation" を「初回 credential は**1回の強制ローテートを受けるまで実用に供せない**」ことで満たすと読む。rotate は同一 credential の秘密差替えなので、rotate 後は期限のない通常の control credential になる — 「初回に配られた秘密が恒久化しない」ことが条項の保護対象であり、rotate 後の秘密は初回秘密ではない。恒常的な期限/再ローテート強制まで求める読みは契約が "implementation-free" とした機構の固定になるため採らない。この読みは依頼者が覆せる
- **ロックアウト経路と復旧 (§8 m-2)**: (i) rotate 成功後にクライアントが新秘密を取りこぼす、(ii) must_rotate credential が disable される、(iii) rate limit 枯渇 — いずれの詰みも**唯一の復旧は CLI reset** である。runbook に明記する

### R-6: control-plane 監査は耐久テーブルへ — 状態変更は同一トランザクション、拒否イベントも耐久記録 (fail-closed by construction)

契約 `audit.sink_failure_policy` は「**authentication/authorization denial**、credential/Application lifecycle 変更、破壊的/特権操作、security-control failure」の耐久記録失敗を fail-closed と定める。現行の `AuditSink` は in-memory で「sink 失敗」が起こり得ない代わりに永続もしない。制御面を公開 HTTP にする本フェーズでこのギャップを許容し続けることはできない。よって:

- 0006 が `r2dbsvc_registry.control_audit` を新設 (制御面プロセス role からは append-only — R-3)。列は**契約 `audit.fields` の 12 項目全て**: `event_id` (uuid PK) / `event_class` / `occurred_at` / `request_id` / `application_id` / `actor_type` / `actor_id` (= 実行 credential_id) / `role` / `operation` / `target_kind` / `outcome` / `reason_code`、加えて DB 側挿入時刻 `recorded_at` (§8 M-9 — v1 は `event_id`/`occurred_at` を欠いていた)。既存 `audit.py` の FORBIDDEN フィールド規則 (credential/token/password/secret/… を extra に載せない) も同一に適用する
- **状態変更系** endpoint は、状態変更と監査 INSERT を**同一トランザクション**で commit する。監査が書けなければ変更ごと abort → fail-closed が構成的に成立する
- **拒否イベント (認証失敗・authorization 拒否・capability 拒否) も耐久記録する** (§8 B-3 — 契約の sink_failure_policy は denial を先頭に列挙しており、in-memory sink に落とすことは不適合だった)。拒否には状態変更が無いので独立トランザクションの INSERT で足り、INSERT が失敗した場合は当該応答を 503 (fail-closed) にする
- **監査増幅の防止**: `control_requests_per_minute` (R-7) の判定は**認証と監査 INSERT より前段**に置く。未認証リクエストが無制限に監査行を生成する DoS 経路を塞ぐ。rate limit 超過の拒否自体は (認証前・実行者不明のため) 耐久監査の対象外とし、この線引きを CONTROL_MAPPING の SI-14 行に明記する
- **unit-of-work の導入 (§8 B-2 — 既存ストアはメソッド内で自己 commit しており、同一トランザクション要求と両立しない)**: `CredentialStore` / `PostgresCredentialStore` / 新設 `ControlCredentialStore` ペアに `unit_of_work()` (context manager) を導入し、状態変更メソッド (`add`/`set_state`/`rotate`/`delete`) は work ハンドル必須の形へ改める。自己 commit 版は削除し、既存呼び出し元 (`ops.py`、`ControlAuthority`、既存テスト) を追随させる。in-memory 側の `unit_of_work()` は「例外時に適用済み変更を巻き戻す」擬似トランザクションとして実装し、parity テストの対象にする (sink 故障注入で変更が残らないことまで含む)
- bootstrap / reset (CLI) も同一トランザクションで `control_audit` に書く。**`ops.py` の既存サブコマンド (issue/rotate/revoke/disable/enable/delete) も同様に `control_audit` へ書くよう改める** (§8 M-10 — SI-14 の "Control Plane administrative change" は帯域外経路にも掛かる。unit-of-work 導入で同時に済む)
- application-plane の耐久 audit sink はフェーズ3のまま。本判断はフェーズ3を control-plane 分だけ先行実施するものであり、フェーズ3側はこのテーブルと形状を再利用してよい (拘束はしない)

### R-7: SI-08 資源境界 — 3クラスを enforce し discovery で公開

- `applications`: 登録済み Application 総数の上限。超過は `LIMIT_EXCEEDED`
- `credentials_per_application`: Application あたりの未失効 application credential 数の上限。超過は `LIMIT_EXCEEDED` (失効済みは数えない — 失効を上限圧迫の理由にしない)
- `control_requests_per_minute`: 制御面全体の分間リクエスト上限 (固定窓カウンタで足りる。データ面 `_acquire_rate` と同系)。超過は `LIMIT_EXCEEDED` (429)。判定は処理パイプラインの最前段 (R-6)
- 値は配備 profile (環境変数 `R2DB_CONTROL_LIMIT_*`、既定は契約 `example_profile` の値)。`GET /control/v1/capabilities` の `limits` / `limit_enforcement` (3クラスとも `enforced`) で公開する。この公開と enforce は C-14 の検証ベクタに含める (§8 M-4)

### R-8: 認証は面ごとのストア分離で相互 fail-closed を構造化する

制御面の認証は `Bearer` → `ControlCredentialStore` (in-memory / Postgres の同一 call surface ペア、P2-D4 と同じくリクエスト毎 DB 参照・キャッシュなし・`authorization_propagation_bound_ms: 0`)。C-14 の境界要求はストア分離から構造的に従う:

- application credential で `/control/v1` → control ストアに verifier が存在せず `AUTH_INVALID` (401)。**専用 pepper (R-2) により、仮に同一 secret 文字列でも verifier が一致しない**。`FORBIDDEN` (403) にしない — 403 は「提示された秘密が正当な application credential である」という存在区別を漏らし、契約 `errors.disclosure` に触れる (§8 m-7)
- control credential で `/v1` (data/schema) → application ストアに存在せず `AUTH_INVALID` (401)
- 失効/無効/must_rotate 超過/DB 不達は既存語彙どおり `AUTH_REVOKED` / `AUTH_INVALID` / `FORBIDDEN` / `AUTH_STATE_UNAVAILABLE` (503。401 に化けさせない)
- 契約は C-14 に特定コードを定めず "fail-closed" のみ要求する。**conformance 側は単一コードに固定せず「401 系 fail-closed」で検証する** (§8 m-7 — 実装差 (surface-absent の 404 等) を跨いで条件が成立するように)
- `RequestByteBoundMiddleware` (body byte bound + request_id 生成) は制御面アプリにも同一のものを装着する

### R-9: capability 申告は環境変数由来で composition root 注入。artifact 更新漏れ検知を同時に塞ぐ

`control_plane` の status は配備の事実 (制御面を提供しているか) であり、コードが一律に決めるものではない。**application 面プロセスは制御面の配備有無を自分では知り得ない** (既定が別プロセスのため — §8 M-7 で v1 の「main.py が enabled を注入」は申告乖離経路と指摘された)。よって:

- `DataService` に `control_plane_status` を構築時注入 (既定 `unavailable`)。`main.py` は **環境変数 `R2DB_CONTROL_PLANE_STATUS`** (許容値 `enabled`/`unavailable`、既定 `unavailable`) から注入する。runbook に「`control_main` を同一配備で起動する場合にのみ `enabled` を設定する」と明記し、この申告が配備者の宣言であることを明確にする
- 分離配備における権威は制御面自身の discovery である: `GET /control/v1/capabilities` は制御面の CapabilityDocument (`contract_version`、`capabilities: {control_plane: enabled, audit_query: unavailable}`、R-7 の limits、`authorization_propagation_bound_ms: 0`、`role: control`) を返す。契約 `versioning.control_discovery` は「分離配備の制御面は `/v1/capabilities` との同居を前提にできない」と定めており、`/v1` 側の申告は同居配備の便宜
- `config/capabilities.json` に `control_plane` を追記する。**既知の欠陥**: `test_r2_capability_artifact_matches_real_capabilities_response` は artifact に書かれた名前しか突合せず、書き忘れを検知しない。本フェーズで逆向きの突合 (実応答の全 capability 名が artifact に列挙されていること) をテストに追加し、この検知漏れクラスを閉じる (逆向き C-12 と同じ発想)

### R-10: `ops.py` の位置づけ再定義 — 儀式 + break-glass。in-band の正準は HTTP

- 正準の in-band 管理面は `/control/v1` になる。`ops.py` の冒頭宣言「CCR-14 未裁定のため暫定」を「bootstrap/reset の帯域外儀式 (契約条項) + 運用者 break-glass」に書き換える
- 既存サブコマンドは**残す** (運用者 OS 権限下の帯域外操作は契約が禁じるものではなく、制御面が落ちている時の復旧経路を消すのは安全側でない)。ただし `--help` と docstring に「通常運用は `/control/v1` を使う」を明記し、**全サブコマンドが `control_audit` に同一トランザクションで監査を書く** (R-6 / §8 M-10)
- `delete-credential` (行の物理削除) は HTTP に存在しない帯域外専用操作として残る (契約の削除対象外方針と両立: 削除は provisioning 解除 runbook の一部でのみ使う)

## 2. HTTP 面の形状 (endpoint → 実装対応)

処理順序は全 endpoint 共通: **rate limit (R-7 最前段) → byte bound / request_id → 認証 (拒否は耐久監査) → shape 検証 → capability 拒否 → 対象解決 → 状態検査 → limit 検査 → 実行 + 同一トランザクション監査**。応答は契約 schema (`_check_object_shape` と同じ import 時ロード機構を制御面 schema 群に適用)。エラーは `application/problem+json`、未捕捉例外は汎用 503 (SI-10)。

| endpoint | service 操作 | 主なエラー経路 |
|---|---|---|
| `GET /control/v1/capabilities` | CapabilityDocument 構築 (R-9) | must_rotate でも許可 (R-5) |
| `POST /control/v1/applications` | 登録済み行の作成 (R-4)。slug は契約 pattern `^[a-z][a-z0-9_]{0,32}$` を shape 検証 | 重複 `CONFLICT`、`applications` 上限 `LIMIT_EXCEEDED`、shape 違反 `VALIDATION_FAILED` |
| `GET /control/v1/applications` | 一覧 (`application_id`, `enabled`) | — |
| `POST .../applications/{id}/disable` | `enabled=false` (可逆) | 不在 `NOT_FOUND` |
| `POST .../applications/{id}/enable` | `enabled=true` | 不在 `NOT_FOUND` |
| `POST /control/v1/credentials` | application credential 発行。`role` が runtime/developer なら発行し秘密を一度だけ返す | **評価順序を固定 (§8 M-1): shape 検証の直後、対象 Application の存在・状態・limit のどの検査よりも前に、`role=control` を `CAPABILITY_UNSUPPORTED` で拒否する** (「存在しない app + role=control」「上限到達 + role=control」でも必ず `CAPABILITY_UNSUPPORTED`。C-17 の「capability 拒否がキー名解決に先行する」と同じ書式)。以降: app 不在 `NOT_FOUND`、`credentials_per_application` 上限 `LIMIT_EXCEEDED` |
| `GET /control/v1/credentials` | application + control 両 credential の一覧 (秘密・verifier なし。control 行は `application_id` 無し・`role: control`)。`must_rotate` は**露出しない** (契約に無いフィールドの実装独自追加は公開面の乖離 — 契約 additive 候補として §12 台帳へ。§8 m-9) | — |
| `POST .../credentials/{id}/rotate` | verifier 差替え、新秘密を一度だけ返す。応答成功時点で旧秘密失効 (リクエスト毎 DB 参照なので伝播 0ms)。must_rotate credential の自己 rotate はここ (R-5) | 不在 `NOT_FOUND`。**revoked への rotate は `VALIDATION_FAILED` で拒否** (§8 M-2 — 既存 rotate は revoked を見ておらず「既存意味論」は存在しなかった。終端状態への書込みを許すと「決して認証できない秘密」を成功として返す誤導になる。un-revoke 拒否と同じコードに揃える)。disabled への rotate は**許す** (可逆状態であり、rotate→enable の運用順序を禁じる理由が無い — 監督決定、覆せる) |
| `POST .../credentials/{id}/revoke` | `revoked=true` (終端)。Q-1 休止中は確認フィールド不検査 (§0.5) | 不在 `NOT_FOUND` |
| `POST .../credentials/{id}/disable` | `enabled=false` (可逆) | 不在 `NOT_FOUND` |
| `POST .../credentials/{id}/enable` | `enabled=true`。**revoked は反転しない** (un-revoke は既存どおり `VALIDATION_FAILED`、enable 自体は revoked を残したまま state を返す — C-13 が固定済みの意味論) | 不在 `NOT_FOUND` |

credential の id 系操作は application / control 両テーブルを対象にする (id prefix `crd_`/`ctl_` で引き先が決まるが、**探索は id でなく両ストア照会**とし、prefix を意味論に昇格させない)。

## 3. service 層の構成

- 新クラス `ControlPlaneService` (新モジュール `control_plane.py`): §2 の操作カタログ + R-5 must_rotate ゲート + R-6 監査 + R-7 limits を持つ制御面 facade。構築時に `applications`/`credentials`/`control_credentials` のストアと audit sink と limits を受ける
- ストアは既存パターンの踏襲: in-memory (`auth.py` に `ControlCredentialStore` 追加、**既存 `CredentialStore` にも `rotate` を追加** — 現状 Postgres 側にしか無い) と Postgres の**同一 call surface ペア**。R-6 の `unit_of_work()` を含めて parity は両実装横断のテストで固定 (CCR-13 の `test_parity_*` 方式)
- 既存 `ControlAuthority` は**残し、`ControlPlaneService` の下位に置く** (in-process conformance adapter と既存テストの互換面)。`ControlAuthority` に無い操作 (list 系、rotate、control credential lifecycle) は `ControlPlaneService` に実装し、重複する操作は `ControlAuthority` 経由に委譲して意味論を一本化する。公開面から `ControlAuthority` へ直接到達できない現行トポロジは不変
- must_rotate ゲートと `role=control` 発行拒否は **`ControlPlaneService` (service 層) に置き、HTTP 層に置かない** — 拒否が bind 層/HTTP 層に落ちて in-process 経路で意味論が変わる形 (前フェーズ B-1 の同型) を避ける
- `AuthorityTopology` に control_plane HTTP 面のノードを追加し、`validate()` が「public_plane → control_plane 不到達」「control_plane → application データ面不到達 (R-3)」を検証する。**既存 `test_topology.py` のアサーションを壊さないことを WP-4 の完了条件に含める** (§8 m-8)

## 4. conformance — port 拡張と C-14/C-15 の executable 化

### port v1.5 (共通、実装非依存)

- control 面操作を port に追加: `control_capabilities()` / `register_application_inband()` / `list_applications()` / `issue_credential_inband(app, role)` / `list_credentials()` / `rotate_credential()` / `revoke_credential_inband()` / `set_credential_enabled_inband()` / application enable/disable、および儀式フック `bootstrap()` / `reset()`。**既存の adapter 直呼び系操作 (`provision_application` 等) は残る** — それらは「テスト前提を作る特権的セットアップ」であり、新操作は「in-band 面そのものの検証対象」。役割が違う
- **面を持たない peer の分岐は2形に定義する (§8 M-8 — 「一様に `CAPABILITY_UNSUPPORTED`」の一括りは C-17 で確立済みの先例と衝突していた)**:
  - **(a) surface-absent**: 呼べる公開 surface がそもそも無い → port 操作は `SurfaceAbsent` (既存の型、C-17/C-18 先例) を `surface`/`forbidden_parameters` 付きで送出し、テストは `signature_forbids_parameters` により「その surface が実在せず要求を受け取れない」ことをソース署名で独立検証する。**拒否の捏造 (peer に届かない拒否を adapter が返すこと) はしない**
  - **(b) declared-unavailable**: surface は在るが `control_plane: unavailable` を申告する実装 → 実在の入口が `CAPABILITY_UNSUPPORTED` で一様拒否することを検証。**現時点でこの形の peer は無い** (将来の配備形のために条件定義のみ置く)
- adapter × フェーズの割当表:

| adapter | WP-1〜WP-4 | WP-5 以降 |
|---|---|---|
| r2db in-process | surface-absent (in-band 面は未実装。`ControlAuthority` は非公開の特権機構であり公開 surface ではない) | **provided** (ControlPlaneService 直結) |
| r2db http | surface-absent (`/control/v1` は 404 — 実在の入口が無い) | **provided** (`create_control_app` への in-process HTTP) |
| MitateDB | surface-absent | surface-absent のまま (次フェーズで provided 化) |

これにより「skip は fail」原則と両立する: どの分岐も実行され、surface-absent は署名検証という実在の証拠を要求する。

### C-14 (authority boundary) の検証ベクタ

1. application credential (runtime/developer 両方) × 全 11 control endpoint → fail-closed (**単一コードに固定せず 401 系 fail-closed で検証** — §8 m-7)
2. control credential × data/schema endpoint (query/mutations/catalog/schema_operations) → 拒否
3. `role=control` の in-band 発行要求 → `CAPABILITY_UNSUPPORTED`。**前提バリエーションを含む (§8 M-1): 対象 Application が不在でも / disabled でも / `credentials_per_application` 上限到達でも、必ず `CAPABILITY_UNSUPPORTED`** (評価順序の検証)
4. 逆向き: 申告 (`control_plane` status) と実挙動の一致 — unavailable 申告で操作が通れば赤、enabled 申告で拒否されれば赤
5. **資源境界 (§8 M-4)**: 3クラスが `GET /control/v1/capabilities` の `limits`/`limit_enforcement` に現れ、各クラスの超過が `LIMIT_EXCEEDED` になる (CONDITIONS.md の C-14 行に SI-08 を追加登録する)

### C-15 (bootstrap/reset lifecycle) の検証ベクタ

1. control credential 存在下の bootstrap 再実行 → 拒否。**全 credential 失効後の再実行も拒否** (§8 M-6)
2. reset → 既存 control credential **全数**が失効し、旧秘密での認証が即座に落ちる。Application データと application credential と監査は不変
3. 初回 credential の非恒久性: rotate 完遂までは capabilities/自己 rotate 以外 `FORBIDDEN`、rotate 後に全権
4. 制御変更の正準監査イベント発行 + **拒否イベントの耐久記録** (§8 B-3)。audit sink 故障注入で変更が abort する fail-closed も、故障注入可能な構成で検証
5. **既定 credential の不在 (§8 M-5、契約 bootstrap[2])**: bootstrap 前は control 認証がいかなる秘密でも通らない。独立に bootstrap した2環境の初回秘密が一致しない

### 既存条件への波及

- **C-08 (revocation boundary) の格上げ**: `conformance_adapter_r2db_http.py` の control 操作 (`ControlAuthority` 直呼び・DB 直接 UPDATE) を `create_control_app` への in-process HTTP 呼出しに置き換えることで、既存条件が「/control/v1 経由の変更が data 面へ伝播する」実スタック検証へ自動的に格上げされる
- **C-13 の再活性化ベクタ台帳 (§8 M-3)**: `/control/v1` の enable・rotate (application/control 両 credential) は新しい再活性化候補 surface である。両 r2db adapter の `credential_reactivation_vectors()` に追加し、「この peer の control-plane surface はこれで全部」という網羅宣言を維持する。変異注入で検出力を確認 (WP-5)

## 5. 実装順序 (work packages)

単一コミット規則 (前フェーズで確立): **申告と実挙動は WP-5 の単一コミットでのみ同時に動く**。それまで `control_plane` は unavailable のまま、`create_control_app` は composition root に接続せず、module-level `app` も作らない。

| WP | 内容 | 完了条件 |
|---|---|---|
| WP-0 | 本設計の独立レビュー (Opus) と反映 | 済 (v1.1、§8) |
| WP-1 | conformance port v1.5 + C-14/C-15 テスト実装 + 3 adapter の surface-absent 分岐 (署名検証) | 3 adapter で C-14/C-15 が実行され green (全 adapter surface-absent)。変異注入で各ベクタの検出力を確認 |
| WP-2 | 0006 migration (applications 二状態化 + `begin_provision_application` 改訂 + control_credentials / r2dbsvc_controlplane / control_audit / GRANT 群) + unit-of-work 導入 (両ストア + 既存呼び出し元追随) + ControlCredentialStore ペア + 専用 pepper + `ops.py` bootstrap/reset + 既存サブコマンドの監査化 + `main.py` 突合強化 | store parity テスト (unit_of_work 含む) + 儀式の C-15 相当単体テスト + 0002 改訂後の provisioning 往復テスト + 変異注入 |
| WP-3 | `ControlPlaneService` (must_rotate ゲート・R-7 limits・R-6 同一トランザクション監査 + 拒否監査) | 単体 + parity + sink 故障注入 fail-closed |
| WP-4 | `control_http.py` + `control_main.py` (factory のみ、module-level app なし) + AuthorityTopology 拡張 | HTTP 層テスト (httpx ASGITransport)。`test_topology.py` 既存アサーション維持。申告は据え置き |
| WP-5 | 申告 flip (env 由来 `control_plane` status + capabilities.json + R-9 逆向き突合テスト) + `control_main` module-level app + 両 r2db adapter の provided 化 + C-13 再活性化ベクタ追加 + C-14/C-15 provided 分岐 green — **単一コミット** | 現行 suite 全 green + 追加分。逆向き C-14 ベクタ 4 が両方向で赤くなることを変異で確認 |
| WP-6 | CONTROL_MAPPING (SI-00/02/06/08/13/14 行 + C-14 行の SI-08 登録) + DEPLOYMENT_RUNBOOK / POSTGRES_PROVISIONING_RUNBOOK (0006・儀式手順・ロックアウト復旧・`R2DB_CONTROL_PLANE_STATUS` の運用) + README + `ops.py` 再定義文言 + 実装記録・将来課題台帳を本書 §11/§12 に | ドキュメント整合。引き継ぎ更新 |

## 6. 申し送り (依頼者への報告事項)

1. **Q-1 (§0.5)**: 破壊的確認の有効性定義は未裁定のまま、契約の明文に従い休止状態で実装する。裁定が出れば additive に実効化
2. **監督決定 (覆せる形での報告)**: (a) 初回 credential 非恒久化は must-rotate 方式で、「1回の強制ローテートが契約 bootstrap[5] を満たす」と読む (R-5)、(b) control-plane 監査の先行耐久化 — 状態変更 + 拒否イベント (R-6)、(c) `register_application` は registry 二状態化の「登録済み」まで (R-4。0002 関数の改訂を含む)、(d) `ops.py` は儀式 + break-glass として存続し全サブコマンドを監査化 (R-10)、(e) 制御面 DB role の新設と権限形状 (R-3)、(f) revoked への rotate は `VALIDATION_FAILED`、disabled への rotate は許可 (§2)、(g) `control_plane` 申告は配備者の環境変数宣言 (R-9)。いずれも契約が機構を定めない領域の実装ポリシーであり、契約変更を伴わない
3. 発行対象 Application が disabled のときの credential 発行可否は契約が定めない。**発行は許す** (credential の実効性は `applications.enabled` が既に握っており、発行拒否は二重ゲート) — 文言確定レベルの細部として監督が決めた。覆す場合は WP-3 の一行変更
4. `CredentialsResult` に `must_rotate` を露出するかは契約 additive 候補として台帳に積む (§8 m-9。運用者が儀式未完遂の credential を in-band で見分けたくなったら契約側で判断)
5. フェーズ3 (耐久 audit sink) の設計は R-6 の `control_audit` を出発点にできるが、拘束しない

## 7. リスクとレビュー重点

- **R-3 の権限表が本設計の安全の要**: `r2dbsvc_controlplane` に余計な GRANT (特に `control_credentials` への INSERT、provisioning 関数への EXECUTE、SEQUENCE/FUNCTION への付与) が紛れると案Bの帯域外限定が崩れる。0006 のレビューは GRANT の全行を契約条項に対応付けて読むこと
- **0002 関数改訂 (R-4) は既存 provisioning 往復の回帰リスク**: 「運用者先行 INSERT フロー」と「登録済み行の UPDATE フロー」の両方をテストで往復させること。`0004` deprovision ガードとの相互作用 (登録済みのみの行は deprovision 対象にならない) も確認
- **reset の原子性** (R-5): 全失効と新規発行が同一トランザクションでないと「失効を生き延びる経路」が瞬間的に開く
- **must_rotate ゲートの列挙** (R-5): 許可リスト (capabilities + 自己 rotate) 方式で実装し、拒否リスト方式にしない (endpoint 追加時に fail-open する)
- **同一トランザクション監査** (R-6) と接続プールの相互作用: 状態変更と INSERT が別コネクションに割れると fail-closed が壊れる。unit_of_work が単一コネクション・単一トランザクションを型で強制する形にする
- **前フェーズの教訓の再発形**: 拒否の所在が bind 層に落ちて公開面へ自動開放される形 (B-1 の同型)。制御面では「`role=control` 発行拒否」「must_rotate ゲート」が候補 — どちらも service 層 (`ControlPlaneService`) に置き、HTTP 層に置かない (§3)
- 実装者の完了報告は実測で裏取る。テスト追加は変異注入まで

## 8. 訂正記録 (WP-0 独立レビュー、Opus、2026-08-29)

blocker 3 / major 10 / minor 10 / nit 2。全指摘を監督が一次ソースで実測裏取りし、誤指摘 0。全件を v1.1 に反映した。

- **B-1**: v1 の R-4「applications 行を作るだけ」は既存列構造 (`database_name` 等 NOT NULL UNIQUE) で実装不能であり、ダミー値は実 provisioning を恒久的に塞ぐ。→ registry 二状態化 + `begin_provision_application` 改訂 + `main.py` 突合強化 (R-4)
- **B-2**: 既存ストアはメソッド内自己 commit で、同一トランザクション監査と両立しない。§3「同一 call surface」と §7「型で強制」が自己矛盾。→ `unit_of_work()` 導入と既存呼び出し元の追随を明文化 (R-6、WP-2)
- **B-3**: 契約 `audit.sink_failure_policy` は authentication/authorization **denial** の耐久記録失敗も fail-closed と定めるのに、v1 は耐久監査を状態変更系に限定していた。→ 拒否イベントも耐久記録、rate limit を最前段化して監査増幅を防止 (R-6)
- **M-1**: `role=control` 拒否の評価順序が未定義で「NOT_FOUND が先」の実装が設計適合を主張できた。→ 順序固定 + C-14 ベクタ3に前提バリエーション (§2、§4)
- **M-2**: 「revoked への rotate は既存ストア意味論に従い拒否」は事実誤認 (既存 rotate は revoked を見ない。in-memory には rotate 自体が無い)。→ 新規に拒否を定義 (`VALIDATION_FAILED`)、in-memory rotate 追加 (§2、§3)
- **M-3**: C-13 の `credential_reactivation_vectors()` 網羅宣言が新 surface (HTTP enable/rotate) で空洞化する。→ WP-5 でベクタ追加 (§4)
- **M-4**: 契約が列挙する「資源境界の公開と enforce」条件がベクタに無かった。→ C-14 ベクタ5 + CONDITIONS.md の SI-08 登録 (§4)
- **M-5**: 「既定 credential 不在」(契約 bootstrap[2]) のベクタ欠落。→ C-15 ベクタ5 (§4)
- **M-6**: bootstrap 拒否条件を「未失効が存在」としており、全件失効状態で reset 以外の発行経路が開いた (契約は "While a control credential exists")。→ 行が存在すれば拒否 (R-5)
- **M-7**: 「main.py が enabled を注入」は既定分離配備で申告乖離 (enabled 申告 + 制御面不在) を作る。→ 環境変数 `R2DB_CONTROL_PLANE_STATUS` による配備者宣言 (R-9)
- **M-8**: unprovided 分岐「一様に `CAPABILITY_UNSUPPORTED`」は C-17 で確立済みの `SurfaceAbsent`/署名検証の先例と衝突し、r2db-http の 404 とも合わない。→ surface-absent / declared-unavailable の2形 + adapter×フェーズ割当表 (§4)
- **M-9**: `control_audit` 列が契約 `audit.fields` の `event_id`/`occurred_at` を欠いていた。→ 12 項目全て + `recorded_at` (R-6)
- **M-10**: `ops.py` 既存サブコマンドの無監査を R-10 が恒久化していた。→ 全サブコマンド監査化 (R-6、R-10)
- **minor**: m-1 rotate-once 読みの明文化 (R-5)、m-2 ロックアウト経路と reset 復旧の明記 (R-5)、m-3 `r2dbsvc_control` への control_audit INSERT 明示 GRANT (R-3)、m-4 append-only 主張の範囲限定 (R-3)、m-5 SEQUENCE/FUNCTION GRANT 不在の確認項目化 (R-3、§7)、m-6 role 名衝突なし・自動開放経路なしの確認記録 (R-2)、m-7 C-14 のコード非固定 + 401/403 の開示論拠 (R-8、§4)、m-8 `test_topology.py` 既存アサーション維持 (§3、WP-4)、m-9 `must_rotate` 非露出 + 契約 additive 候補化 (§2、§6)、m-10 module-level app を WP-5 へ (R-1、WP-4/5)
- **nit**: n-1 規範リストに SI-09 追加 (冒頭)、n-2 「544」実測値依存の記述を除去 (WP-5)
- **レビュー確認済み (指摘なしの観点)**: 案Bの帯域外限定は HTTP (`CAPABILITY_UNSUPPORTED`)・DB GRANT (INSERT 欠如)・CLI (control role 発行コマンド不在 + CHECK 制約) の全経路で閉じている。rotate の in-band 提供は案Bと矛盾しない (同一 credential の秘密差替えであり、失効を生き延びる永続性を作らない)。§2 の schema 対応 (CredentialsResult への control credential 混載、CapabilityDocument の `role: control` を含む) は契約適合。HTTP status 対応に既存実装との衝突なし
