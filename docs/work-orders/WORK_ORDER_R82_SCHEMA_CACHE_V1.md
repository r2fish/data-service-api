# 作業指示書 — スキーマ情報のプロセス内キャッシュ (台帳 R-82)

- 版: v1 (2026-10-04)。基点は local main `9a65cbc`。台帳は `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の R-82 行。
- 着手の根拠: 依頼者指示 2026-10-04 (逐語): 「R-82をチップで出してください」。
- 規模 M。クラスは **D** (`security/CONTROL_MAPPING.md` の「live catalog」の主張と位置参照、`_ISOMORPHIC_TARGETS` の行の追加に触れる。台帳行の見込みは B だった)。役割: 実装担当、レビュー担当、監査担当 (Class D)、監督。
- 訂正は本文を書き換えず、§7 に訂正註として追記する。

## 1. 着手時の突き合わせ (2026-10-04、main `9a65cbc`)

| 台帳行の前提 | 実物 | 判定 |
|---|---|---|
| スキーマ情報を要求ごとに読み直している可能性 | r2db-api: `PostgresCell._load_catalog` を `query` / `transact` / `catalog` が要求ごとに 1 回呼ぶ (`information_schema` の列 1 文 + `pg_index` 1 文、`transact` はさらに制約 registry 1 文を savepoint の中で)。MitateDB-api: `cell.py` が 1 要求の中で `field_domains` / `field_types` / `field_types_and_constraints` を複数回呼び、各回 2 文 | 成り立つ |
| reserved 名の判定を読み直している | 両 peer とも DB を読まない (r2db `_reject_reserved_entity_name`、MitateDB `check_reserved` は定数との照合) | 成り立たない (対象外) |
| DB 上の版数が在る | r2db `_r2db_schema_revision`、MitateDB `_mdb_schema_revision`。schema 操作は全種類が DDL・registry 書き込みと同じ transaction で上げ、dry run・失敗では上がらない (r2db `apply_schema` の 1 箇所、MitateDB の DDL 3 メソッド) | 成り立つ |
| MitateDB の catalog 読みは呼びごとに独立した transaction (R-80 メモ F3) | R-115 以後は要求の scope の developer 接続の 1 transaction の中 (`db=app` の transaction は 2/要求) | 変わった (文数は残る) |
| R-120 / R-113 の entity lock | data 操作は共有 lock を catalog 読みの前に取り、schema 操作は排他 lock を commit まで持つ。r2db の `query` と dry run、MitateDB の `query` は lock を取らない | キャッシュの照合は lock の後に置く (§3 D-4) |
| R-42 (文ごとの `execution_ms` 検査)、R-79 (prepared statement) | 文を減らす方向の変更であり、どちらの機構も変えない | 影響なし |

## 2. 実測 (着手前)

`tools/perf_baseline.py --warmup 10 --n 100 --concurrency 1 --roundtrip` (2026-10-04、`commit=9a65cbc`、`stale=1` は 0 本)。http と socket の値は同じ。

| peer | 接続 | query | mutate | batch | cross_entity |
|---|---|---|---|---|---|
| r2db-api | runtime | 6.00 | 8.00 | 12.00 | - |
| MitateDB-api | runtime | 3.00 | 4.00 | 8.00 | 5.00 |
| MitateDB-api | developer | 10.00 | 6.00 | 22.00 | 10.00 |

(文/要求。MitateDB の developer の文は timeout 設定 1 文を除きすべて catalog 読み。)

文ごとの時間 (使い捨てクラスタ、entity 3 個、同じ接続で 400 回を交互に実行、prepared。load average 22 の下での値で、絶対値ではなく比を読む): r2db の列の読み p50 0.797 ms、index の読み 0.200 ms、MitateDB の `information_schema.columns` の読み 0.235 / 0.216 ms、registry の読み 0.060 ms、**版数 1 行の読み 0.042 ms**、data の SELECT 0.043 ms。

**監督の判断**: catalog 読みは 1 文あたり data 文の 5〜19 倍の時間を使い、r2db は 2〜3 文、MitateDB は 5〜21 文/要求を占める。2026-10-04 の基準値 (`docs/design/TEST_POSTGRES_ISOLATION_V0_1.md` §11.2、http p50: r2db query 1.820 ms、MitateDB query 1.482 ms) に対して雑音の範囲 (台帳 §0.1.4) を超える見込みがあるので、実装する。

## 3. 設計

- **D-1 (鍵)**: キャッシュの鍵は DB から読んだ **(database の oid, schema revision)** の組 (以下 token)。1 文で読む: `SELECT (SELECT oid FROM pg_database WHERE datname = current_database()), revision FROM <revision table>`。oid は同じ名前の DB の作り直し (revision が 0 に戻る) を別の token にする。revision の行が無いときは token 無しとし、キャッシュを使わず live で読む。
- **D-2 (器)**: 両 peer に同名・同文の class `_RevisionKeyedCache` を置く (r2db `postgres.py`、MitateDB `backend_postgres.py`)。1 つの token の値だけを持つ。`get(token, key)` は token が一致するときだけ値を返す。`put(token, key, value)` は、持っている token と違えば中身を捨てて入れ替える。ただし同じ oid で revision が小さい token の `put` は捨てる (新しい内容を古い token で上書きしない)。`threading.Lock` で守る。backend オブジェクト (application ごと) の instance 属性として持ち、class 属性・module 変数にしない。peer 間でコードを共有せず、同型性テスト (`_ISOMORPHIC_TARGETS`、両 peer の `tests/test_audit_query.py`) に 1 行足して固定する (件数 pin と pin テストの名前も実測で更新。`docs/design/MODULE_REFACT_ARCHITECTURE_V1.md` §6 の規律)。
- **D-3 (読む順)**: token を先に読み、その後に live の catalog を読んで token の下に入れる。逆順にしない (READ COMMITTED では、後から読んだ token の下に古い内容が入り得る)。
- **D-4 (lock との関係)**: token は、その要求が entity lock を取った後に読む。r2db は `_lock_entities` の後の、いま `_load_catalog` を呼んでいる位置で読む。MitateDB は token を scope に 1 回だけ覚え (`RequestScope` に slot を足す)、`_acquire_advisory` が lock を取ったら覚えた token を捨てる。
- **D-5 (schema 操作は使わない)**: r2db の `apply_schema` は `_load_catalog` を直接呼び続け、キャッシュを読まず書かない。MitateDB は `scope.kind == "schema"` の scope ではキャッシュを読まず書かない (未 commit の DDL や dry run の内容を入れない)。
- **D-6 (r2db)**: `PostgresCell._catalog(conn, *, with_constraints=True)` を足し、`catalog` / `query` / `transact` の 3 箇所の `_load_catalog` 呼び出しをこれに替える。鍵は `with_constraints` の真偽。入れる前に読み取り専用にする (`types.MappingProxyType`: 最上位、`_TableInfo` の 3 つの dict、index の各 entry)。`_load_catalog` 自体は変えない (呼ばれるたびに live で読む)。
- **D-7 (MitateDB)**: collection ごとの snapshot (domains、declared types、constraints) を 1 つの loader で読む (列 1 文 + registry 1 文。列が 0 行なら `NotFoundError` を上げ、入れない)。`field_domains` / `field_types` / `field_constraints` / `field_types_and_constraints` は snapshot から **コピーを返す** (constraints の `enum` の list を含む)。例外の対応 (timeout → `ResourceLimitError`、`UndefinedTable` → `StorageConfigurationError`、transient、その他) は現行の 4 メソッドと同じにする。`schema_count` / `all_field_types` / `all_field_constraints` / `schema_revision` は変えない。`StorageBackend` の interface と `backend_sqlite.py` の挙動は変えない (`RequestScope` の slot の追加だけ)。
- **D-8 (application ごとの migration の規則)**: 「catalog 読みの結果を変える書き込みは同じ transaction で schema revision を上げる」が成り立つ範囲を固定する。各 peer に静的テストを 1 本置く: `platform_upgrades` が列挙する application ごとの upgrade script のそれぞれが、revision を上げる文を含むか、理由付きの許可表 (r2db: 9・10・11 = bookkeeping table だけを作る / MitateDB: 6・8・9・10・15 = R-82 より前の script で、その番号を要求する package のプロセスは起動時の台帳照合の後にしか要求を受けない) に載っていること。新しい番号は revision を上げるか、表に理由を書くかを迫られる。
- **D-9 (範囲外)**: 契約 (`spec/`)・`conformance-tests/`・migration・ops CLI は変えない。pipeline 化と `SET LOCAL` の 1 文化は R-80。稼働中の同じ DB への書き戻し (restore) は両 peer の runbook に手順が無く、手順を作るときに「プロセスの再起動」を条件にする (引き継ぎ書に残す)。

## 4. 完了条件と変異

各 peer の `tests/test_r82_catalog_cache.py` に置く (PostgreSQL の実物で。観測対象が 1 件以上あることを assert する)。1 変異 = 1 エントリ = 1 テスト (`mutate.py` は最初の失敗で止まる)。

| # | 完了条件 | テスト (両 peer) | 変異 (これだけを壊す) |
|---|---|---|---|
| 1 | 定義が変わらない間、2 回目以降の要求は catalog を読まない (token の 1 文だけ) | 温めた後の query と data 書き込みで loader の呼び出しが 0、token の読みが要求ごとに 1 | `get` が常に `None` を返す |
| 2 | 別プロセス相当 (同じ DB に繋いだ別の cell / backend) が定義を変えたら、次の要求は新しい定義で検証する。足した field が使える方向と、狭めた enum が拒否される方向の両方 | 2 つの独立した cell / backend | `get` が token を照合しない |
| 3 | dry run の schema 操作と失敗して rollback した schema 操作は、キャッシュを汚さない | dry run の add_field の後、その field を名指す要求が拒否される | r2db: `apply_schema` の変更後の再読みを `_catalog` に替える / MitateDB: `kind == "schema"` の除外を外す |
| 4 | lock 待ちの間に commit された schema 操作の結果で検証する | r2db: 排他 lock を持つ schema 操作の commit を待った data 操作 (`test_r120_entity_lock.py` の止め方)。MitateDB: scope で読む → 別 backend が変える → `lock_entities` → 読む | r2db: token の読みを `_lock_entities` の前へ動かす / MitateDB: `_acquire_advisory` の token 破棄を外す |
| 5 | application ごとに別のキャッシュ | 同じ entity 名・違う field を持つ 2 application が各自の定義で検証する。加えて token が (その DB の `pg_database.oid`, revision) であることを独立の読みと突き合わせる | token の文から oid を落とす (定数にする) |
| 6 | 古い token の `put` は新しい token の内容を上書きしない | class の単体テスト | 順序の guard を外す |
| 7 | 返した値を書き換えても次の要求に影響しない | r2db: 返り値への代入が `TypeError`。MitateDB: 返り値を書き換えた後の次の読みが元のまま | r2db: 読み取り専用化を外す / MitateDB: コピーをやめる |
| 8 | `_RevisionKeyedCache` は両 peer で同文 | `_ISOMORPHIC_TARGETS` の行 | 片方の本体を 1 語変える |
| 9 | D-8 の規則 | 静的テスト | 許可表から 1 番号を外す |
| 10 | 既存の R-120 / R-113 / R-102 / R-42 のテストと両 peer の suite が緑 | `pt.py` で両 peer の `tests/` と `conformance-tests/` | 監査照合 (集計行) |
| 11 | 往復数と時間の前後 | `tools/perf_baseline.py` (監督) | 監査照合 (§6 の記録) |
| 12 | 本表に対応の無い行が無い | - | 監査照合 |

## 5. 実装担当への指示

- 変えてよいファイル: `r2db-api/src/r2db_api/postgres.py`、`r2db-api/src/r2db_api/postgres_types.py` (docstring が事実と食い違う場合だけ)、`MitateDB-api/src/mitatedb_api/backend_postgres.py`、`MitateDB-api/src/mitatedb_api/backend.py` (`RequestScope` の slot)、両 peer の `tests/test_r82_catalog_cache.py` (新規)、両 peer の `tests/test_audit_query.py` (`_ISOMORPHIC_TARGETS` の 1 行と件数 pin)、行番号・件数を固定する既存の静的テスト (実測で更新)、`docs/code-history/` (来歴の道具が求める場合)、`security/CONTROL_MAPPING.md` (§5.1)。それ以外に触れる必要が出たら実装せずに報告する。
- 既存の docstring・経緯コメントは言い換えない。事実と食い違う文だけを最小限に直し、`tools/check_comment_provenance.py` を緑にする。新しい関数の docstring は、変異の結果を得た後に、テスト名を引用して書く。
- 道具: `tools/dev/pt.py -C <worktree> -- <peer>/tests -q -n 5 --dist loadgroup` (peer ごと)、`conformance-tests` は 1 回の前景実行、変異は `tools/dev/mutate.py <spec> -C <worktree>`。suite 全体 (根) と `gate.py`・`finalize.py`・git の書き込み操作は実行しない。下請け Agent を使わない。REFUSED (75) は迂回せず報告する。
- 報告: 変更ファイル一覧、変異表 (道具の出力行)、集計行、`log=` のパス、設計と違えた点、手元で確かめていない点。

### 5.1 CONTROL_MAPPING

版 3.21。位置参照は挿入行に合わせて機械的に直す。主張は次の 3 点を、実装後の行番号で直す (文面は監督が確定する):

- SI-01 r2db-api と SI-05 r2db-api の「live `information_schema` catalog (`_load_catalog`)」: 「その DB の live catalog から読んだ内容。`query` / `transact` / `catalog` は、同じ transaction で読んだ (database oid, schema revision) が一致する間だけプロセス内の写しを使い、schema 操作は常に live で読む」。
- MitateDB-api の「Developer-connection catalog reads: 8 of them」: 読みの数え方を実装後の実物に合わせる。
- SI-11 両 peer: 「data 操作の検証に使う定義は、entity lock の後に読んだ token のもの」を既存の entity lock の主張に続けて 1 行。証拠は §4 の 2・3・4 のテスト。

## 6. 記録 (監督が埋める)

### 6.1 往復数の前後 (§4 の 11)

`tools/perf_baseline.py --warmup 10 --n 100 --concurrency 1 --roundtrip`、2026-10-04、前は `commit=9a65cbc`、後は `commit=9a65cbc-dirty` (本変更の作業ツリー)。両 run とも `stale=1` は 0 本。http plug の `conn=` 行 (文/要求)。

| peer | 接続 | query | mutate | batch | cross_entity |
|---|---|---|---|---|---|
| r2db-api | runtime | 6.00 → 5.02 | 8.00 → 6.00 | 12.00 → 10.00 | - |
| MitateDB-api | runtime | 3.00 → 3.00 | 4.00 → 4.00 | 8.00 → 8.00 | 5.00 → 5.00 |
| MitateDB-api | developer | 10.00 → 3.00 | 6.00 → 3.00 | 22.00 → 3.00 | 10.00 → 3.04 |

r2db の query の 5.02 と MitateDB の cross_entity の 3.04 の端数は、温まる前の最初の要求の live 読みである。MitateDB の developer の 3 文は timeout 設定 2 文と token 1 文。

### 6.2 時間の前後 (§4 の 11)

`--warmup 20 --n 200` (K=1) を main のコードと作業ツリーのコードで交互に 2 組、同日に取った。**開発機は計測の間ずっと load average 20〜41 だった** (本件と無関係の別プロジェクトの処理。suite lock の外の負荷)。http plug の p50 は 2.1〜11.4 ms で、負荷の無い日の記録 (`docs/design/TEST_POSTGRES_ISOLATION_V0_1.md` §11.2、1.2〜2.3 ms) の数倍あり、同じ行の 2 組の差が −79% から +188% まで割れた。**この時間の値は前後の判定に使えない** (台帳 §0.1.4 の閾値との突合はしていない)。時間の根拠は §2 の文ごとの値 (catalog 読み 1 文 0.2〜0.8 ms 対 token 1 文 0.04 ms、同じ接続で交互に実行) と 6.1 の文数の差である。負荷の無い状態での `--warmup 20 --n 200` の取り直しは未実施であり、引き継ぎ書に残す。

K=32 (`--warmup 3 --n 15 --concurrency 32`、main のコード → 作業ツリーのコードの順に 1 組、load average は開始時 5.69 / 15.44 / 24.21 と 4.43 / 11.95 / 21.77) は 14 行すべてで p50 が下がった: r2db-api-http query 39.574 → 35.858 ms (−9.4%)、mutate 42.199 → 36.670 (−13.1%)、batch 49.747 → 42.480 (−14.6%)、MitateDB-api-http query 36.504 → 29.372 (−19.5%)、mutate 34.122 → 30.743 (−9.9%)、batch 52.931 → 34.411 (−35.0%)、cross_entity 40.288 → 30.004 (−25.5%)、socket の 7 行は −10.4% 〜 −21.2%。1 組だけの値であり、run 間の雑音 (p50 で 30% まで) の内側の行が多い。悪化した行は無い。

K=1 の 2 組の p50 (ms、http plug、前 → 後):

| plug | op | 1 組目 | 2 組目 |
|---|---|---|---|
| r2db-api-http | query | 7.058 → 7.574 | 8.347 → 6.985 |
| r2db-api-http | mutate | 8.300 → 7.333 | 5.886 → 5.029 |
| r2db-api-http | batch | 9.975 → 7.355 | 9.479 → 4.694 |
| MitateDB-api-http | query | 7.389 → 6.594 | 6.852 → 6.559 |
| MitateDB-api-http | mutate | 3.026 → 6.278 | 7.122 → 5.092 |
| MitateDB-api-http | batch | 10.008 → 2.109 | 11.444 → 6.584 |
| MitateDB-api-http | cross_entity | 5.180 → 5.799 | 2.354 → 6.781 |

### 6.3 負荷の低い状態での取り直し (2026-10-04 16:33〜16:37、完了ゲートの後)

`--warmup 20 --n 200` (K=1)。前 = main `b378989` のコード、後 = 同じ main に本変更を載せた作業ツリー。交互に 2 組。load average は 1 組目 3.9〜4.2、2 組目の前の run の終わりに 10.26 (2 組目の socket の「前」の値はその影響を受けている)。p50 (ms):

| plug | op | 1 組目 | 2 組目 |
|---|---|---|---|
| r2db-api-http | query | 1.624 → 1.407 (−13.4%) | 1.787 → 1.414 (−20.9%) |
| r2db-api-http | mutate | 1.785 → 1.216 (−31.9%) | 1.868 → 1.400 (−25.1%) |
| r2db-api-http | batch | 2.053 → 1.396 (−32.0%) | 2.063 → 1.631 (−20.9%) |
| MitateDB-api-http | query | 1.430 → 1.104 (−22.8%) | 1.481 → 1.171 (−20.9%) |
| MitateDB-api-http | mutate | 1.252 → 1.015 (−18.9%) | 1.158 → 1.154 (−0.3%) |
| MitateDB-api-http | batch | 2.138 → 1.144 (−46.5%) | 2.303 → 1.243 (−46.0%) |
| MitateDB-api-http | cross_entity | 1.452 → 1.039 (−28.4%) | 1.575 → 1.169 (−25.8%) |
| r2db-api-socket | query | 6.126 → 4.886 (−20.2%) | 12.210 → 4.857 |
| r2db-api-socket | mutate | 5.683 → 4.840 (−14.8%) | 8.501 → 4.839 |
| r2db-api-socket | batch | 5.398 → 5.058 (−6.3%) | 9.790 → 5.145 |
| MitateDB-api-socket | query | 4.966 → 4.457 (−10.2%) | 17.607 → 4.517 |
| MitateDB-api-socket | mutate | 4.965 → 4.469 (−10.0%) | 19.257 → 4.686 |
| MitateDB-api-socket | batch | 7.487 → 5.396 (−27.9%) | 9.280 → 4.823 |
| MitateDB-api-socket | cross_entity | 4.867 → 5.162 (+6.1%) | 5.289 → 4.620 (−12.6%) |

p95 は 1 組目の 14 行のうち 12 行で下がり、上がった 2 行は r2db-api-socket batch +10.1% と MitateDB-api-socket cross_entity +7.2% (台帳 §0.1.4 の閾値の内側)。http の 7 行は 2 組とも p50 が下がり、14 個の差のうち 13 個が −13% 以下である。

文ごとの時間 (使い捨てクラスタ、entity 3 個、同じ接続で 400 回を交互に、prepared、load average 4.56 / 5.26 / 7.86。出力のまま):

```
r2db_columns   p50_ms=0.342 p95_ms=0.383
r2db_indexes   p50_ms=0.075 p95_ms=0.085
mdb_columns    p50_ms=0.086 p95_ms=0.105
mdb_count      p50_ms=0.081 p95_ms=0.094
mdb_registry   p50_ms=0.019 p95_ms=0.028
revision       p50_ms=0.015 p95_ms=0.019
token          p50_ms=0.015 p95_ms=0.022
data_select    p50_ms=0.014 p95_ms=0.022
```

`token` が実装の文 (`SELECT (SELECT oid FROM pg_database WHERE datname = current_database()), revision FROM …`) で、版数だけの読みと同じ時間である。

### 6.4 完了ゲートと変異

- 完了ゲート (監督、main `b378989` + 本変更の作業ツリー): `gate: 5248 passed, 2 subtests passed in 556.94s (0:09:16)`、`judge=PASS`、label r82、`pg_database/pg_roles diff 0`。`COLLECTION_FLOOR` 5232 → 5248 (両 peer の `tests/test_r82_catalog_cache.py` 各 8 本)。
- peer の suite (載せ直しの後): r2db-api `1784 passed`、MitateDB-api `1937 passed, 2 subtests passed`。
- 変異 (載せ直しの後、`tools/dev/mutate.py`): `mutate: 19 mutations, 19 as expected, restores verified 4/4 files (sha256 x2)`。§4 の 1〜9 を両 peer で 18 本 (R1〜R9、M1〜M9。6 は訂正註 1 の形) と、レビュー担当の X1 (`query` が制約 registry を読む退行)。
- `tools/check_comment_provenance.py --base main` の赤は 7 行で、監督が正当な赤と裁定した: コードの変更 (§4.1 (1)) 4 行、削除した 2 helper の docstring の消滅 2 行、`field_types` の except 節の中のコメントの anchor の移動 1 行 (コメントは src に逐語で残る。道具の既知の穴 9 の形)。`--register` は OK。
- レビュー (コードレビュー 1 回) の指摘 6 件・懸念 1 件・情報 1 件と、監査の指摘・観察の裁定は引き継ぎ書 `docs/work-orders/HANDOVER_20261004_R82_FABLE.md` の「裁定」節に在る。

## 7. 訂正註

- **訂正註 1 (2026-10-04、監督裁定)**: §3 D-2 の「同じ oid で revision が小さい token の `put` は捨てる」を取り消す。token が違う `put` は常に中身を捨てて入れ替える。理由: 同じ DB への書き戻しで revision が戻ると、戻った後の内容が入らず、revision が元の値に達した要求が書き戻し前の内容で検証する (実装担当の指摘)。古い token の読み手が入れ替えても、内容は必ずその token を読んだ後の live 読みであり、次の新しい token の読み手は一致せずに読み直す。§4 の 6 は「token が違う `put` は前の token の値を全部捨てる (revision が小さくなる方向と oid が変わる方向の両方)」、変異は「入れ替え時に値を捨てない」に差し替える。
- **訂正註 2 (2026-10-04、監督裁定)**: §5 の「変えてよいファイル」に、キャッシュの導入で観測点が変わった既存テスト (r2db `test_constraints_declaration.py`・`test_expired_request_checks.py`・`test_idempotency_records.py`・`test_r120_entity_lock.py`、MitateDB `test_expired_request_checks.py`・`test_postgres.py`) と `docs/code-history/` の両 peer の companion を加える。MitateDB の `_field_types_locked` / `_field_constraints_locked` は参照が 0 になったので削除した (docstring は companion に置けない — 参照元の無い節を道具が拒む。経緯は git に残る)。
- **訂正註 3 (2026-10-04、監査担当の指摘)**: §2 の「MitateDB の developer の文は timeout 設定 1 文を除き」の「1 文」は誤りで、timeout 設定は `SET LOCAL` 2 文である (§6.1 の記述が正しい)。着手前の query 10 文は timeout 設定 2 文 + catalog の reader 4 回 × 2 文。
- **訂正註 4 (2026-10-04、監査担当の指摘)**: §2 の文ごとの時間は出力を保存しておらず、「版数 1 行の読み」は実装の token の文 (`pg_database` の副問い合わせを含む) ではなかった。§6.3 に、token の文を足して負荷の低い状態で取り直した値を出力のまま置く。§6.2 の「負荷の無い状態での取り直しは未実施」は §6.3 で実施した。
- **訂正註 5 (2026-10-04、監督)**: §5.1 の CONTROL_MAPPING の版は 3.22 である (3.21 は並行チャットの R-22 の変更セットが先に取った)。作業ツリーは main `e09472b`、続いて `b378989` に載せ直し、載せ直しの後に両 peer の suite と変異 19 本を取り直した。§4 の 4 の r2db の変異 (R4) は「catalog の読み全体 (token と live 読み) を `_lock_entities` の前へ動かす」であり、文面どおりの「token の読みだけを動かす」はレビュー担当の変異 X2 が赤を実測した (載せ直しの前のソースで)。§4 の 7 の MitateDB の変異 (M7) は constraints のコピーを外す。
