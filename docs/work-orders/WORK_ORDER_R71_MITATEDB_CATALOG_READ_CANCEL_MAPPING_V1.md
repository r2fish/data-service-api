# 作業指示書 — R-71 MitateDB-api の developer 接続の catalog 読みが、打ち切りを `VALIDATION_FAILED` に写す

## 0. 版数・位置づけ

- **v1.0 (2026-09-21)。** 基点 main `1f82348`。台帳は `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の R-71。変更クラスは **Class D** (実装は B だが、`security/CONTROL_MAPPING.md` に主張を 1 つ足すので重い方。契約 `spec/` は触らない)。D が求める依頼者裁定は依頼者指示 2026-09-19 の委任 (引き継ぎ書 `docs/work-orders/HANDOVER_20260919_FABLE2.md` §2 に逐語) の下で監督が下し、事後確認を引き継ぎ書で伺う。版付きの security-contract 決定は `security/CONTROL_MAPPING.md` の版 **2.19**。
- 設計文書は起こさず、決定は本書 §1 に置く (R-62・R-64 の先例)。設計レビュー 1 回を本書に対して行う。
- 規律は `docs/work-orders/OPERATING_CONDITIONS.md` に従う (commit は監督のみ、道具は `tools/dev/`)。

## 1. 問題と決定 (監督確定)

**問題**: `MitateDB-api/src/mitatedb_api/backend_postgres.py` の developer 接続の catalog 読み 8 本 — `schema_count`、`field_domains`、`field_types`、`all_field_types`、`field_constraints`、`field_types_and_constraints`、`all_field_constraints`、`schema_revision` (基点の `except psycopg.Error` は `:360`・`:417`・`:466`・`:493`・`:550`・`:608`・`:633`・`:831`) — は、`psycopg.Error` を一括で `ValidationError` に写す。role 水準の `statement_timeout` (`0013_role_statement_timeouts.sql`、5000ms) による打ち切り `QueryCanceled` と `lock_timeout` の `LockNotAvailable` もここに入るので、**資源の上限超過が client には `VALIDATION_FAILED` (要求の形の誤り) として返る**。同じファイルの他の操作 (基点で 12 箇所) は同じ 2 つの例外を `ResourceLimitError("operation exceeds the execution budget", limit_class="execution_ms")` に写しており、r2db-api は R-62 で catalog を `LIMIT_EXCEEDED` に揃えた。契約違反ではないが (`spec/data-service-api.v1.json` は status を固定しない)、client は AI agent であり、作り直しても通らない条件を「作り直せば通る」と読む。台帳は `all_field_types` と `all_field_constraints` の 2 本を挙げたが、同じ欠陥は 8 本に在る (うち `field_constraints` は現行の `src/` に呼び出し元が無く、protocol とテストからだけ到達する。`field_types_and_constraints` が置き換えた)。

**実効の上限について**: この 8 本は `_set_timeouts` (取引ごとの `SET LOCAL`) を通らず、切るのは role 水準の `statement_timeout` (`0013`、5000ms) である。`lock_timeout` はこの経路では設定されない (migration に `lock_timeout` は 0 件) ので、実配備で起きるのは `QueryCanceled` だけで、`LockNotAvailable` の枝は既存の 12 箇所と同形の防御である。

**決定**:

- **D-1。** 8 本すべてに、同じファイルの既存の形と同じ枝を足す: `except (psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable):` → `self._developer.rollback()` → `raise ResourceLimitError("operation exceeds the execution budget", limit_class="execution_ms")`。枝の位置は `UndefinedTable` の枝 (在れば) と並べ、末尾の `except psycopg.Error` より前。2 本だけを直して 6 本を残さない (同じ欠陥を先送りしない)。メッセージと `limit_class` は既存の 12 箇所と逐語で同じにする (新しい語彙を作らない)。
- **D-2。** 末尾の `except psycopg.Error` → `ValidationError` の防御的な受けは変えない (モジュール冒頭の (ii) の設計)。`StorageConfigurationError` の枝も変えない。
- **D-3。** cell / HTTP の層は原則として変えない。`ResourceLimitError` は既に他の操作で cell と HTTP を通って `LIMIT_EXCEEDED` (`limit_class="execution_ms"`) になる。**この peer では `LIMIT_EXCEEDED` の denial は durable audit に残らない** (`MitateDB-api/src/mitatedb_api/audit_dispatch.py` の `DURABLE_DENIAL_CODES` は auth 系 6 コードの包含集合) — r2db-api の R-62 と違う点で、本件はそれを変えない。**実装担当はまず、8 本の呼び出し元 (`cell.py` ほか) に `ValidationError` を受けて握りつぶす・別の意味に読み替える箇所が無いか、`ResourceLimitError` が catalog の経路 (`GET /v1/catalog`) と query / transact / schema の経路で client まで `LIMIT_EXCEEDED` として届くかを現物で読む。** 届かない経路が在れば、実装せず報告する (裁定は監督)。
- **D-4 (SQLite backend)。** `backend_sqlite.py` は対象外 (`statement_timeout` に当たる打ち切りが無い)。両 backend の同型性を固定するテストが在って赤になるなら直さず報告する。
- **D-5 (r2db-api)。** 触らない。R-62 で済んでいる。
- **D-6 (開示)。** `security/CONTROL_MAPPING.md` の SI-08 / MitateDB-api / 既定 / Control に主張を 1 つ足す (追記であり、既存の主張を書き換えない。履歴への移動は無い): developer 接続の catalog 読みが role 水準の `statement_timeout` による打ち切りを他の操作と同じ `LIMIT_EXCEEDED` (`limit_class` = `execution_ms`) に写すこと、**この読みの実効の上限は role 水準の値 (5000ms) で、要求ごとの budget では縮まらず、`MITATEDB_MAX_EXECUTION_MS` を 5000 以外にした配備では宣言した `execution_ms` と一致しないこと**、根拠のテスト名。`LockNotAvailable` は開示に書かない (実配備で起きない防御の枝)。**文案は実測 (テスト名) の後に監督が確定する** (`OPERATING_CONDITIONS.md` §1.5 の 34・35)。実装担当は版数行・主張・再実測文の案を先例の形で報告に書き、`security/` は監督の確定文ファイル `$SP/r71-final/` を待って逐語複製する。R-64 の検査が効くので、引くテスト名は裸の形なら `MitateDB-api/tests` に在る名前、完全形なら実在の path で書く。

**却下した代替案**: (0) 8 本に deadline を渡して `_set_timeouts` を通す (r2db-api の R-62 と同型) — 上限が宣言した `execution_ms` に追随する点で優れるが、backend の protocol (両 backend)・cell の全呼び出し元の変更になり、cell の limit gate の外から呼ばれる読みの deadline の出所を決める設計が要る。role 水準の上限は R-45 WP-F で「明示の deadline を持たない文」のために採った統制で、本件は写像の誤りだけを直す。宣言との不一致は D-6 で開示し、追随させる件は台帳に起票する (§3a)。(1) 台帳どおり 2 本だけ直す — `field_domains` は query / mutation のたびに通る読みで、同じ誤った写像が残る。(2) 末尾の一括の受けを `SERVICE_UNAVAILABLE` 系に変える — モジュール冒頭 (ii) の設計判断の変更で、本件の範囲を越える。

## 2. WP-1 — 8 本に打ち切りの枝を足し、テストで固定する

### 2.1 触ってよいパス

- `MitateDB-api/src/mitatedb_api/backend_postgres.py`
- `MitateDB-api/tests/` の該当するテストファイル (新設してよい。既存の `QueryCanceled` のテストの置き場所と型に合わせる)
- `docs/code-history/` に、コメントの来歴検査 (`tools/check_comment_provenance.py`) が求める記録が要る場合だけ、その 1 箇所
- (D-6、監督の確定文の後) `security/CONTROL_MAPPING.md`

### 2.2 完了条件

1. 8 本それぞれについて、`QueryCanceled` が `ResourceLimitError` (`limit_class == "execution_ms"`、メッセージは既存と同じ) になり、接続が rollback されて次の呼び出しが通ることをテストが固定する。`LockNotAvailable` も同じだが、この経路では実配備で起きないので**合成の注入だけ**で駆動する (8 本に parametrize してよい。空振り禁止: parametrize の全件で assert が走ること)。**少なくとも 1 本は実 PostgreSQL の本物の `QueryCanceled`** で通す。型は先例 `MitateDB-api/tests/test_audit_query_reader_errors.py` に合わせる (別接続で対象の表に ACCESS EXCLUSIVE lock を保持し、role の `statement_timeout` を一時的に縮めて `pg_roles.rolconfig` から復元する。sleep とクエリを競争させる形では作らない)。この型は `_mdb_field_types` / revision の表を読む 7 本に効き、`information_schema.tables` だけを読む `schema_count` には効かないので、`schema_count` は合成の注入でよい。
2. client から見える結果を 1 本のテストで固定する: `GET /v1/catalog` (または cell の catalog) の読みが打ち切られたとき `LIMIT_EXCEEDED`・`limit_class="execution_ms"` が返り、`VALIDATION_FAILED` ではない。監査行は assert しない (D-3: この peer は `LIMIT_EXCEEDED` を durable audit に残さない)。
3. 末尾の `except psycopg.Error` → `ValidationError` が他の `psycopg.Error` に対して変わらないことを、既存のテストが緑であることで示す (新しいテストは足さない)。
4. `tools/dev/pt.py … -- MitateDB-api/tests -q` が緑。D-6 の複製の後は `conformance-tests/test_control_mapping_register.py` も `pt.py` で回して緑 (ブロック長・行長・軸の形・テスト名の解決)。
5. `tools/check_comment_provenance.py` (src を触るので `--base 1f82348` と `--register` の両方。引数は `--help`)・`tools/check_doc_refs.py`・`tools/public_value_scan.py` が緑。既存の関数に docstring を足さない。足すコメントは最小限で、R-63 の規則で通る形にする。
6. `MitateDB-api/tests/test_limit_class_vocabulary.py` の件数 pin (`len(findings) == 36`。8 本で 44 になる) と由来文を実測で更新する (`OPERATING_CONDITIONS.md` §1.5 の 34)。両 peer の同型性テスト (`_ISOMORPHIC_TARGETS`) と L1 details 語彙の AST 走査 (`tests/test_l1_details_vocabulary_ast_scan.py` の行番号 allowlist・件数 pin) が緑。行番号のずれで赤になったら、`OPERATING_CONDITIONS.md` §1.5 の 40b に従い実測で更新し、報告に列挙する (理由付き除外集合の変更は監督裁定)。
7. 下の対応表に対応の無い行が無い。

### 2.3 完了条件 → 変異

| 完了条件 | 変異 | 期待 |
|---|---|---|
| 1 (8 本の枝) | M1〜M8: 8 本それぞれの新しい枝を 1 本ずつ消す (1 変異 = 1 メソッド。`tests` にはそのメソッドの parametrize の 1 件だけを置く — 件数 pin も赤になるが `mutate.py` は最初の失敗で止まるので別の変異で見る) | その 1 件が赤 |
| 6 (件数 pin) | M12: 新しい枝を 1 本消す (`tests` は `test_limit_class_vocabulary.py` の件数 pin のテストだけ) | 赤 |
| 1 (メッセージ) | M13: 新しい枝の 1 つのメッセージを別の文にする | メッセージを assert するテストが赤 |
| 1 (rollback) | M9: 新しい枝の 1 つから `self._developer.rollback()` を消す | 「次の呼び出しが通る」のテストが赤 |
| 1 (`limit_class`) | M10: 新しい枝の 1 つの `limit_class` を別の値にする | 赤 |
| 2 | M11: `all_field_types` の新しい枝を消す | client から見える結果のテストが赤 |
| 3・4・5・6 | 監査照合 (道具の出力行) | — |
| 7 | 監査照合 (本表) | — |

### 2.4 道具の引数

- `tools/dev/pt.py -C .claude/worktrees/<担当 worktree> -- MitateDB-api/tests -q` (約数分。前景・同期、Bash timeout 600000)
- `tools/dev/pt.py -C .claude/worktrees/<担当 worktree> -- conformance-tests/test_control_mapping_register.py -q` (D-6 の複製の後)
- `tools/dev/mutate.py "$SP/r71-mutations.json" -C .claude/worktrees/<担当 worktree>`
- worktree から subprocess を起こすテストが在る場合の `PYTHONPATH` は `OPERATING_CONDITIONS.md` §2 の 17 に従う。

## 3. レビューと受け入れ

設計レビュー 1 回 (本書 §1 に対して、WP-1 の着手前。**実施済み 2026-09-21**: 高 3・中 6・低 2 を裁定して本書に反映した — 監査の denial の誤った前提の削除、件数 pin、`LockNotAvailable` の扱い、12 箇所、register テスト、`field_constraints` の到達性、実 PostgreSQL の型の先例、実効の上限の開示、代替案 (0)、メッセージの変異。未コミットの起草版への反映なので本文を直した)。コードレビュー 1 回。受け入れ監査 1 回。監督が完了ゲートの集計行・完了条件・監査のパケットを照合して判定する。性能差分は添えない (失敗の枝だけの変更で、成功の経路の文は変わらない)。

## 3a. 範囲外 (起票のみ)

- catalog 読みの上限を宣言した `execution_ms` に追随させる件 (代替案 (0))。
- `security/CONTROL_MAPPING.md` の SI-08 / MitateDB-api / 既定の `execution_ms` の主張が持つ位置参照 2 件 (`cell.py:4044`、`backend_postgres.py:1658-1661`) が陳腐化している件と、`file:line` の位置参照を機械で解決する検査が無い件 (設計レビュー 1 の中-8。R-64 の検査はテスト名しか見ない)。

## 4. 記録 (統合時に監督が埋める)

### 4.1 訂正註 2026-09-21 (コードレビュー 1 と受け入れ監査への監督裁定。§1〜§3 の本文は書き換えない)

- **完了条件 5 の読み替え。** `tools/check_comment_provenance.py --base` の §4.1 (1) は「コード不変」の照合で、`src/` を変える WP では構造上必ず赤になる。求めるのは「`--register` が緑、`--base` は (1) のほかに正当な赤が無い」である。
- **§4.1 (2) の 2 行は道具の誤検出として受ける。** 最終の木での逐語: `FAIL (§4.1 (2)) MitateDB-api/src/mitatedb_api/backend_postgres.py:619 scope/anchor ('PostgresBackend.all_field_constraints', 'stmt#1'): the sequence of CH-ID-less blocks changed (old 1, new 0)`、同 `:477 … ('PostgresBackend.all_field_types', 'stmt#1') …`。根拠: `src/` の差分は追加 24 行・削除 0 行、2 つの docstring は基点と sha256 一致、コメントの列は基点と同一 (監督・コードレビュー・受け入れ監査の 3 者が確認)。塊の直後の `try` 文に except 節が増えて文の整列が切れただけである。`docs/code-history/` への登録はしない。道具の件は台帳 R-89。
- **実装報告のこの点は証拠にしない。** 実装報告は 2 回とも同じコマンドを `OK: 88 blocks checked` と書いたが、worktree を cwd にした 3 者の再実行はいずれも FAIL 3 行である (1 回目は main checkout を測っていた。2 回目の原因は不明)。他の報告値 (pt 1422、変異 14/14、件数 pin 44、allowlist 20、収集 +17) は監査の実測と一致した。
- **枝の順序** は既存の 12 箇所に合わせた (打ち切りの枝が `UndefinedTable` の枝の前)。§2.3 の表に **M14** を足す: `all_field_types` の新しい枝を消す → `::test_all_field_types_real_postgresql_query_canceled_becomes_resource_limit_error` が赤 (完了条件 1 の実 PostgreSQL の 1 本。コードレビューが足した)。
- 合成の注入は、例外を上げる前に本物の `SELECT 1/0` で取引を abort させる (rollback の有無を次の呼び出しで識別するため。M9 が最初 green だったのを実装担当が直した)。実際の打ち切りの経路は実 PostgreSQL の 1 本と M14 が押さえる。

### 4.2 実施と受け入れ

- 実施 2026-09-21。`backend_postgres.py` の 8 本に既存の 12 箇所と逐語同形の枝 (追加 24 行)。D-3 の読解: 8 本の呼び出し元に `ValidationError` を読み替える箇所は無く、`ResourceLimitError` は query / mutate / schema / catalog のどの経路でも HTTP の同じ写像で `LIMIT_EXCEEDED` になる。新設 `MitateDB-api/tests/test_r71_catalog_read_cancel_mapping.py` (17 件: 8 本 × 合成の `QueryCanceled` / `LockNotAvailable`、実 PostgreSQL の `QueryCanceled` 1 本、`GET /v1/catalog` の client から見える結果 1 本ほか)。`test_limit_class_vocabulary.py` の件数 pin 36 → 44、`test_l1_details_vocabulary_ast_scan.py` の行番号 allowlist 20 行を実測で更新 (件数と理由付き除外集合は不変)。
- 道具: `MitateDB-api/tests` `1422 passed, 2 subtests passed`、変異 M1〜M14 は全部 `expect=red got=red` (復元は sha256 2 回)、register テスト `43 passed`、`tools/check_control_mapping_split.py --base 1f82348 --expect "missing=0 added=1 moved=0 …"` 終了コード 0、`check_doc_refs` 0 dangling、`public_value_scan` 0 flagged、comment provenance `--register` 緑。
- `security/CONTROL_MAPPING.md` 版 **2.19**: SI-08 / MitateDB-api / 既定 / Control に主張 1 行 (1,339 字)。ブロックは 5,555 → 6,893 (残り 8,307)。最長は SI-09 / MitateDB-api / `platform upgrade` 12,681 で不変。確定文は監督がスクリプトで入れた。
- 設計レビュー 1 回 (高 3・中 6・低 2、全件を裁定して反映)。コードレビュー 1 回 (高 2・中 1・低 4: 高-2 の `R-87` 未起票は起票して解消、低-4 の恒真の assert は意図の明示として残す、他は差し戻し 1 で反映)。受け入れ監査 1 回: 完了条件 1〜4・6・7 は充足、5 は上の読み替えで充足と裁定。
- 完了ゲート (監督が単独実行、最終の木): `gate: 3822 passed, 2 subtests passed in 356.07s (0:05:56)` / `gate: judge=PASS` / `gate: pg_database/pg_roles diff 0`。増分 +17 は新設のテストファイルの収集数と一致。**受け入れる。**
- **client に見える挙動の変更**: MitateDB-api で catalog 系の読みが role 水準の `statement_timeout` で打ち切られたとき、400 `VALIDATION_FAILED` だったものが `LIMIT_EXCEEDED` (`limit_class` = `execution_ms`) になる (契約の error 語彙の内)。
- 起票: 台帳 R-87 (上限を宣言した `execution_ms` に追随させる)、R-88 (`file:line` の位置参照の機械検査)、R-89 (comment provenance §4.1 (2) の誤検出)。

