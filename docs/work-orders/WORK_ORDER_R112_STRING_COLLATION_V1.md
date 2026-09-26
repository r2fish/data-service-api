# 作業指示書 — R-112 application DB の文字列照合を `C` にし、backend 間の文字列順序を揃える

## 0. 版数・位置づけ

- **v1.0 (2026-09-26)。** 基点 local main `0d7065c` (契約 1.11.0。契約は変えない)。Change Set Manifest 形式 (`docs/design/ROADMAP_POST_PHASE7_V1.md` (以下 `RM`) §9 の 9)。
- 台帳: `RM` §8 の R-112。依頼者裁定 (逐語)「(i)で。2は後で。」(2026-09-26、`RM` v1.126)。**規模 M** (`docs/work-orders/OPERATING_CONDITIONS.md` (以下 `OC`) §1.13 の 73・74)。**変更クラス: 枠は B** (両 peer の `migrations/0003_provision_application.sql`・`ops.py`・`platform_declarations.py`・`tests/`、r2db の `inmemory_sort.py` の docstring。いずれも `tools/change_class.py` の経路判定では B)。**ただし内容上のクラスは §2.10 の実測を見よ (監督判断待ち)。** `spec/`・`conformance-tests/`・`security/` に触れない。
- 設計文書は持たない (規模 M は作業指示書 1 節。`OC` §1.13 の 74)。枠は本書 §1 (監督確定。出所は監督の scratchpad の `$SP/frame-r112.md`)。PostgreSQL の実測は同じ scratchpad の `$SP/pg-collation-measured.md` (監督 2026-09-26、PostgreSQL 16.14) で、テストに使う値集合と期待順序は本書 付録 A に写す。
- 手本: `docs/work-orders/WORK_ORDER_R38_INMEMORY_JSONB_ORDER_V1.md` の節構成 (§0〜§5 と付録)。写さず節番号で指す。
- 役割: 実装担当 (テンプレ 2) 1 回、コードレビュー (テンプレ 5) 1 回 (`docs/work-orders/ROLE_PROMPT_TEMPLATES.md`)。**監査担当は起動しない** (規模 M。Class B の場合。`OC` §1.13 の 74)。commit・完了ゲート・merge は監督。
- 1 WP (脚 A = r2db-api、脚 B = MitateDB-api)、1 worktree (`.claude/worktrees/r38`、branch `r38`、main `0d7065c` と同一)、1 commit、main へ 1 merge。脚 A と脚 B は同じ実装担当が順に行う (§2.4)。両脚が同じ変更セットで入るのは、`ops.py` の検査表が両 peer で同型に固定されているため (§2.10)。
- 並行チャット (worktree r101) は `tools/perf_baseline.py` と `docs/design/PERF_*` を触る。本件はそれらに触れない。

## 1. 監督確定事項

行番号は起草時 (`0d7065c`) の実測。以下 `RP` = `r2db-api/src/r2db_api/`、`MP` = `MitateDB-api/src/mitatedb_api/`、`R3` = `r2db-api/migrations/0003_provision_application.sql`、`M3` = `MitateDB-api/migrations/0003_provision_application.sql`。

### 1.1 問題設定 (事実)

1. 両 peer の application DB は `CREATE DATABASE :"database_name" TEMPLATE template0 ENCODING 'UTF8'` で作られ (`R3`:102、`M3`:63)、照合はクラスタの initdb 既定を継承する (使い捨てクラスタは `tools/testpg/dsa_testpg.py`:820 の `--locale=en_US.UTF-8`)。
2. PostgreSQL backend の ORDER BY・keyset cursor 述語・lt / lte / gt / gte の文字列比較はどちらも COLLATE 句を持たず DB 既定照合で比べる (r2db `RP` `postgres_sql.py` `_order_by_sql` :117-122 / `_keyset_predicate_sql` :71-114 / `_predicate_sql` :175-243; MitateDB `MP` `backend_postgres.py`:1459-1481、`MP` `postgres_sql.py`:38-93)。in-memory (r2db `RP` `inmemory_sort.py`) は codepoint 順、SQLite (MitateDB) は BINARY = byte 順。UTF-8 の byte 順は codepoint 順と同じ。
3. 実測 (付録 A の出所、PostgreSQL 16.14): en_US.UTF-8 では `_ < 1 < a < A < ä < aa < b < B`、codepoint 順では `1 < A < B < Z < _ < a < aa < b < z < ä`。DB を `LC_COLLATE 'C'` にすると jsonb の中の文字列も text 列も codepoint 順になる。`LC_CTYPE` を `C` にすると `upper('ä')` / `ILIKE` / `~*` / 正規表現の `\w` が ASCII 限定になるが、`LC_COLLATE 'C' LC_CTYPE 'en_US.UTF-8'` の組合せは順序だけを変える。
4. jsonb には式レベルの COLLATE を付けられない (`collations are not supported by type jsonb`、実測)。r2db の untyped / object / array 列は物理 jsonb なので、DB の `LC_COLLATE` を変える以外に手段が無い。MitateDB は TEXT 列だけなので列単位の COLLATE も可能だが、r2db と同じ DB 単位の方法で揃える (D-1)。
5. r2db の `contains` / `matches` は LIKE (大文字小文字を区別、照合非依存)。MitateDB には文字列パターンの演算子が無い (`SQL_OPERATOR_TOKENS = {eq, ne, lt, lte, gt, gte, in}`、`MP` `backend.py`:35-42)。両 peer とも ctype に依存する演算子を公開していない。
6. 既存 DB の `LC_COLLATE` は変更できない (再作成のみ)。両 peer とも `ops upgrade-applications` の per-application script は列の変更しかできない。運用前 (着手条件「印なし」) に実施する理由。
7. 両 peer の `ops verify-declarations` は F-3〜F-18 の検査を持ち、最後はどちらも F-18 (max_connections headroom、終了コード 17)。r2db `RP` `ops.py`:992-1021 (`_VERIFY_DECLARATIONS_EXIT_CODES`)、:1063-1170 (`_verify_declarations_checks`)、:1221 (`cmd_verify_declarations`); MitateDB `MP` `ops.py`:1260-1288、:1330-1437、:1540。検査 helper は各 peer の `platform_declarations.py` (r2db F-17 `check_auditreader_statement_timeout` :1142、F-18 `check_max_connections_headroom` :1343; MitateDB :1116、:1318)。
8. 契約 `paging.ordering` は照合を実装依存とし peer 間の一致を要求しない。本件は契約が許す実装内の選択であり、契約文は変えない。
9. テスト: 両 peer とも、文字列の順序 (大文字小文字・非 ASCII) の backend 間 parity を固定するテストは無い (r2db `r2db-api/tests/test_postgres.py` の parity は integer (:3307) と jsonb 構造 (:4040-4117) のみ; MitateDB `MitateDB-api/tests/test_postgres.py` に照合のテストも SQLite backend と同じ要求を比べるテストも無い)。

### 1.2 守るべき条件

1. 順序の一致: 同じ要求 (order_by asc / desc、keyset cursor、lt / gt の文字列比較) に対し、r2db の PostgreSQL backend と in-memory backend、MitateDB の PostgreSQL backend と SQLite backend が同じ順序 / 同じ集合を返す。基準は実サーバの出力 (代理指標を使わない。`OC` §1.7 の 52)。
2. ctype を壊さない: application DB の `datctype` はクラスタ既定 (UTF-8 locale) のままで、`datcollate` だけが `C`。実測で `upper('ä') = 'Ä'` が保たれること。
3. 検出可能: 照合が `C` でない application DB (本変更より前に provision されたもの) は `ops verify-declarations` の新しい検査で FAIL になる (両 peer)。
4. 契約・conformance・security・spec に触れない。`_ISOMORPHIC_TARGETS` に触れない (ops の検査 helper が登録済み同型 helper に当たるかの実測は §2.10)。
5. src の新しい comment に経緯語 (WP / R-112 / phase / 日付 / 裁定名) を書かない。docstring の主張は実測後 (`OC` §1.5 の 34)。migration の comment は既存の 0003 の書式に倣う。

### 1.3 決定と根拠

- **D-1.** 両 peer の `0003` の `CREATE DATABASE` に `LC_COLLATE 'C'` を足す。`LC_CTYPE` は書かない (template0 = クラスタ既定を引き継ぐ)。`ENCODING 'UTF8'` は残す。根拠: §1.1 の 3・4。列単位の COLLATE は jsonb に付けられず、r2db と MitateDB で方法が割れる。platform DB (`0001`) は変えない (公開の data plane ではない。観察として残す)。
- **D-2.** 両 peer の `ops verify-declarations` に検査を 1 つ足す: 登録済みの全 application の database について `pg_database.datcollate = 'C'` かつ `datctype <> 'C'`。番号は各 peer の既存の最後の F 番号 + 1 (起草時の実測で両 peer とも **F-19**、終了コードは次の未使用値 **18**)。失敗時の message は既存の検査と同じ形。各 peer の `platform_declarations.py` に `check_application_collations(conn, schema=...)` を置き、`ops.py` の呼び出し部は他の検査と同じ形にする。既存 DB の retrofit 経路は作らない (再 provision)。
- **D-3.** 文字列順序の parity テストを両 peer に足す (実 PostgreSQL): 付録 A の値集合を string 型列に入れ、(a) order_by asc / desc の items が両 backend で一致し、かつ PostgreSQL 側が codepoint 順 (`sorted()`) そのもの、(b) keyset cursor (page_size 1〜2) の辿りが一致し全行に届く、(c) `gt` / `lt` の where の集合が一致。r2db は加えて untyped 列 (jsonb の中の文字列) でも (a) を確かめる。加えて provisioning の事実の pin: application DB の `datcollate == 'C'`、`datctype != 'C'`、`select upper('ä') = 'Ä'` (application 接続で実行)。
- **D-4.** verify 検査の単体テスト: 照合が `C` でない DB を 1 つ作った状態 (テスト内で `CREATE DATABASE ... LC_COLLATE` を省いて provision するか、pg_database の読み取りを偽装) で FAIL の message を assert。既存の F 検査のテストの形に倣う。
- **D-5.** r2db `RP` `inmemory_sort.py` の `_sort_key` docstring の照合差の段落 (:87-91) を、実測後に「application DB は `LC_COLLATE 'C'` で provision されるので (0003)、文字列も codepoint 順で一致する」に改める (CH-ID 無し docstring の内容変更 = provenance (2) の正当な赤、R-38 と同じ扱い)。`RP` `postgres.py` の module docstring (許容差 2 件) は変えない。
- **D-6.** 変異 (単一 node、`-n` なし): M1 r2db `0003` から `LC_COLLATE 'C'` を外す → r2db の parity (a) と datcollate pin が赤; M2 MitateDB `0003` で同じ → MitateDB 側が赤; M3 r2db の verify 検査の条件を反転 (`datcollate <> 'C'` を合格に) → D-4 のテストが赤; M4 MitateDB で同じ; M5 r2db `0003` に `LC_CTYPE 'C'` を足す → ctype pin (`upper('ä')`) が赤; M6 MitateDB で同じ。対応表に監査照合の行を含める。
- **D-7.** deploy / runbook: 両 peer の README / deploy 文書で provisioning の `CREATE DATABASE` を写している箇所があれば同じ変更を書く。デプロイ先クラスタの locale は問わない (DB 単位で `C` にするため)。起草時の grep の結果は §2.3。

### 1.4 却下した代替案と理由

- (a) 列単位の `COLLATE "C"` (TEXT 列の定義や ORDER BY 句): r2db の jsonb に付けられない。peer 間で方法が割れる。
- (b) in-memory / SQLite 側を locale 照合に合わせる: Python / SQLite で PostgreSQL の locale 照合を再現できない。
- (c) `LC_CTYPE 'C'` も併せて指定: 非 ASCII の大文字小文字の折り返しと正規表現の文字クラスが壊れる (実測)。
- (d) 既存 DB の retrofit script: `LC_COLLATE` は変更不能。運用前なので再 provision で足りる。

### 1.5 未確定で依頼者判断待ちの選択肢

なし。依頼者裁定の「2」(peer 間の JSON 値の順序差。r2db の jsonb 構造順 vs MitateDB の canonical text 順) は保留のまま、本件で触れない。

### 1.6 記録の置き場

変異を持たない完了条件 (17〜21) の逐語記録は、設計文書が無いので本書 §5 に残す (`OC` §1.5 の 40)。log のパス・log のファイル名は本書に書かない (公開値スキャンの誤検知を避ける)。traceback を貼らない (`OC` §1.9 の 63)。

## 2. WP-1 — application DB の照合 `C`、verify 検査 F-19、文字列順序の parity テスト

### 2.1 目的

両 peer の application DB を `LC_COLLATE 'C'` (ctype はクラスタ既定) で provision し (D-1)、照合が `C` でない application DB を `ops verify-declarations` の F-19 で検出し (D-2)、1 実装の 2 backend が文字列に同じ順序・同じ集合を返すことを実 PostgreSQL との差分テストで固定する (D-3・D-4)。

### 2.2 読むべき正本

- 本書 §1 と 付録 A
- `R3`:90-102、`M3`:55-63 (`CREATE DATABASE` とその直上の comment。header comment の書式)。`r2db-api/migrations/0001_bootstrap_control_plane.sql`:106、`MitateDB-api/migrations/0001_bootstrap_platform.sql`:179 (変えない。参照のみ)
- r2db `RP` `ops.py`:985-1170 (終了コード表、`_VERIFY_DECLARATIONS_READ_ORDER`、`_verify_declarations_checks` の F-16〜F-18 の呼び出しの形); MitateDB `MP` `ops.py`:1260-1437
- r2db `RP` `platform_declarations.py`:1126-1203 (`_f17_message`・`check_auditreader_statement_timeout`)、:1262-1273 (`_count_registered_applications`。`<schema>.applications` の読み方); MitateDB `MP` `platform_declarations.py`:1100-1180、:1237-1250
- 両 peer の `tests/test_ops_verify_declarations.py`: `_bootstrap` (r2db :158、MitateDB :169)、`_run_verify` (r2db :287、MitateDB :298)、`_provision_app_for_verify` (r2db :579、MitateDB :620。`0003` を MIGRATIONS_DIR から読み、prefix を書き換えて実行)、F-17 の pass / fail テスト (r2db :1122-1270、MitateDB :1151-1300)、F-18 の終了コード pin (r2db :1102、MitateDB :1128)
- r2db `r2db-api/tests/test_postgres.py`: `make_cell` :306、`_memory_cell` :3115、`test_parity_order_by_null_placement_and_cross_type` :3307、`_seed_jsonb_column` / `_assert_jsonb_column_order` / `_walk_all_pages` / `test_parity_order_by_jsonb_*` :4020-4117 (parity の雛形)
- MitateDB `MitateDB-api/tests/test_postgres.py`: `make_cell` :375、`sessions_for` :384、`app_a` :358。SQLite backend の cell の作り方は `MitateDB-api/tests/test_row_order_column.py`:93 (`ApplicationCell("app1", backend=SQLiteBackend())`)、`read_page` の cursor の辿り方は同 :144-160
- r2db `RP` `inmemory_sort.py`:45-92 (`_sort_key` の docstring。D-5 の対象は :87-91)
- 両 peer の `tests/test_audit_query.py` の `_ISOMORPHIC_TARGETS` (r2db :2393、MitateDB :2188) と、`test_peer_local_helpers_are_isomorphic_to_the_sibling_peer` (r2db :3528、MitateDB :3310) — §2.10
- `OC` §1.4・§1.5・§1.13、`tools/dev/README.md`

### 2.3 現状と目標 (起草時の実測。着手時に再実測する)

| 箇所 | 現状 | 目標 |
|---|---|---|
| `R3`:102 / `M3`:63 | `TEMPLATE template0 ENCODING 'UTF8'` (照合の指定なし) | `TEMPLATE template0 ENCODING 'UTF8' LC_COLLATE 'C'`。`LC_CTYPE` は書かない (D-1)。直上の comment に理由を足す (既存 comment の書式) |
| `0001` (両 peer) | 照合の指定なし | 変えない (D-1) |
| `ops verify-declarations` (両 peer) | F-3〜F-18、最後は F-18 (終了コード 17) | F-18 の後に F-19 (終了コード 18) を足す (D-2) |
| `platform_declarations.py` (両 peer) | 照合の検査なし | `check_application_collations(conn, schema=...)` と F-19 の message (D-2) |
| r2db `_sort_key` docstring (`RP` `inmemory_sort.py`:87-91) | 「照合差は扱わない」 | 実測後に D-5 の内容へ |
| r2db in-memory・MitateDB SQLite・両 peer の `postgres_sql.py` / `backend_postgres.py` | codepoint 順 / byte 順 / COLLATE 句なし | 変えない |
| 文字列順序の backend 間 parity | テスト無し | 脚 A 6 node、脚 B 5 node (2.4 のタスク 1) |
| verify F-19 のテスト | 無し | 脚 A 2 node、脚 B 2 node (2.4 のタスク 1) |
| D-7 の対象 (README / deploy 文書で application DB の `CREATE DATABASE` を写している箇所) | 起草時の grep (`TEMPLATE template0` / `CREATE DATABASE`、`r2db-api/README.md`・`r2db-api/deploy/`・`MitateDB-api/README.md`・`docs/`。`MitateDB-api/deploy/` は存在しない) で **0 件** | 変更なし。着手時に同じ grep を再実行し、件数を §5 に記録する。1 件以上あれば実装前に監督へ上げる |

### 2.4 タスク

実装担当が順に行う。脚 A (r2db) を 1〜6 まで終えてから脚 B (MitateDB) の 1〜6 を行い、7 以降は両脚まとめて行う。ただし `ops.py` の 2 箇所 (終了コード表と `_verify_declarations_checks`) は両 peer で同型に固定されている (§2.10) ので、脚 A のタスク 3 と脚 B のタスク 3 を終えるまで `test_audit_query.py` の同型性テストは赤のままでよい (途中の赤は報告に書く)。

0. **基点の再実測。** 2.11 の全 `pt.py` コマンドを未変更の worktree で 1 回ずつ回し、集計行を §5 の完了条件 20 の欄に写す (MitateDB の `test_postgres.py -k "collation or parity_order"` は起草時 0 件なので `no tests ran` / 終了コード 5 が期待形)。§2.3 の D-7 の grep を再実行し、件数を §5 の完了条件 19 の欄に写す。
1. **テストを先に書く (D-3・D-4)。** 既存ファイルの末尾に追記する (既存行の行番号をずらさない)。名前は 2.14 の表のとおり。値集合・投入順・期待順序は付録 A だけを使う。
   - **parity (`test_postgres.py`、実 PostgreSQL)。** 脚 A は `make_cell(app_a)` と `_memory_cell()`、脚 B は `make_cell(app_a)` と SQLite backend の `ApplicationCell` (§2.2) を比べる。
     - **T1 string 型列の order_by** (両脚): 付録 A の値を A-2 の投入順で string 型列に入れ、`asc` / `desc` それぞれで (1) 2 backend の items が等しい、(2) PostgreSQL の `asc` の items が A-1 の codepoint 順 (= `sorted(値集合)`) と等しく `desc` はその逆順、(3) 件数が値集合の件数以上、を assert。
     - **T2 untyped 列の order_by** (脚 A のみ): T1 と同じ 3 点を untyped 列 (`create_entity` の `fields` に置く列) で。
     - **T3 keyset cursor** (両脚): T1 と同じ列で `page_size` 1 と 2、`asc` と `desc` の各組について `next_cursor` が無くなるまで辿り (上限回数を置く)、(1) 2 backend の連結列が等しい、(2) 各 backend の連結列がその backend の page 無しの items と等しい、(3) 連結列の件数が値集合の件数と等しい、(4) 辿った page の数が 1 より大きい、を assert。脚 A は `_walk_all_pages` (r2db `test_postgres.py`:4079) の形。
     - **T4 where の `gt` / `lt`** (両脚): T1 と同じ列で `gt "a"` と `lt "a"` をそれぞれ page 無しで問い合わせ、(1) 2 backend の値の集合が等しい、(2) PostgreSQL の集合が付録 A の A-3 (Python の `>` / `<` で求めた集合) と等しい、(3) 各集合が空でない、を assert。
     - **P1 照合の pin** (両脚): `app_a` の application DB について `pg_database.datcollate == 'C'` を assert。
     - **P2 ctype の pin** (両脚): 同じ DB について `datctype != 'C'` と、application 接続 (runtime DSN) での `select upper('ä')` が `'Ä'` であることを assert。
   - **verify (`test_ops_verify_declarations.py`、実 PostgreSQL)。** 既存の F-17 の pass / fail テストの形に倣う。`_run_verify` の接続先は、F-19 に届くまでの検査 (F-13 等) で止まらない role にする (r2db `_declare_control_role_as_the_writer` :603、MitateDB `_declare_provision_role_as_the_writer` :643 の使い方を参照)。
     - **V1 FAIL** (両脚): 照合が `C` でない application DB を 1 つ登録した状態を作る。作り方は D-4 の 2 通りのどちらでもよい (例: `_provision_app_for_verify` と同じく `0003` を読み、`LC_COLLATE 'C'` だけを除いた本文で provision する)。どちらを採ったかを報告に書く。(1) 終了コードが 18、(2) stdout に `FAIL F-19` の行が 1 行あり、その DB 名を含む、(3) `OK   F-18` の行が `FAIL F-19` より前にある (F-19 が F-18 の後に走る)、を assert。
     - **V2 OK** (両脚): 未変更の `0003` で application を 1 つ provision した状態で、(1) 終了コードが 0、(2) `OK   F-19` の行がある、を assert (非空振り: 登録済み application が 1 件以上ある状態で判定していることを assert に含める)。
   - 既存テストが F-19 で赤になったら (例: `0003` を経ずに作った DB を `applications` に登録するテスト)、既存テストを変えずに実装前に監督へ上げる (`OC` §1.5 の 37)。
2. **未変更の実装でテストが赤になることを確かめる。** タスク 1 のテストを、`0003`・`ops.py`・`platform_declarations.py` を変えずに 2.11 の絞り込みで回し、集計行と `FAILED` の要約行を §5 の完了条件 1 の欄に写す (T1〜T4・P1 は赤、P2 は緑、V1・V2 は F-19 が未実装なので赤、が期待。違えば報告に書く)。
3. **D-1・D-2 の実装。** `0003` の 1 行と直上の comment。`platform_declarations.py` に `check_application_collations` と F-19 の message (既存の `_f17_message` 等と同じ形: 対象の DB 名、何が違うか、どう直すか (再 provision)。値そのものや接続情報を出さない)。`ops.py` の終了コード表に `"F-19": 18`、`_verify_declarations_checks` の F-18 の後に F-19 の呼び出し (F-17 の呼び出しと同じ形)。`_VERIFY_DECLARATIONS_READ_ORDER`・`cmd_verify_declarations`・F-3〜F-18 の検査は変えない。
4. **変異 (脚ごと)。** 2.14 の該当脚の entry を `$SP/r112-mutations.json` に書き、2.11 の `mutate.py` で回す。
5. **docstring (D-5、脚 A のみ)。** 変異と suite の実測を得た後に `RP` `inmemory_sort.py`:87-91 を D-5 の内容に改める。一致を主張する範囲に、完了条件 3〜6 の test 名と件数を引く (`OC` §1.5 の 34)。`RP` `postgres.py` の module docstring は変えない。
6. **provenance。** 2.11 の `check_comment_provenance.py` 2 本を回し、出力の分類 ((1)〜(5)) を §5 に写す。`docs/code-history/` の登録済み block に掛かる赤 (例: `ops.py` の `_verify_declarations_checks` 内の comment) が出たら、直さずに監督へ上げる。
7. **suite。** 2.11 の `r2db-api/tests`・`MitateDB-api/tests`・conformance の絞り込み・`tools/tests` を回す。
8. **報告。** `pt.py` / `mutate.py` の出力行 (集計行・変異表) をそのまま貼る (`OC` §1.10 の 65)。§5 の欄を埋める。

### 2.5 触ってよいパス

- `r2db-api/migrations/0003_provision_application.sql`、`MitateDB-api/migrations/0003_provision_application.sql` (`CREATE DATABASE` の 1 行と直上の comment だけ)
- `r2db-api/src/r2db_api/platform_declarations.py`、`MitateDB-api/src/mitatedb_api/platform_declarations.py` (F-19 の helper と message の追加だけ)
- `r2db-api/src/r2db_api/ops.py`、`MitateDB-api/src/mitatedb_api/ops.py` (`_VERIFY_DECLARATIONS_EXIT_CODES` の 1 項目と `_verify_declarations_checks` の F-19 の呼び出しだけ)
- `r2db-api/src/r2db_api/inmemory_sort.py` (`_sort_key` の docstring の :87-91 の段落だけ)
- `r2db-api/tests/test_postgres.py`、`MitateDB-api/tests/test_postgres.py`、`r2db-api/tests/test_ops_verify_declarations.py`、`MitateDB-api/tests/test_ops_verify_declarations.py` (末尾への追記のみ。既存テストの本体は変えない)
- 本書 §5

### 2.6 触らないパス

`spec/`、`security/`、`conformance-tests/`、`tools/`、両 peer の `migrations/0001_*` と `0003` 以外の migration、両 peer の `tests/test_audit_query.py` (`_ISOMORPHIC_TARGETS` を含む)、`RP` の `inmemory_sort.py` の docstring 以外・`inmemory_predicate.py`・`postgres_sql.py`・`postgres.py`、`MP` の `backend_sqlite.py`・`backend_postgres.py`・`postgres_sql.py`、両 peer の `conformance/`・README・`r2db-api/deploy/`・`r2db-api/docs/`・`MitateDB-api/docs/`、`docs/ops/`、`docs/code-history/`、`RM`、`OC`、`CLAUDE.md`、`tools/perf_baseline.py`・`docs/design/PERF_*` (並行チャット)。これらに変更が要ると分かったら、実装前に監督へ上げる (`OC` §1.5 の 37)。

### 2.7 期待結果表 (commit の時点)

| 対象 | 期待 |
|---|---|
| 新規 脚 A (T1〜T4・P1・P2・V1・V2、8 node) | すべて ok |
| 新規 脚 B (T1・T3・T4・P1・P2・V1・V2、7 node) | すべて ok |
| 既存の parity・verify のテスト | ok のまま、本体の差分なし |
| `r2db-api/tests` | 基点 + 8、failed 0 |
| `MitateDB-api/tests` | 基点 + 7、failed 0 |
| `conformance-tests -k "c30 or c28 or c06"` | 基点と同件数、failed 0 |
| `tools/tests` | 基点と同件数、failed 0 |
| 両 peer の `test_peer_local_helpers_are_isomorphic_to_the_sibling_peer` と `test_isomorphic_target_table_is_pinned_to_its_current_159_rows` | ok (`_ISOMORPHIC_TARGETS` は 159 行のまま) |
| `mutate.py` | 2.14 の全 entry が `as expected` |
| `check_comment_provenance.py` | `--register` OK、`--base` の分類を §5 に記録 |

### 2.8 完了条件 (assert 水準)

脚 A (r2db-api):

1. application DB の照合が `C`: P1 で `app_a` の DB の `datcollate == 'C'`。未変更の `R3` で赤になったことを §5 に記録する (タスク 2)。
2. ctype はクラスタ既定のまま: P2 で `datctype != 'C'` かつ application 接続の `upper('ä') == 'Ä'`。
3. string 型列の order_by が 2 backend で一致し、PostgreSQL の出力が codepoint 順: T1 で `asc` / `desc` の items が PostgreSQL と in-memory で等しく、PostgreSQL の `asc` が付録 A の A-1 と等しく (`desc` は逆順)、件数 ≥ 値集合の件数。
4. untyped 列 (jsonb の中の文字列) で同じ: T2 で 3 と同じ 3 点。
5. keyset cursor の辿りが一致し全行に届く: T3 で `page_size` 1・2 × `asc`・`desc` の各組について、2 backend の連結列が等しく、各 backend の連結列がその backend の page 無しの items と等しく、件数が値集合の件数と等しく、page 数 > 1。
6. `gt` / `lt` の集合が一致: T4 で `gt "a"`・`lt "a"` の各集合が 2 backend で等しく、PostgreSQL の集合が付録 A の A-3 と等しく、空でない。
7. 照合が `C` でない application DB を F-19 が検出する: V1 で終了コード 18、`FAIL F-19` の行が DB 名を含み、`OK   F-18` の行がその前にある。
8. `0003` で provision した application DB は F-19 を通る: V2 で終了コード 0、`OK   F-19` の行があり、登録済み application が 1 件以上。

脚 B (MitateDB-api):

9. 1 と同じ (P1、`M3`)。
10. 2 と同じ (P2)。
11. 3 と同じ (T1。比較相手は SQLite backend)。
12. 5 と同じ (T3)。
13. 6 と同じ (T4)。
14. 7 と同じ (V1)。
15. 8 と同じ (V2)。

両脚共通:

16. 終了コード表と検査列が両 peer で同じ: 両 peer の `_VERIFY_DECLARATIONS_EXIT_CODES` に `"F-19": 18` があり、両 peer の `test_peer_local_helpers_are_isomorphic_to_the_sibling_peer` が ok (監査照合: 2 つの終了コード表の file:line と、同型性テストの `pt.py` の集計行を §5 に記録)。
17. docstring の主張は実測の後 (D-5): `RP` `inmemory_sort.py` の照合の段落が、完了条件 3〜6 の test 名と件数を引いて書かれ、経緯語が無い。`check_comment_provenance.py --register` が OK で、`--base 0d7065c` の分類 ((1)〜(5)) を §5 に記録している (監査照合: 2 コマンドの出力行と docstring の file:line)。
18. 範囲外に触れていない: `git diff 0d7065c --name-only` が 2.5 のパスの部分集合で、両 peer の `0001` に差分が無く、両 peer の `0003` に `LC_CTYPE` の文字列が 0 件 (監査照合: 3 コマンドの出力を §5 に記録)。
19. D-7: §2.3 の grep の再実行結果が 0 件 (監査照合: コマンドと件数を §5 に記録)。
20. suite: `r2db-api/tests` が基点 + 8、`MitateDB-api/tests` が基点 + 7 で failed 0、conformance の絞り込みと `tools/tests` が基点と同件数で failed 0 (監査照合: タスク 0 とタスク 7 の集計行を §5 に記録)。
21. 2.14 の表に、変異も監査照合も持たない行が無い (監査照合: 本表)。

### 2.9 非空振り要件

- T1・T2・T3 の投入順は付録 A の A-2 (codepoint 順とも en_US 順とも違う固定の置換) とする (入力が既に期待順だと、並べ替えが効いていなくても緑になる)。
- PostgreSQL 側の出力を付録 A の期待値と比べる assert を省かない (2 backend が同じように誤っても緑になる形にしない)。
- T4 は各集合が空でないことを assert する。
- V2 は登録済み application が 1 件以上ある状態で判定していることを assert する (0 件なら F-19 は何も読まずに OK を出せる)。
- P2 は `datctype` の文字列比較だけで済ませず、`upper('ä')` を実サーバで評価する (`OC` §1.7 の 52)。

### 2.10 同型性テストの対象

起草時の実測 (`0d7065c`):

- 両 peer の `tests/test_audit_query.py` の `_ISOMORPHIC_TARGETS` (159 行、r2db :2945 / MitateDB :2728 の件数 pin) に、本件が本体を変える次の 2 つが**登録済み**: `ops.py` の `_VERIFY_DECLARATIONS_EXIT_CODES` (r2db `r2db-api/tests/test_audit_query.py`:2615) と `_verify_declarations_checks` (同 :2666)。MitateDB 側も同じ 2 行 (`MitateDB-api/tests/test_audit_query.py`:2398、:2449)。
- 同じ表に、既存の F 検査の helper も登録されている: `_f17_message`・`check_auditreader_statement_timeout` (r2db :2914-2915)、`check_max_connections_headroom` (:2934)。`check_role_connection_limits` は peer 固有の本体を持つので登録されていない (:2854)。
- `RM` §9 の 8 は「`_ISOMORPHIC_TARGETS` に登録された helper の本体」を **Class C**、「`_ISOMORPHIC_TARGETS` 集合の増減」を **Class D** とする (`tools/change_class.py`:51-54 も、経路判定では見えない内容上の C / D として同じことを書く)。したがって D-2 の「`ops.py` の呼び出し部は他の検査と同じ形」は登録済み helper 2 つの本体の変更であり、内容上 **Class C** に当たる。新しい `check_application_collations` と F-19 の message を F-17 の前例どおり登録するなら集合の増加 = **Class D**、登録しないなら §1.2 の 4 のとおり集合は変わらない。
- **監督へ上げる (本書では決めない)。** 実装担当は `_ISOMORPHIC_TARGETS` に行を足さず、両 peer の `ops.py` の 2 つの登録済み helper を正規化後に一致させる (両 peer の `test_peer_local_helpers_are_isomorphic_to_the_sibling_peer` が ok)。新しい helper を両 peer で同名・同本体にするかどうかは実装担当の実測で報告し、登録は監督の裁定を待つ。

### 2.11 道具の引数と集計行の期待形

リポジトリ root から root の `.venv` で起動する。`SP` は監督が発注時に渡す scratchpad。

```
./.venv/bin/python tools/dev/pt.py -C .claude/worktrees/r38 --wait 300 -- r2db-api/tests/test_postgres.py -q -k "collation or parity_order"
./.venv/bin/python tools/dev/pt.py -C .claude/worktrees/r38 --wait 300 -- r2db-api/tests/test_ops_verify_declarations.py -q
./.venv/bin/python tools/dev/pt.py -C .claude/worktrees/r38 --wait 300 -- MitateDB-api/tests/test_postgres.py -q -k "collation or parity_order"
./.venv/bin/python tools/dev/pt.py -C .claude/worktrees/r38 --wait 300 -- MitateDB-api/tests/test_ops_verify_declarations.py -q
./.venv/bin/python tools/dev/pt.py -C .claude/worktrees/r38 --wait 300 -- r2db-api/tests -q
./.venv/bin/python tools/dev/pt.py -C .claude/worktrees/r38 --wait 300 -- MitateDB-api/tests -q
./.venv/bin/python tools/dev/pt.py -C .claude/worktrees/r38 --wait 300 -- conformance-tests -q -n 5 --dist loadgroup -k "c30 or c28 or c06"
./.venv/bin/python tools/dev/pt.py -C .claude/worktrees/r38 --wait 300 -- tools/tests -q
./.venv/bin/python tools/dev/mutate.py "$SP/r112-mutations.json" -C .claude/worktrees/r38
./.venv/bin/python .claude/worktrees/r38/tools/check_comment_provenance.py --register
./.venv/bin/python .claude/worktrees/r38/tools/check_comment_provenance.py --base 0d7065c <触った src>
```

- `<触った src>` は 2.5 の `.py` のうち実際に触ったもの (最大 5 本)。
- すべて前景で `timeout` 600000 を明示する (`OC` §1.5 の 39)。`tools/tests` は完了ゲートに含まれないので、ここで必ず回す。
- 集計行の期待形 (`<...>` は着手時に基点で実測して埋める):

| コマンド | 期待形 |
|---|---|
| r2db `test_postgres.py -k "collation or parity_order"` | `pt: <基点 + 6> passed` (起草時の grep で該当 def は 5 件) |
| r2db `test_ops_verify_declarations.py` | `pt: <基点 + 2> passed` |
| MitateDB `test_postgres.py -k "collation or parity_order"` | `pt: 5 passed` (起草時の grep で該当 def は 0 件。基点は `no tests ran`) |
| MitateDB `test_ops_verify_declarations.py` | `pt: <基点 + 2> passed` |
| `r2db-api/tests` | `pt: <基点 + 8> passed` (基点の参考値: `1478 passed`) |
| `MitateDB-api/tests` | `pt: <基点 + 7> passed` (基点の参考値: `1480 passed`) |
| conformance `-k "c30 or c28 or c06"` | `pt: <基点と同じ> passed` |
| `tools/tests` | `pt: <基点と同じ> passed` (基点の参考値: `591 passed`) |

- 変異ファイルの entry は **単一の node id、`-n` なし**とする (`mutate.py` は最初の赤で止まる)。1 つの変異を複数の node で赤にしたいときは、同じ `old` / `new` の entry を node ごとに分ける (2.14 の M1a〜M1f 等)。migration の変異の `old` は `TEMPLATE template0 ENCODING 'UTF8'` を含む行の文字列にして、comment に同じ語句があっても一意にする。conformance 全体・`tools/dev/gate.py`・`tools/dev/finalize.py` は監督だけが回す。

### 2.12 使用テンプレート

実装 = テンプレ 2、コードレビュー = テンプレ 5 (クラスは §2.10 の監督裁定に従う)。受け入れ監査は、Class B のままなら起動しない (§0)。監査照合の行 (完了条件 16〜21) は、監督が §5 の逐語記録を道具の出力 (`pt.py`・`mutate.py`・`check_comment_provenance.py`・`git diff`・grep) と突合する (`OC` §1.13 の 74)。

### 2.13 禁止事項

- suite 全体 (`conformance-tests` 全体、root suite) を回さない (`OC` §1.6 の 42)。`tools/dev/gate.py` と `tools/dev/finalize.py` を実行しない (`OC` §1.11 の 70)。
- commit・push・merge をしない。下請けの Agent を使わない (`OC` §1.7 の 47)。
- `spec/`・`conformance-tests/`・`security/`・`tools/` に触れない。`_ISOMORPHIC_TARGETS` に行を足さない・消さない (§2.10)。
- platform DB (`0001`) を変えない。`0003` に `LC_CTYPE` を書かない。in-memory / SQLite 側 (r2db `inmemory_sort.py` のコード・`inmemory_predicate.py`、MitateDB `backend_sqlite.py`) を変えない。PostgreSQL 側の SQL (`postgres_sql.py`・`backend_postgres.py`) に COLLATE 句を足さない。
- 既存 DB の retrofit (`ops upgrade-applications` の per-application script、`ALTER DATABASE`、DB の再作成手順) を作らない。
- 本書 §1 に無い機構を足さない。必要と判断したら実装前に上げる (`OC` §1.5 の 37)。
- src の comment・docstring・migration の comment に経緯語 (WP / R-112 / phase / 日付 / 裁定名) を書かない。
- テストの文字列値に付録 A 以外の値を使わない。
- 変異による一時変更を残さない (復元は `mutate.py` に任せ、`git checkout --` を使わない)。
- log のパス・log 名・traceback・作業機の絶対パス・実 DSN を本書に書かない (§1.6、`OC` §1.9)。

### 2.14 完了条件番号 → 変異

`old` / `new` の文字列は実装後のコードから実装担当が書く (`old` は元ファイルで一意)。node の置き場は 2.4 のタスク 1 のとおり (脚 A は r2db の、脚 B は MitateDB の `tests/test_postgres.py` / `tests/test_ops_verify_declarations.py`)。

| 完了条件 | 変異 (ファイル:操作) | 赤になる test (期待) |
|---|---|---|
| 1 | M1a: `R3` の `CREATE DATABASE` から `LC_COLLATE 'C'` を外す | P1 `test_application_database_collation_is_c` (red) |
| 3 | M1b: M1a と同じ変異 | T1 `test_parity_string_collation_order_by_string_column` (red) |
| 4 | M1c: M1a と同じ変異 | T2 `test_parity_string_collation_order_by_untyped_column` (red) |
| 5 | M1d: M1a と同じ変異 | T3 `test_parity_string_collation_keyset_cursor_walk` (red) |
| 6 | M1e: M1a と同じ変異 | T4 `test_parity_string_collation_where_gt_lt` (red) |
| 8 | M1f: M1a と同じ変異 | V2 `test_verify_declarations_f19_passes_after_provisioning_with_0003` (red) |
| 2 | M5a: `R3` の `CREATE DATABASE` に `LC_CTYPE 'C'` を足す | P2 `test_application_database_collation_keeps_the_cluster_ctype` (red) |
| 8 | M5b: M5a と同じ変異 | V2 (red。F-19 の `datctype <> 'C'` の側を守っていることの確認) |
| 2 | M5c: M5a と同じ変異 | P1 (green。M5 が照合を壊していないことの対照) |
| 7 | M3: r2db の `check_application_collations` の条件を反転する (`datcollate <> 'C'` を合格に) | V1 `test_verify_declarations_f19_fails_when_an_application_database_collation_is_not_c` (red) |
| 9 | M2a: `M3` の `CREATE DATABASE` から `LC_COLLATE 'C'` を外す | P1 (脚 B) (red) |
| 11 | M2b: M2a と同じ変異 | T1 (脚 B) (red) |
| 12 | M2c: M2a と同じ変異 | T3 (脚 B) (red) |
| 13 | M2d: M2a と同じ変異 | T4 (脚 B) (red) |
| 15 | M2e: M2a と同じ変異 | V2 (脚 B) (red) |
| 10 | M6a: `M3` の `CREATE DATABASE` に `LC_CTYPE 'C'` を足す | P2 (脚 B) (red) |
| 15 | M6b: M6a と同じ変異 | V2 (脚 B) (red) |
| 10 | M6c: M6a と同じ変異 | P1 (脚 B) (green。対照) |
| 14 | M4: MitateDB の `check_application_collations` の条件を反転する | V1 (脚 B) (red) |
| 16 | 監査照合: 両 peer の終了コード表の file:line と同型性テストの集計行 (§5) | — |
| 17 | 監査照合: `check_comment_provenance.py` 2 本の出力行と docstring の file:line (§5) | — |
| 18 | 監査照合: `git diff 0d7065c --name-only`、`0001` の diff、`0003` の `LC_CTYPE` の grep (§5) | — |
| 19 | 監査照合: D-7 の grep のコマンドと件数 (§5) | — |
| 20 | 監査照合: タスク 0 とタスク 7 の集計行 (§5) | — |
| 21 | 監査照合: 本表 | — |

## 3. merge (監督)

1. 実装担当の報告 → コードレビュー (テンプレ 5。クラスは §2.10 の裁定による) → 差し戻しはファイルで (`OC` §1.7 の 49)。
2. 完了ゲート `./.venv/bin/python tools/dev/gate.py -C .claude/worktrees/r38 --label r112` を 1 回。集計行を本書 §5 に足す。`tools/tests` は完了ゲートに含まれないので `finalize.py` に `--tools-tests` を付ける。
3. `RM` v1.127 (見込み。他チャットと衝突したら merge 時に renumber): §8 の R-112 行に【追記】(閉止。完了条件・変異の結果・`pt.py` の集計行・完了ゲートの集計行) する。版数ログを 5 行に保ち、6 版目の行を `docs/archive/docs/design/ROADMAP_POST_PHASE7_V1__VERSION_LOG.md` へ移す (`OC` §1.16 の 78)。`security/CONTROL_MAPPING.md` は触らない (制御は変わらない)。
4. 引き継ぎ書 `docs/work-orders/HANDOVER_20260926_FABLE3.md` に本件の節を足す (新規の引き継ぎ書は作らない。チャットごと 1 通、`OC` §1.13 の 75)。
5. `./.venv/bin/python tools/dev/finalize.py -C .claude/worktrees/r38 --branch r38 --tools-tests -m <message file> --allow <触ったパス>` で commit と merge (1 commit)。`--allow` は 2.5 のうち実際に触ったパスと、`RM`・版数ログの記録ファイル・引き継ぎ書・本書。

## 4. 訂正註

(実施中に本書の誤り・発注後の監督裁定が生じたらここへ追記する。本文は書き換えない。`OC` §1.8 の 57。)

**訂正註 1 (2026-09-26、監督裁定、§2.10 の上申への回答)**: 変更クラスは **D** とする。理由: `ops.py` の登録済み同型 helper 2 つ (`_VERIFY_DECLARATIONS_EXIT_CODES`、`_verify_declarations_checks`) の本体を変える (内容上 Class C) に加え、新しい helper `check_application_collations` と F-19 の message helper を F-17 の前例 (R-56: `_f17_message` / `check_auditreader_statement_timeout`) どおり両 peer で同名・同本体にし、両 peer の `tests/test_audit_query.py` の `_ISOMORPHIC_TARGETS` に**登録する** (集合の増加 = Class D、`RM` §9 の 8)。したがって §2.5 に `r2db-api/tests/test_audit_query.py` と `MitateDB-api/tests/test_audit_query.py` (`_ISOMORPHIC_TARGETS` の行の追加と件数 pin の実測更新だけ。`OC` §1.5 の 40b) を加え、§2.6 から同ファイルを外す。規模 M のまま (作業指示書 1 節、実装担当、変異、レビュー担当、完了ゲート) だが Class D なので受け入れ監査 (`evidence-auditor`) を 1 回入れる (`OC` §1.13 の 74)。完了条件 16 は「両 peer の `_ISOMORPHIC_TARGETS` に新しい helper 2 つが登録され、件数 pin が実測値に更新され、両 peer の `test_peer_local_helpers_are_isomorphic_to_the_sibling_peer` が ok」と読み替える。変異 M7 を足す: 片方の peer の `check_application_collations` の本体だけを変える (例: 条件を反転) → その peer の同型性テストが赤 (登録が効いていることの確認。M3 / M4 とは別の node)。

**訂正註 2 (2026-09-26、監督裁定、起草者の疑義への回答)**: (a) `docs/ops/BACKUP_RESTORE_R2DB.md` の復元先の `CREATE DATABASE … OWNER` は本変更セットで `TEMPLATE template0 ENCODING 'UTF8' LC_COLLATE 'C' OWNER …` に直す (復元した DB が F-19 で FAIL しないため。§2.5 に加える)。両 peer の runbook (`r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` の F-18 の段落の後、`MitateDB-api/docs/cloud-run-cloud-sql.md` の同じ箇所) に F-19 の段落を 1 つ足す (何を検査するか、FAIL したら再 provision、クラスタは UTF-8 locale で initdb されていること。§2.5 に加える)。(b) locale: クラスタが C / POSIX で initdb されていると `datctype = 'C'` で F-19 が FAIL するのは意図どおり (非 ASCII の折り返しが壊れた配備を検出する。runbook にその旨を書く)。ICU provider: F-19 は `pg_database.datlocprovider` が読める server (PostgreSQL 15 以上) では `datlocprovider = 'c'` (libc) も要求する (ICU の DB では `LC_COLLATE` が順序を決めないため)。15 未満では provider の検査を省く (`server_version_num` で分岐)。`0003` に `LOCALE_PROVIDER` は書かない (PostgreSQL の下限を上げないため。観察として残す)。(c) 登録済み application の `database_name` が `pg_database` に無い場合、F-19 は FAIL とし message に「見つからない」旨を出す (値や接続情報は出さない)。V1 の追加の脚にはしない (監査照合の対象外。単体で assert を 1 つ足してよい)。(d) 台帳 R-112 行の「`migrations/0001` の `TEMPLATE template0 ENCODING 'UTF8'`」は 0003 の誤り。閉止の【追記】で訂正する (監督)。

**訂正註 3 (2026-09-26、監督裁定、実装担当の報告への回答)**: (1) タスク順の逸脱 (テストより先に実装し、未変更の実装での赤を確認していない) は**採用しない**が差し戻さない: 完了条件 1 の「未変更の `R3` で赤」は、M1a〜M1f / M2a〜M2e (`LC_COLLATE 'C'` を外す変異) が同じ node をすべて赤にした実測で代替する (同じ編集で同じ node が赤になる)。§5 の完了条件 1 の欄にはこの読み替えを書く。次のチャットのコードレビューは、この代替が完了条件 1 の意図 (テストが照合の性質を検出する) を満たすかを独立に確かめる。(2) D-7 の grep の対象を README・deploy に限る読み方は採用 (`docs/` の既存文書の `CREATE DATABASE` への言及は provisioning 文の写しではない)。`docs/ops/BACKUP_RESTORE_R2DB.md` は訂正註 2 (a) で個別に直した。(3) `inmemory_sort.py` の docstring が引く「11 passed」は既存 jsonb 4 node + 新規の合算である旨を、docstring の文言が誤解を生まないかレビューで確かめる。(4) 本 WP の実装は 2026-09-26 のチャット終了時点で worktree r38 の branch r38 に **WIP commit (main 未 merge)** として置く。次のチャットはコードレビュー (テンプレ 5、Class D) から再開する (§3)。 (5) 実装担当の判断: `applications` の列名が peer で違う (r2db `application_slug` / MitateDB `application_id`) ため、`check_application_collations` は `database_name` だけで問い合わせて両 peer byte-identical にした -- 採用。レビューで、登録済み application の列挙が `database_name` だけで全件を覆うこと (欠落・重複が無いこと) を確かめる。(6) 0003 の comment に一時的に書いた `LC_CTYPE` の語は訂正済み (両 peer 0 件) -- 採用。

**訂正註 4 (2026-09-26、監督、チャット終了時)**: (1) 実装担当は §5 を埋めていない (実施記録の材料は引き継ぎ書 `docs/work-orders/HANDOVER_20260926_FABLE3.md` の「追記 — R-112 (i) の着手」節に逐語で写してある: 集計行 10 本、変異表 20/20、provenance の分類、`_ISOMORPHIC_TARGETS` 159 → 161、V1 の作り方)。次のチャットは、コードレビューの前に §5 を引き継ぎ書から転記し、完了条件 1 の読み替え (訂正註 3 (1)) と、完了条件 16 (終了コード表の file:line)・18 (`git diff 0d7065c --name-only`、両 peer の 0001 の diff が空、両 peer の 0003 に `LC_CTYPE` 0 件)・19 (D-7 の grep) の監査照合を実測して記す。(2) §0 と §3 の「1 commit」は、WIP commit `738ca3a` (branch r38、main 未 merge) と修正 commit の 2 commit を 1 回の `--no-ff` merge で main に入れる形に読み替える。

**訂正註 5 (2026-09-26、監督裁定、コードレビュー (opus、Class D、指摘 10 件) への回答)**: (1) 指摘 1 (`security/CONTROL_MAPPING.md` の `file:line` 参照 102 件が本変更セットの行挿入でずれる。監督実測: 基点 `0d7065c` の `r2db-api/src/r2db_api/ops.py:1221` = `cmd_verify_declarations` が現在は :1230) は**直す**: レビュー担当の対応表 (旧行 → 新行、102 件すべて一意) を機械的に当て、当てた後に基点の行の内容と新しい行の内容が一致することを再照合し、`conformance-tests/test_control_mapping_register.py` を `pt.py` で回す。§2.5 に `security/CONTROL_MAPPING.md` (行参照の追従だけ。文言・claim・版は変えない) を加え、§2.6・§3 の 3 の「触らない」を「制御は変えない」と読み替える。版は **3.4 のまま** (`OC` §1.13 の 74: 版上げは制御が変わるときだけ)。`tools/dev/README.md`:78 の同種のずれ (`ops.py:1728` → :1737) は監督が直す (`tools/` は実装担当の禁止パス)。(2) 指摘 2 (両 peer の `check_application_collations` docstring の経緯語 `F-19 (R-112 D-2)`・`(§1.2 condition 2 of the governing work order)`) は直す (§1.2 の 5、§2.13)。同型性テストと provenance を再実行する。(3) 指摘 3 (F-19 の provider 枝 (PostgreSQL 15 以上で `datlocprovider = 'c'`) と DB 不在枝を固定するテストが無い。レビュー担当の変異 RV1・RV2 が緑のまま) は直す: 両 peer の `test_ops_verify_declarations.py` 末尾に、偽の conn / cursor で pg_database の読み取りを偽装する単体テスト (D-4 の 2 通り目) を足す — (a) `datlocprovider = 'i'` かつ `server_version_num >= 150000` で FAIL、(b) `pg_database` に行が無いとき FAIL (訂正註 2 (c) の「単体で assert を 1 つ足してよい」をここで使う)、(c) `server_version_num < 150000` では provider の列を読まない。両 peer 同名・同本体を要求しない (テストは同型 target ではない)。RV1・RV2 と同じ編集を変異 M8 (provider 条件の除去 → (a) が赤)・M9 (不在枝の除去 → (b) が赤) として両 peer で赤にする。§2.14 の表に M8・M9 の行を足す (完了条件 7・14 の追加の脚)。(4) 指摘 4 (`inmemory_sort.py`:87-98 の「11 passed together with this module's own pre-existing jsonb-order tests」は誤読を招く。実際の 11 = 既存 5 (jsonb 4 + `test_parity_order_by_null_placement_and_cross_type`) + 新規 6 (T1〜T4 + P1・P2)。訂正註 3 (3) の「既存 jsonb 4 node」は監督の誤り) は直す: 括弧書きを実測の内訳に改め、`gt` / `lt` は `inmemory_predicate.py` のネイティブ比較 (同じ codepoint 順) と別に書き、一致を主張する範囲を最上位の文字列に限る。r2db runbook の同じ括弧書きも合わせる。provenance を再実行する。(5) 指摘 5 (docstring の「`_count_registered_applications` と同じ対象集合」は偽: 向こうは `count(*)`、こちらは `database_name IS NOT NULL`) は直す。(6) 指摘 6 (`docs/ops/BACKUP_RESTORE_R2DB.md`:28 の復元コマンド 1 本が platform DB にも適用され、復元した platform DB が `LC_COLLATE 'C'` になり D-1 と食い違う) は直す: application DB 用 (`LC_COLLATE 'C'` あり) と platform DB 用 (なし) の 2 行に分ける。訂正註 2 (a) の文言を本註が上書きする。(7) 指摘 7 (FAIL message の対処の文言: ICU で initdb されたクラスタでは PostgreSQL 15 以上の `CREATE DATABASE` が template の provider を継ぐので「現行の 0003 で再 provision」では解けない; deprovision が途中で止まった行 (DROP 済みで行が残る) の正しい対処は 0004 の再実行) は直す: provider の message に libc locale のクラスタで再 provision する旨、missing の message に deprovision (0004) を完了させる旨を足す (値・接続情報は出さない)。両 runbook の F-19 段落にも ICU の場合を 1 文足す。(8) 指摘 8 (r2db runbook の意味の通らない文、両 runbook の F-19 段落に終了コード 18 が無い) は直す。(9) 指摘 9 (MitateDB の新規テスト 3 本が `close_cell(pg_cell)` を呼ばない) は直す: `try/finally`。(10) 指摘 10 (§5 の変異表は「逐語」ではなく実装担当の報告で圧縮された形) は監督が §5 の文言を直す。レビュー担当の問い (1) (完了条件 1 の代替は意図を満たす: M1/M2 は実行される `CREATE DATABASE` 文を基点と同じ文に戻し、T1・T2・T4 は A-1 / A-3 との直接比較を持つ) と (5) (`database_name` は両 peer で UNIQUE・NULL 可、NULL は provision 前の行で DB が無いので除外して正しい) は指摘なしで採用。完了条件 20 の期待形は、指摘 3 の新規 node の分だけ `r2db-api/tests`・`MitateDB-api/tests`・両 peer の `test_ops_verify_declarations.py` の件数が増える (実装担当が実測して報告する)。

## 5. 実施記録

(監査照合の逐語記録 — 実行したコマンドと集計行、または file:line — を完了条件番号ごとに記す。log のパス・log 名・traceback は書かない (§1.6)。完了ゲートの集計行は監督が記す。実装担当の集計行・変異表・provenance の分類は `docs/work-orders/HANDOVER_20260926_FABLE3.md` の「追記 — R-112 (i) の着手」節から監督が転記した (訂正註 4 (1))。完了条件 16・18・19 の監査照合は監督が 2026-09-26 に worktree r38 (HEAD `8268dd7`) で実測した。)

**完了条件 1** (未変更の実装での赤、タスク 2):

読み替え (訂正註 3 (1)): 実装担当はテストより先に実装し、未変更の `R3` / `M3` での赤を実測していない (逸脱 (a)、採用しないが差し戻さない)。代替の実測は下の変異表の M1a〜M1f (脚 A) と M2a〜M2e (脚 B): `0003` の `CREATE DATABASE` から `LC_COLLATE 'C'` を外す同じ編集で P1・T1〜T4・V2 (脚 A 6 node)、P1・T1・T3・T4・V2 (脚 B 5 node) がすべて赤 (`expect=red got=red`)。この代替が完了条件 1 の意図 (テストが照合の性質を検出する) を満たすかは、コードレビュー (Class D) が独立に確かめる。

**完了条件 1〜15** (変異表。実装担当の報告に載った形 (`mutate.py` の per-line 出力のうち件数と `restore=ok` を実装担当が省いた要約。コードレビュー指摘 10、訂正註 5 (10))。3 回に分けて実行、計 20/20 as expected。末尾の `mutate:` 集計行は逐語):

```
M1a expect=red got=red OK | M1b red/red OK | M1c red/red OK | M1d red/red OK
M1e red/red OK | M1f red/red OK | M5a red/red OK | M5b red/red OK
M5c expect=green got=green OK | M3 red/red OK
mutate: 10 mutations, 10 as expected, restores verified 2/2 files (sha256 x2), grep counts unchanged
---
M2a red/red OK | M2b red/red OK | M2c red/red OK | M2d red/red OK | M2e red/red OK
M6a red/red OK | M6b red/red OK | M6c expect=green got=green OK | M4 red/red OK
mutate: 9 mutations, 9 as expected, restores verified 2/2 files (sha256 x2), grep counts unchanged
---
M7 expect=red got=red OK | mutate: 1 mutations, 1 as expected, restores verified 1/1 files (sha256 x2), grep counts unchanged
```

完了条件との対応: 1→M1a、3→M1b、4→M1c、5→M1d、6→M1e、8→M1f / M5b、2→M5a / M5c (緑の対照)、7→M3、9→M2a、11→M2b、12→M2c、13→M2d、15→M2e / M6b、10→M6a / M6c (緑の対照)、14→M4、16→M7 (+監査照合)、17〜21→監査照合のみ。V1 は D-4 の 2 通りのうち「`0003` を読み `LC_COLLATE 'C'` だけを除いた本文で provision する」方 (`_provision_app_for_verify_without_collation_c`)。

差し戻し後の再実行 (訂正註 5。実装担当、逐語。`check_application_collations` の本体と message を触ったので M3・M4・M7 を作り直して再実行、新規 M8 / M9 (両 peer) を追加。0003 は触っていないので M1 / M2 / M5 / M6 は再実行していない):

```
M3       expect=red   got=red       OK  | 1 failed in 0.37s | restore=ok
M4       expect=red   got=red       OK  | 1 failed in 0.35s | restore=ok
M7       expect=red   got=red       OK  | 1 failed in 1.74s | restore=ok
M8       expect=red   got=red       OK  | 1 failed in 0.07s | restore=ok
M8b      expect=red   got=red       OK  | 1 failed in 0.07s | restore=ok
M9       expect=red   got=red       OK  | 1 failed in 0.08s | restore=ok
M9b      expect=red   got=red       OK  | 1 failed in 0.09s | restore=ok
mutate: 7 mutations, 7 as expected, restores verified 2/2 files (sha256 x2), grep counts unchanged
```

対応: M8 / M8b = `check_application_collations` の provider 条件の除去 → `test_check_application_collations_fails_on_icu_provider_on_pg15` (r2db / MitateDB) が赤 (完了条件 7 / 14 の追加の脚)、M9 / M9b = DB 不在枝の除去 → `test_check_application_collations_fails_when_the_database_is_missing` (r2db / MitateDB) が赤 (同)。`test_check_application_collations_skips_the_provider_column_before_pg15` は偽 cursor が受けた SQL に `datlocprovider` が無いことを assert する (変異なし。監査照合: 上の M8 と対で読む)。コードレビュー担当の対照変異 (RV0 `check_application_collations` の datcollate 条件の除去 → r2db V1 赤、RV1 / RV2 = 修正前の provider / 不在枝の除去が緑のまま = 指摘 3 の根拠) はレビュー報告に逐語で残る。

**完了条件 16** (終了コード表と同型性テスト。訂正註 1 の読み替え):

- 終了コード表: `r2db-api/src/r2db_api/ops.py`:1021 `"F-19": 18,` (直前 :1020 `"F-18": 17,`)、`MitateDB-api/src/mitatedb_api/ops.py`:1289 `"F-19": 18,` (直前 :1288 `"F-18": 17,`)。
- `_ISOMORPHIC_TARGETS` の登録: `r2db-api/tests/test_audit_query.py`:2947 (`_f19_message`)・:2948 (`check_application_collations`)、`MitateDB-api/tests/test_audit_query.py`:2730・:2731。件数 pin 159 → 161: r2db :2952 (test 名) / :3310 (`assert len(_ISOMORPHIC_TARGETS) == 161`)、MitateDB :2735 / :3092。
- 同型性テストの集計行 (実装担当): `r2db test_audit_query.py -k isomorphic: pt: 4 passed, 72 deselected in 1.71s`、`MitateDB test_audit_query.py -k isomorphic: pt: 4 passed, 59 deselected in 1.71s`。監督の再実測 (2026-09-26、`8268dd7`): r2db `pt: 4 passed, 72 deselected in 1.77s`、MitateDB `pt: 4 passed, 59 deselected in 1.68s`。
- 登録が効いていることの変異: M7 (上の変異表、red。差し戻し後に作り直して再実行、red)。差し戻し後の同型性テスト (実装担当): r2db `pt: 4 passed, 72 deselected in 1.69s`、MitateDB `pt: 4 passed, 59 deselected in 1.65s`。

**完了条件 17** (provenance 2 本の出力と docstring の file:line):

- `check_comment_provenance.py --register`: `comment provenance register OK: 92 files scanned, 433 CH-IDs` (実装担当。監督の再実測 2026-09-26 も同一行)。
- `check_comment_provenance.py --base 0d7065c` (触った src 5 本。監督の再実測 2026-09-26、実装担当の報告と同じ 5 本): 赤 5 本、すべて `docs/design/CODE_COMMENT_PROVENANCE_V1.md` §4.1 の分類で想定内、登録済み block への赤は無し。
  - (1) 新規関数 / 新規呼び出し: `r2db-api/src/r2db_api/platform_declarations.py`:1398、`r2db-api/src/r2db_api/ops.py`:1021、`MitateDB-api/src/mitatedb_api/platform_declarations.py`:1373、`MitateDB-api/src/mitatedb_api/ops.py`:1289 (`FAIL (§4.1 (1)) … code changed (AST differs, docstrings excluded)`)。
  - (2) CH-ID 無し docstring 段落の内容変更 (D-5、R-38 と同じ扱い): `r2db-api/src/r2db_api/inmemory_sort.py`:46 (`FAIL (§4.1 (2)) … scope/anchor ('_sort_key', 'stmt#1'): the sequence of CH-ID-less blocks changed (old 1, new 1)`)。
- docstring の位置 (差し戻し後): `r2db-api/src/r2db_api/inmemory_sort.py`:87-110 (`_sort_key` の照合の段落。完了条件 3〜5 の test 名 3 つを `_sort_key` の一致の証拠に、完了条件 6 の `test_parity_string_collation_where_gt_lt` を `inmemory_predicate.py` のネイティブ比較の証拠に分けて引き、`-k "collation or parity_order"` の 11 の内訳 (新規 4 + provisioning pin 2 + 既存 parity 5) を書く。一致の主張は最上位の文字列に限る。コードレビュー指摘 4、訂正註 5 (4))。差し戻し後の provenance (実装担当): `--register` 同一行、`--base 0d7065c` は同じ 5 本・同じ分類・同じ行番号 (message の追記は各 def 行より後ろ)。

**完了条件 18** (範囲外。監督実測 2026-09-26):

- `git diff 0d7065c --name-only` = 18 件: `MitateDB-api/docs/cloud-run-cloud-sql.md`、`MitateDB-api/migrations/0003_provision_application.sql`、`MitateDB-api/src/mitatedb_api/ops.py`、`MitateDB-api/src/mitatedb_api/platform_declarations.py`、`MitateDB-api/tests/test_audit_query.py`、`MitateDB-api/tests/test_ops_verify_declarations.py`、`MitateDB-api/tests/test_postgres.py`、`docs/ops/BACKUP_RESTORE_R2DB.md`、`docs/work-orders/HANDOVER_20260926_FABLE3.md`、`docs/work-orders/WORK_ORDER_R112_STRING_COLLATION_V1.md`、`r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md`、`r2db-api/migrations/0003_provision_application.sql`、`r2db-api/src/r2db_api/inmemory_sort.py`、`r2db-api/src/r2db_api/ops.py`、`r2db-api/src/r2db_api/platform_declarations.py`、`r2db-api/tests/test_audit_query.py`、`r2db-api/tests/test_ops_verify_declarations.py`、`r2db-api/tests/test_postgres.py`。§2.5 (訂正註 1 で両 peer の `test_audit_query.py`、訂正註 2 (a) で `docs/ops/BACKUP_RESTORE_R2DB.md` と両 peer の runbook を加えた後) と §3 の 4 の引き継ぎ書の和集合の部分集合。
- 両 peer の `0001` の diff: `git diff 0d7065c -- r2db-api/migrations/0001_*.sql MitateDB-api/migrations/0001_*.sql | wc -l` = 0。
- 両 peer の `0003` の `LC_CTYPE`: `grep -c 'LC_CTYPE'` = r2db 0、MitateDB 0。
- 差し戻し後に加わったファイル (訂正註 5): `security/CONTROL_MAPPING.md` (行参照の追従だけ: 実装担当の機械適用 102 件、基点 `0d7065c` の旧行の内容と現在の新行の内容の一致 102 / 102 を script で再照合; range 参照 :88 `0003_provision_application.sql:217-218` → `:224-225` は対応表が前半だけを置換したのを実装担当が検出して直した; `MitateDB-api/tests/test_audit_query.py::test_isomorphic_target_table_is_pinned_to_its_current_159_rows` → `_161_rows` (:819) は本 WP の件数 pin 改名への追従、監督が直した。文言・claim・版 3.4 は不変。`conformance-tests/test_control_mapping_register.py`: 監督 `pt: 58 passed in 2.11s`)、`tools/dev/README.md`:78 (`ops.py:1728-1752` → `:1737-1761`、監督)。 受け入れ監査の観察 1 で `security/CONTROL_MAPPING.md` の `MitateDB-api/docs/cloud-run-cloud-sql.md` への参照 4 件 (:1123 → :1125 ×1、:2484 → :2486 ×3。F-19 段落の +2 行) も追従した (監督。基点と現在の行内容の一致を確認。r2db runbook と `docs/ops/BACKUP_RESTORE_R2DB.md` への参照は無い)。`conformance-tests/COLLECTION_FLOOR` 4233 → 4262 (完了ゲートでの監督更新)。受け入れ監査の観察 2 (F-19 単体テスト 2 本 × 2 peer の docstring が変異の結果を「turns this green」と書き実測 (赤) と逆に読める) は監督が文言を直した。

**完了条件 19** (D-7 の grep。監督実測 2026-09-26):

- `grep -rn -e 'TEMPLATE template0' -e 'CREATE DATABASE' r2db-api/README.md r2db-api/deploy MitateDB-api/README.md` = **0 件** (`MitateDB-api/deploy/` は存在しない)。
- 同じ grep を `docs/` に掛けると `docs/ops/BACKUP_RESTORE_R2DB.md` の復元先の `CREATE DATABASE` だけに当たる (訂正註 2 (a) で本変更セットが直した文そのもの。差し戻し前 1 件 :28、訂正註 5 (6) で application DB 用と platform DB 用に分けた後は 2 件 :32・:39)。README / deploy に限る読み方 (訂正註 3 (2)) で 0 件。

**完了条件 20** (基点と実装後の集計行。実装担当、逐語):

基点は供与値 (未変更ツリーでの再実測は `r2db-api/tests`・`MitateDB-api/tests`・`tools/tests` の 3 本。絞り込み 4 コマンドの基点は未変更ツリーで再実測していない = 逸脱 (e)、期待形と一致するので採用)。

| コマンド | 基点 | 実装後 |
|---|---|---|
| r2db `test_postgres.py -k "collation or parity_order"` | (未再実測。起草時の grep で該当 def 5 件 = 期待形 `<基点 + 6>` = 11) | `pt: 11 passed, 212 deselected in 2.92s`; 差し戻し後 `pt: 11 passed, 212 deselected in 1.74s` |
| r2db `test_ops_verify_declarations.py` | (未再実測。期待形 `<基点 + 2>`) | `pt: 49 passed in 12.28s`; 差し戻し後 (+3) `pt: 52 passed in 7.19s` |
| MitateDB `test_postgres.py -k "collation or parity_order"` | (未再実測。起草時 0 件 = `no tests ran`) | `pt: 5 passed, 93 deselected in 0.92s`; 差し戻し後 `pt: 5 passed, 93 deselected in 0.78s` |
| MitateDB `test_ops_verify_declarations.py` | (未再実測。期待形 `<基点 + 2>`) | `pt: 51 passed in 11.49s`; 差し戻し後 (+3) `pt: 54 passed in 7.01s` |
| `r2db-api/tests` | `1478 passed` | `pt: 1486 passed in 112.14s` (+8); 差し戻し後 (+3) `pt: 1489 passed in 126.61s` |
| `MitateDB-api/tests` | `1480 passed, 2 subtests passed` | `pt: 1487 passed, 2 subtests passed in 246.62s` (+7); 差し戻し後 (+3) `pt: 1490 passed, 2 subtests passed in 194.85s` |
| conformance `-k "c30 or c28 or c06"` | (基点の参考値: 202) | `pt: 202 passed in 40.44s` |
| `tools/tests` | `591 passed` | `pt: 591 passed in 54.24s`; 差し戻し後 `pt: 591 passed in 54.88s` |

**完了条件 21** (本表): §2.14 の表の全行が変異 (1〜16) または監査照合 (16〜21) を持つ。訂正註 5 (3) で足した M8 / M9 は完了条件 7 / 14 の追加の脚 (本節の差し戻し後の変異表)。

**完了ゲート** (監督、2026-09-26、差し戻し反映後の最終ツリー、main `0d7065c` は動いていないので取り込みなし、solo、使い捨てクラスタ、`tools/dev/gate.py -C .claude/worktrees/r38 --label r112`):

```
gate: 4262 passed, 2 subtests passed in 367.27s (0:06:07)
gate: judge=PASS
gate: pg_database/pg_roles diff 0
```

受け入れ監査の観察 2 件 (CONTROL_MAPPING の runbook 参照 4 件、F-19 単体テストの docstring) を直した最終ツリーで再実行 (label r112b、solo、使い捨てクラスタ):

```
gate: 4262 passed, 2 subtests passed in 406.72s (0:06:46)
gate: judge=PASS
gate: pg_database/pg_roles diff 0
```

`conformance-tests/COLLECTION_FLOOR` 4233 → 4262 (完了ゲートでの監督更新、`conformance-tests/README.md` の運用 3)。内訳: main `0d7065c` の 4241 (R-41 の 4233 + R-38 の 8) + 本 WP の 21 (r2db 11 = T1〜T4・P1・P2・V1・V2・F-19 単体 3、MitateDB 10 = T1・T3・T4・P1・P2・V1・V2・F-19 単体 3)。

## 付録 A. 値集合と PostgreSQL の期待順序

出所: `$SP/pg-collation-measured.md` (監督 2026-09-26、PostgreSQL 16.14。共有ローカル PG に一時 DB を作って計測)。

| 記号 | 内容 |
|---|---|
| 値集合 | `"_"`, `"1"`, `"a"`, `"A"`, `"ä"`, `"aa"`, `"b"`, `"B"`, `"z"`, `"Z"` (10 件、すべて相異なる) |
| A-1 期待順序 (昇順) | `"1" < "A" < "B" < "Z" < "_" < "a" < "aa" < "b" < "z" < "ä"` (codepoint 順 = UTF-8 の byte 順 = `sorted(値集合)`。`LC_COLLATE 'C'` の DB で jsonb の中の文字列・text 列とも実測でこの順) |
| A-2 投入順 | `"b"`, `"Z"`, `"ä"`, `"_"`, `"aa"`, `"1"`, `"B"`, `"a"`, `"z"`, `"A"` (A-1 とも A-4 とも違う固定の置換) |
| A-3 `gt "a"` / `lt "a"` の集合 | `gt "a"` = {`"aa"`, `"b"`, `"z"`, `"ä"`}、`lt "a"` = {`"1"`, `"A"`, `"B"`, `"Z"`, `"_"`} (A-1 の順序から導出。Python の `>` / `<` と同じ) |
| A-4 参考: 現行 (en_US.UTF-8) の昇順 | `"_" < "1" < "a" < "A" < "ä" < "aa" < "b" < "B" < "z" < "Z"` (実測。変異 M1 / M2 のもとで PostgreSQL が返す順序) |

ctype の実測 (P2 の出所):

| DB | datcollate / datctype | `upper('ä')` |
|---|---|---|
| 既定 (現行) | en_US.UTF-8 / en_US.UTF-8 | `Ä` |
| `LC_COLLATE 'C' LC_CTYPE 'C'` | C / C | `ä` (変異 M5 / M6 のもとの値) |
| `LC_COLLATE 'C' LC_CTYPE 'en_US.UTF-8'` | C / en_US.UTF-8 | `Ä` (目標の組合せ。`0003` では `LC_CTYPE` を書かず template0 = クラスタ既定を引き継ぐ。D-1) |
