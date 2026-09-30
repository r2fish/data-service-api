# 参照クライアント設計 (台帳 `RM` R-108)

## 0. 版数・位置づけ

| 版 | 日付 | 状態 |
|---|---|---|
| v0.1 | 2026-09-30 | 設計レビュー前・依頼者裁定待ち (Q-1〜Q-3) |
| v0.2 | 2026-09-30 | 設計レビュー 1 反映済み・依頼者裁定待ち (Q-1〜Q-3)。反映の一覧は §12 |
| v0.3 | 2026-09-30 | 設計レビュー 1 と再確認を反映済み・依頼者裁定待ち (Q-1〜Q-4)。反映の一覧は §13 |

- 対象: 計画文書 `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の R-108 (`RM`:464)。規模 L。
- 基点: main c729ab0 (契約 1.12.0)。並走: 台帳 `RM` R-115 が契約版・条件番号・port 版・launcher を持つ (未 merge)。本書の契約版・条件番号・port 版はすべて (仮) であり、merge 直前に main を読んで振る (フェーズ11 設計 `docs/design/PHASE11_MIN_COMMON_PROFILE_V1.md` D-7 と同じ規律)。
- 枠 (問題設定・条件・決定・却下案・判断待ち) は監督が 2026-09-30 に確定した。本書はそれを変えない。
- 記号: 守るべき条件を K-1〜K-6、契約から読めない点を N-1〜N-19 と呼ぶ。接頭辞は `security/THREAT_MODEL_V1.md` の T 族、台帳 `RM` の P 族・G 族、`tools/check_doc_refs.py` の族のどれとも衝突しない。

## 1. 問題設定

- 目標は `spec/README.md`:5-9 の逐語である。「The target is that an AI agent can use either implementation from: 1. this API specification, 2. a base URL, and 3. an authorized API key.」
- これを実行で示すものは現状無い。C-28 は port と peer ごとの adapter を経由し、adapter は path を文字列で直書きして catalog を読まない。C-29 は配る catalog の byte 一致までである。フェーズ11 設計 §11 (`docs/design/PHASE11_MIN_COMMON_PROFILE_V1.md`:897-907) は「実行可能な形で証明してはいない」と明記している。
- 依頼者裁定 (2026-09-24、フェーズ11 設計 U-3。`docs/design/PHASE11_MIN_COMMON_PROFILE_V1.md`:514。逐語、再審議しない):「U-3: 「(a) 最小形 + (c) を別起票」 — 本項目は両 peer が operation_catalog_url を宣言し byte 一致で配る (C-29) まで。参照クライアント (spec + base URL + key だけから要求を組み立てる共通コードで C-28 を wire plug に回す) は次の項目として起票。」

## 2. 守るべき条件

- K-1 参照クライアントは入力 3 つだけで要求を組む。peer のコード・adapter・port の補助を import しない。path・method・schema 名・header の形をコード中に直書きしない (catalog と契約 JSON から引く)。これを静的検査 (AST) で固定する。
- K-2 両 peer に対して同一のコード・同一の作業列で走り、peer 名で分岐しない。
- K-3 派生物を増やさない。入力は既存の `spec/data-service-api.v1.json` と `spec/OPERATION_CATALOG.json` である。
- K-4 契約に無い知識が要ると分かった箇所は、クライアント側の暗黙知で埋めず、(a) 契約の既存の文から読めることを示すか、(b) 契約の欠落として列挙する (§4)。「緑だから文書は十分」とは書かない。作業列が通る範囲 (common_baseline の 1 周) の証明であることを §11 に書く。
- K-5 Security Invariants: 新しい能力を足さない。検査側の層であり、secret をログ・失敗メッセージに出さない。該当 SI を §7 で列挙する。
- K-6 既存の C-28 / C-29 と adapter の既存 method は書き換えない。port と adapter に method を 1 つ足す。

## 3. 決定と根拠

D-1 置き場と形。`conformance-tests/reference_client.py` (テストでない共通モジュール 1 本) と、新条件 (仮) のテスト 1 本を置く。クライアントの入力は、契約 JSON と catalog (`spec/` から読んだ dict)、base URL、bearer secret、送信関数 (transport) である。根拠: 証明は完了ゲートが走る conformance に置く (§8)。conformance の既存の import 規約 (テストモジュールが `schema_check` 等を bare import する) にそのまま乗る。

D-2 要求の組み立て。operation 名から catalog の method / path / request_schema / roles を引く。path の placeholder は呼び出し側が値を渡し、クライアントは値によらず常に percent-encode する (`/` を含む予約文字をすべて。N-11)。認証 header は契約 `security.schemes` から組む (N-6)。Content-Type、成功と失敗の判別、problem+json でない応答の扱いは §4.1 の表の行による (N-8・N-13・N-14)。body は呼び出し側 (作業列) が意図として与え、送信前に契約の request schema で `conformance-tests/schema_check.py` により検証する (クライアントが契約外の body を送れない)。応答は response schema で検証し、失敗は problem+json の `code` で判断する。HTTP status では分岐しない (`spec/data-service-api.v1.json`:872)。参照クライアントは `operation_catalog_url` を取りに行かない。catalog は入力 1 の `spec/OPERATION_CATALOG.json` から読む (N-18)。宛先は最初の要求 (capabilities) を含め §4.1 の N-19・N-1 の行で決める。入力の base URL が `versioning.base_path` で終わらないとき、operation の surface が段 (1) の capability document に宣言されていないとき (`surfaces.control` の欠落) は、送信せず例外にする (fail closed)。https でない base URL には bearer を送らない (例外は §4.1 の N-15 の行)。

D-2a 結合の検証と送信関数。(1) 参照クライアントの単体テスト (記録用の偽の送信関数) で、接頭辞付き base URL・control 面・`/v1` 二重・`operation_catalog_url`・alias の結合を固定する (D-7 の 3・14・19)。(2) wire への入口が返す base URL は、その plug の capability document の `surfaces.data.base_url` と一致することを段 (1) で assert する。(3) 送信関数は渡された URL・header・body を変えない「運ぶだけ」のものとする。r2db socket の既存 client の `send` は要求 URL の scheme/host/port を宣言面の値で上書きする (`r2db-api/conformance/conformance_adapter_r2db_socket.py`:458-460)。これは避けられるので避ける: 宣言 URL の port は面の生成時に予約済みで (同:208-210)、面の `base_url` を読むと面が起動する (同:233-236)。入口は返す前にそれを読み、宣言 URL をそのまま dial する素の transport を渡す。MitateDB socket は既に URL を書き換えずに dial する (`MitateDB-api/conformance/conformance_adapter_mitatedb_socket.py`:319-329)。既存の `send` は変えない (K-6)。

D-3 作業列。C-28 の 12 段と同じ 1 周を、port ではなく参照クライアントで実行する新しい条件 (仮番号) とする。C-28 本体は触らない。段ごとに「契約のどの節から組んだか」を §5 の表に持つ。

D-4 対象 plug。依頼者裁定どおり wire plug 4 つ (http ×2 = ASGI、socket ×2 = 実 socket + nginx) とする。そのために port に「wire への入口」を 1 つ足し、port 版を上げる (§6)。in-process plug 2 つは wire が無いので対象外と明記する。対象の選別は module 読み込み時の registry 読み (`transport_kind`) で wire adapter 名の列を作り、それで直接 parametrize する。skip も early return も使わない。同じ module 読み込み時に数が 4 であることを assert する (`docs/work-orders/OPERATING_CONDITIONS.md` §1.5 の 32、§1.3 の 22・26)。xdist の group 付けは未実測であり §10 で実測する。

D-4a key の本数。参照クライアントの 1 インスタンスは key を 1 本だけ持つ (目標文の「an authorized API key」)。作業列は 2 インスタンスを使う: schema 操作は developer の key、それ以外は runtime の key。どちらの key で呼べるかは catalog の roles から選ぶ (N-7。どの secret がどの role かは N-16)。根拠: application を使う agent が普段持つのは runtime の key であり、developer 1 本で全段を通すと runtime の経路が証明から落ちる。

D-5 帯域外に残すもの。application の登録と key の発行 (bootstrap) は adapter の既存経路のままとする。目標文の入力 3 は「認可済みの key」であり、発行は目標の外だからである。control 面 (`control.*`) は本項目の作業列に入れない。

D-6 直書き禁止の検査 (AST)。
- クライアント module: import は標準ライブラリと `schema_check` だけ。catalog の operation 名・path・method・schema 名と一致する文字列リテラルを持たない (禁止集合は catalog と契約から導出して照合する)。散文からしか得られない語は下の「散文由来リテラルの表」に契約の file:line 付きで列挙し、表に無いリテラルは赤にする。§4.1 の表も同じ module に持ち、pin する (照合先は D-7 の 15)。許可集合の厳密な形 (契約 JSON の key 名の扱い、例外メッセージの文字列) は作業指示書で確定する。
- テスト module: import の制限は掛けない。代わりに、wire への要求は参照クライアントの公開 API 経由だけで送り、送信関数を直接呼ばないこと、port から使うのは provisioning と wire への入口だけであること、作業列に adapter 名・`transport_kind`・host による分岐が無いこと (対象の選別は D-4 の module 読み込み時の 1 か所) を pin する。
- 送信関数は peer 側のコードで pin の外にある。D-2a の「運ぶだけ」は、送った要求を記録して参照クライアントが組んだ要求と一致することで確かめられる plug では確かめ、確かめられない plug は §11 に書く。

| 散文由来リテラル | 出所 |
|---|---|
| `Authorization` | `spec/data-service-api.v1.json`:13 (`security.schemes.application_credential.description` の「Authorization: Bearer <secret>」) |

D-7 単体テストと変異 (空振り防止の見込み。確定は作業指示書)。記録用の偽の送信関数で参照クライアントを駆動する単体テストを置き、完了条件と変異を 1 対 1 で持つ。変異の注入先は `spec/` のファイルではなくクライアントのコードとテストとする (`spec/` に入れると再生成一致テストと C-29 も同時に赤になり、`docs/work-orders/OPERATING_CONDITIONS.md` §1.5 の 33 を満たさない)。wire 上の作業列の変異 (§5) は C-28 と同時に赤になってよく、この条件単独で赤になる必要があるのは単体テスト側である。

| # | 単体テストが固定すること | 変異 |
|---|---|---|
| 1 | schema 違反の body (必須キー欠落・未知キー・上限超過) は例外になり、送信 0 回 | 送信前検証の呼び出しを外す |
| 2 | 偽の送信関数が schema 違反の成功応答を返すと例外 | 応答検証を外す |
| 3 | 結合 (D-2a): 接頭辞付き base URL (`https://db.example.invalid/tenant-a/v1` と対の control URL) で接頭辞が残る、control 面は control の base path だけを除く、`/v1` が二重にならない (`operation_catalog_url` は 14) | 接頭辞を落とす / origin に path を足す / 単純連結 / control の base URL から `/v1` だけを除く |
| 4 | placeholder の値に `/` を含めると encode されて送信記録に出る (D-2) | encode を外す |
| 5 | 送信記録の header が scheme (構造化値) と散文由来の header 名から組まれている | scheme を別の語 (例 `Token`) に変える。大小文字だけの変異は使わない: r2db の境界は scheme を大小文字を区別せず比べる (`r2db-api/src/r2db_api/http.py`:400) ので、同じ変異が wire 側では生き残り、単体と wire で判定が割れる |
| 6 | 契約版の照合 (D-10): 偽の送信関数の capability document が別の `contract_version` を宣言すると段 (1) で例外 | 照合を外す |
| 7 | secret の非露出 (D-9): sentinel secret で失敗させた例外の文字列と repr に sentinel が出ない | 失敗メッセージに `Authorization` の値を入れる |
| 8 | `schema_check` の新 keyword (D-7a): keyword ごとに正例と負例を 1 組 (`conformance-tests/test_schema_check.py`) | その keyword の判定を外す |
| 9 | D-6 の AST pin | クライアントに catalog の path を直書きする / 表に無い散文由来リテラルを足す / テストから送信関数を直接呼ぶ |
| 10 | 失敗応答の Content-Type に `; charset=utf-8` が付いても失敗として扱う (N-13) | parameter を除かずに比べる |
| 11 | problem+json でも JSON でもない応答 (HTML の 404) は例外になる (N-14) | その応答を成功として扱う |
| 12 | 11 の例外の文字列と repr に応答の本文と header が出ない (N-14) | 例外に本文を入れる |
| 13 | problem+json を status 200 で返されても失敗として扱う (D-2) | status が 2xx なら成功とみなす |
| 14 | 合成の `operation_catalog_url` を宣言させても、送信記録にその URL が出ない (D-2) | 段 (1) の後に `operation_catalog_url` を取りに行く |
| 15 | §4.1 の表の pin: クライアント module の表の key 集合が、テスト module に持つ本書 §4.1 の N 番号の列と一致する (本書の改訂と同じ変更セットで直す) | module の表から行を 1 つ消す |
| 16 | https でなく N-15 の行の例外にも当たらない base URL では送信 0 回で例外 (D-2) | scheme の検査を外す |
| 17 | `versioning.base_path` で終わらない入力 base URL (origin だけ等) では送信 0 回で例外 (D-2) | 末尾の検査を外し、base path の文字数だけ除く |
| 18 | `surfaces.control` を宣言しない capability document の後に control 面の operation を呼ぶと送信 0 回で例外 (D-2) | data の base URL に結合する |
| 19 | surface の判定 (N-19): alias の `audit_query` の項は接頭辞付きの control base URL に結合される | surface を path の接頭辞で決める |

D-7a `schema_check.py` の拡張。現行の `schema_check.py` は、作業列が使う request schema の keyword の一部 (MutationRequest の `maxLength`・`maxProperties`、SchemaOperationRequest の `maxLength`) を実装しておらず、未知の keyword には例外を出す (fail-closed)。作業列が使う request / response schema の keyword をすべて実装する。未知の keyword で例外を出す性質は変えない。同じ変更セットで module docstring (`conformance-tests/schema_check.py`:1-38 の「C-11 の 3 schema が使う keyword の部分集合」) を直す。クライアントが検証する schema の `used_keywords()` が実装済み集合に収まることを、`conformance-tests/test_schema_check.py`:226-245 と同じ形のガードで静的に固定する (例外は instance が通った節点でしか出ないため)。C-11 の判定が変わらないことは §10 で実測する。

D-8 クラスと規模。Class D。`security/CONTROL_MAPPING.md` に触れ、wire への入口を両 peer に同名で置くので `_ISOMORPHIC_TARGETS` が増える (台帳 `RM` §9 の 8 の D 行、`RM`:581)。設計レビューは 2 回で、v0.2 が 1 回目の反映、v0.3 がその再確認の反映である。2 回目は依頼者裁定 (Q-1〜Q-4) を反映した版に対して行う。規模 L。実装の着手は台帳 `RM` R-115 の merge 後とする (契約版・条件番号・port 版・launcher が重なるため)。

D-9 secret。クライアントの例外・失敗メッセージとテストの assert に secret も `CredentialHandle` も入れない。sentinel secret が失敗メッセージに出ないことを単体テストと変異で固定する (D-7 の 7)。

D-10 契約版の照合。段 (1) で、`spec/data-service-api.v1.json` の `contract_version`、catalog の `contract_version`、peer が capability document で宣言する `contract_version` の 3 つが一致することを見る (D-7 の 6)。

## 4. 契約から読めない点の表

判定は main c729ab0 の現物による。「形」は、読める場合に構造化された値から読めるか散文からしか読めないかを示す。

| # | 点 | 判定 | 形 | 契約の該当箇所と理由 |
|---|---|---|---|---|
| N-1 | base URL と path の結合 | 読めない | — | `surfaces.data.base_url` は `versioning.base_path` で終わり、「appending a path to it yields exactly one separator」とだけ言う (`spec/data-service-api.v1.json`:1385、base_path は :31)。一方 catalog と endpoints の path は `/v1/…` で始まる (`spec/OPERATION_CATALOG.json`:24・:283、`spec/data-service-api.v1.json`:350)。単純に連結すると `/v1` が二重になる。どの path をどこに結合するかの規則が無い。入力「a base URL」が origin か `surfaces.data.base_url` かも `spec/README.md`:5-9 は定めない。surfaces は「client が使った URL から推測しない」(:1385) ので、最初の要求の宛先も同じ問いに帰着する。一方、両 peer は接頭辞を保つ結合を既に実装している: `derive_operation_catalog_url` は base_url から末尾の base_path を除いて path を足す (`r2db-api/src/r2db_api/operation_catalog.py`:39-70、`MitateDB-api/src/mitatedb_api/operation_catalog.py`:39-70)。surfaces の検証は末尾だけを見て接頭辞を許し、`/control/v1` の誤結合を別に防ぐ (`r2db-api/src/r2db_api/platform_declarations.py`:341-352、`MitateDB-api/src/mitatedb_api/platform_declarations.py`:369-380)。runbook も接頭辞付き配備を書く (`r2db-api/deploy/DEPLOYMENT_RUNBOOK.md`:633、`MitateDB-api/docs/cloud-run-cloud-sql.md`:1239-1245)。conformance の C-19・C-26 も base_url に path を足す (`conformance-tests/test_c19_client_self_sufficiency.py`:438・:476、`conformance-tests/test_c26_composition_root.py`:165-170)。つまり契約に無い規則を peer が暗黙に持っている。ただし結合先は path の接頭辞では決まらない: `endpoints.audit_query` の path は `/v1/audit/query` だが、deprecation_note は control surface の host に置く alias と定める (`spec/data-service-api.v1.json`:427・:432)。両 peer もこの path を control app に置き (`r2db-api/src/r2db_api/control_http.py`:462-463、`MitateDB-api/src/mitatedb_api/control_http.py`:509-510)、data app の同じ path は application 認証の後に拒否するだけの stub である (`r2db-api/src/r2db_api/http.py`:718-745・:766、`MitateDB-api/src/mitatedb_api/http.py`:1263-1294)。結合先は operation の属する surface で決まる (N-19) |
| N-2 | path の placeholder (`{entity}`) に入れる値 | 読めない | — | catalog は placeholder を持つが (`spec/OPERATION_CATALOG.json`:253・:283)、何を入れるかの定義文が無い。endpoints の semantics「Entity and fields are validated identifiers」(`spec/data-service-api.v1.json`:354) と「The body carries no entity field」(:370) から entity 名と推し量れるだけである。control 面の `{application_id}` 等は D-5 により作業列の外 |
| N-3 | HTTP status | 読める | 構造化 + 散文 | 409 (`DESTRUCTIVE_CONFIRMATION_REQUIRED`) 以外は未定義と明記 (`spec/data-service-api.v1.json`:665・:872)。失敗は `errors.content_type` の problem+json (:844) と `code` (:852-870) で判断できる。成功側の status も定めていないので、クライアントは status で分岐しない (D-2) |
| N-4 | 作業列の意味 (dry_run → plan 提示 → idempotency 再送、declare-and-echo、`details.field` による修正) | 読める | 散文のみ | dry_run (:824-826)、idempotency (:829-830)、declare-and-echo (:682・:695、対象は :698 の構造化列)、`details.field` の '/' path (:886)、床の列挙 (:309-320)。機械可読な手順は無い。作業列は人が散文を読んで書く (§11) |
| N-5 | request body の中身 | 読める | 構造化 | catalog は request_schema を名前だけ持ち (`spec/OPERATION_CATALOG.json`:283 の項)、本体は契約 `schemas` にある (`spec/data-service-api.v1.json`:991 QueryRequest、:1045 MutationRequest、:1149 SchemaOperationRequest)。insert / update / delete は `mutate` 1 operation の `Mutation.operation` の値である (:742-747、:1827) |
| N-6 | 認証 header の形 | 読める | 構造化 (scheme) + 散文 (header 名) | scheme は `type: http` / `scheme: Bearer` の構造化値 (`spec/data-service-api.v1.json`:11-12)。header 名 `Authorization` は description の散文「Authorization: Bearer <secret>」(:13) にしか無い。header 名は D-6 の散文由来リテラルの表に載る |
| N-7 | どの role の key で呼ぶか | 読める | 構造化 | catalog の roles (`spec/OPERATION_CATALOG.json` 各項) と `endpoint_fields_note.roles` (`spec/data-service-api.v1.json`:627)。schema は developer のみ (:410 の endpoints.schema)。baseline の data 面 operation はすべて developer を受ける。自分の key の role は N-16 |
| N-8 | 要求の Content-Type | 読めない | — | 最上位 `media_type: application/json` (`spec/data-service-api.v1.json`:7) は値だけで、要求・成功応答のどちらに掛かるかを述べる文が無い。失敗応答の型だけは :844 が定める |
| N-9 | capability による分岐の要否 | 読める | 散文 | `common_baseline.purpose` と `rule` (`spec/data-service-api.v1.json`:308・:331)。床の operation は宣言を読まずに呼べる |
| N-10 | baseline の query 演算子集合 | 読める | 散文 | 含む側は :314 の散文、全集合は配列 (:725-736)、除く側は `outside` の散文 (:332)。配列として取り出せる形では無い (C-28 も除外 3 名をリテラルで持つ。`conformance-tests/test_c28_baseline_turn.py`:63-76) |
| N-11 | placeholder の値の percent-encode | 読めない (v0.3、2026-09-30 に「読める」から変更。encode の根拠は外部標準 (URI) であり、読めない N-17 に従うため。再確認の指摘 6) | — (v0.2 は「外部標準 (URI。N-17 に依存)」) | 契約は encode を述べない。identifier は ASCII 英数字と underscore (`spec/data-service-api.v1.json`:756) なので、値が identifier なら encode しても変わらない。クライアントは値によらず常に encode する (D-2) |
| N-12 | ページ大きさと budget の上限 | 読める | 構造化 | `Page.size` の 1〜1000 (:1813-1821)、capability document の `limits` (:1320) |
| N-13 | 成功と失敗の判別 | 読めない | — | 失敗は `errors.content_type` の `application/problem+json` (:844) だが、両 peer は parameter 無し (`r2db-api/src/r2db_api/http.py`:345、`MitateDB-api/src/mitatedb_api/http.py`:118) と `; charset=utf-8` 付き (`r2db-api/src/r2db_api/http.py`:327、`MitateDB-api/src/mitatedb_api/http.py`:243) の 2 形で返す。parameter の扱いは外部標準 (N-17)。成功側は status も Content-Type も定めが無く (N-3・N-8)、problem+json でない応答を成功とみなしてよいとする文が無い |
| N-14 | problem+json でない失敗応答 (前段の proxy の 404 等) | 読めない | — | 契約は扱いを定めない。socket の nginx は未知の location に素の 404 を返す (`conformance-tests/socket_harness.py`:317-319) |
| N-15 | TLS | 読める | 散文 | `security.schemes` は「Opaque credential presented over TLS」(`spec/data-service-api.v1.json`:13)。試験 plug は TLS を通らない (§11)。参照クライアントは従うが、試験 plug のための例外を §4.1 に持つ |
| N-16 | 自分の key の role | 読めない | — | key は opaque。`CapabilityDocument.role` (:1345) は required (:1290-1296) に無い任意 field である (両 peer は出している: `r2db-api/src/r2db_api/capabilities_document.py`:190、`MitateDB-api/src/mitatedb_api/capabilities_document.py`:456) |
| N-17 | 前提にする外部標準の範囲 (HTTP・JSON・URI) | 読めない | — | 契約はどの外部標準も名指ししない (RFC の参照が無い)。header の形は :13 の散文、problem+json は :844 の値だけである |
| N-18 | `operation_catalog_url` が surfaces の外にあるとき key を提示するか | 読めない | — | `operation_catalog_url` は surfaces の外を許す (:1389)。`endpoints.operation_catalog` は runtime か developer の認証を要する (:445)。surfaces と違う origin に application の bearer を出すかを述べる文が無い。扱いは Q-4 (v0.3 で Q-2 から分けた) |
| N-19 | catalog の項がどの surface に属するか | 読めない | — | `OperationCatalogEntry` に surface の field は無い (`spec/data-service-api.v1.json`:2041-2056)。control の項の name の `control.` 修飾は生成器の規約で (`tools/contract_catalog.py`:80-87)、契約の文に無い。修飾の無い `audit_query` の項 (`spec/OPERATION_CATALOG.json`:5-20) は control に属し、それは deprecation_note の散文 (`spec/data-service-api.v1.json`:432) にしか無い。契約 JSON の節 (`endpoints` / `control_endpoints`) は構造化値だが、alias 1 項はその節と surface が一致しない |

読めない点は 10 件 (N-1・N-2・N-8・N-11・N-13・N-14・N-16・N-17・N-18・N-19。v0.2 の 8 件に N-11 の判定変更と N-19 を足した)。扱いは Q-1 (N-1)、Q-4 (N-18)、Q-2 (残り 8 件) が決める。

### 4.1 契約外知識の表

読めない点と、読めるが試験のために従わない点 (N-15) を、クライアントがどの値で埋めるかを列挙する。クライアント module に同じ表を持ち、pin する (D-6、D-7 の 15)。Q-1・Q-2 が (A) 系なら該当行は契約の file:line に置き換わって消え、(B) なら残る。N-15 と N-18 の行は裁定によらず残る。

| # | クライアントが使う値 |
|---|---|
| N-1 | operation の surface を N-19 の行で決める。その surface の base URL (data は入力の base URL、control は段 (1) で読む `surfaces.control.base_url`) の末尾からその surface の base path を除き、operation の path 全体を足す (alias の `/v1/audit/query` も control の base URL に結合する)。最初の要求 (capabilities) も同じ規則で入力の base URL に結合する。base URL がその surface の base path で終わらないとき、surface が宣言されていないときは送信せず例外にする (v0.2 の「path の接頭辞で面を決める」は alias を data 面に誤結合するので改めた。再確認の指摘 1) |
| N-2 | `{entity}` に entity 名 (SchemaOperationRequest の `entity` と同じ値) を入れ、percent-encode する |
| N-8 | 要求の Content-Type は `media_type` (`spec/data-service-api.v1.json`:7) の値 |
| N-11 | placeholder の値は常に percent-encode する (`/` を含む予約文字すべて。D-2) |
| N-13 | 応答の Content-Type の media type (parameter を除く) が `errors.content_type` (:844) と一致すれば失敗、そうでなければ JSON として response schema で検証する |
| N-14 | N-13 のどちらにも当たらない応答は例外にする (fail closed)。例外に本文と header を写さない |
| N-15 | https でない base URL には bearer を送らない。例外として、host が loopback か `.invalid` の合成名のときだけ http を許す (試験 plug で走らせるため。§11)。読める要求 (:13) からの逸脱である |
| N-16 | どの secret が runtime / developer かは、入口が帯域外で申告した値を使う (§6) |
| N-17 | HTTP (method・header・media type の parameter)、JSON、URI (percent-encode) を前提にする |
| N-18 | 使わない。`operation_catalog_url` を取りに行かない (D-2) |
| N-19 | catalog の項と method・path が一致する項を契約 JSON の `endpoints` と `control_endpoints` から引き、`control_endpoints` なら control、`endpoints` なら data とする。`endpoints` の項で `deprecation_note` を持つもの (現行は :432 の 1 項) は、その散文により control とする |

## 5. 作業列の段の表

段と期待はフェーズ11 設計 §7 (`docs/design/PHASE11_MIN_COMMON_PROFILE_V1.md`:798-815) のままとし、本表は「契約のどの節から組んだか」の列を足す。同表の変異候補は peer 側のもので、本条件では C-28 と同時に赤になってよい。本条件だけを赤にする変異は単体テスト側 (D-7) が持つ。catalog の項は `spec/OPERATION_CATALOG.json`、契約は `spec/data-service-api.v1.json` の行を指す。

| 段 | フェーズ11 設計 §7 の段 | 組み立ての出所 (追加列) | 関わる N |
|---|---|---|---|
| (1) | capabilities と契約版を読む | catalog `capabilities` (:22)、response schema CapabilityDocument (契約 :1286)、床の capability 名は契約 :321-330。3 つの `contract_version` の一致 (D-10)、入口の base URL と `surfaces.data.base_url` の一致 (D-2a) | N-1・N-6・N-7・N-15・N-16・N-19 |
| (2) | developer で entity を作る (enum と `nullable: false`) | catalog `schema` (:297)、SchemaOperationRequest (:1149)、`field_constraints` (:1228) | N-5・N-7・N-8 |
| (3) | runtime で catalog を読む | catalog `catalog` (:37)、CatalogDocument (:1467)、EntityDescriptor.field_constraints (:2003) | N-1・N-6 |
| (4) | catalog だけから insert を組み、enum 外の値で送る | catalog `mutate` (:251)、MutationRequest (:1045)、拒否の語彙 (:885-886) | N-2・N-3・N-5・N-11・N-13 |
| (5) | 診断だけで同じ要求体を直す | `details.field` の '/' path (:886)、enum は (3) の EntityDescriptor | N-4 |
| (6) | 同じ `idempotency_key` で dry_run | dry_run (:824-826)、MutationRequest の `dry_run` | N-4 |
| (7) | (6) の plan を提示して実送信 | plan (:826)、idempotency (:829) | N-4 |
| (8) | 同 key 同 body で再送 | idempotency.record / correlation (:829-830) | N-4 |
| (9) | baseline の各演算子で order_by・page.size・budget 付き query | catalog `query` (:281)、QueryRequest (:991)、演算子 (:314・:725-736・:332)、上限 (:1813-1821・:1320) | N-2・N-10・N-11・N-12 |
| (10) | 述語 update | catalog `mutate`、`Mutation` (:1827) | N-2・N-5・N-11 |
| (11) | 述語 delete (declare-and-echo) | 拒否 409 と `required_confirmation` (:663-670)、復唱 (:682・:695) | N-3・N-4 |
| (12) | 最終 query で状態を確認 | catalog `query`。next_page は床の外 (:332) なので 1 ページで収まる行数にする | N-12 |

## 6. port の追加

- 追加するもの: application の隔離面ごとに「wire への入口」を返す method 1 つ。返すのは base URL、送信関数、その application の runtime と developer の bearer secret である (D-4)。port 版を上げる (仮)。
- secret は D-5 のとおり adapter の既存 bootstrap 経路で得たもの (`CredentialHandle.secret`、`conformance-tests/adapter.py`:91) をそのまま渡す。
- 送信関数の差: http ×2 は ASGI transport を包み、宣言 base URL は `.invalid` の合成値のまま (`r2db-api/conformance/conformance_adapter_r2db_http.py`:947-950)。socket ×2 は実 TCP で nginx に届き、宣言 base URL は実 loopback URL である (`r2db-api/conformance/conformance_adapter_r2db_socket.py`:533-546)。socket ×2 とも宣言 URL を書き換えずに dial する (D-2a)。
- 対象の選別は `transport_kind` の宣言 (`conformance-tests/adapter.py`:1125) による。名前や URL の形では判定しない (`docs/work-orders/OPERATING_CONDITIONS.md` §1.7 の 52、C-29 と同じ)。
- 返す secret は 2 本だが、参照クライアントの 1 インスタンスに渡すのは 1 本である (D-4a)。
- 送信関数の引数と戻り値の形、in-process plug での振る舞いは作業指示書で確定し、実装前に監督へ上げる (`docs/work-orders/OPERATING_CONDITIONS.md` §1.5 の 37)。入口を両 peer に同名で置くので同型性テストの対象である (同 §1.5 の 38、D-8)。

## 7. Security Invariants との関係

本項目は新しい能力を足さない。検査側の層である (`security/SECURITY_INVARIANTS_V1.md` §2)。

| SI | 関係 |
|---|---|
| SI-05 | 作業列が値・演算子・識別子を契約の構造で送り、拒否を `code` と `details` で受ける (段 (4)(5)(9))。送信前の schema 検証は server 側検証の代わりではない |
| SI-09 | 段 (11) の declare-and-echo を、復唱句を直書きせず拒否の宣言から得て行う |
| SI-10 | 段 (4) の拒否が値を返さないことを wire 上の本文で見る。加えて、参照クライアントとテストの失敗メッセージ・ログに bearer secret を出さない (K-5、D-9) |
| SI-11 | 段 (7)(8) の実送信と再送で行が 1 行のままであること |
| SI-14 | 成功結果の `request_id` と、再送が最初の `request_id` を返すこと |
| SI-03・SI-06 | role は catalog の roles から選び、要求に application や role を選ぶ field を入れない。本項目は新たに検証しない |

新条件 (仮) の SI 列は C-28 と同じ SI-05、SI-09、SI-10、SI-11、SI-14 を見込む。公開リポジトリ規律 (`docs/work-orders/OPERATING_CONDITIONS.md` §1.9 の 60) により、文書・テスト・失敗メッセージには合成値と `example.invalid` だけを使う。

## 8. 却下した代替案

| 案 | 却下の理由 |
|---|---|
| 既存 adapter を catalog 駆動に書き換える | K-6 に反し、6 plug 全部の adapter に触れる。参照クライアントが通れば別項目の候補だが、本設計では起票しない |
| OpenAPI / SDK を生成する | K-3 に反する。`spec/README.md`:11-14 が OpenAPI を派生・非正本としている |
| socket ×2 だけで回す | 依頼者裁定 U-3 が採った (c) 案の定義「wire plug (http ×2、socket ×2)」(`docs/design/PHASE11_MIN_COMMON_PROFILE_V1.md`:506) に反する |
| `tools/` に置く | 完了ゲート (root suite) が `tools/tests` を含まない。証明は conformance に置く |
| real-server launcher (別プロセス) で回す | 裁定の plug 集合と違う。将来の追加候補である |

## 9. 依頼者判断待ち

Q-1 N-1 (base URL と path の結合規則) をどう決めるか。契約に規則は無いが、両 peer・runbook・C-19・C-26 は接頭辞を保つ結合を既に持っている (§4 N-1)。どの案でも `operation_catalog_url` は結合の対象外である (宣言された URL をそのまま使う。surfaces の外の origin に key を出すかは N-18・Q-4)。catalog の項から surface を読めない点 (N-19) は Q-2 が扱う。契約版の列は `versioning.compatibility` (`spec/data-service-api.v1.json`:33) による見込みである。

| 案 | 内容 | 帰結 | 契約版 |
|---|---|---|---|
| (A1) 監督の推奨 | 現物の規則を契約に書く。結合先は path の接頭辞ではなく operation の属する surface で決める (`control_endpoints` の項と alias の `endpoints.audit_query` は control、それ以外の `endpoints` の項は data)。要求 URL はその surface の base_url から末尾のその surface の base path (data は `versioning.base_path`、control は `versioning.control_base_path`) を除き、path 全体を足したものとする。入力の base URL は `surfaces.data.base_url` の形 (base path で終わる) とし、最初の capabilities もこの規則で呼ぶ。base path で終わらない base_url は結合せず、宣言されない surface の operation は呼ばない (fail closed。`surfaces.control` を宣言しない配備では control 面の operation は呼べない)。`operation_catalog_url` は宣言された URL をそのまま使う例外であることを同じ文で述べる。:1385 の「appending a path」の文はこの規則を指す形に直す | peer の挙動の変更は無いが、版の宣言と packaged 写しは変わる (§10 の契約 WP)。成文化になるのは data surface の結合 (両 peer の `derive_operation_catalog_url`) と alias の置き場 (:432 と両 peer の `control_http.py` の 2 route) である。control surface の結合は peer に実装が無く、両 peer の surfaces 検証 (`platform_declarations.py`) と整合する規則の新設である。接頭辞付きの配備でも成り立ち、catalog の形を変えない。入力 base URL の文を含むので §4.1 の N-1 の行は契約の file:line に置き換わる。N-19 は残る | minor |
| (A2) | origin 規則を契約に足す。「path は origin からの絶対 path であり、base_url の origin に結合する」。base_url の path 部分が base_path と完全に一致することも義務にする。:1385 の文を直す | 両 peer の接頭辞対応 (`operation_catalog.py` の結合、surfaces 検証) と runbook の接頭辞付き配備の記述を撤回させる | minor (obligations に entry を足す) か major (:33 の semantic change に当たる) かは未判定 |
| (B) | 契約は変えず、参照クライアントの結合規則を本書 §4.1 にだけ書く | 契約の欠落が残る。§4.1 の N-1 の行が残り、証明は契約と本書 §4.1 に対するものになる | なし |
| (C) | catalog と endpoints の path を base_path 相対に変える | :33 の「removal or semantic change requires a new major version」に当たる。両 peer の `derive_operation_catalog_url` の assert (`path.startswith(base_path)`) が落ちる。散文中の絶対 path (`versioning.discovery`・`control_discovery`・`version_binding` の `/v1/…`・`/control/v1/…`) と食い違う。現行でも alias の `audit_query` の 1 項は path (`/v1`) と surface (control) が一致しないが、(C) では canonical の `audit_query` と `control.audit_query` も同じ `/audit/query` になり、path で区別できなくなる (catalog の項に surface の field は無い。N-19) | major |

(A1) の文案 (surface を path の接頭辞ではなく operation の所属で決め、その surface の base path だけを除く。v0.2 の文案は alias を data の base_url に結合したので改めた): 「Each operation belongs to one surface: every entry in control_endpoints belongs to the control surface, and so does endpoints.audit_query, which its deprecation_note places on the control surface's own host; every other entry in endpoints belongs to the data surface. The base URL a client is given is the deployment's surfaces.data.base_url, and the client reaches GET capabilities from it by the rule that follows. To call an operation, a client takes the base_url of the operation's surface, removes that surface's own base path from its end -- versioning.base_path for the data surface, versioning.control_base_path for the control surface -- and appends the operation's whole path, so any prefix ahead of the base path is kept. A base_url that does not end with its surface's base path is not joined, and an operation of a surface the capability document does not declare -- the control surface where surfaces.control is omitted -- is not called: the client stops rather than guessing. operation_catalog_url is not formed this way: a client uses it exactly as declared.」

Q-2 §4 で「読めない」となった点のうち Q-1 (N-1) と Q-4 (N-18) の外の 8 件を、本項目で契約に足すか、別起票にするか。足す文の趣旨と契約版の見込みは次のとおり。

| # | 契約に足す 1 文の趣旨 | 契約版の帰結 (見込み) |
|---|---|---|
| N-2 | path の placeholder には、その名の値 (`{entity}` は entity 名、control 面は各 ID) を入れる | minor (定義の追加) |
| N-8 | 要求 body と成功応答の Content-Type は `media_type` (:7) である | minor (peer への新しい義務になるかは作業指示書で実測) |
| N-11 | placeholder の値は URI の percent-encode をして入れる (N-17 の外部標準に拠る) | minor |
| N-13 | 応答の Content-Type の media type (parameter を除く) が `errors.content_type` と一致すれば失敗、そうでない JSON 応答は成功である | minor (両 peer の 2 形はどちらも規則に収まる) |
| N-14 | 失敗でも成功でもない応答 (前段の proxy の応答等) は、client が中身を解釈せず失敗として扱う | minor (client 側の文) |
| N-16 | `CapabilityDocument.role` を required にする | minor (`version_binding` の obligations に entry を足す。両 peer は既に出している) |
| N-17 | 前提にする外部標準 (HTTP・JSON・URI) を名指しする | minor |
| N-19 | 派生 catalog の項が属する surface を示す (name の `control.` 修飾は `control_endpoints` 由来であること、修飾の無い `audit_query` は control に属すること) | minor |

- (A) 本項目で足す (1 回の契約版上げにまとめる)。§4.1 の該当行は契約の file:line に置き換わる。監督の推奨。
- (B) 列挙だけして別起票。§4.1 の該当行が残り、証明は契約と本書 §4.1 に対するものになる。

Q-3 作業列の範囲。

- (A) C-28 と同じ 1 周のみ。監督の推奨。
- (B) common_baseline の全 operation を網羅する表駆動に広げる (規模が上がる)。

Q-4 N-18: surfaces の外の origin にある `operation_catalog_url` に application の key を出すか。安全上の選択なので Q-2 から分けた (v0.3)。参照クライアントは `operation_catalog_url` を取りに行かない (D-2) ので、Q-4 は契約の文だけの問いであり、本項目の証明には影響しない。現行は (B) の形である: 契約は URL を data surface の外 (CDN 等) に置くことを許し (`spec/data-service-api.v1.json`:1389)、`operation_catalog` は runtime か developer の認証を要する (:445・:447-450)。C-29 の段 (ii) は宣言された URL に bearer を付けて dial する (`conformance-tests/test_c29_operation_catalog_url.py`:167)。

| 案 | 内容 | 帰結 | 契約版 |
|---|---|---|---|
| (A) 監督の推奨 | key を出すのは URL の origin が data surface の origin と一致するときだけ。外の origin には key なしで取りに行く | 配る側が認証なしで配る義務を負う。`operation_catalog` の認証要求 (:445・:447-450) とぶつかるので、外の origin で配る文書には認証を課さない旨を足す必要がある | 未判定 (認証の意味を変えるのが :33 の semantic change に当たるか) |
| (B) | 宣言された URL には常に key を出す (現行の形) | 第三者 origin に application の bearer が出る。現行の契約と C-29 は変わらない | minor (現行の形を明記する文) |
| (C) | 契約は決めず別起票 | N-18 は契約の欠落として残る | なし |

## 10. WP 分割の見込み

確定は作業指示書 (Change Set Manifest) で行う。各 WP の完了条件と変異の対応は `docs/work-orders/OPERATING_CONDITIONS.md` §1.5 の 40 に従う。

| WP (仮) | 内容 | 主に触るパス |
|---|---|---|
| 契約 (Q-1 (A1) / (A2) / (C)・Q-2 (A) のときだけ) | 契約の文、派生 catalog の再生成、版の宣言 | `spec/`、両 peer の packaged 写し |
| port | wire への入口 (§6)、4 plug の実装、同型性テストの登録 | `conformance-tests/adapter.py`、両 peer の `conformance/`、両 peer の同型性テスト |
| クライアント | `reference_client.py`、§4.1 の表、D-6 の AST pin と散文由来リテラルの表、D-7 の単体テスト、`schema_check.py` の拡張・docstring・keyword ガード (D-7a) | `conformance-tests/` |
| 条件 | 新条件 (仮) のテスト、`CONDITIONS.md` の行と `CONDITIONS_HISTORY.md` の節、`security/CONTROL_MAPPING.md` の証拠、台帳 `RM` §0.1.1 の G-2 / G-3 行 (`RM`:39・:56) の条件数と表記の内訳 | `conformance-tests/`、`security/`、`docs/design/ROADMAP_POST_PHASE7_V1.md` |

新条件の Status 表記は `conformance-tests/CONDITIONS.md` の凡例 (:63-67) に従う。凡例の「four adapters」は登録された全 adapter を意味するので、6 plug のうち 4 plug で走る本条件には使わない。表記の形と凡例に足す文は作業指示書で確定する。

作業指示書で実測して確かめる事項:
- C-19 の bearer 合成走査 (`conformance-tests/test_c19_client_self_sufficiency.py`) と socket harness の `_build_client` 経路の pin (`conformance-tests/test_socket_harness.py`) に、新しい入口が干渉しないこと。
- D-4 の parametrize での xdist の group 付け (`conformance-tests/conftest.py`:125-131)。`registry-guards` group に入らないか、C-19 の前提 (同 group は provisioning も実 process 起動もしない。`conformance-tests/test_c19_client_self_sufficiency.py`:374-386) を破らないか。
- D-7a の後も C-11 の判定が変わらないこと。
- D-6 の「運ぶだけ」を送信記録で確かめられる plug と、確かめられない plug。

## 11. honest scope

- 証明の範囲は common_baseline の 1 周 (C-28 の 12 段) だけである。baseline の他の組み方、床の外の operation、control 面は証明しない。緑は「この作業列について、要求の組み立てに契約外の知識が要らなかった」ことを示すだけで、文書が十分であることは示さない。
- 「契約文書だけ」が成り立つのは要求の形 (path・method・header・body) までである。作業列の意味 (N-4) は散文にしか無く、人 (起草者・実装者) が読んで書く。ここがこの証明の限界である。
- application の登録と key の発行は帯域外 (D-5)。入力 3 の「認可済みの key」を与えられた後だけを示す。
- http ×2 は ASGI transport であり、実 socket を通らない。実 TCP と nginx を通るのは socket ×2 だけで、その app も adapter と同じプロセスで動く。別プロセスで起動する documented 合成根 (real-server launcher) は対象外である。
- 結合規則は 4 plug では区別されない。4 plug の宣言 base URL の path はどれも `/v1` ちょうどで、wire 上で赤になるのは `/v1` の二重だけである。接頭辞付きの結合は単体テスト (D-2a) でだけ示す。origin (scheme・host・port) の誤りが wire で赤になるのは socket ×2 だけで、ASGI transport は host を見ない (`r2db-api/conformance/conformance_adapter_r2db_http.py`:1104-1110)。
- 送信関数は D-6 の pin の外にある。「運ぶだけ」を送信記録で確かめられない plug は、作業指示書の実測 (§10) の結果をここに列挙する。
- 契約は TLS を前提にするが (N-15)、試験 plug は TLS を通らない。socket ×2 は loopback の http、r2db http は https (`r2db-api/conformance/conformance_adapter_r2db_http.py`:948)、MitateDB http は `.invalid` の http (`MitateDB-api/conformance/conformance_adapter_mitatedb_http.py`:125・:131) を宣言し、http ×2 はどちらも ASGI transport である (v0.2 の「http ×2 は https を宣言」は誤り。再確認の指摘 7)。参照クライアントは https でない base URL に bearer を送らないが、loopback と `.invalid` の http を例外として許す (§4.1 の N-15)。4 plug のうち 3 plug はこの例外の下で走る。https でない URL を拒むことは単体テスト (D-7 の 16) でだけ示す。
- 参照クライアントは `operation_catalog_url` を取りに行かない (D-2)。配る catalog と `spec/` の一致は C-29 が持つ。
- 送信前に request schema で検証するので、peer 側の request_schema 拒否の経路はこの条件では通らない (既存条件が持つ)。
- C-28 で単独で赤になるとされた段 (5)(9) は、本条件が入ると本条件と同時に赤になる。単独性は本条件と共有になる。
- 読めない点 (N-1・N-2・N-8・N-11・N-13・N-14・N-16・N-17・N-18・N-19) は、Q-1・Q-2・Q-4 の裁定が出るまで契約の欠落として残り、クライアントは §4.1 の値で埋める。
- 入力の base URL を `surfaces.data.base_url` の形に固定するので、control / audit の credential だけを持つ client の最初の要求は本設計の範囲外である (`versioning.control_discovery` は data の host が control の権限を受けることを義務にしていない)。
- `endpoints.audit_query` の `deprecation_note` (`spec/data-service-api.v1.json`:432) は alias の保持を「1.4.0 の後の minor 1 版」とするが、契約 1.12.0 に alias は残っている。文言と現物の食い違いは本設計では解かず、台帳 `RM` R-118 に起票した。
- 性能について何も主張しない。4 node 分の往復が完了ゲートの壁時計を延ばす量は実測して記録する。目標値は先に置かない。
- 本設計は実行検証されていない。§3 D-7 と §5 の変異はすべて候補であり、実測は作業指示書の「完了条件 → 変異」表で行う (`docs/work-orders/OPERATING_CONDITIONS.md` §1.5 の 34)。

## 12. 設計レビュー 1 の反映 (v0.2)

観点 A は F-1〜F-10、観点 B は 1〜13 とクラスの引き上げ。裁定はすべて採用 (監督、2026-09-30)。

| 指摘 | 裁定 | 反映先 |
|---|---|---|
| A F-1、B 8 (Q-1 の帰結と peer の既存の結合、互換規則) | 採用 | §4 N-1、§9 Q-1 |
| A F-2 (結合を 4 plug が区別しない、r2db socket の URL 書き換え) | 採用 | D-2a、§6、§11 |
| A F-3、B 3 (AST pin が契約外の経路を塞がない、header 名が散文) | 採用 | D-6、§4 N-6 |
| A F-4 (§4 の判定漏れ) | 採用 | §4 N-13〜N-18、D-2、§11 |
| A F-5、B 4 (K-4 と (B) 案の両立、Content-Type の断定) | 採用 | §4.1、D-2、§9 Q-2 |
| A F-6 (placeholder の encode) | 採用 | D-2、§4 N-11、D-7 の 4 |
| A F-7 (secret の非露出の機構) | 採用 | D-9、D-7 の 7 |
| A F-8 (契約版の照合) | 採用 | D-10、§5 段 (1)、D-7 の 6 |
| A F-9、B 1、B 5、B 10 (変異の空振り・注入先・単独性) | 採用 | D-7、§5、§11 |
| A F-10 (`operation_catalog_url` と bearer) | 採用 | §4 N-18、§9 Q-1、D-2 |
| B 2 (対象 plug の選び方) | 採用 | D-4、§10 |
| B 6、B 12 (ID の衝突、位置参照と引用の誤り) | 採用 | §0、§4、§5、§6、§7、§8、§10、§11 |
| B 7 (Status 表記、G-2 / G-3 行) | 採用 | §10 |
| B 9 とクラスの引き上げ (C → D、レビュー回数) | 採用 | D-8 |
| B 11 (D-7a の付随作業) | 採用 | D-7a、§10 |
| B 13 (K-6 と D-4 の矛盾) | 採用 | K-6 |

## 13. 再確認レビューの反映 (v0.3)

| 指摘 | 裁定 | 反映先 |
|---|---|---|
| 1 ((A1) の文案と `audit_query` の deprecation_note の矛盾) | 採用 | §4 N-1・N-19、§4.1 N-1・N-19、§9 Q-1 の (A1)・(C) と文案、D-2a、D-7 の 19 |
| 2 (入力の base URL、最初の要求の宛先、fail closed) | 採用 | §9 Q-1 の (A1) と文案、D-2、§4.1 N-1、D-7 の 17・18 |
| 3 (D-7 の表の欠落 5 件) | 採用 | D-6、D-7 の 3・10〜15 |
| 4 (Q-2 の中身と契約版、N-18 の分離) | 採用 | §9 Q-2 の表、Q-4、§4 N-18 |
| 5 (TLS) | 採用 | D-2、§4 N-15、§4.1 N-15、§11、D-7 の 16 |
| 6 (N-11 と N-17 の食い違い) | 採用 | §4 N-11 (判定を「読めない」に変更)、§4.1 N-11、§5 |
| 7 (§11 の http ×2 の scheme) | 採用 | §11 |
| 8 ((A1) の帰結の「peer のコード変更は無い」) | 採用 | §9 Q-1 の (A1) の帰結 |
