# 依頼者裁定資料 — R-30・R-118・R-120 v0.2

版: v0.2 (2026-10-03)。状態: 依頼者裁定済み (2026-10-03。各行の「裁定 (逐語)」欄。台帳 v1.154)。対象: 台帳 (`RM` §8.1) の R-118・R-30・R-120。

## 0. 要約

| 行 | 裁定の問い | 推奨 |
|---|---|---|
| R-118 | (i) alias の期限句 3 箇所 (`spec`:453・:40 (c)・:636) を「保持し、撤去は major 版でのみ行う」の文に書き直す minor 版 (1.15.0。alias と両 peer の route・stub は残す) にするか、(ii) 今 alias を撤去する major 版 (2.0.0) にするか | (i) (案 A 書き直し) |
| R-30 | (i) SI-00 の containment を DB 側の境界で満たすものと文書で確定し、1 process が複数 Application の DSN を保持する構成を正式に許すか、(ii) 本番の serving set を 1 process 1 Application に限る配備姿勢を宣言し、SI-00 の文書にその姿勢を本番の既定として記すか | (ii) (案 B 配備姿勢の宣言) |
| R-120 | (i) 着手し、MitateDB の 3b と同型の実体単位の共有 lock (案 B) で設計に進むか、(ii) 着手せず `CM`:1534 の開示のまま置くか | (i) (着手する。閉じ方は案 B) |

## 1. 本資料の性質

- 依頼者が 1 回で裁定できるように 3 行の材料を並べる。推奨は書くが裁定はしない。**本資料は何も確定しない。** 裁定は各行の「裁定 (逐語)」欄に逐語で記録する (`OC` §1.7 の 51)。
- 推奨の決定軸: 第一に堅牢で安全、第二に最大限の自由。
- 作成環境は cloud session (PostgreSQL 無し)。R-120 の窓は再現していない (構造のみ、未再現)。未確認・未計測・推測はその語で明記する。
- 基点 rev: local HEAD `05a60c0` (origin/main は `4241b55`)。行番号はすべて 2026-10-02 に現物から取り直したもの。
- 出所の記法は `file:line` (`OC` §0)。本資料の略記: `RM` = `docs/design/ROADMAP_POST_PHASE7_V1.md`、`OC` = `docs/work-orders/OPERATING_CONDITIONS.md`、`CM` = `security/CONTROL_MAPPING.md`、`RC` = `docs/design/REFERENCE_CLIENT_V0_1.md`、`CA` = `docs/design/CONFORMANCE_ADAPTER_V1.md`、`spec` = `spec/data-service-api.v1.json`。§4 に限り `R` = `r2db-api/src/r2db_api/postgres.py`、`M` = `MitateDB-api/src/mitatedb_api/`。
- 利用者 = AI エージェントを含む、共通契約 `spec/` を通じて API を呼ぶ client (`OC` §1.15 の 77)。
- 変更クラスの正本は `RM` §9 の 8 の表 (`RM`:594-601)。A = `.md` のみ、B = peer のコード等、C = `spec/`・`conformance-tests/`・catalog 宣言値、D = `security/` 配下・`CLAUDE.md` 境界節・`_ISOMORPHIC_TARGETS` 集合の増減・公開ゲート (`RM`:601。C の全部 + 依頼者裁定の逐語記録 + 版付き security-contract 決定)。複数に跨れば最も重いクラス。規模 (S / M / L) は `OC` §1.13 の 73-74。
- 表の「契約版数」欄は `spec` の版を上げるかどうか。`RM`:600 の C の証拠列「契約版数の更新」は `spec` を触る案にだけ掛かり、`conformance-tests/` だけを触る案では版は動かない。

## 2. R-118 — audit_query の alias の保持期限の文言が現物と食い違う

### 2.1 問題

`spec`:453 の `deprecation_note` は alias `/v1/audit/query` を「for one further minor version after 1.4.0」保持すると書くが、契約は 1.14.0 (`spec`:6) で alias (`spec`:446-462) は残っている。`spec/CCR_DISPOSITION.md`:146 が予定した「1.5.0 以降に除去するかの別途裁定」は行われていない。契約だけを読む client は、alias が在るのか・いつ消えるのかを文から決められない。

現物の所在:

- 期限句 "one further minor version" は `spec` に 3 箇所: :40 (`version_binding` の (c))、:453、:636 (`control_endpoints.audit_query.semantics`)。同じ句は `spec/CONTRACT_HISTORY.md`:110・:216・:391、両 peer の control_http のコメント (`r2db-api/src/r2db_api/control_http.py`:394、`MitateDB-api/src/mitatedb_api/control_http.py`:436)、README (`r2db-api/README.md`:90・:214、`MitateDB-api/README.md`:137) にもある。
- 両 peer の契約複製も 1.14.0 (`r2db-api/src/r2db_api/capabilities_document.py`:88、`MitateDB-api/src/mitatedb_api/capabilities_document.py`:145)。canonical は `control_endpoints.audit_query` (`spec`:630-642、path :632)。
- `spec`:453 自身が "removal would be a non-additive contract change" と書き、`versioning.compatibility` (`spec`:36) は "removal or semantic change requires a new major version." と定める。deprecation 済みの項の撤去を minor で許す文は spec に無い (grep "deprecat" の該当は :35 :40 :453 :636 :948 :2081 のみ)。
- alias に依存する句: `versioning.url_composition` (`spec`:35) の except 句 ("this rule forms no URL for it")、`definitions.OperationCatalogEntry.description` (`spec`:2081) の alias 文と直後の "Every other entry"、`version_binding` (`spec`:40) の 1.4.0 (b) 補筆・(c)・条件付き義務 (5)、`obligations` (`spec`:68-69) の義務名 `audit_query_canonical_classification_with_alias`、`spec`:948。
- `CM` も alias と data stub を証拠に引く: SI-00 両 peer 節 (`CM`:96・:97・:99・:144・:145)、ほか `CM`:196・:203・:667・:1840・:1847・:1864・:1969。
- 両 peer の route: control 面に alias と canonical の両方があり同じ handler (`r2db-api/src/r2db_api/control_http.py`:462-463、`MitateDB-api/src/mitatedb_api/control_http.py`:509-510)。data 面にも `/v1/audit/query` の stub がある (`r2db-api/src/r2db_api/http.py`:766、handler :718-742 は `_authenticate` の後に常に `CAPABILITY_UNSUPPORTED` (status 400、`r2db-api/src/r2db_api/service.py`:507-528); `MitateDB-api/src/mitatedb_api/http.py`:1300、handler :1269-1282 は `_authenticate` の後に CapabilityError)。control / audit credential を data 面に出すと `spec`:40 の補筆どおり AUTH_INVALID (401)。
- 同一 origin の配備 (`RC`:352 の (ii)): alias を control の base URL に自前で結合すると `<origin>/v1/audit/query` になり、r2db の nginx 雛形 (`r2db-api/deploy/nginx/r2dbsvc-api-8443.conf.example`:113 `location /v1/` → data、:166 `location /control/v1/` → control) と `conformance-tests/socket_harness.py`:303-315 では data 側 stub に届く。現行 (1.14.0) の url_composition は alias の URL を組まない (`spec`:35) ので、契約に従う client はこの URL を dial しない。dial するのは alias を自前で結合した旧 client だけで、stub が拒否する (害は誤った拒否 code であって越境ではない)。`CM`:203 は、現在の登録 plug に同一 origin の配備は無いと書く。
- conformance の pin: `conformance-tests/test_contract.py`:1138-1146 (:1145 `"alias" in deprecation_note`、:1146 `"one further minor version" in deprecation_note`)。文言変更には `spec/CONTRACT_HISTORY.md` と `spec/CONTRACT_HISTORY_MANIFEST.json` (:71 ほか) の更新も要る (`conformance-tests/test_contract_history_register.py`:343)。撤去なら更に `PIN_1_14_0_URL_COMPOSITION` (`conformance-tests/test_contract.py`:1319-)、`PIN_1_14_0_OPERATION_CATALOG_ENTRY_DESCRIPTION` (同 :289-)、`PIN_1_4_0_OBLIGATION_B_ADDENDUM` (同 :1712-)、`PIN_1_12_0_AUDIT_WINDOW_NOTE` (同 :1152-)、件数 `== 20` (`conformance-tests/test_operation_catalog_register.py`:131、`conformance-tests/test_contract.py`:2451)、catalog の byte 再生成、`conformance-tests/test_c09_audit_evidence.py`:654、peer の route disjoint test (`r2db-api/tests/test_control_http.py`:569、`MitateDB-api/tests/test_audit_query.py`)。
- 先例: 文言を現物に合わせる変更を minor とした 1.12.0 (`RC`:296 の記述)。

### 2.2 放置した場合 / 利用者が気づくか

契約だけを読む client は alias が在るか・いつ消えるかを文から決められない。契約に従う client は url_composition により alias を dial しないので実害は無いが、契約が自己矛盾を抱えたまま版を重ねる。**気づくか: はい** (契約の文を読めば矛盾が見える。起票理由と同じ)。

### 2.3 選択肢

| 案 | 内容 | 変更クラス | 規模 | 契約版数 | 触る経路 | conformance | 欠点 |
|---|---|---|---|---|---|---|---|
| A 書き直し (推奨) | `spec`:453・:40 (c)・:636 の期限句 3 箇所を同じ文言で書き直す。主案の文言は「保持し、撤去は major 版でのみ行う (時期は定めない)」、強い変種として「次の major 版で撤去する」を併記する。alias・両 peer の control route・data stub は不変。`spec`:35・:2081 は不変。`spec/CCR_DISPOSITION.md`:146 の未裁定 (撤去するか) は「撤去は major 版でのみ」と埋まる (時期は次の major の設計で決める) | C (`spec/`) + B (peer のコメント。文言のみ) + A (README) | S | minor (1.15.0) | `spec`:40・:453・:636、`spec/CONTRACT_HISTORY.md`:110・:216・:391 と MANIFEST、両 peer の契約複製と版文字列、コメント 2 箇所 (`r2db-api/src/r2db_api/control_http.py`:394、`MitateDB-api/src/mitatedb_api/control_http.py`:436)、README 3 箇所 (`r2db-api/README.md`:90・:214、`MitateDB-api/README.md`:137)、`conformance-tests/test_contract.py`:1146 の pin (:1145 の "alias" は残る) | pin 1 件の文言更新 + 版一致 (C-19 等) の既存 test が 1.15.0 を要求。新条件は不要 | alias が無期限に残る。同一 origin 配備の URL 重なり (`RC`:352 (ii)) は残る (stub が拒否するので越境は無い)。運用開始後に撤去する費用は major 版の費用のまま変わらない (契約に従う client は alias を使わないため) |
| B 撤去 | `endpoints.audit_query` を削除し、`spec`:35 の except 句と :2081 の alias 文・"other" を削り、:40 (b)(c)(5)・:69 の義務名・:636・:948 の alias 依存句を整理。両 peer の control route (alias 側) と data stub を撤去 | D (`CM` の SI-00 両 peer 節ほか :96-99・:144-145・:196・:203・:667・:1840-1864・:1969 の主張が消える) + C + B | L (契約 major、設計レビュー 2 回) | major (2.0.0。`spec`:453 自身が「removal would be a non-additive contract change」、:36 が removal を major と定める) | spec 7 箇所、両 peer の route 2 箇所ずつ、catalog 再生成、§2.1 の撤去時の pin 一覧、`CM` の上記各行、`RC` §11、`CA` | pin 6 本以上と catalog 件数 (`== 20` → 19)、route disjoint test、`conformance-tests/test_c09_audit_evidence.py`:654 を書き換え。1.x の全 PIN の扱いを major でどうするかの設計が要る | major 版の費用が 1 項目の撤去に対して過大。1.4.0 の目的 (pre-1.4.0 形の client を壊さない) を放棄。安全上の利得は無い (alias は control 面で canonical と同じ handler・同じ認証; data stub は既に拒否) |
| C 撤去を minor で行う | B と同じ撤去を 1.15.0 で行う | D + C + B | L | minor (契約の文に反する) | B と同じ | B と同じ | **却下。** `spec`:36 と :453 の自分の文に反する。契約の compatibility 規則そのものを変える versioned 決定が要り、以後「removal は major」が信用できなくなる |
| D 何もしない | 開示のまま | — | — | — | — | — | **却下。** 契約の自己矛盾が残り、起票理由 (利用者が気づく) がそのまま残る |

- 撤去する場合の `spec`:35・:2081 の扱い (B): except 句と alias 文を同じ major の変更セットで削り、"Every other entry" を "Every entry derived from endpoints" に戻す。A では両文とも不変。
- 同一 origin の URL 重なり: A では残るが、契約に従う client は dial せず stub が拒否する。B では両 peer の stub も撤去するので消える (旧 client は 404 (NOT_FOUND) を受ける)。spec の項だけ消して stub を残す中間形は route と契約が食い違うので採らない。`spec`:40 の (5) ("both the canonical POST /control/v1/audit/query path and the POST /v1/audit/query alias actually answer requests as the identical operation") を「同じ origin の両 path」と読むと、同一 origin 配備の alias path は data stub に届くので (5) を満たさない読みが成り立つ (control の host 上の両 path と読めば満たす。読みは分かれる)。配備側の回避として nginx 雛形で `location = /v1/audit/query` を control upstream へ回す案があり (契約の変更ではなく Class B の雛形変更)、案 A を採る場合の付随作業の候補になる。

### 2.4 推奨: A

理由 (決定軸順): 安全は A でも B でも変わらない (alias は control 面で canonical と同一の operation・同一の認証、data 面は stub が拒否、契約に従う client は alias を dial しない)。堅牢さは A で足りる (期限句 3 箇所の自己矛盾が消え、撤去は major 版でのみと一意になる)。自由は A が最大 (旧形の client を壊さず、撤去の時期も次の major の設計に委ねられる)。B は major 版の費用を 1 項目の撤去に払う上に 1.4.0 の目的を放棄し、安全上の利得が無い。

### 2.5 裁定の問い

R-118: (i) alias の期限句 3 箇所 (`spec`:453・:40 (c)・:636) を「保持し、撤去は major 版でのみ行う」の文に書き直す minor 版 (1.15.0。alias と両 peer の route・stub は残す。「次の major 版で撤去する」の強い変種を望むなら「(i) + 強い変種」) にするか、(ii) 今 alias を撤去する major 版 (2.0.0) にするか。

裁定 (逐語): 依頼者 2026-10-03 「(i) 書き直し minor 1.15.0 (推奨)」 (本資料 §0 の問いを 2026-10-03 に提示し、依頼者が選んだ選択肢の表示文。「(推奨)」は選択肢に付した印)

### 2.6 台帳行の起票文の検証

- 起票文「`spec/data-service-api.v1.json`:432 は ... 契約 1.12.0 に alias は残っている」: 行は現物 `spec`:453、契約は 1.14.0。期限句は :453 のほか :40 (c)・:636 にもある。事実関係 (期限句が当てはまらない、alias は残る、client は文から決められない) は今も成立。
- 「両 peer は alias を control 面に置いている」は事実。data 面の stub (§2.1) には触れていない (事実の補足であり誤りではない)。
- 「Class D 見込み (`spec/`)」: 案 A は C (下限 C、`security/` に触れない)。案 B は `CM` の証拠が消えるので D。台帳の「Class D 見込み」は案 B には当たる。
- 陳腐化した参照 (本資料では直さない): `RM`:475 の `:432`・「1.12.0」; `RC`:351 の `spec:37` (現物 :40) と「両 peer は 1.12.0」(現物 1.14.0); `RC`:352 の `:432`・「1.12.0」・`spec:37`; `RC`:296 の `versioning.compatibility (:33)` (現物 :36)。

## 3. R-30 — SI-00 の境界と複数 Application DSN 保持の関係

### 3.1 問題

SI-00 (`security/SECURITY_INVARIANTS_V1.md`:65-87) は "a single application-facing implementation defect" も対象に書く (:68) が、1 process が複数 Application の DSN を保持する構成との関係は `security/` のどこにも書かれていない。両 peer の serving set は `R2DB_SERVE_APPS` / `MITATEDB_SERVE_APPS` の全 slug の runtime / developer DSN を 1 process に保持する (`r2db-api/src/r2db_api/main.py`:418-425、`MitateDB-api/src/mitatedb_api/main.py`:320-327)。この構成を SI-00 が許すのか禁じるのかは未確定である。

現物の所在:

- SI-00: Implementation freedom :84 "The invariant requires containment, not one particular topology."、Verification :87 は credential の喪失だけを名指す。Rationale / Scope / 註は無く、`security/SECURITY_INVARIANTS_V1.md`・`security/THREAT_MODEL_V1.md` とも "process"・"DSN" は 0 件 (grep)。
- T-13 (`security/THREAT_MODEL_V1.md`:130-133): :133 の "where feasible" は横移動の限定に掛かり、後半 "compromise of one application-facing component is not assumed to grant Control Plane authority" は Control Plane だけを扱い他 Application に触れない。T-03 (:80-83) は他 Application 越境を扱うが process 内保持には触れない。
- `CM` の SI-00 節 (r2db :86-111、MitateDB :136-158): 主張は plane 到達可能性、application ごとの DB と CONNECT grant (r2db :87-89。MitateDB は SI-01 節 :237 付近)、role 分離、composition root が control credential store を持たないこと、deprovision の権限境界。複数 DSN 保持への言及は無い。近い記述は SI-01 の :216 と :239 (接続 / pool の分離であり process 境界の主張ではない)。
- 実装: 使用箇所 r2db :629、MitateDB :536。下限 1 (r2db :313、MitateDB :229)、上限の検査は無い。`r2db-api/deploy/env/api.env.example`:59-62 は "a real deployment may serve one slug or many" と書き、例は `alpha,beta`。
- platform DSN: data process は serving set と別に platform DSN を保持する (r2db `R2DB_PLATFORM_DSN`、`r2db-api/src/r2db_api/main.py`:35・:385・:429; MitateDB `MITATEDB_PLATFORM_DSN`、`MitateDB-api/src/mitatedb_api/main.py`:34・:299)。その role の grant は registry の全 Application の行に及ぶ: r2db `r2dbsvc_api` は `r2db-api/migrations/0005_credential_store.sql`:135 (credentials の SELECT)、`r2db-api/migrations/0007_application_audit.sql`:179 (application_audit の INSERT)、`r2db-api/migrations/0015_credential_request_rate.sql`:82 (credential_request_rate の SELECT, INSERT, UPDATE); MitateDB `mitatedbsvc_api` は `MitateDB-api/migrations/0002_registry_and_functions.sql`:254、`MitateDB-api/migrations/0005_application_audit.sql`:225、`MitateDB-api/migrations/0016_credential_request_rate.sql`:82 (同じ 3 種)。
- 現行配備 (文書上): `docs/work-orders/DEPLOY_PHASE6_20260904.md`:1554 (r2db は SLUG=sandbox)、`MitateDB-api/docs/cloud-run-cloud-sql.md`:1251 (`SERVE_APPS` に 1 つ。文書の値は合成例)。**実配備の Application 数は未確認。**
- 試験構成: 複数 Application の serving set を組む test / conformance fixture は、`SERVE_APPS` のカンマ区切りの grep では env example と配備文書以外に見つからなかった。他の経路で組む fixture の有無は未確認。
- `docs/design/OBJECT_STORAGE_BINARY_API_V0_1.md` の A-1 (依頼者決定 2026-09-11。:7、:14): object storage は application ごとの private bucket・provider identity・application 専用の object-capable 実行単位。:152・:160 は「object-capable API 実行単位は一 application だけを serve」。:205 (残課題) は非 object-capable では複数 application 一 process 配備が存続する前提で書かれている。同文書は候補 v0.2 (:3)。
- 台帳 R-113 (閉止 2026-09-29) の worker (`docs/design/MULTI_PROCESS_WORKER_V0_1.md`:151-153 uvicorn `--workers N`、:176・:187 `build_app()` と serving set の検証が worker ごと、:341 MitateDB は served application ごとに永続接続で N process なら N 組): 全 worker が同じ serving set を持ち、process ごとに Application を分ける案は無い。
- 送り元: `docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md`:584-586 (同文書 U-13 (2): 版付きの security-contract 決定としてフェーズ11 へ)。台帳行は `RM`:456。

### 3.2 放置した場合 / 利用者が気づくか

SI-00 の文 (implementation defect を含む) と複数 DSN を保持する実装の関係が未確定のまま残る。現行配備が文書どおり各 1 Application なら実害は無いが、複数 Application を 1 process で serve した瞬間に、process 内のコード実行 (T-13) 1 件が served 全 Application の runtime / developer DSN に届く構成になり、それを SI-00 が許すのか禁じるのかを誰も答えられない。なお platform DSN (§3.1) は serving set と無関係に全 Application の registry 行に及ぶ。`CM` の SI-00 の証拠もその配備形を扱わない。**気づくか: いいえ** (配備の内部。利用者は API からは見えない)。

### 3.3 選択肢

| 案 | 内容 | 変更クラス | 規模 | 契約版数 | 触る経路 | conformance | 欠点 |
|---|---|---|---|---|---|---|---|
| A 境界の文書確定 (複数を正式に許す) | SI-00 に註 (または Implementation freedom に 1 文) を足し、containment は DB 側の境界 (application ごとの DB・CONNECT grant・role) と SI-01 の要求ごとの DSN 選択で満たすこと、1 process が複数 Application の DSN を保持する構成は SI-00 の範囲内であること、process 内のコード実行は T-13 (where feasible) の扱いであることを明記。`CM` の SI-00 両 peer 節に Control / Evidence (SI-01 :216 の test を引く) を足す | D (`security/`) | M | 無し (spec 不変) | `security/SECURITY_INVARIANTS_V1.md` SI-00、`security/THREAT_MODEL_V1.md` T-13 (任意)、`CM` SI-00 両 peer 節 | 新条件は不要。既存の SI-01 の証拠を SI-00 に引く | SI-00 の "single application-facing implementation defect" を論理欠陥に限る読みを文書で固定する = invariant の弱め方を明文化する。T-13 の 1 件で served 全 Application の DSN が同時に漏れる構成を正式に許す |
| B 配備姿勢の宣言 (推奨) | 本番の serving set は 1 process 1 Application と宣言し (A-1 が object-capable 実行単位に求める姿勢を API 全体の既定にする)、複数 Application の serving set は試験・開発の構成として残す (コードは変えない)。SI-00 の註には「SI-00 の containment は DB 側の境界で満たす (:84 の『topology を定めない』はそのまま)。それに加えて本番の配備姿勢として 1 process 1 Application を既定とし、複数 Application の 1 process 配備は試験・開発の構成とする (禁止ではなく、本番の既定)」と記す。`CM` SI-00 両 peer 節に配備姿勢の Control と証拠 (runbook・env example・配備記録) を足す。`r2db-api/deploy/env/api.env.example`:59-62 と `docs/design/OBJECT_STORAGE_BINARY_API_V0_1.md`:205 の「複数 application 一 process」の前提文を宣言に合わせて直す | D (`security/`) + B (env example) + A (runbook) | M | 無し | SI-00、`CM` SI-00 節、`r2db-api/deploy/env/api.env.example`、両 peer の runbook、`docs/design/OBJECT_STORAGE_BINARY_API_V0_1.md`:205 | 新条件は不要 (配備姿勢は conformance で測れない。証拠は配備記録) | 宣言のみで強制が無い (起動時検査なし)。本番で複数 Application を 1 process で serve する自由は失う (試験・開発では残る。serve したい配備は process を分ける費用を払う)。platform DSN の到達範囲は変わらない。台帳 R-113 の worker は serving set を共有するので process 数を増やしても Application は分かれない (本案とは独立) |
| C 強制 (B + 起動時検査) | B に加え、本番モードで serving set が 2 以上なら起動を拒む (または明示の opt-in flag を要求) | D + B (両 peer のコード) | M〜L | 無し | B の全部 + 両 peer の `main.py` の serving set 構築 (r2db :418-425、MitateDB :320-327) + test と変異 | 起動時検査の test は peer ローカル (composition root 単位の C-26 系に足せるかは要検討) | env example の `alpha,beta` と試験構成の変更 (試験構成は未確認)。opt-in flag を足すと既定が fail-closed になり B より強い。費用は両 peer のコードと test・変異。強制の必要性は、未確認の実配備数を配備記録で確かめてから決められる (後から足せる) |
| D 何もしない | — | — | — | — | — | — | **却下。** `docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md` の U-13 が「版付きの security-contract 決定」として送った件が未決のまま残る |

### 3.4 推奨: B

理由 (決定軸順): 安全は B が最も高い (T-13 のコード実行 1 件が届く Application の data (runtime / developer DSN) は 1 Application 分に限られ、SI-00 の文を弱めずに済む)。platform DSN (registry の credentials の SELECT、application_audit の INSERT、credential_request_rate の UPDATE) はどの案でも全 Application に及び、本行の裁定では変わらない。堅牢さ: A-1 (object-capable 実行単位は 1 application) と同じ姿勢で、台帳 R-36 の設計が始まったときに二つの姿勢を持たずに済む。費用は今ゼロ (現行配備は文書上 各 1 Application。実数は未確認)。自由: コードは複数 Application を serve できるまま残り、試験・開発の構成を縛らない (本番で複数を 1 process で serve する自由は失う)。A は invariant の弱め方を明文化する決定であり、安全第一の軸に反する。C は B より強いが、両 peer のコードと test・変異の費用がかかり env example と試験構成に手が入る。強制の必要性は、未確認の実配備数を配備記録で確かめてから決められる (後から足せる)。

### 3.5 裁定の問い

R-30: (i) SI-00 の containment を DB 側の境界で満たすものと文書で確定し、1 process が複数 Application の DSN を保持する構成を正式に許すか、(ii) 本番の serving set を 1 process 1 Application に限る配備姿勢を宣言し (複数は試験・開発の構成、コードは変えない)、SI-00 の文書にはその姿勢を本番の既定として記すか。

裁定 (逐語): 依頼者 2026-10-03 「(ii) 配備姿勢の宣言 (推奨)」 (本資料 §0 の問いを 2026-10-03 に提示し、依頼者が選んだ選択肢の表示文。「(推奨)」は選択肢に付した印)

### 3.6 台帳行の起票文の検証

- 起票文の 3 点 (SI-00 節が複数 DSN に触れない / T-13 が where feasible / 現行配備は各 1 Application) は今も成立。ただし 3 点目は文書上の記述で、実配備数は未確認。
- 陳腐化した参照: 台帳行の r2db `main.py:315-323` は現物では :310-320 が env の解析で、構築は :418-425 (約 +103)。MitateDB `main.py:270-279` は現物 :320-327 (約 +50)。

## 4. R-120 — r2db の DML 検証と書き込みの間の alter の窓

### 4.1 問題

r2db の DML は enum / nullable を registry から読んで Python で検証し (`R`:1128-1150 の `_load_catalog`、`R`:1815-1837 の `_apply`)、物理制約は無い。`transact` の `_load_catalog` (`R`:1670) から最初の write (`R`:1838) までの間に同じ application の `alter_field` または `add_field` (nullable: false) が LOCK TABLE を先に取ると、DML は schema 操作の commit 後に古い宣言で検証済みの値を書き、宣言に反する行が残る (構造のみ、未再現)。MitateDB は `docs/design/MITATEDB_APPLICATION_SERIALIZATION_V0_1.md` の 3b (実体単位の共有 / 排他の advisory lock) でこの重なりを閉じており、両 peer の安全性の結果が食い違う。

現物の所在:

- 物理制約: registry `_r2db_field_constraints` は `r2db-api/migrations/0003_provision_application.sql`:316-322。0003:205-210 の DOMAIN CHECK は jsonb の object / array 形だけ。named CHECK は 0003:196-204 が「considered and rejected」(63 byte 超過と CheckViolation の DETAIL が行全体を含む disclosure の 2 理由。unnamed なら両方回避できると同箇所が書く)。enum は scalar 4 型の typed column にだけ宣言できる (`R`:2337-2345)。
- 窓: `transact` の transaction 開始 `R`:1637 → idempotency lock :1646 → `_load_catalog` :1670 → 最初の write :1838 (`_insert`)。isolation の明示は無く READ COMMITTED (`R`:1408 と :2321 のコメントも同前提)。`alter_field` は `apply_schema` の transaction (`R`:2118) 内で schema lock :2157 → `LOCK TABLE {table} IN SHARE ROW EXCLUSIVE MODE` :2330 → 走査 :2332-2352 → `_write_field_constraints` :2353 → revision bump :2410 → commit。`add_field` (nullable: false) は `R`:2257-2278 で LOCK TABLE (:2268) → `SELECT 1 … LIMIT 1` の空確認 (:2270) → `_add_field` (:2278)。SHARE ROW EXCLUSIVE は INSERT の ROW EXCLUSIVE と衝突する (`R`:2321 のコメントが同じ主張)。
- 順序 (A): DML が先に INSERT → schema 操作が LOCK TABLE で待つ → commit 後に走査・空確認するので違反は CONFLICT (安全)。順序 (B): schema 操作が先に LOCK TABLE → DML の INSERT が待つ → schema 操作の commit 後に DML は `R`:1670 で読んだ古い `table_info` で検証済みの値をそのまま書く (catalog は再読されない)。走査・空確認は LOCK の後なので INSERT 待ちの行は含まれない。`add_field` では古い catalog (field 無し) で検証済みの INSERT が通り、宣言では NULL 不可の field が NULL の行が残る。**(B) が「宣言に反する行が残る」経路** (構造のみ、未再現)。
- 台帳 R-102 の schema lock (3a、`R`:1405-1415、`pg_advisory_xact_lock` の排他のみ、共有版は無い) は `apply_schema` の 1 箇所 (`R`:2157) だけで取られ、`transact` は取らない (docstring `R`:1410-1412 「A data operation (`transact`) and a `query` never do」。この「輪は無い」の前提が lock 順序の設計根拠)。
- MitateDB の 3b: DML 4 経路が entity ごとに `pg_advisory_xact_lock_shared(ns, hashtext(e))` を sorted で取る (`M`/backend_postgres.py:255-265 の `_ENTITY_LOCK_SHARED`、:609-614 `lock_entities`; 呼び出し元 `M`/cell.py:1959 insert、:2257 update、:2378 delete、:2749 transact。catalog 読みより前 :1955-1959)。schema 操作は `lock_schema` (`M`/backend_postgres.py:606-607) + 対象 entity の exclusive (`M`/cell.py:1242 create_collection、:1499 add_field、:1746 alter_field)。
- 経緯: `docs/design/MITATEDB_APPLICATION_SERIALIZATION_V0_1.md` §2.6 (同文書 K-7) :82-90 は r2db の窓を plan・確認句・`schema_objects` の 3 つに限って列挙 (:86-89)。同文書の依頼者裁定 Q-5 (:328) は「足す。r2db の §2.6 の窓は D-8 のとおり同じ変更セットで閉じる」。同文書 D-8 (:209) の方式は「lock を `_load_catalog` の前に置く」(`R`:2157 → :2163)。DML の窓は K-7 の列挙に無かったので台帳 R-102 では閉じていない。起票元: `docs/work-orders/WORK_ORDER_R102_APPLICATION_SERIALIZATION_V1.md`:611 (訂正註 3 の 3)。
- 開示: `CM`:1534 (SI-11 r2db 節の Status) "r2db's DML validation and an `alter_field` commit are not serialized ... (structural, not reproduced; ledger item R-120, still open)." 閉じるとこの行と、同節 `CM`:1518-1526 の Control / Evidence に DML 側の項と再現 test が入る (= Class D の契機)。
- 再現 test の土台: `r2db-api/tests/test_r102_schema_windows.py` の 3 本 (:206、:250、:292)。2 cell の再現は作業機 (PostgreSQL) で行う。
- 性能: 判定は `tools/PERF_BASELINE_README.md`:69-78 (K=3 の p50 が K=1 の 2 倍超)、vector は同 :138-149。`mutate` (insert 1 op、`tools/perf_baseline.py`:1651-1672) と `batch` (5 op、同 :1683-1700) が r2db の `transact` に届く (http / socket plug が PostgresCell を使う場合。in-process plug は未確認)。`query` は `with_constraints=False` の別経路 (`R`:1509) で影響しない。退行閾値は `RM` §0.1.4 の 1 (K=1 の p50 +40% 以内、p95 +50% 以内)。台帳 R-102 で MitateDB が 3b を入れた後の lock 待ちの実測は `RM` §0.1.3 の G-4 行 (K=4 で 0 / 4856 = 0.0%)。

### 4.2 放置した場合 / 利用者が気づくか

順序 (B) が当たると、catalog が enum 外 / NULL 不可と宣言する値を持つ行が残る。後の `alter_field` の走査が CONFLICT を返して初めて見える (または client が catalog を信じて値を処理したときに想定外の値に当たる)。両 peer の安全性の結果が食い違ったままなので、この性質を共通条件 (`conformance-tests/CONDITIONS.md` の C 番号) として固定できない (r2db が赤になる)。`CM`:1534 の開示は残る。運用開始後に当たれば宣言に反する行が data に残り、修復の費用が上がる (`RM` §9 の 12 の印の問い)。**気づくか: 不明** (窓が当たった時だけ。利用者は catalog の宣言と行の値の食い違いとして気づきうるが、原因は特定できない)。

### 4.3 選択肢

| 案 | 内容 | 変更クラス | 規模 | 契約版数 | 触る経路 | conformance | 欠点 |
|---|---|---|---|---|---|---|---|
| A 着手しない | `CM`:1534 の開示のまま置く | — | — | 無し | — | 共通条件は作れない (両 peer の食い違いが残る) | 宣言に反する行が残りうる。`RM` の G-2/G-3 の「両 peer で conformance に固定」から外れた性質が 1 つ残る。運用開始後に当たると修復費用が上がる |
| B 実体単位の共有 lock (推奨) | MitateDB の 3b と同型: `transact` で `_load_catalog` の前に触る entity ごとの advisory lock を共有で sorted に取り (`M`/backend_postgres.py:255-265 の `_ENTITY_LOCK_SHARED` を r2db に同型で置く)、MitateDB が実体の排他を取る schema 操作 (create_collection・add_field・alter_field。`M`/cell.py:1242・:1499・:1746) に当たる r2db の操作 (create_entity・add_field・alter_field) は schema lock (3a) の後に対象 entity を排他で取る。lock 順序を設計で確定 (schema: per-key → 3a → entity 排他 → count; DML: per-key → entity 共有 → count。`R`:1410-1412 の「輪は無い」を更新) | B (コードは r2db のみ) + D (`CM`:1518-1534 の書き換え) + C (共通条件を足すなら) | M | 無し | `R`:1637-1670 (`transact`)、`R`:2157 付近 (`apply_schema`)、`R`:1405-1415 docstring、2 cell 再現 test (土台 `r2db-api/tests/test_r102_schema_windows.py`)、`CM` SI-11 節 | 共通条件 1 件 (両 peer で「DML と、対象実体の制約を変える schema 操作 (alter_field・add_field) は重ならない」) を足せる。MitateDB は 3b により同じ性質を満たす (共通条件は未作成) | DML 経路に往復 +1 (推測。`mutate`・`batch` で計測し `RM` §0.1.4 の 1 の閾値内を確認)。lock 順序と per-key / count lock との輪の分析が要る (設計レビュー)。advisory lock の名前空間を r2db にも持つ |
| C DML 側の表 lock | `transact` で `_load_catalog` の前に触る entity の表に `LOCK TABLE ... IN ROW EXCLUSIVE MODE` を sorted に取る (schema 操作の SHARE ROW EXCLUSIVE と衝突し、LOCK の後の `_load_catalog` は READ COMMITTED で新しい registry を読む) | B + D | M | 無し | `R`:1637-1670、未存在 table の拒否経路 (NOT_FOUND は catalog で判定 `R`:1671-1673 なので LOCK を先に出すと順序が変わる)、`CM` | B と同じ | 未存在 entity の error 経路が変わる (LOCK が先に失敗)。`LOCK TABLE` を `_load_catalog` の前に出すと、catalog で照合する前の識別子で SQL を組むことになり、`CM`:217 の主張 (identifier は `_load_catalog` で live catalog に照合してから SQL を組む) に反する。runtime role の privilege (0003:236-237 で INSERT 等あり) に依存。MitateDB と同型にならず peer 間で方式が分かれる |
| D 物理制約 | registry の enum / nullable を unnamed CHECK / NOT NULL として DDL にも落とす (0003:196-204 の 2 理由を踏まえる) | B + D (+ C: error の意味が変わるなら) | L | 変わりうる (CheckViolation の error code の写像を契約で定めるなら minor) | `alter_field`・`add_field`・`create_entity` の DDL 生成、error 写像 (現状 CheckViolation は `SERVICE_UNAVAILABLE` に落ちる 0003:196-204)、migration | 共通条件は作れるが error code の整合が要る | **却下。** registry と DDL の二重真実。既存 table の migration。error code が VALIDATION でなく SERVICE_UNAVAILABLE に落ちる現状の写像を直す必要。規模 L |
| E 楽観的再確認 | `transact` で最後の write の後・commit の前に schema revision を再読し、`_load_catalog` 時点から進んでいれば rollback して CONFLICT (順序 (B) では INSERT が schema 操作の commit を待つので、再読は新 revision を見る) | B + D (+ C: CONFLICT の新しい発生条件を契約で開示するなら) | M | 変わりうる | `R`:1637-1700 (revision の読みを `transact` に足す)、`CM` | 共通条件は作れる (結果は「残らない」で同じ) が、MitateDB は待ち、r2db は失敗、と挙動が異なる | client に新しい CONFLICT が見え、再送の判断を client に負わせる (安全な再送は C-07 系で担保されるが、MitateDB では起きない失敗)。advisory lock は不要だが、読み直しが「write の後」である根拠 (順序 (A) では不要、(B) でだけ要る) を test で固定する必要 |
| F application 単位の共有 schema lock | `transact` が既存 3a の key (`R`:1405-1415) を `pg_advisory_xact_lock_shared` で取る。schema 操作は変更不要 (排他のまま) | B + D | S〜M | 無し | `R`:1637-1670 と docstring (`R`:1405-1415) | 案 B と同じ共通条件が作れる | 無関係な entity の DML も同 application の schema 操作中は待つ (application 全体で DML と schema 操作が直列)。keyed DML は count lock を保持して 3a を待ち、schema 操作は 3a を保持して count lock を待つので輪の分析が要る (`R`:1410-1412 の前提が崩れる) |

### 4.4 推奨: 着手する。閉じ方は B

理由 (決定軸順): 安全: B は窓を構造的に閉じ (DML と、対象実体の制約を変える schema 操作の重なりが無くなる)、client に新しい失敗を見せない (E との差)、registry と DDL の二重真実を作らない (D との差)。堅牢: MitateDB の 3b と同型なので両 peer の安全性の結果が揃い、共通条件として固定できる (`RM` の G-2/G-3)。MitateDB の 3b の lock 待ちは K=4 で 0 / 4856 (schema 操作の無い負荷)。往復 +1 の費用はこの値では示されず、r2db で `mutate`・`batch` を測る。F は規模が小さいが、同 application の schema 操作中は無関係な entity の DML も待たせ、count lock との輪の分析も要る。B は entity 単位なので無関係な DML を止めない。自由: 契約は変えず、client の挙動も変えない。費用は規模 M (lock 順序の設計 + 2 cell の再現 test + `CM` の書き換え)。運用開始前に閉じる方が安い (宣言に反する行が data に残ってからでは修復が要る)。

### 4.5 裁定の問い

R-120: (i) 着手し、閉じ方は MitateDB の 3b と同型の実体単位の共有 lock (案 B) で設計に進むか (別の閉じ方を望むなら「(i) + 案名」)、(ii) 着手せず `CM`:1534 の開示のまま置くか。

裁定 (逐語): 依頼者 2026-10-03 「(i) 着手、案 B 実体単位の共有 lock (推奨)」 (本資料 §0 の問いを 2026-10-03 に提示し、依頼者が選んだ選択肢の表示文。「(推奨)」は選択肢に付した印)

### 4.6 台帳行の起票文の検証

- 台帳行 `RM`:476 の起票文 (a) DML は registry から読んで Python で検証し物理制約は無い、(b) `_load_catalog` から最初の書き込みまでに `alter_field` が完了しうる、(c) 台帳 R-102 の 3a は schema 操作同士だけを直列にする、(d) MitateDB は 3b で閉じ両 peer が食い違う、はすべて今も事実。
- 起票文は `alter_field` だけを挙げるが、`add_field` (nullable: false) にも同じ窓がある (本資料で補った。§4.1)。
- 「窓は数 ms」は未計測 (構造からの見込み)。

## 5. 未確認事項

- R-118: 旧形 (alias を自前で結合する) client が実在するか (運用前なので無い見込み。未確認)。
- R-30: 現在の実配備の Application 数 (文書上は各 1)。複数 Application の serving set を組む test fixture の有無 (`SERVE_APPS` のカンマ区切りの grep では無し。他の経路は未確認)。
- R-120: 窓の再現 (cloud に PostgreSQL が無い。構造のみ)。「数 ms」は未計測。in-process plug が PostgresCell を使うか。案 B の往復 +1 の実測。

## 6. 改版履歴

| 版 | 日付 | 内容 |
|---|---|---|
| v0.1 | 2026-10-02 | 初版。R-118・R-30・R-120 の依頼者裁定資料 (裁定欄は空欄)。 |
| v0.2 | 2026-10-03 | 依頼者裁定 3 件を各行の「裁定 (逐語)」欄に記録 (R-118 (i)、R-30 (ii)、R-120 (i) 案 B)。本文は変えていない。台帳 v1.154 に逐語と本資料のパスを【追記】。 |
