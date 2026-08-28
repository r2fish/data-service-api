# r2db-api credential 永続化・composition root・並行配備 設計 v1

- 起票日: 2026-08-28
- 設計: Fable (監督・設計担当)
- 実装: Sonnet subagent、レビュー: Opus
- 対象: `docs/work-orders/HANDOVER_20260828.md` §5 の既知欠落のうち「credential が永続化されない」「composition root が無い」、および §2.5 の配備方針 (段階1: 8443 並行稼働) の成果物
- 前提文書: `docs/design/R2DB_SERVICE_LAYER_ARCHITECTURE.md` (D-1〜D-7、§5.3 C-1〜C-5、§8)、`spec/CCR_DISPOSITION.md`

## 0. 契約判断からの独立という制約

`spec/CCR_DISPOSITION.md` が定める通り、CCR-14 (制御プレーン) は**採否未決**であり、本作業は契約変更を先取りしてはならない。本設計は次で独立性を保つ。

- **HTTP の制御面は一切作らない。** 制御操作 (credential の issue / rotate / revoke / disable / enable、application の disable / enable) は帯域外の CLI のみとし、CLI には「CCR-14 採否までの暫定手段」であることを明記する
- **credential 記録の形は、現に動いている in-memory `CredentialRecord` の形をそのまま写す** (id / application / role / verifier / enabled / revoked + 監査用 timestamp)。新しいライフサイクル状態 (期限、pending、rotation lineage 等) を発明しない
- **control credential の型を作らない。** `role` は `runtime` / `developer` のみ (DB の CHECK 制約も同様)。control credential の記録形は CCR-14 の採否 (特に in-band 発行の案A/案B) に依存するため、採用後に additive migration で追加する

いずれも「ゲートを作らない」の適用である: 将来 CCR-14 がどの形で採用されても、本作業の成果物は追記だけで追随できる。

## 1. 決定

### P2-D1 保存場所 — platform DB の registry schema、保存するのは verifier のみ

`r2dbsvc_platform` の `r2dbsvc_registry` schema に `credentials` テーブルを追加する (migration `0005_credential_store.sql`)。

```sql
ALTER TABLE r2dbsvc_registry.applications
    ADD COLUMN IF NOT EXISTS enabled boolean NOT NULL DEFAULT true;

CREATE TABLE IF NOT EXISTS r2dbsvc_registry.credentials (
    credential_id    text PRIMARY KEY,
    application_slug text NOT NULL
        REFERENCES r2dbsvc_registry.applications(application_slug) ON DELETE RESTRICT,
    role             text NOT NULL CHECK (role IN ('runtime', 'developer')),
    verifier         text NOT NULL UNIQUE,
    enabled          boolean NOT NULL DEFAULT true,
    revoked          boolean NOT NULL DEFAULT false,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now()
);
```

- 保存するのは HMAC-SHA256(pepper, secret) の **verifier のみ**。秘密そのものは発行時に一度だけ表示され、どこにも保存されない。旧 VPS 実装の教訓3 (制御 DB に平文 credential を同居させない) をここで守る
- pepper (`R2DB_CREDENTIAL_PEPPER`) は従来どおり環境変数供給。pepper を変えると全 verifier が無効になる (再発行が必要)。これは既知の性質として runbook に記す
- `ON DELETE RESTRICT`: 旧実装の `ondelete=CASCADE` が監査の連結を切った教訓 (CCR-14 教訓欄)。application 行は削除ではなく `enabled=false` が終端
- `verifier UNIQUE`: 認証は verifier 等値検索で行うため、二重一致を構造的に排除する

### P2-D2 application の enabled 状態も永続化する

理由: credential だけ永続化して application の disable 状態を in-memory のまま残すと、**CLI で無効化した application が再起動で黙って有効に戻る** (fail-open)。安全第一の軸から、これは credential 永続化と同時に閉じる。`applications.enabled` は in-memory の `_disabled_apps` と同じ意味論であり、新しい状態ではない。

### P2-D3 API プロセスのロールは読み取り専用の新設 `r2dbsvc_api`

- `r2dbsvc_api`: `LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT CONNECTION LIMIT 10`。`r2dbsvc_platform` への CONNECT、`r2dbsvc_registry` の USAGE、`applications` / `credentials` への **SELECT のみ**
- API プロセスは `r2dbsvc_control` (CREATEROLE/CREATEDB 保持) では決して接続しない — §5.3 C-2 の維持
- 書き込み (issue / rotate / revoke / disable / enable) は CLI が `r2dbsvc_control` の DSN で行う。API プロセスの侵害が credential 記録の改竄に届かないことが SI-02 / least privilege の実体

### P2-D4 認証はリクエストごとに DB を参照する (伝播 bound 0 の維持)

`PostgresCredentialStore` (新規、`auth.py` の `CredentialStore` と同一の呼び出し面) は `authenticate` / `assert_active` のたびに platform DB を参照する。

- 検索は「pepper で verifier を計算 → verifier 等値で 1 行取得」。in-memory 版の全件走査と異なり index 検索になるが、verifier は pepper なしに計算できないため、この形で危険は生じない。取得後の最終比較は従来どおり `hmac.compare_digest`
- `applications.enabled` を JOIN で同時に取得し、無効 application は `APPLICATION_DISABLED` (403)
- **fail-closed**: platform DB へ到達できない場合は `AUTH_STATE_UNAVAILABLE` (503)。`AUTH_INVALID` (401) に化けさせてはならない (未検証を「無効」と申告しない)
- capabilities が公開する `authorization_propagation_bound_ms: 0` の根拠は「毎操作で状態を再検証しキャッシュが無い」ことだった。DB 参照版でも同じ構造 (キャッシュ無し、commit された状態変更は次のリクエストから即時有効) なので 0 の申告は維持される。**キャッシュを入れる場合は bound の申告値を変えなければならない** — 本版ではキャッシュを入れない
- platform DB への接続は store 専用の小さなプール (既定 maxconn 4、`R2DB_PLATFORM_POOL_SIZE` で調整)。`SharedPoolManager` の application キー空間 (`[a-z][a-z0-9_]{0,32}`) と衝突しないよう、共有 manager には載せず store が自前で 1 プール持つ。§8.7 の上限算術には「+ platform プール分 (固定値)」として runbook に追記する

### P2-D5 composition root — `r2db_api/main.py` がモジュールレベル `app` を公開する

uvicorn / systemd から `r2db_api.main:app` で起動できるようにする。環境変数契約:

| 変数 | 必須 | 意味 |
|---|---|---|
| `R2DB_CREDENTIAL_PEPPER` | 必須 | 既存。verifier 計算の pepper |
| `R2DB_PLATFORM_DSN` | 必須 | `r2dbsvc_api` ロールで `r2dbsvc_platform` へ接続する DSN |
| `R2DB_SERVE_APPS` | 必須 | この process が提供する application slug のカンマ区切りリスト |
| `R2DB_APP_<SLUG大文字>_RUNTIME_DSN` | slug ごとに必須 | 当該 application の runtime ロール DSN |
| `R2DB_APP_<SLUG大文字>_DEVELOPER_DSN` | slug ごとに必須 | 当該 application の developer ロール DSN |
| `R2DB_POOL_*` | 任意 | 既存のプール調整 |
| `R2DB_PLATFORM_POOL_SIZE` | 任意 | P2-D4 の platform プール上限 |
| `R2DB_PLATFORM_SCHEMA` | 任意 (テスト専用) | registry schema 名の差し替え。テストが使い捨て prefix の registry を指すためにのみ使い、本番では設定しない (既定 `r2dbsvc_registry`) |

- 提供する application は**構成で宣言する** (静的制御プレーン)。これは CCR-14 が正当な配備形態として明記した形であり、採否を先取りしない
- 起動時に `R2DB_SERVE_APPS` の各 slug を registry (`applications`) と突き合わせ、**未登録・無効・DSN 欠落は起動失敗** (うるさく落ちる。黙って一部だけで起動しない)。role 名 (`PostgresCell` の RLS policy 埋め込みに必要) は registry の行から取る
- DSN の**パスワードの有無は configuration の性質であって code の性質ではない**。password 入り DSN (posture A) でも peer 認証前提の password なし DSN (posture B、§3) でも、code は同一に動く。これが「DB ロールパスワードの保持者」問題を code の決定から切り離す方法である
- 必須変数の欠落は import 時に例外で落とす。process manager から見て「起動失敗」が唯一の失敗様式
- shutdown で `default_pool_manager.dispose_all()` と platform プールの close を行う (ASGI lifespan)

### P2-D6 暫定 CLI — `python -m r2db_api.ops`

CCR-14 採否までの帯域外管理手段。**モジュール docstring・`--help`・runbook のすべてに「暫定 (CCR-14 採否待ち)」を明記する。**

- 接続: `R2DB_CONTROL_DSN` (`r2dbsvc_control` ロール)。pepper も必要 (`R2DB_CREDENTIAL_PEPPER`)
- サブコマンド: `issue-credential <slug> <runtime|developer>` (id と secret を生成、secret は一度だけ標準出力へ)、`rotate-credential <id>`、`revoke-credential <id>`、`disable-credential <id>` / `enable-credential <id>`、`list-credentials` (verifier / secret は出さない)、`disable-app <slug>` / `enable-app <slug>`、`list-apps`
- secret は `secrets.token_urlsafe(32)`、credential_id は `crd_` + 16 hex
- rotate は「同一 credential_id の verifier を差し替える」— `lifecycle.credential` が既に採用している動詞の範囲内であり、新しい意味論を作らない
- **既知の制約 (明記する)**: 耐久 audit sink が未実装 (§7 既存残作業) のため、CLI の制御操作はまだ正準の永続 audit イベントを残せない。`audit.sink_failure_policy` が control-plane 変更を fail-closed とする以上、これは audit sink 実装までの明示的なギャップとして記録する

### P2-D7 conformance HTTP adapter を DB-backed store に切り替える

`conformance_adapter_r2db_http.py` は 0005 も適用し、`PostgresCredentialStore` で `DataService` を組む。C-01 / C-03 / C-08 が「HTTP + PostgreSQL + 永続 credential」の実スタックに対して走ることになる。adapter が in-memory store のままでは、C-08 (revocation) が実際の認証経路を検証しない (adapter が peer の不足を埋めてはならない、の逆向きの適用)。

### P3-D8 並行配備 (段階1: 8443) の成果物

`r2db-api/deploy/` に置く。**すべて合成値** (`example.invalid`、プレースホルダ) で書く。実ホスト名・実 port・実パスは運用者が配備時に差し替える。

- `deploy/systemd/r2dbsvc-api.service` — 専用非 root ユーザ、`EnvironmentFile=`、`ExecStart=<venv>/bin/uvicorn r2db_api.main:app --host 127.0.0.1 --port <内部port>`、hardening (`NoNewPrivileges` / `ProtectSystem=strict` / `ProtectHome` / `PrivateTmp` ほか)
- `deploy/env/api.env.example` — **全項目を明示** (環境からの継承に頼らない、handover §2.5)。値は合成
- `deploy/nginx/r2dbsvc-api-8443.conf.example` — 既存と同じ `server_name` で `listen 8443 ssl` の別 server block。`location /v1/` のみを loopback の uvicorn へ proxy (制御面の location は存在しない)。`client_max_body_size` は application の `request_bytes` bound より僅かに大きく取り、413 の判定主体が application 側 (決定的な problem+json) になるようにする
- `deploy/DEPLOYMENT_RUNBOOK.md` — 段階1 (8443 並行稼働) の手順、検証 (credential なしの `GET /v1/capabilities` が 401 problem+json を返すことが疎通確認になる)、段階2 (443 path 振り分け) の計画と前提 (パス非衝突の確認済み事項)、rollback (8443 を閉じるだけ)、内部 port が既存実装と衝突しないことの確認手順

## 2. 明示的に scope 外

- 耐久 audit sink (§7 既存残作業のまま)
- `ResourceLimits` の環境変数化
- 型付き列・主キー・`order_by`・pagination 等の契約未実装項目 (handover §5)
- VPS 実機への適用 (成果物はファイル一式と runbook まで。実行は運用者)

## 3. 未決事項 (依頼者判断) — DB 認証の posture

per-application DSN のパスワードの保持者問題 (handover §5「DB ロールパスワードの保持者が未定」)。code は両方で同一に動く (P2-D5)。

- **posture A — password 入り DSN を EnvironmentFile に置く**: root 所有 0600 の EnvironmentFile が保護境界。単純で PostgreSQL 版数に依存しない。ただし秘密がファイルに存在し、application 追加のたびに秘密が増える
- **posture B — UNIX socket + peer 認証 (パスワード無し)**: OS ユーザ識別が credential になり、ファイル上の秘密が消える。`pg_hba.conf` の `local ... peer map=...` と `pg_ident.conf` の写像で、API の OS ユーザに `r2dbsvc_app_*` ロール群のみを許す (`r2dbsvc_control` は写像に含めない)。ただし写像の管理が増え、複数ロールへの正規表現写像は PostgreSQL 版数依存の機能差がある (VPS の実版数で要確認)

いずれも C-3 (PostgreSQL は loopback/socket のみ) の内側の話である。runbook は両 posture の設定例を載せ、採用は依頼者判断とする。

## 4. テスト要求 (実装 subagent への指示)

- `./.venv/bin/python -m pytest` 全緑を維持 (244 + 追加分)
- 永続性: store の別インスタンス (再起動相当) が発行済み credential で認証できる
- 伝播: 別接続 (CLI 相当) で revoke / disable / app-disable した変更が、稼働中 store の次の認証・`assert_active` で即時に拒否になる (bound 0 の実証)
- fail-closed: platform DB 到達不能で `AUTH_STATE_UNAVAILABLE` (503) になり、401 に化けない
- restart 越しの application disable 保持 (P2-D2 の fail-open 防止)
- 0005 の再実行が no-op (冪等)
- CLI: issue → 認証成功、rotate → 旧 secret 拒否・新 secret 成功、revoke → `AUTH_REVOKED`
- **変異注入で検出力を確認する**: (1) store が `revoked` を無視、(2) `applications.enabled` を無視、(3) DB 例外を 401 へ写す、の3変異それぞれで suite が落ちることを確認して復元する。復元は scratchpad へのバックアップからコピーで行い、`git checkout` は使わない (handover §7 誤り7)
- PostgreSQL 残骸ゼロ (`r2db(test|svc|http)` prefix の後始末3経路を既存 infra に倣う)。無関係な既存オブジェクトに触れない
