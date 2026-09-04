# フェーズ6 成果の配備実機適用手順 (2026-09-04)

対象: `MitateDB-api` (Cloud Run / Cloud SQL) と `r2db-api` (VPS) の両 peer。
適用するもの: **フェーズ4 / フェーズ5 / フェーズ6 を一括**で実配備へ載せる —
耐久 audit sink + `audit_query` (契約 1.4.0)、`audit_query` の宣言語彙 2 本
(1.5.0)、そして **契約 1.6.0** (locator 形の完全 bearer / `surfaces` /
型付き catalog)。設計は `docs/design/PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md`
(v1.5)、引き継ぎは `docs/work-orders/HANDOVER_20260904_FABLE2.md` §4-1。

**この手順書の位置付け。** `docs/work-orders/DEPLOY_PHASE4_20260903.md` は
**撤回されない**。あの文書の §1.2 (実行 role) / §1.3 (edge policy) / §4 (検証
項目) / §5 (alert) / §6 (容量閾値) / §7 (ロールバックの原則) は本書からも参照
する正本である。本書が足すのは 2 つ:

1. **1.6.0 が手順そのものに作った差分** (引き継ぎ §4-1 の 4 点) — 既存
   credential の再発行、`surfaces` 環境変数 2 本、MitateDB の migration
   `0006`、MitateDB の挙動変更 α/β/γ の cutover。
2. **担当の分離と順序** — 本適用は監督 (秘密を扱わない `gcloud` 操作) と
   運用者 (秘密・psql・SSH を扱う操作) に分かれる。各ステップに **[監督]** /
   **[運用者]** を付し、依存順を固定した。

コマンドや算式は runbook から複製しない。**各ステップは runbook の該当節を
指し、そこを正本として読む。**運用者がその場で打つコマンド列だけ、往復を
減らすために再掲する。runbook と本書が食い違って見えたら、runbook が正しい。

正本 (本書が参照する側):

| peer | 正本 |
|---|---|
| MitateDB-api | `MitateDB-api/docs/cloud-run-cloud-sql.md` §0 / §0.1 / §3.2b〜§3.2f / §3.4a / §6 / §6.1 / §6.2 / §6.3 / §6.4 / §7 / §8 |
| r2db-api | `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` **§5** / §10 / §12 / §15 (§15.1〜§15.5)、`r2db-api/deploy/DEPLOYMENT_RUNBOOK.md` **§1 / §2** / §7、`r2db-api/deploy/env/{api,control}.env.example`。**2026-09-05 の実測により §3 は初回導入になったので、§5 (migration の順序) と DEPLOYMENT_RUNBOOK §1〜§2 が正本に加わり、§12a (既存 credential の再発行) は対象が無く該当しない** (§0.1 の 4-b) |
| 共通 | `spec/data-service-api.v1.json` (`versioning.version_binding` の 1.6.0 段落)、`spec/CCR_DISPOSITION.md` 従属判断 11、`security/CONTROL_MAPPING.md`、`docs/work-orders/DEPLOY_PHASE4_20260903.md` |

**公開リポジトリの文書である。**以下には GCP プロジェクト ID / リージョン /
サービス名 / service account 名 / Secret Manager の**名前** / Cloud Run の
URL が実名で現れる。これらは秘密ではない (URL 中の `<GCP_PROJECT_NUMBER>` は project
number であり、公開情報として扱う)。**秘密値・実 DSN・パスワード・pepper・
bearer は 1 文字も書かない。**それらは Secret Manager と `/etc/r2dbsvc/*.env`
(root:root 0600) にのみ置く。

---

## 0. 適用の前提と、この手順書が決めないこと

### 0.1 前提

1. **適用元は main `4e48d1a`** (フェーズ6 完了、契約 1.6.0)。root suite の
   実測は **1802 passed / 0 failed / 0 skipped / 0 xfailed**
   (`pytest -q -n 5 --dist loadgroup`、監督が単独実行した完了ゲート)。
2. **両実配備ともフェーズ4 以前のコードのままである。**したがって本適用は
   フェーズ4・5・6 を一度に載せる。**migration を当てただけでは書き手は 1 行も
   INSERT しない** — コードの入れ替え (MitateDB = 1.6.0 イメージでの再デプロイ、
   r2db = virtualenv への再インストール + 再起動) が必須である
   (DEPLOY_PHASE4 §0.1 の 1)。
3. **1.6.0 が手順に作る差分は 4 点** (引き継ぎ §4-1):
   - **(i) 既存 credential の再発行** — 互換シムは無い。**ただし要否は peer で
     非対称である** (下の 5 を読むこと)。r2db の手順は
     `POSTGRES_PROVISIONING_RUNBOOK.md` §12a。
   - **(ii) `surfaces` の環境変数 2 本** — `*_DATA_BASE_URL` /
     `*_CONTROL_BASE_URL` を **data / control の両プロセスに同一値で**配る。
     形が不正なら起動時に落ちる。
   - **(iii) MitateDB の migration `0006`** — 既存 application データベースへ
     per-application で適用する (`cloud-run-cloud-sql.md` §3.4a)。**未適用の DB は
     catalog だけでなく read / write も `StorageConfigurationError` で落ちる。**
   - **(iv) MitateDB の挙動変更 α / β / γ の cutover** — `cloud-run-cloud-sql.md`
     §6.4。**利用側 (`mitate-application`) に影響しうる唯一の箇所**である。
4. **監督が読み取り専用で実測した現況 (2026-09-04)。**以下は実測であり、
   推測ではない。実測できなかった項目は「未実測」と明記した。
   **2026-09-05 の作業でこの表の一部は更新された** — 更新分は各行に
   「→ (2026-09-05)」として併記し、旧値は消していない (配備前の状態そのものが
   §7 の記録対象だからである)。

   | 項目 | 実測値 |
   |---|---|
   | GCP project | `<GCP_PROJECT_ID>` |
   | region | **`<REGION>`** (runbook の例示 `us-central1` ではない) |
   | Cloud SQL | `mitatedb-platform` (POSTGRES_16、RUNNABLE)、接続名 `<GCP_PROJECT_ID>:<REGION>:mitatedb-platform` |
   | Cloud Run `mitatedb-data` | image `<REGION>-docker.pkg.dev/<GCP_PROJECT_ID>/cloud-run-source-deploy/mitatedb-api:phase-b` (**フェーズ4 以前のコード**、2026-09-01 ビルド)、maxScale 1、SA `mitatedb-data-runtime@<GCP_PROJECT_ID>.iam.gserviceaccount.com`、ingress all |
   | 同 env | `MITATEDB_SERVE_APPS=mitate`、`MITATEDB_CONTROL_PLANE_STATUS=unavailable` |
   | 同 secrets | `MITATEDB_CREDENTIAL_PEPPER<-mitatedb-credential-pepper`、`MITATEDB_PLATFORM_DSN<-mitatedb-platform-dsn`、`MITATEDB_APP_MITATE_RUNTIME_DSN<-mitatedb-app-mitate-runtime-dsn`、`MITATEDB_APP_MITATE_DEVELOPER_DSN<-mitatedb-app-mitate-developer-dsn` |
   | 同 URL | `https://mitatedb-data-<GCP_PROJECT_NUMBER>.<REGION>.run.app` (旧形式 `https://mitatedb-data-<RUN_HASH>-an.a.run.app` も同一サービス) |
   | Cloud Run `mitatedb-ctrl` | **未配備** → **(2026-09-05) 配備済み**。revision `mitatedb-ctrl-00001-m8s` (image `1.6.0-control`、`--max-instances=1`、`--no-allow-unauthenticated`、SA `mitatedb-ctrl-runtime@<GCP_PROJECT_ID>.iam.gserviceaccount.com`、Cloud SQL 接続あり、audit DSN 無し)。詳細は §2(g) |
   | Secret Manager (名前のみ) | `mitatedb-credential-pepper` / `mitatedb-control-credential-pepper` / `mitatedb-controlplane-dsn` / `mitatedb-platform-dsn` / `mitatedb-provision-dsn` / `mitatedb-postgres-bootstrap` / `mitatedb-control-credential` (version 1、bootstrap 済み) / `mitatedb-app-mitate-runtime-credential` / `mitatedb-app-mitate-developer-credential` (ともに version 1) / `mitatedb-app-mitate-{runtime,developer}-dsn`。**`mitatedb-audit-dsn` は存在しない** |
   | 利用側 | Cloud Run `mitate-application` が `MITATE_DATA_SERVICE_URL=https://mitatedb-data-<RUN_HASH>-an.a.run.app` と `MITATE_DATA_SERVICE_RUNTIME_CREDENTIAL<-mitatedb-app-mitate-runtime-credential` で MitateDB を使う (`mitate-agent` は `mitate-application` 経由) |
   | application DB | **1 つ (`mitate`)** → migration `0006` の適用は 1 回 |
   | Cloud SQL の migration 適用状況 (`0005` / `0006`) | **未実測 (2026-09-05 時点でも未実測)** → §1.4 で先に読む。両方とも冪等なので、確信が持てないなら再実行してよい。**(2026-09-05) `0006` が未適用である可能性を強く示す観測が出た** — §2(c) の検証結果を読むこと |
   | `mitatedb-data` の invoker 設定 (`--allow-unauthenticated` の有無) | **未実測** → §2(c) の検証前に `get-iam-policy` で読む。**(2026-09-05) 監督は tag URL を直接叩かず `gcloud run services proxy` 経由で検証したため、この項目は依然として未実測のままである** |
   | r2db (VPS `r2-vps`) | **未実測 (2026-09-04 時点)** → **(2026-09-05) SSH 読み取りで実測した。下の 4-b を読むこと。結論: 本リポジトリの r2db-api は VPS に未導入であり、§3 は「アップグレード」ではなく初回導入である** |

4-b. **VPS (`r2-vps`) の現況 — 監督が SSH で読み取り実測した (2026-09-05、
   ユーザー `<VPS_USER>`、読み取りのみ)。**

   | 項目 | 実測値 |
   |---|---|
   | 稼働しているサービス | **既存本番の `r2db-api.service` のみ** (`/home/<VPS_USER>/r2-vps/apps/r2db-api`、uvicorn が `127.0.0.1:<EXISTING_APP_PORT>`、nginx が `db.example.invalid` の 443 で前段)。**これは本リポジトリの実装ではない** (`DEPLOYMENT_RUNBOOK.md` §0 が「同居する無関係な既存配備」と呼んでいるもの) |
   | 本リポジトリの r2db-api (Stage 1) | **未導入。**`/etc/r2dbsvc` も `/opt/r2dbsvc` も無く、`r2dbsvc-*` の systemd unit も無い。8443 を listen しているものも無い |
   | Python | **3.12.3 のみ** (`DEPLOYMENT_RUNBOOK.md` §1 の 5 が言う virtualenv は未作成) |
   | 監督の特権 | **無い。**`sudo` はパスワードを要求するため、監督は VPS 上で特権操作を実行できない。**§3 は全ステップが [運用者] である** |

   **この実測が §3 の性格を変える。**本書の初版は §3 を「フェーズ4 前のコードの
   入れ替え」として書いていたが、**入れ替える対象が存在しない。**したがって §3 は
   **`DEPLOYMENT_RUNBOOK.md` §1〜§2 (Stage 1 の初回導入) + §7 (control プロセス) +
   migration `0001`〜`0007` の初回適用**を、最初から 1.6.0 のコードで行う作業として
   読む (§3 を書き直した)。**その結果 `POSTGRES_PROVISIONING_RUNBOOK.md` §12a
   (既存 credential の再発行) は不要になる** — 初回導入で発行する credential は、
   1.6.0 の CLI が最初から locator 形で印字するからである。§12a は「1.6.0 より前に
   発行された credential」だけを対象とする節であり、この配備にはその対象が無い。

5. **既存 credential の再発行の要否は peer で非対称である (重要)。**

   - **r2db は、1.6.0 より前に発行された credential があるなら必須である。**
     1.6.0 より前の r2db は presented bearer 全体の digest で行を引いていた
     (`_SELECT_BY_VERIFIER`)。1.6.0 は `<credential_id>.<secret>` を locator と
     して行を引き、そのうえで `compare_digest` する。**旧 bare secret はその
     ままでは `AUTH_INVALID`** になる (`POSTGRES_PROVISIONING_RUNBOOK.md` §12a)。
     **ただし 4-b の実測により、この配備には対象が 1 件も無い** — Stage 1 は
     未導入であり、credential はこれから 1.6.0 の CLI で初めて発行される。
     §12a の再発行手順は**この配備では実行しない** (§3(e) を読むこと)。
   - **MitateDB は必須ではない。**この peer は **1.6.0 以前から受理側が
     `<credential_id>.<secret>` の locator 形**であった (WP-3 の差分は
     `http.py` の境界で分解していたものを store 内の 1 箇所へ寄せただけであり、
     wire 形は変わっていない)。1.6.0 が変えたのは**発行側の返却形**である —
     従来は raw secret を返しており、**実装知識で合成していた統合者だけが
     動いていた** (引き継ぎ §3 の 1)。`cloud-run-cloud-sql.md` §6.4 の
     「None of the three requires re-issuing any existing credential」は
     この事実の記述である。
   - したがって **`mitate-application` が今日認証を通っているなら、その
     credential は既に locator 形であり、1.6.0 の flip 後もそのまま通る。**
     §2(d) はこの事実の確認から始まり、再発行は**選択**である (裁定 E)。
   - **rotate は不可逆である。**rotate すると verifier が上書きされ、**旧
     secret は永久に失効する。**Secret Manager の旧 version を再 enable しても
     戻らない。ロールバックの設計は §6 でこの事実の上に立てる。

6. **reader DSN (`MITATEDB_AUDIT_DSN` / `R2DB_AUDIT_DSN`) を配線しない選択は、
   いつでも正当である** (DEPLOY_PHASE4 §0.1 の 4)。1.6.0 でもこの性質は
   変わらない。裁定 F。

7. **担当ラベルの意味。**
   - **[監督]** = 秘密を扱わない `gcloud` 操作。イメージのビルド (Cloud Build)、
     IAM binding、`gcloud run deploy` (secrets は `--set-secrets` の**名前参照
     のみ**)、`gcloud run services update-traffic`、および **credential を
     必要としない HTTP 検証**。
   - **[運用者]** = 秘密に触れる操作すべて。Cloud SQL Auth Proxy 経由の `psql`
     (migration 適用、reader パスワード)、break-glass CLI による発行・rotate
     (印字される secret は運用者だけが見る)、Secret Manager への version 追加、
     `mitate-application` の再デプロイ、**VPS 上の全作業 (SSH)**。
   - **`GET /v1/capabilities` は認証を要する**ので、監督はこれを叩けない。
     監督が確認できるのは「無資格で 401 + `application/problem+json` が返る」
     ことまでである (それでも revision が立って serving していることの証拠に
     なる。DEPLOYMENT_RUNBOOK §2 step 6 の 1 と同じ検査)。

### 0.2 この手順書が決めないこと (運用者裁定値) — **裁定済み (2026-09-05)**

以下 6 つは配備固有の値であり、本書は決めない。**適用前に埋め、埋めた表を
本書と一緒に配備記録 (§7) へ残すこと。**空欄のまま §2 / §3 に入らない。

**この表は 2026-09-05 に依頼者が裁定し、埋まった。**以下は空欄の様式ではなく
**確定値**である。変更するなら、変更した事実と理由を §7 に書く。

| # | 裁定項目 | MitateDB-api | r2db-api | 根拠 / 参照 |
|---|---|---|---|---|
| A | 最大インスタンス数 **M** (容量算式に入れる値) | **1** | **1** | MitateDB: `mitatedb-data` の `--max-instances` (現況 1、(c) の新 revision も `--max-instances=1` で作った)。`mitatedb-ctrl` は Invariant 1 により 1 固定だが、**M は data 側の値**。r2db: VPS の単一 uvicorn プロセスなので 1。§3.2d / §15.1 |
| B | platform DB 容量閾値の実数 (増加率のしきい値と観測間隔) | **既定算式値 (A=1、buffer 1000、flush 2.0 s を代入)** | **同左** | DEPLOY_PHASE4 §6 / §3.2d / §15.1 の算式そのまま。下の「B の代入結果」を読むこと。絶対サイズではなく**増加率**に置く |
| C | 監査書込み timeout の配備値 (`*_AUDIT_STATEMENT_TIMEOUT_MS` / `*_AUDIT_IDLE_TIMEOUT_MS`) | **既定 5000 / 5000** (env を置かない) | **既定 5000 / 5000** (env を置かない) | 既定 5000/5000 → 宣言 `visibility_lag_ms` = **11000**。**変えたら宣言が変わる**。data と control の**両方に同一値**を入れる (§3.2b / §15)。既定を採ったので、両プロセスとも当該 env を**置かない**ことが「同一値」の実現手段である |
| D | alert 結線先の基盤 (5 種の固定メッセージをどこで拾い、誰に鳴らすか) | **今回は結線しない (記録のみ、将来課題)** | **同左** | §3.2d / §15.2。**未結線であること自体は契約違反ではない**が、5 種のメッセージが鳴っても誰も気付かない状態である。§5 に未結線時の含意を書いた。将来 Cloud Logging のログベース指標 (MitateDB) / journald (r2db) へ張る |
| E | **切替窓** — `mitate-application` に影響する変更をいつ、どの順で通すか | **即時 (窓を設けない)** | (該当なし。Stage 1 に production traffic は無い) | §2(d)〜(f)。**窓が要る 2 つの理由のうち (2) は消えた** — MitateDB は credential 再発行が不要と確定した (§0.1 の 5、裁定 E-2 = しない)。残るのは (1) **挙動変更 β / γ** だけであり、これは `mitate-application` の**事前対応ではなく (f) 直後の影響確認**として扱う。したがって (d) / (e) は実施せず、(b) 完了 → (c) の再検証 → (f) → β/γ の確認、と直列に進む |
| E-2 | 上記のうち **credential を再発行するか** | **しない** | (**しない選択は無い** — §0.1 の 5) | §0.1 の 5。MitateDB では**必須ではない**。**rotate は不可逆**であり、必要でない不可逆操作は行わない。§2(d) は「事実の確認」だけを実施し、rotate は実行しない。r2db 側は §0.1 の 4-b により**再発行の対象が存在しない** (初回発行である) |
| F | **reader DSN を配線するか** (任意) | **しない** | **しない** | DEPLOY_PHASE4 §0.1 の 4。配線しないので `audit_query` は **`unavailable` 宣言のまま**であり、両ルートは認証後 `CAPABILITY_UNSUPPORTED` を返す。**これも契約適合である。**したがって Secret Manager の **`mitatedb-audit-dsn` は新設しない**し、`R2DB_AUDIT_DSN` も置かない。**耐久 sink 自体は動く** — 証拠は溜まり、読む手段が帯域外の `psql` (§3.2f / §15.4) だけになる |

**B の代入結果 (A=1、既定値)。**算式は DEPLOY_PHASE4 §6 (正本は §3.2d / §15.1)
であり、ここでは A と既定値を代入した形だけを書く:

```
bytes/hour  ~=  2 KiB * 1 * ( <ops/hour> + 2 * <distinct denial keys> * 60 + 3600 / 2.0 )
```

- 配備全体の上限は `2 × <キー数> × <窓数> × 1` 行 (合体 denial) と
  `1000 × 1` 行 (buffer 在庫、`*_AUDIT_BUFFER_CAPACITY` の既定)。**M=1 なので
  プロセスローカルの上限がそのまま配備全体の上限である。**
- 配備の traffic に依らない項は overflow alert の `3600 / 2.0 = 1800` 行/時
  (flush 間隔の既定 2.0 s)、すなわち **2 KiB × 1800 ≒ 3.5 MiB/時が最悪値**。
  残る 2 項 (`<ops/hour>`、`<distinct denial keys>`) は**その配備の traffic で
  あって裁定値ではない** — しきい値を実数 1 つに固める時点で観測から入れる。
- **観測間隔は今回定めない。**裁定 D が「結線しない」である以上、定期サンプルを
  取る主体が無い。**B は「結線するときに使う算式の確定形」として記録する**もの
  であり、今日から鳴る閾値ではない。この区別を §7 にそのまま書く。

C を既定から動かす場合は、**その peer の data プロセスと control プロセスの
両方に同じ値を入れる**こと。片側だけ変えると、宣言 `visibility_lag_ms` が
嘘になる。この一致は機構的に強制されていない。

**表の外に 1 つだけ、その場で指名する値がある**: `mitatedb-ctrl` の
`roles/run.invoker` を持つ principal (運用者グループ、または個々の運用者
アカウント。**`allUsers` にも、`mitate-application` の service account にも
しない**)。§2(g) で指名し、§7 の配備記録に書く。

**この指名も 2026-09-05 に確定した (裁定)。**

- `mitatedb-ctrl` の `roles/run.invoker` = **`user:<OPERATOR_ACCOUNT_EMAIL>`**
  (運用者本人。**付与済み**)。個々の運用者アカウントであり、`allUsers` でも
  `mitate-application` の service account でもない — §1.5 が言う
  「サービス単位の制限」の要求を満たす。
- あわせて、**同じ運用者アカウントに `mitatedb-data` の `roles/run.invoker` も
  付与した** (検証用)。これは `gcloud run services proxy` 経由で data 側の
  無資格 probe を打つためであり、**`allUsers` を足したのではない。**
  この付与によって `mitatedb-data` の invoker 集合が変わっていることに注意し、
  §1.2 の `get-iam-policy` を読むときは「元から誰が入っていたか」と
  「2026-09-05 に足した運用者アカウント」を区別すること。

---

## 1. 適用前チェック

### 1.1 適用元の確認 [監督]

1. 作業ツリーが main `4e48d1a` を含むこと (`git rev-parse HEAD`、
   `git log --oneline -1`)。**イメージのビルドと CLI の実行は、必ずこの
   ツリーから行う** — 旧ツリーの CLI は旧形式の secret を印字する。
2. root suite を**単独実行**し、**1802 passed / 0 failed / 0 skipped /
   0 xfailed** を実測して配備記録に控える。コマンドは
   `./.venv/bin/python -m pytest -q -n 5 --dist loadgroup`。他の pytest が
   走っていないことを `ps` で確認してから回す (引き継ぎ §4-3 の運用規律)。
3. コミット identity の確認は本作業では不要 (本書は配備作業であって
   コミット作業ではない)。適用の過程で文書を更新してコミットする場合のみ、
   通常どおり `git log --format='%an <%ae>'` を確認する。

### 1.2 gcloud 認証と権限 [監督]

```sh
gcloud auth list
gcloud config get-value project     # <GCP_PROJECT_ID> であること
gcloud run services describe mitatedb-data --project=<GCP_PROJECT_ID> --region=<REGION>
gcloud run services get-iam-policy  mitatedb-data --project=<GCP_PROJECT_ID> --region=<REGION>
```

最後の 1 本は §0.1 の「invoker 設定 未実測」を埋めるためのものである
(`allUsers` が入っているか、`mitate-application` の SA だけか)。**検証時に
返る `403` が「Cloud Run の front end が拒否した」なのか「アプリが答えた」
なのかは、この事実を知らないと読み分けられない。**

> **2026-09-05 時点でこの 1 本はまだ実行していない** — (c) の probe は
> `gcloud run services proxy` 経由で打ったため、front end の IAM を経由して
> いない。**(f) の前に実行して §7.2 を埋めること。**読むときは、
> **2026-09-05 に運用者アカウント (`user:<OPERATOR_ACCOUNT_EMAIL>`) へ
> `mitatedb-data` の `roles/run.invoker` を検証用に足している**ことを踏まえ、
> 「元から入っていた principal」と区別する。

必要な権限: Cloud Build の実行、Artifact Registry への push、
`roles/run.admin` 相当 (deploy / update-traffic)、
`roles/iam.serviceAccountUser` (deploy 時の SA 指定)、および §2(g) の
`gcloud projects add-iam-policy-binding` を打てること。

### 1.3 Cloud SQL Auth Proxy [運用者]

`cloud-run-cloud-sql.md` §2 の proxy ceremony を上げる
(`<GCP_PROJECT_ID>:<REGION>:mitatedb-platform`、`127.0.0.1:5432`)。
以降の `psql` と break-glass CLI は**すべてこの proxy 経由**であり、
**どちらの Cloud Run サービス経由でもない** (§7 冒頭)。

### 1.4 migration 適用状況の確認 [運用者]

**両方とも冪等なので、確信が持てないなら状態を調べるより再実行する方が
安全である。**それでも、backfill 行数を後で突き合わせるために、適用前に
一度読んでおく。

> **2026-09-05: この節は未実施のままであり、いま最優先である。**(c) の新
> revision が無資格 probe に **`503`** を返した — `0006` 未適用による
> `StorageConfigurationError` が最有力の説明である ((c) の検証結果)。
> **下の 2 本目のクエリ (`to_regclass('public._mdb_field_types')`) が
> その仮説を直接確かめる。**
>
> **r2db 側のクエリは、この配備では「接続先がまだ無い」ことに注意する** —
> §0.1 の 4-b のとおり VPS には `r2dbsvc_platform` 自体が存在しない可能性が
> 高い。**存在しないことの確認**として読み、そのまま §3(b) の初回構築へ進む。

**MitateDB — platform DB** (`mitatedbsvc_provision` で接続):

```sql
-- 0005 (フェーズ4、application_audit + reader role)
SELECT to_regclass('mitatedb_registry.application_audit');          -- 非 NULL なら適用済み
SELECT rolname FROM pg_roles WHERE rolname = 'mitatedbsvc_auditreader';
-- application と、その物理データベース名
SELECT application_id, database_name FROM mitatedb_registry.applications;
```

**MitateDB — application DB** (上で読んだ `database_name` へ `\c`):

```sql
-- 0006 (フェーズ6、宣言型 registry)
SELECT to_regclass('public._mdb_field_types');                      -- 非 NULL なら適用済み
SELECT count(*) FROM public._mdb_field_types;                       -- 適用済みなら行数
-- 突合の相手: backfill 対象となる列の総数
SELECT count(*) FROM information_schema.columns
 WHERE table_schema = 'public'
   AND table_name NOT IN ('_mdb_schema_revision', '_mdb_field_types');
```

**r2db — platform DB** (`r2dbsvc_control` で接続。VPS 上、[運用者]):

```sql
SELECT to_regclass('r2dbsvc_registry.application_audit');            -- 0007 (フェーズ4)
SELECT rolname FROM pg_roles
 WHERE rolname IN ('r2dbsvc_auditreader', 'r2dbsvc_controlplane');   -- 0007 / 0006
```

**r2db にフェーズ6 の migration は無い** — D-1 は DDL を要さない
(設計 §8 の 5)。

### 1.5 実行 role と接続経路 / edge policy

**DEPLOY_PHASE4 §1.2 の表と §1.3 をそのまま適用する。**フェーズ6 は role も
経路も edge policy の射程も変えていない。特に §1.3 の「`audit_query` を
有効化すると control ホストが `/control/v1/*` の外側のパス
(`POST /v1/audit/query`) も応答する」は、`mitatedb-ctrl` を新規配備する
本適用でこそ効く — MitateDB では `--no-allow-unauthenticated` + 運用者限定
invoker が**サービス単位の制限**になっているため、§2(g) の binding を
指定どおりに置けば満たされる。**→ 2026-09-05 に置いた** (`mitatedb-ctrl` は
`--no-allow-unauthenticated` + invoker = `user:<OPERATOR_ACCOUNT_EMAIL>`)。
**ただし裁定 F = 配線しないので、この配備の `mitatedb-ctrl` は
`POST /v1/audit/query` を認証後 `CAPABILITY_UNSUPPORTED` で断る** — 射程の
問題は発生しないが、**サービス単位の制限は F の値に関わらず維持する。**

---

## 2. MitateDB-api (Cloud Run / Cloud SQL) への適用

順序どおりに実行する。**(a) → (i)。**担当が交互に入れ替わるので、各ステップの
完了を相手に伝えてから次へ進む。

**進捗 (2026-09-05 時点の実測)。**各ステップの本文冒頭に同じことを
「**[実施済み]** / **[未実施]**」として書いた。実測値の正本は §7 の記録表である。

| ステップ | 担当 | 状態 (2026-09-05) |
|---|---|---|
| (a) イメージ 2 本のビルド | [監督] | **実施済み** |
| (b) migration `0005` → `0006` | [運用者] | **未実施。以降すべての前提であり、(f) の必須前提であることが (c) の検証で実測された** |
| (c) data の 1.6.0 revision を `--no-traffic` で作る | [監督] | **実施済み** (traffic は旧 revision が 100% のまま)。**無資格 probe は `401` ではなく `503` を返した** — 下を読むこと |
| (d) credential の扱い | [運用者] | **rotate は実施しない (裁定 E-2 = しない)。**「今日認証が通っているか」の確認のみ残っている |
| (e) `mitate-application` の再デプロイ | [運用者] | **実施しない** ((d) で新 version を作らないため)。β/γ の確認は (f) の後に行う |
| (f) traffic 切替 | [監督] | **未実施。(b) 完了と、その後の `401` 再確認が前提** |
| (g) `mitatedb-ctrl` の新規配備 | [監督] | **実施済み** ((g-1)〜(g-5)、および無資格 probe まで)。**(g-6) の有資格確認 [運用者] は未実施** |
| (h) data を `control_plane=enabled` へ | [監督] | **未実施。(g-6) の完了が前提 (Invariant 3)** |
| (i) 適用後検証 | 両者 | **未実施** |

**(g) を (c)〜(f) より先に完了させたのは順序違反ではない。**(g) は data の
traffic に一切触れないので、(b) の完了を待たずに進められる独立な作業である。
本書が固定している依存は「(b) → (f)」「(g-6) → (h)」の 2 本であり、どちらも
守られている。

> **(g) と (h) は切り離してよい。**`mitatedb-ctrl` を配備せず (f) で止める
> 選択は、契約にも設計にも完全に適合する — `control_plane: unavailable` の
> 宣言はその配備について真であり、`surfaces.control` は正しく省略される
> (契約 1.6.0 の `surfaces` 記述、Invariant 3)。その場合フェーズ6 の
> `surfaces.data` と型付き catalog は (f) の時点で完成しており、
> `audit_query` と in-band control plane だけが従来どおり無い。

### (a) [監督] 1.6.0 イメージを 2 本ビルドする — **[実施済み 2026-09-05]**

> **実測。** Cloud Build `cf15f107-9c67-4e08-8bc2-bbcf4e74fc74` が **43 秒**で
> 成功し、2 本の tag が push された:
> `mitatedb-api:1.6.0-data` (`sha256:5fb2d292…`) と
> `mitatedb-api:1.6.0-control` (`sha256:ac626232…`)。
> **ビルドソースは main `4e48d1a` の `git archive`** である — 作業ツリーの
> 未追跡ファイル (scratchpad の一時 yaml を含む) がコンテキストに混ざらない
> ことを、この作り方自体が保証している。digest の完全形は §7.2 に記録する。

`cloud-run-cloud-sql.md` §6 冒頭が正本。**ビルドコンテキストはリポジトリ
ルート**であり、Dockerfile を明示的に指す (`docker/Dockerfile` の `COPY` は
リポジトリルート相対に書かれている)。`SERVICE` は **build-time ARG** なので、
`gcloud builds submit --tag` (build-arg を渡せない) ではなく **config ファイル**
を使う。以下を**scratchpad の一時ファイル**として置く (リポジトリには
コミットしない):

```yaml
# cloudbuild-160.yaml (一時ファイル。リポジトリに置かない)
steps:
  - name: gcr.io/cloud-builders/docker
    args: ['build', '-f', 'MitateDB-api/docker/Dockerfile',
           '--build-arg', 'SERVICE=data',
           '-t', '<REGION>-docker.pkg.dev/<GCP_PROJECT_ID>/cloud-run-source-deploy/mitatedb-api:1.6.0-data',
           '.']
  - name: gcr.io/cloud-builders/docker
    args: ['build', '-f', 'MitateDB-api/docker/Dockerfile',
           '--build-arg', 'SERVICE=control',
           '-t', '<REGION>-docker.pkg.dev/<GCP_PROJECT_ID>/cloud-run-source-deploy/mitatedb-api:1.6.0-control',
           '.']
images:
  - '<REGION>-docker.pkg.dev/<GCP_PROJECT_ID>/cloud-run-source-deploy/mitatedb-api:1.6.0-data'
  - '<REGION>-docker.pkg.dev/<GCP_PROJECT_ID>/cloud-run-source-deploy/mitatedb-api:1.6.0-control'
```

```sh
gcloud builds submit --project=<GCP_PROJECT_ID> --region=<REGION> \
  --config=<scratchpad>/cloudbuild-160.yaml .
```

- **リポジトリルートから**実行する (`.` がコンテキスト)。
- 秘密はイメージに焼き込まれない (Dockerfile の設計そのもの)。
- 契約 JSON は wheel の package data として同梱されるので、runtime stage への
  `COPY spec/...` は無い (WP-0 の D-4(b))。
- **完了したら 2 本の image digest を控える** (§7 の記録表)。以後の
  `gcloud run deploy` は tag ではなく **digest で指定してもよい** — tag は
  上書きされうるが digest は動かない。
- 代替: `SERVICE` は runtime env でも上書きできるので、1 本だけビルドして
  ctrl 側に `--set-env-vars SERVICE=control` を足す形も動く。**本書は
  runbook §6 の既定 (2 tag 変種) を採る** — 「実行時トグルを取り違えない」
  ことがその既定の理由である。

### (b) [運用者] migration `0005` → `0006` を適用する — **[未実施 / 最優先]**

> **このステップが (f) の前提であることは、(c) の検証で実測された。**
> 1.6.0 の data は request 時に application DB の宣言型 registry
> `_mdb_field_types` を読む (`cell.py:533` の `all_field_types`) ので、
> **`0006` 未適用のデータベースでは read も write も `StorageConfigurationError`
> になる** (§0.1 の 3(iii) が文章で述べていたことが、実際の応答として観測された)。
> 詳細は (c) の検証結果を読むこと。**(b) を飛ばして (f) に進んではならない。**

**順序は `0005` → `0006`。**`0005` は platform DB に 1 回、`0006` は
**application DB ごとに 1 回** (現況は `mitate` の 1 つ)。

**(b-1) `0005` (フェーズ4、`cloud-run-cloud-sql.md` §3.2b):**

```sh
psql "host=127.0.0.1 port=5432 dbname=mitatedb_platform user=mitatedbsvc_provision password=$MITATEDBSVC_PROVISION_PASSWORD" \
  -f MitateDB-api/migrations/0005_application_audit.sql
```

冪等 (`CREATE TABLE IF NOT EXISTS` + 条件付き role 作成 + 冪等 `GRANT`)。
これは `mitatedb_registry.application_audit` (`mitatedbsvc_api` は INSERT
のみ) と `mitatedbsvc_auditreader` role (**`PASSWORD NULL`**、両 audit
テーブルに SELECT のみ) を作る。**reader のパスワード設定は裁定 F 次第**で
あり、§3.2b の帯域外 `ALTER ROLE` を一度だけ行う (値は Secret Manager
`mitatedb-audit-dsn` にのみ置く。この secret は現況に無いので新設する)。

> **裁定 F = 配線しない (2026-09-05)。**したがって **`ALTER ROLE` は行わず、
> `mitatedb-audit-dsn` も新設しない。**`mitatedbsvc_auditreader` は
> `PASSWORD NULL` のまま作られたままにする — **role が存在すること自体は
> 無害であり、パスワードが無い以上その role で接続できる者はいない。**
> `0005` 自体は F に関わらず必須である (書き手の INSERT 先である
> `application_audit` を作るのはこの migration である)。

**(b-2) `0006` (フェーズ6、§3.4a):**

```sh
psql "host=127.0.0.1 port=5432 dbname=mitatedb_platform user=mitatedbsvc_provision password=$MITATEDBSVC_PROVISION_PASSWORD" \
  -v app_id='mitate' \
  -f MitateDB-api/migrations/0006_declared_field_types_upgrade.sql
```

`mitatedb_platform` へ接続して起動し、script 自身が `\c` で application DB
へ移る。冪等 (`CREATE TABLE IF NOT EXISTS` + `ON CONFLICT DO NOTHING`) で
あり、**手で直した行を二度と上書きしない**。

**(b-3) 適用の確認と backfill 行数の突合** — §1.4 の 2 本のクエリを
**application DB で**もう一度実行し、**2 つの数が一致する**ことを確かめる:

```sql
SELECT count(*) FROM public._mdb_field_types;                         -- (X)
SELECT count(*) FROM information_schema.columns
 WHERE table_schema = 'public'
   AND table_name NOT IN ('_mdb_schema_revision', '_mdb_field_types'); -- (Y)
```

**(X) = (Y) が合格条件。**両方を §7 の記録表へ書く。

**(b-4) backfill の既知の限界を、この場で潰す (§3.4a の KNOWN LIMITATION、
設計 §11 L6-16)。**backfill は**物理型からの逆写像**であり、次の写像を使う:

| 物理型 | backfill される宣言型 |
|---|---|
| `bigint` | `integer` |
| `double precision` | `number` |
| `integer` | **`boolean`** |
| `text` | **`string`** |

**危険は 2 方向にある。**

- **物理 `text`** は曖昧である。1.6.0 以前の `add_field` は `object` /
  `array` を受理し、どちらも物理 `text` へ落ちていた。PostgreSQL の catalog
  からは元の宣言を復元できないので、**すべて `string` として backfill される**。
  実際に `object` / `array` として使っていた列があるなら、**この時点で手で
  直す** (直さないと、その列は `string` として検証されるようになる):
  ```sql
  UPDATE public._mdb_field_types SET declared_type = 'object'
    WHERE entity = '<entity>' AND field = '<field>';
  ```
- **物理 `integer`** は `boolean` として backfill される。この peer では
  契約 `integer` は物理 `bigint` へ、契約 `boolean` は物理 `integer` へ
  落ちるので、通常この写像で正しい。**それでも、backfill された
  `declared_type = 'boolean'` の行を全数目視し、`mitate-application` が
  その列に実際に何を書いているかと突き合わせる**こと — γ により、この列へ
  `0` / `1` を書くと (f) の後は `VALIDATION_FAILED` になる。
  ```sql
  SELECT entity, field, declared_type FROM public._mdb_field_types ORDER BY 1, 2;
  ```

**この目視は (f) の前に済ませる。**(f) の後では、誤った宣言型が実際の
拒否として現れる。

### (c) [監督] `mitatedb-data` の 1.6.0 revision を `--no-traffic` で作る — **[実施済み 2026-09-05]**

> **実測。** revision **`mitatedb-data-00004-wh4`** を `1.6.0-data` イメージで
> `--no-traffic --tag=v160` で作成した。
> - **traffic は `mitatedb-data-00003-6vj` (`phase-b` = フェーズ4 前のコード) が
>   100% のままである。**`mitate-application` が見ているのは依然として旧コード。
> - tag URL の実測: `https://v160---mitatedb-data-<RUN_HASH>-an.a.run.app`
>   (旧形式。決定的 URL 形式ではなくこちらが払い出された)。
> - env には下のコマンドどおり `MITATEDB_DATA_BASE_URL` /
>   `MITATEDB_CONTROL_BASE_URL` の 2 本を置き、
>   `MITATEDB_CONTROL_PLANE_STATUS=unavailable` を維持した。
> - **`MITATEDB_DATA_BASE_URL` の形検査を通って起動した**こと自体が、1.6.0 の
>   `surfaces` 設定が最低限成立している証拠である ((c) の 4)。

**旧 revision は traffic を持ったまま動き続ける。**新 revision は tag 付き
URL でだけ到達でき、traffic の切替は (f) で行う。

```sh
gcloud run deploy mitatedb-data \
  --project=<GCP_PROJECT_ID> --region=<REGION> \
  --image=<REGION>-docker.pkg.dev/<GCP_PROJECT_ID>/cloud-run-source-deploy/mitatedb-api:1.6.0-data \
  --add-cloudsql-instances=<GCP_PROJECT_ID>:<REGION>:mitatedb-platform \
  --service-account=mitatedb-data-runtime@<GCP_PROJECT_ID>.iam.gserviceaccount.com \
  --max-instances=1 \
  --no-traffic --tag=v160 \
  --set-secrets=MITATEDB_CREDENTIAL_PEPPER=mitatedb-credential-pepper:latest,MITATEDB_PLATFORM_DSN=mitatedb-platform-dsn:latest,MITATEDB_APP_MITATE_RUNTIME_DSN=mitatedb-app-mitate-runtime-dsn:latest,MITATEDB_APP_MITATE_DEVELOPER_DSN=mitatedb-app-mitate-developer-dsn:latest \
  --set-env-vars=MITATEDB_SERVE_APPS=mitate,MITATEDB_CONTROL_PLANE_STATUS=unavailable,MITATEDB_DATA_BASE_URL=https://mitatedb-data-<GCP_PROJECT_NUMBER>.<REGION>.run.app/v1,MITATEDB_CONTROL_BASE_URL=https://mitatedb-ctrl-<GCP_PROJECT_NUMBER>.<REGION>.run.app/control/v1
```

落としてはならない点:

1. **`--set-secrets` / `--set-env-vars` は既存の集合を置換する。**上の 1 本は
   §0.1 で実測した現況の全 4 secret と全 env を明示的に書き直したものである。
   **`--update-*` で継ぎ足すのではなく `--set-*` で全体を宣言する**のは、
   「今この revision が持っている環境」を 1 箇所で読めるようにするためである。
   実行後に `gcloud run services describe mitatedb-data --format=yaml` で
   実際の集合を読み、上のリストと突合する。
2. **`MITATEDB_CONTROL_PLANE_STATUS` は `unavailable` のまま**にする。
   反転は (h)、`mitatedb-ctrl` の到達確認の後である (Invariant 3)。
3. **`MITATEDB_CONTROL_BASE_URL` はここでは読まれない。**
   `config.FoundationConfig.from_env` は `control_plane_status != "unavailable"`
   のときにだけこの変数を parse・検証する。したがって**綴りを誤っても
   (c) では落ちず、(h) で初めて起動失敗として現れる。**先に置いておくのは
   (h) の変更を 1 変数だけにするためであり、検証を前倒しできるからではない。
4. **`MITATEDB_DATA_BASE_URL` は起動時に形だけ検査される** — 絶対 URL、
   `/v1` で終わる、末尾スラッシュ無し、`/control/v1` で終わらない。不正なら
   変数名を名指しして起動に失敗する。到達性は検査されない (**配備者の表明**)。
5. **`mitatedb-ctrl` の URL は「未配備のサービスについての予測値」である。**
   Cloud Run の決定的 URL 形式 (`<service>-<project number>.<region>.run.app`)
   から書いているが、**(g) の配備後に必ず実測で突合する**:
   ```sh
   gcloud run services describe mitatedb-ctrl --project=<GCP_PROJECT_ID> \
     --region=<REGION> --format='value(status.url)'
   ```
   食い違ったら、**data と ctrl の両方**の `MITATEDB_CONTROL_BASE_URL` を
   実測値へ直す。両文書が同じ `surfaces` を返すことは契約 1.6.0 の無条件
   義務であり、**どちらのプロセスも相手の値を検証できない**。

**(c) の検証 [監督]** — credential 不要:

```sh
curl -s -o /dev/null -w '%{http_code} %{content_type}\n' \
  https://v160---mitatedb-data-<GCP_PROJECT_NUMBER>.<REGION>.run.app/v1/capabilities
```

- 合格: **`401` + `application/problem+json`**。これで「revision が立ち、
  serving し、アプリの認証経路が到達可能で fail-closed である」ことが同時に
  分かる (DEPLOYMENT_RUNBOOK §2 step 6 の 1 と同型の検査)。
- **`403` が返り、本体が HTML / プレーンテキストなら、それは Cloud Run の
  front end が IAM で拒否したのであって、アプリの答えではない** (§1.2 で
  読んだ invoker 設定と突き合わせる)。その場合は ID トークンを
  `X-Serverless-Authorization` に載せて叩く (§6.3。`Authorization` に載せると
  アプリはそれを bearer と読んで `AUTH_INVALID` を返す — どちらにせよ
  `401` + `problem+json` なので、**合格条件としては同じ**である)。
- `gcloud run revisions list --service=mitatedb-data` で新 revision が
  `Ready` かつ traffic 0% であること。

**(c) の検証の実測結果 (2026-09-05) — 合格していない。読み飛ばさないこと。**

監督は `gcloud run services proxy --tag=v160` 経由で、credential 無しで
`GET /v1/capabilities` を叩いた。返ったのは:

- **`503` `SERVICE_UNAVAILABLE`** (期待は `401` + `application/problem+json`)。
- **同条件の `mitatedb-ctrl` は `401` `AUTH_REQUIRED` を返している** ((g) を
  読むこと)。したがってこれは proxy の問題でも Cloud Run の front end の問題でも
  なく、**data のアプリケーションが答えた 503 である。**

**最有力の説明は「(b) が未実施であること」である。**1.6.0 の data は request
処理の中で application DB の宣言型 registry `_mdb_field_types` を読む
(`MitateDB-api/src/mitatedb_api/cell.py:533`、`all_field_types`)。
**`0006` 未適用ならこのテーブルが無く、`StorageConfigurationError` → `503`**
になる。`0005` 未適用による `application_audit` の欠落も同じ症状を作りうる
候補であり、**どちらであるかは (b) を当てれば区別する必要がなくなる** (どちらも
(b) で解消するため)。**推測はここまでであり、原因を断定していない。**

**したがって (c) の合格判定は保留であり、次の 2 つが確定した:**

1. **(b) の `0005` + `0006` 適用は (f) の前提である** — 文章上の前提ではなく、
   実測で裏付けられた前提になった。
2. **(b) の完了後、同じ probe をもう一度打ち、`401` + `application/problem+json`
   が返ることを確かめる。これを (f) の必須の前提条件に加える** (§7.2 の記録表に
   「(b) 後の再 probe」の行を足した)。**`503` のまま traffic を切り替えては
   ならない** — 切り替えた瞬間に `mitate-application` の全 request が 503 になる。

**副次的な注意。**この probe は `gcloud run services proxy` 経由で行ったので、
`mitatedb-data` の invoker 設定 (`--allow-unauthenticated` の有無) は**まだ
読めていない** (§0.1 の表)。(f) の前に §1.2 の `get-iam-policy` を実行して
埋めること — 2026-09-05 に運用者アカウントへ `roles/run.invoker` を足している
ので、**「元から入っていた principal」と「今回足したもの」を区別して読む。**

### (d) [運用者] credential の扱いを決め、必要なら再発行する — **[裁定 E-2 = 再発行しない]**

> **決定済み (2026-09-05)。****rotate は実行しない。**MitateDB の受理側は
> 1.6.0 以前から locator 形であり、flip は credential を失効させない
> (§0.1 の 5)。**rotate は不可逆**であって、必要でない不可逆操作は行わない。
> **このステップに残る作業は下の「事実の確定」だけである** — 以下の rotate
> 手順は、**将来 rotate が必要になったときのために残してある参照であり、
> 今回は実行しない。**

**まず事実を確定する (§0.1 の 5)。**MitateDB の受理側は 1.6.0 以前から
locator 形であり、**flip は credential を失効させない**。したがって:

- **`mitate-application` が今日 `mitatedb-data` に対して認証を通っているなら、
  その値は既に `<credential_id>.<secret>` の形であり、(f) の後もそのまま通る。**
  再発行は**任意**である (裁定 E-2)。
- **今日認証が通っていないなら**、`mitatedb-app-mitate-runtime-credential` の
  値は raw secret であり、`mitate-application` 側が実装知識で合成しているか、
  あるいは現に壊れている。**どちらであるかを (f) の前に確定する** — 前者なら
  その合成は契約 1.6.0 (D-1) が明示的に禁じる行為なので、再発行して合成を
  取り除くのが正しい是正である。

> **裁定 E-2 は「しない」だが、上の 2 択の確定は残る。**「今日認証が通っている」
> ことを確認できないまま (f) を通すと、**flip の後に認証が落ちたとき、原因が
> 1.6.0 なのか元から壊れていたのかを切り分けられない。**確認は運用者にしか
> できない (credential が要る)。**旧 revision に対して行うので、(f) の前に
> 実施できる。**結果は §7.2 に書く。

再発行する場合 (裁定 E-2 = する。**今回は該当しない**)、**§7 の break-glass CLI を、main `4e48d1a`
のソースツリーから、Cloud SQL Auth Proxy 経由で実行する** (どちらの Cloud Run
サービス経由でもない)。**旧ツリーで実行すると印字されるのが旧形式になる。**

```sh
export PYTHONPATH=MitateDB-api/src
export MITATEDB_CONTROLPLANE_DSN="host=127.0.0.1 port=5432 dbname=mitatedb_platform user=mitatedbsvc_controlplane password=..."
export MITATEDB_CREDENTIAL_PEPPER=...            # 値は Secret Manager から
export MITATEDB_CONTROL_CREDENTIAL_PEPPER=...
export MITATEDB_CONTROL_CREDENTIAL_ID=...        # 運用者の control credential
export MITATEDB_CONTROL_CREDENTIAL_SECRET=...    # ← 下の注記を読むこと

# 1) control credential を先に (必要なら)
python -m mitatedb_api.ops rotate-credential <control credential_id>
# 2) application credential (runtime / developer をそれぞれ)
python -m mitatedb_api.ops rotate-credential <credential_id>
```

順序と注意:

1. **`MITATEDB_CONTROL_CREDENTIAL_SECRET` には「保存済みの composed bearer」を
   入れる** (`ops.py` の該当 docstring、§7 の「the operator's own live,
   already-rotated control credential」)。手元に id と secret が別々の形でしか
   無い場合、この帯域外 CLI の利用に限り `<credential_id>.<secret>` を組み立てて
   与える — **これはこの peer が 1.6.0 以前から要求してきた wire 形と同一**で
   あり (§6.3)、契約 D-1 が禁じる「クライアントによる合成」とは別の、運用者の
   帯域外操作である。**この点は監督の確認を得てから実行する。**
2. `mitatedb-control-credential` の version 1 が **bootstrap 直後
   (`must_rotate=true`) のまま**なら、それは `GET /control/v1/capabilities` と
   **自分自身の rotate** しかできない。**まず自分を rotate して生きた
   credential にし**、その新しい値で application credential を rotate する。
   **二度目の `bootstrap` は決して実行しない** — 紛失・漏洩・ロックアウトからの
   回復は `reset` である (§8、`CONTROL_PLANE_COMPROMISE_PLAYBOOK.md`)。
3. 印字は `credential_id:` と `secret:` の 2 行で、**`secret:` が完全な
   bearer である。丸ごと写す。分割しない。**一度しか表示されない。
4. **rotate は不可逆である。**実行した瞬間に旧 secret は失効する。
   **(e) の準備が整ってから実行する。**
5. 新しい値は **Secret Manager の新 version** として追加する (既存 version は
   無効化しない — ただし §6 のとおり、旧 version を戻しても認証は戻らない)。
   ```sh
   # 値は運用者の手元から標準入力で渡す。コマンドラインにも履歴にも残さない。
   gcloud secrets versions add mitatedb-app-mitate-runtime-credential \
     --project=<GCP_PROJECT_ID> --data-file=-
   ```
6. **この CLI は `ControlPlaneService` を通るので `control_audit` に行を書く。**
   (b-1) の `0005` が適用済みであることが前提である。

### (e) [運用者] `mitate-application` を新しい値で再デプロイする — **[実施しない]**

> **(d) で新 version を作らないので、credential のための再デプロイは無い。**
> **ただし下の β / γ は消えない** — 裁定 E は「窓を設けない」であり、
> 「β / γ が無い」ではない。**扱いが変わっただけである**: 事前の release
> ではなく、**(f) の直後に `mitate-application` の実挙動を確認し、必要なら
> その時点で直す。**§4-5 の確認項目はそのまま残る。

(d) で新 version を作った場合のみ。`mitate-application` が
`mitatedb-app-mitate-runtime-credential` を `:latest` で参照しているなら
**再デプロイ (または再起動) が必要**である — Cloud Run は既存 revision の
secret を実行中に差し替えない。特定 version 番号で参照しているなら、参照を
新 version へ更新して再デプロイする。

**あわせて、挙動変更 β / γ への対応を同じ release に載せる** (§6.4、裁定 E):

- **β**: `json` / `object` / `array` と宣言された field の読み出しが **JSON 値**
  で返る。`json.loads()` を二度目に呼んでいるコードは `TypeError` になる。
- **γ**: 宣言 `boolean` の field へ `0` / `1` を書くと `VALIDATION_FAILED`。
  `false` / `true` へ変える。
- **α**: 型を宣言せずに作られる新規 field の既定が `text` → `json`。**受理域が
  広がるだけ**なので、既存の書込みは通り続ける。

### (f) [監督] traffic を新 revision へ 100% 切り替える (切替窓 E) — **[未実施]**

> **裁定 E = 即時 (窓を設けない)。**したがってここでは「窓を待つ」作業は無い。
> **代わりに、実行前に満たさなければならない前提が 3 つある** — うち 2 つは
> 2026-09-05 の実測で足された:
>
> 1. **(b) の `0005` + `0006` が適用済みであること。**
> 2. **(b) の後に無資格 probe を再実行し、`401` +
>    `application/problem+json` が返ること** ((c) の検証。**`503` のままなら
>    切り替えない**)。
> 3. **(d) の「今日認証が通っているか」の確認が済んでいること** (切替後の
>    切り分けを可能にするため)。
>
> **3 つが揃っていないなら (f) を実行しない。**戻す手段は §6.1 のとおり
> `--to-revisions=mitatedb-data-00003-6vj=100` であり、credential 操作は要らない
> (§6.3)。

```sh
gcloud run services update-traffic mitatedb-data \
  --project=<GCP_PROJECT_ID> --region=<REGION> --to-latest
gcloud run services describe mitatedb-data --project=<GCP_PROJECT_ID> \
  --region=<REGION> --format='value(status.traffic)'
```

**この瞬間から `mitate-application` は 1.6.0 のコードを見る。**切替の直後に
運用者が `mitate-application` 側の実挙動 (読み書き) を確認する。
**戻す判断は §6。**

### (g) [監督] `mitatedb-ctrl` を新規配備する — **[実施済み 2026-09-05 / (g-6) のみ未実施]**

> **実測。**(g-1)〜(g-5) と、監督にできる範囲の到達確認まで完了した。
>
> - **(g-1) SA**: `mitatedb-ctrl-runtime@<GCP_PROJECT_ID>.iam.gserviceaccount.com`
>   を作成した。
> - **(g-2) `roles/cloudsql.client`**: data / ctrl の**両方**の SA に付与済み。
>   **ctrl 側は 1 回目の付与が無音で失敗し、再実行で成功した** — 新規作成した
>   service account の伝播遅延である。**エラーが出ないので気付きにくい。**
>   付与直後は `get-iam-policy` で実際に binding が載っているかを読むこと。
> - **(g-2 追加) `roles/secretmanager.secretAccessor`**: ctrl SA に対し、
>   `mitatedb-credential-pepper` / `mitatedb-control-credential-pepper` /
>   `mitatedb-controlplane-dsn` の **3 secret へ個別に**付与した
>   (プロジェクト全体へではない)。**この 3 本は下の `--set-secrets` が参照する
>   ものと一致する。**元の手順にこの step が無かったのは漏れであり、
>   **無いと revision は起動できない。**
> - **(g-3) 配備**: revision **`mitatedb-ctrl-00001-m8s`**
>   (`1.6.0-control`、`--max-instances=1`、`--no-allow-unauthenticated`、
>   Cloud SQL 接続あり、**`MITATEDB_AUDIT_DSN` は付けていない** = 裁定 F)。
>   **起動ログにエラーは無い。**
> - **(g-4) invoker**: `user:<OPERATOR_ACCOUNT_EMAIL>` (§0.2 の表外事項)。
> - **(g-5) URL**: `status.url` の実測は
>   **`https://mitatedb-ctrl-<RUN_HASH>-an.a.run.app`** (旧形式) だが、
>   **決定的 URL `https://mitatedb-ctrl-<GCP_PROJECT_NUMBER>.<REGION>.run.app` も
>   同一サービスへ到達する** (未認証 `curl` が `403` を返した = Cloud Run の
>   front end が IAM で拒否した = **ルーティングは成立している**)。
>   したがって `MITATEDB_CONTROL_BASE_URL` に置いた決定的 URL は**実際に
>   到達する URL であり、直す必要は無い** ((g-5) の「食い違ったら直す」は
>   発動しない)。**この判断の根拠は「403 はアプリではなく front end の応答で
>   ある」ことである** — 到達しない URL なら 404 になる。
> - **監督にできる到達確認**: `gcloud run services proxy` 経由で credential
>   無しの `GET /control/v1/capabilities` を叩き、**`401` `AUTH_REQUIRED`** を
>   得た。**アプリ層まで起動しており、base URL の形検査も通っている。**
>   (c) の data が同条件で `503` を返すのと対照的であり、**(c) の 503 が
>   「1.6.0 のイメージそのものの問題」ではないことの傍証でもある。**
> - **(g-6) は未実施** — control credential を要するので運用者が行う。
>   **(h) はこれが済むまで実行できない (Invariant 3)。**

正本は `cloud-run-cloud-sql.md` §6 冒頭 (IAM 注記) と §6.2。
**§0.1 の現況記録 (control サービス無し) を、runbook §0 の完全形へ寄せる作業**
でもある。

**(g-1) ctrl 用の runtime service account** — 現況には
`mitatedb-data-runtime` しか無い:

```sh
gcloud iam service-accounts create mitatedb-ctrl-runtime \
  --project=<GCP_PROJECT_ID> --display-name='MitateDB control service runtime'
```

**(g-2) `roles/cloudsql.client` を付与する。**これが無いと Cloud SQL
コネクタが `cloudsql.instances.get` の **403 でコンテナ起動前に落ちる**
(2026-09-01 の実測所見。PostgreSQL の権限エラーとは別物):

```sh
gcloud projects add-iam-policy-binding <GCP_PROJECT_ID> \
  --member=serviceAccount:mitatedb-ctrl-runtime@<GCP_PROJECT_ID>.iam.gserviceaccount.com \
  --role=roles/cloudsql.client
```

`mitatedb-data-runtime` 側の同 binding は既に効いている (現に接続できている)
が、明示的に確認しておく。

**付与が無音で失敗しうる (2026-09-05 の実測)。**作りたての service account を
member に指定すると、**エラーを返さずに binding が載らないことがある。**
付与の直後に `gcloud projects get-iam-policy <GCP_PROJECT_ID>` で実際に載って
いるかを読み、載っていなければ**同じコマンドをもう一度実行する。**

**(g-2b) `roles/secretmanager.secretAccessor` を、参照する secret へ個別に
付与する (2026-09-05 に補った step)。**これが無いと revision は secret を
読めず起動できない。**プロジェクト全体へ付けない** — ctrl が読む 3 本だけに
付ける:

```sh
for s in mitatedb-credential-pepper mitatedb-control-credential-pepper mitatedb-controlplane-dsn; do
  gcloud secrets add-iam-policy-binding "$s" --project=<GCP_PROJECT_ID> \
    --member=serviceAccount:mitatedb-ctrl-runtime@<GCP_PROJECT_ID>.iam.gserviceaccount.com \
    --role=roles/secretmanager.secretAccessor
done
```

**この 3 本は (g-3) の `--set-secrets` が参照するものと一致していなければ
ならない。**裁定 F を「配線する」に変えるなら `mitatedb-audit-dsn` にも同じ
binding が要る (今回は不要)。

**(g-3) 配備:**

```sh
gcloud run deploy mitatedb-ctrl \
  --project=<GCP_PROJECT_ID> --region=<REGION> \
  --image=<REGION>-docker.pkg.dev/<GCP_PROJECT_ID>/cloud-run-source-deploy/mitatedb-api:1.6.0-control \
  --add-cloudsql-instances=<GCP_PROJECT_ID>:<REGION>:mitatedb-platform \
  --service-account=mitatedb-ctrl-runtime@<GCP_PROJECT_ID>.iam.gserviceaccount.com \
  --no-allow-unauthenticated \
  --max-instances=1 \
  --set-secrets=MITATEDB_CREDENTIAL_PEPPER=mitatedb-credential-pepper:latest,MITATEDB_CONTROL_CREDENTIAL_PEPPER=mitatedb-control-credential-pepper:latest,MITATEDB_CONTROLPLANE_DSN=mitatedb-controlplane-dsn:latest \
  --set-env-vars=MITATEDB_DATA_BASE_URL=https://mitatedb-data-<GCP_PROJECT_NUMBER>.<REGION>.run.app/v1,MITATEDB_CONTROL_BASE_URL=https://mitatedb-ctrl-<GCP_PROJECT_NUMBER>.<REGION>.run.app/control/v1
```

- **`--max-instances=1` は規模の都合ではなく正しさの要件である。**
  `control_requests_per_minute` も `audit_requests_per_minute` もプロセス内
  カウンタなので、2 インスタンス以上では `limit_enforcement: enforced` の
  宣言が偽になる (Invariant 1、§6.2)。**この flag を外すことは容量変更では
  なく、偽の宣言への静かな後退である。**
- **`--no-allow-unauthenticated`** を落とさない。
- **`MITATEDB_AUDIT_DSN` は裁定 F 次第**である。配線するなら
  `--set-secrets` に `MITATEDB_AUDIT_DSN=mitatedb-audit-dsn:latest` を足す
  (この secret は (b-1) で新設したもの)。**含めなければ `audit_query` は
  `unavailable` 宣言のまま**であり、それも正当な選択である。
  **→ 裁定 F = 配線しない。上のコマンドどおり、この変数は置いていない
  (2026-09-05 の実配備もそうなっている)。**したがって §4-6 の合格形は
  `audit_query.status == "unavailable"` + 両ルートが認証後
  `CAPABILITY_UNSUPPORTED` である。
- **2 つの base URL は §6.1 (= (c)) と同じ値**でなければならない。独立に
  選ばない。
- 裁定 C を既定から動かすなら、`MITATEDB_AUDIT_STATEMENT_TIMEOUT_MS` /
  `MITATEDB_AUDIT_IDLE_TIMEOUT_MS` を **data と ctrl の両方に同一値で**置く。

**(g-4) invoker binding — 運用者だけに。**`allUsers` にも、
`mitate-application` の service account にもしない:

```sh
gcloud run services add-iam-policy-binding mitatedb-ctrl \
  --project=<GCP_PROJECT_ID> --region=<REGION> \
  --member=<運用者グループ / 運用者アカウント。§0.2 の表外事項> \
  --role=roles/run.invoker
```

**(g-5) URL の実測と突合 (必須)** — (c) の 5 のとおり:

```sh
gcloud run services describe mitatedb-ctrl --project=<GCP_PROJECT_ID> \
  --region=<REGION> --format='value(status.url)'
```

`https://mitatedb-ctrl-<GCP_PROJECT_NUMBER>.<REGION>.run.app` と一致するか。
違えば **data と ctrl の両方**の `MITATEDB_CONTROL_BASE_URL` を実測値へ直し、
両方を再デプロイする (data 側は (h) の変更と 1 回にまとめる)。

> **2026-09-05 の実測: `status.url` は
> `https://mitatedb-ctrl-<RUN_HASH>-an.a.run.app` (旧形式) で、文字列としては
> 一致しなかった。しかし直していない。**理由は、決定的 URL
> `https://mitatedb-ctrl-<GCP_PROJECT_NUMBER>.<REGION>.run.app` へ未認証で
> `curl` すると **`403`** が返る = **Cloud Run の front end まで到達しており、
> IAM で拒否されている**からである (到達しない名前なら `403` にはならない)。
> **`surfaces.control.base_url` に求められるのは「その配備に実際に到達する
> URL であること」**であり (§4-1)、両形式とも同一サービスに到達する以上、
> 決定的 URL を宣言することは正しい。**この判断は §7.2 に記録する。**
> **(g-6) で有資格の `GET /control/v1/capabilities` が決定的 URL 経由でも
> `200` を返すことを確かめれば、この判断は実測で閉じる。**

**(g-6) 到達確認 [運用者] — [未実施。(h) の前提]** — control credential が
要るので運用者が行う。**監督は同じ経路で無資格の `401` `AUTH_REQUIRED` まで
確認済みである** (アプリ層が起動していることの証拠にはなるが、**配備成功の
証拠ではない** — 下の注記のとおり)。
§6.3 の 2 経路のうち、**対話的な運用者は `gcloud run services proxy` が既定**
である:

```sh
gcloud run services proxy mitatedb-ctrl --project=<GCP_PROJECT_ID> \
  --region=<REGION> --port=8443
curl -s -H "Authorization: Bearer <control credential の完全な secret>" \
  http://127.0.0.1:8443/control/v1/capabilities
```

合格: `200 application/json`、`capabilities.contract_version == "1.6.0"`。
**`GET /control/v1/capabilities` に無資格版は無い** — `Authorization` を
省けば `401` であり、それは配備成功の証拠ではない。

### (h) [監督] data を `MITATEDB_CONTROL_PLANE_STATUS=enabled` へ — **[未実施]**

> **(g-6) の完了が前提である。**加えて、(h) は data の revision を作り直すので
> **(b) と (f) が済んだ後に行う**のが自然である (未適用のまま `enabled` の
> revision を作ると、(c) と同じ 503 を新しい revision でもう一度作るだけになる)。

**(g-6) で ctrl が実際に到達可能だと確認できてから**行う。順序は
**Invariant 3** の要求そのものである: data サービスは control の到達性を
自分で確かめられないので、この env は**運用者の表明**である。到達不能なまま
`enabled` にすると、`GET /v1/capabilities` が「control_plane: enabled」と
主張しながら誰も listen していない、という宣言と実挙動の不一致になる。

```sh
gcloud run deploy mitatedb-data \
  --project=<GCP_PROJECT_ID> --region=<REGION> \
  --image=<REGION>-docker.pkg.dev/<GCP_PROJECT_ID>/cloud-run-source-deploy/mitatedb-api:1.6.0-data \
  --update-env-vars=MITATEDB_CONTROL_PLANE_STATUS=enabled
```

- **ここで初めて `MITATEDB_CONTROL_BASE_URL` が読まれ、形が検査される**
  ((c) の 3)。綴りを誤っていれば**この deploy が起動失敗になる** — 変数名を
  名指しする起動時例外なので、`gcloud run services logs read mitatedb-ctrl`
  ではなく `mitatedb-data` の revision ログを読む。
- この deploy は新 revision を作る。`--no-traffic` を付けていないので
  traffic は自動で新 revision へ移る。窓を切りたければ (c)(f) と同じ
  2 段構えにしてよい。
- **逆向き — ctrl を止める / undeploy する / scale-to-zero する — なら、
  同じ変更の中で `unavailable` へ戻す** (Invariant 3、§8)。

### (i) 適用後検証

**§4 の観測項目を、この peer について実行する。**

---

## 3. r2db-api (VPS) への適用 — [運用者] のみ / **これは「初回導入」である**

**本節は 2026-09-05 の SSH 実測 (§0.1 の 4-b) を受けて書き直した。**初版は
「フェーズ4 前のコードの入れ替え」として書いていたが、**入れ替える対象が
VPS に存在しない。**

- 稼働しているのは**既存本番の `r2db-api.service`** だけであり、これは
  **本リポジトリの実装ではない** (`/home/<VPS_USER>/r2-vps/apps/r2db-api`、
  uvicorn `127.0.0.1:<EXISTING_APP_PORT>`、nginx `db.example.invalid` 443)。
  `DEPLOYMENT_RUNBOOK.md` §0 が「同居する無関係な既存配備」と呼ぶものである。
- 本リポジトリの r2db-api (Stage 1) は**未導入**である — `/etc/r2dbsvc` も
  `/opt/r2dbsvc` も無く、`r2dbsvc-*` の unit も無く、8443 の listener も無い。

**したがって本節は「1.6.0 への差分適用」ではなく、`DEPLOYMENT_RUNBOOK.md`
§1〜§2 (Stage 1 の初回導入) + §7 (control プロセス) + migration `0001`〜`0007`
の初回適用を、最初から 1.6.0 のコードで一度に行う作業**である。

**この性格の違いが手順を 3 つ変える。**

1. **`POSTGRES_PROVISIONING_RUNBOOK.md` §12a (既存 credential の再発行) は
   実行しない。**§12a は「1.6.0 より前に発行された credential」だけを対象と
   する節であり、この配備にはその対象が 1 件も無い。**初回導入で発行する
   credential は、1.6.0 の CLI が最初から locator 形
   (`<credential_id>.<secret>`) で印字する。**再発行ではなく**初回発行**である。
2. **切替窓は存在しない。**Stage 1 の 8443 には production traffic が無く、
   既存本番の 443 は一切触らない (§0.2 の E は該当なし)。
3. **§4 の検証項目のうち 4-4 前段 (「旧 credential が `AUTH_INVALID`」) は
   実行できない** — 旧 credential が存在しないからである。**後段の
   「不正形の locator も `401`」は実行する** (SI-14 の後退検知であり、
   credential の新旧とは無関係)。

**監督は VPS で特権操作を実行できない。**SSH での読み取りはできたが、`sudo` が
パスワードを要求するためである。**本節は全ステップが [運用者] である。**

**既存本番に触れないことが、この節の最上位の制約である。**専用アカウント名
(`r2dbsvc`)、内部 port、8443 の listener、PostgreSQL のオブジェクト名接頭辞
(`r2dbsvc_`)、DB とその credential — **どれも既存配備のものと重ならないこと**を、
`DEPLOYMENT_RUNBOOK.md` §2 step 1 / step 3 / §6 の指示どおり**その場で確認して
から**選ぶ。既存本番が uvicorn を `127.0.0.1:<EXISTING_APP_PORT>` で動かしていることは実測済み
なので、**3010 は選ばない。**

### (a) 現況の再確認 (最初に必ず)

```sh
systemctl list-units --all 'r2dbsvc*'
id r2dbsvc
ls -la /etc/r2dbsvc /opt/r2dbsvc 2>&1
sudo ss -tlnp
python3 --version
```

**2026-09-05 に監督が読めたのは、`r2dbsvc-*` の unit が無いこと /
`/etc/r2dbsvc` と `/opt/r2dbsvc` が無いこと / 8443 の listener が無いこと /
`python3` が 3.12.3 であること、の 4 点である** (`id r2dbsvc` は未実測。
`ss` は非特権で読めるが、プロセス名まで見るには `sudo` が要る)。
期待する読み取り結果:

1. **`r2dbsvc-*` の unit が無いこと。**あれば本節の前提が変わっているので、
   何が入っているかを先に確定する (§0.1 の 4-b を更新する)。
2. **`r2dbsvc` アカウントが存在しないこと。**存在するなら、それが既存配備の
   ものでないかを確認する (`DEPLOYMENT_RUNBOOK.md` §2 step 1 の警告)。
3. **既存本番の listener を読むこと** — `3010` と 443 が見えるはずである。
   **選ぶ内部 port はこのどれとも重ねない。**8443 自体が空いていることも
   同じ出力で確認する。
4. **Python が 3.11 以上であること。**実測 3.12.3 は `r2db-api` の
   `requires-python = ">=3.11"` を満たす。**virtualenv はこれから作る。**
5. **PostgreSQL の現況** — 本リポジトリ用のクラスタ / データベース
   (`r2dbsvc_platform`) が既にあるか。無ければ (b) は `0001` から始まる。

### (b) PostgreSQL の初回構築 — migration `0001`〜`0007`

正本は `POSTGRES_PROVISIONING_RUNBOOK.md` **§5 (順序)** と
`DEPLOYMENT_RUNBOOK.md` **§1 の 1 (どれが要るかと、なぜ要るか)**。
**コマンドと算式は複製しない。**ここには順序と、初回導入ゆえの注意だけを書く。

**適用順 (各 migration の冒頭コメントが自分で宣言している順序である):**

| # | 何を作るか | 接続する role | 備考 |
|---|---|---|---|
| `0001` | `r2dbsvc_platform` データベース、`r2dbsvc_control` role | **cluster admin** | 冪等 (`pg_roles` / `pg_database` を見てから作る) |
| `0002` | `r2dbsvc_registry` schema と provisioning 関数 | `r2dbsvc_control` | 冪等 (`IF NOT EXISTS` / `CREATE OR REPLACE`) |
| `0005` | `credentials` テーブル、`applications.enabled`、読み取り専用 `r2dbsvc_api` role | `r2dbsvc_control` | `0002` の後。`0003`/`0004` との前後は問わない |
| `0006` | `control_credentials` / `control_audit` / `r2dbsvc_controlplane` role、`applications` の 2 状態化、**provisioning 関数の改訂** | `r2dbsvc_control` | `0002` と `0005` の後。**control プロセスを動かさない配備でも必須** (`DEPLOYMENT_RUNBOOK.md` §1 の 1) |
| `0007` | `application_audit` テーブル、`r2dbsvc_auditreader` role | `r2dbsvc_control` | **`0006` の後。**`R2DB_AUDIT_DSN` を配線しない配備でも必須 — 書き手の INSERT 先そのものである |
| `0003` | **アプリケーション 1 つ分**のデータベースと 2 つの login role | `r2dbsvc_control` | **onboarding するアプリケーションごとに 1 回。** |

**`0003` は `0006` の後に実行する。**`0003` は
`begin_provision_application` / `finish_provision_application` を呼ぶ script で
あり (その本体の `\gset` と最終行)、**`0006` はこの 2 関数を改訂する。**先に
`0003` を通すと旧版の関数で provision することになる。初回導入では順序を自由に
選べるのだから、**`0006` を先に当てる**のが正しい。

**`0003` は冪等ではない (設計上そうしてある)。**既に provision 済みの slug で
再実行すると raise する。**これは事故ではなく合図である。**

**`0004` はここでは実行しない** — deprovision (アプリケーション 1 つの
データベースと role を落とす) の script であり、導入手順の一部ではない。

初回導入ゆえの注意:

- **`0003` が生成する 2 つのパスワード (runtime / developer) は、その場で
  secret 管理へ移す。**この flow はどこにも復元可能な形で残さない
  (`POSTGRES_PROVISIONING_RUNBOOK.md` §5 の注記)。**本書には書かない。**
- **`0007` の `-v auditreader_password=` は、裁定 F = 配線しない なので
  使いどころが無い。**role は作られるが DSN は組まない。**再実行時に値が
  反映されない罠** (`pg_roles` ガードの下にある。DEPLOY_PHASE4 §2(b) の 1) は、
  初回適用では発現しないが、**将来 F を「配線する」に変えるときに効く** —
  そのときは `psql` の `\password` を使う。
- **CCR-13 の DOMAIN catch-up は不要である。**未 provision のクラスタに
  現行の `0003` を当てるので、`public._r2db_json_object` /
  `_r2db_json_array` は最初から作られる (§5 の CCR-13 注記が言う
  「pre-CCR-13 の `0003` で provision 済みのアプリケーション」が存在しない)。
- **クラスタは PostgreSQL 13 以上であること** (`gen_random_uuid()` に依存)。

### (c) Stage 1 の導入 — `DEPLOYMENT_RUNBOOK.md` §2 を最初から

**§2 の step 1〜step 6 をそのまま実施する。**本書はその代替ではない。
1.6.0 ゆえに **step 2 に足されている**のが `surfaces` の 2 変数である
(下の (d) が正本の再掲)。

step ごとの、この配備での要点だけ:

1. **step 1 (専用アカウント)** — `r2dbsvc` を `--system --no-create-home
   --shell /usr/sbin/nologin` で作る。**`id r2dbsvc` が既に何かを返すなら
   止まる。**
2. **step 2 (`/etc/r2dbsvc/api.env`)** — `deploy/env/api.env.example` から
   写し、**`REPLACE_WITH_...` を 1 つ残らず埋める。root:root / 0600。**
   例示値 (`example.invalid`) を実値と取り違えない。
3. **step 3 (内部 port)** — `REPLACE_ME_INTERNAL_PORT` は**わざと数値でない**。
   置換を忘れれば uvicorn が起動時に落ちる。**3010 (既存本番) と 443 と 8443
   を避けて選び、systemd unit と nginx conf の両方に同じ数を置く。**
4. **step 4 (systemd unit)** — 起動に失敗したら
   `journalctl -u r2dbsvc-api.service -e` を先に読む。必須 env の欠落は
   **変数名を名指しして落ちる。****検査を緩めて回避しない。**
5. **step 5 (nginx 8443)** — **既存の 443 server block には触れない。**
   `nginx -t` を通してから reload する。
6. **step 6 (検証)** — 無資格 `curl` で **`401` + `application/problem+json`**。
   有資格の `200` は (e) で credential を発行してからになる。
   **step 6 の 3 (既存本番 443 が無影響であること) を必ず実施する。**
   step 6 の 4 (platform DB 到達不能時の fail-closed と自動復帰) は、
   **既存本番と同じクラスタを止めることになるなら実施しない** — 実施可否は
   運用者が判断し、実施しなかったことを §7.3 に書く。

### (d) `surfaces` の 2 変数を両プロセスへ同一値で

**1.6.0 が env に足した差分の本体である。**`api.env` (data) と `control.env`
(control) の**両方**に、**同一値**で置く (`POSTGRES_PROVISIONING_RUNBOOK.md`
§10、`DEPLOYMENT_RUNBOOK.md` §2 step 2 の 6 / §7 の表):

| 変数 | `api.env` (data) | `control.env` (control) | 形の要件 |
|---|---|---|---|
| `R2DB_DATA_BASE_URL` | **必須** | **必須** | 絶対 URL、`/v1` で終わる、末尾スラッシュ無し、`/control/v1` で終わらない |
| `R2DB_CONTROL_BASE_URL` | `R2DB_CONTROL_PLANE_STATUS` が `unavailable` 以外のときのみ必須 (それ以外では読まれない) | **無条件に必須** | 絶対 URL、`/control/v1` で終わる、末尾スラッシュ無し |

- **形が不正なら起動時に落ちる** — 変数名を名指しする `RuntimeError` である。
  **値を用意しないまま起動すると上がらない。**
- **実値は Stage 1 の実際の到達 URL** (nginx 8443 の listener と、control
  プロセスの内部 port / 管理網の入口) である。**本書には書かない。**
  `deploy/env/{api,control}.env.example` の `example.invalid` は合成例である。
- **両プロセスが同じ値を持つことを、どちらのプロセスも検証できない**
  (設計 §11 L6-5a)。**§4-1 の手作業の diff がその代わりである。**
- **裁定 C = 既定 5000/5000。**したがって `R2DB_AUDIT_STATEMENT_TIMEOUT_MS` /
  `R2DB_AUDIT_IDLE_TIMEOUT_MS` は**どちらのファイルにも置かない** (置かない
  ことが「両方に同一値」の実現手段である)。宣言 `visibility_lag_ms` は 11000。
- **裁定 F = 配線しない。**`R2DB_AUDIT_DSN` はどちらにも置かない。
- `api.env` / `control.env` は **root:root / 0600**。

### (e) control プロセスの導入と、credential の初回発行

**`DEPLOYMENT_RUNBOOK.md` §7 の step 1〜step 5 をそのまま実施する。**
`audit_query` も `surfaces.control` も control プロセスにしか無い
(DEPLOY_PHASE4 §0.1 の 2)。

順序の要点:

1. **§7 step 1 / step 2** — `/etc/r2dbsvc/control.env` (root:root 0600) と
   2 つ目の systemd unit (`uvicorn r2db_api.control_main:app`、**data とは別の
   内部 port**)。**`R2DB_CONTROL_CREDENTIAL_PEPPER` は
   `R2DB_CREDENTIAL_PEPPER` と異なる値でなければならない** — 同じなら
   プロセスが起動を拒否する。
2. **§7 step 4 — control credential の `bootstrap`。****platform データベース
   ごとに、生涯に一度だけ。**この配備では**初回であり、二度目ではない。**
   発行直後は `must_rotate=true` であり、`GET /control/v1/capabilities` と
   自分自身の rotate 以外は何もできない。**直ちに 1 回本物の rotate を行う。**
   紛失・ロックアウトからの回復は `reset` である (§13)。**二度目の
   `bootstrap` は決して実行しない。**
3. **application credential の初回発行** — `python -m r2db_api.ops
   issue-credential <slug> <runtime|developer>` (`DEPLOYMENT_RUNBOOK.md`
   §1 の 3)。**`/control/v1` が立った後なら in-band の
   `POST /control/v1/...` が正典の発行面である**が、初回は帯域外 CLI でよい。
4. **§7 step 3 — `R2DB_CONTROL_PLANE_STATUS=enabled` は最後。**
   control プロセスが**実際に稼働し到達可能だと確認してから**、`api.env` に
   置いて `r2dbsvc-api.service` を再起動する。到達可否の正本は常に control
   自身の `GET /control/v1/capabilities` であり、data 側の宣言ではない
   (MitateDB の Invariant 3 と同じ性質)。

**CLI は main `4e48d1a` のソースツリーから実行する。**旧ツリーの CLI は旧形式の
secret を印字する。CLI は DB へ直接つながるので、**サービスの稼働状態とは
独立に実行できる。**

**印字と扱い:**

- 印字は `credential_id:` と `secret:` の 2 行。**`secret:` が完全な bearer で
  ある。丸ごと写す。分割しない。**一度しか表示されない。
- **`<credential_id>` と secret を自分で連結して bearer を作らない** — 初回
  発行では作る必要が無い (CLI が完成形を印字する)。合成はクライアントに
  禁じられた行為である (契約 D-1、§12a)。
- **§12a の rotate は実行しない** — 対象が無い (本節冒頭の 1)。

### (f) 適用後検証

**§4 の観測項目を、この peer について実行する。**ただし:

- **4-4 の前段 (旧 credential → `AUTH_INVALID`) は該当しない** — 旧
  credential が存在しない。**後段 (不正形 locator → `401`。`503` なら不合格)
  は実行する。**
- **4-6 の `audit_query` は `unavailable` が合格形である** (裁定 F)。
- **4-2 の catalog** は、初回導入では `0003` が作ったばかりの空の
  アプリケーションを見ることになる。**entity が無いこと自体は不合格では
  ない** — 合格条件は「`field_types` が `fields` を網羅している」であり、
  空集合どうしはこれを満たす。**型を確かめたいなら、使い捨ての entity を
  作って確かめる。**

---

## 4. 適用後検証 (両 peer 共通の観測項目)

各項目は「何を打って、何が返れば合格か」で書く。peer 固有の名前だけを
読み替える。**フェーズ4 由来の 6 項目は DEPLOY_PHASE4 §4 (4-1〜4-6) を
そのまま実行する** — ただし**合格値の版数は `1.6.0`** である (§4-0)。
本節が足すのは 1.6.0 固有の 5 項目 (§4-1〜§4-5) と、宣言と実挙動の一致
(§4-6) である。

### 4-0. 版数の合格値が上がっている

DEPLOY_PHASE4 §4-1 は `capabilities.contract_version == "1.5.0"` を合格値と
書いている。**本適用の後の合格値は `"1.6.0"` である。**それ以外
(`audit_query` の `event_classes` / `operations` / `target_kinds` の 3 本が
いずれも空でない配列であること、要素数そのものは合格条件ではないこと、
data ホストの `/v1/capabilities` では `audit_query` が `unavailable` のままで
正しいこと) は §4-1 のとおり変わらない。

**配備したイメージ / コードの版と、宣言される版が一致していること**が
確かめたい性質である。片方だけが動いていれば版束縛違反である。

### 4-1. 両 surface の `surfaces` が一致する (契約 1.6.0 無条件義務)

**data の文書と control の文書が、同じ `surfaces` オブジェクトを返す**こと。
これは契約の無条件義務であり、**どちらのプロセスも自分では確かめられない**
(設計 D-2、L6-5a)。**この手作業の突合が唯一の検査である。**

```sh
diff <(curl -s -H "Authorization: Bearer <application credential>" \
        <data base URL>/v1/capabilities | jq -S '.surfaces') \
     <(curl -s -H "Authorization: Bearer <control credential>" \
        <control base URL>/control/v1/capabilities | jq -S '.surfaces')
```

合格: **差分が無いこと**。加えて:

- `surfaces.data.base_url` が `/v1` で終わり、末尾スラッシュが無いこと。
- `surfaces.control.base_url` が `/control/v1` で終わり、末尾スラッシュが
  無いこと。
- **`control_plane` を `unavailable` と宣言している配備では
  `surfaces.control` が存在しないこと**が合格である (契約の条件付き省略)。
  MitateDB で (g)/(h) を実施しない選択をした場合は、これが合格形である。
- **URL が「その配備に実際に到達する URL」であること。**contract は形しか
  検査しない。**到達性は運用者の目で確かめる** — `surfaces.control.base_url`
  に `/capabilities` を足して実際に叩き、同じ文書が返ること。

### 4-2. catalog が全 field の型を返す

**MitateDB では `GET /v1/catalog` そのものが新規である** (`application_catalog`
が `unavailable` → `enabled`)。

```sh
curl -s -H "Authorization: Bearer <application credential>" \
  <data base URL>/v1/catalog | jq .
```

合格:

- `200 application/json`、`application_scope` と `entities` を持つ。
- `capabilities.application_catalog.status == "enabled"`。
- **各 `EntityDescriptor` の `field_types` が `fields` を網羅している**
  (キー集合が一致する。契約の「maps every name in fields」)。
- 値は 7 語のいずれか: `string` / `integer` / `number` / `boolean` /
  `object` / `array` / **`json`**。
- **MitateDB では、(b-3) で数えた `_mdb_field_types` の行数と、catalog が
  返す `field_types` の総数が一致する**こと。一致しなければ backfill が
  entity を取りこぼしている。
- **型を宣言せずに作られた field は `json`** である。

### 4-3. 新しい bearer を verbatim で提示して認証が通る

(d) / (e) で rotate した credential について、**印字された `secret:` を
そのまま** `Authorization: Bearer <secret>` に載せる:

```sh
curl -s -o /dev/null -w '%{http_code} %{content_type}\n' \
  -H "Authorization: Bearer <rotate が印字した secret を丸ごと>" \
  <data base URL>/v1/capabilities
```

合格: `200 application/json`。**合成も分解も行っていないこと**が、この
検証の本体である (契約 D-1)。

### 4-4. 旧 credential が `AUTH_INVALID` になる (r2db)

> **この配備では前段が該当しない (2026-09-05)。**§0.1 の 4-b のとおり r2db は
> 初回導入であり、**rotate 前の bare secret が存在しない。****後段の
> 「不正形の locator も同じ応答であること」は両 peer で実行する** — あちらは
> credential の新旧と無関係な、SI-14 の後退検知だからである。

**r2db についてのみ、実測できる合格条件である。**rotate 前の bare secret を
そのまま提示する:

```sh
curl -s -o /dev/null -w '%{http_code} %{content_type}\n' \
  -H "Authorization: Bearer <rotate 前の旧 secret>" \
  <data base URL>/v1/capabilities
```

合格: **`401` + `application/problem+json`**、error code は `AUTH_INVALID`。
**未知の credential と同一の応答である**こと (SI-10 — 応答は両者を区別
しない)。

**MitateDB では、この検査は該当しない** (§0.1 の 5)。この peer の wire 形は
1.6.0 以前から locator であり、rotate 前の bearer は **rotate によって**
失効する (flip によってではない)。rotate した場合、旧 bearer は同じく
`AUTH_INVALID` になる。

**不正形の locator も同じ応答であること**を、両 peer で 1 回ずつ確かめる
(ドット無し / 片側が空 / NUL を含む — DB に触れずに fail closed し、否認は
不帰属のまま耐久記録される。WP-2 で見つかった重大バグの再発検知である):

```sh
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer nodot" <data base URL>/v1/capabilities
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer .xyz"   <data base URL>/v1/capabilities
```

合格: **どちらも `401`**。**`503` が返ったら不合格である** — 未認証の
呼び出し側が「認可状態が壊れている」というシグナルを任意に捏造でき、かつ
否認が耐久表に残らない。**これは SI-14 の後退として扱う。**

### 4-5. MitateDB の挙動変更 α / β / γ (cutover の確認)

`cloud-run-cloud-sql.md` §6.4 が正本。**使い捨ての entity を作って確かめる。
本番データを対象にしない。**

- **α**: 型を宣言せずに field を作り、catalog がその field を **`json`** と
  報告すること。文字列も、オブジェクトも、数値も書けること (**受理域が
  広がっただけ**)。
- **β**: `json` / `object` / `array` と宣言した field を読み、**JSON 値**
  (オブジェクト / 配列 / 文字列 / 数値 / 真偽値 / `null`) が返ること。
  **JSON テキストの文字列ではない。**
- **γ**: `boolean` と宣言した field へ `true` を書いて `true` が返ること。
  **`1` を書くと `VALIDATION_FAILED`** になること。
- **(b-4) で目視した既存の宣言型**について、`mitate-application` の実際の
  読み書きが通ること。特に `boolean` と backfill された列。

### 4-6. 宣言と実挙動が一致している

- `capabilities.control_plane.status` が、**control プロセス / サービスが
  実際に到達可能かどうか**と一致していること。到達可否の正本は常に
  control 自身の `GET /control/v1/capabilities` である。
- `capabilities.audit_query.status` が、reader DSN の配線 (裁定 F) と
  一致していること。配線していないなら `unavailable` であり、**正典パスと
  alias の両方が認証後 `400` / `CAPABILITY_UNSUPPORTED`** を返すこと
  (DEPLOY_PHASE4 §4-6。**`200` でもなく、素の `404` でもない**)。
- `capabilities.audit_query.visibility_lag_ms` が裁定 C から導かれる値
  (既定なら 11000) であり、**両プロセスの実 SESSION 値がそれと整合する**
  こと (DEPLOY_PHASE4 §4-2 の `SHOW statement_timeout` /
  `SHOW idle_in_transaction_session_timeout`)。
- `limit_enforcement` の各クラスが `enforced` であり、**`mitatedb-ctrl` の
  `--max-instances=1` が実際に 1 である**こと
  (`gcloud run services describe mitatedb-ctrl` の `maxScale`)。**2 以上なら
  この宣言は偽である。**

---

## 5. logs-based alert の結線と platform DB 容量閾値

> **裁定 D = 今回は結線しない (記録のみ、将来課題)。**したがって本節は
> **今回実行しない。**そのことの含意を先に書く:
>
> - **未結線は契約違反ではない。**契約が要求するのは証拠が耐久化されること
>   であり、alert はその**運用上の見張り**である。証拠は溜まり続ける。
> - **代わりに失われるのは「気付く手段」である。**5 種のメッセージは
>   いずれも**証拠喪失そのもの**を告げるものであり (buffer overflow による
>   ドロップ、alert 行自体が書けない、合体 denial の集計行が書けない)、
>   未結線の間は**それが起きても誰も知らない。**
> - **したがって、これは「後で気が向いたらやる」項目ではなく、次のフェーズへ
>   持ち越す明示的な未了項目である。**§7.5 に「未結線」と書き、理由と
>   将来の結線先候補 (MitateDB = Cloud Logging のログベース指標、
>   r2db = journald) を残す。
> - **容量 (裁定 B) も同じ扱いである** — §0.2 の「B の代入結果」は
>   **結線するときに使う算式の確定形**として記録するものであり、今日から鳴る
>   閾値ではない。**観測間隔は定めていない。**

**DEPLOY_PHASE4 §5 と §6 をそのまま実行する。フェーズ5 / フェーズ6 はこの
2 節に何も足していない。**(以下は将来結線するときの正本の指し先である。)

- **alert (§5)**: 監査パイプラインが出す `logging.error` は**ちょうど 5 種**
  であり、いずれも補間の無い固定文字列である。**5 種すべてに完全一致で
  アラートを張ること** — 独立した 2 つの証拠喪失チャネル (buffer/overflow と
  合体 denial) があり、最初の 3 つだけに張ると合体チャネルが無音になる。
  **回復は、対応する回復メッセージ (3 番目 / 5 番目) で読む。メッセージが
  途切れたことを回復とみなさない。**結線先は裁定 D。
- **容量 (§6)**: 1 行サイズの上限は両 peer とも **2 KiB**。**プロセスあたりの
  行数上限に裁定 A の M を掛ける** (合体カウンタも buffer もプロセス
  ローカルであり、インスタンス間で共有されない)。**絶対サイズではなく
  増加率にアラートを張る。**MitateDB では、これをインスタンス自身の
  ストレージ使用率メトリクスと組み合わせ、自動ストレージ拡張を有効に保つ。
  しきい値の実数は裁定 B。

**これが単なる整頓でない理由**も §6 のとおり: platform DB は**全アプリ
ケーション**の credential store でもあるため、ディスクが埋まればプラット
フォーム全体の認証が止まる (SI-00 の可用性側)。

---

## 6. ロールバック

**DEPLOY_PHASE4 §7 の原則を継承する** (「migration は残して無害である。
慌てて巻き戻さない — 消せば証拠が消える」)。フェーズ6 が足す事実は 3 つ
あり、**うち 1 つは不可逆である**。

### 6.1 戻せるもの

| 対象 | 戻し方 | 備考 |
|---|---|---|
| MitateDB の**コード** | `gcloud run services update-traffic mitatedb-data --to-revisions=<旧 revision>=100` | **旧 revision は (c) 以降ずっと生きている。**これが `--no-traffic` 段取りの目的である |
| MitateDB の `mitatedb-ctrl` | 停止 / undeploy / scale-to-zero | **同じ変更の中で** `mitatedb-data` の `MITATEDB_CONTROL_PLANE_STATUS` を `unavailable` へ戻す (Invariant 3、§8)。**止めただけでは control credential は失効しない** — 破棄が必要なら `CONTROL_PLANE_COMPROMISE_PLAYBOOK.md` |
| `audit_query` だけ | reader DSN (`MITATEDB_AUDIT_DSN` / `R2DB_AUDIT_DSN`) を設定から外して再デプロイ / 再起動 | 宣言は `unavailable` に戻り、両ルートは認証後 `CAPABILITY_UNSUPPORTED`。**耐久 sink は動き続ける** — 証拠は溜まり続け、読む手段が帯域外 (§3.2f / §15.4 の `psql`) だけになる |
| r2db の**コード** | 旧コードを virtualenv へ戻して再起動 | **§6.3 を読むこと** — r2db では credential が道連れになる。**ただしこの配備では「戻す先の旧コード」が存在しない** (§0.1 の 4-b: 初回導入)。**r2db のロールバックは「戻す」ではなく「止める」である** — `r2dbsvc-api.service` / control unit を停止し、nginx の 8443 listener を外す。**既存本番の 443 は最初から触っていないので、止めれば導入前の状態に戻る** |
| MitateDB の migration `0005` / `0006` | **戻さない** | `0006` が作る `public._mdb_field_types` は、**旧コードが一切読まない**。残して完全に無害である。`0005` も同じ (書き手が INSERT しなくなるだけ) |
| r2db の migration `0007` | **戻さない** | 同上 |

### 6.2 戻せないもの — rotate

**rotate した credential は戻せない。**verifier が上書きされているので、
**Secret Manager の旧 version を再 enable しても、その値では認証できない。**
これは配備の設定ではなく、credential store の状態である。

**したがって、ロールバックの計画は「rotate をやり直す」ことで立てる。**
戻した先のコードで、もう一度 rotate して新しい値を配る。

### 6.3 peer 非対称 — 「新しい bearer は旧コードで通るか」

- **MitateDB: 通る。**この peer の受理側は 1.6.0 以前から locator 形なので、
  **rotate 後の bearer は `phase-b` の旧 revision でもそのまま認証を通る**
  (§0.1 の 5)。**したがって traffic を旧 revision へ戻すのに、credential を
  戻す必要は無い。**これがロールバックを単純にしている。
- **r2db: 通らない。**旧コードは presented bearer 全体の digest で行を引く
  ので、`<credential_id>.<secret>` 形の新しい bearer は一致しない。**r2db を
  フェーズ6 前のコードへ戻すなら、credential をもう一度 (旧コードの CLI で)
  発行し直す必要がある。**Stage 1 に production traffic は無いので、これは
  作業量の問題であって障害ではない。
  **この配備では、そもそも戻す先の旧コードが無い** (§0.1 の 4-b) —
  **フェーズ6 前の r2db をわざわざ入れる理由は無いので、この非対称は
  今回の作業では発現しない。**記述は将来のために残す。

### 6.4 監査行そのものの削除はロールバックではない

**保存期間の決定**である。手順は §3.2e / §15.3 (schema owner が実施、
エクスポートが先、DELETE は不可逆、何をいつ誰が消したかは別途記録 —
消した後のテーブルはそれを証拠立てない)。

---

## 7. 配備記録テンプレート

**§0.2 の裁定表を埋めたものと一緒に、以下を実測値で埋めて残す。**

> **記録に書いてよいもの**: `credential_id`、Secret Manager の**名前**と
> **version 番号**、image digest、revision 名、行数、HTTP status。
> **書いてはならないもの**: secret / bearer / パスワード / pepper / DSN の
> 値。**rotate の印字は記録に写さない。**

**この記録は 2026-09-05 に書き始めた。**埋まっている行は実測値であり、
` ` のままの行は**まだ実施していない**ことを意味する (「調べていない」ではなく
「そのステップに到達していない」)。**推測で埋めない。**

### 7.1 適用元

| 項目 | 実測値 |
|---|---|
| main のコミット | **`4e48d1a`** — (a) の Cloud Build のソースはこのコミットの `git archive` である |
| root suite (単独実行、`-n 5 --dist loadgroup`) | **1802 passed / 0 failed / 0 skipped / 0 xfailed** (2026-09-04、監督が単独実行した完了ゲート) |
| 実行日時 / 実行者 | 配備作業の開始 **2026-09-05**、監督 (`gcloud`) + 運用者 (秘密・psql・SSH) |

### 7.2 MitateDB-api

| 項目 | 実測値 |
|---|---|
| (a) Cloud Build の id / 所要 | **`cf15f107-9c67-4e08-8bc2-bbcf4e74fc74`** / **43 秒** (成功) |
| (a) `1.6.0-data` の image digest | **`sha256:5fb2d292…`** (完全形を控えること) |
| (a) `1.6.0-control` の image digest | **`sha256:ac626232…`** (完全形を控えること) |
| (b-1) `0005` 適用前の `to_regclass('mitatedb_registry.application_audit')` | ` ` (未実施) |
| (b-1) 適用後の同上 / `mitatedbsvc_auditreader` の有無 | ` ` / ` ` (未実施) |
| (b-2) `0006` を適用した `application_id` / `database_name` | ` ` / ` ` (未実施。現況の application は `mitate` の 1 つ) |
| (b-3) `_mdb_field_types` の行数 (X) | ` ` (未実施) |
| (b-3) 対象列の総数 (Y) | ` ` (未実施) |
| (b-3) **X = Y か** | ` ` (未実施) |
| (b-4) 手で直した行 (entity.field → declared_type) | ` ` (未実施) |
| (b-4) `boolean` と backfill された列の一覧と、目視の結論 | ` ` (未実施) |
| (c) 新 revision 名 | **`mitatedb-data-00004-wh4`** (`--no-traffic --tag=v160`) |
| (c) tag URL の実測 | **`https://v160---mitatedb-data-<RUN_HASH>-an.a.run.app`** (旧形式が払い出された) |
| (c) 切替前の traffic | **`mitatedb-data-00003-6vj` (`phase-b`) が 100%** |
| (c) 無資格 probe の status (`gcloud run services proxy --tag=v160` 経由) | **`503` `SERVICE_UNAVAILABLE`** — **期待は `401`。合格していない。**(b) 未適用が最有力の説明 (`0006` 未適用 → `StorageConfigurationError`) |
| **(b) 完了後の無資格 probe 再実行 (2026-09-05 に足した必須項目)** | ` ` — **`401` + `application/problem+json` になること。これが (f) の前提である** |
| (c) `describe` で読んだ env と secret の集合が §2(c) と一致するか | ` ` (未確認。**(f) の前に読む**) |
| `mitatedb-data` の invoker 設定 (§1.2 の `get-iam-policy`) | ` ` (**未実測**。2026-09-05 に運用者アカウントへ `roles/run.invoker` を足したので、元の集合と区別して読む) |
| (d) 裁定 E-2 の決定 | **再発行しない** (rotate は不可逆であり、MitateDB では不要 — §0.1 の 5) |
| (d) `mitate-application` が現に認証を通っているかの確認 | ` ` (未実施。**(f) の前に運用者が確認する** — 切替後の切り分けのため) |
| (d) rotate した `credential_id` の一覧 | **無し (rotate を実行しない)** |
| (d) 追加した Secret Manager version (名前 + 番号) | **無し** |
| (e) `mitate-application` の再デプロイ有無 / revision | **無し (credential 起因の再デプロイは発生しない)**。β/γ の対応が要るかは (f) 後に判断 |
| (f) traffic 切替の日時 / 切替後の `status.traffic` | ` ` / ` ` (未実施) |
| (g-1) ctrl の SA 名 | **`mitatedb-ctrl-runtime@<GCP_PROJECT_ID>.iam.gserviceaccount.com`** (新規作成) |
| (g-2) `roles/cloudsql.client` 付与 | **data / ctrl の両 SA に付与済み。**ctrl 側は**1 回目が無音で失敗し、再実行で成功**した (新規 SA の伝播遅延) |
| (g-2b) `roles/secretmanager.secretAccessor` 付与 | **ctrl SA に、`mitatedb-credential-pepper` / `mitatedb-control-credential-pepper` / `mitatedb-controlplane-dsn` の 3 secret へ個別に付与済み** |
| (g-3) ctrl の revision 名 / `maxScale` (**1 であること**) | **`mitatedb-ctrl-00001-m8s`** / **1** (`--max-instances=1`、`--no-allow-unauthenticated`、Cloud SQL 接続あり、`MITATEDB_AUDIT_DSN` 無し) |
| (g-3) ctrl の起動ログ | **エラー無し** |
| (g-4) invoker principal | **`user:<OPERATOR_ACCOUNT_EMAIL>`** (運用者本人。`allUsers` でも `mitate-application` の SA でもない) |
| (g-5) **`status.url` の実測値**と、`MITATEDB_CONTROL_BASE_URL` との一致 | 実測 **`https://mitatedb-ctrl-<RUN_HASH>-an.a.run.app`** (旧形式) / **文字列としては不一致だが直していない** — 決定的 URL `https://mitatedb-ctrl-<GCP_PROJECT_NUMBER>.<REGION>.run.app` も同一サービスへ到達する (未認証 `curl` が **`403`** = front end の IAM 拒否 = ルーティング成立)。**(g-6) で決定的 URL 経由の `200` を確認して閉じる** |
| (g) 無資格 probe (`proxy` 経由、`GET /control/v1/capabilities`) | **`401` `AUTH_REQUIRED`** — アプリ層まで起動し、base URL の形検査も通っている |
| (g-6) 有資格 `GET /control/v1/capabilities` の status / `contract_version` | ` ` / ` ` (未実施 [運用者]。**(h) の前提**) |
| (h) `MITATEDB_CONTROL_PLANE_STATUS=enabled` の revision / 日時 | ` ` / ` ` (未実施) |
| 裁定 F の決定 / `mitatedb-audit-dsn` の新設有無 | **配線しない** / **新設しない** (`audit_query` は `unavailable` 宣言のまま) |

### 7.3 r2db-api

**この配備は初回導入である (§0.1 の 4-b、§3)。**表もそれに合わせて書き直した。

| 項目 | 実測値 |
|---|---|
| (a) 2026-09-05 の SSH 実測: 稼働サービス | **既存本番の `r2db-api.service` のみ** (`/home/<VPS_USER>/r2-vps/apps/r2db-api`、uvicorn `127.0.0.1:<EXISTING_APP_PORT>`、nginx `db.example.invalid` 443)。**本リポジトリの実装ではない** |
| (a) 本リポジトリの Stage 1 の有無 | **未導入** — `/etc/r2dbsvc` / `/opt/r2dbsvc` 無し、`r2dbsvc-*` unit 無し、8443 listener 無し |
| (a) Python | **3.12.3 のみ** (`requires-python = ">=3.11"` を満たす) |
| (a) 監督の特権 | **無し** (`sudo` はパスワード必須)。**§3 は全ステップが [運用者]** |
| (a) PostgreSQL の現況 (`r2dbsvc_platform` の有無) | ` ` (未実測) |
| (b) `0001` / `0002` / `0005` / `0006` / `0007` の適用 | ` ` (未実施。**`0003` は `0006` の後**) |
| (b) `0003` を適用した application slug の一覧 | ` ` (未実施) |
| (c) 選んだ内部 port (既存本番の 3010 と重ならないこと) | ` ` (未実施。**値は記録してよい — 秘密ではない**) |
| (c) `r2dbsvc` アカウント作成 / unit / nginx 8443 | ` ` (未実施) |
| (c) §2 step 6 の 1 (無資格 `curl`) の status + content-type | ` ` (期待 `401` + `application/problem+json`) |
| (c) §2 step 6 の 3 (既存本番 443 が無影響) | ` ` (**必須**) |
| (c) §2 step 6 の 4 (platform DB 到達不能時の fail-closed と自動復帰) | ` ` (実施しなかった場合はその旨と理由) |
| (d) `R2DB_DATA_BASE_URL` を両ファイルへ置いたか (値は書かない) | ` ` |
| (d) `R2DB_CONTROL_BASE_URL` を両ファイルへ置いたか | ` ` |
| (d) 裁定 C: `*_AUDIT_*_TIMEOUT_MS` を置かなかったか (既定 5000/5000) | ` ` |
| (e) control unit の導入 / 起動 | ` ` (未実施) |
| (e) `bootstrap` の実施 (**この配備では初回。二度目ではない**) と直後の rotate | ` ` |
| (e) 初回発行した `credential_id` の一覧 (application / control) | ` ` |
| (e) §12a の再発行 | **該当なし (対象が存在しない)** |
| (d/e) `R2DB_CONTROL_PLANE_STATUS` の最終値 | ` ` (control が到達可能になってから `enabled`) |
| 裁定 F の決定 / `R2DB_AUDIT_DSN` の配線有無 | **配線しない** / **置かない** |

### 7.4 §4 の検証結果

| 項目 | MitateDB | r2db |
|---|---|---|
| 4-0 `contract_version` (期待 `1.6.0`) | ` ` | ` ` |
| 4-0 `audit_query` の 3 語彙が非空 (配線した場合) | **該当なし (裁定 F = 配線しない)** | **該当なし (同左)** |
| 4-1 `surfaces` の 2 文書 diff (期待 差分無し) | ` ` | ` ` |
| 4-1 `surfaces.control` の有無と `control_plane` 宣言の一致 | ` ` | ` ` |
| 4-1 `surfaces.control.base_url` が実際に到達するか ((g-5) の判断を閉じる) | ` ` | ` ` |
| 4-2 `field_types` が `fields` を網羅 / 型の総数 | ` ` | ` ` (初回導入なので entity が空でも合格しうる — §3(f)) |
| 4-3 新 bearer を verbatim で提示 → `200` | ` ` (rotate しないので、既存 credential での `200` を確認する) | ` ` (初回発行した credential で確認) |
| 4-4 旧 credential → `401` `AUTH_INVALID` | **該当なし (rotate しない)** | **該当なし (旧 credential が存在しない)** |
| 4-4 不正形 locator → **`401`** (`503` なら不合格) | ` ` | ` ` |
| 4-5 α / β / γ の確認 | ` ` / ` ` / ` ` ((f) の直後に実施 — 裁定 E は窓を設けない) | (該当なし) |
| 4-6 `visibility_lag_ms` = **11000** と実 SESSION 値の整合 | ` ` | ` ` |
| 4-6 `limit_enforcement` / ctrl の `maxScale` = 1 | ` ` / **`maxScale` = 1 は実測済み** | ` ` |
| DEPLOY_PHASE4 §4-3 reader で INSERT 拒否 | **該当なし (reader DSN を配線しない)** | **該当なし (同左)** |
| DEPLOY_PHASE4 §4-4 書き手で SELECT 拒否 | ` ` (帯域外 `psql` で確認できる) | ` ` |
| DEPLOY_PHASE4 §4-5 破壊的操作 1 件で行が増える | ` ` (`audit_query` は使えないので **帯域外 `psql` で行数を読む** — §3.2f) | ` ` (§15.4) |
| DEPLOY_PHASE4 §4-6 未配線なら `CAPABILITY_UNSUPPORTED` (正典 + alias) | ` ` (**今回の合格形はこれである**) | ` ` (同左) |

### 7.5 §5 の結線

| 項目 | MitateDB | r2db |
|---|---|---|
| 5 種の固定メッセージすべてに alert を張ったか | **張っていない (裁定 D = 今回は結線しない)** | **同左** |
| 結線先 (裁定 D) | **未定 (将来課題)**。候補: Cloud Logging のログベース指標 | **未定 (将来課題)**。候補: journald |
| 容量の増加率しきい値 (裁定 B) と観測間隔 | **算式の確定形のみ記録 (§0.2「B の代入結果」)。観測間隔は未定 — 観測する主体がまだ無い** | **同左** |
| 容量算式に入れた M (裁定 A) | **1** (`mitatedb-data` の `--max-instances`) | **1** (単一 uvicorn プロセス) |
| **未了であることの承知** | **証拠は溜まるが、証拠喪失に気付く手段が無い状態である。**次フェーズへ持ち越す明示的な未了項目として扱う | **同左** |

## 8. 実施記録 追記 (監督、2026-09-05 06:10〜06:40 JST)

§7 の表が埋まる前に進んだ分を時系列で記す (値は実測。秘密値なし)。

1. **§2(b) [運用者] 完了** — `cloud-sql-proxy --gcloud-auth --port 15432 <GCP_PROJECT_ID>:<REGION>:mitatedb-platform` (ADC 不在のため `--gcloud-auth` を使用。ローカル PostgreSQL が 5432 を占有するため別ポート)。`0005_application_audit.sql` → `CREATE TABLE` / `REVOKE` / `GRANT`×6 / `DO` / `assert_role_has_no_memberships` 1 行 (空 = 合格)。`0006_declared_field_types_upgrade.sql -v app_id='mitate'` → `mitatedb_app_mitate` に接続、`CREATE TABLE`、**`INSERT 0 19`** (backfill 19 列)、`COMMIT`。
2. **§2(f) 前提の再 probe** — `gcloud run services proxy --tag=v160` 経由 `GET /v1/capabilities` (credential なし) → **401 `AUTH_REQUIRED`** (適用前は 503。§2(c) の観測どおり 0006 が前提だった)。
3. **§2(f) [監督] 完了** — `update-traffic --to-revisions=mitatedb-data-00004-wh4=100`。直後 1 分のログ: data 00004 に WARNING 1 件 (本文空、無害)、`mitate-application` に ERROR なし。
4. **§2(h) [監督] 完了** — `gcloud run services update mitatedb-data --update-env-vars=MITATEDB_CONTROL_PLANE_STATUS=enabled` → revision **`mitatedb-data-00005-pcz`** (image 1.6.0-data、env 4 本確認)。**注意 (手順書への教訓)**: 3 で traffic を revision 固定にしたため、新 revision は 0% で作られた。`update-traffic --to-latest` で **`00005-pcz` = 100%**。以後は `LATEST` 追従。再 probe → 401。data / ctrl / mitate-application にエラーなし。
5. **Secret Manager の事故と復旧 (運用者作業中)** — `mitatedb-control-credential` の形式確認は `dots=1 length=72` (= 合成形、再発行不要)。ところが確認用の「dots=0 のときだけ」の合成コマンドがプレースホルダ未置換のまま実行され、**version 2 に壊れた値**が登録された (稼働サービスはこの secret を読まないので影響なし)。復旧 = version 1 の値を version 3 として再登録し、version 2 を disable。`latest` が `dots=1 length=72` に戻ることを確認する。
6. **未実施** — credential を伴う検証 (両文書の `surfaces` 一致、`GET /v1/catalog` の `field_types`、β / γ の確認) は運用者が proxy 経由で実行し結果を本表へ転記する。r2db は §3 の初回導入 (運用者)。裁定 D (alert 結線) は未結線。

7. **§4 検証 [運用者、2026-09-05 06:45 JST 前後] 完了** — `gcloud run services proxy` 2 本 (ctrl 18082 / data 18081) 経由、credential は Secret Manager から `$( )` で渡し画面に出さない。(i) control 文書: `contract_version` **1.6.0**、`surfaces.data.base_url = https://mitatedb-data-<GCP_PROJECT_NUMBER>.<REGION>.run.app/v1`、`surfaces.control.base_url = https://mitatedb-ctrl-<GCP_PROJECT_NUMBER>.<REGION>.run.app/control/v1`、control credential (合成形、version 3) で認証成功。(ii) data 文書: 同じ 1.6.0、**`surfaces` は control 文書と同一**、`application_catalog = {status: enabled}`、runtime credential で認証成功。(iii) `GET /v1/catalog`: `application_scope = mitate`、entity `entity_a` / `entity_b` / `entity_c` / `entity_d` (以下省略) の全 `fields` に `field_types` が付く (backfill どおり `integer` / `string` のみ)。**`json` / `boolean` 宣言の列が存在しないため、挙動変更 β / γ は既存データに影響しない** (α は新規の型未宣言 field のみ)。`entity_b.<json_field_1>` / `entity_c.<json_field_2>` は JSON テキストを `string` として保持 (object 化は `add_field` で型付き列を足す運用、設計 §11 L6-16)。
8. **MitateDB の 1.6.0 実機適用はここで完了**。残: r2db の初回導入 (§3、運用者)、裁定 D (alert 結線) は未結線のまま次フェーズへ。

9. **§3 r2db 初回導入の準備 [監督、2026-09-05 07:00〜07:30 JST]** — SSH (ユーザー `<VPS_USER>`、非特権) で実測・準備した。**実測**: Ubuntu 24.04、PostgreSQL 16 (`16-main`、socket `/var/run/postgresql`)、Python は 3.12.3 のみ (3.11 なし)、8443 / 8081 / 8082 は空き、disk 88 GB / mem 1.3 GB 空き、既存 443 ブロックは `db.example.invalid` の Let's Encrypt 証明書 + `options-ssl-nginx.conf` + `proxy_pass 127.0.0.1:<EXISTING_APP_PORT>`、`r2dbsvc` OS アカウント無し、PG role `<VPS_USER>` 無し (接続数の実測は `sudo -u postgres` が要るため運用者)。**GitHub リポジトリは private** (VPS からの https clone は認証要求で失敗) のため、コードは `git archive main` (4e9960c) を SSH 標準入力で `/home/<VPS_USER>/data-service-api` へ展開。`/home/<VPS_USER>/r2dbsvc-venv` (python 3.12) に `r2db-api` を install し、パッケージ import と同梱契約 1.6.0 を確認 (3.12 で動作、psycopg 3.3.5 / uvicorn 0.52.4 / starlette 1.6.0)。**準備物** (`/home/<VPS_USER>/r2dbsvc-stage1/`、運用者が `sudo cp` するだけ): `r2dbsvc-api-8443.conf` (server_name `db.example.invalid`、既存証明書を再利用、`/v1/` → 127.0.0.1:8081、`/control/v1/` → 127.0.0.1:8082、それ以外 404)、`r2dbsvc-api.service` (port 8081、`/opt/r2dbsvc/venv`)、`r2dbsvc-control.service` (`control_main:app`、port 8082、`control.env`)、`api.env` / `control.env` (非秘密値記入済み: `R2DB_DATA_BASE_URL=https://db.example.invalid:8443/v1`、`R2DB_CONTROL_BASE_URL=https://db.example.invalid:8443/control/v1`、posture B の DSN 形、`R2DB_CONTROL_PLANE_STATUS=unavailable` 初期値、`R2DB_AUDIT_DSN` 未設定 = 裁定 F)、`pg_hba_posture_b.txt`、そして **`OPERATOR_STEPS.sh`** (sudo を要する全手順を順序どおりに並べたスクリプト: 0 前提確認 → 1 アカウントと `/opt/r2dbsvc` への配置と venv 再構築 → 2 秘密の生成 → 3 migration 0001→0002→0005→0006→0007→0003 → 4 posture B の pg_hba / pg_ident → 5 env 配置 → 6 control unit と bootstrap → 7 data unit と nginx 8443 と `enabled` 化 → 8 最初の application credential 発行)。**設計上の注意**: unit は `ProtectHome=true` なので `/home/<VPS_USER>` 配下の venv は使えない (`/opt/r2dbsvc` に再構築する。私の home venv は互換性確認用)。**未決 (運用者裁定)**: 最初の application slug、posture (B が 2026-08-28 の裁定、A は fallback)、8443 で `db.example.invalid` を再利用すること (server_name 同一の方針どおり)。

10. **§3 r2db 初回導入 [運用者 + 監督、2026-09-05 07:10〜07:50 JST] — 完了 (外部到達を除く)**。`OPERATOR_STEPS_part1.sh` (SLUG=`sandbox`) → 0005 が `api_password` 未指定で停止 (監督のスクリプト不備。`r2dbsvc_api` role のパスワード変数) → `part1b` で 0005 (api_password 付き) / 0006 / 0007 / 0003 を適用 (登録: `sandbox|t`)。posture B の pg_hba / pg_ident 追記と `reload postgresql` は運用者が監督提供の 1 コマンドで実施。`part2`: `/etc/r2dbsvc/{api,control}.env` (root 0600)、`r2dbsvc-control.service` (8082) と `r2dbsvc-api.service` (8081) が active、loopback で両方 `401 application/problem+json`、bootstrap 実行、`R2DB_CONTROL_PLANE_STATUS=enabled` で再起動。**nginx は `http2 on;` が nginx 1.24 で未対応のため `nginx -t` 失敗** → `listen 8443 ssl http2;` 形に修正して再配置、`nginx -t` 成功・reload。VPS 上から 8443 の data / control とも `401 application/problem+json`、443 の既存本番は無変更 (307)。**bootstrap と最初の runtime credential の印字を運用者が紛失** → `reset --confirm RESET_CONTROL_CREDENTIALS` で control credential を作り直し (旧は失効)、`issue-credential sandbox runtime` を再発行 (旧 runtime credential は値不明のまま有効。control plane から revoke する)。出力は `~/r2dbsvc-stage1/{control,runtime}-credential.txt` (0600) に保存し、秘密管理へ転記後 `shred -u` する。**検証 (loopback、運用者)**: control 文書 `1.6.0`、`surfaces.data = https://db.example.invalid:8443/v1`、`surfaces.control = https://db.example.invalid:8443/control/v1`; data 文書 `1.6.0`、**同一の `surfaces`**、`control_plane = {status: enabled}`; 両 credential で認証成功。**未完**: 外部からの 8443 到達 — ホストの `ufw allow 8443/tcp` は実施済みだが <VPS_PROVIDER> のセキュリティグループが 8443 を通していない (Mac から `Timeout`、443 は到達)。コントロールパネルで TCP 8443 の受信許可を追加する (運用者)。その後: control credential の初回 rotate (must_rotate 解除)、紛失した旧 runtime credential の revoke、`shred -u secrets.env`。

11. **外部到達 (2026-09-05 08:02 JST)** — <VPS_PROVIDER> のセキュリティグループに IN / TCP / 8443 を IPv4 `0.0.0.0/0` と IPv6 `::/0` で追加 (運用者)。数分の反映遅延の後、監督の Mac から `https://db.example.invalid:8443/v1/capabilities` と `/control/v1/capabilities` が **401 `application/problem+json`**、TLS 検証成功 (既存の Let's Encrypt 証明書を再利用)、HTTP/2、`Server: nginx` (版数なし)、未知パスは 404。443 の既存本番は 307 のまま無変更。**r2db Stage 1 (1.6.0) は公開 listener まで含めて稼働。** 残 (運用者): control credential の初回 rotate、値不明の旧 runtime credential の revoke、`secrets.env` 等の秘密管理への転記と `shred -u`。裁定 D (alert 結線) は両 peer とも未結線のまま次フェーズ。

12. **credential の最終状態 (2026-09-05 08:10 JST、運用者)** — control credential を `POST /control/v1/credentials/{id}/rotate` で初回 rotate (`ctl_<REDACTED_1>` が有効・`must_rotate: false`、bootstrap 時の `ctl_<REDACTED_2>` は reset により失効)。`GET /control/v1/credentials?application_id=sandbox` の一覧で `sandbox` の runtime credential は **`crd_<REDACTED_1>` の 1 本のみ**で、再発行分の id と一致 — 項目 10 で「値不明のまま有効」と書いた 1 本目は**そもそも発行されていなかった** (part2 のブロック 8 は nginx `-t` 失敗後に到達していない) ため、**revoke は不要**。残: 秘密の秘密管理への転記と `shred -u` (運用者)。

**ロールバック (現時点)**: r2db は `sudo systemctl disable --now r2dbsvc-api.service r2dbsvc-control.service` + `sites-enabled/r2dbsvc-api-8443.conf` の削除 + `nginx -t && reload` (既存 443 は無影響。`r2dbsvc_*` の DB / role は残してよい)。MitateDB は `gcloud run services update-traffic mitatedb-data --region=<REGION> --to-revisions=mitatedb-data-00003-6vj=100` (旧 phase-b。0005 / 0006 は残してよい)。ctrl を止める場合は同時に data の `MITATEDB_CONTROL_PLANE_STATUS=unavailable`。
