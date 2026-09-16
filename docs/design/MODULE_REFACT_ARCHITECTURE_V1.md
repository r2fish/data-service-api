# 巨大モジュールの段階的リファクタリング設計 (R-22 / R-37)

## 0. 版数・位置づけ

- **現行版: v1.21 (2026-09-16)。** 直後の v1.20 行は当時の改版履歴として保存する。v1.21 は既存の本文を書き換えず、末尾に **§10.18 (WP-4c 実施記録、および WP-4 の完了)** を追記した記録である。
- **現行版: v1.20 (2026-09-16)。** 直後の v1.19 行は当時の改版履歴として保存する。v1.20 は既存の本文を書き換えず、末尾に **§10.17 (WP-4b 実施記録)** を追記した記録である。
- **現行版: v1.19 (2026-09-16)。** 直後の v1.18 行は当時の改版履歴として保存する。v1.19 は既存の本文を書き換えず、末尾に **§10.16 (WP-4a 実施記録)** を追記した記録である。
- **現行版: v1.18 (2026-09-16)。** 直後の v1.17 行は当時の改版履歴として保存する。v1.18 は既存の本文を書き換えず、末尾に **§10.15 (WP-3i 実施記録)** を追記した記録である。
- **現行版: v1.17 (2026-09-16)。** 直後の v1.16 行は当時の改版履歴として保存する。v1.17 は既存の本文を書き換えず、末尾に **§10.14 (WP-3h 実施記録)** を追記した記録である。
- **現行版: v1.16 (2026-09-16)。** 直後の v1.15 行は当時の改版履歴として保存する。v1.16 は既存の本文を書き換えず、末尾に **§10.13 (WP-3g 実施記録)** を追記した記録である。
- **現行版: v1.15 (2026-09-15)。** 直後の v1.14 行は当時の改版履歴として保存する。v1.15 は既存の本文を書き換えず、§10.11 に【追記】を 1 件足し、末尾に **§10.12 (WP-3f 実施記録)** を追記した記録である。
- **現行版: v1.14 (2026-09-15)。** 直後の v1.13 行は当時の改版履歴として保存する。v1.14 は既存の本文を書き換えず、末尾に **§10.11 (WP-3e 実施記録)** を追記した記録である。
- **現行版: v1.13 (2026-09-15)。** 直後の v1.12 行は当時の改版履歴として保存する。v1.13 は既存の本文を書き換えず、末尾に **§10.10 (WP-3d 実施記録)** を追記した記録である。
- **v1.12 (2026-09-15)。** 直後の v1.11 行は当時の改版履歴として保存する。v1.12 は既存の本文を書き換えず、末尾に **§10.9 (WP-3a〜3c 実施記録)** を追記した記録である。
- **現行版: v1.11 (2026-09-15)。** 直後の v1.10 行は当時の改版履歴として保存する。v1.11 は既存の本文を書き換えず、末尾に **§10.8 (WP-2a 実施記録)** を追記した記録である。
- **現行版: v1.10 (2026-09-15)。** 直後の v1.9 行は当時の改版履歴として保存する。v1.10 は既存の本文を書き換えず、末尾に **§10.7 (WP-1m / 1n / 1k 実施記録)** を追記した記録である。
- **現行版: v1.9 (2026-09-15)。** 直後の v1.8 行は当時の改版履歴として保存する。v1.9 は既存の本文を書き換えず、末尾に **§10.6 (WP-1j / 1l 実施記録)** を追記した記録である。
- **現行版: v1.8 (2026-09-14)。** 直後の v1.7 行は当時の改版履歴として保存する。v1.8 は既存の本文を書き換えず、§10.3 に【追記】を 1 件足し、末尾に **§10.5 (WP-1g / 1h / 1i 実施記録)** を追記した記録である。
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

**【追記 2026-09-14、v1.8】** ST6 (WP-1i) までを終えた (§10.5)。残りは作業指示書 §4 の「4〜」行の CE3 → CE4 → BP4、続いて順番の付かない行 (BP1・BP2、WP-2 の CE1 ↔ r2db `_canonical_where_json` の判断、WP-3、WP-4) である。

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

### 10.5 WP-1g / 1h / 1i 実施記録 (2026-09-14、v1.8 追記)

| WP | 抽出 | merge | root ゲート (passed) | 備考 |
| --- | --- | --- | --- | --- |
| WP-1g | r2db `structured.py` → `delete_confirmation.py` (ST5) | `f249ed5` | 3360 | — |
| WP-1h | r2db `structured.py` → `paging.py` (ST7) | `9e82d57` | 3365 | 未使用になった `import base64` を削除。件数 pin 88 → 78 (`paging` 10)。監督裁定 W-2 に従い `_shape_hash` の「immediately above」参照を修正。レビューで SI-08 のテスト 2 本を追加 (where の値又は page size が異なる cursor を拒否) |
| WP-1i | r2db `structured.py` → `value_types.py` (ST6 と `_TEXT_ONLY_OPERATORS`、W-1) | `868e7fd` | 3366 | 件数 pin 78 → 67 (`value_types` 11)。W-2 の `_INT64_MAX` 参照を `value_types.py` に更新 |

- 3 件とも、関数本体は AST で同一、facade 経由で同じ object、docstring は逐語 (`docs/work-orders/OPERATING_CONDITIONS.md` §1.5 の 40c)、独立コードレビュー済み、root ゲートの前後の `pg_database` 差分 0。
- **コードレビューの訂正 (WP-1i)**: `structured.py` 旧 L2296 / L2312 の「below」は、`structured.py` に残る `_apply` 内の呼出しを指すので括弧書きを付けない。作業指示書 §5.13 の括弧書きは 8 箇所ではなく 6 箇所である。

**既知の穴** (移動前から存在し、各 WP の範囲外。§10.4 の続き):

| # | 対象 | 穴 | 追跡 |
| --- | --- | --- | --- |
| 9 | r2db `delete_confirmation.py` | `_PHRASE_MAX_LENGTH` の値は長さの guard としてしか検査されていない | R-39 |
| 10 | r2db `paging.py` | 次を固定するテストが無い: bool の offset の受入れ、cursor / order_by の余分なキー、不正な direction、id を補うのは不在時だけであること | R-39 |
| 11 | r2db `value_types.py` | enum 宣言の field への型違いの値が enum ではなく field_type で報告されること、`in` の要素の `/value/<j>` path を固定するテストが無い | R-39 |
| 12 | r2db `value_types.py` (MitateDB `field_types.py` も同じ) | `number` の field が NaN / ±Infinity を受け入れる | R-40 (共通契約の決定) |

### 10.6 WP-1j / 1l 実施記録 (2026-09-15、v1.9 追記)

| WP | 抽出 | merge | root ゲート (passed) | 備考 |
| --- | --- | --- | --- | --- |
| WP-1j | MitateDB `cell.py` → `constraint_resolution.py` (CE3: `_validate_enum_declaration_with_path`、`_resolve_field_constraints`) | `df9d81f` | 3368 | 件数 pin `cell.py` 47 → 44 (新 module 3)。未使用になった import 2 件を削除。括弧書きは `field_types.py` 2 箇所と `cell.py` 2 箇所 (X-4)。レビューの訂正: スキャンテストの既存コメントから誤って削った一文を戻した |
| WP-1l | MitateDB `backend_postgres.py` → `postgres_reserved_names.py` (BP4: 予約名の定数 2 つと検査本体) | `b0c1a8b` | 3370 | method は 1 行の委譲で残す (X-3)。件数 pin 24 → 23 (新 module 1)、allowlist の 20 行は −14。`pg_` の接頭辞と `audit_events` の完全一致を初めて固定するテストを追加。レビューで `audit_event` を受け入れる確認を 1 行追加 |

- 2 件とも、関数本体は AST で同一、facade 経由で同じ object、docstring は逐語 (`docs/work-orders/OPERATING_CONDITIONS.md` §1.5 の 40c)、独立コードレビュー済み、root ゲートの前後の `pg_database` 差分 0。
- **WP-1k (CE4) はコメント変更セット 3 の統合を待つ** (作業指示書 §5.19 の X-1)。

**既知の穴** (移動前から存在し、各 WP の範囲外。§10.5 の続き):

| # | 対象 | 穴 | 追跡 |
| --- | --- | --- | --- |
| 13 | MitateDB `constraint_resolution.py` | 未知の field_constraints キーが複数あるとき、どのキーを報告するかを固定するテストが無い | R-39 |
| 14 | MitateDB `constraint_resolution.py` | bool でない整数の `nullable` (例 `1`) の拒否を固定するテストが無い | R-39 |
| 15 | `MitateDB-api/tests/test_limit_class_vocabulary.py` | L154 の件数説明が `_resolve_field_constraints` の箇所を今も `cell.py` としている (作業指示書 §5.16 の 19) | R-39 |
| 16 | MitateDB `postgres_reserved_names.py` | 予約名の拒否メッセージの文言を固定するテストが無い | R-39 |
| 17 | MitateDB `postgres_reserved_names.py` | `pg_` の大文字小文字の区別を固定するテストが無い (`identifiers.py` の小文字限定の正規表現が先に弾くので、外からは到達しない) | R-39 |

### 10.7 WP-1m / 1n / 1k 実施記録 (2026-09-15、v1.10 追記)

| WP | 抽出 | merge | root ゲート (passed) | 備考 |
| --- | --- | --- | --- | --- |
| WP-1m | MitateDB `backend_postgres.py` → `postgres_types.py` (BP1: 型対応の定数 4 つ) | `cca16fe` | 3371 | `_TYPES` は facade に残さない (Y-7)。allowlist は −64。manifest の変異 2 で `test_declared_type_registry_round_trips_every_contract_type` も赤になることを実測 |
| WP-1n | MitateDB `backend_postgres.py` → 既存の `postgres_value_domain.py` (BP2: `_validate_value_domain`) | `4d45fc6` | 3373 | 件数 pin 23 → 21 / 4 → 6、allowlist は −118。未使用になった `observed_type_of` を削除。括弧書きは Y-2 / Y-4 / Y-9 と `backend_sqlite.py` L688 |
| WP-1k | MitateDB `cell.py` → `provisional_gate.py` (CE4: `_deny_provisional_field`) | `13241c2` | 3375 | 件数 pin `cell.py` 44 → 43。`http.py` の CH-ID 付き docstring に 40c の括弧書きを足したので、受け皿 `docs/code-history/MitateDB-api/http.md` の CH-0192 に訂正の記録を追記 (コメント出所の変更セット 0g の手順)。`errors.py` の括弧書きは入れ子にしない書き換え |

- 3 件とも、関数本体は AST で同一、facade 経由で同じ object、docstring は逐語 (`docs/work-orders/OPERATING_CONDITIONS.md` §1.5 の 40c)、独立コードレビュー済み、root ゲートの前後の `pg_database` 差分 0。
- **その間に起きた事象**: コメント出所の変更セット 0g が r2db `postgres.py` の 4 行を戻したため、r2db の L1 scan の行番号 pin (1519 → 1523) がずれ、main の root suite が赤になった。`9297dd9` で直した。0g の最終確認は `tools/tests` だけで、root gate を流していなかった。**教訓: src の行数が変わる変更は、root gate を通してから統合する。**
- **次の WP**: WP-1 の「4〜」行は完了。次は WP-2a (CE1 の性質テスト、Y-6)、`backend_postgres.py` のコメント整理 (Y-5、WP-4 の前)、WP-3。

**既知の穴** (移動前から存在し、各 WP の範囲外。§10.6 の続き):

| # | 対象 | 穴 | 追跡 |
| --- | --- | --- | --- |
| 18 | MitateDB `postgres_types.py` | int32 / int64 の入れ替えと text domain の差し替えを検出するのは、新しい literal pin だけ | R-39 |
| 19 | MitateDB `postgres_value_domain.py` | float・int32・json の domain 検査を 1 型だけ飛ばす変異と、孤立 surrogate の検査を high surrogate だけに狭める変異が緑のまま | R-39 |
| 20 | MitateDB `provisional_gate.py` | 移した docstring の呼出し元の文は移動前から古い。到達不能な gate を固定しているのは直接のテストだけ | R-39 |

### 10.8 WP-2a 実施記録 (2026-09-15、v1.11 追記)

**判断 (Y-6)**: MitateDB CE1 と r2db `_canonical_where_json` を `_ISOMORPHIC_TARGETS` に登録しない。契約は phrase の綴りを実装定義としているので、代わりに各 peer のテストで契約の規則を固定した。

| WP | 内容 | merge | root ゲート (passed) | 備考 |
| --- | --- | --- | --- | --- |
| WP-2a | テストのみ。MitateDB 4 本 (非 ASCII の escape、型の区別、上限の境界、3 要素以上の list 順)、r2db 3 本 (型の区別、list 順 (gt / lt / eq)、`_PHRASE_MAX_LENGTH` と契約の上限) | `b45312d` | 3382 | 上限は同梱の契約から読み、4 箇所の `confirmation.maxLength` が等しいことも検査する (Z-3) |

- **レビューの訂正**: テストの docstring から経緯語を消した。list 順を 3 要素に強くした (MitateDB 側の既存の 2 要素だけの穴も閉じた)。
- **閉じた項目**: roadmap R-39 の (1b) と (1g)。conformance のベクトルは R-41 に回した (Z-1)。規則 1 の `destructive` の値からの独立と規則 5 も R-41 に加えた。
- **次の WP**: WP-3 (request binding、manifest 起草中)、`backend_postgres.py` のコメント整理 (Y-5、コメント変更セット 5 の後)。

### 10.9 WP-3a〜3c 実施記録 (2026-09-15、v1.12 追記)

作業指示書 §5.27〜§5.31。3 件とも r2db `service.py` からの片側抽出で、認証・rate・slot・audit の順序は facade に残した。

| WP | 抽出 | merge | root ゲート (passed) | 備考 |
| --- | --- | --- | --- | --- |
| WP-3a | r2db `service.py` → `service_results.py` (SV1: `QueryPage`・`MutationResult`) | `6f7168f` | 3384 | — |
| WP-3b | r2db `service.py` → `capabilities_document.py` (SV2: 文書の組立) | `93a81de` | 3386 | principal・limits・deployment の値を既定値の無い引数で渡す。移した本体の AST の差はその名前の置換だけ (W3-3)。ロールとデプロイ設定の 240 通りで出力が移動前と同一であることをレビューで確認 |
| WP-3c | r2db `service.py` → `request_shape.py` (SV3: query / mutate の形の検査と CH-0126 の塊、W3-5) | `d236d0b` | 3388 | 認証の後に形の検査が走ること (無効な資格情報と不正な形の組は `AUTH_INVALID`) と、拒否が監査に残ることを query・mutate の tests で固定 (mutate はレビューで追加)。L1 scan の件数 pin `service.py` 10 → 4、`request_shape.py` 6、sib tuple に追加 (W3-4) |

- 3 件とも、コメントは CH-ID ごと逐語 (`docs/work-orders/OPERATING_CONDITIONS.md` §1.5 の 40c) で、括弧書きを足した塊は受け皿 `docs/code-history/r2db-api/service.md` に訂正の記録を追記した。変異はすべて赤 (6 / 10 / 14)、root ゲートの前後の `pg_database` 差分 0。WP-3c 統合後の root ゲートは `3388 passed` (`pg_database` / `pg_roles` 差分 0)、`tools/tests` は `392 passed`。
- **次の WP**: ST8〜ST10 と CE5〜CE7 を WP-3d 以降として実測・起草する (作業指示書 §5.31 の W3-1)。

**既知の穴** (移動前から存在し、各 WP の範囲外。§10.7 の続き):

| # | 対象 | 穴 | 追跡 |
| --- | --- | --- | --- |
| 21 | `r2db-api/tests/test_foundation.py` | L439 が `service.py` の `capabilities()` のコメントを引くが、そのコメントはソースに無い (WP-3a の統合時点で既に無い) | R-39 |
| 22 | r2db `service.py` | L720・L770 の docstring の崩れ「every existing caller --, the in-process」 | R-39 |
| 23 | r2db `service_results.py` | L14 (逐語で移動) の docstring の崩れ「CCR-13 introduced `items`/`next_page` adds `revisions`」 | R-39 |
| 24 | r2db `request_shape.py` | 形の検査と `limits.check_request` の順序を固定するテストが無い (WP-3c の commit が記録) | R-39 |
| 25 | `r2db-api/conformance/conformance_adapter_r2db.py`、`conformance-tests/test_c04_unsupported_and_safe_errors.py` | `service.py` の行番号参照が移動前から古い (WP-3c の commit が記録) | R-39 |

### 10.10 WP-3d 実施記録 (2026-09-15、v1.13 追記)

作業指示書 §5.32・§5.33・§5.39 (裁定 W3-6〜W3-14)。

| WP | 抽出 | merge | root ゲート (passed) | 備考 |
| --- | --- | --- | --- | --- |
| WP-3d | r2db `structured.py` → `storage_outcomes.py` (ST10: `QueryOutcome`・`MutationOutcome`・`SchemaOutcome`) | `ead4893` | 3390 | 登録 helper を挟む 2 塊を飛び石で移し、`_ISOMORPHIC_TARGETS` の差分は 0。括弧書きは `backend.py` の 1 か所。新規テスト 2 本 (facade の同一性、frozen と既定値)。変異は実装 5 件とレビュー 3 件がすべて赤。完了条件 1 の変異は、名前を消すと `backend.py` の import が収集時に壊れるため、別の class で上書きする形に改めた (W3-14) |

- root ゲートの前後の `pg_database` / `pg_roles` 差分は 0、`tools/tests` は `404 passed`。
- §10.9 の既知の穴 22・23 (`service.py` と `service_results.py` の docstring の崩れ) は、`d85bd42` (merge `7c25e88`) で閉じた。崩したのは R-22 変更セット 2 の `fb9a098`。
- **次の WP**: WP-3e (CE5)。R-22 変更セット 6 と MitateDB の `tests/test_l1_details_vocabulary_ast_scan.py` を共有するので、変更セット 6 の統合後に行数を測り直してから着手する。

### 10.11 WP-3e (CE5 → `request_vocabulary.py`) 実施記録 (2026-09-15、v1.14 追記)

作業指示書 §5.32・§5.34 (訂正註)・§5.39 (裁定 W3-6〜W3-16)。

| WP | 抽出 | merge | 備考 |
| --- | --- | --- | --- |
| WP-3e | MitateDB `cell.py` → `request_vocabulary.py` (CE5: 7 定数) | 本変更 | `cell.py` L56-229 (`b65e97d`、174 行) を新規の leaf `MitateDB-api/src/mitatedb_api/request_vocabulary.py` へ移した。leaf は何も import しない (`tools/tests/test_leaf_import_direction.py` の許可は空集合)。facade は 7 名を import で読む。`b65e97d` で測り直し、manifest (`9994d7c` で実測) からのずれは無い |

- **40c**: 範囲内の括弧書き 8 箇所を除き、バイト単位で同一の移動である (独立 Opus レビューが別に導出して一致)。括弧書きは計 17 箇所 (範囲内 8、範囲外 9)。範囲外のうち 3 箇所は W3-15・W3-16 で足した。
- 登録 helper と CE7 は動かしていない (正確な範囲で差分 0)。`_ISOMORPHIC_TARGETS` も差分 0。
- **40b**: 更新の要る静的 pin は無い。`cell.py` の L1 details の件数は 43 のまま。backend の allowlist は `cell.py` を覆わない。コメントだけの `cell.py:NNNN` pin 16 件は `b65e97d` の時点ですでに古い (既知の穴、R-39 と同種)。
- **変異** (`mutate.py`。7/7 が予想どおり赤、復元を確認):

| 変異 | 完了条件 | test |
| --- | --- | --- |
| C1 | 1 facade | `test_request_vocabulary_leaf_preserves_cell_facade` (AttributeError で赤。W3-14 の上書きの形は要らなかった) |
| C2 | 2 literal | `test_request_vocabulary_constants_are_literal` |
| C2b | 2 型の pin | 同上 |
| C3 | 3 認可が鍵集合の検査より先 | `test_transact_key_set_check_runs_after_authorization` |
| C3b | 3 `details["field"]` | 同上 |
| C4 | 4 leaf の import | `tools/tests/test_leaf_import_direction.py::test_leaf_modules_import_only_their_allowlisted_modules` |
| C5 | 5 分類 | `::test_every_src_module_is_classified` |

- **40a の suite** (手直し後、`pt.py`): `MitateDB-api/tests` `1112 passed` (subtests 2)、`r2db-api/tests` `1286 passed`、`conformance-tests` `995 passed`、`tools/tests` `403 passed` と commit 前の 1 failed (`test_0f_both_peers_all_src_rev_vs_itself_is_green`。未追跡の新 leaf を `git show HEAD:` で読むため。新しい HEAD では `finalize.py --tools-tests` で緑)。
- `http.py` のコメント来歴の checker: `comment provenance OK: 97 blocks checked`。register: `81 files scanned, 427 CH-IDs`。
- **レビュー**: 独立 Opus レビューと監査 (差し戻し: W3-15・W3-16 と minor 2 件)、手直し 1 回。
- root gate: `3393 passed, 2 subtests passed`、`judge=PASS`、pg_database / pg_roles の差分 0 (監督、`tools/dev/gate.py`)。
- **教訓**: 移動した名前の grep は、行をまたいで折り返した名前を取りこぼす。位置参照の走査は折り返しを考慮して行う (W3-15 はこうして漏れ、後で見つかった)。
- **次の WP**: WP-3f (ST8)。

**【追記 2026-09-15 (WP-3f のレビューで判明)】** 上の「`http.py` のコメント来歴の checker: `comment provenance OK: 97 blocks checked`」は `--base 6e91983` で走らせた結果である。`6e91983` は変更セット 3 (`f03c02f`) より前で、CH-0221・CH-0228 がまだ無い。そのため checker は初めての移動の枝を通り、再編集については何も示していない。WP-3e の実際の親 `b65e97d` に対しては、同じ確認が赤になる: `FAIL (§4.1 (2)) MitateDB-api/src/mitatedb_api/http.py:820 basis block for CH-0221 is not derivable ...`。`:993` の CH-0228 も同じである。これは §10.12 と同じく、設計どおりの再編集の枝である。WP-3e で実際に成り立つ証拠は、新しい HEAD での `tools/tests` `404 passed` (0f が緑、`finalize.py --tools-tests`) である。main は赤ではなく、コードの変更は要らない。上の行は消さずに残す (R-14)。

### 10.12 WP-3f (ST8 → `mutation_binding.py`) 実施記録 (2026-09-15、v1.15 追記)

作業指示書 §5.32・§5.35 (訂正註)・§5.39 (裁定 W3-6〜W3-18)。

| WP | 抽出 | merge | 備考 |
| --- | --- | --- | --- |
| WP-3f | r2db `structured.py` → `mutation_binding.py` (ST8: 11 名) | 本変更 | `structured.py` L64-104 と L137-307 (`b4aac70`、飛び石 2 塊) を新規の leaf `r2db-api/src/r2db_api/mutation_binding.py` へ移した。leaf の import は manifest の一覧だけである。facade は 6 名を import で読む。間の D-1 見出し (manifest の L104-133) は facade に残し、括弧書きを付けた (W3-7 (b))。`b4aac70` で測り直し、manifest (`9994d7c` で実測) からのずれは行の一様なずれだけである |

- **40c**: manifest の括弧書き 3 箇所を除き、バイト単位で同一の移動である (独立 Opus レビューが別に導出して一致)。W3-17 と合わせて括弧書きは計 11 箇所。
- **40b**: `SCANNED_MODULES` と sib tuple に leaf を足した。件数 pin は `structured.py` 49、`mutation_binding.py` 18。`r2db-api/tests/test_audit_query.py` の修飾名は `mutation_binding.bind_mutation` (W3-8)。
- **変異** (`mutate.py`): C1〜C12 の 12/12 が予想どおり赤、復元を確認。test は §5.35 の表のとおり。C1 は W3-14 の上書き (facade の import の後で `parse_predicate = None`) を使った。
- **完了条件 13**: 変更をコミットした使い捨ての clone で観測した。`tools/tests` `403 passed` (0f が緑)。CH-0057 の訂正の記録を消すと 0f が CH-0057 で赤、CH-0266 の記録を消すと 0f が CH-0266 で赤。
- **40a の suite** (手直し後、`pt.py`): `r2db-api/tests` `1289 passed`、`MitateDB-api/tests` `1112 passed` (subtests 2)、`conformance-tests` `995 passed`、`tools/tests` `402 passed` と commit 前の予想どおりの 0f の赤 (未追跡の新 leaf)。
- **レビュー**: 独立 Opus レビュー・監査・調査 (判定: 差し戻し、裁定待ち → W3-17・W3-18・M2・N1〜N3)、手直し 1 回。
- root gate: `3396 passed, 2 subtests passed`、`judge=PASS`、pg_database / pg_roles の差分 0 (監督、`tools/dev/gate.py`)。
- **教訓**:
  - 位置参照の走査は、行をまたいで折り返した名前だけでなく、移した名前の近くの位置の語も探す。WP-3f の走査は折り返しを考慮していたが、折り返していない 8 つの参照を漏らした。
  - R-37 の移動が CH の塊の中に括弧書きを足す場合、来歴の証拠は新しい HEAD での 0f である。`--base <親>` は再編集の枝で設計どおり必ず赤になる。`--base` は R-22 のコメントだけの変更セットの関門であり、R-37 の移動の関門ではない。
- **次の WP**: WP-3g (ST9 の一部)。

### 10.13 WP-3g (ST9 の一部 → `schema_binding.py`) 実施記録 (2026-09-16、v1.16 追記)

作業指示書 §5.32・§5.36 (訂正註)・§5.39 (裁定 W3-6〜W3-20)。

| WP | 抽出 | merge | 備考 |
| --- | --- | --- | --- |
| WP-3g | r2db `structured.py` → `schema_binding.py` (ST9 の一部: 10 名) | 本変更 | `structured.py` L106-228・L253-265・L311-371 (`bdea9ee`、飛び石 3 塊) を新規の leaf `r2db-api/src/r2db_api/schema_binding.py` へ移した。`bind_schema_operation` の本体は facade に残す (W3-9)。leaf の import は `dataclasses`・`typing`・`.errors`・`.value_types` だけである (`__future__` は常に許す)。facade は 9 名を import で読む (`SCHEMA_OPERATIONS` は再 export しない)。`bdea9ee` で測り直し、manifest (`9994d7c` で実測) からのずれは行の一様なずれ (-203) だけである |

- **40c**: 範囲内の括弧書き 11 箇所を除き、バイト単位で同一の移動である (独立 Opus レビューが別に導出して一致)。`bind_schema_operation` の差分は L326 の括弧書きだけである。登録 helper 6 つは AST で同一 (WF-1)。leaf に `developer` と `FORBIDDEN` は無く、gate は `_SCHEMA_KEYS` の検査より前で走る (WF-2)。W3-19・W3-20 と合わせて括弧書きは計 15 箇所。
- leaf L192「this file's own internal vocabulary」はレビューで確かめ、移動後も成り立つので括弧書きを付けない。
- **40b**: `SCANNED_MODULES` と sib tuple (とその docstring) に leaf を足した。件数 pin は `structured.py` 48、`schema_binding.py` 1 (レビューが別に導出して一致)。コメントだけの `structured.py:NNNN` pin は `bdea9ee` の時点ですでに古い (R-39 と同種)。
- **変異** (`mutate.py`、手直し後): C1〜C10 の 10/10 が予想どおり赤、復元を確認。test は §5.36 の表のとおり。C1 は W3-14 の上書き、C6 は孤立した probe を使った (W3-20)。
- **新規テスト 3 本**。WF-3 の順序テストは本物の順序テストである (gate の順序を入れ替えると `FORBIDDEN` が `VALIDATION_FAILED` に変わる)。
- **来歴の証拠 (コミットした HEAD)**: 変更をコミットした使い捨ての clone で `tools/tests` `403 passed` (0f が緑)。実装者と独立レビューがそれぞれ 1 回観測した (どちらも W3-20 の手直し前。W3-20 は CH-ID の無いコメント 1 つだけである)。CH-ID の塊に入る括弧書きは無い。
- **40a の suite** (手直し後、`pt.py`): `r2db-api/tests` `1292 passed`、`MitateDB-api/tests` `1112 passed` (subtests 2)、`conformance-tests` `995 passed`、`tools/tests` `402 passed` と commit 前の予想どおりの 0f の赤 (未追跡の新 leaf)。
- **レビュー**: 手順 0 の停止 → W3-19。独立 Opus レビューと監査 (判定: 差し戻し、小 → W3-20・m1・m2)、手直し 1 回。
- **既知の穴** (レビューで判明。監督が別コミットで roadmap R-39 に足す):
  - `r2db-api/src/r2db_api/limits.py` L278-280「`_fail_constraint_declaration` precedent above in this same module」: `limits.py` では一度も成り立ったことがなく、登録 helper の中にある。
  - `r2db-api/tests/test_audit_query.py` L2686-2687 と MitateDB 側の L2471-2472「never surfaced past its own module」: 移動前から不正確である。
- root gate: 1 回目は `3399 passed` だったが `judge=FAIL (concurrent pytest)` (レビューが同時に pytest を走らせた)。merge せず、手直しの後に再実行した。
- root gate (再実行): `3399 passed, 2 subtests passed`、`judge=PASS`、pg_database / pg_roles の差分 0 (監督、`tools/dev/gate.py`、他の pytest 0 件)。
- **教訓**: pytest を走らせうる agent (使い捨ての clone での無防備な実行を含む) が動いている間は root gate を走らせない。順に走らせる。
- **次の WP**: WP-3h (CE7)。

### 10.14 WP-3h (CE7 → `capabilities_document.py`) 実施記録 (2026-09-16、v1.17 追記)

作業指示書 §5.32・§5.37 (訂正註)・§5.39 (裁定 W3-6〜W3-22)。

| WP | 抽出 | merge | 備考 |
| --- | --- | --- | --- |
| WP-3h | MitateDB `cell.py` → `capabilities_document.py` (CE7) | 本変更 | `ApplicationRuntime.__build_capabilities_document` の本体と `_surfaces_document_fragment` を、`cell.py` (`ffd6493`) から新規の leaf `MitateDB-api/src/mitatedb_api/capabilities_document.py` の `build_capabilities_document(*, is_developer, role, application_id, cell_config, process_ceiling)` (既定値なし) へ移した。leaf の import は `.backend`・`.surfaces` だけで、`.auth` は import しない (W3-10)。facade の method は 5 つの keyword で leaf を 1 回呼ぶ。`capabilities()` の中の 認可 → limit gate → 組立 の順は変えていない。`ffd6493` で測り直すと、manifest (`9994d7c` で実測) からのずれは行の一様なずれ (-166) だけである |

- **40c / W3-10**: 本体の差は 4 つの置換と範囲内の括弧書き 8 箇所だけである (独立 Opus レビューが別に導出して一致)。`_surfaces_document_fragment` はバイト単位で同一。手直しで範囲内に R5 の 2 箇所を足した。W3-21・W3-22 と合わせて、括弧書きは計 21 箇所、書換えは 1 つ (`request_vocabulary.py` L119) である。
- `cell.py` L521 (`ffd6493`)「reads it via `self.__cell.process_ceiling`」は確かめた。facade がなお読むので括弧書きを付けない (W3-21)。「`cell.py`'s own declaration」の形の参照も、残る `capabilities()` を指すので付けない (W3-22 の n1)。
- **40b**: leaf に denial の呼出し箇所は無い。L1 scan の件数 pin (`"cell.py": 43`)、`SCANNED_MODULES`、allowlist は変わらない。`_ISOMORPHIC_TARGETS` も変わらない。
- **変異** (`mutate.py`、手直し後): C1〜C7・C4b・C4c と n2 (入替え)・n3 (C2 の 2 本目) の 11/11 が予想どおり赤で、復元も確かめた。test は §5.37 の表と訂正註のとおり。
- **新規テスト 3 本**。テスト 3 は n2 で強化した。`rpm=1` を使い切った credential を revoke して再び呼ぶと、認可が先なら `AuthenticationError`、入れ替えると `ResourceLimitError` になる。
- **来歴の証拠 (コミットした HEAD)**: 使い捨ての clone で 3 段を観測した。変更の全体をコミットすると `tools/tests` `420 passed`。CH-0208 の訂正の記録だけを消すと、0f が CH-0208 で赤 (`FAIL (§4.1 (2)) MitateDB-api/src/mitatedb_api/http.py:599 basis block for CH-0208 is not derivable ...`)。記録を戻すと `420 passed`。CH-ID の塊に入る編集は R2 だけである。
- **40a の suite** (手直し後、`pt.py`): `MitateDB-api/tests` `1115 passed` (subtests 2)、`r2db-api/tests` `1292 passed`、`conformance-tests` `995 passed`、`tools/tests` `419 passed`。`tools/tests` には commit 前の予想どおりの 0f の赤がある (未追跡の新 leaf)。
- **レビュー**: 手順 0 の停止 → W3-21。独立 Opus の静的レビュー (判定: 差し戻し、小 → W3-22)。手直し 1 回。
- root gate: 1 回目は `3402 passed` だったが、`judge=FAIL (pg_database -7, pg_roles -22)` だった。原因は、実装者が止めた conformance の実行が PostgreSQL に残した物を、suite の起動時の掃除が消したことである。常駐のローカル service の database が残っていることは確かめた。
- root gate (再実行、落ち着いた catalog で): `3402 passed`、`judge=PASS`、pg_database / pg_roles の差分 0 (手直し前)。
- root gate (手直し後): `3402 passed, 2 subtests passed`、`judge=PASS`、pg_database / pg_roles の差分 0 (監督、`tools/dev/gate.py`、他の pytest 0 件)。
- **既知の穴** (監督が別コミットで roadmap R-39 に足す):
  - レビューが見つけた (m2)、移動前から古い `cell.py:NNNN` の参照: `MitateDB-api/README.md` L204-205 (`cell.py:3887`・`:3860`) と L218-220 (`:4051`・`:4055`・`:4044`)、`conformance-tests/test_c04_unsupported_and_safe_errors.py` L159 (`:1751`)、`MitateDB-api/conformance/conformance_adapter_mitatedb_http.py` L2169 (`:1769`)、`conformance-tests/test_c05_limit_declaration_agreement.py` L890 (`:1491`・`:1502`)。
  - `cell.py` L3736「flip to `enabled` below」(`ApplicationDeveloper.create_entity` の中にある。移動前から本体より後ろにあり、文書を指したことがない)。
  - R3・R4 の `cell.py:1875-1926` と R5 の `:770`・`:832` の値。括弧書きは付けたが、値は古いまま残した。
- **教訓**:
  - 位置参照の走査は、移した名前だけでなく、移したコメントを指す参照 (「`X`'s own `...` comment」の形) も探す。R2〜R4 はこの形で漏れた。
  - pytest の実行を止めない。止めた実行が PostgreSQL に残した物で、次の gate の catalog の差分が FAIL になる。
- **次の WP**: WP-3i (CE6 の一部)。

### 10.15 WP-3i (CE6 の一部 → `request_binding.py`) 実施記録 (2026-09-16、v1.18 追記)

作業指示書 §5.32・§5.38 (訂正註)・§5.39 (裁定 W3-6〜W3-23)。

| WP | 抽出 | merge | 備考 |
| --- | --- | --- | --- |
| WP-3i | MitateDB `cell.py` → `request_binding.py` (CE6 の一部: 3 method) | 本変更 | `_check_predicate_value`・`_normalize_value`・`_normalize_value_for_storage` を、`cell.py` (`a48cfa1`) から新規の leaf `MitateDB-api/src/mitatedb_api/request_binding.py` の関数へ移した (W3-11)。class には `X = staticmethod(X)` の委譲の属性を残す。leaf の import は `json`・`.errors`・`.field_types` だけである (`__future__` は常に許す)。CE6 の他の 7 method と登録 helper は変えていない。`a48cfa1` で測り直すと、manifest (`9994d7c` で実測) からのずれは行の一様なずれ (-178) だけである |

- **40c / W3-12**: 差は列挙したものだけである。デコレータの削除 3 つ、`cls` 引数の削除、`cls._normalize_value` → `_normalize_value` の置換、§5.38 の括弧書き 1 箇所。これらを戻すと AST は一致する (独立 Opus レビューが別に導出して一致)。`cell.py` の hunk はちょうど 3 つである (import の 1 行と、委譲の 2 か所)。
- `cell.py` L3392-3393「`_check_predicate_value`'s own path immediately above」は確かめた。`cell.py` に残る `_bind_filters` の呼出し箇所を指すので、括弧書きを付けない (W3-23 (2))。範囲外の括弧書き 2 箇所と leaf の module docstring の訂正は W3-23 のとおりで、括弧書きは計 3 箇所である。
- **40b**: `SCANNED_MODULES` と sib tuple (7 → 8 module) に leaf を足した。件数 pin は `cell.py` 42、`request_binding.py` 1。ずれた `cell.py` の行を引く静的な pin は他に無い。`_ISOMORPHIC_TARGETS` は変わらない。sib tuple の docstring は例を挙げるだけなので変えていない (W3-23 (5))。
- **変異** (`mutate.py`): C1〜C11 と C8b の 12/12 が予想どおり赤で、復元も確かめた。test は §5.38 の表と訂正註のとおり。C2 の巻き添え (既存の json の往復テスト 5 本) と C1 の巻き添えは認めた (W3-23)。
- **新規テスト 4 本**。WF-3 の順序テストは本物の順序テストである (`read` の `_require_data` を `_bind_filters` の後へ移すと、`AuthorizationError` が `ValidationError` に変わる)。
- **来歴の証拠 (コミットした HEAD)**: 使い捨ての clone で `tools/tests` `422 passed` (0f が緑、手直し 1 の前)。CH-ID の塊に入る編集は無い (`cell.py` の marker は 0。register は 85 files、427 CH-IDs)。
- **40a の suite** (1 回目、`pt.py`): `MitateDB-api/tests` `1119 passed` (subtests 2)、`r2db-api/tests` `1292 passed`、`conformance-tests` `995 passed`、`tools/tests` `421 passed`。`tools/tests` には commit 前の予想どおりの 0f の赤がある (未追跡の新 leaf)。
- 40a (手直し後、`pt.py`): `MitateDB-api/tests` `1119 passed` (subtests 2)、`tools/tests` `421 passed` と commit 前の予想どおりの 0f の赤。手直しはコメントと docstring だけなので `r2db-api/tests` と `conformance-tests` は再実行していない。変異 C1・C6・C7・C8 を再実行し 4/4 が赤。
- **レビュー**: 手順 0 (実装者は止まらなかった。逸脱、W3-23)。独立 Opus の静的レビュー (判定: 小を付けて受入れ → W3-23)。手直し 1 回。
- root gate: 1 回目は `3406 passed` だったが、`judge=FAIL (concurrent pytest ×3)` だった。pytest は、同じ checkout でテスト用 PostgreSQL の分離を進める別のセッションのものだった。監督はそのセッションに pytest を控えるよう求め、gate を再実行した。
- root gate (再実行、手直し前): `3406 passed`、`judge=PASS`、pg_database / pg_roles の差分 0。
- root gate (手直し後): `3406 passed, 2 subtests passed`、`judge=PASS`、pg_database / pg_roles の差分 0 (監督、`tools/dev/gate.py`)。開始時の他の pytest は 0 件である。手直し後に 2 回走らせ、1 回目は開始時に他セッションの pytest が 1 件あったため、判定が PASS でも破棄した (§10.15 の教訓)。
- **教訓**:
  - 分類の無い参照で止まる規則があるのは、実装者の自己判定が当てにならないからである。「変更なし」と自己判定した 2 つの参照のうち、1 つは括弧書きが要った。
  - 同じ checkout で並行するセッションは、machine 全体で数える pytest の件数を共有する。root gate を走らせる前に、動いている相手と gate の時間帯を調整する。
- **次の WP**: WP-3 (3a〜3i) は完了した。作業指示書 §4 の表で WP-3 の後に並ぶのは WP-4 (PG1〜PG4、BP3。manifest は未作成) で、本設計 §4 ではその後が WP-5 (facade 縮小と閉止) である。WP-4 の前に置く `backend_postgres.py` のコメント整理 (Y-5) は、R-22 変更セット 6 (merge `42842de`) で行われた (roadmap の R-22 行)。CE6 の残り 7 method は W3-11 で範囲外とした。その後続は作業指示書に未記載。

### 10.16 WP-4a (BP3 → `postgres_sql.py`) 実施記録 (2026-09-16、v1.19 追記)

作業指示書 §5.40 (共通・裁定 Z4-1〜Z4-8)・§5.41 (manifest)・§5.45 (訂正註、第 2 次〜第 4 次の裁定)。

| WP | 抽出 | merge | 備考 |
| --- | --- | --- | --- |
| WP-4a | MitateDB `backend_postgres.py` → `postgres_sql.py` (BP3: `_OPERATOR_SQL`・`_DIRECTION_SQL`・`PostgresBackend._where_sql`) | 本変更 (commit `dd59cd4`、merge `acb257e`。8 files changed, 203 insertions(+), 44 deletions(-)) | 2 定数と 1 method を、新規の pure leaf `MitateDB-api/src/mitatedb_api/postgres_sql.py` の module 定数と関数へ移した (Z4-8)。class には `_where_sql = staticmethod(_where_sql)` の委譲属性を残したので、5 箇所の呼出し (`update_in_transaction`・`delete_in_transaction`・`read`・`update`・`delete`) は 1 行も変わらない。`insert` は `_where_sql` を呼ばない。ORDER BY / LIMIT の組立・`_execute`・timeout・driver 例外の変換は `backend_postgres.py` に残る。leaf の import は `psycopg` (`from psycopg import sql`) と `.backend` (`SQL_OPERATOR_TOKENS`) だけである |

- **40c**: 本体の差は `def _where_sql(self, filters):` → `def _where_sql(filters):` の 1 種だけである。移動した説明コメント (m-7) と定数は逐語で、移動先 `postgres_sql.py` L20-24 と旧 L130-134 は逐語一致する (独立レビューが diff で確認)。括弧書き (位置参照) は `MitateDB-api/src/mitatedb_api/backend_sqlite.py`:45 と `MitateDB-api/tests/test_postgres.py`:1418 の **2 箇所**で、§5.41 の一覧どおりである。
- **`_OPERATOR_SQL` は facade へ再 export しない。** 第 2 次裁定 6 の条件付き (「移動後の読み手 0 を実測で示したら削る」) は、実測により**削る**に決着した。`backend_postgres.py` 側の読み手は 0 件で、`hasattr(backend_postgres, "_OPERATOR_SQL") is False` も実測した。回帰証拠は下の 40a の suite の集計行である。
- **差し戻し S-1**: 上の削除に伴い、`backend_postgres.py`:90 の `from .backend import SQL_OPERATOR_TOKENS, UNCHANGED` の `SQL_OPERATOR_TOKENS` が読み手 0 になっていた (唯一の読み手は `_OPERATOR_SQL` の定義式だった)。監督の差分確認で見つけ、同じ基準 (裁定 6) で削った。`UNCHANGED` は読み手 5 なので残した。**suite でも変異でも検出されない種類の欠陥である** — 壊れるのは実行時の挙動ではなく、設計 D-1 の「依存グラフを細くする」という主張と、同じ変更セット内での裁定 6 の適用の一貫性である。以後の抽出 WP は、移動によって読み手を失った import・定数・再 export が移動元に残っていないかを、移動前の HEAD と比較した AST の参照件数で確かめる (作業指示書 §5.45 の訂正註 4)。
- **40b**: `tools/tests/test_leaf_import_direction.py` の leaf 一覧に 1 行足し、許可集合は `{"psycopg", ".backend"}` である。`MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py` の行番号 allowlist 20 件は実測で行送りした (前半 11 件 -5、後半 9 件 -19)。各件に既存の書式の行送りコメントを添えた。件数 pin は `backend_postgres.py` 21 のまま差分 0、新 leaf は denial 0 件なので `SCANNED_MODULES`・件数 pin の辞書・sib tuple はいずれも差分 0 である。`_ISOMORPHIC_TARGETS` も差分 0 (WF-1)。
- **変異** (`tools/dev/mutate.py`): **13 件すべて予想どおり赤**で、復元も確かめた。内訳は**実装担当 12 (M1〜M11 と M13)、監督 1** で、**M12 (完了条件 12、CH-0340 の訂正の記録を消す変異) が監督**である (W4-4 (a)(c))。M12 は `mutate: 1 mutations, 1 as expected, restores verified 1/1 files (sha256 x2)`。
- **完了条件 16 件** (変異 13 + 監査照合 3)、**新規テスト 5 本**。M13 と完了条件 16 (「operator は閉じた表から引き、閉語彙外は黙って既定値に落ちない」。変異は `_OPERATOR_SQL[item.operator]` を `_OPERATOR_SQL.get(item.operator, sql.SQL("="))` にする) は、独立コードレビューの指摘 (中-1) で足した。manifest の当初の新規 4 本は、この変異を 4 本とも緑のまま通していた。§5.1 の 2 が必須の証拠に挙げる「閉語彙外、例外経路」の取りこぼしである。
- **来歴の証拠 (コミットした HEAD)**: 使い捨て clone は使わない (W4-4 (b))。監督が `tools/dev/finalize.py --no-merge` で WP branch に記録し、その HEAD (`dd59cd4`) で `tools/tests` を流して **`486 passed in 34.06s`** を得た。0f (`test_0f_both_peers_all_src_rev_vs_itself_is_green`) は緑である。移動範囲の CH-ID は 0 件で、範囲外の CH-0340 に括弧書きを足したので `docs/code-history/MitateDB-api/backend_sqlite.md` §CH-0340 に訂正の記録を書いた。登録簿の節は動かしていない (Z4-4)。
- **40a の suite** (`tools/dev/pt.py`): `MitateDB-api/tests` `1124 passed, 2 subtests passed`、`r2db-api/tests` `1292 passed`、`conformance-tests` `1006 passed`、`tools/tests` (高-1 の修正後・統合前) `1 failed, 485 passed`。この 1 赤は `test_0f_both_peers_all_src_rev_vs_itself_is_green` の 1 件だけで、実エラーは `AssertionError: fatal: path 'MitateDB-api/src/mitatedb_api/postgres_sql.py' exists on disk, but not in 'HEAD'` である。**`_check_rev_pair` に到達する前の「全 real_paths が HEAD に存在するか」の assert で停止しており、§9f 起因ではない。**裏づけは、同じ実行が記録後の HEAD で `486 passed` になっていることである (下の来歴の証拠)。
- **訂正の記録の書式 (独立レビュー 高-1)**: 初稿は §CH-0340 の `old:` / `new:` を、コメント記号 `# ` と行の折り返しを含む断片のまま書いていた。`tools/check_comment_provenance.py` の `_apply_corrections` は companion を `_flatten` した本文に対して `old` の 1 件一致を要求するので、これは 0 件一致で `FAIL (§9f)` になる。HEAD の blob 同士でも出るので、**記録に入れても 0f は赤のままだった**。**初稿時点の実装担当の報告「`tools/tests` の 1 赤は未コミットの新 leaf だけが理由」は実測に反しており** (§1.5 の 34)、当時の 1 赤には §9f の不一致も含まれていた。独立レビューだけがこれを検出した。記号を落とし折り返しを連結した 1 行に直して緑にし、その後の統合前の 1 赤は上の 40a のとおり未追跡の新 leaf だけが理由になった。前例は `docs/code-history/MitateDB-api/http.md`:699 (CH-0208) と `docs/code-history/r2db-api/service.md`:409 である。
- **`--base` の §4.1 の赤 (独立レビュー 低-2。完了条件 14 の監査照合の材料)**: `tools/check_comment_provenance.py --base` は `backend_postgres.py`:130・:131 ほか 8 件で §4.1 の赤を出す。CH-ID を持たない塊 (m-7 の説明コメント) が別ファイルへ移ったための**位置ずれ**であり、40c を満たしていても出る (逐語一致と差 1 種は diff で確認済み)。**Z4-4 のとおり `--base` は来歴の証拠に使わない**ので、この赤は判定に使わない。
- **手順 0 の走査: 分類の無い参照 0 件。** §5.41 の「付ける / 付けない」の一覧が全件を覆っていた。**WP-3e〜3i では毎回取りこぼしており、独立レビューだけが順に 3・8・1・5・2 件を見つけていた** (引き継ぎ書 `docs/work-orders/HANDOVER_20260916_FABLE.md` §6)。manifest 起草時に走査を完了条件として書いた効果が出た最初の WP である。
- **レビュー**: 監督の差分確認による差し戻し S-1 (1 件) と、独立 Opus のコードレビュー (高 1 / 中 1 / 低 3 の計 5 件。**全件受け入れ**) による差し戻し 2。クラスの引き上げは無い (Class B のまま。契約・不変条件・`_ISOMORPHIC_TARGETS`・`security/`・`conformance-tests/` に差分 0 を独立レビューが実測)。
- **root gate** (監督、`tools/dev/gate.py`): `3422 passed, 2 subtests passed in 386.48s (0:06:26)`、`judge=PASS`、`pg_database/pg_roles diff 0`、`info=shared pg_database/pg_roles diff 0`。exit 0。R-44 WP-2 統合後の形なので、3 行目は gate 自身が起動した使い捨てクラスタの差分であり**判定に使う**。4 行目の `info=shared` は共有クラスタの情報であり判定に使わない。着手時の期待値は新規テスト 4 本を前提に `3421` だったが、中-1 で新規テストが 5 本になったので `3422` である。統合の直前に main (`b42e7e9`) を取り込んでからゲートを回した (低-3)。
- **教訓**:
  - **役割ごとの権限を manifest の完了条件に織り込む。** 完了条件 12 と 15 は記録を要するが、記録は監督のみが行う。manifest は実装担当に実行不能な条件を割り当てていた。独立レビューもこれを検出しなかった (test id と実測値は照合したが、役割ごとの権限までは見ていない)。裁定 W4-4 で監督の監査照合に変えた。
  - **チェッカーが読む形と、人が読む形は違う。** 訂正の記録の `old:` / `new:` は、チェッカーが `_flatten` した本文に対して照合する。原文の見た目のまま写すと 0 件一致で赤になる。
  - **読み手 0 の判定は、移動した名前だけでなく、その名前を読んでいた import にも掛ける。** 片側だけに適用すると、同じ変更セットの中で基準が 2 通りになる (S-1)。
- **次の WP**: WP-4b (PG1 → 既存 `r2db-api/src/r2db_api/postgres_types.py` へ追加)。以後 4c (PG3)・4d (PG2 + `_bind_value`) の直列である (Z4-2、Z4-7)。W4-4 (d) により、4b〜4d の来歴の証拠と訂正の記録の変異も監督が行う。作業指示書 §5.45 の訂正註 2〜4 は 4b〜4d の manifest に掛かる。PG4 は Z4-1 で範囲外とした。

### 10.17 WP-4b (PG1 → `postgres_types.py`) 実施記録 (2026-09-16、v1.20 追記)

作業指示書 §5.40 (共通・裁定 Z4-1〜Z4-8)・§5.42 (manifest)・§5.45 (訂正註 1〜5 と、本 WP で足した 6・7)。

| WP | 抽出 | merge | 備考 |
| --- | --- | --- | --- |
| WP-4b | r2db `postgres.py` → 既存 leaf `postgres_types.py` (PG1: `_DOMAIN_TO_DECLARED`・`_SQL_TYPE_TO_DECLARED`・`_TableInfo`) | 本変更 (commit `e8906ff`、merge `2e94bbf`。6 files changed, 171 insertions(+), 60 deletions(-)) | 2 定数と 1 dataclass を、既存の pure leaf `r2db-api/src/r2db_api/postgres_types.py` へ移した (Z4-8。新しい module は作らない)。`postgres.py` は既存の `from .postgres_types import ...` に 3 名を足して読むので、`_load_catalog`・`_describe_table` の catalog 読み取り、`information_schema` の照会、型ヒント 4 箇所はいずれも `postgres.py` に残り、呼出し側は 1 行も変わらない。leaf の import は `psycopg`・`dataclasses`・`typing` だけである |

- **40c**: 移動 2 塊は逐語で、本体の変更は 0 である (独立レビューが旧 `postgres.py` L205-226 / L250-275 と byte 比較。差は括弧書き 1 箇所だけ)。移動した塊の**内側**の空行も 1 行も変わっていない。`# history: CH-0005` / `History: CH-0006` / `# history: CH-0101` の 3 件は塊と同行して移った。括弧書き (位置参照) は CH-0101 のコメントの「(`_load_field_constraints` below)」の 1 箇所で、`(in `postgres.py`)` を足した — `_load_field_constraints` が `postgres.py` に残ることは独立レビューが実測した。
- **移動先 module の docstring の訂正 (独立レビュー 中-2)**: `postgres_types.py`:1-6 の module docstring 「PostgreSQL **DDL** type objects …」「it **only maps** an already validated contract field-type word to a psycopg SQL composition object」は、**逆写像 2 本と `_TableInfo` dataclass が入った時点で偽になった**。`_SQL_TYPE_TO_DECLARED` / `_DOMAIN_TO_DECLARED` は catalog 報告 → 宣言型の逆向きの写像であり、`_TableInfo` は psycopg SQL object を 1 つも返さない。**§5.42 の「本体の変更は無し」は移動する塊についての条件であり、移動先 module 自身の docstring は対象外である**と裁定し、4c へ回さず本 WP で直した (§1.5 の 34。偽の断言を残さない)。直した後の文は移動した 3 名を明記する。「neither opens a connection nor executes SQL」の部分は移動後も真である (独立レビューが実測)。当該塊は CH-ID を持たないので `--register` と 0f には影響しない。
- **`field` の import 削除 (訂正註 4 の監査照合)**: 移動により `from dataclasses import dataclass, field` の **`field` が読み手 0** になったので削った (唯一の読み手は移動範囲内の `constraints: … = field(default_factory=dict)` だった)。移動前の HEAD と AST の参照件数を比較する訂正註 4 の検査で見つけた。数え方は **scope-aware** である — `postgres.py`:2361 の `_add_field(self, conn, entity, field: str, field_type)` は**仮引数のシャドーイング**であって module の `field` の読み手ではないので除外する。独立レビューが自分の scope-aware 版で再計数し、同じ結論を得た。`dataclass` は読み手 1 (`postgres.py`:477 の `@dataclass class _PoolManagerEntry`) なので残した。移動によって読み手を失った他の import・定数・再 export は無い。
- **40b**: `tools/tests/test_leaf_import_direction.py` の `postgres_types.py` の許可集合を `{"psycopg"}` → `{"psycopg", "dataclasses", "typing"}` に広げた (1 行)。`constraints: dict[str, "FieldConstraints"]` の `FieldConstraints` は **import しない** (W4-2。`from __future__ import annotations` の下で注釈は評価されない。`TYPE_CHECKING` も使わない)。`r2db-api/tests/test_l1_details_vocabulary_ast_scan.py` の行番号 allowlist は `("postgres.py", 1523)` → **`1472`** に行送りし、同ファイル L121-124 と同じ形の行送りコメントを添えた (独立レビューが `_fail_call_sites` を自分で import して `[(1472, 'VALIDATION_FAILED')]` を実測)。`SCANNED_MODULES`・件数 pin の辞書・sib tuple・`_ISOMORPHIC_TARGETS` はいずれも差分 0 (Z4-6 の非対称のとおり。`postgres.py` は `counts` 辞書に含まれず、`postgres_types.py` は denial 0 のまま)。leaf の分類の条件は §5.45 の C-9 のとおり 4b では外してある。
- **変異** (`tools/dev/mutate.py`): **11 件**。内訳は**実装担当 9 (M1〜M9)、監督 2 (S1・S2。W4-4 (a)(d))** である。M1〜M9 は 9 件すべて予想どおり赤で、復元も確かめた。S1・S2 は下の「来歴の証拠」に記す。
- **完了条件 14 件** (変異 11 + 監査照合 3)、**新規テスト 3 本** (`test_postgres_types_leaf_preserves_postgres_facade`・`test_postgres_types_catalog_maps_are_literal`・`test_table_info_fields_and_defaults`)。manifest の 13 件に、独立コードレビューの中-1 で**完了条件を 1 つ足し、変異を M9 として番号付けた** (下記)。
- **閉語彙外の完了条件の取りこぼし (独立レビュー 中-1)**: manifest の完了条件を満たしたつもりで足した 2 行 (`assert "_r2db_json_unknown" not in _DOMAIN_TO_DECLARED`・`assert "smallint" not in _SQL_TYPE_TO_DECLARED`) は、**直前の `==` による辞書全体の固定に論理的に含意される空振り**であった (§1.5 の 32)。レビュー担当が自作変異で実証したとおり、呼出し側 `postgres.py`:891 の `_SQL_TYPE_TO_DECLARED.get(data_type)` を `.get(data_type, "string")` にする変異は**新規 3 本とも緑で素通り**した。壊れる先は、`information_schema.columns.data_type` が未知の型を報告した列が `None` (= JSONB 相当) ではなく宣言型付きで catalog に載り、`_describe_table` / `catalog()` の宣言型が実体と食い違うことである。対応として**完了条件を 13 → 14、変異を 8 → 9 とし、M9 をこの変異そのものに割り当て**、テストを「表の中身を pin する」形から「`postgres.py` を AST で読み、`_DOMAIN_TO_DECLARED.get` / `_SQL_TYPE_TO_DECLARED.get` の **2 つの呼出しサイトが既定値を取らない (`len(args) == 1`)** ことを固定する」形に差し替えた。テストの docstring の断言も、テストが実際に固定する範囲へ直した (§1.5 の 34。初稿は呼出し側の fallback まで断言しながら呼出し側を 1 行も実行していなかった)。**WP-4a の M13 と同型であり、同じ取りこぼしが 2 回続いた。**規律の強化は作業指示書 §5.45 の訂正註 6 に書き、WP-4c に掛けた。
- **来歴の証拠 (記録した HEAD)**: 使い捨て clone は使わない (W4-4 (b))。監督が `tools/dev/finalize.py --no-merge` で WP branch に記録し、その HEAD (`e8906ff`) で `tools/tests` を流して **`486 passed in 35.26s`** を得た。0f (`test_0f_both_peers_all_src_rev_vs_itself_is_green`) は緑である。移動範囲の CH-ID 3 件 (CH-0005・CH-0006・CH-0101) は登録簿の節を動かさず (Z4-4)、`postgres_types.md` も作らない。括弧書きを足した CH-0101 については `docs/code-history/r2db-api/postgres.md` §CH-0101 に訂正の記録を書いた。書式は訂正註 2 のとおり `# ` を落として折り返しを連結した 1 行であり、`--base bec2eeb` の **§9f は 0 件**である (残る 9 件はすべて §4.1 の位置ずれで、訂正註 5 のとおり判定に使わない)。`--register` は exit 0 (`86 files scanned, 427 CH-IDs`)。
- **S2 の実測 — 0f の読み方の非対称 (本 WP の最大の発見)**: 監督の変異 **S2** (完了条件 9) を W4-4 (c) のとおり**作業ツリー**で当てたところ、予想の赤に反して **`S2 expect=red got=green NG | 1 passed`** であった。**実際に回した S2 の spec は、`postgres_types.py`:61 のコメント側の `# history: CH-0005` を `# history: CH-0006` に差し替えるものであり、§5.42 の完了条件 9 が書いた spec (`_TableInfo` docstring の `History: CH-0006` を `History: CH-0005` に差し替える) とは当てた場所が docstring 側ではなくコメント側で、向きも逆である。守る性質は同じ** (移動した塊の history ID が登録簿の節と対応しなくなれば 0f が赤になる) **であり、記録には実際に回したほうを書く** (§1.5 の 34)。原因は 0f の読み方の非対称である — **0f は src を記録済みのツリーから読み、companion (`docs/code-history/` の登録簿) を作業ツリーから読む。したがって src 側の作業ツリー変異は 0f に見えない。** W4-4 (c) はこの枝を想定しており (「0f が作業ツリーの companion を読まず git から読む形であれば、その場で判明するので、その場合は捨て branch 上の記録で取り直し、結果を記録する」)、そのとおり**捨てコミット**の上で同じ変異を回して**赤を得た** (`1 failed, 11 passed, 234 deselected`。赤は 0f の 1 件)。捨てコミットは当日 `c6bbe30` であったが、`git reset --hard e8906ff` で戻したので**到達不能であり、後日この SHA から検証することはできない。SHA は当日の実施の記録として残すだけであり、再現は「同じ差し替え (`# history: CH-0005` → `# history: CH-0006`) を記録した HEAD の上の捨てコミットに載せて 0f を回す」という変異の内容で行う。**戻した後は **§1.4 の 30 のとおり `sleep` の後に sha256 を 2 回照合して一致、変異文字列の全文 grep 0 件、作業ツリーはクリーン**を確かめた。対照的に監督の変異 **S1** (完了条件 10。§CH-0101 に足した訂正の記録を消す) は**作業ツリーのままで赤になった** (`S1 expect=red got=red OK | 1 failed in 3.27s | restore=ok`)。**companion 側の変異は作業ツリーで効き、src 側の来歴の変異は記録しないと効かない。** WP-4a では完了条件 12 が companion 側の変異だったため、この非対称は現れなかった。
- **40a の suite** (`tools/dev/pt.py`、統合前): `r2db-api/tests` `1295 passed`、`MitateDB-api/tests` `1124 passed, 2 subtests passed`、`conformance-tests` `1006 passed`、`tools/tests` `1 failed, 485 passed`。この 1 赤は 0f の 1 件だけで、**新 leaf を作らない本 WP でも出る** — 変更した src がまだ記録されていないため、記録済みのツリーから読む src 側と作業ツリーの companion 側が食い違うからである。裏づけは、同じ実行が記録後の HEAD で `486 passed` になっていることである (上の来歴の証拠)。§9f 起因ではない。
- **手順 0 の走査: 分類の無い参照 0 件。** §5.42 の「付ける / 付けない」の一覧が全件を覆っていた。独立レビューが全ファイル型で走査をやり直し、同じ結論を得た。`docs/work-orders/WORK_ORDER_CODE_COMMENT_PROVENANCE_CS1.md`:3261 の註 1 件は、§5.42 の「付けない」欄が同ファイルについて「表」としか書いていないため厳密には欄の文言に含まれないが、**同じ理由 (過去の作業指示書。§1.8 の 57 により本文を書き換えない) により触らない** (独立レビュー 低-3)。文自体も偽ではない。既知の穴 `docs/design/PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md` L49・L111 (A-3) は移動前から古く、本 WP では触れていない。
- **実装担当が挙げた疑義の決着 (§CH-0101 の登録簿本文と現行ソースの乖離)**: `docs/code-history/r2db-api/postgres.md` の §CH-0101 の逐語写し本文は `Contract 1.7.0 (D-2 (4), WP-2a): …` で始まるのに対し、現行ソースは `Contract 1.7.0: …` である。この乖離は `bec2eeb` の `postgres.py` にも同じ形であり、**本 WP 以前から実在する**。許容しているのは `tools/check_comment_provenance.py`:1830 の `_sentence_reachable` (設計 §4.1 (4) の機械的な括弧内語削除) であり、`_strip_leading_label` の枝ではない (独立レビューが切り分けて実測)。**本 WP は逐語写しの本文 (fence) を 1 文字も変えておらず、拡大も是正もしていない。足した訂正の記録の `old:` もこの古い基準文を参照していない** (`old:` は `` (`_load_field_constraints` below) `` であり `(D-2 (4), WP-2a)` を含まない。`_parse_corrections` → Correction 1 件 / errs 0、`_apply_corrections` → err `None`)。**本 WP では触らない。**
- **レビュー**: 独立 Opus のコードレビュー **高 0 / 中 2 / 低 4 の計 6 件。全件受け入れ**、差し戻し 1 回。中-1 (閉語彙外の空振り) と中-2 (移動先 docstring) は上記のとおり。低-1 は新規テスト直前の空行を 2 行に揃えるもの、低-2 は `f.default if f.default is not MISSING else MISSING` の恒真式を削るもの、低-3 は報告の文言の訂正 (コード変更なし)、低-4 は統合の直前に main を取り込んでから期待値を出すことである。クラスの引き上げは無い (Class B のまま。`tools/change_class.py` → `class=B`。契約・不変条件・`_ISOMORPHIC_TARGETS`・`security/`・`conformance-tests/` に差分 0 を独立レビューが実測)。
- **root gate** (監督、`tools/dev/gate.py`): `3425 passed, 2 subtests passed in 355.26s (0:05:55)`、`judge=PASS`、`pg_database/pg_roles diff 0`、`info=shared pg_database/pg_roles diff 0`。exit 0。3 行目は gate 自身が起動した使い捨てクラスタの差分であり**判定に使う**。4 行目の `info=shared` は共有クラスタの情報であり判定に使わない。期待値は 4a 統合後の `3422` + 新規テスト 3 本 = **`3425`** で、実測と一致する。統合の直前に main (`f3eee90`) を取り込んでからゲートを回した (低-4)。
- **教訓**:
  - **0f の証拠能力は変異の side によって違う。** 0f は **src を記録済みのツリーから、companion を作業ツリーから読む**。したがって **companion 側の変異 (S1) は作業ツリーで赤になり、src 側の来歴の変異 (S2) は記録しない限り緑のまま通る**。src 側の来歴を固定する完了条件は、捨てコミットの上で回して赤を確認する (W4-4 (c) の枝。作業指示書 §5.45 の訂正註 7)。**「作業ツリーで緑だった」を「変異が効かない」と読み違えると、条件を満たさないまま統合する。**
  - **閉語彙外・例外経路の完了条件は、assertion を足すだけでは満たせない。** WP-4a と WP-4b の **2 回続けて**、足した assertion が同種の変異を素通りした。原因も 2 回とも同じで、**既存の等値 assertion に含意される assertion を足していた**ことである。2 回目は独立レビューが**自作変異で実証**して初めて分かった。以後この条件には**番号付きの変異を 1 つ持たせ、実装担当がその変異を当てて赤になった実測を報告に添える** (§5.45 の訂正註 6)。テストは、断言が及ぶ経路 (呼出し側を含む) を実際に実行するか、AST で呼出しサイトの形を固定する。**表の中身を pin するだけのテストでは足りない。**
  - **移動先 module 自身の docstring は、移動によって偽になりうる。** manifest の「本体の変更は無し」は移動する塊についての条件であって、移動先の module header を凍結するものではない。偽の断言を残すと、後続 WP と WP-5 (facade 縮小) が leaf の範囲の宣言として読んで誤った前提を立てる。WP-4a の差し戻し S-1 と同じく、**suite でも変異でも検出されない**種類の欠陥である。
- **次の WP**: WP-4c (統合後の呼称。PG3 + PG2 + `_bind_value` の 8 名 → 新規 `r2db-api/src/r2db_api/postgres_sql.py`)。依頼者裁定 2026-09-16 により §5.43 (旧 4c) と §5.44 (旧 4d) を 1 つの WP として実施するので、**WP-4 は 4a → 4b → 4c の 3 件の直列**である。§5.45 の訂正註 1〜7 がそのまま掛かる。PG4 は Z4-1 で範囲外とした。

### 10.18 WP-4c (PG3 + PG2 + `_bind_value` → `postgres_sql.py`) 実施記録、および WP-4 の完了 (2026-09-16、v1.21 追記)

作業指示書 §5.40 (共通・裁定 Z4-1〜Z4-8)・§5.43 (旧 4c)・§5.44 (旧 4d)・§5.45 (訂正註 1〜7、依頼者裁定による統合後の manifest と、本 WP で足した訂正註 8)。**呼称は統合後の WP-4c であり、「WP-4d」は使わない。**

| WP | 抽出 | merge | 備考 |
| --- | --- | --- | --- |
| WP-4c | r2db `postgres.py` → 新規 leaf `postgres_sql.py` (PG3: `_select_statement`・`_order_by_sql`・`_append_revision_predicate`、PG2: `_COMPARISON_OPERATORS`・`_where_clause`・`_text_expression`・`_predicate_sql`、および `_bind_value` の**計 8 名**) | 本変更 (commit `2f692ca`、merge `fdaf9e8`。6 files changed, 537 insertions(+), 164 deletions(-)) | 1 定数と 7 method を、新規の pure leaf `r2db-api/src/r2db_api/postgres_sql.py` の module 定数と関数へ、**移動前の `postgres.py` での出現順のまま**移した (Z4-8、監督裁定「leaf の中の並び」)。class には委譲属性を **7 つ**残したので、`query`・`_apply`・`_insert`・`_update`・`_delete`・`_apply_upsert`・`apply_schema` の `self.` 呼出しは形を保つ。`_run`・cursor / transaction の塊・`LOCK TABLE`・`SET LOCAL`・driver 例外の変換はいずれも `postgres.py` に残る。leaf の import は `psycopg` (`sql`・`psycopg.types.json.Jsonb`)・`typing` (`Any`)・`.errors` (`fail`・`violation`)・`.postgres_like` (`_escape_like_literal`) だけである |

- **40c**: 本体の差は **4 種**である。(a) 関数 7 つから `self` 引数を除く、(b) sibling 呼出し 4 種 (`self._order_by_sql`・`self._predicate_sql`・`self._text_expression`・`self._bind_value`) を直接呼出しにする、(c) `_select_statement` と `_append_revision_predicate` に既定値の無い引数 `revision_column` を足し `_REVISION_COLUMN` を置き換える (W4-1)、(d) **docstring のインデントが class の method (8 スペース) から module の関数 (4 スペース) へ移るぶんだけ変わる** (下記の裁定 3)。独立レビューが移動前の blob から (a)〜(c) と `inspect.cleandoc` 相当の正規化を当てたものと leaf を照合し、**7 関数すべてが AST で完全一致 (7/7 SAME)、5 種目の差は無い**ことを実測した。`_COMPARISON_OPERATORS` の 8 行も完全一致である。**出現順の保存**も実測した — 移動前の `postgres.py` の行番号昇順 (`_COMPARISON_OPERATORS` 217 → `_select_statement` 1229 → `_order_by_sql` 1256 → `_bind_value` 1474 → `_append_revision_predicate` 1551 → `_where_clause` 1774 → `_text_expression` 1785 → `_predicate_sql` 1809) と、leaf の定義順 (29 → 39 → 67 → 75 → 87 → 113 → 125 → 150) が一致する。
- **`_REVISION_COLUMN` は動かさない (W4-1)**: leaf の namespace に `_REVISION_COLUMN`・`_ID_COLUMN` は無く、2 関数の `revision_column` に既定値は無い。`postgres.py` の呼出し 4 箇所 (`:1200`・`:1560`・`:1579`・`:1675`) がすべて渡す。`_ID_COLUMN` は leaf が 1 度も読まない。leaf は除外した advisory lock の範囲に触れない。注釈の `Predicate` は import しない (W4-2。`from __future__ import annotations` の下で注釈は評価されない)。
- **`_COMPARISON_OPERATORS` は facade へ再 export しない。** 移動後 `postgres.py` に読み手が残らない (module docstring が名前で言及するだけ) ことを実測し、WP-4a と同じく第 2 次裁定 6 に従って削った。新規テストが `not hasattr` で固定する。独立レビューが repo 全体で再計数し、同じ結論を得た。
- **`_escape_like_literal` の誤削除と復元 (訂正註 4 の適用範囲の拡張。裁定 1)**: 訂正註 4 の「読み手を失ったものの検査」を `postgres.py` の中だけで行い、**読み手 0 と判断して import を削ったところ、`r2db-api/tests/test_postgres.py`:1175 の facade テスト (`test_escape_like_literal_leaf_preserves_facade_and_escape_order`) が赤になった** (`1 failed, 1306 passed` → 復元後 `1307 passed`)。実装担当が赤で気づいて自力で戻し、import は **facade 再 export として残した**。監督は**復元が正しい**と裁定し、**検査の範囲を「その module を facade として読む外部のファイル (テストを含む)」まで広げた**。これは作業指示書 §5.45 の訂正註 8-4 として記録し、**WP-5 (facade 縮小と閉止) に掛ける** — WP-5 は export の削除を扱うので、同じ穴が最も効く WP である。なお `Jsonb` は `postgres.py` に読み手 2 件 (`:976`・`:1148`) が残るので残置が正しく、`_FIELD_TYPE_SQL`・`_JSONB_SQL`・`BoundMutation`・`ConstraintPatch` の 0 件は移動前から 0 で本 WP 起因ではない (WP-5 候補)。
- **docstring のインデントの差を「本体の変更」の 4 種目として認めた (裁定 3)**: class の method (8 スペース) から module の関数 (4 スペース) へ移るので生じる、**移動に内在する差**であり、40c の「本文を言い換えない」に反しない。独立レビューが `inspect.cleandoc` 正規化後に AST で 7/7 完全一致を確かめたことを監査照合の材料とした。W3-3・W3-12 の「差分の列挙で示す」と同じ扱いである。
- **手順 0 の走査 (完了条件 25・26)**: 8 名と `_REVISION_COLUMN`・`_ID_COLUMN` を**名前ごとに**走査し、名前ごとの件数と `file:line` を分けて報告した (一括の走査は名前ごとの取りこぼしを集計に隠す。統合時の裁定の 6 の 1)。**独立レビューが同じ走査を自分でやり直し** (完了条件 26)、ヒットするファイルが 9 件であること、MitateDB 側・`conformance-tests/`・`tools/` のヒットが 0 件であることを含め、実装担当の報告と一致した。独立レビューは manifest の「付ける / 付けない」に行の無い参照を **3 件**挙げた — 設計文書の叙述的言及 (本書 §10.16・§10.17 の 2 件と `docs/design/ROADMAP_POST_PHASE7_V1.md` の 1 件) である (低-6)。**監督がこの 3 件を「触らない」と分類した** — いずれも WP の範囲を述べる叙述であり移動後も真だからである。**これにより分類の無い参照は 0 件になり、完了条件 25 は満たされた。****完了条件 25 の「分類の無い参照が 1 件でもあれば止まる」は、止まって監督が分類することで満たされる規定であり、本 WP はそのとおり運用した。****分類されないまま進んだ W3-23 の逸脱とは異なる。**
- **40b**: `tools/tests/test_leaf_import_direction.py` の leaf 一覧に 1 行足し、許可集合は `{"psycopg", "typing", ".postgres_like", ".errors"}` である。`r2db-api/tests/test_l1_details_vocabulary_ast_scan.py` は `SCANNED_MODULES` に `postgres_sql.py` を足し、`counts` 辞書に `"postgres_sql.py": 2` を由来コメント付きで足し (移動した denial 2 件は `_predicate_sql` の中の `"Filter value is incompatible with the selected operator."` と `"Unsupported filter operator."`)、行番号 allowlist を `("postgres.py", 1472)` → **`1439`** に行送りして既存の形の行送りコメントを添えた。独立レビューが `_fail_call_sites` を自分で走らせ、`postgres.py` の bare な site が `(1439, 'VALIDATION_FAILED', False)` の 1 件、`postgres_sql.py` が 2 件であることを実測した。sib tuple と `_ISOMORPHIC_TARGETS` は差分 0 (WF-1。8 名とも未登録)。
- **変異** (`tools/dev/mutate.py`): **25 件**。内訳は**実装担当 22 (M1〜M21 と RV1)、監督 3 (S3・S4・S5。W4-4 (a)(d))** である。M1〜M21 と RV1 は予想どおり赤で、復元も確かめた。S3〜S5 は下の「来歴の証拠」に記す。
- **完了条件 34 件、うち 24 は無効なので実効 33 件** (変異 25 + 監査照合 8)、**新規テスト 12 本** (統合時の下限 11 を 1 本上回る)。統合後の manifest の 32 件に、独立コードレビューの高-1 で条件を 2 件足した (閉語彙外の条件 33 と、その別形を捕まえる RV1 の条件 34)。
- **完了条件 24 は無効 (裁定 2)**: §CH-0054 の訂正の記録は**書かない**。`docs/code-history/r2db-api/postgres.md` §CH-0054 に登録されている塊は「`# R-7, corrigendum m-7: each element gets the same per-column type-aware bind …`」であり、括弧書きを足した文「both call sites of `_where_clause` (`query`/`_apply` above)」を**含まない**。後者は `_predicate_sql` の中の**別の塊**で CH-ID を持たない (実装担当と独立レビューの双方が `extract_all_blocks` で実測。括弧書きの塊は `postgres_sql.py`:155 で `ch_id=None`、CH-0054 は `:166`)。**WF-5 (iv) の適用は「括弧書きを足す塊が CH-ID を持つか」で決まり、近くの塊が CH-ID を持つかでは決まらない。**manifest (完了条件 24) は起草時に塊の単位を取り違えていた。訂正の記録は §CH-0001 の 1 件だけである。
- **閉語彙外の 3 度目の空振りと、その修正 (独立レビュー 高-1)**: 完了条件 33 のために足したテスト `test_comparison_operator_lookup_has_no_fallback_default` は、`postgres_sql.py` を AST で読み `_COMPARISON_OPERATORS.get(...)` の**引数個数が 1 であること**だけを固定しており、**閉語彙外の operator が拒否されるという性質を 1 度も実行していなかった**。実装担当の M21 (`.get(op, sql.SQL("="))`) は捕まるが、同じ性質を壊す別形は素通りする — 独立レビューの自作変異 **RV1** (`.get(predicate.operator) or sql.SQL("=")`) は、**新規 12 本を含む 189 件すべてを緑のまま通した** (`expect=red got=green NG | 189 passed in 0.36s | restore=ok`)。**訂正註 6 の 3 は「断言が及ぶ経路を実際に実行する。それが難しい場合に限り AST で形を固定する」であり、ここは `_predicate_sql(Predicate(field="f", operator="bogus", value=1), None)` の 1 行で実行できるので、AST 固定だけで済ませる理由が無かった** (WP-4b の「呼出し側が別 module」という難しさは無い)。修正後のテストはこの拒否経路を実行し、`VALIDATION_FAILED` と `details == {"violated_declaration": "capability", "field": "where"}` を固定する。docstring も、固定する範囲までしか断言しない文言に直した (§1.5 の 34)。**RV1 を追加の番号付き変異 (完了条件 34) として当て、赤の実測を報告に添えた。****WP-4a の M13、WP-4b の M9 に続く 3 度目の同種の空振りである。**
- **§4.1 (5) は R-37 の抽出 WP にも掛かる (独立レビュー 中-2)**: `postgres.py`:109-110 に足した新規コメントが `-- R-37` / `# WP-4c)` の経緯トークンを含み、`python3 tools/check_comment_provenance.py --base <基点>` が `FAIL (§4.1 (5)) … added line carries a history token` を出した。**これは訂正註 5 の「位置ずれ」に当たらない** — 設計 `docs/design/CODE_COMMENT_PROVENANCE_V1.md` §4.1 (5) が**追加行の経緯トークンを名指しで禁じている**。**例外を作らない**と裁定し、経緯トークンを落として、すぐ下の CH-0002 の同趣旨コメント (`postgres.py`:116) と同じ、経緯トークンを持たない書き方に揃えた。WP-4a・WP-4b もどちらも src に経緯トークンを足していない (独立レビューの実測)。**0f は rev-vs-itself なので追加行を持たず、この赤を捕まえない。`--base` でしか出ない。**放置すれば、R-22 が (4)/(6) で消してきた経緯トークンが src へ 1 件戻り、以後の WP が「§4.1 の赤はすべて位置ずれ」と読む前例になるところであった。
- **移動先 leaf の module docstring の訂正 (独立レビュー 中-1)**: 新 leaf の header docstring に事実でない断言が 3 件あった。(a)「call sites … are unchanged」は、本 WP がまさに `postgres.py`:1200・:1560・:1579・:1675 の 4 箇所に `revision_column` を足しているので偽である (**WP-4a の leaf の文を、事実を確かめずに写したのが原因である**。§1.5 の 34)。(b) 同じ列挙が `_insert` (`postgres.py`:1539 の `self._bind_value`) を落としていた。(c)「returns a `psycopg.sql` fragment plus its bound parameter list」は、7 名のうち (fragment, params) の対を返すのは 3 つだけで、`_bind_value` は `sql` の値を 1 つも返さないので偽である。3 件とも事実に直した。あわせて低-3 により「checks a principal/capability/catalog」を **「does not … read a principal, a capability document, or the catalog」**の形に改め、拒否の語彙 (`violation("capability", …)`) と読み取りの対象を書き分けた。**この docstring は本 WP の新しい文なので 40c の逐語移送の対象外であり、書き換えてよい** (WP-4b の中-2 と同じ扱い)。壊れる先は WP-5 である — 「call sites are unchanged」を信じると `revision_column` の受け渡しを消してよいと読め、`_insert` の呼出しサイトを数え落とす。
- **来歴の証拠 (記録した HEAD)**: 使い捨て clone は使わない (W4-4 (b))。監督が `tools/dev/finalize.py --no-merge` で WP branch に記録し、その HEAD (`2f692ca`) で `tools/tests` を流して **`492 passed in 30.34s`** を得た。0f (`test_0f_both_peers_all_src_rev_vs_itself_is_green`) は緑である。移動範囲の CH-ID **8 件** (CH-0026・CH-0045・CH-0041・CH-0053〜CH-0057) は登録簿の節を動かさず (Z4-4)、`# history:` / `History:` の行を逐語で一緒に移した。`postgres_sql.md` も作らない。括弧書き (位置参照) は **3 箇所** (`postgres.py` の「… (`_select_statement`, below)」の塊、module docstring の `below`、CH-0054 の隣の塊の `above`) で、**訂正の記録は §CH-0001 の 1 件だけ**である (完了条件 24 は無効)。書式は訂正註 2 のとおり `# ` を落として折り返しを連結した 1 行であり、独立レビューが `--base` の **§9f は 0 件**、逐語写しの fence が 1 文字も動いていないこと (追加 14 行のみ) を実測した。
- **監督の変異 S3・S4・S5 — 0f の非対称の 2 度目の実測**: **S3** (完了条件 23。§CH-0001 に足した訂正の記録を消す) は**companion 側なので作業ツリーのままで赤**になった (`S3 expect=red got=red OK | 1 failed in 2.90s | restore=ok`)。対して **S4** (完了条件 21。`_append_revision_predicate` の `History: CH-0045` → `History: CH-0026`) と **S5** (完了条件 22。`_predicate_sql` の `# history: CH-0057` → `# history: CH-0056`) は **src 側なので作業ツリーでは 0f に見えず**、訂正註 7 の手順どおり**捨てコミット** (当日 `a9e5c88`・`bbd1c35`) の上で回して**赤を確認した** (どちらも `1 failed, 11 passed, 234 deselected`。赤は 0f の 1 件)。捨てコミットは `git reset --hard 2f692ca` で戻したので**到達不能であり、後日この SHA から検証することはできない。SHA は当日の実施の記録として残すだけであり、再現は「同じ差し替えを記録した HEAD の上の捨てコミットに載せて 0f を回す」という変異の内容で行う。**戻した後は **§1.4 の 30 のとおり sha256 を 2 回照合して一致**、**CH-ID の件数** (CH-0026・CH-0045・CH-0056・CH-0057 が各 1)、**記録した HEAD との差分 0** を確かめた。**WP-4b の S1・S2 で判明した非対称 (§10.17 の教訓) が、そのまま 2 度目も再現した。**
- **40a の suite** (`tools/dev/pt.py`): `r2db-api/tests` **`1307 passed`**、`tools/tests` (統合前) **`1 failed, 485 passed`** の 2 本だけである。**WP-4c では `MitateDB-api/tests` と `conformance-tests` を実装担当に回させず、監督の完了ゲート (`3451 passed, 2 subtests passed`) が覆う形にした** — 直前 3 回、実装担当が `conformance-tests` を背景実行して待機状態で止まったためである (§10.16・§10.17 の 40a の欄が 4 本を挙げるのに対し、本 WP が 2 本なのはこの理由による)。この 1 赤は 0f の 1 件だけで、変更した src がまだ記録されていないためである (§10.17 の機構と同じ)。裏づけは、同じ実行が記録後の HEAD で `492 passed` になっていることである (上の来歴の証拠)。§9f 起因ではない (`--base` の §9f が 0 件であることを独立レビューが別に実測した)。
- **`--base` の §4.1 の赤の内訳 (独立レビュー 低-5。完了条件 31 の材料)**: `--base` の §4.1 は **21 件**で、**19 件は訂正註 5 の類型** (位置ずれ・CH-ID 塊の移動・新ファイルの `git show` 不能)、**1 件は中-2** (上記のとおり判定に使い、直した)、**残る 1 件は `postgres.py`:1 の `CH-0001 basis block … not derivable`** である。最後のものは、**`--base` が旧 blob を basis に取る一方で、訂正の記録は新しい本文に合わせて書かれるために構造的に必ず出る**もので、0f (src を記録済み HEAD から読む) では出ない。**完了条件 31 の証拠は 0f であって `--base` ではない。**
- **`_order_by_sql` の閉語彙外の direction (独立レビュー 低-4。足さずに記録した)**: `_order_by_sql` は `"ASC" if direction == "asc" else "DESC"` であり、**閉語彙外の direction が黙って `DESC` になる**。**移動前から同じ挙動**であり、変えれば挙動の変更になる (設計 §1.1 の不変の公開意味に触れる) ので **WP-4 の範囲外**とし、**R-39 候補**として作業指示書 §5.45 の訂正註 8-3 に記録した。訂正註 6 の「閉語彙外・例外経路の場面を置く」は本 WP では PG2 側の 1 件 (完了条件 33・34) で満たす。
- **レビュー**: 独立 Opus のコードレビュー **高 1 / 中 2 / 低 5 の計 8 件。全件受け入れ**。高-1・中-1・中-2・低-3 は上記のとおり。低-1 は `test_foundation.py`:3432 の docstring の `second次裁定 6` を `第 2 次裁定 6` に直すもの、低-2 は `postgres.py`:223-225 の `def _run` 直前の空行を 2 行に戻すもの、低-4 と低-5 は監督が記録に回した情報、低-6 は設計文書 3 件の叙述的言及を触らない判断である。クラスの引き上げは無い (Class B のまま。`tools/change_class.py` = B、`_ISOMORPHIC_TARGETS` 差分 0、8 名とも未登録を独立レビューが実測)。公開リポジトリ規律は `tools/public_value_scan.py` exit 0、`tools/check_doc_refs.py` exit 0、追跡 `.md` の 0 バイト 0 件である。
- **root gate** (監督、`tools/dev/gate.py`): **`3451 passed, 2 subtests passed in 299.76s (0:04:59)`**、`judge=PASS`、`pg_database/pg_roles diff 0`、`info=shared pg_database/pg_roles diff 0`。exit 0。3 行目は gate 自身が起動した使い捨てクラスタの差分であり**判定に使う**。4 行目の `info=shared` は共有クラスタの情報であり判定に使わない。**期待値は `3439`** (別セッションの R-44 WP-3 が main を `f051f99` へ進めた後の基準) **+ 新規テスト 12 本 = `3451`** で、実測と一致する。
- **教訓**:
  - **閉語彙外の条件は、3 度同じ形で空振りした。**WP-4a (M13)・WP-4b (M9) に続き、WP-4c でも足したテストが同種の変異を素通りした。今回の原因は「既存の等値 assertion に含意される assertion」ではなく、**呼出しサイトの形 (AST の引数個数) だけを pin し、性質そのものを 1 度も実行していなかった**ことである。**訂正註 6 の 3 の優先順位 (まず実行、難しい場合に限り AST) を、「難しい」の判定ごと守る。**1 行で呼べる経路を AST 固定で代替してはならない。**3 度とも、独立レビューが自作変異で実証して初めて分かった。**
  - **§4.1 (5) に R-37 の例外は無い。**抽出 WP が src へ足す新しいコメントにも、追加行の経緯トークンの禁止はそのまま掛かる。**0f はこれを構造的に捕まえられない** (rev-vs-itself なので追加行が無い) ので、`--base` の §4.1 を「すべて位置ずれ」と読むと恒久的な盲点になる。§4.1 の赤は**類型ごとに分けて読む** — 位置ずれ、`--base` の basis に由来する構造的なもの、そして (5) の真の赤である。
  - **「読み手 0」は、移動元 module の中だけでは決まらない。**facade として外部 (テストを含む) から読まれている import は、module 内の参照件数では 0 に見える。**WP-5 は export の削除そのものを扱うので、この穴が最も効く。**
  - **manifest の完了条件は、塊の単位を取り違えることがある。**完了条件 24 は「近くの塊が CH-ID を持つ」ことから書かれており、実際に括弧書きが入る塊は CH-ID を持たなかった。**起草時の見立てを、着手時に `extract_all_blocks` の実測で確かめる。**

#### WP-4 の完了

**WP-4 (backend 内の SQL assembly 分離) は、本 WP をもって完了した。**

| # | WP | 抽出 | merge | root gate |
| --- | --- | --- | --- | --- |
| 1 | WP-4a | MitateDB `backend_postgres.py` → 新規 `postgres_sql.py` (BP3、2 定数と `_where_sql`) | `acb257e` | `3422 passed, 2 subtests passed` |
| 2 | WP-4b | r2db `postgres.py` → 既存 leaf `postgres_types.py` (PG1、2 定数と `_TableInfo`) | `2e94bbf` | `3425 passed, 2 subtests passed` |
| 3 | WP-4c | r2db `postgres.py` → 新規 `postgres_sql.py` (PG3 + PG2 + `_bind_value`、8 名) | `fdaf9e8` | `3451 passed, 2 subtests passed` |

- **当初の 4 件が 3 件になったのは、依頼者裁定 (2026-09-16、逐語「4c・4dをまとめてください」) により旧 4c (PG3) と旧 4d (PG2 + `_bind_value`) を 1 つの WP にまとめたためである** (作業指示書 §5.45 の訂正註。Z4-2 の「4 件の直列」を上書きする。Z4-1・Z4-3〜Z4-8 と Z4-7 の「直列・並行しない」は変わらない)。
- **範囲外とした 2 件**: **PG4** (`apply_schema` 内の DDL 組立) は **Z4-1 により実測で範囲外** — SQL の組立はいずれも 1〜2 行の単発で、直後に同じ分岐の中で `_run()` され、`LOCK TABLE` と地続きであり、設計 §7 の停止条件に当たる。**CE6 の残り 7 method** は **W3-11 により範囲外**である。
- **次は WP-5 (facade 縮小と閉止。設計 §4 の最後の WP)** である。R-37 は開いたままであり、WP-5 の manifest は未作成である。**本 WP が WP-5 に引き渡す材料**は、(i) 作業指示書 §5.45 の訂正註 8 の 7 項目 (いずれも WP-5 に掛かる)、(ii) 読み手 0 のまま移動前から残る `_FIELD_TYPE_SQL`・`_JSONB_SQL`・`BoundMutation`・`ConstraintPatch` (本 WP 起因ではない。WP-5 候補)、(iii) `_escape_like_literal` と `_FIELD_TYPE_SQL`/`_JSONB_SQL` の facade 再 export が外部のテストに読まれているという実測 (§10.18 の裁定 1) である。

---
