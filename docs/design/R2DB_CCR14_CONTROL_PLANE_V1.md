# r2db-api CCR-14 control plane HTTP 面 (`/control/v1`) 設計 v1.1

- 日付: 2026-08-29。設計: Fable (監督)。実装: Sonnet subagents、レビュー: Opus subagents
- 改訂: v1.1 — WP-0 独立レビュー (Opus、blocker 3 / major 10 / minor 10 / nit 2、全指摘を実測で裏取り済み・誤指摘 0) を反映。§8 訂正記録
- 改訂: v1.2 — 依頼者との Q-1 検討 (2026-08-29) を反映: 確認機構の守備範囲の明文化 (§0.5)、CLI break-glass への control credential enable/rotate 追加 (R-10)、誤配・侵害への装備 (R-11)、契約 additive 候補2件 (§6)。§9 改訂記録
- 改訂: v1.3 — 抑止宣言の採用 (依頼者合意、2026-08-29): 制御面の拒否応答に「徒労」と「帰属」の真実の宣言を載せる (R-11、§2)。§9 改訂記録
- 改訂: v1.4 — WP-1 完了 (2026-08-29): port v1.5 / C-14・C-15 executable 化の実装レビュー (Opus、blocker 2 / major 7 / minor 7 / nit 2) の反映と、実装中の監督決定・変異注入結果。§10 記録
- 改訂: v1.5 — WP-2 完了 (2026-08-29): 0006 migration / unit-of-work / ControlCredentialStore / 儀式 CLI の実装レビュー (Opus、blocker 2 / major 5 / minor 9 / nit 2) の反映と監督決定 — 特に R-4 の関数分割の訂正 (provisioning 列の確定は finish 側)。§11 記録
- 改訂: v1.6 — WP-3 完了 (2026-08-29): `ControlPlaneService` の実装レビュー (Opus、major 3 / minor 11 / nit 3) の反映と監督決定 — 特に AUTH_REQUIRED の監査対象化と抑止宣言の2分割 (記録/帰属)。§12 記録
- 改訂: v1.7 — WP-4 完了 (2026-08-29): `control_http.py`/`control_main.py` (factory のみ)/AuthorityTopology 拡張の実装レビュー (Opus、major 2 / minor 6 / nit 2) の反映と監督決定 — 特に rate 前課金 (`check_rate` + `rate_precharged`) と control_plane_http→audit 辺の訂正。§13 記録
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

**Q-1: 破壊的確認の有効性定義 (C-06 共通化の前提)。** 契約 1.1.0 の `revoke_credential` 意味論は「最後の有効な control credential の失効は許可され、明示的確認を要する — ただし有効な確認の定義は未解決の契約判断であり、**解決まで本条項は実効化しない**」と自ら定める。よって本実装は revoke を確認検査なしで提供することが契約適合であり、独自の確認規則を発明して契約の空白を埋めることは (CCR-13 の Q-1 で是正した欠陥の形の再発になるため) しない。`CredentialRevokeRequest` の `destructive`/`confirmation` フィールドは schema どおり受理し、内容は検査しない。**この状態は MitateDB の既知欠落 (確認トークン不検証) と同型である**ことを明記して裁定を仰ぐ。裁定のたたき台 (依頼者との往復で具体化、2026-08-29): **サーバが危険を宣言し、クライアントがそれを復唱したときのみ有効**とする状態レスな二段階方式。確認なしの破壊的要求は `DESTRUCTIVE_CONFIRMATION_REQUIRED` で拒否し、その problem+json に正準の確認句 (`required_confirmation` — 操作・対象・帰結クラスから決定論的に構成、再作成可能な対象は状態指紋を含める)、`consequence`、**可逆な代替 (`reversible_alternative`) と復旧経路 (`recovery`)** を機械可読で宣言する。有効な確認 = `destructive: true` + 確認句の全文一致。サーバは句を再計算できるため無状態 (トークン保存・失効・SI-08 の新資源を持ち込まない)。確定後に additive に実効化 (拒否コードは既に契約語彙にある)。**本設計はこの裁定を実装のブロッカーにしない** — 確定後の実効化は語彙追加なしの意味論追加で済む。

**守備範囲の明文化 (依頼者と合意)**: 確認機構が守るのは「要求の曖昧さの排除」まで (C-06 の文言 "ambiguous requests do not execute" のとおり)。正しい credential と正しい手順を備えた「意図しない要求」「悪意の要求」はいかなる in-band 確認でも区別できない (人間向けダイアログでも同じ)。その防御は確認機構ではなく R-11 の層が担う。`reversible_alternative`/`recovery` の宣言は、手順に忠実なエージェント製クライアントを可逆側 (disable) へ誘導するための第3層である。

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
- **control credential の enable / rotate を break-glass サブコマンドに追加する** (依頼者合意、2026-08-29): 唯一の control credential が disable された状態は in-band の enable を呼べる者がいない詰みであり、CLI の enable は秘密の再配布なしに復旧できる (reset より軽い)。秘密の紛失は CLI の rotate (同一 credential_id のまま新秘密 — 監査の連続性を保つ)。**発行 (issue) だけは bootstrap/reset の儀式限定のまま**で、案Bは崩さない。revoke された control credential の復活手段は意図的に作らない — un-revoke は「失効した」という監査事実を偽にし (SI-13 の空洞化)、正準の復旧は reset である

### R-11: 誤配・侵害への装備 — control credential が間違った手に渡る前提の層 (依頼者検討、2026-08-29)

確認機構 (§0.5) では守れない「正規手順を踏む意図しない/悪意の要求」への装備。人は control credential をテストアプリに渡すし、悪意ある者に渡ることもある — その前提で、被害を可逆・可視・有界にする。設計上すでに成立している性質の明文化と、runbook 成果物の追加:

- **可逆性の全数**: control credential でできる操作のうち不可逆は revoke のみで、revoke が壊すのは credential だけ (データは壊れない)。disable された app → enable で復旧、不正発行された credential → 一覧に必ず現れ個別 revoke、ゴミ登録 → disable、rotate による締め出し → reset
- **証拠は消せない**: `control_audit` は制御面 role から INSERT のみ (R-3)。**control credential 保持者にも監査は消せない**。拒否イベントも耐久記録されるため (R-6)、締め出された正規運用者の失敗ログ自体が侵害の検知信号になる
- **持続化できない**: 案B + reset。攻撃者は control credential を増産できず、reset 一発で失権する
- **侵害/誤操作 playbook** (WP-6 成果物): reset → 監査を時刻で切って差分列挙 (`ops.py audit-report --since` 補助コマンド) → 侵害窓中に発行された credential の revoke → disable された app の enable。「control credential 侵害は有界・全復旧可能な事象 (残る実害は窓中の発行 credential 経由のデータ面到達と一時的な運用停止)」として CONTROL_MAPPING に記載
- **sandbox 規則** (runbook 明文): control credential をアプリケーションに保持させない。テスト・練習は専用配備で行う (registry DB ひとつ + 儀式1回で立つ — 分離配備設計の帰結)
- **契約 additive 候補2件** (§6 台帳): (i) `audit` role による制御面**読み取り** (一覧・capabilities) の許可 — 「配れる弱い credential」を用意し、root を配る動機を消す。(ii) per-application **発行凍結** (CLI 限定トグル) — 盗まれた control credential からデータ面への最短経路 (任意 app への credential 発行) を app 単位で閉じる
- **推奨しない**: control credential の複数本運用 (悪意保持者は予備ごと revoke でき、常設の全能秘密が増えるだけ。うっかり締め出しは reset の RTO 数分で足りる)
- **抑止宣言 (v1.3、依頼者合意)**: 制御面の拒否応答に**真実の宣言のみ**を載せる。(i) 徒労の宣言 — `role=control` 発行拒否の文言に「control credential を作る in-band 経路は存在せず、作成は運用者の儀式に限られ、例外はない」と明記。(ii) 帰属の宣言 — 制御面の拒否 problem+json に機械可読の `"audited": true` と「この要求は実行 credential に帰属して耐久記録され、control credential でも消せない」の一文 (R-6 で事実になっている)。狙いは利用者側エージェントの安全学習を発火させ**警告・注意喚起を出させる**ことまで — 悪意のない人間を慎重にさせ、悪意のある者には「この系は面倒だ」と映る (依頼者が期待効果として確定)。ハッタリ・honeypot・偽応答は「宣言 = 実挙動」の conformance 体系を壊すため禁止。決意した攻撃者の素のクライアントには効かないため、安全はこの層に依存しない (主役は本節冒頭の構造的性質)

## 2. HTTP 面の形状 (endpoint → 実装対応)

処理順序は全 endpoint 共通: **rate limit (R-7 最前段) → byte bound / request_id → 認証 (拒否は耐久監査) → shape 検証 → capability 拒否 → 対象解決 → 状態検査 → limit 検査 → 実行 + 同一トランザクション監査**。応答は契約 schema (`_check_object_shape` と同じ import 時ロード機構を制御面 schema 群に適用)。エラーは `application/problem+json` で、認証認可・capability の拒否には R-11 の抑止宣言 (`audited: true` + 帰属の一文。`role=control` 発行拒否には徒労の明記) を含める。未捕捉例外は汎用 503 (SI-10 — 内部情報は出さない。抑止宣言は内部を漏らさない定型文のみ)。

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
| WP-6 | CONTROL_MAPPING (SI-00/02/06/08/13/14 行 + C-14 行の SI-08 登録) + DEPLOYMENT_RUNBOOK / POSTGRES_PROVISIONING_RUNBOOK (0006・儀式手順・ロックアウト復旧・`R2DB_CONTROL_PLANE_STATUS` の運用) + **侵害/誤操作 playbook・sandbox 規則・`ops.py audit-report` (R-11)** + README + `ops.py` 再定義文言 + 実装記録・将来課題台帳を本書 §11/§12 に | ドキュメント整合。引き継ぎ更新 |

## 6. 申し送り (依頼者への報告事項)

1. **Q-1 (§0.5)**: 破壊的確認の有効性定義は未裁定のまま、契約の明文に従い休止状態で実装する。裁定が出れば additive に実効化
2. **監督決定 (覆せる形での報告)**: (a) 初回 credential 非恒久化は must-rotate 方式で、「1回の強制ローテートが契約 bootstrap[5] を満たす」と読む (R-5)、(b) control-plane 監査の先行耐久化 — 状態変更 + 拒否イベント (R-6)、(c) `register_application` は registry 二状態化の「登録済み」まで (R-4。0002 関数の改訂を含む)、(d) `ops.py` は儀式 + break-glass として存続し全サブコマンドを監査化 (R-10)、(e) 制御面 DB role の新設と権限形状 (R-3)、(f) revoked への rotate は `VALIDATION_FAILED`、disabled への rotate は許可 (§2)、(g) `control_plane` 申告は配備者の環境変数宣言 (R-9)。いずれも契約が機構を定めない領域の実装ポリシーであり、契約変更を伴わない
3. 発行対象 Application が disabled のときの credential 発行可否は契約が定めない。**発行は許す** (credential の実効性は `applications.enabled` が既に握っており、発行拒否は二重ゲート) — 文言確定レベルの細部として監督が決めた。覆す場合は WP-3 の一行変更
4. `CredentialsResult` に `must_rotate` を露出するかは契約 additive 候補として台帳に積む (§8 m-9。運用者が儀式未完遂の credential を in-band で見分けたくなったら契約側で判断)
5. **契約 additive 候補 (R-11、依頼者検討から)**: `audit` role による制御面読み取り / per-application 発行凍結。いずれも本フェーズには入れず台帳へ
6. **監督決定の追加 (依頼者合意済み、2026-08-29)**: CLI break-glass への control credential enable/rotate 追加 (R-10)、playbook・sandbox 規則の WP-6 組み込み (R-11)、抑止宣言の採用 — 期待効果は「利用者側エージェントの警告・注意喚起」まで (R-11、§2)
7. フェーズ3 (耐久 audit sink) の設計は R-6 の `control_audit` を出発点にできるが、拘束しない

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

## 9. 改訂記録 (依頼者検討の反映、2026-08-29、v1.2 / v1.3)

依頼者との Q-1 検討の往復で確定・追加した内容。契約変更は伴わない (契約 additive 候補は台帳止め)。

- Q-1 たたき台を具体化: 状態レスな二段階 (hazard 宣言 → 決定論的な確認句の復唱)。宣言に `reversible_alternative`/`recovery` を含める (§0.5)
- 確認機構の守備範囲を「曖昧さの排除まで」と明文化。正規手順を踏む意図しない/悪意の要求はプロトコルで区別できない — その防御は層を分ける (§0.5、R-11)
- 依頼者指摘「人は control credential をテストアプリに渡す。悪意ある者に渡ることもある」を受けて R-11 を新設: 可逆性の全数・監査の不可消去・持続化不能の明文化、playbook / sandbox 規則 / `ops.py audit-report` の WP-6 組み込み、契約 additive 候補2件 (audit role 読み取り、発行凍結)、複数本運用の不採用
- disable された唯一の control credential の復活手段として CLI break-glass に enable / rotate を追加 (R-10)。revoke の復活は意図的に作らない (reset が正準)
- v1.3: 抑止宣言を採用 (R-11、§2)。API に意図の判定器は置けない (正規と悪意の要求は構文上同一) — 代わりに、拒否応答へ「徒労」(in-band の control credential 作成経路は存在しない) と「帰属」(耐久記録・不可消去) の**真実の宣言**を載せ、要求を組み立てる利用者側 AI エージェントの安全学習に読ませる。期待効果は依頼者が「エージェントが警告・注意を出せば十分 (慎重化 + 面倒くさそうの醸成)」と確定。虚偽の宣言は禁止、安全はこの層に依存しない

## 10. WP-1 実装記録 (2026-08-29、v1.4)

WP-1 (port v1.5 + C-14/C-15 テスト実装 + 3 adapter surface-absent 分岐) を実装した。実装: Sonnet、独立レビュー: Opus (blocker 2 / major 7 / minor 7 / nit 2)、全指摘反映済み。suite は 544 → 575 passed (C-14/C-15 各5条件 × 3 adapter = 30 + traceability 検査1)。詳細な実装・変異記録は `docs/design/CONFORMANCE_ADAPTER_V1.md` §15。

### 10.1 レビューが捕捉した主要欠陥 (全て provided 分岐 = WP-5 で初めて走るコードに集中)

- **B-1**: C-14 ベクタ5の `LIMIT_EXCEEDED` は資源クラスを判別できず、契約 example_profile の値では applications 駆動が必ず rate limiter に先に当たる — rate limiter だけ実装した peer がベクタ5全体を空洞的に緑にできた。→ 位置算術で修正 (10.2-b)
- **B-2**: applications 上限の駆動が session-scoped adapter の registry を回復不能に飽和させ、以後の全テストを汚染 (契約に削除経路が無い)。→ 特権 setup op `deprovision_application` の新設で修正 (10.2-a)
- **major**: C-15 ベクタ1のテスト順序依存 / list 応答の鍵名が契約と乖離 (`credential_ref`→`credential_id`) / C-14 ベクタ4が R-4 の「登録済み・未 provisioning」を勘定せず data-plane authenticate を要求 / `control_credential()` の有効性義務未記載 / ベクタ2の縮約が無根拠 / C-15 ベクタ2の監査不変検査が文書の主張に対し未実装 / MitateDB の証拠 surface からの `open_session` 丸ごと除外が将来の回帰穴
- **レビュア誤り 1件** (記録する慣例): B-1 の修正案として「契約の problem+json は既に `details.resource` を持つ」と提示されたが、実測で契約 `errors.shape` の `details` は自由形 object でありそのようなキーは存在しない。監督が一次ソースで裏取りして不採用にし、契約語彙を発明しない位置算術を採った

### 10.2 監督決定 (いずれも覆せる。契約変更なし)

- (a) **port v1.5 の具体形**: 設計 §4 の op 列に加え、特権 setup/観測 op として `control_credential()` (儀式完遂済み handle の用意)・`control_audit_events()` (監査観測)・`deprovision_application()` (登録の後始末 — 運用者特権経路の逆操作であり公開 API 能力では決してない) を追加。計14 abstract method。in-band op は毎呼び出し `actor` handle を取る (事前フィルタ禁止 — application credential を渡した fail-closed 実測が C-14 ベクタ1)。control credential は `ControlCredentialHandle` 別型 (application に属さない、R-2 整合)。list 系は契約 envelope を剥がし行の鍵は契約のまま返す
- (b) **ベクタ5は位置算術で資源クラスを帰属**: 宣言 bound ちょうどまで成功→次の1件で `LIMIT_EXCEEDED`。早すぎる拒否は「クラスを帰属できない」として赤。conformance build 要件: applications/credentials bound ≤ 200、`control_requests_per_minute` > 両駆動の最悪要求数 + 64。rate クラスは恒久 bound が及ばない `control_capabilities` の burst で帰属し、窓 rollover (≤61s、provided 分岐のみ) 後の回復で過渡性 = rate クラスであることを証明
- (c) **ベクタ4の実効性判定は control-plane レベル**: in-band 登録の効果は list 出現 + credential 発行成功まで。data-plane authenticate は要求しない (R-4: 登録済み・未 provisioning の credential は serving されるまでデータ面に到達しない — これは正しい fail-closed であり登録の欠陥ではない)
- (d) **ベクタ2は authenticate 一点に縮約** (根拠明文化): 両 peer とも認証が全 data/schema endpoint の単一の門であるため endpoint 列挙と等価。認証を経ずに data endpoint へ到達できる peer が現れたら拡張が要る
- (e) **C-15 ベクタ5の port 表現可能形**: 固定・空・ありがち秘密の不通 + 儀式2回の発行秘密の相違。「独立に bootstrap した2環境」の完全形は実装側テスト/review evidence
- (f) **exemption 機構** (レビュー M-7 の採用形): `SurfaceAbsent.exempt_parameters` を新設し、テストは violations と宣言 exemption の**厳密一致** + 証拠 surface ⊇ `public_operation_callables()` を要求。MitateDB は全 surface + `open_session.credential_id` の1件 exemption (application 認証入口であり control 要求を運べない)。宣言の弱化・水増し・surface 削りの3変異が全て赤になることを実測
- (g) **form (b) (declared-unavailable) の真正性検査は延期**: 捏造 `CAPABILITY_UNSUPPORTED` が port レベルで検出不能なことを変異 (M5/M9) で実測し、受理境界として明記。正の存在確認 op (`control_inband_surface()`) は form-(b) peer の初登録時に導入する
- (h) **traceability の逆向き検査**: `test_conditions_register.py` に「marker を持つ条件は executable status を持つ」第3検査を追加 (変異 M6 が露出した片方向性の是正。逆向き C-12 と同じ発想)
- (i) C-14 の CONDITIONS 行への SI-08 追加は本 WP で実施 (§4 の記載どおり)。audit sink 故障注入 fail-closed は WP-2/WP-3 の実装側テストスコープ
- (j) C-15 ベクタ3は rotation-forcing 実現形で記述 (契約は機構自由 — TTL を選ぶ将来 peer には時刻注入の port 拡張が要る旨をテスト docstring に明記)

### 10.3 変異注入 (検出力の実測)

9変異中7が期待どおり赤: 実在パラメータの surface 混入 / 絶無主張なき成功 / 申告偽装 (enabled) / fragment 弱化 / exemption 水増し / surface 削り / CONDITIONS status 格下げ。緑のまま = 受理境界 2 (M5/M9、10.2-g で意図的に受理)。生存変異が実在のテスト欠落を示した例は無し (M6 は同一セッション内で是正済み)。

### 10.4 WP-5 への申し送り

- provided 分岐 (C-14/C-15 の enabled 側) は静的レビューのみで未実行。WP-5 の完了条件に「provided 分岐 green + 変異による検出力確認」が含まれる (§5 のとおり)
- ベクタ5の rate 回復チェックは最大 61 秒を要する (CI タイムアウトに注意)。applications 駆動の precondition (`既存数 < bound`) は fixture 消費と bound 設定の関係に依存 — conformance build の bound は suite 自身の登録消費より十分大きく取ること
- `deprovision_application` の実実装 (r2db 2 adapter) は WP-5 で行う (現在は3 adapter とも SurfaceAbsent)

## 11. WP-2 実装記録 (2026-08-29、v1.5)

WP-2 (0006 migration + unit-of-work + ControlCredentialStore ペア + 儀式 CLI + `main.py` 突合強化) を実装した。実装: Sonnet、独立レビュー: Opus (blocker 2 / major 5 / minor 9 / nit 2)、全指摘反映済み。suite は 575 → 619 passed (新規 `r2db-api/tests/test_control_plane_store.py` 43 test 他)。C-13 は work 必須化後も明示再実行で green。詳細な実装・変異記録は実装報告 (セッション記録) と 0006 自身のコメント。

### 11.1 レビューが捕捉した主要欠陥 (blocker は改訂 provisioning 関数に集中)

- **BL-1**: `begin_provision_application` が CREATE DATABASE より前に provisioning 列を UPDATE で確定させ、途中クラッシュで「存在しない DB を provisioning 済みと主張し、0003 再実行も拒否される」回復不能状態を作った (実測)。設計 v1.1 R-4 の文言「begin が UPDATE」自体が 0002/0003 の元の crash-safety 構造 (registry への書込みは finish 側) を見誤っていた — **設計の誤りとして訂正** (11.2-a)
- **BL-2**: `finish_provision_application` の `ON CONFLICT DO NOTHING` が真の競合 (begin と finish の間に登録が割り込む形) を無音で握り潰す (実測: 登録済み行に対し finish が黙って no-op)
- **MA-3 (TOCTOU)**: bootstrap の存在検査が発行トランザクションの外にあり、並行 bootstrap 2本が両方成功し得た (実測)
- **MA-5**: 実装者が採った「work 省略時は自動管理」の緩和は、既定 pool サイズでは無音でトランザクションが割れ、pool_size=1 では枯渇でハングする fail-open であることをレビューが実測 — §7 の「型で強制」の必要性が実証された

### 11.2 監督決定 (いずれも覆せる。契約変更なし)

- (a) **R-4 の関数分割の訂正** (設計自身の訂正): `begin_provision_application` は検証 + already-provisioned ガード (登録済みのみの行は通す) + CREATE ROLE のみで registry に**何も書かない**。provisioning 列の確定は `finish_provision_application` が 0003 の最後に行う (登録済み行への UPDATE → IF NOT FOUND なら INSERT の明示2分岐、ON CONFLICT 禁止 — provisioning 済み行はどちらの分岐にも合致せず PK 違反で音を立てる)。「registry が provisioning 済みを主張するのは実体が完成した後だけ」という 0002 本来の性質が両フロー (運用者先行 / 登録先行) で保存される。begin が作った role のクラッシュ残留は 0002 時代と同一の既存の運用上の疵であり、WP-6 の runbook 記載事項
- (b) **work は厳密必須** (keyword-only、省略は TypeError)。既存呼び出し元は conformance adapter (特権呼び出し箇所) と test_http.py を含め全て追随 (B-2 の「既存呼び出し元を追随させる」の適用範囲を正しく広げた。WP-2 初回のスコープ制約が緩和逸脱を誘発した — 発注側の教訓)。C-13 の再活性化ベクタが FoundationError 形の拒否を保ったことを条件テストの明示再実行で確認
- (c) **儀式の直列化**: bootstrap/reset は同一トランザクション内で `pg_advisory_xact_lock` (定数キー、ops.py に一元定義) を取得してから存在検査・発行を行う。lock 除去変異 (M9) は黒箱テストでは検出不能であることを実測し、受理境界として記録 (機構レベルの決定的2コネクション干渉テストで lock が防ぐ競合そのものは固定済み。本番コードへのテスト用計装は入れない — 監督支持)
- (d) **CLI 監査は成功のみ** (`outcome="allow"`): 拒否イベントの耐久記録は WP-3 の HTTP 制御面の責務 (R-6/B-3)。CLI の失敗は stderr で運用者可視 — 意図的境界として ops.py に明記
- (e) application credential の rotate は既存 Postgres 意味論 (revoked 不検査) を in-memory にもそのまま写し、control credential の rotate は revoked を `VALIDATION_FAILED` で拒否する別意味論 — 両者をテストで対で固定し、混同を防ぐ (§8 M-2 の読みどおり)
- (f) GRANT 検証はカタログ実測 (`has_function_privilege` 等) まで行い、R-2 の中心主張 (`r2dbsvc_api` は control 保存物を読めない) と「controlplane は control_audit を書けるが読み返せない」をテストで固定

### 11.3 WP-3 以降への申し送り

- `ControlPlaneService` は store の work 必須 surface を前提に、状態変更 + 監査 INSERT を単一 `unit_of_work()` で構成する (拒否イベントの耐久記録もここで初めて実装される — 11.2-d)
- `PostgresControlCredentialStore.has_any(include_revoked=False)` は現在未使用 (対称性のため存置)
- advisory lock キーの一元管理場所は未整備 (現在 ops.py の1定数のみ)。制御面 HTTP プロセスが儀式と競合する書込みを持つ場合は同じ直列化の要否を WP-3 で判断

## 12. WP-3 実装記録 (2026-08-29、v1.6)

WP-3 (`ControlPlaneService` — §2 の操作カタログ + must_rotate ゲート + R-7 limits + R-6 同一トランザクション監査/拒否耐久記録 + R-11 抑止宣言) を実装した。実装: Sonnet、独立レビュー: Opus (major 3 / minor 11 / nit 3、blocker 0)、全指摘反映済み。suite は 619 → 672 passed (新規 `r2db-api/tests/test_control_plane_service.py` 53 test、in-memory/Postgres 両 backend パラメトライズ。Postgres 側は `r2dbsvc_controlplane` 相当 DSN で実配線し 0006 GRANT 境界内で全操作が動くことを検証)。変異注入 9 本 (再照準 M3、虚偽宣言 M9 含む) 全て赤→復元→green。conformance / `test_postgres.py` は不変。

### 12.1 アーキテクチャの具体化 (§3 の監督裁定)

実配備の制御面プロセスには DataService が存在しないため、§3 の「ControlAuthority 委譲」を **backend ペア**として具体化した: `ControlPlaneService` (共有意味論 — 処理順序・認証・ゲート・limits・監査・宣言) の下に `InMemoryControlBackend` (重複操作は必ず ControlAuthority 経由 = 意味論一本化、in-process adapter/既存テスト互換) と `PostgresControlBackend` (WP-2 ストア群 + 新設 `PostgresApplicationRegistry`、DataService 不使用)。拒否とゲートの所在は service 層のみ (B-1 再発形なし — レビュー確認済み)。

### 12.2 レビューが捕捉した主要欠陥と監督決定 (いずれも覆せる)

- **MA-1 (実装者判断の却下)**: AUTH_REQUIRED (資格情報の不提示) を監査対象外にした初回判断を却下し、監査対象に追加。契約 `audit.emission` は authentication denial を筆頭に挙げ、最も安価な probe (ヘッダ無し) が耐久痕跡ゼロになる非対称は R-11 の検知信号を無効化する。なお **AUTH_STATE_UNAVAILABLE は監査対象外を承認** (sink が同一 DB のため不達時は必ず二重 503 連鎖になる。応答自体は既に fail-closed) — **WP-6 で CONTROL_MAPPING SI-14 行に rate limit の線引きと並べて明記すること** (条件付き承認)
- **MA-2 (抑止宣言の2分割)**: 認証拒否の監査行が無帰属 (actor 不明) なのに応答が「実行 credential に帰属」と宣言する虚偽をレビューが実測。宣言を `_RECORDED_DECLARATION` (帰属を主張しない耐久記録宣言) と `_ATTRIBUTED_DECLARATION` に分割し、帰属宣言は監査行に actor_id が実在するときのみ。AUTH_REVOKED / disabled 拒否では store が特定済みの credential_id を **problem+json に決して届かない内部経路** (FoundationError の非 details 属性) で監査行にのみ帰属させる — R-11 playbook (侵害窓の差分列挙) が認証拒否側でも機能する。details 経由の存在区別漏れ (R-8/§8 m-7) は構造的に不可能な形
- **MA-3**: 同一トランザクション監査の故障注入が 3 つの uow 系 (applications/credentials/control_credentials) のうち 1 つしか固定していなかった → 全系パラメトライズ + 変異 M3 の再照準で赤を実測
- **監査 `role` の統一 (MI-6)**: audit event の `role` は**実行者のロール** (制御面 service 操作は常に "control"、CLI は None)。対象 credential のロールを書いていた issue_credential の実バグを是正。**対象識別子 (target_id) は契約 `audit.fields` に存在しない語彙ギャップ** — R-11 playbook の「窓中に発行/失効された credential の列挙」は現行 12 項目では実行不能。契約 additive 候補として §6 台帳に積む (下記 12.4)
- **rate window は sliding で存置 (MI-7)**: 設計 R-7 の「固定窓で足りる」より厳格側 (メモリ有界) のため実装を承認し、乖離をコードコメントに記録
- **その他**: in-memory の ControlAuthority 副次監査も rollback に参加 (「起きなかった allow」を残さない)、`control_plane.py` の psycopg 非依存 import (TYPE_CHECKING 化 + subprocess 回帰テスト)、503 文言の原因中立化、`events()` の 503 規律統一、負経路/形状/許可リスト網羅テストの追補

### 12.3 変異注入 (検出力の実測)

9 本全て赤: 拒否リスト化 (列挙漏れ) / role=control 拒否の後置 / 監査 INSERT の uow 外出し (credentials 系に再照準) / 拒否監査失敗の握り潰し / rate 判定の後置 / 失効 credential のカウント混入 / rate 拒否への虚偽 audited 付与 / must_rotate の list 露出 / 無帰属拒否への帰属宣言付与 (虚偽)。生存変異なし。

### 12.4 台帳追加 (契約 additive 候補、§6 に接続)

- **audit.fields への対象識別子 (target_id) の追加** (12.2 MI-6/MI-11): credential lifecycle イベントが対象 credential を識別できず、R-11 playbook の窓中差分列挙が audit 行だけでは完結しない。`ops.py` の既存イベントも同一のギャップ (WP-3 の退行ではない)

### 12.5 WP-4/WP-5 への申し送り (レビューの予見を含む)

- WP-4 (HTTP 層): `ControlPlaneService` の9メソッドは secret/引数 → 契約 schema dict / FoundationError の形でそのまま呼べる。HTTP 層は `details` を problem+json へ転写するだけ (抑止宣言は service 層で確定済み — 意味論を bind 層に持ち込まない)。`R2DB_CONTROL_LIMIT_*` の env 読み出しは composition root の仕事
- WP-5 (conformance provided 化): (i) 既定 limits profile (100/10/60) では C-14 ベクタ5 の headroom 前提 (`rate > apps駆動 + creds駆動 + 64`) を満たさない — conformance build は例えば (20, 5, 200) を注入する。(ii) rate window はグローバルなので session-scoped adapter では他テストと窓を共有する — profile の rate を十分大きく取るか service を再構築する。(iii) port `deprovision_application` は service に対応物を作らない (controlplane role に DELETE が無い) — adapter は運用者特権経路 (in-process: DataService 内部状態 / Postgres: control DSN + `finish_deprovision_application`) で実装。(iv) port `control_audit_events()` は**耐久 sink** を読む (in-memory ControlAuthority の副次トレイルを代用しない。Postgres は control_audit に SELECT を持つ `r2dbsvc_control` 相当 DSN の別インスタンスが要る)。(v) capability document のキー形状は C-14 ベクタ5 の読み方と一致済み (無改修で通る見込み)

## 13. WP-4 実装記録 (2026-08-29、v1.7)

WP-4 (`control_http.py` の `create_control_app` + `control_main.py` composition root (factory のみ、module-level app なし) + AuthorityTopology の制御面 HTTP ノード拡張) を実装した。実装: Sonnet、独立レビュー: Opus (major 2 / minor 6 / nit 2、blocker 0)、全指摘反映済み。suite は 672 → 704 passed。`test_topology.py` の既存アサーションは byte-identical のまま (§8 m-8 完了条件)、conformance / `test_postgres.py` 不変。11 endpoint の method/path/schema 対応は契約と行単位で突合済み (レビュー実測)。単一コミット規則は保存 (module-level app 不在をテストで機械検査、`control_plane` 申告は unavailable のまま)。

### 13.1 レビューが捕捉した主要欠陥と監督決定 (いずれも覆せる)

- **MAJOR-1 (rate 前課金)**: body を持つ 3 endpoint で shape 検証が rate 判定より先に走り、未認証の malformed-body フラッドが `limit_enforcement: "enforced"` 宣言下で無制限だった (レビュー実測)。→ `ControlPlaneService.check_rate()` (公開) + 全9メソッドに keyword-only `rate_precharged: bool = False` を追加し、HTTP handler は Bearer 抽出・body 読取より前に課金してから `rate_precharged=True` で呼ぶ。1リクエスト=1トークンを両経路 (HTTP / in-process 直呼び) で保証し、二重課金なしを bound 位置で検証。byte-bound 413 が窓より前に立つのは middleware 構造上の data 面 parity として受理 (コメント記録)。この修正の過程で、既存 stub テスト2本が `check_rate` 欠如の偶発 `AttributeError`→503 で「主張と別の理由で通っていた」実バグも是正された
- **MAJOR-2 (topology の虚偽辺)**: `control_plane_http → audit` を不到達と宣言していたが、0006 の `GRANT INSERT ON control_audit TO r2dbsvc_controlplane` と R-6 の耐久書込み義務に矛盾 (CONTROL_MAPPING が SI-00/SI-02 evidence に引くテストが虚偽を主張する形)。→ 到達可 (append-only、INSERT のみ) に訂正し topology/yaml/テストを一致させた。宣言=実挙動 (R-11) は evidence artifact 自身にも適用される
- **応答 shape 検証の緩和 (MINOR-3)**: 契約の response schema は `additionalProperties: false` を宣言しない (additive 変更許容) ため、未知キー拒否は宣言のある schema に限定し、それ以外は必須キー検査のみ。malformed 応答は 400 でなく 503 (原因中立文言 — WP-3 MI-9 と整合)
- **逸脱3件は全て承認**: (a) `ALL_PLANES` 第2タプル (PLANES 厳密一致テストとの衝突回避 — WP-5 で PLANES へ統合する)、(b) `control_main` での `R2DB_CREDENTIAL_PEPPER` 必須化 (省略可にすると `validate_control_pepper_separation` が no-op になり R-2 の同値検査を運用者がスキップできてしまう — 必須化が分離を強める)、(c) `WWW-Authenticate` 不採用 (data 面 http.py 自身が出していない実態への一致。両面同時の decision として WP-6 へ)
- `can_reach` の deny ブロック群は default-deny の allow-list に対する文書であり執行辺ではない (全削除しても挙動不変とレビューが実測) — その旨をコード注記

### 13.2 変異注入

9 本全て赤 (認証判定の HTTP 層持ち込み / 宣言転写落とし / 応答検証外し / 例外メッセージ漏洩 / topology 新規則反転 / module-level app 設置 / route 削除 / 前課金落とし / rate_precharged 既定反転)。M4/M5 は初回の変異部位が赤くならず、再配置の過程で「per-handler catch-all が実際の SI-10 境界」「deny ブロックは冗長」という構造事実を露出した (報告書に記録)。

### 13.3 WP-5 への申し送り (§12.5 に追加。レビュー実測の予見を含む)

- **C-15 の `_FAIL_CLOSED_CODES` に `AUTH_REQUIRED` が要る**: 空 secret の probe は両面・両 adapter とも `AUTH_REQUIRED` を返す (実測)。conformance 側の集合 {AUTH_INVALID, AUTH_REVOKED, FORBIDDEN} のままでは provided 分岐が赤になる — §8 m-7 (単一コードに固定しない) と整合的に広げる
- adapter は `{"applications": [...]}` / `{"credentials": [...]}` の envelope を剥がす (port v1.5 の docstring どおり)。405 は data 面 parity で code NOT_FOUND を運ぶ — `classify()` の対応を確認
- `test_control_main_module_has_no_module_level_app` は WP-5 の単一コミットで反転させる (flip チェックリストに載せる)
- `control_plane_http` を `PLANES` に統合し厳密一致アサーションを更新 (m-8 の凍結は WP-4 で終了)
- **`request_bytes` の宣言ギャップ**: 制御面は byte bound を enforce するが control discovery が当該クラスを公開しない — WP-5/WP-6 で declaration を判断 (契約 `limits.classes` に `request_bytes` は存在する)
- conformance build の limits profile 例 (20, 5, 200) は headroom 算術を満たすことをレビューが確認済み。`R2DB_CONTROL_LIMIT_*` の3変数で注入可能 (コード変更不要)
