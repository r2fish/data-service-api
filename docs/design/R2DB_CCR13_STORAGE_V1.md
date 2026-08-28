# r2db-api CCR-13 storage (型付き列・区分宣言・addressability・revision) 設計 v1

- 起票日: 2026-08-28
- 版数: 1.1 (WP-0 独立レビュー (Opus) の blocker 3件・major 10件・minor 10件を反映。§8 訂正記録参照)
- 設計: Fable (監督・設計担当)。実装: Sonnet subagent、レビュー: Opus subagent
- 対象: `docs/work-orders/HANDOVER_20260828_FABLE.md` §2 フェーズ1 — 契約 1.1.0 の CCR-13 採用内容を r2db-api の storage に実装し、対応する conformance 条件を登録・実行可能化する
- 前提文書: `spec/data-service-api.v1.json` (1.1.0)、`spec/CCR_DISPOSITION.md`、`r2db-api/contracts/COMMON_CONTRACT_CHANGE_REQUEST.md` 第4版、`docs/design/R2DB_SERVICE_LAYER_ARCHITECTURE.md`、`docs/design/CONFORMANCE_ADAPTER_V1.md` (port v1.1)

## 0. スコープ

実装するもの:

1. `field_type` の型付き列化 (`add_field`)
2. catalog の区分宣言 (`mutation_class` / `address_fields` / `address_reuse` / `unique_keys`) の公開
3. 一意性: `create_index` (+ `unique`) / `drop_index`
4. `upsert` の再有効化 (宣言済み一意性を存在判定に用いる)
5. `expected_revision` (revision precondition、契約の6条項) と `QueryResult.revisions`
6. `MutationResult.assigned_addresses`
7. `order_by`
8. cursor pagination (`page.cursor` / `next_page`)
9. conformance 条件 C-17 (区分・addressability・一意性の宣言と実挙動の一致)、C-18 (revision precondition 意味論) の登録と、3 adapter での実行可能化 (port v1.2 の coordinated design revision、既存 fixture / C-12 の同時改訂を含む)

非スコープ (フェーズ1に含めない):

- **NOT NULL / DEFAULT の宣言**。契約 1.1.0 に語彙が無い。CCR 文書自身が「本要求はスキーマ表現力の欠落の第一項であって、最後の項ではない」と明記しており、勤務表移行にはこの追加契約変更が別途必要になる (依頼者へ申し送り)
- `idempotency_key` (capability `idempotency`)。現行どおり `CAPABILITY_UNSUPPORTED` で拒否を維持
- `alter_field`。`CAPABILITY_UNSUPPORTED` を維持 (capability_status 規則上、optional target operation の unavailable は適法)
- catalog への field 型の公開。`EntityDescriptor` に型情報の語彙が無い (将来の additive 契約変更候補として申し送り)
- (初版で非スコープとした `contains` の扱いは Q-2 裁定で**スコープ入り**した: `contains` のリテラル化 + `matches` 追加。契約反映済み。実装は WP-3 で r2db 両 cell、MitateDB のエスケープ修正 + `matches` 正直拒否も同時。C-03 probe は WP-5。契約反映から WP-3 までの間、r2db は `matches` を `VALIDATION_FAILED` で拒否する窓が生じる — 未配備ブランチ内のため許容し、WP-3 で実装へ)
- MitateDB-api の新機能実装。同 peer は 1.1.0 を申告しつつ新 capability を unavailable と申告済み。フェーズ1で必要なのは「unavailable 側の正直な拒否」の証拠が C-17/C-18 に載ることのみ (§4 の structurally_absent)
- cross-entity endpoint (`POST /v1/data/mutations`) — CCR-15 はフェーズ外。ただし `MutationResult` の共通形状 (assigned_addresses の `entity` 項目) は将来を塞がない形にする

## 0.5 依頼者裁定待ちの契約論点 (実装は拒否側の暫定で先行する)

| # | 論点 | 暫定 (本フェーズの実装) | 裁定後の変化 |
|---|---|---|---|
| Q-1 | **unique key が2つ以上の entity への upsert** (WP-0 レビュー B-3)。契約 `structured_operations.upsert` は拒否条件を「key 未宣言」「mutable 区分でない」の2つしか列挙せず、多キー時の存在判定は未定義。実装が独自に決めるのは CCR-13 が是正した欠陥の形の再発 | **裁定済み (2026-08-28): 案B。** `Mutation` / `ScopedMutation` に任意フィールド `unique_key` (catalog の `unique_keys[].name` を参照) を追加し、判定キーを名指しする。キー1つなら省略可 (既定)、複数キーで省略は `VALIDATION_FAILED`、未宣言キー名は `NOT_FOUND`、upsert 以外への付与は `VALIDATION_FAILED`。契約 1.1.0 (main 未マージ) への公開前追補として織り込み済み。記録: `spec/CCR_DISPOSITION.md` 従属判断 4 | — |
| Q-2 | **`contains` の意味定義** (WP-0 レビュー M-10)。契約は operator 名を列挙するのみで意味が無く、ワイルドカード解釈が実装ごとに分岐しうる | **裁定済み (2026-08-28): 案i + 補足案。** `contains` は「リテラル部分一致 (ワイルドカード解釈なし)」と契約に明記し、同時にパターン一致演算子 `matches` (`%` = 任意列、`_` = 任意1文字、`\` エスケープ) を additive 追加する — 一般的に期待される能力は最初から普通に提供する (依頼者言明)。**両演算子とも大文字小文字を区別** (peer 間分岐の封鎖。区別しない検索は将来の additive 演算子)。提供しない実装の `matches` は `CAPABILITY_UNSUPPORTED` の正直拒否。反映は WP-2 是正コミット後の専用コミット (契約 + 裁定記録 + r2db 両 cell + MitateDB エスケープ修正 + C-03 probe) | — |

(旧注記「C-17 は多キー upsert の挙動を検査しない」は Q-1 裁定により失効 — C-17 は案B の選択規則を検査する。)

## 1. 設計判断 (実装ポリシー。契約変更ではない)

### R-1: r2db-api の全 entity は `mutable` 区分・サーバ採番 `id` アドレス・`address_reuse: never`

契約は catalog が区分を**宣言する**ことを要求するが、宣言がどう決まるかは機構自由 (`SchemaOperationRequest` に区分を渡す口は意図的に無い — MitateDB のように実装がコードで宣言する peer があるため)。r2db-api の方針:

- `create_entity` が作る全テーブルに `id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY` と `_r2db_revision uuid NOT NULL DEFAULT gen_random_uuid()` を付与する
- 全 entity を `mutation_class: "mutable"`、`address_fields: ["id"]`、`address_reuse: "never"` として catalog に公開する
- クライアントは区分を選べない (append_only 等の宣言はできない)。mutable は全 mutation を支持する区分なので、これは能力の制限ではなくガードレール宣言の粒度の制限である
- **宣言の完全性ガード (fail-closed)**: `_load_catalog` は各 entity テーブルが `id` (bigint, identity) と `_r2db_revision` を実際に持つことを検証し、持たないテーブルが1つでもあれば大きく失敗する (`SERVICE_UNAVAILABLE`、entity 名のみの安全診断)。契約 `declaration_required` は「宣言できない entity が1つでもあれば capability を enabled と申告してはならない」と定めており、静かに偽の宣言 (実際には可視・照準・不変を満たさない `id`) を出すことが最悪の違反になる。実配備は未実施でこの形のテーブルは存在しないため、移行手当ては不要 (pre-CCR13 のテスト残骸は作り直し)
- `address_reuse: "never"` の射程は **entity の生存期間内** (`drop_entity` → 同名 `create_entity` は新しい entity であり、採番は 1 から始まる)。catalog 説明と §5 の review evidence に明記する
- 性質5 (自発的再割当ての禁止) と `never` の根拠: `GENERATED ALWAYS` + 公開 API での `id` 指定拒否 (R-3) により identity sequence は逆行しない。VACUUM / pg_dump リストアは格納済み値と identity 状態を保存する。sequence を巻き戻す面 (`ALTER SEQUENCE` 等) は公開 API に存在しない
- 採番識別子の非推論条項 (契約 `assigned_identifiers`): application ごとに別 database・entity ごとに別 identity sequence なので、値・増分は Application スコープ内で閉じる。§5 の review evidence に記録

**根拠**: (a) 唯一の実クライアント (勤務表、18テーブル全て `id` 主キー) の形と一致する。(b) 区分宣言を永続化する新カタログテーブルが不要になり、「実テーブル定義 (information_schema) が catalog の唯一の真実」という現行設計 (二段階識別子防御) を保てる。

**再検討条件**: クライアントが read_only / append_only のガードレール宣言を必要と実証した場合。`create_entity` に区分を渡す口は契約の additive 変更 (依頼者裁定要) + 実装拡張で後から足せる。

### R-2: `field_type` は `add_field` 専用。型指定なしは従来どおり JSONB

`SchemaOperationRequest` は `field_type` (単数) と `fields` (配列) を持ち、create_entity で複数フィールドへ型を個別指定する形が契約に無い。方針:

- `add_field` + `field_type` → 型付き列 (`string→text`, `integer→bigint`, `number→double precision`, `boolean→boolean`, `object→jsonb`, `array→jsonb`)
- `add_field` で `field_type` 省略 → JSONB (従来挙動の保存 = additive)
- `create_entity` + `field_type` → `VALIDATION_FAILED` を**維持** (現行挙動: `_SCHEMA_KEYS` に `field_type` が無く既に `VALIDATION_FAILED`。初版の「現行は受理して黙って無視」は事実誤認だった — 訂正記録 m-1。維持なので additive 影響なし)

型付き entity の作成手順は「`create_entity` (fields なし可) → `add_field` × N」となる。冗長だが契約の語彙内であり、クライアントは AI エージェント前提 (裁定済みの設計前提) なので手順コストは低い。

**再検討条件**: create_entity での一括型指定が必要と実証されたら、契約の additive 変更として審査。

### R-3: 予約名 — `id` と `_r2db` prefix

- `create_entity` / `add_field` は、フィールド名 `id` および `_r2db` で始まるフィールド名・entity 名を `IDENTIFIER_INVALID` で拒否する (契約の「implementation may apply a stricter known-catalog policy」の範囲内)
- `insert` / `upsert` の values に `id` があれば `VALIDATION_FAILED` (アドレスはサーバ採番)。`update` の values に `id` があれば `VALIDATION_FAILED` (性質4: アドレス不変)。where / order_by / select での `id` 参照は自由 (性質2・3)
- `id` は catalog の `fields` に**含める** (性質2: visible。ordinary selectable field)
- `_load_catalog` の内部列除外は `_r2db` **prefix 一致** (従来の `_r2db_schema_revision` 完全一致から拡張)
- in-memory `ApplicationCell` も**同じ名前** (`id` 可視・`_r2db_revision` 不可視) を使う。cell 固有の内部名 (`_id` 等) を発明しない — 予約規則が両 cell を同時に覆い、公開面が一致する (訂正記録 M-9)
- **既存 conformance fixture との衝突 (訂正記録 B-1)**: 現行3 plug の `build_fixture` は `id` という通常フィールドを seed に使っており、この予約で壊れる。§4 の WP-1 で fixture のフィールド名を改める (coordinated revision)。port は「`id` は peer により予約されうる」を文書化する

### R-4: revision は行ごとの不可視列 `_r2db_revision`

- 全 entity テーブルに `_r2db_revision uuid NOT NULL DEFAULT gen_random_uuid()` (PostgreSQL 13+ 組み込み。配備前提に PostgreSQL 13+ を明記)
- insert 時は DEFAULT、update / upsert の update 経路では `SET _r2db_revision = gen_random_uuid()`。行への mutation の commit ごとに必ず変わり、他行では変わらない (6条項の 3・4)
- catalog の `fields`・`select` 可能フィールドから除外。クライアントへは `QueryResult.revisions` (items と index-aligned、文字列化した uuid) でのみ渡す。capability `revision_preconditions: enabled` を申告する以上、全 entity が mutable 区分なので **query 応答は常に revisions を含める**
- 比較の原子性 (6条項の 5): `UPDATE/DELETE ... WHERE <述語> AND _r2db_revision = $expected` の単一文で行う
- **集合意味論の明示 (訂正記録 M-2)**: `expected_revision` 付き mutation の対象は「述語一致 ∧ revision 一致」の行である。revision は行ごとに一意 (uuid) なので、述語が複数行に一致しても**変更されるのは高々 revision の指す1行** — precondition は「既知の既存行の主張」(契約) であり、revision 自体が行を固定する。これを C-18 の条件に含める (述語3行一致 + revision 1行分 → affected 1)
- 失敗の割り当て (6条項の 6): 変更 0 行のとき同一トランザクション内で `SELECT EXISTS(<述語>)` を再評価し、存在すれば `PRECONDITION_FAILED`、無ければ `NOT_FOUND`。`expected_revision` 付き insert は `VALIDATION_FAILED`。`expected_revision` なしの 0 行 update/delete は従来どおり成功 (affected 0)
- **空 values の update (訂正記録 M-1)**: 現行 `_update` は空 values で書き込みをせず一致件数を返す。この分岐に `expected_revision` が入ると precondition が黙殺される。**空 values + `expected_revision` は `VALIDATION_FAILED`** (precondition は変更を伴う操作の主張)。空 values のみ (precondition なし) は従来挙動を維持
- 順序 (訂正記録 m-5): destructive 確認の検査 (`DESTRUCTIVE_CONFIRMATION_REQUIRED`) は precondition 評価より**先** (SI-09 の failure-before-execution。確認の無い delete は precondition を評価する前に拒否される)。C-18 に明記

### R-5: `create_index` / `drop_index` と upsert の存在判定

- `create_index`: `index` (名前) + `fields` (1〜16) + `unique` (bool、省略時 false)。物理 index 名は `{entity}__{index}` (二重下線区切り)。**クライアント index 名に `__` を含むものは `VALIDATION_FAILED`** (物理名の逆写像を一意に保つ — 訂正記録 m-2)。合成名が 63 バイトを超える場合は `VALIDATION_FAILED`。同名 index の存在は `CONFLICT`、対象 entity / フィールド不存在は `NOT_FOUND`。`unique: true` は `CREATE UNIQUE INDEX`。既存データが一意性に違反していれば `CONFLICT`
- **エラー写像の非開示 (訂正記録 M-5)**: PostgreSQL の UniqueViolation 等を `CONFLICT` に写像する際、DETAIL・制約名・行値は一切伝播させない。`message` は固定文言、`details` は高々 `{"field": <クライアント名>}` / `{"index": <クライアント名>}`
- `drop_index`: **SI-09 の destructive 確認を必須とする** (`destructive: true` + 有効な confirmation。`drop_entity` と同じ扱い)。初版は「データを破壊しないので不要」としたが、unique index の削除は (a) 性質3 の `CONFLICT` ガードレールを外し、(b) upsert を無言で `CAPABILITY_UNSUPPORTED` に変え、(c) 重複データ流入後は再作成不能 (事実上不可逆)。SI-09 の適用範囲 (schema/object deletion) に該当する (訂正記録 M-6)。`security/CONTROL_MAPPING.md` の SI-09 行に反映
- `create_index` は `schema_objects` 上限に**算入する** (SI-08。index は実資源であり、書き込み経路の検査コストも index 数に比例する)。`drop_index` で減算。index 名にも `_r2db` prefix 予約を適用 (`IDENTIFIER_INVALID`)
- `create_index` の `fields` に **アドレスフィールド (`id`) を含むものは `VALIDATION_FAILED`** — アドレスは domain 一意性宣言ではない (§2)。これを許すと「catalog に載るが upsert では原理的に使えない unique key」(values.id 禁止と矛盾) を peer が publish でき、C-17 の positive control が成立しなくなる (WP-2 レビュー M-5)
- catalog の `unique_keys`: `pg_index` から entity ごとの unique index を導出し、`{name: <クライアント名 (prefix を剥がす)>, fields: [...]}` で公開。`id` の PRIMARY KEY はアドレスであって domain 一意性宣言ではないため **unique_keys には含めない**
- **upsert の判定キーは Q-1 裁定 (案B) に従う**: unique key 0 個の entity は契約どおり `CAPABILITY_UNSUPPORTED`。1 個なら `unique_key` 省略可 (そのキーに既定。明示指定も可)。2 個以上は operation の `unique_key` フィールドでキー名を名指しし、省略は `VALIDATION_FAILED`。catalog に無いキー名は `NOT_FOUND`。`unique_key` を upsert 以外の operation に付ければ `VALIDATION_FAILED`
- upsert の values は**選択されたキー**の全フィールドを非 null で含むこと (`VALIDATION_FAILED`)。**upsert に `where` が付いていれば `VALIDATION_FAILED`** (存在判定は宣言済み key であり、述語を黙殺しない — 訂正記録 M-3。現行 bind_mutation の「upsert は where 必須」は逆転する)
- 実行は2文構成 (訂正記録 M-4 — `xmax` 系の未文書挙動に依存しない):
  1. `INSERT ... ON CONFLICT (<key fields>) DO NOTHING RETURNING id` → 行が返れば insert に解決 (assigned_addresses へ)
  2. 0 行なら `UPDATE ... SET <非 key の提供フィールド>, _r2db_revision = gen_random_uuid() WHERE <key eq> RETURNING id` → 0 行なら並行変更として `CONFLICT` (atomic batch ごと rollback)
- upsert + `expected_revision`: ON CONFLICT を使わず「`UPDATE ... WHERE <key eq> AND _r2db_revision = $expected`、0 行なら EXISTS で `PRECONDITION_FAILED` / `NOT_FOUND` を割り当てる」(6条項の 6: precondition は既存行の主張であり、insert への解決で黙殺しない)

### R-6: `order_by` と pagination

- `order_by`: 検証済み識別子 (catalog 照合。未知フィールドは select/where と同じく `NOT_FOUND` — 訂正記録 m-6) + `asc`/`desc` の固定リテラルで `ORDER BY` を合成。決定性のため、`id` が並び順に含まれない場合は末尾に `id ASC` を暗黙追加
- pagination は offset cursor: `page.cursor` は base64url(JSON `{"o": <offset>, "q": <query 形状ハッシュ>}`) の不透明文字列。`q` は (entity, select, where, order_by, size) の正規化ハッシュで、**ページ間で query 形状が変わった cursor は `VALIDATION_FAILED`** (静かなずれを許さない — 訂正記録 m-3)。復号不能・型不正・負値・上限 (10^9) 超の offset も `VALIDATION_FAILED` (PostgreSQL エラーまで到達させない)
- `LIMIT size+1` で続きの有無を判定し、続きがあれば `next_page` に offset+size の cursor、なければ null
- cursor は権限を運ばない (自 Application のデータ内の位置情報のみ)。改竄は自分の結果ページがずれるか `VALIDATION_FAILED` になるだけで越境しない (C-01 の範囲に変化なし)
- 順序の意味論 (WP-2 レビュー M-6/M-B で確定。両 cell が同一であること): NULL の位置は PostgreSQL 既定に合わせる (asc は末尾、desc は先頭)。untyped (JSONB) 列の**非 null 値**の型跨ぎ順序は PostgreSQL jsonb の順序 (`Object > Array > Boolean > Number > String`) に合わせる。JSON null は R-7 の規則により SQL NULL として保存されるため「jsonb null の順位」は発生しない。型付き列は R-7 により単型なので null 位置のみが効く
- `order_by` に同一フィールドが重複していれば `VALIDATION_FAILED`。`order_by` 句数は `query_complexity` に算入する
- cursor の形状ハッシュは application scope と entity を含める。なおハッシュは「同一 query の続きである」ことの確認であり、完全性や権限の検査ではない (cursor は offset 位置情報のみを運ぶ)
- `page.size` の上限は既存 `result_items` 上限と同一。`order_by` 句数の上限は契約どおり 10

### R-7: 型付き列の値検証とバインド

- 書き込み・述語の値は列型に対して検証してからバインドする: `bigint` ← JSON 整数 (bool は拒否)、`double precision` ← JSON 数値、`boolean` ← JSON 真偽、`text` ← JSON 文字列、`jsonb` ← 任意 JSON。型不一致は `VALIDATION_FAILED` (安全診断: field 名と期待型のみ。値は echo しない)
- `in` の値リストは**要素ごと**に同じ型検証・native バインドを行う (訂正記録 m-7)
- **値域検証も共有境界で行う** (WP-3 レビュー blocker-2): `integer` は bigint の値域 (±2^63)、文字列・jsonb・`expected_revision`・パターンは U+0000 を含まないこと。違反は `VALIDATION_FAILED`。これらは `_check_type` を通るのに PostgreSQL が実行時に拒む値であり、放置すると決定的なクライアントバグが `SERVICE_UNAVAILABLE` (= 再試行せよ) に化ける。防御第二層として postgres 側は 22xxx (DataError 系) を包括 `SERVICE_UNAVAILABLE` の手前で `VALIDATION_FAILED` (field 名のみ) に写像する
- **`matches` パターンの文法検証も共有境界で行う**: 末尾の裸 `\` は `VALIDATION_FAILED` (契約に明文化済み — PostgreSQL LIKE では格納データ依存の実行時エラーになるため)
- **`field_type: object` / `array` は PostgreSQL 側で DOMAIN 型 (`_r2db_json_object` / `_r2db_json_array`、`jsonb_typeof` CHECK 付き、application DB provision 時に作成) として列化する** (WP-3 レビューの対案採用)。`_load_catalog` は `information_schema.columns.domain_name` から宣言型を復元し、書き込み時の dict/list 検証は Python 側 (`_check_type`) が `VALIDATION_FAILED` (field 名のみ) で行う — ApplicationCell と同一写像。DOMAIN の CHECK は多層防御であり、発火は真のサーバ側不変条件破れとして 503 でよい。CHECK 制約名の合成 ({entity}__{field} 形式) は 63 バイト超過で逆写像が壊れ、CheckViolation の DETAIL に行全体が載るため不採用
- **述語意味論は SQL (PostgreSQL) 側に統一する** (WP-3 レビュー D-1〜D-4): `contains`/`matches` は NULL 行を単に除外する (エラーにしない)。型付き非文字列列にも text 表現で適用可。`ne` / `in` は SQL 三値論理 (NULL 行は一致しない)。ApplicationCell を PG 意味論に合わせる — 参照実装が配備実体より狭い/違う挙動をしてはならない
- **`eq` / `ne` の述語値に JSON null を渡すことは `VALIDATION_FAILED`** (null 判定は `is_null` を使う。SQL では `= NULL` / `<> NULL` は常に UNKNOWN で空集合になるが、黙って常に空を返すより明示拒否が AI エージェントに診断的 — WP-3 確認レビュー N-3)
- **`contains`/`matches` の text 表現は PostgreSQL の出力規則に一致させる** (WP-3 確認レビュー N-1/N-2): float は整数値なら `.0` を落とす (PG `float8out` 準拠)、jsonb オブジェクトのキー順は (キー長, バイト順)。parity テストはこの表現差が最も壊れやすい値 (整数値 float・キー長混在 dict・"on"/"No" 等 `str(None)` に含まれる部分文字列) で固定する
- null は全列で許容 (NOT NULL は非スコープ)
- **untyped (JSONB) 列への JSON null は SQL NULL としてバインドする** (`jsonb 'null'` を作らない — WP-2 確認レビュー M-B。これを守らないと `is_null` 述語と order_by の null 位置が両 cell で割れる。実 PostgreSQL で実測確認済み)。それ以外のバインドは型付き列では native パラメータ、JSONB 列では従来どおり `Jsonb(...)`。**値が生 SQL に入る経路を新設しない** (既存の `_run` チョークポイントと `sql.*` 合成のみを使う)。ORDER BY / OFFSET / LIMIT の数値はサーバ側計算値のみを `sql.Literal` 化 (既存 LIMIT と同型)
- **値の型検証は precondition 解決・対象行の探索より前に行う** (failure-before-execution。型不一致 = クライアントのバグを `PRECONDITION_FAILED` = 再試行指示として返すと、AI エージェントクライアントは成功しない再試行ループに入る — WP-2 レビュー M-9)
- `register_application(entities=...)` の seed 行も通常の insert 経路を通し、id / revision の採番を受ける (訂正記録 m-9)

## 2. catalog 導出 (R-1 の帰結)

`_load_catalog` は従来どおり information_schema (+ pg_index) だけから導出する。新カタログテーブルは作らない。

```
EntityDescriptor = {
  entity, fields (id を含む。_r2db prefix 列は除外),
  mutation_class: "mutable", address_fields: ["id"], address_reuse: "never",
  unique_keys: [{name, fields}]  (unique index 由来。PRIMARY KEY は除く)
}
```

導出には R-1 の完全性ガードが先行する (id / _r2db_revision を欠く entity があれば fail-closed)。

in-memory `ApplicationCell` (参照実装・in-process conformance plug の実体) も同一の宣言・意味論・エラーコードを実装する。二つの cell の公開面の一致は C-17/C-18 が3 adapter で走ることで検証される (fixture がこの面を実際に踏むよう §4 で保証する)。

## 3. service / HTTP 面の変更

- `StorageBackend` Protocol: `query` の戻りを `(items, revisions, has_more)` 相当へ、`transact` の戻りを `(affected, assigned_addresses)` 相当へ拡張 (具体形は実装で決めてよいが、両 cell と service/http が同じ形を使うこと)
- `http.post_query`: `order_by` / `page.cursor` の拒否を撤去し委譲。応答は `{items, next_page, revisions}`
- `http.post_mutate`: `expected_revision` の拒否を撤去 (`bind_mutation` で受理・検証)。応答は `{committed, affected, assigned_addresses}` (per-entity endpoint では各要素は `{address: {...}}`、`entity` 項目なし、insert (と insert に解決した upsert) の操作順)。`idempotency_key` の拒否は維持
- **WP-2〜WP-5 の乖離封鎖 (暫定ゲート)**: 共有 bind 境界の語彙受理は、放置すると申告 (`unavailable` / `unsupported`) のまま実挙動だけが公開面に開く (WP-2 レビュー B-1 — C-12 は「申告 enabled ⇒ 実行可能」の向きしか検査せず、逆向きの乖離はどの条件も捕まえない)。よって `DataService` (全 facade の共通点) に暫定ゲートを置き、`expected_revision` / `upsert` / `create_index` / `drop_index` / `field_type` / `matches` を `CAPABILITY_UNSUPPORTED` で、catalog の宣言フィールド (`mutation_class` / `address_fields` / `address_reuse` / `unique_keys`) を旧形状への絞り込みで、**申告が更新される WP-5 の同一コミットまで**封鎖する。storage 固有の事実 (catalog `fields` への `id` の出現、予約名) は capability 非依存であり WP-2 から見えてよい
- `capabilities()` の申告更新 (**WP-5 で C-17/C-18 が green になるのと同一コミットで行う** — C-12 が申告と実挙動の一致を強制するため、実装が先・申告が後):
  - `structured_query: enabled` (order_by / pagination が実行可能になったため)
  - `atomic_mutation`: `upsert` を operations に戻す (`unsupported` から除去)。upsert の可否が entity の宣言状態 (unique_keys) に依存する旨は catalog が伝える (C-12 の positive control は §4 の改訂で「key を宣言した entity」上で行う)
  - `schema_operations`: `create_index` / `drop_index` を operations へ。`unsupported` は `["alter_field", "jobs"]`
  - `row_addressability: enabled` / `revision_preconditions: enabled`
  - `idempotency` / `best_effort_transactions` / `cross_entity_mutation` / `control_plane` は unavailable のまま

## 4. conformance — 条件登録・port v1.2・既存資産の同時改訂

開発順序 (契約 → conformance → 実装) に従い、条件の登録と port 改訂を実装より先に確定する (実行可能化は r2db 実装後)。

### 既存資産の coordinated revision (WP-1。訂正記録 B-1 / B-2)

`CONFORMANCE_ADAPTER_V1.md` §11 の手順で port v1.2 として一括改訂する:

1. **共通 fixture のフィールド名から `id` を退避** (例 `item_key`)。3 plug の `build_fixture` / seed / `test_c01` の `_PLACEHOLDER_FIELD` を同時に改める。port 文書に「`id` および実装予約 prefix は peer により予約されうるため、共通 fixture・probe はこれらを通常フィールド名として使わない」を明記。MitateDB は `id` を予約しないが、共通 suite が使わなければ足りる
2. **C-12 の upsert positive control の精密化**: 契約が upsert に前提 (宣言済み一意性) を定めた以上、正の対照は前提を満たした entity (unique index を1つ宣言) 上で行う。unique key の無い entity への upsert は C-17 の負側 (拒否) に移る
3. **port v1.2 の追加操作** (最小):
   - `attempt_mutation` に `expected_revision: str | None = None` を追加 (peer にそのまま伝える)
   - `create_unique_index(session, entity, index, fields)` — C-17 / C-12 改訂に必要
   - `query_with_revisions(session, entity, ...)` — `QueryResult.revisions` 相当の取得 (`select_eq` の拡張でも可)
   - `create_entity(fields: Mapping[str, str])` の**型指定を peer の型付き列へ実配線** (r2db plug は create_entity → add_field × N で写像。JSONB のまま型を捨てない — 訂正記録 M-8。ただし配線の有効化は r2db 実装が add_field + field_type を持つ WP-5)
   - 原則は不変: **adapter は peer の不足を埋めない。** peer が拒否したら拒否を返す。skip は fail
4. **unavailable 側の証拠形式 (訂正記録 M-7)**: MitateDB のように当該語彙を受理する面が構造的に無い peer では、plug が拒否を捏造してはならない。既存の `signature_forbids_parameters` 機構で「`expected_revision` / unique index 相当のパラメータがどの公開呼び出しにも存在しない」ことを構造的に証明する形を C-17/C-18 の負側の正当な証拠として CONDITIONS.md に書き分ける (「executable」と「structural evidence」を混同しない)

### C-17 宣言と実挙動の一致 (区分・addressability・一意性)

- `row_addressability` enabled peer: 全 entity が区分宣言を持つ (declaration_required の全数検査)。mutable entity は address_fields / address_reuse を持つ。アドレス列は select 可能で query 結果に現れる (性質2)。全アドレス eq は高々1行に一致する (性質3)。アドレス列を変更する update は `VALIDATION_FAILED` (性質4)。unique key 重複を作る書き込みは `CONFLICT`
- upsert: unique key 宣言が無い entity では `CAPABILITY_UNSUPPORTED`。宣言済み entity では実行され (キー選択は Q-1 裁定の規則: 1個なら省略可、複数なら `unique_key` 必須で省略は `VALIDATION_FAILED`、未宣言キー名は `NOT_FOUND`)、既存 key 一致で update、無ければ insert になり、insert 解決分だけが assigned_addresses に現れる
- 性質5 + `address_reuse: never`: 削除→再 insert でアドレスが再利用されないことの自動テスト (誘発可能な撹乱) + review evidence (R-1 の根拠、entity 生存期間スコープ、採番の非推論性を含む) の併用。契約の文言どおり
- unavailable peer (MitateDB): 区分宣言は要求されない。宣言に依存する操作の不在は structural evidence (§4 上記4)

### C-12 逆向き条件 (WP-5 で追加登録)

C-12 は「申告 enabled ⇒ 実行可能」の向きしか検査せず、「申告に無い操作・演算子が実行できてしまう」逆向きの乖離 (WP-2 B-1 / WP-3 blocker-1 が2度踏んだ形) を捕まえない。WP-5 で逆向き条件 (申告されない mutation 操作・query 演算子は `CAPABILITY_UNSUPPORTED` で拒否されること) を C-12 の拡張または独立条件として登録する。

### C-18 revision precondition 意味論

- enabled peer: (1) mismatch → `PRECONDITION_FAILED`、(2) 述語一致 0 行 + precondition → `NOT_FOUND`、(3) insert + expected_revision → `VALIDATION_FAILED`、(4) 自行 mutation 後に revision が変わる、(5) 他行 mutation で変わらない、(6) precondition なし 0 行 update/delete は affected 0 の成功、(7) query 応答の revisions が items と整合 (件数一致・行対応)、(8) upsert + precondition は insert に解決されない (key 不一致は `NOT_FOUND`)、(9) 述語が複数行に一致しても変更は revision の指す1行のみ (R-4 集合意味論)、(10) 空 values + precondition は `VALIDATION_FAILED` (黙殺経路の封鎖)、(11) destructive 確認の検査は precondition 評価に先行する
- unavailable peer: `expected_revision` を含む mutation の受理面が構造的に無いことの structural evidence (受理面を持つ peer なら実行前 `CAPABILITY_UNSUPPORTED` + 状態不変)

## 5. 実装順序 (work packages)

| WP | 内容 | 完了条件 |
|---|---|---|
| WP-0 | 本設計文書の独立レビュー (Opus) と反映 | 済 (§8) |
| WP-1 | `conformance-tests/` + 3 plug: fixture `id` 退避、C-12 upsert 対照改訂、port v1.2 (`CONFORMANCE_ADAPTER_V1.md` §11 手順)、C-17/C-18 の CONDITIONS.md 登録 (not yet executable。test ファイルは WP-5 まで書かない — 訂正記録 m-8) | 全既存 suite green (`test_conditions_register.py` 含む) |
| WP-2 | `structured.py` / `ApplicationCell` / `backend.py`: 語彙受理 (create_index/drop_index/field_type)、予約名、型検証、unique key、upsert 再有効化 (2文構成の in-memory 等価)、expected_revision (M-1/M-2/M-3 の分岐込み)、revisions、order_by、pagination、outcome 型 (frozen dataclass。revisions は items と同数、未維持は None — WP-2 レビュー M-10)。**WP-2 単独での実機配備は禁止** (PostgresCell は id 採番を持たず R-3 の予約だけが効くため、アドレス能力が片肺になる。実配備は WP-3 以降) | `test_foundation.py` 拡張 green |
| WP-3 | `postgres.py`: DDL (id identity・_r2db_revision・型 map)、完全性ガード、`ON CONFLICT DO NOTHING` + follow-up UPDATE、`RETURNING`、order_by/offset SQL、catalog 導出 (unique_keys)、エラー写像の非開示 | `test_postgres.py` 拡張 green (実 PostgreSQL) |
| WP-4 | `service.py` / `http.py`: 応答形状 (revisions / next_page / assigned_addresses)、拒否撤去 (order_by / cursor / expected_revision)。**申告更新はまだ行わない** | `test_http.py` 拡張 green |
| WP-5 | C-17/C-18 test 実装 + 3 adapter 実行可能化 + r2db plug の型配線 + `capabilities()` 申告更新 (同一コミット)、CONDITIONS.md status 更新、変異注入で検出力確認 (最低: 性質4検証を外す変異、precondition 黙殺変異 (空 values 分岐含む)、revisions 恒等文字列変異、各1つがテストを赤にすること) | 全 suite green + 変異が検出される |
| WP-6 | 文書更新 (README / `security/CONTROL_MAPPING.md` SI-09 行 (drop_index) / deploy 文書へ PostgreSQL 13+ 前提 / 本書への実装記録追記) と最終レビュー (Opus) | レビュー指摘の解消 |

各 WP の後に commit + push (r2fish 同一性確認を先行)。復元は scratchpad バックアップ経由 (`git checkout` 禁止)。

## 6. 申し送り (依頼者判断)

1. §0.5 Q-1 (upsert 多キー) / Q-2 (`contains` 意味) の裁定
2. **NOT NULL / DEFAULT の契約語彙追加** — 勤務表移行の残り前提。フェーズ1完了後の契約 additive 変更として起票するか
3. **catalog への field 型公開** — AI エージェントクライアントが型を知る手段が現状 discovery に無い。同上
4. **配備前提を PostgreSQL 13+ と明記** (`gen_random_uuid` 組み込み)。deploy 文書に反映する (WP-6)

## 7. リスクとレビュー重点

- 新しい SQL 合成面 (ORDER BY / OFFSET / ON CONFLICT / RETURNING / 型付きバインド) が「識別子は二段階防御、値はバインドのみ、実行は `_run` チョークポイント」を破っていないか
- `ApplicationCell` と `PostgresCell` の意味論乖離 (エラーコード含む)
- 契約 `errors.disclosure` 違反 (特に UniqueViolation / 型不一致の診断)
- precondition の黙殺経路の残存 (M-1 の類型)

## 8. 訂正記録 (WP-0 独立レビュー、Opus、2026-08-28)

blocker 3件・major 10件・minor 10件。全件を採り、以下のとおり反映した。

- **B-1**: R-3 の `id` 予約が既存 conformance fixture (3 plug が `id` を通常フィールドとして seed) と既存 `id JSONB` 列を破壊し、後者は偽のアドレス宣言 (declaration_required 違反) になる → §4 の coordinated revision (fixture 改名) と R-1 の完全性ガード (fail-closed) を新設
- **B-2**: upsert を operations に戻すと、unique key の無い entity で正の対照を取る現行 C-12 が赤になる。capability (サービス単位) と upsert 可否 (entity 単位) の写像が未決だった → C-12 の対照を「key を宣言した entity」上に改訂 (§4)、申告更新を WP-5 の同一コミットへ移動 (§3)
- **B-3**: 「unique key 2個以上で `CAPABILITY_UNSUPPORTED`」は契約の拒否列挙に無く、実装が独自に契約領域を閉じる形 (CCR-13 が是正した欠陥の再発) → §0.5 Q-1 として依頼者裁定へ。実装は拒否側の暫定 (additive に解除可能)
- **M-1**: 空 values update の precondition 黙殺 → R-4 で `VALIDATION_FAILED` に確定、C-18 条件 (10) と変異注入項目に追加
- **M-2**: 述語複数行一致時の意味論未定義 → R-4 で集合意味論 (revision が行を固定) を明示、C-18 条件 (9)
- **M-3**: upsert + where の扱い未定義 → `VALIDATION_FAILED` (R-5)
- **M-4**: `xmax = 0` は未文書挙動 → 2文構成 (ON CONFLICT DO NOTHING → follow-up UPDATE、0行なら CONFLICT) に変更 (R-5)
- **M-5**: UniqueViolation 写像の開示リスク → R-5 に非開示規則を明記
- **M-6**: drop_index の SI-09 未検討 → destructive 確認必須に変更 (ガードレール除去 + 事実上不可逆のため)。CONTROL_MAPPING 反映を WP-6 へ
- **M-7**: MitateDB 側 C-17/C-18 の拒否捏造リスク → structural evidence (`signature_forbids_parameters`) 形式を §4 に規定
- **M-8**: 型付き列が共通 suite を一度も通らない → port v1.2 で `create_entity` の型指定を実配線 (§4)
- **M-9**: `ApplicationCell` の内部名が予約の外 → 両 cell で同一名に統一 (R-3)
- **M-10**: `contains` の意味変更に契約根拠が無い → R-8 をフェーズから外し §0.5 Q-2 へ
- **m-1**: 「field_type は受理して黙って無視」は事実誤認 (現行も `VALIDATION_FAILED`) → R-2 を訂正。additive 影響なしに評価が変わった
- **m-2**: 物理 index 名の跨 entity 衝突 → index 名の `__` を `VALIDATION_FAILED` (R-5)
- **m-3**: cursor が query 形状を束ねない / offset 上限なし → 形状ハッシュ + 上限 10^9 (R-6)
- **m-4**: `address_reuse: never` の射程 → entity 生存期間内と明記 (R-1)
- **m-5**: destructive 確認と precondition の順序 → 確認が先 (R-4、C-18 条件 (11))
- **m-6**: order_by 未知フィールドのコード → `NOT_FOUND` (R-6)
- **m-7**: `in` の型付きバインド → 要素ごと検証 (R-7)
- **m-8**: WP-1 骨格テストが skip/fail どちらかになる → WP-1 は CONDITIONS.md 行 + port 改訂のみ、test は WP-5 (§5)
- **m-9**: seed 行の採番 → 通常 insert 経路を通す (R-7)
- **m-10**: 採番の非推論条項の根拠未記録 → R-1 に記録、review evidence へ

## 9. 訂正記録 (WP-2 実装レビュー、Opus、2026-08-28)

blocker 2件・major 13件・minor 8件。主な処置:

- **B-1**: 共有 bind 境界の語彙受理により、申告 unavailable のまま `expected_revision` / `create_index` / `upsert` / `field_type` / catalog 宣言フィールドが HTTP 面で実挙動化していた (C-12 は逆向きの乖離を捕まえない)。→ §3 の暫定ゲート (DataService 層) を新設し WP-5 まで封鎖。依頼者裁定は不要 (設計 §3 の「外部挙動不変」を実装が破った形であり、設計どおりに戻す是正)
- **B-2**: `unique_keys[].name` が optional のままでは、name 無しキーを宣言した entity への upsert が原理的に到達不能 (選択規則が満たせない)。→ 契約で `name` を required 化 (1.1.0 公開前追補)、C-17 の declaration_required に同旨を追加
- **M-1〜M-13 / minor**: R-5 (index の schema_objects 算入・id への unique index 禁止・`_r2db` prefix)、R-6 (NULL 位置・jsonb 型跨ぎ順序・重複 order_by・cursor scope)、R-7 (型検証の precondition 先行)、§5 (WP-2 単独配備禁止)、outcome 型の dataclass 化、insert + where の拒否、`index`/`unique`/`revision` キーの黙殺封鎖、CONFLICT の HTTP 409 統一、`spec/CCR_DISPOSITION.md` の旧記述訂正、テスト増補 (PostgresCell guard・null 一意性・他キー CONFLICT・cursor 負値/上限/非 dict・複合キー) に反映
- 契約追補の追加修正: 「キー0個 + `unique_key` 指定」は capability 検査がキー名解決に先行し `CAPABILITY_UNSUPPORTED`

## 10. 訂正記録 (WP-3 実装レビュー、Opus、2026-08-28)

blocker 2・major 4群・minor 数件。SQL 合成面 (識別子二段階防御・バインド境界・チョークポイント) は敵対プローブで健全を確認。変異注入 12 本中 10 検出。

- **blocker-1**: `matches` が申告に無いまま DataService で実行可能 (B-1 と同型の再発。ゲート列挙が Q-2 裁定より古かった) → §3 のゲートに `matches` を追加
- **blocker-2**: `_check_type` 通過後に PostgreSQL が拒む値 (bigint 溢れ・U+0000・末尾裸 `\` パターン — 最後は格納データ依存で非決定) が 503 に化け、AI エージェントを成功しない再試行ループに入れる → R-7 に値域・パターン文法検証 (共有境界) と 22xxx→`VALIDATION_FAILED` 写像を追加。末尾裸 `\` は契約に「`VALIDATION_FAILED`」を明文化 (裁定5の文言確定)
- **D-1〜D-4**: ApplicationCell の `contains`/`matches`/`ne`/`in` の NULL・型意味論が PostgreSQL と乖離 (D-1 は nullable 列への contains が常に失敗する参照実装バグ) → R-7 に「述語意味論は SQL 側に統一」を明記し ApplicationCell を修正
- **object/array**: 「正当な乖離」容認を却下し、DOMAIN 型 (`_r2db_json_object`/`_r2db_json_array`) + Python 側検証で厳格側に統一 (CHECK 制約案は名前長溢れと DETAIL 行開示の2つの罠があり不採用)。R-7 に記録
- **テスト**: 素の insert の `assigned_addresses` が無検査 (変異生存)、エスケープ文法境界・両 cell parity テストの追加を WP-3 是正に含める
- C-12 の逆向き条件を WP-5 で登録 (§4 に追記)
