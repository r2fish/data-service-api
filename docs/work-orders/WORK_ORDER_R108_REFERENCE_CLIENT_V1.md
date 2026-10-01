# 作業指示書 — R-108 契約文書だけで要求を組む参照クライアント (Change Set Manifest)

## 0. 版数・位置づけ

- **v1.0 (2026-10-01)。** 起草。未発注・未 commit。
- 設計の正本は `docs/design/REFERENCE_CLIENT_V0_1.md` **v0.6** (以下「設計」。依頼者裁定済み = 設計 §9 の【裁定】と alias の裁定。確定)。本書は設計の条件 (K-1〜K-6)・決定 (D-1〜D-10)・却下案 (設計 §8)・背景を写さず節番号で指す (`RM` §9 の 9)。逐語は付録の確定文ファイル (設計 §9.1 から機械的に抜き出したもの) と §1 の起草案だけ。
- 台帳 `RM` §8.1 の **R-108** (`RM`:469)。**規模 L** (`OC` §1.13 の 74)。**変更クラス D** (設計 D-8: `CM` と `_ISOMORPHIC_TARGETS` 集合の増減)。D の証拠: C の全部 + 依頼者裁定の逐語 (設計 §9) + 版付きの security-contract 決定 (契約 1.14.0、`CM` 3.16)。WP ごとのクラスは各 WP に書く。
- 基点: local main `1e8f7fb` (契約 1.13.0、port v1.20、`CM` 3.15、台帳 v1.147、`COLLECTION_FLOOR` 4927)。統合 branch は worktree `.claude/worktrees/r108` (branch `r108`)。WP-2・WP-3 は WP-1 の commit から分けた別 worktree で並行し (§2.0)、`r108` へ `--no-ff` で戻す。main への merge は全 WP の後に 1 回 (§4)。
- **番号の割当** (監督確定 2026-10-01。main `1e8f7fb` を読んで振った。設計 §0・§9.1 の「(仮)」の解消): 契約版 `<V>` = **1.14.0**、`<V-1>` = **1.13.0**、従属判断 `<N>` = **19** (現行の最後は 1.13.0 の 18。1.12.0 の 17 は obligations の entry を持たない)、新条件 = **C-35** (現行の最後は C-34)、port 版 = **v1.21** (`CA` に §31 を足す)、`CM` = **3.16**、台帳 = **v1.148**。merge の直前に main を読み、先に取られた番号があれば振り直して §6 に訂正註を書く。
- 番号: 完了条件は全 WP の通し番号 (1〜99)。変異は **V<完了条件番号>** (1 つの完了条件に複数あるときは V<番号>a・b…、各 1 entry)。expect は `red` (収集時の assert で落ちる変異は `error`。`DEVTOOLS` の `mutate.py` の節)。変異の無い完了条件は「監査照合」と書き、照合対象の逐語 (実行したコマンドと集計行、`file:line`、`git diff`) を報告と §5 に残すこと自体を完了条件とする (`OC` §1.5 の 40)。
- 本書の `file:line` は `1e8f7fb` の現物である。設計の出所 (`c729ab0` / `168f25f`) との対応は §0.2。実装担当は着手時に記号名で引き直す (行は WP ごとに動く)。
- 読む順: §0.2 → §1 → 設計 §2・§3・§4.1・§5・§6・§9.1・§10・§11 → 担当 WP。

**略記**: `OC` = `docs/work-orders/OPERATING_CONDITIONS.md`、`RM` = `docs/design/ROADMAP_POST_PHASE7_V1.md`、`ROLES` = `docs/work-orders/ROLE_PROMPT_TEMPLATES.md`、`DEVTOOLS` = `tools/dev/README.md`、`CM` = `security/CONTROL_MAPPING.md`、`CA` = `docs/design/CONFORMANCE_ADAPTER_V1.md`、`CT` = `conformance-tests`、`COND` = `conformance-tests/CONDITIONS.md`、`CH` = `conformance-tests/CONDITIONS_HISTORY.md`、`SJ` = `spec/data-service-api.v1.json`、`SC` = `spec/OPERATION_CATALOG.json`、`R` = `r2db-api/src/r2db_api`、`M` = `MitateDB-api/src/mitatedb_api`、`RT` = `r2db-api/tests`、`MT` = `MitateDB-api/tests`、`RC` = `r2db-api/conformance`、`MC` = `MitateDB-api/conformance`、`$SP` = 監督が発注時に渡す scratchpad (`{scratchpad}`)。

### 0.1 枠 (問題設定・守る条件・決定・却下案・未確定)

- 問題設定と守るべき条件: 設計 §1・§2 (K-1〜K-6)。
- 決定と根拠: 設計 §3 の D-1〜D-10、§9.1 の 12 文 (英文は確定案。1 語も言い換えない)、§9 の依頼者裁定 (Q-1 (A1)・Q-2 (A)・Q-3 (A)・Q-4 (A)、alias の扱い)。再審議しない (`OC` §1.7 の 51)。
- 却下した代替案: 設計 §8。蒸し返さない。
- 未確定で依頼者判断待ちの選択肢: 無し。設計が「作業指示書で確定する」とした点と起草中に見つけた点は §1 の監督裁定 M-1〜M-10 に置く。

### 0.2 設計の出所の行番号と現行 main の対応 (註。設計文書は書き換えない)

設計の `file:line` は `c729ab0` / `168f25f` の木である。R-115 (契約 1.13.0) と R-102 の merge で次の行が動いた。表に無い出所は `1e8f7fb` でも同じ行である (設計中の明示の `path:line` 114 件を、両基点と `1e8f7fb` の `git show` で行の字面を照合して確かめた。起草時の照合)。

| 設計の出所 | 現行 (`1e8f7fb`) | 備考 |
|---|---|---|
| `SJ` の裸の `:N` (設計 §4・§5・§9) | :1〜:261 は同じ。:262〜:955 は +8、:956 以降は +9 | R-115 が obligations に entry 8 行 (:262-269)、`audit.process_loss_policy` 1 行 (:964) を足した。例: :308 → :316、:331 → :339、:350 → :358、:354 → :362、:427 → :435、:432 → :440、:627 → :635、:665 → :673、:756 → :764、:844 → :852、:872 → :880、:991 → :1000、:1286 → :1295、:1290-1296 → :1299-1305、:1345-1352 → :1354-1361、:1385 → :1394、:1389 → :1398、:1763 → :1772、:2041-2056 → :2050-2065。obligations は :38-273 |
| 設計 §9.1 #12 の置き場「直前の版 `<V-1>` の段落 (現行は 1.12.0 の文)」 | 1.13.0 の段落 | `SJ`:37 の値の「An implementation still declaring 1.12.0 is not held to any 1.13.0-only obligation retroactively.」の後、「A peer's version-flip」の前 |
| `RM`:462 (R-108) / `RM`:582 (§9 の 8 の D 行) | `RM`:469 / `RM`:593 | `RM`:39 (§0.1.1) と :56 (§0.1.3 の実測の行) は同じ |
| `CT/test_contract.py`:89 | :91 | `contract_version` のピン |
| `CT/test_contract.py`:283・:401-404 | :285 (`FIXED_1_9_0_DEFINITION_OPERATION_CATALOG_ENTRY`)・:403-406 | dict 一致 |
| `CT/test_contract.py`:1167-1184 (1.12.0 の文の between と `versions[-1] == "1.11.0"`) | 1.12.0 の文のピンは :1169-1191 で右端は 1.13.0 の段落の始まり (#12 で動かない)。#12 で右端が動くのは **1.13.0 の段落のピン :1271-1289** (右端 = :1283 の `A peer's version-flip`) | `versions[-1]` の assert は無い。obligations のピンは固定 index (:1188-1190 の `versions[10]`、:1255-1268 の `obligations[10]`)。1.14.0 の entry は index 11 |
| `CT/test_contract.py`:1460 (#2、surfaces の文を全値で) | `PIN_1_6_0_ITEM_2_SURFACES` :1565、照合 :1686 | 全値ではなく正規化した包含のピン (`_normalize_prose_for_pin` :1479-1488)。#2 の文を pin の中で差し替える |
| `CT/test_contract.py`:1575-1576 / :1805-1808 / :1811 / :1943 | :1679-1681 / :1907-1914 / :1916-1923 (照合 :2037-2043) / :2048 | |
| 両 peer の tests の版 literal (r2db 4 ファイル 10 か所、MitateDB 4 ファイル 8 か所) | 件数は同じ | `RT/test_audit_query.py`:1991・:4032・:4066、`RT/test_control_plane_service.py`:1808、`RT/test_denial_details_and_request_id.py`:514、`RT/test_foundation.py`:252・:2496・:2511・:2559・:2594、`MT/test_audit_query.py`:1727・:1757・:1769・:3834、`MT/test_control_plane_service.py`:574、`MT/test_denial_details_and_request_id.py`:552・:566、`MT/test_http.py`:393 |
| 宣言 4 か所 `R/capabilities_document.py`:88・`R/control_plane.py`:656・`M/capabilities_document.py`:145・`M/control_plane.py`:1617 | 同じ行 (値は 1.13.0) | 直前のコメント行 (:86・:654・:143・:1615) が版ごとに 1 文を足す形。CH-ID は CH-0142・CH-0260・CH-0542・CH-0543 |
| `CT/adapter.py`:1125 (`transport_kind`) | :1152 | :91 (`CredentialHandle.secret`) は同じ |
| `COND`:63-67 (凡例) | :65-87 | 凡例は "four adapters" だけを定義する |
| `RC/conformance_adapter_r2db_http.py`:947-950・:948・:960・:1104-1110 | :1021-1024・:1022・:1034・:1178-1184 | |
| `MC/conformance_adapter_mitatedb_http.py`:125・:131・:154 | :126・:132・:155 | |
| `RC/conformance_adapter_r2db.py`:116・:127 / `MC/conformance_adapter_mitatedb.py`:107・:116 | :117・:128 / :108・:117 | |
| `M/capabilities_document.py`:456 / `M/http.py`:117・:118・:243・:573-576・:676・:1263-1294 | :454 / :118・:119・:244・:574-577・:677・:1269-1300 | |
| `R/main.py`:228-234 | :214-219 (`_operation_catalog_url`、:199-219) | |
| `R/platform_declarations.py`:341-352 / `M/platform_declarations.py`:369-380 | :348-359 / :376-387 | |
| `r2db-api/deploy/DEPLOYMENT_RUNBOOK.md`:633 / `MitateDB-api/docs/cloud-run-cloud-sql.md`:1239-1245 | :640 / :1284-1290 | |

## 1. 監督裁定 M-1〜M-10 (依頼者確認待ち)

設計が「作業指示書で確定する」とした 3 点 (M-1・M-2・M-3) と、起草中に見つけた点 (M-4〜M-10)。各件は推奨 1 つと代案を持つ。**裁定は全件「推奨で進める (依頼者には最後にまとめて確認)」** (依頼者の指示による監督の進め方)。確認で覆ったときは §6 に訂正註を足し、行を消さない (`OC` §1.8 の 56・57)。

**M-1 wire への入口と送信関数の形、in-process plug での振る舞い (設計 §6・D-2a・D-4)**

- 推奨:
  - port v1.21: `ConformanceAdapter` の `hold_after_plan_verification` (`CT/adapter.py`:1924) の後に `@abstractmethod def wire_entry(self, application_id: str) -> "WireEntry"` を足す。呼び手は `isolated` の面 (`iso`) で `iso.provision_application(application_id)` の後に呼ぶ。入口はその application に runtime と developer の credential を既存の `issue_credential` (bootstrap の経路。D-5) で 1 本ずつ発行し、`CredentialHandle.secret` (`CT/adapter.py`:91) をそのまま返す。
  - `WireEntry` (`CT/adapter.py` の module 水準、frozen dataclass、`IdempotencyHold` と同じ非 normative の型): `base_url: str` (その面が宣言する `surfaces.data.base_url`)、`send`、`runtime_secret: str`、`developer_secret: str`。secret の 2 欄は `field(repr=False)` (repr と assert の失敗文に出さない。D-9)。
  - `send(method: str, url: str, headers: tuple[tuple[str, str], ...], body: bytes | None) -> tuple[int, tuple[tuple[str, str], ...], bytes]`。同期・blocking。返すのは status、受けた header の組 (順と綴りのまま)、本文の bytes。redirect を追わない (3xx をそのまま返す)。渡された method・URL・header・body を変えずに wire へ渡し、足すのは HTTP のライブラリが枠付けに付ける `Host` と `Content-Length` だけ。接続の失敗は例外として上げる。
  - 実現: plug の event loop の `_run` (`RC/conformance_adapter_r2db_http.py`:1699-1743、`MC/conformance_adapter_mitatedb_http.py`:1418 の同形) の上で、`httpx.Request(method, url, headers=list(headers), content=body)` を transport の `handle_async_request` に直接渡し、`aread()` してから返す (client 層の既定 header・cookie・redirect を通さない)。transport は http adapter の hook 1 つ (名は実装担当が付け報告する) で選ぶ。既定 (ASGI の 2 plug) は面の data app に対する `httpx.ASGITransport`。socket の 2 plug は宣言 URL をそのまま dial する one-shot の `httpx.AsyncHTTPTransport`。r2db socket は返す前に面の `base_url` を読んで面を起動し (`RC/conformance_adapter_r2db_socket.py`:233-236)、URL を書き換える既存の `_LazySocketClient.send` (同:458-460) は使わない。MitateDB socket の既存の transport は URL を書き換えない (`MC/conformance_adapter_mitatedb_socket.py`:319-329)。`wire_entry` の本体と hook の既定は両 peer の http adapter で同型にする (M-9)。
  - in-process の 2 plug: `wire_entry` を実装し、`transport_kind` の `"in_process"` を名指す `AssertionError` を上げる (port の使い方の誤り。`fold_batch_idempotency_key` の扱い `CT/adapter.py`:1118-1124 と同じ)。送信関数を返さず、skip しない。
- 代案: (a) async の send (plug の client と同じ形) — クライアントが event loop を持つことになり、標準ライブラリだけの同期クライアント (D-1・K-1) と合わない。(b) 標準ライブラリの `urllib.request.Request` 相当を受け渡す — header 名を正規化する (`add_header` は capitalize する) ので「運ぶだけ」の照合が header の綴りで割れる。(c) in-process は port の既定 (abstract でない) で上げる — 宣言を忘れた plug が既定を黙って継ぐ (`transport_kind` が既定を持たない理由 `CT/adapter.py`:1134-1152 と同じ)。
- 根拠: 設計 D-2a (3) の「運ぶだけ」を transport の受け渡し点で照合できる形 (M-8)。送信関数は pin の外 (設計 D-6) なので、形を小さくし client 層の暗黙の処理を通さない。
- 確定文: port の docstring の最初の段落は M-10 の確定文ファイル。
- 裁定: 推奨で進める (依頼者には最後にまとめて確認)。

**M-2 D-6 の許可集合の厳密な形 (設計 D-6)**

- 推奨: クライアント module の文字列定数 (`ast.Constant` の str と bytes。f-string の定数部分を含む。module・class・関数の docstring を除く) は次の (i)〜(iv) のどれかでなければ赤とする。
  - (i) 契約の key: テスト module に置く表 (dotted JSON path の集合) のどれかの末尾の key 名。各 path が `SJ` か `SC` で解決することをテストが assert する (応答の key は `SJ` の `schemas.<名>.properties.<key>` の path で書く。path はテスト module の定数なのでクライアント側の禁止に掛からない)。
  - (ii) 散文由来リテラル: テスト module に置く表 (literal → 出所)。設計 D-6 の表の 2 行 (`Authorization`・`Content-Type`) に、実装で要るものを出所付きで足す。見込み: `control.` (#10、`definitions.OperationCatalogEntry.description`)、`https`・`http`・loopback と `.invalid` の照合語 (設計 §4.1 の N-15)、scheme と secret の区切りの空白 (`SJ`:13 の「Authorization: Bearer <secret>」)、media type の parameter の区切り `;` (#6・#9)、percent-encode の `safe` に渡す空文字 (#4)。足す行は報告に出所付きで列挙し、実装前に監督へ上げる (`OC` §1.5 の 37)。
  - (iii) 例外の文: クライアント module の例外 class の構築の引数にだけ現れる定数。
  - (iv) §4.1 の表: クライアント module に置く設計 §4.1 の表 (名は実装担当) の key と値。
  - どの種でも、禁止集合 F (`SC` の各項の `name`・`method`・`path`、`name` から `control.` を除いた名、`SJ` の `schemas` と `definitions` の key 名。テストが `SC` と `SJ` から導く) と一致する定数は赤 ((i) の末尾の key 名が F と一致するときも赤)。capability document を取る operation の名 (段 (1)) はクライアントが持たず、呼び手 (作業列) から他の operation と同じく受け取る。クライアントは最初の呼び出しの応答をその operation の response schema で検証した後にだけ capability document として読み (`contract_version`・`role`・`surfaces`)、それより前の他の呼び出しを送信せず例外にする。
- 代案: (a) `SJ` と `SC` の全 key 名を自動で許す — 許可が数百語になり (`eq`・`insert` 等の語彙が通る)、作業列の知識の直書きを止めない。(b) 許可の表をクライアント module 自身に持たせる — 表の改竄と直書きが同じ差分で通る。
- 根拠: K-1 の「直書きしない」を、構造化値から引けること (path の解決) の照合で固定し、散文からしか得られない語を出所付きの有限の表に閉じる。
- 裁定: 推奨で進める (依頼者には最後にまとめて確認)。

**M-3 C-35 の Status 表記と凡例に足す文 (設計 §10 末尾)**

- 推奨: Status の表記は `executable (four wire adapters)`。`COND` の凡例の段落 (:65-87) の直後に次の 1 文を足す (起草案。監督が M-10 の確定文ファイルに写す): "\"executable (four wire adapters)\" means the same as \"executable (four adapters)\" except that the tests are parametrized over exactly the registered adapters whose declared `transport_kind` is not `in_process` -- the two `asgi` and the two `socket` plugs -- selected once, at module import, from the built registry, and asserted there to number four."
- 代案: (a) `executable (wire plugs)` (数を書かない) — plug 数の変化が表記に出ない。(b) `executable (four adapters, wire transport)` — 凡例の "four adapters" (登録された全 adapter の意、`COND`:65-69) と字面が重なる。
- 裁定: 推奨で進める (依頼者には最後にまとめて確認)。

**M-4 #12 の義務 (b) (`role`) の常設の証拠の置き場 (設計 §10 の条件 WP「既存条件に足すか新条件の段にするかは作業指示書で決める」)**

- 推奨: `CT/test_c19_client_self_sufficiency.py` に test を 1 つ足す。registered の全 adapter (6) の data 面の capability document (`adapter.capability_document()`) が、宣言する `contract_version` が 1.14.0 以上なら `role` を持ち、値が `SJ` の `security.roles` の 1 つであることを見る。`COND` の C-19 の行の Status にその test 名を足す。credential の role と値が一致することは C-35 の段 (1) が wire の 4 plug で見る (D-4a)。control 面の `role` は常設の証拠を持たない (設計 §11)。
- 代案: (a) C-11 (`CT/test_c11_document_conformance.py`) に足す — D-7a の「C-11 の判定不変」の実測と同じ変更セットで C-11 の判定を動かすことになる。(b) C-35 に 6 plug の段として置く — 1 つの条件が 4 plug と 6 plug を混ぜ、Status の表記 (M-3) が 1 つに決まらない。
- 根拠: C-19 は client の自己充足 (鍵について client が契約から知れること) の条件で、6 adapter で走り、版で効く vector を既に持つ (`COND` の C-19 の Status「declare-first」)。
- 裁定: 推奨で進める (依頼者には最後にまとめて確認)。

**M-5 本書の C-35 参照と commit の時期**

- 事実: `tools/check_doc_refs.py` は `.md` 中の `C-NN` が `COND` の行に定義されていることを検査する。本書は C-35 を参照するので、`COND` に C-35 の行が無いうちは本書を commit できない。
- 推奨: WP-1 で `COND` に C-35 の行を `declared` で開き (Condition・Invariants・Evidence は M-10 の確定文、Status は `declared` で始まる 1 文と history の link)、`CH` に `## C-35` の節を足し、本書は WP-1 と同じ変更セットで branch `r108` に commit する。WP-4 で Status を `executable (four wire adapters)` にする。先例: C-28〜C-30 は declared の行を先に開いた (`CH`:410)。
- 代案: 本書を WP-4 の commit まで commit しない (R-102 作業指示書 訂正註 1 (a) の先例) — 並行の WP-2・WP-3 の worktree が本書を branch から読めない。
- 裁定: 推奨で進める (依頼者には最後にまとめて確認)。

**M-6 契約に足す key の置き場 (設計 §9.1 は JSON path だけを定める)**

- 推奨: `versioning.url_composition` は `versioning.control_base_path` の直後。`media_type_note` は最上位の `media_type` の直後、`external_standards` はその直後 (`security` の前)。`errors.response_classification` は `errors.http_status_note` の直後。`endpoint_fields_note.path` は `atomicity` の後 (最後)。`schemas.CapabilityDocument.properties.role.description` は `enum` の後。`definitions.OperationCatalogEntry.description` は `properties` の後 (最後)。位置はテストで固定せず (値のピンだけ)、差分のレビューで確かめる。
- 代案: すべて各節の末尾に足す (規則を 1 つにする)。
- 根拠: 読み手 (AI agent) が関係する key の隣で読める。
- 裁定: 推奨で進める (依頼者には最後にまとめて確認)。

**M-7 D-4 の xdist の group 付けの常設の確かめ (設計外の小さな検査。`OC` §1.5 の 37)**

- 事実 (静的): `CT/conftest.py`:95-132 は `callspec.params["adapter"]` を group 名にし、それが無い item を `registry-guards` (:131) に入れる。`registry-guards` は provisioning も実 process 起動もしない前提である (`CT/test_c19_client_self_sufficiency.py`:374-386)。
- 推奨: C-35 の test と `CT/test_wire_entry.py` (WP-2) は `adapter` fixture を wire 4 名で indirect に parametrize し、test 自身が自分の `xdist_group` の marker の名が adapter 名であることを assert する (先例 `CT/test_c26_composition_root.py`:922-934)。
- 代案: 実測を 1 回だけ行い §5 に記録し、常設の assert は置かない。
- 裁定: 推奨で進める (依頼者には最後にまとめて確認)。

**M-8 「運ぶだけ」の確かめ方 (設計 D-6 の 3 点目・§11)**

- 推奨: WP-2 の port 単体テスト `CT/test_wire_entry.py` が、4 wire plug について transport の受け渡し点 (`httpx.ASGITransport.handle_async_request`・`httpx.AsyncHTTPTransport.handle_async_request`) を monkeypatch の spy で包み (先例 `CT/test_socket_harness.py`:681-709)、送信関数に渡した method・URL (文字単位)・header の組 (`Host`・`Content-Length` を除く全組)・body と、受け渡し点の `httpx.Request` が一致することを assert する。受け渡し点より先 (socket の nginx → upstream) は確かめず、設計 §11 の記録に書く (WP-5)。
- 代案: plug の中に記録点を置く (`WireEntry` に記録の口を足す) — port の面が増える。
- 裁定: 推奨で進める (依頼者には最後にまとめて確認)。

**M-9 同型性の行と `CM` の pin 名の追随 (WP-2)**

- 推奨: `_ISOMORPHIC_TARGETS` (`RT/test_audit_query.py`:2425、`MT/test_audit_query.py`:2217) に足す行は、`wire_entry` (http adapter 2 本の対、in-process adapter 2 本の対) と transport の hook の既定 (http adapter 2 本の対)。socket の override は peer ごとに違う (r2db は URL を書き換える既存 client を避ける) ので行にしない。件数 pin (現行 `test_isomorphic_target_table_is_pinned_to_its_current_205_rows`) を実測の行数に改名し (`OC` §1.5 の 40b)、その名を引く `CM`:879 を同じ WP-2 の変更で追随させる (`CM` の版は上げない。版上げは WP-4 の 3.16 で 1 回。`OC` §1.13 の 75)。
- 代案: `CM`:879 を WP-4 まで赤のままにする (R-115 作業指示書 WP-2 の先例) — 並行の WP-3 の worktree との統合後に `CT/test_control_mapping_register.py` の赤が混ざり、レビューの判定が割れる。
- 裁定: 推奨で進める (依頼者には最後にまとめて確認)。

**M-10 確定文ファイル (`OC` §1.5 の 35・36)**

- 推奨: 監督が発注前に次を作る。契約の 12 文と obligations の entry は付録の script の出力 (`$SP/r108-fixed-text/`)。加えて `$SP/confirmed-r108-wire-entry.txt` (port の docstring の最初の段落。下の起草案を監督が確定)、`$SP/confirmed-r108-condition.txt` (C-35 の行の Condition・Invariants・Evidence の 3 cell と M-3 の凡例の文)。実装担当はファイルから複製し、言い換えない。
- port の段落の起草案: "Returns this surface's wire entry for `application_id`, an Application already provisioned on this surface: the base URL this surface declares as `surfaces.data.base_url`, a send function that carries one request -- method, URL, header pairs and body, exactly as given -- to that URL over this plug's own transport and returns the status, the response's header pairs and its body without following a redirect, and the bearer secret of one runtime and one developer credential issued to that Application through this adapter's own bootstrap path. A plug whose `transport_kind` is `in_process` has no wire and raises `AssertionError`."
- C-35 の行の起草案 (書式は `COND`:27 の表頭、1 cell 3000 字以内):

```text
| C-35 | A client holding only this contract -- `spec/data-service-api.v1.json` and its derived `spec/OPERATION_CATALOG.json` --, a deployment's `surfaces.data.base_url` and one authorized application credential at a time composes every request of the one `common_baseline` turn C-28 drives -- method, URL, headers and body -- from what the contract states, and completes that turn against every wire-transport adapter: the client (`conformance-tests/reference_client.py`) imports no peer, adapter or port code, writes no operation name, path, method, schema name or header shape the contract does not state, validates every body against the operation's request schema before sending and reads every response as `errors.response_classification` states, and reaches the peer only through each plug's `wire_entry` (port v1.21). | SI-05, SI-09, SI-10, SI-11, SI-14 | the reference client's turn over each wire plug's own transport, with the client's static pin and its unit tests over a recording send function -- `conformance-tests/test_c35_reference_client_turn.py`, `conformance-tests/test_reference_client.py` | 〈WP-1: declared で始まる 1 文 (M-5)。WP-4: executable (four wire adapters) と実測の範囲 (`OC` §1.5 の 34)〉 [history](CONDITIONS_HISTORY.md#c-35) |
```

- 裁定: 推奨で進める (依頼者には最後にまとめて確認)。

## 2. Change Set Manifest (WP-1〜WP-5)

### 2.0 共通 (全 WP)

**順序**: WP-1 (契約 1.14.0、単独) → WP-2 (port v1.21) と WP-3 (クライアント) を別 worktree で並行 → 両方を `r108` へ merge → WP-4 (条件 C-35) → WP-5 (記録と閉止、監督) → 計測 (§3)・完了ゲート・受け入れ監査・main への merge (§4)。契約・conformance の WP を実装 WP より先に置く (`ROLES` の「Class C・D」の 4)。

**並行 WP の触るファイル (重なり 0。`OC` §1.2 の 16・17)**: 着手前に監督が `git diff --name-only` の実物と照合する。重なりが出たら実装に入る前に監督へ上げる。

| WP | worktree (branch) | 触るファイル |
|---|---|---|
| WP-2 | `.claude/worktrees/r108-wp2` (`r108-wp2`、WP-1 の commit から) | `CT/adapter.py`、`CT/test_wire_entry.py` (新規)、`RC/conformance_adapter_r2db.py`、`RC/conformance_adapter_r2db_http.py`、`RC/conformance_adapter_r2db_socket.py`、`MC/conformance_adapter_mitatedb.py`、`MC/conformance_adapter_mitatedb_http.py`、`MC/conformance_adapter_mitatedb_socket.py`、`RT/test_audit_query.py`、`MT/test_audit_query.py`、`CA`、`CM` (:879 の pin 名だけ) |
| WP-3 | `.claude/worktrees/r108-wp3` (`r108-wp3`、WP-1 の commit から) | `CT/reference_client.py` (新規)、`CT/test_reference_client.py` (新規)、`CT/schema_check.py`、`CT/test_schema_check.py` |

両 WP とも `CT/` にファイルを足すが、名の系統が別 (`test_wire_entry.py` / `reference_client.py`・`test_reference_client.py`) で、同じファイルに両者が書かない。`CT/COLLECTION_FLOOR` はどの WP も触らない (§4 で監督)。

**役割**:

- 実装担当 (`ROLES` の 2、`implementer`): WP-1〜WP-4 に 1 起動ずつ (差し戻しは別起動)。穴: 担当 worktree = 上表と §0、作業指示書 = 本書の該当 WP、正本設計 = 各 WP の「読むべき正本」、タスク = 完了条件と変異の表、テスト / 変異 = 各 WP の「道具の引数」。
- コードレビュー (`ROLES` の 5、`reviewer`、Class C / D): WP ごとに 1 群。1 巡目は担当観点 A / B の 2 起動の並列で、並列の 2 起動は変異を実行せず spec を `$SP/review-r108-wp<N>-<A|B>-mutations.json` に書く。2 起動の完了後に監督が spec を実行する。修正後の再確認は観点を指定しない 1 起動 (`OC` §1.7 の 50a・50b)。
- 受け入れ監査 (`ROLES` の 6、`evidence-auditor`): 全 WP のレビューの後に 1 回。
- 監督: 確定文ファイルの作成 (M-10・付録)、WP ごとの branch への commit、並行 worktree の重なりの照合と `r108` への merge、WP-5、計測 (§3)、完了ゲート、`COLLECTION_FLOOR` の更新、指摘の 1 件ごとの裁定 (`OC` §1.15 の 77)、local main への merge 1 回。push は停止中。

**実装担当への注意 (全 WP。発注の「注意」の行に置く。規律の本文は `OC` を読む)**:

1. suite 全体・`tools/dev/gate.py`・`tools/dev/finalize.py` を実行しない (`OC` §1.6 の 42、§1.11 の 70)。テストは各 WP の「道具の引数」だけを前景・直列・timeout 600000 で回す (`OC` §1.5 の 39)。
2. commit・merge・push・branch 操作・`git stash` をしない。例外は新規 file の `git add -N` だけ (`OC` §1.1 の 2)。下請けの Agent を起動しない (`OC` §1.7 の 47)。
3. 空振り禁止 (`OC` §1.5 の 32)。skip / xfail を置かない (`OC` §1.3 の 26)。
4. 主張は実測の後 (`OC` §1.5 の 34)。docstring・`COND`・`CM` の断言は変異の結果を得てから書く。
5. 確定文言はファイル経由 (`OC` §1.5 の 35・36)。
6. 設計外の拡張は実装前に上げる (`OC` §1.5 の 37)。触ってよいパスの外の赤は直さず報告する。
7. 同型性テスト (`OC` §1.5 の 38・40b)。
8. 変異は 1 変異 1 entry、`-x` を使わない。各 entry の test id はその完了条件の test 1 件 (`mutate.py` は最初の失敗で止まる)。`-k` の id は `--collect-only -q` で確かめる。`old` / `new` は実装担当が書き、報告に表で残す。REFUSED (終了コード 75) は迂回しない (`OC` §1.10 の 66)。
9. 新しいコメント・docstring は現在形で書き、フェーズ / WP / 台帳 ID / 日付の語を入れない (`docs/design/CODE_COMMENT_PROVENANCE_V1.md` §4.1 (5))。`# history: CH-NNNN` を持つ塊を言い換えるときは同じ変更セットで `docs/code-history/` に訂正を追記する (同設計 §9.3)。`CT/` の docstring とコメントの `file:line` は `CT/test_conformance_docstring_position_refs.py` が解決を検査する。
10. 文書・テスト・失敗文には合成値と `example.invalid` だけを使う (`OC` §1.9 の 60)。一時ファイルは `$SP` 配下、複数手順は `$SP` の bash 3.2 互換 script。報告は `$SP/r108-wp<N>-report.md` (道具の出力行をそのまま貼る。`OC` §1.10 の 65)。port 8000 / 8001 の uvicorn は別 repo の常設 service なので止めない。

**道具の引数** (`$SP` を export し、main checkout を cwd にして `-C` で worktree を指す。渡し忘れると main を測る):

```bash
tools/dev/pt.py -C .claude/worktrees/<name> -- <各 WP の「テスト」のパス> -q
tools/dev/mutate.py "$SP/r108-wp<N>-mutations.json" -C .claude/worktrees/<name>
```

`<name>` は WP-1・WP-4 = `r108`、WP-2 = `r108-wp2`、WP-3 = `r108-wp3`。worktree を cwd にして: `python3 tools/check_comment_provenance.py --base 1e8f7fb <触った src>`、`python3 tools/check_comment_provenance.py --register`、`python3 tools/change_class.py <触った全パス>`、`python3 tools/check_doc_refs.py`、`python3 tools/public_value_scan.py <触った全パス>`。peer の tests は peer ごとに別の `pt.py` 呼び出しで回す。

### 2.1 WP-1 — 契約 1.14.0 (実装担当)

**目的**: 設計 §9.1 の 12 文と obligations の entry (従属判断 19) で契約を 1.14.0 にし、派生 catalog・packaged 写し・両 peer の宣言 4 か所・版の literal・既存ピンを同じ commit で追随させる (`OC` §1.1 の 11)。peer の挙動は変えない (下の実装前の実測が前提)。
**読むべき正本**: 設計 §9 の【裁定】・§9.1・§9.2・§10 の契約 WP の行・§11 の #11 と #12 (c) の項、M-5・M-6・M-10。先例: `git show --stat c86a871` (1.12.0。挙動の変更の無い版上げで、`docs/code-history/` の 4 ファイルの訂正を含む)、`git show --stat 95f6906` (1.13.0 の契約の部)。**クラス**: C。**群**: レビュー群 1。

**注意**: §2.0 の実装担当への注意 1〜10。とくに空振り禁止 (`OC` §1.5 の 32)、主張は実測の後 (同 34)、確定文言はファイル経由 (同 35)、設計外の拡張は実装前に上げる (同 37)、同型性テスト (同 38)。

**実装前の実測 (WP-1 の先頭。義務 (a)(b) を満たさない peer があれば実装に入らず監督へ上げる。設計 §10 末尾の 4 つ目)**:

- 静的な出所: (a) 成功応答は `JSONResponse` (media type `application/json`) か `Response(..., media_type="application/json")`。`R/http.py`:498・:520・:556・:630・:643・:672、`M/http.py`:656・:677・:741・:882・:961・:982・:1173・:1224・:1256。`M/http.py`:997 付近の「already-built `Response`」の経路は実測で確かめる。(b) `role` は `R/capabilities_document.py`:190、`R/control_plane.py`:664、`M/capabilities_document.py`:454、`M/control_plane.py`:1630。
- 手順: 一時の探査 test `CT/test_zz_r108_probe.py` を worktree に置く (commit しない。報告の後に削除し、削除を `git status --short` で示す)。4 wire plug について、plug の data client と control client で、C-28 の作業列が使う data 面の operation (capabilities・catalog・operation-catalog・schema・mutate・query) と control 面の `control_capabilities` の成功応答の `content-type` を記録する。data 面と control 面の capability document の `role`、control credential で data 面の capabilities を読んだ文書の `role` を記録する。`tools/dev/pt.py -C .claude/worktrees/r108 -- conformance-tests/test_zz_r108_probe.py -q -s`。結果は §5.5 の表 1 に埋める。(c) は wire で測れない (設計 §11)。

**確定文の置き方** (ファイルは付録の script の出力。`N.txt` は `$SP/r108-fixed-text/NN.txt`。連結は半角空白 1 つ):

| # | JSON path | 値 |
|---|---|---|
| 1 | `versioning.url_composition` (新) | `01.txt` |
| 2 | `schemas.CapabilityDocument.properties.surfaces.description` | 値の中の「Neither URL ends in a trailing slash, so that appending a path to it yields exactly one separator.」を `02.txt` に置き換える (他の文は 1 文字も変えない) |
| 3・4 | `endpoint_fields_note.path` (新) | `03.txt` + 空白 + `04.txt` |
| 5 | `media_type_note` (新、最上位) | `05.txt` |
| 6・7 | `errors.response_classification` (新) | `06.txt` + 空白 + `07.txt` |
| 8 | `schemas.CapabilityDocument.properties.role.description` (新。`required` は変えない) | `08.txt` |
| 9 | `external_standards` (新、最上位) | `09.txt` |
| 10 | `definitions.OperationCatalogEntry.description` (新) | `10.txt` |
| 11 | `schemas.CapabilityDocument.properties.operation_catalog_url.description` | 現行の値 + 空白 + `11.txt` (既存の文は変えない) |
| 12 | `versioning.version_binding` | 1.13.0 の段落の末尾 (§0.2) と「A peer's version-flip」の間に `12.txt` を置く (前後は空白 1 つ) |
| entry | `versioning.obligations` | 末尾 (index 11) に `obligations-entry.json` |

key の位置は M-6。`SJ` と両 peer の packaged 写し (`R/contract/data-service-api.v1.json`、`M/contract/data-service-api.v1.json`) を byte 一致にする。

**触ってよいパス**:

- `SJ`、`R/contract/data-service-api.v1.json`、`M/contract/data-service-api.v1.json`
- `SC`、`R/contract/OPERATION_CATALOG.json`、`M/contract/OPERATION_CATALOG.json` (`python3 tools/contract_catalog.py` で再生成。引数なしは書き込み、`--check` は照合)
- `spec/CONTRACT_HISTORY.md` (`## versioning.version_binding` の節 (:385) の引用を 1.14.0 の全文に、Revision note 10 を足す。`## schemas.CapabilityDocument.properties.surfaces.description` の節 (:266) に Revision note (#2、1.12.0 の先例 :236 の形))、`spec/CONTRACT_HISTORY_MANIFEST.json` (:96 の entry に whole-value の `rewrite`。`from` = 1.13.0 の値、`to` = 1.14.0 の値)、`spec/CCR_DISPOSITION.md` (従属判断 19 の段。18 の段 (:313) と同じ形で、`version_binding` の 1.14.0 の文を引用する)、`spec/README.md` (1.14.0 の段落。:33 の形)
- 宣言 4 か所と直前のコメント 1 文 (§0.2)。CH-ID の訂正は `docs/code-history/r2db-api/service.md` (CH-0142、:1066)、`docs/code-history/r2db-api/control_plane.md` (CH-0260、:466)、`docs/code-history/MitateDB-api/capabilities_document.md` (CH-0542)、`docs/code-history/MitateDB-api/control_plane.md` (CH-0543) への追記だけ
- 版の literal: §0.2 の r2db 10 か所・MitateDB 8 か所 (8 ファイル)
- `CT/test_contract.py` (§0.2 のピンの差し替えと 12 文と entry の文字列ピン)、`CT/test_contract_history_register.py` (register が要求するときだけ)
- `COND` (C-35 の行を declared で。M-5)、`CH` (`## C-35` の節)
- `RM` の :39 の版 (1.13.0 → 1.14.0) だけ
- これ以外は 0 件。基点で `1.13.0` を含む追跡ファイルは `git grep -l '1\.13\.0' -- ':!docs/archive' ':!docs/code-history'` で実測し、版の宣言・版の literal と、1.13.0 の義務を名指す記述 (`COND`:62、`CH`:434、`CT/test_c33_process_loss.py`:4、両 peer の runbook) を分けて報告する (後者は変えない)。

**完了条件 (1〜28) → 変異** (2〜13 の変異は、確定文の 1 語を `SJ` と両 peer の packaged 写しの 3 か所で同じに変える形 (写しの byte 一致を同時に赤にしない)。test id はその文の文字列ピン。#2・#12 は `CT/test_contract_history_register.py` と同時に赤になってよい = 設計 D-7)

| # | 完了条件 | 変異 |
|---|---|---|
| 1 | 実装前の実測 (上) を行い、(a)(b) の結果を §5.5 の表 1 の形で報告した | 監査照合 (探査の出力の逐語と、探査 file の削除を示す `git status --short`) |
| 2 | #1 の値が `01.txt` と byte 一致し、文字列ピンがそれを assert する | V2: `removes` → `strips` |
| 3 | #2 の文が `02.txt` で、旧文が値に無いことをピンが assert する | V3: `appending` → `adding` |
| 4 | #3 (`endpoint_fields_note.path` の 1 文目) のピン | V4: `braces` → `brackets` |
| 5 | #4 (同 2 文目) のピン | V5: `unreserved` → `reserved` |
| 6 | #5 のピン | V6: `successful` → `accepted` |
| 7 | #6 (`errors.response_classification` の 1 文目) のピン | V7: `case-insensitively` → `case-sensitively` |
| 8 | #7 (同 2〜3 文目) のピン | V8: `intermediary` → `proxy` |
| 9 | #8 のピン。`CapabilityDocument.required` に `role` が無いことも assert する | V9: `opaque` → `structured` |
| 10 | #9 のピン | V10: `RFC 9110` → `RFC 7231` |
| 11 | #10 のピン | V11: `alias` → `copy` |
| 12 | #11 のピン (値の末尾が空白 + `11.txt`)。1.9.0 の文のピン (:1916-1923) は緑のまま | V12: `character for character` → `byte for byte` |
| 13 | #12 のピン: 1.13.0 の段落の末尾と version-flip の文の間が、ちょうど空白 + `12.txt` + 空白 (等号の照合) | V13: `differs` → `diverges` |
| 14 | `versioning.obligations[11]` が `obligations-entry.json` と dict 一致 | V14: `unconditional` から `capability_document_carries_role` を除く (3 か所) |
| 15 | 1.13.0 の段落のピン (:1271-1289) の右端が 1.14.0 の段落の始まりに追随する | V15: 1.14.0 の段落の直前に 1 語足す (3 か所) |
| 16 | 3 つの契約の `contract_version` が 1.14.0 で、:91 のピンが 1.14.0 を assert する | V16: `SJ` の `contract_version` を 1.13.0 に戻す |
| 17 | 3 つの契約が byte 一致 (`test_contract_packaged_copies_are_byte_identical`) | V17: r2db の packaged 写しの #9 の文に 1 文字足す |
| 18 | 派生 catalog の 3 つの写しが再生成済みで `python3 tools/contract_catalog.py --check` が up to date | V18: `M/contract/OPERATION_CATALOG.json` の `contract_version` を 1.13.0 に (test id は catalog の register の test) |
| 19 | 両 peer が data・control の両面で 1.14.0 を宣言し、版の literal の 18 か所が 1.14.0 | V19: `M/control_plane.py` の宣言を 1.13.0 に (`MT/test_control_plane_service.py`:574 の test) |
| 20 | `PIN_1_6_0_ITEM_2_SURFACES` の中の旧文を `02.txt` に差し替え (版の移るピンの規律、:1907-1914 の先例)、包含の照合が緑 | V20: surfaces の値の #2 の外の 1 語 (`never derived` の `never` → `not`) を 3 か所で変える |
| 21 | `endpoint_fields_note` の key 集合のピン (:2048) が `{"roles", "requires_capability", "atomicity", "path"}` | V21: `endpoint_fields_note` に key を 1 つ足す (3 か所) |
| 22 | `FIXED_1_9_0_DEFINITION_OPERATION_CATALOG_ENTRY` (:285、照合 :403-406) が description を含む形に移る (定数の名と経緯のコメントは :1907-1914 の規律に倣う) | V22: `OperationCatalogEntry.required` の 2 項の順を入れ替える (3 か所) |
| 23 | `spec/CONTRACT_HISTORY.md` の 2 節と manifest の `rewrite` が register を通る | V23: manifest の `rewrite.to` の 1 文字を変える |
| 24 | `spec/CCR_DISPOSITION.md` に従属判断 19 の段 (`test_versioning_obligations_subordinate_rulings_exist_in_ccr_disposition` が緑)、`spec/README.md` に 1.14.0 の段落 | V24: 段の頭の `19. **` を `19 **` に |
| 25 | `RM`:39 の版が 1.14.0。4 つの CH-ID の訂正が追記され `check_comment_provenance.py --register` が OK | 監査照合 (`git diff` と出力の逐語) |
| 26 | `COND` の C-35 の行が declared で M-10 の確定文から複製され、`CH` に `## C-35`、`pt.py -- conformance-tests/test_conditions_register.py -q` と `python3 tools/check_doc_refs.py` が緑 | 監査照合 (集計行と出力の逐語) |
| 27 | 下の「テスト」の全呼び出しが failed 0・skipped 0、`git grep` の版の実測を報告した | 監査照合 (集計行の逐語) |
| 28 | 本表に対応の無い行が無い | 監査照合 |

**道具の引数**: テスト = `tools/dev/pt.py -C .claude/worktrees/r108 -- conformance-tests/test_contract.py conformance-tests/test_contract_history_register.py conformance-tests/test_operation_catalog_register.py conformance-tests/test_c29_operation_catalog_url.py conformance-tests/test_c19_client_self_sufficiency.py conformance-tests/test_conditions_register.py -q`、`-- r2db-api/tests/test_foundation.py r2db-api/tests/test_control_plane_service.py r2db-api/tests/test_audit_query.py r2db-api/tests/test_denial_details_and_request_id.py -q`、`-- MitateDB-api/tests/test_http.py MitateDB-api/tests/test_control_plane_service.py MitateDB-api/tests/test_audit_query.py MitateDB-api/tests/test_denial_details_and_request_id.py -q`。変異 = `tools/dev/mutate.py "$SP/r108-wp1-mutations.json" -C .claude/worktrees/r108`。報告 = `$SP/r108-wp1-report.md`。

**レビューの観点**: 確定文の言い換えが無いこと (付録の script を再実行し、ファイルと契約の値を照合する)。版の追随の漏れと、1.13.0 の義務を名指す記述を誤って変えていないこと (`git grep` の実測)。#2 の書き換えが surfaces の他の文を変えていないこと。#12 の置き場 (§0.2) と obligations の index。

### 2.2 WP-2 — port v1.21 (wire への入口。実装担当)

**目的**: 設計 §6・D-2a・D-4 と M-1。port に `wire_entry` を足し、4 wire plug で実現し、in-process の 2 plug は `AssertionError` にする。「運ぶだけ」を受け渡し点で照合する (M-8)。同型性の行を足す (M-9)。
**読むべき正本**: 設計 §6・D-2a・D-4・D-5・D-9、M-1・M-7・M-8・M-9・M-10。現物: `CT/adapter.py`:1026 (`PlanVerificationHold`、非 normative の型の形)・:1152 (`transport_kind`)・:1924 (直前の hook)、`RC/conformance_adapter_r2db_http.py`:1021-1024 (`_SURFACES`)・:1178-1190 (`_build_client` と `_surfaces_value` の hook)・:1699-1743 (`_run`)、`RC/conformance_adapter_r2db_socket.py`:233-236・:447-467・:533-545・:572-621、`MC/conformance_adapter_mitatedb_http.py`:126-145・:1060-1080・:1418、`MC/conformance_adapter_mitatedb_socket.py`:315-335、`CA` §30 (port 改訂の節の形)。**クラス**: D (`_ISOMORPHIC_TARGETS` 集合の増減、`CM`)。**群**: レビュー群 2。

**注意**: §2.0 の実装担当への注意 1〜10。とくに空振り禁止 (`OC` §1.5 の 32)、主張は実測の後 (同 34)、確定文言はファイル経由 (同 35)、設計外の拡張は実装前に上げる (同 37)、同型性テスト (同 38)。

**実装前の実測 (WP-2 の先頭)**:

- 3xx を返す URL を plug ごとに 1 つ決める (完了条件 35 の材料)。見込み (静的): socket の 2 plug は nginx の `location /v1/` に対する末尾 slash の無い `<origin>/v1` が 301、ASGI の 2 plug は Starlette の `redirect_slashes` による末尾 slash 付きの path が 307。一時の探査で実測し、報告に status と `Location` を書く。
- 既存の pin の集計: `tools/dev/pt.py -C .claude/worktrees/r108-wp2 -- conformance-tests/test_c19_client_self_sufficiency.py conformance-tests/test_socket_harness.py -q` を実装前に 1 回回し、集計行を §5.5 の表 2 に書く (完了条件 39 の前値)。

静的な答え (設計 §10 末尾の 1 つ目): C-19 の bearer の合成走査は registered adapter の module file だけを対象にし (`CT/test_c19_client_self_sufficiency.py`:790-806)、id 形の式と `.` を連結する f-string・`+`・`.join` を赤にする (:816-818、:965-1003)。`CredentialHandle.secret` をそのまま返す入口は該当しない。socket harness の pin は `isolated_application_surface` と `hold_in_flight` が `_build_client` を通ることを spy で見る (`CT/test_socket_harness.py`:681-709、:795-839) だけで、入口は `_build_client` の呼び出しの経路を変えない。どちらも完了条件 39 の実行で確かめる。

**触ってよいパス**: §2.0 の表の WP-2 の行。両 peer の `src/` を触らない。

**完了条件 (29〜45) → 変異** (`CT/test_wire_entry.py` は `adapter` を wire 4 名で indirect に parametrize し、選別は module 読み込み時の 1 か所で `transport_kind` を読み、数が 4 であることをその場で assert する。in-process の確かめは別の test で 2 名を同様に選ぶ。M-7)

| # | 完了条件 | 変異 |
|---|---|---|
| 29 | 実装前の実測 (上) を報告した | 監査照合 (探査の出力と集計行の逐語) |
| 30 | port に `wire_entry` と `WireEntry` があり、docstring の最初の段落が `$SP/confirmed-r108-wire-entry.txt` と逐語一致し、`port v1.21` の段落を持つ | 監査照合 (段落と確定文ファイルの `diff` の逐語) |
| 31 | r2db の 2 wire plug: `entry.base_url` がその面の capability document の `surfaces.data.base_url` と一致し、`send` で runtime の secret を付けた `GET` が成功応答を返す | V31: r2db の http adapter の `wire_entry` が control の base URL を返す (r2db の 2 plug で赤) |
| 32 | MitateDB の 2 wire plug: 同上 | V32: MitateDB の http adapter の同じ変異 |
| 33 | runtime と developer の secret がそれぞれの role の credential である (`send` で読んだ capability document の `role`) | V33: r2db の `wire_entry` で 2 つの secret を入れ替える |
| 34 | 「運ぶだけ」(M-8): 4 plug で、受け渡し点の `httpx.Request` の method・URL・header の組 (`Host`・`Content-Length` を除く)・body が `send` の入力と一致する。r2db socket では宣言と host の綴りが違う URL (例 `localhost`) を渡して URL が書き換わらないことを見る | V34a: r2db socket の `send` を既存の `_LazySocketClient` 経由にする。V34b: MitateDB http の `send` が header を 1 つ足す |
| 35 | redirect を追わない: 実装前の実測の URL への `send` が 3xx をそのまま返し、受け渡し点の呼び出しが 1 回 | V35: 1 plug の `send` を `follow_redirects=True` の client 経由にする |
| 36 | `repr(entry)` と、`entry` を含む assert の失敗文に secret が出ない (sentinel で確かめる。D-9) | V36: secret の欄の `repr=False` を外す |
| 37 | in-process の 2 plug の `wire_entry` が `"in_process"` を名指す `AssertionError` を上げ、送信関数を返さない | V37: r2db の in-process adapter の `wire_entry` が `None` を返す |
| 38 | `CT/test_wire_entry.py` の選別の数 4 が module 読み込み時に assert され、各 test が自分の `xdist_group` の名を assert する (M-7) | V38a: `CT/registry.json` から socket の 1 項を除く (expect=error)。V38b: parametrize の引数名を `adapter` 以外にする (自己の assert が赤) |
| 39 | `CT/test_c19_client_self_sufficiency.py`・`CT/test_socket_harness.py` が緑で、集計が実装前と同じ | 監査照合 (前後の集計行の逐語) |
| 40 | `_ISOMORPHIC_TARGETS` に M-9 の行があり、件数 pin が実測の行数に改名され、`CM`:879 が追随し `CT/test_control_mapping_register.py` が緑 | V40: r2db の http adapter の `wire_entry` の本体に正規化で消えない 1 行差を入れる |
| 41 | `CA` の版数行が 1.21 で、§31 (§30 の形: 追加の理由、signature、意味の逐語、plug ごとの実現の実測) がある | 監査照合 (`git diff`) |
| 42 | `check_comment_provenance.py` (adapter の変更) と `change_class.py` の出力を報告した | 監査照合 (出力の逐語) |
| 43 | 新しい試験に skip / xfail が無い | 監査照合 (`git grep -n 'skip\|xfail'` の逐語) |
| 44 | 下の「テスト」の全呼び出しが failed 0・skipped 0 | 監査照合 (集計行の逐語) |
| 45 | 本表に対応の無い行が無い | 監査照合 |

**道具の引数**: テスト = `tools/dev/pt.py -C .claude/worktrees/r108-wp2 -- conformance-tests/test_wire_entry.py conformance-tests/test_c19_client_self_sufficiency.py conformance-tests/test_socket_harness.py conformance-tests/test_control_mapping_register.py conformance-tests/test_conformance_docstring_position_refs.py -q`、`-- r2db-api/tests/test_audit_query.py -k isomorphic -q`、`-- MitateDB-api/tests/test_audit_query.py -k isomorphic -q`。変異 = `tools/dev/mutate.py "$SP/r108-wp2-mutations.json" -C .claude/worktrees/r108-wp2`。報告 = `$SP/r108-wp2-report.md`。

**レビューの観点**: 送信関数が client 層 (既定 header・cookie・redirect) を通らないこと。r2db socket が URL を書き換えないこと (設計 D-2a (3))。secret が repr・失敗文・ログに出ないこと (K-5)。入口が既存の bootstrap の経路で credential を得ること (D-5)。空振り (受け渡し点の spy が本当に呼ばれた回数を assert しているか)。

### 2.3 WP-3 — 参照クライアント (実装担当)

**目的**: 設計 D-1・D-2・D-2a (1)・D-6 (クライアント module の pin)・D-7・D-7a・D-9・D-10 と §9.1 の #1・#3〜#8・#10 の client の規則 (WP-1 の後の契約) を `CT/reference_client.py` に実現し、記録用の偽の送信関数で駆動する単体テストで固定する。送信関数の形は M-1、許可集合は M-2。
**読むべき正本**: 設計 §3 (D-1〜D-2a・D-6・D-7 の表・D-7a・D-9・D-10)・§4.1 (右列: 契約 WP の後は N-15 の 1 行)・§9.1・§11、M-1・M-2。`CT/schema_check.py`:1-38・:58-94・:263 (`used_keywords`)、`CT/test_schema_check.py`:126 (未知の keyword で例外)・:226-245 (keyword のガード)。**クラス**: C。**群**: レビュー群 3。

**注意**: §2.0 の実装担当への注意 1〜10。とくに空振り禁止 (`OC` §1.5 の 32)、主張は実測の後 (同 34)、確定文言はファイル経由 (同 35)、設計外の拡張は実装前に上げる (同 37)、同型性テスト (同 38)。

**実装前の実測 (WP-3 の先頭。設計 §10 末尾の 3 つ目の前半)**: `tools/dev/pt.py -C .claude/worktrees/r108-wp3 -- conformance-tests/test_c11_document_conformance.py conformance-tests/test_c11_response_schema_conformance.py conformance-tests/test_schema_check.py -q` を実装前に 1 回回し、集計行を §5.5 の表 2 に書く (完了条件 75 の前値)。

静的な答え: 作業列が使う request / response schema (`SC` の data 面の項が名指す 10 schema) のうち、`schema_check.py` が実装していない keyword は `maxLength` (`SchemaOperationRequest`・`MutationRequest`) と `maxProperties` (`MutationRequest`) の 2 つだけである (2026-10-01、`used_keywords()` で実測)。C-11 が検証する schema (`CapabilityDocument`・`CatalogDocument`) はどちらも使わないので、2 つを実装しても C-11 の判定は変わらない見込み (完了条件 75 で確かめる)。`definitions.OperationCatalogEntry` に足す `description` は `ANNOTATION_KEYWORDS` (`CT/schema_check.py`:81-92) に入り、keyword として扱われない。

**触ってよいパス**: §2.0 の表の WP-3 の行。`CT/adapter.py`・peer のコード・C-35 の test (WP-4) を触らない。クライアント module は `CT/adapter.py` も peer も import しない (K-1)。

**完了条件 (46〜78) → 変異** (46〜70 は設計 D-7 の表の 1〜25 行に 1 対 1。各行の「固定すること」を完了条件とし、同じ行の「変異」を実測する。失敗を固定する行は失敗の種類 (`code` を読んだ失敗 / `code` を持たない解釈しない失敗) を assert する (D-7 の v0.6 註)。変異の注入先はクライアントのコードとテストで、`spec/` には入れない (D-7))

| # | 完了条件 | 変異 |
|---|---|---|
| 46〜52 | D-7 の 1〜7 行 | V46〜V52: 各行の変異。V48 は 4 種 (V48a 接頭辞を落とす / b origin に path を足す / c 単純連結 / d control の base URL から `/v1` だけを除く)、V49 は 2 種 (a encode を外す / b `/` だけを encode する) |
| 53 | D-7 の 8 行: `CT/test_schema_check.py` に `maxLength`・`maxProperties` の正例と負例を 1 組ずつ | V53a: `maxLength` の判定を外す。V53b: `maxProperties` の判定を外す |
| 54 | D-7 の 9 行のうちクライアント module の AST pin (M-2 の (i)〜(iv) と F、import の制限) | V54a: クライアントに `SC` の path を 1 つ直書きする。V54b: 表に無い散文由来リテラルを足す。V54c: クライアントが `adapter` を import する (3 つ目の変異「テストから送信関数を直接呼ぶ」は C-35 の test module が対象なので WP-4 の 89) |
| 55〜59 | D-7 の 10〜14 行 | V55〜V59: 各行の変異 |
| 60 | D-7 の 15 行: クライアント module の §4.1 の表の key 集合が、テスト module に持つ設計 §4.1 の右列の N 番号の列 (`{N-15}`) と一致 | V60a: 表から行を 1 つ消す。V60b: 表に無い N 番号の行を足す |
| 61〜63 | D-7 の 16〜18 行 | V61〜V63: 各行の変異 |
| 64 | D-7 の 19 行 (v0.5 の形: alias の `audit_query` の項は送信 0 回で例外) | V64a: surface を path の接頭辞で決める。V64b: alias を control の base URL に結合する |
| 65〜70 | D-7 の 20〜25 行 | V65〜V70: 各行の変異 |
| 71 | 段 (1) の前の呼び出しは送信 0 回で例外、段 (1) の応答は response schema で検証した後にだけ capability document として読む (M-2) | V71: 段 (1) の前の呼び出しを送信する |
| 72 | M-2 の (i) の表の全 path が `SJ` か `SC` で解決する | V72: 表に解決しない path を 1 つ足す |
| 73 | クライアントが検証する schema (`SC` の data 面の項 (#10 の規則で alias を除く) が名指す request / response schema。テストが導く。名は直書きしない) の `used_keywords()` が実装済みの集合に収まることを、`CT/test_schema_check.py`:226-245 と同じ形のガードで固定 (D-7a) | V73: `IMPLEMENTED_KEYWORDS` から `maxProperties` を除く |
| 74 | `CT/schema_check.py` の module docstring (:1-38) が実装の範囲 (C-11 の schema と参照クライアントが検証する schema、足した 2 keyword) を述べ、未知の keyword で例外を出す性質が変わらない (`test_unknown_schema_keyword_fails_loud` が緑) | 監査照合 (`git diff` と集計行) |
| 75 | C-11 の判定が変わらない: 実装前と同じ集計 (D-7a、設計 §10 末尾の 3 つ目) | 監査照合 (前後の集計行の逐語) |
| 76 | クライアントの例外・失敗文・テストの assert に secret と `CredentialHandle` が入らない (D-9。D-7 の 7・12 で sentinel を確かめた上で、`git grep` で `CredentialHandle` の不在) | 監査照合 (`git grep` の逐語) |
| 77 | 新しい試験に skip / xfail が無く、下の「テスト」の全呼び出しが failed 0・skipped 0 | 監査照合 (`git grep` と集計行の逐語) |
| 78 | 本表に対応の無い行が無い | 監査照合 |

**道具の引数**: テスト = `tools/dev/pt.py -C .claude/worktrees/r108-wp3 -- conformance-tests/test_reference_client.py conformance-tests/test_schema_check.py conformance-tests/test_c11_document_conformance.py conformance-tests/test_c11_response_schema_conformance.py conformance-tests/test_conformance_docstring_position_refs.py -q`。変異 = `tools/dev/mutate.py "$SP/r108-wp3-mutations.json" -C .claude/worktrees/r108-wp3`。報告 = `$SP/r108-wp3-report.md` (M-2 の (ii) に足した行を出所付きで列挙する)。

**レビューの観点**: 失敗の種類を入れ替える変異が生き残らないこと (D-7 の v0.6 註)。HTTP status で分岐していないこと (#6)。許可集合 (M-2) の抜け道 (f-string の定数部分、bytes、`getattr` の名、docstring の扱い)。`code` を `errors.shape` の検証の前に読まないこと (#7)。

### 2.4 WP-4 — 条件 C-35 (実装担当)

**目的**: 設計 D-3・D-4・D-4a・§5 の 12 段を、参照クライアント 2 インスタンス (runtime / developer) で wire の 4 plug に対して回す条件 C-35 を executable にし、#12 の義務 (a)(b) の常設の証拠 (M-4) と D-6 の test module の pin を置き、`COND`・`CH`・`CM`・`RM` を追随させる。WP-2・WP-3 の merge の後に `r108` で行う。
**読むべき正本**: 設計 D-3・D-4・D-4a・D-5・D-6 (テスト module)・§5・§7・§10 の条件 WP・§11、M-3・M-4・M-7・M-10。雛形: `CT/test_c28_baseline_turn.py` (段の順と assert の形、`_BASELINE_OPERATORS` の導き方 :63-82)、`CT/conftest.py`:380 (`isolated`)・:422-451 (`provision_pair` の深さの注意)。**クラス**: D (`CM`)。**群**: レビュー群 4。

**注意**: §2.0 の実装担当への注意 1〜10。とくに空振り禁止 (`OC` §1.5 の 32)、主張は実測の後 (同 34)、確定文言はファイル経由 (同 35)、設計外の拡張は実装前に上げる (同 37)、同型性テスト (同 38)。

**静的な答え (D-4)**: `adapter` を wire 4 名で indirect に parametrize すると group は adapter 名になる (`CT/conftest.py`:95-132)。test の自己 assert (M-7) が常設の確かめで、結果を §5.5 の表 2 に書く。

**触ってよいパス**: `CT/test_c35_reference_client_turn.py` (新規)、`CT/test_reference_client.py` (D-6 の test module の pin を足すだけ)、`CT/test_c19_client_self_sufficiency.py` (M-4 の test を足すだけ)、`COND` (C-35 の行・凡例の 1 文 (M-3)・C-19 の Status に test 名)、`CH` (`## C-35` の節に executable 化の段)、`CM` (版 3.16、C-35 の Evidence と Status、#12 (b) の Evidence)、`RM` の :39 (条件数を C-00〜C-35 の 36 件に) だけ。両 peer の `src/` と adapter を触らない (変異の注入は別)。

**作業列の形** (設計 §5 の表と D-4a): `isolated` の面で `provision_application` → `wire_entry` → 2 インスタンス (base URL・送信関数・secret 1 本)。段 (1) で、クライアントが読んだ `surfaces.data.base_url` と `entry.base_url` の一致 (D-2a (2))、読んだ `role` と入口の申告の一致 (D-4a) を assert する。各段の operation 名・body の意図は test が与え、組み立てはクライアントが行う。

**完了条件 (79〜93) → 変異** (wire 上の作業列の変異は peer 側のもので、C-28 と同時に赤になってよい (設計 §5)。1 つの peer の変異はその peer の wire 2 plug で赤を確かめる。expect は red、収集時の assert は error)

| # | 完了条件 | 変異 |
|---|---|---|
| 79 | 選別は module 読み込み時の 1 か所 (`registered_adapters()` の `transport_kind`)、数 4 をその場で assert し、`adapter` を indirect に parametrize する | V79: `CT/registry.json` から asgi の 1 項を除く (expect=error) |
| 80 | 各 item が自分の `xdist_group` の名が adapter 名であることを assert する (M-7) | V80: parametrize の引数名を `adapter` 以外にする |
| 81 | 12 段が 4 plug で緑 | 監査照合 (集計行と plug ごとの結果行の逐語) |
| 82 | 段 (1): D-10 の 3 つの `contract_version` の一致、D-2a の base URL の一致、D-4a の role の一致を assert する | V82a: r2db の `wire_entry` で secret を入れ替える。V82b: MitateDB の data 面の宣言 `contract_version` を 1 つ上げる (C-19・C-29 と同時に赤でよい) |
| 83 | 段 (4)(5): enum 外の値の拒否の `details.field` だけで要求を直す | V83a / b: 各 peer の enum の値検証を外す (設計 §5 の変異候補 = フェーズ11 設計 §7 の段 (4)) |
| 84 | 段 (6)〜(8): dry_run・plan・idempotency の再送で行が 1 行、同じ `request_id` | V84a / b: 各 peer で再送時に idempotency の記録を無視する |
| 85 | 段 (9)〜(12): baseline の演算子・述語 update・declare-and-echo の delete・最終 query | V85a / b: 各 peer で `delete` が `affected` を返すのに行を消さない |
| 86 | #12 (a) の常設の証拠: クライアントが成功と分類した応答がすべて `media_type` で、段ごとに 1 件以上ある (クライアントの記録から assert) | V86: MitateDB の catalog の成功応答の media type を `text/plain` にする |
| 87 | #12 (b) の常設の証拠 (M-4): C-19 に足した test が 6 adapter で `role` を見る | V87: MitateDB の in-process の data 面の capability document から `role` を落とす |
| 88 | 段ごとの観測対象が 1 件以上あることを assert する (空振り禁止) | 監査照合 (assert の `file:line`) |
| 89 | D-6 の test module の pin (`CT/test_reference_client.py`): wire への要求はクライアントの公開 API 経由だけ (送信関数を直接呼ばない)、port から使うのは `provision_application` と `wire_entry` だけ、作業列に adapter 名・`transport_kind`・host による分岐が無い (選別の 1 か所を除く) | V89a: C-35 の test が `entry.send` を直接呼ぶ。V89b: C-35 の test が `iso.capability_document()` を呼ぶ。V89c: C-35 の test が `adapter.name` で分岐する |
| 90 | `COND` の C-35 の行が `executable (four wire adapters)` で、Condition 等は確定文のまま、Status の範囲の記述は実測 (変異の表) を引き、凡例の 1 文 (M-3) と C-19 の Status の test 名があり、`CT/test_conditions_register.py` が緑 | 監査照合 (`git diff` と集計行) |
| 91 | `CM` が 3.16 で、C-35 の Evidence が C-28 と同じ 5 SI (SI-05・SI-09・SI-10・SI-11・SI-14) の Common 節に、設計 §11 の開示 (wire の 4 plug のみ、TLS の例外 N-15、`operation_catalog_url` を wire で示さない、送信関数は pin の外) が Status に、#12 (b) の Evidence があり、`CT/test_control_mapping_register.py` が緑。変更した各ファイルについて `grep -c '<path>:' security/CONTROL_MAPPING.md` の前後の件数を報告した | 監査照合 (`git diff`・集計行・件数の逐語) |
| 92 | `RM`:39 の条件数、新しい試験に skip / xfail が無いこと、下の「テスト」の全呼び出しが failed 0・skipped 0 | 監査照合 (`git diff`・`git grep`・集計行の逐語) |
| 93 | 本表に対応の無い行が無い | 監査照合 |

**道具の引数**: テスト = `tools/dev/pt.py -C .claude/worktrees/r108 -- conformance-tests/test_c35_reference_client_turn.py conformance-tests/test_reference_client.py conformance-tests/test_c19_client_self_sufficiency.py conformance-tests/test_c28_baseline_turn.py conformance-tests/test_conditions_register.py conformance-tests/test_control_mapping_register.py conformance-tests/test_conformance_docstring_position_refs.py -q --durations=0` (C-35 の 4 node の所要時間は §3 の材料)。変異 = `tools/dev/mutate.py "$SP/r108-wp4-mutations.json" -C .claude/worktrees/r108`。報告 = `$SP/r108-wp4-report.md`。

**レビューの観点**: 作業列に契約外の知識が入っていないこと (段ごとの「組み立ての出所」が設計 §5 の列と合うか)。入口の申告を参照クライアントに渡していないこと (設計 §6 の v0.4 註)。`CM` の主張が実測を引いていること (`OC` §1.5 の 34)。

### 2.5 WP-5 — 記録と閉止 (監督。起草担当に渡してよい)

**読むべき正本**: `OC` §1.8 の 55・56、§1.15 の 77、§1.16 の 78・79。R-102 作業指示書 §2.7 (記録の WP の形)。**クラス**: D。

| 対象 | 書くこと |
|---|---|
| 設計 | v0.7 の註: 番号の割当 (§0)、行番号の引き直し (本書 §0.2 を指す)、§11 への実測の列挙 (「運ぶだけ」を確かめた範囲 = 受け渡し点、socket の nginx より先は確かめない、redirect を追わないことの wire 上の実測、xdist の group、C-11 不変、4 node の所要時間)。行を消さない (`OC` §1.8 の 56) |
| `RM` | v1.148: R-108 の閉止 (行を `docs/archive/docs/design/ROADMAP_POST_PHASE7_V1__LEDGER_CLOSED.md` の末尾へ逐語で移し §8.2 に索引行。`OC` §1.16 の 79)、§1 の現状の更新 (`OC` §1.8 の 55)、:56 (§0.1.3) の【再実測】(条件数と表記の内訳)、R-118 への追記 (設計 §11 の alias の (ii) と §9 の alias の裁定: co-host 配備で alias を結合すると data 面の stub に届く一致)、版数行と回転 (`OC` §1.16 の 78) |
| 引き継ぎ書 | `docs/work-orders/HANDOVER_<日付>_R108_FABLE.md` (`ROLES` の 7。「裁定」節を最終節に)、最新 2 通から外れる引き継ぎ書の `docs/archive/` への移動 |
| 本書 | §5 の記録 |

**完了条件 (94〜99) → 変異**:

| # | 完了条件 | 変異 |
|---|---|---|
| 94 | 設計 v0.7 の註 (上表) | 監査照合 (`git diff`) |
| 95 | 台帳の閉止・§1・:56 の再実測・R-118 の追記・版数と回転があり、`python3 tools/dev/ledger.py --check` が緑 | 監査照合 (出力の逐語) |
| 96 | 引き継ぎ書に「裁定」節があり、移すべき引き継ぎ書を同じ変更セットで移した | 監査照合 (`git status --short` の逐語) |
| 97 | `tools/check_doc_refs.py`・`tools/public_value_scan.py <触った全パス>` が緑、`tools/change_class.py <全変更セットのパス>` が D | 監査照合 (出力の逐語) |
| 98 | §5 に commit・ゲート・計測・監査・実測の記録がある | 監査照合 |
| 99 | 本表に対応の無い行が無い | 監査照合 |

## 3. 計測 (性能差分。監督)

設計 §11 は性能について何も主張しない。目標値を先に置かず、測った量を記録する (`OC` §1.3 の 27)。

1. 完了ゲートの壁時計への寄与: C-35 の 4 node と `CT/test_wire_entry.py`・`CT/test_reference_client.py` の所要時間を、WP-4 の `pt.py ... --durations=0` と完了ゲートの log の `slowest 25 durations` 節 (`OC` §1.6 の 44a) から転記する。完了ゲートの集計時間は前回 (R-102、4927 passed) と並べるが、負荷で変わるので判定に使わない。
2. 製品の非退行: 製品コードの変更は版の宣言とコメントだけである。`tools/perf_baseline.py --warmup 20 --n 200` (6 plug、K=1) を、基準 = main `1e8f7fb`、実装後 = merge 候補 で同じ日に交互に 1 巡ずつ取り、`RM` §0.1.4 の 1 (p50 +40% / p95 +50%) と突き合わせる。超えたら依頼者へ上げる。
3. 実施条件: 各 run の開始時の 1 分 load average を記録し、3.0 を超えた run は捨てて取り直す。他の pytest と nginx が無いことを確かめる (R-102 作業指示書 §3 の実施条件と同じ)。出力は `$SP/perf-r108-*.txt`。

## 4. 完了ゲートと受け入れ (監督)

- 完了ゲート: merge 候補 (local main に branch `r108` を `--no-ff` で merge した候補) の上で `tools/dev/gate.py -C <候補の worktree> --label r108` を単独実行する (レビュー担当・監査担当が pytest を走らせていないことを確かめてから)。集計行だけを正本にする (`OC` §1.6 の 41)。契約ファイルを触るので root suite の完走を完了条件にする (`OC` §1.1 の 10)。`-C` を渡し忘れると main を測る。
- `CT/COLLECTION_FLOOR` をゲートの実測に更新する (候補の上の commit)。`tools/` には触れないので `tools/tests` は回さない (触れたら `pt.py -- tools/tests -q` を別に回す)。
- pre-commit (公開値スキャン・doc 参照・台帳の固定欄) が緑。commit は `tools/dev/finalize.py`。
- 性能: §3 の表を `RM` §0.1.4 の 1 と突き合わせる。
- 受け入れ監査 (`evidence-auditor`、`ROLES` の 6): 全群のコードレビューの後に 1 回。監査対象は本書 §2 の全完了条件。パケットの「裁定」節は見出しと空表だけ。
- 閉止の前に、§1 の M-1〜M-10 と閉止までに出た監督裁定の一覧を依頼者に示して確認を求める。

## 5. 記録 (統合時に監督が埋める)

### 5.1 commit

| WP | worktree (branch) | commit (本体 → レビュー後 → 再確認後) |
|---|---|---|
| WP-1 | `r108` | `a77131d` → `3bd670b` → `cb6e295`。訂正註 4・5 は `4a8a6a8` |
| WP-2 | `r108-wp2` → `r108` へ merge | `51c770d` → `03b43ba` → `4f32224`。`r108` への merge `7aea515` |
| WP-3 | `r108-wp3` → `r108` へ merge | `7970d0f` → `b820658` → `cc6f9d6`。`r108` への merge `789e3ea` (`b820658` まで) と `a9202f0` (`cc6f9d6`) |
| WP-4 | `r108` | `e5d0e0a` → `495cd95` → `6bb9440` |
| WP-5 | `r108` | `9f08f1f` (起草、worktree `r108-wp5`。`r108` への merge `58bd05d`) → 記録の commit (本節の記入と訂正註 7、`COLLECTION_FLOOR`。`git log` の「R-108 WP-5 records」の行)。local main の取り込みは `2e51997` |

すべて r2fish / noreply、未 push。

### 5.2 完了ゲート

(候補の commit、集計行、judge、pg の差分、label、日時、`COLLECTION_FLOOR` の前後)

- 正本: `gate: 5014 passed, 2 subtests passed in 558.50s (0:09:18)`、judge=PASS、pg_database/pg_roles diff 0 (label r108、2026-10-01 21:18、merge 候補 `2e51997` = local main `9be46b7` を取り込んだ branch `r108`)。記録の commit を足した最終候補での再実行の集計行と main の merge commit は、merge の後の訂正註 (訂正註 7 の次) に記録する
- `COLLECTION_FLOOR`: 4927 → 5014 (記録の commit で更新)
- `tools/tests` (訂正註 2 の 6 により回す): `pt: 789 passed in 98.40s (0:01:38)` (`tools/dev/pt.py -C .claude/worktrees/r108 -- tools/tests -q`、`2e51997`。main の 786 との差 +3 は `tools/tests/test_deploy_smoke.py`)。merge 時の `finalize.py --tools-tests` の集計行は merge の後の訂正註
- 予備 (正本ではない): 訂正註 6 の 4 (`a9202f0`、label r108-pre)。

### 5.3 計測 (§3)

| 計測 | 形 | 基準 (`1e8f7fb`) | 実装後 | 判定 |
|---|---|---|---|---|
| C-35 の 4 node の所要時間 | `--durations=0` / ゲートの log | — | call は r2db http 0.47 s・r2db socket 0.45 s・MitateDB socket 0.41 s・MitateDB http 0.18 s、setup + call + teardown の合計 1.99 s (`pt.py ... --durations=0`、`2e51997`、2026-10-01 21:45。完了ゲートの log の `slowest 25 durations` には入らない。参考: WP-4 の報告、`e5d0e0a` の上の call は r2db socket 0.61 s・MitateDB socket 0.35 s・r2db http 0.30 s・MitateDB http 0.14 s) | 記録のみ |
| `CT/test_wire_entry.py`・`CT/test_reference_client.py` の所要時間 | 同上 | — | `CT/test_wire_entry.py` 合計 2.57 s、`CT/test_reference_client.py` 合計 0.59 s (同じ run、3 ファイルで `pt: 70 passed in 5.30s`。どちらも `slowest 25 durations` に入らない) | 記録のみ |
| 完了ゲートの集計時間 | ゲートの集計行 | 前回 R-102 の値 | 558.50 s (0:09:18)、5014 passed。前回 R-102 は 464.40 s と 910.29 s (4927 passed)、同日の他の 2 回は 587.55 s と 967.55 s (4927 passed)。負荷で変わるので判定に使わない | 記録のみ |
| K=1 全 plug・全 op の p50 / p95 | `tools/perf_baseline.py --warmup 20 --n 200` | main `9be46b7` (計測対象の製品コードは `1e8f7fb` と同じ)。2 run、各 21 行 (下の表は run 1) | `2e51997`。2 run、各 21 行 (下の表は run 1) | 閾値 (p50 +40% / p95 +50%) の内側。run 1 の最大は p50 +7.6% (MitateDB-api の mutate)・p95 +6.8% (MitateDB-api-http の batch)、run 2 の最大は p50 +13.5% (MitateDB-api-socket の mutate)・p95 +18.9% (r2db-api-socket の query)。`backend_calls` は 2 run とも全 21 行で前後同じ |

(各 run の開始時の load average と、捨てた run の理由)

監督、2026-10-01。前後を続けて 1 run ずつ、2 巡。run 1 (21:17): 開始時の 1 分 load average は 基準 1.73 / 実装後 2.01、開始前に pytest 0 を確認 (nginx は未確認)。run 2 (21:44): 2.59 / 2.85、前後に pytest 0・nginx 0 を `ps` で確認 (受け入れ監査が run 1 の実施条件の記録の欠けを指摘したので取り直した)。捨てた run は無い。どちらの木も clean (`commit=9be46b7` / `commit=2e51997`)。出力は scratchpad の `perf-r108-<before|after>-k1-run<N>.txt`。

run 1 の全行 (p50 と p95 は ms、基準 / 実装後 (差)。`backend_calls` は 基準 / 実装後):

| plug | op | p50 | p95 | backend_calls |
|---|---|---|---|---|
| MitateDB-api | batch | 0.179 / 0.172 (-3.9%) | 0.189 / 0.189 (+0.0%) | 39.00 / 39.00 |
| MitateDB-api | cross_entity | 0.132 / 0.133 (+0.8%) | 0.144 / 0.148 (+2.8%) | 18.00 / 18.00 |
| MitateDB-api | mutate | 0.105 / 0.113 (+7.6%) | 0.117 / 0.122 (+4.3%) | 11.00 / 11.00 |
| MitateDB-api | query | 0.136 / 0.141 (+3.7%) | 0.149 / 0.151 (+1.3%) | 12.00 / 12.00 |
| MitateDB-api-http | batch | 2.156 / 2.242 (+4.0%) | 2.256 / 2.409 (+6.8%) | 34.00 / 34.00 |
| MitateDB-api-http | cross_entity | 1.353 / 1.396 (+3.2%) | 1.547 / 1.635 (+5.7%) | 19.00 / 19.00 |
| MitateDB-api-http | mutate | 1.148 / 1.170 (+1.9%) | 1.297 / 1.353 (+4.3%) | 14.00 / 14.00 |
| MitateDB-api-http | query | 1.385 / 1.476 (+6.6%) | 1.443 / 1.534 (+6.3%) | 17.00 / 17.00 |
| MitateDB-api-socket | batch | 5.502 / 5.586 (+1.5%) | 6.437 / 6.486 (+0.8%) | 34.00 / 34.00 |
| MitateDB-api-socket | cross_entity | 4.839 / 4.922 (+1.7%) | 5.696 / 5.792 (+1.7%) | 19.00 / 19.00 |
| MitateDB-api-socket | mutate | 4.570 / 4.672 (+2.2%) | 5.420 / 5.550 (+2.4%) | 14.00 / 14.00 |
| MitateDB-api-socket | query | 4.742 / 4.845 (+2.2%) | 5.976 / 6.127 (+2.5%) | 17.00 / 17.00 |
| r2db-api | batch | 0.873 / 0.878 (+0.6%) | 1.228 / 1.249 (+1.7%) | 1.00 / 1.00 |
| r2db-api | mutate | 0.220 / 0.230 (+4.5%) | 0.305 / 0.300 (-1.6%) | 1.00 / 1.00 |
| r2db-api | query | 0.119 / 0.118 (-0.8%) | 0.131 / 0.134 (+2.3%) | 1.00 / 1.00 |
| r2db-api-http | batch | 1.930 / 2.031 (+5.2%) | 2.035 / 2.131 (+4.7%) | 23.00 / 23.00 |
| r2db-api-http | mutate | 1.740 / 1.836 (+5.5%) | 1.834 / 1.933 (+5.4%) | 19.00 / 19.00 |
| r2db-api-http | query | 1.681 / 1.784 (+6.1%) | 1.782 / 1.870 (+4.9%) | 18.00 / 18.00 |
| r2db-api-socket | batch | 5.443 / 5.493 (+0.9%) | 5.595 / 5.658 (+1.1%) | 23.00 / 23.00 |
| r2db-api-socket | mutate | 5.235 / 5.288 (+1.0%) | 5.371 / 5.426 (+1.0%) | 19.00 / 19.00 |
| r2db-api-socket | query | 5.161 / 5.218 (+1.1%) | 5.309 / 5.361 (+1.0%) | 18.00 / 18.00 |

### 5.4 受け入れ監査と閉止

(パケットの判定の集計、未充足と証拠不足の扱い、依頼者確認の結果)

- 受け入れ監査: `evidence-auditor` 1 回 (候補 `2e51997`、パケット = scratchpad の `acceptance-packet-r108.md`)。完了条件 1〜99 は充足 99・未充足 0・証拠不足 0 (構造的な赤は訂正註 1 の 3 のとおり完了ゲートで判定)。§4 の受入条件の証拠不足 2 件と観察 2 件・設計疑義 1 件の扱いは訂正註 7 の 3
- 依頼者確認 (§1 の M-1〜M-10 と訂正註 1〜6 の監督裁定、R-121 の起票、設計 v0.7 の §7 の註の読み替え): 依頼者確認待ち。依頼者指示 (2026-10-01、逐語)「裁定は監督の推奨で進め、依頼者には最後にまとめて確認を求めてください」の下で進めたので、local main への merge の後に一覧を示して確認を求め、結果は merge の後の訂正註に逐語で記録する (R-102 の先例。§4 の「閉止の前に」は「閉止の記録の確定の前に」と読む = 訂正註 7 の 4)

### 5.5 実装前の実測と静的な答え

表 1 — #12 の義務 (a)(b) (WP-1 の先頭。完了条件 1):

| plug | 面 | operation | 成功応答の `content-type` | capability document の `role` |
|---|---|---|---|---|
| r2db-api (http+postgres) | data | capabilities・catalog・operation-catalog・schema・mutate・query | 6 operation とも 200 `application/json` | `runtime` (runtime の credential で読んだ文書) |
| 同 | control | control_capabilities | 200 `application/json` | `control` |
| 同 | data (control credential) | capabilities | 401 `application/problem+json` (`AUTH_INVALID`)。文書を返さない | — (文書なし) |
| r2db-api (socket) | (同じ 3 行) | | 上の 3 行と同じ (data 6 operation 200 `application/json` / control 200 `application/json` / control credential 401 `application/problem+json` `AUTH_INVALID`) | `runtime` / `control` / 文書なし |
| MitateDB-api (http) | (同じ 3 行) | | 同上 | `runtime` / `control` / 文書なし |
| MitateDB-api (socket) | (同じ 3 行) | | 同上 | `runtime` / `control` / 文書なし |

出所: 訂正註 1 の 4 と WP-1 の実装担当の探査 (一時の probe を置いて `pt.py -s` で 1 回実行し、削除した。出力の逐語は監督の scratchpad の `r108-wp1-probe-output.txt`)。in-process の 2 plug は wire が無く測っていない。義務 (a)(b) は 4 plug とも満たす。3 行目の経路は両 peer の data app が application credential だけを認証するので文書を返さず、義務 (b) は返す文書に掛かるので破れていない。

表 2 — 設計 §10 末尾の 6 項目と D-4・D-7a・「運ぶだけ」:

| 項目 | 静的な答え (本書) | 実測 (埋める) |
|---|---|---|
| C-19 の bearer の合成走査と socket harness の `_build_client` の pin に入口が干渉しない | 干渉しない見込み (§2.2 の静的な答え) | 完了条件 39 の前後の集計行: 前 `pt: 112 passed in 127.37s (0:02:07)`、後 `pt: 112 passed in 69.30s (0:01:09)` (どちらも `CT/test_c19_client_self_sufficiency.py`・`CT/test_socket_harness.py` の 2 ファイル、WP-2 の報告)。干渉しない |
| D-4 の xdist の group | adapter 名 (`CT/conftest.py`:95-132) | 完了条件 80 の自己 assert の結果: 4 node とも緑 (WP-4 の報告、`e5d0e0a`)。V80 (parametrize の引数名を変える) は「'r2db-api' is not a selected wire adapter」で、V80b (conftest の group の hook を外す) は「xdist_group is 'registry-guards'」で赤。`CT/test_wire_entry.py` の同じ自己 assert は V38b で赤 (WP-2 の報告)。group は adapter 名 |
| D-7a の後の C-11 の判定 | 変わらない見込み (§2.3 の静的な答え) | 完了条件 75 の前後の集計行: 前 `pt: 72 passed in 59.37s`、後 `pt: 75 passed in 23.89s` (差 +3 は `CT/test_schema_check.py` の新規 3 test。C-11 の 2 ファイルだけでは 45 passed)。差し戻し 1 の後も `pt: 75 passed in 22.15s` (WP-3 の報告と差し戻し 1 の報告)。判定は変わらない |
| 「運ぶだけ」を確かめられる plug | 4 plug とも transport の受け渡し点まで。socket の nginx より先は確かめない (M-8) | 完了条件 34 の結果: 4 plug とも受け渡し点の `httpx.Request` が入力と一致 (WP-2 の報告の `pt: 221 passed in 150.43s (0:02:30)`)。V34a (r2db socket が URL だけを書き換える transport の派生。訂正註 4 の 10)・V34b は赤。正規形でない method / URL (34c、V34c) と fragment・userinfo (訂正註 6 の 1、V34d) は送らずに例外。socket の nginx より先は確かめない |
| wire 上で redirect を追わない | 3xx を返す URL は plug ごとに実測 (§2.2) | 完了条件 35 の URL・status と結果: 4 plug とも末尾 slash 付きの `/v1/capabilities/` が 307 (`Location` は r2db http `https://r2db-http-pg-data.conformance.invalid/v1/capabilities`、MitateDB http `http://mitatedb-http-pg.conformance.invalid/v1/capabilities`、socket の 2 plug は loopback の host で port を持たない `/v1/capabilities`)。参考: `/v1` は ASGI の 2 plug で 404、socket の 2 plug で 301 (`text/html`、`Location` は port 付き)。送信関数は 307 をそのまま返し、受け渡し点の呼び出しは 1 回。V35 (`follow_redirects=True`) は赤 |
| 義務 (a)(b) を両 peer が既に満たす | 満たす見込み (§2.1 の静的な出所) | 表 1: 満たす (4 wire plug。control credential で data 面を読む経路は 401 で文書を返さない) |
| 新しい key で既存の key 集合のピンが赤になるか | 赤になるのは `CT/test_contract.py`:2048 (`endpoint_fields_note`) と :403-406 (`OperationCatalogEntry` の dict 一致) の 2 つ (完了条件 21・22 で差し替え)。最上位・`versioning`・`errors` の key 集合を固定するテストは無い (`git grep -n 'set(contract\|keys()) ==' -- conformance-tests r2db-api/tests MitateDB-api/tests tools` の実測、2026-10-01) | WP-1 の集計行: `pt: 2 failed, 187 passed in 28.10s` (契約系 6 ファイル。赤の 1 つは訂正註 1 の 3 の構造的な赤、もう 1 つは訂正註 1 の 2 で直した)。key 集合のピンで赤になったのは 3 つ (訂正註 1 の 1)。差し戻し 1 の後 `pt: 1 failed, 188 passed in 119.60s (0:01:59)` (構造的な赤だけ)、r2db `pt: 397 passed`、MitateDB `pt: 234 passed` |
| `OperationCatalogEntry` の description を `schema_check.py` が keyword として扱うか | 扱わない (`ANNOTATION_KEYWORDS`、`CT/schema_check.py`:81-92) | — |
| `operation_catalog_url` の上書きが同じ endpoint を別の綴りで名指したときの起動時の扱い | 両 peer とも絶対 URL (scheme と host がある) であることだけを見て、値をそのまま宣言する。正規化も、組む URL との比較もしない: `R/main.py`:214-219、`R/control_main.py`:589-597、`M/config.py`:173-177・:250・:286-288、`M/control_composition.py`:66-71。したがってその配備には #12 (c) が掛かり、peer の `operation_catalog` はその綴りでも認証を求めるので (c) を満たさない (設計 §11 の v0.6 の項のとおり) | — (静的な読解で足りる) |

## 6. 訂正註 (本文は書き換えない。`OC` §1.8 の 57)

**訂正註 1 (2026-10-01、WP-1 の実施。監督裁定)**

1. (触ってよいパス) `CT/test_operation_catalog_register.py` を WP-1 の触ってよいパスに足す。`test_endpoint_fields_note_present_and_non_empty` が `endpoint_fields_note` の key 集合を 3 つに固定しており、#3・#4 の `path` で赤になる。集合を 4 つにし docstring の件数を直した (実装担当の報告、受け入れ)。§5.5 表 2 の「赤になるのは 2 つ」は 3 つである。
2. (M-5・M-10) declared の C-35 の行の Evidence cell は file 名を持たない散文だけにする: 起草案の末尾の「 -- `conformance-tests/test_c35_reference_client_turn.py`, `conformance-tests/test_reference_client.py`」を外した。未作成の file を名指すと `CT/test_conditions_register.py::test_conditions_md_every_test_name_reference_resolves` が赤になる (実測)。既存の行も Evidence は散文で、test file 名は Status に書く (C-20〜C-34 の形)。確定文ファイル `$SP/confirmed-r108-condition.txt` を同じに改めた。WP-4 は test file 名を Status に書く (完了条件 90)。
3. (完了条件 26・各 WP の「テスト」) `CT/test_conditions_register.py` の marker 系の 3 本 (`test_every_executable_condition_has_a_marked_test`・`test_every_marked_condition_id_is_registered_in_conditions_md`・`test_every_marked_condition_id_maps_to_an_executable_status`) は、条件の test を全部は収集しない呼び出しでは構造的に赤になる (前者は C-19・C-29 だけの収集で executable 33 行が未収集と出る。C-35 は含まれない)。判定は suite 全体を収集する完了ゲートで行う。WP の呼び出しでは残りの test が緑であることを見る (WP-1: 2 の直しの後、名前解決の test は緑)。
4. (完了条件 1 の実測、§5.5 表 1) 4 wire plug の data 面 (capabilities・catalog・operation-catalog・schema・mutate・query) と control 面 (`control_capabilities`) の成功応答はすべて `application/json`、capability document の `role` は data 面が `runtime`、control 面が `control` — 義務 (a)(b) を両 peer は既に満たす。表 1 の 3 行目 (control credential で data 面の capabilities を読む) は 4 plug とも 401 `application/problem+json` (`AUTH_INVALID`) で文書を返さない: 両 peer の data app は application credential だけを認証する。義務 (b) は返す文書に掛かるので破れていない。契約の文は変えず、設計 §11 の記録 (WP-5) に「その経路は文書を返さない」と書く。
5. (`check_comment_provenance.py --base 1e8f7fb`) 宣言 4 か所の src は版の literal の変更で §4.1 (1) (code changed) が出る。他の FAIL は 0、`--register` は緑 (実装担当の報告)。版上げの変更セットでは正当な赤である。

**訂正註 2 (2026-10-01、WP-1 のコードレビュー 1 巡目 = 観点 A / B の並列。監督裁定)**

確定文 12 文・obligations の entry・置き場・index・写しの byte 一致は両観点とも一致を確認した。指摘 (A 5 件、B 5 件、重なり 4 件) の裁定:

1. (A-1 / B-1、直す) `spec/README.md` と両 peer の宣言の直前のコメントが義務 (c) まで「既に満たす」と言い切っていた。(a)(b) の実測と「(c) の掛かる URL を宣言する plug は無い」に限る (差し戻し 1 の 1。文面は監督確定)。
2. (A-3 / B-3、直す) `CT/test_contract.py` の要約コメントの「of another origin」を、組む URL 以外という表現に直す (差し戻し 1 の 2)。
3. (B-4、直す) `spec/README.md` と `spec/CONTRACT_HISTORY.md` の (c) の要約に、要約である旨の断り書きを足す (差し戻し 1 の 3)。
4. (A-2 / B-2、直す = WP-4 に足す) 配備者向けの文書が 1.14.0 の義務 (c) を書いていない。WP-4 の触ってよいパスに `r2db-api/deploy/DEPLOYMENT_RUNBOOK.md` (`R2DB_OPERATION_CATALOG_URL` の行) と `MitateDB-api/docs/cloud-run-cloud-sql.md` (`MITATEDB_OPERATION_CATALOG_URL` の段落) を足し、次の確定文 (監督確定。`<own path>` は各文書の既存の書き方に合わせた `GET /v1/operation-catalog`) を既存の文の直後に足す: 「Under contract 1.14.0 a value set here that is not, character for character, the derived URL obliges the deployment to serve the operation catalog there, as `application/json`, to a request that carries no credential -- a 1.14.0 client presents none at such a URL -- so do not set it to another spelling of the derived URL: this service's own `GET /v1/operation-catalog` requires a credential at every spelling.」 行が増える文書は、`CM` がその文書を指す行参照のうち挿入位置より後のものを増えた行数だけ引き直し、引き直した各参照の行の字面が前後で同じであることを script で照合して報告する (完了条件 91 の「前後の件数」に加える)。`r2db-api/README.md`:113-118 は runbook を指すだけなので変えない。起動時に別綴りの上書きを拒む検査は足さない (観察: 「同じ endpoint の別綴り」は一般には機械判定できず、(c) を満たすかは上書き先の配備の性質である。設計 §11 の v0.6 の項が開示済み)。
5. (A-4 / B-5、直す = WP-5) `spec/CCR_DISPOSITION.md` の 19 の段が引く §5.5 の表 1 は、監督が WP-5 で訂正註 1 の 4 の実測から埋める。
6. (A-5、直す = 差し戻し 1 の 4。本項目の範囲に足す) `tools/deploy_smoke.py` の `_request` が credential を付けたまま redirect を追う。契約 1.14.0 の `versioning.url_composition` の client の規則に本 repo の道具が反するので、同じ変更セットで redirect を追わない形に直し、`tools/tests/test_deploy_smoke.py` (新規) と変異 1 件で固定する。WP-1 の触ってよいパスに `tools/deploy_smoke.py`・`tools/tests/test_deploy_smoke.py` を足す。§4 の「`tools/` には触れないので `tools/tests` は回さない」は成り立たなくなる: 統合時に `finalize.py --tools-tests` を回す。

**訂正註 3 (2026-10-01、WP-1 の差し戻し 1 の再確認レビュー = 1 起動。監督裁定)**

ゲートを止める指摘は無い。低 4 件はすべて同じ変更セットで監督が直した (`tools/deploy_smoke.py`・`tools/tests/test_deploy_smoke.py`):

1. (3xx の本文を読まない分岐が未固定。レビューの変異 RV-1 が緑で生き残った) test の 302 に JSON でない本文 (`text/html`) を持たせ、`_request` が `(302, None)` を返すことと、stage の失敗文が「GET /v1/capabilities -> 302 (expected 200)」に等しいことを assert する。RV-1 は赤になった。
2. (sentinel の api_key が失敗文に出ない完了条件に変異が無い) レビューの RV-2 を変異表に加えた (赤)。
3. (`_NoRedirect` の docstring の契約の写しから「, at any URL this rule forms」が落ちていた) 逐語に戻した。
4. (R1-4 の赤が status の assert で止まり、漏洩が観測されていなかった) 転送先の server が要求を受けていない assert を status の assert の前に移した。R1-4 の赤は「the redirect target received a request」で、bearer 付きの要求が観測される。

実測 (監督、2026-10-01): `pt: 3 passed in 2.02s` (`tools/tests/test_deploy_smoke.py`)。変異 `R1-4` / `RV-1` / `RV-2` はいずれも `expect=red got=red`、`mutate: 3 mutations, 3 as expected, restores verified 1/1 files (sha256 x2)`。

**訂正註 4 (2026-10-01、WP-2 のコードレビュー 1 巡目 = 観点 A / B の並列。監督裁定)**

実装担当の判断 (hook は factory を返す `_wire_transport_factory()`、同型性の行は 3 本で 208、3xx の URL は全 plug で末尾 slash の 307) は受け入れた。指摘 (A 3 件、B 7 件、重なり 1 件) の裁定と、レビュー担当の変異の実測 (監督、`51c770d` に対して): `RB-1` 赤 (host の綴りが受け渡し点で変わる)、`RB-2` 緑、`RB-3` 赤、`mutate: 3 mutations, 2 as expected`。

1. (B-1、高、直す) `RT/test_r78_pool_wait_stats.py` に `_ISOMORPHIC_TARGETS` の件数の assert (`== 205`) が残り、完了ゲートで赤になる。WP-2 の触ってよいパスに同 file を足し、完了条件 40 に「件数を名指す他の assert を `git grep` で実測する」を足す (本書 §2.0 の表の漏れ)。
2. (A-1 / B-2、中、直す = (a)) `send` は httpx の正規形でない method / URL を黙って直して運んでいた。両 peer の `wire_entry` で、組んだ要求の method と URL が入力と違えば送らずに例外にする (確定文「exactly as given」は変えない)。完了条件 34 に 34c (小文字の method・大文字の host・`..` の path で例外、受け渡し点 0 回) と変異 1 件を足す。
3. (A-2、低、直す) secret が空のときにもう一方の secret が失敗文に出る assert を、添字だけを出す形にする。
4. (B-3、低、直す) `WireEntry` の secret の 2 欄を `field(repr=False, compare=False)` にする。`RB-2` が緑だったので (`-q` では欄ごとの差分が出ない)、固定は欄の構造の assert と変異 1 件で行う。
5. (B-4、低、対応不要) 完了条件 36 の失敗文の脚は `RB-3` で単独の赤を実測した。
6. (A-3、低、直す = 開示) 圧縮された応答では返す header と本文が食い違う。`CA` §31.3 に 1 項足す (いまの 4 plug では届かない)。
7. (実装担当の判断 (5)、直す) 接続失敗が例外になることを socket の 2 plug の test 1 本で固定する。
8. (B-5、記録) `check_comment_provenance.py` の対象は両 peer の `src/` だけで、WP-2 は `src/` を触っていない。報告の当該行は対象外の出力である。
9. (B-6、起票 = 台帳 `RM` §8.1 に新しい行。番号は WP-5 の版上げで main を読んで振る) socket plug の 307 の `Location` が宣言の port を持たない (実測)。harness の nginx と r2db の本番雛形は `listen` の port と `proxy_set_header Host $host` の組で、redirect を追う client は別の port へ送られる (静的な読解)。DB の利用者が気づく (redirect の宛先が違う) ので起票する。本項目では `CA` §31.2 に実測の 1 文を足すだけ。
10. (B-7、情報) 変異 V34a は本書の形 (`_LazySocketClient` 経由) ではなく URL だけを書き換える transport の派生で測った。受け入れ (client 層の header で先に赤になる紛れが無い)。

**訂正註 5 (2026-10-01、WP-3 のコードレビュー 1 巡目 = 観点 A / B の並列。監督裁定)**

実装担当の判断 (公開 API は `fetch_capabilities` と `call`、例外 class の構成、violation の path だけを例外文に入れる、surface は `control.` 接頭辞と `control_endpoints` の key 名で決める、base URL の一致は client に持たせない) は受け入れた。指摘 (A 6 件、B 9 件、重なり 3 件) はすべて同じ変更セットで直す。レビュー担当の変異の実測 (監督、`7970d0f` に対して): `RA-1`・`RA-2`・`RA-3`・`RB1a`・`RB1b`・`RB2`・`RB4`・`RB5` は緑 (生き残り)、`RB3` は赤。

1. (A-1、中) D-7 の 11 行・23 行の test が成功 JSON の本文しか持たず、失敗の種類を入れ替える変異 (`RA-1`・`RA-2`) が生き残った。problem 形の本文の場面を足す。
2. (A-2 / B-9、低〜中) base URL の末尾判定が文字列の `endswith` で、query・fragment の中の base path でも結合して送る。URI の path で判定し、query か fragment を持つ base URL は送らない。
3. (A-3 / B-8、低〜中、(b)) `ProblemResponse` の文に応答の `code` がそのまま入る。契約 `errors.codes` が列挙する `code` のときだけ文に入れる (属性は常に持つ)。
4. (A-4 / B-2、低) 静的 pin の (iii) と docstring の免除を文の部品に限り、`.args` と `.__doc__` での持ち出しを赤にする。M-2 の (iii) は「`raise` の直下の例外の構築呼び出しの引数のうち、文字列の定数・f-string の定数部分・文字列の連結・`.join` の receiver」と読む。
5. (A-5 / B-7、低、fail closed) `Content-Type` が 2 本以上の応答は解釈しない失敗にする。
6. (A-6、低) NaN / Infinity を含む body は送らない。応答の NaN と深いネストは解釈しない失敗にする。
7. (B-1、低、案 1) 完了条件 73 のガードは `SC` の全項 (alias を除く) が名指す schema に掛ける。§2.3 の完了条件 73 の「`SC` の data 面の項」を「`SC` の全項 (#10 の規則で alias を除く)」と読み替える (設計 D-7a の「クライアントが検証する schema」どおり。クライアントは control 面の schema も検証する)。
8. (B-3、低) 4xx の status で `media_type` の応答を成功として読む場面を足す (`RB2`)。
9. (B-4、低、外す) `localhost` の許可は設計 §4.1 の N-15 (loopback か `.invalid`) に無いので外す。
10. (B-5・B-6、低) 段 (1) の応答検証は `RB3` の赤で固定を確かめた。`ContractMismatch` は「解釈しない失敗」の側の class として受け入れ、`role` の無い文書の場面を足す (`RB4`)。設計 D-7 の v0.6 註への 1 文は WP-5 の設計 v0.7 の註に入れる。

**訂正註 6 (2026-10-01、WP-2・WP-3 の再確認レビューと WP-4 のコードレビュー 1 巡目。監督裁定)**

1. (WP-2 の再確認、低、直した = 監督) `send` の拒否の検査が fragment と userinfo を素通ししていた (どちらも要求行に載らない)。両 peer の検査を同じ文で広げ、test に 2 場面を足した。変異 `V34d` 赤、`pt: 116 passed` (`CT/test_wire_entry.py` ほか 2 ファイル)、同型性は r2db `5 passed`・MitateDB `4 passed`。
2. (WP-3 の再確認、低 2 件、直した = 差し戻し 2) 静的 pin の持ち出し経路 (例外の束縛の `str(e)`、名前の `__doc__`、`inspect`) を閉じた: クライアントの import を閉じた表 (`ALLOWED_IMPORTS`) で固定し、例外の名前への束縛と名前の `__doc__` を赤にした。(iii) の免除は「位置引数がちょうど 1 つで keyword の無い構築のその引数」と `message=` の値に限り、`ProblemResponse` は文を `message=` で受ける。M-2 の (iii) はこの規則で読む。追加の変異 6 件は赤、`pt: 87 passed`。
3. (WP-4 のレビュー、A 2 件・B 7 件、重なり 2 件。すべて同じ変更セットで直す = 差し戻し 1) レビュー担当の変異 `RA4-1`〜`RA4-3`・`RB4-1`〜`RB4-3` は 6 件とも緑 (生き残り) だった。
   - (A-1 / B-1、中) C-35 の test module の pin が port の他の操作を呼ぶ経路 (`request.getfixturevalue`、`registered_adapters()`、`adapter` の object) と `adapter_name` での分岐を検出しない。6 形を赤にし planted と変異で固定する。
   - (A-2 / B-6、低) 段 (11) は復唱句の key を位置ではなく `required_confirmation` の名前で引く。
   - (B-2、低) C-35 の Status の変異の要約を、測った plug を名指す形に直す。
   - (B-3、低) C-19 の Status から削った 2 句の記録を `CH` の `## C-19` の節へ移す (WP-4 の触ってよいパスを `CH` 全体に広げる)。
   - (B-4、裁定 = SI-06) #12 (b) の Evidence は `CM` の SI-06 Common に置く (完了条件 91 の「C-28 と同じ 5 SI」は C-35 の Evidence についての文で、#12 (b) の置き場は本裁定による)。設計 §7 の SI-03・SI-06 の行への註は WP-5。
   - (B-5、低) C-19 に足した test は `test_c19_data_documents_declare_a_role` と名付ける (見るのは data 面の文書)。
   - (B-7、観察、直す) turn 末尾の media type の比較は送信ごとの検査と重複するので外し、段ごとの成功応答 1 件以上の assert を残す。
4. (予備の完了ゲート、監督、`a9202f0`) `gate: 5014 passed, 2 subtests passed in 711.50s (0:11:51)`、judge=PASS、pg_database/pg_roles diff 0 (label r108-pre)。正本は merge 候補の上で取り直す (§4)。

**訂正註 7 (2026-10-01、WP-4 の再確認レビュー、受け入れ監査、記録。監督裁定)**

1. (WP-4 の再確認 = 1 起動、5 件。差し戻し 2、commit `6bb9440`) 差し戻し 1 の 7 項目は直っていると確認された。レビュー担当の変異 `RC-1`・`RC-2` は `495cd95` で緑 (生き残り)、直しの後は監督の実行で赤 (`mutate: 2 mutations, 2 as expected, restores verified 1/1 files (sha256 x2)`)。
   - (1、中、直した) `request.node.funcargs[...]` 経由で fixture を取る経路。`request` は `_own_group(request)` の唯一の引数としてだけ許す。
   - (2、中、直した) `import conftest` / `import adapter as port` で関数の中から registry と port を引く経路。plain な import と関数の中の `.registered_adapters` を赤にする。
   - (3、低、既知の穴 = `OC` §1.12 の 71) 値の束ね直し (module 水準の `_A = registered_adapters()` を関数から引く、`n = self.adapter_name` で分岐する等) は検査を足さず、pin の docstring の Known gaps に書いた。**pin の範囲の線引き (監督裁定)**: C-35 の test module の pin とクライアント module の pin は書き方の規律を守る静的検査で、製品の欠陥がこの穴から完了ゲートを抜けることは無い。閉じた形で書ける経路は塞ぎ、data-flow を追わないと塞げない経路は既知の穴として pin の docstring に書く。以後、隣の形が見つかっても同じ線で扱う (WP-3・WP-4 で pin の隣の形の指摘が計 4 巡続いたため)。`COND` の C-35 の Status は経路を列挙せず pin の test 名を挙げる。
   - (4、低、直した) journal 節のコメントが外した検査を述べていた。
   - (5、観察) C-35 の Status から差し戻し 1 で削った句 (plug 名の列挙、ASGI の transport は host を見ない) は `CH` に移さない: main に載ったことの無い branch 上の文で、main の旧文 (declared) は逐語で記録済み。「ASGI は host を見ない」は `CM` の SI-10 Common と設計 §11 に残る。`CH` の段落の直後の `---` の表示は既存の並び (同ファイルにあと 4 か所) で、本項目では扱わない。
2. (WP-2 の再確認の `V34d` の集計行。受け入れ監査の指摘) 監督の実行: `V34d expect=red got=red OK | 1 failed in 0.48s | restore=ok`、`mutate: 1 mutations, 1 as expected, restores verified 1/1 files (sha256 x2)` (commit `4f32224` の前)。
3. (受け入れ監査、`2e51997`) 完了条件 1〜99 は充足 99。§4 の証拠不足 2 件・観察 2 件・設計疑義 1 件の裁定:
   - (§4 の (a)、直した) `tools/tests` の集計行が未提出 → §5.2 に `pt: 789 passed` を記録。
   - (§4 の (b)、直した) 計測の実施条件 (他の pytest と nginx が無い) の確認が記録に無い → run 2 を取り直し、前後に pytest 0・nginx 0 を記録 (§5.3)。
   - (完了条件 1・96 の `git status --short` の逐語が報告に無い、観察) 監査が木と履歴で確かめ、充足と判定した。
   - (性能の基準の commit、直した) §5.3 に実物の `9be46b7` と書いた (計測対象のコードは `1e8f7fb` と同じ)。
   - (設計疑義: C-35 の Status が変異を `V79-V89` の範囲で引き、レビュー由来の `RA4` / `RB4` の赤も同じ列挙にある、観察 = (a) 現状のまま) `CH` の C-35 の節が `RA4` / `RB4` を名指すので追跡できる。Status の字数は残り 91 字である。
   - (観察 1: WP-4 の再確認の裁定が訂正註に無い、直した) 本註の 1。
   - (観察 2: C-19 の Status が 2,998 / 3,000 字、観察) 次に足す変更は register の test (`MAX_CELL_LENGTH`) が必ず赤にするので黙って通らない。そのときは文を `CH` へ移す。C-30・C-06・C-05 も 2,983〜2,993 字で、余白の少なさは本項目より前からある。
4. (§4 の読み替え) 「閉止の前に…依頼者に示して確認を求める」は、local main への merge の後に一覧を示して確認を求め、結果を次の訂正註に逐語で記録する、と読む (依頼者指示 2026-10-01「裁定は監督の推奨で進め、依頼者には最後にまとめて確認を求めてください」、R-102 の先例)。
5. (§0 の基点) 本書は基点を `1e8f7fb` と書くが、WP-1 の commit `a77131d` の親は `b656dbf` (`1e8f7fb` + `tools/` の 3 ファイル = `tools/check_comment_provenance.py` の Known gaps 8 番) である。本項目の対象と重ならない。merge 候補は local main `9be46b7` (CI の起動条件の変更) を取り込んだ `2e51997`。
6. (§4 の `tools/tests`) 訂正註 2 の 6 のとおり `tools/` に触れたので、merge は `finalize.py --tools-tests` で行う。

## 付録 — 確定文の抜き出し script

確定文は、設計 §9.1 の表の「新しい文 (英文、確定案)」の列の 12 セルと、#12 の行の obligations の列の entry を、`<V-1>` → `1.13.0`、`<V>` → `1.14.0`、`<N>` → `19` の 3 つの置換だけで写したものである。手で打ち直さない。script は監督の scratchpad の `r108-fixed-text/extract.py` に置いた (起草時に実行済み)。scratchpad は次のチャットから読めないので、全文を下に載せる。再生成: worktree を cwd にして `python3 "$SP/r108-fixed-text/extract.py" . "$SP/r108-fixed-text"` (script を `$SP/r108-fixed-text/extract.py` に保存してから)。

```python
#!/usr/bin/env python3
"""Extract the 12 confirmed contract sentences and the obligations entry of
R-108 from docs/design/REFERENCE_CLIENT_V0_1.md section 9.1, substituting only
<V-1> -> 1.13.0, <V> -> 1.14.0 and <N> -> 19 (supervisor numbering 2026-10-01).

usage: python3 extract.py <repo root> <output dir>
writes <output dir>/01.txt .. 12.txt (each = the cell text, no trailing newline)
and <output dir>/obligations-entry.json (the entry text, no trailing newline).
"""
import json
import sys
from pathlib import Path

SUBSTITUTIONS = (("<V-1>", "1.13.0"), ("<V>", "1.14.0"), ("<N>", "19"))
HEADER = "| # | JSON path | 現行の文 | 新しい文 (英文、確定案) | N | obligations |"
DESIGN = "docs/design/REFERENCE_CLIENT_V0_1.md"


def substitute(text: str) -> str:
    for old, new in SUBSTITUTIONS:
        text = text.replace(old, new)
    for marker in ("<V-1>", "<V>", "<N>"):
        assert marker not in text, marker
    return text


def main() -> None:
    root, out = Path(sys.argv[1]), Path(sys.argv[2])
    lines = (root / DESIGN).read_text(encoding="utf-8").splitlines()
    start = lines.index(HEADER)
    assert lines[start + 1].startswith("|---"), lines[start + 1]
    rows = {}
    for line in lines[start + 2:]:
        if not line.startswith("| "):
            break
        cells = line.split(" | ")
        assert len(cells) == 6, (len(cells), line[:60])
        number = int(cells[0].lstrip("| ").strip())
        rows[number] = cells
    assert sorted(rows) == list(range(1, 13)), sorted(rows)
    out.mkdir(parents=True, exist_ok=True)
    for number, cells in rows.items():
        (out / f"{number:02d}.txt").write_text(substitute(cells[3]), encoding="utf-8")
    entry_cell = rows[12][5].rstrip(" |")
    prefix = "entry: `"
    begin = entry_cell.index(prefix) + len(prefix)
    end = entry_cell.index("`", begin)
    entry = substitute(entry_cell[begin:end])
    parsed = json.loads(entry)
    assert parsed["version"] == "1.14.0" and parsed["subordinate_ruling"] == 19, parsed
    (out / "obligations-entry.json").write_text(entry, encoding="utf-8")
    print(f"wrote 12 sentences and the obligations entry to {out}")


if __name__ == "__main__":
    main()
```

起草時の出力の sha256 (設計 v0.6 から生成。再生成の照合に使う):

```text
5281128d6a1532f558945b5a0b44de8b533625925086549939e301ef9a1813cd  01.txt
23a3373da22df308d6dbf511016e5b4615e2e61963036f2e61f0296e9334a997  02.txt
3b56859952e1b4277a80ef4b103641b2fbf298e0443d32390e15694337f799e9  03.txt
5144e0b8983177d250431521cf10a4f523679fe0fe805d394d2be3d594d75942  04.txt
1928a6f070401d87a5e1358a5366f721e68216ccb4d3cb59ce5691ca6d48f73a  05.txt
3d95f19ae1d8fa3816bd849d5de07536a66a8a435e635d09de38e0f635c5c2b7  06.txt
370f8a0a8c3088a9b2eb26df144c7fcd3a9f89af2ea8216700867c28c8fb9cdd  07.txt
e76af43640fddf8876b18f3088a7d033269c6dd8e693e7116c1c0454ceae816b  08.txt
0210d25a634dfc07473b20033f7eaefd9334094d9577727375c87fb44930002b  09.txt
d6b7372538b44d5c2fd670fa7b636b2e120af12093d67bf12be3ab64eabc44dd  10.txt
28936d8eca687c4eaa6e1e34beb92ba91e129c041ff1059b8949965be7857c69  11.txt
87af7ec9b802162dd41cb4f5a50f2b216f7ff5a1bc01356afc5af6e31ee6c27e  12.txt
b58df86dc9bbcbf6a716c7300d8ac26cd4e2229c617a13d327ad31c01464033e  obligations-entry.json
```

12 文はどれも `CT/test_contract_history_register.py` の marker の pattern (:66-80) に当たらない。当たるのは #12 の `subordinate ruling 19` だけで、`versioning.version_binding` は既存の見出しを持つので新しい見出しは要らない (起草時に pattern を 12 ファイルに当てて実測)。
