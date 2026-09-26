# r2db-api backup / restore runbook

- 版数: v1.0 (2026-09-06、起草)
- 対象: Phase 8 WP-4 (design `docs/design/PHASE8_EFFECTIVE_BOUNDS_AND_HYGIENE_V1.md` D-5 決定 4、work order `docs/work-orders/WORK_ORDER_PHASE8_EFFECTIVE_BOUNDS_V1.md` §2 WP-4 実装の指示 (d))。
- 実値は書かない。すべて `<UPPER_SNAKE>` プレースホルダと `*.example.invalid` のみ (`docs/security/public-repository-policy.md`)。

## 0. 前提

- `pg_dump` / `pg_restore` は PostgreSQL 16 系のクライアントを使う (作業機・CI とも PostgreSQL 16、`.github/workflows/ci.yml:77-82`)。
- 対象は r2db-api のプラットフォーム DB (`r2dbsvc_platform` 相当 — `platform_declarations` / `applications` / `credentials` 等の登記) と、application ごとの個別 DB (`<prefix>_app_<slug>` 相当) の 2 種類である。手順はどちらにも同型で適用できる — 以下は変数名で両方を表す。
- 復元先は必ず **新しい DB 名** にする (既存 DB を直接上書きしない)。動作確認が済むまで元の DB は残す。

## 1. バックアップ (pg_dump、カスタム形式)

```sh
pg_dump --format=custom \
  --dbname="$<UPPER_SNAKE_SOURCE_DSN_ENV>" \
  --file="<DUMP_PATH>"
```

- `$<UPPER_SNAKE_SOURCE_DSN_ENV>` は対象 DB への接続文字列を保持する環境変数名 (例: `R2DBSVC_BACKUP_SOURCE_DSN`)。値は環境変数経由でのみ渡す — 引数に DSN リテラルを書かない (argv secret 規則、`conformance-tests/test_deploy_secret_argv_scan.py`)。
- **application 個別 DB を対象にする場合の注意**: この backend は一部の内部管理テーブル (schema revision の追跡テーブル) に row-level security を `FORCE` で掛けている。読み取り専用の `pg_dump` であっても、その DB の **owner ロール** (または相当の強い権限を持つ接続) で実行しないと `query would be affected by row-level security policy` で失敗する — application が使う `runtime`/`developer` ロールの接続では不足する場合がある。

## 2. 復元先 DB の作成

```sh
psql "$<UPPER_SNAKE_ADMIN_DSN_ENV>" -c \
  "CREATE DATABASE <RESTORED_DB_NAME> TEMPLATE template0 ENCODING 'UTF8' LC_COLLATE 'C' OWNER <UPPER_SNAKE_OWNER_ROLE>"
```

- `<UPPER_SNAKE_OWNER_ROLE>` は元の DB を所有していたロールと**同じロール**にする (プラットフォーム DB なら `..._control` 相当、application DB ならそれを provision したロール)。owner が違うと次段の `pg_restore` が `CREATE SCHEMA`/`CREATE TABLE` で `permission denied for database` になる。

## 3. 復元 (pg_restore)

```sh
pg_restore \
  --dbname="$<UPPER_SNAKE_RESTORED_DSN_ENV>" \
  "<DUMP_PATH>"
```

- `$<UPPER_SNAKE_RESTORED_DSN_ENV>` は手順 2 で作った DB への接続文字列を保持する環境変数名で、**手順 2 と同じロール**で接続する (dump に含まれる `CREATE TABLE` / `ALTER ... OWNER TO` 文を実行できる権限が要る)。
- `pg_restore` は無害な警告 (例: 既存オブジェクトの重複作成をスキップした旨) で終了コード 1 を返すことがある — 復元後の内容確認 (手順 4/5) で実害の有無を判定する。

## 4. 宣言の検証 (`ops verify-declarations`)

プラットフォーム DB を復元した場合、復元先を指す DSN で `ops verify-declarations` を実行し、宣言が壊れていないことを機械的に確認する。

**必ず `audit_writer_roles` に含まれる書き手ロール (`..._api` / `..._controlplane` 相当) の DSN で実行すること** — 手順 2/3 で使う DB **owner** ロール (`..._control` 相当) のままこのコマンドを実行すると、owner は宣言された書き手ロールに含まれないため**必ず F-13 (exit 11) になる** (`audit_writer_roles` は migration `0008_platform_declarations_and_writer_timeouts.sql:161` が `[api_role, controlplane_role]` のみを seed し、owner/control ロールを含めない)。exit 11 が出た場合、宣言が壊れているのではなく**接続ロールを取り違えている**可能性をまず疑うこと。

```sh
R2DB_CONTROL_DSN="$<UPPER_SNAKE_RESTORED_WRITER_DSN_ENV>" \
R2DB_PLATFORM_SCHEMA="<REGISTRY_SCHEMA_NAME>" \
  ./.venv/bin/python -m r2db_api.ops verify-declarations
```

- `$<UPPER_SNAKE_RESTORED_WRITER_DSN_ENV>` は、復元先 DB へ**書き手ロール (`api_role`/`controlplane_role` のいずれか) として**接続する DSN を保持する環境変数名である (例: `R2DBSVC_RESTORE_VERIFY_API_DSN`) — 手順 2/3 の owner ロール DSN とは**別物**。

exit 0 (全検査 pass) を確認する。0 以外なら `docs/design/PHASE8_EFFECTIVE_BOUNDS_AND_HYGIENE_V1.md` D-5 の終了コード表に従って読む — **exit 11 (F-13) は上記の書き手ロール取り違えを最初に疑う**。

## 5. 疎通確認 (`tools/deploy_smoke.py`)

配備が実際に応答することを、実ソケット越しに 3 段で確認する。

**前提**: 復元した DB には、段 3 (query) が実施できるだけの entity が存在する想定である (手順 6 の「復元前後で catalog と 1 query の結果が一致すること」の確認自体、復元前に catalog が空でないことを前提にしている)。復元先が空、または別 application を指す DB を誤って復元した場合、段 3 は実施できず、既定では **exit 4** ("stage 3 not performed") になる — これは「壊れた配備」と「空の配備」を区別するための意図的な挙動であり (WP-4 rework、監督裁定 2026-09-06)、復元検証の文脈で意図的に空の DB を検証する場合のみ `--allow-empty-catalog` を付けて exit 0 にする。

```sh
./.venv/bin/python tools/deploy_smoke.py \
  --base-url-env <UPPER_SNAKE_BASE_URL_ENV> \
  --api-key-env <UPPER_SNAKE_API_KEY_ENV>
```

- `<UPPER_SNAKE_BASE_URL_ENV>` / `<UPPER_SNAKE_API_KEY_ENV>` はいずれも**環境変数名**であり、値そのものを引数に書かない (SI-10)。
- 段 1 (`GET /v1/capabilities`) → 段 2 (`GET /v1/catalog`) → 段 3 (1 query) の順に 1 行ずつ出力する。catalog が空、または選んだ entity に field が無く段 3 を実施できない場合、標準エラーに "stage3 skipped: empty catalog" を出して **exit 4** で終える (空の application そのものは壊れた配備ではないが、「検査した」と「検査できなかった」を終了コードだけで区別できるようにするための既定であり、`--allow-empty-catalog` を明示した場合のみ exit 0 になる)。

## 6. 確認すべきこと

- 手順 4 の exit 0 (プラットフォーム DB を復元した場合)。
- 手順 5 の exit 0 (復元後の配備、または復元後のデータを指すよう再配線した配備に対して)。
- **復元前後で対象 DB の catalog と 1 query の結果が一致すること** — 最低限、復元前に読んだ catalog (entity 一覧・field 一覧) と 1 query の結果行を控えておき、復元後に同じ問い合わせをして比較する。

## 7. 後始末

- 動作確認が済んだら、古い DB を保持する期間 (運用ポリシーで別途定める) の後に削除する。復元検証のためだけに作った一時 DB / 一時ロールは検証後ただちに削除する。
- 一時ファイル (`<DUMP_PATH>`) は実証後に削除する — このファイル自体をリポジトリに置かない。
