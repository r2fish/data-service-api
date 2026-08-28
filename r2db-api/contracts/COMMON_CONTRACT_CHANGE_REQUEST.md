# 共通契約変更要求 (r2db-api 起票)

- 起票日: 2026-08-28
- 改訂: 2026-08-28 (第2版: 独立レビューを受けて CCR-13 を全面改稿、CCR-14 を改稿、CCR-15 を追加。第3版: 第2版への独立レビューを受けて CCR-13 のスコープと検証可能性を確定、CCR-14 に discovery / reset / 削除範囲を追加し乖離の数え方を訂正、CCR-15 に形状を定義)
- 起票者: r2db-api 側設計作業
- 宛先: 共通契約 `spec/data-service-api.v1.json`
- 採否記録: `spec/CCR_DISPOSITION.md`

`MitateDB-api/contracts/COMMON_CONTRACT_CHANGE_REQUEST.md` (CCR-01〜12) と同じ様式で起票する。番号は通番を継承する。

## 起票の基準

いずれも r2db-api 固有の都合ではなく、**共通契約の欠落**として提起する。判断の軸は次の順序に置く。

1. **堅牢で安全であること**
2. その上で**最大限の自由があること**

したがって本要求は、**道路にゲートを設けるのではなく、ガードレールを設けることを目指す。** 具体的には次を守る。

- **機構ではなく結果を要求する。** SI-00 が「containment を要求し、特定の topology を要求しない」のと同じ形にする。機構を契約に書くと、その機構に合わない将来の Capability が「新しいという理由で」通れなくなる。
- **ガードレールは危険のある場所に置く。** 安全要求のスコープは危険の所在から導く。危険の無い区間への無条件の要求は、それ自体がゲートになる (第2版の CCR-13 はこれを誤った)。
- **能力の提供を強制しない。** 必要としない配備に攻撃面を強制するのはゲートである。契約は形状と意味論を定め、可用性は `capability_status` で申告させる。
- **結果は検証可能な性質に分解する。** 散文のままの結果は適合テストが書けず、「機構は自由」が「何も固定されていない」に転化する。機構の自由と相互運用性は、性質の固定によって初めて両立する。

---

## CCR-13 — 行の安定した指し示し可能性 (row addressability)

### 要求

共通契約に、**行を狙った mutation (update / delete / upsert) を支持する entity について、entity 内の行を安定して指し示せること**を結果として要求する。読み取り専用または追記専用の entity は、その旨を catalog で宣言することで本要求の対象外となる。あわせて、ドメイン上の一意性を entity 単位で宣言できる仕組みを定義する。

ガードレールは危険 (行を狙った書き込み) が存在する場所に置く。書き込みを支持しない区間に守るべきものは無い。この免除は第1版の「任意宣言」への回帰ではない。第1版の宣言は**可変データが安全から離脱する選択**であったが、本版の免除は **entity の能力 (行を狙った書き込みを支持しない) から従う**。ガードレールの無い区間は生じない。

**機構は規定しない。** 実装は rowid 相当、サーバ採番の連番、クライアント供給の UUID、自然キー、内容ハッシュ、その他いずれを用いてもよい。ただし機構の自由は、クライアントから見た指し示し方が実装ごとに異なってよいことを意味しない。結果を次の4性質に分解して固定する。

### 指し示し可能性の4性質 (適合テストの単位)

1. **宣言** — addressable な entity は、アドレスを構成するフィールド組を catalog で必ず宣言する
2. **可視** — アドレスフィールドは通常の select 可能なフィールドであり、query 結果に現れる
3. **照準** — アドレス組全体に対する `where` + `eq` は高々1行に一致する
4. **一意・不変** — アドレス組の値は entity 内で一意であり、行の生存期間中変化しない

この分解により、機構が自由なままでもクライアントの手順は一様になる: **catalog で宣言を読む → select で取得する → where eq で照準する。** 散文 (「同じ行を後から確実に指せる」) のままでは適合テストが書けない。とりわけ性質4を欠くと、read → address → mutate の間にアドレスが変わりうる実装が適合してしまう (下記の SQLite rowid が実例である)。

### 問題 — 契約が意味を与えられない操作を既に許可している

`structured_operations.allowed_mutations` は既に `upsert` を含む。

```
allowed_mutations: ["insert", "update", "upsert", "delete"]
```

**upsert は「既存かどうか」の判定基準なしには意味を定義できない。** 何をもって「既に在る」とするのかを契約は一切述べていない。したがって現行契約には、**いかなる実装も正しく実装しようがない操作が含まれている。** これが本要求の第一の、そして最も強い根拠である。

### 副次的な問題 — 事前条件の被参照先が未定義

`Mutation.expected_revision`、`transactions.retry`、エラーコード `PRECONDITION_FAILED` は revision による事前条件を三度言及するが、revision が何を指すのかを定義していない。entity のスキーマ revision に束ねる読み方も文言上は可能であり、実装ごとに別の意味になりうる。

これは「実装不能」ではなく「相互運用可能な形で有効化できない」である。現に両 peer は当該フィールドを `CAPABILITY_UNSUPPORTED` として正当に拒否しており、今日の破綻はない。しかし両 peer がこの能力を有効化した瞬間に非互換になるため、有効化前に契約が被参照先を固定しなければならない。

第2版はこの未定義を問題として指摘しながら、変更表で何も固定していなかった。本版で固定する。**revision の被参照先は次の5条項とする。**

1. revision は実装が発行する**不透明な文字列**であり、クライアントは内容を解釈しない
2. スコープは**行**である (entity のスキーマ revision とは別物である)
3. 当該行への mutation が commit されるたびに変化する
4. `expected_revision` の比較は mutation と**原子的に**行われる
5. 不一致は `PRECONDITION_FAILED` で失敗する

`QueryResult` が revision を行とともに返す要求は、**`revision_preconditions` を有効と申告する実装にのみ適用する。** 無効と申告する実装に revision の維持を強制しない。

### 第1版の誤りの訂正

第1版は「`expected_revision` と `idempotency_key` の双方が行の同一性を前提とする」と記した。**`idempotency_key` について、これは誤りである。**

`idempotency_key` は `MutationRequest` に属するリクエスト単位の項目であり、`Mutation` (行単位) には属さない。サーバはキー→リクエスト要約→結果の重複排除ストアで実装でき、行の同一性を必要としない。

第1版はこの誤りに基づき「同一性を宣言しない entity では `idempotency_key` も利用不可」と提案していた。これは無関係な二つの機構を結合させ、**リトライによる重複追記が最も起きやすい追記専用データから、冪等性を奪う**提案であった。撤回する。

`idempotency_key` はサービス単位の Capability として、行の指し示し可能性とは独立に扱う。

### 証拠 — 実クライアント

r2db-api の現行クライアント (勤務表 etc、18 テーブル) は全テーブルで `id` による行指定を行う。加えて upsert 相当を全箇所で「自然キーで検索 → 見つかれば PATCH、無ければ POST」として手実装している。一意性制約が無いため、競合時に重複を生じうる。

ただしこの証拠の性質を正確に述べる。**このクライアントは現行 VPS 実装 (本契約の統治外) を相手にしており、本契約の利用者が要求したものではない。** 示しているのは「ある実アプリケーションがデータサービスに何を必要としたか」であり、同時に「本契約が唯一の移行対象を収容できない」ことである。

またこのクライアントは列の型、NOT NULL、DEFAULT も必要としている。**行の指し示し可能性だけでは本契約はこのクライアントを収容できない。** 本要求はスキーマ表現力の欠落の第一項であって、最後の項ではない。

### 必要となる契約変更

書き込み側だけでは足りない。読み取り側を含む。

| 箇所 | 変更 |
|---|---|
| `CatalogDocument.entities` | 現在は型なしの配列。entity ごとに (a) addressable / 読み取り専用 / 追記専用の別、(b) addressable の場合はアドレスフィールド組、(c) ドメイン一意性宣言、を記述できる形にする |
| `QueryResult` | `revision_preconditions` が有効な実装は、事前条件に使う行 revision を行とともに返せるようにする。取得できない値を precondition に使えというのは成立しない |
| `MutationResult` | 現在は `{committed, affected}`。サーバ側で採番された識別子を返せるようにする |
| `structured_operations` | `upsert` の判定基準を宣言済みドメイン一意性に紐づける。未宣言 entity での `upsert`、および addressable でない entity への行を狙った mutation は `CAPABILITY_UNSUPPORTED` |
| `structured_operations` | 事前条件の5条項 (上記) を契約文言化する |
| `allowed_schema_operations` | 一意性は既存の `create_index` に `unique` を加える形で表現でき、新語彙をほぼ増やさない |

`upsert` の制限は自由の制限ではない。**意味が定義できないものを、定義できないと正直に申告している**にすぎない。

### Security Invariants との関係

新たな invariant は不要と考える。

- SI-11 の retry/precondition 条項が初めて実効化される
- 一意性違反は Application 自身のスコープ内で `CONFLICT` として現れ、他 Application の存在を漏らさない (SI-10 に抵触しない)
- キー宣言は既存の SI-05 の識別子検証境界を通る

ただし **SI-08 に関して契約に一文が要る。** 冪等キーの重複排除ストアは、保持期間の上限を定めなければ無限に増える状態である。有限の保持境界を要求する条項を加える。

### 両 peer 適用可能性

機構を規定しないため、双方が自然な手段を取れる。ただし第2版の SQLite rowid の引用は訂正が要る。

- **MitateDB-api (SQLite)**: rowid は **`INTEGER PRIMARY KEY` の別名である場合に限り**安定である。裸の rowid は `VACUUM` により振り直される (実測確認済み) ため、性質4「不変」を満たさない。自然な機構は `INTEGER PRIMARY KEY` 列または宣言された一意キーであり、いずれも標準機能で足りる。この実例こそが、結果を散文でなく4性質に分解する理由である — 散文に対する適合テストは VACUUM の事例を検出できず、性質4に対するテストは検出できる。
- **r2db-api (PostgreSQL)**: 現在すべてのフィールドを型なし JSONB 列として保存しており、制約機構を持たないため変更は大きい。ただしこれは実装コストであって契約の非適用性ではない。storage 層は `field_type` の実装のためにいずれ型付き列へ作り直す必要があり、その作業と同時に行うのが最も安い。

---

## CCR-14 — 制御プレーンのプロビジョニングおよび credential ライフサイクル

### 要求

共通契約に、control 権限で認証する制御プレーンの**形状と意味論**を定義する。**endpoint の提供は必須としない。** 実装は `capability_status` により可用性を申告し、提供しない実装は当該操作を `CAPABILITY_UNSUPPORTED` とする。

```
POST   /control/v1/applications                 Application 登録
GET    /control/v1/applications                 一覧
POST   /control/v1/applications/{id}/disable    無効化
POST   /control/v1/applications/{id}/enable     有効化
POST   /control/v1/credentials                  発行 (秘密は一度だけ返す)
GET    /control/v1/credentials                  一覧 (秘密は含まない)
POST   /control/v1/credentials/{id}/rotate      ローテート
POST   /control/v1/credentials/{id}/revoke      失効
POST   /control/v1/credentials/{id}/disable     無効化
POST   /control/v1/credentials/{id}/enable      有効化
```

`lifecycle.credential` が挙げる四つの動詞 (issue / rotate / revoke / disable) をすべて表現する。

**Application の削除は意図的に含まない。** v1 では disable が終端状態である。将来削除を導入する場合は SI-09 の destructive 意味論に従う別途の契約変更とし、監査の連結を切ってはならない (現行 VPS 実装の `ondelete=CASCADE` の教訓)。

### 提供を必須としない理由

設定で宣言する静的な制御プレーン (Application を構成ファイルで宣言し、動的なオンボーディングを持たない配備) は正当な選択肢である。**必要としない配備に HTTP の攻撃面を強制するのはゲートである。**

契約が定めるのは形状と意味論であり、提供するか否かは配備の判断とする。これにより、**制御手段を提供する実装は必ず同じ形で提供する**という性質は保たれる。

### 問題 — 意味論は既にあり、口だけが無い

契約は既に次を定義している。

- `security.roles` に `control` と `audit`
- `security.schemes.control_credential` — 「別途認証される Control/Audit 権限。application credential は受理しない」
- `lifecycle.credential` — control authority は credential を発行・ローテート・失効・無効化してよい
- `POST /v1/audit/query` は `auth=control or audit` として**既に存在する control 認証の HTTP endpoint** である (CCR-12 で採用済み)

すなわち「意味論は採用済みであり、それを行う口だけが未定義」という状態にある。

**乖離の数え方の訂正。** 第2版までは「三実装が三様に乖離している」と述べたが、数え方が誤っている。統治下の2 peer はいずれも HTTP 制御面を持たず (プログラム内部の `ControlAuthority` / `ControlPlane` のみ)、**公開面の乖離は現にゼロ**である。旧 VPS 実装は契約の統治外であり、乖離の数に入らない。正確に述べれば、**乖離は起きた問題ではなく見込みの問題である。** ただしその見込みには根拠がある。統治外の実装は、契約が黙っているときに制御面がどこへ行き着くかを現に示しており (下記の教訓)、統治下の2 peer が今後それぞれ制御面を持つとき、契約が黙っていれば収束すべき形が存在しない。

オンボーディングに運用者のサーバログインを要する状態が汎用データサービスと言えるかという製品上の論点は、この論拠の傍証であって主論拠ではない。

### SI-02 との関係、および同居の問題

SI-02 が制約するのは *Application-facing Runtime and Developer APIs* が到達しうる範囲である。別種の credential で認証される面は Application API ではない。`/v1/audit/query` の存在が、採用済み契約が control 権限の HTTP 面を許容することを既に示している。

**ただし SI-00 の観点で残る問題がある。** 脅威モデルは「application-facing の実装欠陥が単一で起こりうる」と仮定し、SI-00 はそれが制御プレーンを侵さないことを要求する。制御面を Application 面と同一プロセス・同一ルータ・同一ミドルウェアで提供すると、ルーティングまたは認可ミドルウェアの欠陥ひとつが、まさに「単一の application-facing 欠陥による制御プレーン侵害」となる。

一方で「別プロセス・別リスナで動かすこと」を要求すれば、内部境界を保てる単一プロセス配備を潰すゲートになる。**要求すべきは結果である。**

- 制御面は Application 面と**分離して配備可能でなければならない** (契約は同一の network endpoint / プロセスでの提供を要求しない)
- **SI-00 の適合証拠は、同居する場合にその境界がどう保たれるかに答えなければならない**

配置は自由、境界の実証は必須。base path を `/control/v1` として `/v1` から分けるのは、この分離を reverse proxy の切り出しではなく自然な単位にするためである。

### 制御面の discovery と versioning

分離配備される制御面は、`GET /v1/capabilities` が同一ホストに存在することを前提にできない。したがって:

- 制御面を提供する実装は、制御面自身の discovery (`GET /control/v1/capabilities`) を提供する
- `/control/v1` は `versioning.compatibility` と同じ互換性規則 (additive は許可、削除・意味変更は新 major version) に従う

### 最後の control credential と reset

- 最後の有効な control credential の失効は**禁止しない**。侵害された credential は常に失効可能でなければならず、失効を禁止すれば「最後の1本が盗まれた場合」に失効できなくなる
- ただし明示的な確認を要する (SI-09 の destructive 意味論と同型)
- 復旧経路は bootstrap の reset である。reset の意味論を契約に置く: 運用者 / OS 権限のもとでのみ実行可能であり、対象は control credential のみで **Application データと監査証跡を破壊しない**こと、正準の監査イベントを発行すること

### control credential の in-band 発行 — 未決として両論を残す

rotate / revoke / disable を HTTP に置く論拠は成立する (「個別に失効できる」は操作手段を要する)。しかし**新しい control credential の発行**まで in-band である必然は、この論拠からは従わない。両案を依頼者判断として残す。

- **案A — 発行も in-band**: 運用が一貫し、複数運用者の追加にサーバ権限が要らない。ただし盗まれた1本から新しい credential を発行でき、**失効を生き延びる永続性**を攻撃者に与える。既存 invariant は control credential の侵害を扱っていない (SI-00 は Application credential の条項である)
- **案B — 発行は帯域外の儀式に留める** (Vault root の慣行): 永続性の危険を断つ。ただし運用者追加のたびにサーバ権限が要り、CCR-14 が解こうとした運用形態が control credential についてだけ残る

いずれを採るかで conformance 条件が変わるため、採否と同時に判断する。

### 現行 VPS 実装からの教訓 — 三つある

1. **単一の共有パスワードで全 Application を支配してはならない。** `/admin/api/*` は環境変数の 1 パスワードで認証し、Application 単位のスコープを持たない。漏洩時に全 Application が同時に落ちる (SI-00)。失効すれば全運用が止まるため実際には失効できない (SI-13)。監査の `actor_id` が意味を持たない (SI-14)。
2. **認証の秘密を署名鍵に流用してはならない。** `admin_session.py` の署名材料は `admin_session_secret` が空のとき `admin_password` にフォールバックする。認証の秘密とトークン署名鍵が同一物になる。
3. **制御プレーンの保存物を Application 面と同居させてはならない。** 制御 DB は各 Application の DB ロールパスワードを平文で保持し、同居するプロセスから読める。Application 面の欠陥ひとつで全 Application の DB 認証情報が抜ける (SI-12、SI-00)。

副次的に、credential 記録が Application に対して `ondelete=CASCADE` であるため、Application 削除時に credential の記録ごと消え監査の連結が切れる (上記「削除は対象外」の根拠)。

### 新規 invariant は不要

上記の失敗はいずれも既存 invariant に分解できる。必要なのは新しい invariant ではなく**新しい conformance 条件**である。

- application credential が全ての control endpoint に対して fail closed であること
- control credential が data/schema endpoint で拒否されること
- bootstrap を再実行して二本目の「最初の credential」を作れないこと (明示的な reset を除く)
- 制御操作が正準の監査イベントを発行すること (`audit.sink_failure_policy` が既に control-plane 変更を fail-closed としている)
- 「分離して配備可能」は振る舞いテストではなく設計証拠 (review evidence) として審査すること

in-band 発行の採否 (案A/案B) により conformance 条件は追加される。

### bootstrap — endpoint ではなくライフサイクル条項として

最初の control credential だけは帯域外にならざるを得ない (発行する権限を発行する経路が存在しないため)。機構は各 peer の自由 (CLI、初期化ジョブ、その他) とし、契約には次を条項として置く。

- 運用者 / OS 権限のもとで実行され、公開 HTTP 面から実行できないこと
- 既定値やハードコードされた credential が存在しないこと
- control credential が既に存在する場合、明示的な reset なしには再実行できないこと (reset の意味論は上記)
- 正準の監査イベントを発行すること
- 初回 credential が恒久化しないこと (期限またはローテート強制。機構は自由)

### 両 peer 適用可能性

いずれの peer も Application 登録と credential 発行の内部機構を既に持つ (r2db-api の `ControlAuthority`、MitateDB-api の `ControlPlane`)。公開経路の形状を契約で規定するのみで、内部実装と提供可否は各 peer に委ねられる。

### 採用時期 — 三つの選択肢を依頼者判断として残す

本要求の実装には、本契約の r2db-api において credential の永続化 (現在 `CredentialStore` はメモリ上の辞書) と composition root (モジュールレベルの ASGI app が無い) が先行する。第2版は「この前提条件は採用を延期する理由にはならない」と断定したが、これはレビューが不確実と明示した判断を断定に変えたものであり、改める。

1. **全体をいま採用する** — 乖離の見込みを断ち、前提作業 (credential 記録の形、ライフサイクル状態、bootstrap) が契約に沿って行われる。ただし endpoint 形状を運用経験なしに固定する
2. **安全条項のみ先に採用し、endpoint 形状は保留する** — bootstrap 規則・分離配備可能性・共有秘密の禁止・個別失効可能性は運用経験に依存しないためいま採用でき、パス・動詞・req/res 形状は peer がプロセスとして起動できるようになってから確定する
3. **全体を延期する** — 統治下の公開面の乖離は現にゼロであり、緊急性は見込みに基づくため

---

## CCR-15 — entity をまたぐ atomicity

### 要求

複数の entity にまたがる mutation を、ひとつの atomic な単位として実行できる形を共通契約に定義する。**リクエスト形状は機構ではなく契約であり、本版で形状を提案する** (第2版は形状を欠き、変更要求になっていなかった)。

```
POST /v1/data/mutations        auth=runtime or developer
```

- リクエストは `MutationRequest` と同形だが、**各 `Mutation` が必須の `entity` フィールドを持つ**
- batch 全体がひとつの atomic 単位である。本 endpoint に `best_effort` は定義しない (部分結果の意味論を entity をまたいで定義する必要が生じるまで導入しない)
- 既存の `/v1/data/{entity}/mutations` は無変更 (そこでの `Mutation` は `entity` フィールドを持たない)
- **レビュー指摘 (Opus, 第3版に対して)**: 上記は新しい定義 (例 `ScopedMutation`) を要し、既存の `Mutation` に `entity` を追加してはならない。`Mutation.additionalProperties` は `false` であり、共有定義に `entity` を足すと per-entity endpoint でも body の `entity` が受理されうる。path の entity と body の entity が競合する状態は、**C-01 の `request_field_scope` が防ごうとしている当の攻撃面**である。契約には「per-entity endpoint は body の `entity` を引き続き拒否する」と明記すること
- Capability は `cross_entity_mutation` として `capability_status` で申告し、提供しない実装は `CAPABILITY_UNSUPPORTED` で拒否する

実装がどう atomicity を実現するか (単一トランザクション、WAL、その他) は自由である。自由でないのはリクエスト形状と、次の排除である。

### 明示的に排除するもの — 対話的トランザクション

begin / commit をクライアントの往復にまたがって保持する対話的トランザクション面は**定義しない。本契約 v1 の atomic 単位は単一リクエストに限る。** ロックと接続をクライアントの往復にまたがって保持することは、敵対的クライアントに資源保持を許す SI-08 の危険であり、「堅牢と安全が第一」の軸から排除する。

### 問題

現行契約の mutation 経路は `POST /v1/data/{entity}/mutations` であり、**atomic な batch は単一 entity に閉じる。** `transactions.atomic` は「宣言された atomic 単位の全操作が同時に commit するか、外部から見える部分状態を残さない」と定めるが、その単位を entity をまたいで構成する手段が無い。

### 証拠

現行クライアントの `lib/actions/line_binding_relink.php` は、複数テーブルにまたがる更新に対して補償処理 (saga) を手書きしている。コード内のコメントが理由を明記している。

> r2db has no multi-row transaction, so relink keeps a state row and compensates every successful patch on error.

同様の構造は `lib/actions/month_import.php` の delete-then-insert による置換にも現れる。

**本契約どおりに実装しても、このクライアントは補償処理を書き続けることになる。** 単一 entity の atomic batch では足りないためである。

なおこの証拠は第1版において CCR-13 の証拠欄に置かれていた。誤りである。saga が示すのは行の同一性の欠落ではなく、entity をまたぐ atomicity の欠落である。

### Security Invariants との関係

SI-11 (Atomic Integrity) の適用範囲が広がるのみで、新たな invariant は不要と考える。SI-08 に関しては、またぐ entity 数と操作数に有限の境界を要求する。`limits.classes` に entity 数の class (例: `batch_entities`) を追加し、値は配備 profile とする。操作数は既存の `batch_items` が引き続き束ねる。

### 両 peer 適用可能性

いずれの peer も、**ひとつの Application の保存スコープ内で**複数 entity にまたがる atomic 単位を構成できる。契約は peer の topology を断定しない (SI-00 が containment を要求し topology を要求しないのと同じ理由による。第2版は r2db-api の topology を本欄で断定しており、事実としては正しかったが記述として不適切であった)。

**Application をまたぐ atomicity は要求しない** (SI-01 の分離と両立しない)。

---

## 第2版の誤りの訂正 (記録として保持)

- **CCR-13: 無条件の普遍的 addressability は新しいゲートであった。** 再計算される読み取り専用 entity (外部表の透過、集計) はどの機構でも安定した識別子を持てず、「新しいという理由で」塞がれる。機構の自由はこれを救わない — 塞いでいたのは要求の普遍性である。可変 entity へスコープを絞った
- **CCR-13: revision の被参照先を、問題として指摘しながら固定していなかった。** 5条項で固定した
- **CCR-13: SQLite rowid の引用が自らの結果を満たしていなかった。** `INTEGER PRIMARY KEY` でない rowid は `VACUUM` で振り直される (実測確認済み)
- **CCR-14: 「三実装が三様」の数え方が誤り。** 統治下の公開面の乖離はゼロであり、見込みの問題として論じ直した
- **CCR-14: 採用延期の選択肢を断定で消していた。** 三案として依頼者に戻した
- **CCR-15: 形状を提案しておらず、変更要求になっていなかった。** リクエスト形状は機構ではなく契約であり、「機構は自由」を不完全さの言い訳に使っていた

## 未決事項 (依頼者判断)

- CCR-13: `MutationResult` の拡張を v1 で行うか。サーバ側採番の識別子を返す唯一の応答形状変更である
- CCR-14: 採用時期 — 全体採用 / 安全条項のみ先行 / 全体延期 の三案
- CCR-14: control credential の in-band 発行 — 案A (発行も in-band) / 案B (発行は帯域外の儀式)
- CCR-14: base path を `/control/v1` として `/v1` から分けることの確認
- CCR-15: `batch_entities` の境界値と、その enforcement layer の申告方法
