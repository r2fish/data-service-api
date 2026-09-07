# フェーズ4 成果の配備実機適用手順 (2026-09-03)

対象: `r2db-api` (VPS) と `MitateDB-api` (Cloud Run / Cloud SQL) の両 peer。
適用するもの: application-plane 耐久 audit sink (`application_audit`) +
`audit_query` + 契約 1.4.0 宣言 (`docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md`
v1.6、引き継ぎ `docs/work-orders/HANDOVER_20260903_FABLE.md`)。

**この手順書の位置付け。** フェーズ4 の成果は main にマージ済みだが、実配備には
まだ乗っていない。適用に必要な 5 項目 — migration 適用 / reader role DSN 配線 /
logs-based alert 結線 / platform DB 容量閾値 / 監査書込み timeout と宣言
`visibility_lag_ms` の連動 — は、いずれも両 peer の runbook に既に記述がある。
本書が足すのは記述ではなく**順序**である: 両 peer を跨いで、依存順どおりに、
適用後の検証まで一筆書きに実行するための運用者手順。

したがって本書はコマンドや算式を runbook から複製しない。**手順の各ステップは
runbook の該当節を指し、そこを正本として読むこと。**運用者がその場で打つコマンド
列だけは、往復を減らすために再掲する。runbook と本書が食い違って見えたら、
runbook が正しい。

正本 (本書が参照する側):

| peer | 正本 |
|---|---|
| r2db-api | `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` §15 (§15.1〜§15.5)、`r2db-api/deploy/DEPLOYMENT_RUNBOOK.md` §2 / §7 |
| MitateDB-api | `MitateDB-api/docs/cloud-run-cloud-sql.md` §0 / §0.1 / §3.2b〜§3.2f / §6 / §7 / §8 |
| 共通 | `spec/data-service-api.v1.json` (`versioning.version_binding` の 1.4.0 条項)、`security/CONTROL_MAPPING.md` |

公開リポジトリの文書である。以下に現れるホスト名・プロジェクト ID・ポート・
パスはすべて合成の例示 (`example.invalid` 等) であり、実値は配備先の
`EnvironmentFile` / Secret Manager にのみ置く。

---

## 0. 適用の前提と、この手順書が決めないこと

### 0.1 前提

1. 適用対象のコードは main (フェーズ4 完了時点) である。両 peer とも、
   **実配備に載っているのがフェーズ4 前のコードなら、まずそれを入れ替える** —
   migration を当てただけでは書き手は 1 行も INSERT しない (r2db =
   virtualenv への再インストール + 再起動、MitateDB = 1.4.0 コードから
   ビルドしたイメージでの再デプロイ)。
2. r2db は stage 1 (8443 並走) の運用者 runbook が整備済みで、
   control-plane 配備手順は `DEPLOYMENT_RUNBOOK.md` §7 にある。
   **control プロセスが未配備なら、本書 §2 に入る前に §7 を完了しておく** —
   `audit_query` は control ホストにしか存在しない。
3. MitateDB の初回実配備 (2026-09-01、`cloud-run-cloud-sql.md` §0.1) は
   data サービス (`mitatedb-data`) のみで、control サービス
   (`mitatedb-ctrl`) は配備されていない。**MitateDB で `audit_query` を
   提供するには `mitatedb-ctrl` の新規配備が必要**である (本書 §3(c))。
   §0.1 は逸脱の記録であって違反ではない — 本書 §3 はその記録を
   §0 の完全形へ寄せる作業でもある。
4. reader DSN を配線しない選択は、いつでも正当である。`R2DB_AUDIT_DSN` /
   `MITATEDB_AUDIT_DSN` を未設定のまま運用しても、耐久 sink は動き続け、
   証拠は溜まり続け、契約 1.4.0 にも完全に適合する (宣言が
   `unavailable` に据え置かれ、条件付き義務が拘束しないだけ。
   `versioning.version_binding`)。**本書 §2(b) / §3(c) を実施しない、という
   決定は失敗ではない。**

### 0.2 この手順書が決めないこと (運用者裁定値)

以下 4 つは配備固有の値であり、本書は決めない。**適用前に埋め、埋めた表を
本書と一緒に配備記録へ残すこと。**空欄のまま §2 / §3 に入らない。

| # | 裁定項目 | r2db-api | MitateDB-api | 根拠 / 参照 |
|---|---|---|---|---|
| A | 最大インスタンス数 **M** (容量算式に入れる値) | ` ` | ` ` | r2db: VPS では通常 1。MitateDB: `mitatedb-data` の `--max-instances` (`mitatedb-ctrl` は Invariant 1 により 1 固定だが、**M は data 側の値**)。§15.1 / §3.2d |
| B | platform DB 容量閾値の実数 (増加率のしきい値と観測間隔) | ` ` | ` ` | §15.1 / §3.2d の算式に A を代入して算出。絶対サイズではなく**増加率**に置く |
| C | 監査書込み timeout の配備値 (`*_AUDIT_STATEMENT_TIMEOUT_MS` / `*_AUDIT_IDLE_TIMEOUT_MS`) | ` ` / ` ` | ` ` / ` ` | 既定 5000/5000 → 宣言 `visibility_lag_ms` = 11000。**変えたら宣言が変わる** (§15 / §3.2b) |
| D | alert 結線先の基盤 (5 種の固定メッセージをどこで拾い、誰に鳴らすか) | ` ` | ` ` | §15.2 / §3.2d。r2db は journald ベース、MitateDB は Cloud Logging のログベース指標が自然だが、選択は運用者 |

C を既定から動かす場合は、**その peer の data プロセスと control プロセスの
両方に同じ値を入れる**こと (§2(c) / §3(d))。片側だけ変えると、宣言
`visibility_lag_ms` が嘘になる。この一致は機構的に強制されていない。

---

## 1. 共通: 適用前チェック

### 1.1 適用元の確認

1. main が フェーズ4 完了コミットを含むこと。基準は merge `1f391c5`
   (フェーズ4 引き継ぎ) 以降。
2. root suite を**単独実行**し、**1526 passed / 0 failed / 0 skipped /
   0 xfailed** を実測して配備記録に控える。並走実行は PG クラスタ衝突で
   偽の赤を出すため使わない (引き継ぎ §4 の運用規律)。
3. コミット identity の確認は本作業では不要 (本書は配備作業であって
   コミット作業ではない)。適用の過程で文書を更新してコミットする場合のみ、
   通常どおり `git log --format='%an <%ae>'` を確認する。

### 1.2 各 peer の実行 role と接続経路

| 作業 | r2db-api | MitateDB-api |
|---|---|---|
| migration 適用 | `r2dbsvc_control` (schema owner。`R2DBSVC_CONTROL_DSN`) | `mitatedbsvc_provision` (schema owner。Cloud SQL Auth Proxy 経由の `127.0.0.1:5432`) |
| 書き手 (application_audit へ INSERT) | `r2dbsvc_api` — data プロセスが既に持つ `R2DB_PLATFORM_DSN` をそのまま使う。**新しい DSN 変数は無い** | `mitatedbsvc_api` — 同じく `MITATEDB_PLATFORM_DSN` をそのまま使う |
| 書き手 (control_audit へ INSERT) | `r2dbsvc_controlplane` (`R2DB_CONTROLPLANE_DSN`) | `mitatedbsvc_controlplane` (`MITATEDB_CONTROLPLANE_DSN`) |
| 読み手 (`audit_query`) | `r2dbsvc_auditreader` (`R2DB_AUDIT_DSN`、control プロセスのみ、任意) | `mitatedbsvc_auditreader` (`MITATEDB_AUDIT_DSN`、control サービスのみ、任意) |
| 帯域外読み出し | `psql` を `r2dbsvc_auditreader` / schema owner で (§15.4) | `psql` を `mitatedbsvc_auditreader` / schema owner で (§3.2f) |

`application_audit` を**ネットワーク越しに読み戻せる role は reader だけ**で
あり、書き手 role には SELECT が無い。これは append-only を DB 権限で担保する
設計そのものなので、検証で「読めない」ことを確認する対象である (§4)。

### 1.3 edge policy の射程 (audit_query を有効化する前に必ず)

`audit_query` を有効化すると、control ホストは `/control/v1/*` の外側の
パス — `POST /v1/audit/query` (同一ハンドラの alias) — も応答する。
**`/control/v1/*` だけを管理網に限定している edge 規則は、この alias を
境界の外に取り残す。**制限は**ホスト (サービス) 単位**か、両プレフィックスに
対して表明すること。r2db は `POSTGRES_PROVISIONING_RUNBOOK.md` §15.5、
MitateDB は `cloud-run-cloud-sql.md` §0 が正本 (MitateDB は
`--no-allow-unauthenticated` + 運用者限定 invoker がサービス単位の制限に
なっているため、§6.2 の binding を維持していれば満たされる)。

data ホスト側の `/v1/audit/query` は**別の endpoint** であり、認証後に
`CAPABILITY_UNSUPPORTED` を返すまま変わらない。これを control アプリへ
ルーティングして「揃える」ことはしない (§15.5 の 3、§0 の同注)。

---

## 2. r2db-api (VPS) への適用

順序どおりに実行する。(a) → (e)。

### (a) migration `0007_application_audit.sql` の適用

正本: `POSTGRES_PROVISIONING_RUNBOOK.md` §15 冒頭、および migration
ファイル自身のヘッダ (逐条の根拠はそこにある)。

`0006` の後に、`r2dbsvc_control` として一度だけ:

```
psql "$R2DBSVC_CONTROL_DSN" -v auditreader_password="$R2DBSVC_AUDITREADER_PASSWORD" \
  -f r2db-api/migrations/0007_application_audit.sql
```

`R2DBSVC_AUDITREADER_PASSWORD` は**環境変数名**であり、値は他の
`psql -v ..._password` 変数と同じ手順で生成する (§5 の注)。値を本書にも
リポジトリにも書かない。

**冪等性**: `CREATE TABLE IF NOT EXISTS`、条件付き `CREATE ROLE ... \gexec`、
自然に冪等な `GRANT` で構成されており、**再実行して安全**である。適用が
途中で落ちた、適用済みか自信が無い、という場合は、状態を調べるより
**もう一度流す方が安全**。

ただし冪等性には一点、罠がある: reader role の作成は
`WHERE NOT EXISTS (... FROM pg_roles ...)` ガードの下にあるため、**role が
既に存在する再実行では `-v auditreader_password=` の値は反映されない** —
既存のパスワードがそのまま残る。パスワードを新しくしたい場合の扱いは
(b) を見ること。

適用後に足されるもの: `r2dbsvc_registry.application_audit` (`r2dbsvc_api` は
INSERT のみ)、および新 role `r2dbsvc_auditreader` (両 audit テーブルに
SELECT のみ)。

### (b) reader role パスワードの生成と `R2DB_AUDIT_DSN` の配線

**この節を飛ばす選択は正当である** (§0.1 の 4)。飛ばす場合、`audit_query` は
`unavailable` 宣言のまま、ルートは登録されたまま認証後
`CAPABILITY_UNSUPPORTED` を返す。

配線する場合:

1. reader のパスワードは、(a) を **role が存在しない状態から** 実行したので
   あれば `-v auditreader_password=` の値が入っている。その値から
   `r2dbsvc_auditreader` として `r2dbsvc_platform` へ接続する DSN を組み立て、
   **秘密管理側にのみ保管する**。

   **role が既に存在していた場合 ((a) の再実行を含む) は、パスワードは
   更新されていない。**新しいパスワードで DSN を組むなら、`r2dbsvc_control`
   接続から別途:
   ```
   \password r2dbsvc_auditreader
   ```
   `psql` の `\password` を使うこと — 対話的に入力し、平文を
   `ALTER ROLE ... PASSWORD '...'` の形でシェル履歴にもサーバログにも
   残さない。`ALTER ROLE` を直に打つ必要がある場合でも、**値をファイルにも
   履歴にも残さない**。

   これは peer 非対称である: MitateDB の `0005` は reader を
   `PASSWORD NULL` で作り、パスワード設定を最初から帯域外の作業として
   分けているので (§3(a))、この罠が無い。r2db 側だけ、migration の
   引数がパスワードを兼ねている。
2. その DSN を **control プロセスの `EnvironmentFile`** (`DEPLOYMENT_RUNBOOK.md`
   §7 step 1 の `/etc/r2dbsvc/control.env`。root:root / 0600) に
   `R2DB_AUDIT_DSN=` として置く。**data プロセスの `api.env` ではない** —
   読み手は control プロセスだけが持つ。
3. `audit_query` 専用のレート窓を既定 (60) から変える場合のみ、同じ
   `control.env` に `R2DB_CONTROL_LIMIT_AUDIT_REQUESTS_PER_MINUTE=` を置く。
   この peer には上限が無く、引き上げは設定変更で完結する (§15 の
   「Raising the window on this peer is a configuration change」)。
   窓の見積りは §15 の算式に従う。**追い付きはポーリングではなくページング**
   なので、定常値だけで見積もらない。

**値そのものを、本書・runbook・コミットのいずれにも書かない。**

### (c) 監査書込み timeout を両プロセスで揃える

裁定値 C を既定から動かす場合、`R2DB_AUDIT_STATEMENT_TIMEOUT_MS` と
`R2DB_AUDIT_IDLE_TIMEOUT_MS` を **`api.env` (data) と `control.env` (control)
の両方に、同一値で**置く。両プロセスは同名の env を独立に読むだけで、
一致を検証する機構は無い (§15 の "Structural assumption"、引き継ぎ §2
運用前提 1)。

**変えたら宣言が変わる。** 宣言される `visibility_lag_ms` は
`statement_timeout_ms + idle_in_transaction_session_timeout_ms + 1000`
(1s は固定の時刻ずれ余裕) であり、既定なら 11000。片側だけ変えると、
公開している `visibility_lag_ms` が `application_audit` について嘘になり、
どちらのプロセスもそれを検出しない。

同型の未強制が `coalescing_window_ms` にもある: 宣言は control プロセスが
共有既定定数 (60s) から出すが、実際に合体しているのは data プロセスの
`DataService(denial_coalesce_window_s=...)` である。今日この値に env の
つまみは無いので、**既定以外で構築しない**こと。両者に同じ規律を適用する:
**値を変えたなら宣言を変えたのであり、宣言も一緒に変えねばならない。**

data プロセス側にはこのほか `R2DB_AUDIT_BUFFER_CAPACITY` (既定 1000) と
`R2DB_AUDIT_FLUSH_INTERVAL_S` (既定 2.0) がある。前者は容量算式 (§6) に
入る値、後者は遅延のつまみで正しさには効かない。

`deploy/env/api.env.example` は、フェーズ4 の変数を含む補完済みの
テンプレートを使うこと。

### (d) 再起動

1. data プロセスの virtualenv にフェーズ4 のコードを入れ、
   `sudo systemctl restart r2dbsvc-api.service` (`DEPLOYMENT_RUNBOOK.md`
   §2 step 4 と同じ作法)。
2. control プロセスも同様にコードを入れ替え、その unit を再起動
   (§7 step 2 の 2 つ目の unit)。
3. 起動に失敗したら `journalctl -u <unit> -e` を先に読む。必須 env の
   欠落は、変数名を名指しする例外で**うるさく落ちる** — 検査を緩めて
   回避しない。
4. **control プロセスが実際に稼働し到達可能になったことを確認してから**、
   data プロセスの `api.env` に `R2DB_CONTROL_PLANE_STATUS=enabled` を置き、
   `r2dbsvc-api.service` を再起動する (`DEPLOYMENT_RUNBOOK.md` §7 step 3)。
   MitateDB の Invariant 3 (§3(c) の 6) と同じ性質の順序である: この env は
   **配備者の表明**であって、data プロセスは control の到達性を自分で
   確かめられない (R-9)。到達不能なまま `enabled` にすると
   `/v1/capabilities` が「control_plane: enabled」と主張しながら誰も
   listen していない、という宣言と実挙動の不一致になる。到達可否の正本は
   常に control 自身の `GET /control/v1/capabilities` であり、data 側の
   宣言ではない。逆向き — control プロセスを止める — なら、同じ変更の中で
   `unavailable` へ戻す。
   なお、綴りを誤った値は `unavailable` へ丸め込まれず、起動時に
   `RuntimeError` で落ちる (許容値は `enabled` / `unavailable` の 2 つ)。

### (e) 適用後検証

§4 の観測項目を、この peer について実行する。

---

## 3. MitateDB-api (Cloud SQL / Cloud Run) への適用

順序どおりに実行する。(a) → (e)。(c) は**新規配備**であり、r2db 側より
作業が多い。

### (a) migration `0005_application_audit.sql` の適用

正本: `cloud-run-cloud-sql.md` §3.2b、および migration ファイル自身のヘッダ。

Cloud SQL Auth Proxy を上げた状態で (§2 の proxy ceremony)、`0002` の後に、
`mitatedbsvc_provision` として一度だけ:

```sh
psql "host=127.0.0.1 port=5432 dbname=mitatedb_platform user=mitatedbsvc_provision password=$MITATEDBSVC_PROVISION_PASSWORD" \
  -f MitateDB-api/migrations/0005_application_audit.sql
```

r2db の `0007` と同じく **冪等** (`CREATE TABLE IF NOT EXISTS` +
条件付き role 作成 + 冪等 `GRANT`) であり、再実行して安全。

この migration は `mitatedbsvc_auditreader` を **`PASSWORD NULL` で**作る。
reader を使うなら、帯域外で一度だけパスワードを設定する (§3.2b の
`ALTER ROLE ... PASSWORD` の形。生成値は Secret Manager にのみ置く)。

### (b) data サービス (`mitatedb-data`) の再デプロイ

フェーズ4 (1.4.0) のコードから作ったイメージで `mitatedb-data` を
再デプロイする (§6.1 の `gcloud run deploy`)。これで初めて
`application_audit` の**書き手が動く** — migration だけでは 1 行も
書かれない。

この段階では `MITATEDB_CONTROL_PLANE_STATUS` を**まだ `enabled` にしない**
(§0.1 の現況どおり `unavailable` のまま)。反転は (c) の後 (Invariant 3)。

裁定値 C を既定から動かすなら、`MITATEDB_AUDIT_STATEMENT_TIMEOUT_MS` /
`MITATEDB_AUDIT_IDLE_TIMEOUT_MS` をここで `--set-env-vars` に含める
((d) 参照)。

### (c) `mitatedb-ctrl` の新規配備と `MITATEDB_AUDIT_DSN` の配線

**`audit_query` を MitateDB で提供するには、control サービスの新規配備が
必要である。**現況では存在しない (§0.1)。正本は §6 (冒頭の IAM 注記)、
§6.2、§7、§8。

1. **`roles/cloudsql.client` を ctrl の runtime service account に付与する。**
   §6 冒頭の 2026-09-01 実測所見: これが無いと Cloud SQL コネクタが
   `cloudsql.instances.get` の 403 でコンテナ起動前に落ちる (PostgreSQL の
   権限エラーとは別物)。data 側と ctrl 側の両方に必要。
2. reader の DSN を Secret Manager に `mitatedb-audit-dsn` として登録する
   (`mitatedb-controlplane-dsn` と同じ規約)。
3. §6.2 の `gcloud run deploy mitatedb-ctrl` を実行する。イメージは同一
   `docker/Dockerfile` の `SERVICE=control` ビルド。落としてはならない点:
   - `--no-allow-unauthenticated`
   - **`--max-instances=1`** — これは規模の都合ではなく**正しさの要件**で
     ある。`control_requests_per_minute` も `audit_requests_per_minute` も
     プロセス内カウンタなので、2 インスタンス以上では
     `limit_enforcement: enforced` の宣言が偽になる (Invariant 1、§3.2b)。
     この flag を外すことは容量変更ではなく、偽の宣言への静かな後退である。
   - `--add-cloudsql-instances` と ctrl 用 service account
   - `--set-secrets` に `MITATEDB_AUDIT_DSN=mitatedb-audit-dsn:latest` を
     含める (**任意** — 含めなければ `audit_query` は `unavailable` 宣言の
     まま。§0.1 の 4 と同じく、これも正当な選択)
4. invoker binding は**運用者のみ** (Google グループ)。`allUsers` にも、
   広いアプリケーション用 service account にもしない (§6.2)。
5. control credential を持っていないなら、§7 の `bootstrap` を
   **platform DB ごとに一度だけ**実行し、直ちに 1 回本物の rotate を
   行う (発行直後は `must_rotate=true` で、`control_capabilities` と
   自身の rotate 以外は何もできない)。**既に bootstrap 済みなら二度目を
   実行しない** — 紛失・漏洩・ロックアウトからの回復は `reset` であって
   二度目の `bootstrap` ではない (§8)。
6. **ctrl が実際に到達可能になったことを確認してから**、`mitatedb-data` を
   `--update-env-vars=MITATEDB_CONTROL_PLANE_STATUS=enabled` で再デプロイ
   する。順序は Invariant 3 (§0.1 / §8) の要求そのもの: data サービスは
   control の到達性を自分で確かめられないので、この env は**運用者の
   表明**である。到達不能なまま `enabled` にすると、`GET /v1/capabilities`
   が嘘をつく。逆向き — ctrl を止める/scale-to-zero する — なら、同じ
   変更の中で `unavailable` へ戻す。

### (d) timeout env を両サービスで同一値に

裁定値 C を既定から動かす場合、`MITATEDB_AUDIT_STATEMENT_TIMEOUT_MS` と
`MITATEDB_AUDIT_IDLE_TIMEOUT_MS` を **`mitatedb-data` と `mitatedb-ctrl` の
両方に、同一値で**設定する。宣言される `visibility_lag_ms` は control
サービスが**自分の env だけから**計算する一方、`application_audit` の書き手は
data サービスである。不一致は誰も検出しない (§3.2b の verify 注記)。

`coalescing_window_ms` も同型: 宣言は共有既定定数 (60s) 由来、実際に合体
するのは data 側の `AuditRouter` で、env のつまみは無い。既定以外で
構築しないこと。**値を変えたなら宣言も変える。**

### (e) 適用後検証

§4 の観測項目を、この peer について実行する。

**呼び出し経路について。** `mitatedb-ctrl` は `--no-allow-unauthenticated`
で IAM 保護されており、その上で control credential を
`Authorization: Bearer` で渡す必要がある。この二重の認証の通し方は
`cloud-run-cloud-sql.md` §6.3 が正本 (正規経路は `X-Serverless-Authorization`
へ ID トークン・`Authorization` へ control credential を分離する形。
`gcloud run services proxy` を使う代替経路も同節にある) — 以後この節を読むこと。
HTTP 経路が使えない間は、§4 のうち DB 権限に関する
項目 (3・4) と行の増加 (5 の前半) を、Cloud SQL Auth Proxy 経由の `psql`
(§3.2f のクエリ) で先に確認できる。

---

## 4. 適用後検証 (両 peer 共通の観測項目)

各項目は「何を打って、何が返れば合格か」で書く。peer 固有の名前だけを
読み替える。r2db の control ホストは
`https://control.example.invalid:<internal port>`、MitateDB は
`mitatedb-ctrl` の URL (実値は書かない)。

### 4-1. `audit_query` の宣言が `unavailable` 以外である

DSN を配線した場合のみの項目 (配線しないなら 4-6 が該当項目になる)。

**control ホスト**の capabilities を、rotate 済み control credential (または
audit role credential) で取得する:

```
curl -sk -H "Authorization: Bearer <control credential secret>" \
  https://control.example.invalid:<internal port>/control/v1/capabilities
```

合格: `200 application/json`、`capabilities.audit_query.status == "enabled"`、
`capabilities.contract_version == "1.5.0"`、`capabilities.audit_query.authority
== "control_or_audit"`、そして `audit_query` の**宣言語彙 3 本がいずれも空でない
配列**であること — `event_classes`、`operations`、`target_kinds`。

後ろの 2 本は**契約 1.5.0 (従属判断 10 項目 1) で加わった宣言キー**である
(フェーズ5、設計 `docs/design/PHASE5_CONTRACT_150_AND_LIMIT_RANGE_V1.md` D-1)。
実測される要素数は peer で違う — **r2db は `operations` 27 語 / `target_kinds`
5 語**、**MitateDB は `operations` 29 語 / `target_kinds` 5 語**。値の中身は
各実装が宣言するものであり、契約は enum を持たない (共通語彙へ統一しない)。
**要素数そのものは合格条件ではない**。合格条件は「3 本とも空でない配列で
あること」と、後述 4-5 で読んだ行の `operation` / `target_kind` がその宣言に
含まれることである。

**版数についての注意 (どのイメージを配備したかで正しい答えが変わる)**:
上の `1.5.0` は**フェーズ5 のコードから作ったイメージ**を配備した場合の
合格値である。フェーズ4 (1.5.0 以前) のコードから作ったイメージは
`capabilities.contract_version == "1.4.0"` を宣言し、`operations` /
`target_kinds` の 2 キーを**持たない** — これは不合格ではなく、その版の
契約に完全に適合した正しい宣言である (1.5.0 の義務は 1.5.0 以上を宣言する
実装にのみ掛かる)。**配備したイメージの版と宣言が一致していること**が
確かめたい性質であり、片方だけが動いていれば版束縛違反である。

不合格の読み違いに注意する 2 点:

- `GET /control/v1/capabilities` に**無資格版は無い**。`Authorization` を
  省けば `401 AUTH_REQUIRED` であり、それは配備成功の証拠ではない
  (`DEPLOYMENT_RUNBOOK.md` §7 step 5)。
- **data ホストの `/v1/capabilities` では `audit_query` は
  `unavailable` のままで正しい。**読み手は control ホストにしかいない。
  ここが `unavailable` であることは不合格ではない。

### 4-2. 宣言値が配備 env と整合する

同じ応答の中で:

- `capabilities.audit_query.visibility_lag_ms` ==
  (`*_AUDIT_STATEMENT_TIMEOUT_MS`) + (`*_AUDIT_IDLE_TIMEOUT_MS`) + 1000。
  既定なら 11000。
- `capabilities.audit_query.coalescing_window_ms` == 60000
  (既定の合体窓 60s)。

さらに、**宣言が両プロセスについて真である**ことを DB 側で確かめる。
書き手 role が実際に開いている接続の SESSION 値を見る:

```sql
SHOW statement_timeout;
SHOW idle_in_transaction_session_timeout;
```

r2db は `POSTGRES_PROVISIONING_RUNBOOK.md` §15、MitateDB は §3.2b が
この確認の正本 (実行する role と、新規 `psql` セッションでは SESSION 値が
再現しないという注意を含む)。両プロセス分が同じ値であること。

### 4-3. reader role で INSERT が拒否される (権限による append-only)

reader の DSN で接続し、`application_audit` へ INSERT を試みる:

```sql
INSERT INTO <registry schema>.application_audit (event_id) VALUES ('probe');
```

合格: **権限エラーで拒否される** (`permission denied for table
application_audit`)。列の不足などで文法エラーになる前に権限で落ちるのが
期待だが、いずれにせよ**行が入らないこと**が合格条件。
`control_audit` に対しても同じ結果になること。

### 4-4. 書き手 role で SELECT が拒否される

書き手 role (r2db = `r2dbsvc_api`、MitateDB = `mitatedbsvc_api`) の
接続で:

```sql
SELECT count(*) FROM <registry schema>.application_audit;
```

合格: `permission denied`。書き手は追記できるが、読み戻すことも、
改変することも、消すこともできない。これが「append-only はアプリコードの
規律ではなく DB 権限で担保されている」ことの実機証拠である。

### 4-5. 破壊的操作 1 件で行が増え、`audit_query` で読める

1. 適用後の**行数を控える** (schema owner または reader で):
   ```sql
   SELECT count(*) FROM <registry schema>.application_audit;
   ```
2. data ホストに対し、使い捨ての対象へ**破壊的操作を 1 件**実行する
   (削除を伴う mutation、または schema operation)。本番データを対象に
   しないこと。
3. 行数が**増えている**こと。破壊的操作は buffer を経由せず、データ
   commit の**前**に耐久 INSERT + commit される (fail-closed by
   construction) ので、flush 間隔を待つ必要は無い。
4. control ホストの `audit_query` で読む:
   ```
   curl -sk -X POST \
     -H "Authorization: Bearer <control または audit credential secret>" \
     -H 'Content-Type: application/json' \
     -d '{"limit": 5}' \
     https://control.example.invalid:<internal port>/control/v1/audit/query
   ```
   合格: `200`、`events` 配列の各要素が `plane` (`application` または
   `control`) と `cursor` を持ち、順序が `(recorded_at, plane, event_id)`
   である。2 で起こした操作に対応する行が見えること。
5. **cursor で続きが読める**こと:
   ```
   -d '{"after": "<最後の event の cursor>", "limit": 5}'
   ```
   合格: `200`。cursor は不透明値であり、クライアントが組み立てるもの
   ではない (最後に受け取った event の `cursor` をそのまま返すだけ)。
   デコード不能・解決不能な値は `VALIDATION_FAILED` になる。
   **`len(events) < limit` は終端を意味しない** — `visibility_lag_ms` 内の
   行はまだ返らないので、**空ページが返るまで**ポーリングを続ける
   (`completeness_note`)。
6. alias が同じ応答を返すこと (契約 1.4.0 条件付き義務 5):
   同じ body を `POST /v1/audit/query` (**control ホストの方**) へ送り、
   同じ形の `200` が返る。

補足: `count` は「この 1 行が代表する発生回数」で、0 と 1 は決して現れない
(合体集約行と overflow alert 行だけが持ち、他は NULL)。`outcome="allow"` は
「認可され実行に投入された」であって commit 成功を主張しない — 同じ
`request_id` の `outcome="error"` 行があれば commit していない。

### 4-6. DSN 未設定なら `CAPABILITY_UNSUPPORTED` である

reader DSN を配線しない配備 (§0.1 の 4)、または配線前に確認する場合の
合格条件。

**正典パスと alias の両方を叩く。**control ホストに対し、認証の通る
credential で:

- `POST /control/v1/audit/query` (正典)
- `POST /v1/audit/query` (alias。**control ホストの方**)

合格: **どちらも `400`** で、本体の error code が `CAPABILITY_UNSUPPORTED`
であること (`application/problem+json`)。**`200` ではない**し、**素の `404`
でもない** — ルートは登録されており、認証も認可も先に行われたうえでの
拒否である。capabilities では `audit_query.status == "unavailable"`。

この状態でも契約 1.4.0 宣言は完全に適合である。

---

## 5. logs-based alert の結線

正本: r2db = `POSTGRES_PROVISIONING_RUNBOOK.md` §15.2、
MitateDB = `cloud-run-cloud-sql.md` §3.2d 内「The five fixed alert messages」。
結線先の基盤は裁定値 D。

監査パイプラインが出す `logging.error` は**ちょうど 5 種**であり、いずれも
補間の無い固定文字列である (意図的 — クライアント由来の値がプロセスログへ
到達しない)。**5 種すべてに完全一致でアラートを張ること。**これは独立した
2 つの証拠喪失チャネルであり、最初の 3 つだけに張ると合体チャネルが
無音になる。

| # | メッセージ (完全一致) | 意味 |
|---|---|---|
| 1 | `application_audit buffer overflow: events were dropped` | 証拠喪失が**既に起きた**: bounded buffer が最古の event を落とした |
| 2 | `application_audit overflow-alert row could not be written; retrying with backoff` | 帯域内の alert 行自体が書けない — 耐久チャネルと alert が同時に失敗している。再試行は 60s 上限の指数バックオフで貼り付く |
| 3 | `application_audit overflow-alert row recorded; pending overflow cleared` | 上の対の**回復**: alert 行が着地し、累積した drop 数がその `count` に載った |
| 4 | `application_audit coalesced-denial summary row could not be written; retrying` | 合体 denial の窓末集約行が着地していない。その窓の最初の同期行は耐久だが、**繰り返し回数がメモリに取り残されている** — 書き手は INSERT のみなので、最初の行の `count` を後から直すことはできない。何も拒否されていなくても証拠喪失である |
| 5 | `application_audit coalesced-denial summary row recorded; retry cleared` | 上の対の**回復**: 集約行が着地し、取り残されていた回数がその `count` に入った |

2/4 と 3/5 の対は、試行ごとではなく **failing↔healthy の状態遷移でのみ**
発火する (ログ DoS を避けるための規律)。

**回復は、対応する回復メッセージで読む。**buffer/overflow チャネルなら
**3 番目** (`application_audit overflow-alert row recorded; pending overflow
cleared`)、合体チャネルなら **5 番目** (`application_audit coalesced-denial
summary row recorded; retry cleared`)。**メッセージが途切れたことを回復と
みなさない。**証拠が失われることはない — drop カウンタは積算され、いずれ
alert 行の `count` に載る。

---

## 6. platform DB 容量閾値

正本: r2db = §15.1、MitateDB = §3.2d。**算式は複製しない。**本節は裁定値
A (M) を代入する手順だけを書く。

1. 1 行サイズの上限は両 peer とも **2 KiB** (11 個の bounded text 列の
   length CHECK 合計 1504 文字 + `event_id` + 2 つの timestamp + `count` +
   `audit_seq` + tuple overhead)。アプリケーション入力がこれを超えることは
   ない — CHECK が INSERT を拒否する。
2. **プロセスあたりの行数上限**を runbook の表 (§15.1 / §3.2d) から読む:
   fail-closed 操作、合体 denial (キーあたり 60s 窓あたり **2 行**、
   決して 1 ではない)、buffer 済みの通常成功 (最大 `*_AUDIT_BUFFER_CAPACITY`)、
   overflow alert (flush 間隔あたり最大 1 行)。
3. **M を掛ける。**合体カウンタも buffer も**プロセスローカル**であり、
   インスタンス間で共有されない。配備全体の上限は runbook の
   `2 × <キー数> × <窓数> × M` および `<buffer 容量> × M`。ここに裁定値 A を
   代入する — 既定値ではなく、**スケーラの実際の最大値**を入れること
   (r2db の VPS は通常 M=1、MitateDB は `mitatedb-data` の
   `--max-instances`。`mitatedb-ctrl` の 1 ではない)。
4. runbook の `bytes/hour` 概算式に、3 の M と配備の
   `<ops/hour>` / `<distinct denial keys>` / flush 間隔を入れて、裁定値 B の
   しきい値を出す。
5. **絶対サイズではなく増加率にアラートを張る** (絶対サイズは保存期間の
   決定であって、容量監視ではない — §15.3 / §3.2e)。定期サンプルの
   クエリは runbook にある `pg_total_relation_size(...)` の 2 列。
   MitateDB では、これをインスタンス自身のストレージ使用率メトリクスと
   組み合わせ、自動ストレージ拡張を有効に保つ。

これが単なる整頓でない理由: platform DB は**全アプリケーション**の
credential store でもあるため、ディスクが埋まればプラットフォーム全体の
認証が止まる。SI-00 の可用性側であり、行サイズ・行数の上限が存在する理由
そのものである。

---

## 7. ロールバック

適用を戻す必要が生じた場合、戻す粒度は 2 つある。

**migration は残して無害である。**`application_audit` テーブルと
`*_auditreader` role を残したまま、書き手のコード (フェーズ4 前のコード) に
戻せば、単に**書き手が INSERT しなくなる**だけである。テーブルは残り、
それまでに書かれた行も残る。追加された権限は「書き手が 1 テーブルに
INSERT できる」「reader が 2 テーブルを SELECT できる」の 2 つだけで、
どちらも使われなければ何も起こさない。**慌てて migration を巻き戻さない
こと** — 消せば証拠が消える。

**`audit_query` だけを戻すなら、DSN を外す。**`R2DB_AUDIT_DSN` /
`MITATEDB_AUDIT_DSN` を設定から外して該当プロセス/サービスを再起動すれば、
宣言は `{"status": "unavailable"}` に戻り、両ルートは登録されたまま認証後に
`CAPABILITY_UNSUPPORTED` を返す。**耐久 sink は動き続ける** — 証拠は
溜まり続け、読む手段が帯域外 (§15.4 / §3.2f の `psql`) だけになる。
この状態も契約 1.4.0 に完全に適合する。

MitateDB で `mitatedb-ctrl` そのものを止める / undeploy する /
scale-to-zero する場合は、**同じ変更の中で** `mitatedb-data` の
`MITATEDB_CONTROL_PLANE_STATUS` を `unavailable` へ戻すこと (Invariant 3、
§8)。止めただけでは control credential は失効しない — 破棄が必要なら
`CONTROL_PLANE_COMPROMISE_PLAYBOOK.md` に従う。

監査行そのものの削除は、ロールバックではなく**保存期間の決定**である。
手順は §15.3 / §3.2e (schema owner が実施、エクスポートが先、DELETE は
不可逆、何をいつ誰が消したかは別途記録 — 消した後のテーブルはそれを
証拠立てない)。
