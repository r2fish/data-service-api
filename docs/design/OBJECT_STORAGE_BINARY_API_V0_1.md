# オブジェクトストレージ・バイナリ API 設計指示書（候補 v0.2）

- 状態: **候補**。依頼者・設計レビューで確定するまで、共通契約・conformance tests・実装の正本ではない。
- 対象: `r2db-api` と `MitateDB-api` が共有する Data Service API。
- 目的: 画像を含む任意のファイルを、JSON/Base64 ではなくバイト列のまま、認可されたアプリケーションのスコープでアップロード・保存・取得できるようにする。
- 公開規律: 実バケット名、アカウント ID、Cloud project ID、サービスアカウント、鍵、エンドポイント、署名付き URL は記載しない。
- **A-1 決定（依頼者、2026-09-11）**: security 強度を最優先し、object storage は application ごとの private bucket、application 専用 provider identity、application 専用の object-capable 実行単位で隔離する。application-facing 実行単位は他 application の bucket 資格情報、広い親資格情報、他 application 用の downscoped credential を発行できる資格情報のいずれも保持してはならない。
- **A-2〜B-12 決定（依頼者、2026-09-11）**: §0 の全推薦案を採用する。

## 0. 確定した設計判断

| ID | 決定 |
| --- | --- |
| A-1 | application ごとの private bucket、provider identity、object-capable 実行単位で provider 側の隔離を強制する。 |
| A-2 | conformance port は transport 非依存に `bytes + ObjectMetadata` を受け渡す。HTTP はこの port の binding であり、HTTP/socket 固有の streaming・header・切断試験を別条件で追加する。port は次版（v1.16）へ加算的に拡張し、6 adapter 全てが実装する。 |
| B-1 | upload は任意の `Idempotency-Key` を受ける。指定時は bytes の content digest と正規化 metadata を同じ request digest に含め、同一 key の同時送信を直列化する。 |
| B-2 | destructive な削除は `POST /v1/objects/{object_id}/delete` とし、既存 destructive-confirmation の JSON (`destructive` と `confirmation`) を用いる。 |
| B-3 | bytes を返す成功応答も `X-Request-Id` を必須で返す。 |
| B-4 | 完全性値は RFC 9530 `Content-Digest` の canonical string に統一する。JSON descriptor と HTTP header は同じ表現を用いる。 |
| B-5 | `object_bytes`、`object_metadata_bytes`、`object_requests_per_minute`、`object_transfers` を独立した limit class とし、各々を `limits` と `limit_enforcement` に載せる。 |
| B-6 | 認証前には既存の concurrency と小さい byte bound を維持する。認証成功後だけ object upload の大きい `object_bytes` bound を適用する。 |
| B-7 | upload/download 中にも authorization propagation bound 以内の周期で再認可し、失効を観測したら転送を中断する。 |
| B-8 | メタデータ状態は `pending → available → deleting → deleted` とし、cleanup 不能は `cleanup_failed` に記録して回復対象にする。 |
| B-9 | upload、download、delete は runtime と developer の両方が実行できる。既存 data-plane delete との権限対称性を保つ。 |
| B-10 | 初版の object endpoint は dry-run と request budget の適用対象外であることを契約に明記する。 |
| B-11 | filename を安全に正規化して保存・返却し、download は RFC 6266/5987 に従う `Content-Disposition: attachment` を生成する。 |
| B-12 | durable audit の vocabulary に `upload_object`、`download_object`、`delete_object` と target kind `object` を追加する。 |

## 1. 問題と範囲

現行 API は `application/json` の構造化データ API であり、任意バイト列のアップロード・取得、オブジェクトの内容種別、完全性、永続的なファイル識別子を定義していない。JSON 文字列へ Base64 エンコードする方法は、バイナリ API でもオブジェクトストレージでもなく、転送量とメモリ消費を増やすため本機能の実現方法にしない。

本候補は次を追加する。

1. バイト列を受け取るアップロード API。
2. 保存済みバイト列を返す取得 API。
3. アプリケーション由来のスコープによる、テナント間の完全なオブジェクト隔離。
4. `Content-Type`、元ファイル名、バイト数、SHA-256 を含む検証済みメタデータ。
5. r2db-api の Cloudflare R2（S3 互換 API）と、MitateDB-api の Google Cloud Storage（GCS）を用いる、同じ公開契約に対する別実装。

初版の範囲外は、公開 URL、クライアント直送の署名付き URL、multipart/resumable upload、部分取得（Range）、サムネイル生成、ウイルススキャン、コンテンツ変換、一覧検索である。これらは後の加算的 capability として検討する。初版でも運用上の削除・保持が必要になるため、削除は §3 の候補 API に含める。

## 2. 守るべき安全性

既存 Security Invariants の適用結果を以下に固定する。必要ならレビュー時に新しい invariant の要否を判断するが、現時点では既存の認証・認可・有限資源・非開示・監査の原則で表せる。

| 性質 | 要求 |
| --- | --- |
| 認証・認可 | 全操作は既存のアプリケーション bearer credential を先に検証する。匿名アクセス、バケット資格情報のクライアント配布、認可より先の存在確認を認めない。 |
| スコープ隔離 | オブジェクトの所有 application はサーバが認証文脈から導出する。クライアントは object key、application ID、bucket を指定できない。別アプリの object ID は存在有無を漏らさず `NOT_FOUND` とする。加えて provider は application 専用 identity に当該 application の private bucket だけを許可する。 |
| 有限資源 | バイト数、同時転送数、メタデータ長、ストリーム読み書き時間を deployment が宣言・強制する。HTTP 本文を全量メモリへバッファしない。 |
| 完全性 | サーバは受信中に SHA-256 を計算し、送信者が `Content-Digest: sha-256=:<base64>:` を指定した場合は一致を必須とする。取得時は保存済みハッシュを同じ `Content-Digest` 表現で返す。 |
| コンテンツの扱い | `Content-Type` は保存・返却するが、実行・変換・解釈しない。ブラウザ向け取得応答には `X-Content-Type-Options: nosniff` と安全な `Content-Disposition: attachment` を付ける。 |
| 失敗時の後始末 | 上限超過、切断、ハッシュ不一致、バックエンド失敗では未確定オブジェクトを利用可能状態にしない。可能な限り削除し、削除失敗は運用上検知できる状態にする。 |
| 監査・非開示 | 成功、拒否、削除を既存の監査規則に従って記録する。監査・エラーにはファイル内容、オブジェクトキー、認証情報を含めない。 |

## 3. 公開契約の候補

契約版は、レビュー確定後に加算的な `1.x.0` とする。ここでは版番号を先に固定しない。

新 capability 名は `object_storage` とする。capability document は少なくとも次を返す。

```json
{
  "capabilities": {
    "object_storage": {
      "status": "enabled",
      "operations": ["upload", "download", "delete"]
    }
  },
  "limits": {
    "object_bytes": 52428800,
    "object_metadata_bytes": 8192,
    "object_requests_per_minute": 60,
    "object_transfers": 16
  }
}
```

数値は例であり、配備値ではない。`object_bytes` は JSON 用の `request_bytes` とは独立した limit class とする。`object_transfers` は同時に実データを読み書きできる数であり、既存の JSON リクエスト用 concurrency と混同しない。

### 3.1 API 経路

| 操作 | 経路 | 成功結果 | 権限 |
| --- | --- | --- | --- |
| アップロード | `POST /v1/objects` | `201 ObjectDescriptor` | runtime または developer |
| メタデータ取得 | `GET /v1/objects/{object_id}/metadata` | `200 ObjectDescriptor` | 同一 application |
| バイト列取得 | `GET /v1/objects/{object_id}` | `200`、保存済み bytes | 同一 application |
| 削除 | `POST /v1/objects/{object_id}/delete` | `204` | runtime または developer。既存 destructive confirmation が必須 |

`object_id` はサーバが生成する不透明な識別子であり、URL-safe UUID/ULID 形式など、契約で一つの構文を定義する。クライアント指定の object key は受け取らない。ID の推測耐性を認可の代替にしてはならない。

### 3.2 アップロード要求

`POST /v1/objects` の本文は raw bytes とする。`multipart/form-data` は用いない。メタデータは次の HTTP ヘッダーで与える。

| ヘッダー | 規則 |
| --- | --- |
| `Content-Type` | 必須。空、ワイルドカード、複数値を拒否する。MIME 型の allow-list は初版で設けないが、構文は検証する。 |
| `Content-Length` | 任意。存在するときは正の整数か 0。実測バイト数を信頼する代わりには使わない。 |
| `Content-Digest` | 任意の RFC 9530 `sha-256=:<base64>:`。指定された場合は受信 bytes と一致しなければならない。 |
| `Idempotency-Key` | 任意。指定された場合は content digest と正規化 metadata を含む request digest に結び、既存 idempotency の再送・競合・同時送信直列化規則を適用する。 |
| `Content-Disposition` | 任意。`filename` があるときだけ元ファイル名として採用する。制御文字・パス区切り・過長値を拒否し、安全な文字列として保存する。 |

成功時の `ObjectDescriptor` は次である。

```json
{
  "object_id": "opaque-server-generated-id",
  "content_type": "image/png",
  "filename": "photo.png",
  "size_bytes": 12345,
  "content_digest": "sha-256=:base64-encoded-digest:",
  "created_at": "RFC3339 timestamp",
  "request_id": "existing-request-correlation-id"
}
```

オブジェクトの bytes とメタデータは、成功応答を返す前に両方が永続化済みでなければならない。失敗時は `ObjectDescriptor` を返さない。すべての成功応答は `X-Request-Id` を返す。

### 3.3 取得・削除

バイト列取得は保存時の `Content-Type`、`Content-Length`、`Content-Digest`、`X-Request-Id`、RFC 6266/5987 に従う安全な `Content-Disposition: attachment` を返す。エラーを JSON に包んだ 200 応答や、ストレージのリダイレクトを返してはならない。バケット内の実キー、プロバイダ URL、署名、内部例外は公開しない。

削除は「利用可能なオブジェクトを取得不能にする」ことを成功条件とする。最初の confirmation 不足 request は既存形式の `DESTRUCTIVE_CONFIRMATION_REQUIRED` を返し、次の request が `destructive: true` と返された phrase を JSON で echo したときだけ実行する。オブジェクトストレージの物理削除とメタデータ更新の原子的な分散トランザクションは期待できないため、状態機械（`pending`、`available`、`deleting`、`deleted`、`cleanup_failed`）を実装側に持つ。クライアントに見せるのは `available` だけである。削除済みまたは他 application の ID は、ともに `NOT_FOUND` に正規化する。

## 4. 保存モデル

公開 object ID とプロバイダ object key は別物とする。プロバイダ key はサーバだけが、次の論理構造から生成する。

```
applications/<server-derived-application-id>/objects/<server-generated-object-id>
```

実装は raw object と、アプリケーションの DB に置くメタデータ行を対応付ける。メタデータ行は少なくとも、公開 ID、所有 application、provider key、content type、filename、size、canonical `Content-Digest`、作成時刻、状態を持つ。provider key は通常の API 応答、監査、エラーに含めない。この非開示は衛生であり、隔離の防御根拠ではない。防御根拠は application 専用 provider identity が他 bucket に届かないことである。

アップロードは次の順序で行う。

1. HTTP 境界で認証前 concurrency と小さい byte bound を適用し、本文を読む前に認証・能力・転送枠を確認する。
2. `pending` メタデータを永続化する。
3. ストリームを最大 `object_bytes` まで読み、同期 provider SDK の呼出しは threadpool に offload しながら `Content-Digest` を計算して private bucket へ送る。
4. バイト数と任意の `Content-Digest` を検証し、authorization propagation bound 以内の周期で再認可する。
5. `available` メタデータを永続化して成功応答を返す。

3〜5 に失敗した場合、provider object を削除してから問題応答を返す。削除に失敗した場合は `cleanup_failed` を永続化し、公開されない cleanup worker が再試行する。

## 5. 実装ごとの責務

### 5.1 r2db-api: Cloudflare R2

- S3 互換 API を使う専用 storage adapter を置く。アプリケーション DB 接続や公開 HTTP handler に S3 操作を散在させない。
- application ごとに非公開 R2 bucket と、その bucket 専用の API token/credential を provision する。object-capable API 実行単位は一 application だけを serve し、当該 bucket の `GetObject`、`PutObject`、`DeleteObject` 以外を provider に拒否される credential だけを得る。
- bucket 作成、credential 発行・更新・失効は application-facing API の外にある provisioning/control 経路だけが行う。R2 temporary credential を使う場合も、全 bucket に届く親 token は application-facing 実行単位に置かず、当該 bucket にしか届かない親から発行する。
- endpoint、bucket、access key ID、secret access key、最大オブジェクトサイズ、転送上限は external secret manager または root-only の実行環境から渡す。ここで参照できる secret は当該 application 用だけである。
- R2 の S3 API 互換性を adapter の結合テストで確認する。SDK は実装時に採用根拠、タイムアウト、再試行、multipart 閾値を明文化する。

### 5.2 MitateDB-api: Google Cloud Storage

- GCS 専用 storage adapter を置く。Cloud Run ではサービスアカウントまたは Workload Identity を使い、JSON サービスアカウント鍵をアプリ設定・イメージ・リポジトリに置かない。
- application ごとに Uniform bucket-level access を有効にした private GCS bucket と、当該 bucket 専用の Cloud Run service account / Workload Identity を provision する。object-capable 実行単位は一 application だけを serve し、他 bucket への権限を持たない。
- `MITATEDB_OBJECT_STORAGE_BUCKET`、`MITATEDB_OBJECT_STORAGE_MAX_BYTES`、`MITATEDB_OBJECT_STORAGE_TRANSFERS` を環境設定とする。認証は Application Default Credentials を原則とし、ローカル開発は明示的な安全な認証手順を別途 runbook 化する。application-facing 実行単位に、複数 bucket を扱える service account や downscoped token を発行できる token を配置しない。
- GCS の generation/precondition を利用して、同一 provider key の上書きを防ぐ。

両 adapter は同じ抽象操作（put stream、get stream、head、delete）を持つが、コードや SDK wrapper を peer 間で共有しない。公開 API の振る舞いを conformance tests で揃える。peer-local integration test は、application A の実行 identity が application B の bucket に対して `GetObject`、`PutObject`、`DeleteObject` を provider 自身から拒否されることを実測する。

## 6. HTTP 境界と資源制御

現在の JSON 用 request-byte middleware は、本文を読み切ってから下流へ渡す方式である。バイナリ API では次のように拡張または別 middleware 化する。

1. 経路を識別し、object upload だけをストリーミング転送対象にする。
2. 未認証 request は既存の小さい request byte bound を超えて本文を読まない。Authorization header を認証した request だけが、受信チャンクごとに `object_bytes` を数える streaming 経路へ進む。上限超過時は読み取りを中止し `LIMIT_EXCEEDED`（`limit_class: object_bytes`）を返す。
3. 既存の pre-auth concurrency slot を認証前から獲得する。認証後には deployment 全体で効く `object_transfers` 枠を獲得し、接続切断・例外も含め必ず解放する。複数 process が一 base URL を serve する deployment で process-local 枠しか持てない場合、`limit_enforcement.object_transfers` は `deployment_required` と宣言する。
4. JSON endpoint の既存 `request_bytes` 挙動は変更しない。
5. HTTP client と provider SDK の接続・読取・全体時間には有限 timeout を設ける。同期 provider SDK の stream read/write は event loop 上で実行せず threadpool に offload する。転送中も authorization propagation bound 以内に再認可する。

## 7. conformance tests の候補

共通仕様を確定した後、transport 非依存 port v1.16 を使う次のテストを `conformance-tests/` に追加する。各テストは in-process / HTTP / socket × 2 peer の全6 adapter に対して同じ期待結果を検証する。header、streaming、proxy、切断は HTTP/socket 専用条件で追加する。

1. 任意 bytes（NUL、非 UTF-8、画像らしい bytes を含む）を upload し、取得 bytes が完全一致する。
2. 保存・取得メタデータ（content type、filename、size、Content-Digest）が一致する。
3. `Content-Digest` 一致は成功し、不一致は拒否され、取得可能な object を残さない。
4. `object_bytes` を 1 byte 超える upload は `LIMIT_EXCEEDED` になり、下流 storage 呼出し・メタデータのどちらも残さない。
5. application A の object を application B が取得・メタデータ取得・削除できず、いずれも `NOT_FOUND` になる。
6. capability が `unavailable` の deployment は、認証後に `CAPABILITY_UNSUPPORTED` を返し、本文を storage へ送らない。
7. idempotency key を伴う再送・同時送信は一 object に収束し、異なる bytes/metadata での同一 key は `CONFLICT` となる。
8. destructive confirmation が無い削除は副作用なく拒否され、正しい confirmation を伴う削除だけが実行される。
9. 同一 object ID の再利用、provider failure、削除後取得、`pending`/`cleanup_failed` object の非公開性を仕様どおりにする。
10. 取得応答が provider URL・provider key・credential を漏らさず、`Content-Digest`、`Content-Disposition`、`X-Request-Id` を含む正しい security headers を持つ。
11. HTTP/socket 専用で、chunked streaming、未認証の小さい byte bound、切断、転送中 revoke、threadpool offload を検証する。

provider を実際に使う認証設定の検証は peer-local integration test と deployment runbook の責務とし、共通 conformance suite が実在するクラウドアカウントを要求してはならない。

## 8. 運用値・後続 capability の検討事項

§0 の API・安全性に関する判断は確定した。実装前に配備ごとの値と運用手順を決める。

1. 初期 deployment の `object_bytes`、`object_metadata_bytes`、`object_requests_per_minute`、`object_transfers`、認証前 byte bound、timeout、再認可周期。
2. `cleanup_failed` の再試行間隔、監視、alert、保持・法的保全の手順。
3. object metadata を各 application DB に置く。schema/migration の詳細と、provisioning/control 経路が application bucket/identity をどの DB declaration と結び付けるか。
4. マルウェア対策を upload 完了前の必須 gate にするか。初版は対象外と明示し、必要なら `pending_scan` 状態を持つ別 capability とする。

## 9. 実施順序

1. A-1 の provider 側分離を前提に、既存の複数 application を一 process で serve する配備を、object-capable endpoint では application 専用の実行単位へ分割する provisioning/deployment 設計を確定する。各 peer-local integration test で provider 自身が越境を拒否することを実測する。
2. §8 の配備値・運用手順をレビューし、実行環境ごとに確定する。
3. 該当する Security Invariants と threat model の適用を確定する。
4. 共通契約、capability/limit、エラー、操作カタログを更新する。
5. conformance tests を追加し、実装前に失敗することを確認する。
6. r2db-api（R2 adapter、メタデータ、HTTP streaming、設定、local tests）を実装する。
7. MitateDB-api（GCS adapter、メタデータ、HTTP streaming、設定、local tests）を実装する。
8. conformance tests、各 peer の unit/integration tests、公開リポジトリ秘密検査を実行する。
9. 実クラウド環境については、非公開 bucket と最小権限を用いた deployment verification を別 runbook に従って実施する。
