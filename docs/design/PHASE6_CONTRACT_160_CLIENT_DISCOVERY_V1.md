# フェーズ6 実施設計: 契約 1.6.0 (credential の完全 bearer 化 + surface 発見 + 型付き catalog) + 衛生 2 件

- 版数: **v1.5 (2026-09-04、WP-4 記録整理)** — §10 実施記録を全 WP について確定し (WP-0 `18bd0a0` / WP-1 `bb86a37` / WP-2 `36e6d35` / WP-3 / WP-4 の集計行と受理境界、実バグ 3 件、suite 高速化の実測)、§11 の L6-1〜L6-17 に状態を付し L6-18〜L6-20 を新設した。§1〜§9 と §5 の確定英文は v1.4 から不変。旧 v1.4 (2026-09-04、作業指示書 v1.0 起草者との突合 8 件を監督裁定のうえ反映) — **§5 の引用英文は依頼者確定済みであり 1 語も変えていない。** 変更点: **(1)** §6.2 vector 3 (iv) の否定側を「7 語それぞれ」→**「`json` を除く 6 語」**へ (json = any JSON value には違反値が存在せず、書けば空振りになる)。§3 D-3 の choke point 記述にも同旨を追記。**(2)** §8 の 1 の書式例を v1.2 残骸 (`conditional on control_plane being provided`) から **`unconditional -- versioning.version_binding`** へ (G6 の分類に整合。既存同型例 `reserved_entity_names_note` に揃えた)。**(3)** Dockerfile の実体パスを **`MitateDB-api/docker/Dockerfile`** (コメント :85-125、`COPY` :111) へ訂正 (§1.4、§3 D-4(b)、§9 WP-0)。**(4)** §3 D-4(b) に「MitateDB の `pyproject.toml` には `[tool.setuptools.*]` 節が無いので **`[tool.setuptools.package-data]` 節の新設**が要る」を明記。**(5)** **§3 に D-4(c) を新設** — 同型性テストの機構を **(相対パス, シンボル名) の対応表駆動**へ一般化し、既存 11 ヘルパを初期行として維持したうえで `_optional_float` と byte 同一テスト関数を追加、ソース取得方式を両 peer `ast.get_source_segment` に統一する。これで **L5-6 は閉止**、**L5-5 は「走査範囲の拡張で部分的に閉止 — 兄弟 peer に対応物が無いヘルパは表に載せない (表が対象の全数定義)」**として §11 に記録。§9 WP-0 の成果物と §11 の実測事項の矛盾が解けた。**(6)** §9 WP-1 セルの静的固定テストを **(a) 合成不在 + (b) 分解不在**の 2 性質へ訂正 (G1 と整合)。**(7)** **§2 に制約 8 を新設** — 一回適用の migration (platform 単発と per-application upgrade script) は適用後 in-place で編集しない / provisioning script (`0003`/`0004`) は毎回実行されるテンプレートなので改訂してよい / 既存 application DB は upgrade script で同じ終状態へ揃える (テンプレート改訂と upgrade script は対で出す)。以降の制約番号を繰り下げ、参照を追随。**(8)** `contract_version` の実位置を **r2db `service.py:882` / `control_plane.py:714`、MitateDB `cell.py:1280` / `control_plane.py:1364`** へ訂正 (§1.5 の 7)。版数 flip の対象が 4 行であることを明記
- 旧 v1.3 (2026-09-04、第 2 回独立レビュー 20 件を反映) — 発行を `(credential_id, bearer)` 2 値へ、`field_domains` を registry 由来へ、値検証を cell 層 choke point へ、`upsert` 補筆を 2 義務の全文へ、registry を per-application `0006` + backfill 規則へ
- 旧 v1.2 (2026-09-04、第 1 回独立レビュー 14 件を反映) — SI-14 の帰属根拠を撤回、`json` の読み出し表現と `boolean` の wire を WP-3 射程へ、合成撤去と port 申告メソッド削除を WP-3 へ、`upsert` 句の同ラベル補筆 (D-3 (vii)) を追加
- 旧 v1.1 (2026-09-04、起草報告に対する監督裁定 10 件を反映) — `field_types` を任意とし型語彙に `json` を追加、migration 番号の裁定、新条件を C-19 へ、L6-3 を閉止
- 旧 v1.0 (2026-09-04、初版)
- 位置づけ: **監督が確定した枠 (2026-09-04 裁定) の実施設計**である。§3 の D-1〜D-5 は監督裁定を受けた確定であり、**§5 に挙げるもの (契約の英文の最終文言) のみが依頼者確定待ち**である。WP 分割は §9 に概略のみを置き、作業指示書は別途起こす。フェーズ5 設計文書 (`docs/design/PHASE5_CONTRACT_150_AND_LIMIT_RANGE_V1.md`) の構成・粒度・文体をそのまま踏襲する
- テーマ: **「共通仕様 + base URL + API key だけで、peer 非依存に利用できる」ことの完成 (クライアント発見性)**
- 出所: 外部評価 (2026-09-03、読み取り専用調査) の**指摘 2** (credential の wire 表現が peer 間で非互換) と**指摘 3** (スキーマ自己発見と control surface 発見の不足)。**指摘 4** (flush 間隔の未検証) と**指摘 5** (MitateDB の契約同梱) は**契約不変の衛生項目 (WP-0)** として同梱する。指摘 1 (conformance の資源管理) と指摘 7 (共通証拠・CI・lock) は**フェーズ7**、指摘 6 (実機適用) は引き継ぎ §4-1 のまま — いずれも本フェーズの対象外である
- 依頼者指示 (2026-09-04、逐語): 「代替案とか目先の解決ではない、より良い設計で Q1,Q2,Q3 を進めてください。後から問題が出てこればその時に対処します。まずは全体がよりベストな方向でまとまることです。」→ Q1〜Q3 は**監督裁定で確定**であり、両論を残している箇所は本設計に無い
- 契約版の前提: **契約 1.5.0 は公開済み**であり (`spec/CCR_DISPOSITION.md` 従属判断 10、両 peer とも `contract_version` 1.5.0 を宣言済み)、契約に手を入れる以上は版を上げる。本フェーズの契約版は **1.6.0** である。**クライアント通知の可否は本設計の対象外** (依頼者が 1.4.0 で「送らない」と決定済み)
- 直前の状態: フェーズ5 は閉じている (main `a211584`、root suite 単独 **1611 passed / 0 failed / 0 skipped / 0 xfailed**、うち conformance 422)。ブランチ `phase6-contract-160` を main から切ってある
- 体制: Fable 監督/設計/コミット、Opus 起草/独立レビュー/受け入れ監査、Sonnet 実装 (コミットしない)。完了条件・単一コミット規律・identity 確認は既存フェーズと同一
- 設計原則 (依頼者、2026-09-02): 先送りしない / シンプル / 制約・制限で回避しない / 誇れる成果物。既定の重み付けは「最小変更」ではなく「長期に正しい形」。利用者は AI エージェント (宣言は確実に読まれる)
- **本書の §1 の節番号について**: 枠 §1 は 1.1 (Q1) / 1.2 (Q2) / 1.3 (Q3) / 1.4 (衛生) の 4 節である。本書はその 4 節を **§1.1〜§1.4** にそのまま置き、**起草時の実測結果を §1.5** に置く (フェーズ5 設計は実測を §1 の末尾に置いており、その位置を踏襲した)

---

## 1. 問題設定

### 1.1 credential の wire 表現が peer 間で非互換である (Q1)

契約は `security.schemes.application_credential` / `control_credential` を "Opaque credential presented over TLS" と定義し、`schemas.CredentialIssued.secret` (string) を返す。**bearer token の構成法は契約のどこにも無い。**

- **r2db**: `r2db-api/src/r2db_api/auth.py:213` の `authenticate(secret)` は **secret 単独**を取る。Postgres 実装は `r2db-api/src/r2db_api/credential_store.py:139` の `_SELECT_BY_VERIFIER` (digest を索引キーにした行参照)、in-memory は全 record を `compare_digest` で走査する (`auth.py:219-226`)。control credential も同型である (`r2db-api/src/r2db_api/control_http.py:202` の `_extract_bearer` → secret 単独)。
- **MitateDB**: `MitateDB-api/src/mitatedb_api/http.py:305-330` のコメントと `:354` の `_split_bearer` のとおり、bearer は **`<credential_id>.<secret>`** である。store は `MitateDB-api/src/mitatedb_api/credential_store_postgres.py:502` の `WHERE credential_id = %s` で行参照してから digest を照合する。control も同じ (`MitateDB-api/src/mitatedb_api/control_http.py:148` の `_bearer_pair`、`control_plane.py:1204` の `_authenticate(credential_id, secret)`)。

したがって、**同じ契約を読んだクライアントが両 peer に対して同じ手順で bearer を作れない**。MitateDB の in-band 発行・rotate 応答は**生の secret** を返す (`control_plane.py:1543`、`:1600`、`:1610`) ので、その値をそのまま `Authorization: Bearer` に載せても認証は通らない。`http.py:318-325` のコメント自身が「実クライアントが usable bearer を構成できるためには in-band 発行がこの合成を `secret` として返す必要がある」と認めている。

**共通 suite はこの非互換を検出できない**。conformance adapter が実装知識で合成して回避しているためである (`MitateDB-api/conformance/conformance_adapter_mitatedb_http.py:838` / `:988` / `:945` / `:1274`、`_Session.bearer` の規約は同 `:447`)。全数は §1.5 の 5 に置く。

**監査の帰属は既に対称である (v1.2 訂正)**: v1.1 は「MitateDB は既知 id で digest 不一致の試行を credential に帰属できるが r2db はできない」と書いていたが、**これは現物と逆である**。MitateDB の `MitateDB-api/src/mitatedb_api/auth.py:383` は `authenticated = item is not None and digest_matches` であり、`:398-420` のコメントは**監督裁定 (review B-1、2026-09-03)** として逐語で「a PRE-AUTH failure (`authenticated` is `False` — unknown `credential_id`, **or a secret that did not match any stored digest**) must NEVER record the client-claimed id as `actor_id`/`target_id`」と書く (理由: 申告 id を変えるだけで coalescing を回避できる / 過長 id で応答が `AUTH_INVALID` から `SERVICE_UNAVAILABLE` へ反転する / r2db の同一の pre-auth 扱いに揃える)。分岐は `:423-434` で、`authenticated` が偽なら `actor_id=None` / `actor_type="unknown"` である。r2db 側も `service.py:1173-1190` の `_event` が canonical context (post-auth) から actor を導出する。→ **両 peer とも、credential に帰属するのは「digest 一致後に state (revoked / disabled / application 無効) で拒否された場合」だけであり、digest 不一致は `actor_id=None` で記録する。この点で両 peer は既に対称である。** したがって D-1 は帰属能力を変えない (§3 D-1、§7)。

**r2db の配備状況**: `r2db-api/deploy/DEPLOYMENT_RUNBOOK.md` §0 のとおり Stage 1 は別ポート 8443 で、**production traffic は本コードに到達しない**。既存 credential の再発行は運用上可能である。

### 1.2 control surface の所在をクライアントが発見できない (Q2)

契約 `versioning.control_discovery` は control surface の別ホスト配備を許容する ("a separately deployed control surface must not be assumed to share a host with /v1/capabilities")。しかし `schemas.CapabilityDocument` は `additionalProperties: false` の閉じた封筒であり、**control surface の所在を示すキーを持たない**。`versioning.control_base_path` は path (`/control/v1`) を定めるだけで host を定めない。

帰結として、data surface の base URL と API key を渡されたクライアントは、control surface へ辿り着く手段を契約から得られない。逆方向 (control 文書から data surface へ) も同じである。

フェーズ5 D-2 の vector は、同居の有無を **adapter の申告** `control_surface_cohosted_with_data_plane()` (port v1.9、`conformance-tests/adapter.py:1214`) で判定している。4 plug とも `False` を返す。台帳 **L5-4** が「申告を独立に検証する機構が無い」ことを開示済みである。

### 1.3 catalog が型を返さず、片 peer では catalog そのものが無い (Q3)

`spec/data-service-api.v1.json` の `definitions.EntityDescriptor.fields` は**文字列配列 (名前のみ)** である (同ファイル :307)。型の語彙は `schemas.SchemaOperationRequest.field_type` の enum `["string","integer","number","boolean","object","array"]` として**契約に既にある**。したがってクライアントは、entity の存在は発見できても、その field に何を書けるかを発見できない。

- **r2db**: `r2db-api/src/r2db_api/structured.py:1130` の `catalog()` は名前のみを返す。型は既に保持している (in-memory は `structured.py:1431` の `add_field` が `bound.field_type` を格納、Postgres は `postgres.py:249` の `_TableInfo.columns` が「宣言 field 名 → 宣言型」を保持) — **捨てているだけ**である。詳細は §1.5 の 2。
- **MitateDB**: `MitateDB-api/src/mitatedb_api/cell.py:1285` が `application_catalog: unavailable` を宣言し、`http.py:718-723` の `get_catalog` は常に `CAPABILITY_UNSUPPORTED` を返す。`docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md` :22 は「実需要が出てから別フェーズで判断」としていた (**本裁定で上書きする**)。フェーズ3 申し送り: boolean 列は両 backend とも INTEGER 表現であり、`row_addressability: unavailable` である。

### 1.4 衛生 2 件 (WP-0、契約不変)

- **flush 間隔の未検証 (外部評価 指摘 4)**: `_optional_float` は両 peer とも `float(raw)` のみで、負値・0・NaN を素通しする (`r2db-api/src/r2db_api/main.py:200-209`、`MitateDB-api/src/mitatedb_api/main.py:151-160`)。生値はそのまま flush スレッドの `threading.Event.wait` に渡る (`r2db-api/src/r2db_api/main.py:383`、`MitateDB-api/src/mitatedb_api/main.py:336`)。監督実測: `wait(0)` / `wait(-1)` / `wait(nan)` はいずれも即時 `False` を返すため、**flush スレッドがホットループになる**。MitateDB の alert 側は `max(0.0, …)` で丸めるが (`audit_dispatch.py:156`)、flush スレッドは丸めない。
- **MitateDB の契約同梱 (外部評価 指摘 5)**: `MitateDB-api/src/mitatedb_api/http.py:47` は `Path(__file__).resolve().parents[3] / "spec"` で契約を探す。`MitateDB-api/docker/Dockerfile` がこの既知の結合をコメント (:85-125) で明記し、手動 `COPY` (:111 — `COPY spec/data-service-api.v1.json /opt/venv/lib/spec/data-service-api.v1.json`) で補っている。r2db は `pyproject.toml:48` の package-data (`r2db_api/contract/*.json`) + `importlib.resources` であり、フェーズ5 WP-1 で同梱コピーの byte 同一 (`cmp` exit 0) を確認している。

### 1.5 起草時に実測した前提

本設計は下記の実測に立つ (枠 §9 が起草者に指示した 7 項目)。**すべて読み取り専用の調査であり、テストは実行していない**。実装時に食い違えば設計側を訂正する。

**1. 契約 `SchemaOperationRequest` は create_entity で field ごとの型を取れない — D-3 に additive な契約変更が要る。**
`schemas.SchemaOperationRequest.properties.fields` は `{"type":"array","minItems":1,"maxItems":16,"items":{"type":"string","pattern":"^[A-Za-z_][A-Za-z0-9_]*$"}}` であり、**名前の配列**である。`field_type` は同 schema の**リクエスト単位のスカラ 1 個**であって、field との対応を持たない。両 peer はこの事実を明示的に refuse する形で既に実装している:

| peer | 位置 | 挙動 |
|---|---|---|
| r2db | `r2db-api/src/r2db_api/structured.py:597` (`bind_schema_operation`) | `field_type is only supported by add_field.` → **`VALIDATION_FAILED`** |
| MitateDB | `MitateDB-api/src/mitatedb_api/http.py:778` (`post_schema`) | `create_entity cannot honor a request-level field_type for its fields array` → **`CAPABILITY_UNSUPPORTED`** |

MitateDB 側のコメント (`http.py:758-776`) は、silently 無視すると「`field_type: "integer"` を添えた `fields: ["rank"]` が `committed: true` を返すのに実際は `text` で作られる」という実測済みの誤りを生むため refuse していると記す。**したがって、クライアントが create_entity で型を宣言できるようにするには、契約側に per-field 型を運ぶ場所を additive に足す必要がある。** 具体形は §3 D-3 に置く。**あわせて記録**: 同じリクエストに対する拒否コードが peer 間で非対称である (`VALIDATION_FAILED` / `CAPABILITY_UNSUPPORTED`)。D-3 で両者とも受理する形になるため、この非対称は消える。

**1a. 型を宣言せずに作られた field の既定型は、両 peer で既に非対称である。**

| peer | 型無し field の実体 | 受理する値 |
|---|---|---|
| r2db | JSONB (`postgres.py:150-151` の既定) / in-memory は `None` (`structured.py:1405`) | **任意の JSON 値** — `structured.py:779-801` の `_check_type` docstring が逐語で「`field_type` of `None` means the field is untyped (JSONB-equivalent): **any JSON value is accepted**」と書く (NUL 文字のみ拒否) |
| MitateDB | `text` (`http.py:810` の `{name: "text" for name in fields_raw}`) | 文字列のみ |

**この非対称は本フェーズ以前から存在する既存の食い違いである** — 同じ `create_entity {"fields": ["note"]}` を両 peer に投げると、r2db では任意の JSON 値を書ける field が、MitateDB では文字列しか書けない field ができる。D-3 はこれを `json` の既定として揃える (§3 D-3)。

**1b. MitateDB の `json` 型は現状「任意の JSON 値」を受理しない — WP-3 の実装事項。**
MitateDB の `json` は両 backend とも**物理的に TEXT** である (`backend_sqlite.py:49-50` の `_TYPES`、`backend_postgres.py:118-119` の `_TYPES`)。値の経路は次のとおり:

- `cell.py:1128-1140` の `_normalize_value` が **dict / list を正準 JSON テキストへ直列化**し、`bool` / `str` / `int` / `float` / `None` はそのまま通す。
- Postgres backend では `field_domains` (`backend_postgres.py:355-380`) が `json` 列を **`text` ドメインとして報告**し (`:122-129` のコメントが「`text` covers both this foundation's own `text` AND `json` field types」と明記)、`_check_domain` (`:247-250`) が **`str` でない値を `VALIDATION_FAILED` で拒否**する。`None` は `:162-172` の M-5 分岐で常に許容される。
- sqlite backend は `field_domains` が全列 `None` を返す (`backend_sqlite.py:104-120`) ためドメイン検査が働かない。

→ **現状の MitateDB の `json` 列は、Postgres backend では dict / list / str / NULL は受理するが、裸の `int` / `float` / `bool` を拒否する。** sqlite backend はドメイン検査が無いので通る。**backend 間の挙動差がある。**

**さらに、読み出し側に逆直列化が存在しない (実測)**: `cell.py` / `backend_sqlite.py` / `backend_postgres.py` / `http.py` を全走査した結果、**`json.loads` の呼び出しは `http.py:48` (契約ファイルの読み込み) の 1 件のみ**である。したがって `_normalize_value` が正準 JSON テキストへ直列化した値は、**読み出し時に文字列のまま返る**。同じ `{"a": 1}` を両 peer の型無し field に書くと、r2db (JSONB) はオブジェクトを返し、**MitateDB は文字列 `'{"a":1}'` を返す**。→ **契約が `json` を「any JSON value」と定めるには、受理範囲と読み出し表現の両方を揃える必要がある** (§3 D-3、F2)。

**この帰結として、宣言型 registry は catalog / 読み出し / 受理の 3 面すべてで load-bearing である (v1.3、G2 で受理面を追加)**:

- **catalog 面**: 物理型からの逆引きが不能 (§1.5 の 2)。
- **読み出し面**: 物理 TEXT 列だけからは、`string` を宣言した field (文字列をそのまま返すべき) と `json` / `object` / `array` を宣言した field (JSON 値へ復元して返すべき) を**区別できない**。
- **受理面 (v1.3)**: `field_domains` (`backend_postgres.py:355-380`) の情報源は `information_schema.columns.data_type` **だけ**であり (`:368-371`、`:380`)、`text` と `json` は物理 TEXT で同一である — 同 `:122-129` のコメントが逐語で「nothing downstream needs to recover **which of the two** a column was originally declared as」と書く。**現行の情報源のままでは `json` を独立ドメインとして報告できない。** さらに `http.py:484-491` は `object` と `array` を**ともに** `json` へ落とすので、3 語を 1 ドメインに畳むと**宣言 `object` の field が配列も裸の値も受理する** — §5 (3) の確定文 (`a field declared object or array accepts only that shape`) が MitateDB で偽になる。

→ **MitateDB の宣言型 registry は必須であり、DDL 要否は「要する」で確定する** (§1.5 の 2a)。

**1b-3. r2db は同じ検査を既に backend 非依存に持つ (v1.3、G3 の対照)**: `r2db-api/src/r2db_api/structured.py:779-821` の `_check_type` は**共有の validation choke point** であり、`integer` は `isinstance(value, int) and not isinstance(value, bool)` (`:803`、bool を明示的に除外)、`number` も bool 除外 (`:807`)、`boolean` は `isinstance(value, bool)` (`:809`)、`string` / `object` / `array` はそれぞれ str / dict / list (`:811-815`) を要求し、不一致は `VALIDATION_FAILED` (`:818-819`) である。`ApplicationCell` と `PostgresCell` の**双方がこの同じ関数を通る**ので、backend の型強制力に依存しない。**MitateDB にはこれに相当する宣言型ベースの choke point が無い** — §3 D-3 で置く。

**1b-1. 宣言型に対する値の強制が両 backend とも不十分である (v1.3、G3。実測)**: sqlite backend の `field_domains` (`backend_sqlite.py:104-120`) は**全列 `None`** を返し (コメント逐語「every field maps to domain `None`」)、`cell.py:1074` / `:1123` はその `None` を `encode_value(..., domain=…)` に渡すので**検査が一切働かない** — in-process plug は in-memory sqlite である (`conformance_adapter_mitatedb.py:1656`)。Postgres backend も粗い: 宣言 `boolean` は物理 INTEGER → ドメイン `int32` (`backend_postgres.py:130-132`) であり、`_INT_DOMAIN_RANGES` (`:136-138`) と `_check_domain` (`:251-257`) は `-2^31 .. 2^31-1` を通すので **`7` が書ける**。→ **宣言だけあって強制の無い型を出荷しないために、値検証を backend 非依存の層へ置く** (§3 D-3)。

**1b-2. 宣言 `boolean` の wire 表現も現状は契約の嘘になる (実測)**: `backend_postgres.py:100-111` は逐語で「`boolean` maps to `INTEGER` … DELIBERATELY … both backends store and **round-trip a declared-boolean field as 0/1**」と書く (sqlite も `_TYPES` `backend_sqlite.py:49-50` で同じ)。catalog が `field_types: {"flag": "boolean"}` を返しながら query 結果の `flag` が `0` / `1` (JSON number) で返れば、**宣言と実挙動の不一致そのものが新設される** — r2db は本物の JSON boolean を返す。→ **WP-3 の射程で揃える** (§3 D-3、F3)。

**1c. 契約は `alter_field` の意味論を定義しておらず、両 peer とも実行しない。**
`alter_field` は `structured_operations.allowed_schema_operations` と `schemas.SchemaOperationRequest.properties.operation` の **2 つの enum に名前があるだけ**で、契約本文に意味論の記述が無い (全文検索で他の出現なし)。両 peer とも `unsupported` を宣言している — r2db は `service.py:896` の `"schema_operations": {..., "unsupported": ["alter_field", "jobs"]}`、MitateDB は `cell.py:1291` の `"unsupported": ["alter_field", "create_index", "drop_index", "drop_entity", "jobs"]`。→ **本フェーズは `alter_field` と catalog の関係を新たに定めない。** D-3 の原則文 (「クライアントが宣言した型が catalog に返る」) は**最後に成功した宣言**を指すので、将来 `alter_field` が型変更として定義されればその後の宣言型が返る — この一文だけを契約に置く (§5 の (3))。

**2. 宣言型の保持方法は peer で大きく違う。r2db は既に保持し捨てている、MitateDB は保持していない。**

- **r2db in-memory** (`structured.py`): `create_entity` は `:1405` で `self.schema[entity] = {name: None for name in bound.fields}`、`:1406` で `["id"] = "integer"` を置く。`add_field` は `:1431` で `bound.field_type` を格納する。`catalog()` (`:1130-1149`) は `sorted(self.schema[name].keys())` で**名前だけを取り出し、値 (型) を捨てている**。
- **r2db Postgres** (`postgres.py`): `_TableInfo.columns` は docstring (`:232-236`) 自身が「**宣言 field 名 → 宣言型**」と書く `dict[str, str | None]` (`:249`) である。`_load_catalog` は `information_schema.columns` の `data_type` と `domain_name` を読み (`:830-833`)、2 つの DOMAIN (`_r2db_json_object` / `_r2db_json_array`) を `_DOMAIN_TO_DECLARED` (`:173-176`) で `object` / `array` へ戻し、`id` は `:870` で `"integer"` に固定する。`catalog()` (`:778-800`) は `sorted(table_info.columns)` として**やはり値を捨てている**。→ **r2db の D-3 は「捨てるのをやめる」変更であり、新しい保持機構を要さない。**
- **MitateDB**: backend の型語彙は契約と別の**独自語彙** `text` / `integer` / `real` / `boolean` / `json` である (`backend_sqlite.py:49-50` の `_TYPES`、`backend_postgres.py:120` の `_TYPE_SQL`)。契約語彙からの写像は `http.py:484-491` の `_CONTRACT_FIELD_TYPE_TO_MITATEDB` であり、**単射ではない** — `object` と `array` がともに `json` へ落ち、`string` は `text` へ、そして create_entity の名前のみ field も `text` へ落ちる (`http.py:810`)。逆写像は構造的に不能である:
  - sqlite: `field_domains` (`backend_sqlite.py:104-120`) は**全 column について `None`** を返す (SQLite の型親和性が動的であるため、と同所コメント)。
  - Postgres: `field_domains` (`backend_postgres.py:355-380`) が返すのは契約型ではなく**値ドメイン分類** (`int64` / `int32` / `text`) であり、`_DOMAIN_BY_DATA_TYPE` (`:130-132`) 自身が「物理 `integer` = この基盤の `boolean`」と注記する。**フェーズ3 申し送りの boolean→INTEGER が実測で確認された。**

  → **MitateDB は宣言型を別に保持しない限り catalog で型を返せない。** 物理型からの逆引きは (i) `object`/`array` を区別できず、(ii) `boolean` と `integer` を区別できず、(iii) sqlite では何も分からない。**枠 D-3 の既定 (宣言型を peer が保持する / 物理型からの逆引きに頼らない) は現物と整合する。**

**2a. MitateDB の宣言型 registry は application データベース内に置く。migration は per-application 系列の新番号 `0006` であり、既存 DB には upgrade script で当てる (v1.3、G12 で確定形へ)。**
宣言型 registry は entity テーブルと同じ **application データベースの `public`** に要る。MitateDB の migration は **2 系統**である:

| 系統 | ファイル | 適用単位 |
|---|---|---|
| platform 単発 | `0001_bootstrap_platform.sql` / `0002_registry_and_functions.sql` / `0005_application_audit.sql` | `mitatedb_platform` に対して 1 回 |
| **application ごと** | `0003_provision_application.sql` / `0004_deprovision_application.sql` | provisioning / deprovisioning のたびに 1 application ずつ |

設計が前例に挙げる `public._mdb_schema_revision` (`0003_provision_application.sql:137-142`) は、**まさに per-application script の中**にある。したがって:

- **新規 provisioning**: `0003_provision_application.sql` の改訂で registry テーブルを作る。
- **既存 application データベース** (Mitate Phase B の検証 DB を含む): **per-application の upgrade script (新番号 `0006`)** を新設して当てる。**`0003` を改訂しても既存 DB には遡及しない** — この体系に per-application の upgrade script という種類のファイルはまだ前例が無い (`0004` は deprovision) ので、`0006` がその最初の例になる。**platform 単発の `0006` を足しても既存 application DB には何も作らない** — その形にすると、既存 DB は registry テーブルを持たないまま WP-3 の出荷を迎え、起動時ではなく**最初の catalog / 読み出しリクエストで**落ちる。
- **番号**: 現存は `0001`〜`0005` であり、**2 系統は同一の番号列を共有している**。よって次の空き番号は **`0006`** である (裁定 R3 の割当て規則。§8 の 5、§11 L6-2)。
- **sqlite backend** には provisioning という概念が無いので**遅延生成**になる。両 backend で宣言型の読み書き API を揃えることが WP-3 の要件である。

**なぜ「両 backend とも遅延生成」を採らないか (v1.1 が挙げていた第 2 の経路)**: application プロセスの developer role は `public` に request 時 DDL を実行でき (`0003_provision_application.sql:149-151` の `ALTER DEFAULT PRIVILEGES` が根拠)、遅延生成なら migration も upgrade script も要らない。**それでも採らないのは、registry が platform-managed な metadata だからである** — `_mdb_schema_revision` と同じ種類のものであり、その前例は provisioning script が作る形である。遅延生成は「最初の書き込みまでテーブルが存在しない」状態を作り、**読み出し経路 (catalog / query) が「テーブルが無い」と「行が無い」を区別できない**。ただし **Postgres 側の upgrade script が既存 DB に確実に当たることは運用手順に依存する**ので、その手順を runbook に置く (§9 の WP-3 / WP-4)。

**既存 field の backfill 規則 (v1.3、G12。cutover 規則として §8 にも置く)**: upgrade script は既存 entity の列を物理型から registry へ写す。

| 物理型 (MitateDB 内部語彙) | 登録する契約型 |
|---|---|
| `text` | **`string`** |
| `integer` | `integer` |
| `real` | `number` |
| `boolean` | `boolean` |
| `json` | `json` |

**`object` と `array` は物理的に区別できない** (どちらも `json` = TEXT) ので、**既存列は `json` として登録する**。**型無しで作られた既存 field は `text` 物理型なので `string` と報告される** — それが現物の型だからである。**`json` を既定とするのは 1.6.0 以後に型無しで作られた field だけ**である (決定 (ii))。この cutover 規則により、L6-8 が起票していた「registry に行が無い既存 field」は**構造的に生じない**。

**3. r2db の verifier 索引は UNIQUE 制約であり、D-1(c) に DDL migration は要らない。ただし migration 0008 は Q4 に先取りされている。**

- application credential: `r2db-api/migrations/0005_credential_store.sql` の `CREATE TABLE ... credentials (... verifier text NOT NULL UNIQUE ...)`。同ファイル冒頭のコメントが「`verifier ... UNIQUE`: authentication is an equality lookup on this column (`PostgresCredentialStore.authenticate`), never a full scan -- `UNIQUE` is both the index that makes that lookup fast **and a structural guarantee that two credentials can never collide on the same verifier**」と書く。
- control credential: `r2db-api/migrations/0006_control_plane_http.sql:388-390` に同型の `verifier text NOT NULL UNIQUE`。
- 参照 SQL (application): `credential_store.py:139` `_SELECT_BY_VERIFIER` と **`:140` `_SELECT_BY_ID` (credential_id での行参照は既に存在する)**。
- **参照 SQL (control) は名前付き定数を持たない (v1.3、G16)**: `ControlCredentialStore.authenticate` は `credential_store.py:638` の**インライン SQL** (`SELECT credential_id, verifier, enabled, revoked, must_rotate, role FROM {table} WHERE verifier = {ph}`) で digest を索引キーにしており、`_SELECT_BY_ID` 相当が無い。credential_id 参照は `:656` の `assert_active` にだけ存在する。さらに `control_plane.py:515-525` の `authenticate_application(secret)` も **secret 単独**を `PostgresCredentialStore.authenticate` へ渡す経路である。**D-1(c) はこの 3 箇所も対象に含める。**

  → **D-1(c) は `_SELECT_BY_VERIFIER` の使用をやめて既存の `_SELECT_BY_ID` へ寄せるだけであり、DDL 変更を要さない。** `UNIQUE` は上記コメントの後半 (衝突不能性の構造保証) として**そのまま残す**。前半 (索引としての役割) の記述は D-1 後に事実でなくなるため、記述の訂正が要る。
- **migration 番号**: 現存は 0001〜0007。**0008 は Phase 4 Q4 (案 B) に先取りされている** — `docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md:1072` と `docs/work-orders/HANDOVER_20260904_FABLE.md:120` がいずれも「r2db は migration **0008**、MitateDB は migration **0006** — いずれも新番号」と書く。D-1 が番号を要さないことは上記のとおりだが、**D-3 の MitateDB 側 (宣言型の保持) は新しい番号を要する可能性がある** (§3 D-3)。

**4. MitateDB の catalog は `mutation_class` / `address_fields` / `address_reuse` / `unique_keys` を**すべて省略する**のが契約上の正しい形である。**
契約 `structured_operations.mutation_classes.rule` は「**Where row_addressability is enabled**, every entity declares one mutation class in the catalog」と書き、`declaration_required` は「an implementation must not advertise row_addressability as enabled until every entity carries a declaration」と書く。`definitions.EntityDescriptor` の `required` は **`["entity","fields"]` のみ**であり、`address_fields` / `address_reuse` は `if mutation_class == "mutable" then` の条件下でのみ required になる。MitateDB は `row_addressability: unavailable` を宣言している (`cell.py:1296`) ので、**mutation_class を宣言しない**のが規則の素直な読みであり、宣言しないことで `if/then` も発火しない。あわせて:

- `unique_keys` は `create_index` を持たない peer では常に空である (`cell.py:1291` の `schema_operations.unsupported` に `create_index` が入る)。**省略する。**
- 仮に mutation_class を選ぼうとしても選べない: MitateDB の `atomic_mutation.operations` は `["insert","update","delete"]` (`cell.py:1283`) だが、契約 `mutation_classes.supports` で `update` を含むのは `mutable` だけであり、`mutable` は `address_fields` を要求する。**「省略する」以外の解が無い**ことの独立した裏づけである。

**4a. ただし契約 `structured_operations.upsert` の一文が、`row_addressability` による限定を持たない (v1.2、F8)。** 同節は逐語で「upsert or **update** on an entity **not declaring the mutable class**, fail with `CAPABILITY_UNSUPPORTED`」と書き、`mutation_classes.rule` が持つ「Where row_addressability is enabled」という限定が**この句には付いていない**。MitateDB は `update` を実行し (`cell.py:1283`)、`row_addressability: unavailable` (`cell.py:1296`) で mutation_class を宣言しない。**catalog が `unavailable` の間は「宣言していない entity」をクライアントが観測できなかったため矛盾は表に出なかったが、D-3 で catalog を enabled にすると顕在化する** — 契約を読んだ AI エージェントは「この entity への update は `CAPABILITY_UNSUPPORTED` のはず」と判断するのに、MitateDB は実行する。処置は §3 D-3 の決定 (vii) に置く。

**5. adapter の合成箇所は MitateDB の HTTP plug 4 箇所のみ。in-process plug には無い。**

| 位置 | 文脈 |
|---|---|
| `MitateDB-api/conformance/conformance_adapter_mitatedb_http.py:838` | 帯域外 `issue_credential` — `secret=f"{credential_id}.{secret}"` |
| 同 `:988` | `issue_credential_inband` — `secret=f"{result['credential_id']}.{result['secret']}"` |
| 同 `:943-945` | `_control_send` — `ControlCredentialHandle` のときのみ合成 (`CredentialHandle` は既に合成済みなので verbatim) |
| 同 `:1272-1274` | `audit_query_on_data_plane_host` (port v1.9) — 同じ分岐の複製 |

規約コメントは `:447` (`_Session.bearer`) と `:934-946` / `:986` にある。**`MitateDB-api/conformance/conformance_adapter_mitatedb.py` (in-process plug) には合成が 1 件も無い** — store / service を `(credential_id, secret)` の対で直接呼ぶためである。**`_Session.bearer` フィールド自体は撤去しない** (「`Bearer ` の後ろに置く文字列」という意味は D-1 後も要る) — 変えるのはその**規約コメント**と、上記 4 箇所の合成である。あわせて、共通 suite の `conformance-tests/test_c15_bootstrap_reset_lifecycle.py:347` は rotate 応答の `secret` から `ControlCredentialHandle` を組み直しており、**D-1 後はこれがそのまま「verbatim に使う」形になる**。

**6. r2db 同梱契約の byte 同一テストは `r2db-api/tests/test_http.py:286` である。** `test_packaged_contract_copy_is_byte_identical_to_spec_source_of_truth` が `resources.files("r2db_api.contract").joinpath("data-service-api.v1.json").read_bytes()` と `Path(__file__).parents[2] / "spec" / "data-service-api.v1.json"` を比較する。package-data の配線は `r2db-api/pyproject.toml:48` (`r2db_api = ["contract/*.json"]`)、loader のコメントは `r2db-api/src/r2db_api/http.py:45-46`。**MitateDB 側の双子は `MitateDB-api/tests/` に置けば `parents[2]` の深さが一致する**ので、ほぼ逐語の複製になる — 同型性テストの対象として素直である。

**7. `surfaces` の環境変数名と、capability document の構築箇所。**
既存の命名規約は `R2DB_CONTROL_PLANE_STATUS` (`r2db-api/src/r2db_api/main.py:165`、許容語彙を `:154` の集合で検査し不正値は起動時に失敗) と `MITATEDB_CONTROL_PLANE_STATUS` (`MitateDB-api/src/mitatedb_api/config.py:93-99`、同じく起動時検査) である。**D-4 の fail-fast はこの既存の形の踏襲であり、新しい規律ではない。** capability document を組む箇所は 4 つ:

| peer | surface | 位置 |
|---|---|---|
| r2db | data | `r2db-api/src/r2db_api/service.py:882` (`contract_version` 行。`capabilities.control_plane` は `:916`) |
| r2db | control | `r2db-api/src/r2db_api/control_plane.py:714` (`contract_version` 行。`capabilities.control_plane` は `:716`) |
| MitateDB | data | `MitateDB-api/src/mitatedb_api/cell.py:1280` (`contract_version` 行。`capabilities.control_plane` は `:1337`) |
| MitateDB | control | `MitateDB-api/src/mitatedb_api/control_plane.py:1364` (`contract_version` 行。`capabilities.control_plane` は `:1366`) |

**版数 flip の対象行は上表の `contract_version` 行 4 本である** — WP-2 が r2db の 2 本、WP-3 が MitateDB の 2 本を、それぞれ挙動出荷と同一コミットで動かす (§8)。

control プロセスの入口は `r2db-api/src/r2db_api/control_main.py` (既に `R2DB_CONTROL_PLANE_STATUS` / `R2DB_CONTROL_LIMIT_*` を読む) と `MitateDB-api/src/mitatedb_api/control_main.py` (`MITATEDB_CONTROL_*` を読む) である。**control プロセスが data の URL を知る経路は、data プロセスと同じ環境変数を control プロセスにも与えること以外に無い** — どちらのプロセスも相手のホストへ接続しないので、導出はできない。したがって `surfaces` は**配備者の表明**であり、両プロセスに同じ 2 変数を配る形になる (§3 D-2)。

---

## 2. 守るべき条件

1. **契約は additive のみ (1.6.0)**。1.5.0 と同じ版束縛規律を採る — 契約公開は単独コミット、各 peer の flip は挙動出荷と同一コミット、`versioning.version_binding` に 1.6.0 の義務を逐条列挙、全体 vacuity guard を `xfail(strict=True)` で先置きし最後の flip と同一コミットで撤去する。既存キーの削除・型変更・enum 縮小を行わない。
2. **契約に実装固有の構造を漏らさない**。credential は契約上「不透明」のままである。`<credential_id>.<secret>` という**内部構造を契約に書かない**。
3. **peer 間でコードを共有しない**。同名ヘルパは同型性テストで固定する (要請者決定 2026-09-03)。両 peer は同じ安全成果を**同じ形で**満たし、peer 非対称を残さない。
4. **Security Invariants は不変**である。新しい invariant を足さない。SI-06 / SI-07 / SI-10 / SI-13 / SI-14 / SI-15 との関係を §7 に書く。
5. **互換シムを作らない**。二形式受理などの目先の回避を置かない。根拠は §1.1 の配備状況 (r2db Stage 1 に production traffic が無い) である。既存 credential は**再発行**する (runbook 手順)。
6. **利用者は AI エージェント**である。宣言は読まれる前提で declare-the-hazard を採る。宣言と実挙動の一致は C-11 / C-12 系で機械検出される形にする。
7. **常設規律 7 項目** (`docs/work-orders/WORK_ORDER_PHASE5_CONTRACT_150_V1.md` §0.1) を継承する: 空振り禁止 / 変異先行で完了条件 / 主張は実測の後 / 確定文言はファイル経由 / 静的規則は逐語プロトタイプ後 / 同型性テスト / 設計外の拡張は実装前に上げる。
8. **migration の 2 種を区別する (v1.4 で明文化)**。
   - **一回適用の migration** — platform 単発 (`0001` / `0002` / `0005`) と、**per-application の upgrade script (本フェーズが新設する `0006` を含む)** — は、**適用後に in-place で編集しない**。運用者が既に適用したファイルを書き換えないという既存規律である。偽になった記述はコード側 docstring・runbook・`CONTROL_MAPPING.md`・本設計 §11 で訂正する (L6-1)。
   - **provisioning script** (`0003_provision_application.sql` / `0004_deprovision_application.sql`) は、**新規 application の provisioning のたびに毎回実行されるテンプレート**であり、**改訂してよい**。改訂は「これから作られる application DB の終状態」を変える。
   - **既存 application DB は upgrade script (`0006`) で同じ終状態へ揃える。** テンプレート改訂と upgrade script は**対で出す** — 片方だけでは新旧の application DB が別の終状態になる。
9. **公開リポジトリ規律**。実 credential・実 DSN・実ホスト名を文書にもテストにも置かない。合成 pepper と `example.invalid` 等の偽ドメインのみを使う。
10. **契約ファイルを変更するコミット (WP-1) の直前に、監督が依頼者へ再度明示する** (P4-D4 の手続き上の注意を踏襲)。

---

## 3. 決定と根拠

### D-1 (Q1) credential の wire 形式 — 契約は「secret は完全な bearer」、共通実現形は両 peer とも locator 付き token

**決定 (a) 契約 1.6.0**: `security.schemes.application_credential` / `control_credential` の description と `schemas.CredentialIssued.secret`、および rotate 応答の `secret` (application / control の両方) に、次の趣旨を明文化する — **この文字列は完全な bearer token であり、`Authorization: Bearer <secret>` にそのまま提示する。クライアントはこれを合成・分解・派生してはならない。内部構造は不透明である。** `versioning.version_binding` の 1.6.0 義務として、**条件付き**で置く: **control plane を `unavailable` 以外で宣言する 1.6.0 実装は、自らの in-band issue / rotate が返した `secret` を、そのまま bearer として受理しなければならない。**

**契約英文の骨子** (最終文言は依頼者確定待ち、§5):

> `CredentialIssued.secret` — and the `secret` returned by a rotate response, on the application and control surfaces alike — **is the complete bearer token**: a client presents that exact string, verbatim, as `Authorization: Bearer <secret>`. A client MUST NOT compose it from, split it into, or derive it from any other field of the response. Its internal structure is opaque and an implementation may change that structure without a contract change; no client may depend on it.

**決定 (b) 共通実現形 (契約外、リポジトリ設計として両 peer 共通)**: application credential も control / audit credential も、**`<credential_id>.<secret_part>` を 1 つの不透明文字列として発行し、受理側は locator (credential_id) で行参照してから digest を照合する**。

根拠は 3 点である。

1. **credential_id で O(1) の行参照ができ、digest を索引キーにしなくて済む。** 現行の r2db は digest そのものを索引キーにしている (`_SELECT_BY_VERIFIER`)。
2. **rotate 後も token の locator が安定する。** secret 部分が変わっても credential_id は変わらない。
3. **広く使われている形である** (`id.secret`)。AI エージェント統合者にとって既知の形である。

**v1.1 が挙げていた 4 つ目の根拠 (「失敗認証を credential に帰属できるようになる」) は削除した (v1.2)** — §1.1 のとおり現物と逆であり、両 peer は既に対称である。**決定 (locator 形) 自体は上の 3 点で支えられており変わらない。**

**credential_id を token に含めても SI-07 を弱めない**: credential_id は非秘密である — `list_credentials` の応答に現れる (contract `control_endpoints`)。秘密は secret 部分だけであり、その扱い (digest のみ保管、一度だけ返す) は変わらない。

**決定 (c) r2db の変更**:

- issue / rotate 応答の `secret` を合成形にする (application credential = `ops.py` / control 面の in-band 発行、control credential = bootstrap / reset / rotate)。
- `authenticate` を locator 分割 → credential_id で行参照 → `compare_digest` の順に改める (`auth.py:213`、`credential_store.py`、control 側の対応箇所)。
- `_SELECT_BY_VERIFIER` (`credential_store.py:139`) の**使用をやめる** — 定数自体を削るか残すかは実装判断だが、**認証経路から digest 索引を消す**ことが決定である。既存の `_SELECT_BY_ID` (`:140`) がそのまま使える (§1.5 の 3)。
- **control 側にも `_SELECT_BY_ID` 相当を新設する (v1.3、G16)**: `ControlCredentialStore.authenticate` の**インライン** `WHERE verifier = {ph}` (`credential_store.py:638`) を、credential_id 参照の名前付き定数へ置き換える (`:656` の `assert_active` が既に credential_id 参照なので、そこと同じ形に揃える)。
- **`control_plane.py:515-525` の `authenticate_application(secret)`** も locator 経路へ改める — この関数は control プロセスが application credential を検証する唯一の経路であり、secret 単独のまま残すと D-1 が片肺になる。
- **DDL migration は不要**である (§1.5 の 3)。`verifier` 列は digest 保管として残し、`UNIQUE` 制約も**衝突不能性の構造保証として残す**。`0005_credential_store.sql` / `0006_control_plane_http.sql` のコメントのうち「UNIQUE は索引としてこの参照を速くする」と述べる部分は D-1 後に事実でなくなるため、**訂正が要る** (扱いは §11 の申し送りに置く)。
- in-memory store (`auth.py` の `CredentialStore`) と control credential store も同型にする — **全 record 走査を locator 参照へ**改める。
- **互換シムを置かない**。旧形式 (secret 単独) の受理は残さない。既存 credential の再発行手順を `r2db-api/deploy/DEPLOYMENT_RUNBOOK.md` と `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` に置く。

**決定 (d) MitateDB の変更 (v1.2、F4 で帯域外経路まで拡張)**: **issue / rotate の「あらゆる発行点」が合成形を返す。** v1.1 は in-band の 3 行だけを挙げていたが、それでは adapter の合成を撤去できない (帯域外経路が raw の対を返し続けるため)。D-1(c) が r2db について bootstrap / reset まで列挙しているのと**同じ粒度に揃える**。

| 経路 | 位置 | 変更 |
|---|---|---|
| in-band issue / rotate (application) | `MitateDB-api/src/mitatedb_api/control_plane.py:1543` / `:1600` / `:1610` | 応答の `secret` を合成形に |
| 帯域外 store API | `credential_store_postgres` / `auth.CredentialStore` の `issue`、および `ControlCredentialStore` の対応メソッド | **`(credential_id, bearer)` の 2 値を返す** — `bearer` は合成済みで `Authorization` にそのまま載る値、`credential_id` は**別フィールド**である。現在は `(credential_id, secret)` の対を返し `conformance_adapter_mitatedb_http.py:838` が合成しているので、**合成の場所が呼び出し側から store 側へ移る**だけで、返る値の個数は変わらない |
| ops CLI | `MitateDB-api/src/mitatedb_api/ops.py:266-275` の `_print_secret_once` | **`credential_id:` 行は残し、`secret:` 行を合成済み bearer の 1 行に置き換える** (2 行のまま)。adapter の `bootstrap()` (`conformance_adapter_mitatedb_http.py:1097`) / `reset()` (`:1104`) の `_parse_issued_stdout` は、**割るのをやめて 2 行をそれぞれ読む**形になる |

**`credential_id` を消してはならない (v1.3、G1)**: `conformance-tests/adapter.py:64-68` の `CredentialHandle.credential_ref` は必須フィールドであり、`revoke_credential` (`conformance_adapter_mitatedb_http.py:841-842`) と **rotate URL の組み立て** (`:1166` の `/control/v1/credentials/{credential_id}/rotate`) が使う。発行結果を「合成済み bearer 1 個」にすると、**adapter は id を bearer から split して取り出すしかなくなり**、§5 (1) の確定文 (`MUST NOT compose it from, split it into, or derive it from`) と port v1.10 の規約に正面から反する。**契約側は既に `CredentialIssued` / `CredentialRotated` の双方が `credential_id` と `secret` を required で持つ** ので、帯域外も CLI も**その in-band と同じ「id は別フィールド」形に揃える**のが自然である。adapter は `credential_ref` に `credential_id` を、bearer に `secret` を**そのまま**持ち、**合成も分解もしない。**

`_split_bearer` (`http.py:354`) と store 側の行参照は**現状維持**である — MitateDB は既に (b) の受理側を満たしている。

**混在期間を作らない (F4)**: `_repair_control_actor` (`conformance_adapter_mitatedb_http.py:1155-1171`) は bootstrap 由来の **bare** secret と rotate 由来の **合成** secret を同じ `ControlCredentialHandle` に混ぜており、`_control_send` (`:943-945`) が rotate 由来の値に二重前置して `id.id.secret` を作る。**bootstrap / reset / issue / rotate のすべてを同一コミット (WP-3) で合成形にし、bare と合成が同じ handle 型に混在する期間を作らない。**

**決定 (e) conformance**: 新 vector を置く — 「**issue / rotate が返した `secret` を、実装知識なしにそのまま `Authorization: Bearer` に載せて認証できる**」(4 plug 全数)。**application credential は data surface で、control credential は control surface で**それぞれ verbatim に通ること — 両者を「双方の surface で」と束ねない (v1.2、F7: 契約 `security.schemes.control_credential` は「application credentials are not accepted」と書く。交差は既存の C-13 / C-14 が拒否側で固定済みである)。

**adapter の合成コードの撤去は WP-3 と同一コミットである (v1.2、F4)** — §1.5 の 5 の 4 箇所のうち `issue_credential` / `bootstrap` は**既存の全 vector が使う土台**であり、MitateDB がまだ 1.5.0 (raw 返却) の WP-1 時点で撤去すると HTTP plug の既存テストがその場で全滅する。**WP-1 では「adapter に合成が存在しないこと」の静的固定テストを `xfail(strict=True)` で先置きし、WP-3 で撤去する** (全体 vacuity guard と同じ運用)。port v1.10 の規約 (返却値を verbatim に使う) は WP-1 で置く。規則は逐語プロトタイプの後に確定する (常設規律 5)。詳細は §6。

**決定 (f)**: `spec/CCR_DISPOSITION.md` に **従属判断 11** として記録する (§8)。

**実装拘束 (D-1(c)(d) 共通、B-1 裁定の維持。v1.2 で追加)**: locator 化は**監査の帰属規律を一切変えてはならない**。具体的に 3 点である。

1. **locator で行を参照した後も `compare_digest` を先に評価する。** `revoked` / `enabled` / application 無効の検査は **digest 一致後にのみ**行う。現行 r2db in-memory (`auth.py:219-232`) は digest 一致 → revoked → enabled の順であり、**この順序を locator 化で崩さない**。
2. **応答は `AUTH_INVALID` 一様である。** 未知 locator / 既知 locator で digest 不一致 / 不正形 locator のいずれも `AUTH_INVALID` であり、locator が既知か否かを応答で漏らさない (SI-10)。
3. **クライアントが申告した locator を `actor_id` / `target_id` に記録しない。** digest 不一致は `actor_id=None` (MitateDB `auth.py:398-420` の B-1 裁定、r2db `service.py:1173-1190` の canonical context 由来の actor 導出) のままである。**locator が token に入ることで「申告 id が監査に載る」形にしてはならない** — B-1 が閉じた 2 つの穴 (申告 id を変えるだけの coalescing 回避 / 過長 id による応答コード反転) を開けることになる。

**エラー応答の一様性 (SI-10)**: 上記 2 のとおりである。**D-1 は監査の帰属能力を変えない** — 変わるのは行参照の方法だけである。

**不正形 locator の fail-closed (SI-15)**: `.` を含まない、locator 部が空、secret 部が空、のいずれも**認証を実行せず `AUTH_INVALID`** で閉じる。MitateDB は既にこの形である (`http.py:337-341` の `_CredentialMalformed` と `:354-360` の `_split_bearer` → `AUTH_INVALID`)。r2db も同型にする。

### D-2 (Q2) surface の発見 — `CapabilityDocument.surfaces`

**決定**: `schemas.CapabilityDocument` に**任意キー `surfaces`** を追加する。

```
"surfaces": {
  "data":    {"base_url": "<絶対 URL。versioning.base_path (/v1) を含む>"},
  "control": {"base_url": "<絶対 URL。versioning.control_base_path (/control/v1) を含む>"}
}
```

- **data plane の capability document と control plane の capability document の両方が、同じ `surfaces` を返す** (双方向 — どちらから入っても両方へ辿れる)。
- **1.6.0 の義務 (v1.3、G6 で分類語を 1.4.0 の taxonomy へ揃えた)**: 1.6.0 を宣言する実装は `surfaces.data` を返す。control surface が提供されている限り (`control_plane` other than `unavailable`) `surfaces.control` も返す。**どちらも「無条件義務」と呼ぶ** — 契約既存の 1.4.0 段落が、同じ `control_plane` 前提を持つ義務 (b) を「Three of those obligations are **unconditional** … where a control surface is provided at all」と分類する前例に揃える。**conditional と呼ぶのは capability の status に依存する義務** (`application_catalog` / `schema_operations`) だけである。`control_plane: unavailable` の配備は `control` を**省略する**。
- `base_url` は**配備者の表明**である (環境変数、§1.5 の 7)。導出はできない。
- **declare-and-echo**: `surfaces.<x>.base_url + "/capabilities"` は同じ `contract_version` と同じ `surfaces` を返す (自己整合)。adapter は両ホストへ到達できるので、conformance で突合できる。
- **同居判定**: `surfaces.data.base_url` と `surfaces.control.base_url` の **origin 一致** (origin = **scheme + host + port**、path を含まない) で機械的に判定できる。**`surfaces.control` が存在しない配備 (`control_plane: unavailable`) の同居判定は `False` とする** (v1.2、F5) — 同居しうる相手が存在しないためであり、現行の 4 plug の申告値 (`False`) とも一致する。**port v1.9 の申告メソッド `control_surface_cohosted_with_data_plane()` は宣言由来の判定へ置換するが、その削除は最後の flip (WP-3) と同一コミットで行う** (v1.2、F5 — 理由は §6.1 の 2)。台帳 **L5-4** は WP-3 で閉じる。
- **2 プロセス間のドリフト (v1.2、F9)**: §1.5 の 7 のとおり data / control は別プロセスであり、どちらも相手のホストへ接続しない。したがって「両文書が同じ `surfaces` を返す」という 1.6.0 義務は、**どちらのプロセスも単独では守れているか確認できない**。設計上の切り分けは 3 段である。
  - **(a) 実装が起動時に検査できるのは、自プロセスに与えられた変数の形だけ**である — 絶対 URL であること、`data` は `/v1` で終わること、`control` は `/control/v1` で終わること、**末尾スラッシュを含まないこと** (F12 (ii): `base_url + "/capabilities"` を組む以上、`/v1/` を許すと `/v1//capabilities` が生じる)。不正なら fail-fast する。
  - **(b) 両文書の一致は配備者の責任**である。**両プロセスは同じ 2 変数から `surfaces` を構成する**。食い違う配備は非適合であり、クライアントはどちらかを正とみなしてよい保証を持たない。検出は**配備後チェック** (両 peer の DEPLOY / runbook 文書に手順を置く) と、**HTTP plug の declare-and-echo vector** (§6.2 の 2) による。
  - **(c) 構造的な手当ては Q4 と同族である** — 「宣言は control プロセス、実効値は data-plane プロセト」という形は `visibility_lag_ms` / `coalescing_window_ms` の 2 プロセス整合 (`PHASE4_DURABLE_AUDIT_SINK_V1.md` §11.2 Q4) と同型である。**Q4 案 B (DB 側を単一の真実にする) が成立する際に、`surfaces` も同じ機構へ載せる**。§11 に起票する。
- **`surfaces` は `data` / `control` の 2 つのみ**である。audit は control surface の endpoint であって別 surface ではない。data ホスト上の `audit_query` alias は 1.4.0 の deprecation 経路のままであり、`surfaces` には現れない。

**契約英文の骨子** (最終文言は依頼者確定待ち、§5):

> `surfaces` names the absolute base URLs at which this deployment's own surfaces are reached, **as declared by the deployer** — it is not derived, and a client must not infer it from the URL it happened to use. `surfaces.data.base_url` ends at this contract's `versioning.base_path`; `surfaces.control.base_url` ends at `versioning.control_base_path`. **The data surface's capability document and the control surface's own capability document return the same `surfaces` object**, so a client holding either base URL can reach the other surface. A deployment declaring `control_plane` as `unavailable` omits `surfaces.control`. Whether the two surfaces share a host is read from the origins of these two URLs (`versioning.control_discovery`'s co-hosting convenience), never assumed.

**両 peer の変更の具体形**: §1.5 の 7 の 4 箇所に `surfaces` を組み込む — `r2db-api/src/r2db_api/service.py:916` / `r2db-api/src/r2db_api/control_plane.py:716` / `MitateDB-api/src/mitatedb_api/cell.py:1279-1345` / `MitateDB-api/src/mitatedb_api/control_plane.py:1366`。環境変数は既存の `*_CONTROL_PLANE_STATUS` の命名に揃え、**`R2DB_DATA_BASE_URL` / `R2DB_CONTROL_BASE_URL`**、**`MITATEDB_DATA_BASE_URL` / `MITATEDB_CONTROL_BASE_URL`** とする。**両プロセス (data / control) に同じ 2 変数を配る** (§1.5 の 7)。`R2DB_CONTROL_PLANE_STATUS` / `MITATEDB_CONTROL_PLANE_STATUS` と同じく**起動時に形を検査して不正なら失敗する** (絶対 URL であること、`data` は `/v1` で終わること、`control` は `/control/v1` で終わること、**末尾スラッシュを含まないこと**)。`control_plane: unavailable` の配備では control 側変数を要求しない。**検査できるのは形だけであり、両文書の一致は配備者の責任である** (上記 (b))。

**conformance vector**: (i) `surfaces.data` が data 文書と control 文書の双方に現れ、値が一致すること; (ii) `control_plane` が `unavailable` 以外なら `surfaces.control` も同様であること; (iii) declare-and-echo — 各 `base_url` の `/capabilities` が同じ `contract_version` と同じ `surfaces` を返すこと; (iv) 同居判定が origin 比較で得られること (**申告メソッドの消滅の確認は WP-3 まで課さない** — §6.1 の 2)。

### D-3 (Q3) 型付き catalog + MitateDB の `application_catalog` 有効化

**決定 (i) 型語彙に 7 語目 `json` を足す**: `SchemaOperationRequest.field_type` の enum を `["string","integer","number","boolean","object","array"]` から **`["string","integer","number","boolean","object","array","json"]`** へ拡げる。`json` の意味は **any JSON value** である。新設する `field_types` (下記 (ii)(iii)) も catalog も、**この同じ 7 語 enum を使う** — 3 箇所とも同一の語彙である。

**なぜ `json` か**: r2db の型無し列は既に **JSONB = any JSON value** であり (`structured.py:779-801` が逐語でそう書く、§1.5 の 1a)、`json` はその実在の既定を**正直に名付けたもの**である。`unknown` を足す案 (§4 Q3 (D)) と決定的に違うのは、**`json` は型である** — クライアントはそこに何を書けるか (任意の JSON 値) を知り、判断できる。declare-the-hazard は「未知を宣言する」ことではなく「実際の性質を宣言する」ことであり、`json` はそれを満たす。

**決定 (ii) 型を宣言せずに作られた field の型は `json` である**: 契約がこの既定を定める。**「すべての field に型がある」は、型無し field を作れなくすることではなく、型を宣言しなかった field の型を契約が定めることで満たす。**

**MitateDB の挙動変更 (明記する)**: §1.5 の 1a のとおり、型無し field の既定は**既に peer 非対称**である — r2db は任意の JSON 値を受理し、MitateDB は文字列しか受理しない (`http.py:810` の `{name: "text" for name in fields_raw}`)。**MitateDB の既定を `json` へ改める。** これは MitateDB の**実挙動の変更**である (それまで文字列しか書けなかった field に任意の JSON 値が書けるようになる — 受理域の**拡大**であり、既存の書き込みを壊さない)。あわせて §1.5 の 1b のとおり、**MitateDB の `json` 列は現状 Postgres backend で裸の `int` / `float` / `bool` を拒否する**ので、契約の "any JSON value" を満たすよう受理範囲を広げるのが WP-3 の実装事項である。**Mitate Phase B の実 DB への影響 (既存の `text` として作られた列を持つ entity がどう報告されるか) は WP-3 の実測事項**とする (§9)。

**決定 (iii) `EntityDescriptor.field_types`**: `definitions.EntityDescriptor` に **`field_types`** を追加する — object であり、key は field 名、value は (i) の 7 語 enum である。既存の `fields` 配列は**残す** (additive)。1.6.0 の**条件付き義務**: **`application_catalog` を `unavailable` 以外で宣言する 1.6.0 実装は、`fields` の全要素について `field_types` を返す。** 型を宣言せずに作られた field は (ii) により `json` として返る。

**決定 (iv) `SchemaOperationRequest.field_types` — 任意キーであり、要求しない**: §1.5 の 1 のとおり現行契約は create_entity で per-field 型を運べないので、**任意キー `field_types`** を `SchemaOperationRequest` に足す。`EntityDescriptor.field_types` と**同じ綴り・同じ shape** (field 名 → 7 語 enum) である。

- `create_entity` は `fields` (名前の配列) と、任意で `field_types` (名前 → 型) を受ける。`field_types` を与えるなら、そのキー集合は `fields` の要素の**部分集合**である。`field_types` に現れない名前の型は (ii) により `json` である。
- **不正ケースは `VALIDATION_FAILED` である (v1.3、G10)**: (a) `field_types` が **`fields` に無い名前**を持つ要求、(b) `field_types` の値が**7 語の語彙に無い**要求、(c) **`fields` を伴わずに `field_types` だけ**を送る要求 — いずれも `VALIDATION_FAILED` で拒否する。**黙って無視してはならない** — 無視は「宣言したのに `json` で作られた」を生み、それは `MitateDB-api/src/mitatedb_api/http.py:758-776` が実測して refuse した誤りそのものである (§1.5 の 1)。規則を契約に書かないと、一方の peer が無視し他方が拒否する**新しい非対称**が立つ。
- **`field_types` を要求してはならない。** `fields` だけを伴う `create_entity` (1.5.0 で有効なリクエスト) は 1.6.0 実装でも**そのまま有効**であり、その field は `json` 型で作られる。要求する形は 1.5.0 で有効なリクエストを拒否する**意味変更**であり、`versioning.compatibility` (「removal or semantic change requires a new major version」) に反する。
- `add_field` の `field_type` (スカラ) は**変えない** — 両 peer とも現状必須であり、その形を維持する。
- **既存の `fields` の型 (string 配列) は変えない。**

**同じ綴りを 2 箇所で使うことについて**: フェーズ5 の `operations` (台帳 L5-3) と違い、ここでは**両者の意味が同一**である (「field 名 → その field の宣言型」)。曖昧解消文は要らないが、契約文に「リクエスト側の `field_types` で宣言した内容が、catalog の `field_types` として返る」という**対応関係の 1 文**を置く。

**決定 (v) 宣言する事実の範囲**: **null 可否・既定値・必須性は宣言しない** — 契約の schema operations がそれらを定義できない以上、catalog がそれを宣言すると嘘になる。契約文に原則を置く: **「catalog は schema operations で定義できる事実のみを返す」**。将来 schema operations が nullability を得たら、catalog も同じ版で得る。**`alter_field` については新たに何も定めない** — §1.5 の 1c のとおり契約に意味論が無く両 peer とも実行しないので、原則文の「宣言した型が返る」が**最後に成功した宣言**を指すことだけを 1 文で言う。

**決定 (vi) 「未知」を型語彙に足さない**: `unknown` は型ではない。(i) の `json` が、`unknown` が埋めようとしていた場所を**実在の型として**埋める。

**決定 (vii) `structured_operations.upsert` の一文に `row_addressability` の限定を補筆する (v1.2、F8。監督裁定: 案 (i) = additive な限定)**: §1.5 の 4a の衝突を、**1.6.0 での同ラベル補筆**として閉じる — フェーズ5 D-2 (1.4.0 無条件義務 (b) の適用範囲の同ラベル改訂) と**同じ許容形**である。

- **対象は 1 文であり 2 義務を運ぶ**: 前半 (「upsert on an entity **without a declared uniqueness key**」) は逐語で残し、**後半 (mutable class 不宣言時の upsert / update 拒否) にだけ限定を足す** (v1.3、G4)。限定句は契約既存の語法に揃えて **`row_addressability` provided (other than `unavailable`)** とする (v1.3、G8 — `enabled` だけにすると `partial` を落とす)。
- **狭化ではない**: `row_addressability` を提供する実装に対しては**現状と完全に同義**であり、義務は 1 つも減らない。`row_addressability: unavailable` の実装に対して、**mutation_class を宣言していないことを理由に update を禁じる読み**を閉じるだけである。**`mutation_classes.declaration_required` を根拠として引かない** (v1.3、G9 — 同条は「enabled を名乗るなら全 entity が宣言を持て」であって「unavailable なら宣言してはならない」ではない)。
- これは**契約内の 2 つの記述 (`mutation_classes.rule` と `upsert`) を同じ前提の下に揃える**訂正であって、新しい能力を認めるものではない。MitateDB の `update` は 1.3.0 以来出荷済みであり、この補筆は**その適合性を遡って変えない** (フェーズ5 D-2 の additive 根拠と同型)。
- 契約英文の骨子は §5 の (5) に置く。`spec/CCR_DISPOSITION.md` 従属判断 11 の**項目 4** として記録する (§8)。

**契約英文の骨子** (最終文言は依頼者確定待ち、§5):

> The field-type vocabulary gains a seventh member, `json`, meaning **any JSON value**; a field created without a declared type has type `json`. `EntityDescriptor.field_types` maps every name in `fields` to that field's type, drawn from that same vocabulary. What a client declared — through `SchemaOperationRequest.field_types` on `create_entity`, or `field_type` on `add_field` — is what the catalog reports back; a field for which no type was declared reports `json`. **The catalog reports only facts this contract's own schema operations can establish**: it does not declare nullability, default values, or whether a field is required, because no schema operation defined here establishes any of them. There is no "unknown" member of the type vocabulary: every field an implementation lists in `fields` carries a real type.

**両 peer の変更の具体形**:

- **r2db** (捨てるのをやめる — §1.5 の 2):
  - in-memory `structured.py:1130` の `catalog()` に `field_types` を足す。値は `self.schema[name]` そのものである。`id` (server-assigned address) は `"integer"` (`:1406` が既にそう置いている)。
  - `structured.py:1405` の `{name: None for name in bound.fields}` は、**リクエストの `field_types` に名前があればその型を、無ければ内部表現の `None` を置く**形にする。`bind_schema_operation` (`structured.py:569` 以降) の `field_type is only supported by add_field.` (`:597`) を、**任意キー `field_types` を create_entity で受ける形**へ改める (`field_type` スカラの create_entity での拒否はそのまま残す — スカラは per-field 対応を持たないため)。
  - Postgres `postgres.py:778` の `catalog()` に `field_types` を足す。値は `table_info.columns` (既に「宣言 field 名 → 宣言型」) である。`create_entity` の DDL は、`field_types` に名前がある field には `_FIELD_TYPE_SQL` (`:159-166`) を per-field に適用し、無い field は**現行どおり JSONB** のままとする。
  - **明示宣言された `json` は内部表現 `None` と同一に扱う (v1.3、G11)**: `bind_schema_operation` で `json` を受けたら**内部表現 `None` (untyped = JSONB-equivalent) へ写す**。写さずに文字列 `"json"` を格納すると、`_check_type` (`structured.py:779-821`) の分岐は `:816-817` の `else: ok = True` (無検査) へ落ち、**`:820` の NUL 検査が `("string","object","array")` に限定されているため、型無し field なら拒否している NUL 文字が「宣言した `json`」では通る** — 宣言した方が緩くなる逆転が起きる。あわせて **`postgres.py:159-166` の `_FIELD_TYPE_SQL` に `json` の経路 (`_JSONB_SQL`、`:168`) を置く** — 無いと per-field DDL 適用時に `KeyError` になる。
  - **内部表現の `None` は `json` として返す**: r2db の `None` は「型無し = JSONB = any JSON value」を意味しており (`structured.py:779-801`)、決定 (i)(ii) の `json` は**まさにその型の名前**である。したがって catalog の `field_types` は `None` を `"json"` へ写して返すだけでよい — **fail-closed も移行も要らず、既存配備の型無し列もそのまま正しく報告される** (v1.0 が置いていた「残存 `None` は fail-closed」という扱いは裁定 R1 により不要になった。§11 L6-3)。
- **MitateDB** (`application_catalog` を `unavailable` → `enabled` へ flip し `GET /v1/catalog` を実装する):
  - **宣言型 registry を新設する (確定)。** §1.5 の 2 のとおり物理型からの逆引きは不能であり (`object`/`array` の合流、`boolean`→INTEGER、sqlite の型情報欠如)、さらに §1.5 の 1b のとおり**読み出し表現を決めるためにも宣言型が要る**。両 backend に**宣言型の保管**を置き、`create_entity` / `add_field` が契約語彙の値 (7 語) をそのまま書き込む。型を宣言せずに作られた field には **`json` を書き込む** (決定 (ii))。**Postgres 側は per-application 系列の migration `0006`** — 新規 provisioning は `0003` の改訂、**既存 application データベース (Phase B の検証 DB を含む) は per-application の upgrade script `0006`** で当てる。既存列は物理型からの backfill 規則 (§1.5 の 2a) で登録し、**型無しで作られた既存列は `string` として登録する** (`json` 既定は 1.6.0 以後に作られた field にのみ適用する)。**sqlite 側は遅延生成**であり、両 backend で読み書き API を揃える (§1.5 の 2a、§8 の 5)。
  - `cell.py:1285` の `"application_catalog": {"status": "unavailable"}` を `"enabled"` へ flip し、`http.py:718-723` の `get_catalog` を実装する。**宣言と実挙動は同一コミット**である (`cell.py` の既存注記が確立した規律)。
  - **返す EntityDescriptor は `entity` / `fields` / `field_types` の 3 キーのみ**であり、`mutation_class` / `address_fields` / `address_reuse` / `unique_keys` は**省略する** — §1.5 の 4 に根拠 (契約 `mutation_classes.rule` が mutation_class の宣言を `row_addressability` が enabled のときに限っており、MitateDB は `unavailable` である)。
  - `http.py:778` の `create_entity cannot honor a request-level field_type` の refuse を、**任意キー `field_types` を受ける形**へ改める (`field_type` スカラの refuse 自体は残す — r2db と同じ理由)。`http.py:810` の `{name: "text" for name in fields_raw}` を、**`field_types` に名前があればその型を、無ければ `json` を**置く形に改める — **これが決定 (ii) が求める MitateDB の挙動変更である** (既定 `text` → `json`、受理域の拡大)。
  - **`json` は受理範囲と読み出し表現の両方を「any JSON value」に揃える (v1.2、F2)。** 「書けること」だけでは足りない — **書いた JSON 値と読み戻した JSON 値が等しいこと (round-trip)** が要件である。
    - **受理側 (v1.3、G2 で情報源を確定)**: **`field_domains` の情報源を宣言型 registry に切り替える** — `information_schema` からの逆引き (`backend_postgres.py:355-380` の `:368-371` / `:380`) は**廃止**する。registry は `string` / `json` / `object` / `array` を**別々のドメイン**として返し、`_check_domain` (`:247-250`) は **`object` → dict のみ / `array` → list のみ / `json` → 任意 JSON 値 / `string` → str のみ**で分岐する。3 語を 1 ドメインに畳んではならない — 畳むと §5 (3) の確定文「a field declared `object` or `array` accepts only that shape」が偽になる。逆引きを前提にした `backend_postgres.py:122-129` のコメントは同一コミットで訂正する (§11 L6-1 の (v))。
    - **読み出し側**: §1.5 の 1b のとおり**逆直列化が存在しない** (`json.loads` は `http.py:48` の 1 件のみ)。`json` / `object` / `array` を宣言した field の読み出しで、**正準 JSON テキストを JSON 値へ復元して返す**。`string` を宣言した field は文字列のまま返す — **この区別は物理 TEXT 列からはできず、宣言型 registry を引いて初めてできる** (上記)。
  - **宣言 `boolean` の wire 表現を JSON boolean に揃える (v1.2、F3)。** §1.5 の 1b-2 のとおり、両 backend は宣言 boolean を **0/1 で round-trip する** (`backend_postgres.py:100-111` が逐語でそう書く)。catalog が `boolean` を宣言しながら `0`/`1` を返せば、**型付き catalog が最初から嘘を宣言する**ことになる。**registry の宣言型を引いて、書き込みで受理するのは JSON boolean のみ (`0` / `1` / `7` などの int は `VALIDATION_FAILED` で拒否する)、読み出しは `true` / `false` を返す。両 backend で揃える。** 拒否を明記するのは、§1.5 の 1b-1 のとおり現状の Postgres ドメインが `int32` として `7` を通し、それを読み出し時に bool へ写すと**値 round-trip が沈黙のうちに壊れる**ためである。これは MitateDB の**挙動変更**であり (§8)、WP-3 の射程内である。
  - **宣言型に対する値検証を `cell` 層の choke point に置く (v1.3、G3。WP-3 の射程内)。** §1.5 の 1b-1 のとおり **sqlite backend は宣言型を一切強制せず** (`field_domains` が全列 `None`)、Postgres backend も `boolean` を `int32` として通す。**backend のドメイン機構に依存する限り、宣言だけあって強制の無い型が出荷される** — 契約が「every field carries a real type」と宣言し AI エージェントがそれに従って読む以上、これは許されない。**`_prepare_values` 系の既存 choke point (`cell.py:1074` / `:1120-1123` が `encode_value` を呼ぶ地点) で、registry の宣言型に対する値検証を backend 非依存に行う**: `boolean` は JSON boolean のみ / `integer` は整数のみ (bool を除く) / `number` は数値 / `string` は文字列 / `object` は dict / `array` は list / `json` は任意 JSON 値。不一致は **`VALIDATION_FAILED`** である。**`json` だけは拒否する値を持たない** (any JSON value であるため) — 検証は残り 6 語に対して働く。**これは r2db が `structured.py:779-821` の `_check_type` で既に持っている形と同型**であり (§1.5 の 1b-3)、peer 間で同じ安全成果を同じ形で満たす (制約 3)。backend のドメイン検査は**その下の defence-in-depth として残す**。
  - **Mitate Phase B の実 DB への影響を WP-3 で実測する**: 変更前に作られた field (宣言型 registry に行が無い) が実 DB に存在するか、存在する場合それを catalog がどう報告し・どう読み出すかを確定する (§9、§11 L6-8)。
  - `docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md` :22 の「実需要が出てから別フェーズで判断」は**本裁定で上書きされる** — 原文は当時の記述として残し、**日付付きの否定注記**を置く (フェーズ5 D-3 の前例、`PHASE5_CONTRACT_150_AND_LIMIT_RANGE_V1.md` v1.5 の追補と同じ処置)。

**conformance vector**: (i) `application_catalog` が `unavailable` 以外の 1.6.0 peer で、catalog の全 entity の `fields` 全要素が `field_types` に現れること; (ii) `create_entity` の `field_types` / `add_field` の `field_type` で**宣言した型が、catalog にそのまま返ること** (round-trip); (iii) `field_types` の値が契約の **7 語 enum** に収まること; (iv) **型を宣言せずに作った field が `json` として返り、かつそこに任意の JSON 値 (オブジェクト・配列・文字列・数値・真偽値) を書けること** — 決定 (ii) の既定が両 peer で同じであることの実測であり、**MitateDB の既定変更が load-bearing になる vector** である; (v) MitateDB の flip 後、`application_catalog` の宣言と実挙動が一致すること (既存 C-11 / C-12 の逆向き検出が効くことの確認)。

### D-4 (WP-0 衛生、契約不変)

**決定 (a) flush 間隔の fail-fast**: 両 peer の `_optional_float` (`r2db-api/src/r2db_api/main.py:200-209`、`MitateDB-api/src/mitatedb_api/main.py:151-160`) を、**「環境変数が非空なら、有限かつ正の float 以外は起動時に fail-fast (変数名を含む `ValueError`)」**に改める。解釈不能文字列も fail-fast とする。

**なぜ `_optional_int` の degrade-to-default 規律と別扱いにするか**: この関数の唯一の消費者が flush 間隔であり (`R2DB_AUDIT_FLUSH_INTERVAL_S` / `MITATEDB_AUDIT_FLUSH_INTERVAL_S`)、**誤設定の帰結が無音のホットループ**だからである (§1.4)。既定値へ黙って落ちる形は、運用者が誤りに気付く経路を持たない。`_optional_int` を同じ形へ揃えるかどうかは**本フェーズで決めず、§11 に将来課題として記録する**。fail-fast の形自体は新規ではない — `R2DB_CONTROL_PLANE_STATUS` / `MITATEDB_CONTROL_PLANE_STATUS` の既存の起動時検査 (§1.5 の 7) と同型である。

**決定 (b) MitateDB の契約同梱**: r2db と同型に、`MitateDB-api/src/mitatedb_api/contract/data-service-api.v1.json` を package-data として同梱し、`importlib.resources` で読む。

- **`MitateDB-api/pyproject.toml` には `[tool.setuptools.*]` 節が 1 つも無い** (現存する節は `[build-system]` / `[project]` / `[project.optional-dependencies]` / `[tool.pytest.ini_options]` の 4 つのみ)。したがって **`[tool.setuptools.package-data]` 節の新設**が要る — r2db の `pyproject.toml:43-48` (`r2db_api = ["contract/*.json"]` とその説明コメント) を雛形にする。**「既存節への 1 行追加」ではない。**

- `MitateDB-api/src/mitatedb_api/http.py:47` の `Path(__file__).resolve().parents[3] / "spec"` を除去する。
- `spec/` との**byte 同一を固定するテスト**を `MitateDB-api/tests/` に置く — `r2db-api/tests/test_http.py:286` のほぼ逐語の双子であり、`parents[2]` の深さも一致する (§1.5 の 6)。**同型性テストの対象に加える。**
- `MitateDB-api/docker/Dockerfile` (コメント :85-125、`COPY` は :111) の手動 COPY と、そこに書かれた既知結合の注記を除去する。

**決定 (c) 同型性テストの機構を対応表駆動へ一般化する (v1.4、作業指示書突合の裁定 5)**: (a)(b) はどちらも**両 peer に同名の対応物を作る**変更であり、制約 3 (同名ヘルパは同型性テストで固定する) が掛かる。ところが現行の `test_peer_local_helpers_are_isomorphic_to_the_sibling_peer` (`r2db-api/tests/test_audit_query.py:2235` / `MitateDB-api/tests/test_audit_query.py:1933`) は **`this_module` の `getattr` + 兄弟 peer の `tests/test_audit_query.py` の只読み**という形であり、**兄弟ファイルの外にあるシンボルを対象にできない** (台帳 **L5-5**)。`_optional_float` は `src/<peer>/main.py`、byte 同一テストは `tests/test_http.py` にあるので、現行の形のままでは 2 件とも対象にできない。

- **機構を「(相対パス, シンボル名) の対応表」駆動へ一般化する。** 表の各行が「両 peer のこのファイルのこのシンボルは正規化 diff で同型でなければならない」を意味し、**表が対象の全数定義**になる。
- **既存 11 ヘルパ (`tests/test_audit_query.py`) はそのまま表の初期行として維持する** — 一般化は対象を減らさない。
- **本 WP で足す行は 2 つ**: `src/<peer>/main.py::_optional_float` と `tests/test_http.py` の byte 同一テスト関数 (`test_packaged_contract_copy_is_byte_identical_to_spec_source_of_truth`。MitateDB 側は WP-0 で新設する双子)。
- **ソース取得方式を両 peer とも `ast.get_source_segment` に統一する** — 訂正 (作業指示書 v1.1 起草者の実測): 非対称は peer 間ではなく**各テスト内の「自分側 vs 兄弟側」**である (両 peer とも自分側を `inspect.getsource`、兄弟側を `ast.get_source_segment` で取る: `r2db-api/tests/test_audit_query.py:2321/2326`、`MitateDB-api/tests/test_audit_query.py:2011/2016`)。統一は「自分側も AST から取る」形で行う。第 12 次引き継ぎ §4-2 (i) の記述は片方のテストから見たものであり、WP-4 で訂正註を置く。旧記述: 現行は MitateDB 側が `inspect.getsource` (デコレータを**含む**)、r2db 側が `ast.get_source_segment` (`FunctionDef.lineno` 起点なのでデコレータを**含まない**) であり、将来どちらかにデコレータが付くと**実装の差ではなく取得方式の差で赤/緑がぶれる** (台帳 **L5-6**)。**L5-6 はこの統一で閉じる。**
- **L5-5 は部分的に閉じる**: 走査範囲の拡張 (取りうる手当て (ii)) を採る。**兄弟 peer に対応物が無いヘルパは表に載せない** — 表が対象の全数定義である以上、「欠落を赤とするか対象から外すか」という未決の問いは「載せなければ対象外」として解ける。`_ms_from_pg_timeout_text` (MitateDB 側にのみ存在) は載せない。

**両 peer 同時**である。同名ヘルパ (`_optional_float`) は上記の表に載せて固定する (制約 3)。

### D-5 版束縛と移行 — 1.5.0 の前例を踏襲する

**決定**: 契約 1.6.0 の公開と両 peer の宣言 flip を、1.5.0 と同じ形で分離する。詳細は §8、WP 対応は §9。要点のみ:

- `spec/data-service-api.v1.json` の `contract_version` を **1.6.0** にし、`versioning.version_binding` に 1.6.0 の義務を逐条列挙する — **D-1 と D-2 は無条件義務** (D-2 の `surfaces.control` と D-1 の control 側は「control surface が提供されている限り」という前提を句として持つ — 1.4.0 (b) と同じ形)、**D-3 は条件付き義務** (`application_catalog` / `schema_operations` の status に依存)、**D-3 (vii) は 1.6.0 段落へ置かない同ラベル補筆**である。末尾の遡及否認の列挙にも 1.6.0 を加える。
- **r2db パッケージ内コピー**と、**WP-0 で新設する MitateDB パッケージ内コピー**を、いずれも `spec/` と**バイト同一**に同期する。
- 契約 1.6.0 の公開 (WP-1) では**どちらの peer の `contract_version` も動かさない**。過渡期に peer が 1.5.0 を宣言し続けるのは**正しい lag** であって非適合ではない。
- 1.5.0 との**再帰 diff** で「削除 0 / 型変更 0 / 狭化 0」を機械確認する (WP-1 の完了条件)。
- 全体 vacuity guard `…_every_adapter_declares_1_6_0` を WP-1 で `xfail(strict=True)` として登録し、**最後の flip WP と同一コミットで撤去**する。

---

## 4. 却下した代替案

### Q1 (D-1) について

- **(A) MitateDB のみ合成返却、r2db は現状維持**: クライアントから見た非互換は消えるが、**wire 形式の peer 非対称がそのまま残る** (一方は locator 付き token、他方は素の secret)。r2db は digest を索引キーにしたままで、rotate 後の locator の安定性も得られない (§3 D-1(b) の根拠 1・2)。制約 3 (peer 非対称を残さない) に反する。**なお v1.1 はここに「r2db は失敗認証を credential に帰属できない」も挙げていたが、それは現物と逆であり削除した (v1.2、§1.1)。**
- **(B) MitateDB を digest 索引へ揃える**: 対称にはなるが、**弱い側へ揃える**選択である。帰属能力を失い、rotate 後の locator の安定性も失う。依頼者設計原則「より良い設計で」に反する。
- **(D) 契約に `<id>.<secret>` 構造を明記する**: クライアントが自力で合成できるようにはなるが、**credential の不透明性を失う**。以後の形式変更が契約変更になり、契約が実装の内部構造に縛られる。制約 2 に反する。
- **(E) 二形式受理の互換シム**: 移行は楽になるが、**目先の回避**であり常設化の危険がある (「一時的な二重受理」は消える保証がない)。制約 5 と依頼者設計原則 3 (制約・制限で回避しない) に反する。r2db Stage 1 に production traffic が無い (§1.1) ため、そもそも必要がない。

### Q2 (D-2) について

- **(A) `control_base_url` 単独キー**: data 文書に control の URL を 1 本足すだけの最小形だが、**片方向**である — control 文書から data surface へ戻る手段が無く、また**自分自身の URL** も宣言されないので declare-and-echo が成立しない。
- **(B) `.well-known` 文書**: 発見の標準的な形ではあるが、**契約外の新しい経路**を作る。契約は既に `/v1/capabilities` を発見点と定めており、そこに 1 キー足す方が読み手にとって単純である (依頼者設計原則 2)。
- **(C) `capabilities.control_plane` の value 内に URL を置く**: 既存キーの中に収まるが、**capability の status (提供しているか) と配備トポロジ (どこにあるか) を混ぜる**。`capabilities.<x>` の value schema は status を必須とする「能力の宣言」の場所であり、所在の宣言はそこではない。

### Q3 (D-3) について

- **(A) r2db のみ型付き、MitateDB は `unavailable` のまま**: 契約変更は小さくなるが、**発見性の peer 非対称**が残る — 「共通仕様 + base URL + API key だけで peer 非依存に利用できる」という本フェーズのテーマそのものが片 peer で成立しない。制約 3 に反する。
- **(B) null 可否・既定値も宣言する**: catalog の情報量は増えるが、**契約の schema operations がそれらを定義していない**以上、宣言は根拠を持たない。「宣言と実挙動の一致」を機械検証できない宣言を足すことになり、declare-the-hazard の趣旨 (宣言は真実である) に反する。
- **(C) 新 endpoint (`/v1/schema`) を作る**: catalog と schema 記述が二重化する。既存の `GET /v1/catalog` の拡張で足りる。
- **(D) `unknown` を型語彙に足す**: 型無し field を「未知」として宣言できるようにする案。**`unknown` は型ではない** — クライアントは何を書けるか分からず、宣言は判断材料にならない。採ったのは **`json` (any JSON value)** であり (D-3 (i))、これは実在の型である — r2db の型無し列は既に JSONB = any JSON value であり (§1.5 の 1a)、`json` はその既定を正直に名付けたにすぎない。クライアントは「そこに任意の JSON 値を書ける」と読めて判断できる。
- **(E) 型無し field を作れなくする (create_entity で `field_types` を必須にする)**: v1.0 が採っていた形であり、**採らない** — `fields` だけを伴う `create_entity` は 1.5.0 で有効なリクエストであり、1.6.0 実装がそれを拒否するのは `versioning.compatibility` が言う semantic change に当たる (minor 版では許されない)。既定型を契約が定める (D-3 (ii)) 方が、既存クライアントを壊さずに「すべての field に型がある」を満たす。

### D-4 (衛生) について

- **flush 間隔を `max(0.0, …)` で丸める** (MitateDB の alert 側と同じ処置): ホットループは消えるが、**運用者は誤設定に気付かない**。0 を渡した配備が「既定間隔で動いている」ことを知る経路が無い。declare-the-hazard の観点では、**起動時に落ちる方が誠実**である。
- **`_optional_int` も同時に fail-fast へ揃える**: 対称性は上がるが、**degrade-to-default を前提にした既存配備を壊しうる**変更であり、本フェーズの射程 (指摘 4 = flush 間隔) を超える。§11 に将来課題として記録する。

---

## 5. 依頼者確定待ち

本設計で未確定なのは**契約の英文の最終文言のみ**である。両論を残している箇所は無い。

**確定記録 (2026-09-04)**: 下記 (1)〜(5) の英文 (および (4) の遡及否認 4 行への `1.6.0-only` 追記) は、監督が依頼者へ提示し、依頼者が同日「進めてください」で確定した。確定文の正本は scratchpad の `phase6-contract-prose.md` (WP-1 の実装者はそこから逐語複製する)。以後、本節の文言を変える場合は再度の依頼者確定を要する。

確定を要するのは次の 5 か所であり、骨子は下記のとおりである。**確定後は scratchpad の確定文ファイルから逐語複製し、文字列ピンのテストを置く** (1.5.0 の運用と同じ)。

**(1) D-1 — `security.schemes.*` の description と `CredentialIssued.secret`**

> `CredentialIssued.secret` — and the `secret` a rotate response returns, wherever this contract defines one — **is the complete bearer token for the surface that credential is for**: a client presents that exact string, verbatim, as `Authorization: Bearer <secret>`; an application credential on the application surface, a control or audit credential on the control surface (`security.schemes.control_credential` continues to state that application credentials are not accepted there). A client MUST NOT compose it from, split it into, or derive it from any other field of the response — `credential_id` is returned as its own field, for naming the credential in later control operations, and is never something a client extracts from the secret. Its internal structure is opaque; an implementation may change that structure without a contract change, and no client may depend on it. The service still stores only a verifier/digest and never returns the secret again.

**(2) D-2 — `CapabilityDocument.surfaces` の説明文**

> `surfaces` names the absolute base URLs at which this deployment's own surfaces are reached, **as declared by the deployer** — never derived, and never to be inferred by a client from the URL it happened to use. `surfaces.data.base_url` ends at `versioning.base_path`; `surfaces.control.base_url` ends at `versioning.control_base_path`. **The data surface's capability document and the control surface's own capability document return the same `surfaces` object**, so a client holding either base URL can reach the other surface, and either document, fetched again at its own declared URL, answers with the same `contract_version` and the same `surfaces` — the rest of each document remains scoped to the credential presented. A deployment declaring `control_plane` as `unavailable` omits `surfaces.control`. Neither URL ends in a trailing slash, so that appending a path to it yields exactly one separator. Whether the two surfaces share a host is read from the **origins** (scheme, host and port — not the path) of these two URLs — the co-hosting `versioning.control_discovery` permits — and is never assumed; where `surfaces.control` is absent, the surfaces are not co-hosted. **Where the two surfaces run as separate processes, both are configured from the same declaration**: neither can verify the other's document, so a deployment whose two documents disagree is non-conformant, and a client is given no rule for preferring one over the other.

**(3) D-3 — 型語彙の 7 語目 `json`、既定型、catalog の原則文と `field_types` (`EntityDescriptor` 側 / `SchemaOperationRequest` 側)**

> The field-type vocabulary gains a seventh member, `json`, meaning **any JSON value**. **A field created without a declared type has type `json`** — this names an existing default rather than introducing a new one, and there is no "unknown" member of the vocabulary: every field carries a real type.
>
> `EntityDescriptor.field_types` maps every name in `fields` to that field's type, drawn from that same vocabulary. What a client declared — through `SchemaOperationRequest.field_types` on `create_entity`, or `field_type` on `add_field` — is what the catalog reports back, and a field for which no type was declared reports `json`. Where a schema operation later redeclares a field's type, the catalog reports the type most recently declared. **The catalog reports only facts this contract's own schema operations can establish**: it declares neither nullability, nor default values, nor whether a field is required, because no schema operation defined here establishes any of them; a later version that gives schema operations such a notion gives it to the catalog in that same version.
>
> `object` and `array` are narrower than `json`: a field declared `json` accepts **any** JSON value, including but not limited to objects and arrays, while a field declared `object` or `array` accepts only that shape — and the catalog reports the narrower word it was declared with, never rounding it up to `json`.
>
> `SchemaOperationRequest.field_types` and `EntityDescriptor.field_types` share one object shape but not one coverage rule: **the request's object may be partial** — any name in `fields` that it omits is created with type `json` — while **the catalog's object is always total over that entity's own `fields`**. `SchemaOperationRequest.field_types` is **never required**: a `create_entity` naming only `fields` remains a valid request, creating `json` fields. A `field_types` naming a field the request's own `fields` does not name, a `field_types` value outside this vocabulary, or a `field_types` sent without `fields`, each fails `VALIDATION_FAILED`; none of the three is silently ignored. `add_field` continues to carry a single `field_type` for the single field it adds.

**(4) `versioning.version_binding` の 1.6.0 段落** (分類語は契約既存の 1.4.0 段落の taxonomy に揃えた — G6。`control_plane` / `audit_query` のような**配備前提**を持つ義務も、1.4.0 (b) の前例どおり **unconditional** と呼び、その前提を句として添える。**conditional と呼ぶのは capability の status に依存するもの**だけである)

> Only an implementation declaring 1.6.0 or higher additionally claims conformance to the obligations 1.6.0 introduces (subordinate ruling 11). **Two of those obligations are unconditional in the same sense as every obligation enumerated above** — they bind simply by declaring 1.6.0, independent of any capability's own status: (a) its `GET /v1/capabilities` document carries `surfaces.data.base_url`, the absolute base URL of its own data surface, and — where a control surface is provided at all (`control_plane` other than `unavailable`, the same precondition subordinate rulings 8 and 9 already carry) — both surfaces' capability documents additionally carry `surfaces.control.base_url`, each document carrying the same `surfaces`; and (b) the `secret` returned by any issue or rotate path it offers, in band or out of band, is accepted verbatim as a bearer token on the surface that credential is for, with no composition, splitting, or derivation required of the client (`security.schemes`). **The remaining 1.6.0 obligations are conditional**, in the same sense 1.4.0's own conditional list is: they bind only insofar as the implementation's own `capabilities()` declares the named capability as something other than `unavailable`. Where it declares `application_catalog` as something other than `unavailable`: (1) every `EntityDescriptor` it returns carries `field_types`, total over that entity's own `fields`, reporting `json` for any field created without a declared type. Where it declares `schema_operations` as something other than `unavailable`: (2) a `create_entity` it executes accepts `field_types` and creates each field named there with the type declared there, and an `add_field` it executes accepts every member of the seven-member vocabulary, `json` included; a `field_types` naming a field outside the request's own `fields`, carrying a value outside that vocabulary, or sent without `fields`, is refused with `VALIDATION_FAILED`. **1.6.0 introduces no obligation on what a client must send**: `SchemaOperationRequest.field_types` is optional wherever it appears, and a request valid under 1.5.0 stays valid. An implementation still declaring 1.5.0 is not held to any 1.6.0-only obligation retroactively.

**既存の遡及否認 4 行への追記 (G19。文言は機械的であり、確定文の一部として同時に提示する)**: 現物末尾は「An implementation still declaring 1.1.0 … is not held to any 1.2.0-only, 1.3.0-only, 1.4.0-only, or 1.5.0-only obligation retroactively, an implementation declaring 1.2.0 is not held to any 1.3.0-only, 1.4.0-only, or 1.5.0-only …」と **4 行を明示列挙**する。**その 4 行それぞれに `1.6.0-only` を加える** (1.1.0 の行は「1.2.0-only, 1.3.0-only, 1.4.0-only, 1.5.0-only, or 1.6.0-only」となる)。上の確定文が足す 5 行目 (1.5.0 の行) だけでは列挙が閉じない。

**(5) D-3 (vii) — `structured_operations.upsert` の 1 文への同ラベル補筆** (フェーズ5 D-2 と同じ形式。1.6.0 段落へは置かず、当該節の本文を補筆する)

**置換する対象は 1 文であり、その文は 2 つの義務を運ぶ (G4)。** 現物は逐語で:

> upsert on an entity without a declared uniqueness key, and upsert or update on an entity not declaring the mutable class, fail with CAPABILITY_UNSUPPORTED.

**前半 (unique key 不在時の upsert 拒否) は逐語で残し、後半だけを限定する。** r2db は `create_index` を持ち `row_addressability` を提供するので、前半の義務は実際に効いている。確定文は**2 句そろえた全文**である:

> upsert on an entity without a declared uniqueness key fails with `CAPABILITY_UNSUPPORTED`; and, where `row_addressability` is provided (other than `unavailable`) — the same precondition `mutation_classes.rule` carries for the declaration itself — upsert or update on an entity not declaring the mutable class fails with `CAPABILITY_UNSUPPORTED` as well. An implementation that does not provide `row_addressability` does not thereby declare a mutation class for any entity, and this sentence does not refuse the mutations its own `atomic_mutation` capability declares.

**語法の注記 2 点**:

- **(G8) 限定句は `other than unavailable` である** — 契約既存の語法に揃える。`enabled` だけを条件にすると `partial` を落とす。`CapabilityDocument` の status 語彙は `enabled` / `partial` / `unavailable` / `planned` の 4 値であり、MitateDB は現に `structured_query` / `atomic_mutation` / `schema_operations` を **`partial`** で宣言している (`cell.py:1282` / `:1283` / `:1291`)。**`mutation_classes.rule` の側は現行 `enabled` のままである**ため、本補筆によって 2 つの記述の語法が揃わなくなる — この不揃いを §11 **L6-10** に起票する (rule 側を同じ語法へ揃えるかは次に契約文を触るときの判断事項であり、本版では rule 側を変えない)。
- **(G9) `declaration_required` を出典として引かない** — 現物は「an implementation must not advertise `row_addressability` as **enabled** until every entity carries a declaration」であり、これは「enabled を名乗るなら全 entity が宣言を持て」であって「`unavailable` なら宣言してはならない」ではない。確定文は出典参照を外し、`does not thereby declare` (そのこと自体によって宣言することにはならない) に留めてある。

**契約ファイルを変更するコミット (WP-1) の直前に、監督が依頼者へ再度明示し、確定を得てから WP-1 を確定させる** (§2 の 10)。文言以外の設計判断 (キーを足すこと自体、義務の条件付き性、互換シムを置かないこと、MitateDB の catalog flip) は監督裁定済みであり、本節の対象ではない。

---

## 6. conformance / port への影響

### 6.1 port v1.10

`conformance-tests/adapter.py` を **v1.10** へ上げる。3 点である。

1. **credential の verbatim 使用を規約にする (D-1)**。port の規約文に「**adapter は issue / rotate / bootstrap / reset が返した `secret` を、いかなる加工もせずそのまま bearer として使う**」を置く。`CredentialHandle.secret` / `ControlCredentialHandle.secret` の意味を「**完全な bearer token**」と定義し直す (現在は peer ごとの解釈が入っている — `conformance_adapter_mitatedb_http.py:447` / `:934-946`)。`_Session.bearer` フィールド自体は残す (意味は「`Bearer ` の後ろに置く文字列」であり、D-1 後は `secret` と同値になる)。
   - **規約は WP-1 で置き、§1.5 の 5 の 4 箇所の合成の撤去は WP-3 と同一コミットである (v1.2、F4)。** WP-1 では「合成が存在しないこと」の静的固定テストを `xfail(strict=True)` で先置きする。
   - **bootstrap 由来の bare secret と rotate 由来の合成 secret が同じ handle 型に混在する期間を作らない** — MitateDB の全発行点 (in-band / 帯域外 store API / ops CLI) を**同一コミットで**合成形にする (§3 D-1(d))。混在は `_control_send` (`:943-945`) の二重前置 (`id.id.secret`) を実際に生む。
   - **発行は `(credential_id, bearer)` の 2 値である (v1.3、G1)**。port の規約に「**adapter は `credential_ref` に発行側が返した `credential_id` を、bearer に発行側が返した `secret` を、それぞれそのまま持つ — 連結も分割もしない**」と書く。`credential_ref` は revoke / rotate の URL 組み立てに要るので (`conformance-tests/adapter.py:64-68`)、bearer から取り出す形にしてはならない。
2. **同居判定を `surfaces` 由来にする (D-2)。判定関数は port v1.10 に置くが、申告メソッドの削除は WP-3 と同一コミットである (v1.2、F5)。** 理由: `conformance-tests/test_c09_audit_evidence.py:868` が `control_surface_cohosted_with_data_plane()` を**版分岐なしに無条件で**呼んでおり (同 `:833-841` の docstring が逐語で「this is an **UNCONDITIONAL** obligation, unlike every other vector in this file that branches on `contract_version`/`audit_query` status」と書く)、`surfaces` は WP-2 / WP-3 まで出ない。WP-1 で申告を消すと**この無条件 vector が 2 つの WP をまたいで判定不能になる**し、declare-first で逃がせば**無条件義務を条件付きへ格下げする**ことになる。
   - **WP-1**: `surfaces` を返す peer では `surfaces` の origin 比較を正とし、返さない (1.5.0 宣言の) peer では**従来の申告メソッドへフォールバック**する判定関数を port に置く。`surfaces.control` が無い配備の判定は `False` である (§3 D-2)。
   - **WP-3 (最後の flip と同一コミット)**: 申告メソッドを port から削り、4 plug の実装も同時に削る。フォールバック分岐もこのとき消す。**台帳 L5-4 はここで閉じる。**
3. **catalog vector 用に、fixture が「create / add_field で宣言した型」を保持する (D-3)**。round-trip vector (宣言した型が catalog に返り、書いた値が同じ値で読み戻せること) を共通 suite が書けるようにするための最小の追加である。既存の `Fixture` に宣言型を持たせる形か、新メソッドを 1 本足す形かは作業指示書で確定する — 本設計は「**共通 suite が、自分が宣言した型を知った状態で catalog と読み出し値を突合できること**」までを決める。

`docs/design/CONFORMANCE_ADAPTER_V1.md` に **§20 (v1.10)** を新設して記録する (§19 = v1.9 と同じ構成: 追加/削除メソッドの意味論 / 既存機構との関係 / 互換性影響)。**メソッドを削る port 改訂は本 port で初めてである**ため、その事実と、**削除が WP-3 に落ちること・4 plug すべてに同時に落ちること** (Python の `ABC` は不要になったメソッドを自動では消さない — plug 側の実装も同一コミットで削る) を §20 に明記する。**port の版数は WP-1 で v1.10 に上げ、WP-3 の削除もその v1.10 の一部として §20 に記す** (2 つの WP にまたがる 1 つの port 改訂であることを明記する)。

### 6.2 新 vector (4 plug 全数、非空 precondition 付き)

いずれも **1.6.0 以上を宣言する peer に対して**課す (declare-first 分岐は既存の `_semver_tuple` を使う)。

1. **credential verbatim (D-1)** — issue / rotate が返した `secret` を、**adapter の加工なしに**そのまま bearer として提示し、認証が通ること。**surface ごとに書き分ける (v1.2、F7)**: **application credential は data surface** (`GET /v1/capabilities`) で、**control credential は control surface** (`GET /control/v1/capabilities`) で verbatim に通ること。**直積では書かない** — 契約 `security.schemes.control_credential` は「application credentials are not accepted」と書いており、application credential を control surface へ通す要求は権限境界を壊す。交差 (application → control、control → data) は既存の **C-13 / C-14** が拒否側で固定済みであり、本 vector は重複しない。**precondition**: `control_plane` が `unavailable` 以外であること (in-band 発行が存在すること)。
2. **`surfaces` の双方向一致 + declare-and-echo (D-2)** — **plug ごとの適用範囲を明示して分ける (v1.2、F14)**:
   - **(i) data 文書と control 文書の `surfaces` が一致すること**、**(ii) `control_plane` が `unavailable` 以外なら `surfaces.control` が存在すること (`unavailable` なら存在しないこと)** — **4 plug 全数**に課す (どちらも文書を読むだけで、実 URL への到達を要さない)。
   - **(iii) declare-and-echo** (`surfaces.<x>.base_url` の `/capabilities` を叩き直すと同じ `contract_version` と同じ `surfaces` が返ること) — **HTTP plug 2 件のみ**に課す。in-process plug は実 URL を持たず合成の偽ドメインを申告するため (§6.4)、**4 plug 全数に課すと in-process plug で空振りする** (常設規律 1 に触れる)。**この分割と、in-process plug では宣言された URL の実在を検証していないことを `CONDITIONS.md` に限界として開示する** (§6.3、§11 L6-5)。
3. **`field_types` が宣言型と一致し、値が round-trip すること (D-3)** — (i) catalog の全 entity で `fields` ⊆ `field_types` のキー集合、かつ値が契約の **7 語 enum** に収まること; (ii) `create_entity` の `field_types` / `add_field` の `field_type` で宣言した型が catalog にそのまま現れること (**宣言の** round-trip); (iii) **値の round-trip (v1.2、F2/F3 で強化)** — 型を宣言せずに作った field が `json` として返り、そこへ書いた**オブジェクト・配列・文字列・数値・真偽値のそれぞれが、同じ JSON 値として読み戻せること**。「書けること」だけでは足りない — MitateDB は現状 dict を書けても**文字列として読み戻す** (§1.5 の 1b)。**`boolean` を宣言した field についても同じ round-trip を課す** (書いた `true` が `true` で読み戻ること) — MitateDB は現状 `0`/`1` で round-trip する (§1.5 の 1b-2)。**(iv) 否定側 (v1.3、G3。v1.4 で対象語を 6 語に訂正)** — **宣言型に合わない値の書き込みが `VALIDATION_FAILED` で拒否されること**を、**`json` を除く 6 語**それぞれについて **4 plug 全数**で見る (`boolean` に `7`、`integer` に `"abc"`、`number` に `"abc"`、`string` に数値、`object` に配列、`array` にオブジェクト)。**`json` は対象外である** — `json` は any JSON value であり、**違反値が存在しない**ので否定側の vector を書けない (書けば空振りになり、常設規律 1 に触れる)。`json` を宣言した field については (iii) の肯定側 (5 種の JSON 値がすべて round-trip すること) が担う。**(iii) の肯定側だけでは、強制の無い宣言型が緑のまま出荷される** — sqlite backed の in-process plug がまさにその状態である (§1.5 の 1b-1)。**precondition**: `application_catalog` が `unavailable` 以外であること。**`field_types` を送らない `create_entity` が両 peer で受理されること自体も (iii) が併せて見る** (任意性の実測)。
4. **MitateDB flip 後の `application_catalog` の宣言と実挙動の一致** — 既存の C-11 / C-12 系の逆向き検出 (宣言が `enabled` なのに `CAPABILITY_UNSUPPORTED` を返せば赤) が効くことの確認である。**新 vector を足すのではなく、既存 vector が flip によって load-bearing になることを確認する** — vacuous でなくなることを WP-3 の完了条件に置く。

**adapter が bearer を組み立ても分解もしないことの静的固定 (D-1(e)。v1.3、G1 で分解側を追加)**: 4 adapter のソースを走査し、**2 つの性質**を固定するテストを共通 suite に置く。**(a) 合成が無いこと** — `credential_id` (または `credential_ref`) と `secret` を連結する式が存在しない。**(b) 分解が無いこと** — `secret` (または handle の bearer 値) に対する `split` / `partition` / `rsplit` / 添字スライスが存在しない。**(b) を落とすと G1 の抜け道が残る** — 合成をやめても、id を bearer から割り出す実装は連結式を持たないので (a) だけでは緑のまま通る。**規則の形は逐語プロトタイプの後に確定する** (常設規律 5) — フェーズ5 の走査器と同じ手順である。走査対象・許容形・除外リストの要否は WP-1 で実測して決める。

**全体 vacuity guard**: `…_every_adapter_declares_1_6_0` を 1 本置く。**WP-1 で `xfail(strict=True)` として登録**し、**最後の flip WP と同一コミットで撤去**する。形は既存の `test_c09_every_control_surface_adapter_takes_the_provided_branch` と同形 (非 parametrize の関数 1 本が `registered_adapters()` を自前で走査する) にする — `xfail(strict=True)` を最後の flip で外す運用がこの形を前提にしている。

### 6.3 CONDITIONS.md — 起草者の案 (監督裁定事項)

枠 §6 のとおり、新条件を切るか既存行に載せるかは起草者が案を出し、監督が裁定する。

**案 (推奨)**: **新条件 C-19「クライアント自足性 (client self-sufficiency)」を 1 行切る** — 「共通仕様と 1 つの base URL と 1 つの credential だけを持つクライアントが、実装知識なしに、両 surface へ到達し、認証し、entity の型を発見できる」。理由は 3 点である。

1. **既存行のどれとも命題が違う**。C-12 は「宣言と実挙動の一致」(agreement)、C-13 / C-14 は認可境界である。D-1 / D-2 / D-3 が新たに主張するのは「**実装知識なしで到達できる**」という**発見性**の命題であり、agreement の一種ではない。
2. **3 決定が 1 つのテーマの 3 面である**。credential / surface / 型は別々の条件に散らすより 1 条件の 3 vector にする方が、読み手 (AI エージェント統合者) にとって主張が見える。
3. **限界の開示先が要る**。port から `control_surface_cohosted_with_data_plane()` が消える (WP-3) ことで L5-4 が閉じる事実、および「`surfaces` は配備者の表明であり、宣言された URL が実在することは declare-and-echo でしか検証していない」という射程を書く先が要る。

**C-19 に書く限界 (v1.2 で確定)**: (a) declare-and-echo は **HTTP plug 2 件でのみ**実測し、in-process plug は合成の偽ドメインを申告する (§6.2 の 2、§6.4、L6-5); (b) **`surfaces` の 2 プロセス間ドリフトは実装が検出できない** — 検出は配備後チェックと declare-and-echo だけである (§3 D-2 の (b)、L6-5a); (c) 型付き catalog の round-trip は**共通 suite が書いた値についてのみ**であり、既存データの表現は射程外である (L6-8)。

**併せて更新する既存行**: **C-09 行** — L5-4 の開示 (申告を独立に検証する機構が無い) を「port v1.10 で申告を宣言由来へ置換した (削除は WP-3)」という**閉止の記録**へ書き換える。**C-11 / C-12 行** — MitateDB の `application_catalog` が `unavailable` から `enabled` へ変わったことで、当該 capability についての agreement 検査が vacuous でなくなった事実を記録する。**C-17 行** — MitateDB が catalog を返すようになるが `row_addressability: unavailable` のまま `mutation_class` を宣言しないこと、および D-3 (vii) の `upsert` 補筆でその形が契約上一意になったことを記録する。

**代替案 (採らないが記録する)**: すべて C-12 行に載せる。行が肥大し、発見性という新しい命題が agreement の下位に埋もれる。

### 6.4 conformance 構成への影響

- **`surfaces` は 4 plug すべてに base URL の申告を要求する。** in-process plug は実 URL を持たないため、**合成の (実在しない) base URL を構成として与える**形になる — `https://data.example.invalid/v1` / `https://control.example.invalid/control/v1` のような偽ドメインを使う (制約 9)。**declare-and-echo vector は、その URL へ実際に到達できる plug (HTTP plug) でのみ実行し、in-process plug では「到達できない」ことを CONDITIONS.md に限界として開示する** — フェーズ5 D-2 の「認証面代替」と同じ開示の形である。この扱いは WP-1 の実測で確定する。
- **同居判定**: 4 plug とも現行の申告は `False` である。`surfaces` 由来へ置換した後も同じ判定になることを WP-1 で確認する (置換が挙動を変えないことの実測)。

---

## 7. Security Invariants との関係

**新しい invariant は不要である。** 本フェーズは既存の担保を機械検証で厚くし、クライアントから見た peer 非対称を消すものであって、新しい共通安全性質を導入しない。**監査の帰属能力は変えない** (SI-14、§1.1)。

- **SI-14 (Security-Relevant Auditability)** — **不変**である。**D-1 は帰属能力を変えない。** §1.1 のとおり、両 peer とも credential に帰属するのは「digest 一致後に state で拒否された場合」だけであり、digest 不一致は `actor_id=None` で記録する — **既に対称**である (MitateDB `auth.py:383` / `:398-420` の B-1 裁定 2026-09-03、r2db `service.py:1173-1190`)。locator が token に入っても、**クライアントが申告した locator を監査に載せてはならない**という既決の規律は r2db 側でも維持する (§3 D-1 の実装拘束 3)。監査に secret を書かない規律も変わらない。**v1.1 は本行を「改善」と書いていたが、その根拠は現物と逆であり訂正した (v1.2)。**
- **SI-10 (Error and Information Non-Disclosure)** — **不変**である。失敗応答は `AUTH_INVALID` 一様のままであり、**locator が既知か未知かを応答で漏らさない** (§3 D-1 に明記)。区別は監査証拠の側にだけ現れる。`surfaces` が公開するのは**配備者が自ら表明した base URL** であって内部トポロジではない — capability document は既に認証を要する面であり、そこに配備者が意図して置いた所在情報が現れることは "unnecessary internal information" に当たらない。
- **SI-06 (Server-Bound Credential Scope)** — **不変**である。token に credential_id が含まれても、**scope は依然としてサーバが権威ある credential 状態から導出する**。クライアントが locator を書き換えても、その locator の行の digest と一致しない限り認証は通らない (別 credential の locator + 自分の secret 部は `AUTH_INVALID`)。「リクエスト内容で scope を広げられない」という要求は保たれる。
- **SI-07 (Compromised Credential Containment)** — **不変**である。credential_id は非秘密 (`list_credentials` の応答に現れる) であり、token に含めても攻撃者が新たに得る情報は無い。盗まれた token の権限は、その credential に意図して割り当てられた権限のままである。
- **SI-13 (Revocation and Disable Effectiveness)** — **不変**である。失効・無効の判定は行参照の**後**に行われ、判定順序 (revoked → enabled) も変わらない。むしろ locator 参照は「その credential の行」を一意に特定するため、失効判定の対象が構造的に明確になる。伝播境界の宣言 (`authorization_propagation_bound_ms`) は変わらない。
- **SI-15 (Fail-Closed Authorization)** — **保たれる**。**locator の不正形は fail-closed** である — `.` を含まない / locator 部が空 / secret 部が空 のいずれも、認証を実行せず `AUTH_INVALID` で閉じる (§3 D-1)。`surfaces` の環境変数が不正形なら**起動時に失敗する** (§3 D-2) ので、嘘の所在を宣言したまま動く配備が生じない。D-4(a) の flush 間隔 fail-fast も同じ姿勢である。
- **SI-00 (Single-Compromise Containment)** — **不変**である。D-2 は所在を宣言するだけであり、**data-plane プロセスに control credential store を持たせない**構造 (フェーズ5 D-2 が契約の読みとして一意にしたもの) を変えない。`surfaces.control` を宣言することは「control surface がそこにある」という事実の表明であって、data プロセスが control 権限を持つことではない。
- **SI-08 (Bounded Resource Consumption)** — **改善**する (副次的)。D-4(a) の fail-fast は、**誤設定によって flush スレッドが CPU を無制限に消費する形**を起動時に止める。宣言された窓の pre-auth 強制という要求される安全結果は変わらない。

`security/CONTROL_MAPPING.md` の更新対象は **SI-06 / SI-07 / SI-10 / SI-13 / SI-14 / SI-15** の各行 (両 peer の cell を**対で**書き換える — フェーズ5 WP-4 で SI-08 行について実施した形と同じ) と、**SI-08 行** (D-4(a)) である。

---

## 8. 版束縛と移行

契約 1.5.0 の出荷 (従属判断 10、WP-1 `6e38ef8` → r2db `ed4394a` → MitateDB `3f2da59`) と同じ形を踏襲する。

1. **契約 1.6.0 の公開 (WP-1、単一コミット)**
   - `spec/data-service-api.v1.json`: `contract_version` を **1.6.0** へ。**項目 1 (D-1)** を `security.schemes.*` / `schemas.CredentialIssued.secret` の description に「Since 1.6.0 (subordinate ruling 11, item 1; unconditional -- versioning.version_binding)」書式で (v1.4 訂正 — 項目 1・2 は**無条件義務**であり、control surface に関わる部分は前提を句として添える形である。§8 の 4、G6。`conditional on ...` と書く v1.2 由来の書式例は誤りだった。既存の同型例は `structured_operations.reserved_entity_names_note` の「Since 1.4.0 (subordinate ruling 9, item 6; unconditional -- versioning.version_binding)」である)、**項目 2 (D-2)** を `schemas.CapabilityDocument.properties.surfaces` として、**項目 3 (D-3)** を `definitions.EntityDescriptor.properties.field_types` と `schemas.SchemaOperationRequest.properties.field_types` として追加し、`versioning.version_binding` の **1.6.0 段落**に無条件義務 1 件と条件付き義務を逐条列挙する。末尾の遡及否認の列挙にも 1.6.0 を加える。
   - **r2db パッケージ内コピー** (`r2db-api/src/r2db_api/contract/data-service-api.v1.json`) と **MitateDB パッケージ内コピー** (`MitateDB-api/src/mitatedb_api/contract/data-service-api.v1.json`、WP-0 で新設) を**バイト同一**に同期する (両 peer の byte 同一テストが固定する)。
   - `spec/CCR_DISPOSITION.md` に**従属判断 11** を house style で記録する: **(a) 各項目の内容と根拠**、**(b) すべて additive である根拠**、**(c) 版数の扱い**、**(d) 監督裁定の参照**、および**項目ごとの再検討条件**。項目 1 = D-1 (credential の完全 bearer 化)、項目 2 = D-2 (`surfaces`)、項目 3 = D-3 (型語彙の `json`・既定型・`field_types` — `EntityDescriptor` と `SchemaOperationRequest` の両方)、**項目 4 = D-3 (vii) (`structured_operations.upsert` の一文への `row_addressability` 限定の同ラベル補筆。1.6.0 段落へは置かない — フェーズ5 従属判断 10 項目 2 と同じ形式)**。
   - **従属判断 10 の house style に倣い、「義務の条件付き性」を独立した太字段落で書く** — **項目 1 (D-1) と項目 2 (D-2) は無条件義務**であり、そのうち control surface に関わる部分は「control surface が提供されている限り」という前提を句として持つ (契約既存の 1.4.0 (b) と同じ分類。v1.3、G6)。**条件付きなのは項目 3 (D-3) だけ**であり、`application_catalog` / `schema_operations` の status に依存する。**項目 4 (D-3 (vii)) は 1.6.0 段落へ置かない同ラベル補筆**なので、この分類の外である。`version_binding` 本文の列挙と 1 対 1 に対応させる。
   - 共通テスト (§6.2 の新 vector) + **port v1.10** (§6.1 — verbatim 規約 / `surfaces` 由来の同居判定の追加と申告メソッドのフォールバック存置 / catalog fixture) + **全体 vacuity guard と合成不在テストをともに `xfail(strict=True)` で登録** + `CONFORMANCE_ADAPTER_V1.md` §20。**adapter の合成撤去と申告メソッドの削除は WP-1 に含めない** (ともに WP-3、§6.1)。
   - **peer の版数 flip は含まない。**
2. **r2db の 1.6.0 出荷 (WP-2、単一 peer コミット)**: locator 形 credential (application + control、in-memory / Postgres の両 store) + `surfaces` (data / control の 2 文書) + `field_types` (in-memory / Postgres の両 catalog、および create_entity の型受理) + **`contract_version` 1.6.0 flip** + 版数のテスト固定更新。runbook に既存 credential の再発行手順を置く。
3. **MitateDB の 1.6.0 出荷 (WP-3、単一 peer コミット)**: 合成返却 (issue / rotate) + `surfaces` (data / control の 2 文書) + **`application_catalog` の flip と `GET /v1/catalog` の実装** (宣言型の保持機構を含む) + **`contract_version` 1.6.0 flip** + **全体 vacuity guard の `xfail` 撤去を同一コミットで行う** — flip 自身が guard を無介助で緑にすることを示す。
4. **移行の非破壊性 (additive の根拠)**:
   - **D-1**: 契約に**新しいキーを足さない** — 既存 `secret` の**意味を明文化する**だけである。1.5.0 以前の実装は「不透明な文字列を返す」と読んでおり、その読みは変わらない。1.6.0 の義務 (verbatim 受理) は**1.6.0 を宣言する実装にのみ**掛かる。**peer の wire 形式の変更は契約の変更ではない** — 契約は構造を定めていないからである。
   - **D-2**: `CapabilityDocument` に**任意プロパティを 1 つ足す**。`required` は変えないので、既存の 1.5.0 文書は依然として schema に適合する。`additionalProperties: false` の封筒に**プロパティを追加する**のは狭化ではなく拡大である。
   - **D-3**: 3 つの additive 変更からなる。(a) `EntityDescriptor` と `SchemaOperationRequest` に**任意プロパティ `field_types` を 1 つずつ足す** — 既存 `fields` の型 (string 配列) は変えず、**`field_types` を要求もしない** (§3 D-3 (iv))。したがって **1.5.0 で有効なリクエストは 1.6.0 実装でもそのまま有効**であり、`versioning.compatibility` が言う semantic change に当たらない。(b) `field_type` の enum に **`json` を足す** — enum への**追加**は受理域の拡大であって狭化ではない。(c) 「型を宣言せずに作られた field の型は `json` である」という**既定の明文化** — 1.5.0 以前の契約はこの既定を定めておらず、実装ごとに違っていた (§1.5 の 1a)。**明文化によって 1.6.0 実装が既存の要求を失うことは無く、既定が peer 間で揃う。**
     - **MitateDB の挙動変更 3 件は契約の additive 性を損なわない**: (α) 型無し field の既定 `text` → `json` — 契約はこれまでこの既定を定めておらず、`text` は契約が要求した挙動ではなかった。変更後は**受理域が広がる**だけであり (文字列は引き続き書ける)。(β) `json` / `object` / `array` の**読み出し表現を JSON 値へ復元する** (現状は文字列で返る、§1.5 の 1b) — 契約の "any JSON value" を満たすための是正であり、**契約が要求していた挙動へ近づける**変更である。(γ) 宣言 `boolean` の wire 表現を **0/1 → JSON boolean** へ (§1.5 の 1b-2) — catalog が `boolean` を宣言する以上、`0`/`1` を返すことは宣言と実挙動の不一致であり、是正しなければ**型付き catalog が最初から嘘を宣言する**。(β)(γ) は**観測可能な挙動の変更**であり、MitateDB の既存クライアントに影響しうる — **3 件とも 1.6.0 を宣言する MitateDB のコミット (WP-3) と同一コミットに落ちる** (宣言と挙動を同一コミットでしか動かさない規律)。実 DB への影響は WP-3 の実測事項である (§9、§11 L6-8)。
   - **D-3 (vii)**: `structured_operations.upsert` の一文への**同ラベル補筆**である (§3 D-3 (vii))。`row_addressability` を `enabled` で提供する実装に対しては**現状と完全に同義**であり義務は 1 つも減らない。`row_addressability: unavailable` の実装に対して「mutation_class を宣言していないことを理由に update を禁じる」読みを閉じるだけであり、**MitateDB の出荷済み `update` の適合性を遡って変えない** (フェーズ5 D-2 の additive 根拠と同型)。
   - **閉じた封筒 (`additionalProperties: false`) に property を足すことについて**: `CapabilityDocument` も `EntityDescriptor` も閉じた封筒であり、1.5.0 の schema で厳格に検証するクライアントは 1.6.0 応答を拒否しうる。`versioning.compatibility` が additive を許すので適合であり、かつ**前例がある** — 1.3.0 が `must_rotate` を閉じた schema に足したのと**同型**である。
   - **削除 0 / 型変更 0 / 狭化 0** を 1.5.0 との再帰 diff で機械確認する (WP-1 完了条件)。**enum は追加のみであることを含めて確認する。**
   - **description 文字列の内部から義務が消えたことは再帰 diff で検出できない (v1.3、G4)**。再帰 diff は JSON 構造の差分であり、1 つの description 文字列の**中**で義務が 2 個から 1 個へ減っても「値が変わった」としか出ない。D-3 (vii) は現に**2 義務を運ぶ 1 文**を書き換えるので、**補筆の前後の文を確定文ファイルから逐語で文字列ピンし、`upsert` 節が運ぶ義務の個数が 1.5.0 と同数 (2) であることを WP-1 の完了条件として目視で突合する**。
5. **migration 番号の割当て (監督裁定 2026-09-04)**: **予約は割当ではない。** `PHASE4_DURABLE_AUDIT_SINK_V1.md:1072` と第 12 次引き継ぎが Q4 案 B のために「r2db 0008 / MitateDB 0006」と書いているのは**文書上の予約**であって、Q4 は未着手である。**先に出荷するフェーズ6 が次の空き番号を取り、Q4 はその次の番号を取る** — MitateDB の宣言型保持が DDL を要する場合 (§1.5 の 2a) は **0006**、r2db は D-1 が DDL を要さないので番号を取らない (§1.5 の 3)。**WP-4 の記録整理で `PHASE4_DURABLE_AUDIT_SINK_V1.md` §11.2 Q4 と第 12 次引き継ぎ §4-2 に日付付きの注記を置く** (フェーズ5 が `CCR_DISPOSITION` 従属判断 9 と `MITATEDB_PHASE3` R-6 に置いたのと同じ処置)。
6. **1.5.0 に留まる実装**: 1.6.0 の義務を遡及して負わない。共通テストの 1.6.0 分岐は declare-first で切る。
7. **クライアント通知**: 本設計の対象外である (依頼者が 1.4.0 で「送らない」と決定済み)。

---

## 9. WP 分割の概略 (作業指示書は別途)

| WP | 内容 | 公開面への影響 |
|---|---|---|
| **WP-0** | **衛生 (契約不変、両 peer 同時 1 コミット)**: D-4(a) `_optional_float` の fail-fast 化 (両 peer、変数名を含む `ValueError`) + D-4(b) MitateDB の契約同梱 (`pyproject.toml` に **`[tool.setuptools.package-data]` 節を新設** + `importlib.resources` + byte 同一テスト + `http.py:47` の `parents[3]` 除去 + **`docker/Dockerfile` の手動 `COPY` (:111) と注記 (:85-125) の除去**) + **D-4(c) 同型性テストの機構を対応表駆動へ一般化**し、既存 11 ヘルパを初期行として維持したうえで `_optional_float` と byte 同一テスト関数を行として追加、ソース取得方式を両 peer `ast.get_source_segment` に統一 | なし |
| **WP-1** | **契約 1.6.0 単一コミット**: spec 変更 (D-1 の description / D-2 の `surfaces` / D-3 の `json` + 既定型 + `field_types` 2 箇所 / **D-3 (vii) の `upsert` 同ラベル補筆** / `version_binding` の 1.6.0 段落) + 両 peer パッケージ内コピーのバイト同一同期 + 1.5.0 との再帰 diff 照合 (**enum は追加のみ**) + `CCR_DISPOSITION` 従属判断 11 **項目 1〜4** (a)〜(d) + 義務の条件付き性の独立段落 + 共通テスト (§6.2 の 3 種) + **port v1.10** (verbatim 規約 / **`surfaces` 由来の同居判定を追加し申告メソッドはフォールバックとして残す** / catalog fixture) + **全体 vacuity guard と「adapter が bearer を組み立ても分解もしないこと」の静的固定テスト ((a) 合成不在 + (b) split/partition 不在の 2 性質、§6.2) をともに `xfail(strict=True)` で登録** + `CONFORMANCE_ADAPTER_V1.md` §20 + **契約英文の確定文ファイル**。**peer の版数 flip は含まない。adapter の合成撤去と申告メソッドの削除も含まない (ともに WP-3)** | あり (契約公開) |
| **WP-2** | **r2db 単一 peer コミット**: locator 形 credential (in-memory / Postgres の application store + control store、issue / rotate の返却形、`_SELECT_BY_VERIFIER` の使用停止、不正形 locator の fail-closed) + `surfaces` (`service.py:916` / `control_plane.py:716` + 環境変数 2 本の起動時検査) + `field_types` (`structured.py:1130` / `postgres.py:778` の catalog、`structured.py:597` / `:1405` の create_entity 型受理、`postgres.py` の per-field DDL、**`_FIELD_TYPE_SQL` (`postgres.py:159-166`) に `json` → `_JSONB_SQL` (`:168`) の行**、**宣言 `json` を内部表現 `None` へ写す経路**) + **`contract_version` 1.6.0 flip** + **`_SELECT_BY_ID` を使う側の docstring 訂正** (§11 L6-1 の (i) — verifier UNIQUE は索引ではなく衝突不能性の構造保証として残ることを、出荷済み migration ではなくコード側に書く) + runbook (既存 credential の再発行手順、`surfaces` 環境変数) | あり (宣言拡張 + 版数宣言) |
| **WP-3** | **MitateDB 単一 peer コミット**: **あらゆる発行点の合成返却** (in-band `control_plane.py:1543` / `:1600` / `:1610` + 帯域外 store API の戻り値契約 + `ops.py:266-275` の `_print_secret_once` を合成済み bearer 1 行へ) + `surfaces` (`cell.py:1279-1345` (capability document、`control_plane` 行は `:1337`) / `control_plane.py:1366` + 環境変数 2 本の起動時検査) + **宣言型 registry** (Postgres は migration **0006**、sqlite は遅延生成、読み書き API を両 backend で統一) + **`application_catalog` の flip と `GET /v1/catalog` の実装** (`cell.py:1285` / `http.py:718-723`) + 任意キー `field_types` の受理 (`http.py:778`) + **`_CONTRACT_FIELD_TYPE_TO_MITATEDB` (`http.py:484-491`) に 7 語目 `"json": "json"` を足す** + **挙動変更 3 件**: 型無し既定 `text`→`json` (`http.py:810`) / `json`・`object`・`array` の受理範囲と**読み出し表現**を any JSON value へ (`backend_postgres.py:355-380` / `:247-250` + 逆直列化の新設) / 宣言 `boolean` の wire を **0/1 → JSON boolean** (`backend_postgres.py:100-111`、両 backend) + **`contract_version` 1.6.0 flip** + **同一コミットで撤去する 3 点**: 全体 vacuity guard の `xfail` / 合成不在テストの `xfail` と 4 adapter の合成撤去 / port の申告メソッド `control_surface_cohosted_with_data_plane()` と 4 plug の実装 + `MITATEDB_PHASE3` :22 への日付付き否定注記。**実測事項**: (i) Mitate Phase B の実 DB に宣言型 registry の行を持たない既存 field があるか・あればどう報告し読み出すか、(ii) 両 backend の `json` 受理範囲の一致、(iii) 両 backend の読み出し表現の一致、(iv) `boolean` の round-trip の一致 | あり (宣言拡張 + capability flip + 挙動変更 3 件 + 版数宣言) |
| **WP-4** | **記録整理**: 本設計 §10 の実施記録、`conformance-tests/CONDITIONS.md` (§6.3 の新条件 **C-19** + C-09 / C-11 / C-12 行の更新)、`security/CONTROL_MAPPING.md` (SI-06 / SI-07 / SI-08 / SI-10 / SI-13 / SI-14 / SI-15 の各行、両 peer の cell を対で。**SI-06 / SI-07 行の r2db 側は §11 L6-1 の (ii) 訂正先でもある**)、`r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` (**L6-1 の (ii)**: verifier UNIQUE の役割の訂正) と両 peer の runbook / 配備文書の宣言例 (新キーを含む形へ)、**`docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md` §11.2 Q4 と第 12 次引き継ぎ §4-2 への日付付き注記** (migration 番号の予約が本フェーズの出荷でずれた事実 — §8 の 5)、`spec/CCR_DISPOSITION.md` 従属判断 11 への「実施記録」追記、**引き継ぎ第 13 次** | なし |

**契約変更コミット (WP-1) は依頼者確認後に実施する** (§2 の 10)。完了条件は既存フェーズを継承する — テスト追加 + 変異注入 (scratchpad 復元、`git checkout` 不使用)、root suite 完走 (現基準 **1611** + 増分)、独立レビュー往復、commit / push / main merge (`--no-ff`) 1 セット + identity 確認。

**実装上の申し送り 4 点**: (1) **全体 vacuity guard は既存の `test_c09_every_control_surface_adapter_takes_the_provided_branch` と同形で書く** (非 parametrize の関数 1 本、adapter fixture で parametrize しない)。(2) **port からメソッドを削るのは本 port で初めてである** — 削除は **WP-3** に落ち、4 plug 側の実装も同一コミットで削る (`ABC` は不要になったメソッドを自動では消さない)。**WP-1〜WP-2 の間は申告メソッドが残り、`surfaces` を返さない peer のフォールバックとして実際に使われる** (§6.1 の 2 — `test_c09_audit_evidence.py:868` の無条件 vector を判定不能にしないため)。(3) **合成不在の静的固定テストは、規則を逐語プロトタイプで確かめてから確定する** (常設規律 5) — フェーズ5 の走査器と同じ手順であり、WP-1 の実装者は先にプロトタイプを scratchpad へ置く。**このテストは WP-1 で `xfail(strict=True)` として登録し、WP-3 で撤去する** — MitateDB が raw を返し続ける間は adapter が合成せざるを得ないためである (§3 D-1(e))。(4) **WP-3 は撤去が 3 点同時に落ちる重いコミットである** — 全体 vacuity guard / 合成不在テストと adapter 合成 / port 申告メソッドと 4 plug 実装。**どれか 1 つだけ先に落とすと、その時点で赤になるか vacuous になる**ので、分割しない。

---


**追補 (2026-09-04、監督裁定・依頼者承認)**: 作業指示書 v1.2 は **WP-1 に suite 高速化 2 件を同梱**する — (A) C-14 vector 5 (`test_c14_resource_bounds_published_and_enforced`) の位置算術を構成値に比例しない形へ作り替える (フェーズ5 L5-7 の閉止)、(B) conformance を adapter 単位の `xdist_group` で並列化し完了ゲートを `-n 5 --dist loadgroup` にする (監督実験 2026-09-04: 422 passed in 117.17s、従来 373s)。いずれも契約不変・製品不変であり、本設計の D-1〜D-5 に影響しない。ローカル PostgreSQL の `max_connections` は 100 → 300 に変更済み (開発機の設定)。

## 10. 実施記録 (WP-4 記録整理、2026-09-04)

**本節の完成度**: WP-0〜WP-3 は完了しており、各 WP について**実装記録・レビュー往復の閉じ方・変異注入の結果・受理境界 (この WP で「固定しない」と決めた点)** を書いた。残るプレースホルダは **WP-3 / WP-4 のコミットハッシュ (``1b87b38`` / `(本記録コミット。ハッシュは次回引き継ぎ §1 に記載)`) だけ**であり、これは監督がコミット後に埋める欄である — **本文中の事実に未確定は無い**。構成はフェーズ5 設計 §10 を踏襲する。

### 10.1 集計行

**集計行の出所**: 下表の集計行は、**監督が完了ゲートで単独実行して得た実測値**である (`scratchpad/wp0-160-gate.log` / `wp1-160-gate2.log` / `wp2-160-gate3.log` / `wp3-160-gate2.log` の末尾行。各 WP のコミットメッセージ末尾の `Root suite alone:` 行にも転記してあり `git log` で照合できる)。**本節の起草者はテストを実行していない** — レビュー・監査・変異の各ログからの引用である。

| WP | 内容 | 実装コミット | merge コミット | root suite (単独実行) |
|---|---|---|---|---|
| **WP-0(docs)** | 設計 v1.4 + 作業指示書 v1.1 | `488e8d3` | `62e3099` | 文書のみ (基準 **1611 passed / 0 failed / 0 skipped / 0 xfailed**) |
| **WP-0** | 衛生 (D-4) | `18bd0a0` | `c1c5c7c` | **1626 passed / 0 failed / 0 skipped / 0 xfailed** (497.46s、逐次) |
| **WP-1** | 契約 1.6.0 公開 + port v1.10 + C-19 + 追補 A/B | `bb86a37` | `99276a8` | **1675 passed / 0 / 0 / 2 xfailed** (132.38s、`-n 5 --dist loadgroup`) |
| **WP-2** | r2db の 1.6.0 出荷 | `36e6d35` | `1bc7b36` | **1757 passed / 0 / 0 / 2 xfailed** (180.18s) |
| **WP-3** | MitateDB の 1.6.0 出荷 | ``1b87b38`` | ``fcbbf2a`` | **1800 passed / 0 / 0 / 0** (142.82s) |
| **WP-4** | 記録整理 | `(本記録コミット。ハッシュは次回引き継ぎ §1 に記載)` | `(本記録の merge。ハッシュは次回引き継ぎ §1 に記載)` | 文書のみ (**1800** のまま) |

**ディレクトリ別内訳 (収集件数)**:

| WP | `r2db-api/tests` | `MitateDB-api/tests` | `conformance-tests` | 計 |
|---|---|---|---|---|
| 基準 (フェーズ5 末) | 701 | 488 | 422 | **1611** |
| WP-0 | 708 | 496 | 422 | **1626** |
| WP-1 | 708 | 496 | 473 | **1677** (= 1675 + 2 xfailed) |
| WP-2 | **790** | 496 | 473 | **1759** (= 1757 + 2 xfailed) |
| WP-3 | 790 | **535** | **475** | **1800** |

**増減の内訳**:

- **WP-0 = +15**: r2db +7 (fail-fast 5 parametrize + 既定値経路 1 + 対応表 pin 1)、MitateDB +8 (同 5 + 1 + byte 同一 1 + pin 1)。conformance 不変。受け入れ監査が新規収集 id を全数列挙して `1611 + 15 = 1626` を確認した。
- **WP-1 = +51 (すべて conformance)**: 新規ファイル `test_c19_client_self_sufficiency.py` と `test_contract.py` の新規 1 本、および差し戻しで足した検査。**peer suite の収集は 1 件も動いていない** (契約コピー 2 本以外に peer `src/` の差分が無いことを監査が確認)。第 1 ラウンドのゲートは `1671 passed, 2 xfailed`、差し戻し後が `1675 passed, 2 xfailed` (+4)。
- **WP-2 = +82 (すべて r2db)**: 第 1 ラウンドで +51 (`test_surfaces_env.py` 新設 19 を含む)、差し戻し後にさらに +31 (NUL locator / 非文字列 `field_types` / 合成の置き場所 / 相互排他検査などの新設テスト)。conformance の収集件数は**発注どおり不変**であり、増えたのは観測 (r2db 2 plug で 1.6.0 分岐に入る) だけである。
- **WP-3 = +41**: MitateDB +39、conformance +2 (`test_c09_audit_evidence.py` の `surfaces_cohosted` 単体テストほか)、r2db ±0。第 1 ラウンドのゲートは `1777 passed`、差し戻し最終ラウンドで `1800 passed`。

**`xfailed` の推移**: WP-0 で 0、**WP-1 で 2** (全体 vacuity guard `test_c19_every_control_surface_adapter_declares_1_6_0` と静的固定テスト `test_c19_adapters_never_compose_or_decompose_the_bearer_secret`)、WP-2 で 2 のまま (r2db だけでは 4 plug 全数にならないため)、**WP-3 で 0** — 2 本とも最後の flip と同一差分で `xfail` デコレータ行だけを削除した。**フェーズ6 は xfail を 1 本も残していない。**

**suite 高速化の実測 (WP-1 追補 A / B)**: 完了ゲートは **8 分 17 秒 (WP-0、逐次) → 2 分 22 秒 (WP-3、`-n 5 --dist loadgroup`)** になった。内訳は 2 つである。**(A)** C-14 vector 5 を `isolated_control_surface()` の上に作り替え、`sleep(61)` を撤去した — 監督の並列実験ログ (`scratchpad/xdist-experiment.log`) では当該 vector が 4 plug で **61.01〜63.88 秒/plug** を占めていたのに対し、作り替え後は最遅 plug が **1.53 秒**であり 4 plug 合計でも約 6 秒である (フェーズ5 の参考実測 248.68 秒に対する上界の更新でもある)。**(B)** conformance を adapter 単位の `xdist_group` で並列化した — 逐次 `466 passed, 2 xfailed in 386.67s` と並列 `466 passed, 2 xfailed in 129.42s` が**同一の集計行**であること、`1 adapter = 1 worker` (`registry-guards` を含めて 5 worker)、残骸 DB / role が 0 件であることを実測済みである。ローカル PostgreSQL の `max_connections` は **100 → 300** に変更した (開発機の設定。並列 5 worker × adapter ごとの pool を吸収するため)。

**速度規律 (本フェーズで確立し、以降も継続する 5 項目)**: (1) **完了ゲートは監督が単独実行し、その集計行だけを正本にする** (subagent の報告値は突合対象であって正本ではない)。(2) **subagent には suite 全体を回させず、対象ファイル・対象テストの前景直列実行に限る** (`timeout` 600000 明示)。(3) **レビュー・監査は `--collect-only -q` と静的照合を主とし、変異は自作分のみ最小回数**にする。(4) **時間を食う vector は「構成値に比例しない形」へ作り替える** — 比例したままだと変異注入が実用外になる (フェーズ5 L5-7 がその実例)。(5) **並列化は集計行が逐次と一致することを実測してから採る。**

### 10.2 WP-0 — 衛生 (D-4、契約不変、両 peer 同時 1 コミット。`18bd0a0` → merge `c1c5c7c`)

**実際に採った形** (発注時の予定と食い違った点は**実装が正**として記す):

- **D-4(a) flush 間隔の fail-fast**: 両 peer の `_optional_float` が、空でない値について `float()` の失敗と `math.isfinite(value) and value > 0` の両方を検査し、**変数名を含む `ValueError`** を `build_app` の実経路で送出する。`0` / `-1` / `nan` / `inf` / `not-a-number` の **5 形が個別ケース**であり、既定値経路 (不在 `{}` と空文字 `""`) の非後退テストを別に置いた。**`_optional_int` と `audit_dispatch.py` は 1 行も触っていない** (L6-4 のとおり据え置き)。
- **D-4(b) MitateDB の契約同梱**: `pyproject.toml` に **`[tool.setuptools.package-data]` 節を新設**し、`mitatedb_api/contract/data-service-api.v1.json` を `importlib.resources` で読む形にした。byte 同一テストは r2db の双子として `MitateDB-api/tests/test_http.py` に置き、`parents[2]` の深さが一致することを利用している。`docker/Dockerfile` の手動 `COPY spec/...` と `.parents[3]` 算術の注記を削除し、`cloud-run-cloud-sql.md` を packaged copy 形へ書き換えた。
- **発注を超えた点 (監督裁定 (i)、peer 対称)**: `parents[3]` の除去は MitateDB `http.py` だけでなく **`control_http.py` (`_SCHEMAS` を `.http` から import する形へ) と r2db 側のリポジトリ相対フォールバック**にも及んだ。`grep -rn "parents\[3\]" */src` = **0 行**であり、**両 peer とも packaged copy のみを読む**。
- **D-4(c) 同型性テストの一般化 (監督裁定 (ii))**: 機構を **(相対パス, シンボル名) の対応表駆動**へ改め、既存 11 ヘルパに 4 行 (`main.py::_optional_float` / byte 同一テスト関数 / `_isomorphic_symbol_source` / 対応表 pin テスト自身) を足して **15 行**とした。ソース取得は両 peer とも `ast.get_source_segment` に統一し (`inspect.getsource` はコードとして 0 件)、正規化は行頭インデントを保存する。対応表は**タプル全内容を逐語 assert する pin テスト**で固定した。**L5-6 は閉止**、**L5-5 は部分閉止** (兄弟 peer に対応物が無いヘルパは表に載せない = 表が対象の全数定義)。

**レビューと差し戻し**: 独立レビューの指摘 **7 件 (中 3 / 小 4)**、差し戻し **1 回**。中-1 (削除した `COPY` を指す注記の残存) と小-1 / 小-2 / 小-4 は閉じた。**中-2 (機構が自分自身を固定していない)** は 15 行化で部分的に閉じ、**中-3 (デコレータ差が両側とも見えない)** は「記載のみで可」の裁定を受けて **L6-11** として台帳化した (受け入れ監査は「リポジトリ内の記録としては未達」と判定しており、本 WP-4 の §11 でその宿題を閉じている)。**小-3 (作業指示書 WP-0 のテストコマンドが存在しないファイル `r2db-api/tests/test_main.py` を指す)** は指示書側の誤りであり、本 WP-4 で訂正註を置いた (L6-18)。

**受け入れ監査**: 完了条件 **11/11** と監督裁定 (i)(ii)(iii) の**すべてを充足**と判定。対応表 15 行 × 両 peer = 30 箇所を AST で解決し、**全 30 箇所が実在シンボルを指す** (空振りでない) ことと正規化後の左右一致を確認した。秘密・実データ・実ドメインの混入なし。

**変異注入の結果**: 変異 1 (fail-fast の巻き戻し) = **赤** (r2db 5 ケース)、2 (既定値経路の欠落) = **赤**、3 (packaged copy の 1 バイト改変) = **赤** (当該 peer の byte 同一テストのみ、2 本の独立性を実測)、4 (packaged copy の退避) = **収集エラー** (loader が packaged copy を実読している実測)、4′ (対照: `spec/` の退避) = byte 同一テストのみ赤で他 46 本は緑 (`parents[3]` 結合の消滅の実測)、5 (package-data 行の脱落) = ホイールに `contract/*.json` が入らないことを `pip wheel` で確認、6 (対応表 1 行削除) = **pin テストのみ赤** (同型性テスト本体は緑 = pin が唯一の検出手段であることの実測)、7 (同型性の片側崩し) = **両 peer 赤**。

**受理境界 (この WP で「固定しない」と決めた点)**:

- **同型性機構は自分自身を完全には固定できない**。対応表の駆動関数とその入れ子 `_normalize` は peer 名リテラルを持つため原理的に表へ載らず、**片側 `_normalize` の弱化は不可視**である。15 行化はレビュー変異 B (片側の byte 同一 assert の弱化) を両 peer 赤にする程度には効いているが、「自己固定した」と書くと実際より強い保証に読める。
- **デコレータ差は両側とも見えない (L6-11)**。`ast.get_source_segment` への統一で L5-6 の「取得方式差によるぶれ」は閉じたが、片 peer だけにデコレータが付く変化は検出できない (`@pytest.mark.skip` は完了ゲートの `skipped 0` が拾うが、skip しないデコレータは何も拾わない)。
- **変異 5 だけが生ログでない** (監督裁定により再実施不要とした書き起こし)。ただし完了条件 6 (package-data の存在) 自体は監査が `pyproject.toml` で直接確認しており、条件の充足判定は当該変異ログに依存しない。**変異 1 / 2 / 6 の 15 行版での再実測は片 peer に閉じている** — 対応表が両 peer で同一内容であることを AST で確認済みのため実害は低いと判定した。
- **変異 4 は「byte 同一 assert の load-bearing」を測っていない** (import 時ロードのためファイル全体が落ちる)。その分は変異 3 が担う。

### 10.3 WP-1 — 契約 1.6.0 の公開 + port v1.10 + C-19 + 追補 A/B (`bb86a37` → merge `99276a8`)

**実際に採った形**:

- **契約**: `contract_version` 1.6.0。**項目 1 (D-1)** を `security.schemes.*` 2 箇所と `CredentialIssued.secret` / `CredentialRotated.secret` の description に、**項目 2 (D-2)** を `CapabilityDocument.properties.surfaces` に、**項目 3 (D-3)** を `EntityDescriptor.field_types` / `SchemaOperationRequest.field_types` と `field_type` enum の 7 語目 `json` に、**項目 4** を `structured_operations.upsert` の同ラベル補筆として置き、`versioning.version_binding` に 1.6.0 段落を、遡及否認の既存 4 行それぞれに `1.6.0-only` を足した。書式は既存前例と同型 (`unconditional -- versioning.version_binding` / `conditional on <capability> being provided`)。`spec/CCR_DISPOSITION.md` に**従属判断 11** (項目 1〜4、(a)〜(d) + 義務の条件付き性の独立段落)。
- **確定文の逐語性**: `scratchpad/phase6-contract-prose.md` (依頼者確定済み) から複製し、**5 ブロック・9 箇所**について監督・レビュー・監査が**それぞれ独立の正規化器**で照合して全件一致を得た。文字列ピン `test_contract_pins_the_requester_finalized_1_6_0_prose` を新設した。
- **additive 性の機械確認**: 1.5.0 との再帰 diff で **削除 0 / 型変更 0 / 狭化 0**、**追加 6** (新規キー 5 + enum 追加 1)、**変更スカラー 5**。**列挙外の差分 0 件**。`required` / `additionalProperties` の変更は 1 件も無い (`surfaces.*` の nested `required: ["base_url"]` は新規部分木の内側であって退行ではない)。3 者 (`spec/` + 両 peer の packaged copy) の sha256 が同一。
- **port v1.10**: 抽象メソッドは発注の 2 本 (`create_entity_with_declared_types` / `add_field_with_declared_type`) に**追補 A の `isolated_control_surface` を加えた 3 本**になった。同居判定は **module-level の自由関数 `surfaces_cohosted(document, *, fallback)`** として置き、`surfaces` 不在時は申告メソッドへフォールバックする (申告メソッドの削除は WP-3)。credential handle には **verbatim 規約** (合成しない・分割しない) を docstring として置いた。`CONFORMANCE_ADAPTER_V1.md` §20 は §19 と同構成で、「**メソッドを削除する初めての port 改訂であり、それを 1 つでなく 2 つの WP に跨って行う**」ことを明記している。
- **新条件 C-19**: credential verbatim (4 plug)、`surfaces` の 2 文書一致 (4 plug) と declare-and-echo (HTTP plug のみ)、`field_types` の宣言 / 既定 / 値 round-trip (4 plug)、否定側は**契約 enum から導いた `json` を除く 6 語 × 4 plug = 24 件**である。すべて `contract_version >= 1.6.0` の declare-first 分岐であり、本 WP 時点ではどの peer も 1.6.0 を宣言していない。
- **`xfail(strict=True)` 2 本を先置き**: 全体 vacuity guard と、adapter が bearer を**合成も分解もしない**ことの静的固定テスト。後者は逐語プロトタイプ (`scratchpad/wp1y/static_proto.py`) を先に置いてから確定した (常設規律 5)。

**レビューと差し戻し**: 独立レビューの指摘 **10 件 (中 6 / 低 3 / nit 1)**、差し戻し **1 回**。レビューは**報告に無い変異 3 種 (α / β / γ) を自作**し、いずれも「検出されない」ことを実測して指摘の根拠にした。主な閉じ方:

- **F1** — 「項目 4 を 1.6.0 段落へ置いていない」の検査が**テスト自身のリテラル定数**を見ていた → 契約現物 (`version_binding` の実文字列) を見る形へ。
- **F2 (変異 α)** — `surfaces` の**構造**が一切ピンされていなかった (nested `required: ["base_url"]` を spec と両コピーから同時に落としても `52 passed`) → 構造 assert を追加。
- **F3** — 合成箇所は 4 ではなく **5** (追補 A の `isolated_control_surface` が 5 番目を新設していた) → `xfail` reason と §20 の記述を 5 件へ訂正。
- **F4** — 追補 A-2 の変異 A′ が字義どおり成立しない (`limit_class` は C-14 に元から 1 件も無い) → **C-14 に `limit_class` の assert を足して**から literal A′ を再実測し、赤を得た。
- **F5** — in-process MitateDB plug の `create_entity_with_declared_types` が `fields` 引数を捨てていた → 他 3 plug と同じ意味論へ。
- **F6** — `json` 値 round-trip の比較が `==` で、Python の `1 == True` / `3 == 3.0` を通していた (WP-3 (γ) が是正しようとしている欠陥をちょうど見逃す比較) → 型込みの比較へ。
- **F7 / F8 / F9 / F10 (低・nit)** — 分解検出が**受け手の変数名依存**である限界の開示 (C-19 の限界 (e))、否定側 6 語が契約語彙 − `json` と**ちょうど一致する**ことの assert、`isolated_control_surface` の close 規律が観測されていないこと (**L6-13**)、簡体字 1 字ほか。

**受け入れ監査**: 完了条件 **20 項目 + 追補 A-1〜A-3 / B-1〜B-3** を判定し、差し戻し後に**全項目を充足**と判定した (監査自身の再帰 diff・逐語照合器・`cmp` / sha256・AST 再現・収集数突合による)。

**変異注入の結果**: X (契約側) 1 / 2 / 3 / 4 / 4b、Y (conformance 側) 5 / 6 / 7 / 7′ / 8 / 9 / 10 / A / A′、および監督実施の literal A′ が**すべて発注どおりの赤 (または「XPASS へ移らない」対照)** になった。特筆は **7 と 7′ の対比** — 合成 5 箇所を撤去すると `XPASS(strict)` で赤、撤去したうえで `credential_ref` を bearer の `split(".")` で得る形にすると **xfail のまま = 分解不在 (b) が単独で load-bearing** であることの実測である。

**受理境界**:

- **declare-and-echo は「宣言 URL への実ダイヤル」ではない (L6-12)**。4 plug とも `*.conformance.invalid` の合成 base_url を申告し、HTTP plug も `httpx.ASGITransport` で実ソケットを持たない。検証しているのは**同一 adapter への 2 回呼びの自己整合**である。
- **declare-and-echo vector は 4 件収集され、in-process 2 plug は本文内 early-return で戻る**。発注は「HTTP plug 2 件に限定」だったが、実装は id 形を他 vector と揃えるために収集レベルでは絞らなかった。**この 2 件は WP-3 以後も恒久的に無 assert のまま緑**である。
- **変異 8 の赤は 4 plug ではなく 1 plug**である。当該 vector は `form == "provided"` の枝でのみ同居判定に到達し、その枝へ入る plug が 1 つしかないためで、**発注の対応表の「4 plug で赤」は誤り**である (L6-18)。
- **本 WP には「この WP が新しく生んだ値に緑が依存する vector」が 1 本も無い** — declare-first の設計どおりであり、C-19 の全 vector は WP-2 / WP-3 の flip まで vacuous である。この事実は `CONDITIONS.md` の C-19 行に開示した。
- **`CCR_DISPOSITION.md` に D-4 (衛生) の却下案は書かない**。同ファイルは**契約変更の従属判断**を記録する場所であり、契約に触れない衛生決定の却下案は射程外である — 発注文の「(d) D-4 却下 2 件」は項目 4 (D-3 (vii)) の却下と取り違えた誤りとして訂正した (L6-18)。
- **C-14 の `limit_class` assert は soft-assert である** (値が `None` のときは何も要求しない)。C-16 の同型の検査と同じ形であり、`limit_class` は契約が保証する項目ではないためだが、**「宣言しない peer に対しては空振りする」**性質は残る (L6-19)。

### 10.4 WP-2 — r2db の 1.6.0 出荷 (`36e6d35` → merge `1bc7b36`)

**実際に採った形**:

- **D-1 (locator 形 credential)**: **すべての発行点** (in-band issue / rotate、bootstrap、reset、audit ceremony、ops CLI、conformance adapter が使う store 層の add / rotate) が `<credential_id>.<secret_part>` を **`secret` として返し**、`credential_id` は別フィールドとして残る。**すべての認証点** (in-memory / Postgres の application store、control store、`authenticate_application`) が locator を分割し、**credential_id で行を引いてから `compare_digest` を state 検査より先に**行う。`_SELECT_BY_VERIFIER` は定数ごと削除し、`verifier` 列と `UNIQUE` は**衝突不能性の構造保証**として存置した (DDL 無変更 = migration 番号を取らない)。不正形 locator (ドット無し / 片側空 / **NUL バイト**) は DB に触れずに `AUTH_INVALID` で fail closed。未知・不一致・不正形は**同一応答** (SI-10) で、未知 id でも**ダミー verifier に対して `compare_digest` を実行**する (タイミングオラクルの除去)。否認は不帰属 (B-1 / SI-14) のまま耐久記録される。**互換シムは置かず、既存 credential は再発行**する (runbook §12a)。
- **D-2 (surfaces)**: `R2DB_DATA_BASE_URL` / `R2DB_CONTROL_BASE_URL` を**配備者の表明**として両 capability 文書へ逐語 echo する (リクエスト host から導出しない / プロセス間で相互検証しない)。相対 URL・誤終端・末尾スラッシュ・不在・**相互に取り違えた終端**を起動時に拒否する。
- **D-3 (typed catalog)**: catalog が全 field について `field_types` を返し (in-memory / Postgres とも `fields` を走査キーにするので総覧性が構造的に成り立つ)、型無し field は `json`、`create_entity` は任意の部分 `field_types` を受け、`add_field` は `json` を受ける。非文字列・語彙外・`fields` に無い名前は `VALIDATION_FAILED`。宣言 `json` は JSONB へ写り、`object` / `array` は `json` へ丸められない。**1.5.0 のリクエストはそのまま有効**である。
- **flip**: `service.py` / `control_plane.py` の 2 箇所が同一差分で 1.6.0 を宣言し、C-19 の各 vector が **r2db 2 plug で初めて実行される**。

**レビューと差し戻し**: 独立レビューの指摘 **2 件 (重大 1 / 中 1) + 観測 5 件**、差し戻し **1 回** (監督裁定 8 項目)。

- **F1 (重大、実バグ)** — **locator の credential_id 半分に NUL があると 401 が 503 へ反転し、その否認が耐久監査に 1 行も残らない**。クライアント由来のバイトがそのまま SQL パラメータへ渡り、psycopg の拒否が `AUTH_STATE_UNAVAILABLE` へ写り、当該コードが `_DURABLE_DENIAL_CODES` に無いため早期 return するためである。**WP-2 以前はバインドされる値が常に 64 hex 桁の verifier だったので、この経路自体が存在しなかった** — locator 形にしたことが新しく開いた穴である。実測 (実 PG + 実 HTTP): 通常の不正 credential 2 回で耐久行 +2、NUL locator 2 回で **+0**。**閉じ方**: `split_bearer_locator` がどちらの半分の NUL でも `None` を返す (lookup 前に fail closed)。監査が同じ probe を独立に再走させ **`(+0)` → `(+2)`** を実測、`AUTH_STATE_UNAVAILABLE` は 1 度も現れないことを確認した。
- **F2 (中)** — `field_types` の値が JSON 配列 / オブジェクトだと `VALIDATION_FAILED` ではなく **503** になる (`in FIELD_TYPES` が unhashable で `TypeError`)。**閉じ方**: `isinstance(str)` ガードを **`add_field` のスカラ `field_type` 側 (WP-2 以前からの同型の穴) と同一修正で**閉じ、実 HTTP のテストを足した。
- **観測 O1〜O5** — O2 (`compose_bearer_locator` が `.` を検査しない) と O4 (data / control の終端取り違えを通す) は裁定 7(ii)(iii) で閉じた。O1 (adapter 側の合成) は**裁定 3** で閉じた — 合成を store / service 層へ移し、`grep -rn compose_bearer_locator r2db-api/conformance/` = **0 件**にした。O3 (credential_id 存在のタイミングオラクル) は裁定 7(i) の**ダミー verifier**で閉じた。

**受け入れ監査**: 1 回目は完了条件 22 項目のうち **充足 20 / 証拠不足 1 / 設計疑義 2**、差し戻し後の 2 回目を経て**監督は 22/22 を充足と判定した** (コミットメッセージ `audit 22/22 after rework`)。

**変異注入の結果**: 発注の対応表 **1〜16** に加え、差し戻し裁定 8 項目に対する変異 (NUL 検査の除去 / `isinstance` ガードの除去 / 合成の adapter への差し戻し / control 文書側の `surfaces` 破壊 / `json` 列の TEXT 化 / 終端の相互排他ガード除去 / `.` 検査の除去)、およびレビュー自作の M-α / M-β / M-γ が**すべて赤**になった。M-β (capability 文書の `surfaces.data.base_url` をリクエスト host から組み立てる) が実 HTTP を通る 2 本だけを赤にしたこと、M-γ (Postgres の per-field DDL 無視) が `information_schema` を直接読むテストを赤にしたことは、それぞれ**空振りしていないことの実測**である。

**受理境界**:

- **発注どおりでない変異が 1 件ある**。条件 11 (`surfaces` の 2 文書) の変異 8 は「control 文書から `surfaces` を落とす」ものだったが、実施されたのは adapter の `_SURFACES` を落とす操作 (= 変異 16 と同一実験) だった。差し戻し後に**製品コード `control_plane.py` 側を壊す変異**を別途実施し、実 ASGI の 2 アプリを突き合わせるテストで赤を得ている。
- **`json` 内部写像の Postgres 側は独立には固定されていない**。宣言 `json` → 内部 `None` の写像を壊しても、`_FIELD_TYPE_SQL["json"]` と `_column_type_sql` の既定がともに JSONB を返すため PG 側は緑のままである (防御多重化の裏返し)。代替変異 (`field_type is None` 分岐を TEXT へ) が「明示 `json` 列が JSONB であること」を実際に固定している。
- **タイミング安全化の pin が空振りしている**。実装は 4 つの `authenticate` すべてで無条件に `compare_digest` を実行しているが、それを固定するテストは `source.count("_DUMMY_VERIFIER") >= 2` であり、**使用箇所 2 つを短絡形へ戻しても定義行・コメント行だけで閾値を満たす** (監査がスクラッチ上の文字列置換で実測)。実装は正しく、**固定だけが弱い**。
- **ops CLI の rotate 2 経路は自分で合成している**。4 つの `rotate` が `-> None` で合成済み bearer を返さないためであり、「発行点は store / service 層」という原則の**射程内の逸脱**である。挙動面の害は現時点で無い (印字された secret がそのまま認証を通ることを CLI テストが実測)。
- **`CONTROL_PLANE_COMPROMISE_PLAYBOOK.md` は wire 形を一度も書いていない**ため掃討対象ではなかったが、再発行手順への参照 2 箇所を足した (裁定 6)。

### 10.5 WP-3 — MitateDB の 1.6.0 出荷 (``1b87b38`` → merge ``fcbbf2a``)

**実際に採った形**:

- **D-1**: **発行点 9 箇所すべてが store / service 層で合成**する (in-process の issue / rotate、control 側の同 2 経路、Postgres の application / control 各 store、in-band issue と rotate 2 経路)。`ops.py` は返却値を verbatim print、HTTP 境界と adapter の合成は**撤去**した。**受理側は 4 store とも完全 bearer を受ける形へ統一**し (`authenticate(secret)`)、分割は各境界で 1 回だけ行われる。`credential_wire.py` を新設して `compose_bearer_locator` / `split_bearer_locator` を置き、**NUL を含む locator は不正形**として lookup 前に落とす (r2db WP-2 の F1 と同型)。不正形 bearer も未知 id と同じく `authentication_denied` として耐久記録し、申告文字列は coalescing key に入れない。未知 id でもダミー digest に `compare_digest` する。
- **D-2**: `surfaces.py` を新設し、data / control の両文書が同一の `surfaces` を返す。**`control_plane` が `unavailable` の配備では `surfaces.control` を出さない** (r2db と同型)。`MITATEDB_DATA_BASE_URL` / `MITATEDB_CONTROL_BASE_URL` の 4 形を起動時に拒否する。
- **D-3**: **宣言型 registry `_mdb_field_types`** を application データベースに置いた — 新規 provisioning は `0003_provision_application.sql` の改訂 (テンプレート) が作り、**既存 DB には per-application の upgrade script `0006_declared_field_types_upgrade.sql`** が当たる。契約 7 語 ↔ foundation 内部語彙の対応は `field_types.py` の**1 箇所の表**に固定し、値検証を `cell` 層の choke point (`check_declared_value`) へ引き上げた (backend 非依存 = sqlite backed の in-process plug でも効く)。`application_catalog` を `enabled` へ flip し `GET /v1/catalog` を実装、`EntityDescriptor` は `entity` / `fields` / `field_types` の **3 キーのみ**を返す (`row_addressability: unavailable` なので `mutation_class` 等は省略)。**挙動変更 3 件** — (α) 型無し既定 `text` → `json`、(β) `json` / `object` / `array` の受理範囲と読み出し表現を any JSON 値へ、(γ) 宣言 `boolean` の wire を 0/1 → JSON boolean — はすべて flip と同一差分に入れた。
- **撤去 3 点 (同一差分)**: 全体 vacuity guard の `xfail`、静的固定テストの `xfail` と 4 adapter の合成、port の申告メソッド `control_surface_cohosted_with_data_plane()` と 4 plug の実装・フォールバック分岐。**`grep -rn "control_surface_cohosted_with_data_plane"` = 0 行**であり、同居判定は `surfaces` 由来の `surfaces_cohosted()` だけになった。`MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md` :22 には**原文を残したまま日付付きの否定注記**を添えた。
- **監督追補 (A〜G)**: 合成の置き場所、不正形 bearer の監査、C-15 の bogus vector を port の新 primitive `tampered_bearer()` へ、最終ステップ (撤去 3 点)、未実施変異の全数実施、同型性表の拡張、配備文書。

**レビューと差し戻し**: 独立レビューの指摘 **12 件 (重大 1 / 中 6 / 中〜低 2 / 低 3)**、差し戻し **1 回 + 最終ラウンド 1 回**。レビューは**自作変異 R1 / R2 / R3** で「検出されない」ことを実測した。主な閉じ方:

- **F1 (重大、実バグ)** — 同一 duck-type interface の 2 実装が `secret` の形を取り違えていた (in-process store は合成済み bearer を受け、Postgres store は生の secret 部を受ける)。**この組み合わせでは認証が 100% 失敗する**。**閉じ方 (監督裁定 1)**: レビューの提案 (in-process 側を raw へ戻す) ではなく**逆向き** — **4 store すべてを完全 bearer 受けへ統一**し、分割の choke point を store 内 1 箇所にした。peer 対称性はこの形の方が高い。
- **F2 / F3 (中)** — 静的固定テストの合成側が**変数名依存**で、`_COMPOSITION_ALLOWLIST` の 4 行は**1 件も抑止していなかった** (行番号 2 件も陳腐化)。**閉じ方 (最終ラウンド)**: 走査を受け手名に依存しない形へ広げ、実測で裏を取った — **allowlist を空にすると 4 plug で 4 件の finding が出る** (= 実効している)、**`token = handle.secret; return f"{...}.{token}"` 形の注入で赤になる** (= 名前依存が消えた)。
- **F4 (中)** — `split_bearer_locator` の NUL 検査が 1 本も pin されていなかった (検査を外しても関連 suite が全緑)。**閉じ方**: 単体 11 本 + 実 PG 経路 1 本を新設。
- **F5 / F6 (中)** — `MITATEDB_CONTROL_BASE_URL` の否定側テストが皆無だった / `control_plane: unavailable` でも `surfaces.control` が出ていた (契約違反かつ r2db との非対称)。**閉じ方**: `test_config.py` を 19 件へ拡張し、`unavailable` では採用しない形へ。
- **F9 (中〜低)** — `0006` 未適用の application DB で**全 read/write** がクライアント過失コード `VALIDATION_FAILED` で落ちる。**閉じ方**: `UndefinedTable` を個別に捕捉して `StorageConfigurationError` (SERVICE 系) へ。
- **F7 / F8 (中)** — backfill 規則の逸脱と `_check_domain` の 4 語畳み込みは**実装変更ではなく報告**として上げ、監督裁定で**実装どおりを正**とした (下記 受理境界、L6-16 / L6-14)。
- **F11 / F12 (低)** — 陳腐化した docstring 2 件、および `CONDITIONS.md` C-09 行と `security/CONTROL_MAPPING.md` の**現在形の誤記** (申告メソッドを現存として列挙、L5-4 を未閉止として記述)。**閉じ方 (裁定 7)**: 両ファイルを WP-3 の同一差分で訂正した (WP-4 の予定から前倒し)。
- **実バグ 2 件目** — `reset_control_credentials` が `issue()` の返り値を捨てて**生成前の raw secret をそのまま返していた**ため、`bootstrap` は合成済みを返すのに `reset` の CLI / HTTP 呼び出し側だけ raw を受け取っていた (「in-band と帯域外の混在」そのもの)。返り値を受け取る 1 行で閉じた。
- **実バグ 3 件目** — in-process adapter の control credential **生存確認**が bearer を分割してから `authenticate` へ渡していたため、確認が必ず失敗し、**呼ばれるたびに control credential を reset していた** (誤 reset)。裁定 1 の完全 bearer 受け統一と、adapter が分割をやめたことで消えた。

**受け入れ監査**: 1 回目は完了条件 **26 項目**を判定し、**充足 22 / 一部未充足・未充足 3 / 証拠不足 1**。指摘は (A) backfill 規則、(B) in-process plug が `split_bearer_locator` で 2 箇所分解している (静的走査はヘルパ経由を見ない)、(C) `_COMPOSITION_ALLOWLIST` の空振り、(D) 同型性表に `surfaces` 検証ヘルパが載っていない、(E) `CONDITIONS.md` C-19 行が中間状態のまま、(F) **未追跡ファイル 1 件** (`MitateDB-api/tests/test_control_plane_store.py` — `git add` されないままコミットすると同型性テストが解決先不在で赤になる) である。監査は実 PostgreSQL に対して `SELECT` を実行し、**registry 19 行 (integer 7 / string 12)、行の無い既存 field は 0 件**を確認した。最終ラウンドで (B)(C)(E) は閉じ、(A)(D) は台帳項目として受理した。

**変異注入の結果**: 発注の対応表 **1〜18′** (18 行) に加え、**追補 A〜D の 4 変異**、**同型性 A / B / C の 3 変異**、および最終ラウンドの **R1 / R2 / F5 / F6 / F9 / allowlist 空**の各変異が、いずれも指定どおりの赤になった。特筆:

- **変異 5** (sqlite 側の registry 書き込みを落とす) は **sqlite 3 本だけが赤で Postgres 側は巻き込まれない** — 両 backend 分が独立に固定されていることの実測。
- **変異 14** (読み出しの逆直列化を外す) が round-trip vector を赤にした — 「**書けるだけでは緑になる**」ことの対照。
- **変異 16** (片方の plane だけ 1.5.0 へ戻す) は **data 面 (`cell.py`) を戻して**ローカル版数テストと**全体 vacuity guard の両方**を赤にした。フェーズ5 の C-09 guard は control 面の宣言のみを見ていたが、**C-19 の guard は adapter の `contract_version()` = data 面の capability 文書を読む** — 発注の対応表は「片方の plane だけ」としか書いておらず、どちらの面かで結果が変わる (L6-18)。
- **変異 17** は 1 回目 (`42 passed`) で**未検出**であり、`surfaces_cohosted` を直接固定する単体テストを新設して赤を得た。

**受理境界**:

- **`0006` の backfill は物理 TEXT 列を一律 `string` に写す (L6-16)**。作業指示書 完了条件 8 の「`object` / `array` 既存列は `json`」と「型無し既存列は `string`」は、MitateDB では `string` / `object` / `array` / `json` の 4 契約型がすべて物理 TEXT であるため**同時には満たせない自己矛盾**である。監督は実装どおり `string` を正とし、`object` / `array` として使っていた既存列は `add_field` で型付き列を足して移行する形にした (script の KNOWN LIMITATION と runbook に開示)。実 DB では対象列が 0 件であることを確認済みである。
- **store の受理形を (id, secret) から完全 bearer へ変えた**。分割の choke point を store 内 1 箇所に集約する裁定であり、結果として **in-process adapter からも分解が消えた** (`split_bearer_locator` の呼び出しは 4 adapter で 0 件、残るのは散文のみ)。
- **Postgres backend のドメイン検査は名目のみで、形状の防御は cell 層が担う (L6-14)**。値は cell 層で JSON 文字列化されてから backend へ渡るため、`json` / `object` / `array` / `string` の 4 ドメインは**名前だけが 4 つで検査は同一の `isinstance(str)`** である。設計 D-3 の「3 語を 1 ドメインに畳まない」は名目上満たされている。
- **in-process plug は in-memory sqlite、HTTP plug は `httpx.ASGITransport` であり、どちらも実ソケットを持たない (L6-12)**。「宣言された URL に実際に到達できる」ことは共通 suite の射程外である。
- **registry 参照が insert 2 回・query 3 回の往復を足し、キャッシュが無い (L6-15)**。正しさには影響しないが application-plane の遅延として記録する。
- **`surfaces` 検証ヘルパの同型性は未固定 (L6-17)**。MitateDB は `surfaces.py` の 1 モジュールへ集約したが、r2db 側は `main.py` と `control_main.py` に重複コピーを持つため、(相対パス, シンボル名) の対応表に載せられない。**r2db 無変更という WP-3 の制約と衝突した**ため保留した。対応表は 15 行 → **18 行** (bearer 合成 / 分解 / timing pin) になった。

### 10.6 WP-4 — 記録整理 (`(本記録コミット。ハッシュは次回引き継ぎ §1 に記載)`)

**状態**: 本記録コミット。**契約・製品コード・テストは 1 バイトも変更していない** — root suite は WP-3 の **1800 passed / 0 failed / 0 skipped / 0 xfailed** のままである。

**運ぶもの**: 本設計の **§10 (本節) と §11 の状態更新 + 新規台帳 L6-18〜L6-20**、作業指示書 **v1.3** (訂正註 6 件と §11 実施記録)、**`docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md` §11.2 Q4** と**第 12 次引き継ぎ §4-2** への日付付き注記 (migration 番号 — §8 の 5、L6-2)、および**引き継ぎ第 13 次** (`docs/work-orders/HANDOVER_20260904_FABLE2.md`)。

**§9 の WP-4 の予定から前倒しされた分**: `conformance-tests/CONDITIONS.md` (C-09 / C-19 行) と `security/CONTROL_MAPPING.md` (SI-00 / SI-14 行ほか) は、**WP-3 の差し戻し最終ラウンド (裁定 7 / レビュー F12) で先に更新済み**である — 両ファイルが申告メソッドの現存や L5-4 の未閉止を**現在形で断言していた**ため、WP-3 の撤去と同一コミットで訂正する必要があった。

---

## 11. 将来課題

**フェーズ6 起草時に見えている項目 (実装で確定するもの・射程外のもの)**

- **L6-1 出荷済み migration の偽になるコメントは、3 箇所で訂正する (監督裁定済み 2026-09-04)**。`r2db-api/migrations/0005_credential_store.sql` の「`verifier ... UNIQUE`: authentication is an equality lookup on this column (`PostgresCredentialStore.authenticate`), never a full scan -- `UNIQUE` is both the index that makes that lookup fast and a structural guarantee that two credentials can never collide on the same verifier」は、D-1 後に**前半が偽**になる (`0006_control_plane_http.sql:388-390` の control 側も同型)。**後半 (衝突不能性の構造保証) は残る**ので制約自体は存置する。**裁定: 出荷済み migration は in-place で触らない** (既存規律の維持 — 運用者が既に適用したファイルを書き換えない)。訂正先は次の 3 箇所である。
  - **(i) `_SELECT_BY_ID` を使う側の docstring** (`r2db-api/src/r2db_api/credential_store.py` の `PostgresCredentialStore.authenticate` 周辺) — 認証が locator 参照になったこと、`verifier` の `UNIQUE` は衝突不能性の構造保証として残ること。**WP-2 で行う。**
  - **(ii) `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` と `security/CONTROL_MAPPING.md` の該当行** (SI-06 / SI-07 の r2db 側 cell)。**WP-4 で行う。**
  - **(iii) 本項 (L6-1) 自体** — 「migration ファイルの記述は当時のものとして残り、現行の正は上記 (i)(ii) にある」ことの記録。
  - **(iv) `r2db-api/src/r2db_api/credential_store.py:265-270` (v1.3、G17。最も load-bearing)** — 逐語で「The lookup above is already an exact-equality index match on `verifier` … this `compare_digest` is deliberate defence-in-depth, **not the authoritative check**」と書く。**D-1 後はこの `compare_digest` が権威ある検査そのものになる** — §3 D-1 の実装拘束 1 (digest 比較を state 検査より先に) が依存する当の性質を、コード内のコメントが否定したまま残ってはならない。**WP-2 で訂正する。**
  - **(v) `MitateDB-api/src/mitatedb_api/backend_postgres.py:122-129` (v1.3、G2/G17)** — 逐語で「`text` covers both this foundation's own `text` AND `json` field types … nothing downstream needs to recover **which of the two** a column was originally declared as」と書く。**D-3 後は「どちらとして宣言されたか」を復元する必要がある** (受理・読み出し・catalog の 3 面、§3 D-3)。`field_domains` の情報源を registry へ切り替えるのと同一コミット (**WP-3**) で訂正する。
  - **【状態 2026-09-04 (WP-4)】** **(i) と (iv) は WP-2 で、(v) は WP-3 で閉じた** — (i) は `credential_store.py` の `PostgresCredentialStore.authenticate` の docstring が「locator 参照 / `UNIQUE` は衝突不能性の構造保証 / `compare_digest` が権威ある検査」の 3 点を書く形になり、(iv) の逐語「not the authoritative check」は追跡ソースから **0 件**になった (WP-2 監査が照合)。(v) は `backend_postgres.py` の「どちらとして宣言されたかを復元する必要がない」が registry 由来へ訂正済み (WP-3 監査が照合)。**(ii) は半分だけ済んでいる** — `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` は WP-2 が §12a (locator 形の既存 credential 再発行手順) を足して更新したが、**`security/CONTROL_MAPPING.md` の SI-06 / SI-07 の r2db cell は未了**である (本記録コミットは同ファイルに触れていない。次に同ファイルを触るときに行う)。(iii) は本項自身の記録であり、**以後も記録のまま**残す。
- **L6-2 migration 番号は「予約は割当ではない」— 先に出荷するフェーズ6 が次の空き番号を取る (監督裁定済み 2026-09-04)**。`PHASE4_DURABLE_AUDIT_SINK_V1.md:1072` と第 12 次引き継ぎ §4-2 が Q4 案 B のために「r2db 0008 / MitateDB 0006」と書いているのは**文書上の予約**であり、Q4 は未着手である。**フェーズ6 が先に出荷するので、必要なら MitateDB は 0006 を取り、Q4 はその次 (0007) を取る。** r2db は D-1 が DDL を要さないため番号を取らない (§1.5 の 3)。**MitateDB の宣言型 registry は DDL を要すると確定した (v1.2、F2)** — catalog / 読み出し / 受理の 3 面で宣言型が要り、物理 TEXT 列からは復元できないからである (§1.5 の 1b / 2a)。**それは per-application 系列の upgrade script であり、番号は `0006` である (v1.3、G12)** — platform 単発の `0006` にすると既存 application データベースに何も作らない。したがって **MitateDB は 0006 を取り、Q4 は 0007 を取る**。**WP-4 で Q4 の正本 2 文書へ日付付き注記を置く** (§8 の 5、§9 の WP-4)。
  - **【状態 2026-09-04 (WP-4)】** **閉じた。** MitateDB は per-application upgrade script **`0006_declared_field_types_upgrade.sql`** を取り (WP-3)、r2db は D-1 が DDL を要さないため番号を取らなかった (WP-2 で `git diff -- r2db-api/migrations/` が空であることを監査が照合)。**Q4 は次の空き番号 (MitateDB `0007` / r2db `0008`) を取る。** WP-4 で `PHASE4_DURABLE_AUDIT_SINK_V1.md` §11.2 Q4 と第 12 次引き継ぎ §4-2 に日付付き注記を置いた。
- **L6-3 (閉じた) r2db の既存の型無し (JSONB) 列の扱い**。v1.0 はこれを「残存する `None` は fail-closed とし、移行手順の要否を WP-2 で確定する」課題として起票していた。**裁定 R1 (2026-09-04) で閉じた** — 型語彙に `json` (any JSON value) が入り、型を宣言せずに作られた field の型は `json` であると契約が定めるため、r2db の内部表現 `None` は **catalog で `json` として正しく報告される**。fail-closed も移行手順も要らない。本項は「起票して同日に閉じた」記録として残す。
  - **【状態 2026-09-04 (WP-4)】** **閉じたまま。** WP-2 の実測が裏づけた — 内部表現 `None` は catalog で `json` として報告され、fail-closed も移行手順も要らなかった (`test_foundation.py` が `fields` のみの `create_entity` で `field_types` が全 `json` になることを固定)。**記録のまま**残す。
- **L6-4 `_optional_int` の degrade-to-default 規律は揃えていない**。D-4(a) は `_optional_float` のみを fail-fast にした。理由は「唯一の消費者が flush 間隔であり、誤設定の帰結が無音のホットループだから」であって (§3 D-4)、`_optional_int` の消費者にはその性質が無い。だが**同じ形の関数が隣り合って別々の規律を持つ**状態が残る。揃えるなら「既存配備が非数値・0・負値を渡していないこと」を先に確かめる必要がある (後方非互換になりうる) — フェーズ5 の **L5-8** (下限検査の peer 非対称) と同型の判断である。
  - **【状態 2026-09-04 (WP-4)】** **記録のまま。** 本フェーズでは触れていない — WP-0 監査が `_optional_int` と `audit_dispatch.py` が 1 行も変更されていないことを `git diff` で照合済みである。
- **L6-5 `surfaces` は配備者の表明であり、宣言された URL が実在することは declare-and-echo でしか検証していない**。conformance の in-process plug は実 URL を持たないため合成の偽ドメインを申告する (§6.4)。**「宣言された URL に本当に到達できる」ことを独立に検証できるのは HTTP plug だけ**であり、この射程を CONDITIONS.md に開示する。L5-4 (申告を独立検証できない) は port v1.10 の改訂 (削除は WP-3) で閉じるが、**その代わりに「宣言が実在を保証しない」という別種の射程が入る** — 閉じたのではなく、検証の位置が adapter の申告から配備者の宣言へ移った。
  - **【状態 2026-09-04 (WP-4)】** **WP-1 で開示済み** (`CONDITIONS.md` の C-19 行に限界 (a)〜(e))。検証の位置は adapter の申告から配備者の宣言へ移り、**L5-4 は WP-3 の申告メソッド撤去で閉じた** (`grep -rn "control_surface_cohosted_with_data_plane"` = 0 行)。「宣言が実在を保証しない」という射程は**残る** — 実ソケットを持つ HTTP plug はフェーズ7 候補である (L6-12 / L6-20)。
- **L6-5a `surfaces` の 2 プロセス間ドリフトは実装が検出できない (v1.2、F9 で起票)**。data / control は別プロセスであり、どちらも相手のホストへ接続しない (§1.5 の 7)。したがって「両文書が同じ `surfaces` を返す」という 1.6.0 義務を、**どちらのプロセスも単独では確認できない**。実装が起動時に検査できるのは自プロセスに与えられた 2 変数の**形**だけである (§3 D-2 の (a))。配備者が control プロセスにだけ古い `*_DATA_BASE_URL` を渡すと、control 文書から data へ辿ったクライアントが別配備へ行き、**実装は何も検出しない**。検出は配備後チェックと HTTP plug の declare-and-echo vector だけが担う。**これは `visibility_lag_ms` / `coalescing_window_ms` の 2 プロセス整合 (Q4、`PHASE4_DURABLE_AUDIT_SINK_V1.md` §11.2) と同族の構造**であり、**Q4 案 B (DB 側を単一の真実にする) が成立する際に `surfaces` も同じ機構へ載せる**のが手当てである。それまでは配備者責任として runbook に書く。
  - **【状態 2026-09-04 (WP-4)】** **記録のまま。** 両 peer とも「自プロセスに与えられた 2 変数の形だけを起動時に検査する」形で出荷し、リクエスト host からの導出も 2 プロセス間の相互検証も発明していないことを WP-2 / WP-3 のレビューが照合した。2 プロセス間ドリフトの検出は配備後チェックと HTTP plug の declare-and-echo だけが担う (その declare-and-echo 自体の射程は L6-12)。
- **L6-6 `field_types` は型のみを宣言し、値の制約を宣言しない**。D-3 (v) の原則 (catalog は schema operations で定義できる事実のみを返す) に従った結果であり、意図した射程である。将来 schema operations が nullability / 既定値 / 一意性以外の制約を得たとき、catalog も**同じ版で**得る — 片方だけ先行させない。この対応関係を契約文に置く (§5 の (3))。
  - **【状態 2026-09-04 (WP-4)】** **記録のまま (意図した射程)。** 両 peer とも `field_types` は型のみを返す形で出荷した。
- **L6-7 MitateDB の catalog は `mutation_class` を宣言しない**。§1.5 の 4 のとおり契約上正しい形だが、**クライアントから見ると「この entity に update できるか」を catalog からは読めない** — `capabilities().atomic_mutation.operations` から読むことになる。`row_addressability` を将来 enabled にするなら mutation_class の宣言が要り、そのとき `address_fields` をどう定めるか (MitateDB には server-assigned address が無い) が設計事項になる。
  - **【状態 2026-09-04 (WP-4)】** **記録のまま。** WP-3 の catalog は `EntityDescriptor` を `entity` / `fields` / `field_types` の 3 キーのみで返し、`mutation_class` を宣言しない (契約上正しい形) ことを受け入れ監査が照合した。
- **L6-8 (閉じた) MitateDB の既存 field の型報告**。v1.2 はこれを「宣言型 registry に行を持たない既存 field をどう報告するか未確定」として起票していた。**v1.3 で backfill 規則を決めて閉じた (G12)** — upgrade script が既存列を物理型から registry へ写すので (`text`→`string` / `integer`→`integer` / `real`→`number` / `boolean`→`boolean` / `json`→`json`、`object` と `array` は物理的に区別できないため既存列は `json` として登録)、**行が無い field は構造的に生じない**。型無しで作られた既存列は `string` と報告する — それが現物の型である (§1.5 の 2a、§8 の 4)。**残る実測事項は「upgrade script が既存 application データベースすべてに当たったこと」の運用確認だけ**であり、WP-3 / WP-4 の runbook 手順で担保する。
  - **【状態 2026-09-04 (WP-4)】** **閉じた (実測で裏づけ済み)。** WP-3 の受け入れ監査が実 PostgreSQL に対して `SELECT` を実行し、**registry 19 行 = 全 19 列に行があり、行の無い既存 field は 0 件**であることを確認した。ただし backfill 規則そのものは物理 TEXT を一律 `string` に写す形になった (**L6-16**) ので、「型無しで作られた既存列は `string`」は成立するが「`object` / `array` 既存列は `json`」は成立しない。
- **L6-9 宣言型に対する値検証を `cell` 層へ引き上げたことで、backend のドメイン機構が二重になる (v1.3、G3 の副作用)**。§3 D-3 は MitateDB の値検証を `_prepare_values` 系の choke point へ置き、backend の `_check_domain` / `field_domains` は defence-in-depth として残す。**2 層が同じ性質を別の語彙 (契約 7 語 / 内部ドメイン `text`・`int32`・`int64`・`float`) で判定する**状態になり、片方だけ更新される危険が残る。r2db は `_check_type` (共有) と PostgreSQL の列型という同型の 2 層を既に持つので**新しい形ではない**が、MitateDB では registry が 3 面 (catalog / 読み出し / 受理) を担うぶん結合が強い。**2 層の語彙対応を 1 箇所の表に固定し、変異注入で両層の load-bearing を確かめる**のが WP-3 の手当てである。
  - **【状態 2026-09-04 (WP-4)】** **WP-3 で手当てを実施し、残りを L6-14 へ引き継いだ。** 語彙対応は `field_types.py` の 1 表に固定し、変異 13 (対応表から 1 語を落とす) が 9 本を赤にすることで load-bearing を実測した。**backend 側の 4 ドメインの検査ロジックが同一である**点だけが L6-14 として残る。
- **L6-10 `row_addressability` の限定句の語法が契約内で不揃いになる (v1.3、G8)**。D-3 (vii) の補筆は `other than unavailable` を使う (`partial` を落とさないため) が、**`mutation_classes.rule` の側は `Where row_addressability is enabled` のままである**。本版では rule 側を変えない — D-3 (vii) の射程は `upsert` 節の 1 文であり、rule 側の変更は別の判断だからである。結果として、同じ前提が契約内で 2 つの語法で書かれる。**`row_addressability: partial` を宣言する実装が現れたとき、rule 側の宣言義務が掛からない**という既存の穴もそのまま残る (D-3 (vii) はそれを `upsert` 側へ広げないだけで、閉じてはいない)。次に契約文を触るときに rule 側を `other than unavailable` へ揃えるかどうかの判断材料として記録する。
  - **【状態 2026-09-04 (WP-4)】** **記録のまま。** WP-1 は `upsert` 節の 1 文だけを補筆し、`mutation_classes.rule` が**再帰 diff で無変更**であることを監査が確認した。語法の不揃い (`other than unavailable` と `Where ... is enabled`) は残る。


**フェーズ5 から持ち越している項目 (本フェーズで触れないもの)**

- **L5-5 / L5-6 は本フェーズ WP-0 で処置する (v1.4、裁定 5)**。§3 **D-4(c)** のとおり、同型性テストの機構を **(相対パス, シンボル名) の対応表駆動**へ一般化し、既存 11 ヘルパを初期行として維持したうえで `src/<peer>/main.py::_optional_float` と `tests/test_http.py` の byte 同一テスト関数を行として追加する。**L5-6 (ソース取得方式の左右非対称) は閉じる** — 両 peer とも `ast.get_source_segment` (デコレータを含まない側) に統一する。**L5-5 (兄弟ファイル外の同名ヘルパを対象にできない) は部分的に閉じる** — 取りうる手当て (ii)「走査範囲の拡張」を採り、**兄弟 peer に対応物が無いヘルパは表に載せない**と決めた (表が対象の全数定義であるため、L5-5 が未決としていた「欠落を赤とするか対象から外すか」は「載せなければ対象外」として解ける)。`_ms_from_pg_timeout_text` (MitateDB 側にのみ存在) は載せない — **フェーズ5 WP-3 完了条件 17 が字義どおりには満たされていない**という L5-5 の記録はそのまま残る。
  - **【状態 2026-09-04 (WP-4)】** **WP-0 で実施済み** — **L5-6 は閉止** (両 peer とも `ast.get_source_segment`、`inspect.getsource` はコードとして 0 件)、**L5-5 は部分閉止**。対応表は WP-0 の **15 行**から WP-3 で **18 行** (bearer 合成 / 分解 / timing pin) になった。閉じ方に伴って新たに **L6-11** (デコレータ差が両側とも見えない) を起票している。
- **L5-7 (WP-4 変異 6/7 の実測コスト)** と **L5-8 (下限検査の peer 非対称)** は本フェーズの射程外である。
  - **【状態 2026-09-04 (WP-4)】** **L5-7 は機構としては閉じたが、変異の実測は未了である。** WP-1 追補 A が C-14 vector 5 を構成値に比例しない形へ作り替え、当該 vector の所要は 4 plug 合計で約 6 秒 (最遅 plug 1.53 秒) になった — 「駆動コストが構成値に比例するため変異 6 / 7 が実用外」という L5-7 の前提そのものは消えた。**ただし変異 6 / 7 を実際に再実測してはいない** (WP-1 受け入れ監査 A-3 の証拠不足として記録済み)。**L5-8 は射程外のまま**である。
- **Q4 (`visibility_lag_ms` / `coalescing_window_ms` の 2 プロセス整合)** は独立の設計フェーズとして残る (`PHASE4_DURABLE_AUDIT_SINK_V1.md` §11.2 Q4)。本フェーズは migration 番号の点でのみ Q4 と接する (L6-2)。
  - **【状態 2026-09-04 (WP-4)】** **未着手のまま。** 本フェーズが Q4 と接するのは migration 番号だけであり (L6-2)、WP-4 で正本 2 文書 (`PHASE4_DURABLE_AUDIT_SINK_V1.md` §11.2 Q4 / 第 12 次引き継ぎ §4-2) へ日付付き注記を置いた。
- **外部評価の指摘 1 (conformance の資源管理) と指摘 7 (共通証拠・CI・lock)** は**フェーズ7**、**指摘 6 (実機適用)** は引き継ぎ §4-1 のままである。
  - **【状態 2026-09-04 (WP-4)】** **指摘 2 / 3a / 3b / 4 / 5 は本フェーズで閉じた。** 指摘 1 (conformance の資源管理) と指摘 7 (共通証拠・CI・lock) はフェーズ7 候補として **L6-20** に整理した。指摘 6 (実機適用) は引き継ぎ §4-1 のままである。
- **1.4.0 alias の除去** (従属判断 9 項目 7 の再検討条件): `endpoints.audit_query` (`POST /v1/audit/query`) の alias を除去するかは別途裁定であり、**本フェーズでは除去しない** — D-2 の `surfaces` は alias を surface として扱わない (§3 D-2) が、alias の存在自体には触れない。
  - **【状態 2026-09-04 (WP-4)】** **本フェーズでも除去していない。** `surfaces` は alias を surface として扱わないが、alias の存在自体には触れていない。

- **L6-11 同型性テストはデコレータ差を両側とも見ない (WP-0 レビュー 中-3、2026-09-04 起票)**。D-4(c) で自分側・兄弟側とも `ast.get_source_segment` (`FunctionDef.lineno` 起点、デコレータを含まない) に統一した結果、L5-6 の「取得方式差による赤/緑のぶれ」は閉じたが、**片 peer だけにデコレータが付く変化はこの機構では検出できない** (レビューの対照実験: MitateDB の byte 同一テストにのみ `@pytest.mark.skip` を付けても同型性テストは両 peer とも緑。`skip` 自体は完了ゲートの `skipped 0` が拾うが、skip しないデコレータは何も拾わない)。あわせて、対応表の駆動関数と入れ子 `_normalize` は peer 名リテラルを持つため原理的に表へ載らず、片側 `_normalize` の弱化も不可視である (機構の完全な自己固定は不可能)。手当て候補: デコレータ列を `FunctionDef.decorator_list` から別途正規化して突き合わせる、または対応表の各行に「デコレータ無し」を assert する。本フェーズでは記録に留める。
  - **【状態 2026-09-04 (WP-4)】** **記録のまま。** WP-0 受け入れ監査が「残存ギャップの記録がリポジトリ内に無い」と判定した宿題は、**本項の起票そのもので閉じている**。手当て (デコレータ列の突き合わせ) は未実施。

- **L6-12 D-2 (iii) declare-and-echo は「宣言 URL への実ダイヤル」ではなく「同一 adapter への 2 回呼びの自己整合」で実装されている (WP-1、2026-09-04 起票)**。4 plug とも `*.conformance.invalid` 系の合成 base_url を申告し、HTTP plug も `httpx.ASGITransport` で実ソケットを持たないため、宣言された URL に実際に到達できることは共通 suite では検証されない (CONDITIONS C-19 に開示済み。収集は HTTP plug 2 件のみ)。実ソケットを持つ HTTP plug (実サーバを起動して TCP で叩く形) はフェーズ7 (CI・再現性) の候補であり、そこで初めて「宣言 URL の実在」が load-bearing になる。
  - **【状態 2026-09-04 (WP-4)】** **記録のまま。** WP-3 でも実ソケットは持たない (in-process plug は in-memory sqlite、HTTP plug は `httpx.ASGITransport`)。フェーズ7 候補 (**L6-20**)。
- **L6-13 `isolated_control_surface()` の HTTP plug 実装が旧 pool / client を確実に閉じていることを検査するテストが無い (WP-1 レビュー F9、2026-09-04 起票)**。close を外す変異でも `4 passed`、接続数ピークは雑音の範囲 (24 vs 26)。実害は `max_connections = 300` の下では小さいが、接続リーク検査 (呼び出し前後の `pg_stat_activity` 件数、または `SharedPoolManager` の live pool 数) を置く余地がある。
  - **【状態 2026-09-04 (WP-4)】** **記録のまま。** 本フェーズでは手当てしていない。フェーズ7 候補 (**L6-20**)。

- **L6-14 MitateDB の Postgres backend は `json` / `object` / `array` / `string` を別ドメイン名に分けたが検査ロジックは同一 (`isinstance(str)`) であり、形状の防御は cell 層のみ (WP-3 レビュー F8、2026-09-04 起票)**。値は cell 層で JSON 文字列化されてから backend へ渡るため、backend 単独では object と array を区別できない。設計 D-3 の「3 語を 1 ドメインに畳まない」は名目上満たされ、実効的な形状検証は `cell.py` の choke point (`field_types.check_declared_value`) が担う。将来の選択肢: Postgres 側で `json`/`object`/`array` 列を物理 JSONB (r2db の `_r2db_json_object` / `_r2db_json_array` ドメインと同型の `jsonb_typeof` CHECK) にして defence-in-depth を実体化する。挙動変更を伴うため別 WP。
  - **【状態 2026-09-04 (WP-4)】** **記録のまま。** WP-3 の監督裁定で「実装どおりを正」とし、形状の防御は `cell` 層が担うことを設計 §10.5 の受理境界に記録した。実体化 (物理 JSONB + `jsonb_typeof` CHECK) は挙動変更を伴うため別 WP。
- **L6-15 MitateDB の宣言型 registry 参照が insert 2 回・query 3 回の往復を増やし、キャッシュが無い (WP-3 レビュー F10、2026-09-04 起票)**。正しさには影響しないが、application-plane の遅延として計測対象。cell 単位のキャッシュ (registry は schema operation でしか変わらないので schema revision で無効化できる) が自然な手当て。
  - **【状態 2026-09-04 (WP-4)】** **記録のまま。** 本フェーズでは手当てしていない。
- **L6-16 0006 backfill は物理 TEXT 列を一律 `string` に写す (WP-3 レビュー F7 / 監査 A、監督裁定 2026-09-04)**。作業指示書 WP-3 完了条件 8 の「object/array 既存列は `json`」は物理型が同じ TEXT で区別不能なため同時に満たせない自己矛盾であり、実装どおり `string` を正とする。object/array として使っていた既存列は `add_field` で型付き列を足して移行する (runbook に注記)。
  - **【状態 2026-09-04 (WP-4)】** **監督裁定で確定 (実装どおり `string` 一律が正)。記録のまま。** 根拠と手動 `UPDATE` の remediation は `0006` の KNOWN LIMITATION 節と runbook に開示済みであり、実 DB では対象列 0 件であることを WP-3 監査が `SELECT` で確認した。あわせて作業指示書 WP-3 完了条件 8 の自己矛盾を **L6-18** に記録した。

- **L6-17 `surfaces` 検証ヘルパの同型性が未固定 (WP-3 最終ラウンド、2026-09-04 起票)**。MitateDB は `surfaces.py::_validate_surface_base_url` に集約し r2db と同名同 signature にしたが、r2db 側は `main.py` と `control_main.py` に**コメントの異なる重複コピー**を持つため、対応表 (r2db パス 1 つ) に載せられない。手当ては r2db 側を単一モジュールへ寄せる (重複解消) こと。r2db 無変更の WP-3 制約と衝突したため保留。
  - **【状態 2026-09-04 (WP-4)】** **記録のまま。** 手当て (r2db 側 `main.py` / `control_main.py` の重複解消) はフェーズ7 候補 (**L6-20**)。

**フェーズ6 WP-4 (記録整理) で起票した項目**

- **L6-18 作業指示書 (`WORK_ORDER_PHASE6_CONTRACT_160_V1.md`) の誤り 6 件 — 実装・レビュー・監査が実測で見つけたもの (2026-09-04 起票、指示書 v1.3 に訂正註として反映済み)**。いずれも**実装物の欠陥ではなく発注文書側の誤り**であり、指示書 §0 の規律 (「設計と本書が食い違ったら設計が正、本書の誤りとして監督へ差し戻す」) が実際に発動した例である。
  - **(a) WP-0 のテストコマンドが存在しないファイルを指す** — `r2db-api/tests/test_main.py` は存在せず、r2db 側の該当テストは `tests/test_credential_persistence.py` にある (WP-0 レビュー 小-3、監査が実在を照合)。
  - **(b) WP-3 完了条件 8 (backfill 規則) が自己矛盾している** — 「`object` / `array` 既存列は `json`」と「型無し既存列は `string`」は、MitateDB では 4 契約型がすべて物理 TEXT であるため同時には満たせない (L6-16)。
  - **(c) WP-1 の変異 8 の期待「4 plug で赤」が誤り** — 当該 vector は `form == "provided"` の枝でのみ同居判定に到達し、その枝へ入る plug は 1 つだけなので、**赤にできる上限が 1 plug** である。
  - **(d) WP-3 の変異 16「片方の plane だけ 1.5.0 へ戻す」は、どちらの面かで結果が変わる** — 全体 vacuity guard を赤にするには **data 面 (`cell.py`) の flip が要る** (C-19 の guard は adapter の `contract_version()` = data 面の capability 文書を読むため)。フェーズ5 の C-09 guard が control 面の宣言だけを見ていたのとは source が異なる。
  - **(e) WP-1 完了条件 7 (d) が「D-4 却下 2 件」を要求している** — `spec/CCR_DISPOSITION.md` は**契約変更の従属判断**を記録する場所であり、契約に触れない衛生決定 (D-4) の却下案は射程外である。項目 4 (D-3 (vii)) の却下と取り違えた誤りであり、書くべきは後者だった。
  - **(f) 版数参照の取り残し** — 指示書 v1.2 の冒頭が正本設計を「v1.3、確定」と引いていたが、設計ファイルは **v1.4** である (WP-1 監査 疑義 (vii))。
- **L6-19 C-14 の `limit_class` assert は soft-assert であり、宣言しない peer に対しては空振りする (WP-1 追補 A-2 / レビュー F4 の帰結、2026-09-04 起票)**。`limit_class` は契約が保証する項目ではないため、`exc.details.get("limit_class")` が `None` のときは何も要求しない形にした — これは `test_c16_cross_entity_atomicity.py` の同型の検査と**同じ形**である。現況は両 peer とも実際に `limit_class` を出しているので load-bearing だが (変異 A′ が字義どおり赤になる根拠)、**将来 `limit_class` を出さない実装が現れると 2 条件とも静かに空振りに戻る**。手当ての候補は (i) 契約側で `limit_class` を義務化する、(ii) 「出す peer に対しては必ず一致する」ことを別の非空虚 assert で担保する、のいずれかであり、どちらも契約判断を伴うため本フェーズでは採らなかった。
- **L6-20 フェーズ7 の候補 (2026-09-04 時点の一覧。優先順の裁定は次フェーズの枠で行う)**。
  - **(a) 共通 suite に載っていない条件の共通化** — `C-00` / `C-02` / `C-04` / `C-05` / `C-07` / `C-10` は `CONDITIONS.md` 上で **not yet executable (common suite) — peer-local evidence only** のままである。外部評価の**指摘 1 (conformance の資源管理)** と同じ工程で扱うのが自然である。
  - **(b) 共通証拠・CI・lock (外部評価 指摘 7)** — 依存の pin と再現可能な実行環境。本フェーズで `pytest-xdist` を両 peer の dev extras に足したことで、実行環境の差が集計行に効く余地が増えている。
  - **(c) 実ソケットを持つ HTTP plug** — L6-12 の手当て。ここで初めて `surfaces` の「宣言 URL の実在」が load-bearing になる。
  - **(d) r2db の `surfaces` 検証ヘルパの重複解消** — L6-17 の手当て。`main.py` / `control_main.py` の 2 コピーを 1 モジュールへ寄せれば、同型性の対応表に載る。
  - **(e) `isolated_control_surface()` の pool close 検査** — L6-13 の手当て。
