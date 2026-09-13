# 巨大モジュールの段階的リファクタリング設計 (R-22 / R-37)

## 0. 版数・位置づけ

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
