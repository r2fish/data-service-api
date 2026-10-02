# オブジェクトストレージ・バイナリ API 設計指示書（候補 v0.5）

## 版数・位置づけ (番号なし。§0〜§9 は v0.2 の番号を保つ)

| 版 | 日付 | 状態 |
|---|---|---|
| v0.1 | 2026-09-11 以前 | 推薦案を含む初稿。推薦案と退けた選択肢の記録は repository に無い (観察。復元しない。§12.1) |
| v0.2 | 2026-09-11 | 依頼者決定 A-1〜B-12 を反映 (下の 2 行と §0 確定した設計判断の表) |
| v0.3 | 2026-10-02 | 設計レビュー 1 回目 (観点 A / B の並列 2 起動) と再確認 (指定なし 1 起動) を反映。依頼者裁定待ち Q-0〜Q-5 (§11)。設計レビュー 2 回目は裁定反映後。現状との突き合わせは §10、反映の一覧は §12 |
| v0.4 | 2026-10-02 | 依頼者裁定 Q-0〜Q-5 の反映 (裁定の逐語は §11 の冒頭、帰結の一覧は §12 の「v0.4 の帰結の一覧」)。設計レビュー 2 回目の対象版 |
| v0.5 | 2026-10-02 | 設計レビュー 2 回目 (観点 A / B の並列 2 起動) の反映。Q-6〜Q-9 は依頼者指示により推奨で進めた。再確認は次 (反映の一覧は §12 の「設計レビュー 2 の反映の一覧」) |

- 位置づけ: 台帳 `RM` R-36 の設計文書。状態は候補のまま (未実装・未宣言・非正本) で、v0.3 でも変えない。
- v0.3 の印: 設計レビュー 1 の反映箇所には【v0.3 2026-10-02 設計レビュー 1 反映 M-n】(S-n は §10 の行) を、依頼者決定と現状の食い違いには【註 2026-10-02】を付す。v0.2 の行は消さず、判定を変える箇所は旧文の後に新文と根拠を続ける。
- 再確認の印: 再確認 (指定なし 1 起動) の反映箇所には【v0.3 2026-10-02 再確認反映 RC-n】を付す。RC-n は本文書の局所 ID であり、一覧は §12 の「再確認の反映 (RC-1〜RC-21)」。判定を変える箇所は旧文を残し、印を付けた新文を続ける。
- ID の出所: 本文書の SI-N は `security/SECURITY_INVARIANTS_V1.md`、C-N は `conformance-tests/CONDITIONS.md`、R-N と P-N は台帳 `RM` の ID である。M-n・S-n・Q-n・O-n は本文書の局所 ID (§10〜§12、§7.1)。O-n は仮番号であり、conformance 条件の正式 ID は契約確定時に `conformance-tests/CONDITIONS.md` で採番する。
- provider (Cloudflare R2 / GCS / Cloud Run) と RFC の挙動に依る記述は、v0.3 の時点で公式文書を読めていないため全て「未確認」である (§12.1)。
- v0.4 の印: 依頼者裁定 (2026-10-02。逐語は §11 の冒頭) の帰結の反映箇所には【v0.4 2026-10-02 依頼者裁定の帰結 Q-n】を、§11 の各 Q の末尾には【裁定 2026-10-02】を付す。判定を変える箇所は旧文を残し、印を付けた新文を続ける。状態は v0.4 でも候補のまま (契約・conformance・実装はまだ。Q-0 の帰結)。provider と RFC の挙動は v0.4 でも未確認である。
- v0.5 の印: 設計レビュー 2 回目 (観点 A / B の並列 2 起動) の反映箇所には【v0.5 2026-10-02 設計レビュー 2 反映 N-n】を、新たに依頼者裁定級とした Q-6〜Q-9 (§11) の帰結には【v0.5 2026-10-02 設計レビュー 2 反映 Q-n】を付す。N-n は本文書の局所 ID であり、出所 (観点 A の指摘番号 A2-n、観点 B の指摘番号 B2-n) と反映した節の一覧は §12 の「設計レビュー 2 の反映の一覧」。判定を変える箇所は旧文を残し、印を付けた新文を続ける。Q-6〜Q-9 は、依頼者指示 (§11 の冒頭の逐語) を本件にも及ぶものと読み (監督の読み)、推奨で進めた。状態は v0.5 でも候補のまま。provider・RFC・nginx の挙動は未確認、uvicorn / starlette の挙動は本環境のソースで確認、実行は未確認である (§12.1)。

- 状態: **候補**。依頼者・設計レビューで確定するまで、共通契約・conformance tests・実装の正本ではない。
- 対象: `r2db-api` と `MitateDB-api` が共有する Data Service API。
- 目的: 画像を含む任意のファイルを、JSON/Base64 ではなくバイト列のまま、認可されたアプリケーションのスコープでアップロード・保存・取得できるようにする。
- 公開規律: 実バケット名、アカウント ID、Cloud project ID、サービスアカウント、鍵、エンドポイント、署名付き URL は記載しない。
- **A-1 決定（依頼者、2026-09-11）**: security 強度を最優先し、object storage は application ごとの private bucket、application 専用 provider identity、application 専用の object-capable 実行単位で隔離する。application-facing 実行単位は他 application の bucket 資格情報、広い親資格情報、他 application 用の downscoped credential を発行できる資格情報のいずれも保持してはならない。
- **A-2〜B-12 決定（依頼者、2026-09-11）**: §0 の全推薦案を採用する。
- 【註 2026-10-02】A-1 は台帳 `RM` R-30 (SI-00 の境界と、1 process が複数 Application の DSN を保持する構成の関係。未着手・依頼者裁定待ち) の一方の答え (serving set を 1 Application に限る) を object-capable 実行単位に先取りしている (§10 の S-13)。1 つの data base URL の背後で application 専用の実行単位へ要求を届ける経路は設計に無く、§11 の Q-2 で依頼者裁定待ちである。
- 【v0.4 2026-10-02 依頼者裁定の帰結 Q-2】到達経路は案 (ii) に確定した (§3.1 の Q-2 の段落)。JSON 経路の serving set は台帳 `RM` R-30 の裁定に委ねる。

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

【註 2026-10-02】決定の本文は変えない。現状 (契約 1.14.0、port v1.21) との食い違いだけを記す。出所の詳細は §10。

- A-2: 「次版（v1.16）」の版番号は陳腐化した。現行 port は v1.21 (`conformance-tests/adapter.py:1054`、台帳 `RM` R-108) であり、次版は v1.22 以降である。adapter は 6 のまま。bytes を運ぶ既存の経路は WireEntry (`adapter.py:1053-1087`。wire 4 plug 限定で、in-process は AssertionError) と `operation_catalog_document() -> bytes` (`adapter.py:3148`) の 2 つで、in-process adapter に bytes の port method は無い (§10 の S-1。設計レビュー 1 反映 M-22)。
- B-1: 契約の idempotency は JSON request の field `idempotency_key` であり (`spec/data-service-api.v1.json:1304-1307`、`:850-852`)、HTTP header `Idempotency-Key` は契約に無い。raw bytes 本文に request field は置けないので、B-1 は契約の idempotency 節への header 形式の新設になる。digest の材料 (bytes の content digest + 正規化 metadata) も契約側の定義になる (§3.2.1、§10 の S-7)。
- B-2: `destructive_confirmation.applies_to` (`spec/data-service-api.v1.json:678-683`) は閉じた列挙であり、object 削除の追加は契約の改版になる。本文の形式は継承できる (§10 の S-6)。
- B-3: spec に `X-Request-Id` は無い。`request_id` は body の field (`spec/data-service-api.v1.json:871` 等) と audit の field である。両 peer の http.py は実装として `x-request-id` 応答 header を返す (§10 の S-8)。B-3 は peer 実装の header を契約へ昇格させる決定になる。bytes 応答には body の `request_id` が置けないので、header が唯一の経路である。
  - 【v0.5 2026-10-02 設計レビュー 2 反映 Q-9】B-3 の契約化の範囲は「object_storage の 4 操作の全応答 (成功・失敗) が `X-Request-Id` にその要求自身の `request_id` を運ぶ」(object_storage 条件付きの義務。既存操作は変えない) とする (§3.2 の Q-9、§11 の Q-9)。
- B-5: `limits.classes` は閉じた語彙 17 (`spec/data-service-api.v1.json:929-947`。`:323` は語彙外の key を非適合とする) であり、4 class の追加は `limits.classes` の拡張 (契約の版上げ) になる (§10 の S-4)。class ごとの定義は §6.1。時間の bound は §11 の Q-3、総量の bound は §11 の Q-5 で依頼者裁定待ち。
  - 【v0.4 2026-10-02 依頼者裁定の帰結 Q-3】時間の bound は `execution_ms` が表す (class を増やさない。§2、§6.1)。
  - 【v0.4 2026-10-02 依頼者裁定の帰結 Q-5】総量の bound の class は足さず、§8 の運用値に置く (§2)。
  - 【v0.5 2026-10-02 設計レビュー 2 反映 Q-6】上の Q-3 の註を改める (旧文は残す): 転送時間の bound は転送専用の class `object_transfer_ms` が表す (B-5 の 4 class を超える加算的な 1 class。§6.1 の Q-6、§11 の Q-6)。
- B-7: 両 peer が宣言する `authorization_propagation_bound_ms` は 0 である。B-7 との関係は §11 の Q-4 で依頼者裁定待ち。
  - 【v0.4 2026-10-02 依頼者裁定の帰結 Q-4】(a)。object_storage を提供する deployment は正の bound を宣言する (§6 の 5)。
- B-12: audit の operations / target_kinds は実装が `capabilities().audit_query.operations / .target_kinds` で宣言する語彙で、契約は固定 enum を持たない (`spec/data-service-api.v1.json:1011-1012`)。B-12 は「契約の語彙に追加」ではなく「両 peer が宣言に加え、conformance が宣言と実挙動の一致を見る」形になる (§10 の S-5、§7.1 の O-20)。`get_object_metadata` の追加は §3 の M-14 の註。

## 1. 問題と範囲

現行 API は `application/json` の構造化データ API であり、任意バイト列のアップロード・取得、オブジェクトの内容種別、完全性、永続的なファイル識別子を定義していない。JSON 文字列へ Base64 エンコードする方法は、バイナリ API でもオブジェクトストレージでもなく、転送量とメモリ消費を増やすため本機能の実現方法にしない。

本候補は次を追加する。

1. バイト列を受け取るアップロード API。
2. 保存済みバイト列を返す取得 API。
3. アプリケーション由来のスコープによる、テナント間の完全なオブジェクト隔離。
4. `Content-Type`、元ファイル名、バイト数、SHA-256 を含む検証済みメタデータ。
5. r2db-api の Cloudflare R2（S3 互換 API）と、MitateDB-api の Google Cloud Storage（GCS）を用いる、同じ公開契約に対する別実装。

初版の範囲外は、公開 URL、クライアント直送の署名付き URL、multipart/resumable upload、部分取得（Range）、サムネイル生成、ウイルススキャン、コンテンツ変換、一覧検索である。これらは後の加算的 capability として検討する。初版でも運用上の削除・保持が必要になるため、削除は §3 の候補 API に含める。

【v0.3 2026-10-02 設計レビュー 1 反映 S-16】実需: 台帳 `RM` §3.2 の突合表 (`RM`:274) は R-36 を「部分的」とする (Mitate `docs/remaining-work-index.md` §将来設計・保留「添付ファイル・画像 — F2 とは別工程として保留」、`docs/design/agent-entry-record.md` §6.1)。data-service-api への具体的な要件は未確定であり、本文書は推測で実需を足さない。着手条件の充足は §11 の Q-0 で依頼者裁定待ち。

【v0.4 2026-10-02 依頼者裁定の帰結 Q-0】依頼者裁定 (2026-10-02、§11 の冒頭) を、監督の読みで Q-0 の (a) (充足とみなし設計レビュー 2 回目へ進む) と読む (§11 の Q-0)。状態は候補のまま。

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

【v0.3 2026-10-02 設計レビュー 1 反映 M-22】「コンテンツの扱い」行の「ブラウザ向け取得応答」は「全ての download 応答」と改める (B-11 は download の `Content-Disposition: attachment` を一律に生成する。行は残す)。download 応答の `Content-Type` を client がどう分類するかは §11 の Q-1 で依頼者裁定待ち。

【v0.4 2026-10-02 依頼者裁定の帰結 Q-1】download 応答の分類は (甲)+(乙) に確定した (分類規則は §3.3 の Q-1、upload の拒否は §3.2 の Q-1)。

【註 2026-10-02】「有限資源」行の「ストリーム読み書き時間」を B-5 の 4 class のどれが表すかは未決であり、§11 の Q-3 で依頼者裁定待ち。総保存量・object 数の上限は §11 の Q-5 で依頼者裁定待ち。

【v0.4 2026-10-02 依頼者裁定の帰結 Q-3】「有限資源」行の「ストリーム読み書き時間」は `execution_ms` が表す (受付から available / 送信完了まで)。超過は `LIMIT_EXCEEDED` (`limit_class: execution_ms`)。download で header 送出後なら接続の異常終了 (§3.3 の M-6)。計測開始と待ち (slot / 枠の待ち) の扱いは台帳 `RM` R-42 の裁定に従う。R-42 が決まるまで、本設計は「受付 = 認証成功時点」を仮の起点とする (仮)。定義は §6.1 の Q-3 の段落。

【v0.5 2026-10-02 設計レビュー 2 反映 Q-6】上の Q-3 の段落の「ストリーム読み書き時間は `execution_ms` が表す」を改める (旧文は残す): upload / download の転送時間は転送専用の class `object_transfer_ms` が表す。起点 = `object_transfers` 枠の獲得時点、終点 = available への遷移 / 送信完了であり、台帳 `RM` R-42 と独立する。定義は §6.1 の Q-6 の段落 (§11 の Q-6)。

【v0.4 2026-10-02 依頼者裁定の帰結 Q-5】「有限資源」行の総保存量・object 数の根拠: SI-08 (`security/SECURITY_INVARIANTS_V1.md`) の「object creation rate or count」を rate (`object_requests_per_minute`) で満たす (台帳 `RM` P-5)。class は足さず、provider 側 quota / 予算 alert と object 数・総容量の監視を §8 の運用値に置く。

【v0.5 2026-10-02 設計レビュー 2 反映 N-15】上の Q-5 の段落に足す: provider 側の hard quota の有無は未確認である。総保存量の hard な bound (provider quota または実装側の検査) を配備値として必須にする (§8)。alert だけでは SI-08 (`security/SECURITY_INVARIANTS_V1.md`) の Verification を総量について満たさない。class は足さない (Q-5 のまま)。`security/CONTROL_MAPPING.md` の SI-08 行に残余として記録する (作業機。§9 の新 5)。

### 2.1 SI と conformance 条件の対応

【v0.3 2026-10-02 設計レビュー 1 反映 M-21】上の表の各性質に、適用する既存 SI と conformance 条件 (仮 O-n、§7.1) を対応させる。新しい invariant は足さない (`CLAUDE.md` の Security Invariants 節)。

| 性質 | 適用する SI (`security/SECURITY_INVARIANTS_V1.md`) | conformance 条件 (仮 O-n、§7.1) |
| --- | --- | --- |
| 認証・認可 | SI-06、SI-07、SI-03 (runtime / developer の対称は B-9)、SI-15、SI-13 (B-7。§11 の Q-4)。【v0.3 2026-10-02 再確認反映 RC-12】SI-03 は「object 操作は schema 変更の経路にならない (B-9 の対称性の根拠ではない)」に言い換える (旧文は残す) | O-6、O-12、O-13 |
| スコープ隔離 | SI-01、SI-00 (A-1。provider 側の隔離は deployment evidence)、SI-12 (bucket 資格情報を client に渡さない) | O-5、O-17、O-18 |
| 有限資源 | SI-08 | O-4a、O-4b、O-11、O-15、O-16 |
| 完全性 | SI-05 (header 値の検証境界)、SI-11。【v0.3 2026-10-02 再確認反映 RC-12】SI-11 は atomic と宣言する upload / delete に掛かる | O-1、O-2、O-3、O-22 |
| コンテンツの扱い | SI-05 (header 値の検証境界)。nosniff・attachment・no-transform を直接に述べる SI の文言は無い (新設しない) | O-10、O-23 |
| 失敗時の後始末 | SI-11、SI-14 (`cleanup_failed` は security-control failure として監査)。【v0.3 2026-10-02 再確認反映 RC-12】SI-11 は atomic と宣言する upload / delete に掛かる | O-9、O-14、O-19。【v0.3 2026-10-02 再確認反映 RC-2】O-19b |
| 監査・非開示 | SI-14、SI-10 | O-10、O-20 |
| (監督 2026-10-02 追記) 認証・認可 (upload 中の失効) / 失敗の形 | SI-13 / SI-05、SI-10 | O-27 / O-28 (wire 条件。N-17 の obligation 対応の候補に入る) |
| 削除 (B-2) | SI-09 | O-8 |

【v0.4 2026-10-02 依頼者裁定の帰結 Q-1 / Q-3】§7.1 に足した条件の対応: O-24 は「コンテンツの扱い」(SI-05)、O-25 は「有限資源」(SI-08) に加える (上の表の行は残す)。

【v0.5 2026-10-02 設計レビュー 2 反映 N-17】上の表の条件の列に足す (行は残す): 「完全性」に O-7 (SI-11)、「有限資源」に O-21 (SI-08)、「スコープ隔離」に O-26 (SI-00・SI-06・SI-14。いずれも `security/SECURITY_INVARIANTS_V1.md`)。

【v0.3 2026-10-02 再確認反映 RC-13】下の案は非網羅の例示。確定時に §7.1 の O-n 全件と 1 対 1 で対応させる。B-3 (X-Request-Id) が全成功応答に掛かるなら unconditional に置く。

【v0.5 2026-10-02 設計レビュー 2 反映 N-17】上の RC-13 の「§7.1 の O-n 全件と 1 対 1 で対応させる」を改める (旧文は残す): 契約の義務 (obligation) は version_binding の文と 1 対 1 とし (`spec/data-service-api.v1.json:287`)、各 obligation にそれを検証する O-n (6 adapter / wire) を 1 つ以上対応させる。peer-local / deployment の O-n (O-17、O-18、O-19、O-19b、O-21、O-26) は obligation にせず、`security/CONTROL_MAPPING.md` の行に対応させる。B-3 の範囲は §11 の Q-9 のとおり (object_storage 条件付きの義務。上の「全成功応答に掛かるなら unconditional に置く」には当たらない)。

`versioning.obligations` に置く object_storage 条件付き行の案 (版番号と従属判断の番号は契約確定時に決める。§3 の「版番号を先に固定しない」に従う):

```json
{
  "version": "1.x.0",
  "subordinate_ruling": "(未定)",
  "unconditional": [],
  "conditional": [
    {"obligation": "object_bytes_round_trip_exactly", "capability": ["object_storage"]},
    {"obligation": "object_content_digest_verified_on_upload_and_download", "capability": ["object_storage"]},
    {"obligation": "object_cross_application_access_is_not_found", "capability": ["object_storage"]},
    {"obligation": "object_non_available_states_are_not_found", "capability": ["object_storage"]},
    {"obligation": "object_delete_requires_destructive_confirmation", "capability": ["object_storage"]},
    {"obligation": "object_download_declares_content_length_and_aborts_on_failure", "capability": ["object_storage"]},
    {"obligation": "object_limit_classes_in_limits_and_limit_enforcement", "capability": ["object_storage"]},
    {"obligation": "object_operations_in_declared_audit_vocabulary", "capability": ["object_storage"]}
  ]
}
```

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

【v0.5 2026-10-02 設計レビュー 2 反映 Q-6】上の `limits` の例に転送専用の class `object_transfer_ms` を足す (例は残す。値は配備値)。agent が必要な最低速度 = `object_bytes` / `object_transfer_ms` を宣言から導けることを契約文に書く (§6.1 の Q-6)。

【v0.3 2026-10-02 設計レビュー 1 反映 M-14】操作名を 1 組にする。`upload_object` / `download_object` / `get_object_metadata` / `delete_object` を、capability の `operations`、操作カタログの `name`、監査の operations に共通で使う。上の例の `["upload", "download", "delete"]` はこの 4 語に読み替える (例は残す)。B-12 の 3 語はそのまま用い、`get_object_metadata` は B-12 の列挙への追加である。metadata 取得も監査する (query と同じ扱い)。

【v0.3 2026-10-02 設計レビュー 1 反映 S-9】`object_storage` は `common_baseline` (1.9.0 の floor) の外に置く。置かないと 1.9.0 の規則で全 peer に必須になる (§10 の S-9)。conformance 条件は PROVIDED / ABSENT の分岐で書く (§7.1)。

【v0.3 2026-10-02 設計レビュー 1 反映 S-10】操作カタログの案: OperationCatalogEntry (`spec/data-service-api.v1.json:2069`) に `request_media_type` / `response_media_type` を足し、bytes の操作 (upload の request、download の response) の `request_schema` / `response_schema` は null とする (§10 の S-10)。

【v0.3 2026-10-02 再確認反映 RC-9】S-10 の註: upload の request_schema が null のため、header の要件は OperationCatalogEntry に足す `request_headers` (名前 / 必須か / 構文の参照) の記述で agent に示す案。確定は設計レビュー 2。

【v0.5 2026-10-02 設計レビュー 2 反映 N-3】上の RC-9 の案に `response_headers` (名前 / 必須か / 構文の参照) を足す。download の `Content-Length`・`Content-Digest`・`Content-Disposition`・`X-Request-Id` を載せる。

【v0.5 2026-10-02 設計レビュー 2 反映 N-4】S-10 の註: 現行の操作カタログと reference client では `request_schema: null` は「本文を取らない」を意味する (`conformance-tests/reference_client.py:193-195`)。upload_object の null は `request_media_type` があるときに限り「bytes 本文」と読む、を契約の OperationCatalogEntry.description に書く。値の形の案: upload_object は `request_media_type: "*/*"` と「`errors.content_type` を除く単一の media type」の規則文、download_object は `response_media_type: "stored"` (保存値)、他の 2 操作は省略 (= `media_type`)。`request_headers` / `response_headers` は契約の endpoints の entry 側に置き、操作カタログへ派生させる (`conformance-tests/CONDITIONS.md` C-29)。確定は契約改版の WP。

【v0.3 2026-10-02 再確認反映 RC-12】S-10 の註: 4 操作の `atomicity` の案。`upload_object` = atomic (object は available になるか、ならないか)、`delete_object` = atomic、`download_object` / `get_object_metadata` = none (読み取り)。

### 3.1 API 経路

| 操作 | 経路 | 成功結果 | 権限 |
| --- | --- | --- | --- |
| アップロード | `POST /v1/objects` | `201 ObjectDescriptor` | runtime または developer |
| メタデータ取得 | `GET /v1/objects/{object_id}/metadata` | `200 ObjectDescriptor` | 同一 application |
| バイト列取得 | `GET /v1/objects/{object_id}` | `200`、保存済み bytes | 同一 application |
| 削除 | `POST /v1/objects/{object_id}/delete` | `204` | runtime または developer。既存 destructive confirmation が必須 |

【v0.3 2026-10-02 設計レビュー 1 反映 M-14】4 行の roles は `runtime, developer` とする。「同一 application」は認可の説明として残す。

【v0.3 2026-10-02 設計レビュー 1 反映 M-9】削除行の成功結果 `204` を `200 ObjectDeleteResult` (`application/json`) に改める。根拠: `204` は契約 1.14.0 (a) (`spec/data-service-api.v1.json:40`) と応答分類 (`:895`) で「解釈しない失敗」になり、`conformance-tests/CONDITIONS.md` C-25 も満たせない。`ObjectDeleteResult` は `{object_id, deleted: true, request_id}` で、additionalProperties は false とする。詳細は §3.3。

`object_id` はサーバが生成する不透明な識別子であり、URL-safe UUID/ULID 形式など、契約で一つの構文を定義する。クライアント指定の object key は受け取らない。ID の推測耐性を認可の代替にしてはならない。

【v0.3 2026-10-02 設計レビュー 1 反映 M-14】`object_id` の構文違反は `IDENTIFIER_INVALID` (`identifier_syntax`) とする。存在しない / 他 application / deleted の object は `NOT_FOUND` とする。

【v0.5 2026-10-02 設計レビュー 2 反映 N-5】`object_id` の構文を identifier 構文 (`spec/data-service-api.v1.json:778`) に収まる形に確定する: `o_` + 26 文字の小文字 base32 (Crockford、ULID 相当。英字始まり、[a-z0-9_])。上の「URL-safe UUID/ULID 形式など」を改める (旧文は残す)。identifier_syntax、path の percent-encoding (`spec/data-service-api.v1.json:651`)、destructive の phrase (`spec/data-service-api.v1.json:711`) の規則をそのまま使う。上の「構文違反は `IDENTIFIER_INVALID`」を改め (旧文は残す)、code は既存条件と同じ許容集合 {`IDENTIFIER_INVALID`, `VALIDATION_FAILED`}、`violated_declaration` は `identifier_syntax` で固定する (§3.4 の N-5)。

【註 2026-10-02】`endpoint_fields_note.path` (`spec/data-service-api.v1.json:651`) の placeholder は `{entity}`、`{application_id}`、`{credential_id}` だけである。`{object_id}` の埋め方 (構文・percent-encoding) を契約に足す必要がある (§10 の S-3)。

【v0.5 2026-10-02 設計レビュー 2 反映 N-3】上の註に足す: 実装は object 経路の照合を percent-decoding 前の path (ASGI の raw_path) で行うか、`%2F` を含む segment を拒否する。

【v0.4 2026-10-02 依頼者裁定の帰結 Q-2】到達経路を案 (ii) に確定する (§11 の Q-2、§11.1)。

- data base URL は 1 つ。前段 router が credential から application を引き、当該 application 専用の object-capable 単位へ振り分ける。
- router は bucket 資格情報を持たず、bytes を保存しない。router の認証状態は「credential → application の対応」の読み取りだけである。
- 各単位は bearer を自分の 1 application に対して再認証し、誤配は `AUTH_INVALID` で閉じる (fail closed)。
- router は multi-application 部品であり、SI-00 (`security/SECURITY_INVARIANTS_V1.md`) の対象である (router の欠陥は越境の対象になり得る)。その検証は peer-local / deployment evidence とする。
- 「router + 専用単位」は object-capable endpoint だけの構成である。JSON 経路の serving set (`*_SERVE_APPS`) は台帳 `RM` R-30 の裁定に委ね、本設計は R-30 の一方の答えを先取りしない。
- 監督の読み: R-30 の裁定は (ii) (router は multi-application 部品、各 application 専用単位は 1 application だけを serve) と矛盾しない形で別途行う。
- `concurrency` / `object_transfers` の `limit_enforcement` の帰結は §6.1 の Q-2 の段落。配備の分割は §9 の Q-2 の段落。

【v0.5 2026-10-02 設計レビュー 2 反映 Q-7】router の位置づけと要件 (§11 の Q-7。推奨 (a)+(b) で進めた)。

- 位置づけ: router は既存の前段 (reverse proxy) と同格の基盤部品であり、application-facing 実装ではない。router は TLS 終端として全 application の bearer を平文で受けるので、router の単一欠陥は他 application の bearer に届く。A-1 の目的 (application-facing の単一欠陥で他 bucket に届かない) は router については成り立たず、これを SI-00 (`security/SECURITY_INVARIANTS_V1.md`) の残余として `security/CONTROL_MAPPING.md` の SI-00 行に記録する (作業機。§9 の新 5)。
- 要件 1: router は契約の応答を一切組まない。lookup に失敗した要求は deployment の JSON process へ回し、そこが `AUTH_INVALID` / `AUTH_REQUIRED` を返して監査する。
- 要件 2: router は application logic・bucket 資格情報・DB 書き込み・本文の保存を持たない。本文は転送するだけである。
- 要件 3: router が保持する状態は「bearer の hash → application_id」の読み取り専用の射影だけである (secret を再構成できない)。上の「router の認証状態は「credential → application の対応」の読み取りだけ」をこの形に限る (旧文は残す)。
- 要件 4: 専用単位は自分の 1 application で bearer を再認証する (誤配は `AUTH_INVALID`。§7.1 の O-26)。
- 要件 5: 専用単位は serving set が 1 application でなければ起動しない (fail closed)。多 application を許すのは test 専用の composition root だけである (§7.1 の RC-10 と同形)。
- 要件 6: capability document を返す process と専用単位の設定値は同じ出所から導き、起動時に一致を検査する (台帳 `RM` P-3。§6.1 の Q-7)。
- 台帳 `RM` R-30 との関係: 上の「監督の読み: R-30 の裁定は (ii) ... と矛盾しない形で別途行う」を撤回し、次に改める (旧文は残す)。「台帳 `RM` R-30 は独立に裁定する。(ii) の router は application-facing 実装ではなく前段であり、R-30 のどちらの答えとも両立する。R-30 の裁定時に router の位置づけを確認する」。R-30 行への追記は作業機の台帳更新で行う (次の一手)。

【v0.5 2026-10-02 設計レビュー 2 反映 N-19】router は契約の応答を組まない (上の Q-7 の要件 1)。検査順の各段の実行主体は §3.4 の N-19 の表のとおり。認証拒否の監査は、応答した process が書く。`object_requests_per_minute` を数える場所は §6.1 の N-19。

### 3.2 アップロード要求

`POST /v1/objects` の本文は raw bytes とする。`multipart/form-data` は用いない。メタデータは次の HTTP ヘッダーで与える。

| ヘッダー | 規則 |
| --- | --- |
| `Content-Type` | 必須。空、ワイルドカード、複数値を拒否する。MIME 型の allow-list は初版で設けないが、構文は検証する。 |
| `Content-Length` | 任意。存在するときは正の整数か 0。実測バイト数を信頼する代わりには使わない。 |
| `Content-Digest` | 任意の RFC 9530 `sha-256=:<base64>:`。指定された場合は受信 bytes と一致しなければならない。 |
| `Idempotency-Key` | 任意。指定された場合は content digest と正規化 metadata を含む request digest に結び、既存 idempotency の再送・競合・同時送信直列化規則を適用する。 |
| `Content-Disposition` | 任意。`filename` があるときだけ元ファイル名として採用する。制御文字・パス区切り・過長値を拒否し、安全な文字列として保存する。 |
| `Content-Encoding` | 【v0.3 2026-10-02 設計レビュー 1 反映 M-10】identity 以外は `VALIDATION_FAILED`。 |
| `Expect` | 【v0.3 2026-10-02 設計レビュー 1 反映 M-6】`100-continue` を受けたときは、認証と `Content-Length` の検査が済むまで 100 を返さない (§3.2.4)。 |

【v0.3 2026-10-02 設計レビュー 1 反映 M-6 / M-19 / M-7 / M-8】上の表の `Content-Length` 行は §3.2.4、`Content-Digest` 行は §3.2.3、`Idempotency-Key` 行は §3.2.1、`Content-Disposition` 行は §3.2.2 で詳細を定める。`Content-Disposition` 行の「制御文字・パス区切りを拒否」は、B-11 (正規化して保存) に揃えて §3.2.2 の「`_` に置換」に改める (行は残す)。

【v0.4 2026-10-02 依頼者裁定の帰結 Q-1】`Content-Type` 行に足す: media type が `errors.content_type` (`application/problem+json`。`spec/data-service-api.v1.json:866`。type・subtype は大小無視、parameter は無視して比較) に一致する upload は `VALIDATION_FAILED` (`content_type`、`header/content-type`。§3.4)。upload_object の request media type は `media_type` に限らず、構文が妥当な単一の media type (`errors.content_type` を除く) を受け付ける (§3.3 の Q-1)。

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

【v0.3 2026-10-02 設計レビュー 1 反映 M-14】`ObjectDescriptor.request_id` はその応答を生んだ実行のものとする (metadata 取得は自分の `request_id`、upload の replay は元の実行の値)。`X-Request-Id` は、body に `request_id` がある応答では同じ値とする。

【v0.5 2026-10-02 設計レビュー 2 反映 Q-9】上の「`X-Request-Id` は、body に `request_id` がある応答では同じ値とする」を改める (旧文は残す。§11 の Q-9): `X-Request-Id` は常にその要求自身の `request_id` (= その要求の監査行の値) とする。replay の元の値は body の `request_id` だけが運ぶ (既存 JSON の replay の挙動のまま。`r2db-api/src/r2db_api/http.py:279`)。B-3 の契約化の範囲は「object_storage の 4 操作の全応答 (成功・失敗) が `X-Request-Id` にその要求自身の `request_id` を運ぶ」(object_storage 条件付きの義務。既存操作は変えない) とする。

【v0.3 2026-10-02 設計レビュー 1 反映 S-11】upload の成功応答の前に `upload_object` の audit event を同期で書く (`AUDIT_PROCESS_LOSS_V0_1.md` v0.5 決定 1-A)。順序は §4 の 2 transaction 構成に従う。

#### 3.2.1 Idempotency-Key

【v0.3 2026-10-02 設計レビュー 1 反映 M-7】

- request digest の材料: (a) 受信 bytes の SHA-256、(b) `Content-Type` の type/subtype を小文字化したものと parameter (名前は小文字化、値はそのまま、名前順)、(c) 正規化後 filename (無ければ null)。`Content-Digest` header と `Content-Length` は材料に含めない。
- `Idempotency-Key` header の構文と長さは既存 field と同じ (string、最大 128 octet)。引用符を外す等の sf-string 解釈はしない (IETF の Idempotency-Key 草案の値の書式は未確認)。
- 【v0.5 2026-10-02 設計レビュー 2 反映 N-6】上の「最大 128 octet」: header の値は ASCII の可視文字に限る (非 ASCII は `VALIDATION_FAILED`、violated_declaration は `request_schema`、field は `header/idempotency-key`。監督 2026-10-02) ので、octet 数 = 文字数であり、既存 field の maxLength 128 (文字数) と一致する。
- digest は本文を読み終えるまで決まらない。同じ key の 2 本目は自分の pending object として provider に書いた後に record と照合し、replay / `CONFLICT` と判定したらその object を cleanup する。per-key lock や pool 接続を転送の間保持しない。
- 直列化の地点は record の書き込み (available への遷移) であり、ここで B-1 の「高々 1 本が available になる」を満たす。
- `idempotency_entries` と `idempotency_retention_ms` は upload にも掛かる。
- 【v0.5 2026-10-02 設計レビュー 2 反映 N-8】`idempotency_entries` の検査は tx1 (`pending` の永続化) で per-key lock の下に予約として行い、同じ application の同時の keyed upload が両方とも通らないようにする (契約 `spec/data-service-api.v1.json:851` の「before it executes」)。契約の idempotency.record に「upload では provider への書き込みは実行と数えず、available への遷移を実行と数える」を足す案を置く。object_storage の `requires_capability` に `idempotency` を含める (1.9.0 以降 common_baseline で必ず提供されるので追加の負担は無い)。
- replay の応答の `X-Request-Id` と `ObjectDescriptor.request_id` は元の実行の `request_id` とする。
- 【v0.5 2026-10-02 設計レビュー 2 反映 Q-9】上の行のうち `X-Request-Id` を改める (旧文は残す): replay の応答の `X-Request-Id` は replay 要求自身の `request_id`、`ObjectDescriptor.request_id` は元の実行の `request_id` とする (§3.2 の Q-9)。
- 削除は JSON 本文なので、既存形式の `idempotency_key` field を受ける (B-1 と矛盾しない追加)。
- upload の transaction 構成は §4 の【M-7】のとおり。

#### 3.2.2 filename の正規化

【v0.3 2026-10-02 設計レビュー 1 反映 M-8】B-11 (正規化して保存・返却) に揃え、置換か拒否かの区分を表で固定する。両 peer は同じ入力に同じ結果を返す (§7.1 の O-2)。RFC 8187 / RFC 6266 の挙動に依る点は未確認。

| 入力 | 扱い |
| --- | --- |
| 制御文字 | `_` に置換 |
| パス区切り (`/` と `\`) | `_` に置換 |
| 先頭・末尾の空白 | `_` に置換 |
| Unicode の正規化形 | NFC へ正規化 |
| 上限 N octet を超える (N は未定) | `VALIDATION_FAILED` |
| `filename*=UTF-8''…` (RFC 8187) | 受け付ける。`filename` と両方あれば `filename*` を採る |
| `filename` に非 ASCII の octet | `VALIDATION_FAILED` |
| 【v0.3 2026-10-02 再確認反映 RC-5】対象文字集合 (上の制御文字・パス区切りの行) | Unicode の Cc と Cf (U+202E 等の双方向制御を含む) と `/` `\` |
| 【v0.3 2026-10-02 再確認反映 RC-5】処理順 | decode (`filename*` の percent-decoding) → NFC → 置換 → 長さ検査 (N octet は UTF-8 の octet 数) |
| 【v0.3 2026-10-02 再確認反映 RC-5】`filename*` があるとき | `filename` を無視する (非 ASCII の検査は `filename*` が無いときだけ) |
| 【v0.3 2026-10-02 再確認反映 RC-5】`filename*` の charset が UTF-8 以外 | `VALIDATION_FAILED` (`filename`) |
| 【v0.3 2026-10-02 再確認反映 RC-5】正規化後に空 | `VALIDATION_FAILED` (`filename`) |
| 【v0.3 2026-10-02 再確認反映 RC-5】download の `Content-Disposition` | `filename*=UTF-8''<percent-encoded>` と ASCII fallback の `filename=` (非 ASCII を `_` に置換) の両方を返す |
| 【v0.5 2026-10-02 設計レビュー 2 反映 N-9】download の `Content-Disposition` の ASCII fallback | `filename=` は quoted-string とし、`"` `\` `;` と 0x7F・制御文字を `_` に置換する (上の行の置換対象に `"` `\` `;` を足す) |

#### 3.2.3 Content-Digest

【v0.3 2026-10-02 設計レビュー 1 反映 M-19】

- header があるとき `sha-256` の member が必須。他の algorithm の member は無視する。`sha-256` の member が無ければ `VALIDATION_FAILED` (`content_digest`)。RFC 9530 の未対応 algorithm の扱いは未確認。
- canonical string は `sha-256=:<base64 (padding あり)>:` のみとする。
- download 側の照合は §3.3 の【M-19】。

#### 3.2.4 Content-Length と Expect

【v0.3 2026-10-02 設計レビュー 1 反映 M-6】

- `Content-Length` が `object_bytes` を超えるときは、本文を読む前に `LIMIT_EXCEEDED` (`limit_class: object_bytes`) を返す。
- `Expect: 100-continue` を受けたときは、認証と `Content-Length` の検査が済むまで 100 を返さない。
- 途中拒否は client 側で broken pipe になり得るので、client 向けに「`Content-Length` を付けて送る」ことを推奨として契約に書く。

### 3.3 取得・削除

バイト列取得は保存時の `Content-Type`、`Content-Length`、`Content-Digest`、`X-Request-Id`、RFC 6266/5987 に従う安全な `Content-Disposition: attachment` を返す。エラーを JSON に包んだ 200 応答や、ストレージのリダイレクトを返してはならない。バケット内の実キー、プロバイダ URL、署名、内部例外は公開しない。

【v0.3 2026-10-02 設計レビュー 1 反映 M-6】download は常に `Content-Length` を返す (size は metadata にある)。header 送出後の失敗 (provider 失敗、再認可での失効、期限、digest 不一致) では接続を異常終了する (HTTP/1.1 では宣言長未満で切断、HTTP/2 では RST_STREAM。HTTP/2 の挙動は未確認)。chunked の正常終端を送らない。client は「受信長 = `Content-Length` かつ `Content-Digest` 一致」のときだけ成功とする (契約の client 側義務として書く)。

【v0.3 2026-10-02 設計レビュー 1 反映 M-10】download 応答に `Cache-Control: no-transform` を付ける。

【v0.5 2026-10-02 設計レビュー 2 反映 N-14】上の `Cache-Control: no-transform` を `Cache-Control: private, no-store, no-transform` に改める (旧文は残す)。download 応答と metadata 応答の両方に付ける。共有 cache の挙動は未確認。

【v0.3 2026-10-02 設計レビュー 1 反映 M-19】download は provider から読んだ bytes の digest を保存値と照合し、不一致なら本文を切り (上の M-6 の異常終了)、security-control failure として監査する。

【註 2026-10-02】download の成功応答の `Content-Type` は送信者が upload 時に与えた値であり、契約 1.14.0 の応答分類 (`spec/data-service-api.v1.json:895`) とは両立しない。分類の規則は §11 の Q-1 で依頼者裁定待ち。

【v0.4 2026-10-02 依頼者裁定の帰結 Q-1】(甲)+(乙)。

- download_object の応答の分類規則を、契約 `errors.response_classification` (`spec/data-service-api.v1.json:895`) への操作別の例外として足す確定案とする: 「download_object の応答は HTTP status で分類する。2xx は bytes の成功であり、media type を問わず response schema と照合しない。2xx 以外で media type が errors.content_type なら失敗 (code で読む)。それ以外は解釈しない失敗」。
- upload_object は request media type を `media_type` (`spec/data-service-api.v1.json:7`) に限らない (構文が妥当な単一の media type。`errors.content_type` を除く。§3.2 の Q-1)。
- `media_type_note` / `external_standards` (`spec/data-service-api.v1.json:8`、`:9`) に「endpoint が request_media_type / response_media_type を宣言する操作はそれに従う」の 1 文を足す案 (§3 の S-10 の `request_media_type` / `response_media_type` と対応)。
- 契約版は minor (1.x.0) と読む (§11 の Q-1 の RC-19 の論証)。契約の確定文は契約改版の WP で書く (本設計は案)。
- reference client (`conformance-tests/CONDITIONS.md` C-35) への影響は契約改版の WP で見る (§7.1 の O-24)。

【v0.5 2026-10-02 設計レビュー 2 反映 N-3】(監督 2026-10-02: 以下の統合文は M-6 の client 側の成功条件を分類規則の中に取り込んだもので、M-6 の文は置き換えずそのまま残る。)

- 上の確定案の分類文を次の 1 文に統合する (旧文は残す): 「download_object の応答は HTTP status で分類する。2xx は、`Content-Length` がちょうど 1 つあり受信長がそれに等しく、`Content-Digest` の sha-256 member がちょうど 1 つあり受信 bytes と一致するときだけ bytes の成功 (media type を問わず response schema と照合しない)。2xx でそれを満たさないものは解釈しない失敗。2xx 以外で media type が errors.content_type なら失敗 (code で読む)。それ以外は解釈しない失敗」。
- 改版対象に `versioning.version_binding` の 1.14.0 (a) (`spec/data-service-api.v1.json:40`) を足し、新版の entry で「(a) は request_media_type / response_media_type を宣言しない操作の成功応答に掛かる」と書く。
- `response_headers` の案は §3 の N-3、`{object_id}` の照合は §3.1 の N-3、観測は §7.1 の O-24 の N-3。

削除は「利用可能なオブジェクトを取得不能にする」ことを成功条件とする。最初の confirmation 不足 request は既存形式の `DESTRUCTIVE_CONFIRMATION_REQUIRED` を返し、次の request が `destructive: true` と返された phrase を JSON で echo したときだけ実行する。オブジェクトストレージの物理削除とメタデータ更新の原子的な分散トランザクションは期待できないため、状態機械（`pending`、`available`、`deleting`、`deleted`、`cleanup_failed`）を実装側に持つ。クライアントに見せるのは `available` だけである。削除済みまたは他 application の ID は、ともに `NOT_FOUND` に正規化する。

【v0.3 2026-10-02 設計レビュー 1 反映 M-9】

- 削除の成功は `200 ObjectDeleteResult` (`application/json`、`{object_id, deleted: true, request_id}`、additionalProperties false) とする。
- 成功の定義 = metadata を `deleting` に切り替え、API から取得不能になった時点。provider の物理削除は同じ要求内で試み、失敗しても 200 を返して `cleanup_failed` に記録する (peer 間で分かれないよう固定する)。
- 最初の確認不足の要求の本文は `{}` (`Content-Type: application/json`)。
- 削除要求の schema は閉じ、`dry_run` / `budget` は `VALIDATION_FAILED` (`unsupported_field`) で拒否する (B-10 の「適用対象外」の具体形)。
- 削除の再送は `NOT_FOUND` になる。
- 【v0.3 2026-10-02 再確認反映 RC-9】上の「`VALIDATION_FAILED` (`unsupported_field`)」の語を `request_schema` に固定する。削除要求の `dry_run` / `budget` は閉じた schema で受け取れない field であり、`unsupported_field` は「schema がまだ受け取れる field」の語である (`spec/data-service-api.v1.json:921`)。
- 【v0.3 2026-10-02 再確認反映 RC-1】上の「削除の再送は `NOT_FOUND` になる」を分ける。`idempotency_key` なしの再送は `NOT_FOUND`。retention 内に同じ key・同じ digest の再送は元の 200 (`ObjectDeleteResult`、`request_id` も元の値) の replay。digest が異なれば `CONFLICT`。
- 【v0.3 2026-10-02 再確認反映 RC-3】`delete_object` (destructive) の audit の allow 行も、upload と同じ pre_commit 経路に乗せる (data commit の直前に pre_commit で書く。`AUDIT_PROCESS_LOSS_V0_1.md` 決定 1-A。§4 の RC-3)。

【v0.3 2026-10-02 設計レビュー 1 反映 M-14】destructive の句には identifier 検証を通った `object_id` だけを含める (`spec/data-service-api.v1.json:711`)。認証前に本文を読まずに拒否したときは `Connection: close` を付けて接続を閉じる (keep-alive の desync 防止)。

【v0.5 2026-10-02 設計レビュー 2 反映 N-7】上の「認証前に本文を読まずに拒否したときは `Connection: close` を付けて接続を閉じる」を改める (旧文は残す): 本文を読み終える前に応答するときは、認証の前後を問わず `Connection: close` を付け、応答後に接続を閉じる。

### 3.4 失敗の表

【v0.3 2026-10-02 再確認反映 RC-8】検査順を次の表に固定する。同じ段の複数違反は、検査順の表の括弧内に列挙した順 ((4) なら Content-Type → Content-Disposition → Idempotency-Key → Content-Digest → Content-Length の値 → Content-Encoding) で最初の違反を返す (監督 2026-10-02。失敗の表の行順は優先順位ではない)。未認証で `Content-Length` > `object_bytes` は (2) で `AUTH_*` (B-6)。

| 段 | 検査 |
| --- | --- |
| (1) | 認証前の小さい byte bound と concurrency slot。【v0.5 2026-10-02 設計レビュー 2 反映 N-7】object 経路は認証前に本文を 1 octet も読まない (ASGI の receive を呼ばない)。既存の request_bytes の middleware は object 経路に掛けない。uvicorn は最初の receive で 100 Continue を送る (本環境のソースで確認、実行は未確認) |
| (2) | 認証 (`AUTH_*`) |
| (3) | capability (`CAPABILITY_UNSUPPORTED`) |
| (4) | header の構文 (`Content-Type`、`Content-Disposition`、`Idempotency-Key`、`Content-Digest`、`Content-Length` の値、`Content-Encoding`) |
| (5) | `object_metadata_bytes` |
| (6) | `Content-Length` vs `object_bytes` |
| (7) | `object_requests_per_minute` |
| (8) | `object_transfers` |
| (9) | 本文の受信 (受信中の `object_bytes`、digest) |

【v0.5 2026-10-02 設計レビュー 2 反映 N-13】削除の順: `NOT_FOUND` (存在・所有・状態) は destructive confirmation の検査より先とする (契約 `spec/data-service-api.v1.json:851` の「target existence, destructive confirmation」の順と揃う)。

【v0.5 2026-10-02 設計レビュー 2 反映 N-18】同じ要求に段 (4) の 2 つの違反があれば先の方の field を返す。段 (3) と (4) の同時違反は `CAPABILITY_UNSUPPORTED` を返す (§7.1 の O-28)。

【v0.5 2026-10-02 設計レビュー 2 反映 N-19】検査順の各段の実行主体 (上の表の行は残す):

| 段 | 実行主体 |
| --- | --- |
| (1) | 専用単位 (router は本文を読まない) |
| (2)〜(9) | 専用単位 |
| router の lookup に失敗した要求 | deployment の JSON process (`AUTH_INVALID` / `AUTH_REQUIRED` を返して監査する。§3.1 の Q-7 の要件 1) |

【v0.3 2026-10-02 設計レビュー 1 反映 M-15】header の違反の位置 (`field`) は `header/<小文字の header 名>` と書く。`violated_declaration` に `content_type`、`content_digest`、`filename` を足すことは、契約の閉じた語彙 (`spec/data-service-api.v1.json:921`) の拡張になる。「未定」は v0.3 の材料で決まっていない欄である。

【v0.3 2026-10-02 再確認反映 RC-20】上の「「未定」は v0.3 の材料で決まっていない欄である。」を経緯の記述に改める: v0.3 起草時に未定だった欄は 2026-10-02 の監督裁定で埋めた (旧文は残す)。

【v0.3 2026-10-02 再確認反映 RC-9】`field` の定義 (`spec/data-service-api.v1.json:909`、本文 root からの位置) も `header/<名>` を含む形に改版する。

【v0.5 2026-10-02 設計レビュー 2 反映 N-5】上の `field` 定義の改版に「path の placeholder は placeholder 名」を含める (`{entity}` → "entity" の既存の扱いと揃う)。

【v0.5 2026-10-02 設計レビュー 2 反映 N-6】`violated_declaration` の新語 3 つの定義文案 (契約の閉じた語彙 `spec/data-service-api.v1.json:921` に足す):

- `content_type`: `Content-Type` header の値が、契約の宣言する構文 (単一の media type、`errors.content_type` 以外) に反する。
- `content_digest`: `Content-Digest` header の値が構文に反する、sha-256 member を欠く、または受信 bytes と一致しない。
- `filename`: `Content-Disposition` の `filename` / `filename*` が契約の宣言する規則に反する。
- 新語を足す基準: header の値が契約の宣言する構文に反する = 新語。契約が受け付けない header の存在 (`Content-Encoding`) や閉じた schema 外の field = `request_schema`。
- 契約改版の WP の範囲に、語彙の文の「eleven values」→「fourteen values」と、pin (`conformance-tests/test_contract.py` の PIN_1_7_0_VIOLATED_DECLARATION_VOCABULARY、`conformance-tests/test_c21_denial_details_vocabulary.py:53`) の更新を挙げる。

| 条件 | code | violated_declaration | field | 出所 |
| --- | --- | --- | --- | --- |
| `Content-Type` の欠落・空・ワイルドカード・複数値・構文違反 | `VALIDATION_FAILED` (監督裁定 2026-10-02) | `content_type` | `header/content-type` | §3.2、M-15 |
| `Content-Length` と実測バイト数の不一致 | `VALIDATION_FAILED` | `request_schema` | `header/content-length` | M-15。【v0.5 2026-10-02 設計レビュー 2 反映 N-7】wire では HTTP の framing が先に本文長を決め、不正値は uvicorn が契約外の 400 で返す (`conformance-tests/CONDITIONS.md` C-03 の wire rejection と同形。uvicorn の挙動は本環境のソースで確認、実行は未確認)。行は消さない。契約上の code は無い。O-23 の対象外 |
| `Content-Length` が `object_bytes` を超える (本文を読む前) | `LIMIT_EXCEEDED` (`limit_class: object_bytes`) | — | — | M-6 |
| 受信中に `object_bytes` を超える | `LIMIT_EXCEEDED` (`limit_class: object_bytes`) | — | — | §6 の 2 |
| `Content-Digest` に `sha-256` の member が無い | `VALIDATION_FAILED` | `content_digest` | `header/content-digest` | M-19 |
| `Content-Digest` と受信 bytes の不一致 | `VALIDATION_FAILED` (監督裁定 2026-10-02。request が自ら宣言した値との不一致なので request の違反と読む) | `content_digest` | `header/content-digest` | §2、§3.2 |
| filename が上限 N octet を超える、`filename` に非 ASCII の octet | `VALIDATION_FAILED` | `filename` | `header/content-disposition` | M-8 |
| `Content-Encoding` が identity 以外 | `VALIDATION_FAILED` | `request_schema` (監督裁定 2026-10-02。新語彙を増やさない) | `header/content-encoding` | M-10 |
| 同一 `Idempotency-Key` で request digest が異なる | `CONFLICT` | `idempotency_key` (既存語彙) | `header/idempotency-key` (監督裁定 2026-10-02) | §3.2.1 |
| `object_id` の構文違反 | `IDENTIFIER_INVALID`。【v0.5 2026-10-02 設計レビュー 2 反映 N-5】許容集合 {`IDENTIFIER_INVALID`, `VALIDATION_FAILED`} で検証する (MitateDB は `IDENTIFIER_INVALID` を出さない既存の開示。`conformance-tests/test_c21_denial_details_vocabulary.py:209-216`) | `identifier_syntax` (【v0.5 2026-10-02 設計レビュー 2 反映 N-5】固定) | `object_id` (監督裁定 2026-10-02。path の placeholder 名をそのまま位置名とする。`{entity}` の既存の扱いと揃うかは設計レビュー 2 で確認。§10 の S-3)。【v0.5 2026-10-02 設計レビュー 2 反映 N-5】確認済み: 既存 `{entity}` → "entity" と揃う (`r2db-api/src/r2db_api/structured.py:186`、`MitateDB-api/src/mitatedb_api/identifiers.py:33-36`) | M-14 |
| 存在しない / 他 application / `available` 以外の状態 | `NOT_FOUND` | — | — | §3.3、M-14 |
| capability が ABSENT | `CAPABILITY_UNSUPPORTED` | `capability` | 要求全体のため省略 | §7 の 6 |
| 削除の確認不足 | `DESTRUCTIVE_CONFIRMATION_REQUIRED` | — | — | §3.3 |
| 削除要求に `dry_run` / `budget` | `VALIDATION_FAILED` | `unsupported_field`。【v0.3 2026-10-02 再確認反映 RC-9】`request_schema` に固定 (閉じた schema で受け取れない field。`unsupported_field` は「schema がまだ受け取れる field」の語。`spec/data-service-api.v1.json:921`) | 当該 field | M-9、RC-9 |
| provider 失敗 (header 送出前) | `SERVICE_UNAVAILABLE` | — | — | M-15 |
| `object_transfers` の枯渇 | `LIMIT_EXCEEDED` (`limit_class: object_transfers`) | — | — | M-15、§6.1 |
| `object_requests_per_minute` の超過 | `LIMIT_EXCEEDED` (`limit_class: object_requests_per_minute`) | — | — | §6.1 |
| `object_metadata_bytes` の超過 | `LIMIT_EXCEEDED` (`limit_class: object_metadata_bytes`) | — | — | §6.1 |
| download の header 送出後の失敗 (provider 失敗、再認可での失効、期限、digest 不一致) | code なし。接続の異常終了 | — | — | M-6 |
| 転送中の再認可で失効または `AUTH_STATE_UNAVAILABLE` | 転送を中断 (fail closed)。download で header 送出後なら前行と同じ。upload (応答前) では既存の `AUTH_REVOKED` / `APPLICATION_DISABLED` / `AUTH_STATE_UNAVAILABLE` をそのまま返す (監督裁定 2026-10-02。新 code を増やさない)。【v0.5 2026-10-02 設計レビュー 2 反映 N-5】失効 / 無効化の code は `conformance-tests/CONDITIONS.md` C-08 の集合 (`conformance-tests/test_c08_revocation_boundary.py:25-29`) で検証する | — | — | M-11 |
| `Idempotency-Key` の構文・長さ違反 | `VALIDATION_FAILED` | `idempotency_key`。【v0.5 2026-10-02 設計レビュー 2 反映 N-6】`request_schema` に改める (既存の `idempotency_key` は「同じ key で digest が異なる」だけ。`spec/data-service-api.v1.json:921`) | `header/idempotency-key` | 【v0.3 2026-10-02 再確認反映 RC-8】 |
| `Content-Disposition` の構文違反 | `VALIDATION_FAILED` | `filename` | `header/content-disposition` | 【v0.3 2026-10-02 再確認反映 RC-8】 |
| 正規化後に空の filename | `VALIDATION_FAILED` | `filename` | `header/content-disposition` | 【v0.3 2026-10-02 再確認反映 RC-8】、§3.2.2 の RC-5 |
| `Content-Length` の値が不正 | `VALIDATION_FAILED` | `request_schema` | `header/content-length` | 【v0.3 2026-10-02 再確認反映 RC-8】。【v0.5 2026-10-02 設計レビュー 2 反映 N-7】wire では HTTP の framing が先に本文長を決め、不正値は uvicorn が契約外の 400 で返す (`conformance-tests/CONDITIONS.md` C-03 の wire rejection と同形。uvicorn の挙動は本環境のソースで確認、実行は未確認)。行は消さない。契約上の code は無い。O-23 の対象外 |
| `filename*` の charset が UTF-8 以外 | `VALIDATION_FAILED` | `filename` | `header/content-disposition` | §3.2.2 の RC-5 (監督 2026-10-02 に失敗の表へ写した) |
| upload の media type が `errors.content_type` (`application/problem+json`。type・subtype は大小無視、parameter は無視して比較) に一致 | `VALIDATION_FAILED` | `content_type` | `header/content-type` | 【v0.4 2026-10-02 依頼者裁定の帰結 Q-1】、§3.2 |
| 転送が宣言 `execution_ms` を超える (upload、または download の header 送出前) | `LIMIT_EXCEEDED` (`limit_class: execution_ms`)。download の header 送出後は「download の header 送出後の失敗」の行 (接続の異常終了、M-6) | — | — | 【v0.4 2026-10-02 依頼者裁定の帰結 Q-3】、§6.1 |
| 転送が宣言 `object_transfer_ms` を超える (upload、または download の header 送出前) | `LIMIT_EXCEEDED` (`limit_class: object_transfer_ms`)。download の header 送出後は「download の header 送出後の失敗」の行 (接続の異常終了、M-6) | — | — | 【v0.5 2026-10-02 設計レビュー 2 反映 Q-6】上の行の `execution_ms` を `object_transfer_ms` に改める (上の行は残す)、§6.1 の Q-6 |

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
   【v0.3 2026-10-02 設計レビュー 1 反映 M-11】4 の再認可を「転送の間、周期 P で再認可する (§6 の 5)。完了時にも 1 回再認可する」に改める (§11 の Q-4 の案を問わない)。再認可で `AUTH_STATE_UNAVAILABLE` なら中断する (fail closed)。P と宣言 `authorization_propagation_bound_ms` の関係は Q-4 で依頼者裁定待ち。
   【v0.3 2026-10-02 再確認反映 RC-16】上の「(§11 の Q-4 の案を問わない)」を「Q-4 の (a)(b) のいずれでも。(c) を採るなら本項を見直す」に改める。
   【v0.4 2026-10-02 依頼者裁定の帰結 Q-4】Q-4 は (a) を採った (RC-16 の「(c) を採るなら本項を見直す」に当たらない)。P と宣言 `authorization_propagation_bound_ms` の関係は §6 の 5 の Q-4 の段落。
5. `available` メタデータを永続化して成功応答を返す。

3〜5 に失敗した場合、provider object を削除してから問題応答を返す。削除に失敗した場合は `cleanup_failed` を永続化し、公開されない cleanup worker が再試行する。

【v0.3 2026-10-02 設計レビュー 1 反映 M-7】upload は 2 transaction 構成とする: 「`pending` 永続化 (tx1) → provider 転送 (lock・pool 接続を持たない) → `available` 永続化 + idempotency record + audit event (tx2)」。契約 `spec/data-service-api.v1.json:851` の「record は effects と同じ transaction」は tx2 に対して成り立ち、provider 側の効果は transaction の外にある。直列化の地点は §3.2.1 のとおり tx2 の record 書き込みである。

【v0.5 2026-10-02 設計レビュー 2 反映 N-8】tx1 で `idempotency_entries` の検査を予約として行う (§3.2.1 の N-8)。

【v0.3 2026-10-02 再確認反映 RC-3】上の「+ audit event (tx2)」を「audit の allow 行は tx2 の commit の直前に pre_commit で書く (`AUDIT_PROCESS_LOSS_V0_1.md` 決定 1-A。sink が別 DB なので同一 transaction ではない)」に改める。`delete_object` (destructive) も同じ pre_commit 経路に乗せる (§3.3 の RC-3)。O-20 の観測点は §7.1 の RC-11 のとおり。

【v0.3 2026-10-02 設計レビュー 1 反映 S-11】tx2 の audit event (`upload_object`) は成功応答の前に同期で書く (【RC-3 の帰結、監督 2026-10-02】「tx2 の」は tx2 の commit の直前の pre_commit を指す。sink が別 DB なので同一 transaction ではない) (`AUDIT_PROCESS_LOSS_V0_1.md` v0.5 決定 1-A)。bytes を provider に送った後・応答前の process 喪失は process-loss policy の外 (`security/CONTROL_MAPPING.md:1825`) であり、provider に残る孤児 object は `pending` 行と cleanup worker が担う (下の M-5)。

【v0.3 2026-10-02 設計レビュー 1 反映 M-4】cleanup worker は application ごとに、当該 application の provider identity だけで動く (A-1 の制約を application-facing でない worker にも及ぼす)。provider key は metadata 行の provider_key から読まず、worker 自身の設定 (bucket) と object_id から上の論理構造で再計算する。行の provider_key は照合にだけ使い、一致しなければ削除せず security-control failure (SI-14、`security/SECURITY_INVARIANTS_V1.md`) として監査する。検証の形 (peer-local): application A の DB に application B の provider key を持つ `cleanup_failed` 行を書き、B の bucket に何も起きないことを実測する (§7.1 の O-18)。

【v0.3 2026-10-02 設計レビュー 1 反映 M-5】process 喪失・強制終了で 3〜5 の途中に止まった upload は `pending` のまま残る。`pending` のうち作成から (転送の全体時間上限 + 余裕) を過ぎたものは cleanup 対象とする。provider 側の未完了 multipart upload (R2) / resumable session (GCS) も対象に含め、その操作に要る provider 権限を §5.1 / §5.2 に列挙する (provider の挙動は未確認)。cleanup の成功・失敗を監査する (event_class は実装の宣言。`cleanup_failed` は security-control failure)。検証の形 (peer-local): upload 中に process を SIGKILL し、再起動後に `pending` が期限で回収され provider object が残らない (§7.1 の O-19)。転送の全体時間上限は §11 の Q-3 の裁定に従う。

【v0.4 2026-10-02 依頼者裁定の帰結 Q-3】上の「転送の全体時間上限」は宣言 `execution_ms` である (§2 の Q-3 の段落、§6.1)。

【v0.5 2026-10-02 設計レビュー 2 反映 Q-6】上の Q-3 の註の「宣言 `execution_ms`」を「宣言 `object_transfer_ms`」に改める (旧文は残す。§6.1 の Q-6)。

【v0.3 2026-10-02 再確認反映 RC-2】上の M-5 の回収対象に「`deleting` のまま一定時間 (削除の全体時間上限 + 余裕) を過ぎた行」を足す。検証の形 (peer-local): 確認済み削除の途中で SIGKILL すると、再起動後に回収され provider object が残らない (§7.1 の O-19b)。

【v0.3 2026-10-02 再確認反映 RC-7】tx2 の `pending → available` は状態が `pending` のときだけ成功する条件付き更新。worker は provider を削除する前に行を `pending → deleting` へ条件付きで遷移させ、遷移できた行だけ削除する。遷移に負けた upload は tx2 で失敗し、provider object を自分で cleanup (または `cleanup_failed`) して `SERVICE_UNAVAILABLE` を返す。

## 5. 実装ごとの責務

【v0.3 2026-10-02 設計レビュー 1 反映 M-10】両 peer に共通の結果を先に置く。(1) 既存の provider key を上書きしない (object_id の一意性 + provider の precondition)。(2) 未完了 upload を bound 内に消す (§4 の M-5)。(3) 当該 bucket 以外への操作は provider 自身が拒否する。各 peer がこれを provider のどの機能で実現するかは下表のとおりで、v0.3 の時点では全て未確認である (provider の公式文書を読めていない)。

| 主張 | r2db-api (R2) | MitateDB-api (GCS / Cloud Run) | 確認済み / 未確認 |
| --- | --- | --- | --- |
| 当該 bucket 以外への操作を provider が拒否する credential / identity を発行できる | bucket 単位の API token | bucket 単位の service account と Uniform bucket-level access | 未確認 |
| 操作単位 (get / put / delete) まで権限を絞れる | token の粒度 | IAM の粒度 | 未確認 |
| 既存 key の上書き防止 | 条件付き PUT の可否 | generation precondition | 未確認 |
| 未完了 upload の破棄と、そのための権限 | 未完了 multipart upload の abort | resumable session の破棄 | 未確認 |
| 経路の手前の要求本文上限・要求時間上限 | proxy (nginx 例) | Cloud Run の front end | 未確認 |

### 5.1 r2db-api: Cloudflare R2

- S3 互換 API を使う専用 storage adapter を置く。アプリケーション DB 接続や公開 HTTP handler に S3 操作を散在させない。
- application ごとに非公開 R2 bucket と、その bucket 専用の API token/credential を provision する。object-capable API 実行単位は一 application だけを serve し、当該 bucket の `GetObject`、`PutObject`、`DeleteObject` 以外を provider に拒否される credential だけを得る。
- 【v0.3 2026-10-02 設計レビュー 1 反映 M-10】上の行の「`GetObject`、`PutObject`、`DeleteObject` 以外を provider に拒否される credential」を、安全性の主張「当該 bucket 以外への操作を provider が拒否する credential」に改める。操作単位の列挙は R2 の token の粒度を公式文書で確かめてから書く (未確認)。
- bucket 作成、credential 発行・更新・失効は application-facing API の外にある provisioning/control 経路だけが行う。R2 temporary credential を使う場合も、全 bucket に届く親 token は application-facing 実行単位に置かず、当該 bucket にしか届かない親から発行する。
- endpoint、bucket、access key ID、secret access key、最大オブジェクトサイズ、転送上限は external secret manager または root-only の実行環境から渡す。ここで参照できる secret は当該 application 用だけである。
- R2 の S3 API 互換性を adapter の結合テストで確認する。SDK は実装時に採用根拠、タイムアウト、再試行、multipart 閾値を明文化する。
- 【v0.3 2026-10-02 設計レビュー 1 反映 M-5】cleanup worker は未完了 multipart upload の破棄に要る権限を、当該 bucket に限って持つ (操作名と権限の粒度は未確認)。
- 【v0.3 2026-10-02 設計レビュー 1 反映 M-10】上書き防止は §5 冒頭の共通の文 (object_id の一意性 + provider の precondition) に従う。R2 の条件付き PUT の可否は未確認。

### 5.2 MitateDB-api: Google Cloud Storage

- GCS 専用 storage adapter を置く。Cloud Run ではサービスアカウントまたは Workload Identity を使い、JSON サービスアカウント鍵をアプリ設定・イメージ・リポジトリに置かない。
- application ごとに Uniform bucket-level access を有効にした private GCS bucket と、当該 bucket 専用の Cloud Run service account / Workload Identity を provision する。object-capable 実行単位は一 application だけを serve し、他 bucket への権限を持たない。
- `MITATEDB_OBJECT_STORAGE_BUCKET`、`MITATEDB_OBJECT_STORAGE_MAX_BYTES`、`MITATEDB_OBJECT_STORAGE_TRANSFERS` を環境設定とする。認証は Application Default Credentials を原則とし、ローカル開発は明示的な安全な認証手順を別途 runbook 化する。application-facing 実行単位に、複数 bucket を扱える service account や downscoped token を発行できる token を配置しない。
- GCS の generation/precondition を利用して、同一 provider key の上書きを防ぐ。
- 【v0.3 2026-10-02 設計レビュー 1 反映 M-10】上の行は §5 冒頭の共通の文 (object_id の一意性 + provider の precondition) の GCS 側の実現である。GCS の generation precondition の挙動は未確認。配備の front end (Cloud Run) の要求本文上限・要求時間上限は §6 の 6 に従い、その値は未確認。
- 【v0.3 2026-10-02 設計レビュー 1 反映 M-5】cleanup worker は未完了 resumable session の破棄に要る権限を、当該 bucket に限って持つ (操作と権限の粒度は未確認)。

両 adapter は同じ抽象操作（put stream、get stream、head、delete）を持つが、コードや SDK wrapper を peer 間で共有しない。公開 API の振る舞いを conformance tests で揃える。peer-local integration test は、application A の実行 identity が application B の bucket に対して `GetObject`、`PutObject`、`DeleteObject` を provider 自身から拒否されることを実測する。

【v0.3 2026-10-02 設計レビュー 1 反映 M-16】実クラウドでの越境拒否は、skip される test ではなく deployment evidence (`security/CONTROL_MAPPING.md` の SI-00 行) として記録する (§7.1 の O-17)。

## 6. HTTP 境界と資源制御

現在の JSON 用 request-byte middleware は、本文を読み切ってから下流へ渡す方式である。バイナリ API では次のように拡張または別 middleware 化する。

1. 経路を識別し、object upload だけをストリーミング転送対象にする。
2. 未認証 request は既存の小さい request byte bound を超えて本文を読まない。Authorization header を認証した request だけが、受信チャンクごとに `object_bytes` を数える streaming 経路へ進む。上限超過時は読み取りを中止し `LIMIT_EXCEEDED`（`limit_class: object_bytes`）を返す。
   【v0.5 2026-10-02 設計レビュー 2 反映 N-7】object 経路では、未認証 request の本文を 1 octet も読まない (§3.4 の段 (1))。
3. 既存の pre-auth concurrency slot を認証前から獲得する。認証後には deployment 全体で効く `object_transfers` 枠を獲得し、接続切断・例外も含め必ず解放する。複数 process が一 base URL を serve する deployment で process-local 枠しか持てない場合、`limit_enforcement.object_transfers` は `deployment_required` と宣言する。
   【v0.3 2026-10-02 設計レビュー 1 反映 M-3】3 を次に改める。object 経路は認証前に既存の concurrency slot を獲得し、認証成功時にこれを解放して `object_transfers` 枠に持ち替える (現行 JSON 経路は slot を要求全体で保持する: `r2db-api/src/r2db_api/http.py:473-474`。object 経路はこれに従わない)。`object_transfers` は application 単位の枠とし、その意味を `limit_enforcement.object_transfers` として契約に書く。枠の実現は concurrency と同じ host 共有の OS flock slot とする (`MULTI_PROCESS_WORKER_V0_1.md` v0.5 裁定 10。process が死ねば kernel が解放するので、転送中の crash で枠が漏れない)。1 host 内の複数 worker は共有の範囲内、複数 host は `deployment_required`。object 経路は `requests_per_minute` / `concurrency` (持ち替え後) に数えず、`object_requests_per_minute` / `object_transfers` にだけ数える。根拠: 旧文の「process-local 枠しか持てない場合 `deployment_required`」は、`conformance-tests/CONDITIONS.md` C-32 で両 peer が既に deployment 全体の枠を実現している現状と比べて後退であり (§10 の S-4)、長い転送が host 共有の pre-auth slot を占有する。class ごとの定義は §6.1。
   【v0.3 2026-10-02 再確認反映 RC-6】持ち替えるのは `upload_object` / `download_object` だけ。`get_object_metadata` / `delete_object` は既存の JSON 経路と同じく concurrency slot を要求全体で保持する (本文が小さく短い)。`object_requests_per_minute` の鍵は credential_id (既存 `requests_per_minute` と同じ鍵。`r2db-api/src/r2db_api/http.py` の WP-8c の註)。`object_transfers` の鍵は application。
4. JSON endpoint の既存 `request_bytes` 挙動は変更しない。
5. HTTP client と provider SDK の接続・読取・全体時間には有限 timeout を設ける。同期 provider SDK の stream read/write は event loop 上で実行せず threadpool に offload する。転送中も authorization propagation bound 以内に再認可する。
   【v0.3 2026-10-02 設計レビュー 1 反映 M-11】再認可で `AUTH_STATE_UNAVAILABLE` のときは転送を中断する (fail closed)。再認可周期 P と宣言 `authorization_propagation_bound_ms` の関係は §11 の Q-4 で依頼者裁定待ち。転送時間の bound をどの limit class が表すかは §11 の Q-3 で依頼者裁定待ち。
   【v0.4 2026-10-02 依頼者裁定の帰結 Q-4】(a)。object_storage を提供する deployment は `authorization_propagation_bound_ms` を正の値で宣言し、その値は「失効の伝搬遅延 + 再認可周期 P」を含む。両 peer の現行宣言 0 (§11 の Q-4) は、object_storage を宣言する版で変える (宣言値の変更 = 台帳 `RM` §9 の 8 で最低 Class C。台帳 `RM` P-3)。周期 P は配備値 (§8)。再認可で失効 / `APPLICATION_DISABLED` / `AUTH_STATE_UNAVAILABLE` を観測したら中断する (fail closed): upload は応答前なら既存 code (§3.4)、download は接続の異常終了 (§3.3 の M-6)。
   【v0.4 2026-10-02 依頼者裁定の帰結 Q-3】転送時間の bound は `execution_ms` が表す (§6.1 の Q-3 の段落)。
   【v0.5 2026-10-02 設計レビュー 2 反映 Q-6】上の行を改める (旧文は残す): 転送時間の bound は `object_transfer_ms` が表す (§6.1 の Q-6 の段落)。
   【v0.5 2026-10-02 設計レビュー 2 反映 N-20】`authorization_propagation_bound_ms` は deployment に 1 つの値なので、正の値を宣言すると JSON 操作の公表上の保証も同じ値になる (宣言は上限なので真)。観察 (両論): (i) この共有を受け入れる (本設計の扱い)。(ii) 操作別の bound を宣言する (契約の改版が要るので採らない)。
6. 【v0.3 2026-10-02 設計レビュー 1 反映 M-10】経路の手前の全ての本文上限 (proxy・platform) は、`/v1/objects` に限り `object_bytes` 以上かつ request buffering 無効に設定し、宣言する `object_bytes` は経路上で最も小さい上限以下とする (台帳 `RM` P-3)。現状の例: r2db の nginx 例は `client_max_body_size 1100k` (`r2db-api/deploy/nginx/r2dbsvc-api-8443.conf.example:93`)、socket harness は `{client_max_body_size}` (`conformance-tests/socket_harness.py:290`)。Cloud Run の本文上限は未確認。
   【v0.5 2026-10-02 設計レビュー 2 反映 N-7】socket harness の nginx 設定に、`/v1/objects` の `proxy_request_buffering off` / `proxy_buffering off` と `Expect` の扱いを足す (nginx の挙動は未確認)。

### 6.1 limit class の定義

【v0.3 2026-10-02 設計レビュー 1 反映 M-3】B-5 の 4 class を、数える対象・境界・拒否の `limit_class` で定める。宣言値を N とする。

| class | 数える対象 | 境界 (N は受理、N+1 は拒否) | 拒否の `limit_class` | 枠の範囲と `limit_enforcement` |
| --- | --- | --- | --- | --- |
| `object_bytes` | upload 本文の octet 数 | N octet の本文は受理、N+1 octet で拒否 | `object_bytes` | `spec/data-service-api.v1.json:324` (deployment 全体を記述) に従う |
| `object_metadata_bytes` | `Content-Type`・`Content-Disposition`・`Idempotency-Key`・`Content-Digest` の値の octet 合計 | 合計 N octet は受理、N+1 octet で拒否 | `object_metadata_bytes` | 同上 |
| `object_requests_per_minute` | 4 操作 (`upload_object` / `download_object` / `get_object_metadata` / `delete_object`) の要求数 | N 件目は受理、N+1 件目を拒否 | `object_requests_per_minute` | 同上 |
| `object_transfers` | 同時に本文を読み書きしている要求数 | N 本の同時転送は受理、N+1 本目を拒否 | `object_transfers` | application 単位。host 共有の OS flock slot。1 host 内の複数 worker は共有の範囲内、複数 host は `deployment_required` |
| `object_transfer_ms` | 【v0.5 2026-10-02 設計レビュー 2 反映 Q-6】(監督 2026-10-02: `execution_ms` は upload / download には掛けず本 class が代わる。`get_object_metadata` / `delete_object` には既存どおり `execution_ms` が掛かる。) upload / download の 1 要求の転送時間 (起点 = `object_transfers` 枠の獲得時点、終点 = available への遷移 / 送信完了) | N ms 以内に終わる転送は受理、N ms を超えた転送は拒否 | `object_transfer_ms` | `object_bytes` の行と同じ |

【v0.3 2026-10-02 再確認反映 RC-6】持ち替えるのは `upload_object` / `download_object` だけ。`get_object_metadata` / `delete_object` は既存の JSON 経路と同じく concurrency slot を要求全体で保持する (本文が小さく短い)。`object_requests_per_minute` の鍵は credential_id (既存 `requests_per_minute` と同じ鍵。`r2db-api/src/r2db_api/http.py` の WP-8c の註)。`object_transfers` の鍵は application。

【v0.4 2026-10-02 依頼者裁定の帰結 Q-3】転送時間は `execution_ms` が表す (受付から available / 送信完了まで)。class は増やさない。超過は `LIMIT_EXCEEDED` (`limit_class: execution_ms`)。download で header 送出後なら接続の異常終了 (§3.3 の M-6)。計測開始と待ち (slot / 枠の待ち) の扱いは台帳 `RM` R-42 の裁定に従う。R-42 が決まるまで、本設計は「受付 = 認証成功時点」を仮の起点とする (仮)。宣言しない運用値の timeout は置かない (§8)。超過した upload の `object_transfers` 枠は解放される (§7.1 の O-25)。

【v0.5 2026-10-02 設計レビュー 2 反映 Q-6】上の Q-3 の段落の「転送時間は `execution_ms` が表す」を「転送時間は `object_transfer_ms` が表す」に改める (旧文は残す。§11 の Q-6)。`object_transfer_ms` は B-5 の 4 class を超える加算的な class であり、起点 = `object_transfers` 枠の獲得時点、終点 = available への遷移 / 送信完了で、台帳 `RM` R-42 と独立する。超過は `LIMIT_EXCEEDED` (`limit_class: object_transfer_ms`)、download で header 送出後なら接続の異常終了 (§3.3 の M-6)。agent が必要な最低速度 = `object_bytes` / `object_transfer_ms` を宣言から導けることを契約文に書く。実装側の socket timeout は `object_transfer_ms` 以下の運用値とする (§8)。超過した upload の `object_transfers` 枠は解放される (§7.1 の O-25)。

【v0.4 2026-10-02 依頼者裁定の帰結 Q-2】案 (ii) (§3.1 の Q-2 の段落) の `limit_enforcement` の帰結 (§11.1 の (ii) 行から): `concurrency` は、router と全ての専用単位が base URL を serve する 1 host (1 composition root の worker 群。`MULTI_PROCESS_WORKER_V0_1.md` 裁定 10 の slot 共有の範囲) の process なら `enforced` のまま、別 host (Cloud Run の別 service 等) なら `deployment_required`。`object_transfers` は、専用単位が 1 instance のとき `enforced`、複数 instance なら `deployment_required`。宣言は台帳 `RM` P-3 (真であり検査される) に従う。Cloud Run の挙動は未確認。

【v0.5 2026-10-02 設計レビュー 2 反映 Q-8】上の「`concurrency` は ... 1 host ... の process なら `enforced` のまま」を改める (旧文は残す。§11 の Q-8): object-capable な配備 (router・JSON process・専用単位が別 composition root で並ぶ) では `concurrency` を `deployment_required` と宣言する。根拠: `MULTI_PROCESS_WORKER_V0_1.md` 裁定 27・28 (`MULTI_PROCESS_WORKER_V0_1.md:845-846`) の `enforced` の写像は「自 supervisor の workers ≥ process_ceilings.data」かつ「slot directory が自 user 所有 0700」を条件とし、別 composition root (A-1 なら別 OS user) が並ぶ構成はこれを満たさない。宣言を変えても `conformance-tests/CONDITIONS.md` C-32 の挙動は変わらない。

【v0.5 2026-10-02 設計レビュー 2 反映 Q-7】capability document (`limits.object_*`、`limit_enforcement.object_*`、`authorization_propagation_bound_ms`) を返す process と専用単位の設定値は同じ出所から導き、起動時に一致を検査する (台帳 `RM` P-3。§3.1 の Q-7 の要件 6)。

【v0.5 2026-10-02 設計レビュー 2 反映 N-19】`object_requests_per_minute` は専用単位で数える (鍵 credential_id)。単位が 1 instance なら `enforced`、複数 instance なら `deployment_required`。

## 7. conformance tests の候補

【註 2026-10-02】下の本文の「port v1.16」は陳腐化した。現行 port は v1.21 (`conformance-tests/adapter.py:1054`) であり、object の port 拡張は v1.22 以降になる (§0 の A-2 の註。設計レビュー 1 反映 M-22)。条件の書き直しは §7.1。

共通仕様を確定した後、transport 非依存 port v1.16 を使う次のテストを `conformance-tests/` に追加する。各テストは in-process / HTTP / socket × 2 peer の全6 adapter に対して同じ期待結果を検証する。header、streaming、proxy、切断は HTTP/socket 専用条件で追加する。

1. 任意 bytes（NUL、非 UTF-8、画像らしい bytes を含む）を upload し、取得 bytes が完全一致する。
2. 保存・取得メタデータ（content type、filename、size、Content-Digest）が一致する。
3. `Content-Digest` 一致は成功し、不一致は拒否され、取得可能な object を残さない。
4. `object_bytes` を 1 byte 超える upload は `LIMIT_EXCEEDED` になり、下流 storage 呼出し・メタデータのどちらも残さない。
   【v0.3 2026-10-02 設計レビュー 1 反映 M-12】4 を分ける。(i) `Content-Length` が `object_bytes` を超える要求は provider を呼ばず、metadata も残さず拒否する (O-4a)。(ii) 途中で超えた要求は `available` の object と取得可能な metadata を残さず、provider に残ったものは cleanup 対象として記録される (O-4b)。根拠: 旧文は §4 の順序 (pending 永続化と provider 送信が上限検出より先) と両立しない。
5. application A の object を application B が取得・メタデータ取得・削除できず、いずれも `NOT_FOUND` になる。
6. capability が `unavailable` の deployment は、認証後に `CAPABILITY_UNSUPPORTED` を返し、本文を storage へ送らない。
7. idempotency key を伴う再送・同時送信は一 object に収束し、異なる bytes/metadata での同一 key は `CONFLICT` となる。
8. destructive confirmation が無い削除は副作用なく拒否され、正しい confirmation を伴う削除だけが実行される。
9. 同一 object ID の再利用、provider failure、削除後取得、`pending`/`cleanup_failed` object の非公開性を仕様どおりにする。
10. 取得応答が provider URL・provider key・credential を漏らさず、`Content-Digest`、`Content-Disposition`、`X-Request-Id` を含む正しい security headers を持つ。
11. HTTP/socket 専用で、chunked streaming、未認証の小さい byte bound、切断、転送中 revoke、threadpool offload を検証する。

provider を実際に使う認証設定の検証は peer-local integration test と deployment runbook の責務とし、共通 conformance suite が実在するクラウドアカウントを要求してはならない。

### 7.1 条件表 (仮 O-n)

【v0.3 2026-10-02 設計レビュー 1 反映 M-16】上の 1〜11 を条件表の形に書き直す (上の一覧は残す)。

- 番号は `O-1`〜 (仮) とする。正式 ID は契約確定時に `conformance-tests/CONDITIONS.md` で採番する。
- port は v1.22 以降に、streaming 送信 (chunked、途中切断、低速送信) と、偽 provider の状態を読む method を足す (現行 `WireEntry.send` は bytes 一括・`Content-Length` 固定: `conformance-tests/adapter.py:1062-1068`)。
- 【v0.3 2026-10-02 再確認反映 RC-10】port に足す method には、偽 provider に失敗・破損を注入する method (put / get の失敗、読み出し bytes の改変) も含める。偽 provider は test の composition root でだけ選べ、本番の設定では選べない (fail closed。選択は環境変数ではなく test 専用の composition root)。
- `object_storage` は `common_baseline` の外に置き (1.9.0 の floor に入れない)、条件は PROVIDED / ABSENT の分岐で書く。ABSENT は `CAPABILITY_UNSUPPORTED` と storage を呼ばないことを検証し、skip にしない。
- Evidence の語: 「6 adapter」= 全 6 adapter の共通 conformance。「wire」= HTTP / socket 専用条件。「peer-local」= 各 peer の integration test。「deployment」= `security/CONTROL_MAPPING.md` の行に記録する deployment evidence。
- 変異の列は「その条件だけを壊す変異」の候補であり、`tools/dev/mutate.py` の引数は作業指示書で定める。
- 【v0.5 2026-10-02 設計レビュー 2 反映 N-19】6 adapter の composition root は 1 process で複数 application の object を serve する (本番の A-1 構成とは違う。test 専用の composition root)。O-5 はその構成での所有照合を見る。

| ID | Condition | Invariants | Evidence | 観測点 | 変異の候補 | 旧番号 |
| --- | --- | --- | --- | --- | --- | --- |
| O-1 | 任意 bytes (NUL、非 UTF-8、画像らしい bytes) の upload と download が完全一致する | SI-11 | 6 adapter | 取得 bytes = upload bytes | 保存時に末尾 1 byte を落とす | 1 |
| O-2 | 保存・取得 metadata (content type、filename、size、Content-Digest) が一致し、filename の正規化 (§3.2.2) が両 peer で同値。【v0.5 2026-10-02 設計レビュー 2 反映 N-9】観測の入力に `"` と `;` を含む filename を加える | SI-05 | 6 adapter | `ObjectDescriptor` の各 field、同じ入力 filename に対する両 peer の出力 | 片 peer の NFC 正規化を外す | 2 |
| O-3 | `Content-Digest` 一致は成功、不一致は拒否され取得可能な object を残さない。`sha-256` の member 無しは `VALIDATION_FAILED` (`content_digest`)、他 algorithm の member は無視 (§3.2.3) | SI-05、SI-11 | 6 adapter | 応答 code、拒否後の metadata 取得が `NOT_FOUND` | upload 側の digest 照合を外す | 3 |
| O-4a | `Content-Length` が `object_bytes` を超える要求は provider を呼ばず metadata も残さず `LIMIT_EXCEEDED` (`object_bytes`) | SI-08 | 6 adapter。【v0.3 2026-10-02 再確認反映 RC-17】wire (4 adapter) に改める。in-process では `Content-Length` の概念が無いので対象外 | 偽 provider の呼出し 0、metadata 0 | `Content-Length` の事前検査を外す | 4 (i) |
| O-4b | 途中で `object_bytes` を超えた要求は `available` の object と取得可能な metadata を残さず、provider に残ったものが cleanup 対象として記録される | SI-08、SI-11 | wire | 取得が `NOT_FOUND`、偽 provider の残存物に対応する cleanup 記録 | 超過時の cleanup 記録を書かない | 4 (ii) |
| O-5 | application A の object を application B が取得・metadata 取得・削除できず、いずれも `NOT_FOUND` (期待値は §11 の Q-2 の案 (ii) で `AUTH_INVALID` に変わり得る)。【v0.3 2026-10-02 再確認反映 RC-4】期待値は全案で `NOT_FOUND` に固定する (B が自分の経路で A の object_id を要求したとき)。他 application の単位 / URL へ誤配されたときの結果は O-5 ではなく §11.1 の最終列 | SI-01 | 6 adapter | 3 操作の応答 code | 所有 application の照合を外す | 5 |
| O-6 | capability が PROVIDED / ABSENT で分岐する。ABSENT は認証後に `CAPABILITY_UNSUPPORTED` を返し storage を呼ばない。【v0.5 2026-10-02 設計レビュー 2 反映 N-16】ABSENT の観測は「読まれた octet 数 0 と 100 Continue の不送出」(wire) とし、偽 provider の呼出し 0 だけにしない。ABSENT の分岐を通す plug 構成 (object_storage が unavailable の instance) を必須にする | SI-15 | 6 adapter | 応答 code、偽 provider の呼出し 0 | capability 判定を本文の転送後に移す | 6 |
| O-7 | idempotency の再送・同時送信は一 object に収束 (`available` は高々 1)、異なる bytes / metadata の同一 key は `CONFLICT`。replay の `X-Request-Id` と `request_id` は元の値。敗者の pending object は cleanup される (§3.2.1)。【v0.5 2026-10-02 設計レビュー 2 反映 Q-9】replay の `X-Request-Id` は replay 要求自身の `request_id`、body の `request_id` は元の値 (上の「replay の `X-Request-Id` ... は元の値」を改める。§3.2.1 の Q-9) | SI-11 | 6 adapter (同時送信は wire) | available な object の数、応答の request_id、偽 provider の残存物 | digest の材料から `Content-Type` を外す | 7 |
| O-8 | 確認不足 (本文 `{}`) の削除は副作用なく `DESTRUCTIVE_CONFIRMATION_REQUIRED`、正しい confirmation で `200 ObjectDeleteResult`、再送は `NOT_FOUND`、`dry_run` / `budget` は `VALIDATION_FAILED` (`unsupported_field`)。【v0.3 2026-10-02 再確認反映 RC-1】再送を分ける: `idempotency_key` なしの再送は `NOT_FOUND`、retention 内に同じ key・同じ digest の再送は元の 200 (`ObjectDeleteResult`、`request_id` も元の値) の replay、digest が異なれば `CONFLICT`。【v0.3 2026-10-02 再確認反映 RC-9】`dry_run` / `budget` の violated_declaration は `request_schema` | SI-09 | 6 adapter | 応答 code と本文、削除前後の取得 | 確認無しで削除を実行する | 8 |
| O-9 | `pending` / `deleting` / `deleted` / `cleanup_failed` の object は `NOT_FOUND`。provider 失敗は `SERVICE_UNAVAILABLE` で object を残さない。同一 object ID は再利用されない | SI-11 | 6 adapter | 状態ごとの取得・metadata 取得の応答 | `pending` を取得可能にする | 9 |
| O-10 | download 応答は `Content-Length`、`Content-Digest`、`Content-Disposition: attachment`、`X-Content-Type-Options: nosniff`、`Cache-Control: no-transform`、`X-Request-Id` (body の `request_id` があれば同値) を持ち、provider URL・provider key・credential を含まない。【v0.5 2026-10-02 設計レビュー 2 反映 Q-9】`X-Request-Id` はその要求自身の `request_id` (上の「body の `request_id` があれば同値」を改める。§3.2 の Q-9)。【v0.5 2026-10-02 設計レビュー 2 反映 N-14】`Cache-Control` は `private, no-store, no-transform` (§3.3 の N-14) | SI-10 | wire | 応答 header と本文の走査 | `Cache-Control: no-transform` を外す | 10 |
| O-11 | upload 本文を全量メモリにバッファしない (【v0.3 2026-10-02 再確認反映 RC-18】両論の註は表の後) | SI-08 | wire | 偽 provider が最後の chunk の前に先頭 bytes を受け取っている | 本文を読み切ってから provider に渡す | 11 |
| O-12 | 未認証要求は小さい byte bound を超えて本文を読まず、本文を読まずに拒否したときは `Connection: close` で接続を閉じる。【v0.5 2026-10-02 設計レビュー 2 反映 N-7】object 経路は認証前に本文を 1 octet も読まない (§3.4 の段 (1))。本文を読み終える前に応答するときは認証の前後を問わず `Connection: close` で閉じ (§3.3 の N-7)、`LIMIT_EXCEEDED` の後に client が送り続けた bytes が読まれないことを観測する | SI-08、SI-15 | wire | 読まれた octet 数、接続の終了 | 認証前に object 経路の大きい bound を適用する | 11 |
| O-13 | 一定速度の download の途中 t0 で revoke すると、t0 + 宣言 `authorization_propagation_bound_ms` 以内に接続が終わる。再認可で `AUTH_STATE_UNAVAILABLE` なら中断する (§11 の Q-4 の裁定に依存)。【v0.4 2026-10-02 依頼者裁定の帰結 Q-4】条件の形に確定する: 一定速度で読む download の途中 t0 で revoke → t0 + 宣言 bound 以内に接続が終わる (受信長 < `Content-Length`)。Q-4 は (a) (§6 の 5 の Q-4 の段落)。【v0.5 2026-10-02 設計レビュー 2 反映 N-11】試験配備の bound と転送時間の関係: 転送時間 ≫ t0 + 宣言 bound + 余裕とし、`object_transfer_ms` はそれより大きくする。revoke しない同速度の download が完走する陽性対照を必須にする。終了判定はサーバ側の送信停止 (偽 provider の読み出し停止) で行い、client 側の EOF は使わない。upload 側の対は O-27 | SI-13、SI-15 | wire | 接続終了の時刻。【v0.4 2026-10-02 依頼者裁定の帰結 Q-4】受信長と `Content-Length` | 転送中の再認可を外す (完了時だけにする) | 11 |
| O-14 | provider 読み出しを N byte 後に失敗させると、受信長 < `Content-Length` で接続が終わり、chunked の正常終端が無い | SI-11 | wire (socket) | 受信長と接続終了 | 失敗時に正常終端を送る | 11 |
| O-15 | `Content-Length` > `object_bytes` は本文を読む前に `LIMIT_EXCEEDED`。`Expect: 100-continue` には認証と検査の前に 100 を返さない | SI-08 | wire | 100 の送出時点、読まれた octet 数 | 100 を即時に返す | — |
| O-16 | `object_transfers` の枯渇は `LIMIT_EXCEEDED` (`object_transfers`)。切断・例外の後に枠が戻る。object 経路のうち upload / download は持ち替え後に `requests_per_minute` / `concurrency` を消費しない (metadata / delete は RC-6 のとおり concurrency を要求全体で保持する。監督 2026-10-02)。【v0.5 2026-10-02 設計レビュー 2 反映 N-7】`LIMIT_EXCEEDED` (`object_transfers`) の後に client が送り続けた bytes が読まれないことを観測する | SI-08 | wire | 直後の upload が枠を取れること、JSON 経路の枠の残量 | 切断時に枠を解放しない | 11 |
| O-17 | application A の provider identity で application B の bucket への get / put / delete が provider 自身から拒否される | SI-00、SI-01 | peer-local と deployment (`security/CONTROL_MAPPING.md` の SI-00 行)。共通 suite は実クラウドを要求しない | provider の拒否応答 | A の identity に B の bucket の権限を与える構成 | — |
| O-18 | cleanup worker は A の DB にある B の provider key を持つ `cleanup_failed` 行に対し、B の bucket に何もせず security-control failure を監査する (§4 の M-4) | SI-00、SI-14 | peer-local | B の bucket の状態、監査 event。【v0.3 2026-10-02 再確認反映 RC-21】監査 event (security-control failure) の観測を必須にする。B の bucket に何も起きないことだけでは空振りし得る | worker が行の provider_key をそのまま使う | — |
| O-19 | upload 中に process を SIGKILL すると、再起動後に `pending` が期限で回収され provider object が残らない。cleanup の成功・失敗が監査される (§4 の M-5) | SI-11、SI-14 | peer-local | 偽 provider または provider の残存物、監査 event | `pending` を cleanup 対象から外す | 9 |
| O-19b | 【v0.3 2026-10-02 再確認反映 RC-2】確認済み削除の途中で SIGKILL すると、再起動後に回収され provider object が残らない (§4 の RC-2。O-19 と同形) | SI-11、SI-14 | peer-local | 偽 provider または provider の残存物、監査 event | `deleting` を cleanup 対象から外す | — |
| O-20 | 宣言 `audit_query.operations` に 4 操作名、`target_kinds` に `object` があり、宣言と実挙動が一致する。`upload_object` の event は成功応答の前に同期で書かれる | SI-14 | 宣言と一致は 6 adapter。同期書き込みの観測は `conformance-tests/CONDITIONS.md` C-33 と同じ composition root (wire、workers = 2) で行い、in-process は対象外 (監督 2026-10-02) | 成功応答の受信後の audit_query の結果。【v0.3 2026-10-02 再確認反映 RC-11】`conformance-tests/CONDITIONS.md` C-33 の形 (成功応答の直後に process を SIGKILL し、再起動後の audit_query に event がある) にする | upload の event を応答後に非同期で書く | — |
| O-21 | 同期 provider SDK の呼出しが event loop 上で走らない (threadpool offload) | SI-08 | peer-local | event loop の占有の観測 (形は peer が定める) | offload を外す | 11 |
| O-22 | download で provider が保存値と異なる bytes を返すと本文が切られ (O-14 と同じ観測)、security-control failure が監査される | SI-11、SI-14 | wire | 受信長と接続終了、監査 event | download 側の digest 照合を外す | — |
| O-23 | §3.4 の失敗の表の各行の入力に、表のとおりの code / violated_declaration / field を返す (「未定」の欄は 2026-10-02 の監督裁定で埋めた)。【v0.5 2026-10-02 設計レビュー 2 反映 N-5】code は許容集合で検証する (`object_id` の構文違反は {`IDENTIFIER_INVALID`, `VALIDATION_FAILED`}、失効 / 無効化は `conformance-tests/CONDITIONS.md` C-08 の集合)。socket plug での path の wire rejection (`conformance-tests/CONDITIONS.md` C-03 の開示) は `object_id` にも及ぶ。【v0.5 2026-10-02 設計レビュー 2 反映 N-7】`Content-Length` の 2 行は対象外 (§3.4) | SI-05、SI-10 | 6 adapter (header の行は wire) | problem 応答の各 field | 行ごとに該当する検査を外す | — |
| O-24 | 【v0.4 2026-10-02 依頼者裁定の帰結 Q-1】`Content-Type: application/json` で upload した、errors.shape を満たす本文の object (乙により problem+json では保存できないので、観測は `application/json` で行う。監督 2026-10-02) を契約だけで組む client で download すると、bytes の成功に分類される (2xx は media type を問わず response schema と照合しない。§3.3 の Q-1)。upload 時に media type が `errors.content_type` に一致する要求は `VALIDATION_FAILED` (`content_type`、`header/content-type`)。【v0.5 2026-10-02 設計レビュー 2 反映 N-3】`Content-Digest` を持たない 2xx (前段の 200 を模す) が解釈しない失敗に分類されることも観測する。【v0.5 2026-10-02 設計レビュー 2 反映 N-12】upload 側の入力に `Application/Problem+JSON; charset=utf-8` を含める | SI-05 | wire (契約だけで組む client。`conformance-tests/CONDITIONS.md` C-35 への影響は契約改版の WP で見る) | download の分類結果、upload の problem 応答の各 field | (download) 2xx でも media type が errors.content_type なら失敗に分類する。(upload) errors.content_type の拒否を外す。【v0.5 2026-10-02 設計レビュー 2 反映 N-12】download 側の変異を「download の 2xx を media type で分類する (1.14.0 の規則に戻す)」と「peer が download の `Content-Type` を errors.content_type にする」に替える (上の download 側の変異は残す) | — |
| O-25 | 【v0.4 2026-10-02 依頼者裁定の帰結 Q-3】1 byte/秒の upload が宣言 `execution_ms` で `LIMIT_EXCEEDED` (`limit_class: execution_ms`) になり、`object_transfers` 枠が解放される (直後の upload が枠を取れる)。【v0.5 2026-10-02 設計レビュー 2 反映 Q-6】上の `execution_ms` を `object_transfer_ms` に改める (旧文は残す): 1 byte/秒の upload が宣言 `object_transfer_ms` で `LIMIT_EXCEEDED` (`limit_class: object_transfer_ms`) になり、`object_transfers` 枠が解放される | SI-08 | wire | 応答 code と limit_class、拒否までの時間、直後の upload が枠を取れること | upload の転送に `execution_ms` の期限を掛けない。【v0.5 2026-10-02 設計レビュー 2 反映 Q-6】upload の転送に `object_transfer_ms` の期限を掛けない | — |
| O-26 | 【v0.4 2026-10-02 依頼者裁定の帰結 Q-2 (監督 2026-10-02)】誤配の観測: application B の credential を application A の専用単位へ直接送ると `AUTH_INVALID` で閉じ、bytes は保存されず、認証拒否の audit event が残る (router を経ない直接送信で観測する) | SI-00、SI-06、SI-14 | peer-local / deployment evidence (共通 conformance の 6 adapter では router と専用単位を立てないため対象外)。【v0.5 2026-10-02 設計レビュー 2 反映 (監督)】本番形 (router + 専用単位) の宣言値 (limits.object_*、limit_enforcement.object_*、authorization_propagation_bound_ms) と実挙動の一致もここで観測する (P-3) | A の単位の応答 code、A の bucket と metadata に変化が無いこと、audit の denial | A の単位が自分の application 以外の credential も受理する | — |
| O-27 | 【v0.5 2026-10-02 設計レビュー 2 反映 N-11】一定速度の upload の途中 t0 で revoke すると、t0 + 宣言 `authorization_propagation_bound_ms` 以内に既存 code の problem 応答 (§3.4 の再認可の行。または接続終了) となり、object は available にならない (O-13 の upload 側の対) | SI-13、SI-15 (O-13 と同じ) | wire | 応答 code または接続終了の時刻、metadata 取得が `NOT_FOUND` | upload の再認可を外す | — |
| O-28 | 【v0.5 2026-10-02 設計レビュー 2 反映 N-18】検査順: 段 (4) の 2 つの違反 (例: `Content-Type` 欠落 + `Idempotency-Key` 長さ違反) を含む要求は先の方の field を返す。段 (3) と (4) の同時違反は `CAPABILITY_UNSUPPORTED` (§3.4 の N-18) | SI-05、SI-10 (O-23 と同じ) | wire | problem 応答の code と field | 段 (4) 内の順を入れ替える | — |

【v0.3 2026-10-02 再確認反映 RC-18】O-11 の註 (両論): (a) 実装が溜めてよい上限 B octet を契約で固定し、観測は B を超える本文で行う。(b) O-11 を peer-local に移す。SDK の part 長・GCS の chunk 長は未確認。確定は設計レビュー 2。

【v0.5 2026-10-02 設計レビュー 2 反映 RC-18 の見立て】O-11 の註の結論 (監督 2026-10-02): 偽 provider を peer の storage adapter の境界に置き、O-11 は wire のまま残す (client は前半を送り、偽 provider が受け取るまで待ってから残りを送る)。SDK の part 長は peer-local。契約に上限 B の定数は置かない。

【v0.5 2026-10-02 設計レビュー 2 反映 N-18】B-5 の 4 class の N / N+1 境界は、既存 `conformance-tests/CONDITIONS.md` C-05 の `_CAPABILITY_CONDITIONED` (`conformance-tests/test_c05_limit_declaration_agreement.py:84-88`) に object_storage 条件付きで入れる。`conformance-tests/test_contract.py:2372` の limit class 数 17 の pin は改版対象である。(監督 2026-10-02) Q-6 の `object_transfer_ms` も同じ条件付き集合に入れる (object の class は 5 つ。pin は 17 → 22)。

## 8. 運用値・後続 capability の検討事項

§0 の API・安全性に関する判断は確定した。実装前に配備ごとの値と運用手順を決める。

【註 2026-10-02】v0.3 の時点で、§11 の Q-0〜Q-5 が依頼者裁定待ちである。下の 1 の timeout・再認可周期は Q-3 / Q-4 の裁定に従う。

1. 初期 deployment の `object_bytes`、`object_metadata_bytes`、`object_requests_per_minute`、`object_transfers`、認証前 byte bound、timeout、再認可周期。
2. `cleanup_failed` の再試行間隔、監視、alert、保持・法的保全の手順。
3. object metadata を各 application DB に置く。schema/migration の詳細と、provisioning/control 経路が application bucket/identity をどの DB declaration と結び付けるか。
4. マルウェア対策を upload 完了前の必須 gate にするか。初版は対象外と明示し、必要なら `pending_scan` 状態を持つ別 capability とする。

【v0.4 2026-10-02 依頼者裁定の帰結 Q-0〜Q-5】上の【註 2026-10-02】の裁定待ちは、2026-10-02 の依頼者裁定で解けた (§11)。運用値に次を足す。

- Q-3: 宣言しない運用値の timeout は置かない。実装側の socket timeout は宣言 `execution_ms` 以下に設定する運用値とする (v0.2 §6 の 5 の「接続・読取・全体時間の有限 timeout」はこの運用値を指し、別の宣言しない bound ではない。宣言される bound は `execution_ms` だけ。監督 2026-10-02)。
- Q-4: 再認可周期 P は配備値。宣言 `authorization_propagation_bound_ms` は「失効の伝搬遅延 + P」を含む正の値とする (§6 の 5)。
- Q-5: provider 側 quota / 予算 alert、object 数と総容量の監視。class は足さない。
- 【v0.5 2026-10-02 設計レビュー 2 反映 Q-6】上の Q-3 の項の「宣言 `execution_ms` 以下」を「宣言 `object_transfer_ms` 以下」に改める (旧文は残す)。転送時間について宣言される bound は `object_transfer_ms` である (§6.1 の Q-6)。
- 【v0.5 2026-10-02 設計レビュー 2 反映 N-15】総保存量の hard な bound (provider quota または実装側の検査) を配備値として必須にする。alert だけでは SI-08 (`security/SECURITY_INVARIANTS_V1.md`) の Verification を総量について満たさない。provider 側の hard quota の有無は未確認。

## 9. 実施順序

1. A-1 の provider 側分離を前提に、既存の複数 application を一 process で serve する配備を、object-capable endpoint では application 専用の実行単位へ分割する provisioning/deployment 設計を確定する。各 peer-local integration test で provider 自身が越境を拒否することを実測する。
   【v0.4 2026-10-02 依頼者裁定の帰結 Q-2】1 を案 (ii) に合わせて次に改める (旧文は残す)。object-capable endpoint について、1 つの data base URL の前段に router を置き、credential から application を引いて当該 application 専用の object-capable 単位へ振り分ける provisioning/deployment 設計を確定する (§3.1 の Q-2 の段落)。router の欠陥による越境 (SI-00、`security/SECURITY_INVARIANTS_V1.md`) の検証と、provider 自身が越境を拒否することの実測は peer-local integration test と deployment evidence で行う。JSON 経路の serving set (`*_SERVE_APPS`) の分割はここに含めず、台帳 `RM` R-30 の裁定に委ねる。
2. §8 の配備値・運用手順をレビューし、実行環境ごとに確定する。
3. 該当する Security Invariants と threat model の適用を確定する。
4. 共通契約、capability/limit、エラー、操作カタログを更新する。
5. conformance tests を追加し、実装前に失敗することを確認する。
6. r2db-api（R2 adapter、メタデータ、HTTP streaming、設定、local tests）を実装する。
7. MitateDB-api（GCS adapter、メタデータ、HTTP streaming、設定、local tests）を実装する。
8. conformance tests、各 peer の unit/integration tests、公開リポジトリ秘密検査を実行する。
9. 実クラウド環境については、非公開 bucket と最小権限を用いた deployment verification を別 runbook に従って実施する。

【v0.3 2026-10-02 設計レビュー 1 反映 M-20】上の 1〜9 を `CLAUDE.md` の開発順序 (共通 capability → 適用 SI → 共通契約 → conformance 証拠 → 実装 → 実装固有の test / control) に並べ替える (上の一覧は残す)。

1. 共通 capability (`object_storage`) と適用する Security Invariants・threat model の確定 (§2.1)。旧 3。
2. 共通契約 (capability / limit class / エラー / 操作カタログ / media type / idempotency header / destructive の applies_to) の更新。旧 4。
3. conformance tests (§7.1) を追加し、実装前に失敗することを確認する。旧 5。
4. peer ごとの実装と provisioning (r2db-api と MitateDB-api。A-1 の application 専用実行単位を含む。到達経路は §11 の Q-2 と台帳 `RM` R-30 の裁定に従う)。conformance tests、各 peer の unit / integration tests、公開リポジトリ秘密検査を実行する。旧 1、6、7、8。
   【v0.4 2026-10-02 依頼者裁定の帰結 Q-2】到達経路は案 (ii) に確定した (§3.1 の Q-2 の段落)。台帳 `RM` R-30 の裁定は JSON 経路の serving set に委ねる。
5. `security/CONTROL_MAPPING.md` の行と deployment evidence (provider 自身が越境を拒否することの実測を含む)。旧 1 の後半、9。
   【v0.5 2026-10-02 設計レビュー 2 反映 Q-7 / N-15】`security/CONTROL_MAPPING.md` の SI-00 行に router の残余 (§3.1 の Q-7)、SI-08 行に総保存量の残余 (§2 の N-15) を記録する (作業機)。
6. 配備値と運用手順 (§8) の確定。旧 2。

## 10. 現状との突き合わせ (2026-10-02)

【v0.3 2026-10-02 設計レビュー 1 反映 S-1〜S-16】v0.2 の起草 (2026-09-11) 以後に古くなった前提を、監督が現状と突き合わせた結果である。契約は 1.14.0 (`spec/data-service-api.v1.json:6`)、port は v1.21 (`conformance-tests/adapter.py:1054`)、adapter は 6 (`conformance-tests/registry.json`)。表中のファイル名の無い `:N` は `spec/data-service-api.v1.json` の行である。

| # | 設計の前提 (v0.2) | 現状 (file:line) | 食い違い |
| --- | --- | --- | --- |
| S-1 | A-2「port は次版 (v1.16) へ加算的に拡張し、6 adapter 全てが実装する」 | port は v1.21 (`adapter.py:1054` WireEntry、台帳 `RM` R-108)。adapter は 6 のまま。port は in-process adapter も含む 6 adapter が実装する transport 非依存の抽象であり、WireEntry (`adapter.py:1053-1087`、`send(method,url,headers,body)` の body は bytes) は wire 4 plug 限定で in-process は AssertionError | 版番号 v1.16 は陳腐。「次版」は v1.22 以降。bytes を運ぶ既存の経路は WireEntry (wire のみ) と `operation_catalog_document() -> bytes` (`adapter.py:3148`) の 2 つで、in-process adapter に bytes の port method は無い |
| S-2 | 契約だけで要求を組む client に bytes の要求・応答が載る (暗黙) | 1.14.0 `media_type_note` (`:8`): media_type (`application/json`、`:7`) は「every request body a client sends … and every successful response」の media type。`errors.response_classification` (`:895`): 他の media type の応答は「a failure the client does not interpret」。`external_standards` (`:9`): JSON (RFC 8259) for every request and response body。version_binding 1.14.0 (a) (`:40`): 全成功応答が media_type を運ぶのが無条件の義務。`conformance-tests/CONDITIONS.md` C-35 (`:64`) と `reference_client.py` (`:271-304` の `_read` / `_media_type`) はこの分類で動く | raw bytes の upload 本文 (`image/png` 等) と bytes の download 応答は、現行文言のままでは契約違反であり、契約だけで組む client には失敗に分類される。契約 1.x に「media_type の例外 (操作ごとの request / response media type)」を足す決定が要る (§11 の Q-1) |
| S-3 | `{object_id}` の path placeholder | `endpoint_fields_note.path` (`:651`) の placeholder は `{entity}` `{application_id}` `{credential_id}` だけ | `{object_id}` の埋め方 (構文・percent-encoding) を足す必要 |
| S-4 | B-5 の 4 limit class を `limits` / `limit_enforcement` に載せる | `limits.classes` は閉じた語彙 17 (`:929-947`、`:323` は語彙外の key を非適合とする)。`limit_enforcement` の値は enforced / reference_wall_clock / deployment_required / unavailable (`:1351-1360`)。1.8.0 (`:40`): limit_enforcement は deployment 全体を記述し、per-process で複数 process があれば deployment_required。`conformance-tests/CONDITIONS.md` C-32 (`:61`): workers >= 2 で concurrency / requests_per_minute は deployment 全体で bound (両 peer は既に deployment 全体の枠を持つ) | 語彙の追加は契約の版上げ。§6 の 3「process-local 枠しか持てない場合 deployment_required」は、C-32 で両 peer が既に deployment 全体の枠を実現している現状と比べて後退 |
| S-5 | B-12「durable audit の vocabulary に `upload_object` 等を追加」 | audit の operations / target_kinds は実装が `capabilities().audit_query.operations / .target_kinds` で宣言する語彙で、契約は固定 enum を持たない (`:1011-1012`) | 「契約の語彙に追加」ではなく「両 peer が宣言に加え、conformance が宣言と実挙動の一致を見る」形になる |
| S-6 | B-2「既存 destructive-confirmation の JSON を用いる」 | `destructive_confirmation.applies_to` (`:678-683`) は閉じた列挙 + 「future destructive operations inherit this same definition」。`DESTRUCTIVE_CONFIRMATION_V1.md` v1.6 | applies_to への追加が要る (契約)。本文の形式は継承できる |
| S-7 | B-1「任意の `Idempotency-Key` (HTTP header)」 | 契約の idempotency は request field `idempotency_key` (`:1304-1307`、`:850-852`)。1.8.0 の同時到着直列化 (`:40`、`conformance-tests/CONDITIONS.md` C-27 `:56`)。HTTP header `Idempotency-Key` は契約に無い | raw bytes 本文に request field は置けないので header は新形式。契約の idempotency 節に「header 経由の key」を足す決定が要る。digest の定義 (bytes の content digest + 正規化 metadata) も契約側の定義 |
| S-8 | B-3「bytes を返す成功応答も `X-Request-Id` を必須で返す」(既存の相関 header と読める) | spec に `X-Request-Id` は無い。`request_id` は body の field (`:871`、QueryResult `:1441` 等) と audit field。両 peer の http.py は実装として `x-request-id` 応答 header を返す (`r2db-api/src/r2db_api/http.py:41`、`MitateDB-api/src/mitatedb_api/http.py:160`) | B-3 は peer 実装の header を契約へ昇格させる決定になる。bytes 応答には body の request_id が置けないので header が唯一の経路 |
| S-9 | 新 capability `object_storage` | capability 名 14 (`:304-317`)。common_baseline (1.9.0) は floor で、外の capability は宣言で統御 | object_storage を common_baseline の外に置くことを明記する必要 (置かないと 1.9.0 の rule で全 peer に必須になる) |
| S-10 | 操作カタログ | OperationCatalogEntry の必須 field: name, method, path, roles, requires_capability, atomicity, destructive, request_schema, response_schema (`:2069`)。catalog は契約版の派生で byte-identical (1.9.0 (b)、`conformance-tests/CONDITIONS.md` C-29) | bytes の操作の request_schema / response_schema の表し方が未定 |
| S-11 | 監査の process 喪失 | 1.13.0 `audit.process_loss_policy` (`:979`)、`conformance-tests/CONDITIONS.md` C-33 (`:62`)、`AUDIT_PROCESS_LOSS_V0_1.md` v0.5 | upload 完了応答の後の process 喪失でも audit event を失えない。cleanup worker の監査は未定 |
| S-12 | application 単位の直列化 | `MITATEDB_APPLICATION_SERIALIZATION_V0_1.md` v0.7、`conformance-tests/CONDITIONS.md` C-34 (`:63`) | object_transfers と同じ application の直列化の関係が未記述 |
| S-13 | A-1「application 専用の実行単位」 | 台帳 `RM` R-30 (`RM`:456、未着手、M、Class D): SI-00 の境界と 1 process が複数 Application の DSN を保持する構成の関係が未確定。SI-00 の脅威仮定 "single application-facing implementation defect" (`SECURITY_INVARIANTS_V1.md:58,68`)、T-13 "where feasible" (`THREAT_MODEL_V1.md:133`) | A-1 は R-30 の一方の答え (serving set を 1 Application に限る) を object-capable 実行単位に先取りしている。R-30 の裁定と両立させる必要 (§11 の Q-2) |
| S-14 | B-7「転送中の再認可」 | SI-13 (`SECURITY_INVARIANTS_V1.md:338-354`) の authorization propagation bound。台帳 `RM` R-42 (`RM`:462、未着手、L): 期限切れ要求の意味論 (execution_ms の計測開始・待ちの扱い) が未決 | 転送中の期限 (execution_ms は転送に掛かるか、別 class か) は R-42 と連動 (§11 の Q-3、Q-4) |
| S-15 | 「HTTP 本文を全量メモリへバッファしない」「現在の JSON 用 request-byte middleware」 | 両 peer に multipart / octet-stream / streaming の語は無い (探索で確認)。request_bytes は `r2db-api/src/r2db_api/limits.py:12,66,80` 等 | 前提どおり (実装未着手)。変化なし |
| S-16 | 実需 | 台帳 `RM` §3.2 突合表 (`RM`:274): 部分的。着手条件の充足は依頼者裁定 | 設計文書は実需の記述を持たない (§1 の註、§11 の Q-0) |

### 10.1 読解の要点 (監督が原文で確かめたもの)

- **limit / 複数 process**: `MULTI_PROCESS_WORKER_V0_1.md` v0.5 の裁定 10 (`:775-779`): `concurrency` の admission slot は host 内の全 worker で共有する OS flock slot (crash で kernel が解放。DB 往復なし)。PostgreSQL 共有 counter は crash で slot が漏れるため却下。共有は 1 host に閉じ、複数 host は `deployment_required` を宣言するか別起票。裁定 27 (`:845`): `concurrency` は「slot directory が配線され、かつ `process_ceilings.data` ≤ workers」のときだけ `enforced`、それ以外 `deployment_required`。契約 `:324`: limit_enforcement は base URL 背後の deployment 全体を記述。→ v0.2 の §6 の 3 は契約 `:324` と整合するが、`object_transfers` の枠の置き場、1 host 内の複数 worker を「複数 process」に含めるか、認証後の枠が転送中の crash で漏れないことを述べていない。既存の flock slot は認証前 (pre-auth) の枠であり、object_transfers は認証後の枠である (v0.3 の §6 の 3 の M-3、§6.1)。
- **監査の process 喪失**: `AUDIT_PROCESS_LOSS_V0_1.md` v0.5 決定 1-A (`:77-79`): 通常 event も応答の前に同期で書く。destructive は data commit の前に pre_commit で書く。`security/CONTROL_MAPPING.md:1825`: 未応答の in-flight 要求は policy の外 (allow 行だけ残り commit が無い状態を許容)。→ upload の成功応答の前に `upload_object` の event を同期で書く義務が掛かる。bytes を provider に送った後・応答前の process 喪失は policy の外だが provider に孤児 object が残り、pending 行 + cleanup worker がそれを担う。cleanup worker (応答を返さない) の監査、`cleanup_failed` の監査 (SI-14) は v0.2 に無い (v0.3 の §4 の S-11 / M-4 / M-5)。
- **application 単位の直列化**: `MITATEDB_APPLICATION_SERIALIZATION_V0_1.md` v0.7 (甲) (`:136`)・D-3 (`:163-194`): cell lock は廃止、pool は application × role の借用、調停は application DB 内の advisory lock (per-key (idempotency) → 件数 lock → 3a schema → 3b 実体 → 表 lock → revision 行)。keyed の非 replay の書き込み同士は件数 lock で application 全体が直列。lock 待ちは deadline 由来 timeout で打ち切られ `execution_ms` の `LIMIT_EXCEEDED` に写る。→ B-1 の「同一 key の同時送信の直列化」を既存の per-key advisory lock で実現すると、upload 全体 (秒〜分) が per-key lock・件数 lock・pool 接続を保持し、同 application の keyed 書き込み全般と他 object の upload を止める。v0.2 は 2 transaction 構成と直列化の単位を明記しておらず、契約 `:851` の「record は effects と同じ transaction」は provider 側の効果 (transaction 外) に対して定義されていない (v0.3 の §3.2.1、§4 の M-7)。
- **SI-00 / R-30**: SI-00 は "single application-facing implementation defect" も対象 (`SECURITY_INVARIANTS_V1.md:58,68`)、T-13 は "where feasible" (`THREAT_MODEL_V1.md:133`)。台帳 `RM` R-30 (`RM`:456) は未着手・依頼者裁定待ち。現行は `*_SERVE_APPS` で 1 process が複数 Application を serve する構成を許容 (`MULTI_PROCESS_WORKER_V0_1.md:182-215`)。→ A-1 は object-capable endpoint に限って「1 実行単位 = 1 application」を課す。R-30 が未決でも A-1 は自分の範囲で成立するが、§9 の 1 (既存配備の分割) は R-30 の裁定と衝突しうる (§11 の Q-2)。
- **SI-13 / R-42**: SI-13 (`SECURITY_INVARIANTS_V1.md:338-351`) は「subsequent authorization」が bound 内に止まること、「indefinite usable session」を残さないこと。要求単位の認可に掛かる文言で、長い転送の途中の再認可を要求する文言は無い。→ B-7 は文言を超える適用 (invariant の追加ではなく既存 SI-13 の機構の適用決定)。台帳 `RM` R-42 (`RM`:462) は `execution_ms` の計測開始と待ちの扱いが未決で、転送時間を `execution_ms` に含めるかは同種の未決 (§11 の Q-3、Q-4)。
- **契約 1.14.0 の文言**: 上表の S-2・S-3 のとおり。エラー応答 (`errors.content_type`、`:866`) と分類規則 (`:895`) は不変のまま、操作別の request / response media type を足す改版 (1.15.0 以降) が要る。
- **idempotency**: `idempotency_key` は JSON request の field (string, maxLength 128。`:1090`, `:1139`, `:1304`)。digest は request object から (key・plan・dry_run を除く。`:851`)。1.8.0 の同時到着直列化 (`:851` 末尾)。header 方式は未定義。再送・競合・直列化の意味は流用できるが、key の置き場・digest の材料・record と effect の同一 transaction 原則と provider 効果の関係の再定義が要る (v0.3 の §3.2.1)。

## 11. 依頼者裁定待ち (2026-10-02)

【裁定 2026-10-02】依頼者の裁定 (Q-0〜Q-5 に対する裁定。引き継ぎ書 `HANDOVER_20261002_R36_FABLE.md` §4 の提示に対する返答。逐語):

> 全て監督推奨で進めてください

依頼者裁定は逐語で記録し、再審議しない (`docs/work-orders/OPERATING_CONDITIONS.md` §1.7 の 51)。裁定文に書かれていないことは「監督の読み」と明記する。各 Q の末尾に【裁定 2026-10-02】行を置き、両論の本文は残す。下の段落の「v0.3 では確定しない」は v0.3 の記録として残す。

設計レビュー 1 回目で挙がった、依頼者決定 A-1〜B-12 と現状の食い違い、または決定の確定後に挙がった露出である。決定は再審議しない。各件は両論のまま置き、v0.3 では確定しない。「推奨」は監督の推奨であり、裁定ではない。

【v0.5 2026-10-02 設計レビュー 2 反映 Q-6〜Q-9】Q-6〜Q-9 は設計レビュー 2 回目で挙がった、依頼者裁定 Q-0〜Q-5 の帰結と現状の食い違いであり、監督の突合で依頼者裁定級とした。形は Q-0〜Q-5 と同じ。各件の末尾の【裁定 2026-10-02】行は、上の依頼者裁定の逐語を本件にも及ぶものとした監督の読みである。

### Q-0 着手条件の充足

- 決定: 台帳 `RM` R-36 の着手条件は「設計レビュー。充足は依頼者裁定」。
- 【v0.3 2026-10-02 再確認反映 RC-14】決定 (追記): 台帳 `RM` R-36 の着手条件には「運用開始後 (v1.105 の追記: 運用が始まって data と client が存在しても直す費用は上がらない)」もある (`RM`:459)。
- 現状: 実需は台帳 `RM` §3.2 の突合表で「部分的」(Mitate `docs/remaining-work-index.md` §将来設計・保留「添付ファイル・画像 — F2 とは別工程として保留」、`docs/design/agent-entry-record.md` §6.1。data-service-api への具体的な要件は未確定)。
- 【v0.3 2026-10-02 再確認反映 RC-14】運用開始の現状は本 session では確かめていない (作業機で台帳 `RM` §1 の現状から確認)。
- 食い違い: 設計レビュー 1 回目は 2026-10-02 に行ったが、契約・conformance・実装へ進む着手条件の充足は依頼者裁定である。
- 選択肢 (両論): (a) 充足とみなし、設計レビュー 2 回目へ進む。(b) 実需の記録を待つ (候補のまま保留)。
- 推奨: 監督は判断しない (依頼者事項)。
- 【裁定 2026-10-02】依頼者「全て監督推奨で進めてください」→ (a) 充足とみなし、設計レビュー 2 回目へ進む (監督の読み)。帰結は冒頭の版数表 (v0.4 行)、冒頭の v0.4 の印の行、§1。
- 監督の読み: 監督は Q-0 に推奨を置かなかった (上の「監督は判断しない」)。「進めてください」を、着手条件 (設計レビュー。充足は依頼者裁定) の充足 = 選択肢 (a)「充足とみなし設計レビュー 2 回目へ進む」と読む。依頼者がこの読みを覆すときは本節に【訂正】を足す。

### Q-1 download 応答の分類

- 決定: §2「`Content-Type` は保存・返却する」、B-4、B-11 (ブラウザ向け attachment)。
- 現状: 契約 1.14.0 は全成功応答の media type を `application/json` に固定し (`spec/data-service-api.v1.json:8`、`:40` の 1.14.0 (a))、client は media type だけで分類する (`:895`、「HTTP status decides neither」)。§10 の S-2。
- 食い違い: (i) bytes の成功応答は現行文言で契約違反であり、かつ「解釈しない失敗」になる。(ii) 送信者が `Content-Type: application/problem+json` と errors.shape を満たす本文の object を upload すると、同 application の agent が download したとき、200 でも偽の失敗 (例: `AUTH_REVOKED`) として読む。`application/json` なら response schema との照合に回る。
- 選択肢 (両論):
  - (甲) 契約の分類規則に download 操作だけの例外を足す。2xx は bytes の成功 (media type を問わず response schema と照合しない)、2xx 以外で errors.content_type なら失敗、それ以外は解釈しない失敗。upload は request media type を operation 別に許す。
  - (乙) 甲に加えて、upload で media type が errors.content_type に一致するものを `VALIDATION_FAILED` で拒否する (problem+json 文書を保存する能力を失う)。
  - (丙) download は常に `application/octet-stream` で返し、保存値は metadata にだけ載せる (§2 の「返却する」と B-11 の想定を変える)。
  - いずれも契約の `media_type_note` / `response_classification` / `external_standards` の改版 (1.x.0、従属判断 19 の例外) になる。
  - 【v0.3 2026-10-02 再確認反映 RC-19】`spec/data-service-api.v1.json:36` では additive な capability は minor。object_storage は common_baseline の外の新 capability で、既存の要求・応答の意味は変えない。media_type_note / response_classification の改版は新しい操作にだけ掛かる例外の追加であり、既存操作の分類は不変。したがって minor (1.x.0) と読む。semantic change と読む余地があれば major であり、その判断は依頼者。
- 推奨 (監督の推奨): (甲) + (乙)。
- 【裁定 2026-10-02】依頼者「全て監督推奨で進めてください」→ (甲) + (乙)。帰結は §2、§3.2、§3.3、§3.4、§7.1 の O-24 (§2.1 の対応を含む)。

### Q-2 A-1 の application 専用実行単位への到達経路

- 決定: A-1。
- 現状: object 経路は data surface に属し、client は `surfaces.data.base_url` から URL を組む (`spec/data-service-api.v1.json:35`)。data / control の文書は同じ surfaces を返し、control surface は deployment に 1 つ (`:1410`)。limit_enforcement は base URL 背後の全 process を記述する (`:324`)。base URL を serve する process は 1 host (`MULTI_PROCESS_WORKER_V0_1.md:778`)、concurrency の enforced は 1 host の slot 共有が条件 (同 `:845`)。`conformance-tests/CONDITIONS.md` C-19 は 1 base URL と 1 credential で足りることを要求する。台帳 `RM` R-30 (SI-00 の境界と複数 Application の DSN) は未決。§10 の S-13。
- 食い違い: 1 つの data base URL の背後に application ごとの実行単位を置く経路が設計に無い。v0.2 の §9 の 1 は deployment 設計に回しているが、契約の問題である。
- 選択肢 (両論): §11.1 の表の (i)〜(iii)。
- 推奨 (監督の推奨): (ii) を台帳 `RM` R-30 の裁定と同時に決める。各案の `concurrency` / `object_transfers` の `limit_enforcement` の帰結を表 (§11.1) で併記する。
- 【裁定 2026-10-02】依頼者「全て監督推奨で進めてください」→ (ii)。帰結は冒頭の A-1 の註、§3.1、§6.1、§9 (旧 1 と新 4)。下の §11.1 の表は両論の記録として残す。
- 監督の読み: 推奨の「台帳 `RM` R-30 の裁定と同時に」の部分について、R-30 は台帳の別行 (Class D、専用の裁定) であり v0.4 では触れない。object 経路の到達経路としては (ii) を確定し、R-30 の裁定は (ii) (router は multi-application 部品、各 application 専用単位は 1 application だけを serve) と矛盾しない形で別途行う。
- 【v0.5 2026-10-02 設計レビュー 2 反映 N-21】上の裁定行の帰結の列挙に §7.1 の O-26 を足す (裁定行の本文は変えない)。
- 【v0.5 2026-10-02 設計レビュー 2 反映 Q-7】上の監督の読みの「R-30 の裁定は (ii) ... と矛盾しない形で別途行う」を撤回し、「台帳 `RM` R-30 は独立に裁定する。(ii) の router は application-facing 実装ではなく前段であり、R-30 のどちらの答えとも両立する。R-30 の裁定時に router の位置づけを確認する」に改める (旧文は残す。§11 の Q-7、§3.1 の Q-7 の段落)。

#### 11.1 到達経路の選択肢

「監督の見立て 2026-10-02」の欄は、v0.3 の材料 (設計レビュー 1 と監督の突合) に無く監督が起草後に埋めたものであり、設計レビュー 2 回目で検証する。裁定は依頼者。

| 案 | 内容 | 改版の要る契約・規則 | `concurrency` の `limit_enforcement` | `object_transfers` の `limit_enforcement` | SI-00 の観点 | O-5 の期待値。【v0.3 2026-10-02 再確認反映 RC-4】他 application の単位 / URL へ誤配されたときの結果 (欠陥の観測。peer-local または deployment evidence の条件であり O-5 ではない) |
| --- | --- | --- | --- | --- | --- | --- |
| (i) | application ごとに別の data base URL (= 別 deployment)。台帳 `RM` R-30 の「serving set を 1 Application に限る」側を全面採用する | control surface と、surfaces 同一の規則 (`spec/data-service-api.v1.json:1410`) | 監督の見立て 2026-10-02: 各 deployment が 1 host なら `enforced` (`MULTI_PROCESS_WORKER_V0_1.md` 裁定 10・27 のまま) | 監督の見立て: 同じく 1 host 内の共有 slot で `enforced` | 監督の見立て: multi-application 部品が無く SI-00 の面では最も単純。費用は application 数に比例する deployment 数 | 監督の見立て: 別 deployment の credential は `AUTH_INVALID` (そもそも base URL が別) |
| (ii) | 1 base URL のまま、前段 router が credential から application を引き、専用単位へ振り分ける。router は bucket 資格情報を持たない。各単位は bearer を自分の 1 application に再認証するので、誤配は `AUTH_INVALID` で閉じる | 監督の見立て 2026-10-02: 契約は変えなくてよい (surfaces は 1 つのまま) | Cloud Run で service が複数 = 複数 host なら `deployment_required` へ後退 (Cloud Run の挙動は未確認)。1 host 内の process 分割なら `enforced` のまま。【v0.5 2026-10-02 設計レビュー 2 反映 Q-8】object-capable な配備 (router・JSON process・専用単位が別 composition root) では `deployment_required` と宣言する (上の「1 host 内の process 分割なら `enforced` のまま」を改める。旧文は残す。§6.1 の Q-8、§11 の Q-8) | 監督の見立て: application 単位の枠はその application の単位 (1 host) に閉じるので `enforced`。【v0.3 2026-10-02 再確認反映 RC-15】application の単位が 1 instance (Cloud Run なら最大 instance 1。自動スケールの挙動は未確認) のとき | router は全 application の認証状態と全 bytes を扱う multi-application 部品であり、SI-00 の対象 | `NOT_FOUND` は `AUTH_INVALID` に変わり得る。【v0.3 2026-10-02 再確認反映 RC-4】誤配の結果は `AUTH_INVALID` |
| (iii) | object endpoint を application 専用の path prefix、または新 surface (`surfaces.objects`) に置く | url_composition、`conformance-tests/CONDITIONS.md` C-19 と C-35 | 監督の見立て 2026-10-02: (ii) と同じ (prefix で振り分ける前段が要る) | 監督の見立て: (ii) と同じ | 監督の見立て: 前段は path だけ見るので認証状態を持たないが、application の識別子が URL に出る (非開示の衛生に反する) | 監督の見立て: 他 application の prefix へ送った credential は `AUTH_INVALID` |

### Q-3 転送時間の bound

- 決定: B-5 (4 class)、§2「ストリーム読み書き時間を宣言・強制」。
- 現状: 時間を表す limit class は `execution_ms` だけで、計測開始と待ちの扱いは台帳 `RM` R-42 で未決 (§10 の S-14)。
- 食い違い: §2 の時間の要求を、B-5 の 4 class のどれも表さない。
- 選択肢 (両論):
  - (甲) `execution_ms` を転送全体 (受付から available / 送信完了まで) に掛け、台帳 `RM` R-42 の裁定に従う。class を増やさない。1 byte/秒の upload は宣言時間で `LIMIT_EXCEEDED` になり、枠が解放される。
  - (乙) 転送の全体時間と最低速度 (idle) の class を足す (B-5 を超える)。
- 推奨 (監督の推奨): (甲)。宣言しない運用値の timeout は置かない (台帳 `RM` P-3 / P-5)。
- 【裁定 2026-10-02】依頼者「全て監督推奨で進めてください」→ (甲)。台帳 `RM` R-42 の裁定 (execution_ms の計測開始と待ちの扱い) に従う。帰結は §0 の B-5 の註、§2、§3.4、§4 (M-5)、§6 の 5、§6.1、§7.1 の O-25、§8。
- 【v0.5 2026-10-02 設計レビュー 2 反映 Q-6】上の (甲) の帰結のうち転送時間の bound は、§11 の Q-6 で `object_transfer_ms` に改めた (裁定行の本文は変えない)。

### Q-4 B-7 と両 peer の宣言値 0

- 決定: B-7「authorization propagation bound 以内の周期で再認可し、失効を観測したら転送を中断する」。
- 現状: 両 peer は `authorization_propagation_bound_ms: 0` を宣言する (`r2db-api/src/r2db_api/capabilities_document.py:188`、`MitateDB-api/src/mitatedb_api/capabilities_document.py:452`。schema の最小値は 0)。SI-13 は要求単位の「subsequent authorization」に掛かり、転送途中の再認可を求める文言は無い (`security/SECURITY_INVARIANTS_V1.md:338-351`)。
- 食い違い: 0 を文字どおり守るには chunk ごとの再認可が要る。v0.2 の設計内でも §4 の 4 (転送後 1 回) と §6 の 5 / B-7 (転送中) がずれていた (§4 の 4 は v0.3 の M-11 で「転送の間、周期 P で再認可 + 完了時にも 1 回」に揃えた)。
- 選択肢 (両論):
  - (a) object_storage を提供する deployment は正の bound を宣言し、その値を「失効の伝搬遅延 + 再認可周期 P」を含む値とする (宣言値の変更。台帳 `RM` §9 の 8 でクラス確認)。
  - (b) chunk ごとに再認可し、0 を保つ (認証 DB の負荷)。
  - (c) SI-13 を受付時と available 直前 (commit) に適用し、転送中は再認可しない (B-7 の本文と食い違うため推奨しない。記録のみ)。
- 推奨 (監督の推奨): (a)。どの案でも、再認可で `AUTH_STATE_UNAVAILABLE` なら中断する (fail closed)。download の中断は接続の異常終了で client に伝え、client は「受信長 = `Content-Length` かつ `Content-Digest` 一致」を成功条件とする (§3.3 の M-6 の反映と同じ)。
- 【裁定 2026-10-02】依頼者「全て監督推奨で進めてください」→ (a)。帰結は §0 の B-7 の註、§4 の 4、§6 の 5、§7.1 の O-13、§8。

### Q-5 総保存量・object 数の上限

- 決定: B-5 (rate のみ)。
- 現状: SI-08 (`security/SECURITY_INVARIANTS_V1.md`) は「object creation rate or count」を挙げ、rate (`object_requests_per_minute`) で文言は満たす。台帳 `RM` P-5 は安全上必要な bound だけを置く。provider の課金は application をまたぐ運用者の共通資源である。
- 食い違い: 決定との矛盾ではなく、B-5 の確定後に挙がった露出である。
- 選択肢 (両論):
  - (a) 初版は class を足さず、§8 の運用値に provider 側の quota / 予算 alert を置く。
  - (b) `object_count` / `object_total_bytes` の class を足す (B-5 を超える)。
- 推奨 (監督の推奨): (a)。
- 【裁定 2026-10-02】依頼者「全て監督推奨で進めてください」→ (a)。帰結は §0 の B-5 の註、§2、§8。

### Q-6 転送時間の bound と `execution_ms` の共有 (N-10)

- 決定: Q-3 の裁定 (甲) (`execution_ms` を転送全体に掛ける)。B-5 (4 class)。
- 現状: `execution_ms` は deployment に 1 つの宣言値であり、query / mutation / schema operation と共有する (`spec/data-service-api.v1.json:929-947`)。契約の例 (`execution_ms` 5000 ms。`spec/data-service-api.v1.json:955`) と §3 の例 (`object_bytes` 50 MiB) を組むと、10 MiB/s 未満の client の upload は必ず `LIMIT_EXCEEDED` になる。仮の起点「受付 = 認証成功時点」(§2、§6.1 の Q-3 の段落) は契約に「仮」と書けず、両 peer の現行の起点 (limit gate 通過時。`RM`:462) とも違う。
- 食い違い: Q-3 (甲) のままでは実用にならない。
- 選択肢 (両論):
  - (a) 共有を受け入れ、運用値 (§8) で `execution_ms` を上げる (JSON 経路の bound が緩む)。
  - (b) `execution_ms` を操作別に宣言する (契約の limits の形の変更)。
  - (c) 転送専用の class `object_transfer_ms` を 1 つ足す (B-5 の 4 class を超えるが加算的)。起点 = `object_transfers` 枠の獲得時点、終点 = available への遷移 / 送信完了。台帳 `RM` R-42 と独立。
- 推奨 (監督の推奨): (c)。agent が必要な最低速度 = `object_bytes` / `object_transfer_ms` を宣言から導けることを契約文に書く。§6.1 に行を足し、§3.4 の `execution_ms` の行を `object_transfer_ms` に改め (旧文は残す)、O-25 を `object_transfer_ms` に改める。実装側の socket timeout は `object_transfer_ms` 以下の運用値とする。
- 【裁定 2026-10-02】依頼者指示「全て監督推奨で進めてください」(2026-10-02) を本件にも及ぶものと読み (監督の読み)、推奨 (c) で進める。依頼者が覆すときは本行に【訂正】を足す。帰結は §0 の B-5 の註、§2、§3、§3.4 (失敗の表の末尾)、§4 (M-5)、§6 の 5、§6.1 (表と Q-6 の段落)、§7.1 の O-25、§8、§11 の Q-3 の裁定行の後。

### Q-7 router の SI-00 上の扱いと要件 (N-1)

- 決定: Q-2 の裁定 (ii)。A-1。
- 現状: router は TLS 終端として全 application の bearer を平文で受ける (既存の前段 nginx も同じ)。
- 食い違い: router の単一欠陥は他 application の bearer に届くので、A-1 の目的 (application-facing の単一欠陥で他 bucket に届かない) は router については成り立たない。§3.1 の Q-2 の段落の「R-30 の一方の答えを先取りしない」と「R-30 の裁定は (ii) と矛盾しない形で別途行う」は自己矛盾である。
- 選択肢 (両論):
  - (a) router を既存の前段 (reverse proxy) と同格の基盤部品と位置づけ、SI-00 (`security/SECURITY_INVARIANTS_V1.md`) の残余として `security/CONTROL_MAPPING.md` の SI-00 行に記録する。
  - (b) router の要件を列挙して条件にする。
- 推奨 (監督の推奨): (a)+(b)。要件: router は契約の応答を一切組まない (lookup に失敗した要求は deployment の JSON process へ回し、そこが `AUTH_INVALID` / `AUTH_REQUIRED` を返して監査する)、application logic・bucket 資格情報・DB 書き込み・本文の保存を持たない、保持する状態は「bearer の hash → application_id」の読み取り専用の射影だけ (secret を再構成できない)、本文は転送するだけ、専用単位は自分の 1 application で bearer を再認証する (誤配は `AUTH_INVALID`、O-26)。専用単位は serving set が 1 application でなければ起動しない (fail closed。test 専用の composition root だけが多 application を許す。RC-10 と同形)。capability document を返す process と専用単位の設定値は同じ出所から導き、起動時に一致を検査する (台帳 `RM` P-3)。台帳 `RM` R-30 との関係: 「矛盾しない形で」の文を撤回し、「R-30 は独立に裁定する。(ii) の router は application-facing 実装ではなく前段であり、R-30 のどちらの答えとも両立する。R-30 の裁定時に router の位置づけを確認する」に改める (旧文は残す)。R-30 行への追記は作業機の台帳更新で行う (次の一手)。
- 【裁定 2026-10-02】依頼者指示「全て監督推奨で進めてください」(2026-10-02) を本件にも及ぶものと読み (監督の読み)、推奨 (a)+(b) で進める。依頼者が覆すときは本行に【訂正】を足す。帰結は §3.1 (Q-7 の段落)、§6.1 (Q-7 の段落)、§9 の新 5、§11 の Q-2 (監督の読みの後)。

### Q-8 (ii) の `concurrency` の宣言 (N-2)

- 決定: Q-2 の裁定 (ii) と、v0.4 の帰結「1 host なら `enforced` のまま」(§6.1 の Q-2 の段落)。
- 現状: `MULTI_PROCESS_WORKER_V0_1.md` 裁定 27・28 (`MULTI_PROCESS_WORKER_V0_1.md:845-846`) の `enforced` の写像は「自 supervisor の workers ≥ process_ceilings.data」かつ「slot directory が自 user 所有 0700」である。
- 食い違い: router・JSON process・専用単位が別 composition root (A-1 なら別 OS user) で並ぶ (ii) では、そのままでは JSON 経路の `concurrency` も `deployment_required` に後退する。user を揃えると単位間の分離が弱まる (OS 側の塞ぎ方は未確認)。
- 選択肢 (両論):
  - (a) object-capable な配備では `concurrency` を `deployment_required` と宣言する (正直な宣言。`conformance-tests/CONDITIONS.md` C-32 の挙動は変わらない)。
  - (b) slot directory を composition root 間で共有する (裁定 28 を改める。Class D の別裁定)。
  - (c) object の 4 操作は `concurrency` を一切消費せず (metadata / delete も object 側の admission に乗せる)、`concurrency` の意味を「JSON 経路の in-flight」と契約に書く (契約の limits の記述の変更)。
- 推奨 (監督の推奨): (a)。v0.4 の帰結の文を改め (旧文は残す)、§11.1 の (ii) 行と §6.1 を直す。
- 【裁定 2026-10-02】依頼者指示「全て監督推奨で進めてください」(2026-10-02) を本件にも及ぶものと読み (監督の読み)、推奨 (a) で進める。依頼者が覆すときは本行に【訂正】を足す。帰結は §6.1 (Q-8 の段落)、§11.1 の (ii) 行。

### Q-9 X-Request-Id の意味 (N-6 の一部)

- 決定: B-3。§3.2 の M-14「`X-Request-Id` は、body に `request_id` がある応答では同じ値」。
- 現状: 両 peer の `x-request-id` は「その要求自身の request_id = その要求の監査行の値」であり、JSON の replay では header (新) と body (元) が異なる (`r2db-api/src/r2db_api/http.py:279`)。
- 食い違い: M-14 を全体に掛けると既存 JSON の replay が非適合になり、upload だけに掛けると replay 要求自身の監査行と header の相関が切れる。
- 選択肢 (両論):
  - (a) header は常にその要求自身の request_id とする (replay の元の値は body の request_id だけ。既存挙動のまま)。
  - (b) header = body とする。
- 推奨 (監督の推奨): (a)。M-14 と §3.2.1 を改め (旧文は残す)、B-3 の契約化の範囲は「object_storage の 4 操作の全応答 (成功・失敗) が `X-Request-Id` にその要求自身の request_id を運ぶ」(object_storage 条件付きの義務。既存操作は変えない) とする。
- 【裁定 2026-10-02】依頼者指示「全て監督推奨で進めてください」(2026-10-02) を本件にも及ぶものと読み (監督の読み)、推奨 (a) で進める。依頼者が覆すときは本行に【訂正】を足す。帰結は §0 の B-3 の註、§2.1 (RC-13 の後)、§3.2、§3.2.1、§7.1 の O-7・O-10。

## 12. 設計レビュー 1 の反映の一覧 (2026-10-02)

設計レビュー 1 回目は観点 A と観点 B の並列 2 起動で行い、監督が重なりを 1 件にまとめて M-n とした。「出所」の列は観点 A の指摘番号 (A の 1〜14) と観点 B の指摘番号 (F1〜F18) である (依頼者決定の A-1 等とは別の番号)。

| M-n | 出所 | 裁定 | 反映した節 |
| --- | --- | --- | --- |
| M-1 | A の 1、F1、§10 の S-2 | 依頼者裁定待ち | §11 の Q-1 (§2・§3.3 の註から参照) |
| M-2 | A の 2、F3、§10 の S-13 | 依頼者裁定待ち | §11 の Q-2、§11.1 (冒頭の A-1 の註から参照) |
| M-3 | A の 3、F13、§10.1 | 一部反映 / 一部裁定待ち | §6 の 3、§6.1 (反映)。§11 の Q-3 (裁定待ち) |
| M-4 | A の 4 | 反映 | §4、§7.1 の O-18 |
| M-5 | A の 5、F15 の一部 | 反映 | §4、§5.1、§5.2、§7.1 の O-19 |
| M-6 | A の 6、F4 の後半 | 反映 | §3.2 の表 (`Expect` 行)、§3.2.4、§3.3、§3.4、§7.1 の O-14・O-15 |
| M-7 | A の 7、F12、§10.1 | 反映 | §3.2.1、§4 |
| M-8 | A の 8、F5 の filename | 反映 | §3.2.2、§3.4、§7.1 の O-2 |
| M-9 | A の 9、F2、F11 | 反映 | §3.1、§3.3、§3.4、§7.1 の O-8 |
| M-10 | A の 10、F10、F15 | 反映 | §3.2 の表 (`Content-Encoding` 行)、§3.3、§5 冒頭の表、§5.1、§5.2、§6 の 6 |
| M-11 | A の 11、F4 | 一部反映 / 一部裁定待ち | §4 の 4、§6 の 5、§7.1 の O-13 (反映)。§11 の Q-4 (裁定待ち) |
| M-12 | A の 12、F8 | 反映 | §7 の 4、§7.1 の O-4a・O-4b |
| M-13 | A の 13、F13 | 依頼者裁定待ち | §11 の Q-5 |
| M-14 | A の 14、F6、F7 | 反映 | §3 (操作名)、§3.1、§3.2 (request_id)、§3.3、§3.4、§7.1 の O-12・O-20 |
| M-15 | F5 | 反映 | §3.4 |
| M-16 | F9、§10 の S-1 | 反映 | §5 末尾、§7.1 |
| M-17、M-18 | (欠番) | — | 監督の突合で M-17 (F10 の前段の上限) は M-10 に、M-18 (F11 の dry_run / budget) は M-9 に統合した。番号は欠番のまま残す (2026-10-02) |
| M-19 | F14 | 反映 | §3.2.3、§3.3、§3.4、§7.1 の O-3・O-22 |
| M-20 | F16 | 反映 | §9 |
| M-21 | F17 | 反映 | §2.1 |
| M-22 | F18 | 反映 | 冒頭の「版数・位置づけ」、§0 の表の後の A-2 の註、§2 の註、§7 冒頭の註 |
| S-1〜S-16 | 監督の突き合わせ | 反映 | §10、§0 の表の後の註 (A-2・B-1・B-2・B-3・B-5・B-12)、§1 (S-16)、§3 (S-9・S-10)、§3.2 と §4 (S-11) |

### 再確認の反映 (RC-1〜RC-21) (番号なし。§12.1 の番号を保つ)

再確認は指定なし 1 起動で行い、指摘 21 件を監督が裁定した (2026-10-02)。全件「直した」であり、v0.3 の中で反映した (版は v0.3 のまま。冒頭の版数表の v0.3 行を改めた)。反映箇所の印は【v0.3 2026-10-02 再確認反映 RC-n】。

| RC-n | 反映した節 |
| --- | --- |
| RC-1 | §3.3、§7.1 の O-8 |
| RC-2 | §2.1、§4、§7.1 の O-19b |
| RC-3 | §3.3、§4 |
| RC-4 | §7.1 の O-5、§11.1 (最終列の見出しと (ii) 行) |
| RC-5 | §3.2.2 |
| RC-6 | §6 の 3、§6.1 |
| RC-7 | §4 |
| RC-8 | §3.4 (冒頭の検査順の表、失敗の表の末尾 4 行) |
| RC-9 | §3 (S-10 の註)、§3.3、§3.4、§7.1 の O-8 |
| RC-10 | §7.1 |
| RC-11 | §4 (RC-3 の文から参照)、§7.1 の O-20 |
| RC-12 | §2.1、§3 (S-10 の註) |
| RC-13 | §2.1 (obligations 案の直前) |
| RC-14 | §11 の Q-0 |
| RC-15 | §11.1 |
| RC-16 | §4 の 4 |
| RC-17 | §7.1 の O-4a |
| RC-18 | §7.1 (O-11 と表の後の註) |
| RC-19 | §11 の Q-1 |
| RC-20 | §3.4 |
| RC-21 | §7.1 の O-18 |

### v0.4 の帰結の一覧 (番号なし。§12.1 の番号を保つ)

依頼者裁定 (2026-10-02。逐語は §11 の冒頭) の帰結を v0.4 で反映した。反映箇所の印は【v0.4 2026-10-02 依頼者裁定の帰結 Q-n】。上の M-n の表で「依頼者裁定待ち」「一部裁定待ち」とした M-1・M-2・M-3・M-11・M-13 は、この裁定で解けた (表の行は残す)。

| Q-n | 採った案 | 反映した節 |
| --- | --- | --- |
| Q-0 | (a) (監督の読み) | 冒頭の版数表 (v0.4 行) と v0.4 の印の行、§1、§11 の Q-0 |
| Q-1 | (甲) + (乙) | §2、§2.1、§3.2、§3.3、§3.4 (表の末尾から 2 行目)、§7.1 の O-24、§11 の Q-1 |
| Q-2 | (ii) (R-30 の部分は監督の読み) | 冒頭の A-1 の註、§3.1、§6.1、§9 (旧 1 と新 4)、§11 の Q-2。【v0.5 2026-10-02 設計レビュー 2 反映 N-21】§7.1 の O-26 |
| Q-3 | (甲) | §0 の B-5 の註、§2、§2.1、§3.4 (表の末尾)、§4 (M-5)、§6 の 5、§6.1、§7.1 の O-25、§8、§11 の Q-3 |
| Q-4 | (a) | §0 の B-7 の註、§4 の 4、§6 の 5、§7.1 の O-13、§8、§11 の Q-4 |
| Q-5 | (a) | §0 の B-5 の註、§2、§8、§11 の Q-5 |

### 設計レビュー 2 の反映の一覧 (番号なし。§12.1 の番号を保つ)

設計レビュー 2 回目は観点 A と観点 B の並列 2 起動で行い (2026-10-02)、監督が重なりを N-n にまとめた。「出所」の列は観点 A の指摘番号 (A2-1〜A2-20) と観点 B の指摘番号 (B2-1〜B2-14) である (依頼者決定の A-1 等、設計レビュー 1 の出所とは別の番号)。N-1・N-2・N-10 と N-6 の一部 (A2-10) は依頼者裁定級として §11 の Q-7・Q-8・Q-6・Q-9 に置き、依頼者指示 (§11 の冒頭の逐語) を本件にも及ぶものと読んで (監督の読み) 推奨で進めた。反映箇所の印は【v0.5 2026-10-02 設計レビュー 2 反映 N-n】と【v0.5 2026-10-02 設計レビュー 2 反映 Q-n】。再確認は次の一手である。

| N-n | 出所 (A2-n、B2-n) | 反映した節 |
| --- | --- | --- |
| Q-6 (N-10) | A2-12、B2-1 | §11 の Q-6、§0 の B-5 の註、§2、§3、§3.4 (失敗の表の末尾)、§4 (M-5)、§6 の 5、§6.1 (表と Q-6 の段落)、§7.1 の O-25、§8、§11 の Q-3 の裁定行の後 |
| Q-7 (N-1) | A2-1、A2-3、B2-9 | §11 の Q-7、§3.1 (Q-7 の段落)、§6.1 (Q-7 の段落)、§9 の新 5、§11 の Q-2 (監督の読みの後) |
| Q-8 (N-2) | A2-2 | §11 の Q-8、§6.1 (Q-8 の段落)、§11.1 の (ii) 行 |
| Q-9 (N-6 の一部) | A2-10 | §11 の Q-9、§0 の B-3 の註、§2.1 (RC-13 の後)、§3.2、§3.2.1、§7.1 の O-7・O-10 |
| N-3 | A2-4、B2-6、A2-5、B2-2 の header 部分 | §3 (RC-9 の註の後)、§3.1 (`{object_id}` の註の後)、§3.3 (Q-1 の段落の後)、§7.1 の O-24 |
| N-4 | B2-2 | §3 (RC-9 の註の後) |
| N-5 | B2-3、A2-15、B2-4 | §3.1、§3.4 (field 定義の註、`object_id` の行、再認可の行)、§7.1 の O-23 |
| N-6 | B2-5 | §3.2.1、§3.4 (新語の定義、`Idempotency-Key` の行) |
| N-7 | A2-6、A2-7、A2-8、B2-8 の一部 | §3.3 (M-14 の後)、§3.4 (段 (1)、`Content-Length` の 2 行)、§6 の 2・6、§7.1 の O-12・O-16・O-23 |
| N-8 | A2-9、B2-13 | §3.2.1、§4 (M-7 の後) |
| N-9 | A2-11 | §3.2.2、§7.1 の O-2 |
| N-11 | A2-13、B2-8 | §7.1 の O-13、O-27 |
| N-12 | A2-14、B2-7 | §7.1 の O-24 |
| N-13 | A2-16 | §3.4 (検査順の表の後) |
| N-14 | A2-17 | §3.3 (M-10 の後)、§7.1 の O-10 |
| N-15 | A2-18、B2-12 | §2 (Q-5 の段落の後)、§8、§9 の新 5 |
| N-16 | A2-19 | §7.1 の O-6 |
| N-17 | A2-20、B2-10 | §2.1 |
| N-18 | B2-8 | §3.4 (検査順の表の後)、§7.1 の O-28 と表の後 |
| N-19 | B2-9、A2-1 の残り | §3.1 (Q-7 の段落の後)、§3.4 (実行主体の表)、§6.1、§7.1 の前置き |
| N-20 | B2-11 | §6 の 5 |
| N-21 | B2-14 | §11 の Q-2 (裁定行の後)、§12 の「v0.4 の帰結の一覧」の Q-2 行 |
| RC-18 の見立て | A / B 共通 (監督 2026-10-02) | §7.1 (O-11 の註の後) |

### 12.1 観察 (台帳には載せない)

- v0.1 の推薦案と退けた選択肢は repository に無い。v0.3 では復元せず、記録のみとする。
- provider / platform / RFC の挙動は全て未確認である: R2 の token の粒度、R2 の条件付き PUT、multipart / resumable の abort、Cloud Run の本文上限、RFC 9530 の未対応 algorithm、IETF Idempotency-Key 草案の値の書式。v0.3 の起草環境から provider の公式文書に到達できなかった。網に出られる作業機での確認を次の一手に置く。
- 【v0.5 2026-10-02 設計レビュー 2 の観察】uvicorn / starlette の挙動 (最初の receive での 100 Continue の送出、`Content-Length` の不正値への契約外の 400) は本環境のインストール済みソースを読んで確かめた (本環境のソースで確認、実行は未確認)。nginx・provider・RFC の挙動は未確認のままである。
