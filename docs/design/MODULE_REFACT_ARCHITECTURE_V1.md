# 巨大モジュールの段階的リファクタリング設計 (R-22 / R-37)

## 0. 版数・位置づけ

- **現行版: v1.7 (2026-09-14)。** 直後の v1.6 行は当時の改版履歴として保存する。v1.7 は §10.3 以前を書き換えず、未コミットの §10.4 に既知の穴の追跡先 (roadmap R-39) と #6 の扱い (型検査器の既知事項) を反映した記録である。
- **現行版: v1.6 (2026-09-14)。** 直後の v1.5 行は当時の改版履歴として保存する。v1.6 は既存の本文 (§0〜§10.3) を 1 文字も書き換えず、末尾に **§10.4 (WP-1d / 1e / 1f 実施記録)** を追記した記録である。
- **現行版: v1.5 (2026-09-14)。** 直後の v1.4 行は当時の改版履歴として保存する。v1.5 は既存の本文 (§0〜§9) を 1 文字も書き換えず、末尾に **§10 (WP-1 実施記録)** を追記した記録である。
- **現行版: v1.4 (2026-09-14)。** 直後の v1.3 行は当時の改版履歴として保存する。v1.4 は既存の本文 (§0〜§8) を 1 文字も書き換えず、末尾に **§9 (R-22 裁定の反映)** を追記した記録である。
- **現行版: v1.3 (2026-09-14)。** 直後の v1.2 行は当時の改版履歴として保存する。v1.3 は既存の本文 (§0〜§8) を 1 文字も書き換えず、§8.4 冒頭の段落の直後に、依頼者裁定 (2026-09-14) により (a)〜(c) を `docs/work-orders/OPERATING_CONDITIONS.md` §1.5 の 40a〜40c へ昇格した旨の追記を 1 件足した記録である。
- **現行版: v1.2 (2026-09-14)。** 直後の v1.1 行は当時の改版履歴として保存する。v1.2 は §0〜§7 の本文を 1 文字も書き換えず、末尾に **§8 (実施記録)** を追記した記録である — 同日に main へ入った WP-1 相当の片側 leaf 抽出 6 件の遡及 inventory (§8.1)、その逸脱の記録 (§8.2)、是正変更セットとその変異・ゲート結果 (§8.3)、以後の WP への追加規律 (§8.4、§5.1 への追補) である。
- **現行版: v1.1 (2026-09-14)。** v1.0 の「両 Peer を常に同時に同型分割する」という表現を改め、共通の公開意味と、選択して pin した peer-local helper のソース同型性を区別した。実装固有の構造を同一にすることは目的でも完了条件でもない。
- 本書は roadmap R-37 の実施設計である。公共 API、契約、Security Invariants、conformance 条件の正本は、それぞれ `spec/`、`security/SECURITY_INVARIANTS_V1.md`、`conformance-tests/` にある。本書はそれらを変更しない。
- 対象は巨大モジュールを安全に小さくする保守作業であり、新機能、API 形状、権限、resource limit、監査意味、永続化形式を変えない。いずれかが変わる提案は、本書の抽出作業から切り離し、通常の「共通能力 → Security Invariants → contract → conformance → implementation」の順で別途決定する。
- 初期の観測対象は `MitateDB-api/src/mitatedb_api/cell.py`（4,711 行）、`r2db-api/src/r2db_api/structured.py`（3,254 行）、`r2db-api/src/r2db_api/postgres.py`（2,975 行）、`r2db-api/src/r2db_api/service.py`（1,886 行）である。MitateDB の `backend_postgres.py` は SQL 抽出を行う WP-4 の対象候補であり、`service.py` は WP-3 の対象である。行数は優先順位の参考であって、抽出の正当化にはしない。
- 変更クラスは正本 roadmap §9.8 のとおり**触れるファイル集合だけ**で決める。通常の peer-local code は Class B、登録済み `_ISOMORPHIC_TARGETS` helper 本体又は `spec/` / `conformance-tests/` は Class C、`security/`、公開ゲート、又は同 targets 集合の増減は Class D である。一つの変更では最も重い class を採る。

## 1. 守るものと非目標

### 1.1 不変の公開意味

各 work package（WP）は、対象の前後で次を維持しなければならない。

1. API の request / response / error code / `details` 語彙、capability 宣言、評価順序、request_id、idempotency、dry-run / plan の意味。
2. SI-00〜SI-15 の安全結果。特に application / control plane 分離、server-side scope 解決、Runtime / Developer 分離、任意 SQL 非公開、構造化エラーの秘匿、監査、資源制限、原子性、認可情報を確立できない時の fail-closed を弱めない。
3. PostgreSQL の transaction 境界、advisory lock と table lock の取得・解放順、timeout、接続 ownership、例外変換。これらは「SQL 文字列を別ファイルへ移しただけ」とは見なさない。
4. 既存の import 先と、外部・テスト・adapter が参照する public / semi-public symbol の互換性。移動元の module は安定した facade として残し、呼出側を一斉に書換えない。

| 不変条件群 | 抽出で残す choke point | 最低限の証拠 |
| --- | --- | --- |
| SI-00〜SI-03 / SI-15 | service / cell の認証、scope、role、developer gate | 権限拒否と unavailable authorization metadata の既存 peer-local / conformance tests |
| SI-04〜SI-05 | request validator、catalog照合、operator表、SQL execute choke point | raw SQL / identifier / value / operator の static・unit test |
| SI-08〜SI-14 | transaction、lock、timeout、audit、idempotency、limit の caller-side boundary | 既存 rollback、競合、audit、limit、replay tests |

### 1.2 非目標

- `r2db-api` と `MitateDB-api` のコード共有、同じディレクトリ構成の強制、または全関数の本文一致。
- SQL 方言・backend の差を隠す抽象化、DB transaction をまたぐ generic helper、依存性注入 framework の導入。
- 大規模な rename / formatter / import-order だけの変更を抽出と同じコミットに混ぜること。
- `COLLECTION_FLOOR` を「テストを一件も減らしていない証明」と扱うこと。これは大幅な収集減の検知器であり、値の更新は完了ゲートのみで行う。

## 2. 設計判断

### D-1: 先に依存グラフを細くする

新 module は、下位から上位への一方向依存だけを持つ。推奨する層は次のとおりである。

```text
値・識別子・宣言の検証（副作用なし）
        ↓
要求の束縛／正規化（副作用なし、明示入力のみ）
        ↓
service / cell のユースケース調停（認可、plan、idempotency、監査）
        ↓
backend / PostgreSQL 実行（connection、transaction、lock、SQL）
```

下位 module は上位 module、HTTP、環境変数、global mutable state、database connection を import してはならない。日時、乱数、request_id、principal、limits、transaction / connection は暗黙に読むのではなく、必要な層の引数として受け取る。循環 import を解消するための late import は設計上の失敗として扱い、抽出を戻して境界を狭める。

### D-2: facade-first の移行

初回抽出では移動元の public symbol 名、署名、例外を保存する。旧 module は新しい leaf module を import / re-export する薄い facade になってよいが、公開 API の利用者に新 path への移行を要求しない。新 path を public contract として文書化するのは、別の互換性判断が済んだ後だけである。

### D-3: Peer の「意味の一致」と「本文の一致」を分離する

両 peer は共通 contract と conformance により公開意味を一致させる。一方、storage model、credential model、transaction 実現、private helper の形は異なり得る。従って、片側だけの低リスク抽出は許される。

同名・同責務の小さな peer-local helper を意図して本文同型に保つと決めた場合だけ、両側の `_ISOMORPHIC_TARGETS` に一つの行を追加する。登録前に両 source を既存 normalizer で比較し、同型でない理由があるなら登録しない。その場合も conformance と peer-local tests で公開意味を守る。`_ISOMORPHIC_TARGETS` は全体設計の同型性を主張する表ではない。

### D-4: SQL builder は capability を持たない

PostgreSQL 用の query builder を導入する場合、許される責務は identifier / placeholder / 固定トークンを使った SQL object と parameter list の組立だけである。戻り値は `psycopg.sql.SQL` / `Composed` と params に限定する。builder は connection を開かず、execute / commit / rollback / lock / timeout / retry / audit / authorization を行わず、外部入力を raw SQL text として受け取らない。identifier は既存の syntax validation と live catalog 照合済みのもの、operator / sort direction は既存の閉集合、値は placeholder 又は既存の安全な driver value adapter 経由に限定する。

SQL builder の抽出は `postgres.py` と MitateDB の PostgreSQL backend が同じ内部 API を持つことを前提にしない。各 peer の driver 呼出し、transaction 所有権、lock 方式を局所に残す。実行は各 peer の既存 `sql.SQL` / `Composed` 専用 choke point だけに残し、client-influenced statement が plain `str` で到達できない性質を新 module を含む走査で確認する。

## 3. 抽出の適格性と禁止境界

### 3.1 最初に切り出せる候補

各候補はコード読解とテストで次を満たすと示してから抽出する。

| 候補 | 必須の性質 | 初回に残す責務 |
| --- | --- | --- |
| 値・型・identifier の検証 | 明示引数だけで決まり、I/O、時計、乱数、global mutable state を読まない | HTTP error への最終変換、認可判断 |
| schema request の束縛・正規化 | request と明示された capability / role から決まり、DB を読まない | schema revision の取得、transaction、DDL 実行 |
| error `details` の組立 | 許可済みの閉語彙と安全な field path のみを返す | endpoint 固有の HTTP status / body 組立 |
| SQL object の組立 | 固定 SQL 片と検証済み input のみを使い、execute しない | connection / cursor、lock、timeout、例外分類 |

「現在その関数が短い」こと、または二つの peer に似た処理があることは適格性の証拠にならない。

### 3.2 最初の抽出から除外するもの

以下は副作用境界そのものであるため、D-1 の leaf extraction に含めない。必要なら専用 WP と決定的な競合 / rollback テストを先に設計する。

- idempotency reservation / replay と request digest の記録。
- audit emit、request_id の生成・伝播、dry-run / plan の state snapshot。
- connection / cursor の所有権、transaction、advisory / table lock、`SET LOCAL` timeout、retry / driver exception mapping。
- authentication、application scope、Runtime / Developer authorization、control plane access。
- in-memory cell の lock と test seam。R-32 の判断を伴うものは R-37 の内部抽出として進めない。

## 4. 段階的な work package

### WP-0 — inventory と抽出境界の確定

各巨大 module について、候補 symbol、ごく近い callers、読取 / 書込 side effect、現在の import 方向、既存 test、対応する不変条件を表にする。候補ごとに「純粋」「明示 dependency を渡せば純粋」「副作用境界」のいずれかを判定する。抽出後の target path、facade に残す export、touch するファイル、変更クラス、同型性登録の要否もこの表で確定する。特に `bind_schema_operation` は developer gate、request shape、identifier / constraint validation を行い `BoundSchemaOperation` を返す binding boundary であって、DDL builder ではない。認可 gate を leaf へ移動しない。

完了条件は、実装開始前に対象の収集 / test baseline を記録し、複数 WP を並行にするなら manifest 上の変更パスが重ならないことである。WP-0 はコードを動かさない。

### WP-1 — 一方の peer の一つの純粋 leaf

一つの候補だけを新 module へ移す。移動元 facade の API は変えず、直接 unit test と既存 caller test を緑にする。新 module の import graph を静的に確認し、上位層や I/O を import していないことを確認する。意味の等価性をテストできない大きな一括移動は禁止する。

### WP-2 — 必要な場合の peer 対応抽出

もう一方の peer に同じ公開意味の pure leaf があり、本文同型を維持する合理的な理由がある場合にのみ対応抽出を行う。両方の helper 名・signature・正規化後 source が一致した場合は、両方の `test_audit_query.py` の表と full-content pin と row-count pin を同時に更新する。片側固有なら、同型性表は更新せず、差の理由を WP 記録へ残す。

### WP-3 — request binding と service 調停の分離

WP-1 / WP-2 で証明済みの leaf を使い、request binding のまとまりを service / cell から分離する。principal、capability、limits、schema revision 等を暗黙に読ませない。認可、idempotency、audit、plan、dry-run の順序と例外型は facade 側に残す。既存 contract と conformance がこの WP の公開意味を検証するので、変更が必要に見えたら WP を止めて設計変更として扱う。

### WP-4 — backend 内の SQL assembly 分離

WP-3 と独立に、単一 backend の狭い DDL / query assembly を D-4 に従って切り出せる。SQL の生成と実行を分離しても transaction と lock の境界は同一の caller に残る。SQL string の見た目を統一するための置換、dialect 横断化、raw SQL の受入は対象外である。

### WP-5 — facade 縮小と閉止

各 WP の import graph、残る facade、dead private symbol、テストの重複を確認する。export を消す、path を public にする、同型性対象を減らす、テストを削除する場合は個別に根拠と回帰証拠を添え、通常の変更クラス判定を再実施する。line count は成果指標ではなく、責務・依存方向・回帰証拠が閉止条件である。

## 5. 検証と変異

### 5.1 WP ごとの必須証拠

1. 旧 facade と新 leaf の import / export が意図どおりであり、循環 import がない静的照合。
2. 抽出した leaf の同値テスト。正常値だけでなく、境界値、型違い、閉語彙外、例外経路を含める。
3. 既存の peer-local suite と、当該の conformance 条件を駆動する adapter / test。新しい共通条件を作る必要はない。
4. 何を同型性表に登録したか、登録しなかったならなぜか、を review で確認する。
5. 性能に意味のある経路を動かした WP は、`tools/PERF_BASELINE_README.md` の方法で同じ warmup / n の差分を残す。

### 5.2 変異は性質ごとに行う

変異は一時コピー又は専用 worktree で行い、復元と変異文字列 0 件確認は `OPERATING_CONDITIONS.md` の規律に従う。少なくとも次を対象の性質に合わせて実測する。

| 守る性質 | 代表変異 | 赤になる根拠 |
| --- | --- | --- |
| facade 互換 | facade の re-export を外す、又は引数を渡さない | import / caller test |
| validation / error 語彙 | enum / field path / declared type の一箇所を変える | direct test と既存の詳細語彙 test |
| SQL 安全性 | identifier object / placeholder を raw text に置換する | static safety test 又は builder unit test |
| 同型性（登録したものだけ） | 一方の helper の一文字又は数値 literal を変える | 両 peer の isomorphism test |
| transaction / lock（触った場合） | lock / rollback / timeout の一箇所を無効化する | 決定的な peer-local concurrency / rollback test |

「行削除で pytest が何らかのエラーになる」だけでは不十分である。変異は、その WP が主張する意味を直接壊し、意図した test が赤になる必要がある。実施しない完了条件は「監査照合」と明記し、照合対象と実行結果を WP 記録に残す。

### 5.3 完了ゲート

開発中は触った peer suite と該当 conformance file を実行し、統合前と完了時は `docs/work-orders/OPERATING_CONDITIONS.md` §1.3 に従う。監督は他の pytest がないことを確認して root から `./.venv/bin/python -m pytest -q -n 5 --dist loadgroup` を単独実行し、前後の `pg_database` 差分が 0 であることも確認する。合格は failed / skipped / xfailed がすべて 0、CI ではさらに xpassed / deselected が 0、かつ CI 3.11 集計行と性能差分が得られることである。`COLLECTION_FLOOR` は root collection に対して確認し、現行値 3,326 を WP 中に上げない。これは一件も削除されない証明ではないため、test node-id inventory の前後 diff も review 資料にする。テストの追加により collection が増えても、値の更新は完了ゲート時だけである。

## 6. 安全な実施・レビュー・記録

- WP ごとに変更パス manifest、変更クラス、抽出前後の dependency diagram、完了条件→変異表を置く。並行 WP は manifest の重なりを 0 にする。
- 実装 review は一回の設計 review に置換しない。契約を触らない本リファクタリングは最低一回の独立 review を通し、契約・security・conformance の変更を誘発した時点で該当する追加 review / approval に切り替える。
- `_ISOMORPHIC_TARGETS` を更新する場合、両 peer の `tests/test_audit_query.py` の表、full-content pin、row-count pin を同じ pair-closing change set に含める。集合の増減は Class D であり、C の証拠に加えて依頼者裁定の逐語記録と版付き security-contract 決定を要する。表の行数だけを更新すること、既存行を別の行へ差し替えること、normalizer を緩めて差を吸収することは禁止する。
- 新しい文書、test fixture、commit message を含め、実 absolute path、credential、DSN、実 data を置かない。公開前提の走査は未追跡の新設ファイルにも明示パスで実施する。
- roadmap R-37 と Phase 10 台帳 L10-20 は本設計への参照と追跡先であり、完了の事実を先取りしてはならない。実施済みの WP、変異、gate 集計、残余リスクは日付付き追記で記録する。

## 7. 着手・停止条件

着手は WP-0 の inventory、対象 test baseline、変更 path manifest、roadmap §9.9 の Change Set Manifest（目的、読む正本、触る／触らないファイル、完了条件↔変異、検証、class）、独立 reviewer の確認が揃ってからとする。次のいずれかが起きた時点で抽出を停止し、別の設計判断へ戻す。

- public response、capability、error details、evaluation order、idempotency digest、audit event、limit のいずれかが変わる。
- security invariant の保証を以前と同じテストで示せない。
- pure leaf が connection、global state、clock、principal、transaction を必要とし、dependency を明示しても境界が細くならない。
- peer の構造差を `_ISOMORPHIC_TARGETS` の normalizer 拡張で隠す必要が生じる。
- full suite 又は対象 conformance が skip / xfail を必要とする。

この停止はリファクタリングの失敗ではない。新しい能力又は既存の意味の不明確さを発見した時点で、契約・安全性・適合性の正しい決定経路へ戻すための境界である。

## 8. 実施記録

**本節は v1.2 (2026-09-14) の追記である。§0〜§7 の本文は 1 文字も書き換えていない。** §6 の最終項に従い、実施済みの WP・逸脱・是正を日付付きで記録する。**R-22 は依頼者判断待ちであり、本設計の実施は R-22 の裁定を代替しない。** 

### 8.1 WP-1 (2026-09-14) — 遡及 inventory

**本表は、§4 WP-0 が実装前に確定すべきであった表を、コミット後に遡って作成したものである** (§8.2 の 1)。6 件はいずれも一方の peer だけの抽出であり (D-3)、各コミットの変更クラスは `tools/change_class.py` の判定で **B** である。旧 module は新 module から名前を import して保持し、既存の import 先を変えていない (D-2)。

| # | commit | peer | 移動元 → 移動先 | symbol | 分類 (§3.1 の候補 / §4 WP-0 の判定) | 残る facade | 追加・変更したテスト | 同型性登録 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `f8d71a0` | r2db | `r2db-api/src/r2db_api/postgres.py` → `postgres_types.py` | `_FIELD_TYPE_SQL` / `_JSONB_SQL` / `_column_type_sql` | SQL object の組立 / 純粋 (`psycopg.sql` だけを import し、connection を開かず execute しない) | `postgres.py` が 3 名を import | **既存テストの拡張 (新規テストなし)**: `r2db-api/tests/test_postgres.py::test_field_type_sql_json_entry_maps_to_jsonb_without_keyerror` に facade 同一性 (`is`) 3 件、語彙 7 語の集合、`sql.SQL` / `sql.Identifier` の種別、語彙外の JSONB fallback の assert を追加 | 登録しない — MitateDB 側に同名 helper が無い |
| 2 | `80fe099` | MitateDB | `MitateDB-api/src/mitatedb_api/backend_postgres.py` → `postgres_value_domain.py` | `_check_domain` / `_INT_DOMAIN_RANGES` | 値・型の検証 / 純粋 (`.errors` だけを import し、details 付き `ValidationError` を送出する) | `backend_postgres.py` が 2 名を import | **既存テストの拡張 (新規テストなし)**: `MitateDB-api/tests/test_postgres.py::test_check_domain_type_mismatches_are_rejected_at_the_mechanism_level` に `_check_domain` の facade 同一性、`::test_check_domain_range_boundaries_at_the_mechanism_level` に `_INT_DOMAIN_RANGES` の facade 同一性を追加 | 登録しない — r2db 側に同名 helper が無い |
| 3 | `1c08e12` | r2db | `r2db-api/src/r2db_api/service.py` → `audit_counts.py` | `_coalesced_count` | §3.1 の 4 種別に直接の行は無い (監査 event の count 表現) / 純粋 (import なし)。audit emit そのものは §3.2 のとおり `service.py` に残る | `service.py` が import | 新規 `r2db-api/tests/test_application_audit.py::test_coalesced_count_leaf_preserves_the_service_facade` | 登録しない — MitateDB 側に同名 helper が無い |
| 4 | `1f5243b` | r2db | `r2db-api/src/r2db_api/postgres.py` → `postgres_like.py` | `_escape_like_literal` | SQL の `LIKE` に渡す値の escape (SQL object の組立に付随) / 純粋 (import なし) | `postgres.py` が import | 新規 `r2db-api/tests/test_postgres.py::test_escape_like_literal_leaf_preserves_facade_and_escape_order` | 登録しない — MitateDB 側に同名 helper が無い |
| 5 | `51039e7` | r2db | `r2db-api/src/r2db_api/structured.py` → `value_nul.py` | `_contains_nul` | 値の検証 / 純粋 (`typing` だけを import) | `structured.py` が import | 新規 `r2db-api/tests/test_foundation.py::test_contains_nul_leaf_preserves_structured_facade_and_nested_detection` | 登録しない — MitateDB 側に同名 helper が無い |
| 6 | `2a20d33` | MitateDB | `MitateDB-api/src/mitatedb_api/cell.py` → `request_traversal.py` | `_as_traversable` | 要求の束縛・正規化 / 純粋 (`dataclasses` / `typing` だけを import) | `cell.py` が import (`asdict` / `is_dataclass` の import は `cell.py` から外れた) | 新規 `MitateDB-api/tests/test_application_plane_limits.py::test_as_traversable_leaf_preserves_cell_facade_and_dataclass_normalization` (同ファイル冒頭の `from mitatedb_api.cell import …` に `_as_traversable` を追加) | 登録しない — r2db 側に同名 helper が無い |

- **「相手 peer に同名 helper が無い」は、`2a20d33` の両 peer の `src/` と `conformance/` を symbol 名で検索した結果である** (r2db `auth.py` の `_contains_nul` の出現はコメント内の言及であり、定義ではない)。登録しないことは D-3 のとおりであり、`_ISOMORPHIC_TARGETS` の集合は変わっていない。
- **新規テストは 4 件 (#3〜#6)、既存テストの拡張は 2 件 (#1 / #2) である。** root collection は **`2a20d33` 時点で 3,330** である (6 抽出の新規テスト 4 本分、`COLLECTION_FLOOR` 3,326 から +4。監督の実測)。是正後の値は §8.3 のゲート集計に記す。
- **§3.1 末尾が求める適格性の根拠 (「短い」「似ている」以外の理由) は、実施時の記録が無い。**

### 8.2 逸脱の記録

1. **着手条件の未充足。** 6 件は §7 の着手条件 — WP-0 の inventory、対象 test baseline、変更 path manifest、roadmap §9.9 の Change Set Manifest (完了条件↔変異の表を含む)、独立 reviewer の確認 — をいずれも満たさずに main に入った。§8.1 の表は遡及作成であり、着手条件の充足を意味しない。
2. **peer suite を実行しないまま main に入った。** §5.3 の「開発中は触った peer suite を実行する」と、roadmap §9.8 の Class B の証拠 (触った peer の suite + コードレビュー + 監督の root suite) が得られていない。**main `2a20d33` で、両 peer の `tests/test_l1_details_vocabulary_ast_scan.py` が赤である。** 原因は行番号 allowlist と per-module 件数 pin の陳腐化である。赤の node id は次のとおりである。
   - r2db (3 件): `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py::test_every_choke_point_denial_carries_details_ast_full_count`、`::test_allowlist_entries_match_real_bare_call_sites`、`::test_backend_layer_allowlist_entries_have_no_in_memory_sibling_denial`
   - MitateDB (4 件): `MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py::test_every_choke_point_denial_carries_details_ast_full_count`、`::test_allowlist_entries_match_real_bare_call_sites`、`::test_backend_layer_allowlist_entries_have_no_in_memory_sibling_denial`、`::test_ast_full_count_matches_a_non_trivial_floor`
   - 独立レビューが `2a20d33` を再構成して、r2db `3 failed, 4 passed` / MitateDB `4 failed, 5 passed` を再現した。
3. **走査の穴。** MitateDB の `SCANNED_MODULES` は module 名を列挙した tuple であり、`postgres_value_domain.py` を含まない。**`_check_domain` の details 付き `ValidationError` 4 箇所が同 module へ出たため、L1 details 語彙の AST 走査の対象から外れた** (`backend_postgres.py` の件数 pin の実測は 28 → 24、`postgres_value_domain.py` は 4)。件数 pin の赤は「移動元から減った」ことを検知したが、pin を実測値に合わせるだけでは移動先が走査外のまま緑になる。r2db の 4 新 module は `errors` を import しておらず、denial の呼出しを持たない。
4. **経緯コメントの喪失。** 移動時に元の docstring / コメントが短い一般文へ置き換えられ、設計参照が失われた — #1 は元コメントの `R-2/R-7`、WP-3 review の DOMAIN 型統一、`json` 行の Phase 6 WP-2 (design D-3、r2db decision (c)) の説明、`_column_type_sql` の docstring。#2 は `_check_domain` の docstring (B-1 (i)、m-8、追補 4 O-2) と design G3 の注記。#4 は Q-2 (案i) の docstring。#5 は R-7 addendum / WP-3 review blocker-2 の docstring。#6 は Phase 8 WP-1a (design D-1) の docstring (`Filter` を generic な dataclass 変換で扱う理由)。**#3 は移動元に docstring が無く、関数直前の説明コメントは `service.py` に残ったまま関数定義から離れた。**
5. **原因 (事実の範囲)。** L1 details AST scan は、走査対象を module 名 (`SCANNED_MODULES`)・行番号 (allowlist)・module ごとの件数で固定する静的テストであり、ソースの移動を赤で検知する設計であった。赤は出たが、コミット前に peer suite が実行されなかったため、検知が main への統合前に働かなかった。

### 8.3 是正変更セット (branch `r37-wp1-fix`、**監督ゲート通過 2026-09-14**)

**本節は是正の範囲と結果を記録する。R-37 全体の完了を意味しない。**

1. **経緯コメントの復元。** §8.2 の 4 の docstring / コメントを新 module (#3 は `audit_counts.py`) へ戻す。**位置参照の括弧書きと facade re-export の注記 (D-2) 以外は、移動元コミットの原文と逐語一致とする。**
2. **走査 pin の実測更新。** 両 peer の `tests/test_l1_details_vocabulary_ast_scan.py` の行番号 allowlist と per-module 件数を、是正後のソースの実測値へ更新する。
3. **走査対象の追加。** MitateDB の `SCANNED_MODULES` へ `postgres_value_domain.py` を加える。
4. **ガードテストの追加 (両 peer の同ファイル)。** denial の呼出しを含む `src` 配下 (サブパッケージを含む再帰走査) の module は、`SCANNED_MODULES` か理由付き除外集合のいずれかに入っていること。除外集合と `SCANNED_MODULES` は重ならず、除外 module は実際に denial を含むこと。**除外 module 内に新たに足された denial はこの走査では検出されない** (既存の走査範囲の限界。除外集合の変更は監督裁定を要する)。除外集合は r2db が {`auth.py`, `credential_store.py`, `ops.py`}、MitateDB が {`config.py`, `control_auth.py`, `control_credential_store_postgres.py`, `ops.py`} である。
5. **変異の実測。** 6 抽出それぞれの facade 互換変異と意味変異、およびガードテストの変異 (§5.2)。下の表に記す。
6. **独立コードレビュー** (§6)。
7. **root suite ゲート** (§5.3)。下の集計に記す。

**完了条件 ↔ 変異** (§5.2。変異は一時コピー又は専用 worktree で行い、復元と変異文字列 0 件確認は運用条件 §1.4 に従う):

| 対象 | 守る性質 | 変異 | 赤になった node id |
| --- | --- | --- | --- |
| #1 `postgres_types.py` | facade 互換 | `postgres.py` の import から `_column_type_sql` を外す | `r2db-api/tests/test_postgres.py` の大半 (`94 failed, 54 passed, 53 errors`)。`postgres.py` 自身が同名を呼ぶため、pin テスト単独ではなく module 全体で赤になる |
| #1 `postgres_types.py` | 意味 (型対応・SQL object 種別) | `"object"` を `sql.Identifier` から `sql.SQL` へ | `r2db-api/tests/test_postgres.py::test_field_type_sql_json_entry_maps_to_jsonb_without_keyerror` |
| #2 `postgres_value_domain.py` | facade 互換 | `backend_postgres.py` の import から `_check_domain` を外す | `MitateDB-api/tests/test_postgres.py::test_check_domain_type_mismatches_are_rejected_at_the_mechanism_level`、`::test_check_domain_range_boundaries_at_the_mechanism_level` (ImportError) |
| #2 `postgres_value_domain.py` | 意味 (domain 判定) | `int32` の上限を +1 | `MitateDB-api/tests/test_postgres.py::test_check_domain_range_boundaries_at_the_mechanism_level` (DID NOT RAISE) |
| #2 `postgres_value_domain.py` | details 語彙 | `float` 分岐の `ValidationError` から `details=` を外す | `MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py::test_every_choke_point_denial_carries_details_ast_full_count`、`::test_allowlist_entries_match_real_bare_call_sites` |
| #3 `audit_counts.py` | facade 互換 | `service.py` の import を外す | `r2db-api/tests/test_application_audit.py::test_coalesced_count_leaf_preserves_the_service_facade` (ImportError) |
| #3 `audit_counts.py` | 意味 (singleton を count 無しで表す) | `occurrences >= 2` を `>= 1` へ | 同上 (AssertionError) |
| #4 `postgres_like.py` | facade 互換 | `postgres.py` の import を外す | `r2db-api/tests/test_postgres.py::test_escape_like_literal_leaf_preserves_facade_and_escape_order` (ImportError) |
| #4 `postgres_like.py` | 意味 (escape 順序) | `replace()` の順序を入れ替え、backslash を最後に escape | 同上 (AssertionError) |
| #5 `value_nul.py` | facade 互換 | `structured.py` の import を外す | `r2db-api/tests/test_foundation.py::test_contains_nul_leaf_preserves_structured_facade_and_nested_detection` (ImportError) |
| #5 `value_nul.py` | 意味 (入れ子の NUL 検出) | dict 分岐を削除 | 同上 (AssertionError) |
| #6 `request_traversal.py` | facade 互換 | `cell.py` の import を外す | `MitateDB-api/tests/test_application_plane_limits.py` の collection error (module 冒頭で `mitatedb_api.cell` から import するため、同ファイル全体が赤) |
| #6 `request_traversal.py` | 意味 (dataclass の正規化) | `asdict()` を通さずに返す | `MitateDB-api/tests/test_application_plane_limits.py::test_as_traversable_leaf_preserves_cell_facade_and_dataclass_normalization` |
| 是正 3 / 4 | 走査対象の網羅 | MitateDB `SCANNED_MODULES` から `postgres_value_domain.py` を外す | `MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py::test_every_module_with_a_vocabulary_denial_is_accounted_for`、`::test_ast_full_count_matches_a_non_trivial_floor` |
| 是正 4 | 未登録 module の検出 | r2db `value_nul.py` に `details=` の無い `fail(...)` を 1 行足す | `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py::test_every_module_with_a_vocabulary_denial_is_accounted_for` |
| 是正 4 | 除外集合と走査対象の非重複 | MitateDB の除外集合へ `postgres_value_domain.py` を足す (`SCANNED_MODULES` には残す) | `MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py::test_deliberately_unscanned_modules_do_not_overlap_scanned_modules` |
| 是正 4 | 除外の滞留防止 | r2db の除外集合へ denial 0 件の `postgres_like.py` を足す | `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py::test_deliberately_unscanned_modules_each_carry_a_real_denial` |
| 是正 4 | サブパッケージの再帰走査 | scratch コピーの r2db `contract/__init__.py` に `details=` の無い `fail(...)` を足す | **監査照合** (pytest 実行ではなく、ガードの判定ロジックを scratch コピーに対して再生した): 未登録として `['contract/__init__.py']` を検出 |

- 意味変異と facade 変異は、対象テストを選択実行した (`-k` 等。例: `1 failed, 199 deselected`)。走査の変異はファイル全体を実行した。すべての変異で `cp` による復元、`sleep 3`、sha256 の二重照合、変異文字列 0 件を確認した。
- **独立コードレビュー (Opus) は blocker / major 0 件、minor 7 件・nit 6 件であり、監督裁定のうえ全件を是正又は存置 (facade 注記) とした。** レビュー自身の変異のうち、除外集合へ移す**と同時に** `SCANNED_MODULES` と件数 pin から消す完全な編集 (M1) と、除外 module `ops.py` への denial 追加 (M2) は緑のままである (下の残余リスク)。

**root suite ゲートの集計** (2026-09-14、監督、他の pytest 0 件を確認のうえ単独実行、base `2a20d33` + 本是正の差分): `./.venv/bin/python -m pytest -q -n 5 --dist loadgroup` → **`3336 passed in 437.75s (0:07:17)`** (failed / skipped / xfailed 0)。前後の `pg_database` 差分 0、nginx 残留 0。root collection は 3,336 であり、`COLLECTION_FLOOR` は §5.3 に従い 3,326 のまま据え置く (R-37 は WP 中)。**CI 3.11 の集計行は未取得** (GitHub の課金上限により push 停止中。台帳 L10-15 と同じ扱い)。性能差分は取得していない — 6 抽出は関数本体を AST 同一のまま移したもので、呼出し経路は同じ関数 object を import で参照するだけであり、§5.1 の 5 の「性能に意味のある経路を動かした WP」に当たらないと監督が判断した。

**残余リスク**: 4 のガードは、理由付き除外集合に入った module の中に新たに足された denial を検出しない。また、走査対象の module を `SCANNED_MODULES` と件数 pin から消して除外集合へ移す一貫した編集も緑のまま通る。いずれも除外集合の変更として差分に現れるので、除外集合の変更は監督裁定を要する (レビューで検出する)。

### 8.4 以後の WP への追加規律 (**v1.2 追補**)

**§5.1 の本文は書き換えない。以下は §5.1 の必須証拠と §7 の着手条件への追補であり、WP-2 以降のすべての WP に適用する。** `docs/work-orders/OPERATING_CONDITIONS.md` への昇格は依頼者確認待ちである。

**【追記 2026-09-14】** 依頼者裁定「格上げします」により、(a)〜(c) は `OPERATING_CONDITIONS.md` §1.5 の条項 40a〜40c へ昇格した (正本はそちら)。(d) は本設計 §7 に留まる。

- **(a)** 抽出コミットの前に、移動元・移動先を含む両 peer の suite を実行し、集計行を WP 記録に残す。
- **(b)** module を名前・行番号・件数で固定する静的テスト (例: 両 peer の `tests/test_l1_details_vocabulary_ast_scan.py` の `SCANNED_MODULES`、行番号 allowlist、per-module 件数 pin) は、移動の都度同じ変更セットで更新し、新 module が走査対象に入ったことを確認する。この確認はガードテスト (§8.3 の 4) で機械化する。件数 pin を実測値へ合わせるだけの更新で済ませない。
- **(c)** docstring と経緯コメントは逐語で移す。移動によって指す先が変わる位置参照 (`file:line`、「below」「this module's own」等) だけを括弧書きで補い、本文を言い換えない。
- **(d)** WP-2 以降は §7 の着手条件 — WP-0 の inventory、対象 test baseline、変更 path manifest、roadmap §9.9 の Change Set Manifest (完了条件↔変異の表を含む)、独立 reviewer の確認 — を満たしてから着手する。§8.1 のような遡及 inventory は着手条件の代わりにならない。

## 9. R-22 裁定の反映 (2026-09-14)

**本節は v1.4 の追記である。§0〜§8 は書き換えていない。** 裁定の逐語と 4 問の採否の正本は roadmap §8 の R-22 行である。

### 9.1 R-22 の答えとしての R-37

依頼者裁定 (問い 1) により、本設計は R-22 の巨大モジュール分割の答えとして正式に採られた。§8 冒頭の「R-22 の裁定を代替しない」の注記はこの裁定で解消する。次の着手は WP-0 であり、§7 と §8.4 (d) の着手条件は変わらない。

### 9.2 履歴コメントの方針 (問い 3)

経緯は記録へ移し、コード内には現在の理由と記録への参照 ID だけを残す。本節は要件だけを定め、**詳細設計は後続の設計追補で行う**。

1. **受け皿。** 経緯は設計書などの版管理された記録に置く。
2. **参照 ID の形。** 記録の文書と箇所を一意に特定でき、実在を機械的に照合できる形とする (具体形は追補で決める)。
3. **変更の分離。** 経緯の移動は抽出と別の変更セットで行う。抽出中は `docs/work-orders/OPERATING_CONDITIONS.md` §1.5 の 40c に従い逐語で移す — 40c は移動中に経緯を失わない規律であり、本方針と矛盾しない。
4. **影響確認。** 移動の変更セットは、`_ISOMORPHIC_TARGETS` の同型性テストの normalizer と full-content pin、行番号 allowlist を持つ静的走査など、コメント・docstring・行位置に依存するテストへの影響を確認してから行う。

### 9.3 R-32 を WP-3 の前提条件に加える (§7 への追補)

**§7 の本文は書き換えない。** 依頼者裁定 (問い 4) により、WP-3 が `cell.py` の `_gate` 又はその呼出し経路を移動・変更する前に R-32 (roadmap §8) を片付けることを WP-3 の着手条件に加える。§3.2 の最終項はこの順序で満たす。

## 10. WP-1 実施記録 (2026-09-14)

**本節は v1.5 の追記である。§0〜§9 は書き換えていない。** 作業指示書は `docs/work-orders/WORK_ORDER_R37_WP0_INVENTORY_V1.md` (v1.2)。§8.1 の遡及 inventory 6 件とは別の記録である。

### 10.1 WP と統合

| WP | 内容 | merge | root ゲート |
| --- | --- | --- | --- |
| WP-0 | inventory・baseline・manifest。独立レビューで「着手可」 | `de5ffd1` | — |
| WP-1-0 | `tools/tests/test_leaf_import_direction.py`: 両 peer の全 src module を leaf / 理由付き非 leaf に分類。レビューで偽の緑 8 件を閉じた | `cffbbef` | 不要 (root の収集件数 3,341 は不変。`tools/tests` は `109 passed`) |
| WP-1a | r2db `structured.py` → `pg_text_format.py` | `20ed7ab` | `3342 passed` |
| WP-1b | MitateDB `cell.py` → `delete_confirmation.py` | `2e4bf36` | `3343 passed` |
| WP-1c | r2db `structured.py` → `inmemory_sort.py` | `b54721e` | `3344 passed` |

- WP-1a / 1b / 1c はいずれも、関数本体が AST で同一、facade 経由で同じ object、docstring は逐語で移動 (`docs/work-orders/OPERATING_CONDITIONS.md` §1.5 の 40c)、変異はすべて赤、独立コードレビュー承認である。root ゲートの前後の `pg_database` 差分は 0。

### 10.2 既知の穴 (移動前から存在し、各 WP の範囲外)

| # | 対象 | 穴 | 追跡 |
| --- | --- | --- | --- |
| 1 | r2db `pg_text_format.py` | 出力を実 PostgreSQL の text 形と照合するテストが無い (負の指数、`-0.0`、非 ASCII キー) | roadmap §8 R-38 に添える |
| 2 | MitateDB `delete_confirmation.py` | 非 ASCII filter 値の canonical JSON を固定するテストが無い。変わっても古い phrase が拒否されるだけなので、安全側に倒れる | 同上 |
| 3 | r2db `inmemory_sort.py` | 降順の同値行と `false < true` を固定するテストが無い | 同上 |
| 4 | r2db `inmemory_sort.py` | **挙動の食い違い。** in-memory の ORDER BY は、同じ型の array / object を canonical JSON テキストで比較する。PostgreSQL の jsonb の順序 (要素数が先、その後に要素ごと) と一致しない。例: `[1,2] < [3]`、`[10] < [9]` が真になる | roadmap §8 R-38 |

### 10.3 次の WP

作業指示書 §4 の順に、WP-1 後続 (同表「4〜」行: CE2 → ST3 → ST4 → ST5 → ST7 → ST6 → CE3 → CE4 → BP4)、request binding の WP-3 などへ進む。着手条件は §7 と作業指示書どおりである。

### 10.4 WP-1d / 1e / 1f 実施記録 (2026-09-14、v1.6 追記)

| WP | 抽出 | merge | root ゲート (passed) | 備考 |
| --- | --- | --- | --- | --- |
| WP-1d | MitateDB `cell.py` → `request_limits.py` | `6afe211` | 3350 | 新規テスト 6 本 (監督裁定) |
| WP-1e | r2db `structured.py` → `inmemory_predicate.py` | `19f3d3b` | 3352 | 新規テスト 2 本 (監督裁定)。sib 集合は固定 tuple |
| WP-1f | r2db `structured.py` → `identifier_rules.py` | `4fc5517` | 3356 | 新規テスト 4 本 (末尾改行と非 str の SI-05 の穴を塞ぐ)。未使用になった `import re` を削除 |

- 3 件とも、関数本体は AST で同一、facade 経由で同じ object、docstring は逐語 (`docs/work-orders/OPERATING_CONDITIONS.md` §1.5 の 40c)、独立コードレビュー済み、root ゲートの前後の `pg_database` 差分 0。

**既知の穴** (移動前から存在し、各 WP の範囲外。§10.2 の続き):

| # | 対象 | 穴 | 追跡 |
| --- | --- | --- | --- |
| 5 | MitateDB `request_limits.py` | request 計測の bytes / スカラー / tuple / set / dict キーのコストを固定するテストが無い。conformance C-05 は長い str しか通していない | R-39 |
| 6 | r2db `inmemory_predicate.py` | 裸の `Predicate` 注釈は、型検査器を入れると F821 になる (作業指示書 §5.9 V-2) | — (型検査器の既知事項。テストの穴ではないので R-39 に含めない) |
| 7 | r2db `inmemory_predicate.py` | 型なし列の float の jsonb text、`matches` の `\Z` と `(?s)`、contains / matches の NULL 行除外を固定するテストが無い | R-39 (R-38 と同じ論点、下記) |
| 8 | MitateDB `cell.py` ほか | 移動前から古い、又は移動で古くなったが直すと Class C になる参照 (作業指示書 §5.9 V-4 の一覧) | R-39 (conformance-tests を直すので Class C) |

- **R-38 との関係**: 1e が移した述語評価 (`_matches` / `_predicate_text` / `_wildcard_pattern`) は、§10.2 の 4 (in-memory の ORDER BY) と同じく、in-memory の比較の意味を PostgreSQL に合わせる箇所である。#7 はその一致を固定するテストの欠落であり、R-38 と同じ論点に属する。
- 次の WP は作業指示書 §5.10〜§5.14 (WP-1g / 1h / 1i)。
- **追跡 (2026-09-14、監督裁定、v1.7)**: テストの穴の追跡は roadmap §8 R-39 に一本化した (§10.2 の 1〜3 を含む)。
