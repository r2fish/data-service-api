# R-23 AI エージェント向け派生成果物 — 着手前調査

Status: **調査メモ。非正本、未承認、未実装**
Date: **2026-09-13**
Scope: `spec/`、`tools/contract_catalog.py`、capability discovery、L9-4、R-29、関連 conformance の現物確認。契約・実装・配備・ロードマップの状態は変更しない。

## 利用規則（他のAIを含む読者向け）

この文書は、R-23 の**着手前調査**であり、正本、設計決定、実装指示、作業指示書、conformance 要件ではない。ここにある bundle の形、R-23/R-29 の順序、scenario の候補、Security Invariants の適用は、調査時点の提案または観測結果であって、採用済みの結論ではない。

R-23 または R-29 を着手するAI／担当者は、先にロードマップ、`spec/`、`security/`、現行実装、capability document、関連 conformance と実需を再照合し、採用する範囲を設計レビューで明示的に確定すること。本書の事実調査を出発点として再利用してよいが、提案を無批判に実装・契約化・優先順位化してはならない。正本と矛盾する場合は常に正本を優先する。

## 1. 結論

R-23 は契約を改版せずに着手できる。ただし、最初の成果物は **現行契約の構造だけを再配置する静的な JSON bundle** に限るのが安全である。完全な要求例や「両 peer で必ず成功する」手順は、schema の単純投影だけでは作れない。operation ごとの条件付き必須関係、実配備の capability / limit、peer 間の提供差を実行時に解決する必要があるためである。

推奨する最小順序は次のとおり。

1. R-29 で最低共通シナリオの capability 前提と禁止する任意機能を固定する。
2. R-23 で `spec/data-service-api.v1.json` だけから静的 bundle を生成し、byte 一致テストを置く。
3. R-29 の scenario がその bundle と実際の `CapabilityDocument` / `CatalogDocument` を入力として要求を組み立てる。
4. 実配備から bundle を取得可能にする必要が実証された場合だけ、L9-4 (`operation_catalog_url`) または新しい標準 discovery link を別の契約判断として扱う。

これにより、OpenAPI を正本にしない `spec/README.md` の決定、宣言優先、Security Invariants を保ったまま、R-23 と R-29 の間の受け渡しを conformance で観測できる。

## 2. 現在すでに提供される情報

### 2.1 静的な共通契約

`spec/data-service-api.v1.json` は現在 1.8.0 で、次を持つ。

- data 7 + control 12、計 19 operation の method、path、受理 role、必須 capability、atomicity、request / response schema 名。
- `schemas` 20 件と `definitions` 6 件。field の型、required、enum、配列上限、identifier pattern、`additionalProperties` など、要求・応答形の大部分。
- Bearer 認証の方式と、返された secret を加工せず使う規則。
- capability の定義語彙、限界クラス、limit enforcement、構造化エラーの全体語彙、破壊操作、dry run / plan、idempotency、request budget、version obligation。
- `CapabilityDocument.surfaces` による data / control base URL の相互 discovery と、`CapabilityDocument.operation_catalog_url` の optional schema。

したがって「何を呼ぶか」「どの role が呼べるか」「どの JSON shape を送受信するか」の素材はすでに正本にある。

### 2.2 現行の派生成果物

`spec/OPERATION_CATALOG.json` は `tools/contract_catalog.py` による純粋な構造投影である。各 operation に次の 9 項目を持ち、operation 名で安定 sort される。

`name`, `method`, `path`, `roles`, `requires_capability`, `atomicity`, `destructive`, `request_schema`, `response_schema`

`conformance-tests/test_operation_catalog_register.py` は次を固定する。

- generator の再実行結果と checked-in artifact の byte 一致。
- auth と roles、capability 名、atomicity 語彙の整合。
- destructive の構造化原典との対応。
- endpoint 数 19 の非 vacuity。

これは信頼できる索引だが、schema 名から schema 本体へは別ファイルを引く必要がある。

### 2.3 実配備の discovery

`GET /v1/capabilities` と `GET /control/v1/capabilities` は、credential の authority に応じた次の配備固有情報を返す。

- `contract_version`
- capability ごとの `status` と、open な capability 固有情報
- `limits` と `limit_enforcement`
- `authorization_propagation_bound_ms`
- credential に応じた `application_scope` / `role`
- `surfaces.data.base_url` と、control plane がある場合の `surfaces.control.base_url`

`GET /v1/catalog` は Application の entity、field、field type、mutation class、revision、field constraint を返す。C-19 は bearer secret の verbatim 利用、surface discovery、field type round-trip を検査し、socket plug では宣言 base URL を実 TCP で dial する。C-11 / C-12 / C-17 は capability / catalog document の shape・宣言・挙動の一致を補強する。

### 2.4 すでにある scenario 部品

R-16 の調査記録どおり、フェーズ9 は周回の後半を個別条件として持つ。

- C-20: 宣言した field constraint と挙動の一致。
- C-21: 拒否の構造化診断。
- C-22: dry run と実呼びの判定一致、外部副作用 0、plan。
- C-23 / C-27: 逐次・同時再送の idempotency。
- C-24: request budget。
- C-25: 成功結果の `request_id`。

不足しているのは、これらを discovery と catalog から始めて 1 本につなぐ段間の検査であり、個々の安全性質の再実装ではない。

## 3. 不足情報と、単純生成できないもの

### 3.1 1 ファイル性

現行 catalog は schema 名までで、schema / definition 本体、security、errors、limits、version obligations を内包しない。エージェントは `OPERATION_CATALOG.json` と契約 JSON の複数箇所を join する必要がある。

### 3.2 完全な要求例

schema は JSON Schema に近いが、全 operation の完全な要求生成器ではない。例えば `SchemaOperationRequest` は operation ごとに必要になる `field` / `fields` / `index` / destructive confirmation 等の関係を単一の `required` / `oneOf` として表していない。Mutation の addressability、capability で追加される `dry_run` / `idempotency_key` / `budget`、破壊確認の現在値も静的な required-only walk では決められない。

したがって、schema から適当な値を埋めた「完全例」を自動生成すると、構文上は近くても意味上無効、または一方の peer だけで失敗する advisory artifact になり得る。具体例は R-29 の実行可能 scenario fixture と同じ原典から生成し、両 peer で実証すべきである。

### 3.3 path parameter と server binding

`{entity}` / `{application_id}` / `{credential_id}` は path に埋め込まれているが、独立した parameter object と値の取得元は catalog にない。静的 artifact は placeholder の存在までは投影できるが、値は runtime の catalog、control response、または scenario が作成した resource から束縛する必要がある。

server binding 自体は `CapabilityDocument.surfaces` で解けるが、静的 bundle に実 URL を埋めてはならない。base URL と credential を入力し、最初の capability call で binding を得る二段構成が必要である。

### 3.4 配備から派生成果物を取得する URL

L9-4 のとおり `operation_catalog_url` は optional で、現行両 peer は宣言しない。よって「共通 spec を手元に持つ agent」向けの checked-in bundle は契約変更なしで作れるが、「base URL だけから bundle 自体も取得する agent」は現状保証できない。

L9-4 を先に閉じることは可能だが、公開 URL の実在・内容・version 対応・cache / 更新原子性を配備証拠にする必要がある。さらに R-23 の成果物が既存 `OPERATION_CATALOG.json` と異なる shape なら、現在の `operation_catalog_url` の説明だけでそれを指すべきではない。既存 URL の意味変更か、新しい link relation かを明示的に裁定する必要がある。

### 3.5 operation ごとの error code

正本は 17 code の全体語彙を持つが、endpoint ごとの部分集合を構造化していない。フェーズ9で advisory な per-endpoint error list を catalog に載せないと裁定済みである。R-23 の派生物も、散文解釈で endpoint 別一覧を発明してはならない。全体語彙と code-specific details schema を載せ、実際の拒否は capability / request と構造化 details から処理する。

### 3.6 capability は静的表では確定しない

現行の代表的な非対称は次のとおり。

- r2db: `structured_query` / `atomic_mutation` / `revision_preconditions` / `row_addressability` は enabled、`cross_entity_mutation` は unavailable。
- MitateDB: `structured_query` / `atomic_mutation` / `cross_entity_mutation` は partial、`revision_preconditions` / `row_addressability` は unavailable。

このため agent は `status != unavailable` だけでなく capability 固有の `operations` / `unsupported` / operator 語彙を読まなければならない。最低共通作業列を静的に「全実装の必須契約」に変えるのではなく、R-29 の conformance profile と runtime discovery の組合せとして扱うべきである。

## 4. 正本を変えずに作れる最小の派生成果物案

仮称 `spec/AGENT_CONTRACT_BUNDLE.json` を 1 ファイル生成する。これは新しい意味を足さず、次の既存構造を再配置する。

```text
contract_version
discovery
  data_capabilities_operation: "capabilities"
  control_capabilities_operation: "control.control_capabilities"
operations[]
  OPERATION_CATALOG.json の 9 項目
  request_schema_body: schemas[request_schema] または null
  response_schema_body: schemas[response_schema] または null
definitions
security
  schemes
  roles
  scope
errors
  content_type
  shape
  codes
  details_vocabulary
limits
  classes
versioning
  obligations
```

`discovery` の値は endpoint の `name` を参照するだけとし、URL や credential を埋め込まない。schema body 内の `#/definitions/...` は bundle の `definitions` にそのまま解決できる。最初の版では OpenAPI、SDK、自然言語要約、endpoint 別 error list、完全例、実 URL を出さない。

生成規律は `tools/contract_catalog.py` と同じにする。

- 入力は `spec/data-service-api.v1.json` のみ。既存 catalog を二次入力にせず、共通の projection helper を用いて drift を避ける。
- 散文を parse / 要約せず、値は byte-for-byte で運ぶ。
- stable field order、operation name sort、UTF-8、trailing newline。
- checked-in artifact と fresh regeneration の byte 一致、source reference の全解決、operation 19 件 / schema 20 件 / definition 6 件の非 vacuity を register test で固定する。
- artifact 自身に `generated`, `non_authoritative`, `source` を明記する。ただし source hash を正本性の代用品にはしない。

この最小案は schema 本体・認証情報・discovery operation・error / limit 語彙の「一体提供」を改善する。一方、完全例と配備からの取得は閉じないので、R-23 全体をこの artifact だけで閉止してはならない。

## 5. 着手時に必要な設計判断

### D1. 成果物の境界

推奨: 初版は上記 JSON bundle 1 点だけ。OpenAPI は bundle の実需が確認された後の二次派生物とし、OpenAPI を正本にしない決定を維持する。

### D2. 「純粋な投影」の境界

推奨: schema / prose はコピーだけ許し、解釈・要約・endpoint 別意味付けはしない。新しい machine-readable な意味が必要なら正本側の契約判断とする。

### D3. 具体例の所有者

推奨: example を artifact generator の推測で作らず、R-29 scenario の synthetic fixture を正本として派生する。成功例だけでなく、安全な修正周回のための意図的 refusal と修正版を対にする。

### D4. 最低共通 profile の定義

推奨: capability status の固定 snapshot ではなく、「scenario が必要とする capability / operation / operator の最小集合」とする。runtime discovery が満たさなければ scenario は silent skip せず、R-29 の ABSENT / refusal evidence として扱うか、profile 非適合として明示的に失敗させる。

### D5. 配備 discovery と L9-4

推奨: checked-in static bundle の完成を先行させる。配備からの取得要求がある場合、既存 `operation_catalog_url` を bundle に拡張するのか、別 URL field を加えるのかを決める。いずれも契約・peer・配備・socket conformance にまたがるので、静的 bundle と同じ変更束に混ぜない。

### D6. version skew

推奨: agent は bundle の `contract_version` と runtime capability document の版を比較し、runtime が bundle より古い場合はその版の obligation だけを適用する。runtime が新しい場合は、未知の additive capability / field を拒否せず、必要な新 artifact の取得経路がないことを明示する。正確な互換判定規則は着手設計で固定する。

## 6. Security Invariants の適用

R-23 は新しい実行 capability ではなく派生表示であるため、新しい Security Invariant は不要である。ただし artifact と scenario が誤った authority や安全条件を agent に教えると既存境界を弱めるので、次を適用する。

- SI-01 / SI-06 / SI-07: Application scope を入力値として作らず、credential から server-side に束縛された `application_scope` と catalog を使用する。
- SI-02 / SI-03: data / control plane と runtime / developer / control / audit role の区別を operation ごとに保持する。例が control credential や Developer authority を Runtime 手順へ流用しない。
- SI-04 / SI-05: 例・manifest は structured request だけを生成し、SQL や database-native command の escape hatch を提供しない。identifier / operator / schema validation を省略しない。
- SI-08: runtime の `limits` / `limit_enforcement` と request budget を先に読み、例の値を固定上限と見なさない。scenario 自体も小さな synthetic fixture と有限件数に制限する。
- SI-09: destructive operation の `destructive` フラグだけで実行可能とみなさず、現在の refusal から得た confirmation を exact echo する既存規則を維持する。R-29 の最小 happy path は原則非破壊にする。
- SI-10: artifact と fixture に real credential、host、Application / user data、row value、内部接続情報を記録しない。エラー例は contract の安全な details 語彙だけを使う。
- SI-11: atomicity と idempotency を別概念として保持し、scenario は宣言された atomic scope を越えて成功を推定しない。
- SI-14: scenario の成功・拒否・再送を `request_id` と audit evidence へ関連付ける場合、capability が利用可能な枝だけで行い、監査不可の配備で silent pass にしない。
- SI-15: capability、role、scope、schema、limit が確定できない場合は request を生成・実行しない。未知の additive field は互換に扱えても、未知の authority を推定してはならない。

公開リポジトリ規律として、auth example は `Authorization: Bearer <API_KEY>` のような placeholder のみを使い、生成 artifact / snapshot / test output に実値を残さない。

## 7. R-29 との実施順と依存関係

R-23 と R-29 は対だが、完全な直列ではない。

### 先に確定するもの — R-29 の scenario contract

最低共通 scenario の目的、必要 capability、使用しない非共通機能、synthetic entity / field、refusal から修正へ渡す details、dry run、実行、同一 key 再送の観測点を先に固定する。これは「完全例」が本当に両 peer で実行可能かを決める入力である。

最低共通経路は、現行非対称を避けて次を候補にする。

1. Developer credential（Application credential の一種）で capabilities と catalog を取得。
2. 同じ Developer credential と `schema_operations` で synthetic entity を作成。
3. `atomic_mutation` の共通 operation で insert。`upsert` は使わない。
4. `structured_query` の共通 operator だけで query。MitateDB が unsupported と宣言する `contains` / `matches` / `is_null` は使わない。
5. 意図的な schema/value refusal を C-21 details から修正。
6. `dry_run` → plan を付けた実行。
7. `idempotency_key` を同一 body で再送し、元の `request_id` / result が返ることを確認。

`revision_preconditions`、`row_addressability`、`cross_entity_mutation` は peer 間で共通でないので、最低共通シナリオの必須経路から外す。

### 並行して作れるもの — R-23 の静的 bundle

上記 scenario の具体値を含めない schema / operation / security / error / limit bundle と generator は、R-29 の最終決定を待たずに作れる。ただし、example section と scenario-facing convenience field は R-29 の決定前に足さない。

### 最後に結合するもの

scenario test は hard-code した method / path / schema 名ではなく、generated bundle の operation と runtime capability / catalog document を読んで request を作る。これにより次の段間不整合が初めて検出可能になる。

- catalog の schema 名は正しいが schema body が bundle に無い。
- static capability dependency と runtime status / vocabulary が食い違う。
- discovery した surface と選んだ operation の plane が食い違う。
- refusal details が修正ロジックへ渡せない。
- dry-run body と real / replay body の digest 対象が段間で変わる。

## 8. 着手時の最小 Change Set 案

最初の実装束は契約・peer・配備を変更しない repository artifact の変更に限定する。

- `tools/agent_contract_bundle.py`（新規、標準ライブラリのみ）
- `spec/AGENT_CONTRACT_BUNDLE.json`（新規、非正本の生成物）
- `conformance-tests/test_agent_contract_bundle_register.py`（新規、byte 一致・参照整合・非 vacuity）
- `spec/README.md`（生成物の非正本性と利用順だけ追記）

R-29 の scenario conformance、具体例、L9-4 の配備 URL 宣言は別 Change Set とする。この分割なら、初回レビューで projection の正しさだけを判定でき、agent workflow の安全性・両 peer 実行性と混ざらない。

## 9. 調査時確認

- 既存ファイルは変更していない。
- ロードマップの R-23 / R-29 / L9-4 の状態は変更していない。
- 本ファイルは調査結果だけであり、正本・契約・conformance 条件ではない。
- `tools/contract_catalog.py --check`: 成功。
- operation catalog register: 通常の pytest 起動は、必須 socket adapter の PostgreSQL 接続が sandbox で拒否され collection 前に停止した。adapter を必要としない同ファイルの 12 register 関数を直接実行し、12 件すべて成功。
- `tools/check_doc_refs.py`: dangling reference 0、empty tracked Markdown 0。
- `tools/public_value_scan.py`（本ファイルを明示）: flagged 0。R7（個人名）は scanner の仕様どおり未検査であり、目視でも実値を追加していない。
- `git diff --check`: 成功。既存の未コミット変更 2 ファイルは本調査の対象外であり、触れていない。
