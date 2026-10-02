# 参照クライアント設計 (台帳 `RM` R-108)

## 0. 版数・位置づけ

| 版 | 日付 | 状態 |
|---|---|---|
| v0.1 | 2026-09-30 | 設計レビュー前・依頼者裁定待ち (Q-1〜Q-3) |
| v0.2 | 2026-09-30 | 設計レビュー 1 反映済み・依頼者裁定待ち (Q-1〜Q-3)。反映の一覧は §12 |
| v0.3 | 2026-09-30 | 設計レビュー 1 と再確認を反映済み・依頼者裁定待ち (Q-1〜Q-4)。反映の一覧は §13 |
| v0.4 | 2026-09-30 | 依頼者裁定反映済み・設計レビュー 2 前。裁定は §9 の【裁定】、帰結は §9.1 (契約 (仮) の変更案)・§9.2 (契約版の帰結) と各節の v0.4 註。基点は main 168f25f |
| v0.5 | 2026-09-30 | 設計レビュー 2 反映済み。実装は R-115 の merge 後。反映の一覧は §14、各節の v0.5 註 |
| v0.6 | 2026-09-30 | 設計レビュー 2 と再確認を反映済み。実装は台帳 `RM` R-115 の merge 後。反映の一覧は §15、各節の v0.6 註 |
| v0.7 | 2026-10-01 | 実装後の註のみ (本文の判定は変えない)。(仮) の番号は契約 1.14.0・従属判断 19・条件 C-35・port v1.21・`security/CONTROL_MAPPING.md` 3.16 に振った (作業指示書 `docs/work-orders/WORK_ORDER_R108_REFERENCE_CLIENT_V1.md` §0 の 9)。本書の `file:line` と現行の行の対応は同書 §0.2。各節の v0.7 註 (D-2・D-6・D-7・§6・§7・§11) |

- 対象: 計画文書 `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の R-108 (`RM`:462)。規模 L。
- 基点: main c729ab0 (契約 1.12.0)。v0.4 以降に足した file:line は main 168f25f による (§4 の判定は c729ab0 のまま)。並走: 台帳 `RM` R-115 が契約版・条件番号・port 版・launcher を持つ (未 merge)。本書の契約版・条件番号・port 版はすべて (仮) であり、merge 直前に main を読んで振る (フェーズ11 設計 `docs/design/PHASE11_MIN_COMMON_PROFILE_V1.md` D-7 と同じ規律)。
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

D-1 置き場と形。`conformance-tests/reference_client.py` (テストでない共通モジュール 1 本) と、新条件 (仮) のテスト 1 本を置く。クライアントの入力は、契約 JSON と catalog (`spec/` から読んだ dict)、base URL、bearer secret、送信関数 (transport) である。参照クライアントは application の credential だけを扱うので、入力の base URL は §9.1 の #1 の言う application credential の面の base_url (`surfaces.data.base_url`) である (v0.5)。根拠: 証明は完了ゲートが走る conformance に置く (§8)。conformance の既存の import 規約 (テストモジュールが `schema_check` 等を bare import する) にそのまま乗る。

D-2 要求の組み立て。operation 名から catalog の method / path / request_schema / roles を引く。path の placeholder は呼び出し側が値を渡し、クライアントは値によらず常に percent-encode する (`/` を含む予約文字をすべて。N-11)。認証 header は契約 `security.schemes` から組む (N-6)。Content-Type、成功と失敗の判別、problem+json でない応答の扱いは §4.1 の表の行による (N-8・N-13・N-14)。body は呼び出し側 (作業列) が意図として与え、送信前に契約の request schema で `conformance-tests/schema_check.py` により検証する (クライアントが契約外の body を送れない)。応答は response schema で検証し、失敗は problem+json の `code` で判断する。HTTP status では分岐しない (`spec/data-service-api.v1.json`:872)。参照クライアントは `operation_catalog_url` を取りに行かない。catalog は入力 1 の `spec/OPERATION_CATALOG.json` から読む (N-18)。宛先は最初の要求 (capabilities) を含め §4.1 の N-19・N-1 の行で決める。入力の base URL が `versioning.base_path` で終わらないとき、operation の surface が段 (1) の capability document に宣言されていないとき (`surfaces.control` の欠落) は、送信せず例外にする (fail closed)。https でない base URL には bearer を送らない (例外は §4.1 の N-15 の行)。
- v0.4 註 (2026-09-30、依頼者裁定 Q-1 (A1)・Q-2 (A)・Q-4 (A)): 上の「§4.1 の表の行による」「§4.1 の N-19・N-1 の行で決める」は、契約 (仮) の変更案 (§9.1) の文を読むことに置き換わる。挙動の差は 2 点だけである: (i) 自分の key の role は段 (1) の capability document の `role` から読む (§9.1 の #8。v0.3 は入口の申告)、(ii) 要求に body があるときは `Content-Type` を `media_type` で送る (#5)。surface の判定は、`control_endpoints` と同じ名前を持つ `endpoints` の項を control とする (#10。v0.3 の「`deprecation_note` を持つ項」から、契約の文に合わせて改めた)。
- v0.5 註 (2026-09-30、設計レビュー 2 の B-9・A-2): (ii) は挙動の差ではない。出所が §4.1 の N-8 の行から #5 に移るだけで挙動は v0.3 と同じである (単体テストの行は D-7 の 21 で足した)。挙動の差は (i) と次の 1 点になる: `control_endpoints` と同じ名前を持つ `endpoints` の項 (alias) は URL を組まず、送信せず例外にする (#1・#10。v0.4 の「control とする」を改めた)。v0.6 註 (再確認の指摘 5 (f)): 上の「次の 1 点」は数え漏れである。挙動の差は (i)、alias、3xx を追わない (D-7 の 25)、`errors.shape` に合わない problem+json の `code` を読まない (24)、media type の大小文字 (22) である。
- v0.7 註 (2026-10-01、コードレビューで足した client の挙動。作業指示書 `docs/work-orders/WORK_ORDER_R108_REFERENCE_CLIENT_V1.md` 訂正註 5 の 2・3・5・6・9): (1) base URL は URI として読み、query か fragment を持つものは結合しない (送信せず例外)。(2) 例外の文に入れる `code` は契約 `errors.codes` が列挙するものだけである (`code` の属性は常に持つ)。(3) `Content-Type` が 2 本以上の応答、NaN / Infinity を含む応答、深すぎる本文は解釈しない失敗とする。(4) NaN / Infinity を含む request body は送らない (送信せず例外)。(5) `localhost` は §4.1 の N-15 の例外に入れない (N-15 の行どおり loopback か `.invalid` だけ)。

D-2a 結合の検証と送信関数。(1) 参照クライアントの単体テスト (記録用の偽の送信関数) で、接頭辞付き base URL・control 面・`/v1` 二重・`operation_catalog_url` の結合と、alias を結合しないことを固定する (D-7 の 3・14・19。alias は v0.5)。(2) wire への入口が返す base URL は、その plug の capability document の `surfaces.data.base_url` (application credential の面の base_url。#1) と一致することを段 (1) で assert する。(3) 送信関数は渡された URL・header・body を変えない「運ぶだけ」のものとする。r2db socket の既存 client の `send` は要求 URL の scheme/host/port を宣言面の値で上書きする (`r2db-api/conformance/conformance_adapter_r2db_socket.py`:458-460)。これは避けられるので避ける: 宣言 URL の port は面の生成時に予約済みで (同:208-210)、面の `base_url` を読むと面が起動する (同:233-236)。入口は返す前にそれを読み、宣言 URL をそのまま dial する素の transport を渡す。MitateDB socket は既に URL を書き換えずに dial する (`MitateDB-api/conformance/conformance_adapter_mitatedb_socket.py`:319-329)。既存の `send` は変えない (K-6)。送信関数は redirect を追わない (3xx をそのまま返す)。v0.6 (再確認の指摘 6): #1 の redirect の規則は、wire では送信関数 (D-6 の pin の外) が redirect を追わないことに依る (§11)。

D-3 作業列。C-28 の 12 段と同じ 1 周を、port ではなく参照クライアントで実行する新しい条件 (仮番号) とする。C-28 本体は触らない。段ごとに「契約のどの節から組んだか」を §5 の表に持つ。

D-4 対象 plug。依頼者裁定どおり wire plug 4 つ (http ×2 = ASGI、socket ×2 = 実 socket + nginx) とする。そのために port に「wire への入口」を 1 つ足し、port 版を上げる (§6)。in-process plug 2 つは wire が無いので対象外と明記する。対象の選別は module 読み込み時の registry 読み (`transport_kind`) で wire adapter 名の列を作り、それで直接 parametrize する。skip も early return も使わない。同じ module 読み込み時に数が 4 であることを assert する (`docs/work-orders/OPERATING_CONDITIONS.md` §1.5 の 32、§1.3 の 22・26)。xdist の group 付けは未実測であり §10 で実測する。

D-4a key の本数。参照クライアントの 1 インスタンスは key を 1 本だけ持つ (目標文の「an authorized API key」)。作業列は 2 インスタンスを使う: schema 操作は developer の key、それ以外は runtime の key。どちらの key で呼べるかは catalog の roles から選ぶ (N-7。どの secret がどの role かは N-16)。根拠: application を使う agent が普段持つのは runtime の key であり、developer 1 本で全段を通すと runtime の経路が証明から落ちる。v0.4 註: N-16 は裁定 Q-2 (A) により契約で読める (§9.1 の #8)。インスタンスは段 (1) で読んだ `role` と catalog の roles で呼べる operation を決める。入口の申告 (§6) はテストの assert にだけ使う。

D-5 帯域外に残すもの。application の登録と key の発行 (bootstrap) は adapter の既存経路のままとする。目標文の入力 3 は「認可済みの key」であり、発行は目標の外だからである。control 面 (`control.*`) は本項目の作業列に入れない。

D-6 直書き禁止の検査 (AST)。
- クライアント module: import は標準ライブラリと `schema_check` だけ。catalog の operation 名・path・method・schema 名と一致する文字列リテラルを持たない (禁止集合は catalog と契約から導出して照合する)。散文からしか得られない語は下の「散文由来リテラルの表」に契約の file:line 付きで列挙し、表に無いリテラルは赤にする。§4.1 の表も同じ module に持ち、pin する (照合先は D-7 の 15)。許可集合の厳密な形 (契約 JSON の key 名の扱い、例外メッセージの文字列) は作業指示書で確定する。
- テスト module: import の制限は掛けない。代わりに、wire への要求は参照クライアントの公開 API 経由だけで送り、送信関数を直接呼ばないこと、port から使うのは provisioning と wire への入口だけであること、作業列に adapter 名・`transport_kind`・host による分岐が無いこと (対象の選別は D-4 の module 読み込み時の 1 か所) を pin する。
- 送信関数は peer 側のコードで pin の外にある。D-2a の「運ぶだけ」は、送った要求を記録して参照クライアントが組んだ要求と一致することで確かめられる plug では確かめ、確かめられない plug は §11 に書く。

| 散文由来リテラル | 出所 |
|---|---|
| `Authorization` | `spec/data-service-api.v1.json`:13 (`security.schemes.application_credential.description` の「Authorization: Bearer <secret>」) |
| `Content-Type` | §9.1 の #5 (v0.4 で足した。header 名は HTTP の語で、#9 が HTTP を名指す) |

D-6 の v0.7 註 (2026-10-01): 上の「許可集合の厳密な形は作業指示書で確定する」の確定形は、作業指示書 `docs/work-orders/WORK_ORDER_R108_REFERENCE_CLIENT_V1.md` の M-2 を、同書 訂正註 5 の 4 と訂正註 6 の 2 で改めたものである (クライアントの import は閉じた表で固定する、例外の名前への束縛と `__doc__` の読み出しは赤、(iii) の免除は位置引数がちょうど 1 つで keyword の無い構築のその引数と `message=` の値だけ)。テスト module の pin の確定形は同書 訂正註 6 の 3 (port の他の操作を呼ぶ経路と `adapter_name` による分岐を赤にする)。

D-7 単体テストと変異 (空振り防止の見込み。確定は作業指示書)。記録用の偽の送信関数で参照クライアントを駆動する単体テストを置き、完了条件と変異を 1 対 1 で持つ。変異の注入先は `spec/` のファイルではなくクライアントのコードとテストとする (`spec/` に入れると再生成一致テストと C-29 も同時に赤になり、`docs/work-orders/OPERATING_CONDITIONS.md` §1.5 の 33 を満たさない)。wire 上の作業列の変異 (§5) は C-28 と同時に赤になってよく、この条件単独で赤になる必要があるのは単体テスト側である。契約の文の文字列ピン (§10 の契約 WP) は別で、#2・#12 のピンの変異は CONTRACT_HISTORY の引用一致テスト (`conformance-tests/test_contract_history_register.py`:343) と同時に赤になってよい。同じ文を契約と `spec/CONTRACT_HISTORY.md` (:266・:385) の 2 か所で縛っているためである (v0.5、設計レビュー 2 の B-12)。v0.6 (再確認の指摘 1): 参照クライアントの失敗は 2 種類 (`code` を読んだ失敗 / `code` を持たない解釈しない失敗) で、失敗を固定する行はどちらの種類かを assert する。「例外になる」だけの assert では、失敗の種類を入れ替える変異 (10・11・13・22・23・24) が生き残る。

| # | 単体テストが固定すること | 変異 |
|---|---|---|
| 1 | schema 違反の body (必須キー欠落・未知キー・上限超過) は例外になり、送信 0 回 | 送信前検証の呼び出しを外す |
| 2 | 偽の送信関数が schema 違反の成功応答を返すと例外 | 応答検証を外す |
| 3 | 結合 (D-2a): 接頭辞付き base URL (`https://db.example.invalid/tenant-a/v1` と対の control URL) で接頭辞が残る、control 面は control の base path だけを除く、`/v1` が二重にならない (`operation_catalog_url` は 14) | 接頭辞を落とす / origin に path を足す / 単純連結 / control の base URL から `/v1` だけを除く |
| 4 | placeholder の値に `/` (v0.5: と `?`・`#`・`%`) を含めると encode されて送信記録に出る (D-2) | encode を外す (v0.5: `/` だけを encode する、も加える) |
| 5 | 送信記録の header が scheme (構造化値) と散文由来の header 名から組まれている | scheme を別の語 (例 `Token`) に変える。大小文字だけの変異は使わない: r2db の境界は scheme を大小文字を区別せず比べる (`r2db-api/src/r2db_api/http.py`:400) ので、同じ変異が wire 側では生き残り、単体と wire で判定が割れる |
| 6 | 契約版の照合 (D-10): 偽の送信関数の capability document が別の `contract_version` を宣言すると段 (1) で例外 | 照合を外す |
| 7 | secret の非露出 (D-9): sentinel secret で失敗させた例外の文字列と repr に sentinel が出ない | 失敗メッセージに `Authorization` の値を入れる |
| 8 | `schema_check` の新 keyword (D-7a): keyword ごとに正例と負例を 1 組 (`conformance-tests/test_schema_check.py`) | その keyword の判定を外す |
| 9 | D-6 の AST pin | クライアントに catalog の path を直書きする / 表に無い散文由来リテラルを足す / テストから送信関数を直接呼ぶ |
| 10 | 失敗応答の Content-Type に `; charset=utf-8` が付いても失敗として扱い、`code` を読む (例外が problem の `code` を持つ) (N-13。v0.6 で「`code` を読む」を足した) | parameter を除かずに比べる |
| 11 | problem+json でも JSON でもない応答 (HTML の 404) は例外になる (N-14)。v0.6: 例外は解釈しない失敗の種類で、`code` を持たない。偽の応答は Content-Type を `text/html` とし、本文を response schema に合う成功の JSON にする (23 と同じ形。成功として扱う変異が結果を返して赤になる) | その応答を成功として扱う |
| 12 | 11 の例外の文字列と repr に応答の本文と header が出ない (N-14) | 例外に本文を入れる |
| 13 | problem+json を status 200 で返されても失敗として扱い、`code` を読む (D-2。v0.6 で「`code` を読む」を足した) | status が 2xx なら成功とみなす |
| 14 | 合成の `operation_catalog_url` を宣言させても、送信記録にその URL が出ない (D-2) | 段 (1) の後に `operation_catalog_url` を取りに行く |
| 15 | §4.1 の表の pin: クライアント module の表の key 集合が、テスト module に持つ本書 §4.1 の N 番号の列と一致する (本書の改訂と同じ変更セットで直す)。v0.4: 契約 WP の後は {N-15} だけである (§4.1) | module の表から行を 1 つ消す (v0.4: 表に無い N 番号の行を足す、も加える) |
| 16 | https でなく N-15 の行の例外にも当たらない base URL では送信 0 回で例外 (D-2) | scheme の検査を外す |
| 17 | `versioning.base_path` で終わらない入力 base URL (origin だけ等) では送信 0 回で例外 (D-2) | 末尾の検査を外し、base path の文字数だけ除く |
| 18 | `surfaces.control` を宣言しない capability document の後に control 面の operation を呼ぶと送信 0 回で例外 (D-2) | data の base URL に結合する |
| 19 | surface の判定 (N-19): alias の `audit_query` の項は接頭辞付きの control base URL に結合される。v0.5 (§9.1 の #1・#10): alias の `audit_query` の項は送信 0 回で例外 | surface を path の接頭辞で決める。v0.5: alias を control の base URL に結合する |
| 20 | role の読み取り (v0.4、§9.1 の #8): 偽の capability document の `role` が runtime のとき、catalog の roles が developer だけの operation は送信 0 回で例外 | v0.5 で改めた: catalog の roles と段 (1) の `role` の照合を外す (送信する)。v0.4 の「入口の申告を使う」は申告を参照クライアントに渡さない (§6) ので注入できない |
| 21 | Content-Type (v0.4、§9.1 の #5): body のある要求の送信記録に `media_type` の値の `Content-Type` が出る | header を付けない |
| 22 | 大小文字の違う `Application/Problem+JSON` の失敗応答を失敗として扱い、`code` を読む (v0.5、#6。v0.6 で「`code` を読む」を足した) | media type を大小文字を区別して比べる |
| 23 | Content-Type の無い応答は例外になり、送信記録上は 1 回 (v0.5、#7)。v0.6: 偽の応答の本文は response schema に合う成功の JSON とし、例外は解釈しない失敗の種類で `code` を持たない | header が無いとき JSON として読む |
| 24 | `errors.shape` に合わない problem+json の応答は例外になり、`code` を読まない (v0.5、#7 の追加文。成功側の schema 不一致は 2)。v0.6: 例外は解釈しない失敗の種類で `code` を持たない。偽の応答の本文は `code` を持ち、`errors.shape` が名指す他の key を 1 つ欠く | shape の検証を外して `code` を読む |
| 25 | redirect を追わない (v0.5、#1 の追加文): 偽の送信関数が 3xx と `Location` を返すとき、送信記録は 1 回で、`Location` の宛先への送信は 0 回。応答は #7 の規則で失敗として扱う | 3xx の `Location` へ同じ header で送り直す |

D-7a `schema_check.py` の拡張。現行の `schema_check.py` は、作業列が使う request schema の keyword の一部 (MutationRequest の `maxLength`・`maxProperties`、SchemaOperationRequest の `maxLength`) を実装しておらず、未知の keyword には例外を出す (fail-closed)。作業列が使う request / response schema の keyword をすべて実装する。未知の keyword で例外を出す性質は変えない。同じ変更セットで module docstring (`conformance-tests/schema_check.py`:1-38 の「C-11 の 3 schema が使う keyword の部分集合」) を直す。クライアントが検証する schema の `used_keywords()` が実装済み集合に収まることを、`conformance-tests/test_schema_check.py`:226-245 と同じ形のガードで静的に固定する (例外は instance が通った節点でしか出ないため)。C-11 の判定が変わらないことは §10 で実測する。

D-7 の v0.4 註 (v0.5 で訂正。設計レビュー 2 の B-4): 表の根拠は、契約 WP の後は §4.1 の行ではなく §9.1 の文になる: 10・13・22 は #6、11・23・24 は #7、17・18 は #1、19 は #1・#10、20 は #8、21 は #5。12 は D-9 (K-5)、14 は D-2 のまま、16 は §4.1 の N-15 の行のまま (v0.4 の「12 は #7、14 は #11」は、#7・#11 が述べない性質だったので改めた)。契約の新しい文を固定するテストは契約 WP が持つ (§10)。v0.6 (再確認の指摘 5 (e)): 上の対応に漏れがあった。3・25 も #1、4 は #4 である。

D-7 の v0.7 註 (2026-10-01、作業指示書 `docs/work-orders/WORK_ORDER_R108_REFERENCE_CLIENT_V1.md` 訂正註 5 の 10): D-7 の冒頭の v0.6 註の「失敗は 2 種類」は、実装では次の class に分かれる。`RequestRefused` は送信前の拒否、`ProblemResponse` は `code` を読んだ失敗、`UninterpretedResponse` と `ContractMismatch` はどちらも `code` を持たない解釈しない失敗の側である (`ContractMismatch` は段 (1) の契約版の不一致と `role` の無い文書)。

D-8 クラスと規模。Class D。`security/CONTROL_MAPPING.md` に触れ、wire への入口を両 peer に同名で置くので `_ISOMORPHIC_TARGETS` が増える (台帳 `RM` §9 の 8 の D 行、`RM`:582)。設計レビューは 2 回で、v0.2 が 1 回目の反映、v0.3 がその再確認の反映である。2 回目は依頼者裁定 (Q-1〜Q-4) を反映した版に対して行う (v0.4 註: その版が v0.4 である)。規模 L。実装の着手は台帳 `RM` R-115 の merge 後とする (契約版・条件番号・port 版・launcher が重なるため)。

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
| N-14 | problem+json でない失敗応答 (前段の proxy の 404 等) | 読めない | — | 契約は扱いを定めない。socket の nginx は未知の location に素の 404 を返す (`conformance-tests/socket_harness.py`:325-327) |
| N-15 | TLS | 読める | 散文 | `security.schemes` は「Opaque credential presented over TLS」(`spec/data-service-api.v1.json`:13)。試験 plug は TLS を通らない (§11)。参照クライアントは従うが、試験 plug のための例外を §4.1 に持つ |
| N-16 | 自分の key の role | 読めない | — | key は opaque。`CapabilityDocument.role` (:1345) は required (:1290-1296) に無い任意 field である (両 peer は出している: `r2db-api/src/r2db_api/capabilities_document.py`:190、`MitateDB-api/src/mitatedb_api/capabilities_document.py`:456) |
| N-17 | 前提にする外部標準の範囲 (HTTP・JSON・URI) | 読めない | — | 契約はどの外部標準も名指ししない (RFC の参照が無い)。header の形は :13 の散文、problem+json は :844 の値だけである |
| N-18 | `operation_catalog_url` が surfaces の外にあるとき key を提示するか | 読めない | — | `operation_catalog_url` は surfaces の外を許す (:1389)。`endpoints.operation_catalog` は runtime か developer の認証を要する (:445)。surfaces と違う origin に application の bearer を出すかを述べる文が無い。扱いは Q-4 (v0.3 で Q-2 から分けた) |
| N-19 | catalog の項がどの surface に属するか | 読めない | — | `OperationCatalogEntry` に surface の field は無い (`spec/data-service-api.v1.json`:2041-2056)。control の項の name の `control.` 修飾は生成器の規約で (`tools/contract_catalog.py`:80-87)、契約の文に無い。修飾の無い `audit_query` の項 (`spec/OPERATION_CATALOG.json`:5-20) は control に属し、それは deprecation_note の散文 (`spec/data-service-api.v1.json`:432) にしか無い。契約 JSON の節 (`endpoints` / `control_endpoints`) は構造化値だが、alias 1 項はその節と surface が一致しない |

読めない点は 10 件 (N-1・N-2・N-8・N-11・N-13・N-14・N-16・N-17・N-18・N-19。v0.2 の 8 件に N-11 の判定変更と N-19 を足した)。扱いは Q-1 (N-1)、Q-4 (N-18)、Q-2 (残り 8 件) が決める。v0.4 註 (2026-09-30、依頼者裁定 Q-1 (A1)・Q-2 (A)・Q-4 (A)): 上の表の判定は main c729ab0 の契約 1.12.0 に対するものとして残す。10 件はすべて本項目の契約 WP で契約に入り、§9.1 の文で読めるようになる: N-1 は #1・#2、N-2 は #3、N-11 は #4、N-8 は #5、N-13 は #6、N-14 は #7、N-16 は #8、N-17 は #9、N-19 は #10、N-18 は #11 (N-8・N-16・N-18 の実装側の義務は #12)。v0.5 註 (設計レビュー 2 の A-2): N-1・N-19 の alias (`endpoints.audit_query`) は、#1・#10 では結合規則が URL を組まない項として読む。client は `control_endpoints.audit_query` を呼ぶ。

### 4.1 契約外知識の表

読めない点と、読めるが試験のために従わない点 (N-15) を、クライアントがどの値で埋めるかを列挙する。クライアント module に同じ表を持ち、pin する (D-6、D-7 の 15)。Q-1・Q-2 が (A) 系なら該当行は契約の file:line に置き換わって消え、(B) なら残る。N-15 と N-18 の行は裁定によらず残る。v0.4 註 (2026-09-30): 裁定は Q-1 (A1)・Q-2 (A)・Q-4 (A) である。契約 WP の後に残る行は N-15 だけで、クライアント module の表もその 1 行になる (右列)。左列は契約 WP の前の値として残す。

| # | クライアントが使う値 | v0.4 (契約 WP の後) |
|---|---|---|
| N-1 | operation の surface を N-19 の行で決める。その surface の base URL (data は入力の base URL、control は段 (1) で読む `surfaces.control.base_url`) の末尾からその surface の base path を除き、operation の path 全体を足す (alias の `/v1/audit/query` も control の base URL に結合する)。最初の要求 (capabilities) も同じ規則で入力の base URL に結合する。base URL がその surface の base path で終わらないとき、surface が宣言されていないときは送信せず例外にする (v0.2 の「path の接頭辞で面を決める」は alias を data 面に誤結合するので改めた。再確認の指摘 1) | #1 で読める。表から外す。v0.5: #1 は alias の URL を組まないので、左列の alias の結合は契約 WP の後は行わない (送信せず例外。D-7 の 19) |
| N-2 | `{entity}` に entity 名 (SchemaOperationRequest の `entity` と同じ値) を入れ、percent-encode する | #3 で読める。表から外す |
| N-8 | 要求の Content-Type は `media_type` (`spec/data-service-api.v1.json`:7) の値 | #5 で読める。表から外す |
| N-11 | placeholder の値は常に percent-encode する (`/` を含む予約文字すべて。D-2) | #4 で読める。表から外す |
| N-13 | 応答の Content-Type の media type (parameter を除く) が `errors.content_type` (:844) と一致すれば失敗、そうでなければ JSON として response schema で検証する | #6 で読める。表から外す |
| N-14 | N-13 のどちらにも当たらない応答は例外にする (fail closed)。例外に本文と header を写さない | #7 で読める。表から外す |
| N-15 | https でない base URL には bearer を送らない。例外として、host が loopback か `.invalid` の合成名のときだけ http を許す (試験 plug で走らせるため。§11)。読める要求 (:13) からの逸脱である | 残る (契約に足さない。試験 plug のための逸脱であり、契約の文にすべきものではない) |
| N-16 | どの secret が runtime / developer かは、入口が帯域外で申告した値を使う (§6) | #8 で読める。表から外す (値は段 (1) の `role`。D-4a の v0.4 註) |
| N-17 | HTTP (method・header・media type の parameter)、JSON、URI (percent-encode) を前提にする | #9 で読める。表から外す |
| N-18 | 使わない。`operation_catalog_url` を取りに行かない (D-2) | #11 で読める。表から外す (v0.3 の「裁定によらず残る」を改めた。取りに行かないのは D-2 の範囲の決定であり、契約外の知識ではない) |
| N-19 | catalog の項と method・path が一致する項を契約 JSON の `endpoints` と `control_endpoints` から引き、`control_endpoints` なら control、`endpoints` なら data とする。`endpoints` の項で `deprecation_note` を持つもの (現行は :432 の 1 項) は、その散文により control とする | #10 で読める。表から外す (判定は同名の規則。D-2 の v0.4 註)。v0.5: 同名の項は alias で、#1・#10 により URL を組まない (D-2 の v0.5 註) |

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
- 返す secret は 2 本だが、参照クライアントの 1 インスタンスに渡すのは 1 本である (D-4a)。v0.4 註: どちらが runtime / developer かの申告は参照クライアントに渡さない。テストが、段 (1) で読んだ `role` と申告が一致することを assert する。
- 送信関数の引数と戻り値の形、in-process plug での振る舞いは作業指示書で確定し、実装前に監督へ上げる (`docs/work-orders/OPERATING_CONDITIONS.md` §1.5 の 37)。入口を両 peer に同名で置くので同型性テストの対象である (同 §1.5 の 38、D-8)。
- v0.7 註 (2026-10-01): 入口と送信関数の確定形は作業指示書 `docs/work-orders/WORK_ORDER_R108_REFERENCE_CLIENT_V1.md` の M-1 である。送信関数は、HTTP ライブラリの正規形でない method / URL と、fragment か userinfo を持つ URL を運ばず、送らずに例外にする (同書 訂正註 4 の 2、訂正註 6 の 1)。

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
| SI-00・SI-07 (v0.4、v0.5 で改めた) | 裁定 Q-4 (A) により、契約は `operation_catalog_url` が `versioning.url_composition` の組む URL でないとき application の bearer を出さないこと、bearer を付けた要求の redirect を追わないことを client に求める (§9.1 の #11)。SI-07 と `security/THREAT_MODEL_V1.md` T-01 は credential が盗まれた後の被害の範囲を定める。#11 はその前段の、第三者 (CDN 等) に bearer が渡る経路を狭める。#11 の文が及ぶのは `operation_catalog_url` への要求で、#1 で組む URL への要求の redirect は #1 の redirect の文 (credential を付けた要求の redirect を追わない。v0.6 で「末尾の文」という位置の言い方を改めた。再確認の指摘 5 (c)) が扱う。どちらも client の規則であり、規則に従わない client からの漏れは防がない (v0.4 の「経路を契約から除く」は言い過ぎだったので改めた。設計レビュー 2 の A-3)。どの SI の文も変えず、新しい不変条件は足さない。参照クライアントは `operation_catalog_url` を取りに行かないので (D-2)、本条件はこの性質を wire で示さない (§11) |

新条件 (仮) の SI 列は C-28 と同じ SI-05、SI-09、SI-10、SI-11、SI-14 を見込む。公開リポジトリ規律 (`docs/work-orders/OPERATING_CONDITIONS.md` §1.9 の 60) により、文書・テスト・失敗メッセージには合成値と `example.invalid` だけを使う。

v0.7 註 (2026-10-01): §9.1 の #12 の (b) の Evidence は `security/CONTROL_MAPPING.md` の SI-06 の Common 節に置いた (監督裁定、作業指示書 `docs/work-orders/WORK_ORDER_R108_REFERENCE_CLIENT_V1.md` 訂正註 6 の 3)。上の表の「SI-03・SI-06」の行の「本項目は新たに検証しない」は、C-19 に足した test (`test_c19_data_documents_declare_a_role`) が 6 adapter で data 面の capability document の `role` を見る、と読み替える。

## 8. 却下した代替案

| 案 | 却下の理由 |
|---|---|
| 既存 adapter を catalog 駆動に書き換える | K-6 に反し、6 plug 全部の adapter に触れる。参照クライアントが通れば別項目の候補だが、本設計では起票しない |
| OpenAPI / SDK を生成する | K-3 に反する。`spec/README.md`:11-14 が OpenAPI を派生・非正本としている |
| socket ×2 だけで回す | 依頼者裁定 U-3 が採った (c) 案の定義「wire plug (http ×2、socket ×2)」(`docs/design/PHASE11_MIN_COMMON_PROFILE_V1.md`:506) に反する |
| `tools/` に置く | 完了ゲート (root suite) が `tools/tests` を含まない。証明は conformance に置く |
| real-server launcher (別プロセス) で回す | 裁定の plug 集合と違う。将来の追加候補である |

## 9. 依頼者判断待ち (v0.4: 裁定済み)

以下の問い・表・推奨は裁定前の記録として残す (`docs/work-orders/OPERATING_CONDITIONS.md` §1.7 の 51、§1.8 の 56)。裁定は各問いの【裁定】に逐語で置き、再審議しない。

Q-1 N-1 (base URL と path の結合規則) をどう決めるか。契約に規則は無いが、両 peer・runbook・C-19・C-26 は接頭辞を保つ結合を既に持っている (§4 N-1)。どの案でも `operation_catalog_url` は結合の対象外である (宣言された URL をそのまま使う。surfaces の外の origin に key を出すかは N-18・Q-4)。catalog の項から surface を読めない点 (N-19) は Q-2 が扱う。契約版の列は `versioning.compatibility` (`spec/data-service-api.v1.json`:33) による見込みである。

| 案 | 内容 | 帰結 | 契約版 |
|---|---|---|---|
| (A1) 監督の推奨 | 現物の規則を契約に書く。結合先は path の接頭辞ではなく operation の属する surface で決める (`control_endpoints` の項と alias の `endpoints.audit_query` は control、それ以外の `endpoints` の項は data)。要求 URL はその surface の base_url から末尾のその surface の base path (data は `versioning.base_path`、control は `versioning.control_base_path`) を除き、path 全体を足したものとする。入力の base URL は `surfaces.data.base_url` の形 (base path で終わる) とし、最初の capabilities もこの規則で呼ぶ。base path で終わらない base_url は結合せず、宣言されない surface の operation は呼ばない (fail closed。`surfaces.control` を宣言しない配備では control 面の operation は呼べない)。`operation_catalog_url` は宣言された URL をそのまま使う例外であることを同じ文で述べる。:1385 の「appending a path」の文はこの規則を指す形に直す | peer の挙動の変更は無いが、版の宣言と packaged 写しは変わる (§10 の契約 WP)。成文化になるのは data surface の結合 (両 peer の `derive_operation_catalog_url`) と alias の置き場 (:432 と両 peer の `control_http.py` の 2 route) である。control surface の結合は peer に実装が無く、両 peer の surfaces 検証 (`platform_declarations.py`) と整合する規則の新設である。接頭辞付きの配備でも成り立ち、catalog の形を変えない。入力 base URL の文を含むので §4.1 の N-1 の行は契約の file:line に置き換わる。N-19 は残る | minor |
| (A2) | origin 規則を契約に足す。「path は origin からの絶対 path であり、base_url の origin に結合する」。base_url の path 部分が base_path と完全に一致することも義務にする。:1385 の文を直す | 両 peer の接頭辞対応 (`operation_catalog.py` の結合、surfaces 検証) と runbook の接頭辞付き配備の記述を撤回させる | minor (obligations に entry を足す) か major (:33 の semantic change に当たる) かは未判定 |
| (B) | 契約は変えず、参照クライアントの結合規則を本書 §4.1 にだけ書く | 契約の欠落が残る。§4.1 の N-1 の行が残り、証明は契約と本書 §4.1 に対するものになる | なし |
| (C) | catalog と endpoints の path を base_path 相対に変える | :33 の「removal or semantic change requires a new major version」に当たる。両 peer の `derive_operation_catalog_url` の assert (`path.startswith(base_path)`) が落ちる。散文中の絶対 path (`versioning.discovery`・`control_discovery`・`version_binding` の `/v1/…`・`/control/v1/…`) と食い違う。現行でも alias の `audit_query` の 1 項は path (`/v1`) と surface (control) が一致しないが、(C) では canonical の `audit_query` と `control.audit_query` も同じ `/audit/query` になり、path で区別できなくなる (catalog の項に surface の field は無い。N-19) | major |

(A1) の文案 (surface を path の接頭辞ではなく operation の所属で決め、その surface の base path だけを除く。v0.2 の文案は alias を data の base_url に結合したので改めた): 「Each operation belongs to one surface: every entry in control_endpoints belongs to the control surface, and so does endpoints.audit_query, which its deprecation_note places on the control surface's own host; every other entry in endpoints belongs to the data surface. The base URL a client is given is the deployment's surfaces.data.base_url, and the client reaches GET capabilities from it by the rule that follows. To call an operation, a client takes the base_url of the operation's surface, removes that surface's own base path from its end -- versioning.base_path for the data surface, versioning.control_base_path for the control surface -- and appends the operation's whole path, so any prefix ahead of the base path is kept. A base_url that does not end with its surface's base path is not joined, and an operation of a surface the capability document does not declare -- the control surface where surfaces.control is omitted -- is not called: the client stops rather than guessing. operation_catalog_url is not formed this way: a client uses it exactly as declared.」

【裁定】依頼者裁定 (2026-09-30)。逐語: 「Q-1〜Q-4 はすべて監督の推奨どおりで進めてください」。本問いは (A1)。反映先: §9.1 の #1・#2、§9.2、§4 と §4.1 の v0.4 註、D-2 の v0.4 註。

v0.5 註 (2026-09-30、設計レビュー 2 の A-1・B-10・A-2、監督裁定): §9.1 の #1 は上の (A1) の文案を 2 点直した。(i) 「client が受け取る base URL は surfaces.data.base_url」を「その credential の面の base_url」(application credential なら data、control / audit credential なら control) に直した。control / audit の credential しか持たない client を締め出し、:1385 の「a client holding either base URL」と食い違っていたためである。(ii) alias (`endpoints.audit_query`) を control の base URL に結合する規則をやめ、結合規則は alias の URL を組まず、client は `control_endpoints.audit_query` を呼ぶ形にした (:432 が canonical を勧めている)。control の base URL が `<origin>/control/v1` の co-host 配備では、alias を結合した URL が data 側の stub に届くためである (§11)。server 側の義務と alias の配信は変えない。(ii) は次の依頼者裁定が承認した方向 (alias の規則を新しい文で言い直さない) の範囲にある。v0.6 註 (再確認の指摘 5 (a)・9): #1 は (A1) の文案を 3 点直したものである。上の (i)・(ii) と、(iii) credential を付けた要求の redirect を追わない文 (Q-4 の v0.5 註) である (v0.5 の「2 点」は数え漏れ)。(ii) の細部 (結合規則は alias の URL を作らず、client に canonical を呼ばせる) と 3 点の修正は、依頼者に報告済み (2026-09-30)。(ii) が上の方向の範囲にあるとするのは監督の判断である。

依頼者裁定 (2026-09-30、alias の扱い)。監督の案: 「新しい文では別名の規則を言い直さず既存の注記への参照にとどめ、この一致は R-118 (別名の保持期限の食い違い) に追記する」。依頼者の逐語: 「その案で良いです」

Q-2 §4 で「読めない」となった点のうち Q-1 (N-1) と Q-4 (N-18) の外の 8 件を、本項目で契約に足すか、別起票にするか。足す文の趣旨と契約版の見込みは次のとおり。

| # | 契約に足す 1 文の趣旨 | 契約版の帰結 (見込み) |
|---|---|---|
| N-2 | path の placeholder には、その名の値 (`{entity}` は entity 名、control 面は各 ID) を入れる | minor (定義の追加) |
| N-8 | 要求 body と成功応答の Content-Type は `media_type` (:7) である | minor (peer への新しい義務になるかは作業指示書で実測) |
| N-11 | placeholder の値は URI の percent-encode をして入れる (N-17 の外部標準に拠る) | minor |
| N-13 | 応答の Content-Type の media type (parameter を除く) が `errors.content_type` と一致すれば失敗、そうでない JSON 応答は成功である | minor (両 peer の 2 形はどちらも規則に収まる) |
| N-14 | 失敗でも成功でもない応答 (前段の proxy の応答等) は、client が中身を解釈せず失敗として扱う | minor (client 側の文) |
| N-16 | `CapabilityDocument.role` を required にする (v0.5: 改めた。下の v0.5 註) | minor (`version_binding` の obligations に entry を足す。両 peer は既に出している) |
| N-17 | 前提にする外部標準 (HTTP・JSON・URI) を名指しする | minor |
| N-19 | 派生 catalog の項が属する surface を示す (name の `control.` 修飾は `control_endpoints` 由来であること、修飾の無い `audit_query` は control に属すること) | minor |

- (A) 本項目で足す (1 回の契約版上げにまとめる)。§4.1 の該当行は契約の file:line に置き換わる。監督の推奨。
- (B) 列挙だけして別起票。§4.1 の該当行が残り、証明は契約と本書 §4.1 に対するものになる。

【裁定】依頼者裁定 (2026-09-30)。逐語: 「Q-1〜Q-4 はすべて監督の推奨どおりで進めてください」。本問いは (A)。反映先: §9.1 の #3〜#10・#12、§9.2、§4 と §4.1 の v0.4 註、D-4a・D-7 の v0.4 註、§10 の契約 WP。

v0.5 註 (監督裁定 2026-09-30、設計レビュー 2 の B-7。依頼者に報告済み): 上の表の N-16 の「required にする」を、「schema の required は変えず `version_binding` の義務として書く」(§9.1 の #8 と #12 の (b)) に改めた。理由: 旧版を宣言する実装の文書を遡って縛らないため。`surfaces` (1.6.0)・`operation_catalog_url` (1.9.0) の先例と同じ形である (§9.2 の 8)。

Q-3 作業列の範囲。

- (A) C-28 と同じ 1 周のみ。監督の推奨。
- (B) common_baseline の全 operation を網羅する表駆動に広げる (規模が上がる)。

【裁定】依頼者裁定 (2026-09-30)。逐語: 「Q-1〜Q-4 はすべて監督の推奨どおりで進めてください」。本問いは (A)。反映先: §3 と §5 は変えない (作業列は C-28 と同じ 1 周のまま)。

Q-4 N-18: surfaces の外の origin にある `operation_catalog_url` に application の key を出すか。安全上の選択なので Q-2 から分けた (v0.3)。参照クライアントは `operation_catalog_url` を取りに行かない (D-2) ので、Q-4 は契約の文だけの問いであり、本項目の証明には影響しない。現行は (B) の形である: 契約は URL を data surface の外 (CDN 等) に置くことを許し (`spec/data-service-api.v1.json`:1389)、`operation_catalog` は runtime か developer の認証を要する (:445・:447-450)。C-29 の段 (ii) は宣言された URL に bearer を付けて dial する (`conformance-tests/test_c29_operation_catalog_url.py`:167)。

| 案 | 内容 | 帰結 | 契約版 |
|---|---|---|---|
| (A) 監督の推奨 | key を出すのは URL の origin が data surface の origin と一致するときだけ。外の origin には key なしで取りに行く | 配る側が認証なしで配る義務を負う。`operation_catalog` の認証要求 (:445・:447-450) とぶつかるので、外の origin で配る文書には認証を課さない旨を足す必要がある | 未判定 (認証の意味を変えるのが :33 の semantic change に当たるか) |
| (B) | 宣言された URL には常に key を出す (現行の形) | 第三者 origin に application の bearer が出る。現行の契約と C-29 は変わらない | minor (現行の形を明記する文) |
| (C) | 契約は決めず別起票 | N-18 は契約の欠落として残る | なし |

【裁定】依頼者裁定 (2026-09-30)。逐語: 「Q-1〜Q-4 はすべて監督の推奨どおりで進めてください」。本問いは (A)。反映先: §9.1 の #11・#12、§9.2 (表の「未判定」はここで minor と判定した)、§7、§11。

v0.5 註 (2026-09-30、設計レビュー 2 の A-3・A-4・A-8、監督裁定): §9.1 の #11 は、(A) の「origin が一致するときだけ key を出す」を「宣言された URL が `versioning.url_composition` の規則で `endpoints.operation_catalog` について組む URL と一致するときだけ出す」に厳しくした。同じ origin の別 path (同じ host の LB が振る静的配布等) にも key を出さないため、また origin の正規化 (既定の port・大小文字) の解釈が分かれないためである。あわせて、key を付けた要求の redirect を追わないことを足した。趣旨は (A) と同じで、面の外に key を出さない。同じ穴は data 面・control 面の operation (#1 で組む URL) にもあるので、redirect を追わない規則は #1 にも 1 文で置いた (監督裁定 2026-09-30、起草時の指摘。client の規則であり server の義務は足さないので minor のまま。単体テストは D-7 の 25)。

### 9.1 契約 (仮) の変更案 (v0.4、v0.5 で改訂)

裁定 Q-1 (A1)・Q-2 (A)・Q-4 (A) の帰結。1 回の契約版上げにまとめる (Q-2 (A))。`<V>` は新しい契約版、`<V-1>` はその直前の版、`<N>` は従属判断の番号で、いずれも (仮) である (台帳 `RM` R-115 が次の契約版と次の条件番号を持つので、merge 直前に main を読んで振る。§0)。現行の文の行番号は main 168f25f の `spec/data-service-api.v1.json` である。英文は確定案で、作業指示書の確定文ファイルに写し、以後言い換えない (`docs/work-orders/OPERATING_CONDITIONS.md` §1.5 の 35)。#1 は §9 Q-1 の (A1) の文案を v0.5 で 2 点直したものである (Q-1 の v0.5 註)。v0.5 で直した文は #1・#7・#10・#11・#12 である (設計レビュー 2、§14)。v0.6: #1 の修正は 3 点である (2 点は Q-1 の v0.5 註、redirect の文は Q-4 の v0.5 註。Q-1 の v0.6 註)。v0.6 で直した文は #7・#11・#12 である (再確認、§15)。

| # | JSON path | 現行の文 | 新しい文 (英文、確定案) | N | obligations |
|---|---|---|---|---|---|
| 1 | `versioning.url_composition` (新しい key) | なし (関係する現行の文は :31-32・:1385・:432) | Each operation belongs to one surface: every entry in control_endpoints belongs to the control surface, and every entry in endpoints to the data surface, except endpoints.audit_query, the alias its deprecation_note describes: this rule forms no URL for it, and a client reaches that operation at control_endpoints.audit_query instead. The base URL a client is given is the base_url of the surface its credential is for -- surfaces.data.base_url for an application credential, surfaces.control.base_url for a control or audit credential -- and the client reaches that surface's capability document (endpoints.capabilities or control_endpoints.control_capabilities) from it by the rule that follows. To call an operation, a client takes the base_url of the operation's surface, removes that surface's own base path from its end -- versioning.base_path for the data surface, versioning.control_base_path for the control surface -- and appends the operation's whole path, so any prefix ahead of the base path is kept. A base_url that does not end with its surface's base path is not joined, and an operation of a surface the capability document does not declare -- the control surface where surfaces.control is omitted -- is not called: the client stops rather than guessing. A client follows no redirect in answer to a request that carries a credential, at any URL this rule forms. operation_catalog_url is not formed this way: a client uses it exactly as declared. | N-1 | 足さない |
| 2 | `schemas.CapabilityDocument.properties.surfaces.description` (値の 1 文を置き換える) | :1385 の「Neither URL ends in a trailing slash, so that appending a path to it yields exactly one separator.」 | Neither URL ends in a trailing slash; a client forms the URL of an operation from them as versioning.url_composition states, not by appending the operation's path to them. | N-1 | 足さない |
| 3 | `endpoint_fields_note.path` (新しい key の 1 文目) | なし (:627 の `roles` と並ぶ) | A placeholder in braces in path is filled with the value this contract gives the field of the same name: {entity} with an entity name, the value EntityDescriptor.entity and SchemaOperationRequest.entity carry, and {application_id} and {credential_id} with an application_id and a credential_id as the control endpoints return them. | N-2 | 足さない |
| 4 | `endpoint_fields_note.path` (2 文目) | なし | The value is percent-encoded as URI syntax (external_standards) defines it before it is placed in path, so that every character outside the unreserved set is encoded, '/' included; an identifier, being ASCII letters, digits and underscore, is unchanged by it. | N-11 | 足さない |
| 5 | `media_type_note` (新しい最上位 key) | :7 (`media_type` は値だけ) | media_type is the media type of every request body a client sends, named in that request's Content-Type header, and of every successful response an implementation returns; a failure is returned as errors.content_type instead (errors.response_classification). | N-8 | 足す (#12 の (a)) |
| 6 | `errors.response_classification` (新しい key の 1 文目) | なし (関係する現行の文は :844・:872) | A client classifies every response by the media type of its Content-Type header, parameters such as charset ignored and type and subtype compared case-insensitively as HTTP defines: errors.content_type is a failure, read by its code; media_type is a success, read against the operation's response schema. HTTP status decides neither (http_status_note). | N-13 | 足さない |
| 7 | `errors.response_classification` (2〜3 文目) | なし | A response of any other media type, or of none -- one an intermediary ahead of the service returns, for instance -- is a failure the client does not interpret: it reads neither a code nor a result from it. So is a response of media_type that the operation's response schema does not accept, and one of errors.content_type whose body lacks a key errors.shape names or carries one with a value of another type than errors.shape names for it. | N-14 | 足さない |
| 8 | `schemas.CapabilityDocument.properties.role.description` (新しい key。`required` は変えない) | :1345-1352 (enum だけ。:1290-1296 の required に無い) | The role, from security.roles, of the credential this document was fetched with. A secret is opaque (security.schemes), so this is where a client learns which endpoints' roles its credential satisfies. Required of an implementation declaring <V> or higher; this schema's required list does not name it, so that a document an implementation declaring a lower version returns stays valid. | N-16 | 足す (#12 の (b)) |
| 9 | `external_standards` (新しい最上位 key) | なし | This contract is read against three external standards: HTTP semantics (RFC 9110) for methods, header fields, and media types with their parameters; JSON (RFC 8259) for every request and response body; and URI syntax (RFC 3986) for base URLs, paths and percent-encoding. Where this contract states a rule those standards leave open, this contract's rule applies. | N-17 | 足さない |
| 10 | `definitions.OperationCatalogEntry.description` (新しい key。v0.4 の `schemas.` は誤り) | なし (:2041-2056 に description は無い。`definitions` は :1763) | Each entry is derived from one entry of endpoints or of control_endpoints. An entry derived from control_endpoints carries that entry's name prefixed with control.; an entry derived from endpoints carries that entry's name unchanged. An entry of endpoints whose name control_endpoints also carries is that control endpoint's alias (endpoints.audit_query.deprecation_note); versioning.url_composition forms no URL for it, and a client reaches the operation at the entry derived from control_endpoints. Every other entry derived from endpoints belongs to the data surface, and every entry derived from control_endpoints to the control surface. | N-19 | 足さない |
| 11 | `schemas.CapabilityDocument.properties.operation_catalog_url.description` (値の末尾に足す。既存の文は変えない) | :1389 | Where the URL is, character for character, the one versioning.url_composition forms for endpoints.operation_catalog, what it reaches is that endpoint, and a client presents its application credential there as that entry's auth and roles require and follows no redirect in answer to a request that carries it. Where it is any other URL, a client presents no credential there, and a deployment that names such a URL serves the document there, as media_type, to a request that carries none: the document is this contract version's derived operation catalog, the same for every application and every deployment declaring that version, so serving it without a credential discloses nothing this contract does not already publish. Against a deployment declaring a version lower than <V>, such a URL may require a credential a client will not present there; the document is then the derived operation catalog of the version that deployment declares (1.9.0's obligation (b)), which a client holding that version of this contract derives for itself rather than fetching it. endpoints.operation_catalog's auth and roles are unchanged; they govern that endpoint at the URL versioning.url_composition forms for it. | N-18 | 足す (#12 の (c)) |
| 12 | `versioning.version_binding` (直前の版 `<V-1>` の段落 (現行は 1.12.0 の文) の後、最後の「A peer's version-flip」の文の前に足す) と `versioning.obligations` (:38-265 に entry を 1 つ足す) | :37 | Only an implementation declaring <V> or higher additionally claims conformance to the obligations <V> introduces (subordinate ruling <N>). Those obligations are unconditional in the same sense as every obligation enumerated above -- they bind simply by declaring <V>, independent of any capability's own status: (a) every successful response it returns carries media_type as the media type of its Content-Type header (media_type_note); (b) every capability document it returns, on either surface, carries role (CapabilityDocument.properties.role); and (c) where its operation_catalog_url differs, character for character, from the URL versioning.url_composition forms for endpoints.operation_catalog, a request that carries no credential receives the document there, as media_type (CapabilityDocument.properties.operation_catalog_url). What else <V> adds -- versioning.url_composition, the sentence it rewrites in CapabilityDocument.properties.surfaces, endpoint_fields_note.path, errors.response_classification, external_standards and definitions.OperationCatalogEntry's description -- states how a client forms a request and reads a response, and holds an implementation to no behavior beyond these three. <V> requires no implementation to refuse a request it accepted under <V-1>: a request valid under <V-1> stays valid. An implementation still declaring <V-1> is not held to any <V>-only obligation retroactively. | N-8・N-16・N-18 | entry: `{"version": "<V>", "subordinate_ruling": <N>, "unconditional": ["successful_responses_carry_media_type", "capability_document_carries_role", "other_url_operation_catalog_served_without_credential"], "conditional": []}` (v0.5: 3 つ目の名前を v0.4 の `off_origin_…` から改めた。(c) の分け目が origin でなくなったため) |

obligations に entry を足す行は、実装に新しい挙動を求める文 (#5・#8・#11) だけである。#1・#2 に足さない根拠: 実装側の意味 (宣言した base_url でその面に届く) は 1.6.0 の義務 (a) (:37) と :1385 の既存の文が既に持ち、#1 は client が URL を組む規則である。#3・#4・#6・#7・#9・#10 も client の読み方の文で、実装側は既存の文 (:844 と #5) が持つ。

N-19 の形の比較。(i) 散文で足す (#10): `OperationCatalogEntry` の schema に description を足すだけで、派生 catalog の形は変わらない (再生成で変わるのは版の `contract_version` だけ)。(ii) catalog の項に surface の field を足す: `OperationCatalogEntry` (閉じた schema、:2041-2056) の properties と required、生成器 (`tools/contract_catalog.py`:60-71)、両 peer の packaged 写し、C-29 の byte 一致の相手が変わり、既存版の catalog を読む client には無い field になる。(i) を採る。根拠: 参照クライアントの入力 1 は契約 JSON を含み、項の出所の節 (`endpoints` / `control_endpoints`) は既に構造化値である。節と surface が一致しないのは alias 1 項だけで、#10 はそれを「`control_endpoints` と同名の `endpoints` の項」という構造で読める規則にする。alias は削除の予定がある (台帳 `RM` R-118) ので、field を足すと、1 項のためだけに派生物の形を恒久に変えることになる。

### 9.2 契約版の帰結 (v0.4、v0.5 で再判定)

判定の軸は `versioning.compatibility` (:33) の「Additive fields and capabilities are allowed; removal or semantic change requires a new major version.」である。先例: 1.11.0 (従属判断 16) は r2db の拒否コードを変えさせる義務を version_binding の下の minor とし、1.12.0 (従属判断 17) は実装の現物に合わせる文言の変更を「client が計画に使える保証が変わらない」ことを根拠に minor とした (`spec/CCR_DISPOSITION.md` の 16・17)。12 件とも minor に収まり、契約版は 1 つの minor 版 `<V>` である。v0.5 で直した #1・#7・#10・#11・#12 を直した後の文で判定し直し、判定は変わらない (各行の v0.5)。

| # | minor の根拠 |
|---|---|
| 1・2 | data 側の結合は両 peer の `derive_operation_catalog_url` の成文化、alias の置き場は :432 と両 peer の `control_http.py` の成文化である (§4 N-1)。control 側の結合は両 peer の surfaces 検証と整合する規則の新設である。現行の「appending a path」を字義どおりに従うと `/v1` が二重になるので、正しく動く client がこの文に依っていたことは無い。trailing slash が無いという保証は残す。実装の挙動は変わらない。v0.5: #1 に足した 2 点も client の規則である。credential の面の base_url を与える文は :1385 の「a client holding either base URL」と同じ前提を述べる。alias の URL を組まない文は、alias を消さず (server の義務と alias の配信は変えない)、client に :432 が既に勧める canonical を呼ばせるだけである。実装の挙動は変わらない。v0.6 (再確認の指摘 5 (b)): redirect を追わない文 (#1 の redirect の文) も client の規則で、server の義務を足さない |
| 3・4 | placeholder の値の定義と encode の追加。identifier は encode で変わらない (:756) ので、既存の client が送る URL も実装が受ける URL も変わらない |
| 5 | 両 peer の成功応答は既に `application/json` である (`r2db-api/src/r2db_api/http.py`:520 と各 handler の `JSONResponse`、`MitateDB-api/src/mitatedb_api/http.py`:676 と各 handler の `JSONResponse`)。義務は #12 の (a) として `<V>` の宣言にだけ掛かる。client に header を送らせるが、実装に拒否を求めないので、旧来の要求は有効なまま |
| 6・7 | client の読み方の文。両 peer の失敗応答の 2 形 (§4 N-13) はどちらも規則に収まる。両 peer は app 内の失敗を problem+json で返す (`r2db-api/src/r2db_api/http.py`:373-377 を control 面も使う (`r2db-api/src/r2db_api/control_http.py`:102・:484)、`MitateDB-api/src/mitatedb_api/http.py`:573-576、`MitateDB-api/src/mitatedb_api/control_http.py`:237-240)。v0.5: #7 に足した文 (schema に合わない応答を解釈しない) も client の読み方の文で、実装が返す応答は既存の schema と `errors.shape` に従う。v0.6 (再確認の指摘 3): `errors.shape` は key と型の対応表で JSON Schema ではないので、#7 の 3 文目を「shape が名指す key を欠くか、shape の型と違う値を持つ」に直した (名指さない key は拒まない)。両 peer の problem+json は 5 key を文字列 4 つと object 1 つで返し (`r2db-api/src/r2db_api/errors.py`:19、`MitateDB-api/src/mitatedb_api/http.py`:117、`MitateDB-api/src/mitatedb_api/control_http.py`:140)、適合する |
| 8 | client から見ると、常に来る field が 1 つ増えるだけである。義務は #12 の (b) として `<V>` の宣言にだけ掛け、schema の required は変えない。先例: `surfaces` (1.6.0) は義務を version_binding に置いて required に足していない (`conformance-tests/test_contract.py`:1575-1576)。`operation_catalog_url` (1.9.0) も同じ形である (:1389)。両 peer は data と control の両方の文書で既に出している (`r2db-api/src/r2db_api/capabilities_document.py`:190、`r2db-api/src/r2db_api/control_plane.py`:664、`MitateDB-api/src/mitatedb_api/capabilities_document.py`:456、`MitateDB-api/src/mitatedb_api/control_plane.py`:1630) |
| 9 | 既に前提にしていた標準を名指すだけで、実装に義務を足さない |
| 10 | 生成器の既存の規約 (`tools/contract_catalog.py`:80-87) と alias の既存の記述 (:432) の成文化。派生 catalog の形は変わらない。v0.5: path を `definitions.` に直しても、足すのは annotation の description だけで、派生 catalog の形は変わらない |
| 11・12 | Q-4 (A) の判定 (v0.3 は「未判定」)。下の 3 点により minor と判定する。v0.5: 分け目を URL の一致にし、redirect を追わない文、旧版の配備についての文、(c) の `as media_type` を足した。前の 2 つと旧版の文は client の規則である。(c) の義務が掛かる URL は、同じ origin の別 path の分だけ広がるが、`<V>` の宣言にだけ掛かり、両 peer の既定値 (`derive_operation_catalog_url`、`r2db-api/src/r2db_api/operation_catalog.py`:39-70) は #1 が組む URL そのものなので、6 plug の判定は変わらない。v0.6 (再確認の指摘 2・4): 一致の比べ方を character for character とし、旧版の配備の文を「その配備が宣言する版の派生 catalog を client が自分で導く」に直した。どちらも client の規則と (c) の掛かる範囲の明確化で、6 plug の宣言値は #1 が組む URL と文字列で一致するので判定は変わらない |

Q-4 (A) の判定。
- 宣言の経路: 両 peer は surfaces の外の URL を宣言する経路を持つ。既定は `derive_operation_catalog_url` による data surface と同じ origin の URL で、上書き (`r2db-api/src/r2db_api/main.py`:228-234、`r2db-api/src/r2db_api/control_main.py`:589-597、`MitateDB-api/src/mitatedb_api/config.py`:250・:286-288、`MitateDB-api/src/mitatedb_api/control_composition.py`:66-71) は絶対 URL であることしか見ない。上書き先 (runbook の言う CDN。`r2db-api/deploy/DEPLOYMENT_RUNBOOK.md`:633、`MitateDB-api/docs/cloud-run-cloud-sql.md`:1239-1245) で文書を配るのは peer のコードではなく配備である。peer 自身が data surface で配る `operation_catalog` は変わらない。
- 壊れるもの: 無い。6 plug はすべて data surface と同じ origin の URL を宣言する (`r2db-api/conformance/conformance_adapter_r2db.py`:116・:127、`r2db-api/conformance/conformance_adapter_r2db_http.py`:948・:960、`r2db-api/conformance/conformance_adapter_r2db_socket.py`:543・:570、`MitateDB-api/conformance/conformance_adapter_mitatedb.py`:107・:116、`MitateDB-api/conformance/conformance_adapter_mitatedb_http.py`:131・:154、`MitateDB-api/conformance/conformance_adapter_mitatedb_socket.py`:384・:418)。C-29 の段 (ii) は同じ origin に bearer を付ける (`conformance-tests/test_c29_operation_catalog_url.py`:167) ので #11 に適う。repo の中に外の origin へ key を出す client は無い。旧来の client が外の origin に key を付けても、#11 は配る側に key の無い要求へ配ることを求めるだけで key 付きの要求を拒ませないので、その要求は通る。逆に、外の origin で認証を求める旧版の配備に新しい client が当たると取得できないが、その文書は契約の派生 catalog と byte 一致である (1.9.0 の (b)) ので、client は契約から同じものを持つ。v0.6 (再確認の指摘 2): 1.9.0 の (b) の相手はその配備が宣言する版の派生 catalog であり、`<V>` の catalog ではない。client はその配備が宣言する版の契約から同じものを導く。
- 意味: `endpoints.operation_catalog` の auth と roles (:445・:448-450) は変えず、data surface の origin で配る operation に掛かることを #11 で明記する。外の origin は、同版の全配備で同じ公開済みの文書の写しを配る場所として書く。1.9.0 の文は消さずに同じ値の末尾に足すので、1.9.0 の文字列ピン (`conformance-tests/test_contract.py`:1811) も保たれる。外の origin で credential を求めない義務は #12 の (c) として `<V>` の宣言にだけ掛かり、1.11.0 と同じ version_binding の下の新しい義務である。

## 10. WP 分割の見込み

確定は作業指示書 (Change Set Manifest) で行う。各 WP の完了条件と変異の対応は `docs/work-orders/OPERATING_CONDITIONS.md` §1.5 の 40 に従う。v0.4: 契約 WP を最初に置く。クライアント WP の §4.1 の表と D-7 の根拠は契約 WP の後の契約を指す。

| WP (仮) | 内容 | 主に触るパス |
|---|---|---|
| 契約 (v0.3 の「Q-1 (A1) / (A2) / (C)・Q-2 (A) のときだけ」は裁定 Q-1 (A1)・Q-2 (A)・Q-4 (A) で満たされ、v0.4 で確定) | §9.1 の 12 件の文と obligations の entry、`contract_version` と派生 catalog の再生成、両 peer の宣言 4 か所を同一コミットで `<V>` にする (現行は `r2db-api/src/r2db_api/capabilities_document.py`:88、`r2db-api/src/r2db_api/control_plane.py`:656、`MitateDB-api/src/mitatedb_api/capabilities_document.py`:145、`MitateDB-api/src/mitatedb_api/control_plane.py`:1617。R-115 の後に読み直す)。確定文を逐語 assert する文字列ピンを 12 件すべてに置く (`docs/work-orders/OPERATING_CONDITIONS.md` §1.5 の 35)。既存のピンの差し替え (v0.5 で漏れを足した。設計レビュー 2 の B-1・B-2): `conformance-tests/test_contract.py` の :1460 (#2、surfaces の文を全値で)、:1943 (#3、`endpoint_fields_note` の key 集合を 4 つに)、:283・:401-404 (#10、dict 一致の `FIXED_1_9_0_DEFINITION_OPERATION_CATALOG_ENTRY` に description を足す。版を移すピンの規律、:1805-1808 の先例)、:1167-1184 (#12、1.12.0 の文の between と `versions[-1] == "1.11.0"`。#12 を `<V-1>` の段落の後に置くので右端が動く)、:89 の `contract_version` と両 peer の tests の版 literal (main 168f25f で `r2db-api/tests/` 4 ファイル 10 か所、`MitateDB-api/tests/` 4 ファイル 8 か所。R-115 の後に数え直す)。記録: `spec/CONTRACT_HISTORY_MANIFEST.json` の `schemas.CapabilityDocument.properties.surfaces.description` (:96) に whole-value `rewrite` (#2。1.12.0 の先例は `spec/CONTRACT_HISTORY.md`:236)、`spec/CONTRACT_HISTORY.md` の `versioning.version_binding` の節 (:385。unstripped) の引用の更新と Revision note (#12)、`spec/CCR_DISPOSITION.md`、`spec/README.md` の版の段落 (:21-31 の形)、台帳 `RM`:39 の G-2 / G-3 行の版。ピンの変異は、確定文の 1 語を `spec/` と両 peer の packaged 写しの 3 か所で同じに変える形にする (写しの byte 一致テストを同時に赤にしない)。#2・#12 の変異は CONTRACT_HISTORY の引用一致テストと同時に赤になってよい (D-7、B-12)。peer の挙動の変更は要らない見込み (下の実測で確かめる) | `spec/`、両 peer の packaged 写しと宣言 4 か所と `tests/` の版 literal、`conformance-tests/test_contract.py`、`docs/design/ROADMAP_POST_PHASE7_V1.md` |
| port | wire への入口 (§6)、4 plug の実装、同型性テストの登録 | `conformance-tests/adapter.py`、両 peer の `conformance/`、両 peer の同型性テスト |
| クライアント | `reference_client.py`、§4.1 の表、D-6 の AST pin と散文由来リテラルの表、D-7 の単体テスト、`schema_check.py` の拡張・docstring・keyword ガード (D-7a) | `conformance-tests/` |
| 条件 | 新条件 (仮) のテスト、`CONDITIONS.md` の行と `CONDITIONS_HISTORY.md` の節、`security/CONTROL_MAPPING.md` の証拠、台帳 `RM` §0.1.1 の G-2 / G-3 行 (`RM`:39・:56) の条件数と表記の内訳。v0.5 (設計レビュー 2 の B-3): #12 の新しい義務の常設の証拠として、(b) の `role` は capability document を取れる全 plug (6 つ) の data 面で、新条件の作業列とは別の段として常設で見る (既存条件に足すか新条件の段にするかは作業指示書で決める。control 面の capability document を port が出せるかも作業指示書で実測する)。(a) の成功応答の Content-Type は wire plug 4 つの data 面で新条件が見る。見ない範囲は §11 | `conformance-tests/`、`security/`、`docs/design/ROADMAP_POST_PHASE7_V1.md` |

新条件の Status 表記は `conformance-tests/CONDITIONS.md` の凡例 (:63-67) に従う。凡例の「four adapters」は登録された全 adapter を意味するので、6 plug のうち 4 plug で走る本条件には使わない。表記の形と凡例に足す文は作業指示書で確定する。

作業指示書で実測して確かめる事項:
- C-19 の bearer 合成走査 (`conformance-tests/test_c19_client_self_sufficiency.py`) と socket harness の `_build_client` 経路の pin (`conformance-tests/test_socket_harness.py`) に、新しい入口が干渉しないこと。
- D-4 の parametrize での xdist の group 付け (`conformance-tests/conftest.py`:125-131)。`registry-guards` group に入らないか、C-19 の前提 (同 group は provisioning も実 process 起動もしない。`conformance-tests/test_c19_client_self_sufficiency.py`:374-386) を破らないか。
- D-7a の後も C-11 の判定が変わらないこと。D-6 の「運ぶだけ」を送信記録で確かめられる plug と、確かめられない plug。
- v0.4: §9.1 の義務 3 件を両 peer が既に満たすこと (§9.2 の判定は src を読んだものである)。(a) 4 wire plug の成功応答の Content-Type の media type が `application/json` であること (catalog を配る応答を含む)。(b) data と control の両面の capability document に `role` があること (control か audit の credential で data 面の capabilities を読む co-hosting の経路を含む)。(c) は `versioning.url_composition` の組む URL 以外を宣言する plug が無いので wire では測れない (§11)。満たさない peer があれば、その挙動の変更を契約 WP に足して監督へ上げる。
- v0.4: `external_standards`・`media_type_note` の最上位 key、`versioning.url_composition`、`errors.response_classification` を足すことで、契約 JSON の key 集合を固定する既存のテストが赤にならないか。`definitions.OperationCatalogEntry` の description を `schema_check.py` が keyword として扱わないか。
- `operation_catalog_url` の上書きが、結合規則の組む URL と同じ endpoint を別の綴り (末尾の slash、大小文字、既定 port) で名指したとき、両 peer が起動時にどう扱うか (§9.1 の #11 の文字単位の比較の下では、その配備に #12 (c) の義務が掛かる)。

## 11. honest scope

- 証明の範囲は common_baseline の 1 周 (C-28 の 12 段) だけである。baseline の他の組み方、床の外の operation、control 面は証明しない。緑は「この作業列について、要求の組み立てに契約外の知識が要らなかった」ことを示すだけで、文書が十分であることは示さない。
- 「契約文書だけ」が成り立つのは要求の形 (path・method・header・body) までである。作業列の意味 (N-4) は散文にしか無く、人 (起草者・実装者) が読んで書く。ここがこの証明の限界である。
- application の登録と key の発行は帯域外 (D-5)。入力 3 の「認可済みの key」を与えられた後だけを示す。
- http ×2 は ASGI transport であり、実 socket を通らない。実 TCP と nginx を通るのは socket ×2 だけで、その app も adapter と同じプロセスで動く。別プロセスで起動する documented 合成根 (real-server launcher) は対象外である。
- 結合規則は 4 plug では区別されない。4 plug の宣言 base URL の path はどれも `/v1` ちょうどで、wire 上で赤になるのは `/v1` の二重だけである。接頭辞付きの結合は単体テスト (D-2a) でだけ示す。origin (scheme・host・port) の誤りが wire で赤になるのは socket ×2 だけで、ASGI transport は host を見ない (`r2db-api/conformance/conformance_adapter_r2db_http.py`:1104-1110)。
- 送信関数は D-6 の pin の外にある。「運ぶだけ」を送信記録で確かめられない plug は、作業指示書の実測 (§10) の結果をここに列挙する。v0.6 (再確認の指摘 6): #1 の redirect の規則は単体テスト (D-7 の 25) でだけ示す。wire では送信関数が redirect を追わないことに依り (D-2a)、それは作業指示書で実測して記録する。
- 契約は TLS を前提にするが (N-15)、試験 plug は TLS を通らない。socket ×2 は loopback の http、r2db http は https (`r2db-api/conformance/conformance_adapter_r2db_http.py`:948)、MitateDB http は `.invalid` の http (`MitateDB-api/conformance/conformance_adapter_mitatedb_http.py`:125・:131) を宣言し、http ×2 はどちらも ASGI transport である (v0.2 の「http ×2 は https を宣言」は誤り。再確認の指摘 7)。参照クライアントは https でない base URL に bearer を送らないが、loopback と `.invalid` の http を例外として許す (§4.1 の N-15)。4 plug のうち 3 plug はこの例外の下で走る。https でない URL を拒むことは単体テスト (D-7 の 16) でだけ示す。
- 送信前に request schema で検証するので、peer 側の request_schema 拒否の経路はこの条件では通らない (既存条件が持つ)。
- C-28 で単独で赤になるとされた段 (5)(9) は、本条件が入ると本条件と同時に赤になる。単独性は本条件と共有になる。
- 読めない点 (N-1・N-2・N-8・N-11・N-13・N-14・N-16・N-17・N-18・N-19) は、Q-1・Q-2・Q-4 の裁定が出るまで契約の欠落として残り、クライアントは §4.1 の値で埋める。v0.4 註 (2026-09-30): 裁定により 10 件とも契約 WP で契約に入る (§9.1)。証明は契約 `<V>` と本書 §4.1 の N-15 の行 1 つに対するものになる。
- 参照クライアントは `operation_catalog_url` を取りに行かない (D-2)。配る catalog と `spec/` の一致は C-29 が持つ。§9.1 の #11 (組む URL 以外に credential を出さない、そこでは credential 無しで配る、credential を付けた要求の redirect を追わない) は、どの plug もその URL 以外を宣言しないので wire で示さない。示すのは文字列ピンだけである。v0.5 (設計レビュー 2 の A-7): 旧版 (`<V>` 未満) を宣言する配備が組む URL 以外で認証を求めるとき、#11 に従う client はそこから取得できない。その文書は契約の派生 catalog と byte 一致なので (1.9.0 の (b))、client は契約から同じものを読む (#11 の 3 文目)。v0.6 (再確認の指摘 2): 「契約から同じものを読む」を改める。byte 一致の相手はその配備が宣言する版の派生 catalog で、client はその版の契約から同じものを導く。
- v0.6 (再確認の指摘 4): #11 と #12 の (c) は宣言値と組む URL を character for character で比べる。配備が組む URL と同じ endpoint を別の綴り (既定 port の明記、host の大小文字等) で宣言すると、その URL は #11 の「any other URL」に当たり、client は credential を出さず、配備には #12 の (c) の義務 (credential 無しで配る) が掛かる。peer の `operation_catalog` はその綴りで届いても認証を求める (:445) ので、その宣言では (c) を満たさない。
- v0.5 (設計レビュー 2 の B-3): #12 の義務の常設の証拠は、(b) の `role` が 6 plug の data 面、(a) の成功応答の Content-Type が wire plug 4 つの data 面だけである (§10 の条件 WP)。control 面の成功応答の Content-Type、control 面の capability document の `role` (v0.6、再確認の指摘 10。port が control 面の文書を出せるかは §10 で実測する)、(c) (組む URL 以外で credential 無しで配る) は常設の証拠を持たない。(c) は文字列ピンだけである。
- §9.1 の #6・#7 の client 側の規則は参照クライアントの単体テスト (D-7 の 10〜13・22〜24) で示す。実装が成功応答に problem+json を返さないことは、作業列が通る応答についてだけ示す。
- 参照クライアントは application の key だけを扱う (D-1)。§9.1 の #1 は control / audit の credential の base URL (`surfaces.control.base_url`) も定めるが (v0.5、設計レビュー 2 の A-1)、その client の要求は本条件で示さない。v0.6 (再確認の指摘 8): #1 は surfaces を宣言する配備 (1.6.0 以上。1.6.0 の義務 (a)、`spec/data-service-api.v1.json`:37) を前提にする。surfaces を持たない配備 (1.6.0 未満) では、#1 を字義どおりに読むと data 面の operation も「宣言されない surface」に当たる。両 peer は 1.12.0 を宣言しており、その配備は本項目の対象に無いので、契約の文は変えない。
- alias (`endpoints.audit_query`、`spec/data-service-api.v1.json`:432) の扱い。(i) deprecation_note は保持を「1.4.0 の後の minor 1 版」とするが、契約 1.12.0 に alias は残っている。この食い違いは本設計では解かず、台帳 `RM` R-118 に起票した。(ii) v0.5 (設計レビュー 2 の A-2): data と control が同じ origin・同じ接頭辞の配備では、control の base URL は `<origin>/control/v1` で、v0.4 の #1 のとおり alias を結合すると `<origin>/v1/audit/query` になる。r2db の本番 nginx 雛形 (`r2db-api/deploy/nginx/r2dbsvc-api-8443.conf.example`:113-114・:166-167) と socket harness (`conformance-tests/socket_harness.py`:303-304・:314-315・:1393-1394) では、その URL は data の process に届き、そこは application の認証の後に拒否する stub である (`r2db-api/src/r2db_api/http.py`:718-745・:766)。control の process の route (`r2db-api/src/r2db_api/control_http.py`:463) には届かず、1.4.0 の追記 (`spec/data-service-api.v1.json`:37) は stub が control / audit の credential を AUTH_INVALID で拒むことを許す。v0.5 の #1・#10 は alias の URL を組まないのでこの一致に依らないが、alias を呼ぶ既存の client には残る (台帳 `RM` R-118 への追記は監督が行う)。(iii) alias が削除されると #1・#10 の alias の句は当てはまる項を失う。そのときの文の扱いは R-118 が決める。
- 性能について何も主張しない。4 node 分の往復が完了ゲートの壁時計を延ばす量は実測して記録する。目標値は先に置かない。
- 本設計は実行検証されていない。§3 D-7 と §5 の変異はすべて候補であり、実測は作業指示書の「完了条件 → 変異」表で行う (`docs/work-orders/OPERATING_CONDITIONS.md` §1.5 の 34)。
- v0.7 註 (2026-10-01、実装後の実測。出所は作業指示書 `docs/work-orders/WORK_ORDER_R108_REFERENCE_CLIENT_V1.md` の §5.5 と訂正註。上の項は書き換えない):
  - 義務 (a)(b): wire の 4 plug で、data 面の 6 operation と control 面の `control_capabilities` の成功応答はすべて `application/json`、capability document の `role` は data 面が `runtime`、control 面が `control` (同書 訂正註 1 の 4)。control の credential で data 面の capabilities を読む経路 (§10 の v0.4 の項の co-hosting の経路) は、4 plug とも 401 `application/problem+json` (`AUTH_INVALID`) で文書を返さない。義務 (b) は返す文書に掛かるので破れていない。
  - 「運ぶだけ」(D-2a (3)・D-6) を確かめた範囲は transport の受け渡し点 (`httpx.ASGITransport` と `httpx.AsyncHTTPTransport` の `handle_async_request`) までで、4 plug とも確かめた (同書 M-8、完了条件 34)。socket の 2 plug の nginx から upstream までは確かめない。
  - redirect を追わないことの wire 上の実測: 4 plug とも末尾 slash 付きの capabilities の path が 307 を返し、送信関数は 3xx をそのまま返し、受け渡し点の呼び出しは 1 回である (完了条件 35)。socket の 2 plug の 307 の `Location` は宣言の port を持たない (台帳 `RM` R-121)。
    - 【追記 2026-10-02 (R-121)】上の 1 文は R-121 前の実測の記録である。R-121 の後、socket の 2 plug の nginx は client の `Host` を port ごと渡し (`$http_host`)、data・control の両 surface の capabilities path の 307 の `Location` が宣言の authority (host と port) を持つことを `conformance-tests/test_wire_entry.py::test_socket_redirect_location_keeps_the_declared_authority` が固定する (実測は台帳 `RM` R-121 の追記)。
  - D-4 の xdist の group は adapter 名である。C-35 と `conformance-tests/test_wire_entry.py` の各 test が自分の group 名を assert する (同書 M-7、完了条件 38・80)。
  - D-7a の後も C-11 の判定は変わらない: 実装前後の集計は 72 → 75 passed で、差は `conformance-tests/test_schema_check.py` の新規 3 test である (完了条件 75)。
  - C-35 の 4 node の所要時間 (WP-4 の報告、`e5d0e0a` の上の `--durations=0` の call): r2db socket 0.61 s、MitateDB socket 0.35 s、r2db http 0.30 s、MitateDB http 0.14 s。完了ゲートでの値は同書 §5.3。
  - 同じ変更セットで、`tools/deploy_smoke.py` を credential を付けた要求の redirect を追わない形に直し (同書 訂正註 2 の 6・訂正註 3)、両 peer の runbook (`r2db-api/deploy/DEPLOYMENT_RUNBOOK.md`・`MitateDB-api/docs/cloud-run-cloud-sql.md`) に義務 (c) の 1 文を足した (同書 訂正註 2 の 4)。

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

## 14. 設計レビュー 2 の反映 (v0.5)

観点 A は A-1〜A-8、観点 B は B-1〜B-12。裁定はすべて採用 (監督、2026-09-30)。依頼者裁定 Q-1〜Q-4 の選択は変えない。

| 指摘 | 裁定 | 反映先 |
|---|---|---|
| A-1、B-10 (#1 の base URL が control / audit の client を締め出し、:1385 と矛盾) | 採用: その credential の面の base_url | §9.1 の #1、§9 Q-1 の v0.5 註、D-1、D-2a、§11 |
| A-2 (alias の結合が co-host 配備で data の stub に当たる) | 採用: 結合規則は alias の URL を組まず、client は canonical を呼ぶ。依頼者が承認した方向の範囲 (v0.6: 範囲にあるとするのは監督の判断。§9 Q-1 の v0.6 註) | §9.1 の #1・#10、§9 Q-1 の v0.5 註と依頼者裁定 (alias)、§4 と §4.1 の N-1・N-19、D-2 の v0.5 註、D-7 の 19、§9.2、§11 |
| A-3、A-4、A-8 (#11 の redirect、同じ origin の別 path、origin の正規化) | 採用: 分け目を組む URL との一致に、redirect を追わない、(c) に as media_type | §9.1 の #11・#12、§9 Q-4 の v0.5 註、§7、§9.2、§10、§11 |
| A-5 (schema に合わない応答の扱い) | 採用 | §9.1 の #7、D-7 の 24、§9.2 |
| A-6、B-1 (#10 の JSON path) | 採用: `definitions.` に直す | §9.1 の #10・#12、§9.2、§10 (:283・:401-404 のピン) |
| A-7 (旧版の配備からの取得) | 採用 (レビューの文案) | §9.1 の #11、§11 |
| B-2 (契約 WP の一覧の漏れ) | 採用 | §9.1 の #12 の置き場、§10 の契約 WP |
| B-3 (新しい義務の常設の証拠) | 採用: `role` は 6 plug の data 面、成功応答の Content-Type は wire 4 plug の data 面、残りは §11 | §10 の条件 WP、§11 |
| B-4 (D-7 の根拠の付け替え) | 採用 | D-7 の v0.4 註 |
| B-5 (D-7 の 20 の変異) | 採用 | D-7 の 20 |
| B-6 (#6・#7 の単体テストの行) | 採用 | D-7 の 4・22・23 |
| B-7 (N-16 の「required にする」を改めた記録) | 採用: 監督裁定として記録 | §9 Q-2 の表と v0.5 註 |
| B-8 (`RM` の行番号と基点) | 採用 | §0 |
| B-9 (D-2 の v0.4 註の (ii)) | 採用 | D-2 の v0.5 註 |
| B-11 (#12 の列挙に #2 が無い) | 採用 | §9.1 の #12 |
| B-12 (#2・#12 のピンの変異と CONTRACT_HISTORY) | 採用: 同時に赤になってよいと明記 | D-7、§10 |
| 監督裁定 2026-09-30、v0.5 の起草時の指摘 (#1 の redirect の文。この行は v0.6 で足した) | 採用 | §9.1 の #1、§9 Q-4 の v0.5 註、§7、§9.2、D-7 の 25 |

## 15. 再確認レビュー (レビュー 2 の後) の反映 (v0.6)

| 指摘 | 裁定 | 反映先 |
|---|---|---|
| 1 (D-7 の 10・11・13・22 の変異が「失敗の種類」を変えず生き残る) | 採用 (監督、2026-09-30。以下同じ): 行を「`code` を読む」/「`code` を持たない」に分ける | D-7 の冒頭と 10・11・13・22〜24 |
| 2 (#11 の旧版の配備の文が `<V>` の catalog と読める) | 採用 (レビューの文案) | §9.1 の #11、§9.2 の 11・12 と Q-4 (A) の判定、§11 |
| 3 (#7 の「errors.shape does not accept」が一意でない) | 採用 (レビューの文案。名指さない key は拒まない) | §9.1 の #7、§9.2 の 6・7 |
| 4 (#11・#12 (c) の URL の比べ方) | 採用: character for character | §9.1 の #11・#12、§9.2 の 11・12、§11 |
| 5 (redirect の文の記録のずれ (a)〜(f)) | 採用 | §9 Q-1 の v0.6 註、§9.1 の前書き、§9.2 の 1・2、§7、§14、D-7 の v0.4 註、D-2 の v0.6 註 |
| 6 (redirect の規則が wire では送信関数に依る) | 採用 | D-2a、§11 |
| 7 (D-7 の 23 の偽の応答の本文) | 採用 | D-7 の 23 |
| 8 (#1 の fail closed と 1.6.0 未満の配備) | 採用: 契約の文は変えず範囲として書く | §11 |
| 9 (alias の扱いと依頼者裁定の関係) | 採用: 依頼者に報告済み (2026-09-30) と記す | §9 Q-1 の v0.6 註、§14 の A-2 |
| 10 (§11 の control 面の `role`、401 行、余分な空白) | 採用 | §11、§9 Q-4 の v0.5 註 |
